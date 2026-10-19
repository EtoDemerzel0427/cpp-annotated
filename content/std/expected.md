---
title: expected 对象
summary: expected<T, E> 表示一个结果或一个错误；本页讲它的设计取舍、包装错误值的 unexpected<E>、标签 unexpect，以及访问失败时抛出的 bad_expected_access。
status: draft
covers: expected.general, expected.syn, expected.unexpected, expected.un.general, expected.un.cons, expected.un.obs, expected.un.swap, expected.un.eq, expected.bad, expected.bad.void
papers: P0323R12, P2505R5
related: expected.expected, expected.void, optional, variant, syserr, except, except.throw, structure.specifications
tags: 标准库, expected, 错误处理, 词汇类型
updated: 2026-10-19
---

!!! tldr
    - `std::expected<T, E>` {{c++23}} 持有一个 `T` 类型的结果或一个 `E` 类型的错误，没有第三种状态；接口偏向 `T` 一侧。
    - 返回错误必须写 `std::unexpected(e)` 或使用 `unexpect` 标签，`E` 类型的值不会隐式变成错误，即使 `T` 和 `E` 是同一个类型也不会混淆。
    - `unexpected<E>` 的 `E` 必须是对象类型，并且不能是数组、不能带 cv 限定、不能本身是 `unexpected` 的特化。
    - `value()` 在没有值时抛 `bad_expected_access<E>`，异常对象里带着错误值；所有这类异常都能用 `bad_expected_access<void>` 的引用接住。

主模板的成员见 [[expected.expected]]，`T` 为 `void` 时的偏特化见 [[expected.void]]。

## 结果或错误

```cpp run title="parse.cpp" ok
#include <cassert>
#include <charconv>
#include <expected>
#include <string_view>
#include <system_error>

std::expected<int, std::errc> parse(std::string_view s) {
  int v{};
  auto [p, ec] = std::from_chars(s.data(), s.data() + s.size(), v);
  if (ec != std::errc{}) return std::unexpected(ec);
  if (p != s.data() + s.size())
    return std::unexpected(std::errc::invalid_argument);
  return v;
}

int main() {
  auto ok = parse("42");
  assert(ok && *ok == 42);

  auto bad = parse("4x");
  assert(!bad && bad.error() == std::errc::invalid_argument);
  assert(bad == std::unexpected(std::errc::invalid_argument));

  try {
    (void)bad.value();
  } catch (const std::bad_expected_access<std::errc>& e) {
    assert(e.error() == std::errc::invalid_argument);
  }
}
```

¶1 [expected.general] 只有一句定义：`expected<T, E>` 对象持有一个 `T` 类型的对象或一个 `E` 类型的对象，并管理所含对象的生命周期。

它可以看作 `optional<T>`（[[optional]]）的推广：`optional` 只能说没有值，`expected` 还能说为什么没有值。和 `optional` 不同，`expected` 总是含有一个对象，不是值就是错误，没有空的状态。

它和 `variant<T, E>` 的区别在于不对称。`T` 是期望的一侧，`E` 是意外的一侧，接口都偏向 `T`：`*e`、`e->`、`e.value()` 访问值，`if (e)` 检查是否成功，访问错误必须明确写 `e.error()`。

### 什么时候用 expected

C++ 处理可预期的失败（解析失败、文件不存在、网络超时）历来有两种手段：

| | 异常 | 错误码 | `expected<T, E>` |
|---|---|---|---|
| 失败信息 | 任意类型 | 通常只是整数或枚举 | 任意类型 `E` |
| 成功的值 | 正常返回 | 用输出参数，或与错误码挤在一个返回值里 | 正常返回 |
| 能否被忽略 | 不处理就继续传播 | 很容易被忽略 | 不检查就取值，`value()` 会抛异常 |
| 控制流 | 看不见，任何调用都可能跳出 | 显式 | 显式，也可以用单子操作串联 |
| 函数签名是否表明会失败 | 否 | 部分 | 是，`E` 写在返回类型里 |
| 禁用异常时 | 不可用 | 可用 | 除 `value()` 外都可用 |

`expected` 适合失败本身就是正常结果、调用者通常就地处理的场景：解析、校验、查找、I/O。不该发生、发生了也无法就地恢复的错误（违反不变式、内存耗尽），更适合用异常或契约断言。`E` 常用 `std::errc` 或 `std::error_code`（[[syserr]]）、自定义枚举，或者携带上下文的结构体。

