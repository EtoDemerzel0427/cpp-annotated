---
title: 范围访问
summary: ranges::begin/end/cbegin/rbegin/size/ssize/reserve_hint/empty/data/cdata 这组定制点对象的精确算法——物化对象、右值与借用、数组、成员优先、仅 ADL 的非成员查找、返回类型检查与 SFINAE 友好；以及为什么它们取代了 std::begin。
status: done
covers: *
since: c++20
papers: P0896R4, P2602R2, P2278R4
related: ranges, range.req, range.range, customization.point.object, conventions, basic.lookup.argdep, iterator.concepts, iterator.range, stmt.ranged, conv.rval, expr.type.conv
tags: 标准库, 范围, CPO, ADL, 定制点
updated: 2026-10-18
---

`std::begin(c)` 有什么问题？它是一个普通的函数模板：

- 对于自带非成员 `begin` 的用户类型，必须写"两步式" `using std::begin; begin(c);` 才能找到它；
- 它对返回值不做任何检查——`begin()` 返回 `int` 也照单全收；
- 它接受右值容器 `std::begin(std::vector<int>{})`，返回一个立刻悬垂的迭代器。

[range.access] 用一组**定制点对象**（[[g:customization-point-object]]，规则见 [[customization.point.object]] 与 [[conventions]]）解决这三点。读懂这一节的意义在于：`range` 概念就是用 `ranges::begin`/`ranges::end` 定义的（[[range.range]]），所以"一个类型是不是 range"完全由这里的算法决定。

## 公共前提（[range.access.general]）

¶1 这些 CPO 除了 `<ranges>` 之外，包含 `<iterator>` 时也可用。

¶2 定义了贯穿全节的术语——子表达式 `E` 的**物化对象**（*reified object*，[[g:reified-object]]）：

- 若 `E` 是 glvalue，就是 `E` 所指的那个对象；
- 否则是对 `E` 施加临时量实质化转换（[[conv.rval]]）的结果。

随后各条都说"令 `t` 为指代 `E` 的物化对象的**左值**"。也就是说，**无论你传进来的是左值还是右值，后续一律对一个左值 `t` 调用 `t.begin()` / `begin(t)`**。右值性只在第一步"要不要拒绝"时起作用。

## `ranges::begin`（[range.access.begin]）

¶2 给定类型为 `T` 的子表达式 `E`，按顺序判定：

| 条 | 条件 | 结果 |
|---|---|---|
| 2.1 | `E` 是右值且 `enable_borrowed_range<remove_cv_t<T>>` 为 `false` | {{ill-formed}} |
| 2.2 | `T` 是数组且元素类型不完整 | {{ifndr}} |
| 2.3 | `T` 是数组 | `t + 0` |
| 2.4 | `auto(t.begin())` 合法且类型建模 `input_or_output_iterator` | `auto(t.begin())` |
| 2.5 | `T` 是类或枚举，且 `auto(begin(t))` 合法且建模 `input_or_output_iterator`，其中 `begin` **仅经 ADL** 查找 | 该表达式 |
| 2.6 | 其他 | {{ill-formed}} |

几个关键词的分量：

