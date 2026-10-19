---
title: 语言相关概念
summary: same_as、derived_from、convertible_to、common_reference_with、common_with、整数与浮点概念、assignable_from、swappable 与 ranges::swap、destructible、constructible_from、default_initializable、move_constructible、copy_constructible 的定义、语义要求和设计理由。
status: done
covers: *
since: c++20
papers: P0898R3
related: concepts, concepts.object, concepts.compare, temp.constr.order, conv, dcl.init, expr.static.cast, class.derived, customization.point.object, meta.trans.other
tags: 标准库, 概念, convertible_to, common_reference, swap, CPO
updated: 2026-10-19
---

!!! tldr
    - 这些概念大多是对 `<type_traits>` 的包装。包进概念后，约束之间才能比较谁更严格（包含），概念还附带编译器不检查的语义要求。
    - `convertible_to` 要求隐式转换和显式转换都能用，而且结果相等；只有其中一种可用的类型不满足它。
    - `ranges::swap` 会跳过用户写的无约束模板 `swap`，只采用为具体类型写的 `swap`，找不到时退回移动三步。
    - `default_initializable` 同时检查 `T()`、`T{}` 和 `T t;`，所以 `const int` 不满足它。
    - 析构函数可能抛异常的类型不是 `destructible`，进而不是 `movable`、`copyable`，几乎不能用于 ranges。

[concepts.lang] 收录与语言特性对应的概念（[concepts.lang.general] ¶1）：类型之间的关系（相同、派生、可转换、有公共类型），类型的分类（整数、浮点），以及最基本的对象操作（赋值、交换、析构、构造）。[[concepts.object]] 里的 `movable`、`copyable`、`regular` 就是用它们拼成的。

读这一页需要两个来自 [[concepts]] 的词。类型**满足**（satisfy）一个概念，指概念的定义代入后为 `true`，这由编译器检查。类型**建模**（model）一个概念，指它既满足概念，又符合概念规格里的语义要求，这由程序员担保。把满足但不建模的类型交给标准库，程序是 {{ifndr}}（[[res.on.requirements]]）。

## 为什么不直接用类型特征：`same_as`

```cpp run title="same-as-subsumption.cpp" ok
#include <concepts>
#include <cstdio>

template<class T>
void f(T) requires std::same_as<T, int> { std::puts("#1"); }

template<class T>
void f(T) requires std::same_as<int, T> && true { std::puts("#2"); }

int main() {
  f(1);   // 选 #2
}
```

两个重载都可行。#2 的约束包含了 #1 的约束（[[temp.constr.order]]），所以 #2 更受约束，被选中。把两处 `std::same_as` 换成 `std::is_same_v`，Clang 就报调用有歧义。

原因在于包含只认得同一个概念产生的原子约束。直接写在约束里的 `is_same_v<T, int>` 和 `is_same_v<int, T>` 是两个不同的表达式，编译器无法比较它们。`same_as` 的定义特意写了两遍：

```cpp
template<class T, class U>
  concept same-as-impl = is_same_v<T, U>;       // exposition only
template<class T, class U>
  concept same_as = same-as-impl<T, U> && same-as-impl<U, T>;
```

于是 `same_as<T, int>` 规范化成两个原子约束 `is_same_v<T, int>` 和 `is_same_v<int, T>`，它们出自同一个表达式，只是参数映射不同。`same_as<int, T>` 得到的是同样两个约束，顺序相反。合取不在乎顺序，所以两者互相包含，这正是注 1 所说的。

`same_as` 不做任何退化：`same_as<int, const int>` 和 `same_as<int&, int>` 都为假。在 *type-constraint* `{ e } -> same_as<T>` 中，`decltype((e))` 作为第一个实参传入，所以能精确检查表达式的值类别：左值表达式得到的是 `T&`。

## 公有派生：`derived_from`

```cpp
template<class Derived, class Base>
  concept derived_from =
    is_base_of_v<Base, Derived> &&
    is_convertible_v<const volatile Derived*, const volatile Base*>;
```

`is_base_of_v` 只看继承图，私有继承和有歧义的基类也算。再加上指针能否隐式转换的检查，就排除了派生类指针转不到基类指针的情形（基类不可访问或有歧义，见 [[conv.ptr]]、[[class.derived]]）。按注 1，结果是：`Derived` 公有且无歧义地派生自 `Base`，或者两者忽略 cv 后是同一个类类型。指针加上 `const volatile`，是为了让带 cv 限定的类型也能通过。

