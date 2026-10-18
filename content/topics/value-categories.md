---
title: 值类别实战
summary: 从读者角度彻底搞懂 lvalue / xvalue / prvalue：如何判定任意表达式的类别、decltype 如何反映它、std::move 与 std::forward 的本质、保证复制消除、生命周期延长与常见误解
status: draft
since: c++11
order: 10
papers: N3055, P0135R1, P2266R3
related: basic.lval, class.temporary, dcl.init.ref, class.copy.elision, dcl.type.decltype, conv.rval, expr.type, over.ics.rank
tags: 值类别, 移动语义, 复制消除, decltype
updated: 2026-10-17
---

值类别（value category）是 C++ 里“人人都在用、很少有人说得清”的概念。天天写 `std::move` 的人，被问到“为什么右值引用类型的变量本身是左值”“为什么多一对括号 `decltype` 的结果就变了”时，也常常答不上来。

本专题的目标是：读完之后，你能对**任意**表达式说出它的值类别，并解释这个类别如何影响引用绑定、重载决议、`decltype`、移动语义与复制消除。规范性的定义与逐段释义在 [[basic.lval]]；这里侧重方法与实战。

## 一、一句话模型

> **值类别回答两个问题：这个表达式有没有“身份”（指代一个确定的实体）？如果有，它的资源能不能被偷走？**

| | 资源可被偷走 | 资源不可被偷走 |
|---|---|---|
| **有身份** | **xvalue**（亡值，*eXpiring value*） | **lvalue**（左值） |
| **无身份** | **prvalue**（纯右值，*pure rvalue*） | — |

在这三类之上，标准再定义两个合并的类别：

- **glvalue**（泛左值）= lvalue ∪ xvalue，共同点是“有身份”；
- **rvalue**（右值）= xvalue ∪ prvalue，共同点是“可以被偷”（可以绑定到 `T&&`）。

