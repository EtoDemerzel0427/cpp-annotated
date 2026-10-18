---
title: 搜索器
summary: default_searcher、boyer_moore_searcher、boyer_moore_horspool_searcher 三个函数对象：构造时接收模式串，调用时在目标序列中查找并返回 [i, j) 一对迭代器；Boyer–Moore 系列要求哈希与相等谓词一致（pred(A, B) 蕴含 hf(A) == hf(B)），通过 std::search 的 Searcher 重载使用
status: done
covers: *
papers: P0220R1
related: function.objects, alg.search, unord.hash, hash.requirements, algorithms.requirements
tags: 标准库, functional, 搜索器, Boyer-Moore, 字符串搜索
updated: 2026-10-18
---

`std::search(first, last, s_first, s_last)` 规定了结果却没规定算法，实现一般用朴素的 O(N·M) 匹配。对于长模式串或需要对同一模式反复搜索的场景，Boyer–Moore 类算法通过**预处理模式串**、在失配时跳过多个位置，平均情况下快得多。C++17 把 Library Fundamentals TS 中的“搜索器”并入标准（[[P0220R1]]）：搜索器是一个**函数对象**，模式串在构造时给出（预处理只做一次），目标序列在调用时给出。

## 一般规定（[func.search.general]）

- ¶1：模式串 `[pat_first, pat_last)` 交给构造函数；被搜索的序列 `[first, last)` 交给函数调用运算符。
- ¶2：每个搜索器特化都必须满足 *Cpp17CopyConstructible* 与 *Cpp17CopyAssignable*。名为 `ForwardIterator1`、`RandomAccessIterator2`、`BinaryPredicate` 等的模板形参与算法库中同名形参有相同的要求和语义（[[algorithms.requirements]]）；名为 `Hash` 的形参必须满足 *Cpp17Hash*（[[hash.requirements]]）。
- ¶3：Boyer–Moore 搜索器实现 Boyer–Moore 算法，Boyer–Moore–Horspool 搜索器实现 Boyer–Moore–Horspool 算法；一般而言前者占用更多内存、运行更快。这句话不具备可检验的规范含义——标准并没有、也无法精确定义“实现某算法”——它表达的是设计意图。

## 与 `std::search` 配合

[[alg.search]] 为搜索器提供了专门的重载：

```cpp
template<class ForwardIterator, class Searcher>
  constexpr ForwardIterator search(ForwardIterator first, ForwardIterator last, const Searcher& searcher);
// Effects: Equivalent to: return searcher(first, last).first;
```

它只是转调搜索器，并丢掉第二个迭代器；而且 `Searcher` **不需要**可复制构造。若需要匹配区间的终点，直接调用搜索器即可：`auto [i, j] = searcher(first, last);`。

```cpp run title="searchers.cpp" ok
#include <functional>
#include <algorithm>
#include <string>
#include <string_view>
#include <cstdio>
int main() {
  std::string text = "the quick brown fox jumps over the lazy dog";
  std::string_view pat = "lazy";
  auto it = std::search(text.begin(), text.end(),
                        std::boyer_moore_searcher(pat.begin(), pat.end()));   // CTAD
  std::printf("%td\n", it - text.begin());                                    // 35

  std::boyer_moore_horspool_searcher bmh(pat.begin(), pat.end());
  auto [first, last] = bmh(text.begin(), text.end());                         // 直接调用得到 [i, j)
  std::printf("%td %td\n", first - text.begin(), last - text.begin());        // 35 39

  std::default_searcher ds(pat.begin(), pat.end());                           // 只需前向迭代器
  std::printf("%td\n", std::search(text.begin(), text.end(), ds) - text.begin());
}
```

注意模式串的迭代器类型（`string_view::const_iterator`）与目标序列的迭代器类型（`string::iterator`）不同，这是允许的：搜索器的 `operator()` 是独立的成员模板，只要求**值类型相同**（见下）。

## `default_searcher`（[func.search.default]）

```cpp
template<class ForwardIterator1, class BinaryPredicate = equal_to<>>
class default_searcher;
```

