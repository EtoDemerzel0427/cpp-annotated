---
title: reverse_iterator
summary: reverse_iterator 内部保存逻辑位置的下一格，由此产生 base() 差一、比较方向反转，以及对把元素存在体内的迭代器产生悬垂引用。
status: done
covers: *
since: c++98
papers: LWG198, LWG2204
related: predef.iterators, iterator.concept.bidir, iterator.concept.forward, iterator.requirements, iterator.cust, iterator.range, temp.inst, sequence.reqmts
tags: 标准库, 迭代器, 适配器, reverse_iterator
updated: 2026-10-19
---

!!! tldr
    - `reverse_iterator` 内部保存的 `current` 比它逻辑上指向的元素靠后一格，解引用时先复制一份再 `--`，所以 `*r` 等于 `*prev(r.base())`。
    - 用反向迭代器删除元素要写 `v.erase(std::next(rit).base())`；`v.erase(rit.base())` 删掉的是后面那个元素。
    - 它最高是随机访问迭代器，永远不是连续迭代器；`+=`、`[]` 等运算只在实际用到时才要求底层支持随机访问。
    - 比较运算全部反向：`x < y` 就是 `x.base() > y.base()`，`x - y` 就是 `y.base() - x.base()`。
    - 它依赖底层迭代器的引用不指向迭代器自身；把当前值存在体内的迭代器套上它，解引用得到的是悬垂引用。

```cpp run title="reverse_base.cpp" ok
#include <algorithm>
#include <cassert>
#include <iterator>
#include <vector>

int main() {
    std::vector<int> v{1, 2, 3, 4, 5};
    auto rit = std::find(v.rbegin(), v.rend(), 3);
    assert(*rit == 3);
    assert(*rit.base() == 4);            // base() 指向逻辑位置的下一个元素

    // 删除 rit 所指的元素：先前进一步再取 base()
    v.erase(std::next(rit).base());      // 删除 3
    assert((v == std::vector{1, 2, 4, 5}));

    static_assert(std::random_access_iterator<std::reverse_iterator<int*>>);
    static_assert(!std::contiguous_iterator<std::reverse_iterator<int*>>);
}
```

¶1 [reverse.iterators.general]：`reverse_iterator` 是一个迭代器适配器，从底层迭代器所表示序列的末尾向开头遍历。容器的 `rbegin()`、`rend()`，`std::rbegin`（[[iterator.range]]），以及 `views::reverse` 都建立在它之上。

## 为什么要错开一格

反向遍历 `[begin, end)` 时，起点是最后一个元素，终点是第一个元素之前的位置。可是第一个元素之前的位置并不存在：对数组来说，算出首元素之前的指针就是未定义行为（[[expr.add]]）。

`reverse_iterator` 的办法是让内部保存的 `current` 比逻辑位置靠后一格：

```text
            rend()                     rbegin()
              ↓                           ↓
  逻辑位置：  (e0 之前)  e0    e1    e2    e3
  current：             begin                    end
```

