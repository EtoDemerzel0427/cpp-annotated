---
title: 弃用的库特性（一）：数值、C 兼容、类型特征与工具（D.10–D.19）
summary: Annex D 中的十项库弃用，从 numeric_limits::has_denorm、is_pod、aligned_storage 到 std::rel_ops、std::iterator，各自为什么被弃用、该改用什么，以及 libc++ 是否给出警告。
status: done
covers: depr.c.macros, depr.cerrno, depr.meta.types, depr.relops, depr.tuple, depr.variant, depr.vector.bool.swap, depr.iterator, depr.move.iter.elem
papers: P2614R2, P0767R1, P3247R2, P1413R3
related: depr, numeric.limits, meta.unary.prop, utility, tuple, variant, vector.bool, iterator.primitives, move.iterators
tags: 附录, 弃用, 标准库
updated: 2026-10-19
---

!!! tldr
    - 这十项设施仍然是标准的一部分，但正文已经不再提它们，完整定义只留在 Annex D 里，将来可能删除。
    - `is_pod`、`is_trivial` 背后的概念太粗，`aligned_storage`、`aligned_union` 容易用错。改用 `is_trivially_copyable` 等更精确的特征，以及 `alignas(T) std::byte buf[sizeof(T)]`。
    - `std::rel_ops` 已被 C++20 的 `operator<=>` 和改写候选取代；`std::iterator` 基类不如直接写出五个类型别名。
    - `numeric_limits::has_denorm` 和 `*_HAS_SUBNORM` 宏在编译期回答不了一个运行时才确定的问题，所以它们的值改成了未指定。
    - libc++ 给大多数被弃用的名字加了 `[[deprecated]]`，但宏、`volatile` 特化和 `vector<bool>` 的静态 `swap` 没有警告。

