---
title: 模板约束
summary: 约束表达式怎样规范化成由合取、析取和原子约束组成的约束；满足检查怎样短路、怎样吸收替换失败；原子约束为什么必须恰好是 bool，什么时候算相同；声明的关联约束按什么顺序组成；C++26 的折叠展开约束和概念依赖约束。
status: done
covers: temp.constr.general, temp.constr.constr, temp.constr.constr.general, temp.constr.op, temp.constr.atomic, temp.constr.concept, temp.constr.fold, temp.constr.decl, temp.constr.normal
since: c++20
papers: P0734R0, P2963R3, P2841
related: temp.constr.order, temp.concept, expr.prim.req, temp.names, temp.param, over.match.viable, over.match.best, temp.deduct, topics/concepts
tags: 概念, 约束, 规范化, 原子约束, 折叠展开约束
updated: 2026-10-19
---

!!! tldr
    - 约束表达式先被规范化：按 `&&`、`||` 拆开，展开其中的概念，剩下不可再拆的部分叫原子约束。
    - 满足检查从左到右短路，没检查到的部分根本不做替换；原子约束在替换失败时只是不满足，不报错。
    - 原子约束替换后必须恰好是 `bool` 类型的常量表达式，`int` 或带 `operator bool` 的类都会使程序非良构。
    - 两个原子约束只有来自源码中同一处表达式才算相同。想让约束参与重载排序，就要把它写成概念。
    - `!E`、requires 表达式都是一个整体的原子约束；C++26 起，`&&`、`||` 折叠表达式可以拆开比较。

## 约束是什么

```cpp run title="short-circuit.cpp" ok
template<typename T>
constexpr bool get_value() { return T::value; }

template<typename T>
  requires (sizeof(T) > 1) && (get_value<T>())
void f(T) {}       // 关联约束：sizeof(T) > 1  ∧  get_value<T>()

void f(int) {}

int main() {
    f('a');        // OK: 调用 f(int)
}
```

调用 `f('a')` 时，模板版本的第一个条件 `sizeof(char) > 1` 不成立，第二个条件 `get_value<char>()` 根本没有实例化。如果实例化了，`char::value` 会在函数体里产生一个无法挽回的错误。

这说明 `requires` 后面的表达式并不是当作一个普通的 `bool` 表达式整体求值的。[temp.constr.constr.general] ¶1 定义的**约束**（[[g:constraint]]）是对模板实参提出要求的一组逻辑运算和操作数，操作数本身也是约束。共有五种：

| 种类 | 来自 | 规则 |
|---|---|---|
| 合取（conjunction），记作 ∧ | `E1 && E2` | [temp.constr.op] |
| 析取（disjunction），记作 ∨ | `E1 \|\| E2` | [temp.constr.op] |
| 原子约束（atomic constraint） | 其余的表达式 | [temp.constr.atomic] |
| 折叠展开约束 {{c++26}} | `(E && ...)`、`(E \|\| ...)` | [temp.constr.fold] |
| 概念依赖约束 {{c++26}} | `CT<T>`，`CT` 是概念模板形参 | [temp.constr.concept] |

∧ 和 ∨ 不是 C++ 语法，标准用这两个符号区别于表达式里的 `&&` 和 `||`（[temp.constr.op] ¶1）。

拆成这样的结构是为了做两件事。一是满足检查：给定实参，约束是否成立，失败时要能短路、能容忍替换失败。二是比较两个约束谁更强（[[temp.constr.order]]）。判断两个任意 `bool` 表达式之间的蕴含关系是做不到的，但把约束化成原子命题的与、或组合，原子之间只比较身份，蕴含就成了简单的命题逻辑问题。

[temp.constr.constr.general] ¶2 受约束的模板要实例化，关联约束必须得到满足。注 1 指出两个常见的触发点：写出类模板、变量模板或别名模板的特化名字就要检查约束（[[temp.names]]）；重载决议要求候选函数的约束满足（[[over.match.viable]]）。

## 规范化：从表达式到约束 [temp.constr.normal]

```cpp
#include <type_traits>
template<class T> concept Big    = sizeof(T) > 8;
template<class T> concept BigInt = Big<T> && std::is_integral_v<T>;

template<class U> void g(U) requires BigInt<U*> || (sizeof(U) == 1);
```

`g` 的约束规范化之后是：

```text
( sizeof(T) > 8          [T ↦ U*]
  ∧ std::is_integral_v<T> [T ↦ U*] )
∨ sizeof(U) == 1          [U ↦ U]
```

