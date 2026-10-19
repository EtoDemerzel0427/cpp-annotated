---
title: 别名模板
summary: 别名模板是一族类型的名字，它的特化就是代入后的那个类型；由此推出别名不能用来重载、不能被推导出来、不能特化，而依赖的别名特化仍要逐个代入实参。
status: done
covers: temp.alias
since: c++11
papers: N2258, P1814R0
related: temp.decls, dcl.typedef, dcl.pre, temp.deduct.type, temp.spec.partial, over.match.class.deduct, dcl.type.class.deduct, temp.arg.template, expr.reflect
tags: 模板, 别名模板, using, void_t, SFINAE
updated: 2026-10-19
---

!!! tldr
    - `template<class T> using Vec = std::vector<T, Alloc<T>>;` 中，`Vec<int>` 就是 `std::vector<int, Alloc<int>>`，不是一个新类型。
    - 因此不能用别名区分重载，也不能从一个类型推导出别名模板本身；但透过别名推导它的实参是可以的。
    - 别名模板不能特化。需要按类型选择时，把特化写在类模板上，再用别名转发。
    - 依赖的别名特化（如 `void_t<typename T::foo>`）仍要代入全部实参，没被用到的实参也一样，这是 `void_t` 检测惯用法的基础。
    - 别名不能直接或间接引用自身；别名里的 lambda 在每个实例化中都是不同的类型。

## 声明（¶1）

```cpp run ok
#include <memory>
#include <type_traits>
#include <vector>
template<class T> struct Alloc : std::allocator<T> { };

template<class T> using Vec = std::vector<T, Alloc<T>>;
template<class T> using Ptr = T*;            // 不必是类模板特化
template<class T, int N> using Arr = T[N];

Vec<int> v;                                  // 就是 std::vector<int, Alloc<int>> v;
static_assert(std::is_same_v<Ptr<int>, int*>);
static_assert(sizeof(Arr<char, 4>) == 4);
int main() {}
```

¶1 声明部分是别名声明（`using 名字 = 类型;`，[[dcl.pre]]）的模板声明，声明一个[[g:alias-template|**别名模板**]]（alias template）。别名模板是一族类型的名字。

C++03 的 `typedef` 不能带模板形参，只能写成类模板里套一个 typedef，使用时写 `typename MyAlloc<T>::type`。别名模板就是带形参的 typedef：它不定义任何新实体，只是给代入后的类型起一个名字。

## 别名是透明的（¶2）

¶2 一个指称别名模板特化的 *template-id*，例如 `Vec<int>`，等价于把模板实参代入别名的定义（`=` 右边的 *defining-type-id*）后得到的类型。拼接得到的特化也一样（*splice-specialization-specifier*，{{c++26}}，[[basic.splice]]）。唯一的例外是作为反射运算符 `^^` 操作数的 *template-id*，见本节末尾。

注 1 指出一个推论：别名模板的名字不会从这样的类型中被推导出来（[[temp.deduct.type]]）。

```cpp error
#include <memory>
#include <vector>
template<class T> struct Alloc : std::allocator<T> { };
template<class T> using Vec = std::vector<T, Alloc<T>>;
Vec<int> v;

template<class T> void process(Vec<T>&) { }
template<class T> void process(std::vector<T, Alloc<T>>&) { }   // error: 重定义

template<template<class> class TT> void f(TT<int>);
template<template<class, class> class TT> void g(TT<int, Alloc<int>>);

void test() {
  f(v);   // error: 推导不出 TT = Vec
  g(v);   // OK: TT = std::vector
}
```

- `process` 重定义：`Vec<T>` 就是 `std::vector<T, Alloc<T>>`，两个声明是同一个函数模板，别名不产生新类型，自然不能用来重载。
- `f(v)` 失败：`v` 的类型 `std::vector<int, Alloc<int>>` 不记得自己是通过 `Vec` 写出来的。编译器只看到一个有两个实参的 `std::vector` 特化，匹配不了只有一个实参的 `TT<int>`。
- `g(v)` 成功：`TT<int, Alloc<int>>` 与 `std::vector<int, Alloc<int>>` 结构一致，`TT = std::vector`。

推导不出的是别名模板这个名字。透过别名推导它的实参没有问题，因为代入之后别名就消失了，剩下的是普通的形参类型：

```cpp run ok
#include <type_traits>
template<class T> using Id = T;
template<class T> int deduce(Id<T>) { return 1; }                        // 就是 T，可以推导
template<class T> int no_deduce(T, std::type_identity_t<T>) { return 2; }

int main() {
  return deduce(1) + no_deduce(1, 2.0) - 3;   // no_deduce 中 T 只从第一个实参推导为 int
}
```

