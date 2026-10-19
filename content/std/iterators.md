---
title: 迭代器库
summary: 第 24 章导读：迭代器是指针的推广；标准里并存两套描述迭代器的方式，C++98 的命名要求加类别标签，C++20 的概念加哨位，同一个类型在两套里可能被归入不同的类别。
status: done
covers: iterators.general, iterator.synopsis
since: c++98
papers: P0896R4
related: iterator.requirements, iterator.concepts, iterator.cpp17, iterator.assoc.types, iterator.primitives, predef.iterators, stream.iterators, iterator.range, concepts, expr.add
tags: 标准库, 迭代器, 哨位, 概念
updated: 2026-10-19
---

!!! tldr
    - 迭代器把容器和算法分开：算法只要求能 `++`、`*`、`==` 的东西，于是同一个 `std::find` 能用于数组、链表和流。
    - C++98 用写在表格里的命名要求（*Cpp17InputIterator* 等）描述迭代器，类型通过 `iterator_category` 标签自报类别。
    - C++20 另有一套由编译器检查的概念（`input_iterator` 到 `contiguous_iterator`），并允许范围的终点是类型不同的哨位。
    - 两套体系同时有效：`std::` 算法看命名要求，`std::ranges::` 算法看概念；同一个迭代器在两边的类别可以不同。
    - `<iterator>` 里除流迭代器外几乎都是 freestanding，独立实现也要提供。

## 迭代器解决什么问题

```cpp run title="sentinel.cpp" ok
#include <algorithm>
#include <cassert>
#include <iterator>

int main() {
  const char buf[] = "hello\nworld";
  auto nl = std::ranges::find(buf + 0, std::unreachable_sentinel, '\n');
  assert(nl == buf + 5);
}
```

`std::ranges::find` 不知道 `buf` 是数组。它只需要一个能递增、解引用、与终点比较的起点，加上一个终点。**迭代器**（iterator）就是对这种起点的抽象，它的语义从指向数组元素的指针推广而来（[[expr.add]]）。这样 `N` 个容器和 `M` 个算法只需要写 `N + M` 份代码，而不是 `N × M` 份。

上例的终点不是指针，而是 `std::unreachable_sentinel`：一个与任何迭代器比较都返回 `false` 的对象（[[unreachable.sentinel]]）。循环里因此只剩 `*p == '\n'` 一个判断。代价是调用者必须保证 `'\n'` 一定存在，否则 `find` 会越过数组末尾，行为未定义。

第 24 章 [iterators] 把迭代器能做哪些操作、这些操作的语义和复杂度、怎样在编译期查询它的属性都精确地写了出来，并提供一批现成的迭代器和适配器。

## 本章的组织 [iterators.general]

¶1 本章的组件服务于对容器（[[containers]]）、流（[[iostream.format]]）、流缓冲（[[stream.buffers]]）和其他范围（[[ranges]]）的遍历。

¶2 表 76 列出五个子条款，全部在头文件 `<iterator>` 中：

| 子条款 | 内容 | 本站页面 |
|---|---|---|
| [iterator.requirements] | 迭代器的值与范围；关联类型；`iter_move`/`iter_swap`；C++20 迭代器概念；C++17 命名要求；间接可调用概念；算法的通用要求 | [[iterator.requirements]]、[[iterator.assoc.types]]、[[iterator.cust]]、[[iterator.concepts]]、[[iterator.cpp17]]、[[indirectcallable]]、[[alg.req]] |
| [iterator.primitives] | 类别标签；`advance`/`distance`/`next`/`prev` 及其 `ranges::` 版本 | [[iterator.primitives]] |
| [predef.iterators] | 迭代器适配器：`reverse_iterator`、插入迭代器、`basic_const_iterator`、`move_iterator`、`common_iterator`、`counted_iterator`，以及两个哨位类型 | [[predef.iterators]] |
| [stream.iterators] | `istream_iterator`、`ostream_iterator`、`istreambuf_iterator`、`ostreambuf_iterator` | [[stream.iterators]] |
| [iterator.range] | 非成员 `begin`/`end`/`size`/`ssize`/`empty`/`data` | [[iterator.range]] |

## 两套并行的分类

### C++98：命名要求加类别标签

C++98 用文字和表格定义了五种要求：*Cpp17InputIterator*、*Cpp17OutputIterator*、*Cpp17ForwardIterator*、*Cpp17BidirectionalIterator*、*Cpp17RandomAccessIterator*，今天收在 [[iterator.cpp17]]。名字里的 Cpp17 前缀是 C++20 加的，用来和新概念区分。

编译器检查不了表格，所以每个迭代器还要通过 `iterator_traits<I>::iterator_category` 自报一个**类别标签**，例如 `random_access_iterator_tag`。算法根据标签选择重载（[[std.iterator.tags]]）。这套做法有三个问题：

- 标签只是声明。一个类型声称自己是随机访问迭代器，库就照此使用；声明错了，行为未定义。
- 要求捆绑得太紧。*Cpp17ForwardIterator* 要求 `*it` 返回真正的引用，所以 `vector<bool>::iterator` 和按值返回元素的迭代器，即使能常数时间随机访问，按规定也只能算输入迭代器。
- 起点和终点必须同类型。以 `'\0'` 结尾的字符串只能先算出终点，再交给算法。

