---
title: 对组
summary: std::pair 的完整契约——十余个条件 explicit 的构造函数、为什么复制赋值不能 = default（所以 pair 不是平凡可复制的）、平凡析构保证、结构化类型、const 赋值与 pair-like、piecewise_construct、元组式访问与 CTAD
status: done
covers: *
papers: P1951R1, P2255R2, P2321R2, P2165R4, P0892R2
related: utility, tuple, class.copy.assign, class.prop, dcl.struct.bind, over.match.best, class.base.init, temp.param, class.spaceship, utilities
tags: 标准库, pair, 条件 explicit, 平凡性, 结构化绑定
updated: 2026-10-18
---

`std::pair<T1, T2>` 看起来是标准库里最简单的类模板——两个公开数据成员 `first` 和 `second`，仅此而已。但它的条文有四十多段：十个构造函数、十二个赋值运算符，每一个都带着 *Constraints*、条件 `explicit` 或"定义为弃置"的备注。原因是 `pair` 要对**任意**的 `T1`、`T2` 都"表现得像两个独立的变量"——包括引用、不可复制类型、只能显式构造的类型、`const` 类型——同时又要能在泛型代码里被隐式地 `return {a, b};`。这些要求互相拉扯，条文就是它们的平衡点。

读本节需要的前置概念：条件 `explicit`（`explicit(bool)`，[[class.conv.ctor]]）、特殊成员函数的平凡性（[[class.prop]]、[[class.copy.ctor]]、[[class.copy.assign]]）、结构化绑定（[[dcl.struct.bind]]）、合成三路比较（[[g:synthesized-three-way-comparison]]）。与 `tuple` 共享的"tuple-like 协议"详见 [[tuple]]。

| 子条款 | 内容 |
|---|---|
| [pairs.general] | 概述 |
| [pairs.pair] | `pair` 类模板：构造、赋值、`swap`、平凡性与结构化类型 |
| [pairs.spec] | `==`、`<=>`、非成员 `swap`、`make_pair` |
| [pair.astuple] | `tuple_size`、`tuple_element`、`get` |
| [pair.piecewise] | `piecewise_construct_t` |

## 概述（[pairs.general]）

¶1：库提供一个异构二元组模板，一个简化构造的函数模板（`make_pair`），以及若干让 `pair` 能"像 `tuple` 一样被访问"的模板（[[tuple]] 的 [tuple.helper]、[tuple.elem]）。`pair` 本身声明在 `<utility>` 中——这是它和 `tuple` 的一个重要区别：`<utility>` 是全部 freestanding 的轻量头文件，关联容器的 `value_type` 就是 `pair<const Key, T>`。

## 类定义与全局性质（[pairs.pair]/1–4）

类定义的要点：

- 两个公开数据成员 `T1 first; T2 second;`，以及 `first_type` / `second_type` 别名。**没有私有成员、没有基类**——这让 `pair` 能成为结构化类型（见下）。
- `pair(const pair&) = default;` 与 `pair(pair&&) = default;` ——复制/移动构造函数是**预置的**。
- 其余构造函数几乎都是 `constexpr explicit(see below)`。
- 复制/移动赋值运算符**不是**预置的，而是普通声明的 `constexpr pair& operator=(const pair& p);`。
- 一个推导指引 `pair(T1, T2) -> pair<T1, T2>;`。

¶1：成员函数不抛异常，除非某个逐元素操作抛出。¶2：预置的复制/移动构造函数是 constexpr 函数，当且仅当所需的逐元素初始化都满足 constexpr 适用条件（[[g:constexpr-suitable]]，[[dcl.constexpr]]）。

### 平凡析构，但不是平凡可复制

!!! std "[pairs.pair]/3"
    If `(is_trivially_destructible_v<T1> && is_trivially_destructible_v<T2>)` is `true`, then the destructor of `pair` is trivial.

    两个成员都平凡可析构时，`pair` 的析构函数必须平凡。

这条保证"免费"成立：`pair` 不声明析构函数，隐式析构函数的平凡性本来就只取决于成员（[[class.dtor]]）。写成条文是为了**禁止实现**给 `pair` 加一个用户提供的析构函数（例如调试用途）。平凡析构对 `constexpr` 变量、`std::vector<pair<...>>` 的销毁优化都很重要。

