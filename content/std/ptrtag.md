---
title: 指针标记 pointer_tag_pair
summary: C++26 之后进入草案的 pointer_tag_pair：把小整数标记存进对齐指针的空闲低位，大小与原指针相同、可平凡复制、可在常量求值中使用；tagged_pointer/from_tagged 产出的"无效指针值"及其由实现定义的往返保证
status: done
covers: *
since: c++29
related: ptr.align, basic.compound, basic.align, expr.reinterpret.cast, pointer.traits, memory, tuple.helper
tags: 标准库, 指针标记, 对齐, constexpr
papers: P3125R6
updated: 2026-10-18
---

**指针标记**（pointer tagging）是一种古老的底层技巧：如果指针总是指向 8 字节对齐的对象，它的低 3 位必然是 0，可以拿来存 0–7 的小整数。红黑树把颜色塞进父指针，无锁数据结构把版本号或"已删除"标志塞进指针，解释器把类型标记塞进值指针——全都靠这一招省内存、省一次缓存未命中。

问题在于它的合法性。手写版本通常是这样：

```cpp title="hand-rolled-tag.cpp" impl
#include <cstdint>
#include <cassert>

struct alignas(8) Node { int v; };

// 手写的标记指针：低 3 位存标记。指针 <-> 整数的往返映射由实现定义（[expr.reinterpret.cast]）
struct TaggedNode {
    std::uintptr_t bits;
    TaggedNode(Node* p, unsigned tag) : bits(reinterpret_cast<std::uintptr_t>(p) | tag) {
        assert(tag < 8);
    }
    Node* ptr() const { return reinterpret_cast<Node*>(bits & ~std::uintptr_t{7}); }
    unsigned tag() const { return bits & 7; }
};

int main() {
    Node n{42};
    TaggedNode t(&n, 5);
    static_assert(sizeof(TaggedNode) == sizeof(Node*));
    assert(t.ptr()->v == 42 && t.tag() == 5);
}
```

标准只保证"指针 → 足够大的整数 → 同类型指针"的**原样**往返得到原值（[[expr.reinterpret.cast]]）；整数在中间被做了位运算之后再转回来能否得到原指针，完全取决于实现对指针到整数映射的定义。主流平台上它"能用"，但：

- 它不能在常量求值中使用（`reinterpret_cast` 不是常量表达式）；
- 它对编译器的指针来源（provenance）分析不透明，在 CHERI 这类硬件能力指针平台上直接不成立；
- "低几位可用"是程序员的假设，类型的对齐可能被改小。

[ptrtag] 用一个标准类模板把这件事做成**可移植、constexpr、有明确契约**的操作。它由 [[P3125R6]]（"constexpr pointer tagging"）在 C++26 定稿之后加入工作草案，预计属于 C++29。截至写作时，本机 libc++ 尚未实现，本页的 `pointer_tag_pair` 示例均未在本地编译验证。

## 可用位数（[ptrtag.bits]）

```cpp
inline constexpr unsigned max_pointer_bits_available = /* see below */;
constexpr unsigned pointer_bits_available(size_t alignment);
```

- ¶1：`max_pointer_bits_available` 是由实现定义的可用于标记的位数上限。
- ¶2：其值非零表示：对指针做的若干**非算术**操作（作用于无效指针值、行为由实现定义的那些，[[basic.compound]]）能保留足够信息，使得 `from_tagged(tp.tagged())` 能恢复出原来的 `tp`。也就是说，这个常量是实现对"标记往返可行"的承诺。（草案此处写作 `tagged_pointer_pair` 与 `tagged()`，与类名 `pointer_tag_pair`、成员名 `tagged_pointer()` 不一致，是编辑性残留。）
- ¶3–¶5：`pointer_bits_available(alignment)` 返回指向对齐为 `alignment` 的假想对象的指针中，未被使用的位数（由实现定义）；前置条件是 `alignment` 为 2 的幂，满足时是常量表达式（*Constant When*）。
- ¶6 推荐实践：对齐大于 1 时结果应非零。
- ¶7 注：在大多数平台上，结果是 `countr_zero(alignment)` 与 `max_pointer_bits_available` 中的较小者。8 字节对齐 → 3 位。

注意这里只讨论**低位**（对齐带来的零位）。x86-64 和 AArch64 上指针高位通常也不用（虚拟地址只有 48 或 57 位，AArch64 还有 TBI 特性），但能否利用高位因平台和操作系统配置而异，标准把它整体纳入"由实现定义"。

## 类模板 `pointer_tag_pair`（[ptrtag.pair.general]）

