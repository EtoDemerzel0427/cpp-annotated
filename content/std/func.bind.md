---
title: 函数对象绑定器 std::bind
summary: std::bind 固定一个可调用物的部分实参并允许用占位符重排其余实参；本页讲它按值保存状态的方式、处理绑定实参的四条规则、可由用户特化的 is_bind_expression 与 is_placeholder，以及为什么新代码应改用 lambda 或 bind_front / bind_back。
status: done
covers: *
papers: P0356R5
related: func.require, func.bind.partial, func.not.fn, func.memfn, refwrap, function.objects, func.wrap.func, meta.rqmts, defns.expression.equivalent
tags: 标准库, functional, bind, 占位符, 调用包装器
updated: 2026-10-19
---

!!! tldr
    - `std::bind(f, args...)` 把 `f` 和绑定实参按 `decay_t` 复制保存，返回一个参数转发调用包装器。想保存引用，必须传 `std::ref(x)`。
    - 调用时每个绑定实参按四条规则处理：`reference_wrapper` 解包为 `T&`；嵌套的 bind 表达式先用全部调用实参求值；占位符 `_j` 换成第 j 个调用实参；其余作为左值交出。
    - 绑定的值总是作为左值交给目标，即使包装器本身是右值。所以绑定的 `unique_ptr` 无法移交给按值接收的函数。
    - 没被占位符引用的调用实参会被静默丢弃；同一个占位符出现两次，右值实参会被转发两次。
    - 新代码优先用 lambda，或 C++20 的 `bind_front`、C++23 的 `bind_back`。

## 部分应用与实参重排

```cpp run title="bind_rules.cpp" ok
#include <functional>
#include <cstdio>
using namespace std::placeholders;
int add3(int a, int b, int c) { return 100 * a + 10 * b + c; }
int twice(int x) { return 2 * x; }
void bump(int& n) { ++n; }
int main() {
  auto g = std::bind(add3, _2, 5, _1);                    // 占位符可以重排
  std::printf("%d\n", g(1, 2));                           // add3(2, 5, 1) = 251
  std::printf("%d\n", g(1, 2, 999));                      // 多余的调用实参被静默丢弃

  auto h = std::bind(add3, std::bind(twice, _1), 0, _1);  // 嵌套 bind 先求值
  std::printf("%d\n", h(3));                              // add3(twice(3), 0, 3) = 603

  int n = 0;
  auto by_copy = std::bind(bump, n);                      // 绑定的是 n 的副本
  auto by_ref  = std::bind(bump, std::ref(n));            // 解包为 int&
  by_copy(); by_copy();
  by_ref();
  std::printf("%d\n", n);                                 // 1
}
```

`std::bind` 来自 Boost.Bind 和 TR1，C++11 进入标准。它解决的是 lambda 普及之前的两个问题：**部分应用**（固定一个函数的某些实参）和实参重排。`std::placeholders::_1`、`_2`……叫**占位符**，表示调用包装器时的第 1、第 2……个实参。

今天它的大多数用途已被 lambda 和 `bind_front`、`bind_back`（[[func.bind.partial]]）取代，但老代码里仍然很多。它的规格建立在 [[func.require]] 的 *INVOKE* 和调用包装器概念上。

## 保存什么：`decay` 后按值保存 [func.bind.bind]

```cpp
template<class F, class... BoundArgs>
  constexpr unspecified bind(F&& f, BoundArgs&&... bound_args);
template<class R, class F, class... BoundArgs>
  constexpr unspecified bind(F&& f, BoundArgs&&... bound_args);
```

¶1 先定义了后文要用的记号：

| 记号 | 含义 |
|---|---|
| `g` | `bind` 返回的调用包装器 |
| `FD`、`fd` | `decay_t<F>`；目标对象，用 `std::forward<F>(f)` 直接非列表初始化 |
| `TDi`、`tdi` | 第 i 个绑定实参的 `decay_t<Ti>`；对应的绑定实参实体，用 `std::forward<Ti>(ti)` 初始化 |
| `Uj`、`uj` | 调用 `g(u1, …, uM)` 时第 j 个实参推导出的类型，以及实参本身 |

关键在 `decay`：所有绑定的东西都按值保存。函数退化为函数指针，数组退化为指针，引用被剥掉。想保存引用，只能显式用 `std::ref`。

¶2 要求（Mandates）`FD` 能由 `F` 构造，每个 `TDi` 能由 `Ti` 构造，否则程序非良构。这不是约束：`bind` 照样参与重载决议，然后在函数体内报错。¶6 的注 1 说明，如果 `FD` 和所有 `TDi` 都可复制构造，返回的包装器也可复制构造。

## 调用时发生什么

¶4 `bind` 返回一个参数转发调用包装器（[[g:argument-forwarding-call-wrapper]]），而不是完美转发调用包装器。调用 `volatile` 限定的 `g` 是非良构的。否则 `g(u1, …, uM)` 与下面的表达式[[g:expression-equivalent|表达式等价]]：

