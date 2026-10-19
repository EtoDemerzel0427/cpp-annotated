---
title: 类模板 expected
summary: expected<T, E> 主模板：它怎样存放值或错误，各个构造函数如何区分两者，为什么切换值和错误的赋值能提供强异常保证，以及观察器、单子操作和相等比较的规则。
status: draft
covers: *
papers: P0323, P2505, P0848, P3471
related: expected, expected.void, optional.optional, variant.variant, class.union, class.prop, special, structure.specifications, except.throw
tags: 标准库, expected, 异常安全, 平凡性, 单子操作, 加固
updated: 2026-10-19
---

!!! tldr
    - `expected<T, E>` 永远恰好含有一个 `T` 或一个 `E`，没有空状态；默认构造得到的是值初始化的 `T`，也就是成功。
    - 用 `unexpected<X>` 包装的东西永远被当作错误，其余能构造 `T` 的东西被当作值。
    - 在值和错误之间切换的赋值提供强异常保证。为此 `T` 和 `E` 的移动构造如果都可能抛异常，赋值运算符就被定义为弃置；`emplace` 只接受不抛异常的构造。
    - `*e`、`e->`、`e.error()` 在状态不对时是 UB（加固实现中终止），`value()` 则抛出携带错误副本的 `bad_expected_access<E>`。
    - `and_then`、`or_else`、`transform`、`transform_error` 只改动一侧，另一侧原样传到结果里；`and_then` 不能改变错误类型。

`std::expected<T, E>` {{c++23}} 表示一个计算的结果：要么是 `T` 类型的值，要么是 `E` 类型的错误。总览、`unexpected<E>` 和 `bad_expected_access` 见 [[expected]]；`T` 为 `void` 的偏特化见 [[expected.void]]。

库条款用几个固定的小标题描述函数（[[structure.specifications]]）。*Constraints* 不满足时，函数不参与重载决议；*Mandates* 不满足时，程序非良构；*Hardened preconditions*（加固前置条件）被违反时，加固实现必须终止程序，其他实现中是 UB。

## 对象里有什么 [expected.object.general]

```cpp
template<class T, class E>
class expected {
public:
  using value_type = T;
  using error_type = E;
  using unexpected_type = unexpected<E>;
  template<class U> using rebind = expected<U, error_type>;
  // …
private:
  bool has_val;           // exposition only
  union {
    remove_cv_t<T> val;   // exposition only
    E unex;               // exposition only
  };
};
```

¶1 一个 `expected<T, E>` 对象含有一个 `T` 类型的值或一个 `E` 类型的值，这个值嵌套在 expected 对象之中（[[intro.object]]），不另外分配内存。成员 *has_val* 记录当前是哪一种。标准用联合体描述存储，这意味着两者共用同一块内存，任何时刻只有一个是活跃成员（[[class.union]]）。

`rebind<U>` 得到错误类型相同、值类型换成 `U` 的 expected，方便泛型代码书写单子操作的返回类型。

### 哪些类型可以用（¶2–3）

¶2 如果 `remove_cv_t<T>` 是 `void`，或者是完整的、非数组的对象类型，并且不是 `in_place_t`、`unexpect_t` 或 `unexpected` 的特化，`T` 就是 **expected 的合法值类型**（[[g:valid-value-type-for-expected]]）。用不合法的 `T` 实例化 `expected` 是非良构的。`E` 必须是 `unexpected` 的合法模板实参（见 [[expected]]），也就是非数组、非 cv 限定的对象类型，且不是 `unexpected` 的特化。

<div class="compare" markdown="1">

```cpp run ok
#include <expected>
std::expected<const int, int> a;
std::expected<void, int> b;
int main() {}
```

```cpp run error
#include <expected>
std::expected<int&, int> c;
// error: 引用不是对象类型
std::expected<int, const int> d;
// error: E 不能有 cv 限定
```

</div>

