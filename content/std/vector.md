---
title: vector
summary: std::vector 的完整契约：一块连续存储里只有前 size 个元素是对象，扩容为什么必须按倍数增长，reserve 保证什么，插入和擦除让哪些迭代器失效，push_back 的强异常保证为什么依赖 noexcept 移动构造。
status: done
covers: *, vector.syn
related: sequence.reqmts, container.requirements, container.requirements.general, vector.bool, inplace.vector, deque, views.contiguous, default.allocator, expr.const
tags: 标准库, 容器, vector, 迭代器失效, 异常安全, move_if_noexcept
updated: 2026-10-19
---

!!! tldr
    - `vector` 持有一块连续存储，只有前 `size()` 个位置上有对象；经由 `data()` 访问 `[size, capacity)` 是未定义行为。
    - 标准的复杂度要求（末尾插入摊还常数、区间构造 O(log N) 次重新分配）迫使实现按倍数扩容；libc++ 的倍数是 2。
    - `reserve(n)` 之后，只要元素数不超过容量，插入就保证不重新分配，已有元素的地址保持不变。
    - 重新分配使所有迭代器失效；否则插入或擦除只让操作点及之后的迭代器失效。
    - 末尾插入单个元素有强异常保证，前提是 `T` 可拷贝或者移动构造不抛异常。移动构造没有 `noexcept` 的类型，扩容时会被拷贝而不是移动。

`std::vector` 是标准库的默认序列容器。[vector] 本身只有六个子条款，因为它的大部分语义来自它满足的几组通用要求：容器要求（[[container.requirements.general]]）和序列容器要求（[[sequence.reqmts]]）。[vector] 只补充这些要求没有覆盖、或需要额外说明的操作。

`vector<bool>` 是一个行为很不一样的偏特化，见 [[vector.bool]]。

## 内存里有什么

几乎所有实现都用三个指针表示一个 `vector`：

```text
 begin            end              end_cap
   │               │                  │
   ▼               ▼                  ▼
  ┌───┬───┬───┬───┬───┬───┬───┬───┐
  │ T │ T │ T │ T │   │   │   │   │      ← 一次 allocate(capacity()) 得到的存储
  └───┴───┴───┴───┴───┴───┴───┴───┘
  └─── size() 个对象 ──┘└─ 原始存储 ─┘
```

本机 libc++ 中 `sizeof(std::vector<int>) == 24`，正好是三个指针。`size()` 是元素个数，`capacity()` 是不重新分配就能容纳的元素个数。**重新分配**（reallocation）指申请一块更大的存储，把元素搬过去，再释放旧存储。

`allocator<T>::allocate(n)` 只开始一个数组对象的生命周期，不创建任何元素（[[default.allocator]]）。元素由容器通过 `allocator_traits::construct` 逐个构造（[[container.alloc.reqmts]]）。所以 `[data() + size(), data() + capacity())` 这段存储里没有 `T` 对象，经由 `data()` 读写它是未定义行为，即使内存确实已经分配：

```cpp title="beyond-size.cpp" run ub
#include <vector>
#include <cstdio>

int main() {
  std::vector<int> v;
  v.reserve(8);
  v.push_back(1);
  int* p = v.data();
  std::printf("%d\n", p[3]);   // UB: [size, capacity) 中没有对象
}
```

libc++ 在 AddressSanitizer 构建中给 `vector` 加了容器注解：把 `[size, capacity)` 标记为不可访问。本机用 `-fsanitize=address` 运行上面的程序，报告 `container-overflow`。这是少数能在运行时抓住"越过 size、没越过 capacity"的工具。

## 概述（[vector.overview]）

¶1 `vector` 支持在末尾以摊还常数时间插入和擦除；在中间插入和擦除是线性时间。存储自动管理，程序可以给出提示提高效率，也就是 `reserve`。

