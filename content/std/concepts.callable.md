---
title: 可调用概念
summary: invocable 与 regular_invocable（语法相同、语义不同：是否要求保持相等性）、predicate（结果 boolean-testable）、relation（四个方向都是谓词）、equivalence_relation 与 strict_weak_order（纯语义细化）；严格弱序的精确定义，以及"纯语义细化不参与包含"的后果。
status: done
covers: *
since: c++20
related: concepts, concepts.compare, concepts.equality, func.def, func.invoke, temp.constr.normal, temp.constr.order, alg.sorting
tags: 标准库, 概念, invocable, predicate, 严格弱序
updated: 2026-10-18
---

[concepts.callable] 描述对**可调用类型**（[[func.def]]）及其实参的要求（[concepts.callable.general] ¶1）。这一节的六个概念只有前三个有不同的语法；后三个——`regular_invocable` 相对 `invocable`、`equivalence_relation` 与 `strict_weak_order` 相对 `relation`——是**纯语义细化**：语法定义一字不差，区别全在语义要求里。理解这一点，是理解本节的关键。

阅读前提：[[concepts]]（保持相等性、满足 vs 建模），[[concept.booleantestable]]。

## `invocable`（[concept.invocable]）

```cpp
template<class F, class... Args>
  concept invocable = requires(F&& f, Args&&... args) {
    invoke(std::forward<F>(f), std::forward<Args>(args)...); // not required to be equality-preserving
  };
```

¶1：`invocable` 规定可调用类型 `F` 与一组实参类型 `Args...` 之间的关系：能被库函数 `std::invoke`（[[func.invoke]]）求值。

用 `invoke` 而不是 `f(args...)`，意味着它涵盖了 *INVOKE* 的全部形式：普通函数、函数对象、**成员函数指针**（第一个实参是对象、引用、指针或 `reference_wrapper`）、**数据成员指针**。

注意那条注释：**调用表达式不要求保持相等性**（[[concepts.equality]] ¶4 的豁免）。¶2 例 1：生成随机数的函数可以建模 `invocable`。`invocable` 只说"能调用"，对调用的结果一无所求。

`F` 与 `Args` 的值类别通过 `F&&`、`Args&&...` 与 `std::forward` 精确传递：`invocable<F&, int>` 检查对左值 `F` 的调用，`invocable<F, int>` 检查对右值 `F` 的调用——对于 `operator()` 带 `&&` 限定的函数对象，二者结果不同。

```cpp run title="invocable.cpp" ok
#include <concepts>
#include <random>
#include <string>

struct S { int m; int f(int) const { return m; } };

static_assert(std::invocable<int S::*, S&>);                          // 数据成员指针
static_assert(std::invocable<int (S::*)(int) const, const S*, int>);  // 成员函数指针 + 指针
static_assert(!std::invocable<int (S::*)(int) const, S, std::string>);
static_assert(std::invocable<std::mt19937&>);                         // 有状态：照样 invocable

int main() {}
```

## `regular_invocable`（[concept.regularinvocable]）

```cpp
template<class F, class... Args>
  concept regular_invocable = invocable<F, Args...>;
```

¶1：`invoke` 调用表达式**应当保持相等性**，且**不得修改**函数对象或实参。注 1：这一要求取代了 `invocable` 定义中"不要求保持相等性"的注释。

¶2 例 1：随机数生成器不建模 `regular_invocable`。¶3 注 2：`invocable` 与 `regular_invocable` 的区别**纯粹是语义上的**。

"保持相等性 + 不修改"合起来就是数学意义上的**纯函数**：相等的输入（包括函数对象本身的状态）总是得到相等的输出，且没有可观察的副作用。这是算法能多次调用、缓存结果、重排调用顺序的前提。

### 纯语义细化不参与包含

`regular_invocable<F, Args...>` 规范化（[[temp.constr.normal]]）时，概念 id 会被替换为其定义 `invocable<F, Args...>` 的范式——二者的范式**完全相同**。按 [[temp.constr.order]]，它们**互相包含**，谁也不比谁"更受约束"：

```cpp run title="semantic-refinement.cpp" error
#include <concepts>

template<class F> requires std::invocable<F>         int pick(F) { return 1; }
template<class F> requires std::regular_invocable<F> int pick(F) { return 2; }

int main() {
    return pick([] {});   // error: call to 'pick' is ambiguous
}
```

所以不能"用 `regular_invocable` 重载出一个对纯函数更快的版本"。语义细化只是写给人看的契约：它告诉调用者"这里会假设你的函数是纯的"，违反它是 {{ifndr}}。

## `predicate`（[concept.predicate]）