¶1 表达式 `E` 的**范式**（normal form）按下面的规则逐层得到：

| 列表项 | 表达式 | 范式 |
|---|---|---|
| ¶1.1 | `( E )` | `E` 的范式，括号不起作用 |
| ¶1.2 | `E1 \|\| E2` | `E1`、`E2` 范式的析取 |
| ¶1.3 | `E1 && E2` | `E1`、`E2` 范式的合取 |
| ¶1.4 | 概念的特化 `C<A1, ..., An>` | 展开 `C` 的定义，见下 |
| ¶1.5 | `&&` 或 `\|\|` 的折叠表达式 | 折叠展开约束，见后文 |
| ¶1.6 | 其他任何表达式 | 原子约束 |

¶2 求范式的过程叫**规范化**（[[g:normalization]]）。注 1 说明它发生在两个时候：确定一个声明的关联约束时，以及求一个概念特化（如 `BigInt<int>`）的值时。

¶1.2 和 ¶1.3 是按语法拆分的。规范化在模板定义处进行，那时还不知道 `&&` 会不会调用重载的 `operator&&`，所以干脆不考虑重载：两边各自是一个约束，各自必须是 `bool`。

### 原子约束与参数映射 [temp.constr.atomic]

[temp.constr.atomic] ¶1 **原子约束**（[[g:atomic-constraint]]）由一个表达式 `E` 和一个**参数映射**（parameter mapping）组成。参数映射记录 `E` 中出现的每个模板形参被映射成什么实参。注 1 补充，`E` 永远不是 `&&` 或 `||` 表达式，因为它们在规范化时已经拆开了。

上例中，第一个原子约束的 `E` 是 `Big` 定义里原样的 `sizeof(T) > 8`，映射是 `T ↦ U*`，而不是替换后的 `sizeof(U*) > 8`。替换的信息保存在映射里，表达式本身保持原来在源码中的样子，后面判断两个原子约束是否相同时就靠这一点。映射里只出现 `E` 中实际用到的形参，像 `true` 这样的原子约束，映射是空的。

### 概念在规范化时被展开（¶1.4）

¶1.4.2 对概念的特化 `C<A1, ..., An>`，规范化先求 `C` 的约束表达式的范式，再把其中各个原子约束映射里出现的 `C` 的形参，换成这里给出的实参 `A1, ..., An`。换句话说，概念被内联展开，映射被复合：`BigInt<U*>` 展开成 `Big<T> && is_integral_v<T>`（`T ↦ U*`），`Big<T>` 再展开成 `sizeof(T) > 8`，映射复合后仍是 `T ↦ U*`。

复合映射时如果形成了无效的类型，程序是非良构、不要求诊断的（IFNDR）。标准例 1：

```cpp title="normal-ifndr.cpp" ifndr
template<typename T> concept A = T::value || true;
template<typename U> concept B = A<U*>;
template<typename V> concept C = B<V&>;   // IFNDR
```

- `B` 的规范化没有问题，得到 `T::value`（`T ↦ U*`）∨ `true`（空映射）。指针类型显然没有 `::value`，但映射 `T ↦ U*` 本身是合法的类型，问题要到满足检查时才暴露，那时只是不满足。
- `C` 的规范化要形成映射 `T ↦ V&*`，指向引用的指针不是合法的类型，所以程序 IFNDR。本机 Clang 23 不给任何诊断。

¶1.6 其余的表达式都是原子约束，包括 requires 表达式。¶3 的例 2 给出了几个对照：

```cpp
template<typename T> concept C1 = sizeof(T) == 1;
template<typename T> concept C2 = C1<T> && 1 == 2;
template<typename T> concept C3 = requires { typename T::type; };

template<C2 U> void f1(U);   // sizeof(T) == 1 [T ↦ U] ∧ 1 == 2
template<C3 U> void f2(U);   // requires { typename T::type; } [T ↦ U]，一个整体
```

requires 表达式不会被拆开，所以 `requires { a; b; }` 与 `requires { a; }` 之间没有任何结构上的联系。要让它们可以比较，把公共的部分提取成概念：

```cpp
template<class T> concept HasA  = requires (T t) { t.a(); };
template<class T> concept HasAB = HasA<T> && requires (T t) { t.b(); };   // HasAB 比 HasA 强
```

## 满足检查

### 合取与析取短路 [temp.constr.op]