复制/移动**构造**函数是 `= default` 的，所以 `pair<int, int>` 是平凡可复制构造的。但复制**赋值**是用户提供的函数——按 [[class.prop]]，一个类要成为[[g:trivially-copyable-class]]，所有合格的复制/移动赋值运算符都必须平凡。于是：

```cpp run title="pair_triviality.cpp" ok
#include <utility>
#include <type_traits>
#include <string>
#include <cstdio>

using PI = std::pair<int, int>;
static_assert(std::is_trivially_copy_constructible_v<PI>);   // 复制构造 = default
static_assert(std::is_trivially_destructible_v<PI>);         // ¶3 保证
static_assert(!std::is_trivially_copy_assignable_v<PI>);     // 复制赋值不是 = default
static_assert(!std::is_trivially_copyable_v<PI>);            // 于是整体不是平凡可复制

struct Ref { int& r; };                                       // 普通聚合：默认复制赋值被弃置
static_assert(!std::is_copy_assignable_v<Ref>);
static_assert(std::is_copy_assignable_v<std::pair<int&, int>>); // pair 的则是"透过引用赋值"

int main() {
  int a = 1, b = 2;
  std::pair<int&, int> p{a, 10}, q{b, 20};
  p = q;                                   // 把 b 的值赋给 a，p.first 仍然引用 a
  std::printf("a=%d b=%d &p.first==&a:%d\n", a, b, &p.first == &a);   // a=2 b=2 ... 1
}
```

**为什么复制赋值不能 `= default`？** 因为 `pair` 必须支持引用成员。按 [[class.copy.assign]]，含引用类型非静态数据成员的类，其预置复制赋值运算符被定义为**弃置的**——核心语言的立场是"引用不能重新绑定，所以无法赋值"。但 `pair<T&, U&>`（以及 `std::tie` 产生的 `tuple<T&...>`）的整个用途就是"**透过引用赋值**"：`p = q` 应当把 `q.first` 所引用对象的值赋给 `p.first` 所引用的对象。这只能由手写的 `first = p.first; second = p.second;` 实现。¶22 再补一句：这个运算符"定义为弃置的，除非 `is_copy_assignable_v<T1>` 且 `is_copy_assignable_v<T2>` 为 `true`"——注意 `is_copy_assignable_v<int&>` 是 `true`（对 `int&` 赋值就是给被引用的 `int` 赋值），所以引用成员不会导致弃置，`const int` 成员才会。

!!! lawyer "C++20 能不能让它'条件平凡'？"
    C++20 允许为同一个特殊成员函数写多个带 requires 子句的预期声明，例如 `pair& operator=(const pair&) requires (both trivially copy assignable) = default;` 加一个非预置的后备版本——这正是 `optional`/`variant` 实现"条件平凡"的技术（[[special]]、[[class.copy.assign]]）。标准从没对 `pair` 这样要求，实现也不敢自行这样做：平凡可复制性会影响 Itanium ABI 下的**参数传递方式**（平凡可复制的小类型可以在寄存器中传递），改变它就是 ABI 破坏。libc++ 甚至还保留着一个旧 ABI 宏 `_LIBCPP_DEPRECATED_ABI_DISABLE_PAIR_TRIVIAL_COPY_CTOR`（`__utility/pair.h`），在该模式下给 `pair` 加一个非平凡复制构造的私有基类，以兼容更早期"连复制构造都不平凡"的 ABI。

!!! impl "libc++ 如何实现'定义为弃置，除非……'"
    `__utility/pair.h` 中复制赋值的形参类型写成 `__conditional_t<is_copy_assignable<first_type>::value && is_copy_assignable<second_type>::value, pair, __nat> const&`。条件为假时，形参类型变成内部空类型 `__nat`，这个函数就不再是复制赋值运算符；而 `pair` 有用户声明的移动构造函数，于是隐式声明的复制赋值运算符被定义为弃置（[[class.copy.assign]]）——用核心语言规则"借"出了条文要求的弃置效果。

### 结构化类型（¶4）

¶4：若 `T` 与 `U` 都是结构化类型（[[g:structural-type]]，[[temp.param]]），则 `pair<T, U>` 也是；两个 `pair` 值模板实参等价，当且仅当 `first` 与 `second` 分别模板实参等价。这让 `pair` 可以直接作为常量模板形参的类型：

```cpp
template<std::pair<int, char> P>
constexpr int tag = P.first + P.second;
static_assert(tag<{1, 'a'}> == 98);
```

