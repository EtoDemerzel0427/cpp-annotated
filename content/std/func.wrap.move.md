---
title: 仅移动包装器 move_only_function
summary: C++23 的 move_only_function 能装下不可复制的可调用对象，签名里可以写 const、& 和 noexcept，调用空包装器是未定义行为而不是抛异常。
status: draft
covers: *
since: c++23
papers: P0288R9
related: func.wrap, func.wrap.func, func.wrap.copy, func.wrap.ref, func.require, func.def, structure.specifications, dcl.fct, over.match.funcs
tags: 标准库, functional, 类型擦除, move-only, C++23
updated: 2026-10-19
---

!!! tldr
    - `move_only_function` 只能移动，所以目标对象只需能从实参构造，捕获了 `unique_ptr` 的 lambda 也能装进去。
    - 签名可以带 `const`、`&`、`&&` 和 `noexcept`，它们同时决定包装器的 `operator()` 怎么声明、目标以什么方式被调用。`std::function` 的 const 漏洞因此不复存在。
    - 签名不带 `&`/`&&` 时，目标必须既能以左值调用，也能以右值调用。
    - 调用空的 `move_only_function` 违反前条件，是未定义行为；用一个空的 `std::function` 构造它，得到的却不是空包装器。
    - `in_place_type` 构造可以装下连移动都不行的类型，这样的目标一定放在堆上。

!!! warning "实现状态"
    本机 libc++（LLVM 23）还没有实现 `move_only_function`，`<version>` 里的 `__cpp_lib_move_only_function` 是注释掉的。libstdc++ 和 MSVC STL 已经提供。本页的例子无法在本机编译，所以不标判定；可以用代码块上的 godbolt 按钮在 GCC 上试。

## 为什么需要它

```cpp run title="mof-move-only.cpp"
#include <functional>
#include <memory>
#include <vector>

int main() {
    std::vector<std::move_only_function<int()>> tasks;
    tasks.emplace_back([p = std::make_unique<int>(42)] { return *p; });   // OK
    auto t = std::move(tasks.back());
    // auto u = t;                                    // error: 不可复制
    return t() == 42 ? 0 : 1;
}
```

`std::function` 要求目标可复制（[[func.wrap.func]]），上面这个捕获了 `unique_ptr` 的 lambda 装不进去。任务队列、线程池、回调登记表里存的往往正是这种只能移动的对象。

`move_only_function` 的做法是让包装器本身也只能移动：既然包装器永远不会被复制，就不需要复制目标。C++23 通过 [[P0288R9]] 引入它的同时，还修正了 `std::function` 的另外两个问题：签名里不能写 `const` 和 `noexcept`，以及调用空包装器要付出判空的代价。

## 签名里的 const、引用限定和 noexcept

[func.wrap.move.general] 第 1 段规定，主模板 `template<class... S> class move_only_function;` 没有定义，只有形如 `move_only_function<R(ArgTypes...) cv ref noexcept(noex)>` 的偏特化：

- *cv* 是 `const` 或空；
- *ref* 是 `&`、`&&` 或空；
- *noex* 是 `true` 或 `false`。

一共 12 种组合。模板实参是一个带限定符的函数类型，例如 `int() const`、`void(int) && noexcept`。这种类型在核心语言里只能用作成员函数的类型或模板实参，不能用来声明普通函数，俗称 abominable function type（[[g:abominable-function-type]]，[[dcl.fct]]）。包装器正是借它把调用方式写进类型。

签名里的 *cv ref* 会原样出现在包装器的 `operator()` 上。第 2 段另外定义了一个说明用的占位符 *inv-quals*（[[g:inv-quals]]），表示**调用目标时使用的限定**：*ref* 为空时是 *cv*`&`，否则就是 *cv ref*。

| 签名 | 包装器 `operator()` 的限定 | 目标以什么身份被调用 |
|---|---|---|
| `R(A...)` | 无 | 非 const 左值 |
| `R(A...) const` | `const` | const 左值 |
| `R(A...) &` | `&` | 非 const 左值 |
| `R(A...) const &` | `const &` | const 左值 |
| `R(A...) &&` | `&&` | 非 const 右值 |
| `R(A...) const &&` | `const &&` | const 右值 |

注意第一行：签名不带引用限定时，包装器的 `operator()` 在左值和右值上都能调用，但目标总是作为左值被调用。这和没有引用限定的成员函数处理 `*this` 的方式一致（[[over.match.funcs]]），也保证了这样的包装器可以反复调用。

## 能装什么：is-callable-from

[func.wrap.move.ctor] 第 1 段定义了构造函数共用的约束 *is-callable-from*<VT>（[[g:is-callable-from]]），`VT` 是要存进去的目标类型：

!!! std
    is_invocable_r_v<R, VT cv ref, ArgTypes...> && is_invocable_r_v<R, VT inv-quals, ArgTypes...>

*noex* 为 true 时，两处都换成 `is_nothrow_invocable_r_v`。也就是说，目标要能用两种方式调用、并把结果转换为 `R`：一是按签名的 *cv ref*，二是按 *inv-quals*。

