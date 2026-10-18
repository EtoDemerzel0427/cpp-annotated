---
title: 非拥有包装器 function_ref
summary: C++26 的 function_ref——两个指针宽、平凡可复制、从不分配、没有空状态的"可调用对象的引用"；thunk-ptr + bound-entity 模型、constant_wrapper 构造与成员函数绑定、被删除的赋值、推导指引，以及作参数安全、作变量悬垂的生命周期陷阱
status: draft
covers: *
since: c++26
papers: P0792R14
related: func.wrap, func.wrap.func, func.wrap.move, func.wrap.copy, const.wrap.class, func.require, class.prop, basic.types.general, class.temporary, over.match.class.deduct, defns.expression.equivalent
tags: 标准库, functional, 类型擦除, 生命周期, C++26, freestanding
updated: 2026-10-18
---

前三个包装器都**拥有**目标对象，代价是可能的堆分配和复制。可是最常见的回调用法根本不需要所有权：一个函数接受回调参数，在返回之前调用它若干次，然后就不再需要它了——`for_each_line(file, callback)`、`retry(op, on_error)`、`visit_nodes(tree, fn)`。为这种场景构造一个 `std::function` 是浪费；写成模板又会把实现拖进头文件。`function_ref`（{{c++26}}，[[P0792R14]]）就是可调用对象的"`string_view`"：**不拥有、两个指针宽、平凡可复制、从不分配**，而生命周期由调用方负责。

它在 `<functional>` 里被标为 **freestanding**——不需要堆、不需要异常、不需要 RTTI，裸机环境也能用。

!!! warning "实现状态"
    截至本文编写时，libc++（LLVM 23.1）**尚未实现** `function_ref`：`<version>` 中 `__cpp_lib_function_ref`（`202306L`）被注释掉。但它依赖的 `constant_wrapper`（[[const.wrap.class]]）libc++ 23 已经提供（`__cpp_lib_constant_wrapper` 为 `202606L`）。本页 `function_ref` 示例未经本地验证，不标判定。

## 签名：只有 cv 和 noexcept（[func.wrap.ref.general]）

¶1：偏特化 `function_ref<R(ArgTypes...) cv noexcept(noex)>`，*cv* 为 `const` 或空，*noex* 为 true 或 false，共 4 种。**没有 ref 限定**——`function_ref` 从不拥有目标，"以右值调用目标、把它掏空"这种所有权语义在这里没有意义。

*cv* 决定目标**如何被看待**：`function_ref<void() const>` 以 `const T&` 调用目标，`function_ref<void()>` 以 `T&` 调用。注意 `operator()` 本身**总是** `const` 的（[func.wrap.ref.inv]）——`function_ref` 是一个"引用"，调用它不改变引用本身，`const` 是浅的；目标能否被修改由签名中的 *cv* 决定。这与 `std::function` 的 const 漏洞不同：`function_ref<void()>` 明说了"我会以非 const 方式调用目标"，类型没有撒谎。

## 对象模型：thunk + bound-entity（[func.wrap.ref.class]）

¶1：一个 `function_ref` 存两样东西（都是说明用成员）：

- *bound-entity*（[[g:bound-entity]]）：类型为 *BoundEntityType*——一个**未指明的、平凡可复制的、满足 `copyable`** 的类型，能存放**对象指针值或函数指针值**（实践中就是一个 `void*` 与函数指针的联合体）；
- *thunk-ptr*（[[g:thunk-ptr]]）：类型为 `R(*)(BoundEntityType, ArgTypes&&...) noexcept(noex)` 的函数指针。

调用时（[func.wrap.ref.inv] ¶1）：`return thunk-ptr(bound-entity, std::forward<ArgTypes>(args)...);`。*thunk* 是构造时针对具体目标类型实例化出来的一个小函数，它知道怎么把 *bound-entity* 还原为目标并调用它。整个类型擦除就是"一个数据指针 + 一个函数指针"，不需要虚表、不需要 policy 表——因为 `function_ref` 不需要复制、移动或销毁目标。

¶3 定义了 *call-args*：一个实参包，`decltype((call-args))...` 恰为 `ArgTypes&&...`。thunk 的形参都是引用，调用 `function_ref` 时按值的 `ArgTypes...` 形参只构造一次，然后以引用传给 thunk。

### 为什么必须平凡可复制（¶2）

