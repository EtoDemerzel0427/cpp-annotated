---
title: 限定名字查找
summary: X::m 和 obj.m 中的名字怎样查找：:: 前面的名字只考虑命名空间和类型，后面的名字在前者指定的类、命名空间或对象类型里搜索；类自己限定的 A::A 指构造函数；N::x 先查 N 和它的内联命名空间，找不到才沿 using 指令继续。
status: done
covers: basic.lookup.qual.general, class.qual, namespace.qual
papers: P1787R6
related: basic.lookup, class.member.lookup, basic.lookup.unqual, expr.prim.id.qual, expr.ref, namespace.udir, namespace.def, class.pre, namespace.udecl, temp.res
tags: 名字查找, 命名空间, 嵌套名说明符
updated: 2026-10-19
---

!!! tldr
    - `X::` 里的 `X` 只考虑命名空间、类型和类模板，同名的变量、函数会被跳过。
    - `X::m` 里的 `m` 只在 `X` 里搜索；`obj.m`、`p->m` 里的 `m` 在对象的类型里搜索。限定查找从不往外层作用域找。
    - `p->B::f()` 里的 `B` 先在对象的类里找，找不到才在表达式所在处做无限定查找。这是 C++23 的规则，Clang 23 仍按旧规则实现。
    - 类自己限定的 `A::A` 指构造函数，不是类型；派生类限定的 `B::A` 才是类型。
    - `N::x` 先查 `N` 和它的内联命名空间；什么也没找到时，才去查 `N` 里 using 指令提名的命名空间。

## `::` 前面的名字（[basic.lookup.qual.general] ¶1）

```cpp run error
class A {
public:
    static int n;
};
int main() {
    int A;
    A::n = 42;    // OK：A:: 只考虑类型，局部变量 A 被跳过
    A b;          // error: 普通查找找到局部变量 A，它不是类型
}
```

¶1 后面紧跟 `::` 的标识符，查找时只考虑命名空间、类型，以及特化为类型的模板。`X::` 的意思是到 `X` 的作用域里找东西，只有命名空间、类和枚举有这样的作用域。同名的变量、函数应当跳过，否则在类名和变量名相同的 C 风格代码里，就没法访问类的静态成员。

¶1 第二句规定，后面跟 `::` 的名字、模板标识（*template-id*，如 `B<0>`）等，必须指代命名空间、类、枚举或依赖类型。只考虑类型这条限制针对的是直接后跟 `::` 的标识符，后跟 `<` 的名字仍做普通查找：

```cpp run error
struct A { static int n; };
template<int> struct B : A {};
namespace N {
    template<int> void B();
    int f() {
        return B<0>::n;   // error: N::B<0> 不是类型
    }
}
```

`B` 后面跟的是 `<`，所以对 `B` 做普通的无限定查找，在 `N` 中找到函数模板 `N::B` 就停下，全局的类模板 `::B` 被挡住。`N::B<0>` 是函数模板特化，不能放在 `::` 前面。

能出现在 `::` 前面的形式越来越多：

| 形式 | 例子 | 引入 |
|---|---|---|
| 命名空间名、类名、枚举名、typedef 名 | `std::`、`Outer::`、`Color::` | C++98（枚举名 C++11） |
| 模板标识 | `std::vector<int>::` | C++98 |
| `decltype` 说明符 | `decltype(s)::In::` | C++11 |
| 包索引说明符 | `Ts...[0]::type` | {{c++26}} |
| 拼接作用域说明符 | `[:r:]::` | {{c++26}} |

```cpp run ok
template<class... Ts>
struct First { using type = typename Ts...[0]::type; };   // C++26：包索引后跟 ::
struct I { using type = int; };
static_assert(__is_same(First<I, double>::type, int));

struct S { struct In { static const int v = 1; }; };
S s;
int k = decltype(s)::In::v;                                // C++11：decltype 后跟 ::
```

## 限定名和查找上下文（¶2）

`N::C::m.Base::f()` 里有好几个名字，每个都要知道该到哪里去找。¶2 为此定义了几个术语。

¶2 [[g:member-qualified-name|成员限定名]]（member-qualified name）是成员访问 `obj.X`、`p->X` 中紧跟 `.` 或 `->` 的那个名字：要么是普通的成员名（`obj.m` 中的 `m`），要么是 `类型名::`、`命名空间名::` 形式的前缀（`p->Base::f()` 中的 `Base`）。

