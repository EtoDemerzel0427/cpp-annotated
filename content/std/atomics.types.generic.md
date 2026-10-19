---
title: 类模板 atomic
summary: std::atomic<T> 的规则：T 的要求、初始化不是原子操作、compare_exchange 按值表示比较、弱 CAS 的虚假失败，以及整数、浮点、指针特化的算术语义。
status: done
covers: atomics.types.generic, atomics.types.generic.general, atomics.types.operations, atomics.types.int, atomics.types.float, atomics.types.pointer, atomics.types.memop
papers: P0020R6, P0493R5
related: atomics, atomics.order, atomics.lockfree, atomics.wait, atomics.ref.generic, util.smartptr.atomic, depr.atomics, basic.types.general
tags: 标准库, 原子操作, atomic, CAS
updated: 2026-10-19
---

!!! tldr
    - `atomic<T>` 要求 `T` 可平凡复制、没有 cv 限定，否则程序非良构；原子对象不可复制也不可移动。
    - 构造（包括 C++20 起值初始化的默认构造）不是原子操作。把新建的原子对象交给其他线程，同样需要 release/acquire。
    - `compare_exchange` 比较的是值表示，不是 `==`：`+0.0` 与 `-0.0` 比较不等，填充位按标准应当被忽略。
    - 整数原子算术按回绕计算，`INT_MAX` 加 1 得到 `INT_MIN`，没有 UB；指针原子算术越界得到确定的地址，也没有 UB。
    - `a = a + 1` 是一次 load 加一次 store，不是原子的；用 `++a`、`a += 1` 或 `fetch_add`。

## 主模板 [atomics.types.generic.general]

`std::atomic<T>` 的主模板对任何可平凡复制的 `T` 提供 `load`、`store`、`exchange`、`compare_exchange`、`wait`/`notify`。整数、浮点、指针特化再加上算术操作；`shared_ptr`/`weak_ptr` 的偏特化见 [[util.smartptr.atomic]]。

每个操作都有两个重载：一个 `volatile` 的，一个非 `volatile` 且 `constexpr` 的。复制构造和复制赋值被删除，所以原子对象不可复制也不可移动。复制一个原子对象的值需要一次 load 和一次 store，两步合起来不是原子的，标准不让它看起来像是原子的。

### T 的要求（¶1）

```cpp title="atomic-requirements.cpp" error
#include <atomic>
#include <string>
std::atomic<std::string> s;    // error：不可平凡复制（¶1.1）
std::atomic<const int> c{0};   // error：T 有 cv 限定（¶1.6）
```

¶1 `T` 要满足 *Cpp17CopyConstructible* 和 *Cpp17CopyAssignable*。下列任何一个为 `false`，程序非良构 {{ill-formed}}：`is_trivially_copyable_v<T>`、`is_copy_constructible_v<T>`、`is_move_constructible_v<T>`、`is_copy_assignable_v<T>`、`is_move_assignable_v<T>`、`is_same_v<T, remove_cv_t<T>>`。

可平凡复制是核心要求：原子操作在实现上就是对对象表示的 `memcpy` 和 `memcmp`（见下文 CAS 的注 4），只有可平凡复制的类型能这样处理。最后一条禁止 `atomic<const int>` 和 `atomic<volatile int>`；需要 volatile 时写 `volatile atomic<int>`。

libc++ 对第一行用 `static_assert` 报告 `std::atomic<T> requires that 'T' be a trivially copyable type`；第二行的错误来自内部使用的 `_Atomic(const int)`。

¶1 的注 1 提醒，不能静态初始化的类型实参可能很难用。¶2 `atomic<bool>` 是标准布局结构体，析构函数平凡。¶3 注 2：`atomic` 特化的大小和对齐不必与 `T` 相同，例如 12 字节的结构体，`atomic` 版本在 Apple Silicon 上是 16 字节（[[atomics.lockfree]]）。

## 构造不是原子操作 [atomics.types.operations]

