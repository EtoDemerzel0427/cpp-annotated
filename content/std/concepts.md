---
title: 概念库
summary: <concepts> 的总体设计——概念 = 语法要求 + 语义要求；"满足"只看语法、"建模"还要语义；保持相等性（equality preservation）是贯穿整个库的语义公理：相等输入给出相等输出、稳定、默认适用于库中 requires 表达式里的每个表达式，并带来"隐式表达式变体"。
status: done
covers: concepts.general, concepts.equality, concepts.syn
since: c++20
papers: P0898R3, P1754R1
related: concepts.lang, concepts.compare, concepts.object, concepts.callable, temp.constr, temp.constr.order, temp.concept, topics/concepts, res.on.requirements, structure.requirements
tags: 标准库, 概念, 语义要求, 保持相等性
updated: 2026-10-18
---

核心语言的概念机制（[[temp.concept]]、[[temp.constr]]）只回答一个问题：**这组模板实参是否让约束表达式为 `true`**——也就是"能不能编译"。它对"`==` 是不是真的在比较相等""`<` 是不是一个序"一无所知。可是泛型算法真正依赖的恰恰是后者：`sort` 依赖比较器是严格弱序，`find` 依赖 `==` 有等价关系的性质，`filter_view` 依赖谓词对同一元素两次调用给出同样答案。

第 18 章 [concepts] 的任务，就是给这些"语义上的默契"起名字，并把它们写成**规范性要求**。它提供的每个概念都由两半组成：

- **语法要求**（syntactic requirements）：概念定义本身，即那条 `concept C = ...;`，编译器会检查；
- **语义要求**（semantic requirements）：概念定义后面的散文段落（"`T` models `C` only if ..."），编译器不检查，由程序员担保。

¶1 用一句很重的话交代了目的：

!!! std
    The purpose of these concepts is to establish a foundation for equational reasoning in programs.

    这些概念的目的是为程序中的**等式推理**（equational reasoning）奠定基础——即能像在代数中那样"以等代等"地推导代码的行为。

读本章之前，需要先掌握核心语言里的约束与包含：[[temp.constr]]（满足）、[[temp.constr.order]]（包含）以及专题 [[topics/concepts]]。

## 本章的组织（[concepts.general]）

¶2 和表 48 把本章分为五块，全部位于 `<concepts>`：

| 子条款 | 内容 | 本站页面 |
|---|---|---|
| [concepts.equality] | 保持相等性：全章的语义地基 | 本页 |
| [concepts.lang] | 语言相关概念：`same_as`、`convertible_to`、`common_reference_with`、`integral`、`assignable_from`、`swappable`、`constructible_from`…… | [[concepts.lang]] |
| [concepts.compare] | 比较概念：*`boolean-testable`*、`equality_comparable`、`totally_ordered` | [[concepts.compare]] |
| [concepts.object] | 对象概念：`movable`、`copyable`、`semiregular`、`regular` | [[concepts.object]] |
| [concepts.callable] | 可调用概念：`invocable`、`predicate`、`relation`、`strict_weak_order`…… | [[concepts.callable]] |

`<iterator>`、`<ranges>`、`<compare>`（`three_way_comparable`，见 [[cmp.concept]]）中的概念都建立在本章之上。

## 满足 vs 建模：两个层次的"符合"

这是整个概念库最重要的区分，但定义并不在本章，而在库总则：

