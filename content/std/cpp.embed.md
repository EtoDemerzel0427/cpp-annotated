---
title: 资源包含
summary: C++26 的 #embed 指令把任意二进制文件的字节展开为逗号分隔的整数列表；本页讲它展开成什么、资源怎样查找，以及 limit、offset、prefix、suffix、if_empty 五个参数。
status: done
covers: *
since: c++26
papers: P1967R14
related: cpp.include, cpp.cond, cpp.pre, cpp.predefined, dcl.init.list, dcl.init.aggr
tags: 预处理, embed, C++26
updated: 2026-10-19
---

!!! tldr
    - `#embed "file"` 在预处理阶段把文件内容展开成逗号分隔的 `int` 整数字面量，每个值如同用 `fgetc` 读出的一个字节，范围是 0 到 `UCHAR_MAX`。
    - 展开结果没有花括号，出现在哪里就按那里的语法解释：数组初始化、函数实参、`std::vector` 的初始化列表都可以。
    - 用 `unsigned char` 接收数据；用 `char` 时，有符号 `char` 遇到大于 127 的字节就是窄化，非良构。
    - `limit`、`offset` 截取一段字节；`prefix`、`suffix` 只在资源非空时插入记号；`if_empty` 只在资源为空时替换整条指令。
    - 资源的查找方式与 `#include` 平行但相互独立；`__has_embed` 可以在 `#if` 中探测资源和参数。

{{c++26}} 在 `#embed` 之前，把二进制文件放进程序主要有两种办法。一是用 `xxd -i` 之类的工具把文件转成 `{0x12, 0x34, ...}` 形式的源文件，要多一个构建步骤，编译器还要解析几百万个整数字面量。二是用汇编器的 `.incbin` 或链接器选项，不可移植，而且数据在编译期不可见，不能用于 `constexpr` 计算。

`#embed` 把这件事交给预处理器。语义上它展开为一串整数字面量，所以能用在任何需要整数列表的地方，包括常量求值；实现上，编译器可以跳过先生成文本再解析的过程，直接使用文件的字节。它与 C23 的 `#embed` 同源，由 [[P1967R14]] 引入 C++26。

## 展开成什么（¶11–¶13）

```cpp run title="embed-self.cpp" ok flags="-std=c++2c -Wno-c23-extensions"
// 这个文件以 "// " 开头，下面把它自身嵌入
constexpr unsigned char head[] = {
#embed __FILE__ limit(3)
};
static_assert(sizeof head == 3);
static_assert(head[0] == '/' && head[1] == '/' && head[2] == ' ');
int main() {}
```

`__FILE__` 展开成当前源文件名的字符串字面量，所以这个例子在任何地方都能编译。`limit(3)` 只取前三个字节。本页其余能运行的例子都用这个办法。Clang 23 在 C++ 模式下把 `#embed` 当作扩展，每次使用都给出 `-Wc23-extensions` 警告，所以例子关闭了这个警告。

¶11 除非参数另有改变，`#embed` 指令替换为一个逗号分隔的列表，元素是 `int` 类型的整数字面量。

¶12 每个元素的值用 `fgetc` 定义：先以二进制方式从资源中读 *resource-offset* 次并丢弃结果（偏移量由 `offset` 参数给出，见下文），再读 *resource-count* 次，依次得到列表的元素。如果这些读取中有一次返回 `EOF`，程序非良构。`fgetc` 返回的是由 `unsigned char` 转换来的 `int`，所以每个元素的值都在 0 到 `UCHAR_MAX` 之间，没有负数。

¶13 推荐做法：每个整数字面量的值应当如实反映资源的比特流，必要时实现要考虑翻译环境和执行环境之间的差异。标准例 2 表达了这个期望：编译期嵌入的数据与运行时用 `std::ifstream` 以二进制方式读同一个文件得到的数据，用 `memcmp` 比较应当相等。

### 只是一串逗号分隔的值

