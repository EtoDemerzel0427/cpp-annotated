---
title: 程序的启动与终止
summary: main 函数的形式与限制；全局变量怎样初始化、按什么顺序初始化，静态初始化顺序问题及其对策；exit、atexit 与静态对象的析构顺序。
status: draft
covers: *
papers: P1143R2
related: basic.stc.static, basic.stc.thread, stmt.dcl, expr.const.init, dcl.init, support.start.term, class.dtor
tags: 初始化, 生命周期, 链接, UB
updated: 2026-10-19
---

!!! tldr
    - `main` 必须返回 `int`，不能递归调用、取地址或声明为 `inline`、`static`、`constexpr`；流出 `main` 的末尾等价于 `return 0;`，从 `main` 返回等价于先销毁局部对象再调用 `std::exit`。
    - 全局变量先做静态初始化（常量初始化或零初始化），再做动态初始化。静态初始化在任何代码运行之前就已完成，没有顺序问题。
    - 同一个翻译单元里的全局变量按定义顺序动态初始化；不同翻译单元之间顺序不定，这就是静态初始化顺序问题。对策是 `constinit`、函数局部静态变量和模块。
    - 静态对象按构造完成的逆序析构，`atexit` 注册的函数也排在同一个逆序里；常量析构的对象最后销毁。
    - 析构期间再经过一个已销毁的局部静态变量是 UB；`main` 返回后仍在运行的线程使用标准库也是 UB。

`main` 的第一条语句之前和返回之后，程序都在执行代码：构造和析构全局对象、初始化 `thread_local` 变量、调用 `atexit` 注册的函数。本节规定这些事情发生的时机和顺序。会用到的概念：**静态存储期**（static storage duration）的对象存在于整个程序运行期间，例如全局变量和 `static` 局部变量（[[basic.stc.static]]）；**线程存储期**（thread storage duration）的对象每个线程一份，即 `thread_local` 变量（[[basic.stc.thread]]）。

## main 函数 [basic.start.main]

### 合法的写法（¶1–¶2）

```cpp run title="main-ok.cpp" ok
auto main(int argc, char** argv) noexcept -> int {
  return argv[argc] == nullptr ? 0 : 1;   // argv[argc] 保证为空指针
}
```

¶1 程序必须恰好有一个属于全局作用域的 `main` 函数。执行程序就是启动一个主线程，在其中调用 `main`。独立实现（没有操作系统支持的实现，比如内核、固件）是否要求定义 `main` 由实现定义 {{impl}}。

¶2 `main` 声明的返回类型必须是 `int`，除此之外它的类型由实现定义。实现必须接受两种形式：`int()` 和 `int(int, char**)`，都可以带 `noexcept`。上面的尾置返回类型写法也可以，因为声明的返回类型仍然是 `int`；而 `auto main() { return 0; }` 是非良构的，Clang 报错 "'main' must return 'int'"。

在第二种形式中，`argc` 是从环境传入的实参个数，不会是负数。`argc` 不为零时，`argv[0]` 到 `argv[argc-1]` 指向以空字符结尾的字符串，`argv[0]` 是调用程序时用的名字或 `""`；`argv[argc]` 必须是空指针。标准建议把额外的参数加在 `argv` 之后，常见的 `int main(int, char**, char** envp)` 扩展就是这样做的。

### 对 main 的限制（¶3）

¶3 列出了一组禁令，违反任何一条都是非良构：

| 写法 | 为什么禁止 |
|---|---|
| 在表达式中使用 `main`（递归调用、取地址） | 实现可能在 `main` 开头插入启动代码，重入它没有意义 |
| 把 `main` 定义为 deleted，或声明为 `inline`、`static`、`constexpr`、`consteval` | `main` 必须是一个真正存在、能被环境调用的函数 |
| `main` 是协程 | 环境无法驱动协程的挂起和恢复 |
| `main` 带 `"C++"` 以外的链接规范 | |
| 全局作用域的变量 `main`、全局作用域的函数模板 `main` | 与入口符号冲突 |
| 全局作用域的函数 `main` 附着于具名模块 | 模块会改变它的链接和符号名 |
| 任何命名空间中具有 C 语言链接、名为 `main` 的实体 | 它的符号名就是 `main` |

`main` 的链接由实现定义 {{impl}}。除此之外 `main` 这个名字不保留，成员函数、类、其他命名空间的函数都可以叫 `main`：

<div class="compare" markdown="1">

```cpp run ok
namespace N { int main() { return 1; } }
struct S { void main() {} };
int main() { return N::main() - 1; }
```