¶1–¶2 默认构造函数用 `T()` 初始化，也就是值初始化，所以 `std::atomic<int> a;` 的值是 0。这是 C++20 的变化。C++17 及以前默认构造是平凡的，局部的 `a` 值不确定，必须再用 `atomic_init` 或 `ATOMIC_VAR_INIT` 初始化，这两者现在已弃用（[[depr.atomics]]）。

¶3 `atomic(T desired)` 用 `desired` 初始化。两个构造函数都明确说明：初始化不是原子操作。¶3 的注 1 给了一个具体陷阱：

```cpp title="construction-race.cpp" ub
#include <atomic>
#include <thread>
std::atomic<std::atomic<int>*> slot{nullptr};
int main() {
  std::thread t([] {
    std::atomic<int>* p;
    while (!(p = slot.load(std::memory_order::relaxed))) {}
    p->fetch_add(1);   // UB：与 *p 的构造构成数据竞争
  });
  auto* a = new std::atomic<int>(0);
  slot.store(a, std::memory_order::relaxed);
  t.join();
  delete a;
}
```

用 relaxed 操作把刚构造的原子对象的地址交给另一个线程，接收方立即访问它，这次访问与构造之间没有 happens before，是未定义行为。ThreadSanitizer 对这个程序报告 `data race`。把 `slot` 上的 store 改成 `release`、load 改成 `acquire` 就修好了：原子对象也要像普通数据一样被正确发布。

## 读写与交换（¶4–¶20）

¶4 `is_always_lock_free` 和 ¶5 `is_lock_free()` 查询是否无锁，详见 [[atomics.lockfree]]。

| 操作 | 段落 | 内存序前置条件 | 要点 |
|---|---|---|---|
| `store(desired, order)` | ¶6–¶8 | `relaxed`、`release`、`seq_cst` | |
| `operator=(desired)` | ¶9–¶11 | | 等价于 `store(desired)`，返回 `desired` 这个值，不返回引用 |
| `load(order)` | ¶12–¶15 | `relaxed`、`acquire`、`seq_cst` | |
| `operator T()` | ¶16–¶17 | | 等价于 `return load();` |
| `exchange(desired, order)` | ¶18–¶20 | | 原子读-改-写操作，返回旧值 |

`operator=` 返回值而不是引用，所以 `a = b = 5;` 中 `a` 得到的是 5，不会再去读一次 `b`。

每个 `volatile` 重载都有同一条 *Constraints*：`is_always_lock_free` 为 `true`（¶6、¶9、¶12 等）。也就是说，可能用锁实现的原子类型，其 `volatile` 版本不参与重载决议。`volatile` 原子对象的典型用途是与信号处理函数或内存映射硬件通信，基于锁的实现在这些场合本来就靠不住。附录 [[depr.atomics]] 保留了旧行为：这些重载在 `is_always_lock_free` 为 `false` 时也参与重载决议，但已弃用。

## compare_exchange（¶21–¶28）

### 基本语义

¶23 `compare_exchange_strong(expected, desired, success, failure)` 先取出 `expected` 的值，然后原子地比较 `*this` 的值表示与它是否相等：

- 相等：用 `desired` 替换，内存受 `success` 影响，这是一次原子读-改-写操作；
- 不等：把读到的值写回 `expected`，内存受 `failure` 影响，这是一次原子 load。

只给一个内存序参数时，`success` 就是它，`failure` 由它推导：`acq_rel` 换成 `acquire`，`release` 换成 `relaxed`。¶22 要求 `failure` 只能是 `relaxed`、`acquire` 或 `seq_cst`。

¶25 注 4 说明，对没有填充位的对象，`compare_exchange_strong` 的效果如同：

```cpp
if (memcmp(this, &expected, sizeof(*this)) == 0)
  memcpy(this, &desired, sizeof(*this));
else
  memcpy(&expected, this, sizeof(*this));
```

### 只在失败时写 expected

标准的例 2 是链表头插入，直接把 `p->next` 当作 `expected`：

