---
title: 标识符
summary: 标识符的文法（基于 Unicode XID 属性与 UAX #31）、NFC 要求、特殊含义标识符（final、override、import、module、pre、post），以及保留给实现的标识符（双下划线、_大写、全局 _小写）。
status: draft
papers: P1949R7
related: lex.key, lex.charset, uaxid, reserved.names, cpp.replace.general, over.literal
tags: 标识符, Unicode, 保留名
updated: 2026-10-17
---

[[lex.name]] 规定了什么样的字符序列是**标识符**（identifier），哪些标识符在特定上下文中有特殊含义，以及哪些标识符保留给实现。它涉及三个层次的问题：

1. 字符层面：哪些 Unicode 字符可以出现在标识符中？（文法与 ¶1）
2. 语法层面：`override`、`final`、`import` 等为什么不是关键字？（¶2–¶3）
3. 约定层面：程序员不能使用哪些名字？（¶4）

## 文法

```
identifier:
    identifier-start
    identifier identifier-continue
identifier-start:
    nondigit
    an element of the translation character set with the Unicode property XID_Start
        or the Unicode property ID_Compat_Math_Start
identifier-continue:
    digit
    nondigit
    an element of the translation character set with the Unicode property XID_Continue
        or the Unicode property ID_Compat_Math_Continue
nondigit: one of  a–z  A–Z  _
digit: one of  0–9
```

用通俗的话说：

- 首字符可以是 `_`、ASCII 字母、任何具有 Unicode XID_Start 属性的字符（各种文字的字母：汉字、希腊字母、西里尔字母等），或数学兼容记号的起始字符；
- 后续字符可以是上述字符、数字、具有 XID_Continue 属性的字符（组合附加符号、各文字的数字、连接标点等），或数学兼容记号的后续字符。

```cpp run title="unicode-ident.cpp" ok
int 变量 = 1;               // 汉字有 XID_Start
double \u03C0 = 3.14159;    // π，用 UCN 写也一样
int naïve = 2;              // ï 是单个预组合字符 U+00EF（NFC）
int main() { return 变量 + naïve - 3; }
```

不允许的典型例子：

```cpp title="bad-ident.cpp" error
int 😀 = 1;      // error：emoji 没有 XID_Start
int €uro = 3;    // error：€ 是货币符号，不是字母
int $x = 4;      // error（就标准而言）：$ 不是 nondigit，也没有 XID_Start
```

也有出人意料的情形：中点 `·`（U+00B7）具有 XID_Continue 属性，所以 `int a·b = 2;` 声明的是一个名为 `a·b` 的变量，而不是 a 点乘 b。

### ID_Compat_Math：数学记号 {{c++26}}

当前草案在 XID 之外加入了 Unicode 的 ID_Compat_Math_Start / ID_Compat_Math_Continue 属性，对应 UAX #31 的数学兼容记号配置（Mathematical Compatibility Notation profile，[[uaxid.def.general]]）。于是 `∂`（U+2202）、`∇`（U+2207）、`∞`（U+221E）可以作为标识符的首字符，`₀`（U+2080）这样的上下标数字可以出现在标识符中间：

```cpp run title="math-ident.cpp" ok
double ∂x = 0.1;
double x₀ = 1.0;
int main() { return ∂x < x₀ ? 0 : 1; }
```

在 C++23 中，这些字符不能出现在标识符中。实测 Clang 23 接受上例，但给出 "mathematical notation character … in an identifier is a Clang extension" 警告，可见编译器的诊断措辞还停留在 C++23 的规则上。

### `$` 不是标识符字符

尽管 C++26 把 `$` 加入了基本字符集（[[lex.charset]]），它依然不是 *nondigit*，也没有 XID 属性，所以按标准不能出现在标识符中。GCC、Clang、MSVC 都把 `$` 作为扩展接受（Clang 在 `-pedantic` 下给出 `-Wdollar-in-identifier-extension` 警告）。

## ¶1：Unicode 规则

¶1 注 1 说明，XID_Start 和 XID_Continue 由 Unicode 标准的 UAX #44 描述。规范性的要求只有一句：

!!! std
    The program is ill-formed if an *identifier* does not conform to Normalization Form C as specified in the Unicode Standard.

    标识符必须是 NFC（规范组合形式），否则非良构。

