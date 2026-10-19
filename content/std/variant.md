---
title: 变体类型
summary: <variant> 中类模板之外的部分：取值函数 get、get_if、holds_alternative 的契约，关系运算符怎样比较不同的候选类型和无值状态，以及 monostate、bad_variant_access 和 hash。
status: done
covers: variant.general, variant.syn, variant.helper, variant.get, variant.relops, variant.monostate, variant.monostate.relops, variant.specalg, variant.bad.access, variant.hash
papers: P0088R3, P0608R3, P2162R2, P2637R3, P0472R3
related: variant.variant, variant.visit, optional, any, expected, class.union, utilities, structure.specifications, unord.hash, cmp.categories
tags: 标准库, variant, 词汇类型, 和类型
updated: 2026-10-19
---

!!! tldr
    - `variant<Ts...>` 任一时刻装着 `Ts...` 中的一个值，并记得是第几个；值存在 variant 对象内部，不做堆分配。
    - `get<T>`、`get_if<T>`、`holds_alternative<T>` 要求 `T` 在类型列表中恰好出现一次，否则编译失败；运行时装的不是 `T`，`get` 抛 `bad_variant_access`，`get_if` 返回空指针。
    - 比较先比下标，下标相同才比值：`variant<int, double>` 里任何 `int` 都小于任何 `double`。
    - 无值状态（valueless）在比较中是最小的，两个无值的 variant 相等。
    - 第一个候选类型不能默认构造时，在最前面放一个 `monostate`，variant 就可以默认构造了。

```cpp run ok
#include <cassert>
#include <string>
#include <variant>

int main() {
  std::variant<int, std::string> v = 42;   // 装着 int
  assert(v.index() == 0);
  v = "hello";                             // 现在装着 string
  assert(v.index() == 1);
  assert(std::get<std::string>(v) == "hello");
}
```

`std::variant` 是 C++17 引入的类型安全的联合体：一个对象任一时刻恰好装着 `Ts...` 中某一个类型的值，而且自己记得装的是哪一个。用类型论的话说它是一个**和类型**（[[g:sum-type]]）；从实现看，它就是一个[[class.union|联合体]]加一个下标，生存期管理、复制、比较、哈希都由库完成。

类模板本身（构造、赋值、`emplace`、无值状态、`swap`）见 [[variant.variant]]，`std::visit` 见 [[variant.visit]]。

## 候选类型 [variant.general]

¶1 variant 对象持有并管理一个值的生存期；如果它持有值，值的类型必须是 variant 的模板实参之一。这些模板实参叫做**候选类型**（alternative，[[g:variant-alternative]]）。

由这一段和 [[variant.variant]] 可以得到几个事实：

- 持有的值嵌套于（nested within，[[intro.object]]）variant 对象之中，不允许堆分配。`sizeof(variant)` 大致是最大候选类型的大小加上下标，再按对齐补齐。
- variant 也可能不持有值。这种**无值状态**（[[g:valueless-by-exception]]）只在异常打断了类型切换时出现，此时 `index()` 返回 `variant_npos`，即 `size_t(-1)`。详见 [[variant.variant]]。
- 同一个类型可以出现多次，`variant<int, int>` 是合法的。这时只能用下标区分它们，不能用类型，这就是下面许多函数要求 `T` 恰好出现一次的原因。

¶2 标准还定义了一组仅用于说明的函数模板 *GET*。它和 `get<I>` 形式相同，区别是它的前置条件要求 `v.index()` 就是 `I`，违反时是未定义行为，而公开的 `get` 在下标不对时抛异常。标准描述复制、比较、`visit` 时都用 *GET*，意思是实现此时已经知道下标正确，不需要检查。

## 取值 [variant.get]

