---
title: 连续访问：span
summary: std::span 是一个指针加一个长度：它怎样只允许加 const 的元素转换、什么时候构造函数是 explicit、怎样从临时对象构造、子视图和下标如何检查越界、as_bytes 为什么合法，以及它为什么没有 operator==。
status: done
covers: *
papers: P0122R7, P1085R2, P2278R4, P2821R5, P2447R6
related: views, views.multidim, container.requirements, vector, array, basic.types.general, basic.lval, conv.qual, class.temporary, range.range
tags: 标准库, span, 视图, 加固, 对象表示, 悬垂
updated: 2026-10-19
---

!!! tldr
    - `span<T>` 是一个指针加一个长度，`span<T, N>` 的长度是编译期常量 N，实现通常只存一个指针。它不拥有元素，所看存储被释放或搬走后就悬垂。
    - 元素类型只允许加 const：`span<int>` 能变成 `span<const int>`，`Derived` 数组不能变成 `span<Base>`。
    - 只有把运行期长度变成静态长度时构造函数才是 `explicit`，例如 `vector` 到 `span<int, 4>`；长度是否相符由加固前置条件在运行期检查。
    - `span<const T>` 可以从临时 `vector` 构造，便于传参；存进变量就会悬垂。`span<T>`（非 const）拒绝从临时对象构造。
    - 下标、`front`、`back` 和子视图的越界检查是加固前置条件；C++26 的 `at()` 越界抛 `out_of_range`。`span` 没有 `operator==`。

## 指针加长度

```cpp run title="span-basics.cpp" ok
#include <cstdio>
#include <span>
#include <vector>

void print(std::span<const int> s) {           // 一个参数代替 (const int* p, size_t n)
  for (int x : s) std::printf("%d ", x);
  std::puts("");
}

void fill4(std::span<int, 4> s) {              // 长度在类型里：恰好 4 个元素
  for (int& x : s) x = 7;
}

int main() {
  int raw[4] = {1, 2, 3, 4};
  std::vector<int> v{5, 6, 7};
  print(raw);
  print(v);
  print(std::span(v).first(2));                // 子视图：5 6
  fill4(raw);                                  // OK：数组长度在编译期已知是 4
  print(raw);
}
```

`std::span<T, Extent>`（{{c++20}}，[[P0122R7]]）给 C 接口里常见的 `(T* p, size_t n)` 起了一个类型名。和裸指针加长度相比，它有三点好处：

- 长度和指针放在一起，层层传参时不会丢失，也不会配错。
- 长度可以是编译期常量。`span<int, 4>` 的长度写在类型里，实现只需存一个指针，长度不对的子视图在编译期就会被拒绝。
- 元素类型的转换只允许加 const。裸指针允许 `Base* p = derived_array;`，之后按 `sizeof(Base)` 步进就会错位，`span` 在类型层面挡住了这种写法。

第二个模板实参 `Extent` 叫做 **extent**，即元素个数。它的默认值是 `dynamic_extent`，表示长度到运行期才确定。`dynamic_extent` 定义为 `numeric_limits<size_t>::max()`，`mdspan` 也使用同一个常量（[[views]]）。下文把 `Extent` 为 `dynamic_extent` 的 `span` 叫做动态 extent，其余叫做静态 extent。

## 对象模型（[span.overview]）

¶1 `span` 是一段连续对象序列上的视图，这段存储由另外某个对象拥有。`span` 的析构函数什么也不做，存储的生命周期由调用者负责。

¶2 `span` 的所有成员函数都是常数时间。所以它不能提供逐个比较元素的 `operator==`，见后文。

¶3 `span<ElementType, Extent>` 是平凡可复制类型（[[g:trivially-copyable-type]]，[[basic.types.general]]）。复制构造函数和析构函数都是平凡的，所以在 x86-64 和 AArch64 的常见 ABI 下，动态 extent 的 `span` 按值传参时直接放进两个寄存器，和传两个裸参数一样便宜。

¶4 `ElementType` 必须是完整的对象类型，而且不是抽象类：