为什么要求 NFC？因为在 Unicode 中，看起来一样的字符串可能有多种编码：`é` 可以是一个预组合字符 U+00E9，也可以是 `e` 加 U+0301（组合尖音符）。如果不要求规范化，两个外观完全相同的标识符可能是不同的名字。这不仅严重损害可读性，还会给链接带来问题：不同编译器、不同编辑器可能产生不同的字节序列，导致符号对不上（[[diff.cpp20.lex]] 给出的理由正是确保链接器行为一致）。

标准选择要求输入已是 NFC，而不是让编译器先规范化再比较，好处是编译器只需检查而无需改写；输入文件中字节不同的标识符就一定是不同的标识符。

```cpp title="nfc.cpp" error
int a\u0300 = 1;   // error：a + U+0300 组合重音符，不是 NFC（NFC 形式是 U+00E0 à）
int \u212B = 2;    // error：U+212B ANGSTROM SIGN 在 NFC 下变成 U+00C5，故自身不是 NFC
```

!!! impl "实现现状"
    实测 Clang 23 不检查 NFC：上例以 `-std=c++2c -pedantic` 编译，不给出任何诊断。这偏离了标准（标准要求诊断）。所以不要依赖编译器替你发现规范化形式的差异，应当在编辑器或 CI 中统一做 NFC 规范化。

注 2：标识符区分大小写。注 3：附录 [[uaxid]] 逐条比较了 UAX #31 的要求与 C++ 的规则（C++ 满足 R1 默认标识符和 R4 等价规范化标识符两条要求）。注 4：在阶段 4，*identifier* 还包括那些后来在阶段 7 被区分为关键字的预处理记号。因此 `#if` 里可以出现 `new`、`int`（都被当作标识符替换为 0），`#define` 的名字在文法上也可以拼成关键字（但这被 [[cpp.replace.general]] 禁止）。

!!! history "从允许字符表到 UAX #31"
    C++11 到 C++20 用附录 E 的一张码位区间表列出标识符中允许的字符（源自 ISO/IEC TR 10176 与 C99），另有一张表列出不得作为首字符的字符。这张表过于宽松，许多符号甚至一些不可见字符都被允许。C++23 采纳 [[P1949R7]]，改用 Unicode 的 XID_Start/XID_Continue 属性并要求 NFC。[[diff.cpp20.lex]] 记录了这一不兼容变化：原来合法的一些标识符（例如含 emoji 的）变为非良构。

## ¶2–¶3：特殊含义标识符

¶2 表 4 中的标识符出现在特定上下文中时具有特殊含义（[[g:identifier-with-special-meaning|特殊含义标识符]]）。文法引用它们时直接写出，而不经过 *identifier* 产生式。**除非另有规定**，某个 *identifier* 是否具有特殊含义一旦有歧义，都按普通 *identifier* 解释。

表 4（当前草案）：

| 标识符 | 引入 | 上下文 |
|---|---|---|
| `final` | C++11 | 类头（[[class.pre]]）、虚函数声明的 *virt-specifier*（[[class.mem]]） |
| `override` | C++11 | 虚函数声明的 *virt-specifier* |
| `import` | C++20 | 模块导入声明与 import 指令（[[module.import]]、[[cpp.import]]） |
| `module` | C++20 | 模块声明与 module 指令（[[module.unit]]、[[cpp.module]]） |
| `pre` | C++26 | 函数契约断言（[[dcl.contract.func]]） |
| `post` | C++26 | 函数契约断言 |

为什么不直接做成关键字？原因是兼容性。`override`、`final`、`module`、`import`、`pre`、`post` 都是现有代码中常见的变量名或函数名，把它们变成关键字会破坏大量代码。而它们出现的位置（声明符之后、类名之后、行首）又足够特殊，可以靠上下文判断。

```cpp run title="special-ident.cpp" ok
int final = 0, override = 1, import = 2, module = 3, pre = 4, post = 5;  // 全部是普通变量
struct Base { virtual void override() {} };      // 函数名叫 override
struct D final : Base {                          // final：类属性说明符
  void override() override final {}             // 名字 override + virt-specifier override、final
};
int main() { return final + override - 1; }
```

### 除非另有规定

