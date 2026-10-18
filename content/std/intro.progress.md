---
title: 前进保证
summary: 实现可以假设线程终将做出可观察的动作（无副作用的死循环是 UB，C++26 起平凡无限循环除外）；无锁执行；并发/并行/弱并行三级前进保证与保证委托
status: draft
papers: P2809R3
related: intro.multithread, intro.races, stmt.iter.general, algorithms.parallel.exec, exec.get.fwd.progress, atomics.lockfree
tags: 并发, UB, 循环, 前进保证
updated: 2026-10-17
---

本节由两个看似无关的主题组成：

1. 编译器可以假设什么（第 1 段）：每个线程终将终止或做出可观察的动作。由此，没有任何副作用的无限循环是 UB，编译器因而可以删除它无法证明会终止的空循环。
2. 实现必须保证什么（第 2–17 段）：线程在什么条件下一定会往前推进。这为 `std::thread`、并行算法、`std::execution` 的调度器提供了一套分级的术语：并发（concurrent）、并行（parallel）、弱并行（weakly parallel）前进保证。

二者合起来构成一份双向的约定：程序员保证线程不会无声无息地永远空转，实现保证线程（在一定条件下）不会被饿死。

## 实现可以假设什么（¶1）

¶1 实现可以假设任何线程终将做下列之一：

