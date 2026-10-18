---
title: 元组
summary: std::tuple 与 tuple-like 协议——封闭的 tuple-like 概念与开放的 tuple_size/tuple_element/get 协议、结构化绑定的联动、构造函数约束矩阵与消歧义约束、分配器构造、tie/forward_as_tuple/make_tuple/tuple_cat、apply 与 make_from_tuple 的悬垂检查、common_reference 特化与 synth-three-way 比较
status: done
covers: *
papers: P2165R4, P2321R2, P2255R2, P2819R2, P2968R2
related: pairs, utility, dcl.struct.bind, func.require, allocator.uses.construction, class.spaceship, expos.only.entity, meta.trans.other, depr.tuple, range.zip, utilities
tags: 标准库, tuple, 结构化绑定, 元编程, 条件 explicit
updated: 2026-10-18
---

`std::tuple<Types...>` 是 `pair` 推广到任意个元素的结果：¶1 说它是"异构、定长的值集合"，两个元素的 `tuple` "表现得与同样两个实参的 `pair` 相似"。但 `<tuple>` 这个子条款的分量远不止一个类模板——它定义了整个标准库（以及核心语言的结构化绑定）赖以运作的 **tuple-like 协议**：`tuple_size`、`tuple_element`、`get`。`pair`、`array`、`complex`、`ranges::subrange` 都实现了这个协议；`apply`、`make_from_tuple`、`tuple_cat`、`ranges::elements_view` 都只依赖这个协议工作。

本页覆盖 [tuple] 的全部子条款。与 `pair` 共同的设计（条件 `explicit`、透过引用赋值、const 赋值、悬垂引用检查）在 [[pairs]] 里已有详细讨论，这里侧重 `tuple` 特有的部分。

| 子条款 | 内容 |
|---|---|
| [tuple.general] | 概述；`ignore` 也可经 `<utility>` 获得 |
| [tuple.syn] | `<tuple>` 概要（全部 freestanding） |
| [tuple.like] | 说明专用概念 *tuple-like* / *pair-like* |
| [tuple.tuple] | 类模板 `tuple`：[tuple.tuple.general] 定义与推导指引、[tuple.cnstr] 构造、[tuple.assign] 赋值、[tuple.swap] 交换 |
| [tuple.creation] | `make_tuple`、`forward_as_tuple`、`tie`、`tuple_cat` |
| [tuple.apply] | `apply`、`make_from_tuple` |
| [tuple.helper] | `tuple_size`、`tuple_element` |
| [tuple.elem] | `get` |
| [tuple.rel] | `==`、`<=>` |
| [tuple.common.ref] | `basic_common_reference` 与 `common_type` 特化 |
| [tuple.traits] | `uses_allocator` |
| [tuple.special] | 非成员 `swap` |

## 概述与概要（[tuple.general]、[tuple.syn]）

[tuple.general] ¶2：除了 `<tuple>`，包含 `<utility>` 也能使用 `std::ignore`。这是 C++26 把 `ignore` 变成"一等对象"（[[P2968R2]]）时加上的：概要里它的类型是说明专用的 `ignore-type`，只有一个 `constexpr const ignore-type& operator=(const auto&) const noexcept`——**可以给它赋任何值，什么也不发生**。以前 `ignore` 的类型是"未指明的"，只保证能在 `tie` 里用；现在 `std::ignore = f();` 这种"显式丢弃 `[[nodiscard]]` 返回值"的写法有了明确的保证。

`<tuple>` 概要标注 `// all freestanding`，并 `#include <compare>`。概要中值得注意的几项：

- 两个说明专用概念 *tuple-like* 与 *pair-like*（后者是 `tuple-like<T> && tuple_size_v<remove_cvref_t<T>> == 2`）；
- `tuple_size` 与 `tuple_element` 的主模板**只声明不定义**（`// not defined`），以及针对 `const T` 的偏特化；
- `tuple_cat`、`apply`、`make_from_tuple` 的形参都受 *tuple-like* 约束；
- `apply` 的异常规格是 `noexcept(is_nothrow_applicable_v<F, Tuple>)`，返回类型 `apply_result_t<F, Tuple>`（C++26 新增的特征，见 [[meta.trans.other]]）。

## tuple-like：一个封闭的概念，一个开放的协议（[tuple.like]）

!!! std "[tuple.like]/1"
    A type `T` models and satisfies the exposition-only concept *tuple-like* if `remove_cvref_t<T>` is a specialization of `array`, `complex`, `pair`, `tuple`, or `ranges::subrange`.

    *tuple-like* 是一个**封闭的清单**：只有这五个标准模板的特化满足它。

这里有一个非常容易混淆的区分：

| | 判定方式 | 用户类型能否加入 | 谁在使用 |
|---|---|---|---|
| [[g:tuple-protocol]] | 特化 `tuple_size`、`tuple_element`，提供 `get<I>` | 能 | 结构化绑定（[[dcl.struct.bind]]） |
| [[g:tuple-like]] | 固定清单（`array`、`complex`、`pair`、`tuple`、`subrange`） | 不能 | `tuple` 的转换构造/赋值/比较、`tuple_cat`、`apply`、`make_from_tuple`、`pair(P&&)` |

