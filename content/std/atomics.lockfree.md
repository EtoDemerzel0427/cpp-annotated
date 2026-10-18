---
title: 无锁性质
summary: ATOMIC_*_LOCK_FREE 宏的 0/1/2 含义、is_always_lock_free 与 is_lock_free、宿主实现至少有一对无锁整数、"不是无锁的原子操作可能阻塞"对前进保证的影响、address-free 与跨进程共享内存；附 Apple Silicon 上各类型的实测
status: done
covers: atomics.lockfree
related: atomics, atomics.types.generic, atomics.ref.generic, intro.progress, atomics.flag, atomics.alias
tags: 标准库, 原子操作, 无锁
updated: 2026-10-18
---

`std::atomic<T>` 可以用于**任何**可平凡复制的 `T`——包括 1 KB 的结构体。硬件显然没有 1 KB 的原子指令，所以实现可以用锁来模拟。[atomics.lockfree] 规定程序如何查询"这个原子类型是不是真的无锁"，以及"不是无锁"在内存模型中的后果。

## 宏（¶1）

`<atomic>` 定义 11 个宏：`ATOMIC_BOOL_LOCK_FREE`、`ATOMIC_CHAR_LOCK_FREE`、`ATOMIC_CHAR8_T_LOCK_FREE`、`ATOMIC_CHAR16_T_LOCK_FREE`、`ATOMIC_CHAR32_T_LOCK_FREE`、`ATOMIC_WCHAR_T_LOCK_FREE`、`ATOMIC_SHORT_LOCK_FREE`、`ATOMIC_INT_LOCK_FREE`、`ATOMIC_LONG_LOCK_FREE`、`ATOMIC_LLONG_LOCK_FREE`、`ATOMIC_POINTER_LOCK_FREE`。

¶1 这些宏表示对应原子类型的无锁性质，有符号与无符号变体归为一组；性质同样适用于 `atomic` 模板对应的（偏）特化。取值：

| 值 | 含义 |
|---|---|
| 0 | 从不无锁 |
| 1 | **有时**无锁 |
| 2 | 总是无锁 |

"有时无锁"存在的原因：同一个二进制可能运行在不同的 CPU 上（例如老的 x86 没有 `cmpxchg16b`），或者无锁与否取决于对象的对齐。宏是**预处理期**常量，可以用在 `#if` 里，这是它们相比 `is_always_lock_free` 唯一的优势。

¶2 在**宿主**实现上，至少有一个有符号整数的 `atomic` 特化，连同对应的无符号类型，是**总是无锁**的。这项保证与 C++20 的 `atomic_signed_lock_free`/`atomic_unsigned_lock_free` 别名（[[atomics.alias]]）配套：在宿主实现上，可移植代码总能找到一个无锁整数。独立实现没有这项保证——那里唯一保证无锁的是 `atomic_flag`（[[atomics.flag]] ¶2）。

## 运行期查询（¶3）

¶3 `atomic<T>::is_lock_free` 与 `atomic_is_lock_free`（[[atomics.types.operations]]）报告对象是否无锁。**在任何一次程序执行中，同类型的所有原子对象的查询结果相同。**

最后一句排除了"按对象对齐决定"的实现：同一类型的 `atomic` 对象，要么都无锁，要么都不是。这让 `is_lock_free()` 实际上是一个"类型的运行期性质"。`atomic_ref` 的情况类似，它的 `is_lock_free()` 也被规定为针对**类型**的（[[atomics.ref.ops]] ¶4），为此它要求被引用对象按 `required_alignment` 对齐。

编译期的对应物是 `static constexpr bool is_always_lock_free`（[[atomics.types.operations]] ¶4）：为 `true` 时意味着在**所有**运行环境上都无锁。注 2：它与对应的 `ATOMIC_..._LOCK_FREE` 宏（若有）一致。

```cpp run title="lockfree-table.cpp" ok
#include <atomic>
#include <cstdio>

struct P2  { void* a; void* b; };   // 16 字节
struct S12 { int a, b, c; };        // 12 字节
struct S32 { long a[4]; };          // 32 字节

#define SHOW(T) std::printf("%-12s sizeof(atomic) %2zu  alignof %2zu  always_lock_free %d\n", #T, \
  sizeof(std::atomic<T>), alignof(std::atomic<T>), (int)std::atomic<T>::is_always_lock_free)

int main() {
  SHOW(bool); SHOW(long long); SHOW(long double); SHOW(P2); SHOW(S12); SHOW(S32);
  std::printf("atomic_ref<S12>: required_alignment %zu  always_lock_free %d\n",
              std::atomic_ref<S12>::required_alignment, (int)std::atomic_ref<S12>::is_always_lock_free);
}
```

