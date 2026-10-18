---
title: C++17 迭代器要求
summary: Cpp17Iterator / Cpp17InputIterator / Cpp17OutputIterator / Cpp17ForwardIterator / Cpp17BidirectionalIterator / Cpp17RandomAccessIterator 六张要求表——它们是老接口（std:: 算法、容器的迭代器对构造函数、iterator_operations）仍在使用的命名要求；与 C++20 概念的关键差异：要求可复制与 ==、要求 reference 是真引用、要求 iterator_traits 申报类别、差值类型必须是内建有符号整数。
status: done
covers: *
since: c++98
related: iterator.concepts, iterator.assoc.types, iterator.requirements, algorithms.requirements, utility.arg.requirements, iterator.primitives, std.iterator.tags
tags: 标准库, 迭代器, 命名要求, 兼容性
updated: 2026-10-18
---

[iterator.cpp17] 收录的是 C++98 以来的迭代器**命名要求**（*named requirements*）。C++20 把它们改名加上 "Cpp17" 前缀、挪进这个子条款，但没有删除——因为大量既有接口仍以它们为准：

- 非 `ranges::` 算法的模板参数名（`InputIterator`、`ForwardIterator`……）表达的要求（[[algorithms.requirements#4]]）；
- 容器的"迭代器对"构造函数与 `insert`、`assign`（[[container.requirements]]）；
- `std::advance`、`std::distance`、`std::next`、`std::prev`（[[iterator.operations]]）；
- `reverse_iterator`、`move_iterator` 的要求（它们接受"满足 *Cpp17* 要求**或**建模概念"之一）。

与概念不同，命名要求是**纯文本**：编译器不检查，类型通过 `iterator_traits<X>::iterator_category` 自我申报（[[std.iterator.tags]]），申报错误即落入 [[res.on.functions#2.3]] 的未定义行为。

## 记号（[iterator.cpp17.general]）

¶1 规定后续表格中的记号：`a`、`b` 是 `X` 或 `const X` 的值；`difference_type`、`reference` 指 `iterator_traits<X>` 中的对应类型；`n` 是 `difference_type` 的值；`u`、`tmp`、`m` 是标识符；`r` 是 `X&` 的值；`t` 是值类型 `T` 的值；`o` 是某个可写入输出迭代器的类型的值。注 1：对迭代器类型 `X`，必须存在 `iterator_traits<X>` 的实例化——也就是说这一套要求离不开 `iterator_traits`。

## *Cpp17Iterator*（[iterator.iterators]）

¶1：所有迭代器的基础。¶2：`X` 满足 *Cpp17Iterator* 当且仅当

1. 满足 *Cpp17CopyConstructible*、*Cpp17CopyAssignable*、*Cpp17Swappable*、*Cpp17Destructible*（[[utility.arg.requirements]]、[[swappable.requirements]]）——**必须可复制**；
2. `iterator_traits<X>::difference_type` 是**有符号整数类型或 `void`**（`void` 留给输出迭代器）；
3. 表 78 中的表达式有效：`*r`（返回类型未指明；前条件：`r` 可解引用）与 `++r`（返回 `X&`）。

## *Cpp17InputIterator*（[input.iterators]）

¶1：`X` 满足 *Cpp17Iterator* 与 *Cpp17EqualityComparable*，且表 79 的表达式有效。要点：

| 表达式 | 要求 |
|---|---|
| `a != b` | 等价于 `!(a == b)`；前条件：`(a, b)` 在 `==` 的定义域内 |
| `*a` | 返回 `reference`，可转换为 `T`；`(void)*a, *a` 等价于 `*a`；若 `a == b` 且在定义域内，则 `*a` 等价于 `*b` |
| `a->m` | 等价于 `(*a).m` |
| `++r` | 后条件：`r` 可解引用或为过尾值；**先前值的所有副本不再要求可解引用，也不再要求在 `==` 的定义域内** |
| `(void)r++` | 等价于 `(void)++r` |
| `*r++` | 可转换为 `T`，等价于 `{ T tmp = *r; ++r; return tmp; }` |

¶2 定义"**`==` 的定义域**"（*the domain of ==*）：取普通数学意义，即 `==`（被要求）有定义的值的集合，**这个集合可随时间变化**。每个算法根据自己对 `==`/`!=` 的使用对定义域提出额外要求。例 1：`find(a, b, x)` 只在 `a` 具有性质 *p* 时有定义——`b` 具有 *p*；`i` 具有 *p* 当且仅当 `*i == x`，或 `*i != x` 且 `++i` 具有 *p*。这是一个递归定义的"可达"。

¶3 推荐实践：输入迭代器上的算法应单遍。注 1：`a == b` 不蕴含 `++a == ++b`；值类型 `T` 不要求可复制赋值。

## *Cpp17OutputIterator*（[output.iterators]）

¶1：满足 *Cpp17Iterator*，且表 80 有效：`*r = o`、`++r`（且 `addressof(r) == addressof(++r)`）、`r++`（可转换为 `const X&`）、`*r++ = o`。每一行都附带：操作之后 `r` 不再要求可解引用，后条件是 `r` 可递增。

¶2 推荐实践：单遍。注 1：`operator*` 唯一有效的用法是位于赋值左侧；通过同一个迭代器值只赋值一次；相等与不等不一定有定义。

## *Cpp17ForwardIterator*（[forward.iterators]）

¶1：`X` 满足 *Cpp17ForwardIterator* 当且仅当

1. 满足 *Cpp17InputIterator*；
2. 满足 *Cpp17DefaultConstructible*；
3. **若 `X` 是可变迭代器，`reference` 是 `T` 的引用；若是常量迭代器，`reference` 是 `const T` 的引用**；
4. 表 81 有效：`r++` 可转换为 `const X&`，`*r++` 返回 `reference`；
5. 提供多遍保证。

¶2：`==` 的定义域是同一底层序列上的迭代器；值初始化的迭代器可以比较，且与同类型的其他值初始化迭代器相等（注 1：如同指向同一空序列的末尾）。¶3 多遍保证：`a == b` 蕴含 `++a == ++b`；`X` 是指针类型，或 `(void)++X(a), *a` 等价于 `*a`。¶5：相等的两个迭代器要么都可解引用、要么都不可。¶6：两个可解引用的迭代器相等，当且仅当 `*a` 与 `*b` **绑定到同一对象**。

第 3 条与第 ¶6 条一起，是 C++17 体系与代理迭代器之间的鸿沟：`reference` 必须是真引用，相等必须意味着"绑定同一对象"。`vector<bool>::iterator` 的 `reference` 是代理类，按此规定连 *Cpp17ForwardIterator* 都不满足——然而标准库实现历来把它申报为 `random_access_iterator_tag`，这是公认的历史妥协。

!!! note "与概念的对比"
    `forward_iterator` 概念（[[iterator.concept.forward]]）没有"`reference` 必须是真引用"的要求，只要求 `indirectly_readable` 的公共引用关系；它也没有"相等意味着绑定同一对象"的说法，而是用"引用在范围有效期内保持有效"来排除存储型迭代器。所以 `iota_view` 的迭代器是 `random_access_iterator`，却只是 *Cpp17InputIterator*。

## *Cpp17BidirectionalIterator*（[bidirectional.iterators]）

¶1：在 *Cpp17ForwardIterator* 之上，表 82：

- `--r` 返回 `X&`；前条件：存在 `s` 使 `r == ++s`；后条件：`r` 可解引用，`--(++r) == r`，`--r == --s` 蕴含 `r == s`，`addressof(r) == addressof(--r)`；
- `r--` 可转换为 `const X&`；`*r--` 返回 `reference`。

## *Cpp17RandomAccessIterator*（[random.access.iterators]）

¶1：在 *Cpp17BidirectionalIterator* 之上，表 83 以"操作语义"给出参考实现：

| 表达式 | 返回 | 语义 |
|---|---|---|
| `r += n` | `X&` | 等价于 `n` 次 `++`（`n` 为负时 `-n` 次 `--`） |
| `a + n`、`n + a` | `X` | `{ X tmp = a; return tmp += n; }`；`a + n == n + a` |
| `r -= n` | `X&` | `return r += -n;`；前条件：`n` 的绝对值可用 `difference_type` 表示 |
| `a - n` | `X` | `{ X tmp = a; return tmp -= n; }` |
| `b - a` | `difference_type` | 前条件：存在 `n` 使 `a + n == b`；`b == a + (b - a)` |
| `a[n]` | 可转换为 `reference` | `*(a + n)` |
| `a < b` | 建模 *`boolean-testable`* | 等价于 `b - a > 0`；`<` 是全序 |
| `a > b`、`a >= b`、`a <= b` | 同上 | 由 `<` 导出 |

表中的"参考实现"只描述**语义**（结果应当如同这样计算），[[iterator.requirements.general#14]] 仍要求这些操作是常数时间的。

## 两套体系的差异一览

| 方面 | *Cpp17* 命名要求 | C++20 概念 |
|---|---|---|
| 检查方式 | 文本，不检查 | 语法部分编译器检查 |
| 类别来源 | `iterator_traits<X>::iterator_category` | *`ITER_CONCEPT`*（优先 `iterator_concept`） |
| 可复制 | 所有迭代器都要 | 从 `forward_iterator` 起才要 |
| `==` | 从 input 起就要 | 从 `forward_iterator` 起才要；之前与哨位比较 |
| `reference` | forward 起必须是真引用 | 不要求（`contiguous` 除外） |
| 差值类型 | 内建有符号整数（或 `void`） | 有符号类整数，可为整数类类型 |
| 后置 `++` | 必须返回可用的值 | 输入迭代器可返回 `void` |
| `a[n]` | 可转换为 `reference` | 必须恰为 `iter_reference_t` |
| 连续 | 无此类别 | `contiguous_iterator` |
| 终点 | 必须与迭代器同类型 | 任意 `sentinel_for` |

## 实例：C++20 迭代器遇上 C++17 接口

```cpp run title="cpp17_vs_cpp20.cpp" ok
#include <cstdio>
#include <iterator>
#include <ranges>
#include <vector>

int main() {
    auto io = std::views::iota(0, 10);
    using It = decltype(io.begin());
    static_assert(std::random_access_iterator<It>);            // C++20：随机访问
    static_assert(std::same_as<std::iterator_traits<It>::iterator_category,
                               std::input_iterator_tag>);      // C++17：输入

    // std::distance 按 iterator_category 分派：走输入迭代器的逐个 ++ 路径（线性）
    std::printf("%td\n", std::distance(io.begin(), io.end()));
    // ranges::distance 按概念分派：sized_sentinel_for → 一次减法（常数）
    std::printf("%td\n", std::ranges::distance(io.begin(), io.end()));

    // 容器的迭代器对构造函数同样只看 iterator_category：
    // 输入迭代器无法预先求出距离，实现只能逐个 push_back
    std::vector<int> v(io.begin(), io.end());
    std::printf("%zu\n", v.size());
}
```

更进一步，`std::prev(io.end())` 要求 *Cpp17BidirectionalIterator*。libc++ 用 `static_assert` 检查 `iterator_category`，于是直接拒绝编译：

```cpp run title="prev_iota.cpp"
#include <iterator>
#include <ranges>

int main() {
    auto io = std::views::iota(0, 10);
    auto last = std::prev(io.end());   // UB：违反模板实参要求；libc++ 以 static_assert 报错
    return *last;
}
```

标准层面这是违反了模板实参的要求（[[res.on.functions#2.3]]，未定义行为），libc++ 选择把它变成编译错误。改用 `std::ranges::prev(io.end())` 即可。

## 常见误区

!!! pitfall "用 `iterator_category` 判断 C++20 迭代器的能力"
    自己写的分派代码若还在用 `iterator_traits<I>::iterator_category`，会把 `iota`、`transform` 等视图的迭代器一律当成输入迭代器。新代码应当用概念做分派（`if constexpr (std::random_access_iterator<I>)`），或直接调用 `ranges::` 版本的原语。

!!! pitfall "以为 C++23 已经全面放宽"
    [[algorithms.requirements#4]] 的放宽只针对**第 26 章算法**、只针对**非修改**用途（不要求可变迭代器时，`ForwardIterator` 等可以只建模概念）。`std::advance`/`distance`/`next`/`prev`、容器的迭代器对构造函数不在其列。

## 思考题

!!! question "思考题"
    1. 为什么 *Cpp17InputIterator* 的 `++r` 后条件说"先前值的所有副本不再要求在 `==` 的定义域内"，而不是"不再可解引用"？
    2. `std::istreambuf_iterator<char>` 的 `reference` 是 `char`（不是引用）。它满足哪一级 *Cpp17* 要求？建模哪一级概念？

<details markdown="1">
<summary>展开查看答案与解析</summary>

1. 两者都说了：副本"不再要求可解引用，也不再要求在 `==` 的定义域内"。后半句更强：连比较都不保证有意义。对 `istream_iterator`，推进一个副本会消费共享的流，其余副本仍持有旧值、可能与流的状态不一致，比较它们（`==` 只比较流指针，见 [[istream.iterator]]）的结果不反映"位置"——标准干脆不对其作任何保证。
2. 它只能是 *Cpp17InputIterator*（`reference` 不是引用，不满足前向）；在 C++20 中它建模 `input_iterator`，同样不是 `forward_iterator`——因为它是单遍的，`iterator_category` 申报 `input_iterator_tag` 也封顶了 *`ITER_CONCEPT`*。
</details>

## 小结

!!! summary
    - *Cpp17* 命名要求是 C++98 的文字规格，至今仍约束 `std::` 算法、容器构造函数和迭代器原语。
    - 关键门槛：所有迭代器可复制；输入起要求 `==`；前向起要求 `reference` 为真引用且相等即同一对象。
    - 类别靠 `iterator_category` 申报；C++20 迭代器在这套体系里常被"降级"为输入迭代器。
    - 处理 C++20 迭代器时优先用 `ranges::` 原语和算法。
