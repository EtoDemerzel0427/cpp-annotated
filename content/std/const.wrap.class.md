---
title: 类模板 constant_wrapper
summary: C++26 的 std::constant_wrapper 与 std::cw 把一个编译期值编码进类型，让作为函数实参传入的常量在函数体内仍能用于常量表达式，对它做运算的结果也仍是 constant_wrapper。
status: done
related: utility, expr.const, expr.const.core, temp.param, temp.arg.nontype, basic.lookup.argdep, func.require, meta.help, func.wrap.ref
papers: P2781
tags: 标准库, C++26, 元编程, 常量表达式
updated: 2026-10-19
---

!!! tldr
    - 函数形参不是常量表达式，即使调用时传的是字面量；`std::cw<42>` 把值放进类型，对象本身是空的，所以它作为形参传进去后仍能当常量用。
    - 对 `constant_wrapper` 做运算，结果还是 `constant_wrapper`：`cw<42> + cw<13>` 的类型是 `constant_wrapper<55>`。只要混入一个普通值，就退化为普通运算。
    - `&&`、`||` 对 `bool` 值不做包装，以保留短路求值；逗号运算符被弃置；`++cw<5>` 是错误。
    - 第二个模板形参 `T` 只是 `decltype(X)` 的影子，作用是让 ADL 找到被包装值所在命名空间里的函数；指定别的类型是非良构的。
    - `operator()` 和 `operator[]` 在实参全是 `constant_wrapper` 时返回 `constant_wrapper`，否则退化为普通调用和下标。

## 形参不是常量表达式

<div class="compare" markdown="1">

```cpp error
#include <array>
auto make(int n) {
  // error: n 不是常量表达式
  return std::array<int, n>{};
}
```

```cpp ok
#include <array>
#include <utility>
auto make(auto n) {
  return std::array<int, n>{};  // OK
}
auto a = make(std::cw<3>);
```

</div>

左边的 `make` 即使写成 `constexpr`、即使调用时传的是字面量，`n` 在函数体内也不能用作模板实参。同一个函数可以在运行时以任意值调用，常量表达式的规则（[[expr.const]]）不允许读取一个值未知的形参。

右边的 `n` 的类型是 `std::constant_wrapper<3>`。模板实参 `n` 需要一个 `size_t` 常量，于是调用 `n` 的转换函数，它返回静态数据成员 `value`。这次调用不读取对象 `n` 的任何状态（它是空类，本来就没有状态），所以整个表达式仍是常量表达式。值在类型里，对象只是一个空壳。

把值编码进类型的做法早就有了：`std::integral_constant<int, 3>`（[[meta.help]]）。但它只能包装整型和枚举，写法冗长，而且 `integral_constant` 相加得到的是普通 `int`，常量性一做运算就丢了。{{c++26}} 的 `std::constant_wrapper<X>`（简写变量模板 `std::cw<X>`）补上了这些缺口。

!!! std "[const.wrap.class]/1"
    The class template `constant_wrapper` aids in metaprogramming by ensuring that the evaluation of expressions comprised entirely of `constant_wrapper` are core constant expressions ([expr.const.core]), regardless of the context in which they appear.

¶1 完全由 `constant_wrapper` 组成的表达式，在任何上下文中求值都是[[g:core-constant-expression|核心常量表达式]]，包括在函数体内对形参做运算。可包装的值是任何能作常量模板实参的值，也就是[[g:structural-type|结构化类型]]的值（[[temp.param]]），不只是整数。

## 运算结果仍是 constant_wrapper

```cpp run title="cw_basic.cpp" ok
#include <utility>
#include <type_traits>

constexpr auto add(auto a, auto b) { return a + b; }

int main() {
  auto r = add(std::cw<42>, std::cw<13>);
  static_assert(std::is_same_v<decltype(r), std::constant_wrapper<55>>);
  static_assert(r == 55);                  // 隐式转换为 int
  static_assert(decltype(r)::value == 55);

  constexpr auto x = add(42, 13);          // 普通整数：结果只是 int
  static_assert(x == 55);
}
```

