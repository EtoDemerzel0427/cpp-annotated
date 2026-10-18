---
title: 语言相关概念
summary: same_as、derived_from、convertible_to、common_reference_with、common_with、integral 族、assignable_from、swappable（及 ranges::swap 定制点对象）、destructible、constructible_from、default_initializable、move/copy_constructible——每个概念的精确定义、语义要求、为何如此设计，以及它们与核心语言规则的对应。
status: done
covers: *
since: c++20
papers: P0898R3
related: concepts, concepts.object, concepts.compare, temp.constr.order, conv, dcl.init, expr.static.cast, class.derived, customization.point.object, meta.trans.other
tags: 标准库, 概念, convertible_to, common_reference, swap, CPO
updated: 2026-10-18
---

[concepts.lang] 收录的是"对应语言特性"的概念（[concepts.lang.general] ¶1）：类型之间的关系（同一、派生、可转换、有公共引用/公共类型）、类型分类（整数、浮点）、以及最基本的对象操作（赋值、交换、析构、构造）。它们是 [[concepts.object]] 中 `movable`/`copyable`/`regular` 的积木。

很多概念看起来只是给 `<type_traits>` 套了一层壳，但这层壳有两个实打实的作用：

1. **可包含**。类型特征直接写进约束时是孤立的原子约束，彼此无法比较（[[temp.constr.order]]）；包进概念后，引用同一概念的约束才能参与包含。
2. **附带语义要求**。`convertible_to` 不只是 `is_convertible_v`，它还要求显式转换与隐式转换都可用**且结果相等**；`assignable_from` 不只是"能赋值"，还要求赋值返回左操作数本身、赋值后两边相等……

阅读前提：[[concepts]] 中"满足 vs 建模"与"保持相等性"。

## `same_as`（[concept.same]）

```cpp
template<class T, class U>
  concept same-as-impl = is_same_v<T, U>;       // exposition only
template<class T, class U>
  concept same_as = same-as-impl<T, U> && same-as-impl<U, T>;
```

为什么要写两遍？注 1：这样 `same_as<T, U>` 包含 `same_as<U, T>`，反之亦然。

规范化后，`same_as<T, int>` 变成两个原子约束 `is_same_v<T, int>` ∧ `is_same_v<int, T>`（两者都来自 *same-as-impl* 定义中的同一个表达式 `is_same_v<T, U>`，只是参数映射不同）。`same_as<int, T>` 规范化后是同样两个原子约束，只是顺序相反——合取是可交换的，所以二者互相包含。如果直接写 `is_same_v<T, int>`，`is_same_v<T, int>` 与 `is_same_v<int, T>` 是**不同表达式**，无法比较：

```cpp run title="same-as-subsumption.cpp" ok
#include <concepts>
#include <cstdio>

template<class T> void f(T) requires std::same_as<T, int>          { std::puts("#1"); }
template<class T> void f(T) requires std::same_as<int, T> && true  { std::puts("#2"); }

int main() {
    f(1);   // 选 #2：same_as<int, T> && true 包含 same_as<T, int>
}
```

把两处 `std::same_as` 换成 `std::is_same_v`，调用就变成歧义（Clang："call to 'f' is ambiguous"）。

`same_as` 不做任何退化：`same_as<int, const int>` 为假，`same_as<int&, int>` 为假。在 *type-constraint* `{ e } -> same_as<T>` 中，`decltype((e))` 被作为第一个实参，所以能精确检查值类别（左值表达式得到 `T&`）。

## `derived_from`（[concept.derived]）

```cpp
template<class Derived, class Base>
  concept derived_from =
    is_base_of_v<Base, Derived> &&
    is_convertible_v<const volatile Derived*, const volatile Base*>;
```

注 1 给出等价描述：当且仅当 `Derived` **公有且无歧义地**派生自 `Base`，或二者是忽略 cv 后相同的类类型时满足。

`is_base_of_v` 单独使用会把私有继承、歧义继承也算进来（它只看继承图）；加上指针可转换性的检查后，就排除了 [[conv.ptr]] 中派生类指针到基类指针的转换不可用的情形（不可访问或有歧义，见 [[class.derived]]）。用 `const volatile` 指针是为了让 cv 限定的类型也能工作。

```cpp run title="derived-from.cpp" ok
#include <concepts>
#include <type_traits>

struct B {};
struct D : B {};
struct P : private B {};
struct M1 : B {};
struct M2 : B {};
struct MM : M1, M2 {};            // 两个 B 子对象

static_assert(std::derived_from<D, B>);
static_assert(std::is_base_of_v<B, P> && !std::derived_from<P, B>);    // 私有继承
static_assert(std::is_base_of_v<B, MM> && !std::derived_from<MM, B>);  // 歧义基类
static_assert(std::derived_from<B, B> && std::derived_from<const B, B>);
static_assert(!std::derived_from<int, int>);                           // 非类类型

int main() {}
```

