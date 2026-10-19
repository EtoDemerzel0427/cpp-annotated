---
title: 可选对象
summary: <optional> 总览：可选对象的含义，nullopt_t 为什么不能从 {} 构造，optional 与 optional、nullopt、T 之间的比较规则，swap、make_optional、hash、bad_optional_access 和头文件概要。
status: done
covers: optional.general, optional.syn, optional.nullopt, optional.bad.access, optional.relops, optional.nullops, optional.comp.with.t, optional.specalg, optional.hash
papers: P0220R1, P0798, P3168, P2988, P2407
related: optional.optional, optional.optional.ref, expected, variant, any, unord.hash, class.union, structure.specifications, over.match.oper
tags: 标准库, optional, 词汇类型, 比较运算符
updated: 2026-10-19
---

!!! tldr
    - `optional<T>` 把 `T` 的存储放在自己内部，不分配堆内存；没有值时，里面根本不存在 `T` 对象。
    - 比较规则可以归结为一句：无值比任何值都小，并且只和无值相等。每个运算符都转发到 `T` 的同名运算符，不发明 `T` 没有的关系。
    - `nullopt_t` 故意不能从 `{}` 构造，所以 `o = {}` 没有二义，效果是把 `o` 清空。
    - C++26 起 `make_optional<int&>(x)` 返回 `optional<int&>`，不再悄悄退化成 `optional<int>`。
    - `optional<bool>` 和 `optional<T*>` 上，`o == false` 比较的是值，`!o` 检查的是有没有值，两者不同。

[[optional.optional]] 讲主模板的成员，[[optional.optional.ref]] 讲 C++26 的 `optional<T&>`。本页讲其余部分：定义、`nullopt`、异常类、比较运算符、`swap`、`make_optional`、`hash` 和头文件概要。

## 什么是可选对象（[optional.general]）

```cpp run title="optional_lifetime.cpp" ok
#include <optional>
#include <cstdio>

struct Noisy {
  Noisy()  { std::puts("构造"); }
  ~Noisy() { std::puts("析构"); }
};

int main() {
  std::optional<Noisy> o;        // 什么也不打印：没有 Noisy 对象
  std::puts("emplace 之前");
  o.emplace();                   // 构造
  o.reset();                     // 析构
  std::puts("main 结束");
}
```

`o` 的生存期从第一行就开始了，但里面没有任何 `Noisy` 对象，不是一个默认值，而是没有对象。直到 `emplace` 才构造出一个，`reset` 又把它销毁，`o` 本身仍然活着。

!!! std "[optional.general]/1"
    An *optional object* is an object that contains the storage for another object and manages the lifetime of this contained object, if any.

¶1 **可选对象**（optional object）内含另一个对象的存储，并管理这个被包含对象（如果有的话）的生存期。被包含对象可以在可选对象初始化之后才初始化，也可以在可选对象销毁之前就销毁，它是否存在由可选对象自己跟踪。

这几句话对应三个实际的性质：

1. 存储是内嵌的。`sizeof(optional<T>)` 至少是 `sizeof(T)`，通常再加一个 `bool` 和对齐填充，没有堆分配，也没有间接层。
2. 被包含对象的生存期独立于 `optional`。[[optional.optional]] 用一个联合体成员 *val* 描述存储，有值当且仅当 *val* 是联合体的活跃成员（[[class.union]]）。
3. 状态由 `optional` 跟踪。典型实现用一个 `bool` 记录 *val* 是否存在，以便在析构、复制、赋值时做正确的事。`optional<T&>` 则直接用空指针表示无值（[[optional.optional.ref]]）。

在 `optional` 之前，表达可能没有值通常用哨兵值（`-1`、`npos`）、指针（谁拥有它不清楚，往往还要一次堆分配）或 `std::pair<T, bool>`（要求 `T` 可默认构造，没有值时也构造了一个 `T`）。`optional` 把这些问题都解决了。

## nullopt_t 为什么不能从 {} 构造（[optional.nullopt]）

```cpp ok
#include <optional>
void f() {
  std::optional<int> o = 5;
  o = {};    // OK: o 变为无值
}
```

¶1 `nullopt_t` 是一个空类，用作无值状态的标记：`optional<T>` 有一个以 `nullopt_t` 为唯一形参的构造函数，构造一个无值的 `optional`。`nullopt` 是它的常量对象，初始化器未指定。

!!! std "[optional.nullopt]/2"
    Type `nullopt_t` does not have a default constructor or an initializer-list constructor, and is not an aggregate.

