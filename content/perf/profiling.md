---
title: 用剖析器找热点
summary: 优化之前先找出时间花在哪里：采样与插桩的区别，为剖析构建程序（-O2 -g、帧指针，为什么 -O0 的剖析结果不可信），macOS 上的 sample、Instruments 与 dtrace，Linux 上的 perf，怎样读调用树、火焰图和内联帧，硬件计数器能补充什么，以及修掉热点之后用阿姆达尔定律核对收益。
group: 测量
status: draft
order: 15
since: c++11
related: intro.abstract, temp.explicit, time.clock, perf/measuring, perf/reading-assembly, perf/compiler-optimizations, perf/choosing-containers, perf/memory-hierarchy, perf/allocation, toolchain/compilation-pipeline, toolchain/linking-and-symbols
tags: 性能, 剖析, profiler, sample, perf, Instruments, 火焰图, 阿姆达尔定律
updated: 2026-10-19
---

!!! tldr
    - 剖析器回答时间花在哪里。采样剖析器每隔固定时间记录一次调用栈，开销小，结果是统计估计；插桩在函数入口和出口插入代码，计数精确，但会改变被测程序。
    - 剖析要用接近发布的构建：`-O2` 加调试信息。`-O0` 的程序没有内联，剖析结果里排在前面的是一堆在 `-O2` 下根本不存在的小函数。
    - 本机的词频统计程序里，猜测中的内存分配几乎没有出现；66% 的样本落在 `std::map` 的查找上，其中一半以上是比较字符串的 `memcmp`。
    - 剖析结果给出每一部分的占比 p，阿姆达尔定律据此给出上限：这部分即使不花时间，整体也最多快 1/(1−p) 倍。改完要重新测量，下一个热点通常换了位置。
    - 硬件计数器告诉你一段代码慢在缓存缺失还是分支预测失败。macOS 上要通过 Instruments 读取，Linux 上用 `perf stat`。

本节的数字都来自 Apple M2 Pro，macOS 26.5，Homebrew Clang 23.1.3 + libc++，arm64。写作期间这台机器的负载很重（12 个核心上 load average 在 30 到 100 之间），绝对时间偏慢、偏散。下文更依赖剖析结果里的百分比和同一进程中背靠背测得的比值；换一台机器、换一个编译器，数字都会变。测量方法见 [[perf/measuring|怎样测量才可信]]。

## 一个慢得出乎意料的程序

下面的程序生成 500 万个词的文本，统计每个词出现的次数，打印出现最多的五个。每个阶段用一个计时器对象包起来，析构时打印耗时。

```cpp title="wordfreq.cpp" run ok
// wordfreq.cpp：统计词频，打印出现最多的 5 个词
#include <algorithm>
#include <cctype>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <map>
#include <sstream>
#include <string>
#include <vector>

struct ScopedTimer {                 // 析构时打印经过的时间
  const char* name;
  std::chrono::steady_clock::time_point t0 =
      std::chrono::steady_clock::now();
  ~ScopedTimer() {
    std::chrono::duration<double, std::milli> d =
        std::chrono::steady_clock::now() - t0;
    std::fprintf(stderr, "%-7s %8.1f ms\n", name, d.count());
  }
};

// 约 n 个词的合成文本：词表 5 万个词，少数词出现得特别多
std::string make_corpus(std::size_t n) {
  std::vector<std::string> vocab;
  for (int i = 0; i < 50000; ++i)
    vocab.push_back("Word" + std::to_string(i * 7919 % 100003));
  std::string text;
  std::uint64_t s = 42;
  for (std::size_t i = 0; i < n; ++i) {
    s = s * 6364136223846793005u + 1442695040888963407u;
    double u = double(s >> 11) / double(1ull << 53);  // [0, 1)
    text += vocab[std::size_t(u * u * u * vocab.size())];
    text += (i % 12 == 11) ? ".\n" : " ";
  }
  return text;
}

using Counts = std::map<std::string, int>;

Counts count_words(const std::string& text) {
  Counts counts;
  std::istringstream in(text);
  std::string w;
  while (in >> w) {
    std::string clean;
    for (char c : w)
      if (std::isalnum(static_cast<unsigned char>(c)))
        clean += char(std::tolower(static_cast<unsigned char>(c)));
    if (!clean.empty()) ++counts[clean];
  }
  return counts;
}

int main() {
  std::string text;
  Counts counts;
  std::vector<std::pair<std::string, int>> top;
  { ScopedTimer t{"corpus"}; text = make_corpus(5'000'000); }
  { ScopedTimer t{"count"};  counts = count_words(text); }
  {
    ScopedTimer t{"top5"};
    top.assign(counts.begin(), counts.end());
    std::partial_sort(top.begin(), top.begin() + 5, top.end(),
        [](auto& a, auto& b) { return a.second > b.second; });
  }
  for (int i = 0; i < 5; ++i)
    std::printf("%-10s %d\n", top[i].first.c_str(), top[i].second);
}
```

