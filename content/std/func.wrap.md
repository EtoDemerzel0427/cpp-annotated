---
title: 多态函数包装器
summary: function / move_only_function / copyable_function / function_ref 四种类型擦除的可调用包装器总览——所有权、可复制性、签名限定符、空状态行为与擦除成本的对照；外加包装器互相嵌套时的实参别名许可与 bad_function_call
status: draft
covers: func.wrap.general, func.wrap.badcall
papers: P0288R9, P2548R6, P0792R14
related: func.wrap.func, func.wrap.move, func.wrap.copy, func.wrap.ref, func.require, function.objects, func.def, refwrap, const.wrap.class
tags: 标准库, functional, 类型擦除, 可调用对象
updated: 2026-10-18
---

C++ 里"可调用的东西"五花八门：函数指针、成员指针、lambda（每个都有独一无二的闭包类型）、带 `operator()` 的类、`std::bind` 的结果……模板可以把它们一视同仁，但模板会把调用方的类型"传染"到接口上：一个想保存回调的类，要么自己变成模板，要么就需要一个**固定的类型**来装下任意可调用对象。这就是 [func.wrap] 的四个**多态函数包装器**（*polymorphic function wrapper*，[[g:polymorphic-function-wrapper]]）要解决的问题——它们用**类型擦除**（[[g:type-erasure]]）把"具体是什么类型"藏到运行时，只在类型里留下**调用签名**（*call signature*，[[func.def]]）。

四个包装器是按年代逐个补上的，每一个都在修补前一个的设计缺陷：

| 包装器 | 引入 | 页面 | 一句话 |
|---|---|---|---|
| `function<R(Args...)>` | C++11 | [[func.wrap.func]] | 拥有、可复制；空调用抛异常；有 const 正确性漏洞 |
| `move_only_function<R(Args...) cv ref noexcept(b)>` | C++23 | [[func.wrap.move]] | 拥有、仅可移动；签名可带 cv/ref/noexcept |
| `copyable_function<R(Args...) cv ref noexcept(b)>` | {{c++26}} | [[func.wrap.copy]] | "修好了的 `function`"：可复制 + 签名限定符 |
| `function_ref<R(Args...) cv noexcept(b)>` | {{c++26}} | [[func.wrap.ref]] | 不拥有，两个指针宽，平凡可复制，适合作函数参数 |

它们的调用语义都落在 *INVOKE*<R>（[[func.require]]）上：成员指针、函数指针、函数对象统一处理，`R` 为 `void` 时丢弃返回值，`R` 是引用而结果会绑定临时量时 *INVOKE*<R> 非良构。

## 四者对照

| 维度 | `function` | `move_only_function` | `copyable_function` | `function_ref` |
|---|---|---|---|---|
| 所有权 | 拥有目标对象 | 拥有 | 拥有 | **不拥有**：只存指针 + thunk |
| 包装器自身 | 可复制 | 仅可移动 | 可复制 | 平凡可复制 |
| 对目标的要求 | 必须可复制（*Mandates*） | 只需可构造，可以是 move-only | 必须可复制（*Mandates*） | 无（只取地址） |
| 签名中的 cv | 不支持 | `const` 或空 | `const` 或空 | `const` 或空 |
| 签名中的 ref | 不支持 | `&`、`&&` 或空 | `&`、`&&` 或空 | 不支持 |
| 签名中的 noexcept | 不支持 | 支持 | 支持 | 支持 |
| const 正确性 | **有漏洞**：`const` 的 `operator()` 调用非 const 目标 | 由 *inv-quals* 保证 | 同左 | 由 cv 保证 |
| 空状态 | 有；调用抛 `bad_function_call` | 有；调用违反前条件 → {{ub}} | 同左 | **没有**空状态（无默认构造） |
| `operator bool` / `== nullptr` | 有 | 有 | 有 | 无 |
| `target()` / `target_type()` | 有（需要 RTTI） | 无 | 无 | 无 |
| 小对象优化 | 推荐；函数指针与 `reference_wrapper` 构造不得抛出（等于强制） | 推荐；只可能用于 nothrow-move 的类型 | 同左 | 不适用：从不分配 |
| CTAD | 有 | 无 | 无 | 有 |
| freestanding | 否 | 否 | 否 | **是** |
| libc++ 23 | 已实现 | **未实现** | **未实现** | **未实现** |

几点解读：

- **"空状态"的处理反映了不同时代的取舍。** `function` 诞生时把"调用空包装器"定义成抛 `bad_function_call`，这意味着每次调用都要隐含一次判空（或者像 libc++ 那样把空状态实现成一个"会抛异常的 thunk"）。后来的 `move_only_function` / `copyable_function` 把它改成 *Preconditions*：调用空对象是未定义行为，实现不必为它付任何代价。`function_ref` 干脆**不允许存在空状态**：没有默认构造函数，从空函数指针构造违反前条件。
- **const 正确性**：`function::operator()` 是 `const` 成员，却能调用目标的非 const `operator()`，这是 [[func.wrap.func]] 里详细讨论的老漏洞。新包装器把 `const` 写进签名：`move_only_function<void() const>` 只接受能以 const 左值调用的目标。
- **ref 限定**：`move_only_function<void() &&>` 表示"只能作为右值调用一次"，用于一次性任务（调用时以 `std::move(target)` 调用目标）。`function_ref` 不支持 ref 限定，因为它从不拥有目标，"把目标当右值"没有意义。

