---
title: map、set、multimap、multiset
summary: 四个有序关联容器各自特有的成员：map::operator[] 就是 try_emplace，try_emplace 在键已存在时不动实参而 emplace 不保证，insert_or_assign、lookup，C++26 异构插入的未定义行为条件，以及推导指引和 erase_if。
status: done
covers: *
related: associative.reqmts, container.node, container.requirements, unord, flat.map, flat.set, alg.sorting
tags: 标准库, 容器, map, set, 红黑树, try_emplace
updated: 2026-10-19
---

!!! tldr
    - `m[k]` 被定义为 `try_emplace(k).first->second`：键不存在时插入一个值初始化的值，所以它是修改操作，要求映射类型能默认构造。
    - 键已存在时，`try_emplace` 保证没有任何效果，右值实参不会被移走；`emplace` 没有这个保证。
    - `insert_or_assign` 不要求映射类型能默认构造，并且返回是否插入了新元素。
    - C++26 的异构插入要求由异构键构造出的真实键与它在比较器下处于同一位置，否则是未定义行为。
    - `erase_if` 对节点容器是逐个擦除，因为 `pair<const K, T>` 不能赋值，remove-erase 惯用法用不了。

[associative] 定义 `<map>` 里的 `map`、`multimap` 和 `<set>` 里的 `set`、`multiset`。它们的大部分语义来自关联容器要求（[[associative.reqmts]]）：按比较器排序、查找和插入是对数时间、插入不使迭代器失效。[associative] 只补充每个类模板特有的部分，主要是 `map` 的元素访问和带键插入的那一组函数。

## m[k] 做了什么（[map.access]）

```cpp title="map-subscript-nodefault.cpp" error
#include <map>
struct NoDefault { NoDefault(int) {} };
int main() {
  std::map<int, NoDefault> m;
  m.try_emplace(1, 42);    // OK
  m[1];                    // error: operator[] 需要 NoDefault 能默认构造
}
```

¶1 `operator[](const key_type& x)` 的效果等价于 `return try_emplace(x).first->second;`。¶2 右值键的版本把键移进 `try_emplace`。所以 `m[k]` 在键不存在时，用空的实参列表构造映射值，再插入。没有默认构造函数的类型不能用 `operator[]`，即使这个键已经存在。

