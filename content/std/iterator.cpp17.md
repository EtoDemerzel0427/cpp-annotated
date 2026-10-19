---
title: C++17 迭代器要求
summary: C++98 以来的六张迭代器要求表，C++20 起加上 Cpp17 前缀保留下来，仍然约束 std:: 算法、容器构造函数和 std::advance 等原语。
status: done
covers: *
since: c++98
papers: P2408R5
related: iterator.concepts, iterator.assoc.types, iterator.requirements, algorithms.requirements, utility.arg.requirements, iterator.primitives, std.iterator.tags
tags: 标准库, 迭代器, 命名要求, 兼容性
updated: 2026-10-19
---

!!! tldr
    - *Cpp17Iterator* 等六组要求是写成表格的文字规格，编译器不检查；类型靠 `iterator_traits<X>::iterator_category` 申报自己属于哪一级。
    - 它们仍然约束非 `ranges::` 的算法、容器的迭代器对构造函数，以及 `std::advance`、`std::distance`、`std::next`、`std::prev`。
    - 和 C++20 概念相比，这套要求更严：所有迭代器都要可复制，输入迭代器就要能比较相等，前向迭代器的 `reference` 必须是真引用。
    - 所以很多 C++20 视图的迭代器在这里只算输入迭代器。`std::prev(iota.end())` 在 libc++ 上直接编译失败，应当改用 `std::ranges::prev`。

C++98 用一组表格描述五类迭代器。C++20 引入迭代器概念（[[iterator.concepts]]）之后，旧的要求没有删除，只是改名加上 Cpp17 前缀，集中放到这一节。这种写在表格里、编译器不检查的要求叫**命名要求**（named requirements）。

旧要求仍在使用，因为很多接口一直以它们为准：

