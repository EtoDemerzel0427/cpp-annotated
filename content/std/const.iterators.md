---
title: 常量迭代器：basic_const_iterator
summary: C++23 新增——iter_const_reference_t 把引用类型与 const 值类型的右值统一为"常量引用"；const_iterator<I> 对已是常量迭代器的 I 原样返回，否则包装成 basic_const_iterator<I>；const_sentinel 对哨位做同样处理；basic_const_iterator 保持底层的遍历类别（包括 contiguous），只把解引用结果变为常量，并能隐式转换回"已知的常量迭代器类型"（如 const T*）。它是 ranges::cbegin 与 views::as_const 的基础。
status: done
covers: *
since: c++23
related: predef.iterators, iterator.requirements, iterator.concepts, iterator.assoc.types, iterator.cust, iterator.range, move.iterators
tags: 标准库, 迭代器, 适配器, const, C++23
updated: 2026-10-18
---

C++11 加入 `std::cbegin`/`cend`，本意是"给我一个不能修改元素的迭代器"。但它的实现只是 `std::begin(as_const(c))`——对 `std::span<int>` 这样的"浅 const"类型（`const span<int>` 的 `begin()` 仍返回可变迭代器），`cbegin` 给出的迭代器**照样能写**。C++20 的 `ranges::cbegin` 起初也有同样的漏洞。

C++23 的解法是提供一个通用工具：给**任意**输入迭代器套一层，使解引用结果变为常量。这就是 [const.iterators] 的 `basic_const_iterator`（{{c++23}}）。`ranges::cbegin`、`ranges::cend`、`views::as_const`、`span::cbegin` 等都以它为基础。

¶1 of [const.iterators.general]：`basic_const_iterator` 是一个迭代器适配器，行为与底层迭代器相同，只是其间接运算符把底层解引用结果隐式转换为使适配后的迭代器成为**常量迭代器**（[[g:constant-iterator]]）的类型。某些泛型算法可以用常量迭代器调用，以避免修改。¶2：`basic_const_iterator` 的特化都是常量迭代器。

!!! warning "实现状态"
    截至本文写作时，clang 23 自带的 libc++ **尚未实现** `basic_const_iterator`、`const_iterator`、`iter_const_reference_t`（其 `<version>` 中 `__cpp_lib_ranges_as_const` 仍被注释掉）。GCC 的 libstdc++ 与 MSVC STL 已提供。本页示例未能在本地 libc++ 上运行，请用 GCC 在 Compiler Explorer 上验证（下表中的公共引用计算已在本地用 `common_reference_t` 逐项核对）。

## 别名模板（[const.iterators.alias]）

```cpp
template<indirectly_readable It>
  using iter_const_reference_t =
    common_reference_t<const iter_value_t<It>&&, iter_reference_t<It>>;

template<class It>
  concept constant-iterator =        // 说明专用
    input_iterator<It> && same_as<iter_const_reference_t<It>, iter_reference_t<It>>;

template<input_iterator I>
  using const_iterator = see below;   // I 若已是 constant-iterator 则为 I，否则 basic_const_iterator<I>

template<semiregular S>
  using const_sentinel = see below;   // S 若是 input_iterator 则为 const_iterator<S>，否则 S
```

`iter_const_reference_t` 的构造非常巧妙：拿"值类型的 const 右值引用"和"原引用类型"求**公共引用**：

| `iter_reference_t<It>` | `iter_value_t<It>` | `iter_const_reference_t<It>` | 常量迭代器？ |
|---|---|---|---|
| `int&` | `int` | `const int&` | 否 |
| `const int&` | `int` | `const int&` | 是 |
| `int&&` | `int` | `const int&&` | 否 |
| `int`（纯右值） | `int` | `int` | 是（纯右值本来就改不了原元素） |
| `vector<bool>::reference` | `bool` | `bool` | 否 |
| `tuple<int&, int&>`（zip） | `tuple<int, int>` | `tuple<const int&, const int&>` | 否 |

最后两行说明它对代理也成立：代理与 `const 值&&` 的公共引用通常是值类型本身或"把每个成员加 const 的代理"，都不能再用于修改原元素。

