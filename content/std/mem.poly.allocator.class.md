---
title: polymorphic_allocator
summary: pmr 的唯一分配器类型——只存一个 memory_resource*；复制赋值被弃置、传播特征全为假、复制构造容器时退回默认资源，三者合起来保证"容器一生只用一个资源"；construct 执行 uses-allocator 构造；allocate_bytes/new_object 等字节级接口
status: done
covers: *
related: mem.res, mem.res.class, allocator.traits, allocator.uses, allocator.adaptor, default.allocator
tags: 标准库, pmr, 分配器, polymorphic_allocator
papers: P0339R6, P2875R4
updated: 2026-10-18
---

`pmr::polymorphic_allocator<Tp>` 是连接静态分配器模型（[[allocator.traits]]）与运行期资源（[[mem.res.class]]）的桥：它满足 *Cpp17Allocator*，所以可以给任何标准容器用；而它所有的分配都转发给一个 `memory_resource*`。

## 概述（[mem.poly.allocator.class.general]）

- ¶1：当模板实参是 cv 无限定的对象类型时，特化满足 *Cpp17Allocator*。用不同资源构造的同一特化的不同实例可以有完全不同的分配行为——"使用同一静态分配器类型的对象在运行期表现得像使用不同的分配器类型"。
- ¶2：在同样条件下满足分配器完整性要求（[[allocator.requirements.completeness]]）。

唯一的（说明用）数据成员是 `memory_resource* memory_rsrc`。模板形参 `Tp` 的默认实参是 `byte`（C++20，[[P0339R6]]）——`polymorphic_allocator<>` 是一个"通用"的分配器，配合下面的 `allocate_bytes`/`new_object` 使用，不必为每种类型重绑定。

```cpp title="polymorphic-allocator.cpp" ok
#include <memory_resource>
#include <string>
#include <type_traits>
#include <cassert>

using PA = std::pmr::polymorphic_allocator<>;          // Tp 默认是 std::byte
static_assert(std::is_same_v<PA::value_type, std::byte>);
static_assert(!std::is_copy_assignable_v<PA>);          // 复制赋值被弃置
static_assert(!std::allocator_traits<PA>::propagate_on_container_move_assignment::value);
static_assert(!std::allocator_traits<PA>::is_always_equal::value);

int main() {
    std::pmr::monotonic_buffer_resource mr;
    PA a(&mr);                                          // 从 memory_resource* 隐式转换
    auto* s = a.new_object<std::pmr::string>("pmr strings get the allocator too, via construct");
    assert(s->get_allocator().resource() == &mr);       // new_object → construct → uses-allocator 构造
    a.delete_object(s);
    void* raw = a.allocate_bytes(100, 64);
    a.deallocate_bytes(raw, 100, 64);
    assert(PA(&mr) == std::pmr::polymorphic_allocator<int>(&mr));   // 不同 Tp 之间也可比较
}
```

## "资源跟着对象走，不跟着值走"

`polymorphic_allocator` 的几条看似零散的规定，合起来表达了一个设计原则：**容器在构造时绑定一个资源，此后一生不变**。

1. **复制赋值被弃置**：`operator=(const polymorphic_allocator&) = delete`。分配器对象本身不能被重新指向另一个资源。
2. **传播特征全为假**：类里没有定义 `propagate_on_container_*`，`allocator_traits` 取默认的 `false_type`；`is_always_equal` 取 `is_empty`（非空）为假。所以容器赋值、交换时都不会替换分配器（[[allocator.traits]]）。
3. **复制构造容器时退回默认资源**：`select_on_container_copy_construction()` 返回 `polymorphic_allocator()`（¶18），注 4："内存资源不传播"。

第 3 条最容易让人意外：`pmr::vector<int> copy = v;` 中，`copy` 用的是**默认资源**，而不是 `v` 的资源。理由是：资源通常与某个作用域绑定（栈上的 arena、某个请求的生命周期），副本可能活得更久或被传到别处，自动继承资源会制造悬空。需要同一资源时显式传入：`pmr::vector<int> copy(v, v.get_allocator());`。

后果也要清楚：移动赋值两个使用**不同**资源的 `pmr` 容器会退化为逐元素移动；交换它们是 {{ub}}（[[allocator.traits]] 中有示例）。

## 构造函数（[mem.poly.allocator.ctor]）

- `polymorphic_allocator() noexcept`（¶1）：`memory_rsrc = get_default_resource()`——在**构造时**读取默认资源。
- `polymorphic_allocator(memory_resource* r)`（¶2–¶5）：*Preconditions* `r` 非空；不抛出。¶5 注：这个构造函数**不是 `explicit`**，提供从 `memory_resource*` 的隐式转换——这就是 `pmr::vector<int> v(&arena);` 能直接写的原因。
- 转换构造 `polymorphic_allocator(const polymorphic_allocator<U>&) noexcept`（¶6）：复制资源指针。

## 成员函数（[mem.poly.allocator.mem]）

### 类型化分配

- `allocate(n)`（¶1）：`numeric_limits<size_t>::max() / sizeof(Tp) < n` 时抛 `bad_array_new_length`，否则 `memory_rsrc->allocate(n * sizeof(Tp), alignof(Tp))`。
- `deallocate(p, n)`（¶2–¶4）：*Preconditions* `p` 来自一个与 `*memory_rsrc` **相等**的资源 `x`，且是以 `x.allocate(n * sizeof(Tp), alignof(Tp))` 分配的；不抛出。

