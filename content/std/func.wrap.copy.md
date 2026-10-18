---
title: 可复制包装器 copyable_function
summary: C++26 的 copyable_function——"修好了的 std::function"：可复制、签名带 cv/ref/noexcept、const 正确，空调用改为前条件违反；与 function 和 move_only_function 的逐条差异
status: draft
covers: *
since: c++26
papers: P2548R6
related: func.wrap, func.wrap.func, func.wrap.move, func.wrap.ref, func.require, structure.specifications
tags: 标准库, functional, 类型擦除, C++26
updated: 2026-10-18
---

`copyable_function`（{{c++26}}，[[P2548R6]]）的条文几乎是 [[func.wrap.move]] 的逐字复制，再加上复制操作。它填补的是一个空位：C++23 有了 const 正确、支持 `noexcept` 的 `move_only_function`，但需要**可复制**回调的地方（例如要被复制的配置对象、要被多个订阅者共享的处理器）只能退回到有 const 漏洞的 `std::function`。`copyable_function` 就是"用 `move_only_function` 的设计重做一遍 `std::function`"。

本页只讲它与两个兄弟的**差异**；*inv-quals*、*is-callable-from*、`in_place_type` 构造等共有机制请看 [[func.wrap.move]]。

!!! warning "实现状态"
    截至本文编写时，libc++（LLVM 23.1）**尚未实现** `copyable_function`：`<version>` 中 `__cpp_lib_copyable_function`（`202306L`）被注释掉。本页示例未经本地验证，不标判定。

## 与 move_only_function 共有的部分（[func.wrap.copy.general]、[func.wrap.copy.class]）

- [func.wrap.copy.general] ¶1–2：同样是 *cv* × *ref* × *noex* 的 12 个偏特化，*inv-quals* 的定义相同；
- [func.wrap.copy.class] ¶2：同样的 SBO 推荐与"只能用于 nothrow-move 类型"的注；
- [func.wrap.copy.ctor] ¶1：*is-callable-from* 的定义一字不差；
- [func.wrap.copy.inv] ¶2–3：空调用是*前条件*违反（{{ub}}），调用效果是 `INVOKE<R>(static_cast<F inv-quals>(f), std::forward<ArgTypes>(args)...)`；
- [func.wrap.copy.util]：成员 `swap`、隐藏友元 `swap` 与 `operator==(f, nullptr)`；
- 同样**没有** `target()`/`target_type()`，**没有**推导指引。

## 新增与不同之处（[func.wrap.copy.ctor]）

### 复制构造（¶3–4）

¶3：若 `f` 没有目标，`*this` 也没有；否则目标是 `f` 目标的副本。¶4 *Throws*：目标初始化抛出的异常，**并且可能抛 `bad_alloc`**——无条件。

对比 `std::function` 的复制构造（[[func.wrap.func]] 的 [func.wrap.func.con] ¶4）：目标是函数指针或 `reference_wrapper` 时**不抛出**。`copyable_function` 的复制构造函数没有这项保证——它的转换构造函数（¶11）有，复制构造却没有。实现若对这两类目标做内联存储，复制自然不会分配，但标准层面你不能依赖。

### 转换构造的 *Mandates* 多了可复制性（¶7–11）

| 元素 | `move_only_function` | `copyable_function` |
|---|---|---|
| *Constraints* | 非自身、非 `in_place_type_t`、*is-callable-from* | 相同 |
| *Mandates* | `is_constructible_v<VT, F>` | 再加 `is_copy_constructible_v<VT>`（¶8.2） |
| *Preconditions* | *Cpp17Destructible*；可移动时 *Cpp17MoveConstructible* | *Cpp17Destructible* 与 *Cpp17CopyConstructible*（¶9） |

与 `std::function` 一样，可复制性是 *Mandates*：`is_constructible_v<copyable_function<void()>, MoveOnlyLambda>` 为 **true**，真正构造时才硬错误。理由也一样：包装器的复制构造函数必须能复制任何可能被装进来的目标，复制函数在构造时就必须实例化。

`in_place_type` 构造（¶12–23）同理，*Mandates* 在"`VT` 与 `T` 相同"之外加上 `is_copy_constructible_v<VT>`。因此 `copyable_function` **不能**像 `move_only_function` 那样装不可移动的类型——可复制的类型一定可以用复制来"移动"。

### 空状态的来源（¶10）

转换构造在以下情况得到空包装器：空函数指针、空成员指针、**空的 `copyable_function` 特化**。

与 `move_only_function` 的 ¶8 相比，列表里少了 `move_only_function`——这不是遗漏：`move_only_function` 不可复制，违反 ¶8.2 的 *Mandates*，根本不能用来构造 `copyable_function`。和 `move_only_function` 一样，**空的 `std::function` 不在列表里**：用它构造得到一个非空的 `copyable_function`，调用时由内层的 `std::function` 抛 `bad_function_call`（[[func.wrap.move]] 有完整示例）。

