---
title: 隐式转换序列的排序
summary: 什么叫一个隐式转换序列更好：标准 > 用户定义 > 省略号；同为标准转换时比真子序列、等级、引用绑定的左右值与 cv、限定转换；同等级时比指针到 bool、枚举提升、浮点等级、派生层次距离；以及列表初始化序列的专门规则。
status: draft
papers: P0388R4, P1467R9
related: over.best.ics, over.match.best, conv, dcl.init.ref, dcl.init.list
tags: 重载决议, 转换
updated: 2026-10-17
---

[[over.match.best]] 的主规则说"某个实参上 ICS 更好"，本节给出的就是更好的定义。它是整个重载决议中条款最密集的一节：一张三层的比较表，外加十几条细则。不过每条细则背后都有清楚的道理，比如更少的转换更好、更精确的绑定更好、离得更近的基类更好。本页为每一条都配了一个例子。

## 术语（¶1）

¶1 本节定义 ICS 上的一个**偏序**，它基于更好的转换序列（better conversion sequence）与更好的转换（better conversion）两个关系。若 S1 比 S2 更好，则 S2 是比 S1 更差（worse）的转换序列。若 S1 既不比 S2 好也不比 S2 差，二者是**不可区分的**（indistinguishable）转换序列。

这是偏序而不是全序：很多 ICS 之间无法比较，这正是歧义的来源。

## 第一层：三种形式之间（¶2）

¶2 比较 ICS 的基本形式（[[over.best.ics]]）时：

- ¶2.1 标准转换序列优于用户定义转换序列和省略号转换序列；
- ¶2.2 用户定义转换序列优于省略号转换序列。

这一层只做粗略的分档，**不看等级**：即使标准转换序列是 Conversion 等级（如 `const char* → bool`），也优于任何用户定义转换序列（如 `const char* → std::string`）。

```cpp run ok
#include <string>
#include <cstdio>
void g(bool)        { std::puts("g(bool)"); }
void g(std::string) { std::puts("g(std::string)"); }
void e(int)         { std::puts("e(int)"); }
void e(...)         { std::puts("e(...)"); }
struct S { operator int() const { return 0; } };
int main() {
  g("abc");    // g(bool)：数组到指针 + 布尔转换（标准，Conversion 等级）> 用户定义转换
  e(S{});      // e(int)：用户定义转换 > 省略号
}
```

## 第二层：同种形式之间（¶3）

¶3 两个同种形式的 ICS 是不可区分的，除非下列规则之一适用。

### ¶3.1 列表初始化序列

¶3.1 列表初始化序列 L1 优于 L2，若：

- ¶3.1.1 L1 转换到某个 `std::initializer_list<X>`，而 L2 不是；或者若不是这样，
- ¶3.1.2 L1 与 L2 都转换到同一元素类型的数组，且 L1 初始化的元素个数 n1 少于 L2 的 n2；或 n1 = n2 且 L2 转换到未知边界数组而 L1 不是。

!!! std
    "… even if one of the other rules in this paragraph would otherwise apply."

    即使本段其他规则本来会适用，也以 3.1 为准。

这句话的效力很强：`initializer_list` 优先，压过本段所有其他的同形式比较规则（但不压过第一层的标准转换优于用户定义转换）。

```cpp run ok
#include <initializer_list>
#include <string>
#include <utility>
#include <cstdio>
void f1(int)                              { std::puts("f1(int)"); }              // #1
void f1(std::initializer_list<long>)      { std::puts("f1(il<long>)"); }         // #2
void f2(std::pair<const char*, const char*>) { std::puts("f2(pair)"); }          // #3
void f2(std::initializer_list<std::string>)  { std::puts("f2(il<string>)"); }    // #4
int main() {
  f1({42});            // #2：{42}→int 是恒等，{42}→initializer_list<long> 是整型转换——但 3.1.1 优先
  f2({"foo","bar"});   // #4：两者都是用户定义转换，3.1.1 让 initializer_list 胜出
}
```

