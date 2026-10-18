---
title: 算法要求
summary: 整个算法库的“总则”——模板形参名即类型要求（InputIterator/ForwardIterator… 与 C++20 迭代器概念的混合规则）、Predicate/BinaryPredicate 不得经实参修改对象且须对 const 实参给出相同结果、函数对象可被随意复制、a + n 与 b - a 的记法约定、range 重载如何分派到 ranges 版本、显式模板实参的行为未指明，以及 ranges 算法作为“算法函数对象”不被 ADL 找到、不能显式给模板实参
status: done
papers: P0896R4, P2408R5, P3136R1
related: algorithms, alg.req, iterator.requirements, iterator.concepts, customization.point.object, res.on.functions, function.objects, concept.booleantestable, basic.lookup.argdep
tags: 标准库, 算法, 谓词, niebloid, ADL, 迭代器要求
updated: 2026-10-18
---

[algorithms.requirements] 是整个第 26 章的**总则**。后面一百多个算法的条文都写得极其简短——`template<class ForwardIterator, class Predicate> ForwardIterator find_if(...)`，*Returns*: …，*Complexity*: …——之所以能这么短，是因为“`ForwardIterator` 必须满足什么”“`Predicate` 可以做什么不可以做什么”“`a + n` 对前向迭代器是什么意思”全都在这里一次性规定了。不读这一节，就无法精确判断一个算法调用是否合法。

前置知识：迭代器的 *Cpp17* 要求（[[iterator.requirements]]）与迭代器概念（[[iterator.concepts]]）的区别；库对用户类型的一般要求（[[res.on.functions]]：模板实参不满足要求 → {{ub}}）。

## 算法与数据结构解耦（¶1）与 niebloid 的身份（¶2）

¶1 是 STL 的设计宣言：算法按迭代器类型参数化，因此只要程序自定义的数据结构提供满足假设的迭代器，就能直接使用这些算法。

¶2 规定：本章在 `std::ranges` 中、以函数模板形式描述的实体，都是**算法函数对象**（[[g:algorithm-function-object]]，[[alg.func.obj]]）。也就是说，条文里写的

```cpp
template<input_iterator I, sentinel_for<I> S, class Proj = identity, ...>
  constexpr I ranges::find(I first, S last, const T& value, Proj proj = {});
```

只是**说明手法**：实际上 `std::ranges::find` 是一个对象，其 `operator()` 的重载集合与上述模板一致。[alg.func.obj] ¶1 现在的措辞是：

!!! std
    An *algorithm function object* is a customization point object ([customization.point.object]) that is specified as one or more overloaded function templates.

即它是一种**定制点对象**（[[g:customization-point-object]]）。¶2 及注 1 给出了两条可观察后果：

1. `o(args...)` 与“名字查找结果为该重载集合的 `s(args...)`”表达式等价（[[g:expression-equivalent]]）；
2. 它们**不会被 ADL 找到**；而且当非限定名字查找找到它们时，会**抑制** ADL（因为查找结果是对象而非函数，见 [[basic.lookup.argdep]]）。

这类对象在社区里俗称 **niebloid**（以 Eric Niebler 命名）。C++20 时标准只是规定它们“不被 ADL 找到、找到时抑制 ADL”，实现普遍用对象来满足这一点；[[P3136R1]] 把它们正式改成定制点对象，从而它们也获得了 CPO 的全部性质：可复制、`constexpr` 构造、所有实例等价。

