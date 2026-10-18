---
title: vector
summary: std::vector 的完整契约——三指针物理模型、"[size, capacity) 里没有对象"、reserve 的不重新分配保证、几何增长从何而来、push_back 的强异常保证为何依赖 move_if_noexcept、失效规则、constexpr vector 与瞬态分配，以及 libc++ 的 2 倍增长、平凡重定位与 ASan 容器注解
status: done
covers: *, vector.syn
related: sequence.reqmts, container.requirements, container.requirements.general, vector.bool, inplace.vector, deque, views.contiguous, default.allocator, expr.const
tags: 标准库, 容器, vector, 迭代器失效, 异常安全, move_if_noexcept
updated: 2026-10-18
---

`std::vector` 是标准库的默认容器，也是最能体现"复杂度要求如何决定实现"的容器。它的规范正文很短——[vector] 只有六个子条款——因为大部分语义来自它满足的那几组要求（[[container.requirements.general]]、[[sequence.reqmts]]）。本页把这些要求与 [vector] 自己的补充条款合在一起，给出一份**完整**的契约。

`vector<bool>` 是一个语义迥异的偏特化，单独在 [[vector.bool]] 讨论。

## 物理模型：三个指针，两段内存

几乎所有实现都用三个指针表示 `vector`：

```text
 begin            end              end_cap
   │               │                  │
   ▼               ▼                  ▼
  ┌───┬───┬───┬───┬───┬───┬───┬───┐
  │ T │ T │ T │ T │   │   │   │   │      ← 一次 allocate(capacity()) 得到的存储
  └───┴───┴───┴───┴───┴───┴───┴───┘
  └─── size() 个活对象 ─┘└── 原始存储 ──┘
```

本机 libc++ 中 `sizeof(std::vector<int>) == 24`，正是三个指针。关键的法律事实：

- `allocator<T>::allocate(n)` 只开始**数组对象**的生命周期，不开始任何元素的生命周期（[[default.allocator]]）。元素靠 `allocator_traits::construct` 一个个建起来（[[container.requirements]] ¶3）。
- 因此 `[data() + size(), data() + capacity())` 中**没有任何 `T` 对象**。经由 `data()` 读写这段区域是 {{ub}}——哪怕内存"就在那儿"。

```cpp title="beyond-size.cpp" run ub
#include <vector>
#include <cstdio>

int main() {
  std::vector<int> v;
  v.reserve(8);
  v.push_back(1);
  int* p = v.data();
  std::printf("%d\n", p[3]);            // UB: [size, capacity) 中没有对象
}
```

libc++ 在 ASan 构建中为 `vector` 加了**容器注解**（container annotations）：它把 `[size, capacity)` 标记为"中毒"，于是上面这段代码报告 `container-overflow`。这是少见的、能在运行时抓到"越过 size 但未越过 capacity"的工具。

## 概述（[vector.overview]）

¶1：`vector` 是支持在**末尾**（摊还）常数时间插入和擦除的序列容器；中间插入和擦除为线性时间。存储自动管理，但可以给出提示以提高效率（即 `reserve`）。

¶2：`vector` 满足容器、可逆容器、分配器感知容器、序列容器（包括大部分可选操作）的要求，并且**元素类型不是 `bool` 时**满足连续容器要求。不提供的可选操作是 `push_front`、`prepend_range`、`pop_front`、`emplace_front`——它们做不到摊还常数（[[sequence.reqmts]] ¶70）。

¶3：迭代器满足 constexpr 迭代器要求。整个 `vector` 自 C++20 起可在常量求值中使用（见下文）。

¶4：若分配器满足*分配器完整性要求*（[[allocator.requirements.completeness]]），实例化 `vector` 时 `T` **可以不完整**；但在引用该特化的任何成员之前 `T` 必须完整。这条 C++17 引入的保证使递归数据结构成为可能：

