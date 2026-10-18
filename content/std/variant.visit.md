---
title: variant 的访问
summary: std::visit 与 visit<R>、C++26 成员 visit 的精确契约——as-variant 让派生自 variant 的类也能被访问、所有调用必须同类型同值类别的 Mandates、"n ≤ 1 时常数时间"的复杂度要求；overload 模式背后的 using 包展开与聚合 CTAD；libc++ 的函数指针表实现
status: done
papers: P0088R3, P0655R1, P2162R2, P2637R3, P0195R2, P1816R0
related: variant, variant.variant, func.require, over.match.class.deduct, dcl.init.aggr, namespace.udecl, forward, over.match.call
tags: 标准库, variant, visit, 模式匹配, 重载
updated: 2026-10-18
---

`std::visit` 是 `variant` 的"模式匹配"：给它一个可调用对象和若干个 variant，它在运行时查出每个 variant 当前装的是哪个 alternative，然后**以这些 alternative 的具体类型**调用那个可调用对象。它把"运行时的下标"转换成"编译期的重载选择"——这是 `variant` 区别于 C 风格"联合体 + 枚举标签"的关键能力：你不再需要手写 `switch`，也不会漏掉某个分支（漏了编译不过）。

[variant.visit] 规定了两个非成员函数模板和两个 C++26 新增的成员函数模板：

```cpp
template<class Visitor, class... Variants>
  constexpr see below visit(Visitor&& vis, Variants&&... vars);   // ①
template<class R, class Visitor, class... Variants>
  constexpr R visit(Visitor&& vis, Variants&&... vars);           // ② C++20

// variant 的成员，C++26
template<class Self, class Visitor>
  constexpr decltype(auto) visit(this Self&& self, Visitor&& vis);  // ③
template<class R, class Self, class Visitor>
  constexpr R visit(this Self&& self, Visitor&& vis);               // ④
```

前置知识：*INVOKE* 与 *INVOKE*<R>（[[func.require]]）；`variant` 的基本概念与 *GET*（[[variant]]）。

## as-variant：接受从 variant 派生的类（¶1–3）

¶1 先定义四个说明用的函数模板 *as-variant*（[[g:as-variant]]），分别接受 `variant<Ts...>&`、`const variant<Ts...>&`、`variant<Ts...>&&`、`const variant<Ts...>&&`，原样返回（右值版本 `std::move`）。然后令 `V_i` 为 `decltype(as-variant(std::forward<Variants_i>(vars_i)))`。

¶2 **Constraints**：对所有 `i`，`V_i` 是合法类型。

这两段话的真正作用是**接受从 `variant` 派生的类**。`as-variant` 是函数模板，对 `variant<Ts...>&` 形参做模板实参推导时，按 [[temp.deduct.call]]，若实参类型是某个 `variant<Ts...>` 的派生类，推导可以成功（推导出那个基类）。于是：

- 实参是 `variant` 本身 → `V_i` 就是它的引用类型；
- 实参是**唯一地、可访问地**派生自某个 `variant` 特化的类 → `V_i` 是那个基类的引用，访问就针对这个基类子对象；
- 实参不是 variant，或者从**多个** variant 特化派生（推导有歧义）→ `V_i` 不合法，`visit` 不参与重载决议。

```cpp run title="visit-derived.cpp" ok
#include <cassert>
#include <variant>

struct Expr : std::variant<int, double> {
    using variant::variant;
};

int main() {
    Expr e = 2.5;
    double d = std::visit([](auto x) { return double(x); }, e);   // C++23 起 OK
    assert(d == 2.5);
    assert(e.visit([](auto x) { return x > 0; }));                 // 成员 visit 也行
}
```

!!! history "为什么要 as-variant"
    C++17 的 `visit` 规定实参是 `variant` 本身，并用 `variant_size_v<remove_reference_t<Variants>>` 等 trait 来描述——对派生类，`variant_size<Expr>` 没有特化，于是"从 variant 派生"这种很自然的写法（例如用来定义递归的表达式树）在不同实现上时而能编译、时而不能。[[P2162R2]]（"Inheriting from std::variant"）以 *as-variant* 统一了规则，C++23 采纳，并作为缺陷报告追溯到 C++17。libc++ 的 `__cpp_lib_variant` 为 `202102L` 即表示实现了这一改动。

