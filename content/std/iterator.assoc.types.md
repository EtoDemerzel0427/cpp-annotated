---
title: 迭代器关联类型
summary: incrementable_traits / iter_difference_t、indirectly_readable_traits / iter_value_t、iterator_traits——三套特征的偏特化规则；"iterator_traits 是否由主模板生成"这一开关如何决定 iter_value_t 的来源；C++20 iterator_traits 主模板按 cpp17-input-iterator 等说明专用概念自动推导五个成员；指针特化带 iterator_concept = contiguous_iterator_tag。
status: done
covers: *
since: c++98
papers: P0896R4
related: iterator.requirements, iterator.concepts, iterator.cpp17, std.iterator.tags, iterator.cust, temp.spec.partial, temp.deduct, namespace.std
tags: 标准库, 迭代器, iterator_traits, 类型特征
updated: 2026-10-18
---

泛型算法经常需要回答三个关于迭代器 `I` 的问题：**两个 `I` 相减得到什么类型**（差值类型）？**`*i` 读出来的值应当存成什么类型**（值类型）？**`I` 属于哪一类**（类别）？[iterator.assoc.types] 用三个类模板回答它们：

| 问题 | C++20 起的首选写法 | 底层特征 | 子条款 |
|---|---|---|---|
| 差值类型 | `iter_difference_t<I>` | `incrementable_traits<I>` | [incrementable.traits] |
| 值类型 | `iter_value_t<I>` | `indirectly_readable_traits<I>` | [readable.traits] |
| 类别、`pointer`、`reference` | `iterator_traits<I>`（以及概念） | `iterator_traits<I>` | [iterator.traits] |

另有两个在概要中直接定义的别名：`iter_reference_t<T>` = `decltype(*declval<T&>())`，`iter_rvalue_reference_t<T>` = `decltype(ranges::iter_move(declval<T&>()))`（[[iterators]]、[[iterator.cust]]）。

C++98 只有 `iterator_traits` 一个；C++20 把差值类型与值类型拆出来，是因为新概念体系需要对**不是迭代器**的类型也问这两个问题：`weakly_incrementable` 的整数类型需要差值类型，`indirectly_readable` 的 `shared_ptr<int>`、`unique_ptr<int>` 需要值类型。

## `incrementable_traits` 与 `iter_difference_t`（[incrementable.traits]）

¶1 要求：若 `WI` 建模 `weakly_incrementable`，则 `iter_difference_t<WI>` 是它的差值类型。`incrementable_traits` 的规则按偏特化依次是：

1. 主模板：空（没有 `difference_type`）；
2. `T*`（`T` 为对象类型）：`ptrdiff_t`——函数指针、`void*` 被排除；
3. `const I`：转发给 `I`；
4. 有嵌套 `T::difference_type`：用它；
5. 没有嵌套 `difference_type`，但 `a - b` 是整数类型：`make_signed_t<decltype(a - b)>`。

第 5 条让 `int`、`unsigned` 这种"本身就是可递增值"的类型也有差值类型：`iter_difference_t<unsigned>` 是 `int`。

¶2 是本节最微妙的地方：

!!! std
    Let RI be remove_cvref_t<I>. The type iter_difference_t<I> denotes incrementable_traits<RI>::difference_type if iterator_traits<RI> names a specialization generated from the primary template, and iterator_traits<RI>::difference_type otherwise.

    若 `iterator_traits<RI>` 是**由主模板生成**的特化，就查 `incrementable_traits`；否则（用户或库**显式/偏特化**了 `iterator_traits`）就以该特化中的 `difference_type` 为准。

动机是**向后兼容**：C++17 及以前，用户给自己的迭代器特化 `iterator_traits` 是告知关联类型的标准方式（[[std.iterator.tags]] 的例子正是这么做的）。C++20 的新别名必须尊重这些既有特化，否则同一个迭代器会出现两套互相矛盾的答案。而对没有特化 `iterator_traits` 的类型，主模板自己就是从 `incrementable_traits` 等推导出来的——不能反过来再查它，否则就是循环。

"是否由主模板生成"不是程序能直接查询的属性，标准用它作为规格手段；实现通常在主模板里放一个标记成员。

!!! impl "libc++"
    libc++ 在 `iterator_traits` 主模板里定义 `using __primary_template = iterator_traits;`，然后用"`iterator_traits<I>::__primary_template` 是否就是 `iterator_traits<I>` 自身"来判断。用户的特化不会有这个成员（或者其值不同），于是被识别为"非主模板生成"。

