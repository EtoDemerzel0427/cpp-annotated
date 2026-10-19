---
title: 占位类型说明符
summary: auto、decltype(auto) 和 Concept auto 怎样推导出类型，可以写在哪些位置；函数返回类型推导的规则：多个 return、递归、模板中的推导时机和重声明。
status: done
covers: dcl.spec.auto.general, dcl.type.auto.deduct
since: c++11
papers: N3638, N3922, P1141, P0849R8, P2266
related: dcl.type.decltype, temp.deduct.call, dcl.fct, expr.type.conv, dcl.struct.bind, stmt.return, temp.param, dcl.type.class.deduct
tags: 声明, 类型推导, auto
updated: 2026-10-19
---

!!! tldr
    - `auto` 的推导就是模板实参推导：`const auto& x = e;` 中 `x` 的类型，等于调用 `template<class U> void f(const U&)` 时形参的类型。唯一的区别是 `auto x = {1, 2};` 推导出 `std::initializer_list<int>`。
    - `decltype(auto)` 按 `decltype` 的规则推导，会保留引用，括号也会改变结果。
    - 函数的多条 return 必须推导出完全相同的类型；第一条 return 之后，函数就可以递归调用自己。
    - 模板里的返回类型推导要实例化函数体，那里的错误是硬错误，不会触发 SFINAE。
    - 占位类型只能出现在标准明确允许的位置：变量、返回类型、函数和 lambda 的形参、模板参数、`new auto`、`auto(x)`；其他位置一律非良构。

**占位类型**（placeholder type）是先占住位置、稍后再替换成具体类型的说明符，通常从初始化器推导。它有两种形式，前面都可以加一个概念作为约束：

```text
placeholder-type-specifier:
    type-constraint(opt) auto
    type-constraint(opt) decltype ( auto )
```

[dcl.type.auto.deduct] 规定怎样推导，[dcl.spec.auto.general] 规定能写在哪里。不带模板实参的类模板名（CTAD）是另一种占位符，见 [[dcl.type.class.deduct]]。

## auto 怎样推导 [dcl.type.auto.deduct]

```cpp run ok
#include <type_traits>
template<class A, class B> constexpr bool same = std::is_same_v<A, B>;
int i = 0;
const int ci = 0;
const int carr[3] = {1, 2, 3};
int f(int);

auto a1 = ci;    static_assert(same<decltype(a1), int>);             // 去掉顶层 const
auto& a2 = ci;   static_assert(same<decltype(a2), const int&>);      // 引用保留 const
auto a3 = carr;  static_assert(same<decltype(a3), const int*>);      // 数组退化
auto& a4 = carr; static_assert(same<decltype(a4), const int(&)[3]>); // 引用不退化
auto a5 = f;     static_assert(same<decltype(a5), int(*)(int)>);     // 函数退化为指针
auto&& a6 = i;   static_assert(same<decltype(a6), int&>);            // 左值 → int&
auto&& a7 = 1;   static_assert(same<decltype(a7), int&&>);           // 右值 → int&&
int main() {}
```

这些规则和函数模板的实参推导完全一致，因为标准就是这样定义 `auto` 的。¶1 把含占位符的类型替换成推导出的类型的过程叫做**占位类型推导**（[[g:placeholder-type-deduction]]）。

### 推导什么、从哪里推导（¶2）

¶2 先确定含占位符的类型 T，以及用来推导的初始化子句 E：

| 场合 | T | E |
|---|---|---|
| ¶2.1 return 语句 | 函数声明的返回类型 | return 的操作数；没有操作数时是 `void()`；操作数是逗号表达式 X 时是 `(X)`；花括号列表则非良构 |
| ¶2.2 变量 | 变量的声明类型 | `= e`、`{ e }`、`( e )` 中的 `e`；花括号和圆括号里都只能有一个表达式 |
| ¶2.3 `auto(…)`、`auto{…}` | `auto` | 括号里唯一的表达式 |
| ¶2.4 常量模板参数 | 模板参数的声明类型 | 对应的模板实参 |

T 不能是数组类型。E 的类型是 `void` 时（无操作数的 return，或者返回一个 `void` 表达式），T 只能是 `decltype(auto)` 或 `cv auto`，不能是 `auto&`、`auto*` 之类。逗号表达式要包上括号，只是因为它不能直接充当初始化子句，意思不变。

