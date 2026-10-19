---
title: 显然常量求值与常量析构
summary: 哪些表达式必须在翻译期求值（std::is_constant_evaluated() 观察的正是这一点）；哪些表达式会触发 constexpr 函数的实例化；constexpr 变量的析构为什么也要能在编译期完成。
status: done
papers: P0595R2, P1938R3, P0784R7
related: expr.const.init, expr.const.imm, meta.const.eval, stmt.if, temp.inst, dcl.constexpr, basic.start.static, topics/compile-time-programming
tags: 常量求值, is_constant_evaluated, 实例化
updated: 2026-10-19
---

!!! tldr
    - 显然常量求值的表达式是语言要求在翻译期求值的那些：数组边界、模板实参、`if constexpr` 的条件、consteval 块、立即调用、约束检查，以及常量初始化的变量的初始化器。
    - `std::is_constant_evaluated()` 和 `if consteval` 观察的就是这个属性，而不是代码实际在编译期还是运行期执行。
    - 一个变量是否常量初始化，靠试算它的初始化器来判断，试算时 `is_constant_evaluated()` 为真。试算失败的变量在运行期初始化，这时它又为假，同一个初始化器会选中另一个分支。
    - 潜在常量求值的表达式所命名的 constexpr 函数会被实例化，即使它没有被 odr 使用。花括号初始化里的表达式属于这一类，因为要判断是否窄化。
    - constexpr 变量必须具有常量析构：销毁它的过程本身要能作为常量表达式求值。

## 显然常量求值（¶1）

### 哪些表达式必须在编译期求值

有些表达式的值决定了程序的结构，例如数组的长度、模板实参，编译器必须在翻译期求出它们。¶1 把这类表达式或转换称为**显然常量求值**的（[[g:manifestly-constant-evaluated|manifestly constant-evaluated]]）：

| 条目 | 情形 | 例子 |
|---|---|---|
| ¶1.1 | 语法上的 *constant-expression* | 数组边界、`case` 标签、模板实参、`static_assert` 条件、`alignas`、位域宽度、枚举量初值、`noexcept(…)` |
| ¶1.2 | constexpr if 语句的条件 | `if constexpr (cond)` |
| ¶1.3 | consteval 块对应的表达式 {{c++26}} | `consteval { … }` |
| ¶1.4 | 立即调用 | 在立即函数语境之外调用 consteval 函数（[[expr.const.imm]]） |
| ¶1.5 | 为判断原子约束是否满足而代入的结果 | `requires (sizeof(T) > 4)` |
| ¶1.6 | 可用于常量表达式、或具有常量初始化的变量的初始化器 | `constexpr int x = …;`、`constinit` 变量、成功常量初始化的 `const int n = …;` 和静态变量 |

前五项都由语法位置决定，一看便知。¶1.6 不一样：初始化器是否显然常量求值，取决于变量是否常量初始化（[[basic.start.static]]），而这又取决于初始化器能否作为常量表达式求值，形成了一个循环。

