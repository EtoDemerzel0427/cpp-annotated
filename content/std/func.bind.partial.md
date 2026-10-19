---
title: bind_front 与 bind_back
summary: bind_front 和 bind_back 固定一个可调用物的前缀或后缀实参，返回完美转发调用包装器；C++26 增加把可调用物作为非类型模板实参传入的重载，包装器不再需要保存它。
status: done
papers: P0356R5, P2387R3, P2714R1
related: func.require, func.bind, func.not.fn, func.memfn, const.wrap.class, range.adaptor.object, function.objects
tags: 标准库, functional, bind_front, bind_back, 部分应用, NTTP
updated: 2026-10-19
---

!!! tldr
    - `bind_front(f, a, b)(x, y)` 等价于 `invoke(f, a, b, x, y)`；`bind_back(f, a, b)(x, y)` 等价于 `invoke(f, x, y, a, b)`。
    - `f` 和绑定实参都按 `decay_t` 复制保存；要保存引用，传 `std::ref`。
    - 结果是完美转发调用包装器：包装器是右值时，保存的状态也作为右值交出，所以绑定的 `unique_ptr` 可以移交出去。
    - 与 `std::bind` 相比，没有占位符、没有嵌套求值、不解包 `reference_wrapper`，也不丢弃多余的调用实参。
    - C++26 的 `bind_front<f>(args...)` 把 `f` 作为模板实参传入，包装器不保存它，空指针在编译期被拒绝。

## 固定前缀或后缀实参

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
  auto hi = std::bind_front(&Greeter::greet, &g);            // 经 INVOKE：成员函数指针加对象指针
  std::printf("%s\n", hi("bob").c_str());

  auto once = std::bind_front(consume, std::make_unique<int>(42));
  std::move(once)();                                         // 右值包装器交出 unique_ptr&&
}
```

`bind_front` 和 `bind_back` 是 `std::bind`（[[func.bind]]）去掉所有特殊处理之后的版本，只做一件事：把保存好的实参放在调用实参的前面或后面，再经 *INVOKE* 调用目标（[[func.require]]）。

## 规格

```cpp
template<class F, class... Args>
  constexpr unspecified bind_front(F&& f, Args&&... args);
template<class F, class... Args>
  constexpr unspecified bind_back(F&& f, Args&&... args);