```cpp run title="derived-from.cpp" ok
#include <concepts>
#include <type_traits>

struct B {};
struct D : B {};
struct P : private B {};
struct M1 : B {};
struct M2 : B {};
struct MM : M1, M2 {};   // 两个 B 子对象

static_assert(std::derived_from<D, B>);
static_assert(std::is_base_of_v<B, P>);
static_assert(!std::derived_from<P, B>);   // 私有继承
static_assert(std::is_base_of_v<B, MM>);
static_assert(!std::derived_from<MM, B>);  // 歧义基类
static_assert(std::derived_from<const B, B>);
static_assert(!std::derived_from<int, int>);  // 不是类

int main() {}
```

## 隐式和显式都要能转：`convertible_to`

```cpp run title="convertible-to.cpp" ok
#include <concepts>
#include <type_traits>

struct From {};
struct To {
  template<class T> To(T&&) {}   // 什么都能隐式转换过来
  explicit To(From) = delete;    // 显式转换 From 时选中它
};
static_assert(std::is_convertible_v<From, To>);
static_assert(!std::convertible_to<From, To>);

struct E { explicit E(int) {} };   // 只能显式转换
static_assert(!std::convertible_to<int, E>);
static_assert(std::constructible_from<E, int>);

static_assert(std::convertible_to<void, void>);
static_assert(!std::convertible_to<int, void>);

int main() {}
```

`From` 能隐式转换到 `To`，却不满足 `convertible_to<From, To>`，因为定义要求两种转换都可用：

```cpp
template<class From, class To>
  concept convertible_to =
    is_convertible_v<From, To> &&
    requires { static_cast<To>(declval<From>()); };
```

`is_convertible_v` 检查的是[[g:copy-initialization|复制初始化]]，相当于 `return declval<From>();` 能否返回一个 `To`。`static_cast<To>(e)` 检查的是[[g:direct-initialization|直接初始化]]（[[expr.static.cast]]）。两者看到的候选函数不一样：复制初始化不考虑 `explicit` 构造函数，直接初始化考虑（[[over.match.copy]]、[[over.match.ctor]]）。所以会出现两种不一致：

- 只有 `explicit` 构造函数或转换函数时，显式可以，隐式不行，如上面的 `E`。
- 显式路径上多出一个更好的候选，而它被删除或有歧义，就是隐式可以、显式不行。上面的 `To` 就是这样：`static_cast<To>(From{})` 里模板构造函数 `To(From&&)` 和 `To(From)` 的转换序列都是恒等转换，按 [[over.match.best]] 非模板优先，选中被删除的那一个。

为什么两种都要？泛型代码会随手写 `To t = e;`、`return e;`、`static_cast<To>(e)`、`To(e)`。约束只保证其中一种写法可用的话，模板体里换一种写法就可能编译失败，甚至调用一个语义不同的转换。

¶1 还要求两种转换的结果相等。¶2 用一个虚构函数把这一点写得更精确：设 `FromR` 是 `add_rvalue_reference_t<From>`，`f` 是返回 `FromR` 的、保持相等性的无参函数，则 `From` 和 `To` 建模 `convertible_to` 需要：

- ¶2.1 若 `To` 是对象类型或对象的引用类型，`static_cast<To>(f())` 等于 `test(f)`，即 `To test(FromR (&f)()) { return f(); }` 的结果；
- ¶2.2.1 若 `FromR` 是非 const 类型的右值引用，转换之后源对象处于[[g:valid-but-unspecified-state|有效但未指明的状态]]，也就是允许把它移走；
- ¶2.2.2 其他对象引用的情形下，转换不得修改源对象。

`To` 是 `void` 这类非对象类型时，¶2.1 不适用。

## 公共引用与公共类型

### 代理迭代器带来的问题

`vector<bool>::iterator` 解引用得到代理对象 `vector<bool>::reference`，值类型却是 `bool`。`views::zip` 的迭代器解引用得到 `tuple<int&, double&>`，值类型是 `tuple<int, double>`。泛型算法经常要把引用和值放在一起处理：`ranges::sort` 既要比较 `*it` 和 `*jt`，也要比较 `*it` 和一个暂存的 `value_type` 变量。