[temp.constr.op] ¶2 检查合取时，先检查左操作数；不满足，合取就不满足，否则看右操作数。¶3 检查析取时，先检查左操作数；满足，析取就满足，否则看右操作数。

这比运行时 `&&`、`||` 的短路更彻底。没有检查到的操作数根本不做替换，其中的替换失败、会导致硬错误的实例化都不会发生。开头的 `f('a')` 就是标准的例 1。

### 原子约束的满足（¶3）

[temp.constr.atomic] ¶3 判断一个原子约束是否满足分四步：

1. 把参数映射和模板实参代入表达式。
2. 如果代入在原子约束的**直接语境**（immediate context，[[temp.deduct.general]]）中产生了无效的类型或表达式，约束不满足。这不是错误。
3. 否则，必要时做左值到右值转换，然后 `E` 必须是 `bool` 类型的常量表达式。
4. `E` 的值为 `true` 时约束满足。

第 3 步不做任何隐式转换。类型是 `int`，或者是带 `operator bool` 的类，程序都是非良构的，而不是约束不满足：

```cpp title="must-be-bool.cpp" error
template<class T> struct W { static constexpr int value = 1; };

template<class T> requires (W<T>::value) void f(T) {}          // 原子约束的类型是 const int
template<class T> requires (bool(W<T>::value)) void g(T) {}    // OK: 显式转换为 bool

int main() {
    f(0);    // error: 原子约束必须是 bool 类型
    g(0);    // OK
}
```

这样一来，本想检查 `T::value` 是否存在而误写成 `requires (T::value)` 的代码，在 `value` 是 `int` 时会直接报错，而不会悄悄转换。检查存在性应该写 `requires { T::value; }`。

标准例 3 强调，这个错误发生在满足检查阶段，即使另一个候选更好也挽救不了：

```cpp title="not-bool-hard-error.cpp" error
template<typename T> struct S {
    constexpr operator bool() const { return true; }
};

template<typename T> requires (S<T>{})
void f(T);                      // #1
void f(int);                    // #2

void g() {
    f(0);    // error: 检查 #1 的约束时，S<int>{} 不是 bool 类型；
             //        #2 是更好的匹配也无济于事
}
```

!!! impl "Clang 23 接受这段代码"
    非模板候选 `f(int)` 完全匹配时，Clang 跳过了模板候选的约束检查，所以不会遇到这个错误。去掉 `f(int)` 后，Clang 才报告 atomic constraint must be of type 'bool'。按标准，原例的调用是非良构的。

### 直接语境之外的错误是硬错误

第 2 步只吸收直接语境中的替换失败。如果代入触发了另一个模板的实例化，而错误发生在那个实例化内部，就是硬错误：

<div class="compare" markdown="1">

```cpp error
template<class T>
constexpr bool hard() {
  return T::value;
}
template<class T>
  requires (hard<T>())
void f(T) {}
void f(long) {}

int main() {
  f(0);  // error: int::value 出现在
         // hard<int> 的函数体里
}
```

```cpp run ok
template<class T>
  requires (T::value)
void f(T) {}
void f(long) {}

int main() {
  f(0);  // OK: int::value 在直接语境中
         // 失败，约束不满足，调用 f(long)
}
```

</div>

### 满足结果必须稳定（¶3 末句）

¶3 最后一句规定：在程序的不同位置，相同的原子约束和相同的模板实参得到了不同的满足结果，程序 IFNDR。

```cpp title="unstable.cpp" ifndr
template<class T> concept Complete = requires { sizeof(T); };

struct S;
static_assert(!Complete<S>);   // 此时 S 不完整：不满足
struct S {};
static_assert(Complete<S>);    // IFNDR: 同一原子约束、同一实参，结果不同
```

这条规则让编译器可以缓存满足结果，每个原子约束配一组实参只检查一次。本机 Clang 23 正是这样做的：第二个 `static_assert` 失败，Clang 用的是第一次检查时的结果，报告对不完整类型 `S` 用了 `sizeof`。

!!! warning "不要写检测完整性的概念"
    `Complete<T>`、检测某个重载是否已经声明之类依赖程序位置的概念，几乎必然违反这一条。

## 原子约束什么时候相同 [temp.constr.atomic]