[[g:qualified-name|限定名]]（qualified name）包括成员限定名，以及所有带 `X::` 前缀的名字的最后一个组成部分：*qualified-id*、using 声明、`typename T::x`、命名空间别名等里面的那个名字。

每个限定名都有一个[[g:lookup-context|查找上下文]]（lookup context），也就是到哪里去找它：

- 成员限定名的查找上下文是对象表达式的类型。对象表达式的类型依赖于模板参数时，查找上下文也算依赖的。
- 其他限定名的查找上下文是前面的 `X::` 所指的类型、模板或命名空间。

在 `N::C::m.Base::f()` 中，`Base` 是成员限定名，到 `N::C::m` 的类型里找；`C` 到 `N` 里找，`m` 到 `N::C` 里找，`f` 到 `Base` 所指的类里找。注 1 补充，解析成员访问时，`.` 和 `->` 后面的名字一律算限定名，尽管这时还不知道它是哪一种。

## 在查找上下文里搜索（¶3）

¶3 在类、命名空间或枚举里做**限定名字查找**（qualified name lookup），就是在它的作用域里做一次[[g:search-in-scope|搜索]]。类作用域的搜索会扩展到基类（[[class.member.lookup]]），命名空间另有 [namespace.qual] 的补充规则。

限定名就在它的查找上下文里、从它出现的位置做这种查找。有两种例外：查找上下文依赖于模板参数且不是当前实例化（[[temp.dep.type]]），这时要等实例化；查找上下文不是类，例如 `p->m` 中 `p` 指向 `int`。

¶3 还有一条回退规则：如果一个成员限定名后面跟着 `::`，不是依赖名，而在类里什么也没找到，就改做无限定查找。这条规则针对的是 `p->Base::f()` 中的 `Base`：先在 `*p` 的类里找，通常能找到基类的注入类名（类名在类自己作用域内的副本，[[class.pre]]）；找不到，再从表达式所在处向外找。

注 2 指出，在模板特化里查找时，已经没有依赖名了。

### 标准例 3

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
void g(T *p) {                  // 以下按 g<A> 的实例化解释
    p->X<0>::f();               // error: A 中没有 X，解析成 ((p->X) < 0) > ::f()
    p->template X<0>::f();      // OK：回退，在定义处找到 ::X
    p->B::f();                  // OK：A::B 不是类型，被跳过，回退找到 ::B
    p->template C<0>::f();      // error: A::C 不是模板
    p->template D<0>::f();      // error: A::D<0> 不是类类型
    p->T::f();                  // error: A::T 不是类类型
}
template void g(A*);
```

1. `p->X<0>::f()`：`X` 的查找上下文 `T` 是依赖的，推迟到实例化。实例化时在 `A` 里找不到 `X`。前面没有 `template` 关键字，`<` 是否开始模板实参列表取决于查找结果（[[temp.names#7]]），既然没找到，`<` 就是小于号。整个表达式成了 `((p->X) < 0) > ::f()`，而 `p->X` 不存在。
2. 加了 `template` 后，`X<0>` 一定是模板标识。`X` 在 `A` 里找不到，按 ¶3 回退到定义处的无限定查找，找到 `::X`，`::X<0>` 就是 `A`。
3. `B` 后跟 `::`，按 ¶1 只考虑类型，`A` 的数据成员 `B` 被跳过，于是什么也没找到，回退后找到 `::B`。
4. `C` 在 `A` 里找到数据成员 `C`。`template C<0>` 要求 `C` 是模板，但它不是。已经找到了东西，就不再回退。
5. `D` 在 `A` 里找到成员别名模板，`A::D<0>` 是 `void`，不是类。
6. `T` 在 `A` 里找到 `A::T`，即 `void`。这里的 `T` 是在 `A` 里查找的成员限定名，不是 `g` 的模板参数 `T`。

!!! impl "编译器现状"
    本机 Clang 23 对例 3 只拒绝第 6 行，接受第 1、4、5 行。它沿用的是 C++20 及以前的规则：成员访问中 `::` 前的名字，既在对象的类里找，也在整个表达式所在的上下文里找，选能用的那个。按当前草案，这三行都非良构。

!!! history "旧规则：两处都找"
    C++98 到 C++20 的 [basic.lookup.classref] 规定，`p->X::m` 里的 `X` 既在 `*p` 的类里查找，也在整个后缀表达式的上下文里查找；两处都找到时必须是同一个实体。这条规则复杂，容易互相矛盾，还和模板里的依赖查找纠缠在一起。[[P1787R6]] 把它换成了 ¶3 的规则：先在类里找，找不到再回退。

## 析构函数名（¶4）

`~X` 中的 `X` 有很多合法写法：类名、typedef、模板参数，甚至是标量类型的别名（`p->~I()`，`I` 是 `int` 的别名，这叫伪析构函数调用）。¶4 的思路是在几个地方都试一试，只要有一种解释和对象类型对得上就行。

¶4 设限定名 `Q` 跟在 `~` 后面：

- ¶4.1 `Q` 是成员限定名（`p->~Q()`）时，它既做无限定查找，也做限定查找；
- ¶4.2 否则，它前面的 `N::` 必须指一个类型。如果 `N` 前面还有一层 `S::`（`S::N::~Q`），`Q` 就到 `S` 里找；
- ¶4.3 否则，如果 `N` 本身是成员限定名（`p->N::~Q`），对 `Q` 的查找如同 `~Q` 出现在 `N` 的位置，也就是按 ¶4.1；
- ¶4.4 否则 `Q` 做无限定查找。

¶4.5 每一次查找都只考虑类型（`Q` 后面不跟 `<` 时）和特化为类型的模板，什么也没找到或二义的那次查找作废。¶4.6 在至少一次成功查找给出的解释下，含 `Q` 的类型名必须就是原来的查找上下文（忽略 cv 限定）。

```cpp run ok
struct C { typedef int I; };
typedef int I1, I2;
void f(int* p, int* q) {
    p->C::I::~I();      // ¶4.2：I 到 C 里找，找到 C::I，即 int
    q->I1::~I2();       // ¶4.3、¶4.1：I2 在 int 里查不到，无限定查找找到 ::I2
}
struct A { ~A(); };
typedef A AB;
void g(AB* p) {
    p->AB::~AB();       // 显式调用 A 的析构函数
}
```

C++20 起，对标量类型调用伪析构函数会结束对象的生存期（[[expr.prim.id.dtor]]）。

## `A::A` 是构造函数 [class.qual]

```cpp run error
struct A { A(); };
struct B : public A { B(); };