`common_reference_t<R, V&>` 回答的问题是：有没有一个类型，`R` 和 `V&` 都能转换过去，好让同一个函数同时接受两者？对普通引用，它给出符合直觉的结果；对代理类型，可以特化 `basic_common_reference` 来指定答案（[[meta.trans.other]]）。`<iterator>` 中的 `indirectly_readable` 就要求 `common_reference_with<iter_reference_t<I>&&, iter_value_t<I>&>`。

```cpp run title="common-reference.cpp" ok
#include <concepts>
#include <string>
#include <type_traits>
#include <utility>

using std::common_reference_t, std::same_as;

static_assert(same_as<common_reference_t<int&, const int&>,
                      const int&>);
static_assert(same_as<common_reference_t<int&&, int&>,
                      const int&>);
// 没有公共引用时退到值类型
static_assert(same_as<common_reference_t<int&, double&>,
                      double>);
static_assert(std::common_reference_with<int&, double&>);
static_assert(!std::common_reference_with<int*, std::string>);

// pair 特化了 basic_common_reference（C++23）
using PR = std::pair<int&, int&>;
using PV = std::pair<int, int>;
static_assert(same_as<common_reference_t<PR, PV&>, PR>);
static_assert(std::common_reference_with<PR, PV&>);

int main() {}
```

### `common_reference_with`（[concept.commonref]）

¶1 如果 `common_reference_t<T, U>` 良构，得到类型 `C`，并且 `convertible_to<T, C>` 和 `convertible_to<U, C>` 都被建模，就说 `T` 和 `U` 有**公共引用类型**（[[g:common-reference-type|common reference type]]）`C`。按注 1，`C` 可以是 `T` 或 `U` 本身，也可以是别的类型，也可以是引用类型。

```cpp
template<class T, class U>
  concept common_reference_with =
    same_as<common_reference_t<T, U>, common_reference_t<U, T>> &&
    convertible_to<T, common_reference_t<T, U>> &&
    convertible_to<U, common_reference_t<T, U>>;
```

第一项要求对称。`common_reference` 允许用户特化，标准不能假设特化写得对称，于是把对称性写进了约束。

¶2 是语义要求。设 `t1`、`t2` 是类型为 `T` 的保持相等性的表达式，`u1`、`u2` 同理，则 `C(t1)` 等于 `C(t2)` 当且仅当 `t1` 等于 `t2`（¶2.1），对 `u` 也一样（¶2.2）。换句话说，转换到 `C` 既不能把不同的值变成相等，也不能把相等的值变成不同。这样在 `C` 里比较就等同于在原类型里比较，[[concepts.compare]] 的跨类型比较概念正是建立在这一点上。

### `common_with`（[concept.common]）

`common_with` 是值的版本。¶1 说，如果 `T` 和 `U` 都能显式转换到第三个类型 `C`，它们就有**公共类型**（[[g:common-type|common type]]）`C`，注 1 补充 `C` 不一定唯一。

```cpp
template<class T, class U>
  concept common_with =
    same_as<common_type_t<T, U>, common_type_t<U, T>> &&
    requires {
      static_cast<common_type_t<T, U>>(declval<T>());
      static_cast<common_type_t<T, U>>(declval<U>());
    } &&
    common_reference_with<add_lvalue_reference_t<const T>,
                          add_lvalue_reference_t<const U>> &&
    common_reference_with<
      add_lvalue_reference_t<common_type_t<T, U>>,
      common_reference_t<add_lvalue_reference_t<const T>,
                         add_lvalue_reference_t<const U>>>;
```

四项依次是：`common_type_t` 对称；两边都能显式转换到公共类型（只要求显式，比 `convertible_to` 宽）；`const T&` 和 `const U&` 有公共引用；公共类型的左值引用和这个公共引用之间也有公共引用，保证值的世界和引用的世界彼此相容。

¶2 的语义要求和 `common_reference_with` 一样，只是 `C` 换成 `common_type_t<T, U>`。¶3 注 2 指出，可以特化 `common_type` 来定制它。