用 `clang++ -std=c++2c -O2 -gdwarf-4 -fno-omit-frame-pointer wordfreq.cpp -o wordfreq` 构建（这几个选项下一节解释）。本机多次运行，`corpus` 在 70 到 110 ms 之间，`count` 在 1.0 到 1.7 s 之间，`top5` 只有 1 到 3 ms。时间几乎全在 `count_words` 里。

这个函数里有三件事可能慢：`istringstream` 逐词读取，每个词新建一个 `std::string clean`，以及 `std::map` 的查找。常见的直觉是每个词都分配一次内存，所以分配最贵。这个猜测是错的，剖析器给出的答案见下文。

## 采样与插桩

**剖析器**（profiler）测量程序的时间分布在哪些函数、哪些源代码行上。它有两种基本做法。

**采样**（sampling）每隔一段固定时间（比如 1 ms）打断程序，记录当前的调用栈，最后统计每个函数、每一行出现在多少个样本里。一个函数占 30% 的样本，就估计它占 30% 的时间。程序本身不需要改动，开销通常只有几个百分点。代价是结果是统计估计：n 个样本里占比 p 的部分，标准误差约为 √(p(1−p)/n)。1700 个样本、p = 0.66 时约为 1.1 个百分点。很短的函数如果只是偶尔被调用，可能一个样本都落不到。

**插桩**（instrumentation）在函数入口和出口（或者你选定的代码段）插入计时或计数代码。它给出精确的调用次数，不会漏掉短函数。代价是插入的代码本身要花时间，被测的函数越小、调用越频繁，测到的就越不像原来的程序。上面的 `ScopedTimer` 就是手写的插桩。

| | 采样 | 插桩 |
|---|---|---|
| 需要改程序吗 | 不需要，只需调试信息 | 要重新编译或改代码 |
| 开销 | 小，和样本频率有关 | 和插桩点被执行的次数成正比 |
| 结果 | 时间占比的估计 | 精确的次数和区间耗时 |
| 适合 | 第一步：时间去了哪里 | 确认某一段的耗时、数调用次数 |
| 本机工具 | `sample`、Instruments Time Profiler | 计时器、`-finstrument-functions` |

一般先用采样找出大致位置，再在那里加计时器确认。

## 为剖析构建程序

剖析要测的是将来真正运行的那份机器码，所以优化级别要和发布构建一致，通常是 `-O2`。另外还要加两类信息，让剖析器能把地址翻译回源代码。

### 调试信息：`-g`

`-g` 让编译器生成调试信息（DWARF），记录每条指令对应的源文件和行号，以及哪些指令是从哪个函数内联进来的。它不改变生成的代码，只增加可执行文件旁边的数据。没有它，剖析器只能报告函数名（来自符号表），报告不了行号。

本机遇到一个具体问题。Homebrew Clang 23 默认生成 DWARF 5，而系统链接器 ld64-530 读不懂它，链接时打印 `ld: warning: can't parse dwarf compilation unit info`，之后 `sample` 的输出里就没有行号。改用 `-gdwarf-4` 后行号正常。这是本机工具链版本不匹配造成的，和 C++ 无关。

### 帧指针

采样时剖析器要沿着调用栈一路往回走，找出当前函数是被谁调用的。最简单的办法是靠**帧指针**（frame pointer）：每个函数开头把上一层的帧指针存进自己的栈帧，于是栈帧连成一条链表。编译器为了多一个可用寄存器，可以省掉这一步。

```cpp title="fp.cpp"
void g(int);
void f(int x) { g(x); g(x + 1); }
```

本机分别为三个目标用 `-O2 -S` 编译这两行，结果如下：

