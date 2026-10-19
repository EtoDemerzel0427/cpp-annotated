---
title: 范围适配器总论
summary: 范围适配器怎样被调用和组合：管道运算符 | 的精确含义、views::filter(pred) 这类部分应用、用 range_adaptor_closure 让自己的适配器加入管道；各视图共用的写法，以及 movable-box 与 non-propagating-cache 两个辅助组件。
status: done
covers: range.adaptors.general, range.adaptor.object, range.move.wrap, range.nonprop.cache, range.adaptor.helpers
since: c++20
papers: P0896R4, P2387R3, P2494R2, P2711R1
related: ranges, range.all, range.view, range.filter, range.transform, range.utility.conv, customization.point.object, func.require, concepts.object, optional
tags: 标准库, 范围, 适配器, 管道, range_adaptor_closure
updated: 2026-10-19
---

!!! tldr
    - 范围适配器把一个范围变成视图，可以用 `|` 串成管道，元素在遍历时才计算。
    - 闭包对象 `C` 满足 `R | C` 等价于 `C(R)`；两个闭包对象 `C | D` 组成新的闭包，调用它等于 `D(C(r))`。
    - `views::filter(pred)` 是部分应用：它把 `pred` 按值复制进一个闭包，等拿到范围时再调用 `views::filter(r, pred)`。
    - C++23 起，类 `T` 公开继承 `range_adaptor_closure<T>` 后，它的对象就能出现在 `|` 两边。
    - *movable-box* 让不可赋值的 lambda 也能存进视图；*non-propagating-cache* 是复制时不跟着复制的缓存。

## 管道和函数调用两种写法 [range.adaptors.general]

```cpp run ok
#include <ranges>
#include <vector>
#include <algorithm>
#include <cassert>
#include <cstdio>
int main() {
  std::vector<int> ints{0, 1, 2, 3, 4, 5};
  auto even = [](int i) { return i % 2 == 0; };
  auto square = [](int i) { return i * i; };
  for (int i : ints | std::views::filter(even) | std::views::transform(square))
    std::printf("%d ", i);                                   // 0 4 16
  std::puts("");
  assert(std::ranges::equal(ints | std::views::filter(even),
                            std::views::filter(ints, even)));
}
```

¶1 **范围适配器**（range adaptor，[[g:range-adaptor]]）把一个范围变换成具有特定行为的视图。适配器可以串联成管道，结果视图被遍历时才逐个计算元素，这叫惰性求值。¶2 它们声明在 `std::ranges::views` 中，`std::views` 是这个命名空间的别名。

¶3 按位或运算符 `|` 被重载，用来构造管道；每个适配器也都支持语义相同的函数调用写法。¶4 例 1 就是上面的代码：`ints | views::filter(even)` 和 `views::filter(ints, even)` 得到相同的结果。

## 闭包对象与 | [range.adaptor.object]

¶1 **范围适配器闭包对象**（range adaptor closure object，[[g:range-adaptor-closure-object]]）是接受一个范围实参的一元函数对象。`views::reverse`、`views::filter(even)` 都是闭包对象。对闭包对象 `C` 和范围表达式 `R`，下面两个表达式等价：

```cpp
C(R)
R | C
```

两个闭包对象也可以用 `|` 组合。`C | D` 产生一个新的闭包对象 `E`，它是一个完美转发调用包装器（[[func.require]]）：

- ¶1.1 它保存 `D` 的一份副本 `d`，类型为 `decay_t<decltype((D))>`；
- ¶1.2 它保存 `C` 的一份副本 `c`；
- ¶1.3 调用 `E(arg)` 等于 `d(c(arg))`。

!!! std
    the expression C | D produces another range adaptor closure object E. … Its call pattern is d(c(arg))

由此可以得到几个结论：

- `|` 是左结合的。`r | C | D` 是 `(r | C) | D`，先产生视图再适配；`C | D` 单独出现时产生一个还没有接上范围的管道，可以存进变量反复使用。两种写法结果相同。
- 闭包对象按值保存它的组成部分。`auto p = views::filter(pred) | views::transform(f);` 把 `pred` 和 `f` 都复制进 `p`。如果 `pred` 按引用捕获了局部变量，而 `p` 活得比那个变量久，就会悬垂。
- 完美转发调用包装器会把自身的值类别转发给 `c` 和 `d`：左值的 `E` 以左值调用它们，右值的 `E` 以右值调用。

### 适配器对象与部分应用（¶6–¶8）

