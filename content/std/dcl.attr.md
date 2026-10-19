---
title: 属性
summary: 属性与注解的语法（[[...]]、using 前缀、作用于谁）、未知属性被忽略、标准属性的可忽略性规则、[[ 的词法限制；以及 deprecated、fallthrough、indeterminate、likely/unlikely、maybe_unused、noreturn、注解等标准属性
status: done
covers: dcl.attr.grammar, dcl.attr.deprecated, dcl.attr.fallthrough, dcl.attr.indet, dcl.attr.likelihood, dcl.attr.unused, dcl.attr.noreturn, dcl.attr.annotation
papers: N2761, P0028R4, P0283R2, P2552R3, P2156R1, P0188R1, P0212R1, P0479R5, P2795R5, P3394R4, P2361R6, P2173R1
related: dcl.align, dcl.attr.assume, dcl.attr.nodiscard, dcl.attr.nouniqueaddr, cpp.cond, basic.indet, stmt.switch, stmt.expand, intro.abstract, expr.const.reflect
tags: 属性, 注解, 诊断, 优化提示
updated: 2026-10-17
---

**属性**（attribute）是 C++11 引入的一套统一语法 `[[...]]`，用来给源代码中的实体、语句、类型附加额外信息。在它之前，每个编译器都有自己的写法，如 GCC 的 `__attribute__((noreturn))`、MSVC 的 `__declspec(noreturn)`。标准属性把一部分最常用的信息标准化，同时为厂商属性提供了统一的语法形式。C++26 又在同样的方括号里加入了**注解**（annotation）`[[=expr]]`，供静态反射读取。

本页覆盖以下内容：

- [dcl.attr.grammar]：语法、作用对象、未知属性、可忽略性；
- 若干较小的标准属性：`deprecated`、`fallthrough`、`indeterminate`、`likely`/`unlikely`、`maybe_unused`、`noreturn`，以及注解。

较大的几个各有专页：[[dcl.align|alignas]]、[[dcl.attr.assume|assume]]、[[dcl.attr.nodiscard|nodiscard]]、[[dcl.attr.nouniqueaddr|no_unique_address]]。

## 语法（[dcl.attr.grammar] ¶1）

按 ¶1，属性和注解为各种源代码构造（类型、变量、名字、契约断言、块、翻译单元）指定附加信息。

```text
attribute-specifier:
    [ [ attribute-using-prefix(opt) attribute-list ] ]
    [ [ annotation-list ] ]
    alignment-specifier
attribute-using-prefix:   using attribute-namespace :
attribute-list:           attribute(opt) | attribute-list , attribute(opt)
                        | attribute ... | attribute-list , attribute ...
annotation-list:          annotation ...(opt) | annotation-list , annotation ...(opt)
attribute:                attribute-token attribute-argument-clause(opt)
annotation:               = constant-expression
attribute-token:          identifier | attribute-namespace :: identifier
attribute-argument-clause:( balanced-token-seq(opt) )
balanced-token:           ( … ) | [ … ] | { … } | [: … :] | 除这些括号以外的任何记号
```

从语法中可以看出几点：

- `alignas(...)` 在语法上也是一种 *attribute-specifier*，所以它出现的位置规则与属性相同（但它的语义在 [[dcl.align]]）。
- 一个 `[[...]]` 要么全是属性，要么全是注解，不能混合。
- *attribute-list* 中的属性可以为空（`[[ , noreturn, ]]` 合法）；`[[]]` 完全没有效果（¶4）。
- *attribute-argument-clause* 的内容是平衡记号序列，标准语法不关心里面是什么，参数形式由每个属性自行规定（¶3）。这让厂商属性可以有任意复杂的参数。
- *balanced-token* 包括反射的拼接括号 `[: … :]`（C++26）。

## `using` 前缀（¶2）

按 ¶2，如果 *attribute-specifier* 含 *attribute-using-prefix*，其后的 *attribute-list* 中不得出现带命名空间的属性记号，每个属性记号都视为加了 `N::` 前缀。注 1 说明，这条规则不约束前缀如何影响参数子句中的记号。

```cpp title="attr-using.cpp" error
[[using CC: opt(1), debug]]           // 等同于 [[CC::opt(1), CC::debug]]
    void f() {}
[[using CC: opt(1)]] [[CC::debug]]    // 等同于 [[CC::opt(1)]] [[CC::debug]]
    void g() {}
[[using CC: CC::opt(1)]]              // error: 不能同时使用 using 前缀和带命名空间的属性记号
    void h() {}
```

引入这一语法（C++17，[[P0028R4]]）是因为厂商属性往往成组出现（`[[gnu::always_inline, gnu::hot, gnu::nonnull]]`），using 前缀可以省去重复的命名空间。`CC` 是虚构的命名空间，所以 Clang 对上面的 `f`、`g` 会给出未知属性被忽略的警告。

## 一般规则（¶3–¶6）

¶4 包含好几条独立的规则：

1. 属性后的省略号 `...` 只有在该属性的规范允许时才能出现，此时它是包展开。（标准属性都不允许；`alignas` 和注解另有包展开规则。）
2. 不含任何属性的 *attribute-specifier* 没有效果。
3. *attribute-list* 中属性记号的顺序无关紧要。
4. 属性记号中出现的关键字，或满足标识符语法的替代记号，都视为标识符，所以厂商可以定义 `[[vendor::const]]`、`[[gnu::and]]` 之类的属性。
5. 属性记号中的标识符不做名字查找。`[[noreturn]]` 中的 `noreturn` 不是一个声明过的名字。
6. 属性记号决定参数子句（如果有）的额外要求。

¶5 是一条注：除非另有规定，标准规定的属性记号不能用作宏名（[[cpp.replace.general]]）。`#define noreturn ...` 会破坏 `[[noreturn]]`，所以是禁止的。（C 的 `<stdnoreturn.h>` 定义了 `noreturn` 宏，这正是 C++ 不提供这个头的原因之一。）

按 ¶6，注解后跟省略号是包展开（[[temp.variadic]]）。

## 属性属于谁：appertain（¶7）

按 ¶7，每个 *attribute-specifier-seq* 都**属于**（appertain to）某个实体或语句，具体属于谁由它出现的语法位置决定（见 [[stmt.pre]]、[[dcl.pre]]、[[dcl.meaning]] 等各处的规定）。具体规则是：

- 如果属性序列中有某个属性不允许用于它所属的实体或语句，程序非良构；
- 如果属性序列属于友元声明，该声明必须是定义；
- 注 4：属性序列不能属于显式实例化（[[temp.explicit]]）。

属性属于谁完全由位置决定，这也是属性最容易写错的地方：

```cpp title="attr-position.cpp" ok
[[nodiscard]] int f1();        // 声明开头：属于被声明的实体 f1
int f2 [[nodiscard]] ();       // 紧跟 declarator-id：属于 f2
int [[]] x;                    // 紧跟 decl-specifier-seq：属于类型（此处为空，无效果）
struct [[deprecated]] S {};    // class-key 之后：属于类 S
enum E { a [[deprecated]] };   // 枚举量之后：属于枚举量
void g(int n) {
    if (n) [[unlikely]] { }    // 语句之前：属于语句
}

int main() {}
```

为什么友元声明必须是定义？非定义的友元声明可能是某个函数的第一次声明，却出现在类中。如果允许它带属性，各个类的友元声明都可以给同一函数添加属性，不同类给出的属性可能互相矛盾，也很难确定它对哪些其他声明可见。限制为定义后，属性就只有一个来源。

```cpp title="attr-friend.cpp" error
struct S1 {
    [[deprecated]] friend void fr1();                 // error: 带属性的友元声明必须是定义
};
struct S2 {
    [[nodiscard]] friend int fr2(S2) { return 1; }    // OK: 是定义
};
```

## 未知属性与可忽略性（¶8）

¶8 体现了属性设计思路的核心。

首先，**未知属性被忽略**。对于本文档没有规定的属性记号（包括带命名空间的），行为由实现定义；实现不认识的属性记号会被忽略。这样，同一份代码可以同时带上多个编译器的厂商属性：

```cpp title="attr-unknown.cpp" ok
[[gnu::always_inline, msvc::forceinline, clang::always_inline]]
inline int add(int a, int b) { return a + b; }    // 每个编译器只认自己的，忽略其他

[[unknown_attr]] int x;    // OK: 被忽略（Clang 给 -Wunknown-attributes 警告）

int main() { return add(0, 0) + x; }
```

C++11 最初规定不认识的属性的行为由实现定义，实现可以报错；C++17（[[P0283R2]]）改为必须忽略。

其次，误用标准属性是非良构的（注 5）。如果标准规定的属性违反了作用对象规则或参数语法，程序非良构。所以 `[[noreturn]] int x;` 必须诊断，而 `[[vendor::noreturn]] int x;` 只会被忽略，或者由厂商决定如何处理。

第三是**可忽略性**（注 6，C++26 措辞，[[P2552R3]]）：

!!! std
    The *attribute*s specified in [dcl.attr] have optional semantics: given a well-formed program, removing all instances of any one of those *attribute*s results in a program whose set of possible executions for a given input is a subset of those of the original program for the same input…

    标准属性具有可选的语义：从一个良构程序中删去某一种标准属性的所有实例，得到的程序对同一输入的可能执行集合，是原程序可能执行集合的子集（不考虑实现对该属性另行给出的保证）。

直观地说，**删掉标准属性永远不会让程序出现新的行为**。

- 删掉 `[[nodiscard]]`、`[[deprecated]]`、`[[maybe_unused]]`、`[[fallthrough]]`、`[[likely]]`：只影响警告和优化，执行集合不变。
- 删掉 `[[assume(e)]]`：原程序在 `e` 为假时是 UB（任何执行都可能发生），删掉后变成确定的执行，是子集。
- 删掉 `[[noreturn]]`：原程序中返回是 UB，删掉后变成正常返回，是子集。
- 删掉 `[[no_unique_address]]`：布局可能改变，但布局本来就是未指定的，`sizeof` 的可能值都在原来允许的集合中。
- 删掉 `[[indeterminate]]`：原来读取是 UB，删掉后变成错误行为（erroneous behavior），是子集。

这条规则意味着，标准属性不能改变程序的语义，只能提供可以忽略的信息。它也防止委员会以属性语法把真正影响语义的特性（比如契约）加进语言。

最后是**保留名字**。以下属性记号保留给未来标准化：

- ¶8.1：不带命名空间且本文档未规定的记号。所以不要自己发明 `[[my_attr]]`，应当用 `[[mycompany::my_attr]]`；
- ¶8.2：命名空间为 `std` 后跟零个或多个数字（`std`、`std1`、`std23`……）。

推荐做法：每个实现为自己的属性命名空间选一个有辨识度的名字（`gnu`、`clang`、`msvc`）。

## `[[` 的词法限制（¶9）

¶9：两个连续的左方括号 `[[` **只能**出现在引入 *attribute-specifier* 的地方，或者在 *attribute-argument-clause* 的平衡记号序列内部。注 7：即使在不允许属性的位置、即使括号能匹配另一种语法，出现 `[[` 也是非良构的。

```cpp title="attr-double-bracket.cpp" error
int p[10];
void f() {
    int x = 42, y[5];
    int(p[[x] { return x; }()]);    // error: 不是对 p 元素的函数式转换
    y[[] { return 2; }()] = 2;      // error: 即使这里根本不允许属性
    y[ [] { return 2; }()] = 2;     // error: 空格不改变"两个连续的 [ 记号"
    y[([] { return 2; })()] = 2;    // OK: 用括号隔开
    int i [[vendor::attr([[]])]];   // OK: 在属性参数内部可以出现 [[
    (void)i;
}
```

为什么这么严格？因为属性可以出现在非常多的位置，一个 `[[` 是"属性开始"还是"下标 + lambda"，需要无限向前看才能确定。标准选择在词法层面一刀切：`[[` 就是属性。注意规则说的是两个连续的 `[` **记号**，空白不能把它们隔开——`y[ [] { … }()]` 同样非良构。下标里放 lambda 时，要用圆括号把 lambda 包起来。

## 标准属性一览与 `__has_cpp_attribute`

可以用预处理器的 `__has_cpp_attribute(name)` 检测属性是否受支持（[[cpp.cond#5]]）。对标准属性，值是 0 或下表中的值（选哪个由实现定义）；各属性的推荐做法都要求，如果实现不打算真正利用该属性（不发警告、不做优化），就应该返回 0。

| 属性 | 用于 | 作用 | 引入 | `__has_cpp_attribute` | 本站 |
|---|---|---|---|---|---|
| `alignas` | 变量、数据成员、类 | 对齐要求 | C++11 | （不是属性记号） | [[dcl.align]] |
| `assume(expr)` | 空语句 | 优化假设；为假时运行期 UB | C++23 | 202207L | [[dcl.attr.assume]] |
| `deprecated("msg")` | 类、别名、变量、函数、命名空间、枚举、枚举量、概念、特化 | 弃用警告 | C++14 | 201309L | 下文 |
| `fallthrough` | 空语句 | 有意的 case 贯穿 | C++17 | 201603L | 下文 |
| `indeterminate` | 自动变量、函数形参 | 不确定值而非错误值 | C++26 | 202403L | 下文 |
| `likely` / `unlikely` | 语句、标签 | 分支概率提示 | C++20 | 201803L | 下文 |
| `maybe_unused` | 实体、结构化绑定、标签 | 抑制未使用警告 | C++17 | 201603L | 下文 |
| `nodiscard("msg")` | 函数、lambda、类、枚举、构造函数 | 丢弃返回值时警告 | C++17 | 201907L | [[dcl.attr.nodiscard]] |
| `noreturn` | 函数、lambda | 函数不返回；返回则运行期 UB | C++11 | 200809L | 下文 |
| `no_unique_address` | 非静态数据成员 | 潜在重叠子对象 | C++20 | 201803L | [[dcl.attr.nouniqueaddr]] |
| `[[=expr]]` 注解 | 多种声明、基类说明符 | 供反射读取的常量 | C++26 | 无（用特性测试宏） | 下文 |

在 Clang 23 上实测，除 `indeterminate` 返回 0（尚未实现）外，其余均返回上表中的值。

## deprecated（[dcl.attr.deprecated]）

按 ¶1，`deprecated` 标记仍然允许使用、但出于某种原因不鼓励使用的名字和实体（注 1 举例说，比如已过时或不安全）。它可以带一个参数 `( unevaluated-string )`，用于说明理由或建议替代品。

按 ¶2，它可用于以下声明：类、类型别名、变量、非静态数据成员、函数、命名空间、枚举、枚举量、概念、模板特化。

按 ¶3，先前没有该属性的实体可以在后来的重声明中加上它，反之亦然；注 3 说明，一旦标记为弃用，后来的重声明不能取消弃用。不同形式（有无参数、参数不同）的重声明都是允许的。

¶4 的推荐做法是：如果程序在声明之外引用被弃用的名字或实体（在带该属性的声明之后），实现应当给出诊断，并包含属性参数中的文本。

```cpp title="attr-deprecated.cpp" ok
[[deprecated("use g2() instead")]] void g1();
void g2();

enum Mode { fast, safe, legacy [[deprecated]] };
namespace [[deprecated]] old_api { inline int v = 1; }

struct Widget;
struct [[deprecated("Widget is going away")]] Widget;   // 后来的重声明加上弃用：OK

void use() {
    g2();                        // OK
    // g1();                     // 警告：'g1' is deprecated: use g2() instead
    // Mode m = legacy;          // 警告
    // int x = old_api::v;       // 警告
}

int main() {}
```

注意，弃用针对的是引用，所以声明本身和重声明不会触发诊断；而且只有在带属性的声明之后的使用才应警告。

## fallthrough（[dcl.attr.fallthrough]）

按 ¶1，`fallthrough` 只能用于空语句（null statement），这样的语句称为[[g:fallthrough-statement|贯穿语句]]（fallthrough statement）；它不得带参数。约束如下：

- 贯穿语句只能出现在某个外围 `switch` 语句（[[stmt.switch]]）中；
- 贯穿语句之后下一条将要执行的语句，必须是带有同一个 `switch` 的 `case` 或 `default` 标签的语句；
- 如果贯穿语句位于某个迭代语句中，下一条语句还必须属于最内层迭代语句的子语句的同一次执行，不能借助循环贯穿；
- 如果没有这样的语句，程序非良构；
- 贯穿语句的最内层 `switch` 必须包含在它的最内层展开语句（[[stmt.expand]]，C++26）之内（如果有），不能从 `template for` 展开出来的一份代码贯穿到另一份。

¶2 的推荐做法是：贯穿语句应当抑制“一个 case 标签可以从另一个 case 标签到达”这类警告；如果贯穿语句在动态上不可达，实现应当警告。

```cpp title="attr-fallthrough.cpp" error
void g(), h(), i();

void f(int n) {
    switch (n) {
    case 1:
    case 2:                     // 相邻标签之间没有语句，从来不需要 fallthrough
        g();
        [[fallthrough]];        // OK
    case 3:                     // 不鼓励在这里警告
        do {
            [[fallthrough]];    // error: 下一条语句不在同一次循环子语句执行中
        } while (false);
    case 5:
        h();
    case 4:                     // 实现可以在这里警告（未标注的贯穿）
        i();
        [[fallthrough]];        // error: 后面没有 case 标签
    }
}
```

最后一行的错误很常见：为了风格统一，在最后一个 case 后面也写上 `[[fallthrough]];`，这是非良构的。Clang 的诊断是 "fallthrough annotation does not directly precede switch label"。

## indeterminate（[dcl.attr.indet]）{{c++26}}

C++26 把读取未初始化的自动变量从 UB 改为错误行为（[[basic.indet]]，[[P2795R5]]）：变量获得一个由实现选择的错误值，读取它是错误的但有定义，实现可以诊断或终止，但不能假设它不发生。这对安全有利，代价是编译器可能需要真的给变量写入一个值。`[[indeterminate]]` 就是退出这一机制的手段。

按 ¶1，`indeterminate` 可以用于自动存储期的块变量的定义，或函数声明中的形参声明；它不得带参数。它指定该自动存储期对象的存储最初是不确定的（indeterminate），而不是错误的（erroneous）。

按 ¶2，如果函数形参带此属性，必须在函数的第一次声明中就带上；如果不同 TU 的第一次声明中对同一形参一个带、一个不带，IFNDR。

¶3 是一条注：读取标了 `[[indeterminate]]` 的未初始化变量可能导致未定义行为：

```cpp title="attr-indeterminate.cpp"
void f(int);
void g() {
    int x [[indeterminate]], y;
    f(y);              // 错误行为（erroneous behavior）
    f(x);              // 未定义行为
}

struct T {
    T() {}
    int x;
};
int h(T t [[indeterminate]]) {
    f(t.x);            // 以下面的方式调用时是未定义行为
    return 0;
}
int _ = h(T());
```

为什么形参也需要？按值传递的类对象形参是一个新的自动对象，由复制/移动构造函数初始化；`T` 的构造函数没有初始化 `x`，于是 `t.x` 的初始值在 C++26 中是错误值。对性能敏感的代码（例如传递一个大缓冲区的包装类），可以用 `[[indeterminate]]` 告诉实现不必为它写入错误值。

什么时候用？只有在测量表明给变量写错误值带来了不可接受的开销时才用。典型例子是栈上的大缓冲区 `char buf [[indeterminate]] [65536];`，它随后马上会被 `read()` 填满。

!!! impl "实现状态"
    截至 Clang 23，`__has_cpp_attribute(indeterminate)` 为 0，`[[indeterminate]]` 被当作未知属性忽略（给出 `-Wunknown-attributes` 警告）。按可忽略性规则，忽略它是允许的：程序行为从可能 UB 变为错误行为，是子集。GCC 和 Clang 早已有 `-ftrivial-auto-var-init=zero|pattern` 选项，可视为错误值机制的先驱；Clang 另有 `[[clang::uninitialized]]` 用于逐变量退出。

## likely / unlikely（[dcl.attr.likelihood]）{{c++20}}

按 ¶1，`likely` 和 `unlikely` 可以用于标签或语句；它们不得带参数，同一个属性序列中也不能同时出现两者。

¶2 是一条注，要点如下：

- `likely` 的意图是，让实现针对包含它的执行路径任意地比不包含它的路径更可能发生的情形做优化；`unlikely` 反之。
- 一条执行路径包含一个标签，当且仅当它包含跳转到该标签的动作。
- 过度使用可能导致性能下降。

```cpp title="attr-likely.cpp" ok
void g(int);
int f(int n) {
    if (n > 5) [[unlikely]] {       // 认为 n > 5 任意地不可能
        g(0);
        return n * 2 + 1;
    }

    switch (n) {
    case 1:
        g(1);
        [[fallthrough]];
    [[likely]] case 2:              // 认为 n == 2 比 n 取其他值任意地更可能
        g(2);
        break;
    }
    return 3;
}

int main() {}
```

注意“路径包含标签当且仅当包含跳转到它的动作”这一点：上例中从 `case 1` 贯穿到 `case 2` 的路径不包含 `case 2` 标签（没有跳转），所以 `[[likely]]` 只表达 `switch` 直接跳到 `case 2` 的可能性。

!!! pitfall "属性放在哪条语句上"
    在 `if (c) [[likely]] stmt;` 中，属性属于 `stmt`（then 分支），不属于条件。写 `if ([[likely]] c)` 是语法错误。`else [[unlikely]] { … }` 同理。Clang/GCC 把它们映射为分支权重元数据，效果类似 `__builtin_expect`，但作用于语句而不是表达式。

## maybe_unused（[dcl.attr.unused]）

按 ¶1，`maybe_unused` 表示一个名字、标签或实体可能是有意不使用的；它不得带参数。

按 ¶2，它可用于以下声明：类、类型别名、变量（包括结构化绑定声明）、单个结构化绑定（C++26，[[dcl.struct.bind]]）、结果绑定（[[dcl.contract.res]]，C++26 契约）、非静态数据成员、函数、枚举、枚举量；以及标识符标签（[[stmt.label]]）。

按 ¶3，它可以在后来的重声明中加上或去掉；实体在第一个标记它的声明之后即视为已标记。

¶4 的推荐做法如下：

- 对标记了的实体，实现不应就它或它的结构化绑定是否被使用给出警告；
- 对没有标记的结构化绑定声明，只有当它的所有结构化绑定都未被使用时才应警告；
- 对标记了的标签，不应警告其使用与否。

```cpp title="attr-maybe-unused.cpp" ok
#include <cassert>

[[maybe_unused]] static void f([[maybe_unused]] bool thing1,
                               [[maybe_unused]] bool thing2) {
    [[maybe_unused]] bool b = thing1 && thing2;
    assert(b);               // NDEBUG 时 b 未被使用
#ifdef NDEBUG
    goto x;
#endif
    [[maybe_unused]] x: ;    // NDEBUG 未定义时标签未被使用
}

int main() {}
```

未使用警告本身不是标准中的概念，所以这个属性的效果完全依赖于推荐做法。

## noreturn（[dcl.attr.noreturn]）

按 ¶1，`noreturn` 指定函数不返回；它不得带参数，可用于函数或 lambda 的调用运算符（C++23，[[P2173R1]]）。如果函数的任何声明带了 `noreturn`，它的第一次声明就必须带；如果一个 TU 中带、另一个 TU 中不带，IFNDR。

按 ¶2，如果函数 `f` 此前已声明为 `noreturn`，而对它的某次调用最终返回了，行为是**运行期未定义**的（runtime-undefined，[[intro.defs]]）；在常量求值中，是否视为非常量由实现决定。注 1 说明，函数可以通过抛出异常结束，这不算返回。

¶3 的推荐做法是：如果标记为 `noreturn` 的函数可能返回，实现应当警告。

```cpp title="attr-noreturn.cpp" ub
[[noreturn]] void f() {
    throw "error";             // OK: 抛异常不是返回
}

[[noreturn]] void q(int i) {   // 用 i <= 0 调用时行为未定义
    if (i > 0)
        throw "positive";
}                              // Clang: warning: function declared 'noreturn' should not return

int main() {
    try { q(0); } catch (...) {}   // UB: q 返回了
}
```

为什么要求第一次声明就带？编译器第一次看到函数调用时，就要决定是否在调用之后生成代码（以及是否把后续代码视为不可达）。如果到后来的声明才补上 `noreturn`，之前编译的调用点已经按会返回处理了。

`noreturn` 的作用对象是函数而不是类型，所以 `[[noreturn]] void (*fp)();` 非良构。`std::abort`、`std::exit`、`std::terminate`、`std::unreachable` 都是 `[[noreturn]]` 的。

## 注解（[dcl.attr.annotation]）{{c++26}}

注解是 C++26 静态反射的配套特性（[[P3394R4]]）：在声明上附加任意结构化的编译期常量，再用反射 `std::meta::annotations_of` 读取。和属性不同，注解不是给编译器的提示，而是供程序自己在编译期读取的数据，比如序列化库可以读取 `[[=rename("id")]]` 来决定字段名。

按 ¶1，注解可以用于 *base-specifier*，或以下实体的声明 D：类型、类型别名、变量、函数、非 `void` 类型的函数形参、命名空间、枚举量、非静态数据成员。但以下情况除外：

- ¶1.1：X 的宿主作用域（host scope）与目标作用域不同，或
- ¶1.2：X 是非定义的友元声明；

其中 X 在 D 是函数声明 D′ 的函数声明符中的形参声明时为 D′（¶1.3），否则为 D（¶1.4）。

注 1 说明，函数定义中形参声明上的注解，同时作用于函数形参和对应的变量：

```cpp title="annotation-param.cpp"
#include <meta>

void f([[=1]] int x);
void f([[=2]] int y) {
    constexpr auto rp = parameters_of(^^f)[0];
    constexpr auto ry = variable_of(rp);
    static_assert(ry == ^^y);

    static_assert(annotations_of(rp).size() == 2);   // 两个：[1, 2]
    static_assert(annotations_of(ry).size() == 1);   // 只有 [2]
    static_assert(annotations_of(rp)[1] == annotations_of(ry)[0]);
}
```

按 ¶2，设 E 为 `std::meta::reflect_constant(constant-expression)`，E 必须是常量表达式，它的结果是注解的**底层常量**（underlying constant）。也就是说，注解的值经过 `reflect_constant` 变成一个反射值，因此其类型必须是结构类型（可以作为常量模板实参的类型）。

按 ¶3，每个注解（或其实例化）产生一个唯一的注解。重复的值不会合并：

```cpp title="annotation-count.cpp"
[[=1]] void f();
[[=2, =3, =2]] void g();
void g [[=4, =2]] ();
// f 有 1 个注解；g 有 5 个（两个声明上的注解累积）

template<int> int x [[=1]];
static_assert(annotations_of(^^x<0>) != annotations_of(^^x<1>));   // 每个实例化各有其注解
```

按 ¶4，对注解的替换不在立即语境中（not in the immediate context），所以注解中的替换失败是硬错误，而不是 SFINAE：

```cpp title="annotation-sfinae.cpp"
template<class T>
    [[=T::type()]] void f(T t);

void f(int);

void g() {
    f(0);       // OK: 选中 f(int)……
    f('0');     // error: 替换进注解得到无效表达式（不会因 SFINAE 而被静默丢弃）
}
```

只有在函数模板特化的声明真正实例化时，才会对注解做替换。对 `f(0)`，模板推导出 `T = int`，与非模板 `f(int)` 一样好，非模板胜出，模板特化没有被使用，注解不会被替换。对 `f('0')`，模板推导出 `T = char`，是精确匹配，选中后实例化其声明，替换注解得到 `char::type()`，这是硬错误；而且由于不在立即语境中，这个错误不会让该模板退出候选集。

为什么不放在立即语境中？注解是声明的附加数据，不属于函数签名。如果它能参与 SFINAE，注解就会意外地影响重载决议，这与它只是数据的定位不符。

!!! impl "实现状态"
    截至写作时，本机的 Clang 23（Homebrew，libc++）尚未实现静态反射与注解：`[[=1]]` 语法不被接受，`<meta>` 头不存在。上面三个例子未经编译验证，取自标准例子。GCC 的反射实现和 Bloomberg 的 Clang 反射分支是目前可以试验这些例子的途径。

## 实现视角

!!! impl "属性在编译器中"
    - GCC 和 Clang 内部把 `[[gnu::xxx]]` 与 `__attribute__((xxx))` 映射到同一个属性实现，但两种语法的位置规则不同：GNU 语法的位置相当宽松（编译器常常把它应用到附近合适的声明上），标准语法则严格按位置确定属于谁。把 `__attribute__` 机械改写成 `[[gnu::...]]` 时要注意它是否仍然属于原来的实体。
    - MSVC 支持标准属性和 `msvc::` 命名空间的少量属性（如 `msvc::no_unique_address`），其余厂商功能仍主要通过 `__declspec`。
    - `__has_cpp_attribute` 也适用于厂商属性：`__has_cpp_attribute(clang::musttail)` 等。

## 历史与演进

!!! history "C++11 → C++26"
    - C++11：属性语法（[[N2761]]）；`noreturn`、`carries_dependency`；`alignas`。未知属性的行为由实现定义。
    - C++14：`deprecated`。
    - C++17：`fallthrough`（[[P0188R1]]）、`nodiscard`、`maybe_unused`（[[P0212R1]]）；`using` 前缀（[[P0028R4]]）；未知属性必须被忽略（[[P0283R2]]）；命名空间和枚举量可以带属性。
    - C++20：`likely`/`unlikely`（[[P0479R5]]）、`no_unique_address`；`nodiscard` 可带理由、可用于构造函数；允许在同一个属性列表中重复同一属性（[[P2156R1]]）。
    - C++23：`assume`；lambda 的调用运算符可以带属性（[[P2173R1]]）。
    - C++26：`indeterminate`（[[P2795R5]]）；注解（[[P3394R4]]）；当前草案中已不再有 `carries_dependency`；属性参数中的字符串改为不求值字符串（[[P2361R6]]）；重新表述了标准属性的可忽略性规则（[[P2552R3]]），并加入推荐做法：实现不利用属性时 `__has_cpp_attribute` 应为 0；单个结构化绑定可以带属性（因而可以带 `maybe_unused`）。当前草案还允许 `maybe_unused` 用于标签。

## 陷阱

!!! pitfall "属性不改变语义，这只对标准属性成立"
    厂商属性可以任意改变语义：`[[gnu::packed]]` 改变布局，`[[clang::trivial_abi]]` 改变调用约定，`[[msvc::no_unique_address]]` 改变大小。可忽略性规则只约束 [dcl.attr] 中规定的属性。

!!! pitfall "拼错的属性会被静默忽略"
    `[[nodicard]]`（少了 s）是未知属性，按 ¶8 会被忽略。它不会报错，只有 `-Wunknown-attributes`（Clang）或 `-Wattributes`（GCC）会提醒。建议在 CI 中把这两个警告设为错误。

!!! pitfall "`[[noreturn]]` 并不表示不会抛异常"
    它只承诺不返回，抛出异常是允许的。它与 `noexcept` 毫无关系。

## 思考题

!!! question "思考题 1"
    下面哪些是非良构的，哪些只是被忽略？

    ```cpp
    [[noreturn]] int a;
    [[gnu::noreturn]] int b;
    [[nodiscard]] [[nodiscard]] int c();
    [[my_attr]] int d;
    [[std::my_attr]] int e;
    ```

<details markdown="1">
<summary>答案</summary>

- `a`：非良构，`noreturn` 只能用于函数（¶7 和注 5）。
- `b`：`gnu::noreturn` 是厂商属性，行为由实现定义；GCC/Clang 认识它，会给出诊断（Clang 给出 "only applies to functions" 之类的警告或错误，取决于实现）。标准层面不要求诊断。
- `c`：良构，C++20 起同一属性可以重复（[[P2156R1]]）。
- `d`：被忽略（未知属性）；但 `my_attr` 这种无命名空间的记号是保留给未来标准的（¶8.1），自己用它是不明智的。
- `e`：`std` 命名空间的属性记号保留给未来标准化（¶8.2）；当前实现不认识，会被忽略。
</details>

!!! question "思考题 2"
    为什么 `[[assume(expr)]]` 可以是标准属性，而 C++26 的契约 `pre(expr)` 却不能做成属性？

<details markdown="1">
<summary>答案</summary>

原因在于可忽略性规则（¶8 注 6）。删除 `[[assume]]` 只会让原本 UB 的执行变成有定义的执行，执行集合变小，满足子集条件。而契约检查失败时会调用违约处理函数，可能终止程序；删除契约断言后程序会继续执行，这就引入了原程序中不可能出现的执行（原程序在那里会终止），不是子集。所以契约必须是真正的语言特性，有自己的语法。
</details>

## 小结

!!! summary "要点"
    - 语法形式有 `[[attr]]`、`[[ns::attr(args)]]`、`[[using ns: a, b]]`、`[[=const]]`（注解）、`alignas(...)`。
    - 属性按位置属于某个实体或语句；用错对象的标准属性是非良构的；带属性的友元声明必须是定义。
    - 不认识的属性被忽略；无命名空间的未规定记号与 `std*` 命名空间保留。
    - 标准属性可忽略：删掉它们，可能执行的集合只会变小。
    - `[[` 只能开启属性。
    - `deprecated`、`maybe_unused`、`fallthrough`、`likely`/`unlikely` 只影响诊断与优化；`noreturn` 返回、`assume` 为假是运行期 UB；`indeterminate` 把错误行为退回为可能的 UB；注解是给反射读取的数据。