```cpp run title="niebloid.cpp" ok
#include <algorithm>
#include <cassert>
#include <vector>

namespace lib {
    struct Widget { int id; };
    bool operator==(Widget a, Widget b) { return a.id == b.id; }
    // 一个同名的“算法”，指望通过 ADL 被找到
    template<class It, class T> It find(It f, It, const T&) { return f; }
}

int main() {
    std::vector<lib::Widget> v{{1}, {2}, {3}};
    using namespace std::ranges;
    auto it = find(v.begin(), v.end(), lib::Widget{3});  // 普通查找找到 ranges::find 对象 → 抑制 ADL
    assert(it == v.end() - 1);                           // 没有调用 lib::find

    auto sorter = std::ranges::sort;       // 算法函数对象可以复制、传递
    std::vector<int> w{3, 1, 2};
    sorter(w);
    assert(w == (std::vector<int>{1, 2, 3}));
}
```

对比：经典 `std::sort` 是函数模板，**可以**被 ADL 找到——`sort(v.begin(), v.end())` 不写 `std::` 也能编译（`vector` 的迭代器关联命名空间 `std`）；而 `sort(v)`（期待 `ranges::sort`）就找不到：

```cpp run title="adl.cpp" error
#include <algorithm>
#include <vector>
int main() {
    std::vector<int> v{3, 1, 2};
    sort(v.begin(), v.end());   // OK：ADL 找到 std::sort
    sort(v);                    // error: ranges::sort 不会被 ADL 找到
}
```

!!! pitfall "不能对 `ranges::` 算法显式指定模板实参"
    `std::ranges::sort` 是对象，`std::ranges::sort<std::vector<int>&>(v)` 是非良构的（Clang 报 “'sort' does not name a template but is followed by template arguments”）。对经典 `std::` 算法，见下文 ¶15：显式模板实参的行为是**未指明**的。

## 数据竞争：算法不得偷偷写（¶3）

!!! std
    For purposes of determining the existence of data races, algorithms shall not modify objects referenced through an iterator argument unless the specification requires such modification.

这是给多线程程序的保证：两个线程同时对同一个 `vector` 调用 `std::find`/`std::count` 不构成数据竞争（[[intro.races]]），因为实现不允许为了“优化”而临时改写元素（比如在末尾放一个哨兵值再恢复）。

## 模板形参名即类型要求（¶4）

经典算法的模板形参不带约束，标准用**形参名**表达要求：

| 形参名 | 要求 |
|---|---|
| `InputIterator`、`InputIterator1/2` | 满足 *Cpp17InputIterator*（¶4.2） |
| `OutputIterator`、`OutputIterator1/2` | 满足 *Cpp17OutputIterator*（¶4.3） |
| `ForwardIterator`、`…1/2`、`NoThrowForwardIterator` | 若须为可变迭代器：*Cpp17ForwardIterator*；否则：**model `forward_iterator`**（¶4.4） |
| `NoThrowForwardIterator` | 另外：自增、赋值、比较、解引用有效迭代器时不抛异常（¶4.5） |
| `BidirectionalIterator…` | 同上模式：可变 → *Cpp17BidirectionalIterator*，否则 model `bidirectional_iterator`（¶4.6） |
| `RandomAccessIterator…` | 同上模式（¶4.7） |

另外 ¶4.1：若 *Effects* 规定要修改迭代器所指的值，则该实参须满足**可变迭代器**要求。

¶4.4/4.6/4.7 中“**否则 model 概念**”这半句来自 C++23 的 [[P2408R5]]，意义重大。C++20 的许多视图（如 `views::iota(0, n)`、`views::transform`）的迭代器是 C++20 意义下的 `random_access_iterator`，但其 `reference` 是纯右值，因此**不满足** *Cpp17ForwardIterator*（后者要求 `reference` 是真引用）。在 P2408 之前，`std::find(v.begin(), v.end(), x)` 用在这种迭代器上严格说是 UB；现在对**不需要写入**的算法，只要迭代器 model 对应的 C++20 概念即可。需要写入（可变迭代器）时仍保留 *Cpp17* 要求，因为可变性无法用概念完整表达。

注 1：这些按名字的规则**不影响**带约束的迭代器形参——`ranges::` 算法的要求由概念直接写出。

