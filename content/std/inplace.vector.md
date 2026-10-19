---
title: inplace_vector
summary: C++26 的 inplace_vector：容量是编译期常量、元素存放在对象内部的变长连续容器；装满后普通接口抛 bad_alloc，try_ 系列返回空 optional，unchecked_ 系列以前置条件换取零检查。
status: draft
covers: *, inplace.vector.syn
related: vector, array, sequence.reqmts, container.requirements, container.requirements.general, freestanding.item
tags: 标准库, 容器, inplace_vector, C++26, freestanding
since: c++26
papers: P0843R14
updated: 2026-10-19
---

!!! tldr
    - `inplace_vector<T, N>` 的元素存放在对象内部，容量 N 固定，大小在 0 到 N 之间变化；它从不分配堆内存，也不是分配器感知容器。
    - 让大小超过 N 的操作抛 `bad_alloc`；`try_push_back` 装满时返回空 `optional`；`unchecked_push_back` 要求调用者保证还有空间。
    - `T` 的拷贝、移动、析构是平凡的，`inplace_vector<T, N>` 的对应操作也是平凡的；N 为 0 时它是一个空的平凡类型。
    - 因为元素在对象内部，移动构造和 `swap` 都是线性时间，不像 `vector` 那样只交换指针。
    - 会抛异常的成员在 freestanding 实现中被删除，`try_` 和 `unchecked_` 系列保留。

`std::inplace_vector<T, N>`（{{c++26}}，[[P0843R14]]）介于 `array` 和 `vector` 之间：容量像 `array` 一样是编译期常量，存储在对象内部；大小像 `vector` 一样可以变化。适合上限已知、又不想做堆分配的场合，例如实时代码、嵌入式环境、热路径上的临时缓冲。

!!! warning "例子没有经过本地编译"
    本机 Clang 23 自带的 libc++ 还没有提供 `<inplace_vector>`（`<version>` 里 `__cpp_lib_inplace_vector` 仍被注释掉），本机也没有 GCC。所以这里的例子不标判定，可以用 godbolt 按钮在已实现它的标准库上运行。

## 装满之后怎么办

```cpp title="inplace-vector.cpp" run
#include <inplace_vector>
#include <cassert>

int main() {
  std::inplace_vector<int, 2> v;
  v.push_back(1);
  int& r = v.emplace_back(2);       // 返回新元素的引用
  assert(r == 2 && v.size() == v.capacity());

  auto opt = v.try_push_back(3);    // 已满：不抛异常，返回空 optional
  assert(!opt && v.size() == 2);

  try { v.push_back(3); }           // 已满：抛 bad_alloc（¶4）
  catch (const std::bad_alloc&) {}

  static_assert(std::inplace_vector<int, 2>::capacity() == 2);
}
```

[inplace.vector.modifiers] 给末尾插入提供了三套接口，对应三种错误处理方式：

| 接口 | 装满时 | 返回 | 出处 |
|---|---|---|---|
| `push_back`、`emplace_back` | 抛 `bad_alloc` | `reference`，即 `back()` | ¶4–¶7 |
| `try_push_back`、`try_emplace_back` | 没有效果 | `optional<reference>`，装满时为 `nullopt` | ¶8–¶14 |
| `unchecked_push_back`、`unchecked_emplace_back` | 违反前置条件 `size() < capacity()`，{{ub}} | `reference` | ¶15–¶18 |

第一套用异常报告错误，是默认的选择；第二套用返回值，适合禁用了异常的环境；第三套适合调用者已经确认有空间、不想再付一次检查开销的场合。

几处细节：

- `push_back` 返回引用，而 `vector::push_back` 返回 `void`。
- `try_` 系列返回 `optional<reference>`，用到了 C++26 的 `optional<T&>`。¶12 规定除了新元素初始化时抛出的异常，它不抛任何异常。
- ¶10 `try_emplace_back` 用实参直接非列表初始化新元素，也就是 `T(args...)` 而不是 `T{args...}`。
- ¶16、¶18 `unchecked_` 系列被定义为 `*try_emplace_back(…)` 和 `*try_push_back(…)`，空间不足时就是对空 `optional` 解引用。

