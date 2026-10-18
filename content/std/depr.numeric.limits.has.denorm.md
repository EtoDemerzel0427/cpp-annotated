---
title: 弃用的库特性（一）：数值、C 兼容、类型特征与工具（D.10–D.19）
summary: Annex D 中的 10 项库弃用：numeric_limits::has_denorm、C23 中弃用的 <cfloat> 宏、POSIX STREAMS 错误码、is_trivial/is_pod/aligned_storage/aligned_union、std::rel_ops、volatile 版本的 tuple_size 与 variant_size、vector<bool> 的静态 swap、std::iterator 基类、move_iterator::operator->。每项给出规范内容、弃用原因、替代写法与 libc++ 实测的警告。
status: draft
covers: depr.c.macros, depr.cerrno, depr.meta.types, depr.relops, depr.tuple, depr.variant, depr.vector.bool.swap, depr.iterator, depr.move.iter.elem
related: depr, numeric.limits, meta.unary.prop, utility, tuple, variant, vector.bool, iterator.primitives, move.iterators
tags: 附录, 弃用, 标准库
updated: 2026-10-18
---

这一页是 [[depr]] 的库部分之一，对应 Annex D 的 D.10 到 D.19。与核心语言弃用不同，这些库设施的**规范定义**就在 Annex D 里：正文已经把它们移除，`std::rel_ops`、`std::iterator`、`is_pod` 的完整规格只能在这里找到。