!!! std
    A sequence Args of template arguments is said to *model* a concept C if Args satisfies C and meets all semantic requirements (if any) given in the specification of C. —— [[res.on.requirements#1]]

    一组模板实参**建模**（*model*）概念 C，当且仅当它**满足**（*satisfy*）C，并且符合 C 的规格中给出的全部语义要求。

- **满足**（[[g:constraint-satisfaction]]）是核心语言概念：约束表达式规范化后，原子约束代入后求值为 `true`（[[temp.constr.atomic]]）。编译器能判断。
- **建模**（[[g:models-concept]]）是库概念：满足 + 语义要求。编译器原则上无法判断。

后果由 [[res.on.requirements#2]] 和 ¶3 规定：

- 如果程序的**有效性或含义依赖于**某组实参是否建模某概念，而该概念被满足却未被建模——程序 {{ifndr}}；
- 如果某声明的约束所带的语义要求在使用点未被建模——程序 {{ifndr}}。

再配合 [[structure.requirements#9]]：当库函数的约束引用了概念，那个概念的语义要求也会**一并施加**到对该函数的使用上。所以给 `std::ranges::sort` 传一个满足 `strict_weak_order` 语法但实际上不是严格弱序的比较器（比如 `<=`），程序就是 IFNDR——不是"排序结果不对"，而是整个程序失去了标准的保证。

!!! note "为什么是 IFNDR 而不是 UB"
    违反语义要求在概念上是"程序本身不合规"（编译期性质），而不是"某次执行做了非法的事"（运行期性质）。所以标准把它归为 ill-formed，只是不要求诊断——因为诊断它需要证明任意代码的数学性质，原则上不可判定。实践中的效果与 UB 很接近：实现可以假设语义要求成立并据此优化或写算法。

还有一个微妙之处，[[structure.requirements#8]]：**概念所要求的操作不必是全函数**（total function）。`double` 的 `<` 在 NaN 上违反 `totally_ordered` 的语义要求，但这**不影响** `double` 建模 `totally_ordered`——NaN 只是不在 `<` 的**定义域**（下文 ¶2）里。于是"`double` 建模 `totally_ordered`"与"不要把 NaN 传给 `ranges::sort`"同时成立。

## 保持相等性（[concepts.equality]）

这一节只有八段，却是理解整个概念库（以及 `<iterator>`、`<ranges>` 里所有语义要求）的钥匙。几乎每个概念的语义段落最终都归结为："某某表达式保持相等性，并且……"。

### 输入、输出与操作数（¶1）

!!! std
    An expression is *equality-preserving* if, given equal inputs, the expression results in equal outputs.

    一个表达式是**保持相等性的**（[[g:equality-preserving]]，*equality-preserving*），当且仅当：给定相等的输入，它产生相等的输出。

这正是数学里"函数"的定义：同样的自变量，同样的函数值。¶1 接着精确定义了"输入"和"输出"：

- **输入** = 表达式的**操作数**集合；
- **输出** = 表达式的**结果**，加上**被表达式修改的所有操作数**。

第二点很关键：`a = std::move(b)` 的输出不只是 `=` 的返回值，还包括被修改后的 `a` 与 `b`。所以"赋值保持相等性"的意思是：从相等的 `(a, b)` 出发，执行后得到相等的 `a`、相等的 `b`、相等的返回值。

那么什么算"操作数"？¶1 给了一个专门的定义——**只由下列成分构成的最大子表达式**：

- ¶1.1：*id-expression*（[[expr.prim.id]]），即变量名；
- ¶1.2：对 `std::move`、`std::forward`、`std::declval` 的调用。

例 1：`a = std::move(b)` 的操作数是 `a` 和 `std::move(b)`——`std::move(b)` 整体是一个操作数，而不是"`b` 再经过一次函数调用"。这个定义的意图是把 `requires` 表达式里的变量（以及它们的值类别变换）当作"自变量"，而把其余部分（运算符、成员调用）当作被考察的"函数"。

!!! note "“相等”不是 `==`"
    这里的"相等"（*equal*）是**抽象的值相等**——两个对象表示同一个值——而不是"`==` 返回 `true`"。正因如此，`equality_comparable` 的语义要求（[[concept.equalitycomparable#2]]）才有意义：它要求 `a == b` 为 `true` **当且仅当** `a` 与 `b` 相等。`==` 被要求去"反映"相等，而不是"定义"相等。对于没有 `==` 的类型（例如某些 `semiregular` 类型），"相等"仍然是有意义的数学概念。

### 定义域（¶2）

并不是所有输入都必须合法。例 2：对整数 `a / b`，`b == 0` 时表达式没有良定义，但这不妨碍 `a / b` 是保持相等性的。表达式要求良定义的那些输入值的集合称为它的**定义域**（[[g:expression-domain]]，*domain*）。

定义域给"非全函数"留了余地：NaN 不在 `double` 的 `<` 的定义域里；指向不同数组的指针不在 `<` 的定义域里（[[expr.rel]]）；`assignable_from` 的注 1 甚至说，如果对 `x` 赋值会改变 `y`，那么 `x = y` 很可能不在 `=` 的定义域内。

### 稳定性（¶3）

!!! std
    Expressions required to be equality-preserving are further required to be stable: two evaluations of such an expression with the same input objects are required to have equal outputs absent any explicit intervening modification of those input objects.

    被要求保持相等性的表达式还被要求是**稳定的**：用**同一批**输入对象对它求值两次，只要中间没有显式修改这些对象，输出就必须相等。

¶1 说的是"相等的输入"（可以是不同对象），¶3 说的是"同一个对象、不同时刻"。注 1 列出了稳定性实际禁止的东西：

- 对象的值自发变化；
- 被**另一个线程**修改（所以概念的语义要求天然假设了没有数据竞争）；
- 作为**不修改型表达式的副作用**而变化（比如 `const` 成员函数偷偷改 `mutable` 计数器，并且这种变化能被别的保持相等性的表达式观察到）；
- 修改**另一个**对象时顺带改了它（别名）——如果库函数可以通过保持相等性的表达式观察到。

稳定性给了泛型代码一个强有力的推理工具：**刚刚观察到的值，下次再看还是它**。`ranges::filter_view` 缓存 `begin()` 的设计就依赖于此——见下面的例子。

### 默认规则与豁免注释（¶4）

!!! std
    Expressions declared in a *requires-expression* in the library clauses are required to be equality-preserving, except for those annotated with the comment "not required to be equality-preserving."

    库条款中 requires 表达式里声明的表达式，**默认**都要求保持相等性；只有带了"not required to be equality-preserving"注释的除外。

这是一个"默认开启"的全局规则，所以你在 `equality_comparable` 的定义里看不到"`==` 要保持相等性"这句话——它已经由 ¶4 隐含了。最著名的豁免是 `invocable`：

```cpp
template<class F, class... Args>
  concept invocable = requires(F&& f, Args&&... args) {
    invoke(std::forward<F>(f), std::forward<Args>(args)...); // not required to be equality-preserving
  };
```

于是随机数生成器可以建模 `invocable`，但不能建模 `regular_invocable`——后者的唯一区别就是撤销了这个豁免（[[concept.regularinvocable]]）。其他常见的豁免还有输入迭代器的 `++i`、`*i` 等（单趟遍历的本质就是"不稳定"）。

¶4 后半句：被豁免的表达式**可以**保持相等性，只是不被要求。

### 谁会被修改：记号约定（¶5）

一个表达式**修改**（*modify*）它的某个输入，指它以"能被保持相等性的表达式观察到"的方式改变该输入的值。¶5 规定了一个读 requires 表达式的约定：

- 操作数若是**非 const 的左值或右值**，**可能**被修改；
- 操作数若是 **const 左值或 const 右值**，**必须不**被修改。

判断 cv 限定和值类别时，假设每个模板类型参数都表示一个无 cv 限定的、完整的、非数组的对象类型。所以在 `requires(T a, const T c)` 中，`a` 是可修改的左值，`c` 是不可修改的左值，`std::move(a)` 是可修改的右值。

### 隐式表达式变体（¶6–¶8）

这是本节最微妙、也最常被忽略的规则。

!!! std
    Where a *requires-expression* declares an expression that is non-modifying for some constant lvalue operand, additional variations of that expression that accept a non-constant lvalue or (possibly constant) rvalue for the given operand are also required ...

    如果 requires 表达式声明了一个对某个 const 左值操作数不做修改的表达式，那么把该操作数换成非 const 左值或（可能为 const 的）右值后的**变体**也同样被要求……

背后的直觉：概念作者写 `c == d`（`c`、`d` 都是 `const T`）想表达的是"`T` 的对象可以用 `==` 比较"，而不是"只有 const 左值才能比较"。如果每个概念都要把 `const`/非 `const`、左值/右值的组合穷举出来，概念定义会膨胀数倍。于是标准规定：只写 const 左值版本，其余组合**隐含**被要求，并且必须满足同样的语义（包括"不修改"）。这些被隐含要求的表达式叫**隐式表达式变体**（[[g:implicit-expression-variation]]，*implicit expression variations*）。

例外是：如果某个变体被**显式**以不同语义声明了，就不再隐式要求。例 3 演示了全部情形：

```cpp
template<class T> concept C = requires(T a, T b, const T c, const T d) {
  c == d;           // #1
  a = std::move(b); // #2
  a = c;            // #3
};
```

- #1 不修改任何操作数；#2 修改两个操作数；#3 只修改 `a`（¶7.1）；
- #1 隐式要求 `c == b`、`std::move(c) == d`、`a == std::move(b)` 等全部 15 种组合，并且它们都**不修改**操作数（¶7.2）；
- #3 隐式要求 `a = b` 和 `a = std::move(c)`，但**不**隐式要求"第二操作数是非 const 右值"的版本——因为 #2 已经显式声明了它，且语义不同（#2 允许修改 `b`，¶7.3）。

¶6 最后一句是关键的法律细节：**实现在多大程度上检查这些变体的语法，是未指明的**。于是例 4：

```cpp
struct T {
  bool operator==(const T&) const { return true; }
  bool operator==(T&) = delete;
};
```

`T` 满足 `C` 的显式语法要求，但非 const 左值的 `t1 == t2` 选中了被删除的重载——隐式变体不成立。所以 `T` **满足但不建模** `C`，并且"实现是否把要求 `C<T>` 的程序诊断为非良构"是**未指明的**（¶8）。

这不只是纸面上的问题。libc++ 只检查显式写出的 const 左值形式，于是 `std::equality_comparable<T>` 为 `true`，`ranges::find` 的约束检查顺利通过，然后在函数体内部用非 const 左值比较时炸掉：

```cpp run title="implicit-variation.cpp" error
#include <algorithm>
#include <concepts>
#include <vector>

struct T {
  bool operator==(const T&) const { return true; }
  bool operator==(T&) = delete;
};
static_assert(std::equality_comparable<T>);   // OK：只检查了 const 左值形式

int main() {
  std::vector<T> v(3);
  T key;
  auto it = std::ranges::find(v, key);   // error: 在 ranges::equal_to 内部选中了被删除的 operator==
  (void)it;
}
```

Clang + libc++ 的报错位于库头文件 `ranges_operations.h` 中（"overload resolution selected deleted operator '=='"），而不是在约束检查处——这正是"满足但不建模"的典型症状：概念的防线被绕过，错误在模板深处爆发。

## 为什么保持相等性是整个库的钥匙

把上面几条合起来，保持相等性给了泛型算法三项"免费"的推理能力：

1. **可以重复求值**。算法可以对同一元素多次调用谓词或比较器，并相信结果一致（`sort` 的实现会反复比较同一对元素）。
2. **可以缓存**。`filter_view`、`drop_while_view` 等缓存第一次 `begin()` 的结果以满足 `range` 概念对 `begin()` 的摊还 O(1) 要求——缓存之所以正确，就是因为谓词被要求是 `regular_invocable`（经由 `indirect_unary_predicate`）。
3. **可以以等代等**。`a == b` 为真时，任何保持相等性的表达式中把 `a` 换成 `b` 结果不变——这就是 ¶1"equational reasoning"的字面意思。

反面教材：一个有状态的谓词让 `filter_view` 两次遍历给出不同结果。

```cpp run title="stateful-predicate.cpp" ifndr
#include <ranges>
#include <cstdio>

int main() {
    int calls = 0;
    auto first_three = [&calls](int) { return calls++ < 3; };  // 结果取决于调用次数，不保持相等性
    auto v = std::views::iota(0, 6) | std::views::filter(first_three);
    for (int i : v) std::printf("%d ", i);   // 第一遍：0 1 2
    std::puts("");
    for (int i : v) std::printf("%d ", i);   // 第二遍：0（begin() 已被缓存，其余元素全被筛掉）
    std::puts("");
}
```

`filter` 要求 `indirect_unary_predicate`，后者细化 `predicate` → `regular_invocable`。`first_three` **满足**它（语法上能调用、返回 `bool`），但不**建模**它（不保持相等性、修改了状态）。依 [[res.on.requirements#3]]，程序 {{ifndr}}。实际运行中 libc++ 打印 `0 1 2` 和 `0`——这只是一种可能的表现，标准对此不再作任何保证。

## 头文件概要（[concepts.syn]）

`<concepts>` 的概要第一行是 `// all freestanding`：整个头文件在独立实现（[[g:freestanding-implementation]]）中也必须提供——它只有概念定义和一个 CPO，不需要任何运行时支持。

概要里只有一个不是概念的东西：

```cpp
namespace ranges {
  inline namespace unspecified {
    inline constexpr unspecified swap = unspecified;
  }
}
```

`ranges::swap` 是一个**定制点对象**（[[g:customization-point-object]]，[[customization.point.object]]），详见 [[concept.swappable]]。它被放进一个未指明名字的内联命名空间，是为了让 `std::ranges` 里的类型可以有名为 `swap` 的隐藏友元（hidden friend）而不与这个对象冲突：对象的名字位于内层命名空间，隐藏友元的名字属于外层 `std::ranges`，二者不在同一作用域。

其余部分就是本章全部概念的声明，用 `see below` 指向各自的条款。

## 概念的层级与"可包含"的写法

本章的概念彼此**按名字**引用，形成一张细化（refinement）网：

```text
destructible ← constructible_from ← default_initializable
                                  ← move_constructible ← copy_constructible
movable   = object ∧ move_constructible ∧ assignable_from<T&,T> ∧ swappable
copyable  = copy_constructible ∧ movable ∧ assignable_from<T&, (const) T(&)> …
semiregular = copyable ∧ default_initializable
regular   = semiregular ∧ equality_comparable

invocable ← regular_invocable ← predicate ← relation ← equivalence_relation
                                                    ← strict_weak_order
equality_comparable ← totally_ordered
```

按 [[temp.constr.order]]，只有**同一个概念**（经规范化后来自同一处的原子约束）才能参与包含。所以标准库的概念总是写成"`concept B = A<T> && ...`"而不是把 `A` 的定义抄一遍——这保证了 `regular<T>` 包含 `semiregular<T>`，重载 `f(regular auto)` 比 `f(semiregular auto)` 更受约束。

几个刻意为包含设计的定义：

- `same_as<T, U>` 写成 `same-as-impl<T, U> && same-as-impl<U, T>`，使 `same_as<T, U>` 与 `same_as<U, T>` **互相包含**（[[concept.same]]）。
- 反过来要注意**纯语义的细化**：`regular_invocable<F>` 定义为 `invocable<F>`，`strict_weak_order<R, T, U>` 与 `equivalence_relation<R, T, U>` 都定义为 `relation<R, T, U>`。规范化会把概念 id 展开成其定义的范式（[[temp.constr.normal]]），所以它们与被细化的概念规范化后**完全相同**——二者互相包含，谁也不比谁更受约束。用 `invocable` 与 `regular_invocable` 分别约束两个重载，调用会是歧义的（见 [[concepts.callable]]）。纯语义细化只是给程序员看的契约，不参与重载决议。
- 直接写类型特征（`is_integral_v<T>`）的地方都包了一层概念（`integral`），原因同上：原子约束 `is_integral_v<T>` 只有出现在同一个概念定义里时才是"同一个"。

## 历史

- 概念库由 [[P0898R3]]（Standard Library Concepts）在 C++20 引入，脱胎于 Ranges TS；最初命名是 `PascalCase`（`EqualityComparable`），由 [[P1754R1]] 改为现在的 `snake_case`。
- 保持相等性、语义要求、"满足 vs 建模"的框架在 Ranges TS 中就已成型，并随 P0898 一起进入 IS。
- C++20 之后的主要变化集中在比较概念（*`boolean-testable`*、对仅可移动类型的支持，见 [[concepts.compare]]）。

## 陷阱

!!! pitfall "static_assert 通过 ≠ 类型可以安全使用"
    `static_assert(std::regular<T>)` 只证明了**满足**。`T` 的 `==` 可能不是等价关系，复制可能不产生相等的对象——这些都只能靠代码审查和测试。

!!! pitfall "以为 const 版本就够了"
    概念只显式要求 const 左值形式，但隐式变体要求非 const、右值形式也可用且语义相同。只为 `T&` 提供不同语义（或删除）的重载，会让类型"满足但不建模"，错误可能延后到库实现深处才爆发。

!!! pitfall "有状态的函数对象"
    凡是走 `predicate`/`regular_invocable`/`indirect_*` 约束的地方，有状态的、依赖调用次数的函数对象都违反语义要求。旧式 `std::` 算法（基于 *Cpp17* 要求）对此通常也有类似的"不得修改"规定，ranges 算法则通过概念把它形式化了。

## 思考题

!!! question "思考题"
    1. `requires(const T a, const T b) { a < b; }` 隐式要求了哪些表达式？如果 `T` 另有 `bool operator<(T&&) const` 并且它会"偷走"右操作数的资源，`T` 是否建模该概念？
    2. `std::uniform_int_distribution<int>` 加 `std::mt19937&` 能否建模 `invocable`？能否建模 `regular_invocable`？编译器能区分二者吗？
    3. 为什么 ¶3 的稳定性要求可以被解读为"禁止数据竞争"？它与 [[intro.races]] 的数据竞争 UB 有何不同？

<details markdown="1">
<summary>展开查看答案与解析</summary>

1. 隐式要求了把 `a`、`b` 各自替换为非 const 左值、const 右值、非 const 右值后的所有组合（¶6），并且这些变体都必须不修改操作数（¶7.2 的类比）。`operator<(T&&)` 会在右操作数为非 const 右值时被选中并修改它——违反了"不修改"的语义，因此 `T` 满足但不建模（除非该变体被另一个表达式以不同语义显式声明）。依 ¶6 末句，实现是否诊断是未指明的。
2. 能建模 `invocable`（调用表达式被豁免，不要求保持相等性，[[concept.invocable#2]]）；不能建模 `regular_invocable`（[[concept.regularinvocable#2]]）。编译器不能区分：二者语法完全相同（[[concept.regularinvocable#3]]），`std::regular_invocable<...>` 同样为 `true`。
3. 注 1 明说稳定性禁止"来自另一线程的修改"。但这是**语义要求**层面的约束：违反它使程序 IFNDR（[[res.on.requirements]]），即便那个并发修改本身是用原子操作完成、按 [[intro.races]] 并不构成数据竞争。也就是说概念的要求比"无数据竞争"更强：即使没有 UB，值在算法观察期间也不能变。
</details>

## 小结

!!! summary
    - 每个库概念 = 语法要求（编译器检查，决定**满足**）+ 语义要求（程序员担保，决定**建模**）。满足但不建模而程序依赖它 → {{ifndr}}（[[res.on.requirements]]）。
    - **保持相等性**：相等输入 → 相等输出；输入 = 操作数（变量名及其 `move`/`forward`/`declval`），输出 = 结果 + 被修改的操作数。
    - 允许有**定义域**（非全函数）；要求**稳定**（同一对象两次求值结果相同）。
    - 库 requires 表达式中的表达式**默认**都要求保持相等性，除非注明"not required to be equality-preserving"（如 `invocable`）。
    - 非 const 操作数可能被修改，const 操作数不得被修改；对 const 左值不修改的表达式隐含要求其**隐式表达式变体**，实现可以不检查——这是"满足但不建模"的高发区。
    - 概念之间按名字细化，使包含关系成立；`<concepts>` 全部 freestanding。
