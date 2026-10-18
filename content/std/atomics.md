---
title: 原子操作
summary: [atomics] 导读与公共部分——<atomic> 里有什么、"原子对象"在内存模型中的地位、类型别名与 atomic_signed_lock_free、atomic_xxx 非成员函数为何存在，以及 <stdatomic.h> 怎样让同一个头文件同时被 C 和 C++ 编译
status: done
covers: atomics.general, atomics.syn, atomics.alias, atomics.nonmembers, stdatomic.h.syn
related: intro.races, atomics.order, atomics.types.generic, atomics.ref.generic, atomics.flag, atomics.fences, atomics.wait, atomics.lockfree, depr.atomics
tags: 标准库, 原子操作, 内存模型
updated: 2026-10-18
---

[[intro.races]] 规定：两个线程冲突地访问同一内存位置，只要"至少一个不是原子的"且没有 happens before，就是数据竞争、整个程序 UB。所以"原子"是内存模型里的一个**一等概念**——而 [atomics] 就是程序员获得原子对象和原子操作的地方。

本章的页面安排：

| 页面 | 内容 |
|---|---|
| 本页 | [atomics.general]、[atomics.syn]、[atomics.alias]、[atomics.nonmembers]、C 兼容（[stdatomic.h.syn]） |
| [[atomics.order]] | `memory_order` 的精确语义：release/acquire、coherence-ordered before、单一全序 S、out-of-thin-air、原子 modify-write 操作 |
| [[atomics.lockfree]] | `ATOMIC_*_LOCK_FREE`、`is_always_lock_free`、无锁与"可能阻塞"、address-free |
| [[atomics.wait]] | 原子等待/通知：`wait`、`notify_one`、`notify_all` 的"有资格被解除阻塞"规则 |
| [[atomics.ref.generic]] | `atomic_ref<T>`：对普通对象施加原子操作 |
| [[atomics.types.generic]] | `atomic<T>` 及整数、浮点、指针特化 |
| [[util.smartptr.atomic]] | `atomic<shared_ptr<T>>`、`atomic<weak_ptr<T>>` |
| [[atomics.flag]] | `atomic_flag` |
| [[atomics.fences]] | `atomic_thread_fence`、`atomic_signal_fence` |

## 总述（[atomics.general]）

¶1 定义一个仅说明用的别名 *COPYCV*`(FROM, TO)`：把 `FROM` 的顶层 cv 限定加到 `TO` 上。它用于 `atomic_ref<const T>::address()` 这类需要保持 cv 的返回类型（[[atomics.ref.generic]]）。

¶2 本子条款描述**细粒度原子访问**的组件，这种访问通过**原子对象**上的操作提供。

"原子对象"在核心语言里没有独立定义；[[intro.races]] 只说"原子操作"。实际上，一个对象是原子对象当且仅当它是 `atomic<T>`/`atomic_flag` 类型的对象，或者在某个 `atomic_ref` 的生命周期内被它引用（[[atomics.ref.generic]] ¶1）。对原子对象的访问只要都通过原子操作进行，就永远不会构成数据竞争——但注意，原子对象的**初始化**不是原子操作（[[atomics.types.operations]] ¶2）。

## 头文件概要（[atomics.syn]）

`<atomic>` 的概要开头标注了"**mostly freestanding**"：除了标注为 hosted 的 `atomic_signed_lock_free`/`atomic_unsigned_lock_free`，其余在独立实现中也必须提供。它声明：

- `enum class memory_order` 及 `memory_order_relaxed` 等五个**内联常量**（C++20 起 `memory_order` 是作用域枚举，这些常量为了兼容旧代码与 C 而保留）。`memory_order_consume` 不在这里，它在附录 D（[[depr.atomics]]）；
- `ATOMIC_BOOL_LOCK_FREE` 到 `ATOMIC_POINTER_LOCK_FREE` 共 11 个宏（[[atomics.lockfree]]）；
- 类模板 `atomic_ref`、`atomic`，偏特化 `atomic<T*>`；
- 一大批 `atomic_xxx` / `atomic_xxx_explicit` 非成员函数模板（每个都有 `volatile atomic<T>*` 与 `atomic<T>*` 两个重载，后者是 `constexpr`）；
- 类型别名 `atomic_bool` … `atomic_uintmax_t`；
- `atomic_flag` 及其非成员函数、`ATOMIC_FLAG_INIT`；
- `extern "C"` 的 `atomic_thread_fence`、`atomic_signal_fence`。

