---
title: C 标准库的差异
summary: C++ 引入 C 标准库时做了哪些修改：少了哪些头文件，哪些类型和宏变成了关键字，NULL、strchr、longjmp、offsetof、malloc 在 C++ 中有什么不同。
status: done
covers: *
papers: P0593R6
related: diff, diff.iso, support.c.headers, library.c, c.strings, support.types, support.start.term, c.malloc
tags: 附录, 兼容性, C, 标准库
updated: 2026-10-19
---

!!! tldr
    - C++ 提供 C 的头文件，但没有 `<stdnoreturn.h>` 和 `<threads.h>`；`<complex.h>` 和 `<tgmath.h>` 只是包含 `<complex>`、`<cmath>`，没有 C 的复数类型和类型泛型宏。
    - `wchar_t`、`char8_t`、`char16_t`、`char32_t` 和 `and`、`or` 等替代记号在 C++ 中是关键字，不是 typedef 或宏。
    - `NULL` 是实现定义的空指针常量，不能是 `((void*)0)`；`strchr` 等函数有一对 `const` 重载，不会悄悄去掉 `const`。
    - `longjmp` 跳过非平凡析构函数是 UB；`offsetof` 只保证支持标准布局类；`malloc` 等函数在返回的存储中隐式创建对象。

C 标准库的大部分内容原样进入了 C++ 标准库，规格写成"与 C 标准库相同"。这一节汇总其中的显式修改，它和 [[diff.iso]] 是一对：后者讲语言，这里讲库。几乎每一处修改都出于同一个原因：C 库的一些写法与 C++ 更严格的类型系统和对象模型冲突，比如返回去掉 `const` 的指针、用 typedef 定义字符类型、用 `longjmp` 跳过一切清理。

## 头文件 {#diff.mods.to.headers}

¶1 为了与 C 标准库兼容，C++ 标准库提供 [[support.c.headers]] 中列出的 C 头文件，如 `<stdio.h>`。它们与 `<cstdio>` 这样的版本的区别在于名字声明在哪个命名空间：`<cxxx>` 保证在 `std` 中声明，`<xxx.h>` 保证在全局命名空间中声明，两者都可能同时在另一边提供（[[library.c]]）。

¶2 C 的 `<stdnoreturn.h>` 和 `<threads.h>` 没有对应的 C++ 头文件，它们本身也不是 C++ 的一部分。`<stdnoreturn.h>` 定义的 `noreturn` 宏会破坏 C++ 的属性 `[[noreturn]]`；`<threads.h>` 的功能由 `<thread>`、`<mutex>`、`<condition_variable>` 提供。

¶3 C 头文件 `<complex.h>` 和 `<tgmath.h>` 不包含 C 标准库中的任何内容，只是包含其他 C++ 头文件：前者相当于包含 `<complex>`，后者相当于包含 `<cmath>` 和 `<complex>`（[[support.c.headers]]）。C 的 `double _Complex`、宏 `I` 和类型泛型宏在 C++ 中都没有，C++ 用 `std::complex<double>` 和函数重载代替它们。

## 类型与宏 {#diff.mods.to.definitions}

### 字符类型是关键字 {#diff.char16}

¶1 `char8_t`、`char16_t`、`char32_t` 在 C++ 中是独立的类型，不是现有整数类型的 typedef，它们是关键字（[[lex.key]]），`<cuchar>` 不把它们定义为宏或类型名。C 的 `<uchar.h>` 中，`char16_t` 是 `uint_least16_t` 的 typedef，两者无法区分；C++ 可以按这几个类型重载函数、特化模板。

### `wchar_t` {#diff.wchar.t}

¶1 `wchar_t` 同样是独立的类型和关键字，`<cstddef>`、`<cstdlib>`、`<cwchar>` 都不把它定义为宏或类型名。

### `<iso646.h>` {#diff.header.iso646.h}

¶1 `and`、`and_eq`、`bitand`、`bitor`、`compl`、`not`、`not_eq`、`or`、`or_eq`、`xor`、`xor_eq` 在 C++ 中是关键字，即替代记号（[[lex.digraph]]），`<iso646.h>` 不把它们定义为宏。它们不是标识符，所以不能被定义为宏：Clang 对 `#define and &&` 甚至 `#ifdef and` 都报错 `C++ operator 'and' (aka '&&') used as a macro name`。

### 宏 `NULL` {#diff.null}

```cpp impl
#include <cstddef>
void f(int);
void f(char*);
void g() { f(NULL); }   // 本机 Clang：调用有歧义
```

¶1 `<clocale>`、`<cstddef>`、`<cstdio>`、`<cstdlib>`、`<cstring>`、`<ctime>`、`<cwchar>` 中的宏 `NULL`，在 C++ 中是一个实现定义的空指针常量（[[support.types]]）。C 中常见的定义 `((void*)0)` 在 C++ 中不行，因为 `void*` 不能隐式转换为其他指针类型（见 [[diff.iso]]）。

所以 `NULL` 在 C++ 中可能是 `0`、`0L` 或编译器内建的东西，`f(NULL)` 选哪个重载因实现而异。本机 Clang 的 `NULL` 展开为 `__null`，类型是 `long`，上面的调用有歧义。这正是 C++11 引入 `nullptr` 的原因。

## 函数声明 {#diff.mods.to.declarations}

```cpp error
#include <cstring>
const char* cs = "hello";
char* p = std::strchr(cs, 'l');        // error
const char* q = std::strchr(cs, 'l');  // OK
char buf[] = "abc";
char* r = std::strchr(buf, 'b');       // OK：非 const 版本
```

