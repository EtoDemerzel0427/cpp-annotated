---
title: move_iterator 与 move_sentinel
summary: move_iterator 的解引用返回 ranges::iter_move(current)（右值引用），让"复制类"算法改为移动；reference = iter_rvalue_reference_t、pointer = Iterator、operator-> 已弃用（移入附录 D）；iterator_concept 封顶 random_access；对输入迭代器后置 ++ 返回 void；比较运算符均有 Constraints；move_sentinel 配合哨位使用。最大的陷阱：算法若对同一元素解引用两次（谓词 + 复制），第一次就把它移走了。
status: done
covers: *
since: c++11
related: predef.iterators, iterator.cust, alg.req, reverse.iterators, iterator.concept.sentinel, over.inc.default, lib.types.movedfrom
tags: 标准库, 迭代器, 适配器, 移动语义
updated: 2026-10-18
---

¶1 of [move.iterators.general]：`move_iterator` 是一个迭代器适配器，行为与底层迭代器相同，只是间接运算符把底层解引用的结果**隐式转换为右值**。某些泛型算法可以用移动迭代器调用，以**移动代替复制**。¶2 例 1：

```cpp
list<string> s;
vector<string> v1(s.begin(), s.end());          // 复制
vector<string> v2(make_move_iterator(s.begin()),
                  make_move_iterator(s.end())); // 移动
```

## 类定义要点（[move.iterator]）

```cpp
template<class Iterator>
class move_iterator {
public:
  using iterator_type     = Iterator;
  using iterator_concept  = see below;
  using iterator_category = see below;            // 不总是存在
  using value_type        = iter_value_t<Iterator>;
  using difference_type   = iter_difference_t<Iterator>;
  using pointer           = Iterator;
  using reference         = iter_rvalue_reference_t<Iterator>;
  // ...
private:
  Iterator current = Iterator();                  // 说明专用
};
```

- `reference` 是 `iter_rvalue_reference_t<Iterator>`：对 `T*` 是 `T&&`；对代理迭代器则是其 `iter_move` 的结果类型——C++20 起它基于 `ranges::iter_move` 定义，因而也适用于定制了 `iter_move` 的代理迭代器（[[iterator.cust]]）。
- `pointer` 是 `Iterator` 本身。类定义中**没有** `operator->`：它被移到了附录 D 的 [[depr.move.iter.elem]]（{{deprecated}}），返回 `current`——通过 `->` 访问成员得到的是左值，与"解引用即右值"的语义相悖，所以 C++20 起弃用。
- `current` 是私有的说明专用成员（对比 `reverse_iterator` 的 protected `current`）。

¶1 `iterator_concept`：底层建模 `random_access_iterator` → `random_access_iterator_tag`；否则依次 bidirectional、forward；否则 `input_iterator_tag`。**不会是 contiguous**——`contiguous_iterator` 要求引用是左值引用。

¶2 `iterator_category`：仅当 `iterator_traits<Iterator>::iterator_category` 有效时才声明；派生自 `random_access_iterator_tag` 时为 `random_access_iterator_tag`，否则照搬。注意它对 C++17 接口仍申报为随机访问——即便 `reference` 是 `T&&`。*Cpp17ForwardIterator* 要求 `reference` 是"`T` 的引用"，右值引用算不算是一个长期的灰色地带；实践中容器构造函数等都依赖这一申报来预先计算距离。

## 要求（[move.iter.requirements]）

¶1：`Iterator` 必须满足 *Cpp17InputIterator* 或建模 `input_iterator`；若实例化了双向遍历函数，须满足 *Cpp17BidirectionalIterator* 或建模 `bidirectional_iterator`；随机访问函数同理。与 `reverse_iterator` 一样是"实例化时才要求"。

## 构造、转换、元素访问（[move.iter.cons]、[move.iter.op.conv]、[move.iter.elem]）

- 默认构造：`requires default_initializable<Iterator> = default`——C++20 起只在底层可默认初始化时存在；
- `explicit move_iterator(Iterator i)`：以 `std::move(i)` 初始化 `current`（¶1）；
- 跨类型转换构造/赋值：约束同 `reverse_iterator`（¶2–¶6）；
- `base() const&` 返回 `const Iterator&`，`base() &&` 移出（[move.iter.op.conv]）；
- `operator*`：`return ranges::iter_move(current);`（[move.iter.elem] ¶1）；
- `operator[](n)`：`return ranges::iter_move(current + n);`（¶2）。

## 导航（[move.iter.nav]）

`++`、`--`、`+`、`+=`、`-`、`-=` 都直接作用于 `current`。两个值得注意的后置运算符：

```cpp
constexpr void operator++(int);                                        // ¶3：++current
move_iterator operator++(int) requires forward_iterator<Iterator> = default;
move_iterator operator--(int) = default;
```

- 对**单遍**迭代器，后置 `++` 返回 `void`：返回旧值的副本对输入迭代器没有意义（副本在 `++` 之后就失效了），而且底层可能是仅移动的类型。
- 对前向及以上的迭代器，后置 `++`/`--` 是**预置**（*defaulted*）的——这是 C++26 之后核心语言新增的能力（[[over.inc.default]]）：预置的后置递增等价于"复制 `*this`、前置递增、返回副本"。在此之前，标准用散文写出同样的效果。

## 比较与非成员函数（[move.iter.op.comp]、[move.iter.nonmember]）

