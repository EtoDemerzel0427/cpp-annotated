---
title: 模板序言
summary: 模板声明由什么组成、能声明什么；templated 实体的定义；requires 子句的受限文法；以及模板定义为什么要放在头文件里。
status: done
related: temp, temp.param, temp.constr.decl, temp.names, temp.spec, temp.inst, temp.explicit, basic.def.odr, dcl.decl
tags: 模板, templated entity, requires-clause, 变量模板
updated: 2026-10-19
---

!!! tldr
    - 模板定义一族类、函数或变量，一族类型的别名，或者一个概念。`std::vector` 是模板，`std::vector<int>` 才是类。
    - 枚举、`typedef`、命名空间不能是模板；模板只能在命名空间或类作用域声明，函数体里得到模板的唯一途径是泛型 lambda。
    - 函数模板不能部分特化，一个模板声明只能声明一个实体。
    - 模板里定义的东西（类模板的成员函数、局部类、lambda 的闭包类型等）不是模板，但是 templated 实体，很多规则对它们和模板一样适用。
    - `requires` 子句只接受用 `&&`、`||` 连接的初等表达式，`requires sizeof(T) > 1` 要写成 `requires (sizeof(T) > 1)`。

## 模板声明长什么样（¶1）

```cpp run title="kinds.cpp" ok
template<class T> struct Box { T v; };                 // 类模板
template<class T> T twice(T x) { return x + x; }       // 函数模板
template<class T> constexpr T pi = T(3.14159L);        // 变量模板（C++14）
template<class T> using Ptr = T*;                      // 别名模板（C++11）
template<class T> concept Small = sizeof(T) <= 4;      // 概念（C++20）
int main() {
  Box<int> b{1};
  Ptr<int> p = &b.v;
  static_assert(Small<int>);
  return twice(*p) - 2 + int(pi<double>) - 3;
}
```

¶1 **模板**（template）定义一族类、函数或变量，一族类型的别名，或者一个概念，分别叫类模板、函数模板、变量模板、别名模板和概念。模板本身不是类或函数，它的**特化**（specialization）才是：`Box` 不是类型，`Box<int>` 才是。

文法上，模板声明是一个 *template-head* 后面跟一个声明或概念定义：

```text
template-declaration:
    template-head declaration
    template-head concept-definition
template-head:
    template < template-parameter-list > requires-clause(opt)
```

*requires-clause* 是 *template-head* 的一部分，所以模板头本身就带着约束。两个声明要算同一个模板的重声明，它们的 *template-head*（包括 *requires-clause*）必须等价（[[temp.over.link]]）。

注 1：*template-parameter-list* 后面的 `>` 可以来自把 `>>` 拆成两个 `>`（[[temp.names]]），所以 C++11 起 `template<template<class> class TT>` 不必在两个 `>` 之间加空格。

## 哪些声明可以是模板（¶2）

¶2 模板声明里的声明必须是下面几种之一：

- ¶2.1 声明或定义函数、类或变量；
- ¶2.2 在类外定义类模板的成员函数、成员类、成员枚举或静态数据成员，例如 `template<class T> void A<T>::f() {}`；
- ¶2.3 定义类或类模板的成员模板；
- ¶2.4 友元类型声明（*friend-type-declaration*）；
- ¶2.5 推导指引（[[temp.deduct.guide]]）；
- ¶2.6 别名声明（*alias-declaration*）。

它也不能是链接规格说明（`extern "C++" ...` 这种形式）。所以枚举、`typedef`、命名空间都不能是模板：

```cpp title="not-templatable.cpp" error
template<class T> enum E { a };   // error: 枚举不能是模板
template<class T> typedef T X;    // error: typedef 不能是模板
template<class T> using Y = T;    // OK：别名模板
```

需要按类型变化的别名，就用别名模板。C++11 加入别名模板时选择了新的 `using` 语法，没有扩展 `typedef`，此后 `using` 成了写别名的推荐方式。

类模板的成员枚举可以在类外定义（¶2.2），如 `template<class T> enum class A<T>::E : int { x };`。这个枚举随类模板一起特化，但它本身不是枚举模板。

