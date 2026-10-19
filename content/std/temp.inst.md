---
title: 隐式实例化
summary: 编译器何时自动从模板生成定义：类模板特化在需要完整类型时实例化，且只实例化成员的声明；成员函数、静态数据成员、默认实参、noexcept 说明符按需单独实例化；为常量求值所需也算需要；实现不得多实例化，无限递归实例化是 UB。
status: done
covers: temp.inst
papers: P0859R0, P0692R1
related: temp.spec, temp.explicit, temp.expl.spec, temp.point, temp.res, temp.decls, basic.def.odr, expr.const, stmt.if, topics/compile-time-programming
tags: 模板, 实例化, 惰性实例化, 完整类型, constexpr
updated: 2026-10-18
---

C++ 模板的一个基本设计决定是惰性：写下 `std::vector<Widget>` 并不会让编译器立刻生成 `vector<Widget>` 的全部几百个成员函数；它只生成你用到的那部分，而且是在你用到的时候。这既保证了编译速度，也带来了表达力：一个类模板可以有某些成员只对部分实参合法（`std::vector<T>::resize(n)` 要求 `T` 可默认构造，但不可默认构造的 `T` 照样能用 `vector<T>` 的其余部分）。

第 13.9.2 节 [[temp.inst]] 把惰性写成精确的规则：

- 类模板特化在需要完整类型时才实例化（¶2），实例化时只生成成员的声明（¶3）。
- 成员、函数模板特化、变量模板特化在需要定义存在时才实例化（¶4–¶7）。
- 需要定义存在，当然包括 odr-use；为常量求值所需、为确定表达式类型所需也算（¶8–¶9）。
- 实现不得多做（¶12），默认实参、noexcept 说明符等单独实例化的构造各自按需实例化（¶14–¶16）。
- 递归实例化有实现定义的深度上限，无限递归是 {{ub}}（¶18）。
- 约束（*requires-clause*）不随特化一起实例化（¶19）。

读本页前最好了解[[temp.spec]]的术语，以及实例化点（[[temp.point]]）的概念。本节决定是否实例化，[[temp.point]] 决定在哪里实例化。

## 已声明的特化（¶1）

¶1 定义了一个辅助概念：特化 `E` 是[[g:declared-specialization|**已声明的特化**]]（declared specialization），如果

- 存在可达的、针对 `E` 的显式实例化定义或显式特化声明；或者
- 存在可达的显式实例化声明（`extern template`），且 `E` 不是：
    - ¶1.1 内联函数；
    - ¶1.2 用从初始化器或返回值推导的类型声明的（`auto` 变量、`auto` 返回类型函数）；
    - ¶1.3 潜在常量变量（potentially-constant variable，[[expr.const.init]]）；
    - ¶1.4 模板化类的特化。

后面所有关于隐式实例化何时发生的规则，都以“除非它是已声明的特化”开头。直观地说，**已声明的特化，其定义有别的来源**：要么由程序员手写（显式特化），要么在别处生成（显式实例化定义/声明），编译器就不必（也不应）在这里自己生成一份。

那四个例外说的是：即使有 `extern template`，以下几种东西编译器仍然需要能在本 TU 看到定义并实例化：

| 例外 | 为什么仍需隐式实例化 |
|---|---|
| 内联函数 | 为了内联展开（见 ¶5 注 3） |
| 推导类型的变量/函数 | 不实例化就不知道类型 |
| 潜在常量变量 | 常量表达式要用它的值 |
| 模板化类的特化 | 类必须完整才能使用，`extern template` 只是不让生成成员的定义 |

注 1 提醒：在导入模块的 TU 中发生的隐式实例化，不能使用被导入 TU 中具有内部链接的名字（[[basic.link]]）。

!!! note "较新的措辞"
    “declared specialization” 是较新的草案措辞，用来把以前散落在 [[temp.explicit]]、[[temp.expl.spec]] 和本节里的“除非已被显式实例化或显式特化”统一成一个术语。行为没有实质变化。

## 类模板特化何时实例化（¶2）

¶2 除非是已声明的特化，类模板特化在以下情况隐式实例化：