- `==`、`<`、`>`、`<=`、`>=`：都比较 `base()`，每个都带有 *Constraints*（对应 `base()` 表达式良构且可转换为 `bool`）；`<=>` 要求 `three_way_comparable_with`。
- 与 `move_sentinel<S>` 的 `==`（隐藏友元，要求 `sentinel_for<S, Iterator>`）与 `-`（要求 `sized_sentinel_for`）。
- `x - y` 返回 `x.base() - y.base()`；`n + x` 要求 `x.base() + n` 良构且类型为 `Iterator`（¶2）。
- `iter_move(i)` 转发给 `ranges::iter_move(i.current)`；`iter_swap` 转发给 `ranges::iter_swap`。
- `make_move_iterator(i)` 返回 `move_iterator<Iterator>(std::move(i))`。

与 `reverse_iterator` 一样，概要对 `move_iterator<I1>` 与 `move_iterator<I2>` 特化了 `disable_sized_sentinel_for`（底层不建模 `sized_sentinel_for` 时为 `true`）。

## `move_sentinel`（[move.sentinel]、[move.sent.ops]）

¶1：哨位适配器，与 `move_iterator` 一起表示范围：若 `I` 与 `S` 建模 `sentinel_for<S, I>`，则 `move_sentinel<S>` 与 `move_iterator<I>` 建模 `sentinel_for<move_sentinel<S>, move_iterator<I>>`。¶2 例 1 用它和 `ranges::copy_if` 实现了 `move_if`：

```cpp
template<input_iterator I, sentinel_for<I> S, weakly_incrementable O,
         indirect_unary_predicate<I> Pred>
  requires indirectly_movable<I, O>
void move_if(I first, S last, O out, Pred pred) {
  ranges::copy_if(move_iterator<I>{std::move(first)}, move_sentinel<S>{last},
                  std::move(out), pred);
}
```

`move_sentinel<S>` 只是把 `S` 存在私有成员 `last` 中：默认构造值初始化 `last`（且若 `S` 可平凡默认构造则为 constexpr，¶1）；显式从 `S` 构造；可从 `move_sentinel<S2>` 转换与赋值；`base()` 返回 `last`。它要求 `semiregular<S>`。

之所以需要单独的哨位适配器：`move_iterator` 的比较运算符都只与另一个 `move_iterator` 比较 `base()`；让它直接接受任意 `S` 会使比较运算符过于宽泛。包一层 `move_sentinel` 后，"这是移动范围的终点"在类型上一目了然，`sentinel_for` 关系也能从 `S` 与 `I` 自然地传递过来。

## 陷阱：解引用两次

```cpp run title="move_twice.cpp" ok
#include <algorithm>
#include <cstdio>
#include <iterator>
#include <string>
#include <vector>

int main() {
    std::vector<std::string> src{"apple", "banana", "cherry"};
    std::vector<std::string> dst;
    // 谓词按值接收：第一次解引用就把元素移进了参数 s
    std::copy_if(std::make_move_iterator(src.begin()), std::make_move_iterator(src.end()),
                 std::back_inserter(dst),
                 [](std::string s) { return s.size() > 5; });
    // 谓词判定为真的元素随后被第二次解引用、"移动"到 dst——此时它已经是空串
    std::printf("dst.size=%zu dst[0]=\"%s\" src[1]=\"%s\"\n",
                dst.size(), dst[0].c_str(), src[1].c_str());
    // libc++ 输出：dst.size=2 dst[0]="" src[1]=""
}
```

程序本身没有 UB（被移走的 `string` 处于有效但未指明状态，[[lib.types.movedfrom]]），但结果显然不是想要的。`copy_if` 对每个元素先调用 `pred(*it)`，再 `*out = *it`——两次解引用。规则是：**只有当算法保证对每个元素只解引用一次（或谓词以 `const&` 接收）时，才能用 `move_iterator`**。上例把 lambda 参数改成 `const std::string&` 即可。

`indirect_unary_predicate` 概念挡不住这个错误：它只要求谓词可以用 `iter_reference_t`（`string&&`）和 `iter_value_t&`（`string&`）调用，按值接收两者都满足。

## 思考题

!!! question "思考题"
    1. `std::vector<std::unique_ptr<int>> v2(std::make_move_iterator(v1.begin()), std::make_move_iterator(v1.end()));` 能编译吗？为什么容器构造函数可以安全地使用 `move_iterator`？
    2. 为什么 `move_iterator` 的 `iterator_concept` 不能是 `contiguous_iterator_tag`，即便底层是 `T*`？

<details markdown="1">
<summary>展开查看答案与解析</summary>

1. 能。容器的迭代器对构造函数对每个元素只解引用一次（逐个构造元素），而 `iterator_category` 是随机访问，实现还能先算出距离、一次分配。`unique_ptr` 只能移动，这正是 `move_iterator` 的典型用途。
2. `contiguous_iterator` 要求 `iter_reference_t` 是左值引用（[[iterator.concept.contiguous]]），而 `move_iterator<T*>` 的引用是 `T&&`。更本质地，连续迭代器允许库换成指针操作（[[iterator.requirements.general#13]]），而换成 `T*` 就丢失了"移动"语义——库会复制而不是移动。
</details>

## 小结

!!! summary
    - `*it` = `ranges::iter_move(current)`；`reference` = `iter_rvalue_reference_t`；`operator->` 已弃用。
    - 类别封顶随机访问；输入迭代器的后置 `++` 返回 `void`；前向以上的后置 `++`/`--` 是预置函数。
    - `move_sentinel<S>` 让移动迭代器与任意哨位配对。
    - 只对"每个元素只解引用一次"的算法使用 `move_iterator`；谓词按值接收会提前偷走元素。
