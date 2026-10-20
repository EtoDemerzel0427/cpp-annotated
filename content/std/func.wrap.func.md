---
title: 类模板 function
summary: std::function 能装什么、装不进时是 SFINAE 友好的失败还是硬错误、空调用为什么抛异常、operator() const 为什么能修改目标，以及小对象优化、target() 和 CTAD 的规则。
status: done
covers: *
papers: P2255R2, P0847R7, P1169R4, N4159
related: func.wrap, func.wrap.move, func.wrap.copy, func.wrap.ref, func.require, func.def, refwrap, over.match.class.deduct, temp.deduct.guide, support.rtti, over.match.oper, structure.specifications
tags: 标准库, functional, 类型擦除, CTAD, const 正确性
updated: 2026-10-19
---

!!! tldr
    - `std::function<R(Args...)>` 拥有一个目标对象的副本，能装下任何能以左值调用、结果能转换为 `R` 的可复制对象。
    - 能否调用是约束（不满足时 `is_constructible` 为 false），能否复制是 Mandates（不满足时 trait 仍为 true，真正构造时才报硬错误）。
    - 调用空的 `function` 抛 `bad_function_call`；被移动后的 `function` 不保证为空。
    - `operator()` 是 const 成员，却以非 const 左值调用目标。这个 const 漏洞无法修复，新包装器用签名里的 `const` 解决它。
    - 从函数指针或 `reference_wrapper` 构造保证不抛异常，所以 `std::ref(obj)` 是不分配、不复制地装入大对象的标准做法。

## function 解决什么问题

```cpp run ok
#include <functional>
#include <cstdio>

int twice(int x) { return 2 * x; }

int main() {
    std::function<int(int)> f = twice;      // 函数指针
    std::printf("%d\n", f(3));              // 6
    int k = 10;
    f = [k](int x) { return x + k; };      // lambda，类型不同
    std::printf("%d\n", f(3));              // 13
    f = nullptr;                            // 变空
    try { f(3); } catch (const std::bad_function_call&) {
        std::puts("empty");
    }
}
```

函数指针、lambda、带 `operator()` 的类各有各的类型。`std::function<int(int)>` 是一个固定的类型，能装下其中任何一个，只要它能用一个 `int` 调用并返回能转换为 `int` 的值。这种把具体类型藏到运行时的技术叫**类型擦除**（[[g:type-erasure]]）。

几个术语来自 [[func.def]]：`int(int)` 这样的函数类型叫**调用签名**（call signature）；`function` 内部保存的那个可调用对象叫**目标对象**（target object）；持有目标对象、调用时把调用转发给它的对象叫**调用包装器**（call wrapper）。[func.wrap.func.general] 第 1–2 段说的就是：`function` 是调用签名为 `R(ArgTypes...)` 的调用包装器，可以存储、复制和调用任意可调用对象。

`<functional>` 里的主模板 `template<class> class function;` 没有定义，只有对函数类型的偏特化 `function<R(ArgTypes...)>`。所以 `std::function<int>` 是不完整类型，签名里也不能写 `const`、`&` 或 `noexcept`。四个包装器的对比见 [[func.wrap]]。

## 能装进什么：转换构造函数

`template<class F> function(F&& f)` 决定了什么东西能放进 `function`。它的规格分成几个元素，各自的违反后果不同（这些元素的定义见 [[structure.specifications]]）：

¶8 令 `FD` 为 `decay_t<F>`，即实际存进去的类型。

| 元素 | 内容 | 不满足时 |
|---|---|---|
| ¶9 Constraints | `F` 不是 `function` 本身；`is_invocable_r_v<R, FD&, ArgTypes...>` | 构造函数不参与重载决议，`is_constructible` 为 false |
| ¶10 Mandates | `is_copy_constructible_v<FD>`；`is_constructible_v<FD, F>` | 非良构，必须诊断；但 `is_constructible` 仍为 true |
| ¶11 Preconditions | `FD` 满足 *Cpp17CopyConstructible* | {{ub}} |
| ¶14 Throws | `FD` 是函数指针或 `reference_wrapper` 时不抛出 | — |

### 约束：以左值调用（¶9）

约束里写的是 `FD&`，不是 `FD`。`function` 调用目标时，目标是它内部的一个对象，以左值身份被调用。所以只有 `operator()() &&` 的函数对象不满足约束。

