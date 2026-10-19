---
title: 缓存、局部性与数据布局
summary: 为什么访问内存的方式常常比计算量更能决定速度：在本机测出各级缓存和内存的延迟，比较顺序、跨步、随机访问，行优先与列优先，链表与 vector，AoS 与 SoA，成员顺序造成的填充，预取、TLB 与大页，以及用位压缩数据的效果。
status: draft
order: 50
group: 内存
since: c++98
papers: P1847R4
related: basic.align, dcl.align, class.mem, expr.rel, expr.add, intro.abstract, vector.bool, bitset, support.dynamic, toolchain/object-layout-and-vtables, perf/measuring, perf/reading-assembly, perf/vectorization, perf/false-sharing, perf/allocation, perf/choosing-containers
tags: 性能, 缓存, 局部性, 数据布局, 对齐, 填充, TLB, 预取
updated: 2026-10-19
---

!!! tldr
    - 本机（Apple M2 Pro）一次读取的延迟从 L1 缓存的约 0.9 ns 到内存的 115–150 ns，相差一百多倍。工作集落在哪一级缓存，往往比指令条数更能决定速度。
    - CPU 以缓存行为单位搬运数据，本机一行是 128 字节。顺序访问能用满每一行，还能被硬件预取；跨步超过一行、随机访问、沿指针跳转都会让每次读取付出整行甚至整次内存访问的代价。
    - 相互独立的读取可以重叠执行，相互依赖的读取（链表、树）只能一个接一个等。同样是随机访问内存，前者本机约 5 ns 一次，后者约 120 ns。
    - 数据布局由你控制，编译器不会替你改：标准要求成员按声明顺序排列，所以填充多少取决于你写的顺序。把热字段集中、按字段拆成数组（SoA）、用位代替字节，都是在减少每次要搬运的字节数。
    - `__builtin_prefetch` 和大页在本机都不是常规手段：手动预取的效果小且依赖距离，macOS 在 Apple 芯片上不提供用户态大页。

同一个 8192×8192 的 `int` 矩阵，按行求和和按列求和做的是完全相同的加法：

<div class="compare" markdown="1">

```cpp
// 按行：相邻元素
for (size_t i = 0; i < n; ++i)
  for (size_t j = 0; j < n; ++j)
    s += m[i * n + j];
```

```cpp
// 按列：相隔 4n 字节
for (size_t j = 0; j < n; ++j)
  for (size_t i = 0; i < n; ++i)
    s += m[i * n + j];
```

</div>

在本机上，按列求和慢 75 倍。差别全部来自访问内存的顺序。要理解它，先要知道一次内存访问到底有多贵。

