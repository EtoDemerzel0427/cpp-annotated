---
title: 空终止序列工具
summary: <cstring> 的函数与 C 的 <string.h> 相同，C++ 只补充了四点：strtok 和 strerror 可能有数据竞争，memcpy 和 memmove 会隐式创建对象，strchr 等函数有 const 正确的重载。
status: done
covers: cstring.syn
papers: P0593R6
related: strings, char.traits, basic.string, string.view, library.c, intro.object, byte.strings, multibyte.strings, text.c.strings, res.on.data.races, support.signal, basic.lval
tags: 标准库, cstring, memcpy, strtok, C 兼容, 隐式对象创建
updated: 2026-10-19
---

!!! tldr
    - `<cstring>` 的内容和含义与 C23 的 `<string.h>` 相同，函数的前置条件和未定义行为都按 C 标准。
    - `memcpy` 的源和目标重叠是未定义行为，只有 `memmove` 允许重叠；指针实参即使长度为 0 也必须有效。
    - `strtok` 和 `strerror` 不保证没有数据竞争，`strtok` 还会修改输入、丢掉空字段。
    - C++20 起 `memcpy` 和 `memmove` 会在目标存储中隐式创建对象，并返回指向新对象的指针。
    - `strchr`、`strpbrk`、`strrchr`、`strstr`、`memchr` 各有一对重载：传入 `const char*` 就返回 `const char*`。

[c.strings] 只有一个子条款 [cstring.syn]：`<cstring>` 的概要，加上四段话。`<cctype>`、`<cwctype>`、`<cwchar>`、`<cuchar>` 在较早的标准中也放在这一节，现在都移到了第 28 章 [[text.c.strings]]，因为它们的行为依赖 locale 和编码。

## 与 C 相同 [cstring.syn]

```cpp run ub
#include <cstring>
#include <cstdio>

int main() {
  char buf[16] = "abcdefgh";
  std::memcpy(buf + 2, buf, 6);   // UB：源 [0,6) 与目标 [2,8) 重叠；ASan 报 memcpy-param-overlap
  std::puts(buf);
}
```

!!! std
    The contents and meaning of the header `<cstring>` are the same as the C standard library header `<string.h>`.

¶1 C++ 标准没有重复这些函数的规定，所以每个函数的前置条件和未定义行为都来自 C 标准。C 标准对 `<string.h>` 有一条总则：除非另有说明，传给这些函数的指针实参必须有效，即使长度为 0 也一样；访问超出数组末尾是未定义行为。由此得到最常见的几类 {{ub}}。

**重叠**。C 标准规定 `memcpy`、`strcpy`、`strcat`、`strncpy` 在重叠的对象之间复制时行为未定义，只有 `memmove` 允许重叠。`memcpy` 可以按任意顺序、任意宽度搬运数据（向量化、从尾部开始），重叠时结果取决于这些细节；`memmove` 要先判断方向，开销稍大。`char_traits` 的 `copy` 和 `move`（[[char.traits]]）沿用了这种分工。

**空指针加长度 0**。`memcpy(nullptr, nullptr, 0)` 在 C23 中仍是 {{ub}}，因为指针实参必须有效，与长度无关。之后的 C 标准草案放宽了这一点，但 C++ 当前引用的是 C23。编译器可以从 `memcpy(p, q, n)` 推断 `p`、`q` 不为空，删掉后面的空指针检查。默认构造的 `std::string_view` 的 `data()` 是空指针（[[string.view]]），把它和 `size()` 一起交给 `memcpy` 正好落进这个问题。

**没有结尾的空字符**。`strlen`、`strcpy`、`strcmp` 等要求实参是以空字符结尾的字节串（[[byte.strings]]），否则会越界读。两个常见的来源是 `string_view::data()`（[[string.view]]）和 `strncpy`：源串长度不小于 `n` 时，`strncpy` 不写空字符。它是为定长字段设计的，源串较短时还会用空字符填满剩余空间。

```cpp run ok
#include <cstring>
#include <cstdio>

int main() {
  char buf[4];
  std::strncpy(buf, "abcdef", sizeof buf);    // buf = {'a','b','c','d'}，没有 '\0'
  std::printf("%.*s\n", static_cast<int>(sizeof buf), buf);   // 必须显式给出长度
}
```

概要的第一行 `#define __STDC_VERSION_STRING_H__ 202311L` 是 C23 引入的头文件版本宏。随 C23 进入的新函数有：

- `memccpy(s1, s2, c, n)`：复制到遇到字符 `c`（包括它）或满 `n` 个字节为止，返回 `s1` 中 `c` 之后的位置，没遇到则返回空指针，适合连续拼接。
- `strdup`、`strndup`：返回用 `malloc` 分配的副本，要用 `free` 释放，而不是 `delete[]`。它们在独立实现中不提供。
- `memset_explicit`：语义同 `memset`，用于清除敏感数据，C 标准的意图是它不会因为写入后不再读取而被优化掉。

