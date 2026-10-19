---
title: 对组
summary: std::pair 的完整规定：构造函数何时 explicit、为什么复制赋值要手写（因而 pair 不是平凡可复制的）、悬垂引用成员、const 赋值与 pair-like、分段构造、比较、make_pair 与元组式访问。
status: done
covers: *
papers: P1951R1, P2255R2, P2321R2, P2165R4, P0892R2
related: utility, tuple, class.copy.assign, class.prop, dcl.struct.bind, over.match.best, class.base.init, temp.param, class.spaceship, utilities
tags: 标准库, pair, 条件 explicit, 平凡性, 结构化绑定
updated: 2026-10-19
---

!!! tldr
    - `pair` 的复制赋值是手写的，因为它要支持引用成员并透过引用赋值；代价是 `pair<int, int>` 不是平凡可复制类型，不能 `memcpy` 或 `bit_cast`。
    - 每个构造函数是否 `explicit` 跟随元素的对应转换：元素能隐式转换，`return {a, b};` 就能编译。
    - C++23 起，会让引用成员绑定到临时量的构造函数被定义为弃置，`pair<const long&, int>(i, 2)` 不再悄悄悬垂。
    - `const` 赋值运算符是为 `zip` 这类代理引用准备的，只有元素本身支持 `const` 赋值（比如引用）时才可用。
    - `make_pair` 会把 `reference_wrapper` 展开成引用，CTAD 不会：`std::pair{std::ref(i), 1.0}` 的第一个成员是 `reference_wrapper<int>`。

`std::pair<T1, T2>` 只有两个公开数据成员 `first` 和 `second`，条文却有五十多段：十个构造函数、十二个赋值运算符，每个都带着约束、条件 `explicit` 或弃置条件。原因是 `pair` 要对任意的 `T1`、`T2`（引用、不可复制类型、只能显式构造的类型、`const` 类型）都表现得像两个独立的变量，同时又要能在泛型代码里写 `return {a, b};`。

库条文用几个固定的标签描述函数。*Constraints* 不满足时，函数不参与重载决议；*Mandates* 不满足时，程序非良构；*Preconditions* 不满足时，行为未定义（[[structure.specifications]]）。

## 透过引用赋值，代价是不平凡

```cpp run title="pair_assign.cpp" ok
#include <utility>
#include <type_traits>
#include <cstdio>

struct Ref { int& r; };                       // 普通聚合
static_assert(!std::is_copy_assignable_v<Ref>);                  // 复制赋值被弃置
static_assert(std::is_copy_assignable_v<std::pair<int&, int>>);  // pair 可以赋值

int main() {
  int a = 1, b = 2;
  std::pair<int&, int> p{a, 10}, q{b, 20};
  p = q;                  // 把 b 的值赋给 a；p.first 仍然引用 a
  std::printf("a=%d b=%d same:%d\n", a, b, &p.first == &a);   // a=2 b=2 same:1
}
```

核心语言规定，含引用成员的类的预置复制赋值运算符是弃置的（[[class.copy.assign]]），因为引用不能重新绑定。可是 `pair<T&, U&>` 和 `std::tie` 产生的 `tuple<T&...>` 的用途恰恰是透过引用赋值：`p = q` 把 `q.first` 所引用对象的值赋给 `p.first` 所引用的对象。这只能手写成 `first = p.first; second = p.second;`。

所以类定义里复制、移动构造函数是 `= default`，复制、移动赋值运算符却是普通声明的函数。¶20–¶22 规定复制赋值逐个赋值成员，并且定义为弃置，除非 `is_copy_assignable_v<T1>` 和 `is_copy_assignable_v<T2>` 都为真。`is_copy_assignable_v<int&>` 为真（给 `int&` 赋值就是给被引用的 `int` 赋值），所以引用成员不会导致弃置，`const int` 成员才会。

### 平凡性的后果（¶3）

**平凡可复制类型**（[[g:trivially-copyable-class|trivially copyable]]）可以用 `memcpy` 复制，也可以作 `std::bit_cast` 的源和目标。按 [[class.prop]]，它要求所有可用的复制、移动赋值运算符都是平凡的。`pair` 的赋值运算符是用户提供的，于是：

