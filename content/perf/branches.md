---
title: 分支与分支预测
summary: 条件分支和间接调用在现代 CPU 上的真实代价：分支预测怎样工作，预测失败值多少纳秒，编译器什么时候自己消掉分支，无分支写法什么时候赢、什么时候输，likely/unlikely、PGO、虚调用、switch 和 std::unreachable 在汇编和实测里各改变了什么。
group: 代码
status: draft
order: 75
since: c++20
papers: P0479R5, P0627R6
related: dcl.attr.likelihood, utility.undefined, intro.abstract, intro.races, stmt.switch, class.virtual, expr.log.and, perf/compiler-optimizations, perf/lto-pgo, perf/measuring, perf/reading-assembly, perf/vectorization, toolchain/object-layout-and-vtables
tags: 性能, 分支预测, 汇编, likely, PGO, 虚函数, switch
updated: 2026-10-19
---

!!! tldr
    - 分支本身几乎免费，贵的是预测失败：本机一次条件分支预测失败大约损失 5 ns，相当于十几到二十个周期。
    - 排序数组求和的老例子在 Clang 23 的 `-O1` 下已经变成 `csel`，`-O2` 下被向量化，排序与否不再有差别；只有编译器不能消掉的分支（比如条件写内存）才会暴露预测失败的代价。
    - 无分支写法把控制依赖换成数据依赖，两边都要算。分支难以预测时它赢，分支可预测而某一边很贵时它输，本机实测相差 5 倍。
    - `[[likely]]`/`[[unlikely]]` 只改变分支权重，进而改变代码块的排布，不改变预测器。猜对了本机快 1.7 倍，猜错了慢 2 倍；PGO 用真实的执行次数代替猜测，但训练数据不具代表性时同样会变慢。
    - 虚调用和稠密 `switch` 都是间接跳转：目标固定时和直接调用差不多，目标随机时每次多花几纳秒。`std::unreachable()` 能删掉跳转表前的范围检查，本机测不出差别。

!!! note "实验环境与测量方法"
    所有数字来自 Apple M2 Pro（arm64，macOS），Homebrew Clang 23.1.3 与 libc++，除非另行说明都用 `clang++ -std=c++2c -O2`。数据是本机的一次观察，换一颗 CPU、换一个编译器版本，数值甚至结论都可能变化。测量时机器负载很高，绝对数值可能偏大，误预测密集的测试波动尤其明显，正文给出了多次运行的范围。同一进程里先后测得的比例比绝对值可靠，关于编译器做了什么的结论以汇编为准。

    计时用下面这个很小的工具：先预热一次，再重复若干次，取中位数。`escape` 用一条空的内联汇编假装读取了结果，编译器看不到这条汇编做了什么，只好真的把结果算出来。原理和更完整的写法见 [[perf/measuring|测量]]。

    ```cpp title="bench.h"
    #pragma once
    #include <algorithm>
    #include <chrono>
    #include <cstdio>
    #include <vector>

    template <class T>
    inline void escape(T const& v) {
      asm volatile("" : : "r"(&v) : "memory");
    }

    template <class F>
    double bench_ns(F f, int reps = 15) {
      using clk = std::chrono::steady_clock;
      f();                       // 预热
      std::vector<double> t;
      for (int i = 0; i < reps; ++i) {
        auto a = clk::now();
        f();
        auto b = clk::now();
        t.push_back(std::chrono::duration<double, std::nano>(b - a).count());
      }
      std::sort(t.begin(), t.end());
      return t[t.size() / 2];    // 中位数
    }
    ```

## 排序过的数组为什么更快

```cpp title="sum.cpp" ok
#include "bench.h"
#include <random>

long sum_big(const std::vector<int>& v) {
  long s = 0;
  for (int x : v)
    if (x >= 128) s += x;
  return s;
}

int main() {
  std::vector<int> v(1 << 20);
  std::mt19937 rng(42);
  for (int& x : v) x = rng() % 256;
  auto run = [&](const char* name) {
    double ns = bench_ns([&] { long s = sum_big(v); escape(s); });
    std::printf("%-9s %6.2f ns/elem\n", name, ns / v.size());
  };
  run("random");
  std::sort(v.begin(), v.end());
  run("sorted");
}
```

这是一个流传很广的例子：同一组数据，排序之后求和更快。在本机分别用不同的优化级别编译，结果是：

