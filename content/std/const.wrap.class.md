---
title: 类模板 constant_wrapper
summary: C++26 的 std::constant_wrapper 与 std::cw——把一个编译期值编码进类型，使"作为函数实参传进来的常量"在函数体内仍能用于常量表达式；运算符会把运算结果继续包装成 constant_wrapper
status: done
related: utility, expr.const, expr.const.core, temp.param, temp.arg.nontype, basic.lookup.argdep, func.require, meta.help
tags: 标准库, C++26, 元编程, 常量表达式
updated: 2026-10-18
---

C++ 有一条让无数元编程者抓狂的规则：**函数形参永远不是常量表达式**。哪怕函数是 `constexpr` 的、调用时传的是字面量，在函数体里 `x` 也不能用作数组边界、模板实参或 `if constexpr` 条件——因为同一个函数也可能在运行期被调用，而 [[expr.const]] 不允许在常量表达式里读取一个"值未知"的形参。

传统的绕法是把值编码进**类型**：`std::integral_constant<int, 42>`（[[meta.help]]）。类型是编译期实体，传到哪里都还是编译期的，`decltype(x)::value` 永远是常量表达式。但 `integral_constant` 只支持整型和枚举、写法冗长、而且对它做 `+` 运算得到的是普通 `int`——一做运算就"掉回"运行期。

{{c++26}} `std::constant_wrapper<X>`（简写 `std::cw<X>`）是 `integral_constant` 的全面升级：

- 接受任何能作为常量模板实参的值（[[g:structural-type]] 的值，见 [[temp.param]]），不只是整数；
- 几乎所有运算符都被重载成"**对包装的值做运算，结果再包装成 `constant_wrapper`**"——`cw<42> + cw<13>` 的类型是 `constant_wrapper<55>`，常量性在运算中得以保持；
- 能隐式转换为被包装的值，所以在需要普通值的地方照常可用。

¶1 把它的目的说得很直接：

!!! std "[const.wrap.class]/1"
    The class template `constant_wrapper` aids in metaprogramming by ensuring that the evaluation of expressions comprised entirely of `constant_wrapper` are core constant expressions ([expr.const.core]), regardless of the context in which they appear.

    只要一个表达式**完全由 `constant_wrapper` 组成**，它的求值就是[[g:core-constant-expression]]——无论出现在什么上下文里，包括函数体内对形参的运算。

## 一个例子说清楚

```cpp run title="cw_basic.cpp" ok
#include <utility>
#include <array>
#include <type_traits>

constexpr auto add(auto a, auto b) { return a + b; }

template<class N>
auto make_array(N n) {
  return std::array<int, n>{};   // n 是函数形参，却能当常量表达式用
}

int main() {
  auto r = add(std::cw<42>, std::cw<13>);
  static_assert(std::is_same_v<decltype(r), std::constant_wrapper<55>>);
  static_assert(r == 55);               // 隐式转换为 int
  static_assert(decltype(r)::value == 55);

  auto arr = make_array(std::cw<3>);
  static_assert(arr.size() == 3);

  constexpr auto x = add(42, 13);       // 普通整数：结果只是 int
  static_assert(x == 55);
}
```

`std::array<int, n>` 为什么合法？`n` 是形参，但它的类型是 `constant_wrapper<3>`。模板实参需要一个 `size_t` 的转换常量表达式（[[expr.const]]），于是调用 `n` 的转换函数 `operator int()`——它返回静态数据成员 `value`，**根本不读取 `n` 这个对象本身的任何状态**（空类没有状态）。在常量求值中调用一个不访问对象的成员函数是允许的，所以整个表达式是常量表达式。`constant_wrapper` 的全部魔力就在这里：**值在类型里，对象只是一个空壳**。

¶3 的标准例子更戏剧化：`final_phase(auto gathered, auto available)` 里写 `if constexpr (gathered == available)`。传 `cw` 时，`==` 返回 `constant_wrapper<true>` 或 `constant_wrapper<false>`，再转成 `bool`，是常量表达式；传普通 `int` 时，`gathered == available` 读取了形参的值，不是常量表达式，编译失败。

## 类的结构

概要（[const.wrap.class] 开头）由两部分组成：

### 暴露于说明的 `cw-operators` 基类

`constant_wrapper` 公开继承一个说明专用的类 `cw-operators`，所有运算符都定义在那里，形式统一：

```cpp
template<constexpr-param L, constexpr-param R>
  friend constexpr auto operator+(L, R) noexcept
    -> constant_wrapper<(L::value + R::value)> { return {}; }
```

几个要点：