1. 在要求完整定义的对象类型的语境中被引用；
2. 类类型的完整性会影响程序语义时。

第一类是显然的：定义变量、`sizeof`、访问成员、按值传参/返回（在函数定义处）、`new`、基类……都需要完整类型（[[basic.types.general]]）。

第二类更微妙。注 2 解释说，如果表达式的语义依赖于类模板特化的成员列表或基类列表，特化就会被生成。比如 `delete p` 的语义取决于类有没有声明析构函数；`D*` 到 `B*` 的转换取决于继承关系。

```cpp run ok title="needs_complete.cpp"
template<class T> class B { };
template<class T> class D : public B<T> { };

void f(void*);
void f(B<int>*);

void g(D<int>* p, D<char>* pp, D<double>* ppp) {
    f(p);              // 要知道 D<int>* 能否转为 B<int>*：实例化 D<int>，选 f(B<int>*)
    B<char>* q = pp;   // 派生到基类的指针转换：实例化 D<char>
    delete ppp;        // delete 的语义依赖类定义：实例化 D<double>
    (void)q;
}
```

反过来，以下场合不需要完整类型，所以不会实例化：

```cpp ok
template<class T> struct Bad {
    static_assert(sizeof(T) == 0, "instantiated!");   // 一旦实例化就触发
};
Bad<int>* p = nullptr;      // 指针：不需要完整类型
void take(Bad<int>&);       // 引用形参的函数声明：不需要
using U = Bad<int>;         // 别名：不需要
extern Bad<int> obj;        // 非定义的变量声明：不需要
```

把最后一行 `extern` 去掉，或者写 `sizeof(*p)`，`static_assert` 立刻触发：

```cpp error
template<class T> struct Bad { static_assert(sizeof(T) == 0, "instantiated!"); };
Bad<int>* p = nullptr;
auto n = sizeof(*p);        // error: 实例化 Bad<int>，static_assert 失败
```

### 只声明未定义的模板（¶2 末）

如果为特化选中的模板（主模板或某个部分特化，[[temp.spec.partial.match]]）在实例化点已声明但未定义，实例化得到的是不完整类型：

```cpp error
template<class T> class X;
X<char> ch;                 // error: X<char> 是不完整类型
```

注意实例化仍然发生了，只是结果不完整。这对 `std::tuple_size`、`std::hash` 这类故意不定义主模板的 trait 很有用：未特化的实参得到不完整类型，`sizeof` 或成员访问就会报错，SFINAE 能检测到。

## 实例化类：生成哪些成员（¶3）

¶3 是惰性的核心。类模板特化的隐式实例化会导致：

- ¶3.1 对非删除的成员函数、成员类、有作用域的成员枚举、静态数据成员、成员模板、友元，只实例化声明，不实例化定义；
- ¶3.2 对删除的成员函数、无作用域的成员枚举、成员匿名联合，实例化定义。

为什么分成两类？¶3.2 里的东西，声明和定义分不开或者不必分开：

- 删除函数的定义就是 `= delete`，没有函数体可推迟；
- 无作用域枚举的枚举项会被注入到外围类作用域，不实例化定义就无法知道类里有哪些名字；
- 匿名联合的成员同样是外围类的成员。

有作用域枚举（`enum class`）的枚举项只在枚举自己的作用域内，所以可以推迟。

```cpp ok
template<class T>
struct C {
    void f() { T x; }          // f 的定义只在需要时实例化
    void g() = delete;
};
C<void> c;                     // OK：C<void>::f 的定义没有被实例化，T x 不会出错
```

只要不调用 `f`，`C<void>` 完全可以使用。类模板的成员之所以可以只对部分实参合法，根据就在这里。

标准例 3 的后半段：

```cpp
template<> void C<int>::g() { }   // error: 重定义 C<int>::g
```

`C<int>` 被实例化时，`g` 的定义（`= delete`）也被实例化了，于是再写显式特化就是重定义。

!!! impl "Clang 的偏差"
    截至写作时，Clang 23 接受上面这行 `template<> void C<int>::g() { }`（在 `C<int> c;` 之后），没有报重定义。按 ¶3.2 这是非良构的。

