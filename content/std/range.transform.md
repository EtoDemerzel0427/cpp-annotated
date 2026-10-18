---
title: transform 视图
summary: transform_view 对每个元素惰性地施加函数——regular_invocable 与 can-reference 约束、const 迭代要求函数对 const 也可调用、iterator_concept 跟随底层可达 random access 而 C++17 iterator_category 在返回 prvalue 时退化为 input（导致 std::prev 等老接口拒收）、每次解引用都调用函数（transform|filter 双重调用）、返回悬垂引用的 lambda。
status: done
covers: *
since: c++20
papers: P0896R4, P2494R2
related: range.adaptors, range.filter, range.zip, range.elements, range.cache.latest, concepts.callable, iterator.concepts, iterator.cpp17, range.move.wrap
tags: 标准库, 范围, transform, 迭代器类别
updated: 2026-10-18
---

`views::transform(f)` 是函数式编程里的 `map`：视图的第 i 个元素是 `f(底层第 i 个元素)`。它是"最透明"的适配器——保留底层的迭代器强度、大小、common 性——但"元素在每次解引用时现算"这一点带来了一串值得 language lawyer 留意的后果。

## 概览与约束（[range.transform.overview]、[range.transform.view]）

¶1 `transform_view` 给出对底层序列每个元素施加可调用对象后的视图。¶2 `views::transform(E, F)` 表达式等价于 `transform_view(E, F)`。

```cpp
template<input_range V, move_constructible F>
  requires view<V> && is_object_v<F> &&
           regular_invocable<F&, range_reference_t<V>> &&
           can-reference<invoke_result_t<F&, range_reference_t<V>>>
class transform_view : public view_interface<transform_view<V, F>> {
  template<bool> struct iterator;
  template<bool> struct sentinel;
  V base_ = V();
  movable-box<F> fun_;
public:
  constexpr iterator<false> begin();
  constexpr iterator<true> begin() const
    requires range<const V> && regular_invocable<const F&, range_reference_t<const V>>;
  constexpr sentinel<false> end();
  constexpr iterator<false> end() requires common_range<V>;
  // const 版本同理
  constexpr auto size() requires sized_range<V>;
  constexpr auto size() const requires sized_range<const V>;
  // reserve_hint 同理
};
```

- **`regular_invocable`**：函数必须保持相等性（[[concepts.callable]]）。这不是空话：视图可能对同一元素多次调用 `f`，`f` 有副作用或依赖外部可变状态时，行为不受保证。
- ***can-reference***：结果类型不能是 `void`（`iter_reference_t` 必须可以加引用）。
- **`F` 只需 `move_constructible`**：借助 *movable-box*（[[range.move.wrap]]），C++23 起只可移动的函数对象也行（[[P2494R2]]）。
- **const 迭代**：`begin() const` 要求 `const F&` 也能以 `range_reference_t<const V>` 调用。带 `mutable` 的 lambda（其 `operator()` 非 const）会让 `const transform_view` 不可迭代。
- **`size()` 直接转发**：变换不改变元素个数，`transform_view` 在底层 sized 时也 sized。
- **没有 begin 缓存**：`begin()` 就是 `{*this, ranges::begin(base_)}`，O(1)。

## 迭代器（[range.transform.iterator]）

迭代器存底层迭代器 *current_* 和父视图指针 *parent_*（要找到 `fun_`），所以 `transform_view` **不是借用范围**。

- `operator*` 等价于 `invoke(*parent_->fun_, *current_)`——**每次解引用都调用一次 `f`**；
- `value_type` = `remove_cvref_t<invoke_result_t<maybe-const<Const, F>&, range_reference_t<Base>>>`；
- `++`、`--`、`+=` 都只是移动 *current_*，不调用 `f`。

### `iterator_concept` 与 `iterator_category`（¶1–¶2）

¶1 `iterator_concept` 完全跟随底层：random access / bidirectional / forward / input（**不会**到 contiguous——元素不再位于连续存储中）。

¶2 `iterator_category`（仅当底层 forward 时声明）则不同：令 `C` 为底层的 C++17 类别，

- ¶2.1 若 `f` 返回**引用类型**：`C` 派生自 `contiguous_iterator_tag` 时为 `random_access_iterator_tag`，否则为 `C`；
- ¶2.2 否则（`f` 返回 prvalue）：**`input_iterator_tag`**。

原因在于 C++17 的 *Cpp17ForwardIterator* 要求 `reference` 是真正的引用类型（[[iterator.cpp17]]）。返回 `x * x` 的 lambda 让 `reference` 是 `int`，按 C++17 的规则它只能是输入迭代器——尽管 C++20 概念认为它是随机访问的。

后果：只认 C++17 类别的老接口会把它当成输入迭代器。`std::vector(first, last)` 能用（只是不能预先算长度），而 `std::prev`、`std::sort` 等要求更强类别的会被拒绝或失效：

