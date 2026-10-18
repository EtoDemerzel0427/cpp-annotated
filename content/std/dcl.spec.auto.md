---
title: 占位类型说明符
summary: auto / decltype(auto) / Concept auto 能出现在哪里；变量、返回类型、参数（简写函数模板）、模板参数、auto(x) 中的占位类型；占位类型推导即模板实参推导（auto）或 decltype 规则（decltype(auto)）；返回类型推导的递归与重声明规则
status: done
covers: dcl.spec.auto.general, dcl.type.auto.deduct
since: c++11
papers: N3638, N3922, P1141, P0849R8, P2266
related: dcl.type.decltype, temp.deduct.call, dcl.fct, expr.type.conv, dcl.struct.bind, stmt.return, temp.param, dcl.type.class.deduct
tags: 声明, 类型推导, auto
updated: 2026-10-17
---

**占位类型**（placeholder type）是稍后才确定的类型，包括 `auto`、`decltype(auto)`，以及带约束的 `std::integral auto` 等。它们在不同位置有不同的含义：

| 位置 | 含义 | 何时确定 |
|---|---|---|
| 变量声明 `auto x = e;` | 从初始化器推导 | 声明处 |
| 返回类型 `auto f() { return e; }` | 从 return 语句推导 | 函数定义处 / 模板实例化时 |
| 尾置返回 `auto f() -> int` | 只是语法，真正的类型在 `->` 后面 | 立即 |
| 参数 `void f(auto x)` | 简写函数模板：每个 `auto` 是一个发明的模板参数 | 每次调用时（模板实参推导） |
| 模板参数 `template<auto N>` | 从模板实参推导 NTTP 的类型 | 特化时 |
| 显式转换 `auto(e)`、`auto{e}` | 衰变复制（decay-copy） | 表达式处 |
| `new auto(e)` | 从初始化器推导分配的类型 | 表达式处 |
| 结构化绑定 `auto [a, b] = e;` | 推导隐藏变量的类型 | 声明处 |

其中只有参数位置的 `auto` 不是推导一次就确定下来，而是把函数变成模板。本页对应 9.2.9.7 [dcl.spec.auto]：9.2.9.7.1 规定占位符能出现在哪里，9.2.9.7.2 规定推导算法。CTAD 中推导类类型的占位符另见 [[dcl.type.class.deduct]]。

```text
placeholder-type-specifier:
    type-constraint(opt) auto
    type-constraint(opt) decltype ( auto )
```

---

## 9.2.9.7.1 占位类型能出现在哪里

¶1 规定，占位类型说明符指定一个稍后才替换的类型，通常由初始化器推导得到。

### 参数：简写函数模板与泛型 lambda（¶2）

¶2 规定，以下三种 *parameter-declaration* 的类型可以用 `type-constraint(opt) auto` 形式的占位符来声明：

- ¶2.1 函数声明的参数，此时函数是**简写函数模板**（abbreviated function template，[[dcl.fct]]），C++20 引入；
- ¶2.2 lambda 表达式的参数，即泛型 lambda（[[expr.prim.lambda]]），C++14 引入；
- ¶2.3 模板参数，即 `template<auto N>`（C++17）、`template<std::integral auto N>`（C++20）。

占位符必须作为说明符序列中的一个说明符出现（或者出现在替代它的尾置返回类型中），称为该函数、lambda 或模板参数的**泛型参数类型占位符**。注意，这个位置只能用 `auto`，不能用 `decltype(auto)`。

```cpp run ok
#include <concepts>
#include <cstdio>
void print(const auto& x) { std::printf("%d\n", int(x)); }      // 简写函数模板
std::integral auto twice(std::integral auto n) { return n * 2; }  // 受约束的参数与返回类型
template<auto N> struct Const { static constexpr auto value = N; };   // NTTP 占位符
int main() {
    print(3.7);                          // 等价于 template<class T> void print(const T&)
    auto add = [](auto a, auto b) { return a + b; };   // 泛型 lambda
    static_assert(Const<'x'>::value == 'x');
    return twice(2) + add(1, 2) - 7;
}
```

```cpp error
void f(decltype(auto) x);          // error: 参数只能用 auto 形式
```