!!! note "*Cpp17InputIterator* 仍然按老规矩"
    `InputIterator` 没有“否则 model `input_iterator`”这一分支：C++20 的 `input_iterator` 可以是只能移动的类型，而经典算法按值复制迭代器。

## 命名约定 `_copy` 与 `_if`（¶5）

有些算法同时提供原地版与复制版，复制版叫 `algorithm_copy`；接受谓词的版本加后缀 `_if`，且 `_if` 在 `_copy` 之后（`remove_copy_if`、`replace_copy_if`）。脚注 179 解释了为什么没有 `sort_copy`：当操作本身的代价远大于复制时，不提供复制版——用户自己先 `copy` 再 `sort` 即可。

## `Predicate` 与 `BinaryPredicate` 的精确契约（¶6–¶7）

对未加约束的 `Predicate pred` 和值类型为 `T` 的迭代器 `first`，¶6 要求：

1. `pred(*first)` 良构，且 `decltype(pred(*first))` model *boolean-testable*（[[g:boolean-testable]]，[[concept.booleantestable]]）——返回类型不必是 `bool`，但要能“像 `bool` 一样”参与 `!`、`&&`、`||`；
2. `pred` **不得通过实参调用任何非 const 函数**；
3. 对指代 `*first` 同一对象的、类型为（可能 const 的）`T` 的泛左值 `u`，`pred(u)` 必须是有效表达式且结果等于 `pred(*first)`。

第 3 条是 C++20 期间补上的，它的分量常被低估：实现有权以 **const 左值**的形式把元素交给谓词，也有权把元素先存进 `T` 类型的局部变量再调用谓词。因此，形参为 `int&` 的谓词虽然能和 libc++ 的 `std::find_if` 一起编译通过，却不满足要求：

```cpp
std::vector<int> v{1, 2, 3};
auto it = std::find_if(v.begin(), v.end(),
                       [](int& x) { return x == 2; });   // 违反 ¶6：pred(u) 对 const int 的 u 无效
```

能编译只是因为 libc++ 恰好传了非 const 左值；按 [[res.on.functions]]，模板实参不满足要求时行为未定义。`ranges::find_if` 会把这一要求变成约束（`indirect_unary_predicate` 要求对 *indirect-value-t*`<I>`（通常即 `iter_value_t<I>&`）和 `iter_reference_t<I>` 都满足 `predicate`，而 `predicate` 蕴含 `regular_invocable` 的语义要求“相等性保持”，见 [[indirectcallable]]）——比如把上面的 lambda 用于 `const vector` 时，会在约束检查阶段直接报错。

¶7 对 `BinaryPredicate` 做了对称的规定：`binary_pred(*first1, *first2)` 良构且 *boolean-testable*；**除非另有规定，第一个实参总是第一个序列的元素**，当签名中出现 `T value` 时是 `binary_pred(*first1, value)`；同样不得经实参调用非 const 函数，对 const 版本的 `u`、`v` 给出相同结果。

“第一个实参是哪个”这条规定对**异构比较**很关键：`std::find_end`、`std::search` 等传给谓词的顺序是确定的，你可以写一个只接受 `(Elem, Key)` 顺序的谓词。而 `std::upper_bound` 是“另有规定”的例子——它调用的是 `comp(value, *i)`，见 [[alg.binary.search]]。

