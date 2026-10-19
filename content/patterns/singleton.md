---
title: 单例与静态初始化顺序
summary: 全局对象在多个翻译单元之间的初始化和销毁顺序为什么不可靠，Meyers 单例、constinit、永不析构的单例、nifty counter 和 inline 变量各自解决了哪一部分，guard 检查的代价，共享库里的多份单例，以及用依赖注入代替单例。
status: draft
order: 25
since: c++98
papers: N2660, P1143R2, P0386R2
related: basic.start, stmt.dcl, dcl.constinit, dcl.inline, class.static.data, iostream.objects, ios.init, toolchain/linking-and-symbols, history/threads-and-memory-model, patterns/factory-and-registration, patterns/raii
tags: 单例, 静态初始化, SIOF, constinit, inline 变量, 共享库, 依赖注入, 模式
updated: 2026-10-19
---

!!! tldr
    - 不同翻译单元里的全局对象，动态初始化的先后没有保证。一个全局对象的构造函数读另一个翻译单元的全局对象，结果可能随链接顺序改变。
    - 能在编译期算出初值的变量走常量初始化，不参与这种排序；`constinit` 让编译器检查这一点。
    - Meyers 单例（函数内的 `static` 局部对象）把初始化推迟到第一次调用，C++11 起线程安全。代价是每次调用都要检查一个 guard 变量，这次 acquire 读会阻止编译器把访问提到循环外。
    - 析构按构造完成的逆序进行，晚构造的单例会先析构，之后再访问它是 UB。需要在退出阶段使用的单例，通常做成永不析构的。
    - 单例很难测试，并且在共享库之间可能出现多份。多数情况下，把依赖作为参数传进去（依赖注入）比单例更好。

## 一个依赖链接顺序的程序

```cpp title="config.cpp"
#include <map>
#include <string>
std::map<std::string, int> config = {   // 动态初始化：要分配节点
  {"port", 8080}, {"threads", 4},
};
int get(const std::string& key) {
  auto it = config.find(key);
  return it == config.end() ? -1 : it->second;
}
```

```cpp title="server.cpp" ub
#include <cstdio>
#include <string>
int get(const std::string& key);
struct Server {
  int port;
  Server() : port(get("port")) {}       // 读另一个 TU 的全局对象
} server;
int main() { std::printf("port = %d\n", server.port); }
```

本机 Clang 23 + libc++，`clang++ config.cpp server.cpp` 输出 `port = 8080`，`clang++ server.cpp config.cpp` 输出 `port = -1`，`-O0` 和 `-O2` 相同。两个程序的源代码完全一样，差别只是命令行上文件的顺序。

第二种顺序下，`server` 先构造，它调用的 `get` 去查一个还没有构造的 `map`。这个 `map` 此时只是一块零初始化的内存，在它上面调用成员函数是 UB。本机恰好得到 `-1`，换一个标准库也可能直接崩溃。

这个问题叫**静态初始化顺序问题**（[[g:static-initialization-order-fiasco|static initialization order fiasco]]，SIOF）。默认情况下 ASan 不报告它；加上 `ASAN_OPTIONS=check_initialization_order=1` 运行第二种顺序的程序，报告 `initialization-order-fiasco`；再加 `strict_init_order=1`，第一种顺序也会报告，因为它只是碰巧正确。

单例模式在 C++ 里的大部分讨论，都围绕着怎样让全局唯一的对象在被使用时已经构造好、在被使用期间还没有销毁。

## 静态初始化与动态初始化