```cpp
do {
  p->next = head;                                   // 新节点指向当前头
} while (!head.compare_exchange_weak(p->next, p));  // 尝试插入
```

成功时 `p` 已经被发布出去，其他线程随时可能读 `p->next`。如果 CAS 成功后还要写 `expected`（也就是 `p->next`），这次写入就会与它们的读取构成数据竞争。只在失败时写回，就避免了这个问题。

### 弱 CAS 与虚假失败（¶26–¶27）

¶27 `compare_exchange_weak` 可以**虚假失败**：值表示相等时也可能返回 `false`。注 5 解释，这样在 LL/SC（load-linked/store-conditional）架构上也能实现 CAS。结果是 weak 版本几乎总是写在循环里：

```cpp
expected = current.load();
do {
  desired = function(expected);
} while (!current.compare_exchange_weak(expected, desired));
```

已经在循环里时，weak 版本在某些平台上更快；如果用 weak 需要循环而 strong 不需要，就用 strong。¶26 建议实现：值没变、也没有并发修改时，weak CAS 不应该一直失败。

### 按值表示比较的后果（¶28）

¶28 的三个注说明了按值表示比较带来的结果。

注 6：值相等不等于表示相等。IEC 60559 浮点中，`-0.0` 与 `+0.0` 用 `==` 相等但 `memcmp` 不等；载荷相同的 NaN 用 `memcmp` 相等但 `==` 不等。

```cpp run title="cas-float-zero.cpp" ok
#include <atomic>
#include <cstdio>
int main() {
  std::atomic<double> d{+0.0};
  double expected = -0.0;   // == +0.0，但位模式不同
  bool ok = d.compare_exchange_strong(expected, 1.0);
  std::printf("%d %g\n", ok, expected);   // 0 0
}
```

CAS 失败，`expected` 被改写为 `+0.0`。

注 7：从不参与值表示的填充位被忽略。所以标准断言下面的 CAS 一定成功，不会因为 `expected` 的填充字节是垃圾而失败：

```cpp run title="cas-padding.cpp" ok
#include <atomic>
#include <cstdio>
struct padded {
  char clank = 0x42;
  // 这里有填充
  unsigned biff = 0xC0DEFEFE;
};
std::atomic<padded> pad = {};
bool zap() {
  padded expected, desired{0, 0};
  return pad.compare_exchange_strong(expected, desired);
}
int main() { std::printf("%d\n", zap()); }   // 标准要求打印 1
```

注 8：union 的某些位只参与部分成员的值表示时，CAS 可能永远失败，因为当前活跃成员不使用的位的值不确定。

!!! impl "libc++ 的 atomic<T> 没有忽略填充位"
    用 Clang 23 + libc++ 在 Apple Silicon 上编译 `cas-padding.cpp`：`-O2` 时打印 `1`，`-O0` 时打印 `0`。`expected` 是栈上的局部变量，填充字节是残留值，libc++ 的 `atomic<T>::compare_exchange_strong` 把它们一起比较了。libc++ 只在 `atomic_ref` 中用 `__builtin_clear_padding` 清除填充位。这是实现的符合性缺陷。可移植代码最好不让带填充的类型参与 CAS，或者先用 `memset` 把 `expected` 和初值清零。

### wait 与 notify（¶29–¶38）

`wait(old, order)` 反复 load 并按值表示与 `old` 比较，相等则阻塞；`notify_one`、`notify_all` 解除有资格的等待者。规则见 [[atomics.wait]]。

## 整数特化 [atomics.types.int]

¶1 每种字符类型、每种标准整数类型，以及 `<cstdint>` 中 typedef 用到的其他类型（可能是扩展整数类型）都有特化。注 1：`atomic<bool>` 使用主模板，没有算术操作。¶2 这些特化是标准布局结构体，析构函数平凡；`difference_type` 就是 `value_type`。

¶4–¶9 `fetch_add`、`fetch_sub`、`fetch_and`、`fetch_or`、`fetch_xor`、`fetch_max`、`fetch_min` 是原子读-改-写操作，返回修改前的值。

