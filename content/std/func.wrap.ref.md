---
title: 非拥有包装器 function_ref
summary: C++26 的 function_ref 只保存一个指向可调用对象的指针和一个调用函数指针，从不分配、平凡可复制、没有空状态，适合作函数参数，作变量时很容易悬垂。
status: draft
covers: *
since: c++26
papers: P0792R14, P3774R1
related: func.wrap, func.wrap.func, func.wrap.move, func.wrap.copy, const.wrap.class, func.require, class.prop, basic.types.general, class.temporary, over.match.class.deduct, defns.expression.equivalent
tags: 标准库, functional, 类型擦除, 生命周期, C++26, freestanding
updated: 2026-10-19
---

!!! tldr
    - `function_ref` 是可调用对象的引用，类似于 `string_view` 之于字符串：不拥有目标，两个指针宽，平凡可复制，从不分配，也是 freestanding 的。
    - 它保存的是目标的地址。作函数参数是安全的；用临时对象初始化一个 `function_ref` 变量，分号处就悬垂了，无捕获的 lambda 也不例外。
    - 没有默认构造函数，没有空状态，也没有 `operator bool`。
    - 编译期已知的函数用 `std::cw<f>` 传入；成员函数可以用 `{std::cw<&C::mf>, obj}` 绑定到对象，绑定右值对象会被约束拒绝。
    - 除了函数指针、`constant_wrapper` 和兼容的 `function_ref`，给它赋值一律是被删除的操作，以免产生必然悬垂的引用。

!!! warning "实现状态"
    本机 libc++（LLVM 23）还没有实现 `function_ref`，`<version>` 里的 `__cpp_lib_function_ref` 是注释掉的；它依赖的 `constant_wrapper`（[[const.wrap.class]]）已经提供。本页的 `function_ref` 例子无法在本机编译，所以不标判定。

## 为什么需要它

```cpp run title="fr-param.cpp"
#include <functional>

void repeat(int times, std::function_ref<void(int)> fn) {
    for (int i = 0; i < times; ++i) fn(i);
}

int main() {
    int sum = 0;
    repeat(4, [&sum](int i) { sum += i; });   // 不分配，不复制 lambda
    return sum == 6 ? 0 : 1;
}
```

最常见的回调用法不需要所有权：函数接受一个回调，在返回之前调用它若干次，之后就不再需要它。为此构造一个 `std::function` 可能要堆分配、要复制目标；写成模板又会把实现拖进头文件。

`function_ref`（{{c++26}}，[[P0792R14]]）只记住目标在哪里、怎么调用它，目标的生命周期由调用方负责。它不需要堆、异常或 RTTI，所以在 `<functional>` 里标为 freestanding，裸机环境也能用。

## 签名：只有 const 和 noexcept

[func.wrap.ref.general] 规定了 `function_ref<R(ArgTypes...) cv noexcept(noex)>` 这样的偏特化：*cv* 是 `const` 或空，*noex* 是 true 或 false，共 4 种。签名里没有引用限定，因为 `function_ref` 从不拥有目标，以右值调用目标、把它掏空这种所有权语义在这里没有意义。

*cv* 决定目标以什么方式被调用：`function_ref<void() const>` 以 const 左值调用目标，`function_ref<void()>` 以非 const 左值调用。包装器的 `operator()` 则总是 const 的。`function_ref` 是一个引用，调用它不改变引用本身，就像 `T* const p` 仍然可以修改 `*p`。目标会不会被修改，由签名里的 *cv* 明确说出来，所以这里不存在 `std::function` 那样的 const 漏洞（[[func.wrap.func]]）。

## 内部表示（[func.wrap.ref.class]）

第 1 段描述了两个说明用的成员：

- *bound-entity*（[[g:bound-entity]]）：一个未指明的平凡可复制类型的对象，满足 `copyable`，能存放一个对象指针或一个函数指针。
- *thunk-ptr*（[[g:thunk-ptr]]）：类型为 `R(*)(BoundEntityType, ArgTypes&&...) noexcept(noex)` 的函数指针。

调用时（[func.wrap.ref.inv]）执行 `return thunk-ptr(bound-entity, std::forward<ArgTypes>(args)...);`。thunk 是构造时针对具体目标类型生成的一个小函数，它知道怎样把 *bound-entity* 还原成目标并调用。整个类型擦除就是一个数据指针加一个函数指针，不需要虚表，因为 `function_ref` 从不复制、移动或销毁目标。

第 3 段定义的 *call-args* 是一个实参包，`decltype((call-args))...` 恰好是 `ArgTypes&&...`。thunk 的形参都是引用，调用 `function_ref` 时按值的 `ArgTypes...` 形参只构造一次，再以引用传给 thunk。