`void print(const auto& x)` 等价于 `template<class T> void print(const T& x)`，每个泛型参数类型占位符对应一个发明的模板参数（[[dcl.fct]]）。所以简写函数模板就是函数模板，可以特化、显式实例化，也参与偏序；同样，按 ODR 对模板的规则，它在不同 TU 中也不能有不同的定义。

### 尾置返回类型（¶3）

¶3 规定，如果函数声明符有尾置返回类型，说明符序列中可以出现占位符。这时 `auto` 只是语法上的占位，函数的返回类型就是 `->` 之后的类型（那里也可以再出现占位符，从而进行推导）。

```cpp
auto f() -> int;              // 返回 int
auto g() -> auto& ;           // 返回类型从 return 语句推导，形如 auto&
```

### 返回类型推导（¶4）

¶4 规定，占位符可以出现在函数声明符所声明的返回类型中，转换函数除外（转换函数的 `operator auto()` 由 [[class.conv.fct]] 另行规定）。函数的返回类型由函数体中非弃置的 return 语句推导，这里的非弃置排除了 `if constexpr` 中被丢弃分支里的 return（[[stmt.if]]）。

```cpp run ok
#include <type_traits>
template<class T>
auto unwrap(T t) {
    if constexpr (std::is_pointer_v<T>) return *t;   // T = int* 时只有这条 return 不被丢弃
    else return t;
}
int main() { int v = 3; return unwrap(&v) + unwrap(4) - 7; }
```

### 变量（¶5）

¶5 规定，用占位类型声明的变量，其类型由初始化器推导，而且占位类型只能用于变量的初始化声明。占位符必须作为说明符序列中的说明符出现；说明符序列后面必须跟一个或多个声明符，每个声明符都必须带非空的初始化器。

```cpp run ok
auto x = 5;                    // int
const auto *v = &x, u = 6;     // v: const int*，u: const int —— auto 在两处都推导为 int
static auto y = 0.0;           // double
auto f() -> int;
auto g() { return 0.0; }       // 返回 double
auto (*fp)() -> auto = f;      // 函数指针：返回类型也从 f 推导
auto h();                      // OK: 返回类型待定义时推导
int f() { return 0; }
auto h() { return 1; }
int main() { return fp() + int(y) + h() + u - 7; }
```

```cpp error
auto x;                        // error: 没有初始化器
auto int r;                    // error: auto 不再是存储类说明符（C++11 起）
struct S { auto m = 1; };      // error: 非静态数据成员不能用占位类型（它不是"变量"）
```

为什么非静态数据成员不能用 `auto`？默认成员初始化器只提供默认值，构造函数可以用别的值初始化成员；而类的布局必须在类定义结束时就确定下来。让成员类型依赖于一个可能根本不使用的初始化器，会带来大量复杂性（例如初始化器中引用了尚不完整的类自身）。静态数据成员则可以使用占位类型：`static inline auto m = 1;`、`static constexpr auto n = 2;`。

¶5 末尾指出，`auto` 也用于引入结构化绑定（[[dcl.struct.bind]]）。

### new 表达式与函数式转换（¶6–7）

¶6 规定，占位符可以出现在 *new-expression* 的 *new-type-id* 或 *nofun-type-id* 中，例如 `new auto(1)` 分配一个 `int`。

¶7 规定，`auto` 可以作为函数式记法的显式类型转换中的简单类型说明符，即 `auto(x)`、`auto{x}`（C++23，[[P0849R8]]）。

```cpp run ok
#include <vector>
#include <algorithm>
#include <type_traits>
int main() {
    int* p = new auto(42);                 // new auto
    std::vector<int> v{3, 1, 3, 2};
    // 删除所有等于 v.front() 的元素：front() 返回引用，删除过程中它所指的元素会被覆盖
    std::erase(v, auto(v.front()));        // auto(x)：生成一个副本（prvalue）
    const int ci = 0;
    static_assert(std::is_same_v<decltype(auto(ci)), int>);   // 衰变复制：去掉顶层 const
    int result = int(v.size()) - 2 + (*p - 42);                // v == {1, 2}
    delete p;
    return result;
}
```

`auto(x)` 的语义是**衰变复制**（decay-copy）：结果是一个 prvalue，其类型是 `x` 的类型经过数组/函数到指针的转换、去掉引用和顶层 cv 之后得到的类型。在此之前，人们只能写 `auto tmp = x;`，或者使用库内部的 `decay-copy` 函数。注意 `auto(x)` 不同于 `T(x)`：后者需要写出类型，而在泛型代码中这个类型（`std::decay_t<decltype(x)>`）往往很长。