值一侧允许 cv 限定，错误一侧不允许。C++26 的 `optional<T&>` 有引用特化，`expected` 没有。值类型不能是 `unexpected<X>`，否则 `expected<unexpected<int>, int>` 从 `unexpected(1)` 构造时，就分不清那是值还是错误。

¶3 `T`（不是 `void` 时）和 `E` 都必须满足 *Cpp17Destructible*。

## 构造：值还是错误 [expected.object.cons]

```cpp run ok
#include <cassert>
#include <expected>
#include <optional>
#include <string>

std::expected<int, std::string> parse(bool good) {
  if (good) return 42;                       // 值
  return std::unexpected("bad input");       // 错误
}

int main() {
  std::optional<int> o;                // 空
  std::expected<int, std::string> e;   // 有值，*e == 0
  assert(!o && e && *e == 0);
  assert(parse(true) == 42);
  assert(parse(false).error() == "bad input");
}
```

### 默认构造得到成功（¶2–5）

¶2–¶4 默认构造函数要求 `T` 可默认构造，它值初始化 *val*，构造之后 `has_value()` 为真。这与 `optional` 相反：`optional` 默认为空，`expected` 没有空状态，只能默认为成功。把 `optional` 改写成 `expected` 时要注意这一点。

### 从一个值构造（¶23–26）

```cpp
template<class U = remove_cv_t<T>>
  constexpr explicit(!is_convertible_v<U, T>) expected(U&& v);
```

¶23 这个构造函数接受任何能构造 `T` 的实参，但排除了以下几种 `remove_cvref_t<U>`：`in_place_t`、`expected` 本身、`unexpect_t`、`unexpected` 的任何特化。最后一条（¶23.4）是区分值和错误的关键：`unexpected<X>` 永远不会被当作值。

¶23.6 处理 `T` 是 `bool` 的情况。`bool` 可以经由 `explicit operator bool` 从另一个 `expected` 直接初始化，如果不排除，`expected<bool, E> b(other)` 就可能把 `other` 的真假当作新的值。`optional` 有同样的条款（[[optional.optional]]）。

¶24 效果是用 `std::forward<U>(v)` 直接非列表初始化 *val*。只有 `U` 能隐式转换为 `T` 时，这个构造函数才不是 explicit 的，所以 `return 42;` 可以写在返回 `expected<int, E>` 的函数里。

### 从 `unexpected<G>` 构造错误（¶27–31）

```cpp
template<class G> constexpr explicit(!is_convertible_v<const G&, E>)
  expected(const unexpected<G>& e);
template<class G> constexpr explicit(!is_convertible_v<G, E>)
  expected(unexpected<G>&& e);
```

¶28–¶29 只要 `E` 能从 `G` 构造，就用 `e.error()` 直接非列表初始化 *unex*。上例中 `std::unexpected("bad input")` 的类型是 `unexpected<const char*>`，`const char*` 能隐式转换为 `std::string`，所以构造函数不是 explicit 的，可以直接 `return`。

### 原地构造（¶32–47）

`expected(in_place_t, args...)` 在 *val* 处直接构造值，`expected(unexpect_t, args...)` 在 *unex* 处直接构造错误，各有一个接受 `initializer_list` 的版本。它们都是 explicit 的，约束是相应的 `is_constructible_v`。

### 复制、移动和转换构造（¶6–22）

¶6–¶16 复制构造和移动构造按 `rhs` 的状态构造 *val* 或 *unex*。`T` 和 `E` 有一个不可复制构造，复制构造函数就被定义为弃置（¶9）；两者都可平凡复制构造时，它是平凡的（¶10）。移动构造的 noexcept 等价于两者都可以不抛异常地移动构造（¶15）；两者都可平凡移动构造时，它是平凡的（¶16）。

¶17–¶22 从 `expected<U, G>` 转换时，分别用 `U` 构造值、用 `G` 构造错误。只有两侧都能隐式转换，这个构造函数才不是 explicit 的（¶22）。

