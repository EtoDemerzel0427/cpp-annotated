---
title: 模板声明
summary: 13.7 总览：主模板与部分特化的区分；分别实例化的结构（默认实参、noexcept、契约说明符）以及 type-constraint、requires-clause、constexpr if 子语句、expansion statement 的函数体为何被当作独立的定义；别名模板为何不能特化
status: done
covers: temp.decls.general
related: temp.class, temp.mem, temp.variadic, temp.friend, temp.spec.partial, temp.fct, temp.alias, temp.concept, temp.inst, temp.pre
tags: 模板, 主模板, 部分特化, 实例化
updated: 2026-10-17
---

13.7 [temp.decls] 是模板能声明成哪些东西的总目录。[[temp.pre]] 讲了模板声明的一般语法（*template-head* + *declaration*），[[temp.param]] 讲了模板形参，[[temp.names]]/[[temp.arg]] 讲了怎么使用模板；本节则按被模板化的声明种类逐一规定细节：

| 小节 | 内容 | 本站笔记 |
|---|---|---|
| 13.7.1 [temp.decls.general] | 主模板 vs 部分特化；分别实例化的结构 | 本页 |
| 13.7.2 [temp.class] | 类模板，类外定义成员函数/成员类/静态成员/枚举，推导指引 | [[temp.class]] |
| 13.7.3 [temp.mem] | 成员模板（不能是虚函数、析构函数） | [[temp.mem]] |
| 13.7.4 [temp.variadic] | 变参模板：包、包展开、折叠、包索引 | [[temp.variadic]] |
| 13.7.5 [temp.friend] | 模板中的友元 | [[temp.friend]] |
| 13.7.6 [temp.spec.partial] | 部分特化：匹配与偏序 | [[temp.spec.partial]] |
| 13.7.7 [temp.fct] | 函数模板：重载与等价、偏序 | [[temp.fct]]、[[temp.func.order]] |
| 13.7.8 [temp.alias] | 别名模板 | [[temp.alias]] |
| 13.7.9 [temp.concept] | 概念定义 | [[temp.concept]] |

本页只覆盖 13.7.1 的四段，它们给出后面各小节共用的定义。

---

## 模板形参在哪里（¶1）

