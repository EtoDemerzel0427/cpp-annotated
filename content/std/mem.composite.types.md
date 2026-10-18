---
title: 组合类设计用类型
summary: C++26 的 indirect 与 polymorphic——为"把成员放到堆上"提供值语义：深拷贝、const 传播、移动后才可能无值；它们填补了 unique_ptr 在类成员场景中的空白
status: done
since: c++26
related: indirect, polymorphic, unique.ptr, allocator.traits, class.copy.ctor, mem
tags: 标准库, indirect, polymorphic, 值语义, C++26
papers: P3019R14
updated: 2026-10-18
---

[mem.composite.types] 是 C++26 新增的子条款（[[P3019R14]]），只包含两个类模板：[[indirect]] 与 [[polymorphic]]。它的标题"组合类设计用类型"（Types for composite class design）点明了用途：它们是给**类的数据成员**用的。

## 问题：`unique_ptr` 做成员时破坏了值语义

把成员放到堆上有很多理由：

- **不完整类型**：pimpl、递归数据结构（`struct Expr { std::vector<Expr> args; }` 可以，`struct Node { Node left; }` 不行）；
- **大对象**：让外层对象小而便于移动；
- **运行期多态**：成员的动态类型在运行期才确定。

传统做法是 `std::unique_ptr<T>` 成员，但它带来三个问题：

1. **不可复制**：一旦有 `unique_ptr` 成员，外层类的隐式复制构造函数被定义为弃置（[[class.copy.ctor]]），必须手写深拷贝；多态成员更要配一个虚 `clone()`。
2. **`const` 不传播**：在 `const` 成员函数里，`unique_ptr<T>` 成员是 `const unique_ptr<T>`，但 `*p` 仍是 `T&`——可以修改被指对象，`const` 正确性形同虚设。
3. **可以为空**：每次访问都要考虑空指针，而"空"往往根本不是合法状态。

`indirect<T>` 与 `polymorphic<T>` 的设计目标是：**用起来像 `T` 本身作为成员一样**——可复制（深拷贝）、可比较（`indirect`）、`const` 传播、没有"空"状态（除了被移动之后）——只是存储在堆上。

## 两者对比

| | `indirect<T, Allocator>` | `polymorphic<T, Allocator>` |
|---|---|---|
| 被拥有对象的类型 | 恰好是 `T` | `T` 或其任意（可复制的）派生类 |
| 复制 | 复制构造一个 `T` | 复制构造一个与原件**动态类型相同**的对象（类型擦除的 clone） |
| 比较、散列 | 有（委托给 `T`） | 无 |
| `operator*` 的引用限定 | 有 `&`/`&&` 四个重载 | 只有 const/非 const |
| 典型用途 | pimpl、递归类型、大成员 | 多态成员，取代 `unique_ptr<Base>` + 虚 `clone()` |
| `pmr` 别名 | `pmr::indirect<T>` | `pmr::polymorphic<T>` |

两者共享的设计决策：

- **无值状态（valueless）**：唯一可能没有被拥有对象的情形是**被移动之后**。移动构造和移动赋值把源对象的指针偷过来，源对象变为无值，可用 `valueless_after_move()` 查询。对无值对象解引用违反前置条件，{{ub}}。这与 `std::variant` 的 `valueless_by_exception` 思路相似：一个罕见的、可以查询的退化状态，换来 `noexcept` 的移动。
- **分配器感知**：用 `allocator_traits` 分配和构造被拥有对象，分配器的传播遵循容器的 POCCA/POCMA/POCS 规则（[[allocator.traits]]）。
- **`T` 可以不完整**：类定义可以实例化，析构函数和部分赋值操作有完整性 *Mandates*。
- **禁止特化**：程序声明它们的显式或偏特化是 {{ub}}（`indirect` ¶8、`polymorphic` ¶8）。
- **不能是**：非对象类型、数组、`in_place_t`、`in_place_type_t` 的特化、cv 限定类型（¶5）。

## 与其他"包一层"的类型比较

| 类型 | 存储 | 可空 | 复制 | const 传播 |
|---|---|---|---|---|
| `T` 成员 | 内嵌 | 否 | 是 | 是 |
| `optional<T>` | 内嵌 | 是 | 是 | 是 |
| `unique_ptr<T>` | 堆 | 是 | 否 | 否 |
| `shared_ptr<T>` | 堆 | 是 | 浅拷贝（共享） | 否 |
| `indirect<T>` | 堆 | 仅移动后 | 深拷贝 | 是 |
| `polymorphic<T>` | 堆（实现可做小对象优化） | 仅移动后 | 深拷贝（保留动态类型） | 是 |

截至写作时，本机 Clang 23 + libc++ 尚未实现 `indirect` 与 `polymorphic`，相关页面的示例未在本地编译验证。