### 平凡可复制

!!! std
    Each specialization of function_ref is a trivially copyable type ([basic.types.general]) that models copyable.

这不只是说复制很便宜，它还决定了参数怎么传。在 Linux、macOS 等使用 Itanium C++ ABI 的平台上，复制构造函数、移动构造函数或析构函数非平凡的类必须在内存里构造临时对象再传地址；其余的类按 C 的结构体规则传递。在 x86-64 System V 和 AArch64 上，两个指针大小的结构体放在两个寄存器里，所以 `void f(function_ref<void()>)` 的参数传递与 C 风格回调 `(void* ctx, void (*fn)(void*))` 完全相同。

类概要里默认的复制构造函数和复制赋值运算符，加上平凡的成员，就满足了平凡可复制的条件（[[class.prop]]）。

`function_ref` 没有默认构造函数，因此没有空状态：没有 `operator bool`，也不能与 `nullptr` 比较。每个 `function_ref` 都引用着某个可调用实体。

## 构造函数（[func.wrap.ref.ctor]）

¶1 说明用的谓词 *is-invocable-using*<T...> 就是 `is_invocable_r_v<R, T..., ArgTypes...>`，*noex* 为 true 时换成 nothrow 版本。

### 从函数指针（¶3–¶5）

`template<class F> function_ref(F* f) noexcept;`

- ¶3 约束：`F` 是函数类型，且 *is-invocable-using*<F>。
- ¶4 前条件：`f` 不是空指针。`function_ref` 没有空状态可退，违反就是 {{ub}}。
- ¶5 *bound-entity* 存 `f`，thunk 调用 `invoke_r<R>(f, call-args...)`。

这是唯一一个不是 `constexpr` 的构造函数。

### 从任意可调用对象（¶6–¶9）

`template<class F> constexpr function_ref(F&& f) noexcept;`，¶6 令 `T` 为 `remove_reference_t<F>`。

¶7 约束：`F` 去掉 cv 和引用后不是 `function_ref` 本身（同一特化走复制构造）；`T` 不是成员指针；*is-invocable-using*<cv T&>。成员指针被排除，是因为它本身只是一个值，`function_ref` 无处可以长期指向它；要绑定成员函数，用后面的 `constant_wrapper` 构造。

¶8 一般情况下，*bound-entity* 存 `addressof(f)`，thunk 以 `static_cast<cv T&>(f)` 调用目标。无论 `f` 是左值还是右值，存的都是它的地址，后面所有的悬垂问题都源于此。

第 2 段和第 8 段还处理了一个特殊情况：`F` 是另一个 `function_ref`，返回类型和参数与本类型完全相同，只是 cv 或 `noexcept` 不同，并且是朝安全方向转换（`noexcept` 可以变成非 `noexcept`，非 const 签名的来源不能转换成 const 签名）。这时直接复制对方的 *bound-entity* 和 *thunk-ptr*，而不是引用那个 `function_ref` 对象。这是规范性要求。

¶9 进一步允许：只要 `F` 是任意 `function_ref` 特化（签名可以不同，例如参数从 `std::string` 变成 `std::string&&`），实现也可以直接复制它的两个指针。标准的例子说明了后果：

```cpp
void f1(std::string);
void f2(std::string);

function_ref<void(std::string)> r1(&f1);
function_ref<void(std::string&&)> r2(r1);   // 引用 r1，还是复制 r1 的状态？
r2("");                                      // 调用 f1
r1 = &f2;
r2("");                                      // 未指明调用 f1 还是 f2
```

如果 `r2` 引用的是 `r1` 对象，`r1` 重新赋值后 `r2` 会调用 `f2`；如果复制了状态，仍然调用 `f1`。标准让这一点成为未指明行为（{{unspec}}），换取实现避免双重包装的自由（[[func.wrap]] 第 3 段）。

### 从 constant_wrapper（¶10–¶20）

被调用的函数在编译期已知时，没必要在运行时保存它的地址。三个构造函数接受 `constant_wrapper<c, F>`，通常写成 `std::cw<f>`（[[const.wrap.class]]）：

| 写法 | *bound-entity* | thunk 等价于 |
|---|---|---|
| `function_ref(cw<f>)`（¶10–¶12） | 不绑定对象 | `invoke_r<R>(f.value, call-args...)` |
| `function_ref(cw<f>, obj)`（¶13–¶16） | `addressof(obj)` | `invoke_r<R>(f.value, static_cast<cv T&>(obj), call-args...)` |
| `function_ref(cw<f>, ptr)`（¶17–¶20） | `ptr` | `invoke_r<R>(f.value, ptr, call-args...)` |

