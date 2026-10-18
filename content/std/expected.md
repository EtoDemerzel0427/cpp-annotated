---
title: expected 对象
summary: <expected> 总览：expected<T, E> 作为"值或错误"的词汇类型与异常、错误码的取舍；unexpect_t；unexpected<E> 的合法实参（非对象、数组、cv 限定、unexpected 特化一律非良构）、构造与相等比较；bad_expected_access<E> 与受保护的 bad_expected_access<void>
status: draft
covers: expected.general, expected.syn, expected.unexpected, expected.un.general, expected.un.cons, expected.un.obs, expected.un.swap, expected.un.eq, expected.bad, expected.bad.void
papers: P0323, P2505
related: expected.expected, expected.void, optional, variant, syserr, except, except.throw, structure.specifications
tags: 标准库, expected, 错误处理, 词汇类型
updated: 2026-10-18
---

`std::expected<T, E>` {{c++23}} 表达"**要么是一个 `T` 类型的结果，要么是一个 `E` 类型的错误**"。它是 `optional<T>` 的自然推广：`optional` 只能说"没有值"，`expected` 还能说"**为什么**没有值"。

[expected] 这一节的结构：

| 子条款 | 内容 | 本站页面 |
|---|---|---|
| [expected.general]、[expected.syn] | 定义、头文件概要、`unexpect_t` | 本页 |
| [expected.unexpected] | 类模板 `unexpected<E>`：错误值的包装 | 本页 |
| [expected.bad]、[expected.bad.void] | 异常类型 `bad_expected_access` | 本页 |
| [expected.expected] | 主模板 `expected<T, E>` | [[expected.expected]] |
| [expected.void] | 偏特化 `expected<cv void, E>` | [[expected.void]] |

前置知识：[[optional]] 与 [[optional.optional]]（`expected` 的大量规格直接沿用 optional 的手法）；库规范中各元素的法律后果（[[structure.specifications]]）。

## 定义（[expected.general] ¶1）

!!! std
    An `expected<T, E>` object holds an object of type `T` or an object of type `E` and manages the lifetime of the contained objects.

    `expected<T, E>` 对象持有一个 `T` 类型的对象或一个 `E` 类型的对象，并管理所含对象的生命周期。

和 `variant<T, E>` 的区别在于**不对称**：`T` 是"期望的"那一边，`E` 是"意外的"那一边。所有接口都偏向 `T`——`*e`、`e->`、`e.value()` 访问值，`if (e)` 检查是否成功，而访问错误必须明确地说 `e.error()`。与 `optional` 的区别在于：`expected` **永远含有某个对象**（值或错误），不存在"什么都没有"的状态——这就是 [[expected.expected]] 中所说的"永不为空"保证。

## 设计取舍：异常、错误码与 expected

C++ 处理"可预期的失败"（解析失败、文件不存在、网络超时）历来有两种主流手段，各有硬伤：

| | 异常 | 错误码（返回值或输出参数） | `expected<T, E>` |
|---|---|---|---|
| 失败信息 | 任意类型，可携带丰富上下文 | 通常只是整数或枚举 | 任意类型 `E` |
| 成功值如何返回 | 正常返回值 | 输出参数，或与错误码挤在一个返回值里 | 正常返回值 |
| 能否被忽略 | 不能（不处理就传播） | 很容易被忽略 | 访问值前不检查就是 bug；`value()` 会抛 |
| 控制流 | 不可见，任何调用都可能跳出 | 显式 | 显式（或用单子操作串联） |
| 开销 | 成功路径近乎零，失败路径昂贵且不确定 | 每次调用都要检查分支 | 同错误码；对象可能更大 |
| `-fno-exceptions` 环境 | 不可用 | 可用 | 大部分可用（`value()` 除外） |
| 函数签名是否表达"可能失败" | 否 | 部分 | 是，`E` 就写在返回类型里 |

`expected` 适合**失败是正常业务结果的一部分、调用者通常会就地处理**的场景：解析、校验、查找、I/O。对于"不该发生但发生了就无法局部恢复"的错误（违反不变式、内存耗尽），异常或契约断言仍然更合适。

`E` 的常见选择：`std::errc` 或 `std::error_code`（[[syserr]]）、自定义枚举、或者携带上下文的结构体。

