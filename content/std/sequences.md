---
title: 序列容器
summary: 23.3 导读——七个序列容器头文件各自的定位、iter-value-type 在推导指引中的作用，以及如何在 vector / deque / list / forward_list / array / inplace_vector / hive 之间做选择
status: done
covers: sequences.general
related: sequence.reqmts, container.requirements, array, deque, forward.list, hive, list, vector, vector.bool, inplace.vector
tags: 标准库, 容器, 序列容器, 导读
updated: 2026-10-18
---

[sequences] 收录全部具体的序列容器。它们共同遵守 [[sequence.reqmts]] 的契约，各自的条款只补充差异。

## 概述（[sequences.general]）

¶1：头文件 `<array>`、`<deque>`、`<forward_list>`、`<hive>`、`<inplace_vector>`、`<list>`、`<vector>` 定义了满足序列容器要求的类模板。（其中 `array` 与 `hive` 只满足部分要求，见 [[sequence.reqmts]] ¶1。）

¶2：定义了仅用于阐述的别名模板 `iter-value-type<InputIterator>` = `iterator_traits<InputIterator>::value_type`，供推导指引使用。正是它让 `std::vector v(first, last);` 能从迭代器推导出元素类型：

```cpp title="ctad-iter.cpp" run ok
#include <vector>
#include <list>
#include <type_traits>

int main() {
  std::list<double> l{1.0, 2.0};
  std::vector v(l.begin(), l.end());              // 推导指引：vector<iter-value-type<It>>
  static_assert(std::is_same_v<decltype(v), std::vector<double>>);
  std::vector w{l.begin(), l.end()};              // 注意：花括号 → vector<list<double>::iterator>
  static_assert(std::is_same_v<decltype(w)::value_type, std::list<double>::iterator>);
}
```

第二个声明是 CTAD 的经典陷阱：花括号让初始化器列表构造函数的推导候选优先，得到的是"两个迭代器组成的 vector"。

## 一页选型表

| 容器 | 头文件 | 一句话定位 | 本站笔记 |
|---|---|---|---|
| `array<T, N>` | `<array>` | 定长、聚合、零开销包装内置数组 | [[array]] |
| `vector<T>` | `<vector>` | 默认选择：连续、尾部摊还 O(1) | [[vector]] |
| `vector<bool>` | `<vector>` | 按位存储的偏特化，代理引用 | [[vector.bool]] |
| `inplace_vector<T, N>` {{c++26}} | `<inplace_vector>` | 容量固定、存储在对象内部的 `vector` | [[inplace.vector]] |
| `deque<T>` | `<deque>` | 两端 O(1)、两端插入不使引用失效 | [[deque]] |
| `list<T>` | `<list>` | 双向链表：任意位置 O(1)、永不失效、`splice` | [[list]] |
| `forward_list<T>` | `<forward_list>` | 单向链表，相对手写 C 链表零开销 | [[forward.list]] |
| `hive<T>` {{c++26}} | `<hive>` | 对象池：位置由容器定，插入擦除 O(1) 且地址稳定 | [[hive]] |

经验法则：先用 `vector`；需要稳定地址时，看增长模式选 `deque`（只在两端）、`hive`（不在乎顺序）或 `list`（需要任意位置插入或 `splice`）；大小有小上限且不想要堆分配时用 `inplace_vector`；大小固定用 `array`。各容器的失效、复杂度、异常安全对比见 [[container.requirements]] 的总表。
