---
title: 类型推导全景
summary: 把 C++ 的七种类型推导放在一起对照：模板实参推导、auto、decltype、decltype(auto)、类模板实参推导（CTAD）、结构化绑定、lambda 初始化捕获。一张"输入 → 推导结果"的大表（引用、cv、数组、函数、花括号），转发引用与引用折叠，std::forward 的原理，以及常见意外。
status: done
since: c++11
order: 52
papers: N3922, N4164, N3638, N3648, P0091R3, P0217R3, P2266R3, P0887R1, P1141R2, P0780R2
related: temp.deduct, temp.deduct.call, temp.deduct.type, dcl.spec.auto, dcl.type.decltype, dcl.type.class.deduct, over.match.class.deduct, dcl.struct.bind, expr.prim.lambda, dcl.ref, topics/value-categories
tags: 类型推导, auto, decltype, CTAD, 转发引用, 模板
updated: 2026-10-18
---

C++ 里"让编译器替你写类型"的地方越来越多，但它们**不是同一套规则**。粗略地说只有两个"引擎"：

1. **模板实参推导**（[[temp.deduct.call]]）——`template<class T> void f(P)` 中从实参推 `T`。`auto`、CTAD、泛型 lambda、简写函数模板、`auto` 常量模板形参都**复用**这个引擎。
2. **`decltype` 规则**（[[dcl.type.decltype]]）——由表达式的**形式**（是不是未加括号的名字）和**值类别**决定类型。`decltype(auto)` 复用这个引擎。

结构化绑定和 lambda 初始化捕获则是"先用 `auto` 推导出一个隐藏变量，再在其上定义名字"，各自有些特殊的 `decltype` 行为。

