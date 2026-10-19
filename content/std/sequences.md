---
title: 序列容器
summary: 第 23.3 节收录全部具体的序列容器；本页说明它们各自的定位、如何在其中做选择，以及推导指引用到的 iter-value-type。
status: done
covers: sequences.general
related: sequence.reqmts, container.requirements, array, deque, forward.list, hive, list, vector, vector.bool, inplace.vector
tags: 标准库, 容器, 序列容器, 导读
updated: 2026-10-19
---

!!! tldr
    - 七个头文件 `<array>`、`<deque>`、`<forward_list>`、`<hive>`、`<inplace_vector>`、`<list>`、`<vector>` 定义了全部序列容器，它们共同遵守 [[sequence.reqmts]] 的要求。
    - 默认用 `vector`；需要稳定的元素地址时，按增长方式在 `deque`、`hive`、`list` 之间选。
    - `std::vector v(first, last)` 能推导出元素类型，靠的是推导指引中的 `iter-value-type`；写成花括号就会推导出一个装迭代器的 `vector`。

¶1 七个头文件定义了满足序列容器要求的类模板。其中 `array` 和 `hive` 只满足部分要求：`array` 的元素个数固定，`hive` 的插入位置由容器决定（[[sequence.reqmts#1]]）。

## 怎么选

| 容器 | 头文件 | 特点 | 笔记 |
|---|---|---|---|
| `array<T, N>` | `<array>` | 定长，聚合，内置数组的零开销包装 | [[array]] |
| `vector<T>` | `<vector>` | 连续存储，尾部插入摊还 O(1)，默认选择 | [[vector]] |
| `vector<bool>` | `<vector>` | 按位存储的偏特化，元素引用是代理对象 | [[vector.bool]] |
| `inplace_vector<T, N>` {{c++26}} | `<inplace_vector>` | 容量固定、存储在对象内部的 `vector` | [[inplace.vector]] |
| `deque<T>` | `<deque>` | 两端插入 O(1)，两端插入不使引用失效 | [[deque]] |
| `list<T>` | `<list>` | 双向链表，任意位置 O(1) 插入擦除，`splice` | [[list]] |
| `forward_list<T>` | `<forward_list>` | 单向链表，相对手写 C 链表没有额外开销 | [[forward.list]] |
| `hive<T>` {{c++26}} | `<hive>` | 位置由容器决定，插入擦除 O(1)，地址稳定 | [[hive]] |

经验上，先用 `vector`。需要元素地址在插入后保持不变时，只在两端增长选 `deque`，不在乎顺序选 `hive`，需要在任意位置插入或在序列之间 `splice` 选 `list`。大小有一个不大的上限、又不想动态分配时用 `inplace_vector`；大小在编译期固定时用 `array`。各容器的失效规则、复杂度和异常安全的对比见 [[container.requirements]]。

## 推导指引中的 iter-value-type（¶2）

```cpp title="ctad-iter.cpp" run ok
#include <list>
#include <type_traits>
#include <vector>

int main() {
  std::list<double> l{1.0, 2.0};
  std::vector v(l.begin(), l.end());
  static_assert(std::is_same_v<decltype(v),
                               std::vector<double>>);
  std::vector w{l.begin(), l.end()};   // 花括号
  static_assert(std::is_same_v<decltype(w)::value_type,
                               std::list<double>::iterator>);
}
```

¶2 定义了一个仅用于阐述的别名模板 `iter-value-type<InputIterator>`，即 `iterator_traits<InputIterator>::value_type`。各序列容器的推导指引用它从一对迭代器推导出元素类型，所以 `v` 是 `vector<double>`。

`w` 用的是花括号。列表初始化时，类模板实参推导优先考虑初始化器列表构造函数，于是 `w` 被推导为装着两个迭代器的 `vector`。
