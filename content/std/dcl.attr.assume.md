---
title: assume 属性
summary: [[assume(expr)]] 只能用于空语句；表达式不求值但潜在求值（会 odr-use）；若它在该点会为 true 则无效果，否则运行期未定义行为；实现可以利用它优化，也可以完全忽略
status: done
since: c++23
papers: P1774R8
related: dcl.attr.grammar, intro.defs, expr.const.core, basic.def.odr, conv.general, stmt.pre, basic.contract, utility.unreachable
tags: 属性, 优化, UB, assume
updated: 2026-10-17
---

`[[assume(expr)]];` 是 C++23 引入的**假设**（assumption）：程序员向编译器保证"在这一点，`expr` 为真"，编译器可以据此优化。它把各家编译器早已存在的内建功能——Clang 的 `__builtin_assume`、MSVC 的 `__assume`、GCC 的 `if (!(e)) __builtin_unreachable();` 惯用法——标准化成一个可移植的写法（[[P1774R8]]）。

它是标准属性中**唯一能直接引入未定义行为**的"信息性"属性之一（另一个是 `[[noreturn]]`）：假设不成立就是 UB。同时它又严格遵守"可忽略性"（[[dcl.attr.grammar#8]]）：删掉它，程序只会变得"更有定义"。

## 规则（¶1）

¶1 逐句：

1. `assume` 只能用于**空语句**（null statement）；这样的语句称为一个[[g:assumption|假设]]（assumption）。
2. 必须有参数子句，形式为 `( conditional-expression )`。
3. 表达式被**上下文转换为 `bool`**（[[conv.general]]）。
4. 表达式**不被求值**。
5. 若转换后的表达式**在假设出现的位置会求值为 `true`**，假设没有效果。
6. 否则，**求值这个假设**具有**运行期未定义行为**（runtime-undefined behavior，[[intro.defs]]）。

!!! std
    If the converted expression would evaluate to `true` at the point where the assumption appears, the assumption has no effect. Otherwise, evaluation of the assumption has runtime-undefined behavior.

    若转换后的表达式在假设出现之处会求值为 `true`，假设无效果；否则，求值该假设具有运行期未定义行为。

```cpp title="assume-basic.cpp" error
int divide_by_32(int x) {
    [[assume(x >= 0)]];          // OK
    return x / 32;
}

int g(int x) {
    [[assume(x > 0), assume(x < 10)]];   // OK: 一个属性列表中两个假设
    [[assume(x > 0 && x < 10)]];         // OK
    [[assume((x > 0, x < 10))]];         // OK 但多半不是你想要的：逗号表达式，只假设 x < 10
    [[assume(x > 0, x < 10)]];           // error: 参数必须是 conditional-expression，不能有顶层逗号
    return x;
}

int h(int x) {
    [[assume(x > 0)]] return x;          // error: 只能用于空语句
}

[[assume(true)]] int bad;                // error: 不能用于声明
```

### 为什么参数是 *conditional-expression*

语法限定为 *conditional-expression*，排除了**赋值表达式**和**逗号表达式**。`[[assume(x = 1)]]` 几乎一定是笔误（想写 `==`），而且赋值有副作用，在一个"不求值"的上下文里毫无意义；顶层逗号则会与"属性参数列表"的直觉混淆。确实想要它们时可以加括号——但加了括号也不会被求值。

### "不求值"与"会求值为 true"

第 4、5 点是理解 `assume` 的关键。表达式**从不被执行**，所以：

```cpp title="assume-not-evaluated.cpp" ok
int f(int y) {
    [[assume(++y == 43)]];   // y 不会被递增
    return y;                // 可以被替换为 return 42;
}

int main() { return f(42) - 42; }   // OK: 假设"++y == 43"在 y == 42 时会为真
```

规则的措辞是"**会**求值为 true"（would evaluate to true）：判断的是一个**假想的**求值的结果。在 `f` 中，若真的求值 `++y == 43`，它在 `y == 42` 时为真，所以没有 UB；编译器因此可以推出 `y == 42`（**递增前**的值），把 `return y` 替换为 `return 42`（这是标准例子的说法；实际上 Clang 23 因为表达式有副作用而忽略这个假设，并给出 `-Wassume` 警告，见下文）。如果调用 `f(0)`，假想的求值结果为 false——UB。

这个"假想求值"的语义还隐含了几种也是 UB 的情况：

- 假想求值本身会有 UB（比如 `[[assume(*p == 0)]]` 而 `p` 是空指针）——它不会"求值为 true"；
- 假想求值会抛出异常、不终止、调用 `std::exit`——都不是"求值为 true"。

### 潜在求值：会 odr-use（¶2）

¶2 注 1：表达式是**潜在求值**的（[[basic.def.odr]]）。这与 `sizeof`、`decltype` 中的不求值操作数不同：其中出现的变量会被 **odr-use**，函数会被要求有定义，lambda 中会触发隐式捕获的要求。

```cpp title="assume-odr-use.cpp" error
void f(int x) {
    auto l1 = [] { [[assume(x > 0)]]; };     // error: x 被 odr-use，但 lambda 没有捕获
    auto l2 = [=] { [[assume(x > 0)]]; };    // OK: 隐式按值捕获 x
    (void)l1; (void)l2;
}
```

为什么要潜在求值？因为假设的语义是"如果求值会得到 true"——这需要表达式**有一个良定义的求值**，因此它必须像普通表达式一样被完整地处理：名字绑定、模板实例化、odr-use。把它当作不求值操作数会产生一个"能写、但无法定义'会求值成什么'"的表达式。

## 意图与"可以忽略"（¶2）

¶2 注 1 后半：使用假设的意图是让实现**分析表达式的形式**，推导出可用于优化程序的信息。实现**不被要求**从任何特定的假设中推导任何信息。如果实现完全不尝试推导，`__has_cpp_attribute(assume)` 预期为 0。

所以 `assume` 是一份**无强制力的合同**：程序员承诺 `expr` 为真（违约则 UB）；编译器可以利用，也可以不利用。

## 例子：它能带来什么

```cpp title="assume-codegen.cpp" ok
int divide_by_32(int x) {
    [[assume(x >= 0)]];
    return x / 32;      // 可以省掉对负数的处理
}
int plain(int x) {
    return x / 32;
}

int main() {}
```

Clang 23（`-O2`，x86-64）为两者生成的代码：

```text
divide_by_32:                plain:
    mov  eax, edi                lea   eax, [rdi + 31]
    shr  eax, 5                  test  edi, edi
    ret                          cmovns eax, edi
                                 sar   eax, 5
                                 ret
```

有符号整数除以 2 的幂要向零取整，负数需要先加上 31 再算术右移；知道 `x >= 0` 后，一条逻辑右移就够了。

## 与常量求值

[[expr.const.core#3]]：表达式满足核心常量表达式的约束、但求值具有运行期未定义行为时，它**是否**为核心常量表达式由**实现定义**。对于 `assume` 来说就是：常量求值中遇到一个"会为 false"的假设，实现可以选择报错，也可以选择忽略它继续求值。

```cpp title="assume-constexpr.cpp" impl
constexpr int g(int x) {
    [[assume(x > 0)]];
    return x;
}
constexpr int a = g(1);     // OK
constexpr int b = g(-1);    // 实现定义：Clang 23 报错（"assumption evaluated to false"）
```

为什么不像其他 UB 一样要求常量求值必须诊断？因为那会迫使实现在常量求值中**真的求值**每个假设表达式——而假设表达式可能很昂贵、或者有副作用（如 `++y == 43`），设计上就不打算被求值。"运行期未定义行为"这个术语正是为此而创造的（见 [[intro.defs]]）。

## 有副作用的假设

标准允许假设表达式有副作用（它们不会被执行）。但实现很难从这样的表达式中推导信息：

```cpp title="assume-side-effects.cpp" ok
int counter();
void f() {
    [[assume(counter() > 0)]];   // 合法；Clang 警告"assumption is ignored because it contains (potential) side-effects"
}

int main() {}
```

Clang 的策略是：表达式含有（可能的）副作用——包括调用非 `const`/非 `pure` 的函数——就整个忽略该假设。GCC 会尝试更多分析。这都在"实现不被要求推导任何信息"的允许范围内。

## 与相近工具的比较

| 工具 | 条件为假时 | 是否求值表达式 | 用途 |
|---|---|---|---|
| `[[assume(e)]]` | 运行期 UB | 否 | 给优化器提供事实 |
| `assert(e)` | 调试模式下终止；`NDEBUG` 时无事发生 | 调试模式下是 | 调试检查 |
| 契约 `contract_assert(e)`（C++26，[[basic.contract]]） | 按求值语义：忽略 / 观察 / 强制终止 | 取决于语义 | 检查与文档 |
| `if (!e) std::unreachable();`（C++23） | UB | **是** | 标记不可达代码 |

`std::unreachable()` 的版本会**求值** `e`（如果 `e` 有副作用就会执行），而 `assume` 不会。另一方面，**绝对不要**把契约断言和假设"合并"成同一个宏：契约被设计为可以被检查，假设被设计为可以被利用——一个在调试版检查、在发布版假设的宏，会把一个契约违约从"可报告的错误"变成"任意行为"。

## 实现视角

!!! impl "各编译器"
    - **Clang**：`[[assume(e)]]` 降低为 LLVM 的 `llvm.assume` 内建；`__builtin_assume(e)` 是更早的等价物。含副作用的表达式被忽略并给出 `-Wassume` 警告。
    - **GCC**（13 起支持 `[[assume]]`）：同时支持 `__attribute__((assume(e)))` 语法。
    - **MSVC**：长期提供 `__assume(e)`；`__assume(0)` 表示不可达。
    - 过多或复杂的假设可能**降低**性能：它们是优化器 IR 中的额外节点，可能阻碍其他优化。只在测量证明有收益时使用。

## 历史与演进

!!! history "C++23"
    - 引入于 C++23（[[P1774R8]]）。最初的提案讨论过用函数（`std::assume(e)`）、关键字、属性等多种形式；选择属性的理由正是"可忽略性"：删掉它不会改变正确程序的含义。
    - 引入时的措辞是"行为未定义"，并在 [expr.const] 中把它列为"是否为核心常量表达式未指定"的情形；当前草案引入了**运行期未定义行为**这个术语，并改为实现定义。

## 陷阱

!!! pitfall "假设错了就是 UB，不是“优化失效”"
    编译器可以基于假设删除代码，包括删除你用来"兜底"的检查：

    ```cpp
    int f(int* p) {
        [[assume(p != nullptr)]];
        if (!p) return -1;   // 这一行可以被直接删除
        return *p;
    }
    ```

!!! pitfall "以为表达式会被执行"
    `[[assume(init() == 0)]]` 不会调用 `init()`。

!!! pitfall "lambda 中的假设会触发捕获"
    假设表达式潜在求值，引用外部局部变量需要捕获；这可能意外地改变闭包的大小（`[=]` 下）。

## 思考题

!!! question "思考题 1"
    下面的程序有没有 UB？`f(41)` 返回什么？

    ```cpp
    int f(int y) {
        [[assume(++y == 43)]];
        return y;
    }
    ```

<details markdown="1">
<summary>答案</summary>

`f(41)`：假想求值 `++y == 43` 时 `y` 变成 42，比较为 false——假设"不会为 true"，所以**求值这个假设是运行期 UB**。返回什么都不确定（编译器很可能直接返回 42，因为它推出 `y` 必为 42）。只有 `f(42)` 没有 UB，返回 42（`y` 实际上没被递增）。
</details>

!!! question "思考题 2"
    为什么说 `[[assume]]` 满足 [[dcl.attr.grammar#8]] 的可忽略性要求？举一个违反可忽略性的假想属性。

<details markdown="1">
<summary>答案</summary>

带 `[[assume(e)]]` 的程序在 `e` 为假的执行中是 UB，允许任何行为；删除它之后，这些执行变成按普通规则继续执行——这些执行原本就在"任何行为"之中；`e` 为真的执行则完全不受影响。所以删除后的可能执行集合是原集合的子集。一个违反可忽略性的假想属性是 `[[check(e)]]`："若 e 为假则调用 `std::terminate`"——删掉它后，原本必定终止的执行会继续运行，产生了原程序中不可能的执行。这正是契约断言是语言特性而不是属性的原因。
</details>

## 小结

!!! summary "要点"
    - 形式：`[[assume(conditional-expression)]];`，只能用于空语句。
    - 表达式上下文转换为 `bool`，**不求值**但**潜在求值**（odr-use、需要捕获）。
    - "会求值为 true"则无效果；否则（包括假想求值本身 UB、不终止）是**运行期未定义行为**。
    - 常量求值中遇到为假的假设，是否视为非常量由实现定义。
    - 实现可以完全忽略假设；Clang 忽略含副作用的假设。
