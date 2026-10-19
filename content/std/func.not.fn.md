---
title: 函数模板 not_fn
summary: not_fn(f) 返回一个对 f 的结果取反的完美转发调用包装器，调用模式为 !invoke(fd, call_args...)；它取代了 C++20 移除的 not1 / not2，C++26 又增加了不保存可调用物的 not_fn<f>()。
status: done
papers: P0005R4, P2714R1
related: func.require, func.bind.partial, func.bind, function.objects, const.wrap.class
tags: 标准库, functional, not_fn, 谓词, 调用包装器
updated: 2026-10-19
---

!!! tldr
    - `not_fn(f)(args...)` 等价于 `!invoke(f, args...)`，可以对任意参数个数的谓词取反，包括成员指针。
    - 结果是完美转发调用包装器：包装器的 const 和值类别会传给保存的 `f`，带引用限定的 `operator()` 能被正确选中。
    - 返回类型是 `!` 表达式的类型，不一定是 `bool`。
    - C++26 的 `not_fn<f>()` 把 `f` 作为模板实参传入，结果是一个空对象，空指针在编译期被拒绝。

## 对谓词取反

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
  static_assert(std::is_same_v<decltype(even(3)), bool>);                 // !int 的类型是 bool
  std::printf("%d %d\n", even(3), even(4));                               // 0 1

  auto n = std::not_fn(Pred{});
  (void)n(1);              // 左值包装器：目标是 Pred&，打印 &
  (void)std::move(n)(1);   // 右值包装器：目标是 Pred&&，打印 &&
}
```

`not_fn` 在 C++17 加入（[[P0005R4]]）。它取代了 C++98 的 `not1` 和 `not2`：那两个只支持一元和二元谓词，还要求被包装的类型提供 `argument_type` 等成员类型，C++17 弃用，C++20 移除。

## 规格 [func.not.fn]

```cpp
template<class F> constexpr unspecified not_fn(F&& f);
```

¶1 记号与 [[func.bind.partial]] 相同：`FD` 是 `decay_t<F>`，目标对象 `fd` 用 `std::forward<F>(f)` 直接非列表初始化，`call_args` 是调用实参。¶2 要求（Mandates）`FD` 能由 `F` 构造并且可移动构造；¶3 再要求它在语义上满足 *Cpp17MoveConstructible*；¶5 `not_fn` 抛出初始化 `fd` 时抛出的异常。

¶4 返回一个完美转发调用包装器（[[g:perfect-forwarding-call-wrapper]]），调用模式是 `!invoke(fd, call_args...)`。下面几条性质都由此得出：

- 返回类型是 `!` 表达式的类型。`f` 返回 `int` 时是内建的 `!`，结果为 `bool`；`f` 返回一个重载了 `operator!` 的类时，结果就是那个 `operator!` 的返回类型。
- 包装器作为左值调用时目标是 `FD&`，作为右值调用时是 `FD&&`，const 同理，所以上例中 `Pred` 的两个引用限定版本分别被选中。
- 调用经过 `invoke`，所以成员指针也可以取反，例如 `not_fn(&Person::is_adult)`。
- 调用模式不成立时 `g(...)` 是非良构的，不会退到别的限定版本（[[func.require]]）。

## `not_fn<f>()` {{c++26}}

```cpp
template<auto f> constexpr unspecified not_fn() noexcept;
```

这个重载和 `bind_front<f>` 一起由 [[P2714R1]] 加入。¶7 如果 `f` 的类型是指针或成员指针，要求 `f != nullptr`，空指针在编译期被拒绝。¶8 返回的完美转发调用包装器，目标对象是 `cw<f>`（[[const.wrap.class]]）的副本，调用模式是 `!invoke(f, call_args...)`。

包装器不保存任何东西，所以函数本身是 `noexcept`，结果是一个空对象，调用目标在编译期确定。

```cpp run title="not_fn_nttp.cpp" ok
#include <functional>
#include <algorithm>
#include <vector>
#include <cstdio>
bool is_even(int x) { return x % 2 == 0; }
int main() {
  std::vector<int> v{1, 2, 3, 4, 5};
  auto odd = std::not_fn<is_even>();
  static_assert(sizeof(odd) == 1);                       // 空类：不保存函数指针
  static_assert(sizeof(std::not_fn(is_even)) == sizeof(bool (*)(int)));
  std::printf("%td\n", std::ranges::count_if(v, odd));   // 3
}
```

本机 libc++（LLVM 23）已经实现了这个重载，`__cpp_lib_not_fn` 为 `202306L`。
