---
title: 迭代器关联类型
summary: 怎样在编译期查出一个迭代器的差值类型、值类型和类别：incrementable_traits、indirectly_readable_traits、iterator_traits 三个特征类的规则，以及 C++20 的 iterator_traits 主模板怎样自动推导。
status: done
covers: *
since: c++98
papers: P0896R4
related: iterator.requirements, iterator.concepts, iterator.cpp17, std.iterator.tags, iterator.cust, temp.spec.partial, temp.deduct, namespace.std
tags: 标准库, 迭代器, iterator_traits, 类型特征
updated: 2026-10-19
---

!!! tldr
    - C++20 起，查差值类型用 `iter_difference_t<I>`，查值类型用 `iter_value_t<I>`，查 C++17 意义上的类别用 `iterator_traits<I>::iterator_category`。
    - 如果用户特化了 `iterator_traits<I>`，`iter_difference_t` 和 `iter_value_t` 以特化为准；否则查 `incrementable_traits` 和 `indirectly_readable_traits`。
    - `iter_value_t` 同时认 `value_type` 和 `element_type` 两种成员名，二者冲突时不给答案。
    - `iterator_traits` 主模板在类型没有声明成员时会自己推导，推出的类别最高是 `random_access_iterator_tag`；什么都推不出时它是空的，可以安全地用于 SFINAE。

## 三个问题，三个特征类

泛型算法经常要问迭代器 `I` 三个问题：两个 `I` 相减得到什么类型？`*i` 读出的值应该存成什么类型？`I` 属于哪一类？[iterator.assoc.types] 用三个类模板回答：

| 问题 | 首选写法 | 底层特征类 | 子条款 |
|---|---|---|---|
| 差值类型 | `iter_difference_t<I>` | `incrementable_traits<I>` | [incrementable.traits] |
| 值类型 | `iter_value_t<I>` | `indirectly_readable_traits<I>` | [readable.traits] |
| 类别、`pointer`、`reference` | `iterator_traits<I>` | `iterator_traits<I>` | [iterator.traits] |

`<iterator>` 概要里还直接定义了两个别名：`iter_reference_t<T>` 是 `decltype(*declval<T&>())`，`iter_rvalue_reference_t<T>` 是 `decltype(ranges::iter_move(declval<T&>()))`（[[iterators]]、[[iterator.cust]]）。

C++98 只有 `iterator_traits`。C++20 把差值类型和值类型拆出来，是因为新的概念体系要对不是迭代器的类型也问这两个问题：`weakly_incrementable` 的整数需要差值类型，`indirectly_readable` 的 `shared_ptr<int>` 需要值类型。

```cpp run title="value_type.cpp" ok
#include <iterator>
#include <memory>
#include <optional>

static_assert(std::same_as<std::iter_value_t<const int*>, int>);
static_assert(std::same_as<std::iter_value_t<int[3]>, int>);
static_assert(std::same_as<std::iter_difference_t<unsigned>, int>);
static_assert(std::indirectly_readable<std::shared_ptr<int>>);
static_assert(!std::indirectly_readable<std::shared_ptr<void>>);
static_assert(!std::indirectly_readable<std::optional<int>>);

int main() {}
```

下面逐个解释这几行。

## 差值类型 [incrementable.traits]

¶1 如果 `WI` 建模 `weakly_incrementable`，`iter_difference_t<WI>` 就是它的差值类型。`incrementable_traits<T>` 按下列偏特化确定 `difference_type`：

1. 主模板：没有 `difference_type`；
2. `T*`，`T` 是对象类型：`ptrdiff_t`。函数指针和 `void*` 被排除；
3. `const I`：与 `I` 相同；
4. `T` 有嵌套的 `difference_type`：用它；
5. 没有嵌套 `difference_type`，但 `a - b` 是整数类型：`make_signed_t<decltype(a - b)>`。

第 5 条让 `int`、`unsigned` 这类本身就能递增的类型也有差值类型。`unsigned - unsigned` 是 `unsigned`，取有符号版本得到 `int`，所以 `iter_difference_t<unsigned>` 是 `int`。