C++23 的 [[P2165R4]] 引入这个概念时，有意不把它做成"任何实现了协议的类型"：库函数要对元素调用 `get<I>(std::forward<T>(t))` 并假设它的语义（返回第 `I` 个元素的引用、值类别随 `t`），对用户类型无法保证；而且"检测 `tuple_size<T>` 是否完整"这件事本身就容易引发 ODR 问题。所以库只承诺对自己的类型工作。`complex` 是 C++26 才加入清单的（[[P2819R2]]）：`auto [re, im] = z;` 自此合法。

结构化绑定则走另一条路——核心语言的规则（[[dcl.struct.bind]]）：如果 `std::tuple_size<E>` 是一个**完整类型**且有名为 `value` 的成员，就按 tuple-like 协议绑定，对每个 `i` 调用成员 `e.get<i>()` 或（经 ADL 找到的）`get<i>(e)`。用户类型可以实现这个协议：

```cpp run title="user_tuple_protocol.cpp" ok
#include <tuple>
#include <cstddef>
#include <utility>

struct Vec2 { double x, y; };
template<> struct std::tuple_size<Vec2> : std::integral_constant<std::size_t, 2> {};
template<std::size_t I> struct std::tuple_element<I, Vec2> { using type = double; };
template<std::size_t I> constexpr double get(const Vec2& v) { return I == 0 ? v.x : v.y; }

int main() {
  constexpr Vec2 v{1.5, 2.5};
  auto [a, b] = v;                  // OK：结构化绑定只看协议（[dcl.struct.bind]）
  static_assert(std::tuple_size_v<const Vec2> == 2);   // const T 的偏特化转发
  return static_cast<int>(a + b) - 4;
}
```

但 `std::apply(f, v)`、`std::tuple_cat(v)`、`std::tuple<double, double> t(v)` 对 `Vec2` 都不可用——`Vec2` 不满足 *tuple-like* 概念。（为用户类型特化 `std::tuple_size` 是 [[namespace.std]] 明确允许的：特化依赖于程序定义类型的标准类模板。）

## 类模板 `tuple`（[tuple.tuple.general]）

类定义的结构与 `pair` 同构：一组 `constexpr explicit(see below)` 的构造函数、`tuple(const tuple&) = default;` 与 `tuple(tuple&&) = default;`、一组分配器扩展构造函数、两族赋值运算符（普通与 const）、成员 `swap`。区别是 `tuple` 的成员是私有的——标准不规定其布局，只能通过 `get` 访问。

推导指引有四个：`tuple(UTypes...)`、`tuple(pair<T1, T2>)`，以及它们的 `allocator_arg_t` 版本。都是**按值**接收，所以 `std::tuple{1, "x"}` 推导为 `tuple<int, const char*>`，`std::tuple{std::pair{1, 'c'}}` 推导为 `tuple<int, char>`（而**不是** `tuple<pair<int, char>>`——这是一个常被问到的 CTAD 陷阱）。

¶1：程序如果声明 `tuple` 的显式特化或偏特化，**非良构，不要求诊断**（[[g:ifndr]]）。一般规则（[[namespace.std]]）允许对依赖程序定义类型的标准类模板做特化，这里专门禁止了——`tuple` 的语义完全由标准规定，用户特化毫无意义且会破坏 `apply` 等函数的假设。

## 构造（[tuple.cnstr]）

### 全局性质（¶1–¶5）

- ¶2：构造函数只在某个元素的构造抛出时才抛出。
- ¶3：预置的复制/移动构造函数是 constexpr 的，当且仅当逐元素初始化都满足 constexpr 适用条件；`tuple<>` 的则总是 constexpr。
- ¶4：所有 `Ti` 都平凡可析构时，`tuple` 的析构函数平凡。
- ¶5：`tuple<>` 的默认构造函数平凡。

和 `pair` 一样，`tuple` 的复制赋值不是预置的（要支持 `tie` 的透过引用赋值），所以 `tuple` **不是**平凡可复制类型。

### 约束矩阵

下表省略了"`sizeof...(Types) == sizeof...(UTypes)`"之类的显然条件；*Ti* 是第 *i* 个元素类型，*FWD*(u) 是 `static_cast<decltype(u)>(u)`。

| 构造函数 | 段落 | 关键 *Constraints* | `explicit` 当且仅当 |
|---|---|---|---|
| `tuple()` | ¶6–¶8 | 全部可默认构造 | 某个 *Ti* 不能从 `{}` 复制列表初始化 |
| `tuple(const Types&...)` | ¶9–¶11 | 至少 1 个元素；全部可复制构造 | 某个 `const Ti&` 不可隐式转换为 *Ti* |
| `tuple(UTypes&&...)` | ¶12–¶15 | 至少 1 个元素；消歧义约束；全部可构造 | 某个 *Ui* 不可隐式转换为 *Ti* |
| `tuple(const tuple&) = default` | ¶16–¶17 | （*Mandates*：全部可复制构造） | — |
| `tuple(tuple&&) = default` | ¶18–¶19 | 全部可移动构造 | — |
| `tuple(tuple<UTypes...>` 四种 cv/引用`)` | ¶20–¶23 | 全部可从 `get<i>(FWD(u))` 构造；单元素时的防劫持条件 | 某元素不可隐式转换 |
| `tuple(pair<U1, U2>` 四种`)` | ¶24–¶27 | 恰好 2 个元素；逐元素可构造 | 某元素不可隐式转换 |
| `tuple(UTuple&&)`，*tuple-like* | ¶28–¶31 | 不是 `tuple` 自身、不是 `subrange`；大小相等；单元素防劫持 | 某元素不可隐式转换 |
| 分配器扩展版本 | ¶32–¶33 | 同上 | 同上 |