¶6 **范围适配器对象**（range adaptor object，[[g:range-adaptor-object]]）是一个定制点对象（[[customization.point.object]]），第一个实参接受 `viewable_range`，返回一个视图。¶7 只接受一个实参的适配器对象本身就是闭包对象，如 `views::reverse`、`views::join`、`views::all`。

¶8 接受多个实参的适配器对象，如 `views::filter`、`views::take`，可以只给范围以外的实参。如果 `adaptor(range, args...)` 是良构的，那么 `adaptor(args...)` 产生一个闭包对象 `f`，也是完美转发调用包装器：

- ¶8.1 它保存 `adaptor` 的副本；
- ¶8.2 它把 `args...` 按值保存为 `bound_args`，类型是 `decay_t<decltype((args))>...`；
- ¶8.3 调用 `f(r)` 等于 `adaptor(r, bound_args...)`。

所以 `views::filter(pred)` 能单独写出来，它是 `filter` 的部分应用（partial application），作用类似 `std::bind_back(views::filter, pred)`。¶8 最后一句规定，`adaptor(args...)` 是否良构只取决于这些实参能否被保存，不检查之后能否用某个范围调用它，类型错误要到 `r | f` 时才出现。

```cpp run ok
#include <ranges>
#include <vector>
#include <cstdio>
int main() {
  std::vector<int> v{1, 2, 3};
  auto f = std::views::transform([](int x) { return x + 1; });   // 部分应用
  auto a = f(v);          // C(R)
  auto b = v | f;         // R | C，与上一行等价
  static_assert(std::same_as<decltype(a), decltype(b)>);
  auto ab = std::views::take(2) | f;     // C | D：调用时先 take 再 transform
  for (int x : v | ab) std::printf("%d ", x);    // 2 3
  std::puts("");
}
```

### 自定义闭包：range_adaptor_closure（¶2–¶5）{{c++23}}

C++20 中，用户写的函数对象无法加入管道，因为库实现 `|` 的方式没有公开。C++23 的 [[P2387R3]] 提供了一个 CRTP 基类：

```cpp
template<class D>
  requires is_class_v<D> && same_as<D, remove_cv_t<D>>
class range_adaptor_closure { };
```

¶2 如果 `T` 类型的对象 `t` 满足以下全部条件，实现保证 `t` 是一个范围适配器闭包对象，可以写成 `r | t`，也可以与其他闭包组合成 `t | other`：

- ¶2.1 `t` 是接受一个范围实参的一元函数对象；
- ¶2.2 `T` 派生自 `range_adaptor_closure<T>`；
- ¶2.3 `T` 没有其他 `range_adaptor_closure<U>` 基类；
- ¶2.4 `T` 本身不是范围。如果一个类型既是范围又是闭包，`a | b` 就无法判断谁作用于谁。

```cpp run ok
#include <ranges>
#include <vector>
#include <cstdio>
// 自定义闭包：取每个元素的平方
struct square_fn : std::ranges::range_adaptor_closure<square_fn> {
  template<std::ranges::viewable_range R>
  constexpr auto operator()(R&& r) const {
    return std::forward<R>(r)
         | std::views::transform([](auto x) { return x * x; });
  }
};
inline constexpr square_fn square;

int main() {
  std::vector<int> v{1, 2, 3, 4, 5};
  auto odd_squares = std::views::filter([](int x) { return x % 2; }) | square;
  for (int x : v | odd_squares) std::printf("%d ", x);                 // 1 9 25
  for (int x : square(v | std::views::take(2))) std::printf("%d ", x); // 1 4
  std::puts("");
}
```

¶3–¶5 规定了三种未定义行为：

- ¶3 `D` 可以是不完整类型，但 `cv D` 类型的表达式用作 `|` 的操作数时，`D` 必须完整并派生自 `range_adaptor_closure<D>`。如果重载决议为这样的表达式选中了程序自己定义的 `operator|`，行为未定义。所以不要再给自己的闭包类写 `operator|`。
- ¶4 如果 `U` 有基类 `range_adaptor_closure<T>` 而 `T` 不是 `U`，把 `U` 的对象用作 `|` 的操作数是{{ub}}。这对应 CRTP 实参写错的情形。
- ¶5 程序为 `range_adaptor_closure` 添加特化是{{ub}}。

带参数的自定义适配器可以仿照 ¶8，写完整调用和部分应用两个重载：