因为这是约束，不能调用的东西根本不会被当成候选。下面两个重载原本看起来会二义，实际上只有第一个可行：

```cpp run title="overload.cpp" ok
#include <functional>
#include <string>

int g(std::function<int(int)>)         { return 1; }
int g(std::function<int(std::string)>) { return 2; }

int main() {
    return g([](int x) { return x; }) == 1 ? 0 : 1;
}
```

这个 lambda 不能用 `std::string` 调用，所以它不能转换为 `function<int(std::string)>`，第二个 `g` 被排除。

### 可复制性是 Mandates（¶10）

```cpp run title="move-only-target.cpp" error
#include <functional>
#include <memory>
#include <type_traits>

int main() {
    auto task = [p = std::make_unique<int>(42)] { return *p; };
    // 约束只检查能否以左值调用，不检查可复制性：
    static_assert(std::is_constructible_v<std::function<int()>, decltype(task)>);
    std::function<int()> f = std::move(task);   // error: 违反 Mandates，闭包不可复制
}
```

`static_assert` 通过了，错误出现在构造函数内部的实例化里。本机 libc++ 报的是 "call to implicitly-deleted copy constructor"。

为什么不做成约束？`function` 的复制构造函数要能复制它装着的任何目标。类型擦除之后，复制目标的代码必须在构造时就实例化好，而一个装着不可复制目标的 `function` 无法提供这段代码。这不是换一个重载就能解决的问题，所以标准直接把它定为非良构。需要装 move-only 对象时，用 [[func.wrap.move]]。

### 结果什么时候是空的（¶12–¶13）

¶12 下面三种情况构造出空的 `function`：`f` 是空函数指针；`f` 是空成员指针；`f` 是任意一个空的 `function` 特化。最后一种不要求签名相同：从空的 `function<int()>` 构造 `function<long()>`，结果也是空的，而不是一个装着空包装器的包装器。

¶13 其他情况下，目标对象是用 `std::forward<F>(f)` 直接非列表初始化（[[g:direct-non-list-initialization]]）的 `FD`。

!!! pitfall "返回引用的签名会拒绝悬垂的临时量"
    按 [[func.require]]，`R` 是引用、而调用结果需要绑定到一个临时量时，*INVOKE*<R> 是非良构的（C++23，[[P2255R2]]）。所以按标准，`is_constructible_v<function<const int&()>, int(*)()>` 应为 false，约束在构造点就挡住了这种悬垂引用。

    本机 libc++ 还没跟上：`is_invocable_r_v<const int&, int(*)()>` 仍为 true。`std::function<const int&()> f = []{ return 42; };` 不会被约束剔除，而是在库内部实例化时触发 Clang 的 "returning reference to local temporary object" 错误。同样编译失败，但不是 SFINAE 友好的。

## 空状态与调用

¶1–¶2 默认构造函数和 `function(nullptr_t)` 都是 `noexcept`，得到空的 `function`。[func.wrap.func.cap] 的 `explicit operator bool()` 在有目标时返回 true；因为是 `explicit`，`if (f)` 可以，`bool b = f;` 不行（见 [[g:contextually-converted-to-bool]]）。

[func.wrap.func.inv] 规定了调用：`R operator()(ArgTypes... args) const` 返回 *INVOKE*<R>(f, std::forward<ArgTypes>(args)...)，`f` 是目标对象。空的 `function` 被调用时抛 `bad_function_call`（[[func.wrap]]）。目标抛出的异常照常传播。

形参是按值的 `ArgTypes...`。签名是 `void(std::string)` 时，`f(s)` 先把 `s` 复制进 `operator()` 的形参，再转发给目标；目标也按值接收的话，总共是一次复制加一次移动。

## const 漏洞

```cpp run title="const-hole.cpp" ok
#include <functional>
#include <cassert>

int main() {
    const std::function<int()> counter = [n = 0]() mutable { return ++n; };
    assert(counter() == 1);
    assert(counter() == 2);   // const 对象的状态变了
}
```

`operator()` 是 const 成员函数，但调用规则里的 `f` 是目标对象本身，标准没有要求以 const 左值调用它。实际实现都以非 const 左值调用，于是 const 的 `function` 可以调用 `mutable` lambda，改变它捕获的状态。

