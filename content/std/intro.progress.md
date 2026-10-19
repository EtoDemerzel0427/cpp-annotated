---
title: 前进保证
summary: 编译器可以假设每个线程终将做出可观察的动作，所以无副作用的死循环是 UB（C++26 起平凡无限循环除外）；实现则按并发、并行、弱并行三个等级保证线程能往前走。
status: draft
papers: P2809R3
related: intro.multithread, intro.races, stmt.iter.general, algorithms.parallel.exec, exec.get.fwd.progress, atomics.lockfree
tags: 并发, UB, 循环, 前进保证
updated: 2026-10-19
---

!!! tldr
    - 实现可以假设每个线程终将终止，或者做 I/O、volatile 访问、原子或同步操作、`yield`。一个线程永远不做这些事就是 UB，所以编译器可以删除它证明不了会终止的空循环。
    - C++26 起，循环体为空、条件是常量 `true` 的循环（平凡无限循环）不再是 UB，`while (true);` 可以放心写。
    - 循环体不空，或者条件不是常量表达式，就不享受这个豁免：`for (;; ++i) {}` 和 `while (flag);` 永远运行时仍是 UB。
    - 实现对线程的保证分三级：并发（终将取得进展）、并行（开始之后才保证）、弱并行（不保证）。`std::thread` 通常是并发的，并行算法的工作线程只有并行或弱并行保证。
    - 一个线程带前进保证委托地等待一组线程时，会把自己的保证借给其中至少一个，`sync_wait` 和并行算法靠这一点保证终将完成。

## 编译器可以删掉一个可能不终止的循环吗（¶1）

```cpp run title="collatz.cpp" ok
unsigned f(unsigned n) {
  while (n != 1) n = (n % 2) ? 3 * n + 1 : n / 2;
  return 1;
}
int main(int argc, char**) { return f(argc + 26) == 1 ? 0 : 1; }
```

这个循环对 `n == 0` 不终止（0 → 0 → …），对一般的 `n` 是否终止则是著名的未解决问题（Collatz 猜想）。但本机 Clang 23 `-O2` 把 `f` 编译成直接返回 1，循环整个被删掉了。依据是下面这条规则。

¶1 实现可以假设任何线程终将做下列事情之一：

- ¶1.1 终止；
- ¶1.2 调用 `std::this_thread::yield`；
- ¶1.3 调用库 I/O 函数；
- ¶1.4 通过 volatile glvalue 进行访问；
- ¶1.5 执行原子操作或同步操作，原子 modify-write 操作除外（见下文）；
- ¶1.6 {{c++26}} 继续执行一个平凡无限循环（见下一节）。

如果某个线程永远运行，却不做以上任何一件事，行为未定义 {{ub}}。`f` 的循环只修改局部变量，假如它不终止，线程就再也不会做任何可观察的事，这正是实现可以假设不会发生的情况。所以编译器不必知道循环是否终止：终止时返回 1，不终止时是 UB，直接返回 1 在两种情况下都合法。本例中 `n == 27`，循环会终止，程序行为良好。

注 1 说明了这条规则的用意：即使无法证明空循环会终止，也允许编译器删除、合并或重排它。实际代码里很多循环能否终止取决于编译器证明不了的不变式，例如沿链表遍历 `for (p = head; p != end; p = p->next)`。循环结果没人用时删掉它，或者把循环后的代码提到循环前，都要以循环终将结束为前提。

## 平凡无限循环（¶1.6）{{c++26}}

C++23 及以前，`while (true) ;` 同样是 UB。这和嵌入式、系统编程的常见写法冲突：

```cpp
[[noreturn]] void halt() { while (true) ; }   // 停在这里，等看门狗复位或中断
```

程序员想让程序永远停在这里，编译器却可以把循环删掉，然后控制流落进后面的任意代码。Clang 的旧版本确实这样处理过 `int main() { while (1) ; }`：`main` 被编译成空函数体，执行时直接落入下一个函数。

