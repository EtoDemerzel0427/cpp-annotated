---
title: 标准 iostream 对象与前置声明
summary: cin、cout、cerr、clog 及其宽字符版本何时构造、为什么永不析构、初始的 tie 和 unitbuf；与 stdio 同步的含义和 sync_with_stdio(false) 的代价；<iosfwd> 的前置声明与流类的继承关系。
status: done
covers: *, iostream.forward, iosfwd.syn, iostream.forward.overview
related: input.output, iostreams.base, iostreams.requirements, basic.start.dynamic, basic.start.main, basic.start.term, c.files, file.streams, syncstream
tags: 标准库, iostream, cout, 静态初始化, sync_with_stdio
updated: 2026-10-19
---

!!! tldr
    - 八个标准流对象在 `main` 开始之前构造，而且永不析构，所以静态对象的析构函数里也能使用 `cout`。
    - 包含 `<iostream>` 如同在这个翻译单元里定义了一个 `ios_base::Init` 对象，于是同一翻译单元里、定义在它之后的全局对象，构造时一定能使用 `cout`。
    - `cin` 和 `cerr` 都绑定（tie）到 `cout`，`cerr` 还设置了 `unitbuf`，所以提示语和错误信息都能按正确的顺序出现。
    - 标准流默认与 C 的 stdio 同步，可以和 `printf` 任意交错，多线程并发使用也不是数据竞争。`sync_with_stdio(false)` 放弃这两条保证，必须在任何输入输出之前调用。
    - `<iosfwd>` 只有声明，头文件里只需要写 `std::ostream&` 时包含它就够了。

## 全局对象的构造函数里能用 `cout` 吗

```cpp title="a.cpp" run ok
#include <iostream>        // 如同在这里定义了一个 std::ios_base::Init 对象

struct Logger {
  Logger() { std::cout << "Logger ready\n"; }   // OK
} g;

int main() {}
```