¶2 `iter_difference_t<I>` 不是直接查 `incrementable_traits`。设 `RI` 为 `remove_cvref_t<I>`：

!!! std
    The type iter_difference_t<I> denotes incrementable_traits<RI>::difference_type if iterator_traits<RI> names a specialization generated from the primary template, and iterator_traits<RI>::difference_type otherwise.

    如果 `iterator_traits<RI>` 是由主模板生成的，就查 `incrementable_traits`；否则（用户特化过 `iterator_traits`）就用特化里的 `difference_type`。

原因是向后兼容。C++17 及以前，特化 `iterator_traits` 是为自定义迭代器提供关联类型的标准办法（[[std.iterator.tags]] 的例子就是这样做的）。新别名必须尊重这些特化，否则同一个迭代器会有两套互相矛盾的答案。反过来，主模板本身就是从 `incrementable_traits` 等推导出来的，不能再回头查它，否则会循环。

是否由主模板生成，程序没法直接查询，这只是标准的表述手段，实现通常在主模板里放一个标记成员。

!!! impl "libc++"
    libc++ 在 `iterator_traits` 主模板里定义 `using __primary_template = iterator_traits;`，再检查 `iterator_traits<I>::__primary_template` 是不是 `iterator_traits<I>` 自己。用户的特化没有这个成员，于是被识别出来。

¶3 用户可以为程序定义的类型特化 `incrementable_traits`。

## 值类型 [readable.traits]

¶1 如果 `R` 建模 `indirectly_readable`，`iter_value_t<R>` 就是它的值类型。规则比差值类型复杂，因为值类型有两种常见的成员名：迭代器习惯用 `value_type`，智能指针习惯用 `element_type`。

先定义一个仅用于说明的辅助类 *cond-value-type*`<T>`：只有 `T` 是对象类型时，它才提供 `value_type = remove_cv_t<T>`。然后 `indirectly_readable_traits<T>` 的规则是：

| `T` 的情况 | `value_type` |
|---|---|
| `U*` | *cond-value-type*`<U>`：`const int*` 得 `int`，`void*` 没有 |
| 数组类型 | `remove_cv_t<remove_extent_t<T>>`：`int[3]` 得 `int` |
| `const I` | 与 `I` 相同 |
| 只有 `value_type` 或只有 `element_type` | 用它（经 *cond-value-type*） |
| 两者都有，去掉 cv 后相同 | 用 `value_type` |
| 两者都有，去掉 cv 后不同 | 没有 `value_type` |

最后一行的意思是：两个成员说法矛盾时，宁可不给答案。

¶2 与差值类型完全平行：`iterator_traits<RI>` 由主模板生成时查 `indirectly_readable_traits`，否则用 `iterator_traits<RI>::value_type`。¶3 用户可以为程序定义的类型特化 `indirectly_readable_traits`。

¶4 注 1：一些老式输出迭代器声明 `value_type` 为 `void`。*cond-value-type*`<void>` 是空的，所以它们没有值类型，也不是 `indirectly_readable`。

¶5 注 2：`shared_ptr<int>` 是 `indirectly_readable`，值类型为 `int`；`shared_ptr<void>` 的 `element_type` 是 `void`，没有值类型，也不是 `indirectly_readable`。

### 为什么 `optional<int>` 不是 `indirectly_readable`

`optional<int>` 有 `value_type`，也有 `operator*`，却不是 `indirectly_readable`。原因在 [[iterator.concept.readable]]：这个概念要求对 `const In` 解引用得到的类型与 `iter_reference_t<In>` 完全相同。`optional` 是深 const 的，`*const_opt` 得 `const int&`，`*opt` 得 `int&`，两者不同。`shared_ptr` 是浅 const 的，`const shared_ptr<int>` 解引用仍得 `int&`，所以满足。这条要求把像指针的东西和像值的容器区分开了。

## `iterator_traits` [iterator.traits]

### 它提供什么（¶1）

¶1 `iterator_traits<I>` 有五个成员：`iterator_category`（类别标签）、`value_type`、`difference_type`、`pointer`、`reference`。对类类型的迭代器对象 `a`，`pointer` 和 `reference` 应分别是 `decltype(a.operator->())` 和 `decltype(*a)`；不支持 `operator->` 时 `pointer` 为 `void`。输出迭代器的 `value_type`、`difference_type`、`reference` 可以是 `void`。