```cpp run title="pair_triviality.cpp" ok
#include <utility>
#include <type_traits>
using PI = std::pair<int, int>;
static_assert(std::is_trivially_copy_constructible_v<PI>);   // 复制构造 = default
static_assert(std::is_trivially_destructible_v<PI>);         // ¶3 保证
static_assert(!std::is_trivially_copy_assignable_v<PI>);     // 复制赋值是手写的
static_assert(!std::is_trivially_copyable_v<PI>);            // 整体不是平凡可复制
int main() {}
```

!!! std "[pairs.pair]/3"
    If `(is_trivially_destructible_v<T1> && is_trivially_destructible_v<T2>)` is `true`, then the destructor of `pair` is trivial.

¶3 两个成员都平凡可析构时，`pair` 的析构函数必须是平凡的。`pair` 不声明析构函数，隐式析构函数本来就是这样（[[class.dtor]]）。写成条文是为了禁止实现给 `pair` 加一个用户提供的析构函数，比如出于调试目的。

!!! lawyer "能不能让赋值有条件地平凡？"
    C++20 允许为同一个特殊成员函数写多个带 requires 子句的声明，比如一个在元素都平凡可赋值时 `= default`，另一个作为后备手写。`optional`、`variant` 就用这个技术做到有条件地平凡（[[class.copy.assign]]）。标准从没对 `pair` 这样要求，实现也不能自行这样做：平凡可复制性影响 Itanium ABI 下的参数传递方式，改变它会破坏 ABI。libc++ 的 `__utility/pair.h` 甚至还保留着旧 ABI 宏 `_LIBCPP_DEPRECATED_ABI_DISABLE_PAIR_TRIVIAL_COPY_CTOR`，用来兼容更早的、连复制构造都不平凡的布局。

!!! impl "libc++ 怎样实现定义为弃置，除非……"
    libc++ 把复制赋值的形参类型写成 `__conditional_t<is_copy_assignable<first_type>::value && is_copy_assignable<second_type>::value, pair, __nat> const&`。条件为假时形参类型变成内部空类型 `__nat`，这个函数就不再是复制赋值运算符；`pair` 又有用户声明的移动构造函数，于是隐式声明的复制赋值运算符被定义为弃置（[[class.copy.assign]]），借核心语言规则得到了条文要求的效果。

## 构造函数是否 explicit（¶5–¶13）

<div class="compare" markdown="1">

```cpp ok
#include <utility>
#include <string>
std::pair<std::string, int> f() {
  return {"pi", 3};   // OK
}
```

```cpp error
#include <utility>
#include <vector>
std::pair<std::vector<int>, int> g() {
  return {3, 1};  // error: explicit
}
```

</div>

`return {...};` 是复制列表初始化，选中 `explicit` 构造函数时非良构（[[over.match.list]]）。左边 `const char*` 能隐式转换为 `std::string`，选中的构造函数不是 `explicit`；右边 `vector(size_t)` 是 `explicit` 的，`pair` 的对应构造函数也就是 `explicit` 的，正如 `std::vector<int> v = 3;` 不合法。

这就是所有构造函数共同的规则：**`pair` 的构造函数是否 `explicit`，跟随元素的对应转换是否隐式**。条文用 C++20 的条件 `explicit`（`explicit(bool)`，[[class.conv.ctor]]，[[P0892R2]]）表达，每个构造函数写作 `explicit(see below)`。

| 构造函数 | 段落 | *Constraints* | `explicit` 当且仅当 |
|---|---|---|---|
| `pair()` | ¶5–¶7 | 两者可默认构造 | 任一者不可隐式默认构造 |
| `pair(const T1&, const T2&)` | ¶8–¶10 | 两者可复制构造 | 任一者 `const Ti&` 不可隐式转换为 `Ti` |
| `pair(U1&&, U2&&)` | ¶11–¶13 | `is_constructible_v<Ti, Ui>` | 任一者 `Ui` 不可隐式转换为 `Ti` |
| 从 `pair<U1, U2>` 和 pair-like 构造 | ¶14–¶17 | 逐元素可构造；不是 `subrange` | 任一元素不可隐式转换 |
| 分段构造 | ¶18–¶19 | 无（*Mandates*：可构造） | 从不 |