- ¶1.1 终止；
- ¶1.2 调用 `std::this_thread::yield`；
- ¶1.3 调用库 I/O 函数；
- ¶1.4 通过 volatile glvalue 进行访问；
- ¶1.5 执行原子操作或同步操作（{{c++26}} 原子 modify-write 操作除外，[[atomics.order#12]]）；
- ¶1.6 {{c++26}} 继续执行一个[[g:trivial-infinite-loop|**平凡无限循环**]]（trivial infinite loop，[[stmt.iter.general#3]]）。

如果这个假设不成立，即某个线程永远运行却不做以上任何事，行为未定义 {{ub}}。

注 1 说明了意图：即使无法证明空循环会终止，也允许编译器删除、合并或重排它；同时为平凡无限循环设了例外，它们不能被删除或重排。

### 为什么要这条规则？

考虑：

```cpp run title="collatz.cpp" ok
unsigned f(unsigned n) {
  while (n != 1) n = (n % 2) ? 3 * n + 1 : n / 2;   // 没有副作用的循环
  return 1;
}
int main(int argc, char**) { return f(argc + 26) == 1 ? 0 : 1; }
```

循环体只修改局部变量，没有 I/O、volatile、原子、同步。循环是否对所有 `n` 终止？对 `n == 0` 就不终止（0 → 0 → …），对一般的 `n` 则是著名的未解决问题（Collatz 猜想；在无符号回绕的语义下情况更复杂）。但借助 ¶1，编译器无需知道答案：如果循环不终止，线程就永远不做任何可观察的事，这违反了实现可以假设的前提。于是 Clang 23 在 `-O2` 下把 `f` 编译成直接 `return 1`，整个循环被删除。

本例中 `n == 27`，循环会终止，程序行为良好；但如果传入 0，程序就有 UB，直接返回 1 也是合法的行为。

这类优化的实际价值在于：许多循环能否终止取决于编译器无法证明的不变式（如用指针遍历链表 `for (p = head; p != end; p = p->next)`）。当循环后的代码不依赖循环结果时，无论是删除循环，还是把循环后的代码提到循环前，都需要以循环终将结束为前提。

### 平凡无限循环（¶1.6，C++26）

在 C++23 及以前，`while (true) ;` 同样是 UB。这与嵌入式和系统编程的常见写法冲突：

```cpp
[[noreturn]] void halt() { while (true) ; }   // 等待看门狗复位 / 中断
```

程序员的意图是永远停在这里，编译器却可以把它删除，然后控制流落入后面的任意代码。这在 Clang 的旧版本中确实出现过：`int main() { while (1) ; }` 被优化成一个空函数体，执行时直接落入下一个函数。

C++26 通过 [[P2809R3]] 修正了这一点。[[stmt.iter.general#3]] 定义：

- 平凡空迭代语句（trivially empty iteration statement）：形如 `while (E) ;`、`while (E) { }`、`do ; while (E) ;`、`do { } while (E) ;`、`for (init E ; ) ;`、`for (init E ; ) { }`（for 语句不能有迭代表达式）。
- 其控制表达式是 `while`/`do`/`for` 的 *expression*（`for` 缺省时为 `true`）。
- 平凡无限循环：一个平凡空迭代语句，且其转换后的控制表达式作为常量表达式求值为 `true`。
- 平凡无限循环的语句被替换为对 `std::this_thread::yield` 的调用（独立实现中是否替换由实现定义）。

替换为 `yield` 之后，这个循环每次迭代都做了 ¶1.2 中的事，于是不再违反前进假设。¶1.6 又直接把继续执行平凡无限循环列为允许的情形，二者共同保证它不是 UB。

```cpp run title="trivial-loops.cpp" ok
constexpr bool forever = true;
void a() { while (forever) ; }                    // 平凡无限循环
void b() { for (;;) { } }                         // 平凡无限循环：for 无条件视为 true
void c() { do { } while (1); }                    // 平凡无限循环
bool flag;
void d() { while (flag) ; }                       // 平凡空，但条件不是常量表达式 → 不是平凡无限循环
void e() { while (true) { int x = 0; (void)x; } } // 循环体非空 → 不是平凡空迭代语句
void f() { for (unsigned i = 0; ; ++i) { } }      // 有迭代表达式 → 不是平凡空迭代语句
int main() {}
```

`d`、`e`、`f` 若永远运行，仍然是 UB。`d` 尤其值得注意。如果另一个线程会把 `flag` 设为 `false`，这本身就是数据竞争（[[intro.races#17]]）；编译器可以把 `flag` 的读取提出循环，变成 `if (flag) for(;;);`，而后者的 `for(;;)` 只是编译器内部的形式，标准层面的判定在这之前就已经是 UB 了。正确写法是 `std::atomic<bool>`（¶1.5）。

用 Clang 23 `-O2` 编译下面两个程序可以直观看到差别：

```cpp run title="loop-ub.cpp" flags="-std=c++2c -O2" ub
#include <cstdio>
int main() {
  for (unsigned i = 0; ; ++i) { }   // 不是平凡空迭代语句；永不终止且无副作用 → UB
}
void unreachable() { std::puts("hello"); }
```

```cpp run title="loop-ok.cpp" flags="-std=c++2c -O2" ok
#include <cstdio>
int main() {
  while (true) ;                    // C++26：平凡无限循环，不是 UB
}
void unreachable() { std::puts("hello"); }
```

前者的 `main` 被编译成一条陷阱指令（AArch64 上为 `brk`），编译器认定此处不可达；后者保留了一个真正的无限跳转。（运行后者需要手动终止。）

!!! note "C 语言的类似规则"
    C11 起，C 标准规定：对于控制表达式不是常量表达式的迭代语句，若其循环体不执行 I/O、volatile 访问、同步或原子操作，实现可以假设它终止。也就是说 C 从一开始就把 `while (1) ;` 排除在外。C++26 的平凡无限循环规则让 C++ 在这一点上向 C 靠拢，但范围更窄：C++ 还要求循环体为空。

### ¶1.5 中的 modify-write 例外

C++26 新增的原子 modify-write 操作（例如整数原子的 `store_add`）不计入 ¶1.5。直观地说，这类操作是发出后就不再等待结果的归约写入，不读取任何值，因而无法借此观察其他线程的进展；一个只做 `store_add` 的无限循环与只写局部变量的循环一样，不能让线程取得进展。（同样地，它们也不是下文第 3 段所说的执行步骤。）

## 无锁执行（¶2）

¶2 被定义为无锁的原子函数（`atomic_flag` 的操作，[[atomics.flag]]）或被指示为无锁的原子函数（`is_lock_free()` 为真，[[atomics.lockfree]]），其执行称为**无锁执行**（lock-free execution）。对这类执行：

- ¶2.1 若只有一个线程没有阻塞在标准库函数中，则该线程中的无锁执行必须完成（shall）。注 2：并发执行的线程可能阻止无锁执行的进展，例如在 LL/SC（load-linked/store-conditional）实现中，其他线程的写可以让 SC 一直失败。这一性质有时称为无阻碍（obstruction-free）。
- ¶2.2 当一个或多个无锁执行并发运行时，应当（should）至少有一个完成。注 3：实现很难对此给出绝对保证，恶意的干扰（比如反复抢走缓存行）可以阻止进展；但如果实现在预期运行条件下避免了这类异常，程序员可以放心忽略它们。这一性质在本文档之外通常称为无锁（lock-free）。

这里术语有错位：标准里的 lock-free execution 在 ¶2.1 中实际只强制要求 obstruction-free，而通常意义上的 lock-free 只是 ¶2.2 中的建议。

## 执行步骤与取得进展（¶3–¶5）

¶3 线程执行期间，下列事件称为**执行步骤**（execution step）：

- ¶3.1 线程终止；
- ¶3.2 通过 volatile glvalue 进行访问；
- ¶3.3 库 I/O 调用完成；
- ¶3.4 原子或同步操作完成（modify-write 操作除外）。

与 ¶1 的列表对比：¶1 列的是实现可以假设线程会做的事，¶3 列的是算作进展的事件。

¶4 阻塞（[[defns.block]]：等待某个条件满足才能继续，且等待的不是实现去执行该线程的执行步骤）的标准库函数调用，被视为在等待期间持续执行执行步骤。例 1：阻塞直到 I/O 完成的库函数，可以看作在不断检查操作是否完成，每次检查都由执行步骤组成。

有了这条规则，一个阻塞在 `mutex::lock()` 或 `condition_variable::wait()` 中的线程，就不会因为没有执行步骤而被视为饿死，也不会触发 ¶1 的 UB。

¶5 当一个执行步骤发生，或者一个无锁执行由于其他未阻塞的并发线程而未能完成时，线程**取得进展**（makes progress）。后一种即 ¶2.1 的情形：输给了竞争对手也算进展，因为对手在前进。

## 三级前进保证（¶6–¶12）

| 保证 | 实现确保的事 | 段落 | 典型载体 |
|---|---|---|---|
| **并发**（concurrent） | 只要线程未终止，它终将取得进展，无论其他线程是否在进展 | ¶6 | `std::thread`、`std::jthread`、`main` 线程（建议） |
| **并行**（parallel） | 若线程尚未执行任何执行步骤，不保证它会开始；一旦执行了一步，就提供并发保证 | ¶8 | 线程池中的任务；`execution::par` 下库创建的线程 |
| **弱并行**（weakly parallel） | 不保证线程终将取得进展 | ¶10 | `execution::par_unseq` 下库创建的线程；GPU 线程 |

¶6 注 4："终将"指在未指定但有限的时间内。

¶7 主线程以及 `std::thread`、`std::jthread` 创建的线程是否提供并发前进保证，由实现定义 {{impl}}；通用实现应当提供。（用"应当"是为了给单核无抢占的嵌入式系统留出余地。）

¶8–¶9 并行保证可以对照线程池来理解：任务一旦开始执行就不会被无限期搁置，但尚未开始的任务可能一直排队。注 5 给出一个例子：一个提供并发保证的线程以任意顺序、一个接一个地执行一组任务，就满足这些任务的并行保证。

¶10–¶11 弱并行可以对照 SIMD/GPU 的 lane 来理解：同一组 lane 锁步执行，如果一个 lane 在自旋等待另一个 lane 设置的标志，而后者因为分支发散一直没被调度，就会死锁。弱并行线程不能指望自己取得进展，但通过下面介绍的带前进保证委托的阻塞，可以确保它们终将取得进展。

¶12 三者强度递减：并发 > 并行 > 弱并行。注 7：有些线程间同步只有在线程至少提供并行保证时才能进展，在弱并行下会失败。

### 并行算法中的后果

[[algorithms.parallel.exec]] 把这些保证落实到执行策略上：

| 策略 | 库创建的线程的保证 | 能否在元素访问函数里用 mutex？ |
|---|---|---|
| `execution::seq` | 在调用线程上顺序执行 | 可以 |
| `execution::par` | 若 `std::thread` 提供并发保证，则为并行；否则实现定义 | 可以，但不能让一次调用等待另一个尚未开始的调用 |
| `execution::par_unseq` | 弱并行；且多个调用可以在同一线程上交错 | 不行：阻塞同步有死锁风险，调用向量化不安全的库函数是 UB |
| `execution::unseq` | 在调用线程上，调用可以交错 | 不行，理由同上 |

```cpp run title="par-spin.cpp"
#include <algorithm>
#include <atomic>
#include <execution>
#include <vector>
std::atomic<int> stage{0};
void bad(std::vector<int>& v) {
  std::for_each(std::execution::par, v.begin(), v.end(), [&](int& x) {
    if (&x == &v.front()) {
      while (stage.load() == 0) { }   // 等待"另一个元素"的调用……
    } else if (&x == &v.back()) {
      stage.store(1);                 // ……但并行保证不承诺它一定会开始执行
    }
  });
}
int main() { std::vector<int> v(2); (void)v; }
```

在 `par` 下，处理 `back()` 的调用可能被排在处理 `front()` 的调用之后，在同一个工作线程上执行。这样它永远不会开始，`front()` 的调用就会一直自旋下去。这不是 UB，而是死锁：标准没有承诺尚未开始的调用一定会开始（¶8）。用 `seq` 时同样可能死锁（若先处理 front）。正确设计是让元素访问函数之间不相互等待。（此例只为说明，不要运行 `bad`。）

[[algorithms.parallel.exec#9]] 还规定：若并行算法使用了库创建的线程，调用线程会带前进保证委托地阻塞在这些线程的完成上，或者自己去执行元素访问函数。这样即使工作线程只有弱并行保证，算法也终将完成。

### std::execution 中的前进保证

{{c++26}} `std::execution`（[[exec]]）把这套术语暴露为查询：`execution::get_forward_progress_guarantee(sch)` 返回调度器的 `forward_progress_guarantee::concurrent`、`parallel` 或 `weakly_parallel`（[[exec.get.fwd.progress]]）。`this_thread::sync_wait` 要求带前进保证委托地阻塞当前线程，直到 sender 完成，默认实现通过 `get_delegation_scheduler` 查询提供一个由当前线程驱动的 `run_loop` 调度器来达成这一点（[[exec.sync.wait]]）。

## 带前进保证委托的阻塞（¶13–¶16）

¶13 如果规定线程 P **带前进保证委托地阻塞**（block with forward progress guarantee delegation）在一组线程 S 的完成上，那么在 P 阻塞期间，实现必须确保 S 中至少一个线程的前进保证不弱于 P 的保证。S 中的线程终止后被移出 S；S 为空时 P 解除阻塞。

注 8：选择 S 中哪个线程、强化多少步是未指定的；强化不是永久的。只要 P 还在阻塞，实现就必须终将选择并（可能）强化 S 中的某个线程。

直观地说，P 把自己的前进保证借给它等待的线程。若 P 提供并发保证，它在等待一批弱并行任务时，实现必须让其中至少一个任务以并发保证运行。最简单的实现就是 P 自己去执行那些任务，`sync_wait` 的 `run_loop` 和并行算法 ¶9.2 正是这样做的。

¶14 注 9：委托是可传递的。A 阻塞在 B 上强化了 B；若 B 又带委托地阻塞在 C 上，C 也被强化。¶15 注 10：若 S 中的线程都正常结束（终止、且不错误地使用阻塞同步），P 的进展保证不会因这次阻塞而被有效削弱。¶16 注 11：委托并不消除对并行/弱并行线程使用阻塞同步的限制，实现不需要专门强化那个恰好因为保证太弱而阻碍整体进展的线程。

## 最终可见性（¶17）

¶17 实现应当确保原子或同步操作赋予的最后一个值（按修改顺序）在有限时间内对所有其他线程可见。[[atomics.order#13]] 有类似的建议。这只是建议（should），但如果没有它，像下面这样的自旋等待在理论上可能永远看不到新值：

```cpp run title="spin.cpp" ok
#include <atomic>
#include <thread>
std::atomic<bool> go{false};
int main() {
  std::thread t([] { while (!go.load(std::memory_order::acquire)) { } });  // 原子 load：¶1.5，不是 UB
  go.store(true, std::memory_order::release);
  t.join();   // ¶17 + [atomics.order]/13：t 终将看到 true
}
```

## 实现视角

!!! impl "编译器如何实现 ¶1"
    - LLVM IR 中，C++ 函数默认带 `mustprogress` 属性，表示函数必须终将返回、展开或与环境交互；优化器据此删除无副作用的循环。C 代码（及 C++ 中的平凡无限循环）不带该属性或在循环上不附加相应元数据。
    - GCC 通过 `-ffinite-loops` 控制类似的假设，在 C++11 及以后的模式下于 `-O2` 默认开启。
    - 截至写作时，Clang 23 在 `-std=c++2c` 下对平凡无限循环生成真正的无限跳转，而对 `for (unsigned i = 0;; ++i) {}` 生成陷阱指令，与本页所述的 C++26 规则相符。标准说语句被替换成 `yield()` 调用，但 `yield` 没有可观察效果，按 as-if 规则实现不必真的生成调用。

## 历史与演进

!!! history "从 C++11 到 C++26"
    - **C++11**：引入"实现可以假设任何线程终将终止或执行 I/O/volatile/同步/原子操作"这一规则，以及关于无锁和最终可见性的建议。
    - **C++17**：为支持并行算法，引入执行步骤、并发/并行/弱并行前进保证、带前进保证委托的阻塞等术语。
    - **C++26**：[[P2809R3]] 使平凡无限循环不再是 UB（¶1.6 与 [[stmt.iter.general#3]]）；原子 modify-write 操作被排除在 ¶1.5 和 ¶3.4 之外；`std::execution` 用本节术语描述调度器的保证。

## 陷阱

!!! pitfall "“死循环等中断”在 C++23 及以前是 UB"
    `while (1) ;` 在 C++26 之前是 UB。嵌入式代码常在其中加一条 `volatile` 访问或 `asm volatile("")` 来规避，后者是实现扩展，前者是可移植的做法（¶1.4）。C++26 起，空的、条件为常量的循环可以直接写。

!!! pitfall "只有“空”的循环才享受豁免"
    `while (true) { ++local; }` 依然是 UB（如果它真的永远运行），因为循环体不空。`for (;;) {}` 可以，`for (;; ++i) {}` 不行。条件必须是常量表达式：`const bool b = true; while (b);` 可以（`b` 是常量初始化的 `const` 整型/布尔变量，可用于常量表达式），读取普通全局变量的 `while (g);` 不行。

!!! pitfall "自旋等待非原子标志"
    `while (!ready) {}`（`ready` 是普通 `bool`）同时违反两条规则：数据竞争（[[intro.races#17]]），以及在编译器把读取外提时的前进假设。应当用 `std::atomic<bool>`。

## 思考题

!!! question "1. 下面哪个函数（若永远执行下去）在 C++26 中是 UB？"
    ```cpp
    void f1() { while (true) {} }
    void f2() { while (true) { std::this_thread::yield(); } }
    void f3() { int i = 0; while (true) { ++i; } }
    void f4() { std::atomic<int> a; while (true) { a.load(std::memory_order::relaxed); } }
    void f5() { volatile int v = 0; while (true) { (void)v; } }
    ```

<details markdown="1">
<summary>答案</summary>

只有 `f3` 是 UB：循环体不空，因而不是平凡空迭代语句，也不做 ¶1 中的任何事。`f1` 是平凡无限循环（¶1.6）；`f2` 调用 `yield`（¶1.2）；`f4` 执行原子操作（¶1.5，relaxed 也算）；`f5` 通过 volatile glvalue 访问（¶1.4；`(void)v` 是弃值表达式，对 volatile 左值会执行左值到右值转换，见 [[expr.context]]）。
</details>

!!! question "2. 为什么 ¶2.1 只要求 “obstruction-free”，而把真正的 lock-free 放进 “should”？"

<details markdown="1">
<summary>答案</summary>

因为基于 LL/SC 的硬件（老式 ARM、POWER、RISC-V 的 LR/SC）上，CAS 循环理论上可能被其他核心的干扰无限期打断，实现无法给出绝对的 lock-free 保证；但在只有一个线程运行的情况下必然成功，这一点可以保证。标准于是把可证明的部分写成要求，把实践中成立的部分写成建议（注 3）。
</details>

## 小结

| 主题 | 要点 | 段落 |
|---|---|---|
| 前进假设 | 线程终将终止 / yield / I/O / volatile / 原子或同步（不含 modify-write）/ 执行平凡无限循环，否则 UB | ¶1 |
| 平凡无限循环 | 空循环体 + 常量 `true` 条件；C++26 起不是 UB，语句视为 `yield()` | ¶1.6、[[stmt.iter.general#3]] |
| 无锁执行 | 必须 obstruction-free；建议 lock-free | ¶2 |
| 执行步骤 | 终止、volatile 访问、I/O 完成、原子/同步操作完成 | ¶3 |
| 阻塞的库调用 | 视为持续执行执行步骤 | ¶4 |
| 并发 / 并行 / 弱并行 | 终将进展 / 开始后终将进展 / 无保证 | ¶6、¶8、¶10 |
| 委托 | 阻塞者把自己的保证借给被等待者 | ¶13 |
| 最终可见 | 原子写应在有限时间内对其他线程可见（建议） | ¶17 |
