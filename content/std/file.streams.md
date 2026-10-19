---
title: 文件流
summary: <fstream> 的 basic_filebuf 以 C 的 FILE 为模型读写文件：打开模式怎样对应到 fopen 的模式串，关闭、定位、刷新和编码转换的规则，以及 ifstream、ofstream、fstream 报告失败的方式。
status: done
covers: *
related: stream.buffers, iostreams.base, input.streams, output.streams, c.files, fs.class.path, locale.codecvt, iostream.objects
tags: 标准库, iostream, fstream, filebuf, 文件
updated: 2026-10-19
---

!!! tldr
    - 文件流的打开模式先去掉 `ate`，再查表对应到 `fopen` 的模式串；所以 `out` 和 `out | ate` 都会清空文件，表里没有的组合直接打开失败。
    - `app` 每次写之前都回到文件末尾；`ate` 只在打开时定位一次。C++23 的 `noreplace` 对应 `"x"`，文件已存在时打开失败。
    - 打开失败不抛异常，只置 `failbit`；析构时关闭失败会被静默忽略，关心写入结果就显式 `close()` 并检查。
    - 读和写共享同一个文件位置。在 `fstream` 上从写切换到读、从读切换到写之前，要先定位。
    - C++26 的 `native_handle()` 返回平台句柄（POSIX 上是文件描述符），可以直接调用系统 API。

```cpp title="open-modes.cpp" run ok
#include <cstdio>
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>

std::string slurp(const char* f) {
  std::ifstream in(f);
  return {std::istreambuf_iterator<char>(in), {}};
}

int main() {
  using std::ios_base;
  { std::ofstream("log.txt") << "line1\n"; }
  { std::ofstream out("log.txt", ios_base::ate); out << "line2\n"; }  // out|ate → "w"：先清空
  std::cout << slurp("log.txt");                                       // line2

  { std::ofstream out("log.txt", ios_base::app); out << "line3\n"; }  // "a"：追加
  std::cout << slurp("log.txt");                                       // line2、line3 两行
  std::remove("log.txt");
}
```

很多人以为 `ate` 表示从末尾续写，结果第二次打开就把 `line1` 清掉了。要理解为什么，需要知道文件流是怎样建在 C 的文件 I/O 之上的。

`<fstream>` 提供 `basic_filebuf` 和三个流类 `basic_ifstream`、`basic_ofstream`、`basic_fstream`，以及 `filebuf`、`ifstream` 等 `char` 别名和 `w` 前缀的 `wchar_t` 别名（[fstream.syn] ¶1）。`basic_filebuf` 是流缓冲区（见 [[stream.buffers]]），三个流类各持有一个 `basic_filebuf` 成员。

标准没有为文件流发明新的文件模型，而是处处参照 C 的 `FILE`（[[c.files]]）：打开如同 `fopen`，定位如同 `fseek`、`fsetpos`，刷新如同 `fflush`，关闭如同 `fclose`。所以 C 关于文本模式和二进制模式、读写切换、文件定位的规则，文件流也要遵守。

## `basic_filebuf` 的基本约定 [filebuf.general]

¶1 `basic_filebuf` 把输入序列和输出序列都关联到同一个文件。¶2 读写它的限制与 C 的 `FILE` 相同。¶3 具体来说：

- ¶3.1 文件没有为读打开时，输入序列不可读；
- ¶3.2 文件没有为写打开时，输出序列不可写；
- ¶3.3 输入序列和输出序列共享同一个文件位置。

最后一条与 [[string.streams]] 不同：`stringbuf` 的读位置和写位置相互独立，`filebuf` 底下只有一个文件，也只有一个读写位置。所以 `seekg` 和 `seekp` 对文件流效果相同。

¶4 只有 `traits::pos_type` 是 `fpos<traits::state_type>` 时，`basic_filebuf` 才按本节描述工作，否则行为未定义。使用标准的 `char_traits` 时总是满足。

¶7 为了在文件中的字节和流中的字符之间转换，`basic_filebuf` 使用当前 locale 中的 `codecvt<charT, char, state_type>` facet，下文称为 `a_codecvt`。对 `char` 流，标准的 `codecvt<char, char, mbstate_t>` 不做任何转换（[[locale.codecvt]]）。[fstream.syn] ¶2 的注也说明，`basic_filebuf` 把文件看作字节的来源或去处，宽字符流读写的文件里保存的是多字节字符序列。

