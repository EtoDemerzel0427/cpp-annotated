---
title: 函数对象绑定器 std::bind
summary: std::bind 返回参数转发调用包装器；绑定实参按四条规则变换——reference_wrapper 解包、嵌套 bind 表达式先求值、占位符取调用实参、其余作为左值传出；is_bind_expression / is_placeholder 可由用户特化；为何如今应优先使用 lambda 或 bind_front/bind_back
status: done
covers: *
papers: P0356R5
related: func.require, func.bind.partial, func.not.fn, func.memfn, refwrap, function.objects, func.wrap.func, meta.rqmts, defns.expression.equivalent
tags: 标准库, functional, bind, 占位符, 调用包装器
updated: 2026-10-18
---

`std::bind` 来自 Boost.Bind 与 TR1，C++11 进入标准。它解决的是 lambda 普及之前的老问题：**部分应用**（固定一个函数的某些实参）与**实参重排**。今天它的大多数用途都被 lambda 和 C++20 的 `bind_front` / C++23 的 `bind_back`（[[func.bind.partial]]）取代，但它的规格是理解“调用包装器怎么转发状态”的绝佳反面教材，也仍大量存在于老代码中。

阅读前请先看 [[func.require]]：*INVOKE*、*INVOKE*&lt;R&gt;、“参数转发调用包装器”与“表达式等价”。

## 两个探测 trait（[func.bind.isbind]、[func.bind.isplace]）

`bind` 在处理绑定实参时，需要分辨三类特殊对象：`reference_wrapper`、**嵌套的 bind 表达式**、**占位符**。后两者用两个类模板识别：

- **`is_bind_expression<T>`**：对 `bind` 返回的类型，基特征（base characteristic）为 `true_type`，否则为 `false_type`。¶2 允许程序为**程序定义类型**（[[g:program-defined-type]]）特化它为 `true_type`，表示“这个类型应当像 bind 子表达式一样被处理”——即调用时先用调用实参去调用它。
- **`is_placeholder<T>`**：对 `std::placeholders::_J` 的类型，基特征为 `integral_constant<int, J>`，否则为 `integral_constant<int, 0>`。程序可以为自己的类型特化出 `N > 0`，让它充当第 `N` 个占位符。

两者都要满足 *Cpp17UnaryTypeTrait*（[[meta.rqmts]]）。

```cpp run title="custom_placeholder.cpp" ok
#include <functional>
#include <cstdio>
struct MyPh {};
template<> struct std::is_placeholder<MyPh> : std::integral_constant<int, 2> {};
int sub(int a, int b) { return a - b; }
int main() {
  auto g = std::bind(sub, MyPh{}, std::placeholders::_1);   // MyPh 等同于 _2
  std::printf("%d\n", g(1, 10));                            // sub(10, 1) = 9
}
```

## `bind` 的规格（[func.bind.bind]）

```cpp
template<class F, class... BoundArgs>
  constexpr unspecified bind(F&& f, BoundArgs&&... bound_args);
template<class R, class F, class... BoundArgs>
  constexpr unspecified bind(F&& f, BoundArgs&&... bound_args);
```

### 记号（¶1）

¶1 先定义一串名字，后面全靠它们：

| 记号 | 含义 |
|---|---|
| `g` | `bind` 返回的调用包装器 |
| `FD`、`fd` | `decay_t<F>`；目标对象，以 `std::forward<F>(f)` **直接非列表初始化**的左值 |
| `Ti`、`TDi`、`ti`、`tdi` | 第 i 个绑定实参的类型、`decay_t<Ti>`、实参本身、以 `std::forward<Ti>(ti)` 初始化的绑定实参实体 |
| `Uj`、`uj` | 调用 `g(u1, …, uM)` 时第 j 个实参推导出的类型及实参 |

关键在 `decay`：**所有绑定的东西都按值存储**——函数退化为函数指针，数组退化为指针，引用被剥掉。想存引用，只能显式用 `std::ref`。

### Mandates、Preconditions、Throws（¶2、¶3、¶5）

- ¶2 **Mandates**：`is_constructible_v<FD, F>`，且每个 `is_constructible_v<TDi, Ti>`。不满足则**非良构**（必须诊断，但不是 SFINAE：`bind` 照样参与重载决议，然后在函数体内报错）。
- ¶3 **Preconditions**：`FD` 与每个 `TDi` 满足 *Cpp17MoveConstructible* 与 *Cpp17Destructible*；且对**某些**值 `w1…wN`（N 为绑定实参个数），`INVOKE(fd, w1, …, wN)` 是合法表达式。后一条是个很弱的“健全性”要求——你不能 bind 一个参数个数根本对不上的函数——但它是前置条件，违反即 {{ub}}，实现通常不会诊断，等到调用时才报错。
- ¶5 **Throws**：初始化状态实体时抛出的任何异常。
- ¶6 注 1：若 `FD` 与所有 `TDi` 都 *Cpp17CopyConstructible*，返回类型也是。