- `span<void>`、`span<int&>`、`span<int()>` 都不行，它们不是对象类型。本机 libc++ 对 `span<int&>` 直接编译失败。
- `span<int[3]>` 可以，数组是对象类型。`int m[2][3]` 能直接转换成 `span<int[3]>`，每个元素是一行。

### 静态 extent 只存一个指针

条文里用于说明的成员有两个，`data_` 和 `size_`。但它们只用于说明（exposition only），静态 extent 下 `size()` 必然等于 `Extent`，实现不必存它：

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

标准没有规定 `sizeof`，但静态 extent 不为长度付存储代价是设计意图，主流实现都这样做。

### 失效来自外部（¶5）

¶5 凡是使 `[s.data(), s.data() + s.size())` 中的指针失效的操作，也使 `s` 的元素的指针、迭代器和引用失效。

`span` 自己没有任何修改操作，它的失效全部来自底层存储。最常见的是 `vector` 重新分配：

```cpp run title="span-invalidation.cpp" ub
#include <span>
#include <vector>

int main() {
  std::vector<int> v{1, 2, 3};
  std::span<int> s = v;
  v.push_back(4);       // 如果重新分配，s 指向的存储被释放
  return s[0];          // UB: span 不知道 vector 已经搬走
}
```

AddressSanitizer 在本机报告 heap-use-after-free。哪些容器操作会使指针失效，见 [[container.requirements]] 和 [[vector]]。`operator[]` 的加固检查只比较下标和 `size()`，对悬垂无能为力，所以在加固实现里这段代码同样是 UB。

### 成员类型

- `element_type` 就是 `ElementType`，可以带 cv；`value_type` 去掉了 cv。`span<const int>::value_type` 是 `int`，与容器一样，`value_type` 是把元素复制出来时得到的类型。
- `size_type` 是 `size_t`，`difference_type` 是 `ptrdiff_t`，`extent` 是值为 `Extent` 的静态数据成员。
- `iterator` 由实现定义，`const_iterator` 是 `std::const_iterator<iterator>`。C++20 的 `span` 没有 `cbegin`：`const span` 的迭代器仍然可写，叫 `cbegin` 却返回可写迭代器会误导。C++23 引入 `std::const_iterator` 之后才补上（[[P2278R4]]）。

## 构造函数（[span.cons]）

先看总表。最后一列只针对静态 extent；动态 extent 的 `span`，所有构造函数都可以隐式调用。

| 构造函数 | 段落 | 约束要点 | 加固前置条件 | 静态 extent 时 explicit |
|---|---|---|---|---|
| `span()` | ¶1–¶2 | `Extent` 为 0 或 `dynamic_extent` | 无 | 不适用 |
| `span(It first, size_type count)` | ¶3–¶7 | `It` 是连续迭代器；只允许加 const | `count == extent` | 是 |
| `span(It first, End last)` | ¶8–¶12 | 同上；`End` 是 `It` 的有大小哨兵，且不能转换成 `size_t` | `last - first == extent` | 是 |
| 内建数组、`array<T, N>&`、`const array<T, N>&` | ¶13–¶15 | `N == extent` 或动态；只允许加 const | 无 | 否 |
| `span(R&& r)` | ¶16–¶20 | 连续且有大小；是 borrowed range 或元素为 const；不是 `span`、`array`、内建数组 | `ranges::size(r) == extent` | 是 |
| `span(const span<U, N>&)` | ¶22–¶26 | extent 兼容；只允许加 const | `s.size() == extent` | 仅当源为动态、目标为静态 |

库条款里，*Constraints* 不满足时这个函数不参与重载决议；*Preconditions* 违反时是 UB；*Hardened preconditions* 在[[g:hardened-implementation|加固实现]]中违反会终止程序，在其他实现中也是 UB（[[structure.specifications]]）。

### 默认构造（¶1–¶2）

¶1 只有 `Extent` 为 `dynamic_extent` 或 0 时才有默认构造函数。一个承诺恰好有 4 个元素的 `span<int, 4>` 不能凭空造出来。¶2 默认构造的结果满足 `size() == 0 && data() == nullptr`。

### 只允许加 const（¶3、¶8、¶13、¶16、¶22）

每个构造函数都有一条形如下面的约束，`U` 是来源的元素类型：

