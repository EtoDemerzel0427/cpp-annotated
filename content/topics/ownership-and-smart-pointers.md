---
title: 所有权与智能指针设计
summary: 用类型表达谁负责销毁对象：独占、共享、借用和值语义四种所有权，unique_ptr、shared_ptr、weak_ptr 的代价与规则，函数参数怎样传递智能指针，以及 out_ptr、indirect、polymorphic 和最常见的所有权错误。
status: draft
order: 80
since: c++11
papers: P1132R8, P0718R2, P3019R14
related: unique.ptr, util.sharedptr, util.smartptr.shared, util.smartptr.weak, util.smartptr.enab, util.smartptr.ownerless, util.smartptr.atomic, smartptr.adapt, mem.composite.types, indirect, polymorphic, topics/dangling-references, topics/special-members-and-elision
tags: 智能指针, 所有权, unique_ptr, shared_ptr, weak_ptr, RAII, 专题
updated: 2026-10-19
---

!!! tldr
    - 每个动态分配的对象都应该有一个明确的所有者，负责销毁它。所有权有四种：独占（`unique_ptr`）、共享（`shared_ptr`）、借用（`T&`、`T*`、`weak_ptr`），以及值语义（直接持有 `T`）。
    - `unique_ptr` 配无状态删除器时和裸指针一样大，生成的代码也相同；它不能复制，只能移动。持有不完整类型时，外层类的析构函数、构造函数和移动赋值都要定义在类型完整的 `.cpp` 里。
    - `shared_ptr` 是两个指针加一个控制块。`make_shared` 只分配一次，但 `weak_ptr` 会推迟整块内存的释放；引用计数是线程安全的，被指向的对象和 `shared_ptr` 变量本身都不是。
    - 函数形参只在要表达所有权变化时才写智能指针：按值传 `unique_ptr` 表示接管，按值传 `shared_ptr` 表示共享；只是使用对象就传 `T&` 或 `T*`。
    - 最常见的错误是同一个裸指针交给两个 `shared_ptr`、保存临时智能指针的 `get()`、`shared_ptr` 互相引用成环；ASan 和 LSan 能抓到其中大部分。

## 谁来 delete

```cpp run title="legacy.cpp" ub
#include <cstdio>
struct Widget { int id; };

// 头文件里只有这些声明，看不出谁负责 delete
Widget* make_widget(int id);
void    register_widget(Widget* w);   // 注册表会保存 w 吗？会 delete 它吗？
Widget* find_widget(int id);          // 调用方用完要 delete 吗？

static Widget* registry[8];
Widget* make_widget(int id) { return new Widget{id}; }
void register_widget(Widget* w) { registry[w->id] = w; }
Widget* find_widget(int id) { return registry[id]; }
void shutdown() { for (Widget* w : registry) delete w; }

int main() {
  register_widget(make_widget(1));
  delete find_widget(1);   // 调用方以为自己该 delete
  shutdown();              // 注册表又 delete 一次：UB
}
```

三个函数的签名都是 `Widget*`，但含义完全不同：第一个交出一个新对象，第二个接管它，第三个只是借给调用方看一眼。签名里没有这些信息，只能靠文档和约定。约定一旦被误读，结果就是泄漏或重复释放。本机 ASan 报告 `attempting double-free`。

对象的**所有者**（owner）是负责结束它的生命周期并释放其存储的那一方。C++ 不追踪所有权，编译器不会阻止两个地方都 `delete` 同一个指针，也不会提醒没有任何地方 `delete` 它。能做的是把所有权写进类型里，让编译器检查转移和复制：

```cpp run title="typed.cpp" ok
#include <cstdio>
#include <map>
#include <memory>

struct Widget { int id; };

std::unique_ptr<Widget> make_widget(int id);       // 调用方得到所有权
void register_widget(std::unique_ptr<Widget> w);   // 注册表接管所有权
Widget* find_widget(int id);                       // 借用：可能为空，不要 delete

std::map<int, std::unique_ptr<Widget>> registry;
std::unique_ptr<Widget> make_widget(int id) { return std::make_unique<Widget>(id); }
void register_widget(std::unique_ptr<Widget> w) { int id = w->id; registry[id] = std::move(w); }
Widget* find_widget(int id) {
  auto it = registry.find(id);
  return it == registry.end() ? nullptr : it->second.get();
}

int main() {
  register_widget(make_widget(1));
  if (Widget* w = find_widget(1)) std::printf("%d\n", w->id);
}
```

现在签名本身说明了所有权：返回 `unique_ptr` 表示交出，按值接受 `unique_ptr` 表示接管，返回裸指针表示借用。注册表持有的对象在 `registry` 销毁时释放，没有任何手写的 `delete`。

## 四种所有权

| 所有权 | 含义 | 典型类型 |
|---|---|---|
| 值语义 | 对象就是持有者的一部分，复制持有者就复制对象 | `T` 成员、`std::optional<T>`、`std::vector<T>`、C++26 的 `indirect<T>`、`polymorphic<T>` |
| 独占 | 恰好一个所有者，所有权可以转移，不能复制 | `std::unique_ptr<T>` |
| 共享 | 多个所有者，最后一个离开时销毁对象 | `std::shared_ptr<T>` |
| 借用、观察 | 使用对象但不负责销毁，所有者必须活得更久 | `T&`、`T*`、`std::string_view`、`std::span`；`std::weak_ptr<T>` 能检查对象是否还在 |

选择的顺序通常是从上往下：能用值就用值；必须放到堆上（多态、不完整类型、体积大、要转移所有权）时用 `unique_ptr`；只有对象确实没有唯一的所有者、生命周期由多方共同决定时才用 `shared_ptr`。

