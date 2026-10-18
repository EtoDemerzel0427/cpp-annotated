---
title: 分配器特征
summary: allocator_traits 是容器与分配器之间的唯一接口——它把 C++11 的"最小分配器"补全成完整接口；propagate_on_container_* 决定容器赋值和交换时分配器跟不跟着走，is_always_equal 决定能否无条件偷缓冲区；construct/destroy 默认就是 construct_at/destroy_at
status: done
covers: allocator.traits.general, allocator.traits.types, allocator.traits.members, allocator.traits.other
related: pointer.traits, default.allocator, allocator.uses, mem.poly.allocator.class, allocator.adaptor, container.alloc.reqmts, allocator.requirements.general, specialized.construct
tags: 标准库, 分配器, allocator_traits, POCMA, 容器
papers: P2652R2, P0401R6
updated: 2026-10-18
---

C++98 的分配器要求（*Allocator* requirements）是一张很长的清单：`pointer`、`const_pointer`、`reference`、`const_reference`、`size_type`、`difference_type`、`rebind<U>::other`、`address()`、`construct()`、`destroy()`、`max_size()`……每写一个自定义分配器都要把这些样板抄一遍，而其中绝大部分对 99% 的分配器都是同一个答案。更糟的是，C++98 还允许实现**假设**同类型分配器总是相等，这让"有状态分配器"实际上不可用。

C++11 的解决方案分两步：

1. 把分配器要求（[[allocator.requirements.general]]）缩减为**最小集合**：`value_type`、`allocate`、`deallocate`、可从 `A<U>` 转换构造、`==`；
2. 引入 `allocator_traits<Alloc>`，对每个可选成员给出**默认值**。标准容器**只通过** `allocator_traits` 访问分配器（[[container.alloc.reqmts]]），从不直接调用 `a.construct(...)`。

于是 `allocator_traits` 成了容器与分配器之间的**适配层**：分配器作者只写自己真正关心的部分，其余由 traits 补全。它也是"有状态分配器"一等公民化的载体——`propagate_on_container_*` 与 `is_always_equal` 这几个成员决定了容器在复制、移动、交换时如何对待分配器。

## 概述（[allocator.traits.general]）

¶1 有三句话，每句都有分量：

- `allocator_traits` 为所有分配器类型提供统一接口。
- **分配器不能是非类类型**，即使 `allocator_traits` 能补全它所需的全部接口。注 1 给出理由：这样总能从分配器**派生**一个类——[[allocator.adaptor]] 的 `scoped_allocator_adaptor` 就派生自外层分配器，标准库实现也普遍通过派生（或 `[[no_unique_address]]`）对空分配器做空基类优化。
- 若程序声明 `allocator_traits` 的显式或偏特化，程序 {{ifndr}}。这条由 [[P2652R2]] 在 C++23 加入：容器实现依赖 `allocator_traits` 的精确行为（例如 `construct` 一定落到 `a.construct` 或 `construct_at`），允许用户特化等于允许用户偷偷改变容器的元素构造方式。要定制行为，应改分配器本身。

## 成员类型（[allocator.traits.types]）

每个成员都遵循同一模式：若 `Alloc` 有同名成员（在 [[temp.deduct]] 的意义上"有效且表示类型"），就用它；否则用默认值。

| 成员 | 默认值 | 说明 |
|---|---|---|
| `pointer`（¶1） | `value_type*` | 花式指针的入口 |
| `const_pointer`（¶2） | `pointer_traits<pointer>::rebind<const value_type>` | 都从 `pointer` 经 [[pointer.traits]] 推出 |
| `void_pointer`（¶3） | `pointer_traits<pointer>::rebind<void>` | |
| `const_void_pointer`（¶4） | `pointer_traits<pointer>::rebind<const void>` | |
| `difference_type`（¶5） | `pointer_traits<pointer>::difference_type` | |
| `size_type`（¶6） | `make_unsigned_t<difference_type>` | |
| `propagate_on_container_copy_assignment`（¶7） | `false_type` | POCCA |
| `propagate_on_container_move_assignment`（¶8） | `false_type` | POCMA |
| `propagate_on_container_swap`（¶9） | `false_type` | POCS |
| `is_always_equal`（¶10） | `is_empty<Alloc>::type` | 空类分配器被认为总相等 |
| `rebind_alloc<T>`（¶11） | `Alloc::rebind<T>::other`，否则把 `Alloc<U, Args...>` 的首实参换成 `T`；都不行则实例化 {{ill-formed}} | 与 `pointer_traits::rebind` 同一套启发式 |
| `rebind_traits<T>` | `allocator_traits<rebind_alloc<T>>` | |