```cpp
is_convertible_v<U(*)[], element_type(*)[]>
```

为什么不直接写 `is_convertible_v<U*, element_type*>`？因为普通指针允许派生类到基类的转换：`Derived*` 能转成 `Base*`，但把 `Derived` 数组当作 `Base` 数组按 `sizeof(Base)` 步进是 UB。指向数组的指针之间只允许限定转换（[[conv.qual]]）：`int(*)[]` 能转成 `const int(*)[]`，`Derived(*)[]` 不能转成 `Base(*)[]`。条文里的注也说明了这个意图：

!!! std
    The intent is to allow only qualification conversions of the iterator reference type to `element_type`.

注本身不具规范效力，约束的效果来自 `is_convertible_v` 这个表达式。

### 迭代器加长度、迭代器加哨兵（¶3–¶12）

¶4 和 ¶9 的前置条件：`[first, first + count)` 或 `[first, last)` 是有效范围，并且 `It` 建模（models）`contiguous_iterator`，而不只是在语法上满足（satisfies）。一个语法上满足、实际上不连续的迭代器传进来，是 UB。

¶5 和 ¶10 的加固前置条件：静态 extent 时，长度必须恰好等于 `extent`。

¶8.4 要求 `End` 不能转换成 `size_t`。这样 `span(first, n)` 中整数类型的第二个实参总是被当作长度，不会被推导成哨兵类型 `End`，原因见思考题 3。

¶12 `(It, End)` 版本在 `last - first` 抛出异常时抛出同样的异常。用户定义的迭代器做减法可能抛出，所以这个构造函数没有 `noexcept`。

### 内建数组和 std::array（¶13–¶15）

¶13.1 要求 `extent == dynamic_extent || N == extent`。长度不对时，构造函数不参与重载决议，不需要运行期检查。所以这三个构造函数从来不是 `explicit` 的。

¶14 的注 4 说明了内建数组版本为什么写成 `type_identity_t<element_type> (&arr)[N]`：`type_identity_t` 让形参处于不推导语境，使类模板实参推导不经过这个构造函数，推导交给专门的推导指引。

```cpp run title="span-extent-explicit.cpp" error
#include <array>
#include <span>
#include <vector>

int raw[4];
std::array<int, 4> arr;
std::vector<int> vec(4);

std::span<int, 4> a = raw;   // OK：数组构造函数不是 explicit
std::span<int, 4> b = arr;   // OK
std::span<int, 4> c{vec};    // OK：直接初始化可以调用 explicit 构造函数
std::span<int, 4> d = vec;   // error: range 构造函数是 explicit(extent != dynamic_extent)
std::span<int, 3> e = raw;   // error: N == extent 不成立，构造函数不参与决议
std::span<int, 4> f;         // error: 默认构造要求 Extent 为 0 或 dynamic_extent
```

`vector` 到 `span<int, 4>` 必须显式，因为 `vector` 的长度是运行期的，编译器无法验证它恰好是 4。写出 `explicit` 转换表示调用者担保长度正确，实际检查交给加固前置条件。

### 从 range 构造（¶16–¶20）

这是最通用、也最容易出错的构造函数。¶16 的约束：

- ¶16.1 `R` 满足 `ranges::contiguous_range` 和 `ranges::sized_range`。`deque`、`list` 不连续，`vector<bool>` 的迭代器不是连续迭代器，都被排除。
- ¶16.2 要么 `R` 满足 `ranges::borrowed_range`，要么 `element_type` 是 const。
- ¶16.3–¶16.5 `R` 不是 `span`、`array` 或内建数组，它们有专门的构造函数。
- ¶16.6 只允许加 const。

¶16.2 要结合 borrowed range 来理解。**borrowed range**（[[g:borrowed-range]]）是这样的 range：从它取得的迭代器不依赖这个 range 对象本身的生命周期，`span`、`string_view` 都是，`vector` 不是。`R&&` 是转发引用，传左值 `vector<int>& v` 时 `R` 推导为 `vector<int>&`，而按 [[range.range]] 中 `borrowed_range` 的定义，左值引用类型总是满足它。所以这条约束实际上只限制右值实参：

