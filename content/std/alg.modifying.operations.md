---
title: 修改序列的操作
summary: copy/copy_n/copy_if/copy_backward、move/move_backward、swap_ranges/iter_swap、transform、replace、fill、generate、remove、unique、reverse、rotate、sample、shuffle、shift_left/shift_right——重叠规则（result 不在 [first,last) 内）与 _backward 的分工、remove 只“挪不删”及尾部的有效但未指明状态、unique 只合并相邻元素、transform 允许原地但禁止 op 修改区间、sample 的稳定性、C++26 有界输出重载的返回值
status: done
covers: *
papers: P0896R4, P0769R2
related: algorithms.requirements, algorithms.results, alg.nonmodifying, alg.req, algorithm.stable, rand.req.urng, sequence.reqmts
tags: 标准库, 算法, copy, remove, unique, rotate, shuffle
updated: 2026-10-18
---

本节的算法会**写**：要么写到另一个输出区间（`copy`、`transform`、`*_copy`），要么在原区间内重排（`remove`、`unique`、`reverse`、`rotate`、`shuffle`、`shift_*`）。相比只读算法，它们多出三类契约：

1. **可写性**：*Mandates* 中“`*first` is writable to `result`”（[[iterator.requirements.general]] 中“可写”的定义）——违反是编译错误；
2. **重叠**：*Preconditions* 中“`result` 不在 `[first, last)` 内”或“两个区间不重叠”——违反是 {{ub}}；
3. **元素类型要求**：原地重排需要 *Cpp17MoveAssignable*、*Cpp17ValueSwappable* 等（ranges 版用 `permutable` 等概念表达，见 [[alg.req]]）。

另外，C++26 的并行 ranges 重载普遍带**有界输出**（`result_last` 或输出 range `result_r`）：条文中“Let `result_last` be `result + M` for the overloads with no parameter `result_last` or `result_r`; Let N be min(M, result_last - result)”就是为此统一写法——不带上界的版本把上界视作“刚好够用”。

## 复制（[alg.copy]）

### `copy`（¶1–¶5）与重叠规则

¶2 *Preconditions*：**`result` 不在 `[first, last)` 内**。注意这不是“两个区间不重叠”：

- 向**左**搬（`result` 在 `first` 之前，区间重叠）是允许的——`copy` 从前往后逐个赋值（¶3 “starting from `first` and proceeding to `last`”），先读后写，不会覆盖尚未读取的元素；
- 向**右**搬且重叠（`result` 落在 `(first, last)` 内）是 {{ub}}——要用 `copy_backward`（¶26–¶30），它从 `last - 1` 往回复制，前置条件对称地变为“`result` 不在 `(first, last]` 内”。脚注 180：当 `last` 位于 `[result - N, result)` 内时，应使用 `copy_backward` 而非 `copy`。

```cpp run title="overlap.cpp" ok
#include <algorithm>
#include <cassert>
#include <vector>

int main() {
    std::vector<int> v{1, 2, 3, 4, 5, 0, 0};
    // 把 [0,5) 右移 2 格：目标区间的终点 v.end() 已给出，从后往前复制
    std::copy_backward(v.begin(), v.begin() + 5, v.end());
    assert((v == std::vector<int>{1, 2, 1, 2, 3, 4, 5}));

    // 左移：result 不在 [first,last) 内，copy 可以处理这种重叠
    std::vector<int> w{0, 0, 1, 2, 3};
    std::copy(w.begin() + 2, w.end(), w.begin());
    assert((w == std::vector<int>{1, 2, 3, 2, 3}));
}
```

!!! impl "为什么 `copy` 不等于 `memmove`"
    libc++、libstdc++ 对可平凡复制的连续区间会把 `copy`/`move` 降为 `memmove`——`memmove` 处理任意重叠，所以“向右重叠的 `copy`”在实践中常常“碰巧正确”。但这是实现细节：对非平凡类型、非连续迭代器、或 ranges 版本的投影路径，逐元素赋值就会读到已被覆盖的值。标准层面它就是 UB。

¶4：经典版返回 `result + N`，ranges 版返回 `{last, result + N}`（`copy_result`，即 `in_out_result`）——把输入终点也还给你。

### `copy_n`（¶12–¶18）与 `copy_if`（¶19–¶25）

`copy_n`：`N = max(0, n)`，负数视为 0。