C++17 之后还要补充一句：**prvalue 不是对象，而是“初始化某个对象的配方”**。“prvalue 就是临时对象”是 C++17 之前的说法。prvalue 要初始化的那个对象叫“结果对象”，由它所在的上下文提供（[[basic.lval#5]]）。

## 二、判定任意表达式的类别

### 2.1 一个可以直接用的探针

`decltype((e))` 把值类别编码进类型（[[dcl.type.decltype]]）：

- lvalue → `T&`
- xvalue → `T&&`
- prvalue → `T`（不带引用）

据此可以写一个编译期探针。宏里的双层括号是必要的：只有一层时，`decltype(name)` 给出的是名字的声明类型，而不是表达式的类别（见第三节）。

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
        CATEGORY(rr),             // lvalue（具名的右值引用！）
        CATEGORY(std::move(i)),   // xvalue
        CATEGORY(i + 1),          // prvalue
        CATEGORY(make().m));      // xvalue
}
```

（`decltype` 的操作数是未求值操作数，所以 `make` 只需声明、无需定义。）

### 2.2 手工判定的步骤

遇到一个表达式，按下面的顺序判断：

1. **名字**（*id-expression*）：几乎总是 **lvalue**。变量（包括右值引用类型的变量）、函数、数据成员、结构化绑定、模板形参对象都是。只要它是个名字，声明类型是不是 `T&&` 都不影响结论。
   例外：枚举项、非类类型的非类型模板形参、`this` 是 **prvalue**；`return x;`/`co_return x;`/`throw x;` 中可隐式移动的局部变量是 **xvalue**（C++23 起）。
2. **函数调用**（包括重载运算符、转换函数的调用）：看**返回类型**——`T&` → lvalue；`T&&`（对象类型）→ xvalue；`T` → prvalue；返回函数的右值引用 → lvalue。
3. **强制转换**（任何形式）：看**目标类型**，规则同上。例如 `static_cast<T&>(e)` 是 lvalue，`static_cast<T&&>(e)` 是 xvalue，`static_cast<T>(e)` 是 prvalue。
4. **内置运算符**：查该运算符的条款，下表列出了全部常见情形。大致规律是：算术、比较、逻辑、位运算和后置 `++`/`--` 得到 prvalue；解引用 `*p`、前置 `++`/`--`、赋值得到指代原对象的 lvalue。
5. **“继承”规则**：成员访问 `e.m`、下标 `e[i]`（数组操作数）、`.*` 继承对象表达式的 glvalue 性质——左值的成员是左值，xvalue（或被实质化的 prvalue）的成员是 xvalue。静态数据成员和引用成员不在此列，它们总是 lvalue。
6. **括号**不改变值类别：`(e)` 与 `e` 相同。但在 `decltype` 中括号**改变结果**——见第三节。

### 2.3 大表：表达式形式 → 值类别

| 表达式 | 类别 | 备注 / 条款 |
|---|---|---|
| 变量名 `x`（任何类型，包括 `T&&`） | lvalue | [[expr.prim.id.unqual]] |
| `return x;` 中可隐式移动的 `x` | xvalue | C++23 起（[[P2266R3]]） |
| 函数名 `f` | lvalue | |
| 枚举项 `Red` | prvalue | |
| 非类型模板形参 `N`（非类类型） | prvalue | 类类型的模板形参对象是 lvalue |
| `this` | prvalue | [[expr.prim.this]] |
| 字符串字面量 `"abc"` | **lvalue** | 它是一个静态存储期的数组对象，`&"abc"` 合法 |
| 其他字面量 `42`、`'a'`、`nullptr`、`true` | prvalue | |
| 用户定义字面量 `"x"s` | 按 `operator""` 的返回类型 | |
| lambda 表达式 | prvalue | 闭包对象的“配方” |
| `T(args)`、`T{args}` | prvalue | `T&(x)` 之类按引用规则 |
| `f()` | 按返回类型 | [[expr.call]] |
| `static_cast<T&>(e)` / `<T&&>` / `<T>` | lvalue / xvalue / prvalue | `T&&` 为函数类型的右值引用时是 lvalue |
| `std::move(x)` | xvalue | 就是 `static_cast<T&&>` |
| `std::forward<T>(x)` | `T` 为左值引用时 lvalue，否则 xvalue | |
| `*p` | lvalue | [[expr.unary.op]] |
| `&x` | prvalue | |
| `++i`、`--i` | lvalue | [[expr.pre.incr]]，指代 `i` 本身 |
| `i++`、`i--` | prvalue | [[expr.post.incr]]，值是修改前的旧值 |
| `a = b`、`a += b` | lvalue | [[expr.assign]]，指代左操作数 |
| `a + b`、`-a`、`a < b`、`!a`、`a & b` | prvalue | 内置算术/比较/逻辑/位运算 |
| `a[i]`（内置） | 数组操作数为 xvalue 时 xvalue，否则 lvalue | [[expr.sub]] |
| `e.m`（非静态、非引用数据成员） | 与 `e` 同：lvalue 或 xvalue | `e` 为 prvalue 时先实质化 → xvalue |
| `e.m`（引用成员） | lvalue | [[expr.ref]] |
| `e.s`（静态数据成员） | lvalue | |
| `e.f`（非静态成员函数） | prvalue | 只能立即被调用 |
| `p->m` | lvalue | 等价于 `(*p).m` |
| `e.*pm`（数据成员指针） | 与 `e` 同 | [[expr.mptr.oper]] |
| `p->*pm`（数据成员指针） | lvalue | |
| `c ? a : b` | 两者同为同类型 glvalue 时取其类别；否则 prvalue | [[expr.cond]] |
| `a, b` | 与 `b` 相同 | [[expr.comma]] |
| `throw e` | prvalue（`void`） | |
| `typeid(e)` | lvalue | 指代一个 `const std::type_info` 对象 |
| `sizeof e`、`alignof(T)`、`noexcept(e)` | prvalue | |
| `new T` | prvalue | |
| `co_await e` | 按 `await_resume()` 的返回类型 | [[expr.await]] |

可以把这张表与 [[basic.lval#4]] 的 xvalue 清单对照：**xvalue 只来自三种途径**：

1. 返回或转换到对象的右值引用（函数调用、`static_cast<T&&>`、`std::move`）；
2. 可隐式移动的名字（`return x;` 等）；
3. 从 xvalue（或被实质化的 prvalue）“继承”来的子对象访问。

## 三、decltype 与值类别

[[dcl.type.decltype]] 有两套规则，区别就在有没有那层括号：

| 形式 | 规则 | 结果 |
|---|---|---|
| `decltype(name)`、`decltype(e.member)`（**不加括号**） | 实体的**声明类型** | 可能是引用，也可能不是；与值类别无关 |
| `decltype(expr)`（其他所有情形，包括 `decltype((name))`） | 表达式的**类型 + 值类别** | xvalue → `T&&`，lvalue → `T&`，prvalue → `T` |

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

`decltype(auto)` 沿用同一套规则，于是有了那个经典陷阱：`return` 语句里多写一对括号，返回类型就从值变成了引用。

```cpp ok
int g;
decltype(auto) f1() { return g; }     // int
decltype(auto) f2() { return (g); }   // int&——加了括号，返回了引用
// decltype(auto) f3() { int x = 0; return (x); }  // 返回悬垂引用（C++23 起是 int&&，仍悬垂）
```

## 四、引用绑定：值类别的主要消费者

编译器给每个表达式定下值类别，最主要的用处是决定**引用绑定**和**重载决议**：

| 引用类型 | 可绑定的表达式 | 说明（[[dcl.init.ref]]） |
|---|---|---|
| `T&` | 非 const 的 `T` 左值 | 不能绑定右值（经典的“非 const 引用不能绑定临时量”） |
| `const T&` | 任何 `T` 表达式（lvalue、xvalue、prvalue）；可转换为 `T` 的表达式 | 对 prvalue 实质化临时量，并延长其寿命 |
| `T&&` | `T` 的 rvalue（xvalue、prvalue）；可转换为 `T` 的表达式（产生新的临时量） | **不能**直接绑定左值；对 prvalue 同样实质化并延长寿命 |
| `auto&&`、模板 `T&&`（转发引用） | 任何表达式 | 左值时 `T` 推导为 `U&`，引用折叠为 `U&`；右值时 `T` 推导为 `U`，形参为 `U&&` |

重载决议中，当两个候选只在 `T&` / `T&&` 上有区别时，**rvalue 优先绑定 `&&`**，lvalue 只能选 `&`（[[over.ics.rank]]）。移动构造函数和复制构造函数之间的选择就是靠这条规则完成的：

```cpp run title="overload.cpp" ok
#include <cstdio>
#include <utility>