### 调用语义（¶4、¶7、¶8）

!!! std
    Returns: An argument forwarding call wrapper g. A program that attempts to invoke a volatile-qualified g is ill-formed.

¶4：返回的是**参数转发调用包装器**——注意，不是完美转发调用包装器。调用 `volatile` 的 `g` 非良构。非 `volatile` 时，`g(u1, …, uM)` 与

```cpp
INVOKE(static_cast<Vfd>(vfd), static_cast<V1>(v1), …, static_cast<VN>(vN))      // 第一个重载
INVOKE<R>(static_cast<Vfd>(vfd), static_cast<V1>(v1), …, static_cast<VN>(vN))   // 第二个重载
```

**表达式等价**。其中 ¶8：`vfd` 就是 `fd`，类型 `Vfd` 是 `cv FD&`（`cv` 是 `g` 自身的 cv 限定）——**目标对象永远作为左值交出**，不论 `g` 是左值还是右值。

¶7 是 `bind` 的核心：每个绑定实参 `vi` 及其类型 `Vi` 由 `TDi` 决定，**按顺序**匹配四条规则：

| 规则 | 条件 | 传给目标的实参 `vi` | 类型 `Vi` |
|---|---|---|---|
| ¶7.1 | `TDi` 是 `reference_wrapper<T>` | `tdi.get()` | `T&` |
| ¶7.2 | `is_bind_expression_v<TDi>` 为 true | `static_cast<cv TDi&>(tdi)(std::forward<Uj>(uj)...)` | `invoke_result_t<cv TDi&, Uj...>&&` |
| ¶7.3 | `is_placeholder_v<TDi>` 的值 `j` 非零 | `std::forward<Uj>(uj)` | `Uj&&` |
| ¶7.4 | 其他 | `tdi` | `cv TDi&` |

逐条看它们的后果：

**¶7.1 `reference_wrapper` 被解包。** `std::bind(f, std::ref(x))` 调用时传的是 `x` 本身（`T&`），所以 `f` 可以修改 `x`。

**¶7.2 嵌套 bind 表达式被“立即求值”。** 内层 bind 用**全部**调用实参被调用，结果再作为外层的实参。这是函数组合：`bind(f, bind(g, _1))(x)` ≡ `f(g(x))`。但它也是一个陷阱：如果你本意是把一个 bind 表达式**当作回调对象**传给 `f`，它会被先调用掉（见下文陷阱）。

**¶7.3 占位符取第 j 个调用实参**，并完美转发。没有被任何占位符引用的调用实参会被**静默丢弃**——`g(1, 2, 999)` 中的 `999` 不会引起任何错误。同一个占位符出现两次，同一个实参就被转发两次。

**¶7.4 其余绑定实参作为 `cv TDi&` 左值传出。** 无论 `g` 是左值还是右值，绑定的值都以**左值**交出。这意味着绑定一个 `unique_ptr` 后，即使 `std::move(g)()`，目标函数也收不到右值，无法按值接收 `unique_ptr`。

```cpp run title="bind_rules.cpp" ok
#include <functional>
#include <cstdio>
using namespace std::placeholders;
int add3(int a, int b, int c) { return 100 * a + 10 * b + c; }
int twice(int x) { return 2 * x; }
void bump(int& n) { ++n; }
int main() {
  auto g = std::bind(add3, _2, 5, _1);                    // ¶7.3：占位符可以重排
  std::printf("%d\n", g(1, 2));                           // add3(2, 5, 1) = 251
  std::printf("%d\n", g(1, 2, 999));                      // 多余的调用实参被静默丢弃

  auto h = std::bind(add3, std::bind(twice, _1), 0, _1);  // ¶7.2：嵌套 bind 先求值
  std::printf("%d\n", h(3));                              // add3(twice(3), 0, 3) = 603

  int n = 0;
  auto by_copy = std::bind(bump, n);                      // ¶7.4：绑定的是 n 的副本
  auto by_ref  = std::bind(bump, std::ref(n));            // ¶7.1：解包为 int&
  by_copy(); by_copy();
  by_ref();
  std::printf("%d\n", n);                                 // 1
}
```

带 `R` 的重载用 *INVOKE*&lt;R&gt;：结果隐式转换为 `R`，`R = void` 时丢弃结果（[[func.require]] ¶2）。

