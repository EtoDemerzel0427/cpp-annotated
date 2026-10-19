---
title: 元组
summary: std::tuple 与 tuple-like 协议：用户类型可以加入的 tuple_size/tuple_element/get 协议和只认标准类型的 tuple-like 概念，构造函数的约束与消歧义，分配器构造，tie、forward_as_tuple、tuple_cat、apply、make_from_tuple，以及比较和 common_reference 特化。
status: done
covers: *
papers: P2165R4, P2321R2, P2255R2, P2819R2, P2968R2
related: pairs, utility, dcl.struct.bind, func.require, allocator.uses.construction, class.spaceship, expos.only.entity, meta.trans.other, depr.tuple, range.zip, utilities
tags: 标准库, tuple, 结构化绑定, 元编程, 条件 explicit
updated: 2026-10-19
---

!!! tldr
    - 结构化绑定认的是开放的协议：任何类型特化 `tuple_size`、`tuple_element` 并提供 `get`，就能 `auto [a, b] = x;`。
    - `apply`、`tuple_cat`、`make_from_tuple` 和 `tuple` 的转换构造函数认的是封闭的 *tuple-like* 概念，只接受 `array`、`complex`、`pair`、`tuple`、`ranges::subrange`。
    - 贪婪的转发构造函数 `tuple(UTypes&&...)` 带有消歧义约束，防止它抢走单元素 `tuple` 的复制和分配器标签构造；libc++ 23 没有实现后一条。
    - `forward_as_tuple` 的结果存进具名变量后，其中的临时量引用会悬垂；`make_from_tuple<T&>` 制造悬垂引用的情形被 *Mandates* 拦下。
    - `get` 的常量性是浅的：`const tuple<int&>` 的元素仍是 `int&`；右值 `tuple` 里的左值引用元素仍是左值。

[tuple.general] ¶1 `std::tuple<Types...>` 是任意个元素的异构、定长值集合，两个元素的 `tuple` 表现得和同样两个类型的 `pair` 相似。和 `pair` 共同的设计（条件 `explicit`、透过引用赋值、`const` 赋值、禁止悬垂引用成员）在 [[pairs]] 中讲过，这里侧重 `tuple` 特有的部分。

库条文的几个标签：*Constraints* 不满足时，函数不参与重载决议；*Mandates* 不满足时，程序非良构；*Preconditions* 不满足时，行为未定义（[[structure.specifications]]）。

## 两个 tuple-like：开放的协议与封闭的概念

<div class="compare" markdown="1">

```cpp ok
#include <tuple>
#include <cstddef>
using std::size_t;
struct Vec2 { double x, y; };
template<> struct std::tuple_size<Vec2>
  : std::integral_constant<size_t, 2> {};
template<size_t I>
struct std::tuple_element<I, Vec2>
  { using type = double; };
template<size_t I>
double get(const Vec2& v)
  { return I == 0 ? v.x : v.y; }

double f(Vec2 v) {
  auto [a, b] = v;   // OK
  return a + b;
}
```

```cpp error
#include <tuple>
#include <cstddef>
using std::size_t;
struct Vec2 { double x, y; };
template<> struct std::tuple_size<Vec2>
  : std::integral_constant<size_t, 2> {};
template<size_t I>
struct std::tuple_element<I, Vec2>
  { using type = double; };
template<size_t I>
double get(const Vec2& v)
  { return I == 0 ? v.x : v.y; }

double f(Vec2 v) {
  auto add = [](double a, double b)
    { return a + b; };
  return std::apply(add, v);  // error
}
```

</div>

同一个 `Vec2`，结构化绑定可以用，`std::apply` 却不行。标准里有两个都叫 tuple-like 的东西。

**tuple 协议**（[[g:tuple-protocol|tuple protocol]]）是开放的：特化 `tuple_size` 和 `tuple_element`，再提供成员 `get<I>()` 或能经 ADL 找到的 `get<I>(x)`。结构化绑定（[[dcl.struct.bind]]）用的就是它：只要 `std::tuple_size<E>` 是完整类型并且有名为 `value` 的成员，就按协议绑定。为程序定义的类型特化 `std::tuple_size` 是 [[namespace.std]] 允许的。

!!! std "[tuple.like]/1"
    A type `T` models and satisfies the exposition-only concept *tuple-like* if `remove_cvref_t<T>` is a specialization of `array`, `complex`, `pair`, `tuple`, or `ranges::subrange`.

