---
title: 类模板 atomic
summary: atomic<T> 逐条精读——T 的要求（可平凡复制、不能有 cv）、值初始化的默认构造、"初始化不是原子操作"、volatile 重载的约束、compare_exchange 按值表示比较（填充位、±0.0、union）、弱 CAS 的虚假失败；整数特化的回绕语义与 fetch_max、浮点特化、指针特化的无效指针规则；libc++ 在填充位上的不一致
status: done
covers: atomics.types.generic, atomics.types.generic.general, atomics.types.operations, atomics.types.int, atomics.types.float, atomics.types.pointer, atomics.types.memop
papers: P0020R6, P0493R5
related: atomics, atomics.order, atomics.lockfree, atomics.wait, atomics.ref.generic, util.smartptr.atomic, depr.atomics, basic.types.general
tags: 标准库, 原子操作, atomic, CAS
updated: 2026-10-18
---

`std::atomic<T>` 是原子操作的主力。主模板对任何可平凡复制的 `T` 提供 `load`、`store`、`exchange`、`compare_exchange`、`wait`/`notify`；整数、浮点、指针特化再加上算术操作。`shared_ptr`/`weak_ptr` 的偏特化另见 [[util.smartptr.atomic]]。

本页覆盖 [atomics.types.generic] 的前六个子条款：概述、操作、整数特化、浮点特化、指针偏特化、整数与指针共用的成员运算符。

## 主模板（[atomics.types.generic.general]）

类定义里每个操作都有两个重载：一个 `volatile`（非 `constexpr`），一个非 `volatile`（`constexpr`）。复制构造与复制赋值被删除，**原子对象不可复制也不可移动**——复制一个原子对象的"值"需要一次 load 和一次 store，这两步合起来不是原子的，标准拒绝假装它是。

¶1 `T` 必须满足 *Cpp17CopyConstructible* 与 *Cpp17CopyAssignable*。以下任何一个为 `false` 时，程序非良构 {{ill-formed}}：

- ¶1.1 `is_trivially_copyable_v<T>`
- ¶1.2 `is_copy_constructible_v<T>`
- ¶1.3 `is_move_constructible_v<T>`
- ¶1.4 `is_copy_assignable_v<T>`
- ¶1.5 `is_move_assignable_v<T>`
- ¶1.6 `is_same_v<T, remove_cv_t<T>>`

可平凡复制是核心要求：原子操作在实现上就是对对象表示的 `memcpy`/`memcmp`（见下文 CAS 的注 4），只有可平凡复制的类型才能这样处理。¶1.6 禁止 `atomic<const int>` 和 `atomic<volatile int>`——常量的原子对象没有意义，`volatile atomic<int>` 才是正确写法。

注 1：不能静态初始化的类型实参可能很难使用（原子对象的初始化不是原子操作，静态初始化能避免初始化与使用之间的竞争）。

```cpp title="atomic-requirements.cpp" error
#include <atomic>
#include <string>
std::atomic<std::string> s;      // error：string 不可平凡复制（¶1.1）
std::atomic<const int> c{0};     // error：T 带 cv 限定（¶1.6）
```

libc++ 对前者以 `static_assert` 报 "std::atomic<T> requires that 'T' be a trivially copyable type"；对后者，错误来自内部使用的 `_Atomic(const int)`。

¶2 `atomic<bool>` 是标准布局结构体，析构函数平凡。¶3 注 2：`atomic` 特化的表示不必与其实参类型有相同的大小和对齐（实测见 [[atomics.lockfree]]：12 字节的结构体，`atomic` 版本是 16 字节）。

## 操作（[atomics.types.operations]）

### 构造：初始化不是原子操作（¶1–¶3）

¶1–¶2 默认构造函数（*Constraints*：`T` 可默认构造）：用 `T()` 的值初始化原子对象，即**值初始化**。初始化不是原子操作。

这是 C++20 的变化：C++17 及以前，`std::atomic<int> a;` 是**默认初始化**，`a` 的值不确定，必须再用 `atomic_init` 或 `ATOMIC_VAR_INIT` 初始化。现在 `std::atomic<int> a;` 的值就是 0，那两个工具也随之被弃用（[[depr.atomics]]）。

¶3 `constexpr atomic(T desired)`：用 `desired` 初始化，同样**不是原子操作**。注 1 举了一个陷阱：

