---
title: 内存序与一致性
summary: memory_order 的精确定义——五个枚举值各添加什么关系、release/acquire 同步规则、coherence-ordered before、seq_cst 单一全序 S 的四条约束（含栅栏）、S 为何不必与 happens before 一致、out-of-thin-air、RMW 读最新值、C++26 的原子 modify-write 操作；附 Apple Silicon 上的实测
status: done
covers: atomics.order
papers: P0668R5
related: intro.races, intro.multithread, atomics.fences, atomics.types.operations, depr.atomics, intro.progress
tags: 标准库, 原子操作, 内存模型, memory_order
updated: 2026-10-18
---

[[intro.races]] 定义了 happens before、修改顺序、一致性规则，但把"哪些原子操作会建立 synchronizes with"留给了库条款。[atomics.order] 就是那个地方：它为 `memory_order` 的每个值规定语义，并定义 `seq_cst` 所需要的单一全序 S。

本页假设你已经读过 [[intro.multithread]]——那里有 MP、SB、IRIW 三个经典石蕊测试（litmus test）的详细分析。这里聚焦条文本身，并补充一些实测。

## memory_order 枚举（概要）

```cpp
namespace std {
  enum class memory_order : unspecified {
    relaxed = 0, acquire = 2, release = 3, acq_rel = 4, seq_cst = 5
  };
}
```

数值 1 空着：那是 `consume` 的位置。C++26 把 `memory_order::consume` 移到了附录 D（[[depr.atomics]]），并规定它"在允许 `acquire` 的任何地方都允许使用，且含义相同" {{c++26}}。枚举值保留为 1，所以老代码和 C 代码里的 `memory_order_consume` 依然能编译，只是不再有独立的"依赖序"语义。核心语言的 [[intro.races]] 也随之删除了 carries a dependency、dependency-ordered before 等定义。

## 各个值的含义（¶1）

¶1 `memory_order` 规定（非原子的）常规内存同步顺序，按 [[intro.multithread]] 中的定义：

- ¶1.1 `relaxed`：**不对内存排序**。
- ¶1.2 `release`、`acq_rel`、`seq_cst`：**store** 操作在受影响的内存位置上执行 **release 操作**。
- ¶1.3 `acquire`、`acq_rel`、`seq_cst`：**load** 操作在受影响的内存位置上执行 **acquire 操作**。

注意 ¶1.2 说的是"store 操作"，¶1.3 说的是"load 操作"。一个读-改-写操作（`fetch_add`、`exchange`、`compare_exchange`）既是 load 又是 store，所以：

| 内存序 | 对 load | 对 store | 对 RMW |
|---|---|---|---|
| `relaxed` | — | — | — |
| `acquire` | acquire | **前置条件不允许** | 读的一半是 acquire |
| `release` | **前置条件不允许** | release | 写的一半是 release |
| `acq_rel` | **前置条件不允许** | **前置条件不允许** | acquire + release |
| `seq_cst` | acquire + 进入 S | release + 进入 S | 两者 + 进入 S |

"前置条件不允许"来自各操作的 *Preconditions*（如 [[atomics.types.operations]] ¶7：`store` 的 `order` 只能是 `relaxed`、`release`、`seq_cst`）。违反是 UB {{ub}}，不是编译错误。libc++ 用 `diagnose_if` 在实参是常量时给出警告：

```cpp title="bad-order.cpp" ub
#include <atomic>
std::atomic<int> a;
int main() {
  a.store(1, std::memory_order::acquire);   // UB：违反前置条件
  int e = 0;
  a.compare_exchange_strong(e, 1, std::memory_order::relaxed,
                            std::memory_order::release);    // UB：failure 不能是 release
}
```

Clang 23 + libc++ 对两处都给出 `warning: memory order argument to atomic operation is invalid [-Wuser-defined-warnings]`。内存序来自运行期变量时就没有警告了。

