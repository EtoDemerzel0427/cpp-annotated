---
title: 比较概念
summary: 说明专用概念 boolean-testable 的来龙去脉（为什么不直接要求 convertible_to<bool>、"取消资格的声明"到底在防什么）、跨类型比较所依赖的 comparison-common-type-with 与 CONVERT_TO_LVALUE、equality_comparable(_with) 与 totally_ordered(_with) 的语法与语义要求。
status: done
covers: *
since: c++20
papers: P0898R3, P1964R2, P2404R3
related: concepts, concepts.lang, cmp.concept, class.compare, expr.log.and, expr.log.or, over.match.oper, basic.lookup.argdep
tags: 标准库, 概念, 比较, boolean-testable, equality_comparable, totally_ordered
updated: 2026-10-18
---

[concepts.compare] 描述"在可能不同的对象类型的值之间建立关系与顺序"的概念（[concepts.compare.general] ¶1）。表面上只有四个公开概念——`equality_comparable`、`equality_comparable_with`、`totally_ordered`、`totally_ordered_with`——但它们站在两个说明专用（exposition-only）的地基上：

- *`boolean-testable`*：比较运算的结果"像 `bool` 一样可用"意味着什么；
- *`comparison-common-type-with`*：两个不同类型的值"在同一个值域里比较"意味着什么。

`<compare>` 中的 `three_way_comparable(_with)`（[[cmp.concept]]）也直接复用这两块地基，以及在那里定义的 *`partially-ordered-with`*。

阅读前提：[[concepts]]（保持相等性、满足 vs 建模）、[[concept.commonref]]（公共引用）。

## *CONVERT_TO_LVALUE*（[concepts.compare.general] ¶2）

对表达式 `E` 和类型 `C`，*`CONVERT_TO_LVALUE`*`<C>(E)` 定义为：

- ¶2.1：若有效，则为 `static_cast<const C&>(as_const(E))`；
- ¶2.2：否则为 `static_cast<const C&>(std::move(E))`。

它只出现在语义要求中，用来表达"把 `E` 转换到公共引用类型 `C` 后再比较"。优先从 const 左值转换（不移动源对象）；只有 const 左值不能转换时（例如只能从右值构造 `C`），才退而从右值转换。这个两步定义是为了支持**仅可移动**（move-only）类型，见下文的历史部分。

## *boolean-testable*（[concept.booleantestable]）

### 问题：`convertible_to<bool>` 不够

（术语速查：[[g:boolean-testable]]。）

C++20 之前，库对比较结果的要求通常是"可以按语境转换为 `bool`"（*contextually convertible to bool*）。但泛型代码对比较结果做的事远不止 `if (a == b)`，它还会写：

```cpp
if (!(a < b) && pred(x)) ...
return a == b || c == d;
```

如果 `a == b` 返回一个自定义类型 `R`，那么：

- `!r` 调用的可能是 `R::operator!`，返回一个奇怪的东西；
- `r1 && r2` 调用的可能是用户重载的 `operator&&`——**失去短路求值**（[[expr.log.and]]），而且返回值可能根本不是布尔语义。

所以"能转换为 `bool`"不足以保证泛型代码中的逻辑运算符按"常规语义"工作。¶1 正是这个意思：*`boolean-testable`* 规定了可转换为 `bool`、并且逻辑运算符 `&&`、`||`、`!` 具有常规语义的表达式需要满足什么。

### 语法部分（¶1、¶6）

```cpp
template<class T>
  concept boolean-testable-impl = convertible_to<T, bool>;  // exposition only

template<class T>
  concept boolean-testable =                                  // exposition only
    boolean-testable-impl<T> && requires(T&& t) {
      { !std::forward<T>(t) } -> boolean-testable-impl;
    };
```

编译器只检查两件事：`T` 能（隐式且显式地）转换为 `bool`；`!t` 的结果也能转换为 `bool`。

注意：**`&&` 和 `||` 不在语法要求里**。它们被放进了语义要求——因为"不存在会劫持 `&&` 的重载"这件事无法用 requires 表达式表达（你无法在 requires 表达式里写"这个调用必须选中内建运算符"）。

### 语义部分：取消资格的声明（¶2–¶5）

¶2：设 `e` 的 `decltype((e))` 为 `T`。`T` **建模** *`boolean-testable-impl`* 仅当：