- `void f(span<const int>)` 可以接受 `f(make_vector())`。临时对象活到完整表达式结束，在 `f` 执行期间是安全的。
- `span<int>` 从临时 `vector` 构造几乎总是错误，往一个马上要销毁的对象里写入没有意义，所以直接拒绝。

```cpp run title="span-range-ctor.cpp" error
#include <span>
#include <vector>

std::vector<int> make();
void read(std::span<const int>);
void write(std::span<int>);

void f() {
  read(make());                   // OK：元素是 const，允许从右值 vector 构造
  write(make());                  // error: 右值 vector 不是 borrowed range，元素又不是 const
  std::vector<bool> vb(8);
  read(std::span<const bool>(vb)); // error: vector<bool> 不是 contiguous_range
}
```

¶17 把 ¶16 的语法要求改为语义要求（models）作为前置条件；¶18 是静态 extent 的长度检查；¶19 用 `ranges::data(r)` 和 `ranges::size(r)` 初始化；¶20 这两个调用抛出什么，构造函数就抛出什么。

### 复制与 span 之间的转换（¶21–¶27）

¶21、¶27 复制构造和复制赋值都是 `= default` 的 `noexcept` 平凡操作，结果的指针和长度与源相同。

¶22–¶26 是从 `span<U, N>` 到 `span<T, M>` 的转换构造函数：

- ¶22.1 extent 兼容：任一方是动态，或者两者相等。`span<int, 4>` 到 `span<int, 3>` 的构造函数不参与决议。
- ¶22.2 只允许加 const。`span<int>` 能变成 `span<const int>`，反过来不行。
- ¶23 目标是静态 extent 时，加固前置条件要求 `s.size() == extent`。
- ¶26 `explicit` 的条件是 `extent != dynamic_extent && OtherExtent == dynamic_extent`。只有动态到静态需要显式，其他方向都可以隐式转换。

```cpp run title="span-conversions.cpp" error
#include <span>

struct Base { int x; };
struct Derived : Base { int y; };

int buf[4];
Derived d[3];
std::span<int>    dyn = buf;
std::span<int, 4> fix = buf;

std::span<const int> c1 = dyn;   // OK：int 到 const int 是限定转换
std::span<int>       a  = fix;   // OK：静态到动态，隐式
std::span<int, 4>    b{dyn};     // OK：动态到静态，必须显式；加固前置条件 dyn.size() == 4
std::span<int>       c2 = c1;    // error: 丢掉 const
std::span<Base>      e  = d;     // error: Derived(*)[] 不能转换成 Base(*)[]
std::span<int, 4>    g  = dyn;   // error: 动态到静态是 explicit 的
std::span<int, 3>    h{fix};     // error: 两个静态 extent 不相等，构造函数不参与决议
```

### 没有 initializer_list 构造函数

```cpp run title="span-init-list.cpp" error
#include <initializer_list>
#include <span>

void f(std::span<const int>);

void g() {
  std::initializer_list<int> il{1, 2, 3};
  f(il);          // OK：initializer_list 是连续、有大小的 range，元素是 const
  f({1, 2, 3});   // error: 当前草案没有 initializer_list 构造函数
}
```

C++26 周期里，[[P2447R6]] 曾给 `span` 加入 `span(initializer_list<value_type>)` 构造函数，让 `f({1, 2, 3})` 可以编译。当前草案的 [span.cons] 里已经没有这个构造函数，[[version.syn]] 里也没有对应的特性测试宏。

这个构造函数有两个问题。第一，`span<const int> s = {1, 2, 3};` 中 `initializer_list` 的底层数组是临时对象，语句结束就销毁（[[dcl.init.list]]），只有用作函数实参时才安全。第二，花括号初始化优先选择 `initializer_list` 构造函数（[[over.match.list]]），原本调用指针加长度构造函数的 `span<const std::any> s{ptr, n}` 会变成含两个 `any` 的列表。

显式写出的 `initializer_list` 对象仍然可以经由 ¶16 的 range 构造函数转换成 `span<const int>`，如上例的 `f(il)`。

## 推导指引（[span.deduct]）

