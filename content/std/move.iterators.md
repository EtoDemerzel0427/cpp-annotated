---
title: move_iterator 与 move_sentinel
summary: move_iterator 的解引用返回右值引用，让本来复制元素的算法和构造函数改为移动；move_sentinel 让它能与任意哨位配对。
status: done
covers: *
since: c++11
related: predef.iterators, iterator.cust, alg.req, reverse.iterators, iterator.concept.sentinel, over.inc.default, lib.types.movedfrom
tags: 标准库, 迭代器, 适配器, 移动语义
updated: 2026-10-19
---

!!! tldr
    - `*it` 等价于 `ranges::iter_move(current)`，对 `T*` 得到 `T&&`，所以用 `move_iterator` 调用复制类的算法或构造函数，元素会被移动。
    - 它最高是随机访问迭代器，不会是连续迭代器；`operator->` 已弃用。
    - 对单遍的输入迭代器，后置 `++` 返回 `void`。
    - `move_sentinel<S>` 把任意哨位包成移动范围的终点。
    - 只能交给对每个元素只解引用一次的算法；`copy_if` 的谓词按值接收参数时，元素会在判断阶段就被移走。

## 用途 [move.iterators.general]

¶1 `move_iterator` 是一个迭代器适配器，行为与底层迭代器相同，只是解引用的结果变成右值。很多泛型算法和构造函数只会写 `*out = *it`，把这样的迭代器交给它们，复制就变成了移动。¶2 是标准的例子：

<div class="compare" markdown="1">

```cpp
list<string> s;
// 复制每个 string
vector<string> v1(s.begin(), s.end());
```

```cpp
// 移动每个 string
vector<string> v2(
  make_move_iterator(s.begin()),
  make_move_iterator(s.end()));
```

</div>

`vector` 的迭代器对构造函数只对每个元素解引用一次，所以移动是安全的。只能移动的类型也能这样搬运，例如把一个 `vector<unique_ptr<int>>` 的元素移到另一个 `vector` 里。

## 类定义 [move.iterator]

```cpp
template<class Iterator>
class move_iterator {
public:
  using iterator_type     = Iterator;
  using iterator_concept  = see below;
  using iterator_category = see below;  // 不总是存在
  using value_type        = iter_value_t<Iterator>;
  using difference_type   = iter_difference_t<Iterator>;
  using pointer           = Iterator;
  using reference         = iter_rvalue_reference_t<Iterator>;
  // ...
private:
  Iterator current = Iterator();        // 说明专用
};
```

`reference` 是 `iter_rvalue_reference_t<Iterator>`，即 `ranges::iter_move(*it)` 的结果类型（[[iterator.cust]]）。对 `T*` 它是 `T&&`；对自定义了 `iter_move` 的代理迭代器（解引用返回一个行为像引用的类对象，例如 `views::zip` 的迭代器），它是代理自己定义的右值形式。

类定义里没有 `operator->`。它在附录 D 的 [[depr.move.iter.elem]] 中 {{deprecated}}，返回 `current`。通过 `->` 访问成员得到的是左值，与解引用得到右值的语义不一致。

### 类别最高到随机访问（¶1–¶2）

¶1 `iterator_concept` 按底层依次判断 random access、bidirectional、forward，都不满足时为 input。它不会是 `contiguous_iterator_tag`，因为连续迭代器要求引用是左值引用（[[iterator.concept.contiguous]]）。

¶2 只有 `iterator_traits<Iterator>::iterator_category` 有效时才声明 `iterator_category`。底层类别派生自 `random_access_iterator_tag` 时它是 `random_access_iterator_tag`，否则照搬底层的类别。也就是说，对 C++17 风格的接口它仍然申报为随机访问。容器的构造函数据此可以先算出元素个数、一次分配好内存。

## 操作

[move.iter.requirements] ¶1 要求 `Iterator` 满足 *Cpp17InputIterator* 或建模 `input_iterator`。双向、随机访问的操作只有在被实例化时，才要求底层满足相应的要求。

| 操作 | 效果 | 出处 |
|---|---|---|
| 默认构造 | 仅当底层可默认初始化时存在 | 类定义 |
| `explicit move_iterator(Iterator i)` | 用 `std::move(i)` 初始化 `current` | [move.iter.cons] ¶1 |
| 从 `move_iterator<U>` 转换、赋值 | `U` 与 `Iterator` 不同且可转换 | [move.iter.cons] ¶2–¶6 |
| `base() const&` / `base() &&` | 返回 `const Iterator&` / 移出 | [move.iter.op.conv] |
| `*it` | `ranges::iter_move(current)` | [move.iter.elem] ¶1 |
| `it[n]` | `ranges::iter_move(current + n)` | [move.iter.elem] ¶2 |
| `++`、`--`、`+`、`+=`、`-`、`-=` | 作用于 `current` | [move.iter.nav] |
| `==`、`<`、`<=>` 等 | 比较 `base()`，各自有约束 | [move.iter.op.comp] |
| `x - y` | `x.base() - y.base()` | [move.iter.nonmember] ¶1 |
| `iter_move`、`iter_swap` | 转发给 `ranges::iter_move`、`ranges::iter_swap` | [move.iter.nonmember] ¶4–¶5 |
| `make_move_iterator(i)` | `move_iterator<Iterator>(std::move(i))` | [move.iter.nonmember] ¶6 |

