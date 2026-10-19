---
title: Ranges 的设计
summary: 范围库的几个核心设计决定：迭代器加哨位、概念层级、视图与容器的区分、惰性求值、begin() 缓存、借用与悬垂、管道、ranges::to 和投影，以及它们各自带来的后果和常见陷阱。
status: draft
order: 82
since: c++20
papers: P0896R4, P0184R0, P2415R2, P2718R0, P2387R3, P1206R7, P2210R2
related: ranges, range.req, range.view, range.all, range.utility, range.dangling, range.adaptors, range.filter, range.transform, range.utility.conv, iterator.concepts, iterator.concept.sentinel, range.take, range.split, range.factories, stmt.ranged, topics/dangling-references, topics/concepts
tags: 标准库, 范围, 视图, 惰性求值, 悬垂, 专题
updated: 2026-10-19
---

!!! tldr
    - 范围是一个迭代器加一个哨位。哨位可以是另一种类型，所以以 `'\0'` 结尾的字符串、无限序列、取前 n 个都不必先算出终点。
    - 适配器按底层满足哪些概念决定自己的能力：`transform` 保留随机访问和长度，`filter` 降为双向、失去长度。算法用同一组概念决定接受什么。
    - 视图是惰性的：构造管道时不计算任何东西，每次解引用才调用函数。`transform | filter` 会让变换函数对通过的元素各多调用一次。
    - `filter`、`drop`、`reverse` 等为了让 `begin()` 摊还常数时间而缓存结果，代价是 const 的视图不能遍历，底层修改之后视图可能给出陈旧结果甚至未定义行为。
    - 视图通常不拥有元素。算法对非借用的右值范围返回 `ranges::dangling`，C++23 延长了范围 `for` 初始化器里临时量的寿命，其余悬垂要靠程序员自己避免。

## 从迭代器对到管道

从订单簿里按数量降序取出大单的代码，用迭代器对和用范围分别这样写：

<div class="compare" markdown="1">

```cpp
std::sort(book.begin(), book.end(),
  [](const Order& a, const Order& b) {
    return a.qty > b.qty;
  });
std::vector<std::string> names;
for (auto it = book.begin();
     it != book.end(); ++it)
  if (is_big(*it))
    names.push_back(it->sym);
```

```cpp
std::ranges::sort(book,
                  std::ranges::greater{},
                  &Order::qty);
auto names = book
  | std::views::filter(is_big)
  | std::views::transform(&Order::sym)
  | std::ranges::to<std::vector>();
```

</div>

右边有三处变化。算法直接接受整个范围，不会把两个容器的迭代器配错。比较器换成了 `greater` 加一个**投影**（projection）`&Order::qty`，意思是先取出 `qty` 再比较。中间的循环换成了一条管道，`filter` 和 `transform` 都不复制元素，最后才由 `ranges::to` 收集到 `vector`。

同样的写法有时会出乎意料地编译失败：

```cpp run error
#include <cstdio>
#include <ranges>
#include <vector>
void print(const auto& r) {
  for (int x : r) std::printf("%d ", x);
  std::puts("");
}
int main() {
  std::vector<int> v{1, 2, 3, 4, 5, 6};
  print(v | std::views::transform([](int x) { return x * 10; }));  // OK
  print(v | std::views::filter([](int x) { return x % 2 == 0; })); // error
}
```

本机 Clang 23 报告 `filter_view` 的 `begin` "is not marked const"。`transform` 的结果能以 const 遍历，`filter` 的结果不能。

有时又能编译，但悬垂：

```cpp run ub
#include <cstdio>
#include <ranges>
#include <string>
#include <vector>
struct Config {
  std::vector<std::string> keys{"listen_port", "log_level", "worker_threads"};
  const std::vector<std::string>& items() const { return keys; }
};
Config load() { return {}; }
int main() {
  auto lens = load().items()
            | std::views::transform([](const std::string& s) { return s.size(); });
  for (std::size_t n : lens) std::printf("%zu ", n);   // UB：Config 已经销毁
  std::puts("");
}
```

本机 Clang 23 没有任何警告，加 `-fsanitize=address` 运行时在 `ref_view::begin` 里报告 stack-use-after-scope。

这两个现象都不是实现的缺陷，而是范围库几个设计决定的直接后果。下面逐个讲这些决定。

## 范围是迭代器加哨位

