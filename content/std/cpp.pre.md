---
title: 序言
summary: 预处理的总文法；一行在什么条件下是预处理指令（以 #、import、module、export 开头的四种情形）；有条件支持的指令；全局模块片段的限制；被跳过的组里语法放宽；指令内的空白限制；指令里的记号默认不做宏展开。
status: done
related: lex.phases, lex.pptoken, cpp.cond, cpp.replace, cpp.module, cpp.import, module.unit
tags: 预处理, 文法, 模块
updated: 2026-10-19
---

!!! tldr
    - 一行是不是预处理指令，在翻译阶段 4 开始时按词法决定：行首是 `#`，或者是后面跟着特定记号的 `import`、`module`、`export`。宏展开造不出指令。
    - 行首的 `import<...>`、`module m;` 会被当成模块相关的指令，所以名为 `import` 或 `module` 的旧代码可能突然无法编译。
    - `#` 后面跟一个非标准名字，是有条件支持的指令，例如 `#ident`；不支持它的实现必须诊断。
    - 被 `#if 0` 跳过的组里，指令名之后可以写任何记号，但整段仍要能切分成预处理记号。
    - 指令里的记号默认不做宏展开；`#if`、`#elif`、`import`，以及宏形式的 `#include`、`#embed`、`#line` 是例外。

**预处理**（[[g:preprocessing]]）指在翻译之前有条件地跳过部分源码、包含其他文件、从头文件单元导入宏，以及替换宏（¶1）。它发生在翻译阶段 4，操作的对象是阶段 3 切分出的**预处理记号**（[[g:preprocessing-token]]）。本页的核心问题是：哪些行是**预处理指令**（[[g:preprocessing-directive]]）？

## 什么算预处理指令（¶2）

C++17 及以前，答案很简单：以 `#` 开头的行。C++20 引入模块之后，以 `import`、`module`、`export` 开头的某些行也成了指令。先看标准的例 1：

```cpp
#                       // 指令
module ;                // 指令
export module leftpad;  // 指令
import <string>;        // 指令
export import "squee";  // 指令
import rightpad;        // 指令
import :part;           // 指令

module                  // 不是指令
;                       // 不是指令

export                  // 不是指令
import                  // 不是指令
foo;                    // 不是指令

export                  // 不是指令
import foo;             // 指令（但在阶段 7 非良构）

import ::               // 不是指令
import ->               // 不是指令
```

¶2 规定，预处理指令是满足下列条件的一串预处理记号。在翻译阶段 4 开始时，它的第一个记号，即**指令引导记号**（[[g:directive-introducing-token]]），位于源文件开头或者紧跟在含换行的空白之后，也就是位于行首，而且是下面四种之一：

- ¶2.1 `#`；
- ¶2.2 `import`，在同一逻辑行上紧跟 *header-name*、`<`、标识符或 `:`；
- ¶2.3 `module`，在同一逻辑行上紧跟标识符、`:` 或 `;`；
- ¶2.4 `export`，在同一逻辑行上紧跟上面两种形式之一。

指令到行尾结束：它的最后一个记号，是其中第一个后面紧跟着含换行空白的记号。

回到例 1。单独一行的 `module` 后面紧跟换行，不满足 ¶2.3。倒数第二组里，`export` 单独一行不是指令，但下一行的 `import foo;` 自己就满足 ¶2.2，所以是指令。到了阶段 7，悬空的 `export` 后面跟着一个导入声明，语法错误。`import ::` 和 `import ->` 的下一个记号不在 ¶2.2 的列表里，所以不是指令。

### 宏展开造不出指令

判断一行是不是指令，看的是阶段 4 开始时的状态，宏展开发生在这之后。¶8 的例 3 说明了这一点：

```cpp run title="empty-hash.cpp" error
#define EMPTY
EMPTY # include <cstdio>   // 不是指令：阶段 4 开始时这一行以 EMPTY 开头
int main() {}
```

`EMPTY` 展开后，这一行变成 `# include <cstdio>`，但它不会被执行，而是作为普通记号进入阶段 7，那里的 `#` 是语法错误。Clang 报 `expected unqualified-id`。