- ¶2.1：`remove_cvref_t<T>` 不是类类型，或者在它的作用域里查找 `operator&&` 与 `operator||` 什么也找不到（即没有成员形式的重载）；并且
- ¶2.2：以 `T` 为唯一实参类型对 `operator&&`、`operator||` 进行**实参依赖查找**（[[basic.lookup.argdep]]）找不到任何**取消资格的声明**（*disqualifying declaration*）。

¶3–¶5 用三个层层递进的定义刻画"取消资格的声明"：

1. **取消资格的形参**（¶3）：声明类型为 `P` 的函数形参，且
    - ¶3.1：`P` 不依赖模板参数，并且存在从 `e` 到 `P` 的隐式转换序列（[[over.best.ics]]）——这个非模板重载有可能接受 `e`；或
    - ¶3.2：`P` 依赖模板参数，并且要么 ¶3.2.1 `P` 中没有参与推导的模板参数，要么 ¶3.2.2 以 `e` 为实参的函数调用模板实参推导（[[temp.deduct.call]]）成功——这个模板重载有可能接受 `e`。
2. **关键形参**（*key parameter*，¶4）：函数模板 `D` 中类型为 `cv X`（或其引用）的形参，`X` 是某个类模板的特化，该类模板与 `D` 有相同的最内层非内联命名空间，且 `X` 至少含一个参与推导的模板参数。例 1 中 `Z::operator&&(C<T> x, T y)` 有一个关键形参 `C<T> x`；`Z::operator||(C<type_identity_t<T>> x, T y)` 没有（`type_identity_t<T>` 处于非推导语境）。
3. **取消资格的声明**（¶5）：
    - ¶5.1：含至少一个取消资格形参的**非模板**函数声明；或
    - ¶5.2：含至少一个取消资格形参的**函数模板**声明，并且 ¶5.2.1 至少一个取消资格形参是关键形参，或 ¶5.2.2 声明没有任何关键形参，或 ¶5.2.3 它声明的函数模板没有绑定任何名字（[[dcl.meaning]]）。

¶6 注 1 说明意图：对两个都建模 *`boolean-testable-impl`* 的类型 `T1`、`T2`，`declval<T1>() && declval<T2>()` 与 `||` 必须决议到**内建**运算符。

为什么规则这么复杂，而不是简单地说"`&&` 必须选中内建运算符"？因为后者需要知道**另一个**操作数的类型——而概念只拿到一个类型 `T`。¶2–¶5 的设计是一种"单类型的保守近似"：只看与 `T` 相关的那些重载，只要它们中的任何一个**有可能**在与某个其他 boolean-testable 类型组合时被选中，就取消 `T` 的资格。关键形参的规则则是为了不误伤：像 `Z::operator&&(C<T>, T)` 这种只对特定类模板生效的运算符模板，如果 `e` 根本推导不出来，就不算数。

### ¶7：`!` 的语义

`T` 建模 *`boolean-testable`* 仅当 `bool(e) == !bool(!e)`——`!` 必须真的是"取反"。

¶8 例 2：`bool`、`true_type`、`int*`、`bitset<N>::reference` 都建模 *`boolean-testable`*。

### 满足但不建模的例子

```cpp run title="boolean-testable.cpp" ok
#include <concepts>
#include <cstdio>

// == 返回一个重载了 && 的类型
struct Weird {
  bool b;
  operator bool() const { return b; }
  friend Weird operator&&(Weird, Weird) { std::puts("user &&"); return {false}; }
};
struct X {
  int v;
  friend Weird operator==(X a, X b) { return {a.v == b.v}; }
  friend Weird operator!=(X a, X b) { return {a.v != b.v}; }
};
static_assert(std::equality_comparable<X>);   // 满足：&& 不在语法要求里
                                              // 但 ADL 找到取消资格的 operator&& → 不建模

// ! 被删除：连语法都不满足
struct NoBang { operator bool() const { return true; } void operator!() const = delete; };
struct Y {
  friend NoBang operator==(Y, Y) { return {}; }
  friend NoBang operator!=(Y, Y) { return {}; }
};
static_assert(!std::equality_comparable<Y>);

int main() {}
```

`X` 满足 `equality_comparable` 但不建模（经由 *`boolean-testable`* 的语义要求），把它交给任何依赖 `equality_comparable` 的库组件都是 {{ifndr}}（[[res.on.requirements]]）。

