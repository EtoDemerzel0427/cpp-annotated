---
title: 原子操作
summary: 第 32.5 节的入口：什么是原子对象，<atomic> 声明了什么，atomic_xxx 非成员函数和 <stdatomic.h> 怎样让同一份头文件同时被 C 和 C++ 编译，以及 atomic_signed_lock_free 别名。
status: done
covers: atomics.general, atomics.syn, atomics.alias, atomics.nonmembers, stdatomic.h.syn
related: intro.races, atomics.order, atomics.types.generic, atomics.ref.generic, atomics.flag, atomics.fences, atomics.wait, atomics.lockfree, depr.atomics
tags: 标准库, 原子操作, 内存模型
updated: 2026-10-19
---

!!! tldr
    - 原子对象指 `atomic<T>`、`atomic_flag` 的对象，以及被某个 `atomic_ref` 引用期间的对象。只通过原子操作访问它们，永远不会构成数据竞争，但它们的初始化不是原子操作。
    - `atomic_fetch_add(&a, 1)` 这类非成员函数与成员函数完全等价，它们存在是为了让 C 和 C++ 共用代码。
    - C++ 的 `<stdatomic.h>` 把 `_Atomic(T)` 定义成 `std::atomic<T>`，并把 C 的名字引入全局命名空间；C 与 C++ 原子对象表示兼容只是推荐做法。
    - `atomic_signed_lock_free` 和 `atomic_unsigned_lock_free` 命名一个总是无锁、而且等待/通知最高效的整数原子类型。

## 原子对象 [atomics.general]

[[intro.races]] 规定，两个线程冲突地访问同一内存位置，如果至少一个访问不是原子的，而且两者之间没有 happens before，就构成数据竞争，整个程序的行为未定义。所以要让多个线程不加锁地共享一个变量，必须使用原子对象和原子操作。

¶2 本节描述细粒度原子访问的组件，这种访问通过对**原子对象**（atomic object）的操作提供。原子对象有两种来源：

