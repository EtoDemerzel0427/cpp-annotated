---
title: 类模板 function
summary: std::function 的完整契约——构造函数的 Constraints/Mandates 分工、空状态与 bad_function_call、operator() const 调用非 const 目标的 const 正确性漏洞、target()/target_type() 与 RTTI、小对象优化的"推荐"与"不得抛出"、CTAD 推导指引、赋值与 nullptr 比较
status: draft
covers: *
papers: P0302R1, P2255R2, P0847R7, P1169R4
related: func.wrap, func.wrap.move, func.wrap.copy, func.wrap.ref, func.require, func.def, refwrap, over.match.class.deduct, temp.deduct.guide, support.rtti, over.match.oper
tags: 标准库, functional, 类型擦除, CTAD, const 正确性
updated: 2026-10-18
---

`std::function<R(Args...)>` 是四个多态包装器（总览见 [[func.wrap]]）中最老的一个，也是唯一一个签名里**只能**写 `R(Args...)`、不能带 `const`/`&`/`noexcept` 的。它的规格几乎每一条都值得细读：哪些错误是 SFINAE 友好的、哪些是硬错误；哪些行为是"推荐"、哪些是"必须"；以及一个从 C++11 起就存在、至今无法修复的 const 正确性漏洞。

前置知识：*INVOKE*<R> 的定义（[[func.require]]）；*call wrapper* 与 *target object* 的定义（[[func.def]]）；Constraints / Mandates / Preconditions 的区别（[[structure.specifications]]）。

## 定位（[func.wrap.func.general]）

¶1–2：`function` 是一个**调用包装器**（*call wrapper*），其调用签名为 `R(ArgTypes...)`；它"推广了函数指针的概念"——能存储、复制、调用任意可调用对象。头文件里的主模板 `template<class> class function;` **没有定义**，只有对函数类型的偏特化 `function<R(ArgTypes...)>`，所以 `std::function<int>` 是不完整类型。

¶3（注）：推导指引推导出的类型**可能在未来版本中改变**。这是一条非规范性的"免责声明"：委员会保留了将来让 CTAD 推出带 `noexcept` 或其他限定的签名的余地，不要把 `std::function f = lambda;` 推出的确切类型写进 ABI。

## 构造函数（[func.wrap.func.con]）

### 空状态（¶1–2）

`function()` 与 `function(nullptr_t)` 都是 `noexcept`，后条件 `!*this`。空的 `function` 没有目标对象。

### 复制与移动（¶3–7）

¶3–4：复制构造复制目标对象。*Throws*：若目标是 `reference_wrapper` 特化或函数指针则**不抛出**，否则可能抛 `bad_alloc` 或目标复制构造函数抛出的异常。

¶6：移动构造是 `noexcept` 的，被移动的源对象处于"**有效但未指明**的状态"（[[g:valid-but-unspecified-state]]）——注意，**不保证变空**。libc++ 就是一个活生生的反例：

```cpp run title="moved-from.cpp" impl
#include <functional>
#include <cstdio>

int main() {
    std::function<int()> small = [] { return 1; };
    std::function<int()> big = [a = 1L, b = 2L, c = 3L] { return int(a + b + c); };
    auto s2 = std::move(small);
    auto b2 = std::move(big);
    std::printf("small moved-from: %s\n", small ? "non-empty" : "empty");
    std::printf("big   moved-from: %s\n", big ? "non-empty" : "empty");
}
// libc++ 23 输出：
//   small moved-from: non-empty   ← 内联存储的目标被"复制"过去，源保留原目标
//   big   moved-from: empty       ← 堆上的目标只是转移了指针
```

所以"移动后判空"的代码在不同实现、甚至同一实现的不同目标大小下行为不同。移动之后要么重新赋值，要么 `= nullptr`，不要检查它。

¶5、¶7、¶15 都是同一条 *Recommended practice*：对"只持有一个对象指针/引用加一个成员函数指针"这种小目标，应避免动态分配。

### 转换构造函数 `template<class F> function(F&& f)`（¶8–15）

这是最重要的一个构造函数，令 `FD` 为 `decay_t<F>`。它的契约被拆成了四层，每层的法律后果完全不同：