!!! std
    Each specialization of function_ref is a trivially copyable type that models copyable.

    `function_ref` 的每个特化都是平凡可复制类型（[[basic.types.general]]），并满足 `copyable`。

这不只是"复制很便宜"的承诺，它有 ABI 层面的直接后果。Itanium C++ ABI（Linux、macOS 等平台使用）规定：复制构造函数、移动构造函数或析构函数非平凡的类是"对调用而言非平凡的"，必须在内存中构造临时对象并传地址；其余的类按平台 C ABI 像普通结构体一样传递。在 x86-64 System V 与 AArch64 上，两个指针大小的结构体放在两个寄存器里——所以 `void f(function_ref<void()>)` 的参数传递和 C 风格回调 `(void* ctx, void (*fn)(void*))` 一模一样。平凡可复制的判定规则见 [[class.prop]]——类概要里 `function_ref(const function_ref&) noexcept = default;` 与 `operator=(const function_ref&) noexcept = default;` 加上平凡的成员，正是实现这一点的手段。

`function_ref` **没有默认构造函数**，因此也**没有空状态**：没有 `operator bool`，没有 `== nullptr`。任何一个 `function_ref` 对象都引用着某个可调用实体。

## 构造函数（[func.wrap.ref.ctor]）

两个说明用的辅助谓词：

- ¶1 *is-invocable-using*<T...>：`is_invocable_r_v<R, T..., ArgTypes...>`（*noex* 时为 nothrow 版本）；
- ¶2 *is-convertible-from-specialization*<F>：`F` 是另一个 `function_ref<R(Args...) cv2 noexcept(noex2)>`——**返回类型与参数完全相同**，只允许 cv 与 `noexcept` 不同——并且两者都朝"安全"的方向转换。`noexcept` 用函数引用的可转换性编码：`noexcept` 的可以变成非 `noexcept` 的，反之不行；cv 用 `is_convertible_v<int cv&, int cv2&>` 编码：若本类型签名带 `const`，来源也必须带 `const`（来源的 thunk 以 const 方式调用目标，满足本类型"只以 const 方式调用"的承诺；反之则不满足）。

### 从函数指针（¶3–5）

`template<class F> function_ref(F* f) noexcept;`

- *Constraints*：`is_function_v<F>`，且 *is-invocable-using*<F>；
- *Preconditions*：`f` 不是空指针（违反即 {{ub}}——`function_ref` 没有空状态可退）；
- *Effects*：*bound-entity* 存 `f`，*thunk* 调用 `invoke_r<R>(f, call-args...)`。

这是唯一一个**不是 `constexpr`** 的构造函数。

### 从任意可调用对象（¶6–9）

`template<class F> constexpr function_ref(F&& f) noexcept;`，令 `T = remove_reference_t<F>`：

- *Constraints*：`remove_cvref_t<F>` 不是 `function_ref`（同一特化走复制构造）；`T` **不是成员指针**；*is-invocable-using*<cv T&>；
- *Effects*（¶8）：一般情况下 *bound-entity* 存 **`addressof(f)`**，*thunk* 以 `static_cast<cv T&>(f)` 调用目标。若 `F` 是满足 *is-convertible-from-specialization* 的另一个 `function_ref`，则**直接复制**对方的 *bound-entity* 和 *thunk-ptr*——这是**规范性要求**，不是优化。

注意 `addressof(f)`：无论 `f` 是左值还是右值，存的都是它的**地址**。这就是一切悬垂问题的根源（见下文）。

成员指针被排除，因为成员指针本身是一个值而不是可以长期指向的东西；要绑定成员函数，用下面的 `constant_wrapper` 构造。

¶9 *Remarks* 是一条**许可**：如果 `F` 是**任意** `function_ref` 特化（即使签名不完全相同，例如参数从 `std::string` 变成 `std::string&&`），实现也**可以**直接复制它的两个指针，而不是引用那个 `function_ref` 对象本身。标准的例子展示了其后果：

```cpp
void f1(std::string);
void f2(std::string);

function_ref<void(std::string)> r1(&f1);
function_ref<void(std::string&&)> r2(r1);   // 引用 r1？还是复制 r1 的状态？
r2("");                                      // 调用 f1
r1 = &f2;
r2("");                                      // 未指明调用 f1 还是 f2
```

