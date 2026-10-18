---
title: 限定名字查找
summary: :: 之前的名字只考虑命名空间与类型；:: 之后（以及 . / -> 之后）的名字在"查找上下文"中搜索；类中注入类名被解释为构造函数；命名空间中先搜内联命名空间集，找不到才沿 using 指令传递。
status: done
covers: basic.lookup.qual.general, class.qual, namespace.qual
papers: P1787R6
related: basic.lookup, class.member.lookup, basic.lookup.unqual, expr.prim.id.qual, expr.ref, namespace.udir, namespace.def, class.pre, namespace.udecl, temp.res
tags: 名字查找, 命名空间, 嵌套名说明符
updated: 2026-10-17
---

限定名字查找回答的是：**`X::m` 中的 `m`、`obj.m` 中的 `m` 去哪里找？** 直觉很简单——"去 X 里找"、"去 obj 的类里找"。但精确规则要处理一连串细节：

- `X` 本身怎么找？它若同时是变量名和类名呢？（¶1）
- 哪些名字算"限定的"？`p->Base::f()` 里的 `Base` 在哪个语境查？（¶2、¶3）
- `~T` 析构函数名怎么查？（¶4）
- `A::A` 是类型还是构造函数？（[class.qual]）
- `N::x` 在命名空间 N 里没找到，要不要看 N 中 using 指令提名的命名空间？要看内联命名空间吗？（[namespace.qual]）

本页覆盖 6.5.5 全部三个子条款：[basic.lookup.qual.general]、[class.qual]、[namespace.qual]。相关文法见 [[expr.prim.id.qual]]（*qualified-id*、*nested-name-specifier*）与 [[expr.ref]]（成员访问）。

## :: 之前的名字（[basic.lookup.qual.general] ¶1）

¶1 后跟 `::` 的*标识符*，其查找**只考虑命名空间、类型、以及特化是类型的模板**。后跟 `::` 的名字、*template-id*、*splice-scope-specifier* {{c++26}} 或 *computed-type-specifier*，必须指代命名空间、类、枚举或依赖类型（或者是依赖的 *splice-scope-specifier*），并且 `::` 永远不被解释为一个完整的 *nested-name-specifier*。

为什么只考虑这几类？因为 `X::` 之后要在 X 的作用域里找东西，只有拥有作用域的实体才有意义；变量、函数即使与 X 同名也应当被忽略，否则 C 风格"类与变量同名"的代码里将无法访问类的静态成员。

```cpp run error
class A {
public:
    static int n;
};
int main() {
    int A;
    A::n = 42;          // OK：A:: 的查找只考虑类型，局部变量 A 被忽略
    A b;                // error: 普通查找找到局部变量 A，A 不是类型
}
template<int> struct B : A {};
namespace N {
    template<int> void B();
    int f() {
        return B<0>::n; // error: 找到的是 N::B（函数模板），N::B<0> 不是类型
    }
}
```

注意第二个错误：¶1 第一句的"只考虑类型"限制针对的是**直接后跟 `::` 的标识符**；这里 `B` 后面跟的是 `<`，所以对 `B` 做的是普通无限定查找——在命名空间 N 中找到函数模板 `N::B` 就停下，全局的类模板 `::B` 被隐藏。随后按第二句，后跟 `::` 的 *template-id* `B<0>` 必须指代类等，而 `N::B<0>` 是函数模板特化，非良构。

能出现在 `::` 之前的东西，随标准演进越来越多：

| 形式 | 例子 | 引入 |
|---|---|---|
| 命名空间名、类名、枚举名、typedef 名 | `std::`、`Outer::`、`Color::` | C++98（枚举名 C++11） |
| *simple-template-id* | `std::vector<int>::` | C++98 |
| *decltype-specifier* | `decltype(s)::In::` | C++11 |
| *pack-index-specifier* | `Ts...[0]::type` | {{c++26}} |
| *splice-scope-specifier* | `[:r:]::` | {{c++26}} |

