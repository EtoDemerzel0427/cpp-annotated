---
title: 模板声明
summary: 主模板与部分特化怎样区分；默认实参、noexcept、契约说明符和约束为什么按需单独实例化；constexpr if 与 template for 的循环体如何参与实例化；别名模板为什么不能特化。
status: done
covers: temp.decls.general
related: temp.class, temp.mem, temp.variadic, temp.friend, temp.spec.partial, temp.fct, temp.alias, temp.concept, temp.inst, temp.pre
tags: 模板, 主模板, 部分特化, 实例化
updated: 2026-10-19
---

!!! tldr
    - 模板名后面不跟实参列表的声明是主模板；跟着实参列表的是部分特化，只有类模板和变量模板可以部分特化。
    - 函数的默认实参、`noexcept` 说明符、契约说明符，以及约束，都算作各自独立的定义：用到时才实例化，出错也只在用到的地方报错。
    - constexpr if 的被丢弃分支不会随外围模板实例化，但它的非依赖部分仍在模板定义处检查。
    - `template for` 的循环体本身是一个模板定义，每次展开实例化一次。
    - 别名模板不能特化；需要按实参分派时，在类模板上特化，再用别名转发。

## 主模板与部分特化（¶2）

```cpp run ok
template<class T, class U> struct Pair { };          // 主模板：实参列表 <T, U>
template<class T> struct Pair<T, T> { };             // 部分特化：实参列表 <T, T>
template<class... Ts> struct Tup { };                // 主模板：实参列表 <Ts...>

template<class T> constexpr int rank = 0;            // 变量模板的主模板
template<class T> constexpr int rank<T*> = 1 + rank<T>;   // 变量模板的部分特化

static_assert(rank<int**> == 2);
int main() { Pair<int, int> p; (void)p; }
```

¶2 区分两种模板声明的依据很简单：看模板名后面有没有 *template-argument-list*。