void take(const int&) { std::puts("const&"); }
void take(int&&)      { std::puts("&&"); }

int main() {
    int i = 0;
    take(i);              // const&：左值不能绑定 &&
    take(1);              // &&：prvalue，实质化后绑定
    take(std::move(i));   // &&：xvalue
    int&& r = 2;
    take(r);              // const&：r 是左值！
}
```

## 五、std::move 与 std::forward：只是强制转换

### std::move

`std::move` 什么也不移动，运行时不做任何事，只是一次编译期的类型转换。它的全部实现（去掉 constexpr/noexcept 修饰）就是：

```cpp
#include <type_traits>
template<class T>
std::remove_reference_t<T>&& move(T&& t) noexcept {
    return static_cast<std::remove_reference_t<T>&&>(t);
}
```

它把任意表达式**转换为 xvalue**，从而让重载决议选中接受 `T&&` 的函数（如移动构造函数、移动赋值运算符）。真正转移资源的是那个被选中的函数。由此有三个推论：

- 对 `const` 对象 `std::move` 得到 `const T&&`，绑不上移动构造函数的 `T&&` 形参，于是重载决议选中 `const T&` 的复制构造函数，**静默地退化为复制**。
- 对没有移动构造函数的类型 `std::move` 同样退化为复制。
- 对 `int`、指针之类的标量 `std::move` 毫无作用，结果就是复制一次值。

### std::forward 与转发引用

在 `template<class T> void f(T&& x)` 中，`x` 是**转发引用**：传入左值时 `T = U&`，`T&&` 折叠为 `U&`；传入右值时 `T = U`。但无论哪种情况，**在函数体内表达式 `x` 都是左值**（它有名字）。如果直接把 `x` 传给下一层函数，调用方原本传入右值这一信息就丢了。`std::forward<T>(x)` 利用 `T` 里记录的信息，把它“恢复”成原来的类别：

```cpp run title="forward.cpp" ok
#include <cstdio>
#include <utility>

void sink(int&)  { std::puts("lvalue"); }
void sink(int&&) { std::puts("rvalue"); }

template<class T>
void relay(T&& x) {
    sink(x);                     // 总是 lvalue
    sink(std::forward<T>(x));    // 恢复原类别
}

int main() {
    int i = 0;
    relay(i);    // lvalue lvalue
    relay(1);    // lvalue rvalue
}
```

`std::forward<T>(x)` 本质上也只是 `static_cast<T&&>(x)`：

- 传入左值时 `T = U&`，`U& &&` 折叠为 `U&`，结果是 lvalue；
- 传入右值时 `T = U`，`T&&` 就是 `U&&`，结果是 xvalue。

## 六、保证复制消除（C++17）

在 C++14 及以前，返回值优化（RVO）只是标准**允许**的优化：即使编译器实际上省略了复制，被省略的复制/移动构造函数也必须可用。所以对于既不能复制也不能移动的类型（如 `std::mutex`、`std::atomic`），连“按值返回一个新对象”的工厂函数都写不出来。

C++17 改变了模型：prvalue 只是配方，**用 prvalue 初始化同类型的对象时，配方直接在目标对象上执行**——中间没有临时量，因此语义上也没有复制或移动，不需要复制/移动构造函数（[[dcl.init.general#15]]、[[class.copy.elision]]）：

```cpp ok
#include <atomic>
#include <mutex>