静态存储期的变量（全局变量、命名空间作用域变量、类的静态数据成员、函数内的 `static` 变量）的初始化分两种（[[basic.start.static#2]]）：

- **静态初始化**：如果变量是常量初始化的，也就是初始化器是一个常量表达式（[[expr.const.init]]），就做**常量初始化**；否则先做零初始化。这一步在程序开始运行之前完成，实现通常直接把初值写进可执行文件的数据段。
- **动态初始化**：其他所有初始化，需要在运行时执行代码，比如调用非 `constexpr` 的构造函数。

所有静态初始化都先于任何动态初始化（[[basic.start.static#2]]）。所以常量初始化的变量不存在顺序问题，任何构造函数在任何时候读它，读到的都是最终值。

动态初始化的顺序由 [[basic.start.dynamic#3]] 规定，细节见 [[basic.start]]。落到代码上有三条：

- 同一个翻译单元中的普通全局变量，按定义的先后初始化；
- 不同翻译单元中的普通全局变量，初始化不定序，即一定一前一后，但标准不规定哪个在前；
- 模板的静态数据成员（隐式或显式实例化的特化）是无序初始化，和任何变量之间都没有顺序保证（[[basic.start.dynamic#1]]）。

上例的 `config` 和 `server` 属于第二条。本机的实现按链接时目标文件的顺序依次运行各翻译单元的初始化函数，所以结果跟着命令行变。

### 用 constinit 把问题变成编译错误

如果一个全局对象可以在编译期构造，它就不需要排序。`constinit`（C++20，[[P1143R2]]）声明一个变量必须是常量初始化的，否则程序非良构（[[dcl.constinit#2]]）：

<div class="compare" markdown="1">

```cpp ok
#include <array>
#include <string_view>
struct Entry {
  std::string_view key;
  int value;
};
constinit std::array<Entry, 2> config = {{
  {"port", 8080}, {"threads", 4},
}};
```

```cpp error
#include <map>
#include <string_view>
constinit std::map<std::string_view, int>
  config = {{"port", 8080}};
// error: 不是常量初始化
// map 的节点在堆上分配
```

</div>

本机 Clang 23 对右边给出 `variable does not have a constant initializer`，附注指出指向堆分配对象的指针不是常量表达式。左边的 `config` 在程序启动前就已经是最终值，任何翻译单元的构造函数都可以安全地读它。

`constinit` 不改变初始化方式，只是要求检查。不写 `constinit` 的变量，只要它的初始化恰好是常量表达式，同样是常量初始化的；写上它，是为了防止以后某次改动把初始化悄悄变成动态的。它也不像 `constexpr` 那样隐含 `const`，变量仍然可以修改。

[[basic.start.static#3]] 还允许实现把某些动态初始化提前做成静态初始化，只要结果相同。这是一种优化许可，程序不能依赖它。

## Meyers 单例

全局对象的初始化时机是程序启动，函数内 `static` 对象的初始化时机是控制第一次经过它的声明（[[stmt.dcl#3]]）。把全局对象换成一个返回局部 `static` 对象引用的函数，就把初始化顺序问题交给了调用顺序：

```cpp run title="classic.cpp" ok
#include <cstdio>
#include <string>
#include <string_view>

class Logger {
public:
  static Logger& instance() {
    static Logger l;               // 第一次调用时构造，线程安全
    return l;
  }
  Logger(const Logger&) = delete;
  Logger& operator=(const Logger&) = delete;

  void log(std::string_view msg) {
    std::printf("%s%.*s\n", prefix_.c_str(), int(msg.size()), msg.data());
  }
private:
  Logger() : prefix_("[app] ") {}  // 外部无法构造第二个
  ~Logger() = default;             // 外部无法 delete
  std::string prefix_;
};

int main() {
  Logger::instance().log("started");
}
```

这种写法通常称为 **Meyers 单例**。把开头的 `config.cpp` 改成同样的形式，`std::map<std::string, int>& config()` 里放一个 `static` 的 `map`，两种链接顺序都输出 `port = 8080`，ASan 在 `strict_init_order=1` 下也不再报告。`server` 的构造函数第一次调用 `config()` 时，`map` 当场构造。

它依靠的几条规则：

- [[stmt.dcl#3]]：局部 `static` 变量的动态初始化在控制第一次经过声明时执行。初始化以异常退出时不算完成，下次调用会重试。
- 同一条：另一个线程在初始化进行期间进入声明，必须等待初始化完成。这是 C++11 加入的保证（[[N2660]]）。C++98 没有线程和内存模型，当时常用的双重检查锁定无法可移植地写对，见 [[history/threads-and-memory-model]]。
- 同一条：初始化尚未完成时，同一线程递归进入这条声明，行为未定义。单例的构造函数间接调用 `instance()` 就会落入这种情况，见 [[stmt.dcl]]。
- [[dcl.inline#2]] 注 1：inline 函数在多个翻译单元中定义，仍然是同一个实体，它里面的 `static` 变量也只有一个。所以 `instance()` 写在类定义里（隐式 inline）、放进头文件，整个程序仍然只有一个 `Logger`。共享库会打破这一点，见后文。

私有的构造函数和析构函数可以阻止外部构造第二个实例或误删实例。`l` 定义在成员函数内部，访问检查在成员函数的上下文中进行，所以私有的析构函数不影响程序退出时销毁 `l`。

### guard 变量的代价

`Logger` 的构造函数不是 `constexpr` 的，`l` 需要动态初始化，编译器要记录它是否已经初始化。Itanium C++ ABI（Linux 和 macOS 上的 GCC、Clang 使用的 ABI）为这样的变量分配一个 8 字节的 **guard 变量**。下面是本机 Clang 23 `-O2 --target=x86_64-linux-gnu` 为一个这样的函数生成的代码，删去了异常表和伪指令：

```cpp
struct Logger { Logger(); int level; };   // 构造函数定义在别处
Logger& meyers() { static Logger l; return l; }
```

```text
_Z6meyersv:
        pushq   %rbx
        movzbl  _ZGVZ6meyersvE1l(%rip), %eax   # 读 guard 的首字节
        testb   %al, %al
        je      .LBB0_1                        # 0：可能还没初始化
.LBB0_4:
        leaq    _ZZ6meyersvE1l(%rip), %rax     # 快路径：返回地址
        popq    %rbx
        retq
.LBB0_1:
        leaq    _ZGVZ6meyersvE1l(%rip), %rdi
        callq   __cxa_guard_acquire@PLT        # 加锁，再查一次
        testl   %eax, %eax
        je      .LBB0_4                        # 别的线程已经初始化完
        leaq    _ZZ6meyersvE1l(%rip), %rdi
        callq   _ZN6LoggerC1Ev@PLT             # 构造
        leaq    _ZGVZ6meyersvE1l(%rip), %rdi
        callq   __cxa_guard_release@PLT        # 标记完成，唤醒等待者
        jmp     .LBB0_4
```

初始化完成之后，每次调用只走快路径：读一个字节、比较、跳转。构造函数抛出时，着陆点调用 `__cxa_guard_abort` 解锁，下次调用重试。`Logger` 的析构函数是平凡的，所以这里没有 `__cxa_atexit`；析构函数不平凡时，`__cxa_guard_release` 前后还会注册一次析构。逐步的解释见 [[stmt.dcl]] 的实现视角部分。

快路径上的读是 acquire 读：看到 guard 已置位的线程，必须同时看到构造函数写入的所有内容。x86-64 上普通的 `mov` 就有 acquire 语义，所以看不出区别；本机 arm64 上这条读是 `ldaprb`，带 acquire 语义的字节读。

如果局部 `static` 对象可以常量初始化，guard 就完全消失。把类型换成 `struct Counter { int n = 0; };`，它的默认构造函数是隐式 `constexpr` 的，同样的函数编译成两条指令：

```text
_Z14constant_localv:
        leaq    _ZZ14constant_localvE1c(%rip), %rax
        retq
```

### 实测：调用开销和循环优化

本机 Apple Silicon（arm64），Clang 23 `-O2`，测了两种场景。

第一种是单独调用一个不内联的访问函数，返回 `meyers().level` 或一个普通全局对象的 `level`，各调用 10⁹ 次。三轮结果都在每次 0.91–0.94 ns 之间，两者没有可分辨的差别。guard 的分支总是走同一边，预测器能完全预测，它的代价被函数调用本身淹没了。

第二种是在循环里使用单例：

```cpp
void scale_meyers(const int* in, int* out, long n) {
  for (long i = 0; i < n; ++i) out[i] = in[i] * meyers().scale;
}
void scale_global(const int* in, int* out, long n) {
  for (long i = 0; i < n; ++i) out[i] = in[i] * global_config.scale;
}
void scale_hoisted(const int* in, int* out, long n) {
  const int k = meyers().scale;    // 循环外取一次
  for (long i = 0; i < n; ++i) out[i] = in[i] * k;
}
```

4096 个 `int`，重复 20 万次，三轮测得每个元素约 0.36 ns、0.048 ns、0.048 ns。Meyers 版本慢了大约 7.5 倍。

汇编说明了原因。`scale_meyers` 的循环体每次迭代都执行一次 `ldaprb` 读 guard、一次条件跳转，然后逐个元素做标量乘法。acquire 读不能被合并或提到循环外，guard 检查后面还挂着一个可能调用 `__cxa_guard_acquire` 的慢路径，编译器无法向量化这个循环。另外两个版本都被向量化成了每次处理 16 个元素的 `mul.4s` 循环。

所以 guard 本身很便宜，昂贵的是它对优化的阻碍。在热循环里使用单例时，先把引用或需要的值取到循环外面。

## 析构顺序与失效引用

Meyers 单例解决了构造顺序，析构顺序的问题随之而来。静态存储期的对象在 `std::exit`（包括从 `main` 返回）时销毁，顺序与构造完成的顺序相反（[[basic.start.term#4]]）。函数内的 `static` 对象在第一次调用时才构造完成，所以它比在它之前构造好的全局对象更早析构。

```cpp run title="dead-reference.cpp" ub
#include <cstdio>
#include <string>
struct Logger {
  std::string prefix = "[app] a prefix long enough to live on the heap: ";
  void log(const char* m) { std::printf("%s%s\n", prefix.c_str(), m); }
  ~Logger() { std::puts("~Logger"); }
};
Logger& logger() { static Logger l; return l; }

struct Session {
  Session() { std::puts("Session()"); }
  ~Session() { logger().log("session closed"); }   // 析构时用单例
};
Session session;                     // main 之前构造完成

int main() { logger().log("hello"); } // l 在这里才构造完成，晚于 session
```

`l` 晚于 `session` 构造完成，于是先于它析构。`session` 的析构函数调用 `logger()`，控制再次经过 `l` 的定义，而 `l` 已经销毁，这是 UB（[[basic.start.term#5]]）。guard 仍然是已初始化状态，`logger()` 不会重新构造它，只会返回一个已经析构的对象的引用。

本机不加 sanitizer 运行，最后一行输出是没有前缀的 `session closed`，`prefix` 已经被析构了。加 `-fsanitize=address` 运行，报告 `heap-use-after-free`：读发生在 `Session::~Session` 调用的 `Logger::log` 中，释放发生在 `Logger::~Logger` 中。

这类问题叫**失效引用**（dead reference）：退出阶段，一个对象的析构函数用到了另一个已经销毁的单例。日志、内存池、统计计数器这类在任何地方都可能被用到的单例最容易遇到。

### 三种对策

第一种是在依赖方的构造函数里先调用一次 `logger()`。把 `Session()` 改成 `Session() { logger(); }`，`l` 就比 `session` 先构造完成，于是后析构。本机 ASan 不再报告，`~Logger` 最后输出。这种办法要求每个使用者都记得这么做，而且只对构造函数里能预见到的依赖有效。

第二种是让单例永不析构。程序退出时操作系统会回收内存、关闭文件描述符，很多单例的析构函数本来就没有必须做的事：

```cpp run title="no-destructor.cpp" ok
#include <cstdio>
#include <new>
#include <string>
#include <utility>

template<class T>
class NoDestructor {               // 构造 T，但永不析构它
  alignas(T) unsigned char buf_[sizeof(T)];
public:
  template<class... Args>
  explicit NoDestructor(Args&&... args) {
    ::new (static_cast<void*>(buf_)) T(std::forward<Args>(args)...);
  }
  NoDestructor(const NoDestructor&) = delete;
  NoDestructor& operator=(const NoDestructor&) = delete;
  T& get() { return *std::launder(reinterpret_cast<T*>(buf_)); }
};                                 // 析构函数平凡：不注册 atexit

struct Logger {
  std::string prefix = "[app] a prefix long enough to live on the heap: ";
  void log(const char* m) { std::printf("%s%s\n", prefix.c_str(), m); }
  ~Logger() { std::puts("~Logger"); }   // 永远不会运行
};

Logger& leaky() {                  // 写法一：堆上分配，故意不释放
  static Logger* p = new Logger;
  return *p;
}
Logger& no_dtor() {                // 写法二：静态存储里构造，不析构
  static NoDestructor<Logger> l;
  return l.get();
}

struct Session {
  ~Session() {
    leaky().log("session closed (leaky)");
    no_dtor().log("session closed (no_dtor)");
  }
} session;

int main() {
  leaky().log("hello");
  no_dtor().log("hello");
}
```

两种写法在 `session` 的析构函数里都能正常使用，ASan + UBSan 不报告错误，`~Logger` 从未输出。LeakSanitizer（`detect_leaks=1`）也不报告 `leaky()` 的那次 `new`，因为对象在退出时仍然可以通过静态变量 `p` 访问到。`-O2` 汇编里整个程序只有一次 `__cxa_atexit`，是为 `session` 注册的。

`NoDestructor` 的版本不分配堆内存，对象就放在静态存储里。它对应 Chromium、Abseil 等代码库中的同名工具。标准库自己也这样处理标准流：`std::cout` 等八个对象在程序执行期间不会被销毁（[[iostream.objects.overview#3]]），所以任何静态对象的析构函数都可以写日志到 `std::cerr`。

永不析构的代价是析构函数里的工作不会发生。如果 `Logger` 有缓冲区，需要在退出前刷新，就要另外安排，比如注册一个 `atexit` 函数只做刷新，或者让 `main` 显式调用。

第三种是让被依赖的对象具有**常量析构**（[[g:constant-destruction|constant destruction]]），即析构可以在常量求值中完成，典型的是析构函数平凡的类型。这样的静态对象排在所有其他静态对象和 `atexit` 回调之后销毁（[[basic.start.term#3]]）。一个 `constinit` 的 `std::atomic<long>` 计数器在任何析构函数里都可以安全读写。

## Nifty counter 与 ios_base::Init

在 Meyers 单例出现之前，iostreams 用另一种办法保证 `std::cout` 在任何用户全局对象构造之前就可用，并且在它们析构之后才失效。这种办法叫 **nifty counter**，也叫 Schwarz counter。

```cpp
// stream.h
struct Stream { /* ... */ };
Stream& stream();                       // 对象存放在 stream.cpp 的缓冲区里
static struct StreamInitializer {       // 每个包含 stream.h 的 TU 一份
  StreamInitializer();                  // 计数器 0→1 时构造 Stream
  ~StreamInitializer();                 // 计数器 1→0 时析构 Stream
} stream_initializer;
```

每个包含 stream.h 的翻译单元都有一个 `stream_initializer`，它的定义出现在该翻译单元中 `#include` 之后定义的全局对象之前，按 [[basic.start.dynamic#3]] 先初始化。计数器是一个零初始化的 `int`，在任何动态初始化之前就是 0，所以无论哪个翻译单元的初始化器先运行，它都能判断自己是不是第一个。析构对称地进行，最后一个初始化器析构时才销毁 `Stream`。完整的可运行代码和逐步解释见 [[basic.start]]。

标准把这个机制写进了 `<iostream>` 的规格：包含 `<iostream>` 的效果，如同它定义了一个静态存储期的 `ios_base::Init` 对象（[[iostream.objects.overview#5]]）。`Init` 的构造函数在八个标准流对象尚未构造时构造它们（[[ios.init]]）。"如同"只规定效果，实现可以用别的方式达到，本机 libc++ 的做法见 [[iostream.objects]]。

今天写新代码很少需要 nifty counter：Meyers 单例或 inline 变量更简单。它的价值在于说明一个思路，用一个排在最前面的辅助对象来控制真正对象的构造时机。

## inline 静态数据成员：最简单的全局

很多所谓的单例只是一个全局变量加上访问控制。C++17 的 inline 变量（[[P0386R2]]）让类的静态数据成员可以直接在类定义里定义（[[class.static.data#4]]），不再需要在某个 .cpp 里另写一行定义：

```cpp ok
#include <atomic>
struct Stats {
  inline static constinit std::atomic<long> requests{0};
};
void on_request() { Stats::requests.fetch_add(1, std::memory_order_relaxed); }
long count() { return Stats::requests.load(std::memory_order_relaxed); }
```

`requests` 是常量初始化的，没有顺序问题；访问它也没有 guard，本机 `-O2` 下 `on_request` 取得地址后直接执行一条 `ldadd` 原子加，没有任何检查。它是 inline 变量，可以放在头文件里被任意多个翻译单元包含，整个程序只有一个。

需要动态初始化的 inline 变量也比普通全局变量好一些。[[basic.start.dynamic#1]] 规定，非模板的 inline 变量是**部分有序**（partially-ordered）初始化。按 [[basic.start.dynamic#3]]，如果 W 的每一个定义之前都有 V 的某个定义，部分有序的 V 就先于 W 初始化。头文件里定义的 inline 变量，在每个包含该头文件的翻译单元里，都出现在头文件之后的全局变量之前：

```cpp title="config.h"
#include <map>
#include <string>
struct Config {
  inline static std::map<std::string, int> values = {   // 动态初始化
    {"port", 8080}, {"threads", 4},
  };
  static int get(const std::string& key) {
    auto it = values.find(key);
    return it == values.end() ? -1 : it->second;
  }
};
```

```cpp title="b.cpp" ok
#include <cstdio>
#include "config.h"
extern int threads;                    // 定义在 a.cpp，同样包含 config.h
int port = Config::get("port");        // 本 TU 中排在 Config::values 之后
int main() { std::printf("port = %d, threads = %d\n", port, threads); }
```

另一个文件 a.cpp 包含同一个头文件，定义 `int threads = Config::get("threads");`。本机两种链接顺序都输出 `port = 8080, threads = 4`，ASan 在 `strict_init_order=1` 下也不报告。对比开头的 `config.cpp`，差别只是 `map` 的定义从一个 .cpp 移进了被使用者包含的头文件。

这个保证只覆盖包含了定义的翻译单元。如果某个翻译单元没有包含 config.h，只是调用另一个 .cpp 中的函数间接读取 `values`，这个翻译单元里的全局变量就得不到保证。类模板的静态数据成员也不适用，它们是无序初始化。

## 跨共享库的单例

标准描述的是一个程序，没有共享库的概念。[[dcl.inline#2]] 说 inline 函数中的 `static` 变量只有一个，前提是整个程序被当成一个整体链接；动态库各自链接、在运行时装载，一个实体可能在每个库里各有一份。

下面在本机 macOS 上做实验。头文件里有一个 inline 的 Meyers 单例 `registry()` 和一个 inline 变量 `instances`；两个动态库 liba、libb 各有一个函数往 `registry()` 里添加一项并递增 `instances`；主程序依次调用这两个函数，然后读 `registry()` 和 `instances`：

| 构建方式 | 主程序看到的结果 | 单例的份数 |
|---|---|---|
| 默认可见性 | 2 项，`instances = 2` | 1 |
| 两个库都用 `-fvisibility=hidden` | 0 项，`instances = 0` | 3（主程序、liba、libb 各一份） |
| 非 inline 的 `registry()` 放在静态库里，两个库各自链接它 | 1 项 | 2 |

默认可见性下，`nm -m` 显示 guard、对象和 `instances` 都是 `weak external` 符号，dyld 在装载时把各镜像中同名的弱定义合并成一个，所以只有一份。`-fvisibility=hidden` 把它们变成了各库私有的符号，每个库用自己的那份，主程序的那份始终没人写入。第三种情况的每个库里都静态链接了一份 `registry()` 的定义，macOS 的两级命名空间让每个库调用自己的那一份；主程序则绑定到它链接时找到的第一个库。

Linux（ELF）的规则不同，默认可见的符号可以被可执行文件或先装载的库中的同名符号插入（interpose），见 [[toolchain/linking-and-symbols]]。本页没有在 Linux 上实测，具体结果取决于可见性、`-Bsymbolic` 一类链接选项和 `dlopen` 的标志。

几条在各平台上都成立的建议：

- 一个单例只在一个共享库里定义，定义成非 inline 的导出函数，其他库通过这个库的接口取得它；
- 不要把同一个含单例的静态库链接进多个共享库；
- 头文件中的 inline 单例和 inline 变量，只在确认相关符号默认可见时才能跨库共享，而 `-fvisibility=hidden` 正是很多项目的默认设置。

注册表一类的单例最容易受影响：插件里的自注册对象把自己登记到了插件私有的那份注册表里，主程序看到的是空表。这类模式见 [[patterns/factory-and-registration|工厂与自注册]]。

## 测试与依赖注入

单例最常被批评的一点是难以测试。

<div class="compare" markdown="1">

```cpp
class SystemClock {
public:
  static SystemClock& instance();
  std::int64_t now_ms() const;
};
bool expired(std::int64_t expiry_ms) {
  return SystemClock::instance().now_ms()
         > expiry_ms;  // 测试无法控制时间
}
```

```cpp
struct Clock {
  virtual std::int64_t now_ms() const = 0;
protected:
  ~Clock() = default;
};
class TokenChecker {
  const Clock& clock_;   // 由调用方注入
public:
  explicit TokenChecker(const Clock& c)
    : clock_(c) {}
  bool expired(std::int64_t e) const {
    return clock_.now_ms() > e;
  }
};
```

</div>

左边的 `expired` 从函数签名上看不出它依赖时钟，测试只能等真实时间流逝。单例的状态还会在测试用例之间残留，一个用例写入的配置会影响下一个用例；并行运行的测试共享同一个实例。

右边把依赖作为构造函数参数传入，这种做法叫**依赖注入**（dependency injection）。测试时传入一个假的时钟：

```cpp run title="di.cpp" ok
#include <cassert>
#include <chrono>
#include <cstdint>

struct Clock {
  virtual std::int64_t now_ms() const = 0;
protected:
  ~Clock() = default;
};

struct SystemClock final : Clock {
  std::int64_t now_ms() const override {
    using namespace std::chrono;
    return duration_cast<milliseconds>(
        system_clock::now().time_since_epoch()).count();
  }
};

class TokenChecker {
  const Clock& clock_;
public:
  explicit TokenChecker(const Clock& c) : clock_(c) {}
  bool expired(std::int64_t expiry_ms) const {
    return clock_.now_ms() > expiry_ms;
  }
};

struct FakeClock final : Clock {
  std::int64_t t = 0;
  std::int64_t now_ms() const override { return t; }
};

int main() {
  FakeClock clock;
  TokenChecker checker(clock);
  clock.t = 1000;
  assert(!checker.expired(1500));
  clock.t = 2000;                      // 时间由测试控制
  assert(checker.expired(1500));

  static SystemClock system_clock;     // 生产代码：在组装处只建一个
  TokenChecker real(system_clock);
  return real.expired(0) ? 0 : 1;
}
```

只有一个实例这件事并没有消失，它从类的约束变成了程序组装处（通常是 `main`）的决定。`TokenChecker` 不关心时钟有几个，也不关心它什么时候构造、什么时候销毁；对象的生存期由组装处的作用域决定，退出阶段的顺序问题也随之消失。

`Clock` 的析构函数是受保护的非虚函数：`TokenChecker` 只借用时钟，从不通过 `Clock*` 删除它，所以不需要虚析构函数。注入的是引用，调用方要保证时钟活得比 `TokenChecker` 长，这类生存期问题见 [[topics/dangling-references]]。

虚函数调用有一次间接跳转的代价。依赖在编译期就确定时，可以把它作为模板参数注入，`TokenChecker<FakeClock>` 和 `TokenChecker<SystemClock>` 各自生成代码，调用可以内联，见 [[patterns/policy-based-design|基于策略的设计]]。

还有一种折中，保留全局访问点，但允许测试替换实例，例如 `Clock& clock()` 返回一个可以被 `set_clock(Clock*)` 改写的指针所指的对象。这种做法通常称为服务定位器（service locator）。它改动最小，但依赖仍然藏在函数体里，测试结束要记得恢复，并行测试仍然共享它。

## 怎样选择

| 需求 | 做法 |
|---|---|
| 全局常量或可以在编译期构造的全局状态 | `constexpr` 或 `constinit` 变量，类内用 `inline static constinit` |
| 需要动态初始化，使用者都包含定义所在的头文件 | inline 变量（部分有序初始化） |
| 需要动态初始化、惰性构造，可能被其他全局对象的构造函数使用 | Meyers 单例 |
| 还可能被其他静态对象的析构函数使用 | 永不析构的单例（`NoDestructor` 或故意泄漏） |
| 在热循环中访问 | 循环外取引用，或改用常量初始化的变量 |
| 跨共享库只能有一份 | 在一个库里定义非 inline 的导出访问函数 |
| 需要在测试中替换，或实例的个数和生存期应由使用方决定 | 依赖注入，不用单例 |

一个对象之所以是唯一的，往往只是因为当前的程序碰巧只需要一个。数据库连接、配置、时钟都属于这一类，将来很可能需要第二个（测试替身、多租户、多个配置源）。真正必须唯一的对象，比如表示进程本身的资源（标准流、进程级的内存分配器），才适合做成单例。

## 思考题

!!! question "1"
    开头的 `config.cpp` 如果把 `std::map` 换成一个带 `constexpr` 构造函数的类 `Config { int port; constexpr Config() : port(8080) {} };`，不写 `constinit`，`server.cpp` 的结果还取决于链接顺序吗？

<details markdown="1">
<summary>答案</summary>

不取决于。初始化器调用的是 `constexpr` 构造函数，整个初始化是常量表达式，变量是常量初始化的（[[expr.const.init]]），属于静态初始化，先于任何动态初始化完成（[[basic.start.static#2]]）。本机 `-O2` 的汇编里，`config` 直接以 `.long 8080` 出现在数据段中，没有任何初始化函数。

`constinit` 不影响这个结论，它的作用是把常量初始化从一个事实变成一个检查：以后有人给 `Config` 的构造函数加了一行非 `constexpr` 的代码，不写 `constinit` 时程序悄悄回到动态初始化，写了则编译失败。
</details>

!!! question "2"
    `dead-reference.cpp` 中，把 `Session` 的构造函数改成 `Session() { logger(); }`，为什么就不再是 UB？如果 `session` 的构造函数没有调用 `logger()`，而是 `main` 在构造任何东西之前调用了它，结论一样吗？

<details markdown="1">
<summary>答案</summary>

析构顺序由构造完成的先后决定（[[basic.start.term#4]]）。`Session()` 里调用 `logger()`，`l` 在 `Session` 的构造函数执行期间构造完成，早于 `session` 构造完成，所以 `l` 在 `session` 之后析构，`~Session` 使用它时它还活着。本机 ASan 不报告，`~Logger` 最后输出。

第二种情况不一样。`session` 是全局对象，在 `main` 开始之前已经构造完成，`main` 里第一次调用 `logger()` 一定晚于它，`l` 仍然会先析构。决定顺序的是两个对象各自构造完成的时刻，而不是谁先被使用。
</details>

!!! question "3"
    `scale_meyers` 的循环中，`meyers()` 已经在第一次迭代中完成初始化，为什么编译器不能把 guard 检查提到循环外，只检查一次？

<details markdown="1">
<summary>答案</summary>

guard 的读是 acquire 读，是一个原子操作。按 C++ 内存模型，另一个线程可能在任何时刻完成初始化并发布结果，编译器不能把多次 acquire 读合并成一次，否则就改变了程序可能观察到的同步关系。此外慢路径会调用外部函数 `__cxa_guard_acquire` 和构造函数，编译器不知道它们会不会修改 `in` 和 `out` 指向的内存，也就不能把循环向量化。

在循环外手动取一次 `meyers().scale`，就把 guard 检查移到了循环外。本机测得这样写与普通全局变量的速度相同，约 0.048 ns 每元素。
</details>

## 小结

| 问题 | 结论 | 出处 |
|---|---|---|
| 不同 TU 的全局对象谁先初始化 | 不定序，结果可能随链接顺序变化 | [[basic.start.dynamic#3]] |
| 常量初始化的变量 | 先于一切动态初始化，没有顺序问题；`constinit` 强制检查 | [[basic.start.static#2]]、[[dcl.constinit#2]] |
| 局部 `static` 对象何时初始化 | 第一次经过声明时，线程安全，异常后重试 | [[stmt.dcl#3]] |
| 头文件中 inline 函数里的 `static` | 整个程序一份，但共享库可能打破这一点 | [[dcl.inline#2]] |
| guard 的代价 | 快路径一次 acquire 读；会阻止循环外提和向量化 | 本机实测 |
| 静态对象的析构顺序 | 构造完成的逆序；使用已析构的局部 `static` 是 UB | [[basic.start.term#4]]、[[basic.start.term#5]] |
| 头文件里定义的 inline 变量 | 部分有序，先于包含它的 TU 中其后定义的变量 | [[basic.start.dynamic#1]]、[[basic.start.dynamic#3]] |
| `<iostream>` 的标准流 | 如同每个 TU 有一个 `ios_base::Init`；不会被销毁 | [[iostream.objects.overview#3]]、[[iostream.objects.overview#5]] |