模板也不能有 C 语言链接（[[dcl.link]]），因为 C 的名字不经修饰，无法区分 `f<int>` 和 `f<double>`：

```cpp title="c-linkage.cpp" error
extern "C" {
  template<class T> void f(T);   // error: 模板不能有 C 语言链接
}
```

## 变量模板（¶3）

¶3 变量的模板声明引入的是**变量模板**（variable template），类作用域里的变量模板叫**静态数据成员模板**（static data member template）。

```cpp run title="variable-template.cpp" ok
#include <cstdio>
template<class T>
constexpr T pi = T(3.1415926535897932385L);

template<class T>
T circular_area(T r) { return pi<T> * r * r; }

struct S {
  template<class T>
  static constexpr int size = sizeof(T);   // 静态数据成员模板
};

int main() {
  std::printf("%f %d\n", circular_area(1.0), S::size<double>);
}
```

在 C++14 加入变量模板之前，随类型变化的常量要写成 `std::is_same<T, U>::value` 或 `constexpr` 函数模板。变量模板让 C++17 的 `std::is_same_v<T, U>` 这类 `_v` 组件成为可能。

变量模板也可以部分特化（[[temp.spec.partial]]）。¶4 的注 3 指出，用 *simple-template-id*（如 `rank<T[]>`）声明类模板或变量模板，就是在声明部分特化：

```cpp run title="var-partial.cpp" ok
template<class T> constexpr int rank = 0;
template<class T> constexpr int rank<T[]> = 1 + rank<T>;          // 部分特化
template<class T, int N> constexpr int rank<T[N]> = 1 + rank<T>;
static_assert(rank<int[2][3]> == 2);
static_assert(rank<int[][4]> == 2);
int main() {}
```

## 在哪里声明，怎样声明（¶4–¶5）

¶4 的注 2：模板声明只能出现在命名空间作用域或类作用域。

```cpp title="block-scope.cpp" error
void g() {
  template<class T> struct L {};          // error: 块作用域中不能声明模板
  auto lam = [](auto x) { return x; };    // OK：泛型 lambda
}
```

泛型 lambda 是在函数体里得到模板的唯一途径。它的闭包类型和 `operator()` 模板由语言生成，不是由块作用域中的模板声明引入的。

¶4 还有两条要求。第一，模板声明里的声明不能是导出声明：要导出模板，`export` 写在最外面，即 `export template<class T> void f(T);`。第二，函数模板声明的声明符名字必须是一个名字（标识符、`operator@`、转换函数名或字面量运算符名），不能是 *template-id*。这一条禁止了函数模板的部分特化：

```cpp title="no-fn-partial-spec.cpp" error
template<class T> void f(T);
template<class T> void f<T*>(T*);   // error: 函数模板不能部分特化
template<class T> void f(T*);       // OK：另一个重载的函数模板，由偏序挑选
```

需要类似的效果时，用重载加偏序（[[temp.func.order]]），或者把逻辑转给一个可以部分特化的类模板。

¶5 模板声明、显式特化、显式实例化最多只能有一个声明符；声明类模板时不能带声明符：

```cpp title="one-declarator.cpp" error
template<class T> T a, b;          // error: 一个模板声明只能声明一个实体
template<class T> struct S {} s;   // error: 声明类模板时不能同时声明变量
```

如果允许 `template<class T> T a, b;`，`a` 和 `b` 是一个模板还是两个，对 `a<int>` 的显式特化是否也特化 `b`，都说不清楚，标准直接禁止了。

¶5 后半规定，模板声明里的友元类型声明只能是单个 `friend friend-type-specifier ;`。C++26 允许一个友元声明用包展开声明多个友元类型，但这种展开不能用在模板声明里：

```cpp title="friend-pack.cpp" error
template<class...> struct C { struct Nested {}; };
template<class... Us>
struct S {
  template<class... Ts>
  friend class C<Ts>::Nested...;   // error: 模板声明中的友元不能是包展开
  friend class C<Us>::Nested...;   // OK（C++26）：不是模板声明，展开外层的包
};
```

