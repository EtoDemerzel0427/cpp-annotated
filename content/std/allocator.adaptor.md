---
title: scoped_allocator_adaptor
summary: C++11 的作用域分配器适配器：外层分配器给容器自己，内层分配器经 uses-allocator 构造传给元素，从而让嵌套容器的每一层都用上指定的分配器。
status: done
covers: *
related: allocator.uses, allocator.traits, mem.poly.allocator.class, mem.res, container.alloc.reqmts
tags: 标准库, 分配器, scoped_allocator_adaptor
updated: 2026-10-19
---

!!! tldr
    - `scoped_allocator_adaptor<Outer, Inner...>` 把 `Outer` 用于容器自己的内存，把 `Inner...` 依次传给元素、元素的元素。
    - 只给一个分配器时，内层就是适配器本身，所有层递归地共用同一个分配器。
    - 它派生自外层分配器；`allocate`、`deallocate` 只用外层，`construct` 负责把内层分配器注入元素的构造。
    - 传播特征取各层的或，`is_always_equal` 取各层的与。
    - 新代码更常用 `pmr::polymorphic_allocator` 解决同一个问题，但 uses-allocator 构造协议最早就是为这个适配器设计的。

## 要解决的问题

给 `vector<string>` 一个自定义分配器，分配器只管 `vector` 自己的元素数组；每个 `string` 的字符缓冲区仍然用 `string` 自己默认构造出的分配器。想让元素也用指定的分配器，就得在构造每个元素时把分配器传进去。

`scoped_allocator_adaptor`（头文件 `<scoped_allocator>`）在容器构造元素的那一步自动做这件事：

```cpp title="scoped-allocator.cpp" run ok
#include <scoped_allocator>
#include <vector>
#include <string>
#include <cassert>
#include <new>

template<class T>
struct Tagged {                       // 有状态分配器：带一个标签
    using value_type = T;
    int tag = 0;
    Tagged() = default;
    explicit Tagged(int t) : tag(t) {}
    template<class U>
    Tagged(const Tagged<U>& o) noexcept : tag(o.tag) {}
    T* allocate(std::size_t n) {
        return static_cast<T*>(::operator new(n * sizeof(T)));
    }
    void deallocate(T* p, std::size_t) noexcept { ::operator delete(p); }
    friend bool operator==(const Tagged& a, const Tagged& b) {
        return a.tag == b.tag;
    }
};

using Str = std::basic_string<char, std::char_traits<char>, Tagged<char>>;

int main() {
    // 没有适配器：分配器只用于 vector 自己的缓冲区
    std::vector<Str, Tagged<Str>> v0(Tagged<Str>(1));
    v0.emplace_back("a long string that does not fit in SSO.......");
    assert(v0[0].get_allocator().tag == 0);   // 元素用的是默认构造的分配器

    // 一个分配器：外层与内层是同一个
    using A1 = std::scoped_allocator_adaptor<Tagged<Str>>;
    std::vector<Str, A1> v1(A1(Tagged<Str>(1)));
    v1.emplace_back("a long string that does not fit in SSO.......");
    assert(v1[0].get_allocator().tag == 1);   // 元素自动拿到了分配器

    // 两个分配器：外层给 vector，内层给元素
    using A2 = std::scoped_allocator_adaptor<Tagged<Str>, Tagged<char>>;
    std::vector<Str, A2> v2(A2(Tagged<Str>(1), Tagged<char>(2)));
    v2.emplace_back("a long string that does not fit in SSO.......");
    assert(v2.get_allocator().outer_allocator().tag == 1);
    assert(v2[0].get_allocator().tag == 2);
}
```

`v1` 构造元素时，适配器把自己的内层分配器（这里就是 `A1` 本身）追加到实参末尾，元素实际按 `Str(const char*, const Tagged<char>&)` 构造。这能成立，是因为 `A1` 派生自 `Tagged<Str>`，可以转换成 `Str` 的分配器类型 `Tagged<char>`，于是 `uses_allocator<Str, A1>` 为真（[[allocator.uses]]）。

## 外层与内层 [allocator.adaptor.syn]

¶1 适配器用一个外层分配器类型和零个或多个内层分配器类型实例化：

- 只有一个分配器类型时，内层分配器就是适配器自己。容器、元素、元素的元素……递归地都用同一个分配器。
- 有多个时，第一个给容器，第二个传给元素的构造函数，第三个传给元素的元素，依此类推。嵌套深度超过分配器个数时，最后一个被重复使用。

注 1 指出，适配器**派生自**外层分配器类型，因此大多数表达式里可以拿它当外层分配器用。

```cpp
template<class OuterAlloc, class... InnerAllocs>
class scoped_allocator_adaptor : public OuterAlloc {
  using OuterTraits = allocator_traits<OuterAlloc>;   // exposition only
  scoped_allocator_adaptor<InnerAllocs...> inner;     // exposition only
  // ...
};
```

说明用成员 `inner` 本身也是一个适配器，所以结构是递归的：`scoped_allocator_adaptor<A, B, C>` 内含 `scoped_allocator_adaptor<B, C>`，后者内含 `scoped_allocator_adaptor<C>`。只有一个分配器时，`inner_allocator()` 返回 `*this`。

