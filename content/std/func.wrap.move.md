---
title: 仅移动包装器 move_only_function
summary: C++23 的 move_only_function——签名里的 cv/ref/noexcept 限定与 inv-quals、is-callable-from 约束、可装 move-only 甚至不可移动（in_place_type）的目标、空调用是前条件违反（UB）而非抛异常
status: draft
covers: *
since: c++23
papers: P0288R9
related: func.wrap, func.wrap.func, func.wrap.copy, func.wrap.ref, func.require, func.def, structure.specifications, dcl.fct, over.match.funcs
tags: 标准库, functional, 类型擦除, move-only, C++23
updated: 2026-10-18
---

`std::function` 有两个无法在原地修复的缺陷（[[func.wrap.func]]）：目标必须可复制，以及 `operator() const` 会调用非 const 的目标。C++23 的 `move_only_function`（[[P0288R9]]）从零开始重新设计：包装器本身**只能移动**，因此目标也只需可移动（甚至不可移动，见 `in_place_type` 构造）；并且第一次把 **cv、引用限定和 `noexcept`** 写进了包装器的签名。

!!! warning "实现状态"
    截至本文编写时，libc++（LLVM 23.1）**尚未实现** `move_only_function`：`<version>` 中 `__cpp_lib_move_only_function`（`202110L`）被注释掉。libstdc++ 与 MSVC STL 已提供。本页示例无法用本地 libc++ 验证，因此**不标判定**；请用代码块上的 godbolt 按钮以 GCC trunk 试验。

## 十二个偏特化与 *inv-quals*（[func.wrap.move.general]）

主模板 `template<class... S> class move_only_function;` 没有定义，只有形如 `move_only_function<R(ArgTypes...) cv ref noexcept(noex)>` 的偏特化。¶1 规定三个占位符的取值：

- *cv*：`const` 或空；
- *ref*：`&`、`&&` 或空；
- *noex*：`true` 或 `false`。

共 2 × 3 × 2 = 12 种组合。模板实参是一个**带限定符的函数类型**——例如 `int() const &`、`void(int) && noexcept`。这种函数类型在核心语言里被戏称为"可憎的函数类型"（[[g:abominable-function-type]]，[[dcl.fct]]）：它们只能出现在少数位置（成员函数类型、模板实参），不能用来声明普通函数。正是这种奇特的类型让包装器能把"调用方式"编码进类型。

¶2 定义了一个贯穿全节的说明用占位符 *inv-quals*（[[g:inv-quals]]）——**调用目标时使用的限定**：

- *ref* 为空时，*inv-quals* 是 *cv*`&`；
- 否则，*inv-quals* 是 *cv* *ref*。

| 签名 | `operator()` 的限定 | 目标被如何调用（*inv-quals*） |
|---|---|---|
| `R(A...)` | 无 | 非 const 左值（`F&`） |
| `R(A...) const` | `const` | const 左值（`const F&`） |
| `R(A...) &` | `&` | 非 const 左值 |
| `R(A...) const &` | `const &` | const 左值 |
| `R(A...) &&` | `&&` | 非 const 右值（`F&&`） |
| `R(A...) const &&` | `const &&` | const 右值 |

关键在第一行：签名**不带 ref** 时，包装器的 `operator()` 可以在左值和右值上调用，但目标**总是作为左值**被调用。这与"成员函数没有 ref 限定时 `*this` 的处理"一致（[[over.match.funcs]]），也保证了无 ref 限定的包装器可以被反复调用。

## 类概要要点（[func.wrap.move.class]）

- 有 `result_type`；
- 构造：默认、`nullptr_t`、移动（`noexcept`）、`template<class F> move_only_function(F&&)`、两个 `explicit` 的 `in_place_type_t` 构造；**没有复制构造/复制赋值**；
- 调用：`explicit operator bool() const noexcept` 与 `R operator()(ArgTypes...) cv ref noexcept(noex)`；
- 工具：成员 `swap`，以及**隐藏友元**（[[g:hidden-friend]]）`swap` 与 `operator==(const move_only_function&, nullptr_t)`——只能经由 ADL 找到，不污染命名空间的重载集；
- **没有** `target()`/`target_type()`，**没有**推导指引。

¶1："generalize the notion of a callable object"——注意 `function` 的措辞是"推广函数指针"，这里改成了"推广可调用对象"。

¶2 *Recommended practice*：应避免为小的目标对象动态分配。注 1 补充了一个关键限制：

