---
title: 可选对象
summary: <optional> 总览：optional 对象的定义、头文件概要（大部分 freestanding、range 相关特化）、nullopt_t 为何不能默认构造、bad_optional_access，以及 optional 与 optional / nullopt / T 之间完整的比较规则、swap、make_optional 和 hash
status: draft
covers: optional.general, optional.syn, optional.nullopt, optional.bad.access, optional.relops, optional.nullops, optional.comp.with.t, optional.specalg, optional.hash
papers: P0220R1, P0798, P3168, P2988, P2407
related: optional.optional, optional.optional.ref, expected, variant, any, unord.hash, class.union, structure.specifications, over.match.oper
tags: 标准库, optional, 词汇类型, 比较运算符
updated: 2026-10-18
---

`std::optional<T>` 是标准库里最基础的**词汇类型**（vocabulary type）之一：它表达"这里**也许**有一个 `T`"。在它出现之前，人们用三种笨办法表达"可能没有值"：特殊哨兵值（`-1`、`npos`、空字符串）、`T*` 指针（附带"谁拥有它"的歧义和一次堆分配）、或者 `std::pair<T, bool>`（要求 `T` 可默认构造，且"没有值"时仍然构造了一个 `T`）。`optional` 把**存储**放在自身内部（不分配堆内存），并把**被包含对象的生命周期**交给自己管理——没有值的时候，那个 `T` 根本不存在。

[optional] 这一节由三块组成：

| 子条款 | 内容 | 本站页面 |
|---|---|---|
| [optional.general]、[optional.syn] | 定义、头文件概要 | 本页 |
| [optional.optional] | 主模板 `optional<T>`：构造、析构、赋值、swap、迭代器、观察器、单子操作、`reset` | [[optional.optional]] |
| [optional.optional.ref] | C++26 偏特化 `optional<T&>` | [[optional.optional.ref]] |
| [optional.nullopt]、[optional.bad.access] | `nullopt_t`、`bad_optional_access` | 本页 |
| [optional.relops]、[optional.nullops]、[optional.comp.with.t] | 三组比较运算符 | 本页 |
| [optional.specalg]、[optional.hash] | `swap`、`make_optional`、`hash` | 本页 |

阅读前最好熟悉：联合体的活跃成员（[[class.union]]）——`optional` 的规范就是用联合体成员写的；库规范里 *Constraints* / *Mandates* / *Hardened preconditions* 的法律含义（[[structure.specifications]]）；以及 C++20 的比较运算符重写规则（[[over.match.oper]]）。

## 什么是"可选对象"（[optional.general] ¶1）

!!! std
    An *optional object* is an object that contains the storage for another object and manages the lifetime of this contained object, if any.

    可选对象是这样一种对象：它**内含**另一个对象的存储，并管理这个被包含对象（若存在）的生命周期。

¶1 接着说，被包含对象可以在可选对象初始化**之后**才初始化，也可以在可选对象销毁**之前**就被销毁；初始化状态由可选对象自己跟踪。三个要点：

1. **存储是内嵌的**。`sizeof(optional<T>)` 至少是 `sizeof(T)`，通常再加一个 `bool` 和对齐填充。没有堆分配，没有间接层。
2. **生命周期独立**。`optional<std::string> o;` 之后，`o` 的生命周期已经开始，但里面没有任何 `std::string` 对象——不是"空字符串"，是**没有对象**。这正是[[class.union]]里"活跃成员"的语义：[[optional.optional]]用一个匿名联合体成员 *val* 来描述存储，"有值"当且仅当 *val* 是活跃成员。
3. **状态被跟踪**。`optional` 必须自己知道 *val* 是否存活（典型实现是一个 `bool engaged`），以便在析构、复制、赋值时做正确的事。C++26 的 `optional<T&>` 则直接把"空指针"当作"无值"状态（[[optional.optional.ref]]）。

## 头文件概要（[optional.syn]）

概要第一行注释是 `// mostly freestanding`：`<optional>` 的绝大部分在**独立实现**（[[g:freestanding-implementation]]）中也要提供。例外是标为 `// freestanding-deleted` 的 `value()` 系列——它们会抛 `bad_optional_access`，而独立实现不一定支持异常；在独立实现中这些函数被定义为弃置的，你只能用 `operator*`、`value_or` 等不抛异常的接口。这个"部分 freestanding 的类"的机制来自 [[P2407]]。

