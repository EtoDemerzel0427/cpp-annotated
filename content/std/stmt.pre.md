---
title: 语句总则、标号、表达式语句与复合语句
summary: 语句的语法总表；子语句与包围关系；条件（condition）中的声明与 C++26 的结构化绑定条件；标号与控制流受限语句；表达式语句、空语句、复合语句。
status: draft
covers: stmt.label, stmt.expr, stmt.block
papers: P0963R3, P2324R2, P0305R1
related: stmt, stmt.select, stmt.iter, stmt.dcl, basic.scope.block, dcl.struct.bind, expr.context
tags: 语句, 条件, 标号
updated: 2026-10-17
---

本页是第 8 章的基础。[[stmt.pre]] 本身只有八段，但它定义了全章反复使用的四个工具：

1. 语句的语法总表（*statement*、*init-statement*、*condition*、*for-range-declaration*）；
2. 子语句（substatement）与包围（encloses）关系，它们是判断 `break`、`case`、`return` 放在哪里合法的依据；
3. 条件（*condition*）的语义：什么时候是表达式，什么时候是声明，它的值是什么；
4. 条件与 *for-range-declaration* 中允许的声明说明符。

本页还一并讲解三个很短的小节：[[stmt.label]]（标号）、[[stmt.expr]]（表达式语句）、[[stmt.block]]（复合语句）。

## 语句的语法（¶1）

¶1 除非另有说明，语句按顺序执行（executed in sequence，参见 [[intro.execution]]）。这句话看似多余，却是顺序点之外另一层顺序保证的来源：语句之间的先后由语句结构决定，一条表达式语句内部的先后才由 [[intro.execution]] 的 sequenced-before 规则决定。

语法上，*statement* 有以下几类：

| 语法类别 | 例子 | 详见 |
|---|---|---|
| *labeled-statement* | `L: x = 1;`、`case 3: ...` | [[stmt.label]] |
| *expression-statement* | `f(x);`、`;` | [[stmt.expr]] |
| *compound-statement* | `{ ... }` | [[stmt.block]] |
| *selection-statement* | `if`、`if constexpr`、`if consteval`、`switch` | [[stmt.select]] |
| *iteration-statement* | `while`、`do`、`for`、范围 `for` | [[stmt.iter]] |
| *expansion-statement* {{c++26}} | `template for (auto x : t) { }` | [[stmt.expand]] |
| *jump-statement* | `break`、`continue`、`return`、`co_return`、`goto` | [[stmt.jump]] |
| *assertion-statement* {{c++26}} | `contract_assert(p);` | [[stmt.contract.assert]] |
| *declaration-statement* | `int x = 0;` | [[stmt.dcl]] |
| *try-block* | `try { } catch (...) { }` | [[except.pre]] |

除 *labeled-statement* 和 *declaration-statement* 外，每种语句前面都可以有一个可选的 *attribute-specifier-seq*，它属于该语句（appertains to the respective statement）。标号自己的属性写在标号里（见下文 [[stmt.label]]），声明语句的属性属于声明本身（[[dcl.pre]]）。语句属性的典型例子是 `[[likely]]`/`[[unlikely]]`（[[dcl.attr.likelihood]]），以及作用于空语句的 `[[fallthrough]]`（[[dcl.attr.fallthrough]]）。

```cpp run ok
int classify(int n) {
    if (n > 0) [[likely]] {        // 属性属于这个复合语句
        return 1;
    }
    switch (n) {
    case 0:
        [[fallthrough]];           // 属性属于一个空语句 → "fallthrough 语句"
    case -1:
        return 0;
    default:
        return -1;
    }
}
int main() { return classify(1) == 1 ? 0 : 1; }
```

¶1 还给出四个辅助非终结符：

- *init-statement*：*expression-statement*、*simple-declaration* 或 *alias-declaration*（{{c++23}} 起允许 `using` 别名声明）。它出现在 `if`/`switch`/`for`/范围 `for`/`template for` 的开头，总是以分号结尾，所以 `if (auto x = f(); x)` 中间有一个分号。
- *condition*：要么是 *expression*，要么是 *condition-declaration*。后者又有两种形式：普通的说明符 + 声明符 + *brace-or-equal-initializer*，以及 {{c++26}} 的 *structured-binding-declaration* + *initializer*。
- *for-range-declaration*：范围 for 和展开语句中冒号左边的部分，可以是普通声明或结构化绑定声明，没有初始化器（初始化来自冒号右边）。
- *for-range-initializer*：*expr-or-braced-init-list*，即冒号右边的部分，可以是花括号列表。

