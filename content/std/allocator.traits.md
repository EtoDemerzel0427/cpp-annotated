---
title: 分配器特征
summary: allocator_traits 是容器访问分配器的唯一接口，它给分配器没写的成员补上默认值，并决定容器赋值和交换时分配器是否跟着走。
status: done
covers: allocator.traits.general, allocator.traits.types, allocator.traits.members, allocator.traits.other
related: pointer.traits, default.allocator, allocator.uses, mem.poly.allocator.class, allocator.adaptor, container.alloc.reqmts, allocator.requirements.general, specialized.construct
tags: 标准库, 分配器, allocator_traits, POCMA, 容器
papers: P2652R2, P0401R6
updated: 2026-10-19
---

!!! tldr
    - 一个分配器只需提供 `value_type`、`allocate`、`deallocate`、转换构造和 `==`；其余成员由 `allocator_traits` 补上默认值，容器只通过 `allocator_traits` 使用分配器。
    - 三个 `propagate_on_container_*` 成员决定复制赋值、移动赋值、交换时分配器是否随之替换，默认都不替换。
    - 移动赋值时分配器既不传播又不相等，容器就不能接管对方的缓冲区，只能逐个移动元素；交换时出现这种情况是未定义行为。
    - `is_always_equal` 默认是 `is_empty<Alloc>`，它和 POCMA 一起决定容器的移动赋值能否声明为 `noexcept`。
    - `construct`/`destroy` 默认调用 `construct_at`/`destroy_at`；分配器可以自己定义它们，uses-allocator 构造就靠这一点。不允许特化 `allocator_traits`。

## 最小分配器

```cpp run ok
#include <cstdio>
#include <memory>
#include <new>
#include <type_traits>
#include <vector>

// 最小分配器：value_type、allocate、deallocate、转换构造、==
template<class T>
struct Mini {
  using value_type = T;
  int id;
  explicit Mini(int i) : id(i) {}
  template<class U>
  Mini(const Mini<U>& o) noexcept : id(o.id) {}
  T* allocate(std::size_t n) {
    std::printf("  [%d] allocate %zu\n", id, n);
    return static_cast<T*>(::operator new(n * sizeof(T)));
  }
  void deallocate(T* p, std::size_t) noexcept {
    ::operator delete(p);
  }
  friend bool operator==(const Mini& a, const Mini& b) {
    return a.id == b.id;
  }
};

using Tr = std::allocator_traits<Mini<int>>;
static_assert(std::is_same_v<Tr::pointer, int*>);
static_assert(std::is_same_v<Tr::size_type, std::size_t>);
static_assert(std::is_same_v<Tr::rebind_alloc<long>, Mini<long>>);
static_assert(!Tr::propagate_on_container_move_assignment::value);
static_assert(!Tr::is_always_equal::value);   // Mini 不是空类

int main() {
  std::vector<int, Mini<int>> a({1, 2, 3}, Mini<int>(1));
  std::vector<int, Mini<int>> b(Mini<int>(2));
  std::puts("b = std::move(a):");
  b = std::move(a);   // 不能接管 a 的缓冲区
  std::printf("  b.size()=%zu, b alloc id=%d\n", b.size(),
              b.get_allocator().id);
}
```

本机输出：

```text
  [1] allocate 3
b = std::move(a):
  [2] allocate 3
  b.size()=3, b alloc id=2
```

`Mini` 没有写 `pointer`、`size_type`、`construct` 等成员，`allocator_traits` 给它们补上了默认值，`vector` 照样能用。最后一行的移动赋值没有接管 `a` 的缓冲区，而是用 `b` 的分配器重新分配了一次。原因在于分配器的传播规则，见下文。

C++98 的分配器要求是一长串必须手写的成员，而且允许实现假设同类型的分配器总是相等，有状态的分配器实际上无法使用。C++11 把分配器要求缩减到上面这几项（[[allocator.requirements.general]]），引入 `allocator_traits` 补全其余部分，并规定标准容器只通过它访问分配器（[[container.alloc.reqmts]]）。

## 概述 [allocator.traits.general]

¶1 有三条规定：

- `allocator_traits` 为所有分配器类型提供统一的接口。
- 分配器必须是类类型，即使 `allocator_traits` 能补全它需要的全部接口。注 1 说明理由：这样总能从分配器派生。`scoped_allocator_adaptor`（[[allocator.adaptor]]）就派生自外层分配器，库实现也常靠派生或 `[[no_unique_address]]` 让空分配器不占空间。
- 程序声明 `allocator_traits` 的显式特化或偏特化，是 {{ifndr}}（非良构，不要求诊断）。这条由 [[P2652R2]] 在 C++23 加入。容器依赖 `allocator_traits` 的确切行为，要定制行为应该改分配器本身。

## 成员类型 [allocator.traits.types]

每个成员类型的规则都一样：如果 `Alloc` 有同名的成员类型，就用它；否则用默认值。

