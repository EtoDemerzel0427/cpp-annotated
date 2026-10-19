---
title: variant 的访问
summary: std::visit、visit<R> 与 C++26 成员 visit 的规则：访问者必须处理所有组合、结果类型必须一致、valueless 时抛异常、单个 variant 时常数时间，以及 overload 模式和 libc++ 的函数指针表实现。
status: done
papers: P0088R3, P0655R1, P2162R2, P2637R3, P0195R2, P1816R0
related: variant, variant.variant, func.require, over.match.class.deduct, dcl.init.aggr, namespace.udecl, forward, over.match.call
tags: 标准库, variant, visit, 模式匹配, 重载
updated: 2026-10-19
---

!!! tldr
    - `std::visit(f, vs...)` 在运行时查出每个 variant 当前持有的类型，再用这些具体类型的值调用 `f`；`f` 必须能处理所有类型组合，漏掉一个就编译失败。
    - 不指定返回类型时，所有组合的调用结果必须类型相同、值类别也相同；想统一成某个类型，用 C++20 的 `visit<R>`。
    - 任何一个实参不持有值（valueless）时抛 `bad_variant_access`；只访问一个 variant 时，调用必须在常数时间内完成。
    - 从 variant 派生的类也能直接传给 `visit`；C++26 又增加了成员函数 `v.visit(f)`。
    - 用一组 lambda 拼成访问者的 overload 模式只是普通的重载决议，隐式转换照常发生，缺一个分支不一定会报错。

`visit` 的声明和 `variant` 的基本概念见 [[variant]]；它把调用交给 *INVOKE*（[[func.require]]），所以访问者可以是任何可调用对象，包括成员指针。

## visit 做什么

```cpp run title="visit-basic.cpp" ok
#include <cassert>
#include <string>
#include <variant>

int main() {
  std::variant<int, double, std::string> v = 3.5;
  auto size = [](const auto& x) { return sizeof(x); };
  assert(std::visit(size, v) == sizeof(double));
  v = std::string("hi");
  assert(std::visit(size, v) == sizeof(std::string));
}
```

泛型 lambda 的 `operator()` 是一个模板，`visit` 对每个候选类型各实例化一次。运行时 `visit` 读出 `v.index()`，调用对应的那一个。换句话说，它把运行时的下标变成了编译期的重载选择：不用手写 `switch`，也不会漏掉某个分支。

[variant.visit] 规定了两个非成员函数模板和两个成员函数模板：

```cpp
template<class Visitor, class... Variants>
  constexpr see below visit(Visitor&& vis, Variants&&... vars);  // ①
template<class R, class Visitor, class... Variants>
  constexpr R visit(Visitor&& vis, Variants&&... vars);          // ② C++20

// variant 的成员，C++26
template<class Self, class Visitor>
  constexpr decltype(auto) visit(this Self&& self, Visitor&& vis);  // ③
template<class R, class Self, class Visitor>
  constexpr R visit(this Self&& self, Visitor&& vis);               // ④
```

## 调用的形式（¶4–6）

¶4 设实参中有 `n` 个 variant。从每个 variant 各取一个下标，组成一组 `m`，只要每个下标都在范围内，这组下标就是有效的。对每组有效的 `m`，标准定义一个调用表达式 `e(m)`：

```cpp
INVOKE(std::forward<Visitor>(vis), GET<m>(std::forward<V>(vars))...)     // 形式 ①
INVOKE<R>(std::forward<Visitor>(vis), GET<m>(std::forward<V>(vars))...)  // 形式 ②
```

注意 `std::forward<V>(vars)`：实参的值类别和 const 会传给 *GET*。`std::visit(f, std::move(v))` 中访问者收到的是候选值的右值，`std::visit(f, std::as_const(v))` 中收到的是 `const` 左值。

¶6 实际执行的是各 variant 当前下标对应的那一个 `e(m)`，形式 ① 的返回类型是 `decltype(e(m))`。

