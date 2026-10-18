---
title: 文件流
summary: basic_filebuf 如何以 C 的 FILE 为模型读写文件——openmode 组合到 fopen 模式串的映射（表 146，ate 被去掉后再查表，所以 out|ate 会截断；不在表中的组合直接失败；C++23 的 noreplace 对应 "x"），close 的刷新与 unshift，codecvt 转换，seekoff/seekpos 的限制，setbuf(0,0) 无缓冲，读写切换必须定位，C++26 的 native_handle；ifstream/ofstream/fstream 的构造、open/close 与状态位
status: done
covers: *
related: stream.buffers, iostreams.base, input.streams, output.streams, c.files, fs.class.path, locale.codecvt, iostream.objects
tags: 标准库, iostream, fstream, filebuf, 文件
updated: 2026-10-18
---

`<fstream>` 把流接到文件上：`basic_filebuf` 是 streambuf，`basic_ifstream`/`basic_ofstream`/`basic_fstream` 是持有一个 `basic_filebuf` 成员的流。标准没有发明新的文件模型，而是**处处以 C 的 `FILE*` 为参照**：打开模式映射到 `fopen` 的模式串，定位映射到 `fseek`/`fsetpos`，刷新映射到 `fflush`，关闭映射到 `fclose`。所以 C 标准库关于文件的规则（文本/二进制模式、读写切换、文件定位）都适用于文件流。

## `<fstream>` 概要（[fstream.syn]）

声明四个类模板、各自的 `swap`，以及 `filebuf`/`ifstream`/`ofstream`/`fstream` 与 `w` 前缀别名。

- ¶1：定义四个类模板和八个类型，把流缓冲区与文件关联起来，辅助读写文件。
- ¶2（注）：`basic_filebuf` 把文件当作**字节**的来源或去处。在使用大字符集的环境中，文件通常保存多字节字符序列，`basic_filebuf` 把它们转换为宽字符序列。
- ¶3：本节中接受 `const filesystem::path::value_type*` 的成员函数，只在 `path::value_type` **不是** `char` 的系统上提供。注：这让宽字符原生路径的系统（如 Windows 上的 `wchar_t`）可以直接用宽字符串打开文件。

## 原生句柄（[file.native]）{{c++26}}

¶1：本节有几个类带有成员类型 `native_handle_type`。¶2：它表示指向文件的平台相关的**原生句柄**，是可平凡复制的、满足 `semiregular`。注：基于 POSIX 的系统上是 `int`（文件描述符），Windows 上是 `HANDLE`。

## `basic_filebuf`（[filebuf]）

### 概述（[filebuf.general]）

```cpp
template<class charT, class traits = char_traits<charT>>
class basic_filebuf : public basic_streambuf<charT, traits> {
public:
  using native_handle_type = implementation-defined;     // C++26
  basic_filebuf();
  basic_filebuf(basic_filebuf&& rhs);
  virtual ~basic_filebuf();
  basic_filebuf& operator=(basic_filebuf&& rhs);
  void swap(basic_filebuf& rhs);

  bool is_open() const;
  basic_filebuf* open(const char* s, ios_base::openmode mode);
  basic_filebuf* open(const filesystem::path::value_type* s, ios_base::openmode mode); // 仅宽路径系统
  basic_filebuf* open(const string& s, ios_base::openmode mode);
  basic_filebuf* open(const filesystem::path& s, ios_base::openmode mode);
  basic_filebuf* close();
  native_handle_type native_handle() const noexcept;     // C++26
protected:
  streamsize showmanyc() override;
  int_type underflow() override;   int_type uflow() override;
  int_type pbackfail(int_type c = traits::eof()) override;
  int_type overflow (int_type c = traits::eof()) override;
  basic_streambuf<charT, traits>* setbuf(char_type* s, streamsize n) override;
  pos_type seekoff(off_type off, ios_base::seekdir way, ios_base::openmode which = in | out) override;
  pos_type seekpos(pos_type sp, ios_base::openmode which = in | out) override;
  int sync() override;
  void imbue(const locale& loc) override;
};
```