```cpp run title="common-with.cpp" ok
#include <concepts>
#include <string>
#include <type_traits>

using std::string;

static_assert(std::common_with<int, double>);
static_assert(std::same_as<
  std::common_type_t<string, const char*>, string>);
static_assert(std::common_with<string, const char*>);
// 第 3 项里的公共引用是非引用类型 const string
static_assert(std::same_as<
  std::common_reference_t<const string&,
                          const char* const&>,
  const string>);

int main() {}
```

## 整数与浮点（[concepts.arithmetic]）

```cpp run title="arithmetic.cpp" ok
#include <concepts>
#include <cstddef>
#include <type_traits>

static_assert(std::unsigned_integral<bool>);
static_assert(std::unsigned_integral<char8_t>);
// char 是否有符号由实现定义
static_assert(std::signed_integral<char> ==
              std::is_signed_v<char>);
static_assert(std::integral<const int>);
static_assert(!std::integral<const int&>);
static_assert(!std::integral<std::byte>);

int main() {}
```

```cpp
template<class T> concept integral          = is_integral_v<T>;
template<class T> concept signed_integral   = integral<T> && is_signed_v<T>;
template<class T> concept unsigned_integral = integral<T> && !signed_integral<T>;
template<class T> concept floating_point    = is_floating_point_v<T>;
```

`integral` 就是 [[basic.fundamental]] 里的[[g:integral-type|整型]]：`bool`、所有字符类型、有符号和无符号整数类型（包括扩展整数类型）。cv 限定的版本也算，引用不算，枚举和 `std::byte` 都不算。`floating_point` 包括扩展浮点类型（[[basic.extended.fp]]）。

`unsigned_integral` 写成 `integral && !signed_integral` 而不是 `is_unsigned_v`。对整型两者结果一样，但这样写，两个概念都通过名字引用了 `integral`，于是都包含它。

注 1 和注 2 提醒，概念名和 [[basic.fundamental]] 的术语并不一一对应。`char` 不是有符号整数类型，但在 `char` 有符号的实现上它建模 `signed_integral`。`bool`、`char8_t`、`char16_t` 都不是无符号整数类型，却都建模 `unsigned_integral`。

!!! pitfall "用 `unsigned_integral` 约束数字会放进 `bool` 和字符"
    `template<std::unsigned_integral T> T gcd(T, T)` 可以用 `bool`、`char8_t` 实例化。标准库里需要真正整数的地方，如 `<bit>` 的 `popcount` 和饱和算术函数，规格写的是 `T` 是无符号整数类型（[[basic.fundamental]] 的术语），而不是这几个概念，从而排除了 `bool` 和字符类型。

## 赋值：`assignable_from`

```cpp run title="assignable-from.cpp" ok
#include <concepts>
#include <type_traits>

struct VoidAssign {
  void operator=(const VoidAssign&) {}
};

static_assert(!std::assignable_from<int, int>);
static_assert(std::assignable_from<int&, int>);
static_assert(std::is_copy_assignable_v<VoidAssign>);
// 返回 void，不满足
static_assert(!std::assignable_from<VoidAssign&,
                                    const VoidAssign&>);

int main() {}
```

```cpp
template<class LHS, class RHS>
  concept assignable_from =
    is_lvalue_reference_v<LHS> &&
    common_reference_with<const remove_reference_t<LHS>&, const remove_reference_t<RHS>&> &&
    requires(LHS lhs, RHS&& rhs) {
      { lhs = std::forward<RHS>(rhs) } -> same_as<LHS>;
    };
```

定义里有三处容易出错：

1. `LHS` 必须是左值引用。要写 `assignable_from<T&, U>`，不是 `assignable_from<T, U>`。这排除了给右值赋值（`T{} = x`），这种写法在泛型代码里几乎总是错误。
2. 赋值表达式的类型必须恰好是 `LHS`，用的是 `same_as` 而不是 `convertible_to`。返回 `void` 或返回副本的 `operator=` 都不满足。
3. 两边要有公共引用。这把赋值限定在表示同一种值的类型之间：`string&` 可以从 `const char*` 赋值，因为两者有公共引用；一个碰巧重载了 `operator=(int)`、但和 `int` 没有公共引用的类型就不满足。

¶1 的语义要求：设 `lhs` 引用对象 `lcopy`，`rcopy` 是与 `rhs` 相等的另一个对象。

