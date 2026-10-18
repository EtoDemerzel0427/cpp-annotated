---
title: 一元类型特征
summary: 一元 trait 总则；15 个主类型类别谓词（任一类型恰好属于其中一个，cv 不影响结果）与 7 个复合类别谓词——它们是 [basic.types] 分类体系的库版；以及 alignment_of、rank、extent 三个类型属性查询
status: draft
covers: meta.unary.general, meta.unary.cat, meta.unary.comp, meta.unary.prop.query
related: type.traits, meta.unary.prop, basic.types, basic.fundamental, basic.compound, dcl.array, dcl.fct, expr.alignof
tags: 标准库, type_traits, 类型分类
updated: 2026-10-18
---

[meta.unary] 收录"问一个类型的问题"的 trait。它分成三块：**主类型类别**（[meta.unary.cat]）、**复合类型类别**（[meta.unary.comp]）、**类型性质**（[meta.unary.prop]，内容很多，单独成页见 [[meta.unary.prop]]）。紧随其后的 [meta.unary.prop.query] 虽然是同级条款，但同样是对单个类型的查询，也放在本页。

## 总则（[meta.unary.general]）

¶1：本子条款的模板用于在编译期查询类型的性质。¶2：它们每一个都是 *Cpp17UnaryTypeTrait*（[[type.traits]]），条件为真时基特征是 `true_type`，否则是 `false_type`。

## 主类型类别（[meta.unary.cat]）

¶1：表 52 中的主类型类别与 [[basic.types]] 中的描述一一对应。¶3 的注释点出了它们的设计目标：

!!! std
    For any given type `T`, exactly one of the primary type categories has a `value` member that evaluates to `true`.

    对任意给定类型 `T`，主类型类别中**恰好有一个**的 `value` 为 `true`。

也就是说，这 15 个谓词把 C++ 的全部类型**划分**成了互不相交、并起来覆盖全集的 15 个格子：

| 分组 | 谓词 | 条件 | 备注 |
|---|---|---|---|
| 基本类型 | `is_void` | `void` | |
| | `is_null_pointer` | `std::nullptr_t` | C++14；**不是**指针 |
| | `is_integral` | 整型（[[basic.fundamental]]）| 含 `bool`、所有字符类型、扩展整数类型 |
| | `is_floating_point` | 浮点类型 | 含扩展浮点类型（C++23）|
| | `is_reflection` {{c++26}} | `std::meta::info` | |
| 复合类型 | `is_array` | 已知或未知边界的数组 | `std::array` **不是**数组类型 |
| | `is_pointer` | 指针类型 | 含函数指针，**不含**成员指针 |
| | `is_lvalue_reference` / `is_rvalue_reference` | 左值/右值引用 | |
| | `is_member_object_pointer` / `is_member_function_pointer` | 数据成员指针/成员函数指针 | |
| | `is_enum` | 枚举 | 有作用域与无作用域皆是 |
| | `is_union` | 联合体 | |
| | `is_class` | **非联合**类类型 | 闭包类型也是类 |
| | `is_function` | 函数类型 | 含带 cv/引用限定的"可憎函数类型"；**不含**函数引用、函数指针 |

¶2：对任意 `T`，把这些模板应用于 `T` 和 *cv* `T` 结果相同——`is_integral_v<const volatile int>` 为真。注意引用类型和函数类型本身不能被 cv 限定（cv 会被忽略），所以这条规则对它们是平凡成立的。

```cpp run title="primary-categories.cpp" ok
#include <array>
#include <cstddef>
#include <type_traits>

struct S { int m; void f(); };
union U { int a; };
using Abominable = void() const;

static_assert(!std::is_array_v<std::array<int, 3>>);                 // 类模板 array 不是数组类型
static_assert( std::is_array_v<int[]>);                              // 未知边界数组也是
static_assert(!std::is_pointer_v<int S::*>);                         // 成员指针不是指针
static_assert( std::is_pointer_v<void (*)()>);                       // 函数指针是指针
static_assert(!std::is_pointer_v<std::nullptr_t>);
static_assert( std::is_null_pointer_v<const std::nullptr_t>);        // cv 不影响结果
static_assert(!std::is_function_v<int (&)()>);                       // 函数引用是引用
static_assert( std::is_function_v<Abominable>);                      // 可憎函数类型也是函数类型
static_assert( std::is_member_function_pointer_v<void (S::*)() const&&>);
static_assert( std::is_integral_v<bool> && std::is_integral_v<char8_t>);
static_assert(!std::is_class_v<U> && std::is_union_v<U>);
static_assert( std::is_class_v<decltype([] {})>);                     // 闭包类型是类

int main() {}
```

