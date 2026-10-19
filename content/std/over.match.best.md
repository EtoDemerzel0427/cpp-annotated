---
title: 最佳可行函数
summary: 重载决议的最后一步：逐个实参比较隐式转换序列，处处不差且至少一处更好的函数胜出；全部打平时按固定顺序使用十余条决胜规则；只有一个函数胜过所有其他函数时调用才成立。
status: done
covers: over.match.best.general
related: over.match, over.match.viable, over.best.ics, over.ics.rank, temp.func.order, temp.constr.order, over.match.oper, over.match.class.deduct, topics/overload-resolution-walkthrough
tags: 重载决议
updated: 2026-10-19
---

!!! tldr
    - 可行函数 `F1` 比 `F2` 更好，要满足两点：每个实参上 `F1` 的转换都不比 `F2` 差；并且至少一个实参上更好，或者全部打平时有一条决胜规则偏向 `F1`。
    - 决胜规则只在所有实参都打平时才起作用。只要 `F1` 在一个实参上更差，它是非模板、更受约束都没有用。
    - 决胜规则依次是：转换函数结果、函数引用种类、非模板、更特殊的模板、更受约束的非模板、派生类自己的构造函数、非改写候选、非反转候选，最后四条只用于类模板实参推导。
    - 只有一个可行函数比其他所有可行函数都好时，调用才成立。两个候选各赢一个实参就是歧义，编译器不会综合打分。

## 各赢一个实参就是歧义

```cpp error
void Fcn(const int*, short);
void Fcn(int*, int);

int i;
short s = 0;

void f() {
  Fcn(&i, s);     // error: 歧义
  Fcn(&i, 1L);    // OK：Fcn(int*, int)
  Fcn(&i, 'c');   // OK：Fcn(int*, int)
}
```

这是标准的例 8。重载决议先找出所有[[g:viable-function|可行函数]]，也就是实参个数对得上、每个实参都能隐式转换成对应形参类型的函数（[[over.match.viable]]）。两个 `Fcn` 对三个调用都可行，接下来要在它们之间分出高下。

比较的对象是每个实参的[[g:implicit-conversion-sequence|隐式转换序列]]（implicit conversion sequence，ICS），即把这个实参转换成形参类型所用的一串转换（[[over.best.ics]]）。两个 ICS 谁更好由 [[over.ics.rank]] 规定。把三个调用的 ICS 列出来：

| 调用 | 实参 | `Fcn(const int*, short)` | `Fcn(int*, int)` | 这个实参上谁更好 |
|---|---|---|---|---|
| `Fcn(&i, s)` | `&i` | 限定转换 | 恒等 | 后者 |
| | `s` | 恒等 | 整型提升 | 前者 |
| `Fcn(&i, 1L)` | `&i` | 限定转换 | 恒等 | 后者 |
| | `1L` | 整型转换 | 整型转换 | 打平 |
| `Fcn(&i, 'c')` | `&i` | 限定转换 | 恒等 | 后者 |
| | `'c'` | 整型转换 | 整型提升 | 后者 |

第一个调用里两个函数各赢一个实参，没有谁处处不差，所以歧义。后两个调用里 `Fcn(int*, int)` 处处不差，且在 `&i` 上更好，所以它胜出。

