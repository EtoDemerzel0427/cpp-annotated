---
title: 迭代器概念
summary: C++20 的 14 个迭代器概念逐个精读——ITER_TRAITS / ITER_CONCEPT 如何读取类别；indirectly_readable 的四个 common_reference 与 const 要求；indirectly_writable 的 const_cast 怪招；weakly_incrementable 与整数类类型（integer-class type）的完整规格；incrementable；sentinel_for 的语义与"== 的定义域不是静态的"；sized_sentinel_for 与 disable_sized_sentinel_for；input → output → forward（多遍保证）→ bidirectional → random_access → contiguous 各自的语法与语义要求。
status: done
covers: *
since: c++20
papers: P0896R4
related: iterator.requirements, iterator.assoc.types, iterator.cust, iterator.cpp17, concepts, concepts.object, concepts.compare, std.iterator.tags, res.on.requirements, pointer.conversion
tags: 标准库, 迭代器, 概念, 哨位, 整数类类型
updated: 2026-10-18
---

[iterator.concepts] 是 C++20 迭代器模型的核心：用 [[concepts]] 的机制把"迭代器"拆成一组可组合的概念。读这一节要同时盯住两层：**语法要求**（概念定义，编译器检查）与**语义要求**（"`I` models ... only if"，编译器不检查，违反即 {{ifndr}}，见 [[res.on.requirements]]）。

概念之间的组合关系：

```text
indirectly_readable      weakly_incrementable ── incrementable
        │                        │
        │               input_or_output_iterator ─┬─ sentinel_for ── sized_sentinel_for
        │                        │                │
        └──────── input_iterator ┘          output_iterator  (+ indirectly_writable)
                       │
               forward_iterator      (+ incrementable, sentinel_for<I, I>)
                       │
            bidirectional_iterator   (+ --)
                       │
            random_access_iterator   (+ totally_ordered, sized_sentinel_for<I, I>, += + -= - [])
                       │
              contiguous_iterator    (+ 真左值引用, to_address)
```

## *`ITER_TRAITS`* 与 *`ITER_CONCEPT`*（[iterator.concepts.general]）

概念体系仍需迭代器**自我申报**类别——多遍保证、连续存储这类语义性质无法从语法推出。¶1 规定从哪里读这个申报：

- *`ITER_TRAITS(I)`*：若 `iterator_traits<I>` 由主模板生成，则为 `I` 本身；否则为 `iterator_traits<I>`（即用户/库的特化）。
- *`ITER_CONCEPT(I)`*：
    1. *`ITER_TRAITS(I)`*`::iterator_concept` 有效 → 用它；
    2. 否则 *`ITER_TRAITS(I)`*`::iterator_category` 有效 → 用它；
    3. 否则若 `iterator_traits<I>` 由主模板生成 → **`random_access_iterator_tag`**；
    4. 否则不表示类型。

注 1：*`ITER_TRAITS`* 使类别（`iterator_category`，给 C++17 接口看）和概念（`iterator_concept`，给 C++20 接口看）可以**分别**确定。

第 3 条乍看奇怪：什么都没申报，为什么给最高的 `random_access_iterator_tag`？因为 *`ITER_CONCEPT`* 只用来**封顶**——每个遍历概念都写成 `derived_from<ITER_CONCEPT(I), xxx_tag> && 其余语法要求`。没有申报时不额外封顶，类别完全由语法决定。也就是说，"不申报"等于"按语法能到哪一级就是哪一级"。

¶2 的例 1 把这一点演示得很清楚：

```cpp run title="iter_concept.cpp" ok
#include <iterator>

struct I {
    using value_type = int;
    using difference_type = int;
    int operator*() const;
    I& operator++();
    I operator++(int);
    I& operator--();
    I operator--(int);
    bool operator==(I) const;
};

// C++17 视角：iterator_traits 主模板按 (3.2) 推导；*i 是 int 纯右值，
// 不满足 cpp17-forward-iterator → input_iterator_tag
static_assert(std::same_as<std::iterator_traits<I>::iterator_category,
                           std::input_iterator_tag>);
// C++20 视角：I 自己没有 iterator_concept / iterator_category 成员，
// ITER_CONCEPT(I) = random_access_iterator_tag，不封顶；语法上能到双向
static_assert(std::bidirectional_iterator<I>);
static_assert(!std::random_access_iterator<I>);   // 缺 += 等

int main() {}
```

