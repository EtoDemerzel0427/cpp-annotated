---
title: 无锁性质
summary: 怎样知道一个原子类型是不是真的无锁：ATOMIC_*_LOCK_FREE 宏的 0、1、2，is_always_lock_free 与 is_lock_free；不是无锁的原子操作对信号处理函数和前进保证的影响；address-free 与跨进程共享内存；附 Apple Silicon 上各类型的实测。
status: done
covers: atomics.lockfree
related: atomics, atomics.types.generic, atomics.ref.generic, intro.progress, atomics.flag, atomics.alias
tags: 标准库, 原子操作, 无锁
updated: 2026-10-19
---

!!! tldr
    - `std::atomic<T>` 对任何可平凡复制的 `T` 都可用，硬件做不到的大小由实现用锁模拟，所以原子不等于无锁。
    - 编译期用 `atomic<T>::is_always_lock_free` 或 `ATOMIC_*_LOCK_FREE` 宏（0 从不、1 有时、2 总是）查询；同一次执行中，同一类型的所有原子对象无锁性质相同。
    - 宿主实现至少有一对有符号、无符号整数原子类型总是无锁；独立实现只保证 `atomic_flag`。
    - 不是无锁的原子操作被视为可能阻塞：不能在信号处理函数里用，也不能指望它们的前进保证。
    - 在进程间共享内存里放原子对象，依据的是无锁操作应当是 address-free 的推荐，标准本身不保证跨进程原子性。

## 原子不等于无锁

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
| `long double`（在此平台与 `double` 相同） | 8 | 8 | 1 |
| `P2`（16 字节） | 16 | 16 | 1 |
| `S12`（12 字节） | 16 | 16 | 1 |
| `S32`（32 字节） | 32 | 8 | 0 |

`std::atomic<T>` 可以用于任何可平凡复制的 `T`，包括 32 字节甚至更大的结构体。硬件没有这么宽的原子指令，实现就用锁来模拟。libc++ 把 `atomic<S32>` 的操作交给编译器运行库的 `__atomic_load` 等函数，它们用一张按地址散列的锁表实现。

表中还有两点值得注意：