```cpp run ok
#include <cassert>
#include <string>
#include <variant>

int main() {
  std::variant<int, std::string> v = "hello";

  assert(std::holds_alternative<std::string>(v));
  assert(std::get<1>(v).size() == 5);

  try {
    (void)std::get<int>(v);        // 装的是 string：抛异常
    assert(false);
  } catch (const std::bad_variant_access&) {}

  assert(std::get_if<int>(&v) == nullptr);   // 不抛，返回空指针
  if (auto* p = std::get_if<std::string>(&v)) *p += '!';
  assert(std::get<std::string>(v) == "hello!");

  std::variant<int, std::string>* none = nullptr;
  assert(std::get_if<0>(none) == nullptr);   // 空指针实参也合法

  std::string s = std::get<1>(std::move(v)); // 返回 string&&
  assert(s == "hello!");
}
```

这一节的函数分两层检查：下标或类型写错是编译期错误，运行时装的不是想要的那一个才是运行期错误。

### `holds_alternative<T>`（¶1–2）

¶1 `T` 必须在 `Types` 中恰好出现一次。¶2 返回 `index()` 是否等于 `T` 在 `Types` 中的下标。函数是 `noexcept` 的；无值时 `index()` 是 `variant_npos`，结果是 `false`。

恰好出现一次是 *Mandates*，不是 *Constraints*（[[structure.specifications]]）。所以 `holds_alternative<double>(variant<int, long>{})`（出现零次）和 `holds_alternative<int>(variant<int, int>{})`（出现两次）都是非良构的，编译器必须报错。它不会悄悄返回 `false`，也不会让外层模板发生替换失败。

### `get<I>` 与 `get<T>`（¶6–9）

¶6–7 `get<I>(v)` 要求 `I < sizeof...(Types)`；`v.index() == I` 时返回所存对象的引用，否则抛出 `bad_variant_access`。¶8–9 `get<T>(v)` 要求 `T` 恰好出现一次；`v` 持有 `T` 类型的值时返回它的引用，否则抛出 `bad_variant_access`。

两者各有 `&`、`&&`、`const&`、`const&&` 四个重载，把 `v` 的值类别和 const 原样带给结果：`get<1>(std::move(v))` 返回 `T1&&`，可以直接把值移出来。

`optional` 的 `operator*` 在无值时是加固前置条件（[[optional.optional]]），而 `variant` 的 `get` 从 C++17 起就规定为有定义的失败，即抛异常。标准没有提供不检查下标的公开取值函数（*GET* 只用于说明），需要时只能用 `visit` 或 `get_if`。

`<variant>` 的概要标注为 mostly freestanding：独立实现（没有操作系统支持的实现）提供 `<variant>`，但会抛出 `bad_variant_access` 的 `get` 都标注为 *freestanding-deleted*，可以定义为弃置；`get_if` 和 `holds_alternative` 不抛异常，照常提供。

### `get_if`（¶10–13）

¶10–11 `get_if<I>(p)` 要求 `I < sizeof...(Types)`；如果 `p != nullptr` 且 `p->index() == I`，返回指向所存值的指针，否则返回 `nullptr`。¶12–13 `get_if<T>(p)` 要求 `T` 恰好出现一次，等价于用 `T` 的下标调用 `get_if`。

参数是指针，并且明确允许传入空指针。这个形状借鉴了 `any_cast` 的指针重载（[[any]]）：指针版本失败时返回空，引用版本失败时抛异常。

### 类型出现两次或零次

<div class="compare" markdown="1">

```cpp run error
#include <variant>

int main() {
  std::variant<int, int> v;
  // error: int 出现两次
  return std::get<int>(v);
}
```

```cpp run ok
#include <variant>

int main() {
  std::variant<int, int> v;
  // OK：用下标
  return std::get<0>(v);
}
```

</div>

libc++ 把这类 *Mandates* 实现为 `static_assert`，左边的诊断是 type occurs more than once in type list。

!!! pitfall "`get<T>` 会做类型转换"
    `get<long>(std::variant<int, std::string>{1})` 不会把 `int` 转成 `long`：`long` 在类型列表中出现零次，直接编译失败。取值按类型本身匹配，转换只发生在构造和赋值时（见 [[variant.variant]] 中的 *FUN* 规则）。

