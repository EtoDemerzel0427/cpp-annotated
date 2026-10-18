---
title: flat_set 与 flat_multiset
summary: 单个有序序列容器上的集合——与 flat_map 共享"线性插入、失效随底层容器、异常后只恢复不变式"的整套法则，但只有一个容器、迭代器是真引用且为常量迭代器、没有 keys() 观察器；sorted_unique / sorted_equivalent 承诺与 extract/replace
status: done
covers: flat.set.syn, flat.set.overview, flat.set.defn, flat.set.cons, flat.set.cons.alloc, flat.set.modifiers, flat.set.erasure, flat.multiset, flat.multiset.overview, flat.multiset.defn, flat.multiset.cons, flat.multiset.cons.alloc, flat.multiset.modifiers, flat.multiset.erasure
related: flat.map, container.adaptors, associative.reqmts, associative, container.requirements, vector, deque, allocator.uses
tags: 标准库, 容器, 容器适配器, 关联容器
papers: P1222R4
since: c++23
updated: 2026-10-18
---

`std::flat_set`（{{c++23}}，[[P1222R4]]）是 `std::set` 接口的"扁平"实现：所有键存放在**一个**有序的序列容器里（默认 `vector<Key>`），查找用二分，遍历是线性扫描。它与 [[flat.map]] 是同一套设计的两个分支，几乎所有原则都相同：

- 单点插入/删除线性，批量插入"追加 + 排序 + 合并 + 去重"；
- 迭代器失效规则完全取决于底层容器（[[container.adaptors]] 中的 [container.adaptors.general] ¶5）；
- 抛异常后只保证不变式恢复，可能被清空；
- 不是 allocator-aware 容器，但通过 `uses_allocator` 特化参与 uses-allocator 构造；
- `sorted_unique` 标签（[[g:sorted-unique]]）是向库作出的承诺，撒谎是 UB；
- `extract() &&` 整体取出底层容器，`replace()` 整体放回。

本页只讲与 `flat_map` 不同的地方。阅读前请先看 [[flat.map]]。

## 与 flat_map 的结构性差别

| 方面 | `flat_map` | `flat_set` |
|---|---|---|
| 底层容器 | 两个：`KeyContainer`、`MappedContainer` | 一个：`KeyContainer`（成员类型 `container_type`） |
| `value_type` | `pair<Key, T>` | `Key`（与 `key_type` 相同） |
| `reference` | 代理 `pair<const Key&, T&>` | `value_type&`，即 `Key&` |
| 解引用迭代器得到 | 代理 prvalue | `const Key&`（常量迭代器） |
| Cpp17 迭代器要求 | 只满足 *Cpp17InputIterator* | 无此限制，只说建模 `random_access_iterator` |
| `value_compare` | 只比较 `.first` 的嵌套类 | 就是 `Compare` |
| `size_type` | 固定 `size_t` | `KeyContainer::size_type` |
| 观察器 | `keys()`、`values()` | **没有**——只能遍历或 `extract` |
| 不变式 | 三条（等长、有序、按偏移对应） | 一条（有序） |
| UB 前提 | 容器不等长；`sorted_unique` 数据无序或有重复 | 只有后者 |

### 为什么迭代器是常量迭代器

`flat_set` 的元素本身就是键。[[associative.reqmts]] ¶6 规定：value type 与 key type 相同的关联容器，`iterator` 与 `const_iterator` **都是常量迭代器**，二者是否为同一类型未指明。`flat_set` 继承了这条（[flat.set.overview] ¶2 声明它满足关联容器要求，例外条款不涉及这一点）。所以：

```cpp run title="flat-set-const-iter.cpp" error
#include <flat_set>

int main() {
  std::flat_set<int> s{1, 2, 3};
  *s.begin() = 0;   // error: 通过常量迭代器修改键会破坏有序不变式
}
```

一个容易让人困惑的细节：成员类型 `reference` 被定义为 `value_type&`（非 const），但 `*it` 的类型却是 `const Key&`。这与 `std::set` 完全一致——容器要求表中 `X::reference` 只是 `T&` 的别名，常量性由"常量迭代器"这一更强的要求施加。libc++ 中 `flat_set<int>::iterator` 与 `const_iterator` 是同一类型（`std::set` 亦然），所以类定义中 `erase(iterator)` 带了 `requires (!same_as<iterator, const_iterator>)`，避免与 `erase(const_iterator)` 构成重复声明。

