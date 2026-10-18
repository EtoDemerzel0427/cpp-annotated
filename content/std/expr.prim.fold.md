---
title: 折叠表达式
summary: 用一个二元运算符把整个包组合成一个表达式：四种形式、结合方向、空包规则（只有 &&、||、逗号有单位元）、对操作数形式的限制。
status: draft
since: c++17
papers: N4295, P0036R0
related: temp.variadic, expr.prim, temp.constr.fold, expr.comma
tags: 包展开, 可变参数模板, 表达式
updated: 2026-10-17
---

**折叠表达式**（fold expression）在 C++17 引入，用于把一个包中的所有元素用同一个二元运算符组合起来：`(... + args)` 得到 `args₁ + args₂ + … + argsₙ`。在此之前，对包求和、逐个打印、逐个 `push_back`，都必须写递归模板，或者借助初始化列表加逗号运算符的技巧（`int dummy[] = { (f(args), 0)... };`）。

本节只规定语法和分类；折叠表达式实例化之后是什么样子、空包时的值是什么，写在 [[temp.variadic#15]] 中。两处要一起读。

## 文法（¶1）

¶1 折叠表达式对一个包（[[temp.variadic]]）在一个二元运算符上执行折叠：

```text
fold-expression:
    ( cast-expression fold-operator ... )
    ( ... fold-operator cast-expression )
    ( cast-expression fold-operator ... fold-operator cast-expression )
```

*fold-operator* 是以下 32 个二元运算符之一：

```text
+   -   *   /   %   ^   &   |   <<   >>
+=  -=  *=  /=  %=  ^=  &=  |=  <<=  >>=  =
==  !=  <   >   <=  >=  &&  ||  ,    .*   ->*
```

不在列表中的：`<=>`（三路比较）、`[]`、`()`、`?:`、`->` 和 `.`（它们都不是普通二元运算符）。

文法上有几个要点：

1. 括号是语法的一部分。`... + args` 不是表达式；`return (... + args);` 中外层的括号就是折叠表达式自己的括号。
2. 操作数是 *cast-expression*，不是任意表达式。因此优先级低于强制转换的二元运算（`*`、`+`、`<<`、比较、`&&` 等）以及三元、赋值、逗号，都不能直接出现在操作数中，必须加括号。这是为了消除歧义，例如 `args * 2 + ...` 究竟是 `(args * 2) + ...` 还是 `args * (2 + ...)`，标准干脆要求写清楚。
3. 一元运算（`-args`、`!args`、`*args`、`&args`）、后缀运算（`args.size()`、`args[0]`、`f(args)`）、强制转换（`(void)args`）都是 *cast-expression*，可以直接用。

```cpp
template<class... A> auto k(A... a) { return (... + a * 2); }     // error: a * 2 不是 cast-expression
template<class... A> auto q(A... a) { return (... + (a * 2)); }   // OK：加括号
template<class... A> auto p(A... a) { return (... + -a); }        // OK：一元表达式是 cast-expression
template<class... A> auto r(A... a) { return (a ? 1 : 0 + ...); } // error: 条件表达式不是 cast-expression
```

## 一元折叠（¶2）

¶2 定义：

- `(... op e)`：**一元左折叠**（unary left fold）；
- `(e op ...)`：**一元右折叠**（unary right fold）；

二者统称[[g:unary-fold|一元折叠]]。在一元折叠中，*cast-expression* 必须包含一个未展开的包。

左和右指的是结合方向：`...` 在哪边，括号就往哪边堆（[[temp.variadic#15]]）：

| 形式 | 展开为 |
|---|---|
| `(... op E)` 左折叠 | `((E₁ op E₂) op …) op Eₙ` |
| `(E op ...)` 右折叠 | `E₁ op (… op (Eₙ₋₁ op Eₙ))` |

对于满足结合律的运算（整数的 `+`、`&&`、`||`、`,`），方向无关紧要；但 `-`、`/`、`<<`、`=` 等运算的结果就完全不同：

```cpp run ok
#include <cstdio>

template<class... A> int lsub(A... a) { return (... - a); }   // ((10 - 3) - 2) = 5
template<class... A> int rsub(A... a) { return (a - ...); }   // 10 - (3 - 2) = 9

int main() { std::printf("%d %d\n", lsub(10, 3, 2), rsub(10, 3, 2)); }
```

## 二元折叠（¶3）

¶3 形如 `(e1 op1 ... op2 e2)` 的是[[g:binary-fold|**二元折叠**]]。它要求：

- `op1` 与 `op2` 必须是同一个运算符；
- `e1` 和 `e2` 中恰好有一个包含未展开的包。

如果 `e2` 含包，就是二元左折叠（初值在左边：`(init op ... op pack)`）；如果 `e1` 含包，就是二元右折叠（初值在右边：`(pack op ... op init)`）。

| 形式 | 展开为 |
|---|---|
| `(I op ... op E)` 二元左折叠 | `(((I op E₁) op E₂) op …) op Eₙ` |
| `(E op ... op I)` 二元右折叠 | `E₁ op (… op (Eₙ op I))` |

可以这样记：初值 `I` 总是在展开的最内层，`...` 总是指向包展开的方向。

```cpp
template<typename ...Args>
bool f(Args ...args) {
  return (true && ... && args);   // OK：二元左折叠，初值 true
}

template<typename ...Args>
bool g(Args ...args) {
  return (args + ... + args);     // error: 两个操作数都含有未展开的包
}

template<typename ...Args>
auto h(Args ...args) {
  return (args + ... * 1);        // error: 两个运算符必须相同
}
```

二元左折叠最典型的用法是流式输出，初值就是流对象：

```cpp run ok
#include <iostream>

template<class... Args> void print(Args&&... args) {
  (std::cout << ... << args) << '\n';     // ((cout << a1) << a2) << a3
}

int main() { print(1, "a", 2.5); }       // 输出 1a2.5
```

注意这里必须用左折叠：`<<` 是左结合的，`cout << a1` 返回流，再接着 `<< a2`。如果写成右折叠 `(args << ... << std::cout)`，就成了 `a1 << (a2 << (a3 << cout))`，毫无意义。

## 折叠表达式是包展开（¶4）

¶4 折叠表达式是一个包展开。这意味着：

- 它只能出现在模板中（包只存在于模板里）；
- 其中的包被视为已展开，不会再被外层的 `...` 展开；
- 它的实例化规则在 [[temp.variadic#15]] 中，与其他包展开放在一起。

## 空包（[temp.variadic] ¶15 与表 20）

二元折叠遇到空包时，结果就是初值 `I`（展开式中没有任何 `Eᵢ`）。

一元折叠遇到空包时就麻烦了：`args` 为空时，`(... + args)` 该是什么？`0`？如果 `args` 是字符串呢？标准的回答是，只有三个运算符定义了空包值，其余一律非良构：

| 运算符 | 空包时的值 |
|---|---|
| `&&` | `true` |
| `\|\|` | `false` |
| `,` | `void()` |

这三个值是各自运算的单位元，且与操作数类型无关（`&&`/`||` 的结果总是 `bool`；逗号的结果可以丢弃）。而 `+` 的单位元依赖于类型（`int` 是 `0`，`std::string` 是 `""`，矩阵是零矩阵，等等），`*` 同理，标准无从选择。所以对这些运算符，**需要处理空包时，应当使用二元折叠并显式给出初值**。

!!! history "C++17 发布前的修改"
    最初的折叠表达式提案（[[N4295]]）为 `+`、`*`、`&`、`|` 也规定了空包值（`0`、`1`、`-1`、`0`）。这在泛型代码中会悄悄给出类型错误的结果（例如对 `std::string` 求和得到 `int` 0），因此在 C++17 发布前被 [[P0036R0]] 删去，只保留了 `&&`、`||`、`,`。

```cpp run ok
#include <cstdio>
#include <type_traits>

template<class... A> bool all(A... a)        { return (... && a); }   // 空包 → true
template<class... A> bool any(A... a)        { return (... || a); }   // 空包 → false
template<class... A> auto sum0(A... a)       { return (0 + ... + a); } // 二元折叠：空包 → 0
template<class... A> auto comma(A... a)      { return (a, ...); }      // 空包 → void()

template<class... Ts> constexpr bool any_ptr = (std::is_pointer_v<Ts> || ...);

int main() {
  std::printf("%d %d %d\n", all(), any(), sum0());   // 1 0 0
  comma();
  static_assert(std::is_same_v<decltype(comma()), void>);
  static_assert(!any_ptr<> && any_ptr<int, int*>);
}
```

```cpp error
template<class... A> auto sum(A... a) { return (... + a); }
int x = sum();   // error: 一元 + 折叠遇到空包，且 + 没有空包值
```

!!! pitfall "单元素包"
    当包只有一个元素时，一元折叠的结果就是那个元素本身（`(... + a)` → `(a₁)`），运算符根本不会出现。所以当 `args` 只有一个 `int` 时，`(... && args)` 的结果是 `int` 而不是 `bool`。如果需要统一的结果类型，可以用二元折叠（`(true && ... && args)`），或者对结果做显式转换。

## 用逗号折叠对每个元素做同一件事

逗号折叠是最常用的一种：`(f(args), ...)` 依次对每个元素调用 `f`。内置逗号运算符保证从左到右求值（[[expr.comma]]），所以顺序是确定的。

```cpp run ok
#include <cstdio>
#include <vector>

template<class T, class... A> void push_all(std::vector<T>& v, A&&... a) {
  (v.push_back(a), ...);                         // 右折叠：v.push_back(a1), (v.push_back(a2), ...)
}
template<class... A> void print_each(A... a) {
  ((std::printf("%d ", a)), ...);
  std::printf("\n");
}

int main() {
  std::vector<int> v;
  push_all(v, 1, 2, 3);
  print_each(1, 2, 3);                           // 1 2 3
  std::printf("%zu\n", v.size());                // 3
}
```

!!! pitfall "重载的逗号运算符"
    如果 `f(args)` 返回一个重载了 `operator,` 的类类型，`(f(args), ...)` 就会调用那个重载，求值顺序与结果都可能出乎意料（C++17 起重载的逗号运算符也保证从左到右求值，但其返回值和副作用仍由用户定义）。泛型代码中的防御写法是 `((void)f(args), ...)`：转换为 `void` 之后只能使用内置逗号。

!!! tip "折叠表达式里的短路"
    `&&` 与 `||` 折叠保留短路语义：`(... && check(args))` 一旦遇到 `false`，就不再求值后面的元素。这常用于依次尝试、直到成功的逻辑。

## 与约束的关系 {{c++26}}

在 *requires-clause* 和概念定义中，折叠表达式可以组合约束：`template<class... T> requires (C<T> && ...)`。C++26 之前，这样的折叠表达式只算一个原子约束，因此无法比较 `(C<T> && ...)` 与 `(D<T> && ...)`（`D` 包含 `C`）谁更受约束。C++26 引入了**折叠展开约束**（fold expanded constraint，[[temp.constr.fold]]），让 `&&`/`||` 折叠参与约束的包含（subsumption）判断。[[temp.variadic#16]] 说明折叠展开约束不会被实例化。

## 实现视角

!!! impl
    - 折叠表达式在实例化时直接展开为嵌套的二元表达式树，和手写完全相同，不引入任何函数调用或递归实例化，因此比递归模板编译得快得多。
    - 包很大时（数千个元素），左折叠和右折叠会生成同样深的表达式树；某些编译器处理极深的嵌套表达式时可能触及递归深度限制（Clang 用 `-fbracket-depth` 选项控制括号嵌套深度）。
    - Clang 的诊断会明确区分几种错误：空包且没有回退值（对应表 20）、两边都有未展开的包（¶3）、运算符不同（¶3），以及操作数不是 cast-expression（¶1 文法）。

## 陷阱

!!! pitfall "左右写反"
    使用非结合运算（`-`、`/`、`<<`、`>>`、赋值）时一定要想清楚方向。`(args = ... = 0)` 是右折叠：`a1 = (a2 = (a3 = 0))`，把所有元素赋为 0；写成左折叠 `(0 = ... = args)` 则是 `((0 = a1) = a2)`，非良构。

!!! pitfall "以为空包会是 0"
    空包时，`(... + args)` 不会得到 0，而是非良构。只有模板实际以空包实例化时才会报错，所以这种 bug 常常要等到某个调用者传入空包才暴露出来。

## 思考题

!!! question "思考题 1"
    下面的函数调用 `f()`（空包）与 `f(5)` 分别返回什么类型？
    ```cpp
    template<class... A> auto f(A... a) { return (... && a); }
    ```

<details markdown="1">
<summary>答案</summary>

`f()` 是空包，按表 20 结果是 `true`，返回 `bool`。`f(5)` 是单元素包，展开为 `(5)`，其中不出现 `&&`，所以返回 `int`，值为 5。只有两个及以上元素时，结果才是 `bool`。如果要求结果恒为 `bool`，就写 `(true && ... && a)`。
</details>

!!! question "思考题 2"
    `(std::cout << ... << args)` 是左折叠还是右折叠？如果写成 `(args << ... << std::cout)` 会发生什么？

<details markdown="1">
<summary>答案</summary>

前者的 `e2`（`args`）含包，是二元左折叠，初值 `std::cout` 位于最内层：`((cout << a1) << a2) << …`。后者的 `e1` 含包，是二元右折叠：`a1 << (a2 << (… << (aₙ << cout)))`。它从最内层起就要求 `aₙ << std::cout` 有意义，对 `int` 而言这是对流对象做移位，通常非良构（或者调用到意外的重载）。
</details>

## 小结

!!! summary
    | 形式 | 名称 | 展开 | 空包 |
    |---|---|---|---|
    | `(... op E)` | 一元左折叠 | `((E₁ op E₂) op …) op Eₙ` | 仅 `&&`→`true`、`\|\|`→`false`、`,`→`void()`，其余非良构 |
    | `(E op ...)` | 一元右折叠 | `E₁ op (… op (Eₙ₋₁ op Eₙ))` | 同上 |
    | `(I op ... op E)` | 二元左折叠 | `((I op E₁) op …) op Eₙ` | `I` |
    | `(E op ... op I)` | 二元右折叠 | `E₁ op (… op (Eₙ op I))` | `I` |

    - 括号是语法的一部分；操作数必须是 *cast-expression*（否则加括号）。
    - 二元折叠的两个运算符必须相同，且恰好一侧含包。
    - 折叠表达式本身是包展开；实例化规则在 [[temp.variadic#15]]。
