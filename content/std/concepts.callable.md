---
title: 可调用概念
summary: invocable、regular_invocable、predicate、relation、equivalence_relation、strict_weak_order 要求什么；其中三个概念只在语义上加强，编译器无法区分；严格弱序的精确定义，以及用 <= 作比较器为什么会出错。
status: done
covers: *
since: c++20
related: concepts, concepts.compare, concepts.equality, func.def, func.invoke, temp.constr.normal, temp.constr.order, alg.sorting
tags: 标准库, 概念, invocable, predicate, 严格弱序
updated: 2026-10-19
---

!!! tldr
    - `invocable<F, Args...>` 只要求能用 `std::invoke` 调用，包括成员指针；调用可以有状态、有副作用。
    - `regular_invocable` 要求调用是纯的（相等的输入得到相等的结果，不修改任何东西），但语法上与 `invocable` 一字不差，编译器无法区分，也不能靠它选重载。
    - `predicate` 是结果为 *boolean-testable* 的 `regular_invocable`；`relation<R, T, U>` 要求四个方向都是谓词。
    - `strict_weak_order` 要求反自反，并且 `comp` 和"谁也不比谁小"这两种关系都传递。用 `<=` 作排序比较器违反它，在 libc++ 上会越界读写。

[concepts.callable] 描述对[[func.def|可调用类型]]及其实参的要求（[concepts.callable.general] ¶1）。六个概念里，只有 `invocable`、`predicate`、`relation` 有各自的语法定义。`regular_invocable`、`equivalence_relation`、`strict_weak_order` 的定义与它们细化的概念一字不差，区别全在语义要求里，称为纯语义细化。下文的满足、建模、保持相等性等词见 [[concepts]]。

## `invocable`（[concept.invocable]）

```cpp run title="invocable.cpp" ok
#include <concepts>
#include <random>
#include <string>

struct S { int m; int f(int) const { return m; } };
using PMF = int (S::*)(int) const;

static_assert(std::invocable<int S::*, S&>);         // 数据成员指针
static_assert(std::invocable<PMF, const S*, int>);   // 成员函数指针
static_assert(!std::invocable<PMF, S, std::string>);
static_assert(std::invocable<std::mt19937&>);        // 有状态也可以

struct RV { int operator()() && { return 1; } };
static_assert(std::invocable<RV> && !std::invocable<RV&>);

int main() {}
```

```cpp
template<class F, class... Args>
  concept invocable = requires(F&& f, Args&&... args) {
    invoke(std::forward<F>(f), std::forward<Args>(args)...); // not required to be equality-preserving
  };
```

¶1 `invocable` 描述可调用类型 `F` 和一组实参类型 `Args...` 之间的关系：能用库函数 `std::invoke`（[[func.invoke]]）求值。用 `invoke` 而不是 `f(args...)`，意味着它涵盖了 *INVOKE* 的全部形式：普通函数、函数对象、成员函数指针（第一个实参是对象、引用、指针或 `reference_wrapper`）、数据成员指针。

值类别通过 `F&&`、`Args&&...` 和 `std::forward` 原样传递。`invocable<F&, int>` 检查对左值 `F` 的调用，`invocable<F, int>` 检查对右值 `F` 的调用。上面的 `RV` 只有 `&&` 限定的 `operator()`，两者的结果就不同。

定义里的注释说，这个调用表达式不要求保持相等性，这是 [[concepts.equality]] 默认规则的例外。¶2 例 1 说，生成随机数的函数也可以建模 `invocable`。`invocable` 只说能调用，对调用的结果没有任何要求。

## `regular_invocable`：纯函数

```cpp
template<class F, class... Args>
  concept regular_invocable = invocable<F, Args...>;
```

¶1 要求 `invoke` 调用表达式保持相等性，并且不修改函数对象和实参。注 1 说，这一要求取代了 `invocable` 定义中不要求保持相等性的那条注释。¶2 例 1：随机数生成器不建模 `regular_invocable`。¶3 注 2：两者的区别纯粹是语义上的。

