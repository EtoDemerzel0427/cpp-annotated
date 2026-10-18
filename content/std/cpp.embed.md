---
title: 资源包含
summary: C++26 的 #embed：把任意二进制资源在预处理期展开为逗号分隔的 int 整数字面量列表；资源的两种搜索、宽度与计数、按 fgetc 读取的语义模型，以及 limit / offset / prefix / suffix / if_empty 五个参数。
status: draft
covers: *
since: c++26
papers: P1967R14
related: cpp.include, cpp.cond, cpp.pre, cpp.predefined, dcl.init.list, dcl.init.aggr
tags: 预处理, embed, C++26
updated: 2026-10-18
---

{{c++26}} `#embed` 解决的是一个老问题：**把一个二进制文件的内容放进程序里**。在它出现之前，人们的办法是：

- 用 `xxd -i`、CMake 脚本等外部工具把文件转成一个巨大的 `{0x12, 0x34, ...}` 源文件——要多一个构建步骤，而且编译器要解析几百万个整数字面量，慢且耗内存；
- 用汇编器的 `.incbin` 指令或链接器的 `-b binary`——不可移植，且数据在编译期不可见（不能 `constexpr` 使用）。

`#embed` 把这件事交给预处理器：**语义上**它展开为一串整数字面量（所以能用于任何初始化器、函数实参、`constexpr` 计算），**实现上**编译器可以完全跳过"生成文本再解析"的过程，直接把字节塞进 AST。它与 C23 的 `#embed` 同源，由 [[P1967R14]] 引入 C++26。

前置知识：`#include` 的搜索模型（[[cpp.include]]），因为 `#embed` 几乎逐字复制了那套措辞；`#if` 的求值规则（[[cpp.cond]]），因为参数用它求值。

## 资源搜索（[[cpp.embed.gen#1]]–¶7）

与 [[cpp.include]] 的"头文件搜索/源文件搜索"平行，这里定义了：

- [[g:bracket-resource-search|方括号资源搜索]]（*bracket resource search*，¶1）：在一系列位置中查找由字符序列唯一标识的资源；位置与标识方式由实现定义。
- [[g:quote-resource-search|引号资源搜索]]（*quote resource search*，¶2）：查找由字符序列命名的资源，方式由实现定义；不支持或失败则退回方括号资源搜索。

¶3–¶5：`# embed header-name pp-tokens(opt) new-line` 用由资源数据导出的预处理记号替换这条指令。`<...>` 形式做方括号资源搜索，`"..."` 形式做引号资源搜索。

¶6：方括号资源搜索失败，或任一搜索找到了实现**无法处理**的资源，程序非良构。注 1：即使 `limit(0)`，或者只是在 `__has_embed` 中探测，"找到但无法处理"仍然非良构。

¶7 推荐做法：使用与 `#include` **类似但不同**的搜索路径机制。Clang 和 GCC 都为此提供了 `--embed-dir=<dir>` 选项。Clang 23 实测：`#embed <r.bin>` 只在 `--embed-dir` 指定的目录中查找，`-I` 目录对它无效；`#embed "r.bin"` 先在包含者所在目录查找。分开的理由很实际：你大概不希望 `#embed <logo.png>` 去系统头文件目录里乱找，也不希望 `#include` 能找到资源目录里的 `.h`。

## 参数部分的宏展开（¶8）

¶8：无论哪种形式，`#embed` 后面的 *pp-tokens*（若有）都**像普通文本一样做宏展开**，展开后必须符合 *embed-parameter-seq* 的形式。

所以参数里可以用宏：

```cpp
#define MAX_HEADER 64
#embed "file.bin" limit(MAX_HEADER)
```