借用的一方不拥有对象，它的安全完全取决于所有者活得比它久。这类错误统称悬垂，详见 [[topics/dangling-references]]。裸指针 `T*` 在现代代码里默认表示借用，它可以为空，可以重新指向别处；`T&` 则表示一定存在、不会改变指向的借用。

智能指针都是 RAII（Resource Acquisition Is Initialization）的应用：在构造函数里取得资源，在析构函数里释放资源，析构函数在作用域结束、异常展开时都会运行，所以释放不会被遗漏。标准把这些类型放在 [[smartptr]] 中，C++26 的值语义包装类型在 [[mem.composite.types]] 中。

## `unique_ptr`：独占所有权

`unique_ptr<T, D>` 存一个指针和一个**删除器**（[[g:deleter]]）`D`，自身销毁时调用删除器处置所指对象（[[unique.ptr.general#1]]）。默认删除器 `default_delete<T>` 执行 `delete`。析构函数等价于 `if (get()) get_deleter()(get());`，空指针不会传给删除器（[[unique.ptr.single.dtor#1]]）。

### 不能复制，只能移动

<div class="compare" markdown="1">

```cpp run title="move.cpp" ok
#include <memory>
#include <utility>
int main() {
  auto a = std::make_unique<int>(1);
  auto b = std::move(a);  // 转移
  return a == nullptr && *b == 1
             ? 0 : 1;
}
```

```cpp run title="copy.cpp" error
#include <memory>
int main() {
  auto a = std::make_unique<int>(1);
  auto b = a;  // error: 复制构造
               // 函数被删除
}
```

</div>

如果能复制，两个 `unique_ptr` 析构时就会各 `delete` 一次。标准规定每个 `unique_ptr` 特化可以移动构造、移动赋值，但不能复制构造、复制赋值（[[unique.ptr.general#4]]）。移动之后源对象变为空，所有权在任何时刻都只在一处。

有 `unique_ptr` 成员的类因此也不能隐式复制，它的隐式复制构造函数被定义为弃置的（[[class.copy.ctor]]）。这通常正是想要的；需要深复制时，见下文的 `indirect`。

### 零开销：大小与生成的代码

```cpp run title="size.cpp" impl
#include <cstdio>
#include <cstdlib>
#include <memory>

struct FreeDeleter {                     // 无状态函数对象
  void operator()(void* p) const noexcept { std::free(p); }
};
struct CountingDeleter {                 // 有状态：带一个计数器指针
  int* count;
  void operator()(int* p) const noexcept { ++*count; delete p; }
};

int main() {
  auto lam = [](int* p) { delete p; };
  std::printf("%zu\n", sizeof(int*));                                     // 8
  std::printf("%zu\n", sizeof(std::unique_ptr<int>));                     // 8
  std::printf("%zu\n", sizeof(std::unique_ptr<int, FreeDeleter>));        // 8
  std::printf("%zu\n", sizeof(std::unique_ptr<int, decltype(lam)>));      // 8
  std::printf("%zu\n", sizeof(std::unique_ptr<int, void (*)(int*)>));     // 16
  std::printf("%zu\n", sizeof(std::unique_ptr<int, CountingDeleter>));    // 16
  std::printf("%zu\n", sizeof(std::shared_ptr<int>));                     // 16
}
```

注释是本机 64 位 libc++ 的输出。空的删除器（默认删除器、空函数对象、无捕获 lambda）不占空间，实现借助空基类优化或 `[[no_unique_address]]` 把它和指针重叠存放。标准没有要求这一点，所以判定是 {{impl}}。函数指针删除器和带数据的删除器要实际存储，`unique_ptr` 就变成两倍大，而且通过函数指针调用一般不能内联。所以自定义删除器应该写成无状态的函数对象。

大小相同还不够，生成的代码也要相同。本机 Clang 23 `-O2` 下，下面两个函数编译出的 arm64 指令逐条相同：

```cpp ok
#include <memory>
void use(int*) noexcept;
void by_raw()   { int* p = new int(42); use(p); delete p; }
void by_smart() { auto p = std::make_unique<int>(42); use(p.get()); }
```

`use` 声明为 `noexcept`，所以两者都不需要异常清理路径。如果 `use` 可能抛出异常，`by_smart` 会多出一段展开时调用 `delete` 的代码，而 `by_raw` 在那种情况下直接泄漏。唯一真正的额外代价出现在按值传递 `unique_ptr` 时：在 Itanium C++ ABI 下，有非平凡析构函数的类型不能放在寄存器里传递，详见 [[unique.ptr]] 末尾的 ABI 一节。

### 自定义删除器与数组

C 库的资源用专门的函数释放，把它写成删除器就能交给 `unique_ptr`：

```cpp
struct fclose_deleter {
  void operator()(std::FILE* f) const noexcept { std::fclose(f); }
};
using file_ptr = std::unique_ptr<std::FILE, fclose_deleter>;
```

删除器是 `unique_ptr` 类型的一部分，`unique_ptr<FILE, fclose_deleter>` 和 `unique_ptr<FILE, other_deleter>` 是不相关的类型。删除器还可以定义嵌套类型 `pointer`，让 `unique_ptr` 管理文件描述符这类不是指针的句柄（[[unique.ptr.single.general#4]]）。

数组要用 `unique_ptr<T[]>`，它的默认删除器调用 `delete[]`，并提供 `operator[]`：

```cpp run title="array.cpp" ub
#include <cstdio>
#include <memory>
int main() {
  auto a = std::make_unique<int[]>(4);    // 4 个 int，值初始化为 0
  a[3] = 7;
  std::unique_ptr<int> wrong(new int[4]); // 能编译，析构时用 delete 释放 new[] 的结果
  std::printf("%d\n", a[3]);
}
```

`wrong` 析构时执行 `delete`，而对象是由数组 `new` 创建的，这是 UB（[[expr.delete#2]]）。本机 ASan 在 macOS 上默认不检查这种不匹配，加上 `ASAN_OPTIONS=alloc_dealloc_mismatch=1` 后报告 `alloc-dealloc-mismatch (operator new [] vs operator delete)`。实际代码里，动态数组几乎总是应该用 `std::vector`，它还记得自己的长度。

### 不完整类型：pimpl 规则

**pimpl**（pointer to implementation）惯用法把类的私有成员移到一个只在 `.cpp` 里定义的 `Impl` 结构中，头文件里只放一个指向它的 `unique_ptr`。修改实现细节时，包含头文件的代码不必重新编译。

[[unique.ptr.general#4]] 允许 `T` 是不完整类型，但 `default_delete<T>::operator()` 要求 `T` 完整（[unique.ptr.dltr.dflt] ¶3，见 [[unique.ptr.dltr]]）。所以关键在于 `~unique_ptr<Impl>` 在哪里被实例化：

```cpp title="widget-bad.cpp" error
#include <memory>
class Widget {
public:
  Widget() {}               // 类内定义：要能销毁已构造的 impl
  // 没有声明析构函数：隐式析构函数在第一次使用处定义
private:
  struct Impl;
  std::unique_ptr<Impl> impl;
};
void user() { Widget w; }   // error: 在这里实例化 ~unique_ptr<Impl>
```

本机 libc++ 报告对不完整类型 `Widget::Impl` 使用了 `sizeof`，实例化链指向第 4 行的构造函数。三条规则共同决定了哪些成员会实例化 `~unique_ptr<Impl>`：

1. 类内隐式声明或 `= default` 的特殊成员函数，在被 odr-use 的地方才隐式定义（[[dcl.fct.def.default#5]]）。不写析构函数，`~Widget` 就在 `user()` 里定义，那里 `Impl` 不完整。
2. 构造函数要能在异常时销毁已经构造好的成员，所以非委托构造函数会潜在调用每个成员的析构函数（[[class.base.init#14]]）。类内定义的 `Widget() {}` 因此也需要 `~unique_ptr<Impl>`。
3. 移动赋值会销毁旧的 `Impl`，类内 `= default` 的移动赋值在使用处定义，同样需要完整类型。

解决办法是在头文件里只声明这些成员，在 `Impl` 完整之后再定义它们。首次声明之后才写 `= default` 的函数，在写 `= default` 的位置定义（[[dcl.fct.def.default#5]]）：

```cpp title="widget.h"
#include <memory>
class Widget {
public:
  Widget();
  ~Widget();                              // 只声明
  Widget(Widget&&) noexcept;
  Widget& operator=(Widget&&) noexcept;
  int value() const;
private:
  struct Impl;                            // 不完整类型
  std::unique_ptr<Impl> impl;
};
```

```cpp title="widget.cpp" ok
#include "widget.h"
#include <string>
struct Widget::Impl { int v = 42; std::string name; };
Widget::Widget() : impl(std::make_unique<Impl>()) {}
Widget::~Widget() = default;              // Impl 在这里是完整的
Widget::Widget(Widget&&) noexcept = default;
Widget& Widget::operator=(Widget&&) noexcept = default;
int Widget::value() const { return impl->v; }
```

本机把这两个文件和一个移动构造、移动赋值 `Widget` 的 `main.cpp` 一起编译运行，ASan 和 UBSan 都没有报告。

!!! impl "类内 `= default` 的移动构造函数"
    按规则 2，类内 `Widget(Widget&&) = default;` 也是非委托构造函数，同样潜在调用 `impl` 的析构函数。只是首次声明时预置的函数要到被 odr 使用时才隐式定义（[[dcl.fct.def.default#5]]），所以光写这一行、从不移动 `Widget` 时不会报错；本机 Clang 23 下，`Widget b(std::move(a));` 一出现就报 `invalid application of 'sizeof' to an incomplete type`，并注明 "in defaulted move constructor for 'Widget' first required here"。稳妥的做法是把所有特殊成员都放进 `.cpp`。

`shared_ptr` 没有这个问题：它在构造时就把删除方式存进控制块，析构时不需要知道 `T`（[[util.sharedptr]]）。

### `make_unique`

`make_unique<T>(args...)` 返回 `unique_ptr<T>(new T(std::forward<Args>(args)...))`（[[unique.ptr.create#2]]）。用它的理由是代码里不出现 `new`，类型名也不必写两遍。

C++14 时它还有一个理由：`f(std::unique_ptr<T>(new T), g())` 可能先执行 `new T`，再执行抛出异常的 `g()`，`unique_ptr` 还没来得及构造，对象就泄漏了。C++17 规定各个形参的初始化彼此之间不交错（[[expr.call#8]]），这种泄漏不会再发生。

`make_unique<T[]>(n)` 把元素值初始化，`make_unique_for_overwrite` 默认初始化，适合马上就要整体覆盖的大缓冲区。完整的表格见 [[unique.ptr]]。

## `shared_ptr`：共享所有权

### 两个指针和一个控制块

一组共享所有权的 `shared_ptr` 和 `weak_ptr` 都指向同一个**控制块**（control block），里面存强计数、弱计数、删除器和分配器。每个 `shared_ptr` 本身存两个指针：`get()` 返回的存储指针，和控制块指针。强计数归零时销毁对象，弱计数也归零时释放控制块。标准没有提到控制块，这是所有实现共同的模型，详见 [[util.sharedptr]]。

上面 `size.cpp` 的最后一行显示，本机 `shared_ptr<int>` 是 16 字节。

### `make_shared`：一次分配，以及它的代价

```cpp run title="alloc.cpp" impl
#include <cstdio>
#include <cstdlib>
#include <memory>
#include <new>

static int allocs = 0, frees = 0;
void* operator new(std::size_t n) {
  ++allocs;
  if (void* p = std::malloc(n)) return p;
  throw std::bad_alloc();
}
void operator delete(void* p) noexcept { ++frees; std::free(p); }
void operator delete(void* p, std::size_t) noexcept { ++frees; std::free(p); }

struct Big {
  char data[1024];
  ~Big() { std::puts("  ~Big"); }
};

int main() {
  {
    std::shared_ptr<Big> a(new Big);            // new Big + 控制块
    std::printf("shared_ptr(new): allocs=%d\n", allocs);
  }
  allocs = frees = 0;
  std::weak_ptr<Big> w;
  {
    auto b = std::make_shared<Big>();           // 对象与控制块一起分配
    std::printf("make_shared:     allocs=%d\n", allocs);
    w = b;
  }                                             // 强计数归零：~Big 运行
  std::printf("after last shared_ptr: frees=%d\n", frees);
  w.reset();                                    // 弱计数归零：整块释放
  std::printf("after weak_ptr reset:  frees=%d\n", frees);
}
```

本机输出：

```text
shared_ptr(new): allocs=2
  ~Big
make_shared:     allocs=1
  ~Big
after last shared_ptr: frees=0
after weak_ptr reset:  frees=1
```

`shared_ptr<Big>(new Big)` 分配两次，一次给对象，一次给控制块。`make_shared` 把对象放进控制块里，只分配一次；标准建议实现最多分配一次（[[util.smartptr.shared.create#7.1]]），这是建议而不是要求，所以判定是 {{impl}}。

代价在后半段。最后一个 `shared_ptr` 离开时 `~Big` 立即运行，但对象和控制块在同一块内存里，只要还有 `weak_ptr`，那 1 KB 就不能归还。大对象配上长期存在的 `weak_ptr`（比如缓存），会占住可观的内存。这时改用 `shared_ptr<T>(new T)`，对象的内存在强计数归零时就能释放。

### 删除器的类型擦除

```cpp run title="erase.cpp" ok
#include <cstdio>
#include <cstdlib>
#include <memory>
#include <type_traits>
#include <vector>

struct FreeDeleter { void operator()(void* p) const noexcept { std::free(p); } };
struct LogDeleter {
  const char* tag;
  void operator()(int* p) const { std::printf("delete %s\n", tag); delete p; }
};

int main() {
  // unique_ptr：删除器是类型的一部分
  static_assert(!std::is_same_v<std::unique_ptr<int, FreeDeleter>,
                                std::unique_ptr<int, LogDeleter>>);
  // shared_ptr：删除器存进控制块，类型和大小都不变
  std::vector<std::shared_ptr<int>> v;
  v.emplace_back(new int(1));
  v.emplace_back(static_cast<int*>(std::malloc(sizeof(int))), FreeDeleter{});
  v.emplace_back(new int(3), LogDeleter{"third"});
  std::printf("%zu %d\n", sizeof(v[2]),
              std::get_deleter<LogDeleter>(v[2]) != nullptr);  // 16 1
}
```

`shared_ptr<T>` 的删除器不在类型里。构造函数 `shared_ptr(Y* p, D d)` 把 `d` 连同实际类型 `Y` 一起存进控制块（[[util.smartptr.shared.const#11]]），析构时通过控制块的虚函数调用它。这就是**类型擦除**（[[g:type-erasure]]）：一个 `vector<shared_ptr<int>>` 可以装着用三种方式释放的对象。

同样的机制让 `shared_ptr<Base>(new Derived)` 在 `Base` 没有虚析构函数时也能正确销毁 `Derived`，`shared_ptr<void>` 也能销毁任何对象。代价是控制块里多一个虚表指针，每次销毁多一次间接调用。

### 别名构造

```cpp
auto p = std::make_shared<Person>("Ada", 36);
std::shared_ptr<int> age(p, &p->age);   // 拥有整个 Person，指向它的成员
```

别名构造让存储指针和被拥有的对象分离：`age` 让整个 `Person` 活着，解引用得到的却是 `int`（[[util.smartptr.shared.const#14]]）。它适合把子对象交给只认识子对象类型的代码，同时保证外层对象不会先被销毁。`static_pointer_cast` 等四个转换函数也是用它实现的。细节和陷阱见 [[util.smartptr.shared]]。

### 线程安全：计数、对象、变量

`shared_ptr` 的线程安全保证只有一句（[[util.smartptr.shared.general#5]]）：判断数据竞争时，成员函数只算访问了 `shared_ptr`、`weak_ptr` 对象本身，不算访问它们指向的对象；`use_count()` 的变化不算可能引起数据竞争的修改。由此得到三个层次：

| 访问什么 | 多个线程同时这样做 | 结论 |
|---|---|---|
| 引用计数：各自复制、销毁不同的 `shared_ptr` 对象 | 计数被并发修改 | 安全，实现必须用原子操作 |
| 被指向的对象：通过各自的副本写 `*p` | 同一个对象被并发写 | 数据竞争，与 `shared_ptr` 无关 |
| 同一个 `shared_ptr` 变量：一个线程赋值，另一个线程读 | 同一个对象被并发读写 | 数据竞争，要用 `atomic<shared_ptr<T>>` |

```cpp run title="race-object.cpp" ub
#include <memory>
#include <thread>

int main() {
  auto p = std::make_shared<int>(0);
  std::jthread t([p] { ++*p; });   // 线程持有自己的副本：计数没有问题
  ++*p;                            // 两个线程写同一个 int：数据竞争
}
```

本机 `-fsanitize=thread` 报告 `data race`，位置在 lambda 里的 `++*p`。把 `p` 按值捕获只保证了 `int` 在两个线程用完之前不会被释放，并没有让对 `int` 的访问变得同步。要么让对象不可变（`shared_ptr<const T>`），要么由对象自己加锁。

第三行的情形见 [[util.sharedptr]] 中的例子：读线程复制 `p` 的同时写线程给 `p` 赋值，可能读到新的存储指针配旧的控制块。C++20 的 `std::atomic<std::shared_ptr<T>>`（[[P0718R2]]）让一个 `shared_ptr` 变量可以被并发读写：读到指针和增加计数在同一个原子操作之内，而旧对象的减计数、析构和释放发生在原子操作之后（[[util.smartptr.atomic.general#2]]）。截至写作时本机 libc++ 还没有实现这个偏特化，`std::atomic<std::shared_ptr<int>>` 会落到主模板，被它要求 `T` 可平凡复制的 `static_assert` 拒绝。

## `weak_ptr`：不拥有的观察者

### 环

```cpp run title="cycle.cpp"
#include <memory>
#include <string>
#include <vector>

struct Child;
struct Parent {
  std::vector<std::shared_ptr<Child>> children;
};
struct Child {
  std::shared_ptr<Parent> parent;   // 回指拥有者：形成环
  std::string name;
};

void build() {
  auto p = std::make_shared<Parent>();
  auto c = std::make_shared<Child>();
  c->parent = p;
  p->children.push_back(c);
}   // p、c 销毁后两个强计数都还是 1，谁也不会被析构

int main() { build(); }
```

`shared_ptr` 只是计数，没有环检测。`build()` 返回时，`Parent` 被 `Child::parent` 拥有，`Child` 被 `Parent::children` 拥有，两个计数都停在 1，两个对象都不会被销毁。泄漏本身不是 UB，这个程序是良构的，行为也是确定的，只是这些内存永远不会被释放，析构函数里的清理工作也永远不会执行。

本机用 `-fsanitize=address -O1` 编译、`ASAN_OPTIONS=detect_leaks=1` 运行，LeakSanitizer 报告：

```text
==ERROR: LeakSanitizer: detected memory leaks
Indirect leak of 64 byte(s) in 1 object(s) allocated from:
    ... in main cycle.cpp
Indirect leak of 48 byte(s) in 1 object(s) allocated from:
Indirect leak of 16 byte(s) in 1 object(s) allocated from:
SUMMARY: AddressSanitizer: 128 byte(s) leaked in 3 allocation(s).
```

三块都是间接泄漏（indirect leak）：每块都能从另一块泄漏的内存到达，没有一块是从程序的根直接丢失的，这正是环的特征。LSan 用保守扫描判断可达性，栈上残留的旧指针值会让它误以为对象仍可达；本机 `-O0` 构建运行时它有时不报告这个环。macOS 上的 ASan 默认不开启泄漏检测，要显式设置 `detect_leaks=1`。

修复的方法是确定所有权的方向：父节点拥有子节点，子节点回指父节点时用 `weak_ptr<Parent>`。`weak_ptr` 增加的是弱计数，它让控制块活着，不让对象活着。

### `lock()` 与竞态

`weak_ptr` 没有 `operator*`、`operator->` 和 `get()`。访问对象的唯一方式是 `lock()`，它原子地完成检查对象是否存活和取得 `shared_ptr` 两步（[[util.smartptr.weak.obs#3]]）：

```cpp run title="observer.cpp" ok
#include <cstdio>
#include <memory>
#include <set>

struct Listener {
  int id;
  void on_event() const { std::printf("listener %d\n", id); }
};

class Subject {
  // 不拥有监听者；按所有权排序，过期后键的顺序也不变
  std::set<std::weak_ptr<Listener>, std::owner_less<>> listeners_;
public:
  void subscribe(const std::shared_ptr<Listener>& l) { listeners_.insert(l); }
  void notify() {
    for (auto it = listeners_.begin(); it != listeners_.end();) {
      if (auto l = it->lock()) { l->on_event(); ++it; }   // 原子地检查并取得所有权
      else it = listeners_.erase(it);                     // 已销毁：顺手清理
    }
  }
  std::size_t size() const { return listeners_.size(); }
};

int main() {
  Subject s;
  auto a = std::make_shared<Listener>(1);
  {
    auto b = std::make_shared<Listener>(2);
    s.subscribe(a);
    s.subscribe(b);
    s.notify();                       // listener 1、listener 2，顺序未指定
  }                                   // b 销毁，Subject 不知道
  s.notify();                         // 只有 listener 1
  std::printf("%zu\n", s.size());     // 1
}
```

本机输出 `listener 1`、`listener 2`、`listener 1`、`1`。`if (auto l = it->lock())` 把检查和使用合成一步：拿到的 `l` 在整个 `if` 块内保证对象存活，即使另一个线程正在销毁最后一个所有者。

先 `expired()` 再 `lock()` 是错误的写法。`expired()` 返回 `false` 之后、`lock()` 之前，另一个线程可能销毁了对象，`lock()` 返回空指针，后面的解引用就是 UB。`expired()` 只有返回 `true` 是可靠的，因为对象销毁之后不会复活。

### `owner_less`：按所有权比较

上例的 `std::set` 用 `std::owner_less<>` 而不是默认的 `std::less`。`weak_ptr` 根本没有 `<`：它的存储指针可能已经悬空，按地址比较没有意义。`owner_less` 调用 `owner_before`，比较的是两者属于哪个所有权组，实际上就是控制块的地址（[[util.smartptr.ownerless#2]]）。对象销毁后控制块还在，键的顺序不会改变，`set` 的不变式也就不会被破坏。

`shared_ptr` 也有这两种比较：`==` 比较存储指针，`owner_before` 和 `owner_equal` 比较所有权。别名构造出的 `shared_ptr` 与原对象所有权相同，存储指针不同。C++26 还增加了 `owner_hash` 和 `owner_equal` 函数对象，让 `weak_ptr` 可以做无序容器的键，见 [[util.smartptr.ownerless]]。

## `enable_shared_from_this`

对象有时需要从自己的成员函数里拿到一个指向自己的 `shared_ptr`，比如把自己交给一个异步回调，保证回调执行时自己还活着。直接写 `std::shared_ptr<Session>(this)` 会新建第二个控制块，与外面已有的那一组各自删除一次对象。

```cpp run title="session.cpp" ok
#include <cstdio>
#include <functional>
#include <memory>

struct Session : std::enable_shared_from_this<Session> {
  // 回调持有 Session 的共享所有权：回调执行时对象一定活着
  std::function<void()> keep_alive_callback() {
    return [self = shared_from_this()] { self->done(); };
  }
  // 回调只观察：对象已销毁就什么也不做
  std::function<void()> weak_callback() {
    return [w = weak_from_this()] {
      if (auto self = w.lock()) self->done();
      else std::puts("session gone");
    };
  }
  void done() { std::puts("done"); }
};

int main() {
  std::function<void()> cb1, cb2;
  {
    auto s = std::make_shared<Session>();
    cb1 = s->keep_alive_callback();
    cb2 = s->weak_callback();
  }
  cb1();          // done：cb1 里的 self 让 Session 活着
  cb1 = nullptr;  // 最后一个所有者消失
  cb2();          // session gone

  Session local;  // 不被任何 shared_ptr 拥有
  try { local.keep_alive_callback(); }
  catch (const std::bad_weak_ptr&) { std::puts("bad_weak_ptr"); }
}
```

本机输出 `done`、`session gone`、`bad_weak_ptr`。`enable_shared_from_this<T>` 在基类里藏了一个 `weak_ptr`（说明用名 *weak-this*），`shared_from_this()` 返回 `shared_ptr<T>(weak-this)`（[[util.smartptr.enab#7]]）。填写 *weak-this* 的不是它自己，而是创建第一个所有权组的 `shared_ptr` 构造函数或 `make_shared`（[[util.smartptr.shared.const#1]]）。由此得到它的几个陷阱：

- **构造函数里不能用。** 对象还在构造，`make_shared` 还没走到填写 *weak-this* 那一步，`shared_from_this()` 抛出 `bad_weak_ptr`。析构函数里也一样，那时强计数已经归零。需要在创建时把自己注册到别处，就用私有构造函数加静态工厂函数，在 `make_shared` 之后再注册。
- **对象必须已经被 `shared_ptr` 拥有。** 栈上的对象、`unique_ptr` 拥有的对象调用 `shared_from_this()` 都抛出 `bad_weak_ptr`。C++17 起是抛异常，之前是 UB。
- **基类必须可访问。** `class Session : std::enable_shared_from_this<Session>` 是私有继承，`shared_ptr` 的构造函数看不到这个基类，就不填写 *weak-this*，也没有任何诊断，`shared_from_this()` 永远抛异常。
- **它不能阻止错误的写法。** 继承了它之后，`shared_ptr<Session>(this)` 仍然会新建第二个控制块。

两种回调代表两种设计。`keep_alive_callback` 延长对象的寿命，适合回调执行之前对象必须存活的场合；`weak_callback` 不延长寿命，对象被销毁后回调自动失效，适合定时器、事件订阅这类不应该反过来让对象活着的场合。更多细节见 [[util.smartptr.enab]]。

## 函数参数怎样传智能指针

形参类型说明函数对所有权做什么。下表按 C++ Core Guidelines 的 F.7 和 R.30–R.37 整理：

| 形参 | 表达的意思 | 调用处 |
|---|---|---|
| `T&`、`const T&`、`T*` | 只使用对象，不涉及所有权；`T*` 可以为空 | `f(*p)`、`f(p.get())` |
| `unique_ptr<T>`（按值） | 函数接管所有权 | `f(std::move(p))` |
| `unique_ptr<T>&` | 函数可能重置或替换调用方的指针 | `f(p)` |
| `shared_ptr<T>`（按值） | 函数要保存一份所有权，比如存进成员 | `f(p)` 或 `f(std::move(p))` |
| `shared_ptr<T>&` | 函数可能重置或替换调用方的指针 | `f(p)` |
| `const shared_ptr<T>&` | 函数可能决定保存一份所有权，也可能不保存 | `f(p)` |

最常见的错误是只想使用对象，却把形参写成 `const shared_ptr<T>&` 或 `shared_ptr<T>`。前者把函数绑死在 `shared_ptr` 上，栈对象、`unique_ptr` 拥有的对象都传不进来；后者每次调用都做一次原子的加减计数。只使用对象就传 `T&`。

### 接管所有权：按值，不要按右值引用

```cpp run title="sink.cpp" ok
#include <cstdio>
#include <memory>
#include <utility>
#include <vector>

std::vector<std::unique_ptr<int>> store;
void sink_val(std::unique_ptr<int> p) { store.push_back(std::move(p)); }
void sink_ref(std::unique_ptr<int>&& p) {          // 可能接管，也可能不
  if (*p > 10) store.push_back(std::move(p));
}

int main() {
  auto a = std::make_unique<int>(1);
  auto b = std::make_unique<int>(1);
  sink_val(std::move(a));
  sink_ref(std::move(b));
  std::printf("%d %d\n", a == nullptr, b == nullptr);   // 1 0
}
```

按值传递时，形参 `p` 在调用处就从实参移动构造，调用一结束 `a` 必然为空，所有权的转移一目了然。按右值引用传递时，`std::move(b)` 只是一个转换，函数体决定是否真的移走，调用方不能确定 `b` 之后的状态。

### 借用的引用不能来自可能被改写的智能指针

```cpp run title="pin.cpp" ub
#include <cstdio>
#include <memory>
#include <string>

struct Config { std::string name = std::string(64, 'c'); };
std::shared_ptr<Config> g_config = std::make_shared<Config>();

void reload() { g_config = std::make_shared<Config>(); }   // 旧 Config 被销毁

void print(const Config& c) {
  reload();                            // 间接地释放了 c 所指的对象
  std::printf("%zu\n", c.name.size()); // UB
}

int main() {
  print(*g_config);
}
```

`print` 接受 `const Config&` 是正确的设计，问题在调用处：引用来自全局的 `g_config`，而 `print` 在使用 `c` 之前间接地给 `g_config` 赋了值，旧对象的最后一个所有者消失了。本机 ASan 报告 `heap-use-after-free`，位置在 `print`。这就是 Core Guidelines R.37 说的不要从一个可能被别名修改的智能指针取得借用。修正方法是在调用处先复制一份，让局部变量钉住对象：`auto pin = g_config; print(*pin);`，本机验证这样输出 `64`。

## `out_ptr` 与 `inout_ptr`：交给 C 接口

C 接口常通过 `T**` 形参交出新分配的资源。C++23 的 `std::out_ptr`（[[P1132R8]]）把智能指针适配成这种形参：

```cpp run title="out-ptr.cpp" ok
#include <cstdio>
#include <memory>

// 一个典型的 C 接口：通过 T** 交出新资源，另有专门的释放函数
extern "C" {
struct db { int handle; };
int  db_open(const char* name, db** out) {
  if (!name) return -1;            // 失败时不写 *out
  *out = new db{42};
  return 0;
}
void db_close(db* d) { delete d; }
}

struct db_closer {
  void operator()(db* d) const noexcept { db_close(d); }
};
using db_ptr = std::unique_ptr<db, db_closer>;

int main() {
  db_ptr conn;
  if (db_open("test", std::out_ptr(conn)) != 0) return 1;
  std::printf("%d\n", conn->handle);   // 42；离开作用域时调用 db_close
}
```

`std::out_ptr(conn)` 构造一个临时对象，它先清空 `conn`，再把自己内部一个裸指针的地址交给 C 函数；临时对象在完整表达式结束时析构，把 C 函数写入的指针 `reset` 进 `conn`。中间没有一个需要手动管理的裸指针变量，C 函数失败、没有写入时 `conn` 保持为空。

两点需要注意。结果在完整表达式结束时才写回，所以同一个表达式里读 `conn` 看到的还是空指针。C 函数需要读取并自行释放旧值时，改用 `std::inout_ptr`，它在最后对旧值调用 `release()` 而不是删除它。`shared_ptr` 配 `out_ptr` 必须显式给出删除器，否则非良构，因为 C 资源几乎从不该用 `delete` 释放；`shared_ptr` 配 `inout_ptr` 一律非良构，因为 `shared_ptr` 无法交出独占所有权（[[out.ptr.t#3]]、[[inout.ptr.t#3]]）。逐条规则见 [[smartptr.adapt]]。

## 值语义的替代：`indirect` 与 `polymorphic` {{c++26}}

把成员放到堆上，常见的理由有三个：成员类型在这里还不完整（pimpl、递归数据结构）；成员很大，想让外层对象小一些、移动快一些；成员的动态类型到运行时才确定。用 `unique_ptr` 做这种成员，外层类就失去了值语义：

```cpp
struct Shape { virtual ~Shape() = default; virtual double area() const = 0; };

struct Scene {
  std::unique_ptr<Body> body;                 // pimpl 或大对象
  std::vector<std::unique_ptr<Shape>> shapes; // 多态成员
  void touch() const { body->dirty = true; }  // const 函数也能改 *body
};
// Scene 不能复制：要手写复制构造、复制赋值，Shape 还要提供虚 clone()
// body 可以为空：每次访问都要考虑
```

C++26 的 `std::indirect<T>` 和 `std::polymorphic<T>`（[[P3019R14]]）把堆上的对象当作值来对待：

```cpp
#include <memory>
#include <vector>

struct Scene {
  std::indirect<Body> body;                    // 复制 Scene 就复制 Body
  std::vector<std::polymorphic<Shape>> shapes; // 按动态类型复制，不需要 clone()
  // void touch() const { body->dirty = true; }  // error: 这里 *body 是 const Body&
};

void demo() {
  Scene a;                                     // body 默认构造了一个 Body，不为空
  a.shapes.emplace_back(std::in_place_type<Circle>, 1.0);
  Scene b = a;                                 // 隐式复制即为深复制
}
```

截至写作时本机 libc++ 还没有实现这两个类，上面两段代码没有经过编译，所以不加判定。下面的结论来自草案：

- **复制就是复制值。** `indirect` 的复制构造函数用 `*other` 构造一个新的 `T`（[[indirect.ctor#9]]）；`polymorphic` 用被拥有对象的实际类型 `U` 的复制构造函数（[[polymorphic.ctor#8]]），不会切片。为了保证复制一定可行，`polymorphic` 在构造时就要求 `U` 可复制（[[polymorphic.ctor#12]]）。
- **`const` 会传播。** `const indirect<T>` 的 `operator*` 返回 `const T&`，`operator->` 返回 `const_pointer`（[[indirect.obs]]）。
- **没有空状态。** 默认构造也会分配并构造一个 `T`（[[indirect.ctor#5]]）。只有被移动之后才可能**无值**（[[g:valueless]]，[[indirect.general#1]]），可以用 `valueless_after_move()` 查询。`polymorphic` 的移动构造甚至允许不接管指针而是移动构造一个新对象，以便实现小对象优化，所以被移动后不一定无值（[[polymorphic.ctor#10]]）。
- **`T` 可以不完整。** 和 `unique_ptr` 一样，析构函数要求 `T` 完整，pimpl 的规则照旧。
- **`polymorphic` 按实际类型销毁**（[[polymorphic.dtor#2]]），基类不需要虚析构函数。

| 成员类型 | 存储位置 | 可能为空 | 复制外层类 | `const` 传播 |
|---|---|---|---|---|
| `T` | 对象内 | 否 | 复制 `T` | 是 |
| `unique_ptr<T>` | 堆 | 是 | 不能隐式复制 | 否 |
| `shared_ptr<T>` | 堆 | 是 | 两个外层对象共享同一个 `T` | 否 |
| `indirect<T>` | 堆 | 仅在被移动后 | 复制 `T` | 是 |
| `polymorphic<T>` | 堆，或实现内部的小缓冲区 | 仅在被移动后 | 按动态类型复制 | 是 |

用 `shared_ptr` 做成员来换取可复制性，是常见但错误的做法：复制出来的两个外层对象共享同一个内部对象，修改一个会影响另一个，这不是值语义。两者的完整规则见 [[indirect]] 和 [[polymorphic]]，设计动机见 [[mem.composite.types]]。

## 常见错误

| 错误 | 后果 | 能否发现 |
|---|---|---|
| 同一个裸指针交给两个 `shared_ptr` | 两个控制块，各删除一次：UB | ASan：`attempting double-free` |
| 在成员函数里写 `shared_ptr<T>(this)` | 同上 | 同上；改用 `shared_from_this()` |
| 保存临时智能指针的 `get()` | 悬垂指针：UB | Clang `-Wdangling-gsl`；ASan：`heap-use-after-free` |
| `shared_ptr` 互相引用 | 环，永不释放 | LSan：`Indirect leak` |
| `unique_ptr<Base>` 指向派生类，`Base` 析构函数不是虚的 | UB（[[expr.delete#3]]） | 编译器不报错，见 [[unique.ptr]] |
| `release()` 的返回值没有接住 | 泄漏 | LSan |
| 构造函数里调用 `shared_from_this()` | 抛出 `bad_weak_ptr` | 运行期异常 |

前两条的例子：

```cpp run title="two-owners.cpp" ub
#include <memory>
struct Node { int v = 0; };
int main() {
  Node* raw = new Node;
  std::shared_ptr<Node> a(raw);
  std::shared_ptr<Node> b(raw);   // 第二个控制块
}                                 // b、a 各 delete 一次
```

每次从裸指针构造 `shared_ptr` 都会新建一个所有权组。构造 `b` 时违反了前置条件：`delete raw` 必须有良定义的行为（[[util.smartptr.shared.const#5]]），而 `raw` 已经属于另一组。避免的办法是让裸指针根本不出现：用 `make_shared`，需要转换类型时用 `static_pointer_cast`，不要写 `shared_ptr<D>(static_cast<D*>(b.get()))`。

保存 `get()` 的例子：

```cpp run title="get.cpp" ub
#include <cstdio>
#include <memory>
#include <string>

std::unique_ptr<std::string> load() {
  return std::make_unique<std::string>("a string long enough to be on the heap");
}

int main() {
  std::string* s = load().get();   // 临时 unique_ptr 在这一行末尾销毁
  std::printf("%zu\n", s->size()); // UB：对象已被 delete
}
```

本机 Clang 23 给出 `-Wdangling-gsl` 警告，说指针背后的对象会在完整表达式结束时销毁，ASan 报告 `heap-use-after-free`。`get()` 返回的是借用，它的有效期不超过发出它的那个所有者。这一类问题的全貌见 [[topics/dangling-references]]。

## 思考题

!!! question "1"
    一个类有 `std::unique_ptr<Impl> impl;` 成员，头文件里声明了 `~Widget();`，`.cpp` 里定义了 `Widget::~Widget() = default;`，但头文件里还有一个类内定义的 `Widget(int x) : impl(nullptr) { (void)x; }`。包含这个头文件、创建 `Widget(1)` 的代码能编译吗？

<details markdown="1">
<summary>答案</summary>

不能。`Widget(int)` 是非委托构造函数，按 [[class.base.init#14]] 它潜在调用每个成员的析构函数，以便在后续成员初始化抛出异常时销毁已经构造好的成员。这需要实例化 `~unique_ptr<Impl>`，进而实例化 `default_delete<Impl>::operator()`，后者要求 `Impl` 完整（[unique.ptr.dltr.dflt] ¶3，见 [[unique.ptr.dltr]]）。即使 `impl` 被初始化为空指针也一样，判断发生在编译期。这个构造函数也要移到 `.cpp` 里。
</details>

!!! question "2"
    `auto sp = std::make_shared<std::vector<char>>(100'000'000);` 之后，程序把 `std::weak_ptr w = sp;` 存进一个长期存在的缓存，然后 `sp.reset()`。这 100 MB 什么时候还给系统？如果改用 `std::shared_ptr<std::vector<char>>(new std::vector<char>(100'000'000))` 呢？

<details markdown="1">
<summary>答案</summary>

两种写法里，`sp.reset()` 时强计数归零，`vector` 的析构函数都会立即运行，它的 100 MB 缓冲区是 `vector` 自己另外分配的，此时就被释放。控制块推迟释放的只是 `vector` 对象本身那几十个字节。`make_shared` 的推迟释放问题只在 `T` 本身很大时才显著，比如 `make_shared<std::array<char, 100'000'000>>()`：那 100 MB 就在控制块里，要等缓存里的 `weak_ptr` 也销毁才能归还。
</details>

!!! question "3"
    一个函数的签名是 `void attach(std::shared_ptr<Logger> log);`，它的实现只是 `log->write("attached");`，没有保存 `log`。这个签名有什么问题？应该改成什么？

<details markdown="1">
<summary>答案</summary>

按值接受 `shared_ptr` 表示函数要保存一份所有权，但这里只是使用对象。代价有两个：每次调用都有一对原子的加减计数；调用方必须持有 `shared_ptr`，栈上的 `Logger` 或 `unique_ptr` 拥有的 `Logger` 传不进来。应该改成 `void attach(Logger& log);`，调用处写 `attach(*p)`。如果 `Logger` 可能不存在，用 `Logger*`。
</details>
