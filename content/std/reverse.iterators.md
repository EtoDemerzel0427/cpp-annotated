---
title: reverse_iterator
summary: reverse_iterator 保存"当前位置的下一个"，解引用时先复制再 --tmp——由此产生 base() 差一的关系、对存储型迭代器的悬垂引用；iterator_concept 封顶在 random_access（不是 contiguous）；随机访问操作只在被实例化时才要求底层迭代器支持；比较运算符方向反转、<=> 交换参数；iter_move/iter_swap 转发；disable_sized_sentinel_for 的特化。
status: done
covers: *
since: c++98
related: predef.iterators, iterator.concept.bidir, iterator.concept.forward, iterator.requirements, iterator.cust, iterator.range, temp.inst, sequence.reqmts
tags: 标准库, 迭代器, 适配器, reverse_iterator
updated: 2026-10-18
---

¶1 of [reverse.iterators.general]：`reverse_iterator` 是一个迭代器适配器，从底层迭代器所定义序列的末尾向开头遍历。容器的 `rbegin()`/`rend()`、`std::rbegin`（[[iterator.range]]）、`views::reverse` 都建立在它之上。

## 核心设计：保存"下一个"位置

序列 `[begin, end)` 反向遍历时，起点是最后一个元素、终点是"第一个元素之前"。但"第一个元素之前"这个位置**不存在**——对数组而言，指向首元素之前的指针是 UB（[[expr.add]]）。`reverse_iterator` 的解决办法是：内部保存的 `current` 比逻辑位置**靠后一格**。

```text
        rend()                          rbegin()
          ↓                               ↓
  逻辑：   [前]   e0    e1    e2    e3
  current:       begin            ...    end
```

- `rbegin()` 的 `current` 是 `end()`，逻辑上指向 `e3`；
- `rend()` 的 `current` 是 `begin()`，逻辑上指向"`e0` 之前"——一个合法的、可比较的过尾值；
- 解引用：`Iterator tmp = current; return *--tmp;`（[reverse.iter.elem] ¶1）。

这一设计在整个类里处处可见：`operator++` 是 `--current`，`operator+(n)` 是 `current - n`，`operator[](n)` 返回 `current[-n - 1]`。

## 类定义要点（[reverse.iterator]）

```cpp
template<class Iterator>
class reverse_iterator {
public:
  using iterator_type     = Iterator;
  using iterator_concept  = see below;
  using iterator_category = see below;
  using value_type        = iter_value_t<Iterator>;
  using difference_type   = iter_difference_t<Iterator>;
  using pointer           = iterator_traits<Iterator>::pointer;
  using reference         = iter_reference_t<Iterator>;
  // ...
protected:
  Iterator current;
};
```

- ¶1 `iterator_concept`：底层建模 `random_access_iterator` 时为 `random_access_iterator_tag`，否则为 `bidirectional_iterator_tag`。**永远不是** `contiguous_iterator_tag`——反向遍历的元素地址递减，不满足 [[iterator.concept.contiguous]] 的 `to_address(b) == to_address(a) + (b - a)`。
- ¶2 `iterator_category`：底层的 `iterator_category` 派生自 `random_access_iterator_tag` 时为 `random_access_iterator_tag`（把 `contiguous_iterator_tag` 降一级），否则照搬底层。
- `current` 是 **protected** 数据成员，不是说明专用的——派生类可以直接访问它，这是 C++98 遗留下来的公开接口。

## 对底层迭代器的要求（[reverse.iter.requirements]）

¶1：`Iterator` 必须满足 *Cpp17BidirectionalIterator* **或**建模 `bidirectional_iterator`。¶2：若实例化了 `+`、`-`、`+=`、`-=`、`[]` 成员，或非成员 `<`、`>`、`<=`、`>=`、`-`、`+`，则还须满足 *Cpp17RandomAccessIterator* 或建模 `random_access_iterator`。

"实例化时才要求"依赖于 [[temp.inst]]：类模板成员函数的定义只在被使用时实例化。所以 `reverse_iterator<list<int>::iterator>` 是合法类型，只要不调用 `+=`。这是 C++98 式的"惰性约束"，与 C++20 适配器用 `requires` 子句的做法不同——后者让 `random_access_iterator<reverse_iterator<...>>` 这类概念检查给出准确答案，而前者的成员"看起来存在"。

