---
title: 空终止序列工具
summary: <cstring> 在 C++ 中的确切地位——"与 C 的 <string.h> 相同"的含义与例外；strtok/strerror 不保证无数据竞争；memcpy/memmove 是信号安全的并在目标存储中隐式创建对象；const 正确的 strchr 族重载；memcpy 重叠与空指针的 UB、strncpy 不终止等经典陷阱；以及 <cwchar>/<cuchar> 多字节转换中 mbstate_t 的角色
status: done
covers: cstring.syn
papers: P0593R6
related: strings, char.traits, basic.string, string.view, library.c, intro.object, byte.strings, multibyte.strings, text.c.strings, res.on.data.races, support.signal, basic.lval
tags: 标准库, cstring, memcpy, strtok, C 兼容, 隐式对象创建
updated: 2026-10-18
---

[c.strings] 只有一个子条款 [cstring.syn]：`<cstring>` 的概要外加四段话。概要里的函数原型几乎都是 C 的 `<string.h>` 照搬；那四段话则是 C++ 对它们的**全部**补充，每一段都有分量：

- ¶1：内容和含义与 C 标准库的 `<string.h>` 相同；
- ¶2：`strerror` 与 `strtok` 不要求避免数据竞争；
- ¶3：`memcpy` 与 `memmove` 是信号安全的，并且**在目标存储中隐式创建对象**；
- ¶4（注）：`strchr` 等五个函数的签名与 C 不同，但行为相同。

在旧版标准中，这一节还包含 `<cctype>`、`<cwctype>`、`<cwchar>`、`<cuchar>`，现在它们都搬到了第 28 章 [[text.c.strings]]，因为它们的语义依赖 locale 和编码。本页末尾简单交代多字节转换中 `mbstate_t` 的角色，细节以那一节为准。

## 概要（[cstring.syn]）

概要首行是 `#define __STDC_VERSION_STRING_H__ 202311L`——C23 引入的头文件版本宏，表明对应的 C 标准是 ISO/IEC 9899:2024（即 C23）。函数可以按用途分组：

| 组 | 函数 | freestanding |
|---|---|---|
| 内存块复制 | `memcpy`、`memmove`、`memccpy` | 是 |
| 串复制/拼接 | `strcpy`、`strncpy`、`strcat`、`strncat` | 是 |
| 串复制（分配） | `strdup`、`strndup` | **否**（要调用 `malloc`） |
| 比较 | `memcmp`、`strcmp`、`strncmp` | 是 |
| locale 相关比较 | `strcoll`、`strxfrm` | 否 |
| 查找 | `memchr`、`strchr`、`strrchr`、`strpbrk`、`strstr`、`strspn`、`strcspn` | 是 |
| 切分 | `strtok` | 否 |
| 填充 | `memset`、`memset_explicit` | 是 |
| 其他 | `strerror`（否）、`strlen`（是） | |

`memccpy`、`strdup`、`strndup`、`memset_explicit` 是随 C23 进入的新成员：

- `memset_explicit(s, c, n)`：语义同 `memset`，但目的是清除敏感数据，C 标准意图让它不被"写了之后再没读过"的死存储消除优化掉。
- `strdup`/`strndup`：返回 `malloc` 分配的副本，用 `free` 释放——**不是** `delete[]`。
- `memccpy(s1, s2, c, n)`：复制直到遇到字符 `c`（含）或复制满 `n` 个字节，返回 `s1` 中 `c` 之后的位置或空指针，适合高效地串联拼接。

## ¶1：与 C 相同意味着什么

!!! std
    The contents and meaning of the header `<cstring>` are the same as the C standard library header `<string.h>`.

所以**每个函数的前置条件和 UB 都来自 C 标准**，C++ 标准不再重复。C 标准对 `<string.h>` 有一条总则：除非另有说明，传给这些函数的指针实参即使在长度为 0 时也必须是有效值；超出数组末尾访问是 UB。由此得到这一页最常见的几类 {{ub}}：

**重叠的 `memcpy`、`strcpy`、`strcat`、`strncpy`**：C 标准规定"如果复制发生在重叠的对象之间，行为未定义"。只有 `memmove` 允许重叠。AddressSanitizer 能抓到 `memcpy` 的重叠：