注 1：使用 `relaxed` 的原子操作在内存序方面是"放松的"，但实现**仍须保证**对某个原子对象的任何原子访问，相对于对该对象的所有其他原子访问是**不可分割**的。也就是说 relaxed 放弃的是"与**其他**位置的顺序关系"，不放弃原子性，也不放弃单个对象上的一致性（[[intro.races]] ¶11–¶14）。

## release/acquire 同步（¶2）

!!! std
    An atomic operation A that performs a release operation on an atomic object M synchronizes with an atomic operation B that performs an acquire operation on M and takes its value from any side effect in the release sequence headed by A.

    在原子对象 M 上执行 release 操作的原子操作 A，与在 M 上执行 acquire 操作、且其值取自以 A 为首的 release sequence 中任一副作用的原子操作 B 同步。

这是整个 `memory_order` 机制的核心规则。三个条件缺一不可：

1. **同一个**原子对象 M；
2. A 是 release，B 是 acquire；
3. B **实际读到了** A（或 A 的 release sequence 中某个 RMW）写入的值。

第 3 条是很多人忽略的：同步是"读到了才建立"的。B 读到的是 A 之前的旧值，就没有同步，什么也推不出来。所以 acquire load 几乎总是出现在"检查值"的循环或分支里。

```cpp run title="mp-acq-rel.cpp" ok
#include <atomic>
#include <cassert>
#include <thread>

int data = 0;
std::atomic<bool> ready{false};

int main() {
  std::thread producer([] {
    data = 42;                                         // ① 普通写
    ready.store(true, std::memory_order::release);     // ② A：release
  });
  std::thread consumer([] {
    while (!ready.load(std::memory_order::acquire)) {} // ③ B：acquire，读到了 A 写的 true
    assert(data == 42);                                // ④ OK
  });
  producer.join(); consumer.join();
}
```

① sequenced before ②，② synchronizes with ③（¶2），③ sequenced before ④，所以 ① happens before ④，④ 必然读到 42。

把 ② 和 ③ 都改成 `relaxed`：没有了同步，① 与 ④ 之间没有 happens before，构成数据竞争 {{ub}}。ThreadSanitizer 会报告 `data race`：

```cpp run title="mp-relaxed.cpp" ub
#include <atomic>
#include <thread>
int data = 0;
std::atomic<bool> ready{false};
int main() {
  std::thread t1([] {
    data = 42;
    ready.store(true, std::memory_order::relaxed);
  });
  std::thread t2([] {
    while (!ready.load(std::memory_order::relaxed)) {}
    int r = data;          // UB：与 data = 42 构成数据竞争
    (void)r;
  });
  t1.join(); t2.join();
}
```

## coherence-ordered before（¶3）

¶3 定义了同一原子对象 M 上两个原子操作之间的 **coherence-ordered before** 关系（[[g:coherence-ordered-before]]）。A coherence-ordered before B，若：

- ¶3.1 A 是修改，B 读到了 A 存储的值（"读到"）；或
- ¶3.2 A 在 M 的修改顺序中先于 B（"写-写"）；或
- ¶3.3 A 与 B 不是同一个原子读-改-写操作，且存在 M 的原子修改 X，A 读到 X 存储的值，X 在修改顺序中先于 B（"读到的写早于另一个写"，即 from-read）；或
- ¶3.4 传递闭包：存在原子修改 X，A coherence-ordered before X 且 X coherence-ordered before B。

直觉：把 M 上的所有原子操作按"它看到/产生的是修改顺序中的哪个位置"排成一条线，coherence-ordered before 就是这条线上的先后。它是对 [[intro.races]] 中四条一致性规则（¶11–¶14）的"正向"表述：一致性规则说 happens before 不能与修改顺序矛盾，而 coherence-ordered before 把读操作也嵌进修改顺序里，供下面 ¶4 使用。

¶3.3 排除"同一个 RMW"是为了避免 RMW 与自己构成关系：RMW 读到的 X 当然先于它自己写入的值。