```cpp title="same-appearance.cpp" error
#include <type_traits>

template<class T> concept Integral = std::is_integral_v<T>;

// 经过具名概念：两处的 std::is_integral_v<T> 都来自 Integral 的定义
template<class T> int a(T) requires Integral<T> { return 1; }
template<class T> int a(T) requires Integral<T> && std::is_signed_v<T> { return 2; }
int ra = a(1);     // OK: 选第二个，它的约束包含第一个的

// 直接写两遍：两个 std::is_integral_v<T> 是不同的出现
template<class T> int b(T) requires std::is_integral_v<T> { return 1; }
template<class T> int b(T) requires std::is_integral_v<T> && std::is_signed_v<T> { return 2; }
int rb = b(1);     // error: 歧义
```

两个都满足的重载，编译器要比较谁的约束更强（[[temp.constr.order]]）。这种比较最终落到原子约束是否相同上。

¶2 两个原子约束**相同**（identical），要满足两个条件：

1. 它们由同一个表达式在源码中的同一次出现（the same appearance of the same *expression*）形成；
2. 它们的参数映射把形参映射到相同的实参。精确地说，设想一个模板，以映射涉及的形参为形参，分别以两个映射的目标为实参写出它的特化，这两个特化按 [[temp.type]] 是同一个类型。

第 1 条是关键。`b` 的两个声明里各写了一遍 `std::is_integral_v<T>`，记号完全一样，但它们是两次出现，永远不相同。`a` 的两个声明都通过 `Integral<T>` 引入，规范化后都追溯到 `Integral` 定义中的那一处表达式，所以相同。本机 Clang 23 对 `b` 的歧义会附加一条说明：相似的约束表达式不视为等价，除非它们来自同一个概念。

按语义判断两个表达式是否相同是不可判定的；按记号比较又很脆弱，`a+b` 与 `b+a`、宏展开出来的记号该怎么算都说不清。按同一出现判断避开了这些问题，相同只能通过给约束命名来建立。

### 映射的比较（¶2 注 2）

第 2 条比较映射的方式，类似于带别名模板时的声明匹配（[[temp.alias]]）。标准例 1：

```cpp run title="mapping.cpp" ok
template<unsigned N> constexpr bool Atomic = true;
template<unsigned N> concept C = Atomic<N>;
template<unsigned N> concept Add1 = C<N + 1>;
template<unsigned N> concept AddOne = C<N + 1>;

template<unsigned M> void f() requires Add1<2 * M>;
template<unsigned M> int f() requires AddOne<2 * M> && true;

int x = f<0>();    // OK: 两个 f 来自 C 的原子约束都是 Atomic<N>，
                   // 映射都相当于 N ↦ 2 * M + 1，第二个更受约束
int main() {}
```

`Add1` 和 `AddOne` 是两个不同的概念，但都展开到 `C` 定义里同一处的 `Atomic<N>`，两边的映射 `N ↦ 2 * M + 1` 是等价的表达式（[[temp.over.link]]），所以原子约束相同。

如果两个映射只是功能等价而不等价，例如 `2 * N` 与 `N * 2`，而程序的含义又取决于它们是否相同，程序 IFNDR：

```cpp title="func-equiv.cpp" ifndr
template<unsigned N> constexpr bool Atomic = true;
template<unsigned N> concept C = Atomic<N>;
template<unsigned N> concept Add1 = C<N + 1>;

template<unsigned N> void f2() requires Add1<2 * N>;
template<unsigned N> int f2() requires Add1<N * 2> && true;
void h2() {
    f2<0>();   // IFNDR: 要判断两个功能等价但不等价的原子约束是否相同
}
```

本机 Clang 23 报告调用歧义，这是 IFNDR 允许的结果之一。

## 否定是一个原子约束 [temp.constr.op]

¶5 注 2 指出，`!E` 整体是一个原子约束，取反不算约束上的逻辑运算。这有两个后果：

1. 两个分别写出的 `!E` 即使等价，也是两次出现，互不包含。
2. 替换失败使原子约束不满足，不管外面有没有 `!`。`E` 替换失败时，`!E` 不满足，而不是 `E` 为假、`!E` 为真。