## strtok 与 strerror 的数据竞争

```cpp run ok
#include <cstring>
#include <cstdio>

int main() {
  char text[] = "a,b,,c";
  for (char* tok = std::strtok(text, ","); tok; tok = std::strtok(nullptr, ","))
    std::printf("[%s]", tok);                  // [a][b][c]：空字段消失
  std::printf("\n%zu\n", std::strlen(text));   // 1：text 被改成了 "a\0b\0,c"
}
```

!!! std
    The functions `strerror` and `strtok` are not required to avoid data races.

¶2 一般规则（[[res.on.data.races]]）要求标准库函数只通过实参访问对象，所以不同线程调用库函数时互不干扰。这两个函数是例外：

- `strtok` 用一个隐藏的静态指针记住上次切到哪里，之后传 `nullptr` 就从那里继续。两个线程即使切分各自的字符串，也会同时读写这个指针，构成数据竞争，即 {{ub}}（[[intro.multithread]]）。
- `strerror` 可以返回指向内部静态缓冲区的指针，下一次调用（在任何线程中）可能改写它的内容。

单线程中 `strtok` 也有两个问题，上面的例子都能看到：它修改输入，把分隔符改成空字符，所以不能用于字面量；它把连续的分隔符当作一个，空字段被丢掉。

替代方案：POSIX 的 `strtok_r` 和 C11 Annex K 的 `strtok_s` 让调用者保存状态，但都不在 C++ 标准中。C++ 中更自然的做法是用 `std::string_view` 的 `find` 和 `substr` 循环切分，或者用 `std::views::split`，它们不修改输入，也保留空字段。`strerror` 的线程安全替代是 `std::error_code(e, std::generic_category()).message()`（[[syserr]]）或 POSIX 的 `strerror_r`。

## memcpy 和 memmove 隐式创建对象

```cpp run ok
#include <cstring>
#include <cstdlib>
#include <cstdio>

struct Point { int x, y; };

int main() {
  Point src{1, 2};
  void* raw = std::malloc(sizeof(Point));
  Point* p = static_cast<Point*>(std::memcpy(raw, &src, sizeof src));
  std::printf("%d %d\n", p->x, p->y);   // OK：用 memcpy 返回的指针访问新对象
  std::free(raw);
}
```

!!! std
    Each of these functions implicitly creates objects in the destination region of storage immediately prior to copying the sequence of characters to the destination.

¶3 `memcpy` 和 `memmove` 在复制字符之前的一瞬间，在目标存储中**隐式创建对象**（[[g:implicitly-create-objects]]、[[intro.object]]），并返回指向一个合适的已创建对象的指针；没有这样的对象时返回第一个实参的值。这段规定由 C++20 的 [[P0593R6]] 加入。

在 C++17 的对象模型中，`malloc` 返回的存储里没有任何对象，`memcpy` 只是复制字节，`p->x` 访问的是一个不存在的对象，严格地说是未定义行为。[[P0593R6]] 让 `malloc`、`operator new` 等获取存储的操作和 `memcpy`、`memmove` 都隐式创建对象。后者在存储被复用时尤其重要：一块原来存放别的类型对象的缓冲区，`memcpy` 进一个 `Point`，那里就开始了一个 `Point` 的生命周期。

几点精确含义：

- 只创建隐式生存期类型（[[g:implicit-lifetime-type]]）的对象，而且只创建能让程序具有定义行为的那些。对有虚函数或非平凡构造函数的类型，`memcpy` 不会创建对象。能否用 `memcpy` 复制一个已有对象的值，由可平凡复制性决定（[[basic.types.general]]）。
- 返回值直接指向新对象，不必再经过 `std::launder`。上例用的就是返回值。
- 这两个函数是信号安全的（[[support.signal]]），可以在信号处理函数中调用。`memset`、`strlen` 等其他函数没有这个保证。

在 C++20 之前，`memcpy` 也是唯一可移植的类型双关方式，比如把 `float` 的字节复制到 `uint32_t`。现在可以用 `std::bit_cast`（[[bit]]）。

## const 正确的查找函数

C 的 `char* strchr(const char* s, int c);` 传入 `const char*`，返回 `char*`，借此可以写入只读内存。C++ 把 `strchr`、`strpbrk`、`strrchr`、`strstr`、`memchr` 各拆成一对重载：传入 const 指针就返回 const 指针，传入非 const 指针就返回非 const 指针（[[library.c]] 允许这种签名替换）。¶4 的注说明，签名不同，行为与 C 相同。