- **`constexpr-param` 概念**（[[g:constexpr-param]]，在 `<utility>` 概要中定义）：`requires { typename constant_wrapper<T::value>; }`——`T` 有一个静态的 `value`，且该值能再包装成 `constant_wrapper`。注意它是"鸭子类型"：任何有合适 `static constexpr value` 的类型（包括 `std::integral_constant`！）都满足，所以 `cw<1> + std::integral_constant<int, 2>{}` 也得到 `constant_wrapper<3>`。
- **运算在返回类型里完成**：`constant_wrapper<(L::value + R::value)>`。如果这个运算不是常量表达式（例如除以零、溢出）或结果不能作模板实参，返回类型替换失败，这个运算符模板就**被 SFINAE 掉**，表达式退回到"隐式转换后用内建运算符"的路径（或彻底报错）。
- **都是隐藏友元**（[[g:hidden-friend]]）：只能通过 ADL 找到，不会污染普通查找。因为 `cw-operators` 是 `constant_wrapper` 的基类，它是关联类（[[basic.lookup.argdep]]），所以对 `constant_wrapper` 实参总能找到。
- **一元**：`+ - ~ ! & *`；**二元**：算术、位运算、移位、比较（含 `<=>`）、`->*`。
- **`&&` 与 `||` 有额外的 requires 子句**：只有当至少一侧的值**不能**构造 `bool` 时才启用。对两侧都是 `bool`（或可转为 `bool`）的情形，就让表达式转换为 `bool` 后走内建 `&&`/`||`，**保留短路求值**；只有当被包装的是重载了 `&&` 的用户类型时才用包装版本。
- **逗号运算符被弃置**：`(cw<1>, cw<2>)` 是错误。重载逗号会改变其求值顺序语义，干脆禁止。
- **伪变更运算符**（*pseudo-mutators*）：`++`、`--` 以及复合赋值 `+=` 等，都用显式对象形参（`this T`）声明，返回 `constant_wrapper<(++T::value)>` 之类。对普通的 `int` 值，`++T::value` 试图修改一个模板形参对象，不是合法的常量表达式，于是被 SFINAE 掉——`++cw<5>` 是错误。它们的存在是为了被包装的**用户类型**：如果某个字面类型的 `operator++` 是 `const` 成员、返回一个新值（"函数式"的自增），那么 `++cw<obj>` 就能得到新值的 `constant_wrapper`。

```cpp run title="cw_ops.cpp" ok
#include <utility>
#include <type_traits>
static_assert(std::is_same_v<decltype(std::cw<true> && std::cw<false>), bool>);   // 内建 &&
static_assert(std::is_same_v<decltype(std::cw<1> < std::cw<2>), std::constant_wrapper<true>>);
static_assert(std::is_same_v<decltype(-std::cw<3>), std::constant_wrapper<-3>>);
static_assert(std::is_same_v<decltype(std::cw<2> + 3), int>);   // 混入普通值：退化为 int
int main(){}
```

```cpp run title="cw_errors.cpp" error
#include <utility>
int main() {
  auto x = std::cw<5>;
  auto y = ++x;          // error: ++T::value 无效（修改 int 常量），伪变更运算符被 SFINAE 掉
  (void)y;
  constexpr auto q = (std::cw<1>, std::cw<2>);   // error: 逗号运算符被弃置
}
```

### `constant_wrapper` 本体

```cpp
template<auto X, class T = decltype(X)>
struct constant_wrapper : cw-operators {
  static constexpr decltype(auto) value = (X);
  using type = constant_wrapper;
  using value_type = decltype(X);
  // operator=、转换函数、static operator()、static operator[]
};
```

- **`value` 的声明是 `decltype(auto) value = (X);`**——注意括号。对标量类型的 `X`，`(X)` 是 prvalue，`value` 的类型是 `const int` 之类；对类类型的 `X`，常量模板形参是一个左值，指代**模板形参对象**（[[g:template-parameter-object]]，[[temp.param]]），`(X)` 的类型是 `const T&`，所以 `value` 是绑定到那个唯一对象的引用。这样 `&cw<obj>.value` 在整个程序中是同一个地址，且不会复制可能很大的对象。
- **`type` 指向自身**，与 `integral_constant` 保持一致。
- **`operator=`** 是 `const` 的、返回 `constant_wrapper<(value = R::value)>`——同样只对"赋值运算符是 const 且返回值"的用户类型有意义。
- **转换函数** `operator decltype(value)() const` 返回 `value`：这是 `cw<5>` 能在任何需要 `int` 的地方使用的原因。

### 第二个模板形参与 ADL（¶2）

¶2 规定：如果 `constant_wrapper` 的某个特化以不满足 `is_same_v<T, value_type>` 的 `T` 实例化，**程序非良构**。也就是说用户不能自己指定第二个实参——它只是 `decltype(X)` 的一个"影子"。

