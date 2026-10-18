---
title: vector<bool>
summary: vector<bool> 偏特化为何"不是容器"——代理引用 reference、const_reference 是 bool、不经由 allocator_traits::construct、不连续、相邻元素并发写构成数据竞争；以及 flip、hash、formatter 特化和 libc++ 的按字存储与不一致之处
status: done
covers: *
related: vector, container.requirements, container.requirements.general, sequence.reqmts, views.contiguous, class.temporary, intro.races
tags: 标准库, 容器, vector<bool>, 代理引用, 数据竞争
updated: 2026-10-18
---

`std::vector<bool>` 是 C++98 留下的一个著名妥协：为了节省空间，标准为 `vector` 的 `bool` 元素提供了一个**偏特化**，把每个元素压缩成一个位。代价是它不能返回 `bool&`——你没法引用一个位——于是它不满足容器要求中 `reference` 必须是 `T&` 的条款（[[container.requirements.general]]），也不是连续容器。它仍然叫 `vector`，这让泛型代码在它身上屡屡翻车。

## 偏特化与"按位存储"（[vector.bool.pspc] ¶1–¶3）

¶1：为了优化空间分配，提供 `vector<bool, Allocator>` 偏特化。它的接口和主模板几乎一致，差别集中在类型上：

| 成员 | 主模板 `vector<T>` | `vector<bool>` |
|---|---|---|
| `reference` | `T&` | 嵌套类 `reference`（代理） |
| `const_reference` | `const T&` | **`bool`**（按值） |
| `pointer` / `iterator` | 指向 `T` | 实现定义；迭代器不建模 `contiguous_iterator` |
| `data()` | 有 | **没有** |
| `emplace_back` 等 | 构造 `T` | 映射为设置位 |
| 额外成员 | — | `flip()`；`reference::flip()` |

¶2：除下文另有说明外，所有操作的要求与语义同主模板；区别是涉及 `bool` 值的操作映射到容器存储中的**位**，而且**不使用 `allocator_traits::construct`** 构造这些值。所以给 `vector<bool>` 配一个"记录每次 `construct`"的分配器，你什么也看不到——分配器只为底层的字（word）分配存储。

¶3：**不要求**数据存储为连续的 `bool` 数组；推荐采用按位的空间优化表示。注意措辞是"推荐"：标准并不强制按位存储，但所有主流实现都按位存储。

{{impl}} libc++ 以 `size_type`（本机 64 位）为存储单元：`sizeof(std::vector<bool>) == 24`（起始指针、位数、字容量），第一次 `push_back` 分配 1 个 8 字节的字，此时 `capacity() == 64`。

## 代理引用 `reference`（¶4–¶11）

¶4：`reference` 是一个"模拟对序列中单个位的引用"的类。它的成员：

- 复制构造（¶5）：引用同一个位；析构（¶6）什么也不做；
- `operator=(bool)`、`operator=(const reference&)`，以及 C++23 起的 **`const` 限定**的 `operator=(bool) const`（¶7）：设置或清除所引用的位；
- `operator bool() const`（¶9）：读出该位；
- `flip()`（¶10）：等价于 `*this = !*this`；
- 三个 `swap`（¶11）：`swap(reference, reference)`、`swap(reference, bool&)`、`swap(bool&, reference)`，在当前草案中是**友元**函数，按"`bool b = x; x = y; y = b;`"交换两侧的值。

`const` 限定的赋值运算符看起来古怪——给 `const` 对象赋值？它存在的理由是让 `vector<bool>::reference` 满足 C++20 的 `indirectly_writable`：该 concept 要求通过 `const` 的 `iter_reference_t` 也能写入，这对代理引用意味着"赋值不修改代理本身，只修改被代理的位"。没有它，`vector<bool>` 的迭代器在 C++20 range 算法里就不是输出迭代器。

```cpp title="vector-bool-proxy.cpp" run ok
#include <vector>
#include <type_traits>
#include <format>
#include <cassert>
#include <ranges>

static_assert(!std::is_same_v<std::vector<bool>::reference, bool&>);
static_assert(!std::ranges::contiguous_range<std::vector<bool>>);

int main() {
  std::vector<bool> v{true, false, true};
  auto r = v[1];          // r 是 vector<bool>::reference，不是 bool
  r = true;               // 写穿到 v[1]
  assert(v[1]);
  v[0].flip();
  assert(!v[0]);
  using std::swap;
  swap(v[0], v[2]);       // 代理之间的 swap（友元函数）
  assert(v[0] && !v[2]);
  assert(std::format("{}", v[0]) == "true");   // [vector.bool.fmt]
}
```

### `auto` 与悬空代理

`auto x = v[i];` 推导出的是**代理**而不是 `bool`。代理内部存着指向底层字的指针和位掩码；如果它活得比 `vector` 还久，就悬空了：

```cpp title="dangling-proxy.cpp" run ub
#include <vector>
#include <cstdio>
std::vector<bool> make() { return {true, false}; }
int main() {
  auto b = make()[0];     // b 是代理，指向临时 vector 的存储
  std::printf("%d\n", bool(b));   // UB: 临时对象已在完整表达式结束时销毁
}
```

