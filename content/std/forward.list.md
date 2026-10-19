---
title: forward_list
summary: std::forward_list 是单向链表，设计目标是相对手写的 C 单链表没有额外开销，因此没有 size()、back() 和 push_back()，所有修改都在某个位置之后进行。
status: done
covers: *, forward.list.syn
related: list, sequence.reqmts, container.requirements, container.requirements.general
tags: 标准库, 容器, forward_list, 单链表
updated: 2026-10-19
---

!!! tldr
    - `forward_list` 的目标是与手写 C 单链表相比没有空间和时间开销，所以它没有 `size()`、`back()`、`push_back()`，也不能反向遍历。
    - 单链表拿不到前驱，所以插入和擦除都写成 `insert_after`、`erase_after`；在表头操作时用 `before_begin()` 充当前驱。
    - `erase_after` 和 `splice_after` 的区间是全开区间 `(first, last)`。
    - 插入不使任何迭代器或引用失效，擦除只使被擦除元素失效；任何修改操作抛出异常都不影响容器。
    - 把整个链表接过来的 `splice_after(pos, x)` 是线性时间，因为要先走到 `x` 的末尾。

`std::forward_list`（C++11）是单向链表。它不是 [[list]] 的精简版，两者的设计目标不同：`list` 追求完整的序列容器接口，`forward_list` 追求零开销。

## 零开销意味着少了什么 [forward.list.overview]

¶1 `forward_list` 支持前向迭代器，在序列中任意位置插入和擦除都是常数时间，不支持快速随机访问。注 1 说明了整个类的设计目标：

!!! std
    It is intended that forward_list have zero space or time overhead relative to a hand-written C-style singly linked list. Features that would conflict with that goal have been omitted.

被省略的特性有：

