---
title: 别名模板
summary: 别名模板是一族类型的名字；其特化等价于代入后的类型（透明），因此不能通过别名模板推导模板模板实参，也不能特化；依赖的别名特化仍要做代入（void_t 惯用法的基础）；别名不能直接或间接引用自身；别名中的 lambda 每次实例化类型不同；C++26 中反射对别名特化的特殊处理
status: done
covers: temp.alias
since: c++11
papers: N2258, P1814R0
related: temp.decls, dcl.typedef, dcl.pre, temp.deduct.type, temp.spec.partial, over.match.class.deduct, dcl.type.class.deduct, temp.arg.template, expr.reflect
tags: 模板, 别名模板, using, void_t, SFINAE
updated: 2026-10-18
---

**别名模板**（alias template）是 C++11 引入的 `template<class T> using Name = ...;`。它填补了 C++03 的一个空白：`typedef` 不能带模板参数，人们只能写 `typename MyAlloc<T>::type` 这种"在类模板里套一个 typedef"的冗长写法。

别名模板最重要的性质是**透明**：`Vec<int>` 不是一个"新类型"，它**就是**代入后的那个类型。这一条性质推出了本节的几乎所有规则：不能特化、不能被推导、错误在代入时发生。

---

## 声明（¶1）

¶1 *declaration* 为 *alias-declaration*（[[dcl.pre]]）的 *template-declaration* 把其中的标识符声明为[[g:alias-template|**别名模板**]]。别名模板是**一族类型的名字**；别名模板的名字是一个 *simple-template-name*。

```cpp run ok
#include <memory>
#include <type_traits>
#include <vector>
template<class T> struct Alloc : std::allocator<T> { };

template<class T> using Vec = std::vector<T, Alloc<T>>;     // 别名模板
template<class T> using Ptr = T*;                           // 可以是任意类型，不必是类模板特化
template<class T, int N> using Arr = T[N];

Vec<int> v;                     // 与 std::vector<int, Alloc<int>> v; 完全相同
static_assert(std::is_same_v<Ptr<int>, int*>);
static_assert(sizeof(Arr<char, 4>) == 4);
int main() { }
```

别名模板与 `typedef` 的关系，就像函数模板与函数：它是"带参数的 typedef"。但别名模板不是类模板——它不定义任何新实体，只是给"代入后的类型"一个名字。

## 透明性：特化等价于代入后的类型（¶2）

¶2 下列两种形式，若指称别名模板的特化，则**等价于**把模板实参代入别名模板的 *defining-type-id* 所得的关联类型：

- ¶2.1 不是 *reflect-expression* 操作数的 *template-id*；
- ¶2.2 *splice-specialization-specifier*（{{c++26}}，[[basic.splice]]）。

**其他**指名别名模板特化的 *template-id*——也就是作为 `^^` 操作数的那种——是一个类型别名的 *typedef-name*；若构成其关联类型时发生代入失败，这样的 *template-id* 非良构。注 1：别名模板名**不会**从这样的类型中被推导出来（[[temp.deduct.type]]）。

先看普通情形（¶2.1），标准例 1：

```cpp error
#include <memory>
#include <vector>
template<class T> struct Alloc : std::allocator<T> { };
template<class T> using Vec = std::vector<T, Alloc<T>>;
Vec<int> v;                                     // 等同于 std::vector<int, Alloc<int>> v;

template<class T> void process(Vec<T>&) { }
template<class T> void process(std::vector<T, Alloc<T>>&) { }    // error: 重定义——两者是同一个函数模板

template<template<class> class TT> void f(TT<int>);
template<template<class, class> class TT> void g(TT<int, Alloc<int>>);

void test() {
    f(v);                                       // error: 不能推导出 TT = Vec
    g(v);                                       // OK: TT = std::vector
}
```

逐条解读：