| 成员 | 默认值 |
|---|---|
| ¶1 `pointer` | `value_type*` |
| ¶2 `const_pointer` | `pointer_traits<pointer>::rebind<const value_type>` |
| ¶3 `void_pointer` | `pointer_traits<pointer>::rebind<void>` |
| ¶4 `const_void_pointer` | `pointer_traits<pointer>::rebind<const void>` |
| ¶5 `difference_type` | `pointer_traits<pointer>::difference_type` |
| ¶6 `size_type` | `make_unsigned_t<difference_type>` |
| ¶7 `propagate_on_container_copy_assignment` | `false_type` |
| ¶8 `propagate_on_container_move_assignment` | `false_type` |
| ¶9 `propagate_on_container_swap` | `false_type` |
| ¶10 `is_always_equal` | `is_empty<Alloc>::type` |
| ¶11 `rebind_alloc<T>` | `Alloc::rebind<T>::other`；否则把 `Alloc<U, Args...>` 的第一个实参换成 `T`；都不行则非良构 |

几个指针类型都从 `pointer` 经 [[pointer.traits]] 推出，所以分配器只要写一个花式指针 `pointer`，其余的就都有了。`value_type` 没有默认值，它是分配器必须提供的唯一类型成员。三个传播成员常缩写为 POCCA、POCMA、POCS。

`rebind_alloc` 用得很多，因为容器很少分配 `value_type` 本身。`std::list<int, A>` 分配的是链表节点，`std::map` 分配树节点，`allocate_shared` 分配控制块。它们用 `rebind_alloc<Node>` 从 `A<int>` 得到 `A<Node>` 类型，再从手里的 `A<int>` 对象转换构造出一个 `A<Node>` 对象。所以分配器必须支持 `template<class U> A(const A<U>&)`。

## 分配器的传播