```cpp error
#include <initializer_list>
auto f() { return {1, 2}; }    // error: return 不能用花括号列表推导
auto x3{ 1, 2 };               // error: 只能有一个元素
auto v[] = { 1, 2 };           // error: T 不能是数组
auto& g() { return void(); }   // error: E 是 void
```

### 按模板实参推导（¶3）

¶3 对 `auto` 形式（可以带约束），推导分三步：

1. 把 T 中的 `auto` 换成一个新的类型模板参数 `U`，得到 P。如果初始化是复制列表初始化（`= { … }`），换成 `std::initializer_list<U>`，此时 `std::initializer_list` 必须已经声明过（要包含 `<initializer_list>`）。
2. 把 P 当作函数模板的形参类型，E 当作实参，按函数调用的推导规则（[[temp.deduct.call]]）求出 `U`。推导失败则声明非良构。
3. 把 `U` 代回 P，得到最终类型。

例 2 是这条规则最直接的说明：`const auto& i = expr;` 中 `i` 的类型，就是用 `f(expr)` 调用 `template<class U> void f(const U& u);` 时 `u` 的类型。

¶3 中间还有一句边角规则：如果 E 是在函数模板偏序（[[temp.func.order]]）中为 `decltype(auto)` 类型的常量模板参数合成的值，声明非良构。

### 花括号：唯一与模板推导不同的地方

模板实参推导从 `{1, 2}` 推导不出任何东西，`auto` 却可以：

```cpp run ok
#include <initializer_list>
#include <type_traits>
auto x1 = { 1, 2 };   // std::initializer_list<int>
auto x4 = { 3 };      // std::initializer_list<int>：= {…} 总是 initializer_list
auto x5{ 3 };         // int：直接列表初始化，取出唯一的元素推导
static_assert(std::is_same_v<decltype(x1), std::initializer_list<int>>);
static_assert(std::is_same_v<decltype(x4), std::initializer_list<int>>);
static_assert(std::is_same_v<decltype(x5), int>);
int main() {}
```

```cpp error
#include <initializer_list>
auto x2 = { 1, 2.0 };   // error: U 既是 int 又是 double
auto x3{ 1, 2 };        // error: 直接列表初始化只能有一个元素
```

!!! history "`auto x{3};` 曾经是 initializer_list"
    C++11 中 `auto x{3};` 推导为 `std::initializer_list<int>`，几乎总是出乎意料。[[N3922]] 改成了今天的规则：直接列表初始化只允许一个元素，推导为它的类型；`= {…}` 仍然推导为 initializer_list。这一修改作为缺陷报告应用于 C++14，编译器在 C++11 模式下通常也采用新规则。

### decltype(auto)：按 decltype 推导（¶4）

¶4 对 `decltype(auto)` 形式，T 必须就是占位符本身，不能写成 `decltype(auto)*`、`const decltype(auto)&`。推导出的类型是把 E 当作 `decltype` 的操作数得到的类型（[[dcl.type.decltype]]）。

```cpp run ok
#include <type_traits>
template<class A, class B> constexpr bool same = std::is_same_v<A, B>;
int i;
int&& f();
auto           x4a = (i);   static_assert(same<decltype(x4a), int>);
decltype(auto) x4d = (i);   static_assert(same<decltype(x4d), int&>);   // 括号
auto           x5a = f();   static_assert(same<decltype(x5a), int>);
decltype(auto) x5d = f();   static_assert(same<decltype(x5d), int&&>);
auto f2(int x) -> decltype(auto) { return (x); }   // 悬垂引用，Clang 会警告
static_assert(same<decltype(f2(0)), int&&>);
int main() {}
```

`f2` 的返回类型是 `int&&`：C++23 起（[[P2266]]），return 语句中指名局部变量或形参的表达式是 xvalue（[[expr.prim.id.unqual]]），加了括号也一样。C++20 中它推导为 `int&`。两种情况返回的都是悬垂引用。

```cpp error
#include <initializer_list>
int i;
decltype(auto) x6d = { 1, 2 };   // error: { 1, 2 } 不是表达式
decltype(auto)*x7d = &i;         // error: 不是单独的 decltype(auto)
```

