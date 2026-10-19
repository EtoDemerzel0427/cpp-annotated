---
title: 保留名字
summary: 标准库保留给自己的名字：包含标准头文件后不能把库里的名字定义成宏；C 库的函数签名、对象名和类型名在全局和 std 中都被保留；不以下划线开头的字面量后缀留给标准；已被移除的设施留下的僵尸名字仍然保留。在保留的语境中声明这些名字是未定义行为。
status: done
covers: *
related: namespace.constraints, constraints, lex.name, headers, over.literal, res.on.macro.definitions, cpp.replace.general, alt.headers
tags: 库, 保留名, 宏, UB, 链接
updated: 2026-10-19
---

!!! tldr
    - 一个翻译单元只要包含了任何一个标准库头文件，就不能 `#define` 或 `#undef` 任何标准库头文件中声明的名字，例如 `min`、`max`、`move`、`size`。
    - C 标准库的函数签名、对象名和类型名在全局命名空间和 `std` 中都被保留，即使没有包含对应的头文件。不要在全局定义自己的 `abs(int)` 或 `size_t`。
    - 用户定义字面量的后缀必须以下划线开头；不以下划线开头的留给标准，含 `__` 的留给实现。
    - 已从标准中移除的设施（`auto_ptr`、`bind1st`、`<strstream>`…）留下的名字仍然被保留，叫做僵尸名字。
    - 在保留的语境中声明这些名字是未定义行为，编译器通常不会报错。

核心语言已经在 [[lex.name]] 中保留了一批[[g:reserved-identifier|标识符]]：含双下划线的、以下划线加大写字母开头的，以及在全局命名空间中以下划线开头的。这一节是库层面的补充：普通的、不带下划线的名字，只要和标准库发生冲突，也可能是保留的。

## 三类保留名字 [reserved.names.general]

¶1 标准库保留三类名字：宏（¶1.1）、全局名字（¶1.2）、具有外部链接的名字（¶1.3）。

¶2 程序在名字被保留的语境中声明或定义这个名字，行为未定义，第 16 章明确允许的除外。

下面各小节分别说明哪些名字在什么语境中被保留。

## 不能把库里的名字定义成宏 [macro.names]

```cpp ub
#include <cstdio>
#define move(x) static_cast<decltype(x)&&>(x)   // UB：move 声明于 <utility>
#define size 100                                 // UB：std::size 声明于 <iterator> 等
#define min(a, b) ((a) < (b) ? (a) : (b))        // UB：min 声明于 <algorithm>
#undef assert                                    // UB：assert 声明于 <cassert>
int main() {}
```

!!! std
    A translation unit that includes a standard library header shall not `#define` or `#undef` names declared in any standard library header.

¶1 包含了标准库头文件的翻译单元，不得 `#define` 或 `#undef` 任何标准库头文件中声明的名字。

这里有两个"任何"。只要包含了任何一个标准头文件，哪怕只是 `<cstdio>`，就不能把任何一个标准头文件里的名字定义成宏，不限于自己包含的那个。上例只包含了 `<cstdio>`，四行全都违规。

