---
title: unordered_map、unordered_set 及其 multi 版本
summary: 四个无序关联容器的具体条款——默认桶数实现定义、max_load_factor 初始为 1.0、operator[]/at/lookup/try_emplace/insert_or_assign、C++26 异构插入的"哈希值不变且不重复"UB 条件、推导指引中的 size_type、erase_if；libc++ 的节点与桶数组布局、素数/2 的幂桶数策略实测，以及 std::hash 的常见陷阱
status: done
covers: *
related: unord.req, associative, container.node, container.requirements, unord.hash, hash.requirements
tags: 标准库, 容器, unordered_map, 哈希表, rehash
updated: 2026-10-18
---

[unord] 定义 `<unordered_map>`（`unordered_map`、`unordered_multimap`）与 `<unordered_set>`（`unordered_set`、`unordered_multiset`）。它们的绝大部分语义——Hash/Pred 一致性、rehash 失效规则、复杂度、`operator==`——在 [[unord.req]]；本节只补充各类模板特有的成员。接口设计上，`unordered_map` 有意与 `map`（[[associative]]）保持一致，所以 `operator[]`、`try_emplace`、`insert_or_assign` 的规则几乎逐字相同，差异只在"排序"换成了"哈希"。

## 概述（[unord.general]）

¶1：两个头文件各定义两个类模板。¶2：推导指引使用 [associative.general] 中定义的 `iter-value-type`、`iter-key-type`、`iter-mapped-type`、`iter-to-alloc-type`、`range-key-type`、`range-mapped-type`、`range-to-alloc-type`（见 [[associative]]）。

## unordered_map（[unord.map]）

### 概述（[unord.map.overview]）

¶1：支持唯一键，并把 `mapped_type` 关联到键；支持**前向**迭代器。¶2：满足容器、分配器感知容器、无序关联容器的要求（注意：**不是**可逆容器），提供 `a_uniq` 操作；`value_type` 为 `pair<const Key, T>`。¶3：本节只描述表格未覆盖或有额外语义的操作。¶4：`iterator`、`const_iterator`、`local_iterator`、`const_local_iterator` 满足 constexpr 迭代器要求——当前草案中无序容器整体 `constexpr`，但本机 libc++ 尚未实现（没有 `__cpp_lib_constexpr_unordered_map` 一类的宏）。

¶5：推导指引中的 `size_type` 形参类型指的是**被推导出的类型**的 `size_type` 成员——即 `std::unordered_map m(first, last, 16)` 中的 `16` 是桶数。结合 [[unord.req]] ¶246"`Hash` 不得推导为整数类型"，`16` 不会被误推导为哈希器。

### 构造（[unord.map.cnstr]）

¶1：默认构造与 `(n, hf, eql, a)` 构造：构造使用至少 `n` 个桶的空容器；**默认构造时桶数由实现定义**；`max_load_factor()` 返回 **1.0**；常数复杂度。¶3–¶4：区间、`from_range`、初始化器列表构造：未提供 `n` 时桶数由实现定义，然后插入元素，`max_load_factor()` 返回 1.0；平均线性、最坏平方。

本机 libc++ 默认构造的桶数为 **0**——所以 [[unord.req]] 中 `bucket(k)` 的前置条件 `bucket_count() > 0` 在一个刚默认构造的容器上就不成立。

### 元素访问（[unord.map.elem]）

| 成员 | 规定 |
|---|---|
| `operator[](const key_type&)` / `(key_type&&)` | 等价于 `try_emplace(k).first->second`（¶1–¶2） |
| `template<class K> operator[](K&&)` {{c++26}} | *Constraints*：`Hash::is_transparent` 与 `Pred::is_transparent` 都有效（¶3–¶4） |
| `at(k)` | 返回唯一键等价于 `k` 的元素的 `second`；不存在抛 `out_of_range`（¶5–¶6） |
| `template<class K> at(const K&)` | 双透明；前置条件 `find(k)` 良构且行为良定义（¶7–¶10） |
| `lookup(k)` | `optional<mapped_type&>`：`contains(k)` 时为 `find(k)->second`，否则 `nullopt`；平均常数、最坏线性（¶11–¶14） |