1. **`process` 重定义**：`Vec<T>` 等价于 `std::vector<T, Alloc<T>>`（作为依赖类型，这是**结构上**的等价），所以两个声明的函数参数类型相同、*template-head* 等价，是同一个函数模板的两个定义。别名不产生新类型，自然不能用来重载。
2. **`f(v)` 失败**：`v` 的类型是 `std::vector<int, Alloc<int>>`，类型本身不"记得"它是通过 `Vec` 写出来的。推导 `TT<int>` 时，编译器只看到一个有**两个**实参的 `std::vector` 特化，无法匹配只有一个实参的 `TT<int>`。注 1 正是这个意思：别名模板名永远不会从类型中被推导出来。
3. **`g(v)` 成功**：`TT<int, Alloc<int>>` 与 `std::vector<int, Alloc<int>>` 结构匹配，`TT = std::vector`。

透明性还意味着：**通过别名推导模板参数**是可以的（与"推导出别名本身"不同）——因为代入后别名就消失了，留下的就是普通的 P：

```cpp run ok
#include <type_traits>
template<class T> using Id = T;
template<class T> int deduce(Id<T>) { return 1; }            // Id<T> 就是 T：可推导

template<class T> struct identity { using type = T; };
template<class T> using NoDeduce = typename identity<T>::type;   // 等于 C++20 的 std::type_identity_t
template<class T> int no_deduce(T, NoDeduce<T>) { return 2; }   // 第二个参数是非推导语境

int main() {
    // no_deduce(1, 2.0) 中 T 只从第一个实参推导为 int，第二个实参转换为 int —— 不会冲突
    return deduce(1) + no_deduce(1, 2.0) - 3;
}
```

`NoDeduce<T>` 代入后是 `typename identity<T>::type`——*nested-name-specifier* 中的 `T` 是非推导语境（[[temp.deduct.type]]）。这个技巧（`std::type_identity_t`）专门用于"阻止某个参数参与推导"。

!!! note "¶2 中的反射例外 {{c++26}}"
    C++26 的静态反射需要区分 `Vec<int>` 这个**别名**与它代入后的类型 `std::vector<int, Alloc<int>>`：`^^Vec<int>` 应当反射一个"类型别名"（可以查询它是别名、取出它的名字），而不是直接反射底层类型。所以 ¶2 把作为 *reflect-expression* 操作数的 *template-id* 排除在"等价于代入后类型"之外，让它成为一个类型别名的 *typedef-name*（[[expr.reflect]]）。反过来，*splice-specialization-specifier*（拼接出别名模板再加实参）回到普通的透明语义。截至写作时，本机 Clang 23 不支持静态反射，无法验证这部分。

## 依赖的别名特化仍要代入（¶3）

¶3 然而，若 *template-id* 是**依赖的**，后续的模板实参代入仍然作用于该 *template-id*。

```cpp error
template<typename...> using void_t = void;
template<typename T> void_t<typename T::foo> f();
void test() {
    f<int>();          // error: int 没有嵌套类型 foo
}
```

为什么需要这一段？按 ¶2，`void_t<typename T::foo>` "等价于" `void`——如果实现**立刻**把它替换成 `void`，签名中就丢掉了 `typename T::foo`，代入 `T = int` 时不会失败，`f<int>()` 将被接受。¶3 规定：只要 *template-id* 是依赖的，代入就要作用于**原样**的 *template-id*，因此 `typename int::foo` 的代入失败会被发现。在函数模板的签名中，这就是 SFINAE：

```cpp run ok
#include <type_traits>
template<typename...> using void_t = void;

template<class T> void_t<typename T::foo> f(int) { }     // 只对有 T::foo 的类型可行
template<class T> void f(long) { }                       // 后备

struct HasFoo { using foo = int; };
int main() {
    f<HasFoo>(0);      // 选第一个
    f<int>(0);         // 第一个代入失败（SFINAE）→ 选第二个
}
```

!!! history "CWG1558：未使用的实参"
    C++11 原文没有 ¶3。当 `void_t` 这样的别名**不使用**它的某些模板实参时，"这些实参是否参与代入（从而是否可能导致 SFINAE）"是不明确的，不同编译器表现不同。[[CWG1558]] 通过加入 ¶3 解决了这个问题：依赖的别名特化中，所有实参都要代入，未使用的实参也一样。这正是 `std::void_t`（C++17）及检测惯用法能够可移植地工作的依据。在 CWG1558 之前，可移植的实现要写成 `template<class...> struct make_void { using type = void; }; template<class... Ts> using void_t = typename make_void<Ts...>::type;`——经过一个类模板，确保实参被"使用"。

