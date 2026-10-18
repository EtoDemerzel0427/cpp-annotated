---
title: latch 与 barrier
summary: C++20 的两种线程协调类型——一次性的 latch（count_down 的前置条件与"每一次 count_down 都 strongly happens before 被唤醒者返回"）、可重复使用的 barrier（阶段、完成步骤在哪个线程执行、arrival_token、arrive_and_drop、完成函数运行期间调用其他成员是 UB）；libc++ 的树形 barrier 与 ThreadSanitizer 误报
status: done
covers: *
papers: P1135R6
related: thread.sema, atomics.wait, atomics.order, intro.races, algorithms.parallel
tags: 标准库, 并发, latch, barrier
updated: 2026-10-18
---

[thread.coord.general] ¶1：本子条款描述与线程协调相关的概念，定义协调类型 `latch` 与 `barrier`。它们便于由多个线程完成的并发计算。

两者都解决"等 N 个参与者都到了再继续"的问题，区别在于能否重复使用：

| | `latch` | `barrier` |
|---|---|---|
| 使用次数 | 一次（计数到零后不能重置） | 多次（每个阶段结束后自动重置） |
| 谁能减计数 | 任何线程，任意次数（每次减任意量） | 本阶段的参与者，每人一次（`arrive(n)` 可减多） |
| 等待者与减计数者 | 可以不同（如主线程只等不减） | 通常相同（`arrive_and_wait`） |
| 完成时的回调 | 无 | 完成函数，每阶段恰好执行一次 |

本页覆盖 [thread.coord] 的全部子条款（C++20，[[P1135R6]]）。

## latch（[thread.latch]）

### 总述（[thread.latch.general]）

¶1 latch 是一种线程协调机制，允许任意数量的线程阻塞，直到预期数量的线程到达 latch（通过 `count_down`）。预期计数在创建 latch 时设定。**单个 latch 是一次性对象**：预期计数一旦达到，就不能再重用。

`<latch>` 概要（[latch.syn]）只声明 `class latch;`。

### 类 latch（[thread.latch.class]）

类定义：`static constexpr ptrdiff_t max() noexcept;`、`constexpr explicit latch(ptrdiff_t expected);`、析构函数、删除的复制操作、`count_down`、`try_wait`、`wait`、`arrive_and_wait`；仅说明用成员 `ptrdiff_t counter`。

- ¶1 latch 维护一个内部计数器，在创建时初始化。线程可以在 latch 对象上阻塞，等待 `counter` 被减到零。
- ¶2 除析构函数外，对成员函数的并发调用不引入数据竞争。
- ¶3 `max()`：实现支持的 `counter` 的最大值。
- ¶4–¶6 构造函数：*Preconditions* `expected >= 0` 且 `expected <= max()`；初始化 `counter`；不抛异常。

`count_down(ptrdiff_t update = 1)`：

- ¶7 *Preconditions*：`update >= 0`，且 **`update <= counter`**。
- ¶8 *Effects*：原子地将 `counter` 减 `update`。若 `counter` 等于零，解除所有阻塞在 `*this` 上的线程的阻塞。
- ¶9 *Synchronization*：**strongly happens before 所有被解除阻塞的调用的返回**。
- ¶10–¶11 需要时抛 `system_error`。

¶7 意味着"多减"是 UB：5 个工作线程每人 `count_down()` 一次，而 latch 只初始化为 4，第 5 次调用违反前置条件。

¶9 说的是**每一次** `count_down` 都 strongly happens before 被解除阻塞者的返回，而不只是最后一次。所以每个工作线程在 `count_down` 之前写入的结果，对 `wait` 返回后的线程都可见——这正是"等所有工作完成后汇总结果"所需要的。

- ¶12 `try_wait()`：**以非常低的概率返回 `false`**；否则返回 `counter == 0`。也就是说它可以虚假地返回 `false`（与 `try_lock` 的虚假失败同理），但永远不会在计数未归零时返回 `true`。
- ¶13–¶15 `wait()`：若 `counter` 为零立即返回；否则阻塞，直到某次 `count_down` 把它减到零。
- ¶16 `arrive_and_wait(update)`：等价于 `count_down(update); wait();`。

```cpp run title="latch-start-gate.cpp" ok
#include <cstdio>
#include <latch>
#include <thread>
#include <vector>

int main() {
  constexpr int N = 4;
  std::latch start{1};           // 起跑门：主线程一次放行所有工人
  std::latch done{N};            // 终点：等所有工人完成
  int results[N] = {};
  std::vector<std::jthread> ts;
  for (int i = 0; i < N; ++i)
    ts.emplace_back([&, i] {
      start.wait();              // 等主线程发令
      results[i] = i * i;        // 各写各的元素
      done.count_down();         // 每次 count_down 都 strongly happens before done.wait() 返回
    });
  start.count_down();            // 发令
  done.wait();
  int sum = 0;
  for (int r : results) sum += r;
  std::printf("%d\n", sum);      // 0 + 1 + 4 + 9 = 14
}
```

