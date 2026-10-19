---
title: 可复制包装器 copyable_function
summary: C++26 的 copyable_function 按 move_only_function 的设计重做了 std::function：可以复制，签名可带 const、& 和 noexcept，调用空包装器是未定义行为。
status: draft
covers: *
since: c++26
papers: P2548R6
related: func.wrap, func.wrap.func, func.wrap.move, func.wrap.ref, func.require, structure.specifications
tags: 标准库, functional, 类型擦除, C++26
updated: 2026-10-19
---

!!! tldr
    - `copyable_function` 是可以复制的 `move_only_function`：签名限定、*inv-quals*、*is-callable-from*、空调用是 UB，这些规则都相同。
    - 它要求目标可复制。和 `std::function` 一样，这是 Mandates：`is_constructible` 为 true 不代表真能构造。
    - 从 `std::function` 迁移时，要写 `copyable_function<void() const>` 才能在 const 成员函数里调用；只写 `void()` 能编译，却得不到 const 正确性。
    - 用空的 `std::function` 构造它得到非空包装器；`move_only_function` 根本不能用来构造它。

!!! warning "实现状态"
    本机 libc++（LLVM 23）还没有实现 `copyable_function`，`<version>` 里的 `__cpp_lib_copyable_function` 是注释掉的。本页的例子无法在本机编译，所以不标判定。

## 它填补的空位

C++23 有了 const 正确、支持 `noexcept` 的 [[func.wrap.move|move_only_function]]，但它不能复制。需要复制回调的地方，比如要被复制的配置对象、要分发给多个订阅者的处理函数，只能退回到有 const 漏洞的 `std::function`（[[func.wrap.func]]）。`copyable_function`（{{c++26}}，[[P2548R6]]）补上了这个空位。

它的条文几乎是 [func.wrap.move] 的逐字复制，再加上复制操作。下面这些与 `move_only_function` 完全相同，细节见 [[func.wrap.move]]：

- [func.wrap.copy.general]：`R(ArgTypes...) cv ref noexcept(noex)` 的 12 个偏特化，*inv-quals* 的定义；
- [func.wrap.copy.class] 第 2 段：建议做小对象优化，并且只能用于 nothrow 可移动的类型；
- [func.wrap.copy.ctor] 第 1 段：约束 *is-callable-from*；
- [func.wrap.copy.inv]：调用空包装器违反前条件（{{ub}}），调用效果是 `INVOKE<R>(static_cast<F inv-quals>(f), std::forward<ArgTypes>(args)...)`；
- [func.wrap.copy.util]：成员 `swap`，隐藏友元 `swap` 和 `operator==(f, nullptr)`；
- 没有 `target()`/`target_type()`，没有推导指引。

## 从 std::function 迁移

```cpp run title="copyable-migrate.cpp"
#include <functional>

struct Button {
    std::copyable_function<void() const> on_click;
    void click() const { on_click(); }        // OK：operator() 是 const
};

struct Button2 {
    std::copyable_function<void()> on_click;
    void click() const { /* on_click(); */ }  // 取消注释则 error：operator() 不是 const
};

int main() {
    int clicks = 0;
    Button b{[&clicks] { ++clicks; }};        // OK：lambda 本身能以 const 方式调用
    // Button bad{[n = 0]() mutable { ++n; }}; // error: mutable lambda 不能以 const 左值调用
    Button copy = b;                           // OK：可以复制
    copy.click();
    b.click();
    return clicks == 2 ? 0 : 1;
}
```

把 `std::function<void()>` 机械地换成 `copyable_function<void()>` 是能编译的：签名不带 `const` 时，目标以非 const 左值调用，`mutable` lambda 照样能装。但这样的包装器 `operator()` 也不是 const 的，在 const 成员函数里调用它会失败（上例的 `Button2`）。想在 const 上下文中调用，就要写 `void() const`，并接受它只能装能以 const 方式调用的目标。

逐条对比：

| | `std::function<R(A...)>` | `std::copyable_function<R(A...) const>` |
|---|---|---|
| const 包装器调用非 const 目标 | 允许（const 漏洞） | 构造时就拒绝 |
| `noexcept` 签名 | 不能表达 | `R(A...) const noexcept` |
| 调用空包装器 | 抛 `bad_function_call` | {{ub}} |
| 从空的 `std::function` 构造 | 得到空包装器 | 得到非空包装器，目标是那个空 `function` |
| `target()`、`target_type()` | 有 | 无 |
| 类模板实参推导 | 有 | 无 |
| 复制一个装着函数指针的包装器 | 不抛异常 | 规格上可能抛 `bad_alloc` |

## 比 move_only_function 多出的规则

### 复制构造（¶3–¶4）

¶3 `f` 没有目标时，结果也没有；否则目标是 `f` 的目标的副本。