保持相等性加上不修改，就是数学意义上的纯函数：相等的输入（包括函数对象本身的状态）总是得到相等的输出，没有可观察的副作用。算法能多次调用同一个函数、缓存结果、调整调用顺序，依赖的都是这一点。

### 纯语义细化不参与包含

```cpp run title="semantic-refinement.cpp" error
#include <concepts>

template<class F> requires std::invocable<F>
int pick(F) { return 1; }

template<class F> requires std::regular_invocable<F>
int pick(F) { return 2; }

int main() {
  return pick([] {});   // error: 调用有歧义
}
```

约束规范化（[[temp.constr.normal]]）时，概念 id 被替换为其定义的范式，`regular_invocable<F>` 和 `invocable<F>` 得到完全相同的原子约束。按 [[temp.constr.order]]，它们互相包含，谁也不比谁更受约束，于是调用有歧义。

所以不能为纯函数重载出一个更快的版本。语义细化只是写给人看的契约：它告诉调用者这里会假设函数是纯的，违反它的程序是 {{ifndr}}（[[res.on.requirements]]）。`std::regular_invocable<std::mt19937&>` 照样为真。

## `predicate` 与 `relation`

```cpp
template<class F, class... Args>
  concept predicate =
    regular_invocable<F, Args...> && boolean-testable<invoke_result_t<F, Args...>>;

template<class R, class T, class U>
  concept relation =
    predicate<R, T, T> && predicate<R, U, U> &&
    predicate<R, T, U> && predicate<R, U, T>;
```

谓词是结果为 *boolean-testable*（[[concept.booleantestable]]）的纯函数。这里有新的语法要求，所以 `predicate` 真正包含 `regular_invocable`。返回 `int`、指针、`bitset::reference` 的函数都可以是谓词，返回 `void` 的不行，返回一个重载了 `&&` 的类型的是满足但不建模。

二元关系 `relation<R, T, U>` 要求在 `T×T`、`U×U`、`T×U`、`U×T` 四个方向上都是谓词。只提供跨类型方向的比较器不满足它。同类型的方向不可少，因为算法既要拿元素与键比较，也要拿元素与元素比较；后面等价关系和严格弱序的性质（自反、传递）也需要在同一个类型上表述。

```cpp run title="relation.cpp" ok
#include <concepts>
#include <functional>
#include <string>

struct LessIntStr {   // 只有跨类型的两个方向
  bool operator()(int, const std::string&) const;
  bool operator()(const std::string&, int) const;
};
static_assert(!std::relation<LessIntStr, int, std::string>);

static_assert(std::equivalence_relation<
  std::equal_to<>, int, long>);
static_assert(std::strict_weak_order<
  std::less<>, int, long>);

int main() {}
```

## `equivalence_relation`（[concept.equiv]）

```cpp
template<class R, class T, class U>
  concept equivalence_relation = relation<R, T, U>;
```

¶1 关系建模 `equivalence_relation`，当且仅当它在实参上施加一个等价关系：自反、对称、传递。`ranges::unique`、`ranges::adjacent_find` 的比较器就是这种关系。

它与 `equality_comparable` 不同，不要求等价就是相等。忽略大小写比较字符串是合法的等价关系，尽管 `"A"` 和 `"a"` 并不相等。

## `strict_weak_order`（[concept.strictweakorder]）

```cpp
template<class R, class T, class U>
  concept strict_weak_order = relation<R, T, U>;
```

¶1 关系建模 `strict_weak_order`，当且仅当它在实参上施加一个**严格弱序**（[[g:strict-weak-ordering|strict weak ordering]]）。

直观地说，严格弱序把所有元素分成若干组，组与组之间排成一条直线，组内的元素彼此不可区分。按姓氏排序的通讯录就是这样，同姓的人在同一组。

¶2 给出精确定义。严格（strict）指反自反：对所有 `x`，`!comp(x, x)`。弱（weak）指要求比全序弱、比偏序强。令 `equiv(a, b)` 为 `!comp(a, b) && !comp(b, a)`，即谁也不比谁小，则要求 `comp` 和 `equiv` 都传递：

- ¶2.1 `comp(a, b) && comp(b, c)` 蕴含 `comp(a, c)`；
- ¶2.2 `equiv(a, b) && equiv(b, c)` 蕴含 `equiv(a, c)`。

