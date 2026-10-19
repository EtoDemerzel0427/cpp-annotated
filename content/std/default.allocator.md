---
title: 默认分配器 std::allocator
summary: std::allocator<T> 的契约：存储来自 ::operator new 但调用的时机和次数未指定，allocate 只开始数组对象的生命周期而不构造元素，deallocate 的大小必须与分配时一致，常量求值中的分配必须当场释放。
status: done
covers: default.allocator.general, allocator.members, allocator.globals
related: allocator.traits, basic.stc.dynamic, new.delete, expr.new, expr.const, intro.object, basic.life
tags: 标准库, 分配器, allocator, constexpr
papers: P0784R7, P0401R6, P2868R3, P0593R6
updated: 2026-10-19
---

!!! tldr
    - `std::allocator<T>` 只有 `allocate`、`allocate_at_least`、`deallocate` 和几个类型成员，其余接口都由 `allocator_traits` 补全。它是空类，所有实例都相等。
    - `allocate(n)` 开始一个 `T[n]` 数组对象的生命周期，但不构造任何元素；元素要用 `construct_at` 逐个构造。
    - `deallocate(p, n)` 的 `n` 必须等于分配时请求的数量，否则是未定义行为，因为它可能被原样传给带大小的 `operator delete`。
    - 存储来自 `::operator new`，但标准不规定调用的时机和次数，实现可以合并或省略分配。
    - C++20 起这些函数是 `constexpr` 的；常量求值中分配的内存必须在同一次求值内释放。

## 今天的完整定义

```cpp
template<class T> class allocator {
public:
  using value_type                             = T;
  using size_type                              = size_t;
  using difference_type                        = ptrdiff_t;
  using propagate_on_container_move_assignment = true_type;

  constexpr allocator() noexcept;
  constexpr allocator(const allocator&) noexcept;
  template<class U> constexpr allocator(const allocator<U>&) noexcept;
  constexpr ~allocator();
  constexpr allocator& operator=(const allocator&) = default;

  constexpr T* allocate(size_t n);
  constexpr allocation_result<T*> allocate_at_least(size_t n);
  constexpr void deallocate(T* p, size_t n);
};
```

`pointer`、`rebind`、`construct`、`max_size` 这些成员都不在这里，它们由 [[allocator.traits]] 的默认规则给出。`std::allocator` 本身就是一个最小分配器。

### 概述 [default.allocator.general]

¶1 `allocator` 的所有特化都满足分配器完整性要求（[[allocator.requirements.completeness]]）：即使 `T` 是不完整类型，`allocator<T>` 也是完整类型。C++17 允许 `vector`、`list`、`forward_list` 的元素类型在实例化类定义时不完整，就依赖这一条。

¶2 对任何 `T`，`allocator_traits<allocator<T>>::is_always_equal::value` 为真。

¶2 说的是 traits 的值，不是 `allocator` 的成员。这个值来自 traits 的默认规则：`allocator` 是空类，`is_empty<allocator<T>>` 为真。C++17 曾给 `allocator` 加了一个 `is_always_equal` 成员类型，问题在于它会被派生类继承：从 `std::allocator` 派生、带有状态的分配器会错误地声称自己总是相等。这个成员在 C++23 被弃用，C++26 由 [[P2868R3]] 移除。

POCMA（`propagate_on_container_move_assignment`）是 `true_type`。对一个总是相等的分配器，这看起来多余；但有了它，容器的移动赋值可以直接释放自己的存储、接管对方的缓冲区，不必比较分配器。

### 被移除的成员

| 成员 | 状态 |
|---|---|
| `pointer`、`const_pointer`、`reference`、`const_reference`、`rebind`、`address`、`max_size`、`construct`、`destroy`、`allocate(n, hint)` | C++17 弃用，C++20 移除 |
| 显式特化 `allocator<void>` | C++17 弃用，C++20 移除；主模板仍可以实例化 `allocator<void>` 的类定义 |
| `is_always_equal` | C++23 弃用，C++26 移除 |

这些成员都能从 `allocator_traits` 的默认值得到，留着反而会让用户绕过 traits 直接调用它们。

## `allocate` 给了你什么 [allocator.members]

```cpp run ok
#include <memory>
#include <string>

constexpr bool f() {
  std::allocator<std::string> a;
  std::string* p = a.allocate(2);   // 数组 string[2] 开始生命周期，元素没有
  std::construct_at(p, "x");        // 只构造 p[0]
  bool r = p[0] == "x";
  std::string* end = p + 2;         // OK: 尾后指针
  (void)end;                        // p[1] 从未构造，不能读写
  std::destroy_at(p);
  a.deallocate(p, 2);
  return r;
}
static_assert(f());

int main() {}
```

¶2 `T` 必须是完整类型，`allocate` 需要知道 `sizeof(T)`。

¶3 返回指向 `n` 个 `T` 的数组首元素的指针。

¶4 `numeric_limits<size_t>::max() / sizeof(T) < n` 时抛出 `bad_array_new_length`；无法取得存储时抛出 `bad_alloc`。

¶5 存储通过调用 `::operator new` 取得，但调用的时机和次数是未指定的。这个函数开始数组对象的生命周期，但不开始任何数组元素的生命周期。

¶5 的最后一句确定了 `allocate` 在对象模型（[[intro.object]]）里的位置：

- 数组对象存在，所以返回的 `T*` 指向一个数组元素，在 `[p, p + n]` 范围内做指针算术是合法的（[[expr.add]] 只允许在同一个数组对象内做指针算术）。这一句由 C++20 的 [[P0593R6]] 加入；在那之前，严格地说 `vector` 的实现一直在对一个不存在的数组做指针算术。
- 元素不存在，所以必须用 `construct_at` 或 `allocator_traits::construct` 逐个构造（[[basic.life]]）。读写还没构造的元素是 {{ub}}。