```cpp run error
inline int main() {}
// error: main 不能是 inline
```

</div>

!!! impl "Clang 对其中两条只给警告"
    对 `int main() { return main(); }` 和 `extern "C" int main() {}`，本机 Clang 23 都只给出 `-Wmain` 警告，前者的说法是 "referring to 'main' within an expression is a Clang extension"。非良构只要求至少一条诊断，警告也算，所以 Clang 是符合标准的，只是诊断之后把程序当作扩展接受了（[[intro.compliance]]）。

### 从 main 返回与调用 exit（¶4–¶5）

```cpp run title="exit-vs-return.cpp" ok
#include <cstdio>
#include <cstdlib>
struct T { ~T() { std::puts("~T"); } };
int main(int argc, char**) {
  T t;
  if (argc > 5) std::exit(0);   // 不打印 "~T"
  return 0;                     // 先销毁 t，打印 "~T"，再调用 exit(0)
}
```

¶5 `main` 中的 `return` 语句先离开 `main`，也就是销毁局部对象，并且 {{c++26}} 求值 `main` 的后置条件断言（[[basic.contract]]），然后以返回值为实参调用 `std::exit`。控制流到达 `main` 的末尾等价于 `return 0;`，所以 `main` 是唯一一个流出末尾不是 UB 的非 void 函数（参见 [[stmt.return]]）。

¶4 用 `std::exit` 这类方式在不离开当前块的情况下终止程序，不会销毁任何自动存储期对象（普通局部变量），上例中 `exit(0)` 那条路径就不打印 `~T`。如果在静态或线程存储期对象的析构过程中调用 `std::exit`，行为未定义 {{ub}}，因为 `exit` 会重新进入正在进行的析构流程。

## 静态初始化 [basic.start.static]

### 零初始化与常量初始化（¶1–¶2）

```cpp run title="static-vs-dynamic.cpp" ok
#include <cstdlib>
int a = 42;                    // 常量初始化
int b;                         // 零初始化
constexpr double pi = 3.14159; // 常量初始化
struct P { int x, y; };
P p = { 1, 2 };                // 常量初始化
bool c = std::getenv("HOME");  // 动态初始化；在此之前 c 已被零初始化
int main() { return a - 42 + b + (p.x - 1) + (int(pi) - 3); }
```

¶1 静态存储期变量在程序启动时初始化，线程存储期变量在线程开始执行时初始化。

¶2 如果一个静态或线程存储期变量是**常量初始化的**（constant-initialized），粗略地说就是初始化器是常量表达式（准确条件见 [[expr.const.init]]），就对它做**常量初始化**；否则先对它做**零初始化**，把它的每个字节置为零值（[[dcl.init]]）。

!!! std
    Together, zero-initialization and constant initialization are called static initialization; all other initialization is dynamic initialization. All static initialization strongly happens before any dynamic initialization.

零初始化和常量初始化合称[[g:static-initialization|**静态初始化**]]（static initialization），其余的初始化都是**动态初始化**（dynamic initialization），也就是要在运行时执行代码的初始化。所有静态初始化都先于任何动态初始化完成。

实践中，静态初始化的值直接写在可执行文件的 `.data` 段（常量初始化）或 `.bss` 段（零初始化）里，由加载器映射进内存，不执行任何代码。所以静态初始化不存在顺序问题。上例的 `c` 在 `getenv` 被调用之前已经是 `false`。

### 实现可以把动态初始化提前（¶3）

¶3 即使标准不要求，实现也可以把一个动态初始化当作静态初始化来做，条件是这样做看不出区别：动态版本不会在其他静态对象初始化之前修改它们（¶3.1），静态版本算出的值与全部按动态方式初始化时相同（¶3.2）。这让编译器可以在编译期算出 `double d = 1.0 + 2.0;` 或调用内联函数的初始化器。

注 2 指出了一个后果：

```cpp run title="note2.cpp" unspecified
#include <cstdio>
inline double fd() { return 1.0; }
extern double d1;
double d2 = d1;     // 读到的是 1.0 还是 0.0？
double d1 = fd();
int main() { std::printf("%g %g\n", d1, d2); }
```

`d2` 的初始化读取了同一翻译单元中后定义的 `d1`。如果 `d1` 被提前做成静态初始化而 `d2` 是动态初始化，两者都是 1.0；其他情况下 `d2` 是 0.0（只看到了零初始化的 `d1`）。标准不规定是哪一种。本机 Clang 23 在 `-O0` 和 `-O2` 下都输出 `1 0`。

