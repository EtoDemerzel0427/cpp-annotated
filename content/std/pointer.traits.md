---
title: 指针特征与 to_address
summary: pointer_traits 为"花式指针"提供统一接口——element_type、difference_type、rebind 如何从模板实参推出，pointer_to 与可选的 to_address；std::to_address 不解引用地把任何类指针对象变回裸指针
status: done
covers: pointer.traits.general, pointer.traits.types, pointer.traits.functions, pointer.traits.optmem, pointer.conversion
related: memory, allocator.traits, specialized.addressof, unique.ptr, temp.deduct
tags: 标准库, pointer_traits, to_address, 花式指针
papers: P0653R2
updated: 2026-10-18
---

C++ 的分配器模型允许 `allocator::pointer` 不是 `T*`，而是一个类类型——**花式指针**（[[g:fancy-pointer]]）。典型例子是共享内存里的**偏移指针**：同一段共享内存在不同进程中映射到不同地址，存绝对地址没有意义，只能存"相对于自身的偏移"。Boost.Interprocess 的 `offset_ptr` 就是这样的东西。

容器要对这种指针保持泛型，就需要回答几个问题：它指向什么类型？两个指针相减得到什么类型？我要一个"同款但指向 `Node` 的指针"怎么写？怎么从一个对象引用得到指向它的花式指针？`pointer_traits` 就是这些问题的统一答案；它也是 [[allocator.traits]] 推导 `const_pointer`、`void_pointer`、`difference_type` 的基础。

## 概述（[pointer.traits.general]）

¶1：`pointer_traits` 为类指针类型的若干属性提供统一接口。对裸指针 `T*` 有一个现成的偏特化：`pointer = T*`、`element_type = T`、`difference_type = ptrdiff_t`、`rebind<U> = U*`，`pointer_to(r)` 返回 `addressof(r)`。

主模板的成员则需要"推导"。

## 成员类型怎么推导（[pointer.traits.types]）

### ¶1–¶2：SFINAE 友好的前提

¶1 定义了说明用的 `ptr-traits-elem<T>` 与概念 `has-elem-type`。¶2 规定：只有当 `Ptr` 满足 `has-elem-type` 时，主模板生成的特化才有下列成员；否则**一个都没有**。这一点由 [[LWG3545]] 确立——在此之前，`pointer_traits<int>` 会在实例化时硬错误，任何"检测某类型是不是类指针"的代码都会被它炸掉。现在 `pointer_traits<int>` 只是一个空类，可以安全地用在 `requires` 表达式里。

### `element_type`（¶4）

`ptr-traits-elem<Ptr>::type` 按以下顺序确定：

1. `Ptr::element_type`，若存在；
2. 否则，若 `Ptr` 是形如 `SomePointer<T, Args...>` 的类模板特化（且 `SomePointer<T, Args...>::element_type` 不存在），取**第一个模板实参** `T`；
3. 否则没有（`has-elem-type` 不满足）。

第 2 条是个启发式：它假设"花式指针的第一个类型实参就是被指类型"。`offset_ptr<T, ...>`、`Ptr<T, Tag>` 都满足这个约定。注意它只对**类型**模板形参的模板有效——`SomePointer<T, Args...>` 里 `Args` 是类型包，带非类型模板形参的模板（如 `my_ptr<T, 16>`）匹配不上，必须自己提供 `element_type`。

### `difference_type`（¶5）与 `rebind`（¶6）

- `difference_type`：`Ptr::difference_type`，否则 `ptrdiff_t`。
- `rebind<U>`：`Ptr::rebind<U>`，否则若 `Ptr` 是 `SomePointer<T, Args...>`，就是 `SomePointer<U, Args...>`（替换第一个实参）；否则**实例化 `rebind` 是 {{ill-formed}}**。

这里"有效且表示类型"的判断用的是模板实参推导的 SFINAE 语境（[[temp.deduct]]），所以 `Ptr::difference_type` 若是私有成员或不是类型，也只会退回默认值，不会报错。

```cpp title="pointer-traits.cpp" ok
#include <memory>
#include <type_traits>
#include <vector>
#include <cassert>

template<class T, class Tag = void>
struct Ptr {                       // 一个最简"花式指针"
    T* raw = nullptr;
    T& operator*() const { return *raw; }
    T* operator->() const { return raw; }
    static Ptr pointer_to(T& r) { return Ptr{&r}; }
};

using PT = std::pointer_traits<Ptr<int, char>>;
static_assert(std::is_same_v<PT::element_type, int>);              // 取第一个模板实参
static_assert(std::is_same_v<PT::difference_type, std::ptrdiff_t>); // 默认
static_assert(std::is_same_v<PT::rebind<long>, Ptr<long, char>>);  // 替换第一个模板实参

// SFINAE 友好：不是"类指针"的类型得到一个空的 pointer_traits
template<class P> concept has_elem = requires { typename std::pointer_traits<P>::element_type; };
static_assert(!has_elem<int>);
static_assert(has_elem<int*>);

int main() {
    int x = 42;
    Ptr<int, char> p = PT::pointer_to(x);
    assert(std::to_address(p) == &x);                  // 没有 pointer_traits::to_address，退回 p.operator->()
    std::vector<int> v{1, 2, 3};
    assert(std::to_address(v.begin()) == v.data());     // 迭代器也行
    assert(std::to_address(v.end()) == v.data() + 3);   // 不解引用，所以 end() 也安全
}
```

