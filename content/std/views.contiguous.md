---
title: 连续访问：span
summary: std::span 逐条精读——静态/动态 extent 与对象布局、每个构造函数的 Constraints/Preconditions/Hardened preconditions 与 explicit 条件、只允许限定转换的 U(*)[] 技巧、从 range 构造时的 borrowed_range 规则、推导指引、first/last/subspan 的编译期与运行期版本、加固的下标与 C++26 at()、as_bytes 与对象表示，以及悬垂、失效和没有 operator== 的来龙去脉
status: done
covers: *
papers: P0122R7, P1085R2, P2278R4, P2821R5, P2447R6
related: views, views.multidim, container.requirements, vector, array, basic.types.general, basic.lval, conv.qual, class.temporary, range.range
tags: 标准库, span, 视图, 加固, 对象表示, 悬垂
updated: 2026-10-18
---

`std::span<T, Extent>` 是 C++20 给"指针 + 长度"这对老搭档起的正式名字。C 接口里随处可见的 `(T* p, size_t n)`，到了 C++ 里终于可以折叠成一个参数，同时带上类型系统的三样好处：

- **长度跟着指针走**，不会在层层传参中丢失或张冠李戴；
- **长度可以是编译期常量**（`span<int, 4>`），这时 `span` 只存一个指针，还能在编译期拒绝尺寸不匹配的子视图；
- **元素类型的转换被卡死在限定转换上**，`span<Base>` 永远不会从 `Derived` 数组悄悄构造出来——这正是裸指针 `Base* p = derived_array` 最阴险的坑。

这一页覆盖 [views.contiguous] 的全部子条款：[span.syn]、[views.span] 下的七个子条款、[span.objectrep]。阅读前建议先看 [[views]] 导读里"视图不拥有存储"的约定。

## 概要：`dynamic_extent`、`maybe-static-ext` 与两个 ranges 特化（[span.syn]）

概要里有四样东西值得注意：

1. **`dynamic_extent`** 被定义为 `numeric_limits<size_t>::max()`。它是一个"不可能的长度"，用作模板实参时表示"长度到运行期才知道"。`mdspan` 的 `extents` 也复用它（[[views]]）。
2. 仅用于说明的概念 *integral-constant-like* 与变量模板 *maybe-static-ext*：如果一个类型 `T` 像 `integral_constant` 那样携带一个**非 `bool` 的整型**静态值 `T::value`（且满足 *constexpr-wrapper-like*），那么 *maybe-static-ext*`<T>` 就是那个值，否则是 `dynamic_extent`。它只服务于推导指引——让 `span(p, std::cw<4uz>)` 推导出 `span<T, 4>`。
3. `ranges::enable_view<span<...>>` 与 `ranges::enable_borrowed_range<span<...>>` 都特化为 `true`。前者让 `span` 满足 `ranges::view`；后者让对右值 `span` 调用的 ranges 算法返回真正的迭代器（[[g:borrowed-range]]，[[range.range]] ¶4）。
4. `as_bytes`/`as_writable_bytes` 的返回类型里，extent 被换算成 `sizeof(ElementType) * Extent` 字节——静态 extent 在字节视图里依然是静态的。

注释 `// mostly freestanding` 与 `// partially freestanding`：独立实现（freestanding）也要提供 `span`，只有会抛异常的 `at()` 被标为 *freestanding-deleted*。

## `span` 的对象模型（[span.overview]）

### 三句规范性断言（¶1–¶4）

!!! std
    A `span` is a view over a contiguous sequence of objects, the storage of which is owned by some other object.
    `span` 是连续对象序列上的视图，存储由另外某个对象拥有。

¶2：**所有成员函数都是常数时间**。这排除了任何"检查整段序列"的实现，也意味着 `span` 不可能提供按内容比较的 `operator==` 而又保持这个承诺（见下文"为什么没有 `operator==`"）。

¶3：`span<ElementType, Extent>` 是**平凡可复制类型**（[[g:trivially-copyable-type]]，[[basic.types.general]]）。这是一条对实现的硬性要求，意义在 ABI：拷贝构造函数和析构函数都平凡，于是在 Itanium C++ ABI 下 `span` 不属于"为调用目的而非平凡"（non-trivial for the purposes of calls）的类，按值传参时可以直接放进寄存器（x86-64 与 AArch64 上两个机器字的结构体正好占两个寄存器），不需要经过内存。按值传 `span` 和传两个裸参数一样便宜。

¶4：`ElementType` 必须是**完整的对象类型，且不是抽象类**。几个推论：

- `span<void>`、`span<int&>`、`span<int()>` 都不行（不是对象类型）；
- `span<int[3]>` **可以**——数组是对象类型。`int m[2][3]` 能直接转成 `span<int[3]>`，每个元素是一行；
- 违反这条是对模板实参要求的违反，标准对实现"不作任何要求"（[[res.on.functions]] ¶1），libc++ 直接用 `static_assert` 拒绝。

### 布局：静态 extent 只存一个指针

规范里的说明性成员是 `data_` 和 `size_` 两个，但这只是**说明性**的（exposition only）：既然 `size()` 只需"返回 *size_*"，而静态 extent 下 `size()` 必然等于 `Extent`，实现完全可以不存它。libc++ 为静态 extent 写了单独的偏特化：

