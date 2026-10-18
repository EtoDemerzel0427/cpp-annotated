---
title: inplace_vector
summary: C++26 的 inplace_vector——元素存放在对象内部、容量为编译期常量的动态大小连续容器；超容量抛 bad_alloc、try_* 返回 optional<reference>、unchecked_* 以前置条件换性能；平凡性如何从 T 传播；移动与 swap 为何线性；失效规则的空白；freestanding 支持
status: done
covers: *, inplace.vector.syn
related: vector, array, sequence.reqmts, container.requirements, container.requirements.general, freestanding.item
tags: 标准库, 容器, inplace_vector, C++26, freestanding
since: c++26
papers: P0843R14
updated: 2026-10-18
---

`std::inplace_vector<T, N>`（{{c++26}}，[[P0843R14]]）填补了 `array` 与 `vector` 之间的空档：**容量**像 `array` 一样是编译期常量 N、存储在对象内部；**大小**像 `vector` 一样在 0…N 之间变化。它不分配堆内存，因此不是分配器感知容器，并且大部分接口在 freestanding 实现中可用。

!!! warning "本地验证状态"
    截至本文编写时，本机 libc++（Homebrew clang 23）尚未提供 `<inplace_vector>`（`<version>` 中 `__cpp_lib_inplace_vector` 仍被注释掉），本机也没有 GCC。本页示例**未经本地编译验证**，因此不标判定；可借助"godbolt ↗"在支持它的标准库上运行。

## 概述（[inplace.vector.overview]）

¶1：`inplace_vector` 是**连续容器**；容量固定，元素存储在 `inplace_vector` 对象**自身**之内。

¶2：满足容器、可逆容器、连续容器、序列容器（含大部分可选操作）的要求；不提供 `push_front`、`prepend_range`、`pop_front`、`emplace_front`。注意清单里**没有**分配器感知容器——[[container.requirements.general]] 的 [container.alloc.reqmts] ¶1 明确把它和 `array` 一起排除。

¶3：对任意 N，迭代器满足 constexpr 迭代器要求。

!!! std
    Any member function of inplace_vector<T, N> that would cause the size to exceed N throws an exception of type bad_alloc.

    inplace_vector<T, N> 的任何成员函数，若会使大小超过 N，则抛出 bad_alloc 类型的异常。

¶4 选择 `bad_alloc` 而不是 `length_error` 或前置条件，是把"容量不够"统一视为"分配失败"：与 `vector` 在内存耗尽时的行为对齐，让同一份泛型代码对两者有相同的错误路径。

### 平凡性传播（¶5）

¶5 设 `IV` 为 `inplace_vector<T, N>`：

- N 为 0 时：`IV` 平凡可复制且为**空类**，`is_trivially_default_constructible_v<IV>` 为真；
- 否则：`T` 有平凡拷贝构造/移动构造，则 `IV` 也有；`T` 平凡可析构，则 `IV` 平凡可析构，并且若 `T` 的拷贝（移动）构造与拷贝（移动）赋值都平凡，`IV` 的拷贝（移动）赋值也平凡。

这意味着 `inplace_vector<int, 16>` 是平凡可复制的，可以 `memcpy`、可以放进共享内存或网络包里——即使它只有一部分元素是"活的"。实现上，存储通常是一个放在 union 里的元素数组（避免默认构造全部 N 个元素）加一个大小计数器；能否在保持平凡性的同时于常量求值中逐个开始元素的生命周期，是实现这一条款时最微妙的核心语言问题。

注意 N > 0 时**没有**保证平凡默认构造：默认构造必须把大小设为 0。

## 构造（[inplace.vector.cons]）

与 [[sequence.reqmts]] 的通用条目一致，只是**没有分配器参数**：`inplace_vector(n)`、`(n, value)`、迭代器区间、`from_range`、初始化器列表（¶1–¶11）。默认构造 `noexcept`。

`from_range` 构造有一条编译期检查：

!!! std
    *Mandates*: If ranges::size(rg) is a constant expression, then ranges::size(rg) ≤ N.

    若 ranges::size(rg) 是常量表达式，则它不得大于 N。

¶9 让"`std::array<int, 5>` 塞进 `inplace_vector<int, 4>`"在编译期就被拒绝，而运行期才知道大小的区间超容量时按 ¶4 抛 `bad_alloc`。

## 容量（[inplace.vector.capacity]）

- `capacity()` 与 `max_size()` 都是 **`static constexpr`**，返回 N（¶1）。
- `resize(sz)`/`resize(sz, c)`（¶2–¶7）：抛异常时对 `*this` 无效果。
- `reserve(n)` 是 `static constexpr` 的，**什么也不做**；只在 `n > capacity()` 时抛 `bad_alloc`（¶8–¶9）。`shrink_to_fit()` 是 `static constexpr noexcept` 的空操作（¶10）。保留它们是为了让 `inplace_vector` 能替换泛型代码里的 `vector`。

## 数据（[inplace.vector.data]）

`data()` 使 `[data(), data() + size())` 为有效区间，非空时 `data() == addressof(front())`，常数（¶1–¶2）。

## 修改器（[inplace.vector.modifiers]）

### 三套尾部插入接口

| 接口 | 满时的行为 | 返回 | 出处 |
|---|---|---|---|
| `push_back`、`emplace_back` | 抛 `bad_alloc` | `reference`（`back()`） | ¶4–¶7 |
| `try_push_back`、`try_emplace_back` | **无效果** | `optional<reference>`：满则 `nullopt` | ¶8–¶14 |
| `unchecked_push_back`、`unchecked_emplace_back` | **前置条件** `size() < capacity()`，违反即 {{ub}} | `reference` | ¶15–¶18 |