- ¶1.4 `addressof(lhs = rhs) == addressof(lcopy)`，即返回的就是左操作数本身。
- ¶1.5.1 赋值后 `lhs` 等于 `rcopy`。唯一的例外是 `rhs` 是引用 `lcopy` 的非 const xvalue，也就是自移动赋值不要求保持值。
- ¶1.5.2 `rhs` 是非 const xvalue 时，它引用的对象处于有效但未指明的状态。
- ¶1.5.3 否则，如果 `rhs` 是泛左值，它引用的对象不被修改。

¶2 注 1 说明赋值不必对所有值都有定义（[[structure.requirements]]）。如果对 `x` 赋值会修改另一个对象 `y`，例如 `y` 是 `x` 的子对象，那么 `x = y` 多半不在 `=` 的定义域内。

## 交换：`swappable` 与 `ranges::swap`

### 无约束的模板 `swap` 被跳过

```cpp run title="poison-pill.cpp" ok
#include <concepts>
#include <cstdio>
#include <utility>

namespace N {
  struct A { int v; };
  template<class T>              // 无约束模板
  void swap(T& a, T& b) {
    std::puts("N::swap<T>");
    T t = a; a = b; b = t;
  }

  struct B { int v; };
  void swap(B& a, B& b) {        // 非模板
    std::puts("N::swap(B&, B&)");
    std::swap(a.v, b.v);
  }
}

int main() {
  N::A a{1}, b{2};
  std::ranges::swap(a, b);   // 不打印：没用 N::swap<T>
  std::printf("%d %d\n", a.v, b.v);   // 2 1

  N::B c{1}, d{2};
  std::ranges::swap(c, d);   // 打印 N::swap(B&, B&)
  std::printf("%d %d\n", c.v, d.v);   // 2 1

  int x[2]{1, 2}, y[2]{3, 4};
  std::ranges::swap(x, y);   // 逐元素交换
  std::printf("%d %d\n", x[0], y[0]); // 3 1
}
```

`std::ranges::swap` 不是函数，而是一个**定制点对象**（customization point object，CPO，[[customization.point.object]]）：一个函数对象，调用时按固定的顺序寻找合适的交换方式。¶2 规定 `ranges::swap(E1, E2)` 与按下列顺序确定的表达式 `S` [[g:expression-equivalent|表达式等价]]：

1. ¶2.1 如果 `E1` 或 `E2` 是类或枚举类型，并且无限定调用 `(void)swap(E1, E2)` 有效，`S` 就是这个调用。重载决议在这样一个语境中进行：它包含声明 `template<class T> void swap(T&, T&) = delete;`，不包含 `ranges::swap` 本身。如果选中的函数并不交换值，程序 {{ifndr}}。
2. ¶2.2 否则，如果两者是长度相同的数组左值，且 `ranges::swap(*E1, *E2)` 有效，`S` 是 `(void)ranges::swap_ranges(E1, E2)`，`noexcept` 与逐元素交换一致。
3. ¶2.3 否则，如果两者是同一类型 `T` 的左值，`T` 建模 `move_constructible<T>` 和 `assignable_from<T&, T>`，`S` 是一个交换值的表达式，实际就是一次移动构造加两次移动赋值。满足 ¶2.3.1–¶2.3.3 时它是常量表达式；`noexcept` 等于 `is_nothrow_move_constructible_v<T> && is_nothrow_move_assignable_v<T>`。
4. ¶2.4 否则 `ranges::swap(E1, E2)` 非良构。按注 3，在模板实例化的直接语境中这只造成替换失败。

¶3 注 4 总结：只要 `ranges::swap(E1, E2)` 有效，它就交换了值，类型是 `void`。

¶2.1 里那个被删除的模板常被称为**毒丸**（poison pill）。它和一切同样宽泛的模板 `swap` 一样特化，所以经 ADL 找到的无约束模板（包括 `std::swap` 的主模板）和它打成平手，调用有歧义，¶2.1 不成立。注 2 说明了后果：用户的 `swap` 必须是非模板函数，或者比毒丸更特化（[[temp.func.order]]），才会被选中。上面的 `N::A` 因此走到了 ¶2.3。不包含 `ranges::swap` 的声明，是为了让 CPO 不会通过无限定查找找到自己。

