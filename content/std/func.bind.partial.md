---
title: bind_front 与 bind_back
summary: 固定可调用物的前缀或后缀实参，返回完美转发调用包装器，调用模式为 invoke(fd, bound_args..., call_args...) 或其后缀版本；C++26 增加以 NTTP 传入可调用物的重载，包装器不再存储它
status: done
papers: P0356R5, P2387R3, P2714R1
related: func.require, func.bind, func.not.fn, func.memfn, const.wrap.class, range.adaptor.object, function.objects
tags: 标准库, functional, bind_front, bind_back, 部分应用, NTTP
updated: 2026-10-18
---

`bind_front(f, a, b)` 返回一个可调用物 `g`，使得 `g(x, y)` ≡ `invoke(f, a, b, x, y)`；`bind_back(f, a, b)` 则使 `g(x, y)` ≡ `invoke(f, x, y, a, b)`。它们是 `std::bind`（[[func.bind]]）的“去掉所有花招”的版本：没有占位符、没有嵌套求值、没有 `reference_wrapper` 解包、不丢弃多余实参，而且**完美转发状态实体**。

前置知识：完美转发调用包装器与调用模式（[[func.require]] ¶4–¶5）。

## 函数形参版本（¶1–¶5）

```cpp
template<class F, class... Args>
  constexpr unspecified bind_front(F&& f, Args&&... args);
template<class F, class... Args>
  constexpr unspecified bind_back(F&& f, Args&&... args);
```

¶1 的记号：`FD = decay_t<F>`，目标对象 `fd` 以 `std::forward<F>(f)` 直接非列表初始化；`BoundArgs = decay_t<Args>...`，绑定实参实体 `bound_args` 同样以转发后的实参直接非列表初始化；`call_args` 是调用 `g` 时的实参包。和 `bind` 一样，**一切按值存储**（需要引用就传 `std::ref`）。

- ¶2 **Mandates**：`FD` 可由 `F` 构造且可移动构造；每个 `BoundArgs` 可由对应 `Args` 构造且可移动构造。违反则非良构。
- ¶3 **Preconditions**：`FD` 与每个对象类型的 `Ti` 满足 *Cpp17MoveConstructible*（Mandates 只能检查语法，语义要求放在这里）。
- ¶4 **Returns**：一个**完美转发调用包装器** `g`，调用模式为
    - `invoke(fd, bound_args..., call_args...)`（`bind_front`），或
    - `invoke(fd, call_args..., bound_args...)`（`bind_back`）。
- ¶5 **Throws**：初始化状态实体时抛出的异常。

“完美转发”意味着：

| 调用方式 | `fd` 与 `bound_args` 以何种形式交给 `invoke` |
|---|---|
| `g(x)`（非 const 左值） | `FD&`、`BoundArgs&...` |
| `std::as_const(g)(x)` | `const FD&`、`const BoundArgs&...` |
| `std::move(g)(x)` | `FD&&`、`BoundArgs&&...` |
| `std::move(std::as_const(g))(x)` | `const FD&&`、`const BoundArgs&&...` |

并且由于调用是与调用模式**表达式等价**的，某个限定下调用模式不成立时，对应的 `g(...)` 就非良构，而不会退到另一个限定版本（见 [[func.require]] 的“不许退而求其次”）。复制/移动语义按 ¶7 逐成员进行：绑定了只能移动的对象，`g` 也只能移动。

```cpp run title="bind_front_basics.cpp" ok
#include <functional>
#include <memory>
#include <string>
#include <cstdio>
int sub(int a, int b) { return a - b; }
struct Greeter { std::string greet(const std::string& n) const { return "hi " + n; } };
void consume(std::unique_ptr<int> p) { std::printf("%d\n", *p); }
int main() {
  auto ten_minus = std::bind_front(sub, 10);
  auto minus_ten = std::bind_back(sub, 10);
  std::printf("%d %d\n", ten_minus(3), minus_ten(3));        // 7 -7

  Greeter g;
  auto hi = std::bind_front(&Greeter::greet, &g);            // 走 INVOKE：成员函数指针 + 对象指针
  std::printf("%s\n", hi("bob").c_str());

  auto once = std::bind_front(consume, std::make_unique<int>(42));
  std::move(once)();                                         // 右值包装器 -> unique_ptr&&
}
```

!!! pitfall "重载集与函数模板不能直接传"
    `F` 要从实参推导，所以 `std::bind_front(std::max, 0)`、`std::bind_front(overloaded_fn, 1)` 都推导失败。解决办法是包一层 lambda：`std::bind_front([](auto... a) { return f(a...); }, 1)`；或者在 C++26 中用 NTTP 版本——但 NTTP 同样需要一个确定的值，对重载集也得先 `static_cast` 选定一个。

!!! pitfall "绑定 `this` 的生命周期"
    `std::bind_front(&Widget::on_event, this)` 存的是一个裸指针。把它注册为回调后，`Widget` 先析构就是悬垂指针。这与 lambda 捕获 `this` 是同一个问题，`bind_front` 并没有更安全。

## NTTP 版本（¶6–¶10）{{c++26}}

```cpp
template<auto f, class... Args> constexpr unspecified bind_front(Args&&... args);
template<auto f, class... Args> constexpr unspecified bind_back(Args&&... args);
```

C++26 由 [[P2714R1]] 增加了把可调用物作为**非类型模板实参**传入的重载。它们的规格与函数形参版本几乎相同，差别在于：

