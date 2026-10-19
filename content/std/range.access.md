---
title: 范围访问
summary: ranges::begin、end、cbegin、rbegin、size、ssize、reserve_hint、empty、data、cdata 这组定制点对象怎样选择实现：数组、成员、仅经实参依赖查找的非成员，以及对结果类型和右值的检查。
status: done
covers: *
since: c++20
papers: P0896R4, P2602R2, P2278R4
related: ranges, range.req, range.range, customization.point.object, conventions, basic.lookup.argdep, iterator.concepts, iterator.range, stmt.ranged, conv.rval, expr.type.conv
tags: 标准库, 范围, CPO, ADL, 定制点
updated: 2026-10-19
---

!!! tldr
    - `ranges::begin(E)` 依次尝试：数组、成员 `begin()`、只经实参依赖查找找到的 `begin()`；每一步都要求结果是迭代器，否则跳到下一步。
    - 对右值的非借用范围，`begin`、`end`、`cbegin`、`rbegin`、`data` 都拒绝调用，因为得到的迭代器或指针会悬垂；`size`、`ssize`、`empty` 不拒绝。
    - `std::ranges::range` 就是用 `ranges::begin` 和 `ranges::end` 定义的，所以一个类型算不算范围，完全由这一节的规则决定。
    - C++23 起 `ranges::cbegin` 保证返回常量迭代器；本机 libc++ 还没有实现这一点。
    - 不满足条件时只是替换失败，不会硬报错，可以放心用在概念和 `requires` 里。

## std::begin 的三个问题

`std::begin(c)`（[[iterator.range]]）是一个普通的函数模板：

- 用户类型如果只提供非成员 `begin`，必须写两步 `using std::begin; begin(c);` 才能找到它；
- 它不检查返回值，`begin()` 返回 `int` 也照单全收；
- 它接受右值容器，`std::begin(std::vector<int>{})` 返回一个立刻悬垂的迭代器。

[range.access] 用一组**定制点对象**（[[g:customization-point-object]]）解决这三点。定制点对象是一个函数对象，它的调用运算符按固定顺序查找实现，并检查结果类型（[[customization.point.object]]）。

```cpp run ok
#include <ranges>
#include <vector>
namespace lib {
  struct Bag { int data[3]{1, 2, 3}; };
  // 非成员 begin/end：只能经实参依赖查找找到
  inline int* begin(Bag& b) { return b.data; }
  inline int* end(Bag& b) { return b.data + 3; }
}
using std::ranges::range;
template<class R>
concept can_begin = requires(R&& r) {
  std::ranges::begin(std::forward<R>(r));
};

static_assert(range<lib::Bag>);           // ¶2.5：找到 lib::begin
static_assert(!range<const lib::Bag>);    // const Bag& 绑不到 Bag&
static_assert(!can_begin<lib::Bag>);      // ¶2.1：右值，非借用
static_assert(can_begin<std::vector<int>&>);
static_assert(!can_begin<std::vector<int>>);
static_assert(can_begin<std::ranges::subrange<int*>>);  // 借用范围的右值

int main() {
  lib::Bag b;
  int s = 0;
  for (int x : b) s += x;   // 范围 for 也会用实参依赖查找
  return s == 6 ? 0 : 1;
}
```

## 共同的前提 [range.access.general]

¶1 这些定制点对象在 `<ranges>` 和 `<iterator>` 中都可用。

¶2 下文反复用到子表达式 `E` 的**物化对象**（reified object，[[g:reified-object]]）：`E` 是 glvalue 时，就是 `E` 所指的对象；`E` 是纯右值时，是对它做临时量实质化转换（[[conv.rval]]）得到的临时对象。

每个定制点对象都说"令 `t` 为指代 `E` 的物化对象的左值"。也就是说，不管传进来的是左值还是右值，后面一律对左值 `t` 调用 `t.begin()` 或 `begin(t)`。`E` 是不是右值，只在第一步决定要不要拒绝。

## ranges::begin [range.access.begin]

¶2 给定类型为 `T` 的子表达式 `E`，按顺序判断：

| 项 | 条件 | `ranges::begin(E)` |
|---|---|---|
| 2.1 | `E` 是右值，且 `enable_borrowed_range<remove_cv_t<T>>` 为 `false` | {{ill-formed}} |
| 2.2 | `T` 是数组，元素类型不完整 | {{ifndr}} |
| 2.3 | `T` 是数组 | `t + 0` |
| 2.4 | `auto(t.begin())` 有效，类型建模 `input_or_output_iterator` | `auto(t.begin())` |
| 2.5 | `T` 是类或枚举，只经实参依赖查找得到的 `auto(begin(t))` 有效，类型建模 `input_or_output_iterator` | 该表达式 |
| 2.6 | 其他 | {{ill-formed}} |

