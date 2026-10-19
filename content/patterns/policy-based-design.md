---
title: 基于策略的设计
summary: 把类模板的行为拆成几个正交的维度，每个维度由一个模板实参（策略）提供：策略怎样进入宿主类，怎样做到零开销，标准库里的策略，怎样用 concepts 约束策略，以及组合爆炸、类型不兼容和编译期代价。
status: draft
order: 45
since: c++98
papers: P0840R2, P0522R0, P0732R2
related: intro.object, dcl.attr.nouniqueaddr, temp.inst, temp.arg.template, unique.ptr, char.traits, allocator.requirements, mdspan.accessor, execpol, topics/concepts, topics/allocators-and-pmr, topics/ownership-and-smart-pointers, toolchain/object-layout-and-vtables, patterns/strategy, patterns/crtp, patterns/mixin, patterns/type-erasure, patterns/tag-dispatch
tags: 惯用法, 设计模式, 模板, 策略, 空基类优化, no_unique_address, concepts
updated: 2026-10-19
---

!!! tldr
    - 基于策略的设计把一个类模板的行为拆成几个互不相关的维度（检查、释放、加锁……），每个维度由一个模板实参提供，用户通过选择实参组装出需要的类。
    - 策略可以以静态成员函数、基类、`[[no_unique_address]]` 成员或类型别名的形式进入宿主；空策略不占空间，`-O2` 下调用被完全内联，生成的代码和手写的一样。
    - 标准库到处是策略：`Allocator`、`char_traits`、`Compare`、`Hash`、`unique_ptr` 的删除器、`mdspan` 的布局与访问器。执行策略（`std::execution::par`）是另一回事，它是选择重载的标签。
    - 策略不同的特化是互不相关的类型：`Ptr<T, A>` 不能直接赋给 `Ptr<T, B>`，要靠转换构造函数；每种组合也各自实例化一份代码。
    - 策略的要求应该写成 concept，而不是只写在文档里：错误会在写出 `Ptr<int, BadCheck>` 的那一行报告，而不是在宿主内部的某个成员函数里。

## 一个指针，几种行为

设想要写一个独占所有权的智能指针。不同的使用场景对它有不同的要求：

- 解引用时是否检查空指针：发布版不检查，调试版或面向外部输入的代码抛出异常；
- 怎样释放对象：`delete`、`delete[]`、`free`，或者某个 C 库的 `xxx_destroy`；
- 引用计数版本还要考虑计数器是否要原子操作。

如果每种组合写一个类，两种检查方式乘以三种释放方式就是六个类，再加一个维度就翻倍。这些类的大部分代码相同，差别只在几行。用虚函数在运行期选择行为也行，但每个指针要多带一个虚表指针，每次解引用多一次间接调用，这对智能指针来说不可接受。

**基于策略的设计**（policy-based design）的做法是：把每个维度写成一个小类，称为**策略**（policy）；把智能指针写成类模板，称为**宿主**（host），每个维度对应一个模板形参。宿主只规定它要怎样使用策略，比如调用 `Checking::check(p)`，具体行为由用户选择的实参决定。

```cpp run title="ptr.cpp" ok
#include <cstdio>
#include <stdexcept>
#include <utility>

// 检查策略：只提供静态成员函数
struct NoCheck {
  static void check(const void*) noexcept {}
};
struct ThrowOnNull {
  static void check(const void* p) {
    if (!p) throw std::logic_error("null dereference");
  }
};

// 删除策略：无状态函数对象
struct DeleteOne {
  template<class T> void operator()(T* p) const noexcept { delete p; }
};
struct DeleteArray {
  template<class T> void operator()(T* p) const noexcept { delete[] p; }
};

template<class T, class Checking = NoCheck, class Deleter = DeleteOne>
class Ptr : private Deleter {            // 私有继承：空基类不占空间
  T* p_ = nullptr;
  Deleter& deleter() noexcept { return *this; }
public:
  Ptr() = default;
  explicit Ptr(T* p, Deleter d = Deleter()) noexcept
      : Deleter(std::move(d)), p_(p) {}
  Ptr(Ptr&& o) noexcept
      : Deleter(std::move(o.deleter())), p_(std::exchange(o.p_, nullptr)) {}
  Ptr& operator=(Ptr&& o) noexcept {
    Ptr tmp(std::move(o));
    std::swap(p_, tmp.p_);
    std::swap(deleter(), tmp.deleter());
    return *this;
  }
  ~Ptr() { if (p_) deleter()(p_); }

  T& operator*() const  { Checking::check(p_); return *p_; }
  T* operator->() const { Checking::check(p_); return p_; }
  T* get() const noexcept { return p_; }
};

struct Widget { int id; };

int main() {
  Ptr<Widget> a(new Widget{1});                      // 默认策略
  Ptr<Widget, ThrowOnNull> b;                        // 空指针，解引用时抛异常
  Ptr<int, NoCheck, DeleteArray> c(new int[4]{});    // 用 delete[] 释放
  std::printf("%d %d\n", a->id, c.get()[3]);
  try { (void)b->id; } catch (const std::logic_error& e) { std::puts(e.what()); }
}
```