## 类型擦除的代价

把类型藏起来不是免费的。一个拥有型包装器通常由三部分组成：一块内联缓冲区（[[g:small-object-optimization]]，或指向堆的指针）、一个"如何调用"的函数指针、一个"如何复制/移动/销毁"的操作表（虚表或手写的 policy 表）。代价是：

1. **一次间接调用**，编译器一般无法内联目标（除非整个构造—调用链都可见，去虚化成功）；
2. **可能的堆分配**——目标装不进内联缓冲区，或者移动/复制可能抛异常时；
3. **复制成本**——`function` 的复制会深拷贝目标，`std::vector<std::function<...>>` 扩容时尤其明显（`function` 的移动构造函数是 `noexcept` 的，扩容会走移动，这一点还好）；
4. **体积**：libc++ 的 `std::function<int(int)>` 在 64 位平台上是 32 字节；`function_ref` 只有两个指针宽。

`function_ref` 是唯一没有 2、3 两项成本的包装器：它的构造函数全部是 `noexcept` 的，从不分配；它的复制就是复制两个指针。代价转移到了**生命周期**上——见 [[func.wrap.ref]] 的悬垂讨论。

!!! tip "选型经验"
    - 函数**参数**里只在调用期间用一下的回调 → `function_ref`（或者干脆用模板）；
    - 需要**保存**下来、且目标可能是 move-only（捕获了 `unique_ptr`、`promise`）→ `move_only_function`；
    - 需要保存且包装器本身要可复制 → `copyable_function`；`function` 只为兼容旧接口保留。

## 包装器套包装器：实参别名许可（[func.wrap.general] ¶2–3）

¶1 只是说本节描述"封装任意可调用对象的多态包装类"。真正有法律分量的是 ¶2：

!!! std
    Each argument of the invocation of x evaluated as part of the invocation of t may alias an argument in the same position in the invocation of t that has the same type, even if the corresponding parameter is not of reference type.

    当包装器 t 的目标对象 x 本身也是这四种包装器之一时，调用 t 过程中对 x 的调用，其每个实参都**可以与** t 的调用中同位置、同类型的实参是同一个对象——即使对应形参不是引用类型。

为什么需要这样一条许可？考虑一个按值传参的签名 `void(T)`：

```cpp
move_only_function<void(T)> f{copyable_function<void(T)>{[](T) {}}};
T t;
f(t);   // 复制几次 T？
```

朴素实现下，`f(t)` 先把 `t` 复制进 `f.operator()` 的形参（第 1 次），再把形参转发给内层 `copyable_function::operator()` 的**按值**形参（又一个对象），内层再转发给 lambda 的按值形参（再一个对象）。层层包装，层层构造。¶2 允许实现让内层调用的形参直接"就是"外层的那个形参对象——这在核心语言里是不可能的（两个按值形参必然是两个不同的对象，见 [[expr.call]]），所以必须由库条文**显式授权**。代价是：标准的例子明说**复制次数是未指明的**（{{unspec}}）。如果 `T` 的复制构造函数有可观察副作用，你不能依赖它被调用的次数。

¶3 是配套的 *Recommended practice*：从一种包装器构造另一种时，实现**应当避免双重包装**（[[g:double-wrapping]]）。例如用一个 `copyable_function` 去构造 `move_only_function`，理想的实现会直接"接管"内层的存储和调用 thunk，而不是在外面再包一层；`function_ref` 从另一个签名兼容的 `function_ref` 构造时直接复制它的两个指针（[[func.wrap.ref]] ¶8–9）。¶2 的别名许可正是让这种"拆包"在可观察行为上合法的前提——拆包之后少了一层按值传参，复制次数自然变了。

!!! lawyer "许可的边界"
    ¶2 只在**目标对象的类型本身是四种包装器之一的特化**时适用。如果目标是一个自己写的、内部转发的函数对象，标准没有给出任何别名许可，实参按 [[expr.call]] 正常初始化。另外，"同类型"是硬条件：`function_ref<void(std::string)>` 包装一个 `function_ref<void(std::string&&)>` 时，两层形参类型不同，不在许可范围内（实现另有 [[func.wrap.ref]] ¶9 的专门许可）。

## `bad_function_call`（[func.wrap.badcall]）

¶1：`bad_function_call` 派生自 `std::exception`，**只有** `function::operator()` 在包装器为空时抛出它（[[func.wrap.func]] 的 [func.wrap.func.inv]）。其他三个包装器从不抛它——`move_only_function`/`copyable_function` 的空调用是前条件违反，`function_ref` 没有空状态。