!!! std
    Such small-object optimization can only be applied to a type T for which is_nothrow_move_constructible_v<T> is true.

    这种小对象优化只能用于 `is_nothrow_move_constructible_v<T>` 为 true 的类型 T。

原因是 `move_only_function` 的移动构造函数是 `noexcept` 的（[func.wrap.move.ctor] ¶3）。目标若存在内联缓冲区里，移动包装器就必须移动目标；目标的移动可能抛异常，就无法兑现 `noexcept`。存在堆上的目标则只需转移指针。这条注是从规范条款**推出**的结论，不是额外的规定。

## *is-callable-from*：构造函数的核心约束（[func.wrap.move.ctor] ¶1）

!!! std
    is_invocable_r_v<R, VT cv ref, ArgTypes...> && is_invocable_r_v<R, VT inv-quals, ArgTypes...>

    （*noex* 为 true 时两处都换成 `is_nothrow_invocable_r_v`。）

*is-callable-from*<VT>（[[g:is-callable-from]]）要求目标类型 `VT` 能以**两种方式**调用并把结果转换为 `R`：按签名的 *cv ref* 调用，以及按 *inv-quals* 调用。

- 签名带 ref（`&` 或 `&&`）时，*cv ref* 与 *inv-quals* 相同，两个条件合一；
- 签名不带 ref 时，*cv ref* 是 `VT cv`（`is_invocable` 的第一个实参不带引用意味着**右值**），*inv-quals* 是 `VT cv&`（左值）。于是目标必须**同时**能作为左值与右值调用——只有 `operator()() &` 或只有 `operator()() &&` 的函数对象会被拒绝。

可以把它理解为：无 ref 限定的包装器对外承诺"左值右值都能调用"，那么它装的目标也得经得起两种调用方式。

**const 正确性因此得到修复**：

```cpp run title="mof-const.cpp"
#include <functional>

int main() {
    auto counter = [n = 0]() mutable { return ++n; };

    std::move_only_function<int()> f = counter;              // OK：以非 const 左值调用
    // std::move_only_function<int() const> g = counter;     // error: 不满足 is-callable-from，
                                                              //        mutable lambda 不能以 const 左值调用
    const auto& cf = f;
    // cf();                                                  // error: operator() 不是 const 成员
    return f() == 1 ? 0 : 1;
}
```

`std::function` 中"const 对象调用改变状态的目标"在这里被拆成了两个**类型**：要 const 可调用，就写 `int() const`，代价是只能装 const 可调用的目标。

**`noexcept` 是真正的契约**：`move_only_function<void() noexcept>` 只接受 `is_nothrow_invocable` 的目标，它的 `operator()` 也确实是 `noexcept` 的。`std::function` 无法表达这一点。

## 转换构造函数（¶4–9）

`template<class F> move_only_function(F&& f)`，令 `VT = decay_t<F>`：

| 元素 | 内容 |
|---|---|
| *Constraints*（¶5） | `remove_cvref_t<F>` 不是 `move_only_function`；不是 `in_place_type_t` 的特化；*is-callable-from*<VT> |
| *Mandates*（¶6） | `is_constructible_v<VT, F>` |
| *Preconditions*（¶7） | `VT` 满足 *Cpp17Destructible*；若 `is_move_constructible_v<VT>` 为 true，则满足 *Cpp17MoveConstructible* |
| *Postconditions*（¶8） | 见下 |
| *Throws*（¶9） | 目标初始化抛出的异常；除非 `VT` 是函数指针或 `reference_wrapper` 特化，否则可能抛 `bad_alloc` |

与 `function` 对比：*Mandates* 里**没有可复制性**。捕获了 `unique_ptr` 的 lambda 可以直接装进去：

```cpp run title="mof-move-only.cpp"
#include <functional>
#include <memory>
#include <vector>

int main() {
    std::vector<std::move_only_function<int()>> tasks;
    tasks.emplace_back([p = std::make_unique<int>(42)] { return *p; });   // OK
    auto t = std::move(tasks.back());
    // auto u = t;                                                     // error: 不可复制
    return t() == 42 ? 0 : 1;
}
```

¶8：在下列情况下构造出**空**包装器——`f` 是空函数指针；`f` 是空成员指针；`remove_cvref_t<F>` 是 `move_only_function` **或 `copyable_function`** 的特化且 `f` 没有目标。否则目标是由 `std::forward<F>(f)` 直接非列表初始化的 `VT`。

