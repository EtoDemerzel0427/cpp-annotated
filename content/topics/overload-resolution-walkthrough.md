---
title: 重载决议演练：八个经典谜题
summary: 用候选集、可行集、隐式转换序列表、决胜规则这四步，逐个推演八个常见的重载决议问题。
status: draft
order: 40
papers: P2468R2
related: over.match, over.match.funcs, over.match.oper, over.match.viable, over.match.best, over.best.ics, over.ics.rank
tags: 重载决议
updated: 2026-10-19
---

!!! tldr
    - 任何重载决议都可以按四步推演：候选集、可行集、逐个实参比较隐式转换序列、平局时找决胜规则。
    - 隐式转换序列先比形式：标准转换胜过用户定义转换，与等级无关。所以字符串字面量会选 `bool` 重载而不是 `std::string` 重载。
    - 一个函数要胜出，必须在每个实参上都不比对手差；两边各赢一个实参就是歧义，决胜规则救不了。
    - 非模板优先、更受约束优先、非反转优先这些规则只在所有实参都打平时才起作用。模板推导出的特化几乎总是精确匹配，所以非模板函数经常输给模板。
    - 未加约束的转发构造函数会在拷贝非 const 左值时胜过拷贝构造函数，要用约束把类自身排除出去。

## 四步法

每个谜题都按 [[over.match]] 的结构分四步分析：