- ¶7 **Mandates** 不再检查 `FD`，但多了一条：若 `F` 是指针或成员指针类型，`f != nullptr` 必须为 `true`——**空函数指针在编译期就被拒绝**。
- ¶9 **Returns**：完美转发调用包装器 `g`，**其目标对象是 `cw<f>` 的副本**（`cw` 即 C++26 的 `constant_wrapper`，见 [[const.wrap.class]]），调用模式为 `invoke(f, bound_args..., call_args...)` 或 `invoke(f, call_args..., bound_args...)`——注意调用模式里直接用的是 `f` 本身。
- ¶10 **Throws**：只剩初始化 `bound_args` 的异常。

动机有两点：

1. **体积**：`bind_front(sub, 10)` 必须存一个函数指针加一个 `int`；`bind_front<sub>(10)` 的目标对象是空的 `constant_wrapper`，整个包装器只有一个 `int` 大。放进 `std::function`、`move_only_function` 时更容易落进小缓冲区。
2. **可内联性**：函数指针是运行时的值，优化器要先证明它不变才能内联；NTTP 是类型的一部分，调用目标在编译期就确定了。

```cpp run title="nttp_bind_front.cpp" ok
#include <functional>
#include <cstdio>
int sub(int a, int b) { return a - b; }
int main() {
  auto a = std::bind_front(sub, 10);      // 存函数指针 + int
  auto b = std::bind_front<sub>(10);      // C++26：只存 int
  static_assert(sizeof(b) == sizeof(int));
  std::printf("%zu %zu %d %d\n", sizeof(a), sizeof(b), a(3), b(3));   // 16 4 7 7（本机）
}
```

```cpp run title="nttp_null.cpp" error
#include <functional>
constexpr int (*null_fp)(int) = nullptr;
int main() { auto g = std::bind_front<null_fp>(1); (void)g; }   // error：违反 Mandates，f != nullptr
```

!!! impl "libc++ 的支持情况"
    截至本文编写时（LLVM 23），libc++ 定义 `__cpp_lib_bind_front` 为 `202306L`，实现了 NTTP 版的 `bind_front`（`__functional/bind_front.h` 中的 `__nttp_bind_front_t`，用显式对象形参 `this _Self&&` 一次写出四种限定；没有绑定实参时返回一个只有 `static operator()` 的空类）；但**尚未实现 NTTP 版的 `bind_back`**（`__cpp_lib_bind_back` 仍为 `202202L`），`std::bind_back<f>(...)` 在 libc++ 上会报 “no matching function”。

## libc++ 实现笔记

- `__functional/bind_front.h` / `bind_back.h`：函数形参版本都派生自 `__functional/perfect_forward.h` 的 `__perfect_forward<_Op, _Fn, _BoundArgs...>`，`_Op` 分别是 `__bind_front_op`（直接 `std::invoke(args...)`）与 `__bind_back_op`（用 `index_sequence` 把后缀实参挪到最后）。
- 一个小偏差：libc++ 对函数形参版 `bind_front` 用 `requires` 子句表达 ¶2 的 Mandates（于是不满足时是“没有匹配的函数”，SFINAE 友好），对 `bind_back` 则用 `static_assert`。标准写的是 Mandates，二者都满足“非良构且有诊断”的要求。

## 历史演进

!!! history
    - **C++20**：`bind_front`（[[P0356R5]]）。
    - **C++23**：`bind_back`（[[P2387R3]]），它的主要用途是实现**用户定义的范围适配器闭包**（[[range.adaptor.object]]）：`views::foo(arg)` 返回的就是一个“绑定了后缀实参、等待范围作为第一个实参”的对象。
    - **C++26**：两者的 NTTP 版本（[[P2714R1]]），连同 `not_fn<f>`（[[func.not.fn]]）。

## 思考题

!!! question "思考题"
    `auto g = std::bind_front(f, std::string("abc"));` 然后在一个循环里调用 `std::move(g)(i)` 多次，会发生什么？

<details markdown="1">
<summary>展开查看答案与解析</summary>

每次 `std::move(g)(i)` 都把绑定的 `std::string` 作为 `std::string&&` 交给 `f`。如果 `f` 按值接收它，第一次调用就会把字符串移走，之后的调用拿到的是有效但未指明状态的字符串（实践中多为空）。完美转发调用包装器忠实地执行“右值包装器 → 右值状态”的规则，它并不知道你会调用不止一次——对一个可能多次调用的包装器，应当用左值调用 `g(i)`。
</details>

## 小结

!!! summary
    | 要点 | 内容 |
    |---|---|
    | 调用模式 | `bind_front`：`invoke(fd, bound..., call...)`；`bind_back`：`invoke(fd, call..., bound...)` |
    | 包装器层级 | 完美转发调用包装器：状态实体随包装器 cv/值类别转发；不可“回退” |
    | 存储 | `decay_t` 按值；引用用 `std::ref` |
    | 与 `bind` 的差别 | 无占位符、无嵌套求值、无解包、不丢弃实参、状态可作为右值交出 |
    | NTTP 版本（C++26） | `bind_front<f>(args...)`：目标是 `cw<f>`，不存 `f`；编译期拒绝空指针 |
    | libc++ | NTTP `bind_front` 已实现；NTTP `bind_back` 尚未实现 |