## 打开 [filebuf.members] ¶2–¶7

¶3 `open(s, mode)` 如果发现文件已经打开，直接返回空指针，不能对已打开的 filebuf 再次 `open`。否则如同调用 `fopen` 打开 `s` 所指的文件，`fopen` 的第二个实参由 **`mode & ~ios_base::ate`** 查下表得到。`mode` 不是表中的某个组合时，打开失败。

| `in` | `out` | `trunc` | `app` | `noreplace` | `fopen` 模式 |
|:-:|:-:|:-:|:-:|:-:|:-:|
| | + | | | | `"w"` |
| | + | | | + | `"wx"` |
| | + | + | | | `"w"` |
| | + | + | | + | `"wx"` |
| | + | | + | | `"a"` |
| | | | + | | `"a"` |
| + | | | | | `"r"` |
| + | + | | | | `"r+"` |
| + | + | + | | | `"w+"` |
| + | + | + | | + | `"w+x"` |
| + | + | | + | | `"a+"` |
| + | | | + | | `"a+"` |

每一行还可以再加 `binary`，对应模式串里加 `b`，例如 `"wb"`、`"r+b"`、`"w+bx"`。

¶4 打开成功并且 `mode` 含 `ate` 时，再如同 `fseek(file, 0, SEEK_END)` 定位到末尾。¶5 这次定位失败的话，关闭文件并返回空指针。¶6 成功返回 `this`。

从这张表可以读出几条规则：

1. `ate` 不参与查表。`out | ate` 查的是 `out`，对应 `"w"`，会清空文件。要打开已有文件、从末尾开始写、之后还能 `seekp` 回去修改，用 `in | out | ate`，对应 `"r+"` 再定位到末尾。
2. 单独的 `out` 就会清空文件，与 `out | trunc` 相同。要保留原有内容，必须加 `app` 或 `in`。
3. `app` 对应 C 的 `"a"`，每次写之前都定位到末尾，`seekp` 无法让写入发生在中间。`ate` 只在打开时定位一次。
4. `noreplace` {{c++23}} 对应 C 的 `"x"`：文件已存在时打开失败。检查与创建是同一个原子操作，避免了先调用 `exists()` 再打开时其他进程插进来的竞争（[[filesystems]]）。
5. 表中没有的组合打开失败，例如 `in | trunc`、`out | app | trunc`、单独的 `trunc`、`noreplace` 与 `app` 的组合。

```cpp title="open-modes-2.cpp" run ok
#include <cstdio>
#include <fstream>
#include <iostream>

int main() {
  using std::ios_base;
  { std::ofstream("data.txt") << "old\n"; }

  std::ifstream a("data.txt", ios_base::trunc);              // in|trunc：表中没有
  std::ofstream b("data.txt", ios_base::app | ios_base::trunc);
  std::cout << a.is_open() << b.is_open() << '\n';           // 00

  std::ofstream c("data.txt", ios_base::out | ios_base::noreplace);
  std::cout << c.is_open() << '\n';                          // 0：文件已存在

  { std::fstream f("data.txt", ios_base::in | ios_base::out | ios_base::ate);
    f << "new\n"; }                                          // "r+" 再定位到末尾
  std::ifstream in("data.txt");
  std::cout << in.rdbuf();                                   // old、new 两行
  std::remove("data.txt");
}
```

¶7 `open(const string&, mode)` 和 `open(const filesystem::path&, mode)` 等价于 `open(s.c_str(), mode)`。对 `path` 来说，`c_str()` 返回原生格式、原生字符类型的字符串（[[fs.class.path]]），在 Windows 上是 `const wchar_t*`。[fstream.syn] ¶3 规定，接受 `const filesystem::path::value_type*` 的重载只在 `value_type` 不是 `char` 的系统上提供，这就是 Windows 上用宽字符路径打开文件的途径。

## 关闭 [filebuf.members] ¶8–¶10、[filebuf.cons] ¶5

¶8 `close()` 在文件未打开时返回空指针。否则按顺序做三件事：

