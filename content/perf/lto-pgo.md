---
title: 链接时优化与剖析引导优化
summary: 构建层面的优化：为什么编译器看不到另一个翻译单元里的函数体，完整 LTO 与 ThinLTO 怎样在链接时补上内联和去虚化，它们的构建代价，PGO 的插桩、合并、使用三步与它改变的代码排布，采样式 PGO 与 BOLT，-O3 和 -mcpu 实际改变了多少，以及 LTO 让 ODR 违规显形、剖析数据过时这两个陷阱。
status: draft
order: 40
group: 编译器
since: c++98
related: lex.phases, lex.separate, intro.abstract, basic.def.odr, class.virtual, expr.call, expr.pre, toolchain/compilation-pipeline, toolchain/linking-and-symbols, patterns/nvi, patterns/pimpl, perf/compiler-optimizations, perf/branches, perf/measuring, perf/reading-assembly, perf/vectorization, perf/profiling
tags: 性能, LTO, ThinLTO, PGO, 去虚化, 构建, ODR, Clang
updated: 2026-10-19
---

!!! tldr
    - 编译一个翻译单元时，编译器只看得到别的翻译单元里函数的声明，所以跨文件的小函数调用既不能内联，也不能向量化。本机一个 1M 元素的求和，函数体在另一个文件时 0.92 ns/元素，加 `-flto` 后 0.077 ns/元素。
    - `-flto` 把整个程序合成一个模块再优化；`-flto=thin` 只交换摘要、按需导入函数，可以并行并有增量缓存。代价落在链接步骤：本机 80 个文件的程序，链接内存从 60 MiB 涨到 200–300 MiB。
    - LTO 加 `-fwhole-program-vtables` 能把只有一个覆盖者的虚调用变成直接调用，但必须同时让类具有隐藏的 LTO 可见性（例如 `-fvisibility=hidden`），否则什么也不发生。
    - PGO 分三步：插桩编译并运行、`llvm-profdata merge`、带剖析数据重新编译。它改变内联决定、代码块排布和间接调用；本机一个 CSV 解析循环快了约 10%。源码改动后剖析数据会过时，Clang 会警告并丢弃不匹配函数的数据。
    - 这些优化都受 as-if 规则约束，不改变良构程序的行为；但程序有 ODR 违规时，LTO 会让原本被链接器掩盖的错误变成完全不同的结果。

