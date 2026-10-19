---
title: 引用的初始化
summary: 引用绑定的完整算法：引用相关与引用兼容、直接绑定与经由转换函数的绑定、临时量实质化、什么时候生成临时对象，以及 C++23/26 对"绑定到临时量"的新限制
status: draft
covers: dcl.init.ref
papers: P0135R1, P2255R2, P2748R5
related: dcl.init, dcl.ref, class.temporary, conv.rval, conv.qual, over.match.ref, over.ics.ref, stmt.return, class.base.init, topics/initialization
tags: 初始化, 引用, 临时对象, 值类别
updated: 2026-10-17
---

引用不是对象，初始化引用的意思是**决定它绑定到哪个对象（或函数）**。这件事看似简单，`int& r = i;` 就是绑定到 `i`；但只要初始化表达式的类型、值类别或 cv 限定与引用不完全一致，就会出现一系列问题：

- 能不能绑定？（`int& r = 1;` 不能，`const int& r = 1;` 能）
- 绑定到原对象，还是一个新创建的临时对象？（`const long& r = i;` 绑定到临时量，修改 `i` 不影响 `r`）
- 如果要经过用户定义转换，转换函数返回的引用能不能直接用？
- 临时对象活多久？（[[class.temporary]] 的寿命延长）

本节 ¶5 用一个四分支的算法回答前三个问题，并定义了**直接绑定**（bind directly）这一概念，它在重载决议（[[over.ics.ref]]、[[over.ics.rank]]）中同样至关重要。本节是 [[dcl.init]] ¶15.2 的展开：只要目标类型是引用、初始化器不是花括号列表，就来到这里（花括号的情形见 [[dcl.init.list]] ¶3.9–¶3.10，最终大多也会回到这里）。

> 读之前需要知道：值类别（[[basic.lval]]）、临时量实质化转换（[[conv.rval]]）、限定转换与相似类型（[[conv.qual]]）。

## 引用必须被初始化，且不能重新绑定（¶1–¶3）

¶1 声明为 "`T` 的引用" 类型的变量必须初始化。

```cpp
int g(int) noexcept;
void f() {
  int i;
  int& r = i;               // r 指代 i
  r = 1;                    // i 的值变为 1
  int* p = &r;              // p 指向 i
  int& rr = r;              // rr 指代 r 所指代的对象，即 i（引用的引用不存在）
  int (&rg)(int) = g;       // 绑定到函数
  rg(i);                    // 调用 g
  int a[3];
  int (&ra)[3] = a;         // 绑定到数组
  ra[1] = i;                // 修改 a[1]
}
```

¶2 引用初始化之后**不能改为指代另一个对象**，对引用赋值就是对被指代的对象赋值（[[expr.assign]]）。实参传递（[[expr.call]]）和函数返回（[[stmt.return]]）也都是初始化，所以 `void h(int&); h(1);` 失败的原因，和 `int& r = 1;` 失败的原因是同一条规则。

¶3 只有以下位置可以省略引用的初始化器：

| 位置 | 例子 | 为什么可以 |
|---|---|---|
| 形参声明 | `void f(int& r);` | 每次调用时由实参初始化 |
| 函数返回类型 | `int& g();` | 每次返回时由 `return` 初始化 |
| 类定义中的成员声明 | `struct S { int& r; };` | 由构造函数或聚合初始化初始化 |
| 显式 `extern` | `extern int& r2;` | 这只是声明，定义在别处 |

```cpp
int& r1;          // error: 缺少初始化器
extern int& r2;   // OK: 非定义声明
```

## 引用相关与引用兼容（¶4）

¶4 给定类型 "*cv1* `T1`" 与 "*cv2* `T2`"：

- **引用相关**（reference-related）：如果 `T1` 与 `T2` 相似（[[conv.qual]]：逐层去掉 cv 限定后相同），或者 `T1` 是 `T2` 的基类，就说 "*cv1* `T1`" 与 "*cv2* `T2`" 引用相关。
- **引用兼容**（reference-compatible）：如果 "指向 *cv2* `T2` 的指针" 类型的纯右值可以通过标准转换序列转换为 "指向 *cv1* `T1` 的指针"，就说 "*cv1* `T1`" 与 "*cv2* `T2`" 引用兼容。