### 其他位置一律非良构（¶8）

¶8 规定，在本节没有明确允许的地方使用占位类型，程序非良构。例如模板实参 `std::vector<auto>`、`sizeof(auto)`、`catch (auto e)`、函数参数中的 `decltype(auto)`、数组元素类型、类型别名 `using T = auto;`。

### 多个声明符必须推导出相同类型（¶9）

¶9 规定，如果 *init-declarator-list* 中有多个声明符，它们都必须声明变量；每个变量的类型独立推导，但替换占位符的类型必须相同：

```cpp error
#include <initializer_list>
int x = 5;
auto a = 5, *y = &x;           // OK: 两处 auto 都是 int
auto b = 5, c = { 1, 2 };      // error: int vs std::initializer_list<int>
auto d = 1, e = 2.0;           // error: int vs double
```

注意比较的是替换 `auto` 的那个类型，而不是变量的最终类型。`auto a = 5, *y = &x;` 中 `a` 是 `int`、`y` 是 `int*`，但两处 `auto` 都是 `int`。

### 返回类型：多个 return 与无 return（¶10–11）

¶10 规定，如果函数有多个非弃置的 return 语句，每一条都单独推导，推导结果必须相同，不会求公共类型之类的结果来调和：

```cpp error
auto f(bool b) {
    if (b) return 1;
    return 2.0;                // error: 前面推导为 int，这里是 double
}
```

¶11 规定，如果没有非弃置的 return 语句，就当作函数体末尾有一条无操作数的 return，推导结果为 `void`：

```cpp error
auto  f() { }                  // OK: 返回 void
auto* g() { }                  // error: 无法从 void() 推导出 auto*
```

### 模块：导出的函数（¶12）

¶12 规定，一个导出的、返回类型使用占位符的函数，必须在包含其导出声明的 TU 中（私有模块片段之外）定义。原因是导入者需要知道返回类型才能使用这个函数，而导入者只能看到模块接口。Note 2 指出，推导出的返回类型不能是具有内部链接的名字，否则导入者无法命名它（[[basic.link]]）。

### 未推导的占位符不能被使用（¶13）

¶13 规定，如果一个表达式指名了类型尚未推导的变量或函数，程序非良构。但函数中一旦出现过一条非弃置的 return 语句，由它推导出的返回类型就可以在函数的其余部分使用，包括其他 return 语句。因此只要第一条 return 不是递归的，函数就可以递归：

```cpp run ok
auto sum(int i) {
    if (i == 1)
        return i;              // 推导：返回 int
    else
        return sum(i - 1) + i; // OK: 返回类型已知
}
int main() { return sum(4) - 10; }
```

```cpp error
auto n = n;                    // error: n 的初始化器引用了 n
auto f();
void g() { &f; }               // error: f 的返回类型未知（尚未定义）
auto fact(int n) {
    return n <= 1 ? 1 : n * fact(n - 1);   // error: 第一条 return 就递归调用了自己
}
```

`fact` 的写法看上去没有问题，但推导时必须先知道 `fact(n - 1)` 的类型，而这正是要推导的东西。把基本情形单独写成第一条 return 即可。

### 契约中的结果绑定（¶14）{{c++26}}

¶14 规定，结果绑定（`post(r : …)` 中的 `r`，[[dcl.contract.res]]）永远不会具有未推导的占位类型。后置条件在语义上是在函数体之后检查的，所以即使函数的返回类型是 `auto`，后置条件里也可以使用 `r`：

```cpp
auto f()
    post(r : r == 7)    // OK: r 的类型是推导出的 int
{
    return 7;
}
```

### 模板中的返回类型推导（¶15）

¶15 规定，对于模板化函数，返回类型推导在定义被实例化时进行，即使 return 语句的操作数不依赖于模板参数也是如此。Note 3 指出，因此对该函数模板特化的任何使用（哪怕只是取 `decltype`）都会导致隐式实例化；实例化中出现的错误不在函数类型的直接语境中，会使程序非良构，这是硬错误，而不是 SFINAE。

