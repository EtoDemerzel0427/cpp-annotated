---
title: 类型推导全景
summary: C++ 中让编译器推出类型的七种场合（模板实参推导、auto、decltype、decltype(auto)、CTAD、结构化绑定、初始化捕获）其实只靠两套规则；本页把它们放在一起对照。
status: done
since: c++11
order: 52
papers: N3922, N4164, N3638, N3648, P0091R3, P0217R3, P2266R3, P0887R1, P1141R2, P0780R2
related: temp.deduct, temp.deduct.call, temp.deduct.type, dcl.spec.auto, dcl.type.decltype, dcl.type.class.deduct, over.match.class.deduct, dcl.struct.bind, expr.prim.lambda, dcl.ref, topics/value-categories
tags: 类型推导, auto, decltype, CTAD, 转发引用, 模板
updated: 2026-10-19
---

!!! tldr
    - 类型推导只有两套规则：模板实参推导（`auto`、CTAD、泛型 lambda、初始化捕获都用它），以及 `decltype` 规则（`decltype(auto)` 用它）。
    - 按值推导丢掉引用和顶层 const，数组和函数退化成指针；按引用推导什么都不丢。
    - `auto` 与模板推导只差一处：`auto x = {1, 2};` 推导出 `std::initializer_list<int>`。
    - `decltype(x)` 看 `x` 的声明，`decltype((x))` 看表达式的值类别；`decltype(auto)` 在 `return (x);` 里因此可能返回悬垂引用。
    - 转发引用 `T&&` 把实参的值类别编进 `T`，引用折叠和 `std::forward<T>` 再把它还原出来。

## 同一个初始化器，不同的结果

```cpp run ok
const int ci = 0;
auto           a = ci;     // int
auto&          b = ci;     // const int&
decltype(ci)   c = ci;     // const int
decltype((ci)) d = ci;     // const int&
int main() { (void)a; (void)b; (void)c; (void)d; }
```

四个声明的初始化器都是 `ci`，得到的类型却各不相同。原因是这里用了两套规则：

1. **模板实参推导**（[[temp.deduct.call]]）：对 `template<class T> void f(P); f(expr);`，比较形参类型 `P` 和实参类型 `A`，求出 `T`。`auto` 声明、类模板实参推导（CTAD）、泛型 lambda、简写函数模板都复用这套规则。
2. **`decltype` 规则**（[[dcl.type.decltype]]）：由表达式的形式（是不是没加括号的名字）和值类别决定类型。`decltype(auto)` 复用这套规则。

结构化绑定和 lambda 的初始化捕获先用 `auto` 推导一个隐藏变量，再在它上面引入名字，所以各自又有一点特殊之处。