直观地说，引用兼容就是**可以安全地让一个 `T1` 引用直接指向这个 `T2` 对象**。借用指针转换来定义它很巧妙：指针转换已经精确地刻画了派生到基类（[[conv.ptr]]）、添加 cv 限定（[[conv.qual]]）、去掉函数的 `noexcept`（[[conv.fctptr]]）这些安全的视图变换，而不安全的变换（去掉 `const`、基类到派生类）都不是标准转换。

| *cv1* T1（引用的类型） | *cv2* T2（初始化器的类型） | 引用相关？ | 引用兼容？ |
|---|---|---|---|
| `const int` | `int` | ✓ | ✓（`int*` → `const int*`） |
| `int` | `const int` | ✓ | ✗（会丢掉 `const`） |
| `Base` | `Derived` | ✓ | ✓（派生到基类指针转换） |
| `Derived` | `Base` | ✗ | ✗ |
| `const int* const` | `int*` | ✓（相似） | ✓（`int**` → `const int* const*`） |
| `const int*` | `int*` | ✓（相似） | ✗（`int**` → `const int**` 不是合法的限定转换） |
| `long` | `int` | ✗ | ✗ |
| `void()` | `void() noexcept` | ✗ | ✓（函数指针转换） |

¶4 最后一句规定：如果按引用兼容关系判定可以绑定，而对应的标准转换序列却非良构（基类有歧义或不可访问），那么需要这种绑定的程序非良构：

```cpp
struct B {};
struct D1 : B {}; struct D2 : B {};
struct MD : D1, D2 {} md;
B& rb = md;            // error: B 是有歧义的基类

struct PD : private B {} pd;
B& rb2 = pd;           // error（在 PD 及其友元之外）：B 是不可访问的基类
```

注意这里不会退而求其次去创建临时对象，引用相关而绑定非良构就直接是错误。

## 绑定算法（¶5）

用类型为 "*cv2* `T2`" 的表达式初始化 "*cv1* `T1`" 的引用时，¶5 规定按以下顺序检查：

```text
¶5.1  左值引用，且
        .1 初始化器是左值（非位域），cv1 T1 与 cv2 T2 引用兼容          → 直接绑定到该左值
        .2 或 T2 是类类型，T1 与 T2 不引用相关，能转换为引用兼容的左值   → 直接绑定到转换结果
¶5.2  否则，若是"非 const 或带 volatile"的左值引用                       → 非良构
¶5.3  否则，若
        .1 初始化器是右值（非位域）或函数左值，且引用兼容
        .2 或 T2 是类类型，T1 与 T2 不引用相关，能转换为引用兼容的右值/函数左值
      → 得到"转换后的初始化器"；若是纯右值则以 cv1 T4 为类型实质化；直接绑定
¶5.4  否则，T1 必须与 T2 不引用相关，然后
        .1 若 T1 或 T2 是类类型：按拷贝初始化做用户定义转换，再用结果直接初始化引用
        .2 否则：隐式转换为 T1 的纯右值，实质化（类型 cv1 T1），绑定             → 不是直接绑定
```

除了最后一种情形（¶5.4.2，把初始化器隐式转换为被引用类型），其余情形都称引用直接绑定（binds directly）到初始化表达式。

下表按引用种类和初始化器概括结果：

| | 同类型左值 `i` | 同类型右值 `int()` | 不同类型 `long` 的左值 `l` | 能转换为 `int&` 的类 | 能转换为 `int` 的类 |
|---|---|---|---|---|---|
| `int&` | 直接绑定 ¶5.1.1 | ✗ ¶5.2 | ✗ ¶5.2 | 直接绑定 ¶5.1.2 | ✗ ¶5.2 |
| `const int&` | 直接绑定 ¶5.1.1 | 直接绑定（实质化）¶5.3.1 | 临时量 ¶5.4.2 | 直接绑定 ¶5.1.2 | 直接绑定（实质化）¶5.3.2 |
| `int&&` | ✗ ¶5.4（引用相关） | 直接绑定（实质化）¶5.3.1 | 临时量 ¶5.4.2 | ✗ ¶5.4（转换结果是引用相关的左值） | 直接绑定（实质化）¶5.3.2 |

### ¶5.1 左值引用直接绑定左值

¶5.1.1 最常见的情形：初始化器是左值、不是位域、引用兼容。绑定到该左值（或其中适当的基类子对象）。

