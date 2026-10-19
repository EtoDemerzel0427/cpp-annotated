---
title: 内存管理库
summary: 第 20 章导读：<memory>、<memory_resource>、<scoped_allocator> 各管什么，它们怎样建立在核心语言的对象模型之上，以及读库条款时 Constraints、Mandates、Preconditions 等要素各意味着什么。
status: done
covers: mem.general
related: intro.object, basic.life, basic.stc.dynamic, expr.new, memory, smartptr, mem.res, allocator.traits
tags: 标准库, 内存管理, 导读
updated: 2026-10-19
---

!!! tldr
    - 第 20 章是对象模型的库接口：分配器协议、显式开始对象生命周期的函数、智能指针、内存资源都在这里。
    - 读库条款时先分清要素：*Constraints* 不满足则函数不参与重载决议，*Mandates* 不满足则程序非良构，*Preconditions* 不满足则是未定义行为。
    - C++26 的加固前置条件在加固实现中会被检查并终止程序，在其他实现中违反它仍是未定义行为；本章只有少数函数用它。
    - `malloc` 族和内存资源会隐式创建对象，`std::allocator<T>::allocate` 只开始数组对象的生命周期，元素要逐个构造。
    - `<memory>` 里有些声明的规范正文不在本章：特化内存算法在算法章，`atomic<shared_ptr>` 在原子操作章。

第 20 章 [mem] 是标准库里离核心语言最近的一章。核心语言在 [[intro.object]]、[[basic.life]]、[[basic.stc.dynamic]]、[[expr.new]] 里规定对象何时存在、存储从哪里来、`new` 和 `delete` 做什么；本章把这些规则包装成可以组合的库组件。

## 本章地图 [mem.general]

¶1 本章描述内存管理组件。¶2 的表 50 列出子条款与头文件的对应：

| 子条款 | 内容 | 头文件 | 本站笔记 |
|---|---|---|---|
| [memory] | 指针特征、对齐、显式生命周期管理、分配器协议、默认分配器、`addressof`、C 的 `malloc` 族 | `<cstdlib>`、`<memory>` | [[memory]]、[[pointer.traits]]、[[ptr.align]]、[[obj.lifetime]]、[[allocator.uses]]、[[allocator.traits]]、[[default.allocator]] |
| [smartptr] | `unique_ptr`、`shared_ptr`、`weak_ptr`、`out_ptr` / `inout_ptr` | `<memory>` | [[smartptr]]、[[unique.ptr]]、[[util.sharedptr]] |
| [ptrtag] {{c++29}} | `pointer_tag_pair`：把小整数存进指针的空闲位 | `<memory>` | [[ptrtag]] |
| [mem.composite.types] {{c++26}} | `indirect`、`polymorphic` | `<memory>` | [[mem.composite.types]]、[[indirect]]、[[polymorphic]] |
| [mem.res] | `memory_resource`、`polymorphic_allocator`、池资源、单调缓冲资源 | `<memory_resource>` | [[mem.res]] |
| [allocator.adaptor] | `scoped_allocator_adaptor` | `<scoped_allocator>` | [[allocator.adaptor]] |

有几样东西声明在 `<memory>`，规范正文却在别处：

- `uninitialized_copy`、`construct_at`、`destroy_at` 等特化内存算法在算法章的 [[specialized.algorithms]]，它们与 placement new 的关系见 [[memory]]；
- `atomic<shared_ptr<T>>` 在原子操作章的 [[util.smartptr.atomic]]；
- `operator new` / `operator delete`、`std::launder`、`bad_alloc` 在 `<new>`，属于语言支持库 [[support.dynamic]]。

## 读库条款：违反各种要求的后果

库条款很少直接用 shall 规定行为，而是给每个函数列出一组带斜体标签的要素（[[structure.specifications]]）。违反不同要素，后果完全不同：