- ¶1：`basic_filebuf` 把输入序列和输出序列**都**与一个文件关联。
- ¶2–¶3：读写的限制与 C 标准库的 `FILE` 相同。特别是：文件没有为读打开，输入序列不可读；没有为写打开，输出序列不可写；**输入序列和输出序列共享同一个文件位置**（与 stringbuf 的两个独立位置不同）。
- ¶4：只有 `traits::pos_type` 是 `fpos<traits::state_type>` 时才按描述工作，否则行为未定义 {{ub}}。
- ¶5–¶6 {{c++26}}：关联的文件有一个 `native_handle_type` 类型的原生句柄，可以通过 `native_handle()` 获得；`f.close()` 或 `f` 被销毁时，该句柄失效。
- ¶7：为支持文件 I/O 与多字节/宽字符转换，转换通过 locale 中的一个 facet 完成，下文称为 `a_codecvt`：`use_facet<codecvt<charT, char, typename traits::state_type>>(getloc())`。对 `char` 流，标准的 `codecvt<char, char, mbstate_t>` 是不做转换的"恒等"facet（[[locale.codecvt]]）。

### 构造、析构、赋值（[filebuf.cons]、[filebuf.assign]）

- 默认构造：¶1–¶2 后条件 `is_open() == false`。
- 移动构造：¶3 `*this` 与 `rhs` 在构造之后引用**各自独立**的缓冲区（如果有的话）；`*this` 引用 `rhs` 原来的文件，`rhs` 不再引用任何文件；打开模式、locale 等状态一并复制。指针是否沿用 `rhs` 的值由实现定义，但 ¶4 的后条件保证读写位置偏移相同、指针不共享，且 `rhs_a.is_open() == false`。
- 析构函数：¶5 调用 `close()`。析构（包括 `close()`）期间发生的异常被**捕获而不重新抛出**（[[res.on.exception.handling]]）。所以**析构时关闭失败会被静默忽略**——需要知道写入是否成功，必须显式 `close()` 并检查。
- 移动赋值：[filebuf.assign] ¶1 先 `close()`，再移动赋值；之后的可观察状态如同从 `rhs` 移动构造。

### `open`：打开模式到 `fopen` 的映射（[filebuf.members] ¶2–¶7）

`open(s, mode)`：¶2 前置条件 `s` 指向一个 NTCTS。¶3：若 `is_open()` 已为真，返回空指针（**不能对已打开的 filebuf 再次 `open`**）。否则按需初始化，然后打开 `s` 所指的文件，如同调用 `fopen`，第二个实参由 **`mode & ~ios_base::ate`** 按表 146 决定；若 `mode` 不是表中的某个组合，打开失败。

表 146（`+` 表示该位置位；每一行也可以再加 `binary`，对应模式串加 `b`，如 `"wb"`、`"r+b"`、`"w+bx"`）：

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

读这张表要注意：

1. **`ate` 不参与查表**。¶4：打开成功且 `mode` 含 `ate` 时，再如同 `fseek(file, 0, SEEK_END)` 定位到末尾；¶5：定位失败则 `close()` 并返回空指针。于是 `out | ate` 查表时就是 `out`，对应 `"w"`——**会截断文件**！想"打开已有文件、从末尾开始写、之后还能 `seekp` 回去改"，要用 `in | out | ate`（`"r+"` 再定位）。
2. **`out` 单独使用就会截断**（`"w"`），与 `out | trunc` 相同。要保留内容必须加 `app` 或 `in`。
3. **不在表中的组合直接失败**：`in | trunc`、`out | app | trunc`、`in | out | app | trunc`、单独的 `trunc`，以及 `noreplace` 与 `app` 或单独与 `in` 的组合等，打开都会返回空指针，流置 `failbit`。
4. **`app` 与 `ate` 不同**：`app` 对应 C 的 `"a"`，**每次写之前**都定位到末尾，`seekp` 无法让你在中间写；`ate` 只在打开时定位一次。
5. **`noreplace`** {{c++23}} 对应 C11 起的 `"x"`：文件已存在则打开失败——原子地"仅当不存在时创建"，避免先 `exists()` 再打开的竞争（[[filesystems]]）。