```cpp run title="span-sizeof.cpp" ok
#include <cstdio>
#include <ranges>
#include <span>
#include <type_traits>

int main() {
  // libc++（64 位）输出：16 8 8
  std::printf("%zu %zu %zu\n", sizeof(std::span<int>), sizeof(std::span<int, 4>),
              sizeof(std::span<int, 0>));

  static_assert(std::is_trivially_copyable_v<std::span<int>>);   // [span.overview] ¶3
  static_assert(std::ranges::view<std::span<int>>);
  static_assert(std::ranges::borrowed_range<std::span<int>>);
  static_assert(!std::equality_comparable<std::span<int>>);      // 没有 operator==
}
```

尺寸是实现细节（标准没规定 `sizeof`），但"静态 extent 不付长度的存储代价"是设计意图，主流实现都这么做。

### 失效规则继承自底层存储（¶5）

!!! std
    For a `span` `s`, any operation that invalidates a pointer in the range `[s.data(), s.data() + s.size())` invalidates pointers, iterators, and references to elements of `s`.
    凡是使底层范围中的指针失效的操作，也使 `s` 的元素指针、迭代器和引用失效。

`span` 自己没有任何会使其失效的修改操作——它的失效**全部来自外部**。最典型的就是 `vector` 重新分配：

```cpp run title="span-invalidation.cpp" ub
#include <span>
#include <vector>

int main() {
  std::vector<int> v{1, 2, 3};
  std::span<int> s = v;
  v.push_back(4);       // 若发生重新分配，[s.data(), s.data() + 3) 中的指针全部失效
  return s[0];          // UB: span 不知道 vector 已经搬家
}
```

AddressSanitizer 会报 heap-use-after-free。哪些容器操作会使指针失效，见 [[container.requirements]] 中汇总的失效表和 [[vector]]。注意一个反直觉之处：`span` 本身的 `operator[]` 加固检查只比较下标和 `size()`，**对悬垂无能为力**——加固实现里这段代码照样是 UB。

### 成员类型

- `element_type` 就是 `ElementType`（可带 cv），`value_type` 是去掉 cv 的版本。`span<const int>::value_type` 是 `int`——和容器一样，`value_type` 永远是"复制出来的那个值"的类型。
- `size_type` 是 `size_t`，`difference_type` 是 `ptrdiff_t`。
- `iterator` 由实现定义；`const_iterator` 是 `std::const_iterator<iterator>`。C++20 原版的 `span` 一度没有 `cbegin`，因为"`const span` 的迭代器仍可写"会让 `cbegin` 名不副实；C++23 用 `std::const_iterator` 统一解决了这个问题（[[P2278R4]]）。
- `extent` 是静态数据成员，值为 `Extent`。

## 构造函数逐个看（[span.cons]）

先给一张总表，后面逐条展开。"explicit?" 一列只针对 `extent != dynamic_extent` 的情形，动态 extent 的 `span` 所有构造函数都是隐式的。

| 构造函数 | 段落 | *Constraints* 要点 | *Hardened preconditions* | 静态 extent 时 explicit? |
|---|---|---|---|---|
| `span()` | ¶1–¶2 | `Extent` 为 0 或 `dynamic_extent` | — | — |
| `span(It first, size_type count)` | ¶3–¶7 | `It` 满足 `contiguous_iterator`；只允许限定转换 | `count == extent` | 是 |
| `span(It first, End last)` | ¶8–¶12 | 同上；`End` 是 `sized_sentinel_for<It>` 且**不能**转换为 `size_t` | `last - first == extent` | 是 |
| `span(element_type (&)[N])`、`span(array<T,N>&)`、`span(const array<T,N>&)` | ¶13–¶15 | `N == extent`（或动态）；只允许限定转换 | — | 否 |
| `span(R&& r)` | ¶16–¶20 | contiguous + sized；borrowed 或元素为 const；不是 `span`/`array`/内建数组 | `ranges::size(r) == extent` | 是 |
| `span(const span<U, N>&)` | ¶22–¶26 | extent 兼容；只允许限定转换 | `s.size() == extent` | 仅当本身静态、源动态 |

### 默认构造（¶1–¶2）

*Constraints*：`Extent == dynamic_extent || Extent == 0`。一个声称"恰好有 4 个元素"的 `span<int, 4>` 不能凭空造出来，所以它**没有默认构造函数**——放进需要默认构造的容器（例如 `std::array<span<int,4>, 2>` 值初始化）时会碰壁。后置条件是 `size() == 0 && data() == nullptr`。

### 迭代器 + 长度、迭代器 + 哨兵（¶3–¶12）

¶3 和 ¶8 的核心约束是：

```cpp
is_convertible_v<U(*)[], element_type(*)[]>   // U 是 remove_reference_t<iter_reference_t<It>>
```

这是整个 `span` 设计里最值得记住的技巧。为什么不直接写 `is_convertible_v<U*, element_type*>`？因为指针转换允许**派生类到基类**：`Derived*` → `Base*` 合法，但把 `Derived` 数组当作 `Base` 数组按 `sizeof(Base)` 步进，是经典的 UB。而**指向数组的指针**之间只允许限定转换（[[conv.qual]]）：`int(*)[]` → `const int(*)[]` 可以，`Derived(*)[]` → `Base(*)[]` 不行。标准里的注释也说得很直白：