```cpp run title="visit-ambiguous-base.cpp" error
#include <variant>

struct Both : std::variant<int>, std::variant<double> {};

int main() {
    Both b;
    std::visit([](auto) {}, b);   // error: as-variant 推导有歧义，visit 不可行
}
```

## 调用的形式与 Mandates（¶4–5）

¶4：令 `m` 是 `n` 个 `size_t` 构成的包；当每个 `m_i` 都小于 `variant_size_v<remove_reference_t<V_i>>` 时，`m` 是**有效**的。对每个有效的 `m`，定义 `e(m)` 为：

```cpp
INVOKE(std::forward<Visitor>(vis), GET<m>(std::forward<V>(vars))...)     // 形式 ①
INVOKE<R>(std::forward<Visitor>(vis), GET<m>(std::forward<V>(vars))...)  // 形式 ②
```

注意 `std::forward<V>(vars)`——实参的值类别和 const 性质会传递给 *GET*，所以 `std::visit(f, std::move(v))` 中访问者收到的是 alternative 的**右值**，`std::visit(f, std::as_const(v))` 中收到的是 `const&`。

!!! std
    *Mandates*: For each valid pack `m`, `e(m)` is a valid expression. All such expressions are of the same type and value category.

    **强制要求**：对每个有效的 `m`，`e(m)` 都是合法表达式；并且所有这些表达式**类型相同、值类别相同**。

这句话包含两条要求：

1. **穷尽性**：访问者必须能处理**所有组合**。两个 variant 分别有 3、2 个 alternative，就要 6 种调用全部合法。漏掉任何一个是编译错误（不是 SFINAE——这是 *Mandates*）。
2. **结果一致**：形式 ① 的返回类型是 `decltype(e(m))`，它必须对所有 `m` 相同，连**值类别**也要相同。

第二条常常让人意外：

```cpp run title="visit-mismatch-type.cpp" error
#include <variant>

int main() {
    std::variant<int, double> v = 1;
    auto r = std::visit([](auto x) { return x; }, v);   // error: 一个返回 int，一个返回 double
    (void)r;
}
```

```cpp run title="visit-mismatch-category.cpp" error
#include <variant>

int g;
struct F {
    int& operator()(int) const { return g; }       // 左值
    int  operator()(double) const { return 0; }    // 纯右值
};

int main() {
    std::variant<int, double> v = 1;
    (void)std::visit(F{}, v);   // error: 类型都"是 int"，但值类别不同
}
```

libc++ 对这两种情况都给出同一条 `static_assert`："`` `std::visit` requires the visitor to have a single return type. ``"。

为什么不自动取 `common_type`？因为那会引入隐式转换，而 `visit` 的设计是"不替你做决定"。想要统一返回类型，就**明说**——这正是形式 ②。

### `visit<R>`（形式 ②，C++20）

形式 ② 用 *INVOKE*<R>：每个调用的结果都**隐式转换**为 `R`；若 `R` 是（cv）`void`，结果被丢弃。于是只需要每个 `e(m)` 都能转换为 `R`，对它们之间是否同类型不再有要求（*Mandates* 中"同类型同值类别"对 `INVOKE<R>` 表达式自然成立，因为它们的类型都是 `R`）。它由 [[P0655R1]] 在 C++20 加入。

```cpp run title="visit-r.cpp" ok
#include <cassert>
#include <string>
#include <variant>

int main() {
    std::variant<int, double> v = 1;
    double r = std::visit<double>([](auto x) { return x; }, v);  // int 和 double 都转成 double
    assert(r == 1.0);

    int calls = 0;
    std::visit<void>([&](auto x) { ++calls; return x; }, v);     // R = void：丢弃结果
    assert(calls == 1);

    std::variant<int, std::string> w = "abc";
    auto n = w.visit<std::size_t>([](const auto& x) {            // 成员 visit<R>
        if constexpr (std::is_same_v<std::decay_t<decltype(x)>, int>) return x;
        else return x.size();
    });
    assert(n == 3);
}
```

## 返回、异常与复杂度（¶6–8）

