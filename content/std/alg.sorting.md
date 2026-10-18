---
title: 排序及相关操作：总则与排序
summary: [alg.sorting] 的总则——Compare 的含义、comp 必须诱导严格弱序（违反即 UB，并用 libc++ 演示坏比较器导致的越界读与硬化断言）、“相对 comp 和 proj 有序”“相对表达式划分”的定义、等价的含义；以及 sort、stable_sort、partial_sort、partial_sort_copy、is_sorted、nth_element 的契约、复杂度与 libc++ 的 introsort/pdqsort 实现
status: done
covers: alg.sorting.general, alg.sort, sort, stable.sort, partial.sort, partial.sort.copy, is.sorted, alg.nth.element
papers: P0896R4, P2562R1
related: alg.binary.search, alg.set.operations, alg.heap.operations, alg.min.max, algorithms.requirements, alg.req, concepts.compare, cmp
tags: 标准库, 算法, 排序, 严格弱序, UB, libc++
updated: 2026-10-18
---

[alg.sorting] 是本章最大的子条款，包括排序、二分查找、划分、归并、集合操作、堆、最值、字典序比较、排列生成。它们的共同点是：都依赖一个**序关系** `comp`。本页讲总则 [alg.sorting.general] 与排序算法本身；其余内容分在 [[alg.binary.search]]、[[alg.set.operations]]、[[alg.heap.operations]]、[[alg.min.max]]。

整页最重要的一句话是：**`comp` 必须诱导严格弱序，否则行为未定义**——而且这个 UB 不是理论上的：在真实标准库里，它会导致越界读写。

## `Compare` 是什么（[alg.sorting.general] ¶1–¶2）

¶1：本节在 `std` 中直接定义的操作都有两个版本：一个接受 `Compare` 函数对象，一个使用 `operator<`。