¶5.1.2 初始化器是类类型，`T1` 与 `T2` 不引用相关，并且能通过返回左值引用的转换函数转换为引用兼容的左值（候选按 [[over.match.ref]] 枚举）。脚注说明，这要求转换函数返回引用类型。

注 2：这两种直接绑定不需要左值到右值、数组到指针、函数到指针转换，因此这些转换都不施行，引用绑定到的是对象本身，而不是它的值。

```cpp
double d = 2.0;
double& rd = d;                 // rd 指代 d
const double& rcd = d;          // rcd 指代 d（添加 const 是引用兼容的）

struct A { };
struct B : A { operator int&(); } b;
A& ra = b;                      // ¶5.1.1：ra 指代 b 中的 A 子对象
const A& rca = b;               // 同上
int& ir = B();                  // ¶5.1.2：ir 指代 B::operator int& 的结果
```

`int& ir = B();` 值得留意：`B()` 是右值，但 ¶5.1.2 并不要求初始化器是左值，只要求转换结果是左值。

为什么 ¶5.1.2 要求 `T1` 与 `T2` 不引用相关？因为如果二者引用相关（如 `A& ra = b;`），¶5.1.1 已经决定了结果，派生类到基类的绑定不应该被一个用户定义的 `operator A&()` 抢走。

### ¶5.2 非 const 左值引用到此为止

¶5.2 如果不满足 ¶5.1，而引用是非 const 的（或带 `volatile` 的）左值引用，程序非良构。

```cpp
double& rd2 = 2.0;              // error: 不是左值，且引用不是 const
int i = 2;
double& rd3 = i;                // error: 类型不匹配，且引用不是 const
const volatile int& rv = 1;     // error: volatile 也不行
```

这是 C++ 最古老的规则之一，动机非常实际。如果允许 `double& rd3 = i;` 绑定到一个临时的 `double`，那么 `rd3 = 3.14;` 修改的是临时量，`i` 毫无变化。C++ 早期（ARM 时代）允许过这种绑定，结果产生了大量难以察觉的 bug，例如 `void inc(long& x) { ++x; } int n; inc(n);` 悄悄地对临时量自增。从此，非 const 左值引用只能绑定到可修改的左值。

`const` 引用允许绑定临时量，因为通过它无法修改对象，也就不存在误改临时量的问题。`volatile` 被排除在外，是因为 `volatile` 表示每次访问都必须真正发生在那个对象上，绑定到一个编译器创建的临时量违背了这一意图。

### ¶5.3 绑定到右值（以及函数左值）

¶5.3 引用是 const 左值引用或右值引用时，如果

- ¶5.3.1 初始化器是右值（不是位域）或函数左值，且引用兼容；或者
- ¶5.3.2 初始化器是类类型，`T1` 与 `T2` 不引用相关，并且能通过转换函数（[[over.match.ref]]）转换为引用兼容的右值或函数左值，

那么第一种情形中的初始化器、第二种情形中的转换结果称为**转换后的初始化器**（converted initializer）。如果它是纯右值，设其类型为 `T4`，就施行临时量实质化转换（[[conv.rval]]），并把纯右值的类型**视为 "*cv1* `T4`"**。不论哪种情形，引用都绑定到所得的泛左值（或其适当的基类子对象）。

视为 *cv1* `T4` 这一点很重要。`const int& r = 42;` 实质化出的临时对象的类型是 `const int`，所以通过 `const_cast` 修改它是 UB：

```cpp
constexpr int f() {
  const int& x = 42;
  const_cast<int&>(x) = 1;   // UB: 修改 const 对象
  return x;
}
constexpr int z = f();       // error: 不是常量表达式（常量求值中检测到了 UB）
```

标准的例 5 展示了这一分支的各种形态：

```cpp
struct A { };
struct B : A { } b;
extern B f();
const A& rca2 = f();                // 绑定到 B 纯右值实质化后的 A 子对象
A&& rra = f();                      // 同上
struct X {
  operator B();
  operator int&();
} x;
const A& r = x;                     // ¶5.3.2：绑定到 operator B() 结果（实质化后）的 A 子对象
int i2 = 42;
int&& rri = static_cast<int&&>(i2); // xvalue：直接绑定到 i2
B&& rrb = x;                        // ¶5.3.2：直接绑定到 operator B() 的结果

typedef int *AP[3];                 // 3 个 int* 的数组
typedef const int *const ACPC[3];   // 3 个 const int* const 的数组
ACPC &&r2 = AP{};                   // 直接绑定：AP 纯右值以 ACPC 类型实质化
```