## 所有组合都要合法，结果要一致（¶5）

!!! std
    *Mandates*: For each valid pack `m`, `e(m)` is a valid expression. All such expressions are of the same type and value category.

这句话有两层意思。

第一，访问者必须能处理所有组合。两个 variant 分别有 3 个和 2 个候选类型，就要 6 种调用全部合法。这是 *Mandates*（[[structure.specifications]]），不满足时直接编译错误，不会让 `visit` 退出重载决议。

第二，所有组合的结果类型和值类别必须相同，与本次运行时实际持有哪个类型无关。这一点常常让人意外：

<div class="compare" markdown="1">

```cpp error
#include <variant>
int main() {
  std::variant<int, double> v = 1;
  // 一个返回 int，一个返回 double
  auto r = std::visit(
      [](auto x) { return x; }, v);
  (void)r;  // 上一行 error
}
```

```cpp error
#include <variant>
int g;
struct F {
  int& operator()(int) const { return g; }
  int operator()(double) const { return 0; }
};
int main() {
  std::variant<int, double> v = 1;
  // 值类别不同：左值和纯右值
  (void)std::visit(F{}, v);  // error
}
```

</div>

libc++ 对这两种情况给出同一条 `static_assert` 消息："`std::visit` requires the visitor to have a single return type."

为什么不自动取公共类型？那会引入访问者没有写出来的隐式转换。想要统一的返回类型，就明确写出来，这就是形式 ②。

### visit<R>

形式 ② 使用 *INVOKE*<R>：每个调用的结果都隐式转换为 `R`；`R` 是 `void` 时结果被丢弃。各个调用原本的结果类型可以不同，只要都能转换为 `R`。它由 [[P0655R1]] 在 C++20 加入。

```cpp run title="visit-r.cpp" ok
#include <cassert>
#include <string>
#include <type_traits>
#include <variant>

int main() {
  std::variant<int, double> v = 1;
  double r = std::visit<double>([](auto x) { return x; }, v);
  assert(r == 1.0);  // int 和 double 都转成 double

  int calls = 0;
  std::visit<void>([&](auto x) { ++calls; return x; }, v);
  assert(calls == 1);  // R = void：丢弃结果

  std::variant<int, std::string> w = "abc";
  auto n = w.visit<std::size_t>([](const auto& x) {  // 成员 visit<R>
    if constexpr (std::is_same_v<std::decay_t<decltype(x)>, int>) return x;
    else return x.size();
  });
  assert(n == 3);
}
```

## 异常与复杂度（¶7–8）

¶7 只要任何一个实参 variant 处于 valueless 状态（见 [[variant.variant]]），`visit` 就抛出 `bad_variant_access`，访问者一次也不会被调用。

```cpp run title="visit-valueless.cpp" ok
#include <cassert>
#include <variant>

struct S { operator int() { throw 42; } };

int main() {
  std::variant<float, int> v{12.f};
  try { v.emplace<1>(S()); } catch (int) {}  // v 失去值
  try {
    std::visit([](auto) {}, v);
    assert(false);
  } catch (const std::bad_variant_access&) {}
}
```

¶8 规定了复杂度：

!!! std
    For *n* ≤ 1, the invocation of the callable object is implemented in constant time, i.e., for *n* = 1, it does not depend on the number of alternative types of `V_0`. For *n* > 1, the invocation of the callable object has no complexity requirements.

这是规范性要求。只访问一个 variant 时，不能实现成按下标逐个比较的 `if` 链，即使有 100 个候选类型也要常数时间。实践中这意味着跳转表（函数指针数组），或者编译器能生成跳转表的 `switch`。

访问多个 variant 时不作要求，因为 `k` 个各有 `N` 个候选类型的 variant 有 `N^k` 种组合，标准不想强迫实现生成指数大小的表。`n` 为 0 时，`visit(f)` 就是直接调用 `f()`。