[[depr.general#2]] 允许实现给这些名字加 `[[deprecated]]`。实测环境是 Clang 23.1.3 + libc++，所列警告都是 `-Wdeprecated-declarations`（默认开启）；libc++ 往往只在弃用发生的那个语言版本起才加属性，所以同一段代码在 `-std=c++17` 下可能没有警告。

## D.10 `numeric_limits` 的 `has_denorm` 成员 {#depr.numeric.limits.has.denorm}

**¶1–¶4**：`<limits>` 额外定义枚举 `float_denorm_style`（`denorm_indeterminate = -1`、`denorm_absent = 0`、`denorm_present = 1`），以及 `numeric_limits` 的两个静态成员 `has_denorm` 和 `has_denorm_loss`。主模板中它们分别是 `denorm_absent` 和 `false`；`numeric_limits<bool>` 也有这两个成员。¶3 规定，各个特化中这两个成员的值**未指定**。

**为什么弃用**：这两个成员本意是告诉你浮点类型是否支持非规格化数（subnormal），以及精度损失是"因非规格化"还是"因不精确结果"。但实际上：一个类型是否支持非规格化数，在同一平台上可能随运行时的浮点模式（例如 x86 的 FTZ/DAZ 标志）而变，编译期常量根本给不出可靠答案；`has_denorm_loss` 区分的两种精度损失，各实现的理解也不一致。¶3 把它们的值改成"未指定"，等于明说"别依赖它们"。

```cpp
#include <limits>
auto hd  = std::numeric_limits<double>::has_denorm;        // 弃用
auto hdl = std::numeric_limits<double>::has_denorm_loss;   // 弃用
std::float_denorm_style st = std::denorm_present;          // 弃用
```

**libc++ 实测**（`-std=c++23` 起）：

```text
warning: 'has_denorm' is deprecated [-Wdeprecated-declarations]
warning: 'has_denorm_loss' is deprecated [-Wdeprecated-declarations]
warning: 'denorm_present' is deprecated [-Wdeprecated-declarations]
warning: 'float_denorm_style' is deprecated [-Wdeprecated-declarations]
```

**替代**：`numeric_limits<T>::denorm_min()` 仍然在正文中，它返回最小的正非规格化值（不支持时返回最小正规格化值）；需要知道运行期行为，就在运行期测试。

## D.11 弃用的 C 宏 {#depr.c.macros}

**¶1** `<cfloat>` 中有宏 `FLT_HAS_SUBNORM`、`DBL_HAS_SUBNORM`、`LDBL_HAS_SUBNORM`、`DECIMAL_DIG`，定义与 C 的 `<float.h>` 相同。这几个宏在 C23 中被标为过时：`*_HAS_SUBNORM` 的问题与上面的 `has_denorm` 一样；`DECIMAL_DIG` 被按类型区分的 `FLT_DECIMAL_DIG`、`DBL_DECIMAL_DIG`、`LDBL_DECIMAL_DIG` 取代。

**¶2** 宏 `INFINITY` 和 `NAN` 除了通过 `<cfloat>` 获得，在包含 `<cmath>` 时也可用。C23 把这两个宏的"正式住处"移到了 `<float.h>`，`<math.h>` 中的那一份变成过时特性；C++ 跟随这一变化，所以经 `<cmath>` 获得它们的方式被列在这里。

**¶3** `<stdbool.h>` 中有宏 `__bool_true_false_are_defined`，值为 1。C23 中 `bool`、`true`、`false` 成了关键字，这个"用于检测 `<stdbool.h>` 是否已定义这些宏"的宏失去了意义。

**libc++ 实测**：这些宏在 `-std=c++2c -Wdeprecated` 下使用都没有任何警告。宏的弃用很难通过属性表达，实现一般不诊断。

**替代**：`DBL_DECIMAL_DIG` 等；`INFINITY`、`NAN` 改从 `<cfloat>` 获得，或者直接用 `std::numeric_limits<double>::infinity()` / `quiet_NaN()`。

## D.12 弃用的错误号 {#depr.cerrno}

**¶1–¶4**：`<cerrno>` 额外定义宏 `ENODATA`、`ENOSR`、`ENOSTR`、`ETIME`，含义由 POSIX 标准规定；`enum class errc` 额外有对应的枚举项 `no_message_available`、`no_stream_resources`、`not_a_stream`、`stream_timeout`，值与这些宏相同。

**为什么弃用**：这四个错误码属于 POSIX 的 STREAMS 子系统，POSIX 已将 STREAMS 标为过时并从后续版本中删除，C++ 跟随。

```cpp
#include <cerrno>
#include <system_error>
int en = ENODATA;                            // 宏：无警告
auto ec = std::errc::no_message_available;   // 弃用
```

**libc++ 实测**：枚举项在 `-std=c++17` 起就给出 `'no_message_available' is deprecated [-Wdeprecated-declarations]`；宏没有警告。

**替代**：通常没有必要使用它们。如果代码确实与 STREAMS 交互，直接使用平台头文件中的宏。

## D.13 弃用的类型特征 {#depr.meta.types}

**¶1** `<type_traits>` 额外提供 `is_trivial` / `is_trivial_v`、`is_pod` / `is_pod_v`、`aligned_storage` / `aligned_storage_t`、`aligned_union` / `aligned_union_t`。¶2：为它们添加特化的程序，除非对应模板的规格明确允许，否则行为未定义。

### `is_trivial` 与"平凡类"

**¶3** **平凡类**（trivial class）是可平凡复制、并有一个或多个合格的默认构造函数且全部平凡的类。**平凡类型**是标量类型、平凡类、这些类型的数组，或它们的 cv 限定版本。¶6：`is_trivial<T>` 在 `T` 是平凡类型时为 `true_type`。¶7（注）：闭包类型是否为平凡类型未指定。

注意"平凡类型"这个概念本身已经从正文中移除，只在这里定义。正文中描述内存操作时用的是更精确的两个概念：**可平凡复制**（[[basic.types.trivial]]：可以用 `memcpy` 复制）和**隐式生命周期类型**（[[g:implicit-lifetime-type]]：可以由 `malloc` 等隐式创建）。"平凡"把"能平凡默认构造"和"能平凡复制"捆在一起，而实际代码几乎从不需要恰好这两者的合取。

### `is_pod` 与"POD"

**¶4** **POD 类**是既平凡又标准布局、且没有非 POD 类类型（或其数组）的非静态数据成员的类。**POD 类型**是标量类型、POD 类、这些类型的数组或它们的 cv 限定版本。¶9：`is_pod<T>` 在 `T` 是 POD 类型时为 `true_type`。

C++11 把 POD 拆成了"平凡"与"标准布局"两个正交的概念，POD 就是二者的交集。C++20 把 `is_pod` 列为弃用，后来又把整个 POD 概念移出正文：任何需要 POD 的地方都能说清楚自己到底需要哪一半。

### `aligned_storage` 与 `aligned_union`

**¶11–¶15** `aligned_storage<Len, Align>::type` 是一个平凡的标准布局类型，适合用作任何大小不超过 `Len`、对齐是 `Align` 的因数的对象的未初始化存储。`Align` 的默认值是"大小不超过 `Len` 的任何对象类型中最严格的对齐要求"。¶14（注）指出它可以用 `alignas(Align) std::byte[Len]` 代替。

**¶16–¶17** `aligned_union<Len, Types...>::type` 是适合存放 `Types` 中任一类型对象的存储，大小至少为 `Len`；静态成员 `alignment_value` 是这些类型中最严格的对齐。

**为什么弃用**：这两个模板的接口容易用错。`aligned_storage<sizeof(T), alignof(T)>` 很常见，但人们经常写成 `aligned_storage<sizeof(T)>`（默认对齐可能不够或过度），或者忘了加 `::type`、直接把 `aligned_storage<…>` 本身当存储用（它是一个空类）。再加上它们并不真的保证 `type` 的对齐就是 `Align`（实现可以给出更严格的对齐）、使用时还离不开 `reinterpret_cast`，委员会认为 `alignas` 数组更直接。

```cpp
#include <type_traits>
#include <cstddef>
#include <new>

template<class T> struct Slot1 {
  std::aligned_storage_t<sizeof(T), alignof(T)> buf;   // 弃用
};
template<class T> struct Slot2 {
  alignas(T) std::byte buf[sizeof(T)];                 // 替代
  T* get() { return std::launder(reinterpret_cast<T*>(buf)); }
};
```

**libc++ 实测**：

| 名字 | 开始警告的模式 |
|---|---|
| `is_pod` | `-std=c++20` |
| `aligned_storage_t`、`aligned_union` | `-std=c++23` |
| `is_trivial_v` | `-std=c++2c`，警告附带提示：`Consider using is_trivially_copyable_v<T> && is_trivially_default_constructible_v<T> instead.` |

**替代**：

- `is_trivial<T>` → `is_trivially_copyable<T>` 和/或 `is_trivially_default_constructible<T>`（看你到底需要哪一个）；用于判断"能否 `malloc` 后直接使用"，用 `is_implicit_lifetime<T>`（C++23）。
- `is_pod<T>` → `is_standard_layout<T>` 和上面的组合。
- `aligned_storage` / `aligned_union` → `alignas(T) std::byte buf[sizeof(T)]`；联合的情形用 `alignas(Ts...) std::byte buf[std::max({sizeof(Ts)...})]`。

## D.14 关系运算符 `std::rel_ops` {#depr.relops}

**¶1–¶10**：`<utility>` 中有命名空间 `std::rel_ops`，提供四个函数模板：

| 模板 | 前置条件 | 返回 |
|---|---|---|
| `operator!=(x, y)` | `T` 满足 *Cpp17EqualityComparable* | `!(x == y)` |
| `operator>(x, y)` | `T` 满足 *Cpp17LessThanComparable* | `y < x` |
| `operator<=(x, y)` | 同上 | `!(y < x)` |
| `operator>=(x, y)` | 同上 | `!(x < y)` |

它的用法是 `using namespace std::rel_ops;`，让只定义了 `==` 和 `<` 的类型自动获得另外四个运算符。

**为什么弃用**：C++20 的三路比较和改写候选（[[over.match.oper]]）在语言层面解决了同一个问题，而且解决得更好：`rel_ops` 必须靠 `using namespace` 引入，对 ADL 无效（在别的命名空间里的模板代码看不到它），还会把这些运算符模板强加给作用域里的**所有**类型。

```cpp
#include <utility>
struct R {
  bool operator==(const R&) const;
  bool operator<(const R&) const;
};
bool rel(R a, R b) {
  using namespace std::rel_ops;
  return a != b && a > b;
}
```

**libc++ 实测**：`-std=c++20` 起只有 `a > b` 一处警告 `'operator>' is deprecated`；`a != b` **没有**警告。原因是 C++20 中 `a != b` 还有一个由 `R::operator==` 改写得到的候选 `!(a == b)`。它是非模板函数，而 `rel_ops::operator!=` 是函数模板特化，重载决议的平局规则优先选非模板，所以 `rel_ops` 的版本根本没被调用。`-std=c++17` 下两处都不警告。

**替代**：给类型定义 `operator==` 和 `operator<=>`（通常 `= default` 即可），`!=`、`<`、`>`、`<=`、`>=` 全部由改写候选自动提供。

## D.15 `tuple` 的 `volatile` 特化 {#depr.tuple}

**¶1–¶6**：`<tuple>` 额外提供 `tuple_size<volatile T>`、`tuple_size<const volatile T>`、`tuple_element<I, volatile T>`、`tuple_element<I, const volatile T>`。`tuple_size` 的这两个特化在 `tuple_size<T>::value` 良构时派生自 `integral_constant<size_t, tuple_size<T>::value>`，否则没有 `value` 成员（对 SFINAE 友好）；`tuple_element` 的两个特化分别给出 `volatile TE` 和 `const volatile TE`。除 `<tuple>` 外，包含 `<array>`、`<ranges>`、`<utility>` 时也能用到它们。

`tuple_size<const T>` 和 `tuple_element<I, const T>` 不在这里，它们仍是正文的一部分（[[tuple]]）。

**为什么弃用**：C++20 清理 `volatile` 的一部分（与 [[depr.local|D.4]] 同一批）。`volatile` 的元组/`pair`/`array` 几乎没有意义：对整个 `volatile std::tuple` 的访问本来就无法按 `volatile` 语义进行（`get` 不接受 `volatile` 引用）。

**libc++ 实测**：`std::tuple_size<volatile std::tuple<int>>::value` 在 `-std=c++2c` 下可以使用，没有警告。

**替代**：`std::tuple_size<std::remove_volatile_t<T>>`。

## D.16 `variant` 的 `volatile` 特化 {#depr.variant}

**¶1–¶3**：`<variant>` 额外提供 `variant_size<volatile T>`、`variant_size<const volatile T>`、`variant_alternative<I, volatile T>`、`variant_alternative<I, const volatile T>`，规则与 D.15 相同。

**libc++ 实测**：没有警告。

**替代**：同上，先去掉 `volatile`。

## D.17 `vector<bool>` 的静态 `swap` {#depr.vector.bool.swap}

**¶1–¶2**：`vector<bool, Allocator>` 额外有一个**静态**成员函数 `static constexpr void swap(reference x, reference y) noexcept;`，效果等价于 `bool b = x; x = y; y = b;`。

**为什么弃用**：这个静态成员是 `vector<bool>` 用代理引用（`reference` 是一个代理类而不是 `bool&`）实现时的补丁：`std::swap(v[i], v[j])` 对两个临时代理对象无法工作，于是加了 `vector<bool>::swap(v[i], v[j])`。但它与成员 `swap(vector&)` 同名，签名却完全不同，很令人困惑；而现在 `vector<bool>::reference` 本身就有三个友元 `swap`（`reference` 与 `reference`、`reference` 与 `bool&` 互换，见 [[vector.bool]]），经 ADL 直接写 `swap(v[i], v[j])` 就能工作。

```cpp
#include <vector>
void f(std::vector<bool>& v) {
  std::vector<bool>::swap(v[0], v[1]);   // 弃用
  swap(v[0], v[1]);                      // 替代：经 ADL 找到 reference 的 swap
}
```

**libc++ 实测**：没有警告。

## D.18 `std::iterator` 类模板 {#depr.iterator}

**¶1–¶4**：`<iterator>` 额外提供

```cpp
namespace std {
  template<class Category, class T, class Distance = ptrdiff_t,
           class Pointer = T*, class Reference = T&>
  struct iterator {
    using iterator_category = Category;
    using value_type        = T;
    using difference_type   = Distance;
    using pointer           = Pointer;
    using reference         = Reference;
  };
}
```

用作基类，帮新的迭代器类型定义所需的五个类型别名。¶3（注）指出：如果新迭代器本身是类模板，这些别名在类模板定义**内部**不可见（依赖基类中的名字不会被非限定查找找到），只对使用者可见。

**为什么弃用**：这条注释恰好说明了问题。写迭代器类模板时，基类里的 `value_type` 在类内部用不了，还得再写一遍 `using value_type = typename iterator::value_type;`，节省的那几行代码被抵消了。此外，五个模板形参的顺序很难记（`Distance` 在 `Pointer` 前面），`std::iterator<std::forward_iterator_tag, int, int>` 这种把 `difference_type` 误设成 `int` 的错误屡见不鲜。

**libc++ 实测**：`-std=c++17` 起警告 `'iterator<std::forward_iterator_tag, int>' is deprecated [-Wdeprecated-declarations]`。

**替代**：直接在迭代器类里写五个（C++20 起是 `iterator_concept` 加四个）别名。

## D.19 `move_iterator::operator->` {#depr.move.iter.elem}

**¶1–¶2**：`move_iterator<Iterator>` 额外有成员 `constexpr pointer operator->() const;`，返回 `current`（底层迭代器）。

**为什么弃用**：`move_iterator` 的意义是解引用得到**右值**（`*it` 是 `std::move(*current)`），而 `it->m` 经由底层迭代器访问成员，得到的是**左值**。同一个迭代器，`(*it).m` 和 `it->m` 的值类别不同，前者可以移动、后者不能，这违背了 `->` 与 `(*).` 等价的惯例。

```cpp
#include <iterator>
#include <string>
void f(std::string* p) {
  std::move_iterator<std::string*> m(p);
  auto n = m->size();          // 弃用
  auto n2 = (*m).size();       // 替代（注意 *m 是 std::string&&）
  auto n3 = m.base()->size();  // 替代：明确经由底层迭代器
}
```

**libc++ 实测**：`-std=c++20` 起警告 `'operator->' is deprecated [-Wdeprecated-declarations]`。

## 小结

| 条款 | libc++ 警告 | 起始模式 |
|---|---|---|
| D.10 `has_denorm` | 有 | C++23 |
| D.11 C 宏 | 无 | — |
| D.12 STREAMS 错误码 | 仅 `errc` 枚举项 | C++17（所有模式） |
| D.13 类型特征 | 有 | `is_pod` C++20；`aligned_*` C++23；`is_trivial` C++26 |
| D.14 `rel_ops` | 有（`!=` 因改写候选而不触发） | C++20 |
| D.15 / D.16 `volatile` 元组/变体特化 | 无 | — |
| D.17 `vector<bool>::swap` 静态版本 | 无 | — |
| D.18 `std::iterator` | 有 | C++17 |
| D.19 `move_iterator::operator->` | 有 | C++20 |