注意 *`ITER_TRAITS(I)`* 是 `I` 本身而**不是**主模板生成的 `iterator_traits<I>`——否则就会读到推导出的 `input_iterator_tag`，把 C++17 的保守判断带进 C++20。

## `indirectly_readable`（[iterator.concept.readable]）

¶1：可通过 `operator*` 间接读取的类型——指针、智能指针、迭代器——建模此概念。

```cpp
template<class In>
concept indirectly-readable-impl =
  requires(const In in) {
    typename iter_value_t<In>;
    typename iter_reference_t<In>;
    typename iter_rvalue_reference_t<In>;
    { *in } -> same_as<iter_reference_t<In>>;
    { ranges::iter_move(in) } -> same_as<iter_rvalue_reference_t<In>>;
  } &&
  common_reference_with<iter_reference_t<In>&&, iter_value_t<In>&> &&
  common_reference_with<iter_reference_t<In>&&, iter_rvalue_reference_t<In>&&> &&
  common_reference_with<iter_rvalue_reference_t<In>&&, const iter_value_t<In>&>;

template<class In>
concept indirectly_readable = indirectly-readable-impl<remove_cvref_t<In>>;
```

逐项拆开：

- **三个关联类型都得存在**：值类型、引用类型、右值引用类型。
- **`*in` 对 const 对象的结果必须与对非 const 左值的结果同类型**。`iter_reference_t<In>` 用的是 `In&`，而这里 `in` 是 `const In`——所以"深 const"的类型（`optional<int>`：`*const_opt` 是 `const int&`）被排除，"浅 const"的类型（指针、`shared_ptr`、迭代器）通过。解引用的结果不应随迭代器对象自身的 const 而变。
- **三组公共引用**：引用与值、引用与右值引用、右值引用与 const 值之间都要能"统一"。泛型算法需要一个能同时绑定 `*it` 和 `iter_value_t` 临时对象的类型（例如在 `unique` 中比较"已存的值"与"当前元素"），公共引用就是这个类型。代理迭代器正是通过满足这几条才融入体系（[[iterator.cust]]）。
- 外层先 `remove_cvref_t`：`indirectly_readable<const int* const&>` 与 `indirectly_readable<const int*>` 等价。

¶2 唯一的语义要求：对 `I` 的值 `i`，`*i` **保持相等性**（[[concepts]]）——相等的迭代器解引用得到相等的结果，且多次解引用结果稳定。

## `indirectly_writable`（[iterator.concept.writable]）

```cpp
template<class Out, class T>
concept indirectly_writable =
  requires(Out&& o, T&& t) {
    *o = std::forward<T>(t);
    *std::forward<Out>(o) = std::forward<T>(t);
    const_cast<const iter_reference_t<Out>&&>(*o) = std::forward<T>(t);
    const_cast<const iter_reference_t<Out>&&>(*std::forward<Out>(o)) = std::forward<T>(t);
  };   // 四个表达式都"不要求保持相等性"
```

¶2 语义：若 `Out` 同时可读且值类型就是 `decay_t<T>`，那么赋值后 `*o` 等于赋值前 `E` 的值——写进去的就是读出来的。¶3：赋值之后 `o` 不再要求可解引用（输出迭代器"写一次就作废"）。¶4：若 `E` 是亡值，被移走的对象处于有效但未指明状态（[[g:valid-but-unspecified-state]]）。¶5（注 1）：`operator*` 唯一有效的用途是出现在赋值左侧，且通过同一个值只赋值一次。

¶6（注 2）解释那两行 `const_cast` 怪招：

!!! note "为什么要 `const_cast<const iter_reference_t<Out>&&>`"
    目的是**拒绝**"`operator*` 按值返回非代理对象"的迭代器。若 `*o` 返回 `std::string` 纯右值，`*o = "x"` 能编译（对临时 `string` 赋值），却把值写进了一个立即销毁的临时对象——写操作静默丢失。加上 const 之后：
    
    - 真引用 `T&`：`const_cast<T& const&&>` 即 `T&`，照常可赋值；
    - 代理对象：代理通常提供 `const` 限定的赋值运算符（"通过 const 代理写入所指元素"），可通过；
    - 按值返回的 `std::string`：变成 `const std::string&&`，赋值不可行——被拒绝。
    
    所以 `operator*` 返回 `std::string` 的迭代器不建模 `indirectly_writable<I, std::string>`。这也解释了为什么 C++23 的 `views::zip` 等的代理引用类型（`tuple<T&...>`）获得了 const 限定的赋值运算符。

