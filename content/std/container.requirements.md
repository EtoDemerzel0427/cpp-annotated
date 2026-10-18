---
title: 容器要求总览：复杂度、失效与异常安全总表
summary: [container.requirements] 的导读与"查表页"——复杂度只数元素操作、容器只为元素类型调用 allocator_traits::construct、哪些成员函数在数据竞争意义上算 const；并汇总全部标准容器的迭代器/引用失效规则、复杂度与异常安全保证
status: done
covers: container.requirements.pre, container.requirements.dataraces
related: container.requirements.general, sequence.reqmts, associative.reqmts, unord.req, container.node, res.on.data.races, intro.races, allocator.traits
tags: 标准库, 容器, 迭代器失效, 复杂度, 异常安全, 数据竞争
updated: 2026-10-18
---

[container.requirements] 是整个第 23 章的"宪法"。后面每个具体容器（`vector`、`map`……）的条款都很短，因为它们几乎只说一句"`X` 满足容器、可逆容器、分配器感知容器、序列容器的要求"，然后只补充**表格没有覆盖的部分**。所以想回答"`deque::push_front` 会不会让我手里的指针悬空""`unordered_map::insert` 抛异常后容器什么样"，你需要把**通用要求**和**具体容器的补充条款**拼起来读——本页就是把这些拼图拼好的结果。

本节的组织：

| 子条款 | 内容 | 本站笔记 |
|---|---|---|
| [container.requirements.pre] | 三条总则：容器是什么、复杂度怎么数、元素用谁构造 | 本页 |
| [container.requirements.general] | 容器 / 可逆容器 / 可选操作 / 分配器感知容器四组具名要求 | [[container.requirements.general]] |
| [container.requirements.dataraces] | 哪些成员函数在数据竞争意义上算 `const` | 本页 |
| [sequence.reqmts] | 序列容器要求与可选序列操作（`front`、`push_back`、`operator[]`……） | [[sequence.reqmts]] |
| [container.node]、[container.insert.return] | 节点句柄与 `insert_return_type` | [[container.node]] |
| [associative.reqmts] | 有序关联容器要求 | [[associative.reqmts]] |
| [unord.req] | 无序关联容器要求 | [[unord.req]] |

!!! note "具名要求不是 concept"
    这里的"*container* 要求""*Cpp17CopyInsertable*"等都是**具名要求**（named requirements，[[structure.requirements]]）：一组表达式加语义的文字约定，编译器不检查。违反它们通常落入"前置条件不满足"，即 {{ub}}，而不是编译错误。标准库只在少数地方（如 `container-compatible-range`、`ranges::to`）用了真正的 concept。

## 三条总则（[container.requirements.pre]）

### 容器管理元素的存储（¶1）

¶1 一句话定义：容器是**存储其他对象**的对象，并通过构造函数、析构函数、插入、擦除操作**控制这些对象的分配与释放**。注意关键词是"控制"：元素的生命周期（[[basic.life]]）完全由容器决定——你拿到的引用、指针、迭代器什么时候还指向活着的对象，正是本页后半部分"失效规则"要回答的问题。

### 复杂度只数"对元素的操作"（¶2）

!!! std
    All of the complexity requirements in this Clause are stated solely in terms of the number of operations on the contained objects.

    本章所有复杂度要求，**只**按对所含对象执行的操作次数来计。

所以 `vector<vector<int>>` 的拷贝构造是"线性"的——它对外层的 N 个元素各做一次拷贝构造，至于每次拷贝内部又是线性的，不计入。由此有两个常被忽视的推论：

- **复杂度不约束内存分配次数和比较之外的开销**，除非条款单独写明。比如 `vector` 的"摊还常数"`push_back`，是对 `T` 的构造次数而言的；它之所以**事实上**迫使实现采用几何增长，是因为 [vector.modifiers] 的"摊还常数时间"要求加上"重新分配时要搬迁全部元素"这一事实：若每次只多分配常数个槽位，搬迁的元素操作总数就是平方级。
- 复杂度要求是**对实现的禁令**。几个经典例子：