## 全局变量的动态初始化 [basic.start.dynamic]

### 三种初始化类别（¶1）

¶1 静态存储期的非块变量（命名空间作用域的变量和静态数据成员）的动态初始化分三类：

| 类别 | 适用于 | 原因 |
|---|---|---|
| **无序**（unordered） | 模板实例化出来的特化：类模板的静态数据成员、变量模板的特化 | 实例化可能出现在任意多个翻译单元里，谈不上定义位置 |
| **部分有序**（partially-ordered） | 不是实例化特化的 `inline` 变量 | 定义出现在多个翻译单元里，但每处都有确定的位置 |
| **有序**（ordered） | 其余所有：普通全局变量、普通静态数据成员 | 只有一个定义，位置确定 |

注 1 补充，模板化变量的非 inline 显式特化是有序的，因为它不是实例化出来的，只有一个定义。

```cpp run title="categories.cpp" ok
#include <cstdio>
struct Tr { Tr(const char* s) { std::puts(s); } };
inline Tr i1("inline i1");                     // 部分有序
Tr o1("ordered o1");                           // 有序
template<class T> struct H { static Tr t; };
template<class T> Tr H<T>::t("template member");  // 无序
template struct H<int>;
Tr o2("ordered o2");                           // 有序：一定在 o1 之后
int main() {}
```

`i1` 一定在 `o1` 之前，`o1` 一定在 `o2` 之前（规则见下一节），模板成员的位置则没有保证。本机 Clang 23 输出的顺序是 `i1`、模板成员、`o1`、`o2`：模板成员写在 `o1` 之后，却先于 `o1` 初始化。

### 初始化的先后（¶2–¶3）

¶2 如果声明 D 和 E 在同一翻译单元中且 D 在前，或者 E 所在的翻译单元导入了（直接或间接 `import`）D 所在的模块单元且导入点在 E 之前，就说 D **出现顺序先于**（appearance-ordered before）E。第二种情形是 C++20 模块带来的：导入的模块里定义的变量，视为出现在导入点之前。

¶3 对两个静态存储期的非块变量 V 和 W，有三种情况：

- ¶3.1 V、W 都有序且 V 的定义出现顺序先于 W 的定义；或者 V 部分有序、W 不是无序，并且 W 的每个定义前面都有 V 的某个定义。这时 V 先于 W 初始化。只有主线程，或者 V、W 都有序且在同一翻译单元时，这个先于是 sequenced before（同一线程内的先后）；否则是 strongly happens before（跨线程也成立的先后，见 [[intro.races]]）。
- ¶3.2 否则，如果程序在 V 或 W 初始化之前启动了其他线程，它们在哪个线程中初始化是未指定的；在同一线程中时两者无序。
- ¶3.3 否则，两者的初始化不定序（indeterminately sequenced）：一定一前一后，但不知道哪个在前。

注 2 说明，这个定义允许一串有序变量与另一串并发初始化。落到日常代码上，结论是三条：

- 同一翻译单元中的普通全局变量按定义顺序初始化。
- 不同翻译单元中的普通全局变量，没有模块导入关系时，初始化顺序不定。
- 模板的静态数据成员与任何变量之间都没有顺序保证。

### 静态初始化顺序问题

```cpp title="a.cpp"
#include <string>
std::string greeting = "hello, this is a long string beyond SSO";
```

```cpp title="b.cpp" ub
#include <cstdio>
#include <string>
extern std::string greeting;
std::size_t len = greeting.size();   // greeting 可能还没构造
int main() { std::printf("%zu\n", len); }
```

`greeting` 和 `len` 都是有序初始化，但定义在不同翻译单元，彼此没有出现顺序关系，所以按 ¶3.3 不定序。如果 b.cpp 的初始化先运行，`greeting.size()` 就是在一个生命周期还没开始、只做了零初始化的对象上调用成员函数，这是 UB（[[basic.life]]）。这个问题叫做**静态初始化顺序问题**（static initialization order fiasco，SIOF）。

本机 Clang 23 + libc++ 实测：`clang++ a.cpp b.cpp` 输出 39，`clang++ b.cpp a.cpp` 输出 0，初始化顺序跟随命令行上的文件顺序。

把字符串换成短的 `"hello"`，两种顺序都输出 5。libc++ 的 `std::string` 构造函数是 `constexpr` 的，短字符串放在对象内部（SSO，小字符串优化），不分配内存，整个初始化是常量表达式，于是 `greeting` 是常量初始化的，根本不参与动态初始化的排序。这引出了第一个对策。