与 `map` 一样，`operator[]` 是修改操作，要求 `mapped_type` 可从空实参构造，不在"视为 const"名单里。

### 修改器（[unord.map.modifiers]）

- `insert(P&&)`、`insert(hint, P&&)`：*Constraints* `is_constructible_v<value_type, P&&>`，等价于 `emplace`/`emplace_hint`（¶1–¶4）。
- `try_emplace(k, args…)`（¶5–¶12）：键已存在则**无效果**（实参不被移动）；否则以 `piecewise_construct` 构造插入。
- `insert_or_assign(k, obj)`（¶18–¶27）：*Mandates* `is_assignable_v<mapped_type&, M&&>`；存在则赋值，否则插入。
- **异构 `try_emplace` / `insert_or_assign`**（¶13–¶17、¶28–¶32）{{c++26}}：要求 `Hash` 与 `Pred` 都透明。UB 条件的形状与 `map` 不同：

!!! std
    let h be hash_function()(k). Constructs an object u of type value_type ... If hash_function()(u.first) != h || contains(u.first) is true, the behavior is undefined.

    令 h 为 hash_function()(k)；构造 u；若 hash_function()(u.first) != h 或 contains(u.first) 为真，行为未定义。

两个条件分别保证：由 `k` 构造出的真正的键与 `k` **哈希相同**（于是实现可以直接把节点放进用 `h` 算出的桶里，不必重算），并且它**确实不在**容器中（`k` 不等价于任何已有键，而 `u.first` 却等价于某个已有键——这说明 `Key` 与 `K` 的相等语义不协调）。

### 擦除（[unord.map.erasure]）

`erase_if(c, pred)` 是逐个擦除的循环，返回擦除个数。

## unordered_multimap（[unord.multimap]）

支持等价键；提供 `a_eq` 操作；没有 `operator[]`、`at`、`lookup`、`try_emplace`、`insert_or_assign`。构造（[unord.multimap.cnstr]）同 `unordered_map`，修改器（[unord.multimap.modifiers]）只有 `insert(P&&)` 模板，擦除同上。等价键组规则见 [[unord.req]] ¶6。

## unordered_set 与 unordered_multiset（[unord.set]、[unord.multiset]）

值类型即键类型，迭代器为常量迭代器。构造与擦除同上。[unord.set.modifiers] 有 {{c++26}} 的异构 `insert(K&&)` / `insert(hint, K&&)`：要求双透明；已含等价元素则无效果；否则令 `h = hash_function()(x)`，以 `std::forward<K>(x)` 构造 `u`，**若 `hash_function()(u) != h || contains(u)` 则 UB**。`unordered_multiset` 没有异构 `insert`。

## libc++ 实现笔记

{{impl}} 以下为本机 libc++（`<__hash_table>`）的源码阅读与实测：

- **布局**：`sizeof(std::unordered_map<int,int>) == 40`：桶数组指针与桶数、"before-begin"哨兵节点（只含 next）、元素计数、最大负载因子（`float`，与 Hash/Pred 的空类压缩在一起）。所有元素串成**一条**单链表，桶数组的每一项指向"本桶第一个节点的**前驱**"——这样在桶内插入/删除只需前驱，也让全局迭代就是沿单链表走一遍。
- **节点**：next 指针 + 缓存的哈希值（`size_t`）+ 值。`unordered_map<int,int>` 与 `unordered_set<int>` 的节点都是 24 字节；首次插入时还分配了一个 2 项（16 字节）的桶数组。缓存哈希值使 rehash 时不必重新调用 `Hash`——这与 [[unord.req]] 中"rehash 除哈希函数外抛异常则无效果"的规定相呼应。
- **桶数策略**：插入导致超载时，新桶数取 `max(2 * bc + !is_power_of_2(bc), ceil((size + 1) / max_load_factor()))`，非 2 的幂时再取下一个素数；桶号用 `hash % bc`，若 `bc` 是 2 的幂（且大于 2）则用 `hash & (bc - 1)`。实测逐个插入时桶数序列为 0, 2, 5, 11, 23, 47, 97, 197, 397, 797, 1597, 3203, 6421；而 `rehash(64)` 得到 64（保持 2 的幂，走掩码路径），`rehash(100)` 得到 101。

