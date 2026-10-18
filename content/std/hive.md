---
title: hive
summary: C++26 的 hive——由多个元素块组成、插入位置由容器决定、插入擦除都是常数时间且插入从不使其他元素失效的"对象池"式序列容器；块容量限制 hive_limits 与错误行为、reserve/trim_capacity/shrink_to_fit/reshape 的失效差异、splice/sort/get_iterator，以及草案中的一处术语笔误
status: done
covers: *, hive.syn
related: sequence.reqmts, container.requirements, container.requirements.general, list, deque, vector
tags: 标准库, 容器, hive, C++26, 错误行为
since: c++26
updated: 2026-10-18
---

`std::hive`（{{c++26}}）来自游戏、仿真等领域的"对象池"/"桶数组"（bucket array）模式：大量对象频繁创建和销毁，彼此通过指针互相引用，因此要求**元素地址稳定**；同时又要遍历快、内存局部性好。`vector` 擦除会挪元素，`list` 每个元素一次分配、遍历跳来跳去；`hive` 的折中是：元素存放在若干**元素块**中，擦除只是"跳过"该位置，插入优先复用被擦除的空位。

!!! warning "本地验证状态"
    截至本文编写时，本机 libc++ 不提供 `<hive>`，本机也没有 GCC，因此本页不含经本地编译验证的示例。

## 概述（[hive.overview]）

¶1：`hive` 是一种提供**常数时间插入和擦除**的序列容器。存储自动管理在多个内存块中，称为**元素块**（*element blocks*）。插入的**位置由容器决定**，插入可能复用被擦除元素的内存位置。注 1：构造和赋值不算插入操作。

¶2：含有元素的块称为**活动块**（*active blocks*），不含元素的称为**保留块**（*reserved blocks*）。活动块变空后要么被释放、要么变成保留块；保留块在存放元素时变回活动块；`reserve` 可以创建额外的保留块。

¶3：擦除使用**未指明的常数时间技术**标记被擦除元素的位置，迭代时跳过它们，而**不是**挪动后续元素。（参考实现使用"跳跃字段"（skipfield）记录连续空位的长度，让迭代器 O(1) 地跳过整段空洞。）

¶4：活动块的容量按**实现定义**的增长因子增长（不必是整数），例如新块容量可以等于已有活动块容量之和。

### 块容量限制（¶5）

用户和实现都可以为元素块的容量设置最小、最大限制（`hive_limits{min, max}`）：

- (5.1) 最小限制不得大于最大限制；
- (5.2) 用户未指定时使用实现的**默认限制**；
- (5.3) 默认限制不保证等于实现能支持的最小/最大块容量，后者称为**硬限制**（*hard limits*）；最大硬限制不得超过 `allocator_traits<Allocator>::max_size()`；
- (5.4) 若传给构造函数或 `reshape` 的用户限制超出硬限制，或最小值大于最大值，则**行为是错误的（erroneous），效果由实现定义**；注 3：可用 `is_within_hard_limits` 检查；
- (5.5) 块容量在 [min, max] 内时称块"在限制范围内"（*within the bounds*）。

!!! lawyer "错误行为（erroneous behavior）进入库条款"
    (5.4) 是第 23 章少见的使用 {{erroneous}} 的地方：违反它不是 UB，而是"程序有错，但行为被限定在实现定义的范围内"（[[intro.defs]] 中的 erroneous behavior）。实现可以诊断（例如终止或抛异常），也可以钳制到合法范围，但不能让优化器把它当作"不可能发生"。下文 `splice` 的自拼接是另一处。

¶6：`hive` 满足容器要求，**但不提供 `==` 和 `!=`**；满足可逆容器、分配器感知容器的要求，以及序列容器的**部分**要求。没有 `==` 的原因是：元素的顺序由容器决定，两个"内容相同"的 hive 迭代顺序可能不同，按序比较没有意义，而按多重集合比较代价又太高。

¶7：迭代器满足 *Cpp17BidirectionalIterator*，同时建模 `three_way_comparable<strong_ordering>`——可以用 `<` 比较两个迭代器的先后，这对"判断 `it` 是否已越过 `last`"这类跳跃式遍历很重要。

## 接口概览

与 `vector` 相比，`hive` 的接口有几处刻意的差异：