```cpp
template<class F, class... Args>
  concept predicate =
    regular_invocable<F, Args...> && boolean-testable<invoke_result_t<F, Args...>>;
```

谓词 = 纯函数 + 结果 *`boolean-testable`*（[[concept.booleantestable]]）。这一次有新的语法要求，所以 `predicate` 真正地包含 `regular_invocable`（也就包含 `invocable`）。

返回 `int`、指针、`bitset::reference` 的函数都可以是谓词；返回 `void` 的不行；返回一个重载了 `&&` 的类型的，满足但不建模。

## `relation`（[concept.relation]）

```cpp
template<class R, class T, class U>
  concept relation =
    predicate<R, T, T> && predicate<R, U, U> &&
    predicate<R, T, U> && predicate<R, U, T>;
```

二元关系必须在 `T×T`、`U×U`、`T×U`、`U×T` 四个方向上都是谓词。为什么要求同类型的两个方向？因为算法在处理异质查找时，往往既要拿元素与键比较，也要拿元素与元素比较（例如 `ranges::sort` 后再 `ranges::lower_bound`）；更根本地，后面的等价关系与严格弱序的公理（自反、传递）需要在同一个类型上表述。

```cpp run title="relation.cpp" ok
#include <concepts>
#include <functional>
#include <string>

struct LessIntStr {   // 只提供跨类型的两个方向
  bool operator()(int, const std::string&) const;
  bool operator()(const std::string&, int) const;
};
static_assert(!std::relation<LessIntStr, int, std::string>);   // 缺 (int,int)、(string,string)
static_assert(std::equivalence_relation<std::equal_to<>, int, long>);
static_assert(std::strict_weak_order<std::less<>, int, long>);

int main() {}
```

## `equivalence_relation`（[concept.equiv]）

```cpp
template<class R, class T, class U>
  concept equivalence_relation = relation<R, T, U>;
```

¶1：关系建模 `equivalence_relation` 仅当它在实参上施加一个**等价关系**——自反、对称、传递。`ranges::unique`、`ranges::adjacent_find` 的比较器、`unordered_*` 的键相等谓词就是这种关系。

与 `equality_comparable` 的区别：等价关系不要求"等价即相等"。按忽略大小写比较字符串是合法的等价关系，尽管 `"A"` 和 `"a"` 不相等。

## `strict_weak_order`（[concept.strictweakorder]）

```cpp
template<class R, class T, class U>
  concept strict_weak_order = relation<R, T, U>;
```

¶1：关系建模 `strict_weak_order` 仅当它在实参上施加一个**严格弱序**（[[g:strict-weak-ordering]]）。¶2 解释了这两个词：

- **严格**（*strict*）：反自反，对所有 `x`，`!comp(x, x)`；
- **弱**（*weak*）：比全序弱、比偏序强。

令 `equiv(a, b)` 为 `!comp(a, b) && !comp(b, a)`（"谁也不比谁小"），要求是 `comp` 与 `equiv` **都传递**：

- ¶2.1：`comp(a, b) && comp(b, c)` 蕴含 `comp(a, c)`；
- ¶2.2：`equiv(a, b) && equiv(b, c)` 蕴含 `equiv(a, c)`。

¶3 注 1 给出了这些条件的推论：`equiv` 是等价关系（¶3.1）；`comp` 在 `equiv` 的等价类之间诱导出良定义的关系（¶3.2）；这个诱导关系是严格全序（¶3.3）。

直观图景：严格弱序把所有元素分成若干"并列组"（等价类），组与组之间排成一条直线，组内元素彼此"不可区分"。按姓氏排序的人员列表就是这样——同姓的人并列。

### 与 `totally_ordered` 的区别

| | `strict_weak_order` | `totally_ordered` |
|---|---|---|
| 约束对象 | 比较器（关系 `R`） | 类型 `T` 的 `<` 等运算符 |
| "不可区分" | 等价，不一定相等 | 必然相等（三歧性 + `==` 即相等） |
| 用途 | `sort`、`lower_bound`、`set` 的比较器 | 默认比较器 `ranges::less` 要求的类型性质 |

`ranges::less` 要求 `totally_ordered_with`，而 `ranges::sort` 只要求比较器是 `strict_weak_order`（经由 `sortable` → `indirect_strict_weak_order`）。所以给 `ranges::sort` 自定义比较器可以只是严格弱序，用默认比较器时元素类型却必须全序。

### 经典错误：`<=` 不是严格弱序

