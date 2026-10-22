---
title: 标识符
summary: 哪些字符能组成标识符（基于 Unicode 的 XID 属性，必须是 NFC）；final、override、import、module、pre、post 为什么不是关键字；哪些名字保留给实现（含双下划线、下划线加大写字母、全局的下划线开头）。
status: draft
papers: P1949R7
related: lex.key, lex.charset, uaxid, reserved.names, cpp.replace.general, over.literal
tags: 标识符, Unicode, 保留名
updated: 2026-10-19
---

!!! tldr
    - 标识符以字母、`_` 或有 Unicode XID_Start 属性的字符开头，后面可以跟数字和有 XID_Continue 属性的字符。汉字可以，emoji 和 `$` 不行。
    - 标识符必须是 Unicode NFC 形式，否则程序非良构；本机 Clang 23 不检查这一点。
    - `final`、`override`、`import`、`module`、`pre`、`post` 是特殊含义标识符，只在特定位置有特殊含义，别处可以当普通名字用，但不能定义成宏。
    - 含 `__` 或以 `_` 加大写字母开头的标识符处处保留给实现；以 `_` 开头的标识符在全局命名空间中保留。用了它们是 IFNDR：程序有错，但编译器不必报告。

## 哪些字符能组成标识符

```cpp run title="unicode-ident.cpp" ok
int 变量 = 1;               // 汉字有 XID_Start 属性
double \u03C0 = 3.14159;    // π，用通用字符名写也一样
int naïve = 2;              // ï 是一个预组合字符 U+00EF
int main() { return 变量 + naïve - 3; }
```

```cpp title="bad-ident.cpp" error
int 😀 = 1;      // error: emoji 没有 XID_Start 属性
int €uro = 3;    // error: € 是货币符号，不是字母
int $x = 4;      // 按标准 error：$ 不是字母，也没有 XID 属性
```

[[lex.name]] 的文法如下：

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

XID_Start 和 XID_Continue 是 Unicode 给每个字符标注的属性（注 1：见 UAX #44）。直观地说，XID_Start 是各种文字里的字母，包括汉字、希腊字母、西里尔字母；XID_Continue 在此基础上再加数字、组合附加符号和连接标点等。也有出人意料的情形：中点 `·`（U+00B7）有 XID_Continue 属性，所以 `int a·b = 2;` 声明的是一个名为 `a·b` 的变量。

注 2 说，标识符区分大小写。注 3 说，附录 [[uaxid]] 逐条对照了 Unicode 的标识符规范 UAX #31 和 C++ 的规则。

`$` 虽然在 C++26 加入了基本字符集（[[lex.charset]]），但它不是 *nondigit*，也没有 XID 属性，按标准不能出现在标识符里。GCC、Clang、MSVC 都把它作为扩展接受，Clang 在 `-pedantic` 下给出 `-Wdollar-in-identifier-extension` 警告。

### 数学记号 {{c++26}}

当前草案在 XID 之外还加入了 ID_Compat_Math_Start 和 ID_Compat_Math_Continue 两个属性，对应 UAX #31 中为数学记号准备的配置（[[uaxid.def.general]]）。于是 `∂`（U+2202）、`∇`（U+2207）、`∞`（U+221E）可以作为标识符的首字符，下标数字 `₀`（U+2080）可以出现在标识符中间：

```cpp run title="math-ident.cpp" ok
double ∂x = 0.1;
double x₀ = 1.0;
int main() { return ∂x < x₀ ? 0 : 1; }
```

C++23 中这些字符不能出现在标识符里。本机 Clang 23 接受上例，但给出 mathematical notation character in an identifier is a Clang extension 警告，诊断还停留在 C++23 的规则上。

## NFC 要求（¶1）

!!! std
    The program is ill-formed if an *identifier* does not conform to Normalization Form C as specified in the Unicode Standard.

¶1 标识符必须符合 Unicode 的**规范组合形式**（Normalization Form C，NFC），否则程序非良构。

同一个外观的文字在 Unicode 里可能有几种编码。`é` 可以是一个预组合字符 U+00E9，也可以是 `e` 加组合尖音符 U+0301。如果不要求规范化，两个看起来一模一样的标识符可能是两个不同的名字。这会损害可读性，也会给链接带来麻烦：不同的编辑器可能存成不同的字节，导致符号对不上（[[diff.cpp20.lex]] 给出的理由就是让链接器的行为一致）。

标准要求输入本身就是 NFC，而不是让编译器先规范化再比较。编译器只需检查、不必改写，字节不同的标识符就一定是不同的标识符。

```cpp title="nfc.cpp" error
int a\u0300 = 1;   // error: a 加组合重音符 U+0300 不是 NFC，NFC 形式是 U+00E0 à
int \u212B = 2;    // error: U+212B ANGSTROM SIGN 规范化后是 U+00C5，自身不是 NFC
```

