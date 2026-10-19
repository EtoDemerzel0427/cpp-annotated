---
title: 立即函数
summary: consteval 函数的调用必须在编译期完成；什么是立即调用和立即函数语境，以及 constexpr 模板、lambda 和预置函数什么时候会自动升级为立即函数。
status: done
papers: P1073R3, P1938R3, P2564R3, P2216R3, P2996R13
related: dcl.constexpr, stmt.if, expr.const.const, expr.const.defns, meta.const.eval, topics/compile-time-programming
tags: 常量求值, consteval, if consteval
updated: 2026-10-19
---

!!! tldr
    - 用 `consteval` 声明的函数是立即函数。在立即函数语境之外调用它，这次调用就是立即调用，必须是常量表达式。
    - 立即函数语境有三处：立即函数的函数体内、显然常量求值的表达式内、`if consteval` 的第一个分支内。在这些地方调用 consteval 函数，实参可以不是常量。
    - C++23 起，constexpr 函数模板的特化、lambda 的调用运算符和编译器生成的预置函数，如果含有非常量的 consteval 调用，会自动升级为立即函数。手写的普通 constexpr 函数不会升级，这样写直接非良构。
    - 默认实参和默认成员初始化器里的 consteval 调用，算在使用它们的地方。
    - C++26 起，指向 consteval 函数的指针可以存进 constexpr 变量，但不能进入运行期对象。本机 Clang 23 尚未实现这一点。

## 只能在编译期调用的函数

```cpp
consteval int sq(int n) { return n * n; }

int x = sq(3);       // OK：编译期算出 9
int rt = 3;
int y = sq(rt);      // error: 调用不是常量表达式
```

`constexpr` 函数可以在编译期调用，也可以在运行期调用。`consteval` 函数只能在编译期调用。用 `consteval` 声明的函数叫做**立即函数**（[[g:immediate-function|immediate function]]）。

