---
title: 容器要求总览：复杂度、失效与异常安全对照表
summary: 容器要求的三条总则（复杂度只数元素操作、元素只经由分配器构造、哪些成员函数在数据竞争意义上算 const），以及全部标准容器的复杂度、迭代器失效和异常安全对照表。
status: done
covers: container.requirements.pre, container.requirements.dataraces
related: container.requirements.general, sequence.reqmts, associative.reqmts, unord.req, container.node, res.on.data.races, intro.races, allocator.traits
tags: 标准库, 容器, 迭代器失效, 复杂度, 异常安全, 数据竞争
updated: 2026-10-19
---

!!! tldr
    - 标准中的容器复杂度只数对元素的操作次数，但这些要求实际上决定了数据结构：`vector` 几何增长，`deque` 分块，`unordered_map` 每个元素一个节点。
    - 分配器感知容器只对元素类型调用 `allocator_traits::construct` 和 `destroy`，不对内部节点类型调用。
    - 多个线程同时调用 `begin`、`find`、`at` 等函数不构成数据竞争，但关联容器的 `operator[]` 可能插入，不算只读。并发修改不同元素也不构成数据竞争，`vector<bool>` 除外。
    - 失效规则的总原则是没有规定会失效的就不失效。`vector` 看是否重新分配，`deque` 看是否在两端，节点式容器只使被擦除的元素失效，无序容器的插入永远不使引用失效。
    - 默认的异常保证是单元素插入抛异常时没有效果、擦除不抛异常，`vector`、`deque` 等容器在元素自身的操作抛异常时有例外。

```cpp title="invalidate.cpp" run ub
#include <vector>
#include <cstdio>

int main() {
  std::vector<int> v{1, 2, 3};          // capacity() == 3
  int& first = v[0];
  v.push_back(4);                       // 新 size 超过 capacity：重新分配
  std::printf("%d\n", first);           // UB: first 指向已释放的旧缓冲区
}
```

用 `-fsanitize=address` 运行，ASan 报告 `heap-use-after-free`。`push_back` 本身完全合法，没有违反任何前置条件；UB 来自之后经由失效的引用访问一个生存期已经结束的对象（[[basic.life]]）。要知道一个操作会不会让手里的引用失效，要把通用要求和具体容器的条款合起来读，本页的对照表就是合起来的结果。

[container.requirements] 的各部分分布在以下页面：

| 子条款 | 内容 | 笔记 |
|---|---|---|
| [container.requirements.pre] | 三条总则 | 本页 |
| [container.requirements.general] | 容器、可逆容器、可选操作、分配器感知容器四组要求 | [[container.requirements.general]] |
| [container.requirements.dataraces] | 哪些成员函数在数据竞争意义上算 `const` | 本页 |
| [sequence.reqmts] | 序列容器要求 | [[sequence.reqmts]] |
| [container.node]、[container.insert.return] | 节点句柄与 `insert_return_type` | [[container.node]] |
| [associative.reqmts] | 有序关联容器要求 | [[associative.reqmts]] |
| [unord.req] | 无序关联容器要求 | [[unord.req]] |

这些要求是**具名要求**（named requirements，[[structure.requirements]]）：一组表达式及其语义的文字约定，不是 C++20 的 concept，编译器不检查。违反它们一般属于违反前置条件，即 {{ub}}，而不是编译错误。

## 三条总则 [container.requirements.pre]

### 容器控制元素的生存期（¶1）

¶1 容器是存储其他对象的对象，并通过构造函数、析构函数、插入和擦除操作控制这些对象的分配与释放。元素的生存期（[[basic.life]]）完全由容器决定，所以手里的引用、指针、迭代器什么时候还指向活着的对象，就是失效规则要回答的问题。

### 复杂度只数对元素的操作（¶2）

!!! std
    All of the complexity requirements in this Clause are stated solely in terms of the number of operations on the contained objects.

