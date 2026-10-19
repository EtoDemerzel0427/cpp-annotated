---
title: polymorphic_allocator
summary: pmr 使用的分配器类型，只存一个 memory_resource*；复制赋值被弃置、传播特征全为假、复制容器时退回默认资源，合起来保证容器一生只用一个资源；construct 做 uses-allocator 构造，让资源传给元素；以及字节级和对象级的分配接口。
status: done
covers: *
related: mem.res, mem.res.class, allocator.traits, allocator.uses, allocator.adaptor, default.allocator
tags: 标准库, pmr, 分配器, polymorphic_allocator
papers: P0339R6, P2875R4
updated: 2026-10-19
---

!!! tldr
    - `polymorphic_allocator` 只存一个 `memory_resource*`，可以从 `memory_resource*` 隐式构造，所以能写 `pmr::vector<int> v(&arena);`。
    - 容器在构造时绑定一个资源，此后不再改变：分配器不能复制赋值，传播特征全为假。
    - 复制一个 `pmr` 容器，副本使用默认资源而不是原容器的资源；要同一个资源需显式传入。
    - `construct` 做 uses-allocator 构造，`pmr::vector<pmr::string>` 的每个字符串都从同一个资源分配。
    - `allocate_bytes`、`new_object`、`delete_object` 等接口让 `polymorphic_allocator<>` 可以直接当作一个带内存资源的 `new` 和 `delete` 使用。

```cpp run title="polymorphic-allocator.cpp" ok
#include <memory_resource>
#include <string>
#include <type_traits>
#include <cassert>

using PA = std::pmr::polymorphic_allocator<>;    // Tp 默认是 std::byte
static_assert(std::is_same_v<PA::value_type, std::byte>);
static_assert(!std::is_copy_assignable_v<PA>);
static_assert(!std::allocator_traits<PA>::propagate_on_container_move_assignment::value);
static_assert(!std::allocator_traits<PA>::is_always_equal::value);

int main() {
  std::pmr::monotonic_buffer_resource mr;
  PA a(&mr);
  auto* s = a.new_object<std::pmr::string>(
      "pmr strings get the allocator too, via construct");
  assert(s->get_allocator().resource() == &mr);   // 字符串也用 mr
  a.delete_object(s);
  void* raw = a.allocate_bytes(100, 64);
  a.deallocate_bytes(raw, 100, 64);
  assert(PA(&mr) == std::pmr::polymorphic_allocator<int>(&mr));
  assert(a == &mr);                               // 隐式转换后比较
}
```

## 概述 [mem.poly.allocator.class.general]

¶1 模板实参是 cv 无限定的对象类型时，`polymorphic_allocator` 的特化满足 *Cpp17Allocator*，所以可以给任何标准容器使用。用不同资源构造的同一特化的实例，分配行为可以完全不同：使用同一个静态分配器类型的对象，在运行期表现得就像使用了不同的分配器类型。¶2 在同样的条件下，它满足分配器完整性要求（[[allocator.requirements.completeness]]），所以可以用于元素类型尚不完整的 `pmr::vector`。

唯一的说明用数据成员是 `memory_resource* memory_rsrc`。模板形参 `Tp` 的默认实参是 `byte`（C++20，[[P0339R6]]），`polymorphic_allocator<>` 可以配合下文的 `allocate_bytes`、`new_object` 使用，不必为每种类型重绑定。

## 容器一生只用一个资源

`polymorphic_allocator` 有几条看似零散的规定，合起来表达了一个设计原则：容器在构造时绑定一个资源，此后一直不变。

1. 复制赋值被弃置：`operator=(const polymorphic_allocator&) = delete`。分配器对象不能改为指向另一个资源。
2. 传播特征全为假：类中没有定义 `propagate_on_container_*`，`allocator_traits` 取默认的 `false_type`；`is_always_equal` 默认取 `is_empty`，对一个存了指针的类为假。所以容器赋值和交换时都不替换分配器（[[allocator.traits]]）。
3. 复制容器时退回默认资源：¶18 `select_on_container_copy_construction()` 返回 `polymorphic_allocator()`，¶19 注 4 写明内存资源不传播。