## `convertible_to`（[concept.convertible]）

### 定义：隐式与显式都要（¶1）

```cpp
template<class From, class To>
  concept convertible_to =
    is_convertible_v<From, To> &&
    requires { static_cast<To>(declval<From>()); };
```

!!! std
    convertible_to<From, To> requires E to be both implicitly and explicitly convertible to type To. The implicit and explicit conversions are required to produce equal results.

    `convertible_to<From, To>` 要求（类型与值类别同 `declval<From>()` 的）表达式 E **既能隐式又能显式**转换到 `To`，并且两种转换**结果相等**。

`is_convertible_v<From, To>` 检查的是**复制初始化**（[[g:copy-initialization]]）——相当于 `To test() { return declval<From>(); }` 合法；`static_cast<To>(E)` 检查的是**直接初始化**（[[g:direct-initialization]]，[[expr.static.cast]]）。在 C++ 中二者可以不一致：

- 只有 `explicit` 构造函数或转换函数：显式可以、隐式不行；
- 显式路径上有一个更好的、但被删除（或有歧义）的候选：隐式可以、显式不行。复制初始化不考虑 `explicit` 构造函数（[[over.match.copy]]、[[over.match.ctor]]），直接初始化考虑，所以一个 `explicit` 且被删除的构造函数只会"毒害"显式路径。

为什么两者都要？因为泛型代码的作者会随意地写 `To t = e;`、`return e;`、`To(e)`、`static_cast<To>(e)`、`To{e}`。如果一个约束只保证其中一种写法可用，那么约束检查通过后，模板体内换一种写法就可能编译失败，或者——更糟——编译通过但调用了**语义不同**的转换。`convertible_to` 把两条路径都锁死，并在语义层面要求它们给出相等结果，从而让"转换"成为一个与语法无关的概念。

```cpp run title="convertible-to.cpp" ok
#include <concepts>
#include <type_traits>

struct From {};
struct To {
    template<class T> To(T&&) {}      // 任何东西都能隐式转换过来
    explicit To(From) = delete;       // 但显式转换 From 时，这个更好的候选被选中且已删除
};
static_assert(std::is_convertible_v<From, To>);   // 复制初始化不看 explicit 构造函数
static_assert(!std::convertible_to<From, To>);    // static_cast<To>(From{}) 非良构

struct E { explicit E(int) {} };
static_assert(!std::convertible_to<int, E>);      // 只能显式
static_assert(std::constructible_from<E, int>);

static_assert(std::convertible_to<void, void>);   // void 是特例：is_convertible_v<void, void> 为真
static_assert(!std::convertible_to<int, void>);

int main() {}
```

（`static_cast<To>(From{})` 中，模板构造函数 `To(From&&)` 与 `To(From)` 的隐式转换序列都是恒等转换，无法区分，于是按 [[over.match.best]] 非模板优先，选中被删除的 `To(From)`。）

### 语义要求（¶2）

¶2 用一个虚构函数精确表述"隐式转换"：

```cpp
To test(FromR (&f)()) {
  return f();
}
```

其中 `FromR` 是 `add_rvalue_reference_t<From>`，`f` 是返回 `FromR` 的、保持相等性的无参函数。建模要求：

- ¶2.1：若 `To` 是对象类型或对象引用类型，`static_cast<To>(f())` 等于 `test(f)`——显式与隐式结果相等；
- ¶2.2：若 `FromR` 是对象引用类型：
    - ¶2.2.1：若它是对非 const 类型的右值引用，转换后被引用对象处于**有效但未指明的状态**（[[g:valid-but-unspecified-state]]，[[lib.types.movedfrom]]）——即允许"移动走"；
    - ¶2.2.2：否则，转换**不得修改**被引用的对象。

`To` 不是对象/引用类型时（例如 `void`、函数类型），¶2.1 不适用。

## `common_reference_with`（[concept.commonref]）

### 公共引用类型（¶1）

¶1 定义：若 `common_reference_t<T, U>` 良构且为类型 `C`，并且 `convertible_to<T, C>` 与 `convertible_to<U, C>` 都被**建模**，则 `T` 与 `U` 有**公共引用类型**（[[g:common-reference-type]]）`C`。注 1：`C` 可以是 `T` 或 `U` 本身，也可以是别的类型，可以是引用类型。

```cpp
template<class T, class U>
  concept common_reference_with =
    same_as<common_reference_t<T, U>, common_reference_t<U, T>> &&
    convertible_to<T, common_reference_t<T, U>> &&
    convertible_to<U, common_reference_t<T, U>>;
```

### 为什么需要"公共引用"