### 主模板怎样推导（¶2–¶3）

C++20 的主模板会在类型没有声明成员时自己推导。为此要先判断 `I` 像不像一个 C++17 迭代器。¶2 定义了五个仅用于说明的概念，它们是 [[iterator.cpp17]] 命名要求的语法近似：

| 概念 | 在前一个的基础上增加 |
|---|---|
| *cpp17-iterator* | `*i`、`*i++` 可引用，`++i` 返回 `I&`，`copyable<I>` |
| *cpp17-input-iterator* | `equality_comparable`；`incrementable_traits` 给出 `signed_integral` 的差值类型；`indirectly_readable_traits` 给出值类型；两组 `common_reference` |
| *cpp17-forward-iterator* | 可默认构造；`iter_reference_t<I>` 是引用类型，去掉 cvref 后等于值类型；`i++`、`*i++` 的类型约束 |
| *cpp17-bidirectional-iterator* | `--i`、`i--`、`*i--` |
| *cpp17-random-access-iterator* | `totally_ordered`；`+=`、`-=`、`+`、`-`、`[]` 和 `i - i` |

两个细节决定了很多类型的归类：*cpp17-input-iterator* 要求差值类型是 `signed_integral`，整数类类型不算；*cpp17-forward-iterator* 要求 `*i` 返回真引用。

¶3 主模板生成的特化按下面的顺序确定成员：

1. （3.1）`I` 自己声明了 `difference_type`、`value_type`、`reference`、`iterator_category` 四个成员：照抄。`pointer` 有就照抄，没有就是 `void`。这是 C++98 风格迭代器的路径。
2. （3.2）否则，如果 `I` 满足 *cpp17-input-iterator*：
    - `value_type` 来自 `indirectly_readable_traits`，`difference_type` 来自 `incrementable_traits`；
    - `pointer`：有 `I::pointer` 就用它，否则 `operator->()` 合法就用它的返回类型，否则 `void`；
    - `reference`：有 `I::reference` 就用它，否则用 `iter_reference_t<I>`；
    - `iterator_category`：有 `I::iterator_category` 就用它，否则按满足的最强 *cpp17* 概念取随机访问、双向、前向或输入标签。
3. （3.3）否则，如果 `I` 满足 *cpp17-iterator*：当作输出迭代器。`iterator_category` 为 `output_iterator_tag`，`value_type`、`pointer`、`reference` 为 `void`；`difference_type` 能从 `incrementable_traits` 得到就用它，否则为 `void`。
4. （3.4）否则，`iterator_traits<I>` 没有上述任何成员。

第 4 条让 `iterator_traits` 可以安全地用在 SFINAE 里：`iterator_traits<int>::value_type` 只是替换失败，不是硬错误。（3.2）推导出的类别最高是 `random_access_iterator_tag`，不会是 `contiguous_iterator_tag`，因为 C++17 的命名要求里没有连续这一档。

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
// 没有 iterator_category：走 (3.2)，满足 cpp17-forward-iterator
static_assert(std::same_as<std::iterator_traits<It>::iterator_category,
                           std::forward_iterator_tag>);
static_assert(std::same_as<std::iterator_traits<It>::pointer, void>);
static_assert(std::forward_iterator<It>);

// iota 的迭代器：*it 返回 int 纯右值
using IotaIt = std::ranges::iterator_t<std::ranges::iota_view<int, int>>;
static_assert(std::same_as<std::iterator_traits<IotaIt>::iterator_category,
                           std::input_iterator_tag>);
static_assert(std::random_access_iterator<IotaIt>);

