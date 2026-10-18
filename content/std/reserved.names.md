---
title: 保留名字
summary: 标准库保留三类名字：宏、全局名字、外部链接的名字；在保留的语境中声明它们即 UB。包括：已被移除设施留下的"僵尸名字"（auto_ptr、bind1st、<codecvt>……）；包含标准头文件后不得 #define/#undef 其中声明的任何名字；C 库的对象名与函数签名在 std 和全局命名空间中都被保留；::T 与 std::T 必须是同一类型；不以下划线开头的字面量后缀保留给标准。
status: done
covers: *
related: namespace.constraints, constraints, lex.name, headers, using.linkage, over.literal, res.on.macro.definitions, cpp.replace.general
tags: 库, 保留名, 宏, UB, 链接
updated: 2026-10-18
---

[[lex.name]] 在核心语言层面保留了一批**标识符**：含双下划线的、以下划线加大写字母开头的（任何用途）、以下划线开头的（作全局名字）。本节 [reserved.names] 是标准库层面的补充：即使是普通的、不带下划线的名字，只要它与标准库"撞车"，也可能被保留。

## 三类保留与总后果（[reserved.names.general]）

¶1 C++ 标准库保留下列种类的名字：

- **¶1.1 宏**；
- **¶1.2 全局名字**；
- **¶1.3 具有外部链接的名字**。

¶2 若程序在名字被保留的语境中声明或定义该名字（第 16 章明确允许的除外），行为**未定义**。

注意与 [[lex.name]] ¶4 的区别：那里使用保留标识符是 {{ifndr}}，这里是 {{ub}}——但对程序员来说结论一样：编译器多半不会报错，后果自负。

## 僵尸名字（[zombie.names]）

当一个标准库设施被**移除**后，它的名字并不会立即"解放"给用户使用：实现可能出于兼容性仍然提供它们（以扩展的形式，或在旧标准模式下），用户若用这些名字定义自己的东西，就会与之冲突。这些"死而不僵"的名字就是[[g:zombie-name|**僵尸名字**]]（zombie names）。

¶1 在命名空间 `std` 中，表 38 的名字保留给**先前的标准化**：

| 类别 | 名字（节选） | 原设施 |
|---|---|---|
| 智能指针 | `auto_ptr`、`auto_ptr_ref` | C++11 弃用、C++17 移除 |
| 函数适配器 | `binary_function`、`unary_function`、`bind1st`、`bind2nd`、`binder1st`、`binder2nd`、`ptr_fun`、`mem_fun`、`mem_fun_ref`、`not1`、`not2`、`unary_negate`、`binary_negate`、`pointer_to_unary_function`…… | C++98 时代的适配器 |
| 算法 | `random_shuffle` | C++14 弃用、C++17 移除 |
| 异常 | `unexpected_handler`、`set_unexpected`、`get_unexpected`、`uncaught_exception` | 动态异常规范及其配套 |
| 垃圾回收支持 | `declare_reachable`、`undeclare_reachable`、`declare_no_pointers`、`undeclare_no_pointers`、`get_pointer_safety`、`pointer_safety` | C++11 引入、C++23 移除 |
| 临时缓冲 | `get_temporary_buffer`、`return_temporary_buffer`、`raw_storage_iterator` | |
| 类型萃取 | `is_literal_type`、`is_literal_type_v`、`result_of`、`result_of_t` | |
| 字符串转换 | `wstring_convert`、`wbuffer_convert`、`codecvt_utf8`、`codecvt_utf16`、`codecvt_utf8_utf16`、`codecvt_mode`、`little_endian`、`generate_header`、`consume_header` | `<codecvt>` |
| 流 | `strstream`、`istrstream`、`ostrstream`、`strstreambuf` | `<strstream>` |
| C 函数 | `gets` | C11 移除 |

¶2 表 39 的名字作为**成员**保留给先前的标准化，在可移植代码中不得用作**对象式宏**的名字：`argument_type`、`first_argument_type`、`second_argument_type`、`io_state`、`open_mode`、`seek_dir`、`op`、`preferred`、`strict`。