概念 ***tuple-like*** 是封闭的清单，只有这五个标准模板的特化满足它；*pair-like* 是其中大小为 2 的那些。`tuple` 的转换构造、赋值和比较，`tuple_cat`、`apply`、`make_from_tuple`、`pair(P&&)`，都受这个概念约束。

为什么不让库函数接受任何实现了协议的类型？库函数要调用 `get<I>(std::forward<T>(t))` 并依赖它的语义：返回第 `I` 个元素的引用，值类别跟随 `t`。对用户类型无法保证这一点。所以 C++23 引入这个概念时（[[P2165R4]]），只对标准自己的类型作承诺。`complex` 是 C++26 加入清单的（[[P2819R2]]），从此 `auto [re, im] = z;` 合法。

### tuple_size 和 tuple_element（[tuple.helper]）

`<tuple>` 概要中 `tuple_size` 和 `tuple_element` 的主模板只声明、不定义。对不参与协议的类型，`tuple_size<T>` 是不完整类型，结构化绑定正是据此决定走协议绑定还是按数据成员绑定。

¶1–¶3 `tuple_size<tuple<Types...>>` 是 `integral_constant<size_t, sizeof...(Types)>`；`tuple_element<I, tuple<Types...>>::type` 是第 `I` 个类型，要求 `I < sizeof...(Types)`。

!!! std "[tuple.helper]/4"
    If the expression `TS::value` is well-formed when treated as an unevaluated operand, then each specialization of the template meets the *Cpp17UnaryTypeTrait* requirements with a base characteristic of `integral_constant<size_t, TS::value>`. Otherwise, it has no member `value`.

¶4 `tuple_size<const T>` 只在 `tuple_size<T>::value` 有效时才有 `value`；否则它是一个完整、但没有 `value` 的类。这样写是为了下面这段普通的代码：

```cpp ok
struct S { int a, b; };
const S s{1, 2};
auto [x, y] = s;   // E 是 const S，要检查 tuple_size<const S>
```

如果偏特化无条件派生自 `integral_constant<size_t, tuple_size<T>::value>`，实例化 `tuple_size<const S>` 时就要用到不完整的 `tuple_size<S>`，这个错误发生在模板定义内部，不是 SFINAE 能挡住的，按数据成员绑定的代码就编译不过了。按现在的写法，`tuple_size<const S>` 没有 `value`，结构化绑定退回按数据成员绑定。

¶5 检查 `TS::value` 时，访问检查如同在与 `TS`、`T` 无关的上下文中进行，只看表达式的直接语境（[[g:immediate-context|immediate context]]）。注 1 提醒，直接语境之外的副作用（比如隐式实例化出错）仍可能让程序非良构。

¶7 `tuple_element<I, const T>::type` 是 `const TE`。¶6、¶8 规定这两个偏特化经 `<array>`、`<complex>`、`<ranges>`、`<utility>` 也能用，对 `const std::array` 做结构化绑定不必额外包含 `<tuple>`。`volatile` 的对应偏特化在 C++20 弃用，现在位于 [[depr.tuple]]。

## 类模板 tuple（[tuple.tuple.general]）

类定义和 `pair` 同构：一组 `constexpr explicit(see below)` 的构造函数，`= default` 的复制、移动构造函数，一组分配器扩展构造函数，普通和 `const` 两族赋值运算符，成员 `swap`。区别是 `tuple` 的元素是私有的，标准不规定布局，只能通过 `get` 访问。

¶1 程序如果声明 `tuple` 的显式特化或偏特化，就是非良构的，不要求诊断（[[g:ifndr|IFNDR]]：编译器可以不报错，但标准对这个程序不作任何要求）。一般规则允许为程序定义类型特化标准类模板，这里专门禁止了，因为 `apply` 等函数依赖 `tuple` 的标准语义。

推导指引有四个：`tuple(UTypes...)`、`tuple(pair<T1, T2>)`，以及它们的 `allocator_arg_t` 版本，都按值接收。所以 `std::tuple{1, "x"}` 推导为 `tuple<int, const char*>`，`std::tuple{std::pair{1, 'c'}}` 推导为 `tuple<int, char>`，而不是 `tuple<pair<int, char>>`。

## 构造（[tuple.cnstr]）

¶2–¶5 构造函数只在某个元素的构造抛出时才抛出。所有元素都平凡可析构时，`tuple` 的析构函数是平凡的；`tuple<>` 的默认构造函数是平凡的。和 `pair` 一样，`tuple` 的复制赋值是手写的（`tie` 需要透过引用赋值），所以 `tuple` 不是平凡可复制类型。

