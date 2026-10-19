---
title: 编译器能替你做什么，做不到什么
summary: 优化器依据 as-if 规则和没有 UB 的前提改写程序：内联、常量传播、去虚化、复制省略、死存储消除、循环不变量外提各自做什么，别名、看不见的函数、逃逸的地址、volatile 怎样挡住它们，以及怎样用 -Rpass 让 Clang 说出它的决定。
group: 编译器
status: draft
order: 30
since: c++98
related: intro.abstract, basic.lval, dcl.inline, class.copy.elision, dcl.type.cv, expr.new, allocator.members, intro.compliance.general, topics/undefined-behavior, topics/type-punning, topics/special-members-and-elision, topics/arithmetic, toolchain/exception-implementation, perf/reading-assembly, perf/lto-pgo, perf/vectorization, perf/measuring, perf/copies-and-moves
tags: 性能, 优化, as-if, 内联, 别名, 去虚化, Clang
updated: 2026-10-19
---

!!! tldr
    - 标准只要求实现模仿抽象机的可观察行为（volatile 访问、写进文件的数据、交互设备的输入输出），其余一切都可以改写；程序没有 UB 是优化器推理的前提。
    - 内联是其他优化的入口：调用被内联之后，常量才能传进去，循环才能向量化。函数体在另一个翻译单元时，没有 LTO 就无法内联；`inline` 关键字主要管 ODR，在 Clang 上只把内联阈值从 225 提到 325。
    - `final`、已知的动态类型能让虚调用变成直接调用；收益来自随后的内联和向量化，而不是省掉的那次间接跳转。
    - 优化器最常见的障碍是别名：通过 `char`、`unsigned char`、`std::byte` 写内存，编译器就得假设任何对象都可能被改了。`std::vector<unsigned char>` 上按下标写的循环，本机比范围 for 慢 30 倍以上。
    - 用 `-Rpass=…`、`-Rpass-missed=…`、`-Rpass-analysis=…` 让 Clang 报告内联、外提、向量化的决定和失败原因，再到汇编里核对。

## 一个循环变成了一个公式

```cpp godbolt title="asif.cpp" flags="-std=c++2c -O2" ok
int tri(int n) {
  int s = 0;
  for (int i = 0; i < n; ++i) s += i;
  return s;
}
int ten() {
  int a[] = {1, 2, 3, 4};
  int s = 0;
  for (int v : a) s += v;
  return s;
}
```

本机 `clang++ -std=c++2c -O2`（Homebrew Clang 23.1.3，arm64）的输出：

```asm title="AArch64"
__Z3trii:                    ; 没有循环：(n-1) + (n-1)(n-2)/2
  sub   w8, w0, #1
  sub   w9, w0, #2
  umull x9, w8, w9
  add   x8, x8, x9, lsr #1
  cmp   w0, #1
  csel  w0, wzr, w8, lt      ; n < 1 时为 0
  ret
__Z3tenv:
  mov   w0, #10
  ret
```

`tri` 的循环被一个求和公式取代，`ten` 的数组和循环都消失了，只剩常数 10。程序里写的是循环，机器上跑的不是，这是允许的。

