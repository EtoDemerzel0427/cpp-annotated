---
title: 内存管理库
summary: 第 20 章导读——<memory>、<memory_resource>、<scoped_allocator> 里的工具如何建立在核心语言的对象模型之上；读库条款时 Mandates / Constraints / Preconditions / Hardened preconditions 各意味着什么
status: done
covers: mem.general
related: intro.object, basic.life, basic.stc.dynamic, expr.new, memory, smartptr, mem.res, allocator.traits
tags: 标准库, 内存管理, 导读
updated: 2026-10-18
---

第 20 章 [mem] 是标准库里离核心语言**最近**的一章。核心语言在 [[intro.object]]、[[basic.life]]、[[basic.stc.dynamic]]、[[expr.new]] 里定义了"对象什么时候存在、存储从哪里来、`new`/`delete` 做了什么"；本章则把这些规则包装成可组合的库组件：

- 一套**描述指针与分配器的元编程接口**（`pointer_traits`、`allocator_traits`、uses-allocator 构造），让容器可以对"花式指针"和自定义分配器保持泛型；
- 一组**直接操作对象生命周期的函数**（`start_lifetime_as`、`addressof`、`assume_aligned`），它们的语义几乎完全是用核心语言术语写的；
- **所有权类型**：`unique_ptr`、`shared_ptr`/`weak_ptr`，以及 C++26 新增的值语义包装 `indirect`/`polymorphic`；
- **运行期多态的内存资源**（`std::pmr`）与**作用域分配器**（`scoped_allocator_adaptor`）；
- C++26 之后进入草案的 **指针标记**（`pointer_tag_pair`）{{c++29}}。

## 本章地图（[mem.general] ¶2）

¶1 只有一句："本章描述内存管理组件"。¶2 的表 50 给出子条款与头文件的对应：

| 子条款 | 内容 | 头文件 | 本站笔记 |
|---|---|---|---|
| [memory] | 指针特征、对齐、显式生命周期、分配器协议、默认分配器、`addressof`、C 的 `malloc` 族 | `<cstdlib>`、`<memory>` | [[memory]]、[[pointer.traits]]、[[ptr.align]]、[[obj.lifetime]]、[[allocator.uses]]、[[allocator.traits]]、[[default.allocator]] |
| [ptrtag] | `pointer_tag_pair`：把小整数塞进指针的空闲位 | `<memory>` | [[ptrtag]] |
| [smartptr] | `unique_ptr`、`shared_ptr`、`weak_ptr`、`out_ptr`/`inout_ptr` | `<memory>` | [[smartptr]]、[[unique.ptr]]、[[util.sharedptr]] 等 |
| [mem.composite.types] | `indirect`、`polymorphic` {{c++26}} | `<memory>` | [[mem.composite.types]]、[[indirect]]、[[polymorphic]] |
| [mem.res] | `memory_resource`、`polymorphic_allocator`、池资源、单调缓冲资源 | `<memory_resource>` | [[mem.res]] 及其子页 |
| [allocator.adaptor] | `scoped_allocator_adaptor` | `<scoped_allocator>` | [[allocator.adaptor]] |

注意两个**不在**本章的东西：

- `uninitialized_copy`、`construct_at`、`destroy_at` 等"特化内存算法"虽然声明在 `<memory>` 里，但规范正文在算法章的 [[specialized.algorithms]]；本站在 [[memory]] 里讨论它们与 placement new 的关系。
- `atomic<shared_ptr<T>>` 声明在 `<memory>`，规范正文在原子操作章的 [[util.smartptr.atomic]]。
- `operator new`/`operator delete`、`std::launder`、`bad_alloc` 在 `<new>`，属于语言支持库 [[support.dynamic]]。

## 先学会读库条款：五种"要求"的法律后果

库条款几乎不用"shall"直接规定行为，而是给每个函数写一组带斜体标签的元素（[[structure.specifications]] ¶3）。分清它们的法律后果，是读本章的第一门功课：

| 元素 | 不满足时的后果 | 本章典型例子 |
|---|---|---|
| *Constraints* | 该函数**不参与重载决议**（静默不可行，[[over.match]]） | `unique_ptr(unique_ptr<U,E>&&)` 要求 `U` 不是数组 |
| *Mandates* | 程序 {{ill-formed}}，必须诊断（通常是 `static_assert`） | `default_delete<T>::operator()` 要求 `T` 完整 |
| *Preconditions* | {{ub}} | `unique_ptr::operator*` 要求 `get() != nullptr` |
| *Hardened preconditions* {{c++26}} | 在**加固实现**（[[g:hardened-implementation]]）中以终止语义检查（[[basic.contract.eval]]）；非加固实现中违反仍是 UB | `shared_ptr<T[]>::operator[]` 要求 `i >= 0`，`T` 为 `U[N]` 时 `i < N` |
| *Constant When* | 调用不是常量子表达式 | `pointer_tag_pair` 的构造函数 |