与 `flat_map` 不同，`flat_set` 的迭代器解引用得到的是**真正的引用**——内存里确实存在一个 `Key` 对象。因此它不受代理引用的种种限制，`for (auto x : s)` 拷贝的就是键本身。

### 没有 keys()

`flat_map` 提供 `keys()`/`values()` 以 `const&` 暴露底层容器，`flat_set` 却**没有**对应的 `keys()` 或 `container()` 观察器。想把底层数组交给只接受 `const vector<Key>&` 的 API，只能 `std::move(s).extract()` 拿出来、用完再 `replace` 回去，或者用迭代器区间。另外，libc++ 的 `flat_set` 迭代器即使底层是 `vector` 也**刻意**只标为随机访问迭代器而非连续迭代器（源码注释："deliberately lower contiguous_iterator"），所以 `std::to_address(s.begin())`、`std::span(s.begin(), s.end())` 这类依赖 `contiguous_iterator` 的写法不可用——标准也只承诺了 `random_access_iterator`。

## 概述（[flat.set.overview]）

| 段落 | 内容 |
|---|---|
| ¶1 | 唯一键的关联容器接口，"快速检索键本身"；迭代器建模 `random_access_iterator` |
| ¶2 | 满足容器、可逆容器、可选容器要求及关联容器要求，例外：不满足节点句柄要求（[[container.node]]）、不满足失效要求、单元素插入/删除线性；注：不满足 allocator-aware 容器的附加要求 |
| ¶3 | 支持 *a_uniq*、不支持 *a_eq*；`key_type` 与 `value_type` 都是 `Key` |
| ¶4 | 只描述要求表之外或需补充语义的操作 |
| ¶5 | 不变式：键关于比较对象有序 |
| ¶6 | 成员函数以异常退出时恢复对象实参的不变式；移动构造/移动赋值恢复两个实参的不变式；注：可能导致被清空 |
| ¶7 | 任何具有 *Cpp17RandomAccessIterator* 的序列容器都可用，特别是 `vector` 与 `deque`；注：`vector<bool>` 不是序列容器 |
| ¶8 | `Key` 与 `KeyContainer::value_type` 不同则 {{ill-formed}} |
| ¶9 | 以未排序或含相等元素的范围调用接收 `sorted_unique_t` 的成员是 {{ub}} |
| ¶10 | `iterator`、`const_iterator` 满足 constexpr 迭代器要求 |

!!! std
    If any member function in [flat.set.defn] exits via an exception, the invariant of the object argument is restored.
    若 [flat.set.defn] 中任何成员函数以异常退出，对象实参的不变式被恢复。