¶8：`UnaryOperation`、`BinaryOperation`、`BinaryOperation1/2` 只是“期待一个函数对象”（[[function.objects]]），没有 ¶6/¶7 那样的不可修改要求——但具体算法通常在自己的 *Preconditions* 里另行限制，例如 `transform` 要求 `op` 不修改区间内元素、不使迭代器失效（[[alg.transform#2]]）。

## 函数对象可以被随意复制（¶9，注 2）

!!! std
    Unless otherwise specified, algorithms that take function objects as arguments can copy those function objects freely.

这是一条注（非规范性），但它概括的是规范性事实：算法按值接收函数对象，规范没有限制内部复制次数，所以**依赖函数对象身份或内部累积状态**的写法是不可移植的。需要身份时，传 `std::ref(f)`（[[refwrap]]）：

```cpp run title="ref.cpp" ok
#include <algorithm>
#include <cassert>
#include <functional>
#include <vector>

struct Counter {
    int calls = 0;
    bool operator()(int x) { ++calls; return x % 2 == 0; }
};

int main() {
    std::vector<int> v{5, 3, 8, 1, 9, 2, 7, 4, 6, 0};
    Counter c;
    (void)std::count_if(v.begin(), v.end(), c);            // 传值：c 本身不变
    assert(c.calls == 0);
    (void)std::count_if(v.begin(), v.end(), std::ref(c));  // reference_wrapper 保住身份
    assert(c.calls == 10);                                  // count_if 恰好调用 N 次
}
```

`for_each` 是“另有规定”的典型：非并行的 `std::for_each` 返回 `f`（移动后的最终状态），`ranges::for_each` 在结果 `{last, f}` 中带回它（[[alg.foreach]]）。

另注意 `Predicate` 的 `operator()` 写成非 const 的这一点本身没问题——¶6 禁止的是通过**实参**修改对象，不是修改谓词自身的状态。但要注意 `ranges::` 版本要求 `regular_invocable`/`predicate` 的语义（相等性保持），带状态的谓词在那里属于“满足语法要求但不 model 概念”，同样是 {{ub}}。

## `*first == value` 必须真能当 `bool` 用（¶10）

当算法描述写出 `*first == value` 这样的条件时，该表达式在布尔语境下必须求值为 `true` 或 `false`。这是给“返回奇怪类型的 `operator==`”划的底线。

## `a + n` 与 `b - a` 的记法（¶11–¶13）

条文为了简洁，常对**不支持**这些运算的迭代器写 `first + n`、`last - first`。¶11 规定其语义：

- `a + n`：等价于复制 `a` 后自增（或自减）`|n|` 次；
- `b - a`（`[a, b)` 是区间）：等价于从 `a` 数到 `b` 的步数；`[b, a)` 时为负；
- 对由 range `r` 得到的迭代器 `i` 和哨位 `s`，`s - i` 的类型、值、值类别等同于 `ranges::distance(i, s)`；注 3 允许实现在结果相同时改用 `ranges::distance(r)`（对 sized range 是 O(1)）。

所以 *Complexity* 里写的 “`last - first` 次比较”对前向迭代器也有意义，**但不意味着**算法会去做这个减法——计算 `last - first` 本身对前向迭代器是线性的，复杂度条款只计“谓词应用次数”这类指定的操作。

¶12：若 `n` 是 *integer-like* 而类型不是迭代器的差类型 `D`，则 `a + n` 意为 `a + D(n)`。¶13：返回值描述中需要迭代器的地方若写了哨位 `s`，语义是 `ranges::next(i, s)`——这就是为什么 `ranges::find(first, unreachable_sentinel_t{}, x)` 之类调用仍能返回迭代器，以及为什么 `ranges::sort(first, sentinel)` 返回的是迭代器 `last` 而非哨位。

## range 重载的分派（¶14）

!!! std
    Overloads of algorithms that take range arguments behave as if they are implemented by dispatching to the overload in namespace `ranges` that takes separate iterator and sentinel arguments

对每个 range 实参 `r`，迭代器实参用 `ranges::begin(r)` 初始化，哨位实参用 `ranges::end(r)` **或** `ranges::begin(r) + N`（`N = ranges::distance(r)`）。后一种选择是为 C++26 的并行 ranges 重载准备的：它们要求 `sized_sentinel_for`，对“sized 但 common 性不明”的范围，用 `begin + size` 构造一个同类型的终点即可。

另外，range 重载的返回类型里那些 `borrowed_iterator_t<R>`、`borrowed_subrange_t<R>` 是这一层“包装”唯一额外做的事：若 `R` 是非 borrowed 的右值，返回 `ranges::dangling`（[[range.dangling]]），把悬垂迭代器变成编译期错误，见 [[algorithms.results]]。

## 显式模板实参：未指明（¶15）

!!! std
    The well-formedness and behavior of a call to an algorithm with an explicitly-specified template argument list is unspecified, except where explicitly stated otherwise.

注 4 道出用意：实现可以用与标准列出的**不同的模板形参**声明算法——多加一个默认模板实参、调整顺序、合并重载都行。所以 `std::find<std::vector<int>::iterator, int>(...)` 可能编译、可能不编译、可能行为不同，{{unspec}}。

“另有明文规定”的例外是 `std::min`/`std::max`/`std::minmax`：[[alg.min.max]] 的 *Remarks* 明确允许为 `T` 显式指定实参，`std::max<long>(1, 2L)` 是常用写法。

## 思考题

<details markdown="1">
<summary>1. `std::count_if(v.begin(), v.end(), [n = 0](int) mutable { return ++n % 2 == 0; })` 在不同实现上一定返回相同结果吗？</summary>

非并行的 `count_if` 规定“恰好 `last - first` 次谓词应用”，且对输入迭代器只能顺序访问，因此每个元素调用一次、按顺序。但该 lambda 只有一个副本在调用吗？¶9 允许算法随意复制函数对象，若实现把谓词复制后对不同段分别调用，计数就会分叉。实际实现都只用一个副本，但标准不保证——更根本的是，这个谓词对同一元素两次调用结果不同，违反了 ¶6 的“`pred(u)` 等于 `pred(*first)`”要求，属于 {{ub}}。
</details>

<details markdown="1">
<summary>2. 为什么 ¶4.4 对“须为可变迭代器”的情形保留 *Cpp17ForwardIterator* 要求，而不也改成概念？</summary>

C++20 的 `forward_iterator` 概念不要求 `iter_reference_t` 是引用类型，因此 model 它的迭代器可能返回代理或纯右值；对这类迭代器，`*it = x` 是否真的写到了序列元素里无法由概念保证（`indirectly_writable` 只描述“能写”，不保证经典算法内部诸如 `std::swap(*a, *b)` 的用法成立）。经典算法的实现大量依赖“`*it` 是真引用”这一 *Cpp17* 保证，所以 [[P2408R5]] 只放宽了只读情形。
</details>

<details markdown="1">
<summary>3. 在全局作用域写 `using std::ranges::sort;` 之后，`sort(v.begin(), v.end())` 调用的是谁？</summary>

using 声明把对象 `std::ranges::sort` 引入；非限定名字查找找到的是一个**对象**，按 [[basic.lookup.argdep]] 此时不进行 ADL，因此 `std::sort` 不会作为候选出现，调用的是 `ranges::sort` 的迭代器+哨位重载。若改写 `using std::sort;` 则恰好相反。
</details>

## 小结

| 规则 | 段落 | 违反的后果 |
|---|---|---|
| ranges 算法是算法函数对象（CPO），不被 ADL 找到、找到时抑制 ADL | ¶2，[alg.func.obj] | — |
| 算法不得写入规范未要求写入的对象 | ¶3 | （实现义务） |
| 形参名决定迭代器要求；只读时 model C++20 概念即可 | ¶4 | {{ub}} |
| 谓词：*boolean-testable*、不经实参修改、对 const 实参结果相同 | ¶6–¶7 | {{ub}} |
| 函数对象可被随意复制；要身份用 `std::ref` | ¶9 | — |
| `a + n`、`b - a` 是记法，不代表实际运算 | ¶11–¶13 | — |
| range 重载 = 分派到迭代器+哨位重载 | ¶14 | — |
| 对经典算法显式给模板实参 | ¶15 | {{unspec}}（`min`/`max` 例外） |