```cpp title="negation.cpp" error
template<class T> concept sad = false;

template<class T> int f1(T) requires (!sad<T>);
template<class T> int f1(T) requires (!sad<T>) && true;
int i1 = f1(42);        // error: 歧义，两个 !sad<T> 是不同的出现

template<class T> concept not_sad = !sad<T>;
template<class T> int f2(T) requires not_sad<T> { return 1; }
template<class T> int f2(T) requires not_sad<T> && true { return 2; }
int i2 = f2(42);        // OK: 两个 !sad<T> 都来自 not_sad 的定义

template<class T> int f3(T) requires (!sad<typename T::type>);
int i3 = f3(42);        // error: 替换失败，原子约束 !sad<int::type> 不满足

template<class T> concept sad_nested_type = sad<typename T::type>;
template<class T> int f4(T) requires (!sad_nested_type<T>) { return 4; }
int i4 = f4(42);        // OK: 替换失败被包在概念里，sad_nested_type<int> 为 false
```

`f3` 和 `f4` 的意思不同：

- `requires (!sad<typename T::type>)` 要求存在嵌套类型 `type`，并且它不 sad；
- `requires (!sad_nested_type<T>)` 要求不存在 sad 的嵌套类型，没有嵌套类型也算。

`f3` 的原子约束是整个 `!sad<typename T::type>`，代入 `T = int` 时直接失败。`f4` 的原子约束是 `!sad_nested_type<T>`，代入得到 `!sad_nested_type<int>`，这一步没有失败；接着求概念特化 `sad_nested_type<int>` 的值，它内部的替换失败只让它的值为 `false`（[[temp.names]]），取反得 `true`。

## 声明的关联约束 [temp.constr.decl]

```cpp run title="assoc-order.cpp" ok
template<typename T> concept C = true;
template<typename T> concept C1 = true;
template<typename T> concept C2 = sizeof(T) > 0;

template<C T> void f1(T);                     // 关联约束都是 C<T>
template<typename T> requires C<T> void f2(T);
template<typename T> void f3(T) requires C<T>;

template<C1 T> void f4(T) requires C2<T>;     // C1<T> ∧ C2<T>
template<typename T> requires C1<T> && C2<T> void f5(T);   // C1<T> ∧ C2<T>

template<C1 T> requires C2<T> void f6();      // C1<T> ∧ C2<T>
template<C2 T> requires C1<T> void f7();      // C2<T> ∧ C1<T>，顺序不同

void f8(C1 auto x) requires C2<decltype(x)>;  // C1<T′> ∧ C2<decltype(x)>
int main() {}
```

¶1–¶2 约束可以从几个位置写进声明：模板形参列表之后的 *requires-clause*，函数声明末尾的尾随 *requires-clause*，模板形参列表里的 *type-constraint*（`template<C T>`），以及缩写函数模板形参里的 *type-constraint*（`C1 auto x`，[[dcl.fct]]）。

¶3 声明的**关联约束**（[[g:associated-constraints]]）这样组成：

- ¶3.1 一个约束表达式都没有，就没有关联约束；
- ¶3.2 只有一个，关联约束就是它的范式；
- ¶3.3 有多个，就按下面的顺序用 `&&` 连起来，再求范式：
    1. 模板形参列表中各个 *type-constraint*，按出现顺序；
    2. 模板形参列表之后的 *requires-clause*；
    3. 函数形参中各个 *type-constraint*；
    4. 尾随 *requires-clause*。

这个顺序就是满足检查时各约束的实例化顺序，决定了短路的效果。`f6` 和 `f7` 的关联约束是 `C1 ∧ C2` 和 `C2 ∧ C1`，比较强弱时它们互相包含，但检查满足时先检查的不同。