¶1 依据是 [[intro.abstract#1]]：

!!! std
    conforming implementations are required to emulate (only) the observable behavior of the abstract machine

标准用一台**抽象机**（[[g:abstract-machine|abstract machine]]）描述程序的语义，实现不必照搬它的结构，只需要产生相同的**可观察行为**（[[g:observable-behavior|observable behavior]]）。[[intro.abstract#8]] 列出了可观察行为的全部内容：通过 volatile glvalue 的访问、交给宿主环境写入文件的数据、交互设备的输入输出。循环跑了几次、变量放在寄存器还是内存、函数有没有被调用，都不在其中。这就是 **as-if 规则**（[[g:as-if-rule|as-if rule]]），名字来自那里的脚注：只要结果看起来如同遵守了规则，实现就可以不遵守。

as-if 规则管的是有定义的执行。`tri` 的公式成立，前提是 `s += i` 和 `++i` 不溢出；有符号溢出是 UB，编译器不必考虑它。[[intro.abstract#6]] 规定，执行中一旦出现未定义的操作，实现就不再受约束。所以优化器总是在程序没有 UB 的前提下推理，[[topics/undefined-behavior]] 收集了这种推理删掉判空、改写循环的例子。

同样的道理也适用于堆分配：

```cpp godbolt title="alloc.cpp" flags="-std=c++2c -O2" ok
#include <vector>
int vsum() {
  std::vector<int> v{1, 2, 3};
  return v[0] + v[1] + v[2];
}
```

本机 Clang 23 加 libc++ 把 `vsum` 编译成 `mov w0, #6`，`operator new` 和 `operator delete` 都没有调用。[[expr.new#14]] 允许实现省略对可替换全局分配函数的调用，[[allocator.members#5]] 也说明 `std::allocator::allocate` 何时、调用几次 `::operator new` 是未指定的。

## 优化级别

同一个函数在不同 `-O` 级别下差别很大：

```cpp godbolt title="levels.cpp" flags="-std=c++2c -O2" ok
int sum(const int* a, int n) {
  int s = 0;
  for (int i = 0; i < n; ++i) s += a[i];
  return s;
}
```

<div class="compare" markdown="1">

```asm title="-O0 的循环体"
LBB0_2:
  ldr  x8, [sp, #24]    ; 从栈上读 a
  ldrsw x9, [sp, #12]   ; 读 i
  ldr  w9, [x8, x9, lsl #2]
  ldr  w8, [sp, #16]    ; 读 s
  add  w8, w8, w9
  str  w8, [sp, #16]    ; 写回 s
  b    LBB0_3
LBB0_3:
  ldr  w8, [sp, #12]    ; 读 i
  add  w8, w8, #1
  str  w8, [sp, #12]    ; 写回 i
  b    LBB0_1
```

```asm title="-O2 的主循环"
LBB0_7:                 ; 每次 16 个 int
  ldp   q4, q5, [x8, #-32]
  ldp   q6, q7, [x8], #64
  add.4s v0, v4, v0
  add.4s v1, v5, v1
  add.4s v2, v6, v2
  add.4s v3, v7, v3
  subs  x12, x12, #16
  b.ne  LBB0_7
```

</div>

`-O0` 让每个变量都住在栈上，每次使用都从内存读、改完写回，便于调试器随时查看。`-O1` 把变量放进寄存器，循环体只剩四条指令，一次处理一个元素。`-O2` 把循环**向量化**（一条指令处理多个元素），再展开四份，每次迭代处理 16 个 `int`，前后还有处理零头的循环，整个函数 62 行。

下表的时间是对 4096 个 `int` 调用一次 `sum` 的耗时，`levels.cpp` 单独用各级别编译，测量框架统一用 `-O2` 编译，再链接在一起。本机 Apple M2 Pro 测量，表中是多次运行（每次运行取中位数）的范围：

| 级别 | 汇编行数 | 循环形态 | 每次调用 |
|---|---|---|---|
| `-O0` | 25 | 变量都在栈上 | 3.8–9.0 µs |
| `-O1` | 13 | 标量，一次 1 个 | 1.26–1.9 µs |
| `-O2` | 62 | 向量化 ×4 展开，一次 16 个 | 148–151 ns |
| `-O3` | 62 | 与 `-O2` 完全相同 | 148–151 ns |
| `-Os` | 12 | 标量，一次 1 个 | 1.28–1.8 µs |
| `-Oz` | 9 | 标量 | 未测 |

`-O1` 和 `-Os` 不向量化，Clang 说明了原因（下一节介绍这些报告）：

```text
-O1: remark: loop not vectorized: only vectorizing loops that explicitly request it [-Rpass-missed=loop-vectorize]
-Os: remark: the cost-model indicates that vectorization is not beneficial [-Rpass-missed=loop-vectorize]
```

`-O3` 在这个函数上和 `-O2` 逐字节相同。用 `opt -passes='default<O3>' -print-pipeline-passes` 对比本机 LLVM 23 的两条流水线，`-O3` 只多了 `callsite-splitting`、`argpromotion`、`chr` 几个过程，循环展开更激进，非平凡的循环拆分（unswitch）只在 `-O3` 打开；内联阈值也从 225 提到 250（见下文）。`-O3` 是否更快要测，不能默认。

范围之所以这么宽，是因为测量时机器负载很高。向量化版本每次都是 148–151 ns，标量版本在不同运行之间相差可达一倍；即便取最好的一次，`-O2` 也比 `-O1` 快 8 倍以上。

这些数字只说明本机、这个编译器、这个函数上的情况。换一个编译器，级别之间的分工就不同；换一台机器，向量化带来的倍数也不同。

<details class="fine" markdown="1"><summary>测量框架</summary>

本页的计时都用下面这个头文件，测量方法的完整讨论见 [[perf/measuring|测量]]。

```cpp title="bench.h" ok
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <vector>

// 让编译器认为 v 被读取了，不能删掉计算 v 的代码
template<class T> void escape(T const& v) {
  asm volatile("" : : "r,m"(v) : "memory");
}
// 让编译器认为任何内存都可能被读写了
inline void clobber() { asm volatile("" : : : "memory"); }

// 运行 f 共 reps 轮，每轮 iters 次，返回单次调用纳秒数的中位数
template<class F> double bench(F f, int iters, int reps = 21) {
  using clk = std::chrono::steady_clock;
  for (int i = 0; i < iters; ++i) f();                 // 预热
  std::vector<double> ns;
  for (int r = 0; r < reps; ++r) {
    auto t0 = clk::now();
    for (int i = 0; i < iters; ++i) f();
    auto t1 = clk::now();
    ns.push_back(std::chrono::duration<double, std::nano>(t1 - t0).count() / iters);
  }
  std::nth_element(ns.begin(), ns.begin() + reps / 2, ns.end());
  return ns[reps / 2];
}
```

as-if 规则对测量代码同样适用：如果 `sum` 的结果没人用，编译器可以把调用整个删掉。`escape` 是一条空的内联汇编，它声明自己读取 `v`，还可能读写任意内存（`"memory"`），而编译器不分析汇编的内容，只能保留 `v` 的计算。`clobber` 让编译器认为内存被改过，不能把上一轮的结果沿用到下一轮。内联汇编是有条件支持的、含义由实现定义的构造（[[dcl.asm]]），这种写法只适用于 GCC 和 Clang。

被测函数放在单独的翻译单元，防止它被内联进计时循环后又被提出循环。本机测量时机器上还有其他编译任务在运行，同一个程序多次运行的中位数相差可达一倍，所以正文只给范围，只对相差数倍的结果下结论；汇编和优化报告不受负载影响，是主要证据。
</details>

## 让 Clang 说出它的决定

Clang 的**优化报告**（optimization remark）说明每个优化过程做了什么、没做什么。三类开关都接受一个过程名（正则表达式）：

| 开关 | 报告 | 本页用到的过程名 |
|---|---|---|
| `-Rpass=…` | 做成了什么 | `inline`、`licm`、`loop-vectorize` |
| `-Rpass-missed=…` | 想做但没做成 | 同上 |
| `-Rpass-analysis=…` | 没做成的具体原因 | `loop-vectorize` |

报告和警告一样输出到标准错误，带源码位置。`-fsave-optimization-record` 把全部报告存成 YAML 文件，适合大项目。报告里的函数名是修饰过的名字，`_Z3mixj` 就是 `mix(unsigned int)`，可以用 `llvm-cxxfilt` 还原，见 [[perf/reading-assembly|读懂汇编]]。

报告说做了，汇编里不一定看得出好处；报告说没做，也可能是正确的选择。所以报告是找线索的工具，结论仍要回到汇编和测量。

## 内联

### 看不见函数体就无法内联

<div class="compare" markdown="1">

```cpp title="xtu.cpp"
int add3(int x);   // 定义在 add3.cpp
void bump(int* a, int n) {
  for (int i = 0; i < n; ++i)
    a[i] = add3(a[i]);
}
```

```cpp title="stu.cpp"
int add3(int x) { return x + 3; }
void bump(int* a, int n) {
  for (int i = 0; i < n; ++i)
    a[i] = add3(a[i]);
}
```

</div>

左边的 `add3` 在另一个翻译单元里，编译 `xtu.cpp` 时编译器只看到声明，循环里每个元素都要调用一次：

```asm title="xtu.cpp，-O2"
LBB0_2:
  ldr   w0, [x19]
  bl    __Z4add3i          ; 每个元素一次调用
  str   w0, [x19], #4
  subs  x20, x20, #1
  b.ne  LBB0_2
```

右边的 `add3` 被**内联**（把函数体复制到调用点，取代调用），循环里只剩加法，于是又被向量化，主循环每次给 16 个 `int` 加 3（`movi.4s v0, #3` 加四组 `add.4s`）。

对 4096 个元素调用一次 `bump`，本机测得：跨翻译单元 3.8–8.6 µs，同一翻译单元 0.20–0.30 µs，跨翻译单元但加 `-flto` 编译和链接 0.20–0.28 µs，相差 20 倍以上。省掉的不只是调用指令，更重要的是内联让向量化成为可能。

跨翻译单元的内联要靠**链接时优化**（LTO）：编译器把中间表示存进目标文件，链接时把整个程序当作一个单元再优化一遍。代价和用法见 [[perf/lto-pgo|LTO 与 PGO]]。头文件里的函数之所以能内联，是因为每个翻译单元都有它的定义。

### 成本与阈值

函数体可见时，内联与否取决于启发式：编译器估计内联后的代码**成本**，与一个**阈值**比较。下面的 `mix` 由 28 组相同形式的语句组成：

```cpp title="mix.cpp"
unsigned mix(unsigned x) {
  x ^= x >> 3; x *= 3;
  x ^= x >> 4; x *= 5;
  // …同样形式的语句共 28 组
  return x;
}
unsigned caller(unsigned a) { return mix(a) + mix(a + 1); }
```

用 `clang++ -std=c++2c -O2 -S -Rpass=inline -Rpass-missed=inline mix.cpp` 编译，本机 Clang 23 报告（两个调用点的报告相同，只列一条）：

```text
mix.cpp:32:38: remark: '_Z3mixj' not inlined into '_Z6callerj' because too costly to inline (cost=385, threshold=337) [-Rpass-missed=inline]
```

在 `mix` 前面加上 `inline`，同样的命令得到：

```text
mix.cpp:32:38: remark: '_Z3mixj' inlined into '_Z6callerj' with (cost=385, threshold=487) at callsite caller:0:38; [-Rpass=inline]
```

阈值随级别和关键字变化。把 `mix` 分别用各级别编译，报告中的阈值是：

| | `-O1`、`-O2` | `-O3` | `-Os` | `-Oz` |
|---|---|---|---|---|
| 不写 `inline` | 337 | 375 | 75 | 5 |
| 写 `inline` | 487 | 487 | 487 | 未测 |

LLVM 的基础阈值是 225（`-O3` 为 250，`-Os` 为 50），带内联提示的函数为 325；`mix` 只有一个基本块，又得到 50% 的奖励，所以报告中是 337、375、75 和 487。另外两个观察：

- 只被调用一次的 `static` 函数几乎总会被内联。把 `mix` 改成 `static` 并只调用一次，报告变成 `cost=-14615`：删掉函数本身省下的体积被算作一大笔奖励。
- Clang 只对显式写了 `inline` 的函数给提示。在类定义里定义的成员函数隐式是内联函数，本机测试中它的阈值仍是 337，没有提高。

### `inline` 关键字不等于内联

¶3 [[dcl.inline#3]] 说，`inline` 说明符向实现表示，优先在调用点做内联替换，但实现不必这样做。这个关键字真正有约束力的作用在 ¶2 的注里：**内联函数**（[[g:inline-function|inline function]]）可以在多个翻译单元中定义，只要各处定义相同（[[basic.def.odr]]）。所以它的用途是把函数定义放进头文件，而不是命令编译器内联。

两者的关系是间接的：函数定义在头文件里，各个翻译单元才看得见函数体，才有内联的可能。至于真的内联与否，由成本模型决定，`inline` 在 Clang 上只是抬高了阈值。

需要强制时，GCC 和 Clang 提供两个扩展属性：

```cpp godbolt title="attrs.cpp" flags="-std=c++2c -O2" ok
[[gnu::always_inline]] inline int sq(int x) { return x * x; }
[[gnu::noinline]] int cube(int x) { return x * x * x; }
int f(int x) { return sq(x) + cube(x); }
```

```text
attrs.cpp:3:23: remark: '_Z2sqi' inlined into '_Z1fi' with (cost=always): always inline attribute at callsite f:0:23; [-Rpass=inline]
attrs.cpp:3:31: remark: '_Z4cubei' not inlined into '_Z1fi' because it should never be inlined (cost=never): noinline function attribute [-Rpass-missed=inline]
```

`always_inline` 连 `-O0` 也会内联（本机 `-O0` 下第一条报告同样出现），`noinline` 在任何级别都不内联。`noinline` 常用于把冷路径、错误处理移出热函数，或者在基准测试里隔离被测函数；`always_inline` 用多了会让代码膨胀，指令缓存反而吃紧，应当以测量为准。

## 常量传播与折叠

```cpp godbolt title="cprop.cpp" flags="-std=c++2c -O2" ok
int divide(int x, int d) { return x / d; }
int quarter(int x) { return divide(x, 4); }
int by_runtime(int x, int d) { return divide(x, d); }
```

```asm title="AArch64"
__Z7quarteri:              ; 除以 4 变成移位
  add   w8, w0, #3
  cmp   w0, #0
  csel  w8, w8, w0, mi     ; 负数先加 3，保证向零截断
  asr   w0, w8, #2
  ret
__Z10by_runtimeii:
  sdiv  w0, w0, w1         ; 除数未知，只能用除法指令
  ret
```

**常量传播**把已知的常量代入用到它的地方，**常量折叠**在编译期算出常量表达式的值。`quarter` 内联 `divide` 后，除数变成常量 4，除法就换成了移位；有符号除法向零截断（[[expr.mul]]），所以负数要先加 3 再右移。`by_runtime` 的除数是运行期的值，只能用 `sdiv`。

开头的 `ten` 和 `vsum` 也是折叠的结果。这些都是优化器的自由，不是保证：同样的代码在 `-O0` 下照常执行循环。需要保证在编译期算出结果时，用 `constexpr` 变量或 `consteval` 函数，见 [[perf/compile-time-work|编译期计算]]。

## 去虚化

虚调用要先读对象的 vptr，再从 vtable 里读函数地址，最后间接调用，汇编的样子见 [[perf/reading-assembly|读懂汇编]]。如果编译器能确定对象的**动态类型**（[[g:dynamic-type|dynamic type]]），就能把虚调用换成直接调用，进而内联，这叫**去虚化**（devirtualization）。常见的三种情况：

- 对象就在眼前：`Square q(x); const Shape& s = q; s.area();`，本机编译成一条 `fmul`。
- 静态类型是 `final` 类，或者被调用的虚函数声明为 `final`：没有派生类能覆盖它。
- 整个程序可见：LTO 加 `-fwhole-program-vtables` 时，Clang 能确认某个虚函数只有一个覆盖者，见 [[perf/lto-pgo|LTO 与 PGO]]。

去虚化本身省下的只是两次加载和一次间接跳转。在循环里比较 `final` 与非 `final` 的类：

```cpp title="dv.h" ok
struct Shape {
  virtual ~Shape() = default;
  virtual int area() const = 0;
};
struct Sq : Shape {            // 不是 final
  int side = 3;
  int area() const override { return side * side; }
};
struct SqF final : Shape {     // final
  int side = 3;
  int area() const override { return side * side; }
};
```

```cpp title="dv.cpp" ok
#include "dv.h"
long total(const Sq* p, int n) {
  long s = 0;
  for (int i = 0; i < n; ++i) s += p[i].area();
  return s;
}
long total(const SqF* p, int n) {
  long s = 0;
  for (int i = 0; i < n; ++i) s += p[i].area();
  return s;
}
```

`Sq` 版本的循环每次迭代读 vptr、读槽、`blr`；`SqF` 版本内联了 `area`，再被向量化，用 `ld4.4s` 一次读入 16 个对象。各 4096 个对象，在同一个进程里先后测量，`Sq` 版 3.8–9.0 µs，`SqF` 版 0.87–2.2 µs，每次运行中 `SqF` 都快 3 倍以上。

把 `int` 换成 `double`，两个版本就分不出快慢了：本机多次运行，有时 `Sq` 快，有时 `SqF` 快，差异在噪声以内（都在 3.8–8.5 µs 之间）。`SqF` 版的 `area` 照样被内联，读取和乘法也被向量化了，但加法仍是一个接一个的标量 `fadd d0, d0, …`。浮点加法不满足结合律，编译器不能把 `s += …` 拆成几路并行累加（[[expr.pre]]），两个版本都受制于逐个相加的依赖链，间接调用的代价被它掩盖了。所以去虚化值多少，取决于它之后还能做成什么优化。

## 复制省略

```cpp godbolt title="nrvo.cpp" flags="-std=c++2c -O2" ok
struct Big {
  Big();
  Big(Big&&);
  ~Big();
  char buf[256];
};
void fill(Big&);

Big one() {
  Big a;
  fill(a);
  return a;          // a 直接建在返回值的位置
}
Big two(bool c) {
  Big a, b;
  fill(a); fill(b);
  if (c) return a;
  return b;
}
```

<div class="compare" markdown="1">

```asm title="one，-O2"
  mov  x19, x8   ; x8：返回值地址
  mov  x0, x8
  bl   __ZN3BigC1Ev   ; 在那里构造
  mov  x0, x19
  bl   __Z4fillR3Big
  ret               ; 没有移动
```

```asm title="two，-O2（节选）"
  add  x0, sp, #264
  bl   __ZN3BigC1Ev   ; a 在栈上
  add  x0, sp, #8
  bl   __ZN3BigC1Ev   ; b 在栈上
  ...
  csel x1, x8, x21, ne
  mov  x0, x19
  bl   __ZN3BigC1EOS_ ; 移动构造
  add  x0, sp, #8
  bl   __ZN3BigD1Ev
  add  x0, sp, #264
  bl   __ZN3BigD1Ev
```

</div>

返回 prvalue（`return Big();`）时没有任何复制，这是 C++17 起的语言规则，不是优化。返回具名局部变量时，[[class.copy.elision#1]] ¶1.1 允许把这个变量直接构造在返回值的位置，叫做 NRVO（具名返回值优化）。它是允许而非要求：`one` 只有一个候选，Clang 做到了；`two` 有两个候选，返回哪个要到运行期才知道，Clang 23 两个都放在自己的栈帧上，返回时调用一次移动构造函数，再析构两个对象。

改成只有一个返回变量（先决定往哪个对象里写，最后 `return` 它），或者让每个分支返回 prvalue，就能避免这次移动。哪些写法会多一次移动或复制，见 [[topics/special-members-and-elision]] 和 [[perf/copies-and-moves|复制与移动]]。

## 死存储消除

```cpp godbolt title="dse.cpp" flags="-std=c++2c -O2" ok
#include <cstring>
void opaque();
void twice(int* p) {
  *p = 1;            // 被下一次存储覆盖：删除
  *p = 2;
}
void with_call(int* p) {
  *p = 1;            // opaque() 可能读 *p：保留
  opaque();
  *p = 2;
}
void read_password(char*);
void check(const char*);
void login() {
  char pw[64];
  read_password(pw);
  check(pw);
  std::memset(pw, 0, sizeof pw);   // 之后没人读 pw：删除
}
```

一次存储如果在被读取之前就被覆盖，或者存入的对象此后再也不会被读取，它就是**死存储**，删掉它不改变可观察行为。本机 `-O2` 下 `twice` 只剩一条 `str` 存 2；`with_call` 两次都存，因为编译器看不到 `opaque` 的函数体，它可能读 `*p`。

`login` 的结果最出人意料：`memset` 被整个删掉了，栈上的密码在函数返回后原样留在内存里。`pw` 的生存期在 `memset` 之后就结束了，清零对可观察行为没有任何影响。要让清零留下来，就得让编译器认为有人会读：

```cpp
std::memset(pw, 0, sizeof pw);
asm volatile("" : : "r"(pw) : "memory");   // 假装读了 pw 指向的内存
```

加上这一行，本机输出里出现了 `movi.2d v0, #0` 和两条 `stp q0, q0` 清零 64 字节。其他做法有平台函数 `memset_s`（C11 附录 K，可选）、`explicit_bzero`（BSD、glibc），以及 C23 的 `memset_explicit`；它们的共同点是承诺不被当作死存储删除。

## 循环不变量外提

```cpp godbolt title="licm.cpp" flags="-std=c++2c -O2" ok
#include <cstddef>
#include <cstring>
std::size_t count_a(const char* s) {
  std::size_t c = 0;
  for (std::size_t i = 0; i < std::strlen(s); ++i)
    if (s[i] == 'a') ++c;
  return c;
}
void upper(char* s) {
  for (std::size_t i = 0; i < std::strlen(s); ++i)
    if (s[i] >= 'a' && s[i] <= 'z') s[i] -= 32;
}
```

**循环不变量外提**（loop-invariant code motion，LICM）把每次迭代结果都相同的计算移到循环之前。`count_a` 的循环只读 `s`，`strlen(s)` 每次都一样，Clang 把它提出了循环：

```text
licm.cpp:5:31: remark: hoisting call [-Rpass=licm]
```

`upper` 里没有这条报告，汇编中 `bl _strlen` 留在循环里。循环会写 `s[i]`，而写入可能改变字符串的长度（比如写进一个 `'\0'`），编译器不会去证明 `s[i] - 32` 永远不是 0，于是每次迭代都重新计算长度，整个函数变成 O(n²)。

手动外提就能修复：

```cpp
void upper_fixed(char* s) {
  const std::size_t n = std::strlen(s);
  for (std::size_t i = 0; i < n; ++i)
    if (s[i] >= 'a' && s[i] <= 'z') s[i] -= 32;
}
```

两者的语义并不完全相同：如果循环真的写入了 `'\0'`，`upper` 会提前停下，`upper_fixed` 不会。正因为这样，编译器不能替你做这个改写。本机对 1024 个字符，`upper` 每次 23–80 µs，`upper_fixed` 0.34–0.51 µs，相差两个数量级，而且字符串越长差得越多。

## 什么挡住了优化器

上面几种优化都要先回答同一个问题：这次写内存会不会改变那个值？编译器回答不了时，只能保守处理。

### 别名：`char` 能改写一切

```cpp godbolt title="alias.cpp" flags="-std=c++2c -O2" ok
#include <cstddef>
#include <vector>
void idx(std::vector<unsigned char>& v, unsigned char k) {
  for (std::size_t i = 0; i < v.size(); ++i) v[i] += k;
}
void rng(std::vector<unsigned char>& v, unsigned char k) {
  for (auto& x : v) x += k;
}
```

```asm title="idx，-O2"
LBB0_2:
  ldrb  w10, [x8, x9]
  add   w10, w10, w1
  strb  w10, [x8, x9]      ; 写一个字节
  add   x9, x9, #1
  ldp   x8, x10, [x0]      ; 重新读 v 的 begin 和 end
  sub   x10, x10, x8
  cmp   x9, x10
  b.lo  LBB0_2
```

`idx` 每写一个字节，就从 `v` 对象里重新读一次 `begin` 和 `end` 指针（libc++ 的 `vector` 存三个指针），而且不向量化。`rng` 被向量化，每次处理 64 字节：

```text
alias.cpp:4:3: remark: loop not vectorized [-Rpass-missed=loop-vectorize]
alias.cpp:7:3: remark: vectorized loop (vectorization width: 16, interleaved count: 4) [-Rpass=loop-vectorize]
```

原因在 [[basic.lval#11]]。一个对象只能通过与它的类型相似的 glvalue 访问，例外是 `char`、`unsigned char` 和 `std::byte`，它们可以访问任何对象（详见 [[topics/type-punning]]）。所以编译器做**基于类型的别名分析**时，一次 `unsigned char` 写入可能改写任何对象，包括 `v` 自己的 `end` 指针。`rng` 在循环开始前把 `begin()` 和 `end()` 复制进了局部的迭代器，局部变量的地址没有泄露出去，写字节改不了它们。

把 `unsigned char` 换成 `int`，`int` 写入不能改写指针对象，`idx` 也能向量化。各 4096 个元素，本机测得：

| 函数 | 默认 | `-fno-strict-aliasing` |
|---|---|---|
| `idx`，`vector<unsigned char>` | 1.7–5.9 µs | 2.0–5.8 µs |
| `rng`，`vector<unsigned char>` | 50–120 ns | 50–51 ns |
| `idx`，`vector<int>` | 0.20–0.37 µs | 2.1–6.9 µs |

用 `-Rpass-missed=licm` 能直接看到原因，报告指向 libc++ 里 `size()` 读两个指针的那一行：

```text
.../include/c++/v1/__vector/layout.h:425:33: remark: failed to move load with loop-invariant address because the loop may invalidate its value [-Rpass-missed=licm]
.../include/c++/v1/__vector/layout.h:425:42: remark: failed to move load with loop-invariant address because the loop may invalidate its value [-Rpass-missed=licm]
```

这与目标架构无关。手写一个 `struct Bytes { unsigned char* data; std::size_t size; };`，循环条件写成 `i < b.size`，用 `--target=x86_64-linux-gnu` 编译，循环里每次迭代同样有 `movq (%rdi), %rcx` 和 `cmpq 8(%rdi), %rax` 两次重新加载。

修复的办法都是把会被重复读取的值放进局部变量：用范围 for 或迭代器；或者先写 `auto* p = v.data(); auto n = v.size();`。

本机还有两个与标准条文不完全对应的观察：

- `std::vector<signed char>` 的同样循环也不向量化。标准的豁免名单里没有 `signed char`，但 Clang 把它和 `char` 一样当作可以访问任何对象的类型，这是更保守的实现选择。`int8_t` 在这里就是 `signed char`。
- `std::vector<char8_t>` 的循环被向量化了。`char8_t` 是独立的类型，不在豁免名单里，Clang 也就不必为它保守。

### 同类型的指针：`__restrict`

```cpp godbolt title="restrict.cpp" flags="-std=c++2c -O2" ok
void scale(int* out, const int* in, const int* k, int n) {
  for (int i = 0; i < n; ++i) out[i] = in[i] * *k;
}
void scale_r(int* __restrict out, const int* in, const int* k, int n) {
  for (int i = 0; i < n; ++i) out[i] = in[i] * *k;
}
```

`out` 可能指向 `*k`，所以写 `out[i]` 之后 `*k` 可能变了。Clang 的做法是生成两个版本：循环前用几条 `cmp`/`ccmp` 检查 `out` 的范围是否与 `in` 和 `k` 重叠，不重叠就走向量化的版本，`*k` 只读一次；重叠就走标量版本，每次迭代都执行 `ldr w12, [x2]` 重新读 `*k`。`scale_r` 的 `__restrict` 承诺 `out` 指向的内存只通过 `out` 访问，检查和标量版本都没有了。

`__restrict` 来自 C 的 `restrict`，C++ 标准里没有它，GCC、Clang、MSVC 都作为扩展支持。承诺不成立时，编译器按自己的定义视为未定义行为。检查只在每次调用时做一次，长循环里它的成本可以忽略；更有效的手段往往是上一节的办法，先把 `*k` 读进局部变量。运行期别名检查与向量化的关系见 [[perf/vectorization|向量化]]。

### 看不见的函数和逃逸的地址

```cpp godbolt title="escape.cpp" flags="-std=c++2c -O2" ok
void tick();                      // 定义不可见
void watch(const int*);           // 定义不可见

int count_private(int n) {
  int c = 0;
  for (int i = 0; i < n; ++i) { ++c; tick(); }
  return c;
}
int count_escaped(int n) {
  int c = 0;
  watch(&c);                      // c 的地址交出去了
  for (int i = 0; i < n; ++i) { ++c; tick(); }
  return c;
}
```

<div class="compare" markdown="1">

```asm title="count_private"
LBB0_2:
  bl    __Z4tickv
  subs  w20, w20, #1
  b.ne  LBB0_2
  mov   x0, x19   ; 结果就是 n
```

```asm title="count_escaped"
LBB1_1:
  ldr   w8, [sp, #12]   ; 读 c
  add   w8, w8, #1
  str   w8, [sp, #12]   ; 写回 c
  bl    __Z4tickv
  subs  w19, w19, #1
  b.ne  LBB1_1
```

</div>

编译器看不到函数体时，只能假设它做了任何它有权做的事。`count_private` 的 `c` 从未离开这个函数，`tick` 碰不到它，于是 `c` 被算成了 `n`。`count_escaped` 把 `c` 的地址交给了 `watch`，`watch` 可能把指针存起来，`tick` 再通过它读写 `c`；形参是 `const int*` 也不能排除这种可能，因为 `c` 本身不是 const 对象，`const_cast` 之后修改它是合法的。所以每次调用 `tick` 之前都要把 `c` 写回内存，之后再读出来。

这种状态叫做地址**逃逸**。常见的来源有：把局部变量的地址或引用传给看不见的函数、存进全局变量、被 lambda 按引用捕获后交给 `std::function`。限制逃逸的范围，或者让被调用的函数可见（同一翻译单元、头文件、LTO），优化器才有推理的余地。

### volatile

```cpp godbolt title="volatile.cpp" flags="-std=c++2c -O2" ok
int with_volatile(int n) {
  volatile int s = 0;
  for (int i = 0; i < n; ++i) s = s + i;   // 每次都读、写内存
  return s;
}
```

去掉 `volatile`，这就是开头的 `tri`，会被折叠成公式；加上之后，循环里每次迭代都有一条 `ldr` 和一条 `str`，一次也不能省。[[intro.abstract#8]] ¶8.1 规定，通过 volatile glvalue 的访问严格按抽象机的规则求值，它们本身就是可观察行为。[[dcl.type.cv#6]] 的注说明了用意：对象的值可能以实现无法察觉的方式改变，例如内存映射的硬件寄存器。

volatile 不提供线程之间的同步，多线程共享的数据应当用原子类型，见 [[topics/memory-model]]。在基准测试里，把结果写进一个 volatile 变量是防止计算被删除的另一种办法，代价是每次多一次内存写入。

### 异常：大多不是障碍

可能抛出异常的调用并不会让正常路径变慢。一个持有 RAII 对象、循环调用不可见函数的函数，本机加与不加 `-fno-exceptions`，循环部分的指令完全相同，只有寄存器分配不同；多出来的着陆点放在 `ret` 之后，正常执行不会经过。上面 `nrvo.cpp` 的 `one` 也是这样。详细的汇编见 [[perf/reading-assembly|读懂汇编]]，实现机制见 [[toolchain/exception-implementation]]。

异常带来的约束和看不见的函数是同一种：调用可能不返回，所以调用之前对外可见的写入不能推迟到调用之后。这条约束在函数体不可见时本来就存在，异常并没有额外增加多少。

### `-fno-strict-aliasing` 与 `-fwrapv` 的代价

两个开关都把一种 UB 变成有定义的行为，是合规的扩展（[[intro.compliance.general#11]]），代价是优化器少了一个前提：

- `-fno-strict-aliasing` 关闭基于类型的别名分析，任何类型的写入都可能改写任何对象。上表中 `vector<int>` 的 `idx` 因此退化成和 `unsigned char` 一样，从约 0.2 µs 变成 2–7 µs。依赖指针双关的旧代码用它作为安全网，新代码应当按 [[topics/type-punning]] 的办法写。
- `-fwrapv` 让有符号整数按补码回绕。编译器不能再假设 `r * stride + c` 这种下标不回绕，本机在一个二维求和的循环前多生成了一段回绕检查，向量化仍然成功；对 64×64 的数组，测量差异在噪声范围内（默认 0.47–0.87 µs，`-fwrapv` 0.47–0.58 µs，两者的最好成绩都是 0.47 µs）。它对 `x + 1 > x` 一类比较的影响见 [[topics/undefined-behavior]]。

所以 `-fwrapv` 的代价通常不大，`-fno-strict-aliasing` 在大量使用指针的循环里可能很显著。两者都应该在自己的代码上测过再决定。

## `-ffast-math`

前面 `double` 版的 `total` 加法只能按顺序做，是因为浮点加法不满足结合律。`-ffast-math` 打开 `-fassociative-math` 等一组选项，允许编译器按结合律重排。本机 Clang 23 加上它之后，`SqF` 版的主循环变成四路 `fmla.2d` 向量乘加，每路各自累加，循环结束后再把四路合起来；结果的舍入因此可能与按顺序相加不同。它还假设不存在 NaN 和无穷大，会让检查 NaN 的代码失效，见 [[topics/arithmetic]]；向量化本身见 [[perf/vectorization|向量化]]。

## 思考题

!!! question "1"
    下面的基准测试在 `-O2` 下测出的时间几乎与循环次数无关。发生了什么？怎样改？
    ```cpp
    int square(int x) { return x * x; }
    // 同一个文件里
    auto t0 = clk::now();
    for (int i = 0; i < 1'000'000; ++i) { int r = square(i); }
    auto t1 = clk::now();
    ```

<details markdown="1">
<summary>答案</summary>

`square` 在同一个翻译单元里，被内联之后，`r` 从未被使用，计算它没有任何可观察行为。按 as-if 规则（[[intro.abstract#1]]），整个循环都可以删掉，测到的只是两次读时钟之间的空隙。本机 Clang 23 生成的代码里，两次 `bl …steady_clock3nowEv` 之间没有任何指令。注意 `i * i` 在 `i` 较大时会溢出，那是 UB，编译器同样不必为它保留代码。

改法是让编译器无法证明结果没人用：把 `r` 交给本页的 `escape`，或者写进 volatile 变量；同时把被测函数放进另一个翻译单元，或者标 `[[gnu::noinline]]`，防止它和循环一起被优化掉。测量方法见 [[perf/measuring|测量]]。
</details>

!!! question "2"
    `std::vector<std::byte>` 和 `std::vector<char8_t>` 上的 `for (std::size_t i = 0; i < v.size(); ++i) v[i] = …;`，哪个循环每次迭代都要重新读 `v.size()`？

<details markdown="1">
<summary>答案</summary>

`std::byte` 的那个。[[basic.lval#11]] ¶11.3 允许通过 `char`、`unsigned char`、`std::byte` 类型的 glvalue 访问任何对象，所以一次 `std::byte` 写入可能改写 `vector` 内部的指针，编译器不能把 `size()` 提出循环。`char8_t` 是独立的类型，不在名单里，它的写入改不了指针对象。本机 Clang 23 的报告：`char8_t` 的循环 `vectorized loop (vectorization width: 16, interleaved count: 4)`，`std::byte` 的循环 `loop not vectorized`。
</details>

!!! question "3"
    把 `[[gnu::always_inline]]` 加在一个只在 `.cpp` 里定义、头文件里只有声明的函数上，其他翻译单元里对它的调用会被内联吗？

<details markdown="1">
<summary>答案</summary>

不会。内联需要函数体，编译其他翻译单元时编译器只看到声明，属性也就无从生效，只有定义所在的翻译单元内部的调用会被内联。要让各处都能内联，就把定义连同 `inline` 放进头文件（[[dcl.inline#2]] 的注允许内联函数在多个翻译单元中定义），或者使用 LTO。
</details>

## 小结

| 优化 | 做什么 | 常见的障碍 |
|---|---|---|
| 内联 | 把函数体复制到调用点，为其他优化铺路 | 函数体在别的翻译单元；成本超过阈值 |
| 常量传播与折叠 | 编译期算出能算的值 | 值来自运行期或内存 |
| 去虚化 | 虚调用变直接调用，进而内联 | 动态类型未知；类和函数都不是 `final` |
| NRVO | 具名返回变量直接建在返回值位置 | 多个候选变量；`return std::move(x)` |
| 死存储消除 | 删掉没人读的写入 | 中间有看不见的调用；需要保留的清零反被删掉 |
| 循环不变量外提 | 把不变的计算移出循环 | 循环里有可能别名的写入 |
| 向量化 | 一条指令处理多个元素 | 别名；浮点结合律；`-O1`、`-Os` |

| 障碍 | 编译器的假设 | 对策 |
|---|---|---|
| `char`、`unsigned char`、`std::byte` 写入 | 可能改写任何对象 | 把要反复读的值放进局部变量 |
| 同类型指针 | 可能重叠 | 局部变量；`__restrict`（扩展） |
| 看不见的函数 | 可能读写任何可达的内存 | 让函数体可见；LTO |
| 逃逸的地址 | 每次调用后都可能变 | 不把局部变量的地址交出去 |
| volatile | 每次访问都是可观察行为 | 只用于硬件和信号处理一类场合 |
