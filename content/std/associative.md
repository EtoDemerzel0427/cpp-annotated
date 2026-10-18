---
title: map、set、multimap、multiset
summary: 四个有序关联容器的具体条款——map::operator[] 即 try_emplace、at 与 lookup、try_emplace 不碰实参 vs emplace 可能"吃掉"实参、insert_or_assign、C++26 异构插入及其 UB 条件、推导指引与 iter-key-type、erase_if；libc++ 红黑树节点布局实测与常见陷阱
status: done
covers: *
related: associative.reqmts, container.node, container.requirements, unord, flat.map, flat.set, alg.sorting
tags: 标准库, 容器, map, set, 红黑树, try_emplace
updated: 2026-10-18
---

[associative] 定义 `<map>`（`map`、`multimap`）和 `<set>`（`set`、`multiset`）。它们的大部分语义来自 [[associative.reqmts]]，本节只补充每个类模板**特有**的成员：主要是 `map` 的元素访问和"带键的插入"家族。

## 概述与推导指引（[associative.general]）

¶1：`<map>` 定义 `map` 与 `multimap`，`<set>` 定义 `set` 与 `multiset`。¶2：定义了推导指引用的仅阐述别名：

| 别名 | 含义 |
|---|---|
| `iter-value-type<It>` | `iterator_traits<It>::value_type` |
| `iter-key-type<It>` | `remove_const_t<tuple_element_t<0, iter-value-type<It>>>` |
| `iter-mapped-type<It>` | `tuple_element_t<1, iter-value-type<It>>` |
| `iter-to-alloc-type<It>` | `pair<const iter-key-type<It>, iter-mapped-type<It>>` |
| `range-key-type<R>` 等 | 对 `ranges::range_value_t<R>` 的同样处理 |

`iter-key-type` 去掉了 `const`，所以从另一个 `map` 的迭代器（值类型 `pair<const K, V>`）也能推导出 `map<K, V>`；从 `vector<pair<K, V>>` 推导同样可行。初始化器列表的推导指引接受 `initializer_list<pair<Key, T>>`，所以 `std::map m{std::pair{1, 2.0}, std::pair{2, 3.0}}` 推导出 `map<int, double>`。

## map（[map]）

### 概述（[map.overview]）

¶1：`map` 支持唯一键，并提供基于键快速检索另一类型 `T` 的值；支持双向迭代器。¶2：满足容器、可逆容器、分配器感知容器、关联容器要求，提供唯一键（`a_uniq`）操作；`key_type` 为 `Key`，`value_type` 为 `pair<const Key, T>`。¶3：迭代器满足 constexpr 迭代器要求（C++26 起 `map` 整体 constexpr，本机 libc++ 已实现）。

### 构造（[map.cons]）

比较器 + 分配器构造为常数；区间构造（迭代器对或 `from_range`）在区间**已按 `comp` 排序时线性**，否则 N log N（¶1–¶6）。

### 元素访问（[map.access]）

| 成员 | 规定 | 要点 |
|---|---|---|
| `operator[](const key_type& x)` | 等价于 `return try_emplace(x).first->second;`（¶1） | 键不存在时**插入**值初始化的 `T` |
| `operator[](key_type&& x)` | 等价于 `try_emplace(std::move(x)).first->second`（¶2） | |
| `template<class K> operator[](K&& x)` | *Constraints*：`Compare::is_transparent` 有效（¶3–¶4） | C++26 异构插入 |
| `at(x)` | 返回映射值引用；不存在则抛 `out_of_range`（¶5–¶7） | 对数 |
| `template<class K> at(const K& x)` | 透明比较器；前置条件 `find(x)` 良构且行为良定义（¶8–¶12） | |
| `lookup(x)` | 返回 `optional<mapped_type&>`：存在则为 `find(x)->second`，否则 `nullopt`（¶13–¶16） | 较新草案新增，配合 C++26 的 `optional<T&>` |

`operator[]` 用 `try_emplace` 定义，带来两条后果：

1. `mapped_type` 必须能从**空实参列表**构造（经由 `piecewise_construct, forward_as_tuple(k), forward_as_tuple()`）。没有默认构造函数的 `T` 不能用 `operator[]`：

    ```cpp title="map-subscript-nodefault.cpp" error
    #include <map>
    struct NoDefault { NoDefault(int) {} };
    int main() {
      std::map<int, NoDefault> m;
      m.try_emplace(1, 42);    // OK
      m[1];                    // error: operator[] 需要 mapped_type 可默认构造
    }
    ```

2. `operator[]` 是**修改**操作：它不能用于 `const map`，也不在 [container.requirements.dataraces] 的"视为 const"名单里（[[container.requirements]]）。只读访问用 `at`、`find`、`contains` 或 `lookup`。