`operator[]` 因此是修改操作：不能用于 `const map`，也不在 [[container.requirements.dataraces#1]] 视为 const 的函数名单里，两个线程同时对同一个 map 调用 `operator[]` 会构成数据竞争。只读访问用下面几种：

| 成员 | 规定 | 出处 |
|---|---|---|
| `at(x)` | 返回映射值的引用；键不存在时抛 `out_of_range`；对数时间 | ¶5–¶7 |
| `lookup(x)` | 返回 `optional<mapped_type&>`：存在时引用映射值，否则 `nullopt` | ¶13–¶16 |
| `find(x)`、`contains(x)` | 见 [[associative.reqmts]] | |

`lookup` 是 C++26 之后的新接口，用到了 `optional<T&>`。本机 libc++ 还没有提供。

¶3–¶4、¶8–¶12 `operator[]` 和 `at` 还各有一个模板版本 `template<class K>`，只在比较器有成员类型 `is_transparent` 时参与重载决议，这时可以不先构造 `key_type` 就查找。¶9 规定 `at(const K&)` 的前置条件是 `find(x)` 良构且行为有定义。

## try_emplace 与 emplace（[map.modifiers]）

```cpp title="try-emplace.cpp" run ok
#include <map>
#include <memory>
#include <string>
#include <cassert>

int main() {
  std::map<std::string, std::unique_ptr<int>> m;
  m.emplace("a", std::make_unique<int>(1));

  auto p = std::make_unique<int>(2);
  m.try_emplace("a", std::move(p));   // 键已存在：p 不会被移走
  assert(p != nullptr);

  auto q = std::make_unique<int>(3);
  m.emplace("a", std::move(q));       // q 可能已被移进一个临时节点后丢弃
  // 标准不规定 q 此时的状态；本机 libc++ 中 q 已为空

  auto [it, inserted] = m.insert_or_assign("a", std::make_unique<int>(4));
  assert(!inserted && *it->second == 4);   // 已存在：赋值给映射值
}
```

¶3–¶10 `try_emplace(k, args...)` 的效果：

!!! std
    If the map already contains an element whose key is equivalent to k, there is no effect.

没有效果意味着 `args...` 不会被移动。否则，用 `piecewise_construct, forward_as_tuple(k), forward_as_tuple(args...)` 构造一个元素插入，也就是键从 `k` 构造，映射值从 `args...` 构造。

`emplace(args...)` 只规定"构造一个元素 t，当且仅当容器中没有与 t 的键等价的元素时插入"（[[associative.reqmts.general#49]]）。键在 `args` 里面，一般要先构造出元素才知道键是什么。键已存在时，这个元素被销毁，右值实参已经被移进去了。

{{impl}} libc++ 在 `emplace` 的第一个实参正好是 `key_type` 时会先查找，找到就不构造节点：把上例换成 `std::map<int, std::unique_ptr<int>>` 和 `m.emplace(1, std::move(q))`，本机 `q` 保持不变。实参是 `"a"`（`const char[2]`）这类需要转换的类型时，它只能先构造节点。这只是实现的优化，标准只对 `try_emplace` 作出保证。

### insert_or_assign 与 insert(P&&)

¶16–¶25 `insert_or_assign(k, obj)` 要求 `is_assignable_v<mapped_type&, M&&>`（*Mandates*，不满足则非良构）。键已存在时把 `obj` 赋给映射值，否则插入 `value_type(k, std::forward<M>(obj))`。返回 `pair<iterator, bool>`，带提示的版本返回 `iterator`。

和 `m[k] = obj` 相比，它不要求映射类型能默认构造，也不会先构造一个默认值再赋值，并且能告诉你是否插入了新元素。

¶1–¶2 `template<class P> insert(P&& x)` 在 `is_constructible_v<value_type, P&&>` 为真时参与重载决议，等价于 `emplace(std::forward<P>(x))`。有了它，`m.insert(std::pair{1, "x"})` 可以从 `pair<int, const char*>` 直接构造出 `pair<const int, std::string>`，不经过一个中间的 `value_type` 临时对象。

### 计数的惯用法

```cpp run ok
#include <map>
#include <string>
#include <cassert>

int main() {
  std::map<std::string, int> counts;
  ++counts["x"];     // 不存在：插入值初始化的 0，再自增
  ++counts["x"];
  assert(counts.at("x") == 2);
}
```

值初始化保证新插入的 `int` 是 0，所以 `++counts[k]` 是统计次数的标准写法。

## C++26 异构插入（¶11–¶15、¶26–¶31）{{c++26}}

`std::map<std::string, int, std::less<>>` 已经可以用 `const char*` 或 `string_view` 查找，不必构造 `std::string`。C++26 把这一点扩展到插入：`try_emplace(K&& k, ...)`、`insert_or_assign(K&& k, obj)` 和 `operator[](K&&)` 都有了异构版本，要求比较器有 `is_transparent`。

¶13 的效果描述里有一个未定义行为条件：

!!! std
    let r be equal_range(k). Constructs an object u of type value_type with ... If equal_range(u.first) == r is false, the behavior is undefined.

意思是，由 `k` 构造出来的真实键 `u.first`，在比较器下必须和 `k` 落在同一个位置。如果从 `K` 到 `Key` 的转换会改变排序位置，例如转换时截断了字符串、或者统一了大小写而比较器不统一，就是 {{ub}}。这条要求让实现可以先用 `k` 找到插入点，再构造节点直接链入，不必用 `u.first` 再查一次。

本机 libc++ 还没有实现异构插入（`__cpp_lib_associative_heterogeneous_insertion` 未定义）。

!!! lawyer "排除迭代器的约束为什么写在不同的重载上"
    ¶11 对 `map::try_emplace` 的异构版本，要求 `K&&` 不能转换为迭代器，这一条只加在不带提示的那个重载上；`set::insert` 的异构版本恰好相反，加在带提示的重载上（[set.modifiers] ¶1）。两者防的是不同的歧义：`try_emplace(k, args...)` 的 `k` 如果是迭代器，会和带提示的 `try_emplace(hint, key, args...)` 混淆；`insert(hint, x)` 的 `x` 如果是迭代器，会和区间插入 `insert(first, last)` 混淆。

## 构造与推导指引（[associative.general]、[map.cons]）

[map.cons] ¶1–¶6 用比较器和分配器构造是常数时间。区间构造（迭代器对或 `from_range`）在区间已经按比较器排好序时是线性时间，否则是 N log N。

[associative.general] ¶2 定义了几个推导指引用的仅阐述别名：

| 别名 | 含义 |
|---|---|
| `iter-value-type<It>` | `iterator_traits<It>::value_type` |
| `iter-key-type<It>` | `remove_const_t<tuple_element_t<0, iter-value-type<It>>>` |
| `iter-mapped-type<It>` | `tuple_element_t<1, iter-value-type<It>>` |
| `iter-to-alloc-type<It>` | `pair<const iter-key-type<It>, iter-mapped-type<It>>` |
| `range-key-type<R>` 等 | 对 `ranges::range_value_t<R>` 做同样的处理 |

`iter-key-type` 去掉了 `const`，所以从另一个 map 的迭代器（值类型是 `pair<const K, V>`）推导出的是 `map<K, V>`；从 `vector<pair<K, V>>` 推导也一样。初始化器列表的推导指引接受 `initializer_list<pair<Key, T>>`，所以 `std::map m{std::pair{1, 2.0}, std::pair{2, 3.0}};` 推导出 `map<int, double>`。

## erase_if（[map.erasure]）

¶1 `erase_if(c, pred)` 被规定为一个逐个检查、逐个 `c.erase(i)` 的循环，返回擦除的元素个数。节点容器不能用 remove-erase 惯用法：`remove` 要给元素赋值，而 `pair<const K, T>` 不能赋值，`set` 的元素也不能通过迭代器修改。

## multimap、set、multiset

**multimap**（[multimap]）支持等价键，一个键可以对应多个值。它没有 `operator[]`、`at`、`try_emplace`、`insert_or_assign`，因为在 `multimap` 里"键对应的那个值"没有定义。修改器只有 `insert(P&&)` 模板，等价于 `emplace`；构造和 `erase_if` 与 `map` 相同。插入等价键时，新元素放在已有等价元素范围的末尾（[[associative.reqmts.general#54]]）。

**set**（[set]）的 `key_type` 和 `value_type` 都是 `Key`，迭代器是常量迭代器：通过迭代器修改元素可能破坏排序，所以不允许（[[associative.reqmts.general#6]]）。

[set.modifiers] ¶1–¶3 有一个 C++26 的异构 `insert(K&& x)`，要求比较器透明。已有与 `x` 等价的元素时没有效果；否则令 `r = equal_range(x)`，用 `std::forward<K>(x)` 构造 `u`，如果 `equal_range(u) == r` 为假，行为未定义。这和 `map` 的异构插入是同一个模式。

**multiset** 与 `set` 相同，但支持等价键，没有异构 `insert`。

## libc++ 实现

{{impl}} libc++ 的四个有序容器都基于 `<__tree>` 中的红黑树。

- `sizeof(std::map<int, int>)` 和 `sizeof(std::set<int>)` 都是 24 字节：最左节点指针、一个只含 left 指针的尾节点（作为 `end()`，也是根的父节点，直接嵌在容器对象里）、元素个数。比较器是空类时不占空间。
- 每个节点有 left、right、parent 三个指针，一个颜色位（填充到 8 字节），然后是元素。`map<int, int>` 的节点是 40 字节，本机用一个打印请求大小的分配器验证过。
- 尾节点嵌在容器对象里，`end()` 指向容器对象内部，交换两个容器后 `end()` 不会跟着元素走。这就是 [[container.reqmts#65]] 规定交换后 `a.end()` 是否等于 `b.end()` 未指定的现实原因。

## 常见误解

!!! pitfall "用 `m[k]` 判断键是否存在"
    `if (m[k] == 0)` 会插入 `k`。判断存在用 `contains(k)`（C++20）或者 `find(k) != end()`。

!!! pitfall "用 `<=` 作比较器"
    比较器必须是严格弱序，这是关联容器的前置条件，违反它是未定义行为。用 `std::less_equal` 时唯一键容器会出现重复键，`find` 也会失败，见 [[associative.reqmts]]。

!!! pitfall "对 `set` 的元素 `const_cast` 后修改参与比较的成员"
    `set` 的迭代器是常量迭代器，就是为了防止这件事。如果只修改不参与比较的成员，可以把它声明为 `mutable`；要修改参与比较的部分，用 `extract`、修改、再 `insert`（[[container.node]]）。

## 思考题

!!! question "思考题"
    `std::map<std::string, int> m;` 中键 `"k"` 已经存在。`m.emplace("k", 1);` 和 `m.try_emplace("k", 1);` 哪个可能分配内存？

<details markdown="1">
<summary>答案</summary>

`emplace` 可能分配。它的第一个实参是 `const char[2]` 而不是 `std::string`，libc++ 需要先分配一个节点，在里面构造 `pair<const std::string, int>`，才能拿到键去比较；发现重复后再销毁并释放这个节点。

`try_emplace("k", 1)` 会先把 `"k"` 转换成一个 `std::string` 临时对象（短字符串不分配堆内存），用它查找；键存在时没有效果，不分配节点。如果用 C++26 的异构 `try_emplace` 加透明比较器，连这个临时 `std::string` 都可以省掉。
</details>

## 小结

| 容器 | 键 | 特有成员 |
|---|---|---|
| `map` | 唯一 | `operator[]`（即 `try_emplace`）、`at`、`lookup`、`try_emplace`、`insert_or_assign`，以及 C++26 异构版本 |
| `multimap` | 等价 | 只有 `insert(P&&)` |
| `set` | 唯一 | C++26 异构 `insert(K&&)` |
| `multiset` | 等价 | 无 |