几个值得注意的细节：

- 几乎所有操作都是 `constexpr` 的。这是 C++23 之后的新措辞：常量求值中没有并发，原子操作退化为普通读写，于是可以在 `constexpr` 函数里使用 `atomic<T>`。
- 非成员函数接受的值参数类型写作 `typename atomic<T>::value_type`，而不是 `T`。这是有意让该形参成为**非推导语境**：`atomic_store(&a, 1)` 中 `T` 只从第一个实参推导，`1` 再隐式转换。如果写成 `T`，`atomic<long> a; atomic_store(&a, 1);` 会因为两处推导结果不一致（`long` 与 `int`）而失败。
- 栅栏函数声明为 `extern "C"`：C 与 C++ 共用同一个实体（[[stdatomic.h.syn]] 的 using 声明需要这一点）。

!!! impl "libc++ 尚未实现 constexpr 原子操作"
    Clang 23 自带的 libc++ 中，`atomic<T>` 的 `load`、`fetch_add` 等成员不是 `constexpr` 的；在常量表达式里调用它们会报"不是整型常量表达式"。

## 类型别名（[atomics.alias]）

¶1 `atomic_intN_t`/`atomic_uintN_t` 当且仅当 `intN_t`/`uintN_t` 被声明时才声明。

¶2 `atomic_signed_lock_free` 与 `atomic_unsigned_lock_free` 分别命名某个**有符号/无符号整数**的 `atomic` 特化，且其 `is_always_lock_free` 为 `true`。注 1：它们在独立实现中是可选的。实现**应当**为它们选择**原子等待/通知操作（[[atomics.wait]]）最高效**的那个整数类型。

这对别名是 C++20 同步库（[[P1135R6]]）的一部分。动机：Linux 的 futex 只支持 32 位整数，其他平台的原生等待机制支持的宽度又各不相同；可移植代码如果想要"等待最快的原子整数"，就用这个别名。

!!! impl "libc++ 的选择"
    libc++ 的规则是"优先选平台等待用的 contention 类型，否则选最大的无锁整数"。macOS 上 contention 类型是 `int64_t`，所以 `atomic_signed_lock_free` 是 `atomic<long long>`（8 字节）；Linux 上是 `int32_t`，对应 `atomic<int>`。按 [[atomics.wait]] 中的分析，在默认 ABI 下 macOS 只有 8 字节的 `int64_t` 走原生等待，其他类型都要经过一张全局哈希表，所以这个选择正好符合 ¶2 的推荐。

## 非成员函数（[atomics.nonmembers]）

¶1 名字形如 `atomic_f` 或 `atomic_f_explicit` 的非成员函数模板，调用成员函数 `f`：第一个形参的值作为对象表达式，其余形参依次作为实参；类型为 `atomic<T>::value_type*` 的形参在传给成员函数时被解引用（这对应 `compare_exchange` 的 `expected`）。若不存在这样的成员函数，程序非良构。

¶2 注 1：这些非成员函数让程序员可以写出既能作为 C 也能作为 C++ 编译的代码，例如共享的头文件。

所以 `atomic_fetch_add_explicit(&a, 1, memory_order_relaxed)` 与 `a.fetch_add(1, memory_order::relaxed)` 完全等价。它们的存在价值只在于 C 兼容：C 没有成员函数，`<stdatomic.h>` 里的 C 接口就是这些名字。

## C 兼容（[stdatomic.h.syn]）

C11 引入了 `_Atomic` 类型限定符和 `<stdatomic.h>`。C++23 起，C++ 的 `<stdatomic.h>` 提供如下定义：