!!! std
    The intent is to allow only qualification conversions of the iterator reference type to `element_type`.
    意图是只允许从迭代器引用类型到 `element_type` 的限定转换。

（这是注，不具规范效力；规范效力来自 `is_convertible_v` 本身。）

¶4/¶9 的 *Preconditions*（违反为 {{ub}}）：`[first, first + count)` 或 `[first, last)` 是有效范围，并且 `It` **建模**（models）而不只是**满足**（satisfies）`contiguous_iterator`。语法上满足、语义上不连续的迭代器传进来，后果自负。

¶5/¶10 的 *Hardened preconditions*：静态 extent 时长度必须恰好等于 `extent`。

¶8.4 是一个消歧约束：只要 `End` 能转换为 `size_t`，`(It, End)` 重载就退出决议。这保证了 `span(first, n)` 中整数类的第二实参永远被解释为**长度**，而不会被推导成哨兵类型 `End`——否则推导出的精确匹配本来会胜过需要整数转换的 `size_type` 形参（见文末思考题 3）。

¶12：`(It, End)` 版本的 *Throws* 是"`last - first` 抛什么就抛什么"——对用户自定义迭代器，减法理论上可以抛异常，所以这个构造函数没有 `noexcept`。

### 数组与 `std::array`（¶13–¶15）

三个重载共享一组规则。¶13.1：`extent == dynamic_extent || N == extent`——尺寸不匹配时构造函数**不参与重载决议**，而不是运行期检查。这些构造函数从来不是 `explicit` 的：编译期已经确认尺寸正确，没有理由要求显式。

¶14 的注 4 解释了内建数组版本为什么写成 `type_identity_t<element_type> (&arr)[N]`：`type_identity_t` 让参数处于**不推导语境**，防止类模板实参推导（CTAD）通过这个构造函数推出奇怪的结果；CTAD 交给专门的推导指引（[span.deduct]）。

```cpp run title="span-extent-explicit.cpp" error
#include <array>
#include <span>
#include <vector>

int raw[4];
std::array<int, 4> arr;
std::vector<int> vec(4);

std::span<int, 4> a = raw;   // OK：数组构造函数从不 explicit
std::span<int, 4> b = arr;   // OK
std::span<int, 4> c{vec};    // OK：直接初始化可以调用 explicit 构造函数
std::span<int, 4> d = vec;   // error: range 构造函数 explicit(extent != dynamic_extent)
std::span<int, 3> e = raw;   // error: N == extent 不满足，构造函数不是候选
std::span<int, 4> f;         // error: 默认构造要求 Extent 为 0 或 dynamic_extent
```

为什么 `vector` → `span<int, 4>` 必须显式？因为 `vector` 的长度是运行期的，编译器无法验证它恰好是 4；`explicit` 是在源码里留下一个"我担保尺寸正确"的签名，而真正的检查交给加固前置条件。

### 从 range 构造（¶16–¶20）

这是最通用、也最容易出事的构造函数。¶16 的约束逐条看：

- ¶16.1：`R` 满足 `ranges::contiguous_range` **和** `ranges::sized_range`。`std::deque`、`std::list` 不连续，`vector<bool>` 的迭代器不是 `contiguous_iterator`——都被挡在门外。
- ¶16.2：**要么 `R` 满足 `borrowed_range`，要么 `element_type` 是 const。**
- ¶16.3–¶16.5：`R` 不是 `span`、`array` 或内建数组的特化——这些有专门的构造函数，排除掉是为了避免重载歧义、并让编译期尺寸检查生效。
- ¶16.6：同样只允许限定转换。

¶16.2 需要仔细读。`R&&` 是转发引用：传左值 `vector<int>& v` 时 `R` 推导为 `vector<int>&`，而 [[range.range]] ¶3 定义 `borrowed_range<T>` 时对**左值引用类型总是成立**。所以这条规则实际上只约束**右值**实参：

!!! std
    Either `R` satisfies `ranges::borrowed_range` or `is_const_v<element_type>` is `true`.
    要么 `R` 满足 `borrowed_range`，要么元素类型是 const。

设计意图：`void f(span<const int>)` 应该能接受 `f(make_vector())`——临时对象活到完整表达式结束，在 `f` 执行期间足够安全；而 `span<int>` 从临时 `vector` 构造几乎总是 bug（往一个马上要销毁的对象里写有什么意义？），所以直接拒绝。

```cpp run title="span-range-ctor.cpp" error
#include <span>
#include <vector>

std::vector<int> make();
void read(std::span<const int>);
void write(std::span<int>);

void f() {
  read(make());                   // OK：元素是 const，允许从非 borrowed 的右值构造
  write(make());                  // error: vector 右值不是 borrowed_range，元素又不是 const
  std::vector<bool> vb(8);
  read(std::span<const bool>(vb)); // error: vector<bool> 不是 contiguous_range
}
```

¶17 把 ¶16 的语法要求再写一遍成语义要求（*models*），¶18 是静态 extent 的加固尺寸检查，¶19 用 `ranges::data(r)` 与 `ranges::size(r)` 初始化，¶20 说这两者抛什么构造函数就抛什么。

