---
title: 显式类型转换（函数式写法）
summary: T(x)、T(a, b)、T()、T{...}、auto(x) 和类模板名加初始化器的含义：单个圆括号实参时 T(x) 与 C 风格转换 (T)x 完全等价，其他形式用初始化器直接初始化一个 T。
status: done
papers: P0849R8, P0091R3, P0960R3
related: expr.cast, expr.static.cast, dcl.init, dcl.init.list, dcl.type.auto.deduct, dcl.type.class.deduct, over.match.class.deduct, conv.rval, topics/casts
tags: 表达式, 类型转换, 初始化, auto, CTAD
updated: 2026-10-19
---

!!! tldr
    - 只有一个圆括号实参时，`T(x)` 与 C 风格转换 `(T)x` 完全等价，可以悄悄完成 `const_cast` 或 `reinterpret_cast`。
    - 其他形式（多个实参、空括号、花括号）得到一个 `T` 的 prvalue，用初始化器直接初始化；花括号形式禁止窄化。
    - 类型部分只能是单个类型名，`unsigned long(x)`、`int*(p)` 写不出来。
    - 类模板名先做类模板实参推导，`auto` 先按 `auto` 的规则推导，然后才按上面的规则处理。
    - C++23 的 `auto(x)` 得到 `x` 退化后的一个 prvalue 副本，常用于避免引用被后续操作改掉。

```cpp run title="functional-is-c-cast.cpp" ok
#include <cstdint>

struct B {};
struct D : private B {};   // 私有继承

int main() {
    const int c = 42;
    using IP = int*;
    using UIP = std::uintptr_t;
    using BP = B*;

    IP p = IP(&c);     // 等价于 (int*)&c：去掉了 const
    UIP u = UIP(&c);   // 等价于 (std::uintptr_t)&c：reinterpret_cast
    D d;
    BP bp = BP(&d);    // 等价于 (B*)&d：无视私有继承
    (void)p; (void)u; (void)bp;
    // *p = 1;         // 若执行：UB，修改 const 对象
}
```

`int(3.7)`、`std::string("abc")`、`Point{1, 2}`、`std::vector{1, 2, 3}`、`auto(x)` 在语法上是同一种表达式：**函数式写法的显式类型转换**（explicit type conversion, functional notation）。它看起来像调用构造函数，上面的例子却说明它不总是那么温和：三行转换在 `-Wall -Wextra -pedantic` 下都没有任何警告。

## 能写什么类型

函数式转换的类型部分只能是 *simple-type-specifier*（单个类型名、`int`、`auto`、`decltype(e)`、模板名等）或 *typename-specifier*（`typename T::type`），见 [[expr.post]] 的语法。由多个关键字组成的类型和带声明符的类型都不行：

```cpp title="simple-type-only.cpp" error
int x = 1;
unsigned long a = unsigned long(x);   // error: 不是单个类型说明符
int* p = int*(nullptr);               // error: 不能带声明符
using UL = unsigned long;
UL b = UL(x);                         // OK：别名是单个类型名
```

所以这类类型要么先起别名，要么改用 `static_cast<unsigned long>(x)`。

## 先确定类型 T（¶1）

¶1 类型说明符后跟初始化器，初始化器是圆括号里可选的表达式列表或花括号列表，表达式用它构造一个指定类型的值。处理之前先确定类型 `T`：

1. 如果写的是类模板名（被推导类类型的占位符，如 `std::pair`），把它替换为类模板实参推导（CTAD，[[over.match.class.deduct]]）选中的函数的返回类型。
2. 否则，如果类型里含 `auto`，把它替换为按 [[dcl.type.auto.deduct]] 推导出的类型。

```cpp run title="deduce-T.cpp" ok
#include <type_traits>
#include <utility>
#include <vector>

int x = 1;
int arr[3];
std::vector<int> v;

static_assert(std::is_same_v<decltype(std::pair(1, 2.0)), std::pair<int, double>>);
static_assert(std::is_same_v<decltype(std::vector{1, 2}), std::vector<int>>);
static_assert(std::is_same_v<decltype(std::vector(v)), std::vector<int>>);  // 复制，不是 vector<vector<int>>
static_assert(std::is_same_v<decltype(auto(x)), int>);       // C++23
static_assert(std::is_same_v<decltype(auto(arr)), int*>);    // 数组退化为指针
static_assert(std::is_same_v<decltype(auto{arr}), int*>);

int main() {}
```