| 构造函数 | 段落 | 主要 *Constraints* | `explicit` 当且仅当 |
|---|---|---|---|
| `tuple()` | ¶6–¶8 | 全部可默认构造 | 某个 *Ti* 不能从 `{}` 复制列表初始化 |
| `tuple(const Types&...)` | ¶9–¶11 | 至少一个元素；全部可复制构造 | 某个 `const Ti&` 不能隐式转换为 *Ti* |
| `tuple(UTypes&&...)` | ¶12–¶15 | 至少一个元素；消歧义约束；全部可构造 | 某个 *Ui* 不能隐式转换为 *Ti* |
| `tuple(const tuple&) = default` | ¶16–¶17 | （*Mandates*：全部可复制构造） | |
| `tuple(tuple&&) = default` | ¶18–¶19 | 全部可移动构造 | |
| 从 `tuple<UTypes...>` 的四种 | ¶20–¶23 | 逐元素可构造；单元素时的额外条件 | 某元素不能隐式转换 |
| 从 `pair<U1, U2>` 的四种 | ¶24–¶27 | 恰好两个元素；逐元素可构造 | 某元素不能隐式转换 |
| `tuple(UTuple&&)`，*tuple-like* | ¶28–¶31 | 不是 `tuple` 自身或 `subrange`；大小相等；单元素时的额外条件 | 某元素不能隐式转换 |
| 分配器扩展版本 | ¶32–¶33 | 同上 | 同上 |

`explicit` 的规则和 `pair` 一样，跟随元素：

<div class="compare" markdown="1">

```cpp error
#include <tuple>
#include <vector>
std::tuple<int, std::vector<int>> f() {
  return {1, 5};  // error: explicit
}
```

```cpp ok
#include <tuple>
#include <vector>
std::tuple<int, std::vector<int>> g() {
  return {1, std::vector<int>(5)};
}
```

</div>

当前草案还给 `tuple(const Types&...)` 和 `tuple(UTypes&&...)` 规定了异常规格：所有元素的对应构造都不抛出时，它们是 `noexcept` 的。

所有从实参构造元素的构造函数，在某个引用元素会绑定到临时量时都定义为弃置（¶15、¶23、¶27、¶31，[[P2255R2]]），道理与 [[pairs]] 相同。

### 消歧义约束（¶12–¶13）

`template<class... UTypes> tuple(UTypes&&...)` 是一个贪婪的转发构造函数，不加限制的话，它会在两种场合抢走本该属于别的构造函数的调用。¶12 为此定义了 *disambiguating-constraint*，¶13 把它列为约束之一。

¶12.1 单元素 `tuple` 的复制。`tuple<X> t2(t1);` 中 `t1` 是非 `const` 左值时，转发构造函数推导出 `U0 = tuple<X>&`，是精确匹配，比需要加 `const` 的复制构造函数 `tuple(const tuple&)` 更好（[[over.ics.rank]]）。于是单元素时要求 `remove_cvref_t<U0>` 不是 `tuple` 本身。

¶12.2 分配器标签。分配器扩展构造函数中，默认构造版本有 2 个实参（标签、分配器），复制、移动和转换版本有 3 个；转发构造函数有 *N* 个。元素个数是 2 或 3 时两者可能撞上。于是此时要求第一个实参不是 `allocator_arg_t`，除非第一个元素的类型本身就是 `allocator_arg_t`。

撞上的后果不只是二义。看 `tuple<std::any, std::any> t(std::allocator_arg, alloc);`：`any` 能从任何可复制的值构造，转发构造函数可行；对 prvalue 实参 `alloc`，它的 `Alloc&&` 形参比分配器版本的 `const Alloc&` 更好（右值绑定到右值引用优先）。没有 ¶12.2，它就会胜出，把标签和分配器分别装进两个 `any`。

!!! impl "libc++ 23 没有实现 ¶12.2"
    libc++ 的转发构造函数只排除了单个实参是 `tuple` 本身的情形，没有 `allocator_arg_t` 的消歧义条件。本机运行上面的例子，两个 `any` 的 `has_value()` 都是 1，选中的是转发构造函数。按草案应选中分配器扩展的默认构造函数，两个 `any` 都为空。

### 单元素：包一层还是转换（¶21.3、¶29.5）

