---
title: 模板实参
summary: 模板实参与模板形参如何匹配：类型/表达式歧义一律取类型；访问检查发生在实参书写处；常量模板实参的"虚构 constexpr 声明"模型、类类型实参的模板形参对象、指针/引用不得指向临时对象与字符串字面量；模板模板实参的"至少一样特殊"匹配（P0522）。
status: done
covers: temp.arg.general, temp.arg.type, temp.arg.nontype, temp.arg.template
papers: N4268, P0522R0, P1907R1, P2841
related: temp.param, temp.names, temp.type, expr.const.const, temp.func.order, temp.constr.order, class.access
tags: 模板, 模板实参, 常量模板实参, 模板模板实参, P0522
updated: 2026-10-17
---

[[temp.param]] 规定了模板的"端口"，本节规定"插头"：每种形参能接受什么样的实参、实参如何转换成形参的值。它由四个子节组成：

| 子节 | 内容 |
|---|---|
| [temp.arg.general] | 通用规则：形式匹配、名字形式实参的解释、类型/表达式歧义、访问检查、空 `<>`、默认实参的实例化 |
| [temp.arg.type] | 类型模板实参：必须是 *type-id* |
| [temp.arg.nontype] | 常量模板实参：值如何确定；类类型实参与模板形参对象；指针和引用的限制 |
| [temp.arg.template] | 模板模板实参：兼容性与"至少一样特殊"的匹配规则 |

## 通用规则（[temp.arg.general]）

### 类型与形式必须匹配（¶1–¶2）

¶1 *template-id* 中每个 *template-argument* 的**类型和形式**必须与模板为对应形参声明的类型和形式相匹配：类型形参对应类型，常量形参对应值，模板模板形参对应模板。形参包对应零个或多个实参。

¶2 定义了 ***template-head* 的模板实参列表**：第 n 个实参就是第 n 个形参本身的"值"；若第 n 个形参是包 `Ts`，则第 n 个实参是包展开 `Ts...`。这是一个技术性定义，用于描述"主模板自身的 *template-id*"，比如判断部分特化是否与主模板相同（[[temp.spec.partial]]：部分特化的实参列表不能与主模板的这个列表一模一样）。

### 名字形式的实参如何解释（¶3）{{c++26}}

¶3 若 *template-argument* `A` 匹配 *template-argument-name* 形式（一个可能带限定的标识符），就按名字解释，查找其标识符：

- ¶3.1 若找到**注入类名**（[[temp.local]]）：`A` 对应类型模板模板形参时，表示对应的**类模板**；否则表示一个类型名。
- ¶3.2 否则，若找到**模板**，`A` 表示该模板。
- ¶3.3 否则，若找到类型别名或类型，`A` 表示其底层类型，按 *type-id* 解释。
- ¶3.4 否则，`A` 按**表达式**解释。

¶3.1 是一条老规则的新表述：在类模板内部，注入类名 `A` 既可以当类型 `A<T>` 用，也可以当模板 `A` 用，取决于它对应什么样的形参。

```cpp run title="injected.cpp" ok
template<template<class> class TT> struct W {};
template<class T> struct V {};

template<class T>
struct A {
    W<A> w;           // A 对应类型模板模板形参 ⇒ 表示类模板 A
    V<A> v;           // A 对应类型形参 ⇒ 表示类型 A<T>
};
A<int> a;
int main() {}
```

### 类型优先（¶4）

¶4 在 *template-argument* 中，*type-id* 与表达式之间的歧义**一律解析为 *type-id***，**不管**对应形参是什么形式。这是 [[stmt.ambig]]/[[dcl.ambig.res]]"能当声明就当声明"原则在模板实参中的翻版。

```cpp run title="type-wins.cpp" ok
#include <cstdio>
template<class T> void f() { std::puts("type"); }
template<int I>   void f() { std::puts("value"); }

int main() {
    f<int()>();       // int() 是 type-id（返回 int 的函数类型）：调用第一个 f
}
```

