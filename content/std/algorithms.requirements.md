---
title: 算法要求
summary: 整个算法库共用的规则：模板形参的名字表示类型要求，谓词不得通过实参修改对象、对 const 实参必须给出同样的结果，算法可以随意复制函数对象，ranges 算法是 ADL 找不到的函数对象，给经典算法显式指定模板实参的效果是未指定的。
status: done
papers: P0896R4, P2408R5, P3136R1
related: algorithms, alg.req, iterator.requirements, iterator.concepts, customization.point.object, res.on.functions, function.objects, concept.booleantestable, basic.lookup.argdep
tags: 标准库, 算法, 谓词, niebloid, ADL, 迭代器要求
updated: 2026-10-19
---

!!! tldr
    - 经典算法的模板形参不带约束，形参名 `InputIterator`、`ForwardIterator`、`Predicate` 等就是要求。传入不满足要求的类型是未定义行为，编译器不一定报错。
    - 谓词不能通过实参修改元素，而且对同一个元素的 const 左值必须给出相同结果。形参写成 `int&` 的谓词不满足要求。
    - 算法可以随意复制函数对象。需要保留函数对象的状态时，传 `std::ref(f)`。
    - `std::ranges` 里的算法是对象而不是函数：ADL 找不到它们，非限定查找找到它们时会关闭 ADL，也不能给它们写显式模板实参。
    - 条文里对前向迭代器写的 `first + n`、`last - first` 只是记法，表示逐步移动、逐个计数。

后面一百多个算法的条文都很短，例如 `find_if` 只写了 *Returns* 和 *Complexity*。之所以能这么短，是因为 `ForwardIterator` 必须满足什么、`Predicate` 能做什么、`a + n` 对前向迭代器是什么意思，都在 [algorithms.requirements] 统一规定了。

¶1 算法与数据结构的实现分离，以迭代器类型为参数，所以只要程序定义的数据结构提供满足要求的迭代器，就能使用这些算法。

## 形参名就是要求（¶4）

经典算法的声明里没有任何约束：

```cpp
template<class ForwardIterator, class T>
  void fill(ForwardIterator first, ForwardIterator last, const T& value);
```

¶4 规定，模板形参不带约束时，用形参的名字表示类型要求：

| 形参名 | 模板实参必须 |
|---|---|
| `InputIterator`、`InputIterator1`、`InputIterator2` | 满足 *Cpp17InputIterator*（¶4.2） |
| `OutputIterator`、`OutputIterator1`、`OutputIterator2` | 满足 *Cpp17OutputIterator*（¶4.3） |
| `ForwardIterator`、`ForwardIterator1`、`ForwardIterator2`、`NoThrowForwardIterator` | 需要可写时满足 *Cpp17ForwardIterator*，否则建模 `forward_iterator`（¶4.4） |
| `BidirectionalIterator…` | 需要可写时满足 *Cpp17BidirectionalIterator*，否则建模 `bidirectional_iterator`（¶4.6） |
| `RandomAccessIterator…` | 需要可写时满足 *Cpp17RandomAccessIterator*，否则建模 `random_access_iterator`（¶4.7） |

*Cpp17ForwardIterator* 这类名字是旧式的具名要求（[[iterator.requirements]]），`forward_iterator` 是 C++20 的迭代器概念（[[iterator.concepts]]），两者不完全相同。¶4.1 规定，算法的 *Effects* 要修改迭代器所指的值时，这个迭代器必须是可变迭代器，也就是能通过它写入。¶4.5 对 `NoThrowForwardIterator` 另外要求，自增、赋值、比较和解引用有效的迭代器时都不抛异常。

违反这些要求的后果由 [[res.on.functions]] 规定：标准库模板的实参不满足要求时，行为未定义。所以经典算法用错了迭代器，可能编译通过、运行出错。注 1 说明，这些按名字的规则不影响带约束的形参，`ranges` 算法的要求由概念直接写出。

### 只读的算法接受 C++20 迭代器

¶4.4、¶4.6、¶4.7 的后半句"否则建模 C++20 概念"来自 C++23 的 [[P2408R5]]。

C++20 的许多视图，例如 `views::iota(0, n)`、`views::transform`，迭代器的解引用结果是纯右值，不是引用。它们满足 C++20 的 `random_access_iterator`，但不满足 *Cpp17ForwardIterator*，因为后者要求解引用得到真正的引用。在 P2408 之前，把这样的迭代器传给 `std::find` 严格说是未定义行为。现在，不需要写入的算法只要求迭代器建模相应的 C++20 概念。