若 `r2` 引用的是 `r1` 对象，`r1` 被重新赋值后 `r2` 会调用 `f2`；若复制了状态，仍调用 `f1`。标准让这一点**未指明**（{{unspec}}），换来实现消除双重包装的自由（[[func.wrap]] ¶3）。

### 从 constant_wrapper（¶10–20）

当被调用的函数在**编译期已知**时，没必要在运行时存它的地址。三个构造函数接受一个 `constant_wrapper<c, F>`（即 `std::cw<f>`，见 [[const.wrap.class]]）：

| 构造 | 绑定 | *thunk* 等价于 |
|---|---|---|
| `function_ref(cw<f>)`（¶10–12） | 不绑定对象（*bound-entity* 是指向未指明对象的指针或空指针） | `invoke_r<R>(f.value, call-args...)` |
| `function_ref(cw<f>, obj)`（¶13–16） | `addressof(obj)` | `invoke_r<R>(f.value, static_cast<cv T&>(obj), call-args...)` |
| `function_ref(cw<f>, ptr)`（¶17–20） | `ptr` | `invoke_r<R>(f.value, ptr, call-args...)` |

第一种：函数是模板实参，*thunk* 直接调用它——编译器在 thunk 内部可以内联 `f`，省掉一次通过函数指针的间接调用。第二、三种用来**把成员函数绑定到对象**，取代 `std::bind`/lambda：

```cpp run title="fr-member.cpp"
#include <functional>
#include <utility>

struct Counter {
    int n = 0;
    void add(int k) { n += k; }
};

void repeat(int times, std::function_ref<void(int)> fn) {
    for (int i = 0; i < times; ++i) fn(i);
}

int main() {
    Counter c;
    repeat(4, {std::cw<&Counter::add>, c});     // 绑定到对象 c
    repeat(4, {std::cw<&Counter::add>, &c});    // 绑定到指针
    // repeat(4, {std::cw<&Counter::add>, Counter{}});   // error: 约束拒绝右值对象（¶14.1）
    return c.n == 12 ? 0 : 1;
}
```

契约要点：

- ¶14.1 *Constraints*：`is_rvalue_reference_v<U&&>` 为 false——**右值对象被约束拒绝**。这是有意的防悬垂设计：绑定临时对象几乎一定会悬垂。
- ¶11.1、¶15、¶18 *Mandates*：若 `F` 是指针或成员指针，`f.value != nullptr`——空的函数/成员指针在**编译期**就被拒绝（因为值是常量，可以检查）。
- ¶19 *Preconditions*：成员指针 + 对象指针时，对象指针不能为空（运行期值，只能是前条件）。
- ¶11.2 *Mandates*：若 `ArgTypes` 非空且全部（去 cvref 后）满足 *constexpr-param*（即本身都是 `constant_wrapper` 一类的类型），并且 `constant_wrapper<INVOKE(f.value, remove_cvref_t<ArgTypes>::value...)>` 是合法类型，则非良构。可以这样理解：`constant_wrapper` 自己的 `operator()` 在这种情形下会在**编译期**求值并返回一个新的 `constant_wrapper`（[[const.wrap.class]]），而 `function_ref` 的 thunk 是在**运行期**调用 `f.value`——同一写法两种语义，标准选择直接拒绝。

!!! history "nontype → constant_wrapper"
    [[P0792R14]] 最初引入 `function_ref` 时，这组构造函数用的是专门的标签类型 `std::nontype_t<f>`（写作 `std::nontype<f>`）。C++26 定稿前，`nontype_t` 被移除，统一改用更通用的 `std::constant_wrapper`（`std::cw<f>`）。读较早的文章、提案或实现时会看到 `nontype<&Counter::add>` 的写法，含义相同。

### 被删除的赋值（¶21）

```cpp
template<class T> function_ref& operator=(T) = delete;
```

约束：`T` 不是兼容的 `function_ref` 特化、不是指针、不是 `constant_wrapper` 特化。也就是说，**除了**这三种之外的任何东西赋值给 `function_ref` 都被显式删除——最重要的是 lambda：

```cpp
std::function_ref<int()> r = &some_function;
r = &other_function;          // OK：指针不受删除约束 → 隐式转换 + 默认的复制赋值
r = std::cw<other_function>;  // OK
r = [] { return 1; };         // error: 选中被删除的 operator=(T)
```

