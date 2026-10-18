---
title: scoped_allocator_adaptor
summary: C++11 的"作用域分配器"——把外层分配器给容器、内层分配器经 uses-allocator 构造传给元素，可逐层指定或递归复用；它派生自外层分配器，传播特征取各层的"或"，is_always_equal 取"与"；construct 交给最外层分配器
status: done
covers: *
related: allocator.uses, allocator.traits, mem.poly.allocator.class, mem.res, container.alloc.reqmts
tags: 标准库, 分配器, scoped_allocator_adaptor
updated: 2026-10-18
---

在 `pmr`（C++17）出现之前，C++11 为"把分配器传给元素"提供的方案是 `<scoped_allocator>` 中的 `scoped_allocator_adaptor`。它与 `polymorphic_allocator` 解决的是同一个问题——嵌套容器的元素也应当使用同一（或指定的）分配器——但走的是**静态类型**路线。今天在新代码中更常见的是 `pmr`，但理解这个适配器有助于理解 uses-allocator 协议（[[allocator.uses]]）的由来：该协议最早就是为它设计的。

## 头文件与总体设计（[allocator.adaptor.syn]）

¶1：`scoped_allocator_adaptor` 是一个分配器模板，指定一个**外层分配器**（outer allocator，供容器自身使用）以及一个**内层分配器**资源（传给容器每个元素的构造函数）。用一个外层与零个或多个内层分配器类型实例化：

- **只有一个**分配器类型：内层分配器就是适配器自己——容器、元素、元素的元素……**递归地**都用同一个分配器资源；
- **多个**：第一个给容器，第二个给元素，第三个给元素的元素，依此类推；嵌套深度超过分配器个数时，**最后一个**被重复使用。

注 1：它**派生自**外层分配器类型，因此在大多数表达式中可以替代外层分配器——这也是 [[allocator.traits]] ¶1 规定"分配器必须是类类型"的理由之一。

```cpp
template<class OuterAlloc, class... InnerAllocs>
class scoped_allocator_adaptor : public OuterAlloc {
  using OuterTraits = allocator_traits<OuterAlloc>;   // exposition only
  scoped_allocator_adaptor<InnerAllocs...> inner;     // exposition only
  ...
};
```

说明用成员 `inner` 是一个**递归**的适配器：`scoped_allocator_adaptor<A, B, C>` 内含 `scoped_allocator_adaptor<B, C>`，后者内含 `scoped_allocator_adaptor<C>`。（只有一个分配器时没有 `inner` 子对象——`inner_allocator()` 返回 `*this`。）

`value_type`、`size_type`、`pointer` 等成员类型都取自外层分配器的 traits；`rebind<Tp>::other` 只重绑定外层分配器，内层分配器类型不变。有推导指引 `scoped_allocator_adaptor(OuterAlloc, InnerAllocs...)`。

## 成员类型（[allocator.adaptor.types]）

- ¶1 `inner_allocator_type`：`InnerAllocs` 为空时是 `scoped_allocator_adaptor<OuterAlloc>`，否则是 `scoped_allocator_adaptor<InnerAllocs...>`。
- ¶2–¶4 `propagate_on_container_copy_assignment`、`_move_assignment`、`_swap`：若 `OuterAlloc` 与 `InnerAllocs...` 中**任何一个** `A` 的对应特征为真，则为 `true_type`。
- ¶5 `is_always_equal`：**每一个**都为真时才为 `true_type`。

传播取"或"：只要任何一层需要跟着容器走，整个适配器就必须跟着走——否则那一层会与它所分配的内存分离。相等取"与"：只有每一层都总相等，整个适配器才总相等。

## 构造（[allocator.adaptor.cnstr]）

- 默认构造（¶1）：值初始化外层基类和 `inner`。
- `(OuterA2&& outerAlloc, const InnerAllocs&... innerAllocs) noexcept`（¶2–¶3）：*Constraints* `is_constructible_v<OuterAlloc, OuterA2>`；用 `outerAlloc` 初始化基类、用 `innerAllocs...` 初始化 `inner`（递归地逐个初始化）。
- 复制、移动（¶4–¶5），以及从外层类型不同的适配器转换（¶6–¶9，用于 `rebind` 之后的转换）——逐个初始化每一层。所有构造函数都是 `noexcept`：分配器的复制与移动本就不允许抛出。

## 成员函数（[allocator.adaptor.members]）

### ¶1：*OUTERMOST*

`OUTERMOST(x)`：若 `x.outer_allocator()` 有效（[[temp.deduct]] 意义上），则为 `OUTERMOST(x.outer_allocator())`，否则为 `x`。`OUTERMOST_ALLOC_TRAITS(x)` 是其 `allocator_traits`。注 1：这是递归运算，由 `outer_allocator()` 的定义保证终止。

为什么需要它？外层分配器本身也可能是一个 `scoped_allocator_adaptor`（把适配器嵌套在适配器里），`construct` 需要找到**真正**负责构造的那个最外层分配器。

### 访问与转发

