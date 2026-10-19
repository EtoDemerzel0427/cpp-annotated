---
title: list
summary: std::list 是双向链表：任意位置常数时间插入擦除，插入擦除从不使其他元素失效，splice 和 merge 只改链接、让迭代器跟着元素换到另一个链表。
status: done
covers: *, list.syn
related: sequence.reqmts, container.requirements, forward.list, vector, deque, alg.sorting
tags: 标准库, 容器, list, splice, 迭代器失效
updated: 2026-10-19
---

!!! tldr
    - 在任意位置插入或擦除单个元素都是常数时间；插入不使任何迭代器或引用失效，擦除只使被擦除元素失效。
    - `list` 的任何插入，包括区间插入，抛出异常时都没有效果。
    - `splice` 和 `merge` 把节点从一个 `list` 接到另一个，不复制也不移动元素，迭代器和引用跟着元素走；两个 `list` 的分配器不相等时，`splice` 是未定义行为。
    - `size()` 必须是常数时间，所以从另一个 `list` 搬一段区间的 `splice` 是线性的。
    - `sort` 和 `reverse` 重排的是链接，不使迭代器失效。

`std::list` 是双向链表。它遍历起来不快，节点分散在堆上，对缓存不友好。它的价值在于其他容器给不了的三项保证：任意位置常数时间插入擦除；插入擦除从不使其他元素的迭代器和引用失效；能在常数时间内把元素连同节点搬到另一个 `list`。

## 概述 [list.overview]

¶1 `list` 支持双向迭代器，在序列中任意位置插入和擦除都是常数时间，不支持快速随机访问。

¶2 它满足容器、可逆容器、分配器感知容器和序列容器的要求，包括大部分可选操作，例外是不提供 `operator[]` 和 `at`。脚注说明，这两个成员只由迭代器是随机访问迭代器的容器提供。

¶3 迭代器满足 constexpr 迭代器的要求。本机 libc++ 已经支持在常量求值中使用 `list`，`__cpp_lib_constexpr_list` 是 `202502L`。

¶4 只要分配器满足完整性要求，实例化 `list` 时 `T` 可以是不完整类型。

!!! impl
    libc++ 的 `list<int>` 节点是 24 字节：前驱指针、后继指针，加上 `int` 和填充。本机 `sizeof(std::list<int>)` 是 24，即一个哨兵节点的两个指针加上元素计数。哨兵节点就在 `list` 对象内部，所以 `end()` 指向容器对象本身，两个 `list` 交换之后 `end()` 不会跟着换过去。

## 插入与擦除 [list.modifiers]

¶1 插入单个元素是常数时间，恰好调用一次 `T` 的构造函数；插入多个元素是线性时间，复制或移动构造的调用次数恰好等于插入的元素个数。

¶2 插入不影响迭代器和引用的有效性；抛出异常时没有效果。这比 [[vector]] 和 [[deque]] 强得多：`list` 的区间插入也是强异常保证。实现可以先在一条临时链上构造好所有新节点，全部成功后再一次接进来。

¶3–¶5 `erase`、`pop_front`、`pop_back`、`clear` 只使被擦除元素的迭代器和引用失效，不抛异常。擦除单个元素是常数时间，调用一次析构函数；擦除区间线性于区间长度。

[list.capacity] 中的 `resize` 用 `insert` 和 `erase` 来描述（¶1–¶4），所以它的失效规则与这两个操作相同。

## splice：搬节点，不搬元素 [list.ops]

```cpp title="splice.cpp" run ok
#include <cassert>
#include <list>

int main() {
  std::list<int> a{1, 2, 3}, b{10, 20};
  auto it = b.begin();             // 指向 10
  int& r = *it;
  a.splice(a.end(), b);            // 常数时间：只改指针
  assert(b.empty());
  assert(&r == &*it && *it == 10); // 迭代器和引用仍指向同一元素
  a.erase(it);                     // it 现在是 a 的迭代器
  assert((a == std::list<int>{1, 2, 3, 20}));
}
```

¶2 `list` 提供三种 `splice`，它们把元素从一个 `list` 破坏性地移到另一个。同一段还规定：

!!! std
    The behavior of splice operations is undefined if get_allocator() != x.get_allocator().

`splice` 能做到常数时间，前提是节点可以原样换主人。节点是用 `x` 的分配器分配的，接进 `*this` 之后将来由 `*this` 的分配器释放，两个分配器必须相等。