注意"不管对应形参是什么"：即使只有 `template<int I> void f()`，`f<int()>()` 也会把 `int()` 当作类型，然后因为不匹配而失败，而不会退而把 `int()` 解释为值初始化表达式 `0`。脚注 102 说明默认模板实参没有这个歧义——默认实参的形式由形参决定。

### 访问检查发生在实参书写处（¶5）

¶5 注 1：模板实参中使用的名字**在其出现的地方**接受访问控制。由于模板形参不是类成员，在模板内部**使用**模板形参时不进行访问检查。

```cpp title="access-arg.cpp" error
template<class T> class X {
    static T t;
};

class Y {
    struct S {};
    X<S> x;       // OK: 在 Y 内部，S 可访问
                  //     X<Y::S> 有一个 Y::S 类型的静态成员——OK，即使 Y::S 是 private
};

X<Y::S> y;        // error: S 不可访问
```

这是"私有类型可以通过模板泄露"的标准依据：`X<S>` 在 `Y` 内部合法地写出后，模板内部对 `T` 的一切使用都不再检查访问。

¶5 后半：对于类类型或类模板的模板实参，模板定义对模板实参的成员**没有特殊访问权**：

```cpp title="no-special-access.cpp" error
template<template<class TT> class T> class A {
    typename T<int>::S s;       // 访问 B<int>::S
};

template<class U> class B {
    struct S {};                // private
};

A<B> b;                         // error: A 无权访问 B<int>::S
```

!!! lawyer "显式实例化的访问豁免"
    与 ¶5 相对，[[temp.explicit]] 规定**显式实例化**中的名字不受通常的访问检查——这是著名的"通过显式实例化合法地访问私有成员"技巧的来源（把 `&Class::private_member` 作为常量模板实参写在显式实例化里）。

### 空 `<>` 不可省略（¶6）

¶6 使用形参包或默认模板实参时，实参列表可以为空，但**空的 `<>` 必须写**：

```cpp title="empty-angle.cpp" error
template<class T = char> class String;
String<>* p;          // OK: String<char>
String* q;            // error（在此语境中）: 不能省略 <>

template<class... Elements> class Tuple;
Tuple<>* t;           // OK: Elements 为空
Tuple* u;             // error
```

注意 C++17 起，`String s("x");` 这种**声明带初始化器**的写法可以省略 `<>`——那是类模板实参推导（CTAD，[[over.match.class.deduct]]），`String` 在那里作为"推导类类型的占位符"使用；而 `String*` 不是能使用占位符的语境。

### 显式析构函数调用（¶7）

¶7 对类模板特化类型对象的显式析构函数调用可以显式写出模板实参：

```cpp run title="dtor-call.cpp" ok
template<class T> struct A { ~A() {} };
void f(A<int>* p, A<int>* q) {
    p->A<int>::~A();          // OK
    q->A<int>::~A<int>();     // OK
}
int main() {}
```

### 实例化中的错误；重载集；默认实参的实例化（¶8–¶11）

¶8 如果使用某个模板实参导致模板特化的实例化中出现非良构的构造，程序非良构。（这是"硬错误"的一般规定；函数模板推导期间的替换失败由 [[temp.deduct]] 另行处理。）

¶9 当 *template-id* 的组成名字的查找找到一个**重载集**时，重载集中的**非模板函数**、以及模板形参与实参**不匹配**的函数模板都被忽略。注 2：若没有任何函数模板的形参匹配，程序非良构。

```cpp run title="overload-set.cpp" ok
void f(int);
template<int N> int f() { return N; }
template<class T> int f() { return sizeof(T); }

int a = f<1>();        // 非模板 f(int) 被忽略；template<class T> 不匹配 1，被忽略
int b = f<double>();   // template<int N> 不匹配 double，被忽略
int main() {}
```

¶10 当 *simple-template-id* 不指称函数时，默认模板实参在**其值被需要时**隐式实例化：`S<bool>*` 中 `S<bool, int>` 的 `int` 被实例化以形成类型。

¶11 后跟省略号的 *template-argument* 是包展开（[[temp.variadic]]）。

## 类型模板实参（[temp.arg.type]）

¶1 类型模板形参的实参必须是 *type-id*。