| 元素 | 内容 | 违反后果 |
|---|---|---|
| *Constraints*（¶9） | `remove_cvref_t<F>` 不是 `function`；`is_invocable_r_v<R, FD&, ArgTypes...>` | 构造函数**不参与重载决议**（SFINAE 友好，`is_constructible` 为 false） |
| *Mandates*（¶10） | `is_copy_constructible_v<FD>`；`is_constructible_v<FD, F>` | 程序**非良构**，需诊断——但 `is_constructible` 仍为 true |
| *Preconditions*（¶11） | `FD` 满足 *Cpp17CopyConstructible* | {{ub}} |
| *Throws*（¶14） | `FD` 是 `reference_wrapper` 或函数指针时**不抛出** | — |

**Constraints 用 `FD&` 而不是 `FD`。** 因为 `function` 内部存的是一个对象，调用时以**左值**调用它（¶1 的 *INVOKE* 中 `f` 是目标对象的左值）。所以只能以右值调用的函数对象（`operator()() &&`）不满足约束。C++11 时这条要求叫做 "Callable"，后来改称 "*Lvalue-callable*"，现行草案直接把它写成了 `is_invocable_r_v<R, FD&, ArgTypes...>`，含义不变。

这条约束让下面这种曾经二义的重载可以正常工作——不能用 `std::string` 调用的 lambda 根本无法转换为 `function<int(std::string)>`：

```cpp run title="overload.cpp" ok
#include <functional>
#include <string>

int g(std::function<int(int)>)         { return 1; }
int g(std::function<int(std::string)>) { return 2; }

int main() {
    return g([](int x) { return x; }) == 1 ? 0 : 1;
}
```

**可复制性是 Mandates 而不是 Constraints。** 这是一个刻意的选择，也是一个经典陷阱：trait 说"能构造"，真正构造时却硬错误。

```cpp run title="move-only-target.cpp" error
#include <functional>
#include <memory>
#include <type_traits>

int main() {
    auto task = [p = std::make_unique<int>(42)] { return *p; };
    // Constraints 只看"能不能以左值调用"，不看可复制性：
    static_assert(std::is_constructible_v<std::function<int()>, decltype(task)>);
    std::function<int()> f = std::move(task);   // error: 违反 Mandates（闭包不可复制）
}
```

`static_assert` 通过了，错误发生在构造函数体的实例化里（libc++ 报告 "call to implicitly-deleted copy constructor"）。为什么不做成约束？因为 `function` 的复制构造函数必须能复制**任何**它可能装着的目标——类型擦除之后，复制操作在构造时就要实例化好；一个装着 move-only 目标的 `function` 是根本无法存在的，而不是"换一个重载"能解决的。这也正是 `move_only_function`（[[func.wrap.move]]）存在的理由。

**¶12 何时得到空 `function`**：`f` 是空函数指针、空成员指针，或者是一个空的 `function` 特化（注意是**任意** `function` 特化——`function<long()>` 从一个空的 `function<int()>` 构造，结果也是空的，而不是一个"调用时抛异常的包装器的包装器"）。其他情况下，目标对象是用 `std::forward<F>(f)` **直接非列表初始化**（[[g:direct-non-list-initialization]]）的 `FD`。

!!! pitfall "返回引用的签名与临时量"
    *INVOKE*<R> 在 `R` 是引用、而调用结果会绑定到临时量时是**非良构**的（[[func.require]]，C++23 由 [[P2255R2]] 加入）。于是按标准 `is_constructible_v<function<const int&()>, int(*)()>` 应为 false，这类悬垂引用在构造点就被约束挡掉。

    但截至 libc++ 23，`is_invocable_r_v<const int&, int(*)()>` 仍然是 true，`std::function<const int&()> f = []{ return 42; };` 不会被约束剔除，而是在库内部实例化时由 Clang 的"返回局部临时对象的引用"诊断变成硬错误。结果同样是编译失败，但不是 SFINAE 友好的。

### 小对象优化：推荐 vs 必须

¶15 只是 *Recommended practice*（不具强制力），但 ¶14 的 *Throws* 是规范性的：**`FD` 是函数指针或 `reference_wrapper` 时构造不得抛出**。不能抛 `bad_alloc` 就意味着不能堆分配——所以对这两类目标，内联存储实际上是**强制**的。这也是"想让 `function` 引用一个大对象而不复制、不分配"的标准手法：传 `std::ref(obj)`（[[refwrap]]）。