## 关系运算符 [variant.relops]

```cpp run ok
#include <cassert>
#include <compare>
#include <variant>

struct S { operator int() { throw 42; } };

std::variant<float, int> make_valueless() {
  std::variant<float, int> v{12.f};
  try { v.emplace<1>(S()); } catch (int) {}
  return v;                // 复制后仍然无值
}

int main() {
  auto e1 = make_valueless(), e2 = make_valueless();
  std::variant<float, int> a = 1.0f, b = 0;  // 下标 0 和 1

  assert(e1.valueless_by_exception());
  assert(e1 == e2 && !(e1 < e2));  // 两个无值：相等
  assert(e1 < a && e1 < b);        // 无值小于任何有值的
  assert(a < b);                   // 先比下标：0 < 1
  assert((e1 <=> a) == std::strong_ordering::less);
  assert((a <=> b) < 0);
}
```

关系运算符都是非成员函数，只比较同一个 `variant` 类型的两个对象，`variant<int, long>` 和 `variant<long, int>` 不能比较。总的规则是先比下标，下标相同再比值，另外对无值状态有专门的约定：

| 运算 | 规则 |
|---|---|
| `v == w` | ¶2 下标不同为 `false`；否则 `v` 无值为 `true`；否则 `GET<i>(v) == GET<i>(w)` |
| `v != w` | ¶4 下标不同为 `true`；否则 `v` 无值为 `false`；否则 `GET<i>(v) != GET<i>(w)` |
| `v < w` | ¶6 `w` 无值为 `false`；否则 `v` 无值为 `true`；否则比下标；下标相同才比值 |
| `v > w` | ¶8 `v` 无值为 `false`；否则 `w` 无值为 `true`；否则比下标，再比值 |
| `v <= w` | ¶10 `v` 无值为 `true`；否则 `w` 无值为 `false`；否则比下标，再比值 |
| `v >= w` | ¶12 `w` 无值为 `true`；否则 `v` 无值为 `false`；否则比下标，再比值 |
| `v <=> w` | ¶13 都无值为 `equal`；仅 `v` 无值为 `less`；仅 `w` 无值为 `greater`；下标的 `<=>` 不为零则返回它；否则返回 `GET<i>(v) <=> GET<i>(w)` |

从表中可以归纳出三点：

1. 无值状态是最小的元素，两个无值的 variant 相等。在 `==` 中两者的下标同为 `variant_npos`，于是走到 `v` 无值为 `true` 那一步。
2. 下标决定大类。`variant<int, double>(100) < variant<int, double>(0.5)` 为 `true`，比的是第几个候选类型，不是数值。所以候选类型的声明顺序是比较语义的一部分，重排类型列表是破坏性的改动。
3. 每个运算符只调用候选类型的同一个运算符：`v >= w` 用 `Ti` 的 `>=`，不会改写成 `!(v < w)`。对 NaN 这种不构成全序的值，variant 的行为与底层类型一致。

### 约束 {{c++26}}

¶1、¶3、¶5、¶7、¶9、¶11 要求对每个 `i`，相应的 `GET<i>(v) == GET<i>(w)` 等表达式合法且可以转换为 `bool`，这是 *Constraints*。C++23 及以前它是 *Mandates*：`variant<int, NoEq>` 的 `==` 声明存在，一用就是硬错误，而概念只检查声明，于是 `std::equality_comparable<variant<int, NoEq>>` 错误地为 `true`。改成 *Constraints* 后，运算符直接不参与重载决议，概念的判断随之准确：

```cpp run ok
#include <concepts>
#include <variant>

struct NoEq {};
static_assert(std::equality_comparable<std::variant<int, double>>);
static_assert(!std::equality_comparable<std::variant<int, NoEq>>);
int main() {}
```

