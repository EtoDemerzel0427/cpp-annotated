---
title: 最佳可行函数
summary: 如何在可行函数之间分出高下：逐实参比较隐式转换序列，全部不差且至少一处更好者胜；打平时依次使用十余条决胜规则（转换结果、非模板优先、偏序、约束、继承构造函数、改写/反转候选、CTAD 专用规则）。
status: draft
covers: over.match.best.general
related: over.match, over.match.viable, over.best.ics, over.ics.rank, temp.func.order, temp.constr.order, over.match.oper, over.match.class.deduct
tags: 重载决议
updated: 2026-10-17
---

可行函数选出来之后，重载决议的最后一步是在它们之间"比武"。[[over.match.best]] 定义了比武规则：什么叫一个函数比另一个**更好**（better），以及什么时候存在唯一的**最佳**可行函数（best viable function）。

规则分两层：

1. **主规则**：逐个实参比较隐式转换序列（ICS）。若 `F1` 在每个实参上都**不比** `F2` 差，且至少在一个实参上**更好**，`F1` 更好。
2. **决胜规则**（tie-breakers）：若所有实参上都不差、但也没有一处更好（"打平"），按固定顺序检查一串与 ICS 无关的性质：是不是模板、谁更特殊、谁更受约束、是不是改写候选……

本页的子条款 [over.best.ics] 与 [over.ics.rank] 定义"一个 ICS 比另一个好"是什么意思，分别见 [[over.best.ics]] 与 [[over.ics.rank]]。

## ICSi(F)（¶1）

¶1 定义 **ICSi(F)** 为把第 `i` 个实参转换到可行函数 `F` 的第 `i` 个形参类型的隐式转换序列。[[over.best.ics]] 定义隐式转换序列，[[over.ics.rank]] 定义"更好/更差的转换序列"。