```cpp run title="bind_r.cpp" ok
#include <functional>
#include <type_traits>
#include <cstdio>
long twice(int x) { return 2L * x; }
int main() {
  auto g = std::bind<double>(twice, std::placeholders::_1);   // INVOKE<double>
  auto h = std::bind<void>(twice, 21);                        // INVOKE<void>：丢弃返回值
  static_assert(std::is_same_v<decltype(g(1)), double>);
  static_assert(std::is_same_v<decltype(h()), void>);
  std::printf("%g\n", g(21));                                 // 42
}
```

## 占位符（[func.bind.place]）

- ¶1 占位符的个数 *M* 是**由实现定义**的（{{impl}}）。libc++ 提供 `_1` 到 `_10`。
- ¶2 占位符类型满足 *Cpp17DefaultConstructible* 与 *Cpp17CopyConstructible*，默认构造与复制/移动构造都是不抛异常的 `constexpr` 函数；是否可复制赋值由实现定义。
- ¶3 **应当**（*should*，即建议而非强制）定义为 `inline constexpr unspecified _1{};`；否则声明为 `extern unspecified _1;`。
- ¶4 占位符是 freestanding 项。

!!! impl "libc++ 的占位符是 `extern const`"
    libc++ 在 `__functional/bind.h` 中把占位符声明为 `_LIBCPP_EXPORTED_FROM_ABI extern const __ph<1> _1;`，定义放在共享库里。源码注释说明了原因：改成 `inline constexpr` 需要从共享库里删除已有的定义，否则违反 ODR，而删除定义本身就是 ABI 破坏。由于占位符是空类，两种形式在使用上几乎无法区分：本机测试中 `constexpr auto p = std::placeholders::_1;` 与取其地址作为常量表达式都能通过。

## 陷阱

### 嵌套 bind 被意外求值

```cpp run title="nested_bind_trap.cpp" error
#include <functional>
using namespace std::placeholders;
int twice(int x) { return 2 * x; }
int apply(std::function<int(int)> f, int x) { return f(x); }
int main() {
  auto g = std::bind(apply, std::bind(twice, _1), _1);
  return g(3);   // error：内层 bind 被当作子表达式先求值（¶7.2），apply 收到的是 int 而不是可调用物
}
```

要把 bind 表达式当作“值”传进去，得先把它包进一个不被 `is_bind_expression` 识别的类型里（例如 `std::function`，或者 lambda）。

### 同一占位符转发两次

```cpp run title="placeholder_twice.cpp"
#include <functional>
#include <string>
#include <cstdio>
using namespace std::placeholders;
void two(std::string a, std::string b) { std::printf("[%s] [%s]\n", a.c_str(), b.c_str()); }
int main() {
  auto g = std::bind(two, _1, _1);
  std::string s = "hello";
  g(s);                       // 左值：两份复制
  g(std::string("world"));    // 右值被 std::forward 两次：一个形参会拿到被移走的字符串
}
```

¶7.3 说 `_1` 对应的实参是 `std::forward<U1>(u1)`，出现两次就转发两次。右值时第一次初始化形参会把它“移走”，第二次得到的是有效但未指明的状态（[[g:valid-but-unspecified-state]]）；而且函数实参的求值顺序是**未指明**的（[[expr.call]]），哪个形参拿到空字符串也不确定（本机运行输出 `[world] []`）。所以这段代码没有标注判定：它没有 UB，但结果依赖未指明的行为。

### 目标对象总是左值：libc++ 的偏差

¶8 规定 `Vfd` 是 `cv FD&`，`cv` 来自 `g`。考虑一个非 const `operator()` 被弃置、const 版本可用的函数对象：

```cpp run title="bind_cv_fallback.cpp"
#include <functional>
#include <cstdio>
struct F {
  void operator()() const { std::puts("const"); }
  void operator()() = delete;
};
int main() {
  auto g = std::bind(F{});
  g();      // 按条文：INVOKE(static_cast<F&>(fd)) 选中被弃置的版本，应非良构
}
```

按 ¶4 的表达式等价，非 const 的 `g()` 等价于对 `F&` 调用，应选中被弃置的非 const 版本而非良构。但截至本文编写时，libc++ 接受这段代码并输出 `const`——它的 `__bind` 在非 const 调用不成立时退到了 const 版本。完美转发调用包装器（`bind_front` 等）在 libc++ 中则会正确地拒绝同样的代码（见 [[func.require]] 中的“不许退而求其次”），所以这个代码块没有标注判定。

## 为什么优先用 `bind_front` / `bind_back` 或 lambda