```cpp error
#include <cstring>
const char* s = "hello";
char* p = std::strchr(s, 'l');   // error: 不能用 const char* 初始化 char*
```

这行代码在 C 中能编译。从 C 移植来的代码在这里报错时，正确的改法是把 `p` 声明为 `const char*`，而不是加 `const_cast`。宽字符版本 `wcschr` 等在 `<cwchar>` 中也有同样的重载对（[[cwchar.syn#2]]）。

## 多字节转换与 mbstate_t

`<cwchar>` 和 `<cuchar>` 的转换函数不在本节，但它们处理的也是以空字符结尾的序列，并且与 [[char.traits]] 的 `state_type` 直接相关，这里简单说明，细节见 [[text.c.strings]]。

```cpp run ok
#include <cwchar>
#include <clocale>
#include <cstdio>

int main() {
  if (!std::setlocale(LC_ALL, "en_US.UTF-8")) return 1;
  const char* s = "\xE4\xB8\xAD";                      // U+4E2D 的 UTF-8 编码，3 字节
  std::mbstate_t st{};
  wchar_t wc = 0;
  std::size_t r1 = std::mbrtowc(&wc, s, 2, &st);       // 只给 2 字节：返回 (size_t)-2，表示不完整
  std::size_t r2 = std::mbrtowc(&wc, s + 2, 1, &st);   // 补上第 3 字节，接着上次的状态完成转换
  std::printf("%d %zu U+%04X\n", r1 == static_cast<std::size_t>(-2), r2, static_cast<unsigned>(wc));
}
```

本机输出 `1 1 U+4E2D`。在 UTF-8 这样的多字节编码中，一个字符可能由多个 `char` 组成，转换函数一次只看到一段输入，需要一个转换状态对象 `mbstate_t` 记住上一个字符读到了哪里。它就是 `char_traits<char>::state_type`。`mbstate_t` 零初始化（`{}`）时表示初始状态。

- 名字带 `r` 的可重入版本（`mbrtowc`、`mbrlen`、`wcrtomb`、`mbsrtowcs`、`wcsrtombs`，以及 `<cuchar>` 的 `mbrtoc8`、`c8rtomb` 等）由调用者传入 `mbstate_t*`。[[c.mb.wcs#6]] 规定，传入空指针时函数改用内部的静态状态，此时可能与同一函数的其他这类调用发生数据竞争。
- `mbtowc`、`wctomb`、`mblen` 总是使用内部状态，[[c.mb.wcs#4]] 规定它们可能与同一函数的其他调用发生数据竞争，与 `strtok` 是同一个问题。
- 这些函数的行为都取决于当前 C locale 的 `LC_CTYPE`。

## 思考题

!!! question "思考题 1"
    `std::memcpy(dst, sv.data(), sv.size())`，其中 `sv` 是默认构造的 `std::string_view`。有未定义行为吗？

<details markdown="1">
<summary>答案</summary>

按 C++ 当前引用的 C23，有。默认构造的视图的 `data()` 是空指针（[[string.view.cons#1]]），而 C 对 `<string.h>` 的总则要求指针实参有效，即使长度为 0。¶1 使这条规则直接适用于 `std::memcpy`。实际的风险是编译器据此推断 `sv.data()` 不为空，删掉后面的检查。稳妥的写法是 `if (!sv.empty()) std::memcpy(...)`，或者用 `sv.copy(dst, n)`，它对空视图什么也不做。
</details>

!!! question "思考题 2"
    ¶3 只说 `memcpy` 和 `memmove` 隐式创建对象。`malloc` 之后先用 `memset` 清零，再当作平凡结构体使用，合法吗？

<details markdown="1">
<summary>答案</summary>

合法，但对象不是 `memset` 创建的。`memset` 没有隐式创建对象的语义。这里的对象由 `malloc` 创建：[[intro.object]] 规定 `malloc`、`operator new`、开始 `unsigned char` 或 `std::byte` 数组的生命周期等操作会隐式创建对象，`memset` 之后只是给这个已经存在的平凡对象写入字节。

如果存储是复用的，里面已经有另一个类型的对象，`memset` 不会把它换成新类型。这时需要 placement new、`std::start_lifetime_as`（[[obj.lifetime]]），或者用 `memcpy` 从一个现成的该类型对象复制过去。
</details>

!!! question "思考题 3"
    两个线程各自对不同的局部缓冲区调用 `strtok`，会出问题吗？

<details markdown="1">
<summary>答案</summary>

会。`strtok` 记录上次位置的状态是函数内部的静态变量，与实参无关。两个线程都读写这同一个变量，构成数据竞争，即 {{ub}}。有些 C 库把这个状态放在线程局部存储里，于是碰巧安全，但标准不保证（¶2）。
</details>