!!! std
    It is possible to have an access to an atomic object A race with its construction, for example by communicating the address of the just-constructed object A to another thread via `memory_order::relaxed` operations on a suitable atomic pointer variable, and then immediately accessing A in the receiving thread. This results in undefined behavior.

    可能出现对原子对象 A 的访问与 A 的构造竞争：例如用 relaxed 操作把刚构造好的 A 的地址传给另一个线程，接收线程立即访问 A。这是未定义行为。

```cpp title="construction-race.cpp" ub
#include <atomic>
#include <thread>
std::atomic<std::atomic<int>*> slot{nullptr};
int main() {
  std::thread t([] {
    std::atomic<int>* p;
    while (!(p = slot.load(std::memory_order::relaxed))) {}
    p->fetch_add(1);          // UB：与 *p 的构造（非原子）构成数据竞争
  });
  auto* a = new std::atomic<int>(0);
  slot.store(a, std::memory_order::relaxed);   // 改为 release / acquire 即可修复
  t.join();
  delete a;
}
```

"它是原子对象"不能保护它自己的初始化。发布指针时要用 release/acquire，就像发布任何普通数据一样。

### 无锁查询（¶4–¶5）

¶4 `is_always_lock_free`：类型的操作总是无锁时为 `true`；注 2：与对应的 `ATOMIC_..._LOCK_FREE` 宏一致。¶5 `is_lock_free()`：对象的操作无锁时返回 `true`；注 3：与同一类型的 `is_always_lock_free` 一致。详见 [[atomics.lockfree]]。

### volatile 重载的约束

每个操作的 `volatile` 重载都有同一条 *Constraints*：`is_always_lock_free` 为 `true`（如 ¶6、¶9、¶12……）。即：对**可能用锁实现**的原子类型，`volatile` 版本在主条款里不参与重载决议。`volatile` 原子对象的典型用途是与信号处理函数或内存映射硬件通信，基于锁的实现在这些场合本来就不可靠。C++20 弃用了非无锁类型上的 `volatile` 原子操作；现行草案在主条款里把它写成约束，并在附录 D 中保留旧行为（这些重载在 `is_always_lock_free` 为 `false` 时也参与重载决议，但已弃用，见 [[depr.atomics]]）。

### store、load、exchange（¶6–¶20）

- ¶6–¶8 `store(desired, order)`：*Preconditions* `order` 是 `relaxed`、`release` 或 `seq_cst`；原子地替换值；内存受 `order` 影响（[[atomics.order]]）。
- ¶9–¶11 `operator=(desired)`：等价于 `store(desired)`，**返回 `desired`**（值，不是 `*this` 的引用）。所以 `a = b = 5;` 中 `a` 被赋予的是 5，不是重新读取 `b`。
- ¶12–¶15 `load(order)`：*Preconditions* `relaxed`、`acquire` 或 `seq_cst`；原子地返回值。
- ¶16–¶17 `operator T()`：等价于 `return load();`。
- ¶18–¶20 `exchange(desired, order)`：原子地替换并返回旧值；是**原子读-改-写操作**。

### compare_exchange（¶21–¶28）

¶22 *Preconditions*：`failure` 是 `relaxed`、`acquire` 或 `seq_cst`。

¶23 *Effects*：取出 `expected` 的值，然后**原子地**比较 `*this` 的**值表示**与之是否相等；相等则用 `desired` 替换。仅当比较为真时，内存受 `success` 影响；为假时受 `failure` 影响。只给一个内存序参数时，`success` 就是它，`failure` 也是它，但 `acq_rel` 替换为 `acquire`、`release` 替换为 `relaxed`。仅当比较为假时，原子操作之后，`expected` 被替换为比较时读到的值。返回 `true` 时是原子读-改-写操作，否则是原子 load 操作。

¶24 返回比较结果。¶25 注 4：对没有填充位的对象，`compare_exchange_strong` 的效果是

```cpp
if (memcmp(this, &expected, sizeof(*this)) == 0)
  memcpy(this, &desired, sizeof(*this));
else
  memcpy(&expected, this, sizeof(*this));
```

例 1 是标准的 CAS 循环：

```cpp
expected = current.load();
do {
  desired = function(expected);
} while (!current.compare_exchange_weak(expected, desired));
```

例 2 说明"只在失败时更新 `expected`"的好处——链表头插入时可以直接把 `p->next` 当作 `expected`：

