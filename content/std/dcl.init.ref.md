---
title: 引用的初始化
summary: 初始化一个引用时，它绑定到初始化表达式本身、转换函数的结果，还是一个新建的临时对象；哪些绑定非良构；以及标准怎样逐步把必然悬垂的绑定变成编译错误。
status: done
covers: dcl.init.ref
papers: P0135R1, P2255R2, P2748R5, P2718R0
related: dcl.init, dcl.ref, class.temporary, conv.rval, conv.qual, over.match.ref, over.ics.ref, stmt.return, class.base.init, topics/value-categories, topics/dangling-references, topics/initialization
tags: 初始化, 引用, 临时对象, 值类别
updated: 2026-10-19
---

!!! tldr
    - 引用一经初始化就固定指代一个对象或函数；对引用赋值就是对那个对象赋值。传参和 `return` 也是初始化，遵守同一套规则。
    - 类型相同或只多了 cv 限定、或者是派生到基类时，引用直接绑定到原对象；类型不匹配时，`const T&` 和 `T&&` 可以绑定到一个转换出来的临时对象，非 const 左值引用不行。
    - 右值引用永远不能绑定到同类（引用相关）类型的左值，但 `double&& r = i;`（`i` 是 `int`）合法：它绑定的是新建的临时 `double`。
    - 绑定到临时对象的引用会延长它的寿命，但延长穿不过函数调用；`return` 一个绑定到临时量的引用在 C++26 中是编译错误。

## 绑定到谁

```cpp run ok
#include <cstdio>
int main() {
  int i = 1;
  int& r = i;            // r 指代 i
  const long& rl = i;    // rl 指代一个新建的临时 long
  i = 5;
  std::printf("%d %ld\n", r, rl);   // 5 1
}
```

引用不是对象，初始化引用就是决定它**绑定**到哪个对象或函数。`r` 绑定到 `i` 本身；`rl` 的类型与 `i` 不同，于是编译器先把 `i` 转换成一个临时 `long`，`rl` 绑定到这个临时对象，之后修改 `i` 与它无关。

