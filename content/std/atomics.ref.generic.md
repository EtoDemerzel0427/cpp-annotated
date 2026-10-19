---
title: atomic_ref
summary: atomic_ref<T> 让一个普通对象在一段时间内成为原子对象：引用期间的访问规则、对齐前置条件、与 atomic<T> 在无锁性质上的差别，以及整数、浮点、指针特化。
status: done
covers: *
papers: P0019R8
related: atomics, atomics.types.generic, atomics.lockfree, atomics.order, atomics.wait, intro.races, basic.life
tags: 标准库, 原子操作, atomic_ref
updated: 2026-10-19
---

!!! tldr
    - `atomic_ref<T>` 不创建新对象。它存在期间，被引用的普通对象就是一个原子对象；它销毁后，对象又可以普通地访问。
    - 只要还有 `atomic_ref` 引用某个对象，对它的所有访问都必须经由 `atomic_ref`，同一线程里的普通读写也不行；违反是 UB。
    - 对象必须按 `required_alignment` 对齐，它可能大于 `alignof(T)`；不满足是 UB，而且不会被检查。
    - `atomic_ref` 只能使用对象原本的大小，所以它可能不是无锁的，而同一类型的 `atomic<T>` 是无锁的。
    - 整数特化的算术按回绕计算，没有 UB；浮点特化结果不可表示时结果未指定；指针特化越界得到一个确定但不一定可用的地址。

## 为什么需要 atomic_ref

`atomic<T>` 要求在声明对象时就决定它是原子的。但很多对象只在某个阶段被多个线程并发访问：一个大数组在并行阶段由多个线程累加，在串行阶段被普通代码读写。把它声明成 `atomic<int>[]`，串行阶段也要付原子操作的代价；而且 `atomic<int>` 与 `int` 的布局不保证相同，不能直接交给 C 接口。

