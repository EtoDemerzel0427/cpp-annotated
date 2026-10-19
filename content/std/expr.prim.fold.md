---
title: 折叠表达式
summary: 用同一个二元运算符把一个包的所有元素连成一个表达式：四种形式、结合方向、操作数的语法限制，以及空包时的规则。
status: done
since: c++17
papers: N4295, P0036R0
related: temp.variadic, expr.prim, temp.constr.fold, expr.comma
tags: 包展开, 可变参数模板, 表达式
updated: 2026-10-19
---

!!! tldr
    - `(... op e)`、`(e op ...)`、`(i op ... op e)`、`(e op ... op i)` 四种写法分别是一元左折叠、一元右折叠、二元左折叠、二元右折叠；`...` 在哪一侧，括号就往哪一侧堆。
    - 外层括号是语法的一部分，操作数只能是 *cast-expression*，所以 `(... + a * 2)` 要写成 `(... + (a * 2))`。
    - 空包时二元折叠得到初值；一元折叠只有 `&&`（`true`）、`||`（`false`）、`,`（`void()`）有定义，其余运算符非良构。
    - 包只有一个元素时，一元折叠的结果就是这个元素本身，`(... && a)` 不一定是 `bool`。
    - 折叠表达式本身是一个包展开，它的展开结果写在 [[temp.variadic#15]]。

## 从递归模板到折叠

对一个[[g:pack|包]]（模板形参包或函数形参包，[[temp.variadic]]）求和，C++17 之前要写递归模板；C++17 起一个**折叠表达式**（fold expression）就够了：

<div class="compare" markdown="1">

```cpp ok
// C++11/14：递归
int sum() { return 0; }
template<class T, class... R>
int sum(T t, R... r) {
  return t + sum(r...);
}
```

```cpp ok
// C++17：折叠表达式
template<class... A>
int sum(A... a) {
  return (0 + ... + a);
}
```

</div>

实例化时，`(0 + ... + a)` 直接展开成 `((0 + a₁) + a₂) + a₃` 这样的嵌套表达式，没有递归的函数调用，也没有一串中间实例化。

## 四种形式（¶2–¶3）

¶2 只有一个操作数的叫**一元折叠**（[[g:unary-fold|unary fold]]）：`(... op e)` 是一元左折叠，`(e op ...)` 是一元右折叠。操作数 `e` 必须含有未展开的包。

¶3 形如 `(e1 op1 ... op2 e2)` 的叫**二元折叠**（[[g:binary-fold|binary fold]]）。两个运算符必须相同，`e1` 和 `e2` 中恰好有一个含未展开的包，另一个是初值。包在右边（`e2`）时是二元左折叠，包在左边（`e1`）时是二元右折叠。

[[temp.variadic#15]] 规定了它们展开成什么。设包的元素为 E₁ … Eₙ，初值为 I：

| 写法 | 名称 | 展开为 |
|---|---|---|
| `(... op E)` | 一元左折叠 | `((E₁ op E₂) op …) op Eₙ` |
| `(E op ...)` | 一元右折叠 | `E₁ op (… op (Eₙ₋₁ op Eₙ))` |
| `(I op ... op E)` | 二元左折叠 | `((I op E₁) op …) op Eₙ` |
| `(E op ... op I)` | 二元右折叠 | `E₁ op (… op (Eₙ op I))` |

左折叠从左往右结合，右折叠从右往左结合。初值总是在最内层。

对整数的 `+`、`&&`、`||` 这类满足结合律的运算，方向不影响结果；对 `-`、`/`、`<<`、`=`，方向就决定了结果：

```cpp run ok
#include <cstdio>

template<class... A> int lsub(A... a) { return (... - a); }
template<class... A> int rsub(A... a) { return (a - ...); }

int main() {
  std::printf("%d %d\n", lsub(10, 3, 2),   // (10 - 3) - 2 = 5
                         rsub(10, 3, 2));  // 10 - (3 - 2) = 9
}
```

二元左折叠最常见的用途是流式输出，初值就是流对象：

```cpp run ok
#include <iostream>

template<class... Args> void print(Args&&... args) {
  (std::cout << ... << args) << '\n';   // ((cout << a1) << a2) << a3
}

int main() { print(1, "a", 2.5); }      // 输出 1a2.5
```

这里只能用左折叠。写成右折叠 `(args << ... << std::cout)`，最内层就成了 `aₙ << std::cout`，对 `int` 来说是在对一个流做移位，编译不过。

下面是标准例 1 的两个错误，再加上运算符不一致的情形：

```cpp error
template<class... Args> bool f(Args... args) {
  return (true && ... && args);   // OK：二元左折叠，初值 true
}
template<class... Args> auto g(Args... args) {
  return (args + ... + args);     // error: 两边都含未展开的包
}
template<class... Args> auto h(Args... args) {
  return (args + ... * 1);        // error: 两个运算符必须相同
}
```

## 语法限制（¶1）

¶1 给出折叠表达式的文法。允许的 *fold-operator* 共 32 个：

```text
+   -   *   /   %   ^   &   |   <<   >>
+=  -=  *=  /=  %=  ^=  &=  |=  <<=  >>=  =
==  !=  <   >   <=  >=  &&  ||  ,    .*   ->*
```

三路比较 `<=>` 不在其中，`?:`、`[]`、`()`、`.`、`->` 本来就不是普通的二元运算符，也不在其中。

文法还有两点要注意。第一，外层括号是折叠表达式自身的一部分，`return ... + args;` 不是合法的表达式。第二，操作数是 *cast-expression*，也就是强制转换表达式这一优先级及以上的表达式。一元运算（`-a`、`!a`、`*a`）、后缀运算（`a.size()`、`f(a)`）和强制转换（`(void)a`）都可以直接写；`a * 2`、`a ? 1 : 0` 这样优先级更低的表达式必须加括号。

```cpp error
template<class... A> auto k(A... a) { return (... + a * 2); }     // error: a * 2 不是 cast-expression
template<class... A> auto q(A... a) { return (... + (a * 2)); }   // OK：加了括号
template<class... A> auto p(A... a) { return (... + -a); }        // OK：一元表达式
```

这条限制是为了消除歧义：`(a * 2 + ...)` 既可以读成以 `+` 折叠 `a * 2`，也可以读成以 `*` 折叠，标准干脆要求写清楚。

## 空包与单元素包

二元折叠遇到空包时，结果就是初值 I。

一元折叠遇到空包时没有初值可用。[[temp.variadic#15]] 的表 20 只给三个运算符规定了空包时的值，其余运算符一律非良构：

| 运算符 | 空包时的值 |
|---|---|
| `&&` | `true` |
| `\|\|` | `false` |
| `,` | `void()` |

这三个值不依赖元素的类型。`+` 和 `*` 则不同：`int` 的单位元是 `0`，`std::string` 的是 `""`，矩阵的是零矩阵，标准无从选择。需要支持空包时，就用二元折叠给出初值。

```cpp run ok
#include <cstdio>
#include <type_traits>

template<class... A> bool all(A... a)  { return (... && a); }    // 空包：true
template<class... A> bool any(A... a)  { return (... || a); }    // 空包：false
template<class... A> int  sum0(A... a) { return (0 + ... + a); } // 空包：0
template<class... A> auto comma(A... a) { return (a, ...); }     // 空包：void()

int main() {
  std::printf("%d %d %d\n", all(), any(), sum0());   // 1 0 0
  static_assert(std::is_same_v<decltype(comma()), void>);
}
```

```cpp error
template<class... A> auto sum(A... a) { return (... + a); }
int x = sum();   // error: + 没有空包值
```

这个错误只在模板真的以空包实例化时才出现，所以往往要等某个调用者传了零个实参才暴露。

!!! history "空包值的取舍"
    最初的提案 [[N4295]] 也给 `+`、`*`、`&`、`|` 规定了空包值（`0`、`1`、`-1`、`0`）。这样一来，对 `std::string` 的空包求和会悄悄得到 `int` 类型的 `0`。C++17 发布前，[[P0036R0]] 删去了这四个，只保留 `&&`、`||` 和逗号。

包只有一个元素时，一元折叠展开后只剩这个元素本身，运算符根本不出现。所以 `(... && a)` 只有在元素个数不是 1 时才保证是 `bool`：

```cpp run ok
#include <type_traits>

template<class... A> auto f(A... a) { return (... && a); }

static_assert(std::is_same_v<decltype(f()), bool>);         // 空包：true
static_assert(std::is_same_v<decltype(f(5)), int>);         // 单元素：就是 5
static_assert(std::is_same_v<decltype(f(5, 6)), bool>);     // 5 && 6

int main() {}
```

要让结果总是 `bool`，写二元折叠 `(true && ... && a)`。

## 对每个元素做同一件事：逗号折叠

`(f(args), ...)` 依次对每个元素调用 `f`。内置逗号运算符保证从左到右求值（[[expr.comma]]），所以顺序是确定的。

```cpp run ok
#include <cstdio>
#include <vector>

template<class T, class... A> void push_all(std::vector<T>& v, A&&... a) {
  (v.push_back(a), ...);
}

int main() {
  std::vector<int> v;
  push_all(v, 1, 2, 3);
  std::printf("%zu\n", v.size());   // 3
}
```

如果 `f(args)` 返回的类型重载了 `operator,`，折叠就会调用那个重载。泛型代码里的防御写法是 `((void)f(args), ...)`：`void` 类型的操作数只能用内置逗号。

`&&` 和 `||` 折叠保留短路语义：`(... && check(args))` 遇到第一个 `false` 就不再求值后面的元素。

## 折叠表达式是包展开（¶4）

¶4 折叠表达式是一个**包展开**（[[g:pack-expansion|pack expansion]]）。所以它只能出现在有包的地方，也就是模板里；它所含的包由它自己展开，外层不能再对它写 `...`；它的实例化规则和其他包展开一起写在 [[temp.variadic]]。

在 *requires-clause* 和概念定义里，`(C<T> && ...)` 这样的折叠表达式可以组合约束。C++26 起，`&&` 和 `||` 折叠会规范化为**折叠展开约束**（[[g:fold-expanded-constraint|fold expanded constraint]]，[[temp.constr.fold]]），因而能参与约束之间的包含比较：`(D<T> && ...)` 可以比 `(C<T> && ...)` 更受约束（`D` 包含 `C` 时）。C++26 之前，整个折叠只算一个原子约束，无法这样比较。{{c++26}}

## 常见错误

!!! pitfall "非结合运算写反方向"
    `(args = ... = 0)` 是二元右折叠，展开为 `a1 = (a2 = (a3 = 0))`，把每个元素都赋为 0。写成左折叠 `(0 = ... = args)` 就成了 `(0 = a1) = a2`，非良构。

!!! pitfall "以为空包会得到 0"
    `(... + args)` 对空包非良构，不是 0。需要零个元素也能工作时，写 `(0 + ... + args)`。

## 思考题

!!! question "思考题"
    `(std::cout << ... << args)` 是左折叠还是右折叠？`(args << ... << std::cout)` 呢？

<details markdown="1">
<summary>答案</summary>

前者的包在右边，是二元左折叠，初值 `std::cout` 在最内层：`((cout << a1) << a2) << …`。后者的包在左边，是二元右折叠：`a1 << (a2 << (… << (aₙ << cout)))`。它从最内层起就要求 `aₙ << std::cout` 有意义，对算术类型的元素这通常非良构，或者调到意料之外的重载（¶3、[[temp.variadic#15]]）。
</details>