¶3 允许用户对程序定义类型特化 `incrementable_traits`。

## `indirectly_readable_traits` 与 `iter_value_t`（[readable.traits]）

¶1 要求：若 `R` 建模 `indirectly_readable`，`iter_value_t<R>` 是它的值类型。规则比差值类型复杂，因为"值类型"有两种常见的嵌套名：迭代器习惯用 `value_type`，智能指针习惯用 `element_type`。

- 说明专用的 *`cond-value-type<T>`*：仅当 `T` 是**对象类型**时提供 `value_type = remove_cv_t<T>`；
- `T*`：*`cond-value-type<T>`*——所以 `iter_value_t<const int*>` 是 `int`（去 cv），`void*` 没有值类型；
- 数组类型 `I`：`remove_cv_t<remove_extent_t<I>>`——`iter_value_t<int[3]>` 是 `int`（数组可以作为 `indirectly_readable` 的参数是因为它会退化为指针）；
- `const I`：转发给 `I`；
- 只有 `value_type`：用它；只有 `element_type`：用它；
- **两者都有**：若去 cv 后相同，用 `value_type`；否则**无值类型**（歧义，宁可不答）。

¶2 与 `iter_difference_t` 完全平行：`iterator_traits<RI>` 由主模板生成时查 `indirectly_readable_traits`，否则查 `iterator_traits<RI>::value_type`。¶3 允许对程序定义类型特化。

¶4（注 1）与 ¶5（注 2）各给一个边界：

- 一些老式输出迭代器声明 `value_type = void`；*`cond-value-type<void>`* 为空，所以它们没有值类型，也不是 `indirectly_readable`。
- `shared_ptr<int>` 是 `indirectly_readable`，值类型是 `int`；`shared_ptr<void>` 的 `element_type` 是 `void`，没有值类型，也不是 `indirectly_readable`。

```cpp run title="value_type.cpp" ok
#include <iterator>
#include <memory>
#include <optional>

static_assert(std::same_as<std::iter_value_t<const int*>, int>);
static_assert(std::same_as<std::iter_value_t<int[3]>, int>);
static_assert(std::same_as<std::iter_difference_t<unsigned>, int>);
static_assert(std::indirectly_readable<std::shared_ptr<int>>);
static_assert(!std::indirectly_readable<std::shared_ptr<void>>);
static_assert(!std::indirectly_readable<std::optional<int>>);  // 见下文：深 const

int main() {}
```

最后一行值得停一下：`optional<int>` 有 `value_type`，也有 `operator*`，却**不是** `indirectly_readable`。原因在 [[iterator.concept.readable]] 的定义：它对 `const In` 求 `*in`，要求结果类型与 `iter_reference_t<In>`（对非 const 左值求 `*`）**完全相同**。`optional` 是"深 const"的——`*const_opt` 得 `const int&`，`*opt` 得 `int&`——于是不满足。`shared_ptr` 是"浅 const"的（`const shared_ptr<int>` 解引用仍得 `int&`），所以满足。这条要求正是把"像指针的东西"和"像值的容器"区分开的那把刀。

## `iterator_traits`（[iterator.traits]）

### 它要提供什么（¶1）

¶1 规定 `iterator_traits<I>` 的五个成员：`iterator_category`（类别标签）、`value_type`、`difference_type`、`pointer`、`reference`。对类类型的迭代器对象 `a`，`pointer` 与 `reference` 分别应是 `decltype(a.operator->())` 与 `decltype(*a)`；不支持 `operator->` 时 `pointer` 为 `void`。输出迭代器的 `value_type`、`difference_type`、`reference` 可以是 `void`。

### 五个说明专用概念（¶2）

C++20 主模板要自动推导这些成员，就得先判断"`I` 像不像一个 C++17 迭代器"。¶2 为此定义了五个说明专用概念，它们是 [[iterator.cpp17]] 命名要求的**语法近似**：

| 概念 | 关键要求 |
|---|---|
| *`cpp17-iterator`* | `*i`、`*i++` 可引用，`++i` 返回 `I&`，`copyable<I>` |
| *`cpp17-input-iterator`* | 上者 + `equality_comparable` + 有 `incrementable_traits` 差值类型（且为 `signed_integral`）+ 有 `indirectly_readable_traits` 值类型 + 两组 `common_reference` |
| *`cpp17-forward-iterator`* | 上者 + 可默认构造 + **`iter_reference_t<I>` 是引用类型**且去 cvref 后等于值类型 + `i++`/`*i++` 的类型约束 |
| *`cpp17-bidirectional-iterator`* | 上者 + `--i`、`i--`、`*i--` |
| *`cpp17-random-access-iterator`* | 上者 + `totally_ordered` + `+= -= + - []` 与 `i - i` |