- **没有**位置参数的插入：`insert(x)`、`emplace(args…)` 返回指向新元素的迭代器；`emplace_hint(hint, …)` 与 `insert(hint, x)` 的提示**被忽略**（¶2、¶6），存在只是为了与其他容器的泛型代码兼容。
- **没有** `front`、`back`、`push_back`、`operator[]`——位置不由用户控制。
- 额外的容量管理：`capacity`、`reserve`、`shrink_to_fit`、`trim_capacity`、`block_capacity_limits`、`reshape`。
- 额外的操作：`splice`、`unique`、`sort`、`get_iterator`。
- 大部分成员**不是** `constexpr`（只有几个构造函数和 `hive_limits` 相关的静态函数是）。

## 构造、复制与赋值（[hive.cons]）

- 所有构造函数都有接受 `hive_limits` 的版本，初始化仅用于阐述的 `current-limits`（¶3、¶6、¶9……）。
- 拷贝构造（¶15–¶17）：用 `x` 的 `current-limits`。拷贝赋值（¶25–¶27）：注 1 指出 `current-limits` **不变**——这和 `vector` 的"`capacity` 不随赋值传播"相似。
- 移动构造及分配器相等时的带分配器移动构造（¶18–¶21）：**整块**从 `x` 移入，`current-limits` 一并接管；指针、引用、迭代器继续指向原元素，但成为 `*this` 的成员；常数时间。分配器不等时逐元素移动，`x` 的全部迭代器（含 end）失效，线性。后置条件都要求 `x.empty()`、元素相对顺序不变（¶20）。
- 移动赋值（¶27–¶31）：`noexcept(POCMA || is_always_equal)`；POCMA 为真或分配器相等时整块接管（并接管 `current-limits`），否则逐元素移动。

## 容量（[hive.capacity]）

| 成员 | 效果 | 失效 |
|---|---|---|
| `capacity()` | 不再分配元素块即可容纳的元素总数（¶1） | — |
| `reserve(n)` | `n > capacity()` 时分配保留块，之后 `capacity() >= n`；超过 `max_size()` 抛 `length_error`（¶3–¶6） | **全部保持有效**，含 end（¶7） |
| `shrink_to_fit()` | 非约束请求，把 `capacity()` 往 `size()` 收；**可能重新分配元素**（¶9） | 若重新分配：元素**顺序可能改变**，全部失效，含 end（¶11） |
| `trim_capacity()` / `trim_capacity(n)` | 释放全部保留块 / 把容量减到不少于 n；`noexcept` | **全部保持有效**（¶14） |
| `block_capacity_limits()` | 返回 `current-limits`（¶15） | — |
| `block_capacity_default_limits()` / `block_capacity_hard_limits()` | 静态 constexpr，实现的默认 / 硬限制（¶17、¶19） | — |
| `is_within_hard_limits(lim)` | `hl.min <= lim.min && lim.min <= lim.max && lim.max <= hl.max`（¶22） | — |
| `reshape(limits)` | 把不在新限制内的活动块中的元素重新分配到合规块中，释放不合规的块；`size()` 不变（¶24–¶25） | 若重新分配：顺序可能改变，全部失效（¶27）；否则保持有效 |

`trim_capacity` 与 `shrink_to_fit` 的区分是 `hive` 设计的精髓：前者只释放**空**块，从不碰元素，所以绝不失效；后者为了压缩可以把元素从稀疏的块里**搬走**，所以会失效并打乱顺序。需要地址稳定的程序只应使用 `trim_capacity`。

## 修改器（[hive.modifiers]）

- `emplace`/`emplace_hint`（¶1–¶5）：前置条件 *Cpp17EmplaceConstructible*；抛异常则**无效果**；常数时间，恰好构造一个 `T`；**只使尾后迭代器失效**。注 1：`args` 可以引用 `*this` 中的值。
- `insert(x)` 系列（¶6）：等价于 `emplace(std::forward<decltype(x)>(x))`。
- `insert(il)`/`insert_range(rg)`（¶7–¶10）：`rg` 与 `*this` 不重叠；每个迭代器恰好解引用一次；线性；插入了元素则使尾后迭代器失效。
- `insert(n, x)`（¶11–¶14）、`insert(first, last)`（¶15，等价于 `insert_range(ranges::subrange(first, last))`）。
- `erase`（¶16–¶17）：线性于擦除个数；若有活动块因此变空，最坏还要线性于**块的个数**（要把空块从块链中摘除）；只使被擦除元素失效，擦掉最后一个元素时还使 end 失效。
- `swap`（¶18–¶19）：交换内容、`capacity()` 和 `current-limits`，常数，`noexcept(POCS || is_always_equal)`。