A::A() { }          // OK：A::A 指构造函数
B::B() { }

B::A ba;            // OK：在 B 里找到的是基类 A 的注入类名，指类型 A
struct A::A a2;     // OK：详述类型说明符忽略函数名，A::A 指类型
A::A a;             // error: A::A 指构造函数，不是类型
```

[class.qual] ¶1 在查找上下文为类 `C`、不忽略函数名的限定查找中，以下两种情况的名字 `N` 被认为指 `C` 的构造函数：

- ¶1.1 搜索找到的是 `C` 自己的注入类名；
- ¶1.2 `N` 是依赖名，并且是一个继承构造函数的 using 声明的最后一个名字。

这样得到的构造函数名，只能用在构造函数（包括友元构造函数）声明的声明符里，或者用在 using 声明里。

脚注 15 列出了忽略函数名的查找：`::` 前面的名字、详述类型说明符（`struct X` 这种带关键字的写法）、基类说明符。在这些地方，注入类名照常指类型。

`B::A` 不是构造函数，因为 ¶1.1 要求找到的是查找上下文 `C` 自己的注入类名。在 `B` 里找到的是基类 `A` 的注入类名，只是普通的类型名。

早期标准里，`A::A` 有时指类型，有时指构造函数，`A::A::A::A` 这类写法的含义不清。现在的规则是统一的：在不忽略函数名的地方，`C::C` 就是构造函数；要指类型，就写 `C` 或 `struct C::C`。

```cpp run ok
struct A { A(); };
A::A::A::A() { }    // 前面三个 A 在 :: 前，忽略函数名，指类 A；
                    // 最后的 A::A 在声明符里，指构造函数
```

¶1.2 处理模板里的继承构造函数。`using TB<T>::TB;` 中的 `TB` 是依赖名，定义时没法查找确认它是注入类名，所以标准直接规定它指构造函数：

```cpp run ok
struct Base { Base(int); };
struct Der : Base { using Base::Base; };     // 继承 Base 的构造函数
Der d(1);