```cpp
INVOKE(static_cast<Vfd>(vfd), static_cast<V1>(v1), …, static_cast<VN>(vN))      // 第一个重载
INVOKE<R>(static_cast<Vfd>(vfd), static_cast<V1>(v1), …, static_cast<VN>(vN))   // 带 R 的重载
```

¶8 `vfd` 就是 `fd`，类型 `Vfd` 是 `cv FD&`，`cv` 是 `g` 自身的 cv 限定。也就是说，目标对象总是作为左值交出，不论 `g` 是左值还是右值。

¶7 每个绑定实参 `vi` 和它的类型 `Vi` 由 `TDi` 决定，按顺序匹配四条规则：

| 规则 | 条件 | 交给目标的 `vi` | 类型 `Vi` |
|---|---|---|---|
| ¶7.1 | `TDi` 是 `reference_wrapper<T>` | `tdi.get()` | `T&` |
| ¶7.2 | `is_bind_expression_v<TDi>` 为 true | `static_cast<cv TDi&>(tdi)(std::forward<Uj>(uj)...)` | `invoke_result_t<cv TDi&, Uj...>&&` |
| ¶7.3 | `is_placeholder_v<TDi>` 的值 j 非零 | `std::forward<Uj>(uj)` | `Uj&&` |
| ¶7.4 | 其他 | `tdi` | `cv TDi&` |

它们的后果分别是：

- `reference_wrapper` 被解包。`std::bind(f, std::ref(x))` 调用时传的是 `x` 本身，`f` 可以修改 `x`。
- 嵌套的 bind 表达式被立即求值。内层 bind 用全部调用实参调用，结果再作为外层的实参，所以 `bind(f, bind(g, _1))(x)` 就是 `f(g(x))`。如果本意是把一个 bind 表达式当作回调对象交给 `f`，它会先被调用掉（见下文）。
- 占位符取第 j 个调用实参，并完美转发。没有被任何占位符引用的调用实参被静默丢弃，`g(1, 2, 999)` 中的 `999` 不会引起错误。
- 其余绑定实参以 `cv TDi&` 左值交出。即使写 `std::move(g)()`，目标函数也拿不到右值，所以无法把绑定的 `unique_ptr` 移交给按值接收它的函数。