## 单一全序 S（¶4–¶7）

¶4 是 C++20 经 [[P0668R5]] 修订后的 `seq_cst` 定义：

> 存在一个包含**所有** `memory_order::seq_cst` 操作（**包括栅栏**）的单一全序 S，满足：
>
> **首先**，若 A、B 都是 seq_cst 操作且 A **strongly happens before** B，则 A 在 S 中先于 B。
>
> **其次**，对对象 M 上的每一对原子操作 A、B，若 A coherence-ordered before B，则 S 满足：
>
> - ¶4.1 若 A、B 都是 seq_cst 操作，A 在 S 中先于 B；
> - ¶4.2 若 A 是 seq_cst 操作，B happens before 某个 seq_cst 栅栏 Y，则 A 在 S 中先于 Y；
> - ¶4.3 若某个 seq_cst 栅栏 X happens before A，B 是 seq_cst 操作，则 X 在 S 中先于 B；
> - ¶4.4 若 seq_cst 栅栏 X happens before A，B happens before seq_cst 栅栏 Y，则 X 在 S 中先于 Y。

¶4.2–¶4.4 让 seq_cst **栅栏**可以"代表"它前后的非 seq_cst 原子操作参与全序。例如两个线程都执行"relaxed store；seq_cst 栅栏；relaxed load"，SB 测试的 `0, 0` 结果同样被禁止（由 ¶4.4 推出）。

¶5 注 2：这一定义保证 S 与任何原子对象的修改顺序一致；也保证对 M 的 seq_cst load A 读到的值，要么来自 S 中先于 A 的最后一次修改，要么来自某个**非** seq_cst 的修改，该修改不 happens before 任何在 S 中先于 A 的 M 的修改。

¶6 注 3：

!!! std
    We do not require that S be consistent with "happens before". This allows more efficient implementation of `memory_order::acquire` and `memory_order::release` on some machine architectures. It can produce surprising results when these are mixed with `memory_order::seq_cst` accesses.

    我们不要求 S 与 happens before 一致。这使某些架构上 acquire/release 可以实现得更高效；但与 seq_cst 访问混用时可能产生出人意料的结果。

¶4 的"首先"一句用的是 **strongly** happens before，而不是 happens before——这就是 ¶6 所说的放松。在 POWER 上，seq_cst 与 acquire/release 混用时，常用的指令映射无法保证经过 acquire/release 同步边的 happens before 被 S 尊重；C++11 原来的定义要求了这一点，结果是标准与所有主流实现不符。C++20 承认现实，改为只要求与 strongly happens before 一致（详见 [[intro.multithread]] 中 strongly happens before 的讨论）。

¶7 注 4：`seq_cst` 只对"无数据竞争、且**只**使用 `seq_cst` 原子操作"的程序保证顺序一致性。使用任何较弱的内存序都会使这一保证失效，除非极其小心。很多情况下，seq_cst 原子操作相对于同一线程执行的**其他**原子操作是可以重排的。

最后一句常被忽视：`x.store(1); r = y.load(acquire);`——store 是 seq_cst，load 不是，硬件和编译器都可以让 load 先于 store 生效。只有两边都是 seq_cst（或中间夹一个 seq_cst 栅栏）才不行。

### 实测：Apple Silicon 上的 SB

```cpp run title="sb-litmus.cpp" ok
#include <atomic>
#include <cstdio>
#include <thread>

#ifndef ST
#define ST std::memory_order::release
#define LD std::memory_order::acquire
#endif

std::atomic<int> x, y, go{0};
int r1, r2;

int main() {
  int both_zero = 0;
  constexpr int N = 200000;
  for (int i = 0; i < N; ++i) {
    x.store(0); y.store(0); go.store(0);
    std::thread a([] { while (!go.load(std::memory_order::acquire)) {} x.store(1, ST); r1 = y.load(LD); });
    std::thread b([] { while (!go.load(std::memory_order::acquire)) {} y.store(1, ST); r2 = x.load(LD); });
    go.store(1, std::memory_order::release);
    a.join(); b.join();
    both_zero += (r1 == 0 && r2 == 0);
  }
  std::printf("r1 == r2 == 0: %d / %d\n", both_zero, N);
}
```