```cpp run title="parse.cpp" ok
#include <cassert>
#include <charconv>
#include <expected>
#include <string>
#include <string_view>
#include <system_error>

std::expected<int, std::errc> parse(std::string_view s) {
  int v{};
  auto [p, ec] = std::from_chars(s.data(), s.data() + s.size(), v);
  if (ec != std::errc{}) return std::unexpected(ec);
  if (p != s.data() + s.size()) return std::unexpected(std::errc::invalid_argument);
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

注意**返回错误必须经过 `std::unexpected`**：`return v;` 构造值，`return std::unexpected(ec);` 构造错误。为什么不让 `E` 直接隐式转换为 `expected`？因为 `T` 与 `E` 可能是同一类型或可以互相转换——`expected<int, int> f() { return 0; }` 中的 `0` 到底是结果还是错误码？`unexpected` 这层包装让意图在类型上无歧义。

## 头文件概要（[expected.syn]）

`<expected>` 同样是 `// mostly freestanding`，`expected` 主模板与 void 偏特化是"partially freestanding"：`value()` 会抛异常，在独立实现中被弃置。概要中声明了：

- `unexpected<E>`、`bad_expected_access<E>` 与显式特化 `bad_expected_access<void>`；
- 标签类型与常量：

    ```cpp
    struct unexpect_t { explicit unexpect_t() = default; };
    inline constexpr unexpect_t unexpect{};
    ```

    `unexpect` 之于 `expected` 的错误一侧，就如 `in_place` 之于值一侧：`expected<T, E>(unexpect, args...)` 用 `args...` 原地构造错误。默认构造函数是 `explicit` 的——这是标准库标签类型的通用写法（`in_place_t`、`allocator_arg_t` 都一样），它使 `{}` **不能**复制列表初始化为 `unexpect_t`，从而 `e = {}`、`f({})` 不会意外匹配到以 `unexpect_t` 为参数的重载（`nullopt_t` 为了同样的目的走得更远，连默认构造函数都没有，见 [[optional]]）。

- 主模板 `template<class T, class E> class expected;`；
- 偏特化 `template<class T, class E> requires is_void_v<T> class expected<T, E>;`——用一个**受约束的偏特化**同时覆盖 `void`、`const void`、`volatile void`、`const volatile void` 四种情况，而不必写四个偏特化。

## `unexpected<E>`：错误值的信封（[expected.unexpected]）

### 合法的模板实参（[expected.un.general] ¶2）

!!! std
    A program that instantiates the definition of `unexpected` for a non-object type, an array type, a specialization of `unexpected`, or a cv-qualified type is ill-formed.

    以非对象类型、数组类型、`unexpected` 的特化或 cv 限定类型实例化 `unexpected` 的定义，程序非良构。

这句话定义了 [[g:valid-unexpected-argument]]——[[expected.expected]] 中对 `E` 的要求直接引用它（"`E` 不是 `unexpected` 的合法模板实参则非良构"）。逐项理由：

- **非对象类型**（引用、函数、`void`）：`unexpected` 要按值存储错误 *unex*；`expected<T, E&>` 不被支持，错误一侧总是按值持有；
- **数组**：不能复制初始化、不能赋值；
- **`unexpected` 的特化**：`unexpected<unexpected<E>>` 毫无意义，而且会让 `expected(const unexpected<G>&)` 这类构造函数的推导变得含糊——禁止嵌套让"`unexpected<X>` 就是错误值 `X`"这个约定始终成立；
- **cv 限定**：`unexpected<const E>` 存一个 const 成员，复制赋值被弃置，还会把 `expected` 的赋值也连带拖垮；并且 `std::unexpected(x)` 的 CTAD 总是按值推导（`unexpected(E) -> unexpected<E>`），本就推导不出 cv 类型。

注意措辞是"instantiates the **definition**"——只是命名 `unexpected<const int>`（比如作为函数声明的返回类型）不触发；需要完整类型时（定义变量、`sizeof`）才非良构。libc++ 用类内 `static_assert(__valid_std_unexpected<_Err>::value, ...)` 实现，所以触发时机正好是类模板定义被实例化时：

```cpp run title="bad_unexpected.cpp" error
#include <expected>
auto a = sizeof(std::unexpected<const int>);            // error: cv 限定类型
auto b = sizeof(std::unexpected<int[2]>);               // error: 数组类型
auto c = sizeof(std::unexpected<std::unexpected<int>>); // error: unexpected 的特化
auto d = sizeof(std::unexpected<int&>);                 // error: 非对象类型
int main() {}
```

### 构造（[expected.un.cons]）

`unexpected` 没有默认构造函数——错误必须有内容。复制、移动构造与赋值都 `= default`。三个构造函数全部 `explicit`：

- `template<class Err = E> explicit unexpected(Err&& e)`：¶1 *Constraints*：`remove_cvref_t<Err>` 不是 `unexpected`、不是 `in_place_t`，且 `is_constructible_v<E, Err>`；¶2 效果：直接非列表初始化 *unex*。默认实参 `Err = E` 使 `unexpected<std::string>({'a', 'b'})` 这种花括号实参可用。
- `explicit unexpected(in_place_t, Args&&...)` 与 `explicit unexpected(in_place_t, initializer_list<U>, Args&&...)`：原地构造。