!!! impl "libc++ 的实现"
    libc++ 在 `<__concepts/swappable.h>` 中用三个受约束的 `operator()` 分别实现 ¶2.1–¶2.3，毒丸声明在同一个内部命名空间里。¶2.3 写成 `__y = std::exchange(__x, std::move(__y));`。

### 交换值的定义（¶1）

¶1 先给出语义术语。设 `t1`、`t2` 表示类型 `T` 的两个不同但相等的对象，`u1`、`u2` 同理。一个操作**交换了** `t1` 和 `u1` 表示的值（[[g:exchanges-values|exchanges the values]]），当且仅当它不修改 `t2`、`u2`，并且：

- ¶1.1 `T` 和 `U` 相同时，结果是 `t1` 等于 `u2`，`u1` 等于 `t2`；
- ¶1.2 `T` 和 `U` 不同但建模 `common_reference_with<decltype((t1)), decltype((u1))>` 时，在公共引用类型 `C` 下有同样的结论。

`t2`、`u2` 记录交换前的值，用来表述交换后的结果。注 1 允许 `t1` 和 `u1` 是同一个对象，所以自交换必须保持值不变。

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

`swappable<T>` 接受一个类型，检查它的两个左值能否交换。`swappable_with<T, U>` 的实参通常是引用类型，比如 `swappable_with<int&, int&>`，这样才能表达交换一个左值和一个代理右值。标准的例 1 里 `value_swap(a1, proxy(a2))` 就是这种用法。它要求四种组合都能交换，并且有公共引用。

¶4 注 5 说，这两个概念的语义完全由 `ranges::swap` 规定：¶2.1 已经把不交换值定为 IFNDR，¶2.2 和 ¶2.3 本身保证交换值，所以不需要另写语义段落。

## 构造与析构

### `destructible`

```cpp
template<class T>
  concept destructible = is_nothrow_destructible_v<T>;
```

¶1 说它描述实例能在生命期结束时被销毁的类型，以及引用类型。已知边界的数组满足，`void`、函数类型、未知边界数组不满足。¶2 注 1 指出与 *Cpp17Destructible* 的区别：析构函数**潜在抛出**（potentially-throwing，例如声明为 `noexcept(false)`）的类型一律不满足，哪怕某次析构实际上不抛。

这一点会沿着组合链传下去。`constructible_from` 以 `destructible` 开头，于是这样的类型不是 `move_constructible`，也不是 `movable`、`copyable`、`regular`，大多数 ranges 算法和视图都用不了它。

```cpp run title="destructible.cpp" ok
#include <concepts>

struct Throwy { ~Throwy() noexcept(false) {} };
static_assert(!std::destructible<Throwy>);
static_assert(!std::movable<Throwy>);   // 传到上层
static_assert(std::destructible<int&>);
static_assert(!std::destructible<void>);
static_assert(!std::destructible<int[]>);
static_assert(std::destructible<int[3]>);

int main() {}
```

### `constructible_from`

```cpp
template<class T, class... Args>
  concept constructible_from = destructible<T> && is_constructible_v<T, Args...>;
```

¶1 说它约束用一组给定类型的实参初始化变量。`is_constructible_v<T, Args...>` 检查 `T t(declval<Args>()...);` 是否良构（[[meta.unary.prop]]），即直接初始化。加上 `destructible<T>`，是因为能构造却不能安全销毁的对象在值语义里没有用处。这个概念没有语义要求。

### `default_initializable`：三种写法都要能用

```cpp run title="default-initializable.cpp" ok
#include <concepts>
#include <type_traits>

static_assert(std::is_default_constructible_v<const int>);
static_assert(!std::default_initializable<const int>);

struct CM  { const int x; };
struct CM2 { const int x = 0; };
static_assert(!std::default_initializable<CM>);
static_assert(std::default_initializable<CM2>);

struct E { explicit E() = default; };
struct A { E e; };
static_assert(std::is_default_constructible_v<A>);
static_assert(!std::default_initializable<A>);

int main() {}
```

`const int` 可以写 `const int()`，却不能写 `const int t;`，因为 const 对象必须初始化，除非它的类型是 [[g:const-default-constructible]] 的类（[[dcl.init]]）。泛型代码三种写法都会用，所以概念把三种都检查：

