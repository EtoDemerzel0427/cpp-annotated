---
title: 隐式转换序列的排序
summary: 两个隐式转换序列谁更好：先比形式（标准、用户定义、省略号），再用同一形式内的专门规则（花括号列表、标准转换的子序列与等级、引用绑定、同一个用户定义转换），最后在同等级的标准转换之间用几条细则。
status: done
papers: P0388R4, P1467R9
related: over.best.ics, over.match.best, conv, dcl.init.ref, dcl.init.list, topics/overload-resolution-walkthrough
tags: 重载决议, 转换
updated: 2026-10-19
---

!!! tldr
    - 比较两个隐式转换序列分三层：先比形式，标准转换序列胜过用户定义转换序列，后者又胜过省略号；再用同一形式内的专门规则；最后在等级相同的标准转换之间用几条细则。
    - 花括号实参转换成 `std::initializer_list` 时优先，压过同一形式内的其他规则，所以 `f({42})` 选 `f(std::initializer_list<long>)` 而不选 `f(int)`。
    - 少做一步转换更好，但数组到指针、左值到右值这类变换不计入比较，所以 `g(int)` 和 `g(const int&)` 对任何实参都分不出高下。
    - 右值优先绑定右值引用，这是移动语义的基础；两个引用都能绑定时，被引用类型 cv 更少的那个更好。
    - 两个用户定义转换序列只有用的是同一个构造函数或转换函数时才能比较；同等级的标准转换之间，不转成 `bool`、不转成 `void*`、继承层次更近的更好。

## 三层比较

```cpp run ok
#include <cstdio>
#include <string>
void g(bool)        { std::puts("g(bool)"); }
void g(std::string) { std::puts("g(std::string)"); }
void e(int)         { std::puts("e(int)"); }
void e(...)         { std::puts("e(...)"); }
void f(int)         { std::puts("f(int)"); }
void f(double)      { std::puts("f(double)"); }
struct S { operator int() const { return 0; } };
int main() {
  g("abc");   // g(bool)：第一层，标准转换胜过用户定义转换
  e(S{});     // e(int)：第一层，用户定义转换胜过省略号
  short s = 1;
  f(s);       // f(int)：同为标准转换，提升胜过转换
}
```

[[over.match.best]] 选函数时逐个实参比较[[g:implicit-conversion-sequence|隐式转换序列]]（ICS），本节规定两个 ICS 谁更好。ICS 的三种形式（标准转换序列、用户定义转换序列、省略号转换序列）和标准转换的三个等级（精确匹配、提升、转换）在 [[over.best.ics]] 中定义。

¶1 本节定义的是 ICS 之间的一个**偏序**。S1 是比 S2 **更好的转换序列**（better conversion sequence）时，S2 就是比 S1 更差的转换序列。S1 既不比 S2 好也不比 S2 差时，两者是**不可区分的**（indistinguishable）转换序列。偏序意味着很多 ICS 之间无法比较，歧义就是这样产生的。

## 第一层：比形式（¶2）

¶2 比较 ICS 的基本形式时：

- ¶2.1 标准转换序列比用户定义转换序列和省略号转换序列都好；
- ¶2.2 用户定义转换序列比省略号转换序列好。

这一层不看等级。`const char*` → `bool` 是转换等级，仍然胜过任何用户定义转换，`g("abc")` 因此选 `g(bool)`。

## 第二层：同一形式内（¶3）

¶3 形式相同的两个 ICS 是不可区分的，除非下面的规则之一适用。

### 花括号列表（¶3.1）

```cpp run ok
#include <cstdio>
#include <initializer_list>
#include <string>
#include <utility>
using std::initializer_list;
void f1(int)                     { std::puts("f1(int)"); }
void f1(initializer_list<long>)  { std::puts("f1(il<long>)"); }
void f2(std::pair<const char*, const char*>) {
  std::puts("f2(pair)");
}
void f2(initializer_list<std::string>) {
  std::puts("f2(il<string>)");
}
int main() {
  f1({42});            // f1(il<long>)
  f2({"foo", "bar"});  // f2(il<string>)
}
```