### 为什么错误要包一层

`return v;` 构造值，`return std::unexpected(ec);` 构造错误。为什么不让 `E` 直接隐式转换为 `expected`？因为 `T` 和 `E` 可能是同一类型，或者可以互相转换：在 `expected<int, int> f() { return 0; }` 里，`0` 是结果还是错误码？`unexpected` 这层包装让意图体现在类型上。

另一种写法是在构造时传标签。[expected.syn] 定义了：

```cpp
struct unexpect_t { explicit unexpect_t() = default; };
inline constexpr unexpect_t unexpect{};
```

`expected<T, E>(std::unexpect, args...)` 用 `args...` 原地构造错误，就像 `std::in_place` 用于原地构造值。默认构造函数是 `explicit` 的，这是标准库标签类型的通用写法（`in_place_t`、`allocator_arg_t` 也一样）：`{}` 不能复制列表初始化成 `unexpect_t`，所以 `e = {}`、`f({})` 不会意外匹配到以 `unexpect_t` 为形参的重载。

概要还声明了主模板和一个偏特化 `template<class T, class E> requires is_void_v<T> class expected<T, E>;`。用一个受约束的偏特化，就同时覆盖了 `void`、`const void`、`volatile void`、`const volatile void` 四种情况。

## unexpected：错误值的包装（[expected.unexpected]）

### 哪些类型可以作 E

```cpp run title="bad_unexpected.cpp" error
#include <expected>
auto a = sizeof(std::unexpected<const int>);  // error: cv 限定
auto b = sizeof(std::unexpected<int[2]>);     // error: 数组
auto c = sizeof(std::unexpected<std::unexpected<int>>);  // error
auto d = sizeof(std::unexpected<int&>);       // error: 非对象类型
int main() {}
```

¶2 [expected.un.general] 规定，用非对象类型、数组类型、`unexpected` 的特化或 cv 限定类型实例化 `unexpected` 的定义，程序非良构。满足这些条件的类型叫作 `unexpected` 的合法模板实参（[[g:valid-unexpected-argument]]），[[expected.expected]] 对 `E` 的要求直接引用这个概念。逐项看理由：

- 非对象类型（引用、函数、`void`）：`unexpected` 要按值存放错误，`expected<T, E&>` 不被支持，错误一侧总是按值持有。
- 数组：不能复制初始化，也不能赋值。
- `unexpected` 的特化：`unexpected<unexpected<E>>` 没有意义，还会让 `expected(const unexpected<G>&)` 这类构造函数的推导变得含糊。禁止嵌套，"`unexpected<X>` 就是错误值 `X`"这个约定才始终成立。
- cv 限定：`unexpected<const E>` 有一个 const 成员，复制赋值被删除，还会连带 `expected` 的赋值也不可用。而且推导指引 `unexpected(E) -> unexpected<E>` 按值推导，本来就推导不出 cv 类型。

措辞是实例化定义时才非良构。只是写出 `unexpected<const int>`（例如作函数声明的返回类型）不会出错，需要完整类型时（定义变量、`sizeof`）才报错。libc++ 在类体里用 `static_assert` 实现，触发时机恰好是类模板的定义被实例化的时候。

### 构造

`unexpected` 没有默认构造函数，错误必须有内容。复制、移动构造和赋值都是 `= default`。另外三个构造函数全部是 `explicit` 的：

- ¶1 [expected.un.cons] `template<class Err = E> explicit unexpected(Err&& e)`：约束是 `Err` 去掉 cv 和引用后不是 `unexpected`、不是 `in_place_t`，并且 `is_constructible_v<E, Err>`。默认模板实参 `Err = E` 让花括号实参可用，例如 `unexpected<std::string>({'a', 'b'})`。
- ¶4 `explicit unexpected(in_place_t, Args&&...)` 和带 `initializer_list` 的版本（第 7 段）：原地构造错误值。

`explicit` 是有意的：必须写出 `std::unexpected(...)`，`E` 类型的值才会变成错误。推导指引让 `std::unexpected(ec)` 推导出 `unexpected<std::errc>`。`std::unexpected("oops")` 推导出 `unexpected<const char*>`，再由 `expected` 接受 `unexpected<G>` 的转换构造函数转为真正的 `E`：