需要写入时仍然要求 *Cpp17* 版本，因为经典算法的实现大量依赖解引用得到真正的引用，例如对 `*a`、`*b` 调用 `swap`，而 C++20 的概念不保证这一点。`InputIterator` 没有这样的放宽：C++20 的 `input_iterator` 可以是只能移动的类型，而经典算法会复制迭代器。

## 谓词的契约（¶6–¶8）

```cpp
std::vector<int> v{1, 2, 3};
auto it = std::find_if(v.begin(), v.end(),
                       [](int& x) { return x == 2; });  // 不满足 ¶6
```

这段代码在本机 libc++ 上能编译，也能找到 2，但它不满足标准对 `Predicate` 的要求。¶6 对接受 `Predicate pred` 的算法规定了三件事（`first` 是迭代器实参，值类型为 `T`）：

1. `pred(*first)` 是良构的，返回类型建模 *boolean-testable*（[[g:boolean-testable]]）。也就是说返回类型不必是 `bool`，但要能像 `bool` 一样用在 `!`、`&&`、`||` 中（[[concept.booleantestable]]）。
2. `pred` 不能通过实参调用任何非 const 函数，也就是不能通过实参修改元素。
3. 对于和 `*first` 指代同一个对象、类型为 `T` 或 `const T` 的泛左值 `u`，`pred(u)` 必须是有效的表达式，而且结果等于 `pred(*first)`。

第 3 条允许实现以 const 左值的形式把元素交给谓词，或者先把元素放进一个局部变量再调用谓词。上面的 lambda 不接受 `const int`，违反了第 3 条。它能编译，只是因为 libc++ 恰好传了非 const 左值；按 [[res.on.functions]]，这是未定义行为。

`ranges::find_if` 也不会拒绝这个 lambda。它的约束 `indirect_unary_predicate` 只检查谓词能否以 `iter_value_t<I>&` 和 `iter_reference_t<I>` 调用（[[indirectcallable]]），对非 const 的 `vector<int>` 来说两者都是 `int&`。只有把它用在 `const vector<int>` 上时，约束检查才会失败。

¶7 对 `BinaryPredicate` 作了对应的规定：`binary_pred(*first1, *first2)` 良构且返回类型建模 *boolean-testable*，不得通过实参修改对象，对 const 实参给出相同的结果。另外，除非另有规定，第一个实参总是来自第一个序列；签名里有 `T value` 时，调用形式是 `binary_pred(*first1, value)`。

实参顺序固定，对异构比较有用：可以写一个只接受 `(Elem, Key)` 顺序的谓词。`std::upper_bound` 属于另有规定的情形，它调用的是 `comp(value, *i)`（[[alg.binary.search]]）。

