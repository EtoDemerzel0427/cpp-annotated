---
title: expected 的 void 偏特化
summary: expected<void, E> 只表示成功或一个错误：它怎样用一个受约束的偏特化覆盖各种 cv void，为什么它的赋值不需要 reinit-expected，以及 operator*、value() 和单子操作在没有值时的写法。
status: draft
covers: *
papers: P0323, P2505
related: expected, expected.expected, optional.optional, structure.specifications, temp.spec.partial
tags: 标准库, expected, void, 错误处理
updated: 2026-10-19
---

!!! tldr
    - `expected<void, E>` 用于没有结果、只可能失败的操作，`return {};` 表示成功。
    - 它是一个带 `requires is_void_v<T>` 的偏特化，一并覆盖 `void`、`const void` 等四种类型。
    - 值一侧没有对象，在成功和错误之间切换时没有东西需要备份，所以赋值对 `E` 没有不抛异常的移动要求。
    - `*e` 和 `e.value()` 都返回 `void`：前者仍有加固前置条件，可以当作有值的断言；后者在出错时抛出 `bad_expected_access<E>`。
    - `and_then` 和 `transform` 的函数不接受实参；`expected<void, E>` 只能与 `void` 的 expected 或 `unexpected` 比较。

```cpp run ok
#include <cassert>
#include <expected>
#include <string>

std::expected<void, std::string> open_file(bool ok) {
  if (!ok) return std::unexpected("cannot open");
  return {};                        // 成功
}

int main() {
  // and_then 和 transform 的 f 不接受实参
  auto r = open_file(true)
      .and_then([] { return std::expected<int, std::string>(42); })
      .transform([](int n) { return n + 1; });
  assert(r == 43);

  auto e = open_file(false);
  assert(!e && e.error() == "cannot open");

  try {
    e.value();                      // 返回 void，但会抛出
    assert(false);
  } catch (const std::bad_expected_access<std::string>& x) {
    assert(x.error() == "cannot open");
  }

  e.emplace();                      // 丢弃错误，变成成功
  assert(e.has_value());
  *e;                               // OK：operator* 返回 void
}
```

写文件、发送消息、校验输入这类操作没有结果，只需要说明成功了，或者因为某个 `E` 失败了。主模板不能用于 `void`：它有一个 `remove_cv_t<T>` 类型的成员，`operator*` 返回 `T&`，这些对 `void` 都不成立。所以 [expected.void] 给出了一个完整的偏特化。主模板的规则和术语（*Constraints*、*Mandates*、加固前置条件、*reinit-expected*）见 [[expected.expected]]，总览见 [[expected]]。

## 一个偏特化覆盖四种 void [expected.void.general]

```cpp
template<class T, class E> requires is_void_v<T>
class expected<T, E> {
public:
  using value_type = T;
  using error_type = E;
  using unexpected_type = unexpected<E>;
  template<class U> using rebind = expected<U, error_type>;
  // …
private:
  bool has_val;       // exposition only
  union {
    E unex;           // exposition only
  };
};
```

这个偏特化的模板实参列表 `<T, E>` 与主模板相同，它比主模板更特化，靠的是约束 `is_void_v<T>`（[[temp.spec.partial]]）。`is_void_v` 对 `void`、`const void`、`volatile void`、`const volatile void` 都为真，所以一个偏特化就覆盖了四种情况，不必写四个。`value_type` 保留 `T` 原样，`expected<const void, E>::value_type` 是 `const void`。

¶1 主模板说对象含有（contains）一个 `T` 类型的值，这里改成表示（represents）一个 `T` 类型的值：`void` 没有对象可以容纳，成功只是一个状态。错误仍然是嵌套在对象中的一个 `E`。

¶2 `E` 必须是 `unexpected` 的合法模板实参（见 [[expected]]），否则实例化定义是非良构的。¶3 `E` 必须满足 *Cpp17Destructible*。

本机 libc++ 中 `sizeof(std::expected<void, int>)` 等于 `2 * sizeof(int)`：一个 `int`，一个 `bool` 标志，加上填充。

## 构造与析构 [expected.void.cons]

构造函数与主模板基本一致，区别都来自值一侧没有对象：