所有"从实参构造元素"的构造函数，在任一元素是引用且会绑定到临时量时**定义为弃置**（¶15、¶23、¶27、¶31，[[P2255R2]]），原理同 [[pairs]]。

### 消歧义约束：两种"劫持"（¶12）

`template<class... UTypes> tuple(UTypes&&...)` 是一个贪婪的转发构造函数，若不加限制，会在两种场合"劫持"本该由其他构造函数处理的调用：

1. **单元素 tuple 的复制**（¶12.1）：对 `tuple<X> t2(t1);`（`t1` 是非 const 左值 `tuple<X>`），`UTypes = tuple<X>&` 推导出的转发构造函数是**精确匹配**，比要求加 const 的复制构造函数 `tuple(const tuple&)` 更好（[[over.ics.rank]]）。于是要求 `remove_cvref_t<U0>` 不是 `tuple` 本身，把这种情况让给复制/移动构造。
2. **分配器标签**（¶12.2）：对 2 或 3 个元素的 `tuple`，`tuple(allocator_arg, alloc)` 或 `tuple(allocator_arg, alloc, other)` 在实参个数上可能刚好与转发构造函数匹配。于是要求：第一个实参不是 `allocator_arg_t`，**除非**第一个元素类型本身就是 `allocator_arg_t`。为什么只看 2 或 3 个元素？分配器扩展构造函数中，默认构造版本有 2 个实参，复制/移动/转换版本有 3 个（标签、分配器、源对象），逐元素版本有 2 + *N* 个；转发构造函数恰有 *N* 个实参。只有 *N* 为 2 或 3 时两者才可能"撞车"。

撞车的后果不只是歧义：对 `tuple<std::any, std::any> t(std::allocator_arg, alloc);`，若没有 ¶12.2，转发构造函数可行（`any` 能从任何可复制的东西构造），而且对 prvalue 实参 `alloc`，它的 `Alloc&&` 形参比分配器版本的 `const Alloc&` 更好（[[over.ics.rank]]：右值绑定到右值引用优先），于是**静默地**把标签和分配器塞进了两个 `any` 里。

!!! impl "libc++ 23 没有实现 ¶12.2"
    libc++ 的转发构造函数约束（`<tuple>` 中的 `_EnableUTypesCtor`）只排除了"单个实参是 `tuple` 本身"的情形，没有 `allocator_arg_t` 的消歧义条件。本机实测上面的 `tuple<std::any, std::any>` 例子中两个 `any` 都 `has_value()`——选中的是转发构造函数，与草案不符（按草案应选中分配器扩展的默认构造函数，两个 `any` 都为空）。见思考题 2。

### 单元素时的"包一层还是转换"（¶21.3、¶29.5）

`tuple<tuple<int>> outer(inner);` 中 `inner` 是 `tuple<int>`。两种解读：

- 把 `inner` **作为元素**：用 `tuple(const Types&...)`，`T0 = tuple<int>`，复制 `inner` 进去；
- 把 `inner` **当作要转换的 tuple**：用 `tuple(const tuple<UTypes...>&)`，`UTypes = int`，把 `get<0>(inner)`（一个 `int`）转换为 `tuple<int>`。

两者都可行而结果不同。¶21.3 规定：单元素时，若 `decltype(u)` 可转换或可构造为 `T`、或 `T` 与 `U` 相同，则**排除转换构造函数**——也就是"能整体当元素用，就当元素用"：

```cpp run title="tuple_misc.cpp" ok
#include <tuple>
#include <utility>
#include <array>
#include <string>
#include <type_traits>
#include <cstdio>

int main() {
  // 单元素 tuple：从 tuple<int> 构造 tuple<tuple<int>>，是"包一层"还是"转换"？
  std::tuple<int> inner{1};
  std::tuple<std::tuple<int>> outer(inner);       // 包一层：¶21.3 排除了转换构造
  static_assert(std::is_same_v<std::tuple_element_t<0, decltype(outer)>, std::tuple<int>>);

  // tie + ignore
  int i; std::string s;
  std::tie(i, std::ignore, s) = std::make_tuple(42, 3.14, "C++");

  // tuple_cat 接受任意 tuple-like
  auto cat = std::tuple_cat(std::pair{1, 'a'}, std::array<double, 2>{2.5, 3.5}, std::tuple<>{});
  static_assert(std::is_same_v<decltype(cat), std::tuple<int, char, double, double>>);

  // tuple 与 pair 比较（C++23）
  static_assert(std::tuple{1, 2} == std::pair{1, 2});

  // apply：把 tuple-like 展开成实参
  auto sum = std::apply([](auto... xs) { return (xs + ...); }, std::array{1, 2, 3});

  // make_from_tuple
  auto str = std::make_from_tuple<std::string>(std::tuple{3, 'z'});   // string(3, 'z')

  std::printf("%d %s %d %s\n", i, s.c_str(), sum, str.c_str());       // 42 C++ 6 zzz
}
```

### 条件 explicit 的实际效果

与 `pair` 一样，`tuple` 是否能被隐式构造，跟随其元素：

```cpp run title="tuple_explicit.cpp" error
#include <tuple>
#include <vector>
std::tuple<int, std::vector<int>> f() { return {1, 5}; }     // error: vector(size_type) 是 explicit
std::tuple<int, std::vector<int>> g() { return {1, std::vector<int>(5)}; }   // OK
```