- 签名带 `&` 或 `&&` 时，两者相同，只是一个条件。
- 签名不带引用限定时，第一个条件是 `VT cv`。`is_invocable` 的第一个实参不带引用表示右值，所以这一条检查以右值调用；第二个条件 `VT cv&` 检查以左值调用。目标必须两种都支持，只有 `operator()() &` 或只有 `operator()() &&` 的函数对象会被拒绝。

直观地说，不带引用限定的包装器对外承诺左值、右值都能调用，它装的目标也必须经得起这两种调用。

### const 漏洞的修复

```cpp run title="mof-const.cpp"
#include <functional>

int main() {
    auto counter = [n = 0]() mutable { return ++n; };

    std::move_only_function<int()> f = counter;            // OK：以非 const 左值调用
    // std::move_only_function<int() const> g = counter;   // error: 不满足 is-callable-from
    const auto& cf = f;
    // cf();                                                // error: operator() 不是 const 成员
    return f() == 1 ? 0 : 1;
}
```

`std::function` 的问题是 const 的包装器会以非 const 方式调用目标。在这里，两件事被拆成了两个类型：要能在 const 包装器上调用，就写 `int() const`，代价是只能装能以 const 左值调用的目标；写 `int()` 则可以装 `mutable` lambda，但包装器的 `operator()` 也不是 const 的。

`noexcept` 同样成了真正的约定：`move_only_function<void() noexcept>` 只接受 `is_nothrow_invocable` 的目标，它的 `operator()` 也确实是 `noexcept`。`std::function` 表达不了这一点。

## 转换构造函数（¶4–¶9）

`template<class F> move_only_function(F&& f)`，¶4 令 `VT` 为 `decay_t<F>`：

| 元素 | 内容 |
|---|---|
| ¶5 Constraints | `F` 不是 `move_only_function` 本身，也不是 `in_place_type_t` 的特化；*is-callable-from*<VT> |
| ¶6 Mandates | `is_constructible_v<VT, F>` |
| ¶7 Preconditions | `VT` 满足 *Cpp17Destructible*；如果 `VT` 可移动构造，还要满足 *Cpp17MoveConstructible* |
| ¶9 Throws | 目标初始化抛出的异常；除非 `VT` 是函数指针或 `reference_wrapper`，否则还可能抛 `bad_alloc` |

和 `std::function` 相比，Mandates 里没有可复制性。¶7 也只在 `VT` 可移动时才要求它满足移动构造的语义要求，这为后面不可移动的目标留出了空间。

¶8 下面三种情况得到空包装器：`f` 是空函数指针；`f` 是空成员指针；`f` 是空的 `move_only_function` 或 `copyable_function` 特化。其他情况下，目标是用 `std::forward<F>(f)` 直接非列表初始化的 `VT`。

!!! pitfall "用空的 std::function 构造，得到的不是空包装器"
    ¶8 的列表里没有 `std::function`。用一个空的 `std::function<void()>` 构造 `move_only_function<void()>`，得到的是一个非空的包装器，目标就是那个空的 `std::function`：

    ```cpp
    std::function<void()> empty;
    std::move_only_function<void()> m = empty;
    bool b = static_cast<bool>(m);   // true
    m();                             // 不是 UB：目标被调用，它抛出 bad_function_call
    ```

    于是 `if (m) m();` 这样的检查在这里不起作用。迁移旧代码时，如果来源可能是空的 `std::function`，要先判空再转换。

## 在包装器内部直接构造：in_place_type（¶10–¶21）

```cpp
template<class T, class... Args>
  explicit move_only_function(in_place_type_t<T>, Args&&... args);
template<class T, class U, class... Args>
  explicit move_only_function(in_place_type_t<T>, initializer_list<U> ilist, Args&&... args);
```

这两个构造函数用 `args...` 直接构造目标对象，中间不经过任何移动。因此目标可以是不可移动的类型，例如带 `std::mutex` 成员的函数对象：

```cpp run title="mof-in-place.cpp"
#include <functional>
#include <mutex>
#include <utility>

struct Guarded {
    std::mutex m;                   // Guarded 既不能复制也不能移动
    int n;
    explicit Guarded(int start) : n(start) {}
    int operator()() { std::lock_guard lk(m); return ++n; }
};

int main() {
    std::move_only_function<int()> f(std::in_place_type<Guarded>, 41);
    // std::move_only_function<int()> g = Guarded(41);   // error: 违反 Mandates，Guarded 不能由右值构造
    auto h = std::move(f);   // OK：只转移所有权
    return h() == 42 ? 0 : 1;
}
```

最后一行之所以可行，是因为不可移动的目标不可能放在包装器的内联缓冲区里（否则包装器自己就没法移动），它一定在堆上，移动包装器只需转移指针。

规格要点：

- ¶11、¶17 Constraints：`VT` 能从 `Args...`（或 `initializer_list<U>&, Args...`）构造，且满足 *is-callable-from*<VT>。
- ¶12、¶18 Mandates：`VT`（即 `decay_t<T>`）必须与 `T` 是同一类型。`in_place_type<const Foo>`、`in_place_type<Foo&>` 都是非良构的。
- 构造函数是 `explicit` 的，防止复制列表初始化无意中选中它。

