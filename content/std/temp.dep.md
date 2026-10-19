---
title: 待决名
summary: 模板里什么算依赖于模板形参：依赖调用、当前实例化与依赖基类、依赖的限定名和依赖类型、类型依赖与值依赖的表达式，以及 C++26 反射带来的依赖拼接和依赖命名空间。
status: done
covers: temp.dep.general, temp.dep.type, temp.dep.expr, temp.dep.constexpr, temp.dep.splice, temp.dep.namespace, temp.dep.temp
papers: P1787R6, P2996R13
related: temp.res, temp.local, temp.dep.res, temp.point, temp.dep.candidate, expr.prim.id, basic.lookup.qual, class.member.lookup, stmt.if, topics/two-phase-lookup
tags: 模板, 待决名, 当前实例化, 类型依赖, 值依赖, 两阶段查找
updated: 2026-10-19
---

!!! tldr
    - 一个结构是否依赖于模板形参，决定了它在定义处检查，还是推迟到每个特化再检查。判断是按语法保守进行的：`sizeof(T) * 0` 恒为 0，但仍算依赖。
    - 无限定名的调用，只要有实参的类型依赖于模板形参，就是依赖调用，实例化时会追加 ADL。
    - 在类模板内部，`X`、`X<T>` 指的是当前实例化。它的成员在定义处就能查到，不需要 `typename`；查不到又没有依赖基类时，定义处就能报错。
    - 依赖基类（依赖于模板形参、又不是当前实例化的基类）在定义处不被搜索，所以访问它的成员要写 `this->` 或限定名。
    - 类型依赖说的是表达式的类型可能变，值依赖说的是它的常量值可能变。`sizeof(t)` 的类型总是 `size_t`，但值依赖于 `T`。

## 依赖与否决定何时检查

```cpp error
template<class T> void g(T t) {
    int i = 0;
    auto a = i;
    a.foo();            // error: a 的类型是 int，定义处即可诊断
    auto b = t;
    b.foo();            // 暂时 OK: b 的类型依赖于 T，推迟到实例化
}
```

[[temp.res]] 规定，依赖名在每个特化里替换之后再查找，其余的名字在定义处查找一次。本节给出依赖一词的精确定义。模板里几乎每种结构都可以问它是否依赖：

