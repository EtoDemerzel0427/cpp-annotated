---
title: 函数模板 not_fn
summary: not_fn(f) 返回完美转发调用包装器，调用模式为 !invoke(fd, call_args...)；取代了 C++20 移除的 not1/not2；C++26 增加 not_fn<f>() 的 NTTP 版本
status: done
papers: P2714R1
related: func.require, func.bind.partial, func.bind, function.objects, const.wrap.class
tags: 标准库, functional, not_fn, 谓词, 调用包装器
updated: 2026-10-18
---

`not_fn` 把一个谓词“取反”：`not_fn(is_even)(x)` ≡ `!is_even(x)`。它是 C++17 引入的、对 C++98 的 `not1`/`not2` 的通用替代——后者要求被包装的函数对象提供 `argument_type` 等成员类型、只支持一元/二元，C++17 弃用、C++20 移除。

前置知识：完美转发调用包装器与调用模式（[[func.require]]）。

## `not_fn(F&& f)`（¶1–¶5）

¶1 的记号与 [[func.bind.partial]] 相同：`FD = decay_t<F>`，目标对象 `fd` 以 `std::forward<F>(f)` 直接非列表初始化，`call_args` 为调用实参包。

- ¶2 **Mandates**：`is_constructible_v<FD, F> && is_move_constructible_v<FD>`。
- ¶3 **Preconditions**：`FD` 满足 *Cpp17MoveConstructible*。
- ¶4 **Returns**：完美转发调用包装器 `g`，**调用模式为 `!invoke(fd, call_args...)`**。
- ¶5 **Throws**：初始化 `fd` 时抛出的异常。

几个由“调用模式 + 完美转发”直接推出的性质：

- **返回类型是 `!` 表达式的类型**，不一定是 `bool`：若 `f` 返回 `int`，结果是内建 `!int`，即 `bool`；若 `f` 返回一个重载了 `operator!` 的类，结果就是那个 `operator!` 的返回类型。
- **cv/值类别透传**：`g` 作为左值调用时目标是 `FD&`，作为右值调用时是 `FD&&`，`const` 同理——带引用限定的 `operator()` 会被正确选中。
- 因为走 `invoke`，**成员指针也可以取反**：`not_fn(&Person::is_adult)`。
- 调用模式不成立时 `g(...)` 非良构，不会退到别的限定版本（[[func.require]]）。

```cpp run title="not_fn_basics.cpp" ok
#include <functional>
#include <algorithm>
#include <type_traits>
#include <vector>
#include <cstdio>
bool is_even(int x) { return x % 2 == 0; }
struct Odd { int operator()(int x) const { return x % 2; } };      // 返回 int
struct Pred {
  bool operator()(int x) &  { std::puts("&");  return x > 0; }
  bool operator()(int x) && { std::puts("&&"); return x > 0; }
};
int main() {
  std::vector<int> v{1, 2, 3, 4, 5};
  std::printf("%td\n", std::ranges::count_if(v, std::not_fn(is_even)));   // 3

  auto even = std::not_fn(Odd{});
  static_assert(std::is_same_v<decltype(even(3)), bool>);                 // !int -> bool
  std::printf("%d %d\n", even(3), even(4));                               // 0 1

  auto n = std::not_fn(Pred{});
  (void)n(1);              // 左值包装器 -> Pred&  -> 输出 &
  (void)std::move(n)(1);   // 右值包装器 -> Pred&& -> 输出 &&
}
```

## `not_fn<f>()`（¶6–¶8）{{c++26}}

```cpp
template<auto f> constexpr unspecified not_fn() noexcept;
```

与 `bind_front<f>` 一同由 [[P2714R1]] 加入：

- ¶7 **Mandates**：若 `F` 是指针或成员指针类型，`f != nullptr`——空指针在编译期被拒绝。
- ¶8 **Returns**：完美转发调用包装器，目标对象是 `cw<f>`（[[const.wrap.class]]）的副本，调用模式为 `!invoke(f, call_args...)`。
- 函数本身 `noexcept`：不需要存储任何东西，构造不可能抛出。

结果是一个**空**的函数对象：不存函数指针，调用目标在编译期确定。

```cpp run title="not_fn_nttp.cpp" ok
#include <functional>
#include <algorithm>
#include <vector>
#include <cstdio>
bool is_even(int x) { return x % 2 == 0; }
int main() {
  std::vector<int> v{1, 2, 3, 4, 5};
  auto odd = std::not_fn<is_even>();
  static_assert(sizeof(odd) == 1);                       // 空类：不存函数指针
  static_assert(sizeof(std::not_fn(is_even)) == sizeof(bool (*)(int)));
  std::printf("%td\n", std::ranges::count_if(v, odd));   // 3
}
```

## libc++ 实现笔记

`__functional/not_fn.h`：函数形参版本是 `__not_fn_t<_Fn> : __perfect_forward<__not_fn_op, _Fn>`，`__not_fn_op` 的调用运算符就是 `return !std::invoke(std::forward<_Args>(__args)...);`。¶2 的 Mandates 被实现成 `enable_if_t` 约束（不满足时“没有匹配的函数”）。NTTP 版本返回 `__nttp_not_fn_t<_Fn>`，一个只有 `operator() const` 的空类，空指针检查用 `static_assert` 实现。`__cpp_lib_not_fn` 在 C++26 模式下为 `202306L`。

## 小结

!!! summary
    | 要点 | 内容 |
    |---|---|
    | 调用模式 | `!invoke(fd, call_args...)` |
    | 包装器层级 | 完美转发调用包装器（引用限定、const 透传） |
    | 返回类型 | `!` 表达式的类型，不强制为 `bool` |
    | 取代 | `not1`/`not2`（C++17 弃用，C++20 移除） |
    | `not_fn<f>()`（C++26） | 空包装器，目标为 `cw<f>`，编译期拒绝空指针 |