¶3.1 实参是花括号列表时，ICS 叫做列表初始化序列（[[over.ics.list]]）。列表初始化序列 L1 比 L2 好，如果：

- ¶3.1.1 L1 转换成某个 `std::initializer_list<X>`，而 L2 不是；或者，不满足这一条时，
- ¶3.1.2 L1 和 L2 都转换成元素类型相同的数组，并且 L1 初始化的元素个数少于 L2；或者个数相同，而 L2 转换成未知边界数组、L1 不是。

!!! std
    "… even if one of the other rules in this paragraph would otherwise apply."

这条规则压过 ¶3 中所有其他规则，但压不过第一层。`f1({42})` 中，`{42}` → `int` 是恒等，`{42}` → `initializer_list<long>` 是 `int` → `long` 的整型转换（取各元素转换中最差的那个），两者都是标准转换序列，第一层分不出高下。到了第二层，¶3.1.1 直接判定 `initializer_list` 胜出，不再比较等级。

这与 [[over.match.list]] 中初始化列表构造函数优先的规则一致：花括号里的内容优先被当作一串元素。函数实参也遵循同一原则，`f({1})` 和 `T x{1}` 的行为就不会相互矛盾。

数组的规则来自 C++20 的 [[P0388R4]]：

```cpp run ok
#include <cstdio>
void f(int    (&&)[] ) { std::puts("#1 int[]"); }
void f(double (&&)[] ) { std::puts("#2 double[]"); }
void f(int    (&&)[2]) { std::puts("#3 int[2]"); }
int main() {
  f({1});          // #1
  f({1.0});        // #2
  f({1.0, 2.0});   // #2
  f({1, 2});       // #3
}
```

`f({1})` 中，#1 比 #2 好，因为恒等胜过浮点-整型转换。#1 比 #3 好，因为 #3 要初始化两个元素（第二个由 `{}` 补齐），#1 只初始化一个，与实际给出的元素更吻合。`f({1, 2})` 中，#1 和 #3 都初始化两个元素，已知边界的 #3 胜出。

### 标准转换序列（¶3.2）

¶3.2 两个标准转换序列 S1、S2 按下面的顺序比较，前一条不成立才看下一条。

#### 少做一步更好（¶3.2.1）

```cpp run ok
#include <cstdio>
void f(int*)       { std::puts("f(int*)"); }
void f(const int*) { std::puts("f(const int*)"); }
int main() {
  int i = 0;
  f(&i);   // f(int*)
}
```

¶3.2.1 S1 是 S2 的真子序列，则 S1 更好。比较时按 [[over.ics.scs]] 的固定顺序排列各步，**不计左值变换**；恒等被视为任何非恒等序列的子序列。

限定转换和恒等都是精确匹配，等级相同；这条规则让什么也不做的一方胜出。

左值变换指左值到右值、数组到指针、函数到指针这三种转换。不计入它们，下面两组调用就都是歧义：

```cpp error
void f(int*);
void f(int (&)[3]);
void g(int);
void g(const int&);
void use() {
  int a[3];
  f(a);    // error: 歧义，数组到指针不计入，两边都相当于恒等
  int i = 0;
  g(i);    // error: 歧义，左值到右值不计入
  g(1);    // error: 歧义
}
```

所以对任何实参，按值接受和按 const 引用接受都分不出高下。要按左值、右值分派，应当用 `const T&` 和 `T&&` 两个重载（¶3.2.3）。

#### 等级（¶3.2.2）

¶3.2.2 S1 的等级比 S2 高；或者两者等级相同，但能用第三层（¶4）的细则区分。等级从高到低是精确匹配、提升、转换。例如 `f(int)` 和 `f(double)` 并存时，`short` 实参选 `f(int)`（提升胜过转换），`float` 实参选 `f(double)`（`float` → `double` 是提升）。

#### 右值优先绑定右值引用（¶3.2.3）