本机输出 `1 0` 和 `null dereference`，ASan 和 UBSan 没有报告。六种组合只写了一个宿主和四个小策略类，再加一种检查方式只需要再写一个策略类。

这个设计成立的前提是维度之间**正交**：检查方式不关心对象怎样释放，释放方式也不关心是否检查。如果两个策略必须互相配合（比如某种所有权策略只能和某种检查策略一起用），组合的数量就不再是自由的乘积，宿主也要处理不合法的组合。

## 策略的要求是一组表达式

`Ptr` 对 `Checking` 的全部要求是：`Checking::check(p)` 对 `const void*` 类型的 `p` 是合法的表达式。它不要求 `Checking` 继承某个基类，也不关心 `check` 是否 `noexcept`、返回什么。这种只由表达式描述的要求和标准库的具名要求（如 *Cpp17Hash*）是同一种东西。

这种要求在模板实例化时才检查。类模板特化被隐式实例化时，成员函数只实例化声明，不实例化定义（[[temp.inst#3]]）；成员函数的定义只在被使用时才实例化（[[temp.inst#4]]）。所以 `Ptr<Widget, ThrowOnNull>` 从不解引用的话，`ThrowOnNull::check` 根本不会被调用。这个性质既有用（下文的注入接口依赖它），也让错误出现得很晚（见下文用 concepts 约束策略）。

## 策略进入宿主的几种方式

### 静态成员函数

`Checking::check(p_)` 是最简单的形式：策略没有对象，宿主通过 `::` 调用它的静态成员函数。不占空间，没有状态，也不能有状态。

如果以后想支持有状态的检查策略（比如统计解引用次数），可以改成存一个策略对象、写 `checking_.check(p_)`。静态成员函数也可以用成员访问语法调用（[[class.static.general#1]]），所以原来的无状态策略不用改。

### 作为基类：空基类优化

删除器可能有状态（比如带一个指向内存池的指针），所以宿主要存一个删除器对象。如果直接写成数据成员 `Deleter d_;`，即使 `Deleter` 是空类，它也至少占一个字节（[[intro.object#8]]），再按指针对齐补到 8 个字节。

`Ptr` 改用私有继承 `Deleter`。基类子对象属于**潜在重叠子对象**（[[g:potentially-overlapping-subobject]]），它可以大小为零、和其他子对象共用地址（[[intro.object#7]]、[[intro.object#10]]）。这就是**空基类优化**（empty base optimization，EBO）。用私有继承而不是公有继承，是为了不让 `Ptr` 可以隐式转换成 `Deleter&`。

!!! std
    Otherwise, if the object is a base class subobject of a standard-layout class type with no non-static data members, it has zero size.

    标准只在这一种情况下要求空基类大小为零（[[intro.object#8]]），其余情况大小为零的条件由实现定义。主流 ABI 对空基类都做了这个优化，所以下面的大小是 {{impl}}。

### 作为基类：向宿主注入接口

公有继承策略时，策略的公有成员就成了宿主接口的一部分。下面的 `Handle` 在使用 `CountDerefs` 策略时多出一个 `deref_count()`，使用默认策略时没有这个成员：

```cpp run title="inject.cpp" ok
#include <cstddef>
#include <cstdio>

struct NoStats {
  void on_deref() const noexcept {}
protected:
  ~NoStats() = default;            // 不能通过 NoStats* 销毁宿主
};
struct CountDerefs {
  void on_deref() const noexcept { ++derefs_; }
  std::size_t deref_count() const noexcept { return derefs_; }
protected:
  ~CountDerefs() = default;
private:
  mutable std::size_t derefs_ = 0;
};

template<class T, class Stats = NoStats>
class Handle : public Stats {      // 公有继承：策略的公有成员成为宿主接口
  T* p_;
public:
  explicit Handle(T* p) noexcept : p_(p) {}
  T& operator*() const noexcept {
    this->on_deref();              // 依赖基类的成员要写 this->
    return *p_;
  }
};

int main() {
  int x = 7;
  Handle<int, CountDerefs> h(&x);
  *h; *h;
  std::printf("%zu\n", h.deref_count());          // 2
  std::printf("%zu %zu\n", sizeof(Handle<int>),
              sizeof(Handle<int, CountDerefs>));  // 8 16
  // Handle<int> g(&x); g.deref_count();          // error: 没有这个成员
}
```

这里有三个细节：

1. `Stats` 是依赖于模板形参的基类，非限定名字查找不会去里面找，所以必须写 `this->on_deref()`。原因见 [[topics/two-phase-lookup]]。
2. 公有继承意味着 `Handle<int, CountDerefs>*` 能隐式转换成 `CountDerefs*`。如果有人 `new` 一个宿主，再通过策略指针 `delete`，而策略的析构函数不是虚函数，就是 UB（[[expr.delete#3]]）。给策略一个 `protected` 的非虚析构函数，这种 `delete` 就无法通过编译，而宿主仍然能调用它。
3. 宿主的成员函数也可以只对某些策略可用：成员函数定义按需实例化，不用的成员即使对当前策略不合法也不会报错。更清楚的写法是给这个成员加 `requires` 子句，见 [[topics/concepts]]。

用基类注入接口的手法在 [[patterns/mixin|mixin]] 和 [[patterns/crtp|CRTP]] 中更常见。区别在于方向：策略是宿主选择的实现细节，宿主调用它；mixin 是往一个类上叠加功能，CRTP 是基类通过模板实参回调派生类。

### 作为成员：`[[no_unique_address]]` {{c++20}}

继承有副作用：策略的成员名会和宿主的成员名混在一起查找，宿主还能隐式转换成策略的引用（公有继承时）；`final` 的类不能作为基类。C++20 的 `[[no_unique_address]]`（[[P0840R2]]）让数据成员也成为潜在重叠子对象（[[dcl.attr.nouniqueaddr#1]]），不用继承就能得到同样的布局：

<div class="compare" markdown="1">

```cpp
template<class T, class D>
class Ptr : private D {
  T* p_;
  // 通过 *this 取得删除器
};
```

```cpp
template<class T, class D>
class Ptr {
  T* p_;
  [[no_unique_address]] D d_;
};
```

</div>

下面在本机比较几种写法的大小：

```cpp run title="size.cpp" impl
#include <cstdio>

struct Empty  { void operator()(int*) const noexcept {} };
struct Empty2 { void operator()(int*) const noexcept {} };
struct Final final { void operator()(int*) const noexcept {} };
struct Stateful { int* count; void operator()(int*) const noexcept { ++*count; } };

template<class D> struct AsBase : private D { int* p; };
template<class D> struct AsMember { D d; int* p; };
template<class D> struct AsNua { [[no_unique_address]] D d; int* p; };
struct TwoSame     { [[no_unique_address]] Empty a; [[no_unique_address]] Empty  b; int* p; };
struct TwoDistinct { [[no_unique_address]] Empty a; [[no_unique_address]] Empty2 b; int* p; };

int main() {
  std::printf("%zu\n", sizeof(AsBase<Empty>));      // 8
  std::printf("%zu\n", sizeof(AsMember<Empty>));    // 16
  std::printf("%zu\n", sizeof(AsNua<Empty>));       // 8
  std::printf("%zu\n", sizeof(AsNua<Final>));       // 8：final 也行
  std::printf("%zu\n", sizeof(AsNua<Stateful>));    // 16：有状态就要存
  std::printf("%zu\n", sizeof(TwoSame));            // 8
  std::printf("%zu\n", sizeof(TwoDistinct));        // 8
  TwoSame t; TwoDistinct u;
  std::printf("%td %td\n", (char*)&t.b - (char*)&t.a,   // 1
                           (char*)&u.b - (char*)&u.a);  // 0
}
```

注释是本机 Clang 23 在 arm64 上的输出。最后一行说明一条限制：两个大小为零的子对象如果类型相同，就不能有相同的地址（[[intro.object#10]] 第 10.3 项要求它们不是相似类型）。`TwoSame` 的 `b` 因此被放到偏移 1，两个空成员仍然和 `p` 重叠，总大小没有变。宿主有两个同类型的策略（比如两个维度都用同一个空类）时，大小可能因此增加。

`AsBase<Final>` 不能编译，因为 `final` 类不能被继承；`[[no_unique_address]]` 没有这个限制。

!!! impl "实现差异"
    MSVC 为了 ABI 兼容，不让标准的 `[[no_unique_address]]` 生效，要写 `[[msvc::no_unique_address]]`；它的多重继承中也只有第一个空基类默认被压缩，要加 `__declspec(empty_bases)`。跨平台代码通常用宏包装这两处。

    libc++ 的 `unique_ptr` 内部已经从 EBO 改用 `[[no_unique_address]]`，但为了保持和旧布局二进制兼容，对 `final` 的空删除器额外补了填充：本机 `sizeof(std::unique_ptr<int, FinalDel>)` 是 16（`FinalDel` 是一个 `final` 的空函数对象）。布局一旦发布就是 ABI 的一部分，从 EBO 换成 `[[no_unique_address]]` 也可能改变布局。

### 只提供类型

策略还可以只提供类型，让宿主从中选择数据成员的类型。引用计数是否需要原子操作就是这样一个维度：

```cpp ok
#include <atomic>
struct SingleThreaded { using counter = long; };
struct MultiThreaded  { using counter = std::atomic<long>; };

template<class Threading>
struct RefBlock {
  typename Threading::counter refs{1};
  void retain() noexcept { ++refs; }
};
```

本机 `-O2` 下，`RefBlock<SingleThreaded>::retain` 编译成普通的读、加、写三条指令，`RefBlock<MultiThreaded>::retain` 编译成一条 `ldaddal`（arm64 的原子加法，带获取和释放语义）。单线程使用的代码不必为原子操作付出代价，而这个选择对宿主的其余代码透明。

## 策略会被内联掉

策略的成员函数在类内定义，是隐式内联的；宿主调用它们时类型在编译期已知，没有间接调用。只要优化器把它们内联，策略就不留痕迹。下面四个函数两两比较：

```cpp
// 接上文 ptr.cpp 中的 Ptr、NoCheck、ThrowOnNull
int raw(int* const& p)           { return *p; }
int unchecked(const Ptr<int>& p) { return *p; }

int raw_checked(int* const& p) {
  if (!p) throw std::logic_error("null dereference");
  return *p;
}
int checked(const Ptr<int, ThrowOnNull>& p) { return *p; }
```

本机 Clang 23 `-O2`（arm64）下，`raw` 和 `unchecked` 都是 `ldr`、`ldr`、`ret` 三条指令；`raw_checked` 和 `checked` 的指令序列逐条相同，都是一个 `cbz` 跳到抛异常的路径。`Ptr` 的析构函数除了先从对象里读出指针，和手写的 `delete p;` 生成相同的代码。

`Ptr<int>` 按引用传递是为了公平比较。`Ptr` 有非平凡的析构函数，在 Itanium C++ ABI 下不能放在寄存器里按值传递，这一点和 `unique_ptr` 相同，见 [[unique.ptr]] 末尾的 ABI 一节。

## 标准库里的策略

标准库的许多类模板都有策略形参，只是标准不用这个名字，而是叫具名要求：

| 宿主 | 策略形参 | 要求 | 决定什么 |
|---|---|---|---|
| 所有分配器感知容器 | `Allocator` | *Cpp17Allocator*（[[allocator.requirements.general]]） | 内存从哪里来、指针是什么类型 |
| `basic_string`、`basic_string_view`、iostream | `traits` | 字符 traits（[[char.traits.require#1]]） | 字符怎样比较、复制、查找 |
| `set`、`map`、`priority_queue` | `Compare` | 严格弱序（[[associative.reqmts.general#2]]） | 元素顺序 |
| `unordered_set`、`unordered_map` | `Hash`、`Pred` | *Cpp17Hash*（[[unord.req.general#3]]） | 哈希与相等 |
| `unique_ptr` | `D`（删除器） | [[unique.ptr.general]] | 怎样释放对象 |
| `mdspan` | `LayoutPolicy`、`AccessorPolicy` | [[mdspan.layout.policy.reqmts#1]]、[[mdspan.accessor.reqmts#1]] | 多维下标怎样映射到偏移、怎样访问元素 |

`char_traits` 是最典型的例子。只换掉比较相关的几个函数，就得到一个不区分大小写的字符串：

```cpp run title="ci.cpp" ok
#include <cctype>
#include <cstdio>
#include <string>

struct ci_traits : std::char_traits<char> {
  static char up(char c) {
    return static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
  }
  static bool eq(char a, char b) { return up(a) == up(b); }
  static bool lt(char a, char b) { return up(a) < up(b); }
  static int compare(const char* a, const char* b, std::size_t n) {
    for (std::size_t i = 0; i < n; ++i) {
      if (lt(a[i], b[i])) return -1;
      if (lt(b[i], a[i])) return 1;
    }
    return 0;
  }
  static const char* find(const char* s, std::size_t n, char c) {
    for (std::size_t i = 0; i < n; ++i)
      if (eq(s[i], c)) return s + i;
    return nullptr;
  }
};
using ci_string = std::basic_string<char, ci_traits>;

int main() {
  ci_string a = "Hello";
  std::printf("%d\n", a == "HELLO");          // 1
  std::printf("%zu\n", a.find('L'));          // 2
  std::string s = "hello";
  // ci_string b = s;                         // error: 不相关的类型
  ci_string b(s.data(), s.size());            // 要显式转换
  std::printf("%d\n", a == b);                // 1
}
```

注释掉的那一行展示了基于策略的设计最常见的麻烦：`ci_string` 和 `std::string` 是两个不相关的类型，不能互相赋值，`std::cout << a` 也不能编译，因为流的 `operator<<` 只接受 traits 相同的字符串。下文专门讨论这个问题。

`mdspan` 的 `LayoutPolicy` 值得注意：它本身不是映射，而是一个带成员模板的类型，`LayoutPolicy::mapping<E>` 才是针对某个 `extents` 的映射（[[mdspan.layout.policy.reqmts#1]]）。这是让策略推迟到宿主内部才确定全部实参的一种办法，和下文分配器的 rebind 是同一个思路。

### 执行策略不是这种策略

`std::sort(std::execution::par, first, last)` 里的 `par` 也叫**执行策略**（[[g:execution-policy]]），但它的作用方式不同：

- 它是传给函数的对象，不是类模板的实参。并行算法是另一组重载，多出来的第一个形参类型是执行策略模板形参（[[algorithms.parallel.overloads#1]]）。
- 它的类型只用来选择重载，并说明允许哪种并行；算法怎样并行由库实现决定，策略类本身不提供任何行为。
- 集合是封闭的：用户为 `is_execution_policy` 添加特化是 UB（[[execpol.type#3]]），也就是说用户不能写自己的执行策略。

所以执行策略更接近 [[patterns/tag-dispatch|标签分派]] 里的标签，而不是类模板的策略形参。

### 把策略移到运行期

标准库也有反过来的设计。`shared_ptr` 的删除器不是模板实参，构造时传入，被类型擦除后存在控制块里，所以删除器不同的 `shared_ptr<T>` 仍然是同一个类型（见 [[topics/ownership-and-smart-pointers]]）。`std::pmr::polymorphic_allocator` 把分配策略换成一个指向 `memory_resource` 的指针，让使用不同内存来源的容器成为同一类型（见 [[topics/allocators-and-pmr]]）。两者都是用一次间接调用换取类型统一。

## 用 concepts 约束策略

策略的要求只写在文档里时，传错策略的错误要等到宿主内部用到它才出现：

<div class="compare" markdown="1">

```cpp title="no-concept.cpp" error
template<class T, class Checking>
struct Ptr {
  T* p_;
  T& operator*() const {
    Checking::check(p_);
    return *p_;
  }
};
struct BadCheck {
  static bool verify(const void*);
};
int main() {
  int x = 0;
  Ptr<int, BadCheck> p{&x}; // 这里不报错
  return *p;  // error: 出现在
}             // operator* 的实例化里
```

```cpp title="concept.cpp" error
template<class P>
concept CheckingPolicy =
  requires(const void* p) {
    P::check(p);
  };
template<class T, CheckingPolicy Checking>
struct Ptr {
  T* p_;
  T& operator*() const {
    Checking::check(p_);
    return *p_;
  }
};
struct BadCheck {
  static bool verify(const void*);
};
int main() {
  int x = 0;
  Ptr<int, BadCheck> p{&x}; // error: 约束
  return *p;                // 不满足
}
```

</div>

本机 Clang 23 对左边报告 `no member named 'check' in 'BadCheck'`，位置在 `Ptr::operator*` 内部，再用一条 note 指回 `return *p;`。对右边报告 `constraints not satisfied for class template 'Ptr'`，位置就是写出 `Ptr<int, BadCheck>` 的那一行，接着两条 note 说明 `BadCheck` 不满足 `CheckingPolicy`，因为 `P::check(p)` 不合法。

这个例子里两边的诊断都只有几行。差距在宿主更复杂时才明显：本机用一个没有 `std::hash` 特化的键类型实例化 `std::unordered_map` 并调用 `operator[]`，Clang 报告 5 个错误、共 79 行，全部位于 libc++ 的头文件内部。*Cpp17Hash* 是具名要求而不是 concept，libc++ 只能在内部加 `static_assert` 来改善诊断。

写自己的策略化类模板时，每个策略维度都应该有一个 concept。它同时是可检查的文档：读者看 `CheckingPolicy` 的定义就知道要提供什么，不用去读宿主的实现。concept 的写法和满足检查见 [[topics/concepts]]。

!!! pitfall "concept 要和宿主的用法一致"
    上面的 `CheckingPolicy` 要求 `P::check(p)`，所以它拒绝 `check` 是非静态成员函数的策略。如果宿主改成存一个策略对象并写 `checking_.check(p_)`，concept 也要相应改成 `requires(const P& c, const void* p) { c.check(p); }`。concept 写得比宿主的实际用法宽，错误又会回到宿主内部；写得比实际用法窄，就会无谓地拒绝合法的策略。

## 组合爆炸与类型不兼容

策略让写类的人免于组合爆炸，但组合并没有消失，而是转移到了类型系统里：`Ptr<Widget, NoCheck>` 和 `Ptr<Widget, ThrowOnNull>` 是两个不相关的类型。一个函数如果接受 `const Ptr<Widget>&`，就不能传入使用其他策略的 `Ptr`。

解决办法有三种：

1. 函数不需要所有权时，干脆接受 `Widget&` 或 `Widget*`，和策略无关（见 [[topics/ownership-and-smart-pointers]] 的参数传递一节）。
2. 函数写成模板，接受任意策略：`template<class C, class D> void f(const Ptr<Widget, C, D>&);`。代价是每种组合实例化一份，且函数只能放在头文件里。
3. 在宿主里提供转换构造函数，由策略决定哪些转换合法。

第三种的写法和 `unique_ptr` 一样。`unique_ptr<U, E>` 能转换成 `unique_ptr<T, D>`，要求指针可以隐式转换，且 `E` 可以隐式转换成 `D`（[[unique.ptr.single.ctor#19]]）。也就是说，删除器策略自己的转换构造函数决定了 `unique_ptr` 之间能否转换。`Ptr` 可以照搬这个规则：

```cpp run title="convert.cpp" ok
#include <concepts>
#include <utility>

struct NoCheck     { static void check(const void*) noexcept {} };
struct ThrowOnNull {
  ThrowOnNull() = default;
  ThrowOnNull(NoCheck) noexcept {}   // 只允许 NoCheck → ThrowOnNull
  static void check(const void* p) { if (!p) throw 0; }
};

template<class T, class Checking = NoCheck>
class Ptr {
  T* p_ = nullptr;
  template<class, class> friend class Ptr;  // 其他特化也要访问 p_
public:
  Ptr() = default;
  explicit Ptr(T* p) noexcept : p_(p) {}
  Ptr(Ptr&& o) noexcept : p_(std::exchange(o.p_, nullptr)) {}
  template<class U, class C2>
    requires std::convertible_to<U*, T*> && std::convertible_to<C2, Checking>
  Ptr(Ptr<U, C2>&& o) noexcept : p_(std::exchange(o.p_, nullptr)) {}
  ~Ptr() { delete p_; }
};

struct Base { virtual ~Base() = default; };
struct Derived : Base {};

int main() {
  Ptr<Derived>              a(new Derived);
  Ptr<Base, ThrowOnNull>    b = std::move(a);   // OK：两个维度都放宽
  // Ptr<Derived, NoCheck>  c = std::move(b);   // error：Base* → Derived* 不行
  Ptr<Base, ThrowOnNull>    d(new Base);
  // Ptr<Base, NoCheck>     e = std::move(d);   // error：不能丢掉检查
}
```

`Ptr` 的不同特化之间没有特殊的访问权限，所以要用友元模板声明 `template<class, class> friend class Ptr;` 让它们互相访问 `p_`。去掉最后一行的注释，本机 Clang 报告 `no viable conversion`，并在 note 里说明转换构造函数的约束不满足。

## 模板模板形参还是类型形参

宿主经常需要用策略处理一个用户没有直接给出的类型。链表的分配器策略就是例子：用户想的是分配 `T`，链表实际分配的是节点 `Node`。有两种写法：

```cpp run title="rebind.cpp" ok
#include <cstddef>
#include <memory>

template<class T, std::size_t Align = 64>
struct AlignedAlloc {                   // 第二个参数有默认值
  using value_type = T;
  template<class U> struct rebind { using other = AlignedAlloc<U, Align>; };
  AlignedAlloc() = default;
  template<class U> AlignedAlloc(const AlignedAlloc<U, Align>&) noexcept {}
  T* allocate(std::size_t n) {
    return static_cast<T*>(::operator new(n * sizeof(T), std::align_val_t{Align}));
  }
  void deallocate(T* p, std::size_t) noexcept {
    ::operator delete(p, std::align_val_t{Align});
  }
  friend bool operator==(AlignedAlloc, AlignedAlloc) = default;
};

// 写法一：模板模板形参，宿主自己提供类型实参
template<class T, template<class> class Alloc = std::allocator>
class ListA {
  struct Node { T value; Node* next; };
  Alloc<Node> alloc_;                   // 直接用 Node 实例化
public:
  void push(T v) { Node* n = alloc_.allocate(1); alloc_.deallocate(n, 1); (void)v; }
};

// 写法二：类型形参，宿主用 rebind 换掉类型实参
template<class T, class Alloc = std::allocator<T>>
class ListB {
  struct Node { T value; Node* next; };
  using NodeAlloc = std::allocator_traits<Alloc>::template rebind_alloc<Node>;
  NodeAlloc alloc_;
public:
  void push(T v) { Node* n = alloc_.allocate(1); alloc_.deallocate(n, 1); (void)v; }
};

template<class T> using Align128 = AlignedAlloc<T, 128>;

int main() {
  ListA<int, AlignedAlloc> a;           // Align 用默认值 64
  ListA<int, Align128> c;               // 别名模板也能作实参
  ListB<int, AlignedAlloc<int, 128>> b; // rebind 时保留 128
  a.push(1); c.push(2); b.push(3);
}
```

（`push` 只分配再释放一个节点，用来让成员函数实例化。）

模板模板形参（[[g:template-template-parameter]]）的写法看起来更直接，但有几个问题：

- 实参必须是模板，用户不能传一个已经配置好状态的分配器对象类型，比如 `AlignedAlloc<int, 128>`；要配置非类型实参，只能另写别名模板。
- 形参的模板头固定了实参的形状。`template<class> class` 能接受有两个形参的 `AlignedAlloc`，是因为第二个形参有默认值：C++17 起（[[P0522R0]]），只要模板模板形参至少和实参一样特殊就算匹配（[[temp.arg.template#4]]）。在此之前，两者的形参列表必须完全一致。
- 策略本身不能是普通的类，`NoCheck` 这种非模板策略无法传给模板模板形参。

类型形参加 rebind 是标准库的选择：用户给出一个完整的类型，宿主通过 `allocator_traits<Alloc>::rebind_alloc<Node>` 得到针对节点的分配器（[[allocator.traits.types#11]]）。如果分配器没有提供 `rebind` 成员，`allocator_traits` 会把形如 `SomeAllocator<T, Args>` 的类型改写成 `SomeAllocator<U, Args>`，但前提是 `Args` 全是类型实参（[[allocator.requirements.general#18]]）。`AlignedAlloc` 的第二个实参是一个值，不满足这个前提，所以它必须自己写 `rebind`。删掉那一行，本机 libc++ 报告 `This allocator has to implement rebind`。

## 默认策略与命名模板实参

模板实参按位置对应形参。`Ptr<int, NoCheck, DeleteArray>` 只想改删除器，却必须写出排在前面的检查策略，即使它就是默认值。策略越多，这个问题越明显，而且调整形参顺序会破坏所有已有的用法。

C++ 没有命名模板实参。常见的替代办法是把一组策略打包成一个类型，用户从默认包派生，只覆盖需要改的成员：

```cpp run title="named.cpp" ok
#include <cstdio>
#include <type_traits>

struct NoCheck     { static constexpr bool checked = false; };
struct ThrowOnNull { static constexpr bool checked = true; };
struct DeleteOne   { static constexpr bool array = false; };
struct DeleteArray { static constexpr bool array = true; };

// 一组策略打包成一个类型
struct DefaultPtrPolicies {
  using checking = NoCheck;
  using deleter  = DeleteOne;
};

template<class T, class P = DefaultPtrPolicies>
class Ptr {
  using Checking = typename P::checking;
  using Deleter  = typename P::deleter;
public:
  static void describe() {
    std::printf("checked=%d array=%d\n", Checking::checked, Deleter::array);
  }
};

struct ArrayPolicies : DefaultPtrPolicies {
  using deleter = DeleteArray;            // 只改删除器，检查策略沿用默认
};

// 值形式的选项：类类型的常量模板形参（C++20）
struct PtrOptions {
  bool checked = false;
  bool array   = false;
};
template<class T, PtrOptions O = {}>
class Ptr2 {
public:
  static void describe() { std::printf("checked=%d array=%d\n", O.checked, O.array); }
};

int main() {
  Ptr<int>::describe();                         // checked=0 array=0
  Ptr<int, ArrayPolicies>::describe();          // checked=0 array=1
  Ptr2<int, {.array = true}>::describe();       // checked=0 array=1
  static_assert(std::is_same_v<Ptr2<int, {.array = true}>,
                               Ptr2<int, {false, true}>>);
}
```

策略包的缺点是类型身份跟着包走：另一个人写的 `struct MyArrayPolicies : DefaultPtrPolicies { using deleter = DeleteArray; };` 和 `ArrayPolicies` 内容相同，但 `Ptr<int, MyArrayPolicies>` 和 `Ptr<int, ArrayPolicies>` 仍是不同类型。

选项只是开关或数值时，C++20 允许用类类型作常量模板形参（[[P0732R2]]），可以配合指派初始化器写成 `Ptr2<int, {.array = true}>`。这种形参的类型必须是结构化类型（[[g:structural-type]]，[[temp.param#12]]）；两个模板实参的值相等时，得到的就是同一个类型（[[temp.type#1]]），上面的 `static_assert` 验证了这一点。它的局限是只能传值，不能传类型，宿主要用 `if constexpr` 根据值选择行为。更多做法见 [[patterns/named-parameters|命名参数与 builder]]。

## 编译期代价

每种策略组合都是一个独立的类模板特化，用到的成员函数各实例化一份。本机做了一个对照：上文 `ptr.cpp` 的 `Ptr`，每个函数构造、移动、移动赋值、解引用一个 `Ptr`，共 64 个函数。

| 情形 | `-O0` 目标文件 | `-O0` 中 `Ptr` 成员函数 | `-O2` 目标文件 |
|---|---|---|---|
| 1 个函数，1 种组合 | 3.5 KB | 9 | 0.5 KB |
| 64 个函数，同 1 种组合 | 27 KB | 9 | 4.8 KB |
| 64 个函数，64 种组合（4 × 4 × 4） | 120 KB | 576 | 8.5 KB |

`-O0` 下，64 种组合各自生成了全部 9 个成员函数，共 576 个，目标文件是单一组合的 4 倍多。`-O2` 下这些函数全部被内联，`Ptr` 的成员函数一个也没有留下，差距主要来自被管理的类型不同。

这个规模下编译时间都在 0.1 秒左右，看不出差别。真实项目里的代价体现在别处：调试构建的体积和链接时间随组合数增长；每个策略类型都出现在修饰名里，比如 `checked` 函数的符号是 `_Z7checkedRK3PtrIi11ThrowOnNull9DeleteOneE`，嵌套使用时符号和错误信息里的类型名会很长；所有代码都在头文件里，修改一个策略会让所有包含它的翻译单元重新编译。

## 与运行期的策略模式比较

经典的策略模式（[[patterns/strategy|策略模式的几种写法]]）在运行期选择行为：宿主持有一个指向抽象基类的指针或一个 `std::function`，通过虚调用或间接调用执行策略。两者解决的是同一个问题，取舍正好相反：

| | 基于策略的设计（编译期） | 策略模式（运行期） |
|---|---|---|
| 何时选定 | 编译期，写在类型里 | 运行期，可以随时更换 |
| 不同选择的对象 | 不同类型，不能放进同一个容器 | 同一类型 |
| 调用开销 | 无，通常被内联 | 一次间接调用，一般不能内联 |
| 空间开销 | 空策略为零 | 至少一个指针 |
| 代码位置 | 全部在头文件 | 实现可以放在 `.cpp` 里 |
| 代码体积 | 每种组合一份 | 一份 |
| 错误发现 | 编译期（配合 concepts） | 运行期 |

两者也可以结合：用编译期策略决定性能敏感的部分，再用 [[patterns/type-erasure|类型擦除]] 把不同组合包装成同一个接口类型，就像 `shared_ptr` 擦除删除器、`pmr` 擦除分配器那样。

## 常见陷阱

### 通过策略指针删除宿主

宿主公有继承策略时，宿主指针能隐式转换成策略指针；策略的析构函数不是虚函数时，通过它 `delete` 宿主是 UB。策略应该把析构函数声明为 `protected`。私有继承或用 `[[no_unique_address]]` 成员则不会有这个问题。

### 策略之间的名字冲突

宿主继承两个策略，而它们都有名为 `check` 的成员时，在宿主里写 `this->check(p)` 是有歧义的名字查找，编译失败。策略的成员名应该带上维度的前缀，或者改用成员而不是继承。

### 以为 EBO 总会生效

空策略作为普通数据成员会占至少一个字节，再加上对齐填充；`final` 的空策略不能作基类；两个同类型的空子对象不能重叠在同一个地址；MSVC 需要专门的属性。改动策略的存储方式时，要用 `static_assert(sizeof(...) == ...)` 把期望的大小写进代码。

### 只用文档描述策略的要求

错误策略在宿主从未用到它时可以一直不被发现，一旦用到，错误信息出现在宿主内部。用 concept 约束每个策略形参。

### 维度并不正交

如果某个策略只在另一个策略取特定值时才有意义，组合就不再自由，宿主里会出现大量 `if constexpr` 或 `static_assert` 来排除非法组合。这时应该把这两个维度合并成一个策略。

## 什么时候用

| 情形 | 建议 |
|---|---|
| 写通用库，行为维度清楚且正交，性能敏感（容器、智能指针、分配器、日志） | 用基于策略的设计，给每个维度一个 concept |
| 行为需要在运行期切换，或要把不同配置的对象放进同一个容器 | 用运行期策略模式或类型擦除 |
| 只是几个布尔开关或数值 | 用类类型的常量模板形参，或干脆用构造函数参数 |
| 只有一个维度，且只有两三种选择 | 直接写函数对象形参（如 `Compare`），不必提出策略这个概念 |
| 策略之间相互依赖 | 合并成一个策略，或重新划分维度 |
| 代码要在 ABI 边界上发布 | 慎用：策略类型进入修饰名和布局，修改任何策略都改变 ABI |

## 思考题

!!! question "1"
    `struct H { [[no_unique_address]] Empty a; [[no_unique_address]] Empty b; int* p; };` 中 `Empty` 是空类。`&h.a == &h.b` 可能为真吗？`sizeof(H)` 一定比 `sizeof(int*)` 大吗？

<details markdown="1">
<summary>答案</summary>

`&h.a == &h.b` 不可能为真。按 [[intro.object#10]]，两个子对象只有在其中至少一个大小为零、且它们不是相似类型时，才可以共用地址；`a` 和 `b` 类型相同，所以地址必须不同。但这不意味着 `H` 一定变大：它们可以分别和 `p` 的不同字节重叠。本机 Clang 23 把 `a` 放在偏移 0、`b` 放在偏移 1，`sizeof(H)` 仍是 8。由于空成员能否大小为零本身是实现定义的（[[intro.object#8]]），另一个实现给出更大的结果也符合标准。
</details>

!!! question "2"
    库里有 `void render(const Ptr<Widget>& w);`。调用方持有的是 `Ptr<Widget, ThrowOnNull>`，传不进去。`render` 只是读取 `Widget`，不保存它。应该怎样改签名？

<details markdown="1">
<summary>答案</summary>

改成 `void render(const Widget& w);`，调用处写 `render(*p)`。`render` 不涉及所有权，它的形参根本不应该出现智能指针，自然也就和策略无关；解引用发生在调用方，用的是调用方自己的检查策略。如果 `Widget` 可能不存在，用 `const Widget*`。只有当函数要接管或共享所有权时，形参才应该是 `Ptr`，这时再考虑模板化或转换构造函数。
</details>

!!! question "3"
    为什么 `std::execution::par` 叫策略，用户却不能像写 `Compare` 那样写一个自己的执行策略？

<details markdown="1">
<summary>答案</summary>

`Compare` 是类模板的策略形参，标准规定了它必须提供的表达式（严格弱序的比较），容器调用它，行为由用户的实现决定。执行策略不提供行为：并行算法的重载只看实参的类型是不是执行策略（`is_execution_policy_v`），据此选择重载并放宽对元素访问函数的要求，怎样并行完全由库实现决定（[[algorithms.parallel.overloads#1]]）。用户为 `is_execution_policy` 添加特化是 UB（[[execpol.type#3]]），所以这个集合是封闭的，只有标准和实现定义的执行策略。它在机制上是一个标签，而不是可替换的实现。
</details>
