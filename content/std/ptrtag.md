---
title: 指针标记 pointer_tag_pair
summary: C++26 之后加入草案的 pointer_tag_pair，把一个小整数存进对齐指针空闲的低位；它和原指针一样大、可平凡复制，还能在常量求值中使用。
status: done
covers: *
since: c++29
related: ptr.align, basic.compound, basic.align, expr.reinterpret.cast, pointer.traits, memory, tuple.helper
tags: 标准库, 指针标记, 对齐, constexpr
papers: P3125R6
updated: 2026-10-19
---

!!! tldr
    - 指向 8 字节对齐对象的指针，低 3 位总是 0，可以用来存一个 0–7 的标记。`std::pointer_tag_pair` {{c++29}} 把这个技巧做成了有明确契约的标准类型。
    - 手写版本要经过整数做位运算，结果由实现定义，也不能在常量求值中使用；`pointer_tag_pair` 的构造和访问都是 `constexpr`。
    - 它的大小和对齐与原指针相同，可平凡复制，所以能放进 `std::atomic`，一次 CAS 同时更新指针和标记。
    - 能用几位由 `pointer_bits_available(alignof(T))` 决定，通常就是对齐值末尾 0 的个数。
    - `tagged_pointer()` 返回编码后的原始指针，只能原样交还给 `from_tagged`，不能解引用。

## 手写的指针标记

```cpp run impl
#include <cassert>
#include <cstdint>

struct alignas(8) Node { int v; };

// 手写的标记指针：低 3 位存标记
struct TaggedNode {
  std::uintptr_t bits;
  TaggedNode(Node* p, unsigned tag)
      : bits(reinterpret_cast<std::uintptr_t>(p) | tag) {
    assert(tag < 8);
  }
  Node* ptr() const {
    return reinterpret_cast<Node*>(bits & ~std::uintptr_t{7});
  }
  unsigned tag() const { return bits & 7; }
};

int main() {
  Node n{42};
  TaggedNode t(&n, 5);
  static_assert(sizeof(TaggedNode) == sizeof(Node*));
  assert(t.ptr()->v == 42 && t.tag() == 5);
}
```

**指针标记**（pointer tagging）利用的是对齐：`Node` 按 8 字节对齐，指向它的指针低 3 位总是 0，可以存一个小整数。红黑树把节点颜色存进父指针，无锁数据结构把版本号或删除标志存进指针，解释器把类型标记存进值指针，都是为了省下一个字段的内存。

这段代码在主流平台上能正确运行，但标准对它的保证很少。[[expr.reinterpret.cast]] 只保证指针转换成足够大的整数、再原样转回来，得到原来的指针。中间对整数做了位运算之后再转回来能得到什么，取决于实现怎样定义指针和整数之间的映射，所以这里的判定是 {{impl}}。此外：

- `reinterpret_cast` 不能出现在常量表达式里，这个类型无法在常量求值中使用；
- 有几位可用是程序员自己的假设，类型的对齐改小之后，代码会悄悄出错。

[ptrtag] 用一个标准类模板解决这些问题。它由 [[P3125R6]] 在 C++26 定稿之后加入工作草案，预计属于 C++29。截至写作时，本机 libc++ 还没有实现它，下面的 `pointer_tag_pair` 示例都没有经过编译验证。

## 基本用法

```cpp
#include <cassert>
#include <memory>

struct alignas(8) Node { int v; };
enum class Color : unsigned { red, black };

int main() {
  Node n{42};
  std::pointer_tag_pair<Node*, 1, Color> p(&n, Color::black);   // 只用 1 位
  static_assert(sizeof(p) == sizeof(Node*));
  auto [ptr, color] = p;                                         // 元组接口
  assert(ptr->v == 42 && color == Color::black);
}
```

三个模板参数依次是指针类型、请求的位数和标记类型：

```cpp
template<class Ptr, unsigned BitsRequested = bits-available<element-of<Ptr>>,
         class TagT = unsigned>
class pointer_tag_pair;
```

说明用的 `element-of<Ptr>` 是 `pointer_traits<Ptr>::element_type`，`bits-available<T>` 是 `pointer_bits_available(alignof(T))`（见 [[memory]] 概要）。所以默认请求全部可用的位：`pointer_tag_pair<Node*>` 对 8 字节对齐的 `Node` 请求 3 位。

## 可用位数 [ptrtag.bits]

```cpp
inline constexpr unsigned max_pointer_bits_available = /* 由实现定义 */;
constexpr unsigned pointer_bits_available(size_t alignment);
```