Apple Silicon + libc++ 的输出：

| 类型 | `sizeof(atomic<T>)` | `alignof` | 总是无锁 |
|---|---|---|---|
| `bool` | 1 | 1 | 1 |
| `long long` | 8 | 8 | 1 |
| `long double`（在此平台即 `double`） | 8 | 8 | 1 |
| `P2`（16 字节） | 16 | **16** | 1 |
| `S12`（12 字节） | **16** | **16** | 1 |
| `S32`（32 字节） | 32 | 8 | **0** |

两点观察：

- `atomic<S12>` 被**补齐到 16 字节、16 字节对齐**，从而可以用 16 字节的原子指令（`caspal`、`ldp`/`stp`）。[[atomics.types.generic]] ¶3 注 2 明确允许这种做法："`atomic` 特化的表示不必与其实参类型有相同的大小和对齐"。
- 同一个 `S12`，`atomic_ref<S12>` 的 `required_alignment` 只有 4、**不是**无锁的：`atomic_ref` 不能改变被引用对象的大小，12 字节的对象没有原子指令可用。`atomic_ref` 与 `atomic` 的无锁性质可以不同。

32 字节的 `S32` 不是无锁的；libc++ 把这类操作交给编译器运行库的 `__atomic_load` 等函数，它们用一张按地址散列的自旋锁表实现。

## "可能阻塞"（¶4）

¶4 **不是无锁的原子操作，被视为可能阻塞**（[[intro.progress]]）。

这一句把库与核心语言的前进保证连了起来。[[intro.progress]] ¶2 规定：被定义为无锁（`atomic_flag`）或被指示为无锁（本节）的原子函数的执行是**无锁执行**（[[g:lock-free-execution]]）——若只有一个线程没有阻塞在标准库函数中，它的无锁执行必定完成。不是无锁的原子操作则没有这项保证，被当作可能阻塞的库函数对待（[[intro.progress]] ¶4）。实际后果：

- **信号处理函数**里，除了明确标为信号安全的函数，标准库调用中只有**普通无锁原子操作**（[[g:plain-lock-free-atomic-operation]]）是信号安全的（[[support.signal]] ¶2–¶3）。直觉：如果信号打断了一个正持有内部锁的原子操作，处理函数再操作同一对象就会自锁。
- 在只提供弱并行前进保证的执行代理（如 `par_unseq` 算法的元素访问函数，[[algorithms.parallel]]）中，使用可能阻塞的操作可能导致死锁。

## address-free（¶5）

¶5 *推荐做法*：无锁的操作也应当是 **address-free** 的——通过两个不同地址对同一内存位置执行原子操作，应当能原子地通信（脚注 273）。实现不应依赖任何"每进程状态"。注 1：这一限制使得通过"在进程中映射多次的内存"和"两个进程共享的内存"进行通信成为可能。

这正是用 `mmap`/`shm_open` 在进程间放置 `std::atomic` 的依据。只有无锁且 address-free 的原子类型才适合：基于锁的实现，锁表往往在进程私有的内存里，两个进程根本看不到对方的锁。注意 ¶5 只是推荐，标准本身并不保证跨进程原子性。

!!! pitfall "跨进程共享时别忘了 `wait`/`notify`"
    原子对象本身是 address-free 的，并不意味着它的 `wait`/`notify_one` 也能跨进程工作。libc++ 的等待机制（[[atomics.wait]]）对大多数类型使用**进程内**的全局等待表，另一个进程的 `notify_one` 唤醒不了它。

## 实现视角

!!! impl "16 字节原子与运行期检测"
    在 Apple Silicon 上，16 字节原子可以无条件使用 ARMv8.1 的 LSE（`casp` 系列）和 ARMv8.4 的 LSE2（对齐 16 字节的 `ldp`/`stp` 是单拷贝原子），所以 `is_always_lock_free` 为 `true`；上例中 `atomic<P2>::load()` 编译为一条 `ldp`，`compare_exchange_strong` 编译为 `caspal`。在 x86-64 上，16 字节原子需要 `cmpxchg16b` 指令，并非所有 x86-64 CPU 都有，各编译器与运行库对这种情况的处理（编译期假定、运行期检测或一律报告"非无锁"）不尽相同。

## 小结

- 宏：0 从不、1 有时、2 总是；可在预处理期使用。
- 同一类型的所有原子对象无锁性质相同（每次执行内）；`atomic_ref` 的性质可能与 `atomic` 不同。
- 宿主实现至少有一对总是无锁的有符号/无符号整数原子类型。
- 非无锁的原子操作"可能阻塞"，影响信号处理函数与弱前进保证代理中的可用性。
- address-free 是推荐做法，是进程间共享原子变量的前提。