## 从 variant 派生的类（¶1–3）

```cpp run title="visit-derived.cpp" ok
#include <cassert>
#include <variant>

struct Expr : std::variant<int, double> {
  using variant::variant;
};

int main() {
  Expr e = 2.5;
  double d = std::visit([](auto x) { return double(x); }, e);
  assert(d == 2.5);
  assert(e.visit([](auto x) { return x > 0; }));  // 成员 visit
}
```

从 variant 派生是定义递归数据结构（如表达式树）的自然写法。`visit` 能接受 `Expr`，靠的是 ¶1 定义的一组仅用于说明的函数模板 *as-variant*（[[g:as-variant]]）：它们分别接受 `variant<Ts...>` 的四种引用（`&`、`const&`、`&&`、`const&&`），原样返回。

`visit` 把每个实参先交给 *as-variant*，结果的类型记作 `V_i`。¶2 的约束要求每个 `V_i` 都是合法的类型。由于 *as-variant* 是函数模板，对形参 `variant<Ts...>&` 做模板实参推导时，实参如果是某个 variant 特化的派生类，推导会得到那个基类（[[temp.deduct.call]]）。于是：

- 实参是 variant 本身：`V_i` 就是它的引用类型；
- 实参唯一地、可访问地派生自某个 variant 特化：`V_i` 是那个基类的引用，访问针对这个基类子对象；
- 实参不是 variant，或者派生自多个 variant 特化导致推导有歧义：`V_i` 不合法，`visit` 不参与重载决议。

```cpp run title="visit-ambiguous-base.cpp" error
#include <variant>

struct Both : std::variant<int>, std::variant<double> {};

int main() {
  Both b;
  std::visit([](auto) {}, b);  // error: as-variant 推导有歧义
}
```

!!! history "为什么需要 as-variant"
    C++17 的 `visit` 要求实参就是 variant，并用 `variant_size_v<remove_reference_t<Variants>>` 之类的类型特征来描述规则。`variant_size<Expr>` 没有特化，于是从 variant 派生的写法在不同实现上时而能编译，时而不能。[[P2162R2]] 用 *as-variant* 统一了规则，进入 C++23，各实现也在 C++17 模式下采用了它。libc++ 的 `__cpp_lib_variant` 为 `202102L`，表示实现了这一改动。

## 成员 visit（¶9–13）

C++26 的 [[P2637R3]] 给 variant 增加了成员 `visit`，用显式对象形参（deducing this，[[dcl.fct]]）写成。

¶9 先令 `V` 为 *OVERRIDE_REF*(`Self&&`, *COPY_CONST*(`remove_reference_t<Self>`, `variant`))（[[forward]]），意思是把 `self` 的 const 和引用种类照搬到 `variant` 上。¶11 效果等价于 `return std::visit(std::forward<Visitor>(vis), (V)self);`。¶13 `visit<R>` 版本同理，转给 `std::visit<R>`。

转换 `(V)self` 是必要的：`Self` 可能是 `Expr` 这样的派生类，先转换到基类 variant 的引用，再交给非成员 `visit`。

¶10 有一条不太显眼的约束：

!!! std
    *Constraints*: The call to `visit` does not use an explicit *template-argument-list* that begins with a type *template-argument*.

原因在于两个成员模板的模板形参列表。③ 是 `<class Self, class Visitor>`，④ 是 `<class R, class Self, class Visitor>`。写 `v.visit<int>(f)` 的人想调用 ④ 并指定 `R = int`，但对 ③ 来说，显式给出的 `int` 会被当成 `Self`，造成误选或费解的错误。¶10 把 ③ 从这种调用中排除。

libc++ 的做法是在 ③ 的模板形参列表最前面放一个类型为私有标签类的非类型模板形参 `__variant_visit_barrier_tag`，并给它默认实参。任何以类型开头的显式模板实参都无法匹配它，③ 自然不可行。