!!! lawyer "草案中的一处术语笔误"
    [hive.modifiers] ¶7 的前置条件写的是"`T` is *Cpp17EmplaceInsertable* into hive from `*ranges::begin(rg)`"。[[container.requirements.general]] 的 [container.alloc.reqmts] ¶2 并没有定义 *Cpp17EmplaceInsertable* 这个术语——定义的是 *Cpp17EmplaceConstructible*。按上下文，这里显然应读作后者；严格的 language lawyer 会把它记作一个尚待编辑修正的瑕疵。

## 操作（[hive.operations]）

¶1：谓词实参须满足 [algorithms.requirements]；`i + n`、`i - n` 即 `next(i, n)`、`prev(i, n)`；`sort` 适用 [[alg.sorting]]。

- **`splice(x)`**（¶2–¶6）：前置条件分配器相等。`addressof(x) == this` 时**行为是错误的**（{{erroneous}}）且无效果；抛异常则无效果；否则把 `x` 的内容（**活动块**）转入 `*this`，`x` 变空，指针、引用、迭代器随元素转移。若 `x` 有活动块不在 `*this` 的 `current-limits` 内，抛 `length_error`。复杂度线性于两者的**块数**之和（不是元素数）。`x` 的保留块不转移；双方的尾后迭代器失效。
- **`unique(pred)`**（¶7–¶12）：擦除连续等价元素中除第一个外的全部；恰好 `size() - 1` 次谓词调用；只使被擦除者失效（擦掉最后一个元素时还有 end）。
- **`sort(comp)`**（¶13–¶16）：要求 *Cpp17MoveInsertable*、*Cpp17MoveAssignable*、*Cpp17Swappable*；O(N log N) 次比较；**可能分配**；引用、指针、迭代器（含 end）**可能失效**；注 1：**不要求稳定**。与 `list::sort`（重排链接、不失效、稳定）形成鲜明对照：`hive` 的元素在块里，排序只能移动值。
- **`get_iterator(p)`**（¶17–¶19）：前置条件 `p` 指向 `*this` 中的元素；返回指向同一元素的迭代器；复杂度线性于**活动块数**（要找出 `p` 落在哪个块里）。这是从"对象之间互存的裸指针"回到容器迭代器（以便擦除）的桥梁。

## 擦除（[hive.erasure]）

`erase(c, value)` 委托给 `erase_if`；`erase_if(c, pred)` 被规定为逐个 `c.erase(i)` 的循环（¶2），而不是 erase-remove——因为 `remove` 会挪动元素值，破坏 `hive` 的地址稳定性。

## 与其他容器的对比

| | `vector` | `deque` | `list` | `hive` |
|---|---|---|---|---|
| 插入位置 | 用户指定 | 用户指定 | 用户指定 | **容器决定** |
| 插入使其他元素失效 | 可能（重新分配） | 迭代器是 | 否 | **否**（只失效 end） |
| 擦除使其他元素失效 | 之后的全部 | 视位置 | 否 | **否** |
| 每元素一次分配 | 否 | 否 | 是 | 否（按块） |
| 遍历局部性 | 最好 | 好 | 差 | 好（跳过空洞） |
| 随机访问 | 是 | 是 | 否 | 否 |

## 小结

- 元素块 + 跳过式擦除：插入和擦除都是常数时间，插入只使 end 失效，擦除只使被擦除者失效。
- 插入位置由容器决定，提示被忽略；没有 `==`、`front`、`back`、`operator[]`。
- `reserve`/`trim_capacity` 从不失效；`shrink_to_fit`/`reshape`/`sort` 可能搬移元素并打乱顺序。
- 块限制越界与自 `splice` 是**错误行为**而非 UB。
- `get_iterator` 让裸指针能换回迭代器；`erase_if` 是逐个擦除而非 erase-remove。