```cpp run ok
template<class T> auto f(T t) { return t; }        // 实例化时推导
typedef decltype(f(1)) fint_t;                     // 为了推导返回类型，实例化 f<int>
template<class T> auto f(T* t) { return *t; }
void g() { int (*p)(int*) = &f; (void)p; }        // 两个 f 都被实例化以确定返回类型，选中第二个
int main() { }
```

!!! warning "返回类型推导与 SFINAE"
    `template<class T> auto size_of(T t) { return t.size(); }` 不适合用于 SFINAE 检测。对于没有 `size()` 的类型，错误发生在函数体的实例化过程中，是硬错误。需要对 SFINAE 友好时，应使用尾置返回类型 `-> decltype(t.size())` 或 `requires` 约束。

### 重声明必须使用相同的占位符（¶16）

¶16 规定，如果函数（模板）F 的声明返回类型使用了占位符，那么 F 的重声明和特化也必须使用同一个占位符，而不能使用推导出的类型；反过来，如果原声明没有使用占位符，重声明也不能使用。

```cpp error
auto f();
auto f() { return 42; }        // 返回类型是 int
auto f();                      // OK: 同一个占位符
int f();                       // error: auto 与 int 不匹配
decltype(auto) f();            // error: auto 与 decltype(auto) 不匹配
```

为什么不能用 `int f();` 重声明？返回类型为 `auto` 是函数声明的一部分，属于它的签名特征，`auto f()` 和 `int f()` 被视为不同的声明形式，即使推导结果相同。这样规定之后，编译器只看到声明就能知道这个函数的返回类型需要推导。

标准例子中关于模板的部分如下：

```cpp
template <typename T> auto g(T t) { return t; } // #1
template auto g(int);                           // OK: 显式实例化，返回类型 int
template char g(char);                          // error: 没有匹配的模板（#1 的返回类型是 auto）
template<> auto g(double);                      // OK: 前向声明一个显式特化，返回类型未知

template <class T> T g(T t) { return t; }       // OK: 与 #1 不是功能等价的，是另一个模板
template char g(char);                          // OK: 匹配第二个模板
template auto g(float);                         // 仍然匹配 #1
void h() { return g(42); }                      // error: 有歧义
```

这个例子的最后一部分还展示了 `auto` 也可以用于变量的重声明：`extern int v; auto v = 17;` 是合法的（重声明 `v`），`auto S::i = 23;` 也可以定义静态数据成员，因为 ¶16 的限制只针对函数。另外，在 `template<class T> struct A { friend T frf(T); }; auto frf(int i) { return i; }` 中，`frf` 不是 `A<int>` 的友元，因为友元声明的返回类型是 `T` 而不是占位符，二者不对应。

### 不能是虚函数、不能是协程（¶17–18）

¶17 规定，返回类型使用占位符的函数不能是虚函数；¶18 规定它也不能是协程。

```cpp error
struct S { virtual auto f() { return 1; } };   // error: 不能是虚函数
```

为什么？覆盖关系要求派生类虚函数的返回类型与基类的相同或协变（[[class.virtual]]），这需要在类定义时就知道返回类型；而推导要等到函数定义处才能进行，函数定义可能在类外，甚至在另一个 TU 中。协程的返回类型决定了承诺类型（`std::coroutine_traits<R, Args...>`），而推导返回类型又需要先分析函数体中的 `co_return`，这就形成了循环依赖。

### 显式实例化声明（¶19）

¶19 规定，显式实例化声明（`extern template`）不会导致用占位类型声明的实体被实例化，但也不阻止为了确定其类型而进行的实例化：

```cpp run ok
template <typename T> auto f(T t) { return t; }
extern template auto f(int);    // 不实例化 f<int>
int (*p)(int) = f;              // 为了确定返回类型而实例化 f<int>；
                                // 但程序中某处仍需要显式实例化定义
template auto f(int);           // 显式实例化定义（这里补上，使程序完整）
int main() { return p(0); }
```

---

## 9.2.9.7.2 占位类型推导（[dcl.type.auto.deduct]）

¶1 定义了**占位类型推导**（[[g:placeholder-type-deduction]]），即把一个含有占位类型的类型 T 替换为推导出的类型的过程。

### 确定 T 与 E（¶2）

¶2 规定，首先要确定含占位符的类型 T 和对应的初始化子句 E：