1. 如果有 put 区，调用 `overflow(eof())` 把缓冲的字符写出去；
2. 如果最后一次调用的虚函数（`underflow`、`overflow`、`seekoff`、`seekpos` 之中）是 `overflow`，调用 `a_codecvt.unshift` 得到终止序列，写出它，再调用一次 `overflow(eof())`；
3. 不管前面是否失败或抛出异常，都如同 `fclose(file)` 关闭文件。

终止序列（unshift sequence）用于状态相关的编码：有些多字节编码要求在文件末尾写一段回到初始状态的序列，否则文件内容不完整。

任何一步（包括 `fclose`）失败，`close()` 都返回空指针；如果某一步抛出了异常，异常在关闭文件之后重新抛出。¶9–¶10 之后 `is_open()` 为假，成功时返回 `this`。

[filebuf.cons] ¶5 析构函数调用 `close()`。析构期间（包括 `close()` 中）发生的异常被捕获而不重新抛出，`close()` 返回的空指针也没有人检查。所以析构时写入或关闭失败会被静默忽略。关心写入是否成功，就在离开作用域之前显式调用 `close()`，再检查流的状态。

## 读写切换要先定位

```cpp title="fstream-rw.cpp" run ok
#include <cstdio>
#include <fstream>
#include <iostream>
#include <string>

int main() {
  { std::ofstream("rw.txt") << "0123456789"; }
  std::fstream f("rw.txt", std::ios_base::in | std::ios_base::out);  // "r+"
  f << "AB";                     // 写入位置 0、1
  f.seekg(0);                    // 由写切换到读：先定位
  std::string s;
  f >> s;
  std::cout << s << '\n';        // AB23456789
  std::remove("rw.txt");
}
```

