---
title: 容器库
summary: 第 23 章导读——要求、序列容器、关联容器、无序容器、容器适配器、视图六大部分的地图；容器契约的四个维度（复杂度、失效、异常安全、分配器）；C++11 到 C++26 的演进与 constexpr 化
status: done
covers: containers.general
related: container.requirements, sequences, associative, unord, container.adaptors, views, mem, iterators
tags: 标准库, 容器, 导读
updated: 2026-10-18
---

第 23 章 [containers] 定义了 C++ 程序"组织信息集合"的组件（[containers.general] ¶1）。对 language lawyer 来说，这一章的特点是**规范靠表格和交叉引用组织**：具体容器的条款很短，绝大多数语义写在 [container.requirements] 的四组具名要求里。读懂这一章，就是学会把"通用要求 + 具体容器的补充"拼成一份完整契约。

## 本章地图（[containers.general] ¶2）

¶2 的表 74 给出各部分与头文件的对应：

| 子条款 | 内容 | 头文件 | 本站笔记 |
|---|---|---|---|
| [container.requirements] | 容器要求：通用、分配器感知、序列、关联、无序；节点句柄 | — | [[container.requirements]]（含失效/复杂度/异常安全总表）、[[container.requirements.general]]、[[sequence.reqmts]]、[[container.node]]、[[associative.reqmts]]、[[unord.req]] |
| [sequences] | 序列容器 | `<array>` `<deque>` `<forward_list>` `<hive>` `<inplace_vector>` `<list>` `<vector>` | [[sequences]]、[[array]]、[[deque]]、[[forward.list]]、[[hive]]、[[list]]、[[vector]]、[[vector.bool]]、[[inplace.vector]] |
| [associative] | 有序关联容器 | `<map>` `<set>` | [[associative]] |
| [unord] | 无序关联容器 | `<unordered_map>` `<unordered_set>` | [[unord]] |
| [container.adaptors] | 容器适配器 | `<queue>` `<stack>` `<flat_map>` `<flat_set>` | [[container.adaptors]]、[[flat.map]]、[[flat.set]] |
| [views] | 视图 | `<span>` `<mdspan>` | [[views]]、[[views.contiguous]]、[[views.multidim]] |

几个**不在**本章的"容器"：`basic_string`（第 27 章，[[basic.string]]，但它满足本章的连续容器和分配器感知容器要求）、`bitset`（第 22 章工具库）、`valarray`（第 29 章数值库）、`basic_stacktrace`（第 19 章，满足分配器感知容器要求）。迭代器概念和 range 适配器分别在第 24、25 章（[[iterators]]、[[ranges]]）。

## 一份容器契约的四个维度

具体容器的每条规范，几乎都可以归到下面四类之一。本站各页按这四个维度组织：

1. **复杂度**——只数对元素的操作（[[container.requirements]] ¶2），但它们事实上决定了数据结构：几何增长的 `vector`、分块的 `deque`、节点式的 `unordered_map`。
2. **失效**——哪些操作使哪些迭代器、指针、引用不再有效。总原则是"不说就不失效"（[[container.reqmts#67]]）。
3. **异常安全**——缺省是"单元素插入强保证、擦除不抛"（[[container.reqmts#66]]），`vector`/`deque`/关联/无序容器各有例外。
4. **分配器**——元素只能经由 `allocator_traits::construct/destroy` 构造销毁；分配器在拷贝/移动/赋值/交换时如何传播由 POCCA/POCMA/POCS 决定（[[container.requirements.general]]）。分配器协议本身见 [[mem]] 与 [[allocator.traits]]。

## 前置条件的三种强度

本章的函数说明大量使用 [[structure.specifications]] 定义的元素，违反后果各不相同：

| 元素 | 例子 | 违反的后果 |
|---|---|---|
| *Constraints* | `insert(InputIterator, InputIterator)` 要求实参具备输入迭代器资格；`container-compatible-range` | 不参与重载决议 |
| *Mandates* | `vector<T, A>` 要求 `A::value_type` 为 `T`；`array` 的推导指引要求实参同类型 | 非良构，必须诊断 |
| *Preconditions* | `insert(p, i, j)` 的 `i`、`j` 不指向自身；*Cpp17CopyInsertable* | {{ub}}（或实例化时的硬错误） |
| *Hardened preconditions* {{c++26}} | `front()`/`back()`/`pop_*`/`operator[]` 要求非空、不越界 | 加固实现中终止；否则 UB |

## 历史脉络

| 版本 | 本章的关键变化 |
|---|---|
| C++98 | STL 进入标准：`vector`、`deque`、`list`、`set`/`map`/`multi*`、`stack`/`queue`/`priority_queue`、`vector<bool>` |
| C++11 | `array`、`forward_list`、`unordered_*`；移动语义与 `emplace`；`allocator_traits`；`size()` 必须常数；`initializer_list` 构造 |
| C++14 | 关联容器的异构查找（透明比较器） |
| C++17 | 节点句柄 `extract`/`merge`；`try_emplace`/`insert_or_assign`；`std::pmr` 别名；`vector`/`list`/`forward_list` 允许不完整元素类型 |
| C++20 | `std::erase`/`erase_if`；`contains`；`constexpr vector`；`<=>`；`span`；无序容器的异构查找 |
| C++23 | `flat_map`/`flat_set`；`mdspan`；`from_range` 构造与 `*_range` 成员；`vector<bool>` 的 `formatter`；栈与队列的迭代器对构造 |
| C++26 | `inplace_vector`、`hive`；标准库加固；`deque`/`list`/`forward_list`/关联/无序容器/适配器的 constexpr 化；关联容器的异构插入；`span::at`；`submdspan`、填充布局、`aligned_accessor` |

本机 libc++（clang 23）对 C++26 部分的支持是不完整的：`list`、`forward_list`、`map`、`set`、`flat_map`、`flat_set`、`queue` 的 constexpr 已实现（相应 `__cpp_lib_constexpr_*` 宏为 `202502L`），`deque` 尚未；`<inplace_vector>` 与 `<hive>` 尚未提供；关联容器的异构插入（`__cpp_lib_associative_heterogeneous_insertion`）尚未实现。

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

## 小结

- 第 23 章 = 要求（宪法）+ 序列容器 + 有序关联 + 无序关联 + 容器适配器 + 视图。
- 读具体容器时，永远把 [container.requirements] 的通用条目与该容器的补充条款叠加。
- 四个维度：复杂度、失效、异常安全、分配器；查表请看 [[container.requirements]]。