**弃用**（deprecated）的特性仍然是规范性的，实现必须提供，只是已被确定为将来可能删除的候选（[[depr.general#2]]）。实现可以给这些库名字加上 `[[deprecated]]` 属性，使用时得到 `-Wdeprecated-declarations` 警告（默认开启）。

本页的实测环境是 Clang 23.1.3 和 libc++。libc++ 通常只在弃用发生的那个语言版本起才加属性，所以同一段代码在 `-std=c++17` 下可能没有警告。

## D.10 `numeric_limits` 的 `has_denorm` 成员 {#depr.numeric.limits.has.denorm}

```cpp
#include <limits>
auto hd  = std::numeric_limits<double>::has_denorm;       // 弃用
auto hdl = std::numeric_limits<double>::has_denorm_loss;  // 弃用
std::float_denorm_style st = std::denorm_present;         // 弃用
```

¶1 `<limits>` 额外定义枚举 `float_denorm_style`，枚举项是 `denorm_indeterminate = -1`、`denorm_absent = 0`、`denorm_present = 1`。¶2 和 ¶4 给 `numeric_limits` 的主模板和 `numeric_limits<bool>` 加上两个静态成员：`has_denorm` 为 `denorm_absent`，`has_denorm_loss` 为 `false`。

¶3 各个特化中这两个成员的值是未指定的。也就是说，标准不再保证 `numeric_limits<double>::has_denorm` 告诉你任何真实情况。

这两个成员本意是回答：这个浮点类型支持非规格化数（subnormal）吗？精度损失是因为非规格化，还是因为结果不精确？问题在于，同一台机器上非规格化数是否可用，可能随运行时的浮点模式改变（例如 x86 的 FTZ/DAZ 标志），一个编译期常量给不出可靠答案。各实现对 `has_denorm_loss` 的理解也不一致。C++23 因此弃用了它们（[[P2614R2]]）。

libc++ 从 `-std=c++23` 起对上面四个名字都发出 `-Wdeprecated-declarations` 警告。

**替代**：`numeric_limits<T>::denorm_min()` 仍在正文中，返回最小的正非规格化值，不支持时返回最小的正规格化值。需要知道运行时的行为，就在运行时检测。

## D.11 弃用的 C 宏 {#depr.c.macros}

¶1 `<cfloat>` 中有宏 `FLT_HAS_SUBNORM`、`DBL_HAS_SUBNORM`、`LDBL_HAS_SUBNORM` 和 `DECIMAL_DIG`，定义与 C 的 `<float.h>` 相同。C23 把它们标为过时：`*_HAS_SUBNORM` 的问题与上面的 `has_denorm` 一样；`DECIMAL_DIG` 已被按类型区分的 `FLT_DECIMAL_DIG`、`DBL_DECIMAL_DIG`、`LDBL_DECIMAL_DIG` 取代。

¶2 宏 `INFINITY` 和 `NAN` 正常应从 `<cfloat>` 获得。包含 `<cmath>` 也能得到它们，被弃用的是这种获得方式。C23 把这两个宏的主要位置移到了 `<float.h>`，`<math.h>` 中的那一份成了过时特性，C++ 随之调整。

¶3 `<stdbool.h>` 中的宏 `__bool_true_false_are_defined` 值为 1。C23 中 `bool`、`true`、`false` 成了关键字，用来检测这几个宏是否已定义的这个宏也就没有意义了。

宏不能加 `[[deprecated]]`，libc++ 对这些宏都不给警告（`-Wdeprecated` 下也没有）。替代写法是 `DBL_DECIMAL_DIG` 等宏、从 `<cfloat>` 获得 `INFINITY` 和 `NAN`，或者用 `std::numeric_limits<double>::infinity()` 和 `quiet_NaN()`。

## D.12 弃用的错误号 {#depr.cerrno}

```cpp
#include <cerrno>
#include <system_error>
int en = ENODATA;                           // 宏：无警告
auto ec = std::errc::no_message_available;  // 弃用
```

¶1–¶2 `<cerrno>` 额外定义宏 `ENODATA`、`ENOSR`、`ENOSTR`、`ETIME`，含义由 POSIX 规定。¶3–¶4 `enum class errc` 额外有对应的枚举项 `no_message_available`、`no_stream_resources`、`not_a_stream`、`stream_timeout`，值与这些宏相同。

这四个错误码属于 POSIX 的 STREAMS 子系统。POSIX 已把 STREAMS 标为过时并从后续版本中删除，C++ 随之弃用。

libc++ 在所有语言模式下都对这些 `errc` 枚举项发出警告，宏没有警告。一般代码用不到它们；确实要和 STREAMS 交互，就直接用平台头文件中的宏。

## D.13 弃用的类型特征 {#depr.meta.types}

¶1 `<type_traits>` 额外提供 `is_trivial`、`is_pod`、`aligned_storage`、`aligned_union`，以及对应的 `_v` 变量模板和 `_t` 别名模板。¶2 给它们添加特化的程序，除非对应模板的规格明确允许，否则行为未定义。

### `is_trivial` 与平凡类型

¶3 **平凡类**（trivial class）是可平凡复制、并且有一个或多个合格的默认构造函数、这些构造函数全都平凡的类。**平凡类型**是标量类型、平凡类、它们的数组，以及它们的 cv 限定版本。¶6 规定 `is_trivial<T>` 在 `T` 是平凡类型时为 `true_type`。¶5 要求 `T`（去掉数组维度后）是完整类型或 cv `void`，¶7 指出闭包类型是否为平凡类型是未指定的。

平凡类型这个概念如今只在这里定义，C++26 把它从正文移了出来（[[P3247R2]]）。它把能平凡默认构造和能平凡复制捆在一起，而实际代码几乎从不需要恰好这两者同时成立。正文描述内存操作时用的是更精确的两个概念：**可平凡复制**（[[basic.types.general]]，可以用 `memcpy` 复制）和**隐式生命周期类型**（[[g:implicit-lifetime-type]]，可以由 `malloc` 等操作隐式创建）。

libc++ 在 `-std=c++2c` 下对 `is_trivial_v` 发出警告，并附带建议：`Consider using is_trivially_copyable_v<T> && is_trivially_default_constructible_v<T> instead.`

### `is_pod` 与 POD

¶4 **POD 类**是既是平凡类、又是标准布局类，并且没有非 POD 类类型（或其数组）的非静态数据成员的类。**POD 类型**是标量类型、POD 类、它们的数组，以及它们的 cv 限定版本。¶9 规定 `is_pod<T>` 在 `T` 是 POD 类型时为 `true_type`，¶8 和 ¶10 的前置条件和注与 `is_trivial` 相同。

C++11 把 POD 拆成平凡和标准布局两个独立的概念，POD 就是二者的交集。需要 POD 的地方，实际上总是只需要其中的一半：要 `memcpy` 就检查可平凡复制，要和 C 共享布局就检查 `is_standard_layout`。C++20 因此弃用了 `is_pod`（[[P0767R1]]），libc++ 从 `-std=c++20` 起警告。

### `aligned_storage` 与 `aligned_union`

<div class="compare" markdown="1">

```cpp
#include <type_traits>
template<class T> struct Slot1 {
  // 弃用
  std::aligned_storage_t<
      sizeof(T), alignof(T)> buf;
};
```

```cpp
#include <cstddef>
template<class T> struct Slot2 {
  // 替代
  alignas(T)
    std::byte buf[sizeof(T)];
};
```

</div>

¶11–¶13 `aligned_storage<Len, Align>::type` 是一个平凡的标准布局类型，可以用作任何大小不超过 `Len`、对齐是 `Align` 的因数的对象的未初始化存储。`Align` 的默认值是大小不超过 `Len` 的对象类型中最严格的对齐要求。¶14 的注指出，它可以用 `alignas(Align)` 修饰的 `std::byte[Len]` 数组代替；¶15 给出了这样的典型实现。

¶16–¶17 `aligned_union<Len, Types...>::type` 可以存放 `Types` 中任一类型的对象，大小至少为 `Len`；静态成员 `alignment_value` 是这些类型中最严格的对齐。

这两个模板容易用错。忘了写 `::type` 时，`std::aligned_storage<16, 8>` 本身只是一个空类，libc++ 中 `sizeof` 为 1，拿它当存储就会越界。省略 `Align` 时得到的默认对齐可能和所需不同。而它们能做的事，`alignas` 数组都能更直接地做到。C++23 弃用了它们（[[P1413R3]]），libc++ 从 `-std=c++23` 起警告。

**替代**：`alignas(T) std::byte buf[sizeof(T)]`。联合的情形写成 `alignas(Ts...) std::byte buf[std::max({sizeof(Ts)...})]`。在这块存储里用 placement new 创建对象后，经 `std::launder(reinterpret_cast<T*>(buf))` 取得指针。

| 被弃用的特征 | 改用 |
|---|---|
| `is_trivial<T>` | `is_trivially_copyable<T>`、`is_trivially_default_constructible<T>`，看实际需要哪一个；要判断能否 `malloc` 后直接使用，用 `is_implicit_lifetime<T>`（C++23） |
| `is_pod<T>` | `is_standard_layout<T>` 加上面的特征 |
| `aligned_storage`、`aligned_union` | `alignas` 修饰的 `std::byte` 数组 |

## D.14 关系运算符 `std::rel_ops` {#depr.relops}

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

¶1–¶2 `<utility>` 的命名空间 `std::rel_ops` 提供四个函数模板，让只定义了 `==` 和 `<` 的类型自动获得另外四个运算符：

| 模板 | 前置条件 | 返回 |
|---|---|---|
| ¶3–¶4 `operator!=(x, y)` | `T` 满足 *Cpp17EqualityComparable* | `!(x == y)` |
| ¶5–¶6 `operator>(x, y)` | `T` 满足 *Cpp17LessThanComparable* | `y < x` |
| ¶7–¶8 `operator<=(x, y)` | 同上 | `!(y < x)` |
| ¶9–¶10 `operator>=(x, y)` | 同上 | `!(x < y)` |

它必须用 `using namespace std::rel_ops;` 引入。这有两个后果：其他命名空间里的模板代码看不到这些运算符，因为 ADL 不会查找 `std::rel_ops`；而一旦引入，作用域里的每个类型都会得到这四个运算符模板。C++20 的三路比较和改写候选（[[over.match.oper]]）在语言层面解决了同一个问题，`rel_ops` 随之被弃用。

上面的例子在 libc++ 的 `-std=c++20` 下只有 `a > b` 一处警告，`a != b` 没有警告。原因是 C++20 中 `a != b` 还有一个由 `R::operator==` 改写得到的候选 `!(a == b)`。它是非模板函数，而 `rel_ops::operator!=` 是函数模板特化，重载决议在平局时优先选非模板函数，于是 `rel_ops` 的版本根本没有被调用。

**替代**：给类型定义 `operator==` 和 `operator<=>`，通常 `= default` 即可。`!=`、`<`、`>`、`<=`、`>=` 都由改写候选提供。

## D.15 `tuple` 的 `volatile` 特化 {#depr.tuple}

```cpp
#include <tuple>
#include <type_traits>
using V = volatile std::tuple<int, long>;
static_assert(std::tuple_size<V>::value == 2);         // 弃用
static_assert(std::tuple_size<std::remove_volatile_t<V>>::value == 2);
```

¶1 `<tuple>` 额外提供 `tuple_size<volatile T>`、`tuple_size<const volatile T>`、`tuple_element<I, volatile T>` 和 `tuple_element<I, const volatile T>`。

¶2–¶3 两个 `tuple_size` 特化在 `tuple_size<T>::value` 良构时派生自 `integral_constant<size_t, tuple_size<T>::value>`，否则没有 `value` 成员。这样它们可以在 SFINAE 中安全使用。¶5 两个 `tuple_element` 特化分别给出 `volatile TE` 和 `const volatile TE`，其中 `TE` 是 `tuple_element_t<I, T>`。¶4 和 ¶6 规定，包含 `<array>`、`<ranges>`、`<utility>` 时也能用到它们。

`tuple_size<const T>` 和 `tuple_element<I, const T>` 不在这里，它们仍是正文的一部分（[[tuple]]）。

## D.16 `variant` 的 `volatile` 特化 {#depr.variant}

¶1–¶3 `<variant>` 对 `variant_size` 和 `variant_alternative` 额外提供同样的四个特化，规则与 D.15 相同。

这两组特化的弃用是 C++20 清理 `volatile` 的一部分，与 [[depr.volatile.type]] 同属一批。`volatile` 的 `tuple`、`pair`、`array`、`variant` 几乎没有意义：`std::get` 不接受 `volatile` 引用，整个对象本来就无法按 `volatile` 语义访问。

libc++ 对这些特化都不给警告。需要时先去掉 `volatile`，如上例中的 `std::remove_volatile_t<V>`。

## D.17 `vector<bool>` 的静态 `swap` {#depr.vector.bool.swap}

```cpp
#include <vector>
void f(std::vector<bool>& v) {
  std::vector<bool>::swap(v[0], v[1]);  // 弃用
  swap(v[0], v[1]);  // 替代：经 ADL 找到 reference 的友元 swap
}
```

¶1–¶2 `vector<bool, Allocator>` 额外有一个静态成员函数 `static constexpr void swap(reference x, reference y) noexcept;`，效果如同 `bool b = x; x = y; y = b;`。

`vector<bool>` 的 `reference` 是一个代理类，不是 `bool&`。`v[i]` 返回的是代理类型的临时对象，泛型的 `std::swap` 不能绑定它，所以当初加了这个静态成员。但它和交换整个容器的成员 `swap(vector&)` 同名、签名却完全不同，容易混淆。如今 `vector<bool>::reference` 自己有三个友元 `swap`（[[vector.bool]]），直接写 `swap(v[i], v[j])` 就能通过 ADL 找到它们。

libc++ 对静态 `swap` 不给警告。

## D.18 `std::iterator` 类模板 {#depr.iterator}

¶1–¶2 `<iterator>` 额外提供类模板 `iterator<Category, T, Distance = ptrdiff_t, Pointer = T*, Reference = T&>`，它只定义了五个成员类型别名：`iterator_category`、`value_type`、`difference_type`、`pointer`、`reference`。自定义迭代器可以派生自它，省去手写这些别名。¶4 的例子展示了这种用法。

```cpp
#include <iterator>
template<class T>
struct It : std::iterator<std::forward_iterator_tag, T> {  // 弃用
  // value_type v;  // error：依赖基类的成员，非限定查找找不到
};
```

¶3 的注说明了它的问题：如果新迭代器本身是类模板，这些别名在类模板内部不可见，只对使用者可见。基类依赖模板形参，其中的名字不会被非限定查找找到（[[temp.dep]]）。于是在类内部还得再写一遍 `using value_type = ...;`，基类省下的代码又被抵消了。此外，五个模板形参的顺序难记，`Distance` 排在 `Pointer` 前面，写错一个位置就会悄悄定义出错误的别名。

libc++ 从 `-std=c++17` 起警告。替代做法是在迭代器类里直接写出这些别名；C++20 起还应加上 `iterator_concept`。

## D.19 `move_iterator::operator->` {#depr.move.iter.elem}

```cpp
#include <iterator>
#include <string>
void f(std::string* p) {
  std::move_iterator<std::string*> m(p);
  auto n1 = m->size();          // 弃用
  auto n2 = (*m).size();        // *m 是 std::string&&
  auto n3 = m.base()->size();   // 明确经由底层迭代器
}
```

¶1–¶2 `move_iterator<Iterator>` 额外有成员 `constexpr pointer operator->() const;`，返回底层迭代器 `current`。

`move_iterator` 的作用是让解引用得到右值：`*m` 是 `std::move(*current)`。而 `m->x` 经由底层迭代器访问成员，得到的是左值。同一个迭代器上，`(*m).x` 和 `m->x` 的值类别不同，违背了 `->` 与 `(*).` 等价的惯例，所以 C++20 弃用了它。libc++ 从 `-std=c++20` 起警告。

## 小结

| 条款 | 特性 | 替代 | libc++ 警告 |
|---|---|---|---|
| D.10 | `has_denorm`、`has_denorm_loss` | `denorm_min()`，运行时检测 | C++23 起 |
| D.11 | `*_HAS_SUBNORM`、`DECIMAL_DIG` 等宏 | `DBL_DECIMAL_DIG` 等 | 无 |
| D.12 | STREAMS 错误码 | 平台头文件 | 仅 `errc` 枚举项，所有模式 |
| D.13 | `is_trivial`、`is_pod`、`aligned_storage`、`aligned_union` | 精确的类型特征，`alignas` 数组 | `is_pod` C++20 起，`aligned_*` C++23 起，`is_trivial` C++26 |
| D.14 | `std::rel_ops` | `operator==` 加 `operator<=>` | C++20 起（`!=` 因改写候选而不触发） |
| D.15、D.16 | `volatile` 的 `tuple`、`variant` 特化 | `remove_volatile_t` | 无 |
| D.17 | `vector<bool>` 的静态 `swap` | 经 ADL 调用 `swap` | 无 |
| D.18 | `std::iterator` | 直接写类型别名 | C++17 起 |
| D.19 | `move_iterator::operator->` | `(*m).x` 或 `m.base()->x` | C++20 起 |