`value_type` 没有默认值——它是最小分配器唯一必须提供的类型成员。

**`rebind_alloc` 为什么重要？** 容器很少分配 `value_type` 本身：`std::list<int, A>` 分配的是 `__list_node<int>`，`std::map` 分配树节点，`shared_ptr` 的 `allocate_shared` 分配控制块。它们都通过 `rebind_alloc<Node>` 从用户给的 `A<int>` 得到 `A<Node>`，再从 `A<int>` 对象**转换构造**出 `A<Node>` 对象。这就是为什么最小分配器必须支持 `template<class U> A(const A<U>&)`。

```cpp title="minimal-allocator.cpp" ok
#include <memory>
#include <vector>
#include <cstdio>
#include <new>

// C++11 起的"最小分配器"：只需 value_type、allocate、deallocate、转换构造与 ==
template<class T>
struct Mini {
    using value_type = T;
    int id;
    explicit Mini(int i) : id(i) {}
    template<class U> Mini(const Mini<U>& o) noexcept : id(o.id) {}
    T* allocate(std::size_t n) {
        std::printf("  [%d] allocate %zu\n", id, n);
        return static_cast<T*>(::operator new(n * sizeof(T)));
    }
    void deallocate(T* p, std::size_t) noexcept { ::operator delete(p); }
    friend bool operator==(const Mini& a, const Mini& b) { return a.id == b.id; }
};

using Tr = std::allocator_traits<Mini<int>>;
static_assert(std::is_same_v<Tr::pointer, int*>);
static_assert(std::is_same_v<Tr::size_type, std::size_t>);
static_assert(std::is_same_v<Tr::rebind_alloc<long>, Mini<long>>);
static_assert(!Tr::propagate_on_container_move_assignment::value);   // 默认 false_type
static_assert(!Tr::is_always_equal::value);                          // Mini 不是空类

int main() {
    std::vector<int, Mini<int>> a({1, 2, 3}, Mini<int>(1));
    std::vector<int, Mini<int>> b(Mini<int>(2));
    std::puts("b = std::move(a):");
    b = std::move(a);   // POCMA 为假且分配器不等：不能偷缓冲区，只能用 b 的分配器重新分配并逐元素移动
    std::printf("  b.size()=%zu, b alloc id=%d\n", b.size(), b.get_allocator().id);
}
```

输出显示移动赋值时 `[2] allocate 3`——"移动"变成了分配加逐元素移动。

## 有状态分配器的三条传播规则

POCCA/POCMA/POCS 的含义由容器要求定义（[[container.reqmts]] ¶64–¶65、[[container.alloc.reqmts]]）：容器的分配器**只能**通过赋值或 `swap` 被替换，而且只有对应的 `propagate_on_container_*::value` 为真时才替换。

### 复制赋值：POCCA

`a = b` 时：

- POCCA 为真：`a` 的分配器被替换为 `b` 的分配器副本（若二者不等，`a` 必须先用**旧**分配器释放旧存储）；
- POCCA 为假（默认）：`a` 保留自己的分配器，用它分配新存储并复制元素。

**直觉**：分配器表示"这块内存属于谁"。一个从 arena A 分配的容器，被赋值后通常应**继续**留在 arena A——所以默认是不传播。

### 移动赋值：POCMA 与 `is_always_equal`

`a = std::move(b)` 时有三种情形：

1. POCMA 为真：先释放 `a` 的存储，替换分配器，然后**偷走** `b` 的缓冲区。O(1)，不抛异常。
2. POCMA 为假，但 `a.get_allocator() == b.get_allocator()`：两个分配器可以互相释放对方的内存，照样偷缓冲区。O(1)。
3. POCMA 为假且分配器不等：**不能偷**——`a` 的分配器无法释放 `b` 的内存。只能用 `a` 的分配器重新分配，并对元素逐个移动构造或移动赋值（[[container.alloc.reqmts]] 对 `a = rv` 的前置条件因此要求元素 *Cpp17MoveInsertable* 和 *Cpp17MoveAssignable*）。O(n)，可能抛异常。