```cpp
template<class T>
  constexpr bool is-default-initializable = see below;   // exposition only

template<class T>
  concept default_initializable = constructible_from<T> &&
                                  requires { T{}; } &&
                                  is-default-initializable<T>;
```

| 写法 | 初始化种类 | 由哪一项检查 |
|---|---|---|
| `T()` | 值初始化 | `constructible_from<T>` |
| `T{}` | 列表初始化（值初始化或聚合初始化） | `requires { T{}; }` |
| `T t;` | 默认初始化 | *`is-default-initializable`* |

¶1 定义 *`is-default-initializable<T>`*：变量定义 `T t;` 良构时为真。访问检查如同在与 `T` 无关的语境中进行，并且只看变量初始化的直接语境。

例子里的 `A` 说明 `T{}` 也会单独失败。`A()` 是值初始化，没有问题；`A{}` 是聚合初始化，要对成员 `e` 做复制列表初始化，而复制列表初始化选中 `explicit` 构造函数是非良构的。

!!! impl "libc++ 怎样检查 `T t;`"
    requires 表达式里不能声明变量，所以没法直接写出 `T t;` 是否良构。libc++ 在 `<__concepts/constructible.h>` 中用 `requires { ::new _Tp; }` 近似：不带初始化器的 new 表达式对对象做默认初始化，规则与 `T t;` 相同（[[expr.new]]）。

!!! history
    这个概念在 C++20 草案里最初叫 `default_constructible`，只检查 `is_default_constructible`。后来发现它说 `const int` 能默认构造，与泛型代码的实际写法不符，于是在 C++20 发布前加入了 `T{}` 和 `T t;` 两项检查，并改成现在的名字。

### `move_constructible`

```cpp run title="explicit-move.cpp" ok
#include <concepts>

struct ExplMove {
  ExplMove() = default;
  explicit ExplMove(ExplMove&&) = default;
};
static_assert(std::constructible_from<ExplMove, ExplMove>);
static_assert(!std::move_constructible<ExplMove>);

int main() {}
```

```cpp
template<class T>
  concept move_constructible = constructible_from<T, T> && convertible_to<T, T>;
```

`constructible_from<T, T>` 检查 `T t(rv)`，`convertible_to<T, T>` 检查 `T t = rv;` 和 `static_cast<T>(rv)`。移动构造函数是 `explicit` 的类型过不了第二项。

注意 `ExplMove x = ExplMove{};` 本身是合法的：C++17 起的强制复制消除让它根本不调用移动构造函数。但 `is_convertible_v<ExplMove, ExplMove>` 用的是 `declval<ExplMove>()`，一个 xvalue，从它初始化必须真正调用移动构造函数，于是失败。

¶1 的语义要求（`T` 是对象类型时）：设 `rv` 是 `T` 的右值，`u2` 是与 `rv` 相等的另一个对象。

- ¶1.1 定义 `T u = rv;` 之后，`u` 等于 `u2`；
- ¶1.2 `T(rv)` 等于 `u2`；
- ¶1.3 `T` 不是 const 时，`rv` 之后处于有效但未指明的状态；否则 `rv` 不变。

`T` 是引用类型时，`move_constructible<int&>` 也为真，但没有语义要求。

### `copy_constructible`

```cpp
template<class T>
  concept copy_constructible =
    move_constructible<T> &&
    constructible_from<T, T&> && convertible_to<T&, T> &&
    constructible_from<T, const T&> && convertible_to<const T&, T> &&
    constructible_from<T, const T> && convertible_to<const T, T>;
```

复制的来源有三种：非 const 左值、const 左值、const 右值，每种都要求直接和隐式两条路径可用。[[concepts.equality]] 第 6 段的隐式表达式变体只适用于 requires 表达式里写出的表达式，这里用的是类型特征，所以只能逐个列出。

这些都只是语法检查。有一个无约束转发构造函数 `template<class U> S(U&&)` 的类型，对非 const 左值来说模板比 `S(const S&)` 匹配得更好，`S s2 = s1;` 调用的根本不是复制构造函数。它照样满足 `copy_constructible`；如果那个模板构造出的对象不等于 `s1`，就是满足但不建模。

¶1 的语义要求（`T` 是对象类型时）：设 `v` 是 `T` 或 `const T` 的左值，或 `const T` 的右值。