¶4 Throws：目标初始化抛出的异常，并且可能抛 `bad_alloc`，没有例外。`std::function` 的复制构造在目标是函数指针或 `reference_wrapper` 时保证不抛出（[[func.wrap.func]]），`copyable_function` 的转换构造函数有这项保证（¶11），复制构造却没有。实现如果把这两类目标放在内联缓冲区里，复制自然不会分配，但标准不保证这一点。

¶24 复制赋值等价于 `copyable_function(f).swap(*this)`，即复制后交换，提供强异常安全保证。

### 可复制性是 Mandates（¶7–¶11）

| 元素 | `move_only_function` | `copyable_function` |
|---|---|---|
| Constraints | 不是自身，不是 `in_place_type_t`，*is-callable-from* | 相同（¶7） |
| Mandates | `is_constructible_v<VT, F>` | 再加 `is_copy_constructible_v<VT>`（¶8.2） |
| Preconditions | *Cpp17Destructible*；可移动时 *Cpp17MoveConstructible* | *Cpp17Destructible* 和 *Cpp17CopyConstructible*（¶9） |

与 `std::function` 一样，可复制性放在 Mandates 里：对一个只能移动的 lambda，`is_constructible_v<copyable_function<void()>, decltype(lambda)>` 为 true，真正构造时才报硬错误。理由也一样：包装器的复制构造函数要能复制它可能装着的任何目标，复制目标的代码在构造时就得实例化。

`in_place_type` 构造（¶12–¶23）同理，Mandates 在 `VT` 与 `T` 相同之外，加上了 `is_copy_constructible_v<VT>`。前条件 *Cpp17CopyConstructible* 包含了 *Cpp17MoveConstructible*，所以 `copyable_function` 不能像 `move_only_function` 那样装不可移动的类型。

### 什么时候得到空包装器（¶10）

¶10 三种情况：空函数指针、空成员指针、空的 `copyable_function` 特化。

列表里没有 `move_only_function`，这不是遗漏：`move_only_function` 不可复制，违反 ¶8.2，根本不能用来构造 `copyable_function`。和 `move_only_function` 一样，列表里也没有 `std::function`，用空的 `std::function` 构造得到的是非空包装器，调用时由里面的 `std::function` 抛 `bad_function_call`。

## 与其他包装器互相转换

- `copyable_function` 转为 `move_only_function`：可以。空的 `copyable_function` 得到空的 `move_only_function`（[func.wrap.move.ctor] 第 8 段），[[func.wrap]] 第 3 段建议实现直接接管内部存储，避免双重包装。
- `move_only_function` 转为 `copyable_function`：非良构（Mandates）。
- `copyable_function` 转为 `function_ref`：可以，`function_ref` 引用的是这个包装器对象本身（[[func.wrap.ref]]），要注意生命周期。

<details class="fine" markdown="1"><summary>其余条文</summary>

¶11 说的是除非 `VT` 是函数指针或 `reference_wrapper` 特化，否则可能抛 `bad_alloc`；¶17 和 ¶23（两个 `in_place_type` 构造）写的却是指针或 `reference_wrapper` 特化。字面上后者覆盖所有指针类型，但 *is-callable-from* 要求 `VT` 本身可调用，对象指针不可调用，所以实际能落入这一分支的只有函数指针，两种措辞效果相同。`move_only_function` 对应的段落都写的是函数指针。

¶2 默认构造和 `nullptr_t` 构造得到空包装器。¶5 移动构造是 `noexcept`，被移动的对象处于有效但未指明的状态。¶26–¶32 的移动赋值、`nullptr` 赋值、模板赋值和析构函数与 `move_only_function` 相同。

</details>

## 思考题

!!! question "思考题 1"
    为什么不直接给 `std::function` 加上 `const`、引用限定和 `noexcept` 的偏特化，而要另起一个名字？

<details markdown="1">
<summary>答案</summary>

`std::function<R(A...)>` 现有的两项行为都不能改：它的 const `operator()` 会调用非 const 目标，收紧这一点会让所有装着 `mutable` lambda、在 const 上下文中调用的代码编译失败；调用空包装器抛 `bad_function_call` 也是现有代码依赖的行为，改成 UB 是静默的语义破坏。如果只增加 `function<R(A...) const>` 这类新偏特化，同一个模板的不同特化就会有截然不同的 const 语义和空调用语义，很容易混淆。另起名字让新旧两套语义各自一致。
</details>

!!! question "思考题 2"
    `std::is_constructible_v<std::copyable_function<void()>, std::move_only_function<void()>>` 是 true 还是 false？

<details markdown="1">
<summary>答案</summary>

按标准是 true。trait 只反映约束：`move_only_function<void()>` 不是 `copyable_function`，不是 `in_place_type_t`，并且它的 `operator()` 没有引用限定、也不是 const，左值和右值都能调用，*is-callable-from* 成立。不可复制是 Mandates 层面的问题，只在真正构造时报错。对标准库类型来说，`is_constructible` 为 true 不等于能编译。
</details>
