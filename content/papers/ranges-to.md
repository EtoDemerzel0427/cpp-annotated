---
title: ranges::to 与从范围构造容器（P1206）
summary: C++20 的视图没有回到容器的路，P1206 为此加了 ranges::to 和所有标准容器的 from_range 构造函数与 *_range 成员；它为什么最终是一个自由函数加一个标签，四种构造方式为什么按这个顺序尝试，以及后来的修正和 C++26 的 reserve_hint。
status: draft
order: 54
group: 标准库
since: c++23
papers: P1206R0, P1206R1, P1206R7, P2846R6, P2214R2, LWG3733, LWG3785, LWG3847, LWG3958, LWG3984, LWG4016, LWG4121
related: range.utility.conv, ranges.syn, container.requirements.general, sequence.reqmts, range.approximately.sized, range.prim.size.hint, range.adaptor.object, over.match.class.deduct, topics/ranges-design, patterns/tag-dispatch, history/modern-library, papers/generator
tags: 提案, 范围, ranges::to, 容器, from_range, C++23
updated: 2026-10-19
---

!!! tldr
    - C++20 的视图常常不是 common range（首尾类型不同），而容器只有要求首尾同类型的迭代器对构造函数，所以 `std::vector<int> v(r.begin(), r.end())` 经常编译不过。
    - [[P1206R7]] 加了两样东西：自由函数 `ranges::to<C>(r)`（以及管道形式 `r | ranges::to<C>()`），和每个标准容器上带 `from_range` 标签的构造函数，外加 `insert_range`、`append_range`、`assign_range` 等成员。
    - 最初的方案是直接给容器加接受范围的构造函数，因为和 `initializer_list` 构造函数、类模板实参推导冲突而放弃；标签让同一个实参换一种含义，`std::vector v{l}` 和 `std::vector v(std::from_range, l)` 推导出不同的类型。
    - `ranges::to` 依次尝试：范围构造、`from_range` 构造、迭代器对构造、默认构造后逐个追加（能预留时先 `reserve`）；元素本身是范围时逐层递归，所以能直接得到 `vector<vector<int>>`。
    - 之后的修正放宽了目标类型、修好了递归分支、改用 `emplace_back` 追加；C++26 的 [[P2846R6]] 让只能估计长度的范围也能预留内存。

## 问题：范围回不去容器

C++20 的范围库能把数据过滤、变换、截断成一条惰性的管道，但最后常常需要一个真正的容器：要存起来，要随机访问，要交给只接受 `vector` 的接口。C++20 没有提供这一步。最自然的写法是容器的迭代器对构造函数：

<div class="compare" markdown="1">

```cpp run std=c++20 error
#include <ranges>
#include <vector>
int main() {
  std::vector<int> src{1, 2, 3, 9, 4};
  auto r = src | std::views::take_while(
      [](int i) { return i < 5; });
  std::vector<int> out(r.begin(), r.end());
  // error: begin 和 end 类型不同
}
```

```cpp run ok
#include <ranges>
#include <vector>
int main() {
  std::vector<int> src{1, 2, 3, 9, 4};
  auto out = src
    | std::views::take_while(
        [](int i) { return i < 5; })
    | std::ranges::to<std::vector>();
  return out.size() == 3 ? 0 : 1;
}
```

</div>

左边在本机 Clang 23 的 `-std=c++20` 下报 `no matching constructor`。原因是 C++20 的范围由一个迭代器和一个**哨位**（sentinel，表示终点、可以和迭代器类型不同的对象）组成。`take_while` 的终点要靠谓词判断，它的哨位是另一种类型，这样的范围不是 [[g:common-range|common range]]。容器的迭代器对构造函数是 C++98 写的，两个实参必须同类型。哨位的设计理由见 [[topics/ranges-design]]。

[[P1206R7]] 的 Considerations 一节把绕行的办法逐个试了一遍，结论是没有一个总能用：

1. 先套一层 `views::common`，把哨位包装成与迭代器同类型。这对上面的例子有效。
2. 但 `views::common` 要求迭代器可复制，C++20 的单遍输入迭代器可以只能移动。论文用 `std::generator` 举例；本机 libc++ 没有 `<generator>`，换成 `std::views::istream<int>(in) | std::views::common` 同样编译失败。生成器本身见 [[papers/generator|std::generator]]。
3. 剩下的办法只有手写循环：默认构造一个容器，判断能不能 `reserve`，再 `ranges::copy` 到 `back_inserter`。