```cpp run ok
#include <ranges>
#include <vector>
#include <cstdio>
// every_nth(r, n) 与 r | every_nth(n) 都可以用
struct every_nth_closure
    : std::ranges::range_adaptor_closure<every_nth_closure> {
  std::ptrdiff_t n;
  constexpr explicit every_nth_closure(std::ptrdiff_t k) : n(k) {}
  template<std::ranges::viewable_range R>
  constexpr auto operator()(R&& r) const {
    return std::forward<R>(r) | std::views::stride(n);
  }
};
struct every_nth_fn {
  template<std::ranges::viewable_range R>
  constexpr auto operator()(R&& r, std::ptrdiff_t n) const {   // 完整调用
    return every_nth_closure(n)(std::forward<R>(r));
  }
  constexpr auto operator()(std::ptrdiff_t n) const {          // 部分应用
    return every_nth_closure(n);
  }
};
inline constexpr every_nth_fn every_nth;

int main() {
  std::vector<int> v{0, 1, 2, 3, 4, 5, 6};
  for (int x : v | every_nth(3)) std::printf("%d ", x);    // 0 3 6
  for (int x : every_nth(v, 2)) std::printf("%d ", x);     // 0 2 4 6
  auto pipe = std::views::reverse | every_nth(2);          // 标准闭包 | 自定义闭包
  for (int x : v | pipe) std::printf("%d ", x);            // 6 4 2 0
  std::puts("");
}
```

C++23 的 `std::bind_back` 也能做部分应用，但它的结果不派生自 `range_adaptor_closure`，不能直接放在 `|` 右边，需要再包一层。

!!! impl "libc++ 的实现"
    在 `__ranges/range_adaptor.h` 中，libc++ 用内部的 CRTP 基类 `__range_adaptor_closure<T>` 实现管道，公开的 `range_adaptor_closure` 只是从它派生的空类。`range | closure` 调用 `std::invoke(closure, range)`；`closure | closure` 返回 `__pipeable(__compose(c2, c1))`，也就是 ¶1.3 的 `d(c(arg))`。判断一个类型是否为闭包时，同样排除了 `ranges::range` 类型（¶2.4）。

## 各视图共用的写法

几乎所有适配器视图都按同一个模式定义，读懂一个，其余的就容易读了：

```cpp
template<input_range V, ...> requires view<V> && ...
class xxx_view : public view_interface<xxx_view<V, ...>> {
  V base_ = V();                         // 按值保存底层视图
  movable-box<F> fun_;                   // 如果有函数对象
  template<bool Const> class iterator;   // Const 为 true 时以 const V 为底层
  template<bool Const> class sentinel;
public:
  xxx_view() requires default_initializable<V> = default;
  constexpr explicit xxx_view(V base, ...);
  constexpr V base() const & requires copy_constructible<V>;
  constexpr V base() &&;
  constexpr auto begin() requires (!simple-view<V>);
  constexpr auto begin() const requires range<const V> && ...;
  // ...
};
template<class R, ...> xxx_view(R&&, ...) -> xxx_view<views::all_t<R>, ...>;
```

- 底层总是一个视图 `V`。推导指引用 `views::all_t<R>` 把任意 `viewable_range` 变成视图（[[range.all]]）。
- 构造函数是 `explicit` 的。多参数的构造函数是 [[P2711R1]] 统一改成 `explicit` 的。
- 迭代器写成 `template<bool Const>`，一份代码同时服务非 const 和 const 的遍历：`Const` 为真时底层是 *maybe-const*`<Const, V>`，即 `const V`。`iterator<false>` 可以隐式转换为 `iterator<true>`。
- `begin() requires (!simple-view<V>)` 和 `begin() const` 的搭配见 [[range.utility]]。

## movable-box [range.move.wrap]

视图必须可以移动赋值（[[range.view]]），而带捕获的 lambda 有复制和移动构造函数，赋值运算符却是删除的。`filter_view` 如果直接用一个 lambda 成员保存谓词，它就不能赋值，也就不是视图了。

¶1 仅用于说明的 *movable-box*`<T>`（[[g:movable-box]]）解决这个问题。它的行为与 `optional<T>` 完全相同，只有以下区别：

- ¶1.1 约束 `T` 可移动构造且是对象类型；
- ¶1.2 `T` 可以默认初始化时，默认构造函数构造一个值，而不是得到空状态；
- ¶1.3 `T` 不可复制赋值时，复制赋值改为：对方有值就 `emplace(*that)`，否则 `reset()`；
- ¶1.4 `T` 不可移动赋值时，移动赋值同样改用 `emplace`。

也就是说，它用析构旧值、再就地构造新值的方式模拟赋值。代价是多了一个空状态：如果就地构造抛出异常，盒子就空了。这也是 `filter_view::begin()` 有前置条件 `pred_.has_value()` 的原因（[[range.filter]]）。