成员 `visit` 的好处主要在写法上：`v.visit(f)` 对象在前、操作在后，和链式调用一致，也不用先把派生类转换为 variant。

## overload 模式

用一组 lambda 拼成访问者，是 `visit` 最常见的用法，叫作 **overload 模式**（[[g:overload-pattern]]）：

```cpp run title="overloaded.cpp" ok
#include <cassert>
#include <string>
#include <variant>

template<class... Ts>
struct overloaded : Ts... { using Ts::operator()...; };

int main() {
  std::variant<int, double, std::string> v = 3.5;
  auto describe = overloaded{
    [](int) { return std::string("int"); },
    [](double) { return std::string("double"); },
    [](const std::string& s) { return "string:" + s; },
  };
  assert(std::visit(describe, v) == "double");
  v = "hi";
  assert(std::visit(describe, v) == "string:hi");

  // 两个 variant：访问者要处理 3×2 = 6 种组合
  std::variant<int, std::string> w = 7;
  auto both = std::visit([](const auto& a, const auto& b) {
    return sizeof(a) + sizeof(b);
  }, v, w);
  assert(both == sizeof(std::string) + sizeof(int));
}
```

`overloaded` 的两行定义用到了三个语言特性：

1. 闭包类型是普通的类（[[expr.prim.lambda.closure]]），可以作为基类。
2. using 声明中的包展开 `using Ts::operator()...;`（C++17，[[P0195R2]]，[[namespace.udecl]]）把所有基类的 `operator()` 引入同一个作用域，形成一个重载集。没有这一句，不同基类的同名成员会让名字查找产生歧义（[[class.member.lookup]]）。
3. `overloaded` 是没有构造函数的聚合，每个 lambda 初始化一个基类子对象（[[dcl.init.aggr]]）。C++17 需要手写推导指引 `template<class... Ts> overloaded(Ts...) -> overloaded<Ts...>;`；C++20 的 [[P1816R0]] 引入了**聚合推导候选**（[[g:aggregate-deduction-candidate]]，[[over.match.class.deduct]]），编译器根据聚合的元素自动生成这个指引。

!!! pitfall "overload 模式就是普通的重载决议"
    选择哪个 lambda，是对 `vis(alt)` 做普通的重载决议，隐式转换照常发生：

    ```cpp run title="overload-trap.cpp" ok
    #include <cassert>
    #include <string>
    #include <variant>

    template<class... Ts>
    struct overloaded : Ts... { using Ts::operator()...; };

    int main() {
      std::variant<std::string, bool> v = std::string("x");
      auto r = std::visit(overloaded{
        [](bool) { return 1; },
        [](const auto&) { return 2; },
      }, v);
      assert(r == 2);  // 泛型 lambda 精确匹配

      std::variant<char, double> w = 'a';
      auto r2 = std::visit(overloaded{
        [](int) { return 1; },
        [](double) { return 2; },
      }, w);
      assert(r2 == 1);  // 没有 char 分支：char→int 是提升
    }
    ```

    第二个例子说明，忘记写某个分支不一定编译失败，只要现有分支能通过隐式转换接住它。需要严格穷尽时，可以再加一个基类 `struct strict { template<class T> void operator()(T) = delete; };`，写成 `overloaded{..., strict{}}`。任何没有精确匹配的类型都会选中这个删除的模板而报错。

## libc++ 的实现：函数指针表

libc++ 在编译期构造一个 N 维的函数指针数组，运行时按下标取出一项再调用：

1. 对每一种下标组合 `(I_0, I_1, ...)` 实例化一个分派函数，它做的事就是用 `__get_alt<I_0>(v0), __get_alt<I_1>(v1), ...` 调用访问者；
2. 这些函数的地址放进嵌套的 `__farray<FnPtr, N>`，整个表是 `constexpr` 局部变量；
3. 按各 variant 的下标逐维索引，取出函数指针并调用。