```cpp run ok
#include <cstdio>
int i;
int   f1() { return 0; }
int&& f2() { return static_cast<int&&>(i); }
int g(const int&)  { return 1; }
int g(const int&&) { return 2; }

struct A {
  A& operator<<(int) {
    std::puts("A::operator<<(int)"); return *this;
  }
  void p() &  { std::puts("p() &"); }
  void p() && { std::puts("p() &&"); }
};
A& operator<<(A&& a, char) {
  std::puts("operator<<(A&&, char)");
  return static_cast<A&>(a);
}

int main() {
  std::printf("%d %d %d\n", g(i), g(f1()), g(f2()));  // 1 2 2
  A() << 1;     // A::operator<<(int)
  A() << 'c';   // operator<<(A&&, char)
  A a;
  a << 1;       // A::operator<<(int)
  a << 'c';     // A::operator<<(int)
  A().p();      // p() &&
  a.p();        // p() &
}
```

¶3.2.3 S1 和 S2 都是引用绑定（[[dcl.init.ref]]），都不是绑定到没有引用限定符的非静态成员函数的隐式对象形参，并且 S1 把右值引用绑定到右值、S2 绑定的是左值引用，则 S1 更好。

`f(const T&)` 和 `f(T&&)` 并存时右值实参选后者，移动语义就靠这一条。`f2()` 返回 `int&&`，调用表达式是 xvalue，也是右值，所以同样选 `g(const int&&)`。

成员函数的例外要看 `A() << 1`：

| 调用 | `A::operator<<(int)` | `operator<<(A&&, char)` | 结果 |
|---|---|---|---|
| `A() << 1` | 对象：`A&` 绑定右值（特许）；`1`：恒等 | 对象：`A&&` 绑定右值；`1` → `char`：整型转换 | 成员 |
| `A() << 'c'` | 对象：同上；`'c'` → `int`：提升 | 对象：同上；`'c'`：恒等 | 非成员 |
| `a << 1`、`a << 'c'` | 可行 | 不可行，`A&&` 不能绑定左值 | 成员 |