¶6 **Returns**：`e(m)`，其中 `m_i` 是 `as-variant(vars_i).index()`；形式 ① 的返回类型是 `decltype(e(m))`。

¶7 **Throws**：若 `(as-variant(vars).valueless_by_exception() || ...)` 为真，抛出 `bad_variant_access`。也就是说，**任意一个** variant 是 valueless 就抛，访问者一次都不会被调用。

```cpp run title="visit-valueless.cpp" ok
#include <cassert>
#include <variant>

struct S { operator int() { throw 42; } };

int main() {
    std::variant<float, int> v{12.f};
    try { v.emplace<1>(S()); } catch (int) {}        // v 变成 valueless
    try { std::visit([](auto) {}, v); assert(false); }
    catch (const std::bad_variant_access& e) { (void)e.what(); }
}
```

¶8 **Complexity**：

!!! std
    For *n* ≤ 1, the invocation of the callable object is implemented in constant time, i.e., for *n* = 1, it does not depend on the number of alternative types of `V_0`. For *n* > 1, the invocation of the callable object has no complexity requirements.

    当 *n* ≤ 1 时，对可调用对象的调用以**常数时间**实现，即 *n* = 1 时不依赖于 `V_0` 的 alternative 数量。*n* > 1 时，对可调用对象的调用没有复杂度要求。

这是一条**规范性**的要求（不是 "should"）：单 variant 的 `visit` 不允许实现成"按下标逐个 `if` 比较"的线性链——即使有 100 个 alternative 也必须是常数时间。实践中这意味着跳转表（函数指针数组）或编译器能生成跳转表的 `switch`。（*n* = 0 时 `visit(f)` 就是直接调用 `f()`。）多个 variant 时放开要求，是因为 `k` 个各有 `N` 个 alternative 的 variant 会有 `N^k` 种组合，标准不想强迫实现生成指数大小的表。

## 成员 visit（¶9–13，C++26）

[[P2637R3]] 为 `variant` 增加了成员 `visit`，用"显式对象形参"（deducing this，[[dcl.fct]]）写成：

- ¶9：令 `V` 为 *OVERRIDE_REF*(`Self&&`, *COPY_CONST*(`remove_reference_t<Self>`, `variant`))（[[forward]]）——即"把 `self` 的 const 性质和引用种类照搬到 `variant` 上"。
- ¶11 **Effects**：等价于 `return std::visit(std::forward<Visitor>(vis), (V)self);`
- ¶13：`visit<R>` 版本同理，转发到 `std::visit<R>`。

强制转换 `(V)self` 的意义在于：`Self` 可能是派生类（上面的 `Expr`），转换到基类 `variant` 引用后再交给非成员 `visit`。

¶10 是一条耐人寻味的 **Constraints**：

!!! std
    *Constraints*: The call to `visit` does not use an explicit *template-argument-list* that begins with a type *template-argument*.

    **约束**：对 `visit` 的调用没有使用"以类型模板实参开头"的显式模板实参列表。

原因在于两个成员模板的模板形参列表：③ 是 `<class Self, class Visitor>`，④ 是 `<class R, class Self, class Visitor>`。用户写 `v.visit<int>(f)` 想调用 ④ 并指定 `R = int`，但对 ③ 来说，显式写的 `int` 会被当成 **`Self`**——显式对象形参的类型被强行指定为 `int`，造成令人费解的错误或误选。¶10 把 ③ 从这种调用中排除。libc++ 的实现很巧妙：在 ③ 的最前面放一个类型为私有标签类的**非类型模板形参** `__variant_visit_barrier_tag = __variant_visit_barrier_tag{}`，于是任何以类型开头的显式模板实参都无法匹配它，③ 自动不可行。

成员 `visit` 的好处主要是写法上的：`v.visit(f)` 的阅读顺序是"对象在前、操作在后"，和链式调用一致；也省去了把派生类显式转换为 `variant` 的麻烦。

## overload 模式

用一组 lambda 组成访问者是 `visit` 最常见的用法，俗称 **overload 模式**（[[g:overload-pattern]]）：