```cpp title="inplace-vector.cpp" run
#include <inplace_vector>
#include <cassert>

int main() {
  std::inplace_vector<int, 2> v;
  v.push_back(1);
  int& r = v.emplace_back(2);         // 返回 reference（与 vector 不同，push_back 也返回引用）
  assert(r == 2 && v.size() == v.capacity());

  auto opt = v.try_push_back(3);      // 满了：不抛异常，返回 nullopt，容器不变
  assert(!opt && v.size() == 2);

  try { v.push_back(3); } catch (const std::bad_alloc&) { /* ¶4 */ }

  static_assert(std::inplace_vector<int, 2>::capacity() == 2);   // static constexpr
}
```

几点细节：

- `push_back` 返回 `reference`——`vector::push_back` 返回 `void`。
- `try_*` 返回 `optional<reference>`，即 C++26 的 `optional<T&>`。¶12：除元素初始化抛出的异常外不抛，满时不抛 `bad_alloc`。
- `try_emplace_back` 用 `vals…` **直接非列表初始化**新元素（¶10）。
- `unchecked_*` 被规定为 `*try_emplace_back(…)` / `*try_push_back(…)`（¶16、¶18）——对空 `optional` 解引用本身就违反 `optional::operator*` 的前置条件。

三套接口对应三种错误模型：异常（默认）、返回值（嵌入式/禁用异常的环境）、契约（调用者已证明有空间，追求零检查）。

### 其他插入与异常保证（¶1–¶3）

¶1 定义 n：对 `append_range` 是调用前的 `size()`，否则是 `distance(begin, position)`（即插入点之前的元素个数）。¶2：复杂度线性于插入个数加到末尾的距离。¶3：

- 抛出者不是 `T` 的拷贝/移动构造、（移动）赋值，也不是 `InputIterator` 的操作：**无效果**；
- 否则：`size() ≥ n`，并且 `begin() + [0, n)` 中的元素**未被修改**。

这条保证比 `vector` 的中间插入更强、也更具体：插入点之前的前缀永远完好，容器可能多出一部分已插入的元素。注意 `append_range` 超容量的情形：它可能在抛 `bad_alloc` 之前已经追加了一部分元素——¶3 只保证原有的 n 个元素不变。

### 擦除与 `swap`（¶19–¶23）

- `erase`/`pop_back`：使擦除点及之后的迭代器和引用失效；除 `T` 的赋值外不抛；析构次数 = 擦除个数，赋值次数 = 擦除点之后的元素个数（¶19–¶21）。
- `swap(x)`：`noexcept(N == 0 || (is_nothrow_swappable_v<T> && is_nothrow_move_constructible_v<T>))`；前置条件为 `T` 满足 *Cpp17MoveConstructible*，且前 `min(size(), x.size())` 对元素可交换（¶22–¶23）。元素在对象内部，交换只能逐个进行：短的那部分 `swap`，多出的部分移动构造过去再销毁——所以是**线性**的，这也是 [[container.requirements.general]] 把 `inplace_vector` 与 `array` 一起列为"移动和 `swap` 线性"的原因。

### 失效规则的一处空白

[inplace.vector.modifiers] 对**擦除**给出了失效规则（¶19），但对**插入**没有任何一句关于迭代器失效的规定。[[container.requirements.general]] ¶67 的总则说"除非另有规定（显式写出或通过用其他函数定义），容器成员函数不得使迭代器失效、也不得改变元素的值"——而中间插入显然要改变插入点之后元素的值。合理的解读是：插入的效果本身（"在 p 之前插入"）就构成了"另有规定"，插入点及之后的迭代器虽然仍指向有效内存（存储在对象内部，永不重新分配），但不再指向原来的元素；插入点之前的迭代器和引用不受影响。实践中可以把它当作"永不重新分配的 `vector`"来推理。

## 擦除（[inplace.vector.erasure]）

`erase(c, value)` 与 `erase_if(c, pred)` 等价于 erase-remove 惯用法，返回 `size_t`。

## freestanding

`<inplace_vector>` 是"大部分 freestanding"的：会抛 `bad_alloc` 的成员（`push_back`、`emplace_back`、`insert`、`resize`、`reserve`、`at`、带大小的构造函数等）被标为 *freestanding-deleted*（[[freestanding.item]]），而 `try_*`、`unchecked_*`、`erase`、`pop_back`、元素访问都保留。于是在没有异常支持的环境中，`inplace_vector` 的推荐用法就是 `try_push_back` + 检查返回值。

## 与 `vector`、`array` 的选择

- 上限确定且较小、不想要堆分配（实时系统、嵌入式、热路径上的临时缓冲）：`inplace_vector`。
- 大小固定：`array`。
- 大小无界或很大（`inplace_vector` 的 `sizeof` 至少是 `N * sizeof(T)`，放在栈上可能溢出）：`vector`。

## 小结

- 存储在对象内部、容量 N 是 `static constexpr`；不是分配器感知容器；N = 0 时为空的平凡类型，其余情况下平凡性随 `T` 传播。
- 超容量：普通接口抛 `bad_alloc`，`try_*` 返回 `nullopt`，`unchecked_*` 是前置条件违例。
- `push_back`/`emplace_back` 返回引用；`reserve`/`shrink_to_fit` 是 `static` 空操作。
- 移动构造与 `swap` 线性；插入抛异常时前缀保持不变。
