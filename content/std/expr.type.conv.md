---
title: 显式类型转换（函数式写法）
summary: T(x)、T(a, b)、T()、T{...}、auto(x)、auto{x} 与类模板实参推导：单个圆括号实参时 T(x) 与 C 风格转换 (T)x 完全等价（包括 reinterpret_cast 和 const_cast 的能力），其他形式是对结果对象的直接初始化
status: draft
papers: P0849R8, P0091R3, P0960R3
related: expr.cast, expr.static.cast, dcl.init, dcl.init.list, dcl.type.auto.deduct, dcl.type.class.deduct, over.match.class.deduct, conv.rval, topics/casts
tags: 表达式, 类型转换, 初始化, auto, CTAD
updated: 2026-10-17
---

`int(3.7)`、`std::string("abc")`、`Point{1, 2}`、`std::vector{1, 2, 3}`、`auto(x)` 在语法上属于同一种表达式：**函数式写法的显式类型转换**（explicit type conversion, functional notation）。它看起来像调用类型的构造函数，日常也常这么称呼，但标准里的语义要精确得多，其中有一点很容易出错：

> **只有一个圆括号实参时，`T(x)` 与 C 风格转换 `(T)x` 完全等价。**

这意味着 `T(x)` 可以做 `reinterpret_cast` 和 `const_cast` 能做的一切，它并不比 C 风格转换更安全。

本节只有一段规范性文字（¶1），但它连接了初始化（[[dcl.init]]）、C 风格转换（[[expr.cast]]）、占位符类型推导（[[dcl.type.auto.deduct]]）和类模板实参推导（[[over.match.class.deduct]]）。

## 语法与适用范围

函数式转换的语法（见 [[expr.post]]）：

```text
simple-type-specifier ( expression-list(opt) )
typename-specifier    ( expression-list(opt) )
simple-type-specifier braced-init-list
typename-specifier    braced-init-list
```

类型部分只能是 *simple-type-specifier*（单个类型名、`int`、`auto`、`decltype(e)`、模板名……）或 *typename-specifier*（`typename T::type`）。所以由多个关键字组成的类型、指针、引用、数组声明符都不能直接写：

```cpp title="simple-type-only.cpp" error
int x = 1;
unsigned long a = unsigned long(x);   // error: unsigned long 不是单个 simple-type-specifier
int* p = int*(nullptr);               // error: 不能带声明符
using UL = unsigned long;
UL b = UL(x);                         // OK：别名是单个类型名
```

因此泛型代码里常见 `using U = ...; U(x)` 的写法，或者干脆改用 `static_cast<unsigned long>(x)`。

## 先确定类型 `T`（¶1 前半）

¶1：类型说明符后跟初始化器（圆括号内可选的表达式列表，或花括号初始化列表），以给定的初始化器构造指定类型的值。在讨论具体规则之前，先确定类型 `T`：

1. 如果类型是被推导类类型的占位符（只写了类模板名，如 `std::pair`），把它替换为类模板实参推导（CTAD，[[over.match.class.deduct]]）中重载决议选中的函数的返回类型；
2. 否则，如果类型包含占位符类型（`auto`），把它替换为占位符类型推导（[[dcl.type.auto.deduct]]）确定的类型；
3. 记结果为 `T`。

```cpp run title="deduce-T.cpp" ok
#include <type_traits>
#include <utility>
#include <vector>

int x = 1;
int arr[3];

static_assert(std::is_same_v<decltype(std::pair(1, 2.0)), std::pair<int, double>>);  // CTAD
static_assert(std::is_same_v<decltype(std::vector{1, 2}), std::vector<int>>);         // CTAD
static_assert(std::is_same_v<decltype(auto(x)), int>);       // auto 推导，C++23
static_assert(std::is_same_v<decltype(auto(arr)), int*>);    // 数组退化：推导规则同 auto v = arr;
static_assert(std::is_same_v<decltype(auto{arr}), int*>);

int main() {}
```