| 对象 | 定义 | 依赖时会怎样 |
|---|---|---|
| 函数调用 | 依赖调用，[[temp.dep.general#2]] | 被调函数推迟查找，实例化时追加 ADL |
| 限定名 | [[temp.dep.type#5]] | 推迟到实例化查找；指类型或模板时要写 `typename` 或 `template` |
| 类型 | [[temp.dep.type#10]] | 涉及这个类型的语义检查推迟 |
| 表达式的类型 | 类型依赖，[[temp.dep.expr]] | 重载决议、成员查找推迟 |
| 表达式的值 | 值依赖，[[temp.dep.constexpr]] | 常量求值推迟（数组界、模板实参、`if constexpr` 等） |
| 拼接说明符、命名空间别名 {{c++26}} | [[temp.dep.splice]]、[[temp.dep.namespace]] | 反射得到的实体推迟确定 |
| 模板实参 | [[temp.dep.temp]] | 所在的模板特化是依赖类型 |

这些定义互相引用：依赖类型可以由值依赖的数组界构成，类型依赖的表达式来自用依赖类型声明的变量，值依赖又以类型依赖为条件之一。贯穿其中的是当前实例化的概念，有了它，类模板对自身成员的引用仍然可以在定义处检查。

## 依赖调用（[temp.dep.general]）

¶1 模板里有些结构的语义在不同实例化之间可能不同，这样的结构**依赖**（depend）于模板形参。表达式可以是：

- [[g:type-dependent|**类型依赖的**]]（type-dependent）：它的类型可能依赖于模板形参；
- [[g:value-dependent|**值依赖的**]]（value-dependent）：它作为常量表达式求值时的值可能依赖于模板形参。

判定按语法进行，而且偏保守。`sizeof(T) * 0` 对任何 `T` 都是 0，但它照样是值依赖的。编译器不去证明一个表达式其实不依赖，这样规则才可判定，各个实现的结论才一致。

¶2 [[g:dependent-call|**依赖调用**]]（dependent call）是形如 *postfix-expression* `(` *expression-list*ₒₚₜ `)` 的表达式，其中 *postfix-expression* 是一个无限定名，并且满足下列之一：

- ¶2.1 实参中有包展开（[[temp.variadic]]）；
- ¶2.2 实参中有类型依赖的表达式或花括号列表；
- ¶2.3 被调用的名字是带有依赖模板实参的 *template-id*，例如 `I` 是模板形参时的 `get<I>(t)`。

运算符表达式的非成员候选也按这种调用形式判断（[[over.match.oper]]）。只有无限定名才谈得上依赖调用：`N::f(t)` 按限定名的规则判断，`(f)(t)` 的被调用者不是无限定名。这正好对应 ADL 的触发条件（[[basic.lookup.argdep#1]]），因为依赖调用的意义就在于实例化时追加 ADL。

无限定名在下列情况下是依赖的：

- ¶2.4 它是转换函数名 `operator T`，且目标类型依赖；
- ¶2.5 它是 `operator=`，且当前类是模板化实体；
- ¶2.6 它是依赖调用中被调用的名字。

注 1 说明，这样的名字只在实例化点（[[temp.point]]）查找，同时考虑定义语境和实例化语境（[[temp.dep.candidate]]）。

`operator=` 特殊，是因为类模板的每个实例化都声明了一组不同的赋值运算符：隐式声明的拷贝赋值的形参类型是 `const X<T>&`，在定义处还不存在。

```cpp run ok
struct B { B& operator=(int) { return *this; } };
template<class T> struct D : B {
    void f() { operator=(1); }   // 依赖名（¶2.5）：定义处不查找
};
int main() { }
```

如果实例化 `D<int>::f`，查找会找到 `D<int>` 隐式声明的拷贝和移动赋值运算符，它们隐藏了 `B::operator=(int)`，调用失败。同样的代码写成非模板的 `struct D : B`，Clang 立刻报错；写在模板里，错误推迟到实例化，这说明 `operator=` 确实被当作依赖名。

¶3 例 1 列出了几个显而易见的依赖名：在 `template<class T> struct X : B<T>` 中，基类名 `B<T>`、类型名 `T::A`、名字 `B<T>::i` 和 `pb->j`（`pb` 的类型是 `B<T>*`）都依赖于模板形参。

## 当前实例化（[temp.dep.type]）

如果类模板内部凡是涉及 `X<T>` 的东西都算依赖，那么类模板使用自己的成员类型都要写 `typename`，调用自己的成员都要等到实例化才能检查。当前实例化的概念让编译器知道，`X` 的定义里的 `X<T>` 就是这个类自身，它的成员在定义处已经可见。

¶1 在下列情况下，一个名字或 *template-id* 指[[g:current-instantiation|**当前实例化**]]（current instantiation）：

- ¶1.1 在类模板、其嵌套类或它们的成员的定义中，类模板或嵌套类的注入类名（[[temp.local]]）；
- ¶1.2 在主模板或其成员的定义中，类模板名加上模板头的实参列表，即 `X<T>`（或等价的别名模板特化）；
- ¶1.3 在嵌套类的定义中，作为当前实例化的成员被引用的嵌套类名，如 `A<T>::B`；
- ¶1.4 在部分特化或其成员的定义中，类模板名加上与该部分特化等价的实参列表；
- ¶1.5 在模板化函数的定义中，局部类的名字（[[class.local]]）。

¶2 与模板形参等价的模板实参可以代替该形参。对类型形参，表示同一类型的实参与它等价。对常量形参，等价的实参必须是一个标识符，它命名的变量与该形参等价。变量与模板形参等价的条件是：¶2.1 类型相同（忽略 cv 限定）；¶2.2 初始化器是单个标识符，命名这个模板形参，或者递归地命名这样的变量。注 1 补充，给变量名加括号就破坏了等价性。

```cpp run ok
template <class T> class A {
    A* p1;                        // 当前实例化
    A<T>* p2;                     // 当前实例化
    A<T*>* p3;                    // 不是当前实例化
    ::A<T>* p4;                   // 当前实例化（¶1.2）
    class B {
        B* p1;                    // 当前实例化（嵌套类 B）
        A<T>::B* p2;              // 当前实例化（¶1.3）
        typename A<T*>::B* p3;    // 不是当前实例化
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
    B<my_T1, T2, my_I>* b3;       // 当前实例化
    B<my_T1, T2, my_I2>* b4;      // 不是：I+0 不是单个标识符
    B<my_T1, T2, my_I3>* b5;      // 当前实例化：递归等价
    B<my_T1, T2, my_I4>* b6;      // 不是：long 与 int 类型不同
    B<my_T1, T2, my_I5>* b7;      // 不是：带括号
};
int main() { }
```

`I+0` 不算等价，是因为判断它要做常量求值和代数推理。规则只认直接转述，纯按语法判断，每个编译器的结论都一样。

是否当前实例化，实际影响在于名字能否在定义处查到。`A<T>` 是当前实例化，`A<T>::B` 在定义处就能找到，知道它是类型，不需要 `typename`。`A<T*>::B` 则可能被某个 `A<U*>` 的部分特化改成完全不同的东西，只能当依赖名处理：

```cpp error
template<class T> struct A2 {
    struct Nested { int v; };
    void h() {
        A2<T>::Nested n{};        // OK: 当前实例化的成员
        A2<T*>::Nested m{};       // error: 不是当前实例化，须写 typename
    }
};
```

!!! impl "Clang 对等价变量的支持不完整"
    上面的大例子能在 Clang 23 下编译，只是因为成员声明本来就是仅类型语境。在成员函数体内写 `A<k>::type x = 0;`（`k` 是与形参 `N` 等价的变量），Clang 23 并不把 `A<k>` 当作当前实例化，仍然要求 `typename`；`A<k>::nonexistent()` 也不会在定义处报错。直接用模板形参写的 `A<N>::nonexistent()` 则会在定义处报错。

### 依赖基类（¶3）

¶3 [[g:dependent-base-class|**依赖基类**]]（dependent base class）是依赖类型、又不是当前实例化的基类。

依赖基类在定义处不被搜索：[[class.member.lookup#4]] 只合并非依赖的直接基类的查找结果。原因是 `Base<T>` 可以被显式特化成任何样子，定义处看到的主模板成员不能代表实例化时的真实成员。访问依赖基类的成员必须写 `this->` 或限定名，根源就在这里，详见 [[temp.dep.res]]。

注 2 指出，基类也可能就是当前实例化，例如嵌套类把外围类当作基类：

```cpp run ok
template<class T> struct A {
    typedef int M;
    struct B {
        typedef void M;
        struct C;
    };
};

template<class T> struct A<T>::B::C : A<T> {
    M m;                          // OK: A<T>::M（int）
};
A<int>::B::C c;
int main() { }
```

`A<T>` 是当前实例化，不是依赖基类，所以定义处就搜索它，找到 `A<T>::M`。

### 当前实例化的成员（¶4）

¶4 一个名字是**当前实例化的成员**（member of the current instantiation），条件是：¶4.1 如果它是限定名，它的[[g:lookup-context|查找上下文]]是当前实例化；并且 ¶4.2 对它的查找找到了某个本身是当前实例化的类的成员。

```cpp run ok
template <class T> class A {
    static const int i = 5;
    int n1[i];                    // 当前实例化的成员
    int n2[A::i];                 // 同上
    int n3[A<T>::i];              // 同上
    int f();
};

template <class T> int A<T>::f() {
    return i;                     // 当前实例化的成员
}
int main() { }
```

如果当前实例化的成员在查找时至少指向当前实例化中的一个成员声明（包括终端名依赖的 *using-declarator*），它就是**当前实例化的依赖成员**（dependent member of the current instantiation）。区别在于，通过非依赖基类找到的成员是当前实例化的成员，但不是依赖成员；只有在模板自己的定义中声明的才是。后文判断类型依赖和值依赖时会用到这个概念，例如在类外初始化的静态数据成员。

### 依赖的限定名（¶5）

¶5 限定名（[[basic.lookup.qual]]）在下列情况下是依赖的：

- ¶5.1 它是转换函数名，且目标类型依赖；
- ¶5.2 它的查找上下文依赖，且不是当前实例化；
- ¶5.3 它的查找上下文是当前实例化，且它是 `operator=`；
- ¶5.4 它的查找上下文是当前实例化，当前实例化至少有一个依赖基类，并且限定名查找什么都没找到。

¶5.2 是主体：`T::x`、`Base<T>::x`、`t.x`（`t` 的类型依赖）都是依赖的。

¶5.4 是一个折中。查找上下文是当前实例化时，先在定义处查找。找到了，它就是普通的名字，可以提前检查。没找到但有依赖基类，它可能来自依赖基类，于是推迟。没找到又没有依赖基类，它不可能存在，定义处就可以报错：

<div class="compare" markdown="1">

```cpp ok
template<class T>
struct S : T {
  void f() { S::nothing(); }
  // 有依赖基类：推迟（¶5.4）
};
```

```cpp error
template<class T>
struct S2 {
  void f() { S2::nothing(); }
  // error: 没有依赖基类
};
```

</div>

成员访问也一样。`this->m` 中的 `m` 是成员限定名（[[basic.lookup.qual.general#2]]），查找上下文是 `*this` 的类型，即当前实例化。所以在没有依赖基类的类模板里，`this->undeclared()` 同样在定义处报错，Clang 23 就是这样做的。

例 4 展示了 ¶5.2 的一个细节：

```cpp error
struct A {
    using B = int;
    A f();
};
struct C : A {};
template<class T>
void g(T t) {
    decltype(t.A::f())::B i;      // error: 需要 typename 才能把 B 当作类型
}
template void g(C);               // 即使这里的 A 就是 ::A
```

`t.A::f()` 的类型依赖于 `T`，`decltype` 一个类型依赖的表达式得到依赖类型（¶10.13）。`B` 的查找上下文依赖，按 ¶5.2 是依赖名。块作用域又不是仅类型语境，所以必须写 `typename`。

### 实例化时再查一次（¶6）

```cpp run ok
struct A { int m; };
struct B { int m; };

template<typename T>
struct C : A, T {
    int f() { return this->m; }   // 定义处找到 A::m
    int g() { return m; }         // 定义处找到 A::m
};

template int C<B>::g();           // OK
// template int C<B>::f();        // error: 实例化时找到 A::m 和 B::m
int main() { }
```

¶6 如果实例化出的特化用限定名引用了当前实例化的成员，这个名字要在实例化语境中再查一次。结果与定义语境中的不同，查找就是二义的。

`this->m` 是限定名，定义处只能看到非依赖基类，找到 `A::m`。实例化 `C<B>` 时再查一次，依赖基类 `B` 也加入了，同时找到 `A::m` 和 `B::m`，与定义处的结果不同，所以二义。Clang 23 报告在多个基类中找到成员 `m`。

无限定的 `m` 在定义处绑定到 `A::m`，之后不再改变。[[expr.prim.id.general#2]] 把 `m` 改写为 `(*this).m` 的步骤不在模板定义语境中进行，所以它不算用限定名引用当前实例化的成员，不会再查。

这条规则保证了定义处看到的含义与实例化时一致：实例化时视野更大，如果视野扩大改变了结果，宁可报错，也不悄悄换成另一个成员。

### 依赖的初始化器与占位类型（¶7–¶9）

¶7 如果初始化器的某个成分表达式（constituent expression，[[intro.execution]]）是类型依赖的，初始化器就是依赖的。从依赖初始化器推导类型的占位类型（`auto`、`decltype(auto)`，[[dcl.spec.auto.general]]）也是依赖的。

¶8 类模板实参推导的占位符（[[dcl.type.class.deduct]]）在下列情况下依赖：¶8.1 初始化器依赖；¶8.2 它指类型模板模板形参；¶8.3 它指当前实例化的成员别名模板，而这个别名模板的类型在推导和替换之后依赖。

```cpp run ok
template<class T, class V>
struct S { S(T) { } };

template<class U>
struct A {
    template<class T> using X = S<T, U>;
    template<class T> using Y = S<T, int>;
    void f() {
        delete new X(1);          // 依赖：推导结果 S<int, U>
        delete new Y(1);          // 不依赖：推导结果 S<int, int>
    }
};
template struct A<char>;
int main() { }
```

`X(1)` 的实参 `1` 不依赖，但推导结果 `S<int, U>` 依赖于外层的 `U`（¶8.3）。`Y(1)` 在定义处就能完整推导为 `S<int, int>`。

### 依赖类型（¶10–¶11）

¶10 下列类型是[[g:dependent-type|依赖类型]]：

| 段落 | 内容 | 例子 |
|---|---|---|
| ¶10.1 | 模板形参 | `T` |
| ¶10.2 | 由依赖的（限定）名指称的类型 | `typename T::type` |
| ¶10.3 | 当前实例化的直接成员中的嵌套类或枚举 | `A<T>` 中的 `struct Nested` |
| ¶10.4 | 去掉 cv 后依赖的 cv 限定类型 | `const T` |
| ¶10.5 | 由依赖类型构造的复合类型 | `T*`、`T&`、`void(T)`、`int T::*` |
| ¶10.6 | 元素类型依赖或界值依赖的数组 | `int[N]`、`T[3]` |
| ¶10.7 | 形参中有函数形参包的函数类型 | `void(Ts...)` |
| ¶10.8 | 异常说明值依赖的函数类型 | `void() noexcept(B)` |
| ¶10.9 | 依赖的占位类型 | `auto x = t;` 中 `x` 的类型 |
| ¶10.10 | 依赖的类模板推导占位符 | 上面的 `X(1)` |
| ¶10.11 | 模板名是模板形参或有依赖模板实参的 *simple-template-id* | `TT<int>`、`vector<T>`、不带实参的注入类名 |
| ¶10.12 | 包索引类型 | `Ts...[0]` |
| ¶10.13 | `decltype(e)`，其中 `e` 类型依赖 | `decltype(t + 1)` |
| ¶10.14 | 拼接说明符依赖的拼接类型 {{c++26}} | `typename [:R:]` |

¶10.3 说明，当前实例化的嵌套类是依赖类型，尽管它的名字不是依赖名，不需要 `typename`。这两件事并不矛盾：名字是否依赖决定何时查找，类型是否依赖决定这个类型是否随模板实参变化。`A<int>::Nested` 和 `A<char>::Nested` 是不同的类型。

¶10.11 的脚注指出，不带实参列表的注入类名就是 `X<T>`，所以当前实例化本身也是依赖类型。

¶11 注 3 说，typedef 不引入新类型，所以指向当前实例化成员 typedef 的名字，只有在它所指的类型依赖时才依赖。`template<class T> struct S { using I = int; I x; };` 中的 `I` 不依赖。

!!! history "旧术语：未知特化的成员"
    C++11 到 C++20 的这一节还定义了**未知特化的成员**（member of an unknown specialization），用来描述 `T::x`、`Base<T>::x`，以及在当前实例化中查不到、可能来自依赖基类的名字。C++23 的 [[P1787R6]] 改用依赖的限定名（¶5）和查找上下文重写了这部分规则，删除了这个术语。读旧资料时遇到它，可以大致对应到今天 ¶5.2 和 ¶5.4 描述的名字。

## 类型依赖的表达式（[temp.dep.expr]）

¶1 除下文另有规定外，只要有一个子表达式类型依赖，整个表达式就类型依赖。

¶2 如果当前类（[[expr.prim.this]]）是依赖的，`this` 就类型依赖。在类模板的成员函数里，`this` 的类型是 `X<T>*`，所以 `this->m` 是类型依赖的成员访问。这就是 `this->` 能把名字变成依赖名的原因；不过上文说过，查找上下文是当前实例化时，定义处仍会先查一次。

### 标识符表达式（¶3）

¶3 一个 *id-expression* 在下列情况下类型依赖：它是依赖的 *template-id*（concept-id 除外），或者它的终端名属于下列之一：

| 段落 | 名字查找关联到的实体 |
|---|---|
| ¶3.1 | 用依赖类型声明的实体（最常见：`T t;` 中的 `t`） |
| ¶3.2 | 类型含占位类型的常量模板形参（`template<auto V>` 中的 `V`） |
| ¶3.3 | 类型含占位类型、初始化器类型依赖的变量（`auto x = t;`） |
| ¶3.4 | 当前实例化中返回类型含占位类型的成员函数 |
| ¶3.5 | 初始化器类型依赖的结构化绑定 |
| ¶3.6 | 结构化绑定包 {{c++26}} |
| ¶3.7 | 显式对象形参类型依赖的 lambda 中按值捕获的实体 |
| ¶3.8 | `__func__`，如果某个外围函数是模板、类模板成员或泛型 lambda |
| ¶3.9 | 返回类型依赖的函数的结果绑定（契约后置条件，[[dcl.contract.res]]）{{c++26}} |
| ¶3.10 | 指定依赖类型的转换函数名 |
| ¶3.11 | 展开语句引入的、类型含占位类型的名字（展开语句不是迭代式的，或其展开初始化器类型依赖）{{c++26}} |
| ¶3.12 | 依赖的名字 |

此外，命名当前实例化的依赖成员、类型为未知界数组的静态数据成员，也类型依赖（[[temp.static]]），因为类外定义可能补上数组界。

`__func__` 的类型是 `const char[N]`，`N` 取决于函数名字符串的长度。这个字符串的内容由实现定义，实现可以让不同特化的 `__func__` 不同（例如带上模板实参），所以它的类型在实例化之前未知。

¶3.6 的例 1（C++26 结构化绑定包）：

```cpp run ok
#include <cstdio>
struct C { };
void g(...) { std::puts("#1 g(...)"); }

template <typename T>
void f() {
    C arr[1];
    auto [...e] = arr;      // e 是结构化绑定包
    g(e...);                // 依赖调用：实例化时 ADL 找到 #2
}

void g(C) { std::puts("#2 g(C)"); }

int main() { f<int>(); }    // 输出 #2 g(C)
```

`f` 里没有任何东西依赖 `T`，可 `e` 仍被规定为类型依赖：结构化绑定包的元素个数要到实例化时才确定。于是 `g(e...)` 是依赖调用（¶2.1），`g` 的查找推迟到实例化，ADL 在实例化语境中找到了后声明的 `g(C)`。

### 只看所写类型的形式

¶3 末尾规定，下列形式只在所写的类型依赖时才类型依赖，即使操作数类型依赖也不算：

- 函数式转型 `T(args)`、`T{args}`；
- `new T(...)`；
- 四种具名转型 `static_cast<type-id>(e)` 等；
- C 风格转型 `(type)e`。

这些表达式的类型就是写出来的那个类型（或指向它的指针），与操作数无关。`static_cast<int>(t)` 不类型依赖，它的类型就是 `int`，但它可能值依赖（见下文）。

### 永远不类型依赖的形式（¶4）

¶4 下列形式的类型不可能依赖：字面量、`sizeof`、`sizeof...`、`alignof`、`typeid`、`delete`、`throw`、`noexcept(e)`、*requires* 表达式，以及 {{c++26}} 反射表达式 `^^x`（类型总是 `std::meta::info`）。

```cpp run ok
#include <type_traits>
template<class T> void g(T t) {
    auto n = sizeof(t);           // n 的类型是 size_t，不依赖
    static_assert(std::is_same_v<decltype(n), decltype(sizeof 0)>);   // 定义处就能检查
    int i = 0;
    auto a = i;                   // 不依赖
    auto b = t;                   // 类型依赖（¶3.3）
    (void)a; (void)b;
}
template void g(int);
int main() { }
```

### 成员访问及其他（¶5–¶9）

¶5 类成员访问表达式在下列情况下类型依赖：¶5.1 成员名的终端名依赖；¶5.2 其拼接表达式类型依赖；¶5.3 表达式指向当前实例化的成员，而该成员的类型依赖。

注 2 解释了这样规定的效果。`x.y` 的类型通常就是 `x` 所属类中成员 `y` 的类型。如果 `x` 的类型依赖且不是当前实例化，`y` 的类型总是依赖的。反过来，对当前实例化中声明为 `int n;` 的成员，`this->n` 不类型依赖，定义处就知道它是 `int`。

¶6 花括号列表中有任一元素类型依赖或是包展开时，列表类型依赖。¶7 折叠表达式总是类型依赖。¶8 包索引表达式在其 *id-expression* 类型依赖时类型依赖。¶9 {{c++26}} 拼接表达式在其拼接说明符依赖时类型依赖。

## 值依赖的表达式（[temp.dep.constexpr]）

值依赖只在需要常量表达式的地方有意义：数组界、模板实参、`static_assert`、`if constexpr` 的条件、`noexcept(...)`、位域宽度、`alignas` 等。¶1 在这些地方，除另有规定外，只要有一个子表达式值依赖，整个表达式就值依赖。

### 标识符表达式（¶2）

¶2 一个 *id-expression* 在下列情况下值依赖：

- ¶2.1 它是 concept-id，且概念名或某个实参依赖；
- ¶2.2 它类型依赖（类型都不确定，值当然也不确定）；
- ¶2.3 它是常量模板形参的名字；
- ¶2.4 {{c++26}} 它是展开语句引入的名字；
- ¶2.5 它命名当前实例化的依赖成员中的静态数据成员，且没有在类内初始化；
- ¶2.6 它命名当前实例化的依赖成员中的静态成员函数；
- ¶2.7 它命名一个潜在常量变量（[[expr.const.init]]），其初始化器值依赖。

¶2.5 的意思是：类内初始化的 `static const int n = 3;` 在定义处就知道值；类外初始化的静态成员则可能对不同特化有不同的定义（可以显式特化静态成员），所以值依赖：

```cpp run ok
template<class T> struct S {
    static const int n = 3;       // 类内初始化：不值依赖
    static const int m;           // 类外初始化：值依赖（¶2.5）
    void f() {
        int a[n];                 // 定义处 n == 3
        int b[m];                 // 推迟到实例化
        (void)a; (void)b;
    }
};
template<class T> const int S<T>::m = 4;
template struct S<int>;
int main() { }
```

¶2 末尾还规定，`sizeof`、`alignof`、`typeid` 在操作数表达式类型依赖或操作数类型依赖时值依赖。所以 `sizeof(t)` 不类型依赖但值依赖，是类型确定而值不确定的典型例子。

### 其他形式（¶3–¶6）

- ¶3 函数式转型、具名转型和 C 风格转型，在所写类型依赖或操作数值依赖时值依赖。`N` 是常量模板形参时，`static_cast<int>(N)` 值依赖但不类型依赖。
- ¶4 `sizeof...(pack)` 和折叠表达式总是值依赖。
- ¶5 `noexcept(e)` 在 `e` 涉及模板形参时值依赖。涉及（involves）比类型依赖宽：只要 `e` 里出现了模板形参，结果是否为 `true` 就可能随特化变化。
- ¶6 `&` 加限定名，且限定名命名当前实例化的依赖成员时，表达式值依赖，例如 `&S<T>::sm`。此外，`&` 的操作数作为核心常量表达式求值成功、结果指向一个模板化的静态或线程存储期对象或成员函数时，也值依赖。这类实体每个特化各有一份，地址随特化而不同。

### 反射与拼接（¶7–¶8）{{c++26}}

¶7 反射表达式在下列情况下值依赖：¶7.1 形如 `^^name`，而查找找到的声明栖居于某个模板化实体对应的作用域，或者名字是依赖的限定名、依赖的命名空间名、模板形参名；¶7.2 形如 `^^type-id`，且类型依赖；¶7.3 形如 `^^id-expression`，且它值依赖。

`^^x` 的类型永远是 `std::meta::info`，所以从不类型依赖（¶4）。但它反射的是哪个实体可能取决于模板实参，这就是值依赖。¶7.1 的第一种情形意味着，在模板里反射模板内部声明的实体（每个特化各有一份）也是值依赖的。

¶8 拼接表达式在其拼接说明符依赖时值依赖。

## 依赖的拼接说明符（[temp.dep.splice]）{{c++26}}

¶1 拼接说明符 `[: e :]` 在常量表达式 `e` 值依赖时依赖。`[: e :]<args>` 在拼接说明符依赖或任一模板实参依赖时依赖。用作嵌套名说明符的拼接在其拼接说明符依赖时依赖。

依赖的拼接说明符和依赖的嵌套名说明符处境相同：定义处不知道它指什么，后面的成员名指模板或类型时需要 `template` 或 `typename`，除非处于仅类型语境（[[temp.res#4]]）。下面两个例子来自草案；本机 Clang 23 不支持反射（`^^` 和 `[: :]`），没有经过编译验证。

```cpp
template<auto T, auto NS>
void fn() {
    using a = [:T:]<1>;                                   // 依赖；别名声明是仅类型语境
    static_assert([:NS:]::template TCls<1>::v == a::v);   // [:NS:] 依赖：须写 template
}

namespace N {
    template <auto V> struct TCls { static constexpr int v = V; };
}

int main() {
    fn<^^N::TCls, ^^N>();
}
```

¶3 例 2 展示了依赖的拼接会把检查推迟到实例化：

```cpp
template<template<class> class X>
struct S {
    [:^^X:]<int, float> m;        // ^^X 反射模板形参，值依赖
};

template<class> struct V1 {};
template<class, class = int> struct V2 {};

S<V1> s1;                         // error: V1<int, float> 实参过多
S<V2> s2;                         // OK
```

直接写 `X<int, float>` 的话，`X` 是只接受一个类型实参的模板模板形参，定义处就会因实参过多而报错。经过 `[:^^X:]` 一转，变成依赖的拼接，实参个数的检查推迟到实例化。`X = V2` 时第二个形参有默认实参，完全合法。

## 依赖的命名空间（[temp.dep.namespace]）{{c++26}}

¶1 命名空间别名在下列情况下依赖：它的定义 `namespace A = ...;` 中，右边是依赖的限定名，或者是依赖的拼接说明符。命名依赖命名空间别名的 *namespace-name* 也是依赖的。

```cpp
template<std::meta::info R>
int fn() {
    namespace Alias = [:R:];          // [:R:] 依赖，所以 Alias 依赖
    return typename Alias::T{};       // 须写 typename
}

namespace NS { using T = int; }

int a = fn<^^NS>();
```

C++26 之前，命名空间不可能依赖于模板形参，因为没有办法把命名空间当作模板实参传递。反射让 `std::meta::info` 可以表示命名空间，于是有了依赖的命名空间，限定名的规则（[[temp.dep.type#5]] 的 ¶5.2）也随之适用于它。这个例子同样没有经过编译验证。

## 依赖的模板实参（[temp.dep.temp]）

- ¶1 类型模板实参在它指定的类型依赖时依赖。
- ¶2 常量模板实参在它的类型依赖，或它的常量表达式值依赖时依赖。
- ¶3 此外，如果对应的常量模板形参是引用或指针类型，而模板实参指向当前实例化的成员或依赖类型的成员，模板实参也依赖。
- ¶4 包展开形式的模板实参依赖。
- ¶5 模板模板实参在它命名模板形参，或它的终端名依赖时依赖。

¶3 的例子：

```cpp run ok
template<int* P> struct Tag { };
template<class T> struct W {
    static int sm;
    Tag<&sm> t;           // &sm 指向当前实例化的成员：依赖（¶3）
};
template<class T> int W<T>::sm = 0;
W<int> w;
int main() { }
```

`W<int>::sm` 和 `W<char>::sm` 是不同的对象，所以 `Tag<&sm>` 在不同特化中是不同的类型，必须算作依赖。

模板实参的依赖性经 [[temp.dep.type#10]] 的 ¶10.11 传给 *simple-template-id*：只要有一个实参依赖，整个特化就是依赖类型。

!!! impl "编译器如何表示依赖性"
    - Clang 在语法树节点上记录一组依赖位（类型依赖、值依赖、实例化依赖、含未展开的包等），与本节的定义直接对应。依赖类型用专门的节点表示，例如 `typename T::x`、模板形参 `T`、注入类名各有自己的节点类型；实例化时遍历这些节点做替换。
    - 当前实例化是 Clang 能在定义处报告 `no member named ... in 'X<T>'` 的依据：它在定义处对当前实例化做真实的成员查找，没有依赖基类时直接诊断。
    - GCC 有对应的谓词判断表达式是否类型依赖、值依赖，概念上与标准术语一一对应。

## 常见误解

!!! pitfall "值依赖就是类型依赖"
    `sizeof(t)`、`static_cast<int>(N)`、`noexcept(T())` 都值依赖但不类型依赖。用它们构成的类型（如 `int[sizeof(t)]`）是依赖类型，但表达式本身的类型在定义处已知，可以参与定义处的重载决议。

!!! pitfall "不需要 typename，就和 T 无关"
    `A<T>::Nested` 不需要 `typename`，因为名字在定义处找得到；但它是依赖类型（¶10.3），在不同特化中是不同的类。

!!! pitfall "this-> 可以推迟一切检查"
    `this->m` 的查找上下文是当前实例化。当前实例化没有依赖基类而 `m` 不存在时，Clang 和 GCC 在定义处就报错。如果定义处在非依赖基类中找到了 `m`，实例化时还会再查一次（¶6），依赖基类引入同名成员时会二义。

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
    `p`、`q` 是指向当前实例化的指针吗？这有什么实际影响？

<details markdown="1">
<summary>答案</summary>

`k` 的类型与 `N` 相同（都是 `int`，`constexpr` 带来的 const 不计），初始化器是单个标识符 `N`，所以 `k` 与 `N` 等价，`A<k>` 是当前实例化（[[temp.dep.type#2]]）。`k2` 的初始化器带括号，按注 1 不再等价，`A<k2>` 不是当前实例化，尽管在每个实例化中它和 `A<N>` 都是同一个类型。

实际影响在于，通过 `A<k>::` 访问的名字是当前实例化的成员，定义处就能查找，不需要 `typename`，拼写错误可以提前报告。通过 `A<k2>::` 访问的名字是依赖名（¶5.2），类型成员要写 `typename`，错误推迟到实例化。

Clang 23 没有实现等价变量这一条，它对函数体内的 `A<k>::type` 同样要求 `typename`，见上文的实现说明。
</details>

!!! question "思考题 2"
    在 `template<class T> struct S { int n; void f(); };` 的 `f` 中，`this->n` 类型依赖吗？`decltype(this->n)` 是依赖类型吗？

<details markdown="1">
<summary>答案</summary>

都不是。`this` 类型依赖（[[temp.dep.expr#2]]），但成员访问是否类型依赖由 [[temp.dep.expr#5]] 单独规定。终端名 `n` 不依赖：查找上下文是当前实例化，定义处找到了成员，¶5.2 和 ¶5.4 都不满足。表达式指向当前实例化的成员 `n`，而 `n` 的类型 `int` 不依赖。所以 `this->n` 不类型依赖，`decltype(this->n)` 也不是依赖类型（¶10.13 要求表达式类型依赖），就是 `int`。
</details>

!!! question "思考题 3"
    为什么折叠表达式被无条件地规定为类型依赖，而不是在包元素类型依赖时才依赖？

<details markdown="1">
<summary>答案</summary>

折叠表达式必然含有一个未展开的包，包的长度要到实例化时才知道。即使元素类型都已知（比如 `int...` 常量形参包），空包时结果取决于运算符：`&&` 得 `true`，`||` 得 `false`，`,` 得 `void()`，其他运算符非良构；非空包时结果类型取决于展开出的表达式和运算符重载。定义处无法确定结果类型，所以标准直接规定它类型依赖（[[temp.dep.expr#7]]）。同理，`sizeof...` 和折叠表达式总是值依赖（[[temp.dep.constexpr#4]]）。
</details>

## 小结

| 概念 | 出处 | 要点 |
|---|---|---|
| 依赖调用 | [temp.dep.general] ¶2 | 无限定名，加上类型依赖的实参、包展开或依赖模板实参；实例化时追加 ADL |
| 当前实例化 | [temp.dep.type] ¶1–¶2 | 类模板内部指称自身的方式：注入类名、`X<T>`、等价实参 |
| 依赖基类 | ¶3 | 依赖且不是当前实例化；定义处不被搜索 |
| 当前实例化的（依赖）成员 | ¶4 | 定义处可以查找的成员 |
| 依赖的限定名 | ¶5 | 查找上下文依赖且不是当前实例化；或当前实例化有依赖基类而查不到 |
| 实例化时再查 | ¶6 | 限定名引用当前实例化的成员，两次结果不同则二义 |
| 依赖类型 | ¶10 | 14 种情形，包括 C++26 的包索引和拼接类型 |
| 类型依赖 | [temp.dep.expr] | 由子表达式传递；转型只看目标类型；`sizeof` 等永不类型依赖 |
| 值依赖 | [temp.dep.constexpr] | 常量形参、类外初始化的静态成员、`sizeof` 依赖操作数、`sizeof...`、折叠、反射 |
| 依赖拼接与命名空间 | [temp.dep.splice]、[temp.dep.namespace] | C++26 反射带来的新依赖来源 |
| 依赖模板实参 | [temp.dep.temp] | 依赖类型、值依赖、指向当前实例化成员、包展开、模板形参 |