| 优化级别 | 随机顺序 | 排序后 |
|---|---|---|
| `-O0` | 8.65 ns/元素 | 4.78 ns/元素 |
| `-O1` | 0.34 | 0.39 |
| `-O2` | 0.08 | 0.08 |
| `-O3` | 0.08 | 0.08 |

只有 `-O0` 重现了这个现象。看一下各级别生成的循环体就知道原因（`clang++ -std=c++2c -O1 -S`，只保留循环）：

<div class="compare" markdown="1">

```asm
; -O0：真正的条件分支
  ldr   w8, [sp, #4]
  subs  w8, w8, #128
  b.ge  LBB0_3     ; x >= 128 就跳
  b     LBB0_4
LBB0_3:
  ldrsw x9, [sp, #4]
  ldur  x8, [x29, #-16]
  add   x8, x8, x9
  stur  x8, [x29, #-16]
```

```asm
; -O1：没有条件跳转
LBB0_2:
  ldr   w10, [x8], #4
  cmp   w10, #127
  csel  w10, w10, wzr, gt
  add   x0, x0, x10
  cmp   x8, x9
  b.ne  LBB0_2     ; 只剩循环回边
```

</div>

`-O1` 把 `if` 换成了 `csel`（conditional select）：先比较，再按比较结果从两个寄存器里选一个，`x > 127` 时选 `x`，否则选零寄存器 `wzr`，然后无条件地加。x86-64 上对应的指令是 `cmov`，用 `--target=x86_64-linux-gnu -O1` 编译同一个函数能看到 `cmovlel`。`-O2` 更进一步，用 NEON 一次比较 4 个元素（`cmgt.4s`），用比较结果作掩码与原值按位与，再累加，整个循环同样没有数据相关的跳转。向量化的细节见 [[perf/vectorization|向量化]]。