struct Pinned {
    Pinned() = default;
    Pinned(const Pinned&) = delete;
    Pinned(Pinned&&) = delete;
};

Pinned make() { return Pinned{}; }   // OK：prvalue 直接初始化调用方的对象
Pinned a = make();                   // OK
Pinned b = Pinned(Pinned(Pinned())); // OK：只有一个对象
auto c = std::atomic<int>(0);        // OK：C++14 中非良构（atomic 不可复制）
std::mutex m = std::mutex();         // OK：同理
```

哪些在保证之列、哪些**不**在：

| 情形 | C++17 起 |
|---|---|
| `return T(...);`（返回 prvalue） | **保证**无复制/移动 |
| `T x = T(...);` | **保证** |
| `return local;`（具名返回值，NRVO） | **允许**省略，但不保证；类型必须可移动或可复制，否则编译失败 |
| `return std::move(local);` | **阻止** NRVO，强制一次移动（Clang 的 `-Wpessimizing-move` 会警告） |
| `return param;`（函数形参） | 不能 NRVO；但会隐式移动 |
| `T x = cond ? T(1) : T(2);` | 保证（条件表达式的结果是 prvalue） |

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

## 七、临时量与生命周期延长

prvalue 被**实质化**（temporary materialization）为临时对象的时机见 [[class.temporary#2]]；临时对象通常在它所在的**完整表达式结束时**销毁。把临时对象**直接**绑定到引用（`const T&` 或 `T&&`）会把它的寿命延长到与引用相同——但“直接”的含义很窄，稍不注意就会得到悬垂引用：

```cpp run title="lifetime.cpp" ub
#include <cstdio>
#include <string>
#include <utility>

struct A { std::string s = "a string long enough to live on the heap"; };
A make() { return {}; }

