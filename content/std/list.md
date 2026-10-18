---
title: list
summary: std::list 的契约——任意位置常数插入/擦除且从不使其他元素失效、任何插入抛异常都无效果；splice/merge 让迭代器"跟着元素换容器"；size() 常数导致跨 list 的区间 splice 变线性；分配器不等时 splice 是 UB；以及 sort 不是 constexpr 的草案细节
status: done
covers: *, list.syn
related: sequence.reqmts, container.requirements, forward.list, vector, deque, alg.sorting
tags: 标准库, 容器, list, splice, 迭代器失效
updated: 2026-10-18
---

`std::list` 是双向链表。它的价值不在遍历速度（缓存不友好），而在三条别的容器给不了的保证：**任意位置**常数时间插入/擦除、插入擦除**从不**使其他元素的迭代器和引用失效、能在 O(1) 内把元素**连同节点**搬到另一个 `list`（`splice`）。

## 概述（[list.overview]）

¶1：`list` 支持双向迭代器，在序列中任意位置常数时间插入和擦除，存储自动管理；不支持快速随机访问。

¶2：满足容器、可逆容器、分配器感知容器、序列容器（包括大部分可选操作）的要求，例外是不提供 `operator[]` 和 `at`——脚注说明这两者只由迭代器为随机访问的容器提供。

¶3：迭代器满足 constexpr 迭代器要求；`list` 在 C++26 中整体 constexpr 化（本机 libc++ 已实现，`__cpp_lib_constexpr_list` 为 `202502L`）。

¶4：分配器满足分配器完整性要求时，实例化 `list` 允许 `T` 不完整（同 [[vector]]）。

{{impl}} libc++ 的 `list<int>` 节点为 24 字节（前驱、后继指针 + `int` 及填充），`sizeof(std::list<int>) == 24`（哨兵节点的两个指针 + 元素计数）。哨兵节点内嵌在 `list` 对象里，所以 `end()` 指向容器对象内部——这也是为什么 `swap` 后 `end()` 不会"跟着走"。

## 构造与容量（[list.cons]、[list.capacity]）

构造函数与 [[sequence.reqmts]] 的通用条目一致（¶1–¶12）。`resize(sz)`（[list.capacity] ¶1–¶2）在缩小时被规定为"`advance` 到第 `sz` 个位置后 `erase` 到末尾"，`resize(sz, c)`（¶3–¶4）用 `insert`/`erase` 定义——"通过其他函数定义"意味着失效规则也随之继承。

## 修改器（[list.modifiers]）

¶1 复杂度：插入单个元素常数时间，**恰好一次** `T` 的构造；插入多个元素线性，拷贝/移动构造次数恰好等于插入个数。

¶2：**不影响迭代器和引用的有效性。若抛出异常，无效果。**这比 [[vector]]、[[deque]] 强得多：`list` 的**区间**插入也是强保证（实现先在一条临时链上构造好全部新节点，成功后再一次性接入）。

¶3–¶5：`erase`、`pop_front`、`pop_back`、`clear` 只使被擦除元素的迭代器和引用失效；不抛异常；擦除单个元素常数时间、一次析构，擦除区间线性。

## 链表专用操作（[list.ops]）

¶1：因为链表能快速在中间插入和擦除，所以专门提供了一些操作；`Predicate`/`BinaryPredicate` 实参须满足 [algorithms.requirements] 的要求；`i + n`、`i - n` 的语义是 `next(i, n)`、`prev(i, n)`；`merge` 和 `sort` 适用 [[alg.sorting]] 的定义与要求（即比较器必须是严格弱序）。

### `splice`：搬节点，不搬元素（¶2–¶14）

!!! std
    The behavior of splice operations is undefined if get_allocator() != x.get_allocator().

    若 get_allocator() != x.get_allocator()，splice 的行为未定义。

¶2 的这句是 `splice` 能 O(1) 的前提：节点是用 `x` 的分配器分配的，接入 `*this` 后将由 `*this` 的分配器释放，两者必须相等。脚注进一步说明：本节的要求只适用于分配器相等的 `list`。

三种 `splice`：

| 形式 | 前置条件 | 复杂度 |
|---|---|---|
| `splice(pos, x)` | `addressof(x) != this` | **常数**（¶3–¶6） |
| `splice(pos, x, i)` | `i` 是 `x` 的有效可解引用迭代器 | 常数；若 `pos == i` 或 `pos == ++i` 则不变（¶7–¶10） |
| `splice(pos, x, first, last)` | `[first, last)` 是 `x` 中的有效区间，`pos` 不在其中 | `addressof(x) == this` 时常数，**否则线性**（¶11–¶14） |

三者都 `Throws: Nothing`，并且规定：被搬走元素的指针和引用仍指向同一元素、只是现在是 `*this` 的成员；迭代器继续指向原元素，但**此后表现为 `*this` 的迭代器**。

