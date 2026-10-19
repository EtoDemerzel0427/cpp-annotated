---
title: 修改序列的操作
summary: 会写入元素的算法：copy 与 move 的重叠规则和 _backward 版本，transform 何时可以原地进行，remove 和 unique 只移动元素、不改变容器大小，rotate 的返回值，sample 和 shuffle 的随机性，shift_left 与 shift_right，以及 C++26 有界输出重载的返回值。
status: done
covers: *
papers: P0896R4, P0769R2
related: algorithms.requirements, algorithms.results, alg.nonmodifying, alg.req, algorithm.stable, rand.req.urng, sequence.reqmts
tags: 标准库, 算法, copy, remove, unique, rotate, shuffle
updated: 2026-10-19
---

!!! tldr
    - `copy` 只要求 `result` 不在 `[first, last)` 内：向左搬的重叠复制合法，向右搬要用 `copy_backward`。
    - `transform` 允许 `result` 恰好等于输入的起点，即原地变换；错开位置的部分重叠是未定义行为。
    - `remove` 和 `unique` 只把保留的元素移到前面，返回新的逻辑终点，不改变容器大小；尾部元素处于有效但未指定的状态，要用 `erase` 删掉。
    - `unique` 只合并相邻的重复元素，全局去重要先排序。
    - `shuffle` 和 `sample` 只用传入的随机数生成器，但标准不规定具体算法，同一种子在不同标准库上结果不同。

这一节的算法会写入：要么写到另一个输出区间（`copy`、`transform`、各种 `_copy`），要么在原区间内重新排列（`remove`、`unique`、`reverse`、`rotate`、`shuffle`、`shift_left`）。与只读算法相比，它们的条文多了三类要求：

1. **可写**：*Mandates* 中写着 "`*first` is writable to `result`"（[[iterator.requirements.general]]），不满足就编译失败；
2. **重叠**：*Preconditions* 中写着 `result` 不在某个区间内，或者两个区间不重叠，违反了是{{ub}}；
3. **元素类型**：原地重排的经典版本要求 *Cpp17MoveAssignable*、*Cpp17ValueSwappable* 等，`ranges` 版本用 `permutable` 等概念表达（[[alg.req]]）。

## 复制与移动 [alg.copy]、[alg.move]

```cpp run title="overlap.cpp" ok
#include <algorithm>
#include <cassert>
#include <vector>

int main() {
  // 右移两格：区间重叠，用 copy_backward，传入目标区间的终点
  std::vector<int> v{1, 2, 3, 4, 5, 0, 0};
  std::copy_backward(v.begin(), v.begin() + 5, v.end());
  assert((v == std::vector<int>{1, 2, 1, 2, 3, 4, 5}));

  // 左移两格：result 不在 [first, last) 内，copy 可以处理
  std::vector<int> w{0, 0, 1, 2, 3};
  std::copy(w.begin() + 2, w.end(), w.begin());
  assert((w == std::vector<int>{1, 2, 3, 2, 3}));
}
```

### `copy` 的重叠规则

[alg.copy] ¶2 的前置条件是 `result` 不在 `[first, last)` 内。这不等于两个区间不重叠：

- 向左搬，`result` 在 `first` 之前，区间可以重叠。¶3 规定从 `first` 开始依次执行 `*(result + n) = *(first + n)`，每个元素都在被覆盖之前读出。
- 向右搬并且重叠，`result` 落在 `(first, last)` 内，是{{ub}}：按逐个向前赋值的语义，后面的元素会在读出之前被覆盖。

向右搬要用 `copy_backward`（¶26–¶30）。它的第三个实参是目标区间的终点，从 `last - 1` 往回复制，前置条件对称地变为 `result` 不在 `(first, last]` 内。脚注 180 说，`last` 落在 `[result - N, result)` 内时，应该用 `copy_backward` 而不是 `copy`。

¶4 经典版返回 `result + N`；`ranges` 版返回 `{last, result + N}`，把输入走到的位置也还给调用方（[[algorithms.results]]）。

!!! impl "为什么重叠的 `copy` 常常碰巧正确"
    libc++ 和 libstdc++ 对可平凡复制元素的连续区间，会把 `copy` 和 `move` 换成 `memmove`，而 `memmove` 能处理任意重叠。所以对 `vector<int>` 向右重叠复制，结果往往正确。换成非平凡的元素类型或者非连续的迭代器，实现就会逐个赋值，读到已经被覆盖的值。按标准，这种调用一律是未定义行为。

### `copy_n` 与 `copy_if`

`copy_n`（¶12–¶18）复制 `max(0, n)` 个元素，`n` 为负时当作 0。