¶2：`what()` 返回一个由实现定义的 NTBS（{{impl}}）。它的特殊成员函数按 [[exception]] 的统一规定（复制不抛异常等）。

```cpp run title="bad-call.cpp" ok
#include <functional>
#include <cstdio>

int main() {
    std::function<void()> f;          // 空
    try {
        f();
    } catch (const std::bad_function_call& e) {
        std::puts(e.what());          // 内容由实现定义
        return 0;
    }
    return 1;
}
```

!!! impl "libc++"
    libc++ 在 `__functional/function.h` 中用 `__throw_bad_function_call()` 抛出；在 `-fno-exceptions` 模式下改为调用 `_LIBCPP_VERBOSE_ABORT` 终止程序。`what()` 的消息文本取决于部署目标是否提供新版的 dylib（宏 `_LIBCPP_AVAILABILITY_HAS_BAD_FUNCTION_CALL_GOOD_WHAT_MESSAGE`），所以在不同 macOS 版本上打印的字符串可能不同——这正是"由实现定义"的现实含义。

## 实现现状

截至本文编写时（LLVM 23.1），libc++ 的 `<version>` 中 `__cpp_lib_move_only_function`、`__cpp_lib_copyable_function`、`__cpp_lib_function_ref` 三个特性测试宏均被注释掉——**libc++ 尚未实现这三个包装器**（它已经有一个为 `move_only_function` 准备的内部工具 `__utility/small_buffer.h`，但类本身还没有落地）。libstdc++ 与 MSVC STL 已经提供 `move_only_function`。本站 [[func.wrap.move]]、[[func.wrap.copy]]、[[func.wrap.ref]] 中的示例因此无法用本地 libc++ 验证，凡未验证者均不标判定，请借助代码块上的 godbolt 按钮用 GCC trunk 试验。

!!! history
    - C++11：`std::function` 从 TR1（源自 Boost.Function）进入标准。
    - C++17：[[P0302R1]] 删除了 `function` 的分配器支持（`allocator_arg_t` 构造函数和 `assign`），因为从未被一致地实现；同时加入 CTAD 推导指引。
    - C++23：[[P0288R9]] 加入 `move_only_function`，第一次把 cv/ref/noexcept 写进包装器签名。
    - C++26：[[P2548R6]] 加入 `copyable_function`；[[P0792R14]] 加入 `function_ref`。

## 思考题

!!! question "思考题 1"
    为什么 `move_only_function` 的空调用选择了"前条件违反（UB）"而不是像 `function` 那样抛 `bad_function_call`？这对 `noexcept` 签名意味着什么？

<details markdown="1">
<summary>展开查看答案与解析</summary>

如果空调用必须抛异常，那么 `move_only_function<void() noexcept>` 的 `operator()` 就无法是 `noexcept` 的——要么违反自己的异常规格，要么只能 `terminate`。把它定为前条件后，实现可以让空状态的 thunk 什么都不检查（甚至直接调用一个空指针），`noexcept(noex)` 签名得以成立，非空调用也省掉了判空分支。代价是错误从"可捕获的异常"变成了 {{ub}}，需要调用方自己保证非空（[[func.wrap.move]] 的 [func.wrap.move.inv] ¶2）。
</details>

!!! question "思考题 2"
    `T` 的复制构造函数里有 `++copies`。`move_only_function<void(T)> f{copyable_function<void(T)>{[](T){}}}; f(t);` 之后，标准能保证 `copies` 的值吗？如果把内层换成一个自己写的转发函数对象 `struct Fwd { copyable_function<void(T)> g; void operator()(T x) { g(std::move(x)); } };` 呢？

<details markdown="1">
<summary>展开查看答案与解析</summary>

第一种情况不能：目标是包装器特化，[func.wrap.general] ¶2 允许实参别名，复制次数未指明。第二种情况外层的目标 `Fwd` 不是包装器特化，¶2 对"外层 → `Fwd`"这一层不适用，外层到 `Fwd::operator()` 的形参必须按核心语言规则初始化；但 `Fwd` 内部调用 `g`（`copyable_function`，其目标是 lambda，不是包装器）也不在许可范围。于是所有构造都按 [[expr.call]] 正常发生，次数（复制与移动分别多少次）是确定的。
</details>

## 小结

| 问题 | 答案 |
|---|---|
| 想保存回调、目标可能 move-only | `move_only_function`（C++23） |
| 想保存回调、包装器要可复制、要 const 正确 | `copyable_function`（C++26） |
| 只是参数、不保存 | `function_ref`（C++26），注意悬垂 |
| 哪个空调用会抛异常 | 只有 `function`，抛 `bad_function_call` |
| 包装器套包装器时复制次数 | 未指明（¶2 别名许可） |
| 实现应避免什么 | 双重包装（¶3，推荐做法，非强制） |