!!! pitfall "从空的 `std::function` 构造，得到的不是空包装器"
    ¶8 的列表里**没有** `std::function`。用一个空的 `std::function<void()>` 去构造 `move_only_function<void()>`，结果是一个**非空**的 `move_only_function`，它的目标是那个空的 `std::function`：

    ```cpp
    std::function<void()> empty;
    std::move_only_function<void()> m = empty;
    bool b = static_cast<bool>(m);   // true！
    m();                             // 不是 UB：调用目标，目标（空 function）抛 bad_function_call
    ```

    于是"`if (m) m();`"的防御式写法在这里失效。迁移旧代码时，若来源可能是空的 `std::function`，要先判空再转换。

¶7 的前条件值得注意：只在 `VT` **可移动时**才要求它满足移动构造要求。这为下一节的不可移动目标留出了空间。

## `in_place_type` 构造（¶10–21）

```cpp
template<class T, class... Args>
  explicit move_only_function(in_place_type_t<T>, Args&&... args);
template<class T, class U, class... Args>
  explicit move_only_function(in_place_type_t<T>, initializer_list<U> ilist, Args&&... args);
```

目标对象直接在包装器内部（或其分配的存储中）用 `args...` 构造，**不经过任何移动**。因此目标类型可以是**不可移动**的——例如持有 `std::mutex` 或 `std::atomic` 的函数对象：

```cpp run title="mof-in-place.cpp"
#include <functional>
#include <mutex>
#include <utility>

struct Guarded {
    std::mutex m;                       // 使 Guarded 不可复制也不可移动
    int n;
    explicit Guarded(int start) : n(start) {}
    int operator()() { std::lock_guard lk(m); return ++n; }
};

int main() {
    std::move_only_function<int()> f(std::in_place_type<Guarded>, 41);
    // std::move_only_function<int()> g = Guarded(41);   // error: 违反 Mandates，Guarded 不能由右值构造
    auto h = std::move(f);   // OK：包装器的移动只转移所有权（目标必然在堆上）
    return h() == 42 ? 0 : 1;
}
```

最后一行能成立，恰恰依赖了 ¶2 注 1：不可移动的目标不可能放在内联缓冲区里（否则包装器无法移动），所以它一定在堆上，包装器的移动只需转移指针。

契约要点：

- *Constraints*（¶11、¶17）：`is_constructible_v<VT, Args...>`（或 `initializer_list<U>&, Args...`）与 *is-callable-from*<VT>；
- *Mandates*（¶12、¶18）：**`VT` 必须与 `T` 是同一类型**（`VT = decay_t<T>`）。也就是说，`in_place_type<const Foo>`、`in_place_type<Foo&>`、`in_place_type<int(int)>` 都是非良构的——类型擦除包装器存的是一个对象，你必须精确地说出对象的类型；
- 构造函数是 `explicit` 的，避免 `{in_place_type<T>, ...}` 这样的复制列表初始化悄悄生效。

## 赋值与析构（¶22–28）

- ¶22 移动赋值：等价于 `move_only_function(std::move(f)).swap(*this)`。标准没有标 `noexcept`；
- ¶24 `operator=(nullptr_t) noexcept`：销毁目标（若有）；
- ¶26 `template<class F> operator=(F&&)`：等价于 `move_only_function(std::forward<F>(f)).swap(*this)`；
- ¶28 析构：销毁目标（若有）。

## 调用：空调用是前条件违反（[func.wrap.move.inv]）

¶1 `explicit operator bool() const noexcept`：有目标时为 true。

¶2–3：

!!! std
    *Preconditions*: \*this has a target object.

    前条件：`*this` 有目标对象。

¶3 效果等价于 `return INVOKE<R>(static_cast<F inv-quals>(f), std::forward<ArgTypes>(args)...);`，`f` 是指代目标的左值、`F` 是其类型。

这与 `function` 的根本区别：

| | `function` | `move_only_function` |
|---|---|---|
| 空调用 | *Throws*: `bad_function_call` | *Preconditions* 违反 → {{ub}} |
| 实现开销 | 每次调用要能检测空（或空 thunk 抛异常） | 无需检测 |
| `noexcept` 签名 | 无法表达 | `noexcept(noex)` 成立 |