!!! lawyer "标准例 3 中的 f1 在 C++23 中非良构"
    同一个例子里还有一行，注释说返回类型是 `int&`：

    ```cpp
    auto f1(int x) -> decltype((x)) { return (x); }
    ```

    返回类型确实是 `int&`，`decltype((x))` 中的 `(x)` 只是普通的左值。但函数体里的 `return (x);` 在 C++23 起是 xvalue，`int&` 不能绑定到它，所以这个定义非良构。本机 Clang 23 报错 "non-const lvalue reference to type 'int' cannot bind to a temporary of type 'int'"。例子只注释了返回类型，没有提到这一点。

### 带约束的占位符（¶5）

¶5 占位符带有概念约束时，推导出的类型必须满足它的**立即声明的约束**（immediately-declared constraint，[[temp.param]]）：把推导出的类型作为概念的第一个实参，后面接上写出的其他实参。

```cpp error
#include <concepts>
std::integral auto a = 1;                 // OK
std::integral auto b = 1.0;               // error: std::integral<double> 不成立
std::convertible_to<long> auto c = 'x';   // OK: 检查 std::convertible_to<char, long>
```

## 占位类型可以写在哪里 [dcl.spec.auto.general]

¶1 占位类型代表一个稍后才替换的类型。下面是所有允许的位置：

| 位置 | 含义 | ¶ |
|---|---|---|
| 变量 `auto x = e;` | 从初始化器推导 | 5 |
| 返回类型 `auto f() { return e; }` | 从 return 语句推导 | 4 |
| `auto f() -> int` | 只是语法，返回类型写在 `->` 后面 | 3 |
| 形参 `void f(auto x)`、`[](auto x) {}` | 函数变成模板，每次调用时推导 | 2 |
| 模板参数 `template<auto N>` | 从模板实参推导常量参数的类型 | 2 |
| `new auto(e)` | 从初始化器推导分配的类型 | 6 |
| `auto(e)`、`auto{e}` | 衰变复制 | 7 |
| 结构化绑定 `auto [a, b] = e;` | 推导隐藏变量的类型 | 5 |

¶8 在没有明确允许的地方使用占位类型，程序非良构。例如模板实参 `std::vector<auto>`、`sizeof(auto)`、`catch (auto e)`、数组元素类型、`using T = auto;`。

### 变量（¶5、¶9）

¶5 用占位类型声明的变量，类型从初始化器推导，而且只能用于变量的初始化声明：占位符必须是说明符序列中的一个说明符，后面每个声明符都必须带非空的初始化器。¶5 末尾说明 `auto` 也用于引入结构化绑定（[[dcl.struct.bind]]）。

```cpp run ok
auto x = 5;                  // int
const auto *v = &x, u = 6;   // v: const int*，u: const int
static auto y = 0.0;         // double
auto f() -> int;
auto (*fp)() -> auto = f;    // 函数指针，返回类型也推导
int f() { return 0; }
int main() { return fp() + int(y) + u - 6; }
```

```cpp error
auto x;                      // error: 没有初始化器
auto int r;                  // error: auto 在 C++11 起不再是存储类说明符
struct S { auto m = 1; };    // error: 非静态数据成员不是变量
```

非静态数据成员不能用 `auto`：默认成员初始化器只是一个默认值，构造函数可以不用它，而成员的类型必须在类定义结束时确定。静态数据成员是变量，可以写 `static inline auto m = 1;`。

¶9 一个声明里有多个声明符时，它们都必须声明变量。每个变量单独推导，但替换 `auto` 的类型必须相同。比较的是替换 `auto` 的类型，不是变量的最终类型：

```cpp error
#include <initializer_list>
int x = 5;
auto a = 5, *y = &x;        // OK: 两处 auto 都是 int
auto b = 5, c = { 1, 2 };   // error: int 与 std::initializer_list<int>
auto d = 1, e = 2.0;        // error: int 与 double
```

### 形参：简写函数模板与泛型 lambda（¶2）

¶2 以下三种形参的类型可以用 `type-constraint(opt) auto` 声明：