### 字节级与对象级接口（C++20）

| 函数 | 等价于 |
|---|---|
| `allocate_bytes(nbytes, alignment = alignof(max_align_t))`（¶5–¶6） | `memory_rsrc->allocate(nbytes, alignment)` |
| `deallocate_bytes(p, nbytes, alignment)`（¶7） | `memory_rsrc->deallocate(p, nbytes, alignment)` |
| `allocate_object<T>(n = 1)`（¶8–¶9） | 溢出检查后 `allocate_bytes(n*sizeof(T), alignof(T))` |
| `deallocate_object(p, n = 1)`（¶10） | `deallocate_bytes(p, n*sizeof(T), alignof(T))` |
| `new_object<T>(args...)`（¶11–¶12） | `allocate_object<T>()`，再 `construct`；构造抛异常则释放后重新抛出 |
| `delete_object(p)`（¶13） | `destroy(p)` 再 `deallocate_object(p)` |

¶6 注 1：`allocate_bytes` 返回 `void*`（而不是 `byte*`），以便 `static_cast<U*>` 到任意类型。`allocate_object`、`new_object` 的 `T` 不能推导，必须显式给出（注 2、注 3）。

这些接口让 `polymorphic_allocator<>` 本身就能当一个"带 arena 的 `new`/`delete`"使用，不需要为每种类型写 `rebind`。注意 `delete_object` 用的是**静态类型** `T` 的大小——对多态对象用基类指针调用 `delete_object` 会传错大小，违反 `do_deallocate` 的前置条件。

### `construct` 与 `destroy`（¶14–¶17）

- `construct(p, args...)`：*Mandates* 以 `*this` 和 `args...` 对 `T` 做 uses-allocator 构造（[[allocator.uses]]）是良构的；效果就是这样的构造。¶16：除非 `T` 的构造函数抛出，否则不抛出。

这是 `pmr` 能"一路传下去"的关键：`pmr::vector<pmr::string>` 构造元素时，`allocator_traits::construct` 调用到这里，`pmr::string` 的构造函数收到同一个资源。

- `destroy(p)`：等价于 `p->~T()`。它曾由 [[LWG3036]] 在 C++23 中弃用（因为 `allocator_traits::destroy` 的默认行为相同），C++26 由 [[P2875R4]] 撤销弃用——`delete_object` 的规范要用到它，而且用户派生 `polymorphic_allocator` 时也需要一个可调用的基准。

### 其他

- `select_on_container_copy_construction()`（¶18–¶19）：返回默认构造的 `polymorphic_allocator()`。
- `resource()`（¶20）：返回 `memory_rsrc`。

## 相等（[mem.poly.allocator.eq]）

`a == b` 当且仅当 `*a.resource() == *b.resource()`——即两个资源**相等**（同一对象，或 `is_equal` 为真，[[mem.res.class]]），而不只是指针相等。类内还有一个隐藏友元 `operator==(const polymorphic_allocator&, const polymorphic_allocator&)`，使得一侧需要隐式转换（例如 `alloc == &resource`）时也能找到合适的重载——命名空间作用域的模板版本无法从 `memory_resource*` 推导 `T2`，这是 [[LWG3683]] 的修正。

## 思考题

<details markdown="1">
<summary>1. 为什么 `polymorphic_allocator` 弃置复制赋值，却保留复制构造？</summary>

复制构造是分配器模型的基本要求：容器要从用户给的分配器复制出自己的分配器、`rebind` 到节点类型时要转换构造。复制**赋值**则对应"容器被赋值时换掉分配器"，而 `pmr` 的原则是容器一生只用构造时的资源；POCCA 为假时容器本来就不会赋值分配器，弃置复制赋值只是让这一点在类型层面不可违反，防止用户代码误操作已绑定到容器的分配器。
</details>

<details markdown="1">
<summary>2. `std::pmr::vector<std::pmr::vector<int>> outer(&arena); outer.emplace_back();` 内层 vector 从哪里分配？`outer.push_back(std::pmr::vector<int>{1, 2, 3});` 呢？</summary>

两种情况内层 vector 都使用 `arena`：`emplace_back()` 通过 `polymorphic_allocator::construct` 做 uses-allocator 构造，内层得到 `arena`。`push_back(临时 vector)` 也经由 `construct`，以 `(vector&&, const allocator&)` 的后置约定构造——带分配器的移动构造函数；由于临时对象用的是默认资源、与 `arena` 不等，元素会被**逐个移动**到从 `arena` 分配的新缓冲区，而不是偷走临时对象的缓冲区。
</details>

## 小结

- 内部只有一个 `memory_resource*`，可从 `memory_resource*` 隐式构造；默认构造读取当时的默认资源。
- 复制赋值弃置、传播特征全假、复制构造容器时退回默认资源——资源跟着容器的身份走。
- `construct` 执行 uses-allocator 构造，使资源递归传递给元素。
- C++20 起有 `allocate_bytes`/`allocate_object`/`new_object` 等字节级与对象级接口，`Tp` 默认为 `byte`。
- 相等比较的是资源是否相等，而不只是指针。