¶3 表 40 的名字作为**成员函数**保留给先前的标准化，在可移植代码中不得用作**函数式宏**的名字：`converted`、`freeze`、`from_bytes`、`pcount`、`stossc`、`to_bytes`。

¶4 表 41 的**头文件名**保留给先前的标准化：`<ccomplex>`、`<ciso646>`、`<codecvt>`、`<cstdalign>`、`<cstdbool>`、`<ctgmath>`、`<strstream>`。

为什么连**成员名**都要保留？因为实现可能仍然提供这些旧成员。例如 libc++ 的 `<ios>` 中：

```cpp
#    if _LIBCPP_STD_VER <= 14
  typedef iostate io_state;
  typedef openmode open_mode;
  typedef seekdir seek_dir;
#    endif
```

若用户 `#define io_state 1`，然后在 C++14 模式下包含 `<ios>`，这段代码就被宏改写成乱码。`op`、`preferred`、`strict` 来自已移除的 `pointer_safety` 枚举（`relaxed`、`preferred`、`strict`）与 `binder1st` 的 `op` 成员——`relaxed` 不在表中，因为它仍是 `memory_order::relaxed` 的现役名字（而且现役的名字本来就受 [macro.names] 保护）。

本机 libc++ 仍然随附表 41 中的全部头文件，在 `-std=c++2c` 下包含它们不会产生诊断——但其中被移除的内容已不再提供（例如 `std::codecvt_utf8` 在 C++2c 模式下报 "no template named 'codecvt_utf8' in namespace 'std'"）。用户也不能自己写一个名为 `codecvt` 的头文件放进包含路径——那是 [[alt.headers]] 的 UB。

## 宏名（[macro.names]）

!!! std
    A translation unit that includes a standard library header shall not `#define` or `#undef` names declared in any standard library header.

    包含了标准库头文件的翻译单元，不得 `#define` 或 `#undef` 在**任何**标准库头文件中声明的名字。

注意两个"任何"：

- 你包含了**任何一个**标准头文件（哪怕只是 `<cstddef>`）；
- 就不能把**任何一个**标准头文件中声明的名字（不只是你包含的那个）定义成宏。

所以，只要包含了标准库头文件，以下全部是 UB：

```cpp ub
#include <cstdio>
#define move(x) static_cast<decltype(x)&&>(x)   // UB：move 声明于 <utility>
#define size 100                                 // UB：size 声明于 <iterator> 等
#define private public                           // 违反 [cpp.replace.general] ¶9：不得把关键字定义为宏
#define min(a, b) ((a) < (b) ? (a) : (b))        // UB：min 声明于 <algorithm>
#undef assert                                    // UB：assert 声明于 <cassert>
int main() { }
```

