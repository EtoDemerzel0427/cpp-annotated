---
title: 组合类设计用类型
summary: C++26 的 indirect 与 polymorphic：把类的数据成员放到堆上，同时保留值语义（深复制、const 传播、没有空状态），弥补 unique_ptr 做成员时的三个缺陷。
status: done
since: c++26
related: indirect, polymorphic, unique.ptr, allocator.traits, class.copy.ctor, mem
tags: 标准库, indirect, polymorphic, 值语义, C++26
papers: P3019R14
updated: 2026-10-19
---

!!! tldr
    - 用 `unique_ptr` 做数据成员，外层类就不能隐式复制，`const` 成员函数里还能修改被指对象，而且每次访问都要考虑空指针。
    - `indirect<T>` 是放在堆上的 `T`：复制时复制 `T`，`const` 会传播，可以按值比较和散列。
    - `polymorphic<T>` 持有 `T` 或其派生类的对象，复制时按动态类型复制，不需要虚 `clone()`。
    - 两者都没有空状态，只有被移动之后才可能无值，可以用 `valueless_after_move()` 查询。
    - 截至写作时，本机 Clang 23 + libc++ 还没有实现这两个类。

[mem.composite.types] 是 C++26 新增的子条款（[[P3019R14]]），只包含两个类模板 [[indirect]] 和 [[polymorphic]]，本身没有规范性段落。标题 Types for composite class design 说明了它们的用途：作为类的数据成员。

## unique_ptr 做成员的三个问题

把成员放到堆上有几个常见理由：成员类型在这里还不完整（pimpl、递归数据结构）；成员很大，想让外层对象小一些、移动快一些；成员的动态类型到运行时才确定。传统做法是用 `std::unique_ptr<T>` 做成员：

```cpp
struct Widget {
    std::unique_ptr<Impl> impl;
    void set(int v) const { impl->value = v; }   // const 函数也能改
};
Widget a;
Widget b = a;      // error: 复制构造函数被定义为弃置的
```

1. 外层类不能复制。有 `unique_ptr` 成员，隐式的复制构造函数就被定义为弃置的（[[class.copy.ctor]]），只能手写深复制；多态成员还要配一个虚 `clone()`。
2. `const` 不传播。在 `const` 成员函数里，成员的类型是 `const unique_ptr<Impl>`，但 `*impl` 仍然是 `Impl&`，被指对象照样可以修改。
3. 可以为空。每次访问都要考虑空指针，而空往往根本不是合法状态。

`indirect<T>` 和 `polymorphic<T>` 的目标是让成员用起来像直接放一个 `T` 一样：可复制、`const` 会传播、没有空状态，只是对象存放在堆上。

## 两者对比

| | `indirect<T, Allocator>` | `polymorphic<T, Allocator>` |
|---|---|---|
| 被拥有对象的类型 | 恰好是 `T` | `T` 或其可复制的公有派生类 |
| 复制 | 复制构造一个 `T` | 按被拥有对象的动态类型复制构造 |
| 比较、散列 | 有，委托给 `T` | 没有 |
| `operator*` | 有左值、右值四个重载 | 只有 `const` 与非 `const` 两个 |
| 典型用途 | pimpl、递归类型、大成员 | 多态成员，取代 `unique_ptr<Base>` 加虚 `clone()` |

两者共有的设计：

- 只有被移动之后才可能没有被拥有对象，这叫**无值**（valueless，[[g:valueless]]）。移动操作直接接管源对象的指针，源对象变为无值，代价很小而且不抛异常。对无值对象解引用违反前置条件，是 UB。
- 默认构造会分配内存并构造一个 `T`，不像 `unique_ptr` 那样默认为空。
- 它们是分配器感知的：用 `allocator_traits` 分配和构造被拥有对象，分配器在赋值和交换时是否随之替换，遵循与容器相同的规则（[[allocator.traits]]）。`std::pmr::indirect<T>` 和 `std::pmr::polymorphic<T>` 是使用 `polymorphic_allocator` 的别名。
- `T` 可以是不完整类型；析构函数等用到 `T` 完整定义的成员以 *Mandates* 检查完整性。
- `T` 不能是非对象类型、数组、`in_place_t`、`in_place_type_t` 的特化或 cv 限定类型，否则非良构。程序声明它们的显式特化或偏特化是 UB。

## 与其他包装类型比较

| 类型 | 存储位置 | 可能为空 | 复制 | const 传播 |
|---|---|---|---|---|
| `T` 成员 | 对象内 | 否 | 复制 `T` | 是 |
| `optional<T>` | 对象内 | 是 | 复制 `T` | 是 |
| `unique_ptr<T>` | 堆 | 是 | 不能复制 | 否 |
| `shared_ptr<T>` | 堆 | 是 | 共享同一个对象 | 否 |
| `indirect<T>` | 堆 | 仅在被移动后 | 复制 `T` | 是 |
| `polymorphic<T>` | 堆，实现可以把小对象放在内部 | 仅在被移动后 | 按动态类型复制 | 是 |

本机 libc++ 尚未提供 `std::indirect` 和 `std::polymorphic`，两个页面中的示例都没有经过编译验证。