### 一个历史上的技巧：`is_function`

在有编译器内建之前，`is_function` 是最难写的主类别——函数类型有无数种形状（形参列表、`noexcept`、cv、引用限定、C 变参）。经典实现利用了一个核心语言事实：**只有函数类型和引用类型在加 `const` 后保持不变**（[[dcl.fct]]、[[dcl.ref]] 中 cv 被忽略），于是：

```cpp
template<class T>
struct is_function : std::bool_constant<!std::is_const_v<const T> && !std::is_reference_v<T>> {};
```

如今 libc++ 直接用 `__is_function(_Tp)`。

!!! impl "扩展类型在实现中的归属"
    标准说整型包括**扩展整数类型**（[[g:extended-integer-type]]），浮点类型包括**扩展浮点类型**。本地 Clang 23 + libc++ 的实际表现：

    - `is_integral_v<__int128>` 与 `is_integral_v<unsigned _BitInt(7)>` 都是 `true`——libc++ 使用 `__is_integral` 内建，Clang 认为它们是整型；
    - `is_floating_point_v<_Float16>` 却是 `false`：libc++ 的 `is_floating_point` 是对 `float`/`double`/`long double` 的三个显式特化，没有用内建。libc++ 目前也不提供 `<stdfloat>`，所以 C++23 的 `std::float16_t` 等在这套工具链上不可用。

    `_Float16` 是 Clang 的扩展类型，标准并不强制实现把它当作"扩展浮点类型"，所以这不算违规；但它提醒我们：**主类别是否覆盖实现扩展类型，是实现的选择**。

## 复合类型类别（[meta.unary.comp]）

¶1：表 53 的模板是主类别的**便捷组合**，对应 [[basic.types]] 中的描述。¶2：同样，cv 不影响结果。与主类别不同，复合类别**会重叠**（`int*` 既是标量又是复合类型）。

| 谓词 | 定义 | 等价于 |
|---|---|---|
| `is_reference` | 左值或右值引用 | `is_lvalue_reference \|\| is_rvalue_reference` |
| `is_arithmetic` | 算术类型 | `is_integral \|\| is_floating_point` |
| `is_fundamental` | 基本类型 | 算术 + `void` + `nullptr_t` + `meta::info` |
| `is_object` | 对象类型（[[basic.types]]）| 非函数、非引用、非 `void` |
| `is_scalar` | 标量类型 | 算术 + 枚举 + 指针 + 成员指针 + `nullptr_t` + `meta::info` |
| `is_compound` | 复合类型（[[basic.compound]]）| `!is_fundamental` |
| `is_member_pointer` | 成员指针 | 数据成员指针或成员函数指针 |

几个容易记错的点：