## 不能引用自身（¶4）

¶4 别名模板声明中的 *defining-type-id* **不能引用正在声明的别名模板**。别名模板特化产生的类型**不能直接或间接**使用该特化本身。

```cpp error
template<class T> using Self = Self<T*>;         // error: defining-type-id 引用了正在声明的 Self

template<class T> struct A;
template<class T> using B = typename A<T>::U;
template<class T> struct A {
    typedef B<T> U;
};
B<short> b;                                      // error: B<short> 经由 A<short>::U 使用了自身
```

第一种是直接的：在 *defining-type-id* 处，`Self` 还不是可用的别名（不像类模板，在类体中名字已经声明）。第二种是间接的：`B<short>` → `A<short>::U` → `B<short>`，形成循环。别名是透明的"展开"，不能像类模板那样借助"不完整类型"打破递归——递归的类型结构（链表、树）必须经过类模板。

## 别名模板中的 lambda（¶5）

¶5 出现在别名模板声明中的 *lambda-expression*，其类型在该模板的**不同实例化之间不同**，即使 lambda 表达式不依赖于模板形参。

```cpp run ok
#include <type_traits>
template<class T>
using A = decltype([] { });                     // A<int> 与 A<char> 是不同的闭包类型
static_assert(!std::is_same_v<A<int>, A<char>>);
int main() { }
```

为什么要明确规定？因为这个 lambda 不依赖于 `T`，若把别名当作纯粹的"文本替换"，可以认为所有特化共享一个 lambda；也可以认为每次代入都生成新的 lambda。标准选择"每个实例化一个"，与函数模板中 lambda 的行为（每个特化一个闭包类型）一致。