¶1 C 的 `strchr` 接受 `const char*`、返回 `char*`，悄悄去掉了 `const`。C++ 的 `<cstring>` 为 `strchr`、`strpbrk`、`strrchr`、`strstr`、`memchr` 各提供一对重载：传入 `const` 指针返回 `const` 指针，传入非 `const` 指针返回非 `const` 指针（[[cstring.syn]]）。上例第 3 行在 C 中合法，在 C++ 中报错。

¶2 `<cwchar>` 中的 `wcschr`、`wcspbrk`、`wcsrchr`、`wcsstr`、`wmemchr` 同理（[[cwchar.syn]]）。

¶3 `<cstddef>` 除了 C 的 `<stddef.h>` 中的名字，还声明了 `nullptr_t`、`byte`、`to_integer`，以及 [[support.types.byteops]] 中针对 `std::byte` 的运算符。

## 函数行为 {#diff.mods.to.behavior}

### 程序终止与 `longjmp` {#diff.mods.to.behavior.general}

¶1 `<cstdlib>` 中的 `atexit`、`exit`、`abort` 的行为与 C 不同，具体见 [[support.start.term]]。C 不知道析构函数，C++ 要规定它们与对象销毁的关系：

- `exit` 先销毁当前线程的线程存储期对象，再按与构造相反的顺序销毁静态存储期对象，其间交错调用 `atexit` 注册的函数。自动存储期对象不会被销毁，`exit` 不展开栈。
- `abort` 不执行任何析构函数，也不调用 `atexit` 注册的函数。
- `atexit` 不引入数据竞争；一次 `atexit` 调用如果不先发生于 `exit` 调用，它能否成功是未指定的。

```cpp run ub
#include <csetjmp>
#include <string>
std::jmp_buf env;
void g() { std::longjmp(env, 1); }
void f() {
  std::string s = "a long string that forces heap allocation";
  g();   // UB：longjmp 跳过了 s 的析构函数
}
int main() { if (setjmp(env) == 0) f(); }
```

¶2 `longjmp` 的行为受到更多限制（[[csetjmp.syn]]）。如果把一对 `setjmp`/`longjmp` 换成 `catch`/`throw` 会调用某个自动存储期对象的非平凡析构函数，这对调用的行为就是未定义的。在协程的挂起语境中调用 `setjmp` 或 `longjmp` 也是 UB。上例在本机用 `-fsanitize=address` 运行，LeakSanitizer 报告了 `s` 的堆内存泄漏：它的析构函数没有执行。

### `offsetof` {#diff.offsetof}

¶1 `<cstddef>` 中的 `offsetof` 在 C++ 中只保证接受一部分类型实参：用于标准布局类（[[g:standard-layout-class]]）以外的类型是有条件支持的（[[support.types.layout]]）。用于静态数据成员或成员函数时行为未定义。Clang 对含虚函数的类支持 `offsetof`，但给出警告 `'offsetof' on non-standard-layout type`。

### 内存分配函数 {#diff.malloc}

```cpp run ok
#include <cstdlib>
int main() {
  int* p = static_cast<int*>(std::malloc(sizeof(int)));
  if (!p) return 1;
  *p = 1;         // OK：malloc 隐式创建了 int 对象
  int r = *p;
  std::free(p);
  return r - 1;
}
```

¶1 `aligned_alloc`、`calloc`、`malloc`、`realloc` 在 C++ 中有几项额外规定（[[c.malloc]]）：

- 它们不通过 `::operator new` 分配存储，`free` 也不通过 `::operator delete` 释放，所以替换全局分配函数不影响它们。
- 它们在返回的存储中隐式创建对象（[[g:implicitly-create-objects]]，见 [[intro.object]]），并返回指向合适的被创建对象的指针。`calloc` 的对象在存储清零之前创建，`realloc` 的对象在复制内容之前创建。
- 用非空指针和大小 0 调用 `realloc` 是错误行为（erroneous behavior），效果由实现定义（见 [[diff.cpp23]]）。

在 C 中，`malloc` 返回的内存在写入时获得类型，上面的程序天然合法。C++ 中对象必须被创建出来才能访问，C++20 之前没有任何操作在这块存储里创建 `int`，严格说来 `*p = 1` 是 UB。C++20 引入的隐式对象创建（[[P0593R6]]）补上了这个漏洞。

## 小结

| 项目 | C | C++ |
|---|---|---|
| `<stdnoreturn.h>`、`<threads.h>` | 有 | 没有 |
| `<complex.h>`、`<tgmath.h>` | C 复数与类型泛型宏 | 只包含 `<complex>`、`<cmath>` |
| `char16_t` 等 | typedef | 关键字、独立的类型 |
| `<iso646.h>` 的 `and` 等 | 宏 | 关键字 |
| `NULL` | 常为 `((void*)0)` | 实现定义的空指针常量 |
| `strchr` 等 | `const char*` 进、`char*` 出 | `const` 重载对 |
| `exit` | 不涉及析构 | 销毁静态和线程对象，不展开栈 |
| `longjmp` | 可任意跳转 | 跳过非平凡析构函数即 UB |
| `offsetof` | 任意结构体 | 非标准布局类有条件支持 |
| `malloc` | 返回存储 | 返回存储并隐式创建对象 |

<details class="fine" markdown="1"><summary>其余条文</summary>

¶1 [diff.library.general] 说明这一节汇总 C 标准库与 C++ 标准库中取自 C 的部分之间，在头文件、定义、声明和行为上的显式差异。

</details>