| 场合 | T | E |
|---|---|---|
| ¶2.1 return 语句（函数返回类型含占位符） | 声明的返回类型 | 无操作数时为 `void()`；花括号列表则非良构；逗号表达式 X 时为 `(X)`；否则就是操作数 |
| ¶2.2 变量 | 变量的声明类型 | `= e` 时为 `e`；`{ e }` 时为 `e`（必须恰好一个）；`( e )` 时为 `e`（必须恰好一个） |
| ¶2.3 显式类型转换 `auto(…)` / `auto{…}` | `auto`（只能是 `auto`） | 圆括号或花括号中的唯一表达式 |
| ¶2.4 常量模板参数 | 模板参数的声明类型 | 对应的模板实参 |

此外，**T 不能是数组类型**（`auto a[] = {1, 2};` 非良构）。如果 E 的类型是 `void`（return 语句没有操作数，或者返回 `void` 表达式），T 必须是 `decltype(auto)` 或 `cv auto`（可带约束），不能是 `auto&`、`auto*` 等。

```cpp error
#include <initializer_list>
auto f() { return {1, 2}; }    // error: return 语句不能用花括号列表推导
auto x3{ 1, 2 };               // error: 直接列表初始化只能有一个元素
auto v[] = { 1, 2 };           // error: T 不能是数组
auto& g() { return void(); }   // error: E 是 void，T 只能是 cv auto 或 decltype(auto)
```

逗号表达式要包上括号（¶2.1.3），原因是技术性的：E 要当作初始化子句使用，而逗号表达式不是 *assignment-expression*，不能直接作为初始化子句；加上括号后语义不变。

### auto：按模板实参推导（¶3）

¶3 规定，对于 `type-constraint(opt) auto` 形式，推导出的类型 T′ 按模板实参推导的规则确定：

1. 把 T 中的 `auto` 替换为一个新发明的类型模板参数 `U`，得到 P。但如果初始化是复制列表初始化（`= { … }`），就替换为 `std::initializer_list<U>`，此时 `std::initializer_list` 的声明必须先于占位符出现（即需要包含 `<initializer_list>`）。
2. 把 P 当作函数模板的参数类型、E 当作对应的实参，按从函数调用推导的规则（[[temp.deduct.call]]）求出 U。推导失败则声明非良构。
3. 把 U 代入 P，得到 T′。

标准的 Example 2 说得最清楚：`const auto& i = expr;` 中 `i` 的类型，就是用 `f(expr)` 调用发明的函数模板 `template<class U> void f(const U& u);` 时参数 `u` 的类型。

由此可以直接得出 `auto` 的那些常见规则：

```cpp run ok
#include <type_traits>
template<class A, class B> constexpr bool same = std::is_same_v<A, B>;
int i = 0;
const int ci = 0;
const int carr[3] = {1, 2, 3};
int f(int);

auto a1 = ci;        static_assert(same<decltype(a1), int>);              // 按值：去掉顶层 const
auto& a2 = ci;       static_assert(same<decltype(a2), const int&>);       // 按引用：保留 const
auto a3 = carr;      static_assert(same<decltype(a3), const int*>);       // 数组退化
auto& a4 = carr;     static_assert(same<decltype(a4), const int(&)[3]>);  // 引用不退化
auto a5 = f;         static_assert(same<decltype(a5), int(*)(int)>);      // 函数退化为指针
auto&& a6 = i;       static_assert(same<decltype(a6), int&>);             // 转发引用 + 左值 → int&
auto&& a7 = 1;       static_assert(same<decltype(a7), int&&>);            // 转发引用 + 右值 → int&&
const auto* a8 = &i; static_assert(same<decltype(a8), const int*>);
int main() { }
```

### initializer_list 特例

花括号与 `auto` 的组合是 `auto` 推导中唯一不同于模板实参推导的地方（模板实参推导从 `{1, 2}` 推导不出任何东西）：

```cpp run ok
#include <initializer_list>
#include <type_traits>
auto x1 = { 1, 2 };        // std::initializer_list<int>
auto x4 = { 3 };           // std::initializer_list<int>（复制列表初始化：总是 initializer_list）
auto x5{ 3 };              // int（直接列表初始化：单个元素，按 ¶2.2.2 取出元素推导）
static_assert(std::is_same_v<decltype(x1), std::initializer_list<int>>);
static_assert(std::is_same_v<decltype(x4), std::initializer_list<int>>);
static_assert(std::is_same_v<decltype(x5), int>);
int main() { }
```

