---
title: vector<bool>
summary: vector<bool> 把每个元素压成一位，代价是 v[i] 返回代理对象而不是 bool&；它不连续、不满足容器要求，相邻元素的并发写还会构成数据竞争。
status: done
covers: *
related: vector, container.requirements, container.requirements.general, sequence.reqmts, views.contiguous, class.temporary, intro.races
tags: 标准库, 容器, vector<bool>, 代理引用, 数据竞争
updated: 2026-10-19
---

!!! tldr
    - `vector<bool>` 是 `vector` 的偏特化，推荐按位存储；`v[i]` 返回代理类 `reference`，`const_reference` 是 `bool`。
    - 因为一个位无法被引用，`bool& b = v[0];` 编译失败；泛型代码要写 `auto&&`。
    - `auto x = v[i];` 得到的是代理，它引用 vector 的存储，vector 销毁后就悬空。
    - 并发修改同一个容器的不同元素本来不构成数据竞争，`vector<bool>` 是唯一的例外。
    - libc++ 默认 ABI 下 `const_reference` 不是 `bool`，与标准不一致。

## 一个位无法被引用

```cpp title="no-bool-ref.cpp" error
#include <vector>
void f(std::vector<bool>& v) {
  bool& b = v[0];   // error: v[0] 是 vector<bool>::reference 纯右值
  (void)b;
}
```

`std::vector<bool>` 为了节省空间把每个元素压缩成一位。C++ 里最小的可寻址单位是字节，`bool&` 不能指向某个字节中的一位，所以 `operator[]` 只能返回一个**代理**（proxy）对象：它记住底层的字和位掩码，赋值时改那一位，转换成 `bool` 时读那一位。

这就让 `vector<bool>` 不满足容器要求中 `reference` 必须是 `T&` 的规定（[[container.requirements.general]]），也不是连续容器。它仍然叫 `vector`，泛型代码里写 `T& x = c[i];` 或 `for (T& x : c)` 的地方遇到它就编译失败。泛型的写法是 `auto&& x = c[i];` 和 `for (auto&& x : c)`，转发引用可以绑定代理纯右值。

## 偏特化（[vector.bool.pspc] ¶1–¶3）

¶1 为了优化空间，标准提供偏特化 `vector<bool, Allocator>`。接口与主模板几乎相同，区别集中在类型上：

| 成员 | 主模板 `vector<T>` | `vector<bool>` |
|---|---|---|
| `reference` | `T&` | 嵌套类 `reference`（代理） |
| `const_reference` | `const T&` | `bool`（按值） |
| `pointer`、`iterator` | 指向 `T` | 实现定义；迭代器不是连续迭代器 |
| `data()` | 有 | 没有 |
| 额外成员 | 无 | `flip()`、`reference::flip()` |

¶2 除下文另有说明外，所有操作的要求和语义与主模板相同，只是涉及 `bool` 值的操作映射到存储中的位，而且不使用 `allocator_traits::construct` 构造这些值。所以一个记录每次 `construct` 调用的分配器在 `vector<bool>` 上什么也记录不到，分配器只为底层的字分配存储。

¶3 标准不要求把数据存成连续的 `bool` 数组，推荐按位存储。这只是推荐，但主流实现都按位存储。

{{impl}} libc++ 以 `size_type`（本机 64 位）为存储单元。`sizeof(std::vector<bool>)` 是 24 字节（起始指针、位数、字容量）；只含一个元素的 `vector<bool>` 分配一个 8 字节的字，`capacity()` 是 64。

## 代理类 reference（¶4–¶11）

¶4 `reference` 是一个模拟对序列中单个位的引用的类。它的成员：

- ¶5–¶6 拷贝构造得到引用同一位的代理；析构什么也不做。
- ¶7–¶8 `operator=(bool)`、`operator=(const reference&)`，以及 `const` 限定的 `operator=(bool) const`：按实参的值设置或清除所引用的位。
- ¶9 `operator bool() const`：读出这一位。
- ¶10 `flip()`：等价于 `*this = !*this`。
- ¶11 三个友元 `swap`：`swap(reference, reference)`、`swap(reference, bool&)`、`swap(bool&, reference)`，效果如同 `bool b = x; x = y; y = b;`。