- 保存 `pat_first_`、`pat_last_`、`pred_`（¶1），构造只可能抛出迭代器或谓词复制构造的异常（¶2）。
- ¶3 `operator()`：返回 `i`、`j`，其中 `i == search(first, last, pat_first_, pat_last_, pred_)`；若 `i == last` 则 `j == last`，否则 `j == next(i, distance(pat_first_, pat_last_))`。

它就是“把 `std::search` 包装成搜索器接口”，只要求前向迭代器，C++20 起构造函数和 `operator()` 都是 `constexpr`，并且是 freestanding 的。它的价值在于**统一接口**：写一个接受任意 `Searcher` 的泛型函数，调用方按需传入不同算法。

## `boyer_moore_searcher` 与 `boyer_moore_horspool_searcher`（[func.search.bm]、[func.search.bmh]）

两个类模板的规格**逐段相同**，只是名字与“实现的算法”不同：

```cpp
template<class RandomAccessIterator1,
         class Hash = hash<typename iterator_traits<RandomAccessIterator1>::value_type>,
         class BinaryPredicate = equal_to<>>
class boyer_moore_searcher;
```

### 构造函数（¶1–¶4）

- ¶1 **Preconditions**：模式串的值类型满足 *Cpp17DefaultConstructible*、*Cpp17CopyConstructible*、*Cpp17CopyAssignable*——实现要用值类型作为跳转表的键。
- ¶2：设 `V` 为值类型。对任意两个 `V` 值 `A`、`B`，**若 `pred(A, B) == true`，则 `hf(A) == hf(B)` 必须为 true**。这是紧跟在 ¶1 之后的前置条件：违反它，行为未定义 {{ub}}。
- ¶3 **Effects**：保存模式串迭代器、`hash_`、`pred_`。
- ¶4 **Throws**：迭代器的复制构造、值类型的默认构造/复制构造/复制赋值、谓词或哈希的复制构造与 `operator()` 抛出的任何异常；内部数据结构分配失败时**可能抛出 `bad_alloc`**。所以 Boyer–Moore 搜索器的构造**会分配内存**，也因此它们既不是 `constexpr` 也不是 freestanding 的。

### 为什么需要哈希，以及“一致性”从何而来

Boyer–Moore 系列算法的核心是一张“坏字符表”：对模式串中出现的每个**不同的**值，记录它最后出现的位置。对 `char` 这样的小类型可以用 256 项的数组；对一般的值类型，实现只能用**哈希表**——键是 `V`，哈希用 `Hash`，判等用 `BinaryPredicate`。

哈希表能工作的前提是：**判等相等的两个键，哈希值必须相同**（这也是无序容器对 `Hash`/`Pred` 的要求，见 [[unord.hash]]）。¶2 把这一点写成了对用户的要求。最常见的违反方式是只改谓词、忘了改哈希：

```cpp run title="hash_pred_consistency.cpp" ub
#include <functional>
#include <algorithm>
#include <cctype>
#include <string>
#include <cstdio>
struct ci_eq {
  bool operator()(char a, char b) const {
    return std::tolower(static_cast<unsigned char>(a)) == std::tolower(static_cast<unsigned char>(b));
  }
};
struct ci_hash {
  std::size_t operator()(char c) const {
    return std::hash<int>{}(std::tolower(static_cast<unsigned char>(c)));
  }
};
int main() {
  std::string text = "Hello WORLD", pat = "world";
  std::boyer_moore_searcher good(pat.begin(), pat.end(), ci_hash{}, ci_eq{});
  std::printf("%td\n", std::search(text.begin(), text.end(), good) - text.begin());   // 6

  std::boyer_moore_searcher bad(pat.begin(), pat.end(), std::hash<char>{}, ci_eq{});  // UB：违反 ¶2
  std::printf("%td\n", std::search(text.begin(), text.end(), bad) - text.begin());    // 本机输出 11（没找到）
}
```

`bad` 中 `'w'` 与 `'W'` 判等相等，但 `std::hash<char>` 给出不同的哈希值，于是查表时 `'W'` 被当成“模式串中不存在的字符”，算法跳过了真正的匹配位置。这种错误不会崩溃，只会**静默地给出错误答案**。

### 函数调用运算符（¶5–¶8）