- 仅说明用别名 *std-atomic*`<T>` 即 `std::atomic<T>`，宏 `_Atomic(T)` 展开为 *std-atomic*`<T>`；
- 所有 `ATOMIC_*_LOCK_FREE` 宏与 `ATOMIC_FLAG_INIT`；
- 一组 **using 声明**把 `std::memory_order`、`memory_order_relaxed`……、`atomic_flag`、`atomic_int` 等别名、`atomic_load`/`atomic_fetch_add` 等函数、两个栅栏函数引入全局命名空间。包括 `memory_order_consume`。

¶1 每个 using 声明引入与 `<atomic>` 中 `std::A` **同一个实体**；`_Atomic(T)` 以外的宏与 `<atomic>` 中的定义相同。`<stdatomic.h>` 是否同时在 `std` 中提供声明未指定。

¶2 `intN_t`、`uintN_t`、`intptr_t`、`uintptr_t` 对应的 using 声明仅在实现于 [atomics.syn] 声明了对应别名时才有。

¶3 `_Atomic` 宏和这些全局声明，**只**由 `<stdatomic.h>` 提供，其他 C++ 标准库头文件都不提供。

¶4 *推荐做法*：实现应当保证 C 与 C++ 的原子对象表示兼容，使得同一个对象可以在 C 代码中作为 `_Atomic(T)`、在 C++ 代码中作为 `atomic<T>` 访问——表示应相同，保证原子性与内存序的机制也应兼容。

注意 ¶4 只是"推荐"。另外，C++ 里 `_Atomic` 是一个**宏**，只支持函数式的 `_Atomic(T)` 写法；C 的限定符写法 `_Atomic int x;` 在 C++ 中不可用。

```cpp run title="stdatomic-shared.cpp" ok
// 下面这段放在一个 C 与 C++ 共用的头文件里
#include <stdatomic.h>
typedef struct { _Atomic(int) hits; } counter;
static inline void bump(counter* c) {
  atomic_fetch_add_explicit(&c->hits, 1, memory_order_relaxed);
}

// C++ 侧
#include <type_traits>
static_assert(std::is_same_v<_Atomic(int), std::atomic<int>>);
int main() {
  counter c{};
  bump(&c);
  return atomic_load(&c.hits) == 1 ? 0 : 1;
}
```

同样的头文件用 `clang -std=c23` 作为 C 编译也能通过（`bump` 部分）。

!!! pitfall "同一程序中混用 <atomic> 和 <stdatomic.h>"
    `<stdatomic.h>` 把 `atomic_int` 等名字放进全局命名空间。在 C++ 代码里同时 `using namespace std;` 并包含两个头文件，一般不会冲突（它们是同一实体），但 ¶3 规定 `_Atomic` 只有 `<stdatomic.h>` 提供——不要指望 `#include <atomic>` 之后就能用 `_Atomic(int)`。

## 附录 D 中的相关内容

[[depr.atomics]] 保留了几样已弃用的东西 {{deprecated}}：

- `atomic_init`：等价于 `atomic_store_explicit(obj, v, memory_order::relaxed)`；
- `ATOMIC_VAR_INIT(value)`：C++20 起不再需要，因为 `atomic<T>` 的默认构造函数会值初始化；
- `memory_order_consume` 与 `kill_dependency`：`consume` 等价于 `acquire`（见 [[atomics.order]]）；
- 对 `volatile atomic<T>` 的操作：在主条款里，`volatile` 重载要求 `is_always_lock_free` 为 `true`；附录 D 规定这些重载在 `is_always_lock_free` 为 `false` 时也参与重载决议，但已弃用。

## 小结

- "原子对象"：`atomic<T>`、`atomic_flag` 的对象，或被 `atomic_ref` 引用期间的对象。只通过原子操作访问它们不构成数据竞争；初始化本身不是原子操作。
- `atomic_xxx` 非成员函数与成员函数完全等价，只为 C 兼容存在；值形参用 `value_type` 是为了不参与推导。
- `<stdatomic.h>` 让 `_Atomic(T)` 成为 `std::atomic<T>`，表示兼容只是推荐做法。
- `atomic_signed_lock_free` 选择的是"等待/通知最快"的整数类型。