`const` 限定的赋值运算符是 C++23 加的。给 const 对象赋值看起来很怪，但对代理来说，赋值修改的是被代理的位，不是代理本身。C++20 的 `indirectly_writable` 要求通过 const 的引用类型也能写入，有了这个运算符，`vector<bool>` 的迭代器才能用于要求输出迭代器的 range 算法。

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
  r = true;               // 写到 v[1]
  assert(v[1]);
  v[0].flip();
  assert(!v[0]);
  using std::swap;
  swap(v[0], v[2]);       // 代理之间的 swap（友元函数）
  assert(v[0] && !v[2]);
  assert(std::format("{}", v[0]) == "true");   // [vector.bool.fmt]
}
```

### auto 与悬空代理

`auto x = v[i];` 推导出的是代理而不是 `bool`。代理里存着指向底层字的指针，如果它比 vector 活得久，就悬空了：

```cpp title="dangling-proxy.cpp" run ub
#include <vector>
#include <cstdio>
std::vector<bool> make() { return {true, false}; }
int main() {
  auto b = make()[0];             // b 是代理，指向临时 vector 的存储
  std::printf("%d\n", bool(b));   // UB: 临时 vector 已经销毁
}
```

临时对象 `make()` 在完整表达式结束时销毁（[[class.temporary]]），本机 AddressSanitizer 报告 `heap-use-after-free`。换成其他任何 `vector<T>`，`auto b = make()[0];` 都是一次安全的拷贝。修正的写法是 `bool b = make()[0];`。

## flip、hash 与格式化（¶12–¶14，[vector.bool.fmt]）

¶12 成员 `flip()` 把每个元素取反。实现可以按字取反，很快。

¶13 `hash<vector<bool, Allocator>>` 是启用的特化（[[unord.hash]]），`vector<bool>` 可以直接作为 `unordered_set` 的键。

¶14 仅用于阐述的变量模板 `is-vector-bool-reference<T>`：`T` 是某个 `vector<bool, Alloc>::reference`、并且这个 `vector<bool, Alloc>` 不是程序定义的特化时为真。

[vector.bool.fmt] 对满足 `is-vector-bool-reference` 的 `T` 提供 `formatter<T, charT>`，¶1–¶2 的 `parse` 和 `format` 都转发给内部的 `formatter<bool, charT>`。所以 `std::format("{}", v[0])` 输出 `true`，`std::format("{:d}", v[0])` 输出 `1`，和格式化真正的 `bool` 一样。

## 数据竞争的例外

一般规则是：并发修改同一个容器中的不同元素，不构成数据竞争（[[container.requirements.dataraces#2]]）。这条规则点名排除了 `vector<bool>`，第 3 段的注说明 `y[0] = true` 和 `y[1] = true` 并发执行可能构成数据竞争。

原因是硬件没有单独写一位的普通存储指令。设置一位就是对整个字做一次读、改、写，两个线程同时改同一个字里的不同位，会互相覆盖。用 `vector<bool>` 作为多线程的完成标志数组是一个常见的 bug，应当改用 `vector<char>`、`vector<std::atomic<bool>>`（大小固定后再并发使用），或者让每个线程负责不同的字。

## libc++ 与标准的差异

{{impl}} 本机 libc++ 中 `std::vector<bool>::const_reference` 不是 `bool`，而是内部类型 `std::__bit_const_reference<…>`，与 [vector.bool.pspc] 的类概要不一致。只有定义了 ABI 宏 `_LIBCPP_ABI_BITSET_VECTOR_BOOL_CONST_SUBSCRIPT_RETURN_BOOL`（ABI 版本 2 自动定义）时才是 `bool`；默认的 ABI 版本 1 为了二进制兼容保留了旧行为。`__bit_const_reference` 能隐式转换为 `bool`，所以实际影响很小，但 `static_assert(std::is_same_v<std::vector<bool>::const_reference, bool>)` 在 libc++ 上会失败。

## 为什么不删掉它

`vector<bool>` 的问题很早就有共识，多次有人提议弃用或改名，都没有被采纳。把它改回普通的 `vector`，所有依赖按位存储的现有代码会悄悄多用 8 倍内存，ABI 也会改变。

现在的做法是保留它，在新代码里绕开：需要定长位集合用 `std::bitset`；需要真正存 `bool` 的容器用 `std::vector<char>` 或 `std::deque<bool>`。

## 思考题

!!! question "思考题"
    对 `std::vector<bool> v`，`std::span<bool> s(v);` 能编译吗？`std::ranges::sort(v)` 呢？

<details markdown="1">
<summary>答案</summary>

`span<bool>` 不能。`span` 的区间构造函数要求实参是连续区间，而且元素引用类型要能当作 `bool` 的左值使用（[[views.contiguous]]），`vector<bool>` 两条都不满足。

`ranges::sort(v)` 可以。`sort` 要求随机访问区间并满足 `sortable`，后者建立在 `indirectly_swappable` 和 `indirectly_movable_storable` 之上。代理迭代器通过 `iter_swap`、`iter_move` 的定制和 const 赋值运算符满足了这些 concept。本机 Clang 23 + libc++ 两个结论都得到验证。
</details>

## 小结

- `vector<bool>` 的 `reference` 是代理类，`const_reference` 是 `bool`；它不连续，没有 `data()`，不使用 `allocator_traits::construct`。
- `auto x = v[i]` 得到代理，小心悬空；泛型代码用 `auto&&`。
- 并发写相邻元素可能产生数据竞争，这是容器数据竞争规则唯一的例外。
- `flip()`、启用的 `hash` 和 `formatter` 特化让它在实践中好用一些；libc++ 默认 ABI 的 `const_reference` 与标准不一致。