## `weakly_incrementable` 与整数类类型（[iterator.concept.winc]）

```cpp
template<class I>
concept weakly_incrementable =
  movable<I> &&
  requires(I i) {
    typename iter_difference_t<I>;
    requires is-signed-integer-like<iter_difference_t<I>>;
    { ++i } -> same_as<I&>;   // 不要求保持相等性
    i++;                      // 不要求保持相等性
  };
```

¶1：递增**不要求**保持相等性，类型也**不要求**可比较。只要求 `movable`（不要求可复制！），差值类型是有符号类整数类型，前置 `++` 返回自身引用，后置 `++` 可以返回任何东西（包括 `void`）。

### 整数类类型（¶2–¶13）

差值类型必须"像有符号整数"，但标准不想把它限死在内建整数上：`iota_view<long long>` 的两个迭代器之差可能超出 `long long`，需要更宽的类型。¶2 由此引入**整数类类型**（[[g:integer-class-type]]）：由实现定义的一组"行为如同整数"的类型，注 1 指出它**不一定是类类型**。

规格要点：

| 段 | 内容 |
|---|---|
| ¶3 | 值域是连续区间：有符号为 −2<sup>N−1</sup>…2<sup>N−1</sup>−1，无符号为 0…2<sup>N</sup>−1；`N` 称为宽度，且**大于**同符号的任何整数类型的宽度 |
| ¶4 | **类整数**（[[g:integer-like-type]]）= 建模 `integral` 的非 `bool` 类型，或整数类类型；再细分有符号/无符号类整数 |
| ¶5 | 每个整数类类型 `I` 对应一个假想的扩展整数类型 `B(I)`（同符号、同宽度）；规格通过 `B(I)` 描述运算 |
| ¶6 | 转换：整数类 → 任何类整数可**显式**转换；→ 同符号且不更窄的整数类可**隐式**转换；整数 → 整数类双向（隐式、显式）可转换；转换不抛异常，结果按模 2<sup>N</sup> 同余 |
| ¶7 | 运算：`a++`、`++a`、`&a`、一元运算、复合赋值、二元运算都与 `B(I)` 上的对应运算同值同效果，结果类型按规则映射回 `I` |
| ¶8 | 可按 `bool(E != I(0))` 语境转换为 `bool` |
| ¶9 | 建模 `regular` 与 `three_way_comparable<strong_ordering>` |
| ¶10 | 值初始化得 0 |
| ¶11 | `numeric_limits<I>` 被特化，成员值与 `numeric_limits<B(I)>` 一致 |
| ¶12 | 两个类整数（至少一个是整数类）的 `common_type_t` 是不窄于两者的整数类类型；两者都有符号则结果也有符号 |
| ¶13 | *`is-integer-like`*、*`is-signed-integer-like`* 就是对上述分类的判定 |

!!! impl "实现的选择"
    libc++ 不提供类类型的整数类类型：在支持 `__int128` 的平台上，`iota_view<long long, long long>` 的差值类型直接是 `__int128`（libc++ 把它当作整数类型对待）。MSVC STL 则提供了类类型实现。可移植代码不应假设差值类型是内建整数——用 `iter_difference_t<I>` 并只做标准保证的运算。

```cpp run title="integer_like.cpp" ok
#include <ranges>

using D = std::ranges::range_difference_t<std::ranges::iota_view<long long, long long>>;
static_assert(!std::same_as<D, long long>);     // 比 long long 更宽
static_assert(sizeof(D) > sizeof(long long));

int main() {}
```

（第一个断言对任何实现都成立：差值类型要能表示 `long long` 全值域上任意两点之差，必须比 `long long` 更宽——要么是整数类类型（¶3 要求它比所有同符号整数类型更宽），要么是实现提供的更宽扩展整数类型。第二个断言在主流实现上成立，但严格说 `sizeof` 并不由宽度直接决定。）

### 语义要求（¶14–¶15）

¶14：若 `i` 在前置与后置 `++` 的定义域内，称 `i` **可递增**。`I` 建模 `weakly_incrementable` 仅当：`++i` 与 `i++` 定义域相同；可递增时两者都使 `i` 前进到下一个元素；可递增时 `addressof(++i) == addressof(i)`。