¶3 注 1 列出由此能推出的结论：`equiv` 是等价关系（¶3.1）；`comp` 在 `equiv` 的等价类之间诱导出一个良定义的关系（¶3.2）；这个关系是严格全序（¶3.3）。等价类就是上面说的组。

它和 [[concept.totallyordered|totally_ordered]] 约束的对象不同：

| | `strict_weak_order` | `totally_ordered` |
|---|---|---|
| 约束什么 | 比较器 `R` | 类型 `T` 的 `<` 等运算符 |
| 不可区分的元素 | 等价，不一定相等 | 必然相等 |
| 典型用途 | `sort`、`lower_bound`、`set` 的比较器 | 默认比较器 `ranges::less` 对类型的要求 |

`ranges::less` 要求 `totally_ordered_with`，而 `ranges::sort` 对比较器只要求严格弱序（经由 `sortable` 和 `indirect_strict_weak_order`）。所以自定义比较器只需是严格弱序，用默认比较器时元素类型却必须全序。

### 用 `<=` 作比较器

```cpp run title="le-comparator.cpp" ifndr
#include <algorithm>
#include <concepts>
#include <vector>

int main() {
  auto le = [](int a, int b) { return a <= b; };
  // 满足：语法上只是 relation
  static_assert(std::strict_weak_order<decltype(le), int, int>);
  std::vector<int> v(100, 42);
  std::ranges::sort(v, le);   // 不建模：le(x, x) 为 true
}
```

`<=` 违反反自反性。后果不只是排序结果可能不对：很多 `sort` 实现的内层循环靠比较器遇到与枢轴相等的元素时返回 `false` 来停下，用 `<=` 就可能越过数组边界读写。

!!! impl "libc++ 上的表现"
    本机 Clang 23 + libc++ 默认配置下，上面的程序在 `sort` 内部越界访问，以总线错误崩溃（退出码 138）。加上 `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_FAST` 后，越界检查以陷阱指令终止程序；用 `_LIBCPP_HARDENING_MODE_DEBUG` 时会先打印 "Would read out of bounds, does your comparator satisfy the strict-weak ordering requirement?" 再终止。

## 常见误解

!!! pitfall "以为 `regular_invocable` 能在编译期挡住有状态的函数对象"
    挡不住：`std::regular_invocable<std::mt19937&>` 为真。编译器无法判断一个函数是否纯。

!!! pitfall "浮点比较器与 NaN"
    `std::less<double>` 在不含 NaN 的数据上是严格弱序。数据里有 NaN 时，NaN 与每个数都等价，`equiv` 不再传递，`sort` 的前提被破坏。需要时可以用 `std::strong_order`（[[cmp.alg]]）作比较器，它给出包括 NaN 在内的全序。

## 思考题

!!! question "思考题"
    1. 函数对象的 `operator()` 修改一个 `mutable` 的调用计数器，但返回值只依赖实参。它建模 `regular_invocable` 吗？
    2. 若 `comp` 是严格弱序，`[](auto a, auto b) { return !comp(b, a); }` 满足 `strict_weak_order` 吗？建模吗？
    3. 为什么 ¶2 不要求非对称性（`comp(a, b)` 蕴含 `!comp(b, a)`）？

<details markdown="1">
<summary>答案</summary>

1. 取决于计数器能否被观察到。[[concepts.equality]] 所说的修改，是以能被保持相等性的表达式观察到的方式改变值。如果计数器能通过某个保持相等性的公开接口读出，就违反了 ¶1；如果对外完全不可见（纯粹的调试统计），一般不算修改。多线程下非原子的计数器还会带来数据竞争，那是另一个问题。
2. 满足，因为语法上它只需是 `relation`。不建模：对任何 `x`，`!comp(x, x)` 为真，所以它对 `(x, x)` 返回 `true`，违反反自反性。
3. 非对称性可以推出来：如果 `comp(a, b)` 和 `comp(b, a)` 同时为真，由传递性得到 `comp(a, a)`，与反自反矛盾。
</details>
