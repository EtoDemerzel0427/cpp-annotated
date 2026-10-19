---
title: transform 视图
summary: transform_view 对每个元素惰性地调用一个函数：对函数的要求、const 遍历的条件、迭代器强度跟随底层而 C++17 类别在函数返回值时退化为输入迭代器，以及每次解引用都调用函数、返回悬垂引用等陷阱。
status: done
covers: *
since: c++20
papers: P0896R4, P2494R2
related: range.adaptors, range.filter, range.zip, range.elements, range.cache.latest, concepts.callable, iterator.concepts, iterator.cpp17, range.move.wrap
tags: 标准库, 范围, transform, 迭代器类别
updated: 2026-10-19
---

!!! tldr
    - `views::transform(f)` 的第 i 个元素是 `f(底层第 i 个元素)`。它保留底层的迭代器强度（最高随机访问）、大小和首尾同型性，但不是借用范围。
    - 元素不存储，每次解引用都调用一次 `f`。`transform | filter` 会对通过过滤的元素调用两次 `f`。
    - `f` 必须保持相等性（`regular_invocable`），返回类型不能是 `void`；`const transform_view` 能遍历的前提是 `f` 能以 const 调用。
    - `f` 返回值而不是引用时，C++17 风格的 `iterator_category` 是 `input_iterator_tag`，只认 C++17 类别的旧接口会把它当作输入迭代器。
    - `f` 返回引用或视图时，它必须指向比视图活得久的对象，不能指向函数内的临时量。

## 基本用法 [range.transform.overview]

```cpp run ok
#include <ranges>
#include <vector>
#include <cstdio>
int main() {
  std::vector<int> is{0, 1, 2, 3, 4};
  auto squares = std::views::transform(is, [](int i) { return i * i; });
  for (int i : squares) std::printf("%d ", i);   // 0 1 4 9 16
  std::puts("");
}
```

¶1 `transform_view` 给出对底层序列的每个元素施加变换函数后的视图，相当于函数式编程中的 map。¶2 `views::transform` 是范围适配器对象（[[range.adaptors]]），`views::transform(E, F)` 等价于 `transform_view(E, F)`。¶3 例 1 就是上面的代码。

## 类模板 [range.transform.view]

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
    requires range<const V> &&
             regular_invocable<const F&, range_reference_t<const V>>;
  constexpr sentinel<false> end();
  constexpr iterator<false> end() requires common_range<V>;
  // end() 的 const 版本条件同上
  constexpr auto size() requires sized_range<V> { return ranges::size(base_); }
  // size() const、reserve_hint 同理
};
template<class R, class F>
  transform_view(R&&, F) -> transform_view<views::all_t<R>, F>;
