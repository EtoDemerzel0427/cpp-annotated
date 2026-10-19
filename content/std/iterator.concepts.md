---
title: 迭代器概念
summary: C++20 用十几个概念描述迭代器：能否读、能否写、能否递增、与哨位的关系，以及从输入到连续的六个遍历级别。
status: done
covers: *
since: c++20
papers: P0896R4
related: iterator.requirements, iterator.assoc.types, iterator.cust, iterator.cpp17, concepts, concepts.object, concepts.compare, std.iterator.tags, res.on.requirements, pointer.conversion
tags: 标准库, 迭代器, 概念, 哨位, 整数类类型
updated: 2026-10-19
---

!!! tldr
    - 一个迭代器属于哪一级，由语法（有没有 `--`、`+=`、`[]`）和它申报的标签共同决定；标签只封顶，不申报时完全按语法判定。
    - `indirectly_readable` 要求对 const 迭代器解引用得到同样的类型，所以 `std::optional<int>` 不算可读；`indirectly_writable` 用两行 `const_cast` 拒绝写进按值返回的临时对象。
    - C++20 的迭代器不必可复制，也不必能互相比较；终点用**哨位**（sentinel）表示，哨位的类型可以和迭代器不同。
    - 前向迭代器的关键是多遍保证：`a == b` 蕴含 `++a == ++b`，复制一份去递增不影响原件。这是语义要求，编译器不检查。
    - 连续迭代器要求解引用得到真正的左值引用，并且能用 `std::to_address` 换成指针，所以代理迭代器永远不是连续的。

C++17 用一张张需求表描述迭代器（[[iterator.cpp17]]），C++20 把它们改写成可以组合的概念（[[concepts]]）。每个概念都有两层要求。**语法要求**写在概念定义里，编译器会检查。**语义要求**写成 "`I` models ... only if ..."，编译器不检查；一个类型通过了语法检查却不满足语义要求，叫做满足（satisfy）而不建模（model），把它交给标准库就是 {{ifndr}}（[[res.on.requirements]]）。

各个概念之间的关系如下，下层包含上层的全部要求：

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
            random_access_iterator   (+ <, sized_sentinel_for<I, I>, += + -= - [])
                       │
              contiguous_iterator    (+ 真左值引用, to_address)
```

## 迭代器属于哪一级 [iterator.concepts.general]

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

// C++17 视角：*i 是 int 纯右值，不符合前向迭代器的要求
static_assert(std::same_as<std::iterator_traits<I>::iterator_category,
                           std::input_iterator_tag>);
// C++20 视角：I 没有申报类别，按语法能到双向
static_assert(std::bidirectional_iterator<I>);
static_assert(!std::random_access_iterator<I>);   // 缺 += 等

int main() {}
```

同一个类型，C++17 的 `iterator_traits` 说它是输入迭代器，C++20 的概念说它是双向迭代器。两套体系对多遍、连续存储这类无法从语法推出的性质，都要依靠迭代器自己申报，区别在于去哪里读这个申报。

¶1 标准用两个仅供说明的名字描述读取过程。如果 `iterator_traits<I>` 是由主模板生成的，*`ITER_TRAITS(I)`* 就是 `I` 本身；如果有人特化了 `iterator_traits<I>`，它就是那个特化。*`ITER_CONCEPT(I)`* 按顺序取：

1. *`ITER_TRAITS(I)`*`::iterator_concept`，如果存在；
2. 否则 *`ITER_TRAITS(I)`*`::iterator_category`，如果存在；
3. 否则，如果 `iterator_traits<I>` 由主模板生成，取 `random_access_iterator_tag`；
4. 否则不表示任何类型。

每个遍历概念都写成 `derived_from<ITER_CONCEPT(I), 某个_tag> && 其余语法要求`，所以标签的作用只是封顶。第 3 条在什么都没申报时给出最高的标签，等于不封顶，类别完全由语法决定。

¶2 例子中的 `I` 走的正是第 3 条。注意 *`ITER_TRAITS(I)`* 是 `I` 本身，而不是主模板推导出的 `iterator_traits<I>`；否则会读到推导出的 `input_iterator_tag`，把 C++17 的保守判断带进 C++20。注 1 把这称为类别（给 C++17 接口用的 `iterator_category`）和概念（给 C++20 接口用的 `iterator_concept`）可以分别确定。