`&i → int*` 胜过 `&i → const int*`，因为不做转换总比做了一次限定转换好（[[over.ics.rank#3.2.1]]）。`char → short` 不是提升，提升的目标只有 `int`、`unsigned int` 等少数类型（[[conv.prom]]），所以它比 `char → int` 差。

## 什么叫更好的函数（¶1–¶2）

¶1 标准把第 `i` 个实参转换到可行函数 `F` 的第 `i` 个形参类型所用的隐式转换序列记作 **ICSi(F)**。

这里的第 `i` 个实参要按候选函数的视角来数。成员函数多出一个隐含的对象实参，对应它的对象形参（[[over.match.funcs#2]]）。静态成员函数的这个位置不参与比较，它的 ICS 既不比任何标准转换序列好，也不比它差（[[over.best.ics#8]]）。反转的改写候选，两个实参的顺序是交换过的（[[over.match.oper]]）。

¶2 可行函数 `F1` 比 `F2` **更好**（better），条件是对所有实参 `i`，ICSi(F1) 都不比 ICSi(F2) 差，并且下列各条中有一条成立。各条按顺序检查，前一条不成立才看下一条。

!!! std
    "a viable function F1 is defined to be a *better* function than another viable function F2 if for all arguments i, ICSi(F1) is not a worse conversion sequence than ICSi(F2), and then …"

¶2.1 第一条是主规则：存在某个实参 `j`，ICSj(F1) 比 ICSj(F2) 更好。绝大多数调用在这一条就有了结果。

后面的 ¶2.2–¶2.13 是**决胜规则**（tie-breaker）：所有实参上都打平时，改看与 ICS 无关的性质。由于对所有实参都不差是前提，`F1` 只要在一个实参上更差，后面任何一条都救不了它。

## 决胜规则（¶2.2–¶2.13）

标准按 ¶2.2 到 ¶2.13 的顺序检查这些规则，本节末尾的表格按这个顺序列出。下面先讲日常代码里最常遇到的几条，再讲只在转换函数和类模板实参推导中出现的几条。

### 非模板优先，但先比转换（¶2.4）

```cpp run ok
#include <cstdio>
void f(int)                 { std::puts("f(int)"); }
template<class T> void f(T) { std::puts("f<T>(T)"); }
int main() {
  f(1);      // f(int)
  f('a');    // f<char>
  f<>(1);    // f<int>
}
```

¶2.4 `F1` 不是函数模板特化，而 `F2` 是，则 `F1` 更好。

`f(1)` 中模板推导出 `f<int>(int)`，两个函数的 ICS 都是恒等，打平，于是非模板胜出。`f('a')` 中模板推导出 `f<char>(char)`，ICS 是恒等；`f(int)` 需要 `char → int` 的整型提升。主规则 ¶2.1 已经分出了胜负，¶2.4 没有机会起作用。`f<>(1)` 写了显式模板实参列表，只有模板是候选。

模板推导出的签名通常与实参完全吻合，所以模板常常靠更好的转换胜过非模板。

### 更特殊的模板（¶2.5）

```cpp run ok
#include <concepts>
#include <cstdio>
template<class T> void g(T)  { std::puts("g(T)"); }
template<class T> void g(T*) { std::puts("g(T*)"); }
template<class T>         void h(T) { std::puts("h(T)"); }
template<std::integral T> void h(T) { std::puts("h(integral T)"); }
int main() {
  int i = 0;
  g(&i);     // g(T*)
  h(1);      // h(integral T)
  h(1.0);    // h(T)
}
```

¶2.5 `F1` 与 `F2` 都是函数模板特化，且 `F1` 的模板按 [[temp.func.order]] 的偏序规则比 `F2` 的模板[[g:more-specialized|更特殊]]，则 `F1` 更好。

`g(&i)` 中两个模板都推导出 `g(int*)`，ICS 相同；能接受 `T*` 的实参都能交给 `T`，反之不行，所以 `g(T*)` 更特殊。偏序也考虑约束：两个模板除约束外等价时，[[g:more-constrained|更受约束]]的那个更特殊（[[temp.constr.order]]），所以 `h(1)` 选受约束的版本。`h(1.0)` 中受约束的版本不满足约束，根本不是可行函数。

### 更受约束的非模板函数（¶2.6）

```cpp run ok
template <typename T = int>
struct S {
  constexpr int f() { return 1; }                        // #1
  constexpr int f(this S&) requires true { return 2; }   // #2
};
int main() {
  S<> s;
  return s.f() == 2 ? 0 : 1;   // 调用 #2
}
```

¶2.6 `F1` 与 `F2` 都是非模板函数，且 `F1` 比 `F2` 更偏序受约束（more partial-ordering-constrained，[[temp.constr.order]]），则 `F1` 更好。这个比较有前提：两个函数的非对象形参类型列表相同；如果是成员函数，它们是同一个类的直接成员，对象形参类型也相同。

例子中 #1 是普通成员函数，#2 有显式对象形参，但两者的对象形参类型都是 `S&`，可以按约束比较，#2 胜出。

非模板函数只有在模板里才能带 `requires` 子句，比如类模板的成员函数。所以这条规则主要用于类模板中按条件提供的成员函数。

### 派生类自己的构造函数优先（¶2.7）

```cpp run ok
struct A {
  A(int = 0) {}
};
struct B : A {
  using A::A;
  B() {}
};
int main() {
  B b;      // B::B()
}
```

¶2.7 `F1` 是类 `D` 的构造函数，`F2` 是 `D` 的基类 `B` 的构造函数（经 `using` 继承而来），且对所有实参，两者对应的形参类型相同，则 `F1` 更好。

`A(int = 0)` 继承下来后也能不带实参调用，与 `B()` 打平。派生类重新写了一个同样能这样调用的构造函数，用它才合理。没有这条规则，`B b;` 就会歧义。

### 手写的比较运算符优先（¶2.8–¶2.9）

C++20 起，`a < b` 的候选除了各个 `operator<`，还包括由 `operator<=>` 改写而成的 `(a <=> b) < 0`，以及交换操作数后的 `0 < (b <=> a)`。前者叫[[g:rewritten-candidate|改写候选]]，后者是参数反转的合成候选（[[over.match.oper]]）。

```cpp run ok
#include <compare>
#include <cstdio>
struct S {
  friend auto operator<=>(const S&, const S&) = default;   // #1
  friend bool operator<(const S&, const S&) {               // #2
    std::puts("#2"); return false;
  }
};
int main() { (void)(S() < S()); }   // 调用 #2
```

¶2.8 `F2` 是改写候选而 `F1` 不是，则 `F1` 更好。#1 改写出的候选与 #2 的 ICS 完全相同，手写的 #2 胜出。

```cpp run ok
#include <compare>
#include <cstdio>
using std::weak_ordering;
struct S {
  friend weak_ordering operator<=>(const S&, int) {   // #1
    std::puts("#1"); return weak_ordering::equivalent;
  }
  friend weak_ordering operator<=>(int, const S&) {   // #2
    std::puts("#2"); return weak_ordering::equivalent;
  }
};
int main() { (void)(1 < S()); }   // 调用 #2
```

¶2.9 `F1` 与 `F2` 都是改写候选，`F2` 是参数反转的合成候选而 `F1` 不是，则 `F1` 更好。`1 < S()` 可以改写成 `(1 <=> S()) < 0`，用 #2；也可以反转成 `0 < (S() <=> 1)`，用 #1。两者 ICS 相同，不反转的胜出。

这两条同样只在打平时起作用。如果普通候选和反转候选在某个实参上分出了高下，比如一个是非 const 成员函数，就到不了这里。C++20 中许多 `operator==` 歧义就是这样产生的，见 [[over.match.oper]]。

### 用户定义转换：比较转换之后的那一步（¶2.2）

```cpp error
struct A {
  A();
  operator int();
  operator double();
} a;
int   i = a;   // OK：operator int()
float x = a;   // error: 歧义
```

¶2.2 语境是用户定义转换进行的初始化（[[dcl.init]]、[[over.match.conv]]、[[over.match.ref]]），并且从 `F1` 的结果到目标类型的标准转换序列，比从 `F2` 的结果到目标类型的更好，则 `F1` 更好。

用 `a` 初始化 `int` 时，候选是两个转换函数，唯一的实参是对象 `a`，两者的 ICS 完全相同，主规则分不出高下。真正的差别在转换函数返回之后：`operator int()` 的结果无需再转换，`operator double()` 的结果还要做一次 `double → int`。这一步不属于任何实参的 ICS，所以需要单独一条规则。初始化 `float` 时，`int → float` 和 `double → float` 都是转换等级，打平，于是歧义。

普通函数调用不这样比较返回值，因为调用表达式的结果没有确定的目标类型，它可能被丢弃，也可能传给另一个函数。

### 函数引用的种类（¶2.3）

```cpp
template <class T> struct A {
  operator T&();    // #1
  operator T&&();   // #2
};
typedef int Fn();
A<Fn> a;
Fn&  lf = a;        // 调用 #1
Fn&& rf = a;        // 调用 #2
```

¶2.3 语境是用转换函数把函数类型的引用直接绑定到结果上，`F1` 返回的引用与被初始化的引用种类相同（都是左值引用或都是右值引用），而 `F2` 不是，则 `F1` 更好。

函数只有左值，而右值引用也能绑定函数左值，所以 #1、#2 对两个引用都能用。这条规则让种类一致的那个胜出，与 [[over.ics.rank#3.2.4]] 互补。

!!! impl "Clang 的偏离"
    本机 Clang 23 对 `Fn& lf = a;` 选 #1，但对 `Fn&& rf = a;` 报 "reference initialization … is ambiguous"，没有实现这条规则的后一半。按标准，`rf` 的初始化良构，调用 #2。

### 类模板实参推导专用（¶2.10–¶2.13）

写 `std::vector v{1, 2};` 时，编译器从类模板的构造函数和推导指引生成一组假想的函数模板，对它们做一次重载决议来推出 `T`。这就是类模板实参推导（CTAD，[[over.match.class.deduct]]）。下面四条只在这次假想的重载决议中使用：

| 规则 | `F1` 比 `F2` 更好，如果 |
|---|---|
| ¶2.10 | 两者都为类 `D` 生成，`F2` 来自从基类继承的构造函数而 `F1` 不是，且每个显式实参对应的形参要么都是省略号，要么类型相同 |
| ¶2.11 | `F1` 由用户写的[[g:deduction-guide\|推导指引]]生成，`F2` 不是 |
| ¶2.12 | `F1` 是[[g:copy-deduction-candidate\|拷贝推导候选]]（由 `A(A)` 推出 `A` 自身的那个候选），`F2` 不是 |
| ¶2.13 | `F1` 由非模板构造函数生成，`F2` 由构造函数模板生成 |

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

A x(1, 2, 3);       // 用 #3 推导（¶2.13）

template <class T>
A(T) -> A<T>;       // #6，不如 #5 特殊

A a(42);            // 用 #6 推出 A<int>，再用 #1 初始化
A b = a;            // 用 #5 推出 A<int>（¶2.5），再用 #2 初始化

template <class T>
A(A<T>) -> A<A<T>>; // #7，与 #5 同样特殊

A b2 = a;           // 用 #7 推出 A<A<int>>（¶2.11），再用 #1 初始化
```

生成的候选全是函数模板，所以 ¶2.4 几乎不起作用，¶2.5 的偏序往往先于 ¶2.11–¶2.13 决定结果。`b` 和 `b2` 的差别就在这里：#6 的形参 `T` 不如 #5 的 `A<T>` 特殊，偏序已经选了 #5；#7 与 #5 同样特殊，偏序打平，才轮到 ¶2.11 让推导指引胜出。

### 一览

| 顺序 | 规则 | 典型场景 |
|---|---|---|
| ¶2.1 | 某个实参的 ICS 更好 | 绝大多数调用 |
| ¶2.2 | 转换函数结果到目标的转换更好 | `int i = obj;` 在多个转换函数间选择 |
| ¶2.3 | 函数引用的种类一致 | `Fn& r = obj;` |
| ¶2.4 | 非模板胜过模板特化 | `f(int)` 与 `template f(T)` |
| ¶2.5 | 更特殊的模板（含约束） | `g(T*)` 与 `g(T)` |
| ¶2.6 | 更受约束的非模板函数 | 类模板中按条件提供的成员函数 |
| ¶2.7 | 派生类构造函数胜过继承的构造函数 | `using Base::Base;` |
| ¶2.8 | 非改写胜过改写 | 手写的 `<` 与由 `<=>` 改写的 `<` |
| ¶2.9 | 非反转胜过反转 | `x <=> y` 与反转的 `y <=> x` |
| ¶2.10–¶2.13 | CTAD 专用 | 推导指引、拷贝推导候选等 |

## 唯一的最佳者（¶3–¶4）

¶3 如果恰好有一个可行函数比其他所有可行函数都更好，它就是重载决议的结果；否则调用非良构。

两两比较 n 个函数需要 O(n²) 次。脚注 98 给出了一个线性的做法：

1. 第一遍像淘汰赛一样，维护当前胜者 `W`，依次与每个函数比较，挑战者更好时就替换 `W`。
2. 第二遍检查 `W` 是否比其他每个函数都更好。

没有成为最终 `W` 的函数 `F`，都曾在某一轮遇到一个它没能胜过的 `G`，所以 `F` 不可能比所有函数都好。最佳者如果存在，只能是 `W`，第二遍负责确认。这个论证不需要更好关系有传递性。

¶4 注 1 提醒，如果最佳可行函数要靠默认实参才可行，还有额外要求：这些默认实参不能来自多个不同作用域的声明（[[over.match.viable#2]]）。

## 实现视角

!!! impl
    - Clang 的 `isBetterOverloadCandidate` 基本按 ¶2 的顺序实现：先逐个实参比较 ICS，发现某处更差就立即返回；然后依次检查转换函数结果、非模板、偏序、约束、继承构造函数、改写与反转、CTAD 专用规则。GCC 的对应函数是 `joust`。
    - 歧义诊断会列出所有争夺最佳的候选。读诊断时先找出它们分别在哪个实参上胜出，通常就能定位问题。
    - 对 C++20 反转 `operator==` 带来的一些歧义，Clang 和 GCC 以扩展的形式选出一个函数并给出警告，见 [[over.match.oper]]。

## 历史与演进

!!! history
    - C++98 已有主规则、转换函数结果规则、非模板优先和模板偏序。
    - C++11 加入函数引用种类的规则（¶2.3）。
    - C++17 加入 CTAD 的三条规则（¶2.11–¶2.13），并按继承构造函数的新模型改写了 ¶2.7。
    - C++20 让偏序考虑约束，加入非模板函数按约束比较的规则，以及改写、反转候选的两条规则（¶2.8、¶2.9）。
    - C++23 加入继承构造函数的 CTAD 规则（¶2.10）。
    - C++23 之后的新措辞把 ¶2.6 改用更偏序受约束这个术语，明确了两个非模板函数可以按约束比较的前提。

## 常见误解

!!! pitfall "非模板优先能压过更好的转换"
    决胜规则只在打平时起作用。`f(int)` 与 `template<class T> void f(T)` 并存时，`f('a')`、`f(1L)`、`f(1.0f)` 都选模板。

!!! pitfall "更受约束能压过更好的转换"
    同理。约束只在两个地方起作用：不满足约束的函数不可行；ICS 打平时更受约束者胜出。

!!! pitfall "编译器会综合评分"
    重载决议不加权，也不计数。两个候选各在一个实参上胜出，就是歧义，哪怕其中一个在其余十个实参上都是精确匹配。

## 思考题

!!! question "思考题 1"
    下面两个调用分别选哪个函数？
    ```cpp
    void f(int, double);             // #1
    void f(long, int);               // #2
    template<class T> void f(T, T);  // #3
    // f(1, 2);    f(1, 2.0);
    ```

<details markdown="1">
<summary>答案</summary>

`f(1, 2)`：#3 推导出 `f<int>(int, int)`，两个实参都是恒等。#1 是恒等加浮点-整型转换，#2 是整型转换加恒等。#3 在两个实参上都不比 #1、#2 差，且至少一处更好，按 ¶2.1 胜出，用不到非模板优先。

`f(1, 2.0)`：#3 从两个实参推出 `int` 和 `double`，推导失败，不是候选。#1 是两个恒等，#2 是整型转换加浮点-整型转换，选 #1。（本机 Clang 23 运行结果与此一致。）
</details>

!!! question "思考题 2"
    为什么 ¶2.2 只在用户定义转换进行的初始化中比较结果到目标的转换，而普通调用不比较返回类型？

<details markdown="1">
<summary>答案</summary>

普通调用的结果没有确定的目标类型：它可能被丢弃、传给另一个重载函数，或者由 `auto` 接收。重载决议不依赖调用之后的语境，这也是不能只按返回类型重载的原因。在 [[over.match.conv]]、[[over.match.ref]] 等语境中，调用转换函数的唯一目的就是得到某个目标类型的值，目标类型已知；而所有候选的实参都是同一个对象，ICS 相同，只能靠结果到目标的转换来区分。
</details>