### 分配器扩展构造函数（¶32–¶33）

每个构造函数都有一个前置 `allocator_arg_t, const Alloc&` 的版本。¶32 前置条件：`Alloc` 满足 *Cpp17Allocator*。¶33：效果与对应构造函数相同，只是每个**非引用类型**的元素用**使用分配器构造**（*uses-allocator construction*，[[allocator.uses.construction]]）创建（[[g:uses-allocator-construction]]）——如果元素类型"使用"这个分配器（`uses_allocator_v<Ti, Alloc>`），就把分配器传给它（通过 `allocator_arg_t` 前缀约定或尾随分配器约定）；否则忽略分配器。

[tuple.traits] ¶1–¶2 的 `uses_allocator<tuple<Types...>, Alloc> : true_type` 让其他组件知道 `tuple` 可以接受分配器——尽管它没有嵌套的 `allocator_type`。于是 `std::pmr::vector<std::tuple<int, std::pmr::string>>` 会把自己的内存资源一路传递给每个元素中的 `pmr::string`：

```cpp run title="tuple_alloc.cpp" ok
#include <tuple>
#include <memory>
#include <memory_resource>
#include <string>
#include <cstdio>

int main() {
  std::pmr::monotonic_buffer_resource res;
  std::pmr::polymorphic_allocator<> alloc(&res);
  // 对每个非引用元素做 uses-allocator 构造：pmr::string 拿到 alloc，int 则忽略它
  std::tuple<int, std::pmr::string> t(std::allocator_arg, alloc, 1, "a fairly long string, no SSO here");
  std::printf("%d\n", std::get<1>(t).get_allocator().resource() == &res);   // 1
  static_assert(std::uses_allocator_v<std::tuple<int>, std::allocator<int>>);
}
```

注意 `tuple(allocator_arg_t, const Alloc&, const tuple&)` 与 `(…, tuple&&)` 不是 `explicit(see below)`——复制与移动永远是隐式的。

## 赋值与交换（[tuple.assign]、[tuple.swap]、[tuple.special]）

[tuple.assign] 的结构与 `pair` 完全平行：

- ¶2–¶4 复制赋值：弃置除非全部 `is_copy_assignable_v<Ti>`；¶8–¶11 移动赋值：*Constraints* 全部可移动赋值，异常规格为全部 `is_nothrow_move_assignable_v<Ti>` 的合取；
- 从 `tuple<UTypes...>`（¶15–¶26）、`pair<U1, U2>`（¶27–¶38，要求恰好 2 个元素）、*tuple-like* `UTuple`（¶39–¶44，排除自身与 `subrange`）赋值；
- 每一种都有 `const` 版本，约束写成 `is_assignable_v<const Ti&, ...>`，服务于 `zip` 的代理引用（[[P2321R2]]，详见 [[pairs]]）。

```cpp run title="tuple_const_assign.cpp" ok
#include <tuple>
#include <string>
#include <utility>
#include <type_traits>

static_assert(std::is_trivially_destructible_v<std::tuple<int, double*>>);
static_assert(!std::is_trivially_destructible_v<std::tuple<int, std::string>>);
static_assert(std::is_trivially_default_constructible_v<std::tuple<>>);

// CTAD
std::tuple t1{1, 2.0, "x"};
static_assert(std::is_same_v<decltype(t1), std::tuple<int, double, const char*>>);
std::tuple t2{std::pair{1, 'c'}};
static_assert(std::is_same_v<decltype(t2), std::tuple<int, char>>);

// const 赋值：代理引用（ranges::zip 的需要）
void assign_through(const std::tuple<int&, std::string&>& proxy) {
  proxy = std::tuple{42, std::string("hi")};   // 赋给被引用的对象，而非 tuple 本身
}

int main() {
  int i = 0; std::string s;
  assign_through(std::tie(i, s));
  return (i == 42 && s == "hi") ? 0 : 1;
}
```

[tuple.swap]：成员 `swap` 的约束是 *Mandates*（¶2），¶3 前置条件逐元素可交换，¶4 "对每个 `i` 调用 `swap`"——这里的 `swap` 按 [[swappable.requirements]] 的约定是两步法调用，会找到用户的 ADL `swap`。[tuple.special] 的非成员 `swap` 则是 *Constraints*（¶1），异常规格 `noexcept(x.swap(y))`。分工与 `pair` 相同：非成员版本要供 `is_swappable` 探测，必须 SFINAE 友好。

## 创建函数（[tuple.creation]）

| 函数 | 结果类型 | 用途 |
|---|---|---|
| `make_tuple(ts...)` | `tuple<unwrap_ref_decay_t<Ts>...>` | 按值打包；`std::ref`/`std::cref` 展开为引用 |
| `forward_as_tuple(ts...)` | `tuple<Ts&&...>` | 打包成引用，用于转发 |
| `tie(ts...)` | `tuple<Ts&...>` | 打包成左值引用，用于多重赋值 |
| `tuple_cat(tpls...)` | `tuple<CTypes...>` | 拼接任意多个 *tuple-like* |

### `make_tuple`（¶1–¶2）

¶2 的例子：`make_tuple(1, ref(i), cref(j))` 的类型是 `tuple<int, int&, const float&>`。与 `make_pair` 一样，在 CTAD 时代它的独特价值是 `reference_wrapper` 展开。

### `forward_as_tuple`：生命周期由你负责（¶3–¶4）

