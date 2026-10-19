---
title: 模板实参
summary: 模板实参怎样与模板形参匹配：类型和表达式有歧义时取类型，常量实参必须能初始化一个 static constexpr 变量且不能指向字符串字面量或临时对象，模板模板实参只要能接受形参允许的一切用法就匹配。
status: done
covers: temp.arg.general, temp.arg.type, temp.arg.nontype, temp.arg.template
papers: N4268, P0522R0, P0732R2, P1907R1, P2841
related: temp.param, temp.names, temp.type, expr.const.const, temp.func.order, temp.constr.order, class.access
tags: 模板, 模板实参, 常量模板实参, 模板模板实参, P0522
updated: 2026-10-19
---

!!! tldr
    - 模板实参既能读成类型又能读成表达式时，一律读成类型：`f<int()>()` 中的 `int()` 是函数类型。
    - 常量模板实参 `E` 必须能写成 `static constexpr T x = E;`，因此它是常量表达式，指针和引用只能指向静态存储期的对象，而且不允许窄化。
    - 指针或引用实参不能指向字符串字面量、临时对象、`typeid` 的结果或 `__func__`。要用字符串作模板实参，形参得是类类型，比如自己写的 `fixed_string`。
    - 模板实参中的名字在书写处做访问检查；模板对实参类型的私有成员没有特殊访问权。
    - 模板模板实参只要能接受形参允许的一切用法就匹配，所以 C++17 起 `std::vector` 可以传给 `template<class> class`。

[[temp.param]] 规定模板能声明哪些形参。这一页讲另一半：使用模板时，每个**模板实参**（template argument）怎样与形参对应，又怎样变成形参的值。标准把它分成通用规则 [temp.arg.general] 和三种实参各自的规则：类型、常量、模板。

## 实参的种类要与形参对上 [temp.arg.general]

¶1 每个模板实参的种类和类型都要与对应的形参一致：类型形参接受类型，常量形参接受值，模板模板形参接受模板。形参包对应零个或多个实参。

### 有歧义时取类型（¶4）

```cpp run title="type-wins.cpp" ok
#include <cstdio>
template<class T> void f() { std::puts("type"); }
template<int I>   void f() { std::puts("value"); }

int main() {
    f<int()>();   // int() 是"返回 int 的函数"类型：调用第一个 f
}
```

¶4 模板实参在语法上既能读成 *type-id* 又能读成表达式时，一律读成 *type-id*，不管对应的形参是什么。这和语句中"能当声明就当声明"的原则一致（[[stmt.ambig]]、[[dcl.ambig.res]]）。

即使只有 `template<int I> void f()` 一个模板，`f<int()>()` 也把 `int()` 当作类型，然后因为不匹配而失败，不会退回去把它读成值为 0 的表达式。按脚注 102，默认模板实参没有这种歧义，因为它的形式由形参决定。

### 名字形式的实参（¶3）{{c++26}}

¶3 实参是一个可能带限定的名字时，先查找这个名字，再按查找结果决定它的含义：

- ¶3.1 找到注入类名（类模板内部用来指称自身的名字，[[temp.local]]）时，如果对应的是类型模板模板形参，它表示类模板本身，否则表示当前的类型；
- ¶3.2 找到模板时，表示该模板；
- ¶3.3 找到类型或类型别名时，表示那个类型；
- ¶3.4 否则当作表达式。

¶3.1 的效果是，在类模板内部，`A` 既可以当类型 `A<T>` 用，也可以当模板 `A` 用：

```cpp run title="injected.cpp" ok
template<template<class> class TT> struct W {};
template<class T> struct V {};

template<class T>
struct A {
    W<A> w;   // 对应模板模板形参：A 是类模板
    V<A> v;   // 对应类型形参：A 是类型 A<T>
};
A<int> a;
int main() {}
```

### 空的 `<>` 不能省（¶6）

¶6 所有形参都有默认实参，或者只有一个形参包时，实参列表可以为空，但 `<>` 必须写出来：

