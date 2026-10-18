---
title: 对类型与表达式的要求
summary: 库对用户类型提出的"命名要求"：Cpp17EqualityComparable / LessThanComparable / DefaultConstructible / MoveConstructible / CopyConstructible / MoveAssignable / CopyAssignable / Destructible 八张表；"可与……交换"与两步式 swap；Cpp17NullablePointer（可作 unique_ptr::pointer 的类指针类型）；Cpp17Hash；Cpp17Allocator 的完整要求与 allocator_traits 的默认值，以及允许不完整类型的分配器完整性要求。
status: done
covers: *
papers: N4510
related: description, structure.requirements, res.on.functions, res.on.requirements, lib.types.movedfrom, conventions, alg.sorting, unord.hash, allocator.traits, container.requirements, basic.indet
tags: 库, 命名要求, swap, allocator, hash
updated: 2026-10-18
---

当你把自己的类型交给标准库——放进容器、传给算法、作为 `unique_ptr` 的指针类型、作为哈希函数、作为分配器——库就对你的类型提出了要求。C++20 之后，新组件的要求多用**概念**表达（`std::regular`、`std::sortable`……），但大量经典组件（容器、迭代器算法、`unique_ptr`、无序容器……）仍然用本节定义的 **Cpp17 命名要求**（[[structure.requirements#5]]）来描述。

两者的关键区别：概念会被编译器检查（至少语法部分），而 Cpp17 要求**纯粹是文字**——不满足时编译器多半不报错，后果是 UB（[[res.on.functions#2.3]]）。所以必须读懂这些表格。

[utility.requirements.general] ¶1 是导航：[utility.arg.requirements] 讲实例化库模板所用的类型与表达式；[swappable.requirements] 讲可交换；[nullablepointer.requirements] 讲支持空值的类指针类型；[hash.requirements] 讲哈希函数对象；[allocator.requirements] 讲存储分配器。

## 模板实参要求（[utility.arg.requirements]）

### 记号约定（¶1）

¶1 标准库模板定义引用了表 28–35 中详细给出的各种命名要求。在这些表中：

| 记号 | 含义 |
|---|---|
| `T` | 由实例化模板的程序提供的**对象类型或引用类型** |
| `a`、`b`、`c` | （可能带 const 的）`T` 类型的值 |
| `s`、`t` | `T` 类型的可修改左值 |
| `u` | 一个标识符（正在声明的变量名） |
| `rv` | `T` 类型的右值 |
| `v` | （可能带 const 的）`T` 类型的左值，或 `const T` 类型的右值 |

这些表都是"**表达式 + 返回类型 + 要求/后置条件**"的形式。正如 [[structure.requirements#3]] 所说，它们只要求表达式**有效**且有指定的**语义**，不要求以特定方式（成员/非成员）实现。

### 比较类要求（表 28、29）

**表 28 *Cpp17EqualityComparable***：

| 表达式 | 返回类型 | 要求 |
|---|---|---|
| `a == b` | `decltype(a == b)` 建模 *boolean-testable* | `==` 是**等价关系**：自反（`a == a`）、对称、传递 |

**表 29 *Cpp17LessThanComparable***：

| 表达式 | 返回类型 | 要求 |
|---|---|---|
| `a < b` | `decltype(a < b)` 建模 *boolean-testable* | `<` 是**严格弱序**关系（[[alg.sorting]]） |

*boolean-testable* 是 [concept.booleantestable] 中的说明性概念：可以转换为 `bool`，且 `!` 运算也能产生可转换为 `bool` 的结果——它排除了那些"返回值能转成 `bool`、但 `!` 或 `&&` 被重载得古怪"的类型。

**严格弱序**是一切排序和有序关联容器的基础：非自反（`!(a < a)`）、传递，且"不可比较"（`!(a < b) && !(b < a)`）是等价关系。最常见的违反是用 `<=` 作比较器：

```cpp ub
#include <algorithm>
#include <vector>
int main() {
  std::vector<int> v(100, 1);
  std::sort(v.begin(), v.end(), [](int a, int b) { return a <= b; });
  // UB：<= 不是严格弱序（a <= a 为真，违反非自反性）
}
```

这不是理论上的 UB：快速排序的分区循环依赖"哨兵"元素停止扫描，`<=` 会让扫描越过数组边界。本机 libc++ 以 `_LIBCPP_HARDENING_MODE_DEBUG` 编译运行，报告 "Would read out of bounds, does your comparator satisfy the strict-weak ordering requirement?" 并终止；debug 模式下 libc++ 还会在排序后抽查比较器是否构成严格弱序（`__debug_utils/strict_weak_ordering_check.h`）。

!!! lawyer "浮点数满足这些要求吗？"
    `double` 的 `==` 在 NaN 上不自反，`<` 在 NaN 上不构成严格弱序。按表 28/29 的字面，`double` **类型**并不满足 *Cpp17EqualityComparable* / *Cpp17LessThanComparable*。实践中的理解是：要求针对的是**实际参与运算的值**——对不含 NaN 的范围排序是良定义的，含 NaN 则是 UB。概念那一侧，[[structure.requirements#8]] 明确说"必需操作不必是全函数"，把这一点写成了规范。

### 构造与赋值类要求（表 30–34）

**表 30 *Cpp17DefaultConstructible***：

| 表达式 | 后置条件 |
|---|---|
| `T t;` | 对象 `t` 被**默认初始化** |
| `T u{};` | 对象 `u` 被**值初始化**或**聚合初始化** |
| `T()`、`T{}` | 一个 `T` 类型对象被值初始化或聚合初始化 |

注意 `T t;` 对 `int` 是合法的（默认初始化，值不确定或错误值，[[basic.indet]]），所以 `int` 满足 *Cpp17DefaultConstructible*——要求只是"能这样写"，不要求得到确定的值。

**表 31 *Cpp17MoveConstructible***：

| 表达式 | 后置条件 |
|---|---|
| `T u = rv;` | `u` 等价于构造前 `rv` 的值 |
| `T(rv)` | `T(rv)` 等价于构造前 `rv` 的值 |
| | `rv` 的状态是**未指明**的 |

Note 1：`rv` 仍然必须满足使用它的库组件的要求；无论 `rv` 是否被移动过，那些要求中列出的操作都必须按规定工作。

**表 32 *Cpp17CopyConstructible***（在 *Cpp17MoveConstructible* 之外）：

| 表达式 | 后置条件 |
|---|---|
| `T u = v;` | `v` 的值不变，且等价于 `u` |
| `T(v)` | `v` 的值不变，且等价于 `T(v)` |

**表 33 *Cpp17MoveAssignable***：

| 表达式 | 返回类型 | 返回值 | 后置条件 |
|---|---|---|---|
| `t = rv` | `T&` | `t` | 若 `t` 与 `rv` 不指代同一对象，`t` 等价于赋值前 `rv` 的值；`rv` 的状态未指明 |

Note 2：无论 `t` 与 `rv` 是否指代同一对象，`rv` 仍必须满足使用它的库组件的要求。——这句话决定了**自移动赋值**的语义：`x = std::move(x)` 后，`x` 的值可以是任何东西（"若不指代同一对象"的条件不成立，没有值的后置条件），但 `x` 必须仍然是一个可用的对象。标准库类型自身的行为见 [[lib.types.movedfrom#2]]。

**表 34 *Cpp17CopyAssignable***（在 *Cpp17MoveAssignable* 之外）：

| 表达式 | 返回类型 | 返回值 | 后置条件 |
|---|---|---|---|
| `t = v` | `T&` | `t` | `t` 等价于 `v`，`v` 的值不变 |

几个容易忽略的点：

- 这些要求说的是**表达式**：`T u = rv;` 有效，并不要求 `T` 有移动构造函数——只有拷贝构造函数（参数为 `const T&`）的类型也满足 *Cpp17MoveConstructible*，因为右值可以绑定到 `const T&`。
- *Cpp17CopyConstructible* **包含** *Cpp17MoveConstructible*。所以只能移动不能拷贝的类型（`unique_ptr`）满足前者不满足后者；而**拷贝构造函数可用、移动构造函数被删除**的类型两者都不满足——`T u = rv;` 会选中被删除的移动构造函数。
- "等价于"是语义要求：拷贝构造之后两者相等。一个"拷贝时偷偷移动"的类型（例如 C++98 的 `auto_ptr`）在语法上满足表 32，语义上不满足——把它放进容器是 UB。这正是 `auto_ptr` 被弃用、移除的根本原因。

### 析构要求（表 35）

**表 35 *Cpp17Destructible***：

| 表达式 | 后置条件 |
|---|---|
| `a.~T()` | 没有异常被传播 |

Note 3：数组类型与非对象类型不是 *Cpp17Destructible*。

"没有异常被传播"把**析构函数抛异常**变成了违反库要求——与 [[res.on.functions#2.4]] 一致：放进容器的对象的析构函数抛出异常是 UB。C++11 起析构函数默认 `noexcept`（[[except.spec]]），所以只有显式写 `noexcept(false)` 才会触及这一条。

## 可交换要求（[swappable.requirements]）

### "可与……交换"（¶1–¶3）

¶1 本小节定义可交换的类型和表达式。设 `t` 是 `T` 类型的表达式，`u` 是 `U` 类型的表达式。

¶2 对象 `t` **[[g:swappable-with|可与 u 交换]]**（swappable with），当且仅当：

- **¶2.1** 表达式 `swap(t, u)` 和 `swap(u, t)` 在下述上下文中求值时有效；并且
- **¶2.2** 它们的效果是：`t` 所指对象具有 `u` 原来持有的值，`u` 所指对象具有 `t` 原来持有的值。

¶3 求值 `swap(t, u)` 和 `swap(u, t)` 的**上下文**必须确保：通过对一个候选集进行重载决议来选择名为 `swap` 的二元非成员函数，该候选集包含：

- **¶3.1** `<utility>` 中定义的两个 `swap` 函数模板（单对象版本和数组版本）；
- **¶3.2** 实参依赖查找（ADL）产生的查找集。

Note 1：若 `T`、`U` 都是基础类型或基础类型的数组，并且 `<utility>` 的声明在作用域中，上述查找集等价于对 `std::swap(t, u)` 做限定查找的结果。Note 2：具有可交换要求的库组件是否包含 `<utility>` 以确保适当的求值上下文，是未指明的。

这就是著名的**两步式**（two-step）：

```cpp
using std::swap;   // 第一步：让 std::swap 进入候选集（¶3.1）
swap(a, b);        // 第二步：非限定调用，ADL 再加入用户的 swap（¶3.2）
```

[[contents#3]] 说，库规范中非限定的 `swap` 总是在这个上下文中解释——所以 `std::sort` 交换元素时，会使用你在类型所在命名空间中定义的 `swap`。

### 可交换的类型（¶4–¶6）

- ¶4 右值或左值 `t` 是**可交换的**（swappable），当且仅当 `t` 可与任意 `T` 类型的右值或左值（分别地）交换。
- ¶5 类型 `X` 满足 ***Cpp17Swappable*** 要求，若 `X` 类型的左值是可交换的。
- ¶6 满足任何迭代器要求（[[iterator.requirements]]）的类型 `X` 满足 ***Cpp17ValueSwappable*** 要求，若对任何可解引用的 `X` 类型对象 `x`，`*x` 是可交换的。（`std::iter_swap` 和 `std::reverse` 等算法用它。）

### 标准的例子（¶7）

¶7 Example 1 演示了用户代码如何确保在恰当的上下文中求值 `swap`，包括一个**非对称**的、跨类型的交换（`A` 与 `Proxy`）：

```cpp run ok
#include <cassert>
#include <utility>

// Preconditions: std::forward<T>(t) is swappable with std::forward<U>(u).
template<class T, class U>
void value_swap(T&& t, U&& u) {
  using std::swap;
  swap(std::forward<T>(t), std::forward<U>(u)); // 使用 "swappable with" 条件（左值与右值）
}

// Preconditions: T meets the Cpp17Swappable requirements.
template<class T>
void lv_swap(T& t1, T& t2) {
  using std::swap;
  swap(t1, t2);                                 // 使用 T 左值的可交换条件
}

namespace N {
  struct A { int m; };
  struct Proxy { A* a; };
  Proxy proxy(A& a) { return Proxy{ &a }; }

  void swap(A& x, Proxy p) {
    std::swap(x.m, p.a->m);                     // 基础类型：等价于可交换条件的上下文
  }
  void swap(Proxy p, A& x) { swap(x, p); }      // 满足对称性约束
}

int main() {
  int i = 1, j = 2;
  lv_swap(i, j);
  assert(i == 2 && j == 1);

  N::A a1 = { 5 }, a2 = { -5 };
  value_swap(a1, proxy(a2));
  assert(a1.m == -5 && a2.m == 5);
}
```

注意 `N::swap(Proxy, A&)` 的存在只是为了满足 ¶2.1 要求的**对称性**：`swap(t, u)` 与 `swap(u, t)` 都必须有效。

三种调用方式的对比：

```cpp run ok
#include <concepts>
#include <string>
#include <type_traits>
#include <utility>
namespace lib {
  struct Widget { std::string name; };
  void swap(Widget& a, Widget& b) noexcept { a.name.swap(b.name); }
}
static_assert(std::is_nothrow_swappable_v<lib::Widget>);  // 萃取在 ¶3 的上下文中检查
int main() {
  lib::Widget a{"a"}, b{"b"};
  std::swap(a, b);         // 限定调用：绕过 lib::swap，用通用的三次移动
  using std::swap;
  swap(a, b);              // 两步式：ADL 找到 lib::swap
  std::ranges::swap(a, b); // C++20 CPO：内部替你完成两步式
  return a.name == "b" ? 0 : 1;
}
```

C++20 起推荐的写法是 `std::ranges::swap`（[[customization.point.object|定制点对象]]），它把两步式封装起来，并在找不到用户 `swap` 时退回移动交换。

## *Cpp17NullablePointer*（[nullablepointer.requirements]）

¶1 ***Cpp17NullablePointer*** 类型是支持空值的类指针类型。类型 `P` 满足该要求，若：

- **¶1.1** `P` 满足 *Cpp17EqualityComparable*、*Cpp17DefaultConstructible*、*Cpp17CopyConstructible*、*Cpp17CopyAssignable*、*Cpp17Swappable*、*Cpp17Destructible*；
- **¶1.2** 表 36 中的表达式有效且具有所示语义；
- **¶1.3** `P` 满足本小节的所有其他要求。

¶2 值初始化的 `P` 对象产生该类型的**空值**。空值只与自身等价。默认初始化的 `P` 对象可能具有不确定值或**错误值**。Note 1：涉及不确定值的操作可能导致未定义行为，涉及错误值的操作可能导致错误行为（[[basic.indet]]）。

¶3 `P` 类型的对象 `p` 可以按语境转换为 `bool`，效果如同用 `p != nullptr` 替代 `p` 求值。

¶4 *Cpp17NullablePointer* 要求中的任何操作都**不得**以异常退出。

¶5 表 36 中，`u` 是标识符，`t` 是 `P` 的非 const 左值，`a`、`b` 是（可能带 const 的）`P` 值，`np` 是（可能带 const 的）`std::nullptr_t` 值。

| 表达式 | 返回类型 | 操作语义 |
|---|---|---|
| `P u(np);` `P u = np;` | | 后置条件：`u == nullptr` |
| `P(np)` | | 后置条件：`P(np) == nullptr` |
| `t = np` | `P&` | 后置条件：`t == nullptr` |
| `a != b` | `decltype(a != b)` 建模 *boolean-testable* | `!(a == b)` |
| `a == np`、`np == a` | 各自建模 *boolean-testable* | `a == P()` |
| `a != np`、`np != a` | 各自建模 *boolean-testable* | `!(a == np)` |

谁使用这个要求？`std::unique_ptr<T, D>::pointer`（取自 `D::pointer`，若存在）、分配器的 `pointer` / `void_pointer` 等（[[allocator.requirements#92]]）、`std::exception_ptr`。最实用的场景是用 `unique_ptr` 管理"不是指针的句柄"：

```cpp run ok
#include <cstddef>
#include <cstdio>
#include <memory>

struct Fd {                                      // 满足 Cpp17NullablePointer 的文件描述符句柄
  int fd = -1;                                   // 值初始化 → 空值（¶2）
  Fd() = default;
  Fd(std::nullptr_t) noexcept {}                 // P u(np); P(np); t = np
  Fd(int f) noexcept : fd(f) {}
  explicit operator bool() const noexcept { return fd != -1; }  // 如同 p != nullptr（¶3）
  friend bool operator==(Fd, Fd) = default;
  friend bool operator==(Fd a, std::nullptr_t) noexcept { return a.fd == -1; }
};

struct FdCloser {
  using pointer = Fd;                            // unique_ptr<T, D>::pointer = D::pointer
  void operator()(Fd f) const noexcept { std::printf("close(%d)\n", f.fd); }
};

int main() {
  std::unique_ptr<int, FdCloser> p(Fd{3});       // 析构时调用 FdCloser，输出 close(3)
  std::unique_ptr<int, FdCloser> q;              // 空：析构时不调用删除器
  return p && !q ? 0 : 1;
}
```

C++20 的运算符重写让 `!=`、`np == a` 等都从两个 `operator==` 自动得到。

## *Cpp17Hash*（[hash.requirements]）

¶1 类型 `H` 满足 ***Cpp17Hash*** 要求，若：它是函数对象类型（[function.objects]）；满足 *Cpp17CopyConstructible* 与 *Cpp17Destructible*；表 37 中的表达式有效且具有所示语义。

¶2 设 `Key` 是 `H` 类型函数对象的实参类型；表 37 中 `h` 是（可能带 const 的）`H` 值，`u` 是 `Key` 类型的左值，`k` 是可转换为（可能带 const 的）`Key` 的值。

| 表达式 | 返回类型 | 要求 |
|---|---|---|
| `h(k)` | `size_t` | 返回值只取决于实参 `k`，**在程序运行期间**保持不变。对两个不同的值 `t1`、`t2`，`h(t1) == h(t2)` 的概率应该非常小，趋近于 `1.0 / numeric_limits<size_t>::max()` |
| `h(u)` | `size_t` | 不得修改 `u` |

几点解读：

- "**在程序运行期间**"（for the duration of the program）——Note 1 说得更明确："对于程序的**一次给定执行**"。哈希值**可以在不同的运行之间变化**。这允许实现使用随机种子来抵御哈希洪水攻击。本机 libc++ 与 libstdc++ 的 `std::hash<std::string>` 目前都是确定性的，但依赖这一点（例如把 `std::hash` 的结果写进文件或在网络上传输）是不可移植的。
- 碰撞概率是"**应该**"（should），即建议而非要求。`std::hash<int>` 在 libc++ 与 libstdc++ 中是恒等函数（MSVC STL 则使用 FNV-1a）——恒等哈希对**不同的值**碰撞概率为零，满足要求；但它的低位分布对某些输入模式（例如全是 8 的倍数）很差，好在这两个实现的无序容器通常使用质数个桶，缓解了这个问题。
- 表 37 并不要求"相等的键哈希相等"——那是**无序容器**对 `Hash` 与 `Pred` 组合提出的要求（[unord.req]），属于另一层。

为自己的类型提供哈希，通常是特化 `std::hash`——这是 [[namespace.std#2]] 明确允许的（依赖程序定义的类型）：

```cpp run ok
#include <cstddef>
#include <functional>
#include <string>
#include <unordered_set>

struct Point { int x, y; bool operator==(const Point&) const = default; };

template<> struct std::hash<Point> {             // OK：依赖程序定义的类型 Point
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

`std::hash` 的哪些特化是"启用的"、被禁用的特化具备什么性质，见 [[unord.hash]]。

## *Cpp17Allocator*（[allocator.requirements]）

### 分配器是什么（[allocator.requirements.general] ¶1）

¶1 库为**分配器**（allocators）规定了一套标准要求。分配器是封装了**分配模型**信息的类类型对象，这些信息包括：指针类型、指针差值的类型、对象大小的类型，以及该模型的内存分配与释放原语。所有字符串类型、容器（`array` 与 `inplace_vector` 除外）、字符串缓冲与字符串流、`match_results` 都以分配器参数化。

### 记号与 allocator_traits（¶2–¶3）

¶2 定义了一套记号：`T`、`U`、`C` 是任意 cv 无限定对象类型；`X` 是 `T` 的分配器类，`Y` 是对应的 `U` 的分配器类；`XX` 是 `allocator_traits<X>`，`YY` 是 `allocator_traits<Y>`；`a`、`a1`、`a2` 是 `X` 的左值；`p` 是调用 `a1.allocate` 得到的 `XX::pointer` 值（`a1 == a`）；`q`、`w`、`x` 是由 `p` 转换来的 const / void / const void 指针；`n` 是 `XX::size_type` 值；等等。

¶3 类模板 `allocator_traits`（[[allocator.traits]]）为所有分配器类型提供统一接口。若对某个类型或表达式规定了**默认值**，则该要求是**可选的**：分配器不提供时，`allocator_traits` 用规定的默认值替代。Note 1：不存在程序定义的 `allocator_traits` 特化（[[namespace.std#2]] 的"除非明确禁止"在这里生效）。

这就是 C++11 分配器模型的精髓：**容器只通过 `allocator_traits` 访问分配器**，所以分配器只需提供极少的成员，其余由 traits 补齐。

### 要求一览（¶4–¶91）

下表把 ¶4–¶91 的要求压缩在一起（"默认"一列即 *Remarks: Default:* 给出的值；有默认值者为可选）：

| 表达式 | 结果 / 语义 | 默认 |
|---|---|---|
| `X::pointer` | | `T*` |
| `X::const_pointer` | *Mandates*：`pointer` 可转换为它 | `pointer_traits<pointer>::rebind<const T>` |
| `X::void_pointer`、`Y::void_pointer` | *Mandates*：`pointer` 可转换为它；`X`、`Y` 的相同 | `…rebind<void>` |
| `X::const_void_pointer` | *Mandates*：前三种指针可转换为它；`X`、`Y` 的相同 | `…rebind<const void>` |
| `X::value_type` | **必需**：与 `T` 相同 | — |
| `X::size_type` | 能表示分配模型中最大对象大小的无符号整数类型 | `make_unsigned_t<difference_type>` |
| `X::difference_type` | 能表示任意两个指针之差的有符号整数类型 | `pointer_traits<pointer>::difference_type` |
| `X::rebind<U>::other` | 结果为 `Y`；后置条件：`YY::rebind_alloc<T>` 是 `X` | `SomeAllocator<T, Args>` → `SomeAllocator<U, Args>` |
| `*p`、`*q`、`p->m`、`q->m` | `T&`、`const T&`、等价于 `(*p).m` | — |
| `static_cast<XX::pointer>(w)` 等 | 与原值相等 | — |
| `pointer_traits<XX::pointer>::pointer_to(r)` | 与 `p` 相同 | — |
| `a.allocate(n)` | **必需**：为 `n` 个 `T` 的**数组**分配内存，创建数组对象但不构造元素；可抛出适当的异常；`n == 0` 时返回值未指明 | — |
| `a.allocate(n, y)` | 同 `allocate(n)`，`y` 用作局部性提示，用法未指明 | `a.allocate(n)` |
| `a.allocate_at_least(n)` {{c++23}} | 返回 `allocation_result{ptr, count}`，`count >= n` | `{a.allocate(n), n}` |
| `a.deallocate(p, n)` | **必需**；*Throws*: Nothing | — |
| `a.max_size()` | 可以有意义地传给 `allocate` 的最大 `n` | `numeric_limits<size_type>::max() / sizeof(value_type)` |
| `a1 == a2` | 仅当一方分配的存储可以由另一方释放时为 `true`；不抛；自反、对称、传递 | — |
| `a1 != a2` | `!(a1 == a2)` | （C++20 重写自动提供） |
| `a == b`（`b` 是 `Y`） | `a == YY::rebind_alloc<T>(b)` | — |
| `X u(a);`、`X u = a;` | 后置条件 `u == a`；不抛 | — |
| `X u(b);` | **必需**（转换构造）：`Y(u) == b` 且 `u == X(b)`；不抛 | — |
| `X u(std::move(a));` | `a` 的值不变且等于 `u`；不抛 | — |
| `a.construct(c, args...)` | 在 `c` 处构造 `C` 类型对象 | `construct_at(c, std::forward<Args>(args)...)` |
| `a.destroy(c)` | 销毁 `c` 处的对象 | `destroy_at(c)` |
| `a.select_on_container_copy_construction()` | 通常返回 `a` 或 `X()` | `return a;` |
| `X::propagate_on_container_copy_assignment` | 容器拷贝赋值时是否拷贝分配器；为 `true_type` 时拷贝不得抛出 | `false_type` |
| `X::propagate_on_container_move_assignment` | 容器移动赋值时是否移动分配器 | `false_type` |
| `X::propagate_on_container_swap` | 容器交换时是否交换分配器 | `false_type` |
| `X::is_always_equal` | 任意两个 `X` 值 `==` 是否总为 `true` | `is_empty<X>::type` |

几个值得展开的点：

**`allocate` 创建的是一个数组对象（¶36）**。"为 `n` 个 `T` 的数组分配内存，**创建这样一个对象**，但不构造数组元素"——这句话是 C++20 隐式对象创建（[[intro.object]]）引入后的措辞，它保证了 `p + i` 的指针算术在形式上合法（指针运算只在数组对象内有定义，[[expr.add]]）。Example 1 给出了复用存储时的写法：`launder(reinterpret_cast<T*>(new (p) byte[n * sizeof(T)]))` 可以隐式创建合适的数组对象并获得指向它的指针。

**`deallocate` 的前置条件（¶48）**很严格：`p` 必须来自 `allocate`，`n` 必须等于当初传给 `allocate` 的值（若来自 `allocate_at_least`，则 `n` 可以在请求值与实际返回的 `count` 之间）。这让分配器可以不记录块大小——`std::allocator` 可以调用带大小的 `operator delete(void*, size_t)`。

**相等性（¶54）**的含义不是"两个对象一模一样"，而是"**可以互相释放对方分配的内存**"。无状态分配器总是相等；`std::pmr::polymorphic_allocator` 在指向同一内存资源时相等。它决定了容器移动赋值时能否直接"偷"内存：若分配器不相等且不传播，就只能逐元素移动。

**传播特性（¶80–¶91）**：三个 `propagate_on_container_*` 决定分配器是否"跟着内容走"。默认都是 `false_type`——容器拷贝赋值后保留自己原来的分配器。`std::pmr::polymorphic_allocator` 的三者都是 `false_type`，这是它"分配器不跟着数据走"的设计。

**`is_always_equal` 默认为 `is_empty<X>`**：空类分配器必然无状态，必然总相等。

### 花式指针（¶92–¶95）

¶92 分配器类型 `X` 必须满足 *Cpp17CopyConstructible*。`XX::pointer`、`XX::const_pointer`、`XX::void_pointer`、`XX::const_void_pointer` 必须满足 *Cpp17NullablePointer*。这些指针类型上的构造函数、比较运算符函数、拷贝、移动、交换操作均不得以异常退出。`XX::pointer` 与 `XX::const_pointer` 还必须满足 *Cpp17RandomAccessIterator*，并满足额外要求：当 `p` 与 `p + n` 都是可解引用的指针值时，`addressof(*(p + n)) == addressof(*p) + n` 为真——即它们必须是**连续的**。

¶93 定义[[g:equivalently-valued|**等值**]]（equivalently-valued）的指针值：两个（可能不同类型的）指针可以通过只在这四种类型间进行的 `static_cast` 序列转换成 `const_pointer`，并且转换后比较相等。¶94–¶95：`void_pointer` 的比较、`pointer` 的比较与相减，都可以把任一方替换为等值的 `const` 版本而语义不变。

这些要求是为**花式指针**（fancy pointer）准备的——例如共享内存中使用的"偏移量指针"（`boost::interprocess::offset_ptr`），它存储相对于自身地址的偏移，使数据结构可以被映射到不同进程的不同地址。容器内部必须全程使用 `allocator_traits<A>::pointer`，而不能偷偷转成裸指针存储。

### 分配器可以拒绝某些类型（¶96–¶97）

¶96 分配器可以约束可用于实例化它的类型，以及可用于调用其 `construct` 或 `destroy` 成员的实参。若某类型不能与特定分配器一起使用，分配器类或对 `construct`/`destroy` 的调用可能无法实例化。

¶97 若分配器不支持某个过对齐类型所关联的对齐，为该类型实例化分配器可能失败；分配器也可能**静默忽略**所请求的对齐。Note 4：此外，该类型的 `allocate` 可以通过抛出 `bad_alloc` 失败。——所以把 `alignas(64)` 的类型放进使用自定义分配器的容器时，对齐是否被遵守取决于分配器。`std::allocator` 使用 C++17 的对齐感知 `operator new`，会遵守。

### 最小分配器（¶98–¶99）

¶98 Example 2 给出满足 [allocator.requirements.general] 的**最小接口**：

```cpp
template<class T>
struct SimpleAllocator {
  using value_type = T;
  SimpleAllocator(ctor args);
  template<class U> SimpleAllocator(const SimpleAllocator<U>& other);
  T* allocate(std::size_t n);
  void deallocate(T* p, std::size_t n);
  template<class U> bool operator==(const SimpleAllocator<U>& rhs) const;
};
```

¶99 下面的说明性概念定义了 Allocator 类型的最小要求：

```cpp
template<class Alloc>
concept simple-allocator =
  requires(Alloc alloc, size_t n) {
    { *alloc.allocate(n) } -> same_as<typename Alloc::value_type&>;
    { alloc.deallocate(alloc.allocate(n), n) };
  } &&
  copy_constructible<Alloc> &&
  equality_comparable<Alloc>;
```

若类型 `Alloc` 满足 [allocator.requirements.general] 的要求，它就建模 *simple-allocator*。（它被较新的组件引用，例如 `std::execution` 中 `get_allocator` 查询对结果类型的要求。）

一个可运行的计数分配器：

```cpp run ok
#include <cstddef>
#include <cstdio>
#include <new>
#include <vector>

template<class T>
struct Counting {
  using value_type = T;                       // 必需
  static inline std::size_t allocs = 0;
  Counting() = default;
  template<class U> Counting(const Counting<U>&) noexcept {}   // 必需：X u(b);
  T* allocate(std::size_t n) {                // 必需
    ++allocs;
    return static_cast<T*>(::operator new(n * sizeof(T)));
  }
  void deallocate(T* p, std::size_t n) noexcept { ::operator delete(p, n * sizeof(T)); }
  template<class U> bool operator==(const Counting<U>&) const noexcept { return true; }
};  // 其余（pointer、rebind、construct、propagate_*……）全部由 allocator_traits 补齐

int main() {
  std::vector<int, Counting<int>> v;
  for (int i = 0; i < 100; ++i) v.push_back(i);
  std::printf("allocations: %zu\n", Counting<int>::allocs);   // 本机 libc++：8（几何增长）
}
```

### 分配器完整性要求（[allocator.requirements.completeness]）

¶1 若 `X` 是 `T` 的分配器类，`X` 还满足[[g:allocator-completeness-requirements|**分配器完整性要求**]]，当且仅当无论 `T` 是否完整：

- **¶1.1** `X` 是完整类型；
- **¶1.2** `allocator_traits<X>` 除 `value_type` 外的所有成员类型都是完整类型。

这个看似抽象的要求，是 C++17 允许 `vector`、`list`、`forward_list` 以**不完整类型**实例化的基础（[[N4510]]）：容器规范说，若分配器满足完整性要求，则 `T` 在实例化容器时可以是不完整的（只要在使用某些成员之前变得完整）。`std::allocator` 满足这一要求。这使得递归数据结构可以直接写：

```cpp run ok
#include <list>
#include <vector>
struct Node {
  int value;
  std::vector<Node> children;   // C++17 起 OK：此处 Node 尚不完整
  std::list<Node> siblings;     // 同上
};
int main() {
  Node n{1, {}, {}};
  n.children.push_back({2, {}, {}});
  return n.children.size() == 1 ? 0 : 1;
}
```

`std::map<K, Node>`、`std::deque<Node>`、`std::unordered_map` 等**不在**这份许可之列——以不完整类型实例化它们是 UB（[[res.on.functions#2.5]]），尽管在实践中常常也能编译。

## 实现视角

- **两步式 swap**：libc++ 的经典算法通过内部的 `_IterOps<_ClassicAlgPolicy>::iter_swap` 调用 `std::iter_swap`，后者（`__algorithm/iter_swap.h`）的函数体就是一句**非限定**的 `swap(*__a, *__b);`——由于它本身位于 `namespace std` 中，普通查找找到 `std::swap`，ADL 再加入用户的 `swap`，恰好就是 ¶3 规定的上下文，不需要 `using std::swap;`。
- **严格弱序检查**：libc++ debug 模式的 `__check_strict_weak_ordering_sorted` 在排序后对小规模区间做 O(n²) 的抽查，因此只适合测试。libstdc++ 的 `_GLIBCXX_DEBUG` 模式也有类似的比较器检查。
- **allocator_traits 的默认值**是用"检测成员是否存在"实现的：libc++ 中 `allocator_traits::pointer` 就是 `__pointer<value_type, allocator_type>`，而后者定义为 `__detected_or_t<_Tp*, __pointer_member, _Alloc>`——检测 `_Alloc::pointer`，不存在时回退到 `_Tp*`。这正是 ¶3 中"可选要求被默认值替代"的直接翻译。

## 常见误区与陷阱

!!! pitfall "比较器用 <= 或不一致的比较"
    `std::sort`、`std::set`、`std::map`、`std::priority_queue` 的比较器必须是严格弱序。`<=`、只比较部分字段却又与 `==` 不一致、比较浮点 NaN，都可能导致越界读写、无限循环或容器结构损坏——而且完全不会被编译器诊断。

!!! pitfall "swap 写成 std::swap(a, b)"
    在泛型代码中写 `std::swap(a, b)` 会绕过用户的定制 `swap`，失去 `noexcept` 和效率。要么用两步式，要么用 `std::ranges::swap`。

!!! pitfall "把 std::hash 的结果持久化"
    [hash.requirements] 只保证一次程序执行内的一致性。

!!! pitfall "有状态分配器的相等性"
    若有状态分配器的 `operator==` 总返回 `true`，但两者实际上无法互相释放内存，容器在移动赋值、`swap`、`splice` 时会把内存交给错误的分配器释放——UB。

## 思考题

!!! question "思考题 1"
    下面的类型满足 *Cpp17MoveConstructible* 吗？满足 *Cpp17CopyConstructible* 吗？能用 `std::vector<M>` 的 `push_back(const M&)` 吗？

    ```cpp
    struct M { M() = default; M(const M&) = default; M(M&&) = delete; };
    ```

<details markdown="1">
<summary>展开查看答案与解析</summary>

两者都不满足。表 31 要求 `T u = rv;` 有效——但对右值，重载决议选中被删除的 `M(M&&)`（删除函数仍参与重载决议），表达式非良构。*Cpp17CopyConstructible* 包含 *Cpp17MoveConstructible*，所以也不满足。

`vector<M>::push_back(const M&)` 要求 `T` 是 *Cpp17CopyInsertable* 进 `vector`；而扩容时把旧元素搬到新存储需要 *Cpp17MoveInsertable*（用右值构造），`M` 的移动构造被删除，实例化会失败（libc++ 和 libstdc++ 都会报错）。这正是"不要删除移动构造函数，而是不声明它"的原因——不声明时，右值会退回拷贝构造函数。
</details>

!!! question "思考题 2"
    一个分配器的 `is_always_equal` 是 `true_type`，`propagate_on_container_move_assignment` 是 `false_type`。`std::vector<T, A>` 的移动赋值运算符的复杂度是多少？是否可能抛出异常？

<details markdown="1">
<summary>展开查看答案与解析</summary>

由于分配器总是相等，目标容器的分配器可以释放源容器的内存，因此移动赋值可以直接接管源容器的缓冲区：常数时间（加上销毁目标原有元素的线性时间），不需要逐元素移动，也不会抛出。标准中 `vector` 移动赋值的异常规范正是 `allocator_traits<A>::propagate_on_container_move_assignment::value || allocator_traits<A>::is_always_equal::value`。若两者都为 `false`，且两个分配器在运行期不相等，容器就只能逐元素移动构造到自己的存储中——线性时间且可能抛出。
</details>

## 小结

!!! summary "核心要点"
    - Cpp17 命名要求是**文字要求**，编译器不检查语义，违反是 UB。
    - 比较：`==` 必须是等价关系，`<` 必须是严格弱序——比较器写成 `<=` 是真实的越界 bug。
    - 构造/赋值：*Copy* 包含 *Move*；移动后源对象状态未指明但必须仍满足组件要求；自移动赋值不保证值。
    - 析构不得传播异常。
    - 可交换 = 在"`std::swap` + ADL"的上下文中 `swap(t, u)` 与 `swap(u, t)` 都有效且真的交换；用两步式或 `std::ranges::swap`。
    - *Cpp17NullablePointer*：值初始化为空、可与 `nullptr` 比较、按语境转 `bool`、操作不抛——可用作 `unique_ptr` 的句柄类型。
    - *Cpp17Hash*：结果只在一次执行内稳定；碰撞率低只是建议。
    - *Cpp17Allocator*：只需 `value_type`、`allocate`、`deallocate`、转换构造、`==`，其余由 `allocator_traits` 补默认；`allocate` 创建数组对象；相等 = 可互相释放；花式指针必须连续。
    - 完整性要求让 `vector`/`list`/`forward_list` 可以用不完整类型实例化。