*`constant-iterator`* 的定义就是"加 const 不改变引用类型"。¶1：`const_iterator<I>` 对常量迭代器原样返回（不多套一层），否则返回 `basic_const_iterator<I>`。¶2：`const_sentinel<S>` 对本身也是输入迭代器的"哨位"（即同类型首尾的普通范围）做同样包装，否则原样返回——纯哨位不能解引用，无需包装。

概要中还提供 `make_const_iterator(it)` 与 `make_const_sentinel(s)`，分别返回 `const_iterator<I>` 与 `const_sentinel<S>`。

## 类模板 `basic_const_iterator`（[const.iterators.iterator]）

```cpp
template<input_iterator Iterator>
class basic_const_iterator {
  Iterator current_ = Iterator();                         // 说明专用
  using reference = iter_const_reference_t<Iterator>;     // 说明专用
  using rvalue-reference =                                // 说明专用
    iter-const-rvalue-reference-t<Iterator>;
public:
  using iterator_type = Iterator;
  using iterator_concept = see below;
  using iterator_category = see below;    // 不总是存在
  using value_type = iter_value_t<Iterator>;
  using difference_type = iter_difference_t<Iterator>;
  // 构造、base()、*、->、++、--、+=、-=、[]、==、比较、+、-、转换运算符、iter_move ...
};
```

成员类型（[const.iterators.types]）：

- ¶1 `iterator_concept` **完整保留**底层的类别，**包括 `contiguous_iterator_tag`**——这是它与 `move_iterator`、`reverse_iterator` 的显著不同：常量化不改变内存布局，`basic_const_iterator<int*>` 仍是连续迭代器；
- ¶2 `iterator_category` 仅当底层建模 `forward_iterator` 时声明，等于底层的 `iterator_traits<Iterator>::iterator_category`。

`reference`、`rvalue-reference` 都是说明专用的**私有**别名——公开接口里没有 `reference` 成员类型，`iterator_traits` 会经 `iter_reference_t` 推导。*`iter-const-rvalue-reference-t`* 是 `common_reference_t<const iter_value_t<I>&&, iter_rvalue_reference_t<I>>`，供 `iter_move` 使用。

### 操作（[const.iterators.ops]）

- 构造：从 `Iterator`（¶1，移动进去）、从 `basic_const_iterator<U>`（`U` 可转换为 `Iterator`，¶2）、从任何可转换为 `Iterator` 的 `T&&`（¶3，`T` 不是 `basic_const_iterator` 本身）。最后一个让 `basic_const_iterator<vector<int>::const_iterator>` 可以直接从 `vector<int>::iterator` 构造。默认构造仅当底层可默认初始化时存在。
- `base() const&` 返回 `const Iterator&`、`base() &&` 移出（¶4–¶5）。
- `operator*`：`static_cast<reference>(*current_)`（¶6）——**这里就是常量化发生的地方**。
- `operator->`：仅当底层引用是左值引用且去 cvref 后等于值类型时提供；连续迭代器返回 `to_address(current_)`，否则 `addressof(*current_)`（¶7），返回类型是 `const auto*`。
- `operator++(int)`：对输入迭代器返回 `void`（¶9）；对前向迭代器是**预置**（defaulted）的后置递增——这是 C++26 之后核心语言允许的新写法（[[over.inc.default]]），效果是"复制、前置递增、返回副本"。`operator--(int)` 同样是预置的。
- `operator[]`、`+=`、`-=`、`+`、`-`：仅随机访问时提供，结果经 `static_cast<reference>` 常量化。
- 比较：与哨位 `==`（¶14）、与自身类型的 `<`/`<=>`、与**其他类型**（底层迭代器能与之比较的 `I`）的双向比较（¶19–¶22）。后者使 `basic_const_iterator<It>` 能直接与 `It`、`It` 的哨位比较。
- `iter_move`：返回 *`rvalue-reference`*，即常量化的右值引用。

### 转换回常量迭代器（¶15–¶16）

```cpp
template<not-a-const-iterator CI>
  requires constant-iterator<CI> && convertible_to<Iterator const&, CI>
constexpr operator CI() const &;
template<not-a-const-iterator CI>
  requires constant-iterator<CI> && convertible_to<Iterator, CI>
constexpr operator CI() &&;
```