```cpp title="empty-angle.cpp" error
template<class T = char> class String;
String<>* p;     // OK：String<char>
String* q;       // error

template<class... Elements> class Tuple;
Tuple<>* t;      // OK：Elements 为空
Tuple* u;        // error
```

C++17 起 `String s("x");` 可以省略 `<>`，那是类模板实参推导（[[over.match.class.deduct]]），`String` 在那里是一个待推导的占位符。`String*` 所在的位置不能用占位符。

### 重载集中的函数模板（¶9）

¶9 template-id 中的名字找到一个重载集时，非模板函数和形参与实参对不上的函数模板都被忽略。注 2：一个都对不上时，程序非良构。

```cpp run title="overload-set.cpp" ok
void f(int);
template<int N> int f() { return N; }
template<class T> int f() { return sizeof(T); }

int a = f<1>();        // 只剩 template<int N>
int b = f<double>();   // 只剩 template<class T>
int main() {}
```

### 访问检查在实参书写处进行（¶5）

```cpp title="access-arg.cpp" error
template<class T> class X {
    static T t;
};

class Y {
    struct S {};   // private
    X<S> x;        // OK：在 Y 内部，S 可以访问
};

X<Y::S> y;         // error: S 是 Y 的私有成员
```

¶5 注 1：模板实参中的名字，在它出现的地方接受访问控制。模板形参不是类成员，所以模板内部使用 `T` 时不再做访问检查。`X<S>` 在 `Y` 内部合法写出之后，`X` 里对 `Y::S` 的一切使用都不受影响。私有类型能通过模板流出类外，依据就在这里。

¶5 的后半句说，实参是类类型或类模板时，模板定义对实参的成员没有特殊访问权：

```cpp title="no-special-access.cpp" error
template<template<class TT> class T> class A {
    typename T<int>::S s;      // 要访问 B<int>::S
};

template<class U> class B {
    struct S {};               // private
};

A<B> b;                        // error: A 无权访问 B<int>::S
```

!!! lawyer "显式实例化不做访问检查"
    与 ¶5 相反，[[temp.explicit]] 规定显式实例化中的名字不受通常的访问检查。把 `&Class::private_member` 作为常量模板实参写进显式实例化，就能合法地拿到私有成员的指针，这个常见技巧依据的正是这一条。

## 类型模板实参 [temp.arg.type]

¶1 类型形参的实参必须是一个类型（*type-id*）。¶2 的例子和注说明，局部类型、没有名字的类型、不完整类型都可以：

```cpp run title="type-args.cpp" ok
template<class T> class X {};
template<class T> void f(T) {}
struct {} unnamed_obj;

void g() {
    struct A {};
    enum { e1 };
    typedef struct {} B;
    B b;
    X<A>  x1;          // 局部类型
    X<A*> x2;
    X<B>  x3;          // 没有名字的类（有 typedef 名）
    f(e1);             // 没有名字的枚举
    f(unnamed_obj);    // 没有名字的类
    f(b);
    (void)x1; (void)x2; (void)x3;
}

struct Incomplete;
X<Incomplete>* p;      // 不完整类型
int main() { g(); }
```

C++03 不允许局部类型和无名类型作模板实参，理由是它们没有链接，特化无法在别的翻译单元中被指称。C++11 取消了这个限制。这对 lambda 是必需的：每个 lambda 的闭包类型都是无名的局部类型，不能作模板实参的话，`std::sort(v.begin(), v.end(), [](int a, int b) { ... })` 就无法编译。

## 常量模板实参 [temp.arg.nontype]

### 能初始化一个 static constexpr 变量（¶1）

¶1 设常量形参的类型为 `T`，实参为 `E`。虚构一个声明

```cpp
T x = E ;
```

