---
title: 指针特征与 to_address
summary: pointer_traits 给裸指针和花式指针提供统一的接口：element_type、difference_type、rebind 怎样从模板实参推出，pointer_to 和可选的 to_address；std::to_address 不解引用，就能把任何类指针对象变回裸指针。
status: done
covers: pointer.traits.general, pointer.traits.types, pointer.traits.functions, pointer.traits.optmem, pointer.conversion
related: memory, allocator.traits, specialized.addressof, unique.ptr, temp.deduct
tags: 标准库, pointer_traits, to_address, 花式指针
papers: P0653R2
updated: 2026-10-19
---

!!! tldr
    - `pointer_traits<P>` 回答一个类指针类型指向什么（`element_type`）、相减得到什么（`difference_type`）、换成指向别的类型是什么（`rebind<U>`）。
    - 类型自己没有声明这些成员时，`pointer_traits` 默认取第一个模板类型实参作为 `element_type`，`rebind` 则替换这个实参。
    - 推不出 `element_type` 的类型得到一个空的 `pointer_traits`，不会硬错误，可以安全地用在 `requires` 表达式里。
    - `std::to_address(p)` 不解引用，经由 `operator->` 或 `pointer_traits::to_address` 得到裸指针，所以对 `end()` 迭代器也能用。

## 花式指针

C++ 的分配器允许 `allocator::pointer` 不是 `T*`，而是一个类类型，叫做**花式指针**（fancy pointer，[[g:fancy-pointer]]）。典型的例子是共享内存里的偏移指针：同一段共享内存在不同进程里映射到不同的地址，存绝对地址没有意义，只能存相对于自身的偏移。Boost.Interprocess 的 `offset_ptr` 就是这样。

容器要对这种指针保持泛型，就要回答几个问题：它指向什么类型？两个指针相减得到什么类型？怎样得到同一种指针、但指向 `Node`？怎样从一个对象的引用得到指向它的花式指针？`pointer_traits` 统一回答这些问题，[[allocator.traits]] 推导 `const_pointer`、`void_pointer`、`difference_type` 也以它为基础。

```cpp run title="pointer-traits.cpp" ok
#include <cassert>
#include <memory>
#include <type_traits>
#include <vector>

template<class T, class Tag = void>
struct Ptr {                       // 一个最简单的花式指针
    T* raw = nullptr;
    T& operator*() const { return *raw; }
    T* operator->() const { return raw; }
    static Ptr pointer_to(T& r) { return Ptr{&r}; }
};

using PT = std::pointer_traits<Ptr<int, char>>;
static_assert(std::is_same_v<PT::element_type, int>);               // 第一个模板实参
static_assert(std::is_same_v<PT::difference_type, std::ptrdiff_t>);  // 默认值
static_assert(std::is_same_v<PT::rebind<long>, Ptr<long, char>>);   // 替换第一个模板实参

// 不是类指针的类型得到一个空的 pointer_traits
template<class P> concept has_elem = requires { typename std::pointer_traits<P>::element_type; };
static_assert(!has_elem<int>);
static_assert(has_elem<int*>);

int main() {
    int x = 42;
    Ptr<int, char> p = PT::pointer_to(x);
    assert(std::to_address(p) == &x);                  // 退回到 p.operator->()
    std::vector<int> v{1, 2, 3};
    assert(std::to_address(v.begin()) == v.data());     // 迭代器也可以
    assert(std::to_address(v.end()) == v.data() + 3);   // 不解引用，end() 也安全
}
```

`Ptr` 没有声明任何成员类型，`pointer_traits` 仍然推出了全部答案。下面逐条看规则。

## 概述 [pointer.traits.general]

¶1 `pointer_traits` 为类指针类型的若干属性提供统一的接口。

裸指针 `T*` 有一个现成的偏特化：`pointer` 是 `T*`，`element_type` 是 `T`，`difference_type` 是 `ptrdiff_t`，`rebind<U>` 是 `U*`，`pointer_to(r)` 返回 `addressof(r)`。主模板的成员则要从 `Ptr` 推导。

## 成员类型怎样推导 [pointer.traits.types]

### 推不出来时整个特化为空（¶1–¶2）

¶1 定义了说明专用的类模板 *ptr-traits-elem* 和概念 *has-elem-type*。¶2 规定，只有 `Ptr` 满足 *has-elem-type* 时，主模板生成的特化才有下面这些成员；否则一个都没有。

这一点由 [[LWG3545]] 确立。在此之前，`pointer_traits<int>` 在实例化时会硬错误，任何检测某类型是不是类指针的代码都会因此编译失败。现在 `pointer_traits<int>` 只是一个空类，上例的 `has_elem<int>` 因而能如实得到 `false`。

### `element_type`（¶4）

`element_type` 是 *ptr-traits-elem*`<Ptr>::type`，按以下顺序确定：

1. 如果有 `Ptr::element_type`，就是它；
2. 否则，如果 `Ptr` 是形如 `SomePointer<T, Args...>` 的类模板特化，就取第一个模板实参 `T`；
3. 否则推不出来，*has-elem-type* 不满足。

第 2 条是一种约定：假设花式指针的第一个类型实参就是被指向的类型，`offset_ptr<T, ...>` 和上例的 `Ptr<T, Tag>` 都符合。它只适用于形参全是类型的模板。`SomePointer<T, Args...>` 中的 `Args` 是类型包，带非类型模板形参的模板（如 `my_ptr<T, 16>`）匹配不上，必须自己声明 `element_type`。

### `difference_type`（¶5）与 `rebind`（¶6）

