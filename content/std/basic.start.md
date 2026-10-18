---
title: 程序的启动与终止
summary: main 函数的形式与限制；静态初始化（零初始化、常量初始化）与动态初始化的有序/部分有序/无序；静态初始化顺序问题及其对策；exit、atexit 与析构顺序
status: draft
covers: *
papers: P1143R2
related: basic.stc.static, basic.stc.thread, stmt.dcl, expr.const.init, dcl.init, support.start.term, class.dtor
tags: 初始化, 生命周期, 链接, UB
updated: 2026-10-17
---

一个 C++ 程序在 `main` 的第一条语句之前、`main` 返回之后都在执行代码：构造和析构静态存储期对象、调用 `atexit` 注册的函数、初始化线程局部变量。本节（6.10.3）规定的就是 `main` 之外的这些事情：

- [[basic.start.main]]：`main` 可以有哪些形式，有哪些限制；
- [[basic.start.static]]：哪些初始化在编译期/加载期完成（静态初始化）；
- [[basic.start.dynamic]]：其余的初始化（动态初始化）按什么顺序发生，著名的**静态初始化顺序问题**（static initialization order fiasco, SIOF）就出在这里；
- [[basic.start.term]]：程序结束时析构和 `atexit` 回调的顺序。

阅读前提：[[basic.stc.static]]（静态存储期）、[[basic.stc.thread]]（线程存储期）、[[expr.const.init]]（常量初始化的判定）、[[intro.races]]（strongly happens before）。

## main 函数（basic.start.main）

### 程序入口（¶1）