这不只是违反直觉。标准库约定，只通过 const 引用访问对象的库函数不会引入数据竞争（[[res.on.data.races]]），很多代码因此放心地在多个线程里调用 const 对象。一个 const 的 `function` 装着有状态的目标，被两个线程同时调用，就是数据竞争，{{ub}}，而类型上看不出任何问题。

这个漏洞无法修复：收紧规则会让所有装着 `mutable` lambda 的现有代码编译失败。[[N4159]] 系统地讨论了这个问题。后来的 `move_only_function` 和 `copyable_function` 把 `const` 写进签名：`copyable_function<int() const>` 只接受能以 const 左值调用的目标（[[func.wrap.move]]、[[func.wrap.copy]]）。

## 复制、移动与小对象优化

### 复制与移动（¶3–¶7）

¶3–¶4 复制构造复制目标对象。目标是函数指针或 `reference_wrapper` 时不抛异常，否则可能抛 `bad_alloc` 或目标复制构造函数抛出的异常。

¶6 移动构造是 `noexcept` 的。被移动的 `function` 处于有效但未指明的状态（[[g:valid-but-unspecified-state]]），不保证变空。libc++ 就是反例：

```cpp run title="moved-from.cpp" impl
#include <functional>
#include <cstdio>

int main() {
    std::function<int()> small = [] { return 1; };
    std::function<int()> big = [a = 1L, b = 2L, c = 3L] { return int(a + b + c); };
    auto s2 = std::move(small);
    auto b2 = std::move(big);
    std::printf("small: %s\n", small ? "non-empty" : "empty");
    std::printf("big:   %s\n", big ? "non-empty" : "empty");
}
// 本机 libc++ 输出：
//   small: non-empty   内联存储的目标被复制过去，源仍然保留
//   big:   empty       堆上的目标只是转移了指针
```

所以不要在移动之后检查 `function` 是否为空。要继续使用它，先重新赋值或赋 `nullptr`。

### 小对象优化：建议与保证（¶5、¶7、¶14–¶15）

¶5、¶7、¶15 是同一条 *Recommended practice*：对只持有一个对象指针（或引用）加一个成员函数指针的小目标，实现应当避免动态分配。这是建议，不是要求。

¶14 的 Throws 却是规范性的：`FD` 是函数指针或 `reference_wrapper` 时，构造不得抛出。不能抛 `bad_alloc` 就意味着不能堆分配，所以对这两类目标，内联存储实际上是强制的。想让 `function` 使用一个大对象而不复制、不分配，标准做法是传 `std::ref(obj)`（[[refwrap]]），代价是要自己保证 `obj` 活得够久。