### 对应定义的声明视同定义

¶3 后半规定，为了按 [[basic.def.odr]] 和 [[class.mem]] 判断被实例化的重声明是否合法，模板中对应一个定义的、被实例化出来的声明被视为定义。也就是说，惰性只是推迟生成函数体，并不是把这里当作没有定义。

最典型的后果是在类模板里定义友元函数（hidden friend 写法）时违反 ODR：

```cpp error
template<typename T> struct Friendly {
    template<typename U> friend int f(U) { return sizeof(T); }
};
Friendly<char> fc;
Friendly<float> ff;    // error: 第二次给出 f(U) 的定义
```

每个 `Friendly<X>` 都在外围命名空间声明同一个函数模板 `f`，而这个声明对应模板中的一个定义，因此视同定义。两次实例化就是两次定义，非良构。正确的写法是让友元依赖于 `T`（例如 `friend int f(Friendly<T>)`），这样每个特化定义的是不同的函数。

标准例 4 的前半段是同一原理作用在成员类模板的部分特化上：

```cpp error
template<class T, class U>
struct Outer {
    template<class X, class Y> struct Inner;
    template<class Y> struct Inner<T, Y>;         // #1a
    template<class Y> struct Inner<T, Y> { };     // #1b：#1a 的合法重声明（定义）
    template<class Y> struct Inner<U, Y> { };     // #2
};
Outer<int, int> outer;                            // error at #2
```

`T`、`U` 都是 `int` 时，#2 和 #1b 成了同一个部分特化 `Inner<int, Y>` 的两个定义。

## 成员何时实例化（¶4）

¶4 除非是已声明的特化，模板化类的成员的特化在被引用于要求成员定义存在的语境、或成员定义的存在影响程序语义时隐式实例化。特别地，**静态数据成员的初始化（及其副作用）不会发生，除非该静态数据成员本身以要求其定义存在的方式被使用。**

自注册工厂在模板里失效，根本原因就是最后这句：

```cpp run ok title="autoreg.cpp"
#include <cstdio>
int reg(const char* n) { std::printf("registered %s\n", n); return 0; }

template<class T> struct AutoReg {
    static inline int token = reg(T::name);   // 希望"每个派生类自动注册"
};

struct Foo : AutoReg<Foo> { static constexpr const char* name = "Foo"; };
struct Bar : AutoReg<Bar> {
    static constexpr const char* name = "Bar";
    static constexpr auto* force = &token;    // odr-use token：强制实例化其定义
};

int main() { std::puts("main"); }
// 输出：
// registered Bar
// main
```

`Foo` 从未注册：`AutoReg<Foo>` 被实例化了（作为基类需要完整类型），但那只实例化了 `token` 的声明；没有人用到 `token`，它的定义（含初始化器）就不实例化，`reg` 就不会被调用。`Bar` 通过取 `&token` 强制了实例化。

!!! pitfall "非模板中的同样写法是有效的"
    把 `AutoReg` 换成非模板类，`static inline int token = reg(...)` 一定会初始化（动态初始化可能被推迟，但它是程序的一部分）。很多人把非模板版本改写成 CRTP 版本后发现注册失效，原因就在 ¶4。

## 函数模板特化何时实例化（¶5–¶6）

¶5 除非是已声明的特化，函数模板特化在被引用于要求函数定义存在的语境、或定义的存在影响程序语义时隐式实例化。从友元函数定义实例化出声明的函数，同样按此规则实例化定义。

要求函数定义存在，基本等于 odr-use（[[basic.def.odr]]）：调用、取地址、作为虚函数被类使用……但不包括出现在 `sizeof`、`decltype`、`noexcept` 这类不求值操作数里的情形，那里只需要声明（和类型）。

注 3 解释了 ¶1.1 的例外：对一个内联函数写 `extern template`，它不是已声明的特化，所以 odr-use 时仍然隐式实例化，这样函数体可以被内联；只是编译器不会在本 TU 输出它的外部副本。可以在 [[temp.explicit]] 中看到这在目标文件中的效果。