[[P1206R7]] 的对照表里，第三种写法要先拼出元素类型 `iter_value_t<iterator_t<decltype(view)>>`，再写一段 `if constexpr (sized_range<...>)` 才能预留内存。论文还列了四个讨论这个问题的博客和问答帖，说明这已经是常见的绊脚石。

## 设计空间

### 方案一：给容器加范围构造函数

[[P1206R0]] 最初的提议很直接：所有容器、`string`、`span`、`string_view` 都加一个接受范围的构造函数，于是可以写 `std::vector<int> vec{lst};`，甚至 `std::vector vec = ranges::iota(42);`。

R0 花了不少篇幅讨论这个构造函数该不该是 `explicit`。隐式转换写起来最方便，但会制造看不见的 O(n) 复制：

```cpp
void foo(const std::vector<int>&);
std::deque<int> d = /* ... */;
foo(d);   // 假如允许隐式转换：每次调用都复制整个 deque
foo(d);   // 再复制一次
```

R0 的折中是：从容器构造一律 `explicit`，从右值视图构造可以隐式，因为右值视图只能物化一次，谈不上多余的复制。论文自己承认这会产生怪异的结果，例如 `deque dq = std::move(some_span);` 允许隐式构造，却照样复制了全部元素。

这个方案在下一版就放弃了。[[P1206R1]] 给出的理由是和 `initializer_list` 冲突：

```cpp
std::vector<int> foo = /* ... */;
std::vector a{foo};   // 今天：vector<vector<int>>，一个元素
std::vector b(foo);   // 加了范围构造函数之后：vector<int>
```

花括号初始化优先选**初始化器列表构造函数**（[[g:initializer-list-constructor|initializer-list constructor]]），加上类模板实参推导（CTAD，[[over.match.class.deduct]]），`std::vector a{foo}` 的含义早已固定：以 `foo` 为唯一元素的 `vector`。新构造函数只会让圆括号和花括号的差别更难记，而且不能改变已有代码的含义。

### 方案二：转换运算符或成员函数

另一个方向是让视图负责转换。[[P1206R0]] 提到了 Abseil 的做法：`absl::StrSplit` 的返回值有一个模板转换运算符 `template<Container C> operator C();`，可以直接赋给 `vector<string>`、`set<string>` 等。R0 也提到，2014 年前后有人提议过类似 `view.to_container<vector>()` 的成员函数形式。

两者的共同问题是转换逻辑要写进每一个视图类型里。R0 的看法是，视图的种类远多于容器，而且容器之间互相转换同样有用，所以这不是通用的解法。用户自己写的视图也得各自实现一遍。

### 方案三：自由函数 ranges::to

[[P1206R1]] 改用 range-v3 已有的做法：一个自由函数模板，range-v3 里先叫 `to_`，后来叫 `to`。它对任何范围都能用，对任何容器（包括非标准容器）都能用，不需要视图或容器配合。

R1 还沿用了 range-v3 的一个便利：管道形式可以省略括号，写成 `r | ranges::to<std::vector<int>>`。但这只对完整类型可行。`to<std::vector>` 只给了类模板，它是函数模板的名字而不是一个对象，要让它不加括号就能放在 `|` 右边，需要改核心语言。R3 的修订记录写着删除了不带括号的语法，今天两种形式都必须写 `()`。

### 标签：让构造函数换一种含义

只有自由函数还不够。`ranges::to` 只能用容器公开的接口来填充元素，而容器自己能做得更好：它能直接操作未初始化的内存，没有 `reserve` 的容器（`deque`、`list`）也能在内部按块分配。[[P1206R7]] 转引了一组测量，在三个场景里，带标签的范围构造函数都比迭代器对构造函数和 `reserve` 加逐个复制更快。

所以 R3 起重新给容器加了范围构造函数，但用一个空的**标签类型** `from_range_t` 作为第一个形参（[[ranges.syn]]）：

```cpp
struct from_range_t { explicit from_range_t() = default; };
inline constexpr from_range_t from_range{};
```

标签解决了方案一的冲突。同一个实参 `l`，加上标签才表示按范围构造，CTAD 也随之推导出不同的类型。论文还指出了另一种歧义：对元素类型为 `std::any` 的容器，传入一个范围，到底是插入这个范围本身，还是插入其中每个元素？这就是成员函数改用新名字（`insert_range`）而不是给 `insert` 加重载的原因。