第 3 种情形是运行期才知道的，所以**容器移动赋值能不能声明 `noexcept`** 取决于编译期能否排除它。这正是 `is_always_equal`（C++17）的用途：若 POCMA 为真**或** `is_always_equal` 为真，第 3 种情形不可能发生。例如 [[vector.overview]] 中 `vector` 的移动赋值声明为

```cpp
constexpr vector& operator=(vector&& x)
  noexcept(allocator_traits<Allocator>::propagate_on_container_move_assignment::value ||
           allocator_traits<Allocator>::is_always_equal::value);
```

[[indirect]]、[[polymorphic]] 的移动赋值也是同样的 `noexcept` 规格。`is_always_equal` 默认取 `is_empty<Alloc>`：没有状态的分配器的所有实例显然等价。

`std::allocator` 的 POCMA 是 `true_type`（[[default.allocator]]）——即使它是空类、总相等，显式设置 POCMA 也能让容器实现走最简单的"偷缓冲区"路径。

### 交换：POCS

`a.swap(b)`（[[container.reqmts]] ¶65）：

- POCS 为真：分配器也被交换；
- POCS 为假：分配器**不**交换，而且**除非** `a.get_allocator() == b.get_allocator()`，否则行为未定义。

这是一个真实的 {{ub}} 陷阱：`pmr` 容器的分配器 POCS 为假（[[mem.poly.allocator.class]]），交换两个使用不同资源的 `pmr::vector` 就是 UB。

```cpp title="pmr-swap-ub.cpp" ub
#include <vector>
#include <memory_resource>

int main() {
    std::pmr::monotonic_buffer_resource r1, r2;
    std::pmr::vector<int> a({1, 2}, &r1), b({3}, &r2);
    a.swap(b);   // UB：POCS 为假且分配器不相等
}
```

本机实测：默认构建下"正常运行"（两个 vector 交换了缓冲区，但各自的分配器没变——之后 `a` 会用 `r1` 去释放来自 `r2` 的内存）；在 libc++ 加固模式 `extensive`/`debug` 下，`vector::swap` 断言"Either propagate_on_container_swap must be true or the allocators must compare equal"并终止。

!!! summary "三条规则一览"
    | 操作 | 成员 | 为假（默认）时 | 为假且分配器不等的代价 |
    |---|---|---|---|
    | 复制赋值 | POCCA | 保留左操作数的分配器 | 无额外代价 |
    | 移动赋值 | POCMA | 保留左操作数的分配器 | 退化为逐元素移动，O(n)，可能抛异常 |
    | 交换 | POCS | 不交换分配器 | **UB** |

### 复制构造：`select_on_container_copy_construction`（¶9）

复制**构造**时没有"左操作数原有的分配器"，容器调用 `select_on_container_copy_construction(rhs.get_allocator())` 来决定新容器的分配器（[[container.reqmts]] ¶64）。默认返回 `rhs`（即复制分配器）；`polymorphic_allocator` 把它定制为返回**默认构造**的分配器（即 `get_default_resource()`），意为"复制品不应继承原件的 arena"。

## 静态成员函数（[allocator.traits.members]）

| 函数 | 若 `Alloc` 提供 | 否则 |
|---|---|---|
| `allocate(a, n)`（¶1） | `a.allocate(n)`（必须提供） | — |
| `allocate(a, n, hint)`（¶2） | `a.allocate(n, hint)` | `a.allocate(n)` |
| `allocate_at_least(a, n)`（¶3） | `a.allocate_at_least(n)` | `{a.allocate(n), n}` |
| `deallocate(a, p, n)`（¶4–¶5） | `a.deallocate(p, n)`；*Throws*：无 | — |
| `construct(a, p, args...)`（¶6） | `a.construct(p, args...)` | `construct_at(p, args...)` |
| `destroy(a, p)`（¶7） | `a.destroy(p)` | `destroy_at(p)` |
| `max_size(a)`（¶8） | `a.max_size()` | `numeric_limits<size_type>::max() / sizeof(value_type)` |
| `select_on_container_copy_construction(rhs)`（¶9） | `rhs.select_on_container_copy_construction()` | `rhs` |

几个要点：

**`construct` 与 `destroy` 的默认值。** 默认落到 `construct_at`/`destroy_at`（[[specialized.construct]]），也就是 placement new 与伪析构调用；全部是 `constexpr`。这条规则让 C++20 的 `constexpr std::vector` 成为可能：`std::allocator` 本身没有 `construct` 成员（C++20 移除），常量求值时容器通过 `allocator_traits::construct` → `construct_at` 构造元素。