注意"第 `i` 个"的对齐：对成员函数，第 1 个实参是隐含对象实参，对上隐式对象形参（[[over.match.funcs#2]]）；对静态成员函数，第一个实参的 ICS"既不比任何标准转换序列好也不比它差"（[[over.best.ics#8]]）；对反转的改写候选，实参顺序是交换过的（[[over.match.oper]]）。

## 什么叫"更好的函数"（¶2）

¶2 可行函数 `F1` 被定义为比另一个可行函数 `F2` **更好**，如果**对所有实参 `i`，ICSi(F1) 都不比 ICSi(F2) 差**，并且：

!!! std
    "a viable function F1 is defined to be a *better* function than another viable function F2 if for all arguments i, ICSi(F1) is not a worse conversion sequence than ICSi(F2), and then …"

    "对所有实参都不差"是**前提**，之后的各条（主规则 2.1 与决胜规则 2.2–2.13）只是在这个前提下寻找"更好"的理由。

这一前提非常关键：**决胜规则只在 ICS 全部不差时才有机会出场**。如果 `F1` 在某个实参上更差，无论它是不是非模板、是不是更受约束，都不可能比 `F2` 更好。

下面按顺序列出每一条（"或者，若不是这样"表示前一条不成立时才看下一条）：

### ¶2.1 某个实参上 ICS 更好

存在某个实参 `j`，ICSj(F1) 是比 ICSj(F2) 更好的转换序列。这是主规则——绝大多数重载决议在这一条就结束了。

### ¶2.2 用户定义转换的初始化：比较"结果到目标"的转换

语境是**用户定义转换的初始化**（[[dcl.init]]、[[over.match.conv]]、[[over.match.ref]]），且从 `F1` 的结果到目标类型的标准转换序列，比从 `F2` 的结果到目标类型的更好。

```cpp
struct A {
  A();
  operator int();
  operator double();
} a;
int   i = a;   // OK：operator int() 后无需转换，优于 operator double() 后 double→int
float x = a;   // error: 歧义——int→float 与 double→float 都是转换，无从区分
```

为什么需要这条？在 [[over.match.conv]] 的语境里，实参列表只有一个：初始化器（对上转换函数的对象形参）。两个转换函数的对象实参 ICS 完全相同，主规则无法区分。真正的差别在于"转换函数返回之后还要再转换多少"——这一步不属于任何实参的 ICS，所以需要单独一条规则。

### ¶2.3 到函数类型的引用直接绑定：引用种类匹配者优先

语境是用转换函数直接绑定"到函数类型的引用"，`F1` 的返回类型与被初始化的引用是**同一种**引用（左值或右值），而 `F2` 不是。

```cpp nocheck
template <class T> struct A {
  operator T&();    // #1
  operator T&&();   // #2
};
typedef int Fn();
int main() {
  A<Fn> a;
  Fn&  lf = a;      // 调用 #1
  Fn&& rf = a;      // 调用 #2
  (void)lf; (void)rf;
}
```

函数左值可以绑定到右值引用（函数没有"右值"），所以 `#1`、`#2` 对两个引用都能用；这条规则让"引用种类一致"者胜出，避免歧义。它与 [[over.ics.rank#3.2.4]]（函数左值优先绑定左值引用）是互补的。

!!! impl "Clang 的偏离"
    截至写作时，Clang 23 接受 `Fn& lf = a;`（选 #1），但对 `Fn&& rf = a;` 报"reference initialization … is ambiguous"，即没有实现 2.3 的这一半。按标准，`rf` 的初始化良构并调用 #2。

### ¶2.4 非模板优于模板特化

`F1` 不是函数模板特化，而 `F2` 是。

```cpp run ok
#include <cstdio>
void f(int)                      { std::puts("f(int)"); }
template<class T> void f(T)      { std::puts("f<T>(T)"); }
int main() {
  f(1);      // f(int)：ICS 相同（都是精确匹配），非模板优先
  f('a');    // f<char>：模板推导出 f(char)，精确匹配；f(int) 需要整型提升——2.1 先于 2.4
  f<>(1);    // f<int>：显式模板实参列表，只有模板是候选
}
```

`f('a')` 是经典的"模板赢了非模板"：决胜规则只在 ICS 打平时才出场，而模板推导出的精确签名通常比非模板更"贴身"。

### ¶2.5 更特殊的模板

`F1` 与 `F2` 都是函数模板特化，且 `F1` 的模板按 [[temp.func.order]] 的偏序规则比 `F2` 的模板**更特殊**（more specialized）。偏序本身也会考虑约束：两个模板在其他方面等价时，更受约束者更特殊（[[temp.func.order]]、[[temp.constr.order]]）。

```cpp run ok
#include <concepts>
#include <cstdio>
template<class T> void g(T)   { std::puts("g(T)"); }
template<class T> void g(T*)  { std::puts("g(T*)"); }
template<class T>             void h(T) { std::puts("h(T)"); }
template<std::integral T>     void h(T) { std::puts("h(integral T)"); }
int main() {
  int i = 0;
  g(&i);     // g(T*)：两者推导后都是 g(int*)，ICS 相同；g(T*) 更特殊
  h(1);      // h(integral T)：模板头之外等价，更受约束者更特殊
  h(1.0);    // h(T)：受约束版本不满足约束，推导即失败，不是候选
}
```

### ¶2.6 非模板函数：更受约束者优先

`F1` 与 `F2` 都是非模板函数，且 `F1` 比 `F2` **更偏序受约束**（more partial-ordering-constrained，[[temp.constr.order#6]]）：二者非对象形参类型列表相同；若是成员函数，都是同一个类的直接成员；若都是非静态成员函数，对象形参类型相同；并且 `F1` 的声明比 `F2` 的**更受约束**。

```cpp run ok
template <typename T = int>
struct S {
  constexpr int f() { return 1; }                            // #1
  constexpr int f(this S&) requires true { return 2; }       // #2
};
int main() {
  S<> s;
  return s.f() == 2 ? 0 : 1;   // 调用 #2
}
```

这个标准例子里，#1 是隐式对象成员函数、#2 是显式对象成员函数，但它们的对象形参类型都是 `S&`，满足"对象形参类型相同"，所以可以按约束比较，#2 胜出。

非模板函数只能在**模板化**的语境里带约束（类模板的成员、模板化的 lambda 等），所以这条规则主要服务于类模板中的条件成员函数——例如 `std::optional<T>` 的平凡/非平凡特殊成员函数的选择（[[special]] 中"合格的"（eligible）特殊成员函数也是靠"更受约束"来挑的）。

### ¶2.7 派生类构造函数优于继承来的基类构造函数

`F1` 是类 `D` 的构造函数，`F2` 是 `D` 的基类 `B` 的构造函数（经继承），且对所有实参，`F1` 与 `F2` 对应的形参类型相同。

```cpp run ok
struct A {
  A(int = 0) {}
};
struct B : A {
  using A::A;
  B() {}
};
int main() {
  B b;      // B::B()：A(int = 0) 继承后也能接受 0 个实参，形参（无）相同，派生类自己的构造函数优先
}
```

直觉：派生类作者"重新定义"了一个同签名的构造函数，就该用它。没有这条规则，`B b;` 会歧义。

### ¶2.8 非改写候选优于改写候选

`F2` 是改写候选（[[over.match.oper]]），而 `F1` 不是。

```cpp
#include <compare>
struct S {
  friend auto operator<=>(const S&, const S&) = default;   // #1
  friend bool operator<(const S&, const S&);               // #2
};
bool b = S() < S();    // 调用 #2：#1 的改写候选 (x <=> y) < 0 与 #2 的 ICS 相同，非改写者胜
```

这保证用户为某个比较运算符写的"专门版本"总是优先于由 `<=>`/`==` 改写而来的通用版本。

### ¶2.9 非反转候选优于反转候选

`F1` 与 `F2` 都是改写候选，`F2` 是参数反转的合成候选而 `F1` 不是。

```cpp
#include <compare>
struct S {
  friend std::weak_ordering operator<=>(const S&, int);   // #1
  friend std::weak_ordering operator<=>(int, const S&);   // #2
};
bool b = 1 < S();      // 调用 #2：(1 <=> S()) < 0；反转的 #1 即 0 < (S() <=> 1)，ICS 相同，非反转者胜
```

注意 2.8 与 2.9 的边界：若 `x == y` 的普通候选与反转候选在**某个实参上**分出了高下（比如一个是非 const 成员），根本到不了这里——这就是 C++20 中很多"歧义"的来源（见 [[over.match.oper]] 的兼容性一节）。

### ¶2.10–¶2.13 类模板实参推导专用

这四条只在 CTAD 的假想重载决议中起作用（[[over.match.class.deduct]]）：

| 规则 | `F1` 优于 `F2`，若 |
|---|---|
| 2.10 | 二者都由 CTAD 为类 `D` 生成，`F2` 来自**继承**基类的构造函数而 `F1` 不是，且每个显式实参对应的形参要么都是省略号、要么类型相同 |
| 2.11 | `F1` 由**推导指引**（*deduction-guide*）生成而 `F2` 不是 |
| 2.12 | `F1` 是**拷贝推导候选**而 `F2` 不是 |
| 2.13 | `F1` 由**非模板构造函数**生成而 `F2` 由**构造函数模板**生成 |

```cpp
template <class T> struct A {
  using value_type = T;
  A(value_type);    // #1
  A(const A&);      // #2
  A(T, T, int);     // #3
  template<class U>
    A(int, T, U);   // #4
  // #5 是拷贝推导候选 A(A)
};

A x(1, 2, 3);       // 用 #3（2.13）

template <class T>
A(T) -> A<T>;       // #6，不如 #5 特殊

A a(42);            // 用 #6 推出 A<int>，再用 #1 初始化
A b = a;            // 用 #5 推出 A<int>（2.5：#5 更特殊），再用 #2 初始化

template <class T>
A(A<T>) -> A<A<T>>; // #7，与 #5 同样特殊

A b2 = a;           // 用 #7 推出 A<A<int>>（2.11：偏序打平，推导指引优先），再用 #1 初始化
```

注意 CTAD 指引都是函数**模板**，所以 2.4 很少起作用，而 2.5 的偏序往往先于 2.11–2.13 决定结果——`b` 与 `b2` 的差别就在于此。

### 决胜规则一览

| 顺序 | 规则 | 典型场景 |
|---|---|---|
| 2.1 | 某实参 ICS 更好 | 绝大多数情况 |
| 2.2 | 用户定义转换后的第二标准转换更好 | `int i = obj;` 在多个转换函数间选择 |
| 2.3 | 函数引用的引用种类匹配 | `Fn& r = obj;` |
| 2.4 | 非模板 > 模板特化 | `f(int)` vs `template f(T)` |
| 2.5 | 更特殊的模板（含约束） | `g(T*)` vs `g(T)` |
| 2.6 | 更受约束的非模板函数 | 类模板中的条件成员函数 |
| 2.7 | 派生类构造函数 > 继承的基类构造函数 | `using Base::Base;` |
| 2.8 | 非改写 > 改写 | 手写 `<` vs 由 `<=>` 改写 |
| 2.9 | 非反转 > 反转 | `x <=> y` vs 反转的 `y <=> x` |
| 2.10 | （CTAD）非继承 > 继承 | 继承构造函数的 CTAD |
| 2.11 | （CTAD）推导指引 > 隐式指引 | 用户写的推导指引 |
| 2.12 | （CTAD）拷贝推导候选 > 其他 | `A b = a;` |
| 2.13 | （CTAD）非模板构造函数 > 构造函数模板 | |

## 唯一的最佳者（¶3）

¶3 若恰好有一个可行函数比**所有其他**可行函数都更好，它就是重载决议的结果；否则调用非良构。

标准的例子精确展示了"各赢一个实参"导致的歧义：

```cpp
void Fcn(const int*, short);
void Fcn(int*, int);

int i;
short s = 0;

void f() {
  Fcn(&i, s);     // error: 歧义——&i→int* 优于 &i→const int*，但 s→short 优于 s→int
  Fcn(&i, 1L);    // OK：Fcn(int*, int)——&i→int* 更好；1L→short 与 1L→int 都是整型转换，无从区分
  Fcn(&i, 'c');   // OK：Fcn(int*, int)——&i→int* 更好；'c'→int 是提升，优于 'c'→short 的转换
}
```

把 ICS 列成表，一目了然：

| 调用 | 实参 | `Fcn(const int*, short)` | `Fcn(int*, int)` | 谁更好 |
|---|---|---|---|---|
| `Fcn(&i, s)` | `&i` | 限定转换（Exact Match，但不是恒等） | 恒等 | 后者 |
| | `s` | 恒等 | 整型提升 | 前者 |
| | | | | **歧义** |
| `Fcn(&i, 1L)` | `&i` | 限定转换 | 恒等 | 后者 |
| | `1L` | 整型转换 | 整型转换 | 打平 |
| | | | | **后者** |
| `Fcn(&i, 'c')` | `&i` | 限定转换 | 恒等 | 后者 |
| | `'c'` | 整型转换（char→short 不是提升） | 整型提升 | 后者 |
| | | | | **后者** |

（`&i → int*` 优于 `&i → const int*`，依据是 [[over.ics.rank#3.2.1]]：恒等是任何非恒等序列的真子序列。注意 `char → short` 不是整型提升——[[conv.prom]] 的提升目标只有 `int`/`unsigned int` 等。）

### 线性时间算法（脚注 98）

"恰好一个比所有其他都好"听起来需要两两比较（O(n²)）。脚注给出了一个线性算法：

1. 跑一轮"锦标赛"：维护当前擂主 `W`，依次与每个函数比较，若挑战者更好则换擂主。
2. 再遍历一次，验证 `W` 是否比**所有**其他函数都好。

正确性：任何没当上最终擂主的函数 `F`，在某一轮中输给了（或没能打败）某个 `G`，即 `F` 不比 `G` 更好，所以 `F` 不可能是最佳者。因此最佳者若存在，只可能是 `W`；第二遍验证决定它是否真的是。

这个论证只用到"最佳者必须比**每一个**其他函数都更好"这一定义，不需要假设"更好"关系具有传递性；第一遍只能找出唯一可能的人选，第二遍验证才给出结论。

## 关于默认实参的注（¶4）

¶4 注：若最佳可行函数是靠一个或多个默认实参才可行的，还有额外要求（[[over.match.viable#2]]：提供默认实参的作用域必须唯一）。

## 实现视角

!!! impl
    - Clang 的 `isBetterOverloadCandidate` 几乎逐条对应 ¶2 的顺序：先逐实参调用 `CompareImplicitConversionSequences`，若出现"某处更差"立即返回 false；然后依次检查转换函数结果、非模板/模板、偏序（`getMoreSpecializedTemplate`）、约束、继承构造函数、改写/反转、CTAD 专用规则。GCC 的 `joust` 函数同理。
    - 编译器的歧义诊断会列出所有"最佳候选的竞争者"。读诊断时，先找出它们在哪个实参上各有胜负，通常就能定位问题。
    - Clang 和 GCC 在一些场合会以扩展的形式"打破"标准规定的歧义（最著名的是 C++20 的反转 `operator==`，见 [[over.match.oper]]），并给出警告。

## 历史与演进

!!! history
    - **C++98**：主规则、转换函数结果规则、非模板优先、偏序。
    - **C++11**：函数引用的引用种类规则（2.3）；继承构造函数。
    - **C++17**：CTAD 的推导指引/拷贝推导候选/非模板构造函数规则；继承构造函数新模型下的 2.7。
    - **C++20**：约束（偏序中考虑约束，非模板函数按约束比较）；改写与反转候选规则（2.8、2.9）。
    - **C++23**：继承构造函数的 CTAD（2.10）；显式对象形参。
    - **C++26**：{{c++26}} 2.6 使用"更偏序受约束"（more partial-ordering-constrained）这一新术语，明确要求两个非模板函数的非对象形参类型列表相同、属于同一个类、对象形参类型相同。

## 陷阱

!!! pitfall "以为'非模板优先'能压过更好的转换"
    决胜规则只在 ICS 打平时起作用。`f(int)` 与 `template<class T> f(T)`，对 `f('a')`、`f(1L)`、`f(1.0f)` 都会选模板。

!!! pitfall "以为'更受约束'能压过更好的转换"
    同理：约束只在可行性（不满足则不可行）和打平时起作用。

!!! pitfall "以为两个各有千秋的候选，编译器会'综合评分'"
    没有加权、没有计数。只要各在一个实参上胜出，就是歧义。

## 思考题

!!! question "1. 下面两个调用分别选哪个？"
    ```cpp nocheck
    void f(int, double);       // #1
    void f(long, int);         // #2
    template<class T> void f(T, T);  // #3
    // f(1, 2);    f(1, 2.0);
    ```

<details markdown="1">
<summary>答案</summary>

`f(1, 2)`：#3 推导出 `f<int>(int, int)`，两个实参都是恒等。#1：恒等 + 浮点-整型转换；#2：整型转换 + 恒等。#3 在两个实参上都不差于 #1、#2，并且至少一处更好，所以 #3 胜出（主规则 2.1，根本不用"非模板优先"）。

`f(1, 2.0)`：#3 推导冲突（`T` 推出 `int` 与 `double`），不是候选。#1：恒等 + 恒等；#2：整型转换 + 浮点-整型转换。#1 胜出。
</details>

!!! question "2. 为什么 2.2 只在'用户定义转换的初始化'语境中使用，而不是对所有调用比较返回类型？"

<details markdown="1">
<summary>答案</summary>

普通函数调用的返回值没有"目标类型"——调用表达式的结果可能被丢弃、被传给另一个重载函数、被 `auto` 接收，标准不让重载决议依赖调用之后的语境（这与"不能只按返回类型重载"是同一个原则）。而在 [[over.match.conv]]、[[over.match.ref]] 等语境中，转换函数被调用的**唯一目的**就是产生一个特定目标类型的值，目标类型是已知的，而且转换函数的"实参"（对象实参）对所有候选都相同，必须靠"结果到目标"的转换来区分。
</details>

## 小结

!!! summary
    - `F1` 更好 ⇔ 所有实参的 ICS 都不差，且（某个实参更好，或某条决胜规则成立）。
    - 决胜规则顺序：转换结果 → 函数引用种类 → 非模板 → 偏序 → 约束 → 继承构造函数 → 非改写 → 非反转 → CTAD 四条。
    - 恰好一个比所有其他都好才算成功；"各赢一个实参"就是歧义。
    - 可以用"锦标赛 + 验证"在线性时间内找出最佳者；标准不假设"更好"的传递性。