`copy_if`（¶19–¶25）只复制满足谓词的元素。¶21 要求输入与输出区间完全不重叠，比 `copy` 严格，因为输出位置与输入位置不再一一对应。¶25 它是**稳定**的（[[algorithm.stable]]）：复制出的元素保持原来的相对顺序。

### `move` 与 `move_backward`

[alg.move] 与 `copy` 的结构完全相同，只是赋值的右边是 ¶1 中的 *E*(n)：经典版是 `std::move(*(first + n))`，`ranges` 版是 `ranges::iter_move(first + n)`。后者是定制点，对 `views::zip` 这类代理迭代器也能正确地移动。`move_backward` 对应 `copy_backward`。被移走的源元素处于有效但未指定的状态（[[lib.types.movedfrom]]）。

### C++26 的有界输出

C++26 的并行 `ranges` 重载普遍接受一个输出上界：`result_last`，或者一个输出范围 `result_r`。条文对此统一写成 "Let `result_last` be `result + (last - first)` for the overloads with no parameter `result_last` or `result_r`"，再令 N 为 `min(last - first, result_last - result)`：没有上界的版本把上界看作刚好够用。

输出写满就停下，这时返回值要告诉调用方输入处理到了哪里。¶23.3 规定 `copy_if` 此时返回 `{j, result_last}`，`j` 是第一个满足条件、但没有被复制的元素，调用方可以从这里继续。

## 交换 [alg.swap]

`swap_ranges` 逐对交换两个区间的元素。¶2 两个区间不得重叠，经典版还要求元素逐对可交换（[[swappable.requirements]]）。¶3 经典版通过非限定调用 `swap`，ADL 可以找到用户自定义的 `swap`；`ranges` 版用 `ranges::iter_swap`。¶1 经典三迭代器版令 `last2` 为 `first2 + (last1 - first1)`，与三迭代器的 `equal` 一样假定第二个区间足够长。

¶7 `iter_swap(a, b)` 的效果如同 `swap(*a, *b)`。

## `transform` [alg.transform]

```cpp
std::transform(v.begin(), v.end(), v.begin(), f);      // OK：原地变换
std::transform(v.begin(), v.end(), v.begin() + 1, f);  // UB：错开一格
```

¶3 `transform` 对输出区间的每个位置赋予 `op` 作用于对应输入元素的结果。¶2 的前置条件要求 `op` 和 `binary_op` 不使迭代器或子区间失效，也不修改闭区间 `[first1, first1 + N]`、`[first2, first2 + N]`、`[result, result + N]` 中的元素。脚注 182 说明闭区间是有意的：连尾后位置也算在内，所以 `op` 不能往 `vector` 里 `push_back` 使 `end()` 失效。

¶6 的 *Remarks* 明确允许 `result` 等于 `first1` 或 `first2`，也就是原地变换。只允许完全相等。`result == first1 + 1` 时，写入 `*(result + i)` 修改了输入区间中还没读到的元素，违反 ¶2。

