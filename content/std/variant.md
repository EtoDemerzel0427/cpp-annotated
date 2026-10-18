---
title: 变体类型
summary: <variant> 总览——alternative 的概念、variant_size/variant_alternative、get/get_if/holds_alternative 的精确契约（"T 恰好出现一次"是 Mandates）、关系运算符如何对待 valueless 状态、monostate、bad_variant_access 与 hash
status: done
covers: variant.general, variant.syn, variant.helper, variant.get, variant.relops, variant.monostate, variant.monostate.relops, variant.specalg, variant.bad.access, variant.hash
papers: P0088R3, P0608R3, P2162R2, P2637R3
related: variant.variant, variant.visit, optional, any, expected, class.union, utilities, structure.specifications, unord.hash, cmp.categories
tags: 标准库, variant, 词汇类型, 和类型
updated: 2026-10-18
---

`std::variant<Ts...>` 是 C++17 引入的**类型安全的联合体**：一个对象，任一时刻恰好装着 `Ts...` 中某一个类型的值，并且**自己记得**装的是哪一个。用类型论的话说它是一个**和类型**（[[g:sum-type]]）；用实现者的话说，它就是"[[class.union|联合体]] + 一个下标"，只是生命周期管理、复制、比较、哈希全部由库替你写好。

[variant] 一共 12 个子条款。class template 本身（构造、赋值、`emplace`、`valueless_by_exception`、`swap`）在 [[variant.variant]] 深入讲解，`std::visit` 在 [[variant.visit]] 单独成页；本页负责其余部分：

| 子条款 | 内容 | 本页小节 |
|---|---|---|
| [variant.general] | 什么是 alternative；*GET* | 基本概念 |
| [variant.syn] | `<variant>` 概要 | 概要速览 |
| [[variant.variant]] | 类模板本身 | 另页 |
| [variant.helper] | `variant_size`、`variant_alternative` | 辅助类 |
| [variant.get] | `holds_alternative`、`get`、`get_if` | 取值 |
| [variant.relops] | `==` `!=` `<` `>` `<=` `>=` `<=>` | 关系运算符 |
| [[variant.visit]] | `visit` | 另页 |
| [variant.monostate] / [variant.monostate.relops] | `monostate` 及其比较 | monostate |
| [variant.specalg] | 非成员 `swap` | 其余 |
| [variant.bad.access] | `bad_variant_access` | 其余 |
| [variant.hash] | `hash<variant>`、`hash<monostate>` | 其余 |

前置知识：[[structure.specifications]] 中 *Constraints* / *Mandates* / *Preconditions* 的法律含义（[[utilities]] 导读有一张对照表）；联合体的活跃成员（[[class.union]]）。

## 基本概念（[variant.general]）

¶1 一个 `variant` 对象"持有并管理一个值的生命周期"；若它持有值，该值的类型必须是模板实参之一。这些模板实参叫作 **alternative**（[[g:variant-alternative]]，候选类型）。

几个从这句话推出来、但标准写在别处的事实：