- `size()`：维护元素计数要多存一个字段，每次插入擦除多做一次加减。第 2 段因此说 `forward_list` 满足容器要求，例外是不提供 `size()`，并且 `operator==` 是线性复杂度。一般容器的 `==` 在大小不同时是常数时间（[[container.reqmts#45]]），没有 `size()` 就做不到。
- `back()`、`push_back()`、`pop_back()`：常数时间访问末尾需要额外保存一个尾指针。
- 反向迭代：单链表做不到，所以它不是可逆容器。

!!! impl
    本机 libc++ 中 `sizeof(std::forward_list<int>)` 是 8，只有一个头指针。一个 `forward_list<int>` 节点是 16 字节：next 指针加上 `int` 和填充。

¶2 还说明，`forward_list` 满足分配器感知容器的要求，提供 `assign` 系列成员和一部分可选序列操作：`front`、`emplace_front`、`push_front`、`prepend_range`、`pop_front`。

¶4 迭代器满足 constexpr 迭代器的要求；本机 libc++ 已经支持在常量求值中使用 `forward_list`。¶5 只要分配器满足完整性要求，实例化 `forward_list` 时 `T` 可以是不完整类型。

## 在某个位置之后操作

```cpp title="erase-after.cpp" run ok
#include <cassert>
#include <forward_list>
#include <iterator>

int main() {
  std::forward_list<int> l{1, 2, 3, 4};
  // 删除第一个偶数：要拿到它前面那个位置
  for (auto prev = l.before_begin(), cur = l.begin();
       cur != l.end(); prev = cur++) {
    if (*cur % 2 == 0) { l.erase_after(prev); break; }
  }
  assert((l == std::forward_list<int>{1, 3, 4}));
  assert(std::distance(l.begin(), l.end()) == 3);  // 没有 size()
}
```

要删除单链表中的一个节点，必须修改它前一个节点的 next 指针，而单链表没有常数时间找到前驱的办法。所以 `forward_list` 的修改操作都以前驱为参数：`insert_after(pos, x)` 在 `pos` 之后插入，`erase_after(pos)` 删除 `pos` 之后的那个元素。

¶3 注 2 由此解释了区间的写法：`erase_after` 和 `splice_after` 使用全开区间 `(first, last)`，`first` 本身不在区间内，它是第一个被处理元素的前驱。

### before_begin [forward.list.iter]

在表头插入或删除时，第一个元素没有前驱。`before_begin()` 和 `cbefore_begin()` 提供了一个。

¶2 `before_begin()` 返回一个不可解引用的迭代器，自增后等于 `begin()`。¶3 `before_begin() == end()` 必须为假。

实现上，`before_begin()` 指向内嵌在容器对象里的头节点，这个节点只有 next 字段。它和 `end()` 一样不对应任何元素。

## 修改操作 [forward.list.modifiers]

¶1 是所有修改操作的总规则：

- 插入不影响迭代器和引用的有效性；擦除只使被擦除元素的迭代器和引用失效；
- 任何修改操作抛出异常，对容器都没有影响；
- 插入 n 个元素是线性时间，复制或移动构造恰好调用 n 次；擦除 n 个元素是线性时间，析构恰好调用 n 次。

各成员的要点：

| 成员 | 前置条件 | 返回值和说明 |
|---|---|---|
| `emplace_front`、`push_front`、`prepend_range` | 无 | `prepend_range` 保持元素原有顺序，不会反转（¶4） |
| `pop_front()` | 非空 | 如同 `erase_after(before_begin())`（¶5） |
| `insert_after(pos, x)` | `pos` 是 `before_begin()` 或 `[begin(), end())` 中可解引用的迭代器 | 指向新元素（¶6–¶11） |
| `insert_after(pos, n, x)` | 同上 | 指向最后一个新元素；n 为 0 时返回 `pos`（¶12–¶14） |
| `insert_after(pos, first, last)` | 同上；`first`、`last` 不是 `*this` 的迭代器 | 指向最后一个新元素，或 `pos`（¶15–¶17） |
| `insert_range_after(pos, rg)` | 同上；`rg` 与 `*this` 不重叠 | 同上（¶18–¶20） |
| `emplace_after(pos, args...)` | 同上 | 新元素用 `args...` 直接非列表初始化（¶22–¶24） |
| `erase_after(pos)` | `pos` 之后的迭代器可解引用 | 被擦除元素之后的元素，或 `end()`；不抛异常（¶25–¶28） |
| `erase_after(pos, last)` | `(pos, last)` 中的迭代器都可解引用 | `last`；不抛异常（¶29–¶32） |
| `resize(sz)`、`resize(sz, c)` | 无 | 用 `distance(begin(), end())` 描述，所以是线性的（¶33–¶36） |
| `clear()` | 无 | `noexcept`，不使尾后迭代器失效（¶37–¶38） |

`list::insert` 返回第一个新元素，`insert_after` 系列却返回最后一个新元素。这是因为接着往后插入时，需要的前驱正是最后一个新元素。

¶38 明确保证 `clear()` 不使尾后迭代器失效。对一般的序列容器，[[sequence.reqmts#54]] 只说 `clear()` 可能使尾后迭代器失效。

## 链表操作 [forward.list.ops]

¶1 与 [[list]] 的约定相同：名为 `Predicate`、`BinaryPredicate` 的实参要满足算法库的要求，`merge` 和 `sort` 适用 [[alg.sorting]] 的定义。`i + n` 的意思是 `next(i, n)`；前向迭代器不能后退，所以 `i - n` 另外定义为满足 `j + n == i` 的那个迭代器 `j`。

### splice_after

三种 `splice_after` 都把节点从 `x` 摘下接到 `pos` 之后，不复制也不移动元素。被转移元素的指针和引用继续指向原元素，迭代器也继续指向原元素，但此后表现为 `*this` 的迭代器。前置条件都包括两个链表的分配器相等。

| 形式 | 搬动的元素 | 复杂度 |
|---|---|---|
| `splice_after(pos, x)` | `x` 的全部元素，`x` 变空；要求 `addressof(x) != this` | O(distance(x.begin(), x.end()))（¶2–¶5） |
| `splice_after(pos, x, i)` | `i` 之后的那一个元素；`pos == i` 或 `pos == ++i` 时不变 | O(1)（¶6–¶9） |
| `splice_after(pos, x, first, last)` | 全开区间 `(first, last)`；`pos` 不在区间内 | O(distance(first, last))（¶10–¶12） |

整表 `splice_after` 不是常数时间。要把 `x` 接在 `pos` 后面，就得把 `x` 最后一个节点的 next 指向 `pos` 原来的后继，而找到最后一个节点只能从头走到尾。这是不保存尾指针的直接代价。

### remove、unique、merge、sort、reverse

- `remove(value)`、`remove_if(pred)`（¶13–¶17）：擦除所有满足条件的元素，返回擦除个数；谓词恰好调用 `distance(begin(), end())` 次；只使被擦除元素失效；稳定。
- `unique()`、`unique(pred)`（¶18–¶23）：前置条件是 `pred` 为等价关系；每组连续等价的元素只保留第一个。
- `merge(x)`（¶24–¶28）：两个链表都已按 `comp` 排序，分配器相等。合并后 `x` 为空，不复制任何元素，迭代器随元素转移；稳定；比较以外的操作抛出异常时没有效果。
- `sort()`（¶29–¶31）：稳定，约 N log N 次比较，不影响迭代器和引用的有效性，因为它重排的是节点链接，不是元素值。
- `reverse()`（¶32–¶33）：`noexcept`，线性时间，不影响迭代器和引用的有效性。

## erase 与 erase_if [forward.list.erasure]

¶1 非成员 `erase(c, value)` 委托给 `erase_if`，用一个与 `value` 比较相等的 lambda 作谓词；¶2 `erase_if(c, pred)` 等价于 `c.remove_if(pred)`。链表可以直接摘除节点，不需要先 `remove` 再 `erase`。

## 思考题

!!! question "思考题"
    为什么 `forward_list::splice_after(pos, x)` 是线性的，而 `list::splice(pos, x)` 是常数时间？

<details markdown="1">
<summary>答案</summary>

把整个 `x` 接到 `pos` 之后，需要修改 `x` 最后一个节点的 next 指针。`list` 是双向链表，`x` 的尾节点就是 `x.end()` 的前驱，常数时间可得。`forward_list` 只保存头指针，找尾节点只能从头走到尾，所以是 O(distance(x.begin(), x.end()))（¶5）。

区间版本的情况正好相反。`list` 跨容器的区间 `splice` 是线性的，因为要数出区间里有多少个元素来更新 `size()`；`forward_list` 没有 `size()`，但为了找到区间里最后一个节点，同样要走一遍。
</details>
