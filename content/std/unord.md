---
title: unordered_map、unordered_set 及其 multi 版本
summary: 四个无序关联容器各自特有的成员：默认桶数由实现定义、最大负载因子初始为 1.0，operator[]、try_emplace、insert_or_assign 与 map 同构，C++26 异构插入要求哈希值不变且键尚不存在，以及 libc++ 哈希表的布局和桶数策略。
status: done
covers: *
related: unord.req, associative, container.node, container.requirements, unord.hash, hash.requirements
tags: 标准库, 容器, unordered_map, 哈希表, rehash
updated: 2026-10-19
---

!!! tldr
    - `unordered_map` 的 `operator[]`、`at`、`try_emplace`、`insert_or_assign` 与 `map` 的规则相同，只是按哈希而不是按顺序组织元素。
    - 默认构造的桶数由实现定义（libc++ 是 0），`max_load_factor()` 初始为 1.0。
    - 插入可能触发 rehash，使所有迭代器失效，但元素的引用和指针永远不会因插入失效。
    - C++26 异构插入要求由异构键构造出的真实键哈希值相同、而且尚不在容器中，否则是未定义行为。
    - 迭代顺序未指定，rehash 后还会改变；`std::hash` 不加随机种子，键来自不可信输入时可能被构造成大量冲突。

[unord] 定义 `<unordered_map>` 里的 `unordered_map`、`unordered_multimap` 和 `<unordered_set>` 里的 `unordered_set`、`unordered_multiset`。哈希表的通用规则，包括哈希函数与相等谓词必须一致、rehash 让哪些东西失效、复杂度、`operator==` 的含义，都在无序关联容器要求 [[unord.req]] 里。[unord] 只补充每个类模板特有的部分。

`unordered_map` 的接口有意与 `map`（[[associative]]）保持一致，`operator[]`、`try_emplace`、`insert_or_assign` 的规定几乎逐字相同。

## 桶与负载因子

```cpp title="buckets.cpp" run ok
#include <unordered_map>
#include <cstdio>

int main() {
  std::unordered_map<int, int> m;
  std::size_t last = m.bucket_count();
  std::printf("buckets: %zu", last);
  for (int i = 0; i < 1000; ++i) {
    m[i];
    if (m.bucket_count() != last)
      std::printf(" %zu", last = m.bucket_count());
  }
  std::printf("\nload_factor=%.3f max_load_factor=%.1f\n",
              m.load_factor(), m.max_load_factor());
  std::size_t b = m.bucket(42);
  std::printf("key 42 in bucket %zu (size %zu)\n", b, m.bucket_size(b));
  for (auto it = m.begin(b); it != m.end(b); ++it)   // 局部迭代器：只遍历一个桶
    std::printf("  %d\n", it->first);
}
```