（`#define private public` 这一行属于另一条规则：[[cpp.replace.general#9]] 是**核心语言**规则，禁止任何翻译单元把关键字、特殊含义标识符（`final`、`override`……）、属性记号定义为宏——与是否包含标准头文件无关（本机 Clang 给出 "keyword is hidden by macro definition [-Wkeyword-macro]" 警告）。早先的标准把这一条写在本节 [macro.names] 中，后来移入了预处理章节。）

最臭名昭著的违规来自 Windows 的 `<windows.h>`，它把 `min`、`max` 定义成函数式宏。函数式宏只在名字**后面紧跟左括号**时展开，所以有两种常见的绕法：

```cpp run ok
#define min(a, b) ((a) < (b) ? (a) : (b))   // 模拟 <windows.h>（严格说已是 UB）
#include <algorithm>
int main() {
  int x = (std::min)(1, 2);    // (std::min) 后面不是 '(' 紧跟名字 → 宏不展开
  return x == 1 ? 0 : 1;
}
```

不加括号的 `std::min(1, 2)` 会被展开成 `std::((1) < (2) ? (1) : (2))`，本机 Clang 报 "expected unqualified-id"。另一种绕法是在包含 `<windows.h>` 前定义 `NOMINMAX`。

!!! impl "实现的自我保护"
    实现知道用户会这么做，所以会自我防御。libc++ 在内部头文件中用 `_LIBCPP_PUSH_MACROS` / `_LIBCPP_POP_MACROS`（即 `#pragma push_macro`）加上 `<__undef_macros>`，在头文件内部临时 `#undef` 掉 `min`、`max`、`refresh`、`move`、`erase` 这几个最常见的"污染宏"（`refresh`、`erase`、`move` 来自 curses 库），头文件结束时再恢复。这让 `#include <algorithm>` 本身不被破坏，但用户代码中的 `std::min(...)` 仍然会被宏展开——libc++ 救不了调用点。

另见 [headers] ¶8：标准库头文件自己也不得把 C++ 关键字或运算符定义为宏；以及 [[res.on.macro.definitions]]：库的名字与全局函数签名保留给实现。

## 外部链接的名字（[extern.names]）

¶1 头文件中声明为具有外部链接的**对象**的每个名字，保留给实现用于指称具有外部链接的该库对象——**在命名空间 `std` 和全局命名空间中都是**。脚注：这样的保留名字包括 `<cerrno>` 中声明或定义的 `errno`。

¶2 头文件中声明为具有外部链接的每个**全局函数签名**，保留给实现用于指称具有外部链接的该函数签名。脚注：这样的保留函数签名包括 `<csetjmp>` 中的 `setjmp(jmp_buf)` 和 `<cstdarg>` 中的 `va_end(va_list)`。

¶3 来自 C 标准库的、声明为外部链接的每个**名字**，保留给实现用作具有 `extern "C"` 链接的名字，在 `std` 和全局命名空间中都是。

¶4 来自 C 标准库的、声明为外部链接的每个**函数签名**，保留给实现用作同时具有 `extern "C"` 和 `extern "C++"` 链接的函数签名，或用作全局命名空间中的命名空间作用域名字。脚注：`<cuchar>`、`<cwchar>`、`<cwctype>` 中声明的函数签名总是被保留，尽管 C 标准修正案 1 第 4.5.1 节对这些头文件有所限制。

翻译成人话：**即使你没有包含任何头文件**，也不能在全局命名空间（或 `std`）定义一个与 C 标准库同名、同签名的外部链接函数或对象。因为链接器只看符号名：

```cpp ub
// 没有包含任何头文件
int abs(int x) { return x < 0 ? -x : x; }   // UB：全局函数签名 abs(int) 被保留（¶4）
double atof(const char*) { return 0; }      // UB：同上
int errno;                                   // UB：errno 被保留（¶1）——而且 errno 通常是宏
int main() { return abs(-1); }
```

实践中的后果：你的 `abs` 可能与 C 库的 `abs` 发生链接冲突（重复定义），也可能被链接器静默选中，替换掉标准库内部对 `abs` 的调用——编译器还可能把 `abs` 当作内建函数直接优化掉你的定义。

这条规则**不保留**：

- 局部名字、类成员、你自己命名空间中的名字（`app::abs` 完全没问题）；
- 内部链接的名字（`static int abs(int)` 在全局命名空间——仍受 ¶4"用作全局命名空间中的命名空间作用域名字"的限制，不推荐）；
- 非 C 标准库的 POSIX 函数（`read`、`open`、`write`）——它们不受 C++ 标准保护，但受 POSIX 保护。

## 类型（[extern.types]）

¶1 对 C 标准库中的每个类型 `T`，类型 `::T` 和 `std::T` 都保留给实现；声明时，`::T` 必须与 `std::T` **相同**。

```cpp run ok
#include <cstddef>
#include <stddef.h>
#include <type_traits>
static_assert(std::is_same_v<::size_t, std::size_t>);       // 必须是同一类型
static_assert(std::is_same_v<::ptrdiff_t, std::ptrdiff_t>);
int main() { }
```

这条规则保证了混用 `<stddef.h>` 与 `<cstddef>` 的代码不会出现"两个不同的 `size_t`"。对用户的约束是：不能在全局命名空间声明自己的 `size_t`、`FILE`、`tm`、`div_t`…… 例如老代码中的 `typedef unsigned int size_t;` 就是 UB。

## 用户定义字面量后缀（[usrlit.suffix]）

¶1 **不以下划线开头**的字面量后缀标识符（[[over.literal]]）保留给将来的标准化。含**双下划线** `__` 的字面量后缀标识符保留给 C++ 实现使用。

标准库自己的字面量后缀都不带下划线：`s`（`std::string`、`std::chrono::seconds`）、`sv`、`h`、`min`、`ms`、`us`、`ns`、`y`、`d`、`i`、`il`、`if`。用户的后缀必须以下划线开头：

```cpp run ok
unsigned long long operator""_km(unsigned long long v) { return v * 1000; }  // OK
int main() { return 3_km == 3000 ? 0 : 1; }
```

```cpp
unsigned long long operator"" km(unsigned long long v);
// 本机 Clang：warning: user-defined literal suffixes not starting with '_' are reserved;
//             no literal will invoke this operator [-Wuser-defined-literals]
```

注意语言层面的另一个细节：写成 `operator"" _Km`（引号与后缀间有空格，C++23 起弃用）时，`_Km` 是一个独立的标识符，以下划线加大写字母开头，按 [[lex.name]] 是保留标识符；写成 `operator""_Km`（无空格）则 `_Km` 是 *ud-suffix* 的一部分，不受此限。为避免这些细节，统一使用无空格、下划线加小写字母的形式。

## 思考题

!!! question "思考题 1"
    以下程序只包含了 `<cstdio>`。它违反了 [macro.names] 吗？

    ```cpp
    #include <cstdio>
    #define emplace_back push_back
    int main() { }
    ```

<details markdown="1">
<summary>展开查看答案与解析</summary>

违反。[macro.names] 说的是"包含了**某个**标准库头文件的翻译单元，不得 `#define` 在**任何**标准库头文件中声明的名字"。`emplace_back` 在 `<vector>`、`<deque>`、`<list>` 等中声明，尽管本 TU 没有包含它们——但 `<cstdio>` 的实现可能间接包含了它们（[[res.on.headers#1]] 允许 C++ 头文件包含其他 C++ 头文件），标准不想让程序的合法性依赖于这种实现细节，于是一刀切。行为未定义（[reserved.names.general] ¶2）。
</details>

!!! question "思考题 2"
    在自己的命名空间 `app` 里定义 `int app::printf(const char*, ...)` 合法吗？在全局定义 `static int printf(const char*, ...)` 呢？

<details markdown="1">
<summary>展开查看答案与解析</summary>

`app::printf` 合法：[extern.names] 只保留 `std` 与全局命名空间中的名字和签名。但要小心 ADL 和 `using namespace` 造成的混淆。

全局的 `static int printf(const char*, ...)` 不合法：¶4 把 C 库的函数签名保留"用作全局命名空间中的命名空间作用域名字"，不论链接如何。实践中若同时包含了 `<stdio.h>`，它还会与已有声明冲突（同名同参数，链接不同），直接编译失败。
</details>

## 小结

!!! summary "核心要点"
    - 标准库保留宏、全局名字、外部链接名字；在保留语境中声明即 UB。
    - 僵尸名字：被移除设施的名字、成员名、头文件名仍然保留——不能拿来作 `std` 中的名字、对象式/函数式宏、头文件名。
    - 包含任一标准头文件后，不得 `#define`/`#undef` 任一标准头文件中声明的名字（`min`、`max`、`move`、`size`……）；`(std::min)(a, b)` 可以绕过函数式宏。
    - C 库的对象名、函数签名在 `std` 和全局命名空间中都被保留——即使你没包含头文件。
    - `::T` 必须与 `std::T` 是同一类型；不要自己 `typedef size_t`。
    - 用户字面量后缀必须以下划线开头；含 `__` 的后缀保留给实现。
