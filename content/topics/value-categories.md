---
title: 值类别实战
summary: 怎样判断任意表达式是 lvalue、xvalue 还是 prvalue，以及值类别怎样决定引用绑定、重载决议、decltype、移动语义和复制消除。
status: done
since: c++11
order: 10
papers: N3055, P0135R1, P1825R0, P2266R3
related: basic.lval, class.temporary, dcl.init.ref, class.copy.elision, dcl.type.decltype, conv.rval, expr.type, over.ics.rank, topics/type-deduction
tags: 值类别, 移动语义, 复制消除, decltype
updated: 2026-10-19
video: bilibili=BV1m2n16cEz5, youtube=Vr1iS7PpJyo
---

!!! tldr
    - 每个表达式恰好属于 lvalue、xvalue、prvalue 之一；值类别是表达式的属性，与类型无关。`int&& r` 中表达式 `r` 是 lvalue。
    - 名字几乎总是 lvalue；函数调用和强制转换看返回或目标类型：`T&` 得 lvalue，`T&&` 得 xvalue，非引用得 prvalue。
    - `decltype((e))` 把值类别编码成类型：lvalue 得 `T&`，xvalue 得 `T&&`，prvalue 得 `T`。
    - `std::move` 只是转成 xvalue 的强制转换，真正移动资源的是重载决议因此选中的函数。
    - C++17 起 prvalue 不是对象，而是初始化某个对象的方式；用 prvalue 初始化同类型对象时没有复制，也不需要复制或移动构造函数。

## 一个具名的右值引用是左值

```cpp run title="overload.cpp" ok
#include <cstdio>
#include <utility>

void take(const int&) { std::puts("const&"); }
void take(int&&)      { std::puts("&&"); }

int main() {
    int i = 0;
    take(i);              // const&：左值不能绑定 &&
    take(1);              // &&：prvalue
    take(std::move(i));   // &&：xvalue
    int&& r = 2;
    take(r);              // const&：r 是左值
}
```

`r` 的类型是 `int&&`，`take(r)` 却选中了 `const int&` 版本。原因是重载决议看的不是变量声明成什么类型，而是实参表达式的**值类别**（value category）。表达式 `r` 是一个名字，名字是 lvalue。

值类别是表达式的属性，不是值或对象的属性。规范定义在 [[basic.lval]]，这里讲怎样判断和使用它。

## 三种类别