本节回答三个问题：能不能绑定，绑定到原对象还是临时对象，临时对象活多久。目标类型是引用、初始化器不是花括号列表时，[[dcl.init#15.2]] 把初始化交给这里；花括号的情形见 [[dcl.init.list]]，大多最终也回到这里。

阅读本节需要知道值类别（[[basic.lval]]，见专题 [[topics/value-categories]]）：左值（lvalue）指代一个已有的对象，纯右值（prvalue）只是一个值，xvalue 是即将被移走资源的对象。左值和 xvalue 合称泛左值（glvalue），xvalue 和纯右值合称右值（rvalue）。引用只能绑定到泛左值；初始化器是纯右值时，要先经过[[g:temporary-materialization-conversion|临时量实质化转换]]（[[conv.rval]]）创建一个临时对象，得到指代它的 xvalue。

## 引用必须初始化，且不能改绑（¶1–¶3）

¶1 声明为 `T&` 或 `T&&` 的变量必须初始化。标准例 1 展示了绑定到变量、函数和数组：

```cpp run ok
int g(int) noexcept { return 0; }
int main() {
  int i;
  int& r = i;            // r 指代 i
  r = 1;                 // i 的值变为 1
  int* p = &r;           // p 指向 i
  int& rr = r;           // rr 也指代 i：引用的引用不存在
  int (&rg)(int) = g;    // 绑定到函数
  rg(i);                 // 调用 g
  int a[3];
  int (&ra)[3] = a;      // 绑定到数组
  ra[1] = i;             // 修改 a[1]
  (void)p; (void)rr;
}
```

¶2 引用初始化之后不能改为指代另一个对象，对引用赋值就是对被指代的对象赋值（[[expr.assign]]）。实参传递（[[expr.call]]）和函数返回（[[stmt.return]]）都是初始化，所以 `void h(int&); h(1);` 失败的原因与 `int& r = 1;` 相同。

¶3 只有四个位置可以不写引用的初始化器：

| 位置 | 例子 | 谁来初始化 |
|---|---|---|
| 形参声明 | `void f(int& r);` | 每次调用时的实参 |
| 函数返回类型 | `int& g();` | 每次执行的 `return` |
| 类定义中的成员 | `struct S { int& r; };` | 构造函数或聚合初始化 |
| 显式 `extern` | `extern int& r2;` | 别处的定义 |

<div class="compare" markdown="1">

```cpp ok
extern int& r2;   // 非定义声明
```

```cpp error
int& r1;          // error: 缺少初始化器
```

</div>

## 引用相关与引用兼容（¶4）

```cpp
struct Base {}; struct Derived : Base {};
int i;          const int ci = 0;   Derived d;
const int& a = i;    // OK：只是多了 const
int& b = ci;         // error: 会丢掉 const
Base& c = d;         // OK：派生到基类
```

能否直接绑定，取决于两种类型之间的两个关系。¶4 设引用的类型是 *cv1* `T1`，初始化器的类型是 *cv2* `T2`：

- 如果 `T1` 与 `T2` [[g:similar-types|相似]]（逐层去掉 cv 限定后相同，[[conv.qual]]），或者 `T1` 是 `T2` 的基类，就说 *cv1* `T1` 与 *cv2* `T2` **引用相关**（reference-related）。
- 如果“指向 *cv2* `T2` 的指针”可以经标准转换序列转换为“指向 *cv1* `T1` 的指针”，就说 *cv1* `T1` 与 *cv2* `T2` **引用兼容**（reference-compatible）。

引用相关说的是两者是不是同一类东西；引用兼容说的是能不能让 `T1` 的引用直接指向这个 `T2` 对象而不出问题。后者借用指针转换来定义：派生到基类（[[conv.ptr]]）、添加 cv 限定（[[conv.qual]]）、去掉函数类型的 `noexcept`（[[conv.fctptr]]）都是安全的指针转换，而去掉 `const`、基类到派生类都不是标准转换。

| *cv1* `T1`（引用） | *cv2* `T2`（初始化器） | 引用相关 | 引用兼容 |
|---|---|---|---|
| `const int` | `int` | 是 | 是：`int*` → `const int*` |
| `int` | `const int` | 是 | 否：会丢掉 `const` |
| `Base` | `Derived` | 是 | 是：派生到基类 |
| `Derived` | `Base` | 否 | 否 |
| `const int* const` | `int*` | 是（相似） | 是：`int**` → `const int* const*` |
| `const int*` | `int*` | 是（相似） | 否：`int**` → `const int**` 不是合法的限定转换 |
| `long` | `int` | 否 | 否 |

¶4 最后一句规定：如果按引用兼容判定可以绑定，而对应的指针转换本身非良构（基类有歧义或不可访问），程序非良构。这时不会退而创建临时对象。

```cpp error
struct B {};
struct D1 : B {}; struct D2 : B {};
struct MD : D1, D2 {} md;
B& rb = md;        // error: B 是有歧义的基类

struct PD : private B {} pd;
B& rb2 = pd;       // error: B 是不可访问的基类
```

## 绑定算法（¶5）

¶5 用 *cv2* `T2` 类型的表达式初始化 *cv1* `T1` 的引用时，按顺序检查四个分支，第一个适用的决定结果：

1. **左值引用绑定左值**（¶5.1）：初始化器是引用兼容的左值，或者能经转换函数得到引用兼容的左值。直接绑定到它。
2. **非 const 左值引用到此为止**（¶5.2）：前一条不适用，而引用是非 const 或带 `volatile` 的左值引用，程序非良构。
3. **绑定右值**（¶5.3）：初始化器是引用兼容的右值（或函数左值），或者能经转换函数得到这样的结果。纯右值先实质化，然后直接绑定。
4. **创建临时对象**（¶5.4）：`T1` 必须与 `T2` 不引用相关；把初始化器转换成 `T1`，绑定到转换出的临时对象。

下表按引用种类和初始化器给出结果：

| | 同类型左值 `i` | 同类型右值 `int()` | `long` 左值 | 能转换为 `int&` 的类 | 能转换为 `int` 的类 |
|---|---|---|---|---|---|
| `int&` | 直接绑定（¶5.1.1） | 非良构（¶5.2） | 非良构（¶5.2） | 直接绑定（¶5.1.2） | 非良构（¶5.2） |
| `const int&` | 直接绑定（¶5.1.1） | 实质化后直接绑定（¶5.3.1） | 临时对象（¶5.4.2） | 直接绑定（¶5.1.2） | 实质化后直接绑定（¶5.3.2） |
| `int&&` | 非良构（¶5.4） | 实质化后直接绑定（¶5.3.1） | 临时对象（¶5.4.2） | 非良构（¶5.4） | 实质化后直接绑定（¶5.3.2） |

### 左值引用直接绑定左值（¶5.1）

```cpp run ok
struct A { };
struct B : A { operator int&(); } b;
B::operator int&() { static int n; return n; }
double d = 2.0;
double& rd = d;          // rd 指代 d
const double& rcd = d;   // rcd 指代 d：添加 const 是引用兼容的
A& ra = b;               // ¶5.1.1：ra 指代 b 中的 A 子对象
const A& rca = b;        // 同上
int& ir = B();           // ¶5.1.2：ir 指代 operator int& 的结果
int main() {}
```

¶5.1.1 是最常见的情形：引用是左值引用，初始化器是左值（但不是位域），并且引用兼容。引用绑定到这个左值，或者它的适当基类子对象。

¶5.1.2 处理类类型的初始化器：`T1` 与 `T2` 不引用相关，而 `T2` 有返回左值引用的转换函数，能得到引用兼容的左值。候选转换函数按 [[over.match.ref]] 枚举，经重载决议选出最好的一个。`int& ir = B();` 中 `B()` 本身是右值，但 ¶5.1.2 只要求转换的结果是左值。

¶5.1.2 要求 `T1` 与 `T2` 不引用相关，是为了让 `A& ra = b;` 这样的派生到基类绑定始终由 ¶5.1.1 决定，不会被一个用户定义的 `operator A&()` 抢走。

注 2 指出，这两种直接绑定不施行左值到右值、数组到指针、函数到指针转换：引用绑定的是对象本身，不是它的值。

### 非 const 左值引用不接受临时对象（¶5.2）

<div class="compare" markdown="1">

```cpp ok
int i = 2;
const double& r1 = 2.0;
const double& r2 = i;
```

```cpp error
int i = 2;
double& r1 = 2.0;  // error
double& r2 = i;    // error
const volatile int& r3 = 1;
                   // error
```

</div>

¶5.2 如果 ¶5.1 不适用，而引用是非 const 的左值引用，或者带 `volatile` 的左值引用，程序非良构。

这条规则防止的是悄悄修改临时对象。如果 `double& r2 = i;` 能绑定到一个临时 `double`，`r2 = 3.14;` 改的就是临时对象，`i` 毫无变化。C++ 早期版本允许过这种绑定，像 `void inc(long& x) { ++x; }` 被 `int` 实参调用时只自增了临时对象，这类错误很难察觉，于是这种绑定被禁止了。

`const` 引用不能用来修改对象，绑定临时对象没有这个问题。`volatile` 引用仍被排除，因为 `volatile` 要求每次访问都落在那个真实的对象上，换成编译器创建的临时对象就违背了它的用意。

### 绑定右值（¶5.3）

```cpp ok
struct A { };
struct B : A { } b;
extern B f();
const A& rca2 = f();     // 绑定到 B 纯右值实质化后的 A 子对象
A&& rra = f();           // 同上
struct X {
  operator B();
  operator int&();
} x;
const A& r = x;          // ¶5.3.2：绑定到 operator B() 结果的 A 子对象
int i2 = 42;
int&& rri = static_cast<int&&>(i2);  // xvalue：直接绑定到 i2
B&& rrb = x;             // ¶5.3.2：直接绑定到 operator B() 的结果
```

¶5.3 到这里时，引用要么是 const 左值引用，要么是右值引用。如果

- ¶5.3.1 初始化器是右值（但不是位域）或函数左值，并且引用兼容；或者
- ¶5.3.2 初始化器是类类型，`T1` 与 `T2` 不引用相关，并且能经转换函数（[[over.match.ref]]）转换为引用兼容的右值或函数左值，

那么前一种情形的初始化器、后一种情形的转换结果称为**转换后的初始化器**（converted initializer）。如果它是纯右值，设其类型为 `T4`，就施行临时量实质化转换，并把纯右值的类型视为 *cv1* `T4`。引用绑定到所得的泛左值，或者它的适当基类子对象。

视为 *cv1* `T4` 意味着临时对象带上了引用的 cv 限定。`const int& x = 42;` 实质化出的临时对象类型是 `const int`，通过 `const_cast` 修改它就是修改 const 对象：

```cpp error
constexpr int f() {
  const int& x = 42;
  const_cast<int&>(x) = 1;   // UB：修改 const 对象
  return x;
}
constexpr int z = f();       // error: 常量求值中出现 UB，不是常量表达式
```

同样的规则让数组可以整体以更 const 的类型实质化，不必逐元素转换：

```cpp ok
typedef int *AP[3];                 // 3 个 int* 的数组
typedef const int *const ACPC[3];   // 3 个 const int* const 的数组
ACPC&& r = AP{};   // AP 与 ACPC 引用兼容：AP 纯右值以 ACPC 类型实质化
```

函数左值也归入 ¶5.3，所以 `void (&&rf)() = g;` 合法。函数没有可以移走的资源，左值与右值的区分对它没有意义。

### 创建临时对象（¶5.4）

```cpp ok
#include <string>
const double& rcd2 = 2;        // 临时 const double，值 2.0
double&& rrd = 2;              // 临时 double，值 2.0
int i3 = 2;
double&& rrd3 = i3;            // OK：绑定到从 i3 转换出的临时 double
const std::string& s = "abc";  // string(const char*) 构造临时对象
```

¶5.4 前三个分支都不适用时，标准先要求 `T1` 与 `T2` **不引用相关**，然后才允许转换：

- ¶5.4.1 `T1` 或 `T2` 是类类型：按“用户定义转换拷贝初始化一个 *cv1* `T1` 对象”的规则（[[dcl.init#15.6.3]]、[[over.match.copy]]、[[over.match.conv]]）选择转换；如果对应的非引用拷贝初始化非良构，这里也非良构。转换函数调用的结果 E 再以 `(E)` 的形式直接初始化引用，这一次不再考虑用户定义转换。
- ¶5.4.2 否则：把初始化器隐式转换为 `T1` 类型的纯右值，以 *cv1* `T1` 类型实质化，引用绑定到结果。

`double&& rrd3 = i3;` 看起来是右值引用绑定了左值，其实它绑定的是转换出的临时 `double`，修改 `rrd3` 不影响 `i3`。

不引用相关这个前提排除了两类绑定：

1. 右值引用绑定引用相关的左值，如 `double d2; double&& r = d2;`。如果允许，任何左值都能不经 `std::move` 就被当作右值移走。
2. 丢掉 cv 限定，如 `const volatile int cvi = 1; const int& r2 = cvi;`。两者引用相关但不兼容（丢了 `volatile`），不能退而复制一份。

标准例 6 列出了 ¶5.4 的各种错误：

```cpp error
struct Banana { };
struct Enigma { operator const Banana(); };
struct Alaska { operator Banana&(); };
void enigmatic() {
  typedef const Banana ConstBanana;
  Banana&& banana1 = ConstBanana(); // error: 引用相关，会丢掉 const
  Banana&& banana2 = Enigma();      // error: 见下文
  Banana&& banana3 = Alaska();      // error: 转换结果是 Banana 左值
}
const volatile int cvi = 1;
const int& r2 = cvi;                // error: 丢掉 volatile
struct A { operator volatile int&(); } a;
const int& r3 = a;                  // error: 转换结果丢掉 volatile
double d2 = 1.0;
double&& rrd2 = d2;                 // error: 引用相关类型的左值
struct X { operator int&(); };
int&& rri2 = X();                   // error: 转换结果是引用相关类型的左值
```

`banana2` 要走完整个流程。`operator const Banana()` 的结果 `const Banana` 与 `Banana` 不引用兼容（会丢掉 const），所以 ¶5.3.2 不适用。到了 ¶5.4，`Banana` 与 `Enigma` 不引用相关，进入 ¶5.4.1：转换函数的结果 E 是 `const Banana` 纯右值，再用 `(E)` 直接初始化 `Banana&&`，此时 `Banana` 与 `const Banana` 引用相关，被 ¶5.4 禁止。

## 直接绑定

¶5 末尾规定：除 ¶5.4.2（把初始化器隐式转换为被引用类型）之外，所有情形都称引用**直接绑定**（[[g:bind-directly|bind directly]]）到初始化表达式。¶5.4.1 中最后那次 `(E)` 直接初始化会回到 ¶5.1 或 ¶5.3，因此也算直接绑定。

这个概念主要用于重载决议。[[over.ics.ref]] 规定，引用形参直接绑定到实参时，隐式转换序列是恒等转换（或派生到基类转换）；不是直接绑定时，转换序列按转换到被引用类型来计算。[[over.ics.rank]] 中右值引用绑定右值优于左值引用等规则也建立在它之上。

是否直接绑定与寿命延长无关：只要引用最终绑定到实质化出的临时对象，就适用 [[class.temporary#6]] 的寿命延长。

## 位域

```cpp error
struct S { int bf : 3; } s;
int& r1 = s.bf;          // error: 非 const 引用不能绑定位域
const int& r2 = s.bf;    // OK：绑定到保存位域值的临时对象
```

位域不一定从字节边界开始，没有地址，所以引用不能直接绑定它：¶5.1.1 和 ¶5.3.1 都排除了位域。[[class.bit]] 的注 3 说明，`const int&` 绑定的是一个保存位域值的临时对象。

!!! lawyer "措辞上的空隙"
    严格按 ¶5 的文字，`const int& r2 = s.bf;` 不满足 ¶5.1.1（初始化器是位域），也不满足 ¶5.3.1（初始化器是左值），于是进入 ¶5.4；而 ¶5.4 要求 `int` 与 `int` 不引用相关，这里不满足。照字面读，程序非良构。但 [[class.bit]] 的注 3 明确说它绑定到临时对象，所有主流编译器也都接受。注不具规范效力，这是条文与设计意图之间的一处空隙。

## 临时对象活多久（¶6）

¶6 是一条注，指向 [[class.temporary]]。要点如下。

引用绑定到临时对象或它的子对象时，如果这个泛左值是经实质化、括号、数组下标、`.` 成员访问、`.*`、不涉及用户定义转换的 cast、条件运算符或逗号运算符得到的，临时对象的寿命就延长到与引用相同（[[class.temporary#6]]）。

经函数调用得到的引用不会延长寿命，包括 `std::max`、`std::move` 和返回 `const T&` 的成员函数，因为编译器不追踪函数内部返回的是什么。

```cpp run ub
#include <string>
#include <cstdio>
const std::string& id(const std::string& s) { return s; }
int main() {
  const std::string& ok = std::string(40, 'a');       // 寿命延长到 ok 的作用域结束
  const std::string& bad = id(std::string(40, 'b'));  // 临时对象在本行结束时销毁
  std::printf("%c %c\n", ok[0], bad[0]);              // UB：bad 悬垂
}
```

用 `-fsanitize=address` 运行会报告 `stack-use-after-scope`。

也有不延长的例外：绑定到函数调用中引用形参的临时对象、圆括号聚合初始化中绑定到引用成员的临时对象、*new-initializer* 中绑定到引用的临时对象，都只活到所在完整表达式结束（[[class.temporary#6]] 的 6.10–6.12 项）。

## 把必然悬垂的绑定变成编译错误

有些绑定一定会悬垂。C++ 逐步把它们从运行时的 UB 提前为编译错误。

### 成员初始化器

[[class.base.init#8]] 规定，在 *mem-initializer* 中把引用成员绑定到临时对象，程序非良构；[[class.base.init#13]] 对默认成员初始化器作了同样的规定，构造函数实际用到这个默认成员初始化器时报错。

```cpp error
struct A {
  A() : v(42) { }   // error: 临时对象只活到构造函数结束
  const int& v;
};
```

### 库：检测绑定到临时对象 {{c++23}}

[[P2255R2]] 新增了类型特征 `std::reference_constructs_from_temporary` 和 `std::reference_converts_from_temporary`，判断用某类型的表达式（直接或拷贝）初始化一个引用时，会不会把引用绑定到临时对象。这件事无法用普通的模板元编程判断，需要编译器内建支持。

标准库用它们删去了 `std::pair`、`std::tuple` 中会把引用成员绑定到临时对象的构造函数，并让 `INVOKE<R>` 在会返回悬垂引用时非良构（例如 `std::function<const T&()>` 包装返回 `T` 的函数）：

```cpp error
#include <tuple>
#include <string>
#include <type_traits>
static_assert(std::reference_constructs_from_temporary_v<const int&, long>);
static_assert(!std::reference_constructs_from_temporary_v<const int&, int&>);
std::tuple<const std::string&> t("abc");   // error: 引用元素会绑定到临时 string
```

### `return` 绑定临时对象 {{c++26}}

[[P2748R5]] 在 [[stmt.return#6]] 中规定：`return` 语句把返回的引用，或者返回对象的组成引用（constituent reference，[[intro.object]]），绑定到临时对象时，程序非良构。

```cpp error
auto&& f1() {
  return 42;     // error: 返回的引用绑定到临时对象
}
const double& f2() {
  static int x = 42;
  return x;      // error: int → double 创建了临时对象
}
auto&& id(auto&& r) { return static_cast<decltype(r)&&>(r); }
auto&& f3() {
  return id(42); // 良构，但返回的引用悬垂：经过了函数调用
}
```

`f2` 的作者以为返回的是静态变量 `x`，实际上 `const double&` 绑定的是从 `x` 转换出的临时 `double`（¶5.4.2）。C++23 中它良构，返回悬垂引用，使用即 UB；C++26 中它是编译错误。

这条规则豁免了标准为 `std::is_convertible` 虚构的那个函数（[[meta.rel]]），否则 `is_convertible_v<int, const int&>` 会变成 `false`。

!!! impl
    本机 Clang 23 在 `-std=c++2c` 下对 `f1`、`f2` 报错（returning reference to local temporary object），C++23 模式下只给警告。返回对象的引用成员绑定到临时对象时（如 `struct P { const int& r; }; P g() { return P{42}; }`）尚不报错，没有实现组成引用这一部分。

## 实现视角

!!! impl
    - 主流 ABI 中，引用成员和引用形参的表示与指针相同；局部引用变量通常被完全优化掉。
    - 寿命延长的临时对象是编译器生成的隐藏对象：自动存储期的引用对应栈上的隐藏局部变量，命名空间作用域的引用对应静态存储中的隐藏对象，随引用一起析构。
    - Clang 默认开启的 `-Wdangling` 系列能抓到不少立即悬垂的绑定，例如 `std::string_view sv = std::string("x");`。GCC 的 `-Wdangling-reference` 尝试检测把临时对象传给返回引用的函数，但有误报。

## 历史与演进

!!! history
    - C++98：非 const 左值引用只能绑定左值，const 引用可以绑定右值。类类型右值绑定到 const 引用时，实现可以先复制出一个临时对象再绑定，所以即使不复制，也要求拷贝构造函数可访问。
    - C++11：引入右值引用。类右值必须直接绑定，不再允许额外的复制。此后 ¶5 多次改写，以处理右值引用与转换函数的组合。
    - C++14 之后（缺陷报告）：在 *mem-initializer* 中把引用成员绑定到临时对象变为非良构。
    - C++17：[[P0135R1]] 引入临时量实质化，¶5.3 改用转换后的初始化器加实质化的措辞。
    - C++20 前后（缺陷报告）：引用相关改用相似类型定义，`const int* const& r = p;`（`p` 为 `int*`）直接绑定到 `p`，不再创建临时对象。
    - C++23：[[P2255R2]] 的类型特征，以及标准库中对悬垂绑定的禁止。
    - C++26：[[P2748R5]]，`return` 绑定临时对象非良构。

## 常见误解

!!! pitfall "`const T&` 形参加上返回引用"
    `const auto& m = std::max(a, b + 1);` 中 `b + 1` 的临时对象在本行结束时销毁，`m` 可能悬垂。寿命延长只对直接绑定临时对象的那个引用有效，穿不过函数调用。

!!! pitfall "看似绑定到变量，实际绑定到临时对象"
    `int i = 0; const long& r = i; i = 5;` 之后 `r` 仍是 0，因为 `r` 绑定的是转换出的临时 `long`。`void f(const long&)` 接收 `int` 实参时也一样。

!!! pitfall "范围 for 与链式调用"
    `for (auto& x : make_obj().items())` 中，C++20 及以前只有 `items()` 的结果绑定到隐藏的引用，`make_obj()` 返回的临时对象在初始化器结束时就销毁了。C++23 的 [[P2718R0]] 让 *for-range-initializer* 中的所有临时对象都活到循环结束（[[class.temporary#7]]）。

## 思考题

!!! question "思考题 1"
    下面每行绑定到什么？哪些非良构？
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

- `r1`：`make()` 是 `D` 纯右值，`B` 与 `D` 引用兼容，走 ¶5.3.1：实质化一个 `D` 临时对象，绑定到它的 `B` 子对象，寿命延长。
- `r2`：`d` 是左值。¶5.1 只管左值引用，¶5.3.1 要求右值，都不适用；¶5.4 要求 `B` 与 `D` 不引用相关，而 `B` 是 `D` 的基类，所以非良构。
- `r3`：`std::move(d)` 是 xvalue，走 ¶5.3.1，直接绑定到 `d` 的 `B` 子对象，不创建临时对象。
- `r4`：同 `r1`，绑定到实质化出的临时对象的 `B` 子对象，寿命延长。
- `r5`：非 const 左值引用，初始化器是右值，¶5.2 非良构。
</details>

!!! question "思考题 2"
    为什么 `double&& r = i;`（`i` 是 `int` 左值）良构，而 `int&& r = i;` 非良构？这种不对称合理吗？

<details markdown="1">
<summary>答案</summary>

`int&& r = i;`：`int` 与 `int` 引用相关，`i` 是左值。¶5.3 要求右值，¶5.4 要求不引用相关，都不满足，所以非良构。

`double&& r = i;`：`double` 与 `int` 不引用相关，走 ¶5.4.2，`i` 转换为 `double` 纯右值并实质化，`r` 绑定到这个新的临时对象。

这种不对称是合理的。右值引用的含义是可以拿走所绑定对象的资源。`int&& r = i;` 若合法，就等于允许拿走 `i` 的资源，而 `i` 之后还会被使用；`double&& r = i;` 绑定的是一个与 `i` 无关、别人用不到的临时对象，拿走它的资源是安全的。规则真正禁止的是把右值引用绑定到已有的左值对象。
</details>

!!! question "思考题 3"
    下面的 `get` 在 C++23 和 C++26 中分别怎样？
    ```cpp
    struct Cfg { long timeout; };
    const int& get(const Cfg& c) { return c.timeout; }
    ```

<details markdown="1">
<summary>答案</summary>

`c.timeout` 是 `const long` 左值，`int` 与 `long` 不引用相关，走 ¶5.4.2：转换为 `int` 纯右值并实质化，返回的引用绑定到这个临时对象。临时对象在 `return` 语句结束时销毁，返回的引用悬垂。

C++23 中程序良构，但使用返回值是 UB，编译器通常会警告。C++26 中 [[stmt.return#6]] 使它非良构，本机 Clang 23 在 `-std=c++2c` 下报错。
</details>