- **2.1 右值拒绝**：`ranges::begin(std::vector<int>{})` 非良构，因为迭代器会随临时量死去；但 `ranges::begin(std::string_view{"x"})` 合法——`string_view` 是借用范围（[[range.range#4]]），迭代器指向别处的存储。这就是 `enable_borrowed_range` 的用武之地。
- **2.3 `t + 0`**：不写成 `t`，是为了确保得到指针 prvalue，而不是数组左值。
- **`auto(...)`**：C++23 的 *decay-copy* 写法（[[expr.type.conv]]）。返回值总是被**按值复制**出来，`begin()` 返回引用也会被退化。
- **返回类型检查**：成员 `begin()` 存在但返回的不是迭代器，2.4 就不选它，转而尝试 2.5；都不行则非良构。这让 `range` 概念不会把"碰巧有个叫 `begin` 的成员"的类型误判为范围。
- **2.5 仅 ADL**：非成员 `begin` 只通过实参依赖查找（[[basic.lookup.argdep]]）寻找，普通的非限定查找不参与——所以 `std::begin` 本身不会被找到（否则会无限递归或把 `std::begin` 的无约束模板拉进来）。

¶3 注 1：上述"可诊断的非良构"在模板实例化的立即语境中表现为**替换失败**——这是 [[customization.point.object#4]] 要求的"不满足要求时没有可参与重载决议的调用运算符"的具体体现。¶4 注 2：只要 `ranges::begin(E)` 合法，其类型就建模 `input_or_output_iterator`。

```cpp run ok
#include <ranges>
#include <vector>
namespace lib {
  struct Bag { int data[3]{1, 2, 3}; };
  // 非成员 begin/end：只能经 ADL 找到
  inline int* begin(Bag& b) { return b.data; }
  inline int* end(Bag& b) { return b.data + 3; }
}
static_assert(std::ranges::range<lib::Bag>);                 // 2.5：ADL 找到 lib::begin
static_assert(!std::ranges::range<const lib::Bag>);          // const Bag& 绑不到 Bag&
static_assert(!std::invocable<decltype(std::ranges::begin), lib::Bag>);   // 2.1：右值且非借用
static_assert(std::invocable<decltype(std::ranges::begin), std::vector<int>&>);
static_assert(!std::invocable<decltype(std::ranges::begin), std::vector<int>>);  // 右值容器
static_assert(std::invocable<decltype(std::ranges::begin), std::ranges::subrange<int*>>); // 借用范围右值 OK
int main() {
  lib::Bag b;
  int s = 0;
  for (int x : b) s += x;   // 范围 for 也走 ADL（[stmt.ranged]）
  return s == 6 ? 0 : 1;
}
```

```cpp run ok
#include <ranges>
// begin() 返回 int 而不是迭代器：被 CPO 拒绝
struct Weird { int begin() { return 0; } int end() { return 0; } };
static_assert(!std::ranges::range<Weird>);
int main() {}
```

!!! history "毒丸（poison pill）的来去"
    C++20 的措辞是：非成员 `begin(t)` 的重载决议"在一个包含若干**被删除的 `begin` 函数模板**声明的语境中进行"。这些被删除的声明俗称**毒丸**，作用是让非限定查找停在这里、找不到 `std::begin`。但毒丸本身也是重载决议的候选，在某些情况下会比用户提供的合法定制更匹配，从而把它"毒死"。C++23 的 [[P2602R2]]（"Poison Pills are Too Toxic"，作为 DR）把措辞改成了今天的"如同仅进行实参依赖查找"，彻底去掉了这一副作用。

!!! impl "libc++ 怎么实现“仅 ADL”"
    libc++ 在 `__ranges/access.h` 中于 CPO 所在的内部命名空间里声明 `void begin() = delete;`——一个**零参数**的被删除函数。它的作用是让非限定查找在这里停下（不会继续向外找到 `std::begin`），而因为它不接受任何实参，永远不会成为可行函数，于是效果等于"只有 ADL 找到的候选"。函数对象的最后还有一个 `void operator()(auto&&) const = delete;` 兜底。

## `ranges::end`（[range.access.end]）

结构与 `begin` 平行，差别在于：

- ¶2.3 **未知边界数组**（`int[]`）直接非良构（不知道尾在哪）；
- ¶2.4 已知边界数组给出 `t + extent_v<T>`；
- ¶2.5/2.6 成员 `end()` 或 ADL `end(t)` 的返回类型必须建模 `sentinel_for<iterator_t<T>>`——**用 `begin` 的结果类型来检验 `end`**。

¶4 注 2：合法时，`end` 与 `begin` 的类型 `S`、`I` 建模 `sentinel_for<S, I>`。

## `cbegin` / `cend`（[range.access.cbegin]、[range.access.cend]）

C++23 起（[[P2278R4]]）它们**保证返回常量迭代器**：

- `U` = `ranges::begin(possibly-const-range(t))`；
- `cbegin(E)` 等价于 `const_iterator<decltype(U)>(U)`。

*possibly-const-range*（[[ranges.syn]]）的定义是：若 `const R` 是 `input_range` 就用 `const R&`，否则仍用 `R&`。所以对 `vector<int>` 先加 `const` 得到 `const_iterator`；对 `filter_view` 这种没有 `const begin()` 的视图，退而用非 `const` 的迭代器，再由 `const_iterator<>` 包一层 `basic_const_iterator`，使解引用得到 `const int&`。这修好了 C++20 的老问题：C++20 的 `ranges::cbegin(span<int>)` 只是对 `const span` 调 `begin`，而 `span` 的浅 const 使得结果仍然可写。

下面的例子按标准（C++23 起）应当编译通过；但截至编写时 libc++ 尚未实现 [[P2278R4]]（其 `__cpp_lib_ranges_as_const` 仍被注释掉），本站验证环境中两条 `static_assert` 都会失败——`ranges::cbegin(s)` 在 libc++ 上仍返回可写的 `int*` 式迭代器。

```cpp run
#include <ranges>
#include <span>
#include <vector>
#include <type_traits>
int main() {
  std::vector<int> v{1, 2, 3};
  std::span<int> s = v;
  auto it = std::ranges::cbegin(s);
  static_assert(std::is_same_v<decltype(*it), const int&>);   // C++23：真正只读
  auto ev = v | std::views::filter([](int x) { return x > 1; });
  auto ci = std::ranges::cbegin(ev);                          // filter_view 无 const begin，也行
  static_assert(std::is_same_v<decltype(*ci), const int&>);
  return *ci == 2 ? 0 : 1;
}
```

## `rbegin` / `rend` / `crbegin` / `crend`

[range.access.rbegin] ¶2：先试成员 `rbegin()`、再试 ADL `rbegin(t)`（都要求返回迭代器），最后的兜底（2.5）是：若 `ranges::begin(t)` 与 `ranges::end(t)` **类型相同**且建模 `bidirectional_iterator`，则为 `make_reverse_iterator(ranges::end(t))`。注意"类型相同"——非 common 的范围（首尾不同类型）没有这条兜底，需要先 `views::common`。`rend` 对称地使用 `make_reverse_iterator(ranges::begin(t))`，并要求返回类型是 `rbegin` 结果的哨位。`crbegin`/`crend` 与 `cbegin`/`cend` 同理，在 `possibly-const-range` 上调用 `rbegin`/`rend` 再包一层 `const_iterator`/`const_sentinel`。

## `ranges::size`（[range.prim.size]）

¶2 的顺序：

1. 未知边界数组：非良构；
2. 数组：`auto(extent_v<T>)`；
3. `disable_sized_range<remove_cv_t<T>>` 为 `false` 且 `auto(t.size())` 是**整数类类型**（[[iterator.concept.winc]]）：用成员；
4. 类/枚举、未被禁用、`auto(size(t))`（仅 ADL）是整数类类型：用它；
5. 否则，若 `end - begin` 可算、且 `I`、`S` 建模 `sized_sentinel_for<S, I>` **与 `forward_iterator<I>`**：`to-unsigned-like(end - begin)`；
6. 否则非良构。

要点：

- **与 `begin`/`end` 不同，`size` 没有右值拒绝**：大小是一个值，不会悬垂，所以 `ranges::size(std::vector<int>(3))` 合法。
- **`disable_sized_range`**（[[range.sized#3]]）是"逃生舱"：某类型有 `size()` 成员但它**不是 O(1)** 或语义不符（例如老式链表的 O(n) `size()`），特化为 `true` 就能让 `ranges::size` 跳过 3/4 两步。
- 第 5 步要求 `forward_iterator`：对单趟的输入迭代器，求 `end - begin` 之后 `begin` 可能已经"用掉"了（[[range.sized#2]] 的注说明了这一点）。
- 返回类型不一定无符号：成员 `size()` 返回 `int` 就是 `int`；只有第 5 步才强制转成无符号。

## `ranges::ssize`（[range.prim.ssize]）

¶2 若 `ranges::size(t)` 非良构则非良构；否则 `D` = `make-signed-like-t<decltype(ranges::size(t))>`，**若 `ptrdiff_t` 更宽则用 `ptrdiff_t`**，结果为 `static_cast<D>(ranges::size(t))`。它就是为了让 `for (auto i = 0; i < ranges::ssize(v); ++i)` 不再产生有符号/无符号比较告警。

```cpp run ok
#include <ranges>
#include <cstddef>
struct S { int* begin(); int* end(); int size() const { return 3; } };
// 成员 size() 返回 int：ranges::size 原样返回 int
static_assert(std::same_as<decltype(std::ranges::size(std::declval<S&>())), int>);
// ssize：make-signed-like-t<int> 是 int，但 ptrdiff_t 更宽，于是取 ptrdiff_t
static_assert(std::same_as<decltype(std::ranges::ssize(std::declval<S&>())), std::ptrdiff_t>);
int main() {}
```

## `ranges::reserve_hint`（[range.prim.size.hint]）{{c++26}}

¶2：若 `ranges::size(E)` 合法则就是它；否则依次尝试成员 `t.reserve_hint()`、ADL `reserve_hint(t)`（返回整数类类型）。它为 C++26 的 `approximately_sized_range`（[[range.approximately.sized]]）服务：像 `filter_view` 这样无法 O(1) 给出准确长度、但能给出一个**上界或估计**的范围，可以让 `ranges::to` 提前 `reserve`。截至编写时 libc++ 尚未提供此 CPO。

## `ranges::empty`（[range.prim.empty]）

¶2 顺序：未知边界数组非良构 → `bool(t.empty())` → `(ranges::size(t) == 0)` → 若 `begin` 的类型建模 `forward_iterator`，则 `bool(ranges::begin(t) == ranges::end(t))` → 非良构。同样没有右值拒绝。最后一步要求前向迭代器：对输入范围，调用 `begin` 本身就可能有副作用（例如 `istream_view` 的 `begin` 会读一个值，见 [[range.factories]]）。

## `ranges::data` / `ranges::cdata`（[range.prim.data]、[range.prim.cdata]）

`data`：右值且非借用则非良构 → 元素不完整的数组 IFNDR → `auto(t.data())` 是**对象指针**类型 → 若 `ranges::begin(t)` 建模 `contiguous_iterator`，则 `to_address(ranges::begin(t))` → 非良构。

`cdata` 等价于 *as-const-pointer*(`ranges::data(possibly-const-range(t))`)，*as-const-pointer* 只是把 `T*` 变成 `const T*`。

## 为什么 CPO 而不是重载函数

| 需求 | `std::begin`（函数模板） | `ranges::begin`（CPO） |
|---|---|---|
| 用户定制 | 需要 `using std::begin;` 两步式 | 一次限定调用，内部自动 ADL |
| 返回类型检查 | 无 | 必须是迭代器/哨位，否则 SFINAE 失败 |
| 右值保护 | 无 | 非借用右值直接拒绝 |
| 能否当对象传递 | 重载集，不能直接传 | 对象，可复制、可作模板实参 |
| 被 ADL 劫持 | 可能 | 不会（对象不参与 ADL） |

## 常见误区

!!! pitfall "以为 `range<T>` 等于 “T 有 begin/end 成员”"
    `range` 检查的是 `ranges::begin(t)` 与 `ranges::end(t)` 能否**通过 CPO 的全部规则**。成员 `begin()` 返回非迭代器、`end()` 返回的不是对应 `begin` 的哨位、只有 `const` 版本缺失……都会让它为 `false`。用 `static_assert(std::ranges::range<T>)` 调试远比直接 `for` 出错信息友好。

!!! pitfall "对 const 对象的定制只写了非 const 版本"
    上面 `lib::Bag` 只提供 `begin(Bag&)`，于是 `const Bag` 不是范围，`views::all(std::as_const(b))` 也会失败。视图适配器经常需要 `range<const V>`（例如 `transform_view::begin() const`），定制时应同时提供 const 重载。

## 思考题

<details markdown="1">
<summary>1. `ranges::size(std::vector<int>{1,2,3})` 合法吗？`ranges::begin(std::vector<int>{1,2,3})` 呢？为什么二者不同？</summary>

前者合法，返回 3；后者非良构。[range.prim.size] ¶2 没有"右值且非借用则非良构"那一条，因为大小是一个值，调用结束后不依赖容器存活；而 [range.access.begin] ¶2.1 明确拒绝非借用右值，因为得到的迭代器会指向已销毁的临时量。
</details>

<details markdown="1">
<summary>2. 一个类型同时有成员 `begin()`（返回 `int*`）和 ADL 可见的非成员 `begin(T&)`（返回另一种迭代器），`ranges::begin` 选哪个？</summary>

选成员。¶2.4 在 ¶2.5 之前，只要成员版本合法并返回迭代器就采用它，ADL 版本根本不会被考虑。只有成员不存在或返回类型不是 `input_or_output_iterator` 时才轮到 ADL。
</details>

<details markdown="1">
<summary>3. 为什么 `ranges::rbegin` 的兜底要求 `begin` 和 `end` 是同一类型？</summary>

兜底是 `make_reverse_iterator(ranges::end(t))`，`reverse_iterator<I>` 需要一个**迭代器** `I` 作为起点，并且要对它做 `--`。哨位一般既不能递减也不是迭代器，所以只有 common range（`end` 返回的也是迭代器）才能用这个兜底（¶2.5）。
</details>

## 小结

- 所有 CPO 都先把 `E` 变成物化对象的左值 `t`，再按"数组 → 成员 → 仅 ADL 的非成员 → 兜底"的顺序选择实现；
- `begin`/`end`/`cbegin`/`rbegin`/`data` 拒绝非借用右值；`size`/`ssize`/`empty`/`reserve_hint` 不拒绝；
- 每一步都检查返回类型（迭代器、哨位、整数类、对象指针），不合格即 SFINAE 友好地失败；
- `cbegin` 等自 C++23 起保证常量迭代器；`ssize` 至少与 `ptrdiff_t` 一样宽；`disable_sized_range` 可以关闭非 O(1) 的 `size()`。