`tuple<tuple<int>> outer(inner);` 中 `inner` 是 `tuple<int>`，有两种读法：

- 把 `inner` 当作元素，用 `tuple(const Types&...)`，把 `inner` 复制进去；
- 把 `inner` 当作要转换的 `tuple`，用 `tuple(const tuple<UTypes...>&)`，`UTypes = int`，用 `get<0>(inner)` 这个 `int` 初始化元素 `tuple<int>`。

两者都可行，结果却不同。¶21.3 规定单元素时，如果 `u` 能整体转换或构造为元素类型 `T`，或者 `T` 与 `U` 相同，就排除转换构造函数。能整体当元素用，就当元素用。¶29.5 对 *tuple-like* 实参作了同样的规定。

```cpp run title="tuple_wrap.cpp" ok
#include <tuple>
#include <type_traits>
int main() {
  std::tuple<int> inner{1};
  std::tuple<std::tuple<int>> outer(inner);   // 包一层
  static_assert(std::is_same_v<std::tuple_element_t<0, decltype(outer)>,
                               std::tuple<int>>);
  return std::get<0>(std::get<0>(outer)) - 1;
}
```

### 分配器扩展构造函数（¶32–¶33、[tuple.traits]）

每个构造函数都有一个前面加 `allocator_arg_t, const Alloc&` 的版本。¶32 要求 `Alloc` 满足 *Cpp17Allocator*。¶33 规定效果与对应的构造函数相同，只是每个非引用类型的元素用**使用分配器构造**（uses-allocator construction，[[allocator.uses.construction]]）创建：元素类型使用这个分配器（`uses_allocator_v<Ti, Alloc>` 为真）时，就把分配器传给它的构造函数，否则忽略分配器。复制和移动版本 `tuple(allocator_arg_t, const Alloc&, const tuple&)` 不是 `explicit` 的。

[tuple.traits] ¶1–¶2 特化 `uses_allocator<tuple<Types...>, Alloc>` 为 `true_type`，告诉其他组件 `tuple` 可以接受分配器，尽管它没有嵌套的 `allocator_type`。于是 `std::pmr::vector<std::tuple<int, std::pmr::string>>` 会把内存资源一路传给每个元素里的 `pmr::string`：

```cpp run title="tuple_alloc.cpp" ok
#include <tuple>
#include <memory>
#include <memory_resource>
#include <string>
#include <cstdio>

int main() {
  std::pmr::monotonic_buffer_resource res;
  std::pmr::polymorphic_allocator<> alloc(&res);
  // pmr::string 拿到 alloc，int 忽略它
  std::tuple<int, std::pmr::string> t(std::allocator_arg, alloc, 1,
                                      "a fairly long string, no SSO here");
  std::printf("%d\n", std::get<1>(t).get_allocator().resource() == &res);   // 1
}
```

## 赋值与交换（[tuple.assign]、[tuple.swap]、[tuple.special]）

[tuple.assign] 和 `pair` 完全平行。复制赋值（¶2–¶4）定义为弃置，除非所有元素可复制赋值；移动赋值（¶8–¶11）的异常规格是所有元素 `is_nothrow_move_assignable_v` 的合取。此外还有从 `tuple<UTypes...>`（¶15–¶26）、`pair<U1, U2>`（¶27–¶38，要求恰好两个元素）和 *tuple-like*（¶39–¶44，排除自身和 `subrange`）的赋值。

每一种都有 `const` 版本，约束写成 `is_assignable_v<const Ti&, ...>`，服务于 `ranges::zip` 的代理引用（[[P2321R2]]，详见 [[pairs]]）：

```cpp run title="tuple_const_assign.cpp" ok
#include <tuple>
#include <string>

void assign_through(const std::tuple<int&, std::string&>& proxy) {
  proxy = std::tuple{42, std::string("hi")};   // 赋给被引用的对象
}

int main() {
  int i = 0; std::string s;
  assign_through(std::tie(i, s));
  return (i == 42 && s == "hi") ? 0 : 1;
}
```

[tuple.swap] 成员 `swap` 的可交换要求是 *Mandates*（¶2）。¶4 对每个元素调用 `swap`，按 [[swappable.requirements]] 的约定，这是 `using std::swap; swap(a, b);` 式的调用，能找到用户通过 ADL 提供的 `swap`。[tuple.special] 的非成员 `swap` 则是 *Constraints*（¶1），异常规格是 `noexcept(x.swap(y))`。分工与 `pair` 相同：非成员版本供 `is_swappable` 检测，必须在不可交换时退出重载决议。