¶18 的约束中有两组是为了避免歧义。¶18.3 借用 [[optional.optional]] 定义的 *converts-from-any-cvref*：如果 `T` 能从整个 `expected<U, G>` 构造（`T` 不是 `bool` 时），就不做逐成员转换，交给 ¶23 把它整个当作值。¶18.4–¶18.7 是错误一侧的同类检查：如果 `unexpected<E>` 能从整个 `expected<U, G>` 构造，这个转换构造函数同样退出。

## 析构与平凡性 [expected.object.dtor]

¶1 析构函数销毁 *val* 或 *unex* 中活跃的那个。¶2 `T` 和 `E` 都可平凡析构时，析构函数是平凡的。

各个特殊成员的平凡条件汇总如下，`T` 和 `E` 都要满足：

| 特殊成员 | 平凡条件 | 出处 |
|---|---|---|
| 复制构造 | 可平凡复制构造 | [expected.object.cons] ¶10 |
| 移动构造 | 可平凡移动构造 | [expected.object.cons] ¶16 |
| 析构 | 可平凡析构 | [expected.object.dtor] ¶2 |
| 复制赋值 | 可平凡复制构造、复制赋值和析构 | [expected.object.assign] ¶5 |
| 移动赋值 | 可平凡移动构造、移动赋值和析构 | [expected.object.assign] ¶10 |

按 [[class.prop]]，这意味着 `expected<int, int>`、`expected<double, std::errc>` 这类类型应当是平凡可复制的，可以用 `memcpy` 复制。

!!! impl "libc++ 的赋值还不是平凡的"
    libc++ 用 C++20 的受约束特殊成员（[[P0848]]）实现条件平凡：同一个特殊成员声明多次，一个无约束的 `= delete`，一个约束为平凡时的 `= default`，一个约束为非平凡时的用户提供版本。

    但截至 Clang 23 自带的 libc++，复制赋值和移动赋值只有弃置和用户提供两个版本。本机测得 `expected<int, int>` 可平凡复制构造、可平凡析构，却不可平凡复制赋值，因此 `std::is_trivially_copyable_v<std::expected<int, int>>` 为假。草案 [expected.object.assign] ¶5、¶10 的要求尚未实现。

## 赋值：永远不为空 [expected.object.assign]

### 切换时的强异常保证

```cpp run ok
#include <cassert>
#include <expected>
#include <stdexcept>

struct Fragile {
  int v;
  Fragile(int n) : v(n) {
    if (n < 0) throw std::invalid_argument("neg");
  }
};

int main() {
  std::expected<Fragile, int> e =
      std::unexpected(7);
  try {
    e = -1;   // 构造 Fragile(-1) 时抛出
  } catch (const std::invalid_argument&) {}
  assert(!e.has_value() && e.error() == 7);

  e = 5;
  assert(e && e->v == 5);
}
```

`e` 原来含有错误 7，赋值要把它换成一个值。值和错误共用同一块存储，必须先销毁旧的错误才能在原处构造新的值。如果构造抛出异常，对象就既没有值也没有错误。

`optional` 遇到这种情况可以退回空状态，`variant` 会进入 `valueless_by_exception` 状态（[[variant.variant]]），`expected` 两者都没有。上面的程序在异常之后仍然保有原来的错误 7，这就是强异常保证：赋值要么成功，要么对象保持原样。

### *reinit-expected*（¶1）

¶1 标准用一个仅用于说明的函数模板 [[g:reinit-expected]] 描述这种切换。`newval` 是要构造的成员，`oldval` 是当前活跃的成员：