- ¶2.1 函数的形参，函数就成为**简写函数模板**（abbreviated function template，[[dcl.fct]]），C++20 引入；
- ¶2.2 lambda 的形参，即泛型 lambda（[[expr.prim.lambda]]），C++14 引入；
- ¶2.3 模板参数，即 `template<auto N>`（C++17）和 `template<std::integral auto N>`（C++20）。

这个占位符叫做**泛型形参类型占位符**（generic parameter type placeholder）。这里只能用 `auto`，不能用 `decltype(auto)`。

```cpp run ok
#include <concepts>
#include <cstdio>
void print(const auto& x) { std::printf("%d\n", int(x)); }
std::integral auto twice(std::integral auto n) { return n * 2; }
template<auto N> struct Const { static constexpr auto value = N; };
int main() {
    print(3.7);   // 等价于 template<class T> void print(const T&)
    auto add = [](auto a, auto b) { return a + b; };
    static_assert(Const<'x'>::value == 'x');
    return twice(2) + add(1, 2) - 7;
}
```

```cpp error
void f(decltype(auto) x);   // error: 形参只能用 auto
```

每个泛型形参类型占位符对应一个虚构的模板参数，所以简写函数模板就是函数模板：可以特化、显式实例化，参与偏序，也和模板一样受 ODR 约束。

### new 与 auto(x)（¶6–¶7）

¶6 `new auto(1)` 分配一个 `int`。¶7 `auto` 可以用作函数式类型转换的类型，即 `auto(x)` 和 `auto{x}`（C++23，[[P0849R8]]）。

```cpp run ok
#include <vector>
#include <type_traits>
int main() {
    int* p = new auto(42);
    std::vector<int> v{3, 1, 3, 2};
    // front() 返回引用，删除过程中它所指的元素会被覆盖，所以先复制一份
    std::erase(v, auto(v.front()));
    const int ci = 0;
    static_assert(std::is_same_v<decltype(auto(ci)), int>);
    int r = int(v.size()) - 2 + (*p - 42);   // v == {1, 2}
    delete p;
    return r;
}
```

`auto(x)` 的语义是**衰变复制**（decay-copy）：结果是一个 prvalue，类型是 `x` 的类型经过数组和函数到指针的转换、去掉引用和顶层 cv 之后的类型。在泛型代码里，这个类型（`std::decay_t<decltype(x)>`）写出来往往很长，以前只能先写 `auto tmp = x;`。

## 函数的返回类型推导

¶4 除了转换函数，函数声明的返回类型里都可以出现占位符（`operator auto()` 由 [[class.conv.fct]] 另行规定）。返回类型从函数体中**非弃置**的 return 语句推导，也就是不算 `if constexpr` 中被丢弃分支里的 return（[[stmt.if]]）：

```cpp run ok
#include <type_traits>
template<class T>
auto unwrap(T t) {
    if constexpr (std::is_pointer_v<T>) return *t;   // T = int* 时只有这一条有效
    else return t;
}
int main() { int v = 3; return unwrap(&v) + unwrap(4) - 7; }
```

¶3 如果函数用了尾置返回类型，前面的 `auto` 只是语法上的占位，返回类型是 `->` 后面的类型；那里也可以再写占位符，例如 `auto g() -> auto&`。

### 多条 return 与没有 return（¶10–¶11）

¶10 每条非弃置的 return 单独推导，结果必须完全相同，不会去求公共类型。¶11 没有 return 时，当作函数体末尾有一条无操作数的 return，推导为 `void`。

<div class="compare" markdown="1">

```cpp error
auto f(bool b) {
    if (b) return 1;
    return 2.0;  // error: 前面是 int
}
```

```cpp error
auto  f() { }  // OK: void
auto* g() { }  // error: 无法从
               // void() 推导 auto*
```

</div>

Clang 对左边的诊断是 "'auto' in return type deduced as 'double' here but deduced as 'int' in earlier return statement"。

### 推导之前不能使用（¶13）

¶13 表达式指名一个类型还没推导出来的变量或函数，程序非良构。但函数里一旦出现过一条非弃置的 return，推导出的类型就可以在函数的其余部分使用。所以只要第一条 return 不递归，函数就可以递归：

<div class="compare" markdown="1">

```cpp run ok
auto sum(int i) {
    if (i == 1)
        return i;  // 推导出 int
    else
        return sum(i - 1) + i;
}
int main() { return sum(4) - 10; }
```