- ¶5 **Mandates**：`RandomAccessIterator1` 与 `RandomAccessIterator2` 的**值类型相同**。在 `std::string` 里搜 `std::vector<char>` 的模式可以，在 `std::u8string` 里搜 `std::string` 的模式就是非良构。
- ¶7 **Returns**：`i` 是 `[first, last - 模式长度)` 中第一个对所有 `n` 都有 `pred(*(i + n), *(pat_first_ + n)) != false` 的迭代器，`j == next(i, 模式长度)`。模式为空时返回 `make_pair(first, first)`；找不到时返回 `make_pair(last, last)`。
- ¶8 **Complexity**：至多 (last − first) × (模式长度) 次谓词调用。

两点值得细看：

1. ¶7.1 写的是左闭右开区间 `[first, last - (pat_last_ - pat_first_))`，严格读来**不包含**“恰好匹配在末尾”的那个位置 `last - 模式长度`。这显然不是本意——实际实现都能找到末尾的匹配（本机测试中，在 `"abclazy"` 里搜 `"lazy"`，两个搜索器都返回位置 3），属于条文措辞上的瑕疵。
2. ¶8 的复杂度只是一个**最坏情况上界**，与朴素搜索相同。Boyer–Moore 的优势（平均次线性）在标准里没有任何可检验的表述——¶3 的“一般而言更快”是非规范性质的描述。

## libc++ 实现笔记

- `__functional/default_searcher.h`：转调内部的 `std::__search_impl`，即 `std::search` 的同一份实现。
- `__functional/boyer_moore_searcher.h`：坏字符表 `_BMSkipTable` 有两个特化——当值类型是**单字节整型**、且 `Hash` 恰为 `hash<value_type>`、`BinaryPredicate` 恰为 `equal_to<>` 时，用 `std::array<difference_type, 256>`；否则用 `unordered_map<_Key, _Value, _Hash, _BinaryPredicate>`。所以一旦你传入自定义谓词（哪怕只是 `std::equal_to<char>` 而不是 `equal_to<>`），就会走哈希表路径，¶2 的一致性要求也就真正生效了。
- 预处理表以 `shared_ptr` 持有，复制搜索器时共享同一份表——这满足 ¶2 的可复制要求而不必重做预处理。

## 历史演进

!!! history
    搜索器最早出现在 Library Fundamentals TS（`std::experimental`），C++17 经 [[P0220R1]] 并入标准。并入时还修改了接口：TS 中的 `operator()` 只返回匹配起点，C++17 改为返回 `pair`（同时给出终点）。C++20 起 `default_searcher` 成为 `constexpr`。

## 思考题

!!! question "思考题"
    为了在 `std::vector<std::string>` 里查找一个由若干 `std::string` 组成的子序列，用 `boyer_moore_searcher` 有意义吗？需要提供什么？

<details markdown="1">
<summary>展开查看答案与解析</summary>

可以用：值类型 `std::string` 满足默认构造、复制构造、复制赋值（¶1），`std::hash<std::string>` 是启用的特化，默认的 `equal_to<>` 与它一致（¶2），`vector` 迭代器是随机访问的。每个“字符”是一整个字符串，坏字符表是一个 `unordered_map<std::string, ...>`，比较的代价比 `char` 高得多，但当模式较长、字符串种类较多时仍能跳过大量位置。若改用大小写不敏感的比较，必须同时提供大小写不敏感的哈希。
</details>

## 小结

!!! summary
    | 要点 | `default_searcher` | `boyer_moore(_horspool)_searcher` |
    |---|---|---|
    | 迭代器 | 前向 | 随机访问 |
    | 额外形参 | `BinaryPredicate` | `Hash`、`BinaryPredicate` |
    | 前置条件 | — | 值类型可默认构造/复制；`pred(A, B)` ⇒ `hf(A) == hf(B)` |
    | 构造 | 不分配；`constexpr` | 预处理、可能抛 `bad_alloc`；非 `constexpr` |
    | `operator()` | `pair{i, j}`，基于 `std::search` | `pair{i, j}`；Mandates 两边值类型相同 |
    | freestanding | 是 | 否 |
    | 用法 | `std::search(first, last, searcher)` 或直接 `searcher(first, last)` | 同左 |