C++26 通过 [[P2809R3]] 修正了这一点。[[stmt.iter.general#3]] 定义了两个概念：

- **平凡空迭代语句**（trivially empty iteration statement）是循环体为空的 `while`、`do` 或 `for` 语句：`while (E) ;`、`while (E) { }`、`do ; while (E) ;`、`do { } while (E) ;`、`for (init E ; ) ;`、`for (init E ; ) { }`。`for` 语句不能有迭代表达式，条件 `E` 省略时视为 `true`。
- **平凡无限循环**（trivial infinite loop）是条件为常量表达式、且值为 `true` 的平凡空迭代语句。它的循环体被替换为对 `std::this_thread::yield` 的调用（独立实现中是否替换由实现定义）。

替换之后，这个循环每次迭代都在做 ¶1.2 的事；¶1.6 又直接把继续执行平凡无限循环列为允许的情形。两者共同保证它不是 UB，注 1 也说明它不能被删除或重排。

```cpp run title="trivial-loops.cpp" ok
constexpr bool forever = true;
void a() { while (forever) ; }      // 平凡无限循环
void b() { for (;;) { } }           // 平凡无限循环：for 省略条件视为 true
void c() { do { } while (1); }      // 平凡无限循环
bool flag;
void d() { while (flag) ; }         // 条件不是常量表达式
void e() { while (true) { int x = 0; (void)x; } }  // 循环体不空
void f() { for (unsigned i = 0; ; ++i) { } }       // 有迭代表达式
int main() {}
```

`d`、`e`、`f` 都不是平凡无限循环，永远运行时仍然是 UB。本机 Clang 23 `-O2` 对 `a`、`b`、`c` 生成真正的无限跳转；对 `e`、`f` 生成一条陷阱指令（AArch64 上是 `brk`），认定这里不可达；对 `d` 则直接生成 `ret`，即使 `flag` 为真也立即返回。

`d` 尤其容易写错。如果想让另一个线程把 `flag` 改成 `false` 来结束等待，这本身就是数据竞争（[[intro.races#17]]）；正确的写法是 `std::atomic<bool>`，原子读取属于 ¶1.5，循环也就不再是 UB。

!!! note "C 语言的类似规则"
    C11 起，C 标准规定：控制表达式不是常量表达式的循环，如果不做 I/O、volatile 访问、同步或原子操作，实现可以假设它终止。所以 C 从一开始就把 `while (1) ;` 排除在外。C++26 的规则向 C 靠拢，但范围更窄：C++ 还要求循环体为空。

### ¶1.5 中的 modify-write 例外

C++26 新增了**原子 modify-write 操作**（atomic modify-write operation）：同步要求更弱的一类原子读-改-写操作，例如整数原子的 `store_add`（[[atomics.order#12]]）。它们只写入、不返回旧值，线程无法借此观察其他线程的进展。所以一个只做 `store_add` 的无限循环，和只写局部变量的循环一样，不算满足 ¶1.5。下文 ¶3.4 的执行步骤同样把它们排除在外。

## 实现要保证什么

¶1 是程序员对实现的承诺：线程不会无声无息地永远空转。本节其余段落反过来规定实现的义务：线程在什么条件下一定能往前走。`std::thread`、并行算法和 `std::execution` 的调度器都用这套术语描述自己的保证。

### 执行步骤与取得进展（¶3–¶5）

¶3 线程执行期间，下列事件叫做**执行步骤**（execution step）：

- ¶3.1 线程终止；
- ¶3.2 通过 volatile glvalue 进行访问；
- ¶3.3 库 I/O 调用完成；
- ¶3.4 原子或同步操作完成，原子 modify-write 操作除外。

¶1 列的是实现可以假设线程会做的事，¶3 列的是算作进展的事件，两份清单大体对应。

¶4 阻塞在标准库函数里的调用，在等待期间被视为持续执行执行步骤。**阻塞**（block）指等待某个条件满足才能继续（[[defns.block]]）。例 1 的说法是：阻塞到 I/O 完成的库函数，可以看作在不断检查操作是否完成。有了这一条，阻塞在 `mutex::lock()` 或 `condition_variable::wait()` 里的线程既不算饿死，也不违反 ¶1。

¶5 当一个执行步骤发生，或者一个无锁执行（见下文 ¶2）因为其他未阻塞的线程在并发运行而没能完成时，线程**取得进展**（makes progress）。后一种情形下，输给对手也算进展，因为对手在前进。

### 三级前进保证（¶6–¶12）

| 保证 | 实现确保什么 | 段落 | 典型例子 |
|---|---|---|---|
| **并发**（concurrent） | 只要线程没终止，它终将取得进展，不论其他线程如何 | ¶6 | `main` 线程、`std::thread`、`std::jthread`（建议） |
| **并行**（parallel） | 线程还没执行任何执行步骤时，不保证它会开始；一旦执行了一步，就提供并发保证 | ¶8 | 线程池里的任务；`execution::par` 下的工作线程 |
| **弱并行**（weakly parallel） | 不保证线程终将取得进展 | ¶10 | `execution::par_unseq` 下的工作线程；GPU 上的线程 |

¶6 注 4 解释，终将指在未指定但有限的时间内。

¶7 `main` 所在的线程以及 `std::thread`、`std::jthread` 创建的线程是否提供并发保证，由实现定义 {{impl}}；通用实现应当提供。这里只写应当，是为了给单核、无抢占的嵌入式系统留出余地。

¶8–¶9 并行保证可以对照线程池来理解：任务一旦开始执行，就不会被无限期搁置，但还没开始的任务可能一直排队。注 5 举的例子正是这样：一个有并发保证的线程以任意顺序、一个接一个地执行一组任务，就满足了这些任务的并行保证。

¶10–¶11 弱并行可以对照 GPU 的 SIMD 通道来理解。同一组通道锁步执行，如果一个通道自旋等待另一个通道设置的标志，而后者因为分支发散一直没被调度，就会死锁。弱并行线程不能指望自己取得进展，但可以用下文的带前进保证委托的阻塞来保证它们终将完成。

¶12 三者强度递减：并发 > 并行 > 弱并行。注 7 指出，有些线程间同步只有在双方至少提供并行保证时才能进展，在弱并行下会卡住。

### 并行算法里的后果

[[algorithms.parallel.exec]] 把这些保证落实到执行策略上：

| 策略 | 元素访问函数在哪里执行 | 能否在元素访问函数里用 mutex |
|---|---|---|
| `execution::seq` | 调用线程上，依次执行 | 可以 |
| `execution::par` | 库创建的线程上，有并行保证（若 `std::thread` 有并发保证） | 可以，但不能让一次调用等待另一次还没开始的调用 |
| `execution::par_unseq` | 弱并行，多次调用还可以在同一线程上交错 | 不行，阻塞同步可能死锁，调用向量化不安全的库函数是 UB |
| `execution::unseq` | 调用线程上，多次调用可以交错 | 不行，理由同上 |

```cpp run title="par-spin.cpp" flags="-std=c++2c -fexperimental-library"
#include <algorithm>
#include <atomic>
#include <execution>
#include <vector>
std::atomic<int> stage{0};
void bad(std::vector<int>& v) {
  std::for_each(std::execution::par, v.begin(), v.end(), [&](int& x) {
    if (&x == &v.front()) {
      while (stage.load() == 0) { }   // 等待另一个元素的调用
    } else if (&x == &v.back()) {
      stage.store(1);                 // 但这次调用不保证会开始
    }
  });
}
int main() { std::vector<int> v(2); (void)v; }
```

在 `par` 下，处理 `back()` 的调用可能排在处理 `front()` 的调用之后，落到同一个工作线程上。这样它永远不会开始，`front()` 的调用就一直自旋。这不是 UB（自旋里有原子读取），而是死锁：并行保证不承诺还没开始的调用一定会开始（¶8）。用 `seq` 时，如果先处理 `front()`，同样会死锁。正确的设计是让元素访问函数之间不互相等待。本机 libc++ 要加 `-fexperimental-library` 才提供并行执行策略；`main` 没有调用 `bad`，这段代码只用来说明。

[[algorithms.parallel.exec#9]] 还规定，如果并行算法使用了库创建的线程，调用线程要么带前进保证委托地阻塞在它们的完成上，要么自己去执行元素访问函数。这样即使工作线程只有弱并行保证，算法也终将完成。

### 带前进保证委托的阻塞（¶13–¶16）

¶13 如果规定线程 P **带前进保证委托地阻塞**（block with forward progress guarantee delegation）在一组线程 S 的完成上，那么在 P 阻塞期间，实现必须确保 S 中至少有一个线程的前进保证不弱于 P 的保证。S 中的线程终止后就移出 S，S 为空时 P 解除阻塞。

直观地说，P 把自己的前进保证借给它在等的线程。P 有并发保证，它等待一批弱并行任务时，实现就必须让其中至少一个以并发保证运行。最简单的实现是 P 自己去执行这些任务。

注 8 补充，选中 S 里的哪个线程、强化多少步都是未指定的，强化也不是永久的；只要 P 还在阻塞，实现就必须终将选中并强化 S 里的某个线程。后面三条注说明了几个推论：

- ¶14 注 9：委托可以传递。A 阻塞在 B 上，B 得到强化；B 又带委托地阻塞在 C 上，C 也得到强化。
- ¶15 注 10：如果 S 中的线程都正常结束，P 的前进保证不会因为这次阻塞而被削弱。
- ¶16 注 11：委托不解除对并行、弱并行线程使用阻塞同步的限制，因为实现不必专门去强化那个恰好拖住整体进展的线程。

C++26 的 `std::execution`（[[exec]]）把这套术语暴露为查询：`execution::get_forward_progress_guarantee(sch)` 返回调度器的 `forward_progress_guarantee::concurrent`、`parallel` 或 `weakly_parallel`（[[exec.get.fwd.progress]]）。`this_thread::sync_wait` 带前进保证委托地阻塞当前线程，直到 sender 完成；它的做法是提供一个由当前线程驱动的 `run_loop` 调度器（[[exec.sync.wait]]）。

### 无锁执行（¶2）

¶2 被定义为无锁的原子函数（`atomic_flag` 的操作，[[atomics.flag]]）和被指示为无锁的原子函数（`is_lock_free()` 为真，[[atomics.lockfree]]），它们的执行叫做**无锁执行**（lock-free execution）。标准对它们提了两条要求：

- ¶2.1 如果只有一个线程没有阻塞在标准库函数里，这个线程中的无锁执行必须完成。注 2 说明，并发运行的线程可能阻止无锁执行完成，例如在 LL/SC（load-linked / store-conditional）实现中，其他线程的写入可以让 SC 一直失败。这一性质通常叫做无阻碍（obstruction-free）。
- ¶2.2 一个或多个无锁执行并发运行时，应当至少有一个完成。注 3 说明，恶意的干扰（比如反复抢走缓存行）可以阻止进展，实现很难绝对保证这一点；但只要实现在预期的运行条件下避免了这类异常，程序员就可以忽略它们。这一性质通常叫做无锁（lock-free）。

所以名字有些错位：标准的 lock-free execution 只强制要求无阻碍，通常意义上的无锁只是一条建议。

### 最终可见（¶17）

¶17 实现应当确保原子或同步操作写入的最后一个值（按修改顺序）在有限时间内对所有其他线程可见。[[atomics.order#13]] 有同样的建议。这只是建议，但如果没有它，下面这样的自旋等待在理论上可能永远看不到新值：

```cpp run title="spin.cpp" ok
#include <atomic>
#include <thread>
std::atomic<bool> go{false};
int main() {
  std::thread t([] {
    while (!go.load(std::memory_order::acquire)) { }  // 原子读取：¶1.5，不是 UB
  });
  go.store(true, std::memory_order::release);
  t.join();   // t 终将看到 true
}
```

## 实现视角

!!! impl "编译器怎样实现 ¶1"
    - LLVM IR 中，C++ 函数默认带 `mustprogress` 属性，表示函数必须终将返回、展开或与环境交互，优化器据此删除无副作用的循环。C 代码和 C++ 的平凡无限循环不带相应的属性或循环元数据。
    - GCC 用 `-ffinite-loops` 控制类似的假设，C++11 及以后的模式在 `-O2` 下默认开启。
    - 标准说平凡无限循环的循环体被替换成 `yield()` 调用，但 `yield` 没有可观察效果，按 as-if 规则实现不必真的生成这个调用。本机 Clang 23 生成的就是一条跳回自身的指令。

## 历史与演进

!!! history
    - C++11 引入了实现可以假设线程终将终止或做 I/O、volatile、同步、原子操作这条规则，以及关于无锁和最终可见的建议。
    - C++17 为并行算法引入了执行步骤、三级前进保证和带前进保证委托的阻塞。
    - C++26：[[P2809R3]] 让平凡无限循环不再是 UB；原子 modify-write 操作被排除在 ¶1.5 和 ¶3.4 之外；`std::execution` 用这套术语描述调度器的保证。

## 常见误解

!!! pitfall "死循环等中断一直是合法的"
    `while (1) ;` 在 C++26 之前是 UB。以前的嵌入式代码常在循环里加一次 volatile 访问（¶1.4，可移植）或 `asm volatile("")`（实现扩展）来规避。C++26 起，循环体为空、条件为常量的循环可以直接写。

!!! pitfall "只要条件是 true，循环就不是 UB"
    还要求循环体为空。`while (true) { ++local; }` 永远运行时仍然是 UB；`for (;;) {}` 可以，`for (;; ++i) {}` 不行。条件也必须是常量表达式：`const bool b = true; while (b);` 可以，因为 `b` 是常量初始化的 const 变量，可以用在常量表达式里；读取普通全局变量的 `while (g);` 不行。

!!! pitfall "用普通 bool 做自旋等待"
    `while (!ready) {}`（`ready` 是普通 `bool`）同时违反两条规则：另一个线程写 `ready` 是数据竞争（[[intro.races#17]]），循环本身也违反 ¶1。编译器可以把读取提到循环外，甚至像上面的 `d` 那样把循环整个删掉。应当用 `std::atomic<bool>`。

## 思考题

!!! question "思考题 1"
    下面哪些函数如果永远执行下去，在 C++26 中是 UB？
    ```cpp
    void f1() { while (true) {} }
    void f2() { while (true) { std::this_thread::yield(); } }
    void f3() { int i = 0; while (true) { ++i; } }
    void f4() { std::atomic<int> a; while (true) { a.load(std::memory_order::relaxed); } }
    void f5() { volatile int v = 0; while (true) { (void)v; } }
    ```

<details markdown="1">
<summary>答案</summary>

只有 `f3` 是 UB：循环体不空，所以不是平凡无限循环，循环里也不做 ¶1 中的任何事。`f1` 是平凡无限循环（¶1.6）；`f2` 调用 `yield`（¶1.2）；`f4` 执行原子操作，relaxed 也算（¶1.5）；`f5` 通过 volatile glvalue 访问（¶1.4）。`(void)v` 是弃值表达式，对名字为 volatile 变量的表达式会执行左值到右值转换，也就是真的读一次（[[expr.context]]）。
</details>

!!! question "思考题 2"
    为什么 ¶2.1 只强制要求无阻碍，而把真正的无锁写成建议？

<details markdown="1">
<summary>答案</summary>

在 LL/SC 硬件（较早的 ARM、POWER、RISC-V 的 LR/SC）上，CAS 循环理论上可能被其他核心的干扰无限期打断，实现无法绝对保证无锁。但只有一个线程在运行时，操作必然成功，这一点可以保证。标准于是把能保证的部分写成要求，把实践中成立的部分写成建议（注 3）。
</details>

## 小结

| 主题 | 要点 | 段落 |
|---|---|---|
| 前进假设 | 线程终将终止、yield、I/O、volatile 访问、原子或同步操作（不含 modify-write）、执行平凡无限循环，否则 UB | ¶1 |
| 平凡无限循环 | 循环体为空且条件为常量 `true`；C++26 起不是 UB | ¶1.6、[[stmt.iter.general#3]] |
| 执行步骤 | 终止、volatile 访问、I/O 完成、原子或同步操作完成 | ¶3 |
| 阻塞的库调用 | 视为持续执行执行步骤 | ¶4 |
| 并发 / 并行 / 弱并行 | 终将进展 / 开始后终将进展 / 不保证 | ¶6、¶8、¶10 |
| 委托 | 阻塞者把自己的保证借给被等待者 | ¶13 |
| 无锁执行 | 必须无阻碍；建议无锁 | ¶2 |
| 最终可见 | 原子写入应在有限时间内对其他线程可见（建议） | ¶17 |