```cpp run title="unexpected-convert.cpp" ok
#include <cassert>
#include <expected>
#include <string>

std::expected<int, std::string> f() {
  return std::unexpected("oops");  // unexpected<const char*>
}

int main() {
  assert(f().error() == "oops");  // 转换成了 std::string
}
```

### 访问、交换与比较

¶1 [expected.un.obs] `error()` 有 `const&`、`&`、`const&&`、`&&` 四个重载，返回所存的错误值，右值版本返回 `std::move` 之后的结果，都是 `noexcept`。

¶1 [expected.un.swap] 成员 `swap` 要求（*Mandates*）`is_swappable_v<E>`，效果是 `using std::swap; swap(unex, other.unex);`，可以经 ADL 找到 `E` 自己的 `swap`。第 3 段友元 `swap(x, y)` 写成约束（*Constraints*）`is_swappable_v<E>`。

这个区别是有意的。友元 `swap` 会经 ADL 进入任何对 `unexpected<E>` 的无限定 `swap` 调用的候选集，包括 `is_swappable` 内部的检测，所以它必须在不满足条件时退出重载决议，否则 `is_swappable_v<unexpected<X>>` 会给出错误的答案（见思考题 1）。成员函数只有被显式调用时才实例化，用 *Mandates* 直接报错即可。

¶1 [expected.un.eq] `operator==` 是一个隐藏友元模板 `template<class E2> friend constexpr bool operator==(const unexpected&, const unexpected<E2>&)`，返回 `x.error() == y.error()`。要求 `x.error() == y.error()` 良构且结果可转换为 `bool` 是 *Mandates*，不是约束。所以对不可比较的 `X`，`std::equality_comparable<unexpected<X>>` 仍然为真（声明总是可行的），真正调用时才报错。用概念做检测时要留意这一点。

## bad_expected_access（[expected.bad]、[expected.bad.void]）

```cpp
template<class E>
class bad_expected_access : public bad_expected_access<void> {
public:
  constexpr explicit bad_expected_access(E);
  constexpr const char* what() const noexcept override;
  constexpr E& error() & noexcept;  // 以及另外三个 cvref 重载
private:
  E unex;  // 仅用于说明
};
```

¶1 在没有值的 `expected<T, E>` 上调用 `value()`，抛出的就是这个异常。和 `bad_optional_access` 不同，它带着错误值：¶2 构造函数按值接受 `E` 并移动进去，`error()` 把它取回来。上层的 `catch` 能拿到具体的失败原因。

带着 `E` 也带来一个限制。抛出的异常对象必须能被复制（[[except.throw]]），而且 `value()` 是用 `as_const(error())` 复制出错误值来构造异常的，所以 `value()` 的 *Mandates* 要求 `is_copy_constructible_v<E>`（[[expected.expected]]）。只能移动的错误类型可以放进 `expected`，但不能调用 `value()`。

[expected.bad.void] 给出公共基类：

```cpp
template<>
class bad_expected_access<void> : public exception {
protected:
  constexpr bad_expected_access() noexcept;
  constexpr bad_expected_access(const bad_expected_access&) noexcept;
  // 移动构造、两个赋值运算符同样是 protected
  constexpr ~bad_expected_access();
public:
  constexpr const char* what() const noexcept override;
};
```

有了它，可以不关心 `E` 而捕获所有这类异常：`catch (const std::bad_expected_access<void>& e)`。它的特殊成员全部是 `protected` 的，不能单独创建它的对象，也不能把派生类对象切片复制成它，它只作为基类存在：

```cpp run title="catch-by-value.cpp" error
#include <expected>

void f() {
  try {
  } catch (std::bad_expected_access<void> e) {  // error: 构造函数和析构函数是 protected
  }
}
int main() {}
```

两个类的 `what()` 都返回实现定义的 NTBS，所有成员都是 `constexpr` 的。C++26 允许在常量求值中抛出和捕获异常，`bad_expected_access` 也就可以在常量求值中被抛出和处理。

## 与 optional、variant 的比较

| | `optional<T>` | `expected<T, E>` | `variant<T, E>` |
|---|---|---|---|
| 状态 | 有值或无值 | 有值或有错误 | 若干候选类型之一 |
| 能否什么都没有 | 能，这是正常状态 | 不能 | 只在异常之后（valueless） |
| 访问失败时抛 | `bad_optional_access` | `bad_expected_access<E>`，带着错误 | `bad_variant_access` |
| 对称性 | 不适用 | 偏向 `T` | 各候选类型平等 |
| 单子操作 | `and_then`、`transform`、`or_else` | 另加 `transform_error` | 没有，用 `visit` |
| 没有值时的写法 | 不适用 | `expected<void, E>` | `variant<monostate, E>` |