对立即函数的一次调用，如果不处在下一节讲的立即函数语境中，就叫做**立即调用**（[[g:immediate-invocation|immediate invocation]]）。立即调用是显然常量求值的（[[expr.const.defns#1]]），必须是常量表达式，结果在翻译期算出后直接嵌入程序。`sq(rt)` 读取了非常量 `rt`，所以不是常量表达式，程序非良构。

立即函数从来不在运行期执行，编译器也就不为它生成机器码，目标文件里没有它的符号。

### 为什么需要 consteval

C++20 引入 `consteval`（[[P1073R3]]），主要有两个用途。

第一是保证编译期求值。`constexpr` 不提供这个保证。有些函数的意义就在于编译期检查，例如校验格式字符串，运行期调用它们应当是编译错误。`std::format` 的格式串检查就是这样实现的：`std::basic_format_string` 的构造函数是 consteval 的，所以格式串在编译期解析（[[P2216R3]]，作为缺陷修复并入 C++20）。

```cpp run error
#include <format>
#include <string>
std::string a = std::format("{} + {}", 1, 2);  // OK
std::string b = std::format("{:d}", "str");    // error: d 不适用于字符串
```

第二是给纯编译期的工具函数一个归宿。C++26 的反射 API（`std::meta::*`）全部是 consteval 函数（[[P2996R13]]），因为反射值只在编译期有意义。

## 立即函数语境（¶1）

consteval 函数之间要能互相调用。下面的 `quad` 把自己的形参传给 `sq`，形参 `n` 不是常量，但这次调用是合法的：

```cpp run ok
consteval int sq(int n) { return n * n; }
consteval int quad(int n) { return sq(sq(n)); }  // OK
static_assert(quad(2) == 16);
int main() {}
```

¶1 一个潜在求值的表达式或转换，如果满足下面任一条件，就处于**立即函数语境**（[[g:immediate-function-context|immediate function context]]）：

- ¶1.1 它最内层的非块作用域是某个立即函数的形参作用域，也就是它写在立即函数的函数体里；
- ¶1.2 它是某个显然常量求值的表达式或转换的子表达式，例如 constexpr 变量的初始化器、模板实参、`static_assert` 的条件；
- ¶1.3 它所在的语句被一个 consteval if 语句（`if consteval { … }`）的复合语句包围。

在立即函数语境里调用立即函数，不算立即调用，自身不必是常量表达式。这是因为外层已经保证会在编译期求值：`quad` 只有在被立即调用时才执行，那时 `n` 已经有确定的值。常量性的检查推迟到最外层的那次立即调用。

## if consteval

¶1.3 对应的语句是 C++23 的 `if consteval`（[[P1938R3]]，规则见 [[stmt.if#4]]–[[stmt.if#6]]）。它在显然常量求值的语境中执行第一个分支，否则执行 `else` 分支。两个分支都必须是复合语句。

第一个分支是立即函数语境，所以可以把非常量实参传给 consteval 函数。`std::is_constant_evaluated()` 做不到这一点：

<div class="compare" markdown="1">

```cpp run error
#include <type_traits>
consteval int sq(int n) { return n*n; }

constexpr int bad(int n) {
  if (std::is_constant_evaluated())
    return sq(n);  // error
  return n * n;
}
```

```cpp run ok
consteval int sq(int n) { return n*n; }

constexpr int good(int n) {
  if consteval {
    return sq(n);  // OK
  } else {
    return n * n;
  }
}
```

</div>

在左边，`if` 的普通条件不建立任何语境，`sq(n)` 是一次立即调用，而 `n` 不是常量，编译器在定义处就报错。在右边，`sq(n)` 处在立即函数语境中，只是一次普通调用，在 `good` 被常量求值时随之求值。

`std::is_constant_evaluated()` 本身就是用 `if consteval` 规定的：它等价于 `if consteval { return true; } else { return false; }`（[[meta.const.eval#1]]）。

!!! pitfall "`if constexpr (std::is_constant_evaluated())` 永远为真"
    `if constexpr` 的条件是显然常量求值的，所以 `is_constant_evaluated()` 在那里总是返回 `true`，运行期分支被丢弃。Clang 用 `-Wconstant-evaluated` 警告这种写法。要区分编译期和运行期，用 `if consteval` 或普通的 `if (std::is_constant_evaluated())`。

## 立即升级（¶2–¶4）

### C++20 的问题：泛型代码无法转发 consteval 调用

```cpp
consteval int sq(int n) { return n * n; }

template<class T>
constexpr int tf(T n) { return sq(n); }
```

`tf<int>` 里的 `sq(n)` 不在立即函数语境中，`n` 又不是常量。按 C++20 最初的规则这是错误的。于是 `std::invoke`、ranges 算法这类 constexpr 转发模板都无法接收 consteval 可调用对象。C++23 的 [[P2564R3]]（作为缺陷修复，也适用于 C++20）的解决办法是：让 `tf<int>` 自动变成立即函数。

```cpp
consteval int sq(int n) { return n * n; }

constexpr int cf(int n) { return sq(n); }  // error: cf 不会升级

template<class T>
constexpr int tf(T n) { return sq(n); }    // OK：tf<int> 升级为立即函数
int t1 = tf(4);                            // OK：立即调用，是常量
int rt = 3;
int t2 = tf(rt);                           // error: 立即调用 tf(rt) 不是常量

auto lam = [](int n) { return sq(n); };    // OK：lambda 的调用运算符升级
int l1 = lam(2);                           // OK
```

升级之后，`tf<int>` 的每次调用都成了立即调用，检查转移到调用处：`tf(4)` 是常量，合法；`tf(rt)` 不是，非良构。

### 三个定义

¶2 一个潜在求值的表达式或转换，如果最初不处在立即函数语境中，也不是某个立即调用的子表达式，并且满足下面任一条件，就是**立即升级的**（[[g:immediate-escalating|immediate-escalating]]）表达式：

- ¶2.1 它是一个立即常量表达式，即结果指代立即函数或立即对象的常量表达式（[[expr.const.const#5]]）；
- ¶2.2 它是一个不是常量表达式的立即调用。

两种情形说的是同一件事：这里出现了只能存在于编译期的东西，而它所在的位置并不保证在编译期求值。最初（initially）一词用来打破循环：一个表达式是否在立即函数语境中，取决于所在函数是不是立即函数，而函数是否升级又取决于其中有没有立即升级表达式，所以判断时按升级之前的状态。

¶3 下面三类函数是**立即升级函数**（immediate-escalating function）：

- ¶3.1 没有声明为 `consteval` 的 lambda 的函数调用运算符；
- ¶3.2 没有声明为 `consteval` 的、非用户提供的预置函数，例如隐式声明的默认构造函数、`= default` 的比较运算符；
- ¶3.3 由带 `constexpr` 的模板化实体实例化出的函数，预期析构函数除外。函数模板的特化、类模板的 constexpr 成员函数都属于这一类。

!!! std
    An immediate-escalating expression shall appear only in an immediate-escalating function.

立即升级表达式只能出现在立即升级函数里。上例中的 `cf` 是手写的普通 constexpr 函数，不属于三类中的任何一类，所以它非良构。

¶4 **立即函数**是用 `consteval` 声明的函数（¶4.1），或者是一个立即升级函数 F，它的函数体里有一个立即升级表达式，且这个表达式最内层的非块作用域就是 F 的形参作用域（¶4.2）。

最内层作用域的要求排除了嵌套的 lambda：lambda 体里的立即升级表达式只让 lambda 的调用运算符升级，不会穿透到外层函数。

### 为什么只有这三类会升级

这三类函数有一个共同点：程序员没有办法或不方便在声明处写 `consteval`。

- 同一个模板的不同特化，有的需要 consteval，有的不需要，取决于模板实参（见下面标准例子里的 `f<char>` 和 `f<int>`）。
- lambda 很少有人写 `consteval`，泛型 lambda 本身就是模板。
- 编译器生成的构造函数和比较运算符没有地方写 `consteval`，但它们可能调用成员的 consteval 函数。

手写的普通 constexpr 函数只有一个实体。如果它需要用非常量实参调用 consteval 函数，就应该明确写成 `consteval`，或者把调用放进 `if consteval`，标准不替程序员决定。

### 标准例子（¶5）

```cpp
consteval int id(int i) { return i; }
constexpr char id(char c) { return c; }

template<class T>
constexpr int f(T t) { return t + id(t); }

auto a = &f<char>;           // OK：f<char> 调用的是 constexpr 的 id(char)
auto b = &f<int>;            // error: f<int> 是立即函数，不能取地址
static_assert(f(3) == 6);    // OK

template<class T>
constexpr int g(T t) {       // g<int> 不是立即函数：
  return t + id(42);         // id(42) 本身已经是常量
}
```

同一个模板，`f<char>` 是普通的 constexpr 函数，`f<int>` 却是立即函数。这正是升级只能按特化逐个决定的原因。Clang 的诊断会附注原因："'f<int>' is an immediate function because its body contains a call to a consteval function 'id' and that call is not a constant expression"。

```cpp run ok
template<class T, class F>
constexpr bool is_not(T t, F f) { return not f(t); }

consteval bool is_even(int i) { return i % 2 == 0; }

static_assert(is_not(5, is_even));   // OK
int main() {}
```

这里把 consteval 函数当作函数指针传给一个普通的泛型函数，也是合法的：

- 实参 `is_even` 指代立即函数，是立即常量表达式。但它位于 `static_assert` 的条件里，处在立即函数语境中（¶1.2），所以不是立即升级表达式。
- 在 `is_not<int, bool(*)(int)>` 的函数体里，`f(t)` 是通过函数指针形参的调用，静态上没有调用任何立即函数，所以这个特化不升级。
- 整个 `is_not(5, is_even)` 在一次常量求值中完成，`is_even` 的地址从未进入运行期。

只要 consteval 函数的地址不离开常量求值，它就可以穿过任意普通的 constexpr 泛型代码。

### 预置构造函数的升级

¶4 的注 1 说明，用来初始化基类或成员子对象的默认成员初始化器，视为构造函数函数体的一部分。所以默认成员初始化器里的 consteval 调用会让隐式的构造函数升级：

```cpp run ok
consteval int id(int i) { return i; }
struct Z {
  int a = 1;
  int b = id(a);    // 不是常量，是立即升级表达式
  Z() = default;    // 非用户提供 → 升级为立即函数
};
Z z;                // Z() 是立即调用，求值得 b == 1
int f() { Z lz; return lz.b; }   // 同样在编译期构造
int main() { return f() + z.b - 2; }
```

## 默认实参与默认成员初始化器

默认实参属于调用者：它在每个使用它的调用处求值（[[dcl.fct.default]]）。所以默认实参里的 consteval 调用让调用者升级，而不是让声明它的函数升级。

```cpp
consteval int id(int i) { return i; }
int x = 0;

template<class T>
constexpr T h(T t = id(x)) {  // h<int> 不是立即函数：
  return t;                   // 默认实参不在 h 里求值
}

template<class T>
constexpr T hh() {            // hh<int> 是立即函数：
  return h<T>();              // 这里用到了默认实参 id(x)
}

int i = hh<int>();            // error: hh<int>() 是立即调用，读取 x，不是常量
```

¶1 的最后一句处理聚合体。聚合体没有可以升级的构造函数，所以标准规定：如果一次聚合初始化求值了一个含有立即升级表达式的默认成员初始化器，这次聚合初始化本身就是立即调用。

```cpp
consteval int id(int i) { return i; }
struct A {
  int x;
  int y = id(x);     // x 是成员，不是常量
};

constexpr int k1 = A(42).y;   // OK：A(42) 是立即调用，整体是常量
int rt = 1;
int k2 = A{rt}.y;             // error: 立即调用 A{rt} 不是常量

template<class T>
constexpr int k(int) {        // k<int> 不是立即函数：
  return A(42).y;             // A(42) 是常量，不是立即升级表达式
}
```

!!! impl "Clang 23 与标准不一致"
    本机 Clang 23 连 `k1` 也拒绝，报告 "call to consteval function 'id' is not a constant expression"，并把 `k<int>` 当成立即函数（`&k<int>` 报 "cannot take address of immediate function"）。它把默认成员初始化器里的 `id(x)` 单独求值，此时 `this` 不可用，而没有把整个聚合初始化当作一次立即调用。按标准，`k1` 合法，`k<int>` 不是立即函数。

## 取立即函数的地址 {{c++26}}

C++20 和 C++23 中，指向立即函数的指针不能是常量表达式的结果，只能在立即函数语境内部传递。C++26 为配合反射，改用 consteval-only 值和立即对象来表述这条规则（[[expr.const.const#1]]）：指向立即函数的指针可以存进 constexpr 变量或用作模板实参，但不能进入运行期对象。

```cpp
consteval int plus1(int x) { return x + 1; }
template <auto V> struct C {};

auto a = plus1;            // error: 运行期变量
constexpr auto b = plus1;  // C++26：OK
auto c = C<plus1>();       // C++26：OK
```

这是 [[expr.const.const]] 的标准例子。截至写作时，本机 Clang 23 仍按 C++23 的规则拒绝 `b` 和 `c`。

## 契约与常量初始化 {{c++26}}

¶5 的标准例子最后一部分演示契约断言怎样影响初始化方式：

```cpp
constexpr int l(int c) pre(c >= 2) {
  return (c % 2 == 0) ? c / 0 : c;
}

const int i0 = l(0);  // 动态初始化；契约违反或未定义行为
const int i1 = l(1);  // 静态初始化；值为 1，或在编译期报告契约违反
const int i2 = l(2);  // 动态初始化；未定义行为
const int i3 = l(3);  // 静态初始化；值为 3
```

判断一个变量能否常量初始化时，契约断言一律按 ignore 语义处理（[[expr.const.init#4]]）。忽略前置条件后，`l(1)` 和 `l(3)` 都是常量，所以 `i1`、`i3` 静态初始化；`l(0)` 和 `l(2)` 都要除以 0，所以 `i0`、`i2` 动态初始化，运行时才出问题。

翻译期真正求值 `l(1)` 时，实现仍可以检查契约，这时 `1 >= 2` 不成立，产生编译期诊断。这样设计是为了让契约检查的开关不改变变量是静态还是动态初始化，否则打开检查就可能改变全局变量的初始化顺序。本机 Clang 23 尚不支持契约语法，这段代码没有经过编译验证。

## 其他约束

这些规则写在 [[dcl.constexpr]] 和 [[class.virtual]]：

- `consteval` 只能用于函数或函数模板的声明。consteval 函数隐式 inline，也是 constexpr 函数（[[dcl.constexpr#1]]、[[dcl.constexpr#2]]）。
- 一个函数的所有声明必须一致地带或不带 `consteval`。
- 析构函数、分配函数和释放函数不能是 consteval 的（[[dcl.constexpr#2]]）。语言会在离开作用域、`new`/`delete` 表达式等地方隐式调用它们，无法保证每次都在常量求值中。
- consteval 虚函数和非 consteval 虚函数不能互相覆盖（[[class.virtual#18]]）。

!!! impl "consteval 在编译器里"
    立即调用在语义分析阶段就被求值并替换成结果（Clang 中是 `ConstantExpr` 节点），不会到达代码生成，所以 consteval 函数没有符号，调试器也无法在其中设断点。升级要求编译器在实例化函数体时发现立即升级表达式后，把这个特化标记为立即函数，再回头检查之前对它的引用，例如取地址。Clang 在 `-std=c++20` 下也按 P2564 的规则处理。

## 历史与演进

!!! history
    - C++20（[[P1073R3]]）引入 `consteval`。规则很简单：调用必须是常量表达式，除非位于另一个 consteval 函数里。它和泛型转发代码不兼容。
    - C++23（[[P1938R3]]）引入 `if consteval`，让 constexpr 函数可以在编译期分支里调用 consteval 函数。
    - C++23（[[P2564R3]]，作为缺陷修复）引入立即升级，constexpr 模板在需要时自动变成立即函数。
    - C++26（[[P2996R13]]）为配合反射引入立即常量表达式、consteval-only 值和立即对象，指向立即函数的指针因此可以存进 constexpr 变量。

## 常见误解

!!! pitfall "升级只影响这一个函数"
    在 constexpr 函数模板里加一处 consteval 调用，可能让某些特化悄悄变成立即函数，于是远处的 `auto p = &tf<int>;` 或 `tf(runtime_value)` 开始报错。错误出现在使用处，而不是修改处。

!!! pitfall "普通 constexpr 函数也会升级"
    不会。`constexpr int wrap(int n) { return sq(n); }` 直接非良构，升级只适用于模板的特化、lambda 和预置函数。改成 `consteval`，或者把调用放进 `if consteval`。

## 思考题

!!! question "思考题 1"
    下面哪一行是错的？为什么？

    ```cpp
    consteval int sq(int n) { return n * n; }
    auto l1 = [](int n) { return sq(n); };
    auto l2 = [](int n) consteval { return sq(n); };
    int a = l1(2);
    int b = l2(2);
    auto p1 = +l1;
    ```

<details markdown="1">
<summary>答案</summary>

`auto p1 = +l1;` 是错的。`l1` 的调用运算符是立即升级函数（¶3.1），其中的 `sq(n)` 不是常量，所以它升级为立即函数。`+l1` 把无捕获 lambda 转换成函数指针，这个指针指向立即函数，在运行期变量的初始化器里构成立即升级表达式，而命名空间作用域的初始化器不在任何立即升级函数中。Clang 报 "cannot take address of immediate call operator"。`a`、`b` 都是以常量为实参的立即调用，合法。
</details>

!!! question "思考题 2"
    为什么 `std::is_constant_evaluated()` 是 constexpr 函数，而不是 consteval 函数？

<details markdown="1">
<summary>答案</summary>

如果它是 consteval 的，每次调用要么是立即调用，要么处在立即函数语境中，总是在编译期求值，结果永远是 `true`，也就无法区分当前是否处于常量求值中。它必须能在运行期调用并返回 `false`。它的规格正是用 `if consteval` 写的（[[meta.const.eval#1]]）。
</details>