其余目标是否内联完全由实现决定。下面的程序在 libc++ 23 上的结果：

```cpp run title="sbo.cpp" impl
#include <functional>
#include <cstdio>
#include <cstdlib>
#include <new>

static int allocs = 0;
void* operator new(std::size_t n) {
    ++allocs;
    if (void* p = std::malloc(n)) return p;
    throw std::bad_alloc();
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

int twice(int x) { return 2 * x; }

template <class F>
void probe(const char* what, F f) {
    allocs = 0;
    { std::function<int(int)> fn = f; (void)fn(1); }
    std::printf("%-22s sizeof(F)=%2zu  allocs=%d\n", what, sizeof(F), allocs);
}

int main() {
    struct Big { long a[4]; int operator()(int x) const { return x + int(a[0]); } };
    int k = 1;
    probe("function pointer", &twice);
    probe("reference_wrapper", std::ref(twice));
    probe("lambda [&k]", [&k](int x) { return x + k; });
    probe("lambda [a,b]", [a = 1L, b = 2L](int x) { return x + int(a + b); });
    probe("lambda [a,b,c]", [a = 1L, b = 2L, c = 3L](int x) { return x + int(a + b + c); });
    struct ThrowCopy {
        ThrowCopy() = default;
        ThrowCopy(const ThrowCopy&) noexcept(false) {}
        int operator()(int x) const { return x; }
    };
    probe("ThrowCopy (1 byte)", ThrowCopy{});
    probe("Big (32 bytes)", Big{});
    std::printf("sizeof(std::function<int(int)>)=%zu\n", sizeof(std::function<int(int)>));
}
// libc++ 23（arm64 macOS）输出：
//   function pointer       sizeof(F)= 8  allocs=0
//   reference_wrapper      sizeof(F)= 8  allocs=0
//   lambda [&k]            sizeof(F)= 8  allocs=0
//   lambda [a,b]           sizeof(F)=16  allocs=0
//   lambda [a,b,c]         sizeof(F)=24  allocs=1
//   ThrowCopy (1 byte)     sizeof(F)= 1  allocs=1
//   Big (32 bytes)         sizeof(F)=32  allocs=1
//   sizeof(std::function<int(int)>)=32
```

!!! impl "libc++ 的两套实现"
    `__functional/function.h` 里有两套后端，由 ABI 宏 `_LIBCPP_ABI_OPTIMIZED_FUNCTION` 选择（它只在 ABI v2 中定义，默认的稳定 ABI v1 不用它）：

    - **`__value_func`（默认）**：经典的"虚基类 `__base` + 派生 `__func<F>`"方案。对象布局是 `3 * sizeof(void*)` 字节的内联缓冲区加一个 `__base*`，共 32 字节。内联条件是 `sizeof(__func<F>) <= sizeof(__buf_)` **且** `is_nothrow_copy_constructible<F>`。`__func<F>` 自带一个虚表指针，所以留给目标的只有 16 字节——这就是上面 24 字节的 lambda 要分配的原因。要求 nothrow **复制**（而不是移动）是因为它的"移动"对内联目标实际上是调用 `__clone` 复制过去（上一节"移动后不空"的根源），而 `function` 的移动构造函数必须是 `noexcept`。
    - **`__policy_func`（ABI v2）**：不用虚函数，改用一张静态的 `__policy` 表（clone/destroy 函数指针、`type_info*`、是否为空）加一个直接的调用函数指针 `__func_`。内联条件更严格：目标必须**平凡可复制构造且平凡可析构**、且不超过两个指针大小。空状态的调用指针指向 `__empty_func`，它直接抛 `bad_function_call`——于是非空调用的路径上**没有判空分支**。

## 赋值（¶19–30）与析构（¶31）