## 构造与转换（[reverse.iter.cons]、[reverse.iter.conv]）

- 默认构造：值初始化 `current`（¶1）；
- `explicit reverse_iterator(Iterator x)`：用 `x` 初始化 `current`（¶2）——**显式**，防止迭代器被意外地"翻转"；
- 转换构造/赋值 `reverse_iterator<U>` → `reverse_iterator<Iterator>`：要求 `U` 不同于 `Iterator`、`const U&` 建模 `convertible_to<Iterator>`（赋值还要求 `assignable_from`）。这使 `reverse_iterator<iterator>` 能转为 `reverse_iterator<const_iterator>`。
- `base()`：返回 `current`（[reverse.iter.conv] ¶1）。

## 元素访问（[reverse.iter.elem]）

- `operator*`：如同 `Iterator tmp = current; return *--tmp;`。
- `operator->`：仅当 `Iterator` 是指针或 `i.operator->()` 合法时提供；指针时返回 `prev(current)`，否则 `prev(current).operator->()`。
- `operator[](n)`：返回 `current[-n - 1]`；返回类型是**未指明的**（*unspecified*），只要求可用。

## 导航与比较（[reverse.iter.nav]、[reverse.iter.cmp]）

导航全部方向反转：`++` ↔ `--current`，`+ n` ↔ `current - n`，等等。比较运算符也反转：

| 表达式 | 返回 |
|---|---|
| `x == y` / `x != y` | `x.base() == y.base()` / `!=` |
| `x < y` | `x.base() > y.base()` |
| `x > y` | `x.base() < y.base()` |
| `x <= y` | `x.base() >= y.base()` |
| `x >= y` | `x.base() <= y.base()` |
| `x <=> y` | `y.base() <=> x.base()`（注 1：参数顺序反转，因为这是反向迭代器） |

每个比较运算符都有 *Constraints*："对应的 `base()` 表达式良构且可转换为 `bool`"——所以它们对 C++20 的概念检查是友好的。

## 非成员函数（[reverse.iter.nonmember]）

- `x - y` 返回 `y.base() - x.base()`（注意顺序）；`n + x` 返回 `reverse_iterator(x.base() - n)`；
- `iter_move(i)`：`auto tmp = i.base(); return ranges::iter_move(--tmp);`，`noexcept` 取决于复制与 `iter_move` 是否不抛；
- `iter_swap(x, y)`：分别复制、`--` 后调用 `ranges::iter_swap`；
- `make_reverse_iterator(i)`：返回 `reverse_iterator<Iterator>(i)`。

此外，概要（[[iterator.synopsis]]）特化了 `disable_sized_sentinel_for<reverse_iterator<I1>, reverse_iterator<I2>>`：当 `I1` 与 `I2` 不建模 `sized_sentinel_for` 时为 `true`。因为 `reverse_iterator` 的 `operator-` 只受 `decltype(y.base() - x.base())` 的 SFINAE 约束，对 `list` 这类迭代器不会存在，但对"有减法却不是常数时间"的迭代器会存在——这个特化把建模判断交还给底层迭代器。

## 例子：`base()` 与"差一"

```cpp run title="reverse_base.cpp" ok
#include <algorithm>
#include <cassert>
#include <iterator>
#include <vector>

int main() {
    std::vector<int> v{1, 2, 3, 4, 5};
    auto rit = std::find(v.rbegin(), v.rend(), 3);
    assert(*rit == 3);
    assert(*rit.base() == 4);            // base() 指向逻辑位置的"下一个"

    // 用反向迭代器删除它所指的元素：要先前进一步再取 base()
    v.erase(std::next(rit).base());      // 删除 3
    assert((v == std::vector{1, 2, 4, 5}));

    static_assert(std::random_access_iterator<std::reverse_iterator<int*>>);
    static_assert(!std::contiguous_iterator<std::reverse_iterator<int*>>);
}
```

`v.erase(rit.base())` 会删掉 `4` 而不是 `3`——这是使用 `reverse_iterator` 最常见的错误。`std::next(rit).base()`（等价于 `rit.base() - 1`）才是 `rit` 逻辑上所指的元素。

## 例子：存储型迭代器上的悬垂引用

