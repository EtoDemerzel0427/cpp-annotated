---
title: 显然常量求值与常量析构
summary: 哪些表达式必须在翻译期求值（显然常量求值），这正是 std::is_constant_evaluated() 与 if consteval 观察的属性；潜在常量求值与为常量求值所需决定 constexpr 函数何时被实例化；常量析构
status: done
papers: P0595R2, P1938R3, P0784R7
related: expr.const.init, expr.const.imm, meta.const.eval, stmt.if, temp.inst, dcl.constexpr, basic.start.static, topics/compile-time-programming
tags: 常量求值, is_constant_evaluated, 实例化
updated: 2026-10-17
---

本节收集了 [expr.const] 中三个在其他条款中使用的定义：

1. 显然常量求值（manifestly constant-evaluated，¶1）：语言规定必须在翻译期求值的表达式。`std::is_constant_evaluated()` 与 `if consteval` 正是据此返回 true 或选择分支；立即函数语境也以它为基础（[[expr.const.imm#1.2]]）。
2. 潜在常量求值（potentially constant-evaluated）与为常量求值所需（needed for constant evaluation，¶2）：决定 constexpr 函数模板何时实例化、constexpr 函数何时隐式定义（[[temp.inst]]、[[class.default.ctor]] 等）。
3. 常量析构（constant destruction，¶3）：constexpr 变量的析构也必须能在编译期完成（[[dcl.constexpr#6]]）。

## 显然常量求值（¶1）

如果一个表达式或转换属于下列情形之一，它就是**显然常量求值**的：

| 条目 | 情形 | 例子 |
|---|---|---|
| ¶1.1 | 语法上的 *constant-expression* | 数组边界、`case` 标签、模板实参、`static_assert` 条件、`alignas`、位域宽度、枚举量初值、`noexcept(...)` |
| ¶1.2 | constexpr if 语句的条件 | `if constexpr (cond)` |
| ¶1.3 | *consteval-block-declaration* 对应的表达式 {{c++26}} | `consteval { ... }` |
| ¶1.4 | 立即调用 | 对 consteval 函数的调用（不在立即函数语境中时） |
| ¶1.5 | 为判断原子约束是否满足而代入后的结果 | `requires (sizeof(T) > 4)` 中的约束表达式 |
| ¶1.6 | 可用于常量表达式的变量或具有常量初始化的变量的初始化器 | `constexpr int x = ...;`、`const int n = ...;`（成功时）、`constinit` 变量、常量初始化的静态变量 |

前五项都由语法位置决定，一看便知。**微妙之处都来自 ¶1.6**：一个变量的初始化器是否显然常量求值，取决于这个变量最终是否常量初始化，而这又取决于初始化器能否作为常量表达式求值，形成了循环。标准通过 [[expr.const.init#4]] 注 1 和脚注 63 打破这个循环：判断时，对初始化器做一次概念性的试算（notional evaluation），其中 `std::is_constant_evaluated()` 为 true，契约断言按 ignore 语义处理。试算成功，变量就是常量初始化的，初始化器就是显然常量求值的；试算失败，变量就是动态初始化的，初始化器在运行期求值，此时 `is_constant_evaluated()` 为 false。

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

- `a`：试算时 `is_constant_evaluated()` 为 true，选中 `y`，读取非常量 `y` 失败，所以不是常量初始化，而是动态初始化；运行期 `is_constant_evaluated()` 为 false，选中 `1`。因此 `a == 1`，但 `a` 不是 constant-initialized，**不可用于常量表达式**，`double z[a]` 是错误的。
- `b`：试算选中 `2`，成功，所以静态初始化为 2。
- `c`：试算时整个初始化器 `y + ...` 读取 `y` 失败，所以是动态初始化，运行期取 `y + y`。注意 `c` 不是 `const`，但 ¶1.6 中的具有常量初始化适用于任何静态存储期变量，所以这里也做了试算。
- `f()` 中的 `n`：`n` 是 const int，如果常量初始化就可用于常量表达式。它的初始化器满足 ¶1.6，是显然常量求值的，所以即使 `f()` 在运行期调用，`n` 也是 13。`arr` 的大小在编译期就确定为 13，这也是 `char arr[n]` 合法的原因。
- `f()` 中的 `m`：`m` 不是 const，其初始化器不是显然常量求值的，`is_constant_evaluated()` 的值取决于外层的 `f()` 是否处于常量求值中。
  - `int p = f();`：`p` 是静态存储期变量，试算 `f()` 成功（`m = 13`，返回 `13 + 13 = 26`），所以是常量初始化，`p == 26`。
  - `int q = p + f();`：读取 `p`（非 const）使试算失败，所以是动态初始化。运行期调用 `f()`，`m = 17`，`q = 26 + 17 + 13 = 56`。

!!! warning "Clang 的 `-Wconstant-evaluated` 并不总是对的"
    Clang 对 `a`、`b`、`n` 这几行都会警告 "'std::is_constant_evaluated' will always evaluate to 'true' in a manifestly constant-evaluated expression"。对 `a` 而言这是错误的：`a` 最终动态初始化为 1（本站用 Clang 23 运行，确认 `a == 1`、`b == 2`、`p == 26`、`q == 56`）。这条警告的价值在于提示这里的写法很可能不是你想要的，而不是精确描述语义。

### 未求值操作数中也会求值

注 1：除 *static_assert-message* 外，显然常量求值的表达式即使出现在未求值操作数中也会被求值（[[expr.context]]）。

```cpp error
template<class T> constexpr int f() { return T::value; }
constexpr int g() { return sizeof(char[f<int>()]); }   // error: 数组边界是显然常量求值的，
                                                       //        即使在 sizeof 里也要求值 f<int>()
```

`sizeof` 的操作数不求值，但数组边界 `f<int>()` 是 *constant-expression*，必须求出它的值才能确定类型 `char[N]`。于是 `f<int>` 被实例化并求值，`int::value` 出错。*static_assert-message* 之所以例外，是因为 C++26 允许用户生成的 `static_assert` 消息（[[dcl.pre#13]]），这个消息只在断言失败时才需要求值。

### 为什么 `is_constant_evaluated` 设计成这样

C++20 引入 `std::is_constant_evaluated()`（[[P0595R2]]）时，委员会考虑过更直观的语义，即告诉你当前是否在编译期执行。但这无法实现：编译器优化时可以把任何运行期计算折叠为常量，当前是否在编译期执行会随优化级别而变化。所以它改为观察一个由语言确定的属性：当前求值是否是显然常量求值（或位于其内部）。代价就是上面这些反直觉的情形，尤其是 ¶1.6 的试算。

C++23 的 `if consteval`（[[P1938R3]]）观察的是同一属性，但额外提供了立即函数语境（见 [[expr.const.imm]]）。现在 `is_constant_evaluated()` 规定为等价于 `if consteval { return true; } else { return false; }`（[[meta.const.eval#1]]）。

!!! pitfall "`is_constant_evaluated()` 的三个常见陷阱"
    1. `if constexpr (std::is_constant_evaluated())`：条件是显然常量求值的（¶1.2），永远为 true。
    2. 在显然常量求值的初始化器中直接使用，如 `constexpr bool b = std::is_constant_evaluated();`：结果永远为 true，不提供任何信息。
    3. 试算导致的分叉：`const int a = is_constant_evaluated() ? runtime() : 1;` 在运行期得到 1，而你很可能以为得到的是 `runtime()` 的结果。因此，`is_constant_evaluated()` 应当只出现在 **constexpr 函数体内**，用于在同一算法的编译期实现与运行期实现之间切换，并且两个分支必须计算**相同的结果**。

## 潜在常量求值与为常量求值所需（¶2）

如果一个表达式或转换属于下列情形之一，它就是**潜在常量求值**（potentially constant-evaluated）的：

- ¶2.1 显然常量求值的表达式；
- ¶2.2 潜在求值的表达式（[[basic.def.odr]]）；
- ¶2.3 *braced-init-list* 的直接子表达式（脚注 64：有时需要常量求值来判断是否发生窄化）；
- ¶2.4 出现在模板化实体中的 `& cast-expression` 形式的表达式（脚注 65：有时需要常量求值来判断该表达式是否值依赖，见 [[temp.dep.constexpr]]）；
- ¶2.5 上述任一者的潜在求值子表达式。

如果一个函数或变量属于下列情形之一，它就是**为常量求值所需**（needed for constant evaluation）的：

- ¶2.6 被某个潜在常量求值的表达式命名的 constexpr 函数；
- ¶2.7 被某个潜在常量求值的表达式命名的 potentially-constant 变量（[[expr.const.init#6]]）。

这组定义在别处使用：[[temp.inst]] 规定，为常量求值所需的 constexpr 函数模板特化会被隐式实例化（即使它没有被 odr-use）；预置的特殊成员函数如果为常量求值所需，会被隐式定义；变量模板同理。

为什么不直接用 odr-use？因为有些上下文不 odr-use 函数，却需要它的定义来求值：

```cpp
template<class T> constexpr int f() { return T::value; }

decltype(f<int>()) x = 0;              // OK：decltype 的操作数是未求值操作数，不是潜在常量求值
                                       //     f<int> 不需要定义，不实例化

using A = decltype(char{f<int>()});    // error: braced-init-list 的直接子表达式是潜在常量求值的（¶2.3），
                                       //        需要知道 f<int>() 的值来判断 int → char 是否窄化
                                       //        → f<int> 被实例化 → int::value 出错
```

第二个例子正是脚注 64 所说的情形。在列表初始化中，`int` → `char` 是否窄化取决于源值是否是常量且可以表示（[[dcl.init.list]]），所以即使在 `decltype` 中，编译器也必须实例化 `f<int>()` 并尝试求值。

!!! lawyer "实例化的副作用是可观察的"
    实例化一个函数模板可能触发硬错误（如上例），可能实例化其他模板，甚至可能（借助友元注入一类技巧）改变后续代码的含义。所以哪些表达式会导致实例化不是实现细节，而是语言必须精确规定的内容，这正是 ¶2 存在的理由。

## 常量析构（¶3）

如果满足下列条件之一，就说对象 a 具有**常量析构**（constant destruction）：

- ¶3.1 它不是类类型，也不是类类型的（多维）数组；或
- ¶3.2 它是类类型或其（多维）数组，该类有 constexpr 析构函数（[[dcl.constexpr]]），并且对于一个假想的、唯一作用是销毁 a 的表达式 E，如果把 a 及其非 mutable 子对象（不含 mutable 子对象）的生命期视为始于 E 之内，E 是核心常量表达式。

[[dcl.constexpr#6]] 要求 constexpr 变量（以及 constexpr 引用绑定的临时对象）必须具有常量析构。

为什么需要这个要求？C++20 允许 constexpr 析构函数之后，constexpr 变量的析构函数可以做 constexpr 允许的任何事。如果析构过程修改了外部对象，或者释放了不是在本次求值中分配的内存，就无法在编译期模拟它。¶3.2 把生命期视为始于 E 之内，使析构函数可以修改 a 自己的（非 mutable）成员，毕竟 a 正在被销毁。mutable 子对象则不视为始于 E 之内，因为 constexpr 对象的 mutable 成员在运行期可以改变，编译期无法知道析构时它的值。

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

常量析构也为禁止非瞬时分配多加了一层保障：

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
    具有常量析构的静态存储期对象，其析构在语义上仍然在运行期发生，但效果只作用于对象自身（非 mutable 成员），没有可观察的副作用，所以编译器可以省去析构注册（本站测试的 Clang 23 在 `-O2` 下没有为上面的 `t2` 生成 `__cxa_atexit` 注册）。这也是 `constinit` 变量配合平凡析构或常量析构可以完全避免静态析构顺序问题的原因。

## 历史与演进

!!! history "演进"
    - C++11–17：只有常量表达式的语法上下文；没有 `is_constant_evaluated`，也就不需要精确定义显然常量求值。实例化时机由 odr-use 与少数特例决定。
    - C++20：[[P0595R2]] 引入 `std::is_constant_evaluated()` 与显然常量求值；同期为了支持 constexpr 析构函数（[[P0784R7]]）引入常量析构；潜在常量求值与为常量求值所需的措辞也在这一时期整理定型，用于规定实例化。
    - C++23：[[P1938R3]] 引入 `if consteval`；立即函数语境的定义引用了显然常量求值。
    - C++26：¶1.3 引入 consteval 块；试算中忽略契约断言（脚注 63）。

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

- `u`：试算 `pick()` 成功（得 1），所以是常量初始化，`u == 1`，属于静态初始化。
- `v`：试算时读取 `rt` 失败，所以是动态初始化，运行期 `pick()` 返回 2，`v == 2`。
- `w`：`0 * rt` 仍然要读取 `rt`（左值到右值转换），试算失败，所以是动态初始化，`w == 2`，而且 `w` 不可用于常量表达式。

由此可见，初始化器中任何一处非常量读取都会使整个初始化变成动态初始化，从而改变 `is_constant_evaluated()` 的结果。
</details>

!!! question "思考题 2"
    为什么在常量析构的定义中，mutable 子对象的生命期**不**视为始于 E 之内？

<details markdown="1">
<summary>答案</summary>

constexpr 对象的 mutable 成员不是常量，程序可以在运行期通过 const 引用修改它，这正是 mutable 的意义。编译器在翻译期模拟析构时，并不知道运行期结束时 mutable 成员的值；如果允许析构函数读写它，编译期模拟的析构与运行期真实的析构就可能不一致。因此标准把 mutable 子对象当作外部对象：析构函数如果读写它，对象就不具有常量析构。
</details>

## 小结

| 定义 | 判定 | 用途 |
|---|---|---|
| 显然常量求值 | *constant-expression*、`if constexpr` 条件、consteval 块、立即调用、约束代入、常量初始化变量的初始化器 | `is_constant_evaluated()`、`if consteval`、立即函数语境 |
| 潜在常量求值 | 显然常量求值 + 潜在求值 + 花括号列表直接子表达式 + 模板中的 `&expr` | 判断是否为常量求值所需 |
| 为常量求值所需 | 被潜在常量求值表达式命名的 constexpr 函数 / potentially-constant 变量 | 触发实例化与隐式定义 |
| 常量析构 | 非类类型；或 constexpr 析构函数 + 析构是核心常量表达式（mutable 除外） | constexpr 变量的要求 |