| 机制 | 引擎 | 标准位置 | 引入 |
|---|---|---|---|
| 函数模板实参推导 | 模板推导 | [[temp.deduct]] | C++98 |
| `auto` 变量 / 返回类型 | 模板推导（+ `initializer_list` 特例） | [[dcl.type.auto.deduct]] | C++11 / C++14 |
| `decltype(e)` | decltype 规则 | [[dcl.type.decltype]] | C++11 |
| `decltype(auto)` | decltype 规则 | [[dcl.type.auto.deduct]] ¶4 | C++14（[[N3638]]） |
| CTAD：`std::vector v{1, 2};` | 模板推导（对虚构的函数模板） | [[over.match.class.deduct]] | C++17（[[P0091R3]]） |
| 结构化绑定 `auto [a, b] = e;` | `auto` + 特殊的 decltype | [[dcl.struct.bind]] | C++17（[[P0217R3]]） |
| 初始化捕获 `[x = e]` | `auto` | [[expr.prim.lambda.capture#6]] | C++14（[[N3648]]） |
| 泛型 lambda / 简写函数模板 `void f(auto x)` | 模板推导 | [[dcl.fct]] | C++14 / C++20（[[P1141R2]]） |

## 引擎一：模板实参推导

对 `template<class T> void f(P); f(expr);`，`P` 与 `A`（`expr` 的类型）在比较前做如下调整（详见 [[temp.deduct.call]]）：

- `P` **不是引用**（按值）：`A` 的数组退化为指针、函数退化为函数指针、顶层 cv 去掉；
- `P` **是引用**：用被引用的类型比较，`A` 什么都不退化，cv 保留；
- `P` 是**转发引用** `T&&` 且实参是**左值**：`A` 换成 `A&`。

此外，推导**不考虑隐式转换**——只容忍三种差异：引用时多一些 cv、限定转换、派生到基类（[[temp.deduct.call#4]]）。

## 引擎二：decltype

`decltype(e)`（[[dcl.type.decltype#1]]）：

1. `e` 是**未加括号**的 *id-expression* 或类成员访问 → 该名字所指实体的**声明类型**（结构化绑定、常量模板形参各有特殊规定）；
2. 否则，按 `e` 的值类别：亡值 → `T&&`；左值 → `T&`；纯右值 → `T`。

所以 `decltype(x)` 与 `decltype((x))` 可能不同：前者问"`x` 声明成什么"，后者问"表达式 `(x)` 是什么值类别"——具名变量是左值，得到 `T&`。见 [[topics/value-categories]]。

## 大表：同一个输入，七种推导

设有：

```cpp
int i = 0;  const int ci = 0;  int& ri = i;  const int& cri = ci;
int&& f();  int arr[3];  void fn(int);
```

| 输入 `e` | `template<class T> g(T)` 的 `T` | `g(T&)` 的 `T` | `g(T&&)` 的 `T` | `auto x = e;` | `auto& x = e;` | `decltype(e)` | `decltype(auto) x = e;` |
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
| `{1}` | ✗ | ✗ | ✗ | `initializer_list<int>`（`= {1}`）/ `int`（`x{1}`） | ✗ | ✗ | ✗ |

✗ = 推导失败或非良构。
¹ 语法上推导为 `int[3]`，但数组不能用另一个数组拷贝初始化，`decltype(auto) x = arr;` 非良构。
² 推导为函数类型 `void(int)`，不能声明该类型的变量。

（表中模板列与 `auto` 列都在 Clang 23 上用 `static_assert(std::is_same_v<...>)` 验证过。）

几条规律：

- **`auto` = 按值模板推导**：`auto` 列与 `g(T)` 列完全相同（只有花括号例外）。`auto&` 与 `g(T&)`、`auto&&` 与 `g(T&&)` 也一一对应。
- **按值推导丢掉引用和顶层 cv**：`ci`、`ri`、`cri` 全部变成 `int`。
- **`decltype` 不丢任何东西**，但对名字和表达式分别处理：`i` 与 `(i)` 结果不同。
- **字符串字面量是左值**：`decltype("hi")` 是 `const char(&)[3]`。

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

## auto 与模板推导的唯一区别：花括号

[[dcl.type.auto.deduct#3]]：`auto` 的推导就是把 `auto` 替换成虚构的模板形参 `U`，把初始化器当作实参，按 [[temp.deduct.call]] 推导。**例外**：若初始化是**拷贝列表初始化**（`= {...}`），把 `auto` 替换为 `std::initializer_list<U>`。

```cpp
auto x1 = { 1, 2 };   // std::initializer_list<int>
auto x2 = { 1, 2.0 }; // error: 无法推导元素类型
auto x3{ 1, 2 };      // error: 直接列表初始化只能有一个元素
auto x4 = { 3 };      // std::initializer_list<int>
auto x5{ 3 };         // int

template<class T> void g(T);
g({1, 2, 3});         // error: 模板推导中初始化列表是非推导语境
```

!!! history "auto x{1} 的含义变化"
    C++11/14 中 `auto x{3};` 推导为 `std::initializer_list<int>`，这个设计被广泛认为是错误。[[N3922]] 将其改为 `int`（直接列表初始化只允许单个元素），作为 C++17 的修改，主流编译器也将其作为缺陷修正应用到早期模式。

函数返回类型中的 `auto` **没有**这个特例：`auto f() { return {1, 2}; }` 非良构（[[dcl.type.auto.deduct#2]] ¶2.1.2）。

## 转发引用与引用折叠

[[g:forwarding-reference|转发引用]]（[[temp.deduct.call#3]]）：对 cv 未限定的模板形参 `T` 的 `T&&`（以及 `auto&&`）。实参是左值时 `T` 推导为**左值引用类型**，否则为非引用类型。

于是 `T&&` 代入后可能是 `int& &&`——语言里不能直接写"引用的引用"，但通过模板形参或 typedef 形成时，按**引用折叠**规则处理（[[dcl.ref#7]]）：

| `T` | `T&` | `T&&` |
|---|---|---|
| `int` | `int&` | `int&&` |
| `int&` | `int&` | `int&`（左值引用"传染"） |
| `int&&` | `int&` | `int&&` |

规则只有一句：**只要有一个是左值引用，结果就是左值引用**。

### std::forward 的原理

```cpp
template<class T>
constexpr T&& forward(std::remove_reference_t<T>& t) noexcept {
    return static_cast<T&&>(t);
}
```

- 形参 `std::remove_reference_t<T>&` 中 `T` 处在 *nested-name-specifier* 中——**非推导语境**（[[temp.deduct.type#5]]）。所以必须写 `std::forward<T>(x)`，不能让它自己推导（否则对具名变量 `x` 总会推出左值版本）。
- `T = int&`（原实参是左值）：返回 `int& &&` = `int&`，左值。
- `T = int`（原实参是右值）：返回 `int&&`，亡值。

`std::move` 则无条件 `static_cast<remove_reference_t<T>&&>`，总是亡值。

### 不是转发引用的 `&&`

| 写法 | 原因 |
|---|---|
| `template<class T> void f(const T&&)` | 有 cv |
| `template<class T> void f(std::vector<T>&&)` | 不是对模板形参本身的引用 |
| `template<class T> struct S { void f(T&&); };` | 调用 `f` 时不推导 `T` |
| CTAD 中构造函数的 `T&&`（`T` 是类模板形参） | 定义中明确排除（[[temp.deduct.call#3]] 例 4） |

## decltype(auto)：保留一切

[[dcl.type.auto.deduct#4]]：`decltype(auto)` 的推导结果是"把初始化器当作 `decltype` 的操作数"得到的类型。用途是**完美返回**——转发函数的返回值，保留引用性：

```cpp
template<class F, class... Args>
decltype(auto) call(F&& f, Args&&... args) {
    return std::forward<F>(f)(std::forward<Args>(args)...);   // 返回引用就返回引用
}
```

用 `auto` 作返回类型时，返回 `int&` 的函数会被"降级"成返回 `int` 的拷贝。

### 括号陷阱与隐式移动

```cpp
int g = 0;
auto           r1() { return (g); }   // int
decltype(auto) r2() { return (g); }   // int&：(g) 是左值表达式
decltype(auto) r3() { return g; }     // int：未加括号的名字，取声明类型
```

对**局部变量**更危险：

```cpp
decltype(auto) bad() {
    int x = 0;
    return (x);     // C++20：int&（悬垂引用）；C++23 起：int&&（仍然悬垂）
}
```

C++23 的 [[P2266R3]]（Simpler implicit move）规定：`return` 的操作数若是（可能加括号的）指名可隐式移动实体的 *id-expression*，它是**亡值**。于是 `decltype((x))` 在 `return` 语境下变成 `int&&`。标准 [[dcl.type.auto.deduct#4]] 例 3 正好记录了这一点：

```cpp
auto f1(int x) -> decltype((x)) { return (x); }   // 返回类型是 int&
auto f2(int x) -> decltype(auto) { return (x); }  // 返回类型是 int&&
```

!!! lawyer "f1 的函数体其实是非良构的"
    标准例子只断言了 `f1` 的**返回类型**是 `int&`。但按 P2266，`return (x);` 中 `(x)` 是亡值，不能绑定到 `int&`——Clang 23 对 `f1` 的 `return` 报 "non-const lvalue reference to type 'int' cannot bind to a temporary of type 'int'"。而 `f2` 能编译，但返回的是对形参的悬垂引用（Clang 会警告）。这两行很好地说明了：在 `return` 语句里给名字加括号，C++23 之后基本没有好事。

## CTAD：对虚构函数模板做推导

`std::pair p(1, "x");` 中，编译器把 `pair` 的每个构造函数（和每个推导指引）变成一个虚构的函数模板，模板形参 = 类模板形参 + 构造函数模板自己的形参，然后对初始化器做一次普通的重载决议（[[over.match.class.deduct]]）。所以 CTAD 的推导结果遵循**模板推导**规则：

```cpp
std::vector v{1, 2};             // vector<int>：initializer_list 构造函数
std::pair   pr(1, "x");          // pair<int, const char*>：pair 的推导指引按值接受，数组退化
std::tuple  tp{ci, ri};          // tuple<int, int>：按值推导，丢掉 const 和引用
std::array  ar{1, 2, 3};         // array<int, 3>：推导指引
template<class T> struct Agg { T x, y; };
Agg ag{1, 2};                    // Agg<int>：C++20 聚合推导
```

最容易出乎意料的是**拷贝推导候选**（copy deduction candidate）：

```cpp
std::vector v2{v};       // vector<int>，不是 vector<vector<int>>！
std::vector v4{v, v};    // vector<vector<int>>
```

单个元素 `{v}` 时，拷贝推导候选 `template<class T> vector(vector<T>) -> vector<T>` 与 `initializer_list<vector<int>>` 构造函数都可行；[[over.match.best]] 中有专门的决胜规则偏向拷贝推导候选（¶2.12）。于是"包一层"的语义取决于元素个数——泛型代码中写 `std::vector{x}` 很危险，应该写 `std::vector<T>{x}`。

## 结构化绑定：名字不是变量

`auto [a, b] = e;`（[[dcl.struct.bind]]）先按 `auto e' = e;`（带上 `&`/`&&`、cv）声明一个**隐藏变量** `e'`，然后让 `a`、`b` **指称** `e'` 的元素。`a`、`b` 不是独立的变量（对于类类型的情形），而是"名字"。所以：

```cpp
struct P { int a; const double b; };
P p{1, 2.0};
auto  [sa, sb] = p;       // e' 是 P 的拷贝
auto& [ra, rb] = p;       // e' 是 P&

decltype(sa)    // int           ——"被引用类型"：成员的声明类型
decltype(sb)    // const double
decltype(ra)    // int           ——不是 int&！
decltype((sa))  // int&          ——表达式是左值
```

[[dcl.type.decltype#1]] ¶1.1：对结构化绑定的未加括号的名字，`decltype` 给出结构化绑定声明中规定的**被引用类型**（referenced type）。即使 `ra` 实际上引用 `p.a`，`decltype(ra)` 也不带引用。`auto` 修饰的是隐藏的 `e'`，而不是 `a`、`b` 本身——`const auto& [x, y] = p;` 中 `x` 是 `const int`，因为 `e'` 是 `const P&`。

## lambda 初始化捕获：就是 auto

[[expr.prim.lambda.capture#6]]：不带省略号的初始化捕获"表现得像声明并显式捕获了一个形如 `auto init-capture;` 的变量"。所以 `[x = e]` 中 `x` 的类型按 `auto x = e;` 推导，按值，丢引用和顶层 const：

```cpp
const int ci = 0;
auto L1 = [x = ci] { /* decltype(x) 是 int；decltype((x)) 是 const int&（operator() 是 const） */ };
auto L2 = [&r = ci] { /* decltype(r) 是 const int& */ };
auto L3 = [x = ci] mutable { /* decltype((x)) 是 int& */ };
```

对比**普通按值捕获** `[ci]`：闭包成员的类型就是 `ci` 的类型 `const int`（不经过 `auto`），在 `mutable` lambda 里也不能修改。初始化捕获 `[ci = ci]` 则得到 `int`。C++20 起还可以有包形式的初始化捕获 `[...xs = std::move(args)]`（[[P0780R2]]）。

## 其他复用模板推导的地方

- **泛型 lambda**：`[](auto x, auto&& y) {}` 的调用运算符是函数模板，`auto` 形参就是发明的模板形参（[[expr.prim.lambda]]）。
- **简写函数模板**：`void f(auto x);` 等价于 `template<class T> void f(T x);`（C++20，[[P1141R2]]）。`void f(const auto& x)`、`void f(std::integral auto x)` 同理。
- **`auto` 常量模板形参**：`template<auto N> struct S;` 中 `N` 的类型按 `auto` 从模板实参推导（[[dcl.type.auto.deduct]] ¶2.4）。`template<decltype(auto) N>` 可以推导出引用类型。

## 常见意外一览

| 现象 | 原因 | 出处 |
|---|---|---|
| `auto x = vec_bool[0];` 得到代理对象，不是 `bool` | `auto` 推导的是表达式的真实类型 `vector<bool>::reference` | — |
| `auto s = "hi";` 是 `const char*` | 按值推导，数组退化 | [[temp.deduct.call#2]] |
| `std::max(1, 2.0)` 编译失败 | 两个实参推导出不同的 `T`；推导不做转换 | [[temp.deduct.type#2]] |
| `template<class T> void f(std::vector<T>); f({1,2});` 失败 | 初始化列表只对 `initializer_list<T>`、`T[N]` 可推导 | [[temp.deduct.call#1]] |
| `const auto& [x, y] = f();` 中 `decltype(x)` 不是引用 | 结构化绑定的 `decltype` 给出被引用类型 | [[dcl.type.decltype#1]] |
| `std::vector{v}` 不是"vector 的 vector" | CTAD 偏向拷贝推导候选 | [[over.match.class.deduct]] |
| `decltype(auto) f() { return (x); }` 返回引用 | 加括号的名字是左值表达式 | [[dcl.type.decltype#1]] |
| 转发构造函数劫持拷贝构造 | 对非 const 左值，`T&&` 推导出的 `Person&` 比 `const Person&` 更匹配 | [[temp.over]] |
| `template<class T> void f(T&&, T&&); f(i, 0);` 失败 | 左值推出 `int&`、右值推出 `int`，冲突 | [[temp.deduct.call#3]] |
| `f(typename C::iterator)` 无法推导 `C` | 限定名前缀是非推导语境 | [[temp.deduct.type#5]] |

## 思考题

!!! question "思考题 1"
    ```cpp
    const int arr[2] = {1, 2};
    auto a = arr;
    auto& b = arr;
    decltype(auto) c = (arr[0]);
    auto [x, y] = arr;
    ```
    `a`、`b`、`c`、`x` 的类型（`decltype` 结果）分别是什么？

<details markdown="1">
<summary>答案</summary>

- `a`：按值推导，数组退化为指针，指向的 `const` 保留：`const int*`。
- `b`：引用推导，不退化，`auto` 推导为 `const int[2]`，`b` 是 `const int(&)[2]`。
- `c`：`(arr[0])` 是左值，类型 `const int`，`decltype` 给 `const int&`。
- `x`：结构化绑定，隐藏变量 `e'` 是 `auto e'[2]` 从数组逐元素拷贝——按 [[dcl.struct.bind]] ¶1，数组情形下 `e'` 的类型是 "*cv* A"，其中 cv 来自 `auto` 的说明符（这里没有），`A` 是数组类型 `const int[2]`；于是 `decltype(x)` 是 `const int`。注意这与 `auto a = arr` 的退化不同：结构化绑定对数组是逐元素复制，不退化。
</details>

!!! question "思考题 2"
    为什么 `std::forward` 要求显式写模板实参，而 `std::move` 不用？如果把 `forward` 的形参改成 `T&& t` 让它可以推导，会出什么问题？

<details markdown="1">
<summary>答案</summary>

`forward` 的作用是**恢复**调用者那一层的值类别，而这个信息只编码在外层函数模板的 `T` 中（左值 → `T = U&`，右值 → `T = U`）。在函数体里，具名形参 `x` 本身永远是左值；如果让 `forward` 从 `x` 推导，它只能看到"左值"，永远推出 `U&`，于是永远返回左值——完全失去作用。所以 `forward` 把形参放进非推导语境（`remove_reference_t<T>&`），强制调用者把外层的 `T` 传进来。`std::move` 不需要外层信息——它总是转成亡值，所以可以推导。
</details>

!!! question "思考题 3"
    `auto x = expr;` 与 `template<class T> void f(T); f(expr);` 推导出的 `T` 何时不同？

<details markdown="1">
<summary>答案</summary>

只有 `expr` 是花括号初始化列表时：`auto x = {1, 2};` 推导为 `std::initializer_list<int>`，`f({1, 2})` 推导失败。（`auto x{1};` 是直接列表初始化，单元素时推导为 `int`，对应 `f(1)`。）其余情形 [[dcl.type.auto.deduct]] 直接调用 [[temp.deduct.call]]，结果完全相同。另外，返回类型的 `auto` 连这个例外都没有——`return {1, 2};` 直接非良构。
</details>

## 小结

- **两个引擎**：模板推导（`auto`、CTAD、泛型 lambda、初始化捕获都用它）与 `decltype` 规则（`decltype(auto)` 用它）。
- **按值推导**丢引用、丢顶层 cv、数组/函数退化；**按引用推导**全部保留；**转发引用**把值类别编码进 `T`。
- **引用折叠**：有一个 `&` 就是 `&`。`std::forward<T>` 借此恢复值类别。
- **`auto` 与模板推导的唯一差别**是 `= {...}` 推导为 `initializer_list`。
- **`decltype(name)` 看声明，`decltype((name))` 看值类别**；结构化绑定的名字给出"被引用类型"。
- **推导不做隐式转换**——需要转换时显式指定模板实参，或用 `std::type_identity_t` 关掉某个形参的推导。
