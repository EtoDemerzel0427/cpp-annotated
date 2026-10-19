---
title: 多态函数包装器
summary: function、move_only_function、copyable_function、function_ref 四种用类型擦除装下任意可调用物的包装器的对照：所有权、可复制性、签名限定、空状态和开销；以及 bad_function_call 和包装器互相嵌套时的实参别名许可。
status: done
covers: func.wrap.general, func.wrap.badcall
papers: P0288R9, P2548R6, P0792R14, P0302R1
related: func.wrap.func, func.wrap.move, func.wrap.copy, func.wrap.ref, func.require, function.objects, func.def, refwrap, const.wrap.class
tags: 标准库, functional, 类型擦除, 可调用对象
updated: 2026-10-19
---

!!! tldr
    - 四个包装器都用类型擦除把任意可调用物装进一个只由调用签名决定的类型：`function`（C++11）、`move_only_function`（C++23）、`copyable_function`（C++26）、`function_ref`（C++26）。
    - 前三个拥有目标对象；`function_ref` 不拥有，只有两个指针大，从不分配内存，但要自己保证目标活得够久。
    - 只有 `function` 在空调用时抛 `bad_function_call`。`move_only_function` 和 `copyable_function` 的空调用是前置条件违反，`function_ref` 根本没有空状态。
    - 新的三个包装器可以把 `const`、`&`/`&&`、`noexcept` 写进签名，修补了 `function` 的 const 正确性漏洞。
    - 一个包装器的目标是另一个包装器时，标准允许两层调用共用同一个按值形参对象，复制次数因此是未指明的。

## 一个固定的类型装下任意可调用物

```cpp run title="button.cpp" ok
#include <functional>
#include <cstdio>
class Button {
  std::function<void(int)> on_click_;     // 类型只取决于签名 void(int)
public:
  void on_click(std::function<void(int)> f) { on_click_ = std::move(f); }
  void click(int x) { if (on_click_) on_click_(x); }
};
void log_click(int x) { std::printf("free %d\n", x); }
int main() {
  Button b;
  b.on_click(log_click);                                   // 函数指针
  b.click(1);
  int count = 0;
  b.on_click([&count](int x) { count += x; });             // 有状态的 lambda
  b.click(2); b.click(3);
  std::printf("count %d\n", count);                        // 5
}
```

每个 lambda 都有自己独一无二的闭包类型。模板可以接受任何可调用物，但一个要保存回调的类如果不想自己变成模板，就需要一个固定的类型来装它们。

[func.wrap] 的四个**多态函数包装器**（[[g:polymorphic-function-wrapper]]，polymorphic function wrapper）解决的就是这个问题。它们用**类型擦除**（[[g:type-erasure]]）把目标的具体类型藏到运行时，类型里只留下调用签名（[[func.def]]）。调用都按 *INVOKE*&lt;R&gt;（[[func.require]]）进行，所以成员指针、函数指针、函数对象都能装，`R` 为 `void` 时丢弃返回值。

## 四个包装器

| 包装器 | 引入 | 页面 | 特点 |
|---|---|---|---|
| `function<R(Args...)>` | C++11 | [[func.wrap.func]] | 拥有、可复制；空调用抛异常；有 const 正确性漏洞 |
| `move_only_function<R(Args...) cv ref noexcept(b)>` | C++23 | [[func.wrap.move]] | 拥有、只能移动；签名可带 cv、ref、noexcept |
| `copyable_function<R(Args...) cv ref noexcept(b)>` | C++26 | [[func.wrap.copy]] | 可复制，签名可带限定，相当于修正后的 `function` |
| `function_ref<R(Args...) cv noexcept(b)>` | C++26 | [[func.wrap.ref]] | 不拥有，两个指针大，平凡可复制，适合作函数参数 |

