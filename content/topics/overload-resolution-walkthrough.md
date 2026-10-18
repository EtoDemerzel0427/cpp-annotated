---
title: 重载决议演练：八个经典谜题
summary: 用"候选集 → 可行集 → ICS 表 → 决胜规则"的固定流程，逐步推演八个经典的重载决议谜题：0 与空指针、字符串字面量与 bool、花括号初始化、反转的 operator==、转发构造函数劫持拷贝、模板与非模板、约束、值类别分派。
status: draft
order: 40
related: over.match, over.match.funcs, over.match.oper, over.match.viable, over.match.best, over.best.ics, over.ics.rank
tags: 重载决议
updated: 2026-10-17
---

重载决议的规则分散在十几个子条款里，单独读每一条都不难，难在把它们组合起来。这一页不讲新规则，只做一件事：**用同一个固定流程，把八个真实世界中反复出现的谜题从头推到尾**。

## 方法：四步表格法

每个谜题都按下面四步分析，对应 [[over.match]] 的结构：

1. **候选集**（[[over.match.funcs]]）：名字查找（+ ADL）找到哪些函数？模板推导出什么特化？运算符还有哪些成员/非成员/内建/改写候选？
2. **可行集**（[[over.match.viable]]）：个数对吗？约束满足吗？每个实参都有 ICS 吗？
3. **ICS 表**（[[over.best.ics]]、[[over.ics.rank]]）：为每个可行函数、每个实参写出 ICS 的**形式**（标准/用户定义/省略号）和**等级**（Exact/Promotion/Conversion），逐列比较。
4. **决胜**（[[over.match.best]]）：若 ICS 打平，按 2.2–2.13 的顺序找决胜规则。

ICS 表中用以下缩写：

| 缩写 | 含义 |
|---|---|
| **E** | 标准转换序列，Exact Match 等级（恒等、左值变换、限定调整） |
| **P** | 标准转换序列，Promotion 等级 |
| **C** | 标准转换序列，Conversion 等级 |
| **U** | 用户定义转换序列 |
| **…** | 省略号转换序列 |
| **✗** | 无法形成 ICS（不可行） |

---

## 谜题 1：`f(0)`、`f(NULL)` 与 `f(nullptr)`

```cpp nocheck
void f(int*);
void f(long);
void use() {
  f(0);         // ?
  f(0L);        // ?
  f('\0');      // ?
  f(nullptr);   // ?
}
```

**候选**：`f(int*)`、`f(long)`。都可行与否取决于实参。

| 实参 | `f(int*)` | `f(long)` | 结果 |
|---|---|---|---|
| `0`（`int`，空指针常量） | **C**：空指针转换（[[conv.ptr]]） | **C**：整型转换 | 打平，无决胜规则 → **歧义** |
| `0L`（`long`） | **C**：空指针转换 | **E**：恒等 | `f(long)` |
| `'\0'`（`char`） | ✗：不是空指针常量 | **C**：整型转换 | `f(long)` |
| `nullptr` | **C**：空指针转换 | ✗ | `f(int*)` |

要点：

- **空指针转换是 Conversion 等级**，不比 `int → long` 好。这是 C++98 时代 `NULL` 问题的根源：`0` 作为指针用时，与任何整型重载都同等级。
- `'\0'` 不是空指针常量：自 C++11 后的缺陷报告起，空指针常量只能是**值为 0 的整数字面量**或 `std::nullptr_t` 类型的 prvalue（[[conv.ptr]]），字符字面量不算。
- `nullptr` 的类型 `std::nullptr_t` 只能转换到指针、成员指针和（直接初始化中的）`bool`，不能转换到 `long`，于是 `f(long)` 不可行。

`f(NULL)` 呢？`NULL` 的定义是**实现定义的**（{{impl}}），可以是 `0`、`0L` 或编译器内建的 `__null`。本机（macOS 上的 Clang + libc++）`NULL` 展开为 `__null`，其类型在 LP64 下为 `long`，于是 `f(NULL)` 选中 `f(long)`；换一个平台，同样的代码可能歧义。这就是为什么现代 C++ 一律用 `nullptr`。

```cpp run ok
#include <cstdio>
void f(int*) { std::puts("f(int*)"); }
void f(long) { std::puts("f(long)"); }
int main() {
  f(0L);
  f('\0');
  f(nullptr);
}
```

---

## 谜题 2：`f("abc")`：`std::string` 还是 `bool`？

```cpp
#include <string>
void s(bool);
void s(const std::string&);
void use() {
  s("abc");   // ?
}
```

**候选**：两个都在。**可行**：都可行。

| 实参 `"abc"`（`const char[4]` 左值） | `s(bool)` | `s(const std::string&)` |
|---|---|---|
| ICS | 数组到指针（左值变换）+ 布尔转换 → **C**（标准） | `std::string(const char*)` 构造临时对象 → **U** |
| 比较 | | |

