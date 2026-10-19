---
title: 排序及相关操作：总则与排序
summary: 比较器 comp 必须满足什么条件（严格弱序）、违反时在真实标准库里会发生什么；有序、划分、等价这几个词的精确含义；sort、stable_sort、partial_sort、nth_element 等排序算法的保证与复杂度。
status: done
covers: alg.sorting.general, alg.sort, sort, stable.sort, partial.sort, partial.sort.copy, is.sorted, alg.nth.element
papers: P0896R4, P2562R1
related: alg.binary.search, alg.set.operations, alg.heap.operations, alg.min.max, algorithms.requirements, alg.req, concepts.compare, cmp
tags: 标准库, 算法, 排序, 严格弱序, UB, libc++
updated: 2026-10-19
---

!!! tldr
    - 除二分查找外，[alg.sorting] 里所有算法都要求比较器在实际参与比较的值上构成严格弱序，否则行为未定义。
    - `<=`、含 NaN 的 `<`、带容差的比较都不是严格弱序。在 libc++ 上，用 `<=` 排序 100 个相等元素会读越界；开启加固模式可以把它变成确定的终止。
    - 有序只禁止逆序，允许相等；等价指 `!comp(a, b) && !comp(b, a)`，与 `operator==` 无关。
    - `sort` 不稳定、最坏 O(N log N)；`stable_sort` 稳定，复杂度取决于能否分配到额外内存；`nth_element` 只保证平均线性。

## 用 `<=` 排序会怎样

```cpp run title="bad_comp.cpp" flags="-std=c++2c -O1 -fsanitize=address" ub
#include <algorithm>
#include <cstdio>
#include <vector>

int main() {
    std::vector<int> v(100, 7);              // 100 个相等元素
    std::sort(v.begin(), v.end(),
              [](int a, int b) { return a <= b; });
    std::printf("done %d\n", v[0]);
}
```

比较器写成 `a <= b` 看起来只是允许了相等，但这段代码是未定义行为。本机 Clang 23 + libc++ 的结果：

| 编译方式 | 结果 |
|---|---|
| `-O1` | 进程以 `SIGBUS` 崩溃 |
| `-O1 -fsanitize=address` | AddressSanitizer 报告 `heap-buffer-overflow`，越界读发生在 `std::__introsort` 里 |
| 加 `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_FAST` | 越界检查触发陷阱，进程以 `SIGTRAP` 终止，没有文字信息 |
| 加 `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_DEBUG` | 报告 `Would read out of bounds, does your comparator satisfy the strict-weak ordering requirement?` 后中止 |

元素少于 24 个时，libc++ 改用插入排序，`<=` 只会造成多余的移动，程序看起来正常。同一个 bug 是否暴露取决于输入规模，所以这类错误很难靠测试发现。

越界的原因在快速排序的分区循环里。为了省掉边界检查，循环依赖一个推理："区间末尾有一个元素不小于主元，所以 `while (comp(*++i, pivot))` 一定会在走出区间之前停下。"这个推理只在 `comp(x, x)` 为假时成立。用 `<=` 时，所有与主元相等的元素都让条件为真，循环就走出了数组。

## 比较器 `Compare`（[alg.sorting.general] ¶1–¶3）

¶1 本节直接定义在 `std` 中的算法都有两个版本，一个接受比较器，一个使用 `operator<`。¶3 规定后者等价于把 `comp(*i, *j)` 换成 `*i < *j`。