所有数字都是本机（Apple M2 Pro，macOS，Homebrew Clang 23.1，libc++，arm64）上的观察，测量时机器负载很高，绝对值仅供参考，同一张表里的相对比较是交替运行、取多轮最小值得到的。换一台机器、换一个编译器版本，结果都可能不同。计时框架是 [[perf/measuring#harness|bench.hpp]]：每个样本至少约 1 ms，丢弃预热样本，报告 31 个样本的中位数，`bench::do_not_optimize` 用一条空的内联汇编让优化器以为结果被读取了。

## 另一个文件里的小函数

```cpp title="scale.h"
#pragma once
int scale(int x);
```

```cpp title="scale.cpp" ok
#include "scale.h"
int scale(int x) { return x * 3 + 1; }
```

```cpp title="main.cpp" ok
#include "bench.hpp"
#include "scale.h"
#include <cstdio>
#include <vector>

[[gnu::noinline]] long sum(const std::vector<int>& v) {
  long s = 0;
  for (int x : v) s += scale(x);   // scale 定义在另一个翻译单元
  return s;
}

int main() {
  bench::prefer_performance_cores();
  std::vector<int> v(1 << 20);
  for (int i = 0; i < (int)v.size(); ++i) v[i] = i & 1023;
  auto s = bench::run("sum", [&] { long r = sum(v); bench::do_not_optimize(r); });
  std::printf("%.3f ns/elem\n", s.median / v.size());
}
```

```bash
clang++ -std=c++2c -O2 -c scale.cpp -o scale.o
clang++ -std=c++2c -O2 -c main.cpp  -o main.o
clang++ main.o scale.o -o nolto
```

`sum` 的循环每个元素都要 `bl _scale`（本页的汇编都取自 `llvm-objdump -d` 的输出，地址换成了标签，有删节）：

```asm
LBB0_2:
  ldr   w0, [x20], #0x4      ; 取 v[i] 作为实参
  bl    _scale               ; 真正的函数调用
  add   x19, x19, w0, sxtw
  cmp   x20, x21
  b.ne  LBB0_2
```

编译 `main.cpp` 时，编译器只知道 `scale` 的声明。它不知道 `scale` 会不会读写全局变量、会不会抛异常，只能老老实实地调用，循环也就无法向量化。本机测得 0.92 ns/元素。

### 为什么编译器看不到

**翻译单元**（translation unit，TU）是一个源文件连同它 `#include` 进来的全部内容（[[lex.separate#1]]）。翻译阶段 7 把每个 TU 单独分析、翻译成**翻译后的翻译单元**，通常就是一个 `.o` 文件；阶段 8 才把它们组合起来，解析对外部实体的引用（[[lex.phases#1]]）。传统的工具链严格按这个顺序工作：编译器在阶段 7 生成机器码，链接器在阶段 8 只拼接机器码、填地址，不再优化。各阶段的实际对应见 [[toolchain/compilation-pipeline]]。

标准并不要求实现真的把阶段分开。[[lex.phases]] 的脚注说实现只需表现得如同各阶段依次发生，实际上可以合并。更一般的依据是 [[g:as-if-rule|as-if 规则]]：实现只需模拟抽象机的[[g:observable-behavior|可观察行为]]（[[intro.abstract#1]]）。把 `scale` 的函数体搬进 `sum` 不改变任何可观察行为，所以跨 TU 内联是允许的，问题只在于传统工具链在能做这件事的时刻已经没有函数体了。

有两种办法让调用点看到函数体：

- 把定义作为 [[g:inline-function|inline 函数]] 写进头文件。每个 TU 都有一份相同的定义，[[basic.def.odr#16]] 允许这样做。内联阈值等细节见 [[perf/compiler-optimizations|编译器优化]]。
- 保留在 `.cpp` 里，改用**链接时优化**（link-time optimization，LTO），把优化推迟到能看到整个程序的时候。

## 打开 LTO

```bash
clang++ -std=c++2c -O2 -flto -c scale.cpp -o scale.o
clang++ -std=c++2c -O2 -flto -c main.cpp  -o main.o
clang++ -flto main.o scale.o -o full      # 链接时也要带 -flto
```

加了 `-flto` 之后，`.o` 里存的不再是机器码，而是 LLVM 的中间表示（bitcode），`file main.o` 报告 `LLVM bitcode, wrapper`。真正生成机器码推迟到链接时：链接器遇到 bitcode，就交给 LLVM 的 LTO 库把所有模块合在一起，再跑一遍优化和代码生成。

macOS 上 `clang++` 调用系统的 `ld`，并用 `-lto_library` 把 Homebrew LLVM 自己的 `libLTO.dylib` 交给它。用 `clang++ -flto x.o -###` 可以看到实际调用的链接器和这个参数。本机 PATH 里还有另一个较旧的 `ld`，`-###` 显示驱动程序会优先使用 PATH 里找到的那个，所以本页的命令都在 `PATH=/opt/homebrew/opt/llvm/bin:/usr/bin:/bin` 下运行，使用系统的 `ld`（ld-1266.8）。Homebrew 的 `llvm` 包不含 lld，`-fuse-ld=lld` 在本机报 invalid linker name；Linux 上常用 lld 或 gold 加 LLVM 插件。

结果：`sum` 里没有调用了，循环被向量化，每次处理 16 个元素：

```asm
LBB_vec:
  ldp    q17, q18, [x8, #-0x20]
  ldp    q19, q20, [x8], #0x40
  movi.4s v21, #0x1
  mla.4s v21, v17, v1          ; x * 3 + 1，4 个一组
  ...
  saddw2.2d v3, v3, v21        ; 扩展成 64 位累加
  saddw.2d  v2, v2, v21
  ...
  subs   x13, x13, #0x10
  b.ne   LBB_vec
```

`llvm-nm` 还显示了另外两个变化。`_scale` 从最终的可执行文件里消失了，它的唯一用途已经被内联。`sum` 从全局符号 `T` 变成了局部符号 `t`，参数也从 `const vector&` 变成了直接传入 `begin`、`end` 两个指针。链接一个可执行文件时，LTO 知道除了 `main` 之外没有人会从外部调用这些函数，于是把它们**内部化**，可以随意改写签名。

| 构建 | ns/元素 |
|---|---|
| 不开 LTO | 0.92 |
| `-flto` | 0.077 |
| `-flto=thin` | 0.077 |

相差 12 倍，主要来自向量化，而不是省下的调用指令。

!!! note "LTO 只覆盖参与链接的 bitcode"
    LTO 的范围是这一次链接里所有以 bitcode 形式提供的目标文件，包括用 `-flto` 编译的静态库成员。动态库（包括系统的 libc++.dylib）、没有用 `-flto` 编译的目标文件不在其中，跨过它们的调用仍然是普通调用。这也是 [[patterns/pimpl]] 一页指出的：跨共享库边界的调用，LTO 无能为力。

### 完整 LTO 与 ThinLTO

**完整 LTO**（`-flto` 或 `-flto=full`）在链接时把所有模块链接成一个巨大的模块，然后像编译一个超大的 TU 那样优化它。它能看到一切，但这一步基本是串行的，内存占用随整个程序的大小增长。

**ThinLTO**（`-flto=thin`）在编译阶段给每个模块附上一份**摘要**：定义了哪些函数、它们有多大、调用了谁。链接时先只读摘要做全局分析（谁调用谁、哪些符号可以内部化），然后每个模块各自进入一个独立的后端，按需从别的模块**导入**被调用的小函数的函数体，再优化、生成代码。这些后端可以并行，也可以缓存。

| | 完整 LTO | ThinLTO |
|---|---|---|
| 链接时的 IR | 所有模块合成一个 | 每个模块单独处理，按摘要导入函数 |
| 并行 | 优化基本串行 | 后端并行 |
| 增量构建 | 改一个文件，整个程序重新优化 | 有缓存时只重做受影响的模块 |
| 跨模块分析的精度 | 最高 | 依赖摘要，通常接近 |

上面的 `scale` 例子里两者生成的循环相同。

### 构建代价

为了看构建代价，用脚本生成了一个 80 个源文件的程序：每个文件定义一个用 `std::format`、`std::sort`、`std::map`、`std::unordered_map` 处理记录的函数，并调用下一个文件里的函数。编译用 `xargs -P 8` 并行，每种模式测两次，`/usr/bin/time -l` 记录链接的 CPU 时间和最大常驻内存。测量时机器上还有大量其他进程在跑，墙上时间波动很大，表中只列较稳定的 CPU 时间和内存。

| 模式 | 编译 CPU 时间（user+sys） | 链接 CPU 时间（user） | 链接最大内存 | 可执行文件 |
|---|---|---|---|---|
| 不开 LTO | 104–105 s | 0.09–0.10 s | 60 MiB | 1159 KiB |
| `-flto` | 87–95 s | 5.3 s | 261–305 MiB | 957 KiB |
| `-flto=thin` | 82 s | 16–17 s | 206–227 MiB | 1003 KiB |

几点观察：

- 开 LTO 后，编译阶段反而省了时间，因为每个文件不再生成机器码。省下的工作和优化的工作一起转移到了链接步骤。
- 链接从不到 0.1 秒变成数秒，内存涨了 3–5 倍。程序越大，这个差距越大，大型项目的完整 LTO 链接常常是构建里最慢、最吃内存的一步。
- ThinLTO 的链接 CPU 时间比完整 LTO 多，因为每个后端都要重新优化自己和导入的函数；但这些工作分布在多个线程上。负载较低的第一次测量里，墙上时间完整 LTO 7.3 s，ThinLTO 3.2 s。
- 两种 LTO 都让程序变小了，跨模块的内联和死代码删除去掉了重复的模板实例和没人用的函数。

ThinLTO 的缓存对日常的增量构建影响最大。macOS 的 `ld` 用 `-Wl,-cache_path_lto,目录` 指定缓存目录：

```bash
clang++ -flto=thin -Wl,-cache_path_lto,cache o/*.o -o app   # 第一次：user 17.7 s
# 修改一个源文件并只重新编译它
clang++ -flto=thin -Wl,-cache_path_lto,cache o/*.o -o app   # 有缓存：user 0.40 s
clang++ -flto=thin o/*.o -o app2                            # 没有缓存：user 17.2 s
```

完整 LTO 没有这样的增量机制，改一个文件就要重新优化整个程序。常见的做法是日常开发不开 LTO 或只开 ThinLTO，发布构建再开完整 LTO 并配合 PGO。

## 全程序去虚化

```cpp title="op.h"
#pragma once
struct Op {
  virtual ~Op() = default;
  virtual int apply(int x) const = 0;
};
Op* make_op();   // 定义在 op.cpp
```

```cpp title="op.cpp" ok
#include "op.h"
struct Scale final : Op {
  int apply(int x) const override { return x * 3 + 1; }
};
[[gnu::noinline]] Op* make_op() { return new Scale; }
```

```cpp title="main.cpp" ok
#include "bench.hpp"
#include "op.h"
#include <cstdio>
#include <vector>

[[gnu::noinline]] long run(const Op& op, const std::vector<int>& v) {
  long s = 0;
  for (int x : v) s += op.apply(x);   // 虚调用
  return s;
}

int main() {
  bench::prefer_performance_cores();
  std::vector<int> v(1 << 20);
  for (int i = 0; i < (int)v.size(); ++i) v[i] = i & 1023;
  Op* op = make_op();
  auto s = bench::run("run", [&] { long r = run(*op, v); bench::do_not_optimize(r); });
  std::printf("%.3f ns/elem\n", s.median / v.size());
  delete op;
}
```

`run` 里的 `op.apply(x)` 是一次[[g:virtual-function-call|虚调用]]：从对象里取出虚表指针，从虚表里取出函数地址，再间接调用（虚表的布局见 [[toolchain/object-layout-and-vtables]]）。`make_op` 故意不内联，所以即使开了 LTO，`run` 也看不到对象的动态类型是什么。

整个程序里 `Op::apply` 只有 `Scale::apply` 这一个覆盖者。如果编译器能确认这一点，`op.apply(x)` 就只可能调用 `Scale::apply`，可以变成直接调用再内联。Clang 的**全程序去虚化**（whole-program devirtualization）就是做这个的，开关是 `-fwhole-program-vtables`，它要求同时开 LTO，否则报 `invalid argument '-fwhole-program-vtables' only allowed with '-flto'`。

| 构建（都是 `-O2`） | `run` 的循环 | ns/元素 |
|---|---|---|
| 不开 LTO | `blr x8`（间接调用） | 0.92 |
| `-flto` | 间接调用 | 0.92 |
| `-flto -fvisibility=hidden` | 间接调用 | 0.92 |
| `-flto -fwhole-program-vtables` | 间接调用 | 0.92 |
| `-flto -fwhole-program-vtables -fvisibility=hidden` | 内联并向量化，没有调用 | 0.077 |
| `-flto=thin -fwhole-program-vtables -fvisibility=hidden` | 同上 | 0.078 |

只有最后两行生效了。第四行的原因是**LTO 可见性**：去虚化的前提是看到了某个类的所有派生类，而一个默认可见性的类可能在一个之后用 `dlopen` 加载的动态库里被继承，那些覆盖者不在这次链接里。Clang 因此只对具有隐藏 LTO 可见性的类做全程序去虚化。`-fvisibility=hidden` 是最简单的办法；需要导出的类可以单独标 `__attribute__((visibility("default")))`，或者用 `[[clang::lto_visibility_public]]` 声明它的 LTO 可见性是公开的。符号可见性本身见 [[toolchain/linking-and-symbols]]。

去掉 `Scale` 的 `final` 结果不变：这里起作用的是整个程序只有一个覆盖者，而不是 `final`。`final` 只能帮助静态类型就是 `Scale` 的调用点，见 [[perf/compiler-optimizations|编译器优化]] 中的去虚化一节。

这种变换同样是 as-if 规则允许的。标准只规定虚调用调用对象动态类型中的最终覆盖者（[[expr.call#2]]，最终覆盖者的定义见 [[class.virtual#2]]），不规定怎样找到它。标准的程序模型里也没有动态库，在它看来程序在执行前就完整了。`-fvisibility=hidden` 加 `-fwhole-program-vtables` 实际上是你向编译器做出的保证：没有这次链接之外的派生类。如果某个插件真的继承了一个隐藏可见性的类，去虚化后的代码会直接调用错误的函数，这是标准之外的问题，编译器不会报告。

## 剖析引导优化

内联多少、哪个分支放在直通路径上、`switch` 先比较哪个值，编译器平时只能凭静态启发式猜测。**剖析引导优化**（profile-guided optimization，PGO）先让程序在有代表性的输入上跑一遍，记下每个函数、每个分支实际执行了多少次，再把这些计数交给编译器。[[perf/branches|分支]] 一页从分支权重的角度讲了它和 `[[likely]]` 的关系；这里看完整的流程和它对内联、代码排布的影响。

### 三步流程

```bash
# 1. 插桩编译，并在代表性的输入上运行
clang++ -std=c++2c -O2 -fprofile-instr-generate csv.cpp -o cinstr
LLVM_PROFILE_FILE=csv-%p.profraw ./cinstr 1

# 2. 合并原始剖析数据
llvm-profdata merge -o csv.profdata csv-*.profraw

# 3. 带剖析数据重新编译
clang++ -std=c++2c -O2 -fprofile-instr-use=csv.profdata csv.cpp -o cpgo
```

`llvm-profdata` 随 Homebrew 的 `llvm` 包提供，和 `clang++` 在同一个目录，版本必须匹配：`.profraw` 的格式随 LLVM 版本变化。`LLVM_PROFILE_FILE` 里的 `%p` 换成进程号，多次运行、多个进程各写一个文件，`merge` 把它们加在一起。插桩版本运行时更慢，本机这个例子在两次测量中分别比普通版本慢 2.2 倍和 4 倍左右（负载不同）。

`llvm-profdata show --all-functions --counts csv.profdata` 可以查看计数。下面例子里 `parse_field` 被调用了 32 793 216 次，其中三个抛异常的分支计数都是 0。

### 例子：一个解析循环

```cpp title="csv.cpp" ok
#include "bench.hpp"
#include <cstdio>
#include <cstdlib>
#include <stdexcept>
#include <string>

// 解析一个以逗号或换行结尾的整数字段。错误处理分支很长，但几乎从不执行
int parse_field(const char*& p, const char* e, long line) {
  bool neg = false;
  if (p < e && *p == '-') { neg = true; ++p; }
  if (p == e || *p < '0' || *p > '9') {
    std::string msg = "line " + std::to_string(line) + ": expected digit, got '";
    msg += (p == e ? std::string("EOF") : std::string(1, *p));
    msg += "' near \"" + std::string(p, std::min<std::size_t>(e - p, 16)) + "\"";
    throw std::runtime_error(msg);
  }
  long v = 0;
  while (p < e && *p >= '0' && *p <= '9') {
    v = v * 10 + (*p - '0');
    if (v > 2147483647L) {
      std::string msg = "line " + std::to_string(line) + ": overflow";
      throw std::out_of_range(msg);
    }
    ++p;
  }
  if (p < e && *p != ',' && *p != '\n') {
    std::string msg = "line " + std::to_string(line) + ": bad separator '" + std::string(1, *p) + "'";
    throw std::runtime_error(msg);
  }
  if (p < e) ++p;
  return neg ? -int(v) : int(v);
}

[[gnu::noinline]] long sum_csv(const std::string& s) {
  const char* p = s.data();
  const char* e = p + s.size();
  long total = 0, line = 1;
  while (p < e) {
    bool eol = false;
    int v = parse_field(p, e, line);
    if (p[-1] == '\n') eol = true;
    total += v;
    line += eol;
  }
  return total;
}

int main(int argc, char** argv) {
  std::srand(argc > 1 ? std::atoi(argv[1]) : 1);   // 训练和测量用不同的种子
  std::string s;
  while (s.size() < (8u << 20)) {
    for (int k = 0; k < 8; ++k) {
      if (std::rand() % 4 == 0) s += '-';
      s += std::to_string(std::rand() % 100000);
      s += k == 7 ? '\n' : ',';
    }
  }
  bench::prefer_performance_cores();
  auto st = bench::run("sum_csv", [&] { long r = sum_csv(s); bench::do_not_optimize(r); });
  std::printf("%.3f ns/byte\n", st.median / s.size());
}
```

用种子 1 生成的数据训练，用种子 2 生成的数据测量。本机交替运行多轮，取各轮中位数的最小值：

| 构建 | ns/字节（多次测量的范围） |
|---|---|
| `-O2` | 1.21–1.30 |
| `-O2` + PGO | 1.11–1.16 |

PGO 版本快约 10%。为了排除代码对齐的偶然影响，又分别用 `-falign-loops=16/32/64` 和 `-falign-functions=64` 各编译了一份：普通版本在 1.21–1.25 之间，PGO 版本在 1.105–1.115 之间，差距没有因为对齐而消失。

### 它改变了什么

没有剖析数据时，`parse_field` 带着三段构造字符串、抛异常的代码，有 400 多条指令，超过了内联阈值。`sum_csv` 只能调用它，而 `p` 是按引用传入的，`parse_field` 每读一个字符都要把 `p` 写回内存：

```asm
; -O2：parse_field 的数字循环
LBB1_digit:
  ldrb  w13, [x8]
  sub   w14, w13, #0x30
  cmp   w14, #0x9
  b.hi  LBB1_sep
  mul   x10, x10, x11
  add   x10, x10, w14, uxtb
  cmp   x10, x12
  b.ge  LBB1_overflow
  add   x8, x8, #0x1
  str   x8, [x0]           ; 每个字符都把 p 存回调用者的变量
  cmp   x8, x1
  b.ne  LBB1_digit
```

剖析数据告诉编译器，这个调用点执行了三千多万次，而三个错误分支一次也没走过。Clang 对热的调用点使用高得多的内联阈值，于是把 `parse_field` 内联进了 `sum_csv`（`sum_csv` 从 44 条指令变成 405 条）。`p` 留在寄存器里，每个字符少一次存储。错误处理代码被排到了循环之后，热路径是一段连续的直通代码：

```asm
; PGO：内联后的热循环（节选）
LBB0_field:
  ldrb  w13, [x14], #0x1   ; 读第一个字符
  cmp   w13, #0x2d         ; 是 '-' 吗
  ...
LBB0_digit:
  mul   x14, x14, x11
  add   x14, x14, w16, uxtb
  cmp   x14, x12
  b.ge  LBB0_overflow      ; 冷：跳到函数末尾
  cmp   x21, x20
  b.eq  LBB0_done_field
  ldrb  w15, [x21], #0x1
  sub   w16, w15, #0x30
  cmp   w16, #0x9
  b.ls  LBB0_digit         ; 热：留在循环里
  cmp   w15, #0x2c
  b.eq  LBB0_next          ; 逗号
  cmp   w15, #0xa
  b.eq  LBB0_next          ; 换行
  b     LBB0_bad_sep       ; 冷：跳到函数末尾
  ...
LBB0_expected_digit:        ; 冷代码：构造错误信息并抛出
  bl    _strlen
  ...
```

这几种变化就是 PGO 的主要收益来源：

- 内联：热调用点内联得更积极，冷调用点几乎不内联，代码总量不一定增加。
- 代码块排布：执行次数多的后继放在直通位置，冷代码移到函数末尾，热代码在指令缓存里更紧凑。
- 寄存器分配和循环优化：知道哪条路径热，溢出到栈上的代价就放在冷路径上。
- `switch` 和间接调用：常见的值和目标可以单独比较，见下文。

PGO 不能让一个本来就难以预测的分支变得可预测。本机写过一个对随机文本分类的词法分析器，PGO 前后都在 3 ns/字节左右，时间几乎全花在预测失败上，代码怎么排都无济于事。分支预测本身见 [[perf/branches|分支]]。

### 间接调用提升

```cpp title="disp.cpp（节选）"
using Handler = void (*)(State&, const Event&);
Handler table[4] = {on_add, on_max, on_reset, on_error};

[[gnu::noinline]] State process(const std::vector<Event>& evs) {
  State s;
  for (const Event& e : evs) {
    if (e.kind >= 4) [[unlikely]] { ++s.errors; continue; }
    table[e.kind](s, e);   // 间接调用，90% 的事件调用 on_add
  }
  return s;
}
```

PGO 可以记录每个间接调用点实际调用了哪些目标，再把最常见的目标**提升**成一次比较加直接调用：

```asm
; IR 插桩 PGO 之后的 process（节选）
  ldr   x8, [x22, x8, lsl #3]   ; 从 table 取函数指针
  cmp   x8, x23                 ; x23 = on_add 的地址
  b.ne  LBB_indirect            ; 不是 on_add：仍然 blr x8
  ldrsw x8, [x20, #0x4]         ; 是：on_add 的函数体已内联
  ldr   x9, [x19]
  add   x8, x9, x8
  ...
```

记录调用目标的叫**值剖析**（value profiling）。本机 Clang 23 的 `-fprofile-instr-generate` 默认不做值剖析：`llvm-profdata show --ic-targets` 显示这个调用点 `Indirect Call Site Count: 0`，PGO 后的代码仍是 `blr x8`，加 `-mllvm -enable-value-profiling` 才会记录。改用 `-fprofile-generate` / `-fprofile-use` 就有了，它显示四个目标的计数，`on_add` 占 89.99%。

| 构建 | ns/事件 |
|---|---|
| `-O2` | 1.96–2.12 |
| 前端插桩 PGO（`-fprofile-instr-*`） | 1.97–2.01 |
| IR 插桩 PGO（`-fprofile-*`） | 1.69–1.70 |

两种插桩的区别在于插入计数器的时机。`-fprofile-instr-generate` 在 Clang 前端按源代码结构插桩，同一套机制也用于代码覆盖率（`-fcoverage-mapping`），计数能对应到源代码的区域。`-fprofile-generate` 在 LLVM IR 上插桩，插桩前已经做过一部分优化，计数器更少。两者的剖析数据都用 `llvm-profdata merge` 处理。虚调用的去虚化也能用同样的值剖析做推测性提升。

### 剖析数据过时

修改源码之后继续使用旧的剖析数据是常见情况。把 `parse_field` 中分隔符的判断改成也接受 `'\r'`：

```cpp
if (p < e && *p != ',' && *p != '\n' && *p != '\r') {
```

再用原来的 `csv.profdata` 编译：

```text
warning: profile data may be out of date: of 10 functions, 1 has mismatched data that will be ignored [-Wprofile-instr-out-of-date]
```

前端插桩的剖析数据按函数记录一个由控制流结构算出的哈希。函数的分支结构变了，哈希就对不上，Clang 丢弃这个函数的全部计数，其他函数的数据照常使用。结果是 `parse_field` 又不被内联了，`sum_csv` 回到 44 条指令、一次调用。本机这次的计时与 PGO 版本接近，原因没有分析清楚（修改后的源码本身不开 PGO 就比原来快几个百分点），这里只能确定代码生成退回去了。

过时的剖析数据还有更隐蔽的一种：代码没改，但负载变了，剖析数据描述的已经不是真实的执行情况。[[perf/branches|分支]] 一页测量了用相反的分布训练时 PGO 让程序变慢的情况。实践中的做法是：

- 把训练运行纳入构建流程，和源码一起更新剖析数据；
- 用 `-Wprofile-instr-out-of-date`（默认开启）和 `-Wprofile-instr-unprofiled` 留意不匹配和没有数据的函数；
- 训练输入取自真实负载，覆盖主要的使用场景。

### 采样式 PGO 与 BOLT

插桩式 PGO 需要一个专门的插桩版本和一组训练输入。另外两类工具直接从正常构建的程序上收集数据。本机是 macOS，下面两种工具都无法运行，这里只描述它们的工作方式，没有实测。

**采样式 PGO**（AutoFDO）在生产环境中用硬件性能计数器对正常的优化构建采样，Linux 上通常是 `perf record` 加分支记录（Intel 的 LBR，Arm 上的 SPE 或 BRBE 等），再用 `create_llvm_prof` 之类的工具借助调试信息把地址映射回源代码行，生成的剖析文件用 `-fprofile-sample-use=` 交给 Clang。它没有插桩开销，数据来自真实负载，但精度不如插桩计数，而且依赖调试信息把地址对应回源代码。

**BOLT**（`llvm-bolt`）是一个链接后优化器：它直接读取已经链接好的二进制文件和 `perf` 采集的剖析数据，重新排布函数和代码块，再写出新的二进制文件。它处理的是最终的机器码，能看到编译器看不到的东西，例如跨所有目标文件和静态库的函数顺序。BOLT 只支持 ELF 格式（Linux），通常要求链接时保留重定位信息（`-Wl,--emit-relocs`），不支持 macOS 的 Mach-O。它常和 LTO、PGO 叠加使用，先由编译器做内联等决定，再由 BOLT 调整排布。

## `-O3` 与 `-O2`

`-O3` 在 `-O2` 的基础上打开一些更激进的变换（例如更高的内联阈值）。上面两个程序用两种级别各编译一份，比较 `__text` 中的指令和运行时间：

| 程序 | `-O2` 指令数 | `-O3` 指令数 | `-O2` ns | `-O3` ns |
|---|---|---|---|---|
| `csv.cpp` | 1039 | 1243 | 1.26 | 1.24 |
| `disp.cpp` | 474 | 523 | 1.98 | 1.98 |

`-O3` 生成的代码确实不同，但运行时间在测量误差以内。在 `csv.cpp` 里，`-O3` 仍然没有内联 `parse_field`：它只是按固定的规则把阈值调高了一点，而 PGO 是按实际热度做决定。哪个级别更快只能对具体程序测量，不能凭级别的数字推断；`-O3` 生成的代码更大，对指令缓存敏感的大程序有时反而更慢。各级别打开了哪些优化见 [[perf/compiler-optimizations|编译器优化]]。

## `-march=native` 与 `-mcpu`

这些选项决定编译器可以使用哪些指令，以及按哪种微架构调优。用 `clang++ -### ...` 查看驱动程序实际传给前端的参数：

| 选项 | `-target-cpu` | 架构版本 | `-tune-cpu` |
|---|---|---|---|
| 不写 | `apple-m1` | v8.4a | `apple-m5` |
| `-mcpu=native` | `apple-m2` | v8.6a | 不写（按 `apple-m2`） |
| `-march=native` | `apple-m2` | v8.6a | `apple-m5` |
| `-mcpu=apple-m2` | `apple-a15` | v8.6a | 不写 |

在 Apple 平台上，默认目标已经是 M1，NEON、点积（`sdot`）、FMA 都可以直接用。M2 只多了 BF16、`i8mm` 等少数扩展。`csv.cpp`、`disp.cpp`，以及一个 `int8` 点积和一个 `float` 的 `y += a * x` 循环，在默认、`-mcpu=apple-m2`、`-mcpu=native` 下生成的代码完全相同（反汇编逐字一致）。在本机，这些选项对一般代码没有可测的影响。

x86-64 不一样。Linux 上 `x86_64` 的默认目标是最初的 x86-64 基线，只保证有 SSE2。同一个 `y[i] += a * x[i]` 循环交叉编译（`--target=x86_64-linux-gnu -O2 -S`）：

| 选项 | 循环里的关键指令 | 每条指令处理的 `float` |
|---|---|---|
| 默认 | `mulps` + `addps`，`xmm` | 4 |
| `-march=x86-64-v3` | `vfmadd213ps`，`ymm` | 8 |
| `-march=x86-64-v4` | `vfmadd213ps`，`ymm` | 8 |
| `-march=znver4` | `vfmadd213ps`，`zmm` | 16 |

`x86-64-v4` 包含 AVX-512，但 Clang 对通用的 v4 目标仍优先使用 256 位向量，按 `znver4` 调优时才用 512 位。向量化与目标指令集的更多关系见 [[perf/vectorization|向量化]]。

这些选项有两个后果需要注意。

第一，生成的程序只能在支持这些指令的 CPU 上运行。`-march=native` 编译出的程序拿到更老的机器上，可能在执行到某条新指令时因非法指令而终止。分发给别人的程序应当指定一个明确的目标，例如 `-march=x86-64-v3`，而不是 `native`。

第二，浮点结果可能随目标改变。上表中默认目标没有 FMA 指令，乘和加分两步舍入；`x86-64-v3` 用一条 `vfmadd`，只舍入一次。[[expr.pre#6]] 允许浮点表达式的结果以超出类型要求的精度表示，Clang 默认的 `-ffp-contract=on` 据此在同一个表达式内把乘加合并成 FMA。所以同一份源码换一个 `-march`，最后一位可能不同；需要逐位可复现时用 `-ffp-contract=off`。

## LTO 让 ODR 违规显形

```cpp title="cfg.h"
#pragma once
struct Config {
  int retries;
#ifdef WITH_TIMEOUT
  int timeout_ms;
#endif
};
inline Config default_config{3
#ifdef WITH_TIMEOUT
  , 500
#endif
};
```

```cpp title="a.cpp" ifndr
#define WITH_TIMEOUT
#include "cfg.h"
int timeout() { return default_config.timeout_ms; }
```

```cpp title="b.cpp"
#include "cfg.h"
int retries() { return default_config.retries; }
```

```cpp title="main.cpp"
#include <cstdio>
int timeout();
int retries();
int main() { std::printf("%d %d\n", retries(), timeout()); }
```

`Config` 和 [[g:inline-variable|inline 变量]] `default_config` 在两个 TU 里的定义由不同的记号组成，违反了 [[basic.def.odr#16]]（¶16.4 要求各处定义的记号序列相同）。程序非良构，不要求诊断（[[g:ifndr|IFNDR]]），任何结果都不违反标准。本机的实际结果取决于构建方式和链接顺序：

| 构建 | 链接顺序 `a.o b.o` | 链接顺序 `b.o a.o` |
|---|---|---|
| `-O0` | `3 500` | `3 0` |
| `-O2` | `3 500` | `3 0` |
| `-O2 -flto=thin` | `3 500` | `3 0` |
| `-O2 -flto` | `3 500` | `3 -327417768` |

不开 LTO 时，`default_config` 是一个弱定义，链接器按顺序留下第一个，不比较大小，也不比较内容（[[toolchain/linking-and-symbols]]）。`b.o` 在前时留下的是 4 字节的版本，`timeout()` 读的是这个对象后面的 4 个字节，碰巧是 0。程序看起来只是少了一个配置项。ASan 也没有报告这次越界读。

开完整 LTO 时，LTO 同样只留下一份定义，但它接下来会优化整个程序。它发现 `default_config` 从未被写过，于是把 `retries()` 折叠成常量 3；`timeout()` 读取的是一个 4 字节对象之外的位置，这在 LTO 看来是越界访问，结果没有定义，它就不为第二个参数准备任何值。最终的 `main` 只剩下：

```asm
_main:
  ...
  mov  w8, #0x3          ; retries() 折叠成了 3
  str  x8, [sp]          ; 第二个可变参数的位置从未写入
  ...
  bl   _printf
```

`default_config`、`retries`、`timeout` 都从可执行文件里消失了，第二个数是栈上残留的任意值。不开 LTO 时被链接器掩盖的错误，在 LTO 下变成了完全不同的行为。

这类问题的来源通常是：同一个头文件在不同的 TU 里看到不同的宏（`NDEBUG`、功能开关、`_LIBCPP_*` 之类的库配置）、同名的结构体在两个 `.cpp` 里各写了一份、链接了用不同选项编译的同一个库。开 LTO 后程序行为突然改变，在怀疑编译器之前，先检查这些地方。GCC 的 `-flto` 配合 `-Wodr` 能发现一部分类型不一致（本机没有 GCC，未验证）；Clang 对传统的头文件构建方式没有对应的跨 TU 检查，见 [[std/ifndr]]。

## 思考题

!!! question "1"
    `scale` 改写成头文件里的 `inline int scale(int x) { return x * 3 + 1; }`，不开 LTO，`sum` 的性能会怎样？这对 ODR 有什么要求？

<details markdown="1">
<summary>答案</summary>

`main.cpp` 包含了函数体，编译 `sum` 时就能内联并向量化，结果应与 LTO 版本相同。代价是每个包含这个头文件的 TU 都要编译一遍它。inline 函数可以在多个 TU 中定义，但按 [[basic.def.odr#16]]，各处的定义必须由相同的记号组成、名字指代相同的实体，否则程序非良构，不要求诊断。只要头文件不受不同的宏影响，这一点自然满足。
</details>

!!! question "2"
    一个应用程序把核心逻辑放在自己的动态库 `libcore.dylib` 里，主程序和这个库都用 `-flto` 编译。主程序里对 `libcore` 中小函数的调用能被内联吗？对 `libcore` 里定义的抽象类做全程序去虚化呢？

<details markdown="1">
<summary>答案</summary>

都不能跨过动态库的边界。LTO 的范围是一次链接，主程序和 `libcore.dylib` 是两次独立的链接，主程序链接时看到的只是动态库导出的符号，没有函数体。去虚化同理：`libcore` 中的类如果要被主程序使用，它本身就必须是默认可见性的，LTO 可见性是公开的，`-fwhole-program-vtables` 不会处理它；即使强行声明为隐藏，主程序也可能定义新的派生类，去虚化的前提不成立。需要跨边界内联时，把热点函数放进头文件，或者改为静态链接。
</details>

!!! question "3"
    同一个程序，用 `-O2 -flto -fprofile-instr-use=x.profdata` 构建。剖析数据是在不开 LTO 的插桩版本上收集的，能用吗？

<details markdown="1">
<summary>答案</summary>

能。本机用不开 LTO 收集的 `csv.profdata` 加 `-flto` 构建 `csv.cpp`，没有警告，`parse_field` 同样被内联。前端插桩的计数按函数名和函数的控制流哈希记录，与之后的优化、是否开 LTO 无关，Clang 在把源码翻译成 IR 时就把计数附到分支上。LTO 链接时，这些分支权重和函数的热度随 bitcode 一起进入跨模块的内联和排布决定。常见的发布构建正是插桩构建、训练、再以 LTO 加 PGO 构建。只要源码没变，剖析数据就不会过时；源码改了，按上面的警告处理。
</details>

## 小结

| 手段 | 解决什么 | 怎样开 | 代价与前提 |
|---|---|---|---|
| 头文件中的 inline 函数 | 跨 TU 内联 | 把定义放进头文件 | 编译时间；ODR 要求各处定义相同 |
| 完整 LTO | 跨 TU 内联、内部化、死代码删除 | 编译和链接都加 `-flto` | 链接慢、内存大，没有增量 |
| ThinLTO | 同上，可扩展 | `-flto=thin`，`-Wl,-cache_path_lto,目录` | 链接 CPU 时间更多，但并行、可缓存 |
| 全程序去虚化 | 只有一个覆盖者的虚调用 | LTO + `-fwhole-program-vtables` + 隐藏 LTO 可见性 | 保证没有链接之外的派生类 |
| 插桩 PGO | 内联、排布、间接调用按实际热度决定 | `-fprofile-instr-generate` → 运行 → `llvm-profdata merge` → `-fprofile-instr-use` | 训练流程；源码或负载变化时数据过时 |
| 采样 PGO、BOLT | 用生产环境的数据优化 | `-fprofile-sample-use`，`llvm-bolt` | Linux/ELF；需要硬件采样支持 |
| `-O3` | 更激进的固定规则 | `-O3` | 不一定更快，要测量 |
| `-march`/`-mcpu` | 新指令、更宽的向量 | `-march=x86-64-v3` 等 | 程序只能在支持的 CPU 上运行，浮点结果可能变化 |