## 创建函数（[tuple.creation]）

| 函数 | 结果类型 | 用途 |
|---|---|---|
| `make_tuple(ts...)` | `tuple<unwrap_ref_decay_t<Ts>...>` | 按值打包；`std::ref`、`std::cref` 展开为引用 |
| `forward_as_tuple(ts...)` | `tuple<Ts&&...>` | 打包成引用，用于转发 |
| `tie(ts...)` | `tuple<Ts&...>` | 打包成左值引用，用于给多个变量赋值 |
| `tuple_cat(tpls...)` | `tuple<CTypes...>` | 拼接任意多个 *tuple-like* |

¶1–¶2 `make_tuple(1, ref(i), cref(j))` 的类型是 `tuple<int, int&, const float&>`（`j` 是 `float`）。有了 CTAD 之后，它的独特用处是展开 `reference_wrapper`，这一点和 `make_pair` 一样。

### forward_as_tuple 的结果不能存下来（¶3–¶4）

```cpp run title="forward_as_tuple_dangling.cpp" ub
#include <tuple>
#include <string>
#include <cstdio>

int main() {
  auto t = std::forward_as_tuple(std::string(40, 'x'));   // tuple<string&&>
  // 临时 string 在上一行的完整表达式结束时已经销毁
  std::printf("%zu\n", std::get<0>(t).size());            // UB: 悬垂引用
}
```

本机直接运行碰巧打印 `40`；加上 `-fsanitize=address`，ASan 报告 `stack-use-after-scope`。

¶3 说明，结果中可能含有对临时对象的引用，程序必须保证返回值的生存期不超过任何实参。正确的用法是把结果立即作为函数实参，在同一个完整表达式里用掉，那时临时量还活着：`pair` 的分段构造、`map::emplace`、`apply` 都是这样用的。

### tie 与 ignore（¶5–¶6）

`std::tie(i, std::ignore, s) = std::make_tuple(42, 3.14, "C++");` 是 C++17 之前解包的写法。结构化绑定出现后它仍有两个用处：给已有的变量赋值（结构化绑定只能引入新名字），以及用 `std::tie(a.x, a.y) < std::tie(b.x, b.y)` 写字典序比较（C++20 起可以改用预置的 `<=>`）。

`std::ignore` 可以接受任何值的赋值，什么也不做。C++26 起它的类型是说明专用的 `ignore-type`，只有一个接受任意实参的 `const` 赋值运算符（[[P2968R2]]）；以前它的类型未指定，只保证能在 `tie` 里用。现在 `std::ignore = f();` 可以用来明确丢弃一个 `[[nodiscard]]` 返回值。[tuple.general] ¶2 规定包含 `<utility>` 也能用 `ignore`。

### tuple_cat（¶7–¶9）

¶7 用一组记号精确定义了结果：把每个实参去掉 cv 和引用后的类型记作 *Ui*，把所有实参的元素类型 `tuple_element_t<k, Ui>` 依次拼起来得到 `CTypes`，把对应的表达式 `get<k>(std::forward<Ti>(tpi))` 拼起来得到 `celems`。¶8–¶9 要求每个元素能从对应表达式构造，返回 `tuple<CTypes...>(celems...)`。

所以实参可以是任意 *tuple-like*，混合 `pair`、`array`、`tuple`；元素类型原样保留，引用元素仍是引用；实参是右值时，元素被移动出来。

```cpp run title="tuple_cat.cpp" ok
#include <tuple>
#include <utility>
#include <array>
#include <type_traits>
int main() {
  auto cat = std::tuple_cat(std::pair{1, 'a'}, std::array<double, 2>{2.5, 3.5},
                            std::tuple<>{});
  static_assert(std::is_same_v<decltype(cat), std::tuple<int, char, double, double>>);
  static_assert(std::tuple{1, 2} == std::pair{1, 2});   // 与 pair-like 比较
}
```

## apply 与 make_from_tuple（[tuple.apply]）

¶1 `apply(f, t)` 等价于 `INVOKE(std::forward<F>(f), get<I>(std::forward<Tuple>(t))...)`，`I` 取遍 0 到 `tuple_size_v - 1`。用 *INVOKE*（[[func.require]]）意味着 `f` 可以是成员函数指针，第一个元素充当对象。当前草案中它的返回类型是 `apply_result_t<F, Tuple>`，异常规格是 `noexcept(is_nothrow_applicable_v<F, Tuple>)`，这两个特征是 C++26 新增的（[[meta.trans.other]]）。显式的返回类型让 `apply` 在不可调用时能被 SFINAE 检测到。