```cpp title="vector-basics.cpp" run ok
#include <vector>
#include <cassert>

struct Node {
  int value;
  std::vector<Node> children;   // OK：Node 此处不完整，vector 允许（¶4）
};

constexpr int sum_squares(int n) {
  std::vector<int> v;
  for (int i = 1; i <= n; ++i) v.push_back(i * i);
  int s = 0;
  for (int x : v) s += x;
  return s;                     // v 的内存在常量求值结束前被释放：合法
}
static_assert(sum_squares(3) == 14);

int main() {
  std::vector<int> a(3);        // 3 个值初始化的 int：{0, 0, 0}
  std::vector<int> b{3};        // 初始化器列表构造函数优先：{3}
  assert(a.size() == 3 && b.size() == 1);

  std::vector<int> c{1, 2, 3, 4, 5, 6};
  auto n = std::erase_if(c, [](int x) { return x % 2 == 0; });   // C++20
  assert(n == 3 && (c == std::vector<int>{1, 3, 5}));

  Node root{1, {{2, {}}, {3, {}}}};
  assert(root.children.size() == 2);
}
```

`std::vector<int> b{3}` 是一个只有一个元素 3 的 vector：列表初始化时，初始化器列表构造函数在第一阶段就被优先考虑（[[over.match.list]]、[[dcl.init.list]]）。这是 `vector` 最著名的语法陷阱。

## 构造函数（[vector.cons]）

| 构造函数 | 前置条件 | 复杂度 |
|---|---|---|
| `explicit vector(const Allocator&) noexcept` | — | 常数（¶1–¶2） |
| `explicit vector(size_type n, const Allocator& = …)` | *Cpp17DefaultInsertable* | n 个 default-inserted 元素，线性（¶3–¶5） |
| `vector(size_type n, const T& value, const Allocator& = …)` | *Cpp17CopyInsertable* | 线性（¶6–¶8） |
| `vector(InputIterator first, InputIterator last, …)` | 见 [[sequence.reqmts]] | 见下 |
| `vector(from_range_t, R&& rg, …)` | 见 [[sequence.reqmts]] | 见下 |

¶10 对迭代器区间构造给出了一条罕见的、**直接提到重新分配次数**的复杂度：

!!! std
    It makes order N calls to the copy constructor of T and order log N reallocations if they are just input iterators.

    若只是输入迭代器，则调用 T 的拷贝构造函数 O(N) 次，重新分配 O(log N) 次。

对前向迭代器，则"只调用 N 次拷贝构造、不重新分配"——即先求距离、一次分配。O(log N) 次重新分配加上 O(N) 次拷贝，只有**几何增长**才能同时满足：若每次只多分配常数 k 个槽位，重新分配次数是 N/k，搬迁的拷贝总数是 O(N²)。

¶12–¶13 对 `from_range` 构造给出了 C++26 更新后的版本：恰好初始化 N 个元素；若 `R` 建模 `approximately_sized_range` 且 `ranges::distance(rg) <= ranges::reserve_hint(rg)`，或者 `R` 是前向区间但不建模 `approximately_sized_range`，则**不重新分配**；否则 O(log N) 次重新分配与 O(N) 次拷贝/移动构造。`reserve_hint` 让 `views::filter` 这类"只知道上界"的视图也能提供容量提示（[[range.approximately.sized]]）。

## 容量（[vector.capacity]）

### `capacity` 与 `reserve`

¶1：`capacity()` 是"不需要重新分配就能容纳的元素总数"。¶3–¶7 规定 `reserve(n)`：

- 前置条件：*Cpp17MoveInsertable*；
- 若 `n > capacity()`，**此时**重新分配，之后 `capacity() >= n`；否则 `capacity()` **不变**——`reserve` 永不缩小容量；
- `n > max_size()` 抛 `length_error`；若抛出其他异常（除不可拷贝 `T` 的移动构造抛出外），无效果；
- 重新分配使所有引用、指针、迭代器（含 end）失效。

¶7 最后一句是 `vector` 最有用的**正面**保证：

!!! std
    No reallocation shall take place during insertions that happen after a call to reserve() until an insertion would make the size of the vector greater than the value of capacity().

    调用 reserve() 之后的插入，在插入使 size 超过 capacity 之前，不得发生重新分配。

于是"先 `reserve(n)`，再 `push_back` 不超过 n 个元素"期间，**插入点之前**的指针和引用一直有效（插入点及之后仍按 [vector.modifiers] ¶2 失效，但 `push_back` 的插入点就是 end）。这是用 `vector` 安全地保存元素地址的唯一规范途径。