```cpp error
#include <initializer_list>
auto x2 = { 1, 2.0 };      // error: U 推导出 int 和 double，冲突
auto x3{ 1, 2 };           // error: 直接列表初始化只允许一个元素
```

!!! history "C++11/14 中 `auto x{3};` 是 initializer_list"
    在 C++11 中，`auto x{3};` 推导为 `std::initializer_list<int>`，这几乎总是出乎意料。[[N3922]] 修改了规则：直接列表初始化只允许单个元素，并推导为该元素的类型；复制列表初始化 `= {…}` 仍然推导为 initializer_list。这一修改作为缺陷报告应用于 C++14，各编译器在 C++11 模式下通常也采用新规则。

¶3 中间还有一句：如果 E 是在函数模板偏序（[[temp.func.order]]）中为 `decltype(auto)` 类型的常量模板参数合成的值，声明非良构。这是一条处理偏序的边角规则。

### decltype(auto)：按 decltype 规则（¶4）

¶4 规定，对于 `type-constraint(opt) decltype(auto)` 形式，T 必须只是占位符本身，不能是 `decltype(auto)*`、`const decltype(auto)&` 等。推导出的类型就是把 E 当作 `decltype` 的操作数所得的类型（[[dcl.type.decltype]]）。

```cpp run ok
#include <type_traits>
template<class A, class B> constexpr bool same = std::is_same_v<A, B>;
int i;
int&& f();
auto           x2a(i);         static_assert(same<decltype(x2a), int>);
decltype(auto) x2d(i);         static_assert(same<decltype(x2d), int>);
auto           x4a = (i);      static_assert(same<decltype(x4a), int>);
decltype(auto) x4d = (i);      static_assert(same<decltype(x4d), int&>);    // 括号！
auto           x5a = f();      static_assert(same<decltype(x5a), int>);
decltype(auto) x5d = f();      static_assert(same<decltype(x5d), int&&>);
auto          *x7a = &i;       static_assert(same<decltype(x7a), int*>);
auto f2(int x) -> decltype(auto) { return (x); }   // C++23 起：x 是 xvalue（返回悬垂引用，Clang 会警告）
static_assert(same<decltype(f2(0)), int&&>);
int main() { }
```

```cpp error
#include <initializer_list>
int i;
decltype(auto) x6d = { 1, 2 };   // error: {1, 2} 不是表达式
decltype(auto)*x7d = &i;         // error: 声明类型不是单纯的 decltype(auto)
```