¶8 `UnaryOperation`、`BinaryOperation` 等形参只要求是函数对象（[[function.objects]]），没有 ¶6、¶7 的不可修改要求。具体的算法会在自己的 *Preconditions* 里另加限制，例如 `transform` 要求 `op` 不修改区间里的元素（[[alg.transform#2]]）。

¶10 条文用 `*first == value` 这样的表达式作为条件时，它在布尔语境下必须求值为 `true` 或 `false`。

## 函数对象可以被复制（¶9）

```cpp run title="ref.cpp" ok
#include <algorithm>
#include <cassert>
#include <functional>
#include <vector>

struct Counter {
  int calls = 0;
  bool operator()(int x) { ++calls; return x % 2 == 0; }
};

int main() {
  std::vector<int> v{5, 3, 8, 1, 9, 2, 7, 4, 6, 0};
  Counter c;
  (void)std::count_if(v.begin(), v.end(), c);
  assert(c.calls == 0);            // 算法用的是 c 的副本
  (void)std::count_if(v.begin(), v.end(), std::ref(c));
  assert(c.calls == 10);           // 通过引用调用 c 本身
}
```

算法按值接收函数对象，调用方手里的 `c` 不会改变。¶9 的注 2 更进一步：除非另有规定，接受函数对象的算法可以随意复制它们，标准不限制复制的次数。所以依赖函数对象内部累积状态的写法不可移植。需要保留同一个对象时，传 `std::reference_wrapper`（[[refwrap]]），如上例的 `std::ref(c)`。

`for_each` 是另有规定的例子：非并行的 `std::for_each` 把函数对象返回给调用方，`ranges::for_each` 在返回值的 `fun` 成员里带回它（[[alg.foreach]]）。

注意 `Counter::operator()` 修改的是谓词自己的状态，不是实参，所以不违反 ¶6 的第 2 条。但 `ranges` 版本要求谓词建模 `predicate`，其中包含相等性保持：相同的输入必须得到相同的结果。像 `Counter` 这样带状态、每次结果可能不同的谓词，在 `ranges` 算法里属于满足语法要求但不建模概念，同样是未定义行为。

## 不得偷偷写入（¶3）

!!! std
    For purposes of determining the existence of data races, algorithms shall not modify objects referenced through an iterator argument unless the specification requires such modification.

两个线程同时对同一个 `vector` 调用 `std::find` 或 `std::count` 不构成数据竞争（[[intro.races]]）。实现不能为了加速而临时改写元素，比如在末尾放一个哨兵值、查找结束后再恢复。

## `ranges` 算法是对象（¶2）

¶2 规定，本章在 `std::ranges` 中以函数模板形式描述的实体都是**算法函数对象**（[[g:algorithm-function-object]]）。条文里写的

```cpp
template<input_iterator I, sentinel_for<I> S, class Proj = identity, ...>
  constexpr I ranges::find(I first, S last, const T& value, Proj proj = {});
```

只是一种描述方式。`std::ranges::find` 实际上是一个对象，它的 `operator()` 重载与这些模板一一对应。[[alg.func.obj]] 把它定义为一种**定制点对象**（[[g:customization-point-object]]）。这带来几个可以观察到的后果：

- ADL 找不到它们。
- 非限定名字查找找到它们时，因为找到的是对象而不是函数，ADL 不再进行（[[basic.lookup.argdep]]）。
- 它们可以像普通对象一样复制、传递。
- 不能给它们写显式模板实参：`std::ranges::sort<std::vector<int>&>(v)` 是非良构的，本机 Clang 报 'sort' does not name a template but is followed by template arguments。

```cpp run title="niebloid.cpp" ok
#include <algorithm>
#include <cassert>
#include <vector>

namespace lib {
  struct Widget { int id; };
  bool operator==(Widget a, Widget b) { return a.id == b.id; }
  // 同名函数模板，只能通过 ADL 找到
  template<class It, class T>
  It find(It f, It, const T&) { return f; }
}

int main() {
  std::vector<lib::Widget> v{{1}, {2}, {3}};
  using namespace std::ranges;
  auto it = find(v.begin(), v.end(), lib::Widget{3});
  assert(it == v.end() - 1);   // 调用的是 ranges::find

  auto sorter = std::ranges::sort;  // 可以复制、传递
  std::vector<int> w{3, 1, 2};
  sorter(w);
  assert((w == std::vector<int>{1, 2, 3}));
}
```

非限定查找通过 using 指令找到了对象 `std::ranges::find`，ADL 随之关闭，`lib::find` 和 `std::find` 都没有成为候选。经典的 `std::sort` 是函数模板，情况相反：

```cpp run title="adl.cpp" error
#include <algorithm>
#include <vector>
int main() {
  std::vector<int> v{3, 1, 2};
  sort(v.begin(), v.end());  // OK：ADL 找到 std::sort
  sort(v);                   // error: ranges::sort 不会被 ADL 找到
}
```

`vector` 的迭代器关联到命名空间 `std`，所以不写 `std::` 也能通过 ADL 调用 `std::sort`。`sort(v)` 期望的是 `ranges::sort`，ADL 找不到它，而 `std::sort` 没有单个实参的重载。

这类对象在社区里常叫做 niebloid，名字来自 Eric Niebler。C++20 只规定了它们不被 ADL 找到、找到时关闭 ADL，实现普遍用对象来满足。C++26 的 [[P3136R1]] 把它们正式定义为定制点对象，于是它们也有了定制点对象的其他性质（[[customization.point.object]]）。

## 显式模板实参（¶15）

!!! std
    The well-formedness and behavior of a call to an algorithm with an explicitly-specified template argument list is unspecified, except where explicitly stated otherwise.

注 4 解释了原因：实现声明算法时，模板形参可以与标准列出的不同，比如多一个默认模板实参，或者调整顺序。所以 `std::find<std::vector<int>::iterator, int>(...)` 能否编译、做什么，都是{{unspec}}。

明确规定的例外是 `std::min`、`std::max`、`std::minmax`：[[alg.min.max]] 的 *Remarks* 允许为 `T` 显式指定实参，`std::max<long>(1, 2L)` 是常见的写法。

## `a + n` 与 `b - a` 只是记法（¶11–¶13）

条文为了简洁，对不支持算术运算的迭代器也写 `first + n`、`last - first`。¶11 规定了它们的含义：

- `a + n` 等价于复制 `a`，再自增（`n` 为负时自减）`|n|` 次；
- `[a, b)` 是区间时，`b - a` 等价于从 `a` 数到 `b` 的步数；`[b, a)` 是区间时结果为负；
- 迭代器 `i` 和哨位 `s` 来自同一个范围 `r` 时，`s - i` 的类型和值与 `ranges::distance(i, s)` 相同。注 3 允许实现在结果相同时改用 `ranges::distance(r)`，对知道自身大小的范围这只需常数时间。

所以复杂度条款里的"`last - first` 次比较"对前向迭代器也有意义，但它不代表算法真的计算了这个减法。复杂度条款只统计它点名的操作，比如谓词调用次数。

¶12 `n` 是类整数类型、但不是迭代器的差类型 `D` 时，`a + n` 的意思是 `a + D(n)`。¶13 描述返回值时，有时在需要迭代器的地方写了一个哨位 `s`，意思是 `ranges::next(i, s)`。这就是 `ranges::sort(first, sentinel)` 返回一个迭代器而不是哨位的原因。

## 范围重载怎样转发（¶14）

!!! std
    Overloads of algorithms that take range arguments behave as if they are implemented by dispatching to the overload in namespace `ranges` that takes separate iterator and sentinel arguments

对每个范围实参 `r`，对应的迭代器实参是 `ranges::begin(r)`，哨位实参是 `ranges::end(r)` 或 `ranges::begin(r) + N`，其中 `N` 等于 `ranges::distance(r)`。后一种写法对知道大小、但首尾类型不同的范围有用：它得到一个与 `begin` 同类型的终点，可以满足要求 `sized_sentinel_for` 的重载，例如 C++26 的并行 `ranges` 重载。

范围重载的返回类型里常见 `borrowed_iterator_t<R>`。实参是会在调用结束时销毁的临时范围时，这个类型是 `ranges::dangling`，使用返回的迭代器就会编译失败，见 [[algorithms.results]]。

## 命名约定（¶5）

有些算法同时提供原地版本和复制版本，复制版本叫 *algorithm*`_copy`。接受谓词的版本加后缀 `_if`，放在 `_copy` 之后，如 `remove_copy_if`。脚注 179 解释了为什么没有 `sort_copy`：操作本身的代价远大于复制时，不提供复制版本，用户自己先 `copy` 再 `sort` 即可。

## 思考题

!!! question "思考题 1"
    `std::count_if(v.begin(), v.end(), [n = 0](int) mutable { return ++n % 2 == 0; })` 在不同实现上一定返回相同的结果吗？

<details markdown="1">
<summary>答案</summary>

不一定。¶9 允许算法随意复制函数对象，如果实现复制了谓词、对不同的元素使用不同的副本，计数就会分叉。实际的实现都只用一个副本，但标准不保证。更根本的问题是，这个谓词对同一个元素调用两次会得到不同的结果，违反了 ¶6 对 `pred(u)` 等于 `pred(*first)` 的要求，是未定义行为。
</details>

!!! question "思考题 2"
    在全局作用域写了 `using std::ranges::sort;` 之后，`sort(v.begin(), v.end())` 调用的是哪个函数？

<details markdown="1">
<summary>答案</summary>

using 声明引入了对象 `std::ranges::sort`。非限定查找找到的是对象，按 [[basic.lookup.argdep]] 不再进行 ADL，`std::sort` 不会成为候选。调用的是 `ranges::sort` 接受迭代器和哨位的重载。改成 `using std::sort;` 则调用 `std::sort`。
</details>

## 小结

| 规则 | 段落 | 违反的后果 |
|---|---|---|
| 形参名决定迭代器要求；只读时建模 C++20 概念即可 | ¶4 | {{ub}} |
| 谓词：返回值可当 `bool` 用，不经实参修改对象，对 const 实参结果相同 | ¶6–¶7 | {{ub}} |
| 算法可以随意复制函数对象；需要同一个对象时用 `std::ref` | ¶9 | |
| 算法不得写入规范没有要求写入的对象 | ¶3 | 实现的义务 |
| `ranges` 算法是算法函数对象，ADL 找不到，找到时关闭 ADL | ¶2 | |
| 给经典算法显式指定模板实参 | ¶15 | {{unspec}}（`min`、`max` 例外） |
| `a + n`、`b - a` 是记法 | ¶11–¶13 | |
