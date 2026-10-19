---
title: 容器库
summary: 第 23 章导读：容器要求、序列容器、关联容器、无序容器、容器适配器和视图六个部分；一份容器契约要从复杂度、迭代器失效、异常安全、分配器四个方面去读。
status: done
covers: containers.general
related: container.requirements, sequences, associative, unord, container.adaptors, views, mem, iterators
tags: 标准库, 容器, 导读
updated: 2026-10-19
---

!!! tldr
    - 具体容器的条款都很短，大部分语义写在 [[container.requirements]] 的几组通用要求里。读一个容器，要把通用要求和这个容器自己的补充条款合起来看。
    - 一个容器的契约可以归成四类：复杂度、迭代器和引用何时失效、异常安全保证、怎样使用分配器。
    - 容器函数的前置条件有几种强度：*Constraints* 不满足时重载不可行，*Mandates* 不满足时编译报错，*Preconditions* 违反时是 UB，C++26 的加固前置条件在加固实现中会终止程序。
    - `basic_string`、`bitset`、`valarray` 不在这一章，但 `basic_string` 满足本章的容器要求。

## 本章的组成（[containers.general]）

¶1 这一章描述程序用来组织一组信息的组件。¶2 的表 74 列出了它的六个部分：

| 子条款 | 内容 | 头文件 | 本站笔记 |
|---|---|---|---|
| [container.requirements] | 通用、分配器感知、序列、关联、无序容器的要求；节点句柄 | 无 | [[container.requirements]]、[[container.requirements.general]]、[[sequence.reqmts]]、[[container.node]]、[[associative.reqmts]]、[[unord.req]] |
| [sequences] | 序列容器 | `<array>` `<deque>` `<forward_list>` `<hive>` `<inplace_vector>` `<list>` `<vector>` | [[sequences]]、[[array]]、[[deque]]、[[forward.list]]、[[hive]]、[[list]]、[[vector]]、[[vector.bool]]、[[inplace.vector]] |
| [associative] | 有序关联容器 | `<map>` `<set>` | [[associative]] |
| [unord] | 无序关联容器 | `<unordered_map>` `<unordered_set>` | [[unord]] |
| [container.adaptors] | 容器适配器 | `<queue>` `<stack>` `<flat_map>` `<flat_set>` | [[container.adaptors]]、[[flat.map]]、[[flat.set]] |
| [views] | 视图 | `<span>` `<mdspan>` | [[views]]、[[views.contiguous]]、[[views.multidim]] |

有几个常被当作容器的类型不在这一章：`basic_string` 在第 27 章（[[basic.string]]），但满足本章的连续容器和分配器感知容器要求；`bitset` 在第 22 章；`valarray` 在第 29 章；`basic_stacktrace` 在第 19 章，满足分配器感知容器要求。迭代器概念和 range 适配器分别在第 24、25 章（[[iterators]]、[[ranges]]）。

## 读一份容器契约的四个方面

具体容器的规定几乎都属于下面四类之一，本站各容器页也按这四类组织：

1. **复杂度**。标准只数对元素的操作次数（[[container.requirements]]），但这些要求实际上决定了数据结构：`vector` 必须几何增长，`deque` 必须分块，`unordered_map` 必须每个元素一个节点。
2. **失效**。哪些操作使哪些迭代器、指针、引用不再有效。总原则是没有规定会失效的就不失效（[[container.reqmts#67]]）。
3. **异常安全**。默认是单元素插入抛异常时没有效果、擦除不抛异常（[[container.reqmts#66]]），`vector`、`deque`、关联容器和无序容器各有例外。
4. **分配器**。元素只能经由 `allocator_traits::construct` 和 `destroy` 构造、销毁；拷贝、移动、赋值、交换时分配器怎样传递，由三个 propagate 特征决定（[[container.requirements.general]]）。分配器本身的协议见 [[mem]] 和 [[allocator.traits]]。

[[container.requirements]] 把各容器在后三方面的规定整理成了对照表。

## 前置条件的几种强度

本章的函数说明使用 [[structure.specifications]] 定义的几种元素，违反的后果各不相同：

| 元素 | 例子 | 违反的后果 |
|---|---|---|
| *Constraints* | `insert(InputIterator, InputIterator)` 要求实参能当作输入迭代器；`container-compatible-range` | 不参与重载决议 |
| *Mandates* | `vector<T, A>` 要求 `A::value_type` 是 `T` | 非良构，必须诊断 |
| *Preconditions* | `insert(p, i, j)` 的 `i`、`j` 不指向容器自身；元素类型满足 *Cpp17CopyInsertable* | {{ub}}；类型要求不满足时通常表现为实例化错误 |
| *Hardened preconditions* {{c++26}} | `front()`、`back()`、`pop_*`、`operator[]` 要求非空、不越界 | 加固实现中终止程序，否则是 UB |

## 历史与演进

| 版本 | 本章的主要变化 |
|---|---|
| C++98 | STL 进入标准：`vector`、`deque`、`list`、`set`、`map` 及其 multi 版本，`stack`、`queue`、`priority_queue`，`vector<bool>` |
| C++11 | `array`、`forward_list`、`unordered_*`；移动语义与 `emplace`；`allocator_traits`；`size()` 必须是常数复杂度；`initializer_list` 构造 |
| C++14 | 关联容器的异构查找（透明比较器） |
| C++17 | 节点句柄 `extract`、`merge`；`try_emplace`、`insert_or_assign`；`std::pmr` 别名；`vector`、`list`、`forward_list` 允许不完整的元素类型 |
| C++20 | `std::erase`、`erase_if`；`contains`；`constexpr` 的 `vector`；`<=>`；`span`；无序容器的异构查找 |
| C++23 | `flat_map`、`flat_set`；`mdspan`；`from_range` 构造和 `*_range` 成员函数；`stack`、`queue` 的迭代器对构造 |
| C++26 | `inplace_vector`、`hive`；标准库加固；`deque`、`list`、`forward_list`、关联容器、无序容器和容器适配器可以在常量求值中使用；关联容器的异构插入；`span::at`；`submdspan` |

本机 libc++（Clang 23）对 C++26 的部分只有部分支持。`list`、`forward_list`、`map`、`set`、`flat_map`、`flat_set`、`queue` 的 `constexpr` 已经实现（对应的 `__cpp_lib_constexpr_*` 宏为 `202502L`），`deque` 还没有；`<inplace_vector>` 和 `<hive>` 尚未提供；关联容器的异构插入也未实现。

```cpp title="constexpr-containers.cpp" run ok
#include <list>
#include <map>
#include <vector>

constexpr int sum() {
  std::list<int> l{1, 2, 3};
  std::map<int, int> m{{1, 10}, {2, 20}};
  std::vector<int> v(l.begin(), l.end());
  int s = 0;
  for (int x : v) s += x;
  return s + m.at(2);
}
static_assert(sum() == 26);
int main() {}
```