!!! history
    `expected` 的提案经过了十多个修订版，最终以 [[P0323R12]] 进入 C++23。期间争论的问题包括错误一侧是否应有默认类型、能否从 `E` 隐式构造，最终定为错误必须经 `unexpected` 显式表达。同属 C++23 的 [[P2505R5]] 增加了单子操作 `and_then`、`or_else`、`transform`、`transform_error`，`__cpp_lib_expected` 随之升为 `202211L`，本机 libc++ 23 报告的就是这个值。当前草案还为 `expected` 增加了 `has_error()`，libc++ 23 尚未提供。

## 思考题

!!! question "思考题 1"
    设 `X` 不可交换，也不可移动。如果把 `unexpected` 的友元 `swap` 改成 *Mandates*，`std::is_swappable_v<std::unexpected<X>>` 会得到什么？

<details markdown="1">
<summary>答案</summary>

会错误地得到 `true`。`is_swappable` 检测的是在 `using std::swap;` 之后，`swap(declval<T&>(), declval<T&>())` 是否良构。ADL 会找到 `unexpected` 的友元 `swap`；如果它只有 *Mandates*，声明总是可行的，检测只看声明，就报告 `true`，真正调用时才报错。

用 *Constraints* 时，条件不满足的友元退出重载决议，只剩 `std::swap`。它要求 `unexpected<X>` 可移动构造和移动赋值，而这些成员是 `= default` 的，`X` 不可移动时它们被删除，`std::swap` 也不可行，于是得到正确的 `false`。本机 libc++ 23 上，`X` 删除了移动构造时，`std::is_swappable_v<std::unexpected<X>>` 确实为 `false`。
</details>

!!! question "思考题 2"
    `bad_expected_access<void>` 的复制构造函数为什么是 `protected` 而不是 `public`？

<details markdown="1">
<summary>答案</summary>

如果是 `public`，`catch (std::bad_expected_access<void> e)` 这种按值捕获就会把派生类对象切片复制成基类对象，丢掉错误值，而这种写法看上去完全合理，很难察觉。`protected` 让按值捕获变成编译错误，迫使你按引用捕获。派生类 `bad_expected_access<E>` 的复制构造仍然可以调用基类的 protected 复制构造，抛出异常、`exception_ptr` 等需要复制异常对象的场合不受影响。
</details>

## 小结

| 主题 | 规则 |
|---|---|
| `expected<T, E>` | 持有 `T` 或 `E` 之一，没有空状态 |
| 构造错误 | 经 `unexpected<E>` 或 `unexpect` 标签；`E` 不会隐式变成错误 |
| `unexpect_t` | 默认构造函数是 `explicit` 的，`{}` 不会匹配它 |
| `unexpected<E>` 的 `E` | 非数组、非 cv 限定、非 `unexpected` 特化的对象类型；实例化定义时检查 |
| `unexpected` 的构造 | 全部 `explicit`；推导指引 `unexpected(E) -> unexpected<E>` |
| `swap` | 成员用 *Mandates*；友元用 *Constraints* |
| `operator==` | *Mandates*：`error()` 之间可比较 |
| `bad_expected_access<E>` | 带着错误值；`value()` 因此要求 `E` 可复制构造 |
| `bad_expected_access<void>` | 公共基类，特殊成员全是 `protected`，防止切片 |

<details class="fine" markdown="1"><summary>其余条文</summary>

[expected.syn]：头文件概要标为 mostly freestanding。`expected` 主模板和 `void` 偏特化标为 partially freestanding，其中会抛异常的 `value()` 在独立实现中是删除的。

[expected.un.general]/1 只说明这一节描述的类模板 `unexpected` 表示存放在 `expected` 对象中的意外值。

[expected.un.cons] 中各构造函数的 *Throws* 元素（¶3、¶6、¶9）只说抛出初始化错误值时抛出的异常。

[expected.bad]/3–4 是 `error()` 四个重载的返回值；第 5 段和 [expected.bad.void]/1 规定 `what()` 返回实现定义的 NTBS，常量求值期间用普通字面量编码（[[lex.ccon]]）。

</details>