```

¶1 记号与 `bind` 类似：`FD` 是 `decay_t<F>`，目标对象 `fd` 用 `std::forward<F>(f)` 直接非列表初始化；`BoundArgs` 是 `decay_t<Args>...`，绑定实参实体 `bound_args` 用 `std::forward<Args>(args)...` 初始化；`call_args` 是调用 `g` 时的实参。

¶2 要求（Mandates）`FD` 能由 `F` 构造并且可移动构造，每个 `BoundArgs` 能由对应的 `Args` 构造并且可移动构造，否则程序非良构。¶3 再要求它们在语义上满足 *Cpp17MoveConstructible*。¶5 `bind_front` 抛出初始化状态实体时抛出的异常。

¶4 返回一个完美转发调用包装器（[[g:perfect-forwarding-call-wrapper]]）`g`，调用模式（[[g:call-pattern]]）是：

- ¶4.1 `bind_front`：`invoke(fd, bound_args..., call_args...)`；
- ¶4.2 `bind_back`：`invoke(fd, call_args..., bound_args...)`。

完美转发的意思是，`fd` 和 `bound_args` 交给 `invoke` 的形式随 `g` 的值类别和 const 变化：

| 调用方式 | `fd` 和 `bound_args` 的形式 |
|---|---|
| `g(x)` | `FD&`、`BoundArgs&...` |
| `std::as_const(g)(x)` | `const FD&`、`const BoundArgs&...` |
| `std::move(g)(x)` | `FD&&`、`BoundArgs&&...` |
| `std::move(std::as_const(g))(x)` | `const FD&&`、`const BoundArgs&&...` |

调用与调用模式表达式等价，所以某种限定下调用模式不成立时，对应的 `g(...)` 就是非良构的，不会退到另一种限定的版本（例子见 [[func.require]]）。包装器的复制和移动按状态实体逐个进行：绑定了只能移动的对象，`g` 也只能移动。

!!! pitfall "重载集和函数模板不能直接传"
    `F` 要从实参推导，所以 `std::bind_front(std::max, 0)`、`std::bind_front(overloaded_fn, 1)` 都推导失败。可以包一层 lambda：`std::bind_front([](auto... a) { return f(a...); }, 1)`。C++26 的模板实参版本也需要一个确定的值，对重载集同样要先用 `static_cast` 选定一个。

!!! pitfall "绑定 `this` 不比捕获 `this` 安全"
    `std::bind_front(&Widget::on_event, this)` 保存的是一个裸指针。把它注册为回调后，如果 `Widget` 先析构，指针就悬垂了。这和 lambda 捕获 `this` 是同一个问题。

!!! pitfall "多次以右值调用"
    `auto g = std::bind_front(f, std::string("abc"));` 之后在循环里反复写 `std::move(g)(i)`，每次都把绑定的字符串作为 `std::string&&` 交给 `f`。如果 `f` 按值接收，第一次调用就把字符串移走了，之后拿到的是有效但未指明的状态。可能多次调用的包装器应当以左值调用。

## 把可调用物作为模板实参 {{c++26}}

```cpp
template<auto f, class... Args> constexpr unspecified bind_front(Args&&... args);
template<auto f, class... Args> constexpr unspecified bind_back(Args&&... args);
```

C++26 的 [[P2714R1]] 增加了这两个重载，可调用物 `f` 作为非类型模板实参（NTTP）传入。规格与函数形参版本几乎相同，区别有三处：

- ¶7 要求中不再有 `FD`，但多了一条：如果 `f` 的类型是指针或成员指针，`f != nullptr` 必须为 true。空函数指针在编译期就被拒绝。
- ¶9 返回的完美转发调用包装器，目标对象是 `cw<f>` 的副本（`cw` 是 C++26 的 `constant_wrapper`，见 [[const.wrap.class]]）。调用模式直接写 `f`：`invoke(f, bound_args..., call_args...)` 或 `invoke(f, call_args..., bound_args...)`。
- ¶10 抛出的只可能是初始化 `bound_args` 时的异常。

这样做有两个好处。一是体积：`bind_front(sub, 10)` 要保存一个函数指针和一个 `int`，`bind_front<sub>(10)` 的目标对象是空的 `constant_wrapper`，整个包装器只有一个 `int` 大，放进 `std::function`、`move_only_function` 时更容易用上小缓冲区。二是便于内联：函数指针是运行时的值，优化器要先证明它不变才能内联；模板实参是类型的一部分，调用目标在编译期就确定了。

```cpp run title="nttp_bind_front.cpp" ok
#include <functional>
#include <cstdio>
int sub(int a, int b) { return a - b; }
int main() {
  auto a = std::bind_front(sub, 10);      // 保存函数指针和 int
  auto b = std::bind_front<sub>(10);      // C++26：只保存 int
  static_assert(sizeof(b) == sizeof(int));
  std::printf("%zu %zu %d %d\n", sizeof(a), sizeof(b), a(3), b(3));   // 本机：16 4 7 7
}
```

```cpp run title="nttp_null.cpp" error
#include <functional>
constexpr int (*null_fp)(int) = nullptr;
int main() { auto g = std::bind_front<null_fp>(1); (void)g; }   // error: 违反 f != nullptr
```

!!! impl "libc++ 尚未实现模板实参版的 `bind_back`"
    本机 libc++（LLVM 23）实现了模板实参版的 `bind_front`（`__cpp_lib_bind_front` 为 `202306L`），但没有实现对应的 `bind_back`（`__cpp_lib_bind_back` 仍为 `202202L`），`std::bind_back<f>(...)` 报告没有匹配的函数。

    另一个小差别：libc++ 对函数形参版 `bind_front` 用 `requires` 子句表达 ¶2 的要求，不满足时是没有匹配的函数；对 `bind_back` 用 `static_assert`。标准写的是 Mandates，两种做法都满足非良构且有诊断的要求。

## 历史与演进

!!! history
    - C++20：`bind_front`（[[P0356R5]]）。
    - C++23：`bind_back`（[[P2387R3]]）。它的主要用途是实现用户定义的范围适配器闭包（[[range.adaptor.object]]）：`views::foo(arg)` 返回的就是一个绑定了后缀实参、等待范围作为第一个实参的对象。
    - C++26：两者的模板实参版本（[[P2714R1]]），同时加入的还有 `not_fn<f>`（[[func.not.fn]]）。