`lookup` 在本机 libc++ 中尚未提供。

### 修改器（[map.modifiers]）

**`insert(P&& x)`**（¶1–¶2）：*Constraints* `is_constructible_v<value_type, P&&>`；等价于 `emplace(std::forward<P>(x))`。这个模板让 `m.insert({1, "x"})` 之外的 `m.insert(std::pair{1, "x"})`（`pair<int, const char*>`）也能直接构造 `pair<const int, std::string>` 而不经过中间 `value_type` 临时对象。

**`try_emplace(k, args…)`**（¶3–¶10）：

!!! std
    If the map already contains an element whose key is equivalent to k, there is no effect.

    若 map 已含键等价于 k 的元素，则无效果。

"无效果"是关键：`args…` **不会被移动**。对比 `emplace(k, args…)`——唯一键容器必须先构造出 `value_type` 才能拿到键做比较（[[associative.reqmts]] ¶49 只说"插入 t 当且仅当……"），键已存在时这个临时对象被销毁，而右值实参已经被移进去了。

```cpp title="try-emplace.cpp" run ok
#include <map>
#include <memory>
#include <string>
#include <cassert>

int main() {
  std::map<std::string, std::unique_ptr<int>> m;
  m.emplace("a", std::make_unique<int>(1));

  auto p = std::make_unique<int>(2);
  m.try_emplace("a", std::move(p));        // 键已存在：不构造 value_type，p 不被移动
  assert(p != nullptr);

  auto q = std::make_unique<int>(3);
  m.emplace("a", std::move(q));            // emplace 可能已把 q 移进一个临时节点再丢弃
  // 此处 q 的状态未指明（本机 libc++ 中 q 已为空）

  auto [it, inserted] = m.insert_or_assign("a", std::make_unique<int>(4));
  assert(!inserted && *it->second == 4);   // 已存在：赋值给 mapped

  std::map<std::string, int> counts;
  ++counts["x"];                           // operator[]：不存在则值初始化 int 后插入
  assert(counts.at("x") == 1);
}
```

{{impl}} libc++ 在 `emplace` 的第一个实参**恰好是 `key_type`** 时会先用它查找、找到就不构造节点（把 `std::map<int, unique_ptr<int>>` 换成 `emplace(1, std::move(q))`，本机实测 `q` 保持不变）；实参是 `"a"`（`const char[2]`）这类需要转换的类型时，它只能先构造节点。标准对 `emplace` 不作此保证，`try_emplace` 才有保证。

**`insert_or_assign(k, obj)`**（¶16–¶25）：*Mandates* `is_assignable_v<mapped_type&, M&&>`；键存在则把 `obj` 赋给 `e.second`，否则插入 `value_type(k, std::forward<M>(obj))`。返回 `pair<iterator, bool>`（带提示版本返回 `iterator`）。与 `m[k] = obj` 相比，它不要求 `mapped_type` 可默认构造，并且告诉你是否插入了新元素。

**异构版本**（¶11–¶15、¶26–¶31）{{c++26}}：`template<class K, class... Args> try_emplace(K&& k, Args&&...)` 与 `template<class K, class M> insert_or_assign(K&& k, M&& obj)` 要求 `Compare::is_transparent`（`try_emplace` 的首个重载还排除可转换为迭代器的 `K`）。效果描述里埋着一条 UB：

!!! std
    let r be equal_range(k). Constructs an object u of type value_type with ... If equal_range(u.first) == r is false, the behavior is undefined.

    令 r 为 equal_range(k)，构造 value_type 对象 u；若 equal_range(u.first) == r 为假，行为未定义。

也就是说：用异构键 `k` 构造出来的真正的键 `u.first`，必须落在与 `k` **完全相同的位置**。如果 `Key` 从 `K` 的转换会改变它在比较器下的位置（例如截断、规范化大小写而比较器不规范化），就是 {{ub}}。这条前置条件让实现可以"先用 `k` 找到插入点、再构造节点、直接链入"，而不必用 `u.first` 再查一遍。本机 libc++ 尚未实现异构插入（`__cpp_lib_associative_heterogeneous_insertion` 未定义）。

### 擦除（[map.erasure]）

`erase_if(c, pred)` 被规定为逐个 `c.erase(i)` 的循环（¶1），返回擦除个数；节点式容器不能用 erase-remove（`remove` 要给元素赋值，而 `pair<const K, T>` 不可赋值）。

## multimap（[multimap]）

`multimap` 支持等价键（一个键可对应多个值），提供 `a_eq` 操作；**没有** `operator[]`、`at`、`try_emplace`、`insert_or_assign`——"键对应的那个值"在 `multimap` 中没有定义。构造（[multimap.cons]）同 `map`；修改器（[multimap.modifiers]）只有 `insert(P&&)` 模板，等价于 `emplace`；擦除（[multimap.erasure]）同 `map`。等价键的插入顺序与保持规则见 [[associative.reqmts]] ¶4、¶54。