## 特化与名字（¶6–¶7）

¶6 一个模板的特化（显式的或隐式的）与任何其他模板的特化都不相同，即使两者结构完全一样。别名模板不产生新的类型，它的特化就是替换之后的类型（[[temp.alias]]）：

```cpp run title="distinct.cpp" ok
#include <type_traits>
template<class T> struct A { T x; };
template<class T> struct B { T x; };
static_assert(!std::is_same_v<A<int>, B<int>>);   // 不同的模板，不同的类型
template<class T> using AA = A<T>;
static_assert(std::is_same_v<AA<int>, A<int>>);   // 别名模板的特化就是 A<int>
int main() {}
```

¶6 的注 4：在模板实例化的意义上，函数模板和类模板成员函数的默认实参视为定义（[[temp.decls]]），必须遵守 ODR。

¶7 的注 5：模板不能和同一作用域里的其他名字同名（[[basic.scope.scope]]）。例外是函数模板，它可以和 using 声明引入的名字、类型、普通函数、其他函数模板同名，这是函数模板能参与重载的基础。特化（包括部分特化）不引入新的名字，它和主模板属于同一个作用域。

```cpp title="names.cpp" error
void f() {}
class f {};                                    // OK：函数和类同名
template<typename> void f(long) {}             // #1 OK：函数模板和函数同名
template<typename> void f(long) {}             // error: 重定义 #1
template<typename> void f(long long) {}        // OK：另一个重载
template<>         void f<int>(long long) {}   // OK：显式特化不引入名字
template<typename> struct f2 {};
int f2;                                        // error: 类模板不能和变量同名
```

## templated 实体（¶8）

```cpp run title="templated.cpp" ok
template<class T>
struct A {
  void f() {}          // A<T>::f 不是模板，但它是 templated（¶8.4）
  enum E { e1 };       // E 和 e1 都是 templated（¶8.4、¶8.5）
  friend void g(A) {}  // 在 templated 类里定义的友元：templated（注 6）
};
template<class T>
void h() {
  struct Local { T t; };   // templated 类（¶8.3）
  auto lam = [] {};        // 闭包类型是 templated（¶8.6）
  (void)lam; Local l{}; (void)l;
}
int main() { h<int>(); A<int>{}.f(); }
```

类模板的成员函数、函数模板里的局部类，本身都不是模板，却处在模板之中，随模板的每个特化各有一份。¶8 把它们统称为 **templated 实体**（[[g:templated-entity|templated entity]]）。一个实体是 templated 的，如果它是：

| | 情形 | 例子 |
|---|---|---|
| ¶8.1 | 模板 | `template<class T> void f(T);` |
| ¶8.2 {{c++26}} | 在展开语句（[[stmt.expand]]）的 *for-range-declaration* 或语句体中定义或创建的实体 | `template for (auto x : tup) { struct L {}; }` 中的 `L` |
| ¶8.3 | 在 templated 实体中定义或创建的实体 | 函数模板里的局部类、局部变量、临时对象 |
| ¶8.4 | templated 实体的成员 | 类模板的成员函数 |
| ¶8.5 | templated 枚举的枚举器 | 类模板成员枚举的枚举器 |
| ¶8.6 | 出现在 templated 实体声明中的 lambda 的闭包类型 | 函数模板里 `[]{}` 的闭包类型 |

**templated 函数**指函数模板或 templated 的函数，templated 类、templated 变量同理。

¶8.2 是随 C++26 的展开语句加入的：`template for` 的循环体对每个元素各实例化一次，体内定义的实体必须视为 templated，`x` 的类型才能每次不同。

很多规则的适用范围是 templated 实体，而不只是模板：

- 只有 templated 函数可以有尾随的 *requires-clause*（[[dcl.decl]]），所以类模板的普通成员函数也能加约束：

    ```cpp title="member-requires.cpp" error
    template<class T>
    struct S {
      void f() requires (sizeof(T) > 1);   // OK：S<T>::f 是 templated 函数
    };
    S<char> s;                             // OK：只是 s.f() 不能调用
    void g() requires true;                // error: 不是 templated 函数
    ```

