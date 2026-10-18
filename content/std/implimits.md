---
title: 实现限额（Annex B）
summary: 资料性附录 Annex B 列出 44 项可能受实现限制的数量及其建议最小值（嵌套层数、标识符长度、参数个数、constexpr 递归深度、模板实例化深度……）。本页逐项解释，并给出在 Clang 23 上实测或从诊断信息中确认的实际上限——其中 #include 嵌套深度低于建议值，若干深度在达到上限前就会让前端栈溢出。
status: draft
related: intro.compliance, expr.const.core, temp.inst, ub.temp
tags: 附录, 实现限制, 编译器, constexpr, 模板
updated: 2026-10-18
---

抽象机的资源是无限的，真实的编译器不是。Annex B（*Implementation quantities*，实现限额）列出了一些"实现可能有上限"的数量，并为每一项给出一个**可能的最小值**（*potential minimum value*）。它回答的是一个实际问题：写一个合法但"很大"的程序——几千个枚举量、几百层嵌套、深度递归的模板——能指望编译器接受到什么程度？

## 这些数字的法律地位

Annex B 是**资料性**（*informative*）附录，它的数字**不是要求**。

- [[intro.compliance.general#2.1]] 规定，实现必须接受并正确执行一个没有违反任何规则的程序，"**除非超出了实现的限制**"。这句话给了实现在资源用尽时拒绝程序的权利，而且标准没有规定这些限制必须是多少。
- [[intro.compliance.general#9]] 是一条推荐实践：实现**应当**在文档中说明它能处理的程序规模与复杂度，Annex B 列出了一些可能受限的量与"可能的最小支持值"。
- 与 C 标准的"translation limits"不同（C 要求实现至少能翻译一个同时达到全部限额的程序），C++ 的 Annex B 连这种弱保证都没有。

有两处正文直接引用了 Annex B，让其中两项限额具有规范意义：

- [[expr.const.core#2.7]]：超出实现定义的限额的表达式**不是核心常量表达式**。所以 constexpr 递归太深、常量求值步数太多时，结果不是编译器挂死，而是"不是常量"。
- [[temp.inst#18]]：递归实例化的总深度有一个**实现定义**的上限；无限递归实例化的结果是未定义的（见 [[ub.temp]]）。

## 全部 44 项

"Clang 23 实测"一栏的数字来自本机（Clang 23.1.3，arm64 macOS，进程栈 8 MB）上用 `-fsyntax-only` 编译生成的测试文件：

- 写"上限 N"的，是 Clang 的诊断信息里直接给出的数字，或在 N 与 N+1 之间二分出的边界；
- 写"≥ N 通过"的，只是测试过 N 能通过，并没有找到上限；
- 写"栈溢出"的，是前端在达到任何显式上限之前就崩溃了（退出码 139 / SIGSEGV），这个数字与进程栈大小有关；
- "—"表示没有测试。

| # | 数量 | 建议最小值 | Clang 23 实测 |
|---|---|---|---|
| 1.1 | 复合语句、迭代语句、选择语句的嵌套层数（[[stmt.block]]、[[stmt.iter]]、[[stmt.select]]） | 256 | 花括号嵌套上限 2048（`bracket nesting level exceeded maximum of 2048`） |
| 1.2 | 条件包含（`#if`）的嵌套层数（[[cpp.cond]]） | 256 | ≥ 5 000 通过 |
| 1.3 | 一个声明中修饰类型的指针、成员指针、数组、函数声明符的个数（任意组合） | 256 | 5 000 个 `*` 通过 |
| 1.4 | 一个完整表达式中括号表达式的嵌套层数（[[expr.prim.paren]]） | 256 | 1 103 层通过，1 104 层栈溢出 |
| 1.5 | 内部标识符或宏名的字符数（[[lex.name]]、[[cpp.replace]]） | 1 024 | 100 000 字符通过 |
| 1.6 | 外部标识符的字符数 | 1 024 | 同上（测试用的是具有外部链接的全局变量） |
| 1.7 | 一个翻译单元中的外部标识符个数（[[basic.link]]） | 65 536 | 200 000 个全局变量通过 |
| 1.8 | 一个块中声明的块作用域标识符个数 | 1 024 | 20 000 通过 |
| 1.9 | 一个声明引入的结构化绑定个数（[[dcl.struct.bind]]） | 256 | 1 000 通过 |
| 1.10 | 一个翻译单元中同时定义的宏标识符个数 | 65 536 | 200 000 通过 |
| 1.11 | 一个函数定义的形参个数（[[dcl.fct.def.general]]） | 256 | 20 000 通过 |
| 1.12 | 一次函数调用的实参个数（[[expr.call]]） | 256 | — |
| 1.13 | 一个宏定义的形参个数（[[cpp.replace]]） | 256 | 5 000 通过 |
| 1.14 | 一次宏调用的实参个数 | 256 | 5 000 通过 |
| 1.15 | 一个逻辑源代码行的字符数（[[lex.phases]]） | 65 536 | 约 23 万字符的单行通过 |
| 1.16 | 一个字符串字面量（拼接后）的字符数（[[lex.string]]） | 65 536 | 1 000 000 通过 |
| 1.17 | 一个对象的大小（[[intro.object]]） | 262 144 字节 | 2⁴⁰ 字节的静态数组通过；2⁶¹ 个 `char` 报 `array is too large` |
| 1.18 | `#include` 文件的嵌套层数（[[cpp.include]]） | 256 | **上限 200 层文件**：头文件嵌套到第 199 层通过，第 200 层报 `#include nested too deeply` |
| 1.19 | 一个 `switch` 的 `case` 标号个数（不计嵌套的 `switch`）（[[stmt.switch]]） | 16 384 | 20 000 通过 |
| 1.20 | 一个类的非静态数据成员个数（含继承来的）（[[class.mem]]） | 16 384 | — |
| 1.21 | 一个 lambda 表达式的捕获个数（[[expr.prim.lambda.capture]]） | 256 | 2 000 通过 |
| 1.22 | 一个枚举的枚举量个数（[[dcl.enum]]） | 4 096 | 100 000 通过 |
| 1.23 | 一个 *member-specification* 中嵌套类定义的层数（[[class.nest]]） | 256 | 758 层通过，759 层栈溢出 |
| 1.24 | `atexit()` 注册的函数个数（[[support.start.term]]） | 32 | — |
| 1.25 | `at_quick_exit()` 注册的函数个数 | 32 | — |
| 1.26 | 直接与间接基类的个数（[[class.derived]]） | 16 384 | — |
| 1.27 | 一个类的直接基类个数 | 1 024 | 2 000 通过 |
| 1.28 | 一个 *member-specification* 中声明的类成员个数（含成员函数）（[[class.mem]]） | 4 096 | 7 000 个数据成员通过 |
| 1.29 | 一个类中的最终覆盖虚函数个数（不论可访问与否）（[[class.virtual]]） | 16 384 | — |
| 1.30 | 一个类的直接与间接虚基类个数（[[class.mi]]） | 1 024 | 2 000 通过 |
| 1.31 | 一个类的静态数据成员个数（[[class.static.data]]） | 1 024 | 5 000 通过 |
| 1.32 | 一个类中的友元声明个数（[[class.friend]]） | 4 096 | 5 000 通过 |
| 1.33 | 一个类中的访问控制声明个数（[[class.access.spec]]） | 4 096 | 5 000 通过 |
| 1.34 | 一个构造函数定义中的成员初始化器个数（[[class.base.init]]） | 6 144 | 7 000 通过 |
| 1.35 | 一个 *braced-init-list* 中的 *initializer-clause* 个数（[[dcl.init]]） | 16 384 | 200 000 通过 |
| 1.36 | 一个标识符的作用域限定层数（[[expr.prim.id.qual]]） | 256 | 1 000 层嵌套命名空间限定通过 |
| 1.37 | 嵌套的 *linkage-specification* 层数（[[dcl.link]]） | 1 024 | 2 000 通过 |
| 1.38 | constexpr 函数的递归调用层数（[[dcl.constexpr]]） | 512 | **上限 512**（`-fconstexpr-depth`） |
| 1.39 | 一个核心常量表达式中求值的完整表达式个数（[[expr.const.core]]） | 1 048 576 | **约 1 048 576 步**（`-fconstexpr-steps`） |
| 1.40 | 一个模板声明的模板形参个数（[[temp.param]]） | 1 024 | 5 000 通过 |
| 1.41 | 递归嵌套的模板实例化层数，含模板实参推导中的替换（[[temp.inst]]、[[temp.deduct]]） | 1 024 | **上限 1024**（`-ftemplate-depth`） |
| 1.42 | 一个 try 块的处理器个数（[[except.handle]]） | 256 | 2 000 通过 |
| 1.43 | 占位符的个数（`std::placeholders`） | 10 | libc++ 恰好提供 `_1` 到 `_10` |
| 1.44 | 可受危险指针保护的可能回收对象个数（[[saferecl.hp.general]]） | 256 | — |

## 几个值得细看的数字

### constexpr：深度 512、步数约一百万

```cpp error
constexpr int f(int n) { return n == 0 ? 0 : 1 + f(n - 1); }
static_assert(f(511) == 511);   // OK：共 512 层调用
static_assert(f(512) == 512);   // error: 不是常量表达式（超出 512 层）
```

Clang 的诊断附注是 `constexpr evaluation exceeded maximum depth of 512 calls`（可用 `-fconstexpr-depth=N` 调整）。步数限制类似：一个简单的累加循环在常量求值中跑到 1 048 571 次迭代时通过，1 048 572 次时失败，附注是 `constexpr evaluation hit maximum step limit; possible infinite loop?`（可用 `-fconstexpr-steps=N` 调整）。两者与 Annex B 的 1.38、1.39 恰好对齐——Clang 直接采用了建议值作为默认值。

由于 [[expr.const.core#2.7]]，超出这两个限制**不是**编译错误本身，而是"该表达式不是常量表达式"。在只是"可以"常量求值的场合（例如非 `constexpr` 变量的初始化器），这意味着编译器会悄悄退回到运行时初始化，而不是报错。

### 模板实例化深度 1024

```cpp ub
template <int N> struct R { static constexpr int v = R<N - 1>::v + 1; };
template <> struct R<0> { static constexpr int v = 0; };

static_assert(R<1025>::v == 1025);   // OK：恰好在上限内（R<1026> 就超限）
template <class T> struct X { X<T*> a; };
X<int> x;   // 无限递归：fatal error: recursive template instantiation exceeded maximum depth of 1024
```

二分测得 `R<1025>` 可以、`R<1026>` 报（最外层的 `R<1025>` 本身不计入递归深度） `recursive template instantiation exceeded maximum depth of 1024`。注意这是 **fatal error**：Clang 遇到它会立即停止整个编译。`-ftemplate-depth=N` 可以调整。这个数字也正是 Annex B 1.41 的建议值。

### #include 嵌套：低于建议值

Annex B 建议至少支持 256 层 `#include` 嵌套，而 Clang 的上限是 200 层（包括主文件）。这完全合法——Annex B 只是建议——也几乎不会在真实代码中碰到。它是一个很好的提醒：Annex B 的数字既不是下限保证，也不是各实现的实际值。

### 括号与嵌套类：栈先耗尽

Clang 有一个显式的括号嵌套上限 `-fbracket-depth`，默认 2048：在花括号嵌套的测试中，第 2049 层报 `bracket nesting level exceeded maximum of 2048`。但对于**圆括号**表达式，本机在 1 104 层时前端就因栈溢出崩溃了（没有诊断信息，退出码 139），远未达到 2048；嵌套类定义在 759 层时同样崩溃，一条由 14 461 个 `+` 连成的表达式也是如此。这些都超过了 Annex B 的建议值（256），但说明对于递归下降的解析器，真正的限制往往是机器栈，而不是一个写在文档里的数字。

### 对象大小

建议最小值只有 262 144 字节（256 KiB），这是一个非常保守的数字，来自嵌入式与分段内存模型的时代。在 64 位平台上，Clang 接受 2⁴⁰ 字节（1 TiB）的静态数组声明（是否能真正链接和运行是另一回事），而 2⁶¹ 个元素的 `char` 数组被拒绝：`array is too large`——对象的字节大小必须能用 `std::size_t` 表示，且实现还要为指针差 `std::ptrdiff_t` 留余地。

## 小结

| 问题 | 答案 |
|---|---|
| Annex B 的数字是要求吗？ | 不是。它是资料性的"可能的最小值"，实现可以更低（Clang 的 `#include` 嵌套就是 200） |
| 实现超出限制时怎样？ | 可以拒绝程序（[[intro.compliance.general#2.1]]）；在常量求值中，超限使表达式不是常量（[[expr.const.core#2.7]]） |
| Clang 可调的限制 | `-fconstexpr-depth`（默认 512）、`-fconstexpr-steps`（约 1 048 576）、`-ftemplate-depth`（默认 1024）、`-fbracket-depth`（默认 2048） |
| 最可能碰到的限制 | constexpr 的步数与深度、模板实例化深度；解析器的栈深度在机器生成的代码中也可能碰到 |