¶2 `vector` 满足容器、可逆容器、分配器感知容器和序列容器的要求，元素类型不是 `bool` 时还满足连续容器的要求。序列容器的可选操作中，它不提供 `push_front`、`prepend_range`、`pop_front`、`emplace_front`，因为这些操作在 `vector` 上做不到摊还常数时间（[[sequence.reqmts#70]]）。

¶3 迭代器满足 constexpr 迭代器的要求。C++20 起 `vector` 的全部成员都是 `constexpr`，见下文。

¶4 如果分配器满足分配器完整性要求（[[allocator.requirements.completeness]]，`std::allocator` 满足），实例化 `vector<T>` 时 `T` 可以是不完整类型，只要在用到它的任何成员之前 `T` 已经完整。这条 C++17 的保证让递归数据结构可以直接写：

```cpp title="vector-basics.cpp" run ok
#include <vector>
#include <cassert>

struct Node {
  int value;
  std::vector<Node> children;   // OK：Node 此处不完整（¶4）
};

int main() {
  std::vector<int> a(3);        // 3 个值初始化的 int：{0, 0, 0}
  std::vector<int> b{3};        // 初始化器列表构造函数优先：{3}
  assert(a.size() == 3 && b.size() == 1);

  Node root{1, {{2, {}}, {3, {}}}};
  assert(root.children.size() == 2);
}
```

`b{3}` 是只有一个元素 3 的 vector。列表初始化时，初始化器列表构造函数在第一轮就被优先考虑（[[over.match.list]]），只有它不可行时才考虑其他构造函数。要 3 个元素就用圆括号。

## 为什么必须按倍数扩容（[vector.cons]）

| 构造函数 | 前置条件 | 复杂度 |
|---|---|---|
| `explicit vector(const Allocator&) noexcept` | 无 | 常数（¶1–¶2） |
| `explicit vector(size_type n, const Allocator& = …)` | *Cpp17DefaultInsertable* | n 个默认插入的元素，线性（¶3–¶5） |
| `vector(size_type n, const T& value, const Allocator& = …)` | *Cpp17CopyInsertable* | 线性（¶6–¶8） |
| `vector(InputIterator first, InputIterator last, …)` | 见 [[sequence.reqmts]] | 见下 |
| `vector(from_range_t, R&& rg, …)` | 见 [[sequence.reqmts]] | 见下 |

¶10 迭代器区间构造的复杂度少见地直接提到了重新分配的次数。迭代器满足 *Cpp17ForwardIterator* 时，只调用 N 次拷贝构造，不重新分配，也就是先求出距离再一次分配。如果只是输入迭代器，长度事先不可知：

!!! std
    It makes order N calls to the copy constructor of T and order log N reallocations if they are just input iterators.

O(log N) 次重新分配，同时总共只有 O(N) 次拷贝，只有几何增长能做到。假设每次只多分配固定的 k 个位置，重新分配的次数是 N/k，每次都要搬运已有的全部元素，拷贝总数是 O(N²)。按倍数增长时，第 i 次搬运的元素数构成等比数列，总和是 O(N)。末尾插入的摊还常数时间也是同一个道理。

¶11–¶13 `from_range` 构造恰好初始化 N 个元素。以下两种情况不重新分配：`R` 建模 `approximately_sized_range` 且 `ranges::distance(rg) <= ranges::reserve_hint(rg)`，或者 `R` 是前向区间但不建模 `approximately_sized_range`（可以先遍历一遍求长度）。其余情况是 O(log N) 次重新分配和 O(N) 次拷贝或移动构造。`reserve_hint` 让 `views::filter` 这类只知道长度上界的视图也能提供容量提示（[[range.approximately.sized]]）。

## 容量（[vector.capacity]）

### reserve 的保证

¶1 `capacity()` 是不需要重新分配就能容纳的元素总数。

¶3–¶7 `reserve(n)` 的规则：

- 前置条件是 `T` 可移动插入（*Cpp17MoveInsertable*）。
- 当且仅当 `n > capacity()` 时，在此刻重新分配，之后 `capacity() >= n`；否则 `capacity()` 不变。`reserve` 从不缩小容量。
- `n > max_size()` 时抛 `length_error`。抛出其他异常时没有效果，除非异常来自一个不可拷贝类型的移动构造。
- 重新分配使所有引用、指针、迭代器失效，包括尾后迭代器。

¶7 的最后一句是 `vector` 最有用的正面保证：

!!! std
    No reallocation shall take place during insertions that happen after a call to reserve() until an insertion would make the size of the vector greater than the value of capacity().

先 `reserve(n)`，再插入不超过 n 个元素，这期间不会重新分配。`push_back` 的插入点是末尾，所以已有元素的指针和引用一直有效。这是在 `vector` 里安全保存元素地址的规范途径。

### shrink_to_fit、swap、resize

¶8–¶11 `shrink_to_fit()` 是一个不具约束力的请求：实现可以把容量减到 `size()`，也可以什么都不做，但不会增加容量。如果发生了重新分配，所有迭代器失效。

¶12–¶13 `swap` 交换内容和容量，常数时间。

¶14–¶19 `resize(sz)` 需要 `T` 可移动插入、可默认插入。`resize(sz)` 抛异常时没有效果（同样除去不可拷贝类型移动构造抛出的情况）；`resize(sz, c)` 抛异常时一定没有效果。

!!! note "`clear()` 之后容量是多少"
    [vector] 没有规定。[[sequence.reqmts#54]] 只说 `clear()` 销毁全部元素、之后 `empty()` 为真。主流实现都保留容量：本机 libc++ 上 `vector<int>(100)` 在 `clear()` 后容量仍是 100，再 `shrink_to_fit()` 后是 0。想确定地释放内存，可以写 `std::vector<T>().swap(v);`，让 `v` 和一个空 vector 交换存储。

## data（[vector.data]）

¶1 `data()` 返回的指针使 `[data(), data() + size())` 是有效区间；非空时 `data() == addressof(front())`。

空 vector 的 `data()` 可以是空指针，也可以不是，标准只保证 `[data(), data())` 是有效的空区间。本机 libc++ 上一个从未分配过的空 vector 返回空指针。把它传给要求非空指针的 C 接口（比如 `memcpy`，即使长度为 0）之前，要先检查 `empty()`。

## 插入（[vector.modifiers]）

### 复杂度与失效（¶1–¶2）

¶1 插入时如果重新分配，耗时与结果 vector 的元素数成线性；否则与插入的元素数加上插入点到末尾的距离成线性。

¶2 新的 size 大于旧容量时一定重新分配，这会让所有引用、指针、迭代器失效，包括尾后迭代器。没有重新分配时，插入点之前的保持有效，插入点及之后的（包括尾后迭代器）失效。

```cpp title="range-for-push.cpp" run ub
#include <vector>

int main() {
  std::vector<int> v{1, 2, 3};
  for (int x : v)          // 范围 for 缓存了 begin() 和 end()
    v.push_back(x);        // UB: 第一次扩容后，缓存的迭代器全部失效
}
```

范围 `for` 在循环开始前求值并保存 `begin` 和 `end`（[[stmt.ranged]]），所以在循环体里改变容器大小几乎总是错的。本机 AddressSanitizer 报告 `heap-use-after-free`。

### 强异常保证与 move_if_noexcept（¶2）

¶2 后半段规定了插入抛出异常时的结果，分三层：

1. 异常不是来自 `T` 的拷贝构造、移动构造、拷贝赋值、移动赋值，也不是来自输入迭代器的操作（例如分配器抛出 `bad_alloc`）：没有效果。
2. 在末尾插入单个元素（`push_back`、`emplace_back`）时，只要 `T` 可拷贝插入，或者 `is_nothrow_move_constructible_v<T>` 为真：没有效果。这就是强异常保证。
3. 否则，如果异常来自不可拷贝的 `T` 的移动构造：效果未指定。

第 2 层的难点在扩容：旧元素要搬到新存储里。如果用移动构造搬，而第 k 个元素的移动构造抛出了异常，前 k−1 个旧元素已经被移走，无法恢复原状。如果用拷贝构造搬，出错时丢掉新存储即可，旧存储原封未动。

所以实现的选择是：移动构造不抛异常就移动；否则只要能拷贝就拷贝；两者都不行（只能移动，而且移动可能抛出）才退回移动，放弃强保证，这就是第 3 层。标准库函数 `std::move_if_noexcept` 编码的正是这个决策。

```cpp title="move-if-noexcept.cpp" run ok
#include <vector>
#include <cstdio>

struct MayThrow {               // 移动构造没有 noexcept
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
  std::puts("-- MayThrow");
  a.emplace_back();             // 扩容，旧元素被拷贝
  std::vector<NoThrow> b(1);
  std::puts("-- NoThrow");
  b.emplace_back();             // 扩容，旧元素被移动
}
```

本机输出依次是 `-- MayThrow`、`copy`、`-- NoThrow`、`move`。实践中的结论是：移动构造函数应当是 `noexcept` 的。隐式生成的移动构造会自动得到正确的异常说明（[[except.spec]]）；手写的要自己加上，否则放进 `vector` 后每次扩容都会拷贝。

!!! warning "中间插入没有强保证"
    在中间 `insert` 或 `emplace` 时，如果 `T` 的拷贝、移动构造或赋值抛出异常，标准不保证没有效果，因为部分元素可能已经挪动过。需要强保证时，先在副本上操作，成功后再交换。

### 区间插入最多重新分配一次（¶3）

¶3 `insert_range`、`append_range` 在与区间构造相同的两种条件下（见上文 ¶13），最多重新分配一次；迭代器对版本在迭代器满足 *Cpp17ForwardIterator* 时最多一次。这排除了逐个 `push_back` 的朴素实现。

## 擦除（[vector.modifiers]、[vector.erasure]）

¶4–¶6 `erase` 和 `pop_back`：

- 使擦除点及之后的迭代器和引用失效，包括尾后迭代器；
- 除了 `T` 的拷贝赋值或移动赋值，不抛异常；
- `T` 的析构函数调用次数等于擦除的元素数，赋值运算符调用次数等于擦除点之后的元素数。

第三条规定的是"把后面的元素逐个往前赋值"这种实现，排除了搬到新存储的做法。所以 `erase` 从不重新分配，擦除点之前的指针一定有效。

[vector.erasure] ¶1–¶2 C++20 的非成员函数 `std::erase(c, value)` 和 `std::erase_if(c, pred)` 等价于 remove-erase 惯用法：先 `remove` 或 `remove_if`，再 `c.erase(it, c.end())`，返回擦除的元素个数。

```cpp run ok
#include <vector>
#include <cassert>

int main() {
  std::vector<int> c{1, 2, 3, 4, 5, 6};
  auto n = std::erase_if(c, [](int x) { return x % 2 == 0; });
  assert(n == 3 && (c == std::vector<int>{1, 3, 5}));
}
```

当前草案中 `erase` 的第二个模板参数写成 `class U = T`，于是对 `vector<pair<int, int>>` 也可以写 `std::erase(v, {1, 2})`，花括号实参按 `T` 推导。本机 libc++ 还没有这个默认实参，这样写会报 no matching function。

## constexpr vector

C++20 起 `vector` 可以在常量求值中使用，但常量求值中分配的内存必须在同一次常量求值结束前释放（[[expr.const]]，见 [[g:transient-allocation]]）。在 `constexpr` 函数里用 `vector`、只返回一个标量，是合法的；`constexpr` 变量本身是 `vector` 就不行：

<div class="compare" markdown="1">

```cpp run ok
#include <vector>
constexpr int sum_squares(int n) {
  std::vector<int> v;
  for (int i = 1; i <= n; ++i)
    v.push_back(i * i);
  int s = 0;
  for (int x : v) s += x;
  return s;   // v 已在函数内释放
}
static_assert(sum_squares(3) == 14);
```

```cpp run error
#include <vector>
// error: 分配的内存没有在
// 常量求值结束前释放
constexpr std::vector<int> v{1, 2, 3};
```

</div>

Clang 对右边的诊断是 `constexpr variable 'v' must be initialized by a constant expression`。

## libc++ 实现

{{impl}} 以下是本机 Homebrew Clang 23 + libc++ 的实测和源码阅读结果（`<__vector/vector.h>`）。

- **增长因子 2**：需要扩容时，新容量取 `max(2 * capacity(), new_size)`，接近 `max_size()` 时取 `max_size()`。逐个 `push_back` 2000 次，容量依次是 1, 2, 4, …, 2048。libstdc++ 也是 2 倍，MSVC STL 是 1.5 倍。标准只要求摊还常数，不规定倍数。
- **搬运**：扩容时逐个元素调用 `allocator_traits::construct(…, std::move_if_noexcept(*it))`，出错时由异常守卫销毁已经构造的新元素，这就是上文强保证的实现。
- **平凡重定位**：如果 libc++ 认为 `T` 可以平凡重定位（可平凡复制的类型，以及 libc++ 显式标记的 `unique_ptr`、`string` 等），并且分配器的 `construct`、`destroy` 是默认的，扩容时直接 `memcpy` 旧存储，不调用移动构造和析构。按 as-if 规则，这不改变可观察行为。
- **加固模式**：`-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_DEBUG` 下，`operator[]` 越界会打印 `vector[] index out of bounds` 并终止；`_FAST` 模式下直接陷入终止，不打印消息。
- **容器注解**：见开头的 `container-overflow`。

## 常见误解

!!! pitfall "保存 `&v[i]` 后继续 `push_back`"
    除非事先 `reserve` 了足够的容量，下一次扩容就会让这个指针悬空。需要稳定地址时，可以用 `reserve` 建立不扩容保证，改用 `deque`（在两端插入不会让元素的引用失效），或者保存下标而不是指针。

!!! pitfall "`std::vector<T> v(n);` 之后再 `push_back`"
    `v(n)` 已经创建了 n 个元素，`push_back` 把新元素放在第 n+1 个位置。只想预留空间应当写 `v.reserve(n)`。

!!! pitfall "`shrink_to_fit()` 一定释放内存"
    它是不具约束力的请求（¶9）。需要确定释放时，用与空 vector 交换的写法。

## 思考题

!!! question "思考题 1"
    `std::vector<std::unique_ptr<int>>::push_back` 有强异常保证吗？

<details markdown="1">
<summary>答案</summary>

有。`unique_ptr` 不可拷贝，但它的移动构造是 `noexcept` 的，满足 ¶2 中 `is_nothrow_move_constructible_v<T>` 为真的条件。所以在末尾插入单个元素时如果抛出异常（只可能是分配失败），没有效果。失去强保证的只有只能移动、而且移动构造可能抛出的类型，例如拷贝构造被删除、移动构造没有声明 `noexcept` 的用户类型。
</details>

!!! question "思考题 2"
    `v.insert(v.begin(), x)` 没有重新分配。之前绑定到 `v[0]` 的引用 `r` 还有效吗？

<details markdown="1">
<summary>答案</summary>

无效。按 ¶2，没有重新分配时，插入点及之后的引用都失效，`v[0]` 就在插入点上。物理上 `r` 仍指向同一块内存，那里现在是新插入的 `x`，但标准不保证失效的引用指向什么。实际运行多半能读到 `x`，依赖这一点就是依赖实现细节。
</details>

## 小结

| 方面 | 规则 |
|---|---|
| 存储 | 一块连续存储；`[size, capacity)` 中没有对象 |
| 增长 | 复杂度要求迫使实现按倍数增长；libc++ 是 2 倍 |
| `reserve` | 只增不减；之后到容量用尽之前的插入保证不重新分配 |
| 失效 | 重新分配：全部失效；否则插入点或擦除点及之后失效（含尾后迭代器） |
| 异常 | 末尾单元素插入：`T` 可拷贝或移动不抛时有强保证；中间插入没有 |
| `erase` | 从不重新分配；赋值次数等于擦除点之后的元素数 |
| constexpr | C++20 起可在常量求值中使用；分配必须在同一次常量求值内释放 |