## 概述（[inplace.vector.overview]）

¶1 `inplace_vector` 是连续容器，容量固定，元素存储在 `inplace_vector` 对象自身之内。

¶2 它满足容器、可逆容器、连续容器和序列容器的要求，不提供 `push_front`、`prepend_range`、`pop_front`、`emplace_front`。这份清单里没有分配器感知容器：[[container.alloc.reqmts#1]] 把它和 `array` 一起排除在外。

¶3 对任意 N，迭代器都满足 constexpr 迭代器的要求。

!!! std
    Any member function of inplace_vector<T, N> that would cause the size to exceed N throws an exception of type bad_alloc.

¶4 容量不足按分配失败处理，抛 `bad_alloc`，与 `vector` 内存耗尽时的异常类型一致，同一段泛型代码对两者有相同的错误路径。

### 平凡性随 T 传播（¶5）

¶5 记 `IV` 为 `inplace_vector<T, N>`。N 为 0 时，`IV` 是平凡可复制的空类，并且可以平凡默认构造。N 大于 0 时：

- ¶5.1–¶5.2 `T` 的拷贝构造（移动构造）平凡，`IV` 的拷贝构造（移动构造）也平凡；
- ¶5.3 `T` 可平凡析构时，`IV` 也可平凡析构；在此基础上，`T` 的拷贝构造和拷贝赋值都平凡，`IV` 的拷贝赋值就平凡，移动赋值同理。

所以 `inplace_vector<int, 16>` 是平凡可复制的，可以 `memcpy`，可以整体放进共享内存或网络报文。N 大于 0 时标准没有保证平凡默认构造，因为默认构造必须把大小置为 0。

实现上，存储通常是放在 union 里的元素数组（这样默认构造时不会构造全部 N 个元素），再加一个大小计数器。

## 构造与容量（[inplace.vector.cons]、[inplace.vector.capacity]）

构造函数与 [[sequence.reqmts]] 的通用条目相同，只是没有分配器参数：`inplace_vector(n)`、`(n, value)`、迭代器区间、`from_range`、初始化器列表（¶1–¶11）。

¶9 `from_range` 构造有一条编译期检查：

!!! std
    *Mandates*: If ranges::size(rg) is a constant expression, then ranges::size(rg) ≤ N.

把一个 `std::array<int, 5>` 放进 `inplace_vector<int, 4>`，编译期就会被拒绝。运行时才知道大小的区间超出容量时，按 ¶4 抛 `bad_alloc`。

[inplace.vector.capacity] 规定：

- ¶1 `capacity()` 和 `max_size()` 都是 `static constexpr` 函数，返回 N。
- ¶2–¶7 `resize(sz)` 和 `resize(sz, c)` 抛出异常时，对 `*this` 没有效果。
- ¶8–¶9 `reserve(n)` 是 `static constexpr` 的，什么也不做，只在 `n > capacity()` 时抛 `bad_alloc`。
- ¶10 `shrink_to_fit()` 是 `static constexpr noexcept` 的空操作。

`reserve` 和 `shrink_to_fit` 保留下来，是为了让 `inplace_vector` 能直接替换泛型代码里的 `vector`。

[inplace.vector.data] ¶1–¶2 `data()` 的规定与 `vector` 相同：`[data(), data() + size())` 是有效区间，非空时 `data() == addressof(front())`，常数时间。

## 中间插入、擦除与 swap（[inplace.vector.modifiers]）

### 插入抛异常时前缀不变（¶1–¶3）

¶1 先定义 n：对 `append_range` 是调用前的 `size()`，对其余插入函数是插入点之前的元素个数。

¶2 复杂度与插入的元素数加上插入点到末尾的距离成线性。

¶3 如果异常不是来自 `T` 的拷贝构造、移动构造、拷贝赋值、移动赋值，也不是来自输入迭代器的操作，就没有效果。否则，抛出异常后 `size() >= n`，而且前 n 个元素没有被修改。

这条保证比 `vector` 的中间插入更具体：插入点之前的前缀一定完好，但容器里可能多出了一部分已经插入的元素。例如 `append_range` 超出容量时，可能在抛出 `bad_alloc` 之前已经追加了一部分元素。

### 擦除与 swap（¶19–¶23）

¶19–¶21 `erase` 和 `pop_back` 的规则与 `vector` 相同：擦除点及之后的迭代器和引用失效；除了 `T` 的赋值不抛异常；析构次数等于擦除的元素数，赋值次数等于擦除点之后的元素数。

¶22–¶23 `swap(x)` 的异常说明是 `noexcept(N == 0 || (is_nothrow_swappable_v<T> && is_nothrow_move_constructible_v<T>))`。前置条件是 `T` 可移动构造，并且两边前 `min(size(), x.size())` 个元素可以两两交换。

元素在对象内部，交换只能逐个进行：重叠的部分逐个 `swap`，多出来的部分移动构造到另一边，再销毁原来的。所以 `swap` 和移动构造都是线性时间，[[container.reqmts#16]] 和 [[container.reqmts#50]] 把 `inplace_vector` 和 `array` 一起列为例外。

### 插入时的迭代器失效

[inplace.vector.modifiers] 对擦除给出了失效规则（¶19），对插入却没有。[[container.reqmts#67]] 的总则是：除非另有规定，容器成员函数不得使迭代器失效，也不得改变元素的值。

中间插入必然改变插入点之后元素的值，所以插入本身的效果（在 p 之前插入）可以看作另有规定。合理的读法是：存储在对象内部、永不重新分配，插入点之前的迭代器和引用不受影响；插入点及之后的迭代器仍然指向有效的存储，但已经不再指向原来的元素。实践中可以把它当作一个永不重新分配的 `vector` 来推理。

## erase 与 erase_if（[inplace.vector.erasure]）

¶1–¶2 非成员函数 `erase(c, value)` 和 `erase_if(c, pred)` 等价于 remove-erase 惯用法，返回擦除的元素个数（`size_t`）。

## freestanding

`<inplace_vector>` 的头文件概要标注为 mostly freestanding。类概要里，可能因容量不足抛 `bad_alloc` 的成员，包括 `push_back`、`emplace_back`、`insert`、`append_range`、`resize`、`reserve`、带元素的构造函数和 `assign`，以及会抛 `out_of_range` 的 `at`，都标为 *freestanding-deleted*（[[freestanding.item]]），在 freestanding 实现中被删除。`try_`、`unchecked_` 系列、`erase`、`pop_back` 和不抛异常的元素访问都保留。

所以在没有异常支持的环境中，`inplace_vector` 的推荐用法是 `try_push_back` 加上检查返回值。

## 怎么选择

- 上限已知且不大，不想要堆分配：`inplace_vector`。
- 大小固定不变：`array`。
- 大小没有上限，或者上限很大：`vector`。`inplace_vector` 的 `sizeof` 至少是 `N * sizeof(T)`，放在栈上可能导致栈溢出。

## 小结

| 方面 | 规则 |
|---|---|
| 存储 | 在对象内部；容量 N 是 `static constexpr`；不是分配器感知容器 |
| 超出容量 | 普通接口抛 `bad_alloc`；`try_` 返回 `nullopt`；`unchecked_` 违反前置条件 |
| 平凡性 | N 为 0 时是空的平凡类型；否则拷贝、移动、析构的平凡性随 `T` |
| `reserve`、`shrink_to_fit` | `static` 函数，基本是空操作 |
| 移动、`swap` | 线性时间 |
| 插入抛异常 | 插入点之前的元素保持不变 |