概要里值得一提的声明：

- `template<class T> class optional;` 与 C++26 的偏特化 `template<class T> class optional<T&>;`（注释写的是"for lvalue reference types"——右值引用不是合法的被包含类型）。
- 三个变量模板特化 {{c++26}}：
    - `ranges::enable_view<optional<T>> = true`——`optional` 是一个 **view**（最多含一个元素的范围，见 [[optional.optional]] 的迭代器支持）；
    - `format_kind<optional<T>> = range_format::disabled`——虽然 `optional` 现在是范围，但 `std::format` **不会**把它当范围格式化（否则 `optional<int>{1}` 会被打印成 `[1]`，这显然不是大家想要的语义，[[P3168]] 的作者特意把这条路关掉，留给将来专门的 optional 格式化方案）；
    - `ranges::enable_borrowed_range<optional<T&>> = true`——`optional<T&>` 的迭代器指向的是外部对象，不随 `optional<T&>` 本身销毁而悬空，因此是 borrowed range。
- 仅用于说明的概念 *is-derived-from-optional*：`T` 能否绑定到某个 `const optional<U>&`——即 `T` 是 `optional` 的特化**或从某个 `optional` 公开派生**。它只用于 `operator<=>(const optional<T>&, const U&)` 的约束（见下文）。
- 推导指引 `optional(T) -> optional<T>;`（在 [optional.optional.general] 中）：`std::optional o = 1;` 推导为 `optional<int>`；按值推导意味着 `T` 会退化（`"abc"` 推导为 `optional<const char*>`）。

## `nullopt_t`：为什么连默认构造函数都不给（[optional.nullopt]）

¶1 `nullopt_t` 是一个**空类类型**，唯一用途是作为"无值"状态的标记：`optional<T>` 有一个以 `nullopt_t` 为唯一参数的构造函数，表示构造一个不含值的 optional。`nullopt` 是它的 `inline constexpr` 实例，初始化器是*未指明*的。

¶2 是本节的精华：

!!! std
    Type `nullopt_t` does not have a default constructor or an initializer-list constructor, and is not an aggregate.

    `nullopt_t` 没有默认构造函数，没有初始化器列表构造函数，也不是聚合。

为什么这么严格？因为 `optional` 有大量从 `{}` 可以匹配的重载。设想 `nullopt_t` 是个平凡的 `struct nullopt_t {};`：

```cpp
std::optional<int> o = 1;
o = {};   // 如果 nullopt_t 能从 {} 构造，operator=(nullopt_t) 与 operator=(const optional&)、
          // operator=(optional&&) 同时可行，转换序列都是"从 {} 构造一个类对象"，无法区分 → 歧义
```

把 `nullopt_t` 设计成"不能从 `{}` 构造"，`operator=(nullopt_t)` 对 `o = {}` 就**不可行**，于是 `o = {}` 稳定地选中 `operator=(optional&&)`（右侧 `{}` 值初始化出一个空 optional），效果是重置。同理 `f({})` 在 `f(optional<int>)` 与 `f(nullopt_t)` 之间也不会歧义。（`o = {}` 还要过 `operator=(U&&)` 这一关，见 [[optional.optional]]。）

libc++ 的做法（`<optional>`）：`nullopt_t` 只有一个接受两个私有标签类型 `__secret_tag` 的 `explicit constexpr` 构造函数，`nullopt` 用 `nullopt_t{nullopt_t::__secret_tag{}, nullopt_t::__secret_tag{}}` 初始化——用户代码根本拼不出这个调用。

¶2 最后还要求 `nullopt_t` 满足 `copyable` 与 `three_way_comparable<strong_ordering>`：你可以复制 `nullopt`，也可以拿两个 `nullopt_t` 比较（它们总是相等）。

## `bad_optional_access`（[optional.bad.access]）

```cpp
class bad_optional_access : public exception {
public:
  constexpr const char* what() const noexcept override;
};
```

¶1 它是对**不含值**的 optional 调用 `value()` 时抛出的异常类型。¶2 `what()` 返回实现定义的 NTBS；在**常量求值**期间要求按普通字面量编码——这是 C++26 允许在常量求值中抛出与捕获异常之后补上的措辞，`what()` 因此也是 `constexpr` 的。