```cpp
template<class T, class U, class... Args>
constexpr void reinit-expected(T& newval, U& oldval, Args&&... args) {  // exposition only
  if constexpr (is_nothrow_constructible_v<T, Args...>) {
    destroy_at(addressof(oldval));
    construct_at(addressof(newval), std::forward<Args>(args)...);
  } else if constexpr (is_nothrow_move_constructible_v<T>) {
    T tmp(std::forward<Args>(args)...);
    destroy_at(addressof(oldval));
    construct_at(addressof(newval), std::move(tmp));
  } else {
    U tmp(std::move(oldval));
    destroy_at(addressof(oldval));
    try {
      construct_at(addressof(newval), std::forward<Args>(args)...);
    } catch (...) {
      construct_at(addressof(oldval), std::move(tmp));
      throw;
    }
  }
}
```

三个分支用不同的办法保证销毁旧对象之后不会出现异常：

1. 新对象能从实参不抛异常地构造：直接销毁旧对象，再构造新对象。
2. 新对象的类型能不抛异常地移动构造：先在局部变量里构造新对象。这一步可能抛出，但此时旧对象完好。然后销毁旧对象，把局部变量移动进来，这一步不会抛出。上面的 `Fragile` 走的就是这一支。
3. 两者都不行：先把旧对象移动到局部变量里备份，销毁它，再尝试构造新对象。如果抛出异常，把备份移回原处，再重新抛出。这要求旧对象的类型能不抛异常地移动构造，否则恢复时也可能失败。

第 3 支的前提由赋值运算符的弃置条件保证：

!!! std
    This operator is defined as deleted unless: … `is_nothrow_move_constructible_v<T> || is_nothrow_move_constructible_v<E>` is `true`.

这是复制赋值的 ¶4.5，移动赋值的 ¶6.5 有相同的约束。只要 `T`、`E` 中有一个能不抛异常地移动构造，两个方向的切换就都有安全的分支可走（思考题 1 给出了推理）。两者都可能抛出时，赋值在编译期就不可用：

```cpp run ok
#include <expected>
#include <type_traits>

struct Throwy {             // 移动构造可能抛
  Throwy() = default;
  Throwy(const Throwy&) {}
  Throwy(Throwy&&) noexcept(false) {}
  Throwy& operator=(const Throwy&) = default;
  Throwy& operator=(Throwy&&) = default;
};

using A = std::expected<Throwy, int>;
using B = std::expected<Throwy, Throwy>;
static_assert(std::is_copy_assignable_v<A>);
static_assert(!std::is_copy_assignable_v<B>);
static_assert(!std::is_move_assignable_v<B>);
static_assert(std::is_copy_constructible_v<B>);  // 构造不受影响
int main() {}
```

`variant` 在同样的情况下允许赋值，失败时变成无值；`expected` 选择在编译期拒绝，以维持永远有一个值或错误。

### 复制赋值和移动赋值（¶2–10）

¶2 复制赋值分四种情况：

- ¶2.1 两边都有值：`val = *rhs`，异常保证取决于 `T` 的赋值；
- ¶2.2 自己有值，`rhs` 是错误：*reinit-expected*`(unex, val, rhs.error())`；
- ¶2.3 自己是错误，`rhs` 有值：*reinit-expected*`(val, unex, *rhs)`；
- ¶2.4 两边都是错误：`unex = rhs.error()`。

最后，如果没有抛出异常，才执行 `has_val = rhs.has_value()`。标志放在最后更新，异常发生时它仍然描述原来的状态。

¶4 除了 ¶4.5，复制赋值还要求 `T` 和 `E` 都可复制赋值、可复制构造，否则被定义为弃置。¶6–¶7 移动赋值以同样的方式工作，条件写成 *Constraints*。¶9 移动赋值的 noexcept 等价于 `T`、`E` 都能不抛异常地移动赋值和移动构造。

### 从值或 `unexpected` 赋值（¶11–17）

¶11 `operator=(U&& v)` 的约束与 ¶23 的构造函数类似：`U` 不是 `expected` 本身，也不是 `unexpected` 的特化，`T` 能从 `U` 构造和赋值。另外还有一条：