2.1 拒绝右值，是因为得到的迭代器会随临时对象一起失效。**借用范围**（borrowed range）是例外：它的迭代器指向别处的存储，不依赖范围对象本身存活，例如 `string_view`、`span`、`subrange`（[[range.range#4]]）。类型通过把变量模板 `enable_borrowed_range` 特化为 `true` 来声明这一点。

2.3 写成 `t + 0` 而不是 `t`，是为了得到一个指针纯右值，而不是数组左值。

`auto(x)` 是 C++23 的退化复制写法（[[expr.type.conv]]）：结果总是按值复制出来，`begin()` 返回引用也会退化成值。

2.4 和 2.5 都检查结果类型。成员 `begin()` 存在但返回的不是迭代器时，2.4 不选它，转而尝试 2.5；都不行就非良构。所以碰巧有一个叫 `begin` 的成员的类型，不会被误判为范围：

```cpp run ok
#include <ranges>
// begin() 返回 int 而不是迭代器：被定制点对象拒绝
struct Weird { int begin() { return 0; } int end() { return 0; } };
static_assert(!std::ranges::range<Weird>);
int main() {}
```

2.5 只用实参依赖查找（[[basic.lookup.argdep]]），普通的非限定查找不参与。否则会找到 `std::begin` 自己，把一个没有约束的模板拉进来。

¶3 注 1 说明，上面这些可诊断的非良构情形出现在模板实例化的立即语境中时，表现为替换失败。这正是 [[customization.point.object]] 的要求：不满足条件时，没有可以参与重载决议的调用运算符。¶4 注 2：只要 `ranges::begin(E)` 有效，它的类型就建模 `input_or_output_iterator`。

!!! history "毒丸"
    C++20 最初的措辞是：非成员 `begin(t)` 的重载决议在一个声明了若干被删除的 `begin` 函数模板的语境中进行。这些被删除的声明俗称毒丸（poison pill），作用是让非限定查找停在这里，找不到 `std::begin`。但毒丸本身也是重载决议的候选，有时比用户提供的合法定制匹配得更好，反而把它挡掉了。[[P2602R2]] 以缺陷报告的形式改成了今天的如同只进行实参依赖查找。

!!! impl "libc++ 怎样实现只用实参依赖查找"
    libc++ 在定制点对象所在的内部命名空间里声明 `void begin() = delete;`，一个零参数的被删除函数。非限定查找在这里停下，不会继续向外找到 `std::begin`；它不接受任何实参，永远不是可行函数，于是效果等于只有实参依赖查找找到的候选。函数对象的最后还有一个 `void operator()(auto&&) const = delete;` 兜底。

## ranges::end [range.access.end]

¶2 结构与 `begin` 相同，有三处差别：

- 2.3 未知边界的数组（`int[]`）非良构，因为不知道终点在哪；
- 2.4 已知边界的数组给出 `t + extent_v<T>`；
- 2.5、2.6 成员 `end()` 或非成员 `end(t)` 的结果必须建模 `sentinel_for<iterator_t<T>>`，也就是用 `begin` 的结果类型来检验 `end`。

¶4 注 2：只要两者都有效，`end` 的类型 `S` 与 `begin` 的类型 `I` 就建模 `sentinel_for<S, I>`。

## cbegin 与 cend [range.access.cbegin]

¶1 C++23 起（[[P2278R4]]）它们保证返回常量迭代器（通过它不能修改元素，见 [[const.iterators]]）：

- 1.1 右值的非借用范围，非良构；
- 1.2 令 `U` 为 `ranges::begin(possibly-const-range(t))`，结果是 `const_iterator<decltype(U)>(U)`。

*`possibly-const-range(r)`* 在 `const R` 是输入范围时返回 `const R&`，否则仍返回 `R&`（[[ranges.syn]]）。对 `vector<int>`，加 const 就得到 `const_iterator`，`const_iterator<>` 不再包装。对 `filter_view` 这种没有 const `begin()` 的视图，只能用非 const 的迭代器，再由 `const_iterator<>` 套一层 `basic_const_iterator`，解引用得到 `const int&`。

这修好了 C++20 的老问题。C++20 的 `ranges::cbegin(s)` 只是对 `const span<int>` 调用 `begin`，而 `span` 的 const 不传递到元素，结果仍然可写。

[range.access.cend] ¶1 `cend` 对称地使用 `ranges::end` 和 `const_sentinel`。

```cpp run
#include <ranges>
#include <span>
#include <type_traits>
#include <vector>
int main() {
  std::vector<int> v{1, 2, 3};
  std::span<int> s = v;
  auto it = std::ranges::cbegin(s);
  static_assert(std::is_same_v<decltype(*it), const int&>);
  auto ev = v | std::views::filter([](int x) { return x > 1; });
  auto ci = std::ranges::cbegin(ev);   // 没有 const begin() 也行
  static_assert(std::is_same_v<decltype(*ci), const int&>);
  return *ci == 2 ? 0 : 1;
}
```

按标准这段代码应当编译通过。本机 libc++ 还没有实现 [[P2278R4]]，仍按 C++20 的做法只对 const 对象调用 `begin`：`ranges::cbegin(s)` 返回可写的迭代器，第一条 `static_assert` 失败；`filter_view` 没有 const `begin()`，`ranges::cbegin(ev)` 直接报错。所以这里没有标判定。

## rbegin、rend、crbegin、crend

[range.access.rbegin] ¶2 先试成员 `rbegin()`，再试只经实参依赖查找的 `rbegin(t)`，两者都要求结果是迭代器。2.5 是最后的兜底：如果 `ranges::begin(t)` 和 `ranges::end(t)` 类型相同，并且建模 `bidirectional_iterator`，结果就是 `make_reverse_iterator(ranges::end(t))`。

兜底要求首尾同类型，因为 `reverse_iterator` 需要从一个迭代器出发向前走，而哨位一般既不是迭代器，也不能递减。首尾类型不同的范围要先经过 `views::common`。

[range.access.rend] 对称地使用 `make_reverse_iterator(ranges::begin(t))`，并要求结果是 `rbegin` 结果的哨位。[range.access.crbegin]、[range.access.crend] 与 `cbegin`、`cend` 同理，在 *`possibly-const-range(t)`* 上调用 `rbegin`、`rend`，再包一层 `const_iterator` 或 `const_sentinel`。

## ranges::size [range.prim.size]

¶2 的顺序是：

1. 未知边界的数组：非良构；
2. 数组：`auto(extent_v<T>)`；
3. `disable_sized_range<remove_cv_t<T>>` 为 `false`，且 `auto(t.size())` 是整数类类型（行为像整数的类型，包括内建整数，[[iterator.concept.winc]]）：用成员；
4. `T` 是类或枚举，没有被禁用，只经实参依赖查找的 `auto(size(t))` 是整数类类型：用它；
5. `I`、`S` 分别是 `begin`、`end` 的类型，建模 `sized_sentinel_for<S, I>` 和 `forward_iterator<I>`：`to-unsigned-like(end - begin)`；
6. 其他：非良构。

与 `begin` 不同，`size` 没有右值拒绝。长度是一个值，调用结束后不依赖容器存活，所以 `ranges::size(std::vector<int>(3))` 是合法的。

`disable_sized_range`（[[range.sized#3]]）用来关掉第 3、4 步：某个类型有 `size()` 成员，但它不是常数时间，或者含义不对时，把它特化为 `true`。

第 5 步要求前向迭代器。对单遍的输入迭代器，求 `end - begin` 这件事本身可能就让 `begin` 失效了。

结果不一定是无符号的：成员 `size()` 返回 `int`，`ranges::size` 就返回 `int`。只有第 5 步会强制转成无符号。

## ranges::ssize [range.prim.ssize]

¶2 `ranges::size(t)` 非良构时 `ssize` 也非良构。否则令 `D` 为 *`make-signed-like-t<decltype(ranges::size(t))>`*，如果 `ptrdiff_t` 更宽就用 `ptrdiff_t`，结果是 `static_cast<D>(ranges::size(t))`。有了它，`for (auto i = 0; i < ranges::ssize(v); ++i)` 不再有有符号与无符号比较的警告。

```cpp run ok
#include <cstddef>
#include <ranges>
#include <vector>
struct S { int* begin(); int* end(); int size() const { return 3; } };
// 成员 size() 返回 int：ranges::size 原样返回 int
static_assert(std::same_as<
    decltype(std::ranges::size(std::declval<S&>())), int>);
// ssize：make-signed-like-t<int> 是 int，ptrdiff_t 更宽，取 ptrdiff_t
static_assert(std::same_as<
    decltype(std::ranges::ssize(std::declval<S&>())), std::ptrdiff_t>);
// size 不拒绝右值
static_assert(std::ranges::size(std::vector<int>(3)) == 3);
int main() {}
```

## ranges::reserve_hint [range.prim.size.hint] {{c++26}}

¶2 `ranges::size(E)` 有效时就用它；否则依次尝试成员 `t.reserve_hint()` 和只经实参依赖查找的 `reserve_hint(t)`，结果都必须是整数类类型。

它服务于 C++26 的 `approximately_sized_range`（[[range.approximately.sized]]）。有些范围无法在常数时间给出准确长度，但能给出一个估计，`ranges::to` 可以据此提前 `reserve`。本机 libc++ 还没有提供这个定制点对象。

## ranges::empty [range.prim.empty]

¶2 的顺序是：未知边界的数组非良构；`bool(t.empty())`；`(ranges::size(t) == 0)`；如果 `begin` 的类型建模 `forward_iterator`，则 `bool(ranges::begin(t) == ranges::end(t))`；否则非良构。

它同样不拒绝右值。最后一步要求前向迭代器，因为对输入范围调用 `begin` 本身可能有副作用，例如 `istream_view` 的 `begin` 会读入一个值（[[range.factories]]）。

## ranges::data 与 ranges::cdata

[range.prim.data] ¶2 的顺序是：右值的非借用范围非良构；元素类型不完整的数组 IFNDR；`auto(t.data())` 是对象指针类型时用成员；`ranges::begin(t)` 建模 `contiguous_iterator` 时用 `to_address(ranges::begin(t))`；否则非良构。

[range.prim.cdata] ¶1 `cdata` 等价于 *`as-const-pointer`*`(ranges::data(possibly-const-range(t)))`。*`as-const-pointer`* 只是把 `T*` 变成 `const T*`。

## 定制点对象与函数模板的比较

| | `std::begin`（函数模板） | `ranges::begin`（定制点对象） |
|---|---|---|
| 支持用户的非成员 `begin` | 要写 `using std::begin;` 两步 | 一次限定调用，内部做实参依赖查找 |
| 检查结果类型 | 不检查 | 必须是迭代器，否则替换失败 |
| 右值保护 | 没有 | 拒绝非借用范围的右值 |
| 当作对象传递 | 是重载集，不能直接传 | 是对象，可以复制、作模板实参 |
| 被实参依赖查找劫持 | 可能 | 不会，对象不参与实参依赖查找 |

## 常见误解

!!! pitfall "有 begin 和 end 成员的类型就是范围"
    `range<T>` 检查的是 `ranges::begin(t)` 和 `ranges::end(t)` 能否通过上面的全部规则。成员 `begin()` 返回的不是迭代器、`end()` 返回的不是对应的哨位、缺少 const 版本，都会让它为 `false`。用 `static_assert(std::ranges::range<T>)` 调试，比直接写范围 `for` 得到的错误信息更清楚。

!!! pitfall "定制时只写了非 const 版本"
    上面的 `lib::Bag` 只提供了 `begin(Bag&)`，于是 `const Bag` 不是范围，`views::all(std::as_const(b))` 也会失败。视图适配器经常要求 `range<const V>`，例如 `transform_view::begin() const`，定制时应同时提供 const 重载。

## 思考题

!!! question "思考题 1"
    `ranges::size(std::vector<int>{1, 2, 3})` 合法吗？`ranges::begin(std::vector<int>{1, 2, 3})` 呢？为什么不同？

<details markdown="1">
<summary>答案</summary>

前者合法，返回 3；后者非良构。[range.prim.size] ¶2 没有拒绝非借用右值的那一项，因为长度是一个值，调用结束后不依赖容器存活。[range.access.begin] ¶2.1 明确拒绝非借用右值，因为得到的迭代器会指向已经销毁的临时对象。
</details>

!!! question "思考题 2"
    一个类型既有成员 `begin()`（返回 `int*`），又有实参依赖查找可见的非成员 `begin(T&)`（返回另一种迭代器），`ranges::begin` 选哪个？

<details markdown="1">
<summary>答案</summary>

选成员。¶2.4 排在 ¶2.5 前面，成员版本有效并返回迭代器时就用它，非成员版本根本不会被考虑。只有成员不存在，或者返回的不是 `input_or_output_iterator` 时，才轮到实参依赖查找。
</details>