- 非 `ranges::` 算法用模板参数名表达要求，名为 `InputIterator` 的参数要满足 *Cpp17InputIterator*，等等（[[algorithms.requirements#4]]）；
- 容器的迭代器对构造函数以及 `insert`、`assign`（[[container.requirements]]）；
- `std::advance`、`std::distance`、`std::next`、`std::prev`（[[iterator.operations]]）；
- `reverse_iterator`、`move_iterator` 的模板参数，它们接受满足 *Cpp17* 要求或建模对应概念的类型。

类型通过 `iterator_traits<X>::iterator_category` 申报自己满足哪一级（[[std.iterator.tags]]）。申报了却不满足，就是用不符合要求的类型实例化标准库模板，行为未定义（[[res.on.functions#2.3]]）。

## C++20 迭代器遇上 C++17 接口

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

    // std::distance 按 iterator_category 分派，只能逐个 ++
    std::printf("%td\n", std::distance(io.begin(), io.end()));
    // ranges::distance 按概念分派，一次减法
    std::printf("%td\n", std::ranges::distance(io.begin(), io.end()));

    // 迭代器对构造函数同样只看 iterator_category，无法预先求出长度
    std::vector<int> v(io.begin(), io.end());
    std::printf("%zu\n", v.size());
}
```

`iota_view` 的迭代器解引用得到 `int` 纯右值，不是引用。按下文的前向迭代器要求，`reference` 必须是真引用，所以它在 C++17 体系里只能申报为输入迭代器，尽管在 C++20 中它是随机访问迭代器。

`std::prev` 要求 *Cpp17BidirectionalIterator*，于是下面的代码违反了模板实参的要求，行为未定义。libc++ 用 `static_assert` 检查 `iterator_category`，把它变成了编译错误：

```cpp run title="prev_iota.cpp"
#include <iterator>
#include <ranges>

int main() {
    auto io = std::views::iota(0, 10);
    auto last = std::prev(io.end());   // UB：不满足 Cpp17BidirectionalIterator
    return *last;                      // libc++ 在此前以 static_assert 报错
}
```

改用 `std::ranges::prev(io.end())` 就没有问题，它按概念判断。

## 记号 [iterator.cpp17.general]

¶1 后面的表格里，`a`、`b` 是 `X` 或 `const X` 的值，`r` 是 `X&` 的值，`n` 是 `difference_type` 的值，`t` 是值类型 `T` 的值，`o` 是可以写入输出迭代器的某个值。`difference_type`、`reference` 指 `iterator_traits<X>` 中的同名类型。注 1 提醒，对迭代器类型 `X` 必须存在 `iterator_traits<X>` 的实例化，这套要求离不开 `iterator_traits`。

## *Cpp17Iterator* [iterator.iterators]

¶1 所有迭代器都满足的基础要求。¶2 `X` 满足 *Cpp17Iterator*，当且仅当：

1. 可复制构造、可复制赋值、可交换、可析构（[[utility.arg.requirements]]、[[swappable.requirements]]）；
2. `iterator_traits<X>::difference_type` 是有符号整数类型或 `void`，`void` 留给输出迭代器；
3. 表 78 的表达式有效：`*r` 的返回类型不作规定，前提是 `r` 可以解引用；`++r` 返回 `X&`。

## *Cpp17InputIterator* [input.iterators]

¶1 `X` 满足 *Cpp17Iterator* 和 *Cpp17EqualityComparable*，并且表 79 的表达式有效：

| 表达式 | 要求 |
|---|---|
| `a != b` | 等价于 `!(a == b)`；前提是 `(a, b)` 在 `==` 的定义域内 |
| `*a` | 返回 `reference`，可以转换为 `T`；`(void)*a, *a` 等价于 `*a`；`a == b` 时 `*a` 等价于 `*b` |
| `a->m` | 等价于 `(*a).m` |
| `++r` | 之后 `r` 可以解引用或者是尾后值；`r` 先前值的所有副本不再要求可以解引用，也不再要求在 `==` 的定义域内 |
| `(void)r++` | 等价于 `(void)++r` |
| `*r++` | 可以转换为 `T`，等价于 `{ T tmp = *r; ++r; return tmp; }` |

¶2 **`==` 的定义域**（the domain of ==）就是数学上的意思：要求 `==` 有定义的那些值的集合，而且这个集合会随时间变化。每个算法根据自己怎样使用 `==` 和 `!=`，对定义域提出额外要求。例 1 以 `find(a, b, x)` 为例：它要求从 `a` 出发逐个递增，在遇到 `*i == x` 之前一定能到达 `b`。

¶3 推荐实践：输入迭代器上的算法应当单遍。注 1 指出，`a == b` 不蕴含 `++a == ++b`，值类型也不要求可复制赋值，这样 `istream_iterator` 才能作为算法的输入。

## *Cpp17OutputIterator* [output.iterators]

¶1 满足 *Cpp17Iterator*，并且表 80 的 `*r = o`、`++r`、`r++`、`*r++ = o` 都有效。`++r` 要求 `addressof(r) == addressof(++r)`，`r++` 可以转换为 `const X&`。每一个操作之后，`r` 都不再要求可以解引用，但仍然可以递增。

¶2 推荐实践：单遍。注 1 说明 `operator*` 唯一有效的用法是出现在赋值左边，通过同一个迭代器值只写一次；相等和不等不一定有定义。

## *Cpp17ForwardIterator* [forward.iterators]

¶1 `X` 满足 *Cpp17ForwardIterator*，当且仅当：

1. 满足 *Cpp17InputIterator*；
2. 可默认构造；
3. 可变迭代器的 `reference` 是 `T&`，常量迭代器的 `reference` 是 `const T&`；
4. 表 81 有效：`r++` 可以转换为 `const X&`，`*r++` 返回 `reference`；
5. 提供多遍保证。

¶2 `==` 的定义域是指向同一序列的迭代器。值初始化的迭代器可以比较，并且与同类型的其他值初始化迭代器相等；注 1 说它们就像指向同一个空序列的末尾。

¶3 **多遍保证**（multi-pass guarantee）：`a == b` 蕴含 `++a == ++b`；并且 `X` 是指针类型，或者 `(void)++X(a), *a` 等价于 `*a`，即递增一个副本不影响原件。¶4 注 2 说明，多遍保证加上可以多次通过可变迭代器赋值，使需要回头看的单向算法成为可能。

¶5 两个相等的迭代器要么都可以解引用，要么都不可以。¶6 两个可以解引用的迭代器相等，当且仅当 `*a` 和 `*b` 绑定到同一个对象。

第 3 条和 ¶6 把代理迭代器挡在了门外：`reference` 必须是真引用，相等必须意味着指向同一个对象。`vector<bool>::iterator` 的 `reference` 是代理类，严格说连 *Cpp17ForwardIterator* 都不满足，但主流实现一直把它申报为 `random_access_iterator_tag`。C++20 的 `forward_iterator` 概念去掉了这两条，改用引用在范围有效期内保持有效来排除把元素存在体内的迭代器（[[iterator.concept.forward]]）。

## *Cpp17BidirectionalIterator* [bidirectional.iterators]

¶1 在 *Cpp17ForwardIterator* 之上，表 82 要求：

- `--r` 返回 `X&`。前提是存在 `s` 使 `r == ++s`；之后 `r` 可以解引用，`--(++r) == r`，`--r == --s` 蕴含 `r == s`，`addressof(r) == addressof(--r)`。
- `r--` 可以转换为 `const X&`，`*r--` 返回 `reference`。

## *Cpp17RandomAccessIterator* [random.access.iterators]

¶1 在 *Cpp17BidirectionalIterator* 之上，表 83 用一段参考代码给出每个操作的语义：

| 表达式 | 返回 | 语义 |
|---|---|---|
| `r += n` | `X&` | 如同 `n` 次 `++`；`n` 为负时如同 `-n` 次 `--` |
| `a + n`、`n + a` | `X` | `{ X tmp = a; return tmp += n; }`，且 `a + n == n + a` |
| `r -= n` | `X&` | `return r += -n;`，前提是 `n` 的绝对值能用 `difference_type` 表示 |
| `a - n` | `X` | `{ X tmp = a; return tmp -= n; }` |
| `b - a` | `difference_type` | 前提是存在 `n` 使 `a + n == b`；`b == a + (b - a)` |
| `a[n]` | 可以转换为 `reference` | `*(a + n)` |
| `a < b` | 建模 *`boolean-testable`* | 等价于 `b - a > 0`；`<` 是全序 |
| `a > b`、`a >= b`、`a <= b` | 同上 | 由 `<` 导出 |

表里的循环只说明结果应当是什么，不是实现方式。[[iterator.requirements.general#14]] 仍然要求这些操作是常数时间。

## 两套体系对比

| 方面 | *Cpp17* 命名要求 | C++20 概念 |
|---|---|---|
| 检查方式 | 文字规格，编译器不检查 | 语法部分由编译器检查 |
| 类别从哪里读 | `iterator_traits<X>::iterator_category` | *`ITER_CONCEPT`*，优先读 `iterator_concept` |
| 可复制 | 所有迭代器 | 从 `forward_iterator` 起 |
| `==` | 从输入迭代器起 | 从 `forward_iterator` 起，之前与哨位比较 |
| `reference` | 前向起必须是真引用 | 不要求，`contiguous_iterator` 除外 |
| 差值类型 | 有符号整数或 `void` | 有符号类整数类型，可以是整数类类型 |
| 后置 `++` | 必须返回可用的值 | 输入迭代器可以返回 `void` |
| `a[n]` | 可以转换为 `reference` | 必须恰好是 `iter_reference_t` |
| 连续 | 没有这一级 | `contiguous_iterator` |
| 终点 | 与迭代器同类型 | 任何 `sentinel_for` |

## 常见误解

!!! pitfall "用 `iterator_category` 判断 C++20 迭代器的能力"
    分派代码如果还在读 `iterator_traits<I>::iterator_category`，会把 `iota`、`transform` 等视图的迭代器一律当成输入迭代器。新代码应当用概念分派，例如 `if constexpr (std::random_access_iterator<I>)`，或者直接调用 `ranges::` 版本的原语。

!!! pitfall "C++23 已经全面放宽到概念"
    C++23 的 [[P2408R5]] 放宽了 [[algorithms.requirements#4]]，但只针对第 26 章的算法，并且只在不要求可变迭代器时生效：名为 `ForwardIterator` 等的参数可以只建模对应概念。`std::advance`、`std::distance`、`std::next`、`std::prev` 和容器的迭代器对构造函数都不在其中。

## 思考题

!!! question "思考题 1"
    *Cpp17InputIterator* 的 `++r` 规定先前值的副本不再要求可以解引用，还加了一句不再要求在 `==` 的定义域内。后半句有什么用？

<details markdown="1">
<summary>答案</summary>

它说明连比较都失去了意义。`istream_iterator` 的 `==` 只比较两者引用的流是否相同（[[istream.iterator]]）。推进一个副本会从共享的流里读走数据，其余副本手里的旧值和流的状态已经对不上，这时比较它们得到的结果不反映位置，标准干脆不作任何保证。
</details>

!!! question "思考题 2"
    `std::istreambuf_iterator<char>` 的 `reference` 是 `char`，不是引用。它满足哪一级 *Cpp17* 要求？建模哪一级概念？

<details markdown="1">
<summary>答案</summary>

`reference` 不是引用，不满足 *Cpp17ForwardIterator* 的第 3 条，所以它只是 *Cpp17InputIterator*。在 C++20 中它建模 `input_iterator`，同样不是 `forward_iterator`：它本来就是单遍的，申报的 `input_iterator_tag` 也给 *`ITER_CONCEPT`* 封了顶。
</details>