注意 `construct` 的第二个形参是 `T*`，不是 `pointer`：即使分配器使用花式指针，构造时也传裸指针（容器用 `to_address` 转换，见 [[pointer.traits]]）。

**为什么要让分配器能定制 `construct`？** 这是 uses-allocator 构造（[[allocator.uses]]）的挂钩点：`polymorphic_allocator::construct` 和 `scoped_allocator_adaptor::construct` 在这里把自己"注入"元素的构造函数。另一个常见用途是**默认初始化分配器**：重写 `construct(U* p)`（无额外实参）为 `::new(p) U`，让 `vector<double, A>(n)` 不对元素做值初始化清零。

**`allocate_at_least`（¶3）。** C++23 由 [[P0401R6]] 引入：分配器可以返回**比请求更多**的空间，以及实际数量。底层 `malloc` 实现通常按尺寸档位（size class）取整分配，`vector` 若能知道多出来的容量，就可以直接把它算进 `capacity()`，避免下一次 `push_back` 时不必要的重分配。返回类型 `allocation_result<pointer, size_type>` 是只有 `ptr` 和 `count` 两个数据成员的聚合；[allocator.traits.other] ¶1 规定它没有任何其他基类或成员，因此可以对它用结构化绑定。默认实现只是 `{a.allocate(n), n}`。

**`deallocate` 的 *Throws*：Nothing。** 分配器的 `deallocate` 不得抛出异常——容器在析构函数和异常清理路径上调用它。

**`max_size` 的默认值** 只是理论上限；容器实现通常还会把它与 `numeric_limits<difference_type>::max()` 取较小值，因为元素个数必须能用迭代器差值表示。

## 思考题

<details markdown="1">
<summary>1. 一个有状态的 arena 分配器，想让容器移动赋值是 `noexcept` 且 O(1)，有哪些选择？代价是什么？</summary>

- 设 POCMA 为 `true_type`：移动赋值时分配器跟着走。代价是被赋值的容器"搬家"到了另一个 arena——如果你依赖"容器 X 的内存一定在 arena A 里"（例如之后整体释放 A），这会打破该假设。
- 设 `is_always_equal` 为 `true_type`：只有当所有实例确实可以互相释放内存时才正确，例如它们共享一个全局 arena。对真正有状态的分配器撒这个谎，容器会偷来对方的缓冲区再用自己的分配器去释放，导致 UB。
- 都不设：接受 O(n) 和可能抛出。`pmr` 就选择了这条路——`polymorphic_allocator` 的 POCMA 为假、`is_always_equal` 为假，因此 `pmr::vector` 的移动赋值不是 `noexcept`。
</details>

<details markdown="1">
<summary>2. 为什么 `is_always_equal` 的默认值是 `is_empty<Alloc>`，而不是 `true_type`？</summary>

因为空类没有状态，同类型的两个实例在任何可观察意义上都无法区分，"总相等"是安全的推断。非空类可能有状态（指向 arena 的指针），默认为真会让容器在移动赋值和交换时错误地偷缓冲区。反过来，非空却总相等的分配器（例如带一个调试计数器但共用全局堆）必须**显式**声明 `is_always_equal = true_type`。
</details>

<details markdown="1">
<summary>3. 能否特化 `std::allocator_traits<MyAlloc>` 来给它补一个 `construct`？</summary>

不能。¶1 规定声明 `allocator_traits` 的显式或偏特化是 {{ifndr}}（C++23 起）。正确做法是给 `MyAlloc` 本身加 `construct` 成员，`allocator_traits::construct` 会自动优先调用它。
</details>

## 小结

- `allocator_traits` 把最小分配器补全为完整接口；容器只通过它访问分配器；禁止用户特化（{{ifndr}}）。
- 类型成员：`pointer` 默认 `value_type*`，其余指针类型经 `pointer_traits::rebind` 推出；`size_type` 由 `difference_type` 推出；`rebind_alloc` 用于分配节点。
- 传播：POCCA/POCMA/POCS 默认为假；移动赋值在"不传播且不等"时退化为逐元素移动；交换在"不传播且不等"时是 UB；`is_always_equal` 默认为 `is_empty`，决定容器移动操作能否 `noexcept`。
- `construct`/`destroy` 默认是 `construct_at`/`destroy_at`，这是 uses-allocator 构造与 `constexpr` 容器的挂钩点。
- `allocate_at_least` 让分配器报告实际可用容量。