容器的分配器只能在赋值或 `swap` 时被替换，而且只有相应的 `propagate_on_container_*::value` 为真时才替换（[[container.reqmts#64]]）。分配器代表这块内存属于谁：从 arena A 分配的容器被赋值之后，通常应该仍然留在 arena A，所以默认是不传播。

### 复制赋值

`a = b` 时，如果 POCCA 为真，`a` 的分配器替换为 `b` 的分配器的副本；两者不相等时，`a` 要先用旧分配器释放旧存储。POCCA 为假时，`a` 保留自己的分配器，用它分配新存储并复制元素。

### 移动赋值

`a = std::move(b)` 有三种情形：

1. POCMA 为真：释放 `a` 的存储，替换分配器，接管 `b` 的缓冲区。常数时间，不抛异常。
2. POCMA 为假，但两个分配器相等：相等意味着一个可以释放另一个分配的内存，所以照样接管缓冲区。
3. POCMA 为假且分配器不相等：`a` 的分配器不能释放 `b` 的内存，不能接管。只能用 `a` 的分配器重新分配，再逐个移动元素。线性时间，可能抛异常。开头的例子就是这种情形。

情形 3 要到运行期比较分配器才知道。如果想把移动赋值声明为 `noexcept`，就要在编译期排除它。POCMA 为真，或者 `is_always_equal` 为真，情形 3 都不可能发生。所以 `vector` 的移动赋值这样声明（[[vector.overview]]），`indirect`、`polymorphic` 的移动赋值也一样：

```cpp
constexpr vector& operator=(vector&& x)
  noexcept(allocator_traits<Allocator>::propagate_on_container_move_assignment::value ||
           allocator_traits<Allocator>::is_always_equal::value);
```

`is_always_equal` 默认取 `is_empty<Alloc>`：没有数据成员的分配器，所有实例都没有区别。`std::allocator` 是空类，同时还把 POCMA 设为 `true_type`（[[default.allocator]]）。

### 交换

`a.swap(b)` 时，POCS 为真则分配器也交换。POCS 为假则分配器不交换，而且如果两者不相等，行为未定义（[[container.reqmts#65]]）。

```cpp run ub
#include <memory_resource>
#include <vector>

int main() {
  std::pmr::monotonic_buffer_resource r1, r2;
  std::pmr::vector<int> a({1, 2}, &r1), b({3}, &r2);
  a.swap(b);   // UB: POCS 为假且分配器不相等
}
```

`polymorphic_allocator` 没有定义传播成员，POCS 取默认的假（[[mem.poly.allocator.class]]）。所以交换两个使用不同资源的 `pmr::vector` 是未定义行为。本机默认构建下程序正常结束，但两个 vector 交换了缓冲区而没有交换分配器，之后 `a` 会用 `r1` 去释放来自 `r2` 的内存。加上 `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_EXTENSIVE` 后，程序在 `swap` 处陷入并终止。

| 操作 | 成员 | 默认（假）时 | 不传播且分配器不相等的后果 |
|---|---|---|---|
| 复制赋值 | POCCA | 保留左边的分配器 | 无额外代价 |
| 移动赋值 | POCMA | 保留左边的分配器 | 逐个移动元素，线性时间，可能抛异常 |
| 交换 | POCS | 不交换分配器 | {{ub}} |

### 复制构造

复制构造时，新容器没有原来的分配器可以保留。容器调用 `select_on_container_copy_construction(rhs.get_allocator())` 决定新容器的分配器（¶9，[[container.reqmts#64]]），默认返回 `rhs` 的副本。`polymorphic_allocator` 把它定制为返回默认构造的分配器，也就是使用 `get_default_resource()`：副本不继承原件的 arena。

## 静态成员函数 [allocator.traits.members]

| 函数 | `Alloc` 提供时 | 否则 |
|---|---|---|
| ¶1 `allocate(a, n)` | `a.allocate(n)`（必须提供） | |
| ¶2 `allocate(a, n, hint)` | `a.allocate(n, hint)` | `a.allocate(n)` |
| ¶3 `allocate_at_least(a, n)` | `a.allocate_at_least(n)` | `{a.allocate(n), n}` |
| ¶4–¶5 `deallocate(a, p, n)` | `a.deallocate(p, n)`，不抛异常 | |
| ¶6 `construct(a, p, args...)` | `a.construct(p, args...)` | `construct_at(p, args...)` |
| ¶7 `destroy(a, p)` | `a.destroy(p)` | `destroy_at(p)` |
| ¶8 `max_size(a)` | `a.max_size()` | `numeric_limits<size_type>::max() / sizeof(value_type)` |
| ¶9 `select_on_container_copy_construction(rhs)` | `rhs.select_on_container_copy_construction()` | `rhs` |

### `construct` 与 `destroy`（¶6–¶7）

¶6–¶7 默认调用 `construct_at` 和 `destroy_at`（[[specialized.construct]]），它们都是 `constexpr`。C++20 移除了 `std::allocator::construct`，于是常量求值中的 `std::vector` 经 `allocator_traits::construct` 落到 `construct_at` 来构造元素。

`construct` 的第二个形参是 `T*`，不是 `pointer`。即使分配器使用花式指针，构造时传的也是普通指针，容器用 `to_address` 做转换（[[pointer.traits]]）。

分配器可以自己定义 `construct`，这是 uses-allocator 构造（[[allocator.uses]]）的入口：`polymorphic_allocator` 和 `scoped_allocator_adaptor` 在自己的 `construct` 里把分配器传给元素的构造函数。另一个常见用途是让 `construct(U* p)` 在没有额外实参时执行 `::new(p) U`，这样 `vector<double, A>(n)` 就不会把元素清零。

### `allocate_at_least`（¶3）

¶3 C++23 由 [[P0401R6]] 加入。底层的分配器通常按尺寸档位向上取整，实际拿到的空间比请求的多。`allocate_at_least` 让分配器把实际数量一并返回，`vector` 可以把多出来的部分算进 `capacity()`，减少之后的重新分配。

返回类型 `allocation_result<pointer, size_type>` 是一个聚合，只有 `ptr` 和 `count` 两个数据成员。[allocator.traits.other] ¶1 规定它没有其他基类和成员，所以可以对它使用结构化绑定。分配器不提供这个函数时，默认结果就是 `{a.allocate(n), n}`。

### 其余几个

¶5 `deallocate` 不抛异常。容器在析构函数和异常清理路径上调用它，不能在那里再抛出。

¶8 `max_size` 的默认值只是理论上限。容器实现通常还会把它和 `numeric_limits<difference_type>::max()` 取较小值，因为元素个数要能用迭代器之差表示。

## 思考题

!!! question "思考题 1"
    一个有状态的 arena 分配器，想让容器的移动赋值既是 `noexcept` 又是常数时间，有哪些做法？各自的代价是什么？

<details markdown="1">
<summary>答案</summary>

- 把 POCMA 设为 `true_type`：移动赋值时分配器随之替换。代价是被赋值的容器换到了另一个 arena。如果程序依赖容器 X 的内存一定在 arena A 里，比如之后整体释放 A，这个假设就被打破了。
- 把 `is_always_equal` 设为 `true_type`：只有所有实例确实能互相释放内存时才正确，例如它们共用一个全局 arena。对真正有状态的分配器这样声明，容器会接管对方的缓冲区，再用自己的分配器释放，导致未定义行为。
- 都不设：接受线性时间和可能的异常。`pmr` 选择的就是这条路，`polymorphic_allocator` 的 POCMA 和 `is_always_equal` 都为假，所以 `pmr::vector` 的移动赋值不是 `noexcept`。
</details>

!!! question "思考题 2"
    为什么 `is_always_equal` 的默认值是 `is_empty<Alloc>`，而不是 `true_type`？

<details markdown="1">
<summary>答案</summary>

空类没有状态，同类型的两个实例无法区分，推断为总是相等是安全的。非空类可能有状态，比如一个指向 arena 的指针；默认为真会让容器在移动赋值和交换时错误地接管缓冲区。反过来，有数据成员却总是相等的分配器（例如带一个调试计数器、共用全局堆）需要显式声明 `using is_always_equal = std::true_type;`。
</details>

!!! question "思考题 3"
    能否特化 `std::allocator_traits<MyAlloc>`，给它补一个 `construct`？

<details markdown="1">
<summary>答案</summary>

不能。¶1 规定程序声明 `allocator_traits` 的显式特化或偏特化是 {{ifndr}}。正确的做法是给 `MyAlloc` 本身加一个 `construct` 成员，`allocator_traits::construct` 会优先调用它。
</details>
