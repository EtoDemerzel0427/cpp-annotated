---
title: expected 的 void 偏特化
summary: expected<cv void, E>：只表达"成功或某个错误"；用受约束的偏特化覆盖四种 cv void；因为值一侧没有对象，赋值无需 reinit-expected 也天然具有强异常保证；operator* 返回 void 却仍有加固前置条件；value() 返回 void 但会抛；单子操作的 f 不接受实参
status: draft
covers: *
papers: P0323, P2505
related: expected, expected.expected, optional.optional, structure.specifications, temp.spec.partial
tags: 标准库, expected, void, 错误处理
updated: 2026-10-18
---

很多可能失败的操作没有"结果"：写文件、发送消息、校验输入、提交事务。它们要表达的只是"成功了"或"失败了，原因是 `E`"。`expected<void, E>` 就是为此准备的：值一侧什么也不存，错误一侧存一个 `E`。

它不能由主模板直接实例化——主模板里有 `remove_cv_t<T> val;` 这样的成员，`void` 类型的成员是非良构的；`*e` 返回 `T&`、`value_or` 返回 `T`，对 `void` 都说不通。于是 [expected.void] 给出一个完整的偏特化。主模板的设计与术语见 [[expected.expected]]，总览见 [[expected]]。

## 受约束的偏特化（[expected.void.general]）

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

这是一个**带 requires 子句的类模板偏特化**（[[temp.spec.partial]]）：它的模板实参列表 `<T, E>` 与主模板完全相同，靠约束 `is_void_v<T>` 比主模板更特化。一个偏特化同时覆盖 `void`、`const void`、`volatile void`、`const volatile void`——若不用约束，就得写四个偏特化 `expected<void, E>`、`expected<const void, E>`……`value_type` 保留 `T` 原样，所以 `expected<const void, E>::value_type` 是 `const void`。

¶1 的措辞值得对照主模板：

!!! std
    Any object of type `expected<T, E>` either represents a value of type `T`, or contains a value of type `E` nested within ([intro.object]) it.

    任何 `expected<T, E>` 对象要么**表示**一个 `T` 类型的值，要么**含有**一个嵌套于其中的 `E` 类型的值。

主模板说"contains a value of type `T`"，这里改成"represents"——`void` 没有对象可"含有"，"成功"只是一个状态。*has_val* 指示对象是否表示一个 `T` 值。

¶2：以非 `unexpected` 合法实参（见 [[expected]]）作为 `E` 实例化定义，非良构。¶3：`E` 须满足 *Cpp17Destructible*。

```cpp
static_assert(sizeof(std::expected<void, int>) == 2 * sizeof(int));  // libc++ 23 实测：一个 int + 一个 bool + 填充
```

## 构造与析构（[expected.void.cons]、[expected.void.dtor]）

- **默认构造**（¶1）：`noexcept`，后置条件 `has_value()` 为真。所以 `return {};` 就是"返回成功"。
- **复制构造**（¶2–6）：若 `rhs` 是错误，复制 *unex*。除非 `E` 可复制构造，否则弃置；`E` 可平凡复制构造则平凡。
- **移动构造**（¶7–11）：*Constraints* `E` 可移动构造；`noexcept(is_nothrow_move_constructible_v<E>)`；`E` 可平凡移动构造则平凡。
- **从 `expected<U, G>` 转换**（¶12–16）：(13.1) 要求 `is_void_v<U>`——只能从另一个 void 的 expected 转换；其余约束与主模板错误一侧的检查相同（`E` 可从 `GF` 构造；`unexpected<E>` 不能从 `expected<U, G>` 的四种 cvref 形式构造）。`explicit` 只取决于 `G` → `E` 是否可隐式转换。
- **从 `unexpected<G>` 构造**（¶17–21）：与主模板相同。
- **`expected(in_place_t)`**（¶22）：`explicit` 且 `noexcept`，后置条件有值。没有实参——`void` 不需要构造。
- **`expected(unexpect_t, Args&&...)`** 等（¶23–30）：原地构造错误。

析构函数（[expected.void.dtor]）：是错误则销毁 *unex*；`E` 可平凡析构则平凡。

## 赋值：没有 *reinit-expected* 也是强保证（[expected.void.assign]）

主模板为了"永不为空"写了一整套 *reinit-expected*（[[expected.expected]]）。void 偏特化完全不需要它。看复制赋值 ¶1：

- (1.1) 都表示值：**无效果**；
- (1.2) 自己是值、`rhs` 是错误：`construct_at(addressof(unex), rhs.unex); has_val = false;`
- (1.3) 自己是错误、`rhs` 是值：销毁 *unex*，置 *has_val* 为真；
- (1.4) 都是错误：`unex = rhs.error()`。

分析异常：

- (1.2) 中构造 *unex* 可能抛——但此时没有任何东西被销毁过（"值"一侧本来就没有对象），*has_val* 还没改，对象原封不动地"表示一个值"。**强保证白送**。
- (1.3) 只是析构，析构不抛（*Cpp17Destructible*）。