第一种情况下函数是模板实参，thunk 直接调用它，编译器可以把它内联进 thunk，省掉一次经由函数指针的间接调用。后两种用来把成员函数绑定到对象，可以替代 `std::bind` 或 lambda：

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

- ¶14.1 约束要求 `obj` 不是右值。绑定临时对象几乎一定会悬垂，所以直接拒绝。
- ¶11.1、¶15、¶18 Mandates：`f.value` 是指针或成员指针时不能为空。值是编译期常量，可以在编译期检查。
- ¶19 前条件：成员指针配对象指针时，对象指针不能为空。这是运行期的值，只能作为前条件。

!!! history "nontype 与 constant_wrapper"
    [[P0792R14]] 最初用专门的标签类型 `std::nontype_t<f>`（写作 `std::nontype<f>`）表示这组构造函数。C++26 定稿前，[[P3774R1]] 去掉了 `nontype`，改用更通用的 `std::constant_wrapper`。较早的文章和实现里的 `std::nontype<&Counter::add>` 与今天的 `std::cw<&Counter::add>` 含义相同。

### 被删除的赋值（¶21）

```cpp
template<class T> function_ref& operator=(T) = delete;
```

¶21 约束：`T` 不是可以转换过来的 `function_ref` 特化，不是指针，也不是 `constant_wrapper` 特化。除了这三类，其他任何东西赋值给 `function_ref` 都会选中这个被删除的函数，最典型的是 lambda：

```cpp
std::function_ref<int()> r = &some_function;
r = &other_function;          // OK：不受删除约束，先隐式转换再复制赋值
r = std::cw<other_function>;  // OK
r = [] { return 1; };         // error: 选中被删除的 operator=(T)
```

如果没有这条删除，`r = [] { return 1; };` 会先用临时 lambda 构造一个临时 `function_ref`，再复制赋值。语句结束时 lambda 就销毁了，`r` 立即悬垂。删除的赋值把这种必然悬垂的写法变成了编译错误。函数指针不会被销毁，`cw` 不绑定对象，所以这两类被放行。

## 调用

[func.wrap.ref.inv]：`R operator()(ArgTypes... args) const noexcept(noex);` 等价于 `return thunk-ptr(bound-entity, std::forward<ArgTypes>(args)...);`。它没有前条件，因为不存在空状态。但如果被引用的对象已经销毁，thunk 会访问一个生命周期已经结束的对象，这是 {{ub}}（[[basic.life]]）。

## 生命周期：参数安全，变量危险

```cpp run title="fr-lifetime.cpp"
#include <functional>

int apply(std::function_ref<int(int)> f, int x) { return f(x); }

int main() {
    int k = 10;
    int a = apply([k](int x) { return x + k; }, 1);   // OK

    std::function_ref<int(int)> r = [k](int x) { return x + k; };
    int b = r(1);                                       // UB：闭包对象已在上一行末尾销毁

    auto lam = [k](int x) { return x + k; };
    std::function_ref<int(int)> r2 = lam;               // OK：lam 比 r2 活得久
    return a + b + r2(1);
}
```

第一处安全，因为临时对象要到完整表达式结束时才销毁（[[class.temporary]]），`apply` 的整个调用都在这个完整表达式里。第二处，`r` 的初始化是一个独立的完整表达式，分号处闭包被销毁，`r` 里存的地址立即悬垂。

!!! pitfall "无捕获的 lambda 也会悬垂"
    `std::function_ref<int()> r = [] { return 42; };` 看起来无害，因为无捕获 lambda 能转换成函数指针。但模板实参推导不考虑用户定义的转换，`function_ref(F*)` 无法从闭包类型推导出 `F`，选中的是 `function_ref(F&&)`，存的仍是临时闭包对象的地址。两种改法：

    - 用一元 `+` 先转换成函数指针：`function_ref<int()> r = +[] { return 42; };`
    - 用 `constant_wrapper`：`function_ref<int()> r = std::cw<[] { return 42; }>;`。无捕获 lambda 的闭包类型可以作常量模板实参。

!!! pitfall "引用一个拥有型包装器"
    `function_ref<void()> r = some_move_only_function;` 引用的是那个 `move_only_function` 对象本身，它不是 `function_ref`，¶8 复制状态的分支不适用。之后如果这个对象被移动、重新赋值或销毁，`r` 的行为也会跟着改变或悬垂。用函数返回的 `std::function` 临时对象初始化 `function_ref` 变量，同样会悬垂。