```cpp run ok
template<class... Ts>
struct First { using type = typename Ts...[0]::type; };   // C++26：包索引说明符后跟 ::
struct I { using type = int; };
static_assert(__is_same(First<I, double>::type, int));

struct S { struct In { static const int v = 1; }; };
S s;
int k = decltype(s)::In::v;                                // C++11：decltype 后跟 ::
```

## 限定名、成员限定名与查找上下文（¶2）

¶2 定义了几个 C++23 引入的术语，它们取代了旧标准里"在类成员访问表达式中的名字……"这类分散描述。

[[g:member-qualified-name|成员限定名]]（member-qualified name）：类成员访问表达式 `obj.X` / `p->X` 的 *id-expression* 中，下列之一的（唯一）组件名：

- ¶2.1 一个 *unqualified-id*（`obj.m` 中的 `m`）；
- ¶2.2 形如 `type-name ::` 或 `namespace-name ::` 的 *nested-name-specifier*（`p->Base::f()` 中的 `Base`）。

**限定名**（qualified name）：

- ¶2.3 成员限定名；或
- ¶2.4 带有 *nested-name-specifier* 的下列结构的**终端名**：*qualified-id*、*using-declarator*、*typename-specifier*、*qualified-namespace-specifier*、*nested-name-specifier*、*reflection-name*、*elaborated-type-specifier*、*class-or-decltype*。

[[g:lookup-context|查找上下文]]（lookup context）：

- 成员限定名的查找上下文是**其关联对象表达式的类型**（若对象表达式类型依赖，则视为依赖）；
- 其他限定名的查找上下文是**前面的 *nested-name-specifier* 所指名的类型、模板或命名空间**。

注 1：解析成员访问时，`.`/`->` 后面的名字是限定名，尽管此时还不知道它是哪种（成员？基类名？）。

标准例 2：在 `N::C::m.Base::f()` 中，`Base` 是成员限定名（查找上下文是 `N::C::m` 的类型）；`C`、`m`、`f` 是其他限定名（`C` 的上下文是 N，`m` 的上下文是 `N::C`，`f` 的上下文是 `Base` 所指的类）。

## 限定名字查找做什么（¶3）

¶3 在类、命名空间或枚举中的**限定名字查找**，就是对其关联作用域的一次**搜索**（类作用域的搜索会展开到基类，[[class.member.lookup]]），后面两个子条款另有补充。

除另有规定外，限定名在其查找上下文中、从其出现处进行限定名字查找——**除非**查找上下文：

- 是依赖的，且不是当前实例化（[[temp.dep.type]]）——此时推迟到实例化；或
- 不是类或类模板——例如 `p->m` 中 `p` 指向 `int`，或者查找上下文是命名空间时由 [namespace.qual] 处理。

**回退规则**：若一个**成员限定名**是 *nested-name-specifier* 的终端名、且不依赖，而限定查找什么也没找到，那么它改做**无限定查找**。

这条回退规则说的是 `p->Base::f()` 中的 `Base`：先在 `*p` 的类里找 `Base`（通常能找到——基类的注入类名），找不到再从表达式所在处做无限定查找。

注 2：在查找模板特化时（实例化后），没有名字是依赖的。

### 标准例 3 详解

```cpp
int f();
struct A {
    int B, C;
    template<int> using D = void;
    using T = void;
    void f();
};
using B = A;
template<int> using C = A;
template<int> using D = A;
template<int> using X = A;

template<class T>
void g(T *p) {                  // 以下按 g<A> 的实例化来解释
    p->X<0>::f();               // error: 在 A 中找不到 X → 被解析为 ((p->X) < 0) > ::f()
    p->template X<0>::f();      // OK：在定义上下文中找到 ::X
    p->B::f();                  // OK：A::B 是非类型，被忽略 → 回退到无限定查找找到 ::B（即 A）
    p->template C<0>::f();      // error: A::C 不是模板
    p->template D<0>::f();      // error: A::D<0> 不是类类型
    p->T::f();                  // error: A::T 不是类类型
}
template void g(A*);
```

逐行：

