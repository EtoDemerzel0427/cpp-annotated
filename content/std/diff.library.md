---
title: C 标准库的差异
summary: Annex C.9：C++ 引入 C 标准库时做的显式修改——没有 <stdnoreturn.h> 和 <threads.h>；char8_t/char16_t/char32_t/wchar_t 是关键字而不是 typedef；<iso646.h> 不定义宏；NULL 是实现定义的空指针常量；strchr 等函数有 const 重载；exit/abort/atexit/longjmp 的行为受限；offsetof 只保证支持标准布局类；malloc 系列隐式创建对象。附 Clang 23 / libc++ 实测。
status: draft
covers: *
related: diff, diff.iso, support.c.headers, library.c, c.strings, support.types, support.start.term, c.malloc
tags: 附录, 兼容性, C, 标准库
updated: 2026-10-18
---

[diff.library] 汇总 C++ 标准库中**来自 C 标准库的部分**相对 C 原版的显式改动：哪些头文件不提供、哪些宏变成了关键字、哪些函数的声明或行为不同。它和 [[diff.iso]] 是一对：后者讲语言，这里讲库。

这些改动都源于同一个原因：C++ 的类型系统和对象模型比 C 更严格，C 库的一些"宽松"写法（返回去掉 `const` 的指针、用 `typedef` 定义字符类型、`setjmp`/`longjmp` 跳过一切清理）放进 C++ 就会和析构函数、重载、常量正确性冲突。

¶1 [diff.library.general]：本小节汇总 C 标准与 C++ 标准中取自 C 标准库的部分之间，在头文件、定义、声明和行为上的显式差异。

## 对头文件的修改 {#diff.mods.to.headers}

¶1 为了与 C 标准库兼容，C++ 标准库提供 [[support.c.headers]] 中列出的 C 头文件（`<stdio.h>` 等）。它们与 `<cstdio>` 等 `c` 前缀版本的区别在于名字落在哪个命名空间：`<cxxx>` 保证在 `std` 中声明，`<xxx.h>` 保证在全局命名空间中声明，两者都可能同时提供另一边（[[library.c]]）。

¶2 C 标准库的 `<stdnoreturn.h>` 和 `<threads.h>` 在 C++ 中**没有**对应的 C++ 头文件，这两个 C 头文件本身也不是 C++ 的一部分。原因很直接：`noreturn` 在 C++ 中是属性 `[[noreturn]]`，`<stdnoreturn.h>` 定义的 `noreturn` 宏会破坏它；`<threads.h>` 的功能由 `<thread>`、`<mutex>`、`<condition_variable>` 提供。

¶3 C 头文件 `<complex.h>` 和 `<tgmath.h>` **不包含** C 标准库中的任何内容，只是包含其他 C++ 头文件：`<complex.h>` 等价于包含 `<complex>`，`<tgmath.h>` 等价于包含 `<cmath>` 和 `<complex>`。也就是说，C 的 `double _Complex`、`I` 宏、类型泛型宏在 C++ 中都没有；C++ 用 `std::complex<double>` 和函数重载代替它们。

## 对定义的修改 {#diff.mods.to.definitions}

### `char8_t`、`char16_t`、`char32_t` {#diff.char16}

¶1 这三个类型在 C++ 中是**独立的类型**，而不是现有整数类型的 typedef（C 的 `<uchar.h>` 中，`char16_t` 是 `uint_least16_t` 的 typedef）。`char8_t`、`char16_t`、`char32_t` 在 C++ 中是关键字（[[lex.key]]），在 `<cuchar>` 中不作为宏或类型名出现。

后果之一：C++ 可以按这三个类型重载函数、特化模板，而在 C 中 `char16_t` 和 `uint_least16_t` 无法区分。

### `wchar_t` {#diff.wchar.t}

¶1 `wchar_t` 在 C++ 中是独立的类型，不是现有整数类型的 typedef；它是关键字，不在 `<cstddef>`、`<cstdlib>`、`<cwchar>` 中作为宏或类型名出现。

### 头文件 `<iso646.h>` {#diff.header.iso646.h}

¶1 `and`、`and_eq`、`bitand`、`bitor`、`compl`、`not`、`not_eq`、`or`、`or_eq`、`xor`、`xor_eq` 在 C++ 中是关键字（替代表示，见 [[lex.digraph]]），`<iso646.h>` 不把它们引入为宏。

**Clang 23 实测**：包含 `<iso646.h>` 之后 `#ifdef and` 为假；而试图自己 `#define and &&` 会得到 `C++ operator 'and' (aka '&&') used as a macro name` 错误。

### 宏 `NULL` {#diff.null}

¶1 `<clocale>`、`<cstddef>`、`<cstdio>`、`<cstdlib>`、`<cstring>`、`<ctime>`、`<cwchar>` 中定义的宏 `NULL`，在 C++ 中是一个**实现定义的空指针常量**（[[support.types]]）。C 中常见的定义 `((void*)0)` 在 C++ 中不可用，因为 `void*` 不能隐式转换为其他指针类型（见 [[diff.iso]] [expr] ¶1）。

```cpp error
#include <cstddef>
void f(int);
void f(char*);
void g() { f(NULL); }   // NULL 是整数还是 nullptr，由实现定义；这里可能歧义，也可能调用 f(int)
```

**Clang 23 实测**：Clang/libc++ 中 `NULL` 展开为 `__null`，类型是 `long`（LP64），`f(NULL)` 报 `call to 'f' is ambiguous`。这正是 C++11 引入 `nullptr` 的原因：在 C++ 中写空指针，应当用 `nullptr`。