（`pair` 所有成员都是公开的、没有可变成员，按核心语言规则本来就满足结构化类型的条件；这一段把它变成了**对实现的要求**，禁止实现添加私有成员破坏这一点。）

## 构造函数：一张约束矩阵（¶5–¶19）

| 构造函数 | 段落 | *Constraints* | `explicit` 当且仅当 |
|---|---|---|---|
| `pair()` | ¶5–¶7 | 两者可默认构造 | 任一者不可隐式默认构造 |
| `pair(const T1&, const T2&)` | ¶8–¶10 | 两者可复制构造 | 任一者 `const Ti&` 不可隐式转换为 `Ti` |
| `pair(U1&&, U2&&)`，`U1 = T1, U2 = T2` | ¶11–¶13 | `is_constructible_v<Ti, Ui>` | 任一者 `Ui` 不可隐式转换为 `Ti` |
| `pair(pair<U1,U2>&)` 等四种 cv/引用 + `pair(P&&)` | ¶14–¶17 | 逐元素可从 `get<i>(FWD(p))` 构造；`P` 不是 `subrange` | 任一元素不可隐式转换 |
| `pair(piecewise_construct_t, tuple<A...>, tuple<B...>)` | ¶18–¶19 | 无（*Mandates*：可构造） | 从不 |

### 条件 `explicit` 的含义

`explicit(see below)`（[[g:conditionally-explicit]]）是 C++20 的 `explicit(bool)`（[[P0892R2]]）。规则一言以蔽之：**`pair` 的构造函数是否 explicit，跟随其元素的对应构造是否 explicit**。这样 `pair` 在"能否隐式转换"上与"两个独立变量"完全一致：

```cpp run title="pair_explicit.cpp" error
#include <utility>
#include <vector>
struct E { explicit E() = default; };
std::pair<std::vector<int>, int> f() { return {3, 1}; }   // error: vector(size_t) 是 explicit
std::pair<E, int> g() { return {}; }                       // error: 默认构造函数是 explicit
```

`return {3, 1};` 是复制列表初始化，若选中的构造函数是 explicit 则非良构（[[over.match.list]]）——就像 `std::vector<int> v = 3;` 不合法一样。

¶7 对默认构造函数的判据是"**是否可隐式默认构造**"（[[g:implicitly-default-constructible]]，即能否从 `{}` 复制列表初始化）。注 1 提示可以用"能否用 `{}` 初始化一个 `const T&`"来实现这个特征。上例的 `E` 有 explicit 预置默认构造函数，于是 `pair<E, int>` 的默认构造函数也是 explicit 的，`return {};` 失败，但 `std::pair<E, int> e{};`（直接列表初始化）可以。

!!! history "条件 explicit 的演进"
    C++11/14 里 `pair` 的构造函数要么一律隐式、要么一律 explicit，导致 `return {a, b};` 在很多合理场景下编译失败，或在不该隐式的场景下被接受。C++17 通过"改进 pair 与 tuple"的提案（N4387）规定"条件 explicit"，但那时语言里没有 `explicit(bool)`，规范只能写成"此构造函数是 explicit 的，当且仅当……"，实现者要为每个构造函数写**一对**互斥约束的重载（一个 explicit、一个不是）。C++20 的 `explicit(bool)` 让一个声明就能表达，条文也改写成了现在的 `explicit(see below)`。libc++ 的 `__utility/pair.h` 中能看到 `explicit(!__check_pair_construction<_T1, _T2>::template __is_implicit<_U1, _U2>())` 这样的写法。

### 转发构造函数的默认模板实参 {{c++23}}（¶11–¶13）

`template<class U1 = T1, class U2 = T2> pair(U1&& x, U2&& y)`——默认模板实参是 C++23 加的（[[P1951R1]]）。好处是花括号初始化列表也能匹配转发构造函数：