标准用一次概念上的试算打破这个循环（脚注 63、[[expr.const.init#4]]）。判断时先把初始化器当作常量表达式试算，试算中 `std::is_constant_evaluated()` 为真，契约断言按 ignore 语义处理。试算成功，变量就是常量初始化的，初始化器显然常量求值；试算失败，变量在运行期动态初始化，这时 `is_constant_evaluated()` 为假。

### 标准例子

```cpp run title="mce.cpp" ok
#include <cstdio>
#include <type_traits>
template<bool> struct X {};
X<std::is_constant_evaluated()> x;   // 模板实参（¶1.1）：类型是 X<true>

int y;
const int a = std::is_constant_evaluated() ? y : 1;  // 动态初始化为 1
const int b = std::is_constant_evaluated() ? 2 : y;  // 静态初始化为 2
int c = y + (std::is_constant_evaluated() ? 2 : y);  // 动态初始化为 y + y

constexpr int f() {
  const int n = std::is_constant_evaluated() ? 13 : 17;  // n 是 13
  int m = std::is_constant_evaluated() ? 13 : 17;        // 13 或 17
  char arr[n] = {};                                      // char[13]
  return m + sizeof(arr);
}
int p = f();       // 这次调用中 m 是 13：p == 26
int q = p + f();   // 这次调用中 m 是 17：q == 56

int main() { std::printf("%d %d %d %d\n", a, b, p, q); }   // 1 2 26 56
```

逐个看：

- `a`：试算时选中 `y`，读取非常量 `y` 失败，所以 `a` 动态初始化。运行时 `is_constant_evaluated()` 为假，选中 `1`。`a` 的值是 1，但它不是常量初始化的，不能用于常量表达式。
- `b`：试算选中 `2`，成功，静态初始化为 2。
- `c`：不论选哪个分支都要读 `y`，试算失败，运行时得到 `y + y`。`c` 不是 `const`，但它是静态存储期变量，¶1.6 的具有常量初始化同样适用，所以也要试算。
- `n`：`const int` 变量如果常量初始化就可以用于常量表达式，所以它的初始化器显然常量求值。即使 `f()` 在运行期调用，`n` 也是 13，`char arr[n]` 因此合法。
- `m`：不是 `const`，初始化器不是显然常量求值的，`is_constant_evaluated()` 的值取决于外层的 `f()` 是否正在常量求值。`int p = f();` 试算成功，所以 `p` 静态初始化为 26。`int q = p + f();` 读取了非 const 的 `p`，试算失败，运行时调用 `f()`，`m` 是 17，`q` 为 56。

本机 Clang 23 运行结果与标准例子一致。

<div class="compare" markdown="1">

```cpp run ok
#include <type_traits>
int y;
const int b =
  std::is_constant_evaluated() ? 2 : y;
static_assert(b == 2);   // OK
```

```cpp run error
#include <type_traits>
int y;
const int a =
  std::is_constant_evaluated() ? y : 1;
static_assert(a == 1);   // error
```

</div>

标准例子里用的是 `double z[a];`。本机 Clang 23 不加 `-pedantic-errors` 时只给警告，把它当作变长数组扩展再折叠成定长数组，所以这里换成 `static_assert` 演示。

!!! warning "Clang 的 `-Wconstant-evaluated` 并不总是对的"
    Clang 对 `X<…>`、`a`、`b`、`n` 这几行都警告 "'std::is_constant_evaluated' will always evaluate to 'true' in a manifestly constant-evaluated expression"。对 `a` 这是错的：`a` 最终在运行期初始化为 1。这条警告的用处是提示这种写法多半不是你想要的。

### 未求值操作数里也会求值

¶1 的注 1：除了 `static_assert` 的消息，显然常量求值的表达式即使出现在未求值操作数中也会被求值（[[expr.context]]）。

```cpp run error
template<class T> constexpr int f() { return T::value; }
constexpr int g() { return sizeof(char[f<int>()]); }  // error: int::value 不存在
```

`sizeof` 的操作数不求值，但数组边界是 *constant-expression*，必须求出值才能确定类型 `char[N]`，于是 `f<int>` 被实例化并求值。`static_assert` 的消息之所以例外，是因为 C++26 允许用户生成的消息（[[dcl.pre#13]]），它只在断言失败时才需要求值。

### 为什么 is_constant_evaluated 是这样设计的

C++20 引入 `std::is_constant_evaluated()`（[[P0595R2]]）时，更直观的语义是告诉你代码此刻是否在编译期执行。但这无法规定：优化器可以把任何运行期计算折叠成常量，是否在编译期执行会随优化级别变化。所以它观察的是一个由语言确定的属性：当前求值是否是显然常量求值，或者位于这样的求值之中。代价就是上面那些反直觉的情形。

C++23 的 `if consteval`（[[P1938R3]]）观察的是同一个属性，并且第一个分支是立即函数语境（[[expr.const.imm]]）。现在 `is_constant_evaluated()` 的规格就是 `if consteval { return true; } else { return false; }`（[[meta.const.eval#1]]）。

!!! pitfall "`is_constant_evaluated()` 的三种误用"
    1. `if constexpr (std::is_constant_evaluated())`：条件显然常量求值（¶1.2），永远为真。
    2. `constexpr bool b = std::is_constant_evaluated();`：初始化器显然常量求值，结果永远为真，不提供任何信息。
    3. `const int a = std::is_constant_evaluated() ? runtime() : 1;`：试算失败后在运行期得到 1，而不是 `runtime()` 的结果。

    `is_constant_evaluated()` 适合写在 constexpr 函数体内，在同一算法的编译期实现和运行期实现之间切换，两个分支应当算出相同的结果。

## 潜在常量求值与为常量求值所需（¶2）

这两个定义决定 constexpr 函数什么时候被实例化。先看一组对比：

<div class="compare" markdown="1">

```cpp run ok
template<class T>
constexpr int f() { return T::value; }

// 未求值操作数：不实例化 f<int>
decltype(f<int>()) x = 0;
```

```cpp run error
template<class T>
constexpr int f() { return T::value; }

// 要判断 int → char 是否窄化
using A = decltype(char{f<int>()});
// error: 实例化 f<int> 失败
```

</div>

两边的 `f<int>()` 都在 `decltype` 里，都没有被 odr 使用。右边的不同在于它是花括号列表的直接子表达式。列表初始化中 `int` 到 `char` 是否窄化，要看源值是不是能表示的常量（[[dcl.init.list]]），所以编译器必须实例化 `f<int>` 并尝试求值。

¶2 一个表达式或转换如果是下面之一，就是**潜在常量求值**的（potentially constant-evaluated）：

- ¶2.1 显然常量求值的表达式；
- ¶2.2 潜在求值的表达式（[[basic.def.odr]]）；
- ¶2.3 *braced-init-list* 的直接子表达式（脚注 64：有时需要常量求值才能判断是否窄化）；
- ¶2.4 出现在模板化实体中、形如 `& cast-expression` 的表达式（脚注 65：有时需要常量求值才能判断它是否值依赖，见 [[temp.dep.constexpr]]）；
- ¶2.5 上面任一者的潜在求值子表达式。

一个函数或变量如果是下面之一，就是**为常量求值所需**的（[[g:needed-for-constant-evaluation|needed for constant evaluation]]）：

- ¶2.6 被潜在常量求值的表达式命名的 constexpr 函数；
- ¶2.7 被潜在常量求值的表达式命名的潜在常量变量（[[expr.const.init#6]]：constexpr 变量，或引用、const 整型、const 枚举类型的变量）。

[[temp.inst]] 用这组定义规定：为常量求值所需的 constexpr 函数模板特化会被隐式实例化，即使它没有被 odr 使用；预置的特殊成员函数和变量模板也按同样的条件隐式定义或实例化。

实例化不是无关紧要的实现细节。它可能触发硬错误（如上例），可能实例化更多模板，借助友元注入一类技巧甚至能改变后续代码的含义。所以标准必须精确规定哪些表达式会引起实例化，单靠 odr 使用不够。

## 常量析构（¶3）

constexpr 变量的析构也要能在编译期完成。¶3 对象 a 在下面两种情况下具有**常量析构**（[[g:constant-destruction|constant destruction]]）：

- ¶3.1 它不是类类型，也不是类类型的（多维）数组；
- ¶3.2 它是类类型或其（多维）数组，这个类有 constexpr 析构函数，并且设想一个唯一作用是销毁 a 的表达式 E，如果把 a 及其非 mutable 子对象的生命期视为在 E 之内开始，E 是核心常量表达式。

[[dcl.constexpr#6]] 要求 constexpr 变量，以及 constexpr 引用所绑定的临时对象，都具有常量析构。

```cpp
int g;
struct T { int* p; constexpr ~T() { *p = 0; } };
constexpr T t{&g};    // error: 析构修改了 g，g 的生命期不在 E 之内开始

struct T2 { int v; constexpr ~T2() { v = 0; } };
constexpr T2 t2{1};   // OK：只修改自己的非 mutable 成员

struct M { mutable int v; constexpr ~M() { v = 0; } };
constexpr M m{1};     // error: mutable 成员不视为在 E 之内开始

struct ND { int v; ~ND() {} };
constexpr ND nd{1};   // error: 析构函数不是 constexpr，ND 不是字面类型
```

C++20 允许 constexpr 析构函数（[[P0784R7]]）之后，析构函数可以做任何 constexpr 允许的事。如果它修改外部对象，编译期就无法模拟。¶3.2 把 a 的生命期视为在 E 之内开始，于是析构函数可以修改 a 自己的成员，毕竟 a 正在被销毁。

mutable 成员是例外。constexpr 对象的 mutable 成员在运行期可以被修改，编译器在翻译期不知道析构时它的值，所以析构函数只要读写它，对象就不具有常量析构。本机 Clang 23 对只读取 mutable 成员的析构函数同样报 "must have constant destruction"。

常量析构也挡住了跨越编译期和运行期的动态内存：

```cpp
struct Owner {
  int* p;
  constexpr Owner() : p(new int(1)) {}
  constexpr ~Owner() { delete p; }
};
constexpr int use() { return *Owner().p; }  // OK：同一次求值中分配并释放
static_assert(use() == 1);
constexpr Owner o;   // error: 分配的内存没有在初始化的求值中释放
```

`o` 在更早一步就失败了：它的初始化器分配的内存没有在这次求值中释放，不是常量表达式（[[expr.const.core#2.20]]）。

!!! note "常量析构与程序结束"
    具有常量析构的静态存储期对象，析构排在其他所有静态对象和 `atexit` 注册的函数之后，不参与普通的析构顺序规则（[[basic.start.term#3]]）。它的析构没有可观察的效果，所以编译器可以干脆不注册析构：本机 Clang 23 即使在 `-O0` 下也没有为上面的 `t2` 生成 `__cxa_atexit` 调用。`constinit` 变量配合平凡析构或常量析构，可以完全避开静态析构顺序问题。

## 历史与演进

!!! history
    - C++11–17 只有常量表达式的语法上下文，没有 `is_constant_evaluated`，也就不需要精确定义显然常量求值。实例化时机由 odr 使用和少数特例决定。
    - C++20：[[P0595R2]] 引入 `std::is_constant_evaluated()` 和显然常量求值；[[P0784R7]] 允许 constexpr 析构函数，同时引入常量析构。潜在常量求值和为常量求值所需也在这一时期定型，用来规定实例化。
    - C++23：[[P1938R3]] 引入 `if consteval`。
    - C++26：加入 consteval 块（¶1.3）；试算常量初始化时忽略契约断言。

## 思考题

!!! question "思考题 1"
    下面三个变量的值各是多少？静态初始化还是动态初始化？

    ```cpp
    #include <type_traits>
    constexpr int pick() { return std::is_constant_evaluated() ? 1 : 2; }
    int rt = 0;
    int u = pick();
    int v = pick() + rt;
    const int w = pick() + 0 * rt;
    ```

<details markdown="1">
<summary>答案</summary>

- `u`：试算 `pick()` 成功，得 1，静态初始化，`u == 1`。
- `v`：试算时读取 `rt` 失败，动态初始化，运行时 `pick()` 返回 2，`v == 2`。
- `w`：`0 * rt` 仍要读取 `rt`，试算失败，动态初始化，`w == 2`，而且 `w` 不能用于常量表达式。

初始化器里任何一处非常量读取都会让整个初始化变成动态的，从而改变 `is_constant_evaluated()` 的结果。本机 Clang 23 运行输出 `1 2 2`。
</details>

!!! question "思考题 2"
    为什么常量析构的定义里，mutable 子对象的生命期不视为在 E 之内开始？

<details markdown="1">
<summary>答案</summary>

constexpr 对象的 mutable 成员不是常量，程序可以在运行期通过 const 引用修改它，这正是 mutable 的用途。编译器在翻译期模拟析构时，不知道运行期结束时 mutable 成员的值，如果允许析构函数读写它，编译期模拟的析构就可能和真实的析构不一致。所以标准把 mutable 子对象当作外部对象：析构函数读写它，对象就不具有常量析构。
</details>