为什么要这样一刀切？因为标准允许一个 C++ 标准头文件包含其他标准头文件（[[res.on.headers#1]]）。`<cstdio>` 在某个实现里可能间接包含了 `<algorithm>`，标准不想让程序是否合法取决于这种实现细节。

### `<windows.h>` 的 min 和 max

最常见的违规来自 Windows 的 `<windows.h>`，它把 `min`、`max` 定义成了函数式宏。函数式宏只在名字后面紧跟左括号时才展开，所以给函数名加一层括号就能避开：

<div class="compare" markdown="1">

```cpp error
#define min(a, b) ((a) < (b) ? (a) : (b))
#include <algorithm>
int main() {
  return std::min(1, 2);
  // 展开成 std::((1) < (2) ...)
  // error: expected unqualified-id
}
```

```cpp run ok
#define min(a, b) ((a) < (b) ? (a) : (b))
#include <algorithm>
int main() {
  int x = (std::min)(1, 2);
  // min 后面不是 (，宏不展开
  return x == 1 ? 0 : 1;
}
```

</div>

两边定义 `min` 宏本身都已经违反了 [macro.names]，右边的写法只是让代码在这种环境里能编译。更好的办法是在包含 `<windows.h>` 之前定义 `NOMINMAX`，让它不定义这两个宏。

!!! impl "libc++ 的自我保护"
    libc++ 在内部头文件里用 `#pragma push_macro` 保存，再 `#undef` 掉 `min`、`max`、`refresh`、`move`、`erase` 这几个最常见的宏（后三个来自 curses 库），头文件结束时恢复（`<__undef_macros>`）。这保证了 `#include <algorithm>` 本身不被破坏，但用户代码里的 `std::min(...)` 仍然会被宏展开。

!!! note "把关键字定义成宏"
    `#define private public` 违反的是另一条规则。[[cpp.replace.general#9]] 是核心语言的规定：任何翻译单元都不得把关键字、`final` / `override` 这类有特殊含义的标识符、属性记号定义为宏，与是否包含标准头文件无关。这条规则要求诊断，本机 Clang 给出警告 `-Wkeyword-macro`。反过来，标准库头文件自己也不得把关键字定义为宏（[[headers#8]]）。

## C 库的名字和签名 [extern.names]

```cpp ub
// 没有包含任何头文件
int abs(int x) { return x < 0 ? -x : x; }   // UB：C 库函数签名 abs(int) 被保留
double atof(const char*) { return 0; }      // UB：同上
int main() { return abs(-1); }
```

本机 Clang 编译这段代码没有任何警告，运行结果也正常。但链接时它可能与 C 库的 `abs` 发生重复定义，也可能被链接器选中，替换掉库内部对 `abs` 的调用；编译器还可能把 `abs` 当作内建函数，根本不调用你的定义。这些后果都取决于工具链，所以标准把它定为 UB。

¶1 头文件中声明为具有外部链接的对象，其名字保留给实现，用来指代这个库对象，在 `std` 和全局命名空间中都是如此。脚注 141 举的例子是 `<cerrno>` 中的 `errno`。

¶2 头文件中声明为具有外部链接的全局函数签名，保留给实现，用来指代这个函数。脚注 142 举的例子是 `<csetjmp>` 的 `setjmp(jmp_buf)` 和 `<cstdarg>` 的 `va_end(va_list)`。

¶3 来自 C 标准库、具有外部链接的名字，保留给实现用作 `extern "C"` 链接的名字，在 `std` 和全局命名空间中都是如此。

¶4 来自 C 标准库、具有外部链接的函数签名，保留给实现用作同时具有 `extern "C"` 和 `extern "C++"` 链接的函数签名，或者用作全局命名空间中的名字。脚注 143 说明，`<cuchar>`、`<cwchar>`、`<cwctype>` 中的签名总是保留的。

保留与否看的是名字（或签名）加上它所在的命名空间：

| 声明 | 是否违规 |
|---|---|
| 全局的 `int abs(int)`、`int errno;` | 违规 |
| 全局的 `static int abs(int)` | 违规：¶4 保留的是全局命名空间中的名字，与链接无关 |
| `namespace app { int abs(int); }`、类成员 `abs`、局部变量 `abs` | 不违规 |
| 全局的 `int abs(MyType)` | 不违规：签名不同 |
| 全局的 `ssize_t read(int, void*, size_t)` | 不受 C++ 标准保护，但 POSIX 系统上会与系统函数冲突 |

## C 库的类型 [extern.types]

```cpp run ok
#include <cstddef>
#include <stddef.h>
#include <type_traits>
static_assert(std::is_same_v<::size_t, std::size_t>);
static_assert(std::is_same_v<::ptrdiff_t, std::ptrdiff_t>);
int main() {}
```

¶1 对 C 标准库中的每个类型 `T`，`::T` 和 `std::T` 都保留给实现；两者都声明时必须是同一个类型。

这保证了混用 `<stddef.h>` 和 `<cstddef>` 的代码里不会出现两个不同的 `size_t`。对程序而言，这意味着不能在全局声明自己的 `size_t`、`FILE`、`tm`、`div_t` 等。老代码里常见的 `typedef unsigned int size_t;` 就是 UB。

## 字面量后缀 [usrlit.suffix]

```cpp run ok
unsigned long long operator""_km(unsigned long long v) { return v * 1000; }
int main() { return 3_km == 3000 ? 0 : 1; }
```

¶1 不以下划线开头的字面量后缀（[[over.literal]]）保留给将来的标准化；含双下划线 `__` 的后缀保留给 C++ 实现。

标准库自己的后缀都不带下划线：`s`、`sv`、`h`、`min`、`ms`、`us`、`ns`、`y`、`d`、`i`、`il`、`if` 等。用户的后缀必须以下划线开头。本机 Clang 对 `operator"" km`（不带下划线）给出警告：这样的后缀是保留的，不会有任何字面量调用这个运算符。不带空格的 `operator""km` 则直接报错。

还有一个细节。写成 `operator"" _Km` 时，引号和后缀之间有空格，`_Km` 是一个独立的标识符，以下划线加大写字母开头，按 [[lex.name]] 是保留标识符；这种带空格的写法在 C++23 中也已弃用。写成 `operator""_Km` 时，`_Km` 是 ud-suffix 的一部分，不受这条限制。统一使用无空格、下划线加小写字母的形式最省事。

## 僵尸名字 [zombie.names]

标准库的设施被移除之后，它的名字不会立刻还给用户。实现为了兼容旧代码，可能仍然以扩展的形式或在旧标准模式下提供它们，用户拿这些名字定义自己的东西就会冲突。这些名字叫做**僵尸名字**（[[g:zombie-name]]，zombie names）。

¶1 表 38 中的名字在命名空间 `std` 中保留给以前的标准化：

| 类别 | 名字（节选） | 来源 |
|---|---|---|
| 智能指针 | `auto_ptr`、`auto_ptr_ref` | C++11 弃用，C++17 移除 |
| 函数适配器 | `unary_function`、`binary_function`、`bind1st`、`bind2nd`、`ptr_fun`、`mem_fun`、`not1`、`not2`… | C++98 的适配器 |
| 算法 | `random_shuffle` | C++14 弃用，C++17 移除 |
| 异常 | `unexpected_handler`、`set_unexpected`、`get_unexpected`、`uncaught_exception` | 动态异常规范及其配套设施 |
| 垃圾回收支持 | `declare_reachable`、`undeclare_reachable`、`get_pointer_safety`、`pointer_safety` 等 | C++11 引入，C++23 移除 |
| 临时缓冲区 | `get_temporary_buffer`、`return_temporary_buffer`、`raw_storage_iterator` | |
| 类型萃取 | `is_literal_type`、`is_literal_type_v`、`result_of`、`result_of_t` | |
| 编码转换 | `wstring_convert`、`wbuffer_convert`、`codecvt_utf8`、`codecvt_utf16`、`codecvt_utf8_utf16`、`codecvt_mode` 等 | `<codecvt>` |
| 字符数组流 | `strstream`、`istrstream`、`ostrstream`、`strstreambuf` | `<strstream>` |
| C 函数 | `gets` | C11 移除 |

¶2 表 39 中的名字作为成员保留，可移植的代码不得把它们用作对象式宏的名字：`argument_type`、`first_argument_type`、`second_argument_type`、`io_state`、`open_mode`、`seek_dir`、`op`、`preferred`、`strict`。

¶3 表 40 中的名字作为成员函数保留，可移植的代码不得把它们用作函数式宏的名字：`converted`、`freeze`、`from_bytes`、`pcount`、`stossc`、`to_bytes`。

¶4 表 41 中的头文件名保留给以前的标准化：`<ccomplex>`、`<ciso646>`、`<codecvt>`、`<cstdalign>`、`<cstdbool>`、`<ctgmath>`、`<strstream>`。

连成员名都要保留，是因为实现可能还提供着这些旧成员。本机 libc++ 的 `<ios>` 在 C++14 及以前的模式下仍有 `typedef iostate io_state;`。如果用户 `#define io_state 1`，再在 C++14 模式下包含 `<ios>`，这一行就会被宏改写成无效代码。表 39 里的 `op` 来自 `binder1st` 的成员，`preferred`、`strict` 来自已移除的 `pointer_safety` 枚举。

本机 libc++ 仍然附带表 41 中的全部头文件，`-std=c++2c` 下包含它们不会产生诊断，但其中被移除的内容已经不提供了：`std::codecvt_utf8` 会报 "no member named 'codecvt_utf8' in namespace 'std'"。用户也不能自己写一个名为 `codecvt` 的头文件放进标准包含路径，那是 [[alt.headers]] 的 UB。

## 思考题

!!! question "思考题 1"
    下面的程序只包含了 `<cstdio>`，它违反 [macro.names] 吗？
    ```cpp
    #include <cstdio>
    #define emplace_back push_back
    int main() {}
    ```

<details markdown="1">
<summary>答案</summary>

违反。`emplace_back` 在 `<vector>`、`<deque>`、`<list>` 等头文件中声明，虽然这个翻译单元没有包含它们，但 [macro.names] 说的是任何标准库头文件中声明的名字。行为未定义（[reserved.names.general] ¶2）。
</details>

!!! question "思考题 2"
    在自己的命名空间里定义 `int app::printf(const char*, ...)` 合法吗？在全局定义 `static int printf(const char*, ...)` 呢？

<details markdown="1">
<summary>答案</summary>

`app::printf` 合法：[extern.names] 只保留 `std` 和全局命名空间中的名字与签名。

全局的 `static int printf(const char*, ...)` 不合法：¶4 把 C 库的函数签名保留为全局命名空间中的名字，不论链接如何。如果同时包含了 `<stdio.h>`，它还会和已有的声明冲突（同一签名，链接不同），直接编译失败。
</details>