## 调用空包装器是未定义行为

[func.wrap.move.inv] 第 1 段：`explicit operator bool()` 在有目标时返回 true。第 2–3 段规定了调用：

!!! std
    *Preconditions*: \*this has a target object.

效果等价于 `return INVOKE<R>(static_cast<F inv-quals>(f), std::forward<ArgTypes>(args)...);`，其中 `f` 是指代目标的左值，`F` 是它的类型。

| | `std::function` | `move_only_function` |
|---|---|---|
| 调用空包装器 | 抛 `bad_function_call` | 违反前条件，{{ub}} |
| 调用的开销 | 每次调用都隐含判空，或用一个会抛异常的空调用函数代替 | 不需要判空 |
| `noexcept` 签名 | 不能表达 | `noexcept(noex)` 成立 |

```cpp
std::move_only_function<void()> m;
m();   // UB：违反前条件
```

这是普通的前条件，不属于 C++26 的加固前条件（hardened precondition，[[structure.specifications]]），所以即使在加固实现（[[g:hardened-implementation]]）里，标准也不要求检查它。

`static_cast<F inv-quals>(f)` 在签名带 `&&` 时意味着以右值调用目标。这适合表达只能调用一次的任务：

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
    // f();                           // error: operator() 有 && 限定，f 是左值
    std::string s = std::move(f)();   // OK：目标以 OneShot&& 被调用
    return s == "hello" ? 0 : 1;
}
```

调用之后包装器仍然非空，`operator bool` 仍为 true。只能调用一次是写代码时的约定，类型并不强制。

## 赋值、析构与工具函数

- ¶22 移动赋值等价于 `move_only_function(std::move(f)).swap(*this)`，标准没有标 `noexcept`。
- ¶24 `operator=(nullptr_t) noexcept` 销毁目标（如果有）。
- ¶26 `template<class F> operator=(F&&)` 等价于 `move_only_function(std::forward<F>(f)).swap(*this)`。
- ¶28 析构函数销毁目标（如果有）。

[func.wrap.move.util] 提供成员 `swap`，以及两个隐藏友元（[[g:hidden-friend]]）：非成员 `swap` 和 `operator==(const move_only_function&, nullptr_t)`。隐藏友元只能通过实参依赖查找找到，不会出现在命名空间的普通重载集里。`!=` 和 `nullptr == m` 由 C++20 的重写候选合成。

和 `std::function` 不同，`move_only_function` 没有复制操作，没有 `target()`/`target_type()`，也没有推导指引。

## 小对象优化

[func.wrap.move.class] 第 2 段建议实现避免为小的目标对象动态分配，注 1 补充了一个限制：

!!! std
    Such small-object optimization can only be applied to a type T for which is_nothrow_move_constructible_v<T> is true.

这条注是推论，不是额外规定。`move_only_function` 的移动构造函数是 `noexcept`（[func.wrap.move.ctor] 第 3 段）。目标放在内联缓冲区里时，移动包装器就要移动目标；目标的移动可能抛异常的话，`noexcept` 就无法兑现。目标在堆上时，只需转移指针。

## 包装器之间的转换

¶8 把空的 `copyable_function` 也算作空，说明标准预期包装器之间会互相转换。[[func.wrap]] 第 3 段建议实现在这种转换中避免双重包装，例如从 `copyable_function` 构造 `move_only_function` 时直接接管它的内部存储。第 2 段则允许嵌套包装器的按值实参互相别名，所以这种情况下实参被复制几次是未指明的。

## 思考题

!!! question "思考题 1"
    下面哪些类型能装进 `std::move_only_function<void()>`？
    ```cpp
    struct A { void operator()() &; };
    struct B { void operator()() &&; };
    struct C { void operator()() const; };
    struct D { void operator()(); };
    ```

<details markdown="1">
<summary>答案</summary>

签名不带引用限定，*is-callable-from* 要求 `is_invocable_r_v<void, VT>`（右值）和 `is_invocable_r_v<void, VT&>`（左值）同时成立。

- `A` 只能以左值调用，不行；
- `B` 只能以右值调用，不行；
- `C` 的 const 成员函数在任何值类别上都能调用，可以；
- `D` 没有引用限定，左值、右值都能调用，可以。

要装 `A`，用 `move_only_function<void() &>`；要装 `B`，用 `move_only_function<void() &&>`。
</details>

!!! question "思考题 2"
    为什么 `in_place_type<T>` 构造要求 `decay_t<T>` 与 `T` 完全相同，而不是像转换构造函数那样自动退化？

<details markdown="1">
<summary>答案</summary>

`in_place_type<T>` 的意思是在包装器里构造一个类型为 `T` 的对象。如果 `T` 是 `const Foo` 或 `Foo&` 而被悄悄退化，实际存的类型就和写下的不一致：`const` 丢了，调用时就不再是 const 对象；引用变成了值，本想引用外部对象，得到的却是副本。与其静默改变含义，不如直接拒绝。转换构造函数的实参是一个现成的表达式，按值存储时退化是自然的结果。
</details>