| 要素 | 不满足时 | 本章的例子 |
|---|---|---|
| *Constraints* | 函数不参与重载决议，就像不存在一样 | `unique_ptr<T[]>` 的转换构造函数要求源指针也是数组版本、元素类型兼容 |
| *Mandates* | 程序非良构，必须诊断，通常由 `static_assert` 报出 | `default_delete<T>::operator()` 要求 `T` 是完整类型 |
| *Preconditions* | 未定义行为 | `unique_ptr::operator*` 要求 `get() != nullptr` |
| *Hardened preconditions* {{c++26}} | 在加固实现（[[g:hardened-implementation]]）中作为契约检查，违反时终止；否则是未定义行为 | `shared_ptr<T[]>::operator[]` 要求 `i >= 0`，`T` 为 `U[N]` 时还要求 `i < N` |
| *Constant When* | 调用不是常量子表达式 | `pointer_bits_available` 要求对齐值是 2 的幂 |

*Constraints* 和 *Mandates* 的差别在泛型代码里最明显：

<div class="compare" markdown="1">

```cpp run ok
#include <memory>
#include <type_traits>
struct B {};
struct D : B {};
using UB = std::unique_ptr<B[]>;
using UD = std::unique_ptr<D[]>;
// Constraints 不满足：构造函数不是候选
static_assert(
  !std::is_constructible_v<UB, UD>);
int main() {}
```

```cpp run error
#include <memory>
#include <type_traits>
struct Inc;   // 不完整类型
using Del = std::default_delete<Inc>;
// 特征检测看不到 Mandates
static_assert(
  std::is_invocable_v<Del, Inc*>);
void f(Inc* p) {
  Del{}(p);  // error: T 必须完整
}
int main() {}
```

</div>

左边，*Constraints* 让那个构造函数从候选集中消失，`is_constructible` 能如实回答 `false`。右边，*Mandates* 不影响函数是否可调用，`is_invocable` 回答 `true`，真正调用时才在函数体里报错。

库前置条件违反导致的未定义行为，与核心语言的未定义行为地位相同（[[intro.abstract]]）。对空的 `unique_ptr` 解引用和 `*static_cast<int*>(nullptr)` 一样，优化器都可以假设它不发生。C++26 的标准库加固只把一部分前置条件改成了加固前置条件：本章里 `shared_ptr<T[]>::operator[]` 是，`unique_ptr::operator*` 和 `operator->` 不是。

## 本章与核心语言的接口

- 隐式创建对象：`malloc`、`calloc`、`realloc`、`memory_resource::allocate` 都会在返回的存储中隐式创建对象，并返回指向合适对象的指针（[[intro.object]]，[[g:implicitly-create-objects]]）。`start_lifetime_as` 不复制字节，在已有的存储上做同样的事（[[obj.lifetime]]）。
- 生命周期：`allocator<T>::allocate` 只开始数组对象的生命周期，不开始任何元素的生命周期（[[default.allocator]]）。元素要靠 `allocator_traits::construct` 逐个构造，默认就是 `construct_at`，即 placement new。
- delete 表达式：`default_delete` 的效果就是对指针调用 `delete`，所以 [[expr.delete]] 中关于不完整类型、非虚析构函数、`delete` 与 `delete[]` 不匹配的未定义行为原样继承。
- 数据竞争：`shared_ptr` 的线程安全保证用 [[intro.races]] 的冲突和数据竞争来表述（[[util.smartptr.shared]]）。

## 本章的演进

| 版本 | 主要变化 |
|---|---|
| C++98 | `std::allocator`、`auto_ptr`、`raw_storage_iterator`、`get_temporary_buffer` |
| C++11 | `unique_ptr`、`shared_ptr`、`weak_ptr`、`allocator_traits`、`pointer_traits`、`scoped_allocator_adaptor`、`align`、`addressof`；`auto_ptr` 弃用 |
| C++14 | `make_unique` |
| C++17 | `<memory_resource>`、`shared_ptr<T[]>`；移除 `auto_ptr` |
| C++20 | `to_address`、`assume_aligned`、数组版 `make_shared`、`*_for_overwrite`、`constexpr` 的 `allocator` 和 `construct_at`、`atomic<shared_ptr>` |
| C++23 | `start_lifetime_as`、`out_ptr` / `inout_ptr`、`allocate_at_least`、`constexpr unique_ptr` |
| C++26 | `indirect` / `polymorphic`（[[P3019R14]]）、`is_sufficiently_aligned`、`owner_hash` / `owner_equal`（[[P1901R2]]）、`constexpr shared_ptr`（[[P3037R6]]）、移除 `allocator::is_always_equal` 成员（[[P2868R3]]） |
| C++26 之后 | `pointer_tag_pair`（[[P3125R6]]） |