¶6 例 5 给出了完整的场景：

```cpp ok
template<class T> struct Z {
    void f();
    void g();
};

void h() {
    Z<int> a;         // 需要实例化类 Z<int>
    Z<char>* p;       // 不需要实例化 Z<char>
    Z<double>* q;     // 不需要实例化 Z<double>

    a.f();            // 需要实例化 Z<int>::f()
    p->g();           // 需要实例化类 Z<char>（成员访问），以及 Z<char>::g()
}
```

`Z<double>`、`Z<int>::g()`、`Z<char>::f()` 都不需要被实例化。（这段代码能通过编译，但链接会失败，因为 `f`、`g` 没有定义，这与实例化无关。）

## 变量模板特化（¶7）

¶7 变量模板特化（C++14）的规则与函数相同：除非是已声明的特化，在要求变量定义存在、或其存在影响语义时隐式实例化。变量模板的默认模板实参只在需要其值时才实例化。

## 影响语义的两个具体情形（¶8–¶9）

### 为常量求值所需（¶8）

¶8 如果某个变量或函数被一个表达式为常量求值所需（needed for constant evaluation，[[expr.const.defns]]），就认为它的定义的存在影响程序语义，**即使该表达式并不要求常量求值，或者常量求值实际上没有用到这个定义**。

为什么规定得这么宽？因为常量求值的结果会影响程序的含义（例如是否窄化、数组界、`if constexpr` 的分支），编译器必须提前实例化 constexpr 函数才能尝试求值，而尝试本身就可能触发实例化。为了让结果一致，规则要求只要表达式是潜在常量求值的（potentially constant evaluated），其中用到的 constexpr 函数就要被实例化。

```cpp error title="needed_for_ce.cpp"
template<typename T> constexpr int f() { return T::value; }

template<bool B, typename T> void g(decltype(B ? f<T>() : 0));
template<bool B, typename T> void g(...);
template<bool B, typename T> void h(decltype(int{B ? f<T>() : 0}));
template<bool B, typename T> void h(...);

void x() {
    g<false, int>(0);   // OK：B ? f<T>() : 0 不是潜在常量求值的
    h<false, int>(0);   // error：实例化了 f<int>，T::value 非良构
}
```

区别在于：`h` 中的 `int{...}` 是列表初始化，需要判断是否窄化（[[dcl.init.list]]），而窄化的判断依赖于源表达式是否是常量表达式及其值，所以 `B ? f<T>() : 0` 变成潜在常量求值的，`f<int>` 必须实例化。即便 `B` 是 `false`、即便 `int` 到 `int` 根本不可能窄化，也一样。而 `f<int>` 的函数体错误不在推导的直接语境中（[[temp.deduct]]），所以是硬错误，不是 SFINAE。

`g` 中 `decltype` 的操作数只关心类型，`f<T>()` 的类型由声明就能确定（返回 `int`），不需要实例化定义。

!!! history "历史与演进"
    在 C++17 及以前，constexpr 函数何时被定义（实例化）一直是 CWG1581 中悬而未决的问题，各编译器行为不一。C++20 通过 [[P0859R0]] 引入“潜在常量求值”与“为常量求值所需”两个概念，形成了 ¶8 的规则。

### 为确定表达式类型所需（¶9）

¶9 类似地，如果为了确定程序中某个表达式的类型必须实例化，那么定义的存在也影响语义，即使变量或函数没有被 odr-use。

最典型的是未知界数组：

```cpp
template<typename T> struct X {
    static inline int arr[] = {1, 2, T::error};
};
decltype(+X<int>::arr) r;    // error: 为了补全 arr 的类型（int[3]），实例化了它的定义

template<typename T> struct X2 {
    static inline int arr[3] = {1, 2, T::error};
};
decltype(+X2<int>::arr) r2;  // OK：arr 的类型已完整，且未被 odr-use
```

`X<int>::arr` 声明的类型是 `int[]`，界要从初始化器得出，不实例化定义就不知道 `+arr` 是 `int*` 还是别的（实际上都是 `int*`，但标准不做这种碰巧无关紧要的推理）。`X2` 的类型已完整，`decltype` 是不求值操作数，不实例化。