`copy_if`：¶21 要求**区间不重叠**（比 `copy` 严格，因为输出位置与输入位置不再一一对应）；¶25 *Remarks*：**稳定**（[[algorithm.stable]]）——被复制的元素保持原相对顺序。¶23 规定了有界输出版本的返回值：若输出空间不够，返回 `{j, result_last}`，`j` 指向**第一个未被复制的满足条件的元素**——调用者可以据此续传。

## 移动（[alg.move]）

与 `copy` 结构完全一致，只是赋值的右边是 E(n)：经典版 `std::move(*(first + n))`，ranges 版 `ranges::iter_move(first + n)`。后者是定制点，能正确处理代理迭代器（如 `views::zip` 的迭代器）。`move_backward` 对应 `copy_backward`。

被移走的源元素处于“有效但未指明”状态（库类型的一般保证，见 [[lib.types.movedfrom]]）。

## 交换（[alg.swap]）

`swap_ranges`：¶2 两个区间**不得重叠**；经典版要求逐对 *swappable with*（[[swappable.requirements]]），并通过非限定 `swap` 调用（使 ADL 找到用户的 `swap`）；ranges 版用 `ranges::iter_swap`。¶1：经典三迭代器版令 `last2 = first2 + (last1 - first1)`——与 `equal` 的三迭代器版一样，假定第二个区间足够长。

`iter_swap(a, b)`（¶6–¶7）：如同 `swap(*a, *b)`。

## `transform`（[alg.transform]）

¶2 的前置条件有两层：

1. `op`/`binary_op` **不得**使迭代器或子区间失效，**不得**修改闭区间 `[first1, first1 + N]`、`[first2, first2 + N]`、`[result, result + N]` 中的元素（脚注 182：故意用闭区间，连尾后位置也算在内——比如 `op` 不能往 `vector` 里 `push_back` 导致 `end()` 失效）；
2. 并行版还要满足 [[algorithms.parallel.user]]。

¶6 *Remarks*：**`result` 可以等于 `first1` 或 `first2`**——即允许原地变换。这是专门的豁免：`transform` 的 *Effects* 写的是“通过每个 `i` 赋予新值 E(i)”，若没有这句，原地写就可能被理解为违反“不得修改区间元素”。但只允许**完全相等**，错开一个位置的部分重叠仍是 {{ub}}。

