---
title: 部分特化
summary: 类模板和变量模板的部分特化怎样声明、受哪些限制，编译器怎样判断它与实参匹配、多个都匹配时选哪一个，以及部分特化的成员与主模板成员的关系。
status: done
covers: temp.spec.partial.general, temp.spec.partial.match, temp.spec.partial.order, temp.spec.partial.member
since: c++98
related: temp.decls, temp.func.order, temp.deduct.type, temp.constr.order, temp.class, temp.expl.spec, temp.inst, temp.arg.nontype
tags: 模板, 部分特化, 偏序, void_t
updated: 2026-10-19
---

!!! tldr
    - 部分特化为一部分实参提供替代的类定义或变量定义。只有类模板和变量模板能部分特化，函数模板用重载代替，别名模板不能特化。
    - 部分特化必须在每个会用到它的实例化之前可达，否则程序非良构且不要求诊断。
    - 一个部分特化匹配，指它的形参能从实际实参推导出来并满足约束。没有匹配用主模板，一个匹配用它，多个匹配时选最特化的，选不出来就是歧义错误。
    - 比较两个部分特化时，把它们改写成单参数的函数模板，再套用函数模板的偏序规则。
    - 部分特化是一个完整的替代定义，不继承主模板的任何成员。

## 一个例子

```cpp run ok
template<class T> struct is_ptr       { static constexpr bool value = false; };
template<class T> struct is_ptr<T*>   { static constexpr bool value = true;  };

static_assert(!is_ptr<int>::value);
static_assert(is_ptr<int*>::value);    // 用 is_ptr<T*>，T = int
int main() {}
```

第一个声明是**主模板**（primary template）：模板名后面没有实参列表。第二个声明在模板名后面写了实参列表 `<T*>`，它是一个[[g:partial-specialization|**部分特化**]]（partial specialization）：当实参的形状是某个类型的指针时，用这份定义代替主模板。和显式特化 `template<> struct is_ptr<int>` 不同，部分特化仍有自己的模板形参，一次覆盖一族实参。