int main() {}
```

`iota_view` 迭代器的 `iterator_category` 其实是它自己声明的成员：当 `W` 建模 `incrementable` 且差值类型是整数类型时，[[range.iota.iterator]] 规定它为 `input_iterator_tag`。这和（3.2）推导的结果一致，因为 `*it` 不是引用，不满足 *cpp17-forward-iterator*。

### `iterator_concept`（¶4）

¶4 `iterator_traits` 的显式特化或偏特化可以有一个 `iterator_concept` 成员，表明类型对 C++20 迭代器概念的符合程度。例 1：要表示一个类型符合 `input_iterator` 概念但不满足 *Cpp17InputIterator*，可以让特化的 `iterator_concept` 为 `input_iterator_tag`，并且不声明 `iterator_category`。这些成员怎样被读取，见 [[iterator.concepts]] 中的 *ITER_TRAITS* 和 *ITER_CONCEPT*。

主模板从不生成 `iterator_concept`。对普通的类类型迭代器，*ITER_CONCEPT* 直接读 `I::iterator_concept`，不经过 `iterator_traits`。

### 指针的特化（¶5–¶6）

¶5 指针有专门的偏特化：

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

`requires is_object_v<T>` 排除了函数指针和 `void*`；`value_type` 去掉了 cv，所以 `const int*` 的值类型是 `int`；`iterator_category` 仍是随机访问，以兼容按标签分派的老代码，连续性只通过 `iterator_concept` 表达。

¶6 例 2 用 `iterator_traits<BI>::difference_type` 和 `value_type` 写了一个 `reverse`，这是 C++98 泛型代码的典型写法。今天会写 `iter_difference_t<BI>` 和 `iter_value_t<BI>`。

## 常见误解

!!! pitfall "特化了 `iterator_traits`，其余成员还会自动推导"
    一旦特化了 `iterator_traits<MyIt>`，¶2 就让 `iter_value_t<MyIt>`、`iter_difference_t<MyIt>` 改查这个特化，*ITER_CONCEPT* 也改查它（[[iterator.concepts]]）。特化里漏写 `iterator_concept`，C++20 概念就只能看到 `iterator_category`；漏写 `value_type`，`iter_value_t` 就不存在。C++20 之后，给类型自身加成员几乎总比特化 `iterator_traits` 好。

!!! pitfall "`iterator_traits<const I>` 等同于 `iterator_traits<I>`"
    `incrementable_traits` 和 `indirectly_readable_traits` 有 `const I` 偏特化，`iter_value_t` 等别名还会先做 `remove_cvref_t`，但 `iterator_traits` 没有这样的处理。自己声明了四个成员的迭代器，`const It` 照样能走（3.1）；靠推导的迭代器，`const It` 不能 `++`，不满足 *cpp17-iterator*，什么也推不出，`iterator_traits<const It>` 是空的；`int* const` 不匹配指针特化，也是空的。对去掉 cv 的类型使用 `iterator_traits`，或者直接用 `iter_*_t` 别名。

## 思考题

!!! question "思考题 1"
    一个类型同时有 `value_type = int` 和 `element_type = const int`，`iter_value_t` 是什么？如果 `element_type = long` 呢？

<details markdown="1">
<summary>答案</summary>

`value_type` 与 `remove_cv_t<element_type>` 相同，取 `int`。如果 `element_type = long`，两者不同，`indirectly_readable_traits` 没有 `value_type`，`iter_value_t` 不存在，类型也不是 `indirectly_readable`。
</details>

!!! question "思考题 2"
    `incrementable_traits` 的第 5 条为什么用 `make_signed_t`？`iter_difference_t<unsigned char>` 是什么？

<details markdown="1">
<summary>答案</summary>

差值类型必须有符号（[[iterator.concept.winc]]）。`unsigned char - unsigned char` 经整数提升得到 `int`，`make_signed_t<int>` 还是 `int`，所以答案是 `int`。
</details>

!!! question "思考题 3"
    写一个类型，不声明任何成员类型，使 `iterator_traits<X>::iterator_category` 为 `output_iterator_tag`。

<details markdown="1">
<summary>答案</summary>

满足 *cpp17-iterator* 而不满足 *cpp17-input-iterator* 的类型都可以，例如：

```cpp
struct Out { Out& operator*(); Out& operator++(); Out& operator++(int); };
```

它可复制，`*i`、`++i`、`*i++` 都合法，但没有 `operator==`，不满足 `equality_comparable`，于是走（3.3）。它的 `difference_type` 是 `void`，因为 `incrementable_traits<Out>` 给不出答案。
</details>
