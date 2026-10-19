---
title: 内存序与一致性
summary: memory_order 各个值的含义：release/acquire 怎样建立同步，seq_cst 操作和栅栏所在的单一全序 S，为什么 S 不必与 happens before 一致，out-of-thin-air 值，读-改-写总是读最新值，以及 C++26 的原子 modify-write 操作；附 Apple Silicon 上的实测。
status: done
covers: atomics.order
papers: P0668R5, P3475R2, P3111R8
related: intro.races, intro.multithread, atomics.fences, atomics.types.operations, depr.atomics, intro.progress
tags: 标准库, 原子操作, 内存模型, memory_order
updated: 2026-10-19
---

!!! tldr
    - release 写与读到这个值的 acquire 读同步，写之前的普通写对读之后的代码可见。没读到就没有同步。
    - acquire/release 不阻止先写后读的重排；Dekker 式的 store→load 顺序需要两边都用 `seq_cst`，或在中间放 `seq_cst` 栅栏。
    - 所有 `seq_cst` 操作和栅栏处在一个单一全序 S 中，但 S 只需与 strongly happens before 一致，和 acquire/release 混用时可能出现意外结果。
    - `relaxed` 不提供跨变量的顺序，但仍保证原子性和单个对象上的一致性；读-改-写操作总是读修改顺序中的最新值，所以 relaxed 计数器不会丢失增量。
    - 指定了不允许的内存序（例如 `store` 用 `acquire`）违反前置条件，是 UB，不是编译错误。

[[intro.races]] 定义了 happens before、修改顺序和一致性规则，但哪些原子操作建立 synchronizes with（同步）关系，由这一节规定。读之前最好先看 [[intro.multithread]]，那里分析了消息传递（MP）、store buffering（SB）和 IRIW 三个经典的石蕊测试（litmus test）。

## 从一个例子开始：消息传递

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

① 按顺序先于 ②，② 与 ③ 同步，③ 按顺序先于 ④，所以 ① happens before ④，④ 一定读到 42。② 与 ③ 之间的同步来自下面的 ¶2。

把 ② 和 ③ 都改成 `relaxed`，就没有了同步，① 和 ④ 之间没有 happens before，构成数据竞争：

```cpp run title="mp-relaxed.cpp" ub
#include <atomic>
#include <thread>
int data = 0;
std::atomic<bool> ready{false};
int main() {
  int r = 0;
  std::thread t1([] {
    data = 42;
    ready.store(true, std::memory_order::relaxed);
  });
  std::thread t2([&r] {
    while (!ready.load(std::memory_order::relaxed)) {}
    r = data;              // UB：与 data = 42 构成数据竞争
  });
  t1.join(); t2.join();
  return r == 42 ? 0 : 1;
}
```

本机用 `-fsanitize=thread` 编译运行，ThreadSanitizer 报告 `data race`。

## 各个值的含义（¶1）

```cpp
namespace std {
  enum class memory_order : unspecified {
    relaxed = 0, acquire = 2, release = 3, acq_rel = 4, seq_cst = 5
  };
}
```

¶1 `memory_order` 规定非原子内存的同步顺序，按 [[intro.multithread]] 中的定义：

- ¶1.1 `relaxed`：不对内存排序。
- ¶1.2 `release`、`acq_rel`、`seq_cst`：store 操作在受影响的内存位置上执行一次 **release 操作**。
- ¶1.3 `acquire`、`acq_rel`、`seq_cst`：load 操作在受影响的内存位置上执行一次 **acquire 操作**。

读-改-写（read-modify-write，RMW）操作，如 `fetch_add`、`exchange`、`compare_exchange`，既是 load 又是 store，两条规则都适用：

| 内存序 | load | store | RMW |
|---|---|---|---|
| `relaxed` | 无排序 | 无排序 | 无排序 |
| `acquire` | acquire | 不允许 | 读的一半是 acquire |
| `release` | 不允许 | release | 写的一半是 release |
| `acq_rel` | 不允许 | 不允许 | acquire 加 release |
| `seq_cst` | acquire，并进入 S | release，并进入 S | 两者都有，并进入 S |