```cpp error
auto fact(int n) {
    // error: 第一条 return
    // 就用到了 fact 的类型
    return n <= 1 ? 1
         : n * fact(n - 1);
}
```

</div>

```cpp error
auto n = n;          // error: 初始化器引用了 n 自己
auto f();
void g() { &f; }     // error: f 还没有定义，返回类型未知
```

### 模板里的推导时机（¶15）

¶15 模板化函数的返回类型推导在定义被实例化时进行，即使 return 的操作数不依赖模板参数也是如此。注 3 指出，所以对这个特化的任何使用，哪怕只是放进 `decltype`，都会引起隐式实例化；实例化中出现的错误不在函数类型的**直接语境**（immediate context，[[temp.deduct]]）里，会让程序非良构，而不是让推导失败。

```cpp run ok
template<class T> auto f(T t) { return t; }
typedef decltype(f(1)) fint_t;          // 实例化 f<int> 以得到返回类型
template<class T> auto f(T* t) { return *t; }
void g() { int (*p)(int*) = &f; (void)p; }   // 两个 f 都要实例化，选中第二个
int main() {}
```

!!! warning "返回类型推导不适合做 SFINAE 检测"
    `template<class T> auto size_of(T t) { return t.size(); }` 对没有 `size()` 的类型，错误出现在函数体的实例化中，是硬错误。需要 SFINAE 时，用尾置返回类型 `-> decltype(t.size())` 或 `requires` 约束。

¶19 显式实例化声明（`extern template`）不会实例化用占位类型声明的实体，但也不阻止为了确定类型而进行的实例化：

```cpp run ok
template<class T> auto f(T t) { return t; }
extern template auto f(int);   // 不实例化 f<int>
int (*p)(int) = f;             // 为确定返回类型而实例化 f<int>
template auto f(int);          // 程序中某处仍要有显式实例化定义
int main() { return p(0); }
```

### 重声明必须用同一个占位符（¶16）

¶16 函数或函数模板 F 的声明返回类型用了占位符，F 的重声明和特化也必须用同一个占位符，不能写推导出的类型；反过来，原声明没用占位符，重声明也不能用。

```cpp error
auto f();
auto f() { return 42; }   // 返回 int
auto f();                 // OK
int f();                  // error: auto 与 int 不匹配
decltype(auto) f();       // error: auto 与 decltype(auto) 不匹配
```

这样，编译器只看声明就知道返回类型需要推导。对函数模板，这条规则决定了哪些显式实例化能匹配哪个模板。标准例 7 的模板部分：

```cpp
template<typename T> auto g(T t) { return t; }  // #1
template auto g(int);                           // OK: 返回 int
template char g(char);                          // error: 没有匹配的模板
template<> auto g(double);                      // OK: 前向声明一个显式特化

template<class T> T g(T t) { return t; }        // OK: 与 #1 不等价，是另一个模板
template char g(char);                          // OK: 匹配这个模板
template auto g(float);                         // 仍然匹配 #1
void h() { return g(42); }                      // error: 有歧义
```

这条限制只针对函数。例 7 的末尾说明变量可以用 `auto` 重声明：`extern int v; auto v = 17;` 合法，`auto S::i = 23;` 也可以定义静态数据成员。

### 其他限制（¶12、¶14、¶17、¶18）

¶17 返回类型使用占位符的函数不能是虚函数，¶18 也不能是协程。

```cpp error
struct S { virtual auto f() { return 1; } };   // error: 不能是虚函数
```

虚函数的覆盖要检查返回类型是否相同或协变（[[class.virtual]]），这需要在类定义时就知道返回类型，而推导要等到函数定义，定义可能在类外甚至另一个翻译单元里。协程的返回类型决定了它的承诺类型（`std::coroutine_traits<R, Args...>`），而推导返回类型又要先分析 `co_return`，形成循环。

¶12 一个导出的、返回类型使用占位符的函数，必须在含有其导出声明的翻译单元中定义（私有模块片段之外），因为导入者需要看到函数体才能知道返回类型。注 2 指出，推导出的返回类型不能是具有内部链接的名字（[[basic.link]]）。

