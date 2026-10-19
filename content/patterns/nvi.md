---
title: 非虚接口与模板方法
summary: public 非虚函数负责检查、加锁、记录，再调用 private 虚函数完成可定制的那一步；为什么 private 虚函数能被覆盖，访问检查和默认实参为什么都看静态类型，构造期间为什么不能走模板方法，final 在这里为什么不一定能去虚化，以及标准库自己怎样使用这个结构。
status: draft
order: 30
since: c++98
papers: P0847R7, P2900R14
related: class.virtual, class.access, class.cdtor, class.abstract, dcl.fct.default, dcl.contract.func, mem.res.class, locale.categories, patterns/crtp, patterns/strategy, patterns/raii, toolchain/object-layout-and-vtables, topics/allocators-and-pmr
tags: 惯用法, 虚函数, 访问控制, 模板方法, 去虚化
updated: 2026-10-19
---

!!! tldr
    - 非虚接口（NVI）把一个虚函数拆成两层：外层 public 非虚函数是调用方唯一的入口，前置检查、加锁、日志、统计都写在这里一次；内层 private 虚函数是派生类唯一能改的部分。
    - private 虚函数可以被覆盖，因为判断覆盖不考虑访问权；虚调用的访问检查按调用表达式的静态类型做，派生类把覆盖函数改成 public 也打不开基类的门。
    - 虚函数的默认实参按静态类型取，覆盖函数里另写一个默认值只会制造两套行为。NVI 把默认实参放在非虚包装上，问题自然消失。
    - 构造和析构期间虚调用只分派到当前类的版本，所以模板方法不能在基类构造函数里启动；分派到纯虚函数是 UB。
    - 在 NVI 里，`final` 不一定能让 Clang 去虚化，因为虚调用写在基类的包装函数里，那里的静态类型是基类。改用 deducing this 写包装，或者整体换成编译期多态（[[patterns/crtp|CRTP]]），才能按派生类型直接调用。

## 一个虚函数承担了两件事

下面是一个读取数据的抽象接口。调用方通过 `Source&` 使用它，派生类实现具体的数据来源。

```cpp title="public-virtual.cpp" ok
#include <cstddef>
#include <span>

class Source {
public:
  virtual ~Source() = default;
  // 约定：buf 不能为空，返回值不超过 buf.size()，
  // 多线程使用时调用方负责加锁
  virtual std::size_t read(std::span<char> buf) = 0;
};
```

`read` 同时是两样东西：对调用方的接口（必须满足哪些前置条件、保证什么结果），和对派生类的定制点（数据从哪里来）。这两者的读者不同，演化的节奏也不同。

把它们放在同一个函数上，接口上的约定就只能写在注释里。每个派生类都要自己检查参数、自己加锁、自己统计，少写一处就是一个 bug；基类以后想加一条日志，也得改遍所有派生类。

**非虚接口**（Non-Virtual Interface，NVI）的做法是把这两件事拆开：public 函数不是虚函数，它做所有派生类都该做的事，然后调用一个 private 虚函数完成真正可变的那一步。

```cpp run title="nvi.cpp" ok
#include <cassert>
#include <cstddef>
#include <cstdio>
#include <mutex>
#include <span>
#include <string_view>

class Source {
public:
  virtual ~Source() = default;

  // 唯一的入口：检查、加锁、统计都在这里
  std::size_t read(std::span<char> buf) {
    assert(!buf.empty());                  // 前置条件
    std::lock_guard lk(m_);
    std::size_t n = do_read(buf);
    assert(n <= buf.size());               // 后置条件
    total_ += n;
    return n;
  }
  std::size_t total() const { return total_; }

private:
  // 定制点：派生类只决定数据从哪里来
  virtual std::size_t do_read(std::span<char> buf) = 0;

  std::mutex m_;
  std::size_t total_ = 0;
};

class StringSource final : public Source {
  std::string_view s_;
public:
  explicit StringSource(std::string_view s) : s_(s) {}
private:
  std::size_t do_read(std::span<char> buf) override {
    std::size_t n = s_.copy(buf.data(), buf.size());
    s_.remove_prefix(n);
    return n;
  }
};

int main() {
  StringSource src("hello, world");
  Source& s = src;
  char buf[5];
  while (std::size_t n = s.read(buf))
    std::printf("[%.*s]", int(n), buf);
  std::printf("\ntotal = %zu\n", s.total());
}
```