¶2 比较器类型 `Compare` 要满足 `BinaryPredicate` 的要求（[[algorithms.requirements#7]]）：调用结果能当作 `bool` 用，调用不经由实参修改元素。它的返回值转换为 `bool` 后，第一个实参小于第二个时为 `true`，否则为 `false`。

这里的小于只是一个名字。把 `std::greater<>` 作为 `comp` 传入时，"小于"的意思是数值更大，排序结果是降序。本章所有"有序""最小"的说法都相对于 `comp`。

!!! std
    For algorithms other than those described in [alg.binary.search], `comp` shall induce a strict weak ordering on the values.

这是 ¶3 的最后一句，开头的 `<=` 例子违反的就是它。二分查找被排除在外，它只需要更弱的划分性质，见 [[alg.binary.search]]。

## 严格弱序（¶4）

¶4 **严格弱序**（strict weak ordering，[[g:strict-weak-ordering]]）由三条组成。先定义 `equiv(a, b)` 为 `!comp(a, b) && !comp(b, a)`，即两者谁也不小于谁。然后要求：

- 非自反：对所有 `x`，`comp(x, x)` 为假。这是 strict 的含义；
- ¶4.1 `comp` 可传递：`comp(a, b) && comp(b, c)` 蕴含 `comp(a, c)`；
- ¶4.2 `equiv` 可传递：`equiv(a, b) && equiv(b, c)` 蕴含 `equiv(a, c)`。

注 1 指出，满足这些条件后，`equiv` 是一个等价关系，`comp` 在等价类之间诱导出一个严格全序。换句话说，严格弱序就是把元素分成若干等价类，类与类之间排成一条直线。weak 指它比全序弱（允许不同的元素等价），又比偏序强（等价必须可传递）。

非对称性（`comp(a, b)` 蕴含 `!comp(b, a)`）没有单独列出，因为它可以由非自反和传递推出。

要求只针对算法实际比较的值。用 `<` 排序一个不含 NaN 的 `vector<double>` 完全合法，含有 NaN 时就不合法了。

`ranges::sort` 用概念 `sortable<I, Comp, Proj>` 约束比较器，其中包含 `strict_weak_order`（[[concepts.compare]]）。但概念只能检查语法上能否调用；比较器在语义上是不是严格弱序，编译器无法检查，违反时仍是 {{ub}}。

### 常见的错误比较器

| 比较器 | 违反了哪一条 |
|---|---|
| `a <= b` | 非自反：`comp(x, x)` 为真 |
| 含 NaN 时的 `a < b` | `equiv` 不传递：`1` 与 NaN 等价，NaN 与 `2` 等价，但 `1 < 2` |
| `abs(a - b) > eps && a < b`（容差比较） | `equiv` 不传递：`0` ≡ `0.6eps` ≡ `1.2eps`，但 `0` 小于 `1.2eps` |
| `a.x < b.x \|\| a.y < b.y` | 非对称性不成立：`{1, 2}` 与 `{2, 1}` 互相小于对方 |
| 结果依赖随机数或外部状态 | 根本不是一个确定的关系 |

多字段比较的正确写法是 `std::tie(a.x, a.y) < std::tie(b.x, b.y)`，或者默认化 `operator<=>`（[[class.spaceship]]）。

### NaN：不越界，但排不对

```cpp run title="nan_sort.cpp" flags="-std=c++2c -O1 -D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_DEBUG" ub
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <vector>

int main() {
    std::vector<double> v{3, NAN, 1, 2, NAN, 0, 5, 4};
    std::sort(v.begin(), v.end(),
              [](double a, double b) { return a < b; });
    for (double d : v) std::printf("%g ", d);
    std::puts("");
}
```

不开加固时，本机输出 `3 nan 1 2 nan 0 4 5`，显然没有排好。debug 加固模式会在排序后抽查结果，报告 `Your comparator is not a valid strict-weak ordering` 并中止。

!!! tip "浮点数的正确排序方法"
    用 `std::ranges::sort(v, std::strong_order)`（C++20，[[cmp]]）。`strong_order` 对浮点数采用 IEEE 754 的 totalOrder，±0 和各种 NaN 都有确定的位置。也可以先用 `std::erase_if(v, [](double d) { return std::isnan(d); })` 去掉 NaN。

## 有序、划分与等价（¶5–¶8）

¶5 一个序列**相对于 `comp` 和 `proj` 有序**（sorted with respect to，[[g:sorted-with-respect-to]]），指对序列中任意位置 `i` 和任意非负整数 `n`（只要 `i + n` 仍在序列内），

```cpp
bool(invoke(comp, invoke(proj, *(i + n)), invoke(proj, *i)))
```

都为 `false`。其中 `proj` 是**投影**（[[g:projection]]）：比较之前先对元素调用的函数，例如取某个成员。这个定义是说，后面的元素不小于前面的元素。相等是允许的，禁止的只是逆序。¶6 只说相对于 `comp` 有序时，投影取 `identity{}`。

¶7 序列 `[start, finish)` **相对于表达式 `f(e)` 划分**（partitioned with respect to，[[g:partitioned-with-respect-to]]），指存在整数 `n`，使得 `f(*(start + i))` 为真当且仅当 `i < n`。也就是所有使 `f` 为真的元素都排在前面。二分查找的前置条件就是用它表述的。

¶8 讲稳定性等概念时所说的等价，是严格弱序诱导出的等价 `!(a < b) && !(b < a)`，不一定是 `operator==`。`stable_sort` 保持的是等价元素之间的相对顺序。

## `sort`（[sort]）

¶2 对 `std` 中的版本，迭代器要满足 *Cpp17ValueSwappable*，元素类型要能移动构造和移动赋值。`ranges` 版本改用概念 `sortable<I, Comp, Proj>` 约束（[[alg.req.sortable]]）。

¶3 `sort` 使区间相对于 `comp` 和 `proj` 有序。它不稳定：等价元素的相对顺序没有规定。

¶5 复杂度是 O(N log N) 次比较和投影，这是最坏情况的要求。C++98 只要求平均 N log N，当时朴素的快速排序也合规；C++11 收紧之后，实现普遍改用内省排序（introsort）：先做快速排序，递归过深时转为堆排序。

!!! impl "libc++ 的 `std::sort`"
    libc++ 的 `__introsort`（`<__algorithm/sort.h>`）是 pdqsort 风格的内省排序。少于 24 个元素时用插入排序；超过 128 个元素时用 Tukey ninther 选主元，否则三数取中；对连续存储的算术类型配合 `less`/`greater` 使用无分支的 bitset 分区；递归深度耗尽时转为堆排序，保证最坏 O(N log N)。常量求值中（`sort` 自 C++20 起是 `constexpr`）直接使用堆排序。
    
    定义宏 `_LIBCPP_DEBUG_RANDOMIZE_UNSPECIFIED_STABILITY` 后，libc++ 会在排序前随机打乱输入，用来暴露依赖等价元素顺序的代码。

有了投影，`ranges` 版本可以直接按成员排序，不必写 lambda：

```cpp run title="sort_proj.cpp" ok
#include <algorithm>
#include <array>
#include <cassert>
#include <string>
#include <vector>

struct Person { std::string name; int age; };

constexpr bool test_constexpr() {
    std::array a{5, 3, 4, 1, 2};
    std::ranges::stable_sort(a);              // C++26 起 constexpr
    return std::ranges::is_sorted(a);
}
static_assert(test_constexpr());

int main() {
    std::vector<Person> ps{{"carol", 30}, {"alice", 25},
                           {"bob", 30}, {"dave", 25}};
    std::ranges::stable_sort(ps, {}, &Person::age);   // 按 age 比较
    // 稳定：同龄者保持原来的相对顺序
    assert(ps[0].name == "alice" && ps[1].name == "dave");
    assert(ps[2].name == "carol" && ps[3].name == "bob");
}
```

## `stable_sort`（[stable.sort]）

¶6 `stable_sort` 是**稳定**的（[[algorithm.stable]]）：等价元素保持原来的相对顺序。

¶5 它的复杂度分两档：有足够的额外内存时，N log N 次比较（归并排序）；否则至多 N log² N 次（原地归并）。标准很少把资源是否可用写进复杂度。实际上 `stable_sort` 会尝试分配一块临时缓冲区，分配失败时不抛异常，而是改用较慢的原地算法。也因为这样，它在概要中标为 `// hosted`，[[g:freestanding-implementation|独立实现]]不必提供。

C++26 起 `stable_sort`、`stable_partition`、`inplace_merge` 都是 `constexpr`（[[P2562R1]]），上例的 `static_assert` 在本机 libc++ 上通过。

## `partial_sort` 与 `partial_sort_copy`（[partial.sort]、[partial.sort.copy]）

¶3 `partial_sort(first, middle, last)` 把整个区间中最小的 `middle - first` 个元素按序放到 `[first, middle)`，其余元素以未指定的顺序留在 `[middle, last)`。¶5 约 `(last - first) * log(middle - first)` 次比较。经典实现在 `[first, middle)` 上建堆，扫描其余元素，最后对堆排序。它适合取前 k 名。

`partial_sort_copy` 把最小的 N 个元素按序复制到输出区间，N 是输入长度与输出长度中较小的那个。输入只需输入迭代器，输出需要随机访问迭代器。

¶4 是为 `ranges` 双投影版本写的一致性要求：把一个输入值写进输出区间之后，用 `proj2` 比较它的结果，必须与用 `proj1` 比较原值的结果相同。否则选出按 `proj1` 最小的元素和让输出按 `proj2` 有序这两件事就对不上。

## `is_sorted` 与 `is_sorted_until`（[is.sorted]）

¶8 `is_sorted_until` 返回最后一个使 `[first, i)` 有序的 `i`。`is_sorted` 定义为 `is_sorted_until(...) == last`。¶9 两者都是线性复杂度。

## `nth_element`（[alg.nth.element]）

¶3 `nth_element(first, nth, last)` 之后：

1. `nth` 处的元素恰好是整个区间排序后会出现在这个位置的那个元素（`nth == last` 时除外）；
2. 对任意 `i` 属于 `[first, nth)`、`j` 属于 `[nth, last)`，`comp(*j, *i)` 为假，即前半段的元素都不大于后半段的元素。

两段内部的顺序都没有规定。`nth == last` 是合法调用，只是没有任何效果可以依赖。

¶5 非并行版本只要求平均线性，不要求最坏线性。最坏线性需要 median-of-medians 一类算法；libc++ 的 `__nth_element` 是迭代式快速选择，没有最坏线性的保证。并行版本要求 O(N) 次谓词调用和 O(N log N) 次交换。

```cpp run title="nth.cpp" ok
#include <algorithm>
#include <cassert>
#include <vector>

int main() {
    std::vector<int> v{9, 8, 7, 6, 5, 4, 3, 2, 1};
    // 求中位数
    std::nth_element(v.begin(), v.begin() + 4, v.end());
    assert(v[4] == 5);
    assert(std::all_of(v.begin(), v.begin() + 4,
                       [](int x) { return x <= 5; }));
    // 前 3 名
    std::partial_sort(v.begin(), v.begin() + 3, v.end());
    assert(v[0] == 1 && v[1] == 2 && v[2] == 3);
}
```

## 思考题

!!! question "思考题 1"
    `[](const std::string& a, const std::string& b) { return a.size() < b.size(); }` 能用作 `std::sort` 的比较器吗？

<details markdown="1">
<summary>答案</summary>

能。它是严格弱序：等价类是长度相同的字符串，类与类之间按长度排成全序；它非自反，`comp` 和 `equiv` 都可传递。只是 `sort` 不稳定，同样长度的字符串之间的顺序没有规定；需要保持原顺序时用 `stable_sort`。
</details>

!!! question "思考题 2"
    `std::sort` 的比较器抛出异常时，区间会处于什么状态？元素还是原来那些元素的一个排列吗？

<details markdown="1">
<summary>答案</summary>

标准对此没有任何保证，不能认为元素只是被重排了。本机 libc++ 上，对 `{5, 3, 8, 1, 9, 2, 7, 4, 6, 0}` 排序、让第 4 次比较抛出，结果是 `3 5 8 8 9 2 7 4 6 0`：`8` 出现了两次，`1` 不见了。原因是插入排序把当前元素移到一个临时变量里，再把前面的元素逐个后移；比较在中途抛出时，临时变量被销毁，空出的位置里留着一个重复值。

并行版本中比较器抛出异常时，后果由执行策略决定（[[algorithms.parallel.exceptions]]）；对标准库提供的执行策略，结果是调用 `std::terminate`（[[execpol]]）。
</details>

!!! question "思考题 3"
    为什么标准对 `sort` 只写 O(N log N)，对 `partial_sort` 却写 approximately `(last - first) * log(middle - first)`？

<details markdown="1">
<summary>答案</summary>

`sort` 的复杂度是渐近要求，给实现留出选择算法的自由。`partial_sort` 的写法沿袭自 C++98 基于堆的参考实现，approximately 表明它是对比较次数的近似刻画，不是精确上界。两者都只计比较和投影，不计交换。
</details>

## 小结

| 算法 | 稳定 | 比较次数 | 备注 |
|---|---|---|---|
| `sort` | 否 | O(N log N)，最坏情况 | libc++ 用 pdqsort 风格的内省排序 |
| `stable_sort` | 是 | N log N（有内存）或 N log² N | 可能分配内存；C++26 起 `constexpr` |
| `partial_sort` | 否 | 约 N log k | 取前 k 名 |
| `partial_sort_copy` | 否 | 约 N log k | 输入可以是单趟迭代器 |
| `nth_element` | 否 | 平均线性 | 选择、求中位数 |
| `is_sorted`、`is_sorted_until` | 不适用 | 线性 | |