¶2 规定 `nullopt_t` 没有默认构造函数，没有初始化器列表构造函数，也不是聚合，所以不能从 `{}` 构造。原因在 `o = {}` 这样的表达式上。`optional` 有 `operator=(nullopt_t)`、`operator=(const optional&)`、`operator=(optional&&)` 等多个赋值运算符。如果 `nullopt_t` 是普通的 `struct nullopt_t {};`，`{}` 既能构造 `nullopt_t`，也能构造 `optional`，两个转换序列都是用户定义转换、用的又是不同的构造函数，无法比较优劣，调用二义：

```cpp error
struct N {};                     // 假想的 nullopt_t：能从 {} 构造
struct Opt {
  Opt() {}
  Opt(N) {}
  Opt& operator=(N);
  Opt& operator=(const Opt&);
  Opt& operator=(Opt&&);
};
void g(Opt o) { o = {}; }        // error: operator= 二义
```

`nullopt_t` 不能从 `{}` 构造，`operator=(nullopt_t)` 对 `o = {}` 就不可行。剩下的复制赋值和移动赋值中，移动赋值更好（右值绑定到右值引用优先，[[over.ics.rank]]），右侧是一个值初始化的空 `optional`，所以 `o` 被清空。另一个候选 `operator=(U&&)` 被它自己的约束排除了，见 [[optional.optional]] 的赋值一节。

¶2 还要求 `nullopt_t` 满足 `copyable` 和 `three_way_comparable<strong_ordering>`：可以复制 `nullopt`，两个 `nullopt_t` 比较总是相等。

!!! impl "libc++ 怎样让用户造不出 nullopt_t"
    libc++ 的 `nullopt_t` 只有一个 `explicit` 构造函数，接受两个嵌套的标签类型 `__secret_tag`，`nullopt` 用 `nullopt_t{nullopt_t::__secret_tag{}, nullopt_t::__secret_tag{}}` 初始化。用户代码不会写出这样的调用。

## 比较运算符

所有比较规则可以归结为一句：**无值比任何值都小，并且只和无值相等**。形式上分三组。

```cpp run title="cmp.cpp" ok
#include <cassert>
#include <compare>
#include <optional>

int main() {
  std::optional<int> none, zero = 0, one = 1;
  assert(none < zero);              // 无值小于任何值
  assert(none < -1000);             // 和 T 比较也一样
  assert(zero == 0 && one != 0);
  assert(none != 0);                // 无值不等于任何值
  assert(none == std::nullopt);
  assert((none <=> std::nullopt) == 0);
  assert((zero <=> none) > 0);
  std::optional<long> l = 1;
  assert(one == l);                 // optional<int> 与 optional<long> 可比较
}
```

### optional 与 optional（[optional.relops]）

六个关系运算符都是 `template<class T, class U>`，所以 `optional<int>` 可以和 `optional<long>` 比较。以 `operator<` 为例：¶7 要求 `*x < *y` 良构且结果可转换为 `bool`；¶8 规定 `y` 无值时返回 `false`，否则 `x` 无值时返回 `true`，否则返回 `*x < *y`。其余运算符（¶1–¶18）按同一张真值表定义：

| `x` | `y` | `x == y` | `x < y` | `x <= y` | `x > y` | `x >= y` |
|---|---|---|---|---|---|---|
| 无值 | 无值 | `true` | `false` | `true` | `false` | `true` |
| 无值 | 有值 | `false` | `true` | `true` | `false` | `false` |
| 有值 | 无值 | `false` | `false` | `false` | `true` | `true` |
| 有值 | 有值 | `*x == *y` | `*x < *y` | `*x <= *y` | `*x > *y` | `*x >= *y` |

每个运算符各自转发到 `T` 的同名运算符：`x <= y` 用的是 `*x <= *y`，而不是 `!(*y < *x)`。对浮点 NaN 和只定义了部分运算符的类型，这很重要，`optional` 不给 `T` 强加它没有的相等或序关系。注 1 特意说明 `T` 不必满足 *Cpp17EqualityComparable*。

这些要求都是 *Constraints*：`*x < *y` 无效时，`operator<` 只是不参与重载决议，`requires { a < b; }` 得到 `false`，而不是硬错误。各段的 *Remarks* 规定，只有当 `*x < *y` 等是核心常量表达式时，对应的特化才是 constexpr 函数。

¶19 `operator<=>` 要求 `U` 满足 `three_way_comparable_with<T>`，两者都有值时返回 `*x <=> *y`，否则返回 `x.has_value() <=> y.has_value()`。用 `bool` 的比较正好编码了无值最小。