### `shrink_to_fit`、`swap`、`resize`

- `shrink_to_fit()`（¶8–¶11）是**不具约束力的请求**：可以把 `capacity()` 减到 `size()`，也可以什么都不做；但它不会增加容量。若发生重新分配，所有迭代器失效。本机 libc++ 实测：`clear()` 后容量仍为 100，`shrink_to_fit()` 后变为 0。
- `swap(vector&)`（¶12–¶13）交换内容**和** `capacity()`，常数时间，`noexcept(POCS || is_always_equal)`。
- `resize(sz)`（¶14–¶16）需要 *Cpp17MoveInsertable* 与 *Cpp17DefaultInsertable*；除不可拷贝 `T` 的移动构造抛出外，抛异常则无效果。`resize(sz, c)`（¶17–¶19）：抛异常则**一定**无效果。

!!! note "`clear()` 保留容量吗？"
    [vector] 本身没有一句话规定 `clear()` 后的 `capacity()`。[[sequence.reqmts]] ¶54 只说它销毁全部元素、`empty()` 为真。所有主流实现都保留容量（libc++ 实测如此），而 `reserve` 的"不缩小"与 `shrink_to_fit` 的"非约束请求"一起，使得"想真正释放内存"的惯用法是 `std::vector<T>().swap(v)` 或 `v = {}` 之后再 `shrink_to_fit()`。

## 数据（[vector.data]）

¶1：`data()` 返回的指针使 `[data(), data() + size())` 是有效区间；非空时 `data() == addressof(front())`。空 `vector` 的 `data()` 可以是空指针，也可以不是——只保证 `[data(), data())` 是有效（空）区间。把它传给要求非空指针的 C 接口之前，要先检查 `empty()`。

## 修改器（[vector.modifiers]）

### 复杂度与失效（¶1–¶2）

- 若发生重新分配：线性于结果 `vector` 的元素个数；否则线性于插入元素个数加上到末尾的距离。
- 新 size 大于旧容量时**一定**重新分配。重新分配使全部引用、指针、迭代器（含 end）失效；未重新分配时，**插入点之前**的保持有效，插入点及之后（含 end）失效。

```cpp title="range-for-push.cpp" run ub
#include <vector>

int main() {
  std::vector<int> v{1, 2, 3};
  for (int x : v)          // 范围 for 缓存了 begin()/end()
    v.push_back(x);        // UB: 第一次扩容后，缓存的迭代器全部失效
}
```

ASan 报告 `heap-use-after-free`。范围 `for` 被规定为在循环开始前求值并保存 `begin`/`end`（[[stmt.ranged]]），所以在循环体内改变容器大小几乎总是错的。

### 异常安全：`move_if_noexcept` 的来历（¶2）

!!! std
    If an exception is thrown while inserting a single element at the end and T is Cpp17CopyInsertable or is_nothrow_move_constructible_v<T> is true, there are no effects.

    在末尾插入单个元素时抛出异常：若 T 可拷贝插入或其移动构造不抛，则无效果。

拆成三层：

1. 抛出者**不是** `T` 的拷贝/移动构造、（移动）赋值，也不是 `InputIterator` 的操作（例如分配器抛 `bad_alloc`）：**无效果**。
2. 在末尾插入单个元素（`push_back`/`emplace_back`）：只要 `T` 可拷贝插入或移动构造不抛，**无效果**——这就是强异常保证。
3. 否则，若由**不可拷贝**的 `T` 的移动构造抛出：**效果未指明**。

第 2 条怎么实现？扩容时要把旧元素搬到新缓冲区。若用移动构造，而第 k 个元素的移动构造抛了，前 k−1 个旧元素已被"掏空"，无法回滚——强保证破产。所以实现必须：移动构造不抛就移动；否则只要可拷贝就**拷贝**（失败时扔掉新缓冲区即可，旧缓冲区原封未动）；两者都不行（只可移动且移动可能抛），才退回移动并放弃强保证（即第 3 条）。这个决策正是 `std::move_if_noexcept` 编码的逻辑。