## 读和写

### `indirectly_readable` [iterator.concept.readable]

¶1 能用 `operator*` 读出值的类型建模这个概念，包括指针、智能指针和迭代器：

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

逐项来看：

- 值类型、引用类型、右值引用类型三个关联类型都必须存在（[[iterator.assoc.types]]）。
- `iter_reference_t<In>` 是对非 const 左值 `In&` 解引用的类型，而这里的 `in` 是 `const In`。两者必须相同，意思是解引用的结果不随迭代器对象本身是否 const 而变。指针、`shared_ptr`、迭代器都满足；`std::optional<int>` 对 const 对象解引用得到 `const int&`，所以不是 `indirectly_readable`。
- 三组公共引用要求引用、值、右值引用之间能找到一个共同的类型。泛型算法有时要把 `*it` 和一个 `iter_value_t` 临时对象放在一起处理（例如 `unique_copy` 比较保存下来的值和当前元素），公共引用就是两者都能绑定的类型。代理迭代器靠满足这几条融入体系（[[iterator.cust]]）。
- 外层先做 `remove_cvref_t`，所以 `indirectly_readable<const int* const&>` 与 `indirectly_readable<const int*>` 是一回事。

¶2 唯一的语义要求是 `*i` 保持相等性（[[concepts.equality]]）：相等的迭代器解引用得到相等的结果，同一个迭代器反复解引用结果不变。

### `indirectly_writable` [iterator.concept.writable]

```cpp
template<class Out, class T>
concept indirectly_writable =
  requires(Out&& o, T&& t) {
    *o = std::forward<T>(t);
    *std::forward<Out>(o) = std::forward<T>(t);
    const_cast<const iter_reference_t<Out>&&>(*o) = std::forward<T>(t);
    const_cast<const iter_reference_t<Out>&&>(*std::forward<Out>(o)) = std::forward<T>(t);
  };   // 四个表达式都不要求保持相等性
```

前两行很直接。后两行的 `const_cast` 是为了拒绝一种迭代器：`operator*` 按值返回一个普通对象，比如 `std::string`。这时 `*o = "x"` 能编译，因为可以给临时的 `string` 赋值，但写进去的值随临时对象一起销毁，写操作悄无声息地丢了。

¶6 注 2 解释了这个技巧。把解引用结果转成 const 右值之后：

- 真引用 `T&` 经过引用折叠仍是 `T&`，照常可以赋值；
- 代理对象通常提供 const 限定的赋值运算符，意思是通过 const 代理写入它所指的元素，也能通过；
- 按值返回的 `std::string` 变成 `const std::string&&`，不能赋值，于是被拒绝。

```cpp run ok
#include <iterator>
#include <string>

struct ByValue {
    using difference_type = std::ptrdiff_t;
    std::string operator*() const;
    ByValue& operator++();
    ByValue operator++(int);
};

void f(ByValue b) { *b = "x"; }   // 能编译，但值写进了临时对象
static_assert(!std::indirectly_writable<ByValue, std::string>);

int main() {}
```

C++23 给 `std::tuple`、`std::pair` 加上 const 限定的赋值运算符，就是为了让 `views::zip` 返回的 `tuple<T&...>` 这种代理引用通过这一检查（[[P2321R2]]）。

¶2 语义要求：如果 `Out` 同时可读，且值类型就是 `decay_t<T>`，那么赋值之后 `*o` 等于赋值前那个值，写进去的就是读出来的。¶3 赋值之后 `o` 不再要求可以解引用。¶4 如果赋值的源是亡值，源对象处于有效但未指明的状态（[[g:valid-but-unspecified-state]]）。¶5 注 1 总结说，`*o` 唯一有效的用法是出现在赋值左边，并且通过同一个值只写一次。这些是为输出流这类写一次就作废的迭代器准备的。

## 递增

### `weakly_incrementable` [iterator.concept.winc]

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