## barrier（[thread.barrier]）

### 总述（[thread.barrier.general]）

¶1 barrier 是一种线程协调机制，其生命周期由一系列 **barrier 阶段**（phase）组成，每个阶段允许至多预期数量的线程阻塞，直到预期数量的线程到达 barrier。注 1：barrier 适合管理由多个线程处理的重复性任务。

`<barrier>` 概要（[barrier.syn]）：`template<class CompletionFunction = see below> class barrier;`。

### 阶段（[thread.barrier.class] ¶1–¶4）

¶1 每个 barrier 阶段由以下步骤组成：

- ¶1.1 每次调用 `arrive` 或 `arrive_and_drop` 使预期计数递减；
- ¶1.2 预期计数到达零后，**恰好一次**，某个线程在它对 `arrive`、`arrive_and_drop` 或 `wait` 的调用中执行**完成步骤**——但若没有线程调用 `wait`，该步骤是否执行由实现定义 {{impl}}；
- ¶1.3 完成步骤结束时，预期计数被重置为构造函数 `expected` 实参指定的值（可能已被 `arrive_and_drop` 调整），下一阶段开始。

¶2 每个阶段定义一个**阶段同步点**。在本阶段到达 barrier 的线程可以通过调用 `wait` 阻塞在阶段同步点上，直到完成步骤执行完毕。

¶3 每个阶段结束时执行的**阶段完成步骤**：

- ¶3.1 调用完成函数，等价于 `completion()`；
- ¶3.2 解除所有阻塞在阶段同步点上的线程的阻塞。

**完成步骤的结束 strongly happens before 被它解除阻塞的所有调用的返回。** 对于 `CompletionFunction` 不是默认值的特化，**若在完成步骤进行期间调用 barrier 对象除 `wait` 以外的任何成员函数，行为未定义** {{ub}}。

¶4 除析构函数外，对成员函数的并发调用不引入数据竞争。成员函数 `arrive` 与 `arrive_and_drop` 原子地执行。

几个推论：

- **完成函数在哪个线程执行？** ¶1.2：某个参与者线程，在它的 `arrive`、`arrive_and_drop` 或 `wait` 调用里。实际上通常是最后一个到达的线程。不能假设它在某个特定线程上执行。
- **完成函数里能看到什么？** ¶14：每次 `arrive` strongly happens before 本阶段完成步骤的开始。所以完成函数可以安全地读取所有参与者在 `arrive` 之前写入的数据，并做汇总。
- **完成函数之后能看到什么？** ¶3：完成步骤的结束 strongly happens before 被唤醒者返回。所以参与者从 `arrive_and_wait` 返回后，可以看到完成函数写入的数据（比如"下一轮的输入"）。
- **完成函数里不能做什么？** 调用 `arrive` 之类的成员：UB。

### 模板形参与类型（¶5–¶7）

- ¶5 `CompletionFunction` 须满足 *Cpp17MoveConstructible* 与 *Cpp17Destructible*；`is_nothrow_invocable_v<CompletionFunction&>` 必须为 `true`——**完成函数不能抛异常**（一个在别人的 `arrive` 调用中执行的函数抛异常，没有合理的去处）。
- ¶6 默认的 `CompletionFunction` 是未指定类型，可默认构造，`completion()` 无效果。
- ¶7 `barrier::arrival_token` 是未指定类型，满足 *Cpp17MoveConstructible*、*Cpp17MoveAssignable*、*Cpp17Destructible*。

### 成员（¶8–¶29）

- ¶8 `max()`：实现支持的最大预期计数。
- ¶9–¶11 构造函数 `barrier(ptrdiff_t expected, CompletionFunction f = CompletionFunction())`：*Preconditions* `0 <= expected <= max()`；设定每个阶段的初始预期计数与第一阶段的当前预期计数；用 `std::move(f)` 初始化 `completion`；开始第一阶段。注 1：若 `expected` 为 0，该对象只能被销毁。
- ¶12–¶18 `arrival_token arrive(ptrdiff_t update = 1)`：*Preconditions* `update > 0` 且不超过当前阶段的预期计数；构造一个与当前阶段同步点关联的 `arrival_token`，然后把预期计数减 `update`；¶14 *Synchronization*：**对 `arrive` 的调用 strongly happens before 当前阶段完成步骤的开始**；注 2：这次调用可能使完成步骤开始。`arrive` 是 `[[nodiscard]]` 的。
- ¶19–¶22 `wait(arrival_token&& arrival)`：*Preconditions* `arrival` 与本 barrier 当前阶段或**紧邻的上一阶段**的同步点关联；阻塞在该同步点，直到该阶段的完成步骤执行完毕；注 3：若 `arrival` 与之前的阶段关联，立即返回。
- ¶23 `arrive_and_wait()`：等价于 `wait(arrive())`。
- ¶24–¶29 `arrive_and_drop()`：*Preconditions* 当前阶段预期计数大于零；**把所有后续阶段的初始预期计数减一**，然后把当前阶段的预期计数减一（相当于"我最后一次到达，以后不再参与"）；同步规则同 `arrive`。