后置递增和递减的声明值得单独看：

```cpp
constexpr void operator++(int);  // [move.iter.nav] ¶3
move_iterator operator++(int)
  requires forward_iterator<Iterator> = default;
move_iterator operator--(int) = default;
```

对单遍的输入迭代器，后置 `++` 返回 `void`。递增之后旧位置的副本已经失效，返回它没有意义，而且底层迭代器可能只能移动。

对前向及以上的迭代器，后置 `++` 和 `--` 声明为 `= default`。预置的后置递增等价于复制 `*this`、执行前置递增、返回副本（[[over.inc.default]]）。

比较运算符的约束都写成 *Constraints*：对应的 `x.base() == y.base()` 等表达式要良构且能转换为 `bool`。和 `reverse_iterator` 一样，概要对两个 `move_iterator` 特化了 `disable_sized_sentinel_for`，底层不建模 `sized_sentinel_for` 时它为 `true`。

## move_sentinel [move.sentinel]

`move_iterator` 的比较运算符只接受另一个 `move_iterator`。C++20 的范围可以用不同类型的哨位作为终点，于是需要一个配套的哨位适配器。

¶1 如果 `sentinel_for<S, I>` 成立，那么 `sentinel_for<move_sentinel<S>, move_iterator<I>>` 也成立。`move_iterator` 有对应的隐藏友元 `==`（要求 `sentinel_for<S, Iterator>`）和 `-`（要求 `sized_sentinel_for`）。

¶2 标准用它配合 `ranges::copy_if` 写出了一个 `move_if`：

```cpp
template<input_iterator I, sentinel_for<I> S,
         weakly_incrementable O,
         indirect_unary_predicate<I> Pred>
  requires indirectly_movable<I, O>
void move_if(I first, S last, O out, Pred pred) {
  ranges::copy_if(move_iterator<I>{std::move(first)},
                  move_sentinel<S>{last},
                  std::move(out), pred);
}
```

`move_sentinel<S>` 要求 `semiregular<S>`，只是把 `S` 存在私有成员 `last` 里。[move.sent.ops] ¶1 默认构造值初始化 `last`，`S` 可平凡默认构造时这个构造函数是 constexpr；¶2 显式从 `S` 构造；¶3–¶4 可以从 `move_sentinel<S2>` 转换和赋值；¶5 `base()` 返回 `last`。

## 陷阱：同一元素解引用两次

```cpp run title="move_twice.cpp" ok
#include <algorithm>
#include <cstdio>
#include <iterator>
#include <string>
#include <vector>

int main() {
  std::vector<std::string> src{"apple", "banana", "cherry"};
  std::vector<std::string> dst;
  std::copy_if(std::make_move_iterator(src.begin()),
               std::make_move_iterator(src.end()),
               std::back_inserter(dst),
               [](std::string s) { return s.size() > 5; });
  std::printf("%zu \"%s\" \"%s\"\n",
              dst.size(), dst[0].c_str(), src[1].c_str());
}
```

本机 libc++ 输出 `2 "" ""`：`dst` 里有两个元素，却都是空串。`copy_if` 对每个元素先调用 `pred(*it)`，再执行 `*out = *it`，解引用了两次。谓词按值接收参数，第一次解引用时元素已经被移进参数 `s`，第二次移到 `dst` 的是被移走后的空串。

程序本身没有 UB，被移走的 `string` 处于有效但未指定的状态（[[lib.types.movedfrom]]），但结果显然不对。把 lambda 的参数改成 `const std::string&`，第一次解引用就只是绑定引用，不会移动。

`indirect_unary_predicate` 挡不住这个错误。它只要求谓词能用 `iter_reference_t`（这里是 `string&&`）和 `iter_value_t&`（`string&`）调用，按值接收的参数两者都能接受。所以一般规则是：只把 `move_iterator` 交给保证每个元素只解引用一次的算法，或者让谓词按 `const&` 接收。

## 思考题

!!! question "思考题"
    底层是 `T*` 时，`move_iterator<T*>` 的 `iterator_concept` 为什么也不能是 `contiguous_iterator_tag`？

<details markdown="1">
<summary>答案</summary>

`contiguous_iterator` 要求 `iter_reference_t` 是左值引用（[[iterator.concept.contiguous]]），而 `move_iterator<T*>` 的引用类型是 `T&&`。从设计上看，连续迭代器允许库把它换成指针来操作（`to_address`），换成 `T*` 之后解引用得到的是左值，库就会复制而不是移动，移动的语义就丢了。
</details>