int main() {
    const auto& r1 = make().s;           // OK：成员访问作用于被实质化的临时量，延长整个临时对象
    auto&& r2 = std::move(make());       // 悬垂：std::move 的返回值不是临时量本身
    std::printf("%zu\n", r1.size());     // OK
    std::printf("%zu\n", r2.s.size());   // UB：临时对象已在上一个完整表达式结束时销毁
}
```

`r2` 的问题在于：`std::move` 是一次函数调用，`r2` 绑定的是它返回的引用，而不是临时对象本身，所以不会触发寿命延长。ASan 会在最后一行报告 `stack-use-after-scope`；Clang 也会在编译期给出 `-Wdangling` 警告。

经验法则：**引用绑定到“实质化本身”或其子对象（经由 `.`、`[]`、`?:`、`,`、某些强制转换）时延长；经由任何函数调用（包括 `std::move`、`std::min`、成员函数返回 `*this`）时不延长**。后一种情况下，临时对象在完整表达式结束时照常销毁，引用随即悬垂。

## 八、常见误解

!!! pitfall "“右值引用是右值”"
    类型与值类别是两回事。`int&& r = 1;` 中，`r` 的**类型**是 `int&&`，但**表达式** `r` 的类别是 **lvalue**（[[expr.type#1]] 甚至会先把它的类型调整为 `int`）。简单记法：“具名即左值”。

!!! pitfall "“rvalue 不能取地址，所以不能被修改”"
    xvalue 是 rvalue，但它指代一个真实的对象：`std::move(v).push_back(1)` 合法地修改了 `v`。类类型的 prvalue 也能调用非 const 成员函数：`std::string().append("x")`。“不能修改”只针对**内置**运算符：`f() = 1`（`int f()`）非良构（[[basic.lval#10]]）。

!!! pitfall "“字面量都是 rvalue”"
    字符串字面量是 **lvalue**：它是一个静态存储期的数组对象，`&"abc"` 合法，类型是 `const char(*)[4]`。

!!! pitfall "“std::move 之后对象就空了”"
    `std::move` 本身不改变对象。被移动后的标准库对象处于“有效但未指定”的状态；被移动后的 `int` 值不变。

!!! pitfall "“prvalue 就是临时对象”"
    C++17 起，prvalue 不是对象；只有在实质化时才产生临时对象。`T x = T();` 中根本没有临时对象。

!!! pitfall "“返回时加 std::move 更快”"
    `return std::move(local);` 把一个本可 NRVO（零开销）或隐式移动的表达式变成 xvalue，**禁止**了 NRVO，换来一次本可避免的移动。C++11 起 `return local;` 就会隐式移动，C++20/23 扩展了这一规则；返回局部变量时直接写 `return local;` 即可。

!!! pitfall "“xvalue 一定快要死了”"
    xvalue 只表示“**允许**复用其资源”，不表示它真的即将销毁。`std::move(global)` 是一个指代全局对象的 xvalue，它活到程序结束。

## 九、历史一览

!!! history
    - **C++98**：只有 lvalue/rvalue。`const T&` 可以绑定 rvalue，但无法区分“可偷”的对象。
    - **C++11**：右值引用与移动语义需要“有身份但可偷”的类别，[[N3055]] 引入 xvalue，并命名 glvalue/prvalue。
    - **C++14**：无实质变化。
    - **C++17**：[[P0135R1]] 让 prvalue 成为“初始化配方”，引入结果对象与临时量实质化，复制消除成为保证。
    - **C++20**：隐式移动扩展到更多场景（如右值引用局部变量、`throw` 操作数），见 [[P1825R0]]。
    - **C++23**：[[P2266R3]]：可隐式移动的名字在 `return` 中直接是 xvalue，`decltype(auto)` 的结果随之改变。
    - **C++26**：拼接表达式（反射）可以指代非静态数据成员、直接基类关系，均为 lvalue；“glvalue”的定义随之扩展。

## 十、思考题

!!! question "1. 设 `std::vector<std::string> v;`。`std::move(v)[0]` 是什么类别？`std::move(v[0])` 呢？"

<details markdown="1">
<summary>答案</summary>

`std::move(v)[0]`：**lvalue**。`vector::operator[]` 是重载运算符，返回 `reference`（即 `std::string&`）；按“函数调用看返回类型”的规则，结果是 lvalue——尽管 `v` 被转换成了 xvalue。内置 `[]` 对 xvalue 数组产生 xvalue，但标准容器的 `operator[]` 没有按值类别重载（C++23 的“推导 this”可以写出这样的重载，但标准库没有这样做）。

`std::move(v[0])`：**xvalue**，类型 `std::string`。这才是“移动容器中的某个元素”的正确写法。
</details>

!!! question "2. 为什么 `template<class T> void f(T&& x)` 中，`f(std::move(i))` 推导出 `T = int`，而 `f(i)` 推导出 `T = int&`？推导规则看的是什么？"

<details markdown="1">
<summary>答案</summary>

看的是实参表达式的**值类别**。[[temp.deduct.call]] 对转发引用有特殊规则：若实参是**左值**，用“`A` 的左值引用”代替 `A` 进行推导，于是 `T = int&`，`T&&` 经引用折叠为 `int&`。若实参是 rvalue（xvalue 或 prvalue），按普通规则 `T = int`，形参类型为 `int&&`。`std::forward<T>` 之所以能“记住”原始类别，信息就来自这里推导出的 `T`。
</details>

!!! question "3. `const std::string& r = std::string("a") + "b";` 安全吗？`const char* p = (std::string("a") + "b").c_str();` 呢？"

<details markdown="1">
<summary>答案</summary>

第一个安全：`operator+` 返回 `std::string` prvalue，绑定到 `const std::string&` 时实质化并**延长**临时量寿命至 `r` 的作用域结束。

第二个悬垂：临时 `std::string` 被实质化后调用 `c_str()`，它是函数调用，返回的是指针而非引用绑定，不会延长任何寿命；完整表达式结束时临时对象被销毁，`p` 指向已释放的缓冲区，之后通过 `p` 读取是未定义行为。
</details>

## 小结

!!! summary
    - 判定：名字 → lvalue（例外：枚举项、`this`、非类非类型模板形参是 prvalue；`return` 中可移动的局部变量是 xvalue）；函数调用与强制转换 → 看返回/目标类型；内置运算符 → 查表；子对象访问 → 继承。
    - 探针：`decltype((e))` 给出 `T&` / `T&&` / `T`。
    - `std::move` = 转为 xvalue；`std::forward<T>` = 按 `T` 恢复类别；二者都只是 `static_cast`，没有运行时开销。
    - C++17：prvalue 是配方，结果对象由上下文提供；用 prvalue 初始化同类型对象没有复制。
    - 生命周期延长只对“直接”绑定临时量（及其子对象）有效，经过函数调用即失效。