哈希表把元素分进若干个**桶**（bucket）：哈希值相同的键一定在同一个桶里（[[unord.req.general#9]]）。**负载因子**（load factor）是元素数除以桶数，也就是每个桶平均有几个元素。负载因子要超过**最大负载因子**时，容器增加桶数并把元素重新分桶，这叫 **rehash**。

本机 libc++ 上，桶数依次是 `0 2 5 11 23 47 97 197 397 797 1597`，最后 `load_factor=0.626`。libc++ 的 `std::hash<int>` 是恒等函数，所以键 42 正好落在 42 号桶。

[unord.map.cnstr] ¶1–¶2 默认构造和 `(n, hf, eql, a)` 构造得到一个空容器，至少有 `n` 个桶；默认构造时桶数由实现定义；`max_load_factor()` 返回 1.0；常数时间。¶3–¶4 区间、`from_range` 和初始化器列表构造，没有给出 `n` 时桶数同样由实现定义，然后插入元素；平均线性时间，最坏平方时间。

本机 libc++ 默认构造的桶数是 0。所以对一个刚默认构造的容器，`bucket(k)` 的前置条件 `bucket_count() > 0` 不成立（[[unord.req.general#199]]）。

rehash 让所有迭代器失效，并改变元素之间的顺序和所在的桶，但不让元素的引用和指针失效（[[unord.req.general#9]]）：节点只是被重新链接，元素本身不移动。

## 概述（[unord.general]、[unord.map.overview]）

[unord.general] ¶2 推导指引使用 [associative.general] 定义的那组仅阐述别名，如 `iter-key-type`、`range-key-type`，见 [[associative]]。

[unord.map.overview] ¶1 `unordered_map` 支持唯一键，把映射值关联到键，支持前向迭代器。

¶2 它满足容器、分配器感知容器和无序关联容器的要求，提供唯一键的那组操作；`value_type` 是 `pair<const Key, T>`。它不是可逆容器，没有 `rbegin`。

¶4 `iterator`、`const_iterator`、`local_iterator`、`const_local_iterator` 满足 constexpr 迭代器的要求。当前草案中无序容器整体可以在常量求值中使用，本机 libc++ 还没有实现。

¶5 推导指引里 `size_type` 类型的形参，指的是推导出的容器类型的 `size_type`。所以 `std::unordered_map m(first, last, 16)` 中的 `16` 是桶数。[[unord.req.general#246]] 还规定推导指引不得把整数类型推导为 `Hash`，所以 `16` 不会被当成哈希函数。

## 元素访问（[unord.map.elem]）

| 成员 | 规定 | 出处 |
|---|---|---|
| `operator[](const key_type&)`、`(key_type&&)` | 等价于 `try_emplace(k).first->second` | ¶1–¶2 |
| `template<class K> operator[](K&&)` {{c++26}} | `Hash::is_transparent` 和 `Pred::is_transparent` 都存在时才参与重载决议 | ¶3–¶4 |
| `at(k)` | 返回键等价于 `k` 的元素的映射值；不存在时抛 `out_of_range` | ¶5–¶6 |
| `template<class K> at(const K&)` | 同样要求两者都透明；前置条件是 `find(k)` 良构且行为有定义 | ¶7–¶10 |
| `lookup(k)` | 返回 `optional<mapped_type&>`，键不存在时为 `nullopt`；平均常数时间，最坏线性 | ¶11–¶14 |

与 `map` 一样，`operator[]` 是修改操作，要求映射类型能从空实参列表构造，不能用于只读访问。

无序容器的异构查找要求哈希函数和相等谓词都透明，而有序容器只要求比较器透明。原因是查找要先用 `Hash` 算出桶，再用 `Pred` 在桶里比较，两步都要能直接接受异构键。

## 修改器（[unord.map.modifiers]）

- ¶1–¶4 `insert(P&&)`、`insert(hint, P&&)`：在 `is_constructible_v<value_type, P&&>` 为真时参与重载决议，等价于 `emplace`、`emplace_hint`。
- ¶5–¶12 `try_emplace(k, args...)`：键已存在时没有效果，实参不会被移走；否则以 `piecewise_construct` 构造并插入。
- ¶18–¶27 `insert_or_assign(k, obj)`：要求 `is_assignable_v<mapped_type&, M&&>`；键存在时赋值，否则插入。

这三者的动机和用法与 `map` 完全相同，例子见 [[associative]]。

### C++26 异构插入（¶13–¶17、¶28–¶33）{{c++26}}

异构的 `try_emplace` 和 `insert_or_assign` 要求 `Hash` 和 `Pred` 都透明。¶15 的未定义行为条件和 `map` 的形状不同：

!!! std
    let h be hash_function()(k). Constructs an object u of type value_type ... If hash_function()(u.first) != h || contains(u.first) is true, the behavior is undefined.

两个条件各有用处。第一个要求由 `k` 构造出的真实键与 `k` 哈希值相同，于是实现可以直接把新节点放进按 `h` 算出的桶里，不必再算一次哈希。第二个要求这个真实键确实不在容器中：`k` 不等价于任何已有键，`u.first` 却等价于某个已有键，说明 `Key` 和 `K` 的相等语义不一致。

本机 libc++ 还没有实现异构插入。

## erase_if（[unord.map.erasure]）

¶1 `erase_if(c, pred)` 是逐个检查、逐个擦除的循环，返回擦除的元素个数。

## multimap 与 set 版本

**unordered_multimap**（[unord.multimap]）支持等价键，没有 `operator[]`、`at`、`lookup`、`try_emplace`、`insert_or_assign`。修改器只有 `insert(P&&)` 模板，构造和 `erase_if` 与 `unordered_map` 相同。等价键的元素在迭代顺序中彼此相邻（[[unord.req.general#6]]）。

**unordered_set**（[unord.set]）和 **unordered_multiset** 的值类型就是键类型，迭代器是常量迭代器。[unord.set.modifiers] ¶1–¶5 给 `unordered_set` 加了 C++26 的异构 `insert(K&&)` 和 `insert(hint, K&&)`：要求两者都透明；已有等价元素时没有效果；否则令 `h = hash_function()(x)`，用 `std::forward<K>(x)` 构造 `u`，如果 `hash_function()(u) != h || contains(u)` 为真，行为未定义。`unordered_multiset` 没有异构 `insert`。

## libc++ 实现

{{impl}} 以下是本机 libc++（`<__hash_table>`）的源码阅读和实测结果。

- **布局**：`sizeof(std::unordered_map<int, int>)` 是 40 字节，包括桶数组指针和桶数、一个只含 next 指针的哨兵节点、元素个数、`float` 类型的最大负载因子（`Hash`、`Pred` 是空类时不占空间）。
- **一条链表**：所有元素串在同一条单链表上，桶数组的每一项指向本桶第一个节点的前驱。这样在桶内插入或删除只需要知道前驱，遍历整个容器就是沿着链表走一遍。
- **节点**：next 指针、缓存的哈希值（`size_t`）和元素。`unordered_map<int, int>` 的节点是 24 字节；第一次插入时还分配了一个 2 项、16 字节的桶数组（本机用打印请求大小的分配器验证）。缓存哈希值让 rehash 时不必再调用 `Hash`。
- **桶数策略**：需要扩容时，新桶数取 `max(2 * bc + !is_power_of_2(bc), ceil((size + 1) / max_load_factor()))`，结果不是 2 的幂时再取下一个素数。桶号一般用 `hash % bc`，桶数是大于 2 的 2 的幂时改用 `hash & (bc - 1)`。所以逐个插入得到的是素数序列，而 `rehash(64)` 得到 64，`rehash(100)` 得到 101。

`std::hash<int>` 是恒等函数，配上 2 的幂桶数时，比如全是 1024 的倍数的键会全部落进同一个桶。

## 常见误解

!!! pitfall "依赖迭代顺序"
    迭代顺序未指定，rehash 还会改变它（[[unord.req.general#9]]）。换一个标准库、换一种插入顺序，甚至多调用一次 `reserve`，输出顺序都可能不同。测试中比较两个无序容器应当用 `==`，它把容器当作多重集合比较。

!!! pitfall "以为 reserve 保护的是引用"
    插入从来不会让引用和指针失效，与 `reserve` 无关。`reserve` 保护的是迭代器：只要插入后的元素数不超过最大负载因子乘以桶数，就不会 rehash，迭代器保持有效（[[unord.req.general#243]]）。

!!! pitfall "攻击者可以控制键，而哈希是可预测的"
    `std::hash` 对整数通常是恒等函数，对字符串是确定的、不加随机种子的函数。如果键来自不可信的输入，攻击者可以构造大量落进同一个桶的键，把平均常数时间的操作拖到线性时间，标准允许这种最坏情况。这种场合应当使用带随机种子的哈希函数。

## 思考题

!!! question "思考题"
    `std::unordered_map<std::string, int> m; m.reserve(100); m.max_load_factor(0.5f);` 之后插入 100 个元素，迭代器会失效吗？

<details markdown="1">
<summary>答案</summary>

可能会。`reserve(100)` 按当时的最大负载因子 1.0 做 `rehash(ceil(100 / 1.0))`，桶数 B 至少是 100（本机是 101）。之后最大负载因子改成了 0.5，[[unord.req.general#243]] 不 rehash 的条件变成 (N + n) ≤ 0.5 × B，100 ≤ 0.5 × 101 不成立，插入过程中可能 rehash。

正确的顺序是先设置 `max_load_factor`，再 `reserve`。至于引用和指针，无论哪种顺序都不会失效。
</details>

## 小结

| 方面 | 规则 |
|---|---|
| 访问与插入 | 与 `map` 相同：`operator[]` 即 `try_emplace`，`try_emplace` 不动实参，`insert_or_assign` 返回是否插入 |
| 初始状态 | 默认桶数由实现定义（libc++ 是 0）；`max_load_factor()` 为 1.0 |
| 失效 | rehash 让迭代器失效；引用和指针不受插入影响 |
| 异构插入 | 由 `k` 构造的键必须哈希相同且尚不存在，否则 UB；需要 `Hash` 和 `Pred` 都透明 |
| libc++ | 单链表加指向前驱的桶数组；节点缓存哈希值；素数和 2 的幂两种桶数 |