¶6–¶7 默认构造函数值初始化两个成员。判断它是否 `explicit` 的标准是元素能否**隐式默认构造**（[[g:implicitly-default-constructible|implicitly default-constructible]]），即能否从 `{}` 复制列表初始化。注 1 提示可以检查能否用 `{}` 初始化一个 `const T&` 来实现这个判断。如果 `E` 的默认构造函数是 `explicit` 的，`std::pair<E, int> g() { return {}; }` 不合法，`std::pair<E, int> e{};` 却可以。

!!! history
    C++11 里 `pair` 的构造函数要么一律隐式、要么一律 `explicit`，`return {a, b};` 在很多合理的场景下编译失败。C++17 改为条件 `explicit`，但当时语言里没有 `explicit(bool)`，实现者只能为每个构造函数写一对约束互斥的重载，一个 `explicit`，一个不是。C++20 的 `explicit(bool)` 让一个声明就能表达，条文也改写成了现在的样子。

### 花括号实参与默认模板实参 {{c++23}}（¶11–¶12）

转发构造函数写作 `template<class U1 = T1, class U2 = T2> pair(U1&& x, U2&& y)`，默认模板实参是 C++23 加的（[[P1951R1]]）。

```cpp
std::pair<std::string, std::vector<int>> p{"a", {1, 2, 3}};
```

花括号列表 `{1, 2, 3}` 不能用来推导模板形参。C++23 之前 `U2` 推导失败，转发构造函数不可行，只能退回 `pair(const T1&, const T2&)`：先构造一个临时 `vector`，再复制进去。有了默认实参，`U2` 取 `vector<int>`，临时量被移动进去，省了一次复制。

### 禁止悬垂的引用成员 {{c++23}}（¶13、¶17）

```cpp error
#include <utility>
int main() {
  int i = 1;
  std::pair<const long&, int> p(i, 2);   // error: first 会绑定到临时 long
}
```

`int` 左值 `i` 要先转换成一个临时 `long`，`first` 才能绑定。构造结束时临时量就销毁了，`first` 成了悬垂引用。¶13 和 ¶17 规定，只要 `reference_constructs_from_temporary_v<first_type, U1&&>` 或 `second` 的对应项为真，这个构造函数就定义为弃置（[[P2255R2]]）。

定义为弃置而不只是非良构，好处是可以检测：`is_constructible_v<pair<const long&, int>, int&, int>` 为假，泛型代码能据此避开。

!!! impl "libc++ 23 尚未实现这一条"
    libc++ 23 中特性测试宏 `__cpp_lib_reference_from_temporary` 仍被注释掉。上面的 `is_constructible_v` 在 libc++ 上为真，构造函数并没有被弃置。实际构造仍会失败，靠的是核心语言规则：在成员初始化器中把引用成员绑定到临时量是非良构的（[[class.base.init]]）。Clang 报告 `reference member 'first' binds to a temporary object whose lifetime would be shorter than the lifetime of the constructed object`。区别只在于泛型代码能否在不出错的情况下检测到它。

### 从 pair 和 pair-like 构造（¶14–¶17）

¶14 定义 *FWD*(u) 为 `static_cast<decltype(u)>(u)`：形参是 `pair<U1, U2>&` 时得到左值，是 `&&` 时得到右值。这样一份条文就能描述 `pair<U1, U2>&`、`const&`、`&&`、`const&&` 四种重载。其中非 `const` 左值和 `const` 右值两种是 C++23 为 `ranges::zip` 加的（[[P2321R2]]），用于元素类型只能从非 `const` 引用构造之类的代理场景。

¶15–¶16 最后一个重载 `template<pair-like P> pair(P&& p)` 也是 C++23 加的（[[P2165R4]]）。**pair-like** 类型指大小为 2 的 tuple-like 类型（[[tuple.like]]）：`array<T, 2>`、`complex`、`pair`、两个元素的 `tuple`、`ranges::subrange`，所以 `std::pair<long, long> s(arr);` 可以从 `std::array<int, 2>` 构造。¶15.1 排除了 `subrange`，因为 `subrange` 自己就有到 pair-like 类型的转换函数（[[range.subrange]]），两条路径并存会造成歧义。

### 分段构造（¶18–¶19、[pair.piecewise]）

元素类型既不能复制也不能移动，或者构造它需要多个实参时，`pair(U1&&, U2&&)` 就无能为力了。¶19 提供的**分段构造**（piecewise construction）把每个元素的构造实参分别装进一个 `tuple`，在成员的位置上直接构造：