## 对声明的修改 {#diff.mods.to.declarations}

¶1 `<cstring>` 中的 `strchr`、`strpbrk`、`strrchr`、`strstr`、`memchr` 声明不同：C 中它们接受 `const char*`、返回 `char*`（悄悄去掉了 `const`）；C++ 中每个函数提供一对重载，`const` 进 `const` 出，非 `const` 进非 `const` 出（[[cstring.syn]]）。

```cpp
#include <cstring>
const char* cs = "hello";
char* p = std::strchr(cs, 'l');        // C：合法（返回 char*）；C++：非良构
const char* q = std::strchr(cs, 'l');  // OK
char buf[] = "abc";
char* r = std::strchr(buf, 'b');       // OK：非 const 版本
```

**Clang 23 实测**：第 3 行在 C++ 中报 `cannot initialize a variable of type 'char *' with an rvalue of type 'const char *'`。

¶2 `<cwchar>` 中的 `wcschr`、`wcspbrk`、`wcsrchr`、`wcsstr`、`wmemchr` 同理（[[cwchar.syn]]）。

¶3 `<cstddef>` 除了 C 的 `<stddef.h>` 中的名字外，还声明 `nullptr_t`、`byte`、`to_integer`，以及 [[support.types.byteops]] 中针对 `std::byte` 的运算符和运算符模板。

## 对行为的修改 {#diff.mods.to.behavior}

### 概述 {#diff.mods.to.behavior.general}

¶1 `<cstdlib>` 中的 `atexit`、`exit`、`abort` 行为不同，见 [[support.start.term]]。主要差别：

- `exit` 先销毁当前线程的线程存储期对象，再按与构造相反的顺序销毁静态存储期对象并交错调用 `atexit` 注册的函数；**自动存储期对象不会被销毁**（不会进行栈展开）。注册的函数若以异常退出，调用 `std::terminate`。
- `abort` 和 `_Exit` 不执行任何析构函数，也不调用 `atexit` 注册的函数。
- `atexit` 不引入数据竞争；在 `exit` 调用之后才发生的 `atexit` 调用能否成功是未指定的。

¶2 `<csetjmp>` 中的 `longjmp` 行为受到更多限制（[[csetjmp.syn]]）：如果把一对 `setjmp`/`longjmp` 替换成 `catch`/`throw` 会调用任何自动存储期对象的**非平凡析构函数**，那么这对调用的行为是未定义的。在协程的挂起上下文中调用 `setjmp` 或 `longjmp` 也是 UB。

```cpp ub
#include <csetjmp>
#include <string>
std::jmp_buf env;
void g() { std::longjmp(env, 1); }
void f() {
  std::string s = "a long string that forces heap allocation";
  g();   // UB：longjmp 跳过了 s 的非平凡析构函数
}
int main() { if (setjmp(env) == 0) f(); }
```

### 宏 `offsetof` {#diff.offsetof}

¶1 `<cstddef>` 中的 `offsetof` 在 C++ 中只保证接受一部分 *type* 实参：对**标准布局类**以外的类型使用它是**有条件支持**的（[[support.types.layout]]）。此外，`offsetof` 永远不是类型依赖的，作用于静态数据成员或成员函数的结果未定义。

**Clang 23 实测**：对含虚函数的类使用 `offsetof`，Clang 支持它，但给出警告 `'offsetof' on non-standard-layout type 'B' [-Winvalid-offsetof]`。

### 内存分配函数 {#diff.malloc}

¶1 `aligned_alloc`、`calloc`、`malloc`、`realloc` 在 C++ 中受到限制（[[c.malloc]]）：

- 它们不通过 `::operator new` 分配存储（`free` 也不通过 `::operator delete` 释放），所以替换全局分配函数不会影响它们。
- 它们在返回的存储中**隐式创建对象**（[[g:implicitly-create-objects]]，见 [[intro.object]]），并返回指向合适的被创建对象的指针。这是 C++20 才补上的规则：在此之前，按照 C++ 的对象模型，`int* p = (int*)malloc(sizeof(int)); *p = 1;` 严格说来是 UB，因为没有任何操作创建了 `int` 对象。`calloc` 的对象在存储被清零**之前**创建；`realloc` 的对象在复制**之前**创建。
- `realloc` 的前置条件是 `free(ptr)` 有良定义的行为；用非空指针和 0 大小调用 `realloc` 是**错误行为**，效果由实现定义（见 [[diff.cpp23]] [mem] ¶1）。

## 小结

| 项目 | C | C++ |
|---|---|---|
| `<stdnoreturn.h>`、`<threads.h>` | 有 | 无 |
| `<complex.h>`、`<tgmath.h>` | C 复数与类型泛型宏 | 只包含 `<complex>` / `<cmath>` |
| `char16_t` 等 | typedef | 关键字、独立类型 |
| `<iso646.h>` 的 `and` 等 | 宏 | 关键字 |
| `NULL` | 常为 `((void*)0)` | 实现定义的空指针常量（不能是 `void*`） |
| `strchr` 等 | `const char*` → `char*` | `const` 重载对 |
| `exit` | 不知道析构函数 | 销毁静态和线程对象，不展开栈 |
| `longjmp` | 任意跳转 | 跳过非平凡析构函数即 UB |
| `offsetof` | 任意结构体 | 非标准布局类有条件支持 |
| `malloc` | 返回存储 | 返回存储并隐式创建对象 |