[[basic.start.main#1]] 程序必须恰好包含一个属于全局作用域、名为 `main` 的函数。执行程序就是启动一个主执行线程，并在其中调用 `main`。独立实现（freestanding）是否要求定义 `main` 由实现定义 {{impl}}（注 1：独立环境中启动与终止都是实现定义的，内核、固件常常从别的入口开始）。

### 合法的签名（¶2）

[[basic.start.main#2]] 实现不得预定义 `main`。`main` 的类型必须有 C++ 语言链接，声明的返回类型必须是 `int`，除此之外其类型由实现定义。实现必须接受两种类型：

- `int()`，可带 `noexcept`；
- `int(int, char**)`，可带 `noexcept`。

在第二种形式中，`argc` 是从环境传入的实参个数（非负），若非零，`argv[0]` 到 `argv[argc-1]` 指向以空字符结尾的多字节字符串，`argv[0]` 是调用程序时使用的名字或 `""`；`argv[argc]` 必须为 0（空指针）。标准建议把附加的可选参数加在 `argv` 之后，常见的 `int main(int, char**, char** envp)` 扩展就以此为依据。

```cpp run title="main-ok.cpp" ok
auto main(int argc, char** argv) noexcept -> int {   // 尾置返回类型：声明的返回类型仍是 int
  return argv[argc] == nullptr ? 0 : 1;               // argv[argc] 保证为 0
}
```

`auto main() { return 0; }` 是非良构的，因为声明的返回类型是占位符 `auto` 而不是 `int`。Clang 的诊断是 "'main' must return 'int'"。

### main 的限制（¶3）

[[basic.start.main#3]] 列出了一系列禁令：

| 写法 | 结果 | 理由 |
|---|---|---|
| 在表达式中命名 `main`（递归调用、取地址） | 非良构 | 实现可能在 `main` 中插入启动代码（如调用静态构造函数），重入它没有意义 |
| `main` 定义为 deleted；声明为 `inline`、`static`、`constexpr`、`consteval` | 非良构 | `main` 必须是一个真正存在、可被环境调用的外部函数 |
| `main` 是协程 | 非良构 | 环境无法驱动协程的挂起与恢复 |
| `main` 带 `"C++"` 以外的链接规范 | 非良构 | |
| 全局作用域的变量 `main` | 非良构 | 与链接器层面的入口符号冲突 |
| 附着于具名模块的全局函数 `main` | 非良构 | 模块链接会改变符号名 |
| 全局作用域的函数模板 `main` | 非良构 | |
| 任何命名空间中具有 C 语言链接、名为 `main` 的实体 | 非良构 | 它的符号就是 `main`，会冲突 |

`main` 的链接（linkage）本身由实现定义 {{impl}}。`main` 这个名字在其他地方不保留：成员函数、类、枚举、其他命名空间里的函数都可以叫 `main`。

```cpp run title="main-names.cpp" ok
namespace N { int main() { return 1; } }   // OK：不在全局作用域
struct S { void main() {} };               // OK：成员函数
int main() { return N::main() - 1; }
```

```cpp run title="main-bad.cpp" error
inline int main() {}   // error: main 不能是 inline
```

!!! impl "Clang 对两条规则只给警告"
    对 `int main() { return main(); }`，Clang 23 只给出 `-Wmain` 警告（"referring to 'main' within an expression is a Clang extension"）；对 `extern "C" int main()` 也只警告。标准说这两种程序都是非良构的，但非良构只要求至少给出一条诊断，警告也是诊断，所以 Clang 符合标准，只是在给出诊断后（作为扩展）继续接受了程序。GCC 在 `-pedantic` 下对递归调用 `main` 同样给出诊断。

### 不离开块就终止（¶4）

[[basic.start.main#4]] 用 `std::exit` 等方式在不离开当前块的情况下终止程序时，不销毁任何自动存储期对象。若在静态或线程存储期对象的析构期间调用 `std::exit`，行为未定义 {{ub}}（`exit` 会重入析构流程）。

### 从 main 返回（¶5）

[[basic.start.main#5]] `main` 中的 `return` 语句的效果是：离开 `main`（销毁自动对象，并 {{c++26}} 求值 `main` 的后置条件断言），然后以返回值为实参调用 `std::exit`。控制流到达 `main` 末尾等价于 `return 0;`。`main` 是唯一一个流出末尾不算 UB 的非 void 函数（参见 [[stmt.return]]）。

```cpp run title="exit-vs-return.cpp" ok
#include <cstdio>
#include <cstdlib>
struct T { ~T() { std::puts("~T"); } };
int main(int argc, char**) {
  T t;
  if (argc > 5) std::exit(0);   // 走这条路：不打印 "~T"
  return 0;                     // 走这条路：先销毁 t，打印 "~T"，再调用 exit(0)
}
```

## 静态初始化（basic.start.static）

### 两个阶段（¶1）

[[basic.start.static#1]] 静态存储期变量的初始化是程序启动的一部分；线程存储期变量的初始化是线程执行的一部分。每个阶段内部都按下面的规则进行。

### 零初始化与常量初始化（¶2）

[[basic.start.static#2]] 对静态或线程存储期变量：

1. 若它是常量初始化的（constant-initialized，[[expr.const.init]]：初始化器是常量表达式等条件），就执行**常量初始化**（constant initialization）；
2. 否则，先对它进行**零初始化**（[[dcl.init]]）。

零初始化和常量初始化合称[[g:static-initialization|**静态初始化**]]（static initialization）；其余一切初始化都是**动态初始化**（dynamic initialization）。所有静态初始化 strongly happens before 任何动态初始化。

!!! std
    Together, zero-initialization and constant initialization are called static initialization; all other initialization is dynamic initialization. All static initialization strongly happens before any dynamic initialization.

这条规则在工程上的意义是：静态初始化的值在任何用户代码运行之前就已就位。实践中，它们直接写在可执行文件的 `.data`（常量初始化）或 `.bss`（零初始化）段，由加载器映射进内存，根本不需要执行代码。所以**静态初始化不存在顺序问题**。

```cpp run title="static-vs-dynamic.cpp" ok
#include <cstdlib>
int a = 42;                    // 常量初始化
int b;                         // 零初始化
constexpr double pi = 3.14159; // 常量初始化
bool c = std::getenv("HOME");  // 动态初始化（getenv 不能常量求值）；在此之前 c 已被零初始化
struct P { int x, y; };
P p = { 1, 2 };                // 常量初始化（聚合初始化，初始化器都是常量表达式）
int main() { return a - 42 + b + (p.x - 1) + (int(pi) - 3) + (c ? 0 : 0); }
```

### 允许把动态初始化提前为静态（¶3）

[[basic.start.static#3]] 即使标准不要求，实现也可以把动态初始化当作静态初始化执行，只要满足：

- ¶3.1 动态版本不会在其他静态/线程存储期对象初始化之前修改它们的值；
- ¶3.2 静态版本产生的值，与所有不要求静态初始化的变量都动态初始化时动态版本产生的值相同。

这让优化器可以对全局初始化器做常量折叠：对于 `double d = 1.0 + 2.0;` 或调用内联函数的初始化器，编译器可以在编译期算出结果。注 2 指出了由此带来的后果：若 obj1 的初始化引用了同一 TU 中后定义的、可能需要动态初始化的 obj2，那么读到的 obj2 是完全初始化后的值还是零值，是未指定的。

```cpp run title="note2.cpp" unspecified
#include <cstdio>
inline double fd() { return 1.0; }
extern double d1;
double d2 = d1;       // d1 若已被"提前静态初始化"则为 1.0，否则为 0.0
double d1 = fd();
int main() { std::printf("%g %g\n", d1, d2); }
```

标准给出的结论是：若 d1 被静态初始化、d2 被动态初始化，二者都是 1.0；其他情况下 d2 为 0.0。

## 非块变量的动态初始化（basic.start.dynamic）

### 三种初始化类别（¶1）

[[basic.start.dynamic#1]] 非块（namespace 作用域或静态数据成员）静态存储期变量的动态初始化分为三类：

| 类别 | 适用于 | 直觉 |
|---|---|---|
| 无序（unordered） | 隐式或显式实例化的特化（类模板的静态数据成员、变量模板的特化） | 模板实例化可能出现在任意多个 TU 中，谈不上定义位置 |
| 部分有序（partially-ordered） | 不是实例化特化的 `inline` 变量 | 定义在多个 TU 中出现，但每处都有明确的位置 |
| 有序（ordered） | 其余所有（普通全局变量、普通静态数据成员、非 inline 显式特化） | 唯一定义，位置明确 |

注 1：模板化变量的非 inline 显式特化属于有序初始化，因为它不是实例化出来的，只有一个定义。

### 出现顺序（¶2）

[[basic.start.dynamic#2]] 如果 D 在 E 之前，并且满足以下条件之一，则称声明 D **出现顺序先于**（appearance-ordered before）声明 E：

- ¶2.1 二者在同一 TU 中，或
- ¶2.2 E 所在 TU 对 D 所在 TU 有接口依赖（[[module.import]]，即直接或间接导入了它）。

{{c++20}} ¶2.2 是模块带来的：`import M;` 之后，模块 M 接口单元中定义的变量就视为出现在导入点之前。这样模块就有了跨 TU 的、有保证的初始化顺序，传统的头文件加多 TU 的方式则没有。

### 顺序规则（¶3）

[[basic.start.dynamic#3]] 对两个静态存储期非块变量 V、W：

- ¶3.1 若 V、W 都有序初始化且 V 的定义出现顺序先于 W 的定义，或者 V 部分有序、W 不是无序，且 W 的每个定义都有某个 V 的定义出现顺序先于它，则：
    - ¶3.1.1 若程序除主线程外不启动其他线程，或 V、W 都有序且定义在同一 TU 中，V 的初始化 sequenced before W 的初始化；
    - ¶3.1.2 否则，V 的初始化 strongly happens before W 的初始化。
- ¶3.2 否则，若程序在 V 或 W 初始化之前启动了主线程以外的线程，在哪个线程中初始化 V、W 是未指定的；若在同一线程中，则二者无序。
- ¶3.3 否则，V 与 W 的初始化不定序（indeterminately sequenced）。

注 2：这一定义允许一串有序变量的初始化与另一串并发进行。

最重要的推论：

- **同一 TU 中，普通全局变量按定义顺序初始化**（¶3.1）。
- **不同 TU 之间的普通全局变量，初始化顺序不定**（¶3.3，在没有模块导入关系时），这就是 SIOF 的根源。
- 模板静态数据成员相对于任何变量都没有顺序保证（无序）。

```cpp run title="categories.cpp" ok
#include <cstdio>
struct Tr { Tr(const char* s) { std::puts(s); } };
inline Tr i1("inline variable i1");                       // 部分有序
Tr o1("ordered o1");                                      // 有序
template<class T> struct H { static Tr t; };
template<class T> Tr H<T>::t("template static member");   // 无序
template struct H<int>;
Tr o2("ordered o2");                                      // 有序：一定在 o1 之后
int main() {}
```

`i1` 在 `o1` 之前（¶3.1 部分有序情形：本 TU 中 `i1` 的定义先于 `o1`），`o1` 在 `o2` 之前；但模板静态成员的位置没有保证。用 Clang 23 运行，模板成员实际在 `o1` 之前输出，尽管它在源码里写在 `o1` 之后。

### 静态初始化顺序问题（SIOF）

```cpp title="a.cpp"
#include <string>
std::string greeting = "hello, this is a long string beyond SSO";
```

```cpp title="b.cpp" ub
#include <cstdio>
#include <string>
extern std::string greeting;
std::size_t len = greeting.size();   // greeting 可能尚未构造！
int main() { std::printf("%zu\n", len); }
```

`greeting` 和 `len` 都是有序初始化，但定义在不同 TU 中，二者之间没有出现顺序关系，因此不定序（¶3.3）。若 b.cpp 的初始化先运行，`greeting.size()` 就是在一个尚未开始生命周期（只做了零初始化）的对象上调用成员函数，这是 UB（[[basic.life]]）。实测（Clang 23 + libc++，macOS）：`clang++ a.cpp b.cpp` 输出 39，`clang++ b.cpp a.cpp` 输出 0，初始化顺序由链接顺序决定。

还有一个细节：把字符串换成短的 `"hello"`，两种链接顺序都输出 5。这是因为 libc++ 的 `std::string` 构造函数是 `constexpr` 的，短字符串走 SSO 不分配内存，整个初始化是常量表达式，于是执行的是常量初始化（¶2），根本不参与动态初始化的排序。这引出了 SIOF 的第一个对策。

### SIOF 的对策

**1. 让它变成静态初始化：`constexpr` / `constinit`**

{{c++20}} `constinit`（[[dcl.constinit]]）断言变量是常量初始化的，否则非良构。它不像 `constexpr` 那样隐含 `const`，变量仍可修改：

```cpp run title="constinit.cpp" ok
constinit int counter = 42;               // OK：常量初始化，不参与动态初始化排序
constinit thread_local int tls = 0;       // OK：访问时也无需"是否已初始化"的检查
int main() { return counter - 42 + tls; }
```

```cpp run title="constinit-bad.cpp" error
int f();
constinit int bad = f();   // error: 不是常量初始化
```

`constinit` 由 [[P1143R2]] 引入。它把"这个全局变量没有 SIOF"从一个约定变成了编译期检查。

**2. 函数局部静态变量（"Meyers 单例"）**

```cpp run title="meyers.cpp" ok
#include <string>
std::string& greeting() {
  static std::string s = "hello, this is a long string beyond SSO";  // 首次经过时初始化
  return s;
}
std::size_t len = greeting().size();   // 无论哪个 TU 先初始化，都安全
int main() { return len == 0; }
```

块作用域静态变量的动态初始化在控制流第一次经过其声明时进行（[[stmt.dcl#3]]），C++11 起保证线程安全：并发进入的线程会等待初始化完成。代价是每次访问都要检查一次是否已初始化（实现上是一次 acquire load 的快路径），另外还有析构顺序的问题（见下文 [[basic.start.term#5]]）。

**3. Schwarz 计数器（nifty counter）**

这是 iostreams 的传统做法：头文件里定义一个每个 TU 各有一份的静态初始化器对象，它的构造函数递增一个计数器，第一次时构造真正的全局对象；析构时递减，最后一次时析构全局对象。由于每个包含该头文件的 TU 中，初始化器对象的定义都出现在该 TU 所有使用者之前（¶3.1），任何使用者被初始化时，全局对象都已构造好。

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
static struct StreamInitializer {      // 每个包含 stream.h 的 TU 一份
  StreamInitializer();
  ~StreamInitializer();
} stream_initializer;
// ---- stream.cpp ----
static int nifty_counter;              // 零初始化：静态初始化，先于一切动态初始化
alignas(Stream) static unsigned char buf[sizeof(Stream)];
Stream& stream() { return *std::launder(reinterpret_cast<Stream*>(buf)); }
StreamInitializer::StreamInitializer() { if (nifty_counter++ == 0) ::new (buf) Stream(); }
StreamInitializer::~StreamInitializer() { if (--nifty_counter == 0) stream().~Stream(); }
// ---- user.cpp ----
struct User { User() { stream().write("using stream in a static ctor\n"); } } user;
int main() {}
```

关键在于计数器 `nifty_counter` 是零初始化的，它在任何动态初始化之前就是 0（¶2），所以无论哪个 TU 的 `StreamInitializer` 先运行，都能正确判断自己是不是第一个。

标准 [[iostream.objects.overview]] 至今仍规定，包含 `<iostream>` 的效果如同它定义了一个静态存储期的 `ios_base::Init` 实例，这就是 nifty counter 在标准中的体现。它还规定标准流对象在 `main` 开始前构造，且在程序执行期间不被销毁，所以静态对象的析构函数中也可以安全地使用 `std::cout`。库实现可以用更高效的方式（比如在运行库内部用实现特定的初始化优先级）满足这一要求。

**4. 模块**

{{c++20}} 若 b 所在的 TU `import` 了定义 `greeting` 的模块，¶2.2 保证 `greeting` 的定义出现顺序先于 `len`，从而有序（¶3.1）。

### 非初始化 odr 使用与延迟初始化（¶4–¶7）

[[basic.start.dynamic#4]] 不是由非块静态/线程存储期变量的初始化直接或间接引起的 odr 使用（[[basic.def.odr]]），称为**非初始化 odr 使用**（non-initialization odr-use）。

[[basic.start.dynamic#5]] 非块、非 inline 的静态存储期变量的动态初始化，是在 `main` 的第一条语句之前完成，还是被延迟，由实现定义 {{impl}}。若延迟，则它 strongly happens before 对同一 TU 中定义的任何非 inline 函数或非 inline 变量的任何非初始化 odr 使用。在哪个线程、何时执行延迟的初始化，由实现定义；建议实现选择能让程序员避免死锁的时机。脚注：有副作用的初始化即使变量本身未被 odr 使用，也会被执行。

为什么允许延迟？主要是为了动态加载库：`dlopen` 加载的共享库的全局对象不可能在 `main` 之前构造。标准例 1 展示了其中的微妙之处：

```cpp title="例 1"
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

例子的结论：`a`、`b` 是在进入 `main` 之前初始化、还是推迟到 `a` 在 `main` 中首次被 odr 使用时，由实现定义。若 `a` 在 `main` 之前初始化，不保证 `A::A` 调用 `b.Use()` 时 `b` 已初始化（这就是 SIOF）。若 `a` 的初始化被推迟到 `main` 开始之后，例子断言 `b` 会在 `A::A` 使用它之前完成初始化。

!!! lawyer "例 1 的最后一句"
    例子不具规范效力，而它的最后一句很难从现行规范性文字中严格推出：`A::A` 对 `b` 的使用是由 `a` 的初始化间接引起的，按 ¶4 属于初始化 odr 使用，不会触发 ¶5 的保证。例子的意图大概是：推迟初始化的实现会以 TU 为单位、在首次使用该 TU 的实体之前完成该 TU 的全部初始化。实践中没有主流实现对普通全局变量做延迟初始化，所以这一点主要是理论上的。

[[basic.start.dynamic#6]] inline 变量的规则类似，但延迟的初始化只需先于对该变量自身的非初始化 odr 使用（inline 变量可能定义在多个 TU 中，"同一 TU 中的其他实体"没有意义）。

[[basic.start.dynamic#7]] 线程存储期的非块、非 inline 变量：动态初始化在线程初始函数的第一条语句之前完成，还是被延迟，由实现定义。若延迟，线程 t 中的初始化 sequenced before t 对同一 TU 中定义的、有动态初始化的任何非 inline 线程存储期变量的首次非初始化 odr 使用。

!!! impl "Itanium ABI 中的 thread_local"
    主流实现（Itanium C++ ABI，用于 Linux/macOS 上的 GCC 与 Clang）对需要动态初始化的 `thread_local` 变量采用延迟策略：每次访问都通过一个 TLS 包装函数（mangled 名前缀 `_ZTW`），它检查本线程是否已初始化，若没有，则调用 TLS 初始化函数（前缀 `_ZTH`）初始化本 TU 中所有动态初始化的 `thread_local` 变量。这正好对应 ¶7 中以 TU 为单位的粒度。常量初始化的 `thread_local`（如用 `constinit` 声明）可以省掉包装函数的检查。
    普通的非 `thread_local` 全局变量，GCC 与 Clang 都在 `main` 之前初始化（ELF 上通过 `.init_array`），同一可执行文件中各 TU 的顺序通常跟随链接顺序；共享库的全局对象在库被加载时初始化。

### 初始化抛出异常（¶8）

[[basic.start.dynamic#8]] 非块静态/线程存储期变量的初始化若以异常退出，调用 `std::terminate`（[[except.terminate]]）。这时 `main` 还没开始，没有任何 `try` 能包住它。

```cpp run title="init-throw.cpp" ok
#include <stdexcept>
int init() { throw std::runtime_error("boom"); }
int x = init();          // 异常逃出初始化 → std::terminate（程序以 abort 结束）
int main() {}
```

（判定标为 ok，因为行为有明确定义，即调用 `std::terminate`。）块作用域静态变量则不同：其初始化抛异常时，异常正常传播给调用者，下一次经过声明时会重新尝试初始化（[[stmt.dcl#3]]）。

## 终止（basic.start.term）

### 静态与线程存储期对象的析构（¶1–¶3）

[[basic.start.term#1]] 销毁静态存储期的已构造完整对象、调用 `atexit` 注册的函数，都是 `std::exit` 调用的一部分；`exit` 的调用 sequenced before 这些析构和回调。注 1：从 `main` 返回会调用 `std::exit`。

[[basic.start.term#2]] 线程存储期对象在线程初始函数返回或该线程调用 `std::exit` 时销毁。其析构 sequenced before 该线程线程存储期对象存储的释放，并 strongly happens before 任何静态存储期对象的析构。所以 `main` 线程的 `thread_local` 先于全局对象销毁。

[[basic.start.term#3]] 具有**常量析构**（constant destruction，[[expr.const.defns]]：析构可以在常量求值中完成，典型如平凡析构）的完整对象被放到最后销毁：线程存储期的在该线程其他线程存储期对象之后，静态存储期的在所有其他静态对象和所有 `atexit` 回调之后。本条款其余的顺序规则只适用于非常量析构的对象。

为什么这样安排？常量析构的对象在析构时没有可观察效果，把它们放到最后，其他对象的析构函数就可以安全地使用它们，例如在析构函数里访问一个全局的 `int` 或 `std::array<int, N>`，不必担心它已被销毁。

### 析构顺序：与构造相反（¶4）

[[basic.start.term#4]]：

- 若静态存储期完整对象 X 的**视同构造**（deemed construction，[[dcl.init.general#21]]：初始化完成之时）strongly happens before Y 的视同构造，则 Y 的析构完成 sequenced before X 的析构开始。
- 线程存储期对象类似（关系换成 sequenced before）。
- 静态初始化的对象，按如同它是动态初始化时的顺序析构。
- 析构以异常退出时调用 `std::terminate`。

视同构造是特意选择的时间点：初始化完成时，而不是开始时。看标准例 1：

```cpp title="例 1（标准）"
struct DTemp { ~DTemp(); };
struct Temp {
  ~Temp() { static DTemp dt; }
};
struct BTemp { ~BTemp(); };
struct A { const BTemp& tb; ~A(); };
A a[] = { (Temp(), BTemp()), BTemp() };
int main() {}
```

`a` 的初始化是一个完整表达式。在此期间，`Temp()` 临时对象在第一个元素初始化完成后被销毁（逗号表达式内），它的析构函数里构造了块作用域静态对象 `dt`，`dt` 的视同构造在此刻完成；两个 `BTemp` 临时对象绑定到引用成员，生命周期延长到与 `a` 相同。整个完整表达式求值结束时，`a` 才视同构造完成，晚于 `dt`。于是终止时的析构顺序是：先 `a` 的元素，再 `dt`，最后两个 `BTemp`（[[basic.start.term#4]] 的例子原文结论）。

最常用的推论是：**函数局部静态对象在第一次调用时才构造，所以它的析构排在所有在它之前构造完成的对象之后**，它可能比一些先使用它的全局对象更早析构：

### 已销毁的块变量（¶5）

[[basic.start.term#5]] 若函数含有已被销毁的静态/线程存储期块变量，而该函数在静态/线程存储期对象的析构期间被调用，并且控制流经过那个已销毁变量的定义，则行为未定义 {{ub}}。注 2：通过指针等间接方式使用已销毁的块变量同样是 UB。

```cpp run title="dead-reference.cpp" ub
#include <cstdio>
#include <string>
struct Logger {
  std::string prefix = "log: a fairly long prefix to force heap allocation";
  void log(const char* m) { std::printf("%s%s\n", prefix.c_str(), m); }
};
Logger& logger() { static Logger l; return l; }
struct Client {
  ~Client() { logger().log("client destroyed"); }   // UB：l 已经被销毁
};
Client c;                       // c 先构造完成（main 之前）
int main() { logger().log("main"); }   // l 在 main 中构造完成——晚于 c
```

`l` 的视同构造晚于 `c`，所以 `l` 先析构；`c` 的析构函数再调用 `logger()`，控制流经过 `l` 的定义，因此是 UB。AddressSanitizer 在 macOS 上报告 heap-use-after-free。这是 Meyers 单例在析构期的 SIOF（有时称为 dead reference problem）。常见对策：

- 让单例永不析构：`static Logger& l = *new Logger;`（泄漏是故意的）或用 `std::optional`/placement new 不调用析构；
- 在 `Client` 构造时就调用一次 `logger()`，使 `l` 先于 `c` 构造完成，从而后析构；
- 让被依赖的对象有常量析构（¶3），它会被放到最后。

### atexit 与析构的交错（¶6）

[[basic.start.term#6]]：

- 若对象的视同构造 strongly happens before 某次 `std::atexit` 调用，则注册的函数在该对象析构开始之前被调用；
- 若某次 `atexit` 调用 strongly happens before 对象的视同构造，则该对象析构完成后才调用注册的函数；
- 若一次 `atexit` 调用 strongly happens before 另一次，则后注册的函数先被调用。

概括地说，**把 `atexit` 注册看作构造了一个对象，然后统一按逆序拆除**。

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
  std::exit(0);                 // autoobj 不会被析构（[basic.start.main]/4）
}
```

输出：

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

构造/注册顺序是 a、bye1、b、bye2、local，拆除顺序恰好相反。`auto` 从未被析构。

### 线程与标准库在终止期间的使用（¶7）

[[basic.start.term#7]] 如果使用了信号处理函数中不允许使用的标准库对象或函数，且该使用不 happens before 静态对象析构和 `atexit` 回调的完成，行为未定义 {{ub}}。注 3：使用一个静态存储期对象而不 happens before 它的析构是 UB；在调用 `std::exit` 或从 `main` 返回之前结束所有线程，足以（但不是必须）满足这些要求；这些要求允许把线程管理器做成静态对象。

实际含义是：如果 `main` 返回时还有 detach 的后台线程在运行，并使用 `std::cout` 或全局容器，就是 UB，因为全局对象可能正在被拆除。

### abort 与 quick_exit（¶8）

[[basic.start.term#8]] `std::abort()` 终止程序，不执行任何析构函数，也不调用 `atexit` 或 `at_quick_exit` 注册的函数。

[[support.start.term]] 中还有：

| 函数 | 自动对象 | 线程存储期对象 | 静态对象 | atexit 回调 | at_quick_exit 回调 | 刷新 C 流 |
|---|---|---|---|---|---|---|
| 从 `main` 返回 | 析构 | 析构 | 析构 | 调用 | — | 是 |
| `std::exit` | 不析构 | 析构（当前线程） | 析构 | 调用 | — | 是 |
| `std::quick_exit` {{c++11}} | 不 | 不 | 不 | — | 调用（逆序） | 由 `_Exit` 决定，实现定义 |
| `std::_Exit` | 不 | 不 | 不 | 不 | 不 | 实现定义 |
| `std::abort` | 不 | 不 | 不 | 不 | 不 | 实现定义 |
| `std::terminate` | 默认调用 `abort` | | | | | |

`quick_exit` 用于这样的场景：多线程程序中，后台线程仍在运行时，执行完整的静态析构很危险（¶7），`quick_exit` 只运行显式注册的少量清理函数，然后调用 `_Exit`。

## 实现视角

!!! impl "启动代码"
    - ELF（Linux）：编译器把每个 TU 的动态初始化收集到一个函数（GCC 命名为 `_GLOBAL__sub_I_<文件名>`），其地址放入 `.init_array` 段；C 运行库在调用 `main` 前依次调用。同一 TU 内的顺序由编译器保证（¶3.1），TU 之间的顺序取决于链接器排列 `.init_array` 的方式。GCC/Clang 的 `__attribute__((init_priority(N)))` 可以显式调整优先级。
    - 析构注册：Itanium ABI 中，静态对象构造完成后，编译器生成对 `__cxa_atexit(dtor, obj, __dso_handle)` 的调用。析构函数与 `atexit` 回调共用同一个注册栈，¶6 的交错语义由此自然实现。`__dso_handle` 让共享库被 `dlclose` 时只运行属于它的析构。
    - 函数局部静态：用一个 guard 变量加 `__cxa_guard_acquire` / `__cxa_guard_release` / `__cxa_guard_abort` 实现线程安全的一次初始化。GCC 的 `-fno-threadsafe-statics` 可关闭（不符合标准）。
    - MSVC：使用 `.CRT$XC*` 段排列初始化函数，`#pragma init_seg(compiler|lib|user)` 控制所在段，从而控制大致顺序。

!!! impl "常量初始化的实际边界"
    是否常量初始化完全由 [[expr.const.init]] 决定，与优化级别无关：在 `-O0` 下，`std::string greeting = "hello";` 在 libc++ 上依然是常量初始化（因为构造函数是 `constexpr` 且不分配）。但换一个标准库（或字符串变长）就不是了。依赖这种细节并不可靠，需要保证时应写 `constinit`。

## 历史与演进

!!! history "演进"
    - **C++98**：已有同一 TU 按定义顺序、不同 TU 未指定的规则，以及对延迟初始化的许可；块作用域静态变量的初始化不保证线程安全（C++98 没有线程）。
    - **C++11**：块作用域静态变量的初始化成为线程安全的（magic statics）；引入 `thread_local` 及其初始化规则；`quick_exit`/`at_quick_exit`；顺序规则改用 sequenced before / happens before 描述。
    - **C++17**：inline 变量引入部分有序初始化类别。
    - **C++20**：`constinit`（[[P1143R2]]）；`constexpr` 析构函数让常量析构成为可能；模块让出现顺序可以跨 TU 定义；禁止 `main` 为协程、`main` 附着于具名模块等。
    - **C++26**：从 `main` 返回会求值 `main` 的后置条件断言。当前草案还用视同构造这一术语来精确界定析构顺序的参照点。

## 陷阱

!!! pitfall "“全局对象在 main 之前构造”不是保证"
    ¶5 允许延迟。主流实现确实在 `main` 之前构造，但代码不应依赖某个全局对象构造函数的副作用（如注册到工厂）一定在 main 之前发生。更麻烦的是，若静态库中的某个 TU 没有被任何地方引用，链接器根本不会把它拉进可执行文件，它的自注册全局对象也就不存在。这是链接器的行为，不是标准的规定，但同样会让自注册工厂模式失效。

!!! pitfall "constexpr 析构不等于没有析构"
    ¶3 只把常量析构的对象放到最后。一个有 `constexpr` 析构函数、但析构时做了不能常量求值的事情的对象，不算常量析构。

!!! pitfall "从 main 返回后，后台线程仍在运行"
    `std::thread::detach` 出去的线程在 `main` 返回时仍可能运行；此时全局对象被析构，它若访问全局对象或 `<iostream>` 以外的库设施，就是 UB（¶7）。`std::jthread` 作为局部对象在 `main` 返回前 join，是更安全的选择。

## 思考题

!!! question "1. 下面的程序输出什么？"
    ```cpp
    #include <cstdio>
    struct S { S() { std::puts("S"); } ~S() { std::puts("~S"); } };
    S& get() { static S s; return s; }
    struct U { U() { get(); std::puts("U"); } ~U() { std::puts("~U"); } } u;
    int main() {}
    ```

<details markdown="1">
<summary>答案</summary>

`S`、`U`、`~U`、`~S`。`u` 的构造函数中调用 `get()`，`s` 的初始化在 `u` 的初始化完成之前就完成了。按 ¶4，析构顺序看的是视同构造（初始化完成的时间），`s` 早于 `u`，所以 `u` 先析构，`~U` 中若再调用 `get()` 也是安全的。在构造函数里先调用一次单例这一对策，原理就在于此。
</details>

!!! question "2. 两个 TU 中各有一个 `inline int x = f();`（同一个 inline 变量），以及 TU1 中在 `x` 之后定义的普通全局变量 `int y = x + 1;`。y 一定看到初始化后的 x 吗？"

<details markdown="1">
<summary>答案</summary>

是。`x` 部分有序，`y` 有序（不是无序）。¶3.1 的第二种情形要求：对 `y` 的每个定义（只有 TU1 中一个），都存在 `x` 的某个定义出现顺序先于它。TU1 中 `x` 的定义就在 `y` 之前。于是 `x` 的初始化 sequenced before（或在多线程启动时 strongly happens before）`y` 的初始化。反过来，若 `y` 定义在一个看不到 `x` 定义的 TU 中，则没有保证。
</details>

!!! question "3. 为什么 `int main() { return main(); }` 是非良构而不是 UB？"

<details markdown="1">
<summary>答案</summary>

因为"`main` 不得在表达式中被命名"是一条可诊断的语法/语义规则（[[basic.start.main#3]] 用的是 "shall not"，且没有标"no diagnostic required"），按 [[intro.compliance]] 违反它的程序是非良构的，实现必须给出至少一条诊断。是否在给出诊断后仍生成可执行文件，是实现的自由（Clang 就把它当扩展接受）。
</details>

## 小结

| 阶段 | 规则 | 出处 |
|---|---|---|
| 静态初始化 | 常量初始化或零初始化；先于一切动态初始化；没有顺序问题 | [[basic.start.static#2]] |
| 动态初始化（同 TU、有序） | 按定义顺序 | [[basic.start.dynamic#3]] |
| 动态初始化（跨 TU） | 不定序 → SIOF；对策：`constinit`、函数局部静态、nifty counter、模块 | [[basic.start.dynamic#3]] |
| 模板静态成员 | 无序 | [[basic.start.dynamic#1]] |
| 延迟初始化 | 实现定义；若延迟，须先于同 TU 实体的首次非初始化 odr 使用 | [[basic.start.dynamic#5]] |
| 初始化抛异常 | `std::terminate` | [[basic.start.dynamic#8]] |
| 析构顺序 | 视同构造的逆序；`atexit` 回调参与同一逆序；常量析构对象最后 | [[basic.start.term#3]]–[[basic.start.term#6]] |
| `exit` | 不析构自动对象；析构期间调用 `exit` 是 UB | [[basic.start.main#4]] |
| 已销毁的局部静态 | 析构期间再次经过其定义 → UB | [[basic.start.term#5]] |