```cpp run title="overloaded.cpp" ok
#include <cassert>
#include <string>
#include <variant>

template<class... Ts>
struct overloaded : Ts... { using Ts::operator()...; };

int main() {
    std::variant<int, double, std::string> v = 3.5;
    auto describe = overloaded{
        [](int)                  { return std::string("int"); },
        [](double)               { return std::string("double"); },
        [](const std::string& s) { return "string:" + s; },
    };
    assert(std::visit(describe, v) == "double");
    v = "hi";
    assert(std::visit(describe, v) == "string:hi");

    // 多个 variant：访问者要处理所有组合（这里 3×2 = 6 种）
    std::variant<int, std::string> w = 7;
    auto both = std::visit([](const auto& a, const auto& b) {
        return sizeof(a) + sizeof(b);
    }, v, w);
    assert(both == sizeof(std::string) + sizeof(int));
}
```

两行代码用到了三个语言特性：

1. **多重继承自 lambda 闭包类型**：闭包类型是普通的类（[[expr.prim.lambda.closure]]），可以作为基类。
2. **using 声明中的包展开** `using Ts::operator()...;`（C++17，[[P0195R2]]，[[namespace.udecl]]）：把所有基类的 `operator()` 引入同一个作用域，形成**一个**重载集。没有这一句，不同基类的同名成员会造成名字查找歧义（[[class.member.lookup]]）。
3. **聚合的类模板实参推导**：`overloaded{lambda1, lambda2, ...}` 中 `overloaded` 是没有构造函数的聚合，每个 lambda 初始化一个基类子对象（[[dcl.init.aggr]]——C++17 起聚合可以有基类）。C++17 需要手写推导指引 `template<class... Ts> overloaded(Ts...) -> overloaded<Ts...>;`；C++20 的 [[P1816R0]] 引入了**聚合推导候选**（[[g:aggregate-deduction-candidate]]，[[over.match.class.deduct]]），编译器根据聚合的元素自动合成这个指引，那一行就可以删掉了。

!!! pitfall "overload 模式就是普通的重载决议"
    访问者的选择是对 `vis(alt)` 做的**普通重载决议**，所有隐式转换照常生效：

    ```cpp run title="overload-trap.cpp" ok
    #include <cassert>
    #include <string>
    #include <variant>

    template<class... Ts>
    struct overloaded : Ts... { using Ts::operator()...; };

    int main() {
        std::variant<std::string, bool> v = std::string("x");
        auto r = std::visit(overloaded{
            [](bool)        { return 1; },
            [](const auto&) { return 2; },
        }, v);
        assert(r == 2);     // 泛型 lambda 精确匹配，胜过任何转换

        std::variant<char, double> w = 'a';
        auto r2 = std::visit(overloaded{
            [](int)    { return 1; },
            [](double) { return 2; },
        }, w);
        assert(r2 == 1);    // 没有 char 分支：char → int 是提升，胜过 char → double
    }
    ```

    第二个例子说明，忘记写某个分支并不一定会编译失败——只要某个现有分支能通过隐式转换接住它。需要"严格穷尽"时，可以加一个 `[](auto) = delete;` 风格的兜底（例如 `template<class T> void operator()(T) = delete;`），让任何未精确匹配的类型都选中被删除的模板。

## libc++ 实现：函数指针表

libc++ 的 `visit` 在 `__variant_detail::__visitation` 中实现，思路是**在编译期构造一个 N 维函数指针数组，运行时按下标取出一项再调用**：

1. `__make_fmatrix<Visitor, Vs...>()` 对每一种下标组合 `(I_0, I_1, ...)` 实例化一个 `__dispatcher<I_0, I_1, ...>::__dispatch`，它做的事就是 `std::__invoke(vis, __get_alt<I_0>(v0), __get_alt<I_1>(v1), ...)`；
2. 这些函数的地址被放进嵌套的 `__farray<FnPtr, N>`（一个轻量的 `std::array` 替代品），整个表是 `constexpr` 局部变量；
3. `__at(__fmatrix, __vs.index()...)` 按各 variant 的下标逐维索引，取出函数指针并调用。

关键细节：