在一台 Apple Silicon Mac 上用 `clang++ -O2` 编译：

| 内存序 | `r1 == r2 == 0` 出现次数（20 万次） |
|---|---|
| store `release`，load `acquire` | 6892 |
| 全部 `seq_cst`（`-DST=std::memory_order::seq_cst -DLD=std::memory_order::seq_cst`） | 0 |

原因看汇编：release store 与 seq_cst store 都编译为 `stlr`；但 acquire load 编译为 `ldapr`（RCpc，允许越过前面的 `stlr` 提前执行），seq_cst load 编译为 `ldar`（RCsc，不允许）。标准的差别在硬件上就体现为这一条指令的差别。注意次数取决于机器与负载，这里只说明"会出现"与"不会出现"。

## out-of-thin-air（¶8–¶10）

¶8 实现**应当**保证不计算出循环依赖于自身计算的"无中生有"（out-of-thin-air）值。

注 5 的例子（x、y 初始为 0）：

```cpp
// 线程 1
r1 = y.load(memory_order::relaxed);
x.store(r1, memory_order::relaxed);
// 线程 2
r2 = x.load(memory_order::relaxed);
y.store(r2, memory_order::relaxed);
```

`r1 == r2 == 42` 不应出现：y 被写成 42 的前提是 x 被写成 42，而这又循环依赖于 y 被写成 42。注 5 坦承：没有这条限制，这样的执行是"可能的"——也就是说，¶1–¶7 的形式规则本身**并不排除**它。

¶9 注 6：同理，下面的例子也不应出现 `r1 == r2 == 42`：

```cpp
// 线程 1
r1 = x.load(memory_order::relaxed);
if (r1 == 42) y.store(42, memory_order::relaxed);
// 线程 2
r2 = y.load(memory_order::relaxed);
if (r2 == 42) x.store(42, memory_order::relaxed);
```

注 7 给出了两类"不会产生 OOTA 值"的实现：

- 把非 volatile 原子访问当作 volatile 一样直接翻译成机器指令的实现；
- 只做**单线程范围**分析，只做"省略、合并对同一对象的非 volatile 原子访问"以及"（as-if 允许时）重排对不同对象的非 volatile 原子访问"这些优化，其余都当作 volatile 处理的实现。

对其他实现，OOTA 的可能性依然存在。¶10 注 8：与抽象机不同，物理机器有指令执行和信息传输延迟；物理机器会小心管理推测执行，避免在硬件层面产生 OOTA 值。

!!! lawyer "为什么只是“应当”"
    ¶8 是 *should*，没有规范效力。精确地刻画"不允许 OOTA、但允许编译器正常优化"至今仍是开放问题：把"依赖"形式化会被编译器的常量传播、死代码消除等优化破坏（这也是 `consume` 失败的原因）。所以标准选择用一条建议 + 两个"安全实现"的描述来表达意图。实际上主流编译器与硬件都不会产生 OOTA 值。

## RMW 读最新值（¶11）

¶11 原子读-改-写操作**总是**读取修改顺序中**紧邻**其自身写入之前的那个副作用的值。

这条规则是 RMW 与"load 然后 store"的本质区别，与内存序无关——即使是 `relaxed` 的 `fetch_add` 也满足它。所以多个线程对同一个计数器做 relaxed `fetch_add`，结果永远不会丢失增量：

```cpp run title="relaxed-counter.cpp" ok
#include <atomic>
#include <cassert>
#include <thread>
#include <vector>

std::atomic<long> hits{0};

int main() {
  {
    std::vector<std::jthread> ts;
    for (int t = 0; t < 8; ++t)
      ts.emplace_back([] { for (int i = 0; i < 100000; ++i) hits.fetch_add(1, std::memory_order::relaxed); });
  }   // 所有 jthread 在此 join：线程完成 synchronizes with join 返回
  assert(hits.load(std::memory_order::relaxed) == 800000);   // 一次也不会丢
}
```