- ¶5 `difference_type`：如果 `Ptr::difference_type` 有效且是类型，就是它；否则是 `ptrdiff_t`。
- ¶6 `rebind<U>`：如果 `Ptr::rebind<U>` 有效且是类型，就是它；否则，如果 `Ptr` 是 `SomePointer<T, Args...>`，就是 `SomePointer<U, Args...>`；否则实例化 `rebind` 是 {{ill-formed}}。

有效且是类型按模板实参推导的规则判断（[[temp.deduct]]），所以即使 `Ptr::difference_type` 是私有成员或者不是类型，结果也只是退回默认值，不会报错。

```cpp title="rebind-fail.cpp" error
#include <memory>
struct NotTemplate { using element_type = int; };            // 不是模板特化，也没有 rebind 成员
using R = std::pointer_traits<NotTemplate>::rebind<long>;   // error: rebind 的实例化非良构
```

libc++ 用 `static_assert` 报出 Cannot rebind pointer; did you forget to add a rebind member to your pointer?

## `pointer_to` [pointer.traits.functions]

`pointer_to(r)` 从一个对象的引用得到指向它的指针。容器实现里常见的用途是：手里有一个节点对象的引用（例如作为容器成员的哨兵节点），需要得到它的花式指针形式存进链表。

- ¶1 *Mandates*：对主模板，`Ptr::pointer_to(r)` 必须良构。`pointer_traits` 不会替你合成它。
- ¶2 *Preconditions*：`Ptr::pointer_to(r)` 返回的指针确实指向 `r`，并且可以经它访问。
- ¶3 主模板返回 `Ptr::pointer_to(r)`；裸指针版本返回 `addressof(r)`，不是 `&r`（见 [[memory]] 中的 `addressof`）。
- ¶4 如果 `element_type` 是 cv `void`，形参 `r` 的类型未指定；否则是 `element_type&`。`void` 没有引用类型，所以 `pointer_traits<void*>::pointer_to` 没有可移植的调用方式。

[[LWG3454]] 把 `pointer_to` 改成了 `constexpr`。

## 可选成员 `to_address` [pointer.traits.optmem]

¶1 `pointer_traits` 的特化可以定义静态成员 `to_address(pointer p)` 来定制库的行为；主模板生成的特化没有这个成员。¶2 它返回与 `p` 指向同一位置的 `element_type*`。¶3 的注说，它是 `pointer_to` 的逆运算，定义了就会被非成员的 `std::to_address` 使用。

## `std::to_address` [pointer.conversion]

把任意类指针对象变回裸指针，最直接的写法是 `&*p`。它有两个问题：对 `end()` 迭代器或空的花式指针解引用是未定义行为；`operator*` 和 `operator&` 都可能被重载成别的意思。C++20 的 `std::to_address`（[[P0653R2]]）不解引用就能得到地址：

- ¶1–¶2 对裸指针 `T*`，直接返回 `p`；*Mandates* 要求 `T` 不是函数类型，所以 `to_address(&f)` 是 {{ill-formed}}。
- ¶3 对其他类型，如果 `pointer_traits<Ptr>::to_address(p)` 良构就用它，否则返回 `to_address(p.operator->())`。这是递归调用，`operator->` 返回另一个花式指针也没关系。

因为走的是 `operator->` 而不是 `operator*`，对标准库的连续迭代器都可以用 `to_address(it)` 得到元素地址，`end()` 也可以。`contiguous_iterator` 概念（[[iterator.concept.contiguous]]）正是用 `to_address` 表述迭代器与元素地址一一对应的。

!!! pitfall "to_address 不让失效的迭代器变有效"
    `to_address` 本身不解引用，但对已经失效的迭代器做任何操作（包括调用 `operator->`）仍然是未定义行为。

## 思考题

!!! question "思考题 1"
    `template<class T, int N> struct aligned_ptr { T* p; };` 不声明任何成员类型。`pointer_traits<aligned_ptr<int, 16>>::element_type` 是什么？

<details markdown="1">
<summary>答案</summary>

不存在。*ptr-traits-elem* 的第二个偏特化要求形如 `SomePointer<T, Args...>`，其中 `Args...` 是类型模板实参包；`aligned_ptr` 的第二个模板形参是非类型的，匹配失败。于是 *has-elem-type* 不满足，按 ¶2 整个特化没有任何成员。解决办法是在 `aligned_ptr` 里写 `using element_type = T;` 和 `template<class U> using rebind = aligned_ptr<U, N>;`。
</details>

!!! question "思考题 2"
    为什么 `std::to_address` 优先使用 `pointer_traits::to_address`，而不是总用 `operator->`？

<details markdown="1">
<summary>答案</summary>

有些类指针类型在有效但不可解引用时，`operator->` 可能带检查，例如调试模式的迭代器在 `end()` 上调用 `operator->` 会断言失败；有的类型根本没有 `operator->`。给 `pointer_traits` 特化一个 `to_address`，就为这种类型提供了一条只计算地址、不做任何访问检查的途径。libc++ 就为加固模式下带边界检查的迭代器 `__bounded_iter` 特化了 `pointer_traits`，提供不做边界检查的 `to_address`。
</details>

## 小结

| 成员 | 默认来源 | 推不出来时 |
|---|---|---|
| `element_type` | `Ptr::element_type`，否则第一个模板类型实参 | 整个特化没有成员 |
| `difference_type` | `Ptr::difference_type`，否则 `ptrdiff_t` | 不会失败 |
| `rebind<U>` | `Ptr::rebind<U>`，否则替换第一个模板实参 | 实例化非良构 |
| `pointer_to(r)` | 必须由 `Ptr::pointer_to` 提供 | 非良构（*Mandates*） |
| `to_address(p)` | 可选，只有显式特化能提供 | `std::to_address` 退回 `operator->` |