```cpp title="buckets.cpp" run ok
#include <unordered_map>
#include <cstdio>

int main() {
  std::unordered_map<int, int> m;
  std::size_t last = m.bucket_count();
  std::printf("buckets: %zu", last);
  for (int i = 0; i < 1000; ++i) {
    m[i];
    if (m.bucket_count() != last) std::printf(" %zu", last = m.bucket_count());
  }
  std::printf("\nload_factor=%.3f max_load_factor=%.1f\n", m.load_factor(), m.max_load_factor());
  std::size_t b = m.bucket(42);
  std::printf("key 42 in bucket %zu (size %zu)\n", b, m.bucket_size(b));
  for (auto it = m.begin(b); it != m.end(b); ++it) std::printf("  %d\n", it->first);  // 局部迭代器
}
```

本机输出桶数序列 `0 2 5 11 23 47 97 197 397 797 1597`，`load_factor=0.626`。注意 `std::hash<int>` 在 libc++ 中是恒等函数，所以键 42 正好落在 42 号桶——这也意味着"全是 1024 的倍数"之类的键在 2 的幂桶数下会全部撞进同一个桶。

## 常见误区

!!! pitfall "依赖迭代顺序"
    迭代顺序未指明，并且会随 rehash 改变（[[unord.req]] ¶9）。同一程序换一个标准库、换一个插入顺序、甚至只是多 `reserve` 一下，输出顺序都可能不同。测试中比较无序容器请用 `==`（按多重集合比较），不要比较序列化后的字符串。

!!! pitfall "以为 `reserve` 之后插入也不会让引用失效——而之前会"
    引用**从来**不会因插入失效，与 `reserve` 无关；`reserve` 保护的是**迭代器**。

!!! pitfall "攻击者可控的键 + 可预测的哈希"
    `std::hash` 对整数通常是恒等函数，对字符串是确定性的、不加盐的函数。若键来自不可信输入，攻击者可以构造大量同桶键，把平均 O(1) 拖成最坏 O(n)（标准明确允许最坏线性）。这种场景应使用带随机种子的哈希。

## 思考题

!!! question "`std::unordered_map<std::string, int> m; m.reserve(100); m.max_load_factor(0.5f);` 之后插入 100 个元素，迭代器会失效吗？"

<details markdown="1">
<summary>展开查看答案与解析</summary>

可能会。`reserve(100)` 按当时的 `max_load_factor()`（1.0）做 `rehash(ceil(100 / 1.0))`，桶数 B ≥ 100。之后把最大负载因子改为 0.5（[[unord.req]] 说 `max_load_factor(z)` "可能"以 z 为提示改变它），¶243 的不 rehash 条件变为 (N + n) ≤ 0.5·B，100 ≤ 0.5·100 不成立，插入过程中可能 rehash。正确顺序是先设置 `max_load_factor`、再 `reserve`。至于引用和指针，无论如何都不会失效。
</details>

## 小结

- `unordered_map` 与 `map` 的访问/插入接口同构：`operator[]` = `try_emplace`，`try_emplace` 不碰实参，`insert_or_assign` 返回是否插入。
- 默认桶数实现定义（libc++ 为 0），`max_load_factor()` 初始为 1.0。
- C++26 异构插入：由 `k` 构造的键必须哈希相同且尚不存在，否则 UB；本机 libc++ 未实现。
- libc++：单链表 + 指向前驱的桶数组、节点缓存哈希值、素数/2 的幂两种桶数策略。