relaxed 在这里足够，因为我们只关心计数本身，不用它来"发布"其他数据；最后的读取通过 join 获得可见性。

## 原子 modify-write 操作（¶12） {{c++26}}

¶12 **原子 modify-write 操作**（[[g:atomic-modify-write-operation]]）是一种同步要求更弱的原子读-改-写操作，弱在哪里由 [[atomics.fences]] 规定。注 9：意图是用**不受硬件 acquire 栅栏排序**的机制实现它们；除此之外不暗示其他语义或硬件性质（例如不暗示它一定是"远端原子操作"）。

具体的原子 modify-write 操作是整数、浮点、指针原子类型的 `store_add`、`store_sub`、`store_and`、`store_or`、`store_xor`、`store_max`、`store_min` 等成员（[[atomics.types.int]] 等）。它们与对应的 `fetch_*` 的区别：

- 不返回旧值（返回 `void`）；
- 前置条件只允许 `relaxed`、`release`、`seq_cst`——没有 acquire 一半，因为它们的"读"不供程序观察；
- 在 [[atomics.fences#2]] 中不能充当"读端"Y：release 栅栏 → modify-write → acquire 栅栏 这条路径**不**建立同步；
- 不算 [[intro.progress]] 意义上的执行步骤；
- 浮点版本的算术规则可以与普通运算不同，允许树形归约（[[atomics.types.float]] ¶14）。

典型用途是 GPU 或多核上的直方图、归约：大量线程往同一组计数器里加数，谁也不需要读回旧值。硬件可以把这些操作发送到内存控制器或缓存附近执行，而不必把缓存行拉到本核。

!!! impl "libc++ 尚未实现"
    Clang 23 自带的 libc++ 中 `atomic<int>` 没有 `store_add` 等成员。

## 最后的建议性条款（¶13）

¶13 *推荐做法*：实现应当使原子 store 在**合理的时间内**对原子 load 可见，原子 load 也应在合理时间内观察到原子 store。这与 [[intro.progress]] ¶17（"最后一个值应在有限时间内对所有线程可见"）相呼应。没有这条，一个 `while (!flag.load(relaxed)) {}` 的自旋循环理论上可以永远读到旧值。

## 实现视角

!!! impl "AArch64（Apple Silicon，Clang 23 -O2）上的实际映射"
    | 操作 | 指令 |
    |---|---|
    | load `relaxed` / `acquire` / `seq_cst` | `ldr` / `ldapr` / `ldar` |
    | store `relaxed` / `release` / `seq_cst` | `str` / `stlr` / `stlr` |
    | `fetch_add` `relaxed` / `acq_rel` / `seq_cst` | `ldadd` / `ldaddal` / `ldaddal` |
    | `atomic_thread_fence` `acquire` / `release` / `seq_cst` | `dmb ishld` / `dmb ish` / `dmb ish` |
    | `atomic_signal_fence(seq_cst)` | 无指令（仅编译器屏障） |

    `acquire` 与 `seq_cst` 的 load 在这里唯一的区别就是 `ldapr` 与 `ldar`：后者保证不会越过同一线程中更早的 `stlr`，这正是 ¶4.1 需要的"store→load"顺序。

## 历史与演进

!!! history "memory_order 的演变"
    - **C++11**：六个值 `relaxed`、`consume`、`acquire`、`release`、`acq_rel`、`seq_cst`；`seq_cst` 要求 S 与 happens before 一致。
    - **C++17**：`consume` 被注明"暂时不鼓励使用"——所有编译器都把它当作 `acquire` 实现。
    - **C++20**：`memory_order` 改为作用域枚举；[[P0668R5]] 改写 ¶4，引入 coherence-ordered before，要求 S 只与 strongly happens before 一致，并给出栅栏的四条约束。
    - **C++26**：`consume` 进入附录 D，等价于 `acquire`；核心语言中的依赖序定义被删除。新增原子 modify-write 操作（¶12）。

## 陷阱

!!! pitfall "acquire/release 不提供 store→load 顺序"
    "我先 release 写了 x，再 acquire 读 y，所以写一定在读之前生效"——错。release 只约束它**之前**的访问，acquire 只约束它**之后**的访问，`store(release); load(acquire)` 中间正好是一个缺口。需要这种顺序（Dekker、Peterson 算法、SB 模式）时，两个操作都用 `seq_cst`，或在中间放一个 `seq_cst` 栅栏。上面的实测就是这个缺口在真实硬件上的样子。

!!! pitfall "seq_cst 不能修补数据竞争"
    `seq_cst` 只对**原子**操作排序。普通变量上的数据竞争依然是 UB，¶7 的顺序一致性保证明确要求"无数据竞争"。

!!! pitfall "compare_exchange 的 failure 内存序"
    只给一个内存序参数时，failure 序由它推导：`acq_rel` 变为 `acquire`，`release` 变为 `relaxed`，其余不变（[[atomics.types.operations]] ¶23）。所以 `cas(e, d, release)` 失败时**不是** acquire——失败后若要依赖读到的值去访问别的数据，需要显式给出 failure 序。

## 思考题

!!! question "1. 一个 release store 与一个读到它的 relaxed load，再加上 load 之后的 acquire 栅栏，是否同步？"

<details markdown="1">
<summary>答案</summary>

是。这不是 ¶2 的情形（B 不是 acquire 操作），而是 [[atomics.fences#4]]：release 操作 A 与 acquire 栅栏 B 同步，若存在对同一对象的原子操作 X，X sequenced before B，且 X 读到了 A（或 A 为首的 release sequence）写入的值。
</details>

!!! question "2. 两个线程各自对同一个 `atomic<int>` 做 `seq_cst` 的 `fetch_add(1)`，第三个线程 relaxed 地读取它。第三个线程能否先读到 2、再读到 1？"

<details markdown="1">
<summary>答案</summary>

不能。这与 seq_cst 无关：第三个线程的两次读，前一次 sequenced before 后一次，因此 happens before；按读-读一致性（[[intro.races]] ¶12），后一次读到的值必须等于前一次读到的值或在修改顺序中更晚。修改顺序是 0 → 1 → 2，所以读到 2 之后不能再读到 1。单个对象上的一致性对 relaxed 操作同样成立（¶1 注 1）。
</details>

!!! question "3. 为什么 ¶4 第一句用 strongly happens before，而 ¶4.2–¶4.4 用的是 happens before？"

<details markdown="1">
<summary>答案</summary>

第一句约束的是两个 seq_cst 操作之间由"线程间关系"推出的顺序；若用 happens before，就要求经由 acquire/release 同步边的路径也被 S 尊重，这在 POWER 等平台的常用映射下做不到（¶6）。¶4.2–¶4.4 里的 happens before 连接的是普通原子操作与 seq_cst **栅栏**，栅栏在这些平台上编译为完整的屏障指令（如 `sync`），足以保证这些约束，所以可以用较弱、较宽的 happens before。
</details>

## 小结

| 内存序 | 建立的关系 | 用途 |
|---|---|---|
| `relaxed` | 只有单对象上的原子性与一致性 | 计数器、统计、不用于发布数据的标志 |
| `release` / `acquire` | 读到值时 synchronizes with（¶2） | 发布/订阅：生产者-消费者、锁的实现 |
| `acq_rel` | RMW 同时具有两者 | 引用计数递减到零、交换所有权 |
| `seq_cst` | 以上全部 + 参与单一全序 S（¶4） | 需要 store→load 顺序的算法；默认值 |
| `consume` | C++26 起等同 `acquire`，已弃用 | — |