```cpp run title="copy-uses-default.cpp" ok
#include <memory_resource>
#include <vector>
#include <cassert>
int main() {
  std::pmr::monotonic_buffer_resource arena;
  std::pmr::vector<int> v({1, 2, 3}, &arena);
  std::pmr::vector<int> copy = v;
  assert(copy.get_allocator().resource() == std::pmr::get_default_resource());
  std::pmr::vector<int> same(v, v.get_allocator());
  assert(same.get_allocator().resource() == &arena);
}
```

第 3 条最容易让人意外：`copy` 用的是默认资源，不是 `v` 的资源。资源通常与某个作用域绑定，比如栈上的 arena 或者某个请求的生命周期，而副本可能活得更久，或者被传到别处；自动继承资源很容易造成悬空。需要同一个资源时，像 `same` 那样显式传入。

由此还有两个后果：移动赋值两个使用不同资源的 `pmr` 容器，会退化为逐个元素移动；交换它们是 UB（[[allocator.traits]]）。

## 构造函数 [mem.poly.allocator.ctor]

- ¶1 默认构造把 `memory_rsrc` 设为 `get_default_resource()`，在构造的那一刻读取默认资源（[[mem.res]]）。
- ¶2–¶5 `polymorphic_allocator(memory_resource* r)`：前置条件 `r` 非空，不抛出。¶5 注 1 指出它提供了从 `memory_resource*` 的隐式转换，`pmr::vector<int> v(&arena);` 之所以能直接写，就是因为这个构造函数不是 `explicit` 的。
- ¶6 从 `polymorphic_allocator<U>` 转换构造，复制资源指针。容器把分配器重绑定到内部节点类型时用的就是它。

## 成员函数 [mem.poly.allocator.mem]

### 按类型分配

¶1 `allocate(n)`：`numeric_limits<size_t>::max() / sizeof(Tp) < n` 时抛出 `bad_array_new_length`，否则返回 `memory_rsrc->allocate(n * sizeof(Tp), alignof(Tp))` 的结果。

¶2–¶4 `deallocate(p, n)`：前置条件是 `p` 由一个与 `*memory_rsrc` 相等的资源 `x` 以 `x.allocate(n * sizeof(Tp), alignof(Tp))` 分配；效果是 `memory_rsrc->deallocate(p, n * sizeof(Tp), alignof(Tp))`，不抛出。

### 字节级与对象级接口

这组接口是 C++20 加入的：

| 函数 | 等价于 |
|---|---|
| `allocate_bytes(nbytes, alignment = alignof(max_align_t))`（¶5–¶6） | `memory_rsrc->allocate(nbytes, alignment)` |
| `deallocate_bytes(p, nbytes, alignment)`（¶7） | `memory_rsrc->deallocate(p, nbytes, alignment)` |
| `allocate_object<T>(n = 1)`（¶8–¶9） | 检查溢出后 `allocate_bytes(n*sizeof(T), alignof(T))` |
| `deallocate_object(p, n = 1)`（¶10） | `deallocate_bytes(p, n*sizeof(T), alignof(T))` |
| `new_object<T>(args...)`（¶11–¶12） | `allocate_object<T>()` 后 `construct`；构造抛出异常时先释放再重新抛出 |
| `delete_object(p)`（¶13） | `destroy(p)` 后 `deallocate_object(p)` |

¶6 注 1 解释，`allocate_bytes` 返回 `void*` 而不是 `byte*`，是为了能用 `static_cast<U*>` 转换到任意类型。¶9 和 ¶12 的注指出，`allocate_object` 和 `new_object` 的 `T` 无法推导，必须显式给出。

`delete_object` 按静态类型 `T` 的大小释放。用基类指针对一个派生类对象调用 `delete_object`，传给资源的大小就是错的，违反了 `do_deallocate` 的前置条件（[[mem.res.class]]），即使基类有虚析构函数也一样。