展开结果在语法上只是 `v1, v2, ..., vn`，不带花括号。标准例 3 演示了这一点：

```cpp
int i = {
#embed "i.dat"
};            // 若 i.dat 只产生一个值，则良构
int i2 =
#embed "i.dat"
;             // 同上
struct s { double a, b, c; struct { double e, f, g; } x; double h, i, j; };
s x = {
#embed "s.dat"  // 若产生不超过 9 个值，则良构：按花括号省略的规则分配给各成员
};
```

所以它也能出现在函数调用的实参列表和 `std::vector` 的初始化列表里：

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
  return (v.size() == 8 && s == '#' + 'i' + 'n') ? 0 : 1;   // 文件以 "#in" 开头
}
```

!!! pitfall "用 unsigned char 接收"
    元素是 `int` 类型的整数字面量，8 位字节时取值 0 到 255。用它初始化 `char` 数组时，如果 `char` 是有符号的且某个字节不小于 128，就是列表初始化中的窄化转换（[[dcl.init.list]]），程序非良构。所以应当用 `unsigned char` 接收。`std::byte` 不能从 `int` 隐式转换，也不能直接接收。

    Clang 23 在这里与标准不一致：`#embed` 直接初始化 `char` 数组时，即使有 `0xFF` 字节也不报窄化，得到的值是 `-1`；而把 `-E` 的输出 `{255, 1}` 拿去编译，就会报窄化错误。原因是 Clang 对 `#embed` 走了一条不生成整数字面量的快速路径。

## 资源怎样查找（¶1–¶7）

`#embed` 的查找规则几乎逐字照搬 `#include`（[[cpp.include]]），只是把头文件换成了资源（resource）：翻译环境中可以访问的任意数据源。

- ¶1 **方括号资源搜索**（[[g:bracket-resource-search|bracket resource search]]）：在一系列位置中查找由字符序列唯一标识的资源，位置和标识方式由实现定义。
- ¶2 **引号资源搜索**（[[g:quote-resource-search|quote resource search]]）：查找以字符序列命名的资源，方式由实现定义；不支持或找不到时，退回方括号资源搜索。

¶3–¶5 `# embed header-name 参数...` 用资源数据导出的预处理记号替换这条指令。`<...>` 形式做方括号资源搜索，`"..."` 形式做引号资源搜索。

¶6 如果方括号资源搜索失败，或者找到的资源实现无法处理，程序非良构。注 1 补充，即使写了 `limit(0)`，或者只是在 `__has_embed` 中探测，找到却无法处理的资源也使程序非良构。

¶7 推荐做法：资源的搜索路径应当与 `#include` 的类似但相互独立。GCC 和 Clang 为此提供了 `--embed-dir=<dir>` 选项。Clang 23 实测，`#embed <x.bin>` 只在 `--embed-dir` 指定的目录中查找，`-I` 目录对它无效；`#embed "x.bin"` 先在包含者所在的目录查找。分开的好处是，`#embed <logo.png>` 不会到系统头文件目录里去找，`#include` 也不会找到资源目录里的文件。

## 资源有多大（¶9–¶10）

¶9 资源的大小用几个量描述：

| 量 | 含义 |
|---|---|
| *implementation-resource-width* | 资源的大小，以位计，由实现定义 |
| *implementation-resource-count* | 上一项除以 `CHAR_BIT`，即字节数 |
| *resource-offset* | 有 `offset` 参数时为其值，否则为 0 |
| *resource-count*（[[g:resource-count]]） | 有 `limit` 时为 max(min(limit, 字节数 − offset), 0)，否则为 max(字节数 − offset, 0) |

*resource-count* 为 0 的资源是**空资源**。

如果资源的位数不是 `CHAR_BIT` 的整数倍，程序非良构，¶10 的例 1 是一个 6 位的资源。大小以位计，是为了照顾字节不是 8 位的平台，以及不来自普通文件的资源。