| 目标 | 默认 | `-fno-omit-frame-pointer` |
|---|---|---|
| arm64 macOS | 建立帧链（`stp x29, x30` 后 `add x29, sp, #16`） | 相同 |
| aarch64 Linux（`--target=aarch64-linux-gnu`） | 建立帧链（`mov x29, sp`） | 相同 |
| x86-64 Linux（`--target=x86_64-linux-gnu`） | 不出现 `%rbp` | `pushq %rbp` 后 `movq %rsp, %rbp` |

Apple 的 arm64 ABI 要求保留帧指针，所以在本机这个选项不改变代码，加上只是为了让构建命令在各平台通用。x86-64 Linux 上 `-O2` 默认省略帧指针，用 `perf` 剖析时要么加 `-fno-omit-frame-pointer`，要么改用基于 DWARF 的栈回溯（见下文 `perf` 一节）。系统库是否保留帧指针由发行版决定，库里的栈断了，调用树就会缺层。

### 为什么 `-O0` 的剖析结果不可信

把同一个程序用 `-O0` 编译再采样，按源代码行统计，`++counts[clean]` 那一行占 64%，和 `-O2` 差不多。按函数统计就完全变了样：

| 按函数自身耗时排序 | `-O2` | `-O0` |
|---|---|---|
| 第一名 | `_platform_memcmp`，约 47% | `std::basic_string::__get_pointer()`，约 14% |
| `memcmp` 的占比 | 约 47% | 约 5% |
| 至少有 5 个样本的函数个数 | 13 | 78 |

`-O0` 不做内联，`std::string` 的每个访问器、`std::map` 的每层比较器适配器、`streambuf` 的每次取字符都是真正的函数调用，各自分到一份样本。`__get_pointer()` 在 `-O2` 下被内联成一两条指令，根本不是一个函数。照着 `-O0` 的结果去优化 `__get_pointer`，在发布构建里不会有任何效果。`-O0` 的程序本身也慢一个数量级以上（本机在高负载下 `count` 阶段 15 到 26 s，同期 `-O2` 为 1 到 2 s），各部分变慢的倍数不同，占比因此也不可信。