编译器有权这样改写，依据是 as-if 规则（[[g:as-if-rule]]）：实现只需模拟抽象机的可观察行为（[[intro.abstract#1]]）。这里原本就无条件地读了 `x`，加零和不加没有可观察的区别，所以分支是否存在不在标准的规定之内。

## 分支预测器在做什么

CPU 把一条指令拆成取指、译码、执行、写回等多个阶段，像流水线一样同时处理几十上百条指令。遇到条件跳转时，跳不跳要等比较做完才知道，但流水线不能停下来等，否则每个分支都要空转十几个周期。

所以 CPU 会先猜一个方向，沿着猜的路径继续取指和执行，这叫**推测执行**（speculative execution）。负责猜的部件叫**分支预测器**（branch predictor）。它记录每个分支最近的跳转历史，以及到达这里之前其他分支的走向，用这些模式预测下一次。对间接跳转（目标地址放在寄存器里的跳转，如虚调用），它还要预测跳到哪个地址。

猜对了，分支几乎不花时间。猜错了，叫**分支预测失败**（branch misprediction）：推测执行的结果全部作废，从正确的地址重新取指，损失的时间大约等于流水线的深度。数据有序时，`x >= 128` 先是一长串假、后是一长串真，预测器几乎总能猜对；数据随机时，它只能猜对一半左右。

## 让分支留下来：条件写内存

要观察预测失败的代价，需要一个编译器消不掉的分支。把求和改成过滤，只有满足条件的元素才写到输出数组：

```cpp title="filter.cpp" godbolt flags="-std=c++2c -O2" ok
long filter_big(const int* in, long n, int* out) {
  long k = 0;
  for (long i = 0; i < n; ++i)
    if (in[i] >= 128) out[k++] = in[i];
  return k;
}
```

`-O2` 把循环展开了 8 次，但每个元素仍然有一个条件跳转，跳过 `str`：

```asm
LBB0_6:
  ldur  w13, [x12, #-16]
  cmp   w13, #128
  b.lt  LBB0_8          ; 小于 128 就跳过写入
  str   w13, [x2, x0, lsl #2]
  add   x0, x0, #1
LBB0_8:
  ldur  w13, [x12, #-12]
  ...
```

编译器不能把它改成无条件写入。条件不成立时，抽象机根本不写 `out[k]`；`out` 可能只够放满足条件的元素，也可能有别的线程正在读那个位置。标准在 [[intro.races#19]] 的注里明确说，引入抽象机不会执行的写操作一般是不允许的，因为这可能制造原本不存在的数据竞争。

用这个函数扫一个 1M 元素的数组，控制条件成立的概率 p：

| p（条件成立） | 0% | 1% | 5% | 10% | 25% | 50% | 75% | 90% | 99% | 100% | 排序后 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 有分支（ns/元素） | 0.31 | 0.36 | 0.56 | 0.81 | 1.59 | 3.03 | 1.75 | 0.76 | 0.33 | 0.31 | 0.31 |

曲线以 50% 为顶点对称，排序后的数据和 p = 0% 一样快。50% 时大约每两个元素猜错一次，比完全可预测时多出约 2.7 ns/元素，折算下来每次预测失败约 5.4 ns；按 M2 Pro 性能核约 3.5 GHz 的主频，大约是 19 个周期。这是从计时反推的估计，不是硬件计数器的读数，读计数器的方法见 [[perf/profiling|性能剖析]]。

## 无分支写法

### 条件选择：把条件变成数据

既然编译器不能替我们无条件写入，可以手动写成无条件写、有条件前进：

<div class="compare" markdown="1">

```cpp
// 有分支
for (long i = 0; i < n; ++i)
  if (in[i] >= 128)
    out[k++] = in[i];
```

```cpp
// 无分支：out 至少要有 n 个元素
for (long i = 0; i < n; ++i) {
  out[k] = in[i];          // 总是写
  k += (in[i] >= 128);     // 条件只决定下标
}
```

</div>

右边的写法改变了程序的语义：它会写 `out[k]` 之后的位置，所以调用者必须保证 `out` 有 `n` 个元素的空间。这正是编译器不能自动做的那一步。生成的代码用 `cinc`（条件加一）代替了跳转：

```asm
LBB1_3:
  ldur  w12, [x11, #-4]
  str   w12, [x2, x8, lsl #2]   ; 无条件写
  cmp   w12, #127
  cinc  x8, x8, gt              ; 条件成立时 k + 1
  ...
```

无分支版本在所有 p 下都是 0.31 ns/元素左右，和有分支版本最好的情况一样。它没有预测可言，也就没有预测失败。

### 算术掩码与查表

另外两种常见手法：用比较结果构造全 0 或全 1 的**掩码**（mask），按位与选出结果；或者把一串 `if` 预先算成一张表，运行时只做一次下标访问。

```cpp
unsigned m = -(unsigned)(x >= 1000);     // 成立时 0xFFFFFFFF，否则 0
r = (a & m) | (b & ~m);                  // 成立选 a，否则选 b
```

查表适合把输入分成几类的场合。下面把字符分成数字、大写、小写、其他四类：

```cpp title="lut.cpp" ok
#include "bench.h"
#include <array>
#include <random>

constexpr int cls_if(unsigned char c) {
  if (c >= '0' && c <= '9') return 1;
  if (c >= 'A' && c <= 'Z') return 2;
  if (c >= 'a' && c <= 'z') return 3;
  return 0;
}

constexpr auto table = [] {         // 编译期算好 256 项
  std::array<unsigned char, 256> t{};
  for (int c = 0; c < 256; ++c) t[c] = cls_if(c);
  return t;
}();

[[gnu::noinline]] long sum_if(const unsigned char* s, long n) {
  long r = 0;
  for (long i = 0; i < n; ++i) r += cls_if(s[i]);
  return r;
}
[[gnu::noinline]] long sum_lut(const unsigned char* s, long n) {
  long r = 0;
  for (long i = 0; i < n; ++i) r += table[s[i]];
  return r;
}

int main() {
  const long n = 1 << 20;
  std::vector<unsigned char> s(n);
  std::mt19937 rng(7);
  const char* alpha = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                      "abcdefghijklmnopqrstuvwxyz +-*/.,";
  for (auto& c : s) c = alpha[rng() % 68];
  double a = bench_ns([&] { long r = sum_if(s.data(), n); escape(r); });
  double b = bench_ns([&] { long r = sum_lut(s.data(), n); escape(r); });
  std::sort(s.begin(), s.end());
  double c = bench_ns([&] { long r = sum_if(s.data(), n); escape(r); });
  std::printf("random: if %.3f  lut %.3f   sorted: if %.3f ns/byte\n",
              a / n, b / n, c / n);
}
```

`cls_if` 在 `-O2` 下仍然是两个条件跳转加一个 `csel`。本机结果：随机文本上 `if` 链 3.33 ns/字节，查表 0.22 ns/字节；把文本排序后 `if` 链降到 0.53 ns/字节。查表快了 15 倍，排序后的 `if` 链也快了 6 倍，差距几乎全部来自预测失败。查表的前提是表足够小，能一直待在 L1 缓存里，这里只有 256 字节；表大了，换来的可能是缓存缺失，见 [[perf/memory-hierarchy|内存层次]]。

### 什么时候无分支反而慢

无分支代码把两条路径都算了一遍，再丢掉一个结果。如果其中一条路径很贵而且很少走，分支能让 CPU 直接跳过它，无分支写法却每次都要付钱。下面的 `slow` 做三次除数在运行期才知道的除法：

```cpp title="lose.cpp" ok
#include "bench.h"
#include <random>

inline unsigned slow(unsigned x, unsigned d) {  // 运行期除数：真正的除法指令
  return x / d / d / d;
}

[[gnu::noinline]] unsigned long sum_branchy(const unsigned* v, long n, unsigned d) {
  unsigned long s = 0;
  for (long i = 0; i < n; ++i)
    s += v[i] >= 1000 ? slow(v[i], d) : v[i];
  return s;
}

[[gnu::noinline]] unsigned long sum_mask(const unsigned* v, long n, unsigned d) {
  unsigned long s = 0;
  for (long i = 0; i < n; ++i) {
    unsigned x = v[i];
    unsigned m = -(unsigned)(x >= 1000);    // 全 1 或全 0
    s += (slow(x, d) & m) | (x & ~m);       // 两边都算
  }
  return s;
}

int main() {
  const long n = 1 << 20;
  volatile unsigned vd = 3; unsigned d = vd;
  std::vector<unsigned> v(n);
  std::mt19937 rng(1);
  for (int pct : {1, 50}) {
    for (auto& x : v) x = (int)(rng() % 100) < pct ? 5000 + rng() % 1000 : rng() % 1000;
    double a = bench_ns([&] { auto s = sum_branchy(v.data(), n, d); escape(s); });
    double b = bench_ns([&] { auto s = sum_mask(v.data(), n, d); escape(s); });
    std::printf("slow path %2d%%: branchy %.3f  mask %.3f ns/elem\n", pct, a / n, b / n);
  }
}
```

| 走慢路径的比例 | 有分支 | 掩码 |
|---|---|---|
| 1% | 0.36 ns/元素 | 1.85 ns/元素 |
| 50% | 2.92 | 1.85 |

除数用 `volatile` 读进来，是为了不让编译器把除以常数换成乘法。慢路径只占 1% 时，分支几乎总被猜对，有分支的版本比掩码快 5 倍；占 50% 时预测失败占了上风，掩码赢。顺带一提，编译器认出了掩码写法的意图，`sum_mask` 的循环里是 12 条 `udiv` 加 4 条 `csel`，而 `sum_branchy` 保留了条件跳转，没有自作主张地改成无分支。

这说明无分支不是一条通用的优化。它适合两边都便宜、而条件难以预测的场合；分支可预测、或者某一边明显更贵时，留着分支更好。编译器在两者之间做取舍时依据的是代价模型和分支概率，后者正是下一节的话题。

## `[[likely]]` 与 `[[unlikely]]` {{c++20}}

!!! std "[dcl.attr.likelihood]/2（注）"
    The use of the likely attribute is intended to allow implementations to optimize for the case where paths of execution including it are arbitrarily more likely than any alternative path of execution that does not include such an attribute.

这两个属性放在语句或标签上（[[dcl.attr.likelihood#1]]），告诉编译器这条路径比其他路径常见得多或少得多。上面的话出自注，没有规范效力：标准不要求实现据此做任何事，忽略它们完全符合标准。写法和位置规则见 [[dcl.attr.likelihood]]。

### 它在汇编里改变了什么

```cpp title="process.cpp" godbolt flags="-std=c++2c -O2" ok
void log_error(int);
int process(int x) {
  if (x < 0) [[likely]] {     // 故意标反，看看会发生什么
    log_error(x);
    return -1;
  }
  return x * 3 + 1;
}
```

去掉属性和加上属性的 `-O2` 输出：

<div class="compare" markdown="1">

```asm
; 没有属性
  tbnz  w0, #31, LBB0_2  ; 负数才跳
  add   w8, w0, w0, lsl #1
  add   w0, w8, #1
  ret
LBB0_2:
  stp   x29, x30, [sp, #-16]!
  mov   x29, sp
  bl    __Z9log_errori
  mov   w0, #-1
  ldp   x29, x30, [sp], #16
  ret
```

```asm
; [[likely]] 标在错误路径上
  tbz   w0, #31, LBB0_2  ; 非负才跳
  stp   x29, x30, [sp, #-16]!
  mov   x29, sp
  bl    __Z9log_errori
  mov   w0, #-1
  ldp   x29, x30, [sp], #16
  ret
LBB0_2:
  add   w8, w0, w0, lsl #1
  add   w0, w8, #1
  ret
```

</div>

指令完全一样，只是两个代码块交换了位置：被认为常见的那一块紧跟在判断之后，不需要跳转就能执行到。没有属性时 Clang 自己就把调用 `log_error` 的那一侧当成冷路径；把 `[[likely]]` 改成 `[[unlikely]]`，输出和没有属性时逐字相同。

在 LLVM IR（`-S -emit-llvm`）里能看到属性变成了什么：

```text
br i1 %2, label %3, label %4, !prof !10
!10 = !{!"branch_weights", !"expected", i32 2000, i32 1}
```

这是一条分支权重，2000 比 1。GCC 和 Clang 早就有的 `__builtin_expect(x < 0, 1)` 生成的是同一条元数据。所以 `[[likely]]` 并不直接控制硬件，现代 CPU 的预测器也不读编译器的提示；它影响的是编译器的决策：代码块怎样排、是否内联、要不要做成 `csel`、循环怎么展开。

### 实测：猜对和猜错

把属性加到上一节的过滤循环上，三种写法各跑一遍：

| p（条件成立） | 无属性 | `[[likely]]` | `[[unlikely]]` |
|---|---|---|---|
| 1% | 0.36 ns/元素 | 0.39 | 0.21 |
| 50% | 2.9 | 2.9 | 3.0–3.9 |
| 99% | 0.31 | 0.31 | 0.70 |

（多次运行，个别次 `[[likely]]` 在 99% 时达到 0.6，`[[unlikely]]` 在 50% 时波动较大。）

`[[likely]]` 的输出和无属性时相同，所以测不出差别。`[[unlikely]]` 把八个 `str` 都移出了循环主体：主体变成八组比较加一个很少跳转的 `b.ge`，写入放在循环后面，执行完再跳回来。

```asm
LBB2_5:                     ; 循环主体，条件不成立时一路顺序执行
  ldur  w13, [x12, #-16]
  cmp   w13, #128
  b.ge  LBB2_14             ; 很少跳
LBB2_6:
  ldur  w13, [x12, #-12]
  ...
LBB2_14:                    ; 冷路径：写入，再跳回去
  str   w13, [x2, x0, lsl #2]
  add   x0, x0, #1
  b     LBB2_6
```

p = 1% 时，这种排布比默认快 1.7 倍；p = 99% 时，几乎每个元素都要跳出去再跳回来，慢了 2 倍多。两种情况下分支都被猜对了，差别来自跳转本身：前端每个周期能处理的跳转数有限，而默认排布在 p 小时每个元素都要执行一次 `b.lt` 跳过写入。这是根据汇编和计时得出的解释，不是对 Apple 微架构文档的引用。

!!! pitfall "提示只在你确实知道分布时才有用"
    [[dcl.attr.likelihood#2]] 的注 2 也提醒，滥用这两个属性可能让性能变差。错误的提示不会造成错误的结果，只会让常见路径变慢；本机上猜错的代价（2 倍）比猜对的收益（1.7 倍）还大。把它留给真正的冷路径：错误处理、断言失败、一次性的初始化。

## PGO：用测出来的概率代替猜测

**基于剖析的优化**（profile-guided optimization，PGO）先编译一个插桩版本，用有代表性的输入跑一遍，记下每个分支实际走了多少次，再把这些计数喂回编译器。它产生的正是 `[[likely]]` 想表达的那种分支权重，只不过来自测量。

```bash
clang++ -std=c++2c -O2 -fprofile-instr-generate pgo.cpp -o pgo_gen
LLVM_PROFILE_FILE=p1.profraw ./pgo_gen 1          # 用 p = 1% 的数据训练
llvm-profdata merge -o p1.profdata p1.profraw
clang++ -std=c++2c -O2 -fprofile-instr-use=p1.profdata pgo.cpp -o pgo_use1
```

`pgo.cpp` 就是上面的过滤函数，加一个从命令行读 p 的 `main`。训练数据分别用 p = 1% 和 p = 99%，再在两种数据上测：

| 构建 | 在 p = 1% 上运行 | 在 p = 99% 上运行 |
|---|---|---|
| 普通 `-O2` | 0.36 ns/元素 | 0.31 |
| 用 p = 1% 训练 | 0.21 | 0.62 |
| 用 p = 99% 训练 | 0.36 | 0.31 |

用 p = 1% 训练出的循环和手写 `[[unlikely]]` 的排布一样，收益也一样；用 p = 99% 训练的结果和默认相同。PGO 的好处是不用改源码，提示也不会随着代码演进而过时。代价同样清楚：训练数据和真实负载不一致时，它会像写错的 `[[unlikely]]` 一样让程序变慢。PGO 与 LTO 的完整流程见 [[perf/lto-pgo|LTO 与 PGO]]。

## 间接分支：虚函数调用

虚调用要先从对象里读出 vptr，再从 vtable 里读出函数地址，最后跳到寄存器里的地址（arm64 上是 `blr`）。具体布局见 [[toolchain/object-layout-and-vtables]]。这种跳转的目标也要预测：同一个调用点如果总是调用同一个最终覆盖函数，叫**单态**（monomorphic）调用点；目标在几个之间变化，叫**多态**（polymorphic）调用点。

```cpp title="virt.cpp" ok
#include "bench.h"
#include <new>
#include <random>

struct Shape {
  virtual ~Shape() = default;
  virtual unsigned long f(unsigned long x) const = 0;
};
struct A : Shape { unsigned long f(unsigned long x) const override { return x + 1; } };
struct B : Shape { unsigned long f(unsigned long x) const override { return x ^ 3; } };
struct C : Shape { unsigned long f(unsigned long x) const override { return x * 5; } };
struct D : Shape { unsigned long f(unsigned long x) const override { return x - 7; } };

[[gnu::noinline]] unsigned long run(Shape* const* v, long n) {
  unsigned long s = 0;
  for (long i = 0; i < n; ++i) s += v[i]->f(s);
  return s;
}

struct alignas(16) Slot { std::byte b[16]; };

int main() {
  const int n = 1 << 20;
  std::vector<Slot> pool(n);       // 对象连续摆放，各种顺序的访存模式相同
  std::vector<Shape*> v(n);
  std::mt19937 rng(3);
  auto measure = [&](const char* name, int kinds, bool sorted) {
    std::vector<int> types(n);
    for (int& t : types) t = rng() % kinds;
    if (sorted) std::sort(types.begin(), types.end());
    for (int i = 0; i < n; ++i) {
      void* p = &pool[i];
      switch (types[i]) {
      case 0: v[i] = new (p) A; break;
      case 1: v[i] = new (p) B; break;
      case 2: v[i] = new (p) C; break;
      default: v[i] = new (p) D; break;
      }
    }
    double ns = bench_ns([&] { auto s = run(v.data(), n); escape(s); }, 31);
    std::printf("%-18s %.3f ns/call\n", name, ns / n);
  };   // 析构函数没有副作用，这里不调用它们，直接复用存储
  measure("1 type", 1, false);
  measure("2 types, shuffled", 2, false);
  measure("4 types, sorted", 4, true);
  measure("4 types, shuffled", 4, false);
}
```

对象都放在一块连续的内存里，按遍历顺序构造，这样几种情况的访存模式完全相同，差别只来自调用目标的顺序。本机五次运行的结果：

| 调用点上的类型 | ns/调用 |
|---|---|
| 1 种 | 0.92–0.97 |
| 4 种，按类型排序 | 0.92–1.7（多数约 0.93） |
| 2 种，随机 | 4.7–4.9 |
| 4 种，随机 | 6.3–9.4 |

按类型排好序后，四种类型的调用和只有一种一样快：每一段里目标都不变，预测器很快就学会了。打乱之后，两种类型约有一半调用猜错目标，四种类型约有四分之三，每次调用分别多出约 4 ns 和 6 ns 以上。

所以虚调用慢，主要不是因为那两次加载，而是多态调用点上目标难以预测，以及间接调用妨碍了内联。按类型把对象分组存放（每个类型一个容器，或者先按类型排序）往往比去掉虚函数更划算。编译器什么时候能把虚调用变成直接调用（去虚化），见 [[perf/compiler-optimizations|编译器优化]]。

## `switch`：跳转表与比较链

`switch` 有两种常见的实现。case 值稠密时，编译器建一张**跳转表**（jump table），用条件值作下标取出目标地址，做一次间接跳转；case 值稀疏或者很少时，编译成一串比较和条件跳转，通常排成二分查找的形状。

```cpp title="dispatch.cpp" godbolt flags="-std=c++2c -O2" ok
void f0(), f1(), f2(), f3(), f4(), f5(),
     f6(), f7(), f8(), f9(), f10(), f11();

void dispatch(unsigned op) {
  switch (op) {
  case 0: f0(); break;
  case 1: f1(); break;
  case 2: f2(); break;
  case 3: f3(); break;
  case 4: f4(); break;
  case 5: f5(); break;
  case 6: f6(); break;
  case 7: f7(); break;
  case 8: f8(); break;
  case 9: f9(); break;
  case 10: f10(); break;
  case 11: f11(); break;
  }
}
```

```asm
__Z8dispatchj:
  cmp   w0, #11
  b.hi  LBB0_14             ; op > 11：一个 case 也不匹配，直接返回
  mov   w8, w0
  adrp  x9, LJTI0_0@PAGE
  add   x9, x9, LJTI0_0@PAGEOFF
  adr   x10, LBB0_2
  ldrb  w11, [x9, x8]       ; 表里存的是一字节的偏移
  add   x10, x10, x11, lsl #2
  br    x10                 ; 间接跳转
```

什么时候用跳转表由目标平台的代价模型决定，不是语言规则。本机观察到：同样形状的 `switch`（第 i 个 case 调用不同的函数 fi），Clang 23 在 arm64 上从 10 个 case 开始用跳转表，9 个及以下生成比较树；`--target=x86_64-linux-gnu` 时 4 个 case 就已经用跳转表。另外，如果每个 case 只是返回一个随 case 值线性变化的值，编译器会直接把 `switch` 换成算术，两种结构都不出现。

跳转表的 `br` 和虚调用一样是间接分支，代价取决于目标是否可预测。下面是一个 12 个 case 的小解释器循环，每个 case 只做一次整数运算：

| 指令序列 | ns/指令 |
|---|---|
| 一直是同一个 op | 0.61 |
| 0, 1, …, 11 循环 | 1.43 |
| 随机 | 7–17（波动很大） |

有规律的序列，哪怕目标每次都变，预测器也能借助历史学会（不同 op 的运算延迟也不同，所以前两行的差别不全是预测造成的）。随机序列每条指令都可能猜错，比可预测时慢一个数量级。

### 用 `std::unreachable` 去掉范围检查 {{c++23}}

上面汇编的前两行是范围检查：`op` 不在 0 到 11 之间时，标准要求什么也不执行（[[stmt.switch#5]]），所以查表之前必须先比较。如果确知 `op` 不会越界，可以这样告诉编译器：

```cpp
  case 11: f11(); break;
  default: std::unreachable();   // <utility>
  }
```

`std::unreachable()` 的前置条件是 false is true，永远不能满足，所以调用它就是未定义行为（[[utility.undefined#1]]）。编译器因此可以假定 `default` 永远走不到，`cmp` 和 `b.hi` 两条指令随之消失，直接从查表开始。x86-64 上同样少了 `cmpl $11` 和 `ja`。

把它加进上面的解释器循环，三种序列下都测不出差别：可预测时 0.613 对 0.613、1.430 对 1.431 ns/指令；随机时两者都在同样的大范围里波动。被删掉的比较和一个永远猜对的分支本来就几乎不花时间。

!!! pitfall "删掉的是检查，不是错误"
    如果 `op` 实际上会越界，加了 `std::unreachable()` 的版本会用越界的下标去读跳转表，再跳到一个任意地址。原来的代码只是什么也不做。只有在值域确实由别处保证（例如刚刚校验过，或者是一个完整覆盖了所有枚举值的 `switch`）时才用它；调试构建里可以先换成断言。更多由 UB 换来的优化见 [[topics/undefined-behavior]]。

## `&&` 与 `&`

`&&` 规定了短路求值：第一个操作数为假时，第二个不求值（[[expr.log.and#1]]）。如果第二个操作数会读内存，编译器通常必须保留一个分支，因为它不知道在第一个条件为假时读那块内存是否安全。`&` 没有这个限制，两边总是都求值。

<div class="compare" markdown="1">

```cpp
for (long i = 0; i < n; ++i)
  if (a[i] > 0 && b[i] > 0) ++c;
```

```cpp
for (long i = 0; i < n; ++i)
  if ((a[i] > 0) & (b[i] > 0)) ++c;
```

</div>

左边的循环里，每个元素一个 `b.lt`，条件成立后才去读 `b[i]`。右边被向量化了，Clang 还把两个比较合成了一个：`a > 0 && b > 0` 等价于 `min(a, b) > 0`，于是生成 `smin.4s` 加 `cmgt.4s`。每个条件以概率 p 成立时：

| p | `&&` | `&` |
|---|---|---|
| 50% | 2.94 ns/元素 | 0.156 ns/元素 |
| 99% | 0.40–0.54 | 0.157 |

p = 50% 时差别主要来自预测失败；p = 99% 时分支几乎总被猜对，`&` 仍然快 2.5 倍以上，因为它让整个循环可以向量化。

这不是说应该把 `&&` 都换成 `&`。第二个操作数保护着一次可能出错的访问时（`p && p->x`、`i < n && v[i]`），短路是正确性的一部分；第二个操作数很贵而第一个经常为假时，短路也更快。值得换的情形是：两边都便宜、都安全、结果难以预测，或者希望循环被向量化。

## 小结

| 手段 | 改变了什么 | 本机观察 |
|---|---|---|
| 编译器自动 if 转换 | 简单的条件赋值变成 `csel`/`cmov` 或向量掩码 | 排序数组求和在 `-O1` 以上不再受排序影响 |
| 手写无分支（条件选择、掩码） | 控制依赖变成数据依赖，两边都算 | 难预测时稳定在 0.31 ns/元素；一边很贵且少走时慢 5 倍 |
| 查表 | 一串比较变成一次加载 | 字符分类快 15 倍，表要能放进 L1 |
| `[[likely]]`/`[[unlikely]]`、`__builtin_expect` | 分支权重，进而影响代码块排布 | 和默认一致时没有变化；猜对快 1.7 倍，猜错慢 2 倍 |
| PGO | 用实测的分支计数代替猜测 | 与手写提示效果相同，训练数据不对时同样变慢 |
| 按类型分组的虚调用 | 让间接跳转的目标可预测 | 随机 4 种类型约 6–9 ns/调用，排序后约 0.93 |
| `std::unreachable()` 作 `default` | 删掉跳转表前的范围检查 | 测不出差别；值越界时是 UB |
| `&` 代替 `&&` | 两边都求值，允许向量化 | 难预测时快 19 倍，可预测时仍快 2.5 倍 |

## 思考题

!!! question "1"
    把本页开头的 `sum_big` 用 `-O2` 编译，排序与否没有差别。在不改变函数语义、不加编译选项的前提下，怎样改一行代码，就能让排序重新变得重要？

<details markdown="1">
<summary>答案</summary>

让条件路径上出现编译器不能无条件执行的操作，例如一次对外部函数的调用、一次有条件的写内存，或者一次可能出错的读。本页的过滤函数就是第二种：`out[k++] = x` 只能在条件成立时执行，因为引入抽象机不会执行的写操作可能制造数据竞争（[[intro.races#19]]），也可能越界。函数里有了这样的操作，分支就留下来了，排序与否的差别随之回来，本机上是 0.31 对 3.03 ns/元素。
</details>

!!! question "2"
    `if (x < 0) [[unlikely]] return handle(x);` 与 `if (__builtin_expect(x < 0, 0)) return handle(x);` 有什么区别？哪一个是标准 C++？编译器可以完全忽略它们吗？

<details markdown="1">
<summary>答案</summary>

前者是 C++20 的标准属性（[[dcl.attr.likelihood]]），后者是 GCC 和 Clang 的扩展。在 Clang 23 上两者生成同一条 `branch_weights` 元数据（1 比 2000），汇编相同。描述优化意图的那段话是注，不具规范效力，所以实现完全忽略它们也符合标准；按注里的期望，这种实现应该让 `__has_cpp_attribute(likely)` 的值为 0。
</details>

!!! question "3"
    `enum class Op : unsigned char { /* 12 个枚举值 */ };`，一个 `switch` 列全了这 12 个枚举值，没有 `default`。把 `default: std::unreachable();` 加进去，可能带来什么好处？什么情况下这会让程序出错？

<details markdown="1">
<summary>答案</summary>

`Op` 有固定的底层类型，它的值可以是 `unsigned char` 的任何值（[[dcl.enum#8]]），`static_cast<Op>(200)` 是合法的。所以即使列全了枚举值，编译器仍要处理不匹配的情况（[[stmt.switch#5]]：不执行任何语句），跳转表前要做范围检查。加上 `std::unreachable()` 后，编译器可以假定条件值总在 case 之中，删掉这次检查；在比较树形式下也可能省掉最后一次比较。如果有代码通过 `static_cast` 或反序列化构造了枚举值以外的值并传进来，原本无害的空操作就变成了未定义行为（[[utility.undefined#1]]），实际表现可能是用越界的下标读跳转表，再跳到任意地址。
</details>
