---
title: 模板约束
summary: 约束的五种形式（合取、析取、原子约束、概念依赖约束、折叠展开约束）及其满足规则；原子约束以同一出现确定身份，且必须恰好为 bool；声明的关联约束如何组成；规范化如何把约束表达式展开成范式。按约束偏序见独立页面。
status: done
covers: temp.constr.general, temp.constr.constr, temp.constr.constr.general, temp.constr.op, temp.constr.atomic, temp.constr.concept, temp.constr.fold, temp.constr.decl, temp.constr.normal
since: c++20
papers: P0734R0, P2963R3, P2841
related: temp.constr.order, temp.concept, expr.prim.req, temp.names, temp.param, over.match.viable, over.match.best, temp.deduct, topics/concepts
tags: 概念, 约束, 规范化, 原子约束, 折叠展开约束
updated: 2026-10-17
---

[temp.constr] 定义了 C++20 概念（concepts）的语义核心。语法上，约束写成普通的表达式（`C<T> && requires {...}`）；语义上，标准却不把它当作一个 `bool` 表达式来求值，而是先把它**规范化**（normalize）成一棵由合取、析取和原子约束构成的树，再逐个原子约束检查是否**满足**（satisfaction）。

为什么要这么复杂？因为约束要同时服务两件事：

1. 满足检查：给定实参，约束是否成立？这要求能容忍替换失败（`T::value` 对 `int` 无效时，结果应是不满足，而不是编译错误），并且能短路。
2. 偏序比较：两个重载都满足时，哪个更受约束？这要求能比较两个约束的结构，判断一个是否蕴含另一个（[[temp.constr.order]]）。

如果约束只是一个 `bool` 表达式，第 2 件事就无从做起，因为判断两个任意布尔表达式之间的蕴含关系是不可判定的。规范化把约束化为原子命题的与或组合，原子之间只比较身份而不比较语义，蕴含判断于是成了纯粹的命题逻辑问题。

本页的组织：

| 子节 | 内容 |
|---|---|
| [temp.constr.general] | 总览（注） |
| [temp.constr.constr] | 约束的五种形式与满足规则：[temp.constr.op]、[temp.constr.atomic]、[temp.constr.concept]、[temp.constr.fold] |
| [temp.constr.decl] | 声明的关联约束如何组成 |
| [temp.constr.normal] | 规范化 |
| [temp.constr.order] | 按约束的偏序，见独立页面 [[temp.constr.order]] |

读这一页前，建议先读 [[temp.concept]]（概念定义）和 [[expr.prim.req]]（requires 表达式）；读完后接着读 [[temp.constr.order]]。

## 总览（[temp.constr.general]）

¶1 是一个注，给出本节的结构：约束的抽象语法与满足规则在 [temp.constr.constr]；约束与声明的关联在 [temp.constr.decl]；声明按关联约束偏序在 [temp.constr.order]。

注意"抽象语法"这个词：约束（constraint）不是 C++ 的语法构造，而是标准用来描述语义的抽象结构。程序员写的是 *constraint-expression*，标准把它规范化成约束。

## 约束的五种形式（[temp.constr.constr.general]）

¶1 **约束**（[[g:constraint]]）是对模板实参提出要求的、由逻辑运算与操作数构成的序列。逻辑运算的操作数也是约束。共有五种：

| 种类 | 子节 | 来自 | 引入 |
|---|---|---|---|
| 合取（conjunction，∧） | [temp.constr.op] | `E1 && E2` | C++20 |
| 析取（disjunction，∨） | [temp.constr.op] | `E1 \|\| E2` | C++20 |
| 原子约束（atomic constraint） | [temp.constr.atomic] | 其余一切表达式 | C++20 |
| 概念依赖约束（concept-dependent constraint） | [temp.constr.concept] | `CT<T>`，`CT` 是概念模板形参 | {{c++26}} |
| 折叠展开约束（fold expanded constraint） | [temp.constr.fold] | `(E && ...)`、`(E \|\| ...)` | {{c++26}} |