| 复杂度要求 | 它禁止了什么 |
|---|---|
| `size()` 常数（[[container.reqmts#54]]） | 禁止 `list::size()` 遍历计数——这正是 C++11 起 `list` 的跨链表区间 `splice` 变成线性的原因（[[list]]） |
| `deque` 两端插入常数且"恰好调用一次 `T` 的构造函数"（[[deque]]） | 禁止用"环形 `vector` + 扩容搬迁"实现 `deque` |
| 无序容器的 rehash 不使指针/引用失效（[[unord.req#9]]） | 事实上禁止开放寻址（open addressing）哈希表，迫使实现采用"每个元素一个节点"的链式结构 |
| `swap` 常数且不对元素做任何移动/拷贝/交换（[[container.reqmts#50]]、¶65） | 禁止对除 `array`、`inplace_vector` 之外的容器做"逐元素交换"——交换只能交换内部指针（以及分配器、比较器等） |

### 元素只能通过分配器构造（¶3）

¶3 规定：除 `basic_string` 外的分配器感知容器，构造元素用 `allocator_traits<A>::rebind_traits<U>::construct`、销毁用 `…::destroy`（[[allocator.traits]]），其中 `U` 是 `value_type` 或容器内部类型；而且这两个函数**只**对容器的元素类型调用，**不**对内部类型调用。

注 1 点明了后果：节点式容器（`list`、`map`……）不能 `construct` 一个"节点"，而要先分配一块含**对齐缓冲区**的节点内存，再对缓冲区里的元素调用 `construct`。这条规则保证了自定义分配器（例如 [[allocator.adaptor|scoped_allocator_adaptor]]、`polymorphic_allocator` 的 uses-allocator 构造，[[allocator.uses]]）**看得到每一个元素的构造**，并且只看到元素。

{{impl}} libc++ 中，`std::map<int,int>` 的节点为 40 字节（左/右/父三个指针 + 颜色位，再加 8 字节的 `pair<const int,int>`），`std::list<int>` 的节点 24 字节，`std::forward_list<int>` 的节点 16 字节——这是本机用计数分配器实测的 `allocate` 请求大小，各页有详细测量。

## 数据竞争：哪些成员函数"算 const"（[container.requirements.dataraces]）

库的总规则 [[res.on.data.races]] 是：标准库函数不得修改通过非 `const` 实参以外途径可达的对象，通过 `const` 实参只能读。于是"两个线程同时调用 `v.begin()`"是否构成数据竞争（[[intro.races]]），取决于 `begin()` 算不算修改了 `v`——非 `const` 的 `begin()` 形式上拿的是非 `const` 的 `*this`。

¶1 因此专门列出：为避免数据竞争，实现必须把 `begin`、`end`、`rbegin`、`rend`、`front`、`back`、`data`、`find`、`lower_bound`、`upper_bound`、`equal_range`、`at`，以及**除关联容器和无序关联容器以外的** `operator[]` 视为 `const`。

- `map::operator[]` 被排除在外，因为它在键不存在时会**插入**——它真的是修改操作。多线程只读共享的 `map` 必须用 `find`/`at`/`contains`。
- 这条只保证"容器结构本身"没有竞争；通过返回的引用读写**同一个元素**仍按 [[intro.races]] 判断。

¶2 不论 [[res.on.data.races]] 怎样，实现必须保证：并发修改**同一容器中不同元素**所含的对象不构成数据竞争——`vector<bool>` 除外。¶3 的注给出对照：

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

而对 `vector<bool> y`，`y[0] = true` 与 `y[1] = true` 并发执行**可能**构成数据竞争：两个位落在同一个字里，写一位就是对整个字做读-改-写（详见 [[vector.bool]]）。这是 `vector<bool>` "不是真正的容器"的又一个证据。

## 总表一：结构与复杂度

下表把各容器的规范性保证压缩在一起（"均摊"指摊还复杂度；`n` 为元素个数）。

| 容器 | 迭代器类别 | 连续？ | 分配器感知？ | 头/尾插入 | 中间插入/擦除 | 查找 | 规范出处 |
|---|---|---|---|---|---|---|---|
| `array<T,N>` | 随机访问 | 是 | 否 | —（定长） | — | — | [[array]] |
| `vector<T>` | 随机访问 | 是（`T≠bool`） | 是 | 尾：均摊 O(1) | O(到尾部的距离) | — | [[vector]] |
| `vector<bool>` | 随机访问（代理） | **否** | 是 | 尾：均摊 O(1) | 同上 | — | [[vector.bool]] |
| `inplace_vector<T,N>` {{c++26}} | 随机访问 | 是 | 否 | 尾：O(1)（非均摊），满则抛 `bad_alloc` | O(到尾部的距离) | — | [[inplace.vector]] |
| `deque<T>` | 随机访问 | 否 | 是 | 两端：O(1)，恰好一次构造 | O(到较近一端的距离) | — | [[deque]] |
| `list<T>` | 双向 | 否 | 是 | O(1) | O(1) | — | [[list]] |
| `forward_list<T>` | 前向 | 否 | 是 | 头：O(1) | O(1)（`insert_after`） | — | [[forward.list]] |
| `hive<T>` {{c++26}} | 双向（另可三路比较） | 否 | 是 | 位置由容器决定：O(1) | 擦除 O(1)（块变空时最坏 O(块数)） | — | [[hive]] |
| `set`/`map`/`multi*` | 双向 | 否 | 是 | O(log n)；带"恰在 p 之前"的提示时均摊 O(1) | O(log n)；按迭代器擦除均摊 O(1) | O(log n) | [[associative.reqmts]] |
| `unordered_*` | 至少前向 | 否 | 是 | 平均 O(1)，最坏 O(n) | 平均 O(1)，最坏 O(n) | 平均 O(1)，最坏 O(n) | [[unord.req]] |

几个"隐藏"在表格之外的规范性复杂度：

- 除 `array` 与 `inplace_vector` 外，所有容器的移动构造与 `swap` 都是常数（[[container.reqmts#16]]、¶50）。
- `forward_list` 不提供 `size()`，其 `operator==` 为线性（[[forward.list]]）。
- `list::splice` 搬一个区间：同一 `list` 内常数，跨 `list` 线性（为了维持 `size()` 常数）。
- 关联容器从**已排序**区间构造是线性的（[[associative.reqmts#25]]）。

## 总表二：迭代器、指针与引用失效

这是本页最常用的部分。"引用"列同时代表指针（标准总是把 references 与 pointers 并列）；"end"指尾后迭代器。

!!! summary "读表前的两条总则"
    - [[container.reqmts#67]]：**除非另有规定**（显式写出，或通过"用其他函数定义"间接带出），调用容器成员函数或把容器传给库函数，**不得**使该容器内对象的迭代器失效，也不得改变它们的值。所以凡是下表没列的操作（`size`、`find`、`begin`……）都不会导致失效。
    - ¶66.6：除 `array`、`inplace_vector` 外，`swap` **不**使任何元素的引用、指针、迭代器失效——它们改为指向**另一个容器**里的同一元素；但 `end()` 不指向元素，所以可能失效（¶65 明说 `a.end()` 交换后是否等于 `b.end()` 未指明）。

### 序列容器

| 容器 | 操作 | 失效的迭代器 | 失效的引用/指针 | 出处 |
|---|---|---|---|---|
| `vector` | 插入（`push_back`/`emplace`/`insert`/`append_range`/`resize` 增长），**发生重新分配** | 全部，含 end | 全部 | [[vector.modifiers#2]] |
| `vector` | 插入，**未**重新分配 | 插入点及之后，含 end | 插入点及之后 | [[vector.modifiers#2]] |
| `vector` | `erase`/`pop_back`/`resize` 缩小 | 擦除点及之后（含 end） | 擦除点及之后 | [[vector.modifiers#4]] |
| `vector` | `reserve(n)`/`shrink_to_fit()`，发生重新分配 | 全部，含 end | 全部 | [[vector.capacity#7]]、¶11 |
| `deque` | 两端插入 | **全部**，含 end | **无** | [[deque.modifiers#1]] |
| `deque` | 中间插入 | 全部 | 全部 | [[deque.modifiers#1]] |
| `deque` | 擦除最后一个元素（`pop_back`） | 被擦除者 + end | 被擦除者 | [[deque.modifiers#4]] |
| `deque` | 擦除第一个（但不是最后一个）元素（`pop_front`） | 仅被擦除者 | 仅被擦除者 | [[deque.modifiers#4]] |
| `deque` | 擦除既非首也非尾的元素 | 全部，含 end | 全部 | [[deque.modifiers#4]] |
| `deque` | `shrink_to_fit()`（size ≠ 旧容量时） | 全部，含 end | 全部 | [[deque.capacity#8]] |
| `list` | 任何插入 | 无 | 无 | [[list.modifiers#2]] |
| `list` | 擦除/`remove`/`unique` | 仅被擦除者 | 仅被擦除者 | [[list.modifiers#3]]、[list.ops] |
| `list` | `splice`/`merge`/`sort`/`reverse` | 无（被搬走的元素的迭代器改为属于目标 `list`） | 无 | [list.ops] |
| `forward_list` | 插入/擦除/`splice_after`/`merge`/`sort`/`reverse` | 同 `list`；`clear()` 不使 end 失效 | 同 `list` | [[forward.list.modifiers#1]]、¶38 |
| `array` | 无任何操作使之失效；`swap` 交换的是值，迭代器仍指向原 `array` | — | — | [[array.members#5]] |
| `inplace_vector` | `erase`/`pop_back` | 擦除点及之后 | 擦除点及之后 | [[inplace.vector.modifiers#19]] |
| `inplace_vector` | 插入 | 草案未给出显式规则（存储在对象内部、永不搬家；插入点之后的位置改为容纳被挪动后的值） | 同左 | 见 [[inplace.vector]] |
| `hive` | 插入（`insert`/`emplace`/`insert_range`） | **仅 end** | 无 | [[hive.modifiers#5]]、¶10、¶14 |
| `hive` | 擦除 | 被擦除者；擦掉最后一个元素时还有 end | 被擦除者 | [[hive.modifiers#17]] |
| `hive` | `reserve`/`trim_capacity` | 无 | 无 | [[hive.capacity#7]]、¶14 |
| `hive` | `shrink_to_fit`/`reshape`/`sort`（发生重新分配时） | 全部，含 end；元素顺序也可能改变 | 全部 | [[hive.capacity#11]]、¶27，[[hive.operations#16]] |
| 所有序列容器 | `clear()` | 全部元素；**可能**使 end 失效 | 全部 | [[sequence.reqmts#54]] |
| 所有序列容器 | `assign`/`assign_range` | 全部元素；`vector`、`deque` 还包括 end | 全部 | [[sequence.reqmts#59]]、¶63、¶68 |

### 关联与无序容器

| 容器 | 操作 | 失效的迭代器 | 失效的引用/指针 | 出处 |
|---|---|---|---|---|
| `set`/`map`/`multi*` | `insert`/`emplace`/`insert_range` | 无 | 无 | [[associative.reqmts#175]] |
| 同上 | `erase` | 仅被擦除者 | 仅被擦除者 | ¶175 |
| 同上 | `extract` | 仅被取出者 | **不失效**，但元素归节点句柄所有期间经由它们访问是 UB；成功插入后失效 | ¶176 |
| 同上 | `merge` | 不失效（迭代器类型相同时改为属于目标容器） | 不失效 | ¶115 |
| `unordered_*` | `insert`/`emplace`/`insert_range` | 若发生 rehash：**全部**；若 (N+n) ≤ z·B 则保证不 rehash | **从不** | [[unord.req#242]]、¶243 |
| 同上 | `rehash`/`reserve` | 全部 | 无 | ¶9 |
| 同上 | `erase` | 仅被擦除者 | 仅被擦除者 | ¶242 |
| 同上 | `extract` | 仅被取出者 | 同有序关联容器 | ¶244 |
| 同上 | `merge` | 被转移元素的迭代器、以及**目标容器的全部迭代器** | 不失效 | ¶146 |

`flat_map` 等容器适配器的失效规则取决于底层序列容器，见 [[flat.map]]。

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

用 `-fsanitize=address` 运行，ASan 报告 `heap-use-after-free`。注意这里**没有**任何前置条件被违反——`push_back` 本身完全合法，UB 来自之后经由失效引用访问已结束生命周期的对象（[[basic.life]]）。

## 总表三：异常安全

[[container.reqmts#66]] 给出缺省保证，各容器条款再"另有规定"：

| 保证（¶66） | 含义 | 被谁改写 |
|---|---|---|
| ¶66.1 单元素 `insert`/`emplace` 抛异常则无效果 | 强保证 | `vector`、`deque`、`inplace_vector` 的插入在 `T` 自身的拷贝/移动/赋值抛出时不再保证无效果；无序容器在"哈希函数抛出"时除外 |
| ¶66.2 `push_back`/`push_front`/`emplace_back`/`emplace_front` 抛异常则无效果 | 强保证 | `vector` 只在 `T` 可拷贝插入或 `is_nothrow_move_constructible_v<T>` 时保证 |
| ¶66.3 `erase`/`clear`/`pop_back`/`pop_front` 不抛异常 | 不抛 | `vector`、`deque`、`inplace_vector` 的 `erase` 可因 `T` 的赋值抛出；关联/无序容器的 `erase(k)` 可因比较/哈希抛出 |
| ¶66.4 返回的迭代器的复制不抛异常 | 不抛 | — |
| ¶66.5 `swap` 不抛异常 | 不抛 | `array`、`inplace_vector`；关联/无序容器的 `swap` 可因 `Compare`/`Hash`/`Pred` 的 `swap` 抛出 |

分容器的细则：

| 容器 | 插入时的保证 | 出处 |
|---|---|---|
| `vector` | 抛出者不是 `T` 的拷贝/移动构造、（移动）赋值或 `InputIterator` 操作：无效果。在尾部插入单个元素：若 `T` 可拷贝插入或不抛移动构造，无效果；否则若由不可拷贝 `T` 的移动构造抛出，效果未指明 | [[vector.modifiers#2]] |
| `vector::reserve`/`shrink_to_fit`/`resize` | 除"不可拷贝 `T` 的移动构造抛出"外无效果 | [[vector.capacity#4]]、¶9、¶16 |
| `deque` | 在**任一端插入单个元素**抛异常：无效果（无需 nothrow 移动——`deque` 从不搬迁已有元素） | [[deque.modifiers#3]] |
| `list`、`forward_list` | 任何插入抛异常：无效果（区间插入也是强保证） | [[list.modifiers#2]]、[[forward.list.modifiers#1]] |
| `inplace_vector` | `push_back`/`emplace_back`/`try_*`：无效果；`insert` 由 `T` 的操作抛出时：`size() ≥ n` 且前 n 个元素不变 | [[inplace.vector.modifiers#3]]、¶7、¶14 |
| `hive` | `emplace`/`insert` 抛异常：无效果 | [[hive.modifiers#2]] |
| 有序关联容器 | 单元素插入：无效果；`clear` 不抛；`erase(k)` 只可能由 `Compare` 抛出 | [[associative.reqmts]]（[associative.reqmts.except]） |
| 无序关联容器 | 单元素插入：除哈希函数外的任何操作抛出则无效果；`rehash` 除哈希/比较外抛出则无效果 | [[unord.req]]（[unord.req.except]） |

`vector` 那一行就是 `std::move_if_noexcept` 存在的理由：重新分配时，若 `T` 的移动构造可能抛出而 `T` 又可拷贝，实现必须**拷贝**旧元素，才能在中途失败时让旧缓冲区保持原样。详见 [[vector]]。

## 常见误区

!!! pitfall "\"deque 的 push_back 不使任何东西失效\""
    错。它**不使引用失效**，但使**所有迭代器**失效（包括指向未被触碰元素的迭代器）。原因是 `deque` 迭代器内部持有指向"块指针表"（map）的指针，两端插入可能让这张表重新分配。

!!! pitfall "\"unordered_map 插入只要没有 rehash 就安全\""
    对引用而言，**无论是否 rehash** 都安全——标准保证插入从不使引用/指针失效。对迭代器而言，"没有 rehash"的唯一**可依赖**判据是 ¶243 的 (N+n) ≤ z·B；提前 `reserve` 就是为了建立这个条件。

!!! pitfall "\"clear() 之后 end() 还能用\""
    [[sequence.reqmts#54]] 说 `clear()` **可能**使尾后迭代器失效。只有 `forward_list::clear()` 明确保证不使 end 失效（[[forward.list.modifiers#38]]）。

## 思考题

!!! question "1. 为什么 `std::unordered_map` 不能用开放寻址实现？"

<details markdown="1">
<summary>展开查看答案与解析</summary>

[[unord.req#9]]：rehash "does not invalidate pointers or references to elements"；¶242：插入"shall not affect the validity of references to container elements"。开放寻址把元素直接存在槽位数组里，扩容时必须把元素搬到新数组，于是所有引用失效。要同时满足这两条，每个元素必须有自己**稳定的地址**——即独立分配的节点。再加上节点句柄（[[container.node]]）的 `extract`/`insert` 要求能把元素"连同存储"转移给另一个容器，节点式实现就成了唯一选择。这也是 Abseil `flat_hash_map` 等高性能哈希表不能冒充 `std::unordered_map` 的原因。
</details>

!!! question "2. 两个线程分别对同一个 `std::map<int,int> m` 调用 `m[1]` 和 `m.find(2)`，即使键 1 已存在，是否构成数据竞争？"

<details markdown="1">
<summary>展开查看答案与解析</summary>

是（按标准的契约而言）。[[container.requirements.dataraces#1]] 把 `operator[]` 从"视为 const"的名单里**明确排除**了关联容器。于是 `m[1]` 是一次对 `m` 的修改调用（它被允许插入），与另一线程对 `m` 的任何访问冲突，按 [[intro.races]] 构成数据竞争即 UB——哪怕这次调用"碰巧"没有插入。正确做法是读线程都用 `find`/`at`/`contains`。
</details>

## 小结

- 复杂度只数元素操作；但它们**事实上**决定了数据结构：几何增长的 `vector`、分块的 `deque`、节点式的 `unordered_*`。
- 元素的构造与销毁只能经由 `allocator_traits::construct/destroy`，且只针对元素类型。
- 数据竞争：`begin/end/front/back/data/find/at/…` 视为 `const`；关联容器的 `operator[]` 不是。不同元素可并发修改，`vector<bool>` 除外。
- 失效规则的总原则：**不说就不失效**（¶67）；`swap` 让迭代器"跟着元素走"；`vector` 看是否重新分配、`deque` 看是否在两端、节点式容器只失效被擦除者、无序容器的引用永不因插入失效。