!!! lawyer "措辞上的一处不一致"
    ¶11（转换构造）说"除非 `VT` 是**函数指针**或 `reference_wrapper` 特化，否则可能抛 `bad_alloc`"；而 ¶17 与 ¶23（两个 `in_place_type` 构造）写的是"除非 `VT` 是**指针**或 `reference_wrapper` 特化"。按字面，后者覆盖所有指针类型。但 *is-callable-from* 要求 `VT` 本身可调用，而对象指针不是可调用类型（*INVOKE* 不会解引用对象指针去调用它的 `operator()`；成员指针也不是 `is_pointer` 意义上的指针），所以能落入"指针"分支的实际上只有函数指针，两种措辞效果等价。`move_only_function` 对应的 ¶15、¶21 写的都是"函数指针"。这是编辑性差异，不影响语义。

### 复制赋值（¶24）

`operator=(const copyable_function& f)` 等价于 `copyable_function(f).swap(*this)`——copy-and-swap，强异常安全。其余赋值与 `move_only_function` 相同。

## 从 function 迁移：逐条差异

| | `std::function<R(A...)>` | `std::copyable_function<R(A...) const>` |
|---|---|---|
| 以 const 包装器调用非 const 目标 | 允许（漏洞） | 构造时就拒绝 |
| `noexcept` 签名 | 不能表达 | `R(A...) const noexcept` |
| 空调用 | 抛 `bad_function_call` | {{ub}} |
| 从空 `std::function` 构造 | 得到空 | 得到**非空**（目标是空 `function`） |
| `target()`、`target_type()` | 有 | 无 |
| CTAD | 有 | 无 |
| 复制构造对函数指针目标 | 不抛出 | 可能抛 `bad_alloc`（规格上） |

迁移时最容易漏的是第一行：`std::function<void()>` 机械替换成 `copyable_function<void()>`（**不带 const**）是能编译的，因为 *inv-quals* 为非 const 左值、可以装 `mutable` lambda；但这样的包装器 `operator()` 也不是 const 的，`const` 成员函数里调用它会编译失败。想要 const 可调用就必须写 `void() const`，并接受它只能装 const 可调用的目标。

```cpp run title="copyable-migrate.cpp"
#include <functional>

struct Button {
    std::copyable_function<void() const> on_click;
    void click() const { on_click(); }        // OK：operator() 是 const
};

struct Button2 {
    std::copyable_function<void()> on_click;
    void click() const { /* on_click(); */ }  // error（若取消注释）：operator() 不是 const
};

int main() {
    int clicks = 0;
    Button b{[&clicks] { ++clicks; }};        // OK：修改的是被引用的外部对象，lambda 本身 const 可调用
    // Button bad{[n = 0]() mutable { ++n; }}; // error: mutable lambda 不能以 const 左值调用
    Button copy = b;                           // OK：可复制
    copy.click();
    b.click();
    return clicks == 2 ? 0 : 1;
}
```

## 与其他包装器互相转换

- `copyable_function` → `move_only_function`：可以（目标可复制，自然可移动）；空的 `copyable_function` 得到空的 `move_only_function`（[func.wrap.move.ctor] ¶8.3），实现被鼓励直接接管存储，避免双重包装（[[func.wrap]] ¶3）；
- `move_only_function` → `copyable_function`：非良构（*Mandates*）；
- `copyable_function` → `function_ref`：可以，`function_ref` 引用这个包装器对象本身（[[func.wrap.ref]]），要注意生命周期。

## 思考题

!!! question "思考题 1"
    为什么不直接修改 `std::function`，给它加上 cv/ref/noexcept 的偏特化，而要另起一个名字？

<details markdown="1">
<summary>展开查看答案与解析</summary>

两点不能动：`std::function<R(A...)>::operator()` 是 const 且会调用非 const 目标——收紧它会让所有装着 `mutable` lambda、在 const 上下文调用的现有代码编译失败；空调用抛 `bad_function_call` 也是现有代码依赖的可观察行为，改成 UB 是静默的语义破坏。而只增加 `function<R(A...) const>` 等新偏特化，会让同一个模板下 `function<R(A...)>` 与 `function<R(A...) const>` 的空调用语义、const 语义截然不同，极易混淆。另起名字让新旧语义各自一致。
</details>

!!! question "思考题 2"
    `std::is_constructible_v<std::copyable_function<void()>, std::move_only_function<void()>>` 是 true 还是 false？

<details markdown="1">
<summary>展开查看答案与解析</summary>

按标准是 **true**。trait 只反映 *Constraints*：`move_only_function<void()>` 不是 `copyable_function`、不是 `in_place_type_t`，而且以左值和右值都能调用（无 ref 限定的非 const `operator()`），*is-callable-from* 成立。不可复制是 *Mandates* 层面的问题，只在真正构造时报错。这再次说明：对标准库类型，`is_constructible` 为 true 不等于"能编译"。
</details>

## 小结

| 主题 | 要点 |
|---|---|
| 定位 | 用 `move_only_function` 的设计重做的可复制 `std::function` |
| 额外 *Mandates* | `is_copy_constructible_v<VT>`（转换构造与 `in_place_type` 构造） |
| 复制构造 | 复制目标；可能抛 `bad_alloc`（无函数指针例外） |
| 空状态来源 | 空函数指针、空成员指针、空 `copyable_function`；空 `std::function` 不算 |
| 空调用 | 前条件违反 → UB |
| 不能装 | move-only 目标、不可移动目标、`move_only_function` |
| libc++ 23 | 未实现 |