!!! std "[tuple.creation]/3"
    Because the result may contain references to temporary objects, a program shall ensure that the return value of this function does not outlive any of its arguments.

    结果中可能含有对临时对象的引用，程序**必须**保证返回值的生命期不超过任何实参——典型做法是**不要把结果存进具名变量**。

"程序应当（*shall*）"出现在库条文里，违反即 UB。它的正确用法是作为函数实参立即使用（`pair` 的分段构造、`map::emplace`、`apply`），在同一个完整表达式中，临时量还活着：

```cpp run title="forward_as_tuple_dangling.cpp" ub
#include <tuple>
#include <string>
#include <cstdio>

int main() {
  auto t = std::forward_as_tuple(std::string(40, 'x'));   // tuple<string&&>
  // 临时 string 在上一行的完整表达式结束时就被销毁了
  std::printf("%zu\n", std::get<0>(t).size());            // UB: 悬垂引用
}
```

本机用 `-fsanitize=address` 运行，ASan 报告 `stack-use-after-scope`。

### `tie` 与 `ignore`（¶5–¶6）

`tie(i, ignore, s) = make_tuple(42, 3.14, "C++");` 是 C++17 结构化绑定出现前"解包"的标准写法。它至今仍有结构化绑定替代不了的用途：**给已有变量赋值**（结构化绑定只能引入新名字），以及用 `std::tie(a.x, a.y) < std::tie(b.x, b.y)` 写字典序比较（C++20 起可用预置 `<=>` 替代）。

### `tuple_cat`（¶7–¶9）

¶7 用一串记号精确定义了结果：设第 *i* 个实参去 cvref 后的类型为 *Ui*，其大小为 *Si*、元素类型为 `tuple_element_t<k, Ui>`；`CTypes` 是所有实参元素类型按顺序拼接的结果，`celems` 是对应的 `get<k>(std::forward<Ti>(tpi))` 表达式拼接。¶8 *Mandates*：每个 `CTypes` 能从对应的 `celems` 构造；¶9 返回 `tuple<CTypes...>(celems...)`。注意：

- 实参是**任意 *tuple-like***（C++23 起），可以混合 `pair`、`array`、`tuple`、`complex`、`subrange`；
- 元素类型原样保留（`tuple_element_t`），引用元素仍是引用；
- 实参是右值时，元素被移动出来。

## `apply` 与 `make_from_tuple`（[tuple.apply]）

### `apply`（¶1）

```cpp
template<class F, tuple-like Tuple>
  constexpr apply_result_t<F, Tuple> apply(F&& f, Tuple&& t)
    noexcept(is_nothrow_applicable_v<F, Tuple>);
```

效果：等价于 `INVOKE(std::forward<F>(f), get<I>(std::forward<Tuple>(t))...)`，`I` 为 `0` 到 `tuple_size_v - 1`。用 *INVOKE*（[[func.require]]）意味着 `f` 可以是成员函数指针，第一个元素充当对象。

在当前草案中，`apply` 的返回类型与异常规格改用 C++26 新增的 `apply_result_t` / `is_nothrow_applicable_v`（此前是 `decltype(auto)` 与"见下"）。显式写出的返回类型让 `apply` 对不可调用的组合 SFINAE 友好。

!!! impl "libc++ 23 的 apply"
    截至本文编写时，libc++ 23 的 `apply`（`<tuple>`）仍是旧形式：`decltype(auto)` 返回类型，异常规格用 `noexcept(noexcept(...))` 计算，形参也没有用 *tuple-like* 约束（对非 tuple-like 类型会在内部的 `get` 查找处报错）。头文件中也没有 `is_applicable` / `is_nothrow_applicable` 特征。对 *tuple-like* 类型的正常使用，两者行为一致。

### `make_from_tuple` 与悬垂检查（¶2–¶3）

```cpp
template<class T, tuple-like Tuple>
  constexpr T make_from_tuple(Tuple&& t);
```

效果等价于 `T(get<I>(std::forward<Tuple>(t))...)`，内部实现函数带 `requires is_constructible_v<T, decltype(get<I>(declval<Tuple>()))...>`。注 1：`T` 不能从实参推导，必须显式写出。

注意它用的是**函数式记法** `T(...)` 而不是 `T{...}`——对聚合类型，C++20 起 `T(args...)` 也能做聚合初始化（[[dcl.init]] 的括号聚合初始化）。

¶2 的 *Mandates* 针对一个极其隐蔽的悬垂：

!!! std "[tuple.apply]/2"
    *Mandates*: If `tuple_size_v<remove_reference_t<Tuple>>` is 1, then `reference_constructs_from_temporary_v<T, decltype(get<0>(declval<Tuple>()))>` is `false`.

    当 tuple 只有一个元素、而 `T` 是引用类型时，`T(get<0>(...))` 是一个**函数式转型**，等价于 `(T)get<0>(...)`——如果这个引用绑定到一个临时量，`make_from_tuple` 返回时临时量已被销毁。

例如 `make_from_tuple<const std::string&>(std::tuple<const char*>{"x"})`：`(const std::string&)ptr` 先构造一个临时 `string`，引用绑到它上面，然后从函数返回——返回的是悬垂引用。为什么只检查 1 个元素的情形？因为只有单实参时 `T(x)` 才是转型；多实参时 `T` 是引用类型的 `T(a, b)` 本来就非良构。