因此 void 偏特化的赋值**没有** "`T` 或 `E` 至少一个 nothrow 可移动构造" 这种限制：¶3 只要求 `E` 可复制赋值且可复制构造；¶4 在 `E` 可平凡复制构造、平凡复制赋值、平凡析构时**平凡**。移动赋值（¶5–9）对称：*Constraints* `E` 可移动构造与移动赋值，`noexcept` 等价于 `E` nothrow 可移动构造且 nothrow 可移动赋值。

从 `unexpected<G>` 赋值（¶10–13）也一样简单：表示值时 `construct_at` *unex* 并置 *has_val* 为假，否则 `unex = std::forward<GF>(e.error())`。

`emplace()`（¶14）：`noexcept`，若是错误则销毁 *unex* 并置为"表示值"。没有参数，也不返回引用（返回 `void`）。

!!! impl "libc++ 23"
    与主模板相同，libc++ 23 中 `expected<void, E>` 的复制/移动赋值总是用户提供的，即便 `E` 是 `int`，所以 `std::is_trivially_copyable_v<std::expected<void, int>>` 为假；构造与析构的平凡性已按规范实现（`is_trivially_copy_constructible_v<std::expected<void, int>>` 为真）。

## swap（[expected.void.swap]）

¶1 *Constraints*：`E` 可交换且可移动构造。表 73：都表示值则无效果；都是错误则 `swap(unex, rhs.unex)`；`*this` 是错误、`rhs` 是值则调用 `rhs.swap(*this)`；`*this` 是值、`rhs` 是错误时：

```cpp
construct_at(addressof(unex), std::move(rhs.unex));
destroy_at(addressof(rhs.unex));
has_val = false;
rhs.has_val = true;
```

若移动构造抛异常，`rhs.unex` 还没被销毁、两个标志都没改——同样不需要备份与回滚。¶4 `noexcept` 等价于 `E` nothrow 可移动构造且 nothrow 可交换。

## 观察器（[expected.void.obs]）

| 成员 | 规格 |
|---|---|
| `operator bool`、`has_value()` | 返回 *has_val*（¶1） |
| `has_error()` | `!has_value()`（¶2，较新草案新增；libc++ 23 尚未提供） |
| `void operator*() const noexcept` | *Hardened preconditions*：`has_value()`（¶3） |
| `void value() const &` | *Mandates* `E` 可复制构造；无值时抛 `bad_expected_access(error())`（¶4–5） |
| `void value() &&` | *Mandates* `E` 可复制构造且可移动构造；无值时抛 `bad_expected_access(std::move(error()))`（¶6–7） |
| `error()` 四个重载 | *Hardened preconditions*：`has_value()` 为假（¶8–11） |
| `error_or(G&&)` | 与主模板相同（¶12–15） |

两个有趣之处：

1. **`operator*` 返回 `void` 却有前置条件**。它什么都不做、什么都不返回，为什么还要检查？因为它的存在是为了让泛型代码统一写 `*e`：在 `T` 可能是 `void` 的模板里，`*e;` 作为"断言有值"的语句仍然有意义。在加固实现里，对错误状态的 `expected<void, E>` 执行 `*e` 会终止程序——这就是一个廉价的"我确信这里成功了"断言。在非加固实现中违反它是 {{ub}}（尽管实际上什么也不会发生——但标准不作保证）。
2. **`value()` 返回 `void` 但会抛**。`e.value();` 是"成功则继续，失败则把错误作为异常抛出"的惯用法，把 expected 世界与异常世界连接起来。

没有 `operator->`、没有 `value_or`——对 `void` 没有意义。

## 单子操作（[expected.void.monadic]）

与主模板的唯一本质区别：**值一侧没有东西可传，`f` 不接受实参**（`and_then`、`transform`）。

- `and_then`（¶1–8）：`U = remove_cvref_t<invoke_result_t<F>>`；*Constraints* `E` 可从 `error()`（或 `std::move(error())`）构造；*Mandates* `U` 是 `expected` 特化且 `U::error_type` 与 `E` 相同；有值则 `invoke(f)`，否则 `U(unexpect, error())`。
- `or_else`（¶9–14）：`G = remove_cvref_t<invoke_result_t<F, decltype(error())>>`；**没有 *Constraints***——值一侧没有东西要搬运；*Mandates* `G` 是 `expected` 特化且 `G::value_type` 就是 `T`（即同一个 cv void）；有值则返回 `G()`，否则 `invoke(f, error())`。
- `transform`（¶15–22）：`U = remove_cv_t<invoke_result_t<F>>`；*Mandates* `U` 是合法值类型，非 void 时 `U u(invoke(f));` 良构；有值且 `U` 非 void 时，结果的 *val* 以 `invoke(f)` 直接非列表初始化；`U` 为 void 时求值 `invoke(f)` 后返回 `expected<U, E>()`。
- `transform_error`（¶23–28）：`G = remove_cv_t<invoke_result_t<F, decltype(error())>>`；*Mandates* `G` 是 `unexpected` 的合法实参且 `G g(invoke(f, error()));` 良构；有值返回 `expected<T, G>()`。