`basic_const_iterator<I>` 可以隐式转换为**任何**"底层能转换到的常量迭代器类型"——例如 `basic_const_iterator<int*>` → `const int*`、`basic_const_iterator<vector<int>::iterator>` → `vector<int>::const_iterator`。这保证了 `ranges::cbegin(v)` 的结果能交给只接受原生常量迭代器的老接口。约束 *`not-a-const-iterator`*（`CI` 不是 `basic_const_iterator` 的特化）防止与转换构造函数形成二义。

此外，概要特化了 `common_type`：`basic_const_iterator<T>` 与 `U` 的公共类型是 `basic_const_iterator<common_type_t<T, U>>`，使"一端被常量化、另一端未被常量化"的迭代器可以在 `common_iterator`、`?:` 等场合统一类型。

## 例子

```cpp run title="const_iterator.cpp" ok cc=gsnapshot
#include <cassert>
#include <iterator>
#include <ranges>
#include <span>
#include <vector>

static_assert(std::same_as<std::iter_const_reference_t<int*>, const int&>);
static_assert(std::same_as<std::const_iterator<const int*>, const int*>);          // 已是常量：不包装
static_assert(std::same_as<std::const_iterator<int*>, std::basic_const_iterator<int*>>);
static_assert(std::contiguous_iterator<std::basic_const_iterator<int*>>);          // 类别保留

int main() {
    int a[3]{1, 2, 3};
    std::span<int> s(a);
    auto it = std::ranges::cbegin(s);       // basic_const_iterator<span<int>::iterator>
    // *it = 42;                            // error：*it 是 const int&
    assert(*it == 1);

    std::basic_const_iterator<int*> ci = a;
    const int* p = ci;                      // 转换回原生常量迭代器
    assert(p == a);
}
```

## 常见误区

!!! pitfall "`std::cbegin` 与 `std::ranges::cbegin` 不是一回事"
    `std::cbegin(c)` 仍是 C++11 的定义：`std::begin(as_const(c))`（[[iterator.range]]）。对 `span<int>` 这类"浅 const"的视图，它返回的迭代器可写。需要真正的常量迭代器时用 `std::ranges::cbegin`（C++23 起基于 `const_iterator`）或 `views::as_const`。

!!! pitfall "以为常量化会降级类别"
    与 `move_iterator`（封顶 random access）不同，`basic_const_iterator` 保留 contiguous。所以 `std::span<const int>(ranges::cbegin(s), ranges::cend(s))` 合法。

## 思考题

!!! question "思考题"
    1. 为什么 `iter_const_reference_t` 用 `const iter_value_t<It>&&` 而不是 `const iter_value_t<It>&` 参与公共引用？
    2. `const_iterator<std::istreambuf_iterator<char>>` 是什么类型？

<details markdown="1">
<summary>展开查看答案与解析</summary>

1. 为了不把右值引用"降级"为左值引用：若 `iter_reference_t` 是 `int&&`（如 `move_iterator<int*>`），与 `const int&&` 的公共引用是 `const int&&`，仍保留"可以移走"的右值性（虽然 const 右值实际只能复制）；与 `const int&` 求公共引用则会得到 `const int&`。对左值引用 `int&`，`common_reference_t<const int&&, int&>` 是 `const int&`，结果与用 `const int&` 相同。
2. `istreambuf_iterator<char>` 的引用类型是 `char`（纯右值），`iter_const_reference_t` 也是 `char`，它已是 *`constant-iterator`*，所以 `const_iterator<istreambuf_iterator<char>>` 就是 `istreambuf_iterator<char>` 本身。
</details>

## 小结

!!! summary
    - `iter_const_reference_t<It>` = `common_reference_t<const iter_value_t<It>&&, iter_reference_t<It>>`；与原引用相同即为常量迭代器。
    - `const_iterator<I>`：常量迭代器原样返回，否则 `basic_const_iterator<I>`；`const_sentinel` 只包装"本身是迭代器"的哨位。
    - `basic_const_iterator` 保留全部类别（含 contiguous），解引用经 `static_cast` 常量化，可隐式转换回原生常量迭代器。
    - 它是 C++23 `ranges::cbegin`、`views::as_const` 的基础；libc++ 尚未实现。
