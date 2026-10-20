---
title: 编译速度
summary: 怎样测量并缩短 C++ 的构建时间：-ftime-trace 看时间花在哪里，前端与后端的比例，标准头文件和模板实例化的代价，预编译头、import std、extern template、unity build、并行构建、编译器缓存、链接器、调试信息和 LTO 各自省下或多花多少。
group: 工程实践
status: draft
order: 105
since: c++98
papers: P2662R3, P2465R3
related: lex.separate, cpp.include, temp.inst, temp.explicit, namespace.unnamed, basic.def.odr, basic.link, implimits, dcl.type.pack.index, toolchain/physical-design, toolchain/compilation-pipeline, toolchain/modules-in-practice, toolchain/linking-and-symbols, toolchain/cmake, toolchain/dependencies, perf/lto-pgo
tags: 工具链, 构建, 编译时间, 预编译头, 模块, unity build, LTO
updated: 2026-10-19
---

!!! tldr
    - 先测量再优化。Clang 的 `-ftime-trace` 给出一个翻译单元里每个头文件、每次模板实例化、每个优化遍的耗时；本机一个 18 行的 `std::format` 程序，前端约占 2/3，其中 `<format>` 的解析和 `std::format` 的实例化最贵。
    - 头文件和模板实例化的代价都乘以翻译单元的个数。预编译头、`import std;` 和 `extern template` 都是让这部分工作只做一次，本机各自让单个翻译单元的前端工作量降到约一半。
    - unity build 把多个 `.cpp` 拼成一个翻译单元，本机 48 个文件的总 CPU 时间降到约 1/4，代价是无名命名空间和 `static` 名字会冲突，重载决议的结果可能悄悄改变。
    - 并行构建受核数、内存和串行的链接步骤限制。链接器的选择影响很大：本机同一组目标文件，2022 年的 ld64 用 2.85 s，Xcode 自带的新链接器用 0.28 s。
    - `-g` 让目标文件大几倍，本机编译多花 7%～16% 的 CPU；完整 LTO 把优化工作移到串行的链接阶段，改一个文件也要重新优化整个程序，ThinLTO 加缓存可以避免。

!!! note "实验环境"
    Apple M2 Pro（8 个性能核 + 4 个能效核，16 GB 内存），macOS，Homebrew Clang 23.1（libc++），CMake 3.29，Ninja 1.12，GNU Make 3.81。测量时机器上同时运行着其他编译任务（load average 50～100），所以墙钟时间只看趋势。单个编译命令主要报告 `/usr/bin/time -l` 给出的**指令数**（instructions retired，CPU 实际执行的指令条数），它几乎不受负载影响；涉及多个进程的命令报告用户态加内核态的 CPU 时间之和。所有数字都是本机的局部观察。