¶15 推荐实践：作用于 `weakly_incrementable` 类型的算法应是**单遍**的；注 3：`a == b` 不蕴含 `++a == ++b`——这正是 `istream_iterator` 的处境。

## `incrementable`（[iterator.concept.inc]）

```cpp
template<class I>
concept incrementable = regular<I> && weakly_incrementable<I> &&
  requires(I i) { { i++ } -> same_as<I>; };
```

¶1：在 `weakly_incrementable` 之上要求 `regular`（可复制、可默认构造、可比较），后置 `++` 返回 `I`，且递增**必须保持相等性**（注 1：覆盖了 `weakly_incrementable` 中"不要求保持相等性"的注释）。¶2 语义：若 `a == b`，则 `a++ == b`，且 `((void)a++, a) == ++b`。¶3（注 2）：正是"`a == b` 蕴含 `++a == ++b`"允许多遍单向算法。整数类型本身就建模 `incrementable`。

## `input_or_output_iterator`（[iterator.concept.iterator]）

```cpp
template<class I>
concept input_or_output_iterator =
  requires(I i) { { *i } -> can-reference; } && weakly_incrementable<I>;
```

¶1：整个分类体系的根，"迭代器"的泛称就指它。¶2（注 1）：与 *Cpp17Iterator* 不同，它**不要求可复制**——仅移动的迭代器（如包装一个协程句柄或独占资源的输入迭代器）在 C++20 中是合法的。

## `sentinel_for`（[iterator.concept.sentinel]）

```cpp
template<class S, class I>
concept sentinel_for =
  semiregular<S> && !is-integer-like<S> &&
  input_or_output_iterator<I> && weakly-equality-comparable-with<S, I>;
```

- 哨位必须 `semiregular`（可复制、可默认构造）——它要能被存进视图、被复制到多个算法调用中；
- **不能是类整数类型**：防止 `ranges::advance(it, 5)` 与 `ranges::advance(it, bound)` 的重载歧义，以及 `views::counted` 式的"计数"被误当作哨位；
- 只要求 `I` 与 `S` 之间能 `==`/`!=`（[[concepts.compare]] 中的 *`weakly-equality-comparable-with`*），不要求 `S` 自己可比较。

¶2 语义要求（`[i, s)` 表示范围时）：

1. `i == s` 有定义；
2. 若 `i != s`，则 `i` 可解引用，且 `[++i, s)` 表示范围；
3. `assignable_from<I&, S>` 要么建模，要么不满足——**禁止"能赋值但语义不对"**，因为 `ranges::advance(i, bound)` 在可赋值时直接 `i = bound`（[[iterator.primitives]]）；
4. 若 `I` 与 `S` 是同一类型，`i == i` 为真。

¶3 一句容易被忽视的话：

!!! std
    The domain of == is not static.

    `==` 的定义域不是静态的。

对输入迭代器，`i` 与 `s` 表示范围且 `i != s` 时，**递增另一个等于 `i` 的迭代器**之后，`i` 与 `s` 不再保证仍表示范围，`i == s` 也就不再保证有定义。直观地说：两个 `istream_iterator` 副本共享同一个流，推进其中一个，另一个就"过期"了。

## `sized_sentinel_for`（[iterator.concept.sizedsentinel]）

```cpp
template<class S, class I>
concept sized_sentinel_for =
  sentinel_for<S, I> &&
  !disable_sized_sentinel_for<remove_cv_t<S>, remove_cv_t<I>> &&
  requires(const I& i, const S& s) {
    { s - i } -> same_as<iter_difference_t<I>>;
    { i - s } -> same_as<iter_difference_t<I>>;
  };
```

¶1：允许用 `-` **在常数时间内**算出迭代器与哨位之间的距离。¶2 语义：设 `N` 为使 `i == s` 所需的最少 `++i` 次数，`N` 可表示时 `s - i == N`，`-N` 可表示时 `i - s == -N`。

`disable_sized_sentinel_for` 是一个默认为 `false` 的变量模板。¶3：按 [[namespace.std]]，用户可对程序定义类型（`S` 和/或 `I` 是程序定义类型，均为去 cv 的非数组对象类型）特化它，特化必须可用于常量表达式、类型为 `const bool`。¶4（注 1）说明用途：对那些**满足**但不**建模**的类型（比如 `-` 是线性时间，或语义不是距离），提供一个退出开关——否则库会信任 `-` 并据此优化。