```cpp run title="tag.cpp" ok
#include <any>
#include <cstdio>
#include <list>
#include <ranges>
#include <type_traits>
#include <vector>
int main() {
  std::list<int> l{1, 2, 3};
  std::vector a{l};                    // 花括号：initializer_list 优先
  std::vector b(std::from_range, l);   // 标签：按范围构造
  static_assert(std::is_same_v<decltype(a), std::vector<std::list<int>>>);
  static_assert(std::is_same_v<decltype(b), std::vector<int>>);

  std::list<std::any> la{1, 2.0, 'c'};
  std::vector<std::any> v;
  v.insert(v.end(), la);               // 插入一个 any，里面装着整个 list
  v.insert_range(v.end(), la);         // 插入三个 any
  std::printf("%zu %zu %zu\n", a.size(), b.size(), v.size());   // 1 3 4
}
```

本机输出 `1 3 4`。标签类型这种写法在标准库里的其他例子，以及为什么不用 `bool` 形参，见 [[patterns/tag-dispatch|标签分发]]。

### 只要范围，不要迭代器加哨位

`std::ranges` 的算法几乎都同时提供两种重载：接受一个范围，或接受一个迭代器加一个哨位。新的构造函数只接受范围。[[P1206R7]] 的理由有两条。

第一，范围可能比迭代器对知道得更多。`std::list` 是 `sized_range`（`size()` 是常数时间），但它的迭代器和哨位不满足 `sized_sentinel_for`，不能相减。拿到整个 `list`，`vector` 可以一次分配到位；只拿到 `list.begin()` 和 `list.end()`，就得先数一遍或者边插边扩容。确实只有迭代器和哨位时，可以用 `subrange(it, s)` 包成范围。

第二，标签构造函数同时是一个协议：用户容器只要提供 `C(from_range_t, R&&)`，`ranges::to` 就会用它。只有一种形式，协议才简单。

### 两样都要

[[P1206R7]] 明确说这两部分互补。`ranges::to` 支持非标准容器，支持容器的容器；标签构造函数让容器有机会给出更高效的实现，并且是 `ranges::to` 的定制点。论文也说，如果来不及，两部分可以拆开，但 `ranges::to` 必须进 C++23，因为它是范围库缺失的关键一环。[[P2214R2]] 规划 C++23 的范围库时，也把 `ranges::to` 列在最高优先级。

## 最终设计

### ranges::to 的四个分支

