---
title: deque
summary: std::deque 的契约与实现——"块 + 块指针表"的结构如何由两端常数插入、恰好一次构造、引用稳定这三条要求逼出来；两端插入使迭代器失效却不使引用失效；中间插入/擦除只挪较短一侧；两端插入的强异常保证；libc++ 的 4096 字节块
status: done
covers: *, deque.syn
related: sequence.reqmts, container.requirements, vector, list, container.adaptors
tags: 标准库, 容器, deque, 迭代器失效
updated: 2026-10-18
---

`std::deque`（double-ended queue）是"两端都能高效插入"的随机访问序列。它的规范正文只有几段，却通过复杂度和失效规则精确地刻画了一个特定的数据结构。理解 `deque`，最好的办法是从条款**反推**实现。

## 概述（[deque.overview]）

¶1：`deque` 支持随机访问迭代器；在开头或末尾插入和擦除是**常数时间**，在中间是线性时间。

¶2：满足容器、可逆容器、分配器感知容器、序列容器（**包括全部**可选序列操作）的要求。这是唯一提供 [[sequence.reqmts]] ¶70 里全部可选操作的容器：`front`/`back`/`push_front`/`push_back`/`emplace_*`/`prepend_range`/`append_range`/`pop_*`/`operator[]`/`at`。

¶3：迭代器满足 constexpr 迭代器要求。整个 `deque` 在当前草案中是 `constexpr` 的（C++26 将 `deque`、`list`、`forward_list` 及关联容器等一并 constexpr 化）；但截至本文编写时，本机 libc++ 尚未为 `deque` 实现 constexpr，`constexpr` 函数中使用 `deque` 无法常量求值。

## 从条款反推数据结构

[deque.modifiers] ¶2 的这一句是关键：

!!! std
    Inserting a single element at either the beginning or end of a deque always takes constant time and causes a single call to a constructor of T.

    在 deque 开头或末尾插入单个元素，总是常数时间，并且只调用一次 T 的构造函数。

注意"**always**"与"**single call to a constructor**"：不是摊还常数，并且不允许搬迁任何已有元素。再加上 ¶1 "两端插入不影响引用的有效性"，可以推出：元素一旦放下就**永不移动**，只能把新元素放进**新分配的块**里。另一方面，随机访问要求 `operator[]` 常数，于是需要一张"块指针表"（通常叫 map）来定位第 i 个元素所在的块：

```text
   map（块指针表，可扩容、可在两端留空位）
  ┌────┬────┬────┬────┬────┐
  │    │ b0 │ b1 │ b2 │    │
  └────┴─┬──┴─┬──┴─┬──┴────┘
         ▼    ▼    ▼
       [..xx][xxxx][xx..]       ← 定长的元素块；x 为活对象
          ▲              ▲
        begin           end
```

这个结构正好解释了每一条规则：

- 两端插入：在首块/尾块的空位上构造；没空位就分配一个新块，并在 map 两端登记。map 本身满了要重新分配——只复制**块指针**，不搬元素。所以**引用不失效**，但迭代器（内部持有指向 map 槽位的指针）**全部失效**。
- 严格说，map 扩容要复制 O(块数) 个指针，所以"总是常数时间"只对**元素操作**成立——这正是 [[container.requirements]] ¶2"复杂度只数元素操作"的用武之地。
- 中间插入：只能挪动元素；挑较短的一侧挪（下文 ¶2）。

{{impl}} libc++ 的块大小由 `__deque_block_size` 决定：`sizeof(T) < 256 ? 4096 / sizeof(T) : 16`。本机实测：`deque<int>` 第一次 `push_back` 先分配 1 个 8 字节的 map 槽，再分配一个 1024 × 4 = 4096 字节的块；元素为 1000 字节时一块 16 个元素（16000 字节）。`sizeof(std::deque<int>) == 48`。libstdc++ 的块为 512 字节，MSVC STL 的块极小（16 字节或 1 个元素），对大对象几乎退化为"每元素一次分配"。

## 构造函数（[deque.cons]）

`deque(const Allocator&)`（常数）、`deque(n)`（*Cpp17DefaultInsertable*，n 个 default-inserted 元素）、`deque(n, value)`（*Cpp17CopyInsertable*）、迭代器区间与 `from_range` 构造（线性于距离），全部与 [[sequence.reqmts]] 的通用条目一致（¶1–¶12）。

## 容量（[deque.capacity]）

- `resize(sz)`（¶1–¶2）：要求 *Cpp17MoveInsertable* 与 *Cpp17DefaultInsertable*；缩小则擦除末尾，增大则追加 default-inserted 元素。
- `resize(sz, c)`（¶3–¶4）：*Cpp17CopyInsertable*。
- `shrink_to_fit()`（¶5–¶8）：**非约束请求**，减少内存占用但不改变大小。若 size 等于旧容量，或抛出的异常不是不可拷贝 `T` 的移动构造抛出的，则无效果；若 size ≠ 旧容量，线性复杂度，并使**全部**引用、指针、迭代器和 end 失效。

`deque` 没有 `capacity()` 和 `reserve()` 成员——¶6–¶8 里说的"容量"是规范内部的概念。没有 `reserve` 的原因很自然：两端插入从不搬迁元素，预留空间没有收益。