¶2 例子与注：**局部类型、无名类型、无链接的类型**都可以作模板实参；模板类型实参可以是**不完整类型**。

```cpp run title="type-args.cpp" ok
template<class T> class X {};
template<class T> void f(T) {}
struct {} unnamed_obj;

void g() {
    struct A {};
    enum { e1 };
    typedef struct {} B;
    B b;
    X<A>  x1;          // OK: 局部类型
    X<A*> x2;          // OK
    X<B>  x3;          // OK: 无名类型（有 typedef 名）
    f(e1);             // OK: 无名枚举类型
    f(unnamed_obj);    // OK: 无名类类型
    f(b);              // OK
    (void)x1; (void)x2; (void)x3;
}

struct Incomplete;
X<Incomplete>* p;      // OK: 不完整类型可以作模板实参
int main() { g(); }
```

C++03 中局部类型和无名类型**不能**作模板实参（理由是它们没有链接，特化无法跨 TU 命名）。C++11 取消了这一限制——这对 lambda 至关重要：每个 lambda 的闭包类型都是无名的局部类型，若不能作模板实参，`std::sort(v.begin(), v.end(), [](int a, int b){...})` 根本无法工作。

## 常量模板实参（[temp.arg.nontype]）

本子节旧称 "Template non-type arguments"，{{c++26}} 草案随术语变更改为 "Constant template arguments"。它的现行表述非常统一：**一切都归结为"能否初始化一个 static constexpr 变量"**。

### 虚构声明模型（¶1）

¶1 形参的声明类型为 `T`，实参为 `E`，则虚构的声明

```cpp
T x = E ;
```