`auto(x)` 的推导与声明 `auto v(x);` 相同，会发生退化：数组变指针，函数变函数指针，去掉引用和顶层 cv。类型部分只能是 `auto` 本身，`decltype(auto)(x)` 和 `auto&(x)` 都非良构。

## 四种情形（¶1.1–¶1.4）

确定 `T` 之后按初始化器的形式依次匹配：

| 列表项 | 条件 | 含义 | 值类别 |
|---|---|---|---|
| ¶1.1 | 圆括号里恰好一个表达式 | 等价于 C 风格转换 `(T)e`（[[expr.cast]]） | 由 `(T)e` 决定 |
| ¶1.2 | `T` 是 cv `void` | 初始化器必须是 `()` 或 `{}`（包展开之后），不做任何初始化 | `void` 的 prvalue |
| ¶1.3 | `T` 是引用类型 | 如同用初始化器直接初始化一个虚构变量 `T t`，以 `t` 作为结果 | 左值引用或函数右值引用为左值，对象右值引用为亡值 |
| ¶1.4 | 其他 | `T` 的 prvalue，结果对象用初始化器直接初始化（[[dcl.init]]） | prvalue |

另有一条限制：初始化器是圆括号形式时，`T` 不得是数组类型。

### 单个圆括号实参等于 C 风格转换（¶1.1）

!!! std
    If the initializer is a parenthesized single expression, the type conversion expression is equivalent to the corresponding cast expression.