最后一行中，`AP` 与 `ACPC` 相似且引用兼容（多层限定转换），所以数组纯右值以 `ACPC` 类型实质化，不需要逐元素转换出一个新数组。

函数左值也归入 ¶5.3，所以 `void (&&rf)() = g;` 合法。右值引用可以绑定函数左值，因为函数没有可以移走的资源，左值和右值的区分对函数没有意义。

### ¶5.4 最后手段：创建临时对象

¶5.4 如果以上都不满足，`T1` **必须与 `T2` 不引用相关**。这句话排除了两类情形：

1. 右值引用不能绑定到引用相关的左值：`double d2; double&& r = d2;`。如果允许，`std::move` 就失去了意义，任何左值都可以悄悄地当作右值使用。
2. cv 限定被丢弃：`const volatile int cvi = 1; const int& r2 = cvi;` 引用相关但不引用兼容（丢掉了 `volatile`），不能退而创建一个副本。

然后：

- ¶5.4.1 `T1` 或 `T2` 是类类型：按通过用户定义转换拷贝初始化 *cv1* `T1` 对象的规则（[[dcl.init]] ¶15.6.3、[[over.match.copy]]、[[over.match.conv]]）考虑用户定义转换；如果对应的非引用拷贝初始化非良构，这里也非良构。然后用转换函数调用的结果 E，以 `(E)` 形式直接初始化引用，此时不再考虑用户定义转换。
- ¶5.4.2 否则：把初始化表达式隐式转换为 "`T1`" 的纯右值，以 "*cv1* `T1`" 类型实质化，引用绑定到结果。

```cpp
const double& rcd2 = 2;          // ¶5.4.2：临时 const double，值 2.0
double&& rrd = 2;                // ¶5.4.2：临时 double，值 2.0
int i3 = 2;
double&& rrd3 = i3;              // ¶5.4.2：OK！int 左值与 double 不引用相关，创建临时 double
const std::string& s = "abc";    // ¶5.4.1：string(const char*) 构造临时量
```

`double&& rrd3 = i3;` 是一个有名的怪现象：右值引用看起来绑定到了左值。其实并非如此，它绑定的是从 `i3` 转换出的临时 `double`，修改 `rrd3` 不会影响 `i3`。

标准的例 6 展示了 ¶5.4 的所有错误形态：

```cpp
struct Banana { };
struct Enigma { operator const Banana(); };
struct Alaska { operator Banana&(); };
void enigmatic() {
  typedef const Banana ConstBanana;
  Banana &&banana1 = ConstBanana(); // error: 引用相关（丢 const），¶5.4 禁止
  Banana &&banana2 = Enigma();      // error: 转换结果 const Banana 与 Banana 引用相关但不兼容
  Banana &&banana3 = Alaska();      // error: 转换结果是左值 Banana&，右值引用不能绑定
}
const volatile int cvi = 1;
const int& r2 = cvi;                // error: 丢掉 volatile
struct A { operator volatile int&(); } a;
const int& r3 = a;                  // error: 转换函数的结果丢掉 volatile
double d2 = 1.0;
double&& rrd2 = d2;                 // error: 初始化器是引用相关类型的左值
struct X { operator int&(); };
int&& rri2 = X();                   // error: 转换函数的结果是引用相关类型的左值
```

`Banana&& banana2 = Enigma();` 的分析值得细看。¶5.3.2 要求转换结果与 `Banana` 引用兼容，而 `const Banana` 不是（会丢掉 const），所以 ¶5.3.2 不适用。到了 ¶5.4，`Banana` 与 `Enigma` 不引用相关，进入 ¶5.4.1：按拷贝初始化 `Banana` 的规则，`operator const Banana()` 的结果 E 是 `const Banana` 纯右值；再用 `(E)` 直接初始化 `Banana&&` 时，`Banana` 与 `const Banana` 引用相关，被 ¶5.4 禁止，因此非良构。

### 直接绑定为什么重要