```cpp run title="le-comparator.cpp" ifndr
#include <algorithm>
#include <concepts>
#include <vector>

int main() {
    auto le = [](int a, int b) { return a <= b; };
    static_assert(std::strict_weak_order<decltype(le), int, int>);   // 满足：语法上只是 relation
    std::vector<int> v(100, 42);
    std::ranges::sort(v, le);   // 不建模：le(x, x) 为 true，违反反自反性
}
```

`<=` 违反"严格"（`le(x, x)` 为真）。后果不只是"排序结果可能不对"：许多 `sort` 实现的内层循环依赖"比较器在遇到与枢轴相等的元素时返回 `false`"作为哨兵，用 `<=` 可能越过数组边界读写——这是真实存在的崩溃来源。按标准，这个程序 {{ifndr}}。

!!! impl "libc++ 上的实际表现"
    本机 Clang 23 + libc++ 默认构建下，上面的程序在 `sort` 内部越界访问后以总线错误崩溃（退出码 138）。libc++ 的 `<__algorithm/sort.h>` 在内层循环中埋了越界检查（"Would read out of bounds, does your comparator satisfy the strict-weak ordering requirement?"），在 `fast`/`extensive` 强化模式下（`-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_FAST` 等）它以陷阱指令终止程序；在 `debug` 模式下会打印上述消息，并且 `<__debug_utils/strict_weak_ordering_check.h>` 还会在排序完成后抽查前 100 个元素，验证比较器确实是严格弱序。

## 陷阱

!!! pitfall "以为 `regular_invocable` 能在编译期挡住有状态的函数对象"
    它不能：`std::regular_invocable<std::mt19937&>` 为 `true`。编译器无法判断一个函数是否纯，也就无法区分 `invocable` 与 `regular_invocable`。

!!! pitfall "浮点比较器与 NaN"
    `std::less<double>` 在不含 NaN 的数据上是严格弱序；一旦含 NaN，`equiv` 不再传递（NaN 与一切"等价"），`sort` 的前提被破坏。需要时用 `std::strong_order`（C++20，[[cmp.alg]]）作为比较器，它给出包括 NaN 在内的全序。

## 思考题

!!! question "思考题"
    1. 函数对象 `F` 的 `operator()` 修改了一个 `mutable` 的调用计数器，但返回值只依赖于实参。它建模 `regular_invocable` 吗？
    2. 若 `comp` 是严格弱序，`[](auto a, auto b) { return !comp(b, a); }` 是什么关系？它满足 `strict_weak_order` 吗？建模吗？
    3. 为什么 `strict_weak_order` 只要求 `comp` 与 `equiv` 传递，而不要求非对称性（`comp(a, b)` 蕴含 `!comp(b, a)`）？

<details markdown="1">
<summary>展开查看答案与解析</summary>

1. 取决于计数器是否能被"保持相等性的表达式"观察到。¶1 要求调用"不得修改函数对象"——修改的定义（[[concepts.equality]] ¶5）是"以能被保持相等性的表达式观察到的方式改变值"。如果计数器能通过某个保持相等性的公开接口读出，就违反了；如果它对外完全不可观察（纯粹的调试统计），则一般认为不构成"修改"。但在多线程环境中，非原子的计数器本身就会引入数据竞争——这是另一个问题。
2. 它是 `comp` 的"小于等于"版本。语法上满足 `strict_weak_order`（只要 `comp` 满足 `relation`）；但不建模：对任何 `x`，`!comp(x, x)` 为真，于是它对 `(x, x)` 返回 `true`，违反反自反性。
3. 非对称性可以推出来：若 `comp(a, b)` 与 `comp(b, a)` 同时为真，由传递性得 `comp(a, a)`，与反自反矛盾。¶2 把"严格"（反自反）和两条传递性作为公理，其余性质（非对称、`equiv` 是等价关系、诱导严格全序）都是推论，注 1 列出了其中几条。
</details>

## 小结

!!! summary
    | 概念 | 语法 | 语义 |
    |---|---|---|
    | `invocable<F, Args...>` | `invoke(f, args...)` 有效 | 无（调用不要求保持相等性） |
    | `regular_invocable` | 同 `invocable` | 调用保持相等性，不修改函数对象与实参 |
    | `predicate` | + 结果 *`boolean-testable`* | 同上 |
    | `relation<R, T, U>` | 四个方向都是 `predicate` | 同上 |
    | `equivalence_relation` | 同 `relation` | 自反、对称、传递 |
    | `strict_weak_order` | 同 `relation` | 反自反；`comp` 与 `equiv` 传递 |

    纯语义细化（`regular_invocable`、`equivalence_relation`、`strict_weak_order`）规范化后与被细化概念相同，互相包含，不能用来区分重载。