公式里的 `max(..., 0)` 意味着 `offset` 超过资源大小不是错误，资源只是变成空的。`if_empty` 参数就是为这种情况准备的。

## 参数（¶8、[[cpp.embed.param]]）

¶8 无论哪种形式，`#embed` 后面的参数都先像普通文本一样做宏展开，展开后必须是参数序列的形式。所以参数里可以用宏：

```cpp
#define MAX_HEADER 64
#embed "file.bin" limit(MAX_HEADER)
```

也正因为如此，[[cpp.pre#4]] 禁止把 `limit`、`prefix`、`suffix`、`if_empty` 定义为宏，否则参数名本身会被展开掉。

标准参数有五个，每个在一条指令中至多出现一次。形如 `vendor::name` 的带前缀参数是有条件支持的，语义由实现定义（[[cpp.pre#4]]）。

| 参数 | 作用 | 资源为空时 |
|---|---|---|
| `limit(n)` | 最多取 n 个元素 | |
| `offset(n)` | 先跳过 n 个元素 | |
| `prefix(...)` | 在列表前插入这些记号 | 忽略 |
| `suffix(...)` | 在列表后插入这些记号 | 忽略 |
| `if_empty(...)` | | 整条指令替换为这些记号 |

### limit 与 offset

`limit(...)` 指定列表中最多有多少个元素（[[cpp.embed.param.limit]]）。括号里的内容按 `#if` 的规则（[[cpp.cond]]）作为常量表达式求值，但不再做一次宏展开，因为 ¶8 已经展开过了。结果必须是不小于 0 的整数常量表达式，括号内也不能出现 `defined`。

按 `#if` 的规则求值意味着未定义的标识符变成 0。[[cpp.embed.param.limit]] 的例 1：

```cpp
#undef DATA_LIMIT
#if __has_embed(<data.dat> limit(DATA_LIMIT))   // 等价于 limit(0)
#endif
```

同一条款的例 2 有一个细节：`#embed <data.dat> limit(__has_include("a.h"))` 合法，因为 `#if` 规则里可以用 `__has_include`；同样的内容写进 `__has_embed(...)` 里却非良构，因为 `__has_include` 不能出现在 `__has_embed` 的括号里。

`limit` 常用来只取文件头部，例如魔数或签名，也可以从无限长的资源（如 `/dev/urandom`）中取有限个字节：

```cpp
constexpr unsigned char sound_signature[] = {
#embed <sdk/jump.wav> limit(2+2)     // 只取前 4 字节，即 "RIFF"
};
static_assert(sizeof(sound_signature) == 4);
```

`offset(...)` 指定先跳过多少个元素（[[cpp.embed.param.offset]]），求值规则和限制与 `limit` 相同。两者组合时先跳过、再限量：

```cpp
#embed <sdk/jump.wav>                    // arr
#embed <sdk/jump.wav> offset(2)          // offset_arr[0] == arr[2]
#embed <sdk/jump.wav> offset(1) limit(1) // offset_limit_arr[0] == arr[1]
```

Clang 23 还不支持标准的 `offset`，报 unknown embed preprocessor parameter 'offset'，但提供了语义相同的扩展参数 `clang::offset`：

```cpp run title="embed-offset.cpp" impl flags="-std=c++2c -Wno-c23-extensions" cc=clang_trunk
// ABCDEFG
constexpr unsigned char mid[] = {
#embed __FILE__ clang::offset(3) limit(3)   // 跳过 "// "，取 "ABC"
};
static_assert(mid[0] == 'A' && mid[1] == 'B' && mid[2] == 'C');
int main() {}
```

### prefix、suffix 与 if_empty

`prefix(...)` 和 `suffix(...)` 在资源非空时把括号里的记号放在列表的紧前面或紧后面，资源为空时被忽略（[[cpp.embed.param.prefix]]、[[cpp.embed.param.suffix]]）。它们解决的是分隔符问题。下面是 [[cpp.embed.param.suffix]] 的例子：

```cpp
constexpr unsigned char whl[] = {
#embed "ches.glsl" \
  prefix(0xEF, 0xBB, 0xBF, ) /* 非空时加 UTF-8 BOM 和逗号 */ \
  suffix(,)                  /* 非空时补一个逗号 */
  0                          /* 总是以 0 结尾 */
};
// 空文件得到 { 0 }，非空时得到 { 0xEF, 0xBB, 0xBF, 数据..., 0 }
```

如果不用这两个参数，直接写 `{ 0xEF, 0xBB, 0xBF, #embed ..., 0 }`，资源为空时就会出现 `0xBF, , 0` 这样的连续逗号，这是语法错误。

一个常见的用法是生成以 0 结尾的字符串：

```cpp run title="embed-cstr.cpp" ok flags="-std=c++2c -Wno-c23-extensions"
// 本文件以 "//" 开头
constexpr unsigned char text[] = {
#embed __FILE__ limit(2) suffix(, 0)
};
static_assert(sizeof text == 3 && text[0] == '/' && text[2] == 0);
int main() {}
```

`if_empty(...)` 正好相反：资源非空时被忽略，为空时整条 `#embed` 指令替换为括号里的记号，`prefix` 和 `suffix` 自然也不出现（[[cpp.embed.param.if.empty]]）。

```cpp run title="embed-if-empty.cpp" ok flags="-std=c++2c -Wno-c23-extensions"
constexpr int v[] = {
#embed __FILE__ limit(0) prefix(1, ) suffix(, 2) if_empty(-1)
};
static_assert(sizeof v == sizeof(int) && v[0] == -1);   // 资源为空，只剩 if_empty
int main() {}
```

[[cpp.embed.param.if.empty]] 的三个例子说明了什么情况算空：`limit(0)` 让任何资源都为空，在 `__has_embed` 中也一样；只有 1 字节的资源加上 `offset(1)` 之后也为空。

## 用宏写资源名（¶14）

¶14 如果 `embed` 后面不是一个头文件名记号，整条指令的其余部分先做宏展开，再用紧跟 `embed` 的那些记号的拼写和空白拼出一个头文件名，空白怎样处理由实现定义。拼成了就按直接形式处理，拼不成则程序非良构。`#include` 的同样情况是 IFNDR，这里更严格。注 2 同样提醒，相邻的字符串字面量不会拼接。

注 3 强调，整条指令只做一次宏展开。例 4：

```cpp
#define EMPTY
#define X myfile
#define Y rsc
#define Z 42
#embed <myfile.rsc> prefix(Z)    // 直接形式：只展开头文件名之后的部分
#embed EMPTY <X.Y>  prefix(Z)    // 宏形式：整条展开，X、Y、Z 都被替换
// 两行都等价于 #embed <myfile.rsc> prefix(42)
```

Clang 23 对第二行不展开 `<X.Y>` 中的 `X`、`Y`，报 'X.Y' file not found，与草案不符。`#include` 的同类情况也是如此（见 [[cpp.include]]）。

## 用 __has_embed 探测

`__has_embed` 在 [[cpp.cond#4]] 中定义。它按 `#embed` 的方式处理括号中的记号，得到 `__STDC_EMBED_NOT_FOUND__`（0）、`__STDC_EMBED_FOUND__`（1）或 `__STDC_EMBED_EMPTY__`（2），这三个宏见 [[cpp.predefined]]。不认识的参数使结果为 0，而不是使程序非良构，所以可以先试厂商参数，再退回标准写法：

```cpp
#if __has_embed("logo.png" vendor::compress(zstd)) == __STDC_EMBED_FOUND__
  // 实现支持这个厂商参数，且资源非空
#elif __has_embed("logo.png") == __STDC_EMBED_FOUND__
  // 不用厂商参数
#endif
```

## 实现视角

!!! impl "为什么 #embed 快"
    标准语义是展开为整数字面量列表，但按 as-if 规则，实现只需要得到相同的结果。Clang 在预处理器中生成一个携带资源数据的特殊记号交给语法分析，最终形成 AST 节点 `EmbedExpr`。在初始化 `unsigned char` 数组之类的常见情形下，数据整块复制，不必为每个字节创建一个整数字面量节点。所以嵌入几十 MB 的资源在内存和时间上都可以接受。只有用 `-E` 输出预处理结果时，才真的打印成 `65, 66, 67, ...`。

!!! impl "依赖追踪"
    被嵌入的资源和被包含的头文件一样，会出现在 `-MD`、`-MMD` 生成的依赖文件中，资源改变时构建系统会重新编译。本机 Clang 23 实测确实如此。

!!! impl "Clang 23 的支持情况"
    `#embed` 在 C++ 模式下可用，但作为扩展给出警告；支持 `clang::offset` 而不支持标准的 `offset`；没有定义特性测试宏 `__cpp_pp_embed`。

## 历史与演进

!!! history
    - 在 `#embed` 之前，社区靠 `xxd -i`、`.incbin`、链接器的二进制输入等手段嵌入数据；也有过以库函数形式在编译期读文件的 `std::embed` 提案，没有被采纳。
    - C23 先标准化了 `#embed`。
    - C++26 通过 [[P1967R14]] 引入同一机制，同时加入 `__has_embed`、`__STDC_EMBED_*__` 宏和特性测试宏 `__cpp_pp_embed`。`offset` 参数是后来补上的。

## 思考题

!!! question "思考题 1"
    资源 `r.bin` 有 5 字节。下面每条指令展开为什么？
    ```cpp
    #embed "r.bin" offset(3) limit(10)
    #embed "r.bin" offset(7) prefix(1,) if_empty(0)
    #embed "r.bin" limit(0) suffix(,9)
    ```

<details markdown="1">
<summary>答案</summary>

按 ¶9，字节数是 5。

1. offset 为 3，resource-count = max(min(10, 5 − 3), 0) = 2，展开为第 4、5 个字节的值。
2. offset 为 7，resource-count = max(5 − 7, 0) = 0，资源为空：`prefix` 被忽略，整条指令替换为 `if_empty` 的内容 `0`。
3. resource-count = max(min(0, 5), 0) = 0，资源为空：`suffix` 被忽略；没有 `if_empty`，所以展开为空，什么记号也没有。
</details>

!!! question "思考题 2"
    为什么 `#embed` 的元素被规定为 `int` 类型、值取自 `fgetc`，而不是直接规定为 `unsigned char` 类型的值？

<details markdown="1">
<summary>答案</summary>

预处理器只能产生预处理记号，而整数字面量没有 `unsigned char` 类型的写法，最小的整数字面量类型是 `int`（[[lex.icon]]）。规定为 `int` 类型的整数字面量，`#embed` 就能当作纯文本理解（`-E` 的输出可以再次编译），也能用在任何能写整数列表的地方。值取自 `fgetc`，则把字节值精确地规定为非负的 `unsigned char` 值，避开了 `char` 是否有符号这一实现定义的差异。代价就是前面说的窄化问题：接收方要用 `unsigned char` 或更宽的类型。
</details>

## 小结

!!! summary
    - `#embed` 把资源展开为逗号分隔的 `int` 整数字面量，值如同逐字节 `fgetc`，范围是 0 到 `UCHAR_MAX`。
    - 搜索方式与 `#include` 平行：方括号资源搜索，引号资源搜索（找不到退回方括号搜索）；推荐使用独立的搜索路径。
    - 参数部分总是先宏展开；宏形式拼不出资源名是非良构，比 `#include` 严格。
    - `limit`、`offset` 按 `#if` 规则求值，必须不小于 0；元素个数是 max(min(limit, 字节数 − offset), 0)。
    - `prefix`、`suffix` 只在资源非空时生效；`if_empty` 只在资源为空时生效，并替换整条指令。
    - 用 `unsigned char` 接收，避免窄化。