```cpp run title="piecewise.cpp" ok
#include <utility>
#include <tuple>
#include <mutex>
#include <string>
#include <cstdio>

struct Pinned {                         // 不可复制也不可移动
  Pinned(int a, std::string b) : a(a), b(std::move(b)) {}
  Pinned(const Pinned&) = delete;
  int a; std::string b;
};

int main() {
  std::pair<Pinned, std::mutex> p(std::piecewise_construct,
                                  std::forward_as_tuple(1, "one"),
                                  std::forward_as_tuple());     // mutex 默认构造
  auto& [pin, mtx] = p;
  std::lock_guard lk(mtx);
  std::printf("%d %s\n", pin.a, pin.b.c_str());                 // 1 one
}
```

¶18 的要求是 *Mandates* 而不是 *Constraints*：这个构造函数有专门的标签类型作第一个形参，不会和别的重载混淆，不必在重载决议阶段排除。注 2 提醒，如果某个成员是引用并因此绑定到临时量，程序非良构（[[class.base.init]]）。

[pair.piecewise] ¶1 规定 `piecewise_construct_t` 是一个空类，只用作区分重载的标签；`piecewise_construct` 是它的常量对象。它的默认构造函数是 `explicit` 的，防止 `{}` 被隐式转换成标签。关联容器的 `emplace` 用同样的写法原位构造元素：`m.emplace(std::piecewise_construct, std::forward_as_tuple(k), std::forward_as_tuple(a, b))`。

## 赋值的两族（¶20–¶50）

赋值运算符有两族，每族六个，来源相同：复制（¶20–¶25）、从 `const pair<U1, U2>&`（¶26–¶31）、移动（¶32–¶38）、从 `pair<U1, U2>&&`（¶39–¶41、¶48–¶50）、从 pair-like（¶42–¶47）。

普通的一族返回 `pair&`。移动赋值的异常规格是两个元素的 `is_nothrow_move_assignable_v` 相与（¶35）。从 pair-like 赋值要求 `P` 不是 `pair` 本身（¶42.1），以免和复制、移动赋值冲突。

另一族是 `const` 成员函数，返回 `const pair&`，约束写成 `is_assignable_v<const T1&, ...>`。给 `const` 对象赋值看起来不合理，它是为**代理引用**准备的（[[P2321R2]]）。`ranges::zip_view` 的迭代器解引用得到的是 `pair<T1&, T2&>` 或 `tuple<T&...>` 的 prvalue，而可写迭代器的要求（[[iterator.concept.writable]]）包含 `const_cast<const iter_reference_t<I>&&>(*it) = value` 这种形式。

对 `pair<int&, int&>`，`const` 修饰的是 `pair` 本身，不是被引用的 `int`，透过引用赋值仍然合理，`is_assignable_v<int& const&, int>` 就是 `is_assignable_v<int&, int>`，为真。对 `pair<int, int>`，`is_assignable_v<const int&, int>` 为假，`const` 赋值不参与重载决议，不会意外允许修改 `const` 对象。

## swap（¶51–¶54、[pairs.spec]/4–5）

成员 `swap(pair&)` 和 `swap(const pair&) const` 逐个交换元素。¶51 的可交换要求是 *Mandates*，¶54 的异常规格取两个元素的 `is_nothrow_swappable_v`（`const` 版本对应 `const T1`、`const T2`）。

非成员 `swap`（[pairs.spec] ¶4）的要求则是 *Constraints*。泛型代码通过 `using std::swap; swap(a, b);` 或 `ranges::swap` 判断类型能否交换时，调用的是非成员版本。只有它在元素不可交换时退出重载决议，`is_swappable_v<pair<T1, T2>>` 才能如实反映元素的情况。

## 比较与 make_pair（[pairs.spec]）

¶1–¶2 `operator==` 要求 `x.first == y.first` 和 `x.second == y.second` 有效，且结果满足 *boolean-testable*（能像 `bool` 一样用在 `&&`、`!` 中，见 [[concept.booleantestable]]）；返回两者的 `&&`，有短路。两侧可以是不同的 `pair` 特化。这个约束是 C++26 加的，以前元素不可比较时 `equality_comparable<pair<T, U>>` 也为真，直到实例化函数体才报错。