### 拷贝与 span 之间的转换（¶21–¶27）

¶21 与 ¶27：拷贝构造与拷贝赋值都是 `= default` 的 `noexcept` 平凡操作，后置条件就是"指针和长度相等"。

¶22–¶26 是 `span<U, N>` → `span<T, M>` 的转换构造函数：

- ¶22.1：extent 兼容——任一方是动态，或两者相等。`span<int, 4>` → `span<int, 3>` 根本不是候选。
- ¶22.2：只允许限定转换。`span<int>` → `span<const int>` 可以，反方向不行。
- ¶23：若目标是静态 extent，*Hardened precondition* 要求 `s.size() == extent`。
- ¶26：`explicit` 的条件是 `extent != dynamic_extent && OtherExtent == dynamic_extent`——**只有"动态 → 静态"需要显式**，其余方向（静态 → 动态、静态 → 相同静态、动态 → 动态）都是隐式的。

```cpp run title="span-conversions.cpp" error
#include <span>

struct Base { int x; };
struct Derived : Base { int y; };

int buf[4];
Derived d[3];
std::span<int>    dyn = buf;
std::span<int, 4> fix = buf;

std::span<const int> c1 = dyn;   // OK：int → const int 是限定转换
std::span<int>       a  = fix;   // OK：静态 → 动态，隐式
std::span<int, 4>    b{dyn};     // OK：动态 → 静态，必须显式；Hardened precondition: dyn.size() == 4
std::span<int>       c2 = c1;    // error: 丢掉 const
std::span<Base>      e  = d;     // error: Derived(*)[] 不能转换为 Base(*)[]
std::span<int, 4>    g  = dyn;   // error: 动态 → 静态是 explicit 的
std::span<int, 3>    h{fix};     // error: 两个静态 extent 不相等，构造函数不是候选
```

### 当前草案中没有 `initializer_list` 构造函数

[[P2447R6]] 曾在 C++26 周期为 `span` 加入一个 `explicit(extent != dynamic_extent) span(initializer_list<value_type>)` 构造函数，目的是让 `void f(span<const int>); f({1, 2, 3});` 能工作。**但截至本文核对的草案，[span.cons] 里已经没有这个构造函数**，[support.limits] 的特性测试宏表里也没有 `__cpp_lib_span_initializer_list`。本页以当前草案为准。

这个构造函数的争议点有两个，都值得了解：

1. **悬垂几乎是必然的**。`span<const int> s = {1, 2, 3};` 中，`initializer_list` 的底层数组是临时对象（[[dcl.init.list]]），在完整表达式结束时就销毁；只有用作函数实参时它才是安全的。
2. **它会改变已有代码的含义**。花括号初始化优先考虑 `initializer_list` 构造函数（[[over.match.list]]）。像 `span<const std::any> s{ptr, n}` 这样原本调用"指针 + 长度"的代码，在有了这个构造函数后会变成"含两个 `any` 的列表"。

当前草案下（以及本地 libc++ 下），`f({1, 2, 3})` 是 {{ill-formed}}——三个实参的花括号列表找不到对应的构造函数。不过 `std::initializer_list<int>` 本身是连续、有大小的 range，元素又是 const，所以**显式**给出一个 `initializer_list` 对象仍能经由 ¶16 的 range 构造函数转换成 `span<const int>`；悬垂问题同样存在。

```cpp run title="span-init-list.cpp" error
#include <initializer_list>
#include <span>

void f(std::span<const int>);

void g() {
  std::initializer_list<int> il{1, 2, 3};
  f(il);          // OK：initializer_list 是 contiguous + sized range，元素为 const
  f({1, 2, 3});   // error: 当前草案没有 initializer_list 构造函数
}
```

## 推导指引（[span.deduct]）

概要中给了五条推导指引：

| 实参 | 推导结果 | 来源 |
|---|---|---|
| `(It, EndOrSize)` | `span<remove_reference_t<iter_reference_t<It>>, maybe-static-ext<EndOrSize>>` | ¶1：`It` 须满足 `contiguous_iterator` |
| `T (&)[N]` | `span<T, N>` | |
| `array<T, N>&` | `span<T, N>` | |
| `const array<T, N>&` | `span<const T, N>` | |
| `R&&` | `span<remove_reference_t<range_reference_t<R>>>`（动态） | ¶2：`R` 须满足 `contiguous_range` |

要点：

- 从 `vector` 等 range 推导出的永远是**动态** extent，即使 range 的大小在编译期已知（比如 `std::ranges::single_view`）。
- `(It, count)` 中的长度如果是普通整数，结果是动态 extent；如果是携带静态值的类型（`std::integral_constant<size_t, 2>`、C++26 的 `std::cw<2uz>`），*maybe-static-ext* 会提取出静态 extent。
- `const array` 推导出 `span<const T, N>`——const 性从容器传递到元素。