```cpp run title="make_from_tuple_dangling.cpp" error
#include <tuple>
#include <string>
int main() {
  // T = const string&，唯一元素是 const char*：引用会绑定到临时 string
  auto&& r = std::make_from_tuple<const std::string&>(std::tuple<const char*>{"x"});   // error: Mandates
  (void)r;
}
```

!!! impl "libc++：Mandates 用 static_assert，并且加强了约束"
    libc++ 的 `make_from_tuple` 用 `static_assert(!std::reference_constructs_from_temporary_v<...>, "Attempted construction of reference element binds to a temporary whose lifetime has ended")` 实现 *Mandates*。另外它还在外层加了 `requires __can_make_from_tuple<_Tp, _Tuple>`，并在注释中援引 [[LWG3528]]（`make_from_tuple` 能做出等价于 C 风格转型的事）以及"实现可以施加更强约束"的条文，说明这是有意为之的"加强"：让 `make_from_tuple` 本身 SFINAE 友好。

## 辅助类：`tuple_size` 与 `tuple_element`（[tuple.helper]）

- ¶1：除另有规定外，`tuple_size` 的所有特化都满足 *Cpp17UnaryTypeTrait*，基特征为 `integral_constant<size_t, N>`。
- `tuple_size<tuple<Types...>>` 为 `sizeof...(Types)`；`tuple_element<I, tuple<Types...>>`：¶2 *Mandates* `I < sizeof...(Types)`，¶3 结果为第 `I` 个类型。
- **主模板不定义**——这是协议的关键：对非 tuple-like 类型，`tuple_size<T>` 是**不完整类型**。[[dcl.struct.bind]] 正是用"`tuple_size<E>` 是否完整"来决定走协议绑定还是走数据成员绑定的。

### `const T` 的偏特化：SFINAE 友好（¶4–¶8）

!!! std "[tuple.helper]/4"
    If the expression `TS::value` is well-formed when treated as an unevaluated operand, then each specialization of the template meets the *Cpp17UnaryTypeTrait* requirements with a base characteristic of `integral_constant<size_t, TS::value>`. Otherwise, it has no member `value`.

    `tuple_size<const T>` 只在 `tuple_size<T>::value` 有效时才有 `value`，否则它是一个**完整但没有 `value` 的类**。

这个看似多余的措辞修补过一个真实问题：早期规定 `tuple_size<const T>` 无条件派生自 `integral_constant<size_t, tuple_size<T>::value>`，于是对非 tuple-like 的 `const` 类型实例化它会**硬错误**，而结构化绑定 `auto& [a, b] = const_obj;` 正好需要检查 `tuple_size<const E>`。现在它对任何 `T` 都能安全实例化：完整，但没有 `value`；而 [[dcl.struct.bind]] 的条件恰是"完整**且**有名为 `value` 的成员"。¶5 补充：访问检查如同在与 `TS`、`T` 无关的上下文中进行，只看表达式的直接语境（[[g:immediate-context]]）；注 1 提醒，直接语境之外的副作用（隐式实例化等）仍可能使程序非良构。

¶6 与 ¶8：这两个偏特化不仅经 `<tuple>`，也经 `<array>`、`<complex>`、`<ranges>`、`<utility>` 提供——因为这些头文件中的类型都实现了协议，用户不应为了对 `const std::array` 做结构化绑定而额外包含 `<tuple>`。¶7：`tuple_element<I, const T>::type` 为 `const TE`。

`volatile T` 与 `const volatile T` 的对应偏特化在 C++20 被弃用，现位于附录 [[depr.tuple]]（仍然存在、仍然规范性）。

## 元素访问：`get`（[tuple.elem]）

按索引的四个重载（`&`、`&&`、`const&`、`const&&`）：¶1 *Mandates* `I < sizeof...(Types)`，¶2 返回第 `I` 个元素的引用。两条注解解释了引用元素的特殊行为：

- ¶3 注 1（`&&` 重载）：元素类型是 `X&` 时，返回类型是 `X&` 而不是 `X&&`——`tuple_element_t<I, ...>&&` 经引用折叠为 `X&`。**右值 tuple 里的左值引用元素仍是左值**，这正是 `forward_as_tuple` 能正确转发左值实参的原因。
- ¶4 注 2（`const&` 重载）："常量性是浅的"：元素类型是 `X&` 时，返回 `X&` 而不是 `const X&`。这与核心语言中"`const` 对象的引用成员不是 `const`"的规则一致（[[expr.ref]]）。

按类型的 `get<T>`：¶5 *Mandates* `T` 在 `Types` 中**恰好出现一次**；¶7 例子：`tuple<int, const int, double, double>` 中 `get<int>` 与 `get<const int>` 都合法（`int` 与 `const int` 是不同类型），`get<double>` 非良构。

¶8 注 3 解释了一个设计决定：`get` 为什么是非成员函数？如果是成员模板，在依赖类型的上下文里就必须写 `t.template get<0>()`（[[temp.names]]）。非成员的 `get<0>(t)` 自 C++20 起也不再需要 ADL 的特殊处理（[[temp.names]] 允许把 `get<` 当作模板名的开始，即使普通查找什么都没找到）。

## 关系运算符（[tuple.rel]）

### `operator==`（¶1–¶4）

两个重载：`tuple` 与 `tuple`，以及 `tuple` 与任意 *tuple-like*（C++23）。¶2 *Constraints*：对所有 `i`，`get<i>(t) == get<i>(u)` 有效且结果满足 *boolean-testable*（[[g:boolean-testable]]），并且大小相等。¶3 空 tuple 相等。¶4.1：**从下标 0 起依次比较，第一个不等之后不再访问任何元素**——短路是规范性要求。

