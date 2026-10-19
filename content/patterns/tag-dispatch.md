---
title: 标签分派：从重载到 concepts
summary: 在编译期按类型的性质挑选实现的四种写法：迭代器分类标签、enable_if、if constexpr、按约束重载，它们各自依赖哪条语言规则、错误信息长什么样、编译多花多少时间，以及标准库为什么到处用空的标签类型代替 bool 形参。
status: draft
order: 75
since: c++98
papers: P2593R1, P0722R3, P1206R7, LWG2510
related: std.iterator.tags, over.ics.rank, over.best.ics, stmt.if, temp.res.general, temp.deduct.general, temp.constr.order, temp.func.order, iterator.concepts.general, pair.piecewise, utility.syn, new.syn, expr.delete, flat.map.cons, execpol, topics/concepts, topics/compile-time-programming, topics/overload-resolution-walkthrough, patterns/strong-types, patterns/named-parameters
tags: 标签分派, SFINAE, if constexpr, 概念, 重载决议, 模式
updated: 2026-10-19
---

!!! tldr
    - 标签分派把类型的性质编码成一个空类，再用重载决议挑函数。标签之间用继承表示细化关系，派生类到最近基类的转换比到更远基类的转换好，所以总是选中最具体的版本。
    - `enable_if` 把条件写进函数签名，替换失败时候选被丢掉。代价是重载之间的条件必须手工写成互斥，替换失败也只在直接语境里才算数。
    - `if constexpr` 把分支收进一个函数体，未选中的分支在模板实例化时被丢弃。被丢弃的只是依赖模板形参的部分，不依赖模板形参的代码照样要正确。
    - 按约束重载用概念的包含关系排序，入口本身带约束，`requires` 表达式能如实回答能不能调用。用标准库的迭代器概念时，编译期开销明显高于前三种。
    - 标准库的 `in_place_t`、`piecewise_construct_t`、`from_range_t`、`sorted_unique_t` 等都是空的标签类型：它们在编译期选中另一个构造函数或另一种语义，这是 `bool` 形参做不到的。

## 同一个操作，两种算法

把迭代器向前移动 `n` 步，最朴素的写法是循环 `n` 次 `++it`。这对任何迭代器都成立，但对 `std::vector` 的迭代器是浪费：它支持 `it += n`，一步就到。

反过来，直接写 `it += n` 又不行，`std::list` 的迭代器没有 `+=`，代码编译不过。我们需要在编译期根据迭代器类型的性质，在两份实现之间选一份，并且没被选中的那份不能参与编译。