注意 *`cpp17-input-iterator`* 要求差值类型是 `signed_integral`——整数类类型不算——以及 *`cpp17-forward-iterator`* 要求真引用。这两条正是 `iota_view` 的迭代器在 `iterator_traits` 中"降级"为输入迭代器的原因。

### 主模板的推导规则（¶3）

¶3 是 C++20 对 `iterator_traits` 的核心改写。主模板生成的特化按以下顺序确定成员：

1. **（3.1）`I` 自己声明了**四个成员 `difference_type`、`value_type`、`reference`、`iterator_category`（按 [[temp.deduct]] 的意义"有效"）：照抄；`pointer` 有则照抄，无则为 `void`。这是 C++98 风格迭代器的路径。
2. **（3.2）否则，若 `I` 满足 *`cpp17-input-iterator`***：
    - `value_type` 取自 `indirectly_readable_traits`，`difference_type` 取自 `incrementable_traits`；
    - `pointer`：有 `I::pointer` 用之；否则 `decltype(declval<I&>().operator->())` 合法就用它；否则 `void`；
    - `reference`：有 `I::reference` 用之，否则 `iter_reference_t<I>`；
    - `iterator_category`：有 `I::iterator_category` 用之；否则按满足的最强 *cpp17* 概念取 `random_access_iterator_tag`/`bidirectional_iterator_tag`/`forward_iterator_tag`/`input_iterator_tag`。
3. **（3.3）否则，若满足 *`cpp17-iterator`***：当作输出迭代器——`iterator_category = output_iterator_tag`，`value_type`/`pointer`/`reference` 为 `void`，`difference_type` 有则取 `incrementable_traits` 的，否则 `void`。
4. **（3.4）否则**：`iterator_traits<I>` **没有任何**这些成员。

第 4 条让 `iterator_traits` 成为 SFINAE 友好的：`iterator_traits<int>::value_type` 是替换失败而非硬错误。

注意（3.2）中自动推导出的类别**永远不会是** `contiguous_iterator_tag`——C++17 命名要求里没有"连续"这一档。

### `iterator_concept`（¶4）