¶1 `max_pointer_bits_available` 是实现规定的、可用于标记的位数上限。

¶2 这个值不为 0，表示实现承诺标记可以往返：对编码后的指针做的那些非算术操作，虽然作用在无效指针值上、行为由实现定义（[[basic.compound]]），但会保留足够的信息，使 `from_tagged` 能恢复出原来的对象。

¶3–¶5 `pointer_bits_available(alignment)` 返回指向一个对齐为 `alignment` 的假想对象的指针中，未被使用的位数，具体值由实现定义。前置条件是 `alignment` 为 2 的幂；满足前置条件时，调用是常量表达式。

¶6–¶7 建议对齐大于 1 时结果不为 0。注 1 说明，在大多数平台上结果是 `countr_zero(alignment)` 和 `max_pointer_bits_available` 中较小的一个：8 字节对齐得到 3 位。

这里只用对齐带来的低位。x86-64 和 AArch64 的指针高位通常也没有使用，但能不能利用取决于平台和操作系统的配置，标准把这些都归入实现定义的范围。

## 类模板 `pointer_tag_pair` [ptrtag.pair.general]

### 布局保证（¶1–¶3）

¶1–¶2 `pointer_tag_pair<Ptr, BitsRequested, TagT>` 的对象表示一对值：一个 `Ptr` 类型的指针和一个 `TagT` 类型的标记。

¶3 每个特化 `PT` 都可平凡复制，满足 `copyable` 概念，并且 `sizeof(PT) == sizeof(Ptr)`、`alignof(PT) == alignof(Ptr)`。

大小相同是这个类型存在的理由，否则用 `struct { T* p; unsigned tag; }` 就够了。可平凡复制则意味着它可以 `memcpy`，可以放进 `std::atomic`（[[atomics.types.generic]] 要求可平凡复制）。无锁算法正需要这一点：一次比较并交换同时更新指针和版本号。

### 对模板参数的要求（¶4–¶5）

¶4 以下任何一条不满足，程序非良构：

- ¶4.1–¶4.2 `Ptr` 和 `TagT` 都不带 cv 限定，也不是引用；
- ¶4.3 `Ptr` 是对象指针类型，不能是函数指针，也不能是 `unique_ptr` 或花式指针；
- ¶4.4 `TagT` 是无符号整数类型，或者底层类型是无符号整数的枚举；
- ¶4.5 `sizeof(TagT) <= sizeof(void*)`；
- ¶4.6 `BitsRequested <= max_pointer_bits_available`。

¶5 说明用的 `tag-bit-width(v)` 等于 `bit_width(v)`，枚举先经过 `to_underlying`，也就是表示这个标记值最少需要的位数。各个操作的前置条件都写成 `tag-bit-width(t) <= bits_requested`：标记必须放得进请求的位数。

### 哪些 `U*` 可以放进来

构造函数接受 `U* p`，`U` 要满足说明用的概念 `tagging-compatible-pointee<U, PtrT, Bits, Alignment = alignof(U)>`：

- `U*` 能转换为 `PtrT`；
- `pointer_bits_available(Alignment) >= Bits`，按 `U` 的对齐检查位数，而不是按 `PtrT` 所指类型的对齐；
- `element-of<PtrT>` 是 `void`、标量类型、联合体，或者是 `U` 的指针可互转的基类（[[g:pointer-interconvertible]]）。

最后一条是为了排除指针调整。从 `Derived*` 转换到一个非首位的基类 `Base*` 时，地址会加上一个偏移，偏移后的地址不一定还满足 `Derived` 的对齐，标记要用的低位可能已经不是 0。指针可互转的基类，比如标准布局类的第一个基类，转换时地址不变。

## 构造 [ptrtag.pair.cons]

¶1 默认构造得到 `pointer() == nullptr`、`tag() == TagT()`。

¶2–¶5 `pointer_tag_pair(U* p, tag_type t)` 和 `pointer_tag_pair(nullptr_t, tag_type t)` 的前置条件有两条：¶3.1 `p` 不是尾后指针，¶3.2 标记放得进请求的位数。满足前置条件时，构造是常量表达式。构造不抛异常。

### 对齐比类型更严格的对象 [ptrtag.pair.overalign]

`int` 只要求 4 字节对齐，只有 2 位可用。如果程序知道自己的 `int` 都来自一个 64 字节对齐的内存池，可以用 `from_overaligned<64>(p, t)` 多用几位。

¶2 它的前置条件多了一条：`p == nullptr || is_sufficiently_aligned<PromisedAlignment>(p)`（[[ptr.align]]）。约束中的 `tagging-compatible-pointee` 改用 `PromisedAlignment` 计算可用位数。