```cpp run title="span-ctad.cpp" ok
#include <array>
#include <span>
#include <type_traits>
#include <utility>
#include <vector>

int raw[4];
std::array<int, 3> arr;
const std::array<int, 3> carr{};
std::vector<int> vec(5);

std::span a = raw;                     // span<int, 4>
std::span b = arr;                     // span<int, 3>
std::span c = carr;                    // span<const int, 3>
std::span d = vec;                     // span<int>
std::span e{vec.data(), 2};            // span<int>：2 是普通 int，extent 动态
std::span f{vec.data(), std::integral_constant<std::size_t, 2>{}};  // span<int, 2>
std::span g{raw + 0, std::cw<2uz>};    // span<int, 2>

static_assert(std::is_same_v<decltype(a), std::span<int, 4>>);
static_assert(std::is_same_v<decltype(b), std::span<int, 3>>);
static_assert(std::is_same_v<decltype(c), std::span<const int, 3>>);
static_assert(std::is_same_v<decltype(d), std::span<int>>);
static_assert(std::is_same_v<decltype(e), std::span<int>>);
static_assert(std::is_same_v<decltype(f), std::span<int, 2>>);
static_assert(std::is_same_v<decltype(g), std::span<int, 2>>);

int main() {}
```

## 子视图：`first`、`last`、`subspan`（[span.sub]）

每个操作都有**模板版本**（长度是模板实参）和**运行期版本**（长度是函数实参）两套：

| 函数 | 段落 | *Mandates*（编译期） | *Hardened preconditions*（运行期） | 返回的 extent |
|---|---|---|---|---|
| `first<Count>()` | ¶1–¶3 | `Count <= Extent` | `Count <= size()` | `Count` |
| `last<Count>()` | ¶4–¶6 | `Count <= Extent` | `Count <= size()` | `Count` |
| `subspan<Offset, Count>()` | ¶7–¶10 | `Offset <= Extent` 且 `Count` 动态或 `Count <= Extent - Offset` | 同样的式子，`Extent` 换成 `size()` | 见 ¶10 |
| `first(count)` | ¶11–¶12 | — | `count <= size()` | 动态 |
| `last(count)` | ¶13–¶14 | — | `count <= size()` | 动态 |
| `subspan(offset, count)` | ¶15–¶16 | — | `offset <= size()` 且 `count` 动态或 `count <= size() - offset` | 动态 |

设计上的分工很清楚：

- 对**静态 extent** 的 `span`，*Mandates* 会在编译期拦下越界（`Extent` 是真实长度）；
- 对**动态 extent** 的 `span`，`Extent` 是 `numeric_limits<size_t>::max()`，*Mandates* 形同虚设，越界只能靠运行期的加固检查。

¶10 规定 `subspan<Offset, Count>()` 的返回 extent：`Count` 给了就是 `Count`；没给且源是静态的，就是 `Extent - Offset`；否则是动态。注意 ¶8 写成 `Count <= size() - Offset` 而不是 `Offset + Count <= size()`——后者在 `Offset + Count` 溢出时会给出错误结论，先检查 `Offset <= size()` 再做减法就不会溢出。

```cpp run title="span-subviews.cpp" ok
#include <span>
#include <type_traits>

int buf[8];
std::span<int, 8> s8 = buf;
std::span<int>    sd = buf;

// 模板版本：extent 尽可能保持静态
static_assert(std::is_same_v<decltype(s8.first<3>()),      std::span<int, 3>>);
static_assert(std::is_same_v<decltype(s8.subspan<2>()),    std::span<int, 6>>);
static_assert(std::is_same_v<decltype(s8.subspan<2, 3>()), std::span<int, 3>>);
static_assert(std::is_same_v<decltype(sd.subspan<2>()),    std::span<int>>);    // 源是动态的，Count 又省略
static_assert(std::is_same_v<decltype(sd.subspan<2, 3>()), std::span<int, 3>>);
// 运行期版本：结果永远是动态 extent
static_assert(std::is_same_v<decltype(s8.first(3)),        std::span<int>>);

int main() {}
```

```cpp run title="span-subview-mandates.cpp" error
#include <span>

int buf[8];
std::span<int, 8> s8 = buf;
std::span<int>    sd = buf;

auto a = s8.first<9>();       // error: Mandates: Count <= Extent
auto b = s8.subspan<6, 3>();  // error: Mandates: Count <= Extent - Offset
auto c = sd.first<9>();       // 能编译（Extent 是 dynamic_extent）；运行时违反 Hardened precondition
```

## 观察器与元素访问（[span.obs]、[span.elem]）

[span.obs] ¶1–¶3：`size()` 返回 *size_*，`size_bytes()` 返回 `size() * sizeof(element_type)`，`empty()` 等价于 `size() == 0`。三者都是 `noexcept`。`size_bytes()` 不会溢出吗？`span` 的前置条件要求它指向真实存在的对象序列，而任何对象的大小都放得进 `size_t`，所以合法的 `span` 上它不会溢出。

[span.elem] 是 C++26 标准库加固的重点区域：

| 成员 | 段落 | 越界时 |
|---|---|---|
| `operator[](idx)` | ¶1–¶3 | *Hardened precondition* `idx < size()`；非加固实现中是 {{ub}} |
| `at(idx)` {{c++26}} | ¶4–¶5 | **抛 `out_of_range`**——这是函数的规定行为，不是前置条件 |
| `front()` / `back()` | ¶6–¶11 | *Hardened precondition* `!empty()` |
| `data()` | ¶12 | 总是合法，返回 *data_* |

