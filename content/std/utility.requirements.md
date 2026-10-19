---
title: 对类型与表达式的要求
summary: 标准库对用户类型提出的 Cpp17 命名要求：比较（等价关系、严格弱序）、构造与赋值、析构不抛异常；可交换与两步式 swap；Cpp17NullablePointer；Cpp17Hash；Cpp17Allocator 及 allocator_traits 提供的默认值，以及让 vector 能用不完整类型实例化的分配器完整性要求。
status: done
covers: *
papers: N4510
related: constraints, structure.requirements, lib.types.movedfrom, alg.sorting, unord.hash, allocator.traits, container.requirements, namespace.constraints
tags: 库, 命名要求, swap, allocator, hash
updated: 2026-10-19
---

!!! tldr
    - Cpp17 命名要求（*Cpp17CopyConstructible*、*Cpp17Hash* 等）是用文字写的要求，编译器不检查其中的语义。类型不满足它们，程序有未定义行为。
    - 比较器必须是严格弱序。把 `<` 写成 `<=` 会让 `std::sort` 越界读写，而编译器不会报错。
    - 被移动的对象状态未指明，但必须仍能满足库的要求，自移动赋值也一样；析构函数不得抛出异常。
    - 交换在两步式的上下文中进行：候选集包括 `std::swap` 和 ADL 找到的 `swap`。泛型代码里用 `using std::swap; swap(a, b);` 或 `std::ranges::swap`。
    - 自定义分配器只需提供 `value_type`、`allocate`、`deallocate`、转换构造函数和 `==`，其余成员由 `allocator_traits` 补上默认值。

把自己的类型交给标准库时，例如放进容器、交给算法、用作哈希函数或分配器，库就对这个类型提出了要求。C++20 以后的新组件多用概念表达这些要求（`std::regular`、`std::sortable`…），但容器、经典算法、`unique_ptr`、无序容器等大量组件仍然用本节定义的 **Cpp17 命名要求**（[[g:cpp17-named-requirement]]）描述。