| 方面 | `function` | `move_only_function` | `copyable_function` | `function_ref` |
|---|---|---|---|---|
| 所有权 | 拥有目标 | 拥有 | 拥有 | 不拥有，只存指针和调用桩 |
| 包装器自身 | 可复制 | 只能移动 | 可复制 | 平凡可复制 |
| 对目标的要求 | 必须可复制 | 可以只能移动 | 必须可复制 | 无 |
| 签名中的 `const` | 不支持 | 支持 | 支持 | 支持 |
| 签名中的 `&`、`&&` | 不支持 | 支持 | 支持 | 不支持 |
| 签名中的 `noexcept` | 不支持 | 支持 | 支持 | 支持 |
| 空状态 | 有，调用抛 `bad_function_call` | 有，调用是前置条件违反 {{ub}} | 同左 | 没有，无默认构造函数 |
| `target()`、`target_type()` | 有（需要 RTTI） | 无 | 无 | 无 |
| 推导指引 | 有 | 无 | 无 | 有 |
| 独立实现中提供 | 否 | 否 | 否 | 是 |

几处差别值得展开：

- 空状态。`function` 把调用空包装器定义为抛 `bad_function_call`，每次调用都隐含一次判空（本机 libc++ 默认 ABI 下，`-O2` 生成的调用代码里确实有一次判空跳转 `cbz`；只有选用 `_LIBCPP_ABI_OPTIMIZED_FUNCTION` 时，空状态才改成一个会抛异常的调用桩，省掉这次分支）。后来的 `move_only_function` 和 `copyable_function` 把非空改成前置条件，实现不必为空状态付任何代价，`noexcept` 签名也才能成立。`function_ref` 干脆不允许空状态：没有默认构造函数，从空函数指针构造违反前置条件。
- const 正确性。`function::operator()` 是 const 成员函数，却能调用目标的非 const `operator()`，详见 [[func.wrap.func]]。新包装器把 `const` 写进签名：`move_only_function<void() const>` 只接受能以 const 左值调用的目标。
- 引用限定。`move_only_function<void() &&>` 表示只能作为右值调用，适合一次性任务，调用时目标也以右值调用。`function_ref` 不支持引用限定，因为它不拥有目标，把目标当右值没有意义。

## 类型擦除的开销

拥有型包装器通常由三部分组成：一块内联缓冲区（[[g:small-object-optimization]]）或一个指向堆的指针、一个负责调用的函数指针、一张负责复制、移动、销毁的操作表。由此带来几项开销：

1. 一次间接调用，编译器一般无法内联目标。
2. 可能的堆分配：目标放不进内联缓冲区时。标准建议对小对象避免动态分配；对 `move_only_function` 和 `copyable_function`，注释指出这种优化只能用于不抛异常地移动的类型。`function` 从函数指针或 `reference_wrapper` 构造时不得抛异常，实际上等于要求不分配。
3. 复制开销：`function` 的复制会深复制目标。它的移动构造是 `noexcept` 的，所以放在 `vector` 里扩容时会移动而不是复制。
4. 体积：本机 libc++ 的 `std::function<int(int)>` 是 32 字节；`function_ref` 只有两个指针大。

`function_ref` 没有第 2、3 项开销：它的构造函数都是 `noexcept` 的，从不分配，复制只是复制两个指针。代价转到了生命周期上，见 [[func.wrap.ref]]。

!!! tip "怎样选"
    只在调用期间使用的回调参数，用 `function_ref` 或模板。需要保存、目标可能只能移动（捕获了 `unique_ptr` 或 `promise`），用 `move_only_function`。需要保存、包装器本身也要可复制，用 `copyable_function`。`function` 主要为兼容旧接口保留。

## `bad_function_call` [func.wrap.badcall]

¶1 `bad_function_call` 派生自 `std::exception`。只有 `function::operator()` 在包装器没有目标时抛出它；其他三个包装器从不抛它。¶2 它的 `what()` 返回一个由实现定义的字符串（{{impl}}）。

```cpp run title="bad-call.cpp" ok
#include <functional>
#include <cstdio>
int main() {
  std::function<void()> f;          // 空
  try {
    f();
  } catch (const std::bad_function_call& e) {
    std::puts(e.what());            // 内容由实现定义，本机打印 std::bad_function_call
    return 0;
  }
  return 1;
}
```

libc++ 在 `-fno-exceptions` 模式下不抛异常，而是直接终止程序。

## 包装器套包装器：实参别名许可 [func.wrap.general]

¶2 考虑按值接收实参的签名 `void(T)`，外层包装器的目标是另一个包装器：

```cpp
move_only_function<void(T)> f{copyable_function<void(T)>{[](T) {}}};
T t;
f(t);   // 复制几次 T？标准说：未指明
```