临时对象 `make()` 在完整表达式结束时被销毁（[[class.temporary]]），ASan 报告 `heap-use-after-free`。换成任何其他 `vector<T>`，`auto b = make()[0];` 都是安全的**拷贝**。修复方法：`bool b = make()[0];`。

### 不能绑定 `bool&`

```cpp title="no-bool-ref.cpp" error
#include <vector>
void f(std::vector<bool>& v) {
  bool& b = v[0];     // error: 无法把 bool& 绑定到 vector<bool>::reference 纯右值
  (void)b;
}
```

泛型代码中写 `T& x = c[i];` 或 `for (T& x : c)` 的地方，遇到 `vector<bool>` 就编译失败。正确的泛型写法是 `auto&& x = c[i];` / `for (auto&& x : c)`——转发引用能绑定代理纯右值。

## 整体翻转、哈希与格式化（¶12–¶14，[vector.bool.fmt]）

- `flip()`（¶12）：把每个元素取反。`noexcept`，按字取反，很快。
- `hash<vector<bool, Allocator>>`（¶13）是**启用的**特化（[[unord.hash]]），可以直接作为 `unordered_set` 的键。
- ¶14 定义了仅用于阐述的变量模板 `is-vector-bool-reference<T>`：当 `T` 是某个 `vector<bool, Alloc>::reference` 且该 `vector<bool, Alloc>` 不是程序定义的特化时为真。
- [vector.bool.fmt]：对满足 `is-vector-bool-reference` 的 `T` 提供 `formatter<T, charT>`，其 `parse`/`format` 都转发给内部的 `formatter<bool, charT>`（¶1–¶2）。于是 `std::format("{}", v[0])` 输出 `true`，`std::format("{:d}", v[0])` 输出 `1`，就像格式化真正的 `bool`。没有这个特化，代理类型需要先显式转换成 `bool`。

## 数据竞争：唯一的例外

[container.requirements.dataraces] ¶2 要求"并发修改同一容器中不同元素不构成数据竞争"，并**点名排除** `vector<bool>`；¶3 的注说明 `y[0] = true` 与 `y[1] = true` 并发执行可能构成数据竞争（[[container.requirements]]）。原因是硬件上不存在"写一个位"的操作：设置一位就是对整个字做非原子的读-改-写，两个线程同时改同一字中的不同位会互相覆盖。用 `vector<bool>` 作为多线程的"完成标志数组"是经典 bug；应改用 `vector<char>`、`vector<std::atomic<bool>>`（需固定大小）或按字分区。

## libc++ 的偏差

{{impl}} 本机 libc++ 中 `std::vector<bool>::const_reference` **不是** `bool`，而是内部类型 `std::__bit_const_reference<…>`——这与 [vector.bool.pspc] 的概要不一致。源码中只有定义了 ABI 宏 `_LIBCPP_ABI_BITSET_VECTOR_BOOL_CONST_SUBSCRIPT_RETURN_BOOL`（ABI 版本 2 时自动定义）才改为 `bool`；默认的 ABI 版本 1 为了二进制兼容保留了旧行为。实践影响很小（`__bit_const_reference` 能隐式转换为 `bool`），但 `static_assert(std::is_same_v<std::vector<bool>::const_reference, bool>)` 在 libc++ 上会失败。

## 为什么不删掉它

`vector<bool>` 的问题在 C++ 社区早有共识，曾有提案主张弃用或改名，但都没有通过：一旦把它改回"普通的 `vector`"，所有依赖按位存储（内存占用 1/8）的现有代码会悄悄变成 8 倍内存，并且 ABI 改变。标准的选择是保留它，同时在新设施中绕开：需要按位集合时用 `std::bitset`（定长）；需要真正的 `bool` 容器时用 `std::vector<char>` 或 `std::deque<bool>`。

## 思考题

!!! question "`std::span<bool> s(v);` 对 `std::vector<bool> v` 能编译吗？`std::ranges::sort(v)` 呢？"

<details markdown="1">
<summary>展开查看答案与解析</summary>

`span<bool>` 不能：`span` 的区间构造函数要求 `contiguous_range` 且引用类型可转换为 `bool&`（[[views.contiguous]]），`vector<bool>` 两条都不满足。`ranges::sort(v)` 可以：`sort` 要求 `random_access_range` 与 `sortable`，后者基于 `indirectly_swappable`/`indirectly_movable_storable`，代理引用通过 `iter_swap`/`iter_move` 的定制与 `const` 赋值运算符满足这些 concept——这正是 C++20 为代理迭代器所做的铺垫。
</details>

## 小结

- `vector<bool>` 的 `reference` 是代理类，`const_reference` 是 `bool`；不连续，没有 `data()`；不经由 `allocator_traits::construct`。
- `auto x = v[i]` 得到代理——注意悬空；泛型代码用 `auto&&`。
- 相邻元素的并发写会产生数据竞争，这是容器数据竞争规则的唯一例外。
- `flip()`、启用的 `hash`、C++23 的 `formatter` 特化让它在实践中好用一些；libc++ 默认 ABI 的 `const_reference` 与标准不一致。