为什么需要这个影子？注 1 解释：为了 [[g:argument-dependent-lookup]]。ADL 的关联实体（[[g:associated-entities]]）包含类模板特化的**类型模板实参**，但**不包含**常量模板实参的类型。如果只有 `template<auto X>`，`constant_wrapper<geo::Point{...}>` 与命名空间 `geo` 毫无关系，`norm1(cw<p>)` 找不到 `geo::norm1`。多一个 `class T = decltype(X)` 后，`geo::Point` 成为类型模板实参，`geo` 就成了关联命名空间：

```cpp run title="cw_adl.cpp" ok
#include <utility>

namespace geo {
  struct Point { int x, y; };
  constexpr int norm1(Point p) { return (p.x < 0 ? -p.x : p.x) + (p.y < 0 ? -p.y : p.y); }
}

int main() {
  constexpr auto p = std::cw<geo::Point{3, -4}>;
  // 第二个模板实参 geo::Point 让 geo 成为关联命名空间，ADL 找得到 norm1；
  // 再经 operator geo::Point() 隐式转换完成调用
  static_assert(norm1(p) == 7);
}
```

作为对照，一个只有 `template<auto X>` 的包装器做不到：

```cpp run title="no_shadow_param.cpp" error
template<auto X> struct W { operator decltype(X)() const { return X; } };
namespace geo {
  struct Point { int x, y; };
  constexpr int norm1(Point p) { return p.x + p.y; }
}
int main() {
  constexpr int r = norm1(W<geo::Point{3, 4}>{});   // error: ADL 找不到 geo::norm1
}
```

## 调用与下标（¶4–¶11）

`constant_wrapper` 有两个 **static** 的 `operator()` 与 `operator[]`（C++23 允许 static 调用运算符，C++23 起也允许多参数下标）。

¶4 定义 *call-expr*：

- 如果所有实参类型（去掉 cvref 后）都满足 `constexpr-param`，并且 `constant_wrapper<INVOKE(value, remove_cvref_t<Args>::value...)>` 是合法类型，那么 *call-expr* 是这个 `constant_wrapper<...>{}`——**全常量调用，结果仍是常量**；
- 否则 *call-expr* 是 `INVOKE(value, std::forward<Args>(args)...)`——**有运行期实参时退化为普通调用**。

¶5 *Constraints*：*call-expr* 是有效表达式；¶6 返回它；¶7 异常规格为 `noexcept(call-expr)`。*INVOKE* 的含义见 [[func.require]]，所以被包装的值可以是函数指针、lambda、成员指针等任何可调用对象。¶8–¶11 对 `operator[]` 做了完全平行的规定（*subscr-expr*，用 `value[...]` 代替 *INVOKE*）。

```cpp run title="cw_call.cpp" ok
#include <utility>
#include <type_traits>
#include <cstdio>

constexpr int twice(int a) { return a * 2; }
constexpr int table[] = {10, 20, 30};

void check(auto a, auto b) {
  if constexpr (a == b)                 // a、b 是普通函数形参
    std::puts("equal");
  else
    std::puts("different");
}

int main(int argc, char**) {
  auto c = std::cw<twice>(std::cw<21>);             // 全部是 constant_wrapper：结果也是
  static_assert(std::is_same_v<decltype(c), std::constant_wrapper<42>>);

  int rt = std::cw<twice>(argc);                    // 混入运行期实参：退化为普通调用
  auto e = std::cw<table>[std::cw<1>];              // 下标同理
  static_assert(e == 20);

  check(std::cw<1> + std::cw<2>, std::cw<3>);       // 打印 equal
  std::printf("%d\n", rt);
}
```

## 与 `integral_constant` 对比

| | `integral_constant<T, v>` | `constant_wrapper<X>` |
|---|---|---|
| 可包装的值 | 整型、枚举（及 `bool`） | 任意结构化类型的值（含类类型、指针、函数指针） |
| 简写 | `bool_constant`、`true_type` 等少量别名 | `cw<X>`（自动推导类型） |
| 运算结果 | 转换为 `T` 后用内建运算，结果是普通值 | 结果再包装为 `constant_wrapper` |
| 调用/下标 | `operator()` 返回值本身 | 全常量实参时结果仍是 `constant_wrapper` |
| ADL | 关联 `T` | 通过影子模板形参关联 `decltype(X)` |

二者可以混用：`constexpr-param` 只要求有 `::value`，所以 `integral_constant` 也满足它。

## 用途