| 实参 | 推导结果 |
|---|---|
| `(It, EndOrSize)` | `span<remove_reference_t<iter_reference_t<It>>, maybe-static-ext<EndOrSize>>`；¶1 要求 `It` 是连续迭代器 |
| `T (&)[N]` | `span<T, N>` |
| `array<T, N>&` | `span<T, N>` |
| `const array<T, N>&` | `span<const T, N>` |
| `R&&` | `span<remove_reference_t<range_reference_t<R>>>`，动态 extent；¶2 要求 `R` 是连续 range |

*maybe-static-ext* 定义在 [span.syn]，只用于说明。如果类型 `T` 像 `integral_constant` 那样带有一个非 `bool` 整型的静态成员 `T::value`，*maybe-static-ext*`<T>` 就是这个值，否则是 `dynamic_extent`。所以第二个实参是普通整数时得到动态 extent，是 `std::integral_constant<size_t, 2>` 或 C++26 的 `std::cw<2uz>` 时得到静态 extent 2。

从 range 推导出的总是动态 extent，即使 range 的长度在编译期已知。`const array` 推导出 `span<const T, N>`，const 从容器传到了元素上。

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
std::span e{vec.data(), 2};            // span<int>：2 是普通 int，extent 是动态的
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

## 子视图（[span.sub]）

`first`、`last`、`subspan` 都有两个版本：长度作为模板实参的版本，和长度作为函数实参的版本。

| 函数 | 段落 | *Mandates*（编译期） | 加固前置条件（运行期） | 结果的 extent |
|---|---|---|---|---|
| `first<Count>()` | ¶1–¶3 | `Count <= Extent` | `Count <= size()` | `Count` |
| `last<Count>()` | ¶4–¶6 | `Count <= Extent` | `Count <= size()` | `Count` |
| `subspan<Offset, Count>()` | ¶7–¶10 | `Offset <= Extent`，且 `Count` 为动态或 `Count <= Extent - Offset` | 同样的式子，`Extent` 换成 `size()` | 见 ¶10 |
| `first(count)` | ¶11–¶12 | 无 | `count <= size()` | 动态 |
| `last(count)` | ¶13–¶14 | 无 | `count <= size()` | 动态 |
| `subspan(offset, count)` | ¶15–¶16 | 无 | `offset <= size()`，且 `count` 为动态或 `count <= size() - offset` | 动态 |

*Mandates* 不满足时程序非良构。对静态 extent，`Extent` 就是真实长度，越界在编译期被拦下。对动态 extent，`Extent` 是 `size_t` 的最大值，*Mandates* 几乎总能满足，越界只能靠运行期的加固检查。

¶10 `subspan<Offset, Count>()` 结果的 extent：给了 `Count` 就是 `Count`；没给且源是静态的，就是 `Extent - Offset`；否则是动态。¶8 写成 `Count <= size() - Offset` 而不是 `Offset + Count <= size()`，因为后者在加法溢出时会得出错误结论；先确认 `Offset <= size()`，再做减法就不会溢出。

```cpp run title="span-subviews.cpp" ok
#include <span>
#include <type_traits>

int buf[8];
std::span<int, 8> s8 = buf;
std::span<int>    sd = buf;

// 模板版本：尽可能保持静态 extent
static_assert(std::is_same_v<decltype(s8.first<3>()),      std::span<int, 3>>);
static_assert(std::is_same_v<decltype(s8.subspan<2>()),    std::span<int, 6>>);
static_assert(std::is_same_v<decltype(s8.subspan<2, 3>()), std::span<int, 3>>);
static_assert(std::is_same_v<decltype(sd.subspan<2>()),    std::span<int>>);    // 源是动态的，又没给 Count
static_assert(std::is_same_v<decltype(sd.subspan<2, 3>()), std::span<int, 3>>);
// 函数实参版本：结果总是动态 extent
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
auto c = sd.first<9>();       // 能编译（Extent 是 dynamic_extent）；运行时违反加固前置条件
```

## 观察器与元素访问（[span.obs]、[span.elem]）

[span.obs] ¶1–¶3 `size()` 返回 *size_*，`size_bytes()` 返回 `size() * sizeof(element_type)`，`empty()` 等价于 `size() == 0`，三者都是 `noexcept`。`span` 必须指向真实存在的对象序列，而任何对象的大小都能用 `size_t` 表示，所以合法的 `span` 上 `size_bytes()` 不会溢出。