如果没有这条删除，`r = [] { return 1; };` 会先用转换构造函数从临时 lambda 构造一个临时 `function_ref`，再复制赋值——语句结束时 lambda 就销毁了，`r` 立即悬垂。删除的赋值把这个**必然**悬垂的写法变成编译错误。指针与 `constant_wrapper` 不存在这个问题（函数指针本身不会"销毁"，`cw` 不绑定对象），所以被放行。

## 调用（[func.wrap.ref.inv]）

¶1：`R operator()(ArgTypes... args) const noexcept(noex);` 等价于 `return thunk-ptr(bound-entity, std::forward<ArgTypes>(args)...);`。没有前条件，因为不存在空状态——但若被引用的对象已经销毁，调用在 thunk 内部访问它，是 {{ub}}（[[basic.life]]）。

## 生命周期：参数安全，变量危险

`function_ref` 的正确用法几乎只有一种：**作函数参数**。

```cpp run title="fr-lifetime.cpp"
#include <functional>

int apply(std::function_ref<int(int)> f, int x) { return f(x); }

int main() {
    int k = 10;
    int a = apply([k](int x) { return x + k; }, 1);   // OK：临时 lambda 活到完整表达式结束

    std::function_ref<int(int)> r = [k](int x) { return x + k; };
    // 临时 lambda 在上一行的分号处已经销毁
    int b = r(1);                                       // UB：r 引用了已销毁的闭包对象

    auto lam = [k](int x) { return x + k; };
    std::function_ref<int(int)> r2 = lam;               // OK：lam 活得比 r2 久
    return a + b + r2(1);
}
```

第一处安全的原因：临时对象在**完整表达式结束时**才销毁（[[class.temporary]]），`apply` 的调用整个落在这个完整表达式内。第二处：`r` 的初始化是一个独立的完整表达式，分号处闭包临时对象销毁，`r` 里存的 `addressof(f)` 立即悬垂。

!!! pitfall "无捕获的 lambda 也会悬垂"
    `std::function_ref<int()> r = [] { return 42; };` 看起来无害——无捕获 lambda 可以转换为函数指针，函数指针永远不会悬垂。但模板实参推导**不考虑用户定义转换**，`function_ref(F*)` 无法从闭包类型推导出 `F`，于是选中的是 `function_ref(F&&)`：存的是**临时闭包对象的地址**。修正方法：

    - 显式转为函数指针：`function_ref<int()> r = +[] { return 42; };`（一元 `+` 触发到函数指针的转换）；
    - 或者用 `constant_wrapper`：`function_ref<int()> r = std::cw<[] { return 42; }>;`（无捕获 lambda 的闭包类型是结构化类型，可以作常量模板实参）。

!!! pitfall "引用一个拥有型包装器"
    `function_ref<void()> r = some_move_only_function;` 引用的是**那个 `move_only_function` 对象**（它不是 `function_ref` 特化，¶8 的复制状态分支不适用）。之后若 `some_move_only_function` 被移动、重新赋值或销毁，`r` 的行为随之改变或悬垂。从 `std::function` 返回值构造 `function_ref` 同样会悬垂。

同理，`function_ref` 不适合作**数据成员**或**容器元素**，除非你能证明被引用的可调用对象比持有者活得久；需要保存的回调请用 [[func.wrap.move]] 或 [[func.wrap.copy]]。

## 推导指引（[func.wrap.ref.deduct]）

| 指引 | 约束 | 推导结果 |
|---|---|---|
| `function_ref(F*)` | `is_function_v<F>`（¶1） | `function_ref<F>` |
| `function_ref(constant_wrapper<c, F0>)` | `F = remove_pointer_t<F0>` 是函数类型（¶2–4） | `function_ref<F>` |
| `function_ref(constant_wrapper<c, F>, T&&)` | 见下（¶5–6） | `function_ref<R(A...) noexcept(E)>` |

第三条按 `F` 的形式区分：

- ¶5.1 `F` 是成员函数指针 `R(G::*)(A...) cv &opt noexcept(E)`——对象被绑定，剩余参数 `A...`；
- ¶5.2 `F` 是数据成员指针 `M G::*`——`R` 为 `invoke_result_t<F, T&>`（即成员的引用类型），无参数，`E` 为 true（读成员不会抛出）；
- ¶5.3 `F` 是函数指针 `R(*)(G, A...) noexcept(E)`——第一个参数被绑定为对象。

几个值得注意的**缺席**：