¶3 的标准例子用的正是这个性质。函数 `final_phase(auto gathered, auto available)` 里写 `if constexpr (gathered == available)`：传 `constant_wrapper` 时，`==` 的结果是 `constant_wrapper<true>` 或 `constant_wrapper<false>`，再转换为 `bool`，是常量表达式；传普通 `int` 时，`==` 要读取两个形参的值，不是常量表达式，编译失败。

### 运算符怎样定义

`constant_wrapper` 公开继承一个说明专用的类 `cw-operators`，所有运算符都定义在那里，形式统一：

```cpp
template<constexpr-param L, constexpr-param R>
  friend constexpr auto operator+(L, R) noexcept
    -> constant_wrapper<(L::value + R::value)> { return {}; }
```

概念 `constexpr-param`（在 [[utility]] 的概要中定义）的要求是 `typename constant_wrapper<T::value>` 有效：`T` 有一个静态成员 `value`，而且这个值能再被包装。它只看有没有 `::value`，所以 `std::integral_constant` 也满足它。

运算发生在返回类型里。如果 `L::value + R::value` 不是常量表达式（比如除以零、有符号溢出），或者结果不能作模板实参，替换就失败，这个模板被排除出重载决议（SFINAE：模板实参替换失败时只丢弃这个候选，不报错，见 [[temp.deduct]]）。这时表达式改为把操作数转换成被包装的值，使用内建运算符。

这些运算符都是[[g:hidden-friend|隐藏友元]]：在类内定义的友元函数，普通查找找不到，只能通过 ADL（实参依赖查找，按实参类型的关联类和命名空间查找函数，见 [[basic.lookup.argdep]]）找到。`cw-operators` 是 `constant_wrapper` 的基类，属于关联类，所以只要有一个操作数是 `constant_wrapper`，就能找到它们。

```cpp run title="cw_ops.cpp" ok
#include <utility>
#include <type_traits>
using std::cw, std::constant_wrapper, std::is_same_v;
static_assert(is_same_v<decltype(cw<1> < cw<2>), constant_wrapper<true>>);
static_assert(is_same_v<decltype(-cw<3>), constant_wrapper<-3>>);
static_assert(is_same_v<decltype(cw<1> + std::integral_constant<int, 2>{}),
                        constant_wrapper<3>>);
static_assert(is_same_v<decltype(cw<2> + 3), int>);             // 混入普通值：int
static_assert(is_same_v<decltype(cw<true> && cw<false>), bool>); // 内建 &&
int main() {}
```

`cw-operators` 提供的一元运算符有 `+ - ~ ! & *`，二元运算符有算术、位运算、移位、比较（含 `<=>`）和 `->*`。其中有三处特殊安排。

**`&&` 和 `||`**：带一个 requires 子句，只有至少一侧的值不能构造 `bool` 时才可用。两侧都能转换为 `bool` 时，表达式改用内建 `&&`、`||`，保留短路求值。重载的 `&&` 是普通函数调用，两个操作数都会被求值（[[over.match.oper]]）。包装版本只为重载了 `&&` 的用户类型准备。

**逗号**：`operator,` 被弃置，`(cw<1>, cw<2>)` 是错误。

**伪变更运算符**（pseudo-mutators）：`++`、`--` 和 `+=` 等复合赋值，用显式对象形参（`this T`）声明，返回类型是 `constant_wrapper<(++T::value)>` 之类。对 `int` 值，`++T::value` 要修改一个常量，不是有效的常量表达式，于是被排除，`++cw<5>` 是错误。它们服务的是被包装的用户类型：如果某个字面类型的 `operator++` 是 `const` 成员、返回一个新值，`++cw<obj>` 就得到新值的 `constant_wrapper`。

```cpp run title="cw_errors.cpp" error
#include <utility>
int main() {
  auto x = std::cw<5>;
  auto y = ++x;                     // error: ++T::value 无效，没有可用的 ++
  auto q = (std::cw<1>, std::cw<2>); // error: 逗号运算符被弃置
}
```

