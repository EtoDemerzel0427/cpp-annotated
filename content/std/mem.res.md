---
title: 内存资源（std::pmr）
summary: <memory_resource> 导读——把"从哪里分配"从类型中剥离出来交给运行期对象；全局资源 new_delete_resource、null_memory_resource 与默认资源指针的线程安全规则
status: done
covers: mem.res.syn, mem.res.global
related: mem.res.class, mem.poly.allocator.class, mem.res.pool, mem.res.monotonic.buffer, allocator.traits, allocator.uses, allocator.adaptor
tags: 标准库, pmr, 分配器, memory_resource
updated: 2026-10-18
---

C++11 的分配器模型是**静态**的：分配策略是容器类型的一部分。`vector<int, ArenaAlloc<int>>` 与 `vector<int>` 是不同类型，接受 `const vector<int>&` 的函数不能接受前者。想给一个库函数换分配策略，就必须把它改成模板。

C++17 的 `<memory_resource>`（命名空间 `std::pmr`，"polymorphic memory resource"）换了一种思路：

- **`memory_resource`**（[[mem.res.class]]）：一个抽象基类，用虚函数 `do_allocate`/`do_deallocate`/`do_is_equal` 表示"一个可以分配字节的东西"；
- **`polymorphic_allocator<T>`**（[[mem.poly.allocator.class]]）：一个**固定类型**的分配器，内部只存一个 `memory_resource*`，所有分配都转发给它。

于是 `pmr::vector<int>`（即 `vector<int, pmr::polymorphic_allocator<int>>`）是**一个**类型，分配策略在运行期由构造时传入的资源决定。代价是每次分配一次虚函数调用，以及分配器多占一个指针。

## 头文件概要（[mem.res.syn]）

`<memory_resource>` 在 `std::pmr` 中声明：

| 组件 | 本站笔记 |
|---|---|
| `memory_resource` 及其 `operator==` | [[mem.res.class]] |
| `polymorphic_allocator<Tp = byte>` 及其 `operator==` | [[mem.poly.allocator.class]] |
| `new_delete_resource`、`null_memory_resource`、`set_default_resource`、`get_default_resource` | 本页 |
| `pool_options`、`synchronized_pool_resource`、`unsynchronized_pool_resource` | [[mem.res.pool]] |
| `monotonic_buffer_resource` | [[mem.res.monotonic.buffer]] |

各容器头文件还在 `std::pmr` 中提供别名：`pmr::vector<T>`、`pmr::string`、`pmr::map<K, V>`……以及 `<memory>` 中的 `pmr::indirect<T>`、`pmr::polymorphic<T>`（[[memory]]）。

## 程序范围的资源（[mem.res.global]）

### `new_delete_resource()`（¶1）

返回指向一个**静态存储期**对象的指针，该对象派生自 `memory_resource`，用 `::operator new` 和 `::operator delete` 分配与释放。每次调用返回同一个值。对返回值 `p` 和任何资源 `r`，`p->is_equal(r)` 返回 `&r == p`——它只与自己相等。

### `null_memory_resource()`（¶2）

返回一个静态存储期的资源，其 `allocate()` **总是抛出 `bad_alloc`**，`deallocate()` 无效果。同样只与自己相等。

它最常见的用途是作为**上游**，把"不许碰堆"写成硬约束：

```cpp title="null-upstream.cpp" ok
#include <memory_resource>
#include <vector>
#include <cstdio>
#include <new>
int main() {
    std::byte buf[64];
    std::pmr::monotonic_buffer_resource mono(buf, sizeof buf, std::pmr::null_memory_resource());
    std::pmr::vector<int> v(&mono);
    try { for (int i = 0; i < 100; ++i) v.push_back(i); }
    catch (const std::bad_alloc&) { std::printf("bad_alloc after %zu elements\n", v.size()); }
}
```

本机输出 "bad_alloc after 8 elements"：64 字节的栈缓冲区用尽（`vector` 扩容时旧缓冲区不会被单调资源回收）后，任何进一步的分配都会抛出，而不是悄悄落到堆上。这在实时代码与测试中很有用。

### 默认资源指针（¶3–¶7）

¶3 定义**默认内存资源指针**（[[g:default-memory-resource-pointer]]）：当接口没有显式提供资源时，某些设施使用它所指的资源；初始值是 `new_delete_resource()` 的返回值。"某些设施"主要是默认构造的 `polymorphic_allocator`（[[mem.poly.allocator.class]]），以及没有给上游参数的池资源和单调资源。

- `set_default_resource(r)`（¶4–¶5）：`r` 非空时设为 `r`，为空时设为 `new_delete_resource()`；返回旧值。
- `get_default_resource()`（¶7）：返回当前值。
- ¶6：这两个函数的调用**不得引发数据竞争**；对 `set_default_resource` 的调用与其后的 `set_default_resource`、`get_default_resource` 调用**同步**（[[intro.races]]）。实现通常用一个原子指针。

!!! pitfall "默认资源是全局可变状态"
    默认资源在**取用的那一刻**被读取并保存。`pmr::vector<int> v;` 构造时把当时的 `get_default_resource()` 存进分配器，之后再 `set_default_resource` 不影响它。反过来，在多线程程序中把默认资源设成一个线程局部的 arena，会让其他线程在不知情时从这个 arena 分配——而 arena 销毁后，那些对象就悬空了。`set_default_resource` 适合在 `main` 开头设置一次（例如设成一个会断言的"禁止分配"资源来检测意外的堆分配），不适合当作局部作用域工具。

## pmr 模型的生命周期规则

`polymorphic_allocator` 只存一个**裸指针**，不拥有资源。资源必须比所有使用它的分配器（以及用这些分配器分配的对象）活得更长——这是使用 `pmr` 时最常见的 UB 来源：

```cpp title="resource-lifetime.cpp" ub
#include <memory_resource>
#include <vector>
#include <optional>
int main() {
    std::optional<std::pmr::vector<int>> v;
    {
        std::pmr::unsynchronized_pool_resource pool;
        v.emplace({1, 2, 3}, &pool);           // 元素从 pool 分配
    }                                          // pool 析构：release() 把内存还给上游
    v.reset();                                 // UB：vector 用已销毁的资源去 deallocate
}
```

本机 ASan 报告 "stack-use-after-scope"。实践原则：**资源声明在使用它的容器之前**（同一作用域内后声明者先析构）。

## 小结

- `pmr` 把分配策略从类型移到运行期对象：一个 `pmr::vector<T>` 类型，任意多种资源。
- `new_delete_resource` 转发到 `::operator new/delete`；`null_memory_resource` 总是抛 `bad_alloc`，适合作为"禁止落到堆上"的上游。
- 默认资源指针初始为 `new_delete_resource()`，读写无数据竞争；它在分配器构造时被读取。
- 资源不被分配器拥有，必须比所有使用者活得长。