[span.elem] 是 C++26 标准库加固的重点：

| 成员 | 段落 | 越界时 |
|---|---|---|
| `operator[](idx)` | ¶1–¶3 | 加固前置条件 `idx < size()`；非加固实现中是 {{ub}} |
| `at(idx)` {{c++26}} | ¶4–¶5 | 抛 `out_of_range`，这是规定的行为，不是前置条件 |
| `front()`、`back()` | ¶6–¶11 | 加固前置条件 `!empty()` |
| `data()` | ¶12 | 总是可以调用，返回 *data_* |

`at()` 由 [[P2821R5]] 加入。C++20 时 `span` 有意不提供 `at()`，理由是低开销的视图不该带异常；后来认为与其他连续容器保持接口一致更重要。独立实现（freestanding，没有操作系统支持的实现）也要提供 `span`，但会抛异常的 `at()` 在那里是 *freestanding-deleted* 的。

¶3 规定 `operator[]` *Throws*: Nothing，但函数没有标 `noexcept`。标准库通常不给带前置条件的函数加 `noexcept`，这样实现或测试框架可以用抛异常的方式报告前置条件违反。

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
  std::printf("%d\n", s[4]);              // 违反加固前置条件：加固实现中终止，否则 UB
}
```

本机 libc++ 的表现：

- 不加任何宏时，Homebrew 构建的 libc++ 默认不加固，`s[4]` 静默越界读取，打印一个垃圾值。
- 加 `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_DEBUG`，打印 `__idx < size()` 断言失败的信息后 abort。
- 用 `_LIBCPP_HARDENING_MODE_FAST`，同样检查，但用陷阱指令直接终止，不输出信息，开销最小。

libc++ 在 `(It, count)` 构造函数里还检查 `count != 0` 时指针不为空。这超出了标准的要求，但不违反它：违反前置条件本来就是 UB，实现怎样报告都可以。

## 迭代器（[span.iterators]）

¶1 `iterator` 建模 `contiguous_iterator`，满足 *Cpp17RandomAccessIterator* 和 constexpr 迭代器的要求。它不一定是 `T*`：libc++ 用的是包装类型，启用有界迭代器的 ABI 选项后还会换成自带边界检查的类型。代码不应假设迭代器就是指针。

¶2 [[container.reqmts]] 对容器迭代器的所有要求也适用于 `span::iterator`。

¶3–¶6 `begin()`、`end()`、`rbegin()`、`rend()` 是常规定义，空 `span` 的 `begin() == end()`。这些函数都是 `const` 和 `noexcept` 的，而 `span` 的 const 是浅的，`const span<int>` 的 `begin()` 返回的仍是可写的 `iterator`。

[span.syn] 把 `ranges::enable_view` 和 `ranges::enable_borrowed_range` 都特化为 `true`，所以 `span` 既是 `ranges::view`，也是 borrowed range。对右值 `span` 调用 ranges 算法，得到的是可用的迭代器：

```cpp run title="span-borrowed.cpp" ok
#include <algorithm>
#include <span>
#include <type_traits>
#include <vector>

std::vector<int> v{1, 2, 3};

int main() {
  // 右值 span：得到真正的迭代器
  auto it = std::ranges::find(std::span(v), 2);
  static_assert(std::is_same_v<decltype(it), std::span<int>::iterator>);
  // 右值 vector：得到 ranges::dangling
  auto it2 = std::ranges::find(std::vector<int>{1, 2, 3}, 2);
  static_assert(std::is_same_v<decltype(it2), std::ranges::dangling>);

  const std::span<int> s = v;
  s[0] = 42;            // OK：const 修饰的是 span 本身，不是元素
  return *it + v[0] - 44;
}
```

## 对象表示的视图（[span.objectrep]）

¶1–¶2 `as_bytes(s)` 等价于

```cpp
return R{reinterpret_cast<const byte*>(s.data()), s.size_bytes()};
```

¶3–¶4 `as_writable_bytes(s)` 同理，结果是 `span<byte>`。两者都拒绝 volatile 元素，`as_writable_bytes` 还拒绝 const 元素。结果的 extent 是 `sizeof(ElementType) * Extent`，静态 extent 换算成字节后仍是静态的。

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

  auto ro = std::as_bytes(px);              // span<const byte, 8>：静态 extent 换算成字节数
  static_assert(std::is_same_v<decltype(ro), std::span<const std::byte, 8>>);
  for (std::byte b : ro) std::printf("%d ", std::to_integer<int>(b));
  std::puts("");

  auto rw = std::as_writable_bytes(px);     // span<byte, 8>
  rw[0] = std::byte{42};                    // 通过 byte glvalue 修改 Pixel 的对象表示
  std::printf("%d\n", img[0].r);            // 42
}
```