按普通规则，`f(t)` 先把 `t` 复制到 `f.operator()` 的形参里，再把这个形参转发给内层 `copyable_function::operator()` 的按值形参，内层再转发给 lambda 的按值形参。每多一层包装，就多构造一个对象。

¶2 允许实现让内层调用的实参直接就是外层调用里同位置、同类型的那个实参对象，即使对应的形参不是引用类型。核心语言里两个按值形参必然是两个不同的对象（[[expr.call]]），所以这需要库条文明确授权。后果是复制次数未指明（{{unspec}}）：如果 `T` 的复制构造函数有可观察的副作用，不能依赖它被调用的次数。

¶3 建议（Recommended practice）实现在用一种包装器构造另一种时避免双重包装（[[g:double-wrapping]]）。例如用 `copyable_function` 构造 `move_only_function` 时，直接接管内层的存储和调用桩，而不是在外面再包一层。拆掉一层之后少了一次按值传参，¶2 的许可保证这在可观察行为上是合法的。

!!! lawyer "许可的边界"
    ¶2 只在目标对象的类型本身是这四种包装器之一的特化时适用。目标是自己写的转发函数对象时，没有任何别名许可，实参按 [[expr.call]] 正常初始化。

    同类型也是硬条件。`function_ref<void(std::string&&)>` 包装一个 `function_ref<void(std::string)>` 时，两层的形参类型不同，¶2 不适用；不过 [[func.wrap.ref]] 另有一条专门的许可，允许外层直接复制内层的两个指针。

## 实现现状

本机 libc++（LLVM 23）的 `<version>` 中，`__cpp_lib_move_only_function`、`__cpp_lib_copyable_function`、`__cpp_lib_function_ref` 都被注释掉了，这三个包装器尚未实现。libstdc++ 和 MSVC STL 已经提供 `move_only_function`。[[func.wrap.move]]、[[func.wrap.copy]]、[[func.wrap.ref]] 中无法用本机 libc++ 验证的例子都不标判定，可以用代码块上的 godbolt 按钮在 GCC trunk 上试验。

## 历史与演进

!!! history
    - C++11：`std::function` 从 TR1（源自 Boost.Function）进入标准。
    - C++17：删除 `function` 的分配器支持（[[P0302R1]]），因为各实现从未一致地实现它；加入推导指引。
    - C++23：加入 `move_only_function`（[[P0288R9]]），第一次把 cv、ref、noexcept 写进包装器签名。
    - C++26：加入 `copyable_function`（[[P2548R6]]）和 `function_ref`（[[P0792R14]]）。

## 思考题

!!! question "思考题 1"
    为什么 `move_only_function` 把空调用定为前置条件违反，而不是像 `function` 那样抛 `bad_function_call`？这对 `noexcept` 签名意味着什么？

<details markdown="1">
<summary>答案</summary>

如果空调用必须抛异常，`move_only_function<void() noexcept>` 的 `operator()` 就不可能是 `noexcept` 的：要么违反自己的异常说明，要么只能终止程序。定为前置条件后，实现不必为空状态做任何检查，`noexcept(noex)` 签名得以成立，非空调用也省掉了判空分支。代价是错误从可捕获的异常变成了未定义行为，调用方要自己保证非空（[[func.wrap.move]]）。
</details>

!!! question "思考题 2"
    `T` 的复制构造函数里有 `++copies`。`move_only_function<void(T)> f{copyable_function<void(T)>{[](T){}}}; f(t);` 之后，标准能保证 `copies` 的值吗？如果内层换成自己写的 `struct Fwd { copyable_function<void(T)> g; void operator()(T x) { g(std::move(x)); } };` 呢？

<details markdown="1">
<summary>答案</summary>

第一种情况不能：目标是包装器的特化，¶2 允许实参别名，复制次数未指明。

第二种情况，外层的目标 `Fwd` 不是包装器特化，`Fwd` 内部调用的 `g` 的目标是 lambda，也不是包装器特化，两层都不在 ¶2 的许可范围内。所有形参都按 [[expr.call]] 和各包装器调用运算符规定的等价代码正常初始化，不存在别名许可带来的不确定性。
</details>