`at()` 是 C++26 补上的（[[P2821R5]]）。C++20 时 `span` 刻意不提供 `at()`，理由是"span 是低开销的视图，不该带异常"；后来委员会认为与其他连续容器保持接口一致更重要。`at()` 在独立实现中是 *freestanding-deleted* 的，因为它依赖异常。

!!! note "operator[] 的 *Throws: Nothing* 有什么用"
    ¶3 写的是 *Throws*: Nothing，但函数没有标 `noexcept`。这是标准库的"Lakos 规则"：带前置条件的函数不标 `noexcept`，给测试框架或实现留出"违反前置条件时以抛异常的方式报告"的余地。

### 加固模式下的实际表现

```cpp run title="span-hardening.cpp" flags="-std=c++2c -D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_DEBUG"
#include <cstdio>
#include <span>
#include <stdexcept>

int main() {
  int buf[4] = {1, 2, 3, 4};
  std::span<int> s = buf;
  try {
    (void)s.at(4);                        // C++26：越界抛 out_of_range
  } catch (const std::out_of_range&) {
    std::puts("at(4) threw out_of_range");
  }
  std::printf("%d\n", s[4]);              // Hardened precondition 违反：加固实现中终止；否则 UB
}
```

用本地 libc++ 测得：

- 不加任何宏：Homebrew 构建的 libc++ 默认加固模式为 none（`__config_site` 中 `_LIBCPP_HARDENING_MODE_DEFAULT` 为 none 对应的值），`s[4]` 静默读越界，打印一个垃圾值；
- `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_DEBUG`：打印 `libc++ Hardening assertion __idx < size() failed: span<T>::operator[](index): index out of range` 后 abort；
- `_LIBCPP_HARDENING_MODE_FAST`：同样检查，但以陷阱指令（trap）直接终止，不输出诊断信息，开销最小。

libc++ 的 `span` 越界检查归在 `_LIBCPP_ASSERT_VALID_ELEMENT_ACCESS` 类别下，fast 模式就已启用。此外 libc++ 在 `(It, count)` 构造函数里还额外检查"`count != 0` 时指针不得为空"（归在 valid-input-range 类别），这超出了标准的要求，但不违反它——违反前置条件本来就是 UB，实现怎么报告都可以。

## 迭代器（[span.iterators]）

¶1：`iterator` 建模 `contiguous_iterator`、满足 *Cpp17RandomAccessIterator* 和 constexpr 迭代器的要求，值类型是 `value_type`，引用类型是 `reference`。注意没有要求它就是 `T*`——libc++ 用的是包装类型 `__wrap_iter<pointer>`，在启用"有界迭代器"ABI 选项时则换成自带边界检查的 `__bounded_iter<pointer>`。用户代码不应依赖"迭代器是指针"。

¶2：**容器迭代器的所有要求**（[[container.reqmts]]）同样适用于 `span::iterator`。这是 `span` 放在容器章的一个直接后果。

¶3–¶6：`begin()`/`end()`/`rbegin()`/`rend()` 的常规定义；空 `span` 的 `begin() == end()`。所有迭代器函数都是 `const` 且 `noexcept` 的——`span` 的 `const` 是浅的，`const span<int>` 的 `begin()` 返回的仍是可写的 `iterator`。

```cpp run title="span-borrowed.cpp" ok
#include <algorithm>
#include <span>
#include <type_traits>
#include <vector>

std::vector<int> v{1, 2, 3};

int main() {
  // 对右值 span 调用 ranges 算法，得到的是真正的迭代器而不是 ranges::dangling
  auto it = std::ranges::find(std::span(v), 2);
  static_assert(std::is_same_v<decltype(it), std::span<int>::iterator>);
  auto it2 = std::ranges::find(std::vector<int>{1, 2, 3}, 2);
  static_assert(std::is_same_v<decltype(it2), std::ranges::dangling>);

  const std::span<int> s = v;
  s[0] = 42;            // OK：const 的是 span 本身（指针和长度），不是元素
  return *it + v[0] - 44;
}
```

## 对象表示的视图：`as_bytes`、`as_writable_bytes`（[span.objectrep]）

¶1–¶2：`as_bytes(s)` 的效果等价于

```cpp
return R{reinterpret_cast<const byte*>(s.data()), s.size_bytes()};
```

¶3–¶4：`as_writable_bytes` 同理，只是指向 `byte`。约束上：两者都拒绝 `volatile` 元素（¶1、¶3）；`as_writable_bytes` 还拒绝 const 元素（¶3）。

这两个函数的合法性**完全由核心语言担保**，值得把链条讲清楚：

1. **对象表示**：类型为 `T` 的对象的对象表示是从它开始的 `sizeof(T)` 个 `unsigned char` 对象序列（[[basic.types.general]] ¶2，[[g:object-representation]]）。整段 `span<T>` 覆盖 `size_bytes()` 个连续字节，因为数组元素之间没有空隙。
2. **类型可访问**：通过 `std::byte` 类型的 glvalue 访问任意对象的存储值，属于 [[basic.lval]] ¶11 列出的 [[g:type-accessible]] 情形（¶11.3：`char`、`unsigned char` 或 `std::byte`），不违反严格别名规则。
3. **`reinterpret_cast` 本身**：把对象指针转成 `const byte*` 是合法的指针转换（[[expr.reinterpret.cast]]）；随后在这片字节上做指针算术和访问，依赖的是核心语言对"通过字节类型访问对象表示"的处理。