- 没有实参列表的是**主模板**（[[g:primary-template|primary template]]）。它的模板实参列表就是它自己的形参：第 n 个实参就是第 n 个形参，形参包写成包展开（[[temp.arg#2]]）。上例中 `Pair` 的主模板相当于 `Pair<T, U>`。
- 有实参列表的是这个模板的**部分特化**（[[temp.spec.partial]]），被特化的必须是类模板或变量模板。

把主模板看成实参列表为 `<T, U>` 的特化，后面会反复用到。判断部分特化是否比主模板更特化时，就是拿部分特化的实参列表和它比较（[[temp.spec.partial#9.2]]）；部分特化的实参列表也不能与主模板的完全相同，否则等于什么都没有特化。

函数模板和别名模板都不能部分特化：

```cpp error
template<class T> void f(T);
template<class T> void f<T*>(T*);                    // error: 函数模板不能部分特化
template<class T> using Ptr = T*;
template<class T> using Ptr<T*> = T;                 // error: 别名模板不能特化（¶4）
```

函数模板不需要部分特化，因为重载加上函数模板的偏序（[[temp.func.order]]）已经能表达同样的意思：再写一个 `template<class T> void f(T*);` 重载即可。如果再引入部分特化，就有两套机制同时决定调用哪个函数，而特化本身并不参与重载决议，结果很难预料。需要按类型分派时，直接重载、用约束或 `if constexpr`，或者转发给一个可以部分特化的类模板。

## 默认实参、noexcept 与约束按需实例化（¶3）

```cpp run ok
struct NoValue { };

template<class T>
struct Box {
    void put(T t, int n = T::value);          // 默认实参：T = NoValue 时无效
    void swap(Box&) noexcept(T::nothrow);     // noexcept：T = NoValue 时无效
};
template<class T> void Box<T>::put(T, int) { }

int main() {
    Box<NoValue> b;          // OK: 不实例化默认实参和 noexcept
    b.put(NoValue{}, 42);    // OK: 没有用到默认实参
}
```

`NoValue` 既没有 `value` 也没有 `nothrow`，但这段代码是良构的。只有真正用到默认实参时才会出错：

```cpp error
struct NoValue { };
template<class T> struct Box { void put(T, int = T::value) { } };
int main() {
    Box<NoValue> b;
    b.put(NoValue{});        // error: 现在需要实例化默认实参 T::value
}
```

¶3 规定了背后的规则。模板化函数 F 的下面三样东西叫做 F 的**分别实例化的结构**（[[g:separately-instantiated-construct|separately instantiated construct]]）：

- ¶3.1 默认实参；
- ¶3.2 *noexcept-specifier*；
- ¶3.3 *function-contract-specifier*，即 C++26 的 `pre(...)`、`post(...)`（[[dcl.contract.func]]）。

!!! std
    For purposes of name lookup and instantiation, separately instantiated constructs, *type-constraint*s, and *requires-clause*s are considered definitions; each ... is a separate definition which is unrelated to the templated function definition ...

就名字查找和实例化而言，这些结构以及 *type-constraint*、*requires-clause* 都算作定义。每一个都是独立的定义，与函数定义无关，彼此之间也无关。由此得到三个结果：

1. 按需实例化。默认实参在调用用到它时才实例化，异常说明在需要时才实例化（[[temp.inst]]、[[except.spec#13]]），约束在检查满足性时才代入（[[temp.constr]]）。
2. 各自有实例化点（[[temp.point]]），依赖名的 ADL 从各自的实例化点进行。
3. 错误互相隔离。一个默认实参无效，只在省略了这个实参的调用处报错，不影响函数本身。

函数模板也一样，默认实参和函数体是两个定义：

```cpp run ok
template<class T> int def(T, int n = T::size) { return n; }
int main() { return def(1, 0); }   // OK: 第二个实参显式给出，T::size 从未实例化
```

如果默认实参算作函数定义的一部分，那么函数一旦被实例化，所有默认实参都得跟着实例化，即使每次调用都显式给出了实参。标准库依赖相反的行为，例如成员函数上的 `noexcept(std::is_nothrow_swappable_v<T>)`，在 `T` 不可交换时不能直接报错。

### constexpr if 与 template for

¶3 后两句把类似的待遇给了两种语句。

constexpr if 的子语句就实例化而言算作定义（[[stmt.if]]）。所以外围模板实例化时，被丢弃的那个分支不实例化：

```cpp run ok
#include <type_traits>
template<class T>
int size_of(T t) {
    if constexpr (std::is_pointer_v<T>)
        return sizeof(*t);    // T = int 时被丢弃，不实例化 *t
    else
        return sizeof(t);
}
int main() { int x = 0; return size_of(&x) - size_of(x); }
```

条文只说 for the purpose of instantiation，没有说名字查找。所以被丢弃分支里不依赖模板形参的错误，仍然在模板定义处诊断：

```cpp error
template<class T> void f() {
    if constexpr (false) {
        undeclared_name();   // error: 非依赖名，定义模板时就必须能找到
    }
}
```

在非模板函数里，`if constexpr` 的两个分支都会完整检查，被丢弃分支只是不参与返回类型推导，其中用到的实体也不算 odr-use。constexpr if 不是预处理器的 `#if`。

C++26 的展开语句 `template for`（[[stmt.expand]]）更进一步：它的复合语句就名字查找和实例化而言算作一个模板定义，每展开一次就实例化一次。所以即使外围函数不是模板，循环体里依赖展开变量的表达式在每次迭代中也可以有不同的类型：

```cpp run ok
#include <tuple>
#include <cstdio>
int main() {
    auto t = std::tuple{1, 2.5, 'c'};
    template for (auto e : t) {             // C++26；循环体必须是复合语句
        std::printf("%zu ", sizeof(e));     // e 依次是 int、double、char
    }
}
```

## 别名模板不能特化（¶4）

¶4 *alias-declaration* 的语法里不能写 *template-id*，`using Name<Args> = ...` 不是合法的声明，所以别名模板既不能部分特化，也不能显式特化。别名模板只做类型替换（[[temp.alias]]），不能按实参选择不同的定义。

需要按实参分派时，把特化放在类模板上，别名只负责转发：

```cpp run ok
#include <type_traits>
template<class T> struct remove_ptr_impl       { using type = T; };
template<class T> struct remove_ptr_impl<T*>   { using type = T; };   // 在类模板上特化
template<class T> using remove_ptr = typename remove_ptr_impl<T>::type;   // 别名只负责转发

static_assert(std::is_same_v<remove_ptr<int*>, int>);
int main() { }
```

标准库的 `std::xxx_t` 别名都定义成 `typename std::xxx<T>::type`，就是这个原因。

## 本节的其余小节

¶1 只说明一件事：模板的模板形参就是紧跟在关键字 `template` 之后、尖括号里的那个列表。成员模板在类外定义时会有多层 `template<...>`，每一层的形参属于对应的那一层模板（[[temp.mem#1]]）。

13.7 的其余小节按声明的种类分别规定细节：类模板及其成员的类外定义 [[temp.class]]，成员模板 [[temp.mem]]，变参模板 [[temp.variadic]]，友元 [[temp.friend]]，部分特化 [[temp.spec.partial]]，函数模板 [[temp.fct]]，别名模板 [[temp.alias]]，概念 [[temp.concept]]。

## 常见误解

!!! pitfall "`template<> void f<int*>(int*)` 是部分特化"
    这是显式特化，也就是全特化，它不引入新的模板。部分特化的实参列表里还含有模板形参，只有类模板和变量模板才有。

!!! pitfall "实例化 `Box<X>` 会实例化它的所有成员"
    类模板的隐式实例化只实例化成员的声明（[[temp.inst]]），而且声明里的默认实参、`noexcept`、约束也不实例化。成员函数的定义、默认实参、异常说明都按需实例化。

!!! pitfall "constexpr if 的假分支不会被编译"
    它不会被实例化，但模板定义时仍然要解析，非依赖的部分照常检查。

## 思考题

!!! question "思考题 1"
    下面的程序良构吗？

    ```cpp
    template<class T> struct S {
        void f() noexcept(sizeof(T) > 4);
    };
    struct Incomplete;
    S<Incomplete> s;
    ```

<details markdown="1">
<summary>答案</summary>

良构。实例化 `S<Incomplete>` 只实例化 `f` 的声明，而 *noexcept-specifier* 是分别实例化的结构（¶3.2），只有需要异常说明时（调用 `f`、取它的地址、定义它等，[[except.spec#13]]）才实例化。这里从没需要过，所以 `sizeof(Incomplete)` 从未求值。如果后面写 `s.f();`，就会在那时实例化 `noexcept` 并报错。
</details>

!!! question "思考题 2"
    标准说每个分别实例化的结构与其他分别实例化的结构无关。举一个例子说明这会产生可观察的差别。

<details markdown="1">
<summary>答案</summary>

设函数模板有两个默认实参 `int a = T::x, int b = T::y`。调用时给出 `a`、省略 `b`，只有 `T::y` 被实例化，`T::x` 即使无效也不会报错。如果所有默认实参算一个整体，用到其中一个就得全部实例化。

另一个差别是实例化点：每个默认实参的实例化点与函数定义的可以不同，两者之间声明的重载可能被 ADL 找到。如果因此导致含义不同，程序是非良构、不要求诊断的（[[temp.point]]）。
</details>