其余目标是否内联由实现决定。下面的程序统计每种目标在 libc++ 上的分配次数：

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
    struct ThrowCopy {
        ThrowCopy() = default;
        ThrowCopy(const ThrowCopy&) noexcept(false) {}
        int operator()(int x) const { return x; }
    };
    int k = 1;
    probe("function pointer", &twice);
    probe("reference_wrapper", std::ref(twice));
    probe("lambda [&k]", [&k](int x) { return x + k; });
    probe("lambda [a,b]", [a = 1L, b = 2L](int x) { return x + int(a + b); });
    probe("lambda [a,b,c]", [a = 1L, b = 2L, c = 3L](int x) { return x + int(a + b + c); });
    probe("ThrowCopy (1 byte)", ThrowCopy{});
    probe("Big (32 bytes)", Big{});
    std::printf("sizeof(std::function<int(int)>)=%zu\n", sizeof(std::function<int(int)>));
}
// 本机 libc++（arm64 macOS）输出：
//   function pointer       sizeof(F)= 8  allocs=0
//   reference_wrapper      sizeof(F)= 8  allocs=0
//   lambda [&k]            sizeof(F)= 8  allocs=0
//   lambda [a,b]           sizeof(F)=16  allocs=0
//   lambda [a,b,c]         sizeof(F)=24  allocs=1
//   ThrowCopy (1 byte)     sizeof(F)= 1  allocs=1
//   Big (32 bytes)         sizeof(F)=32  allocs=1
//   sizeof(std::function<int(int)>)=32
```

!!! impl "libc++ 的实现"
    libc++ 默认的 `__value_func` 用经典的虚函数方案：一个基类 `__base` 加上每种目标类型一个派生类 `__func<F>`。`function` 对象由 3 个指针大小的内联缓冲区和一个 `__base*` 组成，共 32 字节。`__func<F>` 自带虚表指针，所以留给目标的只有 16 字节，24 字节的 lambda 就要分配。

    内联还要求目标的复制构造函数是 `noexcept`。libc++ 移动内联目标时实际是复制过去（这也是上一节被移动的 `function` 不为空的原因），而 `function` 的移动构造函数必须是 `noexcept`，所以 `ThrowCopy` 只有 1 字节也要放到堆上。

    ABI v2（宏 `_LIBCPP_ABI_OPTIMIZED_FUNCTION`）改用 `__policy_func`：不用虚函数，而是一张静态操作表加一个直接的调用指针。空状态的调用指针指向一个直接抛 `bad_function_call` 的函数，于是非空调用的路径上没有判空分支。

## 赋值与析构（¶19–¶31）

- ¶19 复制赋值如同 `function(f).swap(*this)`，即复制后交换，提供强异常安全保证。
- ¶21 移动赋值用 `f` 的目标替换 `*this` 的目标。标准没有把它标为 `noexcept`，libc++ 加上了，[[res.on.exception.handling]] 允许实现给非虚函数加强异常规格。
- ¶23 `operator=(nullptr_t) noexcept` 销毁目标，结果为空。
- ¶26–¶27 `template<class F> operator=(F&&)` 的约束与转换构造函数相同，效果如同 `function(std::forward<F>(f)).swap(*this)`。可复制性的 Mandates 通过这个临时 `function` 的构造间接生效。
- ¶29 `operator=(reference_wrapper<F>) noexcept` 是单独的重载。从 `reference_wrapper` 构造保证不抛出，所以这个赋值能标 `noexcept`。本机 libc++ 没有提供这个重载，这种赋值走通用模板，`noexcept(f = std::ref(g))` 为 false。
- ¶31 析构函数销毁目标（如果有）。

[func.wrap.func.mod] 的成员 `swap` 和 [func.wrap.func.alg] 的非成员 `swap` 都是 `noexcept`，交换两个目标对象。

## 访问目标：target 与 target_type

[func.wrap.func.targ] 提供两个函数：`target_type()` 在有目标时返回 `typeid(T)`（`T` 是目标的类型），否则返回 `typeid(void)`；`target<T>()` 只在 `target_type() == typeid(T)` 时返回指向目标的指针，否则返回空指针。`T` 必须是目标的精确类型 `decay_t<F>`，不是调用签名：

```cpp run title="target.cpp" ok
#include <functional>
#include <cassert>
#include <typeinfo>

int twice(int x) { return 2 * x; }