`auto(x)` 的推导规则与 `auto v(x);` 声明相同，所以会发生**退化**（decay）：数组变指针、函数变函数指针、去掉顶层 cv 和引用。只有 `auto` 可以这样用；`decltype(auto)(x)` 和 `auto&(x)` 都不行（[[dcl.spec.auto]] 只允许 `auto` 作为函数式转换的类型）。

## 四种情形（¶1.1–¶1.4）

确定 `T` 之后，按初始化器的形式分四种情况，依次匹配：

| 列表项 | 条件 | 含义 | 值类别 |
|---|---|---|---|
| ¶1.1 | 初始化器是圆括号里的单个表达式 | 等价于对应的 C 风格转换 `(T)e`（[[expr.cast]]） | 由 `(T)e` 决定 |
| ¶1.2 | `T` 是 cv `void` | 初始化器必须是 `()` 或 `{}`（包展开后）；不做任何初始化 | prvalue（`void`） |
| ¶1.3 | `T` 是引用类型 | 如同直接初始化一个虚构变量 `T t(初始化器)` 并以 `t` 作为结果 | `T&` 或函数右值引用 ⇒ lvalue；对象右值引用 ⇒ xvalue |
| ¶1.4 | 其他 | 类型 `T` 的 prvalue，其结果对象以初始化器直接初始化（[[dcl.init]]） | prvalue |

另有一条限制：如果初始化器是圆括号（可空）表达式列表，`T` 不得是数组类型。

### ¶1.1：单个圆括号表达式 ≡ C 风格转换

!!! std
    If the initializer is a parenthesized single expression, the type conversion expression is equivalent to the corresponding cast expression.

    初始化器是圆括号中的单个表达式时，类型转换表达式等价于对应的强制转换表达式。

