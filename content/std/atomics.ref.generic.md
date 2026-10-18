---
title: atomic_ref
summary: atomic_ref<T> 让普通对象在一段时间内成为原子对象——生命周期规则（引用期间只能经由 atomic_ref 访问、子对象不得被另一个 atomic_ref 同时引用）、required_alignment 前置条件、与 atomic<T> 无锁性质的差异、cv 限定的 T 与 address()、整数/浮点/指针特化（含 fetch_max、store_add 与无效指针值规则）
status: done
covers: *
papers: P0019R8
related: atomics, atomics.types.generic, atomics.lockfree, atomics.order, atomics.wait, intro.races, basic.life
tags: 标准库, 原子操作, atomic_ref
updated: 2026-10-18
---

`atomic<T>` 要求你在**声明**对象时就决定它是原子的。但很多时候，一个对象只在某个阶段被多个线程并发访问：比如一个大数组在并行阶段由多个线程累加，在串行阶段被普通代码读写。把整个数组声明成 `atomic<int>[]` 会让串行阶段也付出原子操作的代价，而且 `atomic<int>` 与 `int` 的布局不保证相同，不能与 C API 共享。

`atomic_ref<T>`（C++20，[[P0019R8]]）解决这个问题：它是一个**引用**，在它存在期间，被引用的普通对象被当作原子对象。

本页覆盖 [atomics.ref.generic] 的全部子条款：概述、操作、整数特化、浮点特化、指针特化，以及整数与指针共用的成员运算符。

## 类模板（[atomics.ref.generic.general]）

类定义的要点：

- 唯一的数据成员是仅说明用的 `T* ptr`。`atomic_ref` 是可复制的小对象，按值传递就行；
- `value_type` 是 `remove_cv_t<T>`；
- `static constexpr size_t required_alignment`、`static constexpr bool is_always_lock_free`，二者都由实现定义；
- 构造函数 `constexpr explicit atomic_ref(T&)`；`atomic_ref(T&&)` 被删除——不能引用临时对象；
- 复制构造，以及从 `atomic_ref<U>` 的转换构造；**复制赋值被删除**（`atomic_ref` 像引用一样不能重新绑定）；
- 成员 `store`、`operator=`、`load`、`operator value_type`、`exchange`、`compare_exchange_*`、`wait`、`notify_one`、`notify_all`、`address`——**全部是 `const` 成员函数**。`const atomic_ref<int>` 依然可以修改被引用的 `int`，就像 `int* const` 可以修改 `*p`。

### 被引用的对象是原子对象（¶1）

!!! std
    An `atomic_ref` object applies atomic operations to the object referenced by `*ptr` such that, for the lifetime of the `atomic_ref` object, the object referenced by `*ptr` is an atomic object.

    `atomic_ref` 对象对 `*ptr` 引用的对象施加原子操作，使得在 `atomic_ref` 对象的生命周期内，`*ptr` 引用的对象是一个原子对象（[[intro.races]]）。

这是 `atomic_ref` 在内存模型中的全部地位：它不创建新对象，只是**在一段时间内**改变一个已有对象的身份。

### 程序必须遵守的规则（¶2–¶5）

¶2 `is_trivially_copyable_v<T>` 为 `false` 时，程序非良构。

¶3 是对使用者的约束（违反为 UB {{ub}}）：

1. 被引用对象的**生命周期必须长于**所有引用它的 `atomic_ref`；
2. 只要还有任何引用它的 `atomic_ref` 实例存在，**对该对象的所有访问都必须经由这些 `atomic_ref` 实例**进行；
3. 被 `atomic_ref` 引用的对象的**任何子对象**，都不得**同时**被另一个 `atomic_ref` 引用。

第 2 条比"不要有数据竞争"更严格：即使在**同一个线程**里，一边持有 `atomic_ref`、一边用普通赋值修改对象，也违反了 ¶3。原因是实现可能用锁（见 ¶4 注 1）或对象之外的状态来实现原子性，绕过 `atomic_ref` 的访问会破坏这些状态。

第 3 条禁止重叠：`atomic_ref<S>` 引用一个结构体的同时，`atomic_ref<int>` 引用它的某个成员——不行。原子性是按"整个被引用对象"定义的，部分重叠的两个原子对象没有一致的修改顺序。

¶4 通过引用某对象的 `atomic_ref` 施加的原子操作，相对于通过引用**同一**对象的任何其他 `atomic_ref` 施加的原子操作是原子的。所以多个线程各自构造自己的 `atomic_ref` 去引用同一个对象是正确用法，不需要共享同一个 `atomic_ref` 实例。注 1：原子操作或 `atomic_ref` 的构造函数可以获取一个共享资源（例如与被引用对象关联的锁），以便施加原子操作。