¶6：成功返回 `this`，否则空指针。¶7：`open(const string&, mode)` 和 `open(const filesystem::path&, mode)` 等价于 `open(s.c_str(), mode)`——对 `path` 而言 `c_str()` 返回原生格式、原生字符类型的字符串，在 Windows 上是 `const wchar_t*`，于是调用 ¶3 中"仅宽路径系统"的那个重载。

```cpp title="open-modes.cpp" ok
#include <fstream>
#include <iostream>
#include <string>

std::string slurp(const char* f) {
  std::ifstream in(f);
  return {std::istreambuf_iterator<char>(in), {}};
}

int main() {
  { std::ofstream("log.txt") << "line1\n"; }
  { std::ofstream out("log.txt", std::ios_base::ate); out << "line2\n"; }   // out|ate → "w"：先截断！
  std::cout << '[' << slurp("log.txt") << "]\n";                          // [line2\n]

  { std::ofstream out("log.txt", std::ios_base::app); out << "line3\n"; }   // "a"：追加
  { std::fstream f("log.txt", std::ios_base::in | std::ios_base::out | std::ios_base::ate);
    f << "line4\n"; }                                                       // "r+" 再定位到末尾
  std::cout << '[' << slurp("log.txt") << "]\n";                          // [line2\nline3\nline4\n]

  std::ifstream a("log.txt", std::ios_base::trunc);                         // in|trunc：表中没有
  std::ofstream b("log.txt", std::ios_base::app | std::ios_base::trunc);    // out|app|trunc：表中没有
  std::cout << a.is_open() << ' ' << b.is_open() << '\n';                   // 0 0

  std::ofstream c("log.txt", std::ios_base::out | std::ios_base::noreplace); // "wx"：已存在 → 失败
  std::cout << c.is_open() << '\n';                                         // 0
  std::remove("log.txt");
}
```

### `close`（¶8–¶10）

¶8：`is_open()` 为假时返回空指针。若存在 put 区，调用 `overflow(eof())` 刷新字符；若最后一次调用的虚函数（在 `underflow`、`overflow`、`seekoff`、`seekpos` 之中）是 `overflow`，则调用 `a_codecvt.unshift`（可能多次）求出**终止序列**、插入它并再次调用 `overflow(eof())`。最后，**无论前面的调用是否失败或抛出异常**，都关闭文件（如同 `fclose(file)`）。任何一个调用（包括 `fclose`）失败，`close` 返回空指针；若其中某个调用抛出异常，在关闭文件**之后**重新抛出。¶9 后条件 `is_open() == false`；¶10 成功返回 `this`。

"终止序列"（unshift sequence）用于状态相关编码：某些多字节编码在文件末尾需要写一个"回到初始移位状态"的序列，否则文件内容不完整。

### `native_handle`（¶11–¶12）{{c++26}}

前置条件 `is_open()` 为真；返回关联的原生句柄。它让你可以在不放弃 iostream 的前提下调用平台 API（`fstat`、`flock`、`fsync`、`posix_fadvise`……）：

```cpp title="native-handle.cpp" ok
#include <fstream>
#include <iostream>
#include <string>
#include <sys/stat.h>      // POSIX：fstat

int main() {
  { std::ofstream("demo.txt") << "hello\nworld\n"; }
  std::ifstream in("demo.txt", std::ios_base::binary);
  struct stat st;
  if (in.is_open() && fstat(in.native_handle(), &st) == 0) {   // C++26：拿到文件描述符
    std::string all{std::istreambuf_iterator<char>(in), {}};
    std::cout << "size=" << st.st_size << " read=" << all.size() << '\n';   // size=12 read=12
  }
  std::remove("demo.txt");
}
```