`explicit` 是有意的：它防止 `E` 的值被**悄悄**变成错误。你必须写出 `std::unexpected(...)` 这个词。推导指引 `unexpected(E) -> unexpected<E>` 让 `std::unexpected(ec)` 自动推导出 `unexpected<std::errc>`；`std::unexpected("oops")` 推导为 `unexpected<const char*>`，随后由 `expected` 的 `expected(unexpected<G>&&)` 转换构造函数转为真正的 `E`（例如 `std::string`）。

### 观察器、swap、相等（[expected.un.obs]、[expected.un.swap]、[expected.un.eq]）

- `error()` 有 `const&`、`&`、`const&&`、`&&` 四个重载，返回 *unex* 或 `std::move(`*unex*`)`，都是 `noexcept`。
- 成员 `swap`：¶1 *Mandates* `is_swappable_v<E>`；`noexcept(is_nothrow_swappable_v<E>)`；效果是 `using std::swap; swap(unex, other.unex);`（经典的"两步 swap"，允许 ADL 找到 `E` 自己的 `swap`）。
- 友元 `swap(x, y)`：¶3 *Constraints* `is_swappable_v<E>`。

成员 `swap` 用 *Mandates*、友元 `swap` 用 *Constraints*，这个区别不是随意的。友元 `swap` 会经由 ADL 进入**任何**对 `unexpected<E>` 的无限定 `swap` 调用的候选集，包括 `is_swappable` 内部的检测——它必须是 SFINAE 友好的，否则 `is_swappable_v<unexpected<NonSwappable>>` 会给出错误答案甚至硬错误。成员函数只有被显式调用时才会被实例化，用 *Mandates* 直接报错即可。

- `operator==`：一个隐藏友元模板 `template<class E2> friend constexpr bool operator==(const unexpected&, const unexpected<E2>&)`。¶1 是 *Mandates*：`x.error() == y.error()` 良构且结果可转换为 `bool`；¶2 返回该比较的结果。由于是 *Mandates* 而非 *Constraints*，`std::equality_comparable<unexpected<X>>` 对不可比较的 `X` 也会报告"可比较"（声明是可行的），真正调用时才硬错误——这是一个在概念检测时需要留意的不对称。

## `bad_expected_access`（[expected.bad]、[expected.bad.void]）

```cpp
template<class E>
class bad_expected_access : public bad_expected_access<void> {
public:
  constexpr explicit bad_expected_access(E);
  constexpr const char* what() const noexcept override;
  constexpr E& error() & noexcept;   // 以及另外三个 cvref 重载
private:
  E unex;             // exposition only
};
```

[expected.bad] ¶1：当 `has_value()` 为假时访问 `expected<T, E>` 的值（调用 `value()`）就抛出这个异常。与 `bad_optional_access` 不同，它**携带错误值**：¶2 构造函数按值接受 `E` 并移动进 *unex*，`error()` 把它取回来。于是 `e.value()` 抛出的异常里有完整的失败原因，上层 `catch` 可以拿到具体的 `E`。

携带 `E` 带来一个约束：被抛出的异常对象必须可复制构造（[[except.throw]]），所以 `expected::value()` 的 *Mandates* 要求 `is_copy_constructible_v<E>`（[[expected.expected]]）。只能移动的错误类型（如持有 `unique_ptr` 的错误）可以放进 `expected`，但 `value()` 不能用。

[expected.bad.void] 给出公共基类：

```cpp
template<>
class bad_expected_access<void> : public exception {
protected:
  constexpr bad_expected_access() noexcept;
  constexpr bad_expected_access(const bad_expected_access&) noexcept;
  // 移动构造、两个赋值运算符同样 protected
  constexpr ~bad_expected_access();
public:
  constexpr const char* what() const noexcept override;
};
```

它的作用是让你能**不关心 `E`** 地捕获所有 expected 访问失败：`catch (const std::bad_expected_access<void>& e)`。所有特殊成员都是 `protected` 的：不能直接创建一个 `bad_expected_access<void>` 对象，也不能把派生类对象**切片**复制成基类对象——它只作为基类存在。这和 `std::exception` 体系里其他"抽象"基类的思路一致，只是用 `protected` 而非纯虚函数实现。

两者的 `what()` 都返回实现定义的 NTBS，常量求值期间以普通字面量编码；所有成员都是 `constexpr` 的——C++26 允许在常量求值中抛出和捕获异常，`bad_expected_access` 也就可以在 `consteval` 函数里被抛出和处理。

