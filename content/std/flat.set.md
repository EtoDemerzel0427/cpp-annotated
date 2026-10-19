---
title: flat_set 与 flat_multiset
summary: 把键存进一个有序数组的集合容器，规则大多与 flat_map 相同；不同之处在于只有一个底层容器、迭代器解引用得到真正的 const 引用、没有观察底层容器的成员函数。
status: done
covers: flat.set.syn, flat.set.overview, flat.set.defn, flat.set.cons, flat.set.cons.alloc, flat.set.modifiers, flat.set.erasure, flat.multiset, flat.multiset.overview, flat.multiset.defn, flat.multiset.cons, flat.multiset.cons.alloc, flat.multiset.modifiers, flat.multiset.erasure
related: flat.map, container.adaptors, associative.reqmts, associative, container.requirements, vector, deque, allocator.uses
tags: 标准库, 容器, 容器适配器, 关联容器
papers: P1222R4
since: c++23
updated: 2026-10-19
---

!!! tldr
    - `flat_set` 把所有键存在一个有序的序列容器里（默认 `vector<Key>`）。单点插入是线性时间，迭代器失效随底层容器，抛异常后只保证不变式恢复，这些都与 [[flat.map]] 相同。
    - 迭代器是常量迭代器，`*it` 是真正的 `const Key&`，不像 `flat_map` 那样返回代理。
    - 从容器构造的构造函数是 `explicit` 的：`flat_set<int> s = vec;` 不能编译，因为这个转换会排序和去重。
    - 没有 `keys()` 这样的观察器，底层容器只能用 `std::move(s).extract()` 取出、用 `replace()` 放回。
    - `flat_multiset` 不去重，`emplace` 把新元素插到等价元素的末尾。

## 一个有序数组上的 set

```cpp run title="flat-set-basics.cpp" ok
#include <flat_set>
#include <string>
#include <string_view>
#include <vector>
#include <iterator>
#include <cassert>
#include <type_traits>

int main() {
  std::flat_set<std::string, std::less<>> s{"pear", "apple", "fig", "apple"};
  assert(s.size() == 3 && *s.begin() == "apple");       // 构造时排序、去重

  using namespace std::literals;
  auto [it, ok] = s.insert("kiwi"sv);                     // 异构 insert：不存在时才构造 string
  assert(ok && *it == "kiwi");
  static_assert(std::is_same_v<std::iter_reference_t<decltype(s)::iterator>,
                               const std::string&>);      // 常量迭代器

  std::vector<std::string> raw = std::move(s).extract(); // 取出底层的有序 vector
  assert(s.empty() && raw.size() == 4);                   // extract 之后保证为空

  std::flat_multiset<int> ms{3, 1, 3, 2};
  auto pos = ms.emplace(3);                               // multiset 的 emplace 返回 iterator
  assert(ms.count(3) == 3 && pos == std::prev(ms.end()));  // 插在等价元素的末尾
}
```

`std::flat_set`（{{c++23}}，[[P1222R4]]）提供 `std::set` 的接口，存储是一个有序的序列容器。查找用二分，遍历是线性扫描。它和 [[flat.map]] 是同一套设计，下面这些规则完全相同，详细说明见那一页：

- 单点插入和删除是线性时间；批量插入的做法是追加、排序、合并、去重。
- 迭代器失效规则取决于底层容器（[[container.adaptors]] 的通则）。
- 成员函数抛异常后只保证不变式恢复，容器可能被清空。
- 不是分配器感知容器，但标准特化了 `uses_allocator`，所以它参与 uses-allocator 构造。
- `sorted_unique` 标签（[[g:sorted-unique]]）是向库作出的承诺，数据不满足时是 UB。
- `extract() &&` 整个取出底层容器，`replace()` 整个放回。

## 与 flat_map 的差别