```cpp run title="pair_default_targs.cpp" ok
#include <utility>
#include <string>
#include <vector>
#include <array>
#include <tuple>
#include <functional>
#include <type_traits>

std::pair<std::string, int> ok1() { return {"pi", 3}; }   // 隐式：const char* → string 可隐式转换

struct E { explicit E() = default; };

int main() {
  // C++23：U1 = T1、U2 = T2 的默认模板实参让 {...} 也能推导
  std::pair<std::string, std::vector<int>> p{"a", {1, 2, 3}};

  // CTAD：按值的推导指引 → 退化
  std::pair q{1, "abc"};
  static_assert(std::is_same_v<decltype(q), std::pair<int, const char*>>);

  // make_pair：unwrap_ref_decay_t
  int i = 0;
  auto r = std::make_pair(std::ref(i), 1.0);
  static_assert(std::is_same_v<decltype(r), std::pair<int&, double>>);

  // C++23：从 pair-like（这里是 array<int, 2>）构造
  std::array<int, 2> a{7, 8};
  std::pair<long, long> s(a);

  // 显式默认构造：直接列表初始化 OK
  std::pair<E, int> e{};
  (void)e;
  return static_cast<int>(s.first + p.second.size()) - 10;
}
```

C++23 之前，`{1, 2, 3}` 无法推导 `U2`，转发构造函数不可行，只能退回 `pair(const T1&, const T2&)`——先构造临时 `vector` 再**复制**进去。有了默认实参，`U2` 取 `vector<int>`，花括号直接初始化右值引用形参绑定的临时量，然后**移动**进去。

### 禁止悬垂引用成员 {{c++23}}

¶13 与 ¶17 的 *Remarks* 规定：如果 `reference_constructs_from_temporary_v<first_type, U1&&>`（或 `second_type` 对应项）为真——即 `first` 是引用、而用实参初始化它会绑定到一个**临时量**——该构造函数**定义为弃置**（[[P2255R2]]）。典型场景：`pair<const long&, int> p(i, 2);` 中 `int` 左值 `i` 要先转换为临时 `long` 才能绑定，构造结束后 `first` 立即悬垂（[[g:dangling-reference-member]]）。

把它规定为"弃置"而非"非良构"的意义在于**可被检测**：选中弃置函数使 `is_constructible_v<pair<const long&, int>, int&, int>` 为 `false`，泛型代码可以据此回避。

!!! impl "libc++ 23 尚未完全实现"
    截至本文编写时，libc++ 23 的 `<version>` 中 `__cpp_lib_reference_from_temporary` 仍被注释掉。`pair` 的这个构造函数并没有被弃置：`is_constructible_v<std::pair<const long&, int>, int, int>` 在 libc++ 上得到 `true`。不过实际构造仍然会被拒绝——这是**核心语言**的功劳：[[class.base.init]] 规定在 mem-initializer 中把引用成员绑定到临时量是非良构的，Clang 报告 "reference member 'first' binds to a temporary object whose lifetime would be shorter than the lifetime of the constructed object"。区别只在于能否被 SFINAE/概念检测到。

### 从 `pair` 和 pair-like 构造（¶14–¶17）

¶14 定义 *FWD*(u) 为 `static_cast<decltype(u)>(u)`——对 `pair<U1,U2>&` 形参是左值、对 `&&` 形参是右值，这样一份条文同时描述四种 cv/引用组合。四种组合中 `pair<U1, U2>&`（非 const 左值）与 `const pair<U1, U2>&&` 是 C++23 为 `ranges::zip` 等**代理引用**场景添加的（[[P2321R2]]）：元素类型可能只有非 const 引用的构造函数。

最后一个重载 `template<pair-like P> pair(P&& p)` 是 C++23 的 [[P2165R4]] 加入的：任何 *pair-like* 类型（[[g:pair-like]]，[[tuple.like]]：大小为 2 的 `array`、`complex`、`pair`、`tuple`、`ranges::subrange`）都能转换为 `pair`。¶15.1 特意排除 `ranges::subrange`——`subrange` 自己有到 pair-like 类型的转换函数（[[range.subrange]]），两条路径同时存在会造成歧义或意外的行为，因此由 `subrange` 那一侧负责。

### 分段构造（¶18–¶19、[pair.piecewise]）

```cpp
template<class... Args1, class... Args2>
  constexpr pair(piecewise_construct_t, tuple<Args1...> first_args, tuple<Args2...> second_args);
```

¶19：用 `first_args` 中的元素（按 `std::forward<Ui>` 转发）直接构造 `first`，用 `second_args` 构造 `second`——称为**分段构造**（[[g:piecewise-construction]]）。它解决的问题是：元素类型不可复制也不可移动，或者构造需要多个实参，`pair(U1&&, U2&&)` 无法表达。¶18 的约束是 *Mandates*（硬错误）而不是 *Constraints*——这个构造函数有专属的标签类型，不会与其他重载混淆，没必要 SFINAE 友好。注 2 提醒：若某个成员是引用且其初始化绑定到临时量，程序非良构（[[class.base.init]]）。