本机 Clang 23 加 ASan、UBSan 运行，输出 `[hello][, wor][ld]` 和 `total = 12`。`StringSource` 只写了七行逻辑，没有碰锁和计数；它也没办法绕过检查，因为外界根本调用不到 `do_read`。

这种结构的一般形式叫**模板方法**（template method）：基类的一个非虚函数固定算法的骨架，骨架中的若干步骤是虚函数，由派生类填写。NVI 是骨架只有一步时的特例。这里的模板与 C++ 模板无关，指的是骨架本身。

```cpp
// 模板方法：骨架固定，三个步骤可定制
void Exporter::run() {
  auto data = do_collect();
  if (do_validate(data))
    do_write(data);
}
```

## private 虚函数为什么能被覆盖

初学者常以为 private 成员对派生类不可见，因此不能覆盖。覆盖的判定确实与访问权无关：派生类里一个成员函数与基类虚函数的名字、形参列表、cv 限定、引用限定都对应，它就覆盖那个虚函数（[[class.virtual#2]]）。[[class.virtual]] 的脚注明确写着，判断覆盖时不考虑访问控制。

访问控制管的是能不能**指名**一个成员（[[class.access]]）。覆盖不需要指名基类的函数，派生类只是声明了一个自己的函数。所以派生类能覆盖 `Base::step`，却不能调用它：

<div class="compare" markdown="1">

```cpp title="private-hook.cpp" error
class Base {
public:
  void run() { step(); }
  virtual ~Base() = default;
private:
  virtual void step() {}
};
class Derived : public Base {
  void step() override { // OK: 覆盖
    Base::step();  // error: private
  }
};
```

```cpp run title="protected-hook.cpp" ok
class Base {
public:
  void run() { step(); }
  virtual ~Base() = default;
protected:
  virtual void step() {}
};
class Derived : public Base {
  void step() override {
    Base::step();  // OK: protected
  }
};
int main() { Derived d; d.run(); }
```

</div>

左边 Clang 报 `'step' is a private member of 'Base'`。`Base::step()` 这种限定名调用不经过虚分派（[[class.virtual#16]]），它是在指名 `Base::step`，访问检查就生效了。

由此得到选择钩子访问权的规则。派生类的覆盖函数需要先调用基类的默认实现时，钩子用 protected；基类的实现只是默认值或者干脆是纯虚函数，派生类没理由调用它时，用 private。标准库两种都用：`std::pmr::memory_resource` 的 `do_allocate` 是 private，`std::basic_streambuf` 的 `sync`、`overflow` 等是 protected（见下文）。

析构函数是例外。基类析构函数要么是 public 的虚函数，允许通过基类指针 `delete`；要么是 protected 的非虚函数，禁止这样做。它不能做成 private 的钩子，因为派生类的析构函数要隐式调用它。

## 访问检查看静态类型

派生类可以在覆盖时把访问权改宽，但这不影响经由基类的调用：

```cpp title="access-static-type.cpp" error
class Base {
public:
  void run() { step(); }
  virtual ~Base() = default;
private:
  virtual void step() {}
};
class Derived : public Base {
public:
  void step() override {}  // 覆盖时改成 public
};
int main() {
  Derived d;
  Base& b = d;
  d.step();   // OK: 按 Derived::step 检查，public
  b.step();   // error: 按 Base::step 检查，private
}
```

!!! std "[class.access.virt] ¶2"
    Access is checked at the call point using the type of the expression used to denote the object for which the member function is called.

虚函数的访问权由它自己的声明决定，不受覆盖它的函数影响（[[class.access.virt#1]]）。`b.step()` 里 `b` 的静态类型是 `Base`，名字查找找到 `Base::step`，它是 private，于是报错；运行时会分派到哪个函数与此无关。完整的讨论见 [[class.access]] 的虚函数一节。

对 NVI 来说，这条规则保证了基类的门只有基类能开。一个派生类把 `do_read` 改成 public，也只是让持有 `StringSource&` 的代码能绕过检查；所有经由 `Source&` 的代码仍然只能走 `read`。

## 默认实参：只写在非虚包装上

```cpp run title="virtual-default-arg.cpp" ok
#include <cstdio>
struct Shape {
  virtual ~Shape() = default;
  virtual void draw(int width = 1) const {
    std::printf("Shape  width=%d\n", width);
  }
};
struct Circle : Shape {
  void draw(int width = 3) const override {
    std::printf("Circle width=%d\n", width);
  }
};
int main() {
  Circle c;
  const Shape& s = c;
  c.draw();   // Circle width=3
  s.draw();   // Circle width=1
}
```

两次调用执行的都是 `Circle::draw`，但 `width` 一次是 3，一次是 1。默认实参在编译期由调用点补上，编译器只知道静态类型，所以用的是静态类型那个声明上的默认值；覆盖函数也不会继承被覆盖函数的默认实参（[[dcl.fct.default#10]]）。这段程序是良构的，行为也完全确定，只是两个调用点看到了两套默认值。本机 Clang 23 开 `-Wall -Wextra` 不给警告。

NVI 让这个问题没有机会出现：默认实参写在非虚的 `draw` 上，虚函数 `do_draw` 不带默认实参，派生类无从覆盖默认值。

<div class="compare" markdown="1">

```cpp run title="nvi-default-arg.cpp" ok
#include <cstdio>
class Shape {
public:
  virtual ~Shape() = default;
  void draw(int width = 1) const {
    do_draw(width);
  }
private:
  virtual void do_draw(int w) const = 0;
};
class Circle : public Shape {
  void do_draw(int w) const override {
    std::printf("Circle w=%d\n", w);
  }
};
int main() {
  Circle c;
  const Shape& s = c;
  c.draw();   // Circle w=1
  s.draw();   // Circle w=1
}
```

```cpp
// 标准库的写法：包装和虚函数
// 都带同一个默认值（[streambuf]）
pos_type pubseekoff(off_type off,
    ios_base::seekdir way,
    ios_base::openmode which
      = ios_base::in | ios_base::out);
// protected:
virtual pos_type seekoff(off_type off,
    ios_base::seekdir way,
    ios_base::openmode which
      = ios_base::in | ios_base::out);
```

</div>

`basic_streambuf` 的虚函数 `seekoff` 也带默认实参（[[streambuf.virt.buffer]]），与包装 `pubseekoff` 的默认值相同。外部代码只能调用 `pubseekoff`；`seekoff` 上的默认值只对派生类内部的直接调用有意义，两处一致就不会出现上面的分裂。

## 构造和析构期间不能启动模板方法

模板方法的骨架会调用虚函数。在基类构造函数里执行骨架，看起来是一种方便的初始化方式，但这时派生类部分还没有构造：

```cpp run title="template-method-in-ctor.cpp" ub
#include <cstdio>
class Plugin {
public:
  Plugin() { init(); }          // 构造期间启动模板方法
  virtual ~Plugin() = default;
  void init() {
    std::puts("Plugin::init begin");
    do_init();                  // 分派到 Plugin::do_init：纯虚
    std::puts("Plugin::init end");
  }
private:
  virtual void do_init() = 0;
};
class Audio : public Plugin {
  void do_init() override { std::puts("Audio::do_init"); }
};
int main() { Audio a; }
```

在构造函数或析构函数中（直接或间接）对正在构造或析构的对象发起虚调用，调用的是构造函数或析构函数所属类中的最终覆盖函数，不是更派生类中的覆盖函数（[[class.cdtor#4]]）。这里那个函数是纯虚的 `Plugin::do_init`，对纯虚函数的这种虚调用是 UB（[[class.abstract#6]]）。

本机 Clang 23 编译时没有任何警告：Clang 只在构造函数直接调用纯虚函数时提示，这里中间隔了一层非虚的 `init`。运行时 libc++abi 打印 `Pure virtual function called!` 后终止，退出码 134。如果 `do_init` 不是纯虚的，程序不会崩溃，而是静静地执行基类版本，更难发现。细节见 [[class.cdtor]]。

需要构造后立即执行骨架时，把构造和启动分成两步，由工厂函数保证两步都发生：

```cpp run title="two-phase.cpp" ok
#include <cstdio>
#include <memory>
class Plugin {
public:
  virtual ~Plugin() = default;
  template <class T> static std::unique_ptr<Plugin> create() {
    std::unique_ptr<Plugin> p = std::make_unique<T>();
    p->init();                  // 构造已结束，分派到 T::do_init
    return p;
  }
  void init() { std::puts("init: begin"); do_init(); std::puts("init: end"); }
protected:
  Plugin() = default;
private:
  virtual void do_init() = 0;
};
class Audio : public Plugin {
  void do_init() override { std::puts("Audio::do_init"); }
};
int main() { auto p = Plugin::create<Audio>(); }
```

析构是对称的问题：基类析构函数运行时派生类部分已经销毁，在那里调用的钩子同样只会分派到基类版本。清理步骤需要派生类参与时，要么由派生类的析构函数自己完成，要么提供一个在销毁之前调用的 `close()`。

## 标准库里的非虚接口

标准库里有三处成体系地使用这个结构，钩子的访问权各不相同。

| 类 | public 非虚函数 | 虚函数 | 钩子访问权 |
|---|---|---|---|
| `std::basic_streambuf` | `pubsync`、`pubseekoff`、`sgetc`、`sputc`… | `sync`、`seekoff`、`underflow`、`overflow`… | protected |
| `std::num_put` 等 locale facet | `put`、`get`… | `do_put`、`do_get`… | protected |
| `std::pmr::memory_resource` | `allocate`、`deallocate`、`is_equal` | `do_allocate`、`do_deallocate`、`do_is_equal` | private |

`basic_streambuf` 展示了 NVI 的另一个用途：快速路径内联，慢速路径才走虚调用。`pubsync()` 只是返回 `sync()`（[[streambuf.buffer#4]]），但 `sgetc()` 在缓冲区里还有字符时直接返回 `*gptr()`，只有缓冲区读空时才调用虚函数 `underflow()`（[[streambuf.pub.get#5]]）。逐字符读取的绝大多数调用因此只是一次比较和一次读内存。

locale facet 的每个 public 成员函数都只是转发，如 `num_put::put` 返回 `do_put(...)`（[[facet.num.put.members#1]]）。用户定制格式时派生 facet、覆盖 `do_put`，调用方仍然调用 `put`。

`memory_resource` 的包装不只是转发。`allocate` 除了调用 `do_allocate`，还规定在分配到的存储中隐式创建对象（[[mem.res.public#2]]），这是派生类无法也不必关心的语义。`do_allocate` 的前置条件是对齐值为 2 的幂（[[mem.res.private#1]]）。

```cpp run title="counting-resource.cpp" ok
#include <cstddef>
#include <cstdio>
#include <memory_resource>
#include <vector>

class counting_resource : public std::pmr::memory_resource {
  std::pmr::memory_resource* up_;
public:
  std::size_t live = 0;
  explicit counting_resource(std::pmr::memory_resource* up) : up_(up) {}
private:  // 与基类一致，保持 private
  void* do_allocate(std::size_t n, std::size_t align) override {
    void* p = up_->allocate(n, align);   // 经由上游的 public 包装
    live += n;
    return p;
  }
  void do_deallocate(void* p, std::size_t n, std::size_t align) override {
    up_->deallocate(p, n, align);
    live -= n;
  }
  bool do_is_equal(const memory_resource& o) const noexcept override {
    return this == &o;
  }
};

int main() {
  counting_resource r(std::pmr::new_delete_resource());
  {
    std::pmr::vector<int> v(&r);
    v.resize(100);
    std::printf("live = %zu\n", r.live);   // live = 400
  }
  std::printf("live = %zu\n", r.live);     // live = 0
}
```

本机 libc++ 输出 `live = 400` 和 `live = 0`。覆盖函数调用上游资源时走的也是 `allocate`，不是 `do_allocate`：后者在 `memory_resource` 里是 private，外部写 `r.do_allocate(8, 8)` 会得到 `'do_allocate' is a private member of 'std::pmr::memory_resource'`。memory resource 的完整用法见 [[topics/allocators-and-pmr]]。

## C++26 contracts 放在包装上

非虚包装本来就是写前置条件和后置条件的地方。C++26 的函数契约断言（[[dcl.contract.func]]）让这些条件成为声明的一部分，调用方和工具都能看到：

```cpp
class Source {
public:
  virtual ~Source() = default;
  std::size_t read(const std::span<char> buf)
    pre(!buf.empty())
    post(n : n <= buf.size())
  {
    return do_read(buf);
  }
private:
  virtual std::size_t do_read(std::span<char> buf) = 0;
};
```

`post(n : ...)` 中的 `n` 指代返回值。`buf` 前面的 `const` 不是装饰：后置条件里 odr-use 了按值传递的形参，这个形参在函数的所有声明上都必须是 const 类型（[[dcl.contract.func#7]]），否则函数体可能先改掉 `buf`，后置条件检查的就不是调用方传进来的值了。

断言写在非虚包装上，前置条件只写一次，对所有派生类都成立，派生类也无法放宽它。两点需要注意：契约断言在函数体之前求值，所以检查发生在包装函数体内加锁之前；每次求值采用 ignore、observe、enforce 还是 quick-enforce 语义由实现定义（[[basic.contract.eval#2]]），可以被整体关掉。因此它适合表达调用方的义务，不能代替那些无论如何都必须执行的运行时校验。

上面的代码不标判定：本机 Clang 23 尚未实现 contracts，遇到 `pre` 时报语法错误。

## `final` 与去虚化

**去虚化**（devirtualization）指编译器在编译期确定了虚调用的目标，把间接调用换成直接调用，进而内联。最常见的依据是 `final`：对象的静态类型是一个 `final` 类，最终覆盖函数就只能是这个类里的那个。

```cpp title="final-direct.cpp" ok
struct Base {
  virtual ~Base() = default;
  virtual int do_run(int x) = 0;
};
struct Twice final : Base {
  int do_run(int x) override { return x * 2; }
};
int call(Twice& t, int x) { return t.do_run(x) + 1; }
```

本机 Clang 23 `-O2 --target=x86_64-linux-gnu` 编译 `call`，去掉 `final` 和加上 `final` 的结果：

<div class="compare" markdown="1">

```text
; 没有 final
pushq   %rax
movq    (%rdi), %rax   ; 读 vptr
callq   *16(%rax)      ; 间接调用
incl    %eax
popq    %rcx
retq
```

```text
; 有 final
leal    1(,%rsi,2), %eax  ; x*2+1
retq
```

</div>

在 NVI 里情况不同。把同样的 `Twice final` 换成 private 钩子、通过 `run` 调用：

```cpp title="final-nvi.cpp" ok
struct Base {
  virtual ~Base() = default;
  int run(int x) { return do_run(x) + 1; }
private:
  virtual int do_run(int x) = 0;
};
struct Twice final : Base {
private:
  int do_run(int x) override { return x * 2; }
};
int call(Twice& t, int x) { return t.run(x); }
```

本机 Clang 23 `-O2` 为 `call` 生成的代码与没有 `final` 时完全相同，仍然是读 vptr 加间接调用（x86-64 和 arm64 都是如此）。原因是虚调用 `do_run(x)` 写在 `Base::run` 里，那里 `*this` 的静态类型是 `Base`。前端按 `Base` 生成了一次普通的虚调用；`run` 内联进 `call` 之后，优化器看到的只是从某个对象读出的 vptr，它不知道这个对象的动态类型。

在这些情况下 Clang 仍然能去虚化：

- 对象在同一个函数里构造（如 `Twice t; return t.run(x);`），优化器看到了构造函数写入的 vptr，有没有 `final` 都会内联成 `x*2+1`；
- 开启 LTO 并加 `-fwhole-program-vtables -fvisibility=hidden`，链接时发现 `do_run` 在整个程序里只有一个实现，同样内联，此时 `final` 也不是必需的；
- 把包装写成 deducing this 的函数模板，让调用处的静态类型进入包装函数（下一节）。

这里的观察只针对本机 Clang 23；GCC 的过程间类型传播策略不同，没有在本机验证。

性能差别有多大取决于钩子本身的大小。本机 Apple M2 Pro 上，循环 5 亿次经由 `Base&` 调用 `run`，约 480 ms，即每次约 1 ns；经由去虚化的路径，Clang 把整个循环折叠成了闭式计算，耗时接近 0。真正的收益来自内联之后的进一步优化，而不是省下的那一次间接跳转。钩子本身做的是 I/O、分配或加锁时，这 1 ns 无关紧要。

## 编译期的替代：deducing this 与 CRTP

C++23 的显式对象形参（deducing this，[[P0847R7]]）让包装函数可以拿到调用处的静态类型：

```cpp title="deducing-this-nvi.cpp" ok
struct Base {
  virtual ~Base() = default;
  template <class Self>
  int run(this Self& self, int x) {
    return self.do_run(x) + 1;   // 在 Self 上查找 do_run
  }
private:
  virtual int do_run(int x) = 0;
};
struct Twice final : Base {
private:
  friend Base;                   // 让 Base::run 能指名 Twice::do_run
  int do_run(int x) override { return x * 2; }
};
int call(Twice& t, int x) { return t.run(x); }       // 直接内联
int call_base(Base& b, int x) { return b.run(x); }   // 虚调用
```

本机 Clang 23 `-O2` 下 `call` 编译为一条 `leal 1(,%rsi,2), %eax`，`call_base` 仍是间接调用。同一个接口同时支持两种用法：持有基类引用的代码得到运行时多态，知道具体类型的代码得到直接调用。

代价是访问控制。`self.do_run` 在 `Self` 为 `Twice` 时找到的是 `Twice::do_run`，它在 `Twice` 里是 private，而这段代码属于 `Base`，不是 `Twice` 的成员也不是友元。去掉 `friend Base;` 后 Clang 报 `'do_run' is a private member of 'Twice'`。每个派生类都要写这行友元声明，或者把钩子改成 public，后者又放弃了 NVI 的封装。此外 `run` 成了模板，必须定义在头文件里。

如果根本不需要运行时多态，可以去掉虚函数，用 [[patterns/crtp|CRTP]] 或不带虚函数的 deducing this 写同样的骨架。那时没有 vptr，没有共同的基类类型可以放进容器，派生类的错误要到实例化时才报。几种做法的对比：

| | NVI（虚钩子） | deducing this 包装 + 虚钩子 | CRTP / 纯静态 |
|---|---|---|---|
| 运行时多态，可放进 `vector<unique_ptr<Base>>` | 能 | 能 | 不能 |
| 已知具体类型时去虚化 | 依赖优化器，本机 Clang 不能 | 能 | 无虚调用 |
| 钩子可以 private | 能 | 需要 `friend Base` | 需要友元 |
| 包装函数可以放在 `.cpp` 里 | 能 | 不能（模板） | 不能 |
| 对象大小 | 多一个 vptr | 多一个 vptr | 不增加 |

需要在运行时替换算法本身，而不是让派生类填写步骤时，见 [[patterns/strategy]]。

## 什么时候用

| 情况 | 建议 |
|---|---|
| 公开的多态基类，接口上有检查、加锁、日志、统计 | 用 NVI，钩子 private |
| 派生类要在覆盖中调用基类的默认实现 | NVI，钩子 protected |
| 算法有固定骨架和几个可变步骤 | 模板方法 |
| 虚函数需要默认实参 | 默认实参放到非虚包装上 |
| 接口只是转发，没有任何公共逻辑，且永远不会有 | public 虚函数即可，NVI 只多一层名字 |
| 热路径上调用很小的钩子，具体类型在编译期已知 | deducing this 包装或 CRTP |
| 想在构造函数里运行骨架 | 不要；用两段式构造和工厂函数 |

NVI 的运行时成本通常为零：非虚包装会被内联，剩下的虚调用与直接写 public 虚函数时一样。它的主要成本是每个操作多一个名字，以及在接口没有公共逻辑时显得多余。它的好处在接口演化时才显现：基类以后要加检查或统计，只改一处，派生类不用动。

## 思考题

!!! question "1"
    `Base` 有 public 非虚函数 `run()` 调用 private 虚函数 `step()`。`Derived` 覆盖 `step()` 时把它声明为 public，并在 `main` 里写 `Derived d; d.step();`。这能编译吗？会绕过 `run()` 里的检查吗？`Base& b = d; b.step();` 呢？

<details markdown="1">
<summary>答案</summary>

`d.step()` 能编译。访问检查按调用表达式的静态类型进行（[[class.access.virt#2]]），`d` 的静态类型是 `Derived`，找到的 `Derived::step` 是 public。它确实绕过了 `run()` 的检查，但只对持有 `Derived` 的代码有效。`b.step()` 不能编译：静态类型是 `Base`，`Base::step` 是 private，虚函数的访问权由它自己的声明决定，不受覆盖函数影响（[[class.access.virt#1]]）。所以派生类改宽访问权只影响它自己的用户，不影响通过基类接口使用它的代码。
</details>

!!! question "2"
    一个类的 public 虚函数 `virtual void log(Level lv = Level::info);` 已经被几十个派生类覆盖，有的覆盖函数写了 `Level lv = Level::debug`。怎样改成 NVI 而不改变经由基类指针调用的行为？改完之后，经由派生类对象直接调用 `log()` 的行为会变吗？

<details markdown="1">
<summary>答案</summary>

在基类里加 public 非虚函数 `void log(Level lv = Level::info) { do_log(lv); }`，把虚函数改名为 private 的 `do_log(Level)`，去掉所有默认实参，派生类的覆盖函数相应改名。经由基类指针的调用本来就使用基类声明上的默认值 `Level::info`（[[dcl.fct.default#10]]），行为不变。经由派生类对象直接调用 `log()` 时，原来用的是该派生类声明上的默认值，比如 `Level::debug`；改完后派生类不再声明 `log`，名字查找找到基类的包装，默认值统一变成 `Level::info`。这是行为变化，但它消除的正是那种同一个对象两套默认值的分裂。
</details>

!!! question "3"
    把上文 `template-method-in-ctor.cpp` 里的 `do_init` 从纯虚函数改成带空函数体的普通虚函数，程序还是 UB 吗？会输出什么？

<details markdown="1">
<summary>答案</summary>

不再是 UB。构造 `Plugin` 基类子对象期间，`do_init()` 分派到构造函数所属类 `Plugin` 中的最终覆盖函数（[[class.cdtor#4]]），现在它是一个有定义的普通虚函数，调用完全合法。程序输出 `Plugin::init begin` 和 `Plugin::init end`，`Audio::do_init` 从未执行。这比崩溃更糟：没有任何诊断，派生类的初始化静默地被跳过了。
</details>
