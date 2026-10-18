---
title: 成员关系
summary: 两个 constexpr 函数——is_pointer_interconvertible_with_class(m) 判断类对象与其成员子对象是否指针可互换（"首成员"），is_corresponding_member(m1, m2) 判断两个成员指针是否指向公共初始序列中的对应成员；以及 &C::b 的类型不一定是 C 的成员指针带来的陷阱
status: draft
covers: meta.member
papers: P0466R5
related: meta.rel, basic.compound, class.mem, class.prop, expr.unary.op, temp.deduct.call, meta.reflection.queries
tags: 标准库, type_traits, 标准布局, 指针可互换, 成员指针
updated: 2026-10-18
---

[meta.member] 只有两个函数，来自 [[P0466R5]]（与 [[meta.rel]] 中的 `is_layout_compatible`、`is_pointer_interconvertible_base_of` 同一提案）。它们把核心语言中两个关于**标准布局类**的保证暴露给程序：

- [[basic.compound]] 的**指针可互换**（[[g:pointer-interconvertible]]）：标准布局类对象与它的第一个非静态数据成员（或第一个基类子对象）地址相同，可以用 `reinterpret_cast` 互相转换；
- [[class.mem]] 的**公共初始序列**（[[g:common-initial-sequence]]）：两个标准布局 struct 开头那段"类型对应、布局兼容"的成员序列。

为什么这两个是**函数**而不是 trait？因为它们要问的是"**某个成员**"的性质，而成员是由**成员指针的值**指定的，值不能作为类型 trait 的类型实参。它们是 `constexpr` 而非 `consteval`：可以在常量表达式中用，也可以在运行时对一个运行期的成员指针值求值。

```cpp
template<class S, class M>
  constexpr bool is_pointer_interconvertible_with_class(M S::*m) noexcept;
template<class S1, class S2, class M1, class M2>
  constexpr bool is_corresponding_member(M1 S1::*m1, M2 S2::*m2) noexcept;
```

## `is_pointer_interconvertible_with_class`（¶1–¶2）

¶1 *Mandates*：`S` 是完整类型。

¶2 *Returns*：当且仅当以下全部成立时为 `true`：

1. `S` 是标准布局类型；
2. `M` 是对象类型（即 `m` 是**数据**成员指针，不是成员函数指针）；
3. `m` 不是空成员指针值；
4. 每个 `S` 类型的对象 `s` 都与其子对象 `s.*m` 指针可互换。

按 [[basic.compound]]，对标准布局类，第 4 条成立当且仅当 `s.*m` 是 `s` 的第一个非静态数据成员（对联合体，是任一非静态数据成员）。所以这个函数实际上回答的是"**`m` 是不是 `S` 的首成员**"——这是 `offsetof(S, m) == 0` 的类型安全、语义精确的版本（`offsetof == 0` 对非标准布局类可能也成立，但那时不能 `reinterpret_cast`）。

典型用途是侵入式数据结构里的 `container_of`：已知指向成员的指针，求外层对象的指针。只有当成员与外层对象指针可互换时，`reinterpret_cast<S*>(&member)` 才得到一个指向 `S` 对象的合法指针。

## `is_corresponding_member`（¶3–¶4）

¶3 *Mandates*：`S1`、`S2` 都是完整类型。

¶4 *Returns*：当且仅当 `S1`、`S2` 都是标准布局 struct 类型（[[class.prop]]），`M1`、`M2` 都是对象类型，`m1`、`m2` 都非空，且 `m1`、`m2` 指向 `S1` 与 `S2` 的公共初始序列中**对应的**成员时，为 `true`。

公共初始序列的意义在于联合体的"类型双关"豁免：若联合体当前活跃成员是 `S1`，可以通过 `S2` 的对应成员读取公共初始序列中的值（[[class.mem]]）。`is_corresponding_member` 让你在编译期断言"这两个成员确实处在可以这样读取的位置"。

```cpp godbolt title="corresponding.cpp"
#include <type_traits>

struct Header { int tag; long len; };
struct Packet { int kind; long size; char payload[16]; };

static_assert(std::is_pointer_interconvertible_with_class(&Packet::kind));   // 首成员
static_assert(!std::is_pointer_interconvertible_with_class(&Packet::size));
static_assert(std::is_corresponding_member(&Header::len, &Packet::size));    // 公共初始序列：int, long
static_assert(!std::is_corresponding_member(&Header::tag, &Packet::size));

int main() {}
```

