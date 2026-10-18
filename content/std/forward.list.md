---
title: forward_list
summary: std::forward_list——"与手写 C 单链表零开销"的设计目标如何删掉 size()、back() 与 push_back；before_begin 与 *_after 系列为何使用全开区间；插入擦除的失效与异常保证；splice_after/merge/sort 的契约
status: done
covers: *, forward.list.syn
related: list, sequence.reqmts, container.requirements, container.requirements.general
tags: 标准库, 容器, forward_list, 单链表
updated: 2026-10-18
---

`std::forward_list`（C++11）是单向链表。它和 [[list]] 的关系不是"轻量版"，而是**设计目标不同**：`list` 追求完整的序列容器接口，`forward_list` 追求的是零开销。

## 概述（[forward.list.overview]）

¶1：支持前向迭代器，在序列中任意位置常数时间插入和擦除；不支持快速随机访问。注 1 是理解整个类的钥匙：

!!! std
    It is intended that forward_list have zero space or time overhead relative to a hand-written C-style singly linked list. Features that would conflict with that goal have been omitted.

    forward_list 意在相对于手写的 C 风格单链表没有任何空间或时间开销；与此目标冲突的特性都被省略了。

由此被省略的：

- **`size()`**——维护计数要多存一个字段、每次插入擦除多一次加减。¶2 明说 `forward_list` 满足容器要求，**除了**不提供 `size()`，且 `operator==` 为线性复杂度（容器要求本来是"大小不同则常数"，没有 `size()` 就做不到）。
- **`back()`/`push_back()`/`pop_back()`**——要常数时间访问末尾就得多存一个尾指针。
- 反向迭代——单链表做不到，所以它不是可逆容器。

{{impl}} 本机 libc++：`sizeof(std::forward_list<int>) == 8`，就一个头指针；`forward_list<int>` 节点 16 字节（next 指针 + `int` 及填充）。

¶2 还说明：满足分配器感知容器要求，提供 `assign` 系列和部分可选序列操作（`front`、`emplace_front`、`push_front`、`prepend_range`、`pop_front`）。

¶3（注 2）：修改链表需要访问"目标元素之前"的元素，而单链表没有常数时间的办法拿到前驱。所以 `erase_after` 与 `splice_after` 使用**全开区间** `(first, last)` 而不是半开区间。

¶4：迭代器满足 constexpr 迭代器要求（整个类在 C++26 中 constexpr 化，本机 libc++ 已实现）。¶5：分配器满足完整性要求时允许 `T` 不完整。

## `before_begin`（[forward.list.iter]）

`before_begin()`/`cbefore_begin()` 返回一个**不可解引用**的迭代器，自增后等于 `begin()`（¶2）；¶3 要求 `before_begin() == end()` 为假。它是所有 `*_after` 操作在表头插入/删除时的"前驱"：

```cpp title="erase-after.cpp" run ok
#include <forward_list>
#include <cassert>
#include <iterator>

int main() {
  std::forward_list<int> l{1, 2, 3, 4};
  // 删除第一个偶数：必须拿到"它前面那个"位置
  for (auto prev = l.before_begin(), cur = l.begin(); cur != l.end(); prev = cur++) {
    if (*cur % 2 == 0) { l.erase_after(prev); break; }
  }
  assert((l == std::forward_list<int>{1, 3, 4}));
  assert(std::distance(l.begin(), l.end()) == 3);   // 没有 size()
}
```

实现上，`before_begin()` 指向的是内嵌在容器对象里的"头节点"（只有 next 字段），所以它和 `end()`（通常是空指针）一样，都不对应任何元素。

## 元素访问（[forward.list.access]）

只有 `front()`，返回 `*begin()`（¶1）。它的"非空"前置条件来自 [[sequence.reqmts]] ¶72 的加固前置条件。

## 修改器（[forward.list.modifiers]）

¶1 是本子条款的总纲：

- 插入**不影响**迭代器和引用的有效性；擦除只使被擦除元素的迭代器和引用失效；
- 任何修改器抛出异常，**对容器无影响**；
- 插入 n 个元素线性于 n，拷贝/移动构造次数**恰好**为 n；擦除 n 个元素线性于 n，析构次数恰好为 n。

各成员：

