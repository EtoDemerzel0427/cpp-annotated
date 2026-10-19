---
title: 数值类型要求
summary: complex 与 valarray 只能用数值类型（可默认构造、可复制、可析构的值类型）实例化；元素类型的操作抛异常是 UB；valarray 的成员只在用到时才要求元素类型支持相应运算。
status: done
related: numerics, complex.numbers, numarray, utility.arg.requirements, temp.inst
tags: 标准库, 数值, 类型要求
updated: 2026-10-19
---

!!! tldr
    - `complex` 和 `valarray` 只能用数值类型实例化：可默认构造、可复制构造、可复制赋值、可析构的 cv 非限定对象类型，直观地说就是值类型。
    - 满足这四条不等于能用：`complex` 只对浮点类型有保证，`complex<int>` 的效果是未指明的。
    - 元素类型的任何操作抛出异常，行为都是未定义的，所以 `valarray` 不提供异常安全保证。
    - `valarray<T>` 的很多成员只有在 `T` 支持相应运算时才能实例化。`valarray<complex<double>>` 合法，但不能调用 `max()` 或 `>`。

## 什么是数值类型（¶1）

¶1 `complex` 和 `valarray` 是以元素类型为参数的模板，程序只能用**数值类型**（numeric type）实例化它们。数值类型是满足 *Cpp17DefaultConstructible*、*Cpp17CopyConstructible*、*Cpp17CopyAssignable*、*Cpp17Destructible* 四项要求（[[utility.arg.requirements]]）的 cv 非限定对象类型。脚注 218 的解释是"换句话说，就是值类型"：算术类型、指针、`complex`，以及元素为值类型的 `valarray`。

这只是放得进去的门槛。`complex` 还有更严格的规定：用 cv 非限定浮点类型以外的类型实例化 `complex` 主模板，效果是未指明的（[[complex.numbers]] 的 [complex.numbers.general] ¶2）。`int` 是数值类型，但标准不保证 `complex<int>` 能工作。

这条规则是对程序的要求，标准没有要求编译器诊断。违反库对模板实参的要求，按库的一般规则是未定义行为（[[res.on.functions]]）。

## 元素操作抛异常是 UB（¶2）

¶2 如果 `T` 上的任何操作抛出异常，效果是未定义的。

这样规定之后，库不必为 `valarray<T>` 的赋值、加法等操作提供任何异常安全保证。实现可以自由使用表达式模板、延迟求值、就地覆盖，不必考虑运算到一半抛出异常时数组处于什么状态。

后果是：如果 `BigInt` 的加法可能因为内存不足抛出 `bad_alloc`，那么 `valarray<BigInt>` 的加法一旦真的抛出，就是 UB。[[numarray]] 另外允许 `valarray` 自己的库函数在资源不足时抛出 `bad_alloc`，这是另一回事。

## 成员按需可用（¶3、¶4）

```cpp run title="valarray-complex.cpp" ok
#include <complex>
#include <valarray>

int main() {
  std::valarray<std::complex<double>> v{{1, 2}, {3, 4}};
  v *= std::complex<double>(0, 1);   // OK：complex 有 *=
  auto s = v.sum();                  // OK：sum 只要求 +=
  (void)s;
  // auto m = v.max();               // error：max 要用 <，complex 没有
  // std::valarray<bool> b = v > v;  // error：同理
}
```

¶3 `valarray<T>` 的许多成员和相关函数，只有在 `T` 满足各自额外的要求时，才能成功实例化并具有良定义的行为。¶4 的例子就是上面这段代码：`valarray<complex<double>>` 是合法的类型，但 `complex` 没有序关系，`operator>` 实例化不出来。

这依赖于类模板成员的按需实例化（[[temp.inst]]）：类模板特化被隐式实例化时，成员函数只实例化声明，定义要等到被使用时才实例化。所以 `valarray<T>` 可以声明 `max()` 和 `operator<`，即使 `T` 没有 `<`，只要程序不调用它们。

!!! impl "libc++ 的表达式模板"
    在本机 libc++ 中，把最后一行写成 `auto b = v > v;` 可以通过编译。`v > v` 返回的是表达式模板对象（[[numarray]] 允许返回这样的替代类型），比较要到逐元素求值时才实例化。只要不读取 `b` 的元素，错误就不会出现。

!!! note "与现代库组件的对比"
    这种成员存在但不一定能实例化的设计是 C++98 的风格。较新的库组件用 *Constraints*（`requires` 子句）让不可用的成员退出重载决议，这样 `requires { v.max(); }` 能如实给出 `false`。`valarray` 没有这样改写，对它做这类概念检测，结果取决于实现是否恰好在声明里暴露了错误，不能依赖。

## 小结

| 规则 | 段落 | 后果 |
|---|---|---|
| 只能用数值类型实例化 `complex`/`valarray` | ¶1 | 违反是 UB；`complex` 用非浮点类型实例化，效果未指明 |
| `T` 的操作抛异常 | ¶2 | UB，库不提供异常安全保证 |
| 成员按需实例化 | ¶3–¶4 | `valarray<complex<double>>` 可用，但不能调用 `max`、`>` 等 |