- **单一返回类型检查**：`__make_farray` 要求所有函数指针类型相同（`__std_visit_visitor_return_type_check`），这就是 ¶5 中"同类型同值类别"的实现——返回类型不同，函数指针类型就不同，放不进同一个数组。
- **穷尽性检查**：`__value_visitor` 在调用前用 `static_assert(is_invocable_v<Visitor, Values...>, ...)` 检查，失败时的消息是 "`` `std::visit` requires the visitor to be exhaustive. ``"。
- **valueless 先行检查**：`visit` 在查表之前调用 `__throw_if_valueless`（因为 npos 不是有效下标，不能用来索引）。
- **as-variant**：`visit` 的声明带一个默认模板实参 `typename = void_t<decltype(std::__as_variant(std::declval<_Vs>()))...>`，用 SFINAE 实现 ¶2 的 Constraints。
- 复杂度：查表是 O(1)，满足 ¶8；多个 variant 时表大小是各 alternative 数之积，编译时间和目标代码体积随之增长。

同一套 `__visit_alt_at(index, ...)` 机制也被 `variant` 自己的复制构造、赋值、`swap`、比较运算符和 `hash` 使用。

!!! impl "优化后的代码长什么样"
    函数指针表是 `constexpr` 的，优化器能看穿它。在本机（arm64，`-O2`）上，对 `variant<A, B, C>` 调用 `std::visit([](auto x) { return f(x); }, v)`（`f` 是三个外部函数的重载），Clang 23 生成的是几次下标比较加三个直接尾调用，而不是间接跳转；若各分支足够简单，甚至会被折叠成纯算术。所以不必担心 `visit` "一定比 `switch` 慢"——但在 `-O0` 下它确实要经过几层函数调用。

## 思考题

!!! question "思考题 1"
    `std::visit([](auto&& x) -> decltype(auto) { return x; }, v)`，其中 `v` 是 `variant<int, double>` 左值。这能编译吗？若把 lambda 的返回语句改为 `return (x);` 呢？

<details markdown="1">
<summary>展开查看答案与解析</summary>

`return x;` 时 `decltype(auto)` 推导为 `decltype(x)`，即形参的声明类型：对 `int` 分支是 `int&`，对 `double` 分支是 `double&`——类型不同，违反 ¶5，编译错误。`return (x);` 时推导为 `decltype((x))`，`x` 是左值，同样得到 `int&` 与 `double&`，依旧不同，依旧错误。只有所有 alternative 被映射到**同一个**类型（如都 `return double(x);`）或使用 `visit<R>`，才能通过。这道题的要点是：`visit` 的"同类型"检查发生在**所有组合**上，与本次运行时实际持有的类型无关。
</details>

!!! question "思考题 2"
    ¶8 说 *n* = 1 时调用必须是常数时间。那么"按下标做二分查找"的实现（O(log N)）合规吗？`variant` 的复制构造函数呢——它有类似的复杂度要求吗？

<details markdown="1">
<summary>展开查看答案与解析</summary>

不合规：¶8 明确说 *n* = 1 时调用"不依赖于 alternative 的数量"，O(log N) 依赖于 N。这条要求只针对 `visit`。[variant.ctor]、[variant.assign] 等对复制构造、赋值并没有写 *Complexity* 元素，所以标准层面实现可以用任意方式分派（当然实际实现都复用 `visit` 的机制）。另外注意 ¶8 约束的是"对可调用对象的调用"，不包括 ¶7 中检查 valueless 的那一步——对 *n* = 1 那也只是一次比较。
</details>

## 小结

| 方面 | 规则 |
|---|---|
| 可接受的实参 | `variant` 或唯一派生自某个 `variant` 特化的类（*as-variant*，Constraints，C++23 / DR） |
| 调用形式 | `INVOKE(vis, GET<m>(std::forward<V>(vars))...)`，值类别与 const 性质被转发 |
| Mandates | 所有组合都可调用；形式 ① 中所有结果类型与值类别相同 |
| `visit<R>`（C++20） | 每个结果隐式转换为 `R`；`R = void` 时丢弃 |
| 异常 | 任一实参 valueless → `bad_variant_access` |
| 复杂度 | *n* ≤ 1 时常数时间（规范性要求）；*n* > 1 无要求 |
| 成员 `visit`（C++26） | 等价于 `std::visit(vis, (V)self)`；`visit<类型>` 只匹配带 `R` 的版本 |
| overload 模式 | 继承 lambda + `using Ts::operator()...` + 聚合 CTAD（C++20 起不需要推导指引） |