¶1 要求很少：类型可移动（不要求可复制，也不要求可比较），差值类型像有符号整数，前置 `++` 返回自身的引用，后置 `++` 可以返回任何东西，包括 `void`。`int` 本身就满足它。

¶14 语义要求：如果 `i` 在前置和后置 `++` 的定义域内，就说 `i` **可递增**（incrementable）。`++i` 和 `i++` 的定义域必须相同；`i` 可递增时，两者都让 `i` 前进到下一个元素，并且 `addressof(++i) == addressof(i)`。

¶15 推荐实践：作用于这类类型的算法应当是单遍的，同一个值不要经过两次。注 3 指出原因：`a == b` 并不蕴含 `++a == ++b`。两个 `istream_iterator` 指向同一个流时，推进其中一个，另一个看到的内容也变了。

### 整数类类型（¶2–¶13）

差值类型为什么不直接要求是有符号整数？因为 `iota_view<long long, long long>` 的两个迭代器之差可能超出 `long long` 的范围，需要更宽的类型。

¶2 **整数类类型**（[[g:integer-class-type]]）是实现定义的一组表现得像整数的类型。注 1 指出它不一定是类类型。¶3 它的宽度大于同符号的任何整数类型。¶4 **类整数类型**（[[g:integer-like-type]]）指 `bool` 以外建模 `integral` 的类型，或者整数类类型；它们又分为有符号和无符号两种。

```cpp run title="integer_like.cpp" ok
#include <ranges>

using D = std::ranges::range_difference_t<
    std::ranges::iota_view<long long, long long>>;
static_assert(!std::same_as<D, long long>);   // 必须比 long long 更宽

int main() {}
```

这个断言在任何实现上都成立。本机 libc++ 中 `D` 就是 `__int128`，一个它当作整数类型处理的扩展类型；MSVC STL 则提供了一个类类型。可移植代码应当写 `iter_difference_t<I>`，只使用下面列出的运算。

<details class="fine" markdown="1"><summary>整数类类型的完整规格</summary>

| 段 | 内容 |
|---|---|
| ¶3 | 值域是连续区间：有符号为 −2<sup>N−1</sup> 到 2<sup>N−1</sup>−1，无符号为 0 到 2<sup>N</sup>−1；`N` 称为宽度 |
| ¶5 | 每个整数类类型 `I` 对应一个假想的扩展整数类型 `B(I)`，符号与宽度相同；后面的运算都借 `B(I)` 来描述 |
| ¶6 | 可以显式转换为任何类整数类型，可以隐式转换为同符号、宽度不小于自己的整数类类型；整数类型可以隐式、显式转换为整数类类型；转换不抛异常，结果按模 2<sup>N</sup> 取同余值 |
| ¶7 | `a++`、`++a`、`&a`、一元运算、复合赋值、二元运算都与 `B(I)` 上的对应运算同值、同效果；结果类型为 `B(I)` 时映射回 `I` |
| ¶8 | 可以按 `bool(E != I(0))` 按语境转换为 `bool` |
| ¶9 | 建模 `regular` 和 `three_way_comparable<strong_ordering>` |
| ¶10 | 值初始化得到 0 |
| ¶11 | `numeric_limits<I>` 有特化，各成员与 `numeric_limits<B(I)>` 一致 |
| ¶12 | 两个类整数类型中至少有一个是整数类类型时，`common_type_t` 是宽度不小于两者的整数类类型；两者都有符号时结果也有符号 |
| ¶13 | *`is-integer-like`*、*`is-signed-integer-like`* 判断的就是 ¶4 的分类 |

</details>

### `incrementable` [iterator.concept.inc]

```cpp
template<class I>
concept incrementable = regular<I> && weakly_incrementable<I> &&
  requires(I i) { { i++ } -> same_as<I>; };
```

¶1 在 `weakly_incrementable` 之上，要求类型是 `regular`（可复制、可默认构造、可比较相等），后置 `++` 返回 `I`，并且递增必须保持相等性。注 1 说明这一条覆盖了 `weakly_incrementable` 定义中不要求保持相等性的注释。