不允许的组合来自各个操作的前置条件，例如 [[atomics.types.operations#7]] 规定 `store` 的 `order` 只能是 `relaxed`、`release` 或 `seq_cst`。违反前置条件是 UB，不是编译错误：

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

libc++ 用 `diagnose_if` 在内存序是常量时给出警告，本机 Clang 23 对两处都报告 `warning: memory order argument to atomic operation is invalid [-Wuser-defined-warnings]`。内存序来自运行期变量时就没有警告了。

数值 1 原本属于 `consume`。C++26 的 [[P3475R2]] 把 `memory_order::consume` 移到了附录 D 的 [[depr.atomics]]，它在允许 `acquire` 的地方都可以用，含义与 `acquire` 相同 {{c++26}}。核心语言中与它配套的依赖序定义（carries a dependency、dependency-ordered before）也随之删除。

¶1 注 1：`relaxed` 原子操作在内存排序上是放松的，但实现仍必须保证，对某个原子对象的每次原子访问相对于对该对象的所有其他原子访问都不可分割。relaxed 放弃的是与其他内存位置之间的顺序，不放弃原子性，也不放弃单个对象上的一致性（[[intro.races#11]]–[[intro.races#14]] 的四条一致性规则）。

## release/acquire 同步（¶2）

!!! std
    An atomic operation A that performs a release operation on an atomic object M synchronizes with an atomic operation B that performs an acquire operation on M and takes its value from any side effect in the release sequence headed by A.

¶2 在原子对象 M 上执行 release 操作的原子操作 A，与在 M 上执行 acquire 操作、并且从以 A 为首的 release sequence 中某个副作用取值的原子操作 B 同步。release sequence 由 A 和其后修改顺序中对 M 的 RMW 操作组成（[[intro.races]]）。三个条件缺一不可：

1. 同一个原子对象 M；
2. A 是 release，B 是 acquire；
3. B 实际读到了 A 写的值，或者 A 之后的某个 RMW 写的值。

第 3 条容易被忽略：B 读到的是 A 之前的旧值，就没有同步，什么也推不出来。所以 acquire 读几乎总是出现在检查值的循环或分支里，就像上面的 ③。

## coherence-ordered before（¶3）

¶3 定义了同一原子对象 M 上两个原子操作之间的 **coherence-ordered before** 关系（[[g:coherence-ordered-before]]）。A coherence-ordered before B，如果：

- ¶3.1 A 是修改，B 读到了 A 存储的值；或
- ¶3.2 A 在 M 的修改顺序中先于 B；或
- ¶3.3 A 和 B 不是同一个 RMW 操作，A 读到了某个修改 X 存储的值，X 在修改顺序中先于 B；或
- ¶3.4 存在修改 X，A coherence-ordered before X，X coherence-ordered before B。

直观地说，M 的修改顺序是一条线。每个写在线上有自己的位置，每个读落在它所读的那个写之后、下一个写之前。coherence-ordered before 就是这条线上的先后。¶3.3 排除同一个 RMW，是因为 RMW 读到的 X 当然在它自己写入的值之前，不需要这条关系。

## 单一全序 S（¶4–¶7）

### 定义

¶4 是 C++20 经 [[P0668R5]] 修订后的 `seq_cst` 定义。存在一个包含所有 `memory_order::seq_cst` 操作（包括栅栏）的单一全序 S，满足下列约束。

首先，如果 A、B 都是 seq_cst 操作，并且 A strongly happens before B，那么 A 在 S 中先于 B。

其次，对 M 上每一对满足 A coherence-ordered before B 的原子操作：

- ¶4.1 A、B 都是 seq_cst 操作时，A 在 S 中先于 B；
- ¶4.2 A 是 seq_cst 操作、B happens before 某个 seq_cst 栅栏 Y 时，A 在 S 中先于 Y；
- ¶4.3 某个 seq_cst 栅栏 X happens before A、B 是 seq_cst 操作时，X 在 S 中先于 B；
- ¶4.4 seq_cst 栅栏 X happens before A、B happens before seq_cst 栅栏 Y 时，X 在 S 中先于 Y。

¶4.2–¶4.4 让 seq_cst 栅栏代替它前后的非 seq_cst 原子操作参与全序。例如两个线程都执行 relaxed 写、seq_cst 栅栏、relaxed 读，SB 测试中两个读都得到 0 的结果仍然被 ¶4.4 禁止：假设两个读都读到初始值，就能分别推出两个栅栏在 S 中互相先于对方，矛盾。

¶5 注 2：这个定义保证 S 与每个原子对象的修改顺序一致。它还保证，对 M 的 seq_cst 读 A，读到的要么是 S 中 A 之前对 M 的最后一次修改，要么是某个不 happens before S 中 A 之前任何修改的非 seq_cst 修改。

### S 不必与 happens before 一致（¶6）

!!! std
    We do not require that S be consistent with "happens before". This allows more efficient implementation of `memory_order::acquire` and `memory_order::release` on some machine architectures.

¶6 注 3：标准不要求 S 与 happens before 一致，这让某些架构上的 acquire/release 可以实现得更高效；代价是它们与 seq_cst 访问混用时，可能出现意外的结果。

¶4 的第一句用的是 strongly happens before（[[intro.races]]），而不是 happens before，这就是注 3 所说的放松。在 POWER 等架构上，常用的指令映射无法保证经过 acquire/release 同步得到的 happens before 被 S 尊重。C++11 原来的定义要求了这一点，结果标准与主流实现都不符。C++20 改为只要求与 strongly happens before 一致。

### seq_cst 只在全部使用时才是顺序一致的（¶7）

¶7 注 4：`seq_cst` 只对没有数据竞争、而且只使用 `seq_cst` 原子操作的程序保证顺序一致性。使用任何较弱的内存序都会让这个保证失效。很多情况下，seq_cst 操作相对于同一线程的其他原子操作可以重排。

例如 `x.store(1); r = y.load(memory_order::acquire);`：store 是 seq_cst，load 不是，编译器和硬件都可以让 load 先于 store 生效。只有两边都是 seq_cst，或者中间夹一个 seq_cst 栅栏，才能保证先写后读的顺序。

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

在 Apple Silicon Mac 上用 `clang++ -O2` 编译。store 用 `release`、load 用 `acquire` 时，`r1 == r2 == 0` 在 20 万次中出现了几百到几千次，次数随机器负载变化；加上 `-DST=std::memory_order::seq_cst -DLD=std::memory_order::seq_cst` 后，一次也没有出现。

原因在汇编里：release 写和 seq_cst 写都编译成 `stlr`；acquire 读编译成 `ldapr`，它可以越过前面的 `stlr` 提前执行，seq_cst 读编译成 `ldar`，它不能。标准中两种内存序的差别，在硬件上就是这一条指令的差别。

## out-of-thin-air 值（¶8–¶10）

¶8 实现应当保证不会计算出循环依赖于自身计算的无中生有（out-of-thin-air，OOTA）的值。注 5 的例子，`x`、`y` 初始为 0：

```cpp
// 线程 1
r1 = y.load(memory_order::relaxed);
x.store(r1, memory_order::relaxed);
// 线程 2
r2 = x.load(memory_order::relaxed);
y.store(r2, memory_order::relaxed);
```

`r1 == r2 == 42` 不应出现：`y` 被写成 42 的前提是 `x` 被写成 42，而这又依赖于 `y` 被写成 42。注 5 同时承认，没有这条限制，这样的执行是可能的，也就是说 ¶1–¶7 的形式规则本身并不排除它。¶9 注 6 补充，把写改成 `if (r1 == 42) y.store(42, ...)` 这种条件写入，同样不应出现 `r1 == r2 == 42`。

注 7 描述了两类不会产生 OOTA 值的实现：一类把非 volatile 原子访问当作 volatile 一样直接翻译成机器指令；另一类只做一次分析一个线程的优化，只省略、合并对同一对象的原子访问，或者在 as-if 规则允许时重排对不同对象的原子访问，其余都当作 volatile 处理。¶10 注 8 指出，物理机器会小心管理推测执行，避免在硬件层面产生 OOTA 值。

!!! lawyer "为什么只是“应当”"
    ¶8 用的是 should，只是建议。精确地刻画不允许 OOTA、同时允许编译器正常优化，至今仍是未解决的问题：把依赖关系形式化，会与常量传播、死代码消除等优化冲突，`consume` 的失败也是这个原因。所以标准选择了一条建议加两类安全实现的描述。主流编译器和硬件实际上都不会产生 OOTA 值。

## 读-改-写总是读最新值（¶11）

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
  }   // jthread 在这里 join：线程完成与 join 返回同步
  assert(hits.load(std::memory_order::relaxed) == 800000);   // 一次也不会丢
}
```

¶11 原子读-改-写操作总是读取修改顺序中紧挨在它自己的写之前的那个副作用的值。

这是 RMW 与先 load 再 store 的本质区别，与内存序无关，relaxed 的 `fetch_add` 也满足它。所以多个线程对同一个计数器做 relaxed `fetch_add`，不会丢失增量。这里 relaxed 就够了，因为计数器不用来发布其他数据，最后的读取通过 join 获得可见性。

## 原子 modify-write 操作（¶12） {{c++26}}

¶12 **原子 modify-write 操作**（[[g:atomic-modify-write-operation]]）是一类同步要求更弱的原子读-改-写操作，弱在哪里由 [[atomics.fences]] 规定。注 9 说明，意图是用不受硬件 acquire 栅栏排序的机制来实现它们，此外不暗示其他语义或硬件性质。

它们是 [[P3111R8]] 加入的 `store_add`、`store_sub`、`store_and`、`store_or`、`store_xor`、`store_max`、`store_min` 等成员（[[atomics.types.int]] 等）。与对应的 `fetch_*` 相比：

- 返回 `void`，不返回旧值；
- 前置条件只允许 `relaxed`、`release`、`seq_cst`，没有 acquire 的一半，因为程序看不到它们读到的值；
- 在 [[atomics.fences#2]] 中不能充当读的一方，release 栅栏、modify-write、acquire 栅栏这条路径不建立同步；
- 不算 [[intro.progress#3]] 意义上的执行步骤；
- 浮点版本的算术规则可以与普通运算不同，[[atomics.types.float#14]] 的注允许树形归约。

典型用途是直方图和归约：大量线程往同一组计数器里累加，谁也不需要读回旧值。硬件可以把这类操作交给内存控制器或缓存附近执行，不必把缓存行拉到本核。

!!! impl "libc++ 尚未实现"
    Clang 23 自带的 libc++ 中 `atomic<int>` 还没有 `store_add` 等成员。

## 及时可见（¶13）

¶13 *推荐做法*：实现应当让原子写在合理的时间内对原子读可见。这与 [[intro.progress#17]] 的建议一致，那里要求修改顺序中最后的值在有限时间内对所有线程可见。没有这类保证，`while (!flag.load(relaxed)) {}` 这样的自旋循环理论上可以永远读到旧值。

## 实现视角

!!! impl "AArch64（Apple Silicon，Clang 23 -O2）上的映射"
    | 操作 | 指令 |
    |---|---|
    | load `relaxed` / `acquire` / `seq_cst` | `ldr` / `ldapr` / `ldar` |
    | store `relaxed` / `release` / `seq_cst` | `str` / `stlr` / `stlr` |
    | `fetch_add` `relaxed` / `acq_rel` / `seq_cst` | `ldadd` / `ldaddal` / `ldaddal` |
    | `atomic_thread_fence` `acquire` / `release` / `seq_cst` | `dmb ishld` / `dmb ish` / `dmb ish` |
    | `atomic_signal_fence(seq_cst)` | 无指令，只是编译器屏障 |

    acquire 读与 seq_cst 读唯一的区别是 `ldapr` 与 `ldar`：后者不会越过同一线程中更早的 `stlr`，这正是 ¶4.1 需要的 store→load 顺序。

## 历史与演进

!!! history "memory_order 的演变"
    - C++11 有六个值：`relaxed`、`consume`、`acquire`、`release`、`acq_rel`、`seq_cst`，并要求 S 与 happens before 一致。
    - C++17 的 [[P0371R1]] 加了一条注，暂时不鼓励使用 `consume`，因为编译器都把它当作 `acquire` 实现。
    - C++20 把 `memory_order` 改为作用域枚举；[[P0668R5]] 改写了 ¶4，引入 coherence-ordered before，只要求 S 与 strongly happens before 一致，并给出涉及栅栏的四条约束。
    - C++26 把 `consume` 移到附录 D，等同于 `acquire`（[[P3475R2]]），并新增原子 modify-write 操作（[[P3111R8]]）。

## 常见误解

!!! pitfall "先 release 写、再 acquire 读，写一定先生效"
    不对。release 只约束它之前的访问，acquire 只约束它之后的访问，`store(release); load(acquire)` 中间正好是一个缺口。需要这种顺序时（Dekker、Peterson 算法、SB 模式），两个操作都用 `seq_cst`，或者在中间放一个 `seq_cst` 栅栏。上面的实测就是这个缺口在真实硬件上的表现。

!!! pitfall "seq_cst 能修补数据竞争"
    `seq_cst` 只对原子操作排序。普通变量上的数据竞争仍然是 UB，¶7 的顺序一致性保证明确以没有数据竞争为前提。

!!! pitfall "compare_exchange 失败时也是 acquire"
    只给一个内存序参数时，失败时的内存序由它推导：`acq_rel` 变为 `acquire`，`release` 变为 `relaxed`，其余不变（[[atomics.types.operations#23]]）。所以 `cas(e, d, release)` 失败时不是 acquire。失败后要依赖读到的值去访问其他数据，需要显式给出失败时的内存序。

## 思考题

!!! question "1. 一个 release 写，一个读到它的 relaxed 读，读之后再加一个 acquire 栅栏，能否建立同步？"

<details markdown="1">
<summary>答案</summary>

能。这不是 ¶2 的情形，因为读不是 acquire 操作；适用的是 [[atomics.fences#4]]：release 操作 A 与 acquire 栅栏 B 同步，如果存在对同一对象的原子操作 X，X 按顺序先于 B，并且读到了 A（或以 A 为首的 release sequence）写入的值。
</details>

!!! question "2. 两个线程各对同一个 `atomic<int>` 做一次 `seq_cst` 的 `fetch_add(1)`，第三个线程 relaxed 地读两次。能否先读到 2、再读到 1？"

<details markdown="1">
<summary>答案</summary>

不能，而且与 seq_cst 无关。第三个线程的两次读，前一次按顺序先于后一次，所以 happens before 后一次。按读-读一致性（[[intro.races#12]]），后一次读到的值必须等于前一次的值，或者在修改顺序中更晚。修改顺序是 0、1、2，读到 2 之后不能再读到 1。单个对象上的一致性对 relaxed 操作同样成立（¶1 注 1）。
</details>

!!! question "3. 为什么 ¶4 的第一句用 strongly happens before，而 ¶4.2–¶4.4 用 happens before？"

<details markdown="1">
<summary>答案</summary>

第一句约束两个 seq_cst 操作之间的顺序。如果用 happens before，经由 acquire/release 同步得到的路径也必须被 S 尊重，这在 POWER 等平台的常用映射下做不到（¶6）。¶4.2–¶4.4 中的 happens before 连接的是普通原子操作和 seq_cst 栅栏，栅栏在这些平台上编译为完整的屏障指令（如 POWER 的 `sync`），足以满足这些约束，所以可以保留 happens before。
</details>

## 小结

| 内存序 | 建立的关系 | 用途 |
|---|---|---|
| `relaxed` | 只有单个对象上的原子性和一致性 | 计数器、统计、不用于发布数据的标志 |
| `release` / `acquire` | 读到值时同步（¶2） | 生产者-消费者、锁的实现 |
| `acq_rel` | RMW 同时具有两者 | 引用计数减到零、交换所有权 |
| `seq_cst` | 以上全部，并参与单一全序 S（¶4） | 需要 store→load 顺序的算法；默认值 |
| `consume` | C++26 起等同 `acquire`，已弃用 | 不再使用 |
