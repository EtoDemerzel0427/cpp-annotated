---
title: 异常安全与 noexcept
summary: 操作中途抛出异常之后对象处于什么状态：栈回溯销毁什么，基本、强、不抛出三种保证及标准库怎样表述它们，copy-and-swap 的代价，移动构造函数为什么要 noexcept，noexcept 函数抛出时发生什么，以及析构函数、RAII 和 scope guard。
status: draft
order: 74
since: c++98
papers: N2855, N3050, N4152
related: except, except.ctor, except.handle, except.spec, except.special, support.exception, vector, expected, topics/special-members-and-elision, history/move-semantics, toolchain/exception-implementation
tags: 异常, 异常安全, noexcept, RAII, 专题
updated: 2026-10-19
---

!!! tldr
    - 异常安全问的是：一个操作中途抛出异常后，对象处于什么状态，有没有泄漏资源。答案分三级：不抛出、强保证（失败时没有效果）、基本保证（失败后仍然有效，但值不确定）。
    - 写出强保证的通用办法是先在旁边做完所有可能失败的工作，再用不会失败的操作提交。copy-and-swap 是它的一个实例，代价是每次都重新分配。
    - `std::vector` 扩容时只有移动构造函数不抛出（或者类型不可复制）才移动元素，否则复制。手写移动构造函数忘了 `noexcept`，`vector` 就会一直复制。
    - `noexcept` 是承诺，不是检查。异常真的离开 `noexcept` 函数时调用 `std::terminate`，栈是否回溯由实现定义。
    - 析构函数默认不抛出。析构函数在栈回溯中抛出会终止程序，清理工作应当交给 RAII 对象，需要区分成功与失败时用 `std::uncaught_exceptions`。

## 一个会弄坏对象的赋值运算符

```cpp run title="broken-assign.cpp" ub
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <new>

bool fail_next = false;            // 故障注入：让下一次 new[] 失败
void* operator new[](std::size_t n) {
  if (fail_next) { fail_next = false; throw std::bad_alloc(); }
  if (void* p = std::malloc(n)) return p;
  throw std::bad_alloc();
}
void operator delete[](void* p) noexcept { std::free(p); }

class Buffer {
  std::size_t n_;
  int* p_;
public:
  explicit Buffer(std::size_t n) : n_(n), p_(new int[n]{}) {}
  Buffer(const Buffer&) = delete;
  ~Buffer() { delete[] p_; }
  Buffer& operator=(const Buffer& o) {
    if (this != &o) {
      delete[] p_;                 // 先释放旧数组
      p_ = new int[o.n_];          // 抛出：p_ 仍指向已释放的数组
      n_ = o.n_;
      std::copy_n(o.p_, n_, p_);
    }
    return *this;
  }
};

int main() {
  Buffer a(4), b(8);
  try {
    fail_next = true;
    a = b;
  } catch (const std::bad_alloc&) {
    std::puts("assignment failed");
  }
}                                  // ~Buffer 再次 delete[] 同一个指针
```

`operator=` 在分配新数组之前就释放了旧数组。分配失败时异常离开函数，`a.p_` 还指向已经释放的内存，`a` 的不变式被破坏了。调用方接住了异常，程序看起来恢复了，但 `a` 离开作用域时析构函数再次释放同一个指针，这是 UB。本机 Clang 23 加 `-fsanitize=address` 运行，报告 `attempting double-free`，第二次释放发生在 `Buffer::~Buffer()`，第一次在 `Buffer::operator=`。

修复只需要调整顺序：先做可能失败的事，再做不会失败的事。

```cpp run title="fixed-assign.cpp" ok
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <new>

bool fail_next = false;
void* operator new[](std::size_t n) {
  if (fail_next) { fail_next = false; throw std::bad_alloc(); }
  if (void* p = std::malloc(n)) return p;
  throw std::bad_alloc();
}
void operator delete[](void* p) noexcept { std::free(p); }

class Buffer {
  std::size_t n_;
  int* p_;
public:
  explicit Buffer(std::size_t n) : n_(n), p_(new int[n]{}) {}
  ~Buffer() { delete[] p_; }
  std::size_t size() const { return n_; }
  Buffer& operator=(const Buffer& o) {
    int* q = new int[o.n_];        // 可能抛出：*this 尚未改动
    std::copy_n(o.p_, o.n_, q);    // 复制 int 不抛出
    delete[] p_;                   // 从这里起不会再失败
    p_ = q;
    n_ = o.n_;
    return *this;
  }
};

int main() {
  Buffer a(4), b(8);
  try { fail_next = true; a = b; } catch (const std::bad_alloc&) {}
  std::printf("%zu\n", a.size());  // 4：保持原状
  a = b;
  std::printf("%zu\n", a.size());  // 8
}
```