```cpp run ub
#include <cstring>
#include <cstdio>

int main() {
  char buf[16] = "abcdefgh";
  std::memcpy(buf + 2, buf, 6);   // UB：源 [0,6) 与目标 [2,8) 重叠；ASan 报 memcpy-param-overlap
  std::puts(buf);
}
```

为什么 `memcpy` 不顺手处理重叠？因为它的实现可以按任意顺序、任意宽度搬运（向量化、从尾部开始、利用页对齐），重叠时结果取决于这些实现细节。`memmove` 必须先判断方向，开销略大。`char_traits::copy`/`char_traits::move`（[[char.traits]]）原样继承了这对分工。

**空指针 + 长度 0**：`memcpy(nullptr, nullptr, 0)` 在 C23 中仍是 {{ub}}（指针实参必须有效，与长度无关）；之后的 C 标准草案已放宽这一点，但 C++ 当前引用的是 C23。实践后果：编译器可以从 `memcpy(p, q, n)` 推断 `p`、`q` 非空，删掉后面的空指针检查。`std::string_view{}` 的 `data()` 是空指针（[[string.view]]），把它和 `size()` 一起交给 `memcpy` 正好落在这个坑里。

**缺少终止符**：`strlen`、`strcpy`、`strcmp` 等都要求实参是 ntbs（[[byte.strings]]），否则越界读。两个经典来源：

- `strncpy(dst, src, n)` 在 `strlen(src) >= n` 时**不写终止符**（它是为定长字段设计的，不足时还会用 `'\0'` 填满剩余空间）；
- `string_view::data()` 不保证终止（[[string.view]]）。

```cpp run ok
#include <cstring>
#include <cstdio>

int main() {
  char buf[4];
  std::strncpy(buf, "abcdef", sizeof buf);    // buf = {'a','b','c','d'}，没有 '\0'
  std::printf("%.*s\n", static_cast<int>(sizeof buf), buf);   // 必须显式给长度
}
```

## ¶2：`strtok` 与 `strerror` 的数据竞争

!!! std
    The functions `strerror` and `strtok` are not required to avoid data races.

C++ 的一般规则（[[res.on.data.races]]）要求标准库函数不得通过实参以外的途径访问对象，从而在多线程下互不干扰。这两个函数是明确的例外：

- `strtok` 用一个**隐藏的静态指针**记住上次切到哪里，第二次起传 `nullptr` 就是"接着上次"。两个线程同时切分各自的字符串，会互相篡改这个指针——数据竞争，{{ub}}。
- `strerror` 可以返回指向内部静态缓冲区的指针，下一次调用（任何线程）可能改写它。

即使在单线程中，`strtok` 也有两个陷阱：它**修改输入**（把分隔符改写为 `'\0'`，所以不能用于字面量），并且**合并连续的分隔符**、跳过空字段：

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

替代方案：POSIX 的 `strtok_r` 和 C11 Annex K 的 `strtok_s` 把状态交给调用者（都不在 C++ 标准里）；C++ 中更自然的是基于 `std::string_view` 的 `find` + `substr` 循环，或者 `std::views::split`——它们不修改输入，也保留空字段。

`strerror` 的线程安全替代是 `std::error_code{e, std::generic_category()}.message()`（[[syserr]]）或 POSIX 的 `strerror_r`。

## ¶3：`memcpy`/`memmove` 隐式创建对象

!!! std
    The functions `memcpy` and `memmove` are signal-safe. Each of these functions implicitly creates objects in the destination region of storage immediately prior to copying the sequence of characters to the destination. Each of these functions returns a pointer to a suitable created object, if any, otherwise the value of the first parameter.

    `memcpy` 与 `memmove` 是**信号安全**的；它们在复制字符序列**之前的瞬间**，在目标存储中**隐式创建对象**（[[g:implicitly-create-objects]]，[[intro.object]]），并返回指向一个合适的已创建对象的指针（若有），否则返回第一个参数的值。

这段话是 C++20 的 [[P0593R6]] 加入的，它让一个在 C 里天经地义、在 C++ 对象模型里却曾经是 UB 的写法合法化：

```cpp run ok
#include <cstring>
#include <cstdlib>
#include <cstdio>

struct Point { int x, y; };

int main() {
  Point src{1, 2};
  void* raw = std::malloc(sizeof(Point));
  Point* p = static_cast<Point*>(std::memcpy(raw, &src, sizeof src));
  std::printf("%d %d\n", p->x, p->y);   // OK：memcpy 在 raw 处隐式创建了 Point 对象
  std::free(raw);
}
```