## 类的定义

```cpp
template<auto X, class T = decltype(X)>
struct constant_wrapper : cw-operators {
  static constexpr decltype(auto) value = (X);
  using type = constant_wrapper;
  using value_type = decltype(X);
  // operator=、转换函数、static operator()、static operator[]
};
template<auto X>
  constexpr auto cw = constant_wrapper<X>{};
```

`value` 的初始化器 `(X)` 带括号，这是有意的。对标量类型的 `X`，`(X)` 是 prvalue，`value` 就是一个常量 `int` 之类。对类类型的 `X`，常量模板形参是一个左值，指代**模板形参对象**（[[g:template-parameter-object|template parameter object]]，同一个值在整个程序中只有一个这样的对象，见 [[temp.param]]），`(X)` 的类型是 `const T&`，`value` 就是绑定到那个对象的引用。这样不会复制可能很大的对象，`&cw<obj>.value` 在整个程序中也是同一个地址。

`type` 指向自身，与 `integral_constant` 一致。转换函数 `operator decltype(value)() const` 返回 `value`，所以 `cw<5>` 可以用在任何需要 `int` 的地方。`operator=` 是 `const` 成员，返回 `constant_wrapper<(value = R::value)>`，和伪变更运算符一样只对特殊的用户类型有意义。

### 第二个模板形参用于 ADL（¶2）

¶2 如果用不满足 `is_same_v<T, value_type>` 的 `T` 实例化 `constant_wrapper`，程序非良构。用户不能自己指定第二个实参，它只是 `decltype(X)` 的影子。

注 1 解释了它存在的理由。ADL 的关联实体包括类模板特化的类型模板实参，但不包括常量模板实参的类型。如果只有 `template<auto X>`，`constant_wrapper<geo::Point{3, -4}>` 与命名空间 `geo` 没有任何联系。多了 `class T = decltype(X)`，`geo::Point` 成为类型模板实参，`geo` 就是关联命名空间：

<div class="compare" markdown="1">

```cpp ok
#include <utility>
namespace geo {
  struct Point { int x, y; };
  constexpr int norm1(Point p)
    { return p.x + p.y; }
}
constexpr auto p =
  std::cw<geo::Point{3, 4}>;
// ADL 找到 geo::norm1，
// 再经转换函数得到 Point
static_assert(norm1(p) == 7);
```

```cpp error
template<auto X> struct W {
  operator decltype(X)() const
    { return X; }
};
namespace geo {
  struct Point { int x, y; };
  constexpr int norm1(Point p)
    { return p.x + p.y; }
}
// error: ADL 找不到 geo::norm1
int r = norm1(W<geo::Point{3, 4}>{});
```

</div>

## 调用与下标（¶4–¶11）

`constant_wrapper` 有静态的 `operator()` 和 `operator[]`（C++23 起允许静态调用运算符和多参数下标）。

¶4 先定义 *call-expr*。如果去掉 cv 和引用后，所有实参类型都满足 `constexpr-param`，而且 `constant_wrapper<INVOKE(value, remove_cvref_t<Args>::value...)>` 是有效类型，*call-expr* 就是这个类型的一个对象，结果仍是常量。否则 *call-expr* 是 `INVOKE(value, std::forward<Args>(args)...)`，也就是普通调用。

¶5–¶7 `operator()` 的约束是 *call-expr* 有效，效果是返回 *call-expr*，异常规格是 `noexcept(call-expr)`。*INVOKE* 的含义见 [[func.require]]，所以被包装的值可以是函数指针、lambda、成员指针等任何可调用对象。