¶3 `operator<=>` 先比较 `first`，不相等就返回，否则比较 `second`。它用的 *synth-three-way*（语义同核心语言的[[g:synthesized-three-way-comparison|合成三路比较]]）在元素类型没有 `<=>`、只有 `<` 和 `==` 时，用它们合成一个 `weak_ordering`。C++20 之前写的类型放进 `pair` 照样能比较：

```cpp run title="pair_spaceship.cpp" ok
#include <utility>
#include <compare>
#include <type_traits>

struct Legacy {                     // 只有 == 和 < 的老类型
  int v;
  bool operator==(const Legacy&) const = default;
  constexpr bool operator<(const Legacy& o) const { return v < o.v; }
};

using P = std::pair<int, Legacy>;
static_assert(std::is_same_v<decltype(P{} <=> P{}), std::weak_ordering>);
static_assert(P{1, {2}} < P{1, {3}});
static_assert(std::is_same_v<decltype(std::pair{1, 2.0} <=> std::pair{1, 2.0}),
                             std::partial_ordering>);
int main() {}
```

`<`、`<=`、`>`、`>=` 和 `!=` 由 [[over.match.oper]] 的重写候选从 `<=>`、`==` 得到。C++20 之前的六个独立比较运算符模板都删掉了。

¶6 `make_pair(x, y)` 返回 `pair<unwrap_ref_decay_t<T1>, unwrap_ref_decay_t<T2>>`。`unwrap_ref_decay_t` 先做 `decay`（数组变指针，去掉 cv 和引用），再把 `reference_wrapper<X>` 展开成 `X&`。CTAD 用的推导指引 `pair(T1, T2) -> pair<T1, T2>` 是按值接收的，只做 `decay`：

<div class="compare" markdown="1">

```cpp ok
#include <utility>
#include <functional>
int i = 0;
auto r = std::make_pair(std::ref(i), 1.0);
// pair<int&, double>
```

```cpp ok
#include <utility>
#include <functional>
int i = 0;
std::pair r{std::ref(i), 1.0};
// pair<reference_wrapper<int>, double>
```

</div>

有了 C++17 的 CTAD，`make_pair` 剩下的主要用处就是这个展开。

## 元组式访问（[pair.astuple]）

`pair` 实现了 tuple-like 协议（[[tuple]]）：

- `tuple_size<pair<T1, T2>>` 派生自 `integral_constant<size_t, 2>`；
- `tuple_element<I, pair<T1, T2>>::type` 在 `I` 为 0 时是 `T1`，否则是 `T2`，要求 `I < 2`（¶1–¶2）；
- `get<I>(p)` 有 `&`、`const&`、`&&`、`const&&` 四个重载，返回对 `first` 或 `second` 的引用（¶3–¶4）；
- 按类型取的 `get<T>(p)` 要求 `T1` 和 `T2` 是不同的类型（¶5–¶8）。

结构化绑定 `auto [k, v] = p;` 因此走 tuple-like 协议，对隐藏变量调用 `get<0>`、`get<1>`（[[dcl.struct.bind]]）。`pair` 的成员都是公开的，即使没有协议，按数据成员绑定的结果也一样。

```cpp run title="pair_get_type.cpp" error
#include <utility>
int main() {
  std::pair<int, int> p{1, 2};
  return std::get<int>(p);        // error: T1 与 T2 相同
}
```

!!! lawyer "按类型 get 的 Mandates 其实是多余的"
    两组 `get<T>` 分别声明为 `template<class T1, class T2> T1& get(pair<T1, T2>&)` 和 `template<class T2, class T1> T2& get(pair<T1, T2>&)`。对 `pair<int, int>` 调用 `get<int>`，两个模板都推导成功，签名完全相同，偏序也分不出高下（[[temp.func.order]]），重载决议本身就是二义的。libc++ 报的正是 `call to 'get' is ambiguous`。*Mandates* 只是把这是个错误明确写出来，方便实现给出更好的诊断。

## 作为常量模板实参（¶4）

¶4 `T` 和 `U` 都是[[g:structural-type|结构化类型]]（能作常量模板形参的类型，[[temp.param]]）时，`pair<T, U>` 也是；两个 `pair` 值作模板实参等价，当且仅当 `first`、`second` 分别等价。