¶4.2：第二个重载（与 *tuple-like* 比较）**只能经 ADL 找到**，效果类似隐藏友元（[[g:hidden-friend]]）：只有当某个操作数是 `tuple` 时它才会被考虑，不会干扰其他 tuple-like 类型之间的比较。借助 C++20 的重写候选，`pair == tuple` 会被反转为 `tuple == pair`，所以一个重载就覆盖了两个方向。

### `operator<=>`（¶5–¶8）

返回类型是各元素 `synth-three-way-result` 的公共比较类别，¶6：字典序比较，等价于"比首元素，不等则返回；否则比较剩余部分"。*synth-three-way*（[[g:synth-three-way]]）的作用同 [[pairs]]：兼容只有 `<` 的老类型。¶8 注 2 特别说明：定义中的 `ttail`（"除首元素外的 tuple"）**不需要真的构造**——元素可能不可复制——这只是描述递归语义的记法；而且所有比较运算符都短路，不做多余的元素访问。

`<`、`>`、`<=`、`>=`、`!=` 全部由重写候选得到（[[over.match.oper]]）。

## `common_reference` 与 `common_type` 特化（[tuple.common.ref]）

两个特化让 `tuple`（以及与 `tuple` 混用的其他 *tuple-like*）有"逐元素"的公共类型：

- `basic_common_reference<TTuple, UTuple, TQual, UQual>::type` = `tuple<common_reference_t<TQual<TTypes>, UQual<UTypes>>...>`（¶1–¶3）；
- `common_type<TTuple, UTuple>::type` = `tuple<common_type_t<TTypes, UTypes>...>`（¶4–¶5）。

¶2 / ¶4 的约束：至少一方是 `tuple` 的特化（避免两个 `pair` 时与 `pair` 自己的特化冲突）、两者都已 decay、大小相等、结果类型合法。

它们存在的理由是 `ranges::zip_view`（[[range.zip]]）。`zip` 的迭代器引用类型是 `tuple<int&, string&>`，值类型是 `tuple<int, string>`；`indirectly_readable` 要求两者之间存在 `common_reference`（[[iterator.concept.readable]]）。若没有这个特化，`common_reference_t<tuple<int&>&&, tuple<int>&>` 不存在，`zip` 就无法成为输入范围。注意 `TQual` / `UQual` 会把**外层** tuple 的 cv/引用限定"分发"到每个元素上：

```cpp run title="tuple_common_ref.cpp" ok
#include <tuple>
#include <type_traits>
#include <concepts>
#include <utility>
static_assert(std::is_same_v<std::common_reference_t<std::tuple<int&>&, std::tuple<int>&>, std::tuple<int&>>);
static_assert(std::is_same_v<std::common_reference_t<std::tuple<int&>, std::tuple<int>&>, std::tuple<int&>>);
static_assert(std::is_same_v<std::common_reference_t<std::tuple<int&>, std::tuple<int>>, std::tuple<int>>);
static_assert(std::is_same_v<std::common_type_t<std::tuple<int, long>, std::tuple<long, int>>, std::tuple<long, long>>);
int main(){}
```

!!! impl "libc++ 23 只特化了 tuple × tuple"
    草案的特化接受"一方是 `tuple`、另一方是任意 *tuple-like*"（[[P2165R4]] 的推广）。libc++ 23 的 `<tuple>` 中 `basic_common_reference` 仍只对 `tuple<...>` 与 `tuple<...>` 特化：`std::common_reference_t<std::tuple<int&>, std::pair<int, int>>` 在本机无法形成。这与 `<version>` 中 `__cpp_lib_tuple_like` 仍被注释掉（未宣称完整支持 [[P2165R4]]）相一致。

## 实现视角：tuple 在内存里长什么样

标准对 `tuple` 的布局只字未提，各实现差异很大：

- **libc++**：`tuple` 持有一个 `__tuple_impl`，它**按顺序**公开继承 `__tuple_leaf<0, T0>`、`__tuple_leaf<1, T1>`……每个叶子要么持有一个 `T` 成员，要么（`T` 为非 final 空类时）私有继承 `T` 以利用空基类优化。本机测得 `tuple<char, int, double>` 三个元素的偏移是 0、4、8。
- **libstdc++**：递归继承 `_Tuple_impl<I, Head, Tail...>`，基类 `_Tuple_impl<I+1, Tail...>` 在前、`Head` 在后，所以元素在内存中是**逆序**排列的。

所以不要对 `tuple` 的布局做任何假设（标准也不保证它是标准布局类型），需要确定布局时用 `struct`。一个关于空基类优化的 lawyer 细节：本机 `sizeof(std::tuple<int, Empty>)` 为 4（`Empty` 被压缩掉），但 `sizeof(std::tuple<Empty, Empty>)` 为 2——两个 `Empty` 基类子对象类型相同，按 [[intro.object]] 不能占用同一地址，只能各占一个字节。

## 常见误区

