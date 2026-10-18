---
title: 标准 iostream 对象与前置声明
summary: <iosfwd> 的前置声明与继承关系；cin/cout/cerr/clog 及宽字符版本何时构造、绑定到哪个 C 流、初始 tie 与 unitbuf；ios_base::Init 如何保证静态初始化期间可用 cout（与 [basic.start.dynamic] 的关系）、它们为何永不析构；与 stdio 同步的精确含义、sync_with_stdio(false) 的效果，以及标准流的并发保证
status: done
covers: *, iostream.forward, iosfwd.syn, iostream.forward.overview
related: input.output, iostreams.base, iostreams.requirements, basic.start.dynamic, basic.start.main, basic.start.term, c.files, file.streams, syncstream
tags: 标准库, iostream, cout, 静态初始化, sync_with_stdio
updated: 2026-10-18
---

本页合并两节：[iostream.forward]（`<iosfwd>`，只有声明）和 [iostream.objects]（`<iostream>`，八个标准流对象）。后者条文不长，却牵涉到核心语言里最微妙的话题之一——静态初始化顺序。

## `<iosfwd>`：前置声明（[iosfwd.syn]、[iostream.forward.overview]）

### 头文件内容

`<iosfwd>` 声明了本章**所有**流类模板（`basic_ios`、`basic_streambuf`、`basic_istream`/`ostream`/`iostream`、string/span/file/sync 四族流及其 buf）、`istreambuf_iterator`/`ostreambuf_iterator`、`fpos`，以及全部 `char`/`wchar_t` 的别名（`ostream`、`wifstream`、`spanbuf`、`osyncstream`……）和 `streampos`、`wstreampos`、`u8streampos`、`u16streampos`、`u32streampos`。它不定义任何东西，所以很轻；头文件里只需要**提到** `std::ostream&` 时，包含 `<iosfwd>` 而不是 `<ostream>`，可以显著减少编译依赖：

```cpp title="widget.h" ok
#include <iosfwd>

struct Widget { int id; };
std::ostream& operator<<(std::ostream& os, const Widget& w);   // 只需要声明
```

[iosfwd.syn] ¶1：默认模板实参（如 `traits = char_traits<charT>`）既出现在 `<iosfwd>` 里，又出现在各自头文件的概要里；同时包含两者必须是良构的。脚注说明这是**实现的责任**——核心语言规定同一个模板参数的默认实参在同一作用域里不能指定两次（[[temp.param]]），所以实现必须用某种技巧（比如只在一个内部头文件里写默认实参）避开这条限制。用户自己**不能**模仿：在 `std` 里重新声明这些模板本身就是 {{ub}}（[[namespace.std]]）。

### 继承关系（[iostream.forward.overview] ¶1–¶8）

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

- ¶1：`basic_ios` 是 `basic_istream`、`basic_ostream` 及其派生类模板的**虚基类**；`basic_iostream` 同时派生自 `basic_istream` 和 `basic_ostream`。正因为是虚基类，`basic_iostream` 只有一份状态位、一个 `rdbuf()`。这也意味着最终派生类负责初始化 `basic_ios`（[[class.base.init]]）——这就是为什么 `basic_ios` 有一个受保护的默认构造函数和 `init()`（[[iostreams.base]]）。
- ¶2–¶5：列出各 streambuf/流的派生关系（见上图）。注意 `basic_osyncstream` 只派生自 `basic_ostream`，没有输入版本。
- ¶6（注）：对上述任何类模板，若 `traits::char_type` 与 `charT` 不同，程序非良构（规则本身在 [[char.traits]]）。
- ¶8：`fpos` 的特化用于表示文件位置；`streampos` 用于 `char` 流，`wstreampos` 用于 `wchar_t` 流。
- ¶9（注）：概要看起来有循环——`streampos` 用到 `char_traits<char>::state_type`，而 `char_traits<char>::pos_type` 又是 `streampos`。实现可以用等价的类型代换来打破这个循环。

## `<iostream>` 的八个对象（[iostream.syn]）

```cpp
#include <ios>
#include <streambuf>
#include <istream>
#include <ostream>

namespace std {
  extern istream cin;    extern wistream wcin;
  extern ostream cout;   extern wostream wcout;
  extern ostream cerr;   extern wostream wcerr;
  extern ostream clog;   extern wostream wclog;
}
```

`<iostream>` 包含了使用这些对象所需的全部头文件，所以 `#include <iostream>` 之后 `std::cout << 42` 一定可用。