为什么排除 `volatile`？`span<const byte>` 的元素不是 volatile 的，若允许转换，就等于把 volatile 访问悄悄降级为普通访问，丢失 volatile 语义——这与 `const_cast` 去掉 volatile 一样危险。

```cpp run title="span-as-bytes.cpp" ok
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <span>
#include <type_traits>

struct Pixel { std::uint8_t r, g, b, a; };

int main() {
  Pixel img[2] = {{1, 2, 3, 4}, {5, 6, 7, 8}};
  std::span<Pixel, 2> px = img;

  auto ro = std::as_bytes(px);              // span<const byte, 8>：静态 extent 被换算成字节数
  static_assert(std::is_same_v<decltype(ro), std::span<const std::byte, 8>>);
  for (std::byte b : ro) std::printf("%d ", std::to_integer<int>(b));
  std::puts("");

  auto rw = std::as_writable_bytes(px);     // span<byte, 8>
  rw[0] = std::byte{42};                    // 通过 byte glvalue 修改 Pixel 的对象表示
  std::printf("%d\n", img[0].r);            // 42
}
```

```cpp run title="span-as-bytes-error.cpp" error
#include <span>

const int ci[2] = {};
volatile int vi[2];
auto a = std::as_writable_bytes(std::span(ci));  // error: 元素是 const
auto b = std::as_bytes(std::span(vi));           // error: 元素是 volatile
```

!!! warning "反方向没有对应的函数"
    标准只提供"对象 → 字节"的视图，**没有** `span<byte>` → `span<T>` 的函数。把一段收到的字节重新解释为 `T` 对象，需要的不是类型双关，而是在那片存储里**创建对象**——用 `std::start_lifetime_as_array`（[[obj.lifetime]]）或 `memcpy` 到真正的 `T` 对象里。直接 `reinterpret_cast<T*>(bytes.data())` 再访问，那里没有 `T` 对象，是 {{ub}}（除非隐式对象创建恰好为你造出了对象，见 [[intro.object]]）。

## 为什么 `span` 没有 `operator==`

C++20 早期草案中的 `span` 有按内容比较的 `==` 和 `<`，后来被 [[P1085R2]] 移除。症结在于 `span` 身上同时存在两种合理但互相矛盾的相等语义：

- **深比较**（比较元素）：和 `vector`、`string_view` 一致；
- **浅比较**（比较指针和长度）：和"它只是个指针加长度"的身份一致，且满足 [span.overview] ¶2"所有成员函数常数时间"的承诺。

更麻烦的是 `span` 的浅 const 和可写元素：若采用深比较，`span` 就不是 `regular` 的（拷贝后修改元素，原 `span` 跟着"变化"，违背值语义的直觉）；若采用浅比较，又会让 `span(a) == span(b)` 在内容相同的两个数组上返回 `false`，与 `string_view` 相反。委员会最终选择**不提供**，让用户明确写出意图：

- 比较内容：`std::ranges::equal(a, b)`；
- 比较身份：`a.data() == b.data() && a.size() == b.size()`。

## 常见误区与陷阱

!!! pitfall "从临时对象构造 span 立刻悬垂"
    ¶16.2 放行了"元素为 const 时从右值 range 构造"，只是为了函数实参这一种安全场景。一旦把结果存进变量就悬垂了：

```cpp run title="span-dangling.cpp" ub
#include <span>
#include <vector>

std::vector<int> make() { return {1, 2, 3}; }

int main() {
  std::span<const int> s = make();  // 编译通过：元素是 const，Constraints 放行
  return s[0];                      // UB: vector 临时对象在完整表达式结束时已销毁
}
```

Clang 对此有专门的诊断 `-Wdangling-gsl`（默认开启）："object backing the pointer will be destroyed at the end of the full-expression"——Clang 对标准库里一批已知类型（`vector`、`span` 等）内置推断了 `[[gsl::Owner]]`/`[[gsl::Pointer]]` 属性，据此发现"Pointer 类型从临时 Owner 构造"的模式。同样的坑也出现在 `std::span<const int, 3> s = std::array{1, 2, 3};`（绑定到 `const array&` 的临时对象），ASan 报 stack-use-after-scope。临时对象的生命周期规则见 [[class.temporary]]。

!!! pitfall "静态 extent 的 span 从运行期数据构造"
    `span<int, 4>{v.data(), n}` 和 `span<int, 4>{v}` 都要求运行期长度恰好是 4（¶5、¶18）。这是加固前置条件，不是编译期检查，也**不会**截断或填充。如果只是"至少 4 个"，应写 `span<int>(v).first<4>()`——`first<4>` 只要求 `4 <= size()`。

!!! pitfall "以为 `const span<T>` 是只读的"
    `const` 修饰的是 `span` 对象（指针和长度），元素照样可写。要只读，写 `span<const T>`。函数参数写成 `const span<T>&` 既不只读也不更快——按值传 `span<const T>` 才是正确姿势。