`value_type`、`pointer` 等成员类型都取自外层分配器的 traits。`rebind<Tp>::other` 只重绑定外层分配器，内层类型不变。类模板还有推导指引 `scoped_allocator_adaptor(OuterAlloc, InnerAllocs...)`。

## 成员类型 [allocator.adaptor.types]

¶1 `inner_allocator_type` 在没有内层分配器时是 `scoped_allocator_adaptor<OuterAlloc>`，否则是 `scoped_allocator_adaptor<InnerAllocs...>`。

¶2–¶4 三个传播特征（`propagate_on_container_copy_assignment`、`_move_assignment`、`_swap`）只要外层或任何一个内层的对应特征为真，就是 `true_type`。容器赋值或交换时，只要有一层需要跟着容器走，整个适配器就必须跟着走，否则那一层会和它分配的内存分开。

¶5 `is_always_equal` 要求每一层都为真才是 `true_type`。只有每一层都总是相等，整个适配器才总是相等。

## 构造 [allocator.adaptor.cnstr]

¶1 默认构造函数值初始化外层基类和 `inner`。

¶2–¶3 主构造函数 `(OuterA2&& outerAlloc, const InnerAllocs&... innerAllocs)` 要求 `OuterAlloc` 能从 `OuterA2` 构造，它用 `outerAlloc` 初始化基类，用 `innerAllocs...` 递归地初始化 `inner`。

¶4–¶9 复制、移动，以及从外层类型不同的适配器转换（`rebind` 之后需要），都是逐层用对应的分配器初始化。所有构造函数都是 `noexcept`，因为分配器的复制和移动本来就不允许抛出。

## 成员函数 [allocator.adaptor.members]

### 容器自己的内存只用外层（¶2–¶8）

¶2 `inner_allocator()` 没有内层时返回 `*this`，否则返回 `inner`。¶3–¶4 `outer_allocator()` 返回 `static_cast<OuterAlloc&>(*this)`。

¶5–¶8 `allocate`、`deallocate`、`max_size` 全部转发给外层分配器。内层分配器从不为容器自己分配内存。

### 找到最外层（¶1）

¶1 外层分配器本身也可能是一个 `scoped_allocator_adaptor`。为了找到真正负责构造的那一个，标准定义了说明用的 *OUTERMOST*(x)：如果 `x.outer_allocator()` 是有效表达式，就是 *OUTERMOST*(`x.outer_allocator()`)，否则就是 `x`。*OUTERMOST_ALLOC_TRAITS*(x) 是它的 `allocator_traits`。

注 1 说明这是递归定义，靠 `outer_allocator()` 的定义保证终止；对所有 `scoped_allocator_adaptor` 的实例化它都会终止。

### `construct`：注入内层分配器（¶9）

```cpp
apply([p, this](auto&&... newargs) {
        OUTERMOST_ALLOC_TRAITS(*this)::construct(
          OUTERMOST(*this), p, std::forward<decltype(newargs)>(newargs)...);
      },
      uses_allocator_construction_args<T>(inner_allocator(),
                                          std::forward<Args>(args)...));
```

¶9 构造分两步：

1. `uses_allocator_construction_args<T>(inner_allocator(), args...)` 把实参改写成带内层分配器的形式：分配器放在前面、放在末尾，或者原样不动，`pair` 则逐成员递归处理（[[allocator.uses]]）。
2. 改写后的实参交给最外层分配器的 `construct`。

第 2 步保证最外层分配器自己的 `construct` 仍然会被调用，比如它要记日志或改用默认初始化。适配器只是在中间加了注入内层分配器这一步。

### `destroy` 与复制容器（¶10–¶11）

¶10 `destroy(p)` 交给最外层分配器的 `destroy`。

¶11 `select_on_container_copy_construction()` 返回一个新适配器，其中每一层都用该层分配器的 `select_on_container_copy_construction` 结果初始化。

## 相等 [scoped.adaptor.operators]

¶1 没有内层时只比较外层分配器；否则外层和内层（递归地）都相等才相等。

## 与 `pmr` 的比较

C++17 的 `pmr::polymorphic_allocator`（[[mem.poly.allocator.class]]）也通过 uses-allocator 构造把分配器传给元素，但策略放在运行期的 `memory_resource*` 里：

| | `scoped_allocator_adaptor<A...>` | `pmr::polymorphic_allocator` |
|---|---|---|
| 分配策略 | 编译期，由类型决定 | 运行期，由 `memory_resource*` 决定 |
| 嵌套容器的类型 | 每层都要写出对应的分配器类型 | 统一用 `pmr::` 别名 |
| 各层用不同的分配器 | 直接支持 | 自动传递时所有层共用同一个资源 |
| 分配开销 | 可以内联 | 一次虚函数调用 |
| 赋值与交换时传播 | 取各层特征的或 | 永不传播 |

## 小结

- 外层分配器给容器自己，内层分配器经 uses-allocator 构造传给元素；只给一个分配器时递归复用自己。
- 适配器派生自外层分配器，`allocate`、`deallocate` 只用外层。
- 传播特征是各层的或，`is_always_equal` 是各层的与。
- `construct` 先用 `uses_allocator_construction_args` 注入内层分配器，再交给最外层分配器的 `construct`。