`std::type_identity_t<T>` 代入后是 `typename type_identity<T>::type`，`T` 出现在 `::` 左边，属于非推导语境（[[temp.deduct.type]]）。所以第二个参数不参与推导，实参 `2.0` 直接转换成 `int`，不会和第一个实参冲突。这个技巧专门用来让某个参数不参与推导。

## 依赖的别名特化仍要代入（¶3）

¶3 如果 *template-id* 是依赖的，后续的模板实参代入仍然作用于这个 *template-id*。

```cpp error
template<typename...> using void_t = void;
template<typename T> void_t<typename T::foo> f();
void test() {
  f<int>();   // error: int 没有嵌套类型 foo
}
```

按 ¶2，`void_t<typename T::foo>` 等价于 `void`。如果编译器立刻把它换成 `void`，签名里就丢了 `typename T::foo`，代入 `T = int` 时不会出错，`f<int>()` 就会被接受。¶3 要求依赖的 *template-id* 原样保留、实参逐个代入，所以 `typename int::foo` 的失败会被发现。在函数模板的签名中，这就是 SFINAE：

```cpp run ok
template<typename...> using void_t = void;

template<class T> void_t<typename T::foo> f(int) { }   // 只对有 T::foo 的类型可行
template<class T> void f(long) { }                     // 后备

struct HasFoo { using foo = int; };
int main() {
  f<HasFoo>(0);   // 选第一个
  f<int>(0);      // 第一个代入失败，选第二个
}
```

!!! history "CWG1558"
    C++11 的原文没有 ¶3。别名不使用它的某些实参时，这些实参要不要代入、会不会引起 SFINAE，并不明确，各编译器表现不一。[[CWG1558]] 加入了 ¶3：依赖的别名特化中，所有实参都要代入。在此之前，可移植的写法要先经过一个类模板，确保实参被用到：

    ```cpp
    template<class...> struct make_void { using type = void; };
    template<class... Ts> using void_t = typename make_void<Ts...>::type;
    ```

## 不能引用自身（¶4）

¶4 别名模板的定义不能引用正在声明的别名模板，别名特化产生的类型也不能直接或间接地用到这个特化本身。

```cpp error
template<class T> using Self = Self<T*>;   // error: 此处 Self 还不可用

template<class T> struct A;
template<class T> using B = typename A<T>::U;
template<class T> struct A {
  typedef B<T> U;
};
B<short> b;   // error: B<short> 经由 A<short>::U 用到了自身
```

第一种是直接引用：在别名的定义里，`Self` 还不是可用的名字。第二种是间接的：`B<short>` 要用 `A<short>::U`，而它又是 `B<short>`。本机 Clang 23 对第二种在 `A` 的定义处就报告找不到 `U`，位置和标准例子不同，但同样拒绝。

别名只是展开，不像类模板那样能借助不完整类型打断递归。链表、树这类递归结构必须经过类模板。

## 别名模板中的 lambda（¶5）

¶5 别名模板声明里的 lambda，在这个模板的不同实例化之间类型不同，即使 lambda 不依赖模板形参。

```cpp run ok
#include <type_traits>
template<class T>
using A = decltype([] { });
static_assert(!std::is_same_v<A<int>, A<char>>);   // 不同的闭包类型
int main() {}
```

这个 lambda 不依赖 `T`，所以既可以理解为所有特化共用一个，也可以理解为每次代入都新生成一个。标准选了后者，与函数模板中 lambda 的行为一致。