`native_handle()` 是 `noexcept` 的但有前置条件：对未打开的流调用是 {{ub}}。句柄的所有权仍属于 `filebuf`，不要对它调用 `close(2)`。

### 覆写的虚函数（[filebuf.virtuals]）

- **`showmanyc()`**：¶1 行为同基类（返回 0）；¶2 若实现能判断还有多少字符可读，可以提供覆写版本。
- **`underflow()`**：¶3 按 `basic_streambuf::underflow()` 的描述工作，特化在于：如同从文件读入一个外部缓冲区 `extern_buf`，再调用 `a_codecvt.in(state, extern_buf, ..., intern_buf, ...)` 转换到内部缓冲区。实现必须能**恢复每个内部字符对应的文件位置**（`fpos_t`）——这是 `tellg` 在宽字符流上仍然可用的前提；`in()` 报告内部缓冲区不够时用更大的缓冲区重试。
- **`uflow()`**：¶4 同理，用与 `underflow` 相同的方法读取。
- **`pbackfail(c)`**：¶5 三种方式（与 stringbuf 类似，但第 2 种是"若函数被允许向回退位置赋值"）；¶7 文件未打开时总是失败；¶8 **不直接把字符回退到输入序列**（不写文件）；¶9 多种方式可行时选哪种未指定，可用回退位置数可能在任何调用中改变。
- **`overflow(c)`**：¶10 按基类描述工作，但"消费字符"的方式是先用 `a_codecvt.out(state, pbase(), pptr(), ...)` 转换：`error` 则失败；`noconv` 则直接输出 `[pbase(), pptr())`；`partial` 则输出已转换部分并对剩余字符重复；否则输出转换结果（外部缓冲区不够时扩大重试）。**然后建立一个可观察检查点**（observable checkpoint，[[intro.abstract#5]]）{{c++26}}。¶11 成功返回 `not_eof(c)`，失败返回 `eof()`；文件未打开时总是失败。
- **`setbuf(s, n)`**：¶12 若在流上**进行任何 I/O 之前**调用 `setbuf(0, 0)`，流变为**无缓冲**——`pbase()` 和 `pptr()` 总是返回空，输出应尽快出现在文件中。其他情况的效果由实现定义 {{impl}}。
- **`seekoff(off, way, which)`**：¶13 设 `width = a_codecvt.encoding()`。若文件未打开，或 `off != 0 && width <= 0`（变长编码下只能做零偏移定位），定位失败。否则，若 `way != cur` 或 `off != 0`，且上一次操作是输出，就先更新输出序列并写出终止序列；然后定位：`width > 0` 时 `fseek(file, width * off, whence)`，否则 `fseek(file, 0, whence)`，`whence` 由表 147 从 `beg`/`cur`/`end` 映射到 `SEEK_SET`/`SEEK_CUR`/`SEEK_END`。¶14 返回新位置，失败返回 `pos_type(off_type(-1))`。¶15 解释"上一次操作是输出"指最后一个虚操作是 `overflow` 或 put 缓冲区非空。注意 `which` 在这里**被忽略**——输入和输出共享一个文件位置。
- **`seekpos(sp, which)`**：¶16 若打开模式含 `out`，先更新输出序列并写终止序列；如同 `fsetpos` 设置文件位置；若含 `in`，再更新输入序列。文件未打开时失败。¶17：`sp` 无效或两个序列都没被定位时失败；**若 `sp` 不是此前对同一文件的定位函数（`seekoff`/`seekpos`）成功返回的值，效果未定义** {{ub}}。
- **`sync()`**：¶19 若存在 put 区，调用 `overflow` 把字符写入文件，然后如同 `fflush(file)`；若存在 get 区，效果由实现定义 {{impl}}。
- **`imbue(loc)`**：¶20 前置条件：若文件不在开头，且当前 locale 的编码是状态相关的，则新 locale 的该 facet 必须与当前的相同；¶21 之后插入或提取的字符按 `loc` 转换；¶22 这可能需要重新转换已转换过的字符，进而要求实现能重建文件原始内容。实践中：**在打开文件之前 imbue**。

!!! pitfall "同一个 `fstream` 上读写切换必须先定位"
    由于 [[filebuf.general#2]] 规定读写限制与 C 的 `FILE` 相同，C 的规则适用：输出之后不经 `fflush` 或定位不能直接输入，输入之后不经定位（除非到了文件尾）不能直接输出（C 标准中 `fopen` 对更新模式的规定）。对 `fstream` 来说就是：写完要读，先 `seekg`；读完要写，先 `seekp`。

    ```cpp title="fstream-rw.cpp" ok
    #include <fstream>
    #include <iostream>
    #include <string>

    int main() {
      { std::ofstream("rw.txt") << "0123456789"; }
      std::fstream f("rw.txt", std::ios_base::in | std::ios_base::out);  // "r+"
      f << "AB";                     // 写到位置 0..1
      f.seekg(0);                    // 由写切换到读：先定位
      std::string s;
      f >> s;
      std::cout << s << '\n';        // AB23456789
      std::remove("rw.txt");
    }
    ```

## 三个流类（[ifstream]、[ofstream]、[fstream]）

三者结构相同：派生自 `basic_istream` / `basic_ostream` / `basic_iostream`，持有说明专用的 `basic_filebuf sb`，提供 `native_handle_type` 别名。

| 类 | 构造/`open` 时实际使用的模式 |
|---|---|
| `basic_ifstream` | `mode | in`（默认 `mode = in`） |
| `basic_ofstream` | `mode | out`（默认 `mode = out`） |
| `basic_fstream` | `mode`（默认 `in | out`） |

### 构造（以 [ifstream.cons] 为例）

- 默认构造：¶1 以 `addressof(sb)` 初始化基类，`sb` 默认构造（未打开）。
- `explicit basic_ifstream(const char* s, mode = in)`（及宽路径版本）：¶2 构造后调用 `rdbuf()->open(s, mode | in)`；**返回空指针时调用 `setstate(failbit)`**。构造函数不抛异常来报告打开失败——要检查 `is_open()` 或流状态。
- `basic_ifstream(const string& s, mode)`：¶3 等价于 `basic_ifstream(s.c_str(), mode)`。
- `template<class T> explicit basic_ifstream(const T& s, mode)`：¶4 *Constraints*：`is_same_v<T, filesystem::path>`；¶5 等价于 `basic_ifstream(s.c_str(), mode)`。注意它写成受约束的模板而不是 `const filesystem::path&`：模板参数推导不考虑隐式转换，所以这个构造函数只在实参类型**恰好是** `path` 时参与重载决议，不会因为某个类型可以隐式转换为 `path` 而被选中（`path` 可以从各种字符串类型隐式构造）。成员 `open` 则直接接受 `const filesystem::path&`。
- 移动构造：¶6 移动基类和 `sb`，再 `set_rdbuf(addressof(sb))`。

### 成员（[ifstream.members] 等）

- `rdbuf()`：返回 `const_cast<basic_filebuf*>(addressof(sb))`。
- `native_handle()` {{c++26}}：`return rdbuf()->native_handle();`。
- `is_open()`：`rdbuf()->is_open()`。
- `open(s, mode)`：¶4 调用 `rdbuf()->open(s, mode | in)`；**成功则调用 `clear()`**，失败调用 `setstate(failbit)`。"成功则 `clear()`"意味着：用同一个流对象先打开一个不存在的文件（失败、`failbit`），再成功打开另一个文件，状态会被重置——C++11 之前的标准不清除，旧代码里常见的 `f.clear(); f.open(...)` 就是为此。
- `close()`：¶6 调用 `rdbuf()->close()`，返回空指针时 `setstate(failbit)`。

```cpp title="open-failure.cpp" ok
#include <fstream>
#include <iostream>

int main() {
  std::ifstream missing("no-such-file.txt");
  std::cout << "is_open=" << missing.is_open() << " fail=" << missing.fail() << '\n';  // 0 1
  int x;
  missing >> x;                     // 流已失败：sentry 直接返回，什么都不读
  std::cout << "still fail=" << missing.fail() << '\n';                                // 1
}
```

标准没有规定失败原因如何报告：`errno` 往往被 `fopen` 设置，但标准不保证；需要可靠的错误信息时，可以先用 [[fs.op.funcs]] 中带 `error_code` 的函数检查，或打开 `exceptions(failbit)` 并检查 `ios_base::failure::code()`（实现**应当**给出具体原因，[[ios.failure#2]]）。

## 思考题

<details markdown="1">
<summary>1. <code>std::ofstream f("out.txt"); f &lt;&lt; data;</code> 之后磁盘满了，程序如何知道写入失败？</summary>

数据先进入 `filebuf` 的缓冲区，真正写文件发生在 `overflow`/`sync`/`close` 时。缓冲区满时的 `overflow` 失败会让插入器置 `badbit`；但最后一批数据要到析构时的 `close()` 才写出，而析构函数会**吞掉**失败（[[filebuf.cons#5]]）。所以应在离开作用域前显式 `f.close();` 并检查 `f.fail()`（或先 `f.flush()` 检查 `f.bad()`）。即便如此，`fclose` 成功也只代表数据交给了操作系统；要确保落盘，需要用 `native_handle()` 调用 `fsync` 之类的平台 API。
</details>

<details markdown="1">
<summary>2. 宽字符文件流 <code>std::wifstream</code> 上 <code>seekg(10, std::ios_base::beg)</code> 一定成功吗？</summary>

不一定。[[filebuf.virtuals#13]] 规定：`a_codecvt.encoding()` 返回值 `width <= 0`（变长或状态相关编码，例如 UTF-8 locale）时，**任何非零偏移**的 `seekoff` 都失败；只有 `seekoff(0, ...)` 和用 `tellg()` 得到的位置做 `seekpos` 才可靠。在默认的 "C" locale 下 `codecvt<wchar_t, char, mbstate_t>` 通常是每字符一字节（`width == 1`），此时可以成功，偏移按字节计算。
</details>

<details markdown="1">
<summary>3. 为什么 <code>basic_filebuf::seekoff</code> 不区分 <code>which</code> 中的 <code>in</code> 和 <code>out</code>？</summary>

因为 [[filebuf.general#3]] ¶3.3 规定输入序列和输出序列维护**同一个**文件位置——底层是一个 `FILE`（或文件描述符），只有一个读写指针。`seekg` 和 `seekp` 对文件流效果相同，这与 `basic_stringbuf` 两个序列各有独立位置不同。
</details>

## 小结

| 主题 | 要点 |
|---|---|
| 模型 | 以 C 的 `FILE` 为参照：`fopen`/`fseek`/`fsetpos`/`fflush`/`fclose`；读写共享一个位置 |
| 打开模式 | 去掉 `ate` 后查表 146；`out` 与 `out|ate` 都截断；不在表中的组合失败；`noreplace` = `"x"` |
| 失败报告 | 构造/`open` 失败只置 `failbit`；`open` 成功会 `clear()`；析构时 `close` 失败被吞掉 |
| 编码 | 经 `codecvt` 转换；变长编码下只能零偏移定位；`imbue` 应在打开前进行 |
| 缓冲 | I/O 前 `setbuf(0, 0)` 得到无缓冲；其他 `setbuf` 由实现定义 |
| C++26 | `native_handle()` 返回 POSIX `int` / Windows `HANDLE`；`overflow` 输出后建立可观察检查点 |