`cout` 定义在标准库的某个翻译单元里，`g` 定义在用户的翻译单元里。核心语言只保证同一个翻译单元内的全局变量按定义顺序初始化（[[basic.start.dynamic#3]]），不同翻译单元之间的动态初始化没有确定的先后。这就是**静态初始化顺序灾难**（[[g:static-initialization-order-fiasco]]）。照这个规则，`g` 构造时 `cout` 可能还不存在。

[iostream.objects.overview] 用两条规定解决这个问题。

¶3 标准流对象在第一次构造 `ios_base::Init` 类型的对象之前或期间构造，无论如何都在 `main` 函数体开始执行之前（[[basic.start.main]]）。它们在程序执行期间不会被析构。

¶5 在一个翻译单元里包含 `<iostream>`，效果如同 `<iostream>` 定义了一个静态存储期的 `ios_base::Init` 实例。

两条合起来：`#include <iostream>` 出现在 `g` 的定义之前，那个如同存在的 `Init` 对象和 `g` 同在一个翻译单元，先定义，所以先初始化（[[basic.start.dynamic#3.1.1]]）；`Init` 的构造保证 `cout` 已经构造好。

`ios_base::Init` 本身很简单（[[ios.init]]）：构造函数在八个对象尚未构造时构造它们；析构函数在没有其他 `Init` 对象存活时，刷新 `cout`、`cerr`、`clog` 和三个宽字符版本。

### 没有包含 `<iostream>` 的翻译单元

```cpp title="logger.cpp"
#include <iostream>
void log_line(const char* s) { std::cout << s << '\n'; }
```

```cpp title="early.cpp"
void log_line(const char*);

struct Early {
  Early() { log_line("too early?"); }   // 本 TU 没有 Init 对象：
} early;                                // 标准不保证此时 cout 已构造

int main() {}
```

`early.cpp` 没有包含 `<iostream>`，它的全局对象 `early` 和 `logger.cpp` 里的那个 `Init` 对象之间没有确定的初始化顺序。如果 `early` 先初始化，`log_line` 使用的就是一个尚未构造的 `cout`，行为未定义。

修复方法有两种：在 `early.cpp` 里也包含 `<iostream>`；或者在 `log_line` 里先构造一个局部的 `std::ios_base::Init` 对象，它的构造函数保证八个对象已经就绪。

!!! impl "实现怎么做"
    "如同定义了 `Init` 实例"规定的只是效果。本机 libc++ 的 `<iostream>` 里只有八个 `extern` 声明，没有任何 `Init` 对象。八个对象由库自己的实现文件构造，借助编译器的初始化优先级扩展，排在用户代码的动态初始化之前，这也满足了 ¶4 尽早初始化的建议。libstdc++ 早先的做法是在 `<iostream>` 里定义一个 `static ios_base::Init` 对象，每个包含它的翻译单元都多一次构造；较新的版本也改为在库内部初始化。

    所以上面的 `early.cpp` 在本机能正常打印。这是实现给的额外保证，标准本身不提供。

### 模块（¶5）

¶5 还规定，宿主实现中每个标准库模块（[[std.modules]]，如 `import std;`）的行为，如同含有一个接口单元，其中定义了一个不导出的、具有有序初始化的 `ios_base::Init` 变量。注 1 说明这样做的结果：这个变量的定义按 [[basic.start.dynamic#2]] 的意义出现在导入点之后的任何声明之前。所以 `import std;` 之后定义的全局对象，构造时同样可以使用 `cout`。

### 永不析构（¶3）

¶3 的最后一句保证了标准流对象不会被析构。脚注说明了目的：静态存储期对象的构造函数和析构函数都可以用它们读 `stdin`、写 `stdout`/`stderr`。

实现通常在静态存储里用 placement new 构造这些对象，然后永远不调用它们的析构函数。程序正常结束时，最后一个 `Init` 对象的析构函数会刷新它们；此后的静态对象析构时仍可以写 `cout`，`exit` 还会刷新所有打开的 C 流（[[basic.start.term]]）。同步状态下，写进 `cout` 的字符已经在 `stdout` 里，不会丢失。

## 八个对象及其初始状态 [iostream.syn]

```cpp
namespace std {
  extern istream cin;    extern wistream wcin;
  extern ostream cout;   extern wostream wcout;
  extern ostream cerr;   extern wostream wcerr;
  extern ostream clog;   extern wostream wclog;
}
```

`<iostream>` 还包含了 `<ios>`、`<streambuf>`、`<istream>`、`<ostream>`，所以包含它之后 `std::cout << 42` 一定可用。

| 对象 | 关联的 C 流 | 初始 `tie()` | 初始 `unitbuf` | 用途 |
|---|---|---|---|---|
| `cin` / `wcin` | `stdin` | `&cout` / `&wcout` | 否 | 标准输入 |
| `cout` / `wcout` | `stdout` | 空 | 否 | 标准输出 |
| `cerr` / `wcerr` | `stderr` | `&cout` / `&wcout` | 是 | 错误输出，每次输出后刷新 |
| `clog` / `wclog` | `stderr` | 空 | 否 | 日志输出，带缓冲 |

出处是 [narrow.stream.objects] 和 [wide.stream.objects] 的 ¶1–¶6。其余状态与 `basic_ios::init` 设定的相同：格式标志 `skipws | dec`、精度 6、填充字符为空格等，见 [[iostreams.base]]。

¶2 这些对象关联的流缓冲区，动态类型未指定，但行为如同 `basic_filebuf<char>` 或 `basic_filebuf<wchar_t>`。

```cpp run ok
#include <iostream>

int main() {
  std::cout << std::boolalpha
            << (std::cin.tie() == &std::cout) << ' '        // true
            << (std::cerr.tie() == &std::cout) << ' '       // true
            << (std::clog.tie() == nullptr) << ' '          // true
            << bool(std::cerr.flags() & std::ios_base::unitbuf) << ' '   // true
            << bool(std::clog.flags() & std::ios_base::unitbuf) << '\n'; // false
}
```

这几个初始值各有目的。

`cin` 绑定到 `cout`：每次从 `cin` 读取之前，输入的 sentry 先刷新 `cout`（[[istream.sentry#2]]）。所以 `cout << "name? "; cin >> name;` 中的提示一定在等待输入之前显示，这是 [[intro.abstract#8]] 对交互式设备"提示先于等待"的要求在库里的落实。

`cerr` 绑定到 `cout`，又设置了 `unitbuf`，两者解决不同的问题。`tie` 让 `cerr` 每次输出之前先刷新 `cout`，此前缓冲在 `cout` 里的正常输出先出现；`unitbuf` 让 `cerr` 每次输出操作结束时刷新自己，错误信息立刻出现。少了任何一个，终端上的先后顺序都可能不对。

`clog` 同样写 `stderr`，但带缓冲，适合大量日志。

`cin.tie(nullptr)` 关掉的是"读 `cin` 之前刷新 `cout`"，与下一节的 stdio 同步无关。交互程序关掉它，提示语可能不出现。

## 与 stdio 同步 [ios.members.static]

`sync_with_stdio` 声明为 `ios_base` 的静态成员（[[iostreams.base]]），但只对这八个对象有意义。

```cpp
static bool sync_with_stdio(bool sync = true);
```

¶3 标准流对象 `str` 与 C 流 `f` **同步**（[[g:synchronized-standard-stream]]），指对任意字符序列，下面三对操作的效果分别相同：`fputc(f, c)` 与 `str.rdbuf()->sputc(c)`，`fgetc(f)` 与 `str.rdbuf()->sbumpc()`，`ungetc(c, f)` 与 `str.rdbuf()->sputbackc(c)`。脚注说，这意味着两边的操作可以任意混用；实践中同步通常意味着标准流对象和 stdio 共享一个缓冲区。

¶1 调用之前如果已经在标准流上做过任何输入输出，效果由实现定义。否则，以 `false` 调用让标准流独立于 C 流运作。

¶2 返回调用之前是否处于同步状态。第一次调用返回 `true`，因为默认是同步的。

```cpp run impl
#include <cstdio>
#include <iostream>

int main() {
  std::ios_base::sync_with_stdio(false);   // 必须在任何输入输出之前
  std::cout << "1 cout\n";
  std::printf("2 printf\n");
  std::cout << "3 cout\n";                 // 三行的相对顺序不再有保证
}
```

为了与 `printf` 共享缓冲，同步状态下的标准流往往不能有自己的缓冲区，每个字符都要经过 `FILE*` 带锁的接口。关闭同步后，实现可以给 `cout` 配一个独立的缓冲区。这就是竞赛代码里常见的 `std::ios::sync_with_stdio(false); std::cin.tie(nullptr);` 能提速的原因。代价有三点：

1. `cout` 与 `printf` 的输出顺序不再有保证；
2. 失去 ¶7 的并发保证，多个线程并发使用 `cout` 成为数据竞争；
3. 必须在任何输入输出之前调用，否则效果由实现定义。

!!! impl "libc++ 上 `sync_with_stdio(false)` 看不出效果"
    在本机（Clang 23 + libc++）运行上例，输出到终端或管道，顺序都是 1、2、3；输出 300 万个整数，调用与不调用的耗时基本相同。libc++ 的标准流总是直接经由 `FILE*` 读写，`sync_with_stdio` 只记录并返回状态。libstdc++ 在关闭同步后会为标准流换用带独立缓冲的 streambuf，输出到管道时上例三行的顺序可能与代码顺序不同。可移植的代码不能依赖其中任何一种。

## 并发与宽窄混用（¶6–¶7）

¶7 对处于同步状态的标准流对象，多个线程并发调用它的格式化和非格式化输入输出函数，或者并发使用标准 C 流，不构成数据竞争（[[intro.multithread]]）。注 2 提醒，这样不加同步地并发使用，字符可能交错。线程安全的一般规则见 [[iostreams.requirements]]。

!!! pitfall "不是数据竞争，不等于不交错"
    `std::cout << "a" << i << '\n';` 是三次独立的输出调用，每两次之间别的线程都可以插进来。需要整行原子输出时，先拼成一个字符串再一次写出，或者用 `std::osyncstream(std::cout) << ...`（[[syncstream]]），或者用 `std::println(...)`，它写 `stdout` 时在持有 C 流锁的情况下一次写出整行（[[print.fun]]）。

¶6 对对应的宽、窄字符流混合操作（例如交替使用 `cout` 和 `wcout`，两者都写 `stdout`），语义与 C 中对同一个 `FILE` 混用宽窄操作相同。C 的规则是：一个 `FILE` 有定向（orientation），第一次宽字符操作或字节操作决定它，之后再对它做另一种操作，行为未定义（C23 7.23.2）。所以在同一个程序里交替用 `cout` 和 `wcout` 写 `stdout` 是不可移植的。

## `<iosfwd>` 与流类的继承关系 [iostream.forward]

### 前置声明 [iosfwd.syn]

`<iosfwd>` 声明了本章所有的流类模板、`istreambuf_iterator`/`ostreambuf_iterator`、`fpos`，以及全部 `char`/`wchar_t` 别名（`ostream`、`wifstream`、`spanbuf`、`osyncstream` 等）和 `streampos`、`wstreampos`、`u8streampos`、`u16streampos`、`u32streampos`。它不定义任何类，包含起来代价很小。头文件里只需要提到 `std::ostream&` 时，包含它而不是 `<ostream>`，可以减少编译依赖：

```cpp title="widget.h" ok
#include <iosfwd>

struct Widget { int id; };
std::ostream& operator<<(std::ostream& os, const Widget& w);   // 只需要声明
```

### 继承关系 [iostream.forward.overview]

```text
                    ios_base
                       │
              basic_ios<charT,traits>          ← 虚基类
             ╱(virtual)            ╲(virtual)
   basic_istream                  basic_ostream
   │  ╲                          ╱    │
   │   basic_iostream ──────────      │
   │      ├ basic_stringstream        ├ basic_ostringstream
   │      ├ basic_fstream             ├ basic_ofstream
   │      └ basic_spanstream          ├ basic_ospanstream
   ├ basic_istringstream              └ basic_osyncstream
   ├ basic_ifstream
   └ basic_ispanstream

   basic_streambuf<charT,traits>
      ├ basic_stringbuf   ├ basic_filebuf   ├ basic_syncbuf   └ basic_spanbuf
```

¶1 `basic_ios` 是 `basic_istream`、`basic_ostream` 及其派生类模板的虚基类；`basic_iostream` 同时派生自 `basic_istream` 和 `basic_ostream`。因为是虚基类，`basic_iostream` 里只有一份状态位和一个 `rdbuf()`。

虚基类由最终派生类负责初始化（[[class.base.init]]），而各个中间类也想设置它。所以 `basic_ios` 提供了一个受保护的默认构造函数，什么也不初始化，再由各个流类自己调用 `init()`（[[iostreams.base]]）。

¶2–¶5 列出了上图中各个流缓冲区和流的派生关系。`basic_osyncstream` 只派生自 `basic_ostream`，没有输入版本。

¶8 `fpos` 的特化表示文件位置：`streampos` 用于 `char` 流，`wstreampos` 用于 `wchar_t` 流。

## 思考题

!!! question "思考题 1"
    一个静态对象的析构函数通过另一个翻译单元里的函数写 `std::cout`，它自己所在的翻译单元没有包含 `<iostream>`。这样安全吗？

<details markdown="1">
<summary>答案</summary>

安全。[[iostream.objects.overview#3]] 规定标准流对象在程序执行期间不被析构，不存在 `cout` 先于这个静态对象析构的问题。构造时机也不成问题：静态对象析构发生在 `main` 返回之后，而 ¶3 保证八个对象在 `main` 开始之前就已经构造。
</details>

!!! question "思考题 2"
    `import std;` 之后，在全局对象的构造函数里使用 `std::cout`，有保证吗？

<details markdown="1">
<summary>答案</summary>

有。[[iostream.objects.overview#5]] 规定每个标准库模块的行为如同含有一个接口单元，定义了一个不导出、具有有序初始化的 `ios_base::Init` 变量。导入它的翻译单元对这个接口单元有接口依赖，所以该变量的定义按 [[basic.start.dynamic#2]] 出现在导入点之后的全局对象定义之前，初始化也就先于它们（[[basic.start.dynamic#3]]）。
</details>

## 小结

- 八个标准流在 `main` 之前构造，永不析构。包含 `<iostream>` 或 `import std;` 都如同定义了一个 `Init` 对象，保证之后定义的全局对象可以使用它们。
- `cin`、`cerr` 绑定到 `cout`；`cerr` 设置了 `unitbuf`；`clog` 写 `stderr`，带缓冲。
- 默认与 stdio 同步：可以与 `printf` 任意交错，并发使用不是数据竞争，但字符可能交错。
- `sync_with_stdio(false)` 必须在任何输入输出之前调用，以这两条保证换取速度。
- `<iosfwd>` 只声明不定义；`basic_ios` 是虚基类，`basic_iostream` 里只有一份流状态。

<details class="fine" markdown="1"><summary>其余条文</summary>

[iostream.objects.overview] ¶1：本章中的类型名 `FILE` 指 `<cstdio>` 里声明的 `FILE`。

¶4 *Recommended practice*：实现应当尽可能比要求的更早初始化这些对象。

¶5 注 1 的后半句：程序如果不引用任何标准流对象，就无法观察到那个 `Init` 变量的定义是否存在。

[iosfwd.syn] ¶1：默认模板实参（如 `traits = char_traits<charT>`）既出现在 `<iosfwd>` 里，也出现在各自头文件的概要里，同时包含两者必须是良构的。核心语言不允许在同一作用域里给同一个模板参数指定两次默认实参（[[temp.param]]），所以实现要用某种方式避开这条限制，比如只在一个内部头文件里写默认实参。用户不能模仿：在 `std` 里重新声明这些模板是未定义行为（[[namespace.std]]）。

[iostream.forward.overview] ¶6 注 1：对上述任何类模板，`traits::char_type` 与 `charT` 不是同一类型时程序非良构（规则本身在 [[char.traits]]）。¶7：其他别名表示 `char` 或 `wchar_t` 的特化。¶9 注 2：概要看起来有循环依赖，`streampos` 用到 `char_traits<char>::state_type`，而 `char_traits<char>::pos_type` 又是 `streampos`；实现可以用等价的类型替换来打破循环。

</details>
