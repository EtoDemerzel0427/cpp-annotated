---
title: 迭代器库
summary: 第 24 章导读——迭代器是"指针的推广"；C++98 用命名要求（Cpp17InputIterator……）+ 类别标签描述迭代器，C++20 另起一套概念（input_iterator……contiguous_iterator）+ 哨位；两套层次并行存在、判定规则不同，读懂二者的差别是读懂本章的钥匙。
status: done
covers: iterators.general, iterator.synopsis
since: c++98
papers: P0896R4
related: iterator.requirements, iterator.concepts, iterator.cpp17, iterator.assoc.types, iterator.primitives, predef.iterators, stream.iterators, iterator.range, concepts, expr.add
tags: 标准库, 迭代器, 哨位, 概念
updated: 2026-10-18
---

STL 的核心设计是把"数据结构"和"算法"拆开：`N` 个容器、`M` 个算法，中间只靠一个抽象粘合——**迭代器**。算法只说"给我一对能 `++`、能 `*`、能 `==` 的东西"，容器只负责提供这样的东西。于是 `std::find` 写一次，对数组、链表、文件流、`std::map` 都能用。

第 24 章 [iterators] 的任务就是把"这样的东西"精确定义出来：它能做哪些操作、这些操作的**语义**和**复杂度**是什么、怎样在编译期查询它的属性（值类型、差值类型、类别），以及标准库预先提供了哪些迭代器和适配器。

读本章前建议先熟悉：

- 指针算术的核心规则 [[expr.add]]——迭代器的一切语义都是从"指向数组元素的指针"推广出来的；
- 概念库 [[concepts]]（尤其是"满足 vs 建模"和"保持相等性"）——C++20 的迭代器概念全部建立在它之上；
- 库规格的法律元素 [[structure.specifications]]（*Constraints*、*Mandates*、*Preconditions*……）。

## 本章的组织（[iterators.general]）

¶1 交代本章服务的对象：容器（[[containers]]）、流（[[iostream.format]]）、流缓冲（[[stream.buffers]]）以及其他范围（[[ranges]]）。¶2 与表 76 给出五个子条款，全部位于头文件 `<iterator>`：

| 子条款 | 内容 | 本站页面 |
|---|---|---|
| [iterator.requirements] | 迭代器的值（可解引用、过尾、奇异）、范围；关联类型；`iter_move`/`iter_swap`；C++20 迭代器概念；C++17 命名要求；间接可调用概念；通用算法要求 | [[iterator.requirements]]、[[iterator.assoc.types]]、[[iterator.cust]]、[[iterator.concepts]]、[[iterator.cpp17]]、[[indirectcallable]]、[[alg.req]] |
| [iterator.primitives] | 类别标签；`advance`/`distance`/`next`/`prev` 及其 `ranges::` 版本 | [[iterator.primitives]] |
| [predef.iterators] | 迭代器适配器：`reverse_iterator`、插入迭代器、`basic_const_iterator`、`move_iterator`、`common_iterator`、`counted_iterator`、两个哨位类型 | [[predef.iterators]] 及其子页 |
| [stream.iterators] | `istream_iterator`、`ostream_iterator`、`istreambuf_iterator`、`ostreambuf_iterator` | [[stream.iterators]] |
| [iterator.range] | 非成员 `begin`/`end`/`size`/`ssize`/`empty`/`data` | [[iterator.range]] |

## 两套并行的层次：命名要求 vs 概念

这是本章最需要先建立的全局图景。今天的 `<iterator>` 里**同时存在两套**对"迭代器类别"的描述，它们大体对应，但判定方式和细节要求都不同。

### C++98：命名要求 + 类别标签

C++98 用**散文 + 表格**定义了五种迭代器要求：*Cpp17InputIterator*、*Cpp17OutputIterator*、*Cpp17ForwardIterator*、*Cpp17BidirectionalIterator*、*Cpp17RandomAccessIterator*（如今收在 [[iterator.cpp17]]，名字里的 "Cpp17" 前缀是 C++20 加上的，用来与新概念区分）。编译器检查不了表格，所以库另外要求每个迭代器通过 `iterator_traits<I>::iterator_category` **自我申报**一个类别标签（`input_iterator_tag`……），算法用标签做重载分派（[[std.iterator.tags]]）。

这套体系的问题：

- **申报是"信用制"**：类型写了 `random_access_iterator_tag`，库就信它；写错了，就是未定义行为。
- **要求过于捆绑**：*Cpp17ForwardIterator* 要求 `reference` 必须是真正的引用类型（`T&`/`const T&`），于是 `vector<bool>::iterator`、按值返回元素的"生成器"式迭代器，即使能高效地随机访问，按规矩也只能申报为 input。
- **首尾必须同类型**：`[first, last)` 中两个迭代器类型必须相同，以 `'\0'` 结尾的 C 字符串、"读到某个条件为止"这类范围都只能先算出终点再用。

### C++20：概念 + 哨位

Ranges 提案（[[P0896R4]]）引入了一整套迭代器**概念**（[[iterator.concepts]]）：`input_or_output_iterator`、`input_iterator`、`output_iterator`、`forward_iterator`、`bidirectional_iterator`、`random_access_iterator`，再加上全新的第六档 `contiguous_iterator`。与命名要求相比：

- 语法要求由编译器检查，类别仍需申报，但改为通过 *`ITER_CONCEPT`*（[[iterator.concepts]]）读取 `iterator_concept` 成员；
- 不再要求 `reference` 是真引用，代理迭代器可以是随机访问的；
- 不再要求 `input_iterator` 可复制、可 `==` 比较——仅移动的输入迭代器合法；
- 范围的终点由**哨位**（*sentinel*）表示，可以与迭代器类型不同，只需能与迭代器比较（`sentinel_for`）。