!!! std
    Except for `fetch_max` and `fetch_min`, for signed integer types the result is as if the object value and parameters were converted to their corresponding unsigned types, the computation performed on those types, and the result converted back to the signed type.

¶8 规定有符号整数按对应的无符号类型计算再转回，注 2 强调计算不会产生未定义的结果。普通 `int` 溢出是 UB，原子 `int` 溢出则回绕：

```cpp run title="atomic-wrap.cpp" ok
#include <atomic>
#include <climits>
#include <cstdio>
int main() {
  std::atomic<int> a{INT_MAX};
  int old = a.fetch_add(1);
  std::printf("%d %d\n", old, a.load());   // 2147483647 -2147483648
}
```

加上 `-fsanitize=undefined` 运行，UBSan 不报告。原子算术本来就是用硬件的回绕加法实现的，标准直接承认了这一点。

¶9 `fetch_max`/`fetch_min` 如同用 `std::max`/`std::min` 计算 {{c++26}}（[[P0493R5]]）。在此之前，原子 max 只能写 CAS 循环。

¶10–¶13 `store_add` 等 `store_key` 系列 {{c++26}} 不返回值，是原子 modify-write 操作（同步要求更弱的读-改-写，[[atomics.order#12]]），内存序只能是 `relaxed`、`release`、`seq_cst`。¶14–¶15 `operator+=` 等复合赋值返回新值。

!!! impl "libc++ 尚未实现"
    Clang 23 自带的 libc++ 中，`atomic<int>` 没有 `fetch_max`、`fetch_min`（`__cpp_lib_atomic_min_max` 未定义），也没有 `store_add` 等成员。

## 浮点特化 [atomics.types.float]

¶1 每种 cv 无限定的浮点类型都有特化，由 C++20 的 [[P0020R6]] 引入。¶2 它们是标准布局结构体，析构函数平凡。

```cpp run title="atomic-float.cpp" ok
#include <atomic>
#include <cstdio>
#include <thread>
#include <vector>

int main() {
  std::atomic<double> sum{0.0};
  {
    std::vector<std::jthread> ts;
    for (int t = 0; t < 4; ++t)
      ts.emplace_back([&] {
        for (int i = 0; i < 1000; ++i)
          sum.fetch_add(0.5, std::memory_order::relaxed);
      });
  }
  std::printf("%g\n", sum.load());   // 2000
}
```

0.5 的倍数在 `double` 中精确可表示，所以结果与相加的顺序无关，总是 2000。

¶4–¶10 提供 `fetch_add`、`fetch_sub` 和六种 max/min。¶8 结果不可表示时结果未指定 {{unspec}}，但没有其他未定义行为；原子运算的浮点环境可以与调用线程的不同。¶9 的 max/min 语义与 [[atomics.ref.generic]] 的浮点特化相同：`fetch_max`/`fetch_min` 在 NaN 和有符号零上有意放宽，以便映射到硬件指令。

¶11–¶16 `store_add` 等 modify-write 版本，¶14 允许它们的算术规则与普通运算不同（注 1：允许树形归约）。¶17–¶19 `operator+=`、`operator-=` 返回新值，同样适用 ¶8 的规则。

!!! impl "浮点原子加通常不是一条指令"
    大多数硬件没有浮点原子加指令。在 Apple Silicon 上，libc++ 的 `atomic<float>::fetch_add` 在 `-O2` 下编译成 load、`fadd`、CAS 组成的循环，高争用时会反复重试。

## 指针偏特化 [atomics.types.pointer]

¶1 `atomic<T*>` 是一个偏特化，其特化都是标准布局结构体，析构函数平凡。

¶2 除常量求值外，原子指针操作若会产生在该求值语境中无效的指针值 `p`，结果改为 `reinterpret_cast<T*>(reinterpret_cast<uintptr_t>(p))`。所以原子指针的越界算术有确定的结果（只是不一定指向对象），¶9 也写明操作本身没有 UB。原因与 [[atomics.ref.generic]] 的指针特化相同：计算时用的值可能刚被另一个线程改过，不能因此产生 UB。

¶4–¶10 `fetch_add`、`fetch_sub` 的操作数是 `ptrdiff_t`，`fetch_max`、`fetch_min` 的操作数是 `T*`。¶6 要求 `T` 是完整对象类型，`void*` 和函数指针上的算术非良构。¶10 注 2：指向不同完整对象的指针用 `<` 比较不构成严格弱序，`fetch_max` 对它们没有可靠的意义。

¶11–¶14 是 `store_add` 等 modify-write 版本，¶15–¶16 是 `operator+=`、`operator-=`。

## 自增自减 [atomics.types.memop]

| 运算符 | 等价于 | 返回 |
|---|---|---|
| `a++` | `fetch_add(1)` | 旧值 |
| `a--` | `fetch_sub(1)` | 旧值 |
| `++a` | `fetch_add(1) + 1` | 新值 |
| `--a` | `fetch_sub(1) - 1` | 新值 |

它们都用默认的 `seq_cst`，返回的都是值。`++a` 返回的新值是在这次原子操作中算出来的，不会再读一次 `a`，其他线程随后的修改不会反映在返回值里。

## 常见误解

!!! pitfall "`a = a + 1` 是原子的"
    `a + 1` 先调用 `operator T()` 做一次 load，再由 `operator=` 做一次 store，两次原子操作之间可以插入其他线程的修改，增量会丢失。用 `++a`、`a += 1` 或 `fetch_add`。

!!! pitfall "对称地写一个无锁栈的 pop"
    例 2 的 push 是正确的。对称的 pop，`while (!head.compare_exchange_weak(old, old->next))`，有两个问题：读 `old->next` 时节点可能已被另一个线程释放；还有 ABA，节点被弹出、释放、重新分配又被压回，CAS 误以为没变。解决办法是 [[saferecl]] 中的 hazard pointer 或 RCU，或者用 [[util.smartptr.atomic]] 的 `atomic<shared_ptr>`。

!!! pitfall "用浮点的 `==` 推测 CAS 的结果"
    `atomic<double>` 存着 NaN，`expected` 是同一个 NaN 位模式：`memcmp` 相等，CAS 成功，尽管 `NaN == NaN` 为假。`expected` 是另一种 NaN 位模式时则永远失败。

## 历史与演进

!!! history
    - C++11 引入 `atomic<T>`，默认构造函数是平凡的，值不确定。
    - C++20 默认构造改为值初始化；加入浮点特化（[[P0020R6]]）和 `wait`/`notify`；弃用非无锁类型上的 `volatile` 操作；CAS 明确忽略填充位。
    - C++26 加入 `fetch_max`/`fetch_min`（[[P0493R5]]）和 `store_add` 等原子 modify-write 操作。
    - C++23 之后的新措辞让大部分操作成为 `constexpr`，并给浮点特化加上了 `fmaximum` 系列。

## 思考题

!!! question "思考题 1"
    `std::atomic<int> a; int x = a;` 中 `a` 是局部变量，`x` 是多少？在 C++17 中呢？

<details markdown="1">
<summary>答案</summary>

C++20 起默认构造函数值初始化（[[atomics.types.operations#2]]），`x` 是 0。C++17 中默认构造函数是平凡的，局部的 `a` 值不确定，读取它是 UB；静态存储期的 `a` 则会被零初始化。
</details>

!!! question "思考题 2"
    `compare_exchange` 为什么只在失败时写 `expected`？

<details markdown="1">
<summary>答案</summary>

见例 2：成功时 `expected` 可能是刚被发布的对象的一部分（`p->next`）。如果成功后还写它，这次写入发生在发布之后，会与看到 `p` 的其他线程对 `p->next` 的读取构成数据竞争。`atomic<shared_ptr>` 的规定写得更直接：成功时，原子更新之后不再访问 `expected`（[[util.smartptr.atomic]]）。
</details>