```cpp
do {
  p->next = head;                                   // 新节点指向当前头
} while (!head.compare_exchange_weak(p->next, p));  // 尝试插入
```

成功时 `expected`（即 `p->next`）**不会被写入**，所以不会与其他线程随后对 `p` 的访问产生数据竞争——成功之后 `p` 已经发布出去了。

¶26 *推荐做法*：weak CAS 不应**一直**返回 `false`，除非值确实与 `expected` 不同或有并发修改。

¶27 *Remarks*：weak CAS 可以**虚假失败**：值表示相等时也可能返回 `false`，并把原值写回 `expected`。注 5：这使得在 LL/SC（load-linked/store-conditional）机器上也能实现 CAS；后果是几乎所有 weak CAS 都写在循环里。在循环中 weak 版本在某些平台上更快；若 weak 版本需要循环而 strong 版本不需要，应选 strong。

### 按值表示比较的后果（¶28 的三个注）

注 6：比较的是值表示，所以对于有陷阱位或"同一值的不同表示"的类型，`operator==` 相等的值 CAS 可能失败。在 IEC 60559 浮点中：`-0.0` 与 `+0.0` 用 `memcmp` 不等但 `==` 相等；有相同载荷的 NaN 用 `memcmp` 相等但 `==` 不等。

```cpp run title="cas-float-zero.cpp" ok
#include <atomic>
#include <cstdio>
int main() {
  std::atomic<double> d{+0.0};
  double expected = -0.0;                      // -0.0 == +0.0，但位模式不同
  bool ok = d.compare_exchange_strong(expected, 1.0);
  std::printf("%d %g\n", ok, expected);        // "0 0"：比较失败，expected 被改写为 +0
}
```