注意，*condition-declaration* 的普通形式只接受 *brace-or-equal-initializer*，也就是 `= expr` 或 `{...}`，**不接受圆括号初始化器**。原因是圆括号形式在这里会与函数声明、函数式转换产生更多歧义。

```cpp ok
int* get();
void f() {
    if (int* p = get()) { *p = 1; }    // OK: = 初始化
    if (int n{3}) { (void)n; }         // OK: 花括号初始化
    if (const int k = 4) { (void)k; }  // OK: const 是 type-specifier
}
```

```cpp error
void g() {
    if (int n(3)) { }     // error: condition 不允许圆括号初始化器
}
```

## 子语句（¶2）

¶2 定义一条语句的**子语句**（[[g:substatement|substatement]]）：

| 外层语句 | 它的子语句 |
|---|---|
| 带标号语句（¶2.1） | 标号后面的那条语句 |
| 复合语句（¶2.2） | *statement-seq* 中的每一条语句 |
| 选择语句（¶2.3） | 它的各个分支语句（`if` 的两个分支、`switch` 的体），不包括 *init-statement* |
| 迭代语句（¶2.4） | 循环体，不包括 *init-statement* |
| 展开语句（¶2.5） | 它的 *compound-statement*，不包括 *init-statement* |

有两点要注意：

1. *condition* 不是语句，自然不是子语句；*init-statement* 是语句，但被明确排除在子语句之外，它和外层语句的关系由 ¶3.2 单独规定。
2. **lambda 表达式的函数体不是它所在语句的子语句**（注 1）。lambda 体是另一个函数的函数体，控制流不能从 lambda 体跳到外层函数的循环或 `switch` 中。

```cpp error
void h(int n) {
    for (int i = 0; i < n; ++i) {
        [&] {
            if (i == 3) break;   // error: break 没有被循环包围（lambda 体不是循环的子语句）
        }();
    }
}
```

## 包围关系（¶3）

¶3 在子语句的基础上定义**包围**（encloses）关系。语句 S1 包围 S2，当且仅当：

- ¶3.1 S2 是 S1 的子语句；或
- ¶3.2 S1 是选择、迭代或展开语句，S2 是它的 *init-statement*；或
- ¶3.3 S1 是 *try-block*，S2 是它的复合语句或某个 *handler* 的复合语句；或
- ¶3.4 传递闭包：S1 包围 S3，且 S3 包围 S2。

反过来的说法是 S2 被 S1 包围（is enclosed by）。

为什么要单独定义包围，而不直接用子语句？因为很多规则需要一种可以跨越多层、但不跨越函数边界的"在里面"的概念：