¶1 模板的模板形参就是紧跟在关键字 `template` 之后、用尖括号括起来的那个列表。这句话看似多余，实际上规定了 *template-head* 中的 *template-parameter-list* 属于哪个模板：成员模板的类外定义会出现多个 `template<...>` 前缀（`template<class T> template<class U> ...`），每个前缀的形参属于它所对应的那一层模板（见 [[temp.mem#1]]）。

## 主模板与部分特化（¶2）

¶2 区分两种模板声明：

- [[g:primary-template|**主模板**]]（primary template）：模板名后面不跟 *template-argument-list*。主模板的模板实参列表就是它的 *template-head* 的模板实参列表（[[temp.arg#2]]）：第 n 个实参就是第 n 个形参本身，形参包则写成包展开。
- 模板名后面跟着 *template-argument-list* 的模板声明是该模板的**部分特化**（[[temp.spec.partial]]），被特化的必须是类模板或变量模板。

```cpp run ok
template<class T, class U> struct Pair { };          // 主模板：实参列表 <T, U>
template<class T> struct Pair<T, T> { };             // 部分特化：实参列表 <T, T>
template<class... Ts> struct Tup { };                // 主模板：实参列表 <Ts...>

template<class T> constexpr int rank = 0;            // 变量模板的主模板
template<class T> constexpr int rank<T*> = 1 + rank<T>;   // 变量模板的部分特化

static_assert(rank<int**> == 2);
int main() { Pair<int, int> p; (void)p; }
```

主模板的实参列表就是它自己的形参，这一观点在后面反复用到：

- 判断部分特化是否比主模板更特化（[[temp.spec.partial#9.2]]）时，把主模板看作实参列表为 `<T, U>` 的特化；
- 部分特化的实参列表不能与主模板的实参列表完全相同，否则等于没有特化（这正是 ¶9.2 的要求）。

函数模板没有部分特化：

```cpp error
template<class T> void f(T);
template<class T> void f<T*>(T*);                    // error: 函数模板不能部分特化
template<class T> using Ptr = T*;
template<class T> using Ptr<T*> = T;                 // error: 别名模板不能特化（¶4）
```

为什么函数模板没有部分特化？因为函数模板已经有重载，以及按更特化程度挑选重载的偏序（[[temp.func.order]]），二者组合起来就能表达部分特化想表达的东西；再引入部分特化，会让重载和特化两套机制纠缠在一起（经典的 Dimov/Abrahams 问题：显式特化不参与重载决议）。需要让函数按类型分派时，惯用法是转发给一个类模板的静态成员函数，在类模板上做部分特化，或者直接重载、用 `if constexpr` / 约束。

## 分别实例化的结构（¶3）

¶3 定义了一个新术语：模板化函数 F 的[[g:separately-instantiated-construct|**分别实例化的结构**]]（separately instantiated construct）是 F 的

- ¶3.1 默认实参；
- ¶3.2 *noexcept-specifier*；
- ¶3.3 *function-contract-specifier*（`pre(...)` / `post(...)`，{{c++26}}，[[dcl.contract.func]]）。

!!! std
    For purposes of name lookup and instantiation, separately instantiated constructs, *type-constraint*s, and *requires-clause*s are considered definitions; each ... is a separate definition which is unrelated to the templated function definition ...

就名字查找与实例化而言，这些结构以及 *type-constraint*、*requires-clause* 都算作定义，而且**各自是一个独立的定义**，与函数定义本身无关，彼此之间也无关。

这句话有三个后果：

1. 按需实例化：实例化一个类模板特化时，其成员函数的默认实参、`noexcept` 说明符不随之实例化，只在真正需要时才实例化（[[temp.inst]]：默认实参在调用用到它时实例化；异常说明在需要时实例化，[[except.spec#13]]）。
2. 独立的实例化点：每个这样的定义有自己的实例化点（[[temp.point]]），依赖名从各自的实例化点做 ADL。
3. 错误相互隔离：一个默认实参实例化失败，只会在用到它的调用处报错，不影响函数本身的使用。

```cpp run ok
struct NoValue { };

template<class T>
struct Box {
    void put(T t, int n = T::value);          // 默认实参：T = NoValue 时无效
    void swap(Box&) noexcept(T::nothrow);     // noexcept：T = NoValue 时无效
};
template<class T> void Box<T>::put(T, int) { }

int main() {
    Box<NoValue> b;          // OK: 实例化 Box<NoValue> 不实例化默认实参和 noexcept
    b.put(NoValue{}, 42);    // OK: 没有用到默认实参
}
```

```cpp error
struct NoValue { };
template<class T> struct Box { void put(T t, int n = T::value) { } };
int main() {
    Box<NoValue> b;
    b.put(NoValue{});        // error: 现在需要实例化默认实参 T::value
}
```

函数模板也一样，默认实参与函数体是不同的定义：

```cpp run ok
template<class T> int def(T, int n = T::size) { return n; }
int main() { return def(1, 0); }   // OK: 第二个实参显式给出，T::size 从未实例化
```

!!! note "为什么要把它们当成定义"
    定义这个身份决定了两件事：名字查找按定义的上下文进行，实例化按定义的粒度进行。如果把默认实参看成函数定义的一部分，那么只要函数被实例化（比如被调用一次），所有默认实参就都要实例化，即使调用时都显式给出了实参。标准库大量依赖相反的行为（例如成员函数的 `noexcept(is_nothrow_swappable_v<T>)` 对不可交换的 `T` 不能硬报错）。

*type-constraint* 与 *requires-clause* 同样被当作独立定义：约束在检查满足性时才（以替换的方式）实例化，并不随函数模板或类模板特化的实例化而实例化。这与 [[temp.constr.decl]]、[[temp.inst]] 中约束在需要检查时才代入的规则一致。

### constexpr if 与 expansion statement

¶3 后两句把同样的定义身份扩展到两种语句：

- constexpr if 的子语句：就实例化而言算作定义。于是被丢弃的分支（discarded statement）在实例化外围模板时不会被实例化（[[stmt.if]]）。注意原文只说 "for the purpose of instantiation"，不包括名字查找，所以被丢弃分支中的非依赖构造仍在模板定义处检查。
- expansion statement 的 *compound-statement*（`template for` 的循环体，{{c++26}}，[[stmt.expand]]）：就名字查找与实例化而言算作**模板定义**。每次展开都是对这个模板的一次实例化，所以即使外围函数本身不是模板，循环体中依赖于展开变量的名字也可以在每次迭代中有不同的类型和含义。

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

```cpp run ok
#include <tuple>
#include <cstdio>
int main() {
    auto t = std::tuple{1, 2.5, 'c'};
    template for (auto e : t) {             // C++26 expansion statement；循环体必须是复合语句
        std::printf("%zu ", sizeof(e));     // 每次迭代 e 的类型不同：int, double, char
    }
}
```

!!! lawyer "被丢弃的分支仍然要过第一阶段检查"
    算作定义只关乎实例化。被丢弃分支里非依赖的错误仍然会被诊断（或者使程序 IFNDR，[[temp.res.general#6]]）：

    ```cpp
    template<class T> void f() {
        if constexpr (false) {
            undeclared_name();   // error: 非依赖名，在模板定义时就必须能找到
        }
    }
    ```

    而在非模板函数中，`if constexpr` 的被丢弃分支会被完整地检查（只是 return 语句不参与返回类型推导，odr-use 不计）。constexpr if 不是预处理器的 `#if`。

## 别名模板不能被特化（¶4）

¶4 *alias-declaration* 的语法里不能出现 *template-id*（`using Name<Args> = ...` 不是合法的写法），因此别名模板**既不能部分特化，也不能显式特化**。这条结论可以从文法推出，标准把它写出来，是提醒读者别名模板只是纯粹的类型替换，不能按实参选择不同的定义。需要特化行为时，让别名指向一个可以特化的类模板的成员类型：

```cpp run ok
#include <type_traits>
template<class T> struct remove_ptr_impl       { using type = T; };
template<class T> struct remove_ptr_impl<T*>   { using type = T; };   // 在类模板上特化
template<class T> using remove_ptr = typename remove_ptr_impl<T>::type;   // 别名只负责转发

static_assert(std::is_same_v<remove_ptr<int*>, int>);
int main() { }
```

这正是标准库 `xxx_t` 别名都写成 `typename xxx<T>::type` 的原因。别名模板的完整规则见 [[temp.alias]]。

---

!!! pitfall "常见误解"
    - 误以为显式特化 `template<> void f<int*>(int*)` 就是函数模板的部分特化。显式特化是全特化，不引入新的模板；部分特化（模板名后跟含有模板形参的实参列表）只对类模板和变量模板存在。
    - 误以为实例化了 `Box<X>` 就实例化了它的所有成员。隐式实例化只实例化成员的声明（[[temp.inst]]），而且声明中的默认实参、`noexcept`、约束也不实例化；成员函数的定义、默认实参、异常说明都按需实例化。
    - 误以为 constexpr if 的假分支不会被编译。它不会被实例化，但在模板定义时仍然会被解析，并接受第一阶段检查。

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

良构。实例化 `S<Incomplete>` 只实例化 `f` 的声明；`noexcept-specifier` 是分别实例化的结构（¶3.2），只有在需要异常说明时（调用 `f`、取地址、定义 `f` 等，[[except.spec#13]]）才实例化。这里从未需要，所以 `sizeof(Incomplete)` 从未被求值。如果后面写 `s.f();`，则在那时实例化 `noexcept` 并报错（`Incomplete` 不完整）。
</details>

!!! question "思考题 2"
    为什么标准要强调分别实例化的结构与函数定义无关，彼此之间也无关？举一个例子，说明彼此无关会产生可观察的差异。

<details markdown="1">
<summary>答案</summary>

彼此无关意味着每个结构各有实例化点，各自按需实例化。例如函数模板有两个默认实参 `int a = T::x, int b = T::y`：调用时给出 `a` 而省略 `b`，只有 `T::y` 被实例化；`T::x` 即使无效也不会报错。如果所有默认实参被当作一个整体，那么只要用到其中之一就必须全部实例化。另一个差异是实例化点：默认实参的实例化点与函数定义的实例化点可以不同，在它们之间声明的重载可能被 ADL 找到（但若导致不同含义则是 IFNDR，[[temp.point]]）。
</details>

!!! summary "小结"
    - 模板名后不跟实参列表 = 主模板；跟着实参列表 = 部分特化（仅类模板和变量模板）。函数模板用重载 + 偏序代替部分特化。
    - 默认实参、`noexcept`、契约说明符（统称分别实例化的结构）以及 *type-constraint*、*requires-clause* 都是独立的定义：按需实例化、各自有实例化点、错误互相隔离。
    - constexpr if 的子语句就实例化而言是独立定义（被丢弃分支不实例化）；`template for` 的循环体是一个模板定义（{{c++26}}）。
    - 别名模板不能被特化；需要时把特化放到类模板上，用别名转发。