¶2 受约束的模板要实例化，其关联约束必须得到满足。注 1：仅仅形成类模板、变量模板、别名模板特化的名字，就要求约束满足（[[temp.names#14]]）；重载决议要求函数和函数模板的约束满足（[[over.match.viable]]）。

## 合取与析取（[temp.constr.op]）

¶1 有两种二元逻辑运算：合取与析取。注 1：它们没有对应的 C++ 语法，标准用 ∧ 和 ∨ 表示，以区别于表达式中的 `&&` 和 `||`。

¶2 合取的满足：先检查第一个操作数；若不满足，合取不满足；否则合取满足当且仅当第二个操作数满足。

¶3 析取的满足：先检查第一个操作数；若满足，析取满足；否则析取满足当且仅当第二个操作数满足。

这就是短路，而且比运行期 `&&`/`||` 的短路更彻底：未检查的操作数根本不会被替换，因而其中的替换失败，乃至会导致硬错误的实例化，都不会发生。

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

对 `T = char`，`sizeof(char) > 1` 不满足，第二个操作数不再检查，`get_value<char>()` 也就不会实例化。如果实例化了它，`char::value` 会在函数体内产生硬错误（不在替换的直接语境中，见 [temp.constr.atomic]）。

### 否定不是逻辑运算（¶5 注 2）

¶5 注 2 值得牢记：**逻辑非表达式 `!E` 是一个原子约束**，否定运算符不算作约束上的逻辑运算。这带来两个后果：

1. 不同的否定表达式即使等价，也不互相包含，因为原子约束靠同一出现判定身份（见下文）。
2. 替换失败使原子约束不满足，无论外面有没有 `!`。`!E` 中 `E` 替换失败时，整个 `!E` 不满足，而不是 `E` 为假、`!E` 为真。

```cpp title="negation.cpp" error
template<class T> concept sad = false;

template<class T> int f1(T) requires (!sad<T>);
template<class T> int f1(T) requires (!sad<T>) && true;
int i1 = f1(42);        // error: 歧义——两个 !sad<T> 是不同的表达式出现，不构成包含

template<class T> concept not_sad = !sad<T>;
template<class T> int f2(T) requires not_sad<T> { return 1; }
template<class T> int f2(T) requires not_sad<T> && true { return 2; }
int i2 = f2(42);        // OK: 两个 !sad<T> 都来自 not_sad 的定义——同一出现

template<class T> int f3(T) requires (!sad<typename T::type>);
int i3 = f3(42);        // error: 替换失败 ⇒ 原子约束 !sad<int::type> 不满足（! 无法"翻转"它）

template<class T> concept sad_nested_type = sad<typename T::type>;
template<class T> int f4(T) requires (!sad_nested_type<T>) { return 4; }
int i4 = f4(42);        // OK: 替换失败被包在 concept-id 里：sad_nested_type<int> 为 false，取反为 true
```

`f3` 与 `f4` 的区别值得仔细体会：

- `requires (!sad<typename T::type>)` 的意思是存在嵌套类型 `type`，并且它不 sad；
- `requires (!sad_nested_type<T>)` 的意思是不存在 sad 的嵌套类型（没有嵌套类型也算）。

原因在于，`f3` 的原子约束是整个 `!sad<typename T::type>`，替换失败使其不满足；`f4` 的原子约束是 `!sad_nested_type<T>`，替换 `T = int` 得到 `!sad_nested_type<int>`，这一步没有替换失败；接着求值 concept-id `sad_nested_type<int>`，其内部的替换失败只让它的值为 `false`（[[temp.names#15]]），取反得 `true`。

## 原子约束（[temp.constr.atomic]）

### 定义与参数映射（¶1）

¶1 **原子约束**（[[g:atomic-constraint]]）由一个表达式 `E` 和一个**参数映射**（parameter mapping）组成。参数映射是从 `E` 中出现的模板形参到模板实参的映射，它在规范化受约束实体的声明时通过替换形成，因此可能涉及受约束实体尚未替换的模板形参。注 1：原子约束由规范化形成；`E` 永远不是逻辑与或逻辑或表达式。

理解规范化的关键在于参数映射。例如：

```cpp
template<class T> concept Big = sizeof(T) > 8;
template<class U> void g(U) requires Big<U*>;
```

`g` 的关联约束是原子约束 `sizeof(T) > 8`，参数映射为 `T ↦ U*`。表达式 `E` 是概念定义里的原文 `sizeof(T) > 8`，而不是替换后的 `sizeof(U*) > 8`，替换信息记在映射里。这样才能按同一出现来比较原子约束。

### 身份：同一出现 + 等价的映射（¶2）

¶2 两个原子约束 `e1` 和 `e2` **相同**（identical），当且仅当：

1. 它们由**同一个表达式的同一次出现**（the same appearance of the same *expression*）形成；并且
2. 它们的参数映射的目标相同。精确地说：设想一个模板 `A`，其形参与映射所涉及的形参对应且等价（[[temp.over.link]]），则以 `e1` 映射目标为实参的 `A<...>` 与以 `e2` 映射目标为实参的 `A<...>` 是同一个类型（[[temp.type]]）。

第 1 条最为关键：**两个原子约束要相同，必须来自源代码中的同一个位置**。在两个函数模板的 *requires-clause* 中分别写一遍 `std::is_integral_v<T>`，这是两个不同的出现，产生的原子约束永远不相同，哪怕记号一模一样。只有通过同一个具名概念引入，两处规范化后都追溯到概念定义中的那一处出现，才可能相同。

```cpp title="same-appearance.cpp" error
#include <type_traits>

template<class T> concept Integral = std::is_integral_v<T>;

// 通过具名概念：原子约束 std::is_integral_v<T> 来自 Integral 定义中的同一出现
template<class T> int a(T) requires Integral<T> { return 1; }
template<class T> int a(T) requires Integral<T> && std::is_signed_v<T> { return 2; }
int ra = a(1);     // OK: 选第二个（它包含第一个）

// 直接写两遍：两个 std::is_integral_v<T> 是不同的出现
template<class T> int b(T) requires std::is_integral_v<T> { return 1; }
template<class T> int b(T) requires std::is_integral_v<T> && std::is_signed_v<T> { return 2; }
int rb = b(1);     // error: 歧义
```

Clang 在这种情况下会给出一条很有帮助的提示：相似的约束表达式不被视为等价，除非它们来自同一个概念。

为什么这样设计？判断两个表达式是否相同有两种做法：按语义，但这不可判定；或者按记号，但这很脆弱（`a+b` 与 `b+a` 算不算相同？`T` 与 `U` 是同一个形参吗？宏展开出来的记号算不算？）。同一出现的规则回避了这些问题：**相同性只能通过命名（概念）建立**。这也鼓励程序员把有意义的约束命名为概念。

### 映射的比较：类似别名模板（¶2 注 2）

第 2 条（映射等价）的比较方式类似于带别名模板替换的声明匹配（[[temp.alias]]）。标准例 1：

```cpp run title="mapping.cpp" ok
template<unsigned N> constexpr bool Atomic = true;
template<unsigned N> concept C = Atomic<N>;
template<unsigned N> concept Add1 = C<N + 1>;
template<unsigned N> concept AddOne = C<N + 1>;

template<unsigned M> void f() requires Add1<2 * M>;
template<unsigned M> int f() requires AddOne<2 * M> && true;

int x = f<0>();    // OK: 两个 f 中来自 C 的原子约束都是 Atomic<N>，映射都相当于 N ↦ 2 * M + 1
                   //     第二个包含第一个，选第二个（返回 int）
int main() {}
```

尽管 `Add1` 和 `AddOne` 是两个不同的概念，它们都展开到 `C<N + 1>`，再到 `C` 定义中同一处出现的 `Atomic<N>`。映射 `N ↦ 2 * M + 1` 在两边是等价的表达式（按 [[temp.over.link]] 比较），于是原子约束相同。

但如果映射功能等价而不等价（例如 `2 * N` 与 `N * 2`），而程序的含义又取决于它们是否相同，则程序 {{ifndr}}：

```cpp title="func-equiv.cpp" ifndr
template<unsigned N> constexpr bool Atomic = true;
template<unsigned N> concept C = Atomic<N>;
template<unsigned N> concept Add1 = C<N + 1>;

template<unsigned N> void f2() requires Add1<2 * N>;
template<unsigned N> int f2() requires Add1<N * 2> && true;
void h2() {
    f2<0>();   // IFNDR: 需要判断两个功能等价但不等价的原子约束是否包含
}
```

Clang 对此报告调用歧义（这是 IFNDR 允许的结果之一）。

### 满足：替换、恰好为 bool、常量求值（¶3）

¶3 判定原子约束是否满足的步骤如下：

1. 先把参数映射和模板实参替换进表达式。
2. 若替换在原子约束的**直接语境**（immediate context，[[temp.deduct.general]]）中产生无效类型或表达式，约束不满足（不是错误）。
3. 否则，必要时进行左值到右值转换，然后 **`E` 必须是类型为 `bool` 的常量表达式**。
4. 约束满足当且仅当 `E` 求值为 `true`。

第 3 步要求类型恰好是 `bool`，这一点非常严格：不进行任何隐式转换，`int`、带 `operator bool` 的类类型都不行，违反时程序非良构，而不只是约束不满足。

```cpp title="must-be-bool.cpp" error
template<class T> struct W { static constexpr int value = 1; };

template<class T> requires (W<T>::value) void f(T) {}          // 原子约束类型是 const int
template<class T> requires (bool(W<T>::value)) void g(T) {}    // OK: 显式转换为 bool

int main() {
    f(0);    // error: 原子约束必须是 bool 类型（找到 const int）
    g(0);    // OK
}
```

为什么不允许隐式转换到 `bool`？设计上的理由是，约束的结果应当是一目了然的 `true`/`false`，而一个可以转换为 `bool` 的类对象可能有任意复杂的 `operator bool`，甚至在不同语境下转换结果不同。更实际的理由是防止误写：`requires (T::value)` 的本意可能是检查 `T::value` 存在（应写 `requires { T::value; }`），如果 `T::value` 是 `int` 并被默默转换，错误就被掩盖了。

标准例 3 强调这是硬错误：错误发生在满足检查阶段，即使另一个候选更好也无法挽救：

```cpp title="not-bool-hard-error.cpp" error
template<typename T> struct S {
    constexpr operator bool() const { return true; }
};

template<typename T> requires (S<T>{})
void f(T);                      // #1
void f(int);                    // #2

void g() {
    f(0);    // error: 检查 #1 的约束时，表达式 S<int>{} 不是 bool 类型；
             //        即使 #2 是更好的匹配，调用也是非良构的
}
```

!!! impl "编译器现状"
    截至写作时，Clang 23 接受上面的 `g()`：当非模板候选 `f(int)` 是完全匹配时，Clang 跳过了对模板候选的推导与约束检查，因此不会遇到这个错误。去掉 `f(int)` 后，Clang 会正确地报告 "atomic constraint must be of type 'bool'"。按标准，原例的调用是非良构的。

### 直接语境之外的错误是硬错误

第 2 步只吸收直接语境中的替换失败。如果替换触发了某个模板的实例化，而错误发生在那个实例化内部，就是硬错误：

```cpp title="hard-error.cpp" error
template<class T> constexpr bool hard() { return T::value; }

template<class T> requires (hard<T>()) void f(T) {}
void f(long) {}

int main() {
    f(0);    // error: hard<int>() 的函数体中 int::value 无效——不在直接语境中，硬错误
}
```

与之对比，`requires (T::value)` 中 `int::value` 的失败发生在直接语境中，只会使约束不满足。

### 满足结果必须稳定（¶3 末尾）

¶3 最后一句规定：若在程序的不同位置，相同的原子约束和模板实参得到不同的满足结果，则程序 {{ifndr}}。

```cpp title="unstable.cpp" ifndr
template<class T> concept Complete = requires { sizeof(T); };

struct S;
static_assert(!Complete<S>);   // 此时 S 不完整：不满足
struct S {};
static_assert(Complete<S>);    // IFNDR: 同一原子约束、同一实参，结果不同
```

这条规则让实现可以缓存满足结果，同一个 (原子约束, 实参) 只检查一次。Clang 正是这么做的：上例中第二个 `static_assert` 会失败，Clang 报告 `S` 不满足 `Complete`，理由是对不完整类型 `S` 应用了 `sizeof`，用的是第一次的缓存结果。GCC 同样缓存满足结果，并且在某些情况下能检测到同一原子约束的满足值发生了变化，从而报错。两种行为都在 IFNDR 允许的范围内。

!!! warning "不要写检测完整性的概念"
    `Complete<T>`、检测某个函数重载是否已声明之类依赖于程序点的概念，几乎必然触犯 ¶3 的 IFNDR。标准库中没有、也不会有 `std::is_complete`，原因正在于此。

## 概念依赖约束（[temp.constr.concept]）{{c++26}}

C++26 引入了概念模板形参（[[temp.param]]），于是出现了一种新情况：约束中 concept-id 的概念本身是待决的，例如 `CT<T>`，其中 `CT` 是概念模板形参。在模板定义处无法展开 `CT` 的定义，也就无法规范化。

¶1 **概念依赖约束**（[[g:concept-dependent-constraint]]）`CD` 是一个原子约束，其表达式是 concept-id `CI`，`CI` 的 *concept-name* 指称一个待决的概念 `C`。

¶2–¶4 判定 `CD` 是否满足：

1. 把参数映射和模板实参替换进 `C`（确定 `C` 究竟是哪个概念）。若在直接语境中得到无效的 concept-id，不满足。
2. 否则，令 `CI′` 为替换后的 concept-id 的规范形式（注 1：这一步可能 IFNDR）。
3. 把 `CI′` 中各原子约束（包括嵌套的概念依赖约束）的参数映射中出现的 `C` 的模板形参，替换为 `CD` 的参数映射和 `CI` 的实参，得到 `CI″`。
4. `CD` 满足当且仅当 `CI″` 满足（注 2：这可能递归地引起更多概念依赖约束的规范化）。

换句话说，**先推迟，到实例化时再规范化**。

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

`f` 的关联约束是一个概念依赖约束，表达式为 `CU<U, CT>`，映射为恒等映射。调用时把 `D` 代入 `CU` 得到 `D<U, CT>`，其规范形式是 `CC<T>`（映射 `T ↦ U, CC ↦ CT`），这又是一个概念依赖约束；把 `C` 代入 `CC` 后规范化为原子约束 `true`，满足。

概念依赖约束有一个重要限制：**它们不能参与包含关系比较**。含概念依赖约束的关联约束不适于包含（not eligible for subsumption，[[temp.constr.order#3]]），因为在模板定义处无法知道它会展开成什么。

## 折叠展开约束（[temp.constr.fold]）{{c++26}}

在 C++20 中，`(C<Ts> && ...)` 这样的折叠表达式只是一个原子约束，作为一个整体的 `bool` 表达式来检查，不能与 `(D<Ts> && ...)` 比较包含关系。于是下面这种很自然的重载在 C++20/23 中是歧义的：

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

C++26 的 [[P2963R3]] 引入**折叠展开约束**来解决这个问题。

¶1 **折叠展开约束**（[[g:fold-expanded-constraint]]）由一个约束 `C` 和一个折叠运算符（`&&` 或 `||`）构成。它是一个包展开；令 `N` 为包展开形参中的元素个数。

¶2 如果 `&&` 折叠展开约束是有效的包展开，并且 `N = 0`，或者按 `i` 递增的顺序，对每个 `0 ≤ i < N`，把包展开形参替换为第 `i` 个元素后 `C` 都满足，则该约束满足。第一个不满足的 `i` 之后的元素不进行替换。

¶3 如果 `||` 折叠展开约束是有效的包展开、`N > 0`，并且存在最小的 `i` 使替换后 `C` 满足，则该约束满足。第一个满足的 `i` 之后的元素不进行替换。

¶4 注 1：如果包展开中各个包的长度不同，包展开无效，折叠展开约束不满足（而不是错误）。

```cpp title="fold-satisfaction.cpp" error
#include <concepts>
template<class T> concept HasV = requires { T::v; };
struct A { static constexpr int v = 0; };

template<class... Ts> requires (HasV<Ts> || ...)
constexpr int any() { return 1; }
static_assert(any<int, A>() == 1);     // OK: i = 1 时满足

template<class... Ts> requires (std::integral<Ts> || ...)
void none() {}
// none<>();                           // 不满足：|| 折叠要求 N > 0

template<class... Ts, class... Us>
  requires (std::same_as<Ts, Us> && ...)
void pairs() {}
int main() {
    pairs<int>();   // error: Ts = <int>，Us = <>，长度不同 ⇒ 不满足（¶4），没有可行候选
}
```

再对照 C++ 的折叠表达式：空包的 `(E && ...)` 是 `true`，`(E || ...)` 是 `false`。折叠展开约束保持了这个约定（¶2 中 `N = 0` 时满足，¶3 要求 `N > 0`）。

¶5 如果两个折叠展开约束各自的约束都含有一个等价的未展开包（[[temp.over.link]]），它们就**适于比较包含**（compatible for subsumption）。也就是说 `(C<Ts> && ...)` 与 `(D<Ts> && ...)` 可以比较（都展开同一个 `Ts`），而 `(C<Ts> && ...)` 与 `(D<Us> && ...)` 不能。包含规则本身见 [[temp.constr.order#1]]（¶1.3）。

!!! note "什么样的折叠表达式会变成折叠展开约束"
    只有折叠运算符是 `&&` 或 `||` 的折叠表达式，在规范化时才会变成折叠展开约束（[temp.constr.normal]/1.5）。`(sizeof(Ts) + ...) > 10` 这样的表达式仍是普通的原子约束。另外，折叠表达式的操作数不能是未加括号的二元表达式：要写 `((sizeof(Ts) > 0) && ...)` 而不是 `(sizeof(Ts) > 0 && ...)`。

## 受约束的声明（[temp.constr.decl]）

### 约束从哪里来（¶1–¶2）

¶1 模板声明（[[temp.pre]]）或 templated 函数声明（[[dcl.fct]]）可以用 *requires-clause* 加约束。语法上，约束表达式就是一个 *logical-or-expression*：

```text
constraint-expression:
    logical-or-expression
```

¶2 约束也可以通过模板形参列表或形参类型列表中的 *type-constraint* 关联到声明。每种形式都引入额外的 *constraint-expression*。

### 关联约束的组成（¶3）

¶3 声明的**关联约束**（[[g:associated-constraints]]）：

- ¶3.1 若没有引入任何约束表达式，则没有关联约束；
- ¶3.2 若只引入一个，关联约束就是它的范式；
- ¶3.3 否则，关联约束是一个逻辑与表达式的范式，其操作数按下列顺序排列：
    1. 模板形参列表中每个 *type-constraint* 引入的约束表达式（按出现顺序）；
    2. 模板形参列表之后的 *requires-clause* 引入的约束表达式；
    3. 函数声明的形参类型列表中每个 *type-constraint* 引入的约束表达式（即缩写函数模板的 `C auto` 形参，[[dcl.fct]]）；
    4. 函数声明的尾随 *requires-clause* 引入的约束表达式。

**这个顺序决定满足检查时各约束的实例化顺序**，也就决定了短路的效果。

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
template<C2 T> requires C1<T> void f7();      // C2<T> ∧ C1<T>  ——顺序不同！

void f8(C1 auto x) requires C2<decltype(x)>;  // C1<T′> ∧ C2<decltype(x)>，T′ 是虚构的类型形参
int main() {}
```

`f1`、`f2`、`f3` 的关联约束相同，但声明形式不同。按 [[temp.over.link#6]]，模板头等价要求 *type-constraint* 与 *requires-clause* 的写法也一一对应，所以这三种写法的模板头不等价。如果同一个名字分别以其中两种形式声明（例如用 `f2` 的形式声明、用 `f1` 的形式定义），它们接受同样的实参却不对应，按 [[temp.over.link#7]] 程序 {{ifndr}}。声明与定义必须用同一种写法。

`f6` 与 `f7` 的关联约束是 `C1 ∧ C2` 与 `C2 ∧ C1`。在包含关系的意义上它们互相包含（合取的交换性在 [[temp.constr.order]] 中自动成立），但满足检查的顺序不同。

### 类内外约束的等价判断（¶4）

¶4 判断模板化类的实例化特化中某个声明引入的约束表达式 `C1`，是否与类外某个声明的对应约束表达式 `C2` 等价时，要实例化 `C1`；若实例化得到无效表达式，二者不等价。注 1：这在确定一个显式特化声明特化的是哪个成员模板时会发生。

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

对 `A<int>`，#1 的约束实例化为无效的 `C<int::type>`，所以与 `C<int>` 不等价；#2 实例化为 `C<int>`，等价。

!!! lawyer "等价判断 ≠ 满足检查"
    ¶4 比较的是约束表达式本身（实例化后的记号），所以 `C<int::type>` 算作无效表达式。但如果真的调用 `A<int>{}.f(0)`，满足检查走的是规范化：`C` 的范式是原子约束 `true`，其参数映射为空（`true` 中不出现任何模板形参），于是 `int::type` 根本不会被替换，#1 的约束得到满足。两个候选的关联约束都是来自 `C` 定义中同一出现的 `true`，互相包含，调用歧义。Clang 23 正是这样报告的。

## 规范化（[temp.constr.normal]）

### 范式的定义（¶1）

¶1 表达式 `E` 的**范式**（normal form）是按如下规则定义的约束：

| 列表项 | 表达式形式 | 范式 |
|---|---|---|
| ¶1.1 | `( E )` | `E` 的范式（括号透明） |
| ¶1.2 | `E1 \|\| E2` | `E1` 与 `E2` 范式的析取 |
| ¶1.3 | `E1 && E2` | `E1` 与 `E2` 范式的合取 |
| ¶1.4 | concept-id `C<A1, ..., An>` | 见下 |
| ¶1.5 {{c++26}} | `&&`/`\|\|` 的折叠表达式 | 见下 |
| ¶1.6 | 其他任何表达式 `E` | 原子约束：表达式为 `E`，参数映射为恒等映射 |

¶1.2 和 ¶1.3 中的 `||` 和 `&&` 指的是内建运算符的语法形式。规范化发生在模板定义处，此时根本不知道 `&&` 会不会被重载。这也是为什么约束中 `&&` 的操作数必须是 `bool`（原子约束必须是 `bool`），重载的 `operator&&` 永远不会参与。

### concept-id 的范式（¶1.4）

¶1.4 对于 concept-id `CI = C<A1, ..., An>`：

- ¶1.4.1 若 `C` 指称待决的概念（即 `C` 是概念模板形参），`CI` 的范式是概念依赖约束，concept-id 为 `CI`，参数映射为恒等映射。
- ¶1.4.2 否则，先把非待决的概念模板实参 `Ai` 代入 `C` 的约束表达式得到 `CE`（若得到无效 concept-id，{{ifndr}}）；然后对 `CE` 的范式 `N`，把其中原子约束参数映射里出现的 `C` 的模板形参替换为 `CI` 中的对应实参。若替换产生无效类型或表达式，{{ifndr}}。

换言之，**concept-id 在规范化时被内联**：概念的定义被展开，参数映射被复合。具名概念之所以能建立相同性，靠的就是这个机制：无论 `C<X>` 出现在哪里，展开后的原子约束都指向 `C` 定义中的那几处表达式。

标准例 1 展示了 ¶1.4.2 中两个 IFNDR 的区别：

```cpp title="normal-ifndr.cpp" ifndr
template<typename T> concept A = T::value || true;
template<typename U> concept B = A<U*>;
template<typename V> concept C = B<V&>;
```

- `B` 的规范化有效，结果是 `T::value`（映射 `T ↦ U*`）∨ `true`（空映射）。尽管 `T::value` 对指针类型 `T` 永远无效，但在规范化阶段，映射 `T ↦ U*` 本身是合法的类型，问题要等满足检查时才暴露，而那时只是不满足。
- `C` 的规范化使程序 IFNDR：展开 `B<V&>` 时要形成映射 `T ↦ V&*`，即指向引用的指针，这个类型本身无效。

注意 `true` 的映射是空的：原子约束的参数映射只包含表达式中实际出现的模板形参。

### 折叠表达式的范式（¶1.5）{{c++26}}

¶1.5 对 `&&` 或 `||` 的折叠表达式：

- ¶1.5.1 一元左折叠 `( ... Op E )` 与一元右折叠 `( E Op ... )` 的范式相同。
- ¶1.5.2 二元折叠 `( E1 Op ... Op E2 )`：若 `E1` 含未展开的包，范式为 `( E1 Op ... ) Op E2`；否则为 `E1 Op ( E2 Op ... )`。也就是把不含包的初值拆出来，作为普通的合取/析取操作数。
- ¶1.5.3 对 `F = ( E Op ... )`：若 `E` 含未展开的概念模板形参包，则不能同时含其他种类的未展开模板形参包。令 `E′` 为 `E` 的范式：
    - ¶1.5.3.1 若 `E` 含有一个概念模板形参包 `Pk`，且 `E′` 的某个原子约束的参数映射中有 `Pk` 的对应实参，那么所有这样的 `Pk` 的实参个数必须相同（为 `N`），`F` 的范式是把第 `i` 个概念实参代入后的 `E0 Op ... Op EN−1` 的范式，即展开成普通的合取/析取；替换无效则 {{ifndr}}。
    - ¶1.5.3.2 否则，`F` 的范式是折叠展开约束，其约束为 `E′`，折叠运算符为 `Op`。

¶1.5.3.1 的意义在于，概念包在规范化时已知（它们是概念实参，不必等到满足检查），所以可以直接展开成合取。标准例 4：

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

!!! impl "编译器现状"
    截至写作时，Clang 23 对上例的 `f(1)` 报告歧义，即尚未实现 ¶1.5.3.1 中概念包展开为合取的规则。标准规定选择 #2。

标准例 5：同一个折叠表达式混用概念形参包与类型形参包是非良构的：

```cpp
template<typename T, template<typename> concept> struct wrapper {};

template<typename... T, template<typename> concept... CTs>
int f(wrapper<T, CTs>...) requires (CTs<T> && ...);   // error: 折叠表达式含不同种类的模板形参包
```

### 规范化何时发生（¶2–¶3）

¶2 获得约束表达式范式的过程叫**规范化**（[[g:normalization]]）。注 1：确定声明的关联约束时，以及求值指称概念特化的 *id-expression* 时，都要进行规范化。

¶3 标准例 2 和例 3 总结了几种常见情形：

```cpp
template<typename T> concept C1 = sizeof(T) == 1;
template<typename T> concept C2 = C1<T> && 1 == 2;
template<typename T> concept C3 = requires { typename T::type; };
template<typename T> concept C4 = requires (T x) { ++x; };

template<C2 U> void f1(U);      // sizeof(T) == 1（映射 T ↦ U）∧ 1 == 2
template<C3 U> void f2(U);      // requires { typename T::type; }（映射 T ↦ U）
template<C4 U> void f3(U);      // requires (T x) { ++x; }（映射 T ↦ U）
```

**requires 表达式是一个原子约束**，不会被拆开。`C3` 与 `C4` 的 *requires-expression* 各自是一个整体。这意味着分别写了 `requires { a; b; }` 和 `requires { a; }` 的两个约束之间没有包含关系；要让它们可比较，必须把 `a` 提取成一个具名概念：

```cpp
template<class T> concept HasA = requires (T t) { t.a(); };
template<class T> concept HasAB = HasA<T> && requires (T t) { t.b(); };   // HasAB 包含 HasA
```

例 3 展示了概念依赖约束与普通约束的对比：

```cpp
template<typename T> concept C = true;
template<typename T, template<typename> concept CT> concept CC = CT<T>;

template<typename U, template<typename, template<typename> concept> concept CT>
  void f() requires CT<U*, C>;  // 范式：概念依赖约束 CT<T, C>
template<typename U>
  void g() requires CC<U*, C>;  // 范式：原子约束 true——C 是非待决的概念实参，代入后展开
```

## 实现视角

!!! impl "实现视角"
    - 缓存：Clang 和 GCC 都缓存原子约束的满足结果（键为原子约束 + 实参）。¶3 规定不同位置结果不同则 IFNDR，这在实践中就体现为编译器直接复用第一次的结果。
    - 规范化的指数爆炸：包含关系检查要把约束转换为析取范式/合取范式（[[temp.constr.order]]），最坏情况下是指数级的。实现会设置上限；实践中约束很少复杂到触发它。
    - 诊断：Clang 报告约束不满足时，会沿着规范化树向下，指出哪个原子约束失败、为什么失败（例如 "because 'sizeof(T)' would be invalid"）。这是规范化带来的好处之一：失败可以定位到原子约束。
    - 修饰名：受约束的函数模板，约束是签名的一部分（[[intro.defs]] 中函数模板的签名包括 *requires-clause*），Itanium ABI 用 `Q` 前缀编码约束表达式。

## 历史与演进

!!! history "历史与演进"
    - **Concepts TS（2015）**：已有规范化与包含的基本框架；允许 `concept bool` 形式的函数概念与变量概念。
    - **C++20**：[[P0734R0]] 把概念合入工作草案，后续多个提案调整了语法与语义：概念定义改为 `concept C = ...;` 单一形式；原子约束的身份改为按同一出现判定；原子约束必须恰好是 `bool`。
    - **C++26**：概念模板形参带来概念依赖约束（[[P2841]]）；折叠展开约束（[[P2963R3]]）。在 C++23 中，`(C<Ts> && ...)` 是一个不可分解的原子约束。

## 陷阱

!!! pitfall "常见误解"
    - 误以为约束就是编译期的 `bool` 表达式。满足检查按合取/析取逐个原子约束进行，替换失败只让该原子约束不满足，短路时后面的操作数根本不替换。这与 `static_assert(expr)` 的求值模型完全不同。
    - 误以为 `!C<T>` 是 `C<T>` 的否定。在包含关系里，`!C<T>` 是一个新的原子约束，与 `C<T>` 没有任何逻辑联系；在满足检查里，替换失败时 `!E` 也不满足。
    - 误以为同样的表达式写两遍就能比较包含关系。原子约束必须来自同一出现，即通过具名概念引入（¶2）。
    - 误以为 `requires (T::value)` 检查 `value` 是否存在。它检查的是 `T::value` 作为 `bool` 常量表达式的值，且要求类型恰好是 `bool`。检查存在性应写 `requires { T::value; }`。
    - 误以为约束里写个 `int` 会隐式转换成 `bool`。不会，这样写非良构（¶3）。
    - 误以为检测类型是否完整的概念可用。满足结果随程序点变化即 IFNDR（¶3）。

## 思考题

!!! question "思考题 1"
    给定 `template<class T> concept HasX = requires { T::x; };`，下面两个约束对 `T = int` 各自是否满足？

    ```cpp
    template<class T> requires (!HasX<T>) void f(T);       // (a)
    template<class T> requires (!requires { T::x; }) void g(T);   // (b)
    ```

<details markdown="1">
<summary>答案</summary>

两者都满足。(a)：原子约束 `!HasX<T>`，替换 `T = int` 得 `!HasX<int>`，替换本身没有失败；`HasX<int>` 求值为 `false`，取反为 `true`。(b)：原子约束 `!requires { T::x; }`，替换 `T = int` 得 `!requires { int::x; }`，*requires-expression* 内部的无效表达式不是替换失败，而是让 *requires-expression* 求值为 `false`（[[expr.prim.req]]），取反为 `true`。

对比 `requires (!sad<typename T::type>)`：那里的 `typename T::type` 在原子约束的直接语境中替换失败，原子约束直接不满足。
</details>

!!! question "思考题 2"
    为什么规范化要把 concept-id 内联展开，而不是把 `C<T>` 整体当作一个原子约束？

<details markdown="1">
<summary>答案</summary>

如果 `C<T>` 是不可分解的原子，那么 `D<T> = C<T> && E<T>` 规范化为 `C<T> ∧ E<T>`，其中 `C<T>` 是一个原子。单就 `D` 包含 `C` 而言，这已经够用。但内联展开带来两项额外的能力：（1）跨概念的相同性：两个不同概念 `Add1`、`AddOne` 若都基于 `C`，它们展开后的原子约束可以相同（[temp.constr.atomic] 例 1）；（2）概念内部的合取/析取结构可以参与比较：`std::signed_integral<T>` 展开为 `std::integral<T>` 的原子 ∧ `is_signed_v<T>`，于是它包含任何直接要求 `std::integral<T>` 的约束。代价是范式可能很大，以及参数映射的复合可能形成无效类型（¶1.4.2 的 IFNDR）。
</details>

!!! question "思考题 3"
    `template<class... Ts> requires (std::integral<Ts> && ...) void f(Ts...);` 在 C++23 与 C++26 中的关联约束分别是什么？

<details markdown="1">
<summary>答案</summary>

C++23：一个原子约束，表达式是整个折叠表达式 `(std::integral<Ts> && ...)`。C++26：一个折叠展开约束，折叠运算符 `&&`，其约束是 `std::integral<Ts>` 的范式（即 `std::integral` 定义中的原子约束 `is_integral_v<T>`，映射 `T ↦ Ts`）。只有 C++26 中它才能与 `(std::signed_integral<Ts> && ...)` 比较包含关系。
</details>

## 小结

!!! summary "小结"
    | 概念 | 要点 |
    |---|---|
    | 约束的形式 | 合取、析取、原子、概念依赖 {{c++26}}、折叠展开 {{c++26}} |
    | 合取/析取的满足 | 从左到右短路；未检查的操作数不替换 |
    | 原子约束的身份 | 同一表达式的同一出现 + 等价的参数映射；功能等价不等价 ⇒ IFNDR |
    | 原子约束的满足 | 直接语境中替换失败 ⇒ 不满足；否则必须恰好是 `bool` 常量表达式；结果须稳定 |
    | `!E` | 原子约束，不是逻辑运算 |
    | 关联约束的顺序 | 形参列表的 type-constraint → requires-clause → 函数形参的 type-constraint → 尾随 requires-clause |
    | 规范化 | 括号透明；`&&`/`\|\|` 拆分；concept-id 内联展开（复合映射）；`&&`/`\|\|` 折叠 ⇒ 折叠展开约束；其余为原子；requires-expression 是原子 |