- `atomic<S12>` 被补齐到 16 字节、按 16 字节对齐，于是可以使用 16 字节的原子指令。[[atomics.types.generic.general#3]] 注 2 允许这样做：`atomic` 特化的表示不必与实参类型的大小和对齐相同。
- 同样是 `S12`，`atomic_ref<S12>` 的 `required_alignment` 只有 4，也不是无锁的。`atomic_ref` 不能改变被引用对象的大小，12 字节的对象没有原子指令可用。所以 `atomic_ref<T>` 与 `atomic<T>` 的无锁性质可以不同。

## 编译期查询：宏与 is_always_lock_free（¶1）

`<atomic>` 定义了 11 个宏：`ATOMIC_BOOL_LOCK_FREE`、`ATOMIC_CHAR_LOCK_FREE`、`ATOMIC_CHAR8_T_LOCK_FREE`、`ATOMIC_CHAR16_T_LOCK_FREE`、`ATOMIC_CHAR32_T_LOCK_FREE`、`ATOMIC_WCHAR_T_LOCK_FREE`、`ATOMIC_SHORT_LOCK_FREE`、`ATOMIC_INT_LOCK_FREE`、`ATOMIC_LONG_LOCK_FREE`、`ATOMIC_LLONG_LOCK_FREE`、`ATOMIC_POINTER_LOCK_FREE`。

¶1 这些宏表示对应原子类型的无锁性质，有符号和无符号变体归为一组，`atomic` 模板对应的特化和偏特化也适用。取值 0 表示从不无锁，1 表示有时无锁，2 表示总是无锁。

有时无锁这一档存在，是因为同一个二进制可能运行在不同的 CPU 上。例如早期的 x86-64 处理器没有 16 字节比较交换指令 `cmpxchg16b`。宏是预处理期常量，可以用在 `#if` 里。

`atomic<T>` 的 `static constexpr bool is_always_lock_free`（[[atomics.types.operations#4]]）为 `true`，表示这个类型的操作在所有运行环境中都无锁。注 2 说明它与对应的宏（如果有）一致。它适用于任意 `T`，宏只覆盖内建类型。

## 宿主实现至少有一个无锁整数（¶2）

¶2 在宿主实现（hosted，有操作系统支持的完整实现）上，至少有一个有符号整数类型的 `atomic` 特化连同对应的无符号类型总是无锁。

这项保证与 `atomic_signed_lock_free`、`atomic_unsigned_lock_free` 两个别名（[[atomics.alias]]）配套，可移植代码总能找到一个无锁整数。独立实现没有这项保证，那里唯一保证无锁的是 `atomic_flag`（[[atomics.flag#2]]）。

## 运行期查询（¶3）

¶3 `atomic<T>::is_lock_free()` 和 `atomic_is_lock_free` 报告对象是否无锁（[[atomics.types.operations]]）。在任何一次程序执行中，同一类型的所有原子对象查询结果相同。

后一句排除了按对象地址或对齐决定是否无锁的实现，`is_lock_free()` 实际上是类型在这次执行中的性质。`atomic_ref` 也一样，它的 `is_lock_free()` 规定为针对类型的所有对象（[[atomics.ref.ops#4]]），为此它要求被引用的对象按 `required_alignment` 对齐。

## 不是无锁的操作可能阻塞（¶4）

¶4 不是无锁的原子操作被视为可能阻塞（[[intro.progress]]）。

这句话把原子库与前进保证联系了起来。[[intro.progress#2]] 规定，定义为无锁（`atomic_flag`）或按本节被指示为无锁的原子函数，它们的执行是**无锁执行**（[[g:lock-free-execution]]）：只要只有一个线程没有阻塞在标准库函数中，这个线程中的无锁执行就必定完成。不是无锁的原子操作没有这项保证。实际后果有两个：

- 信号处理函数里，标准库调用中只有**普通无锁原子操作**（[[g:plain-lock-free-atomic-operation]]）和明确标为信号安全的函数可以使用（[[support.signal#2]]、[[support.signal#3]]）。如果信号恰好打断了一个持有内部锁的原子操作，处理函数再操作同一对象就会自己等自己。
- 只提供弱并行前进保证的执行代理中，例如 `par_unseq` 并行算法调用的元素访问函数（[[algorithms.parallel]]），使用可能阻塞的操作可能导致死锁。

## address-free 与进程间共享（¶5）

¶5 *推荐做法*：无锁的操作也应当是 address-free 的，即通过两个不同的地址对同一内存位置执行原子操作，能够原子地通信（脚注 273）。实现不应依赖任何每进程的状态。注 1 说明，这让通过在一个进程中映射多次的内存、或者两个进程共享的内存进行通信成为可能。

这是用 `mmap`、`shm_open` 把 `std::atomic` 放进共享内存的依据。只有无锁的原子类型适合这样做：用锁实现的原子操作，锁表通常在进程私有的内存里，两个进程看不到对方的锁。¶5 只是推荐，标准本身并不保证跨进程的原子性。

!!! pitfall "跨进程共享时的 `wait` 和 `notify`"
    原子对象本身是 address-free 的，不等于它的 `wait`、`notify_one` 也能跨进程工作。libc++ 的等待机制（[[atomics.wait]]）对大多数类型使用进程内的全局等待表，另一个进程的 `notify_one` 唤醒不了它。

## 实现视角

!!! impl "16 字节原子"
    Apple Silicon 支持 ARMv8.1 的 LSE（`casp` 系列指令）和 ARMv8.4 的 LSE2（16 字节对齐的 `ldp`、`stp` 是单次拷贝原子的），所以 16 字节类型的 `is_always_lock_free` 为 `true`。上例中 `atomic<P2>::load()` 用 `ldp` 实现，`compare_exchange_strong` 编译为 `caspal`。在 x86-64 上，16 字节原子需要 `cmpxchg16b`，并非所有 x86-64 处理器都有，各编译器和运行库的处理方式（编译期假定、运行期检测或一律报告不是无锁）不尽相同。