`range` 概念只要求能对一个左值调用 `ranges::begin` 和 `ranges::end`（[[range.range#1]]）。`begin` 给出迭代器，`end` 给出**哨位**（sentinel）。哨位只需要能和迭代器比较相等，类型可以不同（[[iterator.concept.sentinel]]）。

为什么不像 C++98 那样要求首尾同类型？因为很多序列的终点不是一个位置，而是一个条件：

```cpp run ok
#include <algorithm>
#include <cstdio>
#include <iterator>
#include <numeric>
#include <ranges>

struct null_sentinel {   // 终点：遇到 '\0'
  friend bool operator==(const char* p, null_sentinel) { return *p == '\0'; }
};

int main(int argc, char** argv) {
  const char* s = argc > 1 ? argv[1] : "hello, ranges";
  auto str = std::ranges::subrange(s, null_sentinel{});   // 不先调用 strlen
  auto comma = std::ranges::find(str, ',');
  std::printf("%td\n", comma - s);                        // 5

  static_assert(!std::ranges::common_range<decltype(str)>);
  static_assert(!std::ranges::sized_range<decltype(str)>);

  auto c = str | std::views::common;                      // 给旧接口用
  long n = std::accumulate(c.begin(), c.end(), 0L);
  // std::accumulate(str.begin(), str.end(), 0L);         // error：首尾类型不同
  std::printf("%ld\n", n);
}
```

`find` 每走一步就和 `null_sentinel` 比较一次，也就是检查一次 `*p == '\0'`，只遍历一遍。如果要求首尾同类型，就得先 `strlen` 再查找，遍历两遍。标准库里同样的例子还有无上界的 `views::iota(0)`（终点是 `unreachable_sentinel_t`，与什么都不相等）、`take_while`（终点里装着谓词）、`views::istream`（终点是 `default_sentinel_t`，比较时检查流的状态）。

代价是出现了两类范围。首尾类型相同的叫 [[g:common-range|common range]]（[[range.refinements#4]]），标准容器都是；不同的就不是。只认一种类型的旧接口，比如 `std::accumulate` 和容器的迭代器对构造函数，要先用 `views::common` 转换（[[range.common]]）。语言这一侧在 C++17 就做了准备：[[P0184R0]] 让范围 `for` 的 `begin` 和 `end` 分别用 `auto` 声明（[[stmt.ranged#1]]），从此范围 `for` 可以直接遍历非 common 的范围。

算法也因此改了返回值。终点是一个条件时，走到终点得到的迭代器是算法算出来的新信息，所以 `ranges::` 算法尽量把它返回，例如 `ranges::copy` 返回输入和输出两端的迭代器。所有接受范围的重载，行为都等价于先取 `ranges::begin(r)` 和 `ranges::end(r)`，再调用迭代器加哨位的版本（[[algorithms.requirements#14]]）。

## 概念层级：能力决定行为

范围的能力用一组概念描述，详细定义见 [[range.req]]：

| 维度 | 概念 | 问的是什么 |
|---|---|---|
| 遍历方式 | `input_range` → `forward_range` → `bidirectional_range` → `random_access_range` → `contiguous_range` | 迭代器能怎样移动；能否多遍遍历；元素是否在连续内存中 |
| 长度 | `sized_range` | 能否在常数时间内得到元素个数（[[range.sized#2]]） |
| 终点 | `common_range` | 哨位和迭代器是否同类型 |
| 代价 | `view` | 移动是否 O(1)、复制是否廉价（下一节） |
| 生命周期 | `borrowed_range` | 迭代器是否不依赖这个范围对象本身存活 |
| 能否进管道 | `viewable_range` | 能否用 `views::all` 安全地转成视图 |

适配器读取底层的这些性质，算出自己的性质；算法读取它们，决定接受什么、用哪种实现。在本机 Clang 23 上逐条检查：

```cpp run ok
#include <algorithm>
#include <list>
#include <ranges>
#include <span>
#include <sstream>
#include <vector>
namespace r = std::ranges;
namespace vw = std::views;
using V = std::vector<int>;
inline V v;
inline std::list<int> l;
constexpr auto sq = [](int x) { return x * x; };
constexpr auto ev = [](int x) { return x % 2 == 0; };

using T = decltype(v | vw::transform(sq));       // 一对一：保留随机访问、长度、common
static_assert(r::random_access_range<T> && r::sized_range<T> && r::common_range<T>);
static_assert(!r::contiguous_range<T>);           // 元素是算出来的，不在内存里

using F = decltype(v | vw::filter(ev));           // 跳跃前进：最多双向，没有长度
static_assert(r::bidirectional_range<F> && !r::random_access_range<F>);
static_assert(!r::sized_range<F> && r::common_range<F>);

using TV = decltype(v | vw::take(3));             // 底层随机访问且有长度：终点可以算出来
static_assert(r::contiguous_range<TV> && r::sized_range<TV> && r::common_range<TV>);
using TL = decltype(l | vw::take(3));             // list：终点要数着走，变成非 common
static_assert(r::sized_range<TL> && !r::common_range<TL>);

using TW = decltype(v | vw::take_while(ev));      // 终点是条件
static_assert(r::contiguous_range<TW> && !r::sized_range<TW> && !r::common_range<TW>);

static_assert(std::same_as<decltype(std::span(v) | vw::take(3)), std::span<int>>);

template<class R> concept sortable_r = requires(R&& x) { r::sort(x); };
static_assert(sortable_r<V&> && !sortable_r<F&> && !sortable_r<std::list<int>&>);
using IS = decltype(vw::istream<int>(std::declval<std::istream&>()));
static_assert(r::input_range<IS> && !r::forward_range<IS>);
template<class R> concept reversible = requires(R&& x) { x | vw::reverse; };
static_assert(reversible<F&> && !reversible<IS&>);
int main() {}
```

几个值得注意的结果：

- `views::take(3)` 作用于 `span` 时直接返回一个更短的 `span`，不包装成 `take_view`（[[range.take]]）。适配器在能保持原类型时就保持原类型。
- 同样是 `take(3)`，作用于 `vector` 是 common range，作用于 `list` 就不是：`list` 走不到第 3 个元素之前算不出终点迭代器，`take_view` 只好用计数迭代器和一个哨位。
- `ranges::sort` 要求随机访问，所以不能排序 `filter` 的结果，也不能排序 `list`。`views::reverse` 要求双向，所以不能反转 `istream`。这些错误都发生在概念检查这一步，诊断会指出哪个约束不满足（概念的一般机制见 [[topics/concepts]]）。

## 视图与容器

适配器要把底层范围按值存起来。如果 `filter` 存的是 `vector` 的副本，管道每多一级就复制一次全部元素，惰性求值也就没有意义了。所以适配器的底层必须是**视图**（[[g:range-view|view]]）：移动是 O(1)，可复制时复制也是 O(1)，N 个副本析构的总代价是 O(N+M)，M 是元素个数（[[range.view#2]]）。

这些要求只关心代价，不关心所有权。`span`、`string_view` 不拥有元素，`owning_view` 拥有一个移进来的容器，二者都是视图；`vector` 不是，因为复制它要复制全部元素。语法上看不出这种差别，所以类型要通过继承 `view_interface` 或特化 `enable_view` 主动声明自己是视图（[[range.view]]）。

容器进入管道时，`views::all` 决定以什么方式进入（[[range.all.general#2]]）：

| 写法 | 底层 | 谁拥有元素 |
|---|---|---|
| `v \| views::filter(p)`，`v` 是左值 | `ref_view<V>`：只存一个指针 | `v` |
| `std::move(v) \| views::filter(p)` 或 `make_vec() \| views::filter(p)` | `owning_view<V>`：把容器移进来，只能移动 | 视图 |
| `ev \| views::reverse`，`ev` 本身是视图 | `ev` 的副本 | 与 `ev` 相同 |

开头的 `Config` 例子悬垂就是因为第一行：`load().items()` 是一个左值表达式，`views::all` 选了 `ref_view`，只记住了一个指向临时 `Config` 内部 `vector` 的指针。表达式是左值还是右值，决定了借用还是接管，这一点和这个对象实际能活多久无关。`ref_view` 与 `owning_view` 的细节见 [[range.all]]。

## 惰性求值与代价模型

构造管道时不访问任何元素，元素在遍历时逐个算出：`transform` 的迭代器每解引用一次就调用一次函数（[[range.transform]]），`filter` 的迭代器每前进一步就对经过的元素逐个调用谓词（[[range.filter]]）。代价因此取决于下游怎样使用迭代器，而不是管道怎么写。下面用两个带计数器的函数测量：

```cpp run ok
#include <algorithm>
#include <cstdio>
#include <ranges>
#include <vector>
int f_calls = 0, p_calls = 0;
int sq(int x) { ++f_calls; return x * x; }
bool even(int x) { ++p_calls; return x % 2 == 0; }
void report(const char* what) {
  std::printf("%-28s f=%d p=%d\n", what, f_calls, p_calls);
  f_calls = p_calls = 0;
}
int main() {
  std::vector<int> v{1, 2, 3, 4, 5, 6, 7, 8, 9, 10};
  namespace vw = std::views;

  auto a = v | vw::transform(sq);
  report("build transform");
  for (int x : a) (void)x;
  report("iterate transform");

  for (int x : v | vw::transform(sq) | vw::take(3)) (void)x;
  report("transform|take(3)");

  for (int x : v | vw::filter(even) | vw::transform(sq) | vw::take(3)) (void)x;
  report("filter|transform|take(3)");

  for (int x : v | vw::transform(sq) | vw::filter(even)) (void)x;
  report("transform|filter");

  auto t = v | vw::transform(sq);
  auto m = std::ranges::max_element(t);
  (void)*m;
  report("max_element(transform)");
  (void)std::ranges::max_element(v, {}, sq);
  report("max_element(v, {}, sq)");

  auto ev = v | vw::filter(even);
  for (int x : ev) (void)x;
  report("filter 1st pass");
  for (int x : ev) (void)x;
  report("filter 2nd pass");
  for (int x : ev | vw::reverse) (void)x;
  report("filter|reverse");
  (void)std::ranges::distance(ev);
  report("distance(filter)");
}
```

```text
build transform              f=0 p=0
iterate transform            f=10 p=0
transform|take(3)            f=3 p=0
filter|transform|take(3)     f=3 p=8
transform|filter             f=15 p=10
max_element(transform)       f=19 p=0
max_element(v, {}, sq)       f=18 p=0
filter 1st pass              f=0 p=10
filter 2nd pass              f=0 p=8
filter|reverse               f=0 p=20
distance(filter)             f=0 p=8
```

逐行解释：

- 构造不计算，`take` 让后面的元素根本不计算。10 个元素的 `transform` 加 `take(3)` 只调用 3 次 `sq`。
- `take` 之前的 `filter` 多找了一步。`filter | transform | take(3)` 的谓词调用了 8 次而不是 6 次。范围 `for` 在处理完第 3 个元素后仍然执行 `++`，`take_view` 的计数迭代器先让底层前进再把计数减到 0，底层的 `filter` 于是继续检查了 7 和 8。底层是输入范围时，这一步会真的从流里多读走一个值（见最后一节）。
- `transform | filter` 对通过的元素调用两次。10 + 5 = 15：谓词判断时解引用一次，循环体读取时又解引用一次。`transform_view` 不保存算出来的值，这正是惰性的代价。解决办法是调换顺序，或者用 C++26 的 `views::cache_latest`（[[range.cache.latest]]，本机 libc++ 还没有实现）。
- 算法会反复解引用。`max_element` 每次比较都解引用两个迭代器，9 次比较调用 18 次，最后的 `*m` 又一次，共 19 次。换成投影也一样是 18 次：投影的结果不缓存，每次比较都重新计算。变换很昂贵时，应当先把结果存进容器。
- 第二遍更便宜，复制以后又变贵。`filter` 的第一遍检查全部 10 个元素，第二遍只检查 8 个，因为 `begin()` 的位置被缓存了。`ev | vw::reverse` 中 `ev` 是左值视图，`views::all` 复制了它，副本不带缓存，要重新找 `begin()`（2 次）；`reverse_iterator` 每次解引用都要先把底层迭代器的副本退一步，每个元素被检查两遍（18 次），合计 20 次。最后一行的 `ranges::distance(ev)` 作用于左值 `ev`，用的是缓存的起点，同样是 8 次。

!!! pitfall "计数器不是好的谓词"
    上面的 `sq` 和 `even` 修改了全局变量，只是为了数调用次数。适配器要求函数和谓词**保持相等性**（equality-preserving，相同的输入给出相同的输出，[[concepts.equality]]），它们只是不依赖计数器的值才碰巧满足。实际代码中，把计数器的值算进结果的函数会让 `filter` 的结果无从预测。

## begin() 的缓存

`range` 的语义要求 `ranges::begin` 是摊还常数时间（[[range.range#2]]）。`filter_view` 的第一个元素要线性查找才能确定，所以标准规定它在第一次调用 `begin()` 时把结果缓存在视图对象里（[[range.filter.view#5]]，[[g:begin-caching]]）。`drop_view`、`drop_while_view`、`reverse_view`、`split_view`、`chunk_by_view` 在某些条件下也这样做。这个决定有三个后果。

第一，`begin()` 要写缓存，所以不是 const 成员。底层是前向范围时，const 的 `filter_view` 不是 `range`，开头的 `print(const auto&)` 因此编译失败。为什么不用 `mutable` 成员？那样两个线程同时调用 const 的 `begin()` 就会产生数据竞争，违反标准库对 const 成员函数的约定（[[res.on.data.races]]）。泛型函数接受视图时，形参写成 `auto&&` 或按值写 `std::ranges::view auto`，不要写 `const auto&`。

第二，缓存不随复制传播。复制一个 `filter_view` 得到的副本会重新查找（[[range.nonprop.cache]]），上一节的 `filter|reverse` 就是这样多出来 2 次调用的。

第三，缓存会过期。第一次遍历之后修改底层容器，视图记住的位置不会更新：

<div class="compare" markdown="1">

```cpp
auto ev = v | views::filter(even);
for (int x : ev) use(x);
v.push_back(6);   // 重新分配
for (int x : ev) use(x);
// UB：缓存的迭代器
// 指向已释放的旧缓冲区
```

```cpp
auto sq = v | views::transform(f);
for (int x : sq) use(x);
v.push_back(5);   // 重新分配
for (int x : sq) use(x);
// OK：transform 不缓存，
// 每次 begin() 都重新取 v.begin()
```

</div>

```cpp run ub
#include <cstdio>
#include <ranges>
#include <vector>
int main() {
  std::vector<int> v{1, 2, 3, 4};
  auto ev = v | std::views::filter([](int x) { return x % 2 == 0; });
  for (int x : ev) std::printf("%d ", x);   // 2 4：begin() 已被缓存
  v.push_back(6);                           // 容量不足，重新分配
  for (int x : ev) std::printf("%d ", x);   // UB：缓存的迭代器指向旧缓冲区
  std::puts("");
}
```

本机 ASan 在第 9 行报告 heap-use-after-free。不重新分配的修改不是 UB，但结果可能是陈旧的：把 `v[0]` 改成偶数之后，`ev` 仍然从缓存的位置开始。通过 `filter` 的迭代器把元素改得不再满足谓词，标准的注更明确地指出可能导致未定义行为。这些例子见 [[range.filter]]。

实用的规则是：视图在创建之后尽快使用，用完即弃；底层可能变化时，重新创建视图。

## 悬垂与借用范围

视图大多不拥有元素，比底层活得久就会悬垂。标准在类型层面挡住了一部分。

### 算法返回 `ranges::dangling`

```cpp run ok
#include <algorithm>
#include <ranges>
#include <vector>
int main() {
  std::vector<int> v{3, -7, 5};
  auto mag = [](int x) { return x < 0 ? -x : x; };

  auto it = std::ranges::max_element(v | std::views::transform(mag));
  static_assert(std::same_as<decltype(it), std::ranges::dangling>);
  // int m = *it;                 // error：dangling 不能解引用

  auto t = v | std::views::transform(mag);
  int m1 = *std::ranges::max_element(t);              // 左值：真正的迭代器
  int m2 = std::ranges::max(v | std::views::transform(mag));   // 只要值
  int m3 = *std::ranges::max_element(v, {}, mag);     // 投影：迭代器指向 v
  return (m1 == 7 && m2 == 7 && m3 == -7) ? 0 : 1;
}
```

返回迭代器的算法收到一个右值范围，而且这个范围不是**借用范围**（[[g:borrowed-range|borrowed range]]，迭代器不依赖范围对象本身存活）时，返回类型变成 `ranges::dangling`（[[range.dangling#1]]）。它什么操作都不支持，使用结果的代码就编译不过。

第一行容易让人意外：`v` 明明还活着。但 `transform_view` 的迭代器保存着指向视图对象的指针，要用里面的函数，而这个视图是一个临时量，分号处就销毁了。所以 `transform_view` 不是借用范围，`dangling` 挡住的是一个真实的悬垂。最后一行用投影代替 `transform`，算法直接在 `v` 上工作，返回的迭代器指向 `v` 的元素 `-7`，不再经过临时视图。

借用范围包括所有左值引用、`span`、`string_view`、`subrange`、`ref_view`、`iota_view`，以及底层借用时的 `take`、`drop`、`reverse` 等（[[range.range#4]]）。

### 范围 `for` 的临时量 {{c++23}}

开头的 `Config` 例子如果直接写在范围 `for` 里：

```cpp run title="cfg-for.cpp" std=c++23 ok
#include <cstdio>
#include <ranges>
#include <string>
#include <vector>
struct Config {
  std::vector<std::string> keys{"listen_port", "log_level", "worker_threads"};
  const std::vector<std::string>& items() const { return keys; }
};
Config load() { return {}; }
int main() {
  for (std::size_t n : load().items()
                     | std::views::transform([](const std::string& s) { return s.size(); }))
    std::printf("%zu ", n);   // 11 9 14
  std::puts("");
}
```

C++23 的 [[P2718R0]] 规定，范围 `for` 初始化器中创建的临时对象一律活到循环结束（[[class.temporary#7]]），所以临时 `Config` 在整个循环期间都存在。本机 Clang 23 用 `-std=c++23` 输出 `11 9 14`；用 `-std=c++20` 时 ASan 报告 stack-use-after-scope。

这项修复只对范围 `for` 的初始化器有效。先把管道存进变量再遍历，像开头那样，仍然悬垂。其余途径（从函数返回指向局部容器的视图、视图作为成员保存等）见 [[topics/dangling-references]] 和 [[range.dangling]]。

## 适配器对象与管道

`views::filter(r, p)` 和 `r | views::filter(p)` 是同一件事。后者能成立，是因为 `views::filter(p)` 先做了**部分应用**：它把 `p` 复制进一个**范围适配器闭包对象**（[[g:range-adaptor-closure-object|range adaptor closure object]]），等拿到范围时再调用 `views::filter(r, p)`（[[range.adaptor.object#8]]）。闭包对象 `C` 满足 `R | C` 等价于 `C(R)`；两个闭包对象 `C | D` 组成一个新的闭包，调用时等于 `D(C(r))`（[[range.adaptor.object#1]]）。

所以管道可以先组好、再接上范围，C++23 起自己写的适配器也能加入（[[P2387R3]]）：

```cpp run ok
#include <ranges>
#include <vector>
#include <cstdio>
struct evens_only : std::ranges::range_adaptor_closure<evens_only> {
  auto operator()(std::ranges::viewable_range auto&& r) const {
    return std::views::filter(std::forward<decltype(r)>(r),
                              [](int x) { return x % 2 == 0; });
  }
};
inline constexpr evens_only evens;
int main() {
  std::vector<int> v{1, 2, 3, 4, 5, 6};
  auto squares = std::views::transform([](int x) { return x * x; });
  auto pipeline = evens | squares | std::views::take(2);   // 还没有范围
  for (int x : v | pipeline) std::printf("%d ", x);       // 4 16
  std::puts("");
}
```

`pipeline` 只是一个函数对象，可以保存、传递、复用。它按值保存了 `take(2)` 的实参和两个 lambda，所以闭包里的实参也要注意生命周期：按引用捕获局部变量的 lambda 放进闭包，同样可能悬垂。各适配器的调用规则见 [[range.adaptors]]。

## `ranges::to` 与投影

视图是惰性的，需要真正的容器时用 C++23 的 `ranges::to`（[[P1206R7]]）。投影是 C++20 算法的另一个设计：几乎每个 `ranges::` 算法都多了一个 `Proj` 形参，默认是 `std::identity`，算法在比较或判断之前先对元素调用它（[[g:projection]]）。

```cpp run ok
#include <algorithm>
#include <cstdio>
#include <map>
#include <ranges>
#include <string>
#include <vector>
struct Order { std::string sym; int qty; };
int main() {
  std::vector<Order> book{{"NVDA", 120}, {"AAPL", 300}, {"MSFT", 50}};

  std::ranges::sort(book, {}, &Order::sym);                 // 按 sym 升序
  auto it = std::ranges::find(book, "MSFT", &Order::sym);   // 按 sym 查找
  auto big = std::ranges::max(book, {}, &Order::qty);       // 返回 Order 的副本
  std::printf("%s %d %s\n", book[0].sym.c_str(), it->qty, big.sym.c_str());

  auto qty = book | std::views::transform([](const Order& o) {
                      return std::pair{o.sym, o.qty};
                    })
                  | std::ranges::to<std::map<std::string, int>>();
  std::string syms = book | std::views::transform(&Order::sym)
                          | std::views::join_with(',')
                          | std::ranges::to<std::string>();
  std::printf("%d %s\n", qty["NVDA"], syms.c_str());        // 120 AAPL,MSFT,NVDA
}
```

输出 `AAPL 50 AAPL` 和 `120 AAPL,MSFT,NVDA`。

投影和 `transform` 的区别在于结果指向哪里。`ranges::find(book, "MSFT", &Order::sym)` 返回的是 `book` 里 `Order` 的迭代器，可以访问 `qty`；`ranges::find(book | views::transform(&Order::sym), "MSFT")` 返回的迭代器只能看到 `sym`。投影对每个元素的调用次数并不比 `transform` 少，上一节的计数已经说明了这一点。投影的类型要求由 `projected` 表达（[[projected#1]]）。

`ranges::to` 依次尝试直接用范围构造、用 `from_range` 标签构造、用迭代器对构造、默认构造后逐个追加（[[range.utility.conv.to#2]]）。`to<std::vector>()` 可以省略元素类型，由类模板实参推导补全。细节见 [[range.utility.conv]]。

## C++23 与 C++26 的新视图

| 设施 | 作用 | 标准 | 本机 libc++ |
|---|---|---|---|
| `views::zip`、`zip_transform` | 并排遍历几个范围 | C++23 | 有 |
| `views::adjacent<N>`、`pairwise` | 长度为 N 的滑动窗口，元素是 tuple | C++23 | 有 |
| `views::enumerate` | 同时给出下标和元素 | C++23 | 有 |
| `views::chunk`、`slide` | 按个数分块、运行时长度的滑动窗口 | C++23 | 没有 |
| `views::chunk_by` | 按相邻元素的关系分段 | C++23 | 有 |
| `views::stride` | 每隔 n 个取一个 | C++23 | 有 |
| `views::join_with` | 展平并插入分隔符 | C++23 | 有 |
| `views::cartesian_product` | 笛卡儿积 | C++23 | 没有 |
| `views::as_const`、`as_rvalue` | 元素只读、元素变成右值 | C++23 | 只有 `as_rvalue` |
| `views::repeat` | 重复同一个值 | C++23 | 有 |
| `ranges::to`、`range_adaptor_closure` | 收集到容器；自定义管道适配器 | C++23 | 有 |
| `std::generator` | 用协程写输入范围 | C++23 | 没有 |
| `views::concat` | 连接几个类型可以不同的范围 | C++26 | 有 |
| `views::indices` | `iota(0, n)` 的简写 | C++26 | 有 |
| `views::cache_latest`、`as_input` | 缓存解引用结果；降级为输入范围 | C++26 | 没有 |

本机 libc++ 一列是用 Clang 23 附带的 libc++ 编译检查得到的。

```cpp run ok
#include <cstdio>
#include <functional>
#include <ranges>
#include <string>
#include <vector>
namespace vw = std::views;
int main() {
  std::vector<std::string> sym{"AAPL", "MSFT", "NVDA"};
  std::vector<int> px{230, 410, 120};

  for (auto [s, p] : vw::zip(sym, px)) std::printf("%s=%d ", s.c_str(), p);
  std::puts("");                                       // AAPL=230 MSFT=410 NVDA=120
  for (auto [i, s] : vw::enumerate(sym)) std::printf("%td:%s ", i, s.c_str());
  std::puts("");                                       // 0:AAPL 1:MSFT 2:NVDA
  for (auto [a, b] : px | vw::pairwise) std::printf("%d ", b - a);
  std::puts("");                                       // 180 -290
  std::vector<int> t{1, 2, 5, 3, 4, 0};
  for (auto run : t | vw::chunk_by(std::ranges::less{})) {
    for (int x : run) std::printf("%d", x);
    std::printf(" ");
  }
  std::puts("");                                       // 125 34 0
  for (int x : vw::concat(px, t | vw::stride(2))) std::printf("%d ", x);
  std::puts("");                                       // 230 410 120 1 5 4
  for (int i : vw::indices(3)) std::printf("%d ", i);
  std::puts("");                                       // 0 1 2
}
```

`zip` 和 `enumerate` 的元素是装着引用的临时 tuple，结构化绑定得到的名字仍然指向底层元素，可以写回（[[range.zip]]、[[range.enumerate]]）。`zip` 和 `concat` 接受多个范围，没有管道写法。

## 常见陷阱

### `split` 与 `lazy_split`

```cpp run ok
#include <cstdio>
#include <ranges>
#include <sstream>
#include <string>
#include <string_view>
int main() {
  std::string_view csv = "AAPL,MSFT,,NVDA";
  for (auto part : csv | std::views::split(',')) {
    std::string_view s(part);                     // split：每段是连续的 subrange
    std::printf("[%.*s] ", int(s.size()), s.data());
  }
  std::puts("");                                  // [AAPL] [MSFT] [] [NVDA]

  std::istringstream in("a b c");
  auto chars = std::views::istream<char>(in);     // 输入范围（跳过空白）
  // chars | std::views::split('b');              // error：split 要求前向范围
  for (auto part : chars | std::views::lazy_split('b')) {
    for (char c : part) std::printf("%c", c);     // part 只能逐个元素遍历
    std::printf("|");
  }
  std::puts("");                                  // a|c|
}
```

`split` 要求前向范围，每一段都是底层的一个 `subrange`，切 `string_view` 时可以直接转成 `string_view`。`lazy_split` 能作用于输入范围，代价是每一段是一个惰性的内层范围，不能转成 `string_view`。C++20 最初的 `split` 是今天的 `lazy_split`，[[P2210R2]] 作为缺陷报告改名，并把 `split` 换成了今天的设计（[[range.split]]）。

### `istream` 只能遍历一遍，`take` 会多读一个

```cpp run ok
#include <cstdio>
#include <ranges>
#include <sstream>
int main() {
  std::istringstream in("1 2 3 4 5 6");
  auto nums = std::views::istream<int>(in);
  for (int x : nums | std::views::take(2)) std::printf("%d ", x);
  std::puts("|");                                 // 1 2 |
  for (int x : nums) std::printf("%d ", x);
  std::puts("|");                                 // 4 5 6 |
  static_assert(!std::ranges::forward_range<decltype(nums)>);
}
```

`3` 去哪了？第一个循环处理完 `2` 之后仍然执行 `++`，`take_view` 的计数迭代器让底层迭代器前进，从流里读走了 `3`，然后计数到 0，循环结束。第二个循环调用 `nums.begin()`，`basic_istream_view::begin()` 每次都先执行 `*stream_ >> value_`（[[range.istream.view]]），又读走一个值，于是从 `4` 开始。上一节 `filter | take(3)` 多检查两个元素也是同一个原因，只是在输入范围上，多读的值就丢掉了。

输入范围不保证第二次调用 `begin()` 得到相同的结果（[[range.range#3]]），把它交给两个算法、遍历两遍、复制视图再分别遍历，都会互相干扰。需要多遍处理时，先 `ranges::to<std::vector>()` 收集下来。必须恰好读 n 个值、一个也不多读时，写普通的循环 `for (int i = 0; i < n && in >> x; ++i)`。`take` 与 `take_while` 在输入范围上的行为见 [[range.take]]。

### 视图不该作为 `const&` 传递

见 begin() 的缓存一节：`const auto&` 收不下 `filter`、`drop_while`、`split`、`chunk_by` 等视图。函数模板接受范围时用 `auto&&` 转发引用；只接受视图时按值接收，并用 `std::move` 往下传。

## 思考题

!!! question "1"
    `std::ranges::find(std::views::iota(0) | std::views::take(10), 7)` 返回 `dangling` 吗？换成 `std::vector<int>{...} | std::views::take(10)` 呢？

<details markdown="1">
<summary>答案</summary>

前者不返回 `dangling`。`views::iota(0)` 没有上界，不是 sized range，所以 `take` 不能把它换成一个更短的 `iota_view`，结果是 `take_view<iota_view<int, unreachable_sentinel_t>>`。`take_view` 在底层借用时也借用，而 `iota_view` 是借用范围（迭代器自带当前值，不依赖视图对象），所以 `find` 返回真正的迭代器。换成有上界的 `views::iota(0, 100)`，`take(10)` 直接返回 `iota_view<int, int>`，结论相同。

后者返回 `dangling`。临时 `vector` 被移进 `owning_view`，`take_view<owning_view<vector<int>>>` 只在底层借用时才借用，`owning_view` 是否借用又随 `vector`，而 `vector` 不是借用范围。这也是正确的结果：`vector` 随这个临时视图一起销毁。
</details>

!!! question "2"
    为什么 `transform_view` 不缓存 `begin()`，而 `filter_view` 必须缓存？

<details markdown="1">
<summary>答案</summary>

`transform_view::begin()` 只是把底层的 `begin()` 包一层，底层是摊还常数时间，它也就是，不需要缓存。`filter_view::begin()` 要调用 `ranges::find_if` 找第一个满足谓词的元素，最坏是线性时间，只有缓存才能满足 [[range.range#2]] 的摊还常数时间要求（[[range.filter.view#5]]）。底层只是输入范围时，`filter_view` 不建模前向范围，`begin()` 本来就不要求保持相等性，标准也就不要求缓存。
</details>

!!! question "3"
    `auto r = v | views::filter(p); auto r2 = r | views::take(3);` 之后，先遍历 `r` 再遍历 `r2`，谓词在 `r2` 的第一个元素上会被重新调用吗？

<details markdown="1">
<summary>答案</summary>

会。`r` 是左值视图，`views::all(r)` 复制它（[[range.all.general#2]]），`r2` 里装的是 `r` 的副本。复制发生在遍历 `r` 之前，而且缓存本来就不随复制传播（[[range.nonprop.cache]]），所以 `r2` 第一次 `begin()` 时要重新查找。上文计数中 `filter|reverse` 多出的 2 次调用就是这样来的。
</details>