[pair.piecewise] ¶1：`piecewise_construct_t` 是一个空类，用作"唯一类型"来消歧义；`inline constexpr piecewise_construct_t piecewise_construct{};` 是它的常量对象。其默认构造函数是 `explicit` 的预置函数，防止 `{}` 被隐式转换成标签。同样的模式也用在 `map::emplace` 中——`m.emplace(std::piecewise_construct, std::forward_as_tuple(k), std::forward_as_tuple(a, b))` 是原位构造 map 元素的标准写法。

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

template<std::pair<int, char> P>        // pair<int, char> 是结构化类型
constexpr int tag = P.first + P.second;

int main() {
  std::pair<Pinned, std::mutex> p(std::piecewise_construct,
                                  std::forward_as_tuple(1, "one"),
                                  std::forward_as_tuple());     // mutex 默认构造
  auto& [pin, mtx] = p;                 // tuple-like 协议 → 结构化绑定
  std::lock_guard lk(mtx);
  static_assert(tag<{1, 'a'}> == 98);
  std::printf("%d %s %d\n", pin.a, pin.b.c_str(), std::get<int>(std::pair{5, 'x'}));   // 1 one 5
}
```

## 赋值（¶20–¶49）

赋值运算符分为两族，每族六个：

- **普通赋值**（返回 `pair&`）：复制赋值（¶20–¶22，弃置除非可复制赋值）、移动赋值（¶32–¶35，*Constraints* 可移动赋值，`noexcept` 取两者的 `is_nothrow_move_assignable`）、从 `pair<U1,U2>` 的复制/移动赋值（¶26–¶28、¶39–¶41）、从 pair-like 赋值（¶42–¶44，要求 `different-from<P, pair>` 以免与复制/移动赋值冲突）。
- **const 赋值**（`const` 成员函数，返回 `const pair&`）：¶23–¶25、¶29–¶31、¶36–¶38、¶45–¶50。约束都写成 `is_assignable_v<const T1&, ...>`。

const 赋值看起来荒谬——给一个 const 对象赋值？——但它是为**代理引用**（[[g:proxy-reference]]）设计的（[[P2321R2]]）。`ranges::zip_view` 的引用类型是 `tuple<T1&, T2&>`（`pair` 同理）的 prvalue；算法对 `*it = value` 的要求（[[iterator.concept.writable]]）包含 `const_cast<const iter_reference_t<I>&&>(*it) = value` 这种形式。对 `pair<int&, int&>` 来说，`const` 的是 `pair` 本身而不是被引用的 `int`，透过引用赋值完全合理：`is_assignable_v<int& const&, int>` 即 `is_assignable_v<int&, int>` 为 `true`。对 `pair<int, int>`，`is_assignable_v<const int&, ...>` 为假，const 赋值不参与重载决议，不会意外地允许修改 const 对象。

!!! lawyer "条文里的一个笔误"
    当前草案 ¶49 写的是 "Assigns `std::forward<U1>(p.first)` to `first` and `std::forward<U2>(u.second)` to `second`"——形参名是 `p`，`u.second` 显然是笔误；¶40 也漏了一个 "to"。这类问题属于编辑性错误，不影响规范含义。读标准时遇到"明显不通"的措辞，先怀疑笔误，再去 GitHub 上的 draft 仓库核对。

## `swap`（¶51–¶54 与 [pairs.spec]/4–5）

成员 `swap(pair&)` 与 `swap(const pair&) const`：¶51 是 *Mandates*（成员函数不需要 SFINAE 友好），¶52 *Preconditions* 要求逐元素可交换（[[swappable.requirements]]），¶53 逐元素交换，¶54 异常规格是 `is_nothrow_swappable_v<T1> && is_nothrow_swappable_v<T2>`（const 版本对应 `const T1`、`const T2`）。

非成员 `swap(pair&, pair&)`（[pairs.spec]/4）则是 *Constraints*：泛型代码通过两步法或 `ranges::swap` 探测"可交换性"时调用的是非成员版本，它必须 SFINAE 友好，`is_swappable_v<pair<T1, T2>>` 才能如实反映元素的可交换性。

## 比较与 `make_pair`（[pairs.spec]）

### `operator==`（¶1–¶2）

*Constraints*：`x.first == y.first` 与 `x.second == y.second` 是有效表达式，且结果类型满足 *boolean-testable*（[[concept.booleantestable]]）。这个约束是 C++26 的"受约束的相等比较"工作加上的：以前 `operator==` 无约束，`equality_comparable<pair<T, U>>` 对不可比较的 `T` 也会"假阳性"，直到实例化函数体才报错。¶2 返回 `x.first == y.first && x.second == y.second`——短路。注意左右两边可以是**不同的** `pair` 特化（`pair<T1,T2>` 与 `pair<U1,U2>`）。

### `operator<=>`（¶3）

返回类型是 `common_comparison_category_t<synth-three-way-result<T1, U1>, synth-three-way-result<T2, U2>>`，效果是先比 `first`、不等则返回，否则比 `second`。*synth-three-way*（库的说明专用实体，[[expos.only.entity]]；语义同核心语言的[[g:synthesized-three-way-comparison]]）的意义：**元素类型没有 `<=>`、只有 `<` 和 `==` 时，用它们合成一个 `weak_ordering`**。这让 C++20 之前写的老类型放进 `pair` 后照样能比较：

```cpp run title="pair_spaceship.cpp" ok
#include <utility>
#include <compare>
#include <type_traits>