在 C++17 的对象模型下，`malloc` 返回的存储里**没有任何对象**，`memcpy` 只是复制字节，`p->x` 访问一个不存在的对象，严格说是 {{ub}}。[[P0593R6]] 从两头修补了这件事：`malloc`/`operator new` 等获取存储的操作会隐式创建对象，`memcpy`/`memmove` 也会——后者在存储被**复用**时尤其关键（例如一块先前存放过其他类型对象的缓冲区，`memcpy` 进去一个 `Point`，就在那里开始了一个 `Point` 的生命周期）。被创建的是能使程序具有定义行为的那些隐式生存期类型（[[g:implicit-lifetime-type]]）的对象；`Point` 是平凡类型，所以它的生命周期在复制之前开始，复制把值放进去。

几点精确含义：

- **只对隐式生存期类型有效**。对含有虚函数或非平凡构造函数的类型，`memcpy` 不会创建对象；用它"复制"这种对象依然是 UB。可平凡复制性的规则（[[basic.types.general]]）决定了 `memcpy` 能否用来复制一个**已有**对象的值。
- **返回值很重要**。"returns a pointer to a suitable created object"意味着返回值直接指向新对象，可以不经 `std::launder` 使用；而 `raw` 本身在形式上只是"指向存储"的指针。上例用的是返回值。
- **信号安全**（[[support.signal]]）：可以在信号处理函数中调用这两个函数。`memset`、`strlen` 等其他函数没有这个保证（尽管实践中通常也是安全的）。

`memcpy` 也是 C++20 之前做**类型双关**的唯一可移植方式（把 `float` 的字节复制到 `uint32_t`），现在有了更直接的 `std::bit_cast`（[[bit]]）。

## ¶4：const 正确的查找函数

C 的 `char* strchr(const char* s, int c);` 是一个类型系统漏洞：传入 `const char*`，拿回 `char*`，就能写入只读内存。C++ 把五个函数（`strchr`、`strpbrk`、`strrchr`、`strstr`、`memchr`）各拆成一对重载：const 进 const 出，非 const 进非 const 出（[[library.c]] 规定了这种签名替换）。¶4 的注强调：签名不同，行为相同。

```cpp error
#include <cstring>
const char* s = "hello";
char* p = std::strchr(s, 'l');   // error: cannot initialize a variable of type 'char *' with an rvalue of type 'const char *'
```

在 C 里这行能编译；从 C 移植过来的代码在 C++ 中因此报错时，正确的修法是把 `p` 改为 `const char*`，而不是加 `const_cast`。

## 多字节字符与 `mbstate_t`（相关条款：[text.c.strings]）

`<cwchar>` 和 `<cuchar>` 不在本节，但它们处理的是同一类"空终止序列"，而且与 [[char.traits]] 的 `state_type` 直接相关，在这里一并交代要点：

- 多字节编码（如 UTF-8、Shift-JIS）中一个字符可能由多个 `char` 组成。转换函数一次只能看到一段输入，所以需要一个**转换状态**对象 `mbstate_t` 记住"上一个字符读了一半"。这正是 `char_traits<char>::state_type` 的类型（[[char.traits]]，[char.traits.specializations.char] ¶1）。
- **可重入**版本（名字带 `r` 的 `mbrtowc`、`mbrlen`、`wcrtomb`、`mbsrtowcs`、`wcsrtombs`，以及 `<cuchar>` 的 `mbrtoc8`/`mbrtoc16`/`mbrtoc32`/`c8rtomb`/`c16rtomb`/`c32rtomb`）由调用者传入 `mbstate_t*`。[c.mb.wcs] ¶6：若传入空指针，函数改用内部静态状态，此时与同一函数的其他"传空指针"的调用之间可能发生数据竞争。
- **不可重入**版本 `mbtowc`、`wctomb`（以及 `mblen`）总是使用内部状态，[c.mb.wcs] ¶4：与同一函数的其他调用之间可能发生数据竞争——与 `strtok` 是同一个问题。
- 所有这些函数的行为都取决于当前 C locale 的 `LC_CTYPE`。