[[over.ics.rank#2]]：标准转换序列优于用户定义转换序列，**无论等级**。所以选 `s(bool)`，`"abc"` 被转换为 `true`。

```cpp run ok
#include <cstdio>
#include <string>
void s(bool)               { std::puts("s(bool)"); }
void s(const std::string&) { std::puts("s(string)"); }
int main() {
  using namespace std::literals;
  s("abc");     // s(bool)
  s("abc"s);    // s(string)：std::string 左值/右值 → const string& 是恒等
}
```

这个结果在真实代码库中造成过大量 bug（例如某个 `setValue(bool)` / `setValue(const std::string&)` 的 API，被传入字符串字面量后静默地设为 `true`）。修复办法：

- 加一个 `s(const char*)` 重载（Exact Match，胜过 bool 的 Conversion）；
- 或者把 `bool` 重载改成模板并加约束：`template<std::same_as<bool> B> void s(B);`——推导出 `B = const char*`，约束不满足，不可行；
- 或者用 `std::string_view` 代替 `const std::string&`——**不能**解决问题，`string_view` 的构造同样是用户定义转换。

---

## 谜题 3：花括号实参 `f({1, 2})`

```cpp nocheck
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

**`f({1, 2})`**：

| 实参 `{1, 2}` | `f(std::vector<int>)` | `f(std::pair<int,int>)` |
|---|---|---|
| ICS（[[over.ics.list#7]]） | [[over.match.list]] 第一阶段选中 `vector(initializer_list<int>)` → **U** | 第二阶段选中 `pair(int, int)`（或转发构造函数模板）→ **U** |

两边都是用户定义转换序列，但使用的是**不同的**构造函数，按 [[over.ics.rank#3.3]] 不可比较。3.1.1（`initializer_list` 优先）只看**形参类型本身**是不是 `initializer_list`，这里两者都不是。→ **歧义**。

**`g({1, 2})`**：

| 实参 `{1, 2}` | `g(std::vector<int>)` | `g(std::initializer_list<int>)` |
|---|---|---|
| ICS | **U**（经 `vector(initializer_list<int>)`） | [[over.ics.list#5]]：元素 `int → int` 中最差者 → **E**（标准） |

标准转换序列优于用户定义转换序列 → `g(std::initializer_list<int>)`。（即使两边形式相同，3.1.1 也会让 `initializer_list` 胜出。）

```cpp run ok
#include <vector>
#include <initializer_list>
#include <cstdio>
void g(std::vector<int>)            { std::puts("g(vector)"); }
void g(std::initializer_list<int>)  { std::puts("g(initializer_list)"); }
int main() { g({1, 2}); }
```

相关的构造函数谜题 `std::vector<int>{3}` vs `std::vector<int>(3)`，见 [[over.match.funcs]] §8。

---

## 谜题 4：C++20 的反转 `operator==`

```cpp
struct S {
  S(int);
  bool operator==(const S&) const;
};
bool a = S(1) == 2;   // ?
bool b = 1 == S(2);   // ? C++17 vs C++20
bool c = 1 != S(2);   // ?
```

**`1 == S(2)` 的候选**（[[over.match.oper]]）：

| 候选 | 来源 | 实参 1 → | 实参 2 → |
|---|---|---|---|
| `S::operator==` 成员候选 | 在 `int` 中搜索——`int` 不是类，**空** | — | — |
| 非成员候选 | 无 | — | — |
| 内建 `operator==(int, int)` 等 | [[over.built]] | `1`：**E** | `S(2) → int`：✗（`S` 没有转换函数） |
| **反转**的 `S::operator==` | 对 `S(2) == 1` 的成员候选合成 | `1 → const S&`（原来的显式形参）：**U**（经 `S(int)`） | `S(2)` → 对象形参：**E** |

只有反转候选可行 → C++20 中 `1 == S(2)` 合法，解释为 `S(2) == 1`。C++17 中没有反转候选，非良构。

`1 != S(2)`：改写候选中包含 `x == y` 的改写目标及其反转；同样只有反转候选可行 → 解释为 `!(S(2) == 1)`。

**C++20 引入的歧义**——把 `operator==` 改成非 `const`：

```cpp nocheck
struct T {
  bool operator==(const T&);     // 漏了 const
};
bool d = T{} == T{};
```

| 候选 | 实参 1（`T{}`） | 实参 2（`T{}`） |
|---|---|---|
| 普通 `T::operator==` | 对象形参 `T&`：**E** | `const T&`：**E** |
| 反转 `T::operator==` | `const T&`：**E** | 对象形参 `T&`：**E** |
| 比较（[[over.ics.rank#3.2.6]]） | 普通更好（`T&` cv 更少） | 反转更好 |

两边各赢一个实参，决胜规则 2.9（非反转优先）没有机会出场——它要求所有实参都不差。按标准是**歧义**；Clang 与 GCC 作为扩展接受并警告。修复：加上 `const`；或按 [[P2468R2]] 声明一个配对的 `operator!=`。

```cpp run ok
struct S {
  int v;
  S(int x) : v(x) {}
  bool operator==(const S& o) const { return v == o.v; }
};
int main() {
  bool a = S(1) == 1;    // 普通候选
  bool b = 1 == S(1);    // 反转候选
  bool c = 1 != S(2);    // 反转 + 改写：!(S(2) == 1)
  return a && b && c ? 0 : 1;
}
```

---

## 谜题 5：转发构造函数劫持拷贝构造函数

```cpp
#include <string>
struct P {
  std::string name;
  template<class T> P(T&& t);   // 想用于 P("alice")、P(std::string{...})
  P(const P&);                   // 拷贝构造
  P(P&&);                        // 移动构造
};
void use(P& a, const P& ca) {
  P b(a);      // ?
  P c(ca);     // ?
}
```

**`P b(a)`**——`a` 是非 const 的 `P` 左值。候选（[[over.match.ctor]]，直接初始化，全部构造函数）：

| 候选 | 推导/形参 | 实参 `a` 的 ICS |
|---|---|---|
| `P<P&>(P& t)`（模板，`T = P&`，引用折叠） | `P&` | 直接绑定，恒等 **E** |
| `P(const P&)` | `const P&` | 直接绑定，恒等 **E**，但被引用类型多了 `const` |
| `P(P&&)` | `P&&` | ✗：右值引用不能绑定左值 |

两个 **E** 之间，[[over.ics.rank#3.2.6]]：绑定到 cv 更少的引用者更好 → **模板胜出**。决胜规则 2.4（非模板优先）没有机会——ICS 已经分出高下。结果：拷贝一个非 const 的 `P` 时，调用的是转发构造函数，它试图用一个 `P&` 去初始化 `std::string name`，通常编译失败或行为错误。

**`P c(ca)`**——`ca` 是 const 左值：模板推导出 `T = const P&`，形参 `const P&`；拷贝构造函数也是 `const P&`。ICS 完全相同 → 决胜规则 2.4 → **非模板的拷贝构造函数**。

```cpp run ok
#include <cstdio>
struct P {
  template<class T> P(T&&) { std::puts("P(T&&)"); }
  P(const P&)              { std::puts("P(const P&)"); }
  P(P&&)                   { std::puts("P(P&&)"); }
  P() {}
};
int main() {
  P a;
  const P ca;
  P b(a);      // P(T&&)  ← 劫持！
  P c(ca);     // P(const P&)
  P d(P{});    // P(P&&)：模板 T = P 时形参 P&&，与移动构造 ICS 相同 → 非模板优先
}
```

**修复**：用约束把 `P` 自身（及其派生类）排除出模板的可行集：

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
  P b(a);      // P(const P&)：模板推导出 T = P&，约束不满足 → 不是候选
  P c(42);     // P(T&&)
}
```

注意继承构造函数的情形另有专门规则（[[over.match.funcs#9]]）：从基类继承来的"拷贝/移动样"构造函数不会被用来拷贝派生类对象。但同一个类里的转发构造函数只能靠你自己约束。

---

## 谜题 6：模板与非模板

```cpp
void f(int);
template<class T> void f(T);
void use() {
  f(1);      // ?
  f('a');    // ?
  f(1L);     // ?
  f<>(1);    // ?
}
```

| 实参 | `f(int)` | 模板 `f<T>(T)` | 结果 | 决定性规则 |
|---|---|---|---|---|
| `1` | **E** | `T = int`：**E** | `f(int)` | 打平 → 2.4 非模板优先 |
| `'a'` | **P**（`char → int`） | `T = char`：**E** | 模板 | 2.1：E 优于 P |
| `1L` | **C**（`long → int`） | `T = long`：**E** | 模板 | 2.1 |
| `f<>(1)` | 不是候选（显式模板实参列表只匹配模板） | `T = int`：**E** | 模板 | 唯一候选 |

**规律**：模板推导出的特化几乎总是精确匹配，所以除非非模板函数**也**是精确匹配，模板都会赢。"非模板优先"只是平局时的决胜规则，而不是"优先考虑"。

```cpp run ok
#include <cstdio>
void f(int)                  { std::puts("f(int)"); }
template<class T> void f(T)  { std::puts("f<T>"); }
int main() { f(1); f('a'); f(1L); f<>(1); }
```

---

## 谜题 7：约束与包含

```cpp
#include <concepts>
template<class T>                      void c(T);   // #1
template<std::integral T>              void c(T);   // #2
template<std::signed_integral T>       void c(T);   // #3
void use() {
  c(1);      // ?
  c(1u);     // ?
  c(1.0);    // ?
}
```

| 实参 | #1 | #2 | #3 | 结果 |
|---|---|---|---|---|
| `1`（`int`） | **E** | **E** | **E** | #3 |
| `1u` | **E** | **E** | ✗（约束不满足，推导失败） | #2 |
| `1.0` | **E** | ✗ | ✗ | #1 |

ICS 全部打平，进入决胜规则 2.5（[[temp.func.order]]）：三个模板除约束外完全相同，偏序退化为比较约束（[[temp.constr.order]]）。`std::signed_integral<T>` 定义为 `std::integral<T> && std::is_signed_v<T>`，**包含**（subsumes）`std::integral<T>`；后者又包含"无约束"。于是 #3 > #2 > #1。

**陷阱**：包含关系是在**原子约束**层面判断的，而两个原子约束只有在"表达式相同**且来自源代码中的同一处**"时才是同一个（[[temp.constr.atomic]]）。所以，若不用命名概念，而是在两处分别写出字面上相同的 `std::is_integral_v<T>`，它们是**不同的**原子约束，互不包含：

```cpp
#include <type_traits>
template<class T> requires std::is_integral_v<T>
void d(T);                                                     // #1
template<class T> requires std::is_integral_v<T> && std::is_signed_v<T>
void d(T);                                                     // #2
void use() {
  d(1);   // error: 歧义——两处 is_integral_v<T> 是不同的原子约束，#2 不包含 #1
}
```

这正是标准库把约束包装成**命名概念**的原因：概念 `std::integral` 的定义只出现一次，所有使用它的地方展开后得到同一个原子约束。

```cpp run ok
#include <concepts>
#include <cstdio>
template<class T>                void c(T) { std::puts("c(T)"); }
template<std::integral T>        void c(T) { std::puts("c(integral)"); }
template<std::signed_integral T> void c(T) { std::puts("c(signed_integral)"); }
int main() { c(1); c(1u); c(1.0); }
```

---

## 谜题 8：按值类别分派

```cpp
void v(int&);          // #1
void v(const int&);    // #2
void v(int&&);         // #3
void v(const int&&);   // #4
void use() {
  int i = 0;
  const int ci = 0;
  v(i);                                // ?
  v(ci);                               // ?
  v(1);                                // ?
  v(static_cast<const int&&>(ci));     // ?
}
```

| 实参 | #1 `int&` | #2 `const int&` | #3 `int&&` | #4 `const int&&` | 结果 | 规则 |
|---|---|---|---|---|---|---|
| `i`（左值 `int`） | **E** | **E**（+const） | ✗ | ✗ | #1 | 3.2.6：cv 更少 |
| `ci`（左值 `const int`） | ✗ | **E** | ✗ | ✗ | #2 | 唯一可行 |
| `1`（prvalue `int`） | ✗ | **E** | **E** | **E**（+const） | #3 | 3.2.3：右值绑右值引用（胜 #2）；3.2.6：cv 更少（胜 #4） |
| const xvalue | ✗ | **E** | ✗ | **E** | #4 | 3.2.3 |

这四种重载完整演示了 [[over.ics.ref#3]]（左右值限制决定可行性）与 [[over.ics.rank]] 3.2.3、3.2.6（决定优劣）的分工。实践中只需要 `const T&` + `T&&` 两个：前者接住一切，后者截获可移动的右值。

```cpp run ok
#include <cstdio>
void v(int&)        { std::puts("v(int&)"); }
void v(const int&)  { std::puts("v(const int&)"); }
void v(int&&)       { std::puts("v(int&&)"); }
void v(const int&&) { std::puts("v(const int&&)"); }
int main() {
  int i = 0;
  const int ci = 0;
  v(i); v(ci); v(1); v(static_cast<const int&&>(ci));
}
```

---

## 总结：读懂任何重载决议的检查清单

!!! summary
    1. **先查找，后决议**：确认名字查找（含 ADL、成员查找的隐藏）把哪些函数交了出来。很多"为什么没选它"的答案是"它根本不在候选集里"。
    2. **模板先推导**：推导失败或约束不满足的模板不是候选；推导出的形参类型通常与实参**精确**相同。
    3. **逐实参填 ICS 表**：先看形式（标准 > 用户定义 > 省略号），再看等级，再看细则（真子序列、引用的左右值与 cv、派生距离……）。
    4. **"所有实参都不差"是硬前提**：各赢一个实参就是歧义，任何决胜规则都救不了。
    5. **决胜规则只在平局时出场**：非模板、更特殊、更受约束、非改写、非反转。
    6. **选完再检查**：访问性、deleted、窄化、位域、explicit（拷贝列表初始化）、歧义转换序列——失败就是非良构，不会改选。