1. `p->X<0>::f()`：`X` 是成员限定名，查找上下文 `T` 依赖，推迟。实例化时在 A 中找 `X`，什么也没有；由于它后面没有 `template` 关键字，`<` 是否开始模板实参列表取决于查找结果（[[temp.names#7]]）。找不到 → `<` 是小于号，整个表达式变成 `((p->X) < 0) > ::f()`，而 `p->X` 不存在，非良构。
2. 加了 `template` 关键字，`X<0>` 被确定为 *simple-template-id*；`X` 在 A 中找不到，¶3 回退到无限定查找（在定义上下文）找到 `::X`，于是 `::X<0>` 即 A，调用 `A::f`。
3. `B` 后跟 `::`，按 ¶1 只考虑类型，A 中的数据成员 `B` 被忽略 → 找不到 → 回退找到 `::B`（别名 A）。
4. `C` 在 A 中找到数据成员 `C`。`template C<0>` 要求 `C` 是模板，但 A::C 不是——非良构，不会回退（找到了东西）。
5. `D` 在 A 中找到成员别名模板 `A::D`，`A::D<0>` 是 `void`，不是类。
6. `T` 在 A 中找到 `A::T`（void），不是类。注意这里的 `T` 被当作成员限定名在 A 中查找，而**不是**函数模板 g 的模板参数 `T`。

!!! impl "编译器现状"
    在本机测试，Clang 23 对例 3 第 1、4、5 行**不报错**，只拒绝第 6 行。这符合 C++20 之前的旧规则：成员访问中 `::` 前的名字"在对象类型的类中与在整个后缀表达式的语境中**都**查找"，择一使用。C++23 改为"先在类中找，找不到才回退"，并且"找到了就不回退"。依据当前草案这三行都非良构。

!!! history "旧规则：在两个语境中查找"
    C++98–C++20 的 [basic.lookup.classref] 规定：`p->X::m` 中的 `X` 既在 `*p` 的类中查找，也在整个后缀表达式的语境中查找；两处都找到时必须指代同一实体，否则非良构。这条"双重查找"规则复杂、易出矛盾，且与模板中的依赖查找交织。P1787R6 把它替换为本节 ¶3 的"类中优先、找不到再回退"。

## 析构函数名（¶4）

¶4 当限定名 Q 跟在 `~` 后面（析构函数名）时：

- ¶4.1 若 Q 是成员限定名（`p->~Q()`），它**既**做无限定查找**也**做限定查找；
- ¶4.2 否则，其 *nested-name-specifier* N 必须指名一个类型。若 N 自身还有一个 *nested-name-specifier* S（`S::N::~Q`），Q 的查找上下文视为 S 所指名的实体；
- ¶4.3 否则（N 只有一层），若 N 的终端名是成员限定名 M（`p->N::~Q`），Q 的查找按"`~Q` 出现在 M 的位置"进行（即按 ¶4.1）；
- ¶4.4 否则 Q 做无限定查找；
- ¶4.5 每次查找只考虑类型（Q 后不跟 `<` 时）与特化是类型的模板；查不到或二义的那次查找被丢弃；
- ¶4.6 包含 Q 的 *type-name* 必须在至少一次成功查找所建立的解释下，指代其原本的查找上下文（忽略 cv 限定）。

规则这么复杂的原因：析构函数名 `~X` 中的 `X` 有很多合法写法——类名、typedef、模板参数，甚至对标量类型的"伪析构"`p->~I()`（`I` 是 `int` 的别名）。¶4 的设计是"多处尝试，只要有一种解释能对上对象的类型就行"。

```cpp run ok
struct C { typedef int I; };
typedef int I1, I2;
extern int* p;
extern int* q;
void f() {
    p->C::I::~I();      // ¶4.2：I 的查找上下文是 C（S），在 C 中找到 C::I = int ✓
    q->I1::~I2();       // ¶4.3/¶4.1：I1 是成员限定名，I2 在 int 中查不到（不是类），
                        //            无限定查找找到 ::I2 = int ✓
}
struct A { ~A(); };
typedef A AB;
int main() {
    AB* p;
    p->AB::~AB();       // 显式调用 A 的析构函数：AB 经无限定查找找到 typedef，指代 A ✓
}
```

`q->I1::~I2()`：对标量类型调用"伪析构函数"（pseudo-destructor），C++20 起它会结束对象的生命期（[[expr.prim.id.dtor]]）。

## [class.qual]：类成员与"A::A 是构造函数"

[class.qual] ¶1 在查找上下文为类 C、且**不忽略函数名**的限定名查找中：

- ¶1.1 若搜索找到 C 的**注入类名**（[[class.pre]]）；或
- ¶1.2 若 N 是依赖的、且是指名构造函数的 *using-declarator* 的终端名；

则 N 被视为指名 **C 的构造函数**。这样的构造函数名只能用在构造函数（或友元构造函数）声明的 *declarator-id* 中，或在 *using-declaration* 中。

脚注 15 列出"忽略函数名"的查找：*nested-name-specifier* 中的名字、*elaborated-type-specifier*、*base-specifier*。在这些地方，注入类名照常指类型。

```cpp run error
struct A { A(); };
struct B : public A { B(); };

A::A() { }          // OK：A::A 指名构造函数，用在 declarator-id 中
B::B() { }

B::A ba;            // OK：查找上下文是 B，找到的是 A 的注入类名（不是 B 的）→ 类型 A
struct A::A a2;     // OK：详述类型说明符忽略函数名 → 注入类名指类型 A
A::A a;             // error: A::A 指名构造函数，不是类型
```

为什么 `B::A` 不算构造函数？¶1.1 要求找到的是**查找上下文 C 自己的**注入类名；在 B 中找到的是基类 A 的注入类名，所以它只是普通的类型名。

为什么要有这条规则？早期标准里 `A::A` 有时指类型、有时指构造函数，导致 `A::A::A::A` 之类的写法含义含混，也让"在类外定义构造函数"的文法变得特殊。现在规则统一：**不忽略函数名的语境中，`C::C` 就是构造函数**；需要类型时用 `C` 本身或 `struct C::C`。

```cpp run ok
struct A { A(); };
A::A::A::A() { }    // 前三个 A 在 nested-name-specifier 中（忽略函数名）→ 类 A；
                    // 最后的 A::A 在 declarator-id 中 → 构造函数
```

¶1.2 处理模板中的继承构造函数 `using Base<T>::Base;`：终端名 `Base` 依赖，无法在定义时查找确认它是注入类名，标准直接规定它指名构造函数。

```cpp run ok
struct Base { Base(int); };
struct Der : Base { using Base::Base; };     // 指名 Base 的构造函数：继承构造函数
Der d(1);

template<class T> struct TB { TB(T); };
template<class T> struct TD : TB<T> { using TB<T>::TB; };   // ¶1.2：依赖的 using 声明符
TD<int> td(1);
```

## [namespace.qual]：命名空间成员

[namespace.qual] ¶1 在命名空间 N 中的限定名字查找：

1. 搜索 N，**另外**搜索 N 的**内联命名空间集**的每个元素（[[namespace.def]]）；
2. **若什么都没找到**，结果为：对"先于查找点、且栖身于 N 或 N 的内联命名空间集元素中的 using 指令"所提名的每个命名空间，进行限定名字查找（递归）的结果。

注 1：若某 using 指令指向已经考虑过的命名空间，它不影响结果——这保证了递归终止，也避免了循环 using 指令造成无限查找。

与无限定查找对比：

| | 无限定查找（[[basic.lookup.unqual]]） | 限定查找 `N::x` |
|---|---|---|
| using 指令提名的命名空间 | 在"公共外围命名空间"那一层与该层声明**合并**搜索 | 只有在 N（及其内联集）中**什么都没找到**时才进入 |
| 内联命名空间 | 由其外层命名空间中的隐式 using 指令处理 | 与 N 一起**同时**搜索 |

### 标准例 1

```cpp run error
int x;
namespace Y { void f(float); void h(int); }
namespace Z { void h(double); }
namespace A { using namespace Y; void f(int); void g(int); int i; }
namespace B { using namespace Z; void f(char); int i; }
namespace AB { using namespace A; using namespace B; void g(); }

void h() {
    AB::g();      // AB 中直接声明了 g → S = {AB::g}
    AB::f(1);     // AB 中没有 f → 递归到 A、B；A 中找到 A::f(int)，故不进入 Y
                  // S = {A::f(int), B::f(char)} → 选 A::f(int)
    AB::f('c');   // 同上，选 B::f(char)
    AB::h(16.8);  // AB、A、B 都没有 h → 递归到 Y、Z：S = {Y::h(int), Z::h(double)} → Z::h
    AB::x++;      // error: AB、A、B、Y、Z 都没有 x；全局的 ::x 不在其中——限定查找不往外找
    AB::i++;      // error: S = {A::i, B::i}，不是同一实体 → 二义
}
```

`AB::f(1)` 那一行最能说明"找不到才递归"的含义：A 中有 `f`，所以 A 这一支不再深入到 Y——`Y::f(float)` **不是**候选，即使它对某些实参是更好的匹配。

### 同一声明找到两次不是二义（¶2）

¶2 注 2：同一个声明被找到多次不构成二义，因为它仍是唯一的声明。

```cpp run ok
namespace A { int a; }
namespace B { using namespace A; }
namespace C { using namespace A; }
namespace BC { using namespace B; using namespace C; }
void f() { BC::a++; }    // OK：S = {A::a, A::a}，同一声明

namespace D { using A::a; }
namespace BD { using namespace B; using namespace D; }
void g() { BD::a++; }    // OK：D 中的 using 声明被替换为 A::a，S 仍是 {A::a}
```

### 每个命名空间至多搜索一次（¶3）

¶3 例 3：因为每个被引用的命名空间只搜索一次，循环的 using 指令是良定义的。

```cpp run ok
namespace B { int b; }
namespace A { using namespace B; int a; }
namespace B { using namespace A; }      // A ↔ B 互相提名

void f() {
    A::a++;     // OK：a 直接在 A 中
    B::a++;     // OK：B 中没有 a → 搜索 A（B 已搜过不再搜）→ A::a
    A::b++;     // OK：A 中没有 b → 搜索 B → B::b
    B::b++;     // OK：b 直接在 B 中
}
```

### 类与枚举不会被其他搜索中的声明丢弃（¶4）

¶4 注 3：[[basic.lookup#4]] 的"类被其他声明隐藏"只在**同一次搜索**内起作用。经 using 指令在**不同**命名空间中找到的类与非类声明，不会让类被丢弃——于是二义。

```cpp run error
namespace A {
    struct x { };
    int x;          // 同一作用域：类 x 被变量 x 隐藏
    int y;
}
namespace B {
    struct y { };
}
namespace C {
    using namespace A;
    using namespace B;
    int i = C::x;   // OK：在 A 的同一次搜索中找到 {struct x, int x}，类被丢弃 → A::x
    int j = C::y;   // error: A::y（变量）与 B::y（类）来自不同搜索，类不被丢弃 → 二义
}
```

### 内联命名空间

内联命名空间的成员在限定查找中"如同"外层命名空间的成员，这是库版本化的基础：

```cpp run ok
namespace lib {
    inline namespace v2 {
        struct W {};
        void f(W);
    }
    namespace v1 { struct W {}; }
}
lib::W w;                // 内联命名空间集参与限定查找：lib::v2::W
void t() {
    lib::f(w);           // OK
    lib::v2::f(w);       // OK：显式指名版本
    f(w);                // OK：ADL，关联命名空间 lib 及其内联命名空间集
}
```

与 using 指令不同，内联命名空间在第 1 步就和 N **一起**搜索，而不是"找不到才去"。因此若 `lib` 自己也声明了 `W`，`lib::W` 就二义了（两个都在第 1 步被找到）——这也是"内联命名空间与外层同名声明"需要小心的地方。

!!! impl "实现视角"
    - 内联命名空间对 ABI 至关重要：其名字进入修饰名。libc++ 的 `std::__1::vector<int>` 在 Itanium ABI 下修饰为含 `NSt3__16vectorIiNS_9allocatorIiEEEE` 的形式，而 libstdc++ 的 `std::vector<int>` 修饰中没有这层——两者因此无法意外链接到一起。源码层面，限定查找与 ADL 让 `std::vector` 透明地指到 `std::__1::vector`。
    - Clang 对成员访问中 `::` 前名字的查找（例 3）仍沿用旧的"双重查找"实现，见上文。

!!! history "历史与演进"
    - **C++98**：限定查找、[basic.lookup.classref] 的双重查找、命名空间限定查找经 using 指令传递的规则。
    - **C++11**：内联命名空间；*decltype-specifier* 可用于 *nested-name-specifier*；枚举名可作限定（`Color::red`）。
    - **C++23**：P1787R6 引入成员限定名、查找上下文；用"类中优先 + 回退"取代双重查找；把"`A::A` 指名构造函数"并入 [class.qual] 的统一表述。
    - **C++26**：包索引说明符（`Ts...[0]::`）与 *splice-scope-specifier*（`[:r:]::`）可出现在 `::` 之前。

## 陷阱

!!! pitfall "以为 N::x 会往外找"
    限定查找只看 N、N 的内联命名空间集与 N 中 using 指令（递归）提名的命名空间，**从不**看 N 的外层。`AB::x` 不会找到全局的 `::x`。

!!! pitfall "以为 using 指令提名的命名空间与 N 平等"
    只要 N 自己（或内联集）有一个同名声明，using 指令提名的命名空间就完全不被考虑。给 N 新增一个声明，可能让原本经 using 指令找到的更好重载消失。

!!! pitfall "B::A 与 A::A"
    派生类限定的基类名 `B::A` 是类型，类自己限定的 `A::A` 是构造函数。模板代码里写 `typename Derived::Base` 是常见且合法的。

## 思考题

!!! question "思考题 1"
    ```cpp
    namespace N { inline namespace I { int v = 1; } }
    namespace M { int v = 2; }
    namespace N { using namespace M; }
    int r = N::v;
    ```
    `r` 是多少？如果把 `inline` 去掉呢？

<details markdown="1">
<summary>答案</summary>

有 `inline`：第 1 步搜索 N 与其内联命名空间集 {I}，找到 `N::I::v` → `r == 1`，using 指令不被考虑。

去掉 `inline`：第 1 步在 N 中找不到 `v`（I 不再是内联集成员），进入第 2 步：N 中的 using 指令提名 M，找到 `M::v` → `r == 2`。I 中的 `v` 只能通过 `N::I::v` 访问。
</details>

!!! question "思考题 2"
    在 `template<class T> void g(T* p) { p->Base::f(); }` 中，若实例化时 `T` 的类中没有名为 `Base` 的类型，但 `g` 定义处能找到一个全局类 `Base`，按 C++23 规则会发生什么？若 `T` 的类中有一个名为 `Base` 的**数据成员**呢？

<details markdown="1">
<summary>答案</summary>

`Base` 是成员限定名、是 *nested-name-specifier* 的终端名。实例化时在 T 的类中查找，只考虑类型（¶1），找不到 → ¶3 回退到无限定查找，找到全局 `Base`；之后 `Base::f` 要求 `Base` 是 `*p` 的（可访问的、无二义的）基类，否则在成员访问检查时非良构。

若 T 的类中 `Base` 是数据成员：¶1 只考虑类型，数据成员被忽略，仍然"什么都没找到"，同样回退——与例 3 中 `p->B::f()` 完全相同。
</details>

## 小结

| 规则 | 要点 |
|---|---|
| `X::` 中的 X | 只考虑命名空间、类型、类模板；必须指命名空间/类/枚举/依赖类型 |
| 成员限定名 | `.`/`->` 后的名字及其 `T::` 部分；上下文是对象表达式的类型 |
| 查找上下文 | 前面 *nested-name-specifier* 指名的实体；依赖则推迟 |
| 回退 | 成员限定的 nns 终端名在类中找不到时，做无限定查找 |
| 析构名 | 多处查找，只要一种解释对得上对象类型 |
| `C::C` | 不忽略函数名的语境下指构造函数；`B::A`、`struct A::A` 是类型 |
| 命名空间限定 | N + 内联集；找不到才沿 using 指令递归；每个命名空间至多一次；不往外找 |
| 二义 | 同一声明多次找到 OK；不同搜索中的类不被变量隐藏 |