struct Legacy {                     // C++20 之前的老类型：只有 == 和 <
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

`<`、`<=`、`>`、`>=` 由 [[over.match.oper]] 的重写候选从 `<=>` 得到，`!=` 从 `==` 得到。C++20 前的六个独立运算符模板都被删除了。

### `make_pair`（¶6–¶7）

返回 `pair<unwrap_ref_decay_t<T1>, unwrap_ref_decay_t<T2>>(std::forward<T1>(x), std::forward<T2>(y))`。`unwrap_ref_decay_t`（[[g:unwrap-ref-decay]]）先 `decay`（数组→指针、去掉 cv 和引用），再把 `reference_wrapper<X>` 展开为 `X&`——于是 `make_pair(std::ref(i), 1.0)` 得到 `pair<int&, double>`（见上文例子）。有了 C++17 CTAD 之后，`make_pair` 的主要价值就剩下这个 `reference_wrapper` 展开：类模板实参推导用的是推导指引 `pair(T1, T2) -> pair<T1, T2>`，**按值**接收，只做 decay，不展开 `reference_wrapper`——`std::pair{std::ref(i), 1.0}` 的类型是 `pair<reference_wrapper<int>, double>`。

## 元组式访问（[pair.astuple]）

`pair` 实现了 tuple-like 协议（详见 [[tuple]] 的 [tuple.helper]）：

- `tuple_size<pair<T1, T2>>` 派生自 `integral_constant<size_t, 2>`；
- `tuple_element<I, pair<T1, T2>>::type`：¶1 *Mandates* `I < 2`，¶2 `I == 0` 为 `T1`，否则为 `T2`；
- `get<I>(p)` 四个重载（`&`、`const&`、`&&`、`const&&`），¶3 *Mandates* `I < 2`，¶4 返回对 `first` 或 `second` 的引用；
- 按类型的 `get<T>(p)`：¶5/¶7 *Mandates* `T1` 与 `T2` 是不同类型。

有了 `tuple_size` 和 `get`，结构化绑定（[[dcl.struct.bind]]）走的就是"tuple-like 绑定协议"这条路：`auto [k, v] = p;` 中 `k`、`v` 是对隐藏变量调用 `get<0>`、`get<1>` 的结果（不过 `pair` 的成员都是公开的，即使没有协议，结构化绑定也能走"按数据成员绑定"那条路，而且结果一样）。

```cpp run title="pair_get_type.cpp" error
#include <utility>
int main() {
  std::pair<int, int> p{1, 2};
  return std::get<int>(p);        // error: T1 与 T2 相同，Mandates 不满足
}
```

!!! lawyer "按类型 get 的 Mandates 其实是冗余的"
    `get<T>` 的两个函数模板分别声明为 `template<class T1, class T2> T1& get(pair<T1, T2>&)` 与 `template<class T2, class T1> T2& get(pair<T1, T2>&)`。对 `pair<int, int>` 调用 `get<int>`，两个模板都能推导成功、签名完全相同，偏序也分不出高下（[[temp.func.order]]），重载决议本身就是**歧义**的——libc++ 报的也正是 "call to 'get' is ambiguous"。*Mandates* 只是把"这是个错误"明确写出来，让实现可以给出更好的诊断。

## 与 `common_type` / `common_reference` 的联动

`<utility>` 概要中为 `pair` 特化了 `common_type<pair<T1,T2>, pair<U1,U2>>`（逐元素 `common_type`）与 `basic_common_reference<pair<...>, pair<...>, TQual, UQual>`（逐元素 `common_reference`）。它们是 C++23 [[P2321R2]] 为 `zip` 准备的：`zip_view` 的迭代器要满足 `indirectly_readable`，就要求 `pair<int&, int&>`（引用类型）与 `pair<int, int>`（值类型）有公共引用类型。规则与 `tuple` 的对应特化相同，详见 [[tuple]]。

## 常见误区

!!! pitfall "易错点清单"
    - **不要假设 `pair<int, int>` 平凡可复制**：`std::is_trivially_copyable_v` 为 `false`，因此不能把它当作 `memcpy` 的合法对象或 `std::bit_cast` 的源/目标（`bit_cast` 要求平凡可复制）。
    - **`std::pair{std::ref(x), y}` 不会得到引用成员**，要用 `make_pair`。
    - **`map<K, V>::value_type` 是 `pair<const K, V>`**：写 `for (const std::pair<K, V>& kv : m)` 会让每个元素都**转换**出一个临时 `pair<K, V>`（通过转换构造函数），既慢又可能让引用悬垂。用 `const auto&` 或结构化绑定。
    - **const 赋值不是"给 const 对象赋值的后门"**：只有元素类型本身支持 `const` 赋值（引用、代理类型）时才参与重载决议。
    - **悬垂的引用成员**：`pair<const std::string&, int> p("abc", 1);` 在 C++23 标准下被弃置，旧代码里这曾经是静默的悬垂。

## 思考题

!!! question "思考题 1"
    为什么 `pair` 的复制/移动**构造**函数可以 `= default`，复制/移动**赋值**运算符却不行？

<details markdown="1">
<summary>展开查看答案与解析</summary>

预置复制构造函数对引用成员做的是"用源对象的引用成员初始化本对象的引用成员"，即绑定到同一个对象——这是合法且正确的语义，所以引用成员不会导致复制构造弃置（[[class.copy.ctor]]）。预置复制赋值则无法"重新绑定"引用，核心语言规定含引用成员的类的预置复制赋值为弃置（[[class.copy.assign]]）。`pair<T&, U&>` 需要的是"透过引用赋值"，只能手写。由此导致的连锁反应：`pair` 永远不是平凡可复制类型（[[class.prop]]）。
</details>

!!! question "思考题 2"
    `std::pair<std::string, std::string> f() { return {"a", "b"}; }` 选中哪个构造函数？在 C++11 与 C++23 中有区别吗？

<details markdown="1">
<summary>展开查看答案与解析</summary>

两个候选：`pair(const T1&, const T2&)` 需要先把两个字符串字面量转换成临时 `std::string` 再复制；`pair(U1&&, U2&&)` 推导 `U1 = const char(&)[2]`、`U2 = const char(&)[2]`，直接用字面量构造成员，是**精确匹配**（引用绑定，[[over.ics.ref]]），优于需要用户定义转换的前者，所以选中转发构造函数。它不是 explicit 的，因为 `const char(&)[2]` 可隐式转换为 `string`。C++11 与 C++23 在这里结果相同——C++23 的默认模板实参只影响**花括号**实参（无法推导）的情形。
</details>

## 小结

!!! summary "核心要点"
    | 性质 | 规定 |
    |---|---|
    | 复制/移动构造 | `= default`，平凡当且仅当元素的对应构造平凡 |
    | 复制/移动赋值 | 用户提供（为支持透过引用赋值），所以 `pair` **不是**平凡可复制类型 |
    | 析构 | 两元素平凡可析构则平凡（¶3 保证） |
    | 结构化类型 | 两元素都是结构化类型时是（¶4） |
    | 构造函数的 explicit | 跟随元素对应转换是否隐式 |
    | 悬垂引用 | C++23 起相关构造函数定义为弃置（libc++ 23 仍靠核心语言规则报错） |
    | const 赋值 | 为代理引用（`zip`）服务，约束为 `is_assignable_v<const Ti&, ...>` |
    | 比较 | `==` 受约束；`<=>` 用 *synth-three-way*，兼容只有 `<` 的老类型 |
    | `make_pair` vs CTAD | 前者展开 `reference_wrapper`，后者不展开 |