一个容易忽略的细节：*Constraints* 失败与 *Mandates* 失败对 SFINAE 与概念检测的影响完全不同。

```cpp title="constraints-vs-mandates.cpp" ok
#include <memory>
#include <type_traits>

struct Base {};
struct Derived : Base {};

// Constraints：unique_ptr<Base[]> 不能从 unique_ptr<Derived[]> 构造——它根本不是候选
static_assert(!std::is_constructible_v<std::unique_ptr<Base[]>, std::unique_ptr<Derived[]>>);
// 单对象版本满足 Constraints（Derived* 可隐式转换为 Base*）
static_assert(std::is_constructible_v<std::unique_ptr<Base>, std::unique_ptr<Derived>>);

int main() {}
```

而 *Mandates* 是"选中之后再报错"：`is_constructible` 之类的特征检测**看不到**它，真正实例化时才会触发 `static_assert`。

!!! note "库里的 UB 与核心语言的 UB 是同一种 UB"
    *Preconditions* 违例导致的未定义行为和核心语言的 UB 法律地位完全相同（[[intro.abstract]]）。`unique_ptr` 解引用空指针，与 `*static_cast<int*>(nullptr)` 一样，都允许优化器假设"不会发生"。C++26 的**标准库加固**（hardening）只把一部分前置条件提升为 *Hardened preconditions*；本章中这样的条款很少——例如 `shared_ptr::operator[]` 的下标——而 `unique_ptr::operator*`、`operator->` 仍然只是普通前置条件。

## 本章与核心语言的接口

本章大量条款只有放在核心语言背景下才读得懂。最常见的几个接口：

- **隐式对象创建**：`malloc`、`calloc`、`realloc`、`memory_resource::allocate` 都被规定为"在返回的存储中隐式创建对象并返回指向合适对象的指针"（[[intro.object]] ¶13–¶16，[[g:implicitly-create-objects]]）。`start_lifetime_as` 则是在**不拷贝**字节的前提下做同一件事（[[obj.lifetime]]）。
- **生命周期与析构**：`allocator<T>::allocate` 只开始**数组对象**的生命周期，不开始任何元素的生命周期（[[default.allocator]]）；元素要靠 `allocator_traits::construct`（默认就是 `construct_at`，即 placement new）一个个建起来。
- **delete 表达式**：`default_delete` 的效果就是"对 `ptr` 调用 `delete`"——于是 [[expr.delete]] 中关于不完整类型、虚析构函数、`delete` 与 `delete[]` 不匹配的全部 UB 都原样继承。
- **数据竞争**：`shared_ptr` 的线程安全保证是用 [[intro.races]] 的"冲突"与"数据竞争"术语表述的（[[util.smartptr.shared]] ¶5）。

## 历史脉络

| 版本 | 本章的关键变化 |
|---|---|
| C++98 | `std::allocator`、`auto_ptr`、`raw_storage_iterator`、`get_temporary_buffer` |
| C++11 | `unique_ptr`、`shared_ptr`、`weak_ptr`、`allocator_traits`、`pointer_traits`、`scoped_allocator_adaptor`、`align`、`addressof`；`auto_ptr` 弃用 |
| C++14 | `make_unique` |
| C++17 | `<memory_resource>`（`std::pmr`）、`shared_ptr<T[]>`；`auto_ptr` 移除 |
| C++20 | `to_address`、`assume_aligned`、`make_shared` 支持数组、`*_for_overwrite`、`constexpr` 的 `allocator`/`construct_at`、uses-allocator 构造函数族、`atomic<shared_ptr>` |
| C++23 | `start_lifetime_as`、`out_ptr`/`inout_ptr`、`allocate_at_least`、`constexpr unique_ptr` |
| C++26 | `indirect`/`polymorphic`（[[P3019R14]]）、`is_sufficiently_aligned`、`owner_hash`/`owner_equal`（[[P1901R2]]）、`constexpr shared_ptr`（[[P3037R6]]）、`start_lifetime`（[[P3726R2]]）、移除 `allocator::is_always_equal` 成员（[[P2868R3]]）；可平凡重定位曾被加入又在 NB 意见处理中撤回 |
| C++26 之后 | `pointer_tag_pair`（[[P3125R6]]） |

## 小结

- 本章是"对象模型的库界面"：凡是遇到 `allocate`、`construct`、`destroy`、`start_lifetime_as`，先想清楚它在 [[intro.object]] / [[basic.life]] 意义上做了什么。
- 读库条款时，按 *Constraints* → *Mandates* → *Preconditions* → *Hardened preconditions* 分辨违例后果：不可行 / 必须报错 / UB / 加固实现中终止。
- `<memory>` 是一个"大杂烩"头文件，规范正文散落在第 20 章、第 26 章（特化算法）和第 32 章（原子智能指针）。