两者的区别在于检查。概念的语法部分由编译器检查；Cpp17 要求完全是文字，不满足时编译器多半不会报错，后果是未定义行为（[[res.on.functions#2.3]]）。

## 读这些表的记号（[utility.arg.requirements] ¶1）

¶1 本节的要求都写成表格：一列表达式，一列返回类型，一列语义要求或后置条件。表里的字母有固定含义：

| 记号 | 含义 |
|---|---|
| `T` | 程序提供的、用来实例化库模板的对象类型或引用类型 |
| `a`、`b`、`c` | 类型为 `T` 或 `const T` 的值 |
| `s`、`t` | `T` 类型的可修改左值 |
| `u` | 正在声明的变量名 |
| `rv` | `T` 类型的右值 |
| `v` | `T` 或 `const T` 类型的左值，或者 `const T` 类型的右值 |

表格只要求表达式有效并具有规定的语义，不规定怎样实现，比如 `==` 是成员还是非成员都可以（[[structure.requirements#3]]）。

## 比较：等价关系与严格弱序（表 28、29）

```cpp ub
#include <algorithm>
#include <vector>
int main() {
  std::vector<int> v(100, 1);
  std::sort(v.begin(), v.end(), [](int a, int b) { return a <= b; });
  // UB：<= 不是严格弱序（a <= a 为真）
}
```

这不只是理论上的问题。快速排序的分区循环靠比较结果停止扫描，`<=` 可能让扫描越过数组边界。本机用 libc++ 加 `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_DEBUG` 编译运行，程序报告 "Would read out of bounds, does your comparator satisfy the strict-weak ordering requirement?" 并终止。

| 要求 | 表达式 | 语义 |
|---|---|---|
| *Cpp17EqualityComparable* | `a == b` | `==` 是**等价关系**：自反（`a == a`）、对称、传递 |
| *Cpp17LessThanComparable* | `a < b` | `<` 是严格弱序（[[alg.sorting]]） |

两者的返回类型都要建模 *boolean-testable*（[[g:boolean-testable]]）：结果能转换为 `bool`，`!` 作用于它也能得到可转换为 `bool` 的结果。这排除了 `!`、`&&` 被重载成奇怪行为的类型。

**严格弱序**（[[g:strict-weak-ordering]]）是排序和有序关联容器的基础。它要求 `<` 非自反（`!(a < a)`）、传递，并且不可比较关系（`!(a < b) && !(b < a)`）是一个等价关系。常见的违反有：用 `<=` 作比较器；比较含 NaN 的浮点数；按多个字段比较时写错了先后逻辑，例如 `a.x < b.x || a.y < b.y`。

!!! lawyer "double 满足这些要求吗"
    NaN 让 `double` 的 `==` 不自反，`<` 也不构成严格弱序，所以按字面 `double` 类型不满足表 28、29。通常的理解是要求针对实际参与运算的值：对不含 NaN 的范围排序是良定义的，含 NaN 则是 UB。概念那一侧，[[structure.requirements#8]] 明确说必需的操作不必是全函数，把这一点写成了规范。

## 构造、赋值与析构（表 30–35）

| 要求 | 表达式 | 后置条件 |
|---|---|---|
| *Cpp17DefaultConstructible*（表 30） | `T t;` | `t` 被默认初始化 |
| | `T u{};`、`T()`、`T{}` | 值初始化或聚合初始化 |
| *Cpp17MoveConstructible*（表 31） | `T u = rv;`、`T(rv)` | 结果等于 `rv` 构造前的值；`rv` 的状态未指明 |
| *Cpp17CopyConstructible*（表 32） | `T u = v;`、`T(v)` | 结果等于 `v`；`v` 不变 |
| *Cpp17MoveAssignable*（表 33） | `t = rv`，返回 `T&` 即 `t` | 若 `t` 和 `rv` 不是同一对象，`t` 等于 `rv` 赋值前的值；`rv` 的状态未指明 |
| *Cpp17CopyAssignable*（表 34） | `t = v`，返回 `T&` 即 `t` | `t` 等于 `v`；`v` 不变 |
| *Cpp17Destructible*（表 35） | `a.~T()` | 没有异常传播出来 |

表 32 和表 34 是在表 31、表 33 之外追加的要求，所以 *Cpp17CopyConstructible* 包含 *Cpp17MoveConstructible*。

### 要求的是表达式，不是成员函数

```cpp error
#include <vector>
struct M {
  M() = default;
  M(const M&) = default;
  M(M&&) = delete;   // 显式删除移动构造函数
};
int main() {
  std::vector<M> v;
  M m;
  v.push_back(m);   // error：扩容时需要用右值构造 M
}
```

表 31 要求 `T u = rv;` 有效，并不要求 `T` 有移动构造函数。只有拷贝构造函数的类型也满足它，因为右值可以绑定到 `const T&`。

反过来，显式删除移动构造函数的类型 `M` 两个要求都不满足。被删除的函数仍然参与重载决议，`M u = rv;` 会选中它，于是非良构。本机 libc++ 报告 "The specified type does not meet the requirements of Cpp17MoveInsertable"。所以不想要移动语义时，应该不声明移动构造函数，而不是删除它；不声明时右值会退回到拷贝构造函数。

### 语义部分编译器不检查

"等于"是语义要求：拷贝之后两个对象相等。C++98 的 `std::auto_ptr` 在拷贝时偷偷转移所有权，语法上满足表 32，语义上不满足，把它放进容器就是 UB。这是 `auto_ptr` 被弃用、最终被移除的根本原因。

### 被移动的对象（表 31、33 的注）

表 31 的注 1 和表 33 的注 2 说，`rv` 被移动之后虽然状态未指明，但仍必须满足使用它的库组件的要求，那些要求中列出的操作必须照常工作。容器和算法会对被移动过的对象赋值、析构，有时还会比较。

注 2 还特意写了无论 `t` 和 `rv` 是否为同一个对象。这决定了自移动赋值 `x = std::move(x)` 的要求：`x` 的值可以是任何东西（值的后置条件只在两者不同时才成立），但 `x` 必须仍是一个可用的对象。标准库类型自己的行为见 [[lib.types.movedfrom#2]]。

### 析构不得抛出异常

表 35 要求析构时没有异常传播出来，这与 [[res.on.functions#2.4]] 一致：容器元素的析构函数抛出异常是 UB。C++11 起析构函数默认是 `noexcept`（[[except.spec]]），只有显式写 `noexcept(false)` 才会触及这一条。注 3 补充，数组类型和非对象类型都不满足 *Cpp17Destructible*。

## 可交换 [swappable.requirements]

```cpp run ok
#include <string>
#include <type_traits>
#include <utility>
namespace lib {
  struct Widget { std::string name; };
  void swap(Widget& a, Widget& b) noexcept { a.name.swap(b.name); }
}
static_assert(std::is_nothrow_swappable_v<lib::Widget>);
int main() {
  lib::Widget a{"a"}, b{"b"};
  std::swap(a, b);          // 限定调用：绕过 lib::swap，做三次移动
  using std::swap;
  swap(a, b);               // 两步式：ADL 找到 lib::swap
  std::ranges::swap(a, b);  // C++20：内部替你做两步式
  return a.name == "b" ? 0 : 1;
}
```

¶1 设 `t` 是 `T` 类型的表达式，`u` 是 `U` 类型的表达式。

¶2 当且仅当下面两条成立时，称 `t` **可与 `u` 交换**（[[g:swappable-with]]，swappable with）：

- ¶2.1 在下面规定的上下文中，`swap(t, u)` 和 `swap(u, t)` 都有效；
- ¶2.2 它们的效果是交换两者的值：`t` 指代的对象得到 `u` 原来的值，`u` 指代的对象得到 `t` 原来的值。

¶3 求值 `swap(t, u)` 的上下文必须保证：对一个候选集做重载决议，选出名为 `swap` 的二元非成员函数。候选集包括 `<utility>` 中的两个 `swap` 函数模板（单个对象的和数组的，¶3.1），以及实参依赖查找（ADL）找到的函数（¶3.2）。

这就是**两步式**（[[g:swap-two-step]]）：`using std::swap;` 把 `std::swap` 放进候选集，非限定调用 `swap(a, b)` 再由 ADL 加入用户自己的 `swap`。[[contents#3]] 规定，库说明中出现的非限定 `swap` 调用都在这个上下文中求值，所以 `std::sort` 交换元素时会用上你在类型所在命名空间里定义的 `swap`。libc++ 的 `std::iter_swap` 函数体就是一句非限定的 `swap(*__a, *__b);`：它本身在 `std` 里，普通查找找到 `std::swap`，ADL 再加入用户的版本。

注 1 指出，`T`、`U` 都是基础类型或其数组时，这个候选集就等于限定调用 `std::swap(t, u)` 的查找结果。注 2 说，有可交换要求的库组件是否自己包含 `<utility>`，是未指明的。

在上面这些定义的基础上：

- ¶4 当且仅当右值（或左值）`t` 可与任何 `T` 类型的右值（或左值）交换时，`t` 是**可交换的**（swappable）。
- ¶5 `X` 类型的左值可交换时，`X` 满足 ***Cpp17Swappable***。
- ¶6 满足某种迭代器要求的类型 `X`，如果对任何可解引用的 `x`，`*x` 都可交换，就满足 ***Cpp17ValueSwappable***。`std::iter_swap`、`std::reverse` 等算法用的就是它。

¶7 例 1 演示了用户代码怎样在正确的上下文中调用 `swap`，其中包括不同类型之间的交换：`N::A` 和代理类型 `N::Proxy`。它同时定义了 `swap(A&, Proxy)` 和 `swap(Proxy, A&)`，后者只是为了满足 ¶2.1 要求的对称性。

C++20 起推荐用 `std::ranges::swap`。它是一个[[g:customization-point-object|定制点对象]]，内部完成两步式，找不到用户的 `swap` 时退回到移动交换。

## *Cpp17NullablePointer* [nullablepointer.requirements]

```cpp run ok
#include <cstddef>
#include <cstdio>
#include <memory>

struct Fd {                                    // 文件描述符句柄
  int fd = -1;                                 // 值初始化得到空值
  Fd() = default;
  Fd(std::nullptr_t) noexcept {}
  Fd(int f) noexcept : fd(f) {}
  explicit operator bool() const noexcept { return fd != -1; }
  friend bool operator==(Fd, Fd) = default;
  friend bool operator==(Fd a, std::nullptr_t) noexcept { return a.fd == -1; }
};

struct FdCloser {
  using pointer = Fd;                          // unique_ptr 用它作为指针类型
  void operator()(Fd f) const noexcept { std::printf("close(%d)\n", f.fd); }
};

int main() {
  std::unique_ptr<int, FdCloser> p(Fd{3});     // 析构时输出 close(3)
  std::unique_ptr<int, FdCloser> q;            // 空：析构时不调用删除器
  return p && !q ? 0 : 1;
}
```

`std::unique_ptr<T, D>` 管理的不一定是指针：如果删除器 `D` 定义了 `pointer` 类型，`unique_ptr` 就存储这个类型的对象。上例用它来管理文件描述符。这个类型要满足的就是 *Cpp17NullablePointer*。

¶1 ***Cpp17NullablePointer*** 类型是支持空值的类指针类型。类型 `P` 要满足它，需要：

- ¶1.1 满足 *Cpp17EqualityComparable*、*Cpp17DefaultConstructible*、*Cpp17CopyConstructible*、*Cpp17CopyAssignable*、*Cpp17Swappable* 和 *Cpp17Destructible*；
- ¶1.2 表 36 中的表达式有效且具有规定的语义；
- ¶1.3 满足本小节的其他要求。

¶2 值初始化的 `P` 对象就是这个类型的空值，空值只与自身相等。默认初始化的 `P` 对象可能具有不确定值或错误值；注 1 提醒，使用前者可能是 UB，使用后者可能是错误行为（[[basic.indet]]）。

¶3 `P` 可以按语境转换为 `bool`，效果如同求值 `p != nullptr`。

¶4 *Cpp17NullablePointer* 要求中的任何操作都不得以异常退出。

¶5 表 36 中，`t` 是 `P` 的非 const 左值，`a`、`b` 是 `P` 的值，`np` 是 `std::nullptr_t` 的值：

| 表达式 | 语义 |
|---|---|
| `P u(np);`、`P u = np;`、`P(np)` | 结果等于 `nullptr` |
| `t = np` | 返回 `P&`；之后 `t == nullptr` |
| `a != b` | `!(a == b)` |
| `a == np`、`np == a` | `a == P()` |
| `a != np`、`np != a` | `!(a == np)` |

C++20 的运算符重写规则让上例只需定义两个 `operator==`，`!=` 和 `np == a` 都能自动得到。除了 `unique_ptr::pointer`，分配器的各种指针类型（[[allocator.requirements.general#92]]）和 `std::exception_ptr` 也满足这个要求。

## *Cpp17Hash* [hash.requirements]

```cpp run ok
#include <cstddef>
#include <functional>
#include <unordered_set>

struct Point {
  int x, y;
  bool operator==(const Point&) const = default;
};

template<> struct std::hash<Point> {   // 允许：依赖程序定义的类型
  std::size_t operator()(const Point& p) const noexcept {
    std::size_t h = std::hash<int>{}(p.x);
    return h ^ (std::hash<int>{}(p.y) + 0x9e3779b9 + (h << 6) + (h >> 2));
  }
};

int main() {
  std::unordered_set<Point> s{{1, 2}, {3, 4}, {1, 2}};
  return s.size() == 2 ? 0 : 1;
}
```

为自己的类型提供哈希，通常是特化 `std::hash`，这是 [[namespace.std#2]] 明确允许的。特化出来的类型要满足 *Cpp17Hash*。

¶1 类型 `H` 满足 ***Cpp17Hash***，需要它是函数对象类型（[[function.objects]]），满足 *Cpp17CopyConstructible* 和 *Cpp17Destructible*，并且表 37 中的表达式有效且具有规定的语义。

¶2 表 37 中，`Key` 是 `H` 的实参类型，`h` 是 `H` 的值，`u` 是 `Key` 类型的左值，`k` 是可以转换为 `Key` 的值：

| 表达式 | 返回类型 | 要求 |
|---|---|---|
| `h(k)` | `size_t` | 返回值只取决于 `k`，在程序运行期间不变；对不同的值 `t1`、`t2`，`h(t1) == h(t2)` 的概率应当非常小，接近 `1.0 / numeric_limits<size_t>::max()` |
| `h(u)` | `size_t` | 不得修改 `u` |

这张表有三点值得注意：

- 注 1 说得更明确：结果只在程序的一次执行内保持一致。不同的运行之间哈希值可以变化，实现可以用随机种子抵御哈希洪水攻击。本机 libc++ 的 `std::hash<std::string>` 目前是确定的，但把 `std::hash` 的结果写进文件或通过网络传输是不可移植的。
- 碰撞概率低用的是 should，只是建议。libc++ 和 libstdc++ 的 `std::hash<int>` 都是恒等函数，不同的值从不碰撞，但低位分布对某些输入（例如全是 8 的倍数）很差，这两个实现的无序容器靠质数个桶缓解这个问题。
- 表 37 没有要求相等的键哈希值相等。那是无序容器对 `Hash` 与 `Pred` 组合提出的要求（[[unord.req]]），属于另一层。

`std::hash` 的哪些特化是启用的、被禁用的特化有什么性质，见 [[unord.hash]]。

## *Cpp17Allocator* [allocator.requirements]

### 最小的分配器

```cpp run ok
#include <cstddef>
#include <cstdio>
#include <new>
#include <vector>

template<class T>
struct Counting {
  using value_type = T;
  static inline std::size_t allocs = 0;
  Counting() = default;
  template<class U> Counting(const Counting<U>&) noexcept {}
  T* allocate(std::size_t n) {
    ++allocs;
    return static_cast<T*>(::operator new(n * sizeof(T)));
  }
  void deallocate(T* p, std::size_t n) noexcept {
    ::operator delete(p, n * sizeof(T));
  }
  template<class U>
  bool operator==(const Counting<U>&) const noexcept { return true; }
};

int main() {
  std::vector<int, Counting<int>> v;
  for (int i = 0; i < 100; ++i) v.push_back(i);
  std::printf("allocations: %zu\n", Counting<int>::allocs);   // 本机 libc++ 输出 8
}
```

¶1 **分配器**（allocator）是封装了一种分配模型的类类型对象：用什么指针类型、指针差值和对象大小用什么类型，以及在这种模型下怎样分配和释放内存。所有字符串类型、除 `array` 和 `inplace_vector` 以外的容器、字符串流和 `match_results` 都以分配器为参数。

¶3 容器不直接使用分配器，而是通过类模板 `allocator_traits`（[[allocator.traits]]）访问它。如果某个要求规定了默认值，它就是可选的：分配器不提供时，`allocator_traits` 用默认值代替。注 1 说明，程序不能特化 `allocator_traits`。

所以上面的 `Counting` 只写了五样东西：`value_type`、`allocate`、`deallocate`、从 `Counting<U>` 转换的构造函数、`==`。`pointer`、`rebind`、`construct`、`propagate_on_container_*` 等都由 `allocator_traits` 补上。libc++ 用检测成员是否存在的方式实现这些默认值，例如 `pointer` 先找 `_Alloc::pointer`，找不到就用 `T*`。

¶98 例 2 给出的最小接口正是这五样。¶99 用一个说明专用的概念 *simple-allocator* 表达了同样的最小要求：`allocate` 的结果解引用得到 `value_type&`，能 `deallocate`，可拷贝构造，可以用 `==` 比较。满足本小节要求的类型就建模这个概念。较新的组件会引用它，例如 `std::execution` 的 `get_allocator` 查询（[[exec.get.allocator]]）。

### 要求一览（¶4–¶91）

¶2 定义了表中的记号：`X` 是 `T` 的分配器类型，`Y` 是对应的 `U` 的分配器类型，`XX` 是 `allocator_traits<X>`；`a`、`a1`、`a2` 是 `X` 的左值，`b` 是 `Y` 的值；`p` 是 `a1.allocate` 返回的指针（`a1 == a`）；`n` 是 `XX::size_type` 的值。

| 表达式 | 结果或语义 | 默认值 |
|---|---|---|
| `X::value_type` | 与 `T` 相同 | 必须提供 |
| `X::pointer` | | `T*` |
| `X::const_pointer`、`void_pointer`、`const_void_pointer` | `pointer` 能转换为它们 | 由 `pointer_traits` 的 `rebind` 得到 |
| `X::size_type` | 无符号整数，能表示最大对象的大小 | `make_unsigned_t<difference_type>` |
| `X::difference_type` | 有符号整数，能表示任意两个指针之差 | `pointer_traits<pointer>::difference_type` |
| `X::rebind<U>::other` | `Y` | 把 `SomeAllocator<T, Args>` 换成 `SomeAllocator<U, Args>` |
| `a.allocate(n)` | 为 `n` 个 `T` 的数组分配内存 | 必须提供 |
| `a.allocate_at_least(n)` {{c++23}} | 返回 `{ptr, count}`，`count >= n` | `{a.allocate(n), n}` |
| `a.deallocate(p, n)` | 释放；不抛异常 | 必须提供 |
| `a.max_size()` | 能有意义地传给 `allocate` 的最大 `n` | `numeric_limits<size_type>::max() / sizeof(value_type)` |
| `a1 == a2` | 一方分配的内存能否由另一方释放；不抛异常 | 必须提供 |
| `X u(b);` | 从 `Y` 转换构造，`Y(u) == b` 且 `u == X(b)`；不抛异常 | 必须提供 |
| `X u(a);`、`X u(std::move(a));` | `u == a`；不抛异常 | |
| `a.construct(c, args...)`、`a.destroy(c)` | 在 `c` 处构造或销毁对象 | `construct_at`、`destroy_at` |
| `a.select_on_container_copy_construction()` | 拷贝容器时新容器用的分配器 | `return a;` |
| `X::propagate_on_container_copy_assignment` 等三项 | 容器拷贝赋值、移动赋值、交换时，分配器是否随之传递 | `false_type` |
| `X::is_always_equal` | 任意两个 `X` 是否总是相等 | `is_empty<X>::type` |

下面几项的含义值得展开。

¶36 `allocate` 不只是分配内存，还会**创建一个 `n` 个 `T` 的数组对象**，只是不构造其中的元素。指针算术只在数组对象内有定义（[[expr.add]]），有了这句话，容器在分配的内存里做 `p + i` 才是合法的。例 1 给出了复用存储时的写法：`launder(reinterpret_cast<T*>(new (p) byte[n * sizeof(T)]))` 可以隐式创建合适的数组对象并得到指向它的指针（[[intro.object]]）。

¶48 `deallocate` 的前置条件很严格：`p` 必须来自 `allocate`，`n` 必须等于当初传给 `allocate` 的值；如果来自 `allocate_at_least`，`n` 可以在请求的数量和实际得到的 `count` 之间。分配器因此不必记录每块内存的大小，`std::allocator` 可以直接调用带大小的 `operator delete(void*, size_t)`。

¶54 分配器相等的意思不是两个对象一模一样，而是**一方分配的内存可以由另一方释放**。无状态的分配器总是相等；`std::pmr::polymorphic_allocator` 在指向同一个内存资源时相等。相等性决定了容器移动赋值时能否直接接管对方的内存：分配器不相等、又不随赋值传递时，只能逐个元素移动。

¶80–¶91 三个 `propagate_on_container_*` 决定分配器是否随容器的内容一起拷贝、移动或交换，默认都是 `false_type`，即容器赋值后保留自己原来的分配器。`std::pmr::polymorphic_allocator` 没有改变这三个默认值，它的设计就是分配器不随数据走。`is_always_equal` 默认取 `is_empty<X>`：没有数据成员的分配器不可能有状态，必然总是相等。

### 花式指针（¶92–¶95）

¶92 分配器类型必须满足 *Cpp17CopyConstructible*。它的四种指针类型必须满足 *Cpp17NullablePointer*，其构造、比较、拷贝、移动、交换操作都不得抛出异常。`pointer` 和 `const_pointer` 还必须满足 *Cpp17RandomAccessIterator*，并且指向的元素必须连续：`p` 和 `p + n` 都可解引用时，`addressof(*(p + n)) == addressof(*p) + n`。

这些要求是为**花式指针**（[[g:fancy-pointer]]，fancy pointer）准备的，也就是不是内置指针的指针类型。典型的例子是共享内存里使用的偏移量指针，例如 `boost::interprocess::offset_ptr`：它存储的是相对于自身地址的偏移，同一份数据结构可以映射到不同进程的不同地址上。容器内部因此必须始终使用 `allocator_traits<A>::pointer`，不能偷偷换成裸指针保存。

¶93 定义了**等值**（[[g:equivalently-valued]]，equivalently-valued）：两个指针值只用这四种指针类型之间的 `static_cast` 都转换成 `const_pointer` 之后比较相等。¶94、¶95 规定，`void_pointer` 之间的比较，以及 `pointer` 之间的比较和相减，都可以把任一方换成等值的 `const` 版本而不改变语义。

### 分配器可以拒绝某些类型（¶96、¶97）

¶96 分配器可以限制能用哪些类型实例化它，以及 `construct`、`destroy` 能接受哪些实参。类型不能与某个分配器一起使用时，分配器类本身或对 `construct` / `destroy` 的调用可能无法实例化。

¶97 分配器不支持某个过对齐类型要求的对齐时，用这个类型实例化分配器可能失败，分配器也可能悄悄忽略这个对齐要求；注 4 补充，`allocate` 还可能抛出 `bad_alloc`。所以把 `alignas(64)` 的类型放进使用自定义分配器的容器时，对齐能否得到保证取决于分配器。`std::allocator` 使用 C++17 的带对齐 `operator new`，会遵守对齐要求。

### 分配器完整性要求 [allocator.requirements.completeness]

```cpp run ok
#include <list>
#include <vector>
struct Node {
  int value;
  std::vector<Node> children;   // OK：此处 Node 还不完整
  std::list<Node> siblings;     // 同上
};
int main() {
  Node n{1, {}, {}};
  n.children.push_back({2, {}, {}});
  return n.children.size() == 1 ? 0 : 1;
}
```

¶1 设 `X` 是 `T` 的分配器类型。如果不论 `T` 是否完整，`X` 都是完整类型（¶1.1），并且 `allocator_traits<X>` 除 `value_type` 以外的成员类型也都是完整类型（¶1.2），就说 `X` 满足**分配器完整性要求**（[[g:allocator-completeness-requirements]]）。

这条要求是 C++17 允许 `vector`、`list`、`forward_list` 以不完整类型实例化的基础（[[N4510]]）。这几个容器的条款规定：分配器满足完整性要求时，实例化容器时 `T` 可以不完整，只要在使用某些成员之前变得完整。`std::allocator` 满足这一要求，所以上例这种递归的数据结构可以直接写。

`std::map<K, Node>`、`std::deque<Node>`、`std::unordered_map` 等没有这样的许可，用不完整类型实例化它们是 UB（[[res.on.functions#2.5]]），尽管实践中常常也能编译。

## 常见误解

!!! pitfall "泛型代码里写 `std::swap(a, b)`"
    限定调用会绕过用户为自己类型定制的 `swap`，失去它的效率和 `noexcept`。泛型代码应该用两步式或 `std::ranges::swap`。

!!! pitfall "有状态分配器的 `==` 总返回 true"
    `==` 的含义是能否互相释放内存。如果两个分配器实际上不能互相释放，`==` 却返回 `true`，容器在移动赋值、`swap`、`splice` 时就会把内存交给错误的分配器释放，这是 UB。

## 思考题

!!! question "思考题 1"
    一个分配器的 `is_always_equal` 是 `true_type`，`propagate_on_container_move_assignment` 是 `false_type`。`std::vector<T, A>` 的移动赋值复杂度是多少？会抛出异常吗？

<details markdown="1">
<summary>答案</summary>

分配器总是相等，目标容器的分配器就能释放源容器的内存，所以移动赋值可以直接接管源容器的缓冲区：除了销毁目标原有元素的线性时间，只需常数时间，不需要逐个移动元素，也不会抛出异常。标准中 `vector` 移动赋值的异常说明正是 `noexcept(allocator_traits<A>::propagate_on_container_move_assignment::value || allocator_traits<A>::is_always_equal::value)`（[[vector.overview]]）。

如果两者都是 `false`，而且两个分配器在运行时不相等，容器就只能把元素逐个移动构造到自己的存储里，需要线性时间，并且可能抛出异常。
</details>

!!! question "思考题 2"
    一个类型的 `operator<` 只比较 `x` 字段，`operator==` 比较 `x` 和 `y` 两个字段。把它放进 `std::set` 有问题吗？

<details markdown="1">
<summary>答案</summary>

`<` 本身仍然是严格弱序：只看 `x` 时，非自反、传递都成立，不可比较关系就是 `x` 相等，它是等价关系。所以 `std::set` 的行为是良定义的。

问题在于 `std::set` 只用 `<` 判断两个元素是否相同：`x` 相同、`y` 不同的两个对象被视为同一个元素，后插入的会被拒绝。这与类型自己的 `==` 不一致，容易让人误解，但不是 UB。
</details>