| 形式 | 前置条件 | 复杂度 |
|---|---|---|
| `splice(pos, x)` | `addressof(x) != this` | 常数（¶3–¶6） |
| `splice(pos, x, i)` | `i` 是 `x` 中可解引用的迭代器；`pos == i` 或 `pos == ++i` 时不变 | 常数（¶7–¶10） |
| `splice(pos, x, first, last)` | `[first, last)` 是 `x` 中的有效区间，`pos` 不在其中 | `addressof(x) == this` 时常数，否则线性（¶11–¶14） |

三种形式都不抛异常。被搬走元素的指针和引用继续指向原元素，只是它现在是 `*this` 的成员；迭代器也继续指向原元素，但此后表现为 `*this` 的迭代器。

为什么跨 `list` 的区间 `splice` 是线性的？因为 `size()` 必须是常数时间（[[container.reqmts#54]]），`list` 要维护元素计数。从 `x` 搬走 `[first, last)` 时，必须知道搬走了多少个，只能数一遍。整个 `x` 的 `splice` 和单元素的 `splice` 不用数，个数分别是 `x.size()` 和 1；同一个 `list` 内部的区间 `splice` 不改变计数，也不用数。

!!! history
    C++03 只说 `size()` 应当是常数时间，libstdc++ 当时选择让 `size()` 线性，以换取常数时间的区间 `splice`。C++11 把 `size()` 改为必须是常数时间，这个取舍从此由标准确定。

## 其他链表操作

¶1 因为链表能在中间快速插入擦除，标准为它专门提供了一组操作。名为 `Predicate`、`BinaryPredicate` 的实参要满足算法库的要求；`i + n`、`i - n` 的含义分别是 `next(i, n)`、`prev(i, n)`；`merge` 和 `sort` 适用 [[alg.sorting]] 的定义，比较器必须是严格弱序。

- `remove(value)`、`remove_if(pred)`（¶15–¶19）：擦除所有满足条件的元素，只使被擦除元素失效；返回擦除个数（C++20 之前返回 `void`）；谓词恰好调用 `size()` 次；稳定。
- `unique()`、`unique(pred)`（¶20–¶25）：前置条件是 `pred` 为等价关系；每组连续等价的元素只保留第一个；谓词恰好调用 `size() - 1` 次。
- `merge(x)`（¶26–¶30）：两个 `list` 都已按 `comp` 排序，且分配器相等。`addressof(x) == this` 时没有效果；否则合并后 `x` 为空，不复制任何元素，迭代器随元素转移；最多比较 `size() + x.size() - 1` 次；稳定；比较以外的操作抛出异常时没有效果。
- `reverse()`（¶31–¶32）：`noexcept`，线性时间，不影响迭代器和引用的有效性。
- `sort()`（¶33–¶35）：稳定，约 N log N 次比较，不影响迭代器和引用的有效性，因为排的是节点链接，不是元素值；抛出异常时元素顺序未指明。

`list` 自带 `sort`，是因为 `std::sort` 需要随机访问迭代器。`list::sort` 通常用归并排序实现，只调整指针。

!!! lawyer "list::sort 的 constexpr"
    当前草案中，`list` 类定义里的两个 `sort` 声明带有 `constexpr`，而 [list.ops] 中描述 `sort` 的那两个声明却没有，属于编辑上的不一致。`forward_list` 的两处都带 `constexpr`。本机 libc++ 中 `list::sort` 可以在常量求值中调用。

## erase 与 erase_if [list.erasure]

¶1 非成员 `erase(c, value)` 委托给 `erase_if`；¶2 `erase_if(c, pred)` 等价于 `c.remove_if(pred)`。链表可以直接摘除节点，不需要先 `remove` 再 `erase`。

## 什么时候该用 list

- 有中间插入擦除，同时需要迭代器和引用一直有效（`deque` 只对两端插入保证引用有效）；
- 需要在多个序列之间常数时间转移元素。LRU 缓存的经典实现就是 `unordered_map<Key, list<…>::iterator>` 加上把命中的元素 `splice` 到表头；
- 元素既不能复制也不能移动。`list` 的 `emplace` 只要求 *Cpp17EmplaceConstructible*，插入时从不移动已有元素。

其他场景下，连续存储的 `vector` 几乎总是更快。

## 思考题

!!! question "思考题"
    `a.splice(a.begin(), a, std::next(a.begin()), a.end())` 合法吗？复杂度是多少？效果是什么？

<details markdown="1">
<summary>答案</summary>

合法。第 11 段的前置条件只要求 `[first, last)` 是 `x`（这里就是 `*this`）中的有效区间，并且 `pos` 不在其中；`a.begin()` 不在 `[next(a.begin()), a.end())` 中。

按第 14 段，`addressof(x) == this` 时是常数时间，因为元素个数不变，不需要数区间长度。效果是把除首元素外的所有元素挪到首元素之前，也就是把原来的首元素移到了末尾。
</details>