没有引用限定符的成员函数也能在右值上调用，这时它的隐式对象形参 `A&` 被特许绑定右值（[[over.match.funcs#5]]）。如果 ¶3.2.3 适用于这种形参，`A() << 1` 的第一个实参上非成员更好，第二个实参上成员更好，就会歧义。这个例外保证了：给 C++11 之前写成的类加上一个接受右值引用的非成员重载，不会让原有调用变成歧义。带引用限定符的 `p() &`、`p() &&` 不受例外影响，照常按 ¶3.2.3 区分。

#### 函数左值优先绑定左值引用（¶3.2.4）

```cpp run ok
int f(void(&)())  { return 1; }   // #1
int f(void(&&)()) { return 2; }   // #2
void g() {}
int main() { return f(g) == 1 ? 0 : 1; }   // 调用 #1
```

¶3.2.4 S1 和 S2 都是引用绑定，S1 把左值引用绑定到函数左值，S2 把右值引用绑定到函数左值，则 S1 更好。函数只有左值，但右值引用也能绑定它（[[over.ics.ref#3]]），这条规则让结果符合函数是左值这一事实。

#### 加的 cv 更少更好（¶3.2.5）

```cpp
int f(const volatile int*);
int f(const int*);
int i;
int j = f(&i);   // f(const int*)

int g(const int*);
int g(const volatile int* const&);
int* p;
int k = g(p);    // 按标准：g(const int*)
```

¶3.2.5 S1 和 S2 只在限定转换上不同，分别得到[[g:similar-types|相似]]但不相同的类型 T1、T2（引用绑定被视为得到被引用类型去掉 cv 的版本），并且 `const T2` 与 T1 引用兼容（[[dcl.init.ref]]），则 S1 更好。直观地说，两边都要加 cv 时，加得少的那个更好。

`g(p)` 中，`g(const volatile int* const&)` 是直接绑定，按 [[over.ics.ref#1.4]] 也是一次限定转换，得到的类型按括号里的规定是 `const volatile int*`。它比 `const int*` 多加了 `volatile`，所以 `g(const int*)` 更好。

!!! impl "Clang 的偏离"
    本机 Clang 23 对 `f(&i)` 的处理与标准一致，但对 `g(p)` 报 "call to 'g' is ambiguous"。按标准（[over.ics.rank] 例 5），应调用 `g(const int*)`。

#### 被引用类型的 cv 更少更好（¶3.2.6）

```cpp
int f(const int&);
int f(int&);
int g(const int&);
int g(int);
struct X {
  void f() const;
  void f();
};
int h(int (&)[]);
int h(int (&)[1]);
void use(const X& a, X b) {
  int i = 0;
  f(i);      // f(int&)
  g(i);      // error: 歧义，g(int) 不是引用绑定
  a.f();     // X::f() const：唯一可行
  b.f();     // X::f()
  int arr[1];
  h(arr);    // 按标准：h(int (&)[1])
}
```

¶3.2.6 S1 和 S2 分别绑定到 T1 的引用和 T2 的引用，T1、T2 不同，并且 T2 与 T1 引用兼容，则 S1 更好。也就是说，被引用类型 cv 更少的更好，数组边界已知的更好。

`b.f()` 说明了成员函数 const 重载的工作方式：隐式对象形参分别是 `X&` 和 `const X&`，按这条规则非 const 版本更好；const 对象只能调用 const 版本。

!!! impl "Clang 的偏离"
    本机 Clang 23 对 `h(arr)` 报歧义。按标准（[over.ics.rank] 例 6），`int (&)[1]` 更好。这部分规则随 C++20 的 [[P0388R4]] 引入。其余各行 Clang 与标准一致。

#### 同一引用类型、不同来源（¶3.2.7）

```cpp
struct Z {};
struct A {
  operator Z&();
  operator const Z&();    // #1
};
struct B {
  operator Z();
  operator const Z&&();   // #2
};
const Z& r1 = A();        // OK：用 #1
const Z&& r2 = B();       // OK：用 #2
```

¶3.2.7 S1 和 S2 绑定同一种引用类型 "reference to `T`"，源类型分别是 V1、V2，并且 `V1*` 到 `T*` 的标准转换序列比 `V2*` 到 `T*` 的好，则 S1 更好。

源类型不同的情况只出现在比较用户定义转换之后的第二段时（[[over.match.best#2.2]]）。`r1` 的两个转换函数结果都能绑定 `const Z&`；把问题换成指针，`const Z*` → `const Z*` 是恒等，`Z*` → `const Z*` 是限定转换，#1 更好。这样引用的比较就复用了 ¶3.2.1 和 ¶3.2.5 对限定转换的规则。

!!! impl "Clang 的偏离"
    本机 Clang 23 对 `r1`、`r2` 都报 "reference initialization … is ambiguous"，尚未实现这条规则。

### 用户定义转换序列（¶3.3）

```cpp run ok
#include <cstdio>
struct A {
  operator short() { return 0; }
} a;
int f(int)   { return 1; }
int f(float) { return 2; }
int main() {
  std::printf("%d\n", f(a));   // 1
}
```

¶3.3 用户定义转换序列 U1 比 U2 好，前提是两者用的是同一个转换函数或构造函数（或者在聚合初始化中初始化同一个类），并且 U1 的第二段标准转换比 U2 的好。上例两边都经过 `operator short()`，`short` → `int` 是提升，`short` → `float` 是转换，`f(int)` 胜出。

用的不是同一个转换时，两个序列不可比较：

```cpp error
struct C { C(int); };
struct D { D(double); };
void f(C);
void f(D);
void use() {
  f(1);   // error: 歧义
}
```

`int` → `int` 明显比 `int` → `double` 匹配得好，但那是第一段的差别，本条只比较第二段，而且只在同一个转换之间比较。

## 第三层：同等级的标准转换（¶4）

¶4 标准转换序列按等级排序：精确匹配好于提升，提升好于转换。等级相同的两个序列不可区分，除非下列规则之一适用。

### 不转成 `bool`（¶4.1）

```cpp run ok
#include <cstdio>
void h(bool)  { std::puts("h(bool)"); }
void h(void*) { std::puts("h(void*)"); }
int main() {
  int* p = nullptr;
  h(p);   // h(void*)
}
```

¶4.1 不把指针或成员指针转换成 `bool` 的转换，比转换成 `bool` 的好。`int*` → `void*` 和 `int*` → `bool` 都是转换等级，这条规则让前者胜出。指针转成 `bool` 丢失的信息最多；C++20 起，它在花括号初始化中也算窄化。

### 枚举提升到底层类型（¶4.2）

```cpp run ok
#include <cstdio>
enum E : short { e };
int g(short) { return 1; }
int g(int)   { return 2; }
int main() { std::printf("%d\n", g(e)); }   // 1
```

¶4.2 底层类型固定的枚举，提升到底层类型比提升到底层类型的提升类型好（两者不同时）。按 [[conv.prom#4]]，`E` → `short` 和 `E` → `int` 都是整型提升，没有这条规则就会歧义。

### 等级相同的浮点类型（¶4.3）{{c++23}}

```cpp
#include <stdfloat>
int f(std::float32_t);
int f(std::float64_t);
int f(long long);
float x;
std::float16_t y;
int i = f(x);   // 在 float 与 float32_t 转换等级相等的实现上，调用 f(std::float32_t)
int j = f(y);   // error: 歧义，没有与 float16_t 等级相等的候选
```

¶4.3 浮点类型 FP1 与浮点类型 FP2 之间的转换（任一方向），比同方向上 FP1 与算术类型 T3 之间的转换好，条件是：

- ¶4.3.1 FP1 与 FP2 的[[g:floating-point-conversion-rank|浮点转换等级]]相等（[[conv.rank]]），并且
- ¶4.3.2 T3 不是浮点类型；或者 T3 是等级与 FP1 不等的浮点类型；或者 FP2 的浮点转换子等级高于 T3。

C++23 引入扩展浮点类型（[[P1467R9]]）时加入了这条规则。`float` 到 `std::float32_t`、`std::float64_t`、`long long` 都是转换等级，这条规则让格式相同的 `std::float32_t` 胜出。本机 libc++ 还没有 `<stdfloat>`，这个例子没有经过编译验证。

### 到 `void*` 更差（¶4.4）

¶4.4 类 `B` 直接或间接派生自 `A` 时，`B*` → `A*` 比 `B*` → `void*` 好，`A*` → `void*` 比 `B*` → `void*` 好。所以 `v(void*)` 和 `v(A*)` 并存时，`B*` 实参选 `v(A*)`。

### 继承层次更近（¶4.5）

```cpp run ok
#include <cstdio>
struct A { int m; };
struct B : A {};
struct C : B {};
int f(A*) { return 1; }
int f(B*) { return 2; }
int g(A)  { return 1; }
int g(B)  { return 2; }
int h(int B::*) { return 1; }
int h(int C::*) { return 2; }
int main() {
  C c;
  std::printf("%d %d %d\n", f(&c), g(c), h(&A::m));   // 2 2 1
}
```

¶4.5 `B` 派生自 `A`、`C` 派生自 `B`（直接或间接）时，离得近的转换更好：

| 规则 | 更好 | 更差 | 比较的是 |
|---|---|---|---|
| ¶4.5.1 | `C*` → `B*` | `C*` → `A*` | 同一来源，不同目标 |
| ¶4.5.2 | `A::*` → `B::*` | `A::*` → `C::*` | 同上，成员指针（方向从基类到派生类） |
| ¶4.5.3 | `C` → `B` | `C` → `A` | 同上，类对象 |
| ¶4.5.4 | `B*` → `A*` | `C*` → `A*` | 不同来源，同一目标 |
| ¶4.5.5 | `B::*` → `C::*` | `A::*` → `C::*` | 同上，成员指针 |
| ¶4.5.6 | `B` → `A` | `C` → `A` | 同上，类对象 |

注 1 指出，来源不同的情况（¶4.5.4–¶4.5.6）只出现在比较用户定义转换之后的第二段时（[[over.match.best#2.2]]），例如一个类同时有 `operator B()` 和 `operator C()`，用它初始化 `A` 时选 `operator B()`。其他场合来源相同、目标不同，适用 ¶4.5.1–¶4.5.3。

## 全部规则一览

```text
比较同一实参的两个 ICS：S1 与 S2
├─ 形式不同：标准 > 用户定义 > 省略号                         ¶2
├─ 都是花括号列表：initializer_list 优先；数组元素少、边界已知优先   ¶3.1
├─ 都是标准转换：
│    ¶3.2.1 真子序列（不计左值变换）
│    ¶3.2.2 等级；等级相同再看 ¶4：
│             不转 bool / 枚举到底层类型 / 同等级浮点 / 不转 void* / 继承层次更近
│    ¶3.2.3 右值绑定右值引用（无引用限定符的隐式对象形参除外）
│    ¶3.2.4 函数左值绑定左值引用
│    ¶3.2.5 限定转换加的 cv 更少
│    ¶3.2.6 被引用类型 cv 更少、数组边界已知
│    ¶3.2.7 同一引用类型，来源的指针转换更好
├─ 都是用户定义转换：同一个转换才比较第二段，否则不可区分        ¶3.3
└─ 其他：不可区分
```

## 实现视角

!!! impl
    - Clang 的 `CompareImplicitConversionSequences`、`CompareStandardConversionSequences`、`CompareQualificationConversions`、`CompareDerivedToBaseConversions` 基本是本节的逐段实现，读这几个函数可以检验自己的理解。
    - 本页有三处 Clang 23 与标准不一致：¶3.2.5 中引用一侧的限定转换、¶3.2.6 的数组边界、¶3.2.7。它们都是标准近年才加入或修订的规则。
    - 这些规则只决定调用哪个函数，没有运行时开销。

## 历史与演进

!!! history
    - C++98 已有三层结构、真子序列、等级、cv 更少、继承层次距离和指针转 `bool` 更差等规则。
    - C++11 的右值引用带来 ¶3.2.3（含隐式对象形参的例外）和 ¶3.2.4，列表初始化带来 ¶3.1.1，底层类型固定的枚举带来 ¶4.2。
    - C++20 的 [[P0388R4]] 加入数组的列表初始化排序（¶3.1.2）和未知边界数组的引用绑定比较。
    - C++23 的 [[P1467R9]] 加入扩展浮点类型的规则 ¶4.3。
    - C++23 之后的新措辞用相似类型和引用兼容重新表述了 ¶3.2.5，并加入 ¶3.2.7。

## 常见误解

!!! pitfall "`initializer_list` 只在构造函数里优先"
    ¶3.1.1 对普通函数同样适用：`f(int)` 和 `f(std::initializer_list<long>)` 并存时，`f({42})` 选后者。

!!! pitfall "编译器会比较两个转换构造函数谁的输入更匹配"
    不同的用户定义转换之间不比较第一段，只要都可行就是歧义（¶3.3）。

!!! pitfall "`bool` 形参是安全的兜底"
    指针、字符串字面量、成员指针都能经标准转换变成 `bool`，而标准转换胜过任何用户定义转换（¶2）。

## 思考题

!!! question "思考题 1"
    解释每个调用的结果。
    ```cpp
    #include <string_view>
    void f(long);           void f(double);           // f(1)
    void g(unsigned char);  void g(int);              // g('a')
    void h(const char*);    void h(std::string_view); // h("x")
    void k(int&&);          void k(const int&);       // int x; k(x); k(1);
    ```

<details markdown="1">
<summary>答案</summary>

- `f(1)`：`int` → `long` 是整型转换，`int` → `double` 是浮点-整型转换，都是转换等级，¶4 没有能区分它们的规则，歧义。
- `g('a')`：`char` → `int` 是整型提升，`char` → `unsigned char` 是整型转换，选 `g(int)`。
- `h("x")`：数组到指针是标准转换，到 `std::string_view` 要调用构造函数，是用户定义转换，选 `h(const char*)`。
- `k(x)`：`int&&` 不能绑定左值，只有 `k(const int&)` 可行。`k(1)`：两个都可行，按 ¶3.2.3 右值绑定右值引用更好，选 `k(int&&)`。
</details>

!!! question "思考题 2"
    如果去掉 ¶3.2.3 中关于隐式对象形参的例外，标准例子中哪个调用的结果会改变？

<details markdown="1">
<summary>答案</summary>

`A() << 1` 会变成歧义。非成员 `operator<<(A&&, char)` 在第一个实参上更好（右值绑定右值引用），成员 `A::operator<<(int)` 在第二个实参上更好（恒等胜过整型转换），两者各赢一个实参。`A() << 'c'` 不受影响，非成员在第二个实参上已经更好，第一个实参又不更差。
</details>