¶7 比 `flat_map` 的对应段落（[[flat.map#7]]）少了一个条件：没有要求 `size`/`max_size` 不抛。原因是 `flat_set` 只有一个容器，不存在"比较两个容器长度来恢复不变式"的需要。

单容器还意味着异常恢复要容易得多：底层 `vector::insert` 在多数情况下本身就提供强保证（元素类型不抛移动或可拷贝时），`flat_set::insert` 因此往往能自然地做到"失败无效果"，`flat_map` 则需要协调两个容器。但标准承诺的仍然只有 ¶6 的"不变式恢复"。

## 定义与构造（[flat.set.defn]、[flat.set.cons]、[flat.set.cons.alloc]）

类定义中内联给出的构造函数与 `flat_map` 平行，有一处细微差别：

```cpp
template<class InputIterator>
  constexpr flat_set(sorted_unique_t, InputIterator first, InputIterator last,
                     const key_compare& comp = key_compare())
    : c(first, last), compare(comp) { }
```

`flat_set` 的 `sorted_unique` 迭代器对构造函数**直接**用 `(first, last)` 构造底层容器，而 `flat_map` 的对应版本是 `insert(sorted_unique, first, last)`——后者按 [flat.map.modifiers] ¶9 仍会做合并与去重。所以对 `flat_set` 撒谎（传入无序数据）的后果是一个立即违反不变式的对象；对 `flat_map` 撒谎的结果则取决于实现是否真的跳过了排序。两者在标准上都是 UB。

[flat.set.cons]：

- ¶1 `explicit flat_set(container_type cont, const key_compare& comp = key_compare())`：以 `std::move(cont)` 初始化 *c*，按 *compare* 排序，并**删除每组连续等价元素中除第一个以外的所有元素**——用文字而不是 `flat_map` 那样的 `zip` 代码描述，效果相同。
- ¶2 复杂度：`cont` 已有序则线性，否则 N log N。

注意这个构造函数是 `explicit` 的（`flat_map` 的两容器构造函数不是，因为它有两个必需参数）——防止 `vector<int>` 被隐式转换成 `flat_set<int>` 并悄悄地排序去重。

[flat.set.cons.alloc]：¶1 只有 `uses_allocator_v<container_type, Alloc>` 为真时才参与重载决议；¶2–¶3 `(cont, a)` 与 `(cont, comp, a)` 等价于无分配器版本，只是 *c* 以 uses-allocator 构造（[[allocator.uses.construction]]）创建；¶4–¶5 `sorted_unique` 版本，复杂度线性（要拷贝 `const&` 参数）；¶6 其余带分配器的构造函数同理。`uses_allocator<flat_set<...>, Alloc>` 直接继承 `uses_allocator_v<KeyContainer, Alloc>`。

## 修改操作（[flat.set.modifiers]）

| 段落 | 成员 | 规定 |
|---|---|---|
| ¶1–¶4 | `template<class K> insert(K&& x)`、`insert(hint, K&& x)` | *Constraints*：`Compare::is_transparent` 有效且 `is_constructible_v<value_type, K>`；*Preconditions*：由 `x` 转换得到的 `u` 满足 `find(x) == find(u)`；若已有等价元素则 `*this` 与 `x` 都不变，否则如同 `emplace(std::forward<K>(x))` |
| ¶5–¶7 | `insert(first, last)` | `c.insert(c.end(), first, last)` 追加 → 排序新元素 → 合并 → 每组等价元素只留第一个；N + M log M；原地合并可能分配内存 |
| ¶8–¶9 | `insert(sorted_unique, first, last)` | 等价于 `insert(first, last)`；线性 |
| ¶10–¶14 | `insert_range(rg)`、`insert_range(sorted_unique, rg)` | 同上，用 `ranges::for_each` 逐个追加 |
| ¶15 | `swap` | `ranges::swap` 比较器与容器；`noexcept` 当且仅当二者都不抛地可交换 |
| ¶16–¶17 | `extract() &&` | 后置条件：`*this` 被清空，**即使以异常退出**；返回 `std::move(c)` |
| ¶18–¶19 | `replace(container_type&& cont)` | 前置条件：`cont` 关于 *compare* 有序且无相等元素；效果：`c = std::move(cont)` |

¶1–¶4 的异构 `insert` 是集合类容器才有的（当前草案中 `std::set` 也有同样的重载）：`flat_map` 没有对应的 `insert(K&&)`，因为它的插入需要同时提供值。它的意义在于"只有确实要插入时才构造 `Key`"——用 `string_view` 查重，不存在时才分配 `string`：

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
  assert(s.size() == 3 && *s.begin() == "apple");       // 构造时排序 + 去重

  using namespace std::literals;
  auto [it, ok] = s.insert("kiwi"sv);                     // 异构 insert：不存在才构造 string
  assert(ok && *it == "kiwi");
  static_assert(std::is_same_v<std::iter_reference_t<decltype(s)::iterator>,
                               const std::string&>);      // 常量迭代器

  std::vector<std::string> raw = std::move(s).extract(); // 取出底层的有序 vector
  assert(s.empty() && raw.size() == 4);                   // ¶16：extract 后保证为空

  std::flat_multiset<int> ms{3, 1, 3, 2};
  auto pos = ms.emplace(3);                               // multiset 的 emplace 返回 iterator
  assert(ms.count(3) == 3 && pos == std::prev(ms.end()));  // 插在等价元素组的末尾
}
```

`emplace`、`emplace_hint`、`erase`、`find` 等在 [flat.set.modifiers] 中没有单独描述，按 ¶4 一律以 [[associative.reqmts]] 为准，只是复杂度换成线性（¶2.3）。

## 删除（[flat.set.erasure]）

¶1 *Preconditions*：`Key` 满足 *Cpp17MoveAssignable*；¶2 对每个元素 `e` 以 `as_const(e)` 调用谓词，删除使其为真者；¶3 返回删除个数；¶4 恰好调用 `c.size()` 次谓词；¶5 稳定，若以异常退出则 `c` 处于有效但未指明的状态（注：仍满足不变式，但可能为空）。

与 `flat_map` 唯一的区别是谓词的实参：`flat_map` 构造一个 `pair<const Key&, const T&>`，`flat_set` 直接传 `as_const(e)`。

## flat_multiset（[flat.multiset]）

允许等价键的版本，标签换成 `sorted_equivalent_t`。概述 ¶1–¶10 与 `flat_set` 逐段对应，区别在于：

- ¶1：支持**等价键**（可包含同一键值的多个副本）；
- ¶3：支持 *a_eq*、不支持 *a_uniq*；
- ¶9：以**未排序**的范围调用接收 `sorted_equivalent_t` 的成员是 {{ub}}——不禁止相等元素。

[flat.multiset.cons] ¶1–¶2：容器构造函数只排序**不去重**；[flat.multiset.cons.alloc] ¶1–¶6 与 `flat_set` 对应。

[flat.multiset.modifiers] 比 `flat_set` 多描述了 `emplace`：

!!! std
    First, initializes an object `t` of type `value_type` with `std::forward<Args>(args)...`, then inserts `t` as if by: `auto it = ranges::upper_bound(c, t, compare); c.insert(it, std::move(t));`
    先构造 `t`，再在 `upper_bound` 位置插入。

¶1 *Constraints* 为 `is_constructible_v<value_type, Args...>`；¶3 返回指向新元素的迭代器。用 `upper_bound` 意味着新元素排在已有等价元素**之后**——与 `std::multiset` 的"插入到等价范围末尾"规则一致，因而插入顺序在等价元素之间得以保留。其余各段：¶4–¶6 批量 `insert` 追加 → 排序 → 合并（不去重），N + M log M；¶7–¶8 `sorted_equivalent` 版本线性；¶9–¶13 `insert_range` 两个版本；¶14 `swap`；¶15–¶16 `extract`；¶17–¶18 `replace`，前置条件只要求有序。

[flat.multiset.erasure] ¶1–¶5 与 `flat_set` 一字不差。

## libc++ 实现现状

截至 Homebrew clang 23.1.3 附带的 libc++：`__cpp_lib_flat_set` 为 `202511L`、`__cpp_lib_constexpr_flat_set` 为 `202502L`，可在常量表达式中使用；迭代器 `iterator` 与 `const_iterator` 为同一类型、刻意不标为连续迭代器；`sorted_unique`/`sorted_equivalent` 与 `replace` 的有序性前提只在 `_LIBCPP_HARDENING_MODE_DEBUG` 下检查（`_LIBCPP_ASSERT_SEMANTIC_REQUIREMENT`），批量插入 `sorted_unique` 数据后也会检查新追加部分是否有序无重复。

## 思考题

1. `std::flat_set<int> s = std::vector<int>{3, 1, 2};` 能编译吗？`std::flat_set<int> s(std::vector<int>{3, 1, 2});` 呢？

<details markdown="1">
<summary>展开查看答案与解析</summary>

前者是复制初始化，需要从 `vector<int>` 隐式转换到 `flat_set<int>`，而唯一可用的构造函数 `flat_set(container_type, const key_compare& = key_compare())` 是 `explicit` 的（[flat.set.defn]），所以编译失败。后者是直接初始化，可以调用 `explicit` 构造函数，结果是排序后的 `{1, 2, 3}`（[flat.set.cons] ¶1）。标准有意让"会排序、会去重、可能 O(N log N)"的转换必须显式写出。
</details>

2. 为什么 [flat.set.overview] ¶1 只说迭代器"建模 `random_access_iterator`"，而 [[flat.map#1]] 还要专门说"满足 *Cpp17InputIterator* 要求"？

<details markdown="1">
<summary>展开查看答案与解析</summary>

`flat_set` 的 `*it` 是真正的 `const Key&`，它完全可以满足 *Cpp17RandomAccessIterator*（标准只是没有强制写出，默认 `vector` 的迭代器包装一下即可满足）。`flat_map` 的 `*it` 是代理 prvalue，*Cpp17ForwardIterator* 要求 `reference` 为真正的引用类型，它做不到，因此标准必须明确降级说明：Cpp17 层面它只是输入迭代器，C++20 概念层面才是随机访问迭代器。
</details>

## 小结

- `flat_set` = 一个有序序列容器 + 比较器；`flat_multiset` 不去重、用 `upper_bound` 插入以保持等价元素的插入顺序。
- 键不可修改：迭代器是常量迭代器，`*it` 是 `const Key&`；与 `flat_map` 的代理引用不同，它是真引用。
- 只有一个不变式（有序）、一条 UB 前提（`sorted_unique` 数据无序或有重复 / `sorted_equivalent` 数据无序），没有"容器不等长"的问题。
- 没有 `keys()` 观察器；底层容器只能通过 `extract() &&` 取出、`replace()` 放回。
- 失效、异常、分配器、批量插入的规则与 [[flat.map]] 相同。