必须满足**定义一个具有静态存储期的 constexpr 变量**的语义约束（[[dcl.constexpr]]）。若 `T` 含有占位符类型（`auto`）或推导类类型的占位符，形参的类型就从这个声明推导；推导出的类型若不允许作常量模板形参（[[temp.param#11]]），程序非良构。

这个模型一举解释了大量规则：

- 必须是**常量表达式**（constexpr 变量的初始化器必须是常量表达式）；
- 引用和指针必须指向**具有静态存储期**的对象或函数（constexpr 变量不能保存局部变量的地址）；
- `auto` 形参的类型推导与 `auto x = E;` 相同（`B<'a'>` 推导为 `char`，`B<void(0)>` 推导为 `void`——不允许）。

```cpp title="invented-decl.cpp" error
template<int& r> class A {};
extern int x;
A<x> a;                       // OK: static constexpr int& v = x; 合法

void f(int p) {
    constexpr int& r = p;     // OK（C++26 草案）：p 从此处是 constexpr-referenceable 的
    A<r> a2;                  // error: static constexpr int& 不能被初始化为引用 p
}

template<auto n> struct B {};
B<5>       b1;                // OK: int
B<'a'>     b2;                // OK: char
B<2.5>     b3;                // OK: double（C++20）
B<void(0)> b4;                // error: 推导出 void，不允许
```

（标准例 1 把 `constexpr int& r = p;` 注为 OK：{{c++26}} 当前草案引入了 **constexpr-referenceable** 的概念（[[expr.const.defns#2]]），自动存储期对象在同一函数内对 constexpr 变量而言是可引用的。但 `A<r>` 仍然非法，因为虚构的是**静态存储期**的 constexpr 变量，`p` 从那里不可引用。截至写作时，Clang 23 尚未实现这一放宽，对 `constexpr int& r = p;` 本身也报错。）

### 非类类型：转换常量表达式（¶2）

¶2 形参 `P` 的（可能推导出的）类型为 `T`、实参为 `A`。若 `T` **不是类类型**且 `A` **不是** *braced-init-list*，`A` 必须是类型 `T` 的**转换常量表达式**（converted constant expression，[[expr.const.const]]），`P` 的值就是（转换后的）`A`。

转换常量表达式只允许有限的隐式转换，并且**禁止窄化**：

```cpp title="converted.cpp" error
template<char c> struct X {};
template<unsigned u> struct U {};

X<'a'> x1;        // OK
X<65>  x2;        // OK: 65 能被 char 精确表示
X<300> x3;        // error: 窄化（300 超出 char 的范围）
U<-1>  u1;        // error: 窄化（-1 不能表示为 unsigned）
U<1.0> u2;        // error: 浮点到整数的转换不允许
```

为什么禁止窄化？因为常量模板实参决定类型身份：如果 `X<300>` 被悄悄转换成 `X<44>`，`X<300>` 和 `X<44>` 就是同一个类型——这几乎肯定不是程序员想要的。

### 类类型与 braced-init-list：候选初始化器（¶3–¶5）

¶3 否则（`T` 是类类型，或 `A` 是 *braced-init-list*），引入一个临时变量

```cpp
constexpr T v = A;
```

它的生命周期在初始化完它和模板形参对象之后立即结束。每个这样的变量的 *id-expression* `v` 称为**候选初始化器**（candidate initializer）。

¶4 若 `T` 是**类类型**，存在一个模板形参对象（[[temp.param#13]]），构造为与 `v` **模板实参等价**；`P` 表示这个模板形参对象。`P` 从一个**未指明的**、与 `v` 模板实参等价的候选初始化器**复制初始化**。如果对任何候选初始化器：

- ¶4.1 初始化非良构，或
- ¶4.2 虚构的 *init-declarator* 的完整表达式不是常量表达式，或
- ¶4.3 初始化导致 `P` 与 `v` **不**模板实参等价，

则程序非良构。

¶5 否则（非类类型，`A` 是 *braced-init-list*），`P` 的值就是 `v` 的值——所以 `C<{42}>` 对 `template<int i>` 是合法的。

为什么要这么绕？因为类类型的模板形参对象是**全程序唯一**的（每个值一个），而同一个值可能被不同 TU 中的不同实参表达式写出。标准需要保证：无论从哪个实参表达式"复制"出模板形参对象，结果都一样。¶4.3 就是这个保证：如果复制构造函数会改变值（使副本与原值不等价），就无法定义"那个唯一的对象"，程序非良构。

```cpp title="candidate-init.cpp" error
template<auto> struct B {};

struct J1 {
    J1* self = this;                       // 指向自身
};
B<J1{}> j1;    // error: 模板形参对象的初始化不是常量表达式
               //        （self 指向临时对象 v，见 ¶6）

struct J2 {
    J2* self = this;
    constexpr J2() {}
    constexpr J2(const J2&) {}             // 复制时 self 指向新对象
};
B<J2{}> j2;    // error: 模板形参对象与引入的临时变量 v 不模板实参等价（¶4.3）
```

!!! impl "编译器现状"
    Clang 23 拒绝上面两个例子，但给出的理由都是"指向临时对象的指针不允许作为模板实参"（即 ¶6 的检查），而不是 ¶4.3 所说的"不模板实参等价"。结论相同。

### 指针和引用的限制（¶6）

¶6 对于引用或指针类型的常量模板形参，以及类类型常量模板形参（或其子对象）中引用或指针类型的非静态数据成员，其值**不能**引用或指向：

- ¶6.1 **临时对象**（[[class.temporary]]）；
- ¶6.2 **字符串字面量对象**（[[lex.string]]）；
- ¶6.3 **`typeid` 表达式的结果**（[[expr.typeid]]）；
- ¶6.4 预定义的 **`__func__` 变量**（[[dcl.fct.def.general]]）；
- ¶6.5 以上任何对象的**子对象**。

共同点：这些对象的**身份不稳定**——同一个字符串字面量在不同 TU 中可能是不同对象（或在同一 TU 中被合并、也可能不合并，这是未指明的），`typeid(int)` 的结果对象在不同 TU/共享库中可能不同，`__func__` 是每个函数的局部静态数组。如果允许它们作为模板实参，`X<"abc">` 在两个 TU 中可能是两个不同的类型，ODR 无从谈起。

注意这个清单**之外**的东西都允许，包括（C++20 起）**子对象的地址**和**尾后指针**：

```cpp run title="subobject-ptr.cpp" ok
int arr[3];
struct S { int m; } s;

template<int* p> struct P {};
P<&arr[1]> pa;      // OK（C++20 起）: 数组元素的地址
P<&s.m>    pm;      // OK（C++20 起）: 成员子对象的地址
P<&arr[3]> pe;      // OK: 尾后指针也是合法的常量表达式值
P<nullptr> pn;      // OK
int main() {}
```

C++17 及之前，指针实参必须指向**完整对象**（不能是子对象），也不能是尾后指针。C++20 的 [[P1907R1]] 移除了这些限制。

### 标准例子（¶7–¶8）

¶8 的例子展示了允许的转换：数组到指针、限定转换、函数重载决议：

```cpp run title="arg-conversions.cpp" ok
template<const int* pci> struct X {};
int ai[10];
X<ai> xi;                       // 数组到指针 + 限定转换

struct Y {};
template<const Y& b> struct Z {};
Y y;
Z<y> z;                         // 无转换，但注意多了 const

template<int (&pa)[5]> struct W {};
int b[5];
W<b> w;                         // 无转换

void f(char);
void f(int);
template<void (*pf)(int)> struct A {};
A<&f> a;                        // 重载决议选中 f(int)

template<int i> struct C {};
C<{ 42 }> c1;                   // OK: braced-init-list（¶5）

void f(char) {}
void f(int) {}
int main() {}
```

### 字符串字面量（¶9）

¶9 注 2：*string-literal* **不能**作为**非类类型**常量模板形参的实参：

```cpp title="string-literal-arg.cpp" error
template<class T, T p> class X {};

X<const char*, "Studebaker"> x;     // error: 字符串字面量对象作模板实参
X<const char*, "Knope" + 1> x2;     // error: 字符串字面量对象的子对象

const char p[] = "Vivisectionist";
X<const char*, p> y;                // OK: p 是一个有链接的具名数组

struct A {
    constexpr A(const char*) {}
};
X<A, "Pyrophoricity"> z;            // OK: 字符串字面量只是 A 的构造函数实参
```

最后一行是 C++20 "字符串作模板实参"的标准做法：形参是类类型，字符串字面量只用来**初始化**模板形参对象，而模板形参对象存的是字符的**值**（拷贝），不是指向字面量的指针。

```cpp run title="fixed-string.cpp" ok
#include <cstddef>
#include <cstdio>

template<std::size_t N>
struct fixed_string {
    char data[N]{};
    constexpr fixed_string(const char (&s)[N]) {
        for (std::size_t i = 0; i < N; ++i) data[i] = s[i];
    }
};

template<fixed_string S>          // 推导类类型的占位符（[temp.param]/11.3）
struct Named {
    static void print() { std::puts(S.data); }
};

int main() {
    Named<"hello">::print();      // OK: S 是 fixed_string<6>，值为 "hello\0"
    static_assert(!__is_same(Named<"a">, Named<"b">));
    static_assert(__is_same(Named<"a">, Named<"a">));   // 按值比较
}
```

注意 `fixed_string` 中**不能**存 `const char*`，否则又回到了"指向字符串字面量"（¶6.2）。

### 临时对象（¶10）

¶10 注 3：形参是引用类型时，临时对象不能作实参：

```cpp title="temporary-arg.cpp" error
template<const int& CRI> struct B {};
B<1> b1;                        // error: 需要一个临时对象
int c = 1;
B<c> b2;                        // OK

struct X { int n; };
struct Y { const int& r; };
template<Y y> struct C {};
C<Y{X{1}.n}> c;                 // error: 引用成员绑定到临时对象的子对象
```

## 模板模板实参（[temp.arg.template]）

### 什么能作模板模板实参（¶1）

¶1 模板模板形参的实参必须是**模板的名字**：

| 形参种类 | 实参必须指称 |
|---|---|
| 类型模板模板形参（*type-tt-parameter*） | 类模板、别名模板，或类型模板模板形参 |
| 变量模板模板形参 {{c++26}} | 变量模板，或变量模板模板形参 |
| 概念模板形参 {{c++26}} | 概念，或概念模板形参 |

匹配时**只考虑主模板**；部分特化即使形参列表与模板模板形参相符也不被考虑。

### 部分特化在使用时才参与（¶2）

¶2 与主模板关联的部分特化在通过模板模板形参**实例化特化**时被考虑。若某个部分特化在实例化点不可达、而它若可达本应被选中，程序 {{ifndr}}。

```cpp run title="tt-partial.cpp" ok
#include <type_traits>
template<class T> class A { public: int x; };          // 主模板
template<class T> class A<T*> { public: long x; };     // 部分特化

template<template<class U> class V> class C {
public:
    V<int>  y;     // 使用主模板：y.x 是 int
    V<int*> z;     // 使用部分特化：z.x 是 long
};

C<A> c;
static_assert(std::is_same_v<decltype(c.y.x), int>);
static_assert(std::is_same_v<decltype(c.z.x), long>);
int main() {}
```

### 兼容（¶3）

¶3 模板模板形参 `P` 与实参 `A` **兼容**（compatible），当：`A` 是类模板或别名模板且 `P` 是类型模板模板形参；`A` 是变量模板且 `P` 是变量模板模板形参；或 `A` 是概念且 `P` 是概念模板形参。也就是"种类对得上"。

### 匹配：P 至少和 A 一样特殊（¶4–¶5）

¶4 是本子节的核心。模板模板实参 `A` **匹配**模板模板形参 `P`，当 `A` 与 `P` 兼容，并且 **`P` 至少和 `A` 一样特殊**（若 `P` 无约束，则忽略 `A` 的约束）。

直觉：`P` 描述了模板内部**会如何使用** `A`。`template<template<class> class P>` 承诺"我只会写 `P<X>`，一个类型实参"。只要 `A` 能接受 `P` 所能接受的一切用法，`A` 就是合格的实参。"`P` 至少和 `A` 一样特殊"正是这个意思：`P` 能接受的实参列表，`A` 都能接受。

¶5 给出精确定义：把 `P` 和 `A` 改写成两个函数模板，然后用函数模板的偏序规则（[[temp.func.order]]）比较。设虚构类模板 `X`，其 *template-head* 与 `A` 相同（包括默认实参和 *requires-clause*）：

- ¶5.1 两个函数模板分别具有与 `P`、`A` 相同的模板形参和 *requires-clause*；
- ¶5.2 每个函数模板有唯一一个函数形参，其类型是 `X` 的特化，模板实参对应该函数模板自己的模板形参（形参包对应包展开 `PP...`）。若改写产生了无效类型，则 `P` 不比 `A` 特殊。

例如 `P = template<class> class`，`A = std::vector`（`template<class T, class Alloc = allocator<T>>`）：

```cpp
template<class T, class Alloc = std::allocator<T>> class X;   // X 的 template-head 取自 A

template<class T>                      void fP(X<T>);           // 对应 P：X<T> 使用 Alloc 的默认实参，有效
template<class T, class Alloc>         void fA(X<T, Alloc>);    // 对应 A
```

`fP` 至少和 `fA` 一样特殊（`X<T>` 即 `X<T, allocator<T>>`，可以从 `fP` 的形参推导出 `fA` 的 `T` 和 `Alloc`），所以 `std::vector` 匹配 `template<class> class`。

```cpp run title="p0522.cpp" ok
#include <vector>
#include <map>

template<template<class> class C>
struct Wrap { C<int> c; };

Wrap<std::vector> w;    // OK（C++17 起）: vector 的第二个形参有默认实参

template<class T> class A {};
template<class T, class U = T> class B {};
template<class... Types> class C {};
template<auto n> class D {};
template<template<class> class P> class X {};
template<template<class...> class Q> class Y {};
template<template<int> class R> class Z {};

X<A> xa;   // OK
X<B> xb;   // OK: B 的 U 有默认实参（C++17 前非良构）
X<C> xc;   // OK: 包可以接受一个实参
Y<A> ya;   // OK: 见 ¶4 第二句（P 含包时的逐形参匹配）
Y<B> yb;   // OK
Y<C> yc;   // OK
Z<D> zd;   // OK: auto 形参可以接受 int 值（C++17 前非良构）
int main() {}
```

¶4 第二句处理 `P` 含形参包的情形：此时若 `A` 的每个模板形参都**匹配** `P` 的 *template-head* 中的对应形参，`A` 也匹配 `P`。两个模板形参**匹配**是指：种类相同；常量形参的类型等价（[[temp.over.link]]）；模板模板形参的各对应形参递归匹配。`P` 中的形参包可以匹配 `A` 中零个或多个"类型与形式相同"的形参（不论它们是否是包）。这就是 `Y<A>`、`Y<B>` 合法的原因——尽管 `Y` 内部若写 `Q<int, int, int>`，实例化时仍会出错：

```cpp title="pack-tt-use.cpp" error
template<class T, class U = T> class B {};
template<template<class...> class Q> struct Y1 { Q<int, int, int> q; };
Y1<B> y;    // 匹配成功，但实例化 Y1<B> 时 B<int, int, int> 实参过多：error
```

### 带约束的匹配

¶4 的例 4 展示了约束如何参与："`P` 至少和 `A` 一样特殊"包括约束——`P` 的约束必须**包含**（subsume，[[temp.constr.order]]）`A` 的约束：

```cpp title="tt-constraints.cpp" error
template<typename T> concept C = requires (T t) { t.f(); };
template<typename T> concept D = C<T> && requires (T t) { t.g(); };

template<template<C> class P> struct S {};

template<C> struct X {};
template<D> struct Y {};
template<typename T> struct Z {};

S<X> s1;   // OK: X 与 P 的约束等价
S<Y> s2;   // error: P 不比 Y 特殊——P 只保证 C，Y 还要求 D
S<Z> s3;   // OK: Z 没有约束，P 至少和它一样特殊
```

直觉：`S` 内部会用满足 `C` 的类型实例化 `P<T>`。`Y` 要求 `D`，比 `C` 更严，于是 `S` 可能把一个只满足 `C` 的类型塞给 `Y`——不安全，拒绝。`Z` 来者不拒，安全。

注意"若 `P` 无约束，则忽略 `A` 的约束"：`template<template<class> class P>` 可以接受 `template<std::integral T> class A`。这是为了兼容 C++20 之前的代码——很多已有的模板模板形参没有约束，若一律拒绝受约束的实参，标准库组件一旦加了约束就会破坏大量用户代码。代价是安全性：在 `P` 中写 `P<double>` 会在实例化时才因约束不满足而报错。

### 部分特化中的模板模板形参

标准例 3 展示了一个常见陷阱：用 `template<class, class...> class TT` 去"匹配任何类模板"：

```cpp title="eval.cpp" error
template<class T> struct eval;
template<template<class, class...> class TT, class T1, class... Rest>
struct eval<TT<T1, Rest...>> {};

template<class T1> struct A;
template<class T1, class T2> struct B;
template<int N> struct C;
template<class T1, int N> struct D;
template<class T1, class T2, int N = 17> struct E;

eval<A<int>> eA;           // OK: 匹配部分特化
eval<B<int, float>> eB;    // OK
eval<C<17>> eC;            // error: C 的形参是常量形参，不匹配 TT
eval<D<int, 17>> eD;       // error: D 的第二个形参是常量形参
eval<E<int, float>> eE;    // error: E 有一个常量形参（即使有默认实参）
```

这里的"error"是因为部分特化不匹配，于是使用了未定义的主模板 `eval`。不存在"匹配任意类模板"的模板模板形参——常量形参和类型形参永远不能互相匹配。

## 实现视角

!!! impl "实现视角"
    - **P0522 的推广**：[[P0522R0]] 在 C++17 中被采纳，但它引入了新的偏序歧义（同一个模板实参可以匹配多个部分特化中的模板模板形参）。Clang 因此长期默认不启用它（需要 `-frelaxed-template-template-args`），直到相关歧义的解决方案落地后才默认开启；GCC 则较早默认启用。当前草案 ¶4 的第二句（含包时的逐形参匹配）就是为保持旧代码可编译而保留的规则。
    - **模板形参对象的唯一性**：类类型常量模板实参的唯一性由 COMDAT 常量（Itanium 修饰名 `_ZTA...`）保证，见 [[temp.param]]。
    - **诊断**：Clang 对 ¶6 的各项违规给出具体原因（"pointer to temporary object is not allowed in a template argument"、"reference to type_info object is not allowed in a template argument" 等）。

## 历史与演进

!!! history "历史与演进"
    - **C++98/03**：常量实参必须是整型常量表达式，或**具有外部链接**的对象/函数的地址（形如 `&obj`），不允许局部类型和无名类型作类型实参。
    - **C++11**：允许具有内部链接的对象；局部类型、无名类型可以作类型实参；允许 `nullptr`；指针实参可以是值为空指针的常量表达式。
    - **C++17**：[[N4268]] 允许所有常量模板实参都是一般的转换常量表达式（此前指针实参必须是 `&x` 的字面形式）；[[P0522R0]] 放宽模板模板实参匹配；`template<auto>`。
    - **C++20**：类类型和浮点类型的常量模板实参（[[P0732R2]]、[[P1907R1]]）；允许指向子对象的指针/引用；约束参与模板模板实参的匹配。
    - **C++26**：概念与变量模板作为模板模板实参（[[P2841]]）；*template-argument-name* 的解释规则（[temp.arg.general]/3）；"非类型"更名为"常量"。

## 陷阱

!!! pitfall "常见误解"
    - **"`X<"abc">` 在 C++20 可以用"**——只有当 `X` 的形参是**类类型**（如 `fixed_string`）时可以；`const char*` 形参永远不接受字符串字面量（¶6.2、¶9）。
    - **"`template<char c>` 接受 `X<300>`，截断为 44"**——不，转换常量表达式禁止窄化，非良构（¶2）。
    - **"模板内部访问模板实参的私有成员没问题，因为我写实参时有访问权"**——在**实参书写处**的访问只覆盖实参本身的名字；模板对实参类型的成员没有特殊访问权（¶5）。
    - **"`template<template<class> class C>` 不能接受 `std::vector`"**——C++17 起可以（P0522）；旧编译器的默认行为不一定如此。
    - **"无约束的模板模板形参拒绝受约束的实参"**——不拒绝，约束在实例化时才起作用（¶4）。

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

- (a) 合法：`a` 是具名数组（不是字符串字面量对象，只是用字面量初始化的），数组到指针转换。
- (b) 非法：`q` 的值指向字符串字面量对象（¶6.2）。
- (c) 合法（C++20 起）：指向具名数组的子对象（尾后指针，`a` 有 2 个元素：`'x'` 和 `'\0'`，`&a[1]` 指向 `'\0'`）。
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

- `S1<I>` 合法：¶4，`P` 无约束时忽略 `A` 的约束。
- `S2<J>` 非法：`P` 的约束是 `std::integral<T>`，`J` 的约束是 `std::signed_integral<T>`（标准库定义为 `integral<T> && is_signed_v<T>`），前者**不包含**后者，`P` 不比 `J` 特殊。
- `S3<I>` 合法：`std::signed_integral<T>` 规范化后包含 `std::integral<T>` 的原子约束，所以 `P` 至少和 `I` 一样特殊——`S3` 内部只会用有符号整数实例化 `P`，`I` 都能接受。

判断包含关系必须看概念的**定义**（规范化结果），而不是名字。
</details>

## 小结

!!! summary "小结"
    | 实参种类 | 核心规则 |
    |---|---|
    | 通用 | 类型/表达式歧义取类型；访问检查在实参书写处；空 `<>` 不可省 |
    | 类型实参 | 任何 *type-id*，包括局部、无名、不完整类型 |
    | 常量实参（非类类型） | 转换常量表达式，禁止窄化 |
    | 常量实参（类类型） | 虚构 `constexpr T v = A;`，复制初始化唯一的模板形参对象；须模板实参等价 |
    | 指针/引用 | 不得指向临时对象、字符串字面量、`typeid` 结果、`__func__` 及其子对象；子对象地址 C++20 起可以 |
    | 模板模板实参 | 种类兼容；`P` 至少和 `A` 一样特殊（改写为函数模板偏序）；`P` 无约束时忽略 `A` 的约束 |