| 问题 | `bind` | `bind_front` / `bind_back`（[[func.bind.partial]]） | lambda |
|---|---|---|---|
| 状态实体的转发 | 永远是 `cv TDi&` 左值 | 按包装器值类别完美转发 | 自己决定 |
| 多余的调用实参 | 静默丢弃 | 照传，个数不符就报错 | 报错 |
| 嵌套 bind 表达式 | 特殊对待，可能意外求值 | 普通对象 | 普通对象 |
| `reference_wrapper` | 解包 | 不解包（靠隐式转换） | 自己写 |
| 重载函数名 | 无法推导 `F`，需要强转 | 同样无法推导 | 直接在函数体里调用，重载决议正常进行 |
| 占位符/重排 | 支持 | 不支持（只固定前缀/后缀） | 任意 |
| 是否“表达式等价”到调用模式 | 是（参数转发） | 是（完美转发，含 cv/引用限定） | — |

最典型的差别是“只能移动的绑定实参”：

```cpp run title="bind_vs_bind_front_move.cpp" ok
#include <functional>
#include <memory>
#include <cstdio>
void consume(std::unique_ptr<int> p) { std::printf("%d\n", *p); }
int main() {
  auto g = std::bind_front(consume, std::make_unique<int>(42));
  std::move(g)();      // OK：右值包装器把状态实体作为 unique_ptr&& 转发
  // g();              // error：左值包装器交出 unique_ptr&，无法复制
  auto b = std::bind(consume, std::make_unique<int>(7));
  // std::move(b)();   // error：bind 总以左值 cv TDi& 交出绑定实参（¶7.4）
  (void)b;
}
```

`bind_front` 由 [[P0356R5]] 引入 C++20，其动机正是提供一个没有占位符、没有嵌套求值、完美转发状态的简单替代品。

## libc++ 实现笔记

- `__functional/bind.h`：`__bind<_Fp, _BoundArgs...>` 把目标与绑定实参存进 `tuple`；`__mu` 系列重载函数分别实现 ¶7 的四条规则（重载于 `reference_wrapper<_Tp>`、`is_bind_expression`、`is_placeholder` 与其余情形）；`__bind_r<_Rp, ...>` 实现带 `R` 的重载。
- `is_bind_expression<T>`、`is_placeholder<T>` 对 cv/引用限定的 `T` 会先 `remove_cvref` 再查询。注意 `decltype(std::placeholders::_1)` 本身就带 `const`（无论是 `inline constexpr` 还是 `extern const` 形式），所以这一步是必要的。

## 思考题

!!! question "思考题 1"
    `auto g = std::bind(f, _1); g();` ——不传任何实参调用一个引用了 `_1` 的 bind 表达式，会怎样？反过来，`auto h = std::bind(f); h(1, 2, 3);` 呢？

<details markdown="1">
<summary>展开查看答案与解析</summary>

前者非良构：¶7.3 要求 `uj` 存在（`j = 1` 而调用实参为 0 个），*INVOKE* 表达式无从构成；libc++ 报告“no matching function for call to object of type `__bind<...>`”。后者良构：没有任何占位符引用这三个实参，它们按 ¶7 根本不出现在 *INVOKE* 表达式里，`h(1, 2, 3)` ≡ `INVOKE(fd)`，即 `f()`。这就是“多余实参被静默丢弃”。
</details>

!!! question "思考题 2"
    为什么 ¶7.2 中嵌套 bind 子表达式的类型 `Vi` 写成 `invoke_result_t<cv TDi&, Uj...>&&`，而不是 `invoke_result_t<cv TDi&, Uj...>`？

<details markdown="1">
<summary>展开查看答案与解析</summary>

因为 ¶4 用 `static_cast<Vi>(vi)` 把每个实参传给 *INVOKE*。加上 `&&` 后经引用折叠：内层返回 `T&` 时 `Vi` 是 `T&`，返回 `T&&` 时是 `T&&`，返回纯右值 `T` 时是 `T&&`——`static_cast<T&&>` 把纯右值实质化为 xvalue 再转发。这样既保留了内层调用结果的值类别，又避免对纯右值结果做多余的复制。
</details>

## 小结

!!! summary
    | 要点 | 内容 |
    |---|---|
    | 存储 | 目标与绑定实参都按 `decay_t` 存值；`std::ref` 才存引用 |
    | 包装器层级 | 参数转发调用包装器（不是完美转发）；调用 `volatile` 的 `g` 非良构 |
    | 目标对象 | 永远作为 `cv FD&` 左值交出 |
    | ¶7 四条规则 | `reference_wrapper` → `T&`；嵌套 bind → 先用全部调用实参求值；占位符 → 转发第 j 个调用实参；其余 → `cv TDi&` 左值 |
    | 占位符 | 个数由实现定义（libc++ 为 10）；建议 `inline constexpr`，libc++ 用 `extern const` |
    | 可扩展点 | 可为程序定义类型特化 `is_bind_expression`、`is_placeholder` |
    | 建议 | 新代码用 lambda 或 `bind_front` / `bind_back` |