- ¶1 默认构造函数是 `noexcept` 的，构造后表示成功。所以在返回 `expected<void, E>` 的函数里，`return {};` 就是返回成功。
- ¶2–¶11 复制构造和移动构造只在 `rhs` 是错误时构造 *unex*。是否弃置、是否平凡、是否 noexcept，都只取决于 `E`。
- ¶12–¶16 从 `expected<U, G>` 转换时，¶13.1 要求 `U` 也是 `void`，也就是只能从另一个 `void` 的 expected 转换。其余约束与主模板错误一侧的检查相同；是否 explicit 只取决于 `G` 能否隐式转换为 `E`。
- ¶17–¶21 从 `unexpected<G>` 构造错误，与主模板相同。
- ¶22 `expected(in_place_t)` 不接受其他实参，是 explicit 且 `noexcept` 的，构造后表示成功。
- ¶23–¶30 `expected(unexpect_t, args...)` 原地构造错误。

[expected.void.dtor] 析构函数在对象是错误时销毁 *unex*；`E` 可平凡析构时，析构函数是平凡的。

## 赋值不需要 *reinit-expected* [expected.void.assign]

<div class="compare" markdown="1">

```cpp run ok
#include <expected>
#include <type_traits>
struct Throwy {   // 移动构造可能抛
  Throwy() = default;
  Throwy(const Throwy&) {}
  Throwy(Throwy&&) noexcept(false) {}
  Throwy& operator=(const Throwy&)
    = default;
  Throwy& operator=(Throwy&&) = default;
};
static_assert(std::is_copy_assignable_v<
  std::expected<void, Throwy>>);
int main() {}
```

```cpp run ok
#include <expected>
#include <type_traits>
struct Throwy {   // 同左
  Throwy() = default;
  Throwy(const Throwy&) {}
  Throwy(Throwy&&) noexcept(false) {}
  Throwy& operator=(const Throwy&)
    = default;
  Throwy& operator=(Throwy&&) = default;
};
static_assert(!std::is_copy_assignable_v<
  std::expected<Throwy, Throwy>>);
int main() {}
```

</div>

主模板在 `T`、`E` 的移动构造都可能抛出时禁止赋值，`void` 偏特化没有这个限制。原因要看 ¶1 复制赋值的四种情况：

- ¶1.1 两边都表示成功：什么也不做。
- ¶1.2 自己成功，`rhs` 是错误：用 `rhs.unex` 构造 *unex*，然后置 `has_val = false`。
- ¶1.3 自己是错误，`rhs` 成功：销毁 *unex*，置 `has_val = true`。
- ¶1.4 两边都是错误：`unex = rhs.error()`。

¶1.2 中构造 *unex* 可能抛出异常，但在此之前没有销毁任何东西，标志也还没改，对象仍然表示成功。¶1.3 只做析构，而析构不会抛出。所以状态切换天然具有强异常保证，不需要主模板那样先备份再恢复。

¶3 因此复制赋值只要求 `E` 可复制赋值、可复制构造，否则被定义为弃置。¶4 `E` 可平凡复制构造、复制赋值和析构时，它是平凡的。¶5–¶9 移动赋值与之对称，约束是 `E` 可移动构造、可移动赋值，noexcept 等价于 `E` 能不抛异常地移动构造和移动赋值。

¶10–¶13 从 `unexpected<G>` 赋值同样简单：对象成功时构造 *unex* 并置标志为假，否则对 *unex* 赋值。

¶14 `emplace()` 没有参数，返回 `void`，是 `noexcept` 的：对象是错误时销毁 *unex*，然后表示成功。

!!! impl "libc++ 的赋值还不是平凡的"
    与主模板一样，截至 Clang 23 自带的 libc++，`expected<void, E>` 的复制赋值和移动赋值总是用户提供的，所以 `std::is_trivially_copyable_v<std::expected<void, int>>` 为假，而 `is_trivially_copy_constructible_v` 为真。

## swap [expected.void.swap]

¶1 `swap` 要求 `E` 可交换、可移动构造。¶2 两边都成功时什么也不做；都是错误时交换 *unex*；自己是错误、对方成功时调用 `rhs.swap(*this)`。剩下的一种情况，自己成功、对方是错误：

```cpp
construct_at(addressof(unex), std::move(rhs.unex));
destroy_at(addressof(rhs.unex));
has_val = false;
rhs.has_val = true;
```

如果移动构造抛出异常，`rhs.unex` 还没有被销毁，两个标志也都没改，同样不需要备份。¶4 noexcept 等价于 `E` 能不抛异常地移动构造和交换。

## 观察器 [expected.void.obs]