### construct 与 destroy（¶14–¶17）

¶14–¶16 `construct(p, args...)` 以 `*this` 为分配器、以 `args...` 为构造实参，对 `T` 做 uses-allocator 构造（[[allocator.uses]]）：如果 `T` 接受分配器，就把 `*this`（转换为 `T` 需要的分配器类型）一并传给构造函数。*Mandates* 要求这样的构造良构；除非 `T` 的构造函数抛出，否则不抛出。

这是资源能逐层传递下去的关键。`pmr::vector<pmr::string>` 构造元素时，`allocator_traits::construct` 调用到这里，`pmr::string` 的构造函数收到同一个资源。上面例子中 `new_object<std::pmr::string>` 构造的字符串使用 `mr`，也是这个原因。

¶17 `destroy(p)` 等价于 `p->~T()`。C++23 曾经弃用它（[[LWG3036]]），理由是 `allocator_traits::destroy` 的默认行为与它相同；C++26 的 [[P2875R4]] 撤销了弃用，因为 `delete_object` 的规定要用到它。

### 其他

¶18–¶19 `select_on_container_copy_construction()` 返回默认构造的 `polymorphic_allocator()`，见上文。¶20 `resource()` 返回 `memory_rsrc`。

## 相等 [mem.poly.allocator.eq]

¶1 `a == b` 返回 `*a.resource() == *b.resource()`，比较的是两个资源是否相等（同一个对象，或者 `is_equal` 为真，见 [[mem.res.class]]），不只是指针是否相等。

类里还有一个隐藏友元 `operator==(const polymorphic_allocator&, const polymorphic_allocator&)`。命名空间作用域的模板版本无法从 `memory_resource*` 推导出模板实参，有了这个友元，`a == &mr` 这种一侧需要隐式转换的比较也能编译（[[LWG3683]]）。

## 思考题

!!! question "思考题 1"
    `polymorphic_allocator` 为什么弃置了复制赋值，却保留复制构造？

<details markdown="1">
<summary>答案</summary>

复制构造是分配器模型的基本要求：容器要从用户给的分配器复制出自己的分配器，重绑定到节点类型时也要转换构造。复制赋值则对应容器被赋值时换掉分配器，而 `pmr` 的原则是容器一生只用构造时的资源。POCCA 为假时容器本来就不会赋值分配器，弃置复制赋值是在类型层面防止用户代码修改一个已经绑定到容器的分配器。
</details>

!!! question "思考题 2"
    `std::pmr::vector<std::pmr::vector<int>> outer(&arena);` 之后，`outer.emplace_back();` 构造的内层 vector 从哪里分配？`outer.push_back(std::pmr::vector<int>{1, 2, 3});` 呢？

<details markdown="1">
<summary>答案</summary>

两种情况下内层 vector 都使用 `arena`，本机验证两者的 `get_allocator().resource()` 都等于 `&arena`。`emplace_back()` 经由 `construct` 做 uses-allocator 构造，内层 vector 得到 `arena`。`push_back` 的实参是一个使用默认资源的临时 vector，`construct` 以带分配器的移动构造函数 `vector(vector&&, const allocator_type&)` 构造新元素；由于两个资源不相等，元素被逐个移动到从 `arena` 分配的新缓冲区，而不是接管临时对象的缓冲区。
</details>

## 小结

- 内部只有一个 `memory_resource*`，可以从 `memory_resource*` 隐式构造；默认构造在构造时读取默认资源。
- 复制赋值弃置、传播特征全假、复制容器时退回默认资源：资源跟着容器本身，不跟着容器的值。
- `construct` 做 uses-allocator 构造，资源会传给元素。
- C++20 起有 `allocate_bytes`、`allocate_object`、`new_object` 等接口，`Tp` 默认为 `byte`。
- 相等比较的是资源是否相等，而不只是指针。