### optional 与 nullopt（[optional.nullops]）

这一组只有两个函数，都是 `noexcept` 的，不要求 `T` 有任何比较能力：

- ¶1 `operator==(const optional<T>& x, nullopt_t)` 返回 `!x`；
- ¶2 `operator<=>(const optional<T>& x, nullopt_t)` 返回 `x.has_value() <=> false`，类型是 `strong_ordering`。

C++17 时这里有 12 个函数（6 个运算符、两个方向）。C++20 起 `nullopt == x`、`x != nullopt`、`x < nullopt` 等都由重写候选从这两个函数得到（[[over.match.oper]]）。

### optional 与 T（[optional.comp.with.t]）

`optional<T>` 可以直接和一个普通值比较，两个方向各 6 个运算符，再加一个 `<=>`。效果和上面的真值表一致：`x` 有值时比较 `*x` 和 `v`，无值时按无值最小处理。

¶1–¶24 每个函数的约束都以 `U`（或另一方向的 `T`）**不是** `optional` 的特化开头。没有这一条，`optional<int> == optional<long>` 除了匹配 [optional.relops] 的版本，还能匹配这里的 `operator==(const optional<T>&, const U&)`，其中 `U = optional<long>`；检查它的约束又要看 `*x == optional<long>`，也就是 `int == optional<long>`，又回到这一组。排除 `optional` 特化切断了这种来回。

¶25 `operator<=>` 的约束是 `!is-derived-from-optional<U> && three_way_comparable_with<T, U>`。说明专用概念 *is-derived-from-optional* 检查 `U` 能否绑定到某个 `const optional<X>&`，即 `U` 是 `optional` 的特化或公开派生自某个 `optional`。它排除的范围更宽：派生自 `optional` 的类型能隐式转换成 `const optional<X>&`，应当交给 optional 与 optional 的版本处理，否则检查 `three_way_comparable_with<T, U>` 时又会考虑这个模板本身，约束会依赖自己。¶25 的效果是 `x.has_value() ? *x <=> v : strong_ordering::less`。

## swap 与 make_optional（[optional.specalg]）

¶1–¶2 非成员 `swap(x, y)` 调用 `x.swap(y)`，异常规格与之相同。约束是 `is_reference_v<T> || (is_move_constructible_v<T> && is_swappable_v<T>)`，前一支是为 `optional<T&>` 准备的：交换两个 `optional<T&>` 只交换内部的指针，不要求 `T` 可交换。

`make_optional` 有三个重载：

- ¶4 `make_optional(v)` 返回 `optional<decay_t<T>>(std::forward<T>(v))`；
- ¶5 `make_optional<T>(args...)` 返回 `optional<T>(in_place, args...)`；
- ¶6 `make_optional<T>(il, args...)` 返回 `optional<T>(in_place, il, args...)`。

¶3 {{c++26}} 第一个重载有一条特别的约束：调用时没有使用以类型模板实参开头的显式模板实参列表。也就是说，写了 `make_optional<X>(...)` 就永远不会选中第一个重载。

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

没有这条约束时，`make_optional<int&>(x)` 能以 `T = int&` 选中第一个重载，返回类型 `optional<decay_t<int&>>` 却是 `optional<int>`：明确写了 `int&`，拿到的却是一份复制。C++26 有了 `optional<T&>` 之后，这种静默退化不能接受。

有了 C++17 的 CTAD，`make_optional` 已经不太需要：`std::optional o = x;` 和 `std::optional<T>(std::in_place, args...)` 更直接。

## hash（[optional.hash]）

¶1 `hash<optional<T>>` 当且仅当 `hash<remove_const_t<T>>` 启用时启用（启用的含义见 [[unord.hash]]）。对有值的 `o`，`hash<optional<T>>()(o)` 必须等于 `hash<remove_const_t<T>>()(*o)`，所以 `unordered_set<optional<int>>` 中有值元素的散列和 `unordered_set<int>` 一致。对无值的 `o`，结果是未指定的值；libc++ 返回 0。成员函数不保证是 `noexcept` 的。

!!! lawyer "hash<optional<int&>>"
    对 `T = int&`，`remove_const_t<T>` 就是 `int&`，`hash<int&>` 不是启用的特化。按字面读，`hash<optional<int&>>` 是禁用的，C++26 加入 `optional<T&>` 时没有为它补上散列支持。libc++ 23 与此一致：`std::hash<std::optional<int&>>` 不可默认构造。不要假设 `unordered_set<optional<T&>>` 能用。

## bad_optional_access（[optional.bad.access]）