```cpp
is_nothrow_constructible_v<T, U> || is_nothrow_move_constructible_v<T> ||
is_nothrow_move_constructible_v<E>   // ¶11.5
```

三项分别是 *reinit-expected* 三个分支的前提，满足任意一项，切换就有安全的路径。¶12 如果当前有值，直接 `val = std::forward<U>(v)`；否则调用 *reinit-expected*`(val, unex, …)`，再置 `has_val = true`。

¶14–¶17 `operator=(unexpected<G>)` 与之对称，¶15.3 把第一项换成 `is_nothrow_constructible_v<E, GF>`。

`expected` 没有 `optional` 那样的重置操作。`e = {}` 匹配的是 `operator=(U&&)`，`U` 取默认实参 `remove_cv_t<T>`，结果是让 `e` 含有值初始化的 `T`。

### `emplace` 只接受不抛异常的构造（¶18–21）

```cpp
template<class... Args> constexpr T& emplace(Args&&... args) noexcept;
```

¶18–¶19 `emplace` 要求 `is_nothrow_constructible_v<T, Args...>`。它销毁当前的值或错误，然后在原处构造新值。

`optional::emplace` 允许构造抛出异常，失败后对象变成空。`expected::emplace` 无处可退；如果像 *reinit-expected* 那样先备份，又失去了原地构造的意义。所以它只允许不抛异常的构造，其余情况用赋值 `e = T(args...)`。

```cpp run error
#include <expected>
struct Fragile { Fragile(int); };   // 构造可能抛
int main() {
  std::expected<Fragile, int> e =
      std::unexpected(7);
  e.emplace(-1);  // error: 不满足 nothrow 构造
}
```

## swap [expected.object.swap]

¶1 成员 `swap` 要求 `T`、`E` 都可交换、都可移动构造，并且至少一个能不抛异常地移动构造，理由与赋值相同。

¶2 两边都有值时交换 *val*，都是错误时交换 *unex*。一边有值、一边是错误时，标准给出了一段与 *reinit-expected* 思路相同的代码：如果 `E` 能不抛异常地移动，先把对方的错误移到局部变量里；否则先把自己的值移到局部变量里。出错时用备份恢复，然后重新抛出。

¶4 noexcept 等价于 `T`、`E` 都能不抛异常地移动构造和交换。

## 读取值和错误 [expected.object.obs]

### 解引用和 `error()`（¶1–8、¶15–18）

`operator->`、`operator*` 的加固前置条件是 `has_value()` 为真（¶1、¶3、¶5）；`error()` 的加固前置条件是 `has_value()` 为假（¶15、¶17）。在含有值的 expected 上调用 `error()`，读的是联合体中不活跃的成员，与在错误上解引用一样危险。加固实现中这些违反会终止程序，其他实现中是 {{ub}}（[[P3471]]）。

¶7 `operator bool` 和 `has_value()` 返回 *has_val*。¶8 `has_error()` 返回 `!has_value()`。这是 C++23 之后才加入草案的成员，截至写作时本机 Clang 23 自带的 libc++ 还没有提供。

### `value()` 抛出携带错误的异常（¶9–14）

```cpp run ok
#include <expected>
#include <cstdio>
#include <string>

int main() {
  std::expected<int, std::string> e =
      std::unexpected("not found");
  try {
    std::printf("%d\n", e.value());
  } catch (const std::bad_expected_access<std::string>& x) {
    std::printf("error: %s\n", x.error().c_str());
  }
}
```

¶10–¶11 有值时 `value()` 返回 *val*，否则抛出 `bad_expected_access(as_const(error()))`。上面的程序输出 `error: not found`。