标准库自己就用了这个开关：`reverse_iterator<I1>` 与 `reverse_iterator<I2>`、`move_iterator<I1>` 与 `move_iterator<I2>` 的组合，在底层迭代器不建模 `sized_sentinel_for` 时被 disable（[[iterator.synopsis]]），因为它们的 `operator-` 是无约束的、会无条件存在。

¶5 例 1：随机访问迭代器对、`counted_iterator` 与 `default_sentinel` 建模此概念。

## 六个类别概念

### `input_iterator`（[iterator.concept.input]）

```cpp
template<class I>
concept input_iterator =
  input_or_output_iterator<I> && indirectly_readable<I> &&
  requires { typename ITER_CONCEPT(I); } &&
  derived_from<ITER_CONCEPT(I), input_iterator_tag>;
```

注 1：与 *Cpp17InputIterator* 不同，不要求 `==`——迭代器通常与哨位比较。也不要求可复制、不要求后置 `++` 返回值。

### `output_iterator`（[iterator.concept.output]）

```cpp
template<class I, class T>
concept output_iterator =
  input_or_output_iterator<I> && indirectly_writable<I, T> &&
  requires(I i, T&& t) { *i++ = std::forward<T>(t); };
```

注 1：不要求 `equality_comparable`。¶2 语义：`*i++ = E;` 的效果等价于 `*i = E; ++i;`。¶3 推荐实践：单遍。注意它**不看** *`ITER_CONCEPT`*——输出能力纯由语法决定；它也是唯一带"值类型"参数的类别概念，因为可写类型是一个集合。

### `forward_iterator`（[iterator.concept.forward]）

```cpp
template<class I>
concept forward_iterator =
  input_iterator<I> && derived_from<ITER_CONCEPT(I), forward_iterator_tag> &&
  incrementable<I> && sentinel_for<I, I>;
```

¶1：增加可复制性、相等比较、**多遍保证**。语义要求：