本机 Clang 23 不检查 NFC，上例以 `-std=c++2c -pedantic` 编译没有任何诊断。这偏离了标准，因为这条规则要求诊断。不要指望编译器替你发现规范化形式的差异，可以在编辑器或 CI 中统一做 NFC 规范化。

注 4 说，在阶段 4，标识符还包括那些到阶段 7 才被区分为关键字的预处理记号。所以 `#if` 里可以出现 `new`、`int`，它们被当作普通标识符替换成 0（[[lex.phases]]）。

!!! history "从字符区间表到 UAX #31"
    C++11 到 C++20 用附录里的一张码位区间表列出标识符中允许的字符，另有一张表列出不能作首字符的字符。这张表过于宽松，许多符号甚至一些不可见的字符都被允许。C++23 采纳 [[P1949R7]]，改用 XID_Start 和 XID_Continue，并要求 NFC。[[diff.cpp20.lex]] 记录了这个不兼容的变化：一些原来合法的标识符，例如含 emoji 的，变成了非良构。

## 特殊含义标识符（¶2、¶3）

```cpp run title="special-ident.cpp" ok
int final = 0, override = 1, import = 2, module = 3, pre = 4, post = 5;  // 普通变量
struct Base { virtual void override() {} };      // 函数名叫 override
struct D final : Base {                          // final：类的属性说明符
  void override() override final {}             // 名字 override，后面是 virt-specifier
};
int main() { return final + override - 1; }
```

¶2 表 4 中的标识符出现在特定上下文中时有特殊含义，叫做[[g:identifier-with-special-meaning|特殊含义标识符]]（identifier with special meaning）。文法用到它们时直接写出拼写，而不经过 *identifier* 产生式。除非另有规定，一个标识符是否有特殊含义存在歧义时，按普通标识符解释。

| 标识符 | 引入 | 有特殊含义的位置 |
|---|---|---|
| `final` | C++11 | 类头（[[class.pre]]）、虚函数声明的 *virt-specifier*（[[class.mem]]） |
| `override` | C++11 | 虚函数声明的 *virt-specifier* |
| `import` | C++20 | 模块导入声明和 import 指令（[[module.import]]、[[cpp.import]]） |
| `module` | C++20 | 模块声明和 module 指令（[[module.unit]]、[[cpp.module]]） |
| `pre` | C++26 | 函数的契约断言（[[dcl.contract.func]]） |
| `post` | C++26 | 函数的契约断言 |

它们不做成关键字，是为了兼容。这些词在现有代码里常被用作变量名或函数名，做成关键字会破坏大量代码；而它们有特殊含义的位置（声明符之后、类名之后、行首）足够特殊，靠上下文就能判断。

### 偏向特殊含义的例外