`auto` 变量模板、返回类型推导的函数同理：要知道 `decltype(f<int>())`，必须实例化 `f<int>` 的函数体。

!!! impl "Clang 的偏差"
    截至写作时，Clang 23 接受上面的 `decltype(+X<int>::arr) r;`，没有实例化 `arr` 的初始化器。按 ¶9 这是非良构的。

## 不实例化也能完成重载决议时（¶10–¶11）

¶10 如果不实例化某个类模板定义就能确定重载决议选中哪个函数，那么是否实际实例化是未指明的（{{unspec}}）。

```cpp ok
template <class T> struct S {
    operator int();
};

void f(int);
void f(S<int>&);
void f(S<float>);

void g(S<int>& sr) {
    f(sr);     // 允许但不要求实例化 S<int>、S<float>
}
```

`f(S<int>&)` 是精确匹配，引用绑定不需要看 `S<int>` 的内部；`S<float>` 那个候选，只有实例化后才知道有没有从 `S<int>` 的转换。编译器可以跳过它，也可以照常实例化，两者都合规。后果是：如果 `S<float>` 的实例化本身会出错，这段代码在某些实现上能编译、在另一些上不能。这是可移植性的一个隐患，写 trait 时要注意不要让无关候选的实例化出错。

¶11 函数模板特化以涉及重载决议的方式被使用时，其声明被隐式实例化（[[temp.over]]）。这就是推导、替换、合成声明、加入候选集那一步；函数体此时不实例化，除非它最终被选中且被 odr-use。

## 实现不得多实例化（¶12）

¶12 实现不得隐式实例化函数模板、变量模板、成员模板、非虚成员函数、模板化类的成员类或静态数据成员、constexpr if 语句的子语句（[[stmt.if]]），除非这样的实例化是必需的。

这是对程序员的保证，不是许可。它意味着你可以在类模板里写只对某些 `T` 合法的成员，而不用担心编译器把它们都生成出来。

注 4：泛型 lambda 的实例化（即闭包类型的实例化）不需要实例化其复合语句中 constexpr if 的子语句，除非调用运算符模板被实例化。

```cpp ok
template<class T> struct W {
    void nv() { T::nope(); }   // 非虚：不使用就永不实例化
};
W<int> w;                       // OK
```

虚函数是例外：是否隐式实例化一个本来不会被实例化的虚成员函数，是未指明的。原因是实现需要虚函数表，而虚函数表要填入函数地址，所以大多数实现在类的构造函数被实例化/使用时就会实例化所有虚函数：

```cpp
template<class T> struct W {
    virtual void v() { T::nope(); }
};
W<int> w;    // 未指明：Clang 会实例化 W<int>::v 并报错
```

¶12 还有两条关于默认实参和默认成员初始化器的规定：

- 在默认实参或默认成员初始化器中使用模板特化，不会导致该模板被隐式实例化，除非为了判断默认实参/初始化器本身的正确性必须这么做。
- 函数调用中使用默认实参，会导致其中的特化被隐式实例化；构造函数定义或聚合初始化中使用默认成员初始化器，同样导致其中的特化被实例化。

```cpp
template<class T> struct S {
    int m = T::value;     // 默认成员初始化器
    S(int) : m(0) {}      // 不使用它
    S() {}                // 使用它
};
S<int> a(1);   // OK：只用了 S(int)，默认成员初始化器从未被实例化
S<int> b;      // error：S() 的定义被实例化，使用了 m 的默认成员初始化器
```

## 与外围函数一起实例化的构造（¶13）

¶13 模板化函数 `F` 若是 (13.1) 局部类的成员，或 (13.2) 非泛型 lambda 的函数调用运算符，那么 `F` 的单独实例化构造（[[temp.decls.general]]：默认实参、noexcept 说明符、函数体等）在 `F` 的声明被实例化时就实例化。

换句话说，外围函数模板的特化一被实例化，其中局部类的成员函数体、非泛型 lambda 的函数体也跟着实例化，它们不享有不用就不生成的惰性。