!!! lawyer "标准例子中的 f1 在 C++23 中是非良构的"
    [dcl.type.auto.deduct] 的 Example 3 里还有一行：

    ```cpp
    auto f1(int x) -> decltype((x)) { return (x); }   // 例子注释："return type is int&"
    ```

    返回类型确实是 `int&`，因为 `decltype((x))` 中的 `(x)` 不是 return 的操作数，只是普通的左值。但函数体中还有 `return (x);`。C++23 起（[[P2266]]），可移动实体 `x` 作为（可以加括号的）return 操作数是 xvalue（[[expr.prim.id.unqual#15]] 中的 move-eligible），而 `int&` 不能绑定到 xvalue，所以这个函数定义在 C++23 及以后是非良构的，Clang 报错 "non-const lvalue reference to type 'int' cannot bind to a temporary of type 'int'"。例子只注释了返回类型，没有提到这一点。同一个例子中的 `f2` 正好展示了这个变化：它的返回类型推导为 `int&&`（C++20 中是 `int&`）。

### 约束（¶5）

¶5 规定，对于带 *type-constraint* 的占位符，其**立即声明的约束**（immediately-declared constraint，[[temp.param]]）对推导出的类型必须得到满足。例如 `std::integral auto x = e;` 要求 `std::integral<推导出的类型>` 成立。

```cpp error
#include <concepts>
std::integral auto a = 1;      // OK
std::integral auto b = 1.0;    // error: std::integral<double> 不满足
std::convertible_to<long> auto c = 'x';   // OK: 检查的是 std::convertible_to<char, long>
```

注意最后一行。立即声明的约束把推导出的类型作为第一个模板实参，所以 `std::convertible_to<long> auto c` 检查的是 `std::convertible_to<char, long>`，而不是 `<long, char>`。

---

## 实现视角

!!! impl "实现视角"
    - mangling：简写函数模板与普通函数模板的 mangled 名相同（发明的模板参数按出现顺序编号，Itanium ABI 中为 `T_`、`T0_`……）。对于使用返回类型推导的函数模板，mangled 名中编码的是占位符（`auto` 编码为 `Da`，`decltype(auto)` 编码为 `Dc`），而不是推导出的类型，这与 ¶16 要求重声明使用同一占位符的规则相互印证。
    - 诊断：多个 return 推导出的类型不一致时，Clang 的诊断形如 "'auto' in return type deduced as 'double' here but deduced as 'int' in earlier return statement"。
    - 编译开销：返回类型推导要求函数体在每个使用点都可见（通常放在头文件中），并且任何取 `decltype` 的使用都会触发实例化（¶15）。在大型代码库中滥用 `auto` 返回类型会增加编译时间。

!!! history "历史与演进"
    | 标准 | 变化 |
    |---|---|
    | C++11 | `auto` 变量（重新定义关键字）；尾置返回类型；lambda 可省略返回类型（单 return 时） |
    | C++14 | 普通函数的返回类型推导与 `decltype(auto)`（[[N3638]]）；泛型 lambda；`auto x{1}` 改为 `int`（[[N3922]]，作为 DR） |
    | C++17 | `template<auto N>`；结构化绑定；CTAD |
    | C++20 | 简写函数模板、受约束占位符 `Concept auto`（[[P1141]]） |
    | C++23 | `auto(x)` / `auto{x}`（[[P0849R8]]）；隐式移动简化（[[P2266]]）影响 `decltype(auto)` 推导 |
    | C++26 | 契约中的结果绑定（¶14）；结构化绑定包 `auto [...xs]` |

!!! pitfall "常见误解"
    - 误以为 `auto` 推导和模板推导完全一样。两者几乎一样，唯一的区别是 `= {…}` 会推导出 `std::initializer_list`。
    - 误以为 `auto x = expr;` 会保留 expr 的引用性和 const。不会，按值推导会去掉引用和顶层 cv。需要保留时，用 `auto&`、`const auto&`、`auto&&` 或 `decltype(auto)`。
    - 误以为多个 return 会推导出公共类型。不会，它们必须完全相同；求公共类型的是条件运算符 `?:`。
    - 误以为 `decltype(auto)` 是更好的 `auto`。它会保留引用，如果返回局部变量时加了括号，就会返回悬垂引用。只应在需要完美转发返回值时使用它。

!!! summary "小结"
    - 允许的位置：变量（必须有初始化器）、返回类型、尾置返回类型、函数/lambda/模板参数（仅限 `auto` 形式）、`new auto`、`auto(x)`、结构化绑定。在其他位置使用非良构。
    - `auto` 的推导就是模板实参推导，外加 `= {…}` 的 initializer_list 特例；`decltype(auto)` 的推导就是 `decltype(E)`。
    - 返回类型：多个 return 必须一致；没有 return 时推导为 `void`；第一条 return 之后可以递归。
    - 重声明必须使用同一占位符；不能是虚函数或协程；模板中的推导在实例化时进行，出错是硬错误。

!!! question "思考题 1"
    下面每个 `auto` 推导为什么类型？

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
- `d`：`std::initializer_list<const char*>`（需要包含 `<initializer_list>`）。
- `e`：`const char*`（直接列表初始化，单个元素）。
</details>

!!! question "思考题 2"
    为什么 `std::vector<bool> v{true}; auto x = v[0]; v[0] = false;` 之后 `x` 也变成了 `false`？用 `auto(…)` 能修复吗？

<details markdown="1">
<summary>答案</summary>

`vector<bool>::operator[]` 返回代理对象 `std::vector<bool>::reference`（一个 prvalue），`auto` 推导出的就是这个代理类型。代理对象内部引用着 `v` 的存储位，所以 `x` 会随 `v[0]` 变化。`auto(v[0])` 不能修复这个问题，因为衰变复制只会复制代理对象本身，类型仍然是 `reference`。需要写出目标类型：`bool x = v[0];` 或 `auto x = static_cast<bool>(v[0]);`。这是一个经典例子：`auto` 推导出的是表达式的类型，而不是你心里想的那个类型。
</details>
