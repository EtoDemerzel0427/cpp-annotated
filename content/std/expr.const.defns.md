---
title: 显然常量求值与常量析构
summary: 哪些表达式"必须"在翻译期求值（显然常量求值）——这正是 std::is_constant_evaluated() 与 if consteval 观察的属性；潜在常量求值与"为常量求值所需"决定 constexpr 函数何时被实例化；常量析构
status: done
papers: P0595R2, P1938R3, P0784R7
related: expr.const.init, expr.const.imm, meta.const.eval, stmt.if, temp.inst, dcl.constexpr, basic.start.static, topics/compile-time-programming
tags: 常量求值, is_constant_evaluated, 实例化
updated: 2026-10-17
---

本节收集了 [expr.const] 中三个"跨条款使用"的定义：

1. **显然常量求值**（manifestly constant-evaluated，¶1）——语言规定**必须**在翻译期求值的表达式。`std::is_constant_evaluated()` 与 `if consteval` 正是根据它返回 true/选择分支；立即函数语境也以它为基础（[[expr.const.imm#1.2]]）。
2. **潜在常量求值**（potentially constant-evaluated）与**为常量求值所需**（needed for constant evaluation，¶2）——决定 constexpr 函数模板何时被**实例化**、constexpr 函数何时被**隐式定义**（[[temp.inst]]、[[class.default.ctor]] 等）。
3. **常量析构**（constant destruction，¶3）——constexpr 变量的析构也必须能在编译期完成（[[dcl.constexpr#6]]）。

## 显然常量求值（¶1）

一个表达式或转换是**显然常量求值**的，如果它是：

| 条目 | 情形 | 例子 |
|---|---|---|
| ¶1.1 | 语法上的 *constant-expression* | 数组边界、`case` 标签、模板实参、`static_assert` 条件、`alignas`、位域宽度、枚举量初值、`noexcept(...)` |
| ¶1.2 | constexpr if 语句的条件 | `if constexpr (cond)` |
| ¶1.3 | *consteval-block-declaration* 对应的表达式 {{c++26}} | `consteval { ... }` |
| ¶1.4 | 立即调用 | 对 consteval 函数的调用（不在立即函数语境中时） |
| ¶1.5 | 为判断原子约束是否满足而代入后的结果 | `requires (sizeof(T) > 4)` 中的约束表达式 |
| ¶1.6 | **可用于常量表达式**、或**具有常量初始化**的变量的初始化器 | `constexpr int x = ...;`、`const int n = ...;`（成功时）、`constinit` 变量、常量初始化的静态变量 |

前五项都是"语法位置"决定的，一目了然。**¶1.6 是一切微妙之处的来源**：一个变量的初始化器是否显然常量求值，取决于这个变量**最终**是否常量初始化——而这又取决于初始化器能否作为常量表达式求值。这是一个循环！标准通过 [[expr.const.init#4]] 注 1 和脚注 63 打破循环：判断时，对初始化器做一次**概念性的试算**（notional evaluation），其中 `std::is_constant_evaluated()` 为 true、契约断言按 ignore 语义。试算成功，变量就是常量初始化的，初始化器就是显然常量求值的；试算失败，就是动态初始化，初始化器在运行期求值，此时 `is_constant_evaluated()` 为 false。

### 标准例子精读

```cpp ok
#include <type_traits>
template<bool> struct X {};
X<std::is_constant_evaluated()> x;                      // 类型是 X<true>：模板实参（¶1.1）
int y;
const int a = std::is_constant_evaluated() ? y : 1;     // 动态初始化为 1
// double z[a];                                         // error: a 不可用于常量表达式
const int b = std::is_constant_evaluated() ? 2 : y;     // 静态初始化为 2
int c = y + (std::is_constant_evaluated() ? 2 : y);     // 动态初始化为 y + y

constexpr int f() {
    const int n = std::is_constant_evaluated() ? 13 : 17;   // n 是 13
    int m = std::is_constant_evaluated() ? 13 : 17;         // m 可能是 13 或 17
    char arr[n] = {};                                       // char[13]
    return m + sizeof(arr);
}
int p = f();             // m 是 13；p 初始化为 26
int q = p + f();         // 这次调用中 m 是 17；q 初始化为 56
```

逐个分析：

- **`a`**：试算时 `is_constant_evaluated()` 为 true，选中 `y`，读取非常量 `y` 失败 → 不是常量初始化 → 动态初始化；运行期 `is_constant_evaluated()` 为 false，选中 `1`。所以 `a == 1`，但 `a` **不可用于常量表达式**（它不是 constant-initialized），`double z[a]` 错误。
- **`b`**：试算选中 `2`，成功 → 静态初始化为 2。
- **`c`**：试算时整个初始化器 `y + ...` 读 `y` 失败 → 动态初始化，运行期取 `y + y`。注意 `c` 不是 `const`，但 ¶1.6 的"具有常量初始化"对任何静态存储期变量都适用，所以这里也进行了试算。
- **`f()` 中的 `n`**：`n` 是 const int，若常量初始化则可用于常量表达式——它的初始化器满足 ¶1.6，是显然常量求值的，**即使 `f()` 在运行期被调用**，`n` 也是 13（`arr` 的大小在编译期就确定为 13，这也是 `char arr[n]` 合法的原因）。
- **`f()` 中的 `m`**：`m` 不是 const，其初始化器不是显然常量求值的；`is_constant_evaluated()` 的值取决于**外层** `f()` 是否在常量求值中。
  - `int p = f();`：`p` 是静态存储期变量，试算 `f()` 成功（`m = 13`，返回 `13 + 13 = 26`）→ 常量初始化，`p == 26`。
  - `int q = p + f();`：读 `p`（非 const）使试算失败 → 动态初始化，运行期调用 `f()`，`m = 17`，`q = 26 + 17 + 13 = 56`。

!!! warning "Clang 的 `-Wconstant-evaluated` 并不总是对的"
    Clang 对 `a`、`b`、`n` 这几行都会警告 "'std::is_constant_evaluated' will always evaluate to 'true' in a manifestly constant-evaluated expression"。对 `a` 而言这是错误的：`a` 最终动态初始化为 1（本站用 Clang 23 运行确认 `a == 1`、`b == 2`、`p == 26`、`q == 56`）。警告的价值在于提示"这里很可能不是你想要的"，而非精确描述语义。

### 未求值操作数中也会求值

注 1：除了 *static_assert-message* 之外，显然常量求值的表达式**即使出现在未求值操作数中也会被求值**（[[expr.context]]）。

```cpp error
template<class T> constexpr int f() { return T::value; }
constexpr int g() { return sizeof(char[f<int>()]); }   // error: 数组边界是显然常量求值的，
                                                       //        即使在 sizeof 里也要求值 f<int>()
```

`sizeof` 的操作数不求值，但数组边界 `f<int>()` 是 *constant-expression*，必须求出值才能确定类型 `char[N]`，于是 `f<int>` 被实例化并求值，`int::value` 出错。*static_assert-message* 例外是因为 C++26 允许用户生成的 `static_assert` 消息（[[dcl.pre#13]]），它只在断言**失败**时才需要求值。

### 为什么 `is_constant_evaluated` 设计成这样

C++20 引入 `std::is_constant_evaluated()`（[[P0595R2]]）时，委员会考虑过"它告诉你当前是否在编译期执行"这种更直观的语义，但那是不可实现的：编译器可以在优化时把任何运行期计算折叠为常量，"当前是否在编译期执行"随优化级别变化。于是改为观察一个**语言层面确定的属性**：当前求值是否是显然常量求值（或其内部）。代价就是上面这些反直觉的情形——尤其是 ¶1.6 的"试算"。

C++23 的 `if consteval`（[[P1938R3]]）观察的是同一属性，但额外提供了立即函数语境（见 [[expr.const.imm]]）。现在 `is_constant_evaluated()` 被规定为等价于 `if consteval { return true; } else { return false; }`（[[meta.const.eval#1]]）。

!!! pitfall "`is_constant_evaluated()` 的三个经典陷阱"
    1. **`if constexpr (std::is_constant_evaluated())`**：条件是显然常量求值的（¶1.2），永远为 true。
    2. **在显然常量求值的初始化器中直接使用**：如 `constexpr bool b = std::is_constant_evaluated();`，永远为 true，毫无信息。
    3. **试算导致的分叉**：`const int a = is_constant_evaluated() ? runtime() : 1;` 运行期得到 1，而你很可能以为是 `runtime()`。规则：`is_constant_evaluated()` 应当只出现在 **constexpr 函数体内**、用于在"同一算法的编译期实现与运行期实现"之间切换，两个分支必须计算**相同的结果**。

## 潜在常量求值与"为常量求值所需"（¶2）

一个表达式或转换是**潜在常量求值**（potentially constant-evaluated）的，如果它是：

- ¶2.1 显然常量求值的表达式；
- ¶2.2 潜在求值的表达式（[[basic.def.odr]]）；
- ¶2.3 *braced-init-list* 的直接子表达式（脚注 64：有时需要常量求值来判断是否发生窄化）；
- ¶2.4 出现在模板化实体中的 `& cast-expression` 形式的表达式（脚注 65：有时需要常量求值来判断该表达式是否值依赖，见 [[temp.dep.constexpr]]）；
- ¶2.5 上述任一者的潜在求值子表达式。

一个函数或变量**为常量求值所需**（needed for constant evaluation），如果它是：

- ¶2.6 被某个潜在常量求值的表达式**命名**的 constexpr 函数；
- ¶2.7 被某个潜在常量求值的表达式命名的 **potentially-constant** 变量（[[expr.const.init#6]]）。

这组定义的用途在别处：[[temp.inst]] 规定，为常量求值所需的 constexpr 函数模板特化会被**隐式实例化**（即使它没有被 odr-use）；预置的特殊成员函数如果为常量求值所需，会被隐式定义；变量模板同理。

为什么不直接用 odr-use？因为有些上下文不 odr-use 函数，却需要它的**定义**来求值：

```cpp
template<class T> constexpr int f() { return T::value; }

decltype(f<int>()) x = 0;              // OK：decltype 的操作数是未求值操作数，不是潜在常量求值
                                       //     f<int> 不需要定义，不实例化

using A = decltype(char{f<int>()});    // error: braced-init-list 的直接子表达式是潜在常量求值的（¶2.3），
                                       //        需要知道 f<int>() 的值来判断 int → char 是否窄化
                                       //        → f<int> 被实例化 → int::value 出错
```

第二个例子正是脚注 64 所说的情形：列表初始化中，`int` → `char` 是否窄化取决于源值是否是常量且可表示（[[dcl.init.list]]），所以即便在 `decltype` 中，编译器也必须实例化并尝试求值 `f<int>()`。

!!! lawyer "实例化的副作用是可观察的"
    实例化一个函数模板可能触发硬错误（如上例）、可能实例化其他模板、甚至（借助友元注入一类技巧）改变后续代码的含义。所以"哪些表达式会导致实例化"不是实现细节，而是语言必须精确规定的东西——这就是 ¶2 存在的理由。

## 常量析构（¶3）

对象 a 具有**常量析构**（constant destruction），如果：

- ¶3.1 它不是类类型或类类型的（多维）数组；或
- ¶3.2 它是类类型或其（多维）数组，该类有 **constexpr 析构函数**（[[dcl.constexpr]]），并且对于一个假想的、唯一作用是销毁 a 的表达式 E，**如果把 a 及其非 mutable 子对象（不含 mutable 子对象）的生命期视为始于 E 之内**，E 是核心常量表达式。

[[dcl.constexpr#6]] 要求：constexpr 变量（以及 constexpr 引用绑定的临时对象）必须具有常量析构。

为什么需要？C++20 允许 constexpr 析构函数之后，constexpr 变量的析构函数可能做任意 constexpr 允许的事。如果析构过程修改了外部对象、或者释放了未在本次求值中分配的内存，它就不能在编译期"模拟"。¶3.2 的"视为生命期始于 E 之内"让析构函数可以修改 a 自己的（非 mutable）成员——毕竟它正在被销毁。而 mutable 子对象**不**被视为始于 E 之内，因为 constexpr 对象的 mutable 成员在运行期可以被改变，编译期无法知道析构时它的值。

```cpp
int g;
struct T { int* p; constexpr ~T() { *p = 0; } };
constexpr T t{&g};          // error: 析构会修改 g，g 的生命期不始于 E

struct T2 { int v; constexpr ~T2() { v = 0; } };
constexpr T2 t2{1};         // OK：修改自己的非 mutable 成员

struct M { mutable int v; constexpr ~M() { v = 0; } };
constexpr M m{1};           // error: mutable 子对象不被视为始于 E 之内

struct ND { int v; ~ND() {} };
constexpr ND nd{1};         // error: ND 不是字面类型（析构函数非 constexpr），在此之前就被 [dcl.constexpr] 拒绝
```

常量析构也是"非瞬时分配"被禁止的另一道保险：

```cpp
struct Owner {
    int* p;
    constexpr Owner() : p(new int(1)) {}
    constexpr ~Owner() { delete p; }
};
constexpr int use() { return *Owner().p; }   // OK：在同一次求值中分配并释放
static_assert(use() == 1);
constexpr Owner o;                           // error: 初始化本身就不是常量表达式——
                                             //        分配未在初始化求值中释放（[expr.const.core]/2.20）
```

!!! note "常量析构与静态析构"
    具有常量析构的静态存储期对象，其析构在运行期仍然"发生"（语义上），但它的效果只作用于对象自身（非 mutable 成员），没有可观察的副作用，编译器可以省去析构注册（本站测试的 Clang 23 在 `-O2` 下没有为上面的 `t2` 生成 `__cxa_atexit` 注册）。这也是为什么 `constinit` 变量配合平凡/常量析构可以完全避免静态析构顺序问题。

## 历史与演进

!!! history "演进"
    - **C++11–17**：只有"常量表达式"的语法上下文；没有 `is_constant_evaluated`，也就不需要"显然常量求值"的精确定义。实例化时机由 odr-use 与少数特例决定。
    - **C++20**：[[P0595R2]] 引入 `std::is_constant_evaluated()` 与"显然常量求值"；同期为了 constexpr 析构函数（[[P0784R7]]）引入"常量析构"；"潜在常量求值"与"为常量求值所需"的措辞在这一时期整理定型，用于规定实例化。
    - **C++23**：[[P1938R3]] `if consteval`；立即函数语境的定义引用显然常量求值。
    - **C++26**：¶1.3 consteval 块；契约断言在试算中被忽略（脚注 63）。

## 思考题

!!! question "思考题 1"
    下面三个变量各自的值是什么？是静态初始化还是动态初始化？

    ```cpp
    #include <type_traits>
    constexpr int pick() { return std::is_constant_evaluated() ? 1 : 2; }
    int rt = 0;
    int u = pick();
    int v = pick() + rt;
    const int w = pick() + 0 * rt;
    ```

<details markdown="1">
<summary>答案</summary>

- `u`：试算 `pick()` 成功（得 1）→ 常量初始化，`u == 1`，静态初始化。
- `v`：试算时读 `rt` 失败 → 动态初始化，运行期 `pick()` 返回 2，`v == 2`。
- `w`：`0 * rt` 仍然要读 `rt`（左值到右值转换），试算失败 → 动态初始化，`w == 2`，且 `w` 不可用于常量表达式。

教训：在初始化器中**任何**一处非常量读取都会把整个初始化变成动态初始化，从而翻转 `is_constant_evaluated()` 的结果。
</details>

!!! question "思考题 2"
    为什么常量析构的定义中，mutable 子对象的生命期**不**被视为始于 E 之内？

<details markdown="1">
<summary>答案</summary>

constexpr 对象的 mutable 成员不是常量：程序可以在运行期通过 const 引用修改它（这正是 mutable 的意义）。编译器在翻译期模拟析构时，并不知道运行期结束时 mutable 成员的值是多少；如果允许析构函数读写它，编译期的"模拟析构"与运行期真实的析构就可能不一致。因此标准把 mutable 子对象当作"外部"对象：析构函数不得读写它，否则不具有常量析构。
</details>

## 小结

| 定义 | 判定 | 用途 |
|---|---|---|
| 显然常量求值 | *constant-expression*、`if constexpr` 条件、consteval 块、立即调用、约束代入、常量初始化变量的初始化器 | `is_constant_evaluated()`、`if consteval`、立即函数语境 |
| 潜在常量求值 | 显然常量求值 + 潜在求值 + 花括号列表直接子表达式 + 模板中的 `&expr` | 判断"为常量求值所需" |
| 为常量求值所需 | 被潜在常量求值表达式命名的 constexpr 函数 / potentially-constant 变量 | 触发实例化与隐式定义 |
| 常量析构 | 非类类型；或 constexpr 析构函数 + 析构是核心常量表达式（mutable 除外） | constexpr 变量的要求 |