| 对象 | 关联的 C 流 | 初始 `tie()` | 初始 `unitbuf` | 用途 |
|---|---|---|---|---|
| `cin` / `wcin` | `stdin` | `&cout` / `&wcout` | 否 | 标准输入 |
| `cout` / `wcout` | `stdout` | 空 | 否 | 标准输出 |
| `cerr` / `wcerr` | `stderr` | `&cout` / `&wcout` | **是** | 错误输出，每次输出后刷新 |
| `clog` / `wclog` | `stderr` | 空 | 否 | 日志输出，带缓冲 |

（出处：[narrow.stream.objects] ¶1–¶6，[wide.stream.objects] ¶1–¶6。其余状态"与 `basic_ios::init` 要求的相同"：`flags() == skipws | dec`、`precision() == 6`、填充字符为空格等，见 [[iostreams.base]] 的表 142。）

```cpp title="std-objects-state.cpp" ok
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

这几个初始值都有明确目的：

- `cin.tie() == &cout`：每次从 `cin` 读之前，`istream::sentry` 会先刷新 `cout`（[[istream.sentry#2]]），于是 `cout << "name? "; cin >> name;` 中的提示一定在等待输入之前显示——这正是 [[intro.abstract#8]] 对交互设备"提示输出先于等待输入"的要求在库里的落实。
- `cerr.tie() == &cout` 加上 `unitbuf`：先刷新 `cout` 已缓冲的内容，再立即写出错误信息，所以错误信息与正常输出在终端上的相对顺序是对的。
- `clog` 同样写 `stderr` 但不带 `unitbuf`，适合大量日志。

## 构造时机：`ios_base::Init` 与静态初始化（[iostream.objects.overview]）

### 规定（¶2–¶5）

- ¶2：这些对象把流与 `<cstdio>` 的标准 C 流关联起来。它们初始关联的 streambuf 的**动态类型未指定**，但行为如同 `basic_filebuf<char>` / `basic_filebuf<wchar_t>`。
- ¶3：这些对象在**第一次构造 `ios_base::Init` 对象之前或期间**被构造、关联被建立，而且无论如何都在 `main` 函数体开始执行之前（[[basic.start.main]]）。**它们在程序执行期间不会被析构。** 脚注说明了目的：静态存储期对象的构造函数和析构函数都可以用它们读 `stdin`、写 `stdout`/`stderr`。
- ¶4 *Recommended practice*：实现应尽可能更早地初始化它们。
- ¶5：在一个翻译单元里包含 `<iostream>` 的效果，**如同** `<iostream>` 定义了一个静态存储期的 `ios_base::Init` 实例。在宿主实现中，每个标准库模块（[[std.modules]]，即 `import std;`）的行为如同含有一个接口单元，其中定义了一个不导出的、具有**有序初始化**（ordered initialization，[[basic.start.dynamic]]）的 `ios_base::Init` 变量。注：于是该变量的定义"出现顺序先于"（appearance-ordered before）导入点之后的任何声明。

`ios_base::Init` 本身（[[ios.init]]）：构造函数在八个对象尚未构造时构造它们；析构函数在没有其他 `Init` 实例存活时，刷新 `cout`、`cerr`、`clog`、`wcout`、`wcerr`、`wclog`。

### 为什么这样设计：与 [basic.start.dynamic] 的关系

核心语言只保证**同一个翻译单元内**、具有有序初始化的非局部变量按定义顺序初始化（[[basic.start.dynamic#3]]）；不同翻译单元之间的动态初始化是**不定序**的。这就是"静态初始化顺序灾难"（[[g:static-initialization-order-fiasco]]）。`cout` 定义在库的某个翻译单元里，用户 TU 里的全局对象构造时，`cout` 可能还没构造。

¶5 的"如同定义了一个 `Init` 实例"正是为此而设：

```cpp title="a.cpp" ok
#include <iostream>        // 如同在这里定义了：static std::ios_base::Init __init;

struct Logger {
  Logger() { std::cout << "Logger ready\n"; }   // OK：同一 TU 中 __init 先于 g 初始化
} g;

int main() {}
```

`#include <iostream>` 出现在 `g` 的定义之前，所以那个"如同存在"的 `Init` 对象与 `g` 同属一个 TU、都是有序初始化，前者的定义出现在前，初始化**按顺序先于**后者（[[basic.start.dynamic#3]] ¶3.1.1）；`Init` 的构造保证 `cout` 已经构造。

反过来，如果使用 `cout` 的 TU **没有**包含 `<iostream>`，保证就消失了：

```cpp title="logger.cpp"
#include <iostream>
void log_line(const char* s) { std::cout << s << '\n'; }
```