本机 libc++ 23 只在 `-std=c++2c` 下给这些运算符加约束，用 `-std=c++23` 编译上例，第二个 `static_assert` 失败。

`operator<=>` 从 C++20 引入时起就带约束 `requires (three_way_comparable<Types> && ...)`，返回类型是各 `compare_three_way_result_t<Types>` 的 `common_comparison_category_t`（[[cmp.common]]）。

## monostate [variant.monostate]

```cpp run ok
#include <cassert>
#include <type_traits>
#include <variant>

struct NoDefault { NoDefault(int) {} };

static_assert(!std::is_default_constructible_v<
              std::variant<NoDefault, int>>);
std::variant<std::monostate, NoDefault, int> v;  // OK

int main() {
  assert(std::holds_alternative<std::monostate>(v));
  v = 42;                     // index() == 2
  v = std::monostate{};       // 回到空状态
  assert(v.index() == 0);
}
```

`struct monostate{};` 是一个空类型，只有一种状态。¶1 说明它的用途：放在第一个候选类型的位置，使 variant 可以默认构造。variant 的默认构造函数要求第一个候选类型 `T0` 可默认构造（[[variant.ctor#2]]），如果它不行，就在最前面垫一个 `monostate`。

它也常被用作空状态，比无值状态更可控：无值状态只能由异常产生，`monostate` 可以随时赋值进去。

[variant.monostate.relops] 规定两个 `monostate` 的 `==` 恒为 `true`，`<=>` 恒为 `strong_ordering::equal`，因为它只有一种状态。C++26 起 `<utility>` 也声明了 `monostate`（[[P0472R3]]），不必为了它包含 `<variant>`。

## 辅助类 [variant.helper]

`variant_size<V>` 和 `variant_alternative<I, V>` 是 `tuple_size`、`tuple_element` 的 variant 版本：`variant_size_v<variant<int, char>>` 是 2，`variant_alternative_t<1, variant<int, char>>` 是 `char`。

- ¶1 `variant_size` 的特化以 `integral_constant<size_t, N>` 为基类。主模板没有定义，所以对非 variant 类型使用它是编译错误，不会得到 0。
- ¶2–3 `variant_size<const T>` 与 `variant_size<T>` 相同；`variant_alternative<I, const T>::type` 是 `const` 加上 `variant_alternative<I, T>::type`。
- ¶4–5 `variant_alternative<I, variant<Types...>>::type` 是 `Types` 中的第 `I` 个类型；`I` 越界违反 *Mandates*，是编译错误，不会发生替换失败。

当前草案只有 `const` 版本的特化。`volatile` 版本在 C++20 中被弃用，已经不在草案里；本机 libc++ 23 仍然提供它们。

## swap、bad_variant_access 和 hash

### 非成员 `swap` [variant.specalg]

¶1 非成员 `swap` 要求每个 `Ti` 都可移动构造、可交换，这是 *Constraints*。¶2 效果等价于 `v.swap(w)`，¶3 异常规格等价于 `noexcept(v.swap(w))`。成员 `swap` 对可移动构造的要求则是 *Mandates*（[[variant.swap#1]]）。非成员版本用 *Constraints*，`std::is_swappable_v<variant<...>>` 才能如实报告 `false`，而不是等到调用时才报错。

### `bad_variant_access` [variant.bad.access]

`bad_variant_access` 公开继承 `std::exception`。¶1 它用来报告对 variant 值的非法访问：`get` 的下标或类型与当前值不符，或者 `visit` 遇到无值的 variant（[[variant.visit#7]]）。¶2 `what()` 返回实现定义的字符串。当前草案中 `what()` 是 `constexpr` 的，常量求值时字符串用普通字面量编码；本机 libc++ 23 的 `what()` 还不是 `constexpr`。

libc++ 实际抛出的是一个内部子类，`what()` 会区分 `std::get: variant is valueless`、`std::get: wrong alternative for variant` 和 `std::visit: variant is valueless`。用 `catch (const std::bad_variant_access&)` 捕获不受影响。

### 哈希 [variant.hash]

¶1 当且仅当每个 `hash<remove_const_t<Types>>` 都启用时，`hash<variant<Types...>>` 才启用（[[unord.hash]]）。禁用的特化不能默认构造，也不能调用，所以 `unordered_set<variant<int, NoHash>>` 在编译期就失败。它的成员函数不保证是 `noexcept` 的，因为底层类型的 hash 可能抛出异常。¶2 `hash<monostate>` 总是启用。

```cpp run ok
#include <functional>
#include <string>
#include <type_traits>
#include <unordered_set>
#include <variant>

struct NoHash {};
using H1 = std::hash<std::variant<int, std::string>>;
using H2 = std::hash<std::variant<int, NoHash>>;
static_assert(std::is_default_constructible_v<H1>);   // 启用
static_assert(!std::is_default_constructible_v<H2>);  // 禁用

int main() {
  std::unordered_set<std::variant<int, std::string>> s{1, "one"};
  return s.size() == 2 ? 0 : 1;
}
```

标准没有规定哈希值怎样计算。实践中下标会参与哈希，否则 `variant<int, long>` 中的 `7` 和 `7L` 会必然碰撞。libc++ 先对当前值求哈希，再与 `hash<size_t>{}(index())` 组合；无值时用一个固定常数代替值的哈希。

## 历史与演进

!!! history
    - C++17：[[P0088R3]] 引入 `variant`。设计上争论最多的是异常打断赋值时怎么办。Boost.Variant 用堆上的备份保证永远有值，标准选择了没有额外开销的无值状态（[[g:never-quite-empty]]）。
    - C++20：[[P0608R3]] 修正了转换构造的 *FUN* 规则，`variant<string, bool> v = "abc"` 不再选 `bool`；特殊成员函数的平凡性传播也在这一时期加入。详见 [[variant.variant]]。
    - C++23：[[P2162R2]] 让 `std::visit` 接受从 `variant` 派生的类，见 [[variant.visit]]。
    - C++26：[[P2637R3]] 增加了成员函数 `visit`；关系运算符从 *Mandates* 改为 *Constraints*；`bad_variant_access::what()` 成为 `constexpr`；`monostate` 也可以从 `<utility>` 获得。

## 思考题

!!! question "思考题 1"
    `std::variant<int, double> a = 100, b = 0.5;`，`a < b`、`a == b`、`a <=> b` 分别是什么？把类型顺序换成 `variant<double, int>` 呢？

<details markdown="1">
<summary>答案</summary>

按 [[variant.relops#6]] 和 ¶13 先比下标：`a.index()` 是 0，`b.index()` 是 1，所以 `a < b` 为 `true`，`a == b` 为 `false`，`a <=> b` 是 `strong_ordering::less`，由 `size_t` 的 `<=>` 得出。100 和 0.5 的大小完全不参与。换成 `variant<double, int>` 后，`a` 持有 `int`（下标 1），`b` 持有 `double`（下标 0），结论反过来。
</details>

!!! question "思考题 2"
    写一个泛型函数 `template<class V> bool is_int(const V& v) { return std::holds_alternative<int>(v); }`，对 `variant<long>` 调用它会怎样？标准为什么这样设计？

<details markdown="1">
<summary>答案</summary>

编译失败，不会返回 `false`。`holds_alternative` 的条件是 *Mandates*，违反时程序非良构且必须诊断（[[structure.specifications]]）。它在函数模板实例化时才触发，不在替换的直接语境（[[g:immediate-context]]）中，所以也不是替换失败。

问一个 variant 是否持有它根本不可能持有的类型，几乎总是笔误，静默返回 `false` 会掩盖错误。泛型代码如果需要类型不在列表中就当作 `false`，应当先自己检查类型是否恰好出现一次（例如用折叠表达式统计 `is_same_v`），再决定是否调用。
</details>