这也是 [[cpp.pre#4]] 禁止把 `limit`、`prefix`、`suffix`、`if_empty` 定义为宏的原因——否则参数名本身会被展开掉。

## 资源的宽度、偏移与计数（¶9–¶10）

¶9 定义了几个量：

| 量 | 定义 |
|---|---|
| *implementation-resource-width* | 资源的大小，**以位计**，实现定义 |
| *implementation-resource-count* | 上者除以 `CHAR_BIT` |
| *resource-offset* | 有 `offset` 参数时为其值，否则为 0 |
| [[g:resource-count|*resource-count*]] | 有 `limit` 时为 `max(min(limit, count − offset), 0)`，否则为 `max(count − offset, 0)` |
| 空资源 | *resource-count* 为 0 |

若宽度不是 `CHAR_BIT` 的整数倍，程序非良构（¶10 的例子：一个 6 位的资源）。以位计宽度的设计是为了照顾"字节"不是 8 位的平台以及非文件的资源来源。

注意 `max(..., 0)`：`offset` 超过资源大小时**不是错误**，资源只是变成空的——这让 `if_empty` 有了用武之地（见下文）。

## 展开为什么（¶11–¶13）

¶11：`#embed` 被替换为**逗号分隔的 `int` 类型整数字面量列表**，除非被参数修改。

¶12 用 `fgetc` 精确定义了每个值：先以二进制方式从资源中调用 *resource-offset* 次 `std::fgetc` 并丢弃结果；再调用 *resource-count* 次，依次产生列表元素。如果这 *resource-count* 次中有一次返回 `EOF`，程序非良构。

这个"如同 `fgetc`"的模型意味着：**每个元素的值在 `[0, UCHAR_MAX]` 之间**（`fgetc` 返回 `unsigned char` 转换的 `int`），而不是有符号的。

```cpp run title="embed-self.cpp" ok flags="-std=c++2c -Wno-c23-extensions"
// 这个文件以 "//" 开头：embed 自身
constexpr unsigned char head[] = {
#embed __FILE__ limit(3)
};
static_assert(sizeof head == 3);
static_assert(head[0] == '/' && head[1] == '/' && head[2] == ' ');
int main() {}
```

`__FILE__` 在参数宏展开时被替换成当前文件名的字符串字面量，于是走 ¶14 的"宏形式"并形成 *header-name*——这是写可在任何地方运行的 `#embed` 示例的小技巧。

¶13 推荐做法：每个整数字面量的值应当**尽量忠实地反映资源的比特流**，这可能需要实现考虑翻译环境与执行环境之间的差异。标准例 2 展示了这个期望：把 `data.dat` 编译期嵌入的结果与运行时用 `ifstream` 二进制读取的结果做 `memcmp`，应当相等。

### 它就是一串逗号分隔的值

例 3 强调了一个事实：`#embed` 的结果在语法上**只是** `v1, v2, ..., vn`，没有花括号。它出现在哪里，就被那里的语法解释：

```cpp
int i = {
#embed "i.dat"
};            // 若 i.dat 只产生一个值则良构
int i2 =
#embed "i.dat"
;             // 同上
struct s { double a, b, c; struct { double e, f, g; } x; double h, i, j; };
s x = {
#embed "s.dat"  // 若产生不超过 9 个值则良构：按聚合初始化的花括号省略规则分配
};
```

所以它也可以出现在函数调用里、模板实参列表里、`std::vector` 的初始化列表里：

```cpp run title="embed-anywhere.cpp" ok flags="-std=c++2c -Wno-c23-extensions"
#include <vector>
int sum3(int a, int b, int c) { return a + b + c; }
int main() {
  std::vector<int> v = {
#embed __FILE__ limit(8)
  };
  int s = sum3(
#embed __FILE__ limit(3)
  );
  return (v.size() == 8 && s == '#' + 'i' + 'n') ? 0 : 1;
}
```

!!! pitfall "char 与窄化"
    元素是 `int` 类型、值域 `[0, 255]`（8 位字节时）的整数字面量。用它初始化 `char` 数组时，若 `char` 是有符号的且某字节 ≥ 128，就是列表初始化中的**窄化转换**（[[dcl.init.list]]），非良构。所以**用 `unsigned char` 接收**，或者用 `std::byte` 时注意它不能从 `int` 隐式转换。

    Clang 23 实测：`#embed` 直接初始化 `char` 数组时，即使有 `0xFF` 字节也**不诊断窄化**（值变成 `-1`）；而把 `-E` 的输出（`{255, 1}`）再编译则报窄化错误。这是 Clang 为 `#embed` 走的快速路径与"如同展开为整数字面量"的语义之间的偏差。

## 宏形式（¶14）

¶14：若 `#embed` 不匹配直接形式（`embed` 后不是 *header-name*），那么 `embed` 之后的记号整体做宏展开，再尝试由展开结果中**紧跟 `embed` 的那部分记号**的拼写和空白拼出 *header-name*（空白处理由实现定义）；成功则按直接形式处理，失败则**非良构**（注意：`#include` 的同样情况是 IFNDR，这里更严格）。注 2：相邻字符串字面量不拼接。

注 3 强调：**宏展开对整条指令只做一次**。例 4：

```cpp
#define EMPTY
#define X myfile
#define Y rsc
#define Z 42
#embed <myfile.rsc> prefix(Z)    // 直接形式：只展开 header-name 之后的部分
#embed EMPTY <X.Y>  prefix(Z)    // 宏形式：整条展开，X、Y、Z 都被替换
// 两者都等价于  #embed <myfile.rsc> prefix(42)
```

Clang 23 对第二行**不**展开 `<X.Y>` 中的 `X`、`Y`（报 `'X.Y' file not found`），与草案不符；`#include` 的同类情况也一样（见 [[cpp.include]]）。

## 参数总览（[[cpp.embed.param]]）

文法（[[cpp.pre]]）：

```text
embed-standard-parameter:
    limit ( pp-balanced-token-seq )
    offset ( pp-balanced-token-seq )
    prefix ( pp-balanced-token-seq(opt) )
    suffix ( pp-balanced-token-seq(opt) )
    if_empty ( pp-balanced-token-seq(opt) )
embed-prefixed-parameter:
    identifier :: identifier
    identifier :: identifier ( pp-balanced-token-seq(opt) )
```

每个标准参数在一条指令中**至多出现一次**。带前缀的参数（如 Clang 的 `clang::offset`）是有条件支持的，语义由实现定义（[[cpp.pre#4]]）。

| 参数 | 作用 | 资源为空时 |
|---|---|---|
| `limit(n)` | 最多取 n 个元素 | — |
| `offset(n)` | 先跳过 n 个元素 | — |
| `prefix(...)` | 在列表**前**插入记号 | 忽略 |
| `suffix(...)` | 在列表**后**插入记号 | 忽略 |
| `if_empty(...)` | — | 整条指令替换为这些记号 |

### limit（[[cpp.embed.param.limit]]）

¶1：`limit(...)` 指定逗号分隔列表中**最多**有多少个元素。至多出现一次；括号内**不得出现** `defined`。

¶2：括号内的 *pp-balanced-token-seq* 按 [[cpp.cond]] 的规则当作 *constant-expression* 求值，但**不再额外做一次宏展开**（¶8 已经做过了）。所以未定义的标识符也会变成 0：

```cpp
#undef DATA_LIMIT
#if __has_embed(<data.dat> limit(DATA_LIMIT))   // 等价于 limit(0)
#endif
```

例 2 有一个细节：`#embed <data.dat> limit(__has_include("a.h"))` 是合法的（按 #if 规则求值，`__has_include` 可用）；但把同样的东西放进 `__has_embed(...)` 里则非良构——`__has_include` 不能嵌在 `__has_embed` 中。

¶3：表达式必须是值 ≥ 0 的整数常量表达式。

`limit` 的用途：只取文件头（魔数、签名），或者对**无限长**的资源（如 `/dev/urandom`）取有限个字节：

```cpp
constexpr unsigned char sound_signature[] = {
#embed <sdk/jump.wav> limit(2+2)     // 只取前 4 字节："RIFF"
};
static_assert(sizeof(sound_signature) == 4);
```

### offset（[[cpp.embed.param.offset]]）

¶1：`offset(...)` 表示要从资源中**跳过**的元素个数。至多出现一次。¶2–¶3：求值规则与 `limit` 相同，值必须 ≥ 0。

¶4 的例子展示了与 `limit` 的组合——先跳过、再限量：

```cpp
#embed <sdk/jump.wav>                    // arr
#embed <sdk/jump.wav> offset(2)          // offset_arr[0] == arr[2]
#embed <sdk/jump.wav> offset(1) limit(1) // offset_limit_arr[0] == arr[1]
```

`offset` 比最初的 `#embed` 提案晚加入标准。Clang 23 尚不支持标准的 `offset`（报 `unknown embed preprocessor parameter 'offset'`），但提供了语义相同的扩展参数 `clang::offset`：

```cpp run title="embed-offset.cpp" impl flags="-std=c++2c -Wno-c23-extensions" cc=clang_trunk
// ABCDEFG
constexpr unsigned char mid[] = {
#embed __FILE__ clang::offset(3) limit(3)   // 跳过 "// "，取 "ABC"
};
static_assert(mid[0] == 'A' && mid[1] == 'B' && mid[2] == 'C');
int main() {}
```

### prefix 与 suffix（[[cpp.embed.param.prefix]]、[[cpp.embed.param.suffix]]）

`prefix(...)` / `suffix(...)` 各至多出现一次。资源**为空**时被忽略；否则把括号内的记号放在逗号分隔列表的紧前面 / 紧后面。

它们的典型用途是**只在非空时**添加分隔符。标准例子（suffix ¶2）：

```cpp
constexpr unsigned char whl[] = {
#embed "ches.glsl" \
  prefix(0xEF, 0xBB, 0xBF, ) /* 非空时加 UTF-8 BOM 及逗号 */ \
  suffix(,)                  /* 非空时补一个逗号 */
  0                          /* 总是有结尾的 0 */
};
// 空文件 → { 0 }；非空 → { 0xEF, 0xBB, 0xBF, 数据..., 0 }
```

如果不用 `prefix`/`suffix` 而直接写 `{ 0xEF, 0xBB, 0xBF, #embed ..., 0 }`，资源为空时就会出现 `0xBF, , 0` 这样的连续逗号，语法错误。

一个常用的变体是生成以 `'\0'` 结尾的字符串：

```cpp run title="embed-cstr.cpp" ok flags="-std=c++2c -Wno-c23-extensions"
// 本文件以 "//" 开头
constexpr unsigned char text[] = {
#embed __FILE__ limit(2) suffix(, 0)
};
static_assert(sizeof text == 3 && text[0] == '/' && text[2] == 0);
int main() {}
```

### if_empty（[[cpp.embed.param.if.empty]]）

¶1：至多出现一次。¶2：资源**非空**时忽略；为空时，**整条** `#embed` 指令被替换为括号内的记号（`prefix`、`suffix` 自然也不出现）。

三个标准例子：

- 例 1：`#embed </owo/uwurandom> if_empty(42203) limit(0)` 展开为 `42203`——`limit(0)` 让资源为空。
- 例 2：`__has_embed(</owo/uwurandom> limit(0) prefix(some tokens)) == __STDC_EMBED_EMPTY__` 在资源存在时恒为真——`limit(0)` 在 `__has_embed` 中同样生效。
- 例 3：一个只有 1 字节的资源，`offset(1) if_empty(42203)` 展开为 `42203`——跳过之后什么也不剩。

```cpp run title="embed-if-empty.cpp" ok flags="-std=c++2c -Wno-c23-extensions"
constexpr int v[] = {
#embed __FILE__ limit(0) prefix(1, ) suffix(, 2) if_empty(-1)
};
static_assert(sizeof v == sizeof(int) && v[0] == -1);   // 空：只剩 if_empty
int main() {}
```

## 与 __has_embed 的关系

`__has_embed` 在 [[cpp.cond#4]] 中定义：它按 `#embed` 的方式处理括号内的记号，返回 `__STDC_EMBED_NOT_FOUND__`（0）、`__STDC_EMBED_FOUND__`（1）或 `__STDC_EMBED_EMPTY__`（2）（三个宏见 [[cpp.predefined]]）。不认识的参数使结果为 0 而不是非良构。典型用法：

```cpp
#if __has_embed("logo.png" vendor::compress(zstd)) == __STDC_EMBED_FOUND__
  // 实现支持该 vendor 参数且资源非空
#elif __has_embed("logo.png") == __STDC_EMBED_FOUND__
  // 退而求其次
#endif
```

## 实现视角

!!! impl "为什么 #embed 快"
    标准语义是"展开为整数字面量列表"，但这只是 as-if 规则下的**可观察**效果。Clang 的实现在预处理器中生成一个携带资源数据的注解记号（annotation token）进入语法分析，最终形成 AST 节点 `EmbedExpr`；在初始化 `unsigned char` 之类数组的常见情形下，数据被整块复制，而不必为每个字节创建一个 `IntegerLiteral` 节点。GCC 15 也有类似的优化。这使得嵌入几十 MB 的资源在内存和时间上都可以接受。

    只有在 `-E` 输出时，实现才不得不真的把它打印成 `65, 66, 67, ...`。

!!! impl "依赖追踪"
    被 `#embed` 的资源和被 `#include` 的头文件一样，会出现在 `-MD`/`-MMD` 生成的依赖文件中——资源改变时，构建系统会重新编译。这是 `#embed` 相对于"运行时读文件"的另一个工程优势。Clang 23 实测 `-MD` 的输出中确实列出了被嵌入的资源文件。

## 历史与演进

!!! history
    - 多年来社区靠 `xxd -i`、`.incbin`、`ld -b binary`、`std::embed`（运行期/编译期函数式方案的早期提案）等迂回手段。
    - C23 先标准化了 `#embed`（WG14 的 N3017）。
    - C++26 以 [[P1967R14]] 引入同一机制 {{c++26}}，并加入 `__has_embed`、`__STDC_EMBED_*__` 宏和特性测试宏 `__cpp_pp_embed`。
    - `offset` 参数随后加入（C 方面也在后续版本中跟进）。

## 思考题

!!! question "思考题 1"
    资源 `r.bin` 有 5 字节。下面每条指令展开为什么？
    ```cpp
    #embed "r.bin" offset(3) limit(10)
    #embed "r.bin" offset(7) prefix(1,) if_empty(0)
    #embed "r.bin" limit(0) suffix(,9)
    ```

<details markdown="1">
<summary>展开查看答案与解析</summary>

按 [[cpp.embed.gen#9]]：count = 5。

1. offset = 3，resource-count = max(min(10, 5−3), 0) = 2：展开为第 4、5 字节的值，`b3, b4`。
2. offset = 7，resource-count = max(5−7, 0) = 0：资源为空，`prefix` 被忽略，整条指令替换为 `if_empty` 的内容 `0`。
3. resource-count = max(min(0, 5), 0) = 0：资源为空，`suffix` 被忽略；没有 `if_empty`，所以展开为**空**（什么记号也没有）。
</details>

!!! question "思考题 2"
    为什么 `#embed` 的元素被定义为 `int` 类型、值取自 `fgetc`，而不是直接定义为 `unsigned char` 类型的值？

<details markdown="1">
<summary>展开查看答案与解析</summary>

因为预处理器产生的只能是**预处理记号**，而整数字面量没有"`unsigned char` 类型"的写法——最小的整数字面量类型就是 `int`（[[lex.icon]]）。把元素定义为 `int` 类型的整数字面量，`#embed` 就能被纯文本地理解（`-E` 输出可以被再次编译），也能在任何能写整数列表的地方使用。值取自 `fgetc` 则把"字节值"精确地定义为非负的 `unsigned char` 值，避开了 `char` 符号性的实现定义差异。代价就是上文的窄化陷阱：接收方要用 `unsigned char` 或更宽的类型。
</details>

## 小结

!!! summary
    - `#embed` 把资源展开为**逗号分隔的 `int` 整数字面量**，值如同逐字节 `fgetc`，范围 `[0, UCHAR_MAX]`。
    - 搜索模型平行于 `#include`：方括号资源搜索 / 引号资源搜索（失败退回方括号）；推荐使用独立的搜索路径。
    - 参数部分总是宏展开；宏形式的资源名拼不成 *header-name* 是**非良构**（比 `#include` 严格）。
    - `limit`、`offset` 按 `#if` 规则求值，必须 ≥ 0；`count = max(min(limit, total − offset), 0)`。
    - `prefix`/`suffix` 只在非空时生效；`if_empty` 只在空时生效且替换整条指令。
    - 用 `unsigned char` 接收，避免窄化。
    - Clang 23：`#embed` 在 C++ 中可用（作为扩展告警），支持 `clang::offset` 而非标准 `offset`，未定义 `__cpp_pp_embed`。