## 修改器（[deque.modifiers]）

### 插入（¶1–¶3）

¶1 失效规则：

- **在中间插入**：使 `deque` 的**所有**迭代器和元素引用失效；
- **在任一端插入**：使所有迭代器失效，但**不影响**元素引用的有效性。

```cpp title="deque-refs.cpp" run ok
#include <deque>
#include <cstdio>

int main() {
  std::deque<int> d{1, 2, 3};
  int* p = &d[1];
  auto it = d.begin() + 1;
  for (int i = 0; i < 10000; ++i) d.push_back(i);   // 两端插入：引用保持有效
  for (int i = 0; i < 10000; ++i) d.push_front(i);
  std::printf("%d\n", *p);                         // OK：仍是 2
  (void)it;                                         // 但 it 已失效，不得再使用
}
```

这使 `deque` 成为"需要稳定元素地址、又只在两端增长"的场景（对象池、事件队列）的首选：比 `list` 省内存、对缓存友好，又不像 `vector` 那样扩容时搬家。

¶2 复杂度：线性于插入元素个数**加上到开头和末尾距离中较小者**。也就是说，在中间插入时实现必须挪动**较短**的一侧——在靠近开头处插入就把前半段往前挪。

¶3 异常安全：

- 抛出者不是 `T` 的拷贝/移动构造或（移动）赋值：无效果；
- 在**任一端**插入单个元素时抛出：**无效果**；
- 否则，若由不可拷贝 `T` 的移动构造抛出：效果未指明。

与 [[vector]] 比较：`vector::push_back` 的强保证依赖"`T` 可拷贝或移动不抛"，因为扩容要搬迁旧元素；`deque` 的两端插入从不搬迁旧元素，所以**无条件**地具有强保证。

### 擦除（¶4–¶6）

¶4 按擦除位置区分：

| 擦除的是 | 失效 |
|---|---|
| 最后一个元素（含 `pop_back`） | 仅被擦除元素的迭代器和引用 + 尾后迭代器 |
| 第一个但不是最后一个元素（含 `pop_front`） | 仅被擦除元素的迭代器和引用 |
| 既非第一也非最后的元素 | 尾后迭代器 + **所有**迭代器和引用 |

注 1 明确：`pop_front` 和 `pop_back` 是擦除操作。

¶5：除 `T` 的赋值运算符外不抛异常。¶6：析构函数调用次数等于擦除个数；赋值运算符调用次数**不超过**擦除点之前与之后元素个数中的较小者——又一次规定"挪短的一侧"。

## 擦除（[deque.erasure]）

非成员 `erase`/`erase_if` 等价于 erase-remove 惯用法（¶1–¶2），与 [[vector]] 相同。

## `deque` 与容器适配器

`std::stack` 和 `std::queue` 的默认底层容器都是 `deque`（[[container.adaptors]]）：`queue` 需要 `push_back` + `pop_front`，`vector` 没有后者；`stack` 只需要尾部操作，`vector` 也能胜任；默认选 `deque` 是沿袭 C++98 的设计，其好处是增长时不搬迁元素、不出现单次大的重新分配。

## 常见误区

!!! pitfall "以为 `deque` 是连续的"
    `deque` 的迭代器是随机访问的，但**不是** `contiguous_iterator`。`&d[0] + i == &d[i]` 只在同一块内成立；把 `&d[0]` 传给需要连续缓冲区的 C 接口是 {{ub}}。

!!! pitfall "以为 `pop_front` 后迭代器都失效"
    恰恰相反：擦除首元素（且不是最后一个）**只**使被擦除者失效。用 `deque` 做 FIFO 时，指向其余元素的迭代器在 `pop_front` 后仍然有效；但随后的 `push_back` 会使全部迭代器失效。

## 思考题

!!! question "`deque<T>::insert(begin() + 1, x)` 会调用 `T` 的赋值运算符吗？会调用几次？"

<details markdown="1">
<summary>展开查看答案与解析</summary>

会，最多 1 次。插入点离开头只有 1 个元素，¶2 要求复杂度线性于"插入个数 + 到两端距离的较小者"，实现会把第 0 个元素往前挪一格：在新的首位置**构造**（移动构造）原 `d[0]` 的值，然后把 `x` **赋值**到原第 0 个位置（或先挪后赋值，具体顺序由实现决定）。这也是 [[sequence.reqmts]] ¶25 要求 `deque` 的 `insert(p, t)` 还需 *Cpp17CopyAssignable* 的原因。由于这是中间插入，¶1 宣布全部迭代器和引用失效——即使物理上大多数元素根本没动。
</details>

## 小结

- 结构：定长块 + 块指针表；元素一旦放下永不移动（除非中间插入/擦除或 `shrink_to_fit`）。
- 两端插入：常数、恰好一次构造、**无条件强保证**；迭代器全失效，引用全保留。
- 中间插入/擦除：挪较短一侧，全部失效。
- 擦除首元素只失效被擦除者；擦除尾元素还失效 end。
- 没有 `capacity`/`reserve`；`shrink_to_fit` 是非约束请求。