```cpp title="early.cpp"
void log_line(const char*);

struct Early {
  Early() { log_line("too early?"); }   // 此 TU 没有 Init 对象：
} early;                                // early 与 logger.cpp 中的 Init 不定序，
                                        // 若 cout 尚未构造，则使用它是 UB
int main() {}
```

修复方法：在 `early.cpp` 里包含 `<iostream>`（让本 TU 也有一个先于 `early` 的 `Init`），或者在 `log_line` 里显式构造一个 `std::ios_base::Init` 局部对象——它的构造函数保证八个对象已经就绪。

!!! impl "实现怎么做"
    "如同定义了 `Init` 实例"只是规定**效果**。本机 libc++ 的 `<iostream>` 头文件里只有八个 `extern` 声明，没有任何 `Init` 对象（可以直接打开头文件确认）；八个对象由库自身的实现文件构造，并借助编译器的初始化优先级扩展让它们先于用户代码的动态初始化运行，从而满足 ¶4 的"尽可能早"。历史上 libstdc++ 的做法是在 `<iostream>` 里定义一个 `static ios_base::Init` 对象，于是每个包含它的 TU 都多一次构造；较新的版本也改为在库内部初始化。所以上面 `early.cpp` 的例子在主流实现上实际能工作——但那是实现给的额外保证，标准本身不提供。

### 永不析构（¶3）

"The objects are not destroyed during program execution." 这句话让 `cout` 可以安全地在**静态对象的析构函数**里使用——即使那个静态对象在 `cout` 所在 TU 的所有对象析构之后才析构。实现通常用 placement new 在静态存储里构造它们，并且永远不调用析构函数。`~Init()` 只做刷新。程序正常结束时（[[basic.start.term]]），`exit` 还会刷新所有打开的 C 流，所以经由 `stdout` 的输出不会丢失。

## 与 stdio 的同步（[ios.members.static]）

`ios_base::sync_with_stdio` 的规定放在 [[iostreams.base]] 的 `ios_base` 一节里，但它只对本页的八个对象有意义，所以在这里讲。

```cpp
static bool sync_with_stdio(bool sync = true);
```

- ¶3 定义了"**同步**"（[[g:synchronized-standard-stream]]）：标准流对象 `str` 与 C 流 `f` 同步时，`fputc(f, c)` 与 `str.rdbuf()->sputc(c)`、`fgetc(f)` 与 `str.rdbuf()->sbumpc()`、`ungetc(c, f)` 与 `str.rdbuf()->sputbackc(c)` 对**任意**字符序列效果相同。脚注：这意味着两者的操作可以任意混用；"实践中，同步通常意味着标准流对象和 stdio 对象**共享一个缓冲区**"。
- ¶1：如果在调用之前标准流上已经发生过任何输入或输出，效果由实现定义 {{impl}}；否则以 `false` 调用会让标准流**独立于** C 流运作。
- ¶2：返回调用之前是否处于同步状态；第一次调用返回 `true`（默认是同步的）。

同步的代价是：为了与 `printf` 共享缓冲，标准流自己往往不能有独立的缓冲区，每个字符都要经过 `FILE*` 的加锁接口。关闭同步后，实现可以给 `cout` 配一个自己的缓冲区，这就是竞赛代码里常见的 `std::ios::sync_with_stdio(false); std::cin.tie(nullptr);` 能显著提速的原因。代价是：