¶8–¶11 对 `operator[]` 作了平行的规定，用 `value[...]` 代替 *INVOKE*。

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
  auto c = std::cw<twice>(std::cw<21>);   // 全部是 constant_wrapper：结果也是
  static_assert(std::is_same_v<decltype(c), std::constant_wrapper<42>>);

  int rt = std::cw<twice>(argc);          // 混入运行时实参：普通调用
  auto e = std::cw<table>[std::cw<1>];    // 下标同理
  static_assert(e == 20);

  check(std::cw<1> + std::cw<2>, std::cw<3>);   // 打印 equal
  std::printf("%d\n", rt);
}
```

## 与 integral_constant 对比

| | `integral_constant<T, v>` | `constant_wrapper<X>` |
|---|---|---|
| 可包装的值 | 整型、枚举 | 任意结构化类型的值（类对象、指针、函数指针等） |
| 简写 | `bool_constant`、`true_type` 等少量别名 | `cw<X>`，类型自动推导 |
| 运算结果 | 转换为 `T` 后用内建运算，结果是普通值 | 再包装为 `constant_wrapper` |
| 调用、下标 | `operator()` 返回值本身 | 实参全是常量时结果仍是 `constant_wrapper` |
| ADL 关联 | `T` | 通过影子形参关联 `decltype(X)` |

两者可以混用，因为 `integral_constant` 也满足 `constexpr-param`。

`constant_wrapper` 适合把编译期参数传给普通函数：调用写成 `f(cw<3>)` 而不是 `f<3>()`，同一个 `auto` 形参的函数还能接收运行时值。标准库自己也这样用：`std::function_ref` 用 `constant_wrapper` 类型的实参表示在编译期就确定了被调用的函数（[[func.wrap.ref]]），多维视图的切片接口也接受它表示编译期已知的范围（[[views.multidim]]）。

!!! impl "libc++ 23"
    libc++ 23 已经实现了 `constant_wrapper`，特性测试宏 `__cpp_lib_constant_wrapper` 为 `202606L`。实现在 `__utility/constant_wrapper.h`：第二个模板形参的默认实参写作 `remove_cvref_t<decltype(_Xp)>`；草案里用 *call-expr* 二选一描述的 `operator()`、`operator[]`，被拆成了两对约束互斥的重载；大多数运算符带 `[[nodiscard]]`。

!!! history
    这个设施源于 [[P2781]]，最初名为 `std::constexpr_v`，修订中先后改名为 `constexpr_wrapper` 和 `constant_wrapper`，以后者进入 C++26。进入草案之后它的措辞还改过，当前草案中 `operator()`、`operator[]` 在有运行时实参时退化为普通调用的形式，与早期版本不完全相同。libc++ 的特性测试宏 `202606L` 反映的就是较新的修订。读旧资料时以当前草案为准。

## 思考题

!!! question "思考题 1"
    `std::cw<1> + 2` 的类型是什么？`std::cw<1> + std::integral_constant<int, 2>{}` 呢？

<details markdown="1">
<summary>答案</summary>

前者是 `int`。`int` 没有 `::value`，不满足 `constexpr-param`，`cw-operators` 的 `operator+` 不可行；`cw<1>` 经转换函数变成 `int`，使用内建加法（[[over.built]]）。

后者是 `constant_wrapper<3>`。`integral_constant<int, 2>` 有静态成员 `value`，`constant_wrapper<2>` 有效，满足 `constexpr-param`，于是选中包装版本。ADL 能找到这个隐藏友元，是因为左操作数的基类 `cw-operators` 是关联类。
</details>

!!! question "思考题 2"
    为什么 `cw<true> && cw<false>` 的结果是 `bool` 而不是 `constant_wrapper<false>`？这样设计放弃了什么，保住了什么？

<details markdown="1">
<summary>答案</summary>

`operator&&` 的 requires 子句要求至少一侧的值不能构造 `bool`。两侧都是 `bool` 时不满足，包装版本不参与重载决议，表达式把两侧转换为 `bool` 后使用内建 `&&`。

放弃的是结果的类型：它不再是 `constant_wrapper`。不过结果仍是常量表达式，因为两侧的转换都不读取对象状态。保住的是短路求值：重载的 `&&` 是普通函数调用，两侧都会被求值，内建 `&&` 在左侧为假时不求值右侧。
</details>