```cpp error
template<class T> void outer() {
    struct Local { void f() { T::nope(); } };   // 局部类成员：随 outer<int> 一起实例化
}
template void outer<int>();                     // error
```

```cpp error
template<class T> void outer() {
    auto l = [] { T::nope(); };                 // 非泛型 lambda：函数体随外围实例化
}
template void outer<int>();                     // error（即便 l 从未被调用）
```

为什么这样规定？局部类和 lambda 不能在外围函数之外被引用或实例化，如果不在此时实例化，就再也没有机会了。注 5 强调，就实例化而言它们仍是与外围函数分开的构造，只是实例化的时机与外围函数绑定。

## 默认实参实例化（¶14–¶15）

¶14 除上述情形外，当模板化函数 `f` 以需要使用默认实参的方式被调用时，依赖名被查找、语义约束被检查、默认实参中用到的模板被实例化，就像这个默认实参是同一作用域、同样模板形参、同样访问权限的函数模板特化中的一个初始化器那样。不过闭包类型的声明作用域（因而它的关联命名空间）仍由默认实参定义处的语境决定。这一过程称为[[g:default-argument-instantiation|**默认实参实例化**]]（default argument instantiation），实例化后的默认实参再作为 `f` 的实参。

¶15（注 6）指出，每个默认实参各自独立地实例化。

```cpp error
template<class T> void f(T x, T y = ydef(T()), T z = zdef(T()));

class A { };
A zdef(A);

void g(A a, A b, A c) {
    f(a, b, c);   // 不实例化任何默认实参
    f(a, b);      // 实例化 z = zdef(T())：OK
    f(a);         // error：实例化 y = ydef(T())，ydef 未声明
}
```

`ydef` 从未声明，但只要不用到 `y` 的默认实参，程序就是良构的。这让标准库可以给函数模板写一些只对部分类型有意义的默认实参。

!!! note "默认实参也遵循两阶段查找"
    `ydef(T())` 是依赖调用，定义处找不到 `ydef` 没关系，实例化时再做 ADL（[[temp.dep.res]]）。若 `A` 所在命名空间里在调用点之前声明了 `ydef(A)`，`f(a)` 就合法了。

## 其他单独实例化的构造（¶16–¶17）

¶16 除上述情形外，模板化函数特化的单独实例化构造只在需要时实例化，典型的是 noexcept 说明符（[[except.spec]]）和函数契约说明符（[[dcl.contract.func]]，{{c++26}}）。实例化时，依赖名被查找、语义约束被检查、其中的模板被实例化，就像这是在那一点实例化特化的声明的一部分。

noexcept 说明符的延迟实例化有重要意义：类模板的成员函数上 `noexcept(noexcept(T(std::declval<T&&>())))` 这样的说明，如果随类一起实例化，会在 `T` 不完整或不可移动时过早出错。延迟到需要知道它是否 noexcept 时（例如被调用、被 `noexcept` 运算符查询、虚函数覆盖检查）才实例化，让 `std::vector<Incomplete>` 这类用法成为可能。

¶17（注 7）指出，实例化点由 [[temp.point]] 规定。

## 递归实例化与实现限制（¶18）

¶18 递归实例化的总深度有一个实现定义的上限（附录 [[implimits]] 建议至少 1024）；递归可能涉及多个模板。**无限递归实例化的结果是未定义的**（{{ub}}）。

```cpp error
template<class T> class X {
    X<T>* p;      // OK：指针不需要完整类型
    X<T*> a;      // 生成 X<T> 需要 X<T*>，它又需要 X<T**>，……
};
X<int> x;
```

Clang 报 "recursive template instantiation exceeded maximum depth of 1024"（可用 `-ftemplate-depth=N` 调整）。注意标准把这定为 UB，而不是非良构，因为一般而言无法判定递归是否终止（等价于停机问题），而且要求实现必须诊断，会把编译器绑定在特定的检测方式上。实践中所有编译器都会在达到上限时报错。