[[basic.lval#1]] 定义了三种基本类别，每个表达式恰好属于其中之一：

- **lvalue**（左值）：指称一个对象或函数的表达式，例如变量名 `x`、`*p`、`a[i]`。
- **xvalue**（亡值，eXpiring value）：也指称一个对象，但这个对象的资源可以被重用，通常因为它快要结束生命周期，例如 `std::move(x)`。
- **prvalue**（纯右值，pure rvalue）：不指称已有的对象，它的求值用来初始化一个对象或计算一个运算数的值，例如 `42`、`a + b`、`std::string("hi")`。

在此之上有两个合并的类别：

- **glvalue**（泛左值）是 lvalue 和 xvalue 的统称，它们的求值确定一个对象、函数（以及 C++26 起的非静态数据成员或直接基类关系）的身份。
- **rvalue**（右值）是 xvalue 和 prvalue 的统称，它们可以绑定到右值引用 `T&&`。

| | 资源可以被重用 | 资源不可以被重用 |
|---|---|---|
| 指称一个已有实体（glvalue） | xvalue | lvalue |
| 不指称已有实体 | prvalue | |

C++17 起，prvalue 不是对象，而是初始化某个对象的方式。被 prvalue 初始化的那个对象叫它的**结果对象**（result object），由 prvalue 所在的上下文提供（[[basic.lval#5]]）。把 prvalue 当作临时对象是 C++17 之前的模型。

## 判断任意表达式的类别

### 一个探针

`decltype((e))` 把值类别编码成类型（[[dcl.type.decltype]]）：lvalue 得 `T&`，xvalue 得 `T&&`，prvalue 得 `T`。据此可以写一个编译期探针：

```cpp run title="probe.cpp" ok
#include <cstdio>
#include <utility>

template<class T> constexpr const char* category      = "prvalue";
template<class T> constexpr const char* category<T&>  = "lvalue";
template<class T> constexpr const char* category<T&&> = "xvalue";
#define CATEGORY(...) category<decltype((__VA_ARGS__))>

struct A { int m; };
A make();

int main() {
    int i = 0;
    int&& rr = 1;
    std::printf("%s %s %s %s %s\n",
        CATEGORY(i),              // lvalue
        CATEGORY(rr),             // lvalue：具名的右值引用
        CATEGORY(std::move(i)),   // xvalue
        CATEGORY(i + 1),          // prvalue
        CATEGORY(make().m));      // xvalue
}
```

本机 Clang 23 输出 `lvalue lvalue xvalue prvalue xvalue`。宏里的两层括号是必需的：只有一层时，`decltype(name)` 给出名字的声明类型，而不是表达式的类别（见下文）。`decltype` 的操作数不求值，所以 `make` 只需声明，不需定义。

### 手工判断的步骤

1. 名字（*id-expression*）几乎总是 lvalue。变量（包括右值引用类型的变量）、函数、数据成员、结构化绑定、模板形参对象都是。例外有两类：枚举项、非类类型的常量模板形参和 `this` 是 prvalue；`return x;`、`co_return x;`、`throw x;` 中可隐式移动的局部变量是 xvalue（C++23 起，[[expr.prim.id.unqual]]）。
2. 函数调用，包括重载运算符和转换函数，看返回类型：`T&` 得 lvalue，对象类型的 `T&&` 得 xvalue，非引用得 prvalue。返回函数的右值引用时得 lvalue。
3. 强制转换，不论哪种写法，看目标类型，规则同上：`static_cast<T&>(e)` 是 lvalue，`static_cast<T&&>(e)` 是 xvalue，`static_cast<T>(e)` 是 prvalue。
4. 内置运算符查下表。大致规律是：算术、比较、逻辑、位运算和后置 `++`、`--` 得到 prvalue；解引用 `*p`、前置 `++`、`--` 和赋值得到指称原对象的 lvalue。
5. 子对象访问随对象走：成员访问 `e.m`、数组下标、`.*` 中，对象是 lvalue 时结果是 lvalue，对象是 xvalue（或被转换成临时对象的 prvalue）时结果是 xvalue。静态数据成员和引用成员例外，总是 lvalue。
6. 括号不改变值类别，`(e)` 与 `e` 相同。但在 `decltype` 中括号会改变结果，见下文。

### 对照表

| 表达式 | 类别 | 说明 |
|---|---|---|
| 变量名 `x`，任何类型，包括 `T&&` | lvalue | [[expr.prim.id.unqual]] |
| `return x;` 中可隐式移动的 `x` | xvalue | C++23 起（[[P2266R3]]） |
| 函数名 `f` | lvalue | |
| 枚举项 `Red` | prvalue | |
| 非类类型的常量模板形参 `N` | prvalue | 类类型的模板形参对象是 lvalue |
| `this` | prvalue | [[expr.prim.this]] |
| 字符串字面量 `"abc"` | lvalue | 它是静态存储期的数组对象，`&"abc"` 合法 |
| 其他字面量 `42`、`'a'`、`nullptr`、`true` | prvalue | |
| 用户定义字面量 `"x"s` | 按 `operator""` 的返回类型 | |
| lambda 表达式 | prvalue | 初始化一个闭包对象 |
| `T(args)`、`T{args}` | prvalue | `T` 是引用类型时按引用的规则 |
| `f()` | 按返回类型 | [[expr.call]] |
| `static_cast<T&>(e)`、`<T&&>`、`<T>` | lvalue、xvalue、prvalue | 目标是函数的右值引用时是 lvalue |
| `std::move(x)` | xvalue | 就是 `static_cast<T&&>` |
| `std::forward<T>(x)` | `T` 是左值引用时 lvalue，否则 xvalue | |
| `*p` | lvalue | [[expr.unary.op]] |
| `&x` | prvalue | |
| `++i`、`--i` | lvalue | [[expr.pre.incr]]，指称 `i` 本身 |
| `i++`、`i--` | prvalue | [[expr.post.incr]]，值是修改前的旧值 |
| `a = b`、`a += b` | lvalue | [[expr.assign]]，指称左操作数 |
| `a + b`、`-a`、`a < b`、`!a`、`a & b` | prvalue | 内置的算术、比较、逻辑、位运算 |
| 内置 `a[i]` | 数组操作数是 lvalue 或操作数是指针时为 lvalue，数组是右值时为 xvalue | [[expr.sub]] |
| `e.m`，非静态、非引用的数据成员 | 与 `e` 相同 | `e` 是 prvalue 时先转换成临时对象，结果是 xvalue |
| `e.m`，引用成员 | lvalue | [[expr.ref]] |
| `e.s`，静态数据成员 | lvalue | |
| `e.f`，非静态成员函数 | prvalue | 只能立即被调用 |
| `p->m` | lvalue | 等价于 `(*p).m` |
| `e.*pm`，数据成员指针 | 与 `e` 相同 | [[expr.mptr.oper]] |
| `p->*pm`，数据成员指针 | lvalue | |
| `c ? a : b` | 两边是同类型、同类别的 glvalue 时取该类别，否则 prvalue | [[expr.cond]] |
| `a, b` | 与 `b` 相同 | [[expr.comma]] |
| `throw e` | prvalue，类型 `void` | |
| `typeid(e)` | lvalue | 指称一个 `const std::type_info` 对象 |
| `sizeof e`、`alignof(T)`、`noexcept(e)` | prvalue | |
| `new T` | prvalue | |
| `co_await e` | 按 `await_resume()` 的返回类型 | [[expr.await]] |

[[basic.lval#4]] 的注 3 列出了 xvalue 的全部来源，可以归成三种：

1. 返回或转换到对象的右值引用：函数调用、`static_cast<T&&>`、`std::move`。
2. 可隐式移动的名字，如 `return x;` 中的 `x`。
3. 对 xvalue 或被转换成临时对象的 prvalue 做子对象访问。

## decltype 与值类别

[[dcl.type.decltype]] 有两套规则，区别就在有没有那层括号：

| 形式 | 规则 | 结果 |
|---|---|---|
| 不加括号的 `decltype(name)`、`decltype(e.member)` | 实体的声明类型 | 可能是引用，也可能不是，与值类别无关 |
| 其他所有情形，包括 `decltype((name))` | 表达式的类型加值类别 | xvalue 得 `T&&`，lvalue 得 `T&`，prvalue 得 `T` |

```cpp ok
#include <type_traits>
#include <utility>
int i = 0;
int&& rr = 0;
struct S { int m; };
const S cs{};

static_assert(std::is_same_v<decltype(i), int>);           // 声明类型
static_assert(std::is_same_v<decltype((i)), int&>);        // 左值表达式
static_assert(std::is_same_v<decltype(rr), int&&>);        // 声明类型
static_assert(std::is_same_v<decltype((rr)), int&>);       // rr 作为表达式是左值
static_assert(std::is_same_v<decltype(std::move(i)), int&&>);
static_assert(std::is_same_v<decltype(i + 0), int>);
static_assert(std::is_same_v<decltype(cs.m), int>);        // 成员的声明类型
static_assert(std::is_same_v<decltype((cs.m)), const int&>); // 表达式：const S 的成员是 const 左值
```

`decltype(auto)` 沿用同一套规则，所以 `return` 语句里多写一对括号，返回类型就从值变成了引用：

```cpp ok
int g;
decltype(auto) f1() { return g; }     // int
decltype(auto) f2() { return (g); }   // int&：加了括号，返回引用
```

对局部变量这样写会返回悬垂引用，C++23 起推出的是 `int&&`，同样悬垂。详见 [[topics/type-deduction]]。

## 引用绑定与重载决议

值类别最主要的用途是决定引用能绑定到什么（[[dcl.init.ref]]）：

| 引用类型 | 能绑定的表达式 | 说明 |
|---|---|---|
| `T&` | 非 const 的 `T` 左值 | 不能绑定右值，即非 const 引用不能绑定临时对象 |
| `const T&` | 任何 `T` 表达式，以及能转换为 `T` 的表达式 | 绑定 prvalue 时产生临时对象并延长其生命周期 |
| `T&&` | `T` 的右值，以及能转换为 `T` 的表达式（产生新的临时对象） | 不能直接绑定左值；绑定 prvalue 时同样产生临时对象并延长其生命周期 |
| 转发引用 `auto&&`、模板中的 `T&&` | 任何表达式 | 实参是左值时 `T` 推导为 `U&`，引用折叠为 `U&`；是右值时 `T` 推导为 `U` |

重载决议中，两个候选只在 `T&` 和 `T&&` 上有区别时，右值优先绑定 `&&`，左值只能选 `&`（[[over.ics.rank]]）。开头的 `take` 例子，以及移动构造函数与复制构造函数之间的选择，都靠这条规则。

## std::move 与 std::forward 只是强制转换

`std::move` 在运行时什么也不做，只是一次编译期的类型转换。去掉 `constexpr` 后，它的全部实现是：

```cpp
#include <type_traits>
template<class T>
std::remove_reference_t<T>&& move(T&& t) noexcept {
    return static_cast<std::remove_reference_t<T>&&>(t);
}
```

它把任意表达式转成 xvalue，于是重载决议选中接受 `T&&` 的函数，例如移动构造函数或移动赋值运算符。真正转移资源的是那个被选中的函数。由此可以推出：

- 对 const 对象 `std::move` 得到 `const T&&`，绑不上移动构造函数的 `T&&` 形参，重载决议选中 `const T&` 的复制构造函数，默默地变成了复制。
- 对没有移动构造函数的类型，`std::move` 同样变成复制。
- 对 `int`、指针这样的标量，`std::move` 没有作用，结果就是复制一次值。

在 `template<class T> void f(T&& x)` 中，不论传入什么，函数体里的表达式 `x` 都是左值，因为它有名字。直接把 `x` 传给下一层函数，调用者传入的是右值这一信息就丢了。`std::forward<T>(x)` 用 `T` 里记录的信息把它恢复成原来的类别：

```cpp run title="forward.cpp" ok
#include <cstdio>
#include <utility>

void sink(int&)  { std::puts("lvalue"); }
void sink(int&&) { std::puts("rvalue"); }

template<class T>
void relay(T&& x) {
    sink(x);                     // 总是 lvalue
    sink(std::forward<T>(x));    // 恢复原来的类别
}

int main() {
    int i = 0;
    relay(i);    // lvalue lvalue
    relay(1);    // lvalue rvalue
}
```

`std::forward<T>(x)` 本质上也只是 `static_cast<T&&>(x)`。传入左值时 `T = U&`，`U& &&` 折叠为 `U&`，结果是 lvalue；传入右值时 `T = U`，结果是 xvalue。引用折叠和推导规则见 [[topics/type-deduction]]。

## 保证的复制消除 {{c++17}}

C++14 及以前，返回值优化（RVO）只是标准允许的优化：即使编译器省略了复制，被省略的复制或移动构造函数也必须可用。所以对既不能复制也不能移动的类型，例如 `std::mutex`、`std::atomic`，连按值返回一个新对象的工厂函数都写不出来。

C++17 的 [[P0135R1]] 改变了模型：用 prvalue 初始化同类型的对象时，prvalue 直接初始化目标对象，中间没有临时对象，因此语义上也没有复制或移动，不需要相应的构造函数（[[dcl.init.general#15]]、[[class.copy.elision]]）：

```cpp ok
#include <atomic>
#include <mutex>

struct Pinned {
    Pinned() = default;
    Pinned(const Pinned&) = delete;
    Pinned(Pinned&&) = delete;
};

Pinned make() { return Pinned{}; }   // OK：prvalue 直接初始化调用者的对象
Pinned a = make();                   // OK
Pinned b = Pinned(Pinned(Pinned())); // OK：只有一个对象
auto c = std::atomic<int>(0);        // OK：C++14 中非良构（atomic 不可复制）
std::mutex m = std::mutex();         // OK：同理
```

返回一个具名的局部变量不在保证之列：

```cpp error
struct Pinned {
    Pinned() = default;
    Pinned(const Pinned&) = delete;
    Pinned(Pinned&&) = delete;
};
Pinned make_named() {
    Pinned p;
    return p;          // error: 需要移动构造函数（NRVO 只是允许，不是保证）
}
```

| 情形 | C++17 起 |
|---|---|
| `return T(...);`，返回 prvalue | 保证没有复制或移动 |
| `T x = T(...);` | 保证 |
| `T x = cond ? T(1) : T(2);` | 保证，条件表达式的结果是 prvalue |
| `return local;`，具名返回值优化（NRVO） | 允许省略但不保证；类型必须可移动或可复制 |
| `return param;`，函数形参 | 不能做 NRVO，但会隐式移动 |
| `return std::move(local);` | 阻止 NRVO，强制一次移动（Clang 的 `-Wpessimizing-move` 会警告） |

## 临时对象与生命周期延长

prvalue 在需要一个对象时被转换成临时对象，这叫**临时量实质化**（temporary materialization，[[class.temporary#2]]）。临时对象通常在它所在的完整表达式结束时销毁。把临时对象直接绑定到引用（`const T&` 或 `T&&`），会把它的生命周期延长到与引用相同。但直接的含义很窄：

```cpp run title="lifetime.cpp" ub
#include <cstdio>
#include <string>
#include <utility>

struct A { std::string s = "a string long enough to live on the heap"; };
A make() { return {}; }

int main() {
    const auto& r1 = make().s;           // OK：成员访问作用于临时对象，整个临时对象被延长
    auto&& r2 = std::move(make());       // 悬垂：std::move 的返回值不是临时对象本身
    std::printf("%zu\n", r1.size());     // OK
    std::printf("%zu\n", r2.s.size());   // UB：临时对象已在上一个完整表达式结束时销毁
}
```

`std::move` 是一次函数调用，`r2` 绑定的是它返回的引用，而不是临时对象本身，所以不会延长生命周期。本机 Clang 23 在编译期给出 `-Wdangling` 警告，ASan 在最后一行报告 `stack-use-after-scope`。

引用经由 `.`、`[]`、`?:`、`,` 和某些强制转换绑定到临时对象或它的子对象时，生命周期会延长；经由任何函数调用，包括 `std::move`、`std::min`、返回 `*this` 的成员函数时，不会延长，临时对象在完整表达式结束时照常销毁（[[class.temporary#6]]）。

## 常见误解

!!! pitfall "右值引用是右值"
    类型与值类别是两回事。`int&& r = 1;` 中，`r` 的类型是 `int&&`，但表达式 `r` 的类别是 lvalue。[[expr.type#1]] 甚至先把这个表达式的类型调整为 `int`。可以记成：有名字的就是左值。

!!! pitfall "右值不能被修改"
    xvalue 是右值，但它指称一个真实的对象：`std::move(v).push_back(1)` 合法地修改了 `v`。类类型的 prvalue 也能调用非 const 成员函数，例如 `std::string().append("x")`。不能修改只针对内置运算符：对 `int f();`，`f() = 1` 非良构（[[basic.lval#10]] 注 10）。

!!! pitfall "字面量都是右值"
    字符串字面量是 lvalue。它是一个静态存储期的数组对象，`&"abc"` 合法，类型是 `const char(*)[4]`。

!!! pitfall "std::move 之后对象就空了"
    `std::move` 本身不改变对象。被移动后的标准库对象处于有效但未指定的状态；被移动后的 `int` 值不变。

!!! pitfall "返回时加 std::move 更快"
    `return std::move(local);` 把一个本可以做 NRVO 或隐式移动的表达式变成 xvalue，禁止了 NRVO，换来一次本可避免的移动。C++11 起 `return local;` 就会隐式移动，C++20 和 C++23 又扩大了这条规则的范围，返回局部变量时直接写 `return local;` 即可。

!!! pitfall "xvalue 一定快要销毁了"
    xvalue 只表示允许重用它的资源，不表示它真的即将销毁。`std::move(global)` 是一个指称全局对象的 xvalue，这个对象活到程序结束。

## 历史

!!! history
    - C++98 只有 lvalue 和 rvalue。`const T&` 可以绑定 rvalue，但无法区分可以重用资源的对象。
    - C++11 为右值引用和移动语义引入了 xvalue，并命名了 glvalue 和 prvalue（[[N3055]]）。
    - C++17 的 [[P0135R1]] 让 prvalue 不再是对象，引入结果对象和临时量实质化，复制消除成为保证。
    - C++20 把隐式移动扩展到右值引用类型的局部变量和 `throw` 的操作数等场合（[[P1825R0]]）。
    - C++23 的 [[P2266R3]] 让可隐式移动的名字在 `return` 中直接成为 xvalue，`decltype(auto)` 的结果随之改变。
    - C++26 的拼接表达式（反射）可以指称非静态数据成员和直接基类关系，glvalue 的定义相应扩展。

## 思考题

!!! question "思考题 1"
    设 `std::vector<std::string> v;`。`std::move(v)[0]` 是什么类别？`std::move(v[0])` 呢？

<details markdown="1">
<summary>答案</summary>

`std::move(v)[0]` 是 lvalue。`vector::operator[]` 是重载运算符，返回 `std::string&`，按函数调用看返回类型的规则，结果是 lvalue，尽管 `v` 被转成了 xvalue。内置 `[]` 对 xvalue 数组得到 xvalue，但标准容器的 `operator[]` 没有按值类别重载。

`std::move(v[0])` 是 xvalue，类型为 `std::string`。移动容器中某个元素应该这样写。
</details>

!!! question "思考题 2"
    在 `template<class T> void f(T&& x)` 中，为什么 `f(std::move(i))` 推导出 `T = int`，而 `f(i)` 推导出 `T = int&`？

<details markdown="1">
<summary>答案</summary>

推导看的是实参表达式的值类别。[[temp.deduct.call#3]] 对转发引用有专门的规则：实参是左值时，用 `A` 的左值引用代替 `A` 进行推导，于是 `T = int&`，`T&&` 经引用折叠成为 `int&`。实参是右值（xvalue 或 prvalue）时按普通规则推导，`T = int`，形参类型是 `int&&`。`std::forward<T>` 能恢复原来的类别，信息就来自这里推导出的 `T`。
</details>

!!! question "思考题 3"
    `const std::string& r = std::string("a") + "b";` 安全吗？`const char* p = (std::string("a") + "b").c_str();` 呢？

<details markdown="1">
<summary>答案</summary>

第一个安全。`operator+` 返回 `std::string` prvalue，绑定到 `const std::string&` 时产生临时对象，并把它的生命周期延长到 `r` 的作用域结束。

第二个悬垂。临时的 `std::string` 被用来调用 `c_str()`，这是函数调用，返回的是指针，没有引用直接绑定到临时对象，不会延长生命周期。完整表达式结束时临时对象被销毁，`p` 指向已释放的缓冲区，之后通过 `p` 读取是未定义行为。
</details>