- `break`/`continue` 必须被某种循环（或 `switch`、展开语句）包围（[[stmt.break]]、[[stmt.cont]]）；
- `case`/`default` 标号必须被 `switch` 包围（[[stmt.label#2]]）；
- 协程不得包围 `return` 语句（[[stmt.return.coroutine#1]]）；
- *try-block* 的 handler 也在包围关系之内（¶3.3），因此 `catch` 块里的 `break` 可以跳出外层循环。

lambda 体不是子语句，而包围关系建立在子语句之上，所以上面这些规则都不会穿透 lambda。

```cpp run ok
#include <stdexcept>
int count_until_throw(int n) {
    int i = 0;
    for (; i < n; ++i) {
        try {
            if (i == 3) throw std::runtime_error("stop");
        } catch (...) {
            break;               // OK: handler 的复合语句被 try-block 包围（¶3.3），进而被 for 包围
        }
    }
    return i;
}
int main() { return count_until_throw(10) == 3 ? 0 : 1; }
```

!!! lawyer "init-statement 里能写 break 吗？"
    ¶3.2 规定 *init-statement* 被它的循环包围，所以仅从包围关系看，`for (break; ;)` 中的 `break` 被 `for` 包围。但 *init-statement* 只能是表达式语句、简单声明或别名声明，而 `break;` 是跳转语句，语法上就放不进去，所以这个问题不会出现。真正有意义的是：*init-statement* 中 lambda 体里的 `break` 仍然不行（lambda 体不是子语句）。¶3.2 的实际用途主要在 [[stmt.return.coroutine]] 这类不得包围某种语句的规则上，以及 [[stmt.label#3]] 的控制流受限判断。

## 条件（¶4–¶8）

### 条件是表达式还是声明（¶4）

¶4 条件的规则同时适用于选择语句（[[stmt.select]]）和 `for`/`while`（[[stmt.iter]]）。（`do` 的括号里只能写 *expression*，见 [[stmt.do]]。）

- 如果条件中出现 *structured-binding-declaration*，条件就是一个结构化绑定声明（[[dcl.pre]]）{{c++26}}；
- 否则，如果它不是 *expression*，条件就是一个声明；
- 声明符不得声明函数或数组；
- *decl-specifier-seq* 不得定义类或枚举；
- 如果出现 `auto`，按 [[dcl.spec.auto]] 从初始化器推导。

为什么禁止数组和函数？条件的值要按语境转换为 bool，数组会退化为非空指针，永远为真；函数声明根本没有初始化器。两者都没有意义。为什么禁止定义类型？如果允许 `if (struct S { ... } s = ...)`，就会在表达式的语法位置引入新的类作用域，给解析器和作用域规则都带来不必要的复杂度。

```cpp error
void f() {
    if (int a[2] = {1, 2}) { }                 // error: 声明符声明了数组
    if (struct B { operator bool() const { return true; } } b{}) { }  // error: 不得定义类
}
```

### 判定变量（¶5）与条件的值（¶6）

¶5 引入术语**判定变量**（[[g:decision-variable|decision variable]]）：

- 对普通声明形式的条件，判定变量就是声明的那个变量；
- 对结构化绑定形式的条件，判定变量是结构化绑定背后那个无名变量 *e*（[[dcl.struct.bind#4]]）。

¶6 规定条件的值：

- 对 `switch` 以外的语句，如果条件是声明，它的值是判定变量按语境转换为 bool（contextually converted to bool，[[conv]]）的结果；如果条件是表达式，它的值是表达式按语境转换为 bool 的结果。如果转换非良构，程序非良构。
- 对 `switch`，条件的值不转换为 bool，而是按 [[stmt.switch#2]] 转换为整型或枚举类型。

按语境转换为 bool 意味着可以使用 `explicit operator bool`，`if (std::unique_ptr<T> p = ...)`、`while (std::cin >> x)` 能工作正是因为这一点。

```cpp run ok
#include <memory>
std::unique_ptr<int> make(bool b) { return b ? std::make_unique<int>(7) : nullptr; }
int main() {
    if (auto p = make(true)) {      // unique_ptr::operator bool 是 explicit，但这里是按语境转换
        return *p == 7 ? 0 : 1;
    }
    return 1;
}
```

### 结构化绑定作为条件 {{c++26}}

在 C++26 之前，条件里不能写结构化绑定，常见的写法是先在 *init-statement* 里绑定，再在条件里测试：

```cpp
if (auto [ptr, ec] = std::from_chars(b, e, v); ec == std::errc{}) { ... }
```

[[P0963R3]] 允许直接把结构化绑定声明当作条件。它的语义是：**被测试的是整个对象 *e*（判定变量），而不是某个绑定**。所以只有当 *e* 本身可以按语境转换为 bool 时，这种写法才有意义。`std::from_chars_result` 正是为此在 C++26 中获得了 `operator bool`（判断 `ec == std::errc{}`）。

```cpp run ok
#include <charconv>
int parse(const char* s, int len) {
    int v = 0;
    if (auto [ptr, ec] = std::from_chars(s, s + len, v)) {   // 测试的是 from_chars_result
        (void)ptr; (void)ec;
        return v;
    }
    return -1;
}
int main() { return parse("42", 2) == 42 ? 0 : 1; }
```

这里还有一个精细的顺序保证：对类元组（tuple-like）类型，先初始化 *e* 并完成它到 bool 的转换，再初始化各个绑定（调用 `get<i>`）（[[dcl.struct.bind#7]]）。这样，类型可以在 `operator bool` 里检查是否有值，只在有值时才调用 `get`。

```cpp ok
struct P {
    int a, b;
    explicit operator bool() const { return a != 0; }
};
int f(P p) {
    if (auto [x, y] = p)   // 判定变量是无名变量 e（P 的副本），而不是 x 或 y
        return x + y;
    return 0;
}
```

```cpp error
#include <tuple>
void g(std::tuple<int, int> t) {
    if (auto [a, b] = t) { }   // error: std::tuple 不能按语境转换为 bool
}
```

!!! pitfall "条件是 e，不是第一个绑定"
    `if (auto [ok, value] = ...)` 看起来像是在测试 `ok`，其实不是，被测试的是整个被绑定的对象。如果想测试某个成员，仍然需要 *init-statement* 加显式条件：`if (auto [ok, v] = f(); ok)`。

### 歧义时视为声明（¶7）

¶7 如果条件在语法上既可以解析为表达式，也可以解析为 *condition-declaration*，就按声明处理。这与 [[stmt.ambig]] 处理语句级歧义的方向一致：能解析为声明就当作声明。

```cpp run ok
struct T {
    int v;
    T(int x) : v(x) {}
    explicit operator bool() const { return v != 0; }
};
int x = 0;
int main() {
    // 可以读作表达式 "把 T(x) 赋值为 5"，也可以读作声明 "T x = 5"。
    // ¶7：按声明处理 —— 声明了一个新的局部变量 x，遮蔽全局 x。
    if (T(x) = 5) {
        return x.v == 5 ? 0 : 1;   // 这里的 x 是 T 类型的新变量
    }
    return 1;
}
```

Clang 对这种写法会给出 `-Wvexing-parse` 警告，提示这对括号被当作了声明符中多余的括号。

### 允许哪些声明说明符（¶8）

¶8 规定，条件和 *for-range-declaration*（包括其中的结构化绑定声明）的每个 *decl-specifier* 只能是 type-specifier 或 `constexpr`。所以：

- `const`、`volatile`、`auto`、类型名：允许（都是 *type-specifier*）；
- `constexpr`：允许；
- `static`、`thread_local`、`extern`、`inline`、`constinit`、`typedef`、`friend`：不允许。

```cpp ok
void f() {
    if (constexpr bool dbg = false) { }       // OK
    for (const auto& c : "abc") { (void)c; }  // OK
}
```

```cpp error
void g() {
    if (static int n = 1) { }                 // error: static 不是 type-specifier
    for (static int i : {1, 2}) { (void)i; }  // error: 同上
}
```

!!! note "条件中声明的名字的作用域"
    条件中声明的名字，作用域从声明点一直延伸到整条语句结束（包括 `else` 分支），并且不得在子语句的最外层块里重新声明同名变量。这条规则在 [[basic.scope.block]] 中（选择、迭代语句及其子语句都有自己的块作用域，见 [[stmt.select.general#2]]、[[stmt.iter.general#2]]）。

```cpp error
void f(int* q) {
    if (int* p = q) {
        int p = 0;   // error: 与条件中声明的 p 冲突
    } else {
        int* p = q;  // error: 同上，else 分支也一样
    }
}
```

## 标号 [stmt.label]

### 三种标号（[stmt.label]/1）

¶1 标号有三种形式：标识符标号 `name:`、`case 常量表达式:` 和 `default:`。每种前面都可以有属性，属性属于标号，而不是被标号的语句。

- 标识符标号的唯一用途是作为 `goto` 的目标。
- 同一个函数中不能有两个同名标号。注意范围是函数而不是块：标号不受块作用域约束，`goto` 只要求目标是当前函数中的标号（[[stmt.goto]]）。
- 可以先 `goto`，后定义标号（前向引用）。

```cpp error
void f(int n) {
    { L: ++n; }
    { L: --n; }      // error: 同一函数中标号 L 重复（不同块也不行）
    goto L;
}
```

标号与其他名字分属不同的名字空间：标号 `x:` 不会和变量 `x` 冲突。

```cpp ok
void f() {
    int x = 0;
x:                   // OK: 标号与变量不冲突
    if (++x < 3) goto x;
}
```

### 标号可以出现在复合语句末尾 {{c++23}}

¶1 第一句说标号可以出现在复合语句中的任何位置，配合 [[stmt.block]] 的语法 `{ statement-seq(opt) label-seq(opt) }`，复合语句末尾可以出现一串标号，视为后面跟了一个空语句。C++23 之前标号必须标在某条语句上，所以人们写 `end: ;`。这项改动（[[P2324R2]]）与 C23 保持一致。

```cpp ok
int f(int n) {
    if (n < 0) goto out;
    n *= 2;
out:
}                    // C++23 起 OK：标号位于复合语句末尾
```

这里 `f` 的返回类型是 `int`，却没有 `return`。它能通过编译，但如果真的执行到函数末尾，就是 UB（[[stmt.return#4]]）。上例只用于演示语法。

```cpp ok
void g(int n) {
    switch (n) {
    case 1:
        ++n;
    default:         // C++23 起 OK：default 标号位于末尾，不需要后跟 ";"
    }
}
```

### case/default 必须被 switch 包围（¶2）

¶2 带 `case`/`default` 标号的语句必须被某个 `switch` 包围（按 ¶3 定义的包围关系）。lambda 体不是子语句，所以 `switch` 里的 lambda 不能有 `case`：

```cpp error
void f(int n) {
    switch (n) {
    case 0:
        [] {
        case 1: ;    // error: 没有被 switch 包围
        }();
    }
}
```

### 控制流受限语句（¶3）

¶3 **控制流受限语句**（[[g:control-flow-limited-statement|control-flow-limited statement]]）S 满足：

- ¶3.1 S 中出现的 `case`/`default` 标号必须属于 S 内部的某个 `switch`；
- ¶3.2 S 中声明的标号只能被 S 中的语句引用（即只能被 S 内部的 `goto` 跳转到）。

换句话说，**控制流不能从外面进入 S**，既不能 `goto` 进去，也不能由外层 `switch` 分派进去。被指定为控制流受限语句的有：

- `if constexpr` 的每个子语句（[[stmt.if#2]]）；
- `if consteval` 的每个子语句（[[stmt.if#5]]）；
- 展开语句的复合语句（[[stmt.expand#2]]）。

三者的动机各不相同。`if constexpr` 的弃置分支可能根本不会实例化，跳进一个不存在的分支没有意义。`if consteval` 的两个分支一个用于编译期、一个用于运行期，跳进去会绕过分支选择。展开语句的体会被复制 N 份，跳转的目标无法确定是哪一份。

```cpp error
void f(int n) {
    switch (n) {
        if constexpr (true) {
        case 1: ;    // error: case 位于控制流受限语句内，而它所属的 switch 在外面
        }
    }
}
```

```cpp error
void g() {
    goto inside;     // error: 不能 goto 进 if constexpr 的子语句
    if constexpr (true) {
    inside: ;
    }
}
```

从里面往外跳是允许的：

```cpp ok
void h(int n) {
    if constexpr (sizeof(int) == 4) {
        if (n) goto out;     // OK: 从控制流受限语句内跳到外面
    }
out:;
}
```

### 展开语句中不得有标识符标号（¶4）{{c++26}}

¶4 标识符标号不得被展开语句包围。即使 `goto` 和标号都在展开语句的体内也不行：体会被实例化 N 次，同一个标号会出现 N 次，违反了同一函数中标号不得重复的规则。（`case`/`default` 标号不受此限制，只要它所属的 `switch` 也在体内。）

```cpp error
void f() {
    template for (auto x : {1, 2}) {
        (void)x;
    again:           // error: 标识符标号被展开语句包围
        ;
    }
}
```

## 表达式语句 [stmt.expr]

¶1 *expression-statement* 的形式是 `expression(opt) ;`。

- 其中的表达式是**弃值表达式**（discarded-value expression，[[expr.context]]）：结果被丢弃，不做数组到指针、函数到指针的转换；只有对 volatile glvalue 的若干简单形式才做左值到右值转换。所以 `vol;` 会产生一次 volatile 读，而 `nonvol;` 什么也不做。
- 表达式语句的所有副作用在下一条语句执行前完成。这是语句层面的顺序保证：表达式语句的完整表达式结束处就是一个序列点。
- 省略表达式的 `;` 称为**空语句**（null statement），常用作循环的空体，也是 `[[fallthrough]];` 的载体。

```cpp run ok
volatile int reg = 0;
int plain = 0;
int main() {
    reg;          // 弃值表达式，volatile id-expression：执行一次 volatile 读
    plain;        // 弃值表达式：什么也不做（编译器可能警告"表达式结果未使用"）
    (void)plain;  // 惯用法：显式弃值，抑制警告
    ;             // 空语句
}
```

!!! note "nodiscard 属性与弃值表达式"
    `[[nodiscard]]` 的警告（[[dcl.attr.nodiscard]]）针对的正是函数调用作为弃值表达式的场景，而表达式语句 `f();` 就是最常见的弃值表达式。转换为 `void` 是表示有意丢弃结果的标准写法。

## 复合语句 [stmt.block]

¶1 **复合语句**（compound statement，又称块，block）把一串语句组合成一条语句：`{ statement-seq(opt) label-seq(opt) }`。末尾的 *label-seq* 见上文，位于末尾的标号视为后接一个空语句。

¶2（注）复合语句定义一个块作用域（[[basic.scope.block]]）。块作用域的意义体现在 [[stmt.dcl]] 中：离开块时，块内已构造的自动变量按逆序销毁。

```cpp run ok
#include <cstdio>
struct Tr { const char* n; ~Tr() { std::printf("~%s\n", n); } };
int main() {
    Tr a{"a"};
    {
        Tr b{"b"};
        Tr c{"c"};
    }               // 打印 ~c ~b
    Tr d{"d"};
}                   // 打印 ~d ~a
```

## 陷阱

!!! pitfall "条件里的赋值与比较"
    `if (x = 0)` 是合法的（表达式条件，值为 0，即 false），这是 C 系语言中常见的 bug 来源。编译器通常会对条件中的赋值给出警告，加一层括号 `if ((x = 0))` 表示有意为之。而 `if (int x = 0)` 是声明，不会被误解为比较。

!!! pitfall "lambda 是控制流的边界"
    `break`、`continue`、`case`、`goto`、`return` 都不能穿过 lambda 体。在 lambda 里写 `return` 只是从 lambda 返回；如果想从外层函数返回，需要通过返回值传递信号。

## 思考题

!!! question "1. 下面的条件里声明了几个变量？"
    ```cpp
    struct T { T(int); explicit operator bool() const; };
    int a = 1;
    void f() { while (T(a) = 2) { } }
    ```

<details markdown="1">
<summary>答案</summary>

一个：`T a = 2`。¶7 规定，条件既能解析为表达式又能解析为声明时，按声明处理；`T(a)` 中多余的括号在声明符中是允许的（`T (a)` 与 `T a` 相同）。于是每次循环都会构造一个新的局部 `a`（初始化为 `T(2)`），测试它，在循环结束（或进入下一轮）时销毁它（[[stmt.while#2]]）。外层的全局 `a` 根本没有用到。
</details>

!!! question "2. switch 中的 lambda 体里能写 fallthrough 语句吗？"
    ```cpp
    void f(int n) {
        switch (n) {
        case 0: [] { [[fallthrough]]; }();
        case 1: ;
        }
    }
    ```

<details markdown="1">
<summary>答案</summary>

不能。[[dcl.attr.fallthrough#1]] 要求 fallthrough 语句"出现在一个包围它的 switch 语句之内"。包围关系建立在子语句之上，而 lambda 体不是子语句（¶2 注 1），所以这个 `switch` 不包围 lambda 体里的 fallthrough 语句，程序非良构。
</details>

!!! question "3. 为什么 `if (auto [a, b] = std::pair{1, 2})` 是非良构的，而 `if (auto [p, ec] = std::from_chars(...))` 可以？"

<details markdown="1">
<summary>答案</summary>

结构化绑定条件的值，是判定变量 e（整个对象）按语境转换为 bool 的结果（¶5、¶6）。`std::pair<int,int>` 没有到 bool 的转换，转换非良构，所以程序非良构；`std::from_chars_result` 在 C++26 中提供了 `operator bool`，所以可以。绑定 `a`、`b`（或 `p`、`ec`）本身从不参与测试。
</details>

## 小结

| 概念 | 要点 |
|---|---|
| 子语句 | 标号后的语句、块中的语句、各分支/循环体/展开体；不含 *init-statement*；不含 lambda 体 |
| 包围 | 子语句 + *init-statement* + try/handler 的块，传递闭包；不穿透 lambda |
| 条件 | 表达式，或 `说明符 声明符 = / {}` 声明，或 {{c++26}} 结构化绑定声明；歧义时当声明 |
| 判定变量 | 声明的变量；结构化绑定时是无名变量 *e* |
| 条件的值 | 判定变量（或表达式）按语境转换为 bool；`switch` 例外 |
| 说明符限制 | 只能是 type-specifier 或 `constexpr`；不能声明数组/函数，不能定义类型 |
| 标号 | 函数作用域、不能重名；C++23 起可出现在块末尾；不得被展开语句包围 |
| 控制流受限语句 | 不能从外面 `goto`/`case` 进去：`if constexpr`、`if consteval` 的分支，展开语句的体 |
| 表达式语句 | 弃值表达式；副作用在下一条语句前完成；`;` 是空语句 |
| 复合语句 | 块作用域；末尾可以有标号 |
