---
title: 数值类型要求
summary: complex 与 valarray 只能用"数值类型"实例化——可默认构造、可复制构造、可复制赋值、可析构的 cv 非限定对象类型；T 的操作抛异常即 UB；valarray 的许多成员只在 T 满足额外要求时才能实例化
status: done
related: numerics, complex.numbers, numarray, utility.arg.requirements, temp.inst
tags: 标准库, 数值, 类型要求
updated: 2026-10-18
---

这一节只有四段，规定 `complex` 与 `valarray` 这两个"装数值的模板"对元素类型的最低要求。它很短，但有两处措辞在实际代码中有后果：一是"抛异常即 UB"，二是"成员函数按需实例化"。

## 什么是数值类型（¶1）

¶1：`complex` 和 `valarray` 由它们包含和操作的信息的类型参数化，程序**只能**用数值类型实例化它们。**数值类型**（numeric type）是满足以下四个具名要求的 cv 非限定对象类型 `T`（[[utility.arg.requirements]]）：

- *Cpp17DefaultConstructible*
- *Cpp17CopyConstructible*
- *Cpp17CopyAssignable*
- *Cpp17Destructible*

脚注 218 给出直觉："换句话说，就是值类型"——算术类型、指针、`complex` 本身、以及以值类型为元素的 `valarray` 特化。

注意这只是"能放进去"的门槛，不保证"能用"。对 `complex` 来说门槛还要更高：[[complex.numbers]] 的 [complex.numbers.general] ¶2 规定，用非 cv 非限定浮点类型实例化 `complex` 主模板的效果**未指明**。所以 `complex<int>` 虽然 `int` 是数值类型，标准也不保证它工作。

"shall instantiate these components only with a numeric type" 是对程序的要求，违反它没有规定诊断，属于库的一般规则：违反库对模板实参的要求是 UB（[[res.on.functions]]）。

## 操作抛异常（¶2）

¶2：如果 `T` 上的任何操作抛出异常，效果是未定义的。

这是一个**强**规定：库不需要为 `valarray<T>` 的赋值、加法等提供任何异常安全保证，因为一旦 `T` 抛异常，整个行为就没有定义了。这让实现可以自由地用表达式模板、延迟求值、就地覆盖等手段，而不必考虑"运算到一半抛异常时数组处于什么状态"。

实际影响：`valarray<BigInt>`，其中 `BigInt` 的加法可能因为分配失败抛 `bad_alloc`，严格说一旦真的抛了就是 UB。（[[numarray]] 另有一句：`valarray` 的库函数自身*可以*因资源不足抛 `bad_alloc`，但不强制。）

## 成员按需可用（¶3、¶4）

¶3：`valarray<T>` 的许多成员和相关函数，只有当 `T` 满足各自额外规定的要求时，才能成功实例化并表现出良定义的行为。

这依赖于类模板成员的**按需实例化**（[[temp.inst]]）：类模板特化被隐式实例化时，只实例化成员函数的声明，不实例化定义；定义要等到被使用时才实例化。于是 `valarray<T>` 可以声明 `operator<`、`min()`、`max()`，即使 `T` 没有 `<`——只要你不调用它们。

¶4 的例子：`valarray<complex<double>>` 合法，但对它调用 `operator>` 实例化不出来，因为 `complex` 没有序关系。

```cpp run title="valarray-complex.cpp" ok
#include <complex>
#include <valarray>

int main() {
  std::valarray<std::complex<double>> v{{1, 2}, {3, 4}};
  v *= std::complex<double>(0, 1);      // OK：complex 有 *=
  auto s = v.sum();                      // OK：sum 只要求 +=
  (void)s;
  // auto m = v.max();                   // error：max 用 operator<，complex 没有
  // std::valarray<bool> b = v > v;      // error：同理
}
```

一个实现细节上的旁注：在 libc++ 里把最后一行写成 `auto b = v > v;` 反而能编译——`v > v` 返回的是表达式模板对象（[[numarray]] 允许返回"替代类型"），比较要等到逐元素求值时才实例化；只要不读 `b` 的元素，错误就不会出现。这正是"按需实例化"在 `valarray` 上的另一种表现。

!!! note "现代写法的对照"
    这种"成员存在但不一定能实例化"的设计是 C++98 的风格。现代库组件通常用 *Constraints*（`requires` 子句）让不可用的成员**从重载决议中消失**，这样 `requires { v.max(); }` 能如实回答 `false`。`valarray` 没有这样改写，所以对 `valarray<complex<double>>` 做这种概念检测，结果取决于实现是否恰好在声明里暴露了错误——不要依赖它。

## 小结

| 规则 | 段落 | 后果 |
|---|---|---|
| 只能用数值类型实例化 `complex`/`valarray` | ¶1 | 违反是 UB（库的一般规则）；`complex` 另有"非浮点类型效果未指明" |
| `T` 的操作抛异常 | ¶2 | UB——库不提供异常安全保证 |
| 成员按需实例化 | ¶3–¶4 | `valarray<complex<double>>` 可用，但不能调用 `max`、`>` 等 |