```cpp title="move-if-noexcept.cpp" run ok
#include <vector>
#include <cstdio>

struct MayThrow {               // 移动构造未声明 noexcept
  MayThrow() = default;
  MayThrow(const MayThrow&) { std::puts("copy"); }
  MayThrow(MayThrow&&)      { std::puts("move"); }
};
struct NoThrow {
  NoThrow() = default;
  NoThrow(const NoThrow&) { std::puts("copy"); }
  NoThrow(NoThrow&&) noexcept { std::puts("move"); }
};

int main() {
  std::vector<MayThrow> a(1);
  std::puts("-- MayThrow: 扩容时搬迁旧元素");
  a.emplace_back();             // 旧元素被 copy
  std::vector<NoThrow> b(1);
  std::puts("-- NoThrow: 扩容时搬迁旧元素");
  b.emplace_back();             // 旧元素被 move
}
```

本机输出：`MayThrow` 的旧元素被 `copy`，`NoThrow` 的旧元素被 `move`。工程结论只有一句：**给你的移动构造函数加 `noexcept`**（或让编译器隐式生成，它会正确推导异常规格，[[except.spec]]），否则把它放进 `vector` 时扩容会退化为拷贝。

!!! warning "中间插入没有强保证"
    在中间 `insert`/`emplace` 时，若 `T` 的拷贝/移动构造或赋值抛出，标准**不**保证无效果——元素已经被挪动了一部分。需要强保证的调用者应先复制一份再在副本上操作。

### 区间插入最多重新分配一次（¶3）

`insert_range`/`append_range`：若 `R` 建模 `approximately_sized_range` 且 `distance <= reserve_hint`，或 `R` 是前向区间但不建模 `approximately_sized_range`，则最多重新分配一次；迭代器对版本在迭代器满足 *Cpp17ForwardIterator* 时最多一次。这禁止了"逐个 `push_back`"的朴素实现。

### 擦除（¶4–¶6）

- 使**擦除点及之后**的迭代器和引用失效（含 end）；
- 除 `T` 的（移动）赋值外不抛异常；
- `T` 的析构函数调用次数 = 擦除元素个数；赋值运算符调用次数 = **擦除点之后**的元素个数。后一条禁止了"擦除时整体搬迁到新缓冲区"的实现，`erase` 永不重新分配，所以擦除点之前的指针一定有效。

## 擦除（[vector.erasure]）

C++20 的非成员 `std::erase(c, value)` 与 `std::erase_if(c, pred)` 被规定为等价于 erase-remove 惯用法（`remove`/`remove_if` 后 `c.erase(it, c.end())`），返回擦除的元素个数。C++26 起 `erase` 的第二个模板参数 `U` 默认为 `T`，于是 `std::erase(v, {1, 2})`（`v` 为 `vector<pair<int,int>>`）这种花括号实参也能推导——但本机 libc++（clang 23）尚未跟进，仍报告无法推导 `_Up`。

## constexpr vector 与瞬态分配

C++20 起 `vector` 的全部成员都是 `constexpr`。但常量求值中分配的内存必须在**同一次**常量求值结束前释放（[[expr.const]]，[[g:transient-allocation]]）：

```cpp title="constexpr-vector-global.cpp" error
#include <vector>
constexpr std::vector<int> v{1, 2, 3};   // error: 分配的内存未在常量求值内释放
```

clang 的诊断是 `constexpr variable 'v' must be initialized by a constant expression`，附注 `pointer to subobject of heap-allocated object is not a constant expression`。在 `constexpr` 函数内部使用 `vector` 并只返回标量（如上面的 `sum_squares`）则完全合法。

## libc++ 实现笔记

{{impl}} 以下为本机 Homebrew clang 23 / libc++ 实测与源码阅读结果（`<__vector/vector.h>`）。