标准库的 `std::advance` 和 `std::distance` 就是这样规定的：随机访问迭代器用 `+`、`-`，常数时间；其他迭代器用 `++`，线性时间（[[iterator.operations#1]]）。下面用同一个 `my_advance` 写四遍，比较每种写法靠的是哪条语言规则。

## 写法一：标签分派

```cpp run title="tag-dispatch.cpp" ok
#include <cstdio>
#include <forward_list>
#include <iterator>
#include <list>
#include <vector>

namespace detail {
template<class It, class D>
constexpr void advance(It& it, D n, std::input_iterator_tag) {
  std::puts("input: ++ n times");
  while (n-- > 0) ++it;
}
template<class It, class D>
constexpr void advance(It& it, D n, std::bidirectional_iterator_tag) {
  std::puts("bidirectional: ++ or --");
  if (n >= 0) while (n-- > 0) ++it;
  else        while (n++ < 0) --it;
}
template<class It, class D>
constexpr void advance(It& it, D n, std::random_access_iterator_tag) {
  std::puts("random access: +=");
  it += n;
}
}  // namespace detail

template<class It, class D>
constexpr void my_advance(It& it, D n) {
  using Cat = typename std::iterator_traits<It>::iterator_category;
  detail::advance(it, n, Cat{});   // 按类型选重载，Cat{} 只是一个空对象
}

int main() {
  std::vector<int> v{1, 2, 3, 4, 5};
  std::list<int> l(v.begin(), v.end());
  std::forward_list<int> f(v.begin(), v.end());
  auto a = v.begin(); my_advance(a, 3);   // random access
  auto b = l.end();   my_advance(b, -2);  // bidirectional
  auto c = f.begin(); my_advance(c, 2);   // forward → input
  int* p = v.data();  my_advance(p, 4);   // 指针：random access
  std::printf("%d %d %d %d\n", *a, *b, *c, *p);
}
```

输出依次是 `random access`、`bidirectional`、`input`、`random access`，最后一行 `4 4 3 5`。

每个迭代器类型都通过 `iterator_traits<It>::iterator_category` 声明自己属于哪一类，这个成员类型叫**迭代器分类标签**（[[g:iterator-category-tag|iterator category tag]]，[[std.iterator.tags#1]]）。标签本身是空类，不带任何数据，它唯一的用处是它的类型。

`my_advance` 构造一个标签对象，把它作为第三个实参传给三个重载的 `detail::advance`。编译器做的是普通的重载决议：哪个重载的第三个形参类型能从 `Cat` 转换过来、转换得最好，就选哪个。没被选中的重载根本不会实例化，所以 `list` 的迭代器永远不会碰到 `it += n`。

### 为什么标签要继承

标准库的标签之间有继承关系（[[std.iterator.tags#1]]）：

```cpp
struct input_iterator_tag { };
struct forward_iterator_tag : input_iterator_tag { };
struct bidirectional_iterator_tag : forward_iterator_tag { };
struct random_access_iterator_tag : bidirectional_iterator_tag { };
struct contiguous_iterator_tag : random_access_iterator_tag { };
```

`forward_list` 的标签是 `forward_iterator_tag`，上面并没有为它写重载。调用照样成功，因为实参类型是形参类型的派生类时，隐式转换序列是一次**派生类到基类的转换**，等级是 Conversion（[[over.best.ics#7]]）。前向迭代器因此自动退回到输入迭代器的算法，不必为每个分类都写一个重载。

当多个重载都可行时，继承还决定了谁胜出：

```cpp run title="nearest-base.cpp" ok
#include <cstdio>
#include <iterator>

void pick(std::input_iterator_tag)         { std::puts("input"); }
void pick(std::bidirectional_iterator_tag) { std::puts("bidirectional"); }
void pick(std::random_access_iterator_tag) { std::puts("random access"); }

int main() {
  pick(std::forward_iterator_tag{});     // 只有 input 可行
  pick(std::contiguous_iterator_tag{});  // 三个都可行，最近的基类胜出
}
```

输出 `input` 和 `random access`。`contiguous_iterator_tag` 到三个基类的转换等级都是 Conversion，按等级分不出高下。这时 [[over.ics.rank#4.5]] 的规则介入：如果 C 派生自 B、B 派生自 A，那么 C 到 B 的转换优于 C 到 A 的转换（4.5.3）。继承链上越近的基类越好，所以总是选中最具体的那个算法。

!!! std
    If class B is derived directly or indirectly from class A and class C is derived directly or indirectly from B, … conversion of C to B is better than conversion of C to A.

    [[over.ics.rank#4.5]]：沿继承链，转换到较近的基类优于转换到较远的基类。标签分派的排序完全建立在这一句上。

继承链断了，这套排序就失效。一个标签同时派生自两个互不相关的类，重载就会歧义：

```cpp title="broken-chain.cpp" error
struct input {};
struct forward {};                       // 忘了继承 input
struct random_access : input, forward {};
void pick(input);
void pick(forward);
void f() { pick(random_access{}); }      // error: 歧义
```

本机 Clang 23 报告 `call to 'pick' is ambiguous`。`input` 和 `forward` 之间没有派生关系，4.5 的任何一条都用不上，两个转换序列无法区分。

### 空标签的运行期代价

标签是空类，`sizeof` 为 1，但它不携带任何信息，优化后什么也不剩。本机 Clang 23 `-O2` 下，对 `int*` 调用 `my_advance` 生成的 arm64 代码只有一条 `add x0, x0, x1, lsl #2`，与直接写 `p + n` 完全相同。

即使不内联，空的类类型形参也不占寄存器。一个 `[[gnu::noinline]] int f(int a, Empty, int b)`，在本机 arm64（Apple ABI）和 x86-64 Linux 目标上，`b` 都直接放在第二个整数寄存器里，与 `int g(int a, int b)` 的代码一模一样。

### 标准库也这样写

本机 libc++ 的 `std::advance` 就是上面的结构：一个入口函数构造 `iterator_category()`，转给三个按标签重载的 `__advance`。标准自己在 [[std.iterator.tags#3]] 的例子里也演示了这种写法。

## 写法二：enable_if 与 SFINAE

C++11 起，可以不经过中间层，直接把条件写进函数模板的签名：

```cpp run title="enable-if.cpp" ok
#include <cstdio>
#include <forward_list>
#include <iterator>
#include <list>
#include <type_traits>
#include <vector>

template<class It>                       // 别名模板：替换失败留在直接语境
using category_t = typename std::iterator_traits<It>::iterator_category;

template<class It, class Tag>
using is_at_least = std::is_base_of<Tag, category_t<It>>;

template<class It, class D,
         std::enable_if_t<is_at_least<It, std::random_access_iterator_tag>::value, int> = 0>
constexpr void my_advance(It& it, D n) {
  it += n;
}

template<class It, class D,
         std::enable_if_t<is_at_least<It, std::bidirectional_iterator_tag>::value &&
                          !is_at_least<It, std::random_access_iterator_tag>::value, int> = 0>
constexpr void my_advance(It& it, D n) {
  if (n >= 0) while (n-- > 0) ++it;
  else        while (n++ < 0) --it;
}

template<class It, class D,
         std::enable_if_t<is_at_least<It, std::input_iterator_tag>::value &&
                          !is_at_least<It, std::bidirectional_iterator_tag>::value, int> = 0>
constexpr void my_advance(It& it, D n) {
  while (n-- > 0) ++it;
}

int main() {
  std::vector<int> v{1, 2, 3, 4, 5};
  std::list<int> l(v.begin(), v.end());
  std::forward_list<int> f(v.begin(), v.end());
  auto a = v.begin(); my_advance(a, 3);
  auto b = l.end();   my_advance(b, -2);
  auto c = f.begin(); my_advance(c, 2);
  std::printf("%d %d %d\n", *a, *b, *c);
}
```

`std::enable_if_t<C, int>` 在 `C` 为真时是 `int`，为假时根本不存在。条件为假的那个模板，在模板实参推导中把推出的类型代回签名时会形成无效的类型，推导失败，这个模板就从候选中消失，不算错误。这条规则叫 **SFINAE**（[[g:sfinae|substitution failure is not an error]]，[[temp.deduct.general#8]]）。

这里不再借助继承排序，三个模板对同一个类型只能有一个存活。所以每个条件都要排除更强的情形：双向版本要写 `!random_access`，输入版本要写 `!bidirectional`。想再加一层，比如为 `contiguous_iterator_tag` 单独写一个版本，就得回头修改随机访问版本的条件。

### 替换失败只在直接语境中才算数

SFINAE 只吞掉直接语境里的错误。**直接语境**（[[g:immediate-context|immediate context]]）指函数类型、模板形参的声明这些被替换的位置本身，不包括替换时顺带实例化的其他模板，例如类模板的定义、变量模板的初始化器（[[temp.deduct.general#8]]）。

上面用的是别名模板 `category_t`。别名模板在替换时被直接展开，失败仍然发生在签名里。把它改成一个变量模板，看起来等价，行为却不同：

<div class="compare" markdown="1">

```cpp
template<class It>
using category_t = typename
  std::iterator_traits<It>
    ::iterator_category;
// 失败在签名里：SFINAE
```

```cpp
template<class It, class Tag>
inline constexpr bool at_least_v =
  std::is_base_of_v<Tag, typename
    std::iterator_traits<It>
      ::iterator_category>;
// 失败在初始化器里：硬错误
```

</div>

用右边的写法，对 `int` 调用 `my_advance`，本机 Clang 23 报的不是没有匹配的函数，而是三次 `no type named 'iterator_category' in 'std::iterator_traits<int>'`，每次附带 `in instantiation of variable template specialization ... requested here`。变量模板特化的初始化器是单独实例化的，不在直接语境里，错误不会被当作替换失败。

### 错误信息

用正确的写法，传一个输出迭代器进去，本机 Clang 23 的诊断是：

```text
error: no matching function for call to 'my_advance'
note: candidate template ignored: requirement 'std::is_base_of<std::random_access_iterator_tag,
      std::output_iterator_tag>::value' was not satisfied [with It = std::ostream_iterator<int>, D = int]
note: candidate template ignored: requirement 'std::is_base_of<std::bidirectional_iterator_tag,
      std::output_iterator_tag>::value' was not satisfied [...]
note: candidate template ignored: requirement 'std::is_base_of<std::input_iterator_tag,
      std::output_iterator_tag>::value' was not satisfied [...]
```

（行内的源码片段已删去，下同。）Clang 会把 `enable_if` 的条件展开打印出来，这已经比老编译器友好得多。但它只能告诉你哪个布尔表达式为假，至于条件为什么为假，要读者自己去对照 trait 的定义。

## 写法三：if constexpr

C++17 起，可以把所有分支放进同一个函数体：

```cpp run title="if-constexpr.cpp" ok
#include <cstdio>
#include <forward_list>
#include <iterator>
#include <list>
#include <type_traits>
#include <vector>

template<class It, class D>
constexpr void my_advance(It& it, D n) {
  using Cat = typename std::iterator_traits<It>::iterator_category;
  if constexpr (std::is_base_of_v<std::random_access_iterator_tag, Cat>) {
    it += n;                         // list 的迭代器没有 +=：这一支被丢弃
  } else if constexpr (std::is_base_of_v<std::bidirectional_iterator_tag, Cat>) {
    if (n >= 0) while (n-- > 0) ++it;
    else        while (n++ < 0) --it;
  } else if constexpr (std::is_base_of_v<std::input_iterator_tag, Cat>) {
    while (n-- > 0) ++it;
  } else {
    static_assert(false, "my_advance needs an input iterator");
  }
}

int main() {
  std::vector<int> v{1, 2, 3, 4, 5};
  std::list<int> l(v.begin(), v.end());
  std::forward_list<int> f(v.begin(), v.end());
  auto a = v.begin(); my_advance(a, 3);
  auto b = l.end();   my_advance(b, -2);
  auto c = f.begin(); my_advance(c, 2);
  std::printf("%d %d %d\n", *a, *b, *c);
}
```

`if constexpr` 的条件必须是常量表达式。条件为假时，第一个子语句是**被丢弃的语句**（[[g:discarded-statement|discarded statement]]）；条件为真时，`else` 后的子语句被丢弃。在模板实例化期间，如果条件不再依赖模板形参，被丢弃的子语句不实例化（[[stmt.if#2]]）。

分支的顺序就是优先级。条件用 `is_base_of_v` 写成至少是某一类，所以必须从最强的分类往下测，先测输入迭代器的话，所有迭代器都会落进第一支。

传一个输出迭代器进去，本机 Clang 23 只有两行：`static assertion failed: my_advance needs an input iterator`，以及 `in instantiation of function template specialization 'my_advance<std::ostream_iterator<int>, int>' requested here`。消息由作者自己写，所以可以写得很直接。

### 被丢弃的语句仍然要正确

被丢弃不等于被忽略。它有两层限制。

第一，丢弃只在模板里有意义。在普通函数里，`if constexpr (false)` 的分支照样完整编译，只是不执行，odr-use 也不要求实体有定义（[[stmt.if#2]] 的注）。

第二，在模板里，被丢弃的分支中不依赖模板形参的代码仍然在定义处检查。这些代码对任何模板实参都一样，如果它们本身就有错，任何实例化都不可能正确：

<div class="compare" markdown="1">

```cpp title="non-template.cpp" error
#include <string>

int g() {
  if constexpr (sizeof(int) == 2) {
    std::string s = 42;  // error
  }
  return 0;
}
```

```cpp title="non-dependent.cpp" ifndr
template<class T>
void f(T t) {
  if constexpr (sizeof(T) == 1) {
    t.foo();       // 依赖 T：不检查
    undeclared();  // 不依赖 T
  }
}
int main() { f(0); }
```

</div>

左边不在模板中，`std::string s = 42` 是普通的错误，本机 Clang 23 报 `no viable conversion from 'int' to 'std::string'`。右边 `f<int>` 的分支被丢弃，`t.foo()` 依赖 `T`，从来不会被检查；`undeclared()` 不依赖 `T`，对任何 `T` 都不可能正确。按 [[temp.res.general#6]]（6.1、6.7），这样的程序非良构，不要求诊断；本机 Clang 23 在定义处就报 `use of undeclared identifier 'undeclared'`。

`static_assert(false, ...)` 是这条规则唯一的例外。[[temp.res.general#6]] 在判断能否生成有效特化时明确忽略失败的 `static_assert`，所以把它放在被丢弃的 `else` 分支里，只有真的走到这一支时才报错（[[P2593R1]]）。在这之前，常见的绕法是写一个依赖模板形参的假条件，如 `static_assert(sizeof(T) == 0)`。本机 Clang 23 在 `-std=c++20` 下也接受 `static_assert(false)`。

## 写法四：按约束重载

C++20 的概念把条件写在模板头里，同时提供了按条件强弱排序的规则：

```cpp run title="concepts.cpp" ok
#include <cstdio>
#include <forward_list>
#include <iterator>
#include <list>
#include <vector>

template<std::input_iterator It>
constexpr void my_advance(It& it, std::iter_difference_t<It> n) {
  while (n-- > 0) ++it;
}

template<std::bidirectional_iterator It>
constexpr void my_advance(It& it, std::iter_difference_t<It> n) {
  if (n >= 0) while (n-- > 0) ++it;
  else        while (n++ < 0) --it;
}

template<std::random_access_iterator It>
constexpr void my_advance(It& it, std::iter_difference_t<It> n) {
  it += n;
}

int main() {
  std::vector<int> v{1, 2, 3, 4, 5};
  std::list<int> l(v.begin(), v.end());
  std::forward_list<int> f(v.begin(), v.end());
  auto a = v.begin(); my_advance(a, 3);
  auto b = l.end();   my_advance(b, -2);
  auto c = f.begin(); my_advance(c, 2);
  std::printf("%d %d %d\n", *a, *b, *c);
}
```

对 `vector` 的迭代器，三个模板都满足约束，按类型推导又一样特殊。这时比较约束：`random_access_iterator` 的定义以 `bidirectional_iterator<I> && ...` 开头，后者又以 `forward_iterator<I> && ...` 开头，于是前者**包含**（[[g:subsumes|subsumes]]）后者，约束更强的模板更特殊（[[temp.func.order#8]] 8.4，[[temp.constr.order#5]]）。这与标签分派中最近基类胜出的效果相同，只是排序依据从类的继承换成了概念的逻辑蕴含。

包含关系只认具名概念之间的引用，各写一遍的同样条件不算相同。规则细节和反例见 [[topics/concepts]]。

### 概念背后仍是标签

标准迭代器概念并没有抛弃标签。`random_access_iterator` 的定义里有 `derived_from<ITER_CONCEPT(I), random_access_iterator_tag>`（[[iterator.concept.random.access#1]]）。`ITER_CONCEPT(I)` 优先取 `iterator_concept` 成员，没有时才退回 `iterator_category`（[[iterator.concepts.general#1]]）。

标签在这里的角色变了：它不再负责选重载，而是作为迭代器作者的声明，表示愿意承担某个分类的语义要求。语法检查交给 *requires* 表达式，语义承诺仍靠标签。

### 错误信息

同样传入输出迭代器，本机 Clang 23 对每个候选都给出一条原因链。第一个候选的部分是：

```text
error: no matching function for call to 'my_advance'
note: candidate template ignored: constraints not satisfied [with It = std::ostream_iterator<int>]
note: because 'std::ostream_iterator<int>' does not satisfy 'input_iterator'
note: because 'std::ostream_iterator<int>' does not satisfy 'indirectly_readable'
note: because 'remove_cvref_t<...>' (aka 'std::ostream_iterator<int>') does not satisfy '__indirectly_readable_impl'
note: because 'typename iter_value_t<_In>' would be invalid: no type named 'value_type' in
      'std::indirectly_readable_traits<std::ostream_iterator<int>>'
...
```

这是四种写法里唯一一个说出了根本原因的：输出迭代器没有 `value_type`，所以不可读。代价是长度，三个候选沿着标准库概念的层次各展开一遍，error 和 note 一共 34 行，而标签分派是 5 行，`enable_if` 是 4 行，`if constexpr` 加 `static_assert` 是 2 行。前两三行通常就够用，后面是逐层追问的证据。

## 四种写法对比

### 入口有没有约束

标签分派和 `if constexpr` 的入口 `my_advance` 是不受约束的模板，任何实参都能匹配，错误发生在函数体里。这不只是错误信息位置的问题：用 *requires* 表达式问能不能调用它，会得到错误的答案。

```cpp
template<class It>
concept advanceable = requires(It& it) { my_advance(it, 1); };

static_assert(advanceable<std::ostream_iterator<int>>);
```

本机 Clang 23 上，这个断言对标签分派版本和 `if constexpr` 版本成立，对 `enable_if` 版本和概念版本失败。前两者对任何类型都声称可以调用，依赖它的其他重载或约束就会被误导。

libc++ 的 `std::ranges::advance` 把两种写法组合起来：入口用 `input_or_output_iterator` 约束，函数体里用 `if constexpr (random_access_iterator<I>)` 分支（标准对它的规定见 [[range.iter.op.advance#2]]）。入口的约束对外如实声明能接受什么，内部的分支避免了多个重载之间的排序问题。

### 编译时间

用脚本生成 1500 个不同的元素类型 `W<K>`，每个类型对 `W<K>*`、一个前向迭代器、一个双向迭代器各调用一次 `my_advance`，共 4500 次实例化。本机 Clang 23 + libc++，`-O0 -c`，用户态 CPU 时间和峰值内存：

| 写法 | 用户态时间 | 峰值内存 |
|---|---|---|
| 只有类型定义，不调用 | 0.2 s | 110 MB |
| 标签分派 | 1.1 s | 288 MB |
| `enable_if` | 1.1 s | 295 MB |
| `if constexpr` | 1.0 s | 258 MB |
| 自定义概念，只检查 `iterator_category` | 1.1 s | 323 MB |
| 标准库迭代器概念 | 18 s | 约 1.9 GB |

测量时机器负载较高，墙钟时间波动很大，表中数字只看量级。前四种几乎没有差别，`if constexpr` 每次只实例化一个函数，略省一点。

标准库概念的开销不在概念机制本身：换成只比较标签的自定义概念，耗时和标签分派相当。开销来自 `input_iterator` 这些概念要检查的大量要求，`indirectly_readable` 里的 `common_reference_with` 尤其昂贵。单独对一个新类型检查一次 `std::input_iterator`，本机约 2.4 ms。对日常代码这不算什么；对于为成千上万个类型实例化的底层库，值得知道。

### 能表达什么

| | 标签分派 | `enable_if` | `if constexpr` | 按约束重载 |
|---|---|---|---|---|
| 最低标准 | C++98 | C++11 | C++17 | C++20 |
| 选择依据 | 标签类型的继承关系 | 手写的互斥条件 | 分支顺序 | 概念的包含关系 |
| 新增一档 | 加一个派生标签和一个重载 | 要改已有重载的条件 | 改这个函数 | 加一个细化的概念和一个重载 |
| 第三方能否扩展 | 能，标签可以派生；非限定调用时还能经 ADL 找到新重载 | 难 | 不能，分支是封闭的 | 能 |
| 入口受约束 | 否 | 是 | 否 | 是 |
| 用在构造函数上 | 能，加一个标签形参 | 能 | 只能在函数体里 | 能 |
| 错误信息 | 函数体内的重载失败 | 列出为假的条件 | 自己写的 `static_assert` | 原因链，较长 |

## 标准库里的标签

迭代器分类是让类型携带性质的标签。标准库里还有另一类更常见的标签：调用者显式传入一个空对象，用来选中一个特定的构造函数或一种特定的语义。

```cpp run title="library-tags.cpp" ok
#include <cstdio>
#include <flat_map>
#include <list>
#include <map>
#include <new>
#include <optional>
#include <string>
#include <tuple>
#include <utility>
#include <variant>
#include <vector>

int main() {
  // in_place：把实参原样转给 T 的构造函数，而不是先造一个 T 再搬进去
  std::optional<std::string> o(std::in_place, 3, 'x');            // "xxx"
  // in_place_type / in_place_index：构造函数不能显式指定模板实参，类型只能靠实参带进来
  std::variant<int, std::string> v(std::in_place_type<std::string>, 2, 'y');
  // piecewise_construct：两个 tuple 分别展开给 first 和 second
  std::map<std::string, std::vector<int>> m;
  m.emplace(std::piecewise_construct,
            std::forward_as_tuple("k"), std::forward_as_tuple(4, 7));
  // nothrow：选中另一个分配函数，失败时返回空指针而不是抛出
  int* p = new (std::nothrow) int[16];
  delete[] p;
  // from_range：按范围构造，同时让类模板实参推导推出元素类型
  std::list<int> src{3, 1, 2};
  std::vector w(std::from_range, src);                             // vector<int>
  std::vector u{src};                                              // vector<list<int>>
  // sorted_unique：调用方承诺键已经有序且不重复，构造时跳过排序
  std::flat_map<int, char> fm(std::sorted_unique, {1, 2, 3}, {'a', 'b', 'c'});

  std::printf("%s %s %zu %zu %zu %zu %c\n", o->c_str(), std::get<1>(v).c_str(),
              m["k"].size(), w.size(), u.size(), u[0].size(), fm[2]);
}
```

本机输出 `xxx yy 4 3 1 3 b`。注意 `w` 和 `u`：同样以 `src` 为实参，带标签时推导出 `vector<int>`，不带标签的花括号推导出一个只有一个元素的 `vector<list<int>>`。

| 标签 | 声明在 | 作用 |
|---|---|---|
| `in_place_t` / `in_place_type_t<T>` / `in_place_index_t<I>` | [[utility.syn]] | `optional`、`variant`、`any`、`expected` 就地构造所含对象；后两个把类型或下标带进构造函数 |
| `piecewise_construct_t` | [[pair.piecewise]] | `pair` 的两个成员分别用一个 `tuple` 展开构造 |
| `allocator_arg_t` | [[allocator.tag]] | `tuple` 等类型的构造函数：下一个实参是分配器 |
| `nothrow_t` | [[new.syn]] | 经 placement 语法选中不抛出的分配函数，失败时返回空指针 |
| `destroying_delete_t` | [[new.syn]] | 类的 `operator delete` 带上它，`delete` 表达式不再先调用析构函数 |
| `from_range_t` | [[ranges.syn]] | 容器从任意范围构造或插入（[[P1206R7]]） |
| `sorted_unique_t` / `sorted_equivalent_t` | [[flat.map.syn]] | 调用方保证输入已经有序，构造时不再排序 |
| 执行策略 `sequenced_policy` 等 | [[execpol]] | 并行算法的重载：选择顺序、并行或向量化执行 |

### 为什么不用 bool

设想 `flat_map` 用一个 `bool assume_sorted` 形参代替 `sorted_unique`。差别有三处。

第一，语义在编译期就分开了。不带标签的构造函数先排序再去重（[[flat.map.cons#1]]），带 `sorted_unique` 的版本只移动容器，复杂度是常数（[[flat.map.cons#4]]）。用 `bool` 的话，两条路径都要编译进同一个函数，运行时再判断。对 `in_place_type<T>` 来说更明显，一个 `bool` 根本带不进类型。

第二，标签能让同一组实参换一种含义。`pair(tuple, tuple)` 本来的意思是用两个 tuple 去初始化两个成员，加上 `piecewise_construct` 才变成把 tuple 展开成构造函数实参。`vector{src}` 本来就是合法的，加上 `from_range` 才变成按范围构造。如果靠 `bool`，这些重载在签名上就无法区分。

第三，调用处可读。`flat_map(keys, values, true)` 里的 `true` 要翻文档才知道含义，`sorted_unique` 自己说明了意图，写错了类型也会在编译期被拒绝。同一个问题在普通函数上的其他解法，见 [[patterns/named-parameters|命名参数与 builder]] 和 [[patterns/strong-types|强类型与幻影类型]]。

### 标签类型的写法

标准库的标签都写成同一个样子：

```cpp
struct in_place_t { explicit in_place_t() = default; };
inline constexpr in_place_t in_place{};
```

默认构造函数是 `explicit` 的（[[LWG2510]]），所以 `std::in_place_t t = {};` 非良构：用空的花括号做复制列表初始化时选中了 explicit 构造函数（[[over.match.ctor#1]]）。一个随手写的 `{}` 不会被悄悄当成标签。

`inline constexpr` 变量让调用者写 `std::in_place` 而不必写 `std::in_place_t{}`，每个翻译单元看到的是同一个对象。`nothrow` 是例外，它在 C++98 就存在，声明为 `extern const nothrow_t nothrow;`。

带标签的构造函数还要防着自己的转发构造函数。`optional(U&& v)` 能接受任何类型，所以标准专门约束它在 `U` 是 `in_place_t` 时不参与（[[optional.ctor#23]]）；`any(T&& value)` 同样排除了 `in_place_type_t` 的特化（[[any.cons#6]]），否则 `std::any a(std::in_place_type<int>);` 会把标签对象本身存进去。自己写类似的类型时，转发构造函数也要加同样的约束。

### 一个由核心语言识别的标签

大多数标签只在库里起作用，`destroying_delete_t` 是少数改变核心语言语义的标签。类的 `operator delete` 的第二个形参是这个类型时，它就是**销毁型 operator delete**（destroying operator delete，[[basic.stc.dynamic.deallocation#2]]），`delete` 表达式不再自动调用析构函数（[[expr.delete#5]]），销毁对象的责任交给这个函数（[[P0722R3]]）。

```cpp run title="destroying-delete.cpp" ok
#include <cstdio>
#include <new>

struct Shape {
  enum Kind { circle, square } kind;
  // 第二个形参是 destroying_delete_t：delete 表达式不再先调用析构函数
  void operator delete(Shape* p, std::destroying_delete_t);
};
struct Circle : Shape { double r; ~Circle() { std::puts("~Circle"); } };
struct Square : Shape { double a; ~Square() { std::puts("~Square"); } };

void Shape::operator delete(Shape* p, std::destroying_delete_t) {
  // 没有虚析构函数，也能按动态类型销毁：自己看 kind 分派
  if (p->kind == circle) { auto* c = static_cast<Circle*>(p); c->~Circle(); ::operator delete(c, sizeof(Circle)); }
  else                   { auto* s = static_cast<Square*>(p); s->~Square(); ::operator delete(s, sizeof(Square)); }
}

int main() {
  Shape* a = new Circle{{Shape::circle}, 1.0};
  Shape* b = new Square{{Shape::square}, 2.0};
  delete a;   // ~Circle
  delete b;   // ~Square
}
```

输出 `~Circle` 和 `~Square`，本机 ASan 和 UBSan 均无报告。通过基类指针删除派生类对象，基类又没有虚析构函数，平常是 UB；[[expr.delete#3]] 对选中销毁型 operator delete 的情形网开一面，因为此时由类自己负责按动态类型销毁。这里的标签不是用来选重载的，编译器识别这个类型本身。

### 执行策略

`std::execution::seq`、`par`、`par_unseq`、`unseq` 也是标签对象，每个属于一个独立的类，彼此没有继承关系。并行算法的重载用仅用于说明的概念 *execution-policy* 约束第一个形参，它检查的是 `is_execution_policy_v`（[[algorithms.parallel.defns]]，[[execpol.type#2]]）。用户不能特化这个 trait（[[execpol.type#3]]），新的策略只能由实现提供。本机 libc++ 的并行算法需要 `-fexperimental-library` 才可用。

## 陷阱

!!! pitfall "按 iterator_category 分派会低估 C++20 迭代器"
    `iota_view` 的迭代器和返回纯右值的 `transform_view` 迭代器，`iterator_category` 都是 `input_iterator_tag`，因为旧的迭代器要求规定前向迭代器的解引用必须返回引用（[[range.iota.iterator]]，[[range.transform.iterator#2]]）。它们的 `iterator_concept` 却是随机访问。用 `iterator_category` 分派的 `my_advance` 会对它们一步一步地加；按 `std::random_access_iterator` 重载的版本会走 `+=`。

```cpp ok
#include <iterator>
#include <ranges>
#include <type_traits>
#include <vector>

using It = std::ranges::iterator_t<std::ranges::iota_view<long, long>>;
static_assert(std::is_same_v<std::iterator_traits<It>::iterator_category,
                             std::input_iterator_tag>);   // 旧分类：input
static_assert(std::random_access_iterator<It>);           // 新概念：random access

int square(int x) { return x * x; }
using Squares = decltype(std::declval<std::vector<int>&>() | std::views::transform(square));
using Jt = std::ranges::iterator_t<Squares>;
static_assert(std::is_same_v<std::iterator_traits<Jt>::iterator_category,
                             std::input_iterator_tag>);   // 解引用返回纯右值
static_assert(std::random_access_iterator<Jt>);
```

!!! pitfall "约束重载的形参形状必须一致"
    按约束排序的前提是两个模板按类型推导一样特殊，并且模板形参列表等价（[[temp.func.order#8]]）。下面的第一个模板多了一个形参 `D`，约束就派不上用场。

```cpp run title="shape-mismatch.cpp" ok
#include <cstdio>
#include <iterator>
#include <vector>

template<std::input_iterator It, class D>
void my_advance(It& it, D n) { std::puts("input"); while (n-- > 0) ++it; }

template<std::random_access_iterator It>
void my_advance(It& it, std::iter_difference_t<It> n) { std::puts("random access"); it += n; }

int main() {
  std::vector<int> v(10);
  auto it = v.begin();
  my_advance(it, 3);   // 打印 input
}
```

实参 `3` 是 `int`。第一个模板推出 `D = int`，精确匹配；第二个模板的形参是 `ptrdiff_t`，需要一次整数转换。重载决议在比较约束之前就按转换序列选中了第一个，`vector` 的迭代器被一步一步地加了 3 次，没有任何警告。把实参改成 `3L`，两个转换都是精确匹配，但模板形参列表长度不同，按 [[temp.func.order#8]]（8.1）约束不参与比较，本机 Clang 23 报 `call to 'my_advance' is ambiguous`。各个重载用相同的形参形状，如 `concepts.cpp` 那样，就没有这个问题。

!!! pitfall "标签分派的入口不受约束"
    入口模板接受一切实参，错误只在函数体里出现，`requires` 表达式和其他重载看到的是一个什么都能调用的函数。如果入口会被其他泛型代码探测，给它加上约束，比如 `template<std::input_iterator It>`，内部仍可以用标签或 `if constexpr` 分派。

## 什么时候用哪种

| 情形 | 选择 |
|---|---|
| C++20 及以后的新代码，按类型能力选算法 | 入口加概念约束，内部用 `if constexpr` 分支；或者直接按约束重载 |
| 选择集合固定，只有作者会扩展 | `if constexpr`，分支集中在一处 |
| 第三方要能为自己的类型加入新的一档 | 按约束重载，或者带继承的标签 |
| 构造函数需要另一种含义，或要带入一个类型 | 标签形参，按 `in_place_t` 的样子写 |
| 要支持 C++17 以前的标准 | 标签分派；条件之间不重叠时可以用 `enable_if` |
| 要为大量类型实例化，编译时间敏感 | 避免在热路径上检查重量级的标准库概念，用更轻的自定义概念或标签 |

## 思考题

!!! question "1"
    在写法一中，把三个 `detail::advance` 的标签形参都改成 `const std::input_iterator_tag&` 之类的引用，选中的重载会变吗？

<details markdown="1">
<summary>答案</summary>

不会。引用直接绑定到派生类对象时，隐式转换序列同样是派生类到基类的转换（[[over.ics.ref#1]]），等级为 Conversion；[[over.ics.rank#4.5]] 的 4.5.3 只看类之间的派生关系，对按值和按引用一视同仁。仍然是最近的基类胜出。按值传递空标签也没有运行期代价，所以标准库通常按值传。
</details>

!!! question "2"
    下面的写法哪里有问题？

    ```cpp
    template<class T>
    void serialize(const T& x) {
      if constexpr (std::is_arithmetic_v<T>) write_number(x);
      else if constexpr (requires { x.serialize(); }) x.serialize();
      else static_assert(false, "not serializable");
    }
    ```

<details markdown="1">
<summary>答案</summary>

在当前草案下它是正确的：`static_assert(false)` 位于被丢弃的分支里，[[temp.res.general#6]] 在判断有效特化时忽略失败的 `static_assert`，只有真正选中最后一支时才报错。真正的问题在设计：分支集合是封闭的，用户无法为自己的类型接入序列化，只能去改这个函数；而且 `serialize` 不受约束，`requires { serialize(y); }` 对任何类型都成立。需要可扩展时，改成按约束重载，或者通过 ADL 查找的定制点，见 [[topics/name-lookup-and-customization]]。
</details>

!!! question "3"
    `std::optional<std::in_place_t> o(std::in_place);` 构造出来的 `o` 有值吗？

<details markdown="1">
<summary>答案</summary>

这个程序非良构。`in_place_t` 和 `nullopt_t` 不是 `optional` 的有效所含类型，用它们实例化 `optional` 就是错误（[[optional.optional.general#2]]）。否则 `optional(std::in_place)` 既可以理解为用空的实参列表就地构造，也可以理解为存一个标签对象，`optional(std::nullopt)` 也有类似的二义性。本机 libc++ 用 `static_assert` 报告 `instantiation of optional with in_place_t is ill-formed`。

同样的考虑也体现在 `optional(U&&)` 的约束上：`U` 是 `in_place_t` 时它不参与重载决议（[[optional.ctor#23]]），标签总是落到带标签的构造函数上。
</details>

## 小结

| 问题 | 结论 | 出处 |
|---|---|---|
| 标签为什么继承 | 派生类到基类是 Conversion 等级，最近的基类优先 | [[over.best.ics#7]]、[[over.ics.rank#4.5]] |
| 空标签的运行期代价 | 本机 `-O2` 下为零，不内联也不占寄存器 | 实测 |
| SFINAE 吞掉哪些错误 | 只有直接语境中的替换失败 | [[temp.deduct.general#8]] |
| 被丢弃的语句 | 模板中不实例化；不依赖模板形参的部分仍要正确 | [[stmt.if#2]]、[[temp.res.general#6]] |
| 约束重载怎样排序 | 包含关系；要求模板形参列表与函数形参类型一致 | [[temp.constr.order#5]]、[[temp.func.order#8]] |
| 迭代器概念与标签 | 概念内部仍以 `ITER_CONCEPT(I)` 标签判断分类 | [[iterator.concepts.general#1]] |
| 标签类型的写法 | 空类，explicit 默认构造函数，`inline constexpr` 对象 | [[utility.syn]]、[[LWG2510]] |