标准库到处用这种写法：`std::unique_ptr<T[]>`、`std::is_pointer<T*>`、`std::tuple_size<std::array<T, N>>`。只有类模板和变量模板可以部分特化（[[temp.decls#2]]）。函数模板靠重载加偏序达到同样的效果（[[temp.func.order]]），别名模板则不能特化（[[temp.decls#4]]）。

## 声明部分特化 [temp.spec.partial.general]

### 形参与实参列表（¶3、¶5）

¶3 标准的例子里，第一个声明是主模板，其余四个是它的部分特化：

```cpp run ok
template<class T1, class T2, int I> class A             { };   // 主模板
template<class T, int I>            class A<T, T*, I>   { };   // #2
template<class T1, class T2, int I> class A<T1*, T2, I> { };   // #3
template<class T>                   class A<int, T*, 5> { };   // #4
template<class T1, class T2, int I> class A<T1, T2*, I> { };   // #5
int main() {}
```

¶5 部分特化的**模板实参列表**就是模板名后面那个 *template-argument-list*，例如 #2 的 `<T, T*, I>`。它必须与主模板的形参列表一一对应：三个位置，依次是类型、类型、`int` 值。部分特化自己的模板形参有几个，与主模板无关，#4 只有一个形参 `T`。

### 主模板在前，部分特化必须可达（¶1）

¶1 主模板的声明必须出现在它的任何部分特化之前。此外，如果一次隐式或显式实例化本来会用到某个部分特化，这个部分特化在那里就必须可达，否则程序{{ifndr}}。

```cpp run ifndr
template<class T> struct Traits { static constexpr int v = 0; };
int use() { return Traits<int*>::v; }   // 这里只看得到主模板
template<class T> struct Traits<T*> { static constexpr int v = 1; };
int main() { return use(); }
```

`use()` 已经用主模板实例化了 `Traits<int*>`，后面出现的部分特化不能追溯生效。本机 Clang 23 不给任何诊断，程序返回 0。不要求诊断的原因是多翻译单元的情形无法检查：一个翻译单元看得见部分特化，另一个看不见，同一个特化就有了两份不同的定义。稳妥的做法是把部分特化和主模板放在同一个头文件里。

### 每个部分特化都是独立的模板（¶2）

¶2 两个部分特化声明指同一个实体，条件是它们特化同一个模板，并且 *template-head* 和模板实参列表都等价（等价的定义见 [[temp.over.link]]）。每个部分特化都是一个独立的模板，有自己的模板形参和自己的成员。

### 在哪里声明（¶6）

¶6 凡是可以定义主模板的作用域，都可以声明它的部分特化。成员模板的部分特化既可以写在类内，也可以写在类外：

```cpp run ok
template<class T> struct A {
  struct C {
    template<class T2> struct B { static constexpr int v = 1; };
    template<class T2> struct B<T2**> { static constexpr int v = 2; };  // #1，类内
  };
};

template<class T> template<class T2>
struct A<T>::C::B<T2*> { static constexpr int v = 3; };                 // #2，类外

static_assert(A<short>::C::B<int*>::v == 3);    // 只有 #2 匹配
static_assert(A<short>::C::B<int**>::v == 2);   // #1、#2 都匹配，#1 更特化
int main() {}
```

### 部分特化不引入名字（¶7）

¶7 部分特化声明不引入新名字。程序使用主模板的名字时，所有可达的部分特化都会被考虑。注 1 指出了一个推论：指向类模板的 using 声明不会限制能通过它找到的部分特化，即使部分特化写在 using 声明之后。

```cpp run ok
namespace N {
  template<class T1, class T2> class A { public: static constexpr int v = 0; };
}
using N::A;                                  // 指向主模板

namespace N {
  template<class T> class A<T, T*> { public: static constexpr int v = 1; };
}

static_assert(A<int, int*>::v == 1);         // 仍然用到了后声明的部分特化
int main() {}
```

函数重载不是这样：using 声明只引入当时已经可见的那些重载（[[namespace.udecl]]）。部分特化不是独立的名字，它附属于主模板，总是跟着主模板一起被找到。

### 带约束的部分特化（¶4）{{c++20}}

¶4 部分特化可以带约束（[[temp.constr]]）：

```cpp run ok
template<typename T> concept C = true;

template<typename T> struct X { static constexpr int v = 0; };
template<typename T> struct X<T*> { static constexpr int v = 1; };   // #1
template<C T> struct X<T> { static constexpr int v = 2; };           // #2

static_assert(X<int>::v == 2);
static_assert(X<int*>::v == 1);
int main() {}
```

两个部分特化都比主模板更特化，但理由不同。#1 的形状更具体：`X<T*>` 能匹配的实参，主模板都能匹配，反过来不行。#2 的实参列表 `<T>` 和主模板一模一样，它更特化只是因为它更受约束（[[temp.constr.order]]）。

`X<int*>` 同时匹配 #1 和 #2，结果选 #1。按下文的偏序方法，#1 在形状上比 #2 更特化，这一步已经分出了胜负，约束根本没有参与比较。约束只在两边形状一样、双向推导都成功时才拿来裁决（[[temp.func.order#8]]）。

### 部分特化的实参列表受到的限制（¶8–¶9）

¶8 先定义两个词。一个常量模板实参如果就是某个常量模板形参的名字，例如 #2 中的 `I`，它是[[g:non-specialized-argument|**非特化的**]]（non-specialized）；其余的常量模板实参都是**特化的**（specialized），例如 #4 中的 `5`。

¶9 部分特化的实参列表有四条限制。

¶9.1 如果一个特化的常量实参对应的主模板形参，其类型依赖于部分特化的形参，程序非良构：

```cpp error
template<class T, T t> struct C { };
template<class T> struct C<T, 1>;          // error: 形参 t 的类型 T 尚未确定

template<int X, int (*array_ptr)[X]> class A { };
int array[5];
template<int X> class A<X, &array> { };    // error: array_ptr 的类型依赖于 X
```

匹配 `C<T, 1>` 时要拿 `1` 和实际的第二个实参比较，而那个实参的类型是 `T`。`T` 推导出来之前，不知道 `1` 应该转换成什么类型再比较，`C<char, 1>` 中的 `char(1)` 和 `C<long, 1>` 中的 `long(1)` 并不是同一个值。标准干脆禁止这种写法。非特化的实参只是一个形参名，没有这个问题。

¶9.2 部分特化必须比主模板更特化，判断方法见下文的偏序。最常见的违反是写了一个和主模板一样的部分特化：

```cpp error
template<class T> struct P { };
template<class T> struct P<T> { };   // error: 什么也没有特化
```

带约束的 `template<C T> struct X<T>` 不违反这一条，因为它靠约束变得更特化。

¶9.3 部分特化的模板形参列表不能有默认模板实参。脚注说明，没有任何场合会用到它们：部分特化的形参总是推导出来的，从不显式给出。

¶9.4 实参里不能有未展开的包；如果某个实参是包展开，它必须是最后一个实参。

```cpp error
template<class T, class U> struct Q { };
template<class T, class U = int> struct Q<T*, U> { };   // error: ¶9.3，默认实参

template<class... Ts> struct R { };
template<class... Ts> struct R<Ts> { };                 // error: ¶9.4，未展开的包
template<class... Ts, class T> struct R<Ts..., T> { };  // error: ¶9.4，包展开不在最后
```

对最后一行，Clang 23 报告的是形参无法推导、这个部分特化永远不会被使用（`-Wunusable-partial-specialization`，默认是错误）。角度不同，结论一样。

### 访问检查的豁免（¶10）

¶10 部分特化的模板实参中出现的非依赖名字，不受通常的访问检查，所以可以用平时访问不到的私有类型：

```cpp run ok
class Outer { struct Priv { }; };    // Priv 是私有的

template<class T> struct Trait { static constexpr int v = 0; };
template<class T> struct Trait<T(*)(Outer::Priv)> { static constexpr int v = 1; };  // OK
template<> struct Trait<Outer::Priv> { static constexpr int v = 2; };              // OK
int main() {}
```

显式特化和显式实例化有同样的豁免（[[temp.spec.general#6]]）。依赖名在声明部分特化时无法检查，要等到把实参代入部分特化时才检查。

## 选用哪个定义 [temp.spec.partial.match]

### 三种结果（¶1）

¶1 一个模板特化需要实例化时，编译器要决定用主模板还是某个部分特化来生成它。做法是拿这个特化的实参，与每个部分特化的实参列表逐一匹配：

- ¶1.1 恰好一个部分特化匹配，就用它。
- ¶1.2 有多个匹配，就用偏序规则找出比其他都更特化的那一个；找不到，程序非良构。
- ¶1.3 一个都不匹配，就用主模板。

只有需要实例化时才做这一步。仅仅写出 `A<int*, int>` 这个名字，例如声明一个指针 `A<int*, int>* p;`，并不需要选定义。

### 匹配就是推导加约束（¶2）

¶2 一个部分特化匹配给定的实参列表，当且仅当它的模板实参能从实际实参推导出来，并且推导出的实参满足它的约束（如果有）。推导用的是 [[temp.deduct.type]] 中从类型推导的规则：把部分特化的实参列表当作 P，实际实参当作 A，逐位比较。

```cpp error
template<class T1, class T2, int I> class A             { };    // #1
template<class T, int I>            class A<T, T*, I>   { };    // #2
template<class T1, class T2, int I> class A<T1*, T2, I> { };    // #3
template<class T>                   class A<int, T*, 5> { };    // #4
template<class T1, class T2, int I> class A<T1, T2*, I> { };    // #5

A<int, int, 1>   a1;   // 用 #1：没有部分特化匹配
A<int, int*, 1>  a2;   // 用 #2，T = int，I = 1；#5 也匹配，但 #2 更特化
A<int, char*, 5> a3;   // 用 #4，T = char；#5 也匹配，但 #4 更特化
A<int, char*, 1> a4;   // 用 #5，T1 = int，T2 = char，I = 1
A<int*, int*, 2> a5;   // error: #3 和 #5 都匹配，互不更特化
```

以 `a2` 为例逐个检查：

| 部分特化 | P | 推导过程 | 结果 |
|---|---|---|---|
| #2 | `<T, T*, I>` | 第 1 位得 `T = int`；第 2 位 `T*` 对 `int*` 也得 `T = int`，一致；`I = 1` | 匹配 |
| #3 | `<T1*, T2, I>` | 第 1 位 `T1*` 对 `int` 失败 | 不匹配 |
| #4 | `<int, T*, 5>` | 第 3 位 `5` 与 `1` 不等 | 不匹配 |
| #5 | `<T1, T2*, I>` | `T1 = int`，`T2 = int`，`I = 1` | 匹配 |

#2 和 #5 都匹配，于是比较两者谁更特化。#2 要求第二个实参恰好是指向第一个实参的指针，比 #5 的要求更多，所以选 #2。

约束不满足的部分特化不算匹配：

```cpp run ok
template<typename T> concept C = requires (T t) { t.f(); };

template<typename T> struct S { static constexpr int v = 1; };   // #1
template<C T> struct S<T> { static constexpr int v = 2; };       // #2

struct Arg { void f(); };
static_assert(S<int>::v == 1);   // #2 的约束不满足，只能用主模板
static_assert(S<Arg>::v == 2);   // #2 匹配，并且比主模板更特化
int main() {}
```

### 推导不出形参的部分特化（¶3）

¶3 如果因为形参列表和实参列表的结构，部分特化的模板实参根本推导不出来，程序非良构：

```cpp error
template<int I, int J> struct A { };
template<int I> struct A<I+5, I*2> { };    // error: I 只出现在不可推导的位置
template<int I> struct A<I, I> { };        // OK

template<int I, int J, int K> struct B { };
template<int I> struct B<I, I*2, 2> { };   // OK: I 从第 1 位推导，第 2 位只用来核对
```

`I+5` 这样含有模板形参的表达式属于非推导语境（[[temp.deduct.type]]），推导时直接跳过。如果 `I` 的每一次出现都在这种位置，它永远推不出来，这个部分特化也永远不会被选中，所以标准要求在声明处报错。`B<I, I*2, 2>` 中 `I` 可以从第 1 位推出，推出之后再检查第 2 位是否等于 `2*I`。

### 先补全默认实参，再匹配（¶4）

¶4 写出一个类模板或变量模板的特化时，例如 `A<int, int, 1>`，实参列表要对着主模板的形参列表。部分特化的实参是从主模板的实参推导出来的。

所以匹配之前，主模板的默认模板实参已经补上了。`void_t` 检测惯用法就建立在这一点上：

```cpp run ok
#include <type_traits>
template<class T, class = void>          // 主模板：第二个形参默认是 void
struct has_type : std::false_type { };

template<class T>
struct has_type<T, std::void_t<typename T::type>> : std::true_type { };

struct Yes { using type = int; };
static_assert(has_type<Yes>::value);
static_assert(!has_type<int>::value);
int main() {}
```

`has_type<Yes>` 先补全为 `has_type<Yes, void>`，再与部分特化匹配。第 1 位推出 `T = Yes`。第 2 位处在非推导语境，把 `T` 代入得到 `void_t<int>`，也就是 `void`，与实际实参一致，匹配成功。对 `int`，代入 `int::type` 失败，这属于推导失败，部分特化不匹配，于是用主模板。`void_t` 的实参明明没有被用到，为什么还会代入失败，见 [[temp.alias#3]]。

## 多个都匹配时选谁 [temp.spec.partial.order]

### 改写成函数模板（¶1）

¶1 判断两个部分特化中哪个[[g:more-specialized|**更特化**]]（more specialized），标准不另立一套规则，而是把它们各改写成一个函数模板，再用函数模板的偏序（[[temp.func.order]]）比较：

- ¶1.1 函数模板的模板形参和约束，与对应的部分特化相同；
- ¶1.2 函数模板只有一个函数形参，类型是这个类模板的特化，实参就是部分特化的实参列表。

也就是说，`template<P...> struct X<args>` 改写成 `template<P...> void f(X<args>)`。函数模板偏序的做法是：把一个模板的形参替换成凭空合成的唯一类型或值，看另一个模板能不能从中推导；只有一个方向成功，成功的那一方的被推导者更特化。

### 例子（¶2）

```cpp run ok
template<int I, int J, class T> struct X { static constexpr int v = 0; };
template<int I, int J> struct X<I, J, int> { static constexpr int v = 1; };   // #1
template<int I>        struct X<I, I, int> { static constexpr int v = 2; };   // #2

// 改写后：
template<int I0, int J0> void f(X<I0, J0, int>);   // A
template<int I0>         void f(X<I0, I0, int>);   // B

static_assert(X<3, 3, int>::v == 2);   // #1、#2 都匹配，#2 更特化
static_assert(X<1, 2, int>::v == 1);   // 只有 #1 匹配
int main() {}
```

| 方向 | 用作实参的变换结果 | 对另一方推导 | 结果 |
|---|---|---|---|
| B 对 A | `X<u, u, int>`，u 是合成的值 | `X<I0, J0, int>` 得 `I0 = u`，`J0 = u` | 成功 |
| A 对 B | `X<u1, u2, int>`，两个不同的合成值 | `X<I0, I0, int>` 要求 `I0` 既是 u1 又是 u2 | 失败 |

B 能接受的实参 A 都能接受，反过来不行，所以 B 更特化，#2 更特化。

`auto` 常量形参也一样：

```cpp run ok
template<auto v>    struct Y { static constexpr int k = 0; };
template<auto* p>   struct Y<p> { static constexpr int k = 1; };    // #3
template<auto** pp> struct Y<pp> { static constexpr int k = 2; };   // #4

int i; int* ip = &i;
static_assert(Y<&i>::k == 1);    // 只匹配 #3
static_assert(Y<&ip>::k == 2);   // #3、#4 都匹配，#4 更特化
static_assert(Y<1>::k == 0);
int main() {}
```

改写成 `template<auto* p0> void g(Y<p0>)`（C）和 `template<auto** pp0> void g(Y<pp0>)`（D）。偏序时，为常量形参合成的值，其类型里的占位符也换成合成的唯一类型（[[temp.func.order#3]]）。D 合成的值类型是 `U**`，能匹配 C 的 `auto*`；C 合成的值类型是 `V*`，匹配不了 D 的 `auto**`。所以 D 更特化。

形状相同时，比较约束：

```cpp run ok
template<typename T> concept C = requires (T t) { t.f(); };
template<typename T> concept D = C<T> && requires (T t) { t.f(); };

template<typename T> class S { public: static constexpr int v = 0; };
template<C T> class S<T> { public: static constexpr int v = 1; };   // #1
template<D T> class S<T> { public: static constexpr int v = 2; };   // #2

struct Arg { void f(); };
static_assert(S<Arg>::v == 2);
int main() {}
```

改写后的 `template<C T> void f(S<T>)` 和 `template<D T> void f(S<T>)` 双向推导都成功，于是比较约束：`D` 包含 `C`（[[temp.constr.order]]），#2 更受约束，因而更特化。

## 部分特化的成员 [temp.spec.partial.member]

### 与主模板的成员无关（¶1）

¶1 类模板部分特化的成员与主模板的成员毫无关系。部分特化中以需要定义的方式用到的成员，必须为部分特化单独定义；主模板成员的定义永远不会拿来充当部分特化成员的定义。

```cpp
template<class T, int I> struct A { void f(); };       // 主模板
template<class T, int I> void A<T, I>::f() { }

template<class T> struct A<T, 2> {                     // 部分特化
  void f();
  void g();
  void h();
};
template<class T> void A<T, 2>::g() { }                // 部分特化的成员
template<> void A<char, 2>::h() { }                    // 部分特化成员的显式特化

int main() {
  A<char, 0> a0;
  A<char, 2> a2;
  a0.f();   // OK: 主模板成员的定义
  a2.g();   // OK: 部分特化成员的定义
  a2.h();   // OK: 显式特化的定义
  a2.f();   // 错误：A<T, 2>::f 没有定义，主模板的 f 不会被用上
}
```

标准例子把最后一行标为错误。准确地说，它 odr-use 了一个没有定义的函数，属于不要求诊断的错误（[[basic.def.odr]]）；本机 Clang 23 编译通过，链接时报 `A<char, 2>::f()` 未定义。

部分特化是一份完整的替代定义，不是在主模板上打补丁。需要的成员都得重新声明、重新定义。想共享实现，就把公共部分放进一个基类。

为部分特化的成员写显式特化，写法和为主模板的成员写显式特化一样，如上例的 `h`。

### 成员模板的部分特化（¶2）

¶2 类模板的成员模板也可以有部分特化，它们同样是外围类模板的成员模板。外围类模板实例化时，每个成员模板部分特化的声明也随之实例化。

如果为外围模板的某个特化显式特化了成员模板本身（主成员模板），那么对这个外围特化来说，成员模板原有的部分特化全部作废。反过来，如果显式特化的只是成员模板的某个部分特化，主成员模板和其余部分特化照常参与匹配。

```cpp run ok
template<class T> struct A {
  template<class T2> struct B { static constexpr int v = 1; };        // #1
  template<class T2> struct B<T2*> { static constexpr int v = 2; };   // #2
};

// 对 A<short> 显式特化主成员模板：
template<> template<class T2> struct A<short>::B { static constexpr int v = 3; };   // #3

static_assert(A<char>::B<int*>::v == 2);    // 用 #2
static_assert(A<short>::B<int*>::v == 3);   // 用 #3，#2 对 A<short> 不起作用
static_assert(A<char>::B<int>::v == 1);     // 用 #1
int main() {}
```

#2 是针对 #1 写的。对 `A<short>` 而言，`B` 已经换成了全新的 #3，原来的部分特化也就没有意义了。

## 变量模板的部分特化

本页的规则同样适用于变量模板（[[temp.decls#2]]）：

```cpp run ok
template<class T> constexpr int ptr_depth = 0;
template<class T> constexpr int ptr_depth<T*> = 1 + ptr_depth<T>;
template<class T> constexpr int ptr_depth<T* const> = 1 + ptr_depth<T>;

static_assert(ptr_depth<int> == 0);
static_assert(ptr_depth<int**> == 2);
static_assert(ptr_depth<int* const*> == 2);
int main() {}
```

## 实现视角

!!! impl
    - Clang 对 ¶3、¶9.4 这类永远不会被使用的部分特化给出 `-Wunusable-partial-specialization`，默认是错误；对 ¶9.2 的违反，报告部分特化没有特化任何模板实参。
    - 编译器通常发现不了对 ¶1 可达性要求的违反。后果是同一个特化在不同翻译单元里有不同的定义，链接后可能出现难以解释的行为差异。

## 历史与演进

!!! history
    - C++98 就有类模板部分特化。
    - C++14 引入变量模板，它们同样可以部分特化。
    - C++17 的 `auto` 常量模板形参使 `Y<auto* p>` 这样的部分特化成为可能；`std::void_t` 进入标准库，检测惯用法随之流行。
    - C++20 允许部分特化带约束，实参列表可以与主模板相同，只要更受约束。
    - 当前草案把非类型模板形参改称常量模板形参，¶8 的特化与非特化实参也随之改用这个说法。

## 常见误解

!!! pitfall "部分特化继承主模板的成员"
    不继承。部分特化是完整的替代定义，用到的每个成员都要重新定义（[temp.spec.partial.member] ¶1）。

!!! pitfall "部分特化可以写在使用之后"
    不可以。它必须在每个会用到它的实例化之前可达，否则 IFNDR，而且编译器多半不会提醒。

!!! pitfall "部分特化可以有默认模板实参"
    不允许（¶9.3）。默认值应该写在主模板上，`void_t` 惯用法正是这样做的。

!!! pitfall "两个都匹配时，编译器会挑看起来更具体的那个"
    编译器按严格的偏序规则比较。两个部分特化互不更特化时，程序就是歧义错误，不会凭直觉选一个。

## 思考题

!!! question "思考题 1"
    下面的 `T<int*, int*>` 用哪个定义？

    ```cpp
    template<class A, class B> struct T { };          // #0
    template<class A>          struct T<A, A> { };    // #1
    template<class A, class B> struct T<A*, B*> { };  // #2
    ```

<details markdown="1">
<summary>答案</summary>

歧义，程序非良构。#1（`A = int*`）和 #2（`A = int, B = int`）都匹配。改写成 `f(T<A, A>)` 和 `g(T<A*, B*>)` 做偏序：用 #1 合成的 `T<U, U>` 对 #2 推导，`U` 不是指针，失败；用 #2 合成的 `T<U1*, U2*>` 对 #1 推导，`A` 既要是 `U1*` 又要是 `U2*`，失败。双向都失败，互不更特化。再加一个 `template<class A> struct T<A*, A*>` 就能消除歧义，它比 #1、#2 都更特化。本机 Clang 23 报告 ambiguous partial specializations。
</details>

!!! question "思考题 2"
    `void_t` 检测惯用法为什么要求主模板的第二个形参默认为 `void`，而不能是 `int` 之类的其他类型？

<details markdown="1">
<summary>答案</summary>

由 [temp.spec.partial.match] ¶4，`has_type<X>` 先用主模板的默认实参补全为 `has_type<X, 默认值>`，再与部分特化 `<T, void_t<typename T::type>>` 匹配。部分特化的第二个实参在代入成功时总是 `void`。如果默认值是 `int`，匹配就要求 `void` 等于 `int`，永远失败，部分特化永远不会被选中，trait 恒为 false。
</details>