这个概念是为**代理迭代器**（proxy iterator）发明的。`vector<bool>::iterator` 解引用得到 `vector<bool>::reference`（一个代理对象），值类型却是 `bool`；`views::zip` 的迭代器解引用得到 `tuple<int&, double&>`，值类型是 `tuple<int, double>`。泛型算法经常需要**同时**处理"引用"和"值"——例如 `ranges::sort` 既要比较 `*it` 与 `*jt`，也要比较 `*it` 与一个临时保存的 `value_type` 变量。

`common_reference_t<R, V&>` 回答的是：**有没有一个类型，`R` 和 `V&` 都能（无损地）转换过去，从而可以在同一个函数签名里统一处理它们？** 对普通引用它退化为直觉结果，对代理类型则可以通过特化 `basic_common_reference` 来定制（¶3 注 2，[[meta.trans.other]]）。`<iterator>` 中的 `indirectly_readable` 就要求 `common_reference_with<iter_reference_t<I>&&, iter_value_t<I>&>`。

```cpp run title="common-reference.cpp" ok
#include <concepts>
#include <string>
#include <type_traits>
#include <utility>

static_assert(std::same_as<std::common_reference_t<int&, const int&>, const int&>);
static_assert(std::same_as<std::common_reference_t<int&&, int&>, const int&>);
static_assert(std::same_as<std::common_reference_t<int&, double&>, double>);  // 无公共引用，退到值
static_assert(std::common_reference_with<int&, double&>);
static_assert(!std::common_reference_with<int*, std::string>);

// pair 特化了 basic_common_reference（C++23），供 views::zip 一类代理使用
static_assert(std::same_as<std::common_reference_t<std::pair<int&, int&>, std::pair<int, int>&>,
                           std::pair<int&, int&>>);
static_assert(std::common_reference_with<std::pair<int&, int&>, std::pair<int, int>&>);

int main() {}
```

`same_as<common_reference_t<T, U>, common_reference_t<U, T>>` 这一项要求**对称性**：`common_reference` 是用户可特化的，标准不能假设特化写得对称，于是把它写进约束。

### 语义要求（¶2）

`C` 为公共引用类型，`t1`、`t2` 为类型 `T` 的保持相等性的表达式，`u1`、`u2` 同理。建模要求：

- ¶2.1：`C(t1)` 等于 `C(t2)` **当且仅当** `t1` 等于 `t2`；
- ¶2.2：`C(u1)` 等于 `C(u2)` 当且仅当 `u1` 等于 `u2`。

即：转换到 `C` 必须是**单射**且保持相等——不能把不同的值映射成相等，也不能把相等的值映射成不同。这使得"在 `C` 中比较"与"在原类型中比较"等价，是 [[concepts.compare]] 中 `equality_comparable_with` 的跨类型语义得以成立的前提。

## `common_with`（[concept.common]）

`common_with` 是 `common_reference_with` 的"值"版本：¶1 说，若 `T` 与 `U` 都能**显式**转换到某第三个类型 `C`，则它们有**公共类型**（[[g:common-type]]）`C`；注 1 说 `C` 不一定唯一。

```cpp
template<class T, class U>
  concept common_with =
    same_as<common_type_t<T, U>, common_type_t<U, T>> &&
    requires {
      static_cast<common_type_t<T, U>>(declval<T>());
      static_cast<common_type_t<T, U>>(declval<U>());
    } &&
    common_reference_with<add_lvalue_reference_t<const T>, add_lvalue_reference_t<const U>> &&
    common_reference_with<
      add_lvalue_reference_t<common_type_t<T, U>>,
      common_reference_t<add_lvalue_reference_t<const T>, add_lvalue_reference_t<const U>>>;
```

逐项拆解：

1. `common_type_t` 对称（同样因为可被特化）；
2. 两边都能**显式**转换到公共类型——只要求显式，比 `convertible_to` 宽松；
3. `const T&` 与 `const U&` 有公共引用；
4. 公共类型的左值引用与那个公共引用之间也有公共引用——保证"值的世界"与"引用的世界"是相容的。

¶2 的语义要求与 `common_reference_with` 平行：`C(t1)` 等于 `C(t2)` 当且仅当 `t1` 等于 `t2`，对 `u` 同理。¶3 注 2：可以通过特化 `common_type` 定制。

```cpp run title="common-with.cpp" ok
#include <concepts>
#include <string>
#include <type_traits>

static_assert(std::common_with<int, double>);
static_assert(std::same_as<std::common_type_t<std::string, const char*>, std::string>);
static_assert(std::common_with<std::string, const char*>);
// 第 3 项中的公共引用是 prvalue 类型 const std::string，而非引用
static_assert(std::same_as<std::common_reference_t<const std::string&, const char* const&>,
                           const std::string>);

int main() {}
```

## 算术概念（[concepts.arithmetic]）

```cpp
template<class T> concept integral         = is_integral_v<T>;
template<class T> concept signed_integral  = integral<T> && is_signed_v<T>;
template<class T> concept unsigned_integral = integral<T> && !signed_integral<T>;
template<class T> concept floating_point   = is_floating_point_v<T>;
```