注 7：CAS 作用于对象的值表示，所以**从不参与值表示的填充位被忽略**。因此标准断言下面的代码"保证不会虚假失败"：

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
  return pad.compare_exchange_strong(expected, desired);   // 标准：必定成功
}
int main() { std::printf("%d\n", zap()); }
```

注 8：对于 union，某些位参与一部分成员的值表示而不参与另一部分时，CAS 可能**永远**失败：当前活跃成员不使用的那些位的值是不确定的。

```cpp
union pony {
  double celestia = 0.;
  short luna;       // 有填充
};
atomic<pony> princesses = {};
bool party(pony desired) {
  pony expected;
  return princesses.compare_exchange_strong(expected, desired);   // 不保证会成功
}
```

!!! impl "libc++ 没有忽略 atomic<T> 的填充位"
    按注 7，`cas-padding.cpp` 必须打印 `1`。用 Clang 23 + libc++ 在 Apple Silicon 上编译：`-O2` 时打印 `1`，**`-O0` 时打印 `0`**——`expected` 是栈上的局部变量，其填充字节是残留的垃圾值，libc++ 的 `atomic<T>::compare_exchange_strong` 直接逐字节比较了它们。libc++ 只在 `atomic_ref` 中用 `__builtin_clear_padding` 清除填充位，`atomic<T>` 中没有。这是实现的一致性缺陷；可移植代码最好避免让带填充的类型参与 CAS，或者用 `memset` 预先把 `expected` 和初值都清零。

### wait 与 notify（¶29–¶38）

`wait(old, order)`（¶29–¶32）：反复执行"`load(order)` 并按值表示与 `old` 比较，不等则返回，相等则阻塞直到被通知或虚假解除阻塞"；是原子等待操作。`notify_one`（¶33–¶35）、`notify_all`（¶36–¶38）：解除有资格的等待操作的阻塞。规则详见 [[atomics.wait]]。

## 整数特化（[atomics.types.int]）

¶1 每种**字符类型**、每种**标准整数类型**、以及 `<cstdint>` 中的 typedef 需要的其他类型（即可能的扩展整数类型），都有 `atomic` 特化。注 1：`atomic<bool>` 使用主模板，没有算术操作。

¶2 都是标准布局结构体，析构函数平凡。特化中 `difference_type` 是 `value_type`。

¶4 表 155 给出 key 与运算的对应：`add`(+)、`sub`(−)、`and`(&)、`or`(|)、`xor`(^)、`max`、`min`。

¶5–¶9 `fetch_key(operand, order)`：原子 RMW，返回修改前的值。

!!! std
    Except for `fetch_max` and `fetch_min`, for signed integer types the result is as if the object value and parameters were converted to their corresponding unsigned types, the computation performed on those types, and the result converted back to the signed type.

    除 `fetch_max`、`fetch_min` 外，对有符号整数类型，结果如同把对象值和参数转换为对应的无符号类型计算、再把结果转换回有符号类型。

注 2：**计算不会产生未定义的结果**。`atomic<int>{INT_MAX}.fetch_add(1)` 有定义，结果是 `INT_MIN`——与普通 `int` 溢出是 UB 不同。原子算术本来就是用硬件的回绕加法实现的，标准直接承认了这一点。

¶9 `fetch_max`/`fetch_min` 如同用 `std::max`/`std::min` 计算 {{c++26}}（[[P0493R5]]）。在此之前，原子 max 只能写 CAS 循环。

¶10–¶13 `store_key`：同样的运算，但是**原子 modify-write 操作**（[[atomics.order#12]]）{{c++26}}：返回 `void`，`order` 只能是 `relaxed`/`release`/`seq_cst`。

¶14–¶15 `operator op=`：等价于 `return fetch_key(operand) op operand;`，即返回**新值**。

!!! impl "libc++ 尚未实现"
    Clang 23 自带的 libc++：`atomic<int>` 没有 `fetch_max`、`fetch_min`（`__cpp_lib_atomic_min_max` 未定义），也没有 `store_add` 等成员。

## 浮点特化（[atomics.types.float]） {{c++20}}

¶1 每种 **cv 无限定的浮点类型**都有特化（[[P0020R6]] 引入，C++20）。¶2 标准布局，平凡析构。

¶4–¶10 `fetch_add`、`fetch_sub`、`fetch_max`、`fetch_min`、`fetch_fmaximum`、`fetch_fminimum`、`fetch_fmaximum_num`、`fetch_fminimum_num`。¶8：结果不可表示时结果未指定 {{unspec}}，但没有其他未定义行为；运算应当遵循 `numeric_limits` 描述的性质；**原子运算的浮点环境可以与调用线程的不同**。¶9 给出各种 max/min 的语义（与 [[atomics.ref.generic]] 中的浮点特化相同：`fetch_max`/`fetch_min` 在 NaN 与有符号零上有意放宽，以便映射到硬件指令）。

¶11–¶16 `store_add`、`store_sub`、`store_max` 等原子 modify-write 版本；¶14 允许其算术规则不同于普通运算（注 1：允许树形归约）。

¶17–¶19 `operator+=`、`operator-=`，返回新值，同样适用 ¶8 的规则。

!!! impl "实现方式"
    大多数硬件没有浮点原子加指令。Apple Silicon 上，libc++ 的 `atomic<float>::fetch_add` 编译为 `ldr` + `fadd` + `cas` 的循环（`-O2`）。所以浮点原子加不是"一条指令"，在高争用下会反复重试。

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
      ts.emplace_back([&] { for (int i = 0; i < 1000; ++i) sum.fetch_add(0.5, std::memory_order::relaxed); });
  }
  std::printf("%g\n", sum.load());   // 2000：0.5 的倍数在 double 中精确可表示，加法顺序无关
}
```

## 指针偏特化（[atomics.types.pointer]）

¶1 有一个针对指针的偏特化 `atomic<T*>`；其特化都是标准布局、平凡析构。

¶2 与 `atomic_ref` 相同的规则：**除常量求值外**，原子指针操作若会产生在该求值语境中无效的指针值 `p`，结果改为 `reinterpret_cast<T*>(reinterpret_cast<uintptr_t>(p))`。所以原子指针的越界算术有确定的结果（只是不一定指向对象），不是 UB。

¶4 表 156：`add`、`sub`、`max`、`min`。¶5–¶10 `fetch_key`：¶6 *Mandates* `T` 是完整对象类型（注 1：`void*` 与函数指针上的算术非良构）；操作数类型是 `ptrdiff_t`（`add`/`sub`）或 `T*`（`max`/`min`）；¶9 结果可能是未定义的地址，但操作本身没有 UB；¶10 注 2：指向不同完整对象的指针用 `<` 不构成严格弱序，`fetch_max` 对它们没有可靠意义。

¶11–¶14 `store_add` 等原子 modify-write 版本。¶15–¶16 `operator+=`、`operator-=`（操作数 `ptrdiff_t`）。