```cpp
template<class Ptr, unsigned BitsRequested = bits-available<element-of<Ptr>>, class TagT = unsigned>
class pointer_tag_pair;
```

其中说明用的 `element-of<U>` 是 `pointer_traits<U>::element_type`，`bits-available<T>` 是 `pointer_bits_available(alignof(T))`（见 [[memory]] 概要）。所以默认情况下"能用几位就要几位"：`pointer_tag_pair<Node*>` 对 8 字节对齐的 `Node` 默认请求 3 位。

### ¶2–¶3：表示与布局保证

¶2：对象表示一个 `Ptr` 类型的指针值和一个 `TagT` 类型的标记值组成的对。¶3：每个特化都是**可平凡复制**的、模拟 `copyable`，并且

- `sizeof(PT) == sizeof(Ptr)`，
- `alignof(PT) == alignof(Ptr)`。

这是这个类型存在的全部理由：它必须**和裸指针一样大**，否则用 `struct { T* p; unsigned tag; }` 就够了。可平凡复制意味着它可以被 `memcpy`、放进 `std::atomic`（[[atomics.types.generic]] 要求可平凡复制），这对无锁算法至关重要——一次 CAS 同时更新指针和版本号。

### ¶4：*Mandates*

1. `Ptr`、`TagT` 都不带 cv/引用；
2. `Ptr` 是对象指针类型（不是函数指针）——只接受**裸指针**，不接受花式指针；
3. `TagT` 是无符号整数类型，或底层类型为无符号整数的枚举；
4. `sizeof(TagT) <= sizeof(void*)`；
5. `BitsRequested <= max_pointer_bits_available`。

### ¶5：`tag-bit-width`

`tag-bit-width(v)` 就是 `bit_width(v)`（枚举先 `to_underlying`），即表示标记值所需的最少位数。各操作的前置条件都写作 `tag-bit-width(t) <= bits_requested`：标记必须放得进请求的位数。

### `tagging-compatible-pointee`：哪些 `U*` 可以放进来

构造函数接受 `U* p`，`U` 需满足说明用概念 `tagging-compatible-pointee<U, PtrT, Bits, Alignment = alignof(U)>`：

- `U*` 可转换为 `PtrT`；
- `pointer_bits_available(Alignment) >= Bits`——**按 `U` 的对齐**（而不是 `Ptr` 所指类型的对齐）检查位数够不够；
- 并且 `element-of<PtrT>` 是 `void`、标量类型、联合体，或者是 `U` 的**指针可互转**的基类（[[g:pointer-interconvertible]]）。

最后一条防止的是**指针调整**：从 `Derived*` 转换到非首基类 `Base*` 时地址会偏移，偏移后的地址未必保持 `Derived` 的对齐，标记位可能已被"占用"。只有指针可互转的基类（标准布局类的首个基类等）转换时地址不变。

### 推导指引

```cpp
pointer_tag_pair(Ptr*) -> pointer_tag_pair<Ptr*>;
pointer_tag_pair(Ptr*, TagT) -> pointer_tag_pair<Ptr*, bits-available<element-of<Ptr>>, TagT>;
```

!!! lawyer "推导指引里的 `element-of<Ptr>`"
    第二条指引中 `Ptr` 推导为**被指类型**（例如 `Node`），而 `element-of<Node>` 是 `pointer_traits<Node>::element_type`——对非指针类型它不存在（[[pointer.traits]] ¶2）。按字面读，这条指引对普通类类型会替换失败；意图显然是 `bits-available<Ptr>`（或 `element-of<Ptr*>`）。这是新加入条款中常见的措辞瑕疵，读者遇到时应按意图理解，并留意后续的 LWG issue。

## 构造（[ptrtag.pair.cons]）与过对齐（[ptrtag.pair.overalign]）

- 默认构造：`pointer() == nullptr`，`tag() == TagT()`。
- `pointer_tag_pair(U* p, tag_type t)` 与 `(nullptr_t, tag_type)`：*Preconditions* 为 (3.1) `p` 不是尾后指针、(3.2) 标记放得下。满足前置条件时是常量表达式。不抛异常。

**为什么排除尾后指针？** 条文没有给出理由。一个合理的解读是：`pointer_tag_pair` 的设计允许实现在常量求值中把标记与所指**对象**关联记录，而尾后指针不指向任何对象；把它排除在外，也就不必为它定义标记的往返语义。

`from_overaligned<PromisedAlignment>(p, t)` 处理"类型的对齐小，但这个具体对象被放在更大边界上"的情形：例如 `int` 只有 4 字节对齐（2 位可用），但你知道你的 `int` 都来自 64 字节对齐的池。前置条件额外要求 `p == nullptr || is_sufficiently_aligned<PromisedAlignment>(p)`（[[ptr.align]]），而 `tagging-compatible-pointee` 改用 `PromisedAlignment` 计算可用位数。