`f1({42})` 的结果尤其出人意料：`{42} → int` 按 [[over.ics.list#10]] 是与 `int → int` 相同的恒等转换，看起来稳操胜券。但 3.1.1 规定，只要一边是 `initializer_list`、另一边不是，就直接判定，不看等级。（注意二者都是标准转换序列：`initializer_list<long>` 的 ICS 按 [[over.ics.list#5]] 是最差的元素转换，即 `int → long`，属于标准转换。如果一边是标准转换、一边是用户定义转换，第一层 ¶2 已经决定了结果，轮不到 3.1。）

为什么这样设计？这与 [[over.match.list]] 的两阶段规则一脉相承：花括号里的内容优先当作序列的元素。函数形参的重载决议也遵循同一原则，使 `f({1})` 与 `T x{1}` 的行为保持一致。

数组规则（C++20，[[P0388R4]]）：

```cpp run ok
#include <cstdio>
void f(int    (&&)[] ) { std::puts("#1 int[]"); }
void f(double (&&)[] ) { std::puts("#2 double[]"); }
void f(int    (&&)[2]) { std::puts("#3 int[2]"); }
int main() {
  f({1});          // #1：比 #2 好（恒等 vs 浮点-整型转换）；比 #3 好（1 个元素 < 2 个元素）
  f({1.0});        // #2：恒等优于浮点-整型转换（#3 的 n=2 > 1，#1 是转换）
  f({1.0, 2.0});   // #2：恒等优于浮点-整型转换
  f({1, 2});       // #3：与 #1 相比，已知边界优于未知边界；与 #2 相比，恒等优于转换
}
```

`f({1})` 对 #3 的比较：#3 需要初始化 2 个元素（第二个由 `{}` 初始化），而 #1 只初始化 1 个。元素更少者更好，意思是它与实际给出的元素更吻合。

### ¶3.2 标准转换序列

¶3.2 标准转换序列 S1 优于 S2，若满足以下条件之一（按顺序检查，前一条不成立才看下一条）：

#### 3.2.1 真子序列

S1 是 S2 的**真子序列**（按 [[over.ics.scs]] 的规范形式比较，排除任何左值变换；恒等转换序列视为任何非恒等序列的子序列）。

```cpp run ok
#include <cstdio>
void f(int*)       { std::puts("f(int*)"); }
void f(const int*) { std::puts("f(const int*)"); }
int main() {
  int i = 0;
  f(&i);    // f(int*)：恒等是"限定转换"的真子序列，尽管二者都是 Exact Match 等级
}
```

这条规则弥补了等级的不足：限定调整是 Exact Match，与恒等同等级，但做了一次转换总是比不做差。

排除左值变换则意味着，数组到指针、函数到指针、左值到右值转换都不计入比较。

```cpp
void f(int*);
void f(int (&)[3]);
void g(int);
void g(const int&);
void use() {
  int a[3];
  f(a);    // error: 歧义——数组到指针是左值变换，不计入比较；两者都相当于恒等
  int i = 0;
  g(i);    // error: 歧义——左值到右值不计入；g(int) 与 g(const int&) 都是恒等
}
```

`g(int)` 与 `g(const int&)` 之间的歧义是一个常见结论：对左值实参而言，按值与按 const 引用**不可区分**。（若实参是右值，也同样歧义。）

#### 3.2.2 等级

S1 的等级优于 S2；或二者等级相同，但可以按下文第 4 段（第三层）的规则区分。

```cpp run ok
#include <cstdio>
void f(int)    { std::puts("f(int)"); }
void f(double) { std::puts("f(double)"); }
int main() {
  short s = 1;
  float x = 1;
  f(s);     // f(int)：Promotion（short→int）优于 Conversion（short→double）
  f(x);     // f(double)：Promotion（float→double）优于 Conversion（float→int）
  f('a');   // f(int)
}
```

#### 3.2.3 右值优先绑定右值引用

S1 与 S2 都包含引用绑定（[[dcl.init.ref]]），且都不指向没有 ref-qualifier 的非静态成员函数的隐式对象形参，并且 S1 把右值引用绑定到右值，S2 绑定左值引用。

移动语义正是建立在这条规则上：`f(const T&)` 与 `f(T&&)` 并存时，右值实参选 `T&&`。

```cpp run ok
#include <cstdio>
int i;
int  f1() { return 0; }
int&& f2() { return static_cast<int&&>(i); }
int g(const int&)  { return 1; }
int g(const int&&) { return 2; }

struct A {
  A& operator<<(int) { std::puts("A::operator<<(int)"); return *this; }
  void p() &  { std::puts("p() &"); }
  void p() && { std::puts("p() &&"); }
};
A& operator<<(A&& a, char) { std::puts("operator<<(A&&, char)"); return static_cast<A&>(a); }

int main() {
  std::printf("%d %d %d\n", g(i), g(f1()), g(f2()));   // 1 2 2
  A() << 1;     // A::operator<<(int)
  A() << 'c';   // operator<<(A&&, char)
  A a;
  a << 1;       // A::operator<<(int)
  a << 'c';     // A::operator<<(int)
  A().p();      // p() &&
  a.p();        // p() &
}
```

逐个看 `operator<<` 的四个调用：

| 调用 | `A::operator<<(int)`（隐式对象形参 `A&`，无 ref-qualifier） | `operator<<(A&&, char)` | 结果 |
|---|---|---|---|
| `A() << 1` | 对象：恒等（特许绑定右值）；`1`：恒等 | `A()`：恒等（右值引用绑右值）；`1→char`：整型转换 | 成员（第二实参更好；第一实参因 3.2.3 的例外而不可区分） |
| `A() << 'c'` | 对象：恒等；`'c'→int`：提升 | `A()`：恒等；`'c'`：恒等 | 非成员（第二实参更好） |
| `a << 1` | 恒等；恒等 | 不可行（`A&&` 不能绑左值） | 成员 |
| `a << 'c'` | 恒等；提升 | 不可行 | 成员 |

`A() << 1` 是理解 3.2.3 例外的关键。如果没有不指向无 ref-qualifier 的隐式对象形参这个例外，第一实参上非成员（`A&&` 绑右值）会比成员（`A&` 绑右值）更好，两个候选各赢一个实参，因而歧义。有了这个例外，C++11 之前的代码（成员函数不区分左右值）不会因为新增的右值引用重载而突然出现歧义。而有 ref-qualifier 的 `p() &`/`p() &&` 不受例外影响，正常按 3.2.3 区分。

#### 3.2.4 函数左值优先绑定左值引用

S1 与 S2 都包含引用绑定，S1 把左值引用绑定到函数类型的左值，S2 把右值引用绑定到函数类型的左值。

```cpp run ok
int f(void(&)())  { return 1; }   // #1
int f(void(&&)()) { return 2; }   // #2
void g() {}
int main() { return f(g) == 1 ? 0 : 1; }   // #1
```

函数只有左值，但右值引用也能绑定它（[[over.ics.ref#3]]）。这条规则让结果符合函数是左值这一直觉。

#### 3.2.5 限定转换：cv 更少者优先

S1 与 S2 仅在限定转换上不同，分别产生相似的类型 T1 与 T2（引用绑定视为产生被引用类型的 cv 非限定版本），T1 与 T2 不同，且 `const T2` 与 T1 引用兼容（[[dcl.init.ref]]）。

直观地说，两个都要加 cv 时，加得少的那个更好。

```cpp nocheck
int f(const volatile int*);
int f(const int*);
int g(const int*);
int g(const volatile int* const&);
void use() {
  int i;
  int j = f(&i);     // f(const int*)：int* → const int* 比 → const volatile int* 少加了 volatile
  int* p = nullptr;
  int k = g(p);      // 标准：g(const int*)
}
```

`g(p)` 的比较对象：`g(const int*)` 的 ICS 是限定转换 `int* → const int*`；`g(const volatile int* const&)` 的 ICS 是直接引用绑定，按 [[over.ics.ref#1.4]] 也是限定转换，产生（按引用绑定视为产生被引用类型的 cv 非限定版本的规定）`const volatile int*`。T1 = `const int*`，T2 = `const volatile int*`，`const T2` 与 T1 引用兼容，所以 S1 更好。

!!! impl "Clang 的偏离"
    Clang 23 正确处理 `f(&i)`，但对 `g(p)` 报 "call to 'g' is ambiguous"，它没有把直接绑定 `const volatile int* const&` 的那一侧视为产生 `const volatile int*` 的限定转换来比较。按标准（这是 [over.ics.rank] 的例 5），应调用 `g(const int*)`。

#### 3.2.6 引用绑定：cv 更少者优先

S1 与 S2 分别绑定到 T1 的引用与到 T2 的引用，T1 与 T2 不同，且 T2 与 T1 引用兼容。也就是说，**被引用类型 cv 更少的那个更好**（以及数组边界更具体的那个更好）。

```cpp nocheck
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
  int j = f(i);    // f(int&)：int& 比 const int& 少 const
  int k = g(i);    // error: 歧义——g(int) 不是引用绑定，3.2.6 不适用
  a.f();           // X::f() const：唯一可行
  b.f();           // X::f()：隐式对象形参 X& 优于 const X&
  int arr[1];
  h(arr);          // 标准：h(int (&)[1])——int[1] 与 int[] 引用兼容，反之不成立
}
```

`b.f()` 说明了这条规则对成员函数 const 重载的意义：const 对象只能调用 const 版本，非 const 对象优先调用非 const 版本，后者正是靠 3.2.6 比较隐式对象形参得出的。

!!! impl "Clang 的偏离"
    `h(arr)` 在 Clang 23 中报歧义（`int(&)[]` 与 `int(&)[1]`）。按标准（[over.ics.rank] 例 6），`int (&)[1]` 更好。这部分规则与 C++20 的 [[P0388R4]] 同时引入。上面代码块中其余各行与 Clang 一致。

#### 3.2.7 同一引用类型，不同源类型（用户定义转换的第二步）

S1 与 S2 绑定同一个引用类型"到 T 的引用"，源类型分别为 V1、V2，且从 `V1*` 到 `T*` 的标准转换序列优于从 `V2*` 到 `T*` 的。

只有在比较用户定义转换的第二 SCS 时（[[over.match.best#2.2]]），才可能出现不同的源类型。这条规则处理多个转换函数都能产生可绑定到 `const Z&` 的结果的情形：

```cpp nocheck
struct Z {};
struct A {
  operator Z&();
  operator const Z&();   // #1
};
struct B {
  operator Z();
  operator const Z&&();  // #2
};
const Z& r1 = A();       // OK：用 #1——const Z* → const Z* 是恒等，优于 Z* → const Z* 的限定转换
const Z&& r2 = B();      // OK：用 #2
```

把引用的比较转化为指针转换的比较是一个巧妙的做法，它复用了 3.2.1/3.2.5 对限定转换的全部规则。

!!! impl "Clang 的偏离"
    截至写作时，Clang 23 对 `r1`、`r2` 都报 "reference initialization … is ambiguous"，尚未实现 3.2.7（这是较新加入标准的规则）。

### ¶3.3 用户定义转换序列

¶3.3 用户定义转换序列 U1 优于 U2，若它们包含同一个用户定义转换函数或构造函数（或在聚合初始化中初始化同一个类），且 U1 的第二 SCS 优于 U2 的。

```cpp run ok
#include <cstdio>
struct A {
  operator short() { return 0; }
} a;
int f(int)   { return 1; }
int f(float) { return 2; }
int main() {
  std::printf("%d\n", f(a));   // 1：都经 operator short()；short→int 是提升，short→float 是转换
}
```

不同的用户定义转换之间**永远不可比较**：

```cpp
struct C { C(int); };
struct D { D(double); };
void f(C);
void f(D);
void use() {
  f(1);     // error: 歧义——C(int) 与 D(double) 是不同的用户定义转换，无法比较（即使 int→int 优于 int→double）
}
```

只比较同一个转换这一限制意味着，两个不同类的转换构造函数之间，无论初始 SCS 差别多大，都是歧义。注意比较的是第二 SCS 而不是第一个，初始 SCS 的差异（这里是 `int → int` 与 `int → double`）不予考虑。

## 第三层：同等级标准转换之间（¶4）

¶4 标准转换序列按等级排序：Exact Match 优于 Promotion，Promotion 优于 Conversion。等级相同的两个序列不可区分，除非下列规则之一适用：

### 4.1 不转换为 bool 者更好

不把指针或成员指针转换为 `bool` 的转换，优于把它们转换为 `bool` 的。

```cpp run ok
#include <cstdio>
void h(bool)  { std::puts("h(bool)"); }
void h(void*) { std::puts("h(void*)"); }
int main() {
  int* p = nullptr;
  h(p);      // h(void*)：int*→void* 与 int*→bool 都是 Conversion，4.1 决胜
}
```

指针到 `bool` 是丢失信息最多的转换。C++20 起（经缺陷报告）它在列表初始化中还被视为窄化转换。

### 4.2 固定底层类型的枚举：提升到底层类型更好

把底层类型固定的枚举提升到其底层类型，优于提升到提升后的底层类型（若二者不同）。

```cpp run ok
#include <cstdio>
enum E : short { e };
int g(short) { return 1; }
int g(int)   { return 2; }
int main() { std::printf("%d\n", g(e)); }   // 1：E→short 与 E→int 都是整型提升（[conv.prom]/4），前者更好
```

按 [[conv.prom#4]]，固定底层类型的枚举既可以提升到底层类型，也可以提升到底层类型的提升类型，两者都是 Promotion。没有 4.2 就会歧义。

### 4.3 扩展浮点类型 {{c++23}}

在浮点类型 FP1 与 FP2 之间（任一方向）的转换，优于同方向在 FP1 与算术类型 T3 之间的转换，若：

- 4.3.1 FP1 的浮点转换等级（[[conv.rank]]）与 FP2 相等，且
- 4.3.2 T3 不是浮点类型；或 T3 是等级不等于 FP1 的浮点类型；或 FP2 的浮点转换子等级高于 T3 的。

这是 C++23 引入扩展浮点类型（`std::float16_t`、`std::float32_t`、`std::bfloat16_t` 等，[[P1467R9]]）时加入的规则：

```cpp nocheck
#include <stdfloat>
int f(std::float32_t);
int f(std::float64_t);
int f(long long);
float x;
std::float16_t y;
int i = f(x);    // 在 float 与 std::float32_t 转换等级相等的实现上，调用 f(std::float32_t)
int j = f(y);    // error: 歧义——没有与 float16_t 等级相等的候选
```

直观地说，名字不同而格式相同的浮点类型之间的转换最好。`float → std::float32_t`（同等级，不同类型）是浮点转换（Conversion），`float → std::float64_t` 也是 Conversion，`float → long long` 也是 Conversion；4.3 让等级相等者胜出。

（本机 libc++ 尚未提供 `<stdfloat>`，此例未经编译验证。）

### 4.4 指针转换：到 void* 更差

若类 B 直接或间接派生自 A：`B* → A*` 优于 `B* → void*`；`A* → void*` 优于 `B* → void*`。

```cpp run ok
#include <cstdio>
struct A {}; struct B : A {};
int v(void*) { return 1; }
int v(A*)    { return 2; }
int main() {
  B* pb = nullptr;
  std::printf("%d\n", v(pb));   // 2：B*→A* 优于 B*→void*
}
```

### 4.5 派生层次：离得越近越好

若 B 派生自 A、C 派生自 B（均可直接或间接）：

| 规则 | 更好 | 更差 | 场景 |
|---|---|---|---|
| 4.5.1 | `C* → B*` | `C* → A*` | 同源，比目标 |
| 4.5.2 | `A::* → B::*` | `A::* → C::*` | 成员指针（方向相反：从基到派生） |
| 4.5.3 | `C → B` | `C → A` | 类对象（派生到基类） |
| 4.5.4 | `B* → A*` | `C* → A*` | 同目标，比源 |
| 4.5.5 | `B::* → C::*` | `A::* → C::*` | 同目标，比源（成员指针） |
| 4.5.6 | `B → A` | `C → A` | 同目标，比源（类对象） |

```cpp run ok
#include <cstdio>
struct A { int m; }; struct B : A {}; struct C : B {};
int f(A*) { return 1; } int f(B*) { return 2; }
int g(A)  { return 1; } int g(B)  { return 2; }
int h(int B::*) { return 1; } int h(int C::*) { return 2; }
struct X {
  operator B() { return {}; }
  operator C() { return {}; }
};
int main() {
  C c;
  C* pc = &c;
  std::printf("%d %d %d\n", f(pc), g(c), h(&A::m));   // 2 2 1：4.5.1、4.5.3、4.5.2
  A a = X();   // 用 operator B()：4.5.6——第二 SCS 中 B→A 优于 C→A
  (void)a;
}
```

注 1 指出：只有在比较初始化中用户定义转换的第二 SCS 时（[[over.match.best#2.2]]），被比较的转换序列才会有不同的源类型（4.5.4–4.5.6 适用的情形）；其他场合源类型相同、目标类型不同（4.5.1–4.5.3 适用）。

## 全景：一张决策图

```text
比较 ICS S1 与 S2（同一实参，两个候选）
│
├─ 形式不同？  标准 > 用户定义 > 省略号                        (¶2)
│
├─ 都是列表初始化序列？ initializer_list 优先；数组元素少/已知边界优先   (¶3.1，压过下面所有)
│
├─ 都是标准转换序列？
│    3.2.1 真子序列（不计左值变换）
│    3.2.2 等级：Exact > Promotion > Conversion；同等级再看 ¶4：
│           4.1 非→bool  4.2 枚举→底层类型  4.3 同等级浮点
│           4.4 →void* 更差  4.5 派生层次更近
│    3.2.3 右值绑右值引用（隐式对象形参无 ref-qualifier 时除外）
│    3.2.4 函数左值绑左值引用
│    3.2.5 限定转换加的 cv 更少
│    3.2.6 引用绑定的 cv 更少 / 数组边界已知
│    3.2.7 同一引用、源类型的指针转换更好
│
├─ 都是用户定义转换序列？ 同一个转换函数/构造函数 → 比第二 SCS；否则不可区分  (¶3.3)
│
└─ 其他：不可区分
```

## 实现视角

!!! impl
    - Clang 的 `CompareImplicitConversionSequences` → `CompareStandardConversionSequences` → `CompareQualificationConversions` / `CompareDerivedToBaseConversions` 几乎就是本节的逐段翻译。阅读这几个函数是验证自己理解的好方法。
    - 本页中有三处 Clang 23 与标准不一致（3.2.5 的引用侧限定转换、3.2.6 的数组边界、3.2.7），都是标准近年才加入或修订的细则。GCC 在这些点上的表现请自行在 Compiler Explorer 上核对。
    - 这些规则只决定选哪个函数，不产生任何运行时开销：选定后生成的代码与直接调用该函数完全一样。

## 历史与演进

!!! history
    - **C++98**：三层结构、真子序列、等级、cv 更少、派生层次距离、指针到 bool 更差都已存在。
    - **C++11**：右值引用带来 3.2.3（含隐式对象形参的例外）与 3.2.4；列表初始化带来 3.1.1；固定底层类型的枚举带来 4.2（后经缺陷报告完善）。
    - **C++20**：[[P0388R4]] 加入数组的列表初始化排序（3.1.2）与未知边界数组的引用绑定比较。
    - **C++23**：[[P1467R9]] 加入扩展浮点类型的排序规则 4.3。
    - **当前草案**：3.2.5 用相似类型加引用兼容重新表述了限定转换的比较；3.2.7 处理同一引用类型、不同源类型的情形。

## 陷阱

!!! pitfall "以为 `initializer_list` 只在构造函数中优先"
    3.1.1 对普通函数同样适用：`f(int)` 与 `f(initializer_list<long>)` 并存时，`f({42})` 选后者。

!!! pitfall "以为 `f(int)` 与 `f(const int&)` 能按左右值分派"
    不能，二者对任何实参都不可区分。要按值类别分派，用 `f(const int&)` 与 `f(int&&)`。

!!! pitfall "以为编译器会比较两个转换构造函数谁的输入更匹配"
    不同用户定义转换之间不比较初始 SCS，只要都可行就歧义（3.3）。

!!! pitfall "以为 `bool` 形参是安全的兜底"
    指针、字符串字面量、成员指针都能经标准转换（Conversion 等级）变成 `bool`，而且标准转换压过任何用户定义转换（¶2）。

## 思考题

!!! question "1. 解释下面每个调用的结果。"
    ```cpp nocheck
    void f(long);           void f(double);         // f(1)  ?
    void g(unsigned char);  void g(int);            // g('a') ?
    void h(const char*);    void h(std::string_view); // h("x") ?
    void k(int&&);          void k(const int&);     // int x; k(x); k(1); ?
    ```

<details markdown="1">
<summary>答案</summary>

- `f(1)`：`int → long` 整型转换，`int → double` 浮点-整型转换，都是 Conversion，¶4 中没有能区分它们的规则，因此歧义。
- `g('a')`：`char → int` 是整型提升，`char → unsigned char` 是整型转换 → `g(int)`。
- `h("x")`：数组到指针（Exact Match，标准转换）vs 用户定义转换（`string_view` 的构造函数）→ `h(const char*)`。
- `k(x)`：`int&&` 不能绑定左值，只有 `k(const int&)` 可行。`k(1)`：两者都可行，3.2.3 右值绑右值引用更好 → `k(int&&)`。
</details>

!!! question "2. 为什么 3.2.3 要把没有 ref-qualifier 的隐式对象形参排除在外？如果去掉这个例外，标准例子中的哪一行会改变结果？"

<details markdown="1">
<summary>答案</summary>

没有 ref-qualifier 的成员函数可以在右值上调用（[[over.match.funcs#5]] 的特许），其隐式对象形参是左值引用，但这只是建模手段，不代表作者有只接受左值的意图。若 3.2.3 适用于它，任何新增的接受右值引用的非成员重载都会在对象实参上胜过原有的成员函数，破坏 C++03 代码。

去掉例外后，`A() << 1` 会改变：非成员 `operator<<(A&&, char)` 在第一实参上（右值绑右值引用）更好，成员 `A::operator<<(int)` 在第二实参上（恒等 vs 整型转换）更好，结果变成歧义。
</details>

## 小结

!!! summary
    - 三层比较：形式（标准 > 用户定义 > 省略号）→ 同形式的专门规则 → 同等级标准转换的细则。
    - 列表初始化：`initializer_list` 优先，压过一切同形式规则；数组元素少者、已知边界者优先。
    - 标准转换：真子序列（不计左值变换）→ 等级 → 右值绑右值引用 → 函数绑左值引用 → cv 更少 → 引用兼容 → 源指针转换更好。
    - 同等级细则：不转 bool、枚举到底层类型、同等级浮点、不转 void*、派生层次更近。
    - 用户定义转换：只有同一个转换函数/构造函数之间才可比较（比第二 SCS）。