这里的等价没有任何保留。C 风格转换会依次尝试 `const_cast`、`static_cast`、`static_cast` 加 `const_cast`、`reinterpret_cast`、`reinterpret_cast` 加 `const_cast`，`static_cast` 还可以无视访问控制转换到私有基类（[[expr.cast#4]]）。页首例子的三行分别用到了其中三种能力。

对标量和指针类型来说，函数式转换并不比 C 风格转换安全。安全的单参数写法是 `static_cast<T>(x)`，或者花括号 `T{x}`，后者还禁止窄化。

对类类型 `T`，`T(x)` 经 C 风格转换落到 `static_cast`，再按 [[expr.static.cast#5]] 成为直接初始化 `T t(x)`，效果就是调用构造函数。所以日常的 `std::string(p)` 没有问题，需要警惕的是指针、引用和算术类型。

函数式转换出现得比具名转换早。C++ 最初引入 `T(x)`，是为了让内置类型和用户定义类型有统一的构造写法，当时可以对齐的只有 C 风格转换；具名转换后来才加入，`T(x)` 的含义已经不能再改。

### `void()`（¶1.2）

`void()` 和 `void{}` 是 `void` 类型的 prvalue，什么也不做，主要用在泛型代码里：

```cpp run title="void-expr.cpp" ok
template<class... T>
void ignore(T... t) {
    (void(t), ...);       // 每一项都是 ¶1.1：(void)t
}

template<class F>
auto call(F f) -> decltype(f(), void()) {   // 检查 f() 合法；返回类型恒为 void
    f();
}

int main() {
    ignore();
    ignore(1, 2.0);
    call([] { return 42; });
}
```

包展开之后这个限定处理的是 `void(t...)`：包为空时初始化器是 `()`，合法；包有一个元素时是单个表达式，按 ¶1.1 是 `(void)t`；两个及以上元素时非良构。

### 引用类型（¶1.3）

`T` 是引用时（只能通过别名或 `decltype` 写出），单个圆括号实参仍按 ¶1.1 处理，其余形式如同声明 `T t(初始化器);` 再使用 `t`：

```cpp run title="ref-conv.cpp" ok
#include <type_traits>

int x = 1;
using R = int&;
using RR = int&&;
using CR = const int&;

static_assert(std::is_same_v<decltype(R(x)), int&>);          // ¶1.1：(int&)x
static_assert(std::is_same_v<decltype(RR(x)), int&&>);        // ¶1.1：(int&&)x
static_assert(std::is_same_v<decltype(R{x}), int&>);          // ¶1.3：int& t{x};
static_assert(std::is_same_v<decltype(CR{1}), const int&>);   // ¶1.3：绑定到临时量

int main() {}
```

`CR{1}` 绑定了一个临时量。标准没有说明虚构变量 `t` 的生命周期，因此这个临时量能活多久并不明确。稳妥的用法是只在所在的完整表达式内使用结果。

### 直接初始化一个 prvalue（¶1.4）

其余情况都得到 `T` 的 prvalue，结果对象被直接初始化。C++17 起 prvalue 本身不是对象，结果对象由上下文提供（[[basic.lval]]）：`T t = T(a, b);` 中结果对象就是 `t`，没有临时量，也不需要移动构造函数。

| 写法 | 初始化方式 | 效果 |
|---|---|---|
| `T()` | [[g:value-initialization|值初始化]] | 标量为零；有用户提供的默认构造函数时调用它 |
| `T{}` | 列表初始化 | 值初始化，或对聚合做聚合初始化 |
| `T(a, b)` | 直接初始化 | 调用构造函数；C++20 起聚合也可以用圆括号（[[P0960R3]]） |
| `T{a, b}` | 直接列表初始化 | 优先选 `initializer_list` 构造函数；禁止窄化 |

```cpp run title="value-init.cpp" ok
#include <string>

struct Agg { int a, b; };
struct Ctor { int v; Ctor(int a, int b) : v(a + b) {} };

int main() {
    int i = int();             // 0
    int j = int{};             // 0
    Agg g1 = Agg(1, 2);        // C++20：圆括号聚合初始化
    Agg g2 = Agg{1, 2};        // 聚合初始化
    Ctor c = Ctor(1, 2);       // 构造函数
    std::string s = std::string(3, 'x');   // "xxx"
    std::string t = std::string{3, 'x'};   // initializer_list：'\3' 和 'x' 两个字符
    return (i + j + g1.a + g2.b + c.v == 6 && s == "xxx" && t.size() == 2) ? 0 : 1;
}
```

`int(3.5)` 属于 ¶1.1，是 C 风格转换，截断为 3；`int{3.5}` 属于 ¶1.4，是列表初始化，[[g:narrowing-conversion|窄化]]使它非良构。

<div class="compare" markdown="1">

```cpp run ok
int a = int(3.5);   // (int)3.5，值为 3
long long big = 1LL << 40;
int b = int(big);   // 截断，不报错
int main() { return a + b; }
```

```cpp error
int c = int{3.5};   // error: 窄化
long long big = 1LL << 40;
int d = int{big};   // error: 窄化
using A = int[3];
auto e = A(1, 2, 3);  // error: 圆括号
                      // 下 T 不得是数组
```

</div>

数组只能用花括号：`A{1, 2, 3}` 合法，得到一个数组 prvalue。但 `auto v = A{1, 2, 3};` 让 `v` 推导为 `int*`，指向一个在完整表达式结束时就销毁的临时数组，`v` 成了悬垂指针，Clang 会给出 `-Wdangling` 警告。

## `auto(x)`：取一个副本（C++23）

[[P0849R8]] 允许 `auto` 作为函数式转换的类型。`auto(x)` 按 `auto` 推导出类型，把 `x` 复制成一个 prvalue，也就是标准库描述中常说的 decay-copy。标准例 1：

```cpp run title="auto-copy.cpp" ok
struct A {};
void f(A&) {}     // #1
void f(A&&) {}    // #2
A& g() { static A a; return a; }

int main() {
    f(g());          // 调用 #1：g() 是左值
    f(A(g()));       // 调用 #2：A(g()) 是 prvalue，需要写出类型名
    f(auto(g()));    // 调用 #2：不需要写类型名
}
```

C++23 之前，要得到副本就得写出类型（`std::decay_t<decltype(x)>(x)`）或引入一个具名变量。一个典型用途：

```cpp run title="auto-copy-erase.cpp" ok
#include <vector>

int main() {
    std::vector<int> v{1, 2, 1, 3, 1};
    // std::erase(v, v.front());     // 危险：front() 是引用，删除过程中它所指的元素会被覆盖
    std::erase(v, auto(v.front()));  // 先复制出值 1，再删除
    return v == std::vector<int>{2, 3} ? 0 : 1;
}
```

`auto{x}` 与 `auto(x)` 推导出的类型相同，只是花括号里必须恰好有一个元素。`auto{1, 2}`、`auto()`、`auto{}` 都非良构，后两者没有可以推导的东西。

推导出 `T` 之后，`auto(x)` 照常按 ¶1.1 等价于 `(T)x`。由于 `T` 就是 `x` 退化后的类型，这个转换只会是 `static_cast` 或类类型的复制、移动构造，不会变成 `reinterpret_cast`。

## 类模板名加初始化器

类模板名后跟初始化器时，先由 CTAD 确定 `T`（[[P0091R3]]），之后才按 ¶1.1–¶1.4 分派。`std::pair(1, 2.0)`、`std::lock_guard(m)` 因此可以省略模板实参。`std::vector(v)` 中 `v` 是 `std::vector<int>`，CTAD 选中复制推导候选，得到 `std::vector<int>`；然后按 ¶1.1 等价于 `(std::vector<int>)v`，即复制构造。

## 与声明的歧义

`T(x);` 单独作为一条语句时，[[stmt.ambig]] 规定能解释为声明的就按声明处理。所以 `std::lock_guard<std::mutex>(m);` 声明了一个名为 `m` 的 `lock_guard` 变量，而不是对互斥量 `m` 加锁：要么编译失败，要么含义完全不同。这条规则不在本节，但它是使用函数式转换时最常见的意外。

## 历史与演进

!!! history
    - C++98：`T(x)` 等价于 `(T)x`；`T()` 初始化为零值（C++03 起称为值初始化）；`T(a, b)` 调用构造函数。
    - C++11：花括号形式 `T{...}`，列表初始化禁止窄化。
    - C++17：类模板实参推导（[[P0091R3]]）；prvalue 直接初始化最终对象，不再经过临时量。
    - C++20：圆括号聚合初始化（[[P0960R3]]）。
    - C++23：`auto(x)` 与 `auto{x}`（[[P0849R8]]）。

## 常见误解

!!! pitfall "`T(x)` 总是构造函数调用"
    对指针和算术类型，它是 C 风格转换。`IntPtr(&const_obj)`、`Handle(pointer)`、`uintptr_t(p)` 都可能悄悄完成 `const_cast` 或 `reinterpret_cast`。审查代码时，对标量或指针类型的单参数函数式转换，应当和 C 风格转换一样对待。

!!! pitfall "`T(a)` 和 `T{a}` 只是写法不同"
    它们可能选中不同的构造函数：`std::vector<int>(3)` 是 3 个零，`std::vector<int>{3}` 是一个元素 3；`std::string(3, 'x')` 与 `std::string{3, 'x'}` 也不同。

!!! pitfall "`auto(x)` 开销很小"
    对类类型，`auto(v)` 会复制整个对象，例如整个 `std::vector`。它的价值在于表意清楚，而不在于便宜。

## 思考题

!!! question "思考题 1"
    设 `const char* p = "abc";`，`std::uintptr_t(p)`、`std::uintptr_t{p}`、`static_cast<std::uintptr_t>(p)` 哪些合法？

<details markdown="1">
<summary>答案</summary>

只有 `std::uintptr_t(p)` 合法：按 ¶1.1 等价于 `(std::uintptr_t)p`，最终是 `reinterpret_cast`。`std::uintptr_t{p}` 按 ¶1.4 是列表初始化，指针不能隐式转换为整数，非良构。`static_cast` 不能把指针转换为整数（[[expr.static.cast]]），也非良构。看起来最无害的写法反而是唯一能编译的。
</details>

!!! question "思考题 2"
    `template<class... T> void h(T... t) { int(t...); }`，`h()`、`h(1)`、`h(1, 2)` 各自如何？

<details markdown="1">
<summary>答案</summary>

`h()`：包为空，得到 `int()`，按 ¶1.4 值初始化，合法。`h(1)`：单个表达式，按 ¶1.1 是 `(int)1`，合法。`h(1, 2)`：按 ¶1.4 要用两个初始化器直接初始化一个 `int`，标量只能有一个初始化器，非良构。
</details>

!!! question "思考题 3"
    `using A = int[2]; auto&& r = A{1, 2};` 中 `r` 的类型是什么？临时数组活多久？与 `auto v = A{1, 2};` 有什么不同？

<details markdown="1">
<summary>答案</summary>

`A{1, 2}` 是 `int[2]` 的 prvalue。`auto&&` 推导时不退化，`r` 的类型是 `int(&&)[2]`，临时数组实质化后绑定到引用，生命周期延长到与 `r` 相同（[[class.temporary]]），所以是安全的。`auto v = A{1, 2};` 推导时数组退化为指针，`v` 是 `int*`，临时数组在完整表达式结束时销毁，`v` 悬垂。
</details>