| 成员 | 规则 |
|---|---|
| `operator bool`、`has_value()` | 返回 *has_val*（¶1） |
| `has_error()` | 返回 `!has_value()`（¶2）；C++23 之后加入，本机 libc++ 尚未提供 |
| `void operator*() const noexcept` | 加固前置条件：`has_value()` 为真（¶3） |
| `void value() const &` | *Mandates* `E` 可复制构造；出错时抛出 `bad_expected_access(error())`（¶4–5） |
| `void value() &&` | *Mandates* `E` 可复制构造且可移动构造；出错时抛出 `bad_expected_access(std::move(error()))`（¶6–7） |
| `error()` 的四个重载 | 加固前置条件：`has_value()` 为假（¶8–11） |
| `error_or(G&&)` | 与主模板相同（¶12–15） |

`operator->` 和 `value_or` 对 `void` 没有意义，所以没有提供。

`operator*` 什么也不返回，却仍有加固前置条件。它的存在让泛型代码在 `T` 可能是 `void` 时也能统一写 `*e`。在加固实现中，对错误状态的 `expected<void, E>` 求值 `*e` 会终止程序，相当于一个开销很小的断言。非加固实现中违反它是 {{ub}}，即使这个函数什么也不做。

`value()` 返回 `void`，但会抛出异常。`e.value();` 的意思是成功就继续，失败就把错误作为异常抛出，适合在 expected 风格的代码与异常风格的代码之间衔接。

## 单子操作 [expected.void.monadic]

与主模板相比，唯一的本质区别是值一侧没有东西可传，`and_then` 和 `transform` 的 `f` 不接受实参：

- ¶1–¶8 `and_then`：`U = remove_cvref_t<invoke_result_t<F>>`，必须是错误类型为 `E` 的 expected。成功时返回 `invoke(f)`，否则返回 `U(unexpect, error())`。
- ¶9–¶14 `or_else`：`f` 接受错误，返回类型 `G` 必须是值类型为 `T` 的 expected。这里没有 *Constraints*，因为值一侧没有东西要传进结果；成功时直接返回 `G()`。
- ¶15–¶22 `transform`：`U = remove_cv_t<invoke_result_t<F>>`。成功且 `U` 不是 `void` 时，结果的值用 `invoke(f)` 直接初始化；`U` 是 `void` 时调用 `f`，返回成功的 `expected<U, E>`。
- ¶23–¶28 `transform_error`：成功时返回 `expected<T, G>()`，否则用 `invoke(f, error())` 初始化新的错误。

通过 `transform`，`void` 和非 `void` 的 expected 可以互相转换：`expected<void, E>` 经 `transform([] { return 42; })` 得到 `expected<int, E>`，`expected<int, E>` 经 `transform([](int) {})` 得到 `expected<void, E>`。

## 相等比较 [expected.void.eq]

¶1–¶2 与另一个 `expected<T2, E2>` 比较时要求 `T2` 也是 `void`：状态不同就不相等，都成功就相等，都是错误时比较错误。¶3–¶4 与 `unexpected<E2>` 比较，与主模板相同。

没有与值比较的重载，因为没有值。主模板的同类运算符带 `requires (!is_void_v<T2>)`，这里带 `requires is_void_v<T2>`，两者互补，所以 `void` 和非 `void` 的 expected 不能相互比较：

```cpp run error
#include <expected>
bool f(std::expected<void, int> a,
       std::expected<int, int> b) {
  return a == b;   // error: 没有可用的 operator==
}
```

<details class="fine" markdown="1"><summary>其余条文</summary>

[expected.void.monadic] ¶2 在当前草案中写作 `is_constructible_v<E, decltype(error())>>`，多了一个 `>`。对照 ¶16 和主模板 [expected.object.monadic] ¶2，本意是 `is_constructible_v<E, decltype(error())>`。这是编辑性错误，不影响含义。

</details>

## 思考题

!!! question "思考题"
    `void` 偏特化的赋值不要求 `E` 能不抛异常地移动构造。能否据此说，`expected<void, E>` 的赋值对任意 `E` 都提供强异常保证？

<details markdown="1">
<summary>答案</summary>

对切换状态的赋值可以这样说：从成功变成错误只需构造 *unex*，失败时什么都没变；从错误变成成功只做析构。

但两边都是错误时（¶1.4），效果是 `unex = rhs.error()`，调用的是 `E` 自己的复制赋值。如果它只提供基本保证，`*this` 中的错误可能处于有效但未指明的状态。准确的说法是：*has_val* 不会因为异常而改变，状态切换具有强保证，同一状态内的赋值继承 `E` 的保证。主模板两边都有值的情况（[expected.object.assign] ¶2.1）也是这样。
</details>