template<class T> struct TB { TB(T); };
template<class T> struct TD : TB<T> { using TB<T>::TB; };   // ¶1.2
TD<int> td(1);
```

## 命名空间成员 [namespace.qual]

### 先查 N，找不到才沿 using 指令（¶1）

[namespace.qual] ¶1 在命名空间 `N` 中做限定查找时，分两步：

1. 搜索 `N`，以及 `N` 的内联命名空间集（[[namespace.def]]）里的每个命名空间；
2. 如果什么也没找到，就对 `N`（及其内联命名空间）中、在查找点之前的每条 using 指令所提名的命名空间，递归地做限定查找，结果合在一起。

注 1 指出，指向已经考虑过的命名空间的 using 指令不影响结果。这保证了递归会结束。

标准例 1：

```cpp run error
int x;
namespace Y { void f(float); void h(int); }
namespace Z { void h(double); }
namespace A { using namespace Y; void f(int); void g(int); int i; }
namespace B { using namespace Z; void f(char); int i; }
namespace AB { using namespace A; using namespace B; void g(); }

void h() {
    AB::g();      // AB 中直接声明了 g，结果是 {AB::g}
    AB::f(1);     // AB 中没有 f，递归到 A、B；A 中有 f，不再进入 Y
                  // 结果 {A::f(int), B::f(char)}，选 A::f(int)
    AB::f('c');   // 同上，选 B::f(char)
    AB::h(16.8);  // AB、A、B 都没有 h，递归到 Y、Z：{Y::h(int), Z::h(double)}，选 Z::h
    AB::x++;      // error: AB、A、B、Y、Z 都没有 x；全局的 ::x 不在其中
    AB::i++;      // error: {A::i, B::i} 是两个实体，二义
}
```

`AB::f(1)` 最能说明找不到才递归的意思：`A` 里有 `f`，所以这一支不再深入 `Y`，`Y::f(float)` 不是候选，哪怕它对某些实参是更好的匹配。

这和无限定查找对待 using 指令的方式不同：

| | 无限定查找（[[basic.lookup.unqual]]） | 限定查找 `N::x` |
|---|---|---|
| using 指令提名的命名空间 | 在某一层外围命名空间，和这一层的声明一起搜索 | 只有 `N`（及其内联命名空间）什么也没找到时才进入 |
| 内联命名空间 | 视同外层命名空间里的 using 指令 | 和 `N` 同时搜索 |

### 同一个声明找到两次不算二义（¶2）

¶2 注 2 指出，同一个声明被找到多次仍然只是一个声明，不构成二义：

```cpp run ok
namespace A { int a; }
namespace B { using namespace A; }
namespace C { using namespace A; }
namespace BC { using namespace B; using namespace C; }
void f() { BC::a++; }    // OK：{A::a, A::a}，同一个声明

namespace D { using A::a; }
namespace BD { using namespace B; using namespace D; }
void g() { BD::a++; }    // OK：D 中的 using 声明换成 A::a，仍是同一个声明
```

### 每个命名空间至多搜索一次（¶3）

¶3 例 3 说明，因为每个命名空间只搜索一次，互相提名的 using 指令不会造成无限循环：

```cpp run ok
namespace B { int b; }
namespace A { using namespace B; int a; }
namespace B { using namespace A; }      // A 与 B 互相提名

void f() {
    A::a++;     // OK：a 直接在 A 中
    B::a++;     // OK：B 中没有 a，搜索 A，找到 A::a
    A::b++;     // OK：A 中没有 b，搜索 B，找到 B::b
    B::b++;     // OK：b 直接在 B 中
}
```

### 来自不同命名空间的类不会被隐藏（¶4）

同一作用域里，类名会被同名的变量隐藏（[[basic.lookup#4]]）。¶4 注 3 指出，这条规则只在同一次搜索内起作用。经 using 指令在不同命名空间里分别找到类和变量时，类不会被丢弃，结果是二义：

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
    int i = C::x;   // OK：在 A 中一次找到两者，类被丢弃，得到变量 A::x
    int j = C::y;   // error: A::y 和 B::y 来自不同的搜索，二义
}
```

### 内联命名空间

在限定查找中，内联命名空间的成员就像外层命名空间的成员一样。库的版本管理就建立在这一点上：

```cpp run ok
namespace lib {
    inline namespace v2 {
        struct W {};
        void f(W);
    }
    namespace v1 { struct W {}; }
}
lib::W w;                // 找到 lib::v2::W
void t() {
    lib::f(w);           // OK
    lib::v2::f(w);       // OK：显式指定版本
    f(w);                // OK：ADL，关联命名空间 lib 及其内联命名空间集
}
```

和 using 指令不同，内联命名空间在第 1 步就和 `N` 一起搜索。所以如果 `lib` 自己也声明了 `W`，`lib::W` 就二义了。