要点：

- `integral` 就是 [[basic.fundamental]] 中的**整型**（[[g:integral-type]]）：`bool`、所有字符类型、有符号与无符号整数类型（含扩展整数类型）。cv 限定版本也算（`integral<const int>` 为真），引用不算。枚举、`std::byte` 都不是。
- `unsigned_integral` 定义为 `integral && !signed_integral`，**不是** `is_unsigned_v`。对整型而言效果一样，但这样写使 `signed_integral` 与 `unsigned_integral` 都按名字引用 `integral`，从而都包含它。
- 注 1、注 2：概念名与 [[basic.fundamental]] 的术语并不一一对应。`char` 不是"有符号整数类型"，但若实现中 `char` 有符号，它建模 `signed_integral`；`bool`、`char8_t`、`char16_t` 等都建模 `unsigned_integral`，尽管它们不是"无符号整数类型"。
- `floating_point` 包括扩展浮点类型（[[basic.extended.fp]]）。

!!! pitfall "用 `unsigned_integral` 约束“数字”会放进 `bool` 和字符类型"
    `template<std::unsigned_integral T> T gcd(T, T)` 可以用 `bool`、`char8_t` 实例化。标准库中凡是想要"真正的整数"的地方（如 `<bit>` 的 `popcount`、`<numeric>` 的饱和算术），都另外排除了 `bool` 和字符类型——规格写的是"`T` 是无符号整数类型"（[[basic.fundamental]] 意义上的术语），而不是这几个概念。

```cpp run title="arithmetic.cpp" ok
#include <concepts>
#include <cstddef>
#include <type_traits>

static_assert(std::unsigned_integral<bool>);
static_assert(std::integral<char8_t> && std::unsigned_integral<char8_t>);
static_assert(std::signed_integral<char> == std::is_signed_v<char>);   // 由实现定义
static_assert(std::integral<const int> && !std::integral<const int&>);
static_assert(!std::integral<std::byte>);

int main() {}
```

## `assignable_from`（[concept.assignable]）

```cpp
template<class LHS, class RHS>
  concept assignable_from =
    is_lvalue_reference_v<LHS> &&
    common_reference_with<const remove_reference_t<LHS>&, const remove_reference_t<RHS>&> &&
    requires(LHS lhs, RHS&& rhs) {
      { lhs = std::forward<RHS>(rhs) } -> same_as<LHS>;
    };
```

三个容易踩的细节：

1. **`LHS` 必须是左值引用**。写 `assignable_from<T&, U>`，不是 `assignable_from<T, U>`。这排除了对右值赋值（`T{} = x`），它在泛型代码里几乎总是 bug。
2. **结果类型必须恰好是 `LHS`**（`same_as`，不是 `convertible_to`）。返回 `void` 或返回值副本的 `operator=` 都不行。
3. **要求公共引用**。这把"赋值"限制在"语义上表示同一种值"的类型之间：`string& = const char*` 可以（有公共引用），但如果某类型恰好重载了 `operator=(int)` 却和 `int` 没有任何"同一值"的关系，它就不满足。

### 语义要求（¶1）

设 `lhs` 引用对象 `lcopy`，`rcopy` 是与 `rhs` 相等的另一个对象。建模要求：

- ¶1.4：`addressof(lhs = rhs) == addressof(lcopy)`——返回的就是左操作数本身；
- ¶1.5.1：赋值后 `lhs` 等于 `rcopy`，**除非** `rhs` 是引用 `lcopy` 的非 const xvalue——即**自移动赋值**不要求保持值；
- ¶1.5.2：`rhs` 是非 const xvalue 时，它引用的对象处于有效但未指明状态；
- ¶1.5.3：否则若 `rhs` 是 glvalue，它引用的对象不被修改。

¶2 注 1：赋值不必是全函数。如果对 `x` 赋值会修改另一个对象 `y`，那么 `x = y` 很可能不在 `=` 的定义域内（例如 `y` 是 `x` 的一个子对象）。

```cpp run title="assignable-from.cpp" ok
#include <concepts>
#include <type_traits>

struct VoidAssign { void operator=(const VoidAssign&) {} };

static_assert(!std::assignable_from<int, int>);      // LHS 不是左值引用
static_assert(std::assignable_from<int&, int>);
static_assert(std::is_copy_assignable_v<VoidAssign>);
static_assert(!std::assignable_from<VoidAssign&, const VoidAssign&>);  // 返回 void

int main() {}
```

## `swappable` 与 `ranges::swap`（[concept.swappable]）

### "交换值"的定义（¶1）

¶1 先定义一个语义术语。设 `t1`、`t2` 表示类型 `T` 的两个**不同但相等**的对象，`u1`、`u2` 同理（注 1：`t1` 与 `u1` 可以是同一个对象）。一个操作**交换了** `t1` 与 `u1` 表示的值（[[g:exchanges-values]]），当且仅当它不修改 `t2`、`u2`，并且：