!!! ub "调用空的 move_only_function"
    ```cpp
    std::move_only_function<void()> m;
    m();   // UB：违反 [func.wrap.move.inv]/2 的前条件
    ```
    现行草案中这是普通的 *Preconditions*，不在 C++26 "加固前条件"（*hardened preconditions*，[[structure.specifications]]）之列，所以即使在加固实现（[[g:hardened-implementation]]）中，标准也不要求检查它。实际实现中，空状态常常对应一个空的调用指针，结果多半是崩溃——但不要依赖。

`static_cast<F inv-quals>(f)` 对 `&&` 签名意味着**以右值调用目标**：

```cpp run title="mof-rvalue.cpp"
#include <functional>
#include <string>
#include <utility>

struct OneShot {
    std::string payload = "hello";
    std::string operator()() && { return std::move(payload); }   // 只能在右值上调用
};

int main() {
    std::move_only_function<std::string() &&> f = OneShot{};
    // f();                       // error: operator() 是 && 限定的，f 是左值
    std::string s = std::move(f)();   // OK：目标以 OneShot&& 被调用
    return s == "hello" ? 0 : 1;
}
```

`&&` 签名表达"这是一次性的调用"——调用后目标可能已被"掏空"。注意包装器本身调用后仍然**非空**（`operator bool` 仍为 true），一次性语义是约定，不是由类型强制的。

## 工具（[func.wrap.move.util]）

¶1–2 成员 `swap` 与友元 `swap` 交换目标，`noexcept`。¶3 友元 `operator==(f, nullptr)`：没有目标时为 true；`!=` 与反向比较由 C++20 重写候选合成。

## 与 [func.wrap.general] ¶2–3 的联动

由于 ¶8 承认 `copyable_function` 是"可能为空的包装器"，从一个 `copyable_function` 构造 `move_only_function` 时，实现可以（也被 [[func.wrap]] ¶3 鼓励）直接接管其内部存储，而不是包一层。被包装的包装器之间的按值实参可以彼此别名，复制次数未指明（[[func.wrap]] ¶2）。

## 思考题

!!! question "思考题 1"
    下列哪些能装进 `std::move_only_function<void()>`？
    ```cpp
    struct A { void operator()() &; };
    struct B { void operator()() &&; };
    struct C { void operator()() const; };
    struct D { void operator()(); };
    ```

<details markdown="1">
<summary>展开查看答案与解析</summary>

签名不带 ref，*is-callable-from* 要求 `is_invocable_r_v<void, VT>`（右值）与 `is_invocable_r_v<void, VT&>`（左值）同时成立。

- `A`：`&` 限定，右值调用失败 → 不行；
- `B`：`&&` 限定，左值调用失败 → 不行；
- `C`：const 成员可在任何值类别上调用 → 可以；
- `D`：无 ref 限定的非 const 成员，左值右值都能调用 → 可以。

若想装 `A`，用 `move_only_function<void() &>`；想装 `B`，用 `move_only_function<void() &&>`。
</details>

!!! question "思考题 2"
    为什么 `in_place_type` 构造要求 `VT` 与 `T` 完全相同（*Mandates*），而不像转换构造那样自动 `decay`？

<details markdown="1">
<summary>展开查看答案与解析</summary>

`in_place_type<T>` 的语义是"在里面构造一个 `T` 类型的对象"。如果允许 `T` 是 `const Foo`、`Foo&` 或函数类型而悄悄 decay，用户写下的类型与实际存储的类型就会不一致：`const` 会被丢掉（调用时就不是 const 对象了）、引用会变成值（本想引用外部对象却得到了一个副本）。与其静默改变语义，不如直接拒绝。转换构造函数则不同——它的实参是一个现成的表达式，decay 是值传递的自然语义。
</details>

## 小结

| 主题 | 要点 |
|---|---|
| 签名 | `R(Args...) cv ref noexcept(noex)`，12 个偏特化 |
| *inv-quals* | 无 ref → *cv*`&`；否则 *cv ref* |
| *is-callable-from* | 按 *cv ref* 与按 *inv-quals* 两种方式都可调用（`noex` 时要求 nothrow） |
| 目标要求 | 可由 `F` 构造（*Mandates*）；不要求可复制；`in_place_type` 时可不可移动 |
| 空状态 | 空指针、空成员指针、空的 `move_only_function`/`copyable_function`；**空 `std::function` 不算** |
| 空调用 | 前条件违反 → UB（非加固前条件） |
| SBO | 推荐；只可能用于 nothrow-move 的类型 |
| 缺席 | 复制、`target()`、CTAD |
| libc++ 23 | 未实现 |