### C++20：概念加哨位

Ranges 提案 [[P0896R4]] 引入了一组迭代器**概念**（[[iterator.concepts]]）：`input_or_output_iterator`、`input_iterator`、`output_iterator`、`forward_iterator`、`bidirectional_iterator`、`random_access_iterator`，以及新的一档 `contiguous_iterator`（元素在内存中连续）。和命名要求相比：

- 语法要求由编译器检查。类别仍需声明，但读的是 `iterator_concept` 成员（规则见 [[iterator.concepts]] 的 *ITER_CONCEPT*）。
- `*it` 不必返回真引用，所以返回代理对象的迭代器也可以是随机访问的。
- `input_iterator` 不要求可复制，也不要求能用 `==` 比较，只能移动的输入迭代器也合法。
- 范围的终点可以是**哨位**（sentinel）：类型可以和迭代器不同，只要二者能比较（`sentinel_for`）。

六个类别的包含关系是 contiguous → random access → bidirectional → forward → input，output 单独一支（[[iterator.requirements.general#2]]）。泛称的迭代器指任何建模 `input_or_output_iterator` 的类型。

!!! warning "同一个类型，两套答案可能不同"
    `std::ranges::iota_view<int, int>` 的迭代器建模 `random_access_iterator`，但它的 `iterator_traits<>::iterator_category` 是 `input_iterator_tag`，因为 `*it` 返回 `int` 纯右值，不满足 *Cpp17ForwardIterator* 对引用的要求。把它交给只看标签的 `std::distance`、`std::prev` 等函数，它得到的是输入迭代器的待遇。详见 [[iterator.cpp17]] 与 [[iterator.primitives]]。

## 头文件 `<iterator>` [iterator.synopsis]

概要按功能可以分成几组，各自在后面的页面详细讲：

| 组 | 主要内容 | 详见 |
|---|---|---|
| 关联类型 | `iter_difference_t`、`iter_value_t`、`iterator_traits`、`iter_reference_t`、`iter_rvalue_reference_t`、`iter_common_reference_t` | [[iterator.assoc.types]] |
| 定制点对象 | `ranges::iter_move`、`ranges::iter_swap` | [[iterator.cust]] |
| 概念 | 13 个迭代器概念（从 `indirectly_readable` 到 `contiguous_iterator`）、6 个间接可调用概念、9 个算法要求概念（从 `indirectly_movable` 到 `sortable`） | [[iterator.concepts]]、[[indirectcallable]]、[[alg.req]] |
| 原语 | 6 个类别标签，`advance`/`distance`/`next`/`prev` 的两套版本 | [[iterator.primitives]] |
| 适配器与哨位 | `reverse_iterator` 到 `unreachable_sentinel_t` | [[predef.iterators]] |
| 流迭代器、范围访问 | `istream_iterator` 等；`std::begin` 等 | [[stream.iterators]]、[[iterator.range]] |

概要开头定义了两个仅用于说明的概念：*can-reference*（`T&` 合法，即 `T` 不是 `void`）和 *dereferenceable*（`*t` 的结果满足 *can-reference*）。`iter_reference_t<T>` 定义为 `decltype(*declval<T&>())`，要求 `T` 满足 *dereferenceable*。

除流迭代器外，概要里几乎每一项都标了 `// freestanding`，独立实现（[[g:freestanding-implementation]]）也必须提供。流迭代器依赖 `<istream>`/`<ostream>`，不在其列。`<iterator>` 必须包含 `<compare>`、`<concepts>` 和 `<initializer_list>`。迭代器概念放在 `<iterator>` 而不是 `<concepts>`，因为它们依赖关联类型和 `iter_move` 这些本章才定义的设施。

## 思考题

!!! question "思考题 1"
    既然 C++20 已经有了概念，为什么 `iterator_traits` 和 *Cpp17* 命名要求没有被弃用？

<details markdown="1">
<summary>答案</summary>

大量 `std::` 算法（[[algorithms.requirements]]）、容器的迭代器对构造函数和用户代码都通过 `iterator_category` 分派。C++20 概念对代理迭代器给出的类别更高，直接替换会改变老代码选中的重载。所以两套并存：`std::` 算法按命名要求（[[algorithms.requirements#4]] 允许不修改元素的前向迭代器参数改为建模 `forward_iterator`），`std::ranges::` 算法按概念。
</details>

!!! question "思考题 2"
    C++20 之前只有 `random_access_iterator_tag`，没有连续迭代器的标签。这会损失什么？

<details markdown="1">
<summary>答案</summary>

库无法在编译期知道元素在内存中连续，也就不能把迭代器换成指针去调用 `memmove`、`memcmp`。实现只能为自己认识的类型（指针、自家 `vector`/`string` 的迭代器）开特例。`contiguous_iterator_tag` 和 `std::to_address` 让用户类型也能得到这种优化（[[iterator.requirements.general#13]]）。
</details>