`ranges::to<C>(r, args...)` 按 [[range.utility.conv.to#2]] 的顺序尝试，额外实参 `args` 放在构造函数实参的最后，用来传分配器、比较器、哈希函数等：

| 条款 | 条件 | 做法 |
|---|---|---|
| ¶2.1.1 | `C(r, args...)` 合法 | 直接构造 |
| ¶2.1.2 | `C(from_range, r, args...)` 合法 | 标签构造 |
| ¶2.1.3 | `r` 是 common range，迭代器有 C++17 风格的 `iterator_category`，`C(begin, end, args...)` 合法 | 迭代器对构造 |
| ¶2.1.4 | `C(args...)` 合法，且能追加元素 | 默认构造，能预留就预留，逐个追加 |

前三个分支都是让容器自己构造，第四个是 `ranges::to` 代劳。用一个记录自己构造方式的类型可以看到分支的选择：

```cpp run title="order.cpp" ok
#include <cstdio>
#include <ranges>
#include <vector>

template<bool Tagged>
struct Probe {
  using value_type = int;
  std::vector<int> v;
  const char* how = "append";
  Probe() = default;
  template<class R> requires Tagged
  Probe(std::from_range_t, R&& r) : how("from_range") {
    for (int x : r) v.push_back(x);
  }
  template<class It>
  Probe(It f, It l) : v(f, l), how("iterator pair") {}
  void push_back(int x) { v.push_back(x); }
  auto begin() const { return v.begin(); }
  auto end() const { return v.end(); }
};

int main() {
  std::vector<int> src{1, 2, 3, 9, 4};
  auto common = src | std::views::transform([](int i) { return i * 2; });
  auto noncommon = src | std::views::take_while([](int i) { return i < 5; });

  std::printf("%s\n", std::ranges::to<Probe<true>>(common).how);
  std::printf("%s\n", std::ranges::to<Probe<false>>(common).how);
  std::printf("%s\n", std::ranges::to<Probe<false>>(noncommon).how);
}
```

本机依次输出 `from_range`、`iterator pair`、`append`。第三行就是本页开头的情形：容器没有标签构造函数，范围又不是 common range，`ranges::to` 退到逐个追加，仍然能完成转换。条件中各个概念的精确含义，以及 ¶2.1.3 为什么检查 `iterator_category`，见 [[range.utility.conv]]。

这个顺序把标签构造放在迭代器对之前，因为标签构造拿到的是整个范围，信息最全。有一个问题报告 [[LWG3958]] 建议进一步把预留加追加的分支提到迭代器对之前：对一个没有标签构造函数的第三方容器，迭代器对会丢掉范围已知的长度。LWG 以 NAD（不是缺陷）关闭，理由是这样做为少见的情况优化，却牺牲了常见的情况。

### 预留与分配次数

¶2.1.4 是唯一由 `ranges::to` 自己决定分配策略的分支。它在 `r` 能给出长度、`C` 是 *reservable-container*（有 `reserve`、`capacity`、`max_size`，[[range.utility.conv.general#3]]）时先调用 `reserve`。要求三个成员都在，是为了不去调用 `unordered_map::reserve` 这类名字相同、语义不同的函数，并让实现能检查不超过 `max_size()`（[[P1206R7]] 的 reservable-container 一节）。

下面替换全局 `operator new` 来数分配次数。`Bag` 既没有标签构造函数也没有迭代器对构造函数，只能走 ¶2.1.4：

```cpp run title="alloc.cpp" ok
#include <cstdio>
#include <cstdlib>
#include <new>
#include <ranges>
#include <sstream>
#include <string>
#include <vector>

static int allocs = 0;
void* operator new(std::size_t n) {
  ++allocs;
  if (void* p = std::malloc(n)) return p;
  throw std::bad_alloc{};
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

struct Bag {
  using value_type = int;
  std::vector<int> v;
  void reserve(std::size_t n) { v.reserve(n); }
  std::size_t capacity() const { return v.capacity(); }
  std::size_t max_size() const { return v.max_size(); }
  std::size_t size() const { return v.size(); }
  void push_back(int x) { v.push_back(x); }
  auto begin() const { return v.begin(); }
  auto end() const { return v.end(); }
};

template<class F> void count(const char* what, F f) {
  allocs = 0;
  f();
  std::printf("%-28s %d\n", what, allocs);
}

int main() {
  std::vector<int> src(1000, 1);
  int calls = 0;
  auto sized = src | std::views::transform([](int i) { return i + 1; });
  auto unsized = src | std::views::take_while([&](int) { ++calls; return true; });

  count("Bag   <- sized", [&] { auto b = std::ranges::to<Bag>(sized); });
  count("Bag   <- not sized", [&] { auto b = std::ranges::to<Bag>(unsized); });
  count("vector<- sized", [&] { auto v = std::ranges::to<std::vector>(sized); });
  calls = 0;
  count("vector<- forward, not sized", [&] { auto v = std::ranges::to<std::vector>(unsized); });
  std::printf("predicate calls: %d\n", calls);

  std::string text;
  for (int i = 0; i < 1000; ++i) text += "1 ";
  std::istringstream in(text);
  auto input = std::views::istream<int>(in);
  count("vector<- input range", [&] { auto v = std::ranges::to<std::vector>(input); });
}
```

本机 Clang 23 加 libc++、`-O2` 的结果：

| 目标 ← 来源 | 走的分支 | 分配次数 |
|---|---|---|
| `Bag` ← 有长度的 `transform` | ¶2.1.4，先 `reserve(1000)` | 1 |
| `Bag` ← 没有长度的 `take_while` | ¶2.1.4，不能预留 | 11 |
| `vector` ← 有长度的 `transform` | ¶2.1.2，标签构造 | 1 |
| `vector` ← 没有长度的 `take_while`（前向范围） | ¶2.1.2，标签构造 | 1 |
| `vector` ← `istream`（单遍输入范围） | ¶2.1.2，标签构造 | 11 |

第四行说明了标签构造的优势：`vector` 自己知道 `take_while` 是前向范围，可以先数一遍再一次分配。代价是谓词被调用了 2000 次而不是 1000 次，范围被遍历了两遍。单遍的 `istream` 不能数两遍，只能边读边扩容，11 次分配是 libc++ 按两倍增长从 1 到 1024 的结果。

### C++26：只能估计长度的范围

上表的 11 次分配和两遍遍历，正是 [[P2846R6]] 要解决的问题。它的例子是 Unicode 大写转换：`ß` 变成 `SS`，所以结果比输入长，转换视图不可能是 `sized_range`；但绝大多数字符的长度不变，输入的长度是一个很好的估计。

P2846R6 加了定制点对象 `ranges::reserve_hint`（[[range.prim.size.hint]]）和概念 `approximately_sized_range`（[[range.approximately.sized]]）：前者对有长度的范围返回 `ranges::size`，否则调用范围自己提供的 `reserve_hint`；后者表示能在常数时间给出一个非负的估计。`sized_range` 自动满足它。`take(n)` 即使底层不知道长度，也给出 `n` 作为估计；`filter`、`take_while` 这类按谓词筛选的视图不提供估计，以免过度分配。

`ranges::to` 的 ¶2.1.4 随之改为按估计预留：

```cpp
if constexpr (approximately_sized_range<R> && reservable-container<C>)
  c.reserve(static_cast<range_size_t<C>>(ranges::reserve_hint(r)));
```

容器的标签构造函数也得到了对应的建议：[[sequence.reqmts#13]] 说，如果估计不小于实际长度，实现不应重新分配超过一次。本机 libc++ 还没有实现 `reserve_hint`，`__cpp_lib_ranges_reserve_hint` 未定义，上面的测量都是 C++23 的行为。

### 范围的范围

¶2.2 处理元素本身是范围、又不能直接转换成目标元素类型的情况：对每个元素递归调用 `to<range_value_t<C>>`。这是 [[P1206R1]] 时还没有、R3 才加上的功能，也是 `ranges::to` 比标签构造函数多出来的能力：

```cpp run title="nested.cpp" ok
#include <cstdio>
#include <deque>
#include <forward_list>
#include <list>
#include <ranges>
#include <string>
#include <string_view>
#include <type_traits>
#include <vector>
int main() {
  std::list<std::forward_list<int>> lst{{0, 1, 2, 3}, {4, 5, 6, 7}};

  auto a = std::ranges::to<std::vector<std::vector<int>>>(lst);    // 逐层递归
  auto b = std::ranges::to<std::vector<std::deque<double>>>(lst);  // 内层顺便换元素类型
  auto c = std::ranges::to<std::vector>(lst);                      // 只换外层
  static_assert(std::is_same_v<decltype(c), std::vector<std::forward_list<int>>>);

  std::string_view str = "the quick brown fox";
  auto words = std::views::split(str, ' ') | std::ranges::to<std::vector<std::string>>();
  std::printf("%zu %zu %g %zu %s\n", a[1].size(), b.size(), b[1][0], c.size(),
              words[2].c_str());   // 4 2 4 2 brown
}
```

本机输出 `4 2 4 2 brown`。`c` 的外层是推导出来的：`to<std::vector>` 只给了类模板，由 CTAD 得到 `vector<forward_list<int>>`，元素可以直接复制，所以不递归。最后一行是 [[range.utility.conv.general#2]] 的例 1：`split` 的每个元素是一段字符的 `subrange`，不能转换成 `string`，于是对每段调用 `to<string>`，后者走 `string` 的标签构造。

不写元素类型时的推导规则（*DEDUCE_EXPR*，[[range.utility.conv.to#4]]）是 [[P1206R1]] 到 R2 之间改出来的：R1 曾打算把 `map` 转成 `vector` 时自动去掉键上的 `const`，R2 删掉了这条特殊处理，改为完全依赖容器的推导指引（[[g:deduction-guide|deduction guide]]）。

### 容器的新成员

凡是原来接受一对输入迭代器的成员函数，[[P1206R7]] 都加了一个接受范围的版本，名字统一加 `_range` 后缀，构造函数则统一用 `from_range` 标签。要求是 *container-compatible-range*：输入范围，且元素的引用类型能转换成容器的元素类型（[[container.requirements.general#2]]）。

```cpp run title="members.cpp" ok
#include <cstdio>
#include <deque>
#include <ranges>
#include <set>
#include <string>
int main() {
  auto r = std::views::iota(1) | std::views::take_while([](int i) { return i <= 3; });

  std::deque<int> d(std::from_range, r);        // 1 2 3
  d.append_range(r);                            // 1 2 3 1 2 3
  d.prepend_range(std::views::iota(7, 9));      // 7 8 1 2 3 1 2 3（不反序）
  d.insert_range(d.begin() + 2, r);             // 7 8 1 2 3 1 2 3 1 2 3
  std::set<int> s;
  s.insert_range(d);                            // 1 2 3 7 8
  std::string str;
  str.assign_range(r | std::views::transform([](int i) { return char('a' + i); }));
  str.append_range(std::string_view("!"));

  for (int x : d) std::printf("%d ", x);
  std::printf("| %zu | %s\n", s.size(), str.c_str());
}
```

本机输出 `7 8 1 2 3 1 2 3 1 2 3 | 5 | bcd!`。

| 成员 | 适用的容器 |
|---|---|
| `C(from_range, rg, ...)` | 所有序列容器、关联容器、无序容器、`string`、容器适配器 |
| `insert_range` | 序列容器（`forward_list` 是 `insert_range_after`）、关联容器、无序容器、`string` |
| `assign_range` | 序列容器、`string` |
| `append_range` / `prepend_range` | 有 `push_back` / `push_front` 的序列容器，以及 `string`（只有 `append_range`） |
| `push_range` | `stack`、`queue`、`priority_queue` |
| `replace_with_range` | `string` |

`append_range` 和 `prepend_range` 是 SG9（范围研究组）要求加的，最初叫 `push_back_range` 和 `push_front_range`，LEWG 后来要求改成现在的名字。`prepend_range` 保持元素原来的顺序（[[sequence.reqmts#99]] 的注 2），[[P1206R7]] 的理由是反序会让大多数人意外，而且反序需要双向范围，会让它少很多用处；需要反序时写 `views::reverse`。

## 措辞

[[P1206R7]] 的措辞分两部分。

第一部分在范围库。[[ranges.syn]] 增加了 `from_range_t` 和 `from_range`，以及四个 `to` 的声明。新的 [[range.utility.conv]] 分成三个子条款：总述和仅用于说明的辅助概念（general），两个带范围实参的 `to`（to），两个返回管道闭包的 `to`（adaptors）。总述的第一句概括了整个设计：

!!! std
    The range conversion functions construct an object (usually a container) from a range, by using a constructor taking a range, a `from_range_t` tagged constructor, or a constructor taking a pair of iterators, or by inserting each element of the range into the default-constructed object. ([[range.utility.conv.general#1]])

    范围转换函数用四种方式之一从范围构造对象（通常是容器），依次对应 ¶2.1.1 到 ¶2.1.4。

管道形式不是适配器，返回的是一个范围适配器闭包对象（[[g:range-adaptor-closure-object|range adaptor closure object]]，[[range.utility.conv.adaptors#2]]），所以可以写在 `|` 右边，也可以和其他闭包组合。

第二部分在容器库。[[container.requirements.general#2]] 增加 *container-compatible-range*；序列容器、关联容器、无序容器的要求表各增加了 `X(from_range, rg)`、`insert_range` 等行，例如 [[sequence.reqmts#11]] 到 ¶14；每个容器的类概要增加对应的成员和推导指引。推导指引的范围形参写成转发引用，R7 的修订记录说这是为了防止数组退化成指针。

论文还加了两个特性测试宏：`__cpp_lib_ranges_to_container` 对应 `ranges::to`，`__cpp_lib_containers_ranges` 对应容器的新成员，R7 的修订记录特意说明是新增宏，而不是改 `__cpp_lib_ranges` 的值。

## 后果

### 后续修正

`ranges::to` 的措辞在 C++23 定稿前后被 LWG 修了好几次。下面是改变了今天条文的几个问题报告：

| 问题 | 原来的写法 | 修正 |
|---|---|---|
| [[LWG3785]] | 第一步就检查 `convertible_to<range_reference_t<R>, range_value_t<C>>`，`C` 必须是范围 | 改为 `C` 不是 `input_range` 时跳过这项检查，于是可以转换成不是范围、但能由范围构造的类型（C++23） |
| [[LWG3847]] | 只有约束 `!view<C>`，`to<const std::string_view>` 能绕过它，返回一个可能悬垂的视图 | 增加 *Mandates*：`C` 必须是 cv 非限定的类类型（C++23） |
| [[LWG3733]] | ¶2.1.3 用 *cpp17-input-iterator* 概念判断迭代器 | 改为检查 `iterator_traits<...>::iterator_category` 派生自 `input_iterator_tag`（C++23） |
| [[LWG3984]] | 递归分支写 `r \| views::transform(...)`，`r` 是不可借用的非视图左值（如左值 `owning_view`）时非良构 | 改为 `ref_view(r) \| views::transform(...)`（C++26） |
| [[LWG4016]] | 追加分支用 `back_inserter` 或 `inserter`，要求和检查对不上，还会多构造一个临时元素 | 改为直接调用成员，`emplace_back` 优先（C++26） |
| [[LWG4121]] | 追加分支对关联容器调用 `c.emplace(c.end(), x)`，而关联容器的 `emplace` 不接受位置 | 改用 `emplace_hint(c.end(), x)`（C++26 定稿之后） |

这些修正和 P2846R6 合起来，就是今天 [[range.utility.conv.to#2]] 与 [[range.utility.conv.general#4]]、¶5 的样子。

### 兼容性与实现

P1206 只增加了新的函数和成员，[[diff.cpp20]] 里没有对应的不兼容条目。新成员的名字都带 `_range` 后缀、构造函数都带标签，这本身就是为了不改变已有调用的重载决议。

本机 Clang 23 加 libc++：`-std=c++23` 和 `-std=c++2c` 下两个宏的值都是 `202202`，`-std=c++20` 下都未定义。上面的例子都在 `-std=c++2c` 下通过 `-Wall -Wextra -pedantic`，`alloc.cpp` 加 ASan 和 UBSan 运行无报告。libc++ 的追加分支已经按 [[LWG4016]] 优先调用 `emplace_back`；对一个只有 `emplace_hint` 和 `insert` 的自定义容器，它调用的是 `insert`，还没有跟上 [[LWG4121]]。`reserve_hint` 尚未实现。

## 思考题

!!! question "1. `std::vector<int> v(std::from_range, r)` 和 `auto v = r | std::ranges::to<std::vector<int>>()` 有什么区别？"

<details markdown="1">
<summary>答案</summary>

对 `vector` 和元素能直接转换的范围，没有区别：`ranges::to` 按 [[range.utility.conv.to#2]] 走到 ¶2.1.2，调用的正是这个标签构造函数（假设 ¶2.1.1 不适用；`vector<int>` 没有不带标签的范围构造函数）。

差别在其他情况。`ranges::to` 能用于没有标签构造函数的非标准容器（退到迭代器对或追加），能递归处理范围的范围，能省略元素类型写成 `to<std::vector>()`，还能放在管道末尾。标签构造函数则是容器自己的接口，也是 `ranges::to` 用来调用更高效实现的入口。
</details>

!!! question "2. 为什么 `std::vector v{lst};` 不能像 `std::string s{sv};` 那样被理解为按范围构造？"

<details markdown="1">
<summary>答案</summary>

`vector` 有 `initializer_list<T>` 构造函数，花括号初始化优先考虑它；CTAD 用 `lst` 的类型推导出 `T = list<int>`，得到只有一个元素的 `vector<list<int>>`。这个含义在 C++17 起就已确定，[[P1206R1]] 放弃不带标签的范围构造函数正是因为它会和这条规则冲突。按范围构造要写 `std::vector v(std::from_range, lst);`。
</details>

!!! question "3. `std::ranges::to<std::unordered_set<int>>(v)` 会先调用 `unordered_set::reserve` 吗？"

<details markdown="1">
<summary>答案</summary>

不会。第一，`unordered_set` 有 `from_range` 标签构造函数，`ranges::to` 在 ¶2.1.2 就停下了，根本走不到预留加追加的 ¶2.1.4；预留桶的工作由容器的构造函数自己决定。第二，即使是一个没有标签构造函数、但有 `reserve` 的无序容器，它也没有 `capacity()`，不满足 *reservable-container*（[[range.utility.conv.general#3]]），`if constexpr` 的条件为假。[[P1206R7]] 要求三个成员同时存在，正是为了避开无序容器这种名字相同、语义不同（预留桶而不是元素空间）的 `reserve`。
</details>
