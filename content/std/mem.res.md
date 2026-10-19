---
title: 内存资源（std::pmr）
summary: <memory_resource> 把从哪里分配内存从容器的类型中拿出来，交给一个运行期的资源对象；两个全局资源 new_delete_resource 与 null_memory_resource；默认资源指针。
status: done
covers: mem.res.syn, mem.res.global
related: mem.res.class, mem.poly.allocator.class, mem.res.pool, mem.res.monotonic.buffer, allocator.traits, allocator.uses, allocator.adaptor
tags: 标准库, pmr, 分配器, memory_resource
updated: 2026-10-19
---

!!! tldr
    - C++11 的分配器是类型的一部分，`vector<int, A>` 与 `vector<int>` 是不同的类型；`std::pmr` 改为让所有容器使用同一个分配器类型，在运行期选择内存资源。
    - `new_delete_resource()` 转发给 `::operator new` 和 `::operator delete`；`null_memory_resource()` 的每次分配都抛出 `bad_alloc`，适合作为禁止使用堆的上游。
    - 默认资源指针初值是 `new_delete_resource()`，分配器在构造时读取它，之后再修改不影响已经构造的分配器。
    - 分配器不拥有资源。资源必须比所有用它分配的对象活得长，否则就是 UB。

## 静态分配器与运行期资源

C++11 的分配器模型是静态的：分配策略是容器类型的一部分。`vector<int, ArenaAlloc<int>>` 与 `vector<int>` 是两个类型，接受 `const vector<int>&` 的函数不能接受前者。想让一个库函数支持别的分配策略，只能把它改成模板。

C++17 的 `<memory_resource>`（命名空间 `std::pmr`，pmr 即 polymorphic memory resource）换了一种做法：

- [[mem.res.class]] 的 `memory_resource` 是一个抽象基类，用虚函数表示一个能分配字节的东西；
- [[mem.poly.allocator.class]] 的 `polymorphic_allocator<T>` 是一个固定的分配器类型，内部只存一个 `memory_resource*`，所有分配都转发给它。

于是 `pmr::vector<int>`，即 `vector<int, pmr::polymorphic_allocator<int>>`，只是一个类型，分配策略由构造时传入的资源在运行期决定。代价是每次分配多一次虚函数调用，分配器多占一个指针的空间。

## 头文件 [mem.res.syn]

`<memory_resource>` 在 `std::pmr` 中声明：

| 组件 | 页面 |
|---|---|
| `memory_resource` 及其 `operator==` | [[mem.res.class]] |
| `polymorphic_allocator<Tp = byte>` 及其 `operator==` | [[mem.poly.allocator.class]] |
| `new_delete_resource`、`null_memory_resource`、`set_default_resource`、`get_default_resource` | 下文 |
| `pool_options`、`synchronized_pool_resource`、`unsynchronized_pool_resource` | [[mem.res.pool]] |
| `monotonic_buffer_resource` | [[mem.res.monotonic.buffer]] |

各容器的头文件还在 `std::pmr` 中提供别名，如 `pmr::vector<T>`、`pmr::string`、`pmr::map<K, V>`；`<memory>` 中有 `pmr::indirect<T>` 和 `pmr::polymorphic<T>`（[[memory]]）。

## 两个全局资源 [mem.res.global]

¶1 `new_delete_resource()` 返回一个指向静态存储期对象的指针，这个对象派生自 `memory_resource`，用 `::operator new` 和 `::operator delete` 分配和释放内存。每次调用返回同一个值。对返回值 `p` 和任何资源 `r`，`p->is_equal(r)` 返回 `&r == p`，即它只与自己相等。

¶2 `null_memory_resource()` 返回一个静态存储期的资源，它的 `allocate()` 总是抛出 `bad_alloc`，`deallocate()` 什么也不做。它同样每次返回同一个值，只与自己相等。

它最常见的用途是作为上游资源，把不许使用堆写成一条在运行时强制执行的约束：

