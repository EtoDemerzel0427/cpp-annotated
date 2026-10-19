---
title: 搜索器
summary: default_searcher、boyer_moore_searcher 和 boyer_moore_horspool_searcher 在构造时接收模式串、调用时在目标序列中查找，返回匹配区间；Boyer–Moore 系列要求哈希与相等谓词一致。
status: done
covers: *
papers: P0220R1, P0253R1
related: function.objects, alg.search, unord.hash, hash.requirements, algorithms.requirements
tags: 标准库, functional, 搜索器, Boyer-Moore, 字符串搜索
updated: 2026-10-19
---

!!! tldr
    - 搜索器是一个函数对象：构造时给出要找的模式串（预处理只做一次），调用时给出被搜索的序列，返回匹配区间 `[i, j)`。
    - 通过 `std::search(first, last, searcher)` 使用时只得到起点；直接调用 `searcher(first, last)` 能同时得到终点。
    - `default_searcher` 只是把 `std::search` 包装成搜索器接口，只需前向迭代器，是 `constexpr` 和 freestanding 的。
    - 两个 Boyer–Moore 搜索器要求随机访问迭代器，构造时可能分配内存，并要求 `pred(A, B)` 为 true 时 `hf(A) == hf(B)`；违反这一点是 UB，通常表现为静默地找错。

## 用法

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
                        std::boyer_moore_searcher(pat.begin(), pat.end()));
  std::printf("%td\n", it - text.begin());                              // 35

  std::boyer_moore_horspool_searcher bmh(pat.begin(), pat.end());
  auto [first, last] = bmh(text.begin(), text.end());                   // 直接调用
  std::printf("%td %td\n", first - text.begin(), last - text.begin());  // 35 39

  std::default_searcher ds(pat.begin(), pat.end());                     // 只需前向迭代器
  std::printf("%td\n", std::search(text.begin(), text.end(), ds) - text.begin());   // 35
}
```

`std::search(first, last, s_first, s_last)` 规定了结果而没有规定算法，实现一般用朴素匹配，最坏 O(N·M)。模式串较长、或者要用同一个模式反复搜索时，Boyer–Moore 类算法先预处理模式串，失配时一次跳过多个位置，平均情况下快得多。

所以搜索器把一次搜索拆成两步。[func.search.general] 第 1 段规定：模式串 `[pat_first, pat_last)` 交给构造函数，被搜索的序列 `[first, last)` 交给函数调用运算符。预处理在构造时完成，之后可以多次调用。

[[alg.search]] 为搜索器提供了一个专门的 `std::search` 重载，效果等价于 `return searcher(first, last).first;`，只转调搜索器，并丢掉终点。需要终点时直接调用搜索器即可。

上例中模式串的迭代器是 `string_view::const_iterator`，目标序列的迭代器是 `string::iterator`，两者类型不同也没关系。搜索器的 `operator()` 是独立的成员模板，只要求两边的值类型相同（见下文）。

## default_searcher（[func.search.default]）

```cpp
template<class ForwardIterator1, class BinaryPredicate = equal_to<>>
class default_searcher;
```

¶1–¶2 构造函数保存两个模式迭代器和谓词，只可能抛出迭代器或谓词复制构造函数的异常。

¶3 `operator()` 返回一对迭代器 `i`、`j`：`i` 就是 `search(first, last, pat_first_, pat_last_, pred_)` 的结果；`i == last` 时 `j == last`，否则 `j == next(i, distance(pat_first_, pat_last_))`。

它只是把 `std::search` 包装成搜索器接口，所以只要求前向迭代器，构造函数和 `operator()` 都是 `constexpr`，并且是 freestanding 的。它的用处在于统一接口：写一个接受任意搜索器的泛型函数，调用方可以按需换用不同的算法。

## Boyer–Moore 搜索器（[func.search.bm]、[func.search.bmh]）

`boyer_moore_searcher` 和 `boyer_moore_horspool_searcher` 的规格逐段相同，只是名字不同：

```cpp
template<class RandomAccessIterator1,
         class Hash = hash<typename iterator_traits<RandomAccessIterator1>::value_type>,
         class BinaryPredicate = equal_to<>>
class boyer_moore_searcher;
```

### 为什么需要哈希

Boyer–Moore 系列算法依赖一张坏字符表：对模式串里出现过的每个不同的值，记录它最后出现的位置。失配时查这张表，决定可以跳过多远。值类型是 `char` 这样的单字节类型时，表可以是一个 256 项的数组；对一般的值类型，实现只能用哈希表，键是值本身，哈希用 `Hash`，判等用 `BinaryPredicate`。

哈希表要能工作，判等相等的两个键必须有相同的哈希值。无序容器对哈希和相等谓词有同样的要求（[[unord.hash]]）。

### 构造函数（¶1–¶4）

¶1 前条件：模式串的值类型可默认构造、可复制构造、可复制赋值，因为实现要拿它当表的键。

¶2 令 `V` 为值类型。对任意两个 `V` 值 `A`、`B`，若 `pred(A, B) == true`，则 `hf(A) == hf(B)` 必须为 true。这一段紧接着 ¶1 的前条件，违反它是 {{ub}}。

最常见的违反方式是只改了谓词，忘了改哈希：

```cpp run title="hash_pred_consistency.cpp" ub
#include <functional>
#include <algorithm>
#include <cctype>
#include <string>
#include <cstdio>