#### 对策一：constinit

C++20 的 `constinit`（[[dcl.constinit]]，[[P1143R2]]）断言变量是常量初始化的，否则程序非良构。它不像 `constexpr` 那样隐含 `const`，变量仍然可以修改：

<div class="compare" markdown="1">

```cpp run ok
constinit int counter = 42;
constinit thread_local int tls = 0;
int main() { return counter - 42 + tls; }
```

```cpp run error
int f();
constinit int bad = f();
// error: 不是常量初始化
```

</div>

这样，这个变量没有 SIOF 就从一个约定变成了编译期检查。依赖 libc++ 恰好把短字符串做成常量初始化是靠不住的，换一个标准库或者字符串变长，结论就变了。

#### 对策二：函数局部静态变量

```cpp run title="meyers.cpp" ok
#include <string>
std::string& greeting() {
  static std::string s = "hello, this is a long string beyond SSO";
  return s;                          // 第一次调用时才初始化 s
}
std::size_t len = greeting().size(); // 不论哪个翻译单元先初始化都安全
int main() { return len == 0; }
```

块作用域的静态变量在控制流第一次经过它的声明时初始化（[[stmt.dcl#3]]）。C++11 起这个初始化是线程安全的：并发进入的线程会等待初始化完成。代价是每次访问都要检查一次是否已经初始化，而且析构时有对称的问题，见下文的 [[basic.start.term#5]]。这种写法常被称为 Meyers 单例。

#### 对策三：Schwarz 计数器

这是 iostreams 的传统做法，也叫 nifty counter。头文件里定义一个 `static` 的初始化器对象，每个包含该头文件的翻译单元各有一份。它的构造函数递增一个计数器，计数器从 0 变 1 时构造真正的全局对象；析构函数递减计数器，减到 0 时析构全局对象。

```cpp run title="nifty.cpp" ok
#include <cstdio>
#include <new>
// ---- stream.h ----
struct Stream {
  Stream() { std::puts("[Stream ctor]"); }
  ~Stream() { std::puts("[Stream dtor]"); }
  void write(const char* s) { std::fputs(s, stdout); }
};
Stream& stream();
static struct StreamInitializer {      // 每个翻译单元一份
  StreamInitializer();
  ~StreamInitializer();
} stream_initializer;
// ---- stream.cpp ----
static int nifty_counter;              // 零初始化，先于一切动态初始化
alignas(Stream) static unsigned char buf[sizeof(Stream)];
Stream& stream() { return *std::launder(reinterpret_cast<Stream*>(buf)); }
StreamInitializer::StreamInitializer() {
  if (nifty_counter++ == 0) ::new (buf) Stream();
}
StreamInitializer::~StreamInitializer() {
  if (--nifty_counter == 0) stream().~Stream();
}
// ---- user.cpp ----
struct User { User() { stream().write("using stream\n"); } } user;
int main() {}
```

它能工作靠两点。第一，每个包含 stream.h 的翻译单元里，初始化器对象的定义都在该翻译单元的使用者之前，按 ¶3.1 先初始化。第二，`nifty_counter` 是零初始化的，任何动态初始化开始之前它就是 0，所以无论哪个翻译单元的初始化器先运行，都能正确判断自己是不是第一个。

标准至今规定，包含 `<iostream>` 的效果如同定义了一个静态存储期的 `ios_base::Init` 对象，`std::cout` 等对象在 `main` 开始之前构造，并且在程序执行期间不被销毁（[[iostream.objects.overview]]）。实现可以用别的方式满足这些要求，比如在运行库内部指定初始化优先级。

#### 对策四：模块

C++20 起，如果 b.cpp `import` 了定义 `greeting` 的模块，按 ¶2.2，`greeting` 的定义出现顺序先于 `len`，于是按 ¶3.1 先初始化。

### 延迟初始化（¶4–¶7）

¶5 非块、非 inline 的静态存储期变量，动态初始化是在 `main` 的第一条语句之前完成还是延迟进行，由实现定义 {{impl}}。如果延迟，它必须先于同一翻译单元中任何非 inline 函数或变量的首次**非初始化 odr 使用**。

¶4 **odr 使用**（odr-use）粗略地说就是需要这个实体有定义的那种使用（[[basic.def.odr]]）。**非初始化 odr 使用**指不是由某个全局变量的初始化直接或间接引起的 odr 使用，也就是程序正常运行中的使用。

允许延迟主要是为了动态加载的库：`dlopen` 加载的共享库，其全局对象不可能在 `main` 之前构造。延迟的初始化在哪个线程、什么时候执行，由实现定义；标准建议实现选择能让程序员避免死锁的时机。脚注 32 补充，初始化有副作用的变量，即使本身没有被 odr 使用，也会被初始化。

¶6 inline 变量的规则类似，但延迟的初始化只需要先于对这个变量本身的非初始化 odr 使用。inline 变量可能定义在多个翻译单元里，同一翻译单元中的其他实体这个说法对它没有意义。

¶7 非块、非 inline 的线程存储期变量，动态初始化在线程的初始函数开始之前完成还是延迟，由实现定义。如果延迟，线程 t 中的初始化必须先于 t 对同一翻译单元中任何有动态初始化的非 inline `thread_local` 变量的首次非初始化 odr 使用。

!!! impl "主流实现怎么做"
    普通全局变量，GCC 和 Clang 都在 `main` 之前初始化（ELF 上通过 `.init_array`），不做延迟；共享库的全局对象在库加载时初始化。

    需要动态初始化的 `thread_local` 变量则是延迟的。Itanium C++ ABI 中，每次访问都经过一个 TLS 包装函数（符号名前缀 `_ZTW`），它检查本线程是否已经初始化，没有的话调用 TLS 初始化函数（前缀 `_ZTH`），一次性初始化本翻译单元中所有动态初始化的 `thread_local` 变量，正好对应 ¶7 以翻译单元为单位的粒度。用 `constinit` 声明的 `thread_local` 可以省掉这次检查。

<details class="fine" markdown="1"><summary>¶5 的标准例子</summary>

```cpp
// - File 1 -
#include "a.h"
#include "b.h"
B b;
A::A() { b.Use(); }

// - File 2 -
#include "a.h"
A a;

// - File 3 -
#include "a.h"
#include "b.h"
extern A a;
extern B b;
int main() { a.Use(); b.Use(); }
```

例子说：`a`、`b` 是在进入 `main` 之前初始化，还是推迟到 `a` 在 `main` 中首次被 odr 使用时，由实现定义。如果 `a` 在 `main` 之前初始化，不保证 `A::A` 调用 `b.Use()` 时 `b` 已经初始化，这就是 SIOF。如果 `a` 的初始化推迟到 `main` 开始之后，例子断言 `b` 会在 `A::A` 使用它之前初始化。

最后这个断言很难从规范性文字严格推出：`A::A` 对 `b` 的使用是 `a` 的初始化间接引起的，按 ¶4 属于初始化 odr 使用，不触发 ¶5 的保证。例子的意图大概是，延迟初始化的实现会以翻译单元为单位，在首次使用该翻译单元的实体之前完成它的全部初始化。由于主流实现不对普通全局变量做延迟初始化，这一点主要是理论上的。例子不具规范效力。

</details>

### 初始化抛出异常（¶8）

```cpp run title="init-throw.cpp" ok
#include <stdexcept>
int init() { throw std::runtime_error("boom"); }
int x = init();          // 异常逃出初始化：调用 std::terminate
int main() {}
```

¶8 非块的静态或线程存储期变量的初始化以异常退出时，调用 `std::terminate`（[[except.terminate]]）。这时 `main` 还没开始，没有任何 `try` 能包住它。这个行为是有定义的，所以例子标为 ok，本机运行时以 abort 结束。块作用域的静态变量不同：初始化抛出的异常正常传给调用者，下次经过声明时会重新尝试初始化（[[stmt.dcl#3]]）。

## 终止 [basic.start.term]

### 谁在什么时候销毁（¶1–¶3）

¶1 销毁已构造完成的静态存储期完整对象、调用 `atexit` 注册的函数，都是 `std::exit` 调用的一部分。从 `main` 返回会调用 `std::exit`（注 1）。

¶2 线程存储期对象在线程的初始函数返回、或者该线程调用 `std::exit` 时销毁。它们的析构先于任何静态存储期对象的析构，所以主线程的 `thread_local` 变量比全局变量先销毁。

¶3 有**常量析构**（constant destruction）的对象，也就是析构可以在常量求值中完成的对象（[[expr.const.defns]]），典型的是析构函数平凡的对象，排到最后销毁：线程存储期的排在本线程其他线程存储期对象之后，静态存储期的排在所有其他静态对象和所有 `atexit` 回调之后。本节其余的顺序规则只适用于没有常量析构的对象。

常量析构的对象析构时没有可观察的效果，把它们放到最后，其他对象的析构函数就可以放心使用它们，比如在析构函数里读一个全局的 `int` 或 `std::array<int, N>`。

### 析构顺序与构造相反（¶4）

¶4 如果静态存储期完整对象 X 的**视同构造**（deemed construction）先于 Y 的视同构造（strongly happens before），那么 Y 的析构完成之后才开始 X 的析构。视同构造指对象初始化完成的时刻；初始化是一个完整表达式时，就是这个完整表达式求值结束的时刻（[[dcl.init.general#21]]）。

线程存储期对象的规则相同，只是关系换成 sequenced before。静态初始化的对象按如同它是动态初始化的顺序析构。析构以异常退出时调用 `std::terminate`。

参照点选在初始化完成而不是开始，是有原因的。看标准的例 1：

```cpp run title="term-example.cpp" ok
#include <cstdio>
struct DTemp { ~DTemp() { std::puts("~DTemp"); } };
struct Temp {
  ~Temp() { static DTemp dt; }
};
struct BTemp {
  int i;
  BTemp(int i) : i(i) {}
  ~BTemp() { std::printf("~BTemp%d\n", i); }
};
struct A { const BTemp& tb; ~A() { std::printf("~A%d\n", tb.i); } };
A a[] = { (Temp(), BTemp(1)), BTemp(2) };
int main() {}
```

`a` 的整个声明是一个完整表达式。求值时依次创建临时对象 `Temp()`、`BTemp(1)`、`BTemp(2)`；两个 `BTemp` 绑定到引用成员，生命周期延长到与 `a` 相同。完整表达式结束时 `Temp()` 被销毁，它的析构函数构造了静态局部变量 `dt`。这之后，完整表达式求值完毕，`a` 才视同构造完成，所以 `dt` 早于 `a`。

于是终止时先销毁 `a` 的元素，再销毁 `dt`，最后是两个 `BTemp`。生命周期被延长的临时对象按构造完成的逆序销毁，并且比在它之后创建的同存储期对象更晚销毁（[[class.temporary#11]]）。本机 Clang 23 的输出是 `~A2`、`~A1`、`~DTemp`、`~BTemp2`、`~BTemp1`，与标准一致。

日常代码里最常用的推论是：函数局部静态对象在第一次调用时才构造完成，所以它比在它之前构造完成的全局对象更早析构。

### 使用已经销毁的局部静态变量（¶5）

```cpp run title="dead-reference.cpp" ub
#include <cstdio>
#include <string>
struct Logger {
  std::string prefix = "log: a fairly long prefix to force heap allocation";
  void log(const char* m) { std::printf("%s%s\n", prefix.c_str(), m); }
};
Logger& logger() { static Logger l; return l; }
struct Client {
  ~Client() { logger().log("client destroyed"); }   // UB：l 已经销毁
};
Client c;                              // main 之前构造完成
int main() { logger().log("main"); }   // l 在这里才构造完成，晚于 c
```

¶5 如果在静态或线程存储期对象的析构过程中调用了一个函数，控制流又经过了这个函数里一个已经销毁的静态（或线程存储期）局部变量的定义，行为未定义 {{ub}}。注 2 补充，通过指针等方式间接使用已销毁的局部变量同样是 UB。

上例中 `l` 的视同构造晚于 `c`，所以 `l` 先析构；之后 `c` 的析构函数调用 `logger()`，经过了 `l` 的定义。本机加 `-fsanitize=address` 运行，报告 heap-use-after-free。这是函数局部静态变量在析构阶段的顺序问题。常见对策有三种：

- 让单例永不析构：`static Logger& l = *new Logger;`，故意泄漏；
- 在 `Client` 的构造函数里先调用一次 `logger()`，让 `l` 先于 `c` 构造完成，从而后于 `c` 析构；
- 让被依赖的对象有常量析构（¶3），它会排到最后。

### atexit 与析构交错（¶6）

¶6 `atexit` 注册的函数和静态对象的析构排在同一个逆序里：

- 对象的视同构造先于某次 `atexit` 调用时，注册的函数在该对象开始析构之前调用；
- 某次 `atexit` 调用先于对象的视同构造时，对象析构完成之后才调用注册的函数；
- 两次 `atexit` 调用中，后注册的函数先调用。

可以把一次 `atexit` 注册看成构造了一个对象，然后所有东西统一按逆序拆除：

```cpp run title="term-order.cpp" ok
#include <cstdio>
#include <cstdlib>
struct T {
  const char* n;
  T(const char* s) : n(s) { std::printf("ctor %s\n", n); }
  ~T() { std::printf("dtor %s\n", n); }
};
T a("a");
void bye1() { std::puts("atexit 1"); }
void bye2() { std::puts("atexit 2"); }
int r1 = std::atexit(bye1);
T b("b");
int r2 = std::atexit(bye2);
T& local() { static T l("local"); return l; }
int main() {
  local();
  T autoobj("auto");
  std::exit(0);           // autoobj 不会析构（[basic.start.main]/4）
}
```

```text
ctor a
ctor b
ctor local
ctor auto
dtor local
atexit 2
dtor b
atexit 1
dtor a
```

构造和注册的顺序是 a、bye1、b、bye2、local，拆除顺序正好相反；`auto` 从未析构。

### 终止期间的其他线程（¶7）

¶7 如果程序使用了信号处理函数中不允许使用的标准库对象或函数（[[support.signal]]），而这次使用不先于（happens before）静态对象析构和 `atexit` 回调的完成，行为未定义 {{ub}}。信号处理函数里允许用的库设施很少，所以这条规则几乎覆盖所有库设施，包括 `std::cout`、`std::string` 和容器。

注 3 补充：使用一个静态存储期对象，而这次使用不先于它的析构，也是 UB。在调用 `std::exit` 或从 `main` 返回之前结束所有线程，就足以满足这些要求。

实际的后果是：`main` 返回时，如果还有 `detach` 出去的线程在运行，并且它在用任何标准库设施或全局对象，就是 UB，因为全局对象可能正在被拆除。

### abort 与 quick_exit（¶8）

¶8 `std::abort()` 终止程序，不执行任何析构函数，也不调用 `atexit` 或 `at_quick_exit` 注册的函数。结合 [[support.start.term]]，几种结束程序的方式对比如下：

| 方式 | 自动对象 | 线程存储期对象 | 静态对象 | atexit 回调 | at_quick_exit 回调 |
|---|---|---|---|---|---|
| 从 `main` 返回 | 析构 | 析构 | 析构 | 调用 | 不调用 |
| `std::exit` | 不析构 | 析构（当前线程） | 析构 | 调用 | 不调用 |
| `std::quick_exit` | 不析构 | 不析构 | 不析构 | 不调用 | 逆序调用 |
| `std::_Exit`、`std::abort` | 不析构 | 不析构 | 不析构 | 不调用 | 不调用 |

`quick_exit` 适合这样的场景：后台线程还在运行，执行完整的静态析构很危险（¶7），于是只运行显式注册的少量清理函数，然后调用 `_Exit` 结束进程。`std::terminate` 默认调用 `abort`。

## 实现视角

!!! impl "启动和终止代码"
    - ELF（Linux）上，编译器把每个翻译单元的动态初始化收集到一个函数里（GCC 命名为 `_GLOBAL__sub_I_<文件名>`），把它的地址放进 `.init_array` 段，C 运行库在调用 `main` 之前依次调用。翻译单元之间的顺序取决于链接器怎样排列 `.init_array`。GCC 和 Clang 的 `__attribute__((init_priority(N)))` 可以显式调整优先级。
    - Itanium ABI 中，静态对象构造完成后，编译器生成一次 `__cxa_atexit(dtor, obj, __dso_handle)` 调用。析构函数和 `atexit` 回调共用同一个注册栈，¶6 的交错顺序由此自然得到。`__dso_handle` 让共享库被 `dlclose` 时只运行属于它的析构。
    - 函数局部静态变量用一个 guard 变量加 `__cxa_guard_acquire`、`__cxa_guard_release`、`__cxa_guard_abort` 实现线程安全的一次初始化。GCC 的 `-fno-threadsafe-statics` 可以关掉它，但那不符合标准。
    - MSVC 用 `.CRT$XC*` 段排列初始化函数，`#pragma init_seg(compiler|lib|user)` 控制对象放在哪一段，从而控制大致的顺序。

## 历史与演进

!!! history
    - C++98 就有同一翻译单元按定义顺序、不同翻译单元不规定顺序的规则，也允许延迟初始化。
    - C++11 让块作用域静态变量的初始化成为线程安全的，引入了 `thread_local` 及其初始化规则和 `quick_exit`，顺序规则改用 sequenced before、happens before 描述。
    - C++17 的 inline 变量带来了部分有序这一类别。
    - C++20 加入了 `constinit`（[[P1143R2]]）；`constexpr` 析构函数让常量析构成为可能；模块让出现顺序可以跨翻译单元成立；同时禁止 `main` 是协程或附着于具名模块。
    - C++26 起，从 `main` 返回时会求值 `main` 的后置条件断言。

## 常见误解

!!! pitfall "全局对象一定在 main 之前构造"
    ¶5 允许延迟。主流实现确实在 `main` 之前构造，但代码不应依赖某个全局构造函数的副作用（比如向工厂注册自己）一定在 `main` 之前发生。另外，如果静态库里的某个目标文件没有被任何地方引用，链接器根本不会把它链接进来，它的自注册全局对象也就不存在。这是链接器的行为，不是标准的规定，但同样会让自注册工厂失效。

!!! pitfall "析构函数是 constexpr 的对象就是常量析构"
    ¶3 只把常量析构的对象排到最后。析构函数是 `constexpr` 的，但这次析构实际做了不能在常量求值中做的事情，就不算常量析构。

!!! pitfall "main 返回后，后台线程用 std::cout 是安全的"
    `std::cout` 本身确实永不销毁，但 ¶7 不看对象是否已销毁：只要使用了信号处理函数中不允许使用的库设施，而这次使用不先于静态析构的完成，就是 UB，`std::cout` 也在其中。`main` 返回之前 join 所有线程，例如把线程放在 `main` 里的 `std::jthread` 局部对象中，就能避免这个问题。

## 思考题

!!! question "思考题 1"
    下面的程序输出什么？
    ```cpp
    #include <cstdio>
    struct S { S() { std::puts("S"); } ~S() { std::puts("~S"); } };
    S& get() { static S s; return s; }
    struct U { U() { get(); std::puts("U"); } ~U() { std::puts("~U"); } } u;
    int main() {}
    ```

<details markdown="1">
<summary>答案</summary>

`S`、`U`、`~U`、`~S`。`u` 的构造函数里调用了 `get()`，所以 `s` 在 `u` 的初始化完成之前就初始化完成了。按 ¶4，析构顺序看视同构造，也就是初始化完成的时刻；`s` 早于 `u`，所以 `u` 先析构，`~U` 里再调用 `get()` 也是安全的。在构造函数里先调用一次单例这个对策，原理就在这里。
</details>

!!! question "思考题 2"
    两个翻译单元里都有 `inline int x = f();`（同一个 inline 变量），TU1 中在 `x` 之后还定义了普通全局变量 `int y = x + 1;`。`y` 一定能看到初始化后的 `x` 吗？

<details markdown="1">
<summary>答案</summary>

能。`x` 是部分有序的，`y` 是有序的，不是无序。¶3.1 的第二种情形要求 `y` 的每个定义（只有 TU1 中一个）前面都有 `x` 的某个定义，TU1 中 `x` 的定义就在 `y` 之前，所以 `x` 先于 `y` 初始化。如果 `y` 定义在一个没有 `x` 定义的翻译单元里，就没有这个保证。
</details>

!!! question "思考题 3"
    为什么 `int main() { return main(); }` 是非良构，而不是 UB？

<details markdown="1">
<summary>答案</summary>

`main` 不得在表达式中使用是一条可诊断规则：[[basic.start.main#3]] 用的是 shall not，也没有注明不要求诊断。按 [[intro.compliance]]，违反它的程序非良构，实现必须至少给出一条诊断。诊断之后是否仍然生成可执行文件是实现的自由，Clang 就把它当作扩展接受。
</details>

## 小结

| 阶段 | 规则 | 出处 |
|---|---|---|
| 静态初始化 | 常量初始化或零初始化；先于一切动态初始化，没有顺序问题 | [[basic.start.static#2]] |
| 同一翻译单元的动态初始化 | 按定义顺序 | [[basic.start.dynamic#3]] |
| 跨翻译单元的动态初始化 | 不定序，即 SIOF；对策：`constinit`、函数局部静态、Schwarz 计数器、模块 | [[basic.start.dynamic#3]] |
| 模板静态成员 | 无序 | [[basic.start.dynamic#1]] |
| 延迟初始化 | 实现定义；若延迟，须先于同一翻译单元实体的首次非初始化 odr 使用 | [[basic.start.dynamic#5]] |
| 初始化抛异常 | `std::terminate` | [[basic.start.dynamic#8]] |
| 析构顺序 | 视同构造的逆序，`atexit` 回调参与同一逆序，常量析构的对象最后 | [[basic.start.term#3]]–[[basic.start.term#6]] |
| `exit` | 不析构自动对象；析构期间调用 `exit` 是 UB | [[basic.start.main#4]] |
| 已销毁的局部静态 | 析构期间再经过它的定义是 UB | [[basic.start.term#5]] |