¶9 左值版本的 *Mandates* 要求 `E` 可复制构造：异常对象里装着一个 `E` 的副本，抛出的异常对象必须可复制构造（[[except.throw]]），而左值 `value()` 不能把错误从 `*this` 里移走。¶12–¶14 右值版本抛出 `bad_expected_access(std::move(error()))`，除可复制构造外还要求 `E` 能从 `std::move(error())` 构造。

所以只能移动的错误类型可以用于 `expected`，但不能调用 `value()`：

```cpp run error
#include <expected>
#include <memory>
int main() {
  std::expected<int, std::unique_ptr<int>> e = 1;
  int a = *e;          // OK
  int b = e.value();   // error: E 不可复制（Mandates）
  (void)a; (void)b;
}
```

### `value_or` 和 `error_or`（¶19–26）

¶19–¶20 `value_or(v)` 有值时返回值的副本，否则返回 `static_cast<T>(std::forward<U>(v))`。¶23–¶24 `error_or(e)` 是它的镜像：有错误时返回错误的副本，有值时返回 `e`。两者的条件都是 *Mandates*：结果类型可复制构造（右值版本为可移动构造），实参可隐式转换为结果类型。

`error_or` 适合把 expected 转成状态码，例如 `return r.error_or(std::errc{});`，成功时返回表示无错误的值。

## 单子操作 [expected.object.monadic]

```cpp run ok
#include <cassert>
#include <expected>
#include <string>
#include <type_traits>

enum class Err { empty, too_big };

std::expected<int, Err> length(std::string s) {
  if (s.empty()) return std::unexpected(Err::empty);
  return static_cast<int>(s.size());
}
std::expected<int, Err> small(int n) {
  if (n > 3) return std::unexpected(Err::too_big);
  return n;
}

int main() {
  // and_then：f 返回 expected<_, Err>；transform：f 返回普通值
  auto r = length("ab").and_then(small)
                       .transform([](int n) { return n * 10; });
  assert(r == 20);

  auto e = length("abcdef").and_then(small);
  assert(e.error() == Err::too_big);

  // transform_error：换错误类型
  std::expected<int, std::string> msg = e.transform_error([](Err x) {
    return std::string(x == Err::empty ? "empty" : "too big");
  });
  assert(msg.error() == "too big");

  // or_else：从错误中恢复
  auto ok = e.or_else([](Err) { return std::expected<int, Err>(0); });
  assert(ok == 0);

  // transform 的 f 返回 void，得到 expected<void, Err>
  auto v = r.transform([](int) {});
  static_assert(std::is_same_v<decltype(v), std::expected<void, Err>>);

  assert(e.value_or(-1) == -1);
  assert(e.error_or(Err::empty) == Err::too_big);
  assert(r.error_or(Err::empty) == Err::empty);
}
```

[[P2505]] 加入了四个单子操作，每个都有 `&`、`const &`、`&&`、`const &&` 四个重载。每个操作把一侧交给 `f`，另一侧原样放进结果：

| 操作 | `f` 处理 | 原样传递 | `f` 的返回值 | 结果类型 |
|---|---|---|---|---|
| `and_then` | 值 | 错误 | `expected<U, E>`，错误类型必须是 `E` | `f` 的返回类型 |
| `or_else` | 错误 | 值 | `expected<T, G>`，值类型必须是 `T` | `f` 的返回类型 |
| `transform` | 值 | 错误 | 任意合法值类型 `U`，可以是 `void` | `expected<U, E>` |
| `transform_error` | 错误 | 值 | `unexpected` 的合法实参 `G` | `expected<T, G>` |

条文对两侧的要求用了不同的小标题。原样传递的一侧写成 *Constraints*，例如 `and_then` 的 ¶2 要求 `E` 能从 `error()` 构造；对 `f` 返回值的要求写成 *Mandates*，例如 ¶3 要求返回类型是 `expected` 的特化且错误类型就是 `E`。