¶5：恰好 N 次 `op` 应用——并且特意写明“这一要求同样适用于并行重载”，不按 [[algorithms.parallel.overloads#3]] 放宽为 O(N)。

## `replace`、`fill`、`generate`（[alg.replace]、[alg.fill]、[alg.generate]）

- `replace`/`replace_if`：把满足条件的元素替换为 `new_value`；*Mandates* `new_value` 可写入 `first`。经典版返回 `void`，ranges 版返回 `last`。
- `replace_copy`/`replace_copy_if`：¶9 区间不重叠。
- `fill`/`fill_n`：`fill_n` 的 N 为 `max(0, n)`，返回 `first + N`（C++11 起，C++03 返回 `void`）。
- `generate`/`generate_n`：恰好 N 次 `gen()`；¶6：并行版的 `gen` **可以**经实参修改对象（[[algorithms.parallel.user]] 的例外）——毕竟生成器几乎总是有状态的。不过并行版调用 `gen()` 的顺序是不确定的。

## `remove` 系列：只挪不删（[alg.remove]）

¶3 *Effects*：“Eliminates all the elements … for which E(i) holds”——但 `remove` 只拿到迭代器，**无法改变容器大小**。它做的是：把要保留的元素依次前移，返回新的逻辑终点 `j`（¶4）。¶6：**稳定**。

!!! std
    Each element in the range `[ret, last)`, where `ret` is the returned value, has a valid but unspecified state, because the algorithms can eliminate elements by moving from elements that were originally in that range.

¶7 注 1：尾部 `[ret, last)` 的元素处于**有效但未指明**的状态——实现是用**移动赋值**挪元素的（¶2 要求 *Cpp17MoveAssignable*），所以尾部可能是被移走的空壳，也可能还是原值。只能对它们赋值或销毁，不要读取。

```cpp run title="remove.cpp" ok
#include <algorithm>
#include <cassert>
#include <string>
#include <vector>

int main() {
    std::vector<std::string> v{"a", "x", "b", "x", "c"};
    auto it = std::remove(v.begin(), v.end(), "x");   // 只是“挪”，不改 size
    assert(v.size() == 5);
    assert(it - v.begin() == 3);
    v.erase(it, v.end());                             // erase-remove 惯用法
    assert((v == std::vector<std::string>{"a", "b", "c"}));

    std::vector<int> w{1, 2, 2, 3, 2};
    auto n = std::erase(w, 2);                        // C++20：容器的非成员 erase 一步到位
    assert(n == 3 && (w == std::vector<int>{1, 3}));

    auto sub = std::ranges::remove(w, 3);             // ranges 版返回 subrange{j, last}
    w.erase(sub.begin(), sub.end());
    assert(w == std::vector<int>{1});
}
```

ranges 版返回 `subrange{j, last}`（正好是要擦除的部分），所以 `v.erase(sub.begin(), sub.end())` 直接可用。

!!! pitfall "`remove(v.begin(), v.end(), v[0])` 的别名问题"
    `value` 以 `const T&` 传入。若它引用的是序列中的元素，`remove` 挪动元素时会把它覆盖，后续比较就用了错的值。标准条文没有为这种别名情形给出任何保证。本机 libc++ 上，对 `{1, 2, 1, 3, 2}` 执行 `v.erase(std::remove(v.begin(), v.end(), v[0]), v.end())` 得到的是 `{2, 1, 3}`，而不是期望的 `{2, 3, 2}`；`std::erase(w, w[0])` 结果相同。安全做法：先复制一份 `auto x = v[0];` 再传入。

`remove_copy`/`remove_copy_if`（¶8–¶15）：输出不满足条件的元素，区间不得重叠，稳定。

## `unique`：只合并相邻的等价元素（[alg.unique]）

¶1：E(i) 为 `pred(*(i - 1), *i)`——每个元素只与**前一个**元素比较。所以 `unique` 去掉的是**连续**的重复；要全局去重，先排序：

```cpp run title="unique.cpp" ok
#include <algorithm>
#include <cassert>
#include <vector>

int main() {
    std::vector<int> v{1, 1, 2, 1, 1, 3};
    v.erase(std::unique(v.begin(), v.end()), v.end());
    assert((v == std::vector<int>{1, 2, 1, 3}));   // 只合并“相邻”的重复
}
```

¶2 *Preconditions*：`pred` 是**等价关系**。用非等价关系（如 `[](int a, int b){ return b - a == 1; }`，想去掉“连续递增”的元素）是 {{ub}}——虽然实际实现会给出一个可预测的结果，但该结果依赖于实现比较的是“前一个保留的元素”还是“前一个原始元素”，标准刻意不规定。¶5：非空区间恰好 `N - 1` 次谓词应用。

`unique_copy`（¶6–¶12）有一段精致的类型要求（¶9.2.2）：输入只是输入迭代器时，算法无法回头读“前一个元素”，必须**保存一份副本**——于是要求值类型 *Cpp17CopyConstructible* + *Cpp17CopyAssignable*；若输出迭代器是前向迭代器且值类型相同，就可以回读已写出的元素，只需可复制赋值；输入本身是前向迭代器则无额外要求。

## `reverse` 与 `reverse_copy`（[alg.reverse]）

`reverse`：恰好 `(last - first) / 2` 次交换。`reverse_copy`：区间不重叠，恰好 N 次赋值。C++26 并行 ranges 的有界版（¶10–¶14）只复制**末尾**的 N 个元素（倒序后排在前面的那些），返回 `{last, NEW_FIRST, result + N}`。

## `rotate` 与 `rotate_copy`（[alg.rotate]）

¶2：把 `first + i` 处的元素放到 `first + (i + (last - middle)) % (last - first)`——注 1：这是**左旋**，`middle` 成为新的首元素。¶3：返回 `first + (last - middle)`，即**原来的首元素现在所在的位置**（C++11 起；C++03 返回 `void`）。这个返回值很有用，例如“把一段元素搬到另一处”的 slide 算法就是两次 `rotate` 拼出来的。¶4：至多 `last - first` 次交换。

¶1 的要求是 *Cpp17ValueSwappable* + 值类型可移动构造/赋值——实现可以根据迭代器类别选用不同算法（前向：逐段交换；双向：三次反转；随机访问：基于 gcd 的环置换）。

## 随机：`sample` 与 `shuffle`（[alg.random.sample]、[alg.random.shuffle]）

`sample(first, last, out, n, g)`：从总体中等概率地选出 `min(last - first, n)` 个元素（每种可能的样本出现概率相等）。¶2 的迭代器要求是“二选一”：总体是前向迭代器（可用**选择抽样**，单趟、稳定），或者输出是随机访问迭代器（可用**蓄水池抽样**，输出位置会被随机覆盖）。¶6.1：当且仅当总体 model `forward_iterator` 时**稳定**——输出保持在总体中的相对顺序。

`shuffle`：等概率地产生每一种排列；恰好 `(last - first) - 1` 次交换（Fisher–Yates）。¶5：`g` 是实现**唯一**的随机源——不能偷偷用 `rand()`。这正是 C++17 移除 `random_shuffle`（其默认版本用实现定义的随机源，通常是 `rand()`）的理由之一。两者都要求 `g` 满足均匀随机位生成器要求（[[rand.req.urng]]）。

```cpp run title="sample.cpp" ok
#include <algorithm>
#include <cassert>
#include <iterator>
#include <random>
#include <vector>

int main() {
    std::vector<int> pop{1, 2, 3, 4, 5, 6, 7, 8, 9, 10};
    std::vector<int> out;
    std::mt19937 g(42);
    std::sample(pop.begin(), pop.end(), std::back_inserter(out), 3, g);
    assert(out.size() == 3);
    assert(std::ranges::is_sorted(out));   // 前向迭代器的总体 → 稳定：保持原相对顺序
    std::ranges::shuffle(pop, g);
    assert(std::ranges::is_permutation(pop, std::vector{1, 2, 3, 4, 5, 6, 7, 8, 9, 10}));
}
```

注意：同一种子在不同标准库实现上得到的样本/排列**不同**——标准只规定了分布，没有规定算法。需要跨平台可复现的洗牌，得自己实现。

## `shift_left` 与 `shift_right`（[alg.shift]）{{c++20}}

由 [[P0769R2]] 引入。`shift_left(first, last, n)`：把 `first + n + i` 处的元素移到 `first + i`；`n == 0` 或 `n >= last - first` 时什么也不做。返回新的逻辑终点 `NEW_LAST`（¶3）。与 `rotate` 的区别：被“挤出去”的元素**不会**绕回来，尾部 n 个位置留下被移走的元素。

`shift_right` 对称；¶5 要求迭代器是双向的**或**值可交换（前向迭代器版只能用交换实现“向后移动”）。¶6：仅当迭代器是双向的时才规定从后往前的移动顺序。

## 思考题

<details markdown="1">
<summary>1. `std::copy(v.begin(), v.end() - 1, v.begin() + 1)` 对 `vector<int>` 在 libc++ 上“看起来正确”，为什么仍然是 UB？</summary>

`result == v.begin() + 1` 落在 `[first, last)` 内，违反 [alg.copy] ¶2。libc++ 对 `int*` 这样的连续可平凡复制区间会走 `memmove` 路径，`memmove` 正确处理重叠，所以“看起来正确”；但标准只规定了逐个前向赋值的语义，按那个语义第二个元素会被第一个覆盖后再读取。正确写法是 `copy_backward(v.begin(), v.end() - 1, v.end())` 或 `shift_right`。
</details>

<details markdown="1">
<summary>2. `std::transform(v.begin(), v.end(), v.begin() + 1, f)` 合法吗？</summary>

不合法。¶6 只允许 `result` **等于** `first1`；`result == first1 + 1` 时，向 `*(result + i)` 的赋值修改了 `[first1, first1 + N]` 中尚未读取的元素，违反 ¶2 的前置条件。
</details>

<details markdown="1">
<summary>3. `std::remove_if` 之后立即读取 `[ret, last)` 中的 `std::string` 元素，会发生什么？</summary>

行为是良定义的（元素处于有效状态，可以调用无前置条件的成员如 `size()`），但值是**未指明**的——可能是空串（被移走），也可能是原值或某个被保留元素的旧值。不要依赖它。
</details>

## 小结

| 算法 | 重叠规则 | 稳定 | 关键点 |
|---|---|---|---|
| `copy` / `move` | `result ∉ [first, last)`（可左移） | — | 右移用 `*_backward` |
| `copy_if` / `remove_copy` / `unique_copy` | 不得重叠 | 是 | 有界版返回续传位置 |
| `transform` | 仅允许 `result == first1/first2` | — | `op` 不得修改闭区间内元素 |
| `remove` / `unique` | 原地 | 是 | 不改大小；尾部有效但未指明；`unique` 只看相邻 |
| `rotate` | 原地 | — | 左旋；返回原首元素的新位置 |
| `sample` | `out ∉ [first, last)` | 总体为前向迭代器时 | 等概率；`g` 是唯一随机源 |
| `shuffle` | 原地 | — | N−1 次交换；结果跨实现不同 |
| `shift_left/right` | 原地 | — | 不绕回；返回新逻辑区间端点 |