## set 与 multiset（[set]、[multiset]）

`set` 的 `value_type` 与 `key_type` 都是 `Key`，`iterator` 是**常量迭代器**——不能经由迭代器修改元素，因为那可能破坏排序（[[associative.reqmts]] ¶6）。构造与 `erase_if` 同 `map`。

[set.modifiers] 有一个 {{c++26}} 的异构插入：`template<class K> insert(K&& x)` / `insert(hint, K&& x)`，要求 `Compare::is_transparent`；若已含与 `x` 等价的元素则无效果；否则令 `r = equal_range(x)`，以 `std::forward<K>(x)` 构造 `u`，**若 `equal_range(u) == r` 为假则 UB**——与 `map` 的异构插入同一模式。有趣的细节：草案中"不可转换为迭代器"的约束只对**带提示的**第二个重载列出（[set.modifiers] ¶1），而 `map::try_emplace` 的同类约束列在第一个重载上——两者防范的歧义不同：`set::insert(hint, x)` 若 `x` 是迭代器，就和区间插入 `insert(first, last)` 撞车；`map::try_emplace(k, args…)` 若 `k` 是迭代器，就和带提示的 `try_emplace(hint, key, args…)` 撞车。

`multiset` 同理，没有异构 `insert`。

## libc++ 实现笔记

{{impl}} libc++ 的四个有序容器都基于 `<__tree>` 中的红黑树：

- `sizeof(std::map<int,int>) == sizeof(std::set<int>) == 24`：起始节点指针、"尾节点"（只含一个 left 指针，作为 `end()` 和根的父节点，内嵌在容器对象里）、元素计数；比较器为空类时经由空基类/`[[no_unique_address]]` 不占空间。
- 节点：`left`、`right`、`parent` 三个指针 + 一个 `bool` 颜色位（填充到 8 字节）+ 值。`map<int,int>` 的节点为 40 字节（本机用计数分配器实测 `allocate(1)` 请求 40 字节）。
- 因为尾节点内嵌在容器对象里，`end()` 指向容器对象内部——这就是 [[container.requirements.general]] ¶65 说"`a.end()` 交换后是否等于 `b.end()` 未指明"的现实原因。

## 常见误区

!!! pitfall "用 `m[k]` 判断键是否存在"
    `if (m[k] == 0)` 会**插入** `k`。判断存在用 `contains(k)`（C++20）或 `find(k) != end()`。

!!! pitfall "用 `<=` 或不一致的比较器"
    见 [[associative.reqmts]] 的 `less_equal` 例子：唯一键容器里出现重复键、`find` 失败——严格弱序是前置条件，违反即 UB。

!!! pitfall "在 `set` 元素上 `const_cast` 修改参与比较的成员"
    `set` 的迭代器是常量迭代器正是为了防止这件事。若必须修改"不参与比较"的成员，把它声明为 `mutable`；若要修改参与比较的部分，用 `extract` → 修改 → `insert`（[[container.node]]）。

## 思考题

!!! question "`std::map<std::string, int> m; m.emplace(“k”, 1);` 与 `m.try_emplace(“k”, 1);`，在键 `“k”` 已存在时，哪个可能分配内存？"

<details markdown="1">
<summary>展开查看答案与解析</summary>

`emplace` 可能：它（在 libc++ 中，因为第一个实参是 `const char[2]` 而不是 `std::string`）需要先分配一个节点并在其中构造 `pair<const std::string, int>`，才能拿到键与已有元素比较；发现重复后再销毁并释放。`try_emplace("k", 1)` 中 `"k"` 先被转换为 `key_type`（`const key_type&` 形参，产生一个 `std::string` 临时对象——短字符串时不分配），用它查找，存在则"无效果"，不分配节点。若使用 C++26 的异构 `try_emplace` 加透明比较器，连这个临时 `std::string` 都可以省掉。
</details>

## 小结

| 容器 | 键 | 特有成员 |
|---|---|---|
| `map` | 唯一 | `operator[]`（= `try_emplace`）、`at`、`lookup`、`try_emplace`、`insert_or_assign`、C++26 异构版本 |
| `multimap` | 等价 | 只有 `insert(P&&)` |
| `set` | 唯一 | C++26 异构 `insert(K&&)` |
| `multiset` | 等价 | — |

- `try_emplace` 在键存在时**不碰**实参；`emplace` 不保证这一点。
- C++26 异构插入要求"由 `k` 构造出的键落在与 `k` 相同的 `equal_range`"，否则 UB。
- `erase_if` 是逐个擦除；`operator[]` 是修改操作。