!!! lawyer "同一个特化写两次呢？"
    ¶5 只说"不同实例化之间不同"。`A<int>` 写两次是否得到同一个类型，标准措辞没有直接回答。本机 Clang 23 中 `std::is_same_v<A<int>, A<int>>` 为 **false**——它把每次使用都当作一次新的代入。不要依赖这类行为；在签名中使用含 lambda 的别名尤其危险（[[temp.over.link#5]]：lambda 永不等价）。

## 别名模板与推导：CTAD（C++20）

¶2 注 1 说"别名模板名不会被推导"，但 C++20 为**类模板实参推导**开了一个特例：可以对别名模板做 CTAD（[[P1814R0]]），前提是别名模板的 *defining-type-id* 形如一个（可推导的）类模板的 *simple-template-id*（[[dcl.type.class.deduct]]）：

```cpp run ok
#include <memory>
#include <type_traits>
#include <vector>
template<class T> struct Alloc : std::allocator<T> { };
template<class T> using Vec = std::vector<T, Alloc<T>>;

Vec w{1, 2, 3};                   // C++20：对别名模板做 CTAD
static_assert(std::is_same_v<decltype(w), std::vector<int, Alloc<int>>>);
int main() { }
```

实现方式（[[over.match.class.deduct]]）：从底层类模板的推导指引出发，把别名的 *defining-type-id* 与指引的返回类型做推导，生成别名专属的推导指引。这不违反注 1——推导的是**别名模板的模板形参**（`T`），而不是从一个已有类型中"推导出别名模板名"。

## 不能特化

别名模板不能部分特化或显式特化（[[temp.decls#4]]）：*alias-declaration* 的语法里没有 *template-id*。需要"按类型选择"时，把特化放在类模板上，用别名转发：

```cpp run ok
#include <type_traits>
template<class T> struct add_ptr_impl      { using type = T*; };
template<class T> struct add_ptr_impl<T&>  { using type = T*; };   // 特化在类模板上
template<class T> using add_ptr = typename add_ptr_impl<T>::type;

static_assert(std::is_same_v<add_ptr<int&>, int*>);
int main() { }
```

---

## 实现视角

!!! impl "实现视角"
    - **mangling**：别名在 mangled 名中**不出现**，签名中的 `Vec<T>` 按代入后的 `std::vector<T, Alloc<T>>` 编码——这就是 ¶2 的"透明"在 ABI 层面的体现。依赖的别名特化若有未使用的实参（`void_t<typename T::foo>`），出现在函数模板签名中时，实现需要保留足以区分声明的信息；具体如何编码依实现而定。
    - **诊断**：编译器通常在错误信息中保留别名的写法（"`Vec<int>` (aka `std::vector<int, Alloc<int>>`)"），这只是诊断层面的便利，不影响语义。
    - **编译开销**：别名模板不需要实例化类，代入比"类模板 + `::type`"便宜；这是 C++14 起标准库全面提供 `_t` 别名的原因之一。

## 历史与演进

!!! history "历史与演进"
    - **C++11**：别名模板（[[N2258]]）。
    - **C++14**：[[CWG1558]] 明确依赖别名特化中未使用的实参也要代入（¶3）；标准库提供 `std::xxx_t` 别名。
    - **C++17**：`std::void_t`。
    - **C++20**：别名模板的 CTAD（[[P1814R0]]）；不求值语境中允许 lambda，于是需要 ¶5 规定别名中 lambda 的类型。
    - **C++26**：静态反射——`^^` 的操作数中的别名特化不再透明（¶2）。

## 陷阱

!!! pitfall "常见误解"
    - "`Vec<T>` 和 `std::vector<T, Alloc<T>>` 可以用来重载"——它们是同一个类型。
    - "可以把别名模板传给 `template<template<class> class TT>` 形参，然后从 `std::vector<int, Alloc<int>>` 推导出它"——可以**显式**传别名模板作模板模板实参，但不能从一个类型**推导**出别名模板。
    - "别名会立即折叠，所以 `void_t<typename T::foo>` 就是 `void`"——依赖的别名特化仍要代入（¶3）。
    - "别名模板可以特化"——不能，用类模板中转。

## 思考题

!!! question "思考题 1"
    下面的调用能否推导？为什么？

    ```cpp
    template<class T> using P = T*;
    template<class T> void f(P<T>);
    int x;
    f(&x);
    ```

<details markdown="1">
<summary>答案</summary>

能，`T = int`。`P<T>` 是依赖的别名特化，等价于 `T*`，所以 `f` 的参数类型就是 `T*`，从 `int*` 推导出 `T = int`。"别名不能被推导"说的是**别名模板名**（例如推导模板模板形参 `TT = P`）不能被推导；透过别名推导别名的**实参**是没问题的——前提是代入后 `T` 仍处于可推导位置（对比 `type_identity_t<T>`）。
</details>

!!! question "思考题 2"
    为什么 CWG1558 之前要把 `void_t` 写成经过 `make_void` 类模板的形式？在 ¶3 之下，下面两种写法有区别吗？

    ```cpp
    template<class...> using void_t1 = void;
    template<class... Ts> struct make_void { using type = void; };
    template<class... Ts> using void_t2 = typename make_void<Ts...>::type;
    ```

<details markdown="1">
<summary>答案</summary>

C++11 的措辞允许实现把 `void_t1<typename T::foo>` 立即替换为 `void`，丢弃从未被使用的实参，于是 `typename T::foo` 的代入失败不会发生，SFINAE 失效。`void_t2` 把实参传进 `make_void<Ts...>`，*defining-type-id* 中**使用**了它们，代入必然发生。¶3 加入后，两者在依赖语境中行为相同：依赖的 *template-id* 的实参总是被代入。区别只剩下 `void_t2` 多实例化了一个类模板。
</details>

!!! summary "小结"
    - 别名模板 = 带参数的 typedef；特化**等价于**代入后的类型（透明）。
    - 透明的推论：不能用别名重载、不能从类型推导出别名模板名、不能特化别名模板。
    - 但依赖的别名特化仍要做代入，未使用的实参也要（CWG1558，`void_t` 的基础）。
    - 不能直接或间接引用自身；递归结构必须经过类模板。
    - 别名中的 lambda 每个实例化一个类型。
    - C++20 起可以对别名模板做 CTAD；C++26 中 `^^Alias<Args>` 反射的是别名本身。