[[filebuf.general#2]] 把 C 的规则带了进来。C 规定，以更新模式打开的文件，输出之后不经 `fflush` 或定位就不能直接输入，输入之后不经定位（读到文件末尾的情形除外）也不能直接输出。对 `fstream` 来说就是：写完要读，先 `seekg`；读完要写，先 `seekp`。

## 定位 [filebuf.virtuals] ¶13–¶18

¶13 `seekoff(off, way, which)` 先取 `width = a_codecvt.encoding()`，它是每个字符占的字节数；变长或状态相关的编码返回 0 或 −1。文件未打开，或者 `off != 0 && width <= 0`，定位失败。也就是说，变长编码下只能做偏移为 0 的定位。

否则，如果需要移动位置并且上一次操作是输出（¶15：最后一个虚操作是 `overflow`，或 put 区不空），先把输出写出去，再写出终止序列。然后如同调用 `fseek`：`width > 0` 时偏移为 `width * off`，否则为 0；`beg`、`cur`、`end` 分别对应 `SEEK_SET`、`SEEK_CUR`、`SEEK_END`。参数 `which` 不起作用，因为只有一个文件位置。

¶14 成功返回新位置，失败返回 `pos_type(off_type(-1))`。

¶16 `seekpos(sp, which)` 如同 `fsetpos` 把文件位置设为 `sp`；打开模式含 `out` 时先写出输出和终止序列，含 `in` 时之后更新输入序列。¶17 如果 `sp` 不是此前对同一文件调用 `seekoff` 或 `seekpos` 成功得到的值，效果未定义。`tellg()` 的结果来自 `seekoff(0, cur, in)`，所以保存 `tellg()` 再 `seekg(pos)` 是安全的用法。

## 缓冲与刷新 [filebuf.virtuals] ¶10–¶12、¶19

¶10 `overflow(c)` 写文件之前先用 `a_codecvt.out` 转换 put 区中的字符：转换出错则失败；不需要转换（`noconv`）则直接写出原字符；只转换了一部分（`partial`）则写出已转换的部分，对剩下的重复。写完之后，C++26 规定它建立一个可观察检查点（[[intro.abstract#5]]）{{c++26}}：之前的输出不会因为后面的未定义行为而被优化掉。¶11 成功返回 `not_eof(c)`；文件未打开时总是失败。

¶12 在流上进行任何 I/O 之前调用 `setbuf(0, 0)`，流变为无缓冲：`pbase()` 和 `pptr()` 总是返回空，输出应尽快出现在文件里。其他情况下 `setbuf` 的效果由实现定义 {{impl}}。

¶19 `sync()` 在有 put 区时调用 `overflow` 写出字符，再如同 `fflush(file)`；有 get 区时的效果由实现定义。`flush()` 和 `std::endl` 最终调用的就是它。

## 原生句柄 [file.native]、[filebuf.members] ¶11–¶12 {{c++26}}

[file.native] ¶2 `native_handle_type` 表示平台相关的原生文件句柄，可平凡复制，满足 `semiregular`。注里举例：POSIX 系统上是 `int`（文件描述符），Windows 上是 `HANDLE`。

¶11–¶12 `native_handle()` 的前置条件是文件已打开，返回关联的句柄。[filebuf.general] ¶6 规定，`close()` 或析构之后句柄失效。句柄仍然归 `filebuf` 所有，不要对它调用 `close(2)`。

```cpp title="native-handle.cpp" run ok
#include <cstdio>
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>
#include <sys/stat.h>      // POSIX：fstat

int main() {
  { std::ofstream("demo.txt") << "hello\nworld\n"; }
  std::ifstream in("demo.txt", std::ios_base::binary);
  struct stat st;
  if (in.is_open() && fstat(in.native_handle(), &st) == 0) {
    std::string all{std::istreambuf_iterator<char>(in), {}};
    std::cout << "size=" << st.st_size << " read=" << all.size() << '\n';  // size=12 read=12
  }
  std::remove("demo.txt");
}
```

有了句柄，就能在不放弃 iostream 的情况下使用 `fstat`、`flock`、`fsync` 这类平台 API。三个流类也各有 `native_handle()`，等价于 `rdbuf()->native_handle()`。

## 三个流类 [ifstream]、[ofstream]、[fstream]

三个类结构相同：分别派生自 `basic_istream`、`basic_ostream`、`basic_iostream`，持有一个说明专用的 `basic_filebuf sb`。构造和 `open` 时实际传给 `sb` 的模式如下：

| 类 | 默认 `mode` | 传给 `sb.open` 的模式 |
|---|---|---|
| `basic_ifstream` | `in` | `mode \| in` |
| `basic_ofstream` | `out` | `mode \| out` |
| `basic_fstream` | `in \| out` | `mode` |

下面以 `basic_ifstream` 为例，另外两个类的段落号相同。

### 构造 [ifstream.cons]

¶2 `basic_ifstream(const char* s, mode = in)` 构造之后调用 `rdbuf()->open(s, mode | in)`，返回空指针时调用 `setstate(failbit)`。构造函数不用异常报告打开失败，要自己检查 `is_open()` 或流的状态：

```cpp title="open-failure.cpp" run ok
#include <fstream>
#include <iostream>

int main() {
  std::ifstream missing("no-such-file.txt");
  std::cout << missing.is_open() << missing.fail() << '\n';  // 01
  int x = 0;
  missing >> x;                     // 流已失败，什么也不读
  std::cout << missing.fail() << x << '\n';                  // 10
}
```

¶3 接受 `const string&` 的版本等价于传 `s.c_str()`。¶4–¶5 接受 `filesystem::path` 的版本写成受约束的模板 `template<class T> explicit basic_ifstream(const T& s, mode)`，约束是 `is_same_v<T, filesystem::path>`。模板实参推导不考虑隐式转换，所以只有实参类型恰好是 `path` 时它才参与重载决议。`path` 能从各种字符串类型隐式构造，这样写保证传字符串时不会经由隐式转换选中它。成员 `open` 则直接接受 `const filesystem::path&`。

¶6 移动构造先移动基类和 `sb`，再调用 `set_rdbuf(addressof(sb))`。

### 成员 [ifstream.members]

- `rdbuf()` 返回 `const_cast` 之后的 `basic_filebuf*`；`is_open()` 返回 `rdbuf()->is_open()`。
- ¶4 `open(s, mode)` 调用 `rdbuf()->open(s, mode | in)`。成功时调用 `clear()`，失败时 `setstate(failbit)`。
- ¶6 `close()` 调用 `rdbuf()->close()`，返回空指针时 `setstate(failbit)`。

`open` 成功时会 `clear()`。用同一个流对象先打开一个不存在的文件（失败，置 `failbit`），再成功打开另一个文件，状态会被清除。C++11 之前的标准不清除状态，所以旧代码里常见 `f.clear(); f.open(...)` 的写法。

标准没有规定打开失败的原因怎样报告。`fopen` 通常会设置 `errno`，但标准不保证。需要可靠的错误信息时，可以先用 [[fs.op.funcs]] 中带 `error_code` 的函数检查，或者调用 `exceptions(failbit)` 让流抛出异常，再看 `ios_base::failure::code()`；按 [[ios.failure#2]]，实现应当在其中给出具体原因。

## 常见误解

!!! pitfall "`std::ios_base::ate` 等于追加"
    `ate` 只在打开时把位置移到末尾一次，而且 `out | ate` 会先清空文件。要追加用 `app`；要保留内容并能在任意位置改写，用 `in | out`（必要时加 `ate`）。

!!! pitfall "`flush()` 成功就说明数据已经写到磁盘上"
    `sync()` 只是如同 `fflush`，把数据交给操作系统。要确保落盘，需要用 `native_handle()` 调用 `fsync` 一类的平台 API。

## 思考题

!!! question "思考题 1"
    `std::ofstream f("out.txt"); f << data;` 之后磁盘满了，程序怎样才能知道写入失败？

<details markdown="1">
<summary>答案</summary>

数据先进入 `filebuf` 的缓冲区，真正写文件发生在 `overflow`、`sync` 或 `close` 时。缓冲区写满时 `overflow` 失败，插入器会置 `badbit`；但最后一批数据要到析构时的 `close()` 才写出，而析构函数不报告失败（[[filebuf.cons#5]]）。所以应在离开作用域之前显式调用 `f.close()` 并检查 `f.fail()`，或者先 `f.flush()` 再检查 `f.bad()`。
</details>

!!! question "思考题 2"
    在 UTF-8 locale 下，`std::wifstream` 上的 `seekg(10, std::ios_base::beg)` 能成功吗？

<details markdown="1">
<summary>答案</summary>

不能。UTF-8 是变长编码，`a_codecvt.encoding()` 返回 0，[[filebuf.virtuals#13]] 规定此时任何非零偏移的 `seekoff` 都失败。可靠的做法是用 `tellg()` 记下位置，之后 `seekg(pos)`。在默认的 "C" locale 下，`codecvt<wchar_t, char, mbstate_t>` 通常是每个字符一个字节（`width == 1`），这时可以成功，偏移按字节计算。
</details>

<details class="fine" markdown="1"><summary>其余条文</summary>

[file.native] ¶1：本节有几个类带有成员类型 `native_handle_type`。

[filebuf.general] ¶5：每个打开的文件都有一个 `native_handle_type` 类型的原生句柄，可以通过 `native_handle()` 获得。

[filebuf.cons] ¶1–¶2：默认构造之后 `is_open()` 为假。¶3–¶4：移动构造之后 `*this` 引用 `rhs` 原来的文件，`rhs` 不再引用任何文件；两者各有独立的缓冲区；指针是否沿用 `rhs` 的值由实现定义，但读写位置的偏移与移动前相同。

[filebuf.assign] ¶1：移动赋值先调用 `close()`，再从 `rhs` 移动赋值，结果如同从 `rhs` 移动构造。¶3–¶4：`swap` 交换两者的状态。

[filebuf.members] ¶1：`is_open()` 在最近一次 `open` 成功且之后没有调用 `close` 时返回真。

[filebuf.virtuals] ¶1–¶2：`showmanyc()` 的行为与基类相同；能判断还有多少字符可读的实现可以覆写它。¶3–¶4：`underflow()` 和 `uflow()` 如同先从文件读入字节，再用 `a_codecvt.in` 转换；实现必须能确定每个转换后的字符对应的文件位置。¶5–¶9：`pbackfail` 的三种方式与 [[string.streams]] 类似，但不直接把字符写回文件；文件未打开时总是失败。

[filebuf.virtuals] ¶20–¶22：`imbue(loc)` 的前置条件是，如果文件不在开头且当前编码是状态相关的，新 locale 的 `codecvt` facet 必须与当前的相同；之后插入和提取的字符按 `loc` 转换，这可能要求实现重新转换已经转换过的字符。实践中应在打开文件之前调用 `imbue`。

[ifstream.swap] 等：成员 `swap` 交换基类和 `sb`，非成员 `swap` 等价于 `x.swap(y)`。

</details>