¶2 语义要求：如果 `a == b`，那么 `a++ == b`，并且 `((void)a++, a) == ++b`。¶3 注 2 指出，正是 `a == b` 蕴含 `++a == ++b` 这一点，让多遍的单向算法成为可能。

## 迭代器与哨位

### `input_or_output_iterator` [iterator.concept.iterator]

```cpp
template<class I>
concept input_or_output_iterator =
  requires(I i) { { *i } -> can-reference; } && weakly_incrementable<I>;
```

¶1 这是整个体系的根，每个迭代器都建模它：能解引用（结果不是 `void`），能递增。¶2 注 1 强调，它和 C++17 的 *Cpp17Iterator* 不同，不要求可复制。包装一个独占资源的仅移动输入迭代器在 C++20 中是合法的迭代器。

### `sentinel_for` [iterator.concept.sentinel]

```cpp
template<class S, class I>
concept sentinel_for =
  semiregular<S> && !is-integer-like<S> &&
  input_or_output_iterator<I> && weakly-equality-comparable-with<S, I>;
```

¶1 哨位是表示范围终点的值。它和迭代器能用 `==`、`!=` 比较（[[concepts.equalitycomparable]]），自身必须可复制、可默认构造，这样才能存进视图、传给多个算法。`std::unreachable_sentinel_t`、`std::default_sentinel_t` 都是常见的哨位类型。

哨位不能是类整数类型。整数在范围库里有另一个含义，表示步数，例如 `ranges::advance(it, 5)`；如果整数也能当哨位，这类调用就有歧义。

¶2 设 `[i, s)` 表示一个范围，`S` 和 `I` 建模 `sentinel_for` 的语义要求是：

1. `i == s` 有定义；
2. 如果 `i != s`，那么 `i` 可以解引用，并且 `[++i, s)` 也表示范围；
3. `assignable_from<I&, S>` 要么建模，要么根本不满足；
4. 如果 `I` 和 `S` 是同一类型，`i == i` 为真。

第 3 条防的是能赋值但语义不对的哨位。`ranges::advance(i, bound)` 在可以赋值时直接执行 `i = bound`（[[range.iter.op.advance]]），这只有在赋值的结果确实是走到终点时才正确。

¶3 还有一句容易被忽略的话：

!!! std
    The domain of == is not static.

意思是：`[i, s)` 表示范围且 `i != s` 时，只要递增另一个与 `i` 相等的迭代器，`i` 和 `s` 就不再保证表示范围，`i == s` 也不再保证有定义。这又是 `istream_iterator` 的情形：两个副本共享一个流，推进一个，另一个就过期了。

### `sized_sentinel_for` [iterator.concept.sizedsentinel]

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

¶1 这个概念表示可以用 `-` 在常数时间内算出迭代器到哨位的距离。¶2 设 `N` 是让 `i == s` 所需的最少 `++i` 次数，那么 `N` 可以表示时 `s - i == N`，`-N` 可以表示时 `i - s == -N`。¶5 例 1 指出，一对随机访问迭代器、`counted_iterator` 与 `default_sentinel_t` 都建模它。

常数时间是语义要求，库会信任它并据此优化，比如用 `s - i` 直接得到范围的大小。如果某个类型有 `-` 运算，但它是线性时间的，或者含义根本不是距离，就需要一个退出开关：

¶3–¶4 `disable_sized_sentinel_for<S, I>` 是一个默认为 `false` 的变量模板。`S` 或 `I` 是程序定义类型时，用户可以把它特化为 `true`，特化必须能用于常量表达式，类型为 `const bool`。注 1 说明它就是给满足而不建模的类型用的。

标准库自己也用了这个开关。`reverse_iterator` 和 `move_iterator` 的 `operator-` 对任何底层迭代器都声明，所以 [[iterator.synopsis]] 在底层迭代器不建模 `sized_sentinel_for` 时把对应组合 disable 掉。

## 六个遍历级别

### `input_iterator` [iterator.concept.input]

```cpp
template<class I>
concept input_iterator =
  input_or_output_iterator<I> && indirectly_readable<I> &&
  requires { typename ITER_CONCEPT(I); } &&
  derived_from<ITER_CONCEPT(I), input_iterator_tag>;
```