[[intro.abstract#1]] 说实现只需要模拟抽象机的[[g:observable-behavior|可观察行为]]，不需要照搬它的结构。这一条通常称为 [[g:as-if-rule|as-if 规则]]，它允许编译器把十几层函数调用压成一个循环。剖析器看到的是编译之后的机器码，所以只有剖析真正要发布的那份机器码才有意义。内联的细节见 [[perf/compiler-optimizations|编译器做了哪些优化]]。

## 在 macOS 上采样

### `sample`

`sample` 是 macOS 自带的命令行采样器，可以附加到一个正在运行的进程上，不需要 root 权限。下面让程序在后台运行，0.3 秒后（文本已经生成完）开始采样 2 秒，每 1 ms 一次：

```text
$ ./wordfreq > /dev/null & sleep 0.3; sample $! 2 1 -mayDie -file s.txt
```

`-mayDie` 让 `sample` 在进程提前退出时先把符号信息读好。输出分两部分。第一部分是**调用树**（call tree）。下面是本机一次运行的节选，模板名做了缩写，删去了地址：

```text
Call graph:
  1703 main  (in wordfreq) + 212  wordfreq.cpp:60
    1118 count_words(...)  (in wordfreq) + 420  wordfreq.cpp:50
    + 827 __tree<...>::__emplace_unique<...>::'lambda'  __tree:1079
    + ! 800 _platform_memcmp  (in libsystem_platform.dylib)
    + ! 27 DYLD-STUB$$memcmp  (in wordfreq)
    + 289 __tree<...>::__emplace_unique<...>::'lambda'  __tree:1079
    375 count_words(...)  (in wordfreq) + 224  wordfreq.cpp:45
    + 91 std::operator>><char>(basic_istream&, basic_string&)  istream:...
    ...
```

每一行开头的数字是落在这个栈帧及其下方的样本数。同一个函数按不同的返回地址分成不同的行，所以 `count_words` 出现了多次，行号指出是函数里的哪一处调用。第 50 行 `++counts[clean]` 占 1703 个样本中的 1118 个（66%），第 45 行 `in >> w` 占 375 个（22%），第 48、49 行逐字符清洗合计约 7%。

第二部分按**自身耗时**（self time）排序，即样本落在这个函数自己的指令上、而不是它调用的函数里：

```text
Sort by top of stack, same collapsed (when >= 5):
    _platform_memcmp  (in libsystem_platform.dylib)          800
    __tree<...>::__emplace_unique<...>::'lambda'  (in wordfreq)  292
    std::operator>><char>(basic_istream&, basic_string&)     243
    std::basic_string<char>::push_back(char)  (in libc++.1.dylib)  119
    count_words(...)  (in wordfreq)                          76
    std::basic_istream<char>::sentry::sentry(...)  (in libc++.1.dylib)  62
    ...
```

结论很清楚：`std::map` 的查找占了大头，其中一半以上是比较两个字符串的 `memcmp`。每个词最多 9 个字符，比 libc++ 中 SSO（短字符串优化，短字符串直接存在 `std::string` 对象内部）的容量 22 个字符小，所以 `std::string clean` 不分配内存，`malloc` 根本没有出现在列表里。在 5 万个键的平衡树里查找，每次大约比较 16 次，每次比较都是一次对 `memcmp` 的库函数调用，还要读取一个可能不在缓存里的树节点。

`DYLD-STUB$$memcmp` 是调用动态库函数时经过的跳板代码：可执行文件里的 `bl` 先跳到这段桩代码，再由它跳到 `libsystem_platform.dylib` 中真正的 `memcmp`。动态链接的细节见 [[toolchain/linking-and-symbols|链接与符号]]。

`sample` 记录的是每个线程当时所在的调用栈，阻塞在系统调用、等待 I/O 或锁的线程也会被计入。这个程序是单线程、纯计算的，两者没有区别。

### Instruments 与 `xctrace`

Instruments 是 Xcode 附带的图形化剖析工具，其中的 Time Profiler 模板只在线程实际占用 CPU 时取样，能按线程、按时间段筛选，并把调用树显示成可以展开的表格。命令行版本是 `xctrace`：

```text
$ xctrace record --template 'Time Profiler' --output wf.trace --launch -- ./wordfreq
```

得到的 `.trace` 文件用 Instruments 打开。本机装的是 xctrace 16.0，在 macOS 26.5 上加载 Instruments 的设备插件失败，打印 `Failed to look up symbolic reference ... is likely a reference to a missing weak symbol`，不生成可读的 trace。看起来是 Xcode 版本和系统不匹配，因此本页没有 Instruments 的输出。

### dtrace

dtrace 可以写脚本按任意事件采样，例如 `dtrace -n 'profile-997 /pid == $target/ { @[ustack()] = count(); }' -c ./wordfreq` 每秒在该进程上取样 997 次并按用户态调用栈计数。本机开启了系统完整性保护（SIP），普通用户运行时报告 `DTrace requires additional privileges`，需要 root 权限，部分功能在 SIP 下仍不可用。日常剖析用 `sample` 或 Instruments 即可。

## 在 Linux 上：perf

Linux 上的标准工具是 `perf`，它直接读取内核和 CPU 的性能计数器。本机是 macOS，下面的命令没有在本机运行，只说明各自做什么：

- `perf record -g ./wordfreq` 按 CPU 时钟采样，`-g` 同时记录调用栈（靠帧指针回溯）。程序没有帧指针时，改用 `perf record --call-graph dwarf`，它在每个样本里复制一段栈内存，事后用 DWARF 调试信息回溯，数据量大得多。
- `perf report` 读取生成的 `perf.data`，交互式地显示按函数排序的表。默认的 Children 列是包含被调用函数在内的总耗时，Self 列是自身耗时，`--no-children` 只按自身耗时排序。
- `perf annotate` 把样本对应到每条汇编指令上，可以看出一个函数里具体哪几条指令最热。
- `perf stat ./wordfreq` 不记录调用栈，只统计整个运行过程中的计数器总数，见下文硬件计数器一节。

## 读调用树和火焰图

### 总耗时与自身耗时

调用树上的每个节点有两个数字。**总耗时**（total，或 inclusive）是落在这个函数以及它直接、间接调用的所有函数中的样本；**自身耗时**（self，或 exclusive）只算样本恰好停在这个函数自己的指令上。`main` 的总耗时接近 100%，自身耗时几乎是 0。

找热点通常从总耗时往下走：从 `main` 开始，每次展开总耗时最大的子节点，直到某个节点的总耗时主要由自身耗时构成，或者分散到许多子节点上。上面的例子里，路径是 `main` → `count_words` 第 50 行 → `__emplace_unique` → `memcmp`。只看自身耗时的排名容易误判：`memcmp` 排第一，但真正该改的不是 `memcmp`，而是调用它约 8000 万次（500 万次查找，每次约 16 次比较）的那一行。

### 火焰图

**火焰图**（flame graph）把同一棵调用树画成一张图：每个栈帧是一个横条，宽度和它的总耗时成正比，被调用者叠在调用者上面。横向的先后顺序通常按函数名排列，不代表时间顺序。宽而平的顶部就是自身耗时大的函数。

画火焰图需要先把样本整理成每行一个完整调用栈加计数的折叠格式，例如 `main;count_words;__emplace_unique;memcmp 800`，再交给绘图工具。Brendan Gregg 的 FlameGraph 脚本和 speedscope 等工具都接受 `perf script` 的输出。它和调用树表达的是同一份数据，区别只在于一眼能看出整体形状。

### 内联帧

`sample` 报告样本落在 `__emplace_unique` 的 lambda 里，但源代码里根本没有写这个 lambda，查找、比较的代码都内联进了它。机器码里只有一个函数，调试信息却记录了每条指令来自哪一层被内联的函数。`atos -i` 可以把这些层展开。取 `memcmp` 调用指令的地址：

```text
$ atos -o wordfreq.dSYM/Contents/Resources/DWARF/wordfreq -l 0x1023cc000 -i 0x1023d2c2c
```

`-l` 是 `sample` 输出头部的 Load Address。结果是同一个地址上的 9 层栈帧，从内到外（名字做了缩写）：

```text
std::char_traits<char>::compare                   char_traits.h:126
std::basic_string_view<char>::compare             string_view:483
std::operator<=>(basic_string_view, basic_string_view)   string_view:772
std::operator<=>(const string&, const string&)    string:3538
std::__default_three_way_comparator<string, string>      default_three_way_comparator.h:51
std::__lazy_synth_three_way_comparator<less<void>, ...>  lazy_synth_three_way_comparator.h:99
std::__lazy_synth_three_way_comparator<__map_value_compare<...>, ...>  map:708
std::__tree<...>::__find_equal<string>            __tree:1960
std::__tree<...>::__emplace_unique<...>::'lambda'  __tree:1079
```

这 9 层在运行时只是一条 `bl memcmp` 和它前后的几条指令。Linux 上 `perf report --inline` 和 `llvm-symbolizer --inlining` 做同样的事。展开之后，剖析结果可以按源代码的结构阅读，同时要记住这些层没有调用开销。

反过来，有些看起来应该内联的函数并没有内联。剖析结果里 `std::basic_string<char>::push_back(char)` 带着 `(in libc++.1.dylib)`，前面还有 `DYLD-STUB$$`，说明每次 `clean += c` 都是一次跨动态库的函数调用；`-O2 -S` 的汇编里也能看到 `bl` 到 `push_back`。原因是 libc++ 用显式实例化声明（`extern template`，[[temp.explicit#2]]）把 `basic_string<char>` 的一批成员函数放在共享库里实例化，`push_back` 在名单上。按 [[temp.explicit#12]] 的注解，这类声明对内联函数没有其他规范效力，是否内联完全由编译器决定；本机这次构建没有内联它。

## 硬件计数器

采样告诉你时间花在哪一行，但不说明为什么慢。`memcmp` 的 800 个样本里，有多少是在比较字节，有多少是在等树节点从内存里读进来？采样剖析器分不出来，因为等待缓存缺失的时间也算在发出读取的那条指令上。

CPU 内部有**性能监视计数器**（performance monitoring counters），可以统计执行的周期数、指令数、各级缓存缺失、分支预测失败等事件。两个常用的派生指标是 IPC（每周期执行的指令数）和每千条指令的缓存缺失数。IPC 很低、缓存缺失很多，说明瓶颈在内存访问，应该改数据布局（见 [[perf/memory-hierarchy|内存层次]]）；分支预测失败多，见 [[perf/branches|分支]]。

在 Linux 上，`perf stat -e cycles,instructions,cache-misses,branch-misses ./wordfreq` 直接给出这些计数，`perf record -e cache-misses` 还能按缺失事件采样，找出缺失大致发生在哪一行。可用的事件名取决于 CPU 型号，`perf list` 会列出。

在 macOS 上，普通用户没有命令行工具能读这些计数器。Instruments 有 CPU Counters 模板（`xctrace list templates` 能列出它），用来读取 Apple 芯片的计数器。本机的 Instruments 无法运行（见上文），所以本页没有给出缓存缺失的数据，`memcmp` 里有多少时间在等内存，这里只能存疑。

## 插桩

### 作用域计时器

`ScopedTimer` 利用析构函数在作用域结束时自动执行这一点（见 [[patterns/raii|RAII]]），用两次 `steady_clock::now()` 量出一个块的耗时。[[time.clock.steady#1]] 规定这个时钟的值随物理时间单调不减，并且相对真实时间匀速前进，所以不受系统时间被调整的影响。它的开销是两次读时钟，本机一次十几纳秒，放在毫秒级的代码段外面可以忽略，放在每次只跑几十纳秒的循环体里就会主导结果。时钟的精度和开销见 [[perf/measuring|怎样测量才可信]]。

### `-finstrument-functions`

GCC 和 Clang 的 `-finstrument-functions` 在每个函数的入口和出口插入对 `__cyg_profile_func_enter` 和 `__cyg_profile_func_exit` 的调用，由你提供这两个函数。下面的版本只计数：

```cpp title="hooks.cpp" ok
// hooks.cpp：-finstrument-functions 的回调，只统计调用次数
#include <cstdio>
static unsigned long long calls = 0;
extern "C" {
__attribute__((no_instrument_function))
void __cyg_profile_func_enter(void*, void*) { ++calls; }
__attribute__((no_instrument_function))
void __cyg_profile_func_exit(void*, void*) {}
}
struct Report {
  __attribute__((no_instrument_function))
  ~Report() { std::fprintf(stderr, "instrumented calls: %llu\n", calls); }
} report;
```

`no_instrument_function` 防止回调自己被插桩，否则会无限递归。把 `hooks.cpp` 不加插桩选项编译，再和插桩过的 `wordfreq.cpp` 链接，本机在高负载下运行一次的结果：

| 构建 | 插桩调用次数 | `count` 阶段 |
|---|---|---|
| 不插桩（同一时段） | 0 | 约 2.3 s |
| `-finstrument-functions` | 6 190 878 981 | 25.7 s |
| `-finstrument-functions-after-inlining` | 10 100 061 | 2.5 s |

Clang 的 `-finstrument-functions` 在内联之前插桩，`std::string`、`std::map` 里每个本该被内联掉的小函数都多了两次调用，程序慢了十倍以上，测到的已经是另一个程序。`-finstrument-functions-after-inlining` 只给内联之后仍然存在的函数插桩，次数少了 600 倍，开销小得多。即便如此，函数级插桩也只适合数调用次数、做调用追踪，不适合测时间占比，那是采样的事。

## 修掉热点，再测一遍

### 阿姆达尔定律

如果程序中占时间比例 p 的部分被加速 s 倍，其余部分不变，整体的加速比是

S = 1 / ((1 − p) + p / s)

这就是**阿姆达尔定律**（Amdahl's law）。s 趋于无穷时，S 的上限是 1 / (1 − p)。剖析结果给出的就是 p。`std::map` 查找占 `count_words` 的 66%，即使把查找变得不花时间，`count_words` 最多快 1 / 0.34 ≈ 2.9 倍；而第 49 行的清洗只占约 4%，把它优化到零，最多快 4%。

### 第一步：换掉 `std::map`

词频统计不需要按键排序，`std::map` 改成 `std::unordered_map` 只需改 `Counts` 的定义。哈希表查找时先算一次哈希，通常只需比较一两次字符串，而不是十几次。

为了减少噪声，下面的数字来自同一份源码的另一个 `main`：先生成一次文本，再在同一个进程里把 `count_words` 连续运行 11 次，取中位数和最小值。结果被检查（键的个数必须是 50000），所以 as-if 规则不能把调用删掉。三个版本交替运行了六轮，负载较轻时测得的最小值是：

| 版本 | `count_words` 最小值 | 相对 v1 |
|---|---|---|
| v1：`std::map` + `istringstream` | 1065 ms | 1.00 |
| v2：`std::unordered_map` + `istringstream` | 596 ms | 1.79 倍 |
| v3：`std::unordered_map` + 手写分词 + `reserve` | 353 ms | 3.0 倍 |

负载重的几轮里三者都变慢，最慢的一轮 v1 的中位数达 4.2 s。按每轮的最小值，v1 > v2 > v3 的顺序始终成立；按中位数，有一轮 v2 反而比 v1 慢，这就是负载造成的噪声。之后又交替测了三轮，中位数分别在 1090–1221、605–744、366–395 ms 之间，比值和上表一致。小于百分之十几的差异在这样的环境下没有意义。

用阿姆达尔定律核对 v2：1065 ms 里不属于查找的部分约为 0.34 × 1065 ≈ 362 ms。v2 测得 596 ms，说明查找从约 703 ms 降到约 234 ms，快了约 3 倍。对 v2 采样，查找那一行占 32%，即 596 ms 中的约 190 ms，和这个推算大致吻合。

### 第二步：下一个热点

修掉一个热点，占比就重新分配。v2 的剖析结果里，第一名变成了 `in >> w` 那一行，占 45%；哈希表查找降到 32%；逐字符清洗占约 18%。`operator>>` 每读一个词都要构造一个 `sentry` 对象，检查流状态、取 locale 中的 `ctype` facet、跳过空白，这些固定开销对 9 个字节的词来说太重了。

<div class="compare" markdown="1">

```cpp title="v1"
// using Counts = std::map<std::string, int>;
Counts count_words(const std::string& text) {
  Counts counts;
  std::istringstream in(text);
  std::string w;
  while (in >> w) {
    std::string clean;
    for (char c : w)
      if (std::isalnum(
            static_cast<unsigned char>(c)))
        clean += char(std::tolower(
            static_cast<unsigned char>(c)));
    if (!clean.empty()) ++counts[clean];
  }
  return counts;
}
```

```cpp title="v3"
// using Counts =
//   std::unordered_map<std::string, int>;
bool space(char c) {
  return std::isspace(
      static_cast<unsigned char>(c));
}
Counts count_words(const std::string& text) {
  Counts counts;
  counts.reserve(1 << 16);
  std::string clean;
  std::size_t i = 0, n = text.size();
  while (i < n) {
    while (i < n && space(text[i])) ++i;
    clean.clear();
    for (; i < n && !space(text[i]); ++i) {
      unsigned char c = text[i];
      if (std::isalnum(c))
        clean += char(std::tolower(c));
    }
    if (!clean.empty()) ++counts[clean];
  }
  return counts;
}
```

</div>

v3 直接在原字符串上扫描分词，`clean` 在循环外只建一次，`clear()` 保留已有的容量，`reserve` 预先分配好桶，避免插入过程中的重新哈希。v3 同时改了两处，严格的做法是一次只改一处、分别测量；这里分词那一行在 v2 中占 45%，按阿姆达尔定律上限约 1.8 倍，实测 596 → 353 ms 是 1.69 倍，大部分收益来自分词。

v3 的剖析结果：哈希表查找占 51%，`clean += char(std::tolower(c))` 那一行占 28%，其中主要是对 libc++ 中 `push_back` 和 libc 中 `tolower` 的函数调用（见上文内联帧一节）。再往下优化就要换数据结构或者避免逐字符追加，属于 [[perf/choosing-containers|选择容器]] 和 [[perf/allocation|内存分配]] 两页的内容。

### 整个程序快了多少

`count_words` 快了 3 倍，整个程序却没有。文本生成阶段 70 到 110 ms 没有变，按 80 ms 计，整体从约 1145 ms 降到约 433 ms，是 2.6 倍。这正是阿姆达尔定律的另一面：被优化的部分越小，没被优化的部分在总时间里的比例就越大。什么时候停下来，取决于剩下的时间是否还值得花工夫，而不是剖析结果里还有没有排第一的函数（永远有）。

## 编译期的热点

剖析器测的是程序运行时的时间。编译本身慢，要找的是哪个头文件、哪个模板实例化最费时间，工具是 Clang 的 `-ftime-trace`：它在目标文件旁边写一个 JSON 文件（`-o x.o` 对应 `x.json`），可以用 Chrome 的 `chrome://tracing` 或 speedscope 打开，看到的也是一张火焰图。编译期的分析和提速方法见 [[toolchain/build-speed|构建提速]]。

## 陷阱

!!! pitfall "剖析调试构建"
    `-O0` 或 `-Og` 构建的剖析结果里，排在前面的常常是在发布构建中会被内联掉的访问器。剖析要用和发布相同的优化级别，再加 `-g`。

!!! pitfall "只看自身耗时"
    自身耗时最大的往往是 `memcmp`、`malloc` 这类底层函数。它们本身通常已经很快，该改的是调用它们太多次的那段代码。沿着总耗时从上往下找。

!!! pitfall "剖析了错误的输入"
    热点取决于输入。把词表从 5 万个词改成 50 个词，本机剖析结果里 `++counts[clean]` 那一行从 66% 降到 26%，`in >> w` 升到 46%，成了第一名。用接近真实的数据剖析，必要时准备几组不同规模的输入。

!!! pitfall "改了两处，只测一次"
    同时做两处修改，就不知道收益来自哪一处，也可能一处变快、一处变慢而互相抵消。每次只改一处，改完重新剖析。

## 思考题

!!! question "1"
    剖析结果显示函数 `f` 占 20% 的时间，你把它改快了 2 倍。整个程序最多快多少？如果 `f` 占 80% 呢？

<details markdown="1">
<summary>答案</summary>

由 S = 1 / ((1 − p) + p / s)：p = 0.2、s = 2 时 S = 1 / (0.8 + 0.1) ≈ 1.11，只快 11%；p = 0.8 时 S = 1 / (0.2 + 0.4) ≈ 1.67。同样把一个函数改快 2 倍，收益取决于它原本占多少。
</details>

!!! question "2"
    `count_words` 在 `-O2` 下有 66% 的样本落在第 50 行。同一行在 `-O0` 下占 64%。既然按行统计差不多，为什么还说 `-O0` 的剖析结果不可信？

<details markdown="1">
<summary>答案</summary>

这一次按行统计碰巧相近，但没有任何保证。`-O0` 下各部分变慢的倍数取决于它们原本有多少调用被内联掉，没有理由相同，占比自然可能变化。按函数看，`-O0` 的第一名是 `-O2` 中根本不存在的 `__get_pointer`。as-if 规则（[[intro.abstract#1]]）允许优化器大幅改变程序结构，只有剖析实际运行的那份机器码，结论才能用在发布版本上。
</details>

!!! question "3"
    在 x86-64 Linux 上用 `perf record -g` 剖析一个用默认 `-O2` 编译的程序，调用树里很多函数直接挂在根节点下，看不到调用者。可能是什么原因，怎么办？

<details markdown="1">
<summary>答案</summary>

`-g` 让 `perf` 沿帧指针回溯，而 x86-64 上 `-O2` 默认省略帧指针（本机用 `--target=x86_64-linux-gnu -O2 -S` 编译出的代码里没有 `%rbp` 帧链），链条断了，调用者就找不到。可以用 `-fno-omit-frame-pointer` 重新编译，或者改用 `perf record --call-graph dwarf`，借助调试信息回溯。系统库同样可能缺少帧指针。
</details>

## 小结

| 问题 | 做法 |
|---|---|
| 时间花在哪里 | 先采样：macOS 用 `sample` 或 Instruments，Linux 用 `perf record` |
| 怎样构建 | 发布的优化级别加 `-g`；需要帧指针回溯时加 `-fno-omit-frame-pointer`；本机用 `-gdwarf-4` |
| 怎样读结果 | 沿总耗时从 `main` 往下找；自身耗时大的底层函数要看是谁在调用 |
| 内联的代码 | `atos -i`、`llvm-symbolizer --inlining` 展开内联帧，它们没有调用开销 |
| 为什么慢 | 硬件计数器：Linux 用 `perf stat`，macOS 用 Instruments 的 CPU Counters |
| 确认一段的耗时 | 作用域计时器；`-finstrument-functions-after-inlining` 只适合数调用次数 |
| 改完之后 | 用阿姆达尔定律估计上限，重新测量，重新剖析，热点会换位置 |
