---
title: latch 与 barrier
summary: C++20 的两种线程协调类型：一次性的 latch 与可分阶段重复使用的 barrier，它们的前置条件、同步保证、完成函数在哪个线程运行，以及 arrive 与 wait 分开调用的用法。
status: done
covers: *
papers: P1135R6
related: thread.sema, atomics.wait, atomics.order, intro.races, algorithms.parallel
tags: 标准库, 并发, latch, barrier
updated: 2026-10-19
---

!!! tldr
    - `latch` 是一次性的倒数计数器：`count_down` 减计数，`wait` 等计数归零。归零后不能重置。
    - `barrier` 按阶段重复使用：每个阶段所有参与者到齐后，运行一次完成函数，然后计数自动重置，进入下一阶段。
    - 两者都保证到达之前的写入，对等待返回之后的线程可见。barrier 的完成函数还能看到本阶段所有参与者的写入。
    - 多减计数是 UB：`count_down` 的减量不能超过剩余计数，`arrive` 也不能超过本阶段的剩余计数。
    - 完成函数必须是 `noexcept` 的，运行期间不得调用 barrier 除 `wait` 以外的成员。

## 两种协调类型 [thread.coord.general] {{c++20}}

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
      done.count_down();
    });
  start.count_down();            // 发令
  done.wait();                   // 所有 count_down 之前的写入在此后可见
  int sum = 0;
  for (int r : results) sum += r;
  std::printf("%d\n", sum);      // 0 + 1 + 4 + 9 = 14
}
```

¶1 [thread.coord] 定义 `latch` 和 `barrier` 两种协调类型，用于多个线程共同完成的并发计算。它们都解决等 N 个参与者到齐再继续的问题，区别在于能否重复使用：

| | `latch` | `barrier` |
|---|---|---|
| 使用次数 | 一次，计数归零后不能重置 | 多次，每个阶段结束后自动重置 |
| 谁减计数 | 任何线程，可以减多次、每次减任意量 | 本阶段的参与者，通常每人一次 |
| 等待者与减计数者 | 可以不同，如主线程只等不减 | 通常相同（`arrive_and_wait`） |
| 完成时的回调 | 无 | 完成函数，每个阶段恰好运行一次 |

## latch [thread.latch]

[thread.latch.general] ¶1 latch 让任意数量的线程阻塞，直到预期数量的线程通过 `count_down` 到达。预期计数在创建时设定。latch 是一次性对象，计数一旦归零就不能再用。

[thread.latch.class] ¶1 latch 维护一个内部计数器 `counter`。¶2 除析构函数外，并发调用成员函数不会引入数据竞争。¶3 `max()` 返回实现支持的最大计数，¶4 构造函数的前置条件是 `0 <= expected <= max()`。

### count_down（¶7–¶11）

```cpp
void count_down(ptrdiff_t update = 1);
```

¶8 原子地把 `counter` 减去 `update`；如果减到零，解除所有阻塞在这个 latch 上的线程。

¶7 前置条件：`update >= 0`，并且 `update <= counter`。所以多减是 UB：latch 初始化为 4，却有 5 个线程各 `count_down()` 一次，第 5 次调用就违反了前置条件。

¶9 每一次 `count_down` 都 [[g:strongly-happens-before|strongly happens before]] 所有被解除阻塞的调用的返回，不只是让计数归零的那一次。所以开头的例子里，每个工人在 `count_down` 之前写入的结果，对 `done.wait()` 返回后的主线程都可见。

### 等待（¶12–¶16）

¶13 `wait()` 在计数为零时立即返回，否则阻塞到某次 `count_down` 把计数减到零。

¶12 `try_wait()` 以非常低的概率返回 `false`，否则返回 `counter == 0`。也就是说它可以虚假地返回 `false`，但不会在计数归零之前返回 `true`。

¶16 `arrive_and_wait(update)` 等价于 `count_down(update); wait();`。

!!! impl "libc++ 的 latch"
    libc++ 的 `latch` 只有一个 `atomic<ptrdiff_t>`。`count_down` 是 `fetch_sub(update, release)`，减到零时 `notify_all()`；`wait` 以 acquire 读取计数。

    每个 `fetch_sub` 都是读改写操作，所以每一次 `count_down` 都是一个 release 序列的开头，之后的 `fetch_sub` 都在这个序列里（[[intro.races#5]]）。最终读到 0 的 acquire 读取因此与每一次 `count_down` 同步，这就是 ¶9 对每一次调用都成立的原因。

## barrier [thread.barrier]

[thread.barrier.general] ¶1 barrier 的生命周期由一系列 **barrier 阶段**（barrier phase）组成。每个阶段允许至多预期数量的线程阻塞，直到预期数量的线程到达。注 1 说明它适合由多个线程处理的重复性任务。

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
  std::barrier sync(N, [&]() noexcept {            // 完成函数：每个阶段运行一次
    std::printf("phase %d: %d %d %d\n", phase, partial[0], partial[1], partial[2]);
    ++phase;
  });
  std::latch done(N);
  std::vector<std::jthread> ts;
  for (int id = 0; id < N; ++id)
    ts.emplace_back([&, id] {
      for (int round = 0; round < 2; ++round) {
        partial[id] = (round + 1) * 10 + id;       // 到达前写入，完成函数可见（¶14）
        sync.arrive_and_wait();                    // 返回后可见完成函数的写入（¶3）
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

### 阶段（[thread.barrier.class] ¶1–¶4）

¶1 每个阶段由三步组成：

- ¶1.1 每次调用 `arrive` 或 `arrive_and_drop` 都使预期计数减少；
- ¶1.2 预期计数归零后，某个线程在它的 `arrive`、`arrive_and_drop` 或 `wait` 调用中执行**完成步骤**，恰好一次；如果没有线程调用 `wait`，完成步骤是否执行由实现定义 {{impl}}；
- ¶1.3 完成步骤结束后，预期计数重置为构造时的 `expected`（可能已被 `arrive_and_drop` 调小），下一阶段开始。

¶2 每个阶段有一个**阶段同步点**。本阶段到达的线程可以调用 `wait` 阻塞在这个点上，直到完成步骤执行完毕。

¶3 完成步骤先调用完成函数（等价于 `completion()`），再解除所有阻塞在阶段同步点上的线程。完成步骤的结束 strongly happens before 被它解除阻塞的所有调用的返回。

¶3 还规定：如果 `CompletionFunction` 不是默认类型，在完成步骤进行期间调用 barrier 除 `wait` 以外的任何成员函数，行为未定义 {{ub}}。¶4 除析构函数外，并发调用成员函数不会引入数据竞争，`arrive` 和 `arrive_and_drop` 原子地执行。

结合第 14 段的同步规则（见下文），对完成函数可以得出这几点：

- 它在某个参与者线程上，在那个线程的 `arrive`、`arrive_and_drop` 或 `wait` 调用里运行。通常是最后一个到达的线程，但程序不能依赖这一点。
- 它能安全地读取所有参与者在 `arrive` 之前写入的数据，适合做汇总。
- 参与者从 `arrive_and_wait` 返回后，能看到完成函数写入的数据，比如为下一轮准备的输入。

例子中完成函数读 `partial`、写 `phase`，参与者在下一轮写 `partial`，这些访问都被第 3 段和第 14 段排好了先后，没有数据竞争。

### 类型要求（¶5–¶7）

¶5 `CompletionFunction` 需满足 *Cpp17MoveConstructible* 和 *Cpp17Destructible*，并且 `is_nothrow_invocable_v<CompletionFunction&>` 必须为真。完成函数在别的线程的 `arrive` 调用里运行，它抛出的异常没有合理的去处，所以不允许抛出。

¶6 默认的 `CompletionFunction` 是一个未指定的类型，可以默认构造，调用它没有效果。¶7 `arrival_token` 是一个未指定的可移动类型。

### 构造与到达（¶8–¶29）

¶9–¶10 构造函数 `barrier(expected, f)` 的前置条件是 `0 <= expected <= max()`。它把每个阶段的初始预期计数设为 `expected`，开始第一个阶段。注 1 指出，`expected` 为 0 的 barrier 只能被销毁。

¶12–¶13 `arrive(update)` 构造一个关联到当前阶段同步点的 `arrival_token`，然后把预期计数减去 `update`。前置条件是 `update > 0`，并且不超过当前阶段剩余的预期计数。¶14 对 `arrive` 的调用 strongly happens before 当前阶段完成步骤的开始。

¶19–¶20 `wait(std::move(token))` 阻塞在 token 关联的阶段同步点上，直到那个阶段的完成步骤运行完毕。¶19 的前置条件要求 token 属于当前阶段或紧邻的上一阶段。注 3 指出，token 属于已经结束的阶段时立即返回。

¶23 `arrive_and_wait()` 等价于 `wait(arrive())`。

`arrive` 与 `wait` 分开，参与者可以先宣布自己到了，做些不依赖别人结果的事，再等待：

```cpp
auto tok = bar.arrive();     // 宣布本阶段我的部分已完成
do_unrelated_work();         // 不依赖其他参与者的工作
bar.wait(std::move(tok));    // 现在才需要其他人的结果
```

token 只可能属于当前阶段或上一阶段。阶段可以在 token 被用掉之前前进一次，但不可能前进两次：这个参与者还没有在下一阶段到达，下一阶段就不能结束。

¶24–¶25 `arrive_and_drop()` 先把之后所有阶段的初始预期计数减一，再把当前阶段的预期计数减一，相当于最后一次到达、以后不再参与。前置条件是当前阶段的预期计数大于零。¶26 同步规则与 `arrive` 相同。

!!! impl "libc++ 的 barrier 与 ThreadSanitizer"
    libc++ 的 `barrier` 是树形 barrier：到达的线程在一棵按缓存行展开的树上逐层汇合，以减少对同一缓存行的争用。树形算法的主体在 libc++ 的动态库里。赢得最后一层的线程在自己的 `arrive` 调用中运行完成函数，然后以 release 写入新的阶段号并 `notify_all()`，等待者以 acquire 读取阶段号。

    用 `-fsanitize=thread` 运行上面的 barrier 例子，ThreadSanitizer 可能报告完成函数读取 `partial` 与参与者的写入构成数据竞争。按 ¶14 这是误报：参与者写入与完成函数之间的同步发生在没有经过 TSan 插桩的动态库内部，TSan 看不到。`latch` 的实现全部在头文件里，不会出现这种误报。

## 常见误解

!!! pitfall "latch 可以重置"
    每一轮都要等齐时，应当用 `barrier`。用 `latch` 就只能每轮新建一个，并且要保证所有线程都用完旧的之后才能销毁它。

!!! pitfall "完成函数里可以调用 barrier 的其他成员"
    对非默认的 `CompletionFunction`，完成步骤进行期间调用除 `wait` 以外的成员函数是 UB（¶3）。完成函数只应做汇总、准备下一轮这类与 barrier 本身无关的工作。

!!! pitfall "参与者多一个也没关系"
    `barrier(3)` 却有 4 个线程调用 `arrive_and_wait()`：第 4 个线程的到达要么超出当前阶段的剩余计数，违反 ¶12 的前置条件，要么被算进下一阶段，使阶段错位。提前退出的参与者应当调用 `arrive_and_drop()`。

## 小结

- `latch`：一次性计数器；`count_down` 不得多减；每次 `count_down` 都 strongly happens before 被唤醒者返回；`try_wait` 可以虚假地返回 `false`。
- `barrier`：分阶段重复使用；每个阶段的完成函数恰好运行一次，在某个参与者线程上；`arrive` strongly happens before 完成步骤开始，完成步骤结束 strongly happens before 等待者返回。
- 完成函数必须 `noexcept`，运行期间不得调用 barrier 除 `wait` 以外的成员。