!!! history
    *`boolean-testable`* 由 [[P1964R2]] 在 C++20 定稿前引入，取代了 Ranges TS/早期 C++20 草案中一个名为 `boolean` 的**公开**概念。旧的 `boolean` 试图用语法要求穷举 `&&`、`||`、`!`、`==`、`!=` 在各种类型组合下的结果，导致定义庞大、编译慢，而且仍然不能阻止 `&&` 被劫持。新方案把语法要求压缩到最小，把"不得劫持"移入语义要求，并降为说明专用概念——用户不能直接使用它。

!!! impl "libc++ 的实现"
    libc++ 在 `<__concepts/boolean_testable.h>` 中把它实现为 `__boolean_testable_impl`（`convertible_to<_Tp, bool>`）和 `__boolean_testable`，与标准的语法部分逐字对应；语义部分（取消资格的声明）当然无法、也没有被检查。

## *comparison-common-type-with*（[concept.comparisoncommontype]）

```cpp
template<class T, class U, class C = common_reference_t<const T&, const U&>>
  concept comparison-common-type-with-impl =   // exposition only
    same_as<common_reference_t<const T&, const U&>,
            common_reference_t<const U&, const T&>> &&
    requires {
      requires convertible_to<const T&, const C&> || convertible_to<T, const C&>;
      requires convertible_to<const U&, const C&> || convertible_to<U, const C&>;
    };

template<class T, class U>
  concept comparison-common-type-with =        // exposition only
    comparison-common-type-with-impl<remove_cvref_t<T>, remove_cvref_t<U>>;
```

它表达的是：`T` 与 `U` 之间有一个公共的"比较域" `C`（`const T&` 与 `const U&` 的公共引用），双方都能转换到 `const C&`——优先从 const 左值，退而从右值。

¶1 语义要求（与 [[concept.commonref]] 平行）：对 `remove_cvref_t<T>` 的保持相等性的左值 `t1`、`t2`，*`CONVERT_TO_LVALUE`*`<C>(t1)` 等于 *`CONVERT_TO_LVALUE`*`<C>(t2)` **当且仅当** `t1` 等于 `t2`；对 `u` 同理。即转换到比较域是保持相等的单射。

!!! history "为什么不直接用 `common_reference_with`"
    C++20 原始定义中，`equality_comparable_with<T, U>` 要求 `common_reference_with<const T&, const U&>`，后者要求 `convertible_to<const T&, common_reference_t<...>>`。对 `unique_ptr<int>` 与 `nullptr_t`，公共引用是 prvalue 类型 `unique_ptr<int>`，从 `const unique_ptr<int>&` 转换过去需要**复制**——仅可移动类型因此不满足，尽管 `p == nullptr` 显然是有意义的比较。[[P2404R3]]（C++23）引入 *`comparison-common-type-with`* 与 *`CONVERT_TO_LVALUE`*，把要求放宽为"能绑定到 `const C&`"，并同样修改了 `totally_ordered_with` 与 `three_way_comparable_with`。

## `equality_comparable`（[concept.equalitycomparable]）

### *weakly-equality-comparable-with*（¶1）

```cpp
template<class T, class U>
  concept weakly-equality-comparable-with = // exposition only
    requires(const remove_reference_t<T>& t, const remove_reference_t<U>& u) {
      { t == u } -> boolean-testable;
      { t != u } -> boolean-testable;
      { u == t } -> boolean-testable;
      { u != t } -> boolean-testable;
    };
```

四个方向都要可用、结果都要 *`boolean-testable`*。在 C++20 之后，由于重写候选（[[over.match.oper]]、[[class.compare]]），只定义一个 `operator==` 就能让四个表达式都有效。

¶1 语义要求：四个表达式**定义域相同**（¶1.1）；`u == t` 与 `t == u` 结果相同（¶1.2，对称）；`t != u` 是 `t == u` 的否定（¶1.3）；`u != t` 与 `t != u` 结果相同（¶1.4）。

### `equality_comparable<T>`（¶2–¶3）

```cpp
template<class T>
  concept equality_comparable = weakly-equality-comparable-with<T, T>;
```

!!! std
    T models equality_comparable only if bool(a == b) is true when a is equal to b, and false otherwise.

    `T` 建模 `equality_comparable` 仅当：`a` 与 `b` **相等**时 `bool(a == b)` 为 `true`，否则为 `false`。

这是整个概念库中把"抽象的相等"与"`==` 运算符"连接起来的那一条：`==` 必须**精确地**反映值的相等（[[concepts.equality]]）。¶3 注 1：由于 `a == b` 被要求保持相等性，可以推出 `==` 是传递的、对称的——结合本条（`a` 与自身相等，所以 `a == a` 为真）就得到了等价关系。