## 与外部代码交换编码后的指针 [ptrtag.pair.tagops]

```cpp
using tagged_pointer_type = cv void*;   // cv 与 Ptr 所指类型相同
tagged_pointer_type tagged_pointer() const noexcept;
static pointer_tag_pair from_tagged(tagged_pointer_type p) noexcept;
```

这两个函数用于把已经编码好的原始指针交给外部，比如存进一个只接受 `void*` 的 C 接口，之后再取回来。

¶2 `tagged_pointer()` 返回一个未指定的值 `tp`。标准保证：只要位数和对齐的条件满足，`from_tagged(tp)` 能恢复出原来的指针和标记。注 1 说明这是一个**无效指针值**（[[g:invalid-pointer-value]]，[[basic.compound]]），对它的操作行为由实现定义。所以 `tagged_pointer()` 的结果不能解引用，只能原样交还给 `from_tagged`。

¶3 如果 `p` 确实来自某个兼容对象的 `tagged_pointer()`，`from_tagged(p)` 恢复出等价的一对值；否则结果的 `pointer()` 和 `tag()` 是未指定的值，这本身不是未定义行为。

这两个函数都不是 `constexpr`，因为常量求值中无法把标记真正编码进地址的位里。由此也能看出实现的思路：常量求值中，编译器可以在内部把指针和标记分开记录；只有 `tagged_pointer()` 需要真正的位编码。

## 访问、比较和元组接口

[ptrtag.pair.accessors] `pointer()` 和 `tag()` 返回所表示的指针和标记，都是 `constexpr` 和 `noexcept`。[ptrtag.pair.swap] `swap` 交换两个对象的值。

[ptrtag.pair.comp] `<=>` 和 `==` 等价于把 `pair(pointer(), tag())` 按字典序比较，要求 `tag_type` 支持相应的比较。建议的做法是：标记的比较是内建运算时，直接比较内部的位表示，一条整数比较指令就够了。注 1 提醒，比较不相关的指针，结果是未指定的，和普通指针一样（[[expr.rel]]）。

[ptrtag.pair.get] `tuple_size` 为 2，`get<0>` 返回指针，`get<1>` 返回标记，所以支持结构化绑定，如前面的例子所示。

!!! lawyer "第二条推导指引"
    ```cpp
    template<class Ptr, class TagT>
      pointer_tag_pair(Ptr*, TagT)
        -> pointer_tag_pair<Ptr*, bits-available<element-of<Ptr>>, TagT>;
    ```
    这里 `Ptr` 推导为被指类型，比如 `Node`。`element-of<Node>` 是 `pointer_traits<Node>::element_type`，而 `Node` 既没有 `element_type` 成员，也不是模板特化，按 [[pointer.traits.types#2]] 这个特化没有任何成员。照字面读，这条指引对普通类类型会替换失败；本意显然是 `bits-available<Ptr>`。这是新条文的措辞问题，阅读时按本意理解即可。

<details class="fine" markdown="1"><summary>其余条文</summary>

[ptrtag.bits] ¶2 和 [ptrtag.pair.tagops] ¶3 的措辞里出现了 `tagged_pointer_pair`、`tp.tagged()`、`pointer_tag_type` 这样的名字，与类名 `pointer_tag_pair` 和成员名 `tagged_pointer()` 不一致，属于编辑性的残留，含义不受影响。

</details>

## 思考题

!!! question "思考题 1"
    为什么 `pointer_tag_pair` 的 `Ptr` 只能是普通指针，不能是 `unique_ptr` 或花式指针？

<details markdown="1">
<summary>答案</summary>

一是布局保证。`sizeof(PT) == sizeof(Ptr)` 和可平凡复制只对普通指针有意义，`unique_ptr` 不可复制，花式指针可能占不止一个字。二是标记位来自地址对齐留下的 0 位，实现必须知道 `Ptr` 的值就是地址；花式指针（比如偏移指针）的位模式和地址没有固定关系。所以 ¶4.3 要求 `is_pointer_v<Ptr>`。
</details>

!!! question "思考题 2"
    `from_tagged` 收到一个随意构造的 `void*`，是未定义行为吗？

<details markdown="1">
<summary>答案</summary>

不是。¶3.2 规定此时 `pointer()` 和 `tag()` 的值是未指定的。但如果接着解引用这个未指定的指针，就是普通的无效指针解引用，属于未定义行为。`from_tagged` 本身总能调用，危险在于怎样使用它的结果。
</details>