现在分配失败时 `a` 原封未动，好像赋值从未发生。这个版本也不再需要 `this != &o` 的检查：自赋值时先复制出一份，再释放旧的，结果仍然正确。

一个操作中途抛出异常之后，对象处于什么状态、有没有泄漏资源，这类性质统称为**异常安全**（exception safety）。要分析它，先要知道异常抛出时语言做了什么。

## 抛出时发生了什么

### 栈回溯

异常从 `throw` 传到接住它的 `catch` 子句（handler）的途中，凡是进入那个 try 块以来已经构造完成、还没销毁的自动对象，都按构造的逆序析构（[[except.ctor#2]]）。这个过程叫**栈回溯**（[[g:stack-unwinding|stack unwinding]]）。

C++ 没有 `finally`，清理靠的就是这一条：把资源交给一个局部对象，它的析构函数在正常返回和异常退出时都会运行。这种写法叫 **RAII**（resource acquisition is initialization），后文还会回到它。上例的 `Buffer` 本身就是一个 RAII 类，它的问题出在赋值运算符的步骤顺序上。

### 构造到一半失败

构造函数抛出时，对象的生存期从未开始，它自己的析构函数不会运行。已经初始化完成的基类和成员会按逆序析构，还没开始初始化的不受影响（[[except.ctor#3]]）。

<div class="compare" markdown="1">

```cpp
struct Leaky {
  int* p;
  int* q;
  Leaky()
    : p(new int[100]),
      q(new int[100]) {}  // 抛出：p 泄漏
  ~Leaky() { delete[] p; delete[] q; }
};
```

```cpp
struct Safe {
  std::unique_ptr<int[]> p;
  std::unique_ptr<int[]> q;
  Safe()
    : p(new int[100]),
      q(new int[100]) {}  // 抛出：析构 p
};
```

</div>

左边第二个 `new` 抛出时，`~Leaky` 不运行，`p` 是 `int*`，没有析构函数可调，内存就泄漏了。右边 `p` 是一个已经构造完成的子对象，回溯时它的析构函数释放内存。由此得到一条规则：一个类如果要管理多份资源，就让每份资源由一个独立的子对象管理。逐条解释、以及委托构造函数的特殊情形，见 [[except.ctor]]。

### 构造函数的 function-try-block

想在构造函数里捕获成员初始化时抛出的异常，`try` 必须把成员初始化列表也包进去，这种写法叫 **function-try-block**：

```cpp run title="ctor-function-try-block.cpp" ok
#include <cstdio>
#include <stdexcept>

struct Conn {
  explicit Conn(const char* host) {
    if (!*host) throw std::invalid_argument("empty host");
  }
};

struct Client {
  Conn conn;
  explicit Client(const char* host) try : conn(host) {
  } catch (const std::invalid_argument& e) {
    std::printf("Client: %s\n", e.what());
  }                                // 到达末尾：自动重新抛出
};

int main() {
  try {
    Client c("");
  } catch (const std::exception& e) {
    std::printf("main: %s\n", e.what());
  }
}
```

输出 `Client: empty host` 和 `main: empty host`。构造函数的 function-try-block 不能把异常吞掉：控制到达 handler 末尾时，当前异常自动重新抛出（[[except.handle#14]]），在 handler 里写 `return` 是非良构的（[[except.handle#13]]）。道理很简单，成员没构造出来，就不存在一个可以交给调用方的对象。

所以它只适合做两件事：记录日志，或者把异常翻译成另一种类型再抛出。进入 handler 时，已构造的成员和基类都已经析构了（[[except.ctor#3]]），在 handler 里访问对象的非静态成员或基类是 UB（[[except.handle#11]]）。释放资源也不是它的职责，交给子对象的析构函数。

## 三种保证

`fixed-assign.cpp` 的赋值失败时对象原封未动；有的操作只能保证失败后对象仍然可用。按失败后的状态，异常安全分三级，这套分类来自 David Abrahams 在 STL 标准化期间的工作，通常称为 Abrahams 保证：

| 保证 | 失败之后 | 典型操作 |
|---|---|---|
| **不抛出保证**（nothrow） | 不会失败 | 析构函数、`swap`、移动构造、`pop_back` |
| **强保证**（strong） | 状态与调用之前相同，好像没调用过 | `vector::push_back`、`fixed-assign.cpp` 的赋值 |
| **基本保证**（basic） | 不变式成立、没有泄漏，但值不确定 | `vector` 的复制赋值、在 `vector` 中间 `insert` |

没有任何保证的操作，比如开头的 `broken-assign.cpp`，失败后连析构都不安全。

三级之间是层层依赖的关系。强保证通常靠先在旁边完成所有可能失败的工作，再用不抛出的操作提交；没有不抛出的操作，就提交不了。基本保证则要求每一份资源在任何时刻都有一个 RAII 对象负责。

### 标准库怎样表述

标准正文不使用基本、强这些名字，而是逐个函数写出失败后的效果：

- 强保证写成 "has no effects" 或 "there are no effects"；
- 不抛出写成 `noexcept`，或者 *Throws*: Nothing；
- 基本保证最接近的说法是**有效但未指定的状态**（[[g:valid-but-unspecified-state|valid but unspecified state]]，[[defns.valid]]）：对象的不变式成立，所有没有前置条件的操作都可以调用。被移动过的标准库对象默认就处于这种状态（[[lib.types.movedfrom#1]]）。

全库通用的规则在 [[res.on.exception.handling]]：库函数通过抛出 *Throws*: 段落列出的类型（或其派生类型）报告失败（¶1）；标准库的析构函数不抛出，表现得如同具有非抛出的异常说明（¶3）；没有 *Throws*: 段落、但又不是 `noexcept` 的函数，可以抛出实现定义的异常，最常见的是 `bad_alloc`（¶4）；实现可以给非虚函数加上 `noexcept`（¶5）。反过来，库对用户代码也有要求：标准库调用的析构函数以异常退出，行为未定义（[[res.on.functions#2.4]]）。

容器的规则集中在 [[container.reqmts#66]]：插入单个元素的 `insert`、`emplace` 抛出时没有效果（66.1）；`push_back`、`push_front` 及对应的 `emplace` 抛出时没有效果（66.2）；`erase`、`clear`、`pop_back`、`pop_front`、`swap` 不抛出（66.3、66.5）。这一段开头就写明，关联容器、无序容器、`deque`、`inplace_vector` 和 `vector` 另有规定。

`vector` 的例外在 [[vector.modifiers#2]]，分三层：

1. 异常不是来自 `T` 的复制、移动构造或赋值，比如分配失败：没有效果；
2. 在末尾插入单个元素，并且 `T` 可以复制插入，或者 `is_nothrow_move_constructible_v<T>` 为真：没有效果；
3. 否则，如果异常来自不可复制的 `T` 的移动构造函数：效果未指定。

第 2、3 层和元素的移动构造函数有关，下文专门讨论。在中间插入时异常来自 `T` 的操作，标准不承诺没有效果，所以只有基本保证。

有些组件的保证取决于元素类型。`optional` 的复制赋值在 `T` 的复制赋值抛出时，包含值的状态 "is as defined by the exception safety guarantee of T's copy assignment"（[[optional.assign#7]]）。泛型组件只能把元素提供的保证原样传出去。

### 容器的复制赋值只有基本保证

[[container.reqmts#18]] 对 `t = v` 只规定了成功时的后置条件 `t == v`，失败时怎样没有说。

```cpp run title="vector-assign-basic.cpp" unspecified
#include <cstdio>
#include <vector>

int budget = 2;                    // 第 3 次复制赋值时抛出
struct E {
  int v;
  E(int x) : v(x) {}
  E(const E&) = default;
  E& operator=(const E& o) {
    if (budget-- == 0) throw 0;
    v = o.v;
    return *this;
  }
};

int main() {
  std::vector<E> a(5, E(0)), b(5, E(1));
  try { a = b; } catch (int) {}
  for (const E& e : a) std::printf("%d ", e.v);
  std::puts("");
}
```

本机 libc++ 输出 `1 1 0 0 0`：容量足够时，`vector` 在原有元素上逐个复制赋值，第三个抛出时前两个已经改了。这是有意的选择，下一节说明为什么。

## copy-and-swap

给 `Buffer` 加上移动构造函数和一个不抛出的 `swap`，赋值运算符可以写成：

```cpp run title="copy-and-swap.cpp" ok
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <new>
#include <type_traits>
#include <utility>
#include <vector>

int allocs = 0;                    // 统计堆分配次数
void* operator new(std::size_t n) {
  ++allocs;
  if (void* p = std::malloc(n)) return p;
  throw std::bad_alloc();
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

class Buffer {
  std::size_t n_ = 0;
  int* p_ = nullptr;
public:
  explicit Buffer(std::size_t n) : n_(n), p_(new int[n]{}) {}
  Buffer(const Buffer& o) : n_(o.n_), p_(new int[o.n_]) {
    std::copy_n(o.p_, n_, p_);
  }
  Buffer(Buffer&& o) noexcept
      : n_(std::exchange(o.n_, 0)), p_(std::exchange(o.p_, nullptr)) {}
  ~Buffer() { delete[] p_; }
  friend void swap(Buffer& a, Buffer& b) noexcept {
    std::swap(a.n_, b.n_);
    std::swap(a.p_, b.p_);
  }
  Buffer& operator=(Buffer o) noexcept {   // 按值传参：复制发生在调用方
    swap(*this, o);
    return *this;                          // o 带着旧数组析构
  }
};

static_assert(std::is_nothrow_move_assignable_v<Buffer>);
static_assert(!std::is_nothrow_copy_assignable_v<Buffer>);

int main() {
  Buffer a(1000), b(1000);
  std::vector<int> u(1000), v(1000);
  allocs = 0;
  for (int i = 0; i < 100; ++i) a = b;
  std::printf("Buffer copy-and-swap: %d allocations\n", allocs);
  allocs = 0;
  for (int i = 0; i < 100; ++i) u = v;
  std::printf("std::vector<int>:     %d allocations\n", allocs);
}
```

这就是 **copy-and-swap**：形参 `o` 按值传递，`a = b` 时用复制构造函数初始化 `o`，`a = std::move(b)` 时用移动构造函数初始化，一个运算符同时充当复制赋值和移动赋值。所有可能失败的工作都在初始化形参时完成，这时 `*this` 还没被碰过；函数体里只有不抛出的 `swap`。

函数本身可以标 `noexcept`，因为形参的初始化发生在调用方。但表达式 `a = b` 包括了这次复制，所以 `is_nothrow_copy_assignable_v<Buffer>` 仍然是 `false`，这与事实相符。

copy-and-swap 的代价在输出里：本机 Clang 23 `-O2`，`Buffer` 赋值 100 次分配了 100 次内存，`std::vector<int>` 同样大小的赋值一次也没有分配，因为它直接复用已有的存储。强保证要求保留旧状态直到新状态完全建好，旧存储在这段时间里就不能复用。

所以标准库给 `vector` 的复制赋值选择了基本保证。需要强保证的调用方可以自己付这笔代价：

```cpp
std::vector<T> tmp = b;   // 可能失败：a 不受影响
a.swap(tmp);              // 不抛出
```

反过来，如果库替所有人付了，不需要强保证的调用方就没有办法拿回性能。这是一条通用的设计原则：用基本保证实现操作，强保证由调用方按需叠加。

## 移动构造函数为什么要 noexcept

### `vector` 扩容的复制与移动次数

`vector` 的容量用完后，要分配一块更大的存储，把旧元素搬过去。用移动构造函数搬比复制便宜，但移动到一半抛出时，前面的元素已经被移走，没法恢复，强保证就保不住了。

```cpp run title="realloc-counts.cpp" ok
#include <cstdio>
#include <type_traits>
#include <vector>

int copies, moves;

template<bool NoexceptMove, bool Copyable>
struct T {
  int v;
  T(int x) : v(x) {}
  T(const T& o) requires Copyable : v(o.v) { ++copies; }
  T(T&& o) noexcept(NoexceptMove) : v(o.v) { ++moves; }
};

template<class U>
void run(const char* name) {
  copies = moves = 0;
  std::vector<U> v;
  for (int i = 0; i < 1000; ++i) v.emplace_back(i);   // 只统计扩容时的搬运
  std::printf("%-26s copies=%4d moves=%4d\n", name, copies, moves);
}

int main() {
  run<T<true,  true >>("noexcept move");
  run<T<false, true >>("throwing move, copyable");
  run<T<false, false>>("throwing move, move-only");
}
```

本机 Clang 23 + libc++ 的输出：

```text
noexcept move              copies=   0 moves=1023
throwing move, copyable    copies=1023 moves=   0
throwing move, move-only   copies=   0 moves=1023
```

libc++ 的容量按 1、2、4、…、1024 翻倍增长，十次扩容一共搬运 1 + 2 + … + 512 = 1023 个元素。三种类型的差别只在搬运用的是复制还是移动：

- 移动构造函数是 `noexcept` 的：移动，强保证照样成立；
- 移动可能抛出，但可以复制：复制，出错时扔掉新存储即可，旧元素完好；
- 只能移动，而且移动可能抛出：只好移动，放弃强保证，这就是 [[vector.modifiers#2]] 第 3 层的效果未指定。

这个决策由 `std::move_if_noexcept` 编码（[[forward]]），它的返回类型是：

```cpp
conditional_t<!is_nothrow_move_constructible_v<T> && is_copy_constructible_v<T>,
              const T&, T&&>
```

返回 `const T&` 会选中复制构造函数，返回 `T&&` 会选中移动构造函数。

### 失败时看得见的差别

```cpp run title="realloc-failure.cpp" unspecified
#include <cstdio>
#include <vector>

int budget = 1000;                 // 剩余可成功的复制或移动次数
template<bool Copyable>
struct T {
  int v;
  T(int x) : v(x) {}
  T(const T& o) requires Copyable : v(o.v) { if (budget-- == 0) throw 0; }
  T(T&& o) : v(o.v) { if (budget-- == 0) throw 0; o.v = -1; }   // 没有 noexcept
};

template<class U> void test(const char* name) {
  std::vector<U> v;
  for (int i = 0; i < 4; ++i) v.emplace_back(i);   // size 4，capacity 4
  budget = 2;                                      // 扩容时第 3 次搬运抛出
  try { v.emplace_back(4); } catch (int) {}
  std::printf("%-10s size=%zu:", name, v.size());
  for (auto& e : v) std::printf(" %d", e.v);
  std::puts("");
}

int main() {
  test<T<true>>("copyable");     // 没有效果：标准保证
  test<T<false>>("move-only");   // 效果未指定
}
```

本机输出 `copyable   size=4: 0 1 2 3` 和 `move-only  size=4: -1 -1 2 3`。可复制的类型扩容失败后原样保留；只能移动的类型，前两个元素已经被移走，`vector` 里留下的是被移动过的对象。

### 怎样让移动构造函数是 noexcept

`std::is_nothrow_move_constructible_v<T>` 查询的是移动构造函数的异常说明，不看函数体。手写的移动构造函数不写 `noexcept`，就是潜在抛出的；隐式声明或 `= default` 的，异常说明由成员推导（[[except.spec#7]]）。

```cpp ok
#include <string>
#include <type_traits>
#include <utility>

struct A {                         // 全部隐式声明
  std::string s;
};
struct B {                         // 手写移动构造，忘了 noexcept
  std::string s;
  B(B&& o) : s(std::move(o.s)) {}
};
struct C {                         // = default：由成员推导
  std::string s;
  C(C&&) = default;
  ~C() {}                          // 析构函数没写说明：隐式 noexcept
};
struct D { B b; };                 // 成员 B 的移动可能抛出，D 也跟着

static_assert( std::is_nothrow_move_constructible_v<A>);
static_assert(!std::is_nothrow_move_constructible_v<B>);
static_assert( std::is_nothrow_move_constructible_v<C>);
static_assert(!std::is_nothrow_move_constructible_v<D>);
static_assert( std::is_nothrow_destructible_v<C>);
static_assert(!std::is_nothrow_copy_constructible_v<A>);  // 复制 string 要分配内存
```

`B` 的问题会传染：任何以 `B` 为成员的类，隐式的移动构造函数也潜在抛出，放进 `vector` 后扩容时同样被复制。能写 `= default` 的就写 `= default`，必须手写的移动操作，确认确实不会抛出后加上 `noexcept`。移动构造函数通常只是转移指针，本来就不会失败。

特殊成员函数什么时候被隐式声明、一个空析构函数怎样让移动变成复制，见 [[topics/special-members-and-elision]]。

!!! pitfall "`is_nothrow_move_constructible` 把析构也算进去"
    这个 trait 按 `T(std::declval<T>())` 这个表达式判断，表达式里有一个临时对象要析构。移动构造函数是 `noexcept` 的、析构函数是 `noexcept(false)` 的类型，本机 libc++ 上得到 `false`，`vector` 扩容时照样复制。这是已知的库问题 [[LWG2116]]，详见 [[except.spec]]。

!!! history "noexcept 的由来"
    C++98 的 `push_back` 已经提供强保证，扩容时复制元素。C++11 引入移动语义后发现，可能抛出的移动会破坏这个已有的保证（[[N2855]]）。最终方案（[[N3050]]）允许移动构造函数抛出，同时加入 `noexcept` 和 `move_if_noexcept`，让库在编译期区分两种情况。经过见 [[history/move-semantics]]。

## noexcept 说明符与 noexcept 运算符

同一个关键字有两种用法：

- **noexcept 说明符**写在函数声明末尾：`void f() noexcept;` 或 `void f() noexcept(条件);`。它规定函数的异常说明，即函数能不能以异常退出（[[except.spec#1]]）。
- **noexcept 运算符** `noexcept(表达式)` 是一个编译期的 `bool` 常量，表达式不求值。只要表达式里有潜在抛出的部分，比如调用了没标 `noexcept` 的函数，结果就是 `false`（[[expr.unary.noexcept#2]]）。

两者合在一起就是泛型代码里常见的 `noexcept(noexcept(...))`：外层是说明符，里层是运算符。包装类型的异常说明应当跟着被包装的类型走：

```cpp ok
#include <string>
#include <type_traits>
#include <utility>
#include <vector>

template<class T>
struct Wrapper {
  T value;
  Wrapper(Wrapper&& o) noexcept(std::is_nothrow_move_constructible_v<T>)
      : value(std::move(o.value)) {}
  friend void swap(Wrapper& a, Wrapper& b)
      noexcept(noexcept(std::swap(a.value, b.value))) {   // 说明符包着运算符
    std::swap(a.value, b.value);
  }
};

struct Slow { Slow(Slow&&); Slow& operator=(Slow&&); };   // 移动没有 noexcept

static_assert( std::is_nothrow_move_constructible_v<Wrapper<std::string>>);
static_assert(!std::is_nothrow_move_constructible_v<Wrapper<Slow>>);
static_assert( std::is_nothrow_swappable_v<Wrapper<std::vector<int>>>);
static_assert(!std::is_nothrow_swappable_v<Wrapper<Slow>>);
```

写成无条件的 `noexcept`，`Wrapper<Slow>` 移动时 `Slow` 一旦抛出，程序就终止；不写，`Wrapper<std::string>` 放进 `vector` 就会被复制。条件 `noexcept` 让两种情况都对。

不写说明符时，异常说明有几条默认规则（[[except.spec#4]]）：普通函数潜在抛出；析构函数和释放函数不抛出，除非某个子对象的析构函数潜在抛出（[[except.spec#8]]、[[except.spec#10]]）；隐式声明和首次声明即 `= default` 的特殊成员函数，按它会调用的函数推导（[[except.spec#7]]、[[except.spec#9]]）。

### noexcept 函数抛出时

编译器不检查 `noexcept` 函数里会不会抛出。异常真的离开 `noexcept` 函数时，程序调用 `std::terminate`（[[except.handle#7]]）。

```cpp run title="noexcept-terminate.cpp" impl
#include <cstdio>
#include <stdexcept>

struct Guard {
  const char* n;
  ~Guard() { std::fprintf(stderr, "~%s\n", n); }
};

void parse() { Guard g{"parse"}; throw std::runtime_error("bad input"); }
void handle() noexcept { Guard g{"handle"}; parse(); }

int main() {
  Guard g{"main"};
  try {
    handle();
  } catch (...) {
    std::fputs("caught\n", stderr);   // 永远不会执行
  }
}
```

本机 Clang 23（`-O0` 和 `-O2` 相同）的输出：

```text
~parse
libc++abi: terminating due to uncaught exception of type std::runtime_error: bad input
```

退出码 134，即 `SIGABRT`。`main` 里的 `catch (...)` 没有机会接住异常，`parse` 的局部对象析构了，`handle` 和 `main` 的没有。标准允许这种部分回溯：异常穿出 `noexcept` 函数时，调用 `std::terminate` 之前栈是回溯、部分回溯还是完全不回溯，由实现定义（[[except.terminate#2]]）。所以不能指望 `noexcept` 函数外层的析构函数做收尾，原因和实现细节见 [[except.special]]。

这也说明了 `noexcept` 的正确用法：只标在确实不会失败的函数上，或者失败就应当终止程序的函数上。一个内部调用了 `push_back` 的函数标成 `noexcept`，就等于决定内存不足时直接终止。

## 析构函数不应抛出

析构函数没写异常说明时默认不抛出（[[except.spec#8]]），里面的 `throw` 直接导致 `std::terminate`。显式写成 `noexcept(false)` 可以让异常传出去，但在栈回溯中析构时抛出，仍然终止程序（[[except.terminate#1.4]]）：

```cpp run title="throwing-dtor.cpp" ok
#include <cstdio>
#include <stdexcept>

struct Implicit {
  ~Implicit() { throw std::runtime_error("from ~Implicit"); }   // 隐式 noexcept
};
struct Explicit {
  ~Explicit() noexcept(false) { throw std::runtime_error("from ~Explicit"); }
};

int main(int argc, char**) {
  try {
    if (argc == 1) { Implicit a; }                 // 情形 1
    if (argc == 2) { Explicit b; }                 // 情形 2
    if (argc == 3) { Explicit c; throw 42; }       // 情形 3：回溯中析构 c
  } catch (const std::exception& e) {
    std::fprintf(stderr, "caught: %s\n", e.what());
  }
}
```

本机 Clang 23 对 `~Implicit` 给出 `-Wexceptions` 警告（"has a non-throwing exception specification but can still throw"）。三种情形的运行结果：

| 情形 | 输出 | 原因 |
|---|---|---|
| 1：隐式 `noexcept` 的析构函数抛出 | `terminating due to uncaught exception of type std::runtime_error: from ~Implicit` | 异常离开非抛出函数（[[except.handle#7]]） |
| 2：`noexcept(false)`，正常离开作用域 | `caught: from ~Explicit` | 异常照常传播 |
| 3：`noexcept(false)`，在回溯中抛出 | `terminating due to uncaught exception of type int` | 回溯中的析构以异常退出（[[except.terminate#1.4]]） |

情形 3 里同时有两个异常要传播，语言无法选择丢掉哪一个，只能终止。即使析构函数允许抛出，它也总得考虑自己正处于回溯之中的可能。再加上标准库调用的析构函数抛出是 UB（[[res.on.functions#2.4]]），以及前文说的成员的 `noexcept(false)` 析构函数会让外层类的移动构造在 trait 上变成可能抛出，结论只有一个：析构函数不要抛出。

析构函数里的操作确实可能失败时，比如关闭文件时刷新缓冲区出错，常见的做法是提供一个显式的 `close()` 让调用方处理错误，析构函数只做不会失败的兜底，失败时记录或忽略。析构函数体抛出时，成员和基类仍会照常析构，不会泄漏（[[except.ctor#3]]），但这不改变上面的结论。

## RAII 与 scope guard

RAII 把清理绑定在对象的析构上，所以清理在正常路径和异常路径上都会发生。`std::unique_ptr`、`std::lock_guard`、`std::fstream` 都是 RAII 类。没有现成的 RAII 类时，可以用一个 **scope guard**：构造时记下一个函数对象，析构时调用它。

有些清理只应当在失败时做，例如撤销已完成的前一步。区分正常离开和回溯离开，要用 `std::uncaught_exceptions()`：它返回当前线程中已经抛出、还没被 handler 接住的异常个数（[[uncaught.exceptions#1]]，{{c++17}}）。

```cpp run title="scope-fail.cpp" ok
#include <cstdio>
#include <exception>
#include <set>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

template<class F>
class ScopeFail {                  // 只在作用域因异常退出时运行 f
  F f_;
  int entry_ = std::uncaught_exceptions();
public:
  explicit ScopeFail(F f) : f_(std::move(f)) {}
  ScopeFail(const ScopeFail&) = delete;
  ScopeFail& operator=(const ScopeFail&) = delete;
  ~ScopeFail() { if (std::uncaught_exceptions() > entry_) f_(); }
};

std::vector<std::string> names;
std::set<int> ids;

void add_user(const std::string& name, int id) {
  names.push_back(name);                         // 第一步
  ScopeFail undo{[] { names.pop_back(); }};      // 第二步失败时撤销第一步
  if (!ids.insert(id).second)                    // 第二步
    throw std::invalid_argument("duplicate id");
}

int main() {
  add_user("ada", 1);
  try { add_user("bob", 1); } catch (const std::exception& e) { std::puts(e.what()); }
  std::printf("%zu names, %zu ids\n", names.size(), ids.size());
}
```

输出 `duplicate id` 和 `1 names, 1 ids`。`add_user` 因此有强保证：`push_back` 失败时什么都没做（[[container.reqmts#66]]）；`insert` 失败或抛出时 `undo` 运行，而 `pop_back` 不抛出。这正是前文的模式：每一步都可能失败，但撤销每一步的操作不会失败。

`ScopeFail` 比较的是构造时和析构时的计数，而不是检查计数是否大于 0。在另一个析构函数里（回溯期间）使用 `ScopeFail` 时，计数一开始就是 1，只看大于 0 会误判为失败，见 [[support.exception]] 的例子。C++17 之前只有返回 `bool` 的 `std::uncaught_exception()`，正好有这个缺陷，它在 C++20 被删除（[[N4152]]）。

标准库没有通用的 scope guard。Library Fundamentals TS 第 3 版提供了 `std::experimental::scope_exit`、`scope_fail`、`scope_success`，本机 libc++ 没有实现。

## 异常、错误码与 `expected`

异常适合失败概率低、需要跨越多层调用才能处理的错误，比如内存不足、配置文件损坏。调用方期望经常遇到的失败，比如解析用户输入，更适合放进返回值：`std::expected<T, E>` 要么持有结果，要么持有错误（[[expected]]，{{c++23}}）；`std::error_code` 适合与操作系统错误码对接（[[syserr]]）。

两种方式不互斥。即使函数用 `expected` 报告业务错误，它内部的 `std::string`、`std::vector` 仍然可能抛出 `bad_alloc`，本页的分析照样适用。

异常的运行时代价集中在抛出的那一刻：在 Itanium ABI 的表驱动实现下，不抛出的路径上没有额外指令，抛出一次要查表、两遍遍历栈，比普通返回慢几个数量级。`noexcept` 能让调用方省掉清理用的着陆点代码。实测数据和汇编见 [[toolchain/exception-implementation]]。

## 思考题

!!! question "1"
    `copy-and-swap.cpp` 的 `operator=` 标了 `noexcept`，可是 `a = b` 明明会分配内存，可能抛出 `bad_alloc`。这是否违反了 `noexcept` 的承诺？

<details markdown="1">
<summary>答案</summary>

没有违反。形参 `o` 的初始化发生在调用方，属于调用表达式 `a = b` 的一部分，不在 `operator=` 的函数体内（[[expr.call]]）。复制构造函数抛出时，异常从调用方的表达式里传出，从未进入 `operator=`，也就没有离开 `noexcept` 函数。

这也是 `is_nothrow_copy_assignable_v<Buffer>` 为 `false`、`is_nothrow_move_assignable_v<Buffer>` 为 `true` 的原因：noexcept 运算符看的是整个表达式，复制时包括了可能抛出的复制构造，移动时只有 `noexcept` 的移动构造。
</details>

!!! question "2"
    一个类的移动构造函数标了 `noexcept`，析构函数标了 `noexcept(false)`。`std::vector` 扩容时会移动还是复制它的元素？

<details markdown="1">
<summary>答案</summary>

本机 libc++ 上会复制。`vector` 按 `is_nothrow_move_constructible_v<T>` 选择，这个 trait 检查的表达式包含一个临时对象的析构，析构函数潜在抛出，结果就是 `false`（[[LWG2116]]）。在 4 个元素的 `vector` 上触发一次扩容，实测复制 4 次、移动 0 次。这又是析构函数不该抛出的一个理由。
</details>

!!! question "3"
    把 `scope-fail.cpp` 中两步的顺序反过来，先 `ids.insert` 再 `names.push_back`，`add_user` 还需要 `ScopeFail` 吗？

<details markdown="1">
<summary>答案</summary>

需要，只是撤销的对象变了。`push_back` 失败（分配失败）时要撤销已经成功的 `insert`，所以 guard 要在 `insert` 成功之后建立，内容是 `ids.erase(id)`。关联容器的 `erase(k)` 只在比较对象抛出时才抛出（[[associative.reqmts.except#1]]），`std::less<int>` 不抛出，所以撤销操作仍然不会失败。一般规律是：最后一步不需要撤销，前面每一步都需要一个不抛出的撤销操作。
</details>

## 小结

| 问题 | 结论 | 出处 |
|---|---|---|
| 异常传播时销毁什么 | 已构造完成的自动对象，按逆序析构 | [[except.ctor#2]] |
| 构造函数抛出 | 对象自己的析构函数不运行，已构造的子对象析构 | [[except.ctor#3]] |
| 构造函数的 function-try-block | 只能记录或翻译异常，末尾自动重新抛出 | [[except.handle#14]] |
| 标准库怎样说强保证 | "no effects" | [[container.reqmts#66]]、[[vector.modifiers#2]] |
| `push_back` 扩容 | 移动构造不抛出才移动，否则复制 | [[vector.modifiers#2]]、[[forward]] |
| 默认的异常说明 | 普通函数潜在抛出；析构函数不抛出；预置函数按成员推导 | [[except.spec#4]]、[[except.spec#7]]、[[except.spec#8]] |
| 异常离开 `noexcept` 函数 | `std::terminate`，回溯程度由实现定义 | [[except.handle#7]]、[[except.terminate#2]] |
| 析构函数在回溯中抛出 | `std::terminate` | [[except.terminate#1.4]] |
| 区分正常退出与回溯退出 | 比较构造时与析构时的 `uncaught_exceptions()` | [[uncaught.exceptions]] |
