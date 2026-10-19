---
title: 成员关系
summary: 两个 constexpr 函数：判断数据成员是否与所在类的对象指针可互换，判断两个数据成员是否处在公共初始序列的对应位置。
status: draft
covers: meta.member
papers: P0466R5
related: meta.rel, basic.compound, class.mem, class.prop, expr.unary.op, temp.deduct.call, meta.reflection.queries
tags: 标准库, type_traits, 标准布局, 指针可互换, 成员指针
updated: 2026-10-19
---

!!! tldr
    - `is_pointer_interconvertible_with_class(&S::m)` 判断 `m` 是否是标准布局类 `S` 的首个数据成员，即能否在 `S*` 和成员的指针之间用 `reinterpret_cast` 互相转换。
    - `is_corresponding_member(&S1::m1, &S2::m2)` 判断两个成员是否处在两个标准布局 struct 公共初始序列的对应位置。
    - 它们以成员指针的值为实参，所以是函数，不是类型特征。
    - `&C::b` 的类型可能是基类的成员指针 `int B::*`，模板实参推导会推出基类。涉及继承时要显式写出类的模板实参。

这两个函数来自 [[P0466R5]]，与 [[meta.rel]] 中的 `is_layout_compatible`、`is_pointer_interconvertible_base_of` 同属一个提案。它们查询的是核心语言给标准布局类的两个保证：

- [[g:pointer-interconvertible|指针可互换]]（[[basic.compound]]）：两个对象地址相同，可以用 `reinterpret_cast` 从一个对象的指针得到另一个对象的指针。标准布局类的对象与它的第一个非静态数据成员指针可互换；联合体对象与它的每个非静态数据成员都指针可互换。
- [[g:common-initial-sequence|公共初始序列]]（[[class.mem]]）：两个标准布局 struct 从头开始、类型布局兼容的那一段成员。

```cpp
template<class S, class M>
  constexpr bool is_pointer_interconvertible_with_class(M S::*m) noexcept;
template<class S1, class S2, class M1, class M2>
  constexpr bool is_corresponding_member(M1 S1::*m1, M2 S2::*m2) noexcept;
```

它们问的是某一个成员的性质，成员要用成员指针的值来指定，而值不能作为类型特征的类型实参，所以做成了函数。它们是 `constexpr` 而不是 `consteval`，既能用在常量表达式中，也能在运行时对一个成员指针变量求值。

## 示例

```cpp run title="corresponding.cpp"
#include <type_traits>
using std::is_corresponding_member;
using std::is_pointer_interconvertible_with_class;

struct Header { int tag; long len; };
struct Packet { int kind; long size; char payload[16]; };

static_assert( is_pointer_interconvertible_with_class(&Packet::kind));
static_assert(!is_pointer_interconvertible_with_class(&Packet::size));
static_assert( is_corresponding_member(&Header::len, &Packet::size));
static_assert(!is_corresponding_member(&Header::tag, &Packet::size));

int main() {}
```

`kind` 是 `Packet` 的首个成员，`size` 不是。`Header` 与 `Packet` 的公共初始序列是 `int, long` 两个成员，`len` 与 `size` 都在第二个位置，所以是对应成员；`tag` 与 `size` 位置不同。

!!! impl "本机无法验证"
    本机 Clang 23 加 libc++ 都没有实现这两个函数：libc++ 中没有声明，Clang 也没有对应的内建。本页的例子没有在本机编译，所以没有标判定。GCC 的 libstdc++ 已经实现了它们，可以点 godbolt 按钮对照。

## `is_pointer_interconvertible_with_class`

¶1：`S` 必须是完整类型（*Mandates*）。

¶2：当且仅当以下条件全部成立时返回 `true`：

1. `S` 是标准布局类型；
2. `M` 是对象类型，也就是说 `m` 指向数据成员，而不是成员函数；
3. `m` 不是空成员指针；
4. 每个 `S` 类型的对象 `s` 都与它的子对象 `s.*m` 指针可互换。