!!! pitfall "`vector<bool>` 不能变成 span"
    `vector<bool>` 的迭代器是代理迭代器，不是 `contiguous_iterator`，`ranges::data` 也不存在，¶16.1 直接把它挡在外面（见 [[vector.bool]]）。

## 历史

| 版本 | 变化 |
|---|---|
| C++20 | `span` 进入标准（[[P0122R7]]）。最初带比较运算符和有符号的 `index_type`，在 C++20 定稿前被修订：比较运算符由 [[P1085R2]] 移除，下标改为 `size_t`。 |
| C++23 | 增加 `cbegin`/`cend` 等，`const_iterator` 定义为 `std::const_iterator<iterator>`（[[P2278R4]]）。`span` 被要求是平凡可复制类型。 |
| C++26 | `at()`（[[P2821R5]]）；推导指引经由 *maybe-static-ext* 支持 `std::cw<N>` 一类的整型常量包装；下标、`front`/`back`、子视图、静态 extent 构造的尺寸检查改写为 *Hardened preconditions*。 |
| C++26 周期 | `initializer_list` 构造函数（[[P2447R6]]）曾加入草案，当前草案文本中已不存在（见上文）。 |

## 思考题

!!! question "1. 下面哪一行能编译？"
    ```cpp
    std::vector<int> v(4);
    void f(std::span<int, 4>);
    f(v);
    f(std::span<int, 4>(v));
    f(std::span(v).first<4>());
    ```

<details markdown="1">
<summary>展开查看答案与解析</summary>

- `f(v)`：{{ill-formed}}。拷贝初始化形参需要隐式转换，而 range 构造函数在静态 extent 下是 `explicit` 的（[span.cons] ¶16 上方声明的 `explicit(extent != dynamic_extent)`）。
- `f(std::span<int, 4>(v))`：合法。函数式转换是直接初始化，可以调用 `explicit` 构造函数；运行期由 ¶18 的加固前置条件检查 `v.size() == 4`。
- `f(std::span(v).first<4>())`：合法。CTAD 得到 `span<int>`，`first<4>()` 返回 `span<int, 4>`（[span.sub] ¶3），运行期检查 `4 <= size()`。语义比上一行宽松：`v` 有 10 个元素也行。

</details>

!!! question "2. `span<const int>` 能从 `std::vector<int>&&` 构造，`span<int>` 不能；那 `span<int>` 能从 `std::span<int>&&` 或 `std::string_view` 之外的哪些右值 range 构造？"

<details markdown="1">
<summary>展开查看答案与解析</summary>

任何满足 `borrowed_range` 的连续、有大小的右值 range 都可以（¶16.2）。标准库里的例子：`std::ranges::subrange<int*>`、`std::ranges::ref_view<std::vector<int>>`、`std::ranges::owning_view` **不行**（它拥有底层 range，不是 borrowed）。右值 `span<int>` 本身被 ¶16.3 排除在 range 构造函数之外，但会走拷贝构造函数或 ¶22 的转换构造函数，同样可以。自定义的连续视图要进入这个名单，需要特化 `ranges::enable_borrowed_range`（[[range.range]] ¶6）。

</details>

!!! question "3. 为什么 `span(It, End)` 需要 ¶8.4 “`End` 不可转换为 `size_t`”，而 `span(It, size_type)` 不需要对称的约束？"

<details markdown="1">
<summary>展开查看答案与解析</summary>

当第二个实参是整数时，两个构造函数都可能可行：`(It, size_type)` 通过整数转换，`(It, End)` 则把整数类型推导为 `End`。如果某个迭代器类型恰好把整数当作合法的哨兵（`sized_sentinel_for<int, It>` 为真），调用就会歧义或者悄悄选中模板版本（模板推导出的精确匹配优于需要转换的非模板版本）。¶8.4 让任何可转换为 `size_t` 的 `End` 都不参与决议，于是"第二个实参是整数"永远意味着长度。反方向不需要约束，因为 `size_type` 是固定类型，不会去匹配一个迭代器哨兵。

</details>

## 小结

| 主题 | 规则 |
|---|---|
| 存储 | 不拥有；动态 extent 存指针 + 长度，静态 extent 实现上只存指针 |
| 平凡性 | 平凡可复制（¶3），按值传递 |
| 元素转换 | 只允许限定转换：`is_convertible_v<U(*)[], T(*)[]>` |
| `explicit` | 只在"运行期长度 → 静态 extent"时出现：迭代器、range、动态 `span` 来源 |
| 右值 range | 必须是 `borrowed_range`，或者元素为 const（仍可能悬垂） |
| 子视图 | 模板版本：静态 extent 时编译期 *Mandates*；运行期版本永远返回动态 extent |
| 越界 | `[]`/`front`/`back`/子视图是 *Hardened preconditions*；`at()` 抛 `out_of_range` |
| 字节视图 | `as_bytes` 拒绝 volatile；`as_writable_bytes` 还拒绝 const；依赖 [[basic.lval]] ¶11 的 `std::byte` 可访问规则 |
| 比较 | 没有 `operator==`；用 `ranges::equal` 或比较 `data()`/`size()` |