!!! impl "libc++ 23 的 apply"
    libc++ 23 的 `apply` 仍是旧形式：返回类型是 `decltype(auto)`，形参也没有用 *tuple-like* 约束，对非 tuple-like 类型会在内部查找 `get` 时报错。头文件里也还没有 `is_applicable`、`is_nothrow_applicable`。对 *tuple-like* 类型的正常使用，两者行为一致。

¶3 `make_from_tuple<T>(t)` 等价于 `T(get<I>(std::forward<Tuple>(t))...)`，内部的说明函数带有 `requires is_constructible_v<T, ...>`。注 1 指出 `T` 无法推导，必须显式给出。它用的是圆括号 `T(...)`：C++20 起圆括号也能对聚合类型做聚合初始化（[[dcl.init]]）。

```cpp run title="apply.cpp" ok
#include <tuple>
#include <array>
#include <string>
#include <cstdio>
int main() {
  auto sum = std::apply([](auto... xs) { return (xs + ...); }, std::array{1, 2, 3});
  auto str = std::make_from_tuple<std::string>(std::tuple{3, 'z'});  // string(3, 'z')
  std::printf("%d %s\n", sum, str.c_str());                          // 6 zzz
}
```

### make_from_tuple 的悬垂检查（¶2）

```cpp run title="make_from_tuple_dangling.cpp" error
#include <tuple>
#include <string>
int main() {
  // T = const string&，唯一的元素是 const char*
  auto&& r = std::make_from_tuple<const std::string&>(std::tuple<const char*>{"x"});
}
```

只有一个元素、`T` 又是引用类型时，`T(get<0>(...))` 是一个函数式转型，等价于 `(const std::string&)ptr`：先构造一个临时 `string`，引用绑定到它，再从函数返回，返回的引用立即悬垂。¶2 的 *Mandates* 规定此时 `reference_constructs_from_temporary_v<T, decltype(get<0>(declval<Tuple>()))>` 必须为假。只检查单元素的情形，是因为只有一个实参时 `T(x)` 才是转型；多个实参时，`T` 为引用类型的 `T(a, b)` 本来就非良构。

!!! impl
    libc++ 用 `static_assert` 实现这条 *Mandates*，Clang 报告 `Attempted construction of reference element binds to a temporary whose lifetime has ended`。libc++ 还在外层加了约束，让 `make_from_tuple` 本身在不可构造时退出重载决议，注释中引用了 [[LWG3528]]。

## 元素访问：get（[tuple.elem]）

¶1–¶2 按下标的 `get<I>` 有 `&`、`&&`、`const&`、`const&&` 四个重载，要求 `I < sizeof...(Types)`，返回第 `I` 个元素的引用。两条注说明了引用元素的行为：

```cpp ok
#include <tuple>
#include <type_traits>
#include <utility>
void f(int i) {
  std::tuple<int&> t{i};
  const std::tuple<int&> ct{i};
  static_assert(std::is_same_v<decltype(std::get<0>(std::move(t))), int&>);  // 不是 int&&
  static_assert(std::is_same_v<decltype(std::get<0>(ct)), int&>);            // 不是 const int&
}
```

¶3 注 1：元素类型是 `X&` 时，`&&` 重载的返回类型 `tuple_element_t<I, ...>&&` 经引用折叠成 `X&`。右值 `tuple` 里的左值引用元素仍是左值，`forward_as_tuple` 能正确转发左值实参，靠的就是这一点。

¶4 注 2：常量性是浅的。元素类型是 `X&` 时，`const&` 重载返回 `X&`。这和核心语言一致：`const` 对象的引用成员并不因此变成对 `const` 的引用。

¶5–¶7 按类型的 `get<T>` 要求 `T` 在 `Types` 中恰好出现一次。¶7 的例子中，`tuple<int, const int, double, double>` 的 `get<int>` 和 `get<const int>` 都合法（`int` 和 `const int` 是不同类型），`get<double>` 非良构。

¶8 注 3 解释了 `get` 为什么是非成员函数：如果是成员模板，在依赖类型的上下文中就必须写 `t.template get<0>()`（[[temp.names]]）。

## 比较（[tuple.rel]）