¶14 {{c++26}} 后置条件中的结果绑定（`post(r : …)` 中的 `r`，[[dcl.contract.res]]）从不具有未推导的占位类型，所以返回类型为 `auto` 的函数也可以在后置条件里使用 `r`：

```cpp
auto f()
    post(r : r == 7)   // OK: r 的类型是推导出的 int
{
    return 7;
}
```

截至写作时本机 Clang 23 不支持契约语法，这个例子没有经过编译验证。

## 实现视角

!!! impl "名字修饰与编译开销"
    - 简写函数模板和等价的普通函数模板修饰后的名字相同：`void h(auto)` 和 `template<class T> void k(T)` 的特化在 Itanium ABI 下都编码为 `...IiEvT_`。
    - 使用返回类型推导的函数模板，名字中编码的是占位符本身（`auto` 为 `Da`，`decltype(auto)` 为 `Dc`），不是推导出的类型。本机 Clang 23 把 `template<class T> auto f(T)` 的 `f<int>` 修饰为 `_Z1fIiEDaT_`。这和 ¶16 要求重声明使用同一个占位符是一致的。
    - 返回类型推导要求函数体在每个使用点可见，通常要放进头文件；任何取 `decltype` 的使用都会触发实例化（¶15）。大量使用 `auto` 返回类型会增加编译时间。

## 历史与演进

!!! history
    | 标准 | 变化 |
    |---|---|
    | C++11 | `auto` 变量（关键字改作新用途）；尾置返回类型 |
    | C++14 | 普通函数的返回类型推导和 `decltype(auto)`（[[N3638]]）；泛型 lambda；`auto x{1}` 改为 `int`（[[N3922]]） |
    | C++17 | `template<auto N>`；结构化绑定；CTAD |
    | C++20 | 简写函数模板、受约束的占位符 `Concept auto`（[[P1141]]） |
    | C++23 | `auto(x)`、`auto{x}`（[[P0849R8]]）；隐式移动简化（[[P2266]]），影响 `decltype(auto)` 的推导 |
    | C++26 | 契约中的结果绑定（¶14） |

## 常见误解

!!! pitfall "`auto x = expr;` 保留引用和 const"
    不保留。按值推导会去掉引用和顶层 cv。需要保留时，用 `auto&`、`const auto&`、`auto&&` 或 `decltype(auto)`。

!!! pitfall "多条 return 会推导出公共类型"
    不会，它们必须完全相同。求公共类型的是条件运算符 `?:`。

!!! pitfall "`decltype(auto)` 是更好的 `auto`"
    它会保留引用，返回局部变量时加了括号就会返回悬垂引用。只在需要原样转发返回值的引用性时使用它。

## 思考题

!!! question "思考题 1"
    下面每个变量是什么类型？

    ```cpp
    const char* const p = "hi";
    auto a = p;
    auto b = "hi";
    auto& c = "hi";
    auto d = { p };
    auto e { p };
    ```

<details markdown="1">
<summary>答案</summary>

- `a`：`const char*`。按值推导去掉顶层 const（指针本身的 const），保留底层 const。
- `b`：`const char*`。字符串字面量是 `const char[3]` 左值，按值推导时数组退化为指针。
- `c`：`auto` 推导为 `const char[3]`，`c` 是 `const char(&)[3]`，引用不退化。
- `d`：`std::initializer_list<const char*>`，需要包含 `<initializer_list>`。
- `e`：`const char*`，直接列表初始化取出唯一的元素。
</details>

!!! question "思考题 2"
    为什么 `std::vector<bool> v{true}; auto x = v[0]; v[0] = false;` 之后 `x` 也变成了 `false`？用 `auto(v[0])` 能修复吗？

<details markdown="1">
<summary>答案</summary>

`vector<bool>::operator[]` 返回代理对象 `std::vector<bool>::reference`（一个 prvalue），`auto` 推导出的就是这个代理类型。代理对象引用着 `v` 里的那一位，所以 `x` 随 `v[0]` 变化。

`auto(v[0])` 也不能修复，衰变复制只复制代理对象本身，类型仍然是 `reference`。要写出目标类型：`bool x = v[0];` 或 `auto x = static_cast<bool>(v[0]);`。`auto` 推导的是表达式的类型，代理类型会原样保留下来。
</details>