注意它直接派生自 `std::exception`，**不是** `std::logic_error`：这是一个历史选择，`catch (const std::logic_error&)` 抓不到它。

## 比较运算符：三组、一条主线

`optional` 的比较规则可以用一句话概括：**"无值"是一个比任何值都小、且只和自己相等的值**。所有比较都围绕这条主线展开，形式上分三组。

### optional 与 optional（[optional.relops]）

六个关系运算符 `== != < > <= >=` 都是 `template<class T, class U>`，即 `optional<int>` 可以与 `optional<long>` 比较。以 `operator<` 为例：

- ¶7 *Constraints*：`*x < *y` 良构且结果可转换为 `bool`；
- ¶8 *Returns*：若 `!y` 则 `false`；否则若 `!x` 则 `true`；否则 `*x < *y`。

其余各个运算符的 *Returns*（¶2、¶5、¶11、¶14、¶17）都是同一张真值表的不同切面：

| `x` | `y` | `x == y` | `x < y` | `x <= y` | `x > y` | `x >= y` |
|---|---|---|---|---|---|---|
| 无值 | 无值 | `true` | `false` | `true` | `false` | `true` |
| 无值 | 有值 | `false` | `true` | `true` | `false` | `false` |
| 有值 | 无值 | `false` | `false` | `false` | `true` | `true` |
| 有值 | 有值 | `*x == *y` | `*x < *y` | `*x <= *y` | `*x > *y` | `*x >= *y` |

几个法律细节：

- **每个运算符各自转发到 `T` 的同名运算符**。`x <= y` 用的是 `*x <= *y`，而不是 `!(*y < *x)`。这对浮点 NaN、对只定义了部分运算符的类型很重要——`optional` 不发明任何 `T` 没有的等式或序关系。注 1 特意说明 `T` 不必满足 *Cpp17EqualityComparable*。
- 这些都是 *Constraints*，不是 *Mandates*：如果 `*x < *y` 不合法，`operator<` 只是**不参与重载决议**，`requires { a < b; }` 会得到 `false`，而不是硬错误。
- ¶3 等 *Remarks*：只有当 `*x == *y` 是核心常量表达式时，该特化才是 constexpr 函数。

¶19 `operator<=>` 的形式略有不同：它要求 `three_way_comparable_with<T> U`，返回 `compare_three_way_result_t<T, U>`；*Returns*：若 `x && y` 则 `*x <=> *y`，否则 `x.has_value() <=> y.has_value()`——用 `bool` 的比较精确编码了"无值最小"。

### optional 与 nullopt（[optional.nullops]）

只有两个函数：

- ¶1 `operator==(const optional<T>& x, nullopt_t)` 返回 `!x`；
- ¶2 `operator<=>(const optional<T>& x, nullopt_t)` 返回 `x.has_value() <=> false`，类型是 `strong_ordering`。

两者都是 `noexcept` 的，也不要求 `T` 有任何比较能力。C++17 时这里有 12 个函数（6 个运算符 × 两个方向）；C++20 起，`nullopt == x`、`x != nullopt`、`x < nullopt` 等全部由[[over.match.oper|重写候选]]从这两个函数合成。

### optional 与 T（[optional.comp.with.t]）

`optional<T>` 可以直接和一个"裸值"比较，两个方向各 6 个运算符外加一个 `<=>`：

```cpp run title="cmp.cpp" ok
#include <cassert>
#include <compare>
#include <optional>

int main() {
  std::optional<int> none, zero = 0, one = 1;
  assert(none < zero);              // 空小于任何值
  assert(none < -1000);             // 和 T 比较也一样
  assert(zero == 0 && one != 0);
  assert(none != 0);                // 空不等于任何值
  assert(none == std::nullopt);
  assert((none <=> std::nullopt) == 0);
  assert((zero <=> none) > 0);
  std::optional<long> l = 1;
  assert(one == l);                 // optional<int> 与 optional<long> 可比较
}
```

