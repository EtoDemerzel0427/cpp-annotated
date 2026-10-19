---
title: deque
summary: std::deque 是两端都能常数时间插入擦除的随机访问序列；它的复杂度和失效规则几乎唯一地决定了"定长块加块指针表"的实现。
status: done
covers: *, deque.syn
related: sequence.reqmts, container.requirements, vector, list, container.adaptors
tags: 标准库, 容器, deque, 迭代器失效
updated: 2026-10-19
---

!!! tldr
    - 在两端插入单个元素总是常数时间，只调用一次 `T` 的构造函数，已有元素从不移动。
    - 两端插入使所有迭代器失效，但不使任何元素的引用失效；中间插入使两者都失效。
    - 两端插入单个元素具有无条件的强异常保证，这一点比 `vector::push_back` 强。
    - 中间插入或擦除时，实现只挪动离两端较近的那一侧。
    - `deque` 不是连续存储，没有 `capacity()` 和 `reserve()`。

`std::deque`（double-ended queue）是一个两端都能高效插入的随机访问序列。它的条文不长，但复杂度和失效规则几乎唯一地确定了它的数据结构，所以最好从条文反推实现。

## 从一个保证说起

```cpp title="deque-refs.cpp" run ok
#include <cstdio>
#include <deque>

int main() {
  std::deque<int> d{1, 2, 3};
  int* p = &d[1];
  for (int i = 0; i < 10000; ++i) d.push_back(i);
  for (int i = 0; i < 10000; ++i) d.push_front(i);
  std::printf("%d\n", *p);   // 2：两端插入不使引用失效
}
```

插入了两万个元素，`p` 仍然指向原来的 2。`vector` 做不到这一点：扩容时元素会被搬到新的存储里，旧指针全部悬垂。

¶1 `deque` 支持随机访问迭代器，在开头或末尾插入、擦除是常数时间，在中间是线性时间。¶2 它满足容器、可逆容器、分配器感知容器和序列容器的要求，包括 [[sequence.reqmts]] 中全部可选操作：`front`、`back`、`push_front`、`push_back`、`emplace_front`、`emplace_back`、`prepend_range`、`append_range`、`pop_front`、`pop_back`、`operator[]`、`at`。标准库中只有 `deque` 提供了全部这些操作。

## 条文决定的数据结构