| 成员 | 前置条件 | 返回 |
|---|---|---|
| `emplace_front`/`push_front`/`prepend_range` | — | `prepend_range` 不反转顺序（¶4 注） |
| `pop_front()` | — | 等价于 `erase_after(before_begin())`（¶5） |
| `insert_after(pos, x)` | `pos` 是 `before_begin()` 或 `[begin(), end())` 中可解引用的迭代器 | 指向新元素（¶6–¶11） |
| `insert_after(pos, n, x)` | 同上 | 指向**最后一个**新元素，n 为 0 时返回 `pos`（¶14） |
| `insert_after(pos, first, last)` | 同上；`first`、`last` 不是 `*this` 的迭代器 | 指向最后一个新元素或 `pos`（¶15–¶17） |
| `insert_range_after(pos, rg)` | 同上；`rg` 与 `*this` 不重叠 | 同上（¶18–¶20） |
| `emplace_after(pos, args…)` | 同上 | 新对象以 `args…` **直接非列表初始化**（¶23） |
| `erase_after(pos)` | `pos` 之后的迭代器可解引用 | 被擦除元素之后元素的迭代器或 `end()`；不抛（¶25–¶28） |
| `erase_after(pos, last)` | `(pos, last)` 中的迭代器都可解引用 | `last`；不抛（¶29–¶32） |
| `resize(sz)` / `resize(sz, c)` | — | 用 `distance(begin(), end())` 定义（¶33–¶36），因此是线性的 |
| `clear() noexcept` | — | ¶38：**不使尾后迭代器失效** |

与 `list` 的"返回第一个新元素"不同，`insert_after` 系列返回**最后一个**新元素——因为后续接着插入时需要的正是"最后一个"作为新的前驱。

¶38 是序列容器中唯一明确保证 `clear()` 不使 end 失效的条款；[[sequence.reqmts]] ¶54 对其他序列容器只说"可能失效"。

## 链表操作（[forward.list.ops]）

¶1：与 [[list]] 相同的约定（谓词要求、`i + n` 即 `next(i, n)`、`merge`/`sort` 适用 [[alg.sorting]]）；另外定义了 `i - n` 为满足 `j + n == i` 的迭代器 `j`。

- `splice_after(pos, x)`（¶2–¶5）：前置条件包括 `get_allocator() == x.get_allocator()` 与 `addressof(x) != this`；`x` 变空；不抛；复杂度 **O(distance(x.begin(), x.end()))**——不是常数！因为要找到 `x` 的最后一个节点才能把它接到 `pos` 后面的原后继上。这是单链表"无尾指针"设计的直接代价。
- `splice_after(pos, x, i)`（¶6–¶9）：搬 `i` 之后的那个元素，O(1)；`pos == i` 或 `pos == ++i` 时不变。
- `splice_after(pos, x, first, last)`（¶10–¶12）：搬全开区间 `(first, last)`，O(distance(first, last))。注意分配器相等在这里写成了前置条件（`list` 中则是整节的"行为未定义"）。
- `remove`/`remove_if`（¶13–¶17）、`unique`（¶18–¶23）：与 `list` 相同，只使被擦除者失效，稳定。
- `merge`（¶24–¶28）：两者有序且分配器相等；不拷贝元素；稳定；比较之外的异常无效果。
- `sort`（¶29–¶31）：稳定，约 N log N 次比较，不影响迭代器和引用的有效性；**`constexpr`**（对比 [[list]] 中 `list::sort` 未标 `constexpr`）。
- `reverse() noexcept`（¶32–¶33）：线性，不影响有效性。

## 擦除（[forward.list.erasure]）

`erase(c, value)` 用相等比较的 lambda 委托给 `erase_if`；`erase_if(c, pred)` 等价于 `c.remove_if(pred)`。

## 思考题

!!! question "为什么 `forward_list::splice_after(pos, x)` 是线性的，而 `list::splice(pos, x)` 是常数？"

<details markdown="1">
<summary>展开查看答案与解析</summary>

把整个 `x` 接到 `pos` 之后，需要把 `x` 的**最后一个节点**的 next 改成 `pos` 原来的后继。`list` 有双向链接和哨兵节点，`x` 的尾节点就是 `x.end()` 的前驱，O(1) 可得；`forward_list` 只有头指针（零开销设计不存尾指针），找尾节点只能从头走到尾，所以是 O(distance(x.begin(), x.end()))（¶5）。反过来，`list` 的跨容器**区间** `splice` 是线性的（要更新 `size()`），而 `forward_list` 没有 `size()`，但为了找区间尾部同样要走一遍——两者殊途同归。
</details>

## 小结

- 零开销设计：没有 `size()`、`back()`、`push_back()`、反向迭代；`sizeof` 只有一个指针。
- 所有修改都在"某个位置之后"进行；`before_begin()` 充当表头的前驱；擦除区间是全开区间 `(first, last)`。
- 插入不使任何东西失效，擦除只使被擦除者失效，任何修改器抛异常都无效果；`clear()` 不使 end 失效。
- 整表 `splice_after` 是线性的；`sort` 稳定且不使迭代器失效。