## 带标记指针的互操作（[ptrtag.pair.tagops]）

```cpp
using tagged_pointer_type = cv void*;      // 与 Ptr 同样的 cv 限定
tagged_pointer_type tagged_pointer() const noexcept;
static pointer_tag_pair from_tagged(tagged_pointer_type p) noexcept;
```

这对函数用于和**外部**代码交换"已经打好标记的原始指针"，例如存入一个只接受 `void*` 的 C API，或者与其他语言的运行时交互。

- ¶2：`tagged_pointer()` 返回一个**未指明的值** `tp`，承诺用同样的位数、在满足对齐的前提下，`DP::from_tagged(tp)` 能恢复出原指针和原标记。注 1 明说：此函数返回一个**无效指针值**（[[g:invalid-pointer-value]]，[[basic.compound]]），对它的操作行为由实现定义。所以 `tagged_pointer()` 的结果**绝不能解引用**，只能原样传回 `from_tagged`。
- ¶3：`from_tagged(p)` 若 `p` 确实来自某个兼容的 `tagged_pointer()`，就恢复出等价的对；否则 `pointer()` 和 `tag()` 的值**未指明**（不是 UB）。

两个函数都**不是** `constexpr`：常量求值中无法把标记"真的"编码进地址位。这也透露了实现策略——常量求值中，`pointer_tag_pair` 可以在编译器内部把指针与标记分开记录（对象大小不变的保证只约束运行期布局），只有 `tagged_pointer()` 需要真正的位编码。

## 访问、交换、比较、元组接口

- `pointer()`、`tag()`（[ptrtag.pair.accessors]）：返回所表示的值，`constexpr`、`noexcept`。
- `swap`（[ptrtag.pair.swap]）：交换值。
- 比较（[ptrtag.pair.comp]）：`<=>` 与 `==` 等价于把 `pair(pointer(), tag())` 按字典序比较；要求 `tag_type` 可三路比较 / 可相等比较。推荐实践：当标记比较是内建运算时，直接比较内部位表示（一条整数比较指令）。注：比较不相关指针的结果未指明——与裸指针的 `<=>` 一样（[[expr.rel]]）。
- 元组接口（[ptrtag.pair.get]）：`tuple_size` 为 2，`get<0>` 返回指针、`get<1>` 返回标记，因此支持结构化绑定：

```cpp title="ptrtag-usage.cpp" ok
#include <memory>
#include <cassert>

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

（未在本地编译验证：本机 libc++ 尚无 `pointer_tag_pair`。）

## 思考题

<details markdown="1">
<summary>1. 为什么 `pointer_tag_pair` 的 `Ptr` 只能是裸指针，不能是 `unique_ptr` 或花式指针？</summary>

两个原因。其一，布局保证 `sizeof(PT) == sizeof(Ptr)` 与"可平凡复制"只有对裸指针才有意义——`unique_ptr` 不可复制，花式指针可能本身就占多个字。其二，标记位来自**地址**的对齐零位，需要实现知道 `Ptr` 的值就是地址；花式指针（如偏移指针）的位模式与地址没有固定关系。¶4.3 的 *Mandates* 因此要求 `is_pointer_v<Ptr>`。
</details>

<details markdown="1">
<summary>2. `from_tagged` 收到一个随意构造的 `void*` 时会发生什么？是 UB 吗？</summary>

不是 UB。¶3.2 规定此时 `dp.pointer()` 与 `dp.tag()` 的值**未指明**。但随后若解引用这个未指明的指针，就是普通的无效指针解引用 UB。换言之，`from_tagged` 本身是"总能调用"的，危险在于使用结果。
</details>

## 小结

- `pointer_tag_pair<Ptr, Bits, TagT>`：与裸指针同大小、同对齐、可平凡复制；默认按被指类型的对齐使用全部可用低位。
- 可用位数由 `pointer_bits_available(alignment)` 给出（通常是 `countr_zero(alignment)`，受 `max_pointer_bits_available` 限制）。
- 构造与访问都是 `constexpr`；`tagged_pointer()`/`from_tagged()` 用于与外部交换编码后的指针，返回的是无效指针值，不能解引用，也不是 `constexpr`。
- 只接受与目标类型指针可互转的派生类指针，避免指针调整破坏对齐假设；`from_overaligned` 用于"对象比类型更对齐"的情形。
- 属于 C++26 之后的草案内容（[[P3125R6]]）。