下文的计时都用本节共用的 [[perf/measuring#harness|bench.hpp]]：`bench::run` 先预热，再取 31 个样本的中位数；`bench::compare` 交替测量两个版本，报告两者中位数的比值；`bench::do_not_optimize(x)` 是一条不生成指令的内联汇编，让编译器认为 `x` 被读写过，不能删掉产生它的代码。

程序都用 `clang++ -std=c++2c -O2`（Homebrew Clang 23.1.3，libc++，arm64）编译，并用 `prefer_performance_cores()` 请求在性能核上运行。测量期间机器上还有很多其他进程（load average 80–120），共享缓存和内存带宽都被占用，绝对数字偏慢、偏散。同一进程内背靠背测得的比值更可信，小的差异不要过度解读。

## 一次读取有多贵

### 缓存与缓存行

CPU 和内存之间隔着几级**缓存**（cache）：容量小、速度快的存储，保存最近用过的数据副本。读取一个地址时，如果数据已经在缓存里（命中），很快就能拿到；否则（未命中）要去下一级取，一直到内存。

缓存不按字节管理数据，而是按固定大小的块，叫做**缓存行**（cache line）。读一个 `int`，搬进缓存的是它所在的一整行。本机的参数可以用 `sysctl` 读出：

```bash
sysctl hw.cachelinesize hw.pagesize hw.l1dcachesize hw.l2cachesize \
       hw.perflevel0.l1dcachesize hw.perflevel0.l2cachesize hw.perflevel0.cpusperl2
```

| 键 | 本机的值 | 含义 |
|---|---|---|
| `hw.cachelinesize` | 128 | 缓存行 128 字节 |
| `hw.pagesize` | 16384 | 虚拟内存页 16 KiB |
| `hw.l1dcachesize` | 65536 | 64 KiB，这是能效核的 L1 数据缓存 |
| `hw.l2cachesize` | 4194304 | 4 MiB，同样是能效核的值 |
| `hw.perflevel0.l1dcachesize` | 131072 | 性能核的 L1 数据缓存：128 KiB |
| `hw.perflevel0.l2cachesize` | 16777216 | 性能核的 L2：16 MiB |
| `hw.perflevel0.cpusperl2` | 4 | 每 4 个性能核共享一个 L2 |

不带 `perflevel` 的键报告的是能效核的数值，测量性能核时要看 `perflevel0`。L2 之后还有一级所有核心共享的系统级缓存（SLC），`sysctl` 不报告它的大小（`hw.l3cachesize` 不存在）。

128 字节的缓存行比 x86-64 常见的 64 字节大一倍。libc++ 的 `std::hardware_destructive_interference_size` 在本机是 128，`hardware_constructive_interference_size` 是 64（[[hardware.interference]]，见 [[support.dynamic]]），两者都来自编译器的预定义宏 `__GCC_DESTRUCTIVE_SIZE` 和 `__GCC_CONSTRUCTIVE_SIZE`。前者用于把被不同线程写入的数据隔开，见 [[perf/false-sharing|伪共享]]。

### 用追指针测延迟

要测一次读取的延迟，必须让每次读取都等上一次完成。办法是让下一次读的地址就是这一次读到的值，也就是沿链表走：

```cpp title="latency.cpp"
#include "bench.hpp"
#include <cstdio>
#include <numeric>
#include <random>
#include <vector>

struct alignas(128) Slot { Slot* next; };   // 一个节点独占一条缓存行

// 在 kib KiB 的缓冲区里沿一个随机环追指针，打印每一步的耗时
void chase(std::size_t kib) {
  std::vector<Slot> buf(kib * 1024 / sizeof(Slot));
  std::size_t n = buf.size();
  std::vector<std::size_t> perm(n);
  std::iota(perm.begin(), perm.end(), 0);
  std::mt19937_64 rng(42);
  for (std::size_t i = n - 1; i > 0; --i)    // Sattolo 算法：排列只有一个环
    std::swap(perm[i], perm[rng() % i]);
  for (std::size_t i = 0; i < n; ++i) buf[i].next = &buf[perm[i]];

  Slot* p = &buf[0];
  char name[32];
  std::snprintf(name, sizeof name, "%zu KiB", kib);
  bench::run(name, [&] {
    p = p->next;                             // 下一个地址取决于这次读到的值
    bench::do_not_optimize(p);
  });
}

int main() {
  bench::prefer_performance_cores();
  for (std::size_t kib = 16; kib <= 1024 * 1024; kib *= 2) chase(kib);
}
```

几个设计决定各有理由：

- `alignas(128)` 让每个节点占一整行（[[dcl.align]]），每走一步都碰一条新的缓存行。
- 链接顺序是随机排列。顺序排列的话，硬件会猜出下一个地址并提前取数据，测到的就不是延迟了。
- 普通的随机打乱可能把节点分成几个小环，指针在小环里打转，实际访问的内存比缓冲区小。Sattolo 算法只生成恰好一个环的排列，保证走遍所有节点。

本机一次运行的中位数（每一步）：

| 工作集 | 每步 | 大致落在 |
|---|---|---|
| 16 KiB – 128 KiB | 0.92 ns | L1 |
| 256 KiB | 6.6 ns | L2 |
| 512 KiB – 4 MiB | 6.0 ns | L2 |
| 8 MiB | 7.5 ns | L2 |
| 16 MiB | 58 ns（最小值 21 ns） | 过渡区 |
| 32 MiB – 64 MiB | 115–118 ns | 内存 |
| 128 MiB – 1 GiB | 125–148 ns | 内存 |

台阶清楚地落在性能核的参数上：128 KiB 以内是 L1，到 256 KiB 跳到 L2，16 MiB 附近开始离开 L2。按能效核的 `hw.l1dcachesize`（64 KiB）去预期，就会对不上。L2 和内存之间这条曲线上没有看到属于 SLC 的清晰平台，16 MiB 一档的中位数和最小值相差很大，属于过渡区。工作集超过 64 MiB 后延迟继续缓慢上升，一个可能的原因是地址翻译也开始未命中，见后文的 TLB 一节。

!!! note "数量级比具体数字重要"
    L1 和内存之间差了一百多倍。一个工作集放不进缓存、访问又互相依赖的循环，每次迭代要等一百多纳秒，这期间 CPU 本可以执行几百条指令。

## 顺序、跨步与随机

延迟只是最坏情况。相互独立的读取可以同时在路上，CPU 也会识别规律的访问并提前取数据，这叫**硬件预取**（hardware prefetching）。下面在 64 MiB 的 `uint32_t` 数组上，按不同步长让每个元素恰好被读一次：

```cpp title="stride.cpp"
#include "bench.hpp"
#include <cstdint>
#include <cstdio>
#include <numeric>
#include <random>
#include <vector>

int main() {
  bench::prefer_performance_cores();
  const std::size_t n = 16 * 1024 * 1024;            // 64 MiB 的 uint32_t
  std::vector<std::uint32_t> a(n, 1);
  for (std::size_t stride : {1, 4, 8, 16, 32, 64, 1024, 4096}) {
    char name[32];
    std::snprintf(name, sizeof name, "stride %zu B", stride * 4);
    auto s = bench::run(name, [&] {
      std::uint32_t sum = 0;
      for (std::size_t start = 0; start < stride; ++start)   // 每个元素恰好读一次
        for (std::size_t i = start; i < n; i += stride) sum += a[i];
      bench::do_not_optimize(sum);
    }, 7);
    std::printf("  -> %.2f ns/elem\n", s.median / n);
  }
  std::vector<std::uint32_t> idx(n);                 // 随机顺序，同样每个元素读一次
  std::iota(idx.begin(), idx.end(), 0u);
  std::shuffle(idx.begin(), idx.end(), std::mt19937_64(1));
  auto s = bench::run("random", [&] {
    std::uint32_t sum = 0;
    for (std::size_t i = 0; i < n; ++i) sum += a[idx[i]];
    bench::do_not_optimize(sum);
  }, 7);
  std::printf("  -> %.2f ns/elem\n", s.median / n);
}
```

步长是运行期的值，所以每种步长执行的都是同一段标量循环，汇编里内层循环没有向量指令。每个元素的指令数相同，差别只来自内存：

| 步长 | 每个元素 |
|---|---|
| 4 B、16 B | 0.48 ns |
| 32 B | 1.22 ns（最小值 0.57 ns） |
| 64 B | 2.09 ns |
| 128 B | 4.56 ns |
| 256 B | 5.64 ns |
| 4 KiB | 6.94 ns |
| 16 KiB | 7.77 ns |
| 随机顺序 | 3.80 ns |

步长 4 字节时，一条 128 字节的缓存行供 32 次读取使用；步长达到 128 字节，每次读取都要搬一整行，只用其中 4 个字节。之后再加大步长，每次读取还是一行，但规律越来越难被预取器利用，跨页也越来越频繁。

随机顺序每个元素 3.8 ns，比追指针的 120 ns 小得多。两者都在 64 MiB 以上的数据里随机读取，区别在于这里的读取互相独立：`a[idx[i]]` 的地址只取决于 `idx`，不取决于上一次读到的值，所以 CPU 可以同时发出很多个未命中的请求，等待时间互相重叠。链表、树、哈希表的冲突链则是一次读完才知道下一次读哪里。

## 二维数组：行优先与列优先

C++ 的多维数组是数组的数组（[[dcl.array#9]]），而数组的元素是连续分配的（[[dcl.array#6]]），所以 `int m[R][C]` 是**行优先**（row-major）的：同一行的元素相邻，下一行接在后面。`m[i * n + j]` 这种手工展开沿用同样的约定。按行遍历是顺序访问；按列遍历每一步跨过一整行，`n = 8192` 时就是 32 KiB。

```cpp title="matrix.cpp"
#include "bench.hpp"
#include <cstdio>
#include <vector>

long sum_rows(const std::vector<int>& m, std::size_t n) {
  long s = 0;
  for (std::size_t i = 0; i < n; ++i)
    for (std::size_t j = 0; j < n; ++j) s += m[i * n + j];   // 相邻元素
  return s;
}
long sum_cols(const std::vector<int>& m, std::size_t n) {
  long s = 0;
  for (std::size_t j = 0; j < n; ++j)
    for (std::size_t i = 0; i < n; ++i) s += m[i * n + j];   // 相隔 4n 字节
  return s;
}

int main() {
  bench::prefer_performance_cores();
  for (std::size_t n : {128, 1024, 8192}) {
    std::vector<int> m(n * n, 1);
    std::printf("n = %zu (%zu KiB)\n", n, n * n * sizeof(int) / 1024);
    bench::compare([&] { long s = sum_rows(m, n); bench::do_not_optimize(s); },
                   [&] { long s = sum_cols(m, n); bench::do_not_optimize(s); }, 11);
  }
}
```

| n | 矩阵大小 | 按行（每元素） | 按列（每元素） | 列/行 |
|---|---|---|---|---|
| 128 | 64 KiB | 0.080 ns | 0.30 ns | 3.8 |
| 1024 | 4 MiB | 0.047 ns | 2.9 ns | 62 |
| 8192 | 256 MiB | 0.11 ns | 7.9 ns | 75 |

矩阵完全放得进 L1 时，按列仍然慢 3.8 倍，这部分差别不来自缓存。看 `-O2` 的汇编：`sum_rows` 的内层循环被向量化，用 `ldp q16, q17` 一次读 32 字节，再用 `saddw`/`saddw2` 把 4 个 `int` 加宽累加；`sum_cols` 的内层循环是标量的 `ldrsw` 加 `add`，每次一个元素。连续访问让编译器能用 SIMD 指令（见 [[perf/vectorization|自动向量化]]），跨步访问不能。矩阵变大以后，缓存未命中的代价叠加上来，差距扩大到 60–75 倍。

真实代码里，解决办法是交换循环顺序，或者在无法交换时（比如矩阵转置、矩阵乘法）分块：每次只处理一个能放进缓存的小块，让块内的数据被反复使用。

## 链表与 vector

`std::list` 的每个节点单独分配，节点之间靠指针相连。遍历链表就是追指针，所以它的速度取决于节点在内存里的位置：

```cpp title="list.cpp"
#include "bench.hpp"
#include <cstdio>
#include <list>
#include <random>
#include <vector>

template<class C> long sum(const C& c) { long s = 0; for (int x : c) s += x; return s; }

int main() {
  bench::prefer_performance_cores();
  const int n = 4'000'000;
  std::vector<int> v(n, 1);
  std::list<int> fresh(n, 1);          // 节点按顺序分配，地址大体连续

  std::list<int> shuffled(n, 1);       // 同样的节点，把链接顺序打乱
  std::vector<std::list<int>::iterator> its;
  for (auto it = shuffled.begin(); it != shuffled.end(); ++it) its.push_back(it);
  std::shuffle(its.begin(), its.end(), std::mt19937_64(7));
  std::list<int> tmp;
  for (auto it : its) tmp.splice(tmp.end(), shuffled, it);   // 只改指针，不搬节点
  shuffled.swap(tmp);

  double tv = bench::run("vector", [&] { long s = sum(v); bench::do_not_optimize(s); }, 11).median;
  double tf = bench::run("list, fresh", [&] { long s = sum(fresh); bench::do_not_optimize(s); }, 11).median;
  double ts = bench::run("list, shuffled", [&] { long s = sum(shuffled); bench::do_not_optimize(s); }, 11).median;
  std::printf("ns/elem: vector %.3f  list fresh %.2f  list shuffled %.1f\n", tv / n, tf / n, ts / n);
}
```

| 容器 | 每个元素 |
|---|---|
| `vector<int>` | 0.058 ns |
| `list<int>`，刚创建 | 1.11 ns |
| `list<int>`，链接顺序打乱 | 134 ns |

刚创建的链表，节点是连续分配的，地址大体相邻，缓存和预取器仍然有效。它比 `vector` 慢 19 倍，是因为每一步要先读出 `next` 才能继续，循环无法向量化，每个节点还要多占两个指针。`splice` 只改链接、不移动节点，打乱之后遍历顺序与地址顺序无关，每一步都是一次内存延迟，和前面追指针测得的 120–150 ns 相符。

真实程序里的链表经过反复插入删除，节点的分布接近后一种情况。容器怎么选见 [[perf/choosing-containers|选择容器]]，分配器怎样影响节点位置见 [[perf/allocation|堆分配的代价]]。

## 成员顺序与填充

### 编译器不会替你重排

```cpp title="layout.cpp" run impl
#include <cstddef>
#include <cstdint>

struct Order {               // 按业务含义排列
  bool         active;
  double       price;
  std::int16_t venue;
  std::int64_t qty;
  bool         is_buy;
};
struct OrderSorted {         // 按对齐要求从大到小排列
  double       price;
  std::int64_t qty;
  std::int16_t venue;
  bool         active;
  bool         is_buy;
};
static_assert(sizeof(Order) == 40 && alignof(Order) == 8);
static_assert(offsetof(Order, price) == 8 && offsetof(Order, qty) == 24);
static_assert(sizeof(OrderSorted) == 24);
int main() {}
```

每个类型有一个**对齐要求**（[[g:alignment|alignment]]）：这种类型的对象只能放在它的整数倍地址上（[[basic.align#1]]）。`double` 和 `int64_t` 在本机要求 8 字节对齐，所以 `active` 后面要空出 7 个字节才能放 `price`，`venue` 后面空出 6 个字节才能放 `qty`；整个类的大小还要向上取整到 8 的倍数，数组里下一个元素才对齐。这些空出来的字节就是**填充**（padding）。同样 20 字节的数据，`Order` 占 40 字节，`OrderSorted` 占 24 字节。具体的大小和对齐都由实现决定，所以这个例子标为 {{impl}}。

Clang 的 `-Wpadded` 会逐一指出填充的位置：

```text
layout.cpp:6:16: warning: padding struct 'Order' with 7 bytes to align 'price' [-Wpadded]
layout.cpp:8:16: warning: padding struct 'Order' with 6 bytes to align 'qty' [-Wpadded]
layout.cpp:4:8: warning: padding size of 'Order' with 7 bytes to alignment boundary [-Wpadded]
layout.cpp:11:8: warning: padding size of 'OrderSorted' with 4 bytes to alignment boundary [-Wpadded]
```

`clang++ -Xclang -fdump-record-layouts -fsyntax-only` 可以打印完整的偏移表，用法见 [[toolchain/object-layout-and-vtables]]。

编译器不会自动按大小重排成员。[[expr.rel#4.2]] 要求指向同一对象中后声明的非静态数据成员的指针比较起来更大（零大小的子对象和联合体除外），[[class.mem.general#24]] 的注释据此说明：成员按声明顺序分配，后声明的地址更高，对齐要求可能让相邻成员之间留出空隙。

!!! history "C++23：访问控制不再允许重排"
    C++20 及以前，这条顺序保证只适用于访问控制相同的成员，`public:` 段和 `private:` 段之间的先后未指定。主流编译器从未利用过这项许可。C++23 的 [[P1847R4]] 删除了它，现在所有非静态数据成员都按声明顺序排列，与访问控制无关。

### 填充的代价

填充的字节和有用的字节一样要被搬进缓存。在 800 万个元素上统计 `active` 订单的数量：

```cpp title="layout-bench.cpp"
// 接上面的 Order 和 OrderSorted
template<class T> long open_qty(const std::vector<T>& v) {
  long s = 0;
  for (const T& o : v) if (o.active) s += o.qty;
  return s;
}
// main 中：
//   std::vector<Order> a(8'000'000);  std::vector<OrderSorted> b(8'000'000);
//   每三个元素一个 active，qty 全为 1
//   bench::compare([&] { long s = open_qty(a); bench::do_not_optimize(s); },
//                  [&] { long s = open_qty(b); bench::do_not_optimize(s); }, 11);
```

两次运行中 `OrderSorted` 与 `Order` 的耗时比是 0.664 和 0.654，与大小之比 24/40 = 0.6 接近。数组大到放不进缓存时，扫描的速度大体由每个元素的字节数决定。

## 热字段与冷字段

### AoS、热/冷拆分与 SoA

一个粒子系统每一帧只更新位置，颜色、名字等字段只在渲染或调试时用到。经常访问的字段叫**热字段**，很少访问的叫**冷字段**。下面比较三种布局：

```cpp title="particles.cpp"
#include "bench.hpp"
#include <cstdio>
#include <vector>

struct Particle {              // AoS：热字段和冷字段放在一起
  float x, y, z, vx, vy, vz;   // 每一帧都更新：24 字节
  float color[4];              // 只有渲染时用
  char name[48];               // 只有调试时用
  int id, flags;
};                             // 96 字节

struct Hot  { float x, y, z, vx, vy, vz; };              // 热/冷拆分：24 字节
struct Cold { float color[4]; char name[48]; int id, flags; };

struct Particles {             // SoA：每个字段一个数组
  std::vector<float> x, y, z, vx, vy, vz;
};

void step(std::vector<Particle>& ps, float dt) {
  for (auto& p : ps) { p.x += p.vx * dt; p.y += p.vy * dt; p.z += p.vz * dt; }
}
void step(std::vector<Hot>& ps, float dt) {
  for (auto& p : ps) { p.x += p.vx * dt; p.y += p.vy * dt; p.z += p.vz * dt; }
}
void step(Particles& s, float dt) {
  for (std::size_t i = 0; i < s.x.size(); ++i) s.x[i] += s.vx[i] * dt;
  for (std::size_t i = 0; i < s.y.size(); ++i) s.y[i] += s.vy[i] * dt;
  for (std::size_t i = 0; i < s.z.size(); ++i) s.z[i] += s.vz[i] * dt;
}

int main() {
  bench::prefer_performance_cores();
  static_assert(sizeof(Particle) == 96 && sizeof(Hot) == 24);
  for (std::size_t n : {4'000, 4'000'000}) {
    std::vector<Particle> aos(n, Particle{0, 0, 0, 1, 1, 1, {}, {}, 0, 0});
    std::vector<Hot> hot(n, Hot{0, 0, 0, 1, 1, 1});
    std::vector<Cold> cold(n);                 // 按下标与 hot 对应
    std::vector<float> zero(n), one(n, 1);
    Particles soa{zero, zero, zero, one, one, one};
    float dt = 0.01f;
    bench::do_not_optimize(dt);
    std::printf("n = %zu\n", n);
    double a = bench::run("AoS", [&] { step(aos, dt); bench::clobber_memory(); }).median;
    double h = bench::run("hot/cold", [&] { step(hot, dt); bench::clobber_memory(); }).median;
    double s = bench::run("SoA", [&] { step(soa, dt); bench::clobber_memory(); }).median;
    std::printf("  ns/particle: AoS %.2f  hot/cold %.2f  SoA %.2f\n", a / n, h / n, s / n);
  }
}
```

**AoS**（array of structures，结构体数组）是最自然的写法：一个粒子一个结构体，放进一个数组。**SoA**（structure of arrays，数组结构体）把每个字段单独放进一个数组。热/冷拆分介于两者之间：热字段仍然组成结构体，冷字段挪到另一个按相同下标对应的数组里。

| 粒子数 | AoS（96 B/个） | 热/冷拆分（24 B/个） | SoA |
|---|---|---|---|
| 4000 | 1.19 ns | 0.46 ns | 0.18 ns |
| 400 万 | 2.75 ns | 0.72 ns | 0.56 ns |

AoS 每更新一个粒子要搬运 96 字节，其中 72 字节这一帧用不到。4000 个粒子时 AoS 共 375 KiB，超出了 128 KiB 的 L1，拆分后的 94 KiB 则放得下。400 万个粒子时三者都在内存里，耗时大体跟着每个粒子的字节数走。

SoA 和热/冷拆分搬运的字节数相同，却又快了一截，原因在指令上。SoA 版本的循环被向量化，内层每次迭代用 4 条 `fmla.4s` 处理 16 个 `float`；AoS 和拆分版本里，`x`、`y` 用一条 `fmla.2s`，`z` 用一条标量 `fmadd`，每次迭代只处理一个粒子。SoA 的循环前还有一段运行期检查（`ccmp`），因为编译器无法证明 `x` 和 `vx` 两个数组不重叠，向量化的条件见 [[perf/vectorization|自动向量化]]。

!!! pitfall "SoA 不是免费的"
    SoA 让一次只看一个粒子的代码变难写：取一个完整的粒子要读 6 个数组，增删元素要同步维护所有数组。按访问模式拆分：每帧扫描全部元素、只用少数字段的代码适合 SoA 或热/冷拆分；随机取出单个对象、用到大部分字段的代码适合 AoS。

## 预取

### 硬件预取与手动预取

前面已经看到，顺序和规律跨步的访问会被硬件自动预取。GCC 和 Clang 还提供一个扩展 `__builtin_prefetch(addr)`，它生成一条提示指令（arm64 上是 `prfm`），请求把 `addr` 所在的行提前取进缓存。它不是标准 C++，提示也可能被硬件忽略。

手动预取只对硬件猜不出、但程序提前知道的地址有意义。典型场景是按索引表随机读取：读 `a[idx[i]]` 时，`idx[i + d]` 已经知道了。

```cpp title="prefetch.cpp"
#include "bench.hpp"
#include <cstdint>
#include <cstdio>
#include <random>
#include <vector>

int main() {
  bench::prefer_performance_cores();
  const std::size_t n = 32 * 1024 * 1024;     // 256 MiB 的 uint64_t
  const std::size_t m = 4 * 1024 * 1024;      // 每轮 400 万次随机读
  std::vector<std::uint64_t> a(n, 1);
  std::vector<std::uint32_t> idx(m);
  std::mt19937_64 rng(3);
  for (auto& i : idx) i = rng() % n;

  auto gather = [&](std::size_t d) {          // 提前 d 次迭代预取
    return [&a, &idx, d] {
      std::uint64_t sum = 0;
      for (std::size_t i = 0; i < m; ++i) {
        if (d != 0 && i + d < m) __builtin_prefetch(&a[idx[i + d]]);
        sum += a[idx[i]];
      }
      bench::do_not_optimize(sum);
    };
  };
  for (std::size_t d : {8, 32, 128}) {
    std::printf("d = 0 vs d = %zu: ", d);
    bench::compare(gather(0), gather(d), 11);
  }
}
```

`i + d < m` 这个条件不能省：`idx[i + d]` 越界是未定义行为，与预取是否只是提示无关。

| 预取距离 d | 耗时比（预取/不预取），两次运行 |
|---|---|
| 8 | 1.23、1.10 |
| 32 | 1.03、1.12 |
| 128 | 0.85、0.83 |

不预取时每次读取约 5.3 ns，已经比内存延迟小二十多倍，因为这些读取互相独立，CPU 本来就在重叠它们。距离太近时，预取的数据还没到就要用了，多出的指令反而让循环变慢；距离 128 时快了约 15%。最佳距离取决于内存延迟、循环体的长度和硬件，换一台机器就要重新测。

对追指针这样的依赖链，手动预取没有用：下一个地址只有读完当前节点才知道，而那时去预取它已经太晚了。在前面 128 MiB 的随机链表上，每一步先 `__builtin_prefetch(p->next)` 再前进，耗时比是 0.987，与不预取没有区别。要让链式结构变快，只能改变布局，例如把节点放进连续的数组，用下标代替指针。

## TLB 与大页

### 地址翻译也要缓存

程序使用的是虚拟地址，每次访问都要翻译成物理地址。翻译以页为单位，本机一页 16 KiB。最近用过的翻译结果缓存在 **TLB**（translation lookaside buffer）里；TLB 未命中时，硬件要读内存中的页表才能完成翻译。

下面让 n 个节点分别紧挨着（相距 128 字节）或者每页一个（相距 16 KiB + 128 字节），比较追指针的延迟。两种布局访问的缓存行数相同，区别只在于跨过了多少页：

```cpp title="tlb.cpp"
#include "bench.hpp"
#include <cstdio>
#include <memory>
#include <numeric>
#include <random>
#include <unistd.h>
#include <vector>

struct alignas(128) Slot { Slot* next; };

// n 个节点，相邻两个节点相距 gap 字节（gap 是 128 的倍数），沿随机环追指针
auto chase(std::size_t n, std::size_t gap) {
  std::size_t k = gap / sizeof(Slot);
  auto buf = std::make_shared<std::vector<Slot>>(n * k);
  auto at = [&](std::size_t i) { return &(*buf)[i * k]; };
  std::vector<std::size_t> perm(n);
  std::iota(perm.begin(), perm.end(), 0);
  std::mt19937_64 rng(42);
  for (std::size_t i = n - 1; i > 0; --i) std::swap(perm[i], perm[rng() % i]);
  for (std::size_t i = 0; i < n; ++i) at(i)->next = at(perm[i]);
  return [buf, p = at(0)]() mutable {
    p = p->next;
    bench::do_not_optimize(p);
  };
}

int main() {
  bench::prefer_performance_cores();
  const std::size_t page = getpagesize();          // 本机 16384
  for (std::size_t n : {256, 1024, 4096}) {
    std::printf("%zu nodes: packed vs one per page\n", n);
    bench::compare(chase(n, 128), chase(n, page + 128));
  }
  bench::run("256, gap = page", chase(256, page));
}
```

| 节点数 | 紧挨着 | 每页一个 | 跨过的地址范围 |
|---|---|---|---|
| 256 | 0.92 ns | 0.92 ns | 4 MiB |
| 1024 | 0.94 ns | 3.0–7.0 ns | 16 MiB |
| 4096 | 6.0–6.9 ns | 20–23 ns | 64 MiB |

1024 个节点只占 128 KiB 的缓存行，紧挨着时全在 L1 里；分散到 1024 页上，数据仍然可能在缓存里，但地址翻译开始未命中，每步慢了几倍。延迟曲线在 64 MiB 以后仍在缓慢上升，很可能也有这个因素。

节点间距恰好是 16 KiB（不加 128 字节）时，256 个节点的延迟从 0.92 ns 升到 5.2–6.8 ns。这次的原因不在 TLB：缓存按地址的低位把行分到不同的组里，间距是 2 的大幂次时，所有节点落进同几个组，组装满了就互相挤出，128 KiB 的 L1 实际只用上一小部分。按 2 的幂次跨步访问（例如列宽为 4096 的矩阵按列遍历）会碰到同样的问题，给每行加一点填充就能避开。

### 大页在 macOS 上不可用

更大的页能让同样数量的 TLB 项覆盖更多内存。Linux 提供透明大页和 `MAP_HUGETLB`。macOS 的 `mmap` 有 `VM_FLAGS_SUPERPAGE_SIZE_ANY` 和 `VM_FLAGS_SUPERPAGE_SIZE_2MB` 两个标志（通过 `fd` 参数传入），但在本机（Apple 芯片，macOS 26）上两者都返回 `EINVAL`（Invalid argument）。这台机器上用户程序能做的，是减少跨过的页数：让一起使用的数据在地址上也靠在一起。

## 用位代替字节

一个标志只需要 1 位，存成 `bool` 或 `char` 却占 8 位。标准对 `vector<bool>` 的规定是不要求按 `bool` 连续存储，并推荐按位压缩（[[vector.bool.pspc#3]]）；`std::bitset<N>` 也按位存储（见 [[bitset]]）。压缩后同一条缓存行能装下 8 倍的标志：

```cpp title="flags.cpp"
#include "bench.hpp"
#include <cstdint>
#include <cstdio>
#include <memory>
#include <random>
#include <vector>

template<class Flags> auto lookups(std::size_t n, const std::vector<std::uint32_t>& q) {
  auto f = std::make_shared<Flags>(n);
  for (std::size_t i = 0; i < n; i += 3) (*f)[i] = true;
  return [f, &q] {
    std::size_t hits = 0;
    for (auto i : q) hits += (*f)[i];
    bench::do_not_optimize(hits);
  };
}

int main() {
  bench::prefer_performance_cores();
  std::mt19937 rng(5);
  for (std::size_t n : {1u << 20, 1u << 25, 1u << 28}) {
    std::vector<std::uint32_t> q(1'000'000);
    for (auto& x : q) x = rng() % n;
    std::printf("%zu flags: bool %zu KiB, char %zu KiB\n", n, n / 8 / 1024, n / 1024);
    auto [b, c] = bench::compare(lookups<std::vector<bool>>(n, q),
                                 lookups<std::vector<char>>(n, q), 11);
    std::printf("  ns/lookup: bool %.2f  char %.2f\n", b.median / q.size(), c.median / q.size());
  }
}
```

| 标志数 | `vector<bool>` 大小 | `vector<char>` 大小 | `vector<bool>` 每次 | `vector<char>` 每次 |
|---|---|---|---|---|
| 2²⁰ | 128 KiB | 1 MiB | 0.38 ns | 0.60 ns |
| 2²⁵ | 4 MiB | 32 MiB | 1.2–1.3 ns | 2.5–5.7 ns |
| 2²⁸ | 32 MiB | 256 MiB | 4.2–4.4 ns | 4.5–5.0 ns |

这是三次运行中两次的结果；另一次在 2²⁸ 这一档测出 `vector<bool>` 18.5 ns、`vector<char>` 7.5 ns，受机器负载影响明显，这一档的差别不能下结论。

前两档的差别都来自层级：`vector<bool>` 放得进 L1 或 L2 时，`vector<char>` 已经落到了下一级。按位存储每次访问要多做移位和掩码，两者都放不进 L2 以后，节省的空间就换不来多少速度了。`vector<bool>` 的代理引用、不能取地址、相邻元素的并发写构成数据竞争等问题见 [[vector.bool]]。

## 思考题

!!! question "思考题 1"
    把 `struct S { char tag; double v; };` 改成 `struct S { double v; char tag; };`，`sizeof(S)` 在本机是多少？`std::vector<S>` 的内存占用会减少吗？

<details markdown="1">
<summary>答案</summary>

两种写法在本机都是 16。`double` 要求 8 字节对齐，前一种在 `tag` 后面填充 7 字节，后一种在 `tag` 后面有 7 字节尾部填充，因为 `sizeof` 必须是对齐的整数倍，数组中下一个元素的 `v` 才能对齐。调整顺序只能消除成员之间的填充，不能消除为满足对齐而产生的尾部填充。只有当几个小成员能凑在一起填满同一段空隙时，重排才能减小大小，就像 `Order` 和 `OrderSorted` 那样。要进一步压缩，只能把 `tag` 挪出去（热/冷拆分或 SoA），或者用 `#pragma pack` 之类的扩展放弃对齐。后者不是标准 C++，会产生未对齐的成员，访问可能变慢，取这些成员的地址当作普通指针使用也不安全。
</details>

!!! question "思考题 2"
    有人在遍历 `std::map` 的循环里对下一个节点调用 `__builtin_prefetch`，期望加速。根据前文的测量，你预期效果如何？还有什么更有效的改法？

<details markdown="1">
<summary>答案</summary>

`std::map` 的迭代是沿树的指针移动，下一个节点的地址要读完当前节点才知道，和前文的追指针一样是依赖链。提前一个节点预取，等于在马上就要读的时候才发出请求，前文在随机链表上测得的耗时比是 0.987，没有收益。更有效的办法是改变布局：如果键的集合构建后很少修改，可以改用排序后的 `std::vector`（或 C++23 的 `std::flat_map`）加二分查找，遍历就变成了顺序访问。
</details>

!!! question "思考题 3"
    一个 4096×4096 的 `float` 矩阵按列求和，把每行的存储长度改成 4096 + 32 个元素（多出的不用）以后，本机测得耗时降到原来的 0.61–0.64。为什么？

<details markdown="1">
<summary>答案</summary>

每行 4096 个 `float` 是 16 KiB，正好等于本机的页大小，也是 2 的大幂次。按列遍历时相邻两次访问相隔 16 KiB，地址的低位全部相同，这些行被分到缓存的同几个组里，互相挤出，缓存的有效容量大大缩小。TLB 一节里间距恰好 16 KiB 的那组测量就是这个现象。多出 32 个元素（128 字节，正好一条缓存行）后，连续几行的同一列落在不同的组里，冲突消失。按列遍历仍然每次要搬一整行，只是能用上整个缓存了，所以仍比按行遍历慢得多。
</details>

## 小结

| 问题 | 本机观察 | 对策 |
|---|---|---|
| 工作集超出缓存 | L1 约 0.9 ns，L2 约 6 ns，内存 115–150 ns | 缩小热数据，分块处理 |
| 跨步、按列访问 | 步长到 128 B 后每次读取都付一整行；按列比按行慢 4–75 倍 | 交换循环顺序，按访问顺序存放数据 |
| 依赖链（链表、树） | 打乱的链表每个元素 134 ns，`vector` 0.058 ns | 用连续数组和下标，减少指针跳转 |
| 填充 | `Order` 40 B 与 24 B 版本，扫描耗时比约 0.66 | 成员按对齐从大到小声明，`-Wpadded` 检查 |
| 冷字段 | AoS 比热/冷拆分慢 2.6–3.8 倍 | 热/冷拆分或 SoA |
| 手动预取 | 随机读取最多快约 15%，依赖链无效 | 先改布局，预取要按距离实测 |
| TLB | 1024 个节点分散到 1024 页，每步慢 3–7 倍 | 让一起用的数据在地址上靠近；macOS 没有用户态大页 |
| 标志位 | 放得进下一级缓存时 `vector<bool>` 快 1.6–4.4 倍 | 用位存储，注意代理引用 |

所有程序和构建命令都可以在安静的机器上重新运行。数字会随 CPU、内存、编译器版本和系统负载变化，结论的方向和数量级更值得记住。