```cpp run ok
#include <cwchar>
#include <clocale>
#include <cstdio>

int main() {
  if (!std::setlocale(LC_ALL, "en_US.UTF-8")) return 1;
  const char* s = "\xE4\xB8\xAD";                      // U+4E2D 的 UTF-8 编码，3 字节
  std::mbstate_t st{};
  wchar_t wc = 0;
  std::size_t r1 = std::mbrtowc(&wc, s, 2, &st);       // 只给 2 字节：返回 (size_t)-2，"不完整"
  std::size_t r2 = std::mbrtowc(&wc, s + 2, 1, &st);   // 补上第 3 字节：状态接续，完成转换
  std::printf("%d %zu U+%04X\n", r1 == static_cast<std::size_t>(-2), r2, static_cast<unsigned>(wc));
}
```

本机输出 `1 1 U+4E2D`：第一次调用把前两个字节的信息存进 `st`，第二次调用只用一个字节就完成了转换。`mbstate_t` 必须**零初始化**（`{}`）才代表初始状态。宽字符串版本的 `wcschr` 等函数在 `<cwchar>` 中同样有 const 正确的重载对（[cwchar.syn] ¶2）。

## 思考题

!!! question "1. `std::memcpy(dst, sv.data(), sv.size())`，其中 `sv` 是默认构造的 `std::string_view`。有 UB 吗？"

<details markdown="1">
<summary>展开查看答案与解析</summary>

按当前 C++ 引用的 C23：有。默认构造的 `string_view` 的 `data()` 是空指针（[string.view.cons] ¶1），而 C 对 `<string.h>` 的总则要求指针实参有效，即使长度为 0。¶1 让这条 C 规则直接适用于 `std::memcpy`。实际风险是编译器据此推断 `sv.data()` 非空并删掉后续检查。稳妥写法是 `if (!sv.empty()) std::memcpy(...)`，或者改用 `std::ranges::copy`/`sv.copy(dst, n)`——后者对空视图什么也不做。

</details>

!!! question "2. [cstring.syn] ¶3 只说 `memcpy` 与 `memmove` 隐式创建对象。`malloc` 之后先 `memset` 清零、再当作平凡结构体使用，合法吗？"

<details markdown="1">
<summary>展开查看答案与解析</summary>

合法，但功劳不在 `memset`。¶3 只点名了 `memcpy` 和 `memmove`，`memset` 没有隐式创建对象的语义。这里的对象是 `malloc` 创建的：[[intro.object]] 规定获取存储的若干操作（包括 `malloc`、`operator new`、`unsigned char`/`std::byte` 数组的生命周期开始）会隐式创建对象，`memset` 随后只是给这个已存在的平凡对象写入字节。如果存储是**复用**的、里面已经有另一个类型的对象，`memset` 不会替你换成新类型——这时需要 placement new、`std::start_lifetime_as`（[[obj.lifetime]]），或者用 `memcpy` 从一个现成的该类型对象复制过去。

</details>

!!! question "3. 两个线程各自对**不同的**本地缓冲区调用 `strtok`，会出问题吗？"

<details markdown="1">
<summary>展开查看答案与解析</summary>

会。¶2 说 `strtok` 不要求避免数据竞争，原因是它的"上次切到哪"的状态是**函数内部的静态变量**，与实参无关。两个线程的调用都会读写这同一个变量，构成数据竞争，即 {{ub}}（[[intro.multithread]]）。实践中，有些 C 库把这个状态放进线程局部存储从而"碰巧"安全，但标准不保证。

</details>

## 小结

| 主题 | 规则 |
|---|---|
| 来源 | 内容与语义同 C23 `<string.h>`（¶1）；前置条件与 UB 都按 C 标准 |
| 新成员 | C23 的 `memccpy`、`strdup`、`strndup`、`memset_explicit` |
| 数据竞争 | `strtok`、`strerror` 不保证（¶2）；`mbtowc` 等及传空 `mbstate_t*` 的转换函数同理 |
| `memcpy`/`memmove` | 信号安全；在目标中隐式创建对象并返回指向它的指针（¶3，C++20） |
| 重叠 | 只有 `memmove` 允许；`memcpy`/`strcpy`/`strcat`/`strncpy` 重叠是 UB |
| 空指针 | 即使长度为 0 也必须有效（C23） |
| `strncpy` | 源过长时不写终止符 |
| const 正确 | `strchr`/`strpbrk`/`strrchr`/`strstr`/`memchr` 拆为 const/非 const 重载对（¶4） |
| 多字节 | `mbstate_t` 携带跨调用的转换状态；必须零初始化；见 [[text.c.strings]] |