```cpp
class bad_optional_access : public exception {
public:
  constexpr const char* what() const noexcept override;
};
```

¶1 对无值的 `optional` 调用 `value()` 时，抛出的就是这个类型的异常。¶2 `what()` 返回实现定义的字符串；常量求值期间，这个字符串按普通字面量编码。它是 `constexpr` 的，因为 C++26 允许在常量求值中抛出和捕获异常。

它直接派生自 `std::exception`，不是 `std::logic_error`，所以 `catch (const std::logic_error&)` 抓不到它。

## 头文件概要（[optional.syn]）

`<optional>` 的概要标注为 mostly freestanding：在**独立实现**（不依赖操作系统的实现，见 [[g:freestanding-implementation|freestanding implementation]]）中，绝大部分也要提供。`optional` 和 `optional<T&>` 是 partially freestanding 的类：会抛出 `bad_optional_access` 的 `value()` 在独立实现中是弃置的，只能用 `operator*`、`value_or` 这些不抛异常的接口（[[P2407]]）。

概要中值得注意的还有三个变量模板特化 {{c++26}}：

- `ranges::enable_view<optional<T>>` 为 `true`：`optional` 是一个最多含一个元素的视图，可以用于范围 `for`（见 [[optional.optional]] 的迭代器）；
- `format_kind<optional<T>>` 为 `range_format::disabled`：`optional` 虽然是范围，`std::format` 不按范围格式化它，否则 `optional<int>{1}` 会被打印成 `[1]`（[[P3168]]）；
- `ranges::enable_borrowed_range<optional<T&>>` 为 `true`：`optional<T&>` 的迭代器指向外部对象，`optional<T&>` 本身销毁后不会悬垂。

推导指引 `optional(T) -> optional<T>` 在 [[optional.optional]] 中。它按值推导，所以 `std::optional o = 1;` 是 `optional<int>`，`std::optional s = "abc";` 是 `optional<const char*>`。

!!! history
    `optional` 源自 Boost.Optional，先进入 Library Fundamentals TS，再随 [[P0220R1]] 进入 C++17。早期提案包含 `optional<T&>`，因为对它赋值应当改绑还是写穿有争议而被删去，直到 C++26 的 [[P2988]] 才重新加入（[[optional.optional.ref]]）。C++20 用 `<=>` 和重写候选大幅精简了比较运算符。C++23 加入 `and_then`、`transform`、`or_else`（[[P0798]]）。C++26 加入范围支持（[[P3168]]）、`optional<T&>`、部分 freestanding（[[P2407]]）和 `make_optional` 的显式实参约束。

## 常见误解

!!! pitfall "optional<bool> 上的 == false 和 !"
    `std::optional<bool> b = false;` 时，`b == false` 比较的是值，为 `true`；`!b` 检查的是有没有值，为 `false`。`optional<T*>` 上的 `opt == nullptr` 和 `!opt` 同样是两回事。

!!! pitfall "bad_optional_access 是 logic_error"
    它直接派生自 `std::exception`。按 `logic_error` 捕获会漏掉它。

## 思考题

!!! question "思考题 1"
    `std::optional<double> a = NAN, b = NAN;` 中 `a <= b` 与 `!(b < a)` 的结果为什么不同？标准为什么不用后者定义前者？

<details markdown="1">
<summary>答案</summary>

两者都有值，按 [optional.relops] ¶14，`a <= b` 是 `*a <= *b`，有 NaN 参与的比较都为 `false`；`!(b < a)` 是 `!false`，为 `true`。

标准让每个运算符转发到 `T` 的同名运算符，就是为了不给 `T` 强加全序假设。`optional<T>` 的比较是 `T` 的比较的扩展，两边都有值时与 `T` 的行为完全一样。
</details>

!!! question "思考题 2"
    `std::optional<int> o = 5; o = {};` 中，`operator=(U&&)` 为什么没有被选中？如果选中了会怎样？

<details markdown="1">
<summary>答案</summary>

`operator=(U&&)` 的模板形参有默认实参 `U = remove_cv_t<T>`，花括号列表无法推导 `U`，于是取默认的 `int`。[[optional.optional]] 中它的约束要求 `T` 是标量且 `decay_t<U>` 就是 `T` 时不参与重载决议（[optional.assign] ¶14.2），正好排除了这种情况。

如果选中它，`{}` 会值初始化一个 `int` 0，`o` 变成有值的 0，而不是被清空。同样写法下 `optional<int>` 和 `optional<std::string>` 行为就会不一致，这条约束保证了 `o = {}` 总是清空。
</details>