- ¶2：`==` 的定义域是**同一底层序列**上的迭代器；但**值初始化**的同类型迭代器可以比较，且彼此相等（注 1：如同指向同一个空序列的末尾）。
- ¶3：从前向迭代器取得的指针和引用，在 `[i, s)` 仍表示范围期间保持有效——禁止"把元素存在迭代器体内"（对比 [[iterator.requirements.general#15]]）。
- ¶4 **多遍保证**（[[g:multi-pass-guarantee]]）：对两个可解引用的 `a`、`b`，`a == b` 蕴含 `++a == ++b`；并且 `((void)[](X x){++x;}(a), *a)` 等价于 `*a`——递增 `a` 的副本不影响 `a` 本身。

¶5（注 2）：多遍保证加上"可变迭代器可以多次赋值"（解除输出迭代器的一次性限制），使多遍单向算法（如 `search`、`adjacent_find`）可用。

### `bidirectional_iterator`（[iterator.concept.bidir]）

在前向之上要求 `--i` 返回 `I&`、`i--` 返回 `I`。¶2：`r` **可递减**当且仅当存在 `q` 使 `++q == r`；可递减的 `r` 在 `--r`、`r--` 的定义域内（所以 `begin()` 不可递减）。¶3 语义：对相等的 `a`、`b`，可递减时 `addressof(--a) == addressof(a)`、`a-- == b`、`a--` 与 `--b` 之后仍相等、`++(--a) == b`；可递增时 `--(++a) == b`。

### `random_access_iterator`（[iterator.concept.random.access]）

```cpp
template<class I>
concept random_access_iterator =
  bidirectional_iterator<I> && derived_from<ITER_CONCEPT(I), random_access_iterator_tag> &&
  totally_ordered<I> && sized_sentinel_for<I, I> &&
  requires(I i, const I j, const iter_difference_t<I> n) {
    { i += n } -> same_as<I&>;
    { j +  n } -> same_as<I>;
    { n +  j } -> same_as<I>;
    { i -= n } -> same_as<I&>;
    { j -  n } -> same_as<I>;
    {  j[n]  } -> same_as<iter_reference_t<I>>;
  };
```

¶1：常数时间的 `+= + -= -`，常数时间的距离计算（`sized_sentinel_for<I, I>`），以及下标。注意 `j[n]` 必须**恰好**返回 `iter_reference_t<I>`（*Cpp17RandomAccessIterator* 只要求"可转换为 `reference`"）。¶2 用 12 条语义要求把 `+=` 等运算钉死为"走 `n` 步"：`(a += n) == b`、`a + n == (a += n)`、结合律 `a + (x + y) == (a + x) + y`、`a + 0 == a`、`(b -= n) == a`、`a[n] == *b`、`a <= b` 等。

### `contiguous_iterator`（[iterator.concept.contiguous]）

```cpp
template<class I>
concept contiguous_iterator =
  random_access_iterator<I> && derived_from<ITER_CONCEPT(I), contiguous_iterator_tag> &&
  is_lvalue_reference_v<iter_reference_t<I>> &&
  same_as<iter_value_t<I>, remove_cvref_t<iter_reference_t<I>>> &&
  requires(const I& i) {
    { to_address(i) } -> same_as<add_pointer_t<iter_reference_t<I>>>;
  };
```

- 引用必须是**真左值引用**，且去 cvref 后就是值类型——代理迭代器永远不是连续的；
- 必须能用 `std::to_address`（[[pointer.conversion]]）取得指针：对类类型迭代器，`to_address` 优先调用 `pointer_traits<I>::to_address`，否则调用 `i.operator->()`。

¶2 语义（`a`、`b` 可解引用，`c` 不可解引用，`b` 从 `a` 可达、`c` 从 `b` 可达，`D` 为差值类型）：

1. `to_address(a) == addressof(*a)`；
2. `to_address(b) == to_address(a) + D(b - a)`；
3. `to_address(c) == to_address(a) + D(c - a)`——过尾迭代器也能转成指针，且恰好是"末元素之后"的指针（[[expr.add]]）；
4. `to_address(I{})` 有定义——值初始化的迭代器也能转换（通常得空指针）；
5. `ranges::iter_move(a)` 与 `std::move(*a)` 类型、值类别、效果都相同；
6. 若 `ranges::iter_swap(a, b)` 良构，其效果等价于 `ranges::swap(*a, *b)`。

第 5、6 条是 [[iterator.requirements.general#13]] 授权的前提：库要能随时把迭代器换成指针而不改变程序含义，就不能允许用户通过定制 `iter_move`/`iter_swap` 偷偷改变行为。

## 标准库类型在概念体系中的位置

```cpp run title="where.cpp" ok
#include <deque>
#include <forward_list>
#include <iterator>
#include <list>
#include <ranges>
#include <string>
#include <vector>

static_assert(std::contiguous_iterator<std::vector<int>::iterator>);
static_assert(std::contiguous_iterator<std::string::const_iterator>);
static_assert(std::random_access_iterator<std::deque<int>::iterator>
           && !std::contiguous_iterator<std::deque<int>::iterator>);
static_assert(std::bidirectional_iterator<std::list<int>::iterator>);
static_assert(std::forward_iterator<std::forward_list<int>::iterator>);
static_assert(std::input_iterator<std::istream_iterator<int>>
           && !std::forward_iterator<std::istream_iterator<int>>);
static_assert(std::output_iterator<std::ostream_iterator<int>, int>
           && !std::input_iterator<std::ostream_iterator<int>>);
// 代理迭代器：随机访问，但不是连续的
static_assert(std::random_access_iterator<std::vector<bool>::iterator>
           && !std::contiguous_iterator<std::vector<bool>::iterator>);

// 仅可移动的输入迭代器：C++20 合法，C++17 不合法
struct MoveOnly {
    using value_type = int;
    using difference_type = std::ptrdiff_t;
    MoveOnly(MoveOnly&&) = default;
    MoveOnly& operator=(MoveOnly&&) = default;
    int operator*() const;
    MoveOnly& operator++();
    void operator++(int);
};
static_assert(std::input_iterator<MoveOnly> && !std::copyable<MoveOnly>);

// 按值返回 string：可以"赋值"，但不是 indirectly_writable
struct ByValue {
    using difference_type = std::ptrdiff_t;
    std::string operator*() const;
    ByValue& operator++();
    ByValue operator++(int);
};
static_assert(!std::indirectly_writable<ByValue, std::string>);

int main() {}
```

## 常见误区

!!! pitfall "满足 `forward_iterator` 不等于是前向迭代器"
    多遍保证、"引用不得指向迭代器自身"、`==` 的定义域都是语义要求。一个把元素缓存在自身的生成器式迭代器，只要声明了 `iterator_concept = forward_iterator_tag`，语法上就能满足；但它只是满足而不建模，交给依赖多遍或依赖引用稳定性的算法/适配器就是 {{ifndr}}（[[res.on.requirements]]）。不确定时，申报 `input_iterator_tag`。

!!! pitfall "忘记 `iterator_concept`，类别被 `iterator_category` 封顶"
    *`ITER_CONCEPT`* 在没有 `iterator_concept` 时会读 `iterator_category`。一个随机访问的代理迭代器若只写了 `iterator_category = input_iterator_tag`（为了诚实地告诉 C++17 接口"我不满足 *Cpp17ForwardIterator*"），在 C++20 中也会被封顶为 `input_iterator`。正确做法是两个都写：`iterator_category = input_iterator_tag`、`iterator_concept = random_access_iterator_tag`——这正是 `iota_view`、`views::transform` 等的迭代器的做法。

!!! pitfall "后置 `++` 的返回类型"
    `weakly_incrementable` 对 `i++` 没有类型要求，`incrementable` 要求它返回 `I`。输入迭代器常让 `operator++(int)` 返回 `void`（C++20 标准库的 `move_iterator`、`basic_const_iterator` 对输入迭代器正是如此），所以泛型代码对非前向迭代器不应使用 `i++` 的结果。

## 思考题

!!! question "思考题"
    1. `int` 是 `weakly_incrementable` 吗？是 `input_or_output_iterator` 吗？`unreachable_sentinel_t` 为什么能与 `int` 比较？
    2. `sentinel_for` 的语义要求 (2.3) "`assignable_from<I&, S>` 要么建模、要么不满足"，具体防止了什么？
    3. 为什么 `contiguous_iterator` 要单独要求 `same_as<iter_value_t<I>, remove_cvref_t<iter_reference_t<I>>>`？举一个违反它但其余条件都满足的例子会出什么问题？

<details markdown="1">
<summary>展开查看答案与解析</summary>

1. `int` 建模 `weakly_incrementable`（甚至 `incrementable`）：`movable`、差值类型经 `incrementable_traits` 第 5 条为 `int`、`++i` 返回 `int&`。但 `*i` 不合法，所以不是 `input_or_output_iterator`。`unreachable_sentinel_t` 的 `operator==` 约束的是 `weakly_incrementable`（[[unreachable.sentinel]]），所以能与 `int` 比较——这让 `views::iota(0)` 的"无界"成为可能。不过 `sentinel_for<unreachable_sentinel_t, int>` 为假，因为 `int` 不是迭代器。
2. `ranges::advance(i, bound)` 在 `assignable_from<I&, S>` 时直接执行 `i = std::move(bound)`（[[range.iter.op.advance]]）。若一个哨位能赋值给迭代器、但赋值的结果并不是"走到终点"（例如赋值只复制了部分状态），这个优化就会给出错误的结果。(2.3) 把这种类型排除在建模之外。
3. 库会把 `[i, s)` 替换成 `[to_address(i), ...)` 的指针范围，并以 `iter_value_t<I>` 为元素类型做 `memmove` 之类的优化。若引用类型是 `const Derived&` 而值类型是 `Base`，指针算术就会以错误的元素大小步进；要求两者一致保证了"指针类型就是元素类型的指针"。
</details>

## 小结

!!! summary
    - *`ITER_CONCEPT`*：`iterator_concept` → `iterator_category` → 未申报时 `random_access_iterator_tag`（即不封顶）；读的是类型自身（或用户特化），不是推导出的 traits。
    - `indirectly_readable`：const/非 const 解引用同类型、三组公共引用、`*i` 保持相等性。
    - `indirectly_writable`：`const_cast` 拒绝"写进按值返回的临时对象"。
    - `weakly_incrementable`：可移动、有符号类整数差值类型；整数类类型有完整的"像整数"规格。
    - `sentinel_for`：`semiregular`、非类整数、可与迭代器比较；`==` 的定义域不是静态的。`sized_sentinel_for` 可用 `disable_sized_sentinel_for` 退出。
    - 遍历概念逐级加：可读+申报 → 多遍+可比较 → `--` → 常数时间算术与全序 → 真引用+`to_address`。