- ¶1.1：`T` 与 `U` 相同时，结果是 `t1` 等于 `u2`、`u1` 等于 `t2`；
- ¶1.2：`T` 与 `U` 不同且 `common_reference_with<decltype((t1)), decltype((u1))>` 被建模时，结果是 `C(t1)` 等于 `C(u2)`、`C(u1)` 等于 `C(t2)`。

`t2`、`u2` 是"旁证"：它们记录了交换前的值，用来表述交换后的结果。注意 `t1` 与 `u1` 允许是同一个对象——**自交换**必须保持值不变。

### `ranges::swap` 定制点对象（¶2）

`ranges::swap` 是一个**定制点对象**（CPO，[[customization.point.object]]）：一个函数对象，`ranges::swap(E1, E2)` 与按以下顺序确定的表达式 `S` **表达式等价**（[[g:expression-equivalent]]）：

1. **¶2.1 用户定制**：若 `E1` 或 `E2` 具有类或枚举类型，且在这样一个语境中**无限定**调用 `(void)swap(E1, E2)` 有效——该语境包含声明

    ```cpp
    template<class T>
      void swap(T&, T&) = delete;
    ```

    且不包含 `ranges::swap` 的声明——则 `S` 就是它。若重载决议选中的函数并不"交换值"，程序 {{ifndr}}。
2. **¶2.2 数组**：若 `E1`、`E2` 是等长数组左值，且 `ranges::swap(*E1, *E2)` 有效，`S` 是 `(void)ranges::swap_ranges(E1, E2)`，`noexcept` 与逐元素交换一致。
3. **¶2.3 兜底**：若 `E1`、`E2` 是同一类型 `T` 的左值，且 `T` 建模 `move_constructible<T>` 与 `assignable_from<T&, T>`，`S` 是一个交换值的表达式（即"移动构造 + 两次移动赋值"）。满足 ¶2.3.1–¶2.3.3 时它是常量表达式；`noexcept` 等于 `is_nothrow_move_constructible_v<T> && is_nothrow_move_assignable_v<T>`。
4. **¶2.4**：否则非良构。注 3：在模板实例化的直接语境中，这会导致替换失败（SFINAE 友好）。

¶3 注 4：只要 `ranges::swap(E1, E2)` 有效，它就交换值并且类型为 `void`。

### 那个被删除的模板：毒丸（poison pill）

¶2.1 里的 `template<class T> void swap(T&, T&) = delete;` 俗称**毒丸**。它的作用（注 2）：

- 它屏蔽掉所有与它签名相同、又不比它更受约束的**通用**交换模板（典型如经 ADL 找到的 `std::swap` 主模板在 libc++ 中以 `enable_if` 实现约束，与毒丸同样特化，于是形成歧义而失败）——CPO 只接受"为这个类型专门写的" `swap`；同时，¶2.1 要求的语境"不包含 `ranges::swap` 的声明"保证 CPO 不会递归地找到自己；
- 用户提供的 `swap` 必须比毒丸**更特化**（[[temp.func.order]]）或是非模板函数，才能被选中。

后果是一个反直觉的现象：**用户写的无约束模板 `swap` 会被静默绕过**。

```cpp run title="poison-pill.cpp" ok
#include <concepts>
#include <cstdio>
#include <utility>

namespace N {
  struct A { int v; };
  template<class T> void swap(T& a, T& b) {          // 无约束模板：与毒丸一样特化
    std::puts("N::swap<T>"); T t = a; a = b; b = t;
  }
  struct B { int v; };
  void swap(B& a, B& b) { std::puts("N::swap(B&, B&)"); std::swap(a.v, b.v); }
}

int main() {
  N::A a{1}, b{2};
  std::ranges::swap(a, b);     // ¶2.1 歧义 → 无效；落到 ¶2.3，不打印任何东西
  std::printf("%d %d\n", a.v, b.v);     // 2 1

  N::B c{1}, d{2};
  std::ranges::swap(c, d);     // ¶2.1：非模板，比毒丸更好 → 打印 "N::swap(B&, B&)"
  std::printf("%d %d\n", c.v, d.v);     // 2 1

  int x[2]{1, 2}, y[2]{3, 4};
  std::ranges::swap(x, y);     // ¶2.2：逐元素交换
  std::printf("%d %d\n", x[0], y[0]);   // 3 1
}
```

