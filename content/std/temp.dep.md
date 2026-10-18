---
title: 待决名
summary: 什么是"依赖的"：依赖调用与依赖名、当前实例化与依赖基类、依赖的限定名与依赖类型、类型依赖与值依赖表达式，以及 C++26 反射带来的依赖拼接说明符与依赖命名空间。这些定义决定了模板里每个名字是在定义处还是在实例化处查找。
status: done
covers: temp.dep.general, temp.dep.type, temp.dep.expr, temp.dep.constexpr, temp.dep.splice, temp.dep.namespace, temp.dep.temp
papers: P1787R6, P2996R13
related: temp.res, temp.local, temp.dep.res, temp.point, temp.dep.candidate, expr.prim.id, basic.lookup.qual, class.member.lookup, stmt.if, topics/two-phase-lookup
tags: 模板, 待决名, 当前实例化, 类型依赖, 值依赖, 两阶段查找
updated: 2026-10-17
---

[[temp.res]] 说"依赖名对每个特化在替换后查找、非依赖名在定义处查找一次"。本节 [[temp.dep]] 回答前一句话里那个词的精确含义：**什么是依赖的**（dependent）。

模板定义中几乎每一种结构都可以问"它依赖于模板形参吗"：

| 被问的东西 | 定义在 | 依赖会导致什么 |
|---|---|---|
| 函数调用 | 依赖调用，[[temp.dep.general#2]] | 被调函数名推迟查找，实例化时追加 ADL |
| 限定名 | [[temp.dep.type#5]] | 推迟到实例化查找；定义时需要 `typename`/`template` |
| 类型 | [[temp.dep.type#10]] | 不能在定义处做依赖类型相关的语义检查 |
| 表达式的类型 | 类型依赖，[[temp.dep.expr]] | 重载决议、成员查找推迟 |
| 表达式的值 | 值依赖，[[temp.dep.constexpr]] | 常量求值推迟（数组界、模板实参、`if constexpr`……） |
| 拼接说明符、命名空间别名 {{c++26}} | [[temp.dep.splice]]、[[temp.dep.namespace]] | 反射实体推迟确定 |
| 模板实参 | [[temp.dep.temp]] | 模板特化本身是依赖类型 |

这些定义是**相互递归**的：依赖类型可由值依赖的数组界构成，类型依赖表达式由依赖类型的声明产生，值依赖又以类型依赖为前提之一……本页按标准的顺序逐个梳理。贯穿始终的核心概念是**当前实例化**（current instantiation）——它是 C++ 让"类模板内部引用自己的成员"仍然可以在定义处检查的关键。

## 概述：依赖调用与依赖名（[temp.dep.general]）

### 依赖的含义（¶1）

¶1 模板里有些结构的语义在不同实例化之间可能不同，这样的结构**依赖于**模板形参。特别地，类型和表达式可能依赖于模板形参的类型和/或值，这决定了某些名字的查找语境。表达式可以是：

- [[g:type-dependent|**类型依赖的**]]（type-dependent）：它的类型可能依赖于模板形参；
- [[g:value-dependent|**值依赖的**]]（value-dependent）：它作为常量表达式求值时的值可能依赖于模板形参。

注意"可能"：判定是**语法上的、保守的**。`sizeof(T) * 0` 对任何 `T` 都是 `0`，但它照样是值依赖的。编译器不做"其实不依赖"的推理，这样规则才可判定、各实现才一致。

### 依赖调用（¶2）

¶2 [[g:dependent-call|**依赖调用**]]（dependent call）是形如 *postfix-expression* `(` *expression-list*ₒₚₜ `)` 的表达式（也可以是运算符的非成员候选所形成的调用，[[over.match.oper]]），其中 *postfix-expression* 是一个 *unqualified-id*，并且：

- ¶2.1 *expression-list* 中有包展开（[[temp.variadic]]），或
- ¶2.2 *expression-list* 中有类型依赖的表达式或 *braced-init-list*，或
- ¶2.3 *unqualified-id* 是一个 *template-id*，其中有依赖于模板形参的模板实参。

然后，*unqualified-id* 的**组成名字**（component name）是依赖的，当：

- ¶2.4 它是 *conversion-function-id*，且 *conversion-type-id* 是依赖的；
- ¶2.5 它是 `operator=`，且当前类是模板化实体；
- ¶2.6 *unqualified-id* 是一次依赖调用的 *postfix-expression*。

注 1：这样的名字只在模板实例化点（[[temp.point]]）查找，同时考虑模板定义的语境和实例化点的语境（[[temp.dep.candidate]]）。

几个要点：

- **只有无限定名**才谈得上依赖调用。`N::f(t)` 是限定名，按限定名的规则（[[temp.dep.type#5]]）判定；`(f)(t)` 不是 *unqualified-id*。这与 ADL 的触发条件（[[basic.lookup.argdep#1]]）完全对应——依赖调用的意义正在于"实例化时追加 ADL"。
- ¶2.3 让 `get<I>(t)` 这类调用在 `I` 是模板形参时也算依赖调用，即使 `t` 本身不是类型依赖的。
- ¶2.5 为什么 `operator=` 特殊？脚注说：类模板的每个实例化都声明了一组不同的赋值运算符（隐式声明的拷贝/移动赋值的形参类型是 `const X<T>&`），在定义处它们根本还不存在，所以必须推迟。

```cpp run ok
struct B { B& operator=(int) { return *this; } };
template<class T> struct D : B {
    void f() { operator=(1); }   // 依赖名（¶2.5）：定义处不查找
};
// 若实例化 D<int>::f，查找到 D<int> 隐式声明的拷贝/移动赋值，
// 它们隐藏了 B::operator=(int)，调用失败。
int main() { }
```

同样的代码写成非模板的 `struct D : B`，编译器立刻报错（`D` 的隐式赋值运算符隐藏了基类的）。在模板里错误被推迟到实例化——这本身就说明了 `operator=` 是依赖的。

### 例 1（¶3）

```cpp
template<class T> struct X : B<T> {
    typename T::A* pa;
    void f(B<T>* pb) {
        static int i = B<T>::i;
        pb->j++;
    }
};
```

基类名 `B<T>`、类型名 `T::A`、名字 `B<T>::i` 和 `pb->j` 都显式地依赖于模板形参。

## 依赖类型（[temp.dep.type]）

### 当前实例化（¶1–¶2）

假如类模板内部一切涉及 `X<T>` 的东西都算"依赖的"，那么类模板里调用自己的成员函数、使用自己的成员类型都得写 `typename`/`this->`，而且错误都只能等到实例化。**当前实例化**的概念让编译器知道：`X<T>` 在 `X` 的定义里指的就是"我自己"，它的成员在定义时就已经看得见，可以直接查找。

¶1 在下列语境中，一个名字或 *template-id* **指称**[[g:current-instantiation|**当前实例化**]]：

- ¶1.1 在类模板、类模板的嵌套类、类模板的成员、嵌套类的成员的定义中：类模板或嵌套类的**注入类名**；
- ¶1.2 在主类模板或其成员的定义中：类模板名后跟其模板头的实参列表（或等价的别名模板特化），即 `X<T>`；
- ¶1.3 在类模板嵌套类的定义中：作为当前实例化的成员被引用的嵌套类名（如 `A<T>::B`）；
- ¶1.4 在部分特化或其成员的定义中：类模板名后跟与该部分特化等价的实参列表；
- ¶1.5 在模板化函数的定义中：局部类的名字（[[class.local]]）。

¶2 与模板形参**等价**的模板实参可以代替该形参：对类型形参，指同一类型的实参等价；对常量形参，一个**标识符**，它命名的变量与该形参等价。变量与模板形参等价，当 ¶2.1 类型相同（忽略 cv）且 ¶2.2 初始化器是单个标识符，命名该模板形参，或递归地命名这样的变量。注 1：给变量名加括号就破坏了等价性。

```cpp run ok
template <class T> class A {
    A* p1;                        // 当前实例化
    A<T>* p2;                     // 当前实例化
    A<T*>* p3;                    // 不是当前实例化
    ::A<T>* p4;                   // 当前实例化（¶1.2：模板名 + 模板头实参）
    class B {
        B* p1;                    // 当前实例化（嵌套类 B）
        A<T>::B* p2;              // 当前实例化（¶1.3），无需 typename
        typename A<T*>::B* p3;    // 不是当前实例化，须 typename
    };
};

template <class T> class A<T*> {
    A<T*>* p1;                    // 当前实例化（¶1.4）
    A<T>* p2;                     // 不是当前实例化
};

template <class T1, class T2, int I> struct B {
    B<T1, T2, I>* b1;             // 当前实例化
    B<T2, T1, I>* b2;             // 不是
    typedef T1 my_T1;
    static const int my_I = I;
    static const int my_I2 = I+0;
    static const int my_I3 = my_I;
    static const long my_I4 = I;
    static const int my_I5 = (I);
    B<my_T1, T2, my_I>* b3;       // 当前实例化：my_T1 即 T1，my_I 的初始化器是标识符 I
    B<my_T1, T2, my_I2>* b4;      // 不是：I+0 不是单个标识符
    B<my_T1, T2, my_I3>* b5;      // 当前实例化：递归等价
    B<my_T1, T2, my_I4>* b6;      // 不是：类型 long ≠ int
    B<my_T1, T2, my_I5>* b7;      // 不是：带括号
};
int main() { }
```

为什么 `I+0` 不行？因为要判断等价就得做常量求值和代数推理，规则选择了**纯语法**的判定：只认"直接转述"。这样每个编译器得出的结论都一样。

!!! impl "Clang 对“等价变量”的支持不完整"
    上例在 Clang 23 下能编译，但那只是因为成员声明本身就是仅类型语境。实测在成员函数体内写 `A<k>::type x = 0;`（`k` 是与形参 `N` 等价的变量），Clang 并不把 `A<k>` 当作当前实例化，仍然要求 `typename`；`A<k>::nonexistent()` 也不会在定义处被诊断。直接用模板形参写的 `A<T>::Nested` 则没有问题。

"是否当前实例化"的实际影响：`A<T>::B* p2` 不需要 `typename`，因为 `A<T>` 是当前实例化，`B` 在定义时就能被找到、知道它是类型；`A<T*>::B` 则可能被某个 `A<U*>` 的部分特化改写成完全不同的东西，只能当依赖名处理。

```cpp error
template<class T> struct A2 {
    struct Nested { int v; };
    void h() {
        A2<T>::Nested n{};        // OK：当前实例化的成员
        A2<T*>::Nested m{};       // error: 不是当前实例化，须写 typename
    }
};
```

### 依赖基类（¶3）

¶3 [[g:dependent-base-class|**依赖基类**]]（dependent base class）是一个依赖类型、且**不是**当前实例化的基类。

注 2：基类可能就是当前实例化——嵌套类把外围类当作基类的时候：

```cpp run ok
template<class T> struct A {
    typedef int M;
    struct B {
        typedef void M;
        struct C;
    };
};

template<class T> struct A<T>::B::C : A<T> {
    M m;                          // OK：A<T>::M（int）。A<T> 是当前实例化，不是依赖基类
};
A<int>::B::C c;
int main() { }
```

依赖基类之所以重要，是因为它在**定义时不被搜索**：[[class.member.lookup#4]] 只合并"直接**非依赖**基类"的查找集。原因很简单——`Base<T>` 可以被显式特化成任何样子，定义时看到的主模板成员不能代表实例化时的真实成员。这就是"依赖基类中的名字必须用 `this->` 或限定名访问"的根源，详见 [[temp.dep.res]]。

### 当前实例化的成员（¶4）

¶4 一个限定或无限定名字是**当前实例化的成员**（member of the current instantiation），当：

- ¶4.1 如果它是限定名，其查找上下文是当前实例化；并且
- ¶4.2 对它的查找找到了某个"是当前实例化的类"的任何成员。

```cpp run ok
template <class T> class A {
    static const int i = 5;
    int n1[i];                    // i：当前实例化的成员
    int n2[A::i];                 // A::i：当前实例化的成员
    int n3[A<T>::i];              // A<T>::i：当前实例化的成员
    int f();
};

template <class T> int A<T>::f() {
    return i;                     // 当前实例化的成员
}
int main() { }
```

进一步，如果名字是当前实例化的成员，并且查找时至少指向当前实例化中的一个成员**声明**（包括终端名依赖的 *using-declarator*），它就命名一个**当前实例化的依赖成员**（dependent member of the current instantiation）。区别在于：通过非依赖基类找到的成员是"当前实例化的成员"，但不是"依赖成员"；只有在模板自己的定义中声明的才是依赖成员。依赖成员在 [[temp.dep.expr]]、[[temp.dep.constexpr]] 中用于判定类型/值依赖（例如 `static const int m;` 在类外定义的静态成员）。

### 依赖的限定名（¶5）

¶5 限定名（[[basic.lookup.qual]]）是**依赖的**，当：

- ¶5.1 它是 *conversion-function-id*，且 *conversion-type-id* 是依赖的；
- ¶5.2 其查找上下文是依赖的，且**不是**当前实例化；
- ¶5.3 其查找上下文是当前实例化，且它是 `operator=`；
- ¶5.4 其查找上下文是当前实例化，当前实例化**至少有一个依赖基类**，并且限定名查找**什么都没找到**。

¶5.2 是主体：`T::x`、`Base<T>::x`、`t.x`（`t` 的类型依赖）都是依赖的。¶5.4 是精巧的折衷：查找上下文是当前实例化时，先在定义处查；找到了就是普通名字（可以提前检查）；没找到又有依赖基类——它可能来自依赖基类，于是推迟；没找到且没有依赖基类——它不可能存在，可以在定义处报错。

```cpp error
template<class T> struct S : T {
    void f() { S::nothing(); }   // OK（暂时）：有依赖基类 T，查找无果 → 依赖名（¶5.4）
};
template<class T> struct S2 {
    void f() { S2::nothing(); }  // error: 没有依赖基类，查找无果 → 非依赖，定义处即可诊断
};
```

同一机制也适用于成员访问：`this->m` 中 `m` 是成员限定名（[[basic.lookup.qual.general#2]]），其查找上下文是 `*this` 的类型，即当前实例化。所以 `this->undeclared()` 在没有依赖基类的类模板里同样可以在定义处报错——Clang 就是这样做的。

例 4 演示 ¶5.2 的一个微妙之处：

```cpp error
struct A {
    using B = int;
    A f();
};
struct C : A {};
template<class T>
void g(T t) {
    decltype(t.A::f())::B i;      // error: 需要 typename 才能把 B 解释为类型
}
template void g(C);               // ……即使在这里 A 就是 ::A
```

`t.A::f()` 中 `A` 是成员限定名，查找上下文是 `t` 的类型 `T`——依赖的。虽然实际上 `A` 一定会在外层找到 `::A`，但 `decltype(...)` 是类型依赖表达式的 decltype，是依赖类型（¶10.13），`B` 的查找上下文依赖，按 ¶5.2 `B` 是依赖名；块作用域又不是仅类型语境，必须写 `typename`。

### 实例化时的二次查找（¶6）

¶6 如果某个特化被实例化，它用**限定名**引用了当前实例化的成员，这个名字会在**模板实例化语境中**再查一次。如果结果与定义语境中的结果不同，**名字查找是二义的**。

```cpp run ok
struct A { int m; };
struct B { int m; };

template<typename T>
struct C : A, T {
    int f() { return this->m; }   // 定义语境中找到 A::m
    int g() { return m; }         // 定义语境中找到 A::m
};

template int C<B>::g();           // OK：无限定名 m 不会在定义语境中被转换为成员访问
// template int C<B>::f();        // error: 实例化时找到 A::m 和 B::m，二义
int main() { }
```

为什么 `this->m` 和 `m` 不一样？`this->m` 是限定名（成员限定名），查找上下文是当前实例化，定义时找到 `A::m`（非依赖基类），所以它不是依赖名；但标准要求实例化时重新查一次，这时依赖基类 `T = B` 也加入了，出现 `B::m`，与定义时结果不同 → 二义。无限定的 `m` 在定义时就绑定到 `A::m`：[[expr.prim.id.general#2]] 把 `m` 变换为 `(*this).m` 的步骤"不在模板定义语境中发生"，所以它不被视为对当前实例化成员的限定引用，不再二次查找。

这条规则保护的是"定义时看到的含义 = 实例化时的含义"：对限定名，实例化时的视野更大（加入了依赖基类），若视野扩大改变了结果，宁可报错也不默默换掉。

### 依赖的初始化器与占位类型（¶7–¶9）

¶7 初始化器是依赖的，当它的某个**成分表达式**（constituent expression，[[intro.execution]]）是类型依赖的。占位类型（`auto`、`decltype(auto)`，[[dcl.spec.auto.general]]）是依赖的，当它指定从依赖初始化器推导出的类型。

¶8 推导类类型的占位符（CTAD，[[dcl.type.class.deduct]]）是依赖的，当：¶8.1 有依赖的初始化器；¶8.2 它指称类型模板模板形参；¶8.3 它指称当前实例化成员的别名模板，且其 *defining-type-id* 在 CTAD 与替换之后是依赖的。

```cpp run ok
template<class T, class V>
struct S { S(T) { } };

template<class U>
struct A {
    template<class T> using X = S<T, U>;
    template<class T> using Y = S<T, int>;
    void f() {
        delete new X(1);          // 依赖：X 推导后是 S<int, U>，依赖于 U
        delete new Y(1);          // 不依赖：Y 推导后是 S<int, int>
    }
};
template struct A<char>;
int main() { }
```

`X(1)` 的实参 `1` 并不依赖，但推导结果 `S<int, U>` 依赖于外层的 `U`（¶8.3）；而 `Y(1)` 在定义处就能完整推导为 `S<int, int>`。

### 依赖类型的清单（¶10–¶11）

¶10 类型是[[g:dependent-type|依赖的]]，若它是：

| 条目 | 内容 | 例子 |
|---|---|---|
| ¶10.1 | 模板形参 | `T` |
| ¶10.2 | 由依赖的（限定）名指称 | `typename T::type` |
| ¶10.3 | 当前实例化的直接成员的嵌套类或枚举 | `A<T>` 中的 `struct Nested` |
| ¶10.4 | cv 限定类型，去掉 cv 后依赖 | `const T` |
| ¶10.5 | 由依赖类型构造的复合类型 | `T*`、`T&`、`void(T)`、`int T::*` |
| ¶10.6 | 元素类型依赖或界值依赖的数组 | `int[N]`、`T[3]` |
| ¶10.7 | 形参中含函数形参包的函数类型 | `void(Ts...)` |
| ¶10.8 | 异常说明值依赖的函数类型 | `void() noexcept(B)` |
| ¶10.9 | 依赖的占位类型所指的类型 | `auto x = t;` 中 `x` 的类型 |
| ¶10.10 | 依赖的推导类类型占位符所指的类型 | 上面的 `X(1)` |
| ¶10.11 | 模板名是模板形参、或有依赖模板实参的 *simple-template-id* | `TT<int>`、`vector<T>`、无实参列表的注入类名 |
| ¶10.12 | *pack-index-specifier* | `Ts...[0]` |
| ¶10.13 | `decltype(e)`，`e` 类型依赖 | `decltype(t + 1)` |
| ¶10.14 | 拼接说明符依赖的 *splice-type-specifier* {{c++26}} | `typename [:R:]` |

几个值得注意的条目：

- **¶10.3**：当前实例化的嵌套类是依赖类型，尽管它的名字不是依赖名（不需要 `typename`）。这两件事不矛盾——"名字依赖"决定何时查找，"类型依赖"决定类型是否随实参变化。`A<int>::Nested` 和 `A<char>::Nested` 是不同的类型。
- **¶10.11 + 脚注**：注入类名不带实参列表时，就是 `X<T>`，所以是依赖类型；当前实例化本身是依赖类型。
- **¶10.12**：*pack-index-specifier* 一律是依赖的（C++26 包索引）。

¶11（注 3）：typedef 不引入新类型，所以指向当前实例化成员 typedef 的名字只有在它所指的类型依赖时才是依赖的：`template<class T> struct S { using I = int; I x; };` 中 `I` 不依赖。

!!! history "“未知特化的成员”去哪了？"
    C++11 到 C++20 的 [temp.dep.type] 还定义了一个术语**未知特化的成员**（member of an unknown specialization），用来描述 `T::x`、`Base<T>::x` 以及在当前实例化中找不到、但可能来自依赖基类的名字。C++23 的 [[P1787R6]] 用"依赖的限定名"（¶5）和查找上下文的概念统一重写了这部分规则，这个术语被删除了。读旧资料（包括很多书和 Stack Overflow 回答）时会遇到它，可以大致把它对应到今天 ¶5.2 与 ¶5.4 描述的那些名字。

## 类型依赖的表达式（[temp.dep.expr]）

### 一般规则与 this（¶1–¶2）

¶1 除下面另有规定外，若表达式的任何子表达式是类型依赖的，则该表达式是类型依赖的。

¶2 `this` 是类型依赖的，当当前类（[[expr.prim.this]]）是依赖的。在类模板的成员函数中，`this` 的类型是 `X<T>*`——依赖类型，所以 `this->anything` 都是类型依赖的成员访问。这正是 `this->` 能把名字"变成依赖的"的原因（但如上所述，若查找上下文是当前实例化，查找仍会在定义处先进行）。

### id-expression（¶3）

¶3 *id-expression* 是类型依赖的，若它是依赖的 *template-id*（非 concept-id），或其终端名：

| 条目 | 名字查找关联到…… |
|---|---|
| ¶3.1 | 一个或多个以依赖类型声明的声明（最常见：`T t;` 中的 `t`） |
| ¶3.2 | 类型含占位类型的常量模板形参（`template<auto V>` 中的 `V`） |
| ¶3.3 | 类型含占位类型、初始化器类型依赖的变量（`auto x = t;`） |
| ¶3.4 | 当前实例化中返回类型含占位类型的成员函数 |
| ¶3.5 | 初始化器类型依赖的结构化绑定 |
| ¶3.6 | **结构化绑定包** {{c++26}} |
| ¶3.7 | 带依赖类型显式对象形参的 lambda 中以复制捕获的实体 |
| ¶3.8 | `__func__`，若任一外围函数是模板、类模板成员或泛型 lambda |
| ¶3.9 | 返回类型依赖的函数的结果绑定（契约后置条件，[[dcl.contract.res]]）{{c++26}} |
| ¶3.10 | 指定依赖类型的 *conversion-function-id* |
| ¶3.11 | 展开语句 *for-range-declaration* 引入、类型含占位类型的名字（非迭代展开，或展开初始化器类型依赖）{{c++26}} |
| ¶3.12 | 依赖的名字 |

此外，若它命名当前实例化的一个依赖成员，且是"未知界数组"类型的静态数据成员（[[temp.static]]），也是类型依赖的——类外定义可能补上界。

¶3.8 `__func__` 为什么类型依赖？它的类型是 `const char[N]`，`N` 取决于函数名字符串的长度；而字符串内容由实现定义，实现可以让不同特化的 `__func__` 不同（例如带上模板实参），所以长度——进而类型——在实例化前未知。

¶3.6 的例 1（C++26 结构化绑定包）：

```cpp run ok
#include <cstdio>
struct C { };
void g(...) { std::puts("#1 g(...)"); }

template <typename T>
void f() {
    C arr[1];
    auto [...e] = arr;      // e 是结构化绑定包
    g(e...);                // 包展开：依赖调用，实例化时 ADL 找到 #2
}

void g(C) { std::puts("#2 g(C)"); }

int main() { f<int>(); }    // 输出 #2 g(C)
```

`f` 里没有任何东西依赖 `T`，可 `e` 仍被规定为类型依赖：结构化绑定包的元素个数要到实例化时才确定（标准选择不在定义处展开它）。于是 `g(e...)` 是依赖调用（¶2.1 包展开），`g` 的查找推迟到实例化，ADL 在实例化语境中找到了后声明的 `g(C)`。

### 只看类型部分的形式

¶3 后半：下列形式只有当所写的 *type-id* / *simple-type-specifier* / *typename-specifier* / *new-type-id* 依赖时才是类型依赖的，**即使子表达式类型依赖**：

- 函数式转型 `T(args)`、`T{args}`；
- `new T(...)`；
- `dynamic_cast`/`static_cast`/`const_cast`/`reinterpret_cast<type-id>(e)`；
- C 风格转型 `(type)e`。

道理很直接：这些表达式的类型就是写出来的那个类型（或其指针），与操作数无关。`static_cast<int>(t)` 不是类型依赖的（类型就是 `int`），但它是值依赖的（见下文）。

### 永不类型依赖的形式（¶4）

¶4 下列形式**永远不是**类型依赖的，因为类型不可能依赖：字面量、`sizeof`、`sizeof...`、`alignof`、`typeid`、`delete`、`throw`、`noexcept(e)`、*requires-expression*、{{c++26}} *reflect-expression*（`^^x`，类型总是 `std::meta::info`）。

```cpp run ok
#include <type_traits>
template<class T> void g(T t) {
    auto n = sizeof(t);           // sizeof 永不类型依赖：n 的类型是 size_t
    static_assert(std::is_same_v<decltype(n), decltype(sizeof 0)>);   // 定义处就能确定
    int i = 0;
    auto a = i;                   // 非依赖
    auto b = t;                   // 类型依赖（¶3.3）
    (void)a; (void)b;
}
template void g(int);
int main() { }
```

类型依赖的结构推迟检查，非依赖的立即检查：

```cpp error
template<class T> void g(T t) {
    int i = 0;
    auto a = i;
    a.foo();            // error: a 不依赖，类型是 int，定义处即可诊断
    auto b = t;
    b.foo();            // OK（暂时）：类型依赖，推迟到实例化
}
```

### 成员访问、花括号列表、折叠与包索引（¶5–¶9）

¶5 类成员访问表达式是类型依赖的，当：¶5.1 其 *id-expression* 的终端名是依赖的；¶5.2 其 *splice-expression* 类型依赖；或 ¶5.3 表达式指向当前实例化的成员，且该成员的类型是依赖的。

注 2：`x.y` 的类型通常就是 `x` 的类中成员 `y` 的类型；但如果 `x` 的类型依赖且**不是**当前实例化，`y` 的类型总是依赖的。反之，对当前实例化，`this->n` 中如果 `n` 声明为 `int n;`，`this->n` **不是**类型依赖的——定义时就知道它是 `int`。

¶6 *braced-init-list* 中任一元素类型依赖或是包展开，则它类型依赖。¶7 *fold-expression* 总是类型依赖的（折叠结果的类型取决于展开后的运算）。¶8 *pack-index-expression* 在其 *id-expression* 类型依赖时类型依赖。¶9 {{c++26}} *splice-expression* 在其拼接说明符依赖时类型依赖。

## 值依赖的表达式（[temp.dep.constexpr]）

值依赖只在**需要常量表达式**的语境中有意义（¶1：除另有规定外，此类语境中的表达式在任一子表达式值依赖时值依赖）：数组界、模板实参、`static_assert`、`if constexpr` 的条件、`noexcept(...)`、位域宽度、`alignas`……

### id-expression（¶2）

¶2 *id-expression* 是值依赖的，若：

- ¶2.1 它是 concept-id，且概念名依赖或任一实参依赖；
- ¶2.2 它是类型依赖的（类型都不确定，值当然也不确定）；
- ¶2.3 它是常量模板形参的名字；
- ¶2.4 它是展开语句 *for-range-declaration* 引入的名字 {{c++26}}；
- ¶2.5 它命名一个当前实例化的依赖成员的静态数据成员，且**没有在 *member-declarator* 中初始化**；
- ¶2.6 它命名一个当前实例化的依赖成员的静态成员函数；
- ¶2.7 它命名一个潜在常量变量（[[expr.const.init]]），其初始化器是值依赖的。

¶2.5 的意思是：类内初始化的 `static const int n = 3;` 在定义时就知道值；但类外初始化的静态成员，其定义可能对不同特化不同（可以显式特化静态成员），所以是值依赖的：

```cpp run ok
template<class T> struct S {
    static const int n = 3;       // 类内初始化：不值依赖
    static const int m;           // 类外初始化：值依赖（¶2.5）
    void f() {
        int a[n];                 // 定义时 n == 3
        int b[m];                 // 推迟到实例化
        (void)a; (void)b;
    }
};
template<class T> const int S<T>::m = 4;
template struct S<int>;
int main() { }
```

`sizeof`、`typeid`、`alignof` 的值依赖规则：操作数表达式**类型**依赖、或操作数类型依赖时，它们**值**依赖。所以 `sizeof(t)` 不类型依赖但值依赖——这是"类型确定、值不确定"的经典例子。

### 转型与函数式转型（¶3）

¶3 函数式转型、具名转型和 C 风格转型，在所写类型依赖、或操作数值依赖时值依赖。`static_cast<int>(N)` 中 `N` 是常量模板形参，因此值依赖但不类型依赖。

### sizeof...、折叠、noexcept、取址（¶4–¶6）

- ¶4 `sizeof...(pack)` 和 *fold-expression* 总是值依赖的。
- ¶5 *noexcept-expression* 在其操作数**涉及**模板形参时值依赖。注意措辞是"涉及"（involves），比"类型依赖"或"值依赖"都宽：`noexcept(T())` 中 `T()` 的类型是 `T`（类型依赖），但即使操作数不类型依赖，只要涉及模板形参（比如调用的函数的 noexcept 性质可能随特化变化），整个 `noexcept(...)` 就是值依赖的。
- ¶6 `&qualified-id` 中 *qualified-id* 命名当前实例化的依赖成员时值依赖；`&cast-expression` 当操作数作为核心常量表达式求值成功、且结果指向一个模板化的静态/线程存储期对象或成员函数时，也是值依赖的。后半句覆盖了 `&S<T>::sm` 这种指针常量——每个特化的静态成员地址不同。

### 反射与拼接（¶7–¶8）{{c++26}}

¶7 *reflect-expression* 是值依赖的，若：¶7.1 形如 `^^name`，且查找到的声明栖身于对应模板化实体的作用域，或名字是依赖的限定名、依赖的命名空间名、模板形参名；¶7.2 形如 `^^type-id` 且类型依赖；¶7.3 形如 `^^id-expression` 且其值依赖。

直觉：`^^x` 的**类型**永远是 `std::meta::info`（所以从不类型依赖，¶4），但它**反射的是哪个实体**可能取决于模板实参，这就是值依赖。特别地，¶7.1 的第一种情形意味着在模板里反射一个模板内部声明的局部实体（每个特化各有一份）也是值依赖的。

¶8 *splice-expression* 在其拼接说明符依赖时值依赖。

## 依赖的拼接说明符（[temp.dep.splice]）{{c++26}}

¶1 *splice-specifier* `[: e :]` 是依赖的，当其转换后的常量表达式 `e` 值依赖。*splice-specialization-specifier* `[: e :]<args>` 在其拼接说明符依赖、或任一模板实参依赖时依赖。*splice-scope-specifier*（拼接用作嵌套名说明符）在其拼接说明符或拼接特化说明符依赖时依赖。

```cpp
template<auto T, auto NS>
void fn() {
    using a = [:T:]<1>;                                   // [:T:] 依赖，[:T:]<1> 也依赖
    static_assert([:NS:]::template TCls<1>::v == a::v);   // [:NS:] 依赖：TCls 前需要 template
}

namespace N {
    template <auto V> struct TCls { static constexpr int v = V; };
}

int main() {
    fn<^^N::TCls, ^^N>();
}
```

依赖的拼接说明符的处境与依赖的嵌套名说明符完全相同：定义时不知道它指什么，所以后面的成员名需要 `template`/`typename` 消歧义（`[:NS:]::template TCls<1>`），除非处于仅类型语境（`using a = [:T:]<1>;` 是 *defining-type-id*，[[temp.res#4]]）。

¶3 例 2 展示了一个后果：依赖的拼接让检查推迟到实例化——

```cpp
template<template<class> class X>
struct S {
    [:^^X:]<int, float> m;        // [:^^X:] 依赖（^^X 反射模板形参，值依赖）
};

template<class> struct V1 {};
template<class, class = int> struct V2 {};

S<V1> s1;                         // error: V1<int, float> 实参过多
S<V2> s2;                         // OK
```

如果直接写 `X<int, float>`，`X` 是只接受一个类型实参的模板模板形参，在定义处就会因实参过多而报错。通过 `[:^^X:]` 绕一圈，变成依赖的拼接，实参个数的检查推迟到实例化——此时 `X = V2` 有默认实参，完全合法。

!!! impl "未经本机验证"
    本节与下一节的反射例子来自草案，本机 Clang 23（Homebrew 版）尚不支持 `^^` 与 `[: :]`，因此未经编译验证。判定以草案为准。

## 依赖的命名空间（[temp.dep.namespace]）{{c++26}}

¶1 命名空间别名是依赖的，若它由 *namespace-alias-definition* 引入，且其 *qualified-namespace-specifier* 是依赖的限定名，或其 *splice-specifier* 依赖。*namespace-name* 命名依赖的命名空间别名时是依赖的。

```cpp
template<std::meta::info R>
int fn() {
    namespace Alias = [:R:];          // [:R:] 依赖 → Alias 依赖
    return typename Alias::T{};       // Alias 依赖：须 typename
}

namespace NS { using T = int; }

int a = fn<^^NS>();
```

在 C++26 之前，命名空间永远不可能依赖于模板形参——没有任何办法把命名空间当作模板实参传递。反射让 `std::meta::info` 可以表示命名空间，于是出现了"依赖的命名空间"，限定名规则（[[temp.dep.type#5]] ¶5.2"查找上下文依赖"）随之适用于它。

## 依赖的模板实参（[temp.dep.temp]）

- ¶1 类型模板实参在其指定的类型依赖时依赖。
- ¶2 常量模板实参在其类型依赖、或其常量表达式值依赖时依赖。
- ¶3 此外，若对应的常量模板形参是引用或指针类型，而模板实参指代或指向**当前实例化的成员**或依赖类型的成员，该实参也是依赖的。
- ¶4 包展开形式的模板实参是依赖的。
- ¶5 模板模板实参在它命名一个模板形参、或其终端名依赖时依赖。

¶3 的例子：

```cpp run ok
template<int* P> struct Tag { };
template<class T> struct W {
    static int sm;
    Tag<&sm> t;           // &sm 指向当前实例化的成员：依赖的模板实参（¶3）
};
template<class T> int W<T>::sm = 0;
W<int> w;
int main() { }
```

`&sm` 的类型是 `int*`（不依赖），在定义处它甚至算不上值依赖的"计算"，但 `W<int>::sm` 和 `W<char>::sm` 是不同的对象，`Tag<&sm>` 在不同特化中是不同的类型，所以必须视为依赖。

模板实参的依赖性通过 [[temp.dep.type#10]] ¶10.11 传递给 *simple-template-id*：只要有一个实参依赖，整个特化就是依赖类型。

## 实现视角

!!! impl "编译器如何表示“依赖”"
    - **Clang** 在 AST 节点上计算一组依赖位（`ExprDependence`/`TypeDependence`：Type、Value、Instantiation、UnexpandedPack、Error 等），直接对应本节的类型依赖、值依赖与"含未展开包"。依赖的类型用专门的节点表示（如 `DependentNameType` 表示 `typename T::x`、`TemplateTypeParmType` 表示 `T`、`InjectedClassNameType` 表示注入类名）。实例化时 `TreeTransform` 遍历这些节点做替换。
    - **当前实例化**是 Clang 能在定义处报"no member named ... in 'X<T>'"的依据：它在定义处对当前实例化做真实的成员查找，没有依赖基类时直接诊断。
    - **GCC** 有对应的 `type_dependent_expression_p`、`value_dependent_expression_p` 等谓词，概念上与标准术语一一对应。
    - 对 ¶6（实例化时二次查找限定名），上面的 `C<B>::f()` 例子 Clang 正确报出二义（"在多个基类中找到成员 m"）。

## 陷阱

!!! pitfall "“值依赖”不等于“类型依赖”"
    `sizeof(t)`、`static_cast<int>(N)`、`noexcept(T())` 都是值依赖但非类型依赖的。依赖它们的类型（如 `int[sizeof(t)]`）是依赖类型，但表达式本身的类型在定义时已知，可以参与定义时的重载决议。

!!! pitfall "当前实例化的嵌套类型是依赖类型，但名字不是依赖名"
    `A<T>::Nested` 不需要 `typename`（名字在定义时找得到），但 `A<T>::Nested` 是依赖类型（¶10.3）——不同特化中是不同的类。不要因为"不需要 typename"就以为它的含义与 `T` 无关。

!!! pitfall "this-> 不是万能的推迟按钮"
    `this->m` 的查找上下文是当前实例化：如果当前实例化没有依赖基类而 `m` 不存在，Clang/GCC 在定义处就报错；如果定义处在非依赖基类中找到了 `m`，实例化时还会再查一次（¶6），可能因依赖基类引入同名成员而二义。

## 思考题

!!! question "思考题 1"
    ```cpp
    template<int N> struct A {
        static constexpr int k = N;
        static constexpr int k2 = (N);
        A<k>* p;
        A<k2>* q;
    };
    ```
    `p`、`q` 的类型是当前实例化的指针吗？这有什么实际影响？

<details markdown="1">
<summary>答案</summary>

`k` 的类型与 `N` 相同（`int`，`constexpr` 带来的 const 被忽略），初始化器是单个标识符 `N`，所以 `k` 与 `N` 等价，`A<k>` 是当前实例化（¶2）。`k2` 的初始化器是带括号的 `(N)`，按注 1 破坏了等价，`A<k2>` 不是当前实例化——尽管在每个实例化中它和 `A<N>` 都是同一个类型。

实际影响：通过 `A<k>::` 访问成员时，它是当前实例化的成员，定义时就能查找，不需要 `typename`、拼写错误可以提前报错；通过 `A<k2>::` 访问的名字则是依赖名（¶5.2），类型成员需要 `typename`，错误推迟到实例化。

（实测 Clang 23 并未实现"等价变量"这一条：它对 `A<k>::type` 在函数体内同样要求 `typename`。这是编译器与标准的差异，见 ¶2 后的说明。）
</details>

!!! question "思考题 2"
    在类模板 `template<class T> struct S { int n; void f(); };` 的 `f` 中，表达式 `this->n` 是类型依赖的吗？`decltype(this->n)` 是依赖类型吗？

<details markdown="1">
<summary>答案</summary>

都不是。`this` 是类型依赖的（¶2），但成员访问表达式的类型依赖由 ¶5 单独规定：终端名 `n` 不是依赖的（查找上下文是当前实例化，在定义时找到了成员，¶5.2/¶5.4 都不满足），表达式指向当前实例化的成员 `n`，而 `n` 的类型 `int` 不依赖，所以 ¶5.1–¶5.3 都不成立，`this->n` 不是类型依赖的。于是 `decltype(this->n)` 也不是依赖类型（¶10.13 要求表达式类型依赖），就是 `int`。
</details>

!!! question "思考题 3"
    为什么 *fold-expression* 被无条件地规定为类型依赖，而不是"包元素类型依赖时才依赖"？

<details markdown="1">
<summary>答案</summary>

折叠表达式必然包含一个未展开的包，而包的长度只有在实例化时才知道。即使所有元素类型都已知（比如 `int...` 常量形参包），空包的折叠结果取决于运算符（`&&` 得 `true`、`,` 得 `void()`、其他运算符空包非良构），非空包的结果类型取决于运算符重载与展开出的表达式结构。定义时无法确定结果类型，所以标准直接规定它类型依赖（¶7），同理 `sizeof...` 和折叠表达式都是值依赖的（[temp.dep.constexpr] ¶4）。
</details>

## 小结

| 概念 | 定义处 | 一句话 |
|---|---|---|
| 依赖调用 | [temp.dep.general] ¶2 | 无限定名 + 类型依赖实参/包展开/依赖模板实参；实例化时追加 ADL |
| 当前实例化 | [temp.dep.type] ¶1–¶2 | 类模板内部的"我自己"：注入类名、`X<T>`、等价实参 |
| 依赖基类 | ¶3 | 依赖类型且非当前实例化；定义时不被搜索 |
| 当前实例化的（依赖）成员 | ¶4 | 定义时可查找的成员 |
| 依赖的限定名 | ¶5 | 查找上下文依赖且非当前实例化；或当前实例化 + 依赖基类 + 查无此名 |
| 实例化时二次查找 | ¶6 | 限定名引用当前实例化成员，两次结果不同 → 二义 |
| 依赖类型 | ¶10 | 14 种情形，含 C++26 的包索引与拼接类型 |
| 类型依赖 | [temp.dep.expr] | 子表达式传递；转型只看目标类型；sizeof 等永不 |
| 值依赖 | [temp.dep.constexpr] | 常量形参、类外初始化的静态成员、sizeof(依赖)、`sizeof...`、折叠、反射 |
| 依赖拼接/命名空间 | [temp.dep.splice]、[temp.dep.namespace] | C++26 反射带来的新依赖源 |
| 依赖模板实参 | [temp.dep.temp] | 依赖类型/值依赖/指向当前实例化成员/包展开/模板形参 |