`arrive` 与 `wait` 分开，允许参与者"到达后先去做别的事，晚点再等"（split-phase）：

```cpp
auto tok = bar.arrive();     // 宣布本阶段我的部分已完成
do_unrelated_work();         // 不依赖其他参与者的工作
bar.wait(std::move(tok));    // 现在才需要其他人的结果
```

¶19 只允许 token 属于"当前或上一阶段"：因为阶段可以前进一次而 token 还没被用掉，但不可能前进两次——你自己没有到达下一阶段，下一阶段就无法完成。

```cpp run title="barrier-phases.cpp" ok
#include <barrier>
#include <cstdio>
#include <latch>
#include <thread>
#include <vector>

int main() {
  constexpr int N = 3;
  int phase = 0;
  int partial[N] = {};
  std::barrier sync(N, [&]() noexcept {            // 完成步骤：每阶段恰好执行一次
    std::printf("phase %d: %d %d %d\n", phase, partial[0], partial[1], partial[2]);
    ++phase;
  });
  std::latch done(N);
  std::vector<std::jthread> ts;
  for (int id = 0; id < N; ++id)
    ts.emplace_back([&, id] {
      for (int round = 0; round < 2; ++round) {
        partial[id] = (round + 1) * 10 + id;       // 在 arrive 之前写：完成函数可见（¶14）
        sync.arrive_and_wait();                    // 完成步骤结束 strongly happens before 返回（¶3）
      }
      done.count_down();
    });
  done.wait();
  std::printf("all done after %d phases\n", phase);
}
```

输出：

```text
phase 0: 10 11 12
phase 1: 20 21 22
all done after 2 phases
```

完成函数读取 `partial`、修改 `phase`，参与者在下一轮修改 `partial`——这些访问都被 ¶3 与 ¶14 的 strongly happens before 排序，没有数据竞争。

!!! impl "libc++ 的 barrier 与 ThreadSanitizer"
    libc++ 的 `barrier`（40 字节）是一个**树形 barrier**：到达的线程先被编号，再在一棵按缓存行展平的树上逐层汇合，以减少对同一缓存行的争用。树形算法的主体（`__arrive_barrier_algorithm_base`）在 libc++ 的**动态库**中；赢得最后一层的线程在自己的 `arrive` 调用里执行完成函数，然后 `phase.store(old + 2, release)` 并 `notify_all`，等待者以 acquire 在 `phase` 上 `wait`。

    上面的例子用 `-fsanitize=thread` 运行时，TSan 报告完成函数对 `partial` 的读取与参与者的写入构成 `data race`。按 ¶14 这是**误报**：参与者写入与完成函数之间的同步发生在未经 TSan 插桩的 libc++ 动态库内部，TSan 看不到。`latch` 的实现完全在头文件中（`fetch_sub(release)` + `wait(acquire)`），TSan 对它不误报。

!!! impl "libc++ 的 latch"
    `latch` 只有一个 `atomic<ptrdiff_t>`（8 字节）。`count_down` 是 `fetch_sub(update, release)`，减到零时 `notify_all`；`wait` 以 acquire 读取。由于所有 `fetch_sub` 都是 RMW，每一次 `count_down` 都处在之后各次 RMW 所组成的 release sequence 的开头（[[intro.races]] ¶5），所以最终读到 0 的 acquire load 与**每一次** `count_down` 都同步——这就是 ¶9 对每次调用都成立的实现原理。

## 陷阱

!!! pitfall "latch 不能重置"
    循环里需要"每一轮都等齐"时，用 `barrier`；用 `latch` 就只能每轮新建一个，并且要保证所有线程都用完了旧的才能销毁它。

!!! pitfall "完成函数里调用 barrier 的其他成员"
    ¶3：对非默认 `CompletionFunction` 的特化，完成步骤进行期间调用除 `wait` 外的成员函数是 UB。完成函数只应做汇总/准备下一轮这类与 barrier 无关的工作。

!!! pitfall "参与者数量不对"
    `barrier(3)` 却有 4 个线程 `arrive_and_wait()`：第 4 个线程的 `arrive` 发生在某个阶段预期计数已为 0 之后或属于下一阶段，破坏前置条件或让阶段错位。用 `arrive_and_drop()` 处理提前退出的参与者。

## 小结

- `latch`：一次性计数器；`count_down` 不得多减；每次 `count_down` 都 strongly happens before 被唤醒者返回；`try_wait` 可以虚假返回 `false`。
- `barrier`：多阶段；每阶段完成函数恰好执行一次，在某个参与者线程上；`arrive` strongly happens before 完成步骤开始，完成步骤结束 strongly happens before 等待者返回。
- 完成函数必须 `noexcept`，执行期间不得调用 barrier 的其他成员（`wait` 除外）。