- 持有的值**嵌套在**（*nested within*，[[intro.object]]）`variant` 对象里——即不允许堆分配（[[variant.variant#1|[variant.variant.general]/1]]）。`sizeof(variant)` 大致是"最大 alternative 的大小 + 下标"再对齐。
- "若它持有值"暗示可能**不持有值**：这就是 [[g:valueless-by-exception]] 状态，只会在异常打断类型切换时出现，详见 [[variant.variant]]。
- 同一个类型可以出现多次（`variant<int, int>` 合法），此时只能用**下标**而不能用类型来区分它们——这正是下面一系列 "T occurs exactly once" 条件的来源。

¶2 引入一个说明用的函数模板族 *GET*：它和 `get<I>` 长得一样，区别在于它的 ¶4 是 *Preconditions*（`v.index()` 必须是 `I`，违反就是 UB），而公开的 `get` 在下标不对时**抛异常**。标准在描述复制构造、比较、`visit` 时都用 *GET*，表示"这里实现者已经知道下标是对的，不需要检查"。

## 概要速览（[variant.syn]）

概要第一行注释是 `// mostly freestanding`：`variant` 在[[g:freestanding-implementation|独立实现]]中可用，但所有会抛 `bad_variant_access` 的 `get` 重载被标注为 *freestanding-deleted*（在独立实现中可以定义为删除）；`get_if`、`holds_alternative` 不抛异常，照常提供。

值得注意的几处：

- `variant_npos` 是 `size_t(-1)`，是 valueless 时 `index()` 的返回值；
- `<variant>` 必须包含 `<compare>`，因为它声明了 `operator<=>`；
- 关系运算符是**非成员**、同类型 `variant` 之间的比较——`variant<int, long>` 和 `variant<long, int>` 不能比；
- `hash` 只为 `variant<Types...>` 和 `monostate` 特化。

## 辅助类（[variant.helper]）

`variant_size<T>` 与 `variant_alternative<I, T>` 是 `variant` 版的 `tuple_size` / `tuple_element`：

- ¶1：`variant_size` 的所有特化都满足 *Cpp17UnaryTypeTrait*，基特征为 `integral_constant<size_t, N>`；主模板**不定义**，所以对非 variant 类型使用它是硬错误而不是返回 0。
- ¶2：`variant_size<const T>` 转发到 `variant_size<T>`。
- `variant_size<variant<Types...>>` 直接继承 `integral_constant<size_t, sizeof...(Types)>`。
- ¶3：`variant_alternative<I, const T>::type` 是 `const VA::type`。
- ¶4–5：`variant_alternative<I, variant<Types...>>::type` 是 `T_I`；**Mandates**：`I < sizeof...(Types)`——越界是诊断出来的编译错误，不是 SFINAE。

!!! note "volatile 版本"
    早期标准还为 `volatile T`、`const volatile T` 提供了特化，C++20 将库中这类 `volatile` 重载整体弃用，当前草案只保留 `const` 版本。libc++ 23 的 `<variant>` 仍然保留了 `volatile` 特化。

## 取值（[variant.get]）

这一节的五组函数是日常最常写的代码，而它们的契约有精确的分层：**下标或类型写错**是编译期问题，**运行时装的不是你要的那个**才是运行期问题。

### `holds_alternative<T>`（¶1–2）

!!! std
    *Mandates*: The type `T` occurs exactly once in `Types`.

    **强制要求**：类型 `T` 在 `Types` 中**恰好出现一次**。

返回 `index()` 是否等于 `T` 在 `Types` 中的下标。注意它是 *Mandates* 而不是 *Constraints*：`holds_alternative<double>(variant<int, long>{})`（零次）和 `holds_alternative<int>(variant<int, int>{})`（两次）都是**非良构且必须诊断**，不会悄悄返回 `false`，也不会让外层模板 SFINAE 掉。函数是 `noexcept` 的；valueless 时 `index()` 是 `variant_npos`，结果自然是 `false`。

### `get<I>` 与 `get<T>`（¶6–9）

- `get<I>(v)`：**Mandates** `I < sizeof...(Types)`；**Effects**：若 `v.index() == I` 返回对所存对象的引用，否则**抛出** `bad_variant_access`。
- `get<T>(v)`：**Mandates** `T` 恰好出现一次；**Effects**：若 `v` 持有 `T` 类型的值，返回其引用，否则抛出 `bad_variant_access`。
- 四个重载（`&`、`&&`、`const&`、`const&&`）把 `v` 的值类别和 const 性质原样转发给结果：`get<1>(std::move(v))` 返回 `T_1&&`，可以直接把值"搬出来"。

对比 `optional::operator*`（[[optional.observe]]）：那里"没有值"是 C++26 的 *Hardened preconditions*；而 `variant::get` 从 C++17 起就选择了**有定义的失败**——抛异常。想要无检查的访问，标准没有提供公开接口（*GET* 是说明用的），只能用 `visit` 或 `get_if`。

### `get_if`（¶10–13）

- `get_if<I>(p)`：**Mandates** `I < sizeof...(Types)`；若 `p != nullptr && p->index() == I` 返回指向所存值的指针，否则返回 `nullptr`。
- `get_if<T>(p)`：**Mandates** `T` 恰好出现一次；等价于 `get_if<i>(p)`。
- 参数是**指针**，并且明确允许传 `nullptr`（返回 `nullptr`）。这个形状借鉴了 `any_cast` 的指针重载（[[any]]）：指针版本"失败时返回空"，引用版本"失败时抛异常"。

```cpp run title="variant-get.cpp" ok
#include <cassert>
#include <string>
#include <variant>

int main() {
    std::variant<int, std::string> v = "hello";

    assert(std::holds_alternative<std::string>(v));
    assert(std::get<1>(v).size() == 5);
    assert(std::get<std::string>(v) == "hello");

    try {
        (void)std::get<int>(v);                      // 存的是 string → 抛异常
        assert(false);
    } catch (const std::bad_variant_access&) {}

    assert(std::get_if<int>(&v) == nullptr);         // 指针形式：不抛，返回 nullptr
    if (auto* p = std::get_if<std::string>(&v)) *p += '!';
    assert(std::get<std::string>(v) == "hello!");

    std::variant<int, std::string>* none = nullptr;
    assert(std::get_if<0>(none) == nullptr);         // 空指针实参也合法

    std::string s = std::get<1>(std::move(v));       // 右值重载返回 string&&
    assert(s == "hello!");
}
```

而"类型出现两次"是编译错误：

```cpp run title="get-ambiguous.cpp" error
#include <variant>

int main() {
    std::variant<int, int> v;
    return std::get<int>(v);      // error: Mandates 不满足——int 出现两次
}
```

libc++ 把这类 Mandates 实现为 `static_assert`（`__tuple/find_index.h` 中的 `__find_exactly_one_t`，诊断为 "type occurs more than once in type list"）。用下标 `std::get<0>(v)` 则没有问题。

!!! pitfall "`get<T>` 不做任何转换"
    `get<long>(variant<int, std::string>{1})` 不是"把 int 转成 long"——`long` 在 `Types` 中出现零次，直接编译失败。`variant` 的取值是**按身份匹配**，转换只发生在**构造/赋值**时（见 [[variant.variant]] 的 *FUN* 规则）。

## 关系运算符（[variant.relops]）

比较的总体规则是"**先比下标，下标相同再比值**"，再加上对 valueless 状态的特别约定。逐条看 *Returns*：

| 运算 | 规则（¶编号） |
|---|---|
| `v == w` | 下标不同 → `false`；否则若 `v` valueless → `true`；否则 `GET<i>(v) == GET<i>(w)`（¶2） |
| `v != w` | 下标不同 → `true`；否则若 `v` valueless → `false`；否则 `GET<i>(v) != GET<i>(w)`（¶4） |
| `v < w` | `w` valueless → `false`；否则 `v` valueless → `true`；否则比下标；下标相同才 `GET<i>(v) < GET<i>(w)`（¶6） |
| `v > w` | `v` valueless → `false`；否则 `w` valueless → `true`；否则比下标；再比值（¶8） |
| `v <= w` | `v` valueless → `true`；否则 `w` valueless → `false`；否则比下标；再比值（¶10） |
| `v >= w` | `w` valueless → `true`；否则 `v` valueless → `false`；否则比下标；再比值（¶12） |
| `v <=> w` | 都 valueless → `equal`；仅 `v` → `less`；仅 `w` → `greater`；下标 `<=>` 非零则返回之；否则 `GET<i>(v) <=> GET<i>(w)`（¶13） |

由此可以归纳出三条语义：

1. **valueless 是最小元素**，且两个 valueless 相等（`==` 中两者下标同为 `variant_npos`，于是走到"若 `v` valueless → `true`"）。
2. **下标决定大类**：`variant<int, double>` 中，任何 `int` 都小于任何 `double`，`variant<int,double>(100) < variant<int,double>(0.5)` 为 `true`——比的是"第几个 alternative"，不是数值。
3. 每个运算符**只调用对应的那个运算符**：`v < w` 用 `T_i` 的 `<`，`v >= w` 用 `T_i` 的 `>=`，不会把 `>=` 改写成 `!(v < w)`。这保证了对 NaN 之类非全序的值，`variant` 的行为与底层类型一致。

```cpp run title="variant-relops.cpp" ok
#include <cassert>
#include <compare>
#include <variant>

struct S { operator int() { throw 42; } };

std::variant<float, int> make_valueless() {
    std::variant<float, int> v{12.f};
    try { v.emplace<1>(S()); } catch (int) {}
    return v;                                   // 复制一个 valueless 的 variant 仍是 valueless
}

int main() {
    auto e1 = make_valueless(), e2 = make_valueless();
    std::variant<float, int> a = 1.0f, b = 0;   // a.index()==0, b.index()==1

    assert(e1.valueless_by_exception());
    assert(e1 == e2 && !(e1 < e2));             // 两个 valueless：相等
    assert(e1 < a && e1 < b);                   // valueless 小于任何有值的
    assert(a < b);                              // 先比 index：0 < 1，不比值
    assert((e1 <=> a) == std::strong_ordering::less);
    assert((a <=> b) < 0);
}
```

### 约束：从 Mandates 到 Constraints

¶1、¶3、¶5、¶7、¶9、¶11 对每个运算符都写着 *Constraints*：对所有 `i`，`GET<i>(v) == GET<i>(w)`（相应运算符）必须是合法表达式且可转换为 `bool`。C++23 及之前的措辞是 *Mandates*——那时 `variant<int, NoEq>` 的 `==` "存在但一用就硬错误"，于是 `std::equality_comparable<variant<int, NoEq>>` 会错误地报告 `true`（概念只检查声明）。改成 *Constraints* 后运算符直接不参与重载决议，概念检测随之变准。

```cpp run title="relops-constraints.cpp" ok
#include <concepts>
#include <variant>

struct NoEq {};
static_assert(std::equality_comparable<std::variant<int, double>>);
static_assert(!std::equality_comparable<std::variant<int, NoEq>>);  // C++26：Constraints
int main() {}
```

libc++ 只在 `-std=c++2c` 下给这些运算符加 `requires` 子句；用 `-std=c++23` 编译上例，第二个 `static_assert` 会失败。

`operator<=>` 则从 C++20 引入起就是带 `requires (three_way_comparable<Types> && ...)` 的约束模板，返回类型是所有 `compare_three_way_result_t<Types>` 的 `common_comparison_category_t`（[[cmp.common]]）。

## monostate（[variant.monostate]、[variant.monostate.relops]）

`struct monostate{};` ——一个空的、只有一种状态的类型。¶1 说明它的用途：**放在第一个 alternative，使 variant 可以默认构造**。`variant` 的默认构造函数要求 `T_0` 可默认构造（[[variant.ctor#2]]），如果第一个类型没有默认构造函数，就在最前面垫一个 `monostate`。它也常被当作"空"状态使用，比 valueless 更可控：valueless 只能由异常产生，`monostate` 可以随时赋值进去。

[variant.monostate.relops] 给出 `operator==` 恒为 `true`、`operator<=>` 恒为 `strong_ordering::equal`，都是 `constexpr noexcept`；注 1 解释：只有一种状态，所以总是相等。`<variant>` 之外，`monostate` 也在 `<utility>` 中声明（C++26 起，为了让不想包含 `<variant>` 的代码也能用它）——libc++ 把它放在 `__variant/monostate.h`。

```cpp run title="monostate.cpp" ok
#include <cassert>
#include <type_traits>
#include <variant>

struct NoDefault { NoDefault(int) {} };

// std::variant<NoDefault, int> x;               // error: T0 不可默认构造
std::variant<std::monostate, NoDefault, int> v;  // OK：持有 monostate

static_assert(std::is_default_constructible_v<std::variant<std::monostate, NoDefault>>);
static_assert(!std::is_default_constructible_v<std::variant<NoDefault, int>>);

int main() {
    assert(v.index() == 0);
    assert(std::holds_alternative<std::monostate>(v));
    v = 42;                                        // index() == 2
    v = std::monostate{};                          // "清空"回到空状态
    assert(v.index() == 0);
    assert(std::monostate{} == std::monostate{});
}
```

## 其余：swap、bad_variant_access、hash

### 非成员 `swap`（[variant.specalg]）

¶1 **Constraints**：对所有 `i`，`is_move_constructible_v<T_i> && is_swappable_v<T_i>`；¶2 等价于 `v.swap(w)`；¶3 异常规格等价于 `noexcept(v.swap(w))`。注意成员 `swap` 对 `is_move_constructible` 用的是 *Mandates*（[[variant.swap#1]]），而非成员版本用 *Constraints*——这样 `std::is_swappable_v<variant<...>>` 能正确地报告 `false`，而不是在调用时才炸。成员函数的语义在 [[variant.variant]] 中讨论。

### `bad_variant_access`（[variant.bad.access]）

公开继承 `std::exception`；¶1 说明它用来报告对 variant 值的非法访问——`get` 下标/类型不对、`visit` 遇到 valueless（[[variant.visit#7]]）。¶2 `what()` 返回实现定义的 NTBS。C++26 草案中 `what()` 是 `constexpr` 的，并规定常量求值时按普通字面量编码——这是"常量求值中允许抛出异常"系列改动的一部分。截至本文编写时，libc++ 23 的 `bad_variant_access::what()` 尚不是 `constexpr`。

!!! impl "libc++：带消息的子类"
    libc++ 实际抛出的是内部子类 `__bad_variant_access_with_msg`，`what()` 会区分 `"std::get: variant is valueless"`、`"std::get: wrong alternative for variant"` 和 `"std::visit: variant is valueless"`。用 `catch (const std::bad_variant_access&)` 捕获不受影响。

### 哈希（[variant.hash]）

!!! std
    The specialization `hash<variant<Types...>>` is enabled if and only if every specialization in `hash<remove_const_t<Types>>...` is enabled.

    `hash<variant<Types...>>` 是**启用的**，当且仅当每个 `hash<remove_const_t<Types>>` 都是启用的。

"启用/禁用"的含义见 [[unord.hash]]：禁用的特化不可默认构造、不可调用，`unordered_set<variant<int, NoHash>>` 会在编译期失败而不是链接期。¶1 还特意说明成员函数**不保证** `noexcept`（底层类型的 hash 可能抛）。¶2：`hash<monostate>` 总是启用。

标准不规定哈希值如何组合，但实践中**下标会参与哈希**——否则 `variant<int, long>` 的 `7` 和 `7L` 会天然碰撞。libc++ 的实现是"对当前 alternative 求哈希，再与 `hash<size_t>{}(index())` 组合"；valueless 时用一个固定常数（源码注释里是光速 299792458）代替值的哈希。

```cpp run title="variant-hash.cpp" ok
#include <functional>
#include <string>
#include <type_traits>
#include <unordered_set>
#include <variant>

struct NoHash {};
using H1 = std::hash<std::variant<int, std::string>>;
using H2 = std::hash<std::variant<int, NoHash>>;
static_assert(std::is_default_constructible_v<H1>);   // 启用
static_assert(!std::is_default_constructible_v<H2>);  // 禁用：NoHash 没有 hash

int main() {
    std::unordered_set<std::variant<int, std::string>> s{1, "one"};
    return s.size() == 2 ? 0 : 1;
}
```

## 历史

!!! history "variant 的演进"
    - **C++17**：[[P0088R3]] 引入 `variant`。设计争论的焦点是"异常打断赋值时怎么办"：Boost.Variant 用堆上备份保证"永不为空"，标准最终选择了零开销的 **valueless_by_exception** 状态（[[g:never-quite-empty]]）。
    - **C++20**：[[P0608R3]] 修正转换构造的 *FUN* 规则（`variant<string, bool> v = "abc"` 不再选 `bool`）；特殊成员函数的平凡性传播、`constexpr` 化等也在这一时期完成。详见 [[variant.variant]]。
    - **C++23**：[[P2162R2]] 让 `std::visit` 接受从 `variant` 派生的类（*as-variant*），见 [[variant.visit]]。
    - **C++26**：[[P2637R3]] 增加成员 `visit`；关系运算符从 *Mandates* 改为 *Constraints*；`bad_variant_access::what()` 成为 `constexpr`。

## 思考题

!!! question "思考题 1"
    `std::variant<int, double> a = 100, b = 0.5;` 那么 `a < b`、`a == b`、`a <=> b` 分别是什么？如果把类型顺序换成 `variant<double, int>` 呢？

<details markdown="1">
<summary>展开查看答案与解析</summary>

按 [variant.relops]/6 与 ¶13，先比下标：`a.index() == 0`、`b.index() == 1`，于是 `a < b` 为 `true`、`a == b` 为 `false`、`a <=> b` 是 `strong_ordering::less`（由 `size_t` 的 `<=>` 产生）——数值 100 > 0.5 完全不参与。换成 `variant<double, int>` 后 `a` 持有 `int`（下标 1），`b` 持有 `double`（下标 0），结论反转。所以 **alternative 的声明顺序是 `variant` 比较语义的一部分**，重排类型列表是破坏性改动。
</details>

!!! question "思考题 2"
    为什么 `holds_alternative<T>` 用 *Mandates* 而不是 *Constraints*？写一个泛型函数 `template<class V> bool is_int(const V& v) { return holds_alternative<int>(v); }`，对 `variant<long>` 调用它会发生什么？

<details markdown="1">
<summary>展开查看答案与解析</summary>

*Mandates* 违反是**非良构且要求诊断**（[[structure.specifications]]），在函数模板实例化时以 `static_assert` 风格触发，不在 [[g:immediate-context]] 中，因此**不是 SFINAE**：`is_int(variant<long>{})` 直接编译失败，而不是返回 `false`。标准的考虑是：问一个 variant "是否持有它根本不可能持有的类型"几乎总是笔误，让它静默返回 `false` 会掩盖 bug。需要"类型不在列表里就当 false"的泛型代码，应先自己检查类型是否恰好出现一次（例如用折叠表达式数 `is_same_v`），再决定是否调用。
</details>

## 小结

| 设施 | 契约要点 |
|---|---|
| `variant_size` / `variant_alternative` | 主模板不定义；`I` 越界是 Mandates |
| `holds_alternative<T>` | Mandates：`T` 恰好出现一次；`noexcept` |
| `get<I>` / `get<T>` | Mandates 下标/类型合法；运行时不匹配**抛** `bad_variant_access` |
| `get_if<I>` / `get_if<T>` | 同样的 Mandates；不匹配或 `nullptr` 实参返回 `nullptr`；`noexcept` |
| 关系运算符 | 先比下标，再比值；valueless 最小且彼此相等；C++26 起为 Constraints |
| `monostate` | 放在首位使 variant 可默认构造；永远相等 |
| 非成员 `swap` | Constraints：可移动构造且可交换 |
| `hash<variant>` | 所有 alternative 都可哈希时才启用；不保证 `noexcept` |