- `if constexpr` 被舍弃的分支，只有在 templated 实体里才不实例化（[[stmt.if]]）；在普通函数里，舍弃的分支照样要完全合法。
- 只有在 templated 实体里，名字和表达式才可能是待决的（依赖模板形参，[[temp.dep]]）。
- 模板不可能有合法特化时的 IFNDR 规则（[[temp.res]]）适用于所有 templated 实体。

## requires 子句（¶9）

```cpp title="requires-grammar.cpp" error
#include <type_traits>
template<class T> concept C = true;
template<class T> requires C<T> && std::is_integral_v<T> void f1();   // OK
template<class T> requires (sizeof(T) > 1) void f2();                 // OK：带括号
template<class T> requires requires (T t) { t + t; } void f3();       // OK：requires 表达式
template<class T> requires sizeof(T) > 1 void f4();                   // error: 需要括号
template<class T> requires !C<T> void f5();                           // error: 要写成 (!C<T>)
```

¶9 可选的 *requires-clause* 给模板实参加上约束（[[temp.constr.decl]]）。它的表达式是**不求值操作数**（[[expr.context]]），不会在运行时求值。

它的文法 *constraint-logical-or-expression* 只允许用 `&&` 和 `||` 连接**初等表达式**（*primary-expression*）：字面量、名字（包括 `C<T>`、`std::is_integral_v<T>`）、括号表达式、lambda、折叠表达式、requires 表达式等。`sizeof(T) > 1`、`!C<T>`、`N == 0` 都不是初等表达式，必须加括号。

为什么这样限制？*requires-clause* 后面紧跟着声明的其余部分，而声明说明符可能被误读成表达式的一部分。注 7 的例子：

```cpp error
template<int N> requires N == sizeof new unsigned short
int f();   // error: == 表达式需要括号
```

如果允许任意表达式，`int` 是属于 `new unsigned short int`，还是函数 `f` 的返回类型？解析器无从判断。限定为初等表达式之后，复杂的表达式都要加括号，边界就清楚了。写在函数声明符后面的尾随 *requires-clause* 用的是同一套文法（[[dcl.decl]]）。

`template<class T> requires requires (T t) { ++t; }` 中，第一个 `requires` 开始 *requires-clause*，第二个开始 requires 表达式。这样写是合法的，但通常说明应该给这个 requires 表达式起个名字，定义成概念：只有具名的概念才能参与约束之间的包含比较（[[temp.constr.order]]）。

约束虽然不求值，但判断约束是否满足时要做替换和常量求值（[[temp.constr.atomic]]），这可能导致模板被隐式实例化。两者并不矛盾：常量求值发生在编译期，不属于程序的执行。

## 模板定义要放在头文件里（¶10）

¶10 函数模板、类模板的成员函数、变量模板、类模板的静态数据成员，它们的定义必须从每个隐式实例化它的**定义域**（definition domain，大致是一个翻译单元，见 [[basic.def.odr]]）的末尾可达，除非对应的特化在某个翻译单元中被显式实例化；否则 {{ifndr}}。

```cpp title="a.h"
template<class T> T twice(T x);   // 只有声明
```

```cpp title="a.cpp"
#include "a.h"
template<class T> T twice(T x) { return x + x; }
template int twice<int>(int);     // 显式实例化定义：在这里生成 twice<int>
```

```cpp title="main.cpp" ok
#include "a.h"
int main() {
  return twice(21) == 42 ? 0 : 1;   // OK：twice<int> 在 a.cpp 中显式实例化
  // twice(1.0) 则是 IFNDR：twice<double> 的定义不可达，也没有显式实例化
}
```

这就是模板要写在头文件里的依据。为什么不要求诊断？编译 `main.cpp` 时编译器看不到 `a.cpp`，不知道 `twice<double>` 有没有在别处显式实例化。

