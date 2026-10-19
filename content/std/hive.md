---
title: hive
summary: C++26 的 std::hive 把元素存放在若干元素块中，插入位置由容器决定，插入和擦除都是常数时间，并且插入擦除从不移动其他元素。
status: done
covers: *, hive.syn
related: sequence.reqmts, container.requirements, container.requirements.general, list, deque, vector
tags: 标准库, 容器, hive, C++26, 错误行为
since: c++26
updated: 2026-10-19
---

!!! tldr
    - `hive` 适合大量对象频繁创建和销毁、彼此用指针互相引用的场景：元素地址稳定，遍历又比 `list` 快得多。
    - 插入位置由容器决定，可能复用被擦除元素留下的空位；插入只使尾后迭代器失效，擦除只使被擦除元素失效。
    - 没有 `front`、`back`、`push_back`、`operator[]`，也没有 `==`；插入时给的位置提示一律忽略。
    - `reserve` 和 `trim_capacity` 从不使任何东西失效；`shrink_to_fit`、`reshape`、`sort` 可能搬动元素并打乱顺序。
    - 块容量限制超出实现的硬限制，以及 `x.splice(x)`，都是错误行为（erroneous behavior），不是未定义行为。

`std::hive`（{{c++26}}）来自游戏、仿真等领域常用的对象池模式，也叫桶数组（bucket array）。这类程序里有大量对象被频繁创建和销毁，对象之间用指针互相引用，所以要求元素地址稳定；同时又要经常遍历全部对象，所以要求内存局部性好。

`vector` 擦除元素时会挪动后面的元素，地址不稳定；`list` 每个元素单独分配，遍历时在内存里跳来跳去。`hive` 的折中是：元素放在若干大块里，擦除只是把位置标记为空，遍历时跳过；插入优先填进这些空位。

!!! impl
    截至写作时，本机 libc++ 还没有提供 `<hive>`，本机也没有其他实现，所以本页的代码没有经过编译验证，也不标判定。

```cpp title="hive-sketch.cpp"
#include <hive>

struct Particle { float x, y; Particle* target; };

void step(std::hive<Particle>& ps, Particle* dead) {
  // 由指针找回迭代器，再擦除；其他元素的地址不变
  ps.erase(ps.get_iterator(dead));
  // 插入位置由容器决定，可能复用 dead 留下的空位
  auto it = ps.insert({0, 0, nullptr});
  for (Particle& p : ps) p.x += 1;   // 遍历时跳过空位
  (void)it;
}
```

## 元素块与跳过式擦除 [hive.overview]

¶1 `hive` 是一种插入和擦除都是常数时间的序列容器。存储自动管理，分布在多个内存块中，这些块叫**元素块**（element blocks）。插入的位置由容器决定，插入可以复用被擦除元素的内存位置。注 1 补充，构造和赋值不算插入。

¶2 含有元素的块叫**活动块**（active blocks），不含元素的块叫**保留块**（reserved blocks）。活动块变空后，要么被释放，要么成为保留块；保留块存放元素后又成为活动块。调用 `reserve` 可以创建更多保留块。

¶3 擦除用某种未指明的常数时间技术标记被擦除的位置，之后遍历时跳过它们，而不是把后面的元素挪过来。参考实现用一个跳跃字段（skipfield）记录连续空位的长度，迭代器可以一步跳过一整段空位。

¶4 活动块的容量按实现定义的增长因子增长，这个因子不必是整数。例如，新块的容量可以等于已有活动块的容量之和。

¶6 `hive` 满足容器的要求，但不提供 `==` 和 `!=`；它还满足可逆容器、分配器感知容器的要求，以及序列容器的一部分要求。不提供 `==` 是因为元素顺序由容器决定，两个内容相同的 `hive` 迭代顺序可能不同，逐个比较没有意义，而按多重集合比较代价又太高。

¶7 迭代器满足 *Cpp17BidirectionalIterator* 的要求，同时建模 `three_way_comparable<strong_ordering>`，可以用 `<` 比较两个迭代器的先后。

### 块容量限制（¶5）

用户和实现都可以为元素块的容量设定最小值和最大值，用 `hive_limits{min, max}` 表示：