`f1`、`f2`、`f3` 的关联约束相同，但它们不是同一个函数模板的三种等价写法。判断两个声明是否声明同一个模板时，*type-constraint* 和 *requires-clause* 要按写法一一对应（[[temp.over.link#6]]）。如果用 `f2` 的形式声明、用 `f1` 的形式定义同一个名字，两者接受同样的实参却不对应，程序 IFNDR（[[temp.over.link#7]]）。声明和定义要用同一种写法。

### 类模板成员的约束对应（¶4）

```cpp run title="member-spec.cpp" ok
template<class T> concept C = true;

template<class T> struct A {
    template<class U> U f(U) requires C<typename T::type>;   // #1
    template<class U> U f(U) requires C<T>;                  // #2
};

template<> template<class U>
U A<int>::f(U u) requires C<int> { return u; }               // OK: 特化 #2

int main() {}
```

¶4 拿类模板实例化后某个成员声明的约束表达式，与类外声明的约束表达式比较是否等价时，先实例化前者；实例化得到无效的表达式，两者就不等价。注 1 指出，这种比较发生在判断一个显式特化特化的是哪个成员模板时。上例中，`A<int>` 的 #1 实例化为无效的 `C<int::type>`，不匹配；#2 实例化为 `C<int>`，匹配。

!!! lawyer "比较写法和检查满足是两回事"
    ¶4 比较的是约束表达式本身，所以 `C<int::type>` 算无效。但如果调用 `A<int>{}.f(0)`，满足检查走的是规范化：`C` 的范式是原子约束 `true`，映射为空，`int::type` 根本不会被代入，#1 的约束反而是满足的。两个候选的关联约束都是 `C` 定义里同一处的 `true`，互相包含，调用歧义。本机 Clang 23 正是这样报告的。

## 折叠展开约束 [temp.constr.fold] {{c++26}}

```cpp run title="fold-subsume.cpp" ok
#include <concepts>

template<class... T> requires (std::integral<T> && ...)
constexpr int f(T...) { return 1; }

template<class... T> requires (std::signed_integral<T> && ...)
constexpr int f(T...) { return 2; }

static_assert(f(1, 2L) == 2);   // C++26: 选第二个；C++23: 歧义
static_assert(f(1u, 2) == 1);   // 只有第一个满足
static_assert(f() == 2);        // 空包：两个都满足，第二个更受约束
int main() {}
```

C++23 中 `(std::integral<T> && ...)` 只是一个原子约束，两个折叠表达式是两次不同的出现，谁也不包含谁，上面的调用是歧义的。C++26 通过 [[P2963R3]] 让这类折叠表达式规范化成**折叠展开约束**（[[g:fold-expanded-constraint]]），使它们可以比较。

¶1 折叠展开约束由一个约束 `C` 和一个折叠运算符 `&&` 或 `||` 组成。它是一个包展开（[[temp.variadic]]），`N` 是被展开的包的元素个数。

¶2 `&&` 折叠展开约束满足，要求包展开有效，并且 `N = 0`，或者按 `i` 从小到大，把每个包替换为第 `i` 个元素后 `C` 都满足。¶3 `||` 折叠展开约束满足，要求包展开有效、`N > 0`，并且存在某个 `i` 使 `C` 满足。两者都短路：遇到第一个决定结果的 `i` 之后，后面的元素不再代入。

空包时 `&&` 满足、`||` 不满足，与折叠表达式 `(E && ...)` 为 `true`、`(E || ...)` 为 `false` 的约定一致。¶4 注 1 补充，几个包长度不同时包展开无效，约束不满足，而不是报错：

```cpp title="fold-satisfaction.cpp" error
#include <concepts>
template<class T> concept HasV = requires { T::v; };
struct A { static constexpr int v = 0; };

template<class... Ts> requires (HasV<Ts> || ...)
constexpr int any() { return 1; }
static_assert(any<int, A>() == 1);     // OK: i = 1 时满足

template<class... Ts, class... Us>
  requires (std::same_as<Ts, Us> && ...)
void pairs() {}
int main() {
    pairs<int>();   // error: Ts = <int>，Us = <>，长度不同，约束不满足，没有可行函数
}
```

¶5 两个折叠展开约束的约束里含有等价的未展开包（[[temp.over.link]]）时，它们**适于比较包含**（compatible for subsumption）。`(C<Ts> && ...)` 与 `(D<Ts> && ...)` 展开的是同一个 `Ts`，可以比较；与 `(D<Us> && ...)` 不能比较。比较规则见 [[temp.constr.order#1]]。

### 折叠表达式怎样规范化（[temp.constr.normal] ¶1.5）

只有折叠运算符是 `&&` 或 `||` 的折叠表达式才变成折叠展开约束，`(sizeof(Ts) + ...) > 10` 仍是普通的原子约束。另外，折叠表达式的操作数不能是没加括号的二元表达式，要写 `((sizeof(Ts) > 0) && ...)`。

- ¶1.5.1 左折叠 `( ... Op E )` 与右折叠 `( E Op ... )` 的范式相同。
- ¶1.5.2 带初值的二元折叠把不含包的那一端拆出来，作为普通的合取或析取的操作数：`( E1 Op ... Op E2 )` 在 `E1` 含包时按 `( E1 Op ... ) Op E2` 处理，否则按 `E1 Op ( E2 Op ... )` 处理。
- ¶1.5.3.2 一般情况下，`( E Op ... )` 的范式是一个折叠展开约束，其约束是 `E` 的范式，运算符是 `Op`。

¶1.5.3 还处理一种特殊情况：`E` 里展开的是概念模板形参包（C++26 新增的概念模板形参，[[temp.param]]）。概念包的元素在规范化时就已知，所以 ¶1.5.3.1 直接把它展开成普通的合取或析取。同一个折叠表达式不能既展开概念形参包又展开其他种类的形参包（标准例 5）。标准例 4：

```cpp title="concept-pack.cpp" ok
template<typename T> concept A = true;
template<typename T> concept B = A<T> && true;     // B 包含 A
template<typename T> concept C = true;
template<typename T> concept D = C<T> && true;     // D 包含 C

template<typename T, template<typename> concept... CTs>
concept all_of = (CTs<T> && ...);

template<typename T> requires all_of<T, A, C>
constexpr int f(T) { return 1; }                   // #1：A<T> ∧ C<T>
template<typename T> requires all_of<T, B, D>
constexpr int f(T) { return 2; }                   // #2：B<T> ∧ D<T>

static_assert(f(1) == 2);                          // #2 更受约束
```

!!! impl "Clang 23 报告歧义"
    本机 Clang 23 对上例的 `f(1)` 报告歧义，即还没有实现 ¶1.5.3.1 把概念包展开成合取的规则。标准规定选 #2。

## 概念依赖约束 [temp.constr.concept] {{c++26}}

C++26 允许概念作为模板形参（[[temp.param]]），于是约束里可能出现 `CT<T>` 这样的写法，其中 `CT` 是概念模板形参。在模板定义处不知道 `CT` 是哪个概念，也就无法展开它。

[temp.constr.normal] ¶1.4.1 遇到这种待决的概念时，规范化不展开它，而是得到一个**概念依赖约束**（[[g:concept-dependent-constraint]]）。[temp.constr.concept] ¶1 概念依赖约束是一种原子约束，它的表达式是一个概念特化 `CI`，`CI` 中的概念 `C` 是待决的。

¶2–¶4 检查它是否满足，就是把展开推迟到实参已知的时候：

1. 先把实参代入，确定 `C` 是哪个概念。在直接语境中得到无效的概念特化，约束不满足。
2. 求代入后的概念特化的范式 `CI′`。注 1 提醒，这一步可能 IFNDR。
3. 把 `CI′` 中各原子约束映射里出现的 `C` 的形参，换成相应的实参，得到 `CI″`。
4. `CI″` 满足，原约束就满足。注 2 指出，这可能递归地引出更多概念依赖约束。

```cpp run title="concept-dependent.cpp" ok
template<typename>
concept C = true;

template<typename T, template<typename> concept CC>
concept D = CC<T>;

template<typename U,
         template<typename> concept CT,
         template<typename, template<typename> concept> concept CU>
int f() requires CU<U, CT> { return 0; }

int i = f<int, C, D>();
int main() {}
```

`f` 的关联约束是一个概念依赖约束，表达式是 `CU<U, CT>`。调用时把 `D` 代入 `CU`，得到 `D<U, CT>`，它的范式是 `CC<T>`（映射 `T ↦ U, CC ↦ CT`），又是一个概念依赖约束。再把 `C` 代入 `CC`，规范化得到原子约束 `true`，满足。

[temp.constr.normal] ¶3 例 3 对比了两种情况：`requires CT<U*, C>` 中 `CT` 是概念形参，范式是概念依赖约束；`requires CC<U*, C>` 中 `CC` 是具体的概念，只是实参里有一个概念 `C`，规范化时直接代入展开，最终得到原子约束 `true`。

概念依赖约束不能参与强弱比较：含有它的关联约束不适于包含（[[temp.constr.order#3]]），因为它将来展开成什么在定义处无从知道。

<details class="fine" markdown="1"><summary>其余条文</summary>

[temp.constr.general] ¶1 是一个注，说明本节的结构：约束的抽象语法和满足规则在 [temp.constr.constr]，约束与声明的关联在 [temp.constr.decl]，按约束对声明排序在 [[temp.constr.order]]。约束是标准用来描述语义的抽象结构，程序员写出的是 *constraint-expression*。

[temp.constr.decl] ¶1 的语法 `constraint-expression: logical-or-expression` 说明约束表达式在语法上就是一个普通的 *logical-or-expression*。

</details>

## 实现视角

!!! impl "缓存、诊断与修饰名"
    - Clang 缓存原子约束的满足结果，键是原子约束加模板实参。¶3 规定结果不稳定时 IFNDR，实践中就表现为直接复用第一次的结果。
    - 比较约束强弱要把约束化成析取范式或合取范式，最坏情况下子句数随约束规模指数增长（[[temp.constr.order]]）。实际代码里的约束很少复杂到这个程度。
    - Clang 报告约束不满足时，会沿着规范化的结构往下，指出是哪个原子约束失败、为什么失败。
    - 函数模板的签名包括尾随 *requires-clause*（[[defns.signature.templ]]），所以约束会进入修饰名。Itanium ABI 用 `Q` 引出约束表达式，例如本机 Clang 23 把 `template<class T> int g(T) requires C<T>` 的特化 `g<int>` 修饰为 `_Z1gIiEiT_Q1CIS0_E`。

## 历史与演进

!!! history
    - C++20 通过 [[P0734R0]] 把 Concepts TS 的约束机制并入标准，同时去掉了 TS 中 `concept bool` 形式的函数概念和变量概念，概念统一写成 `concept C = ...;`。
    - C++26 加入概念模板形参和随之而来的概念依赖约束（[[P2841]]），以及折叠展开约束（[[P2963R3]]）。在此之前，`(C<Ts> && ...)` 是一个不可分解的原子约束。

## 常见误解

!!! pitfall "约束就是编译期的 `bool` 表达式"
    满足检查按合取、析取逐个原子约束进行，替换失败只让那个原子约束不满足，短路时后面的操作数根本不代入。这与 `static_assert(expr)` 的求值方式不同。

!!! pitfall "`!C<T>` 是 `C<T>` 的否定"
    比较强弱时，`!C<T>` 是一个新的原子约束，与 `C<T>` 没有任何逻辑联系。检查满足时，替换失败的 `!E` 也是不满足。

!!! pitfall "同样的表达式写两遍就能比较强弱"
    原子约束必须来自同一处出现，也就是通过同一个概念引入。

!!! pitfall "`requires (T::value)` 检查 `value` 是否存在"
    它检查的是 `T::value` 的值，而且要求类型恰好是 `bool`。检查存在性写 `requires { T::value; }`。

## 思考题

!!! question "思考题 1"
    给定 `template<class T> concept HasX = requires { T::x; };`，下面两个约束对 `T = int` 是否满足？

    ```cpp
    template<class T> requires (!HasX<T>) void f(T);              // (a)
    template<class T> requires (!requires { T::x; }) void g(T);   // (b)
    ```

<details markdown="1">
<summary>答案</summary>

都满足。(a) 的原子约束是 `!HasX<T>`，代入 `T = int` 得 `!HasX<int>`，代入本身没有失败；`HasX<int>` 的值为 `false`，取反为 `true`。(b) 的原子约束是 `!requires { T::x; }`，requires 表达式内部的无效表达式不是替换失败，只让 requires 表达式的值为 `false`（[[expr.prim.req]]），取反为 `true`。

对比 `requires (!sad<typename T::type>)`：那里的 `typename T::type` 在原子约束的直接语境中替换失败，原子约束直接不满足。
</details>

!!! question "思考题 2"
    为什么规范化要把概念展开，而不是把 `C<T>` 整体当作一个原子约束？

<details markdown="1">
<summary>答案</summary>

如果 `C<T>` 是不可分解的原子，单就 `D = C<T> && E<T>` 比 `C` 强而言已经够用。但展开带来两项额外的能力。一是跨概念的相同：`Add1`、`AddOne` 两个不同的概念都基于 `C`，展开后的原子约束可以相同（[temp.constr.atomic] 例 1）。二是概念内部的结构可以参与比较：`std::signed_integral<T>` 展开后含有 `std::integral<T>` 的原子约束，所以它比任何直接要求 `std::integral<T>` 的约束都强。代价是范式可能很大，复合映射也可能形成无效类型（¶1.4.2 的 IFNDR）。
</details>

!!! question "思考题 3"
    `template<class... Ts> requires (std::integral<Ts> && ...) void f(Ts...);` 在 C++23 和 C++26 中的关联约束分别是什么？

<details markdown="1">
<summary>答案</summary>

C++23 中是一个原子约束，表达式是整个折叠表达式。C++26 中是一个 `&&` 折叠展开约束，其约束是 `std::integral<Ts>` 的范式，即 `std::integral` 定义中的原子约束 `is_integral_v<T>`，映射 `T ↦ Ts`。只有在 C++26 中，它才能与 `(std::signed_integral<Ts> && ...)` 比较强弱。
</details>