!!! lawyer "草案中的一处笔误"
    当前草案 [expected.void.monadic] ¶2 写作 "*Constraints*: `is_constructible_v<E, decltype(error())>>` is `true`"——多了一个 `>`。对照 ¶16 与主模板 [expected.object.monadic] ¶2，含义显然是 `is_constructible_v<E, decltype(error())>`。这是纯编辑性错误，不影响规范含义。

`transform` 让 void 与非 void 的 expected 可以互相转换：`expected<void, E>` 经 `transform([]{ return 42; })` 得到 `expected<int, E>`；`expected<int, E>` 经 `transform([](int){})` 得到 `expected<void, E>`（见 [[expected.expected]]）。

```cpp run title="void_expected.cpp" ok
#include <cassert>
#include <expected>
#include <string>
#include <type_traits>

std::expected<void, std::string> open_file(bool ok) {
  if (!ok) return std::unexpected("cannot open");
  return {};                                   // 值初始化：has_value() == true
}

int main() {
  auto r = open_file(true)
             .and_then([] { return std::expected<int, std::string>(42); })  // f 无参
             .transform([](int n) { return n + 1; });
  assert(r == 43);

  auto e = open_file(false);
  assert(!e && e.error() == "cannot open");

  // transform 的 f 也是无参的；结果可以是 expected<int, E>
  auto n = open_file(true).transform([] { return 7; });
  static_assert(std::is_same_v<decltype(n), std::expected<int, std::string>>);
  assert(*n == 7);

  try {
    e.value();                                 // value() 返回 void，但会抛
    assert(false);
  } catch (const std::bad_expected_access<std::string>& ex) {
    assert(ex.error() == "cannot open");
  }

  e.emplace();                                 // 丢弃错误，变成"成功"
  assert(e.has_value());
  *e;                                          // 合法：operator* 返回 void

  static_assert(std::is_trivially_copy_constructible_v<std::expected<void, int>>);
  static_assert(sizeof(std::expected<void, int>) == 2 * sizeof(int));
}
```

## 相等比较（[expected.void.eq]）

- `operator==(const expected& x, const expected<T2, E2>& y)`，`requires is_void_v<T2>`：¶1 *Constraints* `x.error() == y.error()` 良构；¶2 状态不同则 `false`；都表示值则 `true`；都是错误则比较错误。
- `operator==(const expected& x, const unexpected<E2>& e)`：与主模板相同。

没有与"值"比较的重载——没有值可比。主模板的 `operator==(const expected&, const expected<T2, E2>&)` 带 `requires (!is_void_v<T2>)`，这里带 `requires is_void_v<T2>`，两者互补：void 与非 void 的 expected 不能相互比较。

## 思考题

!!! question "思考题"
    主模板的复制赋值要求 "`T` 或 `E` 至少一个 nothrow 可移动构造"，void 偏特化却没有任何类似要求。能否据此说"`expected<void, E>` 的赋值对任意 `E` 都提供强异常保证"？

<details markdown="1">
<summary>展开查看答案与解析</summary>

对**切换状态**的赋值，是的：值→错误时只需构造 *unex*，失败则什么都没变；错误→值时只是析构。但对"都是错误"的情况 (1.4)，效果是 `unex = rhs.error()`，调用的是 `E` 的复制赋值，异常保证完全取决于 `E` 自己的赋值运算符——若 `E` 的赋值只提供基本保证，`*this` 的错误值可能处于有效但未指明的状态。所以准确的说法是：*has_val* 永远不会因异常而改变，状态切换具有强保证，而同状态内的赋值继承 `E` 的保证。主模板在"都有值"的情况 (2.1) 也是同样的道理。
</details>

## 小结

| 主题 | `expected<void, E>` | 对照主模板 |
|---|---|---|
| 偏特化形式 | `requires is_void_v<T>`，覆盖四种 cv void | — |
| 存储 | *has_val* + `union { E unex; }` | 多一个 *val* |
| 默认构造 | `noexcept`，表示成功 | 值初始化 `T` |
| `in_place` 构造 | 无实参，`noexcept` | 转发实参 |
| 赋值 | 无需 *reinit-expected*，状态切换天然强保证，无 nothrow 移动要求 | *reinit-expected*，要求 `T` 或 `E` nothrow 可移动 |
| `emplace()` | 无参，返回 `void` | 转发实参，返回 `T&`，要求 nothrow |
| `*e` | 返回 `void`，仍有加固前置条件 | 返回 `T&` |
| `value()` | 返回 `void`，可能抛 | 返回 `T&` |
| `value_or`、`->` | 无 | 有 |
| 单子操作 | `and_then`/`transform` 的 `f` 无参；`or_else` 无 *Constraints* | `f` 接受值 |
| 比较 | 仅与 void expected、`unexpected` 比较 | 还可与值比较 |