- **枚举不是算术类型**：`is_arithmetic_v<E>` 为假，但 `is_scalar_v<E>` 为真；同理 `is_integral_v<E>` 也为假——尽管无作用域枚举可以整型提升。
- **`void` 是基本类型但不是对象类型**；`int[]`（未知边界数组）**是**对象类型（只是不完整）。
- **引用是复合类型**但不是对象类型。
- **`std::meta::info` 是标量类型**（[[basic.types.general#7]]）{{c++26}}：反射值就像一个整数或指针那样被复制、比较，这正是它能做常量模板实参的原因。

```cpp run title="composite-categories.cpp" ok
#include <cstddef>
#include <type_traits>

enum E { e };
struct S { int m; };

static_assert(!std::is_arithmetic_v<E> && !std::is_integral_v<E> && std::is_scalar_v<E>);
static_assert( std::is_fundamental_v<void> && !std::is_object_v<void>);
static_assert( std::is_object_v<int[]>);
static_assert(!std::is_object_v<int&> && std::is_compound_v<int&>);
static_assert( std::is_scalar_v<int S::*> && std::is_scalar_v<std::nullptr_t>);
static_assert(!std::is_scalar_v<int[1]>);

int main() {}
```

## 类型属性查询（[meta.unary.prop.query]）

¶1–¶2：表 55 中的三个模板也是 *Cpp17UnaryTypeTrait*，但基特征是 `integral_constant<size_t, Value>`——"返回值"是一个数而不是布尔。

| 模板 | 值 |
|---|---|
| `alignment_of<T>` | `alignof(T)`；*Mandates*：`alignof(T)` 是有效表达式（[[expr.alignof]]）|
| `rank<T>` | 若 `T` 是数组类型，为其维数；否则 0 |
| `extent<T, I = 0>` | 第 `I` 维（从 0 起）的边界；若 `T` 不是数组、维数 ≤ `I`，或 `I == 0` 且 `T` 是未知边界数组，则为 0 |

- `alignment_of` 是 C++11 引入 `alignof` 运算符之前的遗产，今天直接写 `alignof(T)` 即可。它的 *Mandates* 意味着 `alignment_of<void>`、`alignment_of<void()>` 非良构（必须诊断）；而 `alignment_of<int&>` 合法，值为 `alignof(int)`（`alignof` 作用于引用类型时取被引用类型的对齐，[[expr.alignof]]）；`alignment_of<int[]>` 也合法，值为元素对齐。
- `rank` 与 `extent` 只看**内建数组**：`rank_v<std::array<int, 3>>` 是 0。
- `extent` 用 0 同时表示"不是数组/越界"和"未知边界"，无法区分——需要时配合 `is_bounded_array` / `is_unbounded_array`（[[meta.unary.prop]]）。

```cpp run title="rank-extent.cpp" ok
#include <type_traits>

static_assert(std::rank_v<int> == 0);
static_assert(std::rank_v<int[][4]> == 2);
static_assert(std::extent_v<int[2][4]> == 2);
static_assert(std::extent_v<int[2][4], 1> == 4);
static_assert(std::extent_v<int[][4]> == 0);          // 未知边界的第 0 维
static_assert(std::extent_v<int[][4], 1> == 4);
static_assert(std::extent_v<int[3][4], 2> == 0);      // 维数不够
static_assert(std::alignment_of_v<int&> == alignof(int));
static_assert(std::alignment_of_v<int[]> == alignof(int));

int main() {}
```

C++26 反射库为它们提供了 `consteval` 对应物：`std::meta::rank(info)`、`std::meta::extent(info, unsigned)`，以及名字不同的 `std::meta::alignment_of(info)`（后者语义更宽，也接受数据成员、变量等，见 [[meta.reflection.queries]]）。

## 陷阱

!!! pitfall "`is_pointer` 不认智能指针、不认成员指针"
    `is_pointer_v<std::unique_ptr<int>>` 为假（那是类类型）；`is_pointer_v<int S::*>` 也为假（成员指针是单独的主类别）。泛型代码里想表达"可解引用的东西"，应使用概念（如 `std::indirectly_readable`）而不是 `is_pointer`。

!!! pitfall "`is_function` 与 `is_member_function_pointer` 的分界"
    `is_function_v<void() const>` 为真：这种带 cv 限定的函数类型只能作为成员函数指针的"被指向类型"出现，不能声明普通函数，但它确实是函数类型（[[dcl.fct]]）。反过来，`void (S::*)() const` 才是成员函数指针类型。

## 思考题

!!! question "思考题"
    对哪些类型 `T`，`std::is_fundamental_v<T>`、`std::is_compound_v<T>` 都为假？

<details markdown="1">
<summary>展开查看答案与解析</summary>

没有这样的类型。[meta.unary.comp] 中 `is_compound` 的条件是"`T` 是复合类型"，而 [[basic.compound]] 把除基本类型外的所有类型都归为复合类型；15 个主类别也恰好分成"基本"（`void`、`nullptr_t`、整型、浮点、`meta::info`）与"复合"（其余）两组。因此 `is_compound_v<T> == !is_fundamental_v<T>` 对所有类型成立。
</details>

## 小结

| 组 | 要点 |
|---|---|
| 主类别（15 个）| 两两互斥、覆盖全集；cv 无关；`is_reflection` 为 C++26 新增 |
| 复合类别（7 个）| 主类别的组合，可重叠；枚举不是算术类型但是标量类型；`meta::info` 是标量类型 |
| 属性查询 | `alignment_of`（= `alignof`）、`rank`、`extent`（未知边界与越界都给 0）|