标准对构建过程只给了一个模型：程序由若干翻译单元组成，它们可以分别翻译，最后链接在一起（[[lex.separate#1]] 的注 1）。源文件、翻译单元和翻译后的翻译单元不必以文件形式存在，也不必与任何外部表示一一对应（[[lex.separate#1]] 的注 2）。这两句给了实现很大的空间：预编译头、BMI、编译缓存、LTO 都是在这个空间里做的优化。每一步具体做什么见 [[toolchain/compilation-pipeline|编译流水线]]。

## 时间花在哪里

一个典型的小翻译单元：

```cpp title="app.cpp" run ok
#include <algorithm>
#include <format>
#include <map>
#include <string>
#include <vector>

struct Order { std::string sym; int qty; double px; };

std::string report(std::vector<Order> v) {
  std::ranges::sort(v, {}, &Order::px);
  std::map<std::string, int> pos;
  for (const auto& o : v) pos[o.sym] += o.qty;
  std::string out;
  for (const auto& [s, q] : pos)
    out += std::format("{:>6} {:>8}\n", s, q);
  return out;
}
```

`-ftime-trace` 让 Clang 在目标文件旁边写一个同名的 `.json`，格式是 Chrome 的 trace event 格式，可以拖进 `chrome://tracing` 或 Perfetto 看火焰图：

```text
$ clang++ -std=c++2c -O2 -c app.cpp -ftime-trace -o app.o
$ ls -l app.json
-rw-r--r--  1 weiran  wheel  375880 Oct 19 17:50 app.json
```

默认只记录超过 500 µs 的事件。`-ftime-trace-granularity=0` 记录全部事件，本机 JSON 涨到 65 MB，那次编译也慢了约 40%，一般用不着。

ClangBuildAnalyzer 可以汇总多个 trace，本机没有安装。单个 trace 用几行 Python 就能汇总：文件里以 `Total ` 开头的事件是各类事件的累计时长，`Source` 事件是成对的 `b`/`e`（开始、结束）记录，取最外层的就是每个直接包含的头文件的耗时。本机这次运行的结果：

| 事件 | 耗时 | 说明 |
|---|---:|---|
| ExecuteCompiler | 2007 ms | 整个编译 |
| Frontend | 1346 ms | 预处理、解析、语义分析、实例化、生成 IR |
| 其中 Source | 579 ms | 处理头文件：`<format>` 324 ms，`<algorithm>` 197 ms，`<vector>` 33 ms，`<map>` 25 ms |
| 其中 PerformPendingInstantiations | 427 ms | 翻译单元末尾集中实例化函数模板 |
| 其中 CheckConstraintSatisfaction | 501 ms | 检查概念约束，与上面几项有重叠 |
| Backend | 647 ms | 优化（400 ms）和机器码生成（245 ms） |

按模板名合并 `InstantiateFunction` 事件，最贵的是 `std::format`（421 ms，包含它内部触发的实例化）、`std::vformat_to`（368 ms），`std::__tree` 的 10 个特化合计 155 ms。`<string>` 没有出现在头文件列表里，因为 `<algorithm>` 和 `<format>` 已经间接包含了它，第二次包含被 include guard 跳过。

两点读法。第一，嵌套事件的时间包含子事件，各行相加没有意义，只比较同一层。第二，trace 只说明一个翻译单元；项目的总时间是每个翻译单元的时间乘以它出现的次数，同一个头文件被 300 个 `.cpp` 包含，就付 300 次。

### 前端与后端

`-fsyntax-only` 只跑前端，不生成代码。和 `-O0`、`-O2` 比较，差值大致就是后端的成本：

| 命令 | 指令数 | CPU 时间 |
|---|---:|---:|
| `-fsyntax-only` | 4.68 G | 0.56 s |
| `-c -O0` | 5.67 G | 0.66 s |
| `-c -O2` | 8.22 G | 1.07 s |

这个翻译单元在 `-O0` 下几乎全是前端，`-O2` 下后端约占 40%。头文件多、函数体少的翻译单元偏向前端，大量模板代码被实例化又被内联的翻译单元偏向后端。前端的成本靠减少重复解析和实例化来降，后端的成本靠减少要优化的代码量、选择优化级别来降，二者的手段不同，所以先看比例。

## 头文件的代价

`#include` 用头文件的全部内容替换这条指令（[[cpp.include#3]]）。替换是文本层面的，被包含的内容和源文件一起经历全部翻译阶段。本机逐个只包含一个标准头文件，`-E -P` 的输出行数和 `-fsyntax-only` 的成本：

| 头文件 | 预处理后行数 | 大小 | 指令数 | CPU 时间 |
|---|---:|---:|---:|---:|
| （空文件） | — | — | 0.34 G | 0.02 s |
| `<cstddef>` | 141 | 10 KB | 0.36 G | 0.03 s |
| `<memory>` | 11 333 | 704 KB | 0.87 G | 0.09 s |
| `<map>` | 15 943 | 970 KB | 1.07 G | 0.11 s |
| `<string>` | 14 041 | 853 KB | 1.10 G | 0.14 s |
| `<functional>` | 20 622 | 1.27 MB | 1.25 G | 0.13 s |
| `<algorithm>` | 24 193 | 1.38 MB | 1.38 G | 0.14 s |
| `<ranges>` | 23 845 | 1.46 MB | 1.45 G | 0.16 s |
| `<vector>` | 23 678 | 1.34 MB | 1.49 G | 0.16 s |
| `<format>` | 30 126 | 1.65 MB | 2.64 G | 0.27 s |
| `<regex>` | 35 207 | 1.93 MB | 2.67 G | 0.29 s |
| `<print>` | 30 258 | 1.66 MB | 2.76 G | 0.29 s |
| `<iostream>` | 35 635 | 1.96 MB | 3.24 G | 0.35 s |
| `<chrono>` | 41 123 | 2.31 MB | 3.28 G | 0.38 s |
| 以上 13 个一起 | 77 273 | 4.43 MB | 5.12 G | 0.68 s |

行数和成本并不成比例：`<format>` 比 `<vector>` 只多 27% 的行，指令数却多 77%，因为它在头文件里就实例化了大量模板、检查了大量约束。13 个头文件一起包含只比最大的单个贵 60%，它们共享了大部分内部头文件。

这张表说明的是单个翻译单元的下限：写一行 `#include <chrono>`，这个 `.cpp` 就至少要 0.38 s CPU 时间。头文件怎样组织才能少包含、包含得便宜，见 [[toolchain/physical-design|物理设计]]，这里不重复。

## 模板实例化的代价

模板的每个特化都是编译器复制、替换出来的一份新声明（[[temp.inst]]）。写法不同，同样的结果可能需要实例化数量级不同的特化。下面的程序取一个类型包的第 `I` 个元素，用两种方法：经典的递归偏特化，和 C++26 的包索引 `Ts...[I]`（[[dcl.type.pack.index]]，[[P2662R3]]）。

```cpp title="meta.cpp" run ok
#include <cstddef>
#include <type_traits>
#include <utility>

#ifndef N
#define N 200
#endif

template <std::size_t> struct T {};

#ifdef RECURSIVE
template <std::size_t I, class... Ts> struct nth;
template <class H, class... Ts>
struct nth<0, H, Ts...> { using type = H; };
template <std::size_t I, class H, class... Ts>
struct nth<I, H, Ts...> : nth<I - 1, Ts...> {};
template <std::size_t I, class... Ts>
using nth_t = typename nth<I, Ts...>::type;
#else
template <std::size_t I, class... Ts>
using nth_t = Ts...[I];                  // C++26 包索引
#endif

template <class... Ts, std::size_t... I>
constexpr bool check(std::index_sequence<I...>) {
  return (std::is_same_v<nth_t<I, Ts...>, T<I>> && ...);
}
template <std::size_t... I>
constexpr bool all(std::index_sequence<I...> s) {
  return check<T<I>...>(s);
}
static_assert(all(std::make_index_sequence<N>{}));
```

递归版本求 `nth_t<I, ...>` 要实例化 `I + 1` 个 `nth` 的特化，每个特化带着一份剩余的类型列表。对所有 `I` 求一遍，就是约 N²/2 个类特化，类型列表的总长度是 N³ 量级。包索引由编译器直接取出第 `I` 个元素，不产生中间特化。

| | N = 100 | N = 200 | N = 1000 |
|---|---:|---:|---:|
| 递归偏特化（`-DRECURSIVE`） | 2.64 G 指令，176 MB | 15.4 G 指令，829 MB | — |
| `Ts...[I]` | 0.64 G 指令，64 MB | 0.73 G 指令，68 MB | 3.34 G 指令，198 MB |

N 翻倍，递归版本的指令数涨到约 5.8 倍，内存涨到 4.7 倍；包索引版本在 N = 1000 时还不到递归版本 N = 200 的四分之一。递归深度也有上限：标准建议实现至少支持 1024 层嵌套实例化（[[implimits#1.41]]），无限递归的实例化是 UB（[[temp.inst#18]]）。

在 `-ftime-trace` 里，这类问题表现为某个 `InstantiateClass` 或 `InstantiateFunction` 事件下面挂着很深的子事件。常见的改法是用编译器内建的设施替换手写的递归：包索引、折叠表达式、`std::make_index_sequence`（libc++ 用内建函数实现），以及 `if constexpr` 代替基于特化的分派。思路见 [[topics/compile-time-programming]]。

## 预编译头

头文件每个翻译单元都要处理一遍，**预编译头**（precompiled header，PCH）把一组头文件的处理结果序列化到磁盘，之后的编译直接加载。标准不知道 PCH 的存在，它之所以合法，是因为结果必须和真的包含了那些头文件一样（[[lex.separate#1]] 的注 2 允许翻译单元不以文本形式存在）。

```text
$ cat pch.h
#pragma once
#include <algorithm>
#include <format>
#include <map>
#include <string>
#include <vector>
$ clang++ -std=c++2c -x c++-header pch.h -o pch.h.pch
$ clang++ -std=c++2c -O0 -include-pch pch.h.pch -c app.cpp -o app.o
```

`-include-pch` 相当于在 `app.cpp` 第一行之前包含 `pch.h`，之后 `app.cpp` 自己的 `#include <format>` 因为 include guard 不再展开。本机测量：

| | 指令数 | CPU 时间 |
|---|---:|---:|
| 生成 `pch.h.pch`（14.7 MB） | 4.09 G | 0.45 s |
| `app.cpp`，`-O0`，不用 PCH | 5.69 G | 0.65 s |
| `app.cpp`，`-O0`，用 PCH | 3.08 G | 0.31 s |

剩下的 3 G 指令主要是 `std::format` 等模板在这个翻译单元里的实例化和代码生成，PCH 省不掉。生成 PCH 的成本约等于一次包含全部头文件的编译，项目里有几十个翻译单元共用它才划算。

PCH 和编译选项绑定。用 `-O0` 生成的 PCH 给 `-O2` 编译使用，Clang 直接拒绝：

```text
$ clang++ -std=c++2c -O2 -include-pch pch.h.pch -c app.cpp -o app.o
error: OptimizationLevel differs in precompiled file '/tmp/bs.UQgY/pch.h.pch' vs. current file
1 error generated.
```

语言标准不同（`C++26 was enabled in precompiled file ... but is currently disabled`）、命令行上的同名宏取值不同（`definition of macro 'X' differs between the precompiled file ... ('1') and the command line ('2')`）也会报错。反过来，生成 PCH 时用了 `-DX=1`、使用时不写 `-DX`，本机 Clang 不报错，`X` 照样有定义。所以每种配置要各自生成 PCH，构建系统通常替你处理，CMake 的写法是 `target_precompile_headers`，见 [[toolchain/cmake|CMake]]。

!!! pitfall "PCH 掩盖缺失的包含"
    PCH 被强制包含在每个翻译单元的最前面，一个 `.cpp` 忘了包含 `<map>` 也能编译。换一个构建配置、关掉 PCH，或者把这个文件拿到别的项目里，就会编译失败。头文件应当自包含，见 [[toolchain/physical-design|物理设计]]。持续集成里保留一个不用 PCH 的构建可以发现这类问题。

## `import std;`

标准库模块 `std`（[[P2465R3]]，C++23）是另一种只做一次的方式，而且是标准的。libc++ 提供了模块接口源码，要先预编译成 BMI：

```text
$ clang++ -std=c++2c -Wno-reserved-module-identifier --precompile \
    /opt/homebrew/opt/llvm/share/libc++/v1/std.cppm -o std.pcm
$ clang++ -std=c++2c -O0 -fmodule-file=std=std.pcm -c app_mod.cpp -o app_mod.o
```

`app_mod.cpp` 是把 `app.cpp` 的五行 `#include` 换成 `import std;`。本机测量：

| | `#include` 五个头文件 | `import std;` |
|---|---:|---:|
| 预编译 `std.pcm`（35.5 MB） | — | 9.79 G，1.23 s |
| `-fsyntax-only` | 4.68 G | 1.99 G |
| `-c -O0` | 5.76 G | 3.01 G |
| `-c -O2` | 8.22 G | 5.46 G |

`import std;` 导入的是整个标准库，前端工作量仍然比包含五个头文件少一半多，和 PCH 的效果相当。区别在于模块是语言的一部分：宏不会跨越 `import`，导入顺序不影响含义，没有 PCH 掩盖缺失包含的问题。BMI 同样和编译器版本、关键选项绑定。BMI 的种类、依赖扫描和 CMake 集成见 [[toolchain/modules-in-practice|模块的工程实践]]。

## `extern template`

如果很多翻译单元都使用同一个类模板特化，每个翻译单元都会把它的成员函数实例化、优化、生成代码一遍，最后链接器只留一份。**显式实例化声明**（[[g:explicit-instantiation-declaration|explicit instantiation declaration]]）`extern template class X<T>;` 告诉编译器这个特化在别处有**显式实例化定义**，本翻译单元不必再实例化（[[temp.explicit#2]]）。写法、`.cpp` 怎样组织、只对列出的实参可用这些问题，见 [[toolchain/physical-design|物理设计]]。

需要补充的是 inline 成员的情况。一个类模板 `Table<K>`，三个成员函数的定义写在头文件里，16 个翻译单元都使用 `Table<std::string>`。本机 `-O2` 下，加上 `extern template class Table<std::string>;` 前后：

| | 单个翻译单元 | 16 个翻译单元 CPU 合计 | `u01.o` |
|---|---:|---:|---:|
| 成员是普通函数，无 `extern template` | 8.13 G | 16.6 s | 106 KB |
| 成员是普通函数，有 `extern template` | 3.50 G | 6.1 s，另加 `table.cpp` 1.0 s | 2.9 KB |
| 成员是 inline，无 `extern template` | 8.10 G | — | — |
| 成员是 inline，有 `extern template` | 7.12 G | — | — |

成员函数是 inline 的时候（在类内定义，或者显式写 `inline`），`extern template` 几乎不省时间。这是标准有意的安排：inline 函数即使是显式实例化声明的对象，在被 odr-use 时仍然隐式实例化，以便内联；只是不必生成独立的函数体（[[temp.inst#5]] 的注 3）。省时间要靠把重的成员定义成非 inline。

标准库自己也这样做。libc++ 的 `<string>` 对 `basic_string<char>` 和 `basic_string<wchar_t>` 的大部分成员写了显式实例化声明，定义放在 `libc++.dylib` 里，所以每个翻译单元不必为 `std::string` 的成员生成代码。

## unity build

**unity build**（也叫 jumbo build）把若干个 `.cpp` 用 `#include` 拼成一个源文件来编译。公共头文件只处理一次，模板只实例化一次。CMake 打开 `CMAKE_UNITY_BUILD` 后，每 8 个源文件生成一个这样的文件：

```cpp title="unity_0_cxx.cxx"
/* generated by CMake */

/* NOLINTNEXTLINE(bugprone-suspicious-include) */
#include "/tmp/bs.UQgY/proj/src/main.cpp"

/* NOLINTNEXTLINE(bugprone-suspicious-include) */
#include "/tmp/bs.UQgY/proj/src/r00.cpp"
...
```

本机测试项目有 48 个类似 `app.cpp` 的源文件和一个 `main.cpp`，Release（`-O3`）构建，`ninja -j12`：

| | 编译的翻译单元 | CPU 合计 | 墙钟 | 改一个 `.cpp` 后重建 |
|---|---:|---:|---:|---:|
| 普通构建 | 49 | 63.4 s | 16.1 s | 1.14 s CPU |
| unity build | 7 | 14.8 s | 5.4 s | 1.99 s CPU |

全量构建的 CPU 时间降到约 1/4。代价有三个。第一，改一个文件要重新编译它所在的整组，本机增量重建贵了约 75%。第二，并行度下降，7 个翻译单元填不满 12 个核。第三，也是最麻烦的，翻译单元的边界变了，而 C++ 有许多规则是以翻译单元为单位的。

### 内部名字冲突

每个源文件里都有这样的辅助代码：

```cpp title="r00.cpp（片段）"
namespace {
struct Row { std::string key; double val; };
std::string fmt_row(const Row& r) {
  return std::format("{:>8} {:10.3f}\n", r.key, r.val);
}
}  // namespace
```

分开编译时这完全正确：无名命名空间里的名字具有内部链接（[[basic.link#4]]），各个翻译单元的 `Row` 是不同的实体。拼在一起之后，构建失败：

```text
In file included from .../Unity/unity_5_cxx.cxx:7:
/tmp/bs.UQgY/proj/src/r40.cpp:7:8: error: redefinition of 'Row'
    7 | struct Row { std::string key; double val; };
      |        ^
/tmp/bs.UQgY/proj/src/r39.cpp:7:8: note: previous definition is here
```

原因在 [[namespace.unnamed#1]]：一个翻译单元里所有无名命名空间的 *unique* 名字都替换成同一个标识符。两个文件的无名命名空间合进同一个翻译单元，就是同一个命名空间，`Row` 定义了两次，违反了一个翻译单元内最多一个定义的规则（[[basic.def.odr#2]]）。`static` 函数、`static` 变量同理。

这种冲突至少会报错。更危险的是不报错、但含义变了的情况：

<div class="compare" markdown="1">

```cpp title="a.cpp"
#include <cstdio>
static void show(int) {
  std::puts("a.cpp: show(int)");
}
void fa() { show(1); }
```

```cpp title="b.cpp"
#include <cstdio>
static void show(long) {
  std::puts("b.cpp: show(long)");
}
void fb() { show(1); }
```

</div>

两个 `show` 签名不同，不构成重定义。分开编译时 `fb` 只看得见 `show(long)`，输出 `b.cpp: show(long)`。拼成一个翻译单元后，`b.cpp` 里的 `show(1)` 也看得见 `a.cpp` 的 `show(int)`，重载决议选择精确匹配的 `show(int)`，本机输出变成两行 `a.cpp: show(int)`。程序仍然良构，唯一的线索是 `-Wunused-function` 报告 `b.cpp` 的 `show(long)` 没有用到。同样的问题还出在宏、`using namespace` 指令和文件作用域的 `using` 声明上，它们都会从前一个文件泄漏到后一个。

### 处理办法

CMake 提供了几个开关：给不宜合并的文件设置 `SKIP_UNITY_BUILD_INCLUSION`；或者设置 `UNITY_BUILD_UNIQUE_ID`，CMake 在 unity build 时为每个文件定义一个值不同的宏，源码里用它在无名命名空间内再套一层：

```cpp title="r00.cpp（改写后）"
#ifndef UNITY_ID
#define UNITY_ID
#endif

namespace { namespace UNITY_ID {
struct Row { std::string key; double val; };
std::string fmt_row(const Row& r);
}}  // namespace

// 使用处写 UNITY_ID::Row、UNITY_ID::fmt_row
```

使用处必须带限定。如果在无名命名空间里加一句 `using namespace UNITY_ID;` 图省事，这些 using 指令在合并后都位于同一个无名命名空间里，后面的文件同时看见所有文件的 `fmt_row`。本机用两个文件的最小例子验证，Clang 报告 `call to ... is ambiguous`。

本机还观察到一点：CMake 3.29 中，项目设置 `CMAKE_CXX_STANDARD 26` 后默认启用模块依赖扫描，而参与扫描的源文件不会被合并，unity build 实际上没有生效，要同时设置 `CMAKE_CXX_SCAN_FOR_MODULES OFF`（CMake 的 `UNITY_BUILD` 文档写明了这条限制）。

我的建议：unity build 适合作为持续集成的全量构建手段，日常开发用普通构建；新代码给内部辅助函数起不易冲突的名字，或者从一开始就用 `UNITY_ID` 包一层；持续集成里同时保留一个非 unity 的构建，确认两者都能通过、测试结果一致。

## 并行构建

分别翻译是并行的基础：翻译单元之间没有依赖（模块除外），可以同时编译（[[lex.separate]]）。同一个 49 个文件的项目，全量构建，`ninja -jN`：

| `-j` | 墙钟 | CPU 合计 |
|---:|---:|---:|
| 1 | 54.8 s | 51.8 s |
| 4 | 16.7 s | 55.5 s |
| 8 | 9.3 s | 54.9 s |
| 12 | 8.5 s | 57.6 s |

8 个核以内接近线性，再往上收益很小：多出来的 4 个是能效核，机器上也有其他负载。限制并行度的还有两件事。一是内存，本机每个编译进程峰值约 200 MB，模板很重的翻译单元可以到几 GB，`-j` 过大会开始换页，反而更慢；Ninja 的 `pool` 可以单独限制重任务的并发数。二是链接，它在所有编译完成之后串行执行，下文单独讨论。

Ninja 不加 `-j` 时默认并行（本机默认 14），Make 默认串行，这是二者最常见的差别。全量构建时真正干活的都是编译器，构建工具本身的开销可以忽略。差别在于没有任何文件改变的空构建：本机这个项目 `make -j12` 用 0.14 s，`ninja` 不到 10 ms。项目有几千个文件、开发时一天构建上百次，这个差别才会显现。CMake 生成哪一种由 `-G` 决定，推荐 Ninja。

## 编译器缓存

ccache 和 sccache 本机都没有安装，这里只描述机制，没有本机输出。

编译器缓存包装编译命令。它把编译器版本、命令行选项和输入内容一起做哈希，命中时直接复制上次的 `.o`，不运行编译器。输入内容有两种算法：先预处理再哈希预处理结果（总是正确，但每次都要付预处理的成本），或者直接哈希源文件和它依赖的所有头文件（ccache 的 direct mode，更快，依赖编译器报告的头文件列表）。sccache 还可以把缓存放在远端存储上，在多台机器、多个持续集成任务之间共享。

适用场景是同一份源码被反复从头编译：切换分支后切回来、`make clean`、持续集成每次都从干净的目录开始。日常的增量构建本来就只编译改过的文件，缓存帮助不大。

几个需要注意的地方：

- 命令行里的绝对路径（包括 `-g` 写进调试信息的源文件路径）不同，哈希就不同。在不同目录下检出的同一份代码，要配置路径改写（ccache 的 `base_dir`，或 Clang 的 `-fdebug-prefix-map`）才能共享缓存。
- PCH 和模块的 BMI 是额外的输入，缓存工具需要专门支持，否则命中率会很低，或者干脆不缓存。使用前查看所用版本的文档。

## 链接器

全部编译完成后，链接器必须一次处理所有目标文件。链接器做的事情（解析符号、合并弱定义、重定位）见 [[toolchain/linking-and-symbols|链接与符号]]。它是构建中天然串行的一步，增量构建时往往是最慢的一步：改一个 `.cpp`，编译一个文件，然后重新链接整个程序。

本机测试用 400 个目标文件（共 93 MB，约 40 万个符号，每个文件还带 1000 个内联函数模板特化的弱定义，链接时要合并），比较本机能找到的三个 Mach-O 链接器：

| 链接器 | 墙钟 | CPU |
|---|---:|---:|
| ld64-530（2022 年的 ld64，来自 PATH 上的另一套工具链） | 2.85 s | 2.98 s |
| Xcode 的 ld64-957（`-Wl,-ld_classic`，已弃用） | 0.54 s | 0.76 s |
| Xcode 的新链接器 ld-1266（Xcode 默认） | 0.28 s | 0.83 s |

新链接器的 CPU 时间并不比旧版 ld64 少，但它多线程，墙钟时间是一半。LLVM 的 lld（Mach-O 版是 `ld64.lld`）和 mold 本机都没有安装，没有测量。Clang 用 `-fuse-ld=lld` 或 `--ld-path=<路径>` 选择链接器。

!!! pitfall "Clang 用的是哪个 `ld`"
    本机 Homebrew Clang 默认用 `PATH` 里找到的第一个 `ld`，结果是 Anaconda 带的 ld64-530，而不是 Xcode 的链接器。它不认识 Clang 23 生成的 DWARF 5，链接带 `-g` 的目标文件时警告 `can't parse dwarf compilation unit info`，并且不写调试映射，`dsymutil` 随后报告 `no debug symbols in executable`，调试器找不到源码行。用 `clang++ -### x.o` 可以看到实际调用的链接器路径。

## 调试信息

`-g` 让编译器为每个函数、类型、变量生成 DWARF 描述。它不改变生成的代码，但要多做不少工作。还是 `app.cpp`：

| 选项 | `-O0` 指令数 | `-O0` 目标文件 | `-O2` 指令数 | `-O2` 目标文件 |
|---|---:|---:|---:|---:|
| 无 | 5.67 G | 405 KB | 8.22 G | 113 KB |
| `-gline-tables-only` | 5.86 G | 571 KB | 8.48 G | 339 KB |
| `-g` | 6.07 G | 1046 KB | 9.52 G | 891 KB |

`-O2 -g` 比 `-O2` 多 16% 的指令，目标文件大 7.9 倍，主要是标准库模板的类型描述。`-gline-tables-only` 只保留地址到源码行的映射，足够让崩溃栈和性能分析器显示文件名和行号，但调试器看不到局部变量和类型。

整个 49 文件的项目，`-O2` 全量构建：

| 选项 | CPU 合计 | 目标文件合计 | 链接 | `dsymutil` |
|---|---:|---:|---:|---:|
| `-g0` | 59.8 s | 6.0 MB | 0.09 s | — |
| `-gline-tables-only` | 60.4 s | 18.0 MB | 0.08 s | 0.09 s，dSYM 3.6 MB |
| `-g` | 69.5 s | 45.2 MB | 0.09 s | 0.26 s，dSYM 9.3 MB |

在 macOS 上，链接器不把 DWARF 复制进可执行文件，只记录一张指向各个 `.o` 的调试映射，所以 `-g` 几乎不影响链接时间。需要独立的调试信息包时，`dsymutil` 再把它们收集成 `.dSYM`。Linux 的 ELF 链接器默认把所有 `.debug_*` 节复制进输出，调试信息大时链接会明显变慢，这是 `-gsplit-dwarf` 存在的原因；这一点本机无法验证。

我的建议：日常开发构建用 `-g`，需要调试时信息齐全；发布构建如果只需要符号化的崩溃栈，用 `-gline-tables-only`；持续集成里只编译、跑测试的任务可以完全不要调试信息。

## LTO 何时拖慢构建

**链接时优化**（link-time optimization，LTO）让编译器在每个 `.o` 里保存 LLVM IR 而不是机器码，链接时把整个程序的 IR 放在一起优化，从而能跨翻译单元内联。它对运行速度的影响见 [[perf/lto-pgo|LTO 与 PGO]]。构建时间方面，同一个 49 文件项目，Xcode 链接器，`ninja -j12`：

| | 全量构建墙钟 | 改一个 `.cpp` 后重建 | 只重新链接 |
|---|---:|---:|---:|
| 无 LTO | 10.0 s | 1.38 s | 0.17 s |
| `-flto=thin` | 11.8 s | 2.10 s（CPU 9.0 s） | 1.22 s（CPU 8.9 s） |
| `-flto=thin` + 缓存 | — | 0.89 s | 0.12 s |
| `-flto`（完整 LTO） | 9.2 s | 3.02 s | 2.20 s |

全量构建差别不大：优化和代码生成的工作从编译阶段移到了链接阶段，总量相近。差别在增量构建。完整 LTO 把所有 IR 合并成一个模块串行优化，改一个文件也要重新优化整个程序，链接时间随程序规模增长，大项目可以到几分钟、占用几 GB 内存。ThinLTO 只做全程序的摘要分析，各模块的后端并行执行，所以 CPU 时间远大于墙钟时间；但没有缓存时它同样每次重做全部模块。

加上 `-Wl,-cache_path_lto,<目录>`（ELF 上的 lld 写作 `--thinlto-cache-dir=`）后，ThinLTO 只重新优化受影响的模块，本机增量重建甚至比不用 LTO 还快，因为编译阶段只生成 IR、不生成机器码。

我的建议：日常开发构建不开 LTO；发布构建需要 LTO 时用 ThinLTO 并配置缓存；完整 LTO 只在测量证明它确实带来额外性能时使用。

## 思考题

!!! question "unity build 与 ODR"
    两个 `.cpp` 各自在无名命名空间里定义了 `struct Row`，成员不同。分开编译时程序良构吗？unity build 时报错的依据是什么？如果把两个 `Row` 都改成命名空间作用域的普通 `struct Row`（不在无名命名空间里），分开编译会怎样？

<details markdown="1">
<summary>答案</summary>

分开编译时良构：无名命名空间具有内部链接（[[basic.link#4]]），而且每个翻译单元的 *unique* 名字不同（[[namespace.unnamed#1]]），两个 `Row` 是不同的实体。unity build 时它们位于同一个翻译单元，所有无名命名空间的 *unique* 是同一个标识符，于是同一个实体在一个翻译单元里定义了两次，违反 [[basic.def.odr#2]]，必须诊断。

去掉无名命名空间后，两个 `Row` 是同一个具有外部链接的类，定义在不同翻译单元中，却不由相同的记号序列组成，违反 [[basic.def.odr#16]]，不要求诊断。链接器通常看不出来（类本身不产生符号），问题会在两边各自实例化 `std::vector<Row>` 的成员时出现：同名的弱符号只保留一份，另一个翻译单元用错了布局。unity build 反而把这个隐藏的 ODR 违规变成了编译错误。

</details>

!!! question "`extern template` 与 inline"
    给类内定义所有成员的类模板加上 `extern template class X<int>;`，`-O2` 下为什么几乎省不了编译时间？`-O0` 呢？

<details markdown="1">
<summary>答案</summary>

类内定义的成员函数是 inline 的。[[temp.inst#5]] 的注 3 说明：inline 函数即使是显式实例化声明的对象，也不算声明过的特化，被 odr-use 时仍然隐式实例化，以便考虑内联，只是不必生成独立的函数体。所以实例化和优化的工作都还在。本机 `-O0` 下省了约 15% 的指令（5.74 G 到 4.85 G），`-O2` 下约 12%（8.10 G 到 7.12 G），而非 inline 成员能省 57%。

</details>

## 小结

| 手段 | 省掉什么 | 本机观察 | 代价 |
|---|---|---|---|
| `-ftime-trace` | — | 找出最贵的头文件和实例化 | 无 |
| 精简包含 | 解析 | `<chrono>` 一行 0.38 s | 需要整理头文件，见 [[toolchain/physical-design]] |
| 改写元编程 | 实例化 | 包索引比递归快 20 倍以上 | 需要较新的标准 |
| 预编译头 | 解析 | 前端工作量约减半 | 选项绑定；掩盖缺失的包含 |
| `import std;` | 解析 | 与 PCH 相当 | 构建系统要支持模块 |
| `extern template` | 实例化与代码生成 | 16 个 TU 合计从 16.6 s 到 7.1 s | 对 inline 成员无效；只对列出的实参可用 |
| unity build | 重复的解析与实例化 | 全量 CPU 约 1/4 | 内部名字冲突；重载悄悄改变；增量变慢 |
| 并行（Ninja） | 墙钟 | 8 核内接近线性 | 内存 |
| 编译器缓存 | 重复编译 | 本机未安装 | 路径、PCH、模块需要配置 |
| 更快的链接器 | 链接 | 2.85 s 到 0.28 s | 无 |
| 少一些调试信息 | 后端与磁盘 | `-g` 多 7%～16% | 调试体验 |
| 不开 LTO 或 ThinLTO + 缓存 | 链接期优化 | 完整 LTO 增量重建慢 2 倍以上 | 运行性能 |