!!! tip "深递归的常见来源"
    - 递归的 `std::tuple`/类型列表实现，元素数上千时；
    - `constexpr` 递归函数模板（每层一个特化）；
    - 写错终止条件的部分特化。

    C++17 起用折叠表达式、C++26 起用包索引（`Ts...[I]`）和展开语句往往能把 O(N) 深度的递归改为 O(1) 深度。

## 约束不随特化实例化（¶19）

¶19 模板特化或成员函数的 *type-constraint* 和 *requires-clause* 不随特化或函数本身一起实例化（即使是局部类的成员函数）；对其原子约束的替换按 [[temp.constr.decl]] 和 [[temp.constr.atomic]]，在判断约束是否满足或比较声明时进行。注 8 指出，约束满足性在模板实参推导和重载决议时判断。

```cpp ok
template<typename T> concept C = sizeof(T) > 2;
template<typename T> concept D = C<T> && sizeof(T) > 4;

template<typename T> struct S {
    S() requires C<T> { }   // #1
    S() requires D<T> { }   // #2
};

S<char[8]> s2;              // OK：两者都满足，#2 约束更强，选 #2
```

```cpp error
template<typename T> concept C = sizeof(T) > 2;
template<typename T> concept D = C<T> && sizeof(T) > 4;
template<typename T> struct S {
    S() requires C<T> { }
    S() requires D<T> { }
};
S<char> s1;                 // error: 没有匹配的构造函数
```

`S<char>` 被实例化时两个构造函数都是它的成员（声明被实例化），但约束不满足。它们仍然抑制了隐式默认构造函数的声明（[[class.default.ctor]]），所以 `s1` 没有可行的构造函数。

例 12 展示了约束层面的 IFNDR：

```cpp ifndr
template<typename T> struct S1 {
    template<typename U>
        requires false
    struct Inner1;           // IFNDR：没有合法特化
};
template<typename T> struct S2 {
    template<typename U>
        requires (sizeof(T[-(int)sizeof(T)]) > 1)
    struct Inner2;           // IFNDR：对约束的任何替换都不会得到合法表达式
};
```