如果宏展开能造出指令，判断一行是不是指令就得先展开宏，而宏的定义又取决于之前的指令，形成循环。所以宏展开的结果即使看起来像指令，也不会被当作指令处理（[[cpp.rescan#4]]）。宏造不出 `#include`、`#define`，也造不出 `#pragma`，这正是 `_Pragma` 运算符存在的理由（[[cpp.pragma.op]]）。

### import 和 module 何时是指令

在阶段 4，`import` 和 `module` 只是普通的标识符，`export` 也还不是关键字。¶2.2 和 ¶2.3 用行首加下一个记号来识别它们，选择这些后继记号是为了尽量不影响把 `import`、`module` 当普通名字用的旧代码：

```cpp run title="import-as-identifier.cpp" ok
int module = 1;            // 行首是 int，不是指令
int import = 2;
int f() {
  return module + import;  // 不在行首
}
int main() { return f() - 3; }
```

但只要碰上规则，普通代码就会被当成指令：

<div class="compare" markdown="1">

```cpp error
template<class> struct import {};
import<int> x;
// error: 'int' file not found
```

```cpp error
using module = int;
module i;
// error: 不是合法的模块声明
```

</div>

左边，行首 `import` 后跟 `<`，这是一条导入指令，`<int>` 被词法分析为 *header-name*（[[lex.pptoken]]），Clang 真的去找名为 `int` 的头文件。右边是 ¶3 的例 2：`module i;` 满足 ¶2.3，是指令，但它不在文件开头，不符合任何指令文法，整个文件不是合法的 *preprocessing-file*。Clang 报 `module declaration must occur at the start of the translation unit`。

修复办法是让这些名字不出现在行首，或者在前面加限定，例如 `::module i;`。

### 换行结束指令，即使在宏调用中间（注 1）

在普通文本里，函数式宏的调用可以跨越多行。在指令里不行，换行总是结束指令：

```cpp error
#define F(x) x
#if F(1     // 指令在这里结束，F( 没有配对的 )
)
#endif
```

Clang 报 `unterminated function-like macro invocation`。

## 总文法

¶2 之前是整个预处理的文法。顶层的 *preprocessing-file* 要么是普通的一组行（*group*），要么是一个模块文件：

```text
preprocessing-file:
    group(opt)
    module-file

module-file:
    line-directives(opt) pp-global-module-fragment(opt) pp-module group(opt) pp-private-module-fragment(opt)
```

模块文件依次是：可选的 `#line` 指令，可选的全局模块片段 `module;`，一条模块指令 `export(opt) module 名字;`，正文，以及可选的私有模块片段 `module :private;`。

*group* 由四种部分组成：

| 部分 | 是什么 | 例 |
|---|---|---|
| *control-line* | 普通指令 | `#include`、`#embed`、`#define`、`#undef`、`#line`、`#error`、`#warning`、`#pragma`、空指令 `#`、导入指令 |
| *if-section* | 条件编译块 | `#if`、`#ifdef`、`#ifndef` … `#elif` … `#else` … `#endif` |
| *text-line* | 普通源码行 | `int x = N;` |
| `#` *conditionally-supported-directive* | `#` 后跟一个不是标准指令名的东西 | `#ident "v1"` |

文法里有两处细节值得注意。

函数式宏的定义要求宏名后紧跟 *lparen*，即前面没有空白的 `(`。所以 `#define F (x) [x]` 定义的是对象式宏，替换列表是 `(x) [x]`。这只约束定义；调用函数式宏时，宏名和 `(` 之间可以有空白甚至换行（[[cpp.replace.general#13]]）。

```cpp run title="lparen.cpp" ok
#define F (x) [x]   // 对象式宏：F 后有空格
#define G(x) [x]    // 函数式宏
// F(1)  展开为  (x) [x](1)
// G (2) 展开为  [2]
int main() {}
```

*pp-balanced-token-seq* 是圆括号、方括号、花括号都配对的记号序列，供 `#embed` 的参数和 `__has_embed` 使用（[[cpp.embed]]）。

## text-line 与有条件支持的指令（¶3）

¶3 第一句规定，一串预处理记号只有在不以指令引导记号开头时，才是 *text-line*。上面的 `module i;` 正是靠这一句被排除的：它以指令引导记号开头，不能作为普通文本行，又不是合法的指令，于是文件非良构。

¶3 第二句定义**有条件支持的指令**（[[g:conditionally-supported-directive]]）：`#` 后面的记号不以任何标准指令名开头。它的语义由实现定义；有条件支持意味着不支持它的实现必须给出诊断（[[intro.compliance]]）。

```cpp run title="cond-directive.cpp" impl
#ident "build 42"   // GCC、Clang 都支持：把字符串写进目标文件
int main() {}
```

Clang 支持 `#ident`（加 `-pedantic` 时警告它是扩展），不支持 GCC 的 `#assert`，遇到时报 `invalid preprocessing directive`，这就是不支持则诊断。

无论实现是否支持，有条件支持的指令都算预处理指令。这对 [[cpp.replace.general#14]] 有影响：宏实参里出现本来会作为指令的行是非良构的，`#ident` 这样的行也算。

## `#embed` 的参数名不能是宏（¶4）

¶4 `#embed` 的记号在宏替换之前如果包含标识符 `limit`、`prefix`、`suffix` 或 `if_empty`，而这个标识符被定义成了宏，程序非良构。`#embed` 的参数部分会做宏展开（[[cpp.embed]]），参数名一旦被替换就无法识别了。与其让 `#define limit 1` 悄悄改变 `#embed` 的含义，不如直接报错。[[cpp.cond#9]] 对 `__has_embed` 有同样的规定。

```cpp title="embed-macro-param.cpp" error
#define limit 1
const unsigned char d[] = {
#embed "data.bin" limit(2)   // error: limit 是宏
};
```

Clang 23 在这里报的是 `expected identifier`，因为参数名已经展开成了 `1`，结论相同。在 `-std=c++2c -pedantic` 下，Clang 还会警告 `#embed is a Clang extension`。

!!! lawyer "offset 不在列表里"
    ¶4 和 [[cpp.cond#9]] 列出的名字都没有 `offset`，尽管它也是标准参数（[[cpp.embed.param.offset]]）。按字面读，`#define offset 2` 之后写 `offset(1)` 不触发 ¶4，参数展开成 `2(1)`，不符合参数文法，仍然非良构，只是理由不同。看起来是加入 `offset` 时漏改了这里。本机 Clang 23 还不认识标准的 `offset`，报 `unknown embed preprocessor parameter 'offset'`。

¶4 第二句：带前缀的参数（*embed-prefixed-parameter*，形如 `vendor::name(...)`）是有条件支持的，语义由实现定义，例如 Clang 的 `clang::offset(n)`。

## 全局模块片段里只能有指令（¶5）

¶5 在阶段 4 开始时，全局模块片段（`module;` 与模块声明之间的部分）里既不能有 *text-line*，也不能有导入指令。

```cpp title="gmf.cppm" error
module;
#include <cstdio>        // OK：#include 是指令
#define NDEBUG           // OK
int helper();            // error: 全局模块片段里出现 text-line
export module m;
```

`#include` 进来的头文件里当然有大量声明，但那是 `#include` 执行之后的事；¶5 只约束直接写在全局模块片段里的东西。全局模块片段的用途就是用 `#include` 引入传统头文件，这样构建工具不做完整解析也能理解它。

!!! impl "Clang 不检查"
    本机 Clang 23 对全局模块片段里直接写出的 `int helper();` 不给任何诊断，加 `-pedantic` 也一样。这不符合 ¶5。

## 被跳过的组里语法放宽（¶6）

¶6 在被 `#if` 跳过的组（[[cpp.cond]]）里，指令名与换行之间可以是任意的预处理记号序列。预处理器在这里只需要看指令名，以追踪 `#if` 的嵌套层次：

```cpp run title="skipped.cpp" ok
#if 0
#  foo bar baz                   // 不是标准指令：不要紧
#  if this is (not an expression // 不求值，只计嵌套层数
#  endif trailing junk           // 跳过组中的 #endif 后可以跟任意记号
#  include <no/such/file>        // 不执行
#  error not triggered           // 不执行
#  define F(                     // 不检查
#endif
int main() {}
```

但任意记号序列仍然必须能切分成预处理记号，阶段 3 对跳过的组一视同仁。所以未闭合的 `/*` 在跳过的组里也是非良构的；按 [[lex.pptoken#2]]，单独的 `'` 或 `"` 也是。

!!! impl "Clang 对单独的引号很宽容"
    本机 Clang 23 在被跳过的组里遇到单独的 `'`（比如 `#if 0` 里的英文 `don't`）不给任何诊断。按草案这是非良构的。很多代码依赖这种宽容，用 `#if 0` 注释掉大段英文。

## 指令内的空白（¶7）

¶7 从指令引导记号之后到结尾换行之前，记号之间只能出现空格和水平制表，包括阶段 3 中替换注释得到的空格，以及可能由其他空白替换来的空格。

括号里的补充是关键。阶段 3 中，换行以外的非空空白序列是保留还是替换为一个空格，是未指定的（[[lex.phases]]）。所以在 `#define` 和宏名之间放一个垂直制表符是否违反 ¶7，取决于实现在阶段 3 有没有把垂直制表换成空格。本机 Clang 23 接受它，不给警告。

注释可以出现在指令中，因为在阶段 3 它已经变成空格：

```cpp run title="comment-in-directive.cpp" ok
#define N /* 注释变成空格 */ 3
#if N == 3 // 行尾注释同样
#endif /* 甚至 #endif 后面 */
int main() { return N - 3; }
```

## 指令里的记号默认不展开（¶8）

¶8 预处理指令里的记号不做宏展开，除非另有规定。规定要展开的情形如下：

| 指令 | 是否宏展开 | 出处 |
|---|---|---|
| `#if`、`#elif` | 是，`defined` 的操作数除外 | [[cpp.cond#9]] |
| `#ifdef`、`#ifndef`、`#elifdef`、`#elifndef` | 否，直接检查标识符 | [[cpp.cond]] |
| `#include` | 仅当不是 `<...>` 或 `"..."` 形式时 | [[cpp.include#7]] |
| `#embed` | 参数部分展开；资源名仅当不是直接形式时 | [[cpp.embed]] |
| `#line` | 仅当不是直接形式时 | [[cpp.line]] |
| `import` 指令 | 是 | [[cpp.import]] |
| `module` 指令 | 模块名不展开，其余部分展开 | [[cpp.module]] |
| `#define`、`#undef`、`#error`、`#warning` | 否 | |
| `#pragma` | 否，实现可以对特定 pragma 自行展开 | [[cpp.pragma]] |

`#define` 不展开，所以宏名本身不会被替换：

```cpp run title="define-no-expand.cpp" ok
#define A B
#define A B      // 重定义 A，不是定义 B：宏名 A 不展开
#undef A         // 取消的也是 A
int main() {}
```

另外，在可以开始指令的位置，`#` 后面的标识符不受宏替换（[[cpp.replace.general#10]]），所以定义一个名为 `include` 的宏不会让 `#include` 失效。

## 历史与演进

!!! history
    - C++98：指令就是以 `#` 开头（前面可以有空白）的行，文法与 C89 基本一致。
    - C++11：与 C99 的预处理器同步（[[N1653]]），加入可变参数宏、`_Pragma` 和空的宏实参。
    - C++20：模块。`import`、`module`、`export` 开头的行成为指令，并引入 *module-file* 文法（[[P1703R1]]、[[P1857R3]]）。
    - C++23：`#elifdef`、`#elifndef`（[[P2334R1]]）和 `#warning`（[[P2437R1]]）。
    - C++26：`#embed` 及其参数文法（[[P1967R14]]）。原来散落在本章的许多 UB 改成了非良构或 IFNDR。

C++20 早期的设计里，`import` 只是一个普通声明，在阶段 7 才处理。问题在于 `import "foo.h";` 会导入宏，这些宏又会影响后面各行的预处理。不完整地编译一遍，就不知道一个文件依赖哪些模块，构建系统也就无法在编译之前排出顺序。[[P1703R1]] 和 [[P1857R3]] 的做法是让这些行在阶段 4 就被识别，并用 ¶2 中纯词法的规则限定它们的形状，这样一次相对便宜的预处理就能扫描出全部依赖。[[cpp.module]] 禁止模块名来自宏展开，也是出于同样的考虑。

## 常见误解

!!! pitfall "宏实参里可以写 #if"
    ```cpp
    printf("%d\n", MAX(a,
    #ifdef BIG
        1000
    #else
        10
    #endif
    ));
    ```
    如果 `printf` 或 `MAX` 是函数式宏，这段代码非良构（[[cpp.replace.general#14]]，C++23 及以前是 UB）。有的 C 标准库把 `printf`、`memcpy` 实现为宏，于是这段代码在有的平台上能编译，有的不能。Clang 对此只给出 `-Wembedded-directive` 警告。

## 思考题

!!! question "思考题 1"
    下面两行哪一行是预处理指令？到阶段 7 会怎样？
    ```cpp
    export module
    m;
    ```

<details markdown="1">
<summary>答案</summary>

两行都不是指令。第一行的 `module` 后面在同一逻辑行上没有标识符、`:` 或 `;`，不满足 ¶2.3，`export` 也就不满足 ¶2.4。第二行以标识符 `m` 开头，是 *text-line*。

这两行作为普通记号进入后面的阶段。`module` 没有被替换成模块关键字（[[cpp.module]]），阶段 7 看到的只是普通标识符，构不成模块声明，结果是语法错误。模块声明的 `module` 和名字必须写在同一行。
</details>

!!! question "思考题 2"
    `#define EMPTY` 之后，`EMPTY #define X 1` 不会定义 `X`。而 `#define D defined(A)` 之后，`#if D` 在 Clang 上却能工作。两者有什么本质区别？

<details markdown="1">
<summary>答案</summary>

第一种是用宏造指令。是不是指令在阶段 4 开始时就确定了（¶2），宏展开在这之后，所以永远造不出指令。这是规则本身的结果，所有实现都一样。

第二种是 `#if` 表达式里的宏展开产生了 `defined`，[[cpp.cond#9]] 规定这是 IFNDR（C++23 及以前是 UB）。它能工作只是因为 Clang 选择照常求值，同时给出 `-Wexpansion-to-defined` 警告，标准并不保证。
</details>