| | `flat_map` | `flat_set` |
|---|---|---|
| 底层容器 | 两个：`KeyContainer`、`MappedContainer` | 一个：`KeyContainer`，成员类型名 `container_type` |
| `value_type` | `pair<Key, T>` | `Key` |
| `*it` | 代理 `pair<const Key&, T&>` | `const Key&` |
| Cpp17 迭代器要求 | 只满足 *Cpp17InputIterator* | 标准只说它建模 `random_access_iterator` |
| `value_compare` | 只比较 `.first` 的嵌套类 | 就是 `Compare` |
| `size_type` | `size_t` | `KeyContainer::size_type` |
| 观察底层容器 | `keys()`、`values()` | 没有 |
| 不变式 | 等长、有序、按偏移对应 | 只有有序 |
| UB 前提 | 容器不等长；`sorted_unique` 数据无序或有重复 | 只有后者 |

### 迭代器是常量迭代器

`flat_set` 的元素就是键，改了元素就可能破坏有序。[[associative.reqmts]] 规定，值类型与键类型相同的关联容器，`iterator` 和 `const_iterator` 都是常量迭代器。`flat_set` 满足关联容器要求，这一点不在例外之列，所以：

```cpp run title="flat-set-const-iter.cpp" error
#include <flat_set>

int main() {
  std::flat_set<int> s{1, 2, 3};
  *s.begin() = 0;   // error: 不能通过常量迭代器修改键
}
```

成员类型 `reference` 定义为 `value_type&`，没有 const，而 `*it` 的类型却是 `const Key&`。这与 `std::set` 一样：容器要求表里 `X::reference` 只是 `T&` 的别名，常量性来自常量迭代器这条更强的要求。

本机 libc++ 中 `flat_set<int>::iterator` 和 `const_iterator` 是同一类型，`std::set` 也是如此。类定义因此给 `erase(iterator)` 加了 `requires (!same_as<iterator, const_iterator>)`，避免它和 `erase(const_iterator)` 成为重复的声明。

`*it` 是真正的引用，内存里确实有一个 `Key` 对象。所以 `flat_set` 没有代理引用带来的问题，`for (auto x : s)` 复制的就是键本身。

### 没有 keys()

`flat_map` 用 `keys()` 和 `values()` 以 `const&` 暴露底层容器，`flat_set` 没有对应的成员。要把底层数组交给只接受 `const vector<Key>&` 的接口，只能 `std::move(s).extract()` 取出，用完再 `replace` 回去，或者传迭代器区间。

迭代器区间也不能当作连续内存用。标准只承诺 `random_access_iterator`，本机 libc++ 即使底层是 `vector` 也没有把迭代器标为 `contiguous_iterator`。所以 `std::to_address(s.begin())`、`std::span(s.begin(), s.end())` 这类写法不能用。

## 概述（[flat.set.overview]）

¶1 `flat_set` 是唯一键的关联容器，快速检索的是键本身。迭代器建模 `random_access_iterator`。

¶2 它满足容器、可逆容器、可选容器要求和关联容器要求，例外与 `flat_map` 相同：不满足节点句柄的要求，不满足迭代器失效的要求，单元素插入和删除是线性时间。注 1：它不满足分配器感知容器的附加要求。

¶3 支持 *a_uniq* 操作，不支持 *a_eq* 操作；`key_type` 和 `value_type` 都是 `Key`。

¶4 只描述要求表以外、或需要补充语义的操作。

¶5 不变式只有一条：键按比较对象有序。

¶6 成员函数以异常退出时，`*this` 的不变式被恢复；移动构造和移动赋值恢复两个对象的不变式。注 2：这可能导致容器被清空。