¶5 `transform` 恰好调用 N 次 `op`，并且特意写明这一要求同样适用于并行重载，不按 [[algorithms.parallel.overloads#3]] 放宽为 O(N)。

## `replace`、`fill`、`generate`

- [alg.replace] `replace` 和 `replace_if` 把满足条件的元素换成 `new_value`；¶2 要求 `new_value` 能写入 `first`。¶4 经典版返回 `void`，`ranges` 版返回 `last`。`replace_copy` 系列 ¶9 要求区间不重叠。
- [alg.fill] `fill_n` 写入 `max(0, n)` 个元素，¶4 返回 `first + N`。C++03 的 `fill_n` 返回 `void`，C++11 改为返回迭代器。
- [alg.generate] `generate` 恰好调用 N 次 `gen()`（¶5）。¶6 并行版的 `gen` 可以通过实参修改对象，这是 [[algorithms.parallel.user]] 的例外，因为生成器几乎总是有状态的。并行版调用 `gen()` 的顺序不确定。

## `remove`：只移动，不删除 [alg.remove]

```cpp run title="remove.cpp" ok
#include <algorithm>
#include <cassert>
#include <string>
#include <vector>

int main() {
  std::vector<std::string> v{"a", "x", "b", "x", "c"};
  auto it = std::remove(v.begin(), v.end(), "x");  // 只移动元素，不改变 size
  assert(v.size() == 5 && it - v.begin() == 3);
  v.erase(it, v.end());                            // erase-remove 惯用法
  assert((v == std::vector<std::string>{"a", "b", "c"}));

  std::vector<int> w{1, 2, 2, 3, 2};
  auto n = std::erase(w, 2);                       // C++20：一步完成
  assert(n == 3 && (w == std::vector<int>{1, 3}));

  auto sub = std::ranges::remove(w, 3);            // 返回 {j, last}
  w.erase(sub.begin(), sub.end());
  assert(w == std::vector<int>{1});
}
```

¶3 说 `remove` "eliminates" 满足条件的元素，但它只拿到一对迭代器，无法改变容器的大小。它实际做的是把要保留的元素依次往前移，¶4 返回新的逻辑终点 `j`。¶6 它是稳定的。

!!! std
    Each element in the range `[ret, last)`, where `ret` is the returned value, has a valid but unspecified state, because the algorithms can eliminate elements by moving from elements that were originally in that range.

¶7 的注 1 解释了尾部 `[ret, last)` 的状态：实现用移动赋值搬动元素（¶2 要求 *Cpp17MoveAssignable*），尾部可能是被移走的空对象，也可能还是原值。可以对它们赋值或销毁，不要依赖它们的值。

¶4.2 `ranges` 版本返回 `{j, last}`，正好是要擦除的部分，所以可以直接传给 `erase`。C++20 起，标准容器还有非成员函数 `std::erase` 和 `std::erase_if`，一步完成 erase-remove（[[sequence.reqmts]]）。

!!! pitfall "`remove(v.begin(), v.end(), v[0])`"
    `value` 以 `const T&` 传入。它引用的是序列里的元素时，`remove` 搬动元素会覆盖它，之后的比较就用了错误的值，标准没有为这种别名情形提供任何保证。本机 libc++ 上，对 `{1, 2, 1, 3, 2}` 执行 `v.erase(std::remove(v.begin(), v.end(), v[0]), v.end())`，得到的是 `{2, 1, 3}` 而不是 `{2, 3, 2}`；`std::erase(w, w[0])` 结果相同。先复制一份 `auto x = v[0];` 再传入。

`remove_copy` 和 `remove_copy_if`（¶8–¶15）把不满足条件的元素复制到输出区间，¶11 要求区间不重叠，¶15 它们也是稳定的。

## `unique`：只合并相邻的元素 [alg.unique]

```cpp run title="unique.cpp" ok
#include <algorithm>
#include <cassert>
#include <vector>

int main() {
  std::vector<int> v{1, 1, 2, 1, 1, 3};
  v.erase(std::unique(v.begin(), v.end()), v.end());
  assert((v == std::vector<int>{1, 2, 1, 3}));   // 只合并相邻的重复

  std::vector<int> w{3, 1, 3, 2, 1};
  std::ranges::sort(w);                           // 全局去重：先排序
  auto [first, last] = std::ranges::unique(w);
  w.erase(first, last);
  assert((w == std::vector<int>{1, 2, 3}));
}
```

¶1 中 *E*(i) 是 `pred(*(i - 1), *i)`：每个元素只和前一个元素比较。所以 `unique` 去掉的是连续的重复，要全局去重得先排序。与 `remove` 一样，它返回新的逻辑终点，`ranges` 版返回要擦除的 `subrange`（¶4）。

¶2 要求 `pred` 是等价关系。用 `[](int a, int b) { return b - a == 1; }` 这样的谓词去掉连续递增的元素，是{{ub}}：实际结果取决于实现拿新元素和上一个保留的元素比较，还是和原序列中的前一个元素比较。¶5 对非空区间恰好调用 `N - 1` 次谓词。

`unique_copy` 的 ¶9.2.2 对元素类型的要求分三种情况，原因都在于算法要能读到上一个元素：

- 输入是前向迭代器：可以回头读输入，没有额外要求；
- 否则，输出是前向迭代器且值类型相同：可以读回已经写出的元素，只要求值类型可复制赋值；
- 否则：输入只能遍历一趟，算法必须自己保存一份上一个元素，要求值类型可复制构造并可复制赋值。

## `reverse` 与 `rotate`

[alg.reverse] ¶4 `reverse` 恰好交换 `(last - first) / 2` 次。`reverse_copy` 要求区间不重叠，恰好赋值 N 次。C++26 的有界版本（¶10–¶14）在输出放不下时只复制末尾的 N 个元素，也就是反转后排在前面的那些，返回 `{last, NEW_FIRST, result + N}`。

[alg.rotate] ¶2 把位于 `first + i` 的元素放到 `first + (i + (last - middle)) % (last - first)`。注 1 说这是**左旋**：`middle` 处的元素成为新的第一个元素。

¶3 经典版返回 `first + (last - middle)`，即原来的第一个元素现在的位置（C++03 返回 `void`），`ranges` 版返回 `{first + (last - middle), last}`。这个返回值很有用，比如把一段元素挪到序列的另一处，可以用两次 `rotate` 完成。¶4 至多交换 `last - first` 次。实现可以按迭代器类别选用不同的算法：前向迭代器逐段交换，双向迭代器三次反转，随机访问迭代器按最大公约数分环置换。

## 随机：`sample` 与 `shuffle`

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
  assert(std::ranges::is_sorted(out));   // 总体是前向迭代器：稳定

  std::ranges::shuffle(pop, g);
  assert(std::ranges::is_permutation(pop, std::vector{1, 2, 3, 4, 5, 6, 7, 8, 9, 10}));
}
```

[alg.random.sample] ¶3 `sample` 从总体中选出 `min(last - first, n)` 个元素，每一种可能的样本出现的概率相等。注 1 提到两种做法：选择抽样和蓄水池抽样。¶2.3 的迭代器要求是二选一：

- 总体是前向迭代器，可以用选择抽样，按顺序输出；
- 否则输出必须是随机访问迭代器，可以用蓄水池抽样，输出位置会被随机覆盖。

¶6.1 当且仅当总体是前向迭代器时，`sample` 是稳定的，样本保持在总体中的相对顺序。

[alg.random.shuffle] ¶2 `shuffle` 使每一种排列出现的概率相等，¶4 恰好交换 `(last - first) - 1` 次，即 Fisher–Yates 洗牌。¶5 规定，实现用到随机数时，`g` 就是唯一的随机源，不能另外调用 `rand()`。C++17 删除的 `random_shuffle` 没有这样的保证，它的双实参版本使用实现决定的随机源，通常就是 `rand()`。两个算法都要求 `g` 满足均匀随机位生成器的要求（[[rand.req.urng]]）。

标准只规定了结果的分布，没有规定算法，所以同一个种子在不同标准库上得到的样本和排列不同。需要跨平台复现时，只能自己实现洗牌。

## `shift_left` 与 `shift_right` [alg.shift] {{c++20}}

C++20 的 [[P0769R2]] 引入了这两个算法。¶2 `shift_left(first, last, n)` 把位于 `first + n + i` 的元素移到 `first + i`；`n == 0` 或 `n >= last - first` 时什么也不做。¶3 它返回新的逻辑终点。与 `rotate` 不同，被挤出去的元素不会绕回来，尾部 n 个位置留下的是被移走的元素。

`shift_right` 方向相反，¶7 返回新的逻辑起点。¶5 经典版要求迭代器满足 *Cpp17BidirectionalIterator* 或元素可交换：只有前向迭代器时，无法从后往前移动，只能借助交换实现。¶6 只有迭代器是双向的非并行版本，才规定从后往前依次移动。

## 思考题

!!! question "思考题 1"
    `std::copy(v.begin(), v.end() - 1, v.begin() + 1)` 对 `vector<int>` 在 libc++ 上结果看起来正确，为什么仍然是未定义行为？

<details markdown="1">
<summary>答案</summary>

`result` 是 `v.begin() + 1`，落在 `[first, last)` 内，违反了 [alg.copy] ¶2。libc++ 对 `int` 这样的连续、可平凡复制的区间用 `memmove`，它能处理重叠，所以结果看起来正确。但标准规定的是从前往后逐个赋值，按这个语义第二个元素会在读出之前被覆盖。正确的写法是 `std::copy_backward(v.begin(), v.end() - 1, v.end())`，或者 `std::shift_right(v.begin(), v.end(), 1)`。
</details>

!!! question "思考题 2"
    `std::remove_if` 之后立即读取 `[ret, last)` 中的 `std::string` 元素，会发生什么？

<details markdown="1">
<summary>答案</summary>

行为是确定的，元素处于有效状态，可以调用 `size()` 这类没有前置条件的成员函数。但它们的值未指定：可能是被移走的空字符串，也可能是原值，或者某个被保留元素的旧值。不要依赖它。
</details>

## 小结

| 算法 | 重叠规则 | 稳定 | 要点 |
|---|---|---|---|
| `copy`、`move` | `result` 不在 `[first, last)` 内，可以向左重叠 | | 向右重叠用 `_backward` 版本 |
| `copy_if`、`remove_copy`、`unique_copy` | 不得重叠 | 是 | 有界版本返回可以继续的位置 |
| `transform` | 只允许 `result` 等于输入起点 | | `op` 不得修改闭区间内的元素 |
| `remove`、`unique` | 原地 | 是 | 不改变大小；尾部有效但未指定；`unique` 只看相邻元素 |
| `rotate` | 原地 | | 左旋；返回原第一个元素的新位置 |
| `sample` | `out` 不在 `[first, last)` 内 | 总体为前向迭代器时 | 等概率；`g` 是唯一随机源 |
| `shuffle` | 原地 | | N − 1 次交换；结果因实现而异 |
| `shift_left`、`shift_right` | 原地 | | 元素不绕回；返回新的逻辑端点 |