¶5 末尾定义了**直接绑定**（[[g:bind-directly]]）：除 ¶5.4.2 外的所有情形都是直接绑定，也包括 ¶5.4.1 中最后那次直接初始化，因为它以 `(E)` 的形式回到了 ¶5.1/¶5.3。

这个概念在别处有三个用途：

1. 重载决议：[[over.ics.ref]] 规定，引用参数直接绑定到实参时，隐式转换序列是恒等转换（或派生到基类转换）；不是直接绑定时，转换序列按转换为被引用类型来计算。[[over.ics.rank]] 中“右值引用绑定右值优于左值引用”等规则也建立在这个概念之上。
2. 寿命延长：不论是否直接绑定，只要引用最终绑定到一个（实质化产生的）临时对象，就适用 [[class.temporary]] ¶6 的寿命延长。
3. 常量表达式与结构化绑定等处，推理引用指代哪个对象时也要用到它。

## 位域

位域不能被非 const 引用绑定（[[class.bit]]）：¶5.1.1 和 ¶5.3.1 都明确排除了位域。`const int& r = s.bf;` 按 [[class.bit]] 注 3 的说法，绑定到一个保存位域值的临时对象。

```cpp
struct S { int bf : 3; } s;
int& r1 = s.bf;          // error: 非 const 引用不能绑定位域
const int& r2 = s.bf;    // OK: 绑定到临时量（主流实现均如此）
```

!!! lawyer "措辞上的空隙"
    严格按 ¶5 的文字，`const int& r2 = s.bf;` 既不满足 ¶5.1.1（初始化器是位域），也不满足 ¶5.3.1（初始化器是左值，而且位域被排除），于是进入 ¶5.4。而 ¶5.4 要求 `T1`（`int`）与 `T2`（`int`）不引用相关，这里却是相同类型。照字面理解，程序就非良构了；但 [[class.bit]] 的注 3（非规范性）明确说它绑定到临时量，所有主流编译器也都接受。这是规范文字与设计意图之间的一处空隙。

## 临时对象的寿命（¶6）

¶6（注）绑定到引用的临时对象的寿命由 [[class.temporary]] 描述。要点：

- 引用绑定到临时量（或其子对象）时，如果这一泛左值是通过实质化、括号、数组下标、`.` 成员访问、`.*`、不涉及用户定义转换的 cast、条件运算符、逗号运算符等不改变所指对象的表达式得到的，临时量的寿命就延长到引用的寿命（[[class.temporary]] ¶6）。
- 通过函数调用得到的引用（包括 `std::max`、`std::move`、返回 `const T&` 的成员函数）**不会**触发延长，因为编译器看不到函数体内部。

```cpp run ub
#include <string>
#include <cstdio>
const std::string& id(const std::string& s) { return s; }
int main() {
  const std::string& ok = std::string(40, 'a');        // 寿命延长到 ok 的作用域结束
  const std::string& bad = id(std::string(40, 'b'));   // 临时量在本行结束时销毁
  std::printf("%c %c\n", ok[0], bad[0]);               // UB: bad 悬垂
}
```

用 `-fsanitize=address` 运行会报告 `stack-use-after-scope`。

- 例外：绑定到函数调用中引用形参的临时量、绑定到 *new-initializer* 中引用的临时量、圆括号聚合初始化中绑定到引用元素的临时量，都只存活到完整表达式结束（[[class.temporary]] ¶6.10–¶6.12）。

## 禁止把引用绑定到注定悬垂的临时量

既然有些绑定必然悬垂，越来越多的规则把它们从运行时的 UB 提前为编译错误。

### 构造函数的成员初始化器

[[class.base.init]] ¶8（C++14 之后通过缺陷报告加入）规定，在 *mem-initializer* 中把引用成员绑定到临时表达式，程序非良构；¶13 规定，在默认成员初始化器中这样做，则在实际使用该初始化器时非良构。

```cpp
struct A {
  A() : v(42) { }   // error: 临时量只活到构造函数结束
  const int& v;
};
```

### 库：`reference_constructs_from_temporary` {{c++23}}

[[P2255R2]] 新增了两个类型特征 `std::reference_constructs_from_temporary<T, U>` 和 `std::reference_converts_from_temporary<T, U>`，用来判断用 `U` 类型的表达式（直接或拷贝）初始化引用 `T` 时，是否会把引用绑定到一个临时量。它们无法用普通的模板元编程实现，需要编译器内建支持。