```cpp run title="reverse_stash.cpp" ub
#include <cstdio>
#include <iterator>

// "生成器"式迭代器：当前值存在迭代器自身，*it 返回对成员的引用
struct Counter {
    using value_type = int;
    using difference_type = std::ptrdiff_t;
    int cur = 0;
    const int& operator*() const { return cur; }
    Counter& operator++() { ++cur; return *this; }
    Counter operator++(int) { auto t = *this; ++cur; return t; }
    Counter& operator--() { --cur; return *this; }
    Counter operator--(int) { auto t = *this; --cur; return t; }
    bool operator==(const Counter&) const = default;
};
static_assert(std::bidirectional_iterator<Counter>);   // 满足——但不建模

int main() {
    std::reverse_iterator<Counter> r(Counter{3});
    const int& x = *r;   // operator* 内的 tmp 是局部变量，返回的引用指向它
    std::printf("%d\n", x);   // UB：悬垂引用
}
```

`Counter` 满足 `bidirectional_iterator` 的全部语法要求，却违反 [[iterator.concept.forward#3]]（"从前向迭代器取得的引用在范围有效期间保持有效"）——它只能算输入迭代器（[[iterator.requirements.general#15]]）。`reverse_iterator::operator*` 正依赖这条语义：它解引用的是**局部副本** `tmp`，返回的引用必须指向 `tmp` 之外的东西。用 AddressSanitizer 的 `-fsanitize-address-use-after-return=always` 运行上例，会报告 stack-use-after-return。

!!! history "曾经的解决尝试"
    C++11 的规格曾为 `reverse_iterator` 增设一个说明专用的成员 `deref_tmp`，让 `operator*` 把 `--current` 的结果存进成员后再解引用，以支持存储型迭代器。但这让 `reverse_iterator` 自身变成存储型迭代器（引用随适配器对象销毁而失效），而且 `const` 的 `operator*` 修改成员会引发数据竞争；C++14 撤销了这一改动，回到"复制到局部变量再解引用"的写法，并依靠前向迭代器的"引用不依赖迭代器对象"要求来保证正确性。

## 常见误区

!!! pitfall "`erase(rit.base())` 删错元素"
    见上。记住：`&*rit == &*(rit.base() - 1)`。

!!! pitfall "`reverse_iterator<T*>` 不是指针，也不是连续迭代器"
    需要指针的接口（`std::span`、`memcpy`）不能直接接受反向迭代器。`std::span<int>(v.rbegin(), v.rend())` 不能编译。

## 思考题

!!! question "思考题"
    1. 为什么 `reverse_iterator` 的 `operator[]` 返回类型是"未指明的"，而不是 `reference`？
    2. `reverse_iterator<reverse_iterator<I>>` 与 `I` 的关系是什么？`views::reverse` 对 `reverse_view` 再取 `reverse` 时为什么不生成这种类型？

<details markdown="1">
<summary>展开查看答案与解析</summary>

1. `current[-n - 1]` 的类型由底层迭代器决定；对 *Cpp17RandomAccessIterator*，`a[n]` 只要求"可转换为 `reference`"，可能是代理。若规定返回 `reference`，就得强制一次转换，对代理迭代器可能产生悬垂或错误的语义；"未指明"允许实现直接返回 `current[-n - 1]` 的结果。
2. 双重反转的 `current` 是 `reverse_iterator<I>(x)`，再解引用时 `--` 两次抵消，行为与 `I` 一致，但类型更复杂、每次解引用都要多复制。`views::reverse` 对 `reverse_view` 以及元素为 `reverse_iterator` 的 `subrange` 做了特殊处理，直接取回底层范围（[[range.reverse.overview]]）。
</details>

## 小结

!!! summary
    - `current` 保存逻辑位置的下一格；`*r` = `*prev(current)`，`r.base()` 比 `r` 靠后一格。
    - 类别：最高随机访问，永不连续；随机访问操作在实例化时才要求底层支持。
    - 比较方向反转，`<=>` 交换参数，`x - y` = `y.base() - x.base()`。
    - 依赖底层是"真"前向迭代器：存储型迭代器会导致悬垂引用。
    - `disable_sized_sentinel_for` 特化让 sized 判断跟随底层迭代器。