int main() {
    std::function<int(int)> f;
    assert(!f && f == nullptr && nullptr == f);

    int (*np)(int) = nullptr;
    f = np;                                        // 空函数指针得到空 function（¶12.1）
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

这两个函数让 `function` 依赖 RTTI（[[support.rtti]]）。标准里没有关闭 RTTI 这种模式，但 `-fno-rtti` 构建很常见，libc++ 在关闭 RTTI 时干脆不声明这两个函数。后来的三个包装器都不提供目标访问，部分原因就在这里。

## 与 nullptr 比较

[func.wrap.func.nullptr] 只声明了一个 `operator==(const function&, nullptr_t) noexcept`，返回 `!f`。`nullptr == f`、`f != nullptr` 由 C++20 的重写候选（[[g:rewritten-candidate]]，[[over.match.oper]]）合成，C++20 之前它们是单独声明的重载。

两个 `function` 之间不能比较。类型擦除之后，没有办法判断两个目标是否相等。

## 类模板实参推导（¶16–¶18）

`function` 有两条推导指引（一般机制见 [[over.match.class.deduct]]）：

1. `function(R(*)(ArgTypes...)) -> function<R(ArgTypes...)>`，从函数指针或退化成函数指针的函数名推导。
2. `template<class F> function(F) -> function<see below>`，从函数对象推导。

¶16 第二条要求 `&F::operator()` 作为不求值操作数是良构的，并且它的类型是下面三种形式之一：

- `R(G::*)(A...) cv &opt noexceptopt`：普通的非静态成员函数，cv、`&` 和 `noexcept` 都被丢弃；
- `R(*)(G, A...) noexceptopt`：显式对象成员函数（[[g:explicit-object-member-function]]，[[P0847R7]]），第一个形参 `G` 是对象参数，被跳过；
- `R(*)(A...) noexceptopt`：C++23 的 `static operator()`（[[P1169R4]]）。

¶17 推导结果是 `function<R(A...)>`。

```cpp run title="ctad.cpp" ok
#include <functional>
#include <type_traits>

int add(int a, int b) { return a + b; }

struct T {
    static char operator()(int) { return 'x'; }     // static operator()（C++23）
};

int main() {
    std::function f1 = add;                          // 指引 1
    std::function f2 = [](double) { return 1; };     // 指引 2
    std::function f3 = T{};
    static_assert(std::is_same_v<decltype(f1), std::function<int(int, int)>>);
    static_assert(std::is_same_v<decltype(f2), std::function<int(double)>>);
    static_assert(std::is_same_v<decltype(f3), std::function<char(int)>>);
    auto ne = [](int) noexcept { return 0; };
    std::function f4 = ne;                           // noexcept 被丢弃
    static_assert(std::is_same_v<decltype(f4), std::function<int(int)>>);
}
```

`&F::operator()` 必须唯一且不是模板。泛型 lambda 的 `operator()` 是模板，取不了地址，第二条指引不可用：

```cpp run title="ctad-generic.cpp" error
#include <functional>

int main() {
    std::function g = [](auto x) { return x; };   // error: 没有可用的推导指引
}
```

同理，有多个 `operator()` 重载的类和 `std::bind` 的结果都不能用 CTAD。[func.wrap.func.general] 的注 1 还提醒，推导指引推出的类型将来可能改变，不要依赖它的确切结果。

!!! impl "libc++ 还没有实现显式对象形参形式"
    按第二种形式，`struct S { long operator()(this S, double); };` 应推导出 `function<long(double)>`。本机 libc++ 把显式对象形参当成了普通形参，推导出 `function<long(S, double)>`，于是 `std::function f = S{};` 编译失败（"no viable conversion from 'S' to 'std::function<long (S, double)>'"）。这是 libc++ 的缺陷。

## 思考题

!!! question "思考题 1"
    `std::is_constructible_v<std::function<void()>, F>` 为 true，能否保证 `std::function<void()> f = F{};` 能编译？反过来呢？

<details markdown="1">
<summary>答案</summary>

不能。trait 只反映约束（¶9）：`F` 不是 `function` 本身，且 `decay_t<F>` 能以左值调用。可复制性属于 Mandates（¶10），不影响 trait，违反时是硬错误。捕获了 `unique_ptr` 的闭包就会让 trait 为 true 而构造失败。

反过来，trait 为 false 说明转换构造函数不参与重载决议。剩下的候选只有复制、移动和 `nullptr_t` 构造，`F` 不能转换成这些参数类型，构造就一定失败。
</details>

!!! question "思考题 2"
    实参是 `std::ref(g)` 时，为什么选中的是 `operator=(reference_wrapper<F>)`，而不是通用的 `template<class F> operator=(F&&)`？

<details markdown="1">
<summary>答案</summary>

两个都是函数模板，实参类型都能精确匹配，隐式转换序列不分高下，于是由函数模板的偏序决定（[[temp.deduct.partial]]）。`reference_wrapper<F>` 能作为实参去推导 `F&&` 的形参，反过来不行，所以 `reference_wrapper<F>` 版本更特化，被选中。这个版本能声明 `noexcept`，因为 ¶14 保证从 `reference_wrapper` 构造不抛出。
</details>

!!! question "思考题 3"
    `const std::function<void()> f = [v = std::vector<int>{}]() mutable { v.push_back(1); };` 被两个线程同时调用。UB 应该归咎于谁？

<details markdown="1">
<summary>答案</summary>

两个线程同时修改同一个 `vector`（闭包的捕获成员），构成数据竞争（[[intro.races]]），是 UB。[[res.on.data.races]] 约束的是标准库自己不引入数据竞争；这里的修改是用户提供的目标对象做的，标准库只是按 *INVOKE* 调用了它，所以责任在用户。改用 `copyable_function<void() const>` 后，这个 `mutable` lambda 根本装不进去。
</details>