同一提案利用这些特征，在 `std::pair`、`std::tuple` 的相关构造函数会把引用成员绑定到临时量时将其删除，并让 `INVOKE<R>`（`std::function<const T&()>` 等）在会返回悬垂引用时非良构：

```cpp
#include <tuple>
#include <string>
#include <type_traits>
static_assert(std::reference_constructs_from_temporary_v<const int&, long>);
static_assert(!std::reference_constructs_from_temporary_v<const int&, int&>);
std::tuple<const std::string&> t("abc");   // error（C++23 起）：引用元素会绑定到临时 string
```

### 核心语言：`return` 绑定临时量 {{c++26}}

[[P2748R5]] 在 [[stmt.return]] ¶6 中规定：如果 `return` 语句把返回的引用绑定到临时表达式，程序非良构。当前草案还进一步覆盖了返回对象的**组成引用**（constituent reference，[[intro.object]]）：

```cpp
auto&& f1() {
  return 42;            // error（C++26）：返回的引用绑定到临时量
}
const double& f2() {
  static int x = 42;
  return x;             // error（C++26）：int → double 的转换创建了临时量
}
auto&& id(auto&& r) { return static_cast<decltype(r)&&>(r); }
auto&& f3() {
  return id(42);        // OK（但几乎一定是 bug）：经过函数调用，编译器不追踪
}
```

`f2` 是一个很好的例子：程序员以为返回的是静态变量 `x`，实际上 `const double&` 绑定的是 `x` 转换出的临时 `double`（¶5.4.2）。C++23 及以前它是良构的，返回一个悬垂引用（使用即 UB）；C++26 中则是编译错误。

这条规则豁免了为 `std::is_convertible` 虚构的那个函数（[[meta.rel]]），否则 `is_convertible_v<int, const int&>` 会变成 `false`，破坏大量现有代码。

!!! impl
    截至写作时，Clang 对 `f1`、`f2` 报错（"returning reference to local temporary object"），但返回对象的引用成员绑定到临时量时（如 `struct P { const int& r; }; P g() { return P{42}; }`）尚不报错。

## 实现视角

!!! impl
    - 引用的表示就是指针：在所有主流 ABI 中，引用成员和引用形参的表示与指针相同；引用变量通常会被完全优化掉。
    - 寿命延长的临时量存放在当前栈帧（自动存储期的引用）或静态存储（命名空间作用域的引用）中，在引用离开作用域时析构，编译器为它生成一个隐藏的局部对象。
    - 诊断：Clang 的 `-Wdangling` 系列（默认开启）能捕获不少立即悬垂的绑定，例如圆括号聚合初始化中的引用成员、`std::string_view sv = std::string("x");`；GCC 的 `-Wdangling-reference` 尝试检测把临时量传给返回引用的函数这类情形，但有误报。

## 历史与演进

!!! history
    - **C++98**：非 const 左值引用只能绑定左值；const 引用可以绑定右值。对于类类型右值，实现可以选择直接绑定，也可以先拷贝出一个临时量再绑定，因此即使不拷贝，也要求拷贝构造函数可访问。
    - **C++11**：引入右值引用。通过解决一个核心问题，类右值绑定到 const 引用时必须直接绑定，不再允许额外拷贝。此后 ¶5 经过多次改写，以处理右值引用与转换函数的组合。
    - **C++14 之后**（缺陷报告）：*mem-initializer* 中把引用成员绑定到临时量变为非良构。
    - **C++17**：[[P0135R1]] 引入临时量实质化，¶5.3 改用转换后的初始化器加实质化的措辞。
    - **C++20 时期**（缺陷报告）：引用相关改用相似类型定义，`const int* const& r = p;`（`p` 为 `int*`）直接绑定到 `p`。
    - **C++23**：[[P2255R2]] 类型特征与库中对悬垂绑定的禁止。
    - **C++26**：[[P2748R5]] `return` 语句绑定临时量非良构。

## 陷阱

!!! pitfall "`const T&` 形参 + 返回引用 = 悬垂"
    `const auto& m = std::max(a, b + 1);` 中 `b + 1` 的临时量在本行结束时销毁，`m` 可能悬垂。寿命延长只对直接绑定临时量的那个引用有效，无法穿过函数调用。