## 与 optional、variant 的比较

| | `optional<T>` | `expected<T, E>` | `variant<T, E>` |
|---|---|---|---|
| 状态 | 有值 / 无值 | 有值 / 有错误 | 若干备选之一（可能 valueless） |
| 是否可能"什么都没有" | 是（正常状态） | **否**（永不为空） | 仅在异常后 `valueless_by_exception` |
| 访问失败时抛 | `bad_optional_access` | `bad_expected_access<E>`（携带错误） | `bad_variant_access` |
| 对称性 | — | 偏向 `T` | 各备选平等 |
| 单子操作 | `and_then`/`transform`/`or_else` | 再加 `transform_error` | 无（用 `visit`） |
| `void` 一侧 | 不适用 | `expected<void, E>` 偏特化 | `variant<monostate, E>` |

## 历史

- [[P0323]]：`std::expected` 的提案，历经十多个修订版，于 C++23 合入（`__cpp_lib_expected` 初值 202202L）。期间接口几经调整（例如错误一侧是否应有默认类型、能否从 `E` 隐式构造），最终定型为"错误必须经 `unexpected` 显式表达"。
- [[P2505]]：为 `expected` 添加单子操作（`and_then`、`or_else`、`transform`、`transform_error`），同属 C++23，`__cpp_lib_expected` 升为 202211L——本机 libc++ 23 报告的就是这个值。
- C++26：观察器加上加固前置条件；`bad_expected_access` 的成员成为 `constexpr`；较新的草案又为 `expected` 增加了 `has_error()`（libc++ 23 尚未提供）。

## 思考题

!!! question "思考题 1"
    为什么 `unexpected` 的友元 `swap` 用 *Constraints*，而成员 `swap` 用 *Mandates*？如果把友元 `swap` 也改成 *Mandates*，`std::is_swappable_v<std::unexpected<X>>`（`X` 不可交换）会得到什么？

<details markdown="1">
<summary>展开查看答案与解析</summary>

`is_swappable` 的检测是"在 `using std::swap;` 的语境下，`swap(declval<T&>(), declval<T&>())` 是否良构"。ADL 会找到 `unexpected` 的隐藏友元 `swap`。若它只有 *Mandates*，声明本身总是可行的，检测只看声明，于是报告 `true`；真正调用时才因 *Mandates* 不满足而硬错误。用 *Constraints* 则不满足时友元不参与重载决议，剩下 `std::swap`，它要求 `unexpected<X>` 可移动构造与移动赋值——而 `unexpected<X>` 的这些操作是 `= default` 的，`X` 不可移动时它们被弃置，于是 `std::swap` 也不可行，最终得到正确的 `false`。本机 libc++ 23 上 `std::is_swappable_v<std::unexpected<NS>>`（`NS` 删除了移动构造）确实为 `false`。成员 `swap` 不参与这类检测，没有这个顾虑。
</details>

!!! question "思考题 2"
    `bad_expected_access<void>` 的复制构造函数为什么是 `protected` 而不是 `public`？

<details markdown="1">
<summary>展开查看答案与解析</summary>

若是 `public`，`catch (std::bad_expected_access<void> e)`（**按值**捕获）就会把派生类对象切片复制成基类对象，丢掉错误值，而且这种写法看上去完全合理、很难察觉。`protected` 让按值捕获成为编译错误，逼你写 `catch (const std::bad_expected_access<void>& e)`。同时派生类 `bad_expected_access<E>` 的复制构造仍可调用基类的 protected 复制构造，异常对象本身的复制（抛出、`exception_ptr`）不受影响。
</details>

## 小结

| 主题 | 规则 |
|---|---|
| `expected<T, E>` | 持有 `T` 或 `E` 之一，永不为空 |
| 错误的构造 | 必须经 `unexpected<E>` 或 `unexpect` 标签，`E` 不会隐式变成错误 |
| `unexpect_t` | `explicit` 默认构造，`{}` 不会匹配 |
| `unexpected<E>` 的 `E` | 必须是非数组、非 cv 限定、非 `unexpected` 特化的对象类型；否则实例化定义即非良构 |
| `unexpected` 构造 | 全部 `explicit`；CTAD `unexpected(E) -> unexpected<E>` |
| swap | 成员：*Mandates*；友元：*Constraints* |
| `operator==` | *Mandates*：`error()` 可比较 |
| `bad_expected_access<E>` | 携带 `E`；`value()` 因此要求 `E` 可复制构造 |
| `bad_expected_access<void>` | 公共基类，特殊成员全 `protected`，防切片 |