- (5.1) 最小限制不得大于最大限制；
- (5.2) 用户构造时没有指定，就使用实现的默认限制；
- (5.3) 默认限制不一定等于实现能支持的最小和最大块容量，后两者叫**硬限制**（hard limits）。最大硬限制不得超过 `allocator_traits<Allocator>::max_size()`；
- (5.4) 传给构造函数或 `reshape` 的限制超出硬限制，或者最小值大于最大值时，行为是错误的，效果由实现定义。注 3 指出，可以用 `is_within_hard_limits` 事先检查；
- (5.5) 容量在 [min, max] 之内的块，称为在这对限制的范围之内（within the bounds）。

(5.4) 用的是 C++26 的**错误行为**（erroneous behavior，[[intro.defs]]）：程序有错，但行为是确定的，由实现定义。实现可以诊断，例如终止程序或抛出异常，也可以把限制钳制到合法范围，但不能像对待 UB 那样假设它不会发生。

## 和 vector 不同的接口

- 插入不带位置参数：`insert(x)`、`emplace(args...)` 返回指向新元素的迭代器。`emplace_hint(hint, ...)` 和 `insert(hint, x)` 中的提示被忽略（[hive.modifiers] 第 2、6 段），保留它们只是为了与其他容器的泛型代码兼容。
- 没有 `front`、`back`、`push_back`、`operator[]`，因为位置不由用户控制。
- 多了一组容量管理函数：`capacity`、`reserve`、`shrink_to_fit`、`trim_capacity`、`block_capacity_limits`、`reshape`。
- 多了几个操作：`splice`、`unique`、`sort`、`get_iterator`。
- 大部分成员不是 `constexpr`，只有构造空 `hive` 的几个构造函数和与 `hive_limits` 有关的几个函数是。

## 构造与赋值 [hive.cons]

每个构造函数都有一个接受 `hive_limits` 的版本，用它初始化仅用于阐述的成员 *current-limits*（¶3、¶6、¶9 等）。

¶16 复制构造使用 `x` 的 *current-limits*。复制赋值则不改变 *current-limits*（¶26 注 1），和 `vector` 赋值不传播 `capacity` 类似。

¶19 移动构造，以及分配器相等时带分配器的移动构造，把元素块整块从 `x` 移过来，*current-limits* 一并接管。指针、引用和迭代器继续指向原来的元素，只是它们现在属于 `*this`。这是常数时间。分配器不相等时只能逐个移动元素，`x` 的所有迭代器（包括尾后迭代器）都失效，线性时间（¶21）。¶20 两种情况下，之后 `x` 都为空，元素的相对顺序不变。

¶28–¶31 移动赋值的异常规格是 `noexcept(POCMA || is_always_equal)`。POCMA 为真或分配器相等时整块接管，同时接管 *current-limits*；否则逐个移动元素。

## 容量 [hive.capacity]

| 成员 | 效果 | 失效 |
|---|---|---|
| `capacity()` | 不再分配元素块就能容纳的元素总数（¶1） | 无 |
| `reserve(n)` | `n > capacity()` 时分配保留块，之后 `capacity() >= n`；超过 `max_size()` 抛 `length_error`（¶3–¶6） | 全部保持有效，包括尾后迭代器（¶7） |
| `shrink_to_fit()` | 非约束性请求，让 `capacity()` 接近 `size()`；可能重新分配元素（¶9） | 若重新分配，元素顺序可能改变，全部失效（¶11） |
| `trim_capacity()`、`trim_capacity(n)` | 释放全部保留块，或把容量降到不少于 n；`noexcept`（¶12） | 全部保持有效（¶14） |
| `block_capacity_limits()` | 返回 *current-limits*（¶15） | 无 |
| `block_capacity_default_limits()`、`block_capacity_hard_limits()` | 静态函数，返回实现的默认限制和硬限制（¶17、¶19） | 无 |
| `is_within_hard_limits(lim)` | `hl.min <= lim.min && lim.min <= lim.max && lim.max <= hl.max`（¶22） | 无 |
| `reshape(limits)` | 把不在新限制范围内的活动块中的元素重新分配到范围内的块里，释放范围外的块；`size()` 不变（¶24–¶25） | 若重新分配，顺序可能改变，全部失效；否则保持有效（¶27） |

`trim_capacity` 和 `shrink_to_fit` 的区别是 `hive` 设计的核心。前者只释放空块，从不碰元素，所以不会使任何东西失效；后者为了压缩内存，可以把元素从稀疏的块里搬走，所以会使一切失效并打乱顺序。依赖元素地址稳定的程序只应该使用 `trim_capacity`。