前一句说调用 `::operator new` 的时机和次数未指定，这给了实现合并或省略分配的自由，和 [[expr.new]] 允许省略或合并 *new-expression* 的分配调用一样。所以替换了全局 `operator new` 来计数时，计到的次数不一定和 `allocate` 的调用次数一致。libc++ 在常量求值之外调用的是 `__builtin_operator_new`，这个内建函数告诉 Clang，这次调用享有和 *new-expression* 一样的省略许可。

### 并发（¶1）

¶1 除析构函数外，从不同线程并发调用默认分配器的成员函数不会引入数据竞争。对同一块存储的分配和释放调用构成一个全序，每次释放都先于这个序中的下一次分配发生。

后一句的意思是：一块内存被一个线程释放、又被另一个线程分配到，前一个线程对它的所有写入对后一个线程可见，不构成数据竞争。这和 [[new.delete.dataraces]] 对 `operator new`、`operator delete` 的保证相同。

## `allocate_at_least`（¶6–¶9）{{c++23}}

¶7 `allocate_at_least(n)` 和 `allocate` 一样分配存储，但返回 `allocation_result<T*>{ptr, count}`，其中 `count >= n`（[[P0401R6]]）。用途见 [[allocator.traits]]：容器可以把多拿到的空间算进容量。¶6、¶8、¶9 的要求、异常和备注与 `allocate` 相同。

```cpp run ok
#include <cstdio>
#include <limits>
#include <memory>
#include <new>

int main() {
  std::allocator<int> a;
  auto [p, n] = a.allocate_at_least(5);   // 聚合，可以结构化绑定
  std::printf("asked 5, got %zu\n", n);   // libc++：5
  a.deallocate(p, 5);                     // 第二个实参可以取 [5, n] 中任意值

  try {
    (void)a.allocate(std::numeric_limits<std::size_t>::max() / 2);
  } catch (const std::bad_array_new_length&) {
    std::puts("bad_array_new_length");    // max / sizeof(int) < n
  }
  static_assert(std::allocator<int>() == std::allocator<long>());
}
```

标准允许 `count` 大于 `n`，但不要求。本机 libc++ 返回的正好是 5，因为底层的 `operator new` 无法报告实际分到的块大小。

## `deallocate` 的大小（¶10–¶12）

¶10 前置条件要求大小匹配：

- ¶10.1 如果 `p` 来自 `allocate_at_least`，设那次调用请求了 `req` 个、返回了 `ret`，那么 `p == ret.ptr`，并且 `req <= n <= ret.count`；
- ¶10.2 否则 `p` 来自 `allocate`，`n` 必须等于当初传给 `allocate` 的值。

违反它是 {{ub}}。C++14 起 `::operator delete` 有带大小的版本，实现可以把 `n * sizeof(T)` 直接传给它。tcmalloc、jemalloc 等分配器用这个大小直接确定尺寸档位，不再查元数据，传错大小会破坏堆。

¶11–¶12 `deallocate` 释放 `p` 所指的存储，使用 `::operator delete`，调用的时机未指定。

## 相等比较 [allocator.globals]

¶1 `operator==(const allocator<T>&, const allocator<U>&)` 总是返回 `true`，`!=` 由 C++20 的重写规则生成。`T` 不同的两个 `allocator` 也相等：经过 rebind 之后，一个可以释放另一个分配的内存。

## 常量求值中的 `std::allocator`

C++20 起 `allocate` 和 `deallocate` 是 `constexpr` 的（[[P0784R7]]），这是 `constexpr std::vector` 和 `std::string` 的基础。常量求值中的分配必须是**瞬时分配**（[[g:transient-allocation]]）：在同一次求值内释放，不能留到运行期（[[expr.const]]）。

```cpp run error
#include <memory>
constexpr int* leak() {
  std::allocator<int> a;
  int* p = a.allocate(1);
  std::construct_at(p, 7);
  return p;   // 没有在这次常量求值内释放
}
constexpr int* q = leak();   // error: 不是常量表达式
```

Clang 23 报告 `q` 必须由常量表达式初始化，并附注指向堆分配对象的指针不是常量表达式，同时指出分配发生的位置。

常量求值中能分配内存的只有 *new-expression*（调用可替换的全局分配函数）和 `std::allocator<T>::allocate`。自定义分配器想在常量求值中使用，内部必须委托给 `std::allocator`。

## 思考题

!!! question "思考题 1"
    从 `std::allocator<int>` 派生一个带计数器成员的分配器 `Counting<int>`。C++17 下 `allocator_traits<Counting<int>>::is_always_equal` 是什么？C++26 呢？

<details markdown="1">
<summary>答案</summary>

C++17 中 `std::allocator` 有成员 `using is_always_equal = true_type;`，`Counting` 继承了它，traits 优先采用 `Alloc::is_always_equal`，结果为真。这是错的：`Counting` 有状态，容器的移动赋值会直接接管对方的缓冲区。这正是这个成员被弃用并移除的原因。C++26 中继承不到这个成员，traits 退回到 `is_empty<Counting<int>>`，结果为假。
</details>

!!! question "思考题 2"
    调用 `a.deallocate(p, n)` 时把 `n` 写成 0 会怎样？

<details markdown="1">
<summary>答案</summary>

除非当初调用的就是 `allocate(0)`，否则违反 ¶10 的前置条件，是 {{ub}}。实践中，如果实现调用了带大小的 `operator delete(p, 0)`，按尺寸档位管理内存的分配器会把这块内存放进错误的空闲链表。
</details>