!!! impl "libc++ 的实现"
    libc++ 在 `<__concepts/swappable.h>` 中把 CPO 实现为 `ranges::__swap::__fn` 的三个受约束 `operator()`，分别对应 ¶2.1–¶2.3。¶2.1 的条件写成概念 `__unqualified_swappable_with`（要求 `remove_cvref_t` 后有一方是类或枚举，且无限定 `swap(...)` 有效），毒丸声明在同一个内部命名空间里；¶2.2 用 `__swappable_arrays`，实现是一个逐元素调用自身的循环（源码注释中有"replace with `ranges::swap_ranges`"的 TODO）；¶2.3 的 `__exchangeable` 实现为 `__y = std::exchange(__x, std::move(__y));`。CPO 对象本身是 `inline constexpr auto swap = __swap::__fn{};`，位于内联命名空间 `__cpo` 中。

### 两个概念

```cpp
template<class T>
  concept swappable = requires(T& a, T& b) { ranges::swap(a, b); };

template<class T, class U>
  concept swappable_with =
    common_reference_with<T, U> &&
    requires(T&& t, U&& u) {
      ranges::swap(std::forward<T>(t), std::forward<T>(t));
      ranges::swap(std::forward<U>(u), std::forward<U>(u));
      ranges::swap(std::forward<T>(t), std::forward<U>(u));
      ranges::swap(std::forward<U>(u), std::forward<T>(t));
    };
```

注意参数形式：`swappable<T>` 接受**类型**并对其左值交换；`swappable_with<T, U>` 的 `T`、`U` 通常是**引用类型**（例如 `swappable_with<int&, int&>`），以便表达"交换两个右值代理"这类情形——标准的例 1 中，`value_swap(a1, proxy(a2))` 就是把左值与一个代理右值交换。`swappable_with` 要求四种组合都可交换，并有公共引用（保证交换的是"同一种值"）。

¶4 注 5：这两个概念的语义**完全由** `ranges::swap` 规定——因为 CPO 在 ¶2.1 已经把"不交换值"定为 IFNDR，¶2.2/¶2.3 的实现本身保证交换值，所以概念不需要额外的语义段落。

## `destructible`（[concept.destructible]）

```cpp
template<class T>
  concept destructible = is_nothrow_destructible_v<T>;
```

¶1：指所有"实例能在生命期结束时被销毁"的类型，**或引用类型**。

- 引用类型满足（`is_nothrow_destructible_v<int&>` 为真）；
- `void`、函数类型、未知边界数组不满足；已知边界数组满足；
- ¶2 注 1：与 *Cpp17Destructible* 不同，**潜在抛出异常**的析构函数（`noexcept(false)`）一律不满足，即使某次调用实际上不抛异常。

这一点会沿着细化链一路传播：`noexcept(false)` 析构的类型不是 `constructible_from` 的任何东西，于是不是 `movable`、`copyable`、`regular`，也就不能用于绝大多数 ranges 算法和视图。

```cpp run title="destructible.cpp" ok
#include <concepts>

struct Throwy { ~Throwy() noexcept(false) {} };
static_assert(!std::destructible<Throwy>);
static_assert(!std::movable<Throwy>);           // 沿细化链传播
static_assert(std::destructible<int&>);
static_assert(!std::destructible<void>);
static_assert(!std::destructible<int[]> && std::destructible<int[3]>);

int main() {}
```

## `constructible_from`（[concept.constructible]）

```cpp
template<class T, class... Args>
  concept constructible_from = destructible<T> && is_constructible_v<T, Args...>;
```

¶1：约束"用给定实参类型初始化一个变量"。`is_constructible_v<T, Args...>` 检查的是 `T t(declval<Args>()...);` 是否良构（[[meta.unary.prop]]），即**直接初始化**；带上 `destructible<T>` 是因为"能构造但不能销毁"的对象在值语义里没有意义。

没有语义段落：直接初始化的语义由各类型自己决定，这里只关心能否构造。

## `default_initializable`（[concept.default.init]）

```cpp
template<class T>
  constexpr bool is-default-initializable = see below;   // exposition only

template<class T>
  concept default_initializable = constructible_from<T> &&
                                  requires { T{}; } &&
                                  is-default-initializable<T>;
```

一次要求**三种**默认初始化写法都可用：

| 写法 | 初始化种类 | 由谁检查 |
|---|---|---|
| `T()` | 值初始化 | `constructible_from<T>` |
| `T{}` | 列表初始化（值初始化或聚合初始化） | `requires { T{}; }` |
| `T t;` | 默认初始化 | *`is-default-initializable`*（¶1） |

¶1：当且仅当变量定义 `T t;` 对某个虚构变量良构时为真；访问检查如同在与 `T` 无关的语境中进行；只考虑变量初始化的**直接语境**。

为什么要三种都检查？因为它们确实会分道扬镳：

- `const int`：`T()`、`T{}` 都行，但 `const int t;` 非良构（[[dcl.init]]：const 对象必须被初始化，除非类型是 [[g:const-default-constructible]]）；
- 含 `const` 成员且无默认成员初始化器的聚合：同理，`T t;` 不行；
- 某成员的默认构造函数是 `explicit` 的聚合：`T()` 行，但 `T{}` 是聚合初始化，会对该成员做**复制列表初始化**，而复制列表初始化选中 `explicit` 构造函数是非良构的。