¶2 的默认规则是有歧义时当作普通标识符，但有些地方标准另有规定，偏向特殊含义。例如 [[class.pre#5]] 规定，当 *class-key* 后跟类名、标识符 `final`，再跟 `:` 或 `{` 时，`final` 解释为类属性说明符：

```cpp run title="final-ambiguity.cpp" ok
struct A;
struct A final {};        // 定义 struct A，而不是"值初始化一个名叫 final、类型为 struct A 的变量"
struct X {
  struct C { constexpr operator int() { return 5; } };
  struct B final : C {};  // 定义嵌套类 B，而不是声明一个名叫 final、宽度为 C{} 的位域
};
int main() {}
```

`import` 和 `module` 的情况更进一步：它们的特殊含义由预处理器在阶段 4 决定（逻辑行开头的 `import`/`module`/`export import` 等构成指令，见 [[lex.pptoken#4]]），因此有了 [[diff.cpp17.lex]] 记录的破坏性变化：

```cpp title="module-break.cpp" error
class module {};
module m1;          // C++20 起：这是一个模块声明，而不是变量声明
class import {};
import j1;          // C++20 起：这是一个模块导入声明
```

### ¶3：不能用作宏名

¶3（注 5）指出，特殊含义标识符不能用作宏名（[[cpp.replace.general]]）。所以为了兼容旧编译器而写的 `#define override`，在当前草案下是非良构的。Clang 对此给出 `-Wkeyword-macro` 警告。

## ¶4：保留标识符

¶4 此外，有些作为记号或预处理记号出现的标识符保留给 C++ 实现使用（通称[[g:reserved-identifier|保留标识符]]），不得另作他用；违反时**不要求诊断**（[[ifndr.lex]]）。

- ¶4.1　含有双下划线 `__` 的标识符，以及以下划线后跟大写字母开头的标识符，保留给实现作任何用途（本标准规定的除外，如 `__cplusplus`）。
- ¶4.2　以下划线开头的标识符，保留给实现用作全局命名空间中的名字。

| 标识符 | 全局命名空间 | 其他作用域 | 宏名 | 依据 |
|---|---|---|---|---|
| `__x`、`x__y`、`a__` | 保留 | 保留 | 保留 | ¶4.1 |
| `_Foo` | 保留 | 保留 | 保留 | ¶4.1 |
| `_foo` | 保留 | 可用 | 见下文 | ¶4.2 |
| `_` | 保留 | 可用（C++26 还有占位符语义） | — | ¶4.2 |
| `foo_` | 可用 | 可用 | 可用 | — |

```cpp title="reserved.cpp" ifndr
int _z;              // IFNDR：全局命名空间中以 _ 开头
namespace N { int _z; }   // OK：不在全局命名空间
int main() {
  int __x;           // IFNDR：含 __
  int _Y;            // IFNDR：_ 后跟大写字母
  int x__y;          // IFNDR：含 __（不只是开头！）
}
```

（例子改编自 [[ifndr.lex]]。Clang 提供 `-Wreserved-identifier` 警告，默认不开启，`-Wall -Wextra` 也不包含它。）

### 为什么是 IFNDR 而不是错误？

因为实现需要使用这些名字，比如标准库头文件里的 `_Tp`、`__first`、`_M_impl`、`__builtin_expect`、`_GLIBCXX_...` 宏等。编译器必须允许这些头文件使用保留名，却很难区分一个名字出自系统头文件还是用户代码（宏展开和 `#include` 嵌套使这种区分并不可靠）。于是标准把违规定为不要求诊断，用户用了保留名，后果自负。典型的后果是与实现的某个宏冲突，产生难以理解的错误或行为。

### 作为记号或预处理记号出现

这个限定很精确。它说明：

- 字符串字面量、注释里的 `__x` 不算；
- 用户定义字面量的后缀不算，因为 `""_Bq` 是一个单独的记号，`_Bq` 并没有作为记号出现。[[over.literal]] 例子中的区别正是由此而来：

```cpp title="udl-reserved.cpp" ifndr
double operator""_Bq(long double);    // OK：_Bq 不是单独的记号
double operator"" _Bq(long double);   // IFNDR：_Bq 作为一个标识符记号出现，_ 后跟大写字母
                                      // （此写法本身也已弃用，见 [[lex.ext]]）
```

!!! lawyer "以 `_小写` 开头的宏名"
    ¶4.2 只说以 `_` 开头的标识符保留用作全局命名空间中的名字，而宏名不属于任何命名空间。所以 `#define _foo 1` 是否违反 ¶4 存在争议。但实际危害是一样的：实现可能在全局命名空间中声明 `_foo`，你的宏会把它替换掉。稳妥的做法是，**任何宏名都不要以下划线开头**。

### 不止 [lex.name]

[[lex.name]] 只规定语言层面的保留。标准库另有一套保留规则（[[reserved.names]]），涉及命名空间 `std` 和 `posix` 的内容、标准库头文件中声明的宏名、属性记号（[[cpp.replace.general]]）、已从标准库移除的僵尸名（zombie name）、不以 `_` 开头的用户定义字面量后缀（[[usrlit.suffix]]）等等。

### 脚注 11：链接器

脚注 11 提醒，在链接器不接受扩展字符的系统上，可以用某种编码表示 UCN，从而形成合法的外部标识符；C++ 对外部标识符的有效字符数不设翻译上限。实践中，GCC 和 Clang（Itanium ABI）在修饰名中直接使用标识符的 UTF-8 字节。

## 陷阱

!!! pitfall "头文件保护宏用了保留名"
    `#ifndef _MY_HEADER_H_`、`#define __UTILS_H__` 极其常见，但都是保留标识符（¶4.1：`_` 加大写字母，或含 `__`）。改成 `MY_HEADER_H` 即可。

!!! pitfall "`x__y` 也是保留的"
    双下划线在任何位置都保留，不只是开头。宏拼接（`a ## __ ## b`）生成的名字也要注意这一点。

!!! pitfall "以为 Unicode 标识符所见即所得"
    外观相同但规范化形式不同的标识符，以及用了同形异码字符（拉丁 `a` 与西里尔 `а`）的标识符，都是不同的名字。NFC 要求解决了前一种情况（编译器未必检查），后一种情况标准不管。

## 思考题

!!! question "思考题 1"
    下面哪些声明违反 [[lex.name#4]]？

    ```cpp
    namespace detail { int _impl; }           // (1)
    struct S { int _Size; };                  // (2)
    void f(int _) {}                          // (3)
    #define my__macro 1                       // (4)
    int operator""_Km(unsigned long long);    // (5)
    ```

<details markdown="1">
<summary>答案</summary>

1. 不违反：`_impl` 不在全局命名空间。
2. 违反（IFNDR）：`_S` 这种形式（`_` 加大写字母）在任何作用域都保留，包括类成员。
3. 不违反：函数参数不在全局命名空间。
4. 违反：含 `__`，按 ¶4.1 保留作任何用途，宏名也不例外。
5. 不违反 [[lex.name]]：`""_Km` 是单个记号，`_Km` 没有作为记号出现；以 `_` 开头的字面量后缀正是留给用户的（[[usrlit.suffix]]）。
</details>

!!! question "思考题 2"
    特殊含义标识符的默认歧义规则是当作普通标识符，为什么 [[class.pre#5]] 偏偏规定 `struct A final {` 中的 `final` 取特殊含义？

<details markdown="1">
<summary>答案</summary>

默认偏向普通标识符是为了兼容：在引入 `override`/`final` 之前合法的代码，引入之后应当保持原意。而 `struct A final {}` 和 `struct B final : C{}` 这两种形式，作为普通标识符只能分别解释为带花括号初始化的变量 `final`（C++03 中这根本不合法，C++11 才有列表初始化）和位域 `final`（宽度为 `C{}`，同样需要 C++11 的列表初始化）。也就是说，旧代码中几乎不可能出现按普通标识符解释的这两种写法，而把它们解释为 `final` 类正是新特性的核心用法。所以在这里偏向特殊含义不会破坏实际代码。
</details>

## 小结

!!! summary
    - 标识符 = (`_` | 字母 | XID_Start | 数学起始) (数字 | `_` | 字母 | XID_Continue | 数学后续)*；必须是 NFC；区分大小写。
    - C++23 起基于 UAX #31；C++26 加入数学兼容记号字符；`$` 始终不是标准的标识符字符。
    - 特殊含义标识符有 `final`、`override`、`import`、`module`、`pre`、`post`；有歧义时默认当作普通标识符；不能用作宏名。
    - 含 `__` 或以 `_` 加大写字母开头的标识符处处保留；以 `_` 开头的标识符在全局命名空间中保留。违反时为 IFNDR。