¶7 任何支持 *Cpp17RandomAccessIterator* 的序列容器都可以用，标准点名了 `vector` 和 `deque`；注 3：`vector<bool>` 不是序列容器。与 [[flat.map#7]] 相比，这里少了 `size` 和 `max_size` 不抛异常的要求，可能是因为只有一个容器，恢复不变式时不需要比较两个容器的长度。

¶8 `Key` 与 `KeyContainer::value_type` 不同时，程序{{ill-formed}}。

¶9 用未排序或含相等元素的范围调用接收 `sorted_unique_t` 的成员函数，行为未定义。

¶10 `iterator` 和 `const_iterator` 满足 constexpr 迭代器的要求。

只有一个容器，异常恢复也简单得多。底层 `vector::insert` 在元素类型可以复制、或者移动不抛异常时本身就有强保证，`flat_set::insert` 往往可以自然做到失败无效果。但标准承诺的仍然只是 ¶6 的不变式恢复。

## 构造（[flat.set.defn]、[flat.set.cons]、[flat.set.cons.alloc]）

[flat.set.cons] ¶1 `flat_set(container_type cont, const key_compare& comp = key_compare())` 把 `cont` 移入，按 *compare* 排序，然后在每组连续的等价元素中只保留第一个。¶2 `cont` 已经有序时是线性时间，否则 N log N。

这个构造函数是 `explicit` 的。`flat_map` 的两容器构造函数不需要 `explicit`，因为它至少要两个实参，本来就不会参与隐式转换。`flat_set` 只要一个实参，加上 `explicit` 就避免了 `vector<int>` 被悄悄转换成 `flat_set<int>`，顺带排序去重：

<div class="compare" markdown="1">

```cpp run ok
#include <flat_set>
#include <vector>
// 直接初始化，结果是 {1, 2, 3}
std::flat_set<int> s(
    std::vector<int>{3, 1, 2});
```

```cpp run error
#include <flat_set>
#include <vector>
// error: 复制初始化不能用 explicit 构造函数
std::flat_set<int> s =
    std::vector<int>{3, 1, 2};
```

</div>

类定义中直接给出的 `sorted_unique` 迭代器对构造函数与 `flat_map` 有一处不同：

```cpp
template<class InputIterator>
  constexpr flat_set(sorted_unique_t, InputIterator first, InputIterator last,
                     const key_compare& comp = key_compare())
    : c(first, last), compare(comp) { }
```

`flat_set` 直接用 `(first, last)` 构造底层容器，而 `flat_map` 的对应版本调用 `insert(sorted_unique, first, last)`，按条文它的效果等价于普通的批量插入。所以向 `flat_set` 传入无序数据，得到的对象立刻就违反了不变式；向 `flat_map` 传入无序数据会怎样，取决于实现是否真的跳过了排序。两种情况在标准上都是 UB。

[flat.set.cons.alloc] ¶1 只有 `uses_allocator_v<container_type, Alloc>` 为真时，带分配器的构造函数才参与重载决议。¶2–¶6 它们等同于对应的无分配器版本，只是底层容器以 uses-allocator 构造（[[allocator.uses.construction]]）方式创建。¶5 `sorted_unique` 加分配器的版本是线性时间，因为要复制 `const&` 形参。

## 修改（[flat.set.modifiers]）

¶1–¶4 异构 `insert(K&& x)` 和 `insert(hint, K&& x)` 是集合类容器才有的重载，当前草案中 `std::set` 也有。`flat_map` 没有对应的版本，因为它插入时还需要一个值。

- 约束：比较器透明（`Compare::is_transparent` 存在），并且 `value_type` 能从 `K` 构造。
- 前置条件：由 `x` 转换得到的对象 `u` 满足 `find(x) == find(u)`。
- 效果：已有等价元素时，`*this` 和 `x` 都不变；否则如同 `emplace(std::forward<K>(x))`。

它的用处是只在确实要插入时才构造 `Key`。开头的例子用 `string_view` 查重，不存在时才分配 `string`。

| 段落 | 成员 | 规定 |
|---|---|---|
| ¶5–¶7 | `insert(first, last)` | 追加到末尾，对新元素排序，与原有部分合并，每组等价元素只留第一个；N + M log M；原地合并可能分配内存 |
| ¶8–¶9 | `insert(sorted_unique, first, last)` | 等价于 `insert(first, last)`；线性 |
| ¶10–¶14 | `insert_range(rg)`、`insert_range(sorted_unique, rg)` | 同上 |
| ¶15 | `swap` | 交换比较器和容器；两者都不抛异常地可交换时为 `noexcept` |
| ¶16–¶17 | `extract() &&` | 后置条件：`*this` 被清空，即使以异常退出；返回 `std::move(c)` |
| ¶18–¶19 | `replace(container_type&& cont)` | 前置条件：`cont` 按 *compare* 有序且无相等元素；效果为 `c = std::move(cont)` |

`emplace`、`erase`、`find` 等在这里没有单独描述，按 ¶4 以 [[associative.reqmts]] 为准，只是复杂度换成线性（¶2.3）。

## erase_if（[flat.set.erasure]）

¶1 前置条件：`Key` 满足 *Cpp17MoveAssignable*。¶2–¶4 对每个元素 `e` 以 `as_const(e)` 调用谓词，删除使谓词为真的元素，返回删除个数，谓词恰好调用 `c.size()` 次。¶5 删除是稳定的；如果抛出异常，`c` 处于有效但未指明的状态，仍满足不变式，但可能为空。

与 `flat_map` 唯一的区别是谓词的实参：`flat_map` 传 `pair<const Key&, const T&>`，`flat_set` 直接传 `as_const(e)`。

## flat_multiset（[flat.multiset]）

`flat_multiset` 允许等价的键，标签换成 `sorted_equivalent_t`。概述 ¶1–¶10 与 `flat_set` 逐段对应，区别在于：

- ¶1 支持等价键，即可以包含同一个键值的多个副本；
- ¶3 支持 *a_eq*，不支持 *a_uniq*；
- ¶9 用未排序的范围调用接收 `sorted_equivalent_t` 的成员是 {{ub}}，相等的元素是允许的。

[flat.multiset.cons] ¶1–¶2 从容器构造时只排序、不去重；[flat.multiset.cons.alloc] ¶1–¶6 与 `flat_set` 对应。

[flat.multiset.modifiers] 比 `flat_set` 多描述了 `emplace`：

!!! std
    First, initializes an object `t` of type `value_type` with `std::forward<Args>(args)...`, then inserts `t` as if by: `auto it = ranges::upper_bound(c, t, compare); c.insert(it, std::move(t));`

¶1 约束是 `is_constructible_v<value_type, Args...>`；¶2 先构造 `t`，再在 `upper_bound` 处插入；¶3 返回指向新元素的迭代器。在 `upper_bound` 处插入，新元素就排在已有等价元素之后，与 `std::multiset` 一致，等价元素之间保持插入顺序。

其余各段：¶4–¶6 批量 `insert` 追加、排序、合并，不去重，N + M log M；¶7–¶8 `sorted_equivalent` 版本是线性时间；¶9–¶13 `insert_range` 的两个版本；¶14 `swap`；¶15–¶16 `extract`；¶17–¶18 `replace`，前置条件只要求有序。[flat.multiset.erasure] ¶1–¶5 与 `flat_set` 相同。

!!! impl "libc++ 的实现"
    本机 libc++ 中 `__cpp_lib_flat_set` 为 `202511L`，`__cpp_lib_constexpr_flat_set` 为 `202502L`。`iterator` 和 `const_iterator` 是同一类型，没有标为连续迭代器。`sorted_unique`、`sorted_equivalent` 和 `replace` 的有序性前提只在 debug 加固档检查；以 `sorted_unique` 批量插入后，也会检查新追加的部分是否有序、无重复。

## 思考题

!!! question "思考题 1"
    [flat.set.overview] ¶1 只说迭代器建模 `random_access_iterator`，[[flat.map#1]] 为什么还要专门说它满足 *Cpp17InputIterator*？

<details markdown="1">
<summary>答案</summary>

`flat_set` 的 `*it` 是真正的 `const Key&`，包装一下 `vector` 的迭代器就能满足 *Cpp17RandomAccessIterator*，标准不需要降级说明。`flat_map` 的 `*it` 是代理 prvalue，而 *Cpp17ForwardIterator* 要求 `reference` 是真正的引用类型，它做不到。所以标准必须写明：按 Cpp17 要求它只是输入迭代器，按 C++20 概念它才是随机访问迭代器。
</details>

!!! question "思考题 2"
    `std::flat_multiset<int> ms{2, 1};` 之后调用 `ms.insert(ms.begin(), 2)`，新的 2 排在已有的 2 之前还是之后？

<details markdown="1">
<summary>答案</summary>

带 hint 的插入在 [flat.multiset.modifiers] 中没有单独描述，按 ¶4 以 [[associative.reqmts]] 为准：对允许等价键的容器，`insert(p, t)` 总会插入，并且把 `t` 插到尽量靠近 `p` 之前的位置。`ms.begin()` 指向 1，离它最近、又能保持有序的位置是已有的 2 之前，所以新元素排在前面。对 `int` 看不出差别；换成比较器只比较一个字段的结构体，本机 libc++ 的结果是新元素排在已有的等价元素之前。
</details>