这里的等价没有任何保留。C 风格转换会依次尝试 `const_cast`、`static_cast`、`static_cast` + `const_cast`、`reinterpret_cast`、`reinterpret_cast` + `const_cast`（[[expr.cast#4]]）。所以：

```cpp run title="functional-is-c-cast.cpp" ok
#include <cstdint>

struct B {};
struct D : private B {};   // 私有继承

int main() {
    const int c = 42;
    using IP = int*;
    using UIP = std::uintptr_t;
    using BP = B*;

    IP p = IP(&c);            // 等价于 (int*)&c：const_cast，悄悄去掉了 const
    UIP u = UIP(&c);          // 等价于 (std::uintptr_t)&c：reinterpret_cast
    D d;
    BP bp = BP(&d);           // 等价于 (B*)&d：无视私有继承的 static_cast（[expr.cast]/4.6）
    (void)p; (void)u; (void)bp;
    // *p = 1;                // 若执行：UB，修改 const 对象
}
```

这三行都没有任何警告（`-Wall -Wextra -pedantic` 下也没有）。标准这样设计，是因为函数式转换的历史比具名转换更早：C++ 最初引入 `T(x)` 是为了让用户定义类型和内置类型有统一的构造写法，那时能与之对齐的只有 C 风格转换。具名转换（`static_cast` 等）是 C++98 标准化时才加入的，而 `T(x)` 的语义不能再改。

由此可知，对标量类型而言，认为函数式转换比 C 风格转换安全是一种错觉。真正安全的单参数写法是 `static_cast<T>(x)` 或花括号 `T{x}`（后者还禁止窄化）。

对类类型 `T`，`T(x)` 经 C 风格转换 → `static_cast` → [[expr.static.cast#5]] 的直接初始化 `T t(x)`，效果与直接调用构造函数相同。所以日常的 `std::string(p)` 并没有问题，问题只出在指针、引用、算术类型上。

### ¶1.2：`void()`

`void()` 和 `void{}` 是 `void` 类型的 prvalue，不做任何事。主要用途在泛型代码中：

```cpp run title="void-expr.cpp" ok
template<class... T>
void ignore(T... t) {
    (void(t), ...);       // 每个都是 ¶1.1：单表达式 ⇒ (void)t
    void(sizeof...(t));   // ¶1.1
}

template<class F>
auto call(F f) -> decltype(f(), void()) {   // SFINAE 检查 f() 合法；void() 让返回类型恒为 void
    f();
}

int main() {
    ignore();
    ignore(1, 2.0);
    call([] { return 42; });
}
```

"包展开后"这个限定处理的是 `void(t...)`：如果包为空，初始化器是 `()`，合法（¶1.2）；如果包有一个元素，就变成单表达式，按 ¶1.1 是 `(void)t`；如果有两个及以上，`T` 是 `void` 而初始化器不是 `()`/`{}`，非良构。

### ¶1.3：引用类型

`T` 是引用时（只能经别名或 `decltype` 写出），多实参或花括号形式如同声明 `T t(初始化器);` 并使用 `t`：

```cpp run title="ref-conv.cpp" ok
#include <type_traits>

int x = 1;
using R = int&;
using RR = int&&;
using CR = const int&;

static_assert(std::is_same_v<decltype(R(x)), int&>);     // ¶1.1：(int&)x
static_assert(std::is_same_v<decltype(RR(x)), int&&>);   // ¶1.1：(int&&)x，即 static_cast 左值到亡值
static_assert(std::is_same_v<decltype(R{x}), int&>);     // ¶1.3：int& t{x}; → lvalue
static_assert(std::is_same_v<decltype(CR{1}), const int&>);   // ¶1.3：绑定到临时量

int main() {}
```

`CR{1}` 绑定一个临时量。虚构变量 `t` 只是一种描述手法，标准没有说明 `t` 本身的生命周期，因而这个临时量被延长到何时并不清楚；稳妥的理解是只在所在完整表达式内使用 `CR{1}` 的结果，不要把它绑定到另一个引用上留待以后使用。

### ¶1.4：直接初始化的 prvalue

其余情况（多实参圆括号、空圆括号、花括号）都得到一个 `T` 类型的 prvalue，其结果对象被直接初始化。C++17 起 prvalue 不是对象，结果对象由上下文提供（[[basic.lval]]）：`T t = T(a, b);` 中结果对象就是 `t` 本身，没有临时量，也不需要移动构造函数（保证复制消除）。

具体的初始化语义完全交给 [[dcl.init]]：

| 写法 | 初始化 | 效果 |
|---|---|---|
| `T()` | 值初始化 | 标量 ⇒ 零；有用户提供的默认构造函数 ⇒ 调用它；否则零初始化后（若非平凡）再默认初始化 |
| `T{}` | 列表初始化 → 值初始化或聚合初始化 | 同上，聚合则按成员 |
| `T(a, b)` | 直接初始化 | 构造函数；C++20 起聚合也可用圆括号初始化（[[P0960R3]]） |
| `T{a, b}` | 直接列表初始化 | 优先 `initializer_list` 构造函数；禁止窄化 |

```cpp run title="value-init.cpp" ok
#include <string>

struct Agg { int a, b; };
struct Ctor { int v; Ctor(int a, int b) : v(a + b) {} };

int main() {
    int i = int();             // 0
    int j = int{};             // 0
    double d = double();       // 0.0
    Agg g1 = Agg(1, 2);        // C++20：圆括号聚合初始化
    Agg g2 = Agg{1, 2};        // 聚合初始化
    Ctor c = Ctor(1, 2);       // 构造函数
    std::string s = std::string(3, 'x');   // "xxx"
    std::string t = std::string{3, 'x'};   // initializer_list<char>：两个字符 '\3' 和 'x'
    return (i + j + d + g1.a + g2.b + c.v == 6 && s == "xxx" && t.size() == 2) ? 0 : 1;
}
```

最后两行是 `()` 与 `{}` 的经典差别：花括号优先匹配 `initializer_list` 构造函数（[[over.match.list]]）。

`int(3.5)` 是 ¶1.1（C 风格转换，截断为 3），`int{3.5}` 是 ¶1.4（列表初始化，属于窄化，非良构）。因此花括号形式是更安全的函数式转换：

```cpp title="narrowing.cpp" error
int a = int(3.5);         // OK：(int)3.5，值为 3
int b = int{3.5};         // error: 窄化转换
long big = 1L << 40;
int c = int{big};         // error: 窄化（big 不是常量表达式）
using A = int[3];
auto arr = A(1, 2, 3);    // error: 圆括号初始化器下 T 不得是数组
```

数组只能用花括号：`A{1, 2, 3}` 合法，但它是一个数组 prvalue。`auto v = A{1, 2, 3};` 会让 `v` 推导为 `int*`，指向一个在完整表达式末尾就销毁的临时数组，成为悬垂指针（Clang 会给出 `-Wdangling` 警告）。

## `auto(x)` 与 `auto{x}`（C++23）

[[P0849R8]] 让 `auto` 可以作为函数式转换的类型。`auto(x)` 的含义是按 `auto` 推导出的类型，把 `x` 复制成一个 prvalue，也就是标准库里常说的 *decay-copy*。标准例 1：

```cpp run title="auto-copy.cpp" ok
struct A {};
void f(A&) {}     // #1
void f(A&&) {}    // #2
A& g() { static A a; return a; }

int main() {
    f(g());          // 调用 #1：g() 是左值
    f(A(g()));       // 调用 #2：A(g()) 是 prvalue（需要写出类型名）
    f(auto(g()));    // 调用 #2：auto(g()) 是 prvalue（不需要写类型名）
}
```

需要它的原因是，在 C++23 之前，制造一个副本需要写出类型（`std::decay_t<decltype(x)>(x)`），或者引入一个具名变量（`auto copy = x; use(std::move(copy));`）。典型用例：

```cpp run title="auto-copy-erase.cpp" ok
#include <algorithm>
#include <vector>

int main() {
    std::vector<int> v{1, 2, 1, 3, 1};
    // std::erase(v, v.front());     // 危险：v.front() 是引用，删除过程中它所指的元素会被覆盖
    std::erase(v, auto(v.front()));  // OK：先复制出值 1，再删除
    return v == std::vector<int>{2, 3} ? 0 : 1;
}
```

`auto(x)` 与 `auto{x}` 的区别只在推导规则：`auto{x}` 要求花括号内恰好一个元素（`auto{1, 2}` 非良构），并按直接列表初始化推导（[[dcl.type.auto.deduct]]），结果与 `auto(x)` 相同。`auto()` 与 `auto{}` 非良构，因为没有可供推导的东西。

!!! note "`auto(x)` 也是 ¶1.1 吗？"
    是的：`auto(x)` 先把占位符替换为推导出的 `T`，然后由于初始化器是单个圆括号表达式，等价于 `(T)x`。由于 `T` 是 `x` 退化后的类型，这个 C 风格转换只可能是 `static_cast`（或者对类类型的复制/移动构造），不会意外地变成 `reinterpret_cast`。

## CTAD 与函数式转换

类模板名后跟初始化器时，¶1 先做 CTAD 得到具体类型。这让 `std::pair(1, 2.0)`、`std::lock_guard(m)`、`std::array{1, 2, 3}` 可以省略模板实参。需要注意的是，先由 CTAD 确定 `T`，之后才按 ¶1.1–¶1.4 分派：`std::vector(v)` 中 `v` 是 `std::vector<int>`，CTAD 选中复制推导候选，得到 `std::vector<int>`（复制，而不是 `vector<vector<int>>`），然后按 ¶1.1 等价于 `(std::vector<int>)v`，即复制构造。

## 与声明的歧义

`T(x);` 作为语句时，[[stmt.ambig]] 规定：能解释为声明的就是声明。所以 `std::lock_guard<std::mutex>(m);` 声明了一个名为 `m` 的局部 `lock_guard` 变量（编译失败或产生错误的语义），而不是创建一个临时锁。这不属于本节的规则，但它是使用函数式转换时最常见的意外。

## 历史与演进

!!! history
    - C++98：`T(x)` ≡ `(T)x`；`T()` 值初始化（C++03 引入"值初始化"这一术语）；`T(a, b)` 调用构造函数。
    - C++11：花括号形式 `T{...}`；列表初始化禁止窄化。
    - C++17：CTAD（[[P0091R3]]）；保证复制消除使 `T(...)` 的 prvalue 直接初始化最终对象。
    - C++20：圆括号聚合初始化（[[P0960R3]]），`Agg(1, 2)` 合法。
    - C++23：`auto(x)` / `auto{x}`（[[P0849R8]]）。

## 陷阱

!!! pitfall "`T(x)` 不一定是构造函数调用，对指针和整数它是 C 风格转换"
    `IntPtr(&const_obj)`、`Handle(pointer)`、`uintptr_t(p)` 都会悄悄完成 `const_cast` 或 `reinterpret_cast`。在代码审查中，看到对标量或指针类型的单参数函数式转换，应当像看到 C 风格转换一样警惕。

!!! pitfall "`T(a)` 与 `T{a}` 可能选不同的构造函数"
    `std::vector<int>(3)` 是 3 个零，`std::vector<int>{3}` 是一个元素 3；`std::string(3, 'x')` 与 `std::string{3, 'x'}` 也不同。

!!! pitfall "`auto(x)` 对类类型会复制整个对象"
    对大对象，`auto(v)` 会复制整个 `std::vector`。它的价值在于语义清晰，而不在于廉价。

## 思考题

!!! question "思考题 1"
    设 `const char* p = "abc";`，`std::uintptr_t(p)`、`std::uintptr_t{p}`、`static_cast<std::uintptr_t>(p)` 哪些合法？

<details markdown="1">
<summary>答案</summary>

`std::uintptr_t(p)` 合法：¶1.1，等价于 `(std::uintptr_t)p`，最终解释为 `reinterpret_cast`。`std::uintptr_t{p}` 非良构：¶1.4，列表初始化一个整数不能用指针（没有指针到整数的隐式转换）。`static_cast<std::uintptr_t>(p)` 非良构：`static_cast` 不能把指针转换为整数（[[expr.static.cast]]）。三种写法里看起来最无害的那个，反而是唯一能编译的。
</details>

!!! question "思考题 2"
    `template<class... T> void h(T... t) { int(t...); }`，`h()`、`h(1)`、`h(1, 2)` 各自如何？

<details markdown="1">
<summary>答案</summary>

`h()`：包为空，`int()`，¶1.4 值初始化，合法（结果是 0，被丢弃）。`h(1)`：单表达式，¶1.1，`(int)1`，合法。`h(1, 2)`：多个表达式，¶1.4 要用两个初始化器直接初始化一个 `int`，而标量只能有一个初始化器，所以非良构。
</details>

!!! question "思考题 3"
    `using A = int[2]; auto&& r = A{1, 2};` 中 `r` 的类型是什么？临时数组的生命周期多长？与 `auto v = A{1, 2};` 有何不同？

<details markdown="1">
<summary>答案</summary>

`A{1, 2}` 是 `int[2]` 的 prvalue。`auto&&` 推导时不退化，`r` 的类型是 `int(&&)[2]`，临时数组被实质化并绑定到引用，生命周期延长到 `r` 的生命周期（[[class.temporary]]），因此是安全的。`auto v = A{1, 2};` 中 `auto` 推导发生数组到指针的退化，`v` 是 `int*`，临时数组在完整表达式末尾销毁，`v` 悬垂。
</details>

## 小结

!!! summary
    | 写法 | 规则 | 结果 |
    |---|---|---|
    | `T(e)` | ¶1.1：≡ `(T)e`，可能是 `const_cast`/`static_cast`/`reinterpret_cast` | 由 C 风格转换决定 |
    | `void()` / `void{}` | ¶1.2 | `void` prvalue |
    | `R{e}`、`R(a, b)`（`R` 是引用） | ¶1.3：如同 `R t(...)` | lvalue 或 xvalue |
    | `T()`、`T{}`、`T(a, b)`、`T{a, b}` | ¶1.4：结果对象直接初始化 | prvalue |
    | `auto(e)` / `auto{e}` | 先按 `auto` 推导（退化），再按上表 | prvalue 副本 |
    | `C(args)`（`C` 是类模板） | 先 CTAD 得到 `T`，再按上表 | 同上 |