1. **候选集**（[[over.match.funcs]]）：名字查找（包括 ADL）找到了哪些函数？模板推导出了哪些特化？运算符还有哪些成员、非成员、内建和改写候选？
2. **可行集**（[[over.match.viable]]）：实参个数对吗？约束满足吗？每个实参都能形成隐式转换序列吗？
3. **比较隐式转换序列**（[[over.best.ics]]、[[over.ics.rank]]）：**隐式转换序列**（implicit conversion sequence，下称 ICS）是把一个实参转换成形参类型的步骤。为每个可行函数、每个实参写出 ICS 的形式和等级，逐列比较。
4. **决胜**（[[over.match.best#2]]）：如果 ICS 打平，按该段第 2.2 到 2.13 项的顺序找决胜规则。

ICS 有三种形式：**标准转换序列**、**用户定义转换序列**（经过一个转换构造函数或转换函数）、**省略号转换序列**（实参匹配 `...`）。标准转换序列又按等级分为精确匹配（恒等、数组或函数到指针、限定调整）、提升和转换。下面的表格用这些缩写：

| 缩写 | 含义 |
|---|---|
| E | 标准转换序列，精确匹配等级 |
| P | 标准转换序列，提升等级 |
| C | 标准转换序列，转换等级 |
| U | 用户定义转换序列 |
| ✗ | 不能形成 ICS，函数不可行 |

## 谜题 1：`f(0)`、`f(NULL)` 与 `f(nullptr)`

```cpp
void f(int*);
void f(long);
void use() {
  f(0);         // ?
  f(0L);        // ?
  f('\0');      // ?
  f(nullptr);   // ?
}
```

候选是 `f(int*)` 和 `f(long)`，是否可行取决于实参：

| 实参 | `f(int*)` | `f(long)` | 结果 |
|---|---|---|---|
| `0`（`int`，空指针常量） | C：空指针转换（[[conv.ptr]]） | C：整型转换 | 打平，没有决胜规则，歧义 |
| `0L`（`long`） | C：空指针转换 | E：恒等 | `f(long)` |
| `'\0'`（`char`） | ✗：不是空指针常量 | C：整型转换 | `f(long)` |
| `nullptr` | C：空指针转换 | ✗ | `f(int*)` |

空指针转换的等级是转换，并不比 `int` 到 `long` 好。这就是 C++98 时代 `NULL` 问题的根源：`0` 当作指针用时，和任何整型重载同等级。

`'\0'` 不是空指针常量。经 C++11 之后的缺陷修复（[[CWG903]]），空指针常量只能是值为 0 的整数字面量，或 `std::nullptr_t` 类型的 prvalue，字符字面量不算。`nullptr` 的类型 `std::nullptr_t` 只能转换到指针、成员指针和 `bool`（仅限直接初始化），不能转换到 `long`，所以 `f(long)` 对它不可行。

`f(NULL)` 的结果取决于实现：`NULL` 可以定义为 `0`、`0L` 或编译器内建的 `__null`（{{impl}}）。本机 Clang 23 + libc++ 把它展开为 `__null`，在 LP64 平台上按 `long` 处理，于是选中 `f(long)`。换一个平台，同样的代码可能是歧义的。所以表示空指针时应当一律写 `nullptr`。

## 谜题 2：`std::string` 还是 `bool`

```cpp run ok
#include <cstdio>
#include <string>
void s(bool)               { std::puts("s(bool)"); }
void s(const std::string&) { std::puts("s(string)"); }
int main() {
  using namespace std::literals;
  s("abc");     // ?
  s("abc"s);    // ?
}
```

两个候选都可行：

| 实参 | `s(bool)` | `s(const std::string&)` |
|---|---|---|
| `"abc"`（`const char[4]` 左值） | 数组到指针，再布尔转换：C | 经 `std::string(const char*)` 构造临时对象：U |
| `"abc"s`（`std::string` prvalue） | ✗ | 引用直接绑定：E |

按 [[over.ics.rank#2]]，标准转换序列优于用户定义转换序列，不论等级。所以 `s("abc")` 选 `s(bool)`，字面量被转换成 `true`。程序先输出 `s(bool)`，再输出 `s(string)`。

这种重载在实际代码里造成过很多错误：一个同时有 `setValue(bool)` 和 `setValue(const std::string&)` 的接口，传入字符串字面量后悄悄地设成了 `true`。修复的办法有两种：

- 加一个 `s(const char*)` 重载，它是精确匹配，胜过 `bool` 的转换等级。
- 把 `bool` 重载改成受约束的模板：`template<std::same_as<bool> B> void s(B);`。对 `"abc"` 推导出 `B = const char*`，约束不满足，这个重载不可行。

把 `const std::string&` 换成 `std::string_view` 不能解决问题，从 `const char*` 构造 `string_view` 同样是用户定义转换。

## 谜题 3：花括号实参

```cpp
#include <vector>
#include <utility>
#include <initializer_list>
void f(std::vector<int>);
void f(std::pair<int, int>);
void g(std::vector<int>);
void g(std::initializer_list<int>);
void use() {
  f({1, 2});   // ?
  g({1, 2});   // ?
}
```

实参 `{1, 2}` 是花括号初始化列表，不是表达式，ICS 按 [[over.ics.list]] 的专门规则形成。

`f({1, 2})`：

| 实参 `{1, 2}` | `f(std::vector<int>)` | `f(std::pair<int, int>)` |
|---|---|---|
| ICS（[[over.ics.list#7]]） | 经构造函数 `vector(initializer_list<int>)`：U | 经 `pair` 的构造函数：U |

两边都是用户定义转换序列，但用的是不同的构造函数，按 [[over.ics.rank#3.3]] 无法比较。[[over.ics.rank#3]] 的第 3.1.1 项偏好转换到 `std::initializer_list` 的序列，但这里两个形参类型都不是 `initializer_list`，用不上。结果是歧义，本机 Clang 23 报 `call to 'f' is ambiguous`。

`g({1, 2})`：

| 实参 `{1, 2}` | `g(std::vector<int>)` | `g(std::initializer_list<int>)` |
|---|---|---|
| ICS | 经 `vector(initializer_list<int>)`：U | [[over.ics.list#5]]：取各元素转换中最差的一个，`int` 到 `int`：E |

标准转换序列优于用户定义转换序列，选 `g(std::initializer_list<int>)`。

构造函数层面的对应问题，`std::vector<int>{3}` 与 `std::vector<int>(3)` 的区别，见 [[over.match.list]]。

## 谜题 4：C++20 的反转 `operator==`

```cpp run ok
struct S {
  int v;
  S(int x) : v(x) {}
  bool operator==(const S& o) const { return v == o.v; }
};
int main() {
  bool a = S(1) == 1;    // ?
  bool b = 1 == S(1);    // ?  C++17 呢？
  bool c = 1 != S(2);    // ?
  return a && b && c ? 0 : 1;
}
```

`1 == S(1)` 的候选（[[over.match.oper]]）：

| 候选 | 来源 | 第 1 个实参 | 第 2 个实参 |
|---|---|---|---|
| 成员候选 | 在 `int` 中查找 `operator==`，`int` 不是类，没有 | | |
| 非成员候选 | 没有 | | |
| 内建 `operator==(int, int)` 等 | [[over.built]] | `1`：E | `S(1)` 到 `int`：✗，`S` 没有转换函数 |
| 反转的 `S::operator==` | 为 `S(1) == 1` 合成 | `1` 到 `const S&`（原来的显式形参）：U，经 `S(int)` | `S(1)` 到对象形参：E |

只有反转候选可行，所以 C++20 中 `1 == S(1)` 合法，解释为 `S(1) == 1`。C++17 没有反转候选，这一行是非良构的。`1 != S(2)` 的改写候选包括 `x == y` 及其反转，同样只有反转候选可行，解释为 `!(S(2) == 1)`。

反转候选也带来了新的歧义。把 `operator==` 写成非 const 成员：

```cpp error
struct T {
  bool operator==(const T&);     // 漏了 const
};
bool d = T{} == T{};             // 按标准是歧义
```

| 候选 | 第 1 个实参 `T{}` | 第 2 个实参 `T{}` |
|---|---|---|
| 普通的 `T::operator==` | 对象形参 `T&`：E | `const T&`：E |
| 反转的 `T::operator==` | `const T&`：E | 对象形参 `T&`：E |
| 比较（[[over.ics.rank#3.2.6]]） | 普通的更好，绑定的引用 cv 限定更少 | 反转的更好 |

两边各赢一个实参。[[over.match.best#2]] 第 2.9 项的非反转优先要求所有实参都不差，在这里用不上，所以按标准是歧义。本机 Clang 23 作为扩展接受这段代码，并给出 `-Wambiguous-reversed-operator` 警告。修复方法是加上 `const`，或者按 [[P2468R2]] 声明一个配对的 `operator!=`，这样 `operator==` 就不再生成反转候选。

## 谜题 5：转发构造函数劫持拷贝

```cpp run ok
#include <cstdio>
#include <utility>
struct P {
  template<class T> P(T&&) { std::puts("P(T&&)"); }
  P(const P&)              { std::puts("P(const P&)"); }
  P(P&&)                   { std::puts("P(P&&)"); }
  P() {}
};
int main() {
  P a;
  const P ca;
  P b(a);             // ?
  P c(ca);            // ?
  P d(std::move(a));  // ?
}
```

`P b(a)` 中 `a` 是非 const 的 `P` 左值。直接初始化考虑全部构造函数（[[over.match.ctor]]）：

| 候选 | 形参 | 实参 `a` 的 ICS |
|---|---|---|
| 模板，推导出 `T = P&`，引用折叠后 | `P&` | 直接绑定：E |
| `P(const P&)` | `const P&` | 直接绑定：E，但被引用类型多了 `const` |
| `P(P&&)` | `P&&` | ✗：右值引用不能绑定左值 |

两个 E 之间，按 [[over.ics.rank#3.2.6]]，绑定到 cv 限定更少的引用更好，于是模板胜出。[[over.match.best#2]] 第 2.4 项的非模板优先没有机会起作用，因为 ICS 已经分出了高下。拷贝一个非 const 的 `P` 时，调用的是转发构造函数。如果它用实参去初始化某个成员，比如 `std::string name`，通常会编译失败。

`P c(ca)` 中，模板推导出 `T = const P&`，形参是 `const P&`，与拷贝构造函数完全相同。ICS 打平，按第 2.4 项选非模板的拷贝构造函数。`P d(std::move(a))` 同理：模板推导出 `T = P`，形参 `P&&` 与移动构造函数相同，选移动构造函数。程序依次输出 `P(T&&)`、`P(const P&)`、`P(P&&)`。

修复办法是用约束把 `P` 自身及其派生类排除出模板的候选：

```cpp run ok
#include <concepts>
#include <type_traits>
#include <cstdio>
struct P {
  template<class T>
    requires (!std::derived_from<std::remove_cvref_t<T>, P>)
  P(T&&) { std::puts("P(T&&)"); }
  P(const P&) { std::puts("P(const P&)"); }
  P() {}
};
int main() {
  P a;
  P b(a);      // P(const P&)：T = P& 时约束不满足
  P c(42);     // P(T&&)
}
```

从基类继承来的构造函数另有专门规则（[[over.match.funcs.general#9]]）：形如拷贝或移动构造函数的继承构造函数，不会被用来从单个实参构造派生类对象。同一个类里的转发构造函数则只能靠自己加约束。

## 谜题 6：模板与非模板

```cpp run ok
#include <cstdio>
void f(int)                  { std::puts("f(int)"); }
template<class T> void f(T)  { std::puts("f<T>"); }
int main() {
  f(1);      // ?
  f('a');    // ?
  f(1L);     // ?
  f<>(1);    // ?
}
```

| 实参 | `f(int)` | 模板 `f<T>(T)` | 结果 | 起决定作用的规则 |
|---|---|---|---|---|
| `1` | E | `T = int`：E | `f(int)` | 打平，第 2.4 项：非模板优先 |
| `'a'` | P，`char` 提升为 `int` | `T = char`：E | 模板 | 第 2.1 项：E 优于 P |
| `1L` | C，`long` 转换为 `int` | `T = long`：E | 模板 | 第 2.1 项 |
| `f<>(1)` | 不是候选，显式模板实参列表只匹配模板 | `T = int`：E | 模板 | 唯一候选 |

模板推导出的特化几乎总是精确匹配，所以除非非模板函数也是精确匹配，否则模板会赢。非模板优先只是平局时的决胜规则。

## 谜题 7：约束与包含

```cpp run ok
#include <concepts>
#include <cstdio>
template<class T>                void c(T) { std::puts("c(T)"); }               // #1
template<std::integral T>        void c(T) { std::puts("c(integral)"); }        // #2
template<std::signed_integral T> void c(T) { std::puts("c(signed_integral)"); } // #3
int main() {
  c(1);      // ?
  c(1u);     // ?
  c(1.0);    // ?
}
```

| 实参 | #1 | #2 | #3 | 结果 |
|---|---|---|---|---|
| `1`（`int`） | E | E | E | #3 |
| `1u` | E | E | ✗，约束不满足 | #2 |
| `1.0` | E | ✗ | ✗ | #1 |

ICS 全部打平，进入 [[over.match.best#2]] 第 2.5 项，按 [[temp.func.order]] 对模板做偏序。三个模板除了约束完全相同，偏序退化为比较约束（[[temp.constr.order]]）。`std::signed_integral<T>` 定义为 `std::integral<T> && std::is_signed_v<T>`，因而**包含**（subsumes）`std::integral<T>`，后者又包含无约束。于是 #3 优于 #2，#2 优于 #1。

包含关系是在原子约束的层面判断的。按 [[temp.constr.atomic]]，两个原子约束只有在表达式相同、并且出自源代码同一处时才算同一个。如果不用命名概念，而是在两处分别写出字面上相同的 `std::is_integral_v<T>`，它们是两个不同的原子约束，互不包含：

```cpp error
#include <type_traits>
template<class T> requires std::is_integral_v<T>
void d(T);                                                     // #1
template<class T> requires std::is_integral_v<T> && std::is_signed_v<T>
void d(T);                                                     // #2
void use() {
  d(1);   // error: 歧义，#2 不包含 #1
}
```

标准库把约束包装成命名概念，原因就在这里：`std::integral` 的定义只出现一次，所有用到它的地方展开后得到的是同一个原子约束。

## 谜题 8：按值类别分派

```cpp run ok
#include <cstdio>
void v(int&)        { std::puts("v(int&)"); }          // #1
void v(const int&)  { std::puts("v(const int&)"); }    // #2
void v(int&&)       { std::puts("v(int&&)"); }         // #3
void v(const int&&) { std::puts("v(const int&&)"); }   // #4
int main() {
  int i = 0;
  const int ci = 0;
  v(i);                               // ?
  v(ci);                              // ?
  v(1);                               // ?
  v(static_cast<const int&&>(ci));    // ?
}
```

| 实参 | #1 `int&` | #2 `const int&` | #3 `int&&` | #4 `const int&&` | 结果 | [[over.ics.rank#3]] 的规则 |
|---|---|---|---|---|---|---|
| `i`，`int` 左值 | E | E，多了 const | ✗ | ✗ | #1 | 3.2.6：cv 限定更少 |
| `ci`，`const int` 左值 | ✗ | E | ✗ | ✗ | #2 | 唯一可行 |
| `1`，`int` prvalue | ✗ | E | E | E，多了 const | #3 | 3.2.3：右值绑定右值引用，胜过 #2；3.2.6：胜过 #4 |
| `const int` xvalue | ✗ | E | ✗ | E | #4 | 3.2.3 |

这四个重载展示了两类规则的分工：[[over.ics.ref#3]] 的左值、右值限制决定哪些函数可行；[[over.ics.rank#3]] 的第 3.2.3 和 3.2.6 项决定哪个更好。实践中通常只需要 `const T&` 和 `T&&` 两个重载：前者接受一切，后者截获可以移动的右值。

## 检查清单

1. 先查找，后决议。确认名字查找（包括 ADL 和成员查找中的隐藏）把哪些函数交了出来。很多为什么没选它的答案是它根本不在候选集里。
2. 模板先推导。推导失败或约束不满足的模板不是候选；推导出的形参类型通常与实参精确相同。
3. 逐个实参比较 ICS。先看形式（标准优于用户定义，用户定义优于省略号），再看等级，再看细则：真子序列、引用绑定的左右值与 cv 限定、派生距离等。
4. 所有实参都不差是前提。两边各赢一个实参就是歧义。
5. 决胜规则只在平局时起作用：非模板、更特殊的模板、约束更多、非改写、非反转。
6. 选定之后还要检查：访问权限、是否被删除、窄化、拷贝列表初始化中选中了 explicit 构造函数等。这些检查失败时程序非良构，不会改选其他函数。