!!! pitfall "看似绑定到变量，实际绑定到临时量"
    `int i; const long& r = i; i = 5;` 之后 `r` 仍是 0，因为 `r` 绑定的是转换出的临时 `long`。形参 `void f(const long&)` 接收 `int` 实参时也是一样。

!!! pitfall "范围 for 与链式调用"
    `for (auto& x : make_obj().items())` 中只有 `make_obj().items()` 的结果被绑定到隐藏的引用，`make_obj()` 返回的临时对象在初始化器结束时销毁。C++23 起 [[class.temporary]] ¶7 让 *for-range-initializer* 中的所有临时量都延长寿命，修复了这一问题。

## 思考题

!!! question "1. 下面每行绑定到什么？哪些非良构？"
    ```cpp
    struct B {}; struct D : B {};
    D make();
    D d;
    B&& r1 = make();
    B&& r2 = d;
    B&& r3 = std::move(d);
    const B& r4 = make();
    B& r5 = make();
    ```

<details markdown="1">
<summary>答案</summary>

- `r1`：`make()` 是 `D` 纯右值，`B` 与 `D` 引用兼容 → ¶5.3.1，实质化 `D` 临时量，绑定到其 `B` 子对象；临时量寿命延长。
- `r2`：`d` 是左值。¶5.1 不适用（右值引用），¶5.2 不适用，¶5.3.1 要求右值，不满足；¶5.4 要求 `B` 与 `D` 不引用相关，而 `B` 是 `D` 的基类 → 非良构。
- `r3`：`std::move(d)` 是 xvalue（右值）→ ¶5.3.1，直接绑定到 `d` 的 `B` 子对象，不涉及临时量。
- `r4`：同 `r1`，绑定到实质化的临时量的 `B` 子对象，寿命延长。
- `r5`：非 const 左值引用，初始化器是右值 → ¶5.2 非良构。
</details>

!!! question "2. 为什么 `double&& r = i;`（`i` 是 `int` 左值）是良构的，而 `int&& r = i;` 不是？这种不对称合理吗？"

<details markdown="1">
<summary>答案</summary>

`int&& r = i;`：`int` 与 `int` 引用相关，`i` 是左值；¶5.3 要求右值，¶5.4 要求不引用相关，都不满足 → 非良构。

`double&& r = i;`：`double` 与 `int` 不引用相关 → ¶5.4.2，`i` 转换为 `double` 纯右值并实质化，`r` 绑定到这个新的临时对象。

这是合理的。右值引用的语义是可以窃取所绑定对象的资源。如果 `int&& r = i;` 合法，就等于允许窃取 `i`，而 `i` 之后还会被使用；`double&& r = i;` 绑定的是一个与 `i` 无关的临时量，没有人会再用它，窃取它是安全的。规则真正禁止的是**把右值引用绑定到现存的左值对象**。
</details>

!!! question "3. 下面的 `get` 在 C++23 和 C++26 中分别如何？"
    ```cpp
    struct Cfg { long timeout; };
    const int& get(const Cfg& c) { return c.timeout; }
    ```

<details markdown="1">
<summary>答案</summary>

`c.timeout` 是 `const long` 左值，`int` 与 `long` 不引用相关 → ¶5.4.2：转换为 `int` 纯右值并实质化，返回的引用绑定到这个临时量。临时量在 `return` 语句的完整表达式结束时销毁，返回的引用悬垂。

- C++23：良构，但任何使用返回值的行为都是 UB（多数编译器会警告返回了局部临时对象的引用）。
- C++26：[[stmt.return]] ¶6（[[P2748R5]]）使其非良构。
</details>

## 小结

!!! summary
    - 引用相关 = 相似类型或基类；引用兼容 = 对应的指针能通过标准转换安全转换。
    - ¶5 的顺序：左值引用直接绑定左值（或转换函数返回的左值）→ 非 const 左值引用到此为止 → 绑定右值/函数左值（或转换函数返回的右值），纯右值实质化 → 不引用相关时才允许创建临时量。
    - 除了隐式转换为被引用类型再实质化（¶5.4.2）这一种情形，其余都叫直接绑定。
    - 右值引用永远不能绑定到引用相关的左值，但可以绑定到从不相关类型的左值转换出的临时量。
    - 寿命延长无法穿过函数调用；C++14/23/26 逐步把必然悬垂的绑定变成编译错误。