- ¶19 复制赋值："如同" `function(f).swap(*this)`——经典的 copy-and-swap，强异常安全。
- ¶21 移动赋值：用 `f` 的目标替换 `*this` 的目标。注意标准**没有**把它标为 `noexcept`（移动构造是 `noexcept` 的，移动赋值不是）；libc++ 给它加了 `noexcept`，这是 [[res.on.exception.handling]] 允许实现对非虚函数做的"强化"。
- ¶23 `operator=(nullptr_t) noexcept`：销毁目标，后条件为空。
- ¶26–27 `template<class F> operator=(F&&)`：*Constraints* 只有 `is_invocable_r_v<R, decay_t<F>&, ArgTypes...>`，效果"如同" `function(std::forward<F>(f)).swap(*this)`——所以可复制性的 *Mandates* 是通过那个临时 `function` 的构造间接施加的。
- ¶29 `operator=(reference_wrapper<F>) noexcept`：单独的重载，正是因为从 `reference_wrapper` 构造保证不抛出，赋值才能标 `noexcept`（libc++ 23 未提供这个重载，此类赋值走通用模板，不是 `noexcept`）。
- ¶31 析构：若非空，销毁目标。

## 调用与 const 正确性漏洞（[func.wrap.func.inv]）

¶1：`R operator()(ArgTypes... args) const` 返回 *INVOKE*<R>(f, std::forward<ArgTypes>(args)...)，其中 `f` 是目标对象。¶2：`!*this` 时抛 `bad_function_call`（[[func.wrap]]），否则传播目标抛出的异常。

注意形参是**按值的** `ArgTypes...`：签名是 `void(std::string)` 时，调用 `f(s)` 先把 `s` 复制进 `operator()` 的形参，再 `std::forward` 给目标——如果目标也按值接收，就是一次复制加一次移动。

问题出在 `const` 上。`operator()` 是 `const` 成员函数，这本应意味着"调用不修改包装器的状态"。可是 ¶1 里的 `f` 指的是**目标对象**本身——标准没有说要以 const 左值调用它。实际实现中，目标以非 const 左值被调用：

```cpp run title="const-hole.cpp" ok
#include <functional>
#include <cassert>

int main() {
    const std::function<int()> counter = [n = 0]() mutable { return ++n; };
    // counter 是 const 对象，却调用了 mutable lambda 的非 const operator()：
    assert(counter() == 1);
    assert(counter() == 2);   // const 对象的"内部状态"变了
}
```

后果不止是"违背直觉"：标准库约定 const 成员函数可以被多个线程并发调用而不产生数据竞争（[[res.on.data.races]]）。一个 `const std::function` 被两个线程同时调用、而目标是有状态的 `mutable` lambda——这是数据竞争，{{ub}}，而类型系统完全没给你任何提示。

为什么不修？因为一修就破坏大量现有代码（所有装着 `mutable` lambda 或非 const `operator()` 函数对象的 `function` 都会编译失败）。委员会的选择是另起炉灶：`move_only_function` 和 `copyable_function` 把 `const` 写进签名，`move_only_function<int() const>` 只接受能以 const 左值调用的目标（[[func.wrap.move]] 的 *inv-quals*）。这个问题在 [[N4159]] 中有系统的论述。

## 容量、目标访问与 RTTI（[func.wrap.func.cap]、[func.wrap.func.targ]）

[func.wrap.func.cap] ¶1：`explicit operator bool() const noexcept`——有目标时为 true。`explicit` 意味着 `if (f)` 可以（按语境转换为 `bool`，[[g:contextually-converted-to-bool]]），`bool b = f;` 不行。

[func.wrap.func.targ]：

- ¶1 `target_type()`：有目标时返回 `typeid(T)`，否则 `typeid(void)`；
- ¶2 `target<T>()`：仅当 `target_type() == typeid(T)` 时返回指向目标的指针，否则返回空指针。

`T` 必须是**目标的精确类型**（`decay_t<F>`），不是调用签名：

```cpp run title="target.cpp" ok
#include <functional>
#include <cassert>
#include <typeinfo>

int twice(int x) { return 2 * x; }

int main() {
    std::function<int(int)> f;
    assert(!f && f == nullptr && nullptr == f);
    try { f(1); assert(false); } catch (const std::bad_function_call&) {}

    int (*np)(int) = nullptr;
    f = np;                                        // 空函数指针 → 空 function（¶12.1）
    assert(f == nullptr);

    f = twice;
    assert(f.target_type() == typeid(int (*)(int)));
    assert(*f.target<int (*)(int)>() == &twice);
    assert(f.target<int(int)>() == nullptr);      // 签名不是目标类型
    auto lam = [](int x) { return x + 1; };
    f = lam;
    assert(f.target<decltype(lam)>() != nullptr);
    assert(std::function<void()>{}.target_type() == typeid(void));
}
```