| 机制 | 用哪套规则 | 标准位置 | 引入 |
|---|---|---|---|
| 函数模板实参推导 | 模板推导 | [[temp.deduct]] | C++98 |
| `auto` 变量、`auto` 返回类型 | 模板推导，加 `initializer_list` 特例 | [[dcl.type.auto.deduct]] | C++11 / C++14 |
| `decltype(e)` | decltype 规则 | [[dcl.type.decltype]] | C++11 |
| `decltype(auto)` | decltype 规则 | [[dcl.type.auto.deduct#4]] | C++14（[[N3638]]） |
| CTAD：`std::vector v{1, 2};` | 对虚构的函数模板做模板推导 | [[over.match.class.deduct]] | C++17（[[P0091R3]]） |
| 结构化绑定 `auto [a, b] = e;` | `auto`，再加特殊的 `decltype` | [[dcl.struct.bind]] | C++17（[[P0217R3]]） |
| 初始化捕获 `[x = e]` | `auto` | [[expr.prim.lambda.capture#6]] | C++14（[[N3648]]） |
| 泛型 lambda、简写函数模板 `void f(auto x)` | 模板推导 | [[dcl.fct]] | C++14 / C++20（[[P1141R2]]） |

## 模板实参推导

对 `template<class T> void f(P); f(expr);`，记 `expr` 的类型为 `A`。比较之前，`P` 和 `A` 先按 `P` 的形式做调整（[[temp.deduct.call#2]]、[[temp.deduct.call#3]]）：

- `P` 不是引用（按值传）：`A` 是数组就换成指针，是函数就换成函数指针，顶层 cv 去掉。
- `P` 是引用：用被引用的类型去比较，`A` 不退化，cv 保留。
- `P` 是转发引用 `T&&`（见下文）且实参是左值：把 `A` 换成 `A&`。

<div class="compare" markdown="1">

```cpp
template<class T> void byval(T);
const int ci = 0;
int arr[3];
byval(ci);   // T = int
byval(arr);  // T = int*
```

```cpp
template<class T> void byref(T&);
const int ci = 0;
int arr[3];
byref(ci);   // T = const int
byref(arr);  // T = int[3]
```

</div>

推导只求精确匹配，不考虑隐式转换。[[temp.deduct.call#4]] 只容忍三种差异：引用形参时推出的类型可以多一些 cv；指针之间的限定转换和函数指针转换；实参类型是推出的类模板特化的派生类。所以 `std::max(1, 2.0)` 推导失败：两个实参分别推出 `T = int` 和 `T = double`，不同的推导结果使推导失败（[[temp.deduct.type#2]]），不会把 `1` 转成 `double`。

需要转换时，可以显式写出模板实参 `std::max<double>(1, 2.0)`，或者用 `std::type_identity_t<T>`（C++20，[[P0887R1]]）把某个形参放进非推导语境，让它只参与转换、不参与推导。

## auto：模板推导，加一个花括号特例

[[dcl.type.auto.deduct#3]] 规定，`auto` 的推导就是把 `auto` 换成一个虚构的模板形参 `U`，把初始化器当作实参，按 [[temp.deduct.call]] 推导。`const auto& x = e;` 推出的类型，与 `template<class U> void f(const U&); f(e);` 中的 `U` 相同。

唯一的例外是**拷贝列表初始化**（`= {...}` 形式）：这时把 `auto` 换成 `std::initializer_list<U>` 再推导。

```cpp
auto x1 = { 1, 2 };   // std::initializer_list<int>
auto x2 = { 1, 2.0 }; // error: 无法推导元素类型
auto x3{ 1, 2 };      // error: 直接列表初始化只能有一个元素
auto x4 = { 3 };      // std::initializer_list<int>
auto x5{ 3 };         // int

template<class T> void g(T);
g({1, 2, 3});         // error: 花括号列表使 T 处于非推导语境
```

函数模板对花括号实参的处理见 [[temp.deduct.call#1]]：只有形参形如 `std::initializer_list<T>` 或 `T[N]` 时才能从花括号列表推导，否则这个形参不参与推导。

返回类型里的 `auto` 没有这个特例：`return {1, 2};` 直接非良构（[[dcl.type.auto.deduct#2]] ¶2.1.2）。

!!! history "auto x{1} 的含义变化"
    C++11/14 中 `auto x{3};` 推导为 `std::initializer_list<int>`，与大多数人的直觉不符。[[N3922]] 把它改为 `int`，同时规定直接列表初始化只能有一个元素。这是 C++17 的修改，主流编译器在 C++11/14 模式下也按缺陷修正采用新规则。

## decltype：名字与表达式

[[dcl.type.decltype#1]] 把 `decltype(e)` 分成两种情形：

1. `e` 是没加括号的名字（*id-expression*）或没加括号的类成员访问：结果是这个名字所指实体的**声明类型**。结构化绑定和常量模板形参各有专门规定，见下文。
2. 其他表达式：按 `e` 的[[topics/value-categories|值类别]]加引用。亡值得到 `T&&`，左值得到 `T&`，纯右值得到 `T`。

所以 `decltype(x)` 问的是 `x` 声明成了什么，`decltype((x))` 问的是表达式 `(x)` 是什么值类别。具名变量是左值，`decltype((x))` 总是左值引用。

## 一张对照表

设有下面这些声明：

```cpp
int i = 0;  const int ci = 0;  int& ri = i;  const int& cri = ci;
int&& f();  int arr[3];  void fn(int);
```

| 输入 `e` | `g(T)` 的 `T` | `g(T&)` 的 `T` | `g(T&&)` 的 `T` | `auto x = e;` | `auto& x = e;` | `decltype(e)` | `decltype(auto) x = e;` |
|---|---|---|---|---|---|---|---|
| `i` | `int` | `int` | `int&` | `int` | `int&` | `int` | `int` |
| `(i)` | `int` | `int` | `int&` | `int` | `int&` | `int&` | `int&` |
| `ci` | `int` | `const int` | `const int&` | `int` | `const int&` | `const int` | `const int` |
| `ri` | `int` | `int` | `int&` | `int` | `int&` | `int&` | `int&` |
| `cri` | `int` | `const int` | `const int&` | `int` | `const int&` | `const int&` | `const int&` |
| `42` | `int` | ✗ | `int` | `int` | ✗ | `int` | `int` |
| `f()`（亡值） | `int` | ✗ | `int` | `int` | ✗ | `int&&` | `int&&` |
| `std::move(i)` | `int` | ✗ | `int` | `int` | ✗ | `int&&` | `int&&` |
| `arr` | `int*` | `int[3]` | `int(&)[3]` | `int*` | `int(&)[3]` | `int[3]` | `int[3]`¹ |
| `fn` | `void(*)(int)` | `void(int)` | `void(&)(int)` | `void(*)(int)` | `void(&)(int)` | `void(int)` | ✗² |
| `"hi"` | `const char*` | `const char[3]` | `const char(&)[3]` | `const char*` | `const char(&)[3]` | `const char(&)[3]` | `const char(&)[3]` |
| `{1, 2}` | ✗ | ✗ | ✗ | `initializer_list<int>` | ✗ | ✗（不是表达式） | ✗ |

✗ 表示推导失败或非良构。¹ 推导结果是 `int[3]`，但数组不能用另一个数组初始化，所以这个声明非良构。² 推导结果是函数类型 `void(int)`，不能声明这种类型的变量。

从表中可以读出几条规律：

- `auto` 列与 `g(T)` 列完全相同，只有花括号一行例外。`auto&` 对应 `g(T&)`，`auto&&` 对应 `g(T&&)`。
- 按值推导把 `ci`、`ri`、`cri` 都变成 `int`。
- `decltype` 什么都不丢，但对名字和表达式分别处理，所以 `i` 和 `(i)` 两行不同。
- 字符串字面量是左值，`decltype("hi")` 是 `const char(&)[3]`。

下面的代码用 `static_assert` 核对了表中的大部分格子，本机 Clang 23 编译通过：

```cpp run ok title="deduction_table.cpp"
#include <type_traits>
#include <initializer_list>
#include <utility>
template<class T, class U> constexpr bool same = std::is_same_v<T, U>;

int i = 0; const int ci = 0; int& ri = i; const int& cri = ci; int&& f(); int arr[3];
void fn(int);

template<class Expect, class T> void byval(T)  { static_assert(same<T, Expect>); }
template<class Expect, class T> void byref(T&) { static_assert(same<T, Expect>); }
template<class Expect, class T> void fwd(T&&)  { static_assert(same<T, Expect>); }

auto  a1 = ci;     static_assert(same<decltype(a1), int>);
auto& a2 = ci;     static_assert(same<decltype(a2), const int&>);
auto&& a3 = i;     static_assert(same<decltype(a3), int&>);
auto&& a4 = 0;     static_assert(same<decltype(a4), int&&>);
auto  a5 = arr;    static_assert(same<decltype(a5), int*>);
auto& a6 = arr;    static_assert(same<decltype(a6), int(&)[3]>);
auto  a7 = fn;     static_assert(same<decltype(a7), void(*)(int)>);
auto  a8 = {1, 2}; static_assert(same<decltype(a8), std::initializer_list<int>>);
auto  a9{1};       static_assert(same<decltype(a9), int>);
auto  a10 = {1};   static_assert(same<decltype(a10), std::initializer_list<int>>);

static_assert(same<decltype(i), int> && same<decltype((i)), int&>);
static_assert(same<decltype(f()), int&&> && same<decltype(ci), const int>);
static_assert(same<decltype("hi"), const char(&)[3]>);

decltype(auto) d1 = ci;  static_assert(same<decltype(d1), const int>);
decltype(auto) d2 = (i); static_assert(same<decltype(d2), int&>);
decltype(auto) d3 = f(); static_assert(same<decltype(d3), int&&>);

int main() {
    byval<int*>(arr);   byref<int[3]>(arr);          fwd<int(&)[3]>(arr);
    byval<int>(ci);     byref<const int>(ci);        fwd<const int&>(ci);
    byval<const char*>("hi"); byref<const char[3]>("hi"); fwd<const char(&)[3]>("hi");
    byval<void(*)(int)>(fn);  byref<void(int)>(fn);       fwd<void(&)(int)>(fn);
    fwd<int>(42);       fwd<int>(std::move(i));
}
```

## 转发引用与引用折叠

**转发引用**（[[g:forwarding-reference|forwarding reference]]）是对 cv 未限定的模板形参 `T` 写的 `T&&`，`auto&&` 也是（[[temp.deduct.call#3]]）。实参是左值时，`T` 推导为左值引用类型；实参是右值时，`T` 推导为非引用类型。这个名字来自 [[N4164]]，此前也常被叫作 universal reference。

```cpp
template<class T> void f(T&& x);
int i = 0;
f(i);   // T = int&，形参类型 int& && 折叠为 int&
f(0);   // T = int， 形参类型 int&&
```

把 `T = int&` 代回 `T&&`，得到 `int& &&`。程序里不能直接写引用的引用，但通过模板形参或类型别名形成时，按**引用折叠**处理（[[dcl.ref#7]]）：只要有一个是左值引用，结果就是左值引用。

| `T` | `T&` | `T&&` |
|---|---|---|
| `int` | `int&` | `int&&` |
| `int&` | `int&` | `int&` |
| `int&&` | `int&` | `int&&` |

这样，实参是左值还是右值，就记录在了 `T` 里。

### std::forward 怎样还原值类别

```cpp
template<class T>
constexpr T&& forward(std::remove_reference_t<T>& t) noexcept {
    return static_cast<T&&>(t);
}
```

在函数体里，具名形参 `x` 无论声明成什么都是左值。`std::forward<T>(x)` 借助外层推导出的 `T` 恢复调用者传进来的值类别：

- `T = int&`（原实参是左值）：返回类型 `int& &&` 折叠为 `int&`，结果是左值。
- `T = int`（原实参是右值）：返回类型 `int&&`，结果是亡值。

形参写成 `std::remove_reference_t<T>&`，`T` 出现在 `::` 之前的限定部分，是非推导语境（[[temp.deduct.type#5]]）。所以调用时必须显式写出 `T`。`std::move` 不需要外层的信息，它无条件转成 `std::remove_reference_t<T>&&`，结果总是亡值。

### 不是转发引用的 `&&`

| 写法 | 原因 |
|---|---|
| `template<class T> void f(const T&&)` | 带了 cv |
| `template<class T> void f(std::vector<T>&&)` | 不是对模板形参本身的引用 |
| `template<class T> struct S { void f(T&&); };` | 调用 `f` 时 `T` 已经确定，不推导 |
| CTAD 中构造函数的 `T&&`（`T` 是类模板形参） | 定义中明确排除（[[temp.deduct.call#3]] 例 4） |

## decltype(auto)：原样转发返回值

`decltype(auto)` 把初始化器（或 `return` 的操作数）当作 `decltype` 的操作数来求类型（[[dcl.type.auto.deduct#4]]）。它的主要用途是转发函数的返回值，被转发的函数返回引用，转发者也返回引用：

```cpp
template<class F, class... Args>
decltype(auto) call(F&& f, Args&&... args) {
    return std::forward<F>(f)(std::forward<Args>(args)...);
}
```

如果用 `auto` 作返回类型，一个返回 `int&` 的函数经过 `call` 就会变成返回 `int` 的副本。

### 给返回的名字加括号

```cpp
int g = 0;
auto           r1() { return (g); }   // int
decltype(auto) r2() { return (g); }   // int&：(g) 是左值表达式
decltype(auto) r3() { return g; }     // int：没加括号的名字，取声明类型
```

返回的是局部变量时，加括号会产生悬垂引用：

```cpp
decltype(auto) bad() {
    int x = 0;
    return (x);     // C++20：int&；C++23 起：int&&。都悬垂
}
```

C++23 的 [[P2266R3]] 规定，`return` 的操作数如果是指名一个可隐式移动的实体（例如局部变量）的名字，加不加括号都一样，它是亡值。所以这里的 `(x)` 是亡值，推出 `int&&`。本机 Clang 23 对这一行给出 `-Wreturn-stack-address` 警告。

[[dcl.type.auto.deduct#4]] 的例 3 正好展示了这一点：

```cpp
auto f1(int x) -> decltype((x)) { return (x); }   // 返回类型是 int&
auto f2(int x) -> decltype(auto) { return (x); }  // 返回类型是 int&&
```

!!! lawyer "f1 的函数体非良构"
    例子只断言了 `f1` 的返回类型。尾置返回类型不在 `return` 语句里，`decltype((x))` 仍是 `int&`；而函数体里的 `(x)` 按 P2266 是亡值，不能绑定到 `int&`。本机 Clang 23 在 `-std=c++2c` 下对 `f1` 报错 "non-const lvalue reference to type 'int' cannot bind to a temporary of type 'int'"，`-std=c++20` 下只给悬垂警告。`f2` 能编译，但返回了对形参的悬垂引用。

## CTAD：对虚构的函数模板做推导

写 `std::pair p(1, "x");` 时，编译器为 `pair` 的每个构造函数和每条推导指引生成一个虚构的函数模板，它的模板形参是类模板形参加上构造函数模板自己的形参。然后对初始化器做一次普通的重载决议（[[over.match.class.deduct]]）。因此 CTAD 的结果遵循模板推导的规则：

```cpp
std::vector v{1, 2};             // vector<int>：initializer_list 构造函数
std::pair   pr(1, "x");          // pair<int, const char*>：推导指引按值接受，数组退化
std::tuple  tp{ci, ri};          // tuple<int, int>：按值推导，丢掉 const 和引用
std::array  ar{1, 2, 3};         // array<int, 3>：推导指引
template<class T> struct Agg { T x, y; };
Agg ag{1, 2};                    // Agg<int>：C++20 聚合推导
```

最容易出乎意料的是花括号里只有一个同类对象的情形：

```cpp
std::vector v2{v};       // vector<int>，不是 vector<vector<int>>
std::vector v4{v, v};    // vector<vector<int>>
```

除了构造函数和推导指引，CTAD 还有一个**拷贝推导候选**（copy deduction candidate），相当于 `template<class T> vector(vector<T>) -> vector<T>`。[[over.match.class.deduct#6]] ¶6.1 规定，花括号里只有一个表达式、类型是这个类模板的特化（或其派生类）时，跳过优先考虑 `initializer_list` 构造函数的那一轮，于是拷贝推导候选胜出。是否多包一层取决于元素个数，所以在泛型代码里写 `std::vector{x}` 很危险，应该写 `std::vector<T>{x}`。

## 结构化绑定：名字不是变量

`auto [a, b] = e;` 先声明一个隐藏变量，相当于 `auto e' = e;`（`&`、`&&`、cv 都加在它身上），再让 `a`、`b` 指称 `e'` 的元素（[[dcl.struct.bind]]）。对类类型，`a`、`b` 不是独立的变量，只是指称成员的名字：

```cpp
struct P { int a; const double b; };
P p{1, 2.0};
auto  [sa, sb] = p;       // e' 是 P 的副本
auto& [ra, rb] = p;       // e' 是 P&

decltype(sa)    // int：成员的声明类型
decltype(sb)    // const double
decltype(ra)    // int，不是 int&
decltype((sa))  // int&：表达式是左值
```

[[dcl.type.decltype#1]] ¶1.1 规定，对没加括号的结构化绑定名字，`decltype` 给出结构化绑定声明中定义的**被引用类型**（referenced type）。所以即使 `ra` 实际上指称 `p.a`，`decltype(ra)` 也不带引用。

`auto` 和 cv 修饰的是隐藏变量，不是 `a`、`b` 本身。`const auto& [x, y] = p;` 中 `e'` 是 `const P&`，`decltype(x)` 因此是 `const int`。

## 初始化捕获：就是 auto

[[expr.prim.lambda.capture#6]] 规定，不带省略号的初始化捕获如同声明并显式捕获了一个 `auto init-capture;` 形式的变量。所以 `[x = e]` 中 `x` 的类型按 `auto x = e;` 推导，丢掉引用和顶层 const：

```cpp
const int ci = 0;
auto L1 = [x = ci] { /* decltype(x) 是 int；decltype((x)) 是 const int&，因为 operator() 是 const */ };
auto L2 = [&r = ci] { /* decltype(r) 是 const int& */ };
auto L3 = [x = ci] mutable { /* decltype((x)) 是 int& */ };
```

普通的按值捕获 `[ci]` 不经过 `auto`，闭包成员的类型就是 `ci` 的类型 `const int`，在 `mutable` lambda 里也不能修改。C++20 起还可以写包形式的初始化捕获 `[...xs = std::move(args)]`（[[P0780R2]]）。

## 其他复用模板推导的地方

- **泛型 lambda**：`[](auto x, auto&& y) {}` 的调用运算符是函数模板，每个 `auto` 形参对应一个虚构的模板形参（[[expr.prim.lambda]]）。
- **简写函数模板**（C++20，[[P1141R2]]）：`void f(auto x);` 等价于 `template<class T> void f(T x);`。`void f(const auto& x)`、`void f(std::integral auto x)` 同理。
- **`auto` 常量模板形参**：`template<auto N> struct S;` 中 `N` 的类型从模板实参推导（[[dcl.type.auto.deduct#2]] ¶2.4）。写成 `template<decltype(auto) N>` 可以推导出引用类型。

## 常见意外

| 现象 | 原因 | 出处 |
|---|---|---|
| `auto x = vec_bool[0];` 得到代理对象，不是 `bool` | `auto` 推出的是表达式的真实类型 `vector<bool>::reference` | [[vector.bool]] |
| `auto s = "hi";` 是 `const char*` | 按值推导，数组退化 | [[temp.deduct.call#2]] |
| `std::max(1, 2.0)` 编译失败 | 两个实参推出不同的 `T`，推导不做转换 | [[temp.deduct.type#2]] |
| `template<class T> void f(std::vector<T>); f({1, 2});` 失败 | 花括号列表只能推导 `initializer_list<T>` 和 `T[N]` 形参 | [[temp.deduct.call#1]] |
| `const auto& [x, y] = f();` 中 `decltype(x)` 不是引用 | 结构化绑定的 `decltype` 给出被引用类型 | [[dcl.type.decltype#1]] |
| `std::vector{v}` 不是 vector 的 vector | 单个同类元素时跳过 `initializer_list` 构造函数 | [[over.match.class.deduct#6]] |
| `decltype(auto) f() { return (x); }` 返回引用 | 加括号的名字按表达式处理 | [[dcl.type.decltype#1]] |
| 带转发引用的构造函数抢走了拷贝构造 | 对非 const 左值，`T&&` 推出的 `Person&` 比 `const Person&` 更匹配 | [[over.match.best]] |
| `template<class T> void f(T&&, T&&); f(i, 0);` 失败 | 左值推出 `int&`，右值推出 `int`，两者冲突 | [[temp.deduct.call#3]] |
| `template<class C> void f(typename C::iterator);` 无法推导 `C` | `::` 之前的部分是非推导语境 | [[temp.deduct.type#5]] |

## 思考题

!!! question "思考题 1"
    ```cpp
    const int arr[2] = {1, 2};
    auto a = arr;
    auto& b = arr;
    decltype(auto) c = (arr[0]);
    auto [x, y] = arr;
    ```
    `decltype(a)`、`decltype(b)`、`decltype(c)`、`decltype(x)` 分别是什么？

<details markdown="1">
<summary>答案</summary>

- `a`：按值推导，数组退化为指针，指向的 const 保留，得到 `const int*`。
- `b`：按引用推导，不退化，`auto` 推出 `const int[2]`，`b` 是 `const int(&)[2]`。
- `c`：`(arr[0])` 是 `const int` 类型的左值，得到 `const int&`。
- `x`：初始化器是数组时，[[dcl.struct.bind#1]] 规定隐藏变量的类型就是数组类型 `const int[2]`，逐元素复制，不退化。`decltype(x)` 是元素类型 `const int`。

以上结论都经本机 Clang 23 的 `static_assert` 核对。
</details>

!!! question "思考题 2"
    为什么 `std::forward` 要求显式写模板实参，而 `std::move` 不用？如果把 `forward` 的形参改成 `T&& t`，让它自己推导，会出什么问题？

<details markdown="1">
<summary>答案</summary>

`forward` 要恢复的是调用者那一层的值类别，这个信息只保存在外层函数模板推出的 `T` 中：左值时 `T = U&`，右值时 `T = U`。在函数体里，具名形参永远是左值，如果让 `forward` 从它推导，只能推出 `U&`，永远返回左值，`forward` 就没有作用了。所以 `forward` 把形参放进非推导语境，强制调用者传入外层的 `T`。`std::move` 不需要外层的信息，它总是转成亡值，可以自己推导。
</details>

!!! question "思考题 3"
    `auto x = expr;` 推出的类型与 `template<class T> void f(T); f(expr);` 推出的 `T` 何时不同？

<details markdown="1">
<summary>答案</summary>

只有 `expr` 是花括号列表时不同：`auto x = {1, 2};` 推出 `std::initializer_list<int>`，`f({1, 2})` 推导失败。`auto x{1};` 是直接列表初始化，只有一个元素，推出 `int`，与 `f(1)` 一致。其余情形 [[dcl.type.auto.deduct#3]] 直接沿用 [[temp.deduct.call]]，结果相同。返回类型中的 `auto` 连这个例外都没有，`return {1, 2};` 非良构。
</details>