规格中的几条要求在实现里都有对应：

- ¶5 的结果一致：所有函数指针必须同一类型才能放进同一个数组，不同时就触发前面那条 `static_assert`。
- ¶5 的穷尽性：调用前用 `static_assert(is_invocable_v<...>)` 检查，消息是 "`std::visit` requires the visitor to be exhaustive."
- ¶7 的 valueless 检查：查表之前先调用 `__throw_if_valueless`，因为无值标记不是有效下标。
- ¶2 的约束：`visit` 的声明带一个默认模板实参 `void_t<decltype(std::__as_variant(std::declval<_Vs>()))...>`，用 SFINAE 实现。
- ¶8 的复杂度：查表是 O(1)。多个 variant 时，表的大小是各候选类型数之积，编译时间和代码体积随之增长。

variant 自己的复制构造、赋值、`swap`、比较运算符和 `hash` 也复用这套分派机制。

!!! impl "优化之后的代码"
    函数指针表是 `constexpr` 的，优化器能看穿它。本机（arm64，`-O2`）上，对 `variant<A, B, C>` 调用 `std::visit([](auto x) { return f(x); }, v)`（`f` 是三个外部函数的重载），Clang 23 生成的是几次下标比较加三个直接的尾调用，没有间接跳转。所以不必认定 `visit` 一定比 `switch` 慢；不过在 `-O0` 下它确实要经过好几层函数调用。

## 思考题

!!! question "思考题 1"
    `v` 是 `variant<int, double>` 左值。`std::visit([](auto&& x) -> decltype(auto) { return x; }, v)` 能编译吗？把返回语句改成 `return (x);` 呢？

<details markdown="1">
<summary>答案</summary>

都不能。`return x;` 时 `decltype(auto)` 推导为 `decltype(x)`，即形参的声明类型：`int` 分支是 `int&`，`double` 分支是 `double&`，类型不同，违反 ¶5。`return (x);` 时推导为 `decltype((x))`，`x` 是左值，同样得到 `int&` 和 `double&`。只有让所有分支返回同一个类型（如都 `return double(x);`），或者改用 `visit<R>`，才能通过。结果一致的检查针对所有组合，与运行时实际持有的类型无关。
</details>

!!! question "思考题 2"
    只访问一个 variant 时，按下标做二分查找（O(log N)）的实现合规吗？variant 的复制构造函数有类似的复杂度要求吗？

<details markdown="1">
<summary>答案</summary>

不合规。¶8 明确说 *n* = 1 时调用不依赖于候选类型的数量，O(log N) 依赖于 N。这条要求只针对 `visit`：[variant.ctor]、[variant.assign] 没有写 *Complexity* 元素，标准层面复制构造和赋值可以用任意方式分派，实际实现都复用 `visit` 的机制。另外，¶8 约束的是对可调用对象的调用，不包括 ¶7 的 valueless 检查，而这项检查对 *n* = 1 也只是一次比较。
</details>

## 小结

| 方面 | 规则 |
|---|---|
| 可接受的实参 | variant，或唯一派生自某个 variant 特化的类（*as-variant*，约束） |
| 调用形式 | `INVOKE(vis, GET<m>(std::forward<V>(vars))...)`，值类别和 const 随实参传递 |
| 编译期要求 | 所有组合都可调用；形式 ① 的所有结果类型和值类别相同 |
| `visit<R>`（C++20） | 每个结果隐式转换为 `R`；`R = void` 时丢弃 |
| 异常 | 任一实参 valueless 时抛 `bad_variant_access` |
| 复杂度 | 一个 variant 时常数时间；多个时不作要求 |
| 成员 `visit`（C++26） | 等价于 `std::visit(vis, (V)self)`；`v.visit<类型>(f)` 只匹配带 `R` 的版本 |
| overload 模式 | 继承 lambda、`using Ts::operator()...`、聚合的类模板实参推导 |