¶2 与表 77 给出六个类别的关系：contiguous → random access → bidirectional → forward → input，另有独立的 output。¶3 明确这六类分别对应六个概念；而泛称"迭代器"（*iterator*）指任何建模 `input_or_output_iterator` 的类型。

!!! warning "同一个类型，两套答案可能不同"
    `std::ranges::iota_view<int, int>` 的迭代器建模 `random_access_iterator`，但它的 `iterator_traits<>::iterator_category` 是 `input_iterator_tag`——因为 `*it` 返回 `int` 纯右值，不满足 *Cpp17ForwardIterator* 对 `reference` 的要求。把它交给只认类别标签的老算法（如 `std::prev`、`std::distance`）时，得到的是 input 迭代器待遇。详见 [[iterator.cpp17]] 与 [[iterator.primitives]]。

## 头文件概要（[iterator.synopsis]）

`<iterator>` 概要很长，按功能可分为：

1. **说明专用的基础概念**：*`can-reference`*（`T&` 合法，即 `T` 不是 `void`）、*`dereferenceable`*（`*t` 的结果可引用）。`iter_reference_t<T>` 就定义为 `decltype(*declval<T&>())`，要求 `T` 满足 *`dereferenceable`*。
2. **关联类型**：`incrementable_traits`/`iter_difference_t`、`indirectly_readable_traits`/`iter_value_t`、`iterator_traits`、`iter_reference_t`、`iter_rvalue_reference_t`、`iter_common_reference_t`——见 [[iterator.assoc.types]]。
3. **定制点对象**：`ranges::iter_move`、`ranges::iter_swap`——见 [[iterator.cust]]。
4. **概念**：14 个迭代器概念、6 个间接可调用概念、8 个算法要求概念——见 [[iterator.concepts]]、[[indirectcallable]]、[[alg.req]]。
5. **原语**：6 个类别标签与 `advance`/`distance`/`next`/`prev` 两套版本——见 [[iterator.primitives]]。
6. **适配器与哨位**：见 [[predef.iterators]]。
7. **流迭代器**与**范围访问函数**。

几个值得注意的细节：

- 除流迭代器外，概要中几乎每一项都标注了 `// freestanding`：独立实现（[[g:freestanding-implementation]]）也必须提供它们。流迭代器依赖 `<istream>`/`<ostream>`，不在其列。
- `<iterator>` 必须包含 `<compare>`、`<concepts>`、`<initializer_list>`。
- 迭代器概念本身没有放在 `<concepts>` 而放在 `<iterator>`，因为它们依赖关联类型、`iter_move` 等本章设施。

## 一个例子：哨位让"边界"不再是迭代器

```cpp run title="sentinel.cpp" ok
#include <algorithm>
#include <cassert>
#include <iterator>

int main() {
    const char buf[] = "hello\nworld";
    // 终点不是一个指针，而是"永远不会到达"的哨位：
    // 循环里只剩 *p == '\n' 的判断，没有 p != last 的判断。
    auto nl = std::ranges::find(buf + 0, std::unreachable_sentinel, '\n');
    assert(nl == buf + 5);
}
```

`unreachable_sentinel_t` 与任何 `weakly_incrementable` 类型比较都返回 `false`（[[unreachable.sentinel]]）。前提是程序员**保证**目标一定存在——否则 `find` 会越过数组末尾，是未定义行为。这正是 C++20 迭代器模型的风格：把更多的选择权（和责任）交给调用者。

## 思考题

!!! question "思考题"
    1. 既然 C++20 已经有了概念，为什么 `iterator_traits` 和 *Cpp17* 命名要求没有被弃用？
    2. `contiguous_iterator` 为什么在 C++20 之前一直没有对应的类别标签？只有 `random_access_iterator_tag` 会损失什么？

<details markdown="1">
<summary>展开查看答案与解析</summary>

1. 大量非 `ranges::` 算法（[[algorithms.requirements]]）、容器的迭代器对构造函数、用户代码都通过 `iterator_traits::iterator_category` 做分派；而 C++20 概念对某些类型给出的类别更"高"（代理迭代器），直接替换会改变老代码的重载选择。两套体系并存，各自服务各自的接口：`std::` 算法按命名要求（C++23 起部分放宽为也接受概念，见 [[algorithms.requirements#4]]），`std::ranges::` 算法按概念。
2. 没有标签，库无法在编译期知道"元素在内存中连续"，从而不能安全地把迭代器降级为指针、调用 `memmove`/`memcmp`。实现只能对自己认识的类型（指针、自家 `vector`/`string` 的迭代器）开后门。`contiguous_iterator_tag` 与 `to_address` 一起让这件事对用户类型也成为可能（[[iterator.requirements.general#13]]）。
</details>

## 小结

!!! summary
    - 迭代器是指针的推广；本章形式化它的接口、语义与复杂度。
    - 两套并行体系：*Cpp17XxxIterator* 命名要求 + `iterator_category` 标签（C++98 起）；`xxx_iterator` 概念 + `iterator_concept` + 哨位（C++20 起）。
    - 概念体系放宽了 `reference` 必须为真引用、输入迭代器必须可复制、首尾必须同类型等限制，并新增 `contiguous_iterator`。
    - 同一类型在两套体系中的类别可能不同；老接口看标签，`ranges::` 接口看概念。