插入一节的第 2 段（[[deque.modifiers#2]]）是关键：

!!! std
    Inserting a single element at either the beginning or end of a deque always takes constant time and causes a single call to a constructor of T.

这里说的是总是常数时间，不是摊还常数；而且只调用一次构造函数，不允许搬动已有元素。再加上两端插入不使引用失效，可以推出：元素一旦放下就不再移动，新元素只能放进新分配的块里。另一方面，`operator[]` 必须是常数时间，于是还需要一张块指针表（通常叫 map），用来定位第 i 个元素在哪个块里。

```text
   map（块指针表，可以扩容，两端可以留空位）
  ┌────┬────┬────┬────┬────┐
  │    │ b0 │ b1 │ b2 │    │
  └────┴─┬──┴─┬──┴─┬──┴────┘
         ▼    ▼    ▼
       [..xx][xxxx][xx..]       ← 定长的元素块，x 是元素
          ▲              ▲
        begin           end
```

每条规则都能在这个结构上得到解释：

- 两端插入时，在首块或尾块的空位上构造元素；没有空位就分配一个新块，登记到 map 的一端。map 满了要重新分配，但只复制块指针，不搬元素。所以引用不失效；而迭代器内部保存着指向 map 槽位的指针，map 一重新分配它们就失效了。
- map 扩容要复制 O(块数) 个指针，严格说不是常数时间。标准的复杂度只计算对元素的操作次数（[[container.requirements.pre#2]]），所以总是常数时间对元素操作成立。
- 中间插入只能挪动元素，所以是线性的，实现挑较短的一侧去挪。

!!! impl
    libc++ 的块大小是 `sizeof(T) < 256 ? 4096 / sizeof(T) : 16` 个元素，`deque<int>` 一块是 1024 个 `int`。本机 `sizeof(std::deque<int>)` 是 48。libstdc++ 的块是 512 字节；MSVC STL 的块只有 16 字节，元素大于 8 字节时每块只放一个元素，对大对象几乎等于每个元素一次分配。

## 插入 [deque.modifiers]

¶1 失效规则按插入位置区分：

- 在中间插入，使 `deque` 的所有迭代器和元素引用失效；
- 在任一端插入，使所有迭代器失效，但不影响元素引用的有效性。

因此 `deque` 很适合需要稳定元素地址、又只在两端增长的场景，例如对象池或事件队列。它比 `list` 省内存、对缓存友好，又不像 `vector` 那样扩容时搬迁元素。

¶2 复杂度线性于插入的元素个数，加上插入点到开头和到末尾两个距离中较小的那个。也就是说，在靠近开头的位置插入时，实现要把前半段往前挪，而不是把后半段往后挪。

¶3 异常安全分三种情况：

- 抛出异常的不是 `T` 的复制构造、移动构造、复制赋值或移动赋值：没有效果；
- 在任一端插入单个元素时抛出异常：没有效果；
- 其他情况下，如果异常来自一个不可复制插入的 `T` 的移动构造函数：效果未指明。

和 [[vector]] 比较：`vector::push_back` 的强保证依赖 `T` 可复制或移动构造不抛异常，因为扩容时要搬迁旧元素。`deque` 的两端插入从不搬迁旧元素，所以强保证是无条件的。

## 擦除

¶4 失效规则按擦除位置区分：

| 擦除的元素 | 失效的范围 |
|---|---|
| 包括最后一个元素（如 `pop_back`） | 被擦除元素的迭代器和引用，以及尾后迭代器 |
| 包括第一个但不包括最后一个元素（如 `pop_front`） | 只有被擦除元素的迭代器和引用 |
| 既不是第一个也不是最后一个 | 尾后迭代器，以及所有元素的迭代器和引用 |

注 1 明确，`pop_front` 和 `pop_back` 也是擦除操作。

¶5 除了 `T` 的赋值运算符，擦除不抛异常。¶6 析构函数的调用次数等于擦除的元素个数；赋值运算符的调用次数不超过擦除点之前和之后元素个数中较小的那个，同样是只挪较短的一侧。

!!! pitfall "以为 pop_front 后所有迭代器都失效"
    擦除首元素（且它不是最后一个元素）只使被擦除元素失效。用 `deque` 做先进先出队列时，指向其余元素的迭代器在 `pop_front` 之后仍然有效。不过之后的 `push_back` 会使所有迭代器失效。

## 容量 [deque.capacity]

¶1–¶4 `resize(sz)` 和 `resize(sz, c)`：缩小时擦除末尾多出的元素，增大时在末尾追加默认插入的元素或 `c` 的副本。

¶5–¶8 `shrink_to_fit()` 是一个非约束性请求，可以减少内存占用，但不改变元素个数。如果大小已经等于原来的容量，或者抛出的异常不是来自不可复制插入的 `T` 的移动构造函数，就没有效果。真的发生了收缩时，复杂度线性，并使所有引用、指针、迭代器以及尾后迭代器失效。

`deque` 没有 `capacity()` 和 `reserve()`，第 6 到 8 段中的容量只是规范内部的概念。不提供 `reserve` 也合理：两端插入从不搬迁元素，预留空间没有收益。

!!! pitfall "以为 deque 是连续存储"
    `deque` 的迭代器是随机访问迭代器，但不是 `contiguous_iterator`。`&d[0] + i == &d[i]` 只在同一块之内成立，把 `&d[0]` 当作连续缓冲区交给 C 接口，越过块边界的访问是 {{ub}}。

## 构造与 erase_if

[deque.cons] 中的构造函数与 [[sequence.reqmts]] 的通用条目一致：空构造常数时间，`deque(n)` 和 `deque(n, value)` 线性于 n，迭代器区间和 `from_range` 构造线性于区间长度（¶1–¶12）。

[deque.erasure] 的非成员 `erase` 和 `erase_if` 等价于先 `remove`/`remove_if` 再 `erase` 的惯用法，与 [[vector]] 相同（¶1–¶2）。

## 与容器适配器的关系

`std::stack` 和 `std::queue` 默认的底层容器都是 `deque`（[[container.adaptors]]）。`queue` 需要 `push_back` 和 `pop_front`，`vector` 没有后者；`stack` 只用尾部操作，`vector` 也能胜任。默认选 `deque` 沿袭自 C++98，它的好处是增长时不搬迁元素，也不会出现单次很大的重新分配。

!!! impl
    当前草案中 `deque` 的成员都是 `constexpr`，迭代器满足 constexpr 迭代器的要求（[[deque.overview#3]]）。本机 libc++ 还没有为 `deque` 实现这一点：在 `consteval` 函数中构造 `deque` 无法常量求值。

## 思考题

!!! question "思考题"
    `d.insert(d.begin() + 1, x)` 会调用 `T` 的赋值运算符吗？之后哪些迭代器和引用还有效？

<details markdown="1">
<summary>答案</summary>

通常会，大约一次。插入点离开头只有一个元素，[[deque.modifiers#2]] 要求复杂度线性于插入个数加上到两端距离的较小者，所以实现会挪动前面那一个元素：在新的首位置移动构造原来的 `d[0]`，再把 `x` 赋值到原来第 0 个元素所在的位置。这也是 [[sequence.reqmts#25]] 要求 `deque` 的 `insert(p, t)` 还满足 *Cpp17CopyAssignable* 的原因。

这是中间插入，按 [[deque.modifiers#1]]，所有迭代器和引用都失效，尽管物理上大多数元素根本没有动。
</details>