```cpp title="splice.cpp" run ok
#include <list>
#include <cassert>

int main() {
  std::list<int> a{1, 2, 3}, b{10, 20};
  auto it = b.begin();                  // 指向 10
  int& r = *it;
  a.splice(a.end(), b);                 // O(1)：只改指针，不拷贝、不移动元素
  assert(b.empty());
  assert(&r == &*it && *it == 10);      // 迭代器与引用都还指向同一个元素……
  a.erase(it);                          // ……而且现在它是 a 的迭代器
  assert((a == std::list<int>{1, 2, 3, 20}));
}
```

为什么跨 `list` 的区间 `splice` 是线性的？因为 `size()` 必须常数（[[container.reqmts#54]]），`list` 要维护元素计数；从 `x` 搬走 `[first, last)` 时必须知道搬了多少个，只能数一遍。整个 `x` 的 `splice` 和单元素 `splice` 不需要数（个数分别是 `x.size()` 和 1）。C++03 时代 `size()` 只是"应当"常数，libstdc++ 曾选择 O(n) 的 `size()` 换取 O(1) 的区间 `splice`；C++11 把 `size()` 改为必须常数，这个取舍就被标准定死了。

### `remove`、`unique`（¶15–¶25）

- `remove(value)`/`remove_if(pred)`：擦除所有满足条件的元素，只使被擦除者失效；返回擦除个数（C++20 起返回 `size_type`，之前返回 `void`）；恰好 `size()` 次谓词调用；稳定。
- `unique()`/`unique(binary_pred)`：前置条件 `binary_pred` 是等价关系（¶21）；擦除每组**连续**等价元素中除第一个外的所有元素；恰好 `size() - 1` 次谓词调用。

### `merge`（¶26–¶30）

前置条件：两个 `list` 都按 `comp` 有序，且分配器相等（¶27）。`addressof(x) == this` 时无效果；否则合并，`x` 变空，**不拷贝任何元素**，迭代器随元素转移。至多 `size() + x.size() - 1` 次比较。稳定。比较之外的操作抛异常则无效果。

### `reverse` 与 `sort`（¶31–¶35）

- `reverse()`：`noexcept`，线性，不影响迭代器和引用的有效性。
- `sort()`/`sort(comp)`：稳定，约 N log N 次比较，**不影响迭代器和引用的有效性**（排序的是节点链接，而不是元素值）；抛异常时元素顺序未指明。

!!! lawyer "`list::sort` 不是 constexpr"
    当前草案中 `list` 的几乎所有成员都标为 `constexpr`，唯独 `void sort();` 与 `template<class Compare> void sort(Compare comp);` **没有**——而 `forward_list::sort` 是 `constexpr` 的（[[forward.list]]）。这看上去是 constexpr 化时的疏漏或有意保留；按现行条文，在常量求值中调用 `std::list::sort` 不被要求可行。

`list` 自带 `sort` 是因为 `std::sort` 需要随机访问迭代器；`list::sort` 通常是归并排序，只重排指针。

## 擦除（[list.erasure]）

`erase(c, value)` 等价于用 `erase_if` 加上相等比较的 lambda，`erase_if(c, pred)` 等价于 `c.remove_if(pred)`（¶1–¶2）——没有 erase-remove，因为链表可以直接摘除节点。

## 什么时候真的该用 `list`

- 需要**迭代器/引用永久稳定**，且有中间插入/擦除（`deque` 只保证两端）；
- 需要 O(1) 的 `splice` 在多个序列之间转移元素（LRU 缓存的经典实现：`unordered_map<Key, list<…>::iterator>` + `splice` 到表头）；
- 元素不可移动、不可拷贝（`list` 的插入不要求可移动赋值，`emplace` 只要求 *Cpp17EmplaceConstructible*）。

其余场景下，`vector` 的连续存储几乎总是更快。

## 思考题

!!! question "`a.splice(a.begin(), a, std::next(a.begin()), a.end())`（同一 `list` 内把除首元素外的所有元素挪到开头）合法吗？复杂度？"

<details markdown="1">
<summary>展开查看答案与解析</summary>

合法：前置条件只要求 `[first, last)` 是 `x`（此处即 `*this`）中的有效区间、`pos` 不在其中——`a.begin()` 不在 `[next(begin), end)` 中。¶14：`addressof(x) == this` 时**常数**时间，因为元素计数不变，无需数区间长度。效果是把首元素移到末尾（一次"旋转"）。
</details>

## 小结

- 插入从不使任何东西失效，擦除只使被擦除者失效；所有插入（含区间）都是强异常保证。
- `splice`/`merge` 不拷贝不移动元素，迭代器和引用随元素转移到目标 `list`；分配器不等是 UB。
- `size()` 常数 ⇒ 跨 `list` 的区间 `splice` 线性。
- `sort`/`reverse` 重排链接而不是值，不使迭代器失效；`list::sort` 在草案中未标 `constexpr`。