!!! impl "实现视角"
    内联命名空间的名字会进入修饰名。libc++ 的 `std::vector<int>` 实际是 `std::__1::vector<int>`，Itanium ABI 下修饰名里含 `NSt3__16vectorIiNS_9allocatorIiEEEE`；libstdc++ 的修饰名没有这一层，所以用两个库编译的代码不会意外地链接在一起。源码层面，限定查找和 ADL 让 `std::vector` 直接找到 `std::__1::vector`。

!!! history "历史与演进"
    - C++98：限定查找、成员访问中的两处查找、命名空间限定查找沿 using 指令传递，这些规则都已存在。
    - C++11：引入内联命名空间；`decltype` 可以放在 `::` 前；枚举名可以用作限定（`Color::red`）。
    - C++23：[[P1787R6]] 引入成员限定名和查找上下文，用“先在类里找，找不到再回退”取代两处查找，并把 `A::A` 指构造函数的规则统一写进 [class.qual]。
    - C++26：包索引说明符（`Ts...[0]::`）和拼接作用域说明符（`[:r:]::`）可以放在 `::` 前。

## 常见误解

!!! pitfall "N::x 找不到时会往外层找"
    限定查找只看 `N`、`N` 的内联命名空间和 `N` 中 using 指令（递归）提名的命名空间，从不看 `N` 的外层。`AB::x` 不会找到全局的 `::x`。

!!! pitfall "using 指令提名的命名空间和 N 地位相同"
    只要 `N` 自己（或它的内联命名空间）有一个同名声明，using 指令提名的命名空间就完全不考虑。给 `N` 新增一个声明，可能让原来经 using 指令找到的更好重载消失。

!!! pitfall "B::A 和 A::A 是一回事"
    派生类限定的基类名 `B::A` 是类型，类自己限定的 `A::A` 是构造函数。模板里写 `typename Derived::Base` 是常见而合法的写法。

## 思考题

!!! question "思考题 1"
    ```cpp
    namespace N { inline namespace I { int v = 1; } }
    namespace M { int v = 2; }
    namespace N { using namespace M; }
    int r = N::v;
    ```
    `r` 是多少？去掉 `inline` 呢？

<details markdown="1">
<summary>答案</summary>

有 `inline` 时，第 1 步搜索 `N` 和它的内联命名空间 `I`，找到 `N::I::v`，`r == 1`，using 指令不予考虑。

去掉 `inline` 后，第 1 步在 `N` 中找不到 `v`（`I` 不再属于内联命名空间集），进入第 2 步：using 指令提名 `M`，找到 `M::v`，`r == 2`。本机 Clang 23 的运行结果与此一致。
</details>

!!! question "思考题 2"
    在 `template<class T> void g(T* p) { p->Base::f(); }` 中，如果实例化时 `T` 的类里没有名为 `Base` 的类型，但 `g` 的定义处能找到一个全局类 `Base`，按 C++23 的规则会怎样？如果 `T` 的类里有一个名为 `Base` 的数据成员呢？

<details markdown="1">
<summary>答案</summary>

`Base` 是成员限定名，后面跟着 `::`。实例化时在 `T` 的类里查找，只考虑类型（¶1），什么也没找到，于是按 ¶3 回退到无限定查找，找到全局的 `Base`。之后 `Base::f` 还要求 `Base` 是 `*p` 的可访问、无二义的基类，否则成员访问非良构。

如果 `T` 的类里的 `Base` 是数据成员，它同样因为不是类型而被跳过，结果仍是什么也没找到，回退的过程和例 3 中的 `p->B::f()` 一样。
</details>

## 小结

| 规则 | 要点 |
|---|---|
| `X::` 中的 `X` | 只考虑命名空间、类型、类模板；必须指命名空间、类、枚举或依赖类型 |
| 成员限定名 | `.`、`->` 后面的名字或 `T::` 前缀；查找上下文是对象的类型 |
| 查找上下文 | 前面的 `X::` 所指的实体；依赖时推迟到实例化 |
| 回退 | 成员访问里 `::` 前的名字在类里找不到时，做无限定查找 |
| 析构函数名 | 在几处查找，有一种解释和对象类型对得上即可 |
| `C::C` | 不忽略函数名时指构造函数；`B::A`、`struct A::A` 是类型 |
| 命名空间限定 | `N` 加内联命名空间；找不到才沿 using 指令递归；每个命名空间至多一次；不往外找 |
| 二义 | 同一声明找到多次不算；不同搜索中的类不被变量隐藏 |