- `atomic<T>` 和 `atomic_flag` 类型的对象；
- 被 `atomic_ref` 引用的普通对象，在这个 `atomic_ref` 的生命周期内是原子对象（[[atomics.ref.generic#1]]）。

对原子对象的所有访问都通过原子操作进行，就不会有数据竞争。唯一的例外是初始化：[[atomics.types.operations#2]] 规定原子对象的初始化不是原子操作，把刚构造好的对象的地址通过 relaxed 原子操作交给另一个线程，那个线程立即访问它，仍然可能与构造发生竞争。

¶1 定义了一个仅说明用的别名 *COPYCV*`(FROM, TO)`，表示给 `TO` 加上 `FROM` 的顶层 cv 限定，用于 `atomic_ref<const T>::address()` 这类需要保留 cv 的返回类型。

本章其余各节：

| 页面 | 内容 |
|---|---|
| [[atomics.order]] | `memory_order` 的语义：release/acquire、单一全序 S、读-改-写 |
| [[atomics.lockfree]] | `ATOMIC_*_LOCK_FREE`、`is_always_lock_free`、跨进程共享 |
| [[atomics.wait]] | `wait`、`notify_one`、`notify_all` |
| [[atomics.ref.generic]] | `atomic_ref<T>` |
| [[atomics.types.generic]] | `atomic<T>` 及其整数、浮点、指针特化 |
| [[util.smartptr.atomic]] | `atomic<shared_ptr<T>>`、`atomic<weak_ptr<T>>` |
| [[atomics.flag]] | `atomic_flag` |
| [[atomics.fences]] | `atomic_thread_fence`、`atomic_signal_fence` |

## `<atomic>` 里有什么 [atomics.syn]

`<atomic>` 的概要标注为 mostly freestanding：除了标为 hosted 的 `atomic_signed_lock_free` 和 `atomic_unsigned_lock_free`，其余内容在独立实现（freestanding，可以没有操作系统支持的实现）中也必须提供。它声明了：

- `enum class memory_order` 和 `memory_order_relaxed` 等五个内联常量。`memory_order` 从 C++20 起是作用域枚举，这些常量为了兼容旧代码和 C 而保留。`memory_order_consume` 不在这里，它在附录 D（[[depr.atomics]]）。
- `ATOMIC_BOOL_LOCK_FREE` 到 `ATOMIC_POINTER_LOCK_FREE` 共 11 个宏（[[atomics.lockfree]]）。
- 类模板 `atomic_ref`、`atomic` 和偏特化 `atomic<T*>`。
- 一组 `atomic_xxx`、`atomic_xxx_explicit` 非成员函数模板，每个都有接受 `volatile atomic<T>*` 和 `atomic<T>*` 的两个重载。
- `atomic_bool` 到 `atomic_uintmax_t` 等类型别名，`atomic_flag` 及其非成员函数，`ATOMIC_FLAG_INIT`。
- 栅栏函数 `atomic_thread_fence`、`atomic_signal_fence`，声明为 `extern "C"`，这样 C 和 C++ 用的是同一个实体，`<stdatomic.h>` 才能用 using 声明引入它们。

非成员函数中表示值的形参写作 `typename atomic<T>::value_type` 而不是 `T`。这是有意的：`::` 左边的部分是非推导语境，`T` 只从第一个实参推导。所以 `atomic<long> a; atomic_store(&a, 1);` 能编译，`1` 被隐式转换成 `long`；如果形参写成 `T`，两个实参分别推导出 `long` 和 `int`，推导失败。

几乎所有原子操作都声明为 `constexpr`，这是 C++23 之后的新措辞（[[P3309R3]]）。常量求值中没有并发，原子操作就是普通的读写，于是 `constexpr` 函数里可以使用 `atomic<T>`。

!!! impl "libc++ 尚未实现 constexpr 原子操作"
    Clang 23 自带的 libc++ 中，`atomic<T>` 的 `load`、`fetch_add` 等成员不是 `constexpr` 的，在常量表达式中调用它们会报错。

## 非成员函数 [atomics.nonmembers]

¶1 名字形如 `atomic_f` 或 `atomic_f_explicit` 的非成员函数模板调用成员函数 `f`：第一个实参作为对象，其余实参依次传给成员函数。类型为 `atomic<T>::value_type*` 的形参先解引用再传，这对应 `compare_exchange` 的 `expected`。不存在对应的成员函数时，程序非良构。

所以 `atomic_fetch_add_explicit(&a, 1, memory_order_relaxed)` 与 `a.fetch_add(1, memory_order::relaxed)` 完全等价。¶2 注 1 说明了它们存在的理由：C 没有成员函数，程序员可以用这些名字写出既能作为 C 编译、也能作为 C++ 编译的代码，例如共享的头文件。

## C 兼容：`<stdatomic.h>` [stdatomic.h.syn]

```cpp run title="stdatomic-shared.cpp" ok
// 下面这段放在 C 与 C++ 共用的头文件里
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

共用的那部分在本机也能用 `clang -std=c23` 作为 C 代码编译和运行。

C11 引入了类型限定符 `_Atomic` 和头文件 `<stdatomic.h>`。C++23 起，C++ 的 `<stdatomic.h>` 提供：

- 宏 `_Atomic(T)`，展开为 `std::atomic<T>`（经过一个仅说明用的别名）；
- 全部 `ATOMIC_*_LOCK_FREE` 宏和 `ATOMIC_FLAG_INIT`；
- 一组 using 声明，把 `std::memory_order`、`memory_order_relaxed` 等常量（包括 `memory_order_consume`）、`atomic_flag`、`atomic_int` 等别名、`atomic_load` 等函数和两个栅栏函数引入全局命名空间。

¶1 每个 using 声明引入的都是 `<atomic>` 中的同一个实体，除 `_Atomic(T)` 外的宏也与 `<atomic>` 中的定义相同。`<stdatomic.h>` 是否同时在 `std` 中提供声明是未指定的。¶2 `intN_t`、`uintN_t`、`intptr_t`、`uintptr_t` 对应的 using 声明，只有在 `<atomic>` 声明了相应别名时才提供。

¶3 `_Atomic` 宏和这些全局声明只由 `<stdatomic.h>` 提供，其他 C++ 标准库头文件都不提供。

¶4 *推荐做法*：实现应当保证 C 与 C++ 的原子对象表示兼容，同一个对象既能在 C 代码中作为 `_Atomic(T)` 访问，也能在 C++ 代码中作为 `atomic<T>` 访问。这只是推荐，不是要求。

在 C++ 中 `_Atomic` 是宏，只能写成函数形式 `_Atomic(T)`。C 的限定符写法 `_Atomic int x;` 不是标准 C++。

!!! pitfall "只包含 `<atomic>` 时的 `_Atomic`"
    按 ¶3，只包含 `<atomic>` 时 `_Atomic(int)` 不应该可用。Clang 却会接受它，因为 Clang 在 C++ 中把 `_Atomic` 当作 C11 扩展关键字（`-pedantic` 下给出 `-Wc11-extensions` 警告）。这时得到的是 Clang 内建的原子类型，不是 `std::atomic<int>`，上例中的 `static_assert` 会失败。共用头文件应当包含 `<stdatomic.h>`。

## 类型别名 [atomics.alias]

¶1 `atomic_intN_t`、`atomic_uintN_t` 当且仅当 `intN_t`、`uintN_t` 存在时才声明。

¶2 `atomic_signed_lock_free` 和 `atomic_unsigned_lock_free` 分别命名某个有符号、无符号整数类型的 `atomic` 特化，它的 `is_always_lock_free` 为 `true`。注 1 说明它们在独立实现中是可选的。实现应当选择原子等待和通知操作（[[atomics.wait]]）最高效的那个整数类型。

这对别名来自 C++20 的同步库（[[P1135R6]]）。不同平台的原生等待机制支持的整数宽度不同，例如 Linux 的 futex 只支持 32 位。可移植代码需要一个等待最快的原子整数时，就用这个别名。

!!! impl "libc++ 的选择"
    libc++ 优先选择平台等待机制使用的整数类型，否则选最大的无锁整数。默认配置下，macOS 上它是 `int64_t`，所以 `atomic_signed_lock_free` 是 8 字节的 `atomic<long long>`；Linux 上是 `int32_t`，对应 `atomic<int>`（见 `<__atomic/aliases.h>`、`<__atomic/contention_t.h>`）。

## 附录 D 中的相关内容

[[depr.atomics]] 保留了几项已弃用的设施 {{deprecated}}：

- `atomic_init(obj, v)`，等价于 `atomic_store_explicit(obj, v, memory_order::relaxed)`；
- `ATOMIC_VAR_INIT(value)`，C++20 起已经不需要，因为 `atomic<T>` 的默认构造函数会值初始化；
- `memory_order::consume` 和 `kill_dependency`，`consume` 在允许 `acquire` 的地方都可以用，含义与 `acquire` 相同（见 [[atomics.order]]）；
- `volatile atomic<T>` 上的操作：正文规定这些重载只在 `is_always_lock_free` 为 `true` 时可用，附录 D 让它们在 `is_always_lock_free` 为 `false` 时也参与重载决议，但这种用法已弃用。