¶5 `is_always_lock_free` 为 `false` 且 `is_volatile_v<T>` 为 `true` 时，程序非良构。对应地，整数（[atomics.ref.int] ¶2）、浮点（[atomics.ref.float] ¶2）、指针（[atomics.ref.pointer] ¶3）特化也有同样的规定。

```cpp run title="atomic-ref-histogram.cpp" ok
#include <atomic>
#include <cstdio>
#include <thread>
#include <vector>

int main() {
  alignas(std::atomic_ref<int>::required_alignment) int hist[4] = {};
  {
    std::vector<std::jthread> ts;
    for (int t = 0; t < 4; ++t)
      ts.emplace_back([&hist, t] {
        for (int i = 0; i < 1000; ++i)
          std::atomic_ref(hist[(i + t) % 4]).fetch_add(1, std::memory_order::relaxed);  // 每次临时构造一个 atomic_ref
      });
  }                                         // join：此后不再有 atomic_ref 引用 hist
  for (int v : hist) std::printf("%d ", v); // 普通访问：OK
  std::puts("");
}
```

输出 `1000 1000 1000 1000`，ThreadSanitizer 不报告竞争。并行阶段每次访问都经由临时的 `atomic_ref`；`jthread` 析构（join）之后进入串行阶段，所有 `atomic_ref` 都已销毁，普通读取是合法的，join 也提供了所需的 happens before。

```cpp title="atomic-ref-mixed.cpp" ub
#include <atomic>
#include <thread>
int counter = 0;
int main() {
  std::thread t([] { std::atomic_ref(counter).fetch_add(1); });
  ++counter;        // UB：其他线程的 atomic_ref 可能仍然存在，此访问没有经由 atomic_ref（¶3）
  t.join();
}
```

## 操作（[atomics.ref.ops]）

### 对齐与无锁性质（¶1–¶4）

¶1 `required_alignment`：被 `atomic_ref` 引用的对象所需的对齐，**至少**为 `alignof(T)`。对与 `T` 相似（similar）的任何类型 `U`，其值与 `atomic_ref<remove_cv_t<U>>::required_alignment` 相同——`atomic_ref<const int>` 与 `atomic_ref<int>` 的对齐要求一致。

¶2 注 1：实现可以把 `required_alignment` 定义得**大于** `alignof(T)`，以保证该 `atomic_ref<T>` 的所有对象上的操作都是无锁的。例如在某些 32 位平台上，`alignof(long long)` 是 4，但 8 字节原子指令要求 8 字节对齐；此时 `atomic_ref<long long>::required_alignment` 可以是 8。

¶3 `is_always_lock_free`：操作总是无锁时为 `true`；同样对相似类型一致。¶4 `is_lock_free()`：当**类型** `atomic_ref<T>` 的所有对象上的操作都无锁时返回 `true`。

`atomic_ref` 的无锁性质可以与 `atomic<T>` 不同，因为 `atomic<T>` 可以给自己加填充和对齐，`atomic_ref` 只能用对象本来的大小：在 Apple Silicon 上，12 字节的结构体 `S12`，`atomic<S12>` 被补到 16 字节，总是无锁；`atomic_ref<S12>` 的 `required_alignment` 为 4，**不是**无锁的（实测见 [[atomics.lockfree]]）。

### 构造（¶5–¶10）

¶5 构造函数 `atomic_ref(T& obj)` 的**前置条件**：被引用对象按 `required_alignment` 对齐。违反为 UB。这就是上例中 `alignas(std::atomic_ref<int>::required_alignment)` 的作用：对 `int` 而言通常是多余的，对 `double`、`long long`、结构体则可能必要。¶6–¶7：之后 `*this` 引用 `obj`；不抛异常。

¶8 复制构造：引用同一对象。

¶9–¶10 转换构造 `template<class U> atomic_ref(const atomic_ref<U>&)`：约束是 `T` 与 `U` 相似（[[conv.qual]]）且 `U*` 可转换为 `T*`。即只允许"加 cv 限定"的转换：`atomic_ref<int>` → `atomic_ref<const int>`。这是 C++23 之后的新措辞，随 cv 限定的 `T` 一起加入。

### 读写与 RMW（¶11–¶27）

与 `atomic<T>` 的对应操作（[[atomics.types.operations]]）逐一相同，只是作用于 `*ptr`：

- ¶11–¶13 `store`：*Constraints* `is_const_v<T>` 为 `false`；内存序前置条件 `relaxed`/`release`/`seq_cst`。
- ¶14–¶15 `operator=`：等价于 `store(desired); return desired;`——**返回值类型而不是引用**，与 `atomic<T>` 相同。
- ¶16–¶19 `load`、`operator value_type`。
- ¶20–¶22 `exchange`：原子读-改-写操作。
- ¶23–¶27 `compare_exchange_weak/strong`：比较**值表示**；只给一个内存序时 failure 序的推导规则；成功时是 RMW，失败时是原子 load；weak 版本可以虚假失败（¶27）。

