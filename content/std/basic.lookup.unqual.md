---
title: 无限定名字查找
summary: 不带 :: 或成员访问前缀的名字，从其直接作用域出发沿父作用域链逐层做无限定搜索，并在恰当的层级并入活跃 using 指令提名的命名空间；本页从这一个算法推出函数体、成员函数、友元、模板参数等所有场景的查找顺序。
status: done
papers: P1787R6
related: basic.lookup, class.member.lookup, basic.lookup.argdep, namespace.udir, basic.scope.scope, basic.scope.pdecl, class.mem, temp.local, class.friend
tags: 名字查找, 作用域, using 指令
updated: 2026-10-17
---

绝大多数名字都是**无限定的**（unqualified）：`x`、`f(a)`、`T`、`operator+`……它们没有 `N::` 前缀告诉编译器去哪里找，只能从所在位置往外找。本节规定了往外找的精确含义。

在 C++20 及以前，本节是一张场景清单（命名空间作用域的名字、成员函数体中的名字、友元函数中的名字、构造函数的 mem-initializer 中的名字……）。从 C++23 起（P1787R6），本节只剩一个算法：

1. 名字所在的程序点有一个**直接作用域**（immediate scope，[[basic.scope.scope#1]]）；
2. 在这个作用域里做一次无限定搜索，没找到就到它的父作用域继续；
3. 在每一层，同时搜索在这一层生效的 using 指令所提名的命名空间。

旧清单里的所有场景，都可以由作用域的嵌套方式（第 6.4 节各条）与这一算法共同推出。下面先讲算法（¶1–¶3），再讲两条特例（¶5、¶6），最后逐一推演常见场景。

## 活跃的 using 指令（¶1）

¶1 一个 *using-directive* 在作用域 S 中、程序点 P 处[[g:active-using-directive|活跃]]（active），当且仅当它先于 P（[[basic.lookup#2]]），并且栖身于：

- S 本身，或
- 某个在 S 中活跃的 using 指令所提名的命名空间的作用域。

第二款是递归的：S 里有 `using namespace A;`，A 里又有 `using namespace B;`，那么 A 中的那条指令在 S 中也活跃。这就是 using 指令的**传递性**（[[namespace.udir#5]]）。

## 无限定搜索（¶2）

¶2 在作用域 S 中从 P 出发的[[g:unqualified-search|无限定搜索]]（unqualified search），包括以下各次搜索（[[class.member.lookup#1|搜索]]）的结果：

- ¶2.1 S 本身；
- ¶2.2 对每个包含 P、且是 S 或被 S 包含的作用域 U：在 U 中于 P 处活跃的 using 指令所提名的、被 S 包含的每个命名空间。

若什么都没找到，结果就是在 S 的父作用域中从 P 出发做无限定搜索的结果（如果有父作用域）。

注 1 补充两点：

- 搜索类作用域时，也搜索基类作用域（[[class.member.lookup]]）。单继承时，就好像基类作用域直接包含派生类作用域。
- 与作用域链上某个作用域相关联的模板参数作用域也在考虑之列（[[temp.local]]）。

¶3 **无限定名字查找**从程序点出发，在其直接作用域中做一次无限定搜索。

### ¶2.2 的含义：如同声明在最近的公共外围命名空间

¶2.2 读起来很绕，但它精确地表达了教科书里那条常见的规则：

!!! std
    During unqualified name lookup, the names appear as if they were declared in the nearest enclosing namespace which contains both the using-directive and the designated namespace.

    （[[namespace.udir#3]] 注 2）无限定查找时，被提名命名空间中的名字如同声明在"同时包含该 using 指令与被提名命名空间的最近外围命名空间"中。

原因在于，按 ¶2.2，只有搜索到包含 A 的作用域 S 时，被提名的命名空间 A 才会并入（"被 S 包含"这一条件）；而 using 指令所在的作用域 U 必须在 S 之内（"是 S 或被 S 包含"）。同时满足这两个条件的最内层 S，正是同时包含 using 指令与 A 的最近作用域，A 的名字到这一层才与 S 自己的名字一起参与搜索。

推演一个例子：

```cpp run ok
namespace A { int i = 1; }
namespace B {
    long i = 2;
    void f() {
        using namespace A;      // 指令栖身于 f 的块作用域
        static_assert(__is_same(decltype(i), long));   // 找到的是 B::i
    }
}
void g() {
    using namespace A;
    static_assert(__is_same(decltype(i), int));        // 找到的是 A::i
}
```

在 `B::f` 中查找 `i`：

| 搜索的作用域 S | 并入的命名空间（¶2.2） | 结果 |
|---|---|---|
| f 的块作用域 | A 不被块作用域包含 → 不并入 | 无 |
| f 的函数参数作用域 | 同上 | 无 |
| 命名空间 B | A 不被 B 包含 → 不并入 | **B::i**，停止 |

`A` 要到全局作用域才会并入，但搜索在 B 就停了。所以 using 指令不会让 `A::i` 隐藏外层的 `B::i`，A 的名字实际上放在了更外面的一层。而在全局函数 `g` 中，全局作用域既包含指令又包含 A，`A::i` 在全局这一层参与搜索。

反过来，若那一层本来就有同名声明，就会产生二义：

```cpp run error
int x = 0;
namespace A { int x = 1; }
void f() {
    using namespace A;
    x = 2;            // error: 在全局作用域这一层同时找到 ::x 与 A::x → 二义
}
```

而局部声明总是先找到，using 指令无法盖过它们：

```cpp run ok
namespace N { int y = 0; }
int f() {
    using namespace N;
    int y = 1;        // 块作用域的 y
    return y;         // 局部 y；N::y 要到全局层才参与
}
```

!!! tip "与 using 声明对比"
    `using N::y;` 是一个声明，它把 `y` 绑定在所在作用域中，因此在块作用域里写了 `using N::y;` 再写 `int y;`，就是冲突的重声明。using 指令不声明任何名字（[[namespace.udir#4]]），只改变在哪一层同时搜索哪个命名空间。

## 无限定名字的定义（¶4）

¶4 不紧跟在 *nested-name-specifier* 之后、也不紧跟在类成员访问的 `.` 或 `->` 之后的名字（中间可以隔着 `template` 关键字或 `~`），称为**无限定名字**。除非另有规定，这样的名字从其出现处做无限定名字查找。

另有规定的常见情形有：

- 函数调用 `f(args)` 的 `f` 还要加上 ADL 的结果（[[basic.lookup.argdep]]）；
- 运算符表达式里的 `operator@` 查找忽略成员函数（[[over.match.oper#3]]）；
- 非限定的友元函数声明不查找其名字（[[dcl.meaning.general#2]]）；
- 声明的 *declarator-id* 不是对名字的使用，不做查找；
- 下面 ¶5 的转换类型标识与 ¶6 的友元声明符。

## 转换函数名中的类型（¶5）

¶5 在 *conversion-type-id*（`operator T*` 中的 `T*`）里，*type-specifier* 或 *ptr-operator* 的无限定组件名先按整个 *conversion-function-id* 的查找方式查找，找不到再做无限定查找。两种情况都只考虑类型，以及特化为类型的模板。

这样规定的原因可以从 `x.operator T()` 看出：这个转换函数属于 `x` 的类，它声明里的 `T` 很可能是那个类的成员类型。若只在调用处做无限定查找，就无法写出调用这类转换函数（以类内类型别名声明）的表达式。

```cpp run ok
struct T1 { struct U { int i; }; };
struct T2 { };
struct U1 {};
struct U2 {};

struct B {
    using T = T1;
    using U = U1;
    operator U1 T1::*();
    operator U1 T2::*();
    operator U2 T1::*();
    operator U2 T2::*();
};

template<class X, class T>
int g() {
    using U = U2;
    X().operator U T::*();                // #1：U 与 T 都先在 X（=B）中找 → B::U、B::T
    X().operator U decltype(T())::*();    // #2：U 在 B 中找到 B::U；decltype 里的 T 是普通表达式中的名字
    return 0;
}
int x = g<B, T2>();   // #1 调用 B::operator U1 T1::*
                      // #2 调用 B::operator U1 T2::*
```

`#1` 中 `operator U T::*` 作为成员限定名，在 `X` 的类即 B 中查找；`U`、`T` 作为它的组件名也先在 B 中找，分别得到 `B::U`（U1）与 `B::T`（T1）。`#2` 中 `decltype(T())` 里的 `T` 是表达式中的名字，按普通规则找到模板参数 `T`（T2）。

## 带限定名的友元声明符（¶6）

¶6 在友元声明的声明符中，若 *declarator-id* 是 *qualified-id*，且其嵌套名说明符指定类或命名空间 S，那么出现在 *declarator-id* 之后的无限定名字先在 S 的作用域中搜索，找不到再做普通的无限定查找。

这样规定的动机是：`friend void A::f(F);` 把 A 中已有的某个 `f` 声明为友元，参数类型 `F` 自然应该按 `A::f` 原声明的语境来理解。这与类外定义成员函数的情形一致，`void X::g(T)` 中的 `T` 先在 X 中找（因为 *declarator-id* 之后的部分属于类作用域，[[basic.scope.class#1]]）。但友元声明不算进入那个作用域的重声明（[[basic.scope.class#1]] 明确排除了 friend），所以需要本条单独规定。

```cpp run error
using I = int;
using D = double;
namespace A {
    inline namespace N { using C = char; }
    using F = float;
    void f(I);
    void f(D);
    void f(C);
    void f(F);
}
struct X0 { using F = float; };
struct W {
    using D = void;
    struct X : X0 {
        void g(I);
        void g(::D);
        void g(F);
    };
};
namespace B {
    typedef short I, F;
    class Y {
        friend void A::f(I);        // error: I 在 A 中找不到 → 外层 B::I(short)；没有 A::f(short)
        friend void A::f(D);        // OK：D 在 A 中找不到 → ::D(double)
        friend void A::f(C);        // error: 在 A 中搜索不考虑内联命名空间 N 的成员
        friend void A::f(F);        // OK：F 在 A 中找到 A::F(float)
        friend void W::X::g(I);     // error: 没有 X::g(short)
        friend void W::X::g(D);     // OK：D 在 X 中（含基类 X0）找不到 → 外层，W::D 不在作用域链上 → ::D
        friend void W::X::g(F);     // OK：F 在 X 的基类 X0 中找到
    };
}
```

有几处细节值得说明：

- `A::f(C)`：¶6 说的是在 S 的作用域中做一次搜索，而搜索（单次搜索）不包括内联命名空间，只有限定名字查找才额外搜索内联命名空间集（[[namespace.qual#1]]）。所以找不到 `C`。
- `W::X::g(D)`：在 X 中（含 X0）搜索 D 找不到，于是回到友元声明所在处做无限定查找。作用域链是 Y → B → 全局，不经过 W，所以找到 `::D`（double）。

!!! impl "编译器现状"
    在本机测试，Clang 23 对 S 是类的情形实现了本条（`W::X::g(F)` 通过），但对 S 是命名空间的情形没有实现：Clang 拒绝 `friend void A::f(F);`，把 `F` 解析为 `B::F`（short），报告友元声明与 A 中的任何声明都不匹配。按标准，这一行应是良构的。

## 场景推演：由作用域链决定

下面用作用域嵌套加无限定搜索，重新推导旧标准场景清单里的主要情形。

### 块作用域与声明位置

名字只能找到先于查找点的声明，而声明的位置（locus）在完整声明符之后（[[basic.scope.pdecl#1]]）。所以：

```cpp run ok
const int i = 2;
void g() {
    int i[i];      // 声明符 i[i] 中的 i 查找时，新 i 的 locus 还没到 → 找到 ::i
                   // 结果：两个 int 的数组
    (void)i;
}
```

而在 `int v = v;` 中，初始化器位于声明符之后，找到的是正在声明的 `v` 自己；读取它是在其生命期外访问，行为未定义（[[basic.scope.pdecl#1]] 的例子）。

### 命名空间成员函数的类外定义

在 `void N::g() { ... }` 中，*declarator-id* 之后的部分属于命名空间 N 的作用域（[[basic.scope.namespace#1]]），所以函数体中的无限定名字先在 g 的块作用域中找，然后是 N，最后才是全局，尽管这个定义在文本上写在全局。

```cpp run ok
namespace N { void g(); int helper(); }
void N::g() {
    helper();        // OK：找到 N::helper——函数体在 N 的作用域内
}
```

### 成员函数：完整类上下文与类外定义

类定义内的成员函数体是完整类上下文（[[class.mem#10]]），无限定搜索到达类作用域时，按 [[class.member.lookup#3]] 从类定义末尾开始搜索，所以可以使用后面才声明的成员。默认实参、默认成员初始化器、noexcept 说明符也是如此；但数组边界、成员类型等不是完整类上下文：

```cpp run error
struct X {
    int f(int a = k) { return a + m; }      // OK：默认实参与函数体都是完整类上下文
    static constexpr int k = 3;
    int m = 0;
    friend int peek(const X& x) { return x.m + k; }   // OK：友元函数体在类内定义，位于类作用域中
    int arr[k2];                            // error: 数组边界不是完整类上下文，k2 尚未声明
    static constexpr int k2 = 4;
};
```

在类外定义 `X::T X::f() {...}` 中，*declarator-id* `X::f` 之后的部分（参数列表、尾置返回类型、函数体）属于类作用域（[[basic.scope.class#1]]），之前的返回类型则不属于，要写全限定：

```cpp run error
struct X { using T = int; T f(); T g(); auto h() -> T; };

X::T X::f() { T local = 0; return local; }  // OK：返回类型需限定，函数体内 T 直接可用
auto X::h() -> T { return 0; }              // OK：尾置返回类型在 declarator-id 之后
T X::g() { return 0; }                      // error: 返回类型处 T 不在 X 的作用域内
```

### 友元函数

- 在类内定义的友元函数，其函数体在文本上位于类的 *member-specification* 内，因此其作用域链经过类作用域，可以直接使用类的成员名（上例 `peek` 中的 `k`）。这对应旧标准 [basic.lookup.unqual] 中关于在类内定义的友元函数的专门段落。
- 在类外定义的友元函数不在类作用域中（[[class.friend#6]] 注 3），因为 [[basic.scope.class#1]] 把友元重声明排除在外。
- 友元声明本身不绑定名字（[[class.friend#10]]），所以在 `friend void f(X);` 之后，在外层命名空间中做无限定查找找不到这个 `f`，只有 ADL 能找到它。这是隐藏友元（hidden friend）惯用法的基础，详见 [[basic.lookup.argdep]]。

### 局部类

局部类成员函数体的作用域链经过外围函数的块作用域，所以查找能找到外围函数的局部变量；但 odr-use 它们是非良构的（[[basic.def.odr]]），不构成 odr-use 的使用（如 `sizeof`、常量）则是允许的：

```cpp run error
void f() {
    int n = 1;
    const int c = 2;
    struct L {
        int g() { return sizeof(n) + c; }   // OK：n 未被 odr-use；c 是可用于常量表达式的常量
        int h() { return n; }               // error: odr-use 了外围函数的自动变量
    };
    (void)n;
}
```

### 隐藏是找到即停的副产品

旧标准用专门条款规定内层声明隐藏外层同名声明。新模型不需要这样的条款：无限定搜索在某一层找到任何东西就停止，根本看不到外层。这也解释了为什么**内层的一个函数会隐藏外层的所有同名重载**：

```cpp run ok
void h(int);
namespace N {
    void h(double);
    void k() { h(1); }   // 调用 N::h(double)：搜索在 N 找到 h 就停了，::h(int) 不是候选
}
```

（若实参有类类型，ADL 可能再把别处的函数加回来，这时 ADL 与无限定查找的结果合在一起，见 [[basic.lookup.argdep]]。）

### 模板参数作用域

[[temp.local#7]] 规定，无限定查找在与模板声明相关联的最外层作用域之后，紧接着考虑该模板声明的模板参数作用域，即使该作用域的父作用域在文本上并不包含模板参数列表（类外定义的情形）。由此可以推出：**类模板的成员（包括非依赖基类的成员）比模板参数先找到**。

```cpp run ok
struct B { };
namespace N {
    typedef void V;
    template<class T> struct A : B {
        typedef void C;
        void f();
        template<class U> void g(U);
    };
}

template<class V> void N::A<V>::f() {      // N::V 在这里不被考虑
    V v;                                   // V 仍是模板参数（int），不是 N::V（void）
    static_assert(!__is_same(V, void));
}

template<class B> template<class C> void N::A<B>::g(C) {
    B b;                                   // B 是基类 ::B（类作用域及其基类先被搜索），不是模板参数
    C c;                                   // C 是成员模板 g 的模板参数，不是 A::C
    static_assert(__is_same(B, ::B));
}
template struct N::A<int>;
template void N::A<int>::g(long);
```

`f` 中的 `V`：搜索顺序是 f 的块 → 参数作用域 → 类 A（含基类 B）→ A 的模板参数作用域 → N → 全局，所以先在 N 之前找到模板参数 `V`。`g` 中的 `B`：类 A 的作用域（含基类 `B` 的注入类名）先于模板参数作用域，于是 `B` 指基类。至于 `C`，标准例子说 `C` 是成员模板 g 的模板参数，而不是 `A::C`，因为成员模板 g 的模板参数作用域紧接在与 g 相关联的最外层作用域之后，即在 g 自己的参数作用域之后、类 A 之前。

此外，[[temp.local#6]] 禁止在模板参数的作用域内再把同一个名字绑定到其他声明（`template<class T> struct Y { int T; };` 非良构），所以模板参数被成员隐藏的情况只能经由基类成员或类外定义发生。

### 依赖基类

无限定搜索到达类模板作用域时，按 [[class.member.lookup#4]] 只合并非依赖基类。依赖基类的成员要用 `this->`、`Derived::` 或 `typename Derived::` 访问：

```cpp run error
template<class T> struct Base { using type = T; };
template<class T> struct D : Base<T> {
    typename D::type y;   // OK：限定名，查找推迟到实例化
    type x;               // error: 无限定查找不进入依赖基类
};
```

!!! impl "实现视角"
    - Clang 的 `Sema::CppLookupName` 沿 `Scope`/`DeclContext` 链向外走，每到一层，用 `UnqualUsingDirectiveSet` 按公共外围命名空间把 using 指令提名的命名空间挂到对应层级，这与 ¶2.2 的规范描述等价。
    - 依赖基类的查找：在 `/permissive-` 之前，MSVC 会在实例化时再查一遍依赖基类，使 `type x;` 之类的代码也能通过编译；Clang 与 GCC 遵循标准报错。

!!! history "历史与演进"
    - **C++98–C++20**：本节是长达十余段的场景清单，分别描述命名空间作用域、类定义、成员函数定义、友元、mem-initializer、静态数据成员定义等处的查找顺序。
    - **C++23**：P1787R6 把它压缩为现在的 6 段：活跃 using 指令、无限定搜索、无限定查找、无限定名字的定义，以及两条特例（转换类型标识 ¶5、友元声明符 ¶6）。各场景由第 6.4 节的作用域规则推出，尤其是 [[basic.scope.class]]、[[basic.scope.namespace]] 中"*declarator-id* 之后的部分也属于该作用域"的规定。

## 陷阱

!!! pitfall "以为 using namespace 能覆盖外层同名"
    `namespace B { long i; void f() { using namespace A; i; } }` 中的 `i` 仍是 `B::i`。using 指令引入的名字位于指令与目标命名空间的公共外围命名空间那一层，往往比想象的更靠外。

!!! pitfall "头文件里的 using namespace"
    在全局作用域写 `using namespace std;`，std 的名字就在全局这一层参与搜索。日后标准库若加入一个与你的全局函数同名的函数（例如 `std::size`、`std::data`、`std::byte`），原本无二义的代码可能变成二义，或者改为调用别的函数。

!!! pitfall "类外定义的返回类型"
    返回类型位于 *declarator-id* 之前，不在类作用域中。要么写 `X::T X::f()`，要么用尾置返回类型 `auto X::f() -> T`。

## 思考题

!!! question "思考题 1"
    ```cpp
    namespace A { int n = 1; }
    namespace B { using namespace A; }
    namespace C {
        int n = 2;
        namespace D {
            using namespace B;
            int get() { return n; }
        }
    }
    ```
    `C::D::get()` 返回几？

<details markdown="1">
<summary>答案</summary>

返回 2。D 中的指令提名 B，根据 ¶1 的传递性，B 中提名 A 的指令在 D 中也活跃。但哪个作用域包含 A？只有全局作用域。沿链搜索：get 的块、参数作用域 → D（A、B 都不被 D 包含）→ C，在 C 找到 `C::n` 后停止。`A::n` 要到全局层才会并入。
</details>

!!! question "思考题 2"
    为什么 ¶5 要求转换类型标识里的名字先按 *conversion-function-id* 的方式查找，¶6 要求友元声明符里的名字先在 S 中搜索？二者的共同动机是什么？

<details markdown="1">
<summary>答案</summary>

两者的动机相同：这个名字的含义应当由它所指的那个声明的语境决定，而不是由使用处的语境决定。`x.operator T()` 指的是 x 的类中的转换函数，其 `T` 通常是那个类的成员；`friend void A::f(F)` 指的是 A 中已有的 `f`，其参数 `F` 应按 A 中的含义理解。不这样规定，就很难甚至无法在类外指名这些声明。
</details>

## 小结

| 情形 | 搜索顺序（由内到外） |
|---|---|
| 块中 | 当前块 → 外层块 → 函数参数作用域 → （成员函数：类及其非依赖基类 → 模板参数）→ 外围命名空间 → … → 全局 |
| using 指令 | 被提名命名空间在同时包含指令与它的最内层作用域那一层并入；具有传递性 |
| 类外定义 | *declarator-id* 之后属于类/命名空间作用域；之前（返回类型）不属于 |
| 完整类上下文 | 能看到整个类的成员 |
| 模板参数 | 在与模板关联的最外层作用域之后考虑；类成员与非依赖基类成员优先 |
| 转换类型标识 | 先在转换函数所属类中找类型 |
| 带限定名的友元声明符 | 声明符中 *declarator-id* 之后的名字先在 S 中找 |
| 隐藏 | 找到即停的副产品；内层一个函数隐藏外层全部重载 |