struct ci_eq {
  bool operator()(char a, char b) const {
    return std::tolower(static_cast<unsigned char>(a)) ==
           std::tolower(static_cast<unsigned char>(b));
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
  std::printf("%td\n", std::search(text.begin(), text.end(), good) - text.begin());  // 6

  std::boyer_moore_searcher bad(pat.begin(), pat.end(), std::hash<char>{}, ci_eq{}); // UB：违反 ¶2
  std::printf("%td\n", std::search(text.begin(), text.end(), bad) - text.begin());   // 本机输出 11
}
```

在 `bad` 里，`'w'` 和 `'W'` 判等相等，`std::hash<char>` 却给出不同的哈希值。查表时 `'W'` 被当成模式串里不存在的字符，算法跳过了真正的匹配位置，最后报告没找到。程序不会崩溃，只是静默地给出错误答案。

¶3 构造函数保存模式迭代器、哈希和谓词。¶4 它可能抛出迭代器、值类型、谓词、哈希的相关操作抛出的异常，内部数据结构分配失败时还可能抛 `bad_alloc`。也就是说，Boyer–Moore 搜索器的构造会分配内存，所以它们既不是 `constexpr` 的，也不是 freestanding 的。

### 函数调用运算符（¶5–¶8）

¶5 Mandates：`RandomAccessIterator1` 和 `RandomAccessIterator2` 的值类型相同。在 `std::string` 里找 `std::vector<char>` 形式的模式可以，在 `std::u8string` 里找 `std::string` 形式的模式就是非良构的。

¶7 返回值：`i` 是第一个使模式的每个元素都与 `*(i + n)` 满足 `pred` 的位置，`j == next(i, 模式长度)`。模式为空时返回 `make_pair(first, first)`，找不到时返回 `make_pair(last, last)`。

¶8 复杂度：至多 (last − first) × (模式长度) 次谓词调用。这只是最坏情况的上界，与朴素搜索相同。Boyer–Moore 平均次线性的优势在标准里没有可检验的表述。

!!! lawyer "末尾的匹配"
    ¶7.1 写的范围是左闭右开的 `[first, last - (pat_last_ - pat_first_))`，严格按字面读，不包含恰好匹配在末尾的那个位置 `last - 模式长度`。这显然不是本意。本机 libc++ 在 `"abclazy"` 里搜 `"lazy"`，两个搜索器都返回位置 3，即末尾的匹配。

## 一般要求（[func.search.general]）

¶2 每个搜索器特化都必须满足 *Cpp17CopyConstructible* 和 *Cpp17CopyAssignable*。名为 `ForwardIterator1`、`RandomAccessIterator2`、`BinaryPredicate` 等的模板形参，与算法库中同名的形参有相同的要求（[[algorithms.requirements]]）；名为 `Hash` 的形参必须满足 *Cpp17Hash*（[[hash.requirements]]）。

¶3 说 Boyer–Moore 搜索器实现 Boyer–Moore 算法，Horspool 搜索器实现 Boyer–Moore–Horspool 算法，一般而言前者占用更多内存、运行更快。标准无法精确定义实现某个算法是什么意思，这一段表达的是设计意图。

!!! impl "libc++ 的实现"
    `default_searcher` 直接调用 `std::search` 的内部实现。

    Boyer–Moore 的坏字符表有两个版本：值类型是单字节整型、`Hash` 恰好是 `hash<value_type>`、谓词恰好是 `equal_to<>` 时，用 `std::array<difference_type, 256>`；否则用 `unordered_map<Key, Value, Hash, BinaryPredicate>`。所以只要传了自定义谓词，哪怕只是 `std::equal_to<char>` 而不是 `equal_to<>`，就会走哈希表，¶2 的一致性要求也就真正起作用。

    预处理得到的表由 `shared_ptr` 持有，复制搜索器时共享同一份表，满足可复制的要求而不必重做预处理。

## 历史

!!! history
    搜索器最早出现在 Library Fundamentals TS（`std::experimental`），C++17 通过 [[P0220R1]] 并入标准。TS 里的 `operator()` 只返回匹配的起点，[[P0253R1]] 把它改成返回一对迭代器，同时给出终点。C++20 起 `default_searcher` 成为 `constexpr`。

## 思考题

!!! question "思考题"
    想在 `std::vector<std::string>` 里查找由若干 `std::string` 组成的子序列，用 `boyer_moore_searcher` 可行吗？需要提供什么？

<details markdown="1">
<summary>答案</summary>

可行。`std::string` 满足默认构造、复制构造和复制赋值（¶1），`std::hash<std::string>` 是启用的特化，并且与默认的 `equal_to<>` 一致（¶2），`vector` 的迭代器是随机访问的。这时每个字符是一整个字符串，坏字符表是一个以 `std::string` 为键的哈希表，每次比较比 `char` 贵得多，但模式较长、不同字符串较多时仍能跳过大量位置。如果改用大小写不敏感的比较，就必须同时提供大小写不敏感的哈希。
</details>