¶2 建议实践：在用不到空状态时，例如 `T` 本身可以赋值，或者复制和移动构造不抛异常，*movable-box*`<T>` 应当只存一个 `T`，不加表示是否有值的标志，这样就没有额外开销。

!!! history "从 copyable-box 到 movable-box"
    C++20 中它叫 *copyable-box*，要求 `T` 可以复制构造。[[P2494R2]] 把它放宽为 *movable-box*，从此 `views::transform`、`views::filter` 等可以接受只能移动的函数对象，例如捕获了 `unique_ptr` 的 lambda。libc++ 的 `__ranges/movable_box.h` 的注释记录了这次改名。

## non-propagating-cache [range.nonprop.cache]

¶1 仅用于说明的 *non-propagating-cache*`<T>`（[[g:non-propagating-cache]]）也表现得像 `optional<T>`，区别在于它不传播自己的内容：

- ¶1.2 复制构造不复制任何东西，新对象为空；
- ¶1.3 移动构造得到空对象，并把源对象清空；
- ¶1.4–¶1.5 复制赋值和移动赋值都把自身清空，移动赋值还清空源对象；
- ¶1.6 额外的成员 *emplace-deref*`(i)` 先清空，再用 `*i` 直接初始化所含的值。`*i` 是纯右值时，由于复制消除，即使 `T` 不能移动也能构造。

¶2 注 2 说明，它使输入视图能在遍历时临时缓存值。

缓存只属于一个视图对象。复制视图得到一个没有缓存的新视图，第一次使用时重新计算。这样做有两个原因：缓存的内容可能指向原视图内部，比如 `join_view` 缓存的内层范围，复制过去就会悬垂；缓存的结果对新视图来说也可能已经不对了。

标准中用到它的地方有：`join_view` 和 `join_with_view`（缓存外层迭代器和纯右值的内层范围）、`lazy_split_view` 和输入版的 `chunk_view`（缓存当前迭代器）、`cache_latest_view`（缓存最近一个元素）。`filter_view` 等视图的 `begin()` 缓存在标准中只写成 Remarks 里的一句 caches the result，实现通常也用语义相同的类型。

<details class="fine" markdown="1"><summary>其余条文：辅助设施 [range.adaptor.helpers]</summary>

[range.adaptor.helpers] 定义了几个仅用于说明的工具：*tuple-transform* 对元组的每个元素调用函数，把结果组成新的 `tuple`；*tuple-for-each* 对每个元素调用函数；*as-lvalue* 把右值当作左值使用；*all-random-access*、*all-bidirectional*、*all-forward* 检查一组视图（按 *maybe-const*）是否都达到某个迭代器强度。它们主要服务于 `zip`、`zip_transform`、`cartesian_product`、`concat` 等多视图适配器。

</details>

## 惰性求值的代价

- 构造视图是 O(1) 的，只是把底层视图和函数对象存起来。
- 每一步 `++` 可能做不止常数的工作：`filter` 要跳过不满足谓词的元素，`join` 要跳过空的内层范围。整个遍历的总代价仍与底层元素个数成线性。
- 解引用可能重复计算：`transform` 的 `operator*` 每次都调用函数。`transform | filter` 会对通过过滤的元素调用两次函数，一次在 `filter` 判定，一次在读取时，见 [[range.transform]]。C++26 的 `views::cache_latest` 就是为这种情况设计的（[[range.cache.latest]]）。
- `begin()` 第一次可能是 O(n)，之后是 O(1)：`filter`、`drop_while`、`split`、`chunk_by` 等会缓存第一次的结果。

## 视图索引

| 类别 | 视图 |
|---|---|
| 包装 | [[range.all\|all、ref_view、owning_view]]、[[range.common\|common、counted]]、[[range.as.const\|as_const、as_rvalue]]、[[range.cache.latest\|cache_latest、as_input]] |
| 选择 | [[range.filter\|filter]]、[[range.take\|take、take_while]]、[[range.drop\|drop、drop_while]]、[[range.chunk\|stride]] |
| 变换 | [[range.transform\|transform]]、[[range.elements\|elements、keys、values]]、[[range.enumerate\|enumerate]] |
| 顺序 | [[range.reverse\|reverse]] |
| 展平与拼接 | [[range.join\|join、join_with]]、[[range.concat\|concat]] |
| 切分 | [[range.split\|split、lazy_split]]、[[range.chunk\|chunk、slide、chunk_by]] |
| 多序列 | [[range.zip\|zip、zip_transform、adjacent、adjacent_transform]]、[[range.cartesian\|cartesian_product]] |