```cpp ok
#include <utility>
template<std::pair<int, char> P>
constexpr int tag = P.first + P.second;
static_assert(tag<{1, 'a'}> == 98);
```

`pair` 的成员都是公开的、非 `mutable` 的，按核心语言规则本来就满足条件。这一段把它变成对实现的要求，禁止实现添加私有成员。

## 与 common_type、common_reference 的联动

`<utility>` 为 `pair` 特化了 `common_type`（逐元素取 `common_type`）和 `basic_common_reference`（逐元素取 `common_reference`），见 [[utility]]。它们是 C++23 为 `zip` 准备的（[[P2321R2]]）：`zip_view` 的迭代器要满足 `indirectly_readable`，`pair<int&, int&>`（引用类型）和 `pair<int, int>`（值类型）就必须有公共引用类型。`tuple` 有同样的特化，见 [[tuple]]。

<details class="fine" markdown="1"><summary>其余条文</summary>

[pairs.general] ¶1 说明库提供 `pair`、`make_pair`，以及让 `pair` 能像 `tuple` 一样访问的模板。

[pairs.pair] ¶1 成员函数不抛异常，除非它调用的某个逐元素操作抛出。

¶2 预置的复制、移动构造函数是 constexpr 函数，当且仅当所需的逐元素初始化都满足 constexpr 适用条件（[[dcl.constexpr]]）。

[pairs.spec] ¶7 的例子说明 `make_pair(5, 3.1415926)` 可以代替 `pair<int, double>(5, 3.1415926)`。

当前草案的 ¶49 写作 "Assigns `std::forward<U1>(p.first)` to `first` and `std::forward<U2>(u.second)` to `second`"，`u.second` 应为 `p.second`；¶40 漏了一个 "to"。这些是编辑性错误，不影响含义。

</details>

## 常见误解

!!! pitfall "pair<int, int> 可以 memcpy"
    `std::is_trivially_copyable_v<std::pair<int, int>>` 为假，它不能作 `memcpy` 的合法对象，也不能作 `std::bit_cast` 的源或目标。需要平凡可复制的二元组时，自己写一个聚合 `struct`。

!!! pitfall "遍历 map 时写 const std::pair<K, V>&"
    `map<K, V>::value_type` 是 `pair<const K, V>`。`for (const std::pair<K, V>& kv : m)` 会为每个元素经转换构造函数造出一个临时 `pair<K, V>`，既有复制开销，又容易让保存下来的引用悬垂。用 `const auto&` 或结构化绑定。

!!! pitfall "const 赋值让 const pair 可以被修改"
    只有元素类型本身支持 `const` 赋值（引用、代理类型）时，`const` 赋值运算符才参与重载决议。`const std::pair<int, int>` 仍然不能赋值。

## 思考题

!!! question "思考题 1"
    为什么 `pair` 的复制构造函数可以 `= default`，复制赋值运算符却不行？

<details markdown="1">
<summary>答案</summary>

预置复制构造函数用源对象的引用成员初始化本对象的引用成员，也就是绑定到同一个对象，这是合法且正确的语义，引用成员不会让复制构造弃置（[[class.copy.ctor]]）。预置复制赋值无法重新绑定引用，核心语言规定含引用成员的类的预置复制赋值是弃置的（[[class.copy.assign]]）。`pair<T&, U&>` 需要的是透过引用赋值，只能手写。连带的结果是 `pair` 永远不是平凡可复制类型（[[class.prop]]）。
</details>

!!! question "思考题 2"
    `std::pair<std::string, std::string> f() { return {"a", "b"}; }` 选中哪个构造函数？C++11 和 C++23 有区别吗？

<details markdown="1">
<summary>答案</summary>

有两个候选。`pair(const T1&, const T2&)` 要先把两个字符串字面量转换成临时 `std::string`，是用户定义转换。`pair(U1&&, U2&&)` 推导出 `U1 = U2 = const char(&)[2]`，实参直接绑定引用，是精确匹配（[[over.ics.ref]]），所以选中转发构造函数。`const char(&)[2]` 能隐式转换为 `string`，它不是 `explicit` 的。

C++11 和 C++23 结果相同。C++23 的默认模板实参只影响实参是花括号列表、无法推导的情形。
</details>