所以 `function_ref` 不适合作数据成员或容器元素，除非能确定被引用的对象比持有者活得久。需要保存的回调用 [[func.wrap.move]] 或 [[func.wrap.copy]]。

## 推导指引（[func.wrap.ref.deduct]）

| 指引 | 约束 | 推导结果 |
|---|---|---|
| `function_ref(F*)` | `F` 是函数类型（第 1 段） | `function_ref<F>` |
| `function_ref(constant_wrapper<c, F0>)` | `F` 即 `remove_pointer_t<F0>` 是函数类型（第 2–4 段） | `function_ref<F>` |
| `function_ref(constant_wrapper<c, F>, T&&)` | 见下（第 5–6 段） | `function_ref<R(A...) noexcept(E)>` |

第三条按 `F` 的形式区分：

- `F` 是成员函数指针 `R(G::*)(A...) cv &opt noexcept(E)`：对象被绑定，剩下的参数是 `A...`；
- `F` 是数据成员指针 `M G::*`：`R` 是 `invoke_result_t<F, T&>`，也就是成员的引用类型，没有参数，`E` 为 true；
- `F` 是函数指针 `R(*)(G, A...) noexcept(E)`：第一个参数被绑定为对象。

没有从任意函数对象推导的指引，`std::function_ref r = lambda;` 是非良构的。推导出的签名也从不带 `const`，第三条会丢掉成员函数的 *cv*。

```cpp run title="fr-deduce.cpp"
#include <functional>
#include <type_traits>
#include <utility>

int twice(int x) noexcept { return 2 * x; }
struct P { int x; int get() const { return x; } };

int main() {
    std::function_ref a = &twice;                  // function_ref<int(int) noexcept>
    std::function_ref b = std::cw<twice>;          // function_ref<int(int) noexcept>
    P p{3};
    std::function_ref c{std::cw<&P::get>, p};      // function_ref<int()>，const 被丢弃
    std::function_ref d{std::cw<&P::x>, p};        // function_ref<int&() noexcept>
    static_assert(std::is_same_v<decltype(c), std::function_ref<int()>>);
    static_assert(std::is_same_v<decltype(d), std::function_ref<int&() noexcept>>);
    return a(1) + b(1) + c() + d() == 10 ? 0 : 1;
}
```

<details class="fine" markdown="1"><summary>其余条文</summary>

¶11.2 是一条 Mandates：如果 `ArgTypes` 非空，去掉 cv 和引用后全都满足 *constexpr-param*（本身就是 `constant_wrapper` 一类的类型），并且 `constant_wrapper<INVOKE(f.value, remove_cvref_t<ArgTypes>::value...)>` 是合法类型，程序就是非良构的。原因是 `constant_wrapper` 自己的 `operator()` 在这种情况下会在编译期求值，返回一个新的 `constant_wrapper`（[[const.wrap.class]]），而 `function_ref` 的 thunk 在运行期调用 `f.value`。同一种写法会有两种含义，标准选择直接拒绝。

¶2 用两个 `is_convertible_v` 编码了 *is-convertible-from-specialization*：`noexcept` 方向用函数引用 `R(&)(Args...) noexcept(noex2)` 到 `R(&)(Args...) noexcept(noex)` 的可转换性，cv 方向用 `int cv&` 到 `int cv2&` 的可转换性。

</details>

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
<summary>答案</summary>

- (1) 安全：`make()` 返回的临时对象活到完整表达式结束，`use` 在此期间完成调用。
- (2) 悬垂：`r1` 存的是临时 `move_only_function` 的地址（¶8），分号处临时对象销毁，之后调用 `r1()` 是 UB。单参数构造对右值没有任何限制，这是有意的，否则 (1) 这样的正确用法也会被拒绝。只有 `constant_wrapper` 加对象的构造拒绝右值（¶14.1）。
- (3) 安全，前提是 `m` 比 `r2` 活得久。如果之后给 `m` 重新赋值，`r2` 会调用新的目标，因为它引用的是 `m` 这个对象。
</details>

!!! question "思考题 2"
    为什么 `function_ref` 的 `operator()` 可以是 const，却没有 `std::function` 的 const 漏洞？

<details markdown="1">
<summary>答案</summary>

`std::function` 拥有目标，目标是包装器的一部分，const 的包装器理应意味着 const 的目标，它却以非 const 方式调用目标。`function_ref` 不拥有目标，它是一个引用：引用本身是 const，和被引用的对象能不能修改是两回事。后者由签名的 *cv* 明确表达，`function_ref<void()>` 声明了会以非 const 左值调用目标，`function_ref<void() const>` 只接受能以 const 方式调用的目标。类型如实描述了行为，所以不存在漏洞。
</details>