- **没有从任意函数对象推导的指引**。`std::function_ref r = lambda;` 非良构——与 `std::function` 不同，`function_ref` 需要决定签名里是否带 `const`，从 `&F::operator()` 推导无法可靠地回答这个问题；
- 推导出的签名**从不带 `const`**（第三条丢弃了成员函数的 *cv*）。

```cpp run title="fr-deduce.cpp"
#include <functional>
#include <type_traits>
#include <utility>

int twice(int x) noexcept { return 2 * x; }
struct P { int x; int get() const { return x; } };

int main() {
    std::function_ref a = &twice;                        // function_ref<int(int) noexcept>
    std::function_ref b = std::cw<twice>;                // function_ref<int(int) noexcept>
    P p{3};
    std::function_ref c{std::cw<&P::get>, p};            // function_ref<int()>（const 被丢弃）
    std::function_ref d{std::cw<&P::x>, p};              // function_ref<int&() noexcept>
    static_assert(std::is_same_v<decltype(c), std::function_ref<int()>>);
    static_assert(std::is_same_v<decltype(d), std::function_ref<int&() noexcept>>);
    return a(1) + b(1) + c() + d() == 10 ? 0 : 1;
}
```

`d` 的推导：`invoke_result_t<int P::*, P&>` 是 `int&`，所以结果是 `function_ref<int&() noexcept>`。

## 思考题

!!! question "思考题 1"
    下面哪一行会悬垂？
    ```cpp
    std::move_only_function<int()> make();
    void use(std::function_ref<int()>);

    use(make());                                   // (1)
    std::function_ref<int()> r1 = make();          // (2)
    auto m = make();
    std::function_ref<int()> r2 = m;               // (3)
    ```

<details markdown="1">
<summary>展开查看答案与解析</summary>

- (1) 安全：`make()` 返回的临时 `move_only_function` 活到完整表达式结束，`use` 在此期间完成调用。
- (2) 悬垂：`r1` 存的是临时 `move_only_function` 的地址（¶8，`addressof(f)`），分号处临时对象销毁。之后调用 `r1()` 是 UB。注意 `function_ref` 只对**右值对象 + `constant_wrapper`** 的组合做了约束拒绝（¶14.1），对 ¶6 的单参数构造没有任何右值限制——这是有意的，否则 (1) 这样的正确用法也会被拒绝。
- (3) 安全，只要 `m` 活得比 `r2` 久，并且之后没有对 `m` 重新赋值（重新赋值后 `r2` 会调用新的目标，因为它引用的是 `m` 这个对象）。
</details>

!!! question "思考题 2"
    为什么 `function_ref` 的 `operator()` 可以是 `const` 而不重蹈 `std::function` const 漏洞的覆辙？

<details markdown="1">
<summary>展开查看答案与解析</summary>

`std::function` 的问题在于它**拥有**目标：目标是包装器的一部分，const 包装器理应意味着 const 目标，可它却以非 const 方式调用目标。`function_ref` 不拥有目标，它是一个引用——就像 `T* const p` 可以修改 `*p`，"引用本身是 const" 与"被引用的对象是否可修改"是两回事。而后者由签名的 *cv* 明确表达：`function_ref<void()>` 声明了"以非 const 左值调用目标"，`function_ref<void() const>` 只接受 const 可调用的目标并以 const 左值调用。类型准确描述了行为，所以不存在漏洞。
</details>

## 小结

| 主题 | 要点 |
|---|---|
| 签名 | `R(Args...) cv noexcept(noex)`，4 个偏特化，无 ref 限定 |
| 表示 | *thunk-ptr* + *bound-entity*；平凡可复制、满足 `copyable`；寄存器传参 |
| 空状态 | 没有：无默认构造、无 `operator bool`；空函数指针构造是前条件违反 |
| 一般构造 | 存 `addressof(f)`——临时对象会悬垂；兼容的 `function_ref` 复制状态 |
| `constant_wrapper` 构造 | 编译期已知的函数可内联；绑定对象时拒绝右值 |
| 赋值 | 除兼容 `function_ref`、指针、`constant_wrapper` 外一律删除 |
| CTAD | 函数指针、`cw<f>`、`cw<f>` + 对象；无函数对象指引；推导结果不带 const |
| 用法 | 作参数；不要作变量、成员或容器元素 |
| libc++ 23 | 未实现（`constant_wrapper` 已实现） |