泛型代码（例如容器、视图的默认构造）会随意使用这三种写法，所以概念要求全部可用。

```cpp run title="default-initializable.cpp" ok
#include <concepts>
#include <type_traits>

static_assert(std::is_default_constructible_v<const int>);
static_assert(!std::default_initializable<const int>);       // const int t; 非良构

struct CM  { const int x; };
struct CM2 { const int x = 0; };
static_assert(!std::default_initializable<CM>);
static_assert(std::default_initializable<CM2>);

struct E { explicit E() = default; };
struct A { E e; };
static_assert(std::is_default_constructible_v<A>);           // A() 可以
static_assert(!std::default_initializable<A>);               // A{} 对 e 复制列表初始化，选中 explicit

int main() {}
```

!!! impl "libc++ 怎么检查 `T t;`"
    "某个定义是否良构"不能直接写成 requires 表达式（requires 里不能声明变量）。libc++ 在 `<__concepts/constructible.h>` 中用 `requires { ::new _Tp; }` 来近似：*new-expression* 不带初始化器时对对象做默认初始化，规则与 `T t;` 相同（[[expr.new]]）。

!!! history
    C++20 最初的概念名为 `default_constructible`，只要求 `is_default_constructible`。后来发现它对 `const int` 这类类型给出"能默认构造"的结论，与泛型代码的实际写法不符，于是在 C++20 定稿前经 LWG issue 修订：加入 `T{}` 与 `T t;` 两项检查，并改名为 `default_initializable`。

## `move_constructible`（[concept.moveconstructible]）

```cpp
template<class T>
  concept move_constructible = constructible_from<T, T> && convertible_to<T, T>;
```

`constructible_from<T, T>` 检查 `T t(rvalue)`；`convertible_to<T, T>` 检查 `T t = rvalue;` 与 `static_cast<T>(rvalue)`。于是 **`explicit` 移动构造函数**的类型不满足：

```cpp run title="explicit-move.cpp" ok
#include <concepts>

struct ExplMove {
    ExplMove() = default;
    explicit ExplMove(ExplMove&&) = default;
};
static_assert(std::constructible_from<ExplMove, ExplMove>);
static_assert(!std::move_constructible<ExplMove>);   // ExplMove y = std::move(x); 非良构

int main() {}
```

（严格说，C++17 起 `ExplMove x = ExplMove{};` 因为保证的复制消除并不调用移动构造函数，所以是合法的；但 `convertible_to` 检查的 `is_convertible_v<ExplMove, ExplMove>` 用的是 `declval<ExplMove>()`——一个 xvalue——它需要真正调用移动构造函数，于是失败。）

¶1 语义要求（`T` 为对象类型时）：设 `rv` 为 `T` 的右值，`u2` 是与 `rv` 相等的另一个对象，则

- ¶1.1：`T u = rv;` 之后 `u` 等于 `u2`；
- ¶1.2：`T(rv)` 等于 `u2`；
- ¶1.3：若 `T` 非 const，`rv` 处于有效但未指明的状态；否则不变。

`T` 为引用类型时，`constructible_from<int&, int&>` 等成立，`move_constructible<int&>` 为真，但没有语义要求。

## `copy_constructible`（[concept.copyconstructible]）

```cpp
template<class T>
  concept copy_constructible =
    move_constructible<T> &&
    constructible_from<T, T&> && convertible_to<T&, T> &&
    constructible_from<T, const T&> && convertible_to<const T&, T> &&
    constructible_from<T, const T> && convertible_to<const T, T>;
```

复制的"源"有三种形式：非 const 左值、const 左值、const 右值，每种都要求直接与隐式两条路径都可用。为什么要显式列出而不依赖隐式表达式变体？因为 [[concepts.equality]] ¶6 的隐式变体只适用于 requires 表达式中声明的表达式，而这里用的是类型特征——必须手动穷举。

注意这些都只是**语法**检查。一类常见问题是带"贪婪"转发构造函数的类型：`template<class U> S(U&&)` 对非 const 左值 `S&` 是比 `S(const S&)` 更好的匹配，于是 `S s2 = s1;` 调用的根本不是复制构造函数。语法上它照样满足 `copy_constructible`；只有当那个模板做的事不产生与 `s1` 相等的对象时，才违反下面的语义要求而变成"满足但不建模"。

¶1 语义要求（`T` 为对象类型时）：设 `v` 为 `T` 或 `const T` 的左值、或 `const T` 的右值，则

- ¶1.1：`T u = v;` 之后 `u` 等于 `v`，且 `v` 未被修改；
- ¶1.2：`T(v)` 等于 `v`，且不修改 `v`。

这就是"复制"的数学定义：复制品与原件相等，原件不变。`auto_ptr` 式的"复制即转移"违反它。