这两个函数把 `type_info` 拉进了 `function` 的接口，使 `function` 依赖 RTTI（[[support.rtti]]）。标准本身不承认"关闭 RTTI"这种模式，但现实中的 `-fno-rtti` 构建很常见：libc++ 在 `_LIBCPP_HAS_RTTI` 为假时直接不声明 `target()` 与 `target_type()`。这是后来的三个包装器都**不提供**目标访问的原因之一——它们也就不需要为每个目标类型生成 `type_info`。

## nullptr 比较（[func.wrap.func.nullptr]）与 swap（[func.wrap.func.mod]、[func.wrap.func.alg]）

[func.wrap.func.nullptr] ¶1：只声明了一个 `operator==(const function&, nullptr_t) noexcept`，返回 `!f`。C++20 之前还有 `nullptr == f`、`f != nullptr`、`nullptr != f` 三个重载；C++20 起它们都由**重写候选**（[[g:rewritten-candidate]]，[[over.match.oper]]）合成：`f != nullptr` 改写为 `!(f == nullptr)`，`nullptr == f` 反转为 `f == nullptr`。libc++ 在 `_LIBCPP_STD_VER <= 17` 时仍保留这些旧重载。

两个 `function` 之间**不能**比较——类型擦除之后无从定义"相等"。libc++ 还额外声明了一个 `= delete` 的成员 `operator==(const function<R2(Args2...)>&)`，注释是"堵住类型系统中的漏洞"：防止两个 `function` 经由某种隐式转换意外地比较成功。

[func.wrap.func.mod] ¶1 的成员 `swap` 与 [func.wrap.func.alg] ¶1 的非成员 `swap` 都是 `noexcept`，交换目标对象。

## CTAD 推导指引（¶16–18）

`function` 有两条推导指引（类模板实参推导的一般机制见 [[over.match.class.deduct]]，推导指引语法见 [[temp.deduct.guide]]）：

1. `function(R(*)(ArgTypes...)) -> function<R(ArgTypes...)>`：从函数指针（包括函数名退化而来）推导。
2. `template<class F> function(F) -> function<see below>`：从函数对象推导。¶16 要求 `&F::operator()` 作为不求值操作数是良构的，并且其类型匹配下列形式之一：
    - 非静态成员：`R(G::*)(A...) cv &opt noexceptopt`——普通的隐式对象成员函数，cv、`&` 和 `noexcept` 都被**丢弃**；
    - 非静态成员：`R(*)(G, A...) noexceptopt`——**显式对象成员函数**（[[g:explicit-object-member-function]]，deducing this，[[P0847R7]]），第一个形参 `G` 是对象参数，被跳过；
    - 静态成员：`R(*)(A...) noexceptopt`——C++23 的 `static operator()`（[[P1169R4]]）。

¶17：推导出 `function<R(A...)>`。

```cpp run title="ctad.cpp" ok
#include <functional>
#include <type_traits>

int add(int a, int b) { return a + b; }

struct T {
    static char operator()(int) { return 'x'; }     // 静态 operator()（C++23）
};

int main() {
    std::function f1 = add;                          // 指引 1
    std::function f2 = [](double) { return 1; };     // 指引 2：从 &F::operator() 推导
    std::function f4 = T{};
    static_assert(std::is_same_v<decltype(f1), std::function<int(int, int)>>);
    static_assert(std::is_same_v<decltype(f2), std::function<int(double)>>);
    static_assert(std::is_same_v<decltype(f4), std::function<char(int)>>);
    auto ne = [](int) noexcept { return 0; };
    std::function f5 = ne;                           // noexcept 被丢弃
    static_assert(std::is_same_v<decltype(f5), std::function<int(int)>>);
}
```

`&F::operator()` 必须**唯一且不是模板**。泛型 lambda 的 `operator()` 是模板，取不了地址，指引 2 被约束剔除：

```cpp run title="ctad-generic.cpp" error
#include <functional>

int main() {
    std::function g = [](auto x) { return x; };   // error: 无可用的推导指引
}
```

同理，有重载 `operator()` 的类、`std::bind` 的结果都无法用 CTAD。