¶2 本章的复杂度要求只按对所含对象执行的操作次数计算。例 1：`vector<vector<int>>` 的拷贝构造是线性的，它对外层的 n 个元素各做一次拷贝构造；每次拷贝内部又是线性的，这不计入。

复杂度要求不约束内存分配的次数，除非条款单独写明。`vector::push_back` 的摊还常数，是对 `T` 的构造次数而言的。它实际上迫使实现采用几何增长，是因为重新分配时要把全部元素搬到新缓冲区：如果每次只多分配常数个位置，搬迁的总次数就是平方级。

复杂度要求也排除了一些实现方式：

| 复杂度要求 | 它排除了什么 |
|---|---|
| `size()` 是常数（[[container.reqmts#54]]） | `list::size()` 不能遍历计数。所以 C++11 起，在两个 `list` 之间 `splice` 一个区间变成了线性的，因为要数出搬了几个元素（[[list]]） |
| `deque` 两端插入是常数，而且恰好调用一次 `T` 的构造函数（[[deque]]） | 不能用环形缓冲区加扩容搬迁来实现 `deque` |
| 无序容器 rehash 不使指针和引用失效（[[unord.req#9]]） | 不能用开放寻址的哈希表，只能每个元素一个节点 |
| `swap` 是常数，不对元素做任何移动、拷贝或交换（[[container.reqmts#50]]、[[container.reqmts#65]]） | 除 `array`、`inplace_vector` 外，交换只能交换内部指针（以及分配器、比较器等） |

### 元素只能通过分配器构造（¶3）

¶3 除 `basic_string` 外的分配器感知容器，用 `allocator_traits<A>::rebind_traits<U>::construct` 构造元素，用 `...::destroy` 销毁元素（[[allocator.traits]]），其中 `U` 是 `value_type` 或容器的内部类型。这两个函数只对容器的元素类型调用，不对内部类型调用。

注 1 说明了后果：`list`、`map` 这类节点式容器不能 `construct` 一个节点，而要先分配一块包含对齐缓冲区的节点内存，再对缓冲区里的元素调用 `construct`。这样，`scoped_allocator_adaptor`（[[allocator.adaptor]]）和 `polymorphic_allocator` 的 uses-allocator 构造（[[allocator.uses]]）能看到每一个元素的构造，而且只看到元素。

{{impl}} 本机用计数分配器测得 libc++ 的节点大小：`std::map<int,int>` 每个节点 40 字节（左、右、父三个指针，颜色标志，再加 8 字节的 `pair<const int,int>`），`std::list<int>` 24 字节，`std::forward_list<int>` 16 字节。

## 数据竞争：哪些成员函数算 const [container.requirements.dataraces]

两个线程同时调用 `v.begin()` 算不算数据竞争（[[intro.races]]）？库的总规则 [[res.on.data.races]] 说，标准库函数通过非 `const` 实参可以修改对象，通过 `const` 实参只能读。非 `const` 版本的 `begin()` 拿到的是非 `const` 的 `*this`，按总规则它可能修改 `v`。

¶1 所以这一节专门规定：为避免数据竞争，实现必须把 `begin`、`end`、`rbegin`、`rend`、`front`、`back`、`data`、`find`、`lower_bound`、`upper_bound`、`equal_range`、`at` 视为 `const`，`operator[]` 也是，但关联容器和无序关联容器的除外。

`map::operator[]` 被排除，是因为键不存在时它会插入，确实是修改操作。多个线程只读一个共享的 `map`，要用 `find`、`at` 或 `contains`。这一条只保证容器本身的结构没有竞争；通过返回的引用读写同一个元素，仍然按 [[intro.races]] 判断。

¶2 不论 [[res.on.data.races]] 怎样规定，并发修改同一容器中不同元素所含的对象都不构成数据竞争，`vector<bool>` 除外。¶3 的注给出了对照：

```cpp title="dataraces.cpp" run ok
#include <thread>
#include <vector>

int main() {
  std::vector<int> x(2);
  std::thread t1([&] { x[1] = 5; });
  std::thread t2([&] { *x.begin() = 10; });   // 不同元素：没有数据竞争
  t1.join(); t2.join();
  return x[0] == 10 && x[1] == 5 ? 0 : 1;
}
```

对 `vector<bool> y`，`y[0] = true` 和 `y[1] = true` 并发执行可能构成数据竞争：两个位在同一个字里，写一位要对整个字做读、改、写（[[vector.bool]]）。

## 对照表一：结构与复杂度

n 为元素个数。

| 容器 | 迭代器类别 | 连续 | 分配器感知 | 头尾插入 | 中间插入、擦除 | 查找 | 出处 |
|---|---|---|---|---|---|---|---|
| `array<T,N>` | 随机访问 | 是 | 否 | 不能插入 | 不能插入 | | [[array]] |
| `vector<T>` | 随机访问 | 是（`T` 不是 `bool`） | 是 | 尾部摊还 O(1) | O(到尾部的距离) | | [[vector]] |
| `vector<bool>` | 随机访问（代理引用） | 否 | 是 | 尾部摊还 O(1) | 同上 | | [[vector.bool]] |
| `inplace_vector<T,N>` {{c++26}} | 随机访问 | 是 | 否 | 尾部 O(1)，满了抛 `bad_alloc` | O(到尾部的距离) | | [[inplace.vector]] |
| `deque<T>` | 随机访问 | 否 | 是 | 两端 O(1)，恰好一次构造 | O(到较近一端的距离) | | [[deque]] |
| `list<T>` | 双向 | 否 | 是 | O(1) | O(1) | | [[list]] |
| `forward_list<T>` | 前向 | 否 | 是 | 头部 O(1) | O(1)（`insert_after`） | | [[forward.list]] |
| `hive<T>` {{c++26}} | 双向 | 否 | 是 | 位置由容器决定，O(1) | 擦除 O(1)；有块变空时最坏 O(块数) | | [[hive]] |
| `set`、`map` 及 multi 版本 | 双向 | 否 | 是 | O(log n)；新元素正好插在提示位置之前时摊还 O(1) | O(log n)；按迭代器擦除摊还 O(1) | O(log n) | [[associative.reqmts]] |
| `unordered_*` | 至少前向 | 否 | 是 | 平均 O(1)，最坏 O(n) | 平均 O(1)，最坏 O(n) | 平均 O(1)，最坏 O(n) | [[unord.req]] |

表外还有几条复杂度规定：

- 除 `array` 和 `inplace_vector` 外，所有容器的移动构造和 `swap` 都是常数（[[container.reqmts#16]]、[[container.reqmts#50]]）。
- `forward_list` 不提供 `size()`（[[forward.list]]）。
- `list::splice` 搬一个区间：在同一个 `list` 内是常数，跨 `list` 是线性的。
- 关联容器从已排序的区间构造是线性的（[[associative.reqmts#25]]）。

## 对照表二：迭代器、指针与引用的失效

"引用"一列同时代表指针，标准总是把两者并列；"end"指尾后迭代器。读表前要记住两条总则：

- [[container.reqmts#67]]：除非另有规定（明确写出，或者通过用其他函数定义间接带出），调用容器的成员函数或把容器传给库函数，不使该容器中对象的迭代器失效，也不改变它们的值。所以表中没有列出的操作（`size`、`find`、`begin` 等）都不会导致失效。
- [[container.reqmts#66]] 第 6 项：除 `array`、`inplace_vector` 外，`swap` 不使任何元素的引用、指针、迭代器失效，它们改为指向另一个容器中的同一个元素。`end()` 不指向元素，所以可能失效；¶65 规定交换前的 `a.end()` 交换后是否等于 `b.end()` 是未指定的。

### 序列容器

| 容器 | 操作 | 失效的迭代器 | 失效的引用 | 出处 |
|---|---|---|---|---|
| `vector` | 插入（`push_back`、`emplace`、`insert`、`append_range`、`resize` 增长），发生重新分配 | 全部，含 end | 全部 | [[vector.modifiers#2]] |
| `vector` | 插入，没有重新分配 | 插入点及之后，含 end | 插入点及之后 | [[vector.modifiers#2]] |
| `vector` | `erase`、`pop_back`、`resize` 缩小 | 擦除点及之后，含 end | 擦除点及之后 | [[vector.modifiers#4]] |
| `vector` | `reserve`、`shrink_to_fit` 发生重新分配 | 全部，含 end | 全部 | [[vector.capacity#7]]、[[vector.capacity#11]] |
| `deque` | 在两端插入 | 全部，含 end | 无 | [[deque.modifiers#1]] |
| `deque` | 在中间插入 | 全部 | 全部 | [[deque.modifiers#1]] |
| `deque` | 擦除最后一个元素（如 `pop_back`） | 被擦除的元素和 end | 被擦除的元素 | [[deque.modifiers#4]] |
| `deque` | 擦除第一个元素但不是最后一个（如 `pop_front`） | 被擦除的元素 | 被擦除的元素 | [[deque.modifiers#4]] |
| `deque` | 擦除既不是第一个也不是最后一个的元素 | 全部，含 end | 全部 | [[deque.modifiers#4]] |
| `deque` | `shrink_to_fit`（size 不等于原容量时） | 全部，含 end | 全部 | [[deque.capacity#8]] |
| `list` | 任何插入 | 无 | 无 | [[list.modifiers#2]] |
| `list` | 擦除、`remove`、`unique` | 被擦除的元素 | 被擦除的元素 | [[list.modifiers#3]]、[[list.ops]] |
| `list` | `splice`、`merge`、`sort`、`reverse` | 无；被搬走的元素的迭代器改为属于目标 `list` | 无 | [[list.ops]] |
| `forward_list` | 插入、擦除、`splice_after`、`merge`、`sort`、`reverse` | 同 `list`；`clear()` 不使 end 失效 | 同 `list` | [[forward.list.modifiers#1]]、[[forward.list.modifiers#38]] |
| `array` | 没有使之失效的操作；`swap` 交换的是值，迭代器仍指向原来的 `array` | 无 | 无 | [[array.members#5]] |
| `inplace_vector` | `erase`、`pop_back` | 擦除点及之后 | 擦除点及之后 | [[inplace.vector.modifiers#19]] |
| `inplace_vector` | 插入 | 草案没有明确规定。存储在对象内部，不会搬家，但插入点之后的位置改为存放被挪动后的值 | 同左 | [[inplace.vector]] |
| `hive` | `insert`、`emplace`、`insert_range` | 只有 end | 无 | [[hive.modifiers#5]]、[[hive.modifiers#10]]、[[hive.modifiers#14]] |
| `hive` | 擦除 | 被擦除的元素；擦掉最后一个元素时还有 end | 被擦除的元素 | [[hive.modifiers#17]] |
| `hive` | `reserve`、`trim_capacity` | 无 | 无 | [[hive.capacity#7]]、[[hive.capacity#14]] |
| `hive` | `shrink_to_fit`、`reshape`、`sort` 发生重新分配 | 全部，含 end；元素的顺序也可能改变 | 全部 | [[hive.capacity#11]]、[[hive.capacity#27]]、[[hive.operations#16]] |
| 所有序列容器 | `clear()` | 全部元素，并且可能使 end 失效 | 全部 | [[sequence.reqmts#54]] |
| 所有序列容器 | `assign`、`assign_range` | 全部元素；`vector`、`deque` 还包括 end | 全部 | [[sequence.reqmts#59]]、[[sequence.reqmts#63]]、[[sequence.reqmts#68]] |

### 关联容器与无序容器

| 容器 | 操作 | 失效的迭代器 | 失效的引用 | 出处 |
|---|---|---|---|---|
| `set`、`map` 及 multi 版本 | `insert`、`emplace`、`insert_range` | 无 | 无 | [[associative.reqmts#175]] |
| 同上 | `erase` | 被擦除的元素 | 被擦除的元素 | [[associative.reqmts#175]] |
| 同上 | `extract` | 被取出的元素 | 不失效，但元素归节点句柄所有期间经由它们访问是 UB；在此期间取得的引用，元素成功插入后失效 | [[associative.reqmts#176]] |
| 同上 | `merge` | 不失效；迭代器类型相同时，被转移元素的迭代器改为属于目标容器 | 不失效 | [[associative.reqmts#115]] |
| `unordered_*` | `insert`、`emplace`、`insert_range` | 发生 rehash 时全部失效；(N+n) ≤ z·B 时保证不 rehash | 从不失效 | [[unord.req#242]]、[[unord.req#243]] |
| 同上 | `rehash`、`reserve` | 全部 | 无 | [[unord.req#9]] |
| 同上 | `erase` | 被擦除的元素 | 被擦除的元素 | [[unord.req#242]] |
| 同上 | `extract` | 被取出的元素 | 同有序关联容器 | [[unord.req#244]] |
| 同上 | `merge` | 被转移元素的迭代器，以及目标容器的全部迭代器 | 不失效 | [[unord.req#146]] |

表中 N 是插入前的元素个数，n 是插入的个数，B 是桶数，z 是最大负载因子。`flat_map` 等容器适配器的失效规则取决于底层的序列容器，见 [[flat.map]]。

## 对照表三：异常安全

[[container.reqmts#66]] 给出默认保证，各容器的条款再作出例外规定：

| ¶66 的默认保证 | 含义 | 例外 |
|---|---|---|
| ¶66.1 单元素 `insert`、`emplace` 抛异常时没有效果 | 强保证 | `vector`、`deque`、`inplace_vector` 的插入在 `T` 自身的拷贝、移动、赋值抛异常时不保证；无序容器在哈希函数抛异常时不保证 |
| ¶66.2 `push_back`、`push_front`、`emplace_back`、`emplace_front` 抛异常时没有效果 | 强保证 | `vector` 只在 `T` 可拷贝插入或 `is_nothrow_move_constructible_v<T>` 时保证 |
| ¶66.3 `erase`、`clear`、`pop_back`、`pop_front` 不抛异常 | 不抛 | `vector`、`deque`、`inplace_vector` 的 `erase` 可能因 `T` 的赋值抛异常；关联容器和无序容器的 `erase(k)` 可能因比较或哈希抛异常 |
| ¶66.4 返回的迭代器的拷贝构造和赋值不抛异常 | 不抛 | 无 |
| ¶66.5 `swap` 不抛异常 | 不抛 | `array`、`inplace_vector`；关联容器和无序容器的 `swap` 可能因 `Compare`、`Hash`、`Pred` 的 `swap` 抛异常 |

各容器的插入保证：

| 容器 | 插入时的保证 | 出处 |
|---|---|---|
| `vector` | 抛异常的不是 `T` 的拷贝构造、移动构造、赋值、移动赋值，也不是输入迭代器的操作时，没有效果。在尾部插入单个元素：`T` 可拷贝插入或移动构造不抛异常时，没有效果；否则由不可拷贝的 `T` 的移动构造抛出时，效果未指定 | [[vector.modifiers#2]] |
| `vector::reserve`、`shrink_to_fit`、`resize` | 除不可拷贝的 `T` 的移动构造抛异常外，没有效果 | [[vector.capacity]] |
| `deque` | 在任一端插入单个元素抛异常时没有效果，不需要不抛异常的移动构造，因为 `deque` 从不搬动已有元素 | [[deque.modifiers#3]] |
| `list`、`forward_list` | 任何插入抛异常都没有效果，区间插入也是 | [[list.modifiers#2]]、[[forward.list.modifiers#1]] |
| `inplace_vector` | `push_back`、`emplace_back` 和 `try_*` 系列没有效果；`insert` 由 `T` 的操作抛异常时，`size()` 不小于 n，且前 n 个元素不变 | [[inplace.vector.modifiers]] |
| `hive` | `emplace`、`insert` 抛异常时没有效果 | [[hive.modifiers#2]] |
| 有序关联容器 | 单元素插入没有效果；`clear` 不抛异常；`erase(k)` 只可能因 `Compare` 抛异常 | [[associative.reqmts]] |
| 无序关联容器 | 单元素插入时，哈希函数以外的操作抛异常则没有效果；`rehash` 时，哈希和比较以外的操作抛异常则没有效果 | [[unord.req]] |

`vector` 那一行解释了 `std::move_if_noexcept` 的用处：重新分配时，如果 `T` 的移动构造可能抛异常而 `T` 又可以拷贝，实现就必须拷贝旧元素，这样中途失败时旧缓冲区仍然完好。详见 [[vector]]。

## 常见误解

!!! pitfall "`deque::push_back` 不使任何东西失效"
    它不使引用失效，但使所有迭代器失效，包括指向没有被触碰的元素的迭代器。`deque` 的迭代器内部持有指向块指针表的指针，两端插入可能让这张表重新分配。

!!! pitfall "`unordered_map` 插入时只要没有 rehash 就安全"
    对引用来说，不论是否 rehash 都安全，插入从不使引用失效。对迭代器来说，判断不会 rehash 的唯一可靠依据是 [[unord.req#243]] 的 (N+n) ≤ z·B，提前 `reserve` 就是为了满足它。

!!! pitfall "`clear()` 之后 `end()` 还能用"
    [[sequence.reqmts#54]] 规定 `clear()` 可能使尾后迭代器失效。只有 `forward_list::clear()` 明确保证不使它失效（[[forward.list.modifiers#38]]）。

## 思考题

!!! question "思考题 1"
    为什么 `std::unordered_map` 不能用开放寻址实现？

<details markdown="1">
<summary>答案</summary>

[[unord.req#9]] 规定 rehash 不使指向元素的指针和引用失效，[[unord.req#242]] 规定插入不影响引用的有效性。开放寻址把元素直接存放在槽位数组里，扩容时必须把元素搬到新数组，所有引用都会失效。要同时满足这两条，每个元素必须有自己稳定的地址，也就是单独分配的节点。节点句柄（[[container.node]]）的 `extract` 和 `insert` 还要求能把元素连同存储一起转移给另一个容器。所以 Abseil 的 `flat_hash_map` 这类开放寻址的哈希表不能作为 `std::unordered_map` 的实现。
</details>

!!! question "思考题 2"
    两个线程分别对同一个 `std::map<int,int> m` 调用 `m[1]` 和 `m.find(2)`，即使键 1 已经存在，这是数据竞争吗？

<details markdown="1">
<summary>答案</summary>

按标准是。[[container.requirements.dataraces#1]] 明确把关联容器的 `operator[]` 排除在视为 `const` 的函数之外。`m[1]` 是一次修改 `m` 的调用，与另一个线程对 `m` 的访问冲突，按 [[intro.races]] 构成数据竞争，行为未定义，即使这次调用碰巧没有插入。读线程应该用 `find`、`at` 或 `contains`。
</details>

## 小结

- 复杂度只数元素操作，但它实际上决定了每种容器的数据结构。
- 元素只经由 `allocator_traits::construct` 和 `destroy` 构造、销毁，而且只针对元素类型。
- `begin`、`end`、`front`、`back`、`data`、`find`、`at` 等视为 `const`，关联容器的 `operator[]` 不是。不同元素可以并发修改，`vector<bool>` 除外。
- 没有规定会失效的就不失效；`swap` 让迭代器跟着元素走。
- 默认异常保证：单元素插入强保证，擦除不抛异常；`vector`、`deque`、`inplace_vector` 在元素自身操作抛异常时例外。