## 陷阱汇总

!!! pitfall "概念名 ≠ 同名的 *Cpp17* 要求"
    `destructible` 比 *Cpp17Destructible* 严（禁止潜在抛出的析构函数）；`default_initializable` 比 *Cpp17DefaultConstructible* 严（三种写法）；`move_constructible` 要求隐式转换（排除 `explicit` 移动构造）；`assignable_from` 要求返回 `T&` 且有公共引用。从 C++17 迁移到概念时，"以前能用的类型现在不满足"常常就是这几处。

!!! pitfall "以为 `std::swap` 的定制方式在 ranges 里照样有效"
    在自己命名空间里写一个**无约束**的 `template<class T> void swap(T&, T&)` 当"通用交换"，`ranges::swap` 会因为与毒丸歧义而跳过它，静默退回到移动三步走。应当为具体类型提供非模板的 `swap`（最好是隐藏友元），或者给模板加约束使其比毒丸更特化。

## 思考题

!!! question "思考题"
    1. `std::convertible_to<int, long>` 为真吗？它的语义要求被 `int`/`long` 建模吗？如果 `To` 是 `short` 呢（`int` → `short` 是窄化转换）？
    2. 为什么 `assignable_from` 要求 `common_reference_with<const remove_reference_t<LHS>&, const remove_reference_t<RHS>&>`，而不是 `convertible_to<RHS, remove_reference_t<LHS>>`？
    3. 对两个 `int` 左值 `x`、`y`，`ranges::swap(x, y)` 走 ¶2 的哪一条？`ranges::swap(x, x)` 呢？

<details markdown="1">
<summary>展开查看答案与解析</summary>

1. 为真，且被建模：`int` 到 `long` 的隐式与显式转换结果相等，且不修改源。`convertible_to<int, short>` 同样为真（窄化只在列表初始化中被禁止，[[dcl.init.list]]），隐式与显式转换结果相同（都是模 2^N 的结果），因此也被建模——`convertible_to` 只要求两条路径一致，不要求转换"无损"。无损性是 `common_reference_with` 的语义（¶2 的单射要求）才关心的。
2. 赋值的语义要求是"赋值后 `lhs` 等于 `rcopy`"（¶1.5.1）——这要求左右两边的值在同一个"相等"的意义下可比较。公共引用正好提供这样一个共同的值域（并且转换到它是保持相等的单射）。单纯的可转换性不能保证这一点：`RHS` 可以转换到 `LHS` 的值类型，却与它没有任何一致的相等概念。另外，`common_reference_with` 是对称的，能支持代理引用作为左操作数。
3. `int` 不是类或枚举类型，¶2.1 不适用；不是数组，¶2.2 不适用；`int` 建模 `move_constructible` 与 `assignable_from<int&, int>`，走 ¶2.3，且是常量表达式、`noexcept`。`ranges::swap(x, x)` 同样走 ¶2.3；按 ¶1 的定义（注 1 允许 `t1`、`u1` 是同一个对象），它必须让 `x` 保持原值——"移动构造临时量 + 两次移动赋值"对 `int` 正是如此。
</details>

## 小结

!!! summary
    | 概念 | 语法核心 | 关键语义 / 设计要点 |
    |---|---|---|
    | `same_as` | `is_same_v` 双向 | 双向写法使 `same_as<T,U>` 与 `same_as<U,T>` 互相包含 |
    | `derived_from` | `is_base_of` + 指针可转换 | 只认公有、无歧义的派生 |
    | `convertible_to` | 隐式 **且** 显式 | 两条路径结果相等；右值源可被移走，其余不得修改 |
    | `common_reference_with` | 对称的 `common_reference_t`，双方可转换 | 转换到 C 是保持相等的单射；为代理引用设计 |
    | `common_with` | 对称的 `common_type_t`，可显式转换 + 公共引用相容 | 同上，"值"的版本 |
    | `integral` 等 | 类型特征 | `bool`、字符类型也是 `unsigned_integral`/`signed_integral` |
    | `assignable_from<L, R>` | `L` 是左值引用，`lhs = rhs` 恰为 `L` | 返回 `lhs` 本身；赋值后相等；自移动除外 |
    | `swappable(_with)` | `ranges::swap` 可调用 | 语义全由 CPO 定义；无约束模板 `swap` 被毒丸挡掉 |
    | `destructible` | `is_nothrow_destructible` | 潜在抛出的析构函数不满足；引用满足 |
    | `constructible_from` | `destructible` + `is_constructible` | 直接初始化 |
    | `default_initializable` | `T()`、`T{}`、`T t;` 三者 | `const int` 不满足 |
    | `move_constructible` | 构造 + 隐式转换自 `T` | `explicit` 移动构造不满足 |
    | `copy_constructible` | 三种源 × 两条路径 | 复制品等于原件，原件不变 |