¶1–¶3 `operator==` 有两个重载：`tuple` 与 `tuple`，`tuple` 与任意 *tuple-like*（C++23）。约束要求两者大小相等，每对 `get<i>(t) == get<i>(u)` 有效，且结果满足 *boolean-testable*（能像 `bool` 一样用在 `&&`、`!` 中，见 [[concept.booleantestable]]）。空 `tuple` 相等。

¶4.1 从下标 0 起依次比较，遇到第一个不相等之后，不再比较也不再访问任何元素，短路是规范性要求。¶4.2 第二个重载只能经 ADL 找到，效果类似[[g:hidden-friend|隐藏友元]]：只有某个操作数是 `tuple` 时才会被考虑，不会干扰其他 tuple-like 类型之间的比较。借助 C++20 的重写候选，`pair == tuple` 被反转成 `tuple == pair`，一个重载覆盖两个方向。

¶5–¶7 `operator<=>` 的返回类型是各元素 *synth-three-way-result* 的公共比较类别。¶6 规定字典序比较：比较首元素，不相等就返回，否则比较其余部分。*synth-three-way* 的作用同 [[pairs]]：元素只有 `<` 和 `==` 时，用它们合成一个 `weak_ordering`。¶8 注 2 说明，定义里的其余部分 `ttail` 只是描述递归的记法，不需要真的构造出来（元素不一定能复制）。

`<`、`>`、`<=`、`>=`、`!=` 都由重写候选得到（[[over.match.oper]]）。

## common_reference 与 common_type 特化（[tuple.common.ref]）

¶1–¶3 `basic_common_reference<TTuple, UTuple, TQual, UQual>::type` 是 `tuple<common_reference_t<TQual<TTypes>, UQual<UTypes>>...>`。¶4–¶5 `common_type<TTuple, UTuple>::type` 是 `tuple<common_type_t<TTypes, UTypes>...>`。¶2、¶4 的约束是：至少一方是 `tuple` 的特化（两个 `pair` 时由 `pair` 自己的特化处理），两者都已 decay，大小相等，结果类型有效。

它们是为 `ranges::zip_view`（[[range.zip]]）准备的。`zip` 迭代器的引用类型是 `tuple<int&, string&>`，值类型是 `tuple<int, string>`，`indirectly_readable` 要求两者有公共引用类型（[[iterator.concept.readable]]）。`TQual`、`UQual` 把外层 `tuple` 的 cv 和引用限定分发到每个元素上：

```cpp run title="tuple_common_ref.cpp" ok
#include <tuple>
#include <type_traits>
using std::tuple, std::common_reference_t, std::is_same_v;
static_assert(is_same_v<common_reference_t<tuple<int&>&, tuple<int>&>, tuple<int&>>);
static_assert(is_same_v<common_reference_t<tuple<int&>, tuple<int>&>, tuple<int&>>);
static_assert(is_same_v<common_reference_t<tuple<int&>, tuple<int>>, tuple<int>>);
static_assert(is_same_v<std::common_type_t<tuple<int, long>, tuple<long, int>>,
                        tuple<long, long>>);
int main() {}
```

!!! impl "libc++ 23 只特化了 tuple 与 tuple"
    草案的特化接受一方是 `tuple`、另一方是任意 *tuple-like*（[[P2165R4]]）。libc++ 23 只对两个 `tuple` 特化，`std::common_reference_t<std::tuple<int&>, std::pair<int, int>>` 在本机无法形成。这与 `<version>` 中 `__cpp_lib_tuple_like` 仍被注释掉一致。

## 实现：tuple 在内存里的布局

标准对 `tuple` 的布局没有任何规定，各实现差别很大。

- libc++ 的 `tuple` 持有一个 `__tuple_impl`，它按顺序继承 `__tuple_leaf<0, T0>`、`__tuple_leaf<1, T1>`……每个叶子要么持有一个 `T` 成员，要么在 `T` 是非 `final` 的空类时继承 `T`，以利用空基类优化。本机测得 `tuple<char, int, double>` 三个元素的偏移是 0、4、8。
- libstdc++ 递归继承 `_Tuple_impl<I, Head, Tail...>`，基类 `_Tuple_impl<I+1, Tail...>` 在前、`Head` 在后，元素在内存中是逆序排列的。

需要确定布局时用 `struct`。空基类优化也有限度：本机 `sizeof(std::tuple<int, Empty>)` 是 4，`Empty` 不占空间；`sizeof(std::tuple<Empty, Empty>)` 却是 2，因为两个同类型的空子对象必须有不同的地址（[[intro.object]]）。