实践中违反这条规则的典型症状是链接错误（未定义符号 `twice<double>`），但标准不保证。如果另一个翻译单元碰巧隐式实例化了同一个特化，链接器可能悄悄用上它，程序看起来能运行；换个链接顺序或优化级别，那个翻译单元可能把调用内联掉、不再输出这个符号，链接就失败了。

在模块中，定义可以来自导入的模块接口单元，只要可达（[[module.reach]]）。所以模块化之后模板定义仍要放在接口里，放在实现单元里就不可达。

!!! impl
    - GCC、Clang（Itanium ABI）和 MSVC 都把隐式实例化的模板特化作为 COMDAT 或弱符号放进每个用到它的目标文件，由链接器合并。
    - 显式实例化声明 `extern template`（[[temp.explicit]]）告诉编译器这里不必实例化，别处已有，用来减少编译时间和目标文件大小。
    - 名字修饰会编码模板实参，例如 `twice<int>` 修饰为 `_Z5twiceIiET_S0_`。带约束的模板，其约束也会进入修饰名：Clang 为 `template<class T> requires std::integral<T> void c1(T)` 的 `c1<int>` 生成 `_Z2c1IiQsr3stdE8integralIT_EEvS0_`，其中 `Q...` 编码了 *requires-clause*，用来区分只靠约束区分的重载。

## 历史与演进

!!! history
    - C++98 只有类模板和函数模板。它还有 `export template`，允许把模板定义放在 `.cpp` 里、由实现负责跨翻译单元实例化，正是为了解决 ¶10 的问题；但只有基于 EDG 前端的编译器实现过它。
    - C++11 删除了 `export` 模板（保留关键字），加入别名模板、变参模板、`>>` 的拆分和 `extern template`。
    - C++14 加入变量模板，C++17 加入推导指引。
    - C++20 加入概念和 *requires-clause*。模块重新启用了 `export` 关键字，¶4 因此规定模板声明里的声明不能是导出声明。
    - C++26 让展开语句中的实体成为 templated（¶8.2），并加入友元类型的包展开（¶5）。

## 常见误解

!!! pitfall "类模板的成员函数是函数模板"
    `A<T>::f` 是 templated 函数（¶8.4），不是函数模板：调用它不做模板实参推导，也只能用 `template<>` 为某个 `A<X>` 显式特化它。它按需实例化，是因为 [[temp.inst]] 对 templated 实体的成员有专门的规定。

!!! pitfall "把模板定义放进 .cpp 最多导致链接错误"
    按标准这是 IFNDR（¶10）。别的翻译单元碰巧实例化了同一个特化时，程序可能能运行，换个链接顺序或优化级别又失败。

## 思考题

!!! question "1. 下面哪些声明是良构的？"
    ```cpp
    template<class T> struct A { enum class E; };
    template<class T> enum class A<T>::E { x };           // (a)
    template<class T> int v1 = 1, v2 = 2;                 // (b)
    template<class T> auto lam = [](T t) { return t; };   // (c)
    ```

<details markdown="1">
<summary>答案</summary>

- (a) 良构。¶2.2 允许在类外定义类模板的成员枚举。
- (b) 非良构。¶5 规定模板声明最多一个声明符。
- (c) 良构。这是一个以 lambda 初始化的变量模板，`lam<int>` 和 `lam<double>` 各有自己的闭包类型（闭包类型是 templated 的，¶8.6）。
</details>

!!! question "2. 函数模板 `template<class T> void g(T) {}` 只在 `x.cpp` 中定义，`x.cpp` 调用了 `g(1)`；`y.cpp` 只有声明，也调用了 `g(1)`。这个程序良构吗？"

<details markdown="1">
<summary>答案</summary>

是 IFNDR（¶10）。`y.cpp` 隐式实例化了 `g<int>`，但它的定义从 `y.cpp` 不可达，`g<int>` 也没有在任何翻译单元里显式实例化，`x.cpp` 里的只是隐式实例化。实践中通常能链接成功，因为 `x.cpp` 输出了弱符号 `g<int>`；但优化时 `x.cpp` 可能把 `g<int>` 内联掉、不再输出这个符号，链接就会失败。
</details>