为什么传递的一侧用 *Constraints*？设 `E` 只能移动。在左值 `e` 上调用 `and_then`，`&` 重载需要把 `error()` 复制到结果里，做不到。写成 *Constraints* 后这个重载退出重载决议，`e.and_then(f)` 报出没有匹配函数的错误，`std::move(e).and_then(f)` 则可以选中 `&&` 重载正常工作。

几个细节：

- `and_then` 不能改变错误类型，`or_else` 不能改变值类型。需要改变时先用 `transform_error` 或 `transform` 转换。
- ¶19–¶20 `transform` 的 `f` 返回 `void` 时，先调用 `f`，再返回一个有值的 `expected<void, E>`。
- ¶20.2、¶28 `transform` 和 `transform_error` 用 `f` 的调用结果直接非列表初始化结果中的成员，不经过临时对象，所以结果类型不必可移动。

## 相等比较 [expected.object.eq]

三个比较运算符都是隐藏友元，条件都写成 *Constraints*：

- ¶1–¶2 与另一个 `expected<T2, E2>` 比较（`T2` 不能是 `void`）：状态不同就不相等；都有值时比较值，都是错误时比较错误。
- ¶3–¶4 与一个值 `v` 比较（`T2` 不能是 `expected` 的特化）：有值时返回 `*x == v`，否则为假。
- ¶5–¶6 与 `unexpected<E2>` 比较：是错误时比较错误，否则为假。

没有 `<` 和 `<=>`，成功和失败之间没有自然的顺序。`!=` 由 C++20 的重写规则得到（[[over.match.oper]]）。`expected` 的比较用 *Constraints*，`unexpected` 自己的 `operator==` 用 *Mandates*（见 [[expected]]），前者在 `requires` 表达式中可以被检测出来。

## 常见误解

!!! pitfall "默认构造的 expected 表示尚未赋值"
    `std::expected<int, E> e;` 含有值 0。它表示成功，不是占位状态。

!!! pitfall "`e = {}` 会清空 expected"
    `expected` 没有空状态。`e = {}` 让 `e` 含有值初始化的 `T`。

!!! pitfall "只能移动的错误类型也能用 `value()`"
    `value()` 要把错误复制进异常对象，`E` 不可复制构造时调用它是非良构的。用 `has_value()` 加 `*e` 或 `error()` 代替。

## 思考题

!!! question "思考题 1"
    [expected.object.assign] ¶4.5 只要求 `T` 或 `E` 有一个能不抛异常地移动构造，而不是两者都要。为什么这就够了？请分别考虑从错误切换到值和从值切换到错误。

<details markdown="1">
<summary>答案</summary>

设 `T` 能不抛异常地移动，`E` 不能。

从错误切换到值，新对象是 `T`。如果 `T` 能从实参不抛异常地构造，走第 1 支；否则 `T` 能不抛异常地移动，走第 2 支。两种都安全。

从值切换到错误，新对象是 `E`。如果 `E` 能从实参不抛异常地构造，走第 1 支；否则 `E` 不能不抛异常地移动，只能走第 3 支，备份的是旧对象 `T`。`T` 能不抛异常地移动，恢复不会失败。

反过来设 `E` 能而 `T` 不能，推理对称。只有两者都不能时，某个方向会落到第 3 支，而恢复时的移动可能再次抛出，所以只排除这一种组合。
</details>

!!! question "思考题 2"
    如果允许 `expected::emplace` 的构造抛出异常，它的效果应当怎样描述才能保持永远有值或错误？代价是什么？

<details markdown="1">
<summary>答案</summary>

只能照搬 *reinit-expected*：要么先在局部变量里构造新值再移动进来，要么先备份旧对象，构造失败时恢复。前者多一次移动，而且对不可移动的 `T` 做不到；后者也多一次移动，并要求旧对象的类型能不抛异常地移动。无论哪种，`emplace` 都不再是零额外开销的原地构造。标准因此把 `emplace` 限定为不抛异常的构造，其余情况交给赋值运算符。
</details>