后果：

- `double` 满足 `equality_comparable`，也建模它——NaN 不在 `==` 的定义域内（[[structure.requirements#8]]），不影响建模；但如果你的数据里有 NaN，就不能指望依赖 `equality_comparable` 的算法给出有意义的结果。
- 一个"按名字忽略大小写比较"的 `==` 只有在"忽略大小写后相同"本来就是该类型的**值相等**时才建模它——即该类型的其他保持相等性的操作（例如 `name()` 访问器）也必须不能区分大小写不同的两个对象，否则 `a == b` 为真但 `a.name() != b.name()`，违反了 `==` 与"相等"的对应。

### `equality_comparable_with<T, U>`（¶4）

```cpp
template<class T, class U>
  concept equality_comparable_with =
    equality_comparable<T> && equality_comparable<U> &&
    comparison-common-type-with<T, U> &&
    equality_comparable<common_reference_t<const remove_reference_t<T>&,
                                           const remove_reference_t<U>&>> &&
    weakly-equality-comparable-with<T, U>;
```

跨类型的相等比较不是"有个 `operator==(T, U)` 就行"。它要求：

1. 两边**各自**都是 `equality_comparable` 的；
2. 存在公共比较域 `C`，且 `C` 本身也是 `equality_comparable` 的；
3. 跨类型的四个运算都可用。

¶4 语义要求：设 `t`、`t2` 是表示**不同但相等**对象的左值（类型分别为 `const remove_reference_t<T>` 与 `remove_cvref_t<T>`），`u`、`u2` 同理，则

```cpp
bool(t == u) == bool(CONVERT_TO_LVALUE<C>(t2) == CONVERT_TO_LVALUE<C>(u2))
```

即**跨类型比较的结果必须与"都转换到公共类型后再比较"一致**。这条要求把"`string == const char*`"这类混合比较的含义钉死为"按 `string` 的值比较"，而不是比较指针或者别的什么。

```cpp run title="equality-comparable-with.cpp" ok
#include <concepts>
#include <memory>
#include <string>
#include <string_view>

static_assert(std::equality_comparable_with<std::string, const char*>);
static_assert(std::equality_comparable_with<std::string, std::string_view>);
static_assert(!std::equality_comparable_with<int, std::string>);
static_assert(std::equality_comparable_with<std::unique_ptr<int>, std::nullptr_t>);  // 自 P2404R3 起

int main() {}
```

（libc++ 在 `-std=c++20` 下也采用 P2404R3 之后的定义，上面最后一条同样成立。）

## `totally_ordered`（[concept.totallyordered]）

```cpp
template<class T>
  concept totally_ordered = equality_comparable<T> && partially-ordered-with<T, T>;
```

*`partially-ordered-with`* 定义在 [[cmp.concept]]：`<`、`>`、`<=`、`>=` 在两个方向上共 8 个表达式都可用且结果 *`boolean-testable`*；其语义要求包括 8 个表达式定义域相同、`t < u` 与 `u > t` 一致、`t <= u` 与 `u >= t` 一致等。

¶1 语义要求：对 `const remove_reference_t<T>` 的左值 `a`、`b`、`c`：

- ¶1.1：**三歧性**（trichotomy）：`a < b`、`a > b`、`a == b` 恰有一个为真；
- ¶1.2：`<` **传递**；
- ¶1.3：`a <= b` 等价于 `!(b < a)`；
- ¶1.4：`a >= b` 等价于 `!(a < b)`。

三歧性加上 `==` 的"等于即相等"，意味着 `<` 是**全序**：任意两个不相等的值必可比较。这比 `strict_weak_order`（[[concept.strictweakorder]]）严格——后者允许"不可区分但不相等"的等价类。

`totally_ordered_with<T, U>`（¶2）的结构与 `equality_comparable_with` 平行：双方各自全序、可跨类型相等比较、公共比较域全序、跨类型的 8 个运算可用；语义要求 ¶2.1–¶2.8 逐一规定跨类型的 `<`、`>`、`<=`、`>=`（两个方向）必须与"转换到 `C` 后比较"一致。

```cpp run title="totally-ordered.cpp" ok
#include <concepts>
#include <cmath>

static_assert(std::totally_ordered<double>);           // 满足，也建模：NaN 只是不在定义域内
static_assert(std::totally_ordered_with<int, double>);

int main() {
    double nan = std::nan("");
    // nan < 1.0、nan > 1.0、nan == 1.0 全为 false，违反三歧性——
    // 但这只说明 NaN 不在定义域内（[structure.requirements]/8）。
    return (nan < 1.0 || nan > 1.0 || nan == 1.0) ? 1 : 0;
}
```

## 陷阱

!!! pitfall "返回自定义类型的比较运算符"
    表达式模板库（如某些线性代数库、SQL DSL）让 `a == b` 返回一个"延迟求值的表达式"，并重载 `&&`、`||` 来拼接表达式。这些类型可以满足 `equality_comparable`（只要结果能转 `bool`、`!` 也行），但几乎必然不建模 *`boolean-testable`*。把这样的类型放进 `ranges::find`、`ranges::sort` 是 IFNDR。

!!! pitfall "只为一个方向提供异质比较"
    C++20 之前写 `bool operator==(const S&, const char*)` 还需要写反方向和 `!=`。C++20 的重写候选会自动补齐，所以 `weakly-equality-comparable-with` 通常自动满足——但前提是你写的是 `operator==` 而不是只写了 `operator!=`；`!=` 不会被用来重写 `==`。

!!! pitfall "跨类型比较与公共类型不一致"
    如果 `S == int` 比较的是 `S::id`，而 `common_reference_t<const S&, const int&>`（通过某个转换）却得到别的东西，`equality_comparable_with<S, int>` 就满足但不建模。为一对类型定义异质比较时，应当同时确保它们的公共类型给出同样的结论，或者干脆不要提供能产生公共类型的隐式转换。

## 思考题

!!! question "思考题"
    1. 为什么 *`boolean-testable`* 的语法部分要求 `{ !std::forward<T>(t) } -> boolean-testable-impl`，却不要求 `!t` 本身也是 *`boolean-testable`*（递归）？
    2. `std::equality_comparable_with<int, double>` 为真吗？它的语义要求被建模吗（考虑大整数）？
    3. 一个类型只定义了 `operator<=>`（`= default`），没有定义 `operator==`，它满足 `totally_ordered` 吗？

<details markdown="1">
<summary>展开查看答案与解析</summary>

1. 递归定义会导致无限展开（`!!t`、`!!!t`……）。标准只要求一层：`!t` 的结果能转换为 `bool` 即可；语义要求 ¶7 `bool(e) == !bool(!e)` 保证这一层的含义正确。至于对 `!t` 的结果再做 `&&`，它的资格由 ¶2 对**那个**类型的要求决定——但那是另一个类型，标准在这里刻意止步。
2. 为真：公共引用是 `double`，四个比较都可用。是否建模取决于"相等"的定义域：`int` 都能精确表示为 IEEE 双精度（`int` 为 32 位时），所以转换到 `double` 是保持相等的单射，比较结果与"转换后比较"一致——被建模。若是 `long long` 与 `double`，超过 2^53 的值转换后会合并，转换不再是单射，`comparison-common-type-with` 的语义要求（¶1）被违反。
3. 满足。按 [[class.compare.default]]，`= default` 的 `operator<=>` 会隐式声明一个 `= default` 的 `operator==`；于是 `==`、`!=`（重写）、`<` 等（经 `<=>` 重写）都可用。若是**用户提供**（非 defaulted）的 `operator<=>`，则不会隐式声明 `==`，`equality_comparable` 不满足，`totally_ordered` 也就不满足。
</details>

## 小结

!!! summary
    - *`CONVERT_TO_LVALUE`*`<C>(E)`：转到 `const C&`，优先从 const 左值，否则从右值——为仅可移动类型而设。
    - *`boolean-testable`*：语法上只要求可转 `bool`、`!` 的结果可转 `bool`；语义上要求 `&&`、`||` 必然决议到内建运算符（由"取消资格的声明"刻画）且 `!` 真的是取反。
    - *`comparison-common-type-with`*：对称的公共引用 `C`，双方可绑定到 `const C&`，且转换是保持相等的单射（[[P2404R3]]，C++23）。
    - `equality_comparable`：`==` 精确反映值相等 ⇒ 等价关系；`_with` 版本要求跨类型比较与"转到公共类型后比较"一致。
    - `totally_ordered`：在 `equality_comparable` 之上要求三歧性、传递性和 `<=`/`>=` 与 `<` 的一致性；NaN 不在定义域内，不影响 `double` 建模它。