## 共用的成员运算符（[atomics.types.memop]）

整数与指针特化共有：

| 运算符 | 等价于 | 返回 |
|---|---|---|
| `a++` | `fetch_add(1)` | 旧值 |
| `a--` | `fetch_sub(1)` | 旧值 |
| `++a` | `fetch_add(1) + 1` | 新值 |
| `--a` | `fetch_sub(1) - 1` | 新值 |

都使用默认的 `seq_cst`。返回的是**值**，所以 `++a` 返回的新值是原子操作那一刻算出来的，而不是之后再读一次 `a`——中间其他线程的修改不会反映在返回值里。

## 陷阱

!!! pitfall "`a = a + 1` 不是原子的"
    `a + 1` 先 `load`（`operator T()`），再 `store`（`operator=`），两个原子操作之间可以插入别的线程的修改。用 `++a`、`a += 1` 或 `fetch_add`。

!!! pitfall "无锁栈的 pop 与 ABA"
    例 2 的 push 是正确的，但对称的 pop——`while (!head.compare_exchange_weak(old, old->next))`——有两个问题：`old->next` 可能读取已被另一线程释放的节点（释放后使用），以及 ABA（节点被弹出、释放、重新分配又被压回，CAS 误以为没变）。这正是 [[saferecl]] 的 hazard pointer 和 RCU 要解决的问题，或者用 [[util.smartptr.atomic]] 的 `atomic<shared_ptr>`。

!!! pitfall "对 `atomic<double>` 用 CAS 比较 NaN"
    存的是 NaN，`expected` 是同一个 NaN 位模式：`memcmp` 相等，CAS 成功——尽管 `NaN == NaN` 为假。反过来，`expected` 是另一种 NaN 位模式时永远失败。别依赖浮点的 `==` 语义去推测 CAS 的结果。

## 历史与演进

!!! history "atomic<T> 的演变"
    - **C++11**：引入 `atomic<T>`，默认构造函数平凡（值不确定），需要 `atomic_init`/`ATOMIC_VAR_INIT`。
    - **C++20**：默认构造改为值初始化；增加浮点特化（[[P0020R6]]）、`wait`/`notify`（[[atomics.wait]]）；非无锁类型上的 `volatile` 操作被弃用；CAS 明确忽略填充位（注 7）。
    - **C++26**：`fetch_max`/`fetch_min`（[[P0493R5]]）；原子 modify-write 操作 `store_add` 等。
    - **C++23 之后**：大部分操作成为 `constexpr`；浮点特化增加 `fmaximum` 系列。

## 思考题

!!! question "1. `std::atomic<int> a; int x = a;` 中 `x` 的值是多少？C++17 呢？"

<details markdown="1">
<summary>答案</summary>

C++20 起，默认构造函数值初始化（¶2），`x` 为 0（若 `a` 是局部变量也一样）。C++17 中默认构造函数是平凡的，局部的 `a` 值不确定，读取它是 UB（静态存储期的 `a` 则被零初始化）。
</details>

!!! question "2. 为什么 `compare_exchange` 在失败时才写 `expected`，而不是总是写？"

<details markdown="1">
<summary>答案</summary>

例 2 说明了原因：成功时 `expected` 可能就是刚刚被发布的对象的一部分（`p->next`）。如果成功后还要把读到的值写回 `expected`，这次写入发生在发布**之后**，会与看到 `p` 的其他线程对 `p->next` 的读取构成数据竞争。只在失败时写回，就避免了这一点。shared_ptr 特化的 ¶17 也写明"成功时 `expected` 在原子更新之后不再被访问"。
</details>

## 小结

- `T` 必须可平凡复制、可复制/移动构造与赋值、无 cv 限定，否则非良构。
- 初始化（包括默认构造）不是原子操作；发布新建的原子对象也需要同步。
- `volatile` 重载只对总是无锁的类型存在。
- CAS 比较**值表示**：`±0.0` 不等、同载荷 NaN 相等、填充位忽略（libc++ 的 `atomic<T>` 尚未做到）。
- 整数原子算术回绕，没有 UB；浮点原子算术结果不可表示时未指定；指针原子算术越界有确定结果。
- 复合运算符与前置 `++`/`--` 返回新值，后置返回旧值，都是值而非引用。