!!! impl "libc++ 尚未实现显式对象参数形式"
    按 ¶16.1 的第二种形式，`struct S { long operator()(this S, double); };` 应推导出 `function<long(double)>`。但 libc++ 23 的推导指引（`__strip_signature_t<decltype(&_Fp::operator())>`）把显式对象参数当成了普通形参，推导出 `function<long(S, double)>`，于是 `std::function f = S{};` 编译失败（"no viable conversion from 'S' to 'std::function<long (S, double)>'"）。这是 libc++ 的缺陷，不是标准的问题。

## 思考题

!!! question "思考题 1"
    `std::is_constructible_v<std::function<void()>, F>` 为 true，是否就能保证 `std::function<void()> f = F{};` 能编译？反过来呢？

<details markdown="1">
<summary>展开查看答案与解析</summary>

不能。trait 只反映 *Constraints*（¶9）：不是 `function` 本身、且 `decay_t<F>` 能以左值调用并把结果转换为 `R`。*Mandates*（¶10）——`FD` 可复制构造、可由 `F` 构造——不影响 trait，违反时是硬错误。所以 move-only 闭包会让 trait 为 true 而构造失败（上文 `move-only-target.cpp`）。

反过来，trait 为 false 意味着转换构造函数不参与重载决议；剩下的候选只有复制/移动构造与 `nullptr_t` 构造，`F` 若不能转换为 `function` 或 `nullptr_t`，构造必然失败。
</details>

!!! question "思考题 2"
    为什么 `function& operator=(reference_wrapper<F>) noexcept` 要单独声明，而不是让通用的 `template<class F> operator=(F&&)` 处理？

<details markdown="1">
<summary>展开查看答案与解析</summary>

通用模板赋值的效果是构造临时 `function` 再 swap，构造一般可能抛 `bad_alloc`，所以通用版本不能是 `noexcept`。而 ¶14 保证从 `reference_wrapper` 构造不抛出，单独的重载因此可以声明 `noexcept`，让"把一个对象的引用装进 `function`"在接口层面成为不抛异常的操作。

实参是 `reference_wrapper<X>` 时，两个模板的隐式转换序列都是恒等转换，于是由函数模板偏序（[[temp.deduct.partial]]）决胜：`reference_wrapper<F>` 能从 `F&&`（偏序时去掉引用）推导成功、反之不能，所以 `reference_wrapper<F>` 版本更特化而被选中。

顺带一提：libc++ 23 没有声明这个重载，`noexcept(f = std::ref(g))` 在 libc++ 上为 false。
</details>

!!! question "思考题 3"
    `const std::function<void()> f = [v = std::vector<int>{}]() mutable { v.push_back(1); };` 被两个线程同时调用 `f()`。这里的 UB 应归咎于哪条规则？

<details markdown="1">
<summary>展开查看答案与解析</summary>

两个线程通过 const 成员函数 `operator()` 同时修改了同一个 `vector` 对象（目标的捕获成员），构成数据竞争（[[intro.races]]），是 UB。[[res.on.data.races]] 要求标准库函数在只通过 const 实参访问对象时不引入数据竞争——但这里的修改是**用户的目标对象**做的，标准库只是按 *INVOKE* 调用了它，所以责任在用户。`function` 的 const 漏洞让这种错误在类型上不可见；换成 `copyable_function<void() const>` 后，`mutable` lambda 根本无法被装进去（约束要求能以 const 左值调用）。
</details>

## 小结

| 主题 | 要点 |
|---|---|
| Constraints | 不是 `function` 自身；`is_invocable_r_v<R, decay_t<F>&, Args...>`（左值可调用） |
| Mandates | 目标可复制构造——硬错误，`is_constructible` 看不出来 |
| 空状态 | 默认/nullptr/空指针/空 `function` 构造；调用抛 `bad_function_call` |
| 移动后 | 有效但未指明，**不保证为空**（libc++ 内联目标仍非空） |
| SBO | 推荐；函数指针与 `reference_wrapper` 构造不得抛出 = 事实上的强制 |
| const 漏洞 | `operator() const` 以非 const 左值调用目标；不可修复，由新包装器解决 |
| 目标访问 | `target<T>()` 要求精确的目标类型；依赖 RTTI |
| 比较 | 只有 `== nullptr`；C++20 重写候选合成其余 |
| CTAD | 函数指针；`&F::operator()` 的三种形式（含 deducing this 与 static）；丢弃 noexcept |