- ¶1.1 定义 `T u = v;` 之后，`u` 等于 `v`，且 `v` 没有被修改；
- ¶1.2 `T(v)` 等于 `v`，且不修改 `v`。

复制品与原件相等、原件不变，这就是复制的含义。`auto_ptr` 那种复制即转移的设计违反了它。

## 常见误解

!!! pitfall "概念和同名的 *Cpp17* 要求一样"
    概念通常更严。`destructible` 禁止潜在抛出的析构函数；`default_initializable` 要求三种写法；`move_constructible` 要求能隐式转换，排除了 `explicit` 移动构造函数；`assignable_from` 要求返回 `T&` 并有公共引用。从 C++17 迁移到概念时，以前能用的类型现在不满足，原因多半在这几处。

!!! pitfall "在 ranges 里照旧用模板 `swap` 定制交换"
    在自己的命名空间里写一个无约束的 `template<class T> void swap(T&, T&)`，`ranges::swap` 会因为它与毒丸歧义而跳过它，直接退回移动三步。应当为具体类型提供非模板的 `swap`（最好是隐藏友元），或者给模板加约束，使它比毒丸更特化。

## 思考题

!!! question "思考题"
    1. `std::convertible_to<int, short>` 为真吗？`int` 和 `short` 建模它吗？
    2. `assignable_from` 为什么要求 `common_reference_with<const remove_reference_t<LHS>&, const remove_reference_t<RHS>&>`，而不只是 `convertible_to<RHS, remove_reference_t<LHS>>`？
    3. 对两个 `int` 左值 `x`、`y`，`ranges::swap(x, y)` 走 ¶2 的哪一项？`ranges::swap(x, x)` 呢？

<details markdown="1">
<summary>答案</summary>

1. 为真，也建模。窄化只在列表初始化中被禁止（[[dcl.init.list]]），隐式和显式转换都可用，结果都是同一个值，源对象也不被修改。`convertible_to` 只要求两条路径一致，不要求转换无损；无损是 `common_reference_with` 的语义要求才关心的。
2. ¶1.5.1 要求赋值后 `lhs` 等于 `rcopy`，这需要两边的值在同一种相等意义下可以比较。公共引用提供了这样一个共同的值域，而且转换到它保持相等。单纯的可转换性做不到：`RHS` 能转换到 `LHS` 的值类型，却可能和它没有一致的相等概念。
3. `int` 不是类或枚举类型，¶2.1 不适用；也不是数组，¶2.2 不适用。`int` 建模 `move_constructible` 和 `assignable_from<int&, int>`，所以走 ¶2.3，结果是常量表达式且 `noexcept`。`ranges::swap(x, x)` 也走 ¶2.3；按 ¶1 的注 1，它必须让 `x` 保持原值，移动构造加两次移动赋值对 `int` 正是如此。
</details>

## 速查

| 概念 | 语法核心 | 语义与设计要点 |
|---|---|---|
| `same_as` | 双向 `is_same_v` | 双向写法让 `same_as<T,U>` 与 `same_as<U,T>` 互相包含 |
| `derived_from` | `is_base_of` + 指针可转换 | 只认公有、无歧义的派生 |
| `convertible_to` | 隐式且显式 | 两条路径结果相等；右值源可被移走 |
| `common_reference_with` | 对称的 `common_reference_t` | 转换到 `C` 保持相等且不合并值 |
| `common_with` | 对称的 `common_type_t` | 同上，值的版本 |
| `integral` 等 | 类型特征 | `bool` 和字符类型也算 |
| `assignable_from<L, R>` | `L` 是左值引用，结果恰为 `L` | 返回左操作数本身；自移动除外 |
| `swappable(_with)` | `ranges::swap` 可调用 | 语义由 CPO 规定 |
| `destructible` | `is_nothrow_destructible` | 潜在抛出的析构函数不满足 |
| `constructible_from` | `destructible` + `is_constructible` | 直接初始化 |
| `default_initializable` | `T()`、`T{}`、`T t;` | `const int` 不满足 |
| `move_constructible` | 构造 + 隐式转换自 `T` | `explicit` 移动构造不满足 |
| `copy_constructible` | 三种来源 × 两条路径 | 复制品等于原件，原件不变 |