`atomic_ref<T>`（C++20，[[P0019R8]]）是一个引用，它存在期间把被引用的普通对象当作原子对象：

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
          std::atomic_ref(hist[(i + t) % 4])
              .fetch_add(1, std::memory_order::relaxed);
      });
  }                                          // join：atomic_ref 都已销毁
  for (int v : hist) std::printf("%d ", v);  // 普通访问：OK
  std::puts("");
}
```

输出 `1000 1000 1000 1000`，ThreadSanitizer 没有报告。并行阶段每次访问都经由一个临时的 `atomic_ref`。`jthread` 析构时 join，之后所有 `atomic_ref` 都已销毁，join 也提供了所需的 happens before，所以普通读取合法。

## 引用期间的规则 [atomics.ref.generic.general]

!!! std
    An `atomic_ref` object applies atomic operations to the object referenced by `*ptr` such that, for the lifetime of the `atomic_ref` object, the object referenced by `*ptr` is an atomic object.

¶1 在 `atomic_ref` 对象的生命周期内，它引用的对象是一个原子对象（[[intro.races]]）。这就是 `atomic_ref` 在内存模型中的全部地位：它只是在一段时间内改变一个已有对象的身份。

¶2 `T` 必须可平凡复制，否则程序非良构。

¶3 是对使用者的三条约束，违反都是 UB {{ub}}：

1. 被引用对象的生命周期必须长于所有引用它的 `atomic_ref`；
2. 只要还有引用它的 `atomic_ref` 存在，对该对象的所有访问都必须经由这些 `atomic_ref`；
3. 被引用对象的任何子对象，都不得同时被另一个 `atomic_ref` 引用。

第 2 条比不得有数据竞争更严：即使在同一个线程里，一边持有 `atomic_ref`、一边普通地赋值，也违反了这条。原因是实现可能用锁或对象以外的状态实现原子性（见 ¶4 的注），绕过 `atomic_ref` 的访问会破坏这些状态。

<div class="compare" markdown="1">

```cpp ok
#include <atomic>
int x = 0;
void f() {
  {
    std::atomic_ref r(x);
    r.store(1);
  }        // r 已销毁
  x = 2;   // OK
}
```

```cpp ub
#include <atomic>
int x = 0;
void f() {
  std::atomic_ref r(x);
  r.store(1);
  x = 2;   // UB：r 还在（¶3）
}
```

</div>

多线程时更容易踩到：

```cpp title="atomic-ref-mixed.cpp" ub
#include <atomic>
#include <thread>
int counter = 0;
int main() {
  std::thread t([] { std::atomic_ref(counter).fetch_add(1); });
  ++counter;   // UB：t 中的 atomic_ref 可能还在，这次访问没有经由它
  t.join();
}
```

ThreadSanitizer 对这个程序报告 `data race`。

第 3 条禁止重叠：`atomic_ref<S>` 引用一个结构体的同时，`atomic_ref<int>` 引用它的某个成员，这是不允许的。原子性是按整个被引用对象定义的，部分重叠的两个原子对象没有一致的修改顺序。

¶4 经由一个 `atomic_ref` 施加的原子操作，相对于经由引用同一对象的其他 `atomic_ref` 施加的原子操作是原子的。所以每个线程各自构造自己的 `atomic_ref` 去引用同一个对象是正确用法，不需要共享同一个实例。注 1 说明，原子操作或 `atomic_ref` 的构造函数可以获取一个共享资源，例如与被引用对象关联的一把锁。

¶5 `is_always_lock_free` 为 `false` 而 `T` 是 volatile 类型时，程序非良构。

### 类的形状

- 唯一的数据成员是仅说明用的 `T* ptr`，`atomic_ref` 是可以按值传递的小对象。
- `value_type` 是 `remove_cv_t<T>`。
- 构造函数 `explicit atomic_ref(T&)`；`atomic_ref(T&&)` 被删除，不能引用临时对象。
- 可以复制构造，但复制赋值被删除：它像引用一样不能重新绑定。
- 所有成员函数都是 `const` 的。`const atomic_ref<int>` 依然可以修改被引用的 `int`，就像 `int* const` 可以修改 `*p`。

## 对齐与无锁性质 [atomics.ref.ops]

¶1 `required_alignment` 是被 `atomic_ref` 引用的对象所需的对齐，至少为 `alignof(T)`。与 `T` 相似（similar，只差 cv 限定）的类型 `U`，其 `atomic_ref<remove_cv_t<U>>` 的这个值与之相同，所以 `atomic_ref<const int>` 和 `atomic_ref<int>` 的要求一样。

¶2 注 1：实现可以把 `required_alignment` 定得比 `alignof(T)` 大，以保证所有操作都是无锁的。例如某些 32 位平台上 `alignof(long long)` 是 4，而 8 字节原子指令要求 8 字节对齐。

¶5 构造函数的前置条件是被引用对象按 `required_alignment` 对齐。上面直方图例子里的 `alignas` 就是为此写的：对 `int` 通常多余，对 `double`、`long long`、结构体可能必要。

¶3 `is_always_lock_free` 在操作总是无锁时为 `true`。¶4 `is_lock_free()` 在类型 `atomic_ref<T>` 的所有对象上的操作都无锁时返回 `true`。

`atomic_ref` 的无锁性质可以与 `atomic<T>` 不同。`atomic<T>` 可以给自己加填充、提高对齐；`atomic_ref` 只能用对象本来的大小和对齐。在 Apple Silicon 上用 Clang 23 测试，12 字节的 `struct S12 { int a, b, c; }`：`sizeof(atomic<S12>)` 是 16，`atomic<S12>::is_always_lock_free` 为 `true`；`atomic_ref<S12>::required_alignment` 是 4，`is_always_lock_free` 为 `false`（另见 [[atomics.lockfree]]）。

## 操作 [atomics.ref.ops]

### 构造与转换（¶5–¶10）

除了上面的对齐前置条件，¶8 复制构造得到引用同一对象的 `atomic_ref`。¶9 的转换构造函数 `atomic_ref(const atomic_ref<U>&)` 要求 `T` 与 `U` 相似，且 `U*` 能转换为 `T*`，也就是只允许加 cv 限定：`atomic_ref<int>` 可以转换为 `atomic_ref<const int>`。这是 C++23 之后随 cv 限定的 `T` 一起加入的新措辞。

### 读写、交换与 CAS（¶11–¶27）

这些操作与 `atomic<T>` 的对应操作逐一相同（[[atomics.types.operations]]），只是作用于 `*ptr`：

| 操作 | 段落 | 要点 |
|---|---|---|
| `store` | ¶11–¶13 | `T` 不能是 const；内存序只能是 `relaxed`、`release`、`seq_cst` |
| `operator=` | ¶14–¶15 | 等价于 `store(desired); return desired;`，返回值而不是引用 |
| `load`、`operator value_type` | ¶16–¶19 | 内存序只能是 `relaxed`、`acquire`、`seq_cst` |
| `exchange` | ¶20–¶22 | 原子读-改-写操作 |
| `compare_exchange_weak/strong` | ¶23–¶27 | 比较值表示；weak 版本可以虚假失败 |

对 `atomic_ref<const T>`，所有修改操作都被 *Constraints* 排除，只剩 `load`、`wait` 这类只读操作。

### 等待与通知（¶28–¶36）

`wait(old, order)` 反复执行 `load(order)` 并按值表示与 `old` 比较，相等则阻塞，直到被通知或虚假唤醒。`notify_one`、`notify_all` 要求 `T` 不是 const。规则见 [[atomics.wait]]。

### address()（¶37）

¶37 `address()` 返回 `ptr`，类型是 *COPYCV*`(T, void)*`，对 `atomic_ref<const int>` 是 `const void*`。返回 `void*` 而不是 `T*`：拿到地址可以比较、散列（例如实现按地址分桶的锁），但要访问对象仍须经过 `atomic_ref`，返回 `void*` 让误用更难发生。这也是 C++23 之后的新措辞。

!!! impl "libc++ 的支持情况（Clang 23）"
    - `address()` 已实现。
    - `atomic_ref<const int>` 无法使用：构造函数内部把 `const int*` 传给 `int*` 形参，编译失败。
    - 成员函数还不是 `constexpr` 的，在常量表达式中使用 `atomic_ref` 会失败。

## 整数特化 [atomics.ref.int]

¶1 除 cv `bool` 之外的每种整数类型都有特化，提供整数专有的原子操作；`atomic_ref<bool>` 使用主模板。特化的 `difference_type` 就是 `value_type`。

¶4–¶9 `fetch_add`、`fetch_sub`、`fetch_and`、`fetch_or`、`fetch_xor`、`fetch_max`、`fetch_min` 是原子读-改-写操作，返回修改前的值。¶8 规定，除 `max`/`min` 外，有符号整数的计算如同转换为对应的无符号类型计算再转回，所以溢出时回绕，不会有 UB。¶9 `fetch_max`/`fetch_min` 如同用 `std::max`/`std::min` 计算 {{c++26}}。

¶10–¶13 `store_add` 等 `store_key` 系列 {{c++26}} 做同样的运算但不返回值。它们是**原子 modify-write 操作**：一种同步要求更弱的读-改-写操作，意图是用不受 acquire 栅栏排序的硬件机制实现（[[atomics.order#12]]、[[atomics.fences]]）。内存序只能是 `relaxed`、`release`、`seq_cst`。

¶14–¶15 `operator+=` 等复合赋值等价于 `return fetch_key(operand) op operand;`，返回新值，内存序总是 `seq_cst`。

## 浮点特化 [atomics.ref.float]

¶1 每种浮点类型都有特化，包括扩展浮点类型。提供 `fetch_add`、`fetch_sub` 和六种 max/min：`fetch_max`、`fetch_min`、`fetch_fmaximum`、`fetch_fminimum`、`fetch_fmaximum_num`、`fetch_fminimum_num`。

¶8 结果不可表示时结果未指定 {{unspec}}，但操作本身没有 UB。还有一点容易忽略：原子运算使用的浮点环境（[[cfenv]]）可以和调用线程的不同，用 `fesetround` 设置的舍入模式不一定作用于 `fetch_add`。

¶9 规定各种 max/min 的语义：

- `fetch_fmaximum`/`fetch_fminimum` 如同 C 的 `fmaximum`/`fminimum`，NaN 会传播；
- `fetch_fmaximum_num`/`fetch_fminimum_num` 如同 `fmaximum_num`/`fminimum_num`，忽略 NaN；
- `fetch_max`/`fetch_min` 如同 `fmaximum_num`/`fminimum_num`，但放宽三点：两个实参都是 NaN 时存入一个未指定的 NaN；恰好一个是 NaN 时存入另一个实参或某个未指定的 NaN；两个实参是符号不同的零时存入哪一个未指定。¶10 建议把 `-0` 当作小于 `+0`。

放宽是为了能直接映射到硬件的浮点 max/min 指令，它们在 NaN 和有符号零上的行为各不相同。

¶11–¶16 `store_add`、`store_sub`、`store_max` 等是原子 modify-write 操作。¶14 额外允许它们的算术规则与普通浮点运算不同，注 1 明确允许树形归约：一千个线程对同一个 `float` 执行 `store_add`，硬件可以先两两相加再合并。浮点加法不满足结合律，结果可能与任何一种逐个相加的顺序都不同。

¶17–¶18 `operator+=`、`operator-=` 返回新值。

## 指针特化 [atomics.ref.pointer]

¶1 每种对象指针类型都有特化。

¶2 普通指针算术越界是 UB（[[expr.add]]），但原子指针的 `fetch_add` 不能有 UB，因为它计算时用的值可能刚被另一个线程改过。于是 ¶2 规定：除常量求值期间外，原子指针上的操作如果会产生一个在该求值语境中无效的指针值 `p`（[[basic.compound]]），结果改为 `reinterpret_cast<T*>(reinterpret_cast<uintptr_t>(p))`。

所以越界的结果是一个经过整数往返的指针，值是确定的，只是不一定指向任何对象。¶10 和 ¶16 相应地写明：结果可能是未定义的地址，但操作本身没有未定义行为。

¶5–¶11 `fetch_add`、`fetch_sub` 的操作数是 `difference_type`（`ptrdiff_t`），`fetch_max`、`fetch_min` 的操作数是指针。¶7 要求指向完整对象类型，`void*` 和函数指针上的算术非良构。¶11 注 1 提醒，指向不同完整对象的指针用 `<` 比较不构成严格弱序（[[expr.rel]]），这时 `fetch_max` 的结果没有可靠的意义。

¶12–¶16 是 `store_add` 等 modify-write 版本，¶17–¶18 是 `operator+=`、`operator-=`。

## 自增自减 [atomics.ref.memop]

整数和指针特化共用四个运算符，都要求被引用类型不是 const：

| 运算符 | 等价于 | 返回 |
|---|---|---|
| `r++` | `fetch_add(1)` | 旧值 |
| `r--` | `fetch_sub(1)` | 旧值 |
| `++r` | `fetch_add(1) + 1` | 新值 |
| `--r` | `fetch_sub(1) - 1` | 新值 |

前置 `++` 返回的也是值，不是引用。

## 常见误解

!!! pitfall "对齐不够只是慢一点"
    `atomic_ref<double>` 引用一个从字节缓冲区里 `reinterpret_cast` 出来、只有 4 字节对齐的 `double`，违反构造函数的前置条件，是 UB。实际后果可能是失去原子性（一次访问被拆成两次），也可能在某些硬件上触发对齐异常。

!!! pitfall "整体和部分可以分开原子访问"
    用 `atomic_ref<uint64_t>` 原子地读一个 8 字节结构体，同时用 `atomic_ref<uint32_t>` 修改其中一半，违反 ¶3 的第 3 条。有时整体、有时部分地访问时，应当始终以整体为单位做 CAS。

## 思考题

!!! question "思考题 1"
    两个线程各自构造一个 `atomic_ref<int>` 引用同一个 `int`，各做 1000 次 `fetch_add(1, relaxed)`。join 之后读到的一定是 2000 吗？

<details markdown="1">
<summary>答案</summary>

一定。¶4 规定经由不同 `atomic_ref` 对同一对象的原子操作彼此是原子的；¶1 让对象在这段时间内是原子对象，因而有单一的修改顺序；[[atomics.order#11]] 规定每次读-改-写读取修改顺序中紧邻其前的值，所以没有增量丢失。join 之后两个 `atomic_ref` 都已销毁，join 提供 happens before，普通读取合法。
</details>

!!! question "思考题 2"
    `std::atomic_ref<const int>` 有什么用？

<details markdown="1">
<summary>答案</summary>

给只读的一方用。另一个线程通过 `atomic_ref<int>` 修改对象时，按 ¶3，读取方也必须经由 `atomic_ref` 访问，而它手里可能只有 `const int&`。在允许 cv 限定的 `T` 之前，只能 `const_cast` 后构造 `atomic_ref<int>`。`atomic_ref<const int>` 只提供 `load`、`wait` 这类操作，也可以由 `atomic_ref<int>` 转换得到（¶9）。
</details>

## 小结

| | `atomic<T>` | `atomic_ref<T>` |
|---|---|---|
| 对象何时是原子的 | 一直 | 只在有 `atomic_ref` 引用它期间 |
| 布局 | 可能与 `T` 不同 | 就是 `T` 本身 |
| 无锁性质 | 可以靠填充和对齐达到 | 受限于对象的大小，需满足 `required_alignment` |
| 复制 | 不可复制 | 可复制构造（复制的是引用），不可复制赋值 |
| 混用普通访问 | 不可能 | 引用期间禁止（UB） |