它必须满足定义一个静态存储期的 constexpr 变量时的全部要求（[[dcl.constexpr]]）。`T` 含有 `auto` 这样的占位符时，形参的类型就从这个声明推导；推导出的类型不能作常量形参类型（[[temp.param#11]]）时，程序非良构。

很多规则都由这个模型直接得出：

- 实参必须是常量表达式；
- 指针和引用只能指向具有静态存储期的对象或函数，局部变量的地址不行；
- `auto` 形参按 `auto x = E;` 推导：`B<'a'>` 中是 `char`，`B<void(0)>` 中是 `void`，后者不允许。

```cpp title="invented-decl.cpp" error
template<int& r> class A {};
extern int x;
A<x> a;                       // OK

void f(int p) {
    constexpr int& r = p;     // 按当前草案 OK，见下文
    A<r> a2;                  // error: 静态的 constexpr 引用不能引用 p
}

template<auto n> struct B {};
B<5>       b1;                // int
B<'a'>     b2;                // char
B<2.5>     b3;                // double（C++20 起）
B<void(0)> b4;                // error: 推导出 void
```

标准的例 1 把 `constexpr int& r = p;` 标为 OK。C++26 草案放宽了规则，在同一个函数内部，constexpr 引用可以引用自动变量（[[expr.const]]）。但 `A<r>` 仍然非法，因为虚构的是一个静态存储期的变量，它不能引用 `p`。截至写作时，本机 Clang 23 还没有实现这项放宽，`constexpr int& r = p;` 本身也报错。

### 非类类型：不允许窄化（¶2）

¶2 形参不是类类型、实参也不是花括号列表时，实参必须是形参类型的**转换常量表达式**（converted constant expression，[[expr.const.const]]）：只允许少数几种隐式转换，而且不允许窄化。形参的值就是转换后的实参。

```cpp title="converted.cpp" error
template<char c> struct X {};
template<unsigned u> struct U {};

X<'a'> x1;        // OK
X<65>  x2;        // OK：65 能用 char 表示
X<300> x3;        // error: 窄化
U<-1>  u1;        // error: 窄化
U<1.0> u2;        // error: 浮点到整数的转换不允许
```

常量实参决定类型的身份。如果 `X<300>` 悄悄变成 `X<44>`，两者就成了同一个类型，这几乎不会是程序员的本意。

¶8 的例子列出了允许的几种转换：数组到指针、加 const、从重载集中选出函数。

```cpp run title="arg-conversions.cpp" ok
template<const int* pci> struct X {};
int ai[10];
X<ai> xi;                  // 数组到指针，再加 const

struct Y {};
template<const Y& b> struct Z {};
Y y;
Z<y> z;                    // 没有转换，引用多了 const

template<int (&pa)[5]> struct W {};
int b[5];
W<b> w;                    // 没有转换

void f(char);
void f(int);
template<void (*pf)(int)> struct A {};
A<&f> a;                   // 重载决议选中 f(int)

template<int i> struct C {};
C<{ 42 }> c1;              // 花括号列表，见 ¶5

void f(char) {}
void f(int) {}
int main() {}
```

`C<{ 42 }>` 是合法的，本机 Clang 23 会给出一条 `-Wbraced-scalar-init` 警告。

### 类类型：复制出唯一的模板形参对象（¶3–¶5）

¶3 形参是类类型，或者实参是花括号列表时，标准引入一个临时变量

```cpp
constexpr T v = A;
```

它在初始化完成后立即结束生命周期。这样的 `v` 叫做**候选初始化器**（candidate initializer）。

¶5 对非类类型（实参是花括号列表的情况），形参的值就是 `v` 的值，所以 `template<int i>` 可以接受 `C<{42}>`。

¶4 对类类型，形参指称一个模板形参对象（[[temp.param#13]]），它是从某个与 `v` 等价的候选初始化器复制初始化来的。下面任一情况发生，程序就非良构：

- ¶4.1 这次初始化本身非良构；
- ¶4.2 初始化不是常量表达式；
- ¶4.3 复制得到的对象与 `v` 不是模板实参等价的（[[temp.type]]）。

为什么这么绕？同一个值在整个程序里只有一个模板形参对象，但不同的翻译单元可以用不同的实参表达式写出这个值。标准要保证不管从哪个表达式复制，得到的对象都一样。如果复制构造函数改变了值，就无法确定那个唯一的对象，¶4.3 因此判它非良构。

```cpp title="candidate-init.cpp" error
template<auto> struct B {};

struct J1 {
    J1* self = this;     // 指向自身
};
B<J1{}> j1;    // error: 初始化不是常量表达式（¶4.2）

struct J2 {
    J2* self = this;
    constexpr J2() {}
    constexpr J2(const J2&) {}   // 复制后 self 指向新对象
};
B<J2{}> j2;    // error: 副本与 v 不等价（¶4.3）
```

本机 Clang 23 拒绝这两行，但给出的理由都是 "pointer to temporary object is not allowed in a template argument"，即下一节 ¶6 的检查。结论相同。

### 指针和引用不能指向什么（¶6）

¶6 引用或指针类型的常量实参，以及类类型实参中引用或指针类型的成员，都不能引用或指向：

- ¶6.1 临时对象（[[class.temporary]]）；
- ¶6.2 字符串字面量对象（[[lex.string]]）；
- ¶6.3 `typeid` 表达式的结果（[[expr.typeid]]）；
- ¶6.4 预定义变量 `__func__`（[[dcl.fct.def.general]]）；
- ¶6.5 以上对象的子对象。

这些对象的共同点是身份不稳定。两个相同的字符串字面量是不是同一个对象，标准不作规定，不同翻译单元里通常是不同的对象。`typeid(int)` 的结果在不同的共享库里可能是不同的对象；每个函数有自己的 `__func__`。如果允许它们作模板实参，`X<"abc">` 在两个翻译单元里可能是两个不同的类型。

清单之外的都可以，包括 C++20 起的子对象地址和尾后指针：

```cpp run title="subobject-ptr.cpp" ok
int arr[3];
struct S { int m; } s;

template<int* p> struct P {};
P<&arr[1]> pa;      // 数组元素的地址（C++20 起）
P<&s.m>    pm;      // 成员的地址（C++20 起）
P<&arr[3]> pe;      // 尾后指针
P<nullptr> pn;
int main() {}
```

C++17 及以前，指针实参必须指向完整对象，也不能是尾后指针。C++20 的 [[P1907R1]] 去掉了这些限制。

### 字符串作模板实参（¶9）

<div class="compare" markdown="1">

```cpp error
template<const char* p>
struct X {};

X<"Studebaker"> x;  // error
X<"Knope" + 1> x2;  // error: 子对象

const char p[] = "Vivisectionist";
X<p> y;             // OK：具名数组
```

```cpp ok
struct A {
  constexpr A(const char*) {}
};
template<A a> struct Y {};

// 字面量只是构造函数的实参
Y<"Pyrophoricity"> z;
```

</div>

¶9 注 2：字符串字面量不能作非类类型常量形参的实参，因为它的值会指向字符串字面量对象（¶6.2）。左边的 `p` 是一个用字面量初始化的具名数组，它本身不是字符串字面量对象，所以可以。

右边是 C++20 起用字符串作模板实参的方法：形参是类类型，字面量只用来初始化模板形参对象。下面的 `fixed_string` 把字符复制进自己的数组，模板形参对象保存的是字符的值，而不是指向字面量的指针：

```cpp run title="fixed-string.cpp" ok
#include <cstddef>
#include <cstdio>
#include <type_traits>

template<std::size_t N>
struct fixed_string {
    char data[N]{};
    constexpr fixed_string(const char (&s)[N]) {
        for (std::size_t i = 0; i < N; ++i) data[i] = s[i];
    }
};

template<fixed_string S>   // 推导类类型的占位符（[temp.param]/11.3）
struct Named {
    static void print() { std::puts(S.data); }
};

static_assert(!std::is_same_v<Named<"a">, Named<"b">>);
static_assert(std::is_same_v<Named<"a">, Named<"a">>);   // 按值比较

int main() { Named<"hello">::print(); }
```

`fixed_string` 里如果存一个 `const char*`，就又回到了指向字符串字面量的情形。

### 引用不能绑定到临时对象（¶10）

¶10 注 3：形参是引用类型时，需要临时对象的实参不能用：

```cpp title="temporary-arg.cpp" error
template<const int& CRI> struct B {};
B<1> b1;                  // error: 需要一个临时对象
int c = 1;
B<c> b2;                  // OK

struct X { int n; };
struct Y { const int& r; };
template<Y y> struct C {};
C<Y{X{1}.n}> c;           // error: 引用成员绑定到临时对象的子对象
```

## 模板模板实参 [temp.arg.template]

### 实参必须是模板的名字（¶1–¶3）

¶1 模板模板形参的实参必须是一个模板的名字。¶3 规定了哪种形参能接受哪种模板，满足这一条的形参和实参叫做**兼容的**（compatible）：

| 形参 | 实参 |
|---|---|
| 类型模板模板形参 `template<...> class` | 类模板、别名模板，或另一个类型模板模板形参 |
| 变量模板模板形参 `template<...> auto` {{c++26}} | 变量模板，或另一个变量模板模板形参 |
| 概念模板形参 `template<...> concept` {{c++26}} | 概念，或另一个概念模板形参 |

匹配时只看主模板，部分特化即使形参列表合适也不考虑。¶2 但是，通过模板模板形参使用特化时，主模板的部分特化照常参与选择：

```cpp run title="tt-partial.cpp" ok
#include <type_traits>
template<class T> class A { public: int x; };        // 主模板
template<class T> class A<T*> { public: long x; };   // 部分特化

template<template<class U> class V> class C {
public:
    V<int>  y;     // 用主模板：y.x 是 int
    V<int*> z;     // 用部分特化：z.x 是 long
};

C<A> c;
static_assert(std::is_same_v<decltype(c.y.x), int>);
static_assert(std::is_same_v<decltype(c.z.x), long>);
int main() {}
```

如果某个部分特化在实例化点不可达，而它可达的话本应被选中，程序非良构，不要求诊断。

### 形参能用的，实参都要能接受（¶4–¶5）

```cpp run title="p0522.cpp" ok
#include <vector>

template<template<class> class C>
struct Wrap { C<int> c; };

Wrap<std::vector> w;   // OK（C++17 起）

template<class T> class A {};
template<class T, class U = T> class B {};
template<class... Types> class C {};
template<auto n> class D {};
template<template<class> class P> class X {};
template<template<class...> class Q> class Y {};
template<template<int> class R> class Z {};

X<A> xa;   // OK
X<B> xb;   // OK：U 有默认实参（C++17 前非良构）
X<C> xc;   // OK：包可以接受一个实参
Y<A> ya;   // OK
Y<B> yb;   // OK
Y<C> yc;   // OK
Z<D> zd;   // OK：auto 形参可以接受 int 值（C++17 前非良构）
int main() {}
```

`template<template<class> class C>` 等于承诺：模板内部只会写 `C<X>` 这种带一个类型实参的形式。`std::vector` 有两个形参，但第二个有默认实参，`std::vector<X>` 完全合法，所以它是合格的实参。

¶4 精确的说法是：实参 `A` 与形参 `P` 兼容，并且 `P` **至少和 `A` 一样特殊**（at least as specialized）时，`A` 匹配 `P`。如果 `P` 没有约束，就忽略 `A` 的约束。

¶5 至少一样特殊的判断方法是把两者改写成函数模板，再套用函数模板的偏序规则（[[temp.func.order]]）。设想一个类模板 `X`，它的模板头和 `A` 完全相同，包括默认实参和约束；再写两个函数模板，模板形参分别取自 `P` 和 `A`，各有一个类型为 `X<...>` 的函数形参。以 `P = template<class> class`、`A = std::vector` 为例：

```cpp
template<class T, class Alloc = std::allocator<T>> class X;   // 模板头取自 A

template<class T>              void fP(X<T>);          // 对应 P
template<class T, class Alloc> void fA(X<T, Alloc>);   // 对应 A
```

`X<T>` 就是 `X<T, std::allocator<T>>`，从 `fP` 的形参可以推导出 `fA` 的 `T` 和 `Alloc`，所以 `fP` 至少和 `fA` 一样特殊，`std::vector` 匹配。改写如果得到无效的类型，`P` 就不比 `A` 特殊。

¶4 的后半部分处理 `P` 含形参包的情形：这时只要 `A` 的每个形参都与 `P` 的对应形参匹配，`A` 也匹配 `P`。两个形参匹配，指种类相同、常量形参的类型等价（[[temp.over.link]]）、模板模板形参的形参递归匹配。`P` 中的形参包可以对应 `A` 中零个或多个种类相同的形参，不管它们是不是包。所以 `Y<A>`、`Y<B>` 合法，尽管在 `Y` 里写 `Q<int, int, int>` 会在实例化时出错：

```cpp title="pack-tt-use.cpp" error
template<class T, class U = T> class B {};
template<template<class...> class Q> struct Y1 { Q<int, int, int> q; };
Y1<B> y;    // 匹配成功，但实例化时 B<int, int, int> 实参过多：error
```

### 带约束的匹配

¶4 例 4 展示了约束怎样参与匹配。`P` 至少和 `A` 一样特殊，意味着 `P` 的约束必须包含（subsume，[[temp.constr.order]]）`A` 的约束：

```cpp title="tt-constraints.cpp" error
template<typename T> concept C = requires (T t) { t.f(); };
template<typename T> concept D = C<T> && requires (T t) { t.g(); };

template<template<C> class P> struct S {};

template<C> struct X {};
template<D> struct Y {};
template<typename T> struct Z {};

S<X> s1;   // OK：约束相同
S<Y> s2;   // error: Y 要求 D，比 P 保证的 C 更严
S<Z> s3;   // OK：Z 没有约束
```

`S` 内部只保证用满足 `C` 的类型去实例化 `P`。`Y` 要求 `D`，`S` 就可能把一个只满足 `C` 的类型交给它，所以被拒绝。`Z` 接受任何类型，是安全的。

`P` 没有约束时忽略 `A` 的约束，所以 `template<template<class> class P>` 可以接受 `template<std::integral T> class A`。这是为了兼容 C++20 以前的代码：已有的模板模板形参大都没有约束，如果一律拒绝带约束的实参，标准库组件一加约束，大量用户代码就会失效。代价是，在 `P` 里写 `P<double>`，要到实例化时才会因约束不满足而报错。

### 不存在能匹配任何类模板的形参

```cpp title="eval.cpp" error
template<class T> struct eval;
template<template<class, class...> class TT, class T1, class... Rest>
struct eval<TT<T1, Rest...>> {};

template<class T1> struct A;
template<class T1, class T2> struct B;
template<int N> struct C;
template<class T1, int N> struct D;
template<class T1, class T2, int N = 17> struct E;

eval<A<int>> eA;           // OK：匹配部分特化
eval<B<int, float>> eB;    // OK
eval<C<17>> eC;            // error: C 的形参是常量形参
eval<D<int, 17>> eD;       // error: D 的第二个形参是常量形参
eval<E<int, float>> eE;    // error: E 有常量形参，即使有默认实参
```

`template<class, class...> class TT` 看起来能匹配任何类模板，但常量形参和类型形参永远不能互相匹配。后三行的部分特化不匹配，于是用到了只有声明的主模板 `eval`，因而报错。

## 实现视角

!!! impl
    - [[P0522R0]] 在 C++17 中放宽了模板模板实参的匹配，但它带来了新的偏序歧义：同一个实参可能同时匹配多个部分特化中的模板模板形参。Clang 因此长期默认不启用它，需要 `-frelaxed-template-template-args`；近年的版本已默认启用。本机 Clang 23 默认接受上面的 `Wrap<std::vector>`。
    - Clang 对 ¶6 的各项违规给出具体原因，如 "pointer to temporary object is not allowed in a template argument"、"reference to type_info object is not allowed in a template argument"。
    - 类类型常量实参的模板形参对象在目标文件中是一个可合并的只读常量，见 [[temp.param]] 的实现视角。

## 历史与演进

!!! history
    - C++98/03：常量实参只能是整型常量表达式，或者具有外部链接的对象、函数的地址，且必须写成 `&obj` 的形式；局部类型和无名类型不能作类型实参。
    - C++11：允许内部链接的对象、`nullptr` 和值为空指针的常量表达式；局部类型、无名类型可以作类型实参。
    - C++17：所有常量实参都可以是一般的转换常量表达式（[[N4268]]）；放宽模板模板实参的匹配（[[P0522R0]]）；`template<auto>`。
    - C++20：类类型和浮点类型的常量实参（[[P0732R2]]、[[P1907R1]]）；允许指向子对象的指针和引用；约束参与模板模板实参的匹配。
    - C++26：概念和变量模板可以作模板模板实参（[[P2841]]）；名字形式实参的解释规则（¶3）；"非类型"改称"常量"。

## 常见误解

!!! pitfall "C++20 起字符串字面量总能作模板实参"
    `X<"abc">` 只有当 `X` 的形参是类类型（如 `fixed_string`）时才可以。`const char*` 形参永远不接受字符串字面量（¶6.2、¶9）。

!!! pitfall "`template<char c>` 接受 `X<300>` 并截断"
    转换常量表达式不允许窄化，`X<300>` 非良构（¶2）。

!!! pitfall "无约束的模板模板形参会拒绝带约束的实参"
    不会。`P` 没有约束时忽略实参的约束，问题要到实例化时才暴露（¶4）。

## 思考题

!!! question "思考题 1"
    下面哪些模板实参合法？

    ```cpp
    template<const char* p> struct S {};
    static const char a[] = "x";
    constexpr const char* q = "y";
    S<a> s1;          // (a)
    S<q> s2;          // (b)
    S<&a[1]> s3;      // (c)
    ```

<details markdown="1">
<summary>答案</summary>

- (a) 合法。`a` 是用字面量初始化的具名数组，不是字符串字面量对象，做数组到指针转换即可。
- (b) 非法。`q` 的值指向字符串字面量对象（¶6.2）。
- (c) 合法（C++20 起）。`a` 有两个元素 `'x'` 和 `'\0'`，`&a[1]` 指向具名数组的一个元素。
</details>

!!! question "思考题 2"
    给定

    ```cpp
    template<std::integral T> struct I {};
    template<std::signed_integral T> struct J {};
    template<template<class> class P> struct S1 {};
    template<template<std::integral T> class P> struct S2 {};
    template<template<std::signed_integral T> class P> struct S3 {};
    ```

    `S1<I>`、`S2<J>`、`S3<I>` 中哪些合法？

<details markdown="1">
<summary>答案</summary>

- `S1<I>` 合法：`P` 没有约束，忽略 `I` 的约束（¶4）。
- `S2<J>` 非法：`P` 的约束是 `std::integral<T>`，`J` 要求 `std::signed_integral<T>`。标准库把后者定义为 `integral<T> && is_signed_v<T>`，前者不包含后者，`P` 不比 `J` 特殊。
- `S3<I>` 合法：`std::signed_integral<T>` 规范化后包含 `std::integral<T>`，`S3` 只会用有符号整数实例化 `P`，`I` 都能接受。

判断包含关系要看概念的定义规范化之后的结果，而不是概念的名字。
</details>

<details class="fine" markdown="1"><summary>其余条文</summary>

[temp.arg.general] ¶2 定义模板头的实参列表：第 n 个实参就是第 n 个形参本身，形参是包 `Ts` 时对应包展开 `Ts...`。它用来描述主模板自身，比如部分特化的实参列表不能与它完全相同（[[temp.spec.partial]]）。

¶7 对类模板特化的对象显式调用析构函数时，可以写出模板实参：`p->A<int>::~A()` 和 `q->A<int>::~A<int>()` 都可以。本机 Clang 23 在 `-pedantic` 下对前一种给出 `-Wdtor-name` 警告，标准的例子把它标为 OK。

¶8 使用某个模板实参导致特化的实例化中出现非良构的构造时，程序非良构。函数模板推导中的替换失败另由 [[temp.deduct]] 处理。

¶10 template-id 不指称函数时，默认模板实参在需要它的值时才隐式实例化，例如 `S<bool>*` 要用到 `S<bool, int>` 中的 `int`。

¶11 后面跟省略号的模板实参是包展开（[[temp.variadic]]）。

</details>