每个函数的 *Constraints* 都以"`U`（或 `T`）**不是** `optional` 的特化"开头（¶1、¶3……）。原因：如果没有这条，`optional<int> == optional<long>` 既能匹配 [optional.relops] 的 `operator==(const optional<T>&, const optional<U>&)`，又能匹配这里的 `operator==(const optional<T>&, const U&)`（`U = optional<long>`），而后者会去检查 `*x == optional<long>` 是否合法——又要回头看 `int == optional<long>`……排除 `optional` 特化可以切断这种递归和歧义。

`operator<=>`（¶25）的约束更强一些：`requires (!is-derived-from-optional<U>) && three_way_comparable_with<T, U>`。它排除的范围比"不是 `optional` 的特化"更宽：一个**派生自** `optional<X>` 的类型 `D` 也被排除。直观理由是，`D` 能隐式转换为 `const optional<X>&`，与它的比较理应交给 optional-optional 版本；若让本重载也接手，`three_way_comparable_with<T, D>` 的检查又会去查找 `T <=> D`，而这个查找会再次考虑本模板本身，容易形成约束的自我依赖。¶25 的 *Effects* 是 `x.has_value() ? *x <=> v : strong_ordering::less`。

!!! pitfall "`optional<bool>` 与 `optional<T*>` 的比较"
    `std::optional<bool> b = false; if (b == false)` 比较的是**值**（有值且为 `false` → `true`）；而 `if (!b)` 检查的是**有无值**（有值 → `false`）。对 `optional<T*>` 同理，`opt == nullptr` 与 `!opt` 是两回事。代码审查时看到 `optional<bool>` 要格外警惕。

## swap 与 make_optional（[optional.specalg]）

¶1 非成员 `swap(optional<T>&, optional<T>&)` 的 *Constraints* 是

```cpp
is_reference_v<T> || (is_move_constructible_v<T> && is_swappable_v<T>)
```

——`is_reference_v<T>` 那一支是为 C++26 的 `optional<T&>` 准备的：交换两个 `optional<T&>` 只是交换两个指针（[[optional.optional.ref]]），不要求 `T` 可交换。其 `noexcept` 规格与成员 `x.swap(y)` 一致。

`make_optional` 有三个重载：

- `make_optional(T&& v)` → `optional<decay_t<T>>(std::forward<T>(v))`；
- `make_optional<T>(args...)` → `optional<T>(in_place, args...)`；
- `make_optional<T>(il, args...)` → `optional<T>(in_place, il, args...)`。

¶3 给第一个重载加了一条奇特的约束 {{c++26}}：**调用没有使用以类型模板实参开头的显式模板实参列表**。也就是说，`make_optional<X>(...)` 永远不会选中第一个重载。为什么需要？看 `make_optional<int&>(x)`：没有这条约束时，第一个重载以 `T = int&` 可行，返回类型却是 `optional<decay_t<int&>>` 即 `optional<int>`——你明确写了 `int&`，拿到的却是一份拷贝。C++26 有了 `optional<T&>` 之后，这种"静默退化"变得不可接受：

```cpp run title="make_optional.cpp" ok
#include <optional>
#include <type_traits>

int main() {
  int x = 0;
  auto a = std::make_optional(x);          // 推导：optional<int>
  auto b = std::make_optional<int&>(x);    // 显式实参：跳过第一个重载
  static_assert(std::is_same_v<decltype(a), std::optional<int>>);
  static_assert(std::is_same_v<decltype(b), std::optional<int&>>);
}
```

实际上在 C++17 之后，`make_optional` 已经没什么存在的必要：CTAD（`std::optional o = x;`）和 `std::optional<T>(std::in_place, args...)` 更直接。

## hash（[optional.hash]）

¶1 `hash<optional<T>>` **当且仅当** `hash<remove_const_t<T>>` 启用时启用（"启用"的含义见 [[unord.hash]]）。对有值的 `o`，`hash<optional<T>>()(o)` 必须等于 `hash<remove_const_t<T>>()(*o)`——于是 `unordered_set<optional<int>>` 中有值元素的散列分布与 `unordered_set<int>` 完全一致。对无值的 `o`，结果是**未指明**的值。成员函数**不保证** `noexcept`。

libc++（`<optional>` 末尾）对无值返回 `0`：`static_cast<bool>(__opt) ? hash<remove_const_t<_Tp>>()(*__opt) : 0`。