¶4：`iterator_traits` 的显式或偏特化**可以**有一个 `iterator_concept` 成员，用来表明对 C++20 概念的符合程度。例 1：想声明"符合 `input_iterator` 概念但不符合 *Cpp17InputIterator*"，可以让特化的 `iterator_concept` 为 `input_iterator_tag` 而**不声明** `iterator_category`。这些成员如何被读取见 [[iterator.concepts]] 中的 *`ITER_TRAITS`*/*`ITER_CONCEPT`*。

注意：主模板**从不**生成 `iterator_concept` 成员——它只在特化里出现。对普通类类型迭代器，*`ITER_CONCEPT`* 直接去读 `I::iterator_concept`，而不经过 `iterator_traits`。

### 指针特化（¶5）

```cpp
template<class T> requires is_object_v<T>
struct iterator_traits<T*> {
  using iterator_concept  = contiguous_iterator_tag;
  using iterator_category = random_access_iterator_tag;
  using value_type        = remove_cv_t<T>;
  using difference_type   = ptrdiff_t;
  using pointer           = T*;
  using reference         = T&;
};
```

三个细节：`requires is_object_v<T>` 排除了函数指针与 `void*`；`value_type` 去掉了 cv（`const int*` 的值类型是 `int`）；`iterator_category` 仍是 `random_access_iterator_tag`（为兼容老代码的标签分派），连续性只通过 `iterator_concept` 表达。

¶6 例 2 用 `iterator_traits<BI>::difference_type` 与 `value_type` 实现了一个 `reverse`——这就是 C++98 时代泛型代码的典型写法；今天会写 `iter_difference_t<BI>` 与 `iter_value_t<BI>`。

## 例子：什么都不写，`iterator_traits` 也能推导

```cpp run title="traits_deduce.cpp" ok
#include <iterator>
#include <ranges>

// C++20 风格：只声明 iterator_concept、value_type、difference_type
struct It {
    using iterator_concept = std::forward_iterator_tag;
    using value_type = int;
    using difference_type = std::ptrdiff_t;
    int* p;
    int& operator*() const { return *p; }
    It& operator++() { ++p; return *this; }
    It operator++(int) { auto t = *this; ++p; return t; }
    bool operator==(const It&) const = default;
};
// 没有 iterator_category：走 (3.2)，满足 cpp17-forward-iterator → forward_iterator_tag
static_assert(std::same_as<std::iterator_traits<It>::iterator_category,
                           std::forward_iterator_tag>);
static_assert(std::same_as<std::iterator_traits<It>::pointer, void>);   // 无 operator->
static_assert(std::forward_iterator<It>);

// iota 的迭代器：*it 返回 int 纯右值 → 不满足 cpp17-forward-iterator
using IotaIt = std::ranges::iterator_t<std::ranges::iota_view<int, int>>;
static_assert(std::same_as<std::iterator_traits<IotaIt>::iterator_category,
                           std::input_iterator_tag>);
static_assert(std::random_access_iterator<IotaIt>);

int main() {}
```

`iota_view` 迭代器的 `iterator_category` 其实是它自己声明的成员（[[range.iota.iterator]] 规定：当 `W` 建模 `incrementable` 且差值类型是整数类型时，声明为 `input_iterator_tag`），与 (3.2) 推导的结果一致——两条路都会把它判为 C++17 意义上的输入迭代器。

## 常见误区

!!! pitfall "特化了 `iterator_traits` 就别再指望成员被自动推导"
    一旦你特化了 `iterator_traits<MyIt>`，¶2 就会让 `iter_value_t<MyIt>`、`iter_difference_t<MyIt>` 改查你的特化，*`ITER_CONCEPT`* 也改查它（[[iterator.concepts]]）。特化里漏写 `iterator_concept`，C++20 概念就只能看到 `iterator_category`；漏写 `value_type`，`iter_value_t` 就不存在。C++20 之后，给类型自身加成员几乎总是比特化 `iterator_traits` 更好的选择。

!!! pitfall "`iterator_traits<const I>` 不是 `iterator_traits<I>`"
    `incrementable_traits` 与 `indirectly_readable_traits` 都有 `const I` 偏特化，`iter_value_t` 等别名还会先 `remove_cvref_t`；但 `iterator_traits<const It>` 由主模板生成，`const It` 不满足 `copyable` 等要求，通常没有任何成员。总是对去 cv 的类型使用 `iterator_traits`，或者干脆用 `iter_*_t` 别名。

## 思考题

!!! question "思考题"
    1. 一个类型同时有 `value_type = int` 和 `element_type = const int`，`iter_value_t` 是什么？若 `element_type = long` 呢？
    2. 为什么 `incrementable_traits` 的第 5 条用 `make_signed_t`？`iter_difference_t<unsigned char>` 是什么？
    3. 写出一个类型，使 `iterator_traits<X>::iterator_category` 为 `output_iterator_tag`，且你没有声明任何成员类型。

<details markdown="1">
<summary>展开查看答案与解析</summary>

1. `value_type` 与 `remove_cv_t<element_type>` 相同，取 `int`。若 `element_type = long`，两者不同，`indirectly_readable_traits` 没有 `value_type`，`iter_value_t` 不存在，类型不是 `indirectly_readable`。
2. 差值类型必须是有符号的（[[iterator.concept.winc]]）。`unsigned char - unsigned char` 经整数提升得 `int`，`make_signed_t<int>` 为 `int`；所以 `iter_difference_t<unsigned char>` 是 `int`。
3. 任何满足 *`cpp17-iterator`* 但不满足 *`cpp17-input-iterator`* 的类型都行，例如 `operator*` 返回自身引用、`operator++` 返回自身引用、可复制，但没有 `operator==`（不满足 `equality_comparable`）——走 (3.3)。这类推导出来的 `difference_type` 是 `void`，除非 `incrementable_traits` 能找到一个。
</details>

## 小结

!!! summary
    - `iter_difference_t`/`iter_value_t`：`iterator_traits<RI>` 由主模板生成时查新特征，否则尊重用户特化。
    - `indirectly_readable_traits` 同时识别 `value_type` 与 `element_type`，冲突时宁缺毋滥；只给对象类型提供值类型。
    - C++20 `iterator_traits` 主模板：有四个成员就照抄；否则按 *cpp17* 说明专用概念推导；什么都不像就为空（SFINAE 友好）。
    - 自动推导的类别最高到 `random_access_iterator_tag`；`iterator_concept` 只出现在特化中（指针特化即是）。