## 插入与擦除 [hive.modifiers]

- ¶1–¶5 `emplace` 和 `emplace_hint`：要求 `T` 可以从 `args` 就地构造；抛出异常时没有效果；常数时间，恰好构造一个 `T`；只使尾后迭代器失效。注 1 说明 `args` 可以引用 `*this` 中的元素。
- ¶6 各个 `insert(x)` 等价于 `emplace(std::forward<decltype(x)>(x))`。
- ¶7–¶10 `insert(il)` 和 `insert_range(rg)`：`rg` 不得与 `*this` 重叠；区间中每个迭代器恰好解引用一次；线性时间；插入了元素时使尾后迭代器失效。
- ¶11–¶15 `insert(n, x)` 插入 n 个副本；`insert(first, last)` 等价于 `insert_range(ranges::subrange(first, last))`。
- ¶16–¶17 `erase`：线性于擦除的元素个数；如果有活动块因此变空，最坏还要加上线性于块数的时间，用来把空块从块链中摘下。只使被擦除元素的迭代器、指针和引用失效；擦掉最后一个元素时，尾后迭代器也失效。
- ¶18–¶19 `swap`：交换元素、`capacity()` 和 *current-limits*，常数时间。

## 其他操作 [hive.operations]

¶1 名为 `Predicate`、`BinaryPredicate` 的实参要满足算法库的要求；`i + n`、`i - n` 的含义是 `next(i, n)`、`prev(i, n)`；`sort` 适用 [[alg.sorting]] 的定义。

**splice**（¶2–¶6）。前置条件是两个 `hive` 的分配器相等。`addressof(x) == this` 时行为是错误的，没有效果。否则把 `x` 的活动块转入 `*this`，`x` 变空，指针、引用和迭代器跟着元素走；`x` 的保留块不转移。如果 `x` 有活动块不在 `*this` 的 *current-limits* 范围之内，抛出 `length_error`；抛出异常时没有效果。复杂度线性于两者的块数之和，而不是元素个数。两边的尾后迭代器都失效。

**unique**（¶7–¶12）。每组连续等价的元素只保留第一个；谓词恰好调用 `size() - 1` 次；只使被擦除元素失效，擦掉最后一个元素时尾后迭代器也失效。

**sort**（¶13–¶16）。要求 `T` 可移动插入、可移动赋值、可交换；比较 O(N log N) 次；可能分配内存；引用、指针和迭代器（包括尾后迭代器）都可能失效；注 1 指出不要求稳定。这和 `list::sort` 正好相反：`list` 重排链接，不失效，而且稳定；`hive` 的元素在块里，排序只能移动值。

**get_iterator**（¶17–¶19）。前置条件是 `p` 指向 `*this` 中的元素，返回指向同一元素的迭代器，复杂度线性于活动块的个数，因为要找出 `p` 落在哪个块里。对象之间互相保存的是裸指针，要擦除某个对象时，就靠它换回迭代器。

## erase 与 erase_if [hive.erasure]

¶1 非成员 `erase(c, value)` 委托给 `erase_if`。¶2 `erase_if(c, pred)` 被规定为逐个调用 `c.erase(i)` 的循环，而不是先 `remove_if` 再 `erase`：`remove_if` 会挪动元素的值，破坏 `hive` 的地址稳定性。

## 与其他序列容器比较

| | `vector` | `deque` | `list` | `hive` |
|---|---|---|---|---|
| 插入位置 | 用户指定 | 用户指定 | 用户指定 | 容器决定 |
| 插入使其他元素失效 | 重新分配时全部失效 | 迭代器失效，引用不失效 | 否 | 否，只有尾后迭代器 |
| 擦除使其他元素失效 | 擦除点之后的全部 | 视位置而定 | 否 | 否 |
| 每个元素单独分配 | 否 | 否 | 是 | 否，按块分配 |
| 遍历的内存局部性 | 最好 | 好 | 差 | 好，跳过空位 |
| 随机访问 | 是 | 是 | 否 | 否 |

<details class="fine" markdown="1"><summary>其余条文</summary>

[[hive.modifiers#7]] 的前置条件写的是 `T` is *Cpp17EmplaceInsertable* into hive，而 [container.alloc.reqmts] 定义的术语是 *Cpp17EmplaceConstructible*，并没有 *Cpp17EmplaceInsertable*。按上下文应读作后者，这是一处尚待编辑修正的笔误。

</details>