!!! pitfall "易错点清单"
    - **`std::tuple{p}`（`p` 是 `pair`）推导为 `tuple<T1, T2>` 而不是 `tuple<pair<...>>`**；要包一层请写明模板实参。
    - **`forward_as_tuple` 的结果不要存进具名变量**——除非你确定所有实参都是长寿的左值。
    - **`apply`、`tuple_cat`、`make_from_tuple` 不接受用户的 tuple-like 类型**，即使它能用于结构化绑定。
    - **`get<T>` 要求类型唯一**；`int` 与 `const int` 算两个类型。
    - **右值 tuple 的引用元素**：`get<0>(std::move(t))` 对 `tuple<X&>` 返回 `X&`，不会"移动"被引用的对象。
    - **`make_from_tuple<T&>`**：单元素时可能制造悬垂引用，C++23 起被 *Mandates* 拦截。
    - **不要特化 `std::tuple`**：IFNDR。

## 历史演进

!!! history "从 TR1 到 C++26"
    - **C++11**：`tuple` 从 TR1 进入标准，使用变参模板实现。
    - **C++14**：`get<T>` 按类型访问；`tuple_element_t`；大量 `constexpr`。
    - **C++17**：`apply`、`make_from_tuple`；CTAD 推导指引；条件 `explicit`（N4387）；结构化绑定以 tuple-like 协议为基础。
    - **C++20**：`<=>` 取代六个关系运算符；`explicit(bool)` 改写条文；`tuple_size` 等的 `volatile` 偏特化弃用。
    - **C++23**：*tuple-like* 概念及与之互操作的构造/赋值/比较/`tuple_cat`/`apply`（[[P2165R4]]）；const 赋值与 `pair`/`tuple` 的 `common_reference`（[[P2321R2]]）；悬垂引用构造函数弃置与 `make_from_tuple` 的 *Mandates*（[[P2255R2]]）。
    - **C++26**：`complex` 加入 *tuple-like*（[[P2819R2]]）；`ignore` 成为有明确类型的对象并可经 `<utility>` 获得（[[P2968R2]]）；`==` 受约束；`apply` 使用 `apply_result_t` / `is_nothrow_applicable_v`。

## 思考题

!!! question "思考题 1"
    为什么 `tuple_size<const T>` 要规定成"`TS::value` 有效时才有 `value`"，而不是直接派生自 `integral_constant<size_t, tuple_size<T>::value>`？请举出一段在后一种规定下会出错的合法代码。

<details markdown="1">
<summary>展开查看答案与解析</summary>

```cpp
struct S { int a, b; };
const S s{1, 2};
auto [x, y] = s;   // E 是 const S
```
[[dcl.struct.bind]] 要检查 `std::tuple_size<const S>` 是否为完整类型且有 `value` 成员。若偏特化无条件派生自 `integral_constant<size_t, tuple_size<S>::value>`，实例化它时 `tuple_size<S>` 不完整，`tuple_size<S>::value` 是硬错误（不在直接语境中，SFINAE 救不了），上面这段完全合法的按数据成员绑定就会编译失败。按现行 ¶4 的措辞，`tuple_size<const S>` 完整但没有 `value`，结构化绑定退回到按数据成员绑定。
</details>

!!! question "思考题 2"
    按当前草案，下面的程序输出什么？为什么？
    ```cpp
    std::tuple<std::any, std::any> t(std::allocator_arg, std::allocator<int>{});
    std::printf("%d %d\n", std::get<0>(t).has_value(), std::get<1>(t).has_value());
    ```

<details markdown="1">
<summary>展开查看答案与解析</summary>

应输出 `0 0`。元素个数为 2，第一个实参的类型是 `allocator_arg_t`，而 `T0` 是 `any` 而不是 `allocator_arg_t`，¶12.2 的消歧义约束为假，转发构造函数 `tuple(UTypes&&...)` 不参与重载决议。剩下的可行函数是分配器扩展的默认构造函数 `tuple(allocator_arg_t, const Alloc&)`；`uses_allocator_v<any, allocator<int>>` 为假，所以两个 `any` 不带分配器地值初始化，都为空。

若没有这条约束，转发构造函数同样可行，并且对第二个实参（prvalue）是"右值绑定到右值引用"，比 `const Alloc&` 更好（[[over.ics.rank]]），它会胜出，两个 `any` 分别装入 `allocator_arg_t` 和 `allocator<int>`——输出 `1 1`。截至本文编写时，libc++ 23 正是这样（它没有实现 ¶12.2），本机实测输出 `1 1`。
</details>

## 小结

!!! summary "核心要点"
    | 主题 | 要点 |
    |---|---|
    | tuple-like 协议 | `tuple_size`（主模板不定义）、`tuple_element`、`get`；用户类型可实现，供结构化绑定使用 |
    | *tuple-like* 概念 | 封闭清单：`array`、`complex`（C++26）、`pair`、`tuple`、`subrange`；库函数只认它 |
    | 构造 | 条件 explicit；消歧义约束防止劫持复制构造与分配器标签；单元素优先"包一层" |
    | 悬垂 | 引用元素绑定临时量的构造函数弃置；`make_from_tuple` 单元素引用 *Mandates* |
    | 分配器 | 每个构造函数都有 `allocator_arg_t` 版本，非引用元素做 uses-allocator 构造 |
    | 创建 | `make_tuple`（值）、`tie`（左值引用）、`forward_as_tuple`（转发引用，勿存储）、`tuple_cat`（任意 tuple-like） |
    | `get` | 常量性是浅的；右值 tuple 中的左值引用元素仍是左值 |
    | 比较 | `==` 受约束、短路；`<=>` 用 *synth-three-way*；与 tuple-like 比较只经 ADL |
    | `common_reference` | 逐元素，为 `zip` 的代理引用而设 |
    | 布局 | 未规定；libc++ 正序、libstdc++ 逆序 |