这两个函数的合法性来自核心语言：

1. 类型为 `T` 的对象的**对象表示**是从它开始的 `sizeof(T)` 个 `unsigned char` 对象（[[basic.types.general]]，[[g:object-representation]]）。数组元素之间没有空隙，所以整个 `span<T>` 正好覆盖 `size_bytes()` 个连续字节。
2. 通过 `std::byte` 类型的 glvalue 访问任何对象的存储值都是允许的（[[basic.lval#11]]，[[g:type-accessible]]），不违反严格别名规则。
3. 把对象指针 `reinterpret_cast` 成 `const byte*` 是合法的指针转换（[[expr.reinterpret.cast]]）。

排除 volatile 是因为 `span<const byte>` 的元素不是 volatile 的。如果允许转换，volatile 访问就会悄悄变成普通访问，失去 volatile 的语义。

```cpp run title="span-as-bytes-error.cpp" error
#include <span>

const int ci[2] = {};
volatile int vi[2];
auto a = std::as_writable_bytes(std::span(ci));  // error: 元素是 const
auto b = std::as_bytes(std::span(vi));           // error: 元素是 volatile
```

!!! warning "没有从字节到对象的函数"
    标准只提供对象到字节的视图，没有把 `span<byte>` 变成 `span<T>` 的函数。把收到的一段字节当作 `T` 对象使用，需要在那片存储里创建对象：用 `std::start_lifetime_as_array`（[[obj.lifetime]]），或者 `memcpy` 到一个真正的 `T` 对象里。直接 `reinterpret_cast<T*>(bytes.data())` 再访问，那里没有 `T` 对象，是 {{ub}}，除非隐式对象创建恰好在那里创建了对象（[[intro.object]]）。

## 为什么没有 operator==

C++20 早期草案中的 `span` 有逐元素比较的 `==` 和 `<`，后来被 [[P1085R2]] 移除。`span` 同时有两种合理但互相矛盾的相等语义：

- 比较元素：和 `vector`、`string_view` 一致。但这不是常数时间，违背 ¶2。而且 `span` 的 const 是浅的、元素可写，复制一个 `span` 后修改元素，原来的 `span` 也跟着变，不符合值语义。
- 比较指针和长度：和它只是指针加长度的身份一致，但内容相同的两个数组会比较为不相等，与 `string_view` 相反。

最后选择不提供，让调用者写出意图：比较内容用 `std::ranges::equal(a, b)`；比较身份用 `a.data() == b.data() && a.size() == b.size()`。

## 常见误解

!!! pitfall "从临时对象构造 span 后存进变量"
    ¶16.2 允许元素为 const 的 `span` 从右值 range 构造，是为了函数实参这种安全的场合。存进变量就悬垂了：

```cpp run title="span-dangling.cpp" ub
#include <span>
#include <vector>

std::vector<int> make() { return {1, 2, 3}; }

int main() {
  std::span<const int> s = make();  // 能编译：元素是 const，约束允许
  return s[0];                      // UB: 临时 vector 在语句结束时已销毁
}
```

本机 Clang 对这一行默认给出 `-Wdangling-gsl` 警告：Clang 知道 `vector`、`span` 等标准库类型分别是拥有者和非拥有的指针类，能发现指针类从临时拥有者构造的模式。`std::span<const int, 3> s = std::array{1, 2, 3};` 是同样的错误，AddressSanitizer 报 stack-use-after-scope。临时对象的生命周期规则见 [[class.temporary]]。

!!! pitfall "静态 extent 的 span 会截断或补齐"
    `span<int, 4>{v.data(), n}` 和 `span<int, 4>{v}` 都要求运行期长度恰好是 4（¶5、¶18），不会截断，也不会补齐。如果只是要求至少 4 个元素，写 `span<int>(v).first<4>()`，`first<4>()` 只要求 `4 <= size()`。

!!! pitfall "const span<T> 是只读的"
    `const` 修饰的是 `span` 对象，即指针和长度，元素照样可写。只读要写 `span<const T>`。形参写成 `const span<T>&` 既不只读也不更快，按值传 `span<const T>` 才对。

## 历史

!!! history
    - C++20：`span` 进入标准（[[P0122R7]]）。定稿前做了修改：比较运算符由 [[P1085R2]] 移除，长度类型由有符号的 `index_type` 改为 `size_t`，`cbegin` 等成员被删除。
    - C++23：`span` 被要求是平凡可复制类型；`cbegin` 等重新加入，`const_iterator` 定义为 `std::const_iterator<iterator>`（[[P2278R4]]）。
    - C++26：加入 `at()`（[[P2821R5]]）；推导指引通过 *maybe-static-ext* 支持 `std::cw<N>` 这类整型常量包装；下标、`front`、`back`、子视图和静态 extent 构造的长度检查改为加固前置条件。`initializer_list` 构造函数（[[P2447R6]]）曾经加入，当前草案中已经不存在。

## 思考题

!!! question "思考题 1：下面哪些调用能编译？"
    ```cpp
    std::vector<int> v(4);
    void f(std::span<int, 4>);
    f(v);
    f(std::span<int, 4>(v));
    f(std::span(v).first<4>());
    ```

<details markdown="1">
<summary>答案</summary>

- `f(v)` 非良构。初始化形参是复制初始化，需要隐式转换，而 range 构造函数在静态 extent 下是 `explicit` 的。
- `f(std::span<int, 4>(v))` 可以。函数式转换是直接初始化，可以调用 `explicit` 构造函数；运行期由 ¶18 的加固前置条件检查 `v.size() == 4`。
- `f(std::span(v).first<4>())` 可以。推导得到 `span<int>`，`first<4>()` 返回 `span<int, 4>`（[span.sub] ¶3），运行期检查 `4 <= size()`。它比上一行宽松，`v` 有 10 个元素也可以。

</details>

!!! question "思考题 2：`span<int>` 能从哪些右值 range 构造？"
    `span<const int>` 能从右值 `std::vector<int>` 构造，`span<int>` 不能。哪些右值 range 可以构造 `span<int>`？

<details markdown="1">
<summary>答案</summary>

连续、有大小、并且是 borrowed range 的右值都可以（¶16.2）。标准库里的例子有 `std::ranges::subrange<int*>` 和 `std::ranges::ref_view<std::vector<int>>`。`std::ranges::owning_view<std::vector<int>>` 不行，它拥有底层的 `vector`，不是 borrowed range。右值 `span<int>` 被 ¶16.3 排除在 range 构造函数之外，但会使用复制构造函数或 ¶22 的转换构造函数，所以同样可以。自定义的连续视图要加入这个行列，需要特化 `ranges::enable_borrowed_range`（[[range.range#6]]）。

</details>

!!! question "思考题 3：为什么 `span(It, End)` 需要 ¶8.4？"
    `span(It, End)` 有约束要求 `End` 不能转换成 `size_t`，`span(It, size_type)` 为什么不需要对称的约束？

<details markdown="1">
<summary>答案</summary>

第二个实参是整数时，两个构造函数都可能可行：`(It, size_type)` 经过整数转换，`(It, End)` 把这个整数类型推导为 `End`。如果某个迭代器类型恰好接受整数作为有大小的哨兵，调用就会选中模板版本，因为推导出的精确匹配优于需要转换的版本。¶8.4 让任何能转换成 `size_t` 的 `End` 都不参与决议，于是第二个实参是整数时总是表示长度。反方向不需要约束，因为 `size_type` 是固定的类型，不会匹配迭代器哨兵。

</details>