- `rbegin()` 的 `current` 是 `end()`，逻辑上指向 `e3`；
- `rend()` 的 `current` 是 `begin()`，逻辑上指向 `e0` 之前，这是一个合法、可以比较的位置；
- 解引用如同 `Iterator tmp = current; return *--tmp;`（[[reverse.iter.elem#1]]）。

整个类都按这个错位来写：`operator++` 是 `--current`，`operator+(n)` 返回 `reverse_iterator(current - n)`，`operator[](n)` 返回 `current[-n - 1]`。`base()` 直接返回 `current`，所以比逻辑位置靠后一格。`&*rit == &*(rit.base() - 1)` 总是成立。

## 类的定义 [reverse.iterator]

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
  // 构造、base()、*、->、++、--、+、+=、-、-=、[]、iter_move、iter_swap
protected:
  Iterator current;
};
```

¶1 底层建模 `random_access_iterator` 时，`iterator_concept` 是 `random_access_iterator_tag`，否则是 `bidirectional_iterator_tag`。它永远不是 `contiguous_iterator_tag`：反向遍历时元素地址递减，不满足连续迭代器 `to_address(b) == to_address(a) + (b - a)` 的要求（[[iterator.concept.contiguous]]）。所以 `std::span<int>(v.rbegin(), v.rend())` 不能编译。

¶2 底层的 `iterator_category` 派生自 `random_access_iterator_tag` 时，`iterator_category` 是 `random_access_iterator_tag`，也就是把 `contiguous_iterator_tag` 降一级；否则照搬底层的标签。

`current` 是 protected 的普通数据成员，不是仅供说明的成员。派生类可以直接访问它，这是从 C++98 保留下来的公开接口。

## 对底层迭代器的要求 [reverse.iter.requirements]

¶1 `Iterator` 必须满足 *Cpp17BidirectionalIterator* 或建模 `bidirectional_iterator`。

¶2 如果成员 `+`、`-`、`+=`、`-=`、`[]`，或者非成员 `<`、`>`、`<=`、`>=`、`-`、`+` 的定义被实例化了，`Iterator` 还必须满足 *Cpp17RandomAccessIterator* 或建模 `random_access_iterator`。

类模板成员函数的定义只在用到时才实例化（[[temp.inst]]），所以 `reverse_iterator<std::list<int>::iterator>` 是合法的类型，只要不调用 `+=`。这是 C++98 式的做法，代价是这些成员在声明上看起来总是存在：

```cpp run ok
#include <iterator>
#include <list>

using R = std::reverse_iterator<std::list<int>::iterator>;
static_assert(requires(R r) { r += 1; });         // 声明存在，检查通过
static_assert(!std::random_access_iterator<R>);   // 但 iterator_concept 给出了正确答案

int main() {}
```

C++20 之后新增的适配器改用 `requires` 子句，成员只在底层支持时才存在。

## 构造与转换 [reverse.iter.cons] [reverse.iter.conv]

- ¶1 默认构造值初始化 `current`。
- ¶2 `explicit reverse_iterator(Iterator x)` 用 `x` 初始化 `current`。它是 explicit 的，普通迭代器不会被悄悄地翻转。
- ¶3–¶7 可以从 `reverse_iterator<U>` 转换构造和转换赋值，条件是 `U` 与 `Iterator` 不同、`const U&` 可以转换为 `Iterator`，赋值还要求 `assignable_from<Iterator&, const U&>`。`reverse_iterator<iterator>` 因此能转换为 `reverse_iterator<const_iterator>`。
- `base()` 返回 `current`（[[reverse.iter.conv#1]]）。

## 元素访问与移动 [reverse.iter.elem] [reverse.iter.nav]

¶2 `operator->` 只在 `Iterator` 是指针、或者 `i.operator->()` 合法时提供：指针时返回 `prev(current)`，否则返回 `prev(current).operator->()`。¶3 `operator[](n)` 返回 `current[-n - 1]`，返回类型是未指明的。

[reverse.iter.nav] 的十二段把方向全部反过来：`++` 是 `--current`，`--` 是 `++current`，`+ n` 是 `current - n`，`+= n` 是 `current -= n`，依此类推。

## 比较 [reverse.iter.cmp]

| 表达式 | 结果 |
|---|---|
| `x == y`、`x != y` | `x.base() == y.base()`、`x.base() != y.base()` |
| `x < y` | `x.base() > y.base()` |
| `x > y` | `x.base() < y.base()` |
| `x <= y` | `x.base() >= y.base()` |
| `x >= y` | `x.base() <= y.base()` |
| `x <=> y` | `y.base() <=> x.base()` |

¶13–¶14 `<=>` 交换了参数顺序，注 1 说明这是因为它是反向迭代器。前六个运算符都有约束：对应的 `base()` 表达式必须良构并且可以转换为 `bool`，所以概念检查能得到准确的结果。

## 非成员函数 [reverse.iter.nonmember]

- ¶1 `x - y` 返回 `y.base() - x.base()`，注意顺序。¶2 `n + x` 返回 `reverse_iterator(x.base() - n)`。
- ¶3–¶4 `iter_move(i)` 等价于 `auto tmp = i.base(); return ranges::iter_move(--tmp);`。复制底层迭代器和对它 `iter_move` 都不抛异常时，它是 `noexcept` 的。
- ¶5–¶6 `iter_swap(x, y)` 分别复制两个 `base()`，各自 `--` 后调用 `ranges::iter_swap`。
- ¶7 `make_reverse_iterator(i)` 返回 `reverse_iterator<Iterator>(i)`。

`operator-` 只靠返回类型 `decltype(y.base() - x.base())` 约束。底层迭代器有减法时它就存在，不管减法是不是常数时间。所以 [[iterator.synopsis]] 特化了 `disable_sized_sentinel_for<reverse_iterator<I1>, reverse_iterator<I2>>`：`I2` 和 `I1` 不建模 `sized_sentinel_for` 时它为 `true`，让判断跟随底层迭代器（[[iterator.concept.sizedsentinel]]）。

## 把元素存在体内的迭代器

```cpp run title="reverse_stash.cpp" ub
#include <cstdio>
#include <iterator>

// 当前值存在迭代器自身，*it 返回对成员的引用
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
static_assert(std::bidirectional_iterator<Counter>);   // 满足，但不建模

int main() {
    std::reverse_iterator<Counter> r(Counter{3});
    const int& x = *r;        // operator* 里的 tmp 是局部变量，引用指向它
    std::printf("%d\n", x);   // UB：悬垂引用
}
```

`Counter` 通过了 `bidirectional_iterator` 的全部语法检查，但违反了前向迭代器的语义要求：从迭代器取得的引用，在范围有效期间必须保持有效（[[iterator.concept.forward#3]]）。这样的迭代器只能算输入迭代器（[[iterator.requirements.general#15]]）。

`reverse_iterator::operator*` 正依赖这条要求：它解引用的是局部副本 `tmp`，返回的引用必须指向 `tmp` 以外的东西。本机用 `-fsanitize=address -fsanitize-address-use-after-return=always` 运行上例，AddressSanitizer 报告 stack-use-after-return。

!!! history "曾经的修补"
    [[LWG198]] 的决议曾在 C++11 中给 `reverse_iterator` 增加一个仅供说明的成员 `deref_tmp`，让 `operator*` 把递减后的迭代器存进成员再解引用，以支持这类迭代器。但这样 `reverse_iterator` 自己就成了把元素存在体内的迭代器，引用随适配器对象一起失效；而且 const 的 `operator*` 修改成员，会在多线程读取时引起数据竞争。[[LWG2204]] 在 C++14 中撤销了这一改动，回到复制到局部变量再解引用的写法。

## 思考题

!!! question "思考题 1"
    `operator[]` 的返回类型为什么是未指明的，而不是 `reference`？

<details markdown="1">
<summary>答案</summary>

`current[-n - 1]` 的类型由底层迭代器决定。对 *Cpp17RandomAccessIterator*，`a[n]` 只要求能转换为 `reference`，可能是一个代理对象。如果规定返回 `reference`，就要强制做一次转换，对代理迭代器可能产生悬垂引用。未指明的返回类型允许实现直接返回 `current[-n - 1]` 的结果。
</details>

!!! question "思考题 2"
    `reverse_iterator<reverse_iterator<I>>` 和 `I` 有什么关系？对 `reverse_view` 再套一次 `views::reverse` 时，为什么得不到这种类型？

<details markdown="1">
<summary>答案</summary>

两次反转在行为上抵消，结果与 `I` 一样，但类型更复杂，每次解引用都要多复制、多递减一次。所以 `views::reverse` 对 `reverse_view`，以及由 `reverse_iterator` 组成的 `subrange`，做了特殊处理，直接取回底层范围（[[range.reverse.overview]]）。
</details>