!!! lawyer "同一个特化写两次呢"
    ¶5 只说不同实例化之间不同，没有直接回答 `A<int>` 写两次是否是同一个类型。本机 Clang 23 中 `std::is_same_v<A<int>, A<int>>` 为 false，它把每次使用都当作一次新的代入。不要依赖这种行为，尤其不要在函数签名里使用含 lambda 的别名（[[temp.over.link#5]]：lambda 永不等价）。

## 别名模板与 CTAD {{c++20}}

注 1 说别名模板的名字不会被推导，但 C++20 允许对别名模板做类模板实参推导（CTAD，[[P1814R0]]），前提是别名的定义形如一个类模板的特化（[[dcl.type.class.deduct]]）：

```cpp run ok
#include <memory>
#include <type_traits>
#include <vector>
template<class T> struct Alloc : std::allocator<T> { };
template<class T> using Vec = std::vector<T, Alloc<T>>;

Vec w{1, 2, 3};
static_assert(std::is_same_v<decltype(w), std::vector<int, Alloc<int>>>);
int main() {}
```

编译器从 `std::vector` 的推导指引出发，把别名的定义与指引的返回类型做推导，生成别名专用的推导指引（[[over.match.class.deduct]]）。这和注 1 不矛盾：推导的是别名的形参 `T`，不是从一个现成的类型里认出别名。

## 不能特化

别名声明的语法里不能写 *template-id*，所以别名模板不能部分特化，也不能显式特化（[[temp.decls#4]]）。需要按类型选择时，把特化放在类模板上，再用别名转发：

```cpp run ok
#include <type_traits>
template<class T> struct add_ptr_impl     { using type = T*; };
template<class T> struct add_ptr_impl<T&> { using type = T*; };   // 特化写在类模板上
template<class T> using add_ptr = typename add_ptr_impl<T>::type;

static_assert(std::is_same_v<add_ptr<int&>, int*>);
int main() {}
```

## 反射看到的是别名本身 {{c++26}}

C++26 的静态反射需要区分别名 `Vec<int>` 和它代表的类型：`^^Vec<int>` 应当反射一个类型别名，可以查询它是别名、取出它的名字，而不是直接反射 `std::vector<int, Alloc<int>>`。所以 ¶2 把作为 `^^` 操作数的 *template-id* 排除在透明规则之外，规定它是一个类型别名的 *typedef-name*；如果构造它代表的类型时代入失败，这个 *template-id* 非良构（[[expr.reflect]]）。本机 Clang 23 不支持静态反射，这部分没有经过编译验证。

## 实现视角

!!! impl
    - 别名不出现在修饰名中。签名里的 `Vec<T>` 按代入后的 `std::vector<T, Alloc<T>>` 编码，这是透明性在 ABI 层面的体现。
    - 编译器的诊断通常保留别名的写法，例如 `Vec<int>` (aka `std::vector<int, Alloc<int>>`)。这只是为了方便阅读，不影响语义。

## 历史与演进

!!! history
    - C++11 引入别名模板（[[N2258]]）。
    - [[CWG1558]] 作为缺陷报告加入了 ¶3，此后 C++14 标准库提供了 `std::xxx_t` 系列别名，C++17 加入 `std::void_t`。
    - C++20 允许对别名模板做 CTAD（[[P1814R0]]）；lambda 可以出现在不求值操作数中，于是需要 ¶5 规定别名中 lambda 的类型。
    - C++26 的静态反射让 `^^` 操作数中的别名特化不再透明。

## 常见误解

!!! pitfall "可以用 `Vec<T>` 和 `std::vector<T, Alloc<T>>` 重载"
    它们是同一个类型，两个声明是同一个函数模板。

!!! pitfall "能从 `std::vector<int, Alloc<int>>` 推导出模板模板形参 `TT = Vec`"
    可以显式把别名模板作为模板模板实参传进去，但不能从一个类型推导出别名模板。

!!! pitfall "`void_t<typename T::foo>` 会立即折叠成 `void`"
    依赖的别名特化仍要代入全部实参（¶3），代入失败会被发现。

## 思考题

!!! question "思考题 1"
    下面的调用能推导吗？

    ```cpp
    template<class T> using P = T*;
    template<class T> void f(P<T>);
    int x;
    f(&x);
    ```

<details markdown="1">
<summary>答案</summary>

能，`T = int`。`P<T>` 等价于 `T*`，`f` 的参数类型就是 `T*`，从 `int*` 推导出 `T = int`。不能推导的是别名模板这个名字本身，例如把 `P` 推导为某个模板模板形参。透过别名推导它的实参没有问题，前提是代入后 `T` 仍处在可推导的位置（对比 `std::type_identity_t<T>`）。
</details>

!!! question "思考题 2"
    在 ¶3 之下，下面两种 `void_t` 有区别吗？

    ```cpp
    template<class...> using void_t1 = void;
    template<class... Ts> struct make_void { using type = void; };
    template<class... Ts> using void_t2 = typename make_void<Ts...>::type;
    ```

<details markdown="1">
<summary>答案</summary>

在依赖语境中行为相同：依赖的 *template-id* 的实参总要代入，`void_t1<typename T::foo>` 也会因 `T::foo` 不存在而代入失败。区别只是 `void_t2` 多实例化了一个类模板。在 CWG1558 之前，C++11 的措辞允许实现直接把 `void_t1<...>` 换成 `void`、丢掉没用到的实参，那时只有 `void_t2` 能可移植地触发 SFINAE。
</details>