```

- `regular_invocable` 要求函数保持相等性（[[concepts.callable]]）。视图可能对同一个元素多次调用 `f`，所以 `f` 有副作用或依赖外部可变状态时，行为没有保证。
- *can-reference* 要求调用结果的类型可以加引用，也就是不能是 `void`。
- `F` 只需要可移动构造。函数对象存放在 *movable-box* 中（[[range.move.wrap]]），C++23 起只能移动的函数对象也可以（[[P2494R2]]）。
- `begin() const` 要求 `const F&` 也能以 `range_reference_t<const V>` 调用。带 `mutable` 的 lambda 的 `operator()` 不是 const 的，会让 `const transform_view` 无法遍历。
- 变换不改变元素个数，底层有大小时 `size()` 直接转发。
- 没有 `begin()` 缓存，`begin()` 就是用 `ranges::begin(base_)` 构造迭代器，是 O(1) 的。

## 迭代器 [range.transform.iterator]

迭代器保存底层迭代器 `current_` 和指向父视图的指针 `parent_`，需要通过它找到 `fun_`。因此 `transform_view` 不是借用范围。

- `operator*` 等价于 `invoke(*parent_->fun_, *current_)`，每次解引用都调用一次 `f`；
- `value_type` 是 `f` 返回类型去掉引用和 cv 限定后的类型；
- `++`、`--`、`+=` 等只移动 `current_`，不调用 `f`。

### iterator_concept 与 iterator_category（¶1–¶2）

¶1 `iterator_concept` 完全跟随底层：底层是随机访问范围就是随机访问，依次类推到双向、前向、输入。它不会是 contiguous 的，因为变换后的元素并不连续存放在内存中。

¶2 C++17 风格的 `iterator_category` 只在底层是前向范围时声明。令 `C` 为底层迭代器的 C++17 类别：

- ¶2.1 如果 `f` 返回引用类型，`C` 派生自 `contiguous_iterator_tag` 时为 `random_access_iterator_tag`，否则就是 `C`；
- ¶2.2 否则，`f` 返回的是值（纯右值），类别为 `input_iterator_tag`。

两者不一致的原因是，C++17 的 *Cpp17ForwardIterator* 要求 `reference` 是真正的引用类型（[[iterator.cpp17]]）。返回 `x * x` 的 lambda 使 `reference` 为 `int`，按 C++17 的规则它只能算输入迭代器，尽管按 C++20 的概念它是随机访问迭代器。

后果是，只认 C++17 类别的旧接口会把它当作输入迭代器。`std::vector(first, last)` 仍然能用，只是不能预先算出长度；`std::prev` 这类要求双向迭代器的函数就不行了：

```cpp run
#include <iterator>
#include <ranges>
#include <vector>
int main() {
  std::vector<int> v{1, 2, 3};
  auto sq = v | std::views::transform([](int x) { return x * x; });
  static_assert(std::ranges::random_access_range<decltype(sq)>);
  static_assert(std::same_as<
      std::iterator_traits<std::ranges::iterator_t<decltype(sq)>>::iterator_category,
      std::input_iterator_tag>);
  auto last = std::prev(sq.end());   // libc++ 拒绝编译
  return *last == 9 ? 0 : 1;
}
```

两条 `static_assert` 都成立。最后的 `std::prev` 被本机 libc++ 内部的 `static_assert` 拒绝（Attempt to prev(it) with a non-bidirectional iterator）。在标准层面，`std::prev` 要求实参满足 *Cpp17BidirectionalIterator*，传入一个只满足 *Cpp17InputIterator* 的迭代器违反了库的要求，行为未定义，拒绝编译是实现允许的一种结果，所以这段代码没有标判定。改用概念版的 `std::ranges::prev` 即可。

## 返回引用的 transform

成员指针也是可调用对象。`views::transform(&Person::name)` 以左值 `Person&` 调用，得到 `std::string&`。返回的是引用，所以元素可以写，`iterator_category` 也保留底层的类别：

```cpp run ok
#include <ranges>
#include <string>
#include <vector>
#include <cstdio>
struct Person { std::string name; int age; };
int main() {
  std::vector<Person> ps{{"Ada", 36}, {"Alan", 41}};
  auto names = ps | std::views::transform(&Person::name);   // 元素类型 std::string&
  static_assert(std::same_as<std::ranges::range_reference_t<decltype(names)>,
                             std::string&>);
  for (auto& n : names) n += "!";                            // 写回原对象

  auto ages = ps | std::views::transform([](const Person& p) { return p.age; });
  for (int a : ages) std::printf("%d ", a);
  std::printf("%s\n", ps[0].name.c_str());   // 36 41 Ada!
}
```

如果只是想让算法按某个字段比较，用算法的投影参数更直接，例如 `ranges::sort(ps, {}, &Person::age)`（[[g:projection]]）。

## 常见陷阱

### 每次解引用都调用函数

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
  std::printf("%d\n", calls);   // 9
}
```

`filter` 判断谓词时解引用底层一次，6 个元素共调用 6 次；循环体读取 3 个偶数的平方时又各解引用一次，再调用 3 次。昂贵的变换函数会被重复调用。可以这样处理：

- 谓词能用原始元素表达时，把 `filter` 放到 `transform` 之前；
- 使用 C++26 的 `views::cache_latest`（[[range.cache.latest]]）：`transform(f) | cache_latest | filter(p)`，每个元素只计算一次。

这里的 lambda 按引用捕获了计数器、有副作用，只是为了数出调用次数。它不保持相等性，形式上违反了 `regular_invocable` 的语义要求，实际代码中不要这样写。

### 返回悬垂的引用或视图

```cpp run ub
#include <ranges>
#include <string>
#include <string_view>
#include <vector>
#include <cstdio>
int main() {
  std::vector<std::string> words{"alpha", "beta"};
  auto r = words | std::views::transform(
      [](const std::string& s) -> std::string_view {
        return s + "!";   // 指向 return 后就销毁的临时 string
      });
  for (std::string_view sv : r)
    std::printf("%.*s\n", int(sv.size()), sv.data());   // UB
}
```

本机 Clang 23 对这段代码给出 `-Wreturn-stack-address` 警告（returning address of local temporary object）。变换函数返回引用或视图时，它必须指向比视图活得久的对象：底层元素的子对象（如 `&Person::name`）可以，函数内的临时量不行。

### mutable lambda

```cpp
auto r = v | views::transform([n = 0](int x) mutable { return x + n++; });
// const 的 r 不能遍历：const F& 不可调用
// n++ 也让函数不再保持相等性，违反 regular_invocable 的语义要求
```

## 小结

| 性质 | `transform_view` |
|---|---|
| 迭代器强度（C++20 概念） | 同底层，最高随机访问 |
| C++17 类别 | 返回引用时同底层（contiguous 降为随机访问），返回值时为输入 |
| sized、common | 同底层 |
| 借用 | 否 |
| const 可遍历 | `const V` 是范围且 `const F&` 可调用时 |
| 函数调用次数 | 每次解引用一次 |