```cpp run error
#include <iterator>
#include <ranges>
#include <vector>
int main() {
  std::vector<int> v{1, 2, 3};
  auto sq = v | std::views::transform([](int x) { return x * x; });
  static_assert(std::ranges::random_access_range<decltype(sq)>);
  static_assert(std::same_as<std::iterator_traits<std::ranges::iterator_t<decltype(sq)>>::iterator_category,
                             std::input_iterator_tag>);
  auto last = std::prev(sq.end());      // error（libc++）：C++17 的 std::prev 要求双向迭代器类别
  return *last == 9 ? 0 : 1;
}
```

上例中前两条 `static_assert` 都成立；报错来自 libc++ 在 `std::prev` 里对类别的 `static_assert`（"Attempt to prev(it) with a non-bidirectional iterator"）。标准层面，把一个只满足 *Cpp17InputIterator* 的迭代器交给要求 *Cpp17BidirectionalIterator* 的 `std::prev`，违反前置条件。修复：改用概念版的 `std::ranges::prev`。

## 投影成员：返回引用的 transform

成员指针也是可调用对象。`views::transform(&Person::name)` 对左值 `Person&` 调用得到 `std::string&`——**引用**，所以元素可写，`iterator_category` 也保留底层的类别：

```cpp run ok
#include <ranges>
#include <string>
#include <vector>
#include <cstdio>
struct Person { std::string name; int age; };
int main() {
  std::vector<Person> ps{{"Ada", 36}, {"Alan", 41}};
  auto names = ps | std::views::transform(&Person::name);      // 成员指针：返回 std::string&
  static_assert(std::same_as<std::ranges::range_reference_t<decltype(names)>, std::string&>);
  for (auto& n : names) n += "!";                                // 可以写回
  auto ages = ps | std::views::transform([](const Person& p) { return p.age; });   // prvalue int
  for (int a : ages) std::printf("%d ", a);
  std::printf("%s\n", ps[0].name.c_str());   // 36 41 Ada!
}
```

（若只是为了给算法提供"按某字段比较"，用算法的**投影**参数 `ranges::sort(ps, {}, &Person::age)` 通常更直接。）

## 坑点

### 1. 每次解引用都调用函数：transform | filter

```cpp run ok
#include <ranges>
#include <vector>
#include <cstdio>
int main() {
  int calls = 0;
  std::vector<int> v{1, 2, 3, 4, 5, 6};
  auto r = v | std::views::transform([&](int x) { ++calls; return x * x; })
             | std::views::filter([](int x) { return x % 2 == 0; });
  for (int x : r) (void)x;
  std::printf("%d\n", calls);   // 9：每个元素被 filter 判定时算一次，3 个偶数平方被读取时又各算一次
}
```

`filter` 的 `++` 解引用底层一次来判断谓词；循环体读取元素时又解引用一次。昂贵的变换函数会被重复调用。对策：

- 把 `filter` 放到 `transform` **之前**（若谓词可以用原始元素表达）；
- C++26 的 `views::cache_latest`（[[range.cache.latest]]）：`transform(f) | cache_latest | filter(p)`，每个元素只算一次。

（这里 lambda 按引用捕获了计数器、有副作用，只是为了演示调用次数；它在形式上违反了 `regular_invocable` 的"保持相等性"语义要求，在生产代码中不要这么做。）

### 2. 返回悬垂引用/视图的函数

```cpp run ub
#include <ranges>
#include <string>
#include <string_view>
#include <vector>
#include <cstdio>
int main() {
  std::vector<std::string> words{"alpha", "beta"};
  auto r = words | std::views::transform([](const std::string& s) -> std::string_view {
    return s + "!";     // string_view 指向一个在 return 后就销毁的临时 string
  });
  for (std::string_view sv : r) std::printf("%.*s\n", int(sv.size()), sv.data());   // UB
}
```

Clang 对这段代码会给出 `-Wdangling-gsl` 告警。规律：**变换函数返回引用或视图时，它必须指向比视图活得更久的东西**——底层元素的子对象（如 `&Person::name`）可以，函数内的临时量不行。

### 3. `mutable` lambda 破坏 const 可迭代性

```cpp
auto r = v | views::transform([n = 0](int x) mutable { return x + n++; });
// const 的 r 不是 range（const F& 不可调用）；而且 n++ 也违反 regular_invocable 的语义要求
```

## 小结

| 性质 | `transform_view` |
|---|---|
| 迭代器强度（C++20） | 同底层，最高 random access |
| C++17 类别 | 返回引用时同底层（contiguous 降为 random access），返回 prvalue 时 input |
| sized / common | 同底层 |
| 借用 | 否 |
| const 可迭代 | 当 `const V` 是范围且 `const F&` 可调用 |
| 函数调用次数 | 每次解引用一次 |