- `inner_allocator()`（¶2）：`InnerAllocs` 为空时返回 `*this`，否则返回 `inner`。
- `outer_allocator()`（¶3–¶4）：`static_cast<OuterAlloc&>(*this)`。
- `allocate`、`deallocate`、`max_size`（¶5–¶8）：全部转发给 `allocator_traits<OuterAlloc>` 与外层分配器。**内层分配器从不为容器自身分配内存。**

### `construct`（¶9）

```cpp
apply([p, this](auto&&... newargs) {
        OUTERMOST_ALLOC_TRAITS(*this)::construct(
          OUTERMOST(*this), p, std::forward<decltype(newargs)>(newargs)...);
      },
      uses_allocator_construction_args<T>(inner_allocator(), std::forward<Args>(args)...));
```

两步：

1. 用 `uses_allocator_construction_args<T>(inner_allocator(), args...)` 把实参改写成"带内层分配器"的形式（[[allocator.uses]]）——前置约定、后置约定或原样，`pair` 逐成员递归；
2. 把改写后的实参交给**最外层分配器**的 `construct`。

第 2 步的意义：如果最外层分配器有自己的 `construct`（例如做日志、或默认初始化），它仍然被调用；`scoped_allocator_adaptor` 只是在中间插入了"注入内层分配器"这一步。

### `destroy`、`select_on_container_copy_construction`（¶10–¶11）

- `destroy(p)`：`OUTERMOST_ALLOC_TRAITS(*this)::destroy(OUTERMOST(*this), p)`。
- `select_on_container_copy_construction()`：返回一个新适配器，其中每一层分配器 `a1` 用 `allocator_traits<A1>::select_on_container_copy_construction(a2)` 初始化（`a2` 是 `*this` 中对应的那层）。

## 相等（[scoped.adaptor.operators]）

`InnerAllocs` 为空时比较外层分配器；否则比较外层**且**比较内层（递归）。

## 示例

```cpp title="scoped-allocator.cpp" ok
#include <scoped_allocator>
#include <vector>
#include <string>
#include <cassert>
#include <new>

template<class T>
struct Tagged {                                  // 有状态分配器：带一个标签
    using value_type = T;
    int tag = 0;
    Tagged() = default;
    explicit Tagged(int t) : tag(t) {}
    template<class U> Tagged(const Tagged<U>& o) noexcept : tag(o.tag) {}
    T* allocate(std::size_t n) { return static_cast<T*>(::operator new(n * sizeof(T))); }
    void deallocate(T* p, std::size_t) noexcept { ::operator delete(p); }
    friend bool operator==(const Tagged& a, const Tagged& b) { return a.tag == b.tag; }
};

using Str = std::basic_string<char, std::char_traits<char>, Tagged<char>>;

int main() {
    // 单个分配器：外层与内层用同一个
    using A1 = std::scoped_allocator_adaptor<Tagged<Str>>;
    std::vector<Str, A1> v1(A1(Tagged<Str>(1)));
    v1.emplace_back("a long string that certainly does not fit in SSO");
    assert(v1[0].get_allocator().tag == 1);      // 元素自动拿到了分配器

    // 两个分配器：外层给 vector，内层给元素
    using A2 = std::scoped_allocator_adaptor<Tagged<Str>, Tagged<char>>;
    std::vector<Str, A2> v2(A2(Tagged<Str>(1), Tagged<char>(2)));
    v2.emplace_back("another long string that does not fit in SSO.....");
    assert(v2.get_allocator().outer_allocator().tag == 1);
    assert(v2[0].get_allocator().tag == 2);

    // 没有适配器：分配器只用于 vector 自己的缓冲区，元素用默认构造的 Tagged<char>
    std::vector<Str, Tagged<Str>> v3(Tagged<Str>(1));
    v3.emplace_back("yet another long string that does not fit in SSO..");
    assert(v3[0].get_allocator().tag == 0);
}
```

`v1` 的元素收到的是 `A1` 的 `inner_allocator()`——即 `A1` 自身——经后置约定 `Str(const char*, const Tagged<char>&)` 转换为 `Tagged<char>`（`uses_allocator<Str, A1>` 为真，因为 `A1` 可转换为 `Str::allocator_type`：适配器派生自 `Tagged<Str>`，而 `Tagged<char>` 可从任何 `Tagged<U>` 转换构造）。

## 与 `pmr` 的比较

| | `scoped_allocator_adaptor<A...>` | `pmr::polymorphic_allocator` |
|---|---|---|
| 分配策略 | 编译期（类型） | 运行期（`memory_resource*`） |
| 嵌套容器的类型 | 每层都要写对应的分配器类型 | 统一 `pmr::` 别名 |
| 每层用不同分配器 | 直接支持 | 需要不同的资源对象，但只能整体传递同一个 |
| 分配开销 | 可内联 | 一次虚函数调用 |
| 传播 | 取各层特征的"或" | 永不传播 |

## 小结

- 外层分配器给容器自身，内层分配器经 uses-allocator 构造传给元素；只给一个分配器时递归复用自身。
- 适配器**派生**自外层分配器；`allocate`/`deallocate` 只用外层。
- 传播特征是各层的"或"，`is_always_equal` 是各层的"与"。
- `construct` 先用 `uses_allocator_construction_args` 注入内层分配器，再交给最外层分配器的 `construct`。