对标准布局的 struct，第 4 条等价于 `m` 是首个非静态数据成员；对联合体，任何非静态数据成员都满足。所以这个函数可以看作 `offsetof(S, m) == 0` 的精确版本：一个非标准布局类的成员偏移也可能是 0，但那时不能用 `reinterpret_cast` 在两者之间转换。

典型的用途是侵入式数据结构中的 `container_of`：已知一个指向成员的指针，求外层对象的指针。只有成员与外层对象指针可互换时，`reinterpret_cast<S*>(&member)` 才得到一个指向那个 `S` 对象的指针。

## `is_corresponding_member`

¶3：`S1` 和 `S2` 必须是完整类型（*Mandates*）。

¶4：当且仅当 `S1`、`S2` 都是标准布局 struct（[[class.prop]]），`M1`、`M2` 都是对象类型，`m1`、`m2` 都不为空，而且两者指向 `S1` 与 `S2` 公共初始序列中的对应成员时，返回 `true`。

公共初始序列的用处在联合体上。如果联合体中当前活跃的成员是 `S1` 类型的对象，标准允许通过 `S2` 类型的成员读取公共初始序列中的值（[[class.mem]]）。用 `is_corresponding_member` 可以在编译期断言两个成员确实处在可以这样读取的位置。

## 继承带来的陷阱

¶5 的注 1 指出，成员指针表达式 `&C::b` 的类型不一定是 `C` 的成员指针。按 [[expr.unary.op]]，如果 `b` 是在基类 `B` 中声明的，即使通过派生类 `C` 来命名，`&C::b` 的类型也是 `int B::*`。于是模板实参推导（[[temp.deduct.call]]）把 `S` 推导为 `B`，而不是 `C`。

下面是标准的例 1：

```cpp run title="member-of-base.cpp"
#include <type_traits>
using std::is_corresponding_member;
using std::is_pointer_interconvertible_with_class;

struct A { int a; };               // 标准布局
struct B { int b; };               // 标准布局
struct C : public A, public B {};  // 不是标准布局

// &C::b 的类型是 int B::*，S 推导为 B，b 是 B 的首成员
static_assert( is_pointer_interconvertible_with_class(&C::b));
// 显式指定 S = C：C 不是标准布局
static_assert(!is_pointer_interconvertible_with_class<C, int>(&C::b));

// 实际比较的是 A::a 与 B::b
static_assert( is_corresponding_member(&C::a, &C::b));
static_assert(!is_corresponding_member<C, C, int, int>(&C::a, &C::b));

int main() {}
```

`C` 的两个基类都有数据成员，所以 `C` 不是标准布局类。不写模板实参时，第一个断言实际问的是 `B` 的首成员，第三个断言比较的是两个各自只有一个 `int` 成员的类 `A`、`B`，结果都为真。显式指定 `C` 后，`int B::*` 隐式转换为 `int C::*`，问题才真正针对 `C`，结果为假。

涉及继承时，要显式写出类的模板实参，否则问的可能不是你以为的那个类。

## 与反射的关系

C++26 的静态反射（[[meta.reflection.queries]]）提供了更通用的工具，例如 `std::meta::offset_of` 给出成员的偏移，`nonstatic_data_members_of` 列出全部数据成员，再配合判断标准布局的查询，就能表达本页两个函数的含义。不过这两个函数不需要反射，也能在运行时使用。

## 思考题

!!! question "思考题"
    设 `union U { int i; float f; };`。`std::is_pointer_interconvertible_with_class(&U::f)` 的值是什么？`std::is_corresponding_member(&U::i, &U::f)` 呢？

<details markdown="1">
<summary>答案</summary>

前者为 `true`。联合体也是类，`U` 是标准布局类型；按 [[basic.compound]]，联合体对象与它的每一个非静态数据成员都指针可互换，不只是第一个。

后者为 `false`。第 4 段要求 `S1`、`S2` 是标准布局 struct，即用 `struct` 或 `class` 声明的标准布局类（[[class.prop]]），联合体不满足。
</details>