¶2：`Compare` 满足 `BinaryPredicate` 的要求（[[algorithms.requirements#7]]：*boolean-testable*、不经实参修改、对 const 实参结果相同）；调用结果转换为 `bool` 后，若第一个实参“小于”第二个则为 `true`，否则为 `false`。

注意这里的“小于”只是**名称**：`std::greater<>` 作为 `comp` 时，“小于”的意思是“数值更大”，排序结果是降序。所有“有序”“最小”的说法都是相对 `comp` 而言的。

## 严格弱序（¶3–¶4）

!!! std
    For algorithms other than those described in [alg.binary.search], `comp` shall induce a strict weak ordering on the values.

¶4 给出**严格弱序**（[[g:strict-weak-ordering]]）的定义：

- **strict**：非自反，对所有 `x`，`!comp(x, x)`；
- **weak**：比全序弱、比偏序强。定义 `equiv(a, b)` 为 `!comp(a, b) && !comp(b, a)`，要求 `comp` 与 `equiv` **都是传递的**：
    - `comp(a, b) && comp(b, c)` ⇒ `comp(a, c)`（¶4.1）
    - `equiv(a, b) && equiv(b, c)` ⇒ `equiv(a, c)`（¶4.2）

注 1 指出这样就可以证明：`equiv` 是等价关系；`comp` 在 `equiv` 的等价类上诱导出良定义的关系；该关系是严格全序。换言之，**严格弱序 = 把元素分成若干等价类，类与类之间是全序**。

（非对称性 `comp(a, b) ⇒ !comp(b, a)` 没有单独列出，因为它可以由非自反 + 传递推出。）

“诱导在**值**上”这个措辞的含义是：要求只针对算法实际会比较的那些值成立，而不是对类型的所有可能值成立。`std::sort` 一个不含 NaN 的 `vector<double>`，用 `<` 完全合法；一旦含有 NaN 就不合法了。概念层面的对应物是 `strict_weak_order`（[[concepts.compare]]）——`ranges::sort` 的约束 `sortable<I, Comp, Proj>` 要求它被**满足**，但“是否 model”（语义部分）编译器无法检查，违反仍是 {{ub}}。

### 常见的“不是严格弱序”

| 比较器 | 违反了什么 |
|---|---|
| `a <= b` | 非自反性：`comp(x, x)` 为 `true` |
| 含 NaN 的 `a < b` | `equiv` 不传递：`1 ≡ NaN`、`NaN ≡ 2`，但 `1 < 2` |
| `abs(a - b) > eps && a < b`（“容差比较”） | `equiv` 不传递：0 ≡ 0.6eps ≡ 1.2eps 但 0 < 1.2eps |
| 多字段比较写错，如 `a.x < b.x \|\| a.y < b.y` | 传递性/非对称性都可能失败：`{1,2}` 与 `{2,1}` 互相“小于” |
| 每次调用结果随机或依赖外部状态 | 不是关系，也违反 ¶2 的谓词一致性要求 |

多字段比较的正确写法是 `std::tie(a.x, a.y) < std::tie(b.x, b.y)`，或者 C++20 的 `operator<=>` 默认化（[[class.spaceship]]）。

### 违反严格弱序：真实的越界

为什么会越界？高效的快速排序分区循环为了省掉边界检查，依赖“哨兵”推理：例如“已知区间末尾有个元素不小于主元，所以 `while (comp(*++i, pivot))` 一定会在到达末尾前停下”。这个推理只在 `comp` 是严格弱序时成立。用 `<=` 时，对相等元素 `comp(x, pivot)` 永远为 `true`，循环就会冲出数组。

```cpp run title="bad_comp.cpp" flags="-std=c++2c -O1 -fsanitize=address" ub
#include <algorithm>
#include <cstdio>
#include <vector>

int main() {
    std::vector<int> v(100, 7);              // 100 个相等元素
    std::sort(v.begin(), v.end(),
              [](int a, int b) { return a <= b; });  // 不是严格弱序：comp(x, x) == true
    std::printf("done %d\n", v[0]);
}
```

本机 Clang 23 + libc++ 的实测结果：

| 编译方式 | 结果 |
|---|---|
| `-O1`（默认，硬化关闭） | 进程以 `SIGBUS` 崩溃（退出码 138） |
| `-O1 -fsanitize=address` | `AddressSanitizer: heap-buffer-overflow`，`READ of size 4`，栈顶是 `std::__introsort<…>` |
| `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_FAST` 或 `…_EXTENSIVE` | 越界检查触发陷阱指令，进程以 `SIGTRAP` 终止（退出码 133），无文字信息 |
| `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_DEBUG` | `sort.h:603: libc++ Hardening assertion __first != __end failed: Would read out of bounds, does your comparator satisfy the strict-weak ordering requirement?` |

注意：100 个元素才触发——小于 24 个元素时 libc++ 走插入排序分支，`<=` 只会导致多余的交换，“看起来没事”。UB 的表现依赖于输入规模，这正是这类 bug 难以在测试中发现的原因。

NaN 的情形更隐蔽：不会越界，只是“排不好”。debug 硬化模式会在排序结束后抽查结果：

```cpp run title="nan_sort.cpp" flags="-std=c++2c -O1 -D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_DEBUG" ub
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <vector>

int main() {
    std::vector<double> v{3, NAN, 1, 2, NAN, 0, 5, 4};
    std::sort(v.begin(), v.end(), [](double a, double b) { return a < b; });
    for (double d : v) std::printf("%g ", d);
    std::puts("");
}
```

不开硬化时输出 `3 nan 1 2 nan 0 4 5`（显然没排好）；debug 模式下报 `strict_weak_ordering_check.h:52: libc++ Hardening assertion … failed: Your comparator is not a valid strict-weak ordering` 并中止。

!!! tip "如何对浮点数正确排序"
    用 `std::ranges::sort(v, std::strong_order)`（C++20，[[cmp]]）：`strong_order` 对浮点数使用 IEEE 754 的 totalOrder，所有值（包括 ±0、各种 NaN）都有确定位置。或者先用 `std::erase_if(v, [](double d){ return std::isnan(d); })` 去掉 NaN。

## “有序”“划分”“等价”的定义（¶5–¶8）

¶5：序列**相对于 `comp` 和 `proj` 有序**（[[g:sorted-with-respect-to]]），当且仅当对每个指向序列的迭代器 `i` 和每个使 `i + n` 指向序列元素的非负整数 `n`，`bool(invoke(comp, invoke(proj, *(i + n)), invoke(proj, *i)))` 为 `false`。也就是“后面的元素不小于前面的元素”——**允许相等**，只禁止逆序。¶6：仅相对 `comp` 有序指投影为 `identity{}`。

¶7：序列 `[start, finish)` **相对于表达式 `f(e)` 划分**（[[g:partitioned-with-respect-to]]），当且仅当存在整数 `n`，使得对所有 `0 <= i < finish - start`，`f(*(start + i))` 为 `true` 当且仅当 `i < n`。即：所有使 `f` 为真的元素都在前面。这是二分查找前置条件的基础，见 [[alg.binary.search]]。

¶8：描述稳定性等概念时所说的“等价”，指严格弱序诱导的等价 `!(a < b) && !(b < a)`，**不是** `operator==`。`stable_sort` 保持的是**等价**元素的相对顺序。

## `sort`（[sort]）

- ¶2 *Preconditions*（经典版）：迭代器 *Cpp17ValueSwappable*，值类型 *Cpp17MoveConstructible* + *Cpp17MoveAssignable*。ranges 版的约束是 `sortable<I, Comp, Proj>`（[[alg.req.sortable]]）。
- ¶3 *Effects*：使 `[first, last)` 相对 `comp` 和 `proj` 有序。**不稳定**——等价元素的相对顺序未指明。
- ¶5 *Complexity*：O(N log N) 次比较与投影。这是**最坏**复杂度；C++98 时只要求“平均 N log N”，那时用朴素快速排序是合规的，C++11 收紧后实现普遍改用 introsort。

!!! impl "libc++ 的 `std::sort`"
    `__introsort`（`<__algorithm/sort.h>`）是一个 pdqsort 风格的内省排序：长度 ≤ 5 用固定比较网络；小于 24 用插入排序；超过 128 用 Tukey ninther 选主元，否则三数取中；对连续存储的算术类型配合 `less`/`greater` 使用无分支的 bitset 分区；递归深度耗尽时退化为堆排序（通过 `__partial_sort`），保证最坏 O(N log N)；若当前子区间的左邻元素与主元等价，则改用“等值靠左”的分区一次性跳过所有等值元素。递归深度上限为 `2 * bit_log2(N)`。常量求值时（`sort` 自 C++20 起是 `constexpr`）则直接用堆排序。若定义宏 `_LIBCPP_DEBUG_RANDOMIZE_UNSPECIFIED_STABILITY`，排序前还会随机打乱输入（`__debug_randomize_range`），专门用来暴露“依赖于等价元素顺序”的代码；debug 硬化模式则会在排序后抽查结果是否符合严格弱序（见上文 NaN 的例子）。

ranges 版的投影让“按成员排序”无需写 lambda：

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
    std::vector<Person> ps{{"carol", 30}, {"alice", 25}, {"bob", 30}, {"dave", 25}};
    std::ranges::stable_sort(ps, {}, &Person::age);         // 投影：按 age 比较
    assert(ps[0].name == "alice" && ps[1].name == "dave");  // 稳定：同龄者保持原相对顺序
    assert(ps[2].name == "carol" && ps[3].name == "bob");
}
```

## `stable_sort`（[stable.sort]）

¶5 的复杂度有两档：**若有足够的额外内存**，N log N 次比较（归并排序）；否则至多 N log² N 次（原地归并）。¶6：**稳定**（[[algorithm.stable]]）。

“若有足够内存”是标准中少见的、把**资源可用性**写进复杂度的条款：`stable_sort` 会尝试分配临时缓冲区（libc++ 用内部的 `__allocate_unique_temporary_buffer`），失败也不抛异常，而是降级为较慢的算法。正因为可能需要分配，`stable_sort` 在 freestanding 中被标为 `// hosted`。

`stable_sort` 在 C++26 之前不是 `constexpr`（因为常量求值中不能使用临时缓冲区的分配方式），[[P2562R1]] 让它与 `stable_partition`、`inplace_merge` 一起变成 `constexpr`；上面的 `static_assert` 在本机 libc++ 上通过。

## `partial_sort` 与 `partial_sort_copy`（[partial.sort]、[partial.sort.copy]）

`partial_sort(first, middle, last)`：把整个区间中**最小的** `middle - first` 个元素有序地放到 `[first, middle)`，¶3：其余元素在 `[middle, last)` 中顺序未指明。¶5：约 `(last - first) * log(middle - first)` 次比较——经典实现是在 `[first, middle)` 上建堆、扫描其余元素、最后 `sort_heap`。适合“取前 k 名”。

`partial_sort_copy`：把最小的 N = min(输入长度, 输出长度) 个元素有序地复制到输出区间。输入只需输入迭代器，输出需随机访问迭代器。¶4 是一条为 ranges 双投影版写的一致性要求：把输入值写入输出后，用 `proj2` 比较它与用 `proj1` 比较原值结果相同——否则“输出按 `proj2` 有序”就和“选出按 `proj1` 最小的”对不上。

## `is_sorted` 与 `is_sorted_until`（[is.sorted]）

`is_sorted_until` 返回最后一个使 `[first, i)` 有序的 `i`（¶8），`is_sorted` 定义为 `is_sorted_until(...) == last`。线性复杂度。

## `nth_element`（[alg.nth.element]）

¶3 *Effects*：

1. `nth` 处的元素恰是“若整个区间排序后会出现在该位置的元素”（除非 `nth == last`）；
2. 对任意 `i ∈ [first, nth)`、`j ∈ [nth, last)`，`comp(*j, *i)` 为 `false`——前半段都“不大于”后半段。

两段内部的顺序都未指明。¶5：非并行版**平均**线性（标准没有要求最坏线性——introselect 或 median-of-medians 才能做到，libc++ 的 `__nth_element` 是迭代式快速选择，没有最坏线性保证）；并行版 O(N) 次谓词调用和 O(N log N) 次交换。

`nth == last` 时什么也不保证——这是一个合法调用，只是没有效果描述可依赖。

```cpp run title="nth.cpp" ok
#include <algorithm>
#include <cassert>
#include <vector>

int main() {
    std::vector<int> v{9, 8, 7, 6, 5, 4, 3, 2, 1};
    std::nth_element(v.begin(), v.begin() + 4, v.end());   // 求中位数
    assert(v[4] == 5);
    assert(std::all_of(v.begin(), v.begin() + 4, [](int x) { return x <= 5; }));
    std::partial_sort(v.begin(), v.begin() + 3, v.end());  // 前 3 名
    assert(v[0] == 1 && v[1] == 2 && v[2] == 3);
}
```

## 思考题

<details markdown="1">
<summary>1. 以下比较器用于 `std::sort` 是否合法？`[](const std::string& a, const std::string& b) { return a.size() < b.size(); }`</summary>

合法。它是严格弱序：等价类是“相同长度的字符串”，类之间按长度全序；非自反、`comp` 与 `equiv` 都传递。只是 `sort` 不稳定，同长度字符串的相对顺序未指明；需要保持原顺序用 `stable_sort`。
</details>

<details markdown="1">
<summary>2. `std::sort` 中比较器抛出异常，区间会处于什么状态？</summary>

非并行 `sort` 没有为异常提供特殊保证：异常会传播出去，区间中的元素是原元素的某个排列（实现只通过交换/移动重排，不会丢失元素——但若值类型的移动操作本身也可能抛出，连这一点都不保证，因为某个元素可能正处在临时变量中）。并行版则直接 `terminate`（[[algorithms.parallel]]）。
</details>

<details markdown="1">
<summary>3. 为什么标准对 `sort` 只给 O(N log N)，对 `partial_sort` 却写“approximately (last - first) * log(middle - first)”？</summary>

`sort` 的复杂度是 C++11 收紧后的渐近要求，给实现留足选择算法的自由；`partial_sort` 的描述沿袭了 C++98 基于堆的参考实现，“approximately”说明它是对比较次数的近似刻画而非精确上界。两者都只计比较（与投影），不计交换。
</details>

## 小结

| 算法 | 稳定 | 复杂度（比较次数） | 备注 |
|---|---|---|---|
| `sort` | 否 | O(N log N)（最坏） | libc++：introsort/pdqsort 风格 |
| `stable_sort` | 是 | N log N（有内存）/ N log² N | 可能分配；C++26 起 `constexpr` |
| `partial_sort` | 否 | ≈ N log k | 取前 k 名 |
| `partial_sort_copy` | 否 | ≈ N log k | 输入可为单趟 |
| `nth_element` | 否 | 平均线性 | 选择/中位数 |
| `is_sorted(_until)` | — | 线性 | — |

- `comp` 必须在实际出现的值上诱导严格弱序；`<=`、含 NaN 的 `<`、容差比较都不行。
- 违反是真实的 UB：libc++ 上会越界读；开启 libc++ 硬化（fast/extensive/debug）可将其变成确定性的终止。
- “有序”只禁止逆序；“等价”指 `!comp(a,b) && !comp(b,a)`，不是 `==`。