<details class="fine" markdown="1"><summary>其余条文</summary>

[tuple.syn] `<tuple>` 整个头文件是 freestanding 的，并包含 `<compare>`。*pair-like* 定义为 `tuple-like<T> && tuple_size_v<remove_cvref_t<T>> == 2`。

[tuple.cnstr] ¶1 定义记号：*Ti* 是 `Types` 中第 *i* 个类型，*Ui* 是 `UTypes` 中第 *i* 个类型，下标从 0 开始。¶3 预置的复制、移动构造函数是 constexpr 函数，当且仅当逐元素初始化都满足 constexpr 适用条件；`tuple<>` 的总是 constexpr 函数。

[tuple.assign] ¶1 赋值运算符只在某个元素的赋值抛出时才抛出。[tuple.swap] ¶5 同理。

</details>

!!! history
    C++11 从 TR1 引入 `tuple`，借助变参模板实现。C++14 加入按类型的 `get<T>`。C++17 加入 `apply`、`make_from_tuple`、推导指引和条件 `explicit`，结构化绑定以 tuple 协议为基础。C++20 用 `<=>` 取代六个关系运算符，弃用 `volatile` 偏特化。C++23 引入 *tuple-like* 概念及相关的构造、赋值、比较（[[P2165R4]]），`const` 赋值和 `common_reference` 特化（[[P2321R2]]），以及禁止悬垂引用的规则（[[P2255R2]]）。C++26 把 `complex` 加入 *tuple-like*（[[P2819R2]]），给 `ignore` 规定了类型（[[P2968R2]]）。

## 常见误解

!!! pitfall "std::tuple{p} 会把 pair 包一层"
    `p` 是 `pair<int, char>` 时，`std::tuple{p}` 推导为 `tuple<int, char>`，用的是 `tuple(pair<T1, T2>)` 推导指引。要得到 `tuple<pair<int, char>>`，必须写明模板实参。

!!! pitfall "实现了协议的类型可以用于 apply"
    `apply`、`tuple_cat`、`make_from_tuple` 只接受 *tuple-like* 的五种标准类型。用户类型实现了 tuple 协议，也只能用于结构化绑定。

!!! pitfall "get<0>(std::move(t)) 会移动元素"
    对 `tuple<X&>`，`get<0>(std::move(t))` 返回 `X&`，不会移动被引用的对象。只有非引用元素才得到 `X&&`。

## 思考题

!!! question "思考题 1"
    按当前草案，下面的程序输出什么？为什么？
    ```cpp
    std::tuple<std::any, std::any> t(std::allocator_arg, std::allocator<int>{});
    std::printf("%d %d\n", std::get<0>(t).has_value(), std::get<1>(t).has_value());
    ```

<details markdown="1">
<summary>答案</summary>

应输出 `0 0`。元素个数为 2，第一个实参的类型是 `allocator_arg_t`，而 `T0` 是 `any` 不是 `allocator_arg_t`，¶12.2 的消歧义约束为假，转发构造函数不参与重载决议。剩下可行的是分配器扩展的默认构造函数 `tuple(allocator_arg_t, const Alloc&)`；`uses_allocator_v<any, allocator<int>>` 为假，两个 `any` 不带分配器地值初始化，都为空。

没有这条约束时，转发构造函数也可行，而且对 prvalue 第二实参是右值绑定到右值引用，比 `const Alloc&` 更好（[[over.ics.rank]]），它会胜出，输出 `1 1`。libc++ 23 没有实现 ¶12.2，本机实测正是 `1 1`。
</details>

!!! question "思考题 2"
    `std::tuple<int> a{1}; std::tuple<long> b(a);` 用的是哪个构造函数？`std::tuple<std::tuple<int>> c(a);` 呢？

<details markdown="1">
<summary>答案</summary>

`b(a)`：单元素，`T = long`，`U = int`。`tuple<int>` 不能转换或构造为 `long`，`T` 与 `U` 也不同，¶21.3 的额外条件成立，转换构造函数 `tuple(const tuple<UTypes...>&)` 可行，用 `get<0>(a)` 初始化元素。

`c(a)`：`T = tuple<int>`，`U = int`。`a` 能直接构造 `T`，¶21.3 排除转换构造函数，选中 `tuple(const Types&...)`，`a` 被整体复制进去成为唯一的元素。
</details>