¶1 可以读，可以递增。注 1 说明它不要求 `==`，因为迭代器通常和哨位比较，而不是和另一个迭代器比较。它也不要求可复制，不要求后置 `++` 有返回值。

### `output_iterator` [iterator.concept.output]

```cpp
template<class I, class T>
concept output_iterator =
  input_or_output_iterator<I> && indirectly_writable<I, T> &&
  requires(I i, T&& t) { *i++ = std::forward<T>(t); };
```

¶1 可以写，可以递增，注 1 指出不要求可比较相等。¶2 语义要求 `*i++ = E;` 等价于 `*i = E; ++i;`。¶3 推荐实践是单遍。

它和其他五个级别有两点不同：不看 *`ITER_CONCEPT`*，能否输出纯由语法决定；而且带一个值类型参数 `T`，因为一个迭代器可以写入的类型是一个集合。

### `forward_iterator` [iterator.concept.forward]

```cpp
template<class I>
concept forward_iterator =
  input_iterator<I> && derived_from<ITER_CONCEPT(I), forward_iterator_tag> &&
  incrementable<I> && sentinel_for<I, I>;
```

¶1 在输入迭代器之上增加可复制、可比较相等和多遍保证。语义要求有三条：

- ¶2 `==` 的定义域是指向同一序列的迭代器。例外是值初始化的同类型迭代器，它们可以互相比较，并且相等；注 1 说它们就像指向同一个空序列的末尾。
- ¶3 从前向迭代器取得的指针和引用，在 `[i, s)` 仍表示范围期间保持有效。所以元素不能存放在迭代器对象里面，对照 [[iterator.requirements.general#15]]。
- ¶4 **多遍保证**（[[g:multi-pass-guarantee]]）：对两个可以解引用的 `a`、`b`，`a == b` 蕴含 `++a == ++b`；并且 `((void)[](X x){++x;}(a), *a)` 等价于 `*a`，即递增 `a` 的一个副本不影响 `a`。

¶5 注 2 说明，多遍保证加上可以通过可变迭代器多次赋值（输出迭代器没有这个自由），使 `search`、`adjacent_find` 这类需要回头看的单向算法成为可能。

### `bidirectional_iterator` [iterator.concept.bidir]

```cpp
template<class I>
concept bidirectional_iterator =
  forward_iterator<I> && derived_from<ITER_CONCEPT(I), bidirectional_iterator_tag> &&
  requires(I i) {
    { --i } -> same_as<I&>;
    { i-- } -> same_as<I>;
  };
```

¶2 如果存在某个 `q` 使 `++q == r`，就说 `r` **可递减**；可递减的 `r` 必须在 `--r` 和 `r--` 的定义域内。指向首元素的迭代器不可递减。

¶3 语义要求让 `--` 成为 `++` 的逆运算。对相等的 `a`、`b`，可递减时有 `addressof(--a) == addressof(a)`、`a-- == b`、各自递减后仍相等、`++(--a) == b`；可递增时有 `--(++a) == b`。

### `random_access_iterator` [iterator.concept.random.access]

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

¶1 增加常数时间的 `+=`、`+`、`-=`、`-`，常数时间的距离计算，以及下标。`j[n]` 必须恰好返回 `iter_reference_t<I>`；C++17 的 *Cpp17RandomAccessIterator* 只要求它能转换为 `reference`。

¶2 十二条语义要求规定这些运算的含义就是走 `n` 步：设 `b` 是从 `a` 递增 `n` 次得到的，那么 `(a += n) == b`，`a + n` 等于 `a += n`，`(b -= n) == a`，`a + D(0) == a`，`a + D(x + y)` 等于 `(a + x) + y`，`b` 可解引用时 `a[n] == *b`，`a <= b`，等等。

### `contiguous_iterator` [iterator.concept.contiguous]

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

¶1 元素在内存中连续存放。语法上，解引用必须得到真正的左值引用，去掉 cv 和引用后就是值类型，所以代理迭代器不可能是连续的。还必须能用 `std::to_address` 得到指针（[[pointer.conversion]]）：对类类型迭代器，它优先调用 `pointer_traits<I>::to_address`，否则调用 `i.operator->()`。

¶2 设 `a`、`b` 可以解引用，`c` 不可以，`b` 从 `a` 可达，`c` 从 `b` 可达，`D` 是差值类型。语义要求是：

1. `to_address(a) == addressof(*a)`；
2. `to_address(b) == to_address(a) + D(b - a)`；
3. `to_address(c) == to_address(a) + D(c - a)`，即尾后迭代器也能换成指针，并且恰好指向末元素之后；
4. `to_address(I{})` 有定义；
5. `ranges::iter_move(a)` 与 `std::move(*a)` 的类型、值类别和效果都相同；
6. 如果 `ranges::iter_swap(a, b)` 良构，它的效果等价于 `ranges::swap(*a, *b)`。

后两条是 [[iterator.requirements.general#13]] 的前提。那里允许库把连续迭代器随时换成指针来处理；如果用户能通过定制 `iter_move`、`iter_swap` 改变行为，这种替换就会改变程序的含义。

## 标准库类型在哪一级

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

int main() {}
```

## 常见误解

!!! pitfall "满足 `forward_iterator` 就是前向迭代器"
    多遍保证、引用不得指向迭代器自身、`==` 的定义域，都是语义要求。一个把当前元素缓存在自己体内的生成器式迭代器，只要申报了 `forward_iterator_tag`，语法检查就能通过；但它只是满足而不建模，交给依赖多遍或引用稳定性的算法就是 {{ifndr}}。拿不准时，申报 `input_iterator_tag`。

!!! pitfall "只写了 `iterator_category`，C++20 的类别被压低了"
    没有 `iterator_concept` 时，*`ITER_CONCEPT`* 会读 `iterator_category`。一个随机访问的代理迭代器为了如实告诉 C++17 接口自己不符合 *Cpp17ForwardIterator*，写了 `iterator_category = input_iterator_tag`，在 C++20 中也会被压到 `input_iterator`。应当两个都写：`iterator_category = input_iterator_tag`，`iterator_concept = random_access_iterator_tag`。`iota_view` 和 `views::transform` 的迭代器就是这样做的。

!!! pitfall "使用输入迭代器的 `i++` 的结果"
    `weakly_incrementable` 对 `i++` 的类型没有要求，只有 `incrementable` 要求它返回 `I`。输入迭代器的 `operator++(int)` 常常返回 `void`，标准库的 `move_iterator` 和 `basic_const_iterator` 在底层不是前向迭代器时就是这样。泛型代码对非前向迭代器应当只写 `++i`。

## 思考题

!!! question "思考题 1"
    `int` 是 `weakly_incrementable` 吗？是 `input_or_output_iterator` 吗？`std::unreachable_sentinel_t` 为什么能和 `int` 比较？

<details markdown="1">
<summary>答案</summary>

`int` 可移动，差值类型是 `int`（[[incrementable.traits]]），`++i` 返回 `int&`，所以建模 `weakly_incrementable`，甚至建模 `incrementable`。但 `*i` 不合法，所以它不是 `input_or_output_iterator`。

`unreachable_sentinel_t` 的 `operator==` 只约束另一边是 `weakly_incrementable`（[[unreachable.sentinel]]），所以能和 `int` 比较，这让 `views::iota(0)` 可以没有终点。不过 `sentinel_for<unreachable_sentinel_t, int>` 为假，因为 `int` 不是迭代器。
</details>

!!! question "思考题 2"
    `std::shared_ptr<int>` 是 `indirectly_readable`，`std::optional<int>` 不是。两者都有 `operator*`，区别在哪里？

<details markdown="1">
<summary>答案</summary>

概念要求 `*in`（`in` 是 const 对象）的类型与 `iter_reference_t<In>`（对非 const 左值解引用的类型）相同。`shared_ptr` 是浅 const，对 const 的 `shared_ptr<int>` 解引用仍得到 `int&`；`optional` 是深 const，对 const 的 `optional<int>` 解引用得到 `const int&`，与 `int&` 不同。`optional` 是一个装着值的容器，不是指向别处的句柄，这个区别正是概念想要刻画的。
</details>