!!! lawyer "`hash<optional<int&>>`？"
    ¶1 用的是 `remove_const_t<T>`，对 `T = int&` 而言就是 `int&`，而 `hash<int&>` 不是启用的特化。所以按字面读，`hash<optional<int&>>` 是**禁用**的——C++26 合入 `optional<T&>` 时并没有给它补散列支持。libc++ 23 的行为与此一致（`std::hash<std::optional<int&>>` 不可默认构造）。不要假设 `unordered_set<optional<T&>>` 可用。

## 历史

- `optional` 源自 Boost.Optional，先进入 Library Fundamentals TS，再随 [[P0220R1]] 合入 C++17。早期提案曾包含 `optional<T&>`，因"赋值到底是改绑还是写穿"的争议被移除——这场争论直到 C++26 的 [[P2988]] 才了结（见 [[optional.optional.ref]]）。
- C++20：比较运算符改用 `<=>` 并借助重写候选大幅精简（`nullopt` 比较从 12 个函数减到 2 个）；`optional` 的特殊成员函数可以是 constexpr 的。
- C++23：单子操作 `and_then` / `transform` / `or_else`（[[P0798]]）。
- C++26：range 支持（[[P3168]]）、`optional<T&>`（[[P2988]]）、部分 freestanding（[[P2407]]）、观察器的加固前置条件、`make_optional` 显式实参约束。

## 思考题

!!! question "思考题 1"
    `std::optional<int> o = 5; o = {};` 之后 `o` 是什么？如果把 `nullopt_t` 改成 `struct nullopt_t {};`，这行代码还能编译吗？

<details markdown="1">
<summary>展开查看答案与解析</summary>

`o` 变为无值。候选有：`operator=(nullopt_t)`（`nullopt_t` 不能从 `{}` 初始化，不可行）、`operator=(const optional&)`、`operator=(optional&&)`、`operator=(U&&)`（`U` 取默认实参 `int`，但被 [optional.assign] ¶14.2 排除：`T` 是标量且 `decay_t<U>` 就是 `T`）。剩下的复制赋值与移动赋值都通过 `optional` 的默认构造函数从 `{}` 得到参数，[[over.ics.rank]] 中"右值引用绑定右值优先"的规则选中移动赋值；右侧是空 optional，于是 `o` 被重置。

若 `nullopt_t` 能从 `{}` 构造，`operator=(nullopt_t)` 也变得可行，它的转换序列（用 `nullopt_t` 的默认构造函数构造参数）与 `operator=(optional&&)` 的（用 `optional` 的默认构造函数）同属用户定义转换、但用的是不同的构造函数，[[over.ics.rank]] 无法区分 → 歧义，编译失败。这正是 [optional.nullopt] ¶2 的动机。
</details>

!!! question "思考题 2"
    为什么 `std::optional<double> a = NAN, b = NAN;` 中 `a <= b` 与 `!(b < a)` 结果不同？标准为什么不用后者来定义前者？

<details markdown="1">
<summary>展开查看答案与解析</summary>

两者都有值，`a <= b` 按 [optional.relops] ¶14 是 `*a <= *b`，NaN 参与的比较都为 `false`；而 `!(b < a)` 是 `!false` 即 `true`。标准让每个运算符都转发到 `T` 的**同名**运算符，就是为了不对 `T` 强加全序假设——`optional<T>` 的比较应当是 `T` 比较的"提升"，在"都有值"时与 `T` 的行为一模一样。
</details>

## 小结

| 主题 | 规则 |
|---|---|
| 可选对象 | 内嵌存储 + 管理被包含对象的生命周期；无值时 `T` 对象不存在 |
| freestanding | 大部分可用；`value()` 在独立实现中弃置 |
| `nullopt_t` | 空类、无默认构造/初始化器列表构造、非聚合 → `o = {}` 无歧义 |
| `bad_optional_access` | 派生自 `exception`；`what()` constexpr |
| 比较 | 无值 < 任何值；各运算符转发到 `T` 同名运算符；全是 *Constraints* |
| `nullopt` 比较 | 只有 `==` 和 `<=>`，其余靠 C++20 重写 |
| 与 `T` 比较 | 排除 `optional` 特化（`<=>` 排除派生自 optional 的类型） |
| `make_optional<X>(...)` | C++26 起永远走 `in_place` 重载 |
| hash | 有值时等于 `hash<T>`；无值时未指明（libc++ 为 0） |