¶2 说有歧义时默认按普通标识符解释，但有些地方标准另有规定。[[class.pre#5]] 规定，类关键字后面跟类名、标识符 `final`、再跟 `:` 或 `{` 时，`final` 解释为类的属性说明符：

```cpp run title="final-ambiguity.cpp" ok
struct A;
struct A final {};        // 定义 struct A，而不是声明一个名叫 final、类型为 A 的变量
struct X {
  struct C { constexpr operator int() { return 5; } };
  struct B final : C {};  // 定义嵌套类 B，而不是声明一个名叫 final、宽度为 C{} 的位域
};
int main() {}
```

`import` 和 `module` 更进一步：逻辑源行开头的 `import`、`module`（可以带 `export`）构成预处理指令，在阶段 4 就决定了含义（[[lex.pptoken#4]]）。所以有了 [[diff.cpp17.lex]] 记录的不兼容：

```cpp title="module-break.cpp" error
class module {};
module m1;          // C++20 起这是一个模块声明，而不是变量声明
class import {};
import j1;          // C++20 起这是一个导入声明
```

¶3 的注 5 说，特殊含义标识符不能用作宏名（[[cpp.replace.general]]）。为了兼容旧编译器而写的 `#define override`，在当前草案下是非良构的。本机 Clang 23 在 `-pedantic` 下对此给出 `-Wkeyword-macro` 警告，默认不诊断。

## 保留标识符（¶4）

¶4 有些标识符作为记号或预处理记号出现时，保留给 C++ 实现使用，程序不能另作他用，叫做[[g:reserved-identifier|保留标识符]]。违反这条规则的程序非良构，但不要求诊断（{{ifndr}}，[[ifndr.lex]]）。

- ¶4.1 含有双下划线 `__` 的标识符，以及以下划线加大写字母开头的标识符，保留给实现作任何用途。标准自己规定的除外，例如 `__cplusplus`。
- ¶4.2 以下划线开头的标识符，保留给实现作为全局命名空间中的名字。

| 标识符 | 全局命名空间 | 其他作用域 | 宏名 | 依据 |
|---|---|---|---|---|
| `__x`、`x__y`、`a__` | 保留 | 保留 | 保留 | ¶4.1 |
| `_Foo` | 保留 | 保留 | 保留 | ¶4.1 |
| `_foo` | 保留 | 可用 | 有争议，见下文 | ¶4.2 |
| `foo_` | 可用 | 可用 | 可用 | |

```cpp title="reserved.cpp" ifndr
int _z;                   // IFNDR：全局命名空间中以 _ 开头
namespace N { int _z; }   // OK：不在全局命名空间
int main() {
  int __x;                // IFNDR：含 __
  int _Y;                 // IFNDR：_ 后跟大写字母
  int x__y;               // IFNDR：含 __，不只是开头
}
```

例子改编自 [[ifndr.lex]]。Clang 提供 `-Wreserved-identifier` 警告，它不在 `-Wall -Wextra` 里，要单独打开。

为什么不要求诊断？实现自己就要用这些名字：标准库头文件里的 `_Tp`、`__first`、`_M_impl`，编译器内建的 `__builtin_expect`，各种 `_GLIBCXX_...` 宏。编译器必须允许头文件使用保留名，又很难可靠地判断一个名字出自系统头文件还是用户代码（宏展开和嵌套的 `#include` 让这种区分不可靠）。用户用了保留名，典型的后果是与实现的某个宏或声明冲突，出现难以理解的错误。

作为记号出现这个限定很精确。字符串字面量和注释里的 `__x` 不算。用户定义字面量的后缀也不算，因为 `""_Bq` 是一个记号，`_Bq` 没有单独作为记号出现。[[over.literal]] 的例子正是这个区别：

```cpp title="udl-reserved.cpp" ifndr
double operator""_Bq(long double);    // OK：_Bq 不是单独的记号
double operator"" _Bq(long double);   // IFNDR：_Bq 作为标识符记号出现，_ 后跟大写字母
                                      // 这种带空格的写法本身也已弃用，见 lex.ext
```

!!! lawyer "以 `_小写` 开头的宏名"
    ¶4.2 只说以 `_` 开头的标识符保留作全局命名空间中的名字，而宏名不属于任何命名空间，所以 `#define _foo 1` 是否违反 ¶4 有争议。实际的危害一样：实现可能在全局命名空间声明 `_foo`，你的宏会把它替换掉。稳妥的做法是宏名都不以下划线开头。

[[lex.name]] 只规定语言层面的保留。标准库另有一套保留规则（[[reserved.names]]），涉及命名空间 `std` 和 `posix`、标准库头文件中声明的名字、属性记号、已从标准库移除的名字、不以 `_` 开头的字面量后缀（[[usrlit.suffix]]）等。

<details class="fine" markdown="1"><summary>其余条文</summary>

脚注 11：如果链接器不接受扩展字符，可以用某种方式编码通用字符名，以形成合法的外部标识符；C++ 对外部标识符的有效字符数不设上限。实践中，GCC 和 Clang（Itanium ABI）直接在修饰名里使用标识符的 UTF-8 字节。

</details>

## 常见误解

!!! pitfall "头文件保护宏用了保留名"
    `#ifndef _MY_HEADER_H_`、`#define __UTILS_H__` 很常见，但都是保留标识符：前者是下划线加大写字母，后者含 `__`。改成 `MY_HEADER_H` 即可。

!!! pitfall "只有开头的双下划线才保留"
    双下划线在任何位置都保留，`x__y` 也是。用宏拼接名字（`a ## __ ## b`）时同样要注意。

!!! pitfall "Unicode 标识符所见即所得"
    外观相同但规范化形式不同的标识符，以及用了形状相同的不同字母的标识符（拉丁 `a` 与西里尔 `а`），都是不同的名字。NFC 要求处理的是前一种（编译器未必检查），后一种标准不管。

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
2. 违反（IFNDR）：`_Size` 以下划线加大写字母开头，在任何作用域都保留，类成员也不例外。
3. 不违反：函数形参不在全局命名空间。
4. 违反：含 `__`，按 ¶4.1 保留作任何用途，宏名也不例外。
5. 不违反：`""_Km` 是一个记号，`_Km` 没有单独作为记号出现；以 `_` 开头的字面量后缀正是留给用户的（[[usrlit.suffix]]）。
</details>

!!! question "思考题 2"
    特殊含义标识符有歧义时默认按普通标识符解释，为什么 [[class.pre#5]] 偏偏规定 `struct A final {` 里的 `final` 取特殊含义？

<details markdown="1">
<summary>答案</summary>

默认偏向普通标识符是为了兼容：引入 `final` 之前合法的代码，引入之后应当保持原来的意思。

而 `struct A final {}` 和 `struct B final : C {}` 如果按普通标识符解释，前者是用花括号初始化的变量 `final`，后者是宽度为 `C{}` 的位域 `final`，两者都要用到花括号初始化。花括号初始化和 `final` 都是 C++11 引入的，在此之前这两种写法根本不合法，所以不存在因此改变含义的旧代码。在这里偏向特殊含义不会破坏兼容，又正好对应 `final` 类的常见写法。
</details>