!!! impl "本地无法验证"
    截至本文编写，本地 Clang 23 + libc++ **都没有实现**这两个函数（libc++ 中没有声明，Clang 也没有对应的内建），上面的例子未在本地编译运行。可以点击 godbolt 按钮，在 Compiler Explorer 上换用已实现它们的标准库对照。

## 陷阱：`&C::b` 的类型（¶5，注 1）

这一段是本节最有"法律味"的部分。

!!! std
    The type of a pointer-to-member expression `&C::b` is not always a pointer to member of `C`, leading to potentially surprising results when using these functions in conjunction with inheritance.

    成员指针表达式 `&C::b` 的类型**不一定**是"`C` 的成员指针"，这在与继承一起使用这些函数时可能导致出人意料的结果。

根源在 [[expr.unary.op]]：若 `b` 是类 `B` 的成员，`&C::b` 的类型是"**`B` 的**成员指针"，即 `int B::*`——即使你是通过派生类 `C` 去命名它。于是模板实参推导（[[temp.deduct.call]]）会把 `S` 推导为 `B` 而不是 `C`：

```cpp godbolt title="member-of-base.cpp"
#include <type_traits>

struct A { int a; };                      // 标准布局
struct B { int b; };                      // 标准布局
struct C : public A, public B { };        // 不是标准布局：两个基类都有数据成员

static_assert( std::is_pointer_interconvertible_with_class(&C::b));
// 成功！&C::b 的类型是 int B::*，S 被推导为 B，而 b 是 B 的首成员

static_assert(!std::is_pointer_interconvertible_with_class<C, int>(&C::b));
// 显式指定 S = C：int B::* 隐式转换为 int C::*，C 不是标准布局 → false

static_assert( std::is_corresponding_member(&C::a, &C::b));
// 成功！实际比较的是 A::a 与 B::b：两个 { int } 的公共初始序列的首成员

static_assert(!std::is_corresponding_member<C, C, int, int>(&C::a, &C::b));
// 强制使用 C：C 不是标准布局 struct → false

int main() {}
```

这个例子是标准注释里的原例（注释为非规范性内容，但它演示的推导结果完全由规范性条款决定）。教训是：**在涉及继承时，显式写出类模板实参**，否则你问的可能根本不是你以为的那个类。

## 与反射的对照

C++26 反射提供了更通用的工具（[[meta.reflection.queries]]）：`std::meta::offset_of(^^S::m)` 直接给出成员的字节/位偏移，`nonstatic_data_members_of(^^S, ctx)[0]` 给出首成员，配合 `is_standard_layout_type(^^S)` 就能表达 `is_pointer_interconvertible_with_class` 的全部语义。但 [meta.member] 的两个函数不需要反射、可以在运行期使用，仍有其位置。

## 思考题

!!! question "思考题"
    `union U { int i; float f; };` 中 `std::is_pointer_interconvertible_with_class(&U::f)` 的值是什么？`std::is_corresponding_member(&U::i, &U::f)` 呢？

<details markdown="1">
<summary>展开查看答案与解析</summary>

前者为 `true`：`U` 是标准布局类型（联合体也是类），按 [[basic.compound]]，联合体对象与它的**每一个**非静态数据成员都指针可互换，不只是第一个。

后者为 `false`：¶4 要求 `S1`、`S2` 是标准布局 **struct**（[[class.prop]] 中 struct 指用 `class` 或 `struct` 声明的类），联合体不满足。
</details>

## 小结

| 函数 | 本质 | 要求 |
|---|---|---|
| `is_pointer_interconvertible_with_class(m)` | `m` 是否为 `S` 的"首成员"（联合体：任一成员）| 标准布局；数据成员；非空 |
| `is_corresponding_member(m1, m2)` | `m1`、`m2` 是否为公共初始序列中的对应成员 | 两者都是标准布局 struct；数据成员；非空 |
| 陷阱 | `&C::b` 的类型可能是 `int B::*`，模板推导出基类 | 涉及继承时显式写模板实参 |