带 `R` 的重载用 *INVOKE*&lt;R&gt;：结果隐式转换为 `R`，`R` 为 `void` 时丢弃结果（[[func.require#2]]）。

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

## 两个识别用的 trait [func.bind.isbind] [func.bind.isplace]

¶7.2 和 ¶7.3 要分辨嵌套的 bind 表达式和占位符，靠的是两个类模板。它们都满足 *Cpp17UnaryTypeTrait*（[[meta.rqmts]]）：

- `is_bind_expression<T>`：`T` 是 `bind` 返回的类型时派生自 `true_type`，否则派生自 `false_type`。程序可以为自己定义的类型（[[g:program-defined-type]]）特化它为 `true_type`，让这个类型像 bind 子表达式一样在调用时先被求值。
- `is_placeholder<T>`：`T` 是 `std::placeholders::_J` 的类型时派生自 `integral_constant<int, J>`，否则派生自 `integral_constant<int, 0>`。程序可以为自己的类型特化出 `N > 0`，让它充当第 N 个占位符。

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

## 占位符 [func.bind.place]

¶1 占位符的个数由实现定义（{{impl}}），libc++ 提供 `_1` 到 `_10`。¶2 占位符类型可以默认构造和复制构造，这些构造函数都是不抛异常的 `constexpr` 函数；是否可复制赋值由实现定义。

¶3 标准建议把占位符定义为 `inline constexpr unspecified _1{};`，不这样做时声明为 `extern unspecified _1;`。¶4 占位符在独立实现中也要提供。

!!! impl "libc++ 的占位符是 `extern const`"
    libc++ 在 `__functional/bind.h` 中把占位符声明为 `extern const __ph<1> _1;`，定义放在共享库里。源码注释解释说，改成 `inline constexpr` 需要从共享库删掉已有的定义以免违反 ODR，而删掉定义本身就破坏 ABI。占位符是空类，两种写法在使用上几乎没有区别。

## 陷阱

### 嵌套 bind 被意外求值

```cpp run title="nested_bind_trap.cpp" error
#include <functional>
using namespace std::placeholders;
int twice(int x) { return 2 * x; }
int apply(std::function<int(int)> f, int x) { return f(x); }
int main() {
  auto g = std::bind(apply, std::bind(twice, _1), _1);
  return g(3);   // error: 内层 bind 先被求值（¶7.2），apply 收到 int
}
```

本意是把 `bind(twice, _1)` 作为回调交给 `apply`，但按 ¶7.2 它会先用调用实参 `3` 求值，`apply` 的第一个实参变成了 `int`。要把 bind 表达式当作值传进去，先把它包进一个不被 `is_bind_expression` 识别的类型，例如 `std::function` 或 lambda。

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
  g(s);                       // 左值：复制两份
  g(std::string("world"));    // 右值被转发两次：一个形参拿到被移走的字符串
}
```

¶7.3 说 `_1` 对应的实参是 `std::forward<U1>(u1)`，出现两次就转发两次。实参是右值时，第一次初始化形参会把它移走，第二次得到的是有效但未指明的状态（[[g:valid-but-unspecified-state]]）。函数形参的初始化顺序也是未指明的（[[expr.call]]），所以哪个形参拿到空字符串并不确定，本机输出 `[world] []`。这段代码没有 UB，但结果依赖未指明的行为，因此没有标判定。

### libc++ 会退到 const 版本

```cpp run title="bind_cv_fallback.cpp"
#include <functional>
#include <cstdio>
struct F {
  void operator()() const { std::puts("const"); }
  void operator()() = delete;
};
int main() {
  auto g = std::bind(F{});
  g();      // 按条文应非良构；libc++ 接受并打印 const
}
```

按 ¶4 和 ¶8，非 const 的 `g()` 等价于对 `F&` 调用，重载决议选中被弃置的非 const 版本，程序应当非良构。本机 libc++ 接受了这段代码并输出 `const`：它的 `__bind` 在非 const 调用不成立时退到了 const 版本。同样的代码换成 `bind_front`，libc++ 会正确拒绝（见 [[func.require]]）。由于标准与实现不一致，这个代码块没有标判定。

## 为什么改用 `bind_front`、`bind_back` 或 lambda

| 问题 | `bind` | `bind_front` / `bind_back` | lambda |
|---|---|---|---|
| 状态如何交给目标 | 总是 `cv TDi&` 左值 | 按包装器的值类别完美转发 | 自己决定 |
| 多余的调用实参 | 静默丢弃 | 照常传入，个数不符就报错 | 报错 |
| 嵌套 bind 表达式 | 先被求值 | 普通对象 | 普通对象 |
| `reference_wrapper` | 解包 | 不解包，靠隐式转换 | 自己写 |
| 重载函数名 | 推导不出 `F`，要先强制转换 | 同样推导不出 | 在函数体里调用，重载决议正常进行 |
| 重排实参 | 支持 | 只能固定前缀或后缀 | 任意 |

最典型的差别是只能移动的绑定实参：

```cpp run title="bind_vs_bind_front_move.cpp" ok
#include <functional>
#include <memory>
#include <cstdio>
void consume(std::unique_ptr<int> p) { std::printf("%d\n", *p); }
int main() {
  auto g = std::bind_front(consume, std::make_unique<int>(42));
  std::move(g)();      // OK：右值包装器把状态作为 unique_ptr&& 转发
  // g();              // error: 左值包装器交出 unique_ptr&，无法复制
  auto b = std::bind(consume, std::make_unique<int>(7));
  // std::move(b)();   // error: bind 总以左值交出绑定实参（¶7.4）
  (void)b;
}
```

C++20 的 `bind_front`（[[P0356R5]]）就是为此设计的：没有占位符，没有嵌套求值，状态完美转发。

<details class="fine" markdown="1"><summary>其余条文</summary>

[func.bind.general] ¶1 只是说明本条款描述一种统一的实参绑定机制。

[func.bind.bind] ¶3 的前置条件要求 `FD` 和每个 `TDi` 满足 *Cpp17MoveConstructible* 和 *Cpp17Destructible*，并且对某些值 `w1, …, wN`（N 是绑定实参的个数），`INVOKE(fd, w1, …, wN)` 是合法表达式。后一条只是排除参数个数根本对不上的绑定；它是前置条件，违反时实现通常不诊断，等调用时才报错。¶5 规定 `bind` 抛出初始化状态实体时抛出的异常。

</details>

## 思考题

!!! question "思考题 1"
    `auto g = std::bind(f, _1); g();`：不传实参调用一个引用了 `_1` 的 bind 表达式，会怎样？反过来，`auto h = std::bind(f); h(1, 2, 3);` 呢？

<details markdown="1">
<summary>答案</summary>

前者非良构。¶7.3 要用第 1 个调用实参，但调用时没有实参，*INVOKE* 表达式无从构成；libc++ 报告没有匹配的调用运算符。

后者良构。没有占位符引用这三个实参，按 ¶7 它们根本不出现在 *INVOKE* 表达式里，`h(1, 2, 3)` 就是 `f()`。这就是多余实参被静默丢弃。
</details>

!!! question "思考题 2"
    ¶7.2 中嵌套 bind 子表达式的类型 `Vi` 为什么写成 `invoke_result_t<cv TDi&, Uj...>&&`，而不是不带 `&&`？

<details markdown="1">
<summary>答案</summary>

¶4 用 `static_cast<Vi>(vi)` 把每个实参交给 *INVOKE*。加上 `&&` 后经引用折叠：内层返回 `T&` 时 `Vi` 是 `T&`，返回 `T&&` 或纯右值 `T` 时 `Vi` 是 `T&&`。这样既保留了内层调用结果的值类别，又避免对纯右值结果多做一次复制或移动。
</details>