- **增长因子 2**：`__recommend(new_size)` 返回 `max(2 * capacity(), new_size)`（容量已过 `max_size()/2` 时返回 `max_size()`）。逐个 `push_back` 2000 次，容量序列为 1, 2, 4, 8, …, 2048。libstdc++ 同为 2 倍；MSVC STL 为 1.5 倍。标准只要求摊还常数，不规定因子。
- **`move_if_noexcept`**：扩容由 `__uninitialized_allocator_relocate` 完成，逐元素调用 `allocator_traits::construct(…, std::move_if_noexcept(*it))`，失败时由异常守卫销毁已构造的新元素——这正是上文强保证的实现。
- **平凡重定位**：若 `T` 被 libc++ 认为可平凡重定位（如 `int`、`unique_ptr`、`std::string` 等）且分配器的 `construct`/`destroy` 是平凡的，扩容直接 `memcpy` 旧缓冲区，不调用任何移动构造和析构。这在标准层面是"as-if"优化：可观察行为不变。
- **加固**：`_LIBCPP_HARDENING_MODE_DEBUG` 下，`operator[]` 越界报告 `libc++ Hardening assertion __n < size() failed: vector[] index out of bounds`，`front()` 在空容器上报告 `front() called on an empty vector`；`_FAST` 模式下 `operator[]` 越界直接陷阱终止，无消息。
- **ASan 容器注解**：见上文的 `container-overflow`。

## 常见误区

!!! pitfall "保存 `&v[i]`，然后继续 `push_back`"
    除非事先 `reserve` 足够容量，否则下一次扩容就让它悬空。需要稳定地址的场景：用 `reserve` 建立不扩容保证、改用 `deque`（两端插入不失效引用）、或存下标而不是指针。

!!! pitfall "`std::vector<T> v(n)` 然后 `push_back`"
    `vector(n)` 已经创建了 n 个元素，`push_back` 会把新元素放在**第 n+1 个**位置。只想预留空间应写 `v.reserve(n)`。

!!! pitfall "以为 `shrink_to_fit()` 一定释放内存"
    它是非约束请求（¶9）。在需要确定释放的场合，用"与空 `vector` 交换"的惯用法。

## 思考题

!!! question "1. `std::vector<std::unique_ptr<int>>::push_back` 有强异常保证吗？"

<details markdown="1">
<summary>展开查看答案与解析</summary>

有。`unique_ptr` 不可拷贝，但它的移动构造是 `noexcept` 的，满足 ¶2 中"`is_nothrow_move_constructible_v<T>` 为 true"的分支，所以在末尾插入单个元素抛异常（只可能是分配失败）时无效果。失去强保证的只有"只可移动且移动构造可能抛出"的类型——例如一个移动构造未声明 `noexcept`、拷贝构造又被删除的用户类型。
</details>

!!! question "2. `v.insert(v.begin(), x)` 未发生重新分配时，指向 `v[0]` 的引用 `r` 还有效吗？它现在引用哪个元素？"

<details markdown="1">
<summary>展开查看答案与解析</summary>

**失效。** ¶2：未重新分配时，"插入点及之后"的引用都失效，`v[0]` 就在插入点上。虽然物理上 `r` 仍指向同一块内存、那里有一个活着的 `int`（新插入的 `x`），标准仍宣布它失效——失效的含义是"不再保证指向原来的元素"，标准不为这种情况提供"它现在指向谁"的保证。实践中你会读到 `x`，但依赖它就是依赖实现细节；对于有非平凡赋值的类型，插入点处的对象甚至可能经历了"析构后重建"而不只是赋值，这时旧引用能否继续使用还要看 [[basic.life]] ¶9–¶10 的透明替换规则。
</details>

## 小结

| 方面 | 规则 |
|---|---|
| 存储 | 一块连续存储；`[size, capacity)` 中**没有对象** |
| 增长 | 标准要求摊还常数（并在区间构造中明说 O(log N) 次重新分配），事实上强制几何增长；libc++ 2 倍 |
| `reserve` | 只增不减；之后到容量用尽前的插入**保证**不重新分配 |
| 失效 | 重新分配：全部；否则插入/擦除点及之后（含 end） |
| 异常 | 尾部单元素插入：强保证当且仅当 `T` 可拷贝或移动不抛；中间插入无强保证 |
| `erase` | 从不重新分配；赋值次数 = 擦除点之后的元素数 |
| constexpr | C++20 起全部 constexpr；分配必须在同一次常量求值内释放 |