对 `const T` 的 `atomic_ref`，所有修改操作被 *Constraints* 排除，只剩 `load`、`wait` 等只读操作。

### 等待与通知（¶28–¶36）

`wait(old, order)`（¶28–¶30）：反复 `load(order)` 并按值表示与 `old` 比较，相等则阻塞直到被通知或虚假唤醒（[[atomics.wait]]）。`notify_one`、`notify_all`（¶31–¶36）：*Constraints* `is_const_v<T>` 为 `false`。

### address()（¶37）

¶37 `address()` 返回 `ptr`，类型是 *COPYCV*`(T, void)*`——对 `atomic_ref<const int>` 是 `const void*`。返回 `void*` 而不是 `T*` 是刻意的：拿到地址可以做比较、散列（比如实现"按地址分桶的锁"），但要访问对象仍须经过 `atomic_ref`（¶3），返回 `void*` 让误用更难发生。这也是 C++23 之后的新措辞。

!!! impl "libc++ 的支持情况（Clang 23）"
    - `address()` 已实现，返回类型正是 `__copy_cv_t<_Tp, void>*`。
    - `atomic_ref<const int>` **无法使用**：构造时内部把 `const int*` 传给 `int*` 形参而编译失败。
    - 成员函数不是 `constexpr` 的。

## 整数特化（[atomics.ref.int]）

¶1 除 cv `bool` 之外的所有整数类型都有 `atomic_ref` 特化，提供整数专有的原子操作；注 1：`atomic_ref<bool>` 使用主模板。`difference_type` 是 `value_type` 本身。

¶4–¶9 `fetch_key`（key 为 `add`、`sub`、`and`、`or`、`xor`、`max`、`min`，对应表 155）：原子 RMW；返回修改前的值。¶8：除 `max`/`min` 外，有符号整数的计算**如同转换为对应无符号类型计算后再转回**——所以溢出时回绕，**没有 UB**（注 2）。¶9：`fetch_max`/`fetch_min` 如同用 `std::max`/`std::min` {{c++26}}。