```cpp title="rebind-fail.cpp" error
#include <memory>
struct NotTemplate { using element_type = int; };            // 不是模板特化、没有 rebind 成员
using R = std::pointer_traits<NotTemplate>::rebind<long>;   // error: rebind 的实例化非良构
```

libc++ 用 `static_assert` 报出"Cannot rebind pointer; did you forget to add a rebind member to your pointer?"。

## `pointer_to`（[pointer.traits.functions]）

`pointer_to(r)` 是"从对象引用得到指向它的指针"。

- ¶1 *Mandates*：对主模板，`Ptr::pointer_to(r)` 必须良构——`pointer_traits` 不会替你合成它。
- ¶2 *Preconditions*：`Ptr::pointer_to(r)` 返回的指针确实指向 `r`、可以解引用。
- ¶3：裸指针版本返回 `addressof(r)`（不是 `&r`，见 [[memory]] 中 `addressof` 一节）。
- ¶4：若 `element_type` 是 cv `void`，`r` 的类型未指明；否则是 `element_type&`。`void` 没有引用类型，所以 `pointer_traits<void*>::pointer_to` 实际上不可调用。

C++26 期间 [[LWG3454]] 把 `pointer_to` 改为 `constexpr`。容器实现里最常见的用途是：手头有一个节点对象的引用（例如哨兵节点就是容器的一个成员），需要得到它的**花式指针**形式来存入链表。

## 可选成员 `to_address`（[pointer.traits.optmem]）

¶1：`pointer_traits` 的特化**可以**定义静态成员 `to_address(pointer p)`，以定制库的行为；主模板生成的特化**没有**这个成员。¶2：它返回与 `p` 指向同一位置的 `element_type*`。¶3 的注：它意在作为 `pointer_to` 的逆运算，若定义了就会被非成员 `std::to_address` 使用。

## `std::to_address`（[pointer.conversion]）

C++20 引入（[[P0653R2]]），解决的问题是：**怎样把任意类指针对象变回裸指针，而不解引用它**？

最朴素的写法 `&*p` 有两个毛病：对 `end()` 迭代器或空花式指针解引用是 UB；而且 `operator*` 可能被重载成别的意思。`to_address` 的规则：

- ¶1–¶2：对裸指针 `T*`，直接返回 `p`；*Mandates* `T` 不是函数类型（`to_address(&f)` 是 {{ill-formed}}）。
- ¶3：对其他类型，若 `pointer_traits<Ptr>::to_address(p)` 良构就用它，否则返回 `to_address(p.operator->())`——**递归**调用，因此 `operator->` 返回另一个花式指针也没关系。

因为走的是 `operator->` 而不是 `operator*`，标准库对**连续迭代器**普遍可以用 `to_address(it)` 得到元素地址，包括 `end()`。`contiguous_iterator` 概念（[[iterator.concept.contiguous]]）正是用 `to_address` 来表述"迭代器与元素地址一一对应"的。

!!! pitfall "to_address 不检查有效性"
    `to_address` 本身不解引用，但它也不让悬空指针变得有效。对已失效的迭代器调用 `to_address` 虽然通常"能跑"，但按迭代器的规则，对失效迭代器做任何操作（包括 `operator->`）都是 UB。

!!! impl "libc++"
    libc++ 的 `std::to_address` 先检测 `pointer_traits<P>::to_address` 是否可用，否则检测 `P` 是否有 `operator->`，然后递归 `__to_address`；`to_address(T*)` 中用 `static_assert(!is_function<T>)` 实现 *Mandates*。

## 思考题

<details markdown="1">
<summary>1. `template<class T, int N> struct aligned_ptr { T* p; };` 不写任何成员类型，`pointer_traits<aligned_ptr<int, 16>>::element_type` 是什么？</summary>

不存在。`ptr-traits-elem` 的第二个偏特化要求形如 `SomePointer<T, Args...>`，其中 `Args...` 是**类型**模板实参包；`aligned_ptr` 的第二个模板形参是非类型的，匹配失败。于是 `has-elem-type` 不满足，按 ¶2 整个特化没有任何成员。解决办法是在 `aligned_ptr` 里写 `using element_type = T;` 以及 `template<class U> using rebind = aligned_ptr<U, N>;`。
</details>

<details markdown="1">
<summary>2. 为什么 `std::to_address` 在 ¶3 里优先用 `pointer_traits::to_address`，而不是总用 `operator->`？</summary>

因为有些类指针类型**有效但不可解引用**时，`operator->` 可能带检查（例如调试模式迭代器在 `end()` 上调用 `operator->` 会断言失败），或者根本没有 `operator->`。给 `pointer_traits` 写一个 `to_address` 特化，等于为这种类型提供了一个"不经过任何访问检查的纯地址计算"通道。标准库实现常为自己的调试迭代器做这种特化。
</details>

## 小结

| 成员 | 默认来源 | 失败时 |
|---|---|---|
| `element_type` | `Ptr::element_type` → 第一个模板类型实参 | 整个特化无成员（SFINAE 友好） |
| `difference_type` | `Ptr::difference_type` → `ptrdiff_t` | — |
| `rebind<U>` | `Ptr::rebind<U>` → 替换第一个模板实参 | 实例化 {{ill-formed}} |
| `pointer_to(r)` | 必须由 `Ptr::pointer_to` 提供（*Mandates*） | {{ill-formed}} |
| `to_address(p)` | 可选，仅显式特化可提供 | `std::to_address` 退回 `operator->` |