- **把"编译期参数"传进普通函数**：替代"把参数做成模板形参"的写法，让调用语法与普通函数一致（`f(cw<3>)` 而不是 `f<3>()`），并且同一个函数还能接收运行期值（形参是 `auto`）。
- **在 SIMD / 线性代数库中**表达编译期已知的尺寸、步长、掩码，同时保留运算符语法——这类"编译期已知、但希望像普通值一样书写"的参数在 `std::simd` 一类库中尤其常见。
- **作为 `std::function_ref` 等的"编译期绑定函数"标签**：当前草案里 `function_ref` 等接口用 `constant_wrapper` 类型的实参来表示"在编译期就确定了被调用的函数"（见 [[func.wrap.ref]]）。

## 实现：libc++

!!! impl "libc++ 23（`__utility/constant_wrapper.h`）"
    libc++ 23 已实现 `constant_wrapper`，`<version>` 中 `__cpp_lib_constant_wrapper` 为 `202606L`。几处实现细节：
    
    - 第二个模板形参的默认实参写的是 `remove_cvref_t<decltype(_Xp)>`，然后在类体里 `static_assert(is_same_v<_Tp, value_type>, ...)`——用静态断言实现 ¶2 的"非良构"；
    - `value` 声明为 `static constexpr decltype((_Xp)) value = (_Xp);`，与草案的 `decltype(auto)` 等价；
    - 草案中单个 `operator()` / `operator[]` 内部用"*call-expr* 二选一"描述，libc++ 拆成了**两对互斥约束的重载**：一个返回 `constant_wrapper<std::invoke(value, ...)>`，另一个在前者不可用时做普通 `std::invoke`；
    - 多处返回类型写成 `constant_wrapper<auto(_Lp::value->*_Rp::value)>` 之类，注释说明是为绕过一个 Clang 缺陷而加的 `auto(...)`，待所有受支持的 Clang 修复后移除；
    - 大部分运算符带 `[[nodiscard]]`。

## 历史

!!! history "从 constexpr_v 到 constant_wrapper"
    这个设施源于提案 P2781（最初名为 `std::constexpr_v`），在 C++26 周期中更名为 `constant_wrapper` 并被采纳。C++26 定稿之后它又经历了修订：当前草案的形式（`template<auto X, class T = decltype(X)>`、`value` 用 `decltype(auto)` 声明、`operator()` / `operator[]` 在有运行期实参时退化为普通调用）与最初进入草案时的措辞并不完全相同，libc++ 23 的特性测试宏也相应是 `202606L`。读旧资料时请以当前草案为准。

## 思考题

!!! question "思考题 1"
    `std::cw<1> + 2` 的类型是什么？`std::cw<1> + std::integral_constant<int, 2>{}` 呢？

<details markdown="1">
<summary>展开查看答案与解析</summary>

前者是 `int`：`int` 不满足 `constexpr-param`（没有 `::value`），`cw-operators` 的 `operator+` 不可行，于是 `cw<1>` 经转换函数变成 `int`，走内建加法（[[over.built]]）。后者是 `constant_wrapper<3>`：`integral_constant<int, 2>` 有 `static constexpr int value = 2`，且 `constant_wrapper<2>` 合法，满足 `constexpr-param`，于是选中包装版本。注意此处 ADL 能找到隐藏友元，是因为左操作数 `constant_wrapper<1>` 的基类 `cw-operators` 是关联类。
</details>

!!! question "思考题 2"
    为什么 `cw<true> && cw<false>` 的结果是 `bool` 而不是 `constant_wrapper<false>`？这样设计丢失了什么、保住了什么？

<details markdown="1">
<summary>展开查看答案与解析</summary>

`cw-operators` 中 `operator&&` 的 requires 子句要求至少一侧的值**不能**构造 `bool`；对 `bool` 值不满足，包装版本不参与重载决议，表达式转换为 `bool` 后使用内建 `&&`。丢失的是"结果仍为 constant_wrapper"（不过结果本身仍是常量表达式，因为两侧的转换都不读取对象状态）；保住的是**短路求值**——重载的 `&&` 是普通函数调用，两侧都会被求值（[[over.match.oper]]），而内建 `&&` 在左侧为假时不求值右侧。
</details>

## 小结

!!! summary "核心要点"
    - `constant_wrapper<X>` 把值放进类型，对象本身是空的；对它的运算不读取对象状态，因此在任何上下文（包括函数形参）都是常量表达式。
    - 运算符定义在说明专用基类 `cw-operators` 中，都是隐藏友元或显式对象形参成员，运算在返回类型里完成，失败则被 SFINAE 掉。
    - `&&`/`||` 对可转为 `bool` 的值不做包装以保留短路；逗号被弃置；伪变更运算符只对"函数式"用户类型有意义。
    - 第二个模板形参只是 `decltype(X)` 的影子，用户指定不同的类型则非良构；它存在的唯一理由是 ADL。
    - `operator()` / `operator[]` 在全常量实参时返回 `constant_wrapper`，否则退化为普通 *INVOKE* / 下标。