¶10–¶13 `store_key`：**原子 modify-write 操作**（[[atomics.order#12]]）{{c++26}}。不返回值；内存序前置条件只允许 `relaxed`/`release`/`seq_cst`；同样的回绕规则。

¶14–¶15 `operator op=`：等价于 `return fetch_key(operand) op operand;`——返回**新值**，且没有 `volatile` 版本也没有内存序参数（总是 `seq_cst`）。

## 浮点特化（[atomics.ref.float]）

¶1 所有浮点类型都有特化（包括扩展浮点类型）。¶4–¶8 `fetch_add`、`fetch_sub`，以及 `fetch_max`、`fetch_min`、`fetch_fmaximum`、`fetch_fminimum`、`fetch_fmaximum_num`、`fetch_fminimum_num`：

- ¶8 结果不可表示时结果未指定 {{unspec}}，但**没有 UB**；运算应当符合 `numeric_limits<value_type>` 描述的性质；**原子运算所用的浮点环境（[[cfenv]]）可以与调用线程的浮点环境不同**——你用 `fesetround` 设置的舍入模式不一定作用于 `fetch_add`。
- ¶9 `max`/`min` 系列的语义：
    - `fetch_fmaximum`/`fetch_fminimum` 如同 C 的 `fmaximum`/`fminimum`（NaN 传播，`-0 < +0`）；
    - `fetch_fmaximum_num`/`fetch_fminimum_num` 如同 `fmaximum_num`/`fminimum_num`（忽略 NaN）；
    - `fetch_max`/`fetch_min` 如同 `fmaximum_num`/`fminimum_num`，但放宽三点：两个都是 NaN 时存入未指定的 NaN；恰好一个是 NaN 时存入另一个或某个未指定的 NaN；两个是符号不同的零时存哪个未指定。¶10 推荐把 `-0` 当作小于 `+0`。

  放宽的目的是允许直接映射到硬件的浮点 max/min 指令，它们在 NaN 与有符号零上的行为各不相同。
- ¶11–¶16 `store_add`、`store_sub` 及 `store_max` 等：原子 modify-write 操作。¶14 额外允许：**浮点原子 modify-write 操作的算术规则可以与普通浮点运算或原子浮点类型的运算不同**；注 1：允许树形归约。也就是说一千个线程 `store_add` 到同一个 `float`，硬件可以先两两相加再合并，结果与按某个顺序逐个相加的结果可能不同（浮点加法不满足结合律）。
- ¶17–¶18 `operator+=`、`operator-=`。

## 指针特化（[atomics.ref.pointer]）

¶1 所有对象指针类型都有特化。

¶2 是一条有意思的规定：

> **除常量求值期间外**，当原子指针上的操作会产生一个在该求值语境中**无效**的指针值 `p`（[[basic.compound]]）时，结果改为 `reinterpret_cast<T*>(reinterpret_cast<uintptr_t>(p))`。

普通指针算术越界是 UB（[[expr.add]]），但原子指针的 `fetch_add` 不能有 UB——它可能在其他线程修改指针后才计算。这条规则把"越界"的结果定义为"经过整数往返的指针"，值是确定的，只是不一定指向任何对象。与之配合，¶10、¶16 说"结果可能是一个未定义的地址，但操作本身没有未定义行为"。

¶5–¶11 `fetch_add`、`fetch_sub`（以 `difference_type` 即 `ptrdiff_t` 为操作数）、`fetch_max`、`fetch_min`：¶7 *Mandates* 指向完整对象类型（`void*` 与函数指针上的算术非良构）。¶11 注 1：指针若指向不同的完整对象，`<` 不构成严格弱序（[[expr.rel]]），`fetch_max` 的结果也就没有可靠意义。

¶12–¶16 `store_add` 等原子 modify-write 版本。¶17–¶18 `operator+=`、`operator-=`。

## 成员运算符（[atomics.ref.generic] 末尾）

整数与指针特化共用 `operator++(int)`（`fetch_add(1)`）、`operator--(int)`、`operator++()`（`fetch_add(1) + 1`）、`operator--()`，都要求被引用类型不是 `const`。注意前置 `++` 返回的也是**值**，不是引用。

## 陷阱

!!! pitfall "atomic_ref 的生命周期就是“原子期”"
    ```cpp
    std::atomic_ref r(x);
    r.store(1);
    x = 2;              // UB：r 还活着
    ```
    把 `atomic_ref` 限制在最小的作用域，或者像上面的直方图例子那样每次访问临时构造一个。

!!! pitfall "对齐不够是 UB，而且不会被检查"
    `atomic_ref<double>` 引用一个从字节缓冲区里 `reinterpret_cast` 出来、只有 4 字节对齐的 `double`，违反 ¶5 的前置条件。在 x86 上它可能"碰巧能用"（拆成两次访问而失去原子性），在 ARM 上可能直接触发对齐异常。

!!! pitfall "不要让两个 atomic_ref 引用重叠的对象"
    用 `atomic_ref<uint64_t>` 原子地读一个 8 字节结构体、同时用 `atomic_ref<uint32_t>` 修改其中一半——违反 ¶3。需要"有时整体、有时部分"地原子访问，应当始终以整体为单位做 CAS。

## 思考题

!!! question "1. 两个线程各自构造一个 `atomic_ref<int>` 引用同一个 `int`，各做 1000 次 `fetch_add(1, relaxed)`。结果一定是 2000 吗？"

<details markdown="1">
<summary>答案</summary>

一定（前提是之后的读取与两个线程有 happens before，比如 join 之后）。¶4：经由不同 `atomic_ref` 对同一对象的原子操作彼此是原子的；¶1：在 `atomic_ref` 存在期间对象是原子对象，因此有单一的修改顺序；[[atomics.order#11]]：每次 RMW 读取修改顺序中紧邻其前的值，所以没有增量丢失。
</details>

!!! question "2. `std::atomic_ref<const int>` 有什么用？"

<details markdown="1">
<summary>答案</summary>

用于只读的一方：另一个线程通过 `atomic_ref<int>` 修改对象时，按 ¶3，读取方也必须经由 `atomic_ref` 访问，而它手里可能只有 `const int&`。在 cv 限定的 `T` 被允许之前，只能 `const_cast` 后构造 `atomic_ref<int>`，这既丑陋，在对象本身是 const 对象时还会让人担心修改。`atomic_ref<const int>` 只提供 `load`、`wait` 等操作，也可以由 `atomic_ref<int>` 转换得到（¶9）。
</details>

## 小结

| | `atomic<T>` | `atomic_ref<T>` |
|---|---|---|
| 对象何时是原子的 | 一直 | 只在某个引用它的 `atomic_ref` 存在期间 |
| 布局 | 可能与 `T` 不同（填充、对齐） | 就是 `T` 本身 |
| 无锁性质 | 可以靠补齐达到 | 受限于对象的大小，需满足 `required_alignment` |
| 可复制 | 否 | 是（复制的是引用），但不可复制赋值 |
| 混用普通访问 | 不可能 | 引用期间禁止（UB） |
| `bool` | `atomic<bool>` 用主模板 | `atomic_ref<bool>` 用主模板 |