```cpp run title="null-upstream.cpp" ok
#include <memory_resource>
#include <vector>
#include <cstdio>
#include <new>
int main() {
  std::byte buf[64];
  std::pmr::monotonic_buffer_resource mono(
      buf, sizeof buf, std::pmr::null_memory_resource());
  std::pmr::vector<int> v(&mono);
  try {
    for (int i = 0; i < 100; ++i) v.push_back(i);
  } catch (const std::bad_alloc&) {
    std::printf("bad_alloc after %zu elements\n", v.size());
  }
}
```

本机输出 `bad_alloc after 8 elements`。`vector` 依次申请容纳 1、2、4、8 个 `int` 的缓冲区，共 60 字节；单调资源不回收旧缓冲区（[[mem.res.monotonic.buffer]]），下一次申请 64 字节时栈上的缓冲区不够了，转向上游，上游抛出 `bad_alloc`，而不是悄悄改用堆。这在实时代码和测试中很有用。

## 默认资源指针 [mem.res.global]

¶3 **默认内存资源指针**（default memory resource pointer，[[g:default-memory-resource-pointer]]）指向一个内存资源，某些设施在接口没有显式提供资源时使用它。初值是 `new_delete_resource()` 的返回值。使用它的主要是默认构造的 `polymorphic_allocator`，以及没有给出上游参数的池资源和单调资源。

- ¶4–¶5 `set_default_resource(r)`：`r` 非空时把默认资源指针设为 `r`，为空时设为 `new_delete_resource()`；返回原来的值。
- ¶7 `get_default_resource()` 返回当前值。
- ¶6 调用这两个函数不会引起数据竞争；一次 `set_default_resource` 调用与其后的 `set_default_resource`、`get_default_resource` 调用同步（[[intro.races]]）。实现通常用一个原子指针。

```cpp run title="default-resource.cpp" ok
#include <memory_resource>
#include <vector>
#include <cassert>
int main() {
  std::pmr::monotonic_buffer_resource arena;
  std::pmr::vector<int> d;                       // 此时读取默认资源
  std::pmr::set_default_resource(&arena);
  std::pmr::vector<int> e;
  assert(d.get_allocator().resource() == std::pmr::new_delete_resource());
  assert(e.get_allocator().resource() == &arena);
  std::pmr::set_default_resource(nullptr);       // 恢复为 new_delete_resource()
}
```

默认资源在分配器构造的那一刻被读取并保存下来，`d` 不受之后的 `set_default_resource` 影响。

!!! pitfall "把默认资源当作局部作用域的工具"
    默认资源是全局可变状态。在多线程程序中把它设成某个线程局部的 arena，其他线程会在不知情的情况下从这个 arena 分配；arena 销毁后，那些对象的内存就失效了。`set_default_resource` 适合在 `main` 开头设置一次，例如设成一个每次分配都报错的资源，用来发现意外的堆分配。

## 资源必须比使用者活得长

`polymorphic_allocator` 只存一个裸指针，不拥有资源。资源必须比所有使用它的分配器，以及用这些分配器分配的对象活得更长。这是使用 `pmr` 时最常见的 UB：

```cpp run title="resource-lifetime.cpp" ub
#include <memory_resource>
#include <vector>
#include <optional>
int main() {
  std::optional<std::pmr::vector<int>> v;
  {
    std::pmr::unsynchronized_pool_resource pool;
    v.emplace({1, 2, 3}, &pool);           // 元素从 pool 分配
  }                                        // pool 销毁
  v.reset();                               // UB：通过已销毁的 pool 释放内存
}
```

本机 ASan 报告 `stack-use-after-scope`：`vector` 析构时调用的 `pool.deallocate()` 访问的是一个已经销毁的栈上对象。在同一个作用域里，把资源声明在使用它的容器之前，后声明的对象先析构，顺序就是对的。

## 小结

- `pmr` 把分配策略从类型移到运行期对象：一个 `pmr::vector<T>` 类型，可以配任意资源。
- `new_delete_resource` 转发给 `::operator new` 和 `::operator delete`；`null_memory_resource` 总是抛出 `bad_alloc`，适合作为禁止使用堆的上游。
- 默认资源指针初值是 `new_delete_resource()`，读写没有数据竞争，分配器在构造时读取它。
- 资源不归分配器所有，必须比所有使用者活得长。