1. `cout` 与 `printf` 的输出顺序不再有保证；
2. 失去 [[iostream.objects.overview#7]] 的并发保证——多个线程并发使用 `cout` 变成数据竞争；
3. 必须在**任何** I/O 之前调用，否则 {{impl}}。

```cpp title="unsync.cpp" impl
#include <cstdio>
#include <iostream>

int main() {
  std::ios_base::sync_with_stdio(false);   // 在任何 I/O 之前
  std::cout << "1 cout\n";
  std::printf("2 printf\n");
  std::cout << "3 cout\n";                 // 关闭同步后，三行的相对顺序不再有保证
}
```

!!! impl "libc++ 上 `sync_with_stdio(false)` 看不出效果"
    在本机（Clang 23 + libc++）上运行上例，无论输出到终端还是管道，顺序都是 1、2、3；写 300 万个整数的耗时在调用与不调用时也相同。libc++ 的标准流始终直接经由 C 的 `FILE*` 读写，`sync_with_stdio` 只记录并返回状态。libstdc++ 则会在关闭同步后为标准流换用带独立缓冲的 streambuf，输出到管道时上例三行的顺序就可能与代码顺序不同。可移植代码不能依赖任何一种。

`cin.tie(nullptr)` 是另一回事：它关掉的是"每次读 `cin` 前刷新 `cout`"，与 stdio 同步无关。交互程序关掉它会导致提示语不出现。

## 宽窄混用与并发（¶6、¶7）

- ¶6：对**对应的**宽、窄字符流混用（比如交替使用 `cout` 和 `wcout`，两者都写 `stdout`），语义与 C 中对同一个 `FILE` 混用宽窄操作相同。C 的规则是：流有一个"定向"（orientation），第一次宽字符操作或窄字符操作决定它，之后再做另一种操作是未定义行为（C 标准 7.23.2）。所以同一程序里交替用 `cout` 和 `wcout` 写同一个 `stdout` 不可移植。
- ¶7：对**同步状态**的标准流对象，多个线程并发调用其格式化、非格式化输入输出函数，或并发使用标准 C 流，**不构成数据竞争**（[[intro.multithread]]）；注：不同步地并发使用可能导致字符交错。线程安全的总体规则见 [[iostreams.requirements]]，不交错的输出见 [[syncstream]]。

!!! pitfall "“不是数据竞争” ≠ “不交错”"
    `std::cout << "a" << i << '\n';` 是三次独立的格式化输出调用，每次调用之间别的线程都可以插进来。即使每个 `<<` 本身是原子的，一行文字也可能被拆开。需要整行原子输出，就先拼成字符串再一次写出，或者用 `std::osyncstream(std::cout) << ...`，或者用 `std::println(...)`——写 `stdout` 的版本在持有 C 流锁的情况下一次写出整行（[[print.fun]]）。

## 思考题

<details markdown="1">
<summary>1. 一个静态对象的<b>析构函数</b>里写 <code>std::cout</code>，它所在的 TU 没有包含 &lt;iostream&gt;（通过别的 TU 的函数间接写）。这安全吗？</summary>

就"`cout` 是否还活着"而言是安全的：[[iostream.objects.overview#3]] 规定标准流对象在程序执行期间**不被析构**，所以不存在"`cout` 先于我析构"的问题。需要考虑的是构造时机——只要程序已经进入 `main`，¶3 保证它们已经构造。析构期间写出的字符可能留在缓冲区里，但正常终止时 `exit` 会刷新所有 C 流（[[basic.start.term]]）；同步状态下 `cout` 的字符就在 `stdout` 里。
</details>

<details markdown="1">
<summary>2. <code>import std;</code> 之后在全局对象构造函数里使用 <code>std::cout</code>，有保证吗？</summary>

有。[[iostream.objects.overview#5]] 规定每个标准库模块的行为如同含有一个定义了不导出 `ios_base::Init` 变量的接口单元，该变量具有有序初始化；导入它的 TU 对该接口单元有接口依赖，于是该变量的定义 appearance-ordered before 导入点之后的全局对象定义（[[basic.start.dynamic#2]]），初始化也就先于它们发生（¶3.1）。
</details>

<details markdown="1">
<summary>3. 为什么 <code>cerr</code> 要 tie 到 <code>cout</code>，而它自己又是 unitbuf？只要其中一个不行吗？</summary>

两者解决不同的问题。`unitbuf` 让 `cerr` 的每次输出操作结束时刷新**自己**（[[ostream.sentry]] 的析构函数），保证错误信息立刻出现；`tie(&cout)` 让 `cerr` 每次输出**之前**先刷新 `cout`，保证此前缓冲在 `cout` 里的正常输出先出现。只有前者，终端上可能先看到错误、后看到它之前打印的正常输出；只有后者，错误信息可能留在 `cerr` 自己的缓冲里。
</details>

## 小结

- `<iosfwd>` 只声明不定义，头文件里只需要 `std::ostream&` 时用它。
- `basic_ios` 是虚基类，`basic_iostream` 里只有一份流状态。
- 八个标准流在第一个 `ios_base::Init` 构造之前或期间、且在 `main` 之前构造，**永不析构**；包含 `<iostream>` 如同定义了一个 `Init` 对象，借助 [[basic.start.dynamic]] 的 TU 内有序初始化保证同一 TU 的全局对象可以使用 `cout`。
- `cin`、`cerr` 绑定到 `cout`；`cerr` 是 `unitbuf`；`clog` 写 `stderr` 但带缓冲。
- 默认与 stdio 同步：可以与 `printf` 任意交错、并发使用不是数据竞争；`sync_with_stdio(false)` 必须在任何 I/O 之前调用，换取速度、放弃这些保证。