这是 [[temp.res#6]] 中不可能有合法特化的规则作用在约束上。

## 实现视角

!!! impl "实例化是怎么做的"
    - Clang 和 GCC 都把从模板到特化的过程实现为对 AST 的树变换（Clang 叫 `TreeTransform`/`TemplateInstantiator`）。类模板特化先实例化成员声明，成员函数定义被放入待实例化队列，在 TU 末尾（或需要常量求值时立即）处理。[[temp.point]] 允许 TU 末尾也作为实例化点，现实原因就在这里。
    - 因为在 TU 末尾才实例化函数体，许多函数模板体中的错误要到最后才报告，诊断中的 "in instantiation of ... requested here" 链会指向最初的使用点。
    - 每个 TU 独立实例化同一个特化，生成的代码以 COMDAT/弱符号输出，链接器去重。这就是模板代码膨胀与编译时间问题的根源，也是 [[temp.explicit]] 中 `extern template` 存在的理由。
    - 递归深度：Clang 默认 1024（`-ftemplate-depth`），GCC 也有对应的 `-ftemplate-depth=` 选项。constexpr 求值另有步数与深度上限（`-fconstexpr-steps`、`-fconstexpr-depth`）。

## 陷阱

!!! pitfall "能编译不等于所有成员都合法"
    类模板的成员函数只在被使用时才实例化。测试代码只用到 `push_back` 时，`resize` 中的错误永远不会被发现。写库时应该用显式实例化定义（`template class MyVec<SomeType>;`）在测试中强制实例化所有成员（[[temp.explicit#9]]）。

!!! pitfall "模板里的静态数据成员初始化可能根本不发生"
    见 ¶4 的自注册例子。需要副作用时，必须确保这个静态成员被 odr-use。

!!! pitfall "`decltype`/`sizeof` 并不总是不实例化"
    不求值操作数里的函数调用不会实例化函数体，除非需要函数体来确定类型（`auto` 返回类型），或者表达式是潜在常量求值的（¶8）。`decltype(f<T>())` 对 `auto f()` 会实例化 `f<T>` 的函数体，函数体里的错误是硬错误。

!!! pitfall "虚函数总是被实例化（实际上）"
    ¶12 说未指明，实践中几乎总是实例化。不要在类模板的虚函数里写只对部分 `T` 合法的代码。

## 思考题

!!! question "思考题 1"
    以下哪几行会导致 `Big<int>` 被隐式实例化？
    ```cpp
    template<class T> struct Big { T data[1000]; };
    Big<int>* a;                         // (1)
    Big<int>& f();                       // (2)
    auto g() -> Big<int>;                // (3)
    void h(Big<int>* p) { p = p + 1; }   // (4)
    bool b = std::is_class_v<Big<int>>;  // (5)
    ```

<details markdown="1">
<summary>答案</summary>

(1)(2)(3) 都不需要完整类型，其中 (3) 是函数声明，返回类型只在定义和调用处才需要完整。(4) 指针算术要求指向完整对象类型（[[expr.add]]），会实例化。(5) `std::is_class` 不要求完整类型，库实现通常用编译器内建（`__is_class`），不会实例化。不过标准只规定 trait 的结果，并不保证实现不实例化；对 `is_class` 而言这不影响结果。
</details>

!!! question "思考题 2"
    ```cpp
    template<class T> struct A {
        static constexpr int v = T::value;
        int arr[2];
    };
    int n = sizeof(A<int>);
    ```
    这段代码良构吗？

<details markdown="1">
<summary>答案</summary>

良构。`sizeof(A<int>)` 实例化类 `A<int>`。`static constexpr` 数据成员是内联变量，类内初始化器属于它的定义；而按 ¶3.1，类的实例化只生成静态数据成员的声明，所以 `T::value` 不会被替换。Clang 接受这段代码。若随后写 `A<int>::v`，就需要它的值，初始化器被实例化，报错。
</details>

!!! question "思考题 3"
    为什么 ¶13 规定非泛型 lambda 的函数体随外围函数实例化，而泛型 lambda 不是？

<details markdown="1">
<summary>答案</summary>

非泛型 lambda 的调用运算符是一个普通（非模板）成员函数；外围函数特化被实例化后，它就是一个具体的函数，此后再也没有模板实参来触发实例化，要么现在实例化，要么永远不实例化。泛型 lambda 的调用运算符本身是成员模板，它的函数体依赖于它自己的模板形参，自然可以等到被调用（推导出 `auto` 形参）时再实例化，适用 ¶12 的不得多实例化规则。注意此时函数体中只依赖外围 `T` 的错误可能被实现按 [[temp.res#6]] 提前诊断（Clang 会这样做），因为替换 `T` 后它们已是非依赖结构。
</details>

## 小结

| 规则 | 段落 | 要点 |
|---|---|---|
| 已声明的特化不隐式实例化 | ¶1 | `extern template` 对内联函数、推导类型、常量变量、类无此效果 |
| 类模板特化：需要完整类型或完整性影响语义时实例化 | ¶2 | 指针、引用、别名不触发；未定义的模板得到不完整类型 |
| 类实例化只生成成员声明 | ¶3 | 删除函数、无作用域枚举、匿名联合例外；对应定义的声明视同定义 |
| 成员、函数、变量：需要定义存在时实例化 | ¶4–¶7 | 静态数据成员不用就不初始化 |
| 为常量求值所需 / 为确定类型所需时实例化 | ¶8–¶9 | 即使不 odr-use、不实际常量求值 |
| 无需实例化即可完成重载决议 | ¶10 | 是否实例化 {{unspec}} |
| 实现不得多实例化 | ¶12 | 虚函数 {{unspec}}；默认实参/成员初始化器按需 |
| 局部类成员、非泛型 lambda 随外围实例化 | ¶13 | 不享受惰性 |
| 默认实参各自独立实例化 | ¶14–¶15 | 未使用的默认实参可以非良构 |
| noexcept、契约说明符按需实例化 | ¶16 | — |
| 递归深度实现定义；无限递归 | ¶18 | {{ub}} |
| 约束不随特化实例化 | ¶19 | 满足性在推导/重载决议时检查 |
