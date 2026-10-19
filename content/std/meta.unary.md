---
title: 一元类型特征
summary: 主类型类别谓词把每个类型恰好归入一类，复合类别谓词是它们的组合；rank、extent、alignment_of 查询数组维数、边界和对齐。
status: done
covers: meta.unary.general, meta.unary.cat, meta.unary.comp, meta.unary.prop.query
related: type.traits, meta.unary.prop, basic.types, basic.fundamental, basic.compound, dcl.array, dcl.fct, expr.alignof
tags: 标准库, type_traits, 类型分类
updated: 2026-10-19
---

!!! tldr
    - 15 个主类型类别谓词（`is_void`、`is_integral`、`is_pointer`、`is_class` ……）互不重叠：任何类型恰好让其中一个为真。
    - 复合类别谓词（`is_arithmetic`、`is_scalar`、`is_object` ……）是主类别的组合，可以重叠。
    - 两类谓词都不看顶层 cv：`is_integral_v<const volatile int>` 为真。
    - 常被记错的几条：成员指针不是指针，枚举不是算术类型但是标量类型，`std::array` 不是数组类型。
    - `rank`、`extent`、`alignment_of` 的结果是 `size_t` 数值，`extent` 对未知边界和越界都给 0。

## 总则 [meta.unary.general]

¶1 [meta.unary] 里的模板用来在编译期查询一个类型的性质。它分三部分：主类型类别、复合类型类别和类型性质。类型性质的内容很多，单独成页，见 [[meta.unary.prop]]。

¶2 这些模板都是 *Cpp17UnaryTypeTrait*（[[type.traits]]）：条件为真时派生自 `true_type`，否则派生自 `false_type`。

## 主类型类别 [meta.unary.cat]

```cpp title="primary-categories.cpp" run ok
#include <array>
#include <cstddef>
#include <type_traits>

struct S { int m; void f(); };
union U { int a; };
using Abominable = void() const;

static_assert(!std::is_array_v<std::array<int, 3>>);           // 类模板 array 不是数组类型
static_assert( std::is_array_v<int[]>);                        // 未知边界数组也是
static_assert(!std::is_pointer_v<int S::*>);                   // 成员指针不是指针
static_assert( std::is_pointer_v<void (*)()>);                 // 函数指针是指针
static_assert(!std::is_pointer_v<std::nullptr_t>);
static_assert( std::is_null_pointer_v<const std::nullptr_t>);  // cv 不影响结果
static_assert(!std::is_function_v<int (&)()>);                 // 函数引用是引用
static_assert( std::is_function_v<Abominable>);                // 带 cv 限定的函数类型也是
static_assert( std::is_member_function_pointer_v<void (S::*)() const&&>);
static_assert( std::is_integral_v<bool> && std::is_integral_v<char8_t>);
static_assert(!std::is_class_v<U> && std::is_union_v<U>);
static_assert( std::is_class_v<decltype([] {})>);              // 闭包类型是类

int main() {}
```

¶1 主类型类别与 [[basic.types]] 中的类型分类一一对应。¶3 的注说明了它们的设计目标：

!!! std
    For any given type `T`, exactly one of the primary type categories has a `value` member that evaluates to `true`.

也就是说，这 15 个谓词把所有 C++ 类型分成互不相交、合起来覆盖全部类型的 15 格：

| 分组 | 谓词 | 条件 | 备注 |
|---|---|---|---|
| 基本类型 | `is_void` | `void` | |
| | `is_null_pointer` | `std::nullptr_t` | 不是指针 |
| | `is_integral` | 整型（[[basic.fundamental]]） | 含 `bool`、所有字符类型、扩展整数类型 |
| | `is_floating_point` | 浮点类型 | 含扩展浮点类型 |
| | `is_reflection` {{c++26}} | `std::meta::info` | |
| 复合类型 | `is_array` | 已知或未知边界的数组 | `std::array` 不是数组类型 |
| | `is_pointer` | 指针类型 | 含函数指针，不含成员指针 |
| | `is_lvalue_reference`、`is_rvalue_reference` | 左值引用、右值引用 | |
| | `is_member_object_pointer`、`is_member_function_pointer` | 数据成员指针、成员函数指针 | |
| | `is_enum` | 枚举 | 有作用域和无作用域都算 |
| | `is_union` | 联合体 | |
| | `is_class` | 非联合的类类型 | 闭包类型也是类 |
| | `is_function` | 函数类型 | 含带 cv 或引用限定的函数类型；不含函数引用、函数指针 |

`void() const` 这种带限定符的函数类型不能用来声明普通函数，只出现在成员函数指针的被指向类型里，但它确实是函数类型（[[dcl.fct]]）。

¶2 把这些模板应用于 `T` 和 *cv* `T`，结果必须相同。引用类型和函数类型上的 cv 限定本来就会被忽略，对它们这条规则自然成立。

!!! note "没有编译器内建时怎样写 `is_function`"
    函数类型的形状很多：形参列表、`noexcept`、cv 和引用限定、C 风格变参。早期实现利用了一个核心语言事实：只有函数类型和引用类型加上 `const` 后保持不变（[[dcl.fct]]、[[dcl.ref]]）。于是可以这样写：

    ```cpp
    template<class T>
    struct is_function
      : std::bool_constant<!std::is_const_v<const T> && !std::is_reference_v<T>> {};
    ```

    今天的 libc++ 直接用 Clang 内建 `__is_function(_Tp)`。

!!! impl "实现的扩展类型归到哪一类"
    标准规定整型包括扩展整数类型，浮点类型包括扩展浮点类型。本机 Clang 23 + libc++ 中：

    - `is_integral_v<__int128>` 和 `is_integral_v<unsigned _BitInt(7)>` 都为真，libc++ 用的是 Clang 的 `__is_integral` 内建；
    - `is_floating_point_v<_Float16>` 为假，libc++ 的 `is_floating_point` 只对 `float`、`double`、`long double` 做了特化。libc++ 也没有提供 `<stdfloat>`。

    `_Float16` 是 Clang 的扩展，标准不强制实现把它当作扩展浮点类型，所以这不算违规。

## 复合类型类别 [meta.unary.comp]

¶1 复合类别谓词是主类别的组合，对应 [[basic.types]] 中的定义。¶2 同样不看 cv。和主类别不同，它们会重叠，例如 `int*` 既是标量类型又是复合类型。

| 谓词 | 条件 | 由哪些主类别组成 |
|---|---|---|
| `is_reference` | 引用 | 左值引用、右值引用 |
| `is_arithmetic` | 算术类型 | 整型、浮点 |
| `is_fundamental` | 基本类型 | 算术、`void`、`nullptr_t`、`meta::info` |
| `is_object` | 对象类型（[[basic.types.general#6]]） | 除函数、引用、`void` 以外的全部 |
| `is_scalar` | 标量类型 | 算术、枚举、指针、成员指针、`nullptr_t`、`meta::info` |
| `is_compound` | 复合类型（[[basic.compound]]） | 除基本类型以外的全部 |
| `is_member_pointer` | 成员指针 | 数据成员指针、成员函数指针 |

```cpp title="composite-categories.cpp" run ok
#include <cstddef>
#include <type_traits>

enum E { e };
struct S { int m; };

static_assert(!std::is_arithmetic_v<E> && !std::is_integral_v<E>);
static_assert( std::is_scalar_v<E>);
static_assert( std::is_fundamental_v<void> && !std::is_object_v<void>);
static_assert( std::is_object_v<int[]>);
static_assert(!std::is_object_v<int&> && std::is_compound_v<int&>);
static_assert( std::is_scalar_v<int S::*> && std::is_scalar_v<std::nullptr_t>);
static_assert(!std::is_scalar_v<int[1]>);

int main() {}
```

容易记错的几点：

- 枚举不是算术类型，也不是整型，尽管无作用域枚举可以整型提升；但枚举是标量类型。
- `void` 是基本类型，不是对象类型。未知边界数组 `int[]` 是对象类型，只是不完整。
- 引用是复合类型，不是对象类型。
- {{c++26}} `std::meta::info` 是标量类型（[[basic.types.general#7]]）。反射值像整数或指针一样复制和比较，所以可以做常量模板实参。

## 类型性质查询 [meta.unary.prop.query]

¶1–¶2 这三个模板也是 *Cpp17UnaryTypeTrait*，但基特征是 `integral_constant<size_t, Value>`，结果是一个数：

| 模板 | 值 |
|---|---|
| `alignment_of<T>` | `alignof(T)`；*Mandates*：`alignof(T)` 是有效表达式（[[expr.alignof]]） |
| `rank<T>` | 数组的维数；不是数组则为 0 |
| `extent<T, I = 0>` | 第 `I` 维（从 0 数起）的边界；`T` 不是数组、维数不超过 `I`，或 `I` 为 0 且 `T` 是未知边界数组时为 0 |

```cpp title="rank-extent.cpp" run ok
#include <type_traits>

static_assert(std::rank_v<int> == 0);
static_assert(std::rank_v<int[][4]> == 2);
static_assert(std::extent_v<int[2][4]> == 2);
static_assert(std::extent_v<int[2][4], 1> == 4);
static_assert(std::extent_v<int[][4]> == 0);       // 未知边界的第 0 维
static_assert(std::extent_v<int[][4], 1> == 4);
static_assert(std::extent_v<int[3][4], 2> == 0);   // 维数不够
static_assert(std::alignment_of_v<int&> == alignof(int));
static_assert(std::alignment_of_v<int[]> == alignof(int));

int main() {}
```

¶3–¶4 的标准例子与此类似。几点说明：

- `alignment_of` 出现在 `alignof` 运算符之前，今天直接写 `alignof(T)` 即可。按它的 *Mandates*，`alignment_of<void>` 和 `alignment_of<void()>` 非良构；`alignment_of<int&>` 合法，值是 `alignof(int)`，因为 `alignof` 作用于引用类型时取被引用类型的对齐；`alignment_of<int[]>` 的值是元素的对齐。
- `rank` 和 `extent` 只认内建数组，`rank_v<std::array<int, 3>>` 是 0。
- `extent` 用 0 同时表示不是数组、越界和未知边界，需要区分时配合 `is_bounded_array`、`is_unbounded_array`（[[meta.unary.prop]]）。

C++26 反射库有对应的 `consteval` 函数 `std::meta::rank` 和 `std::meta::extent`。`std::meta::alignment_of` 的适用范围更宽，也接受数据成员和变量的反射（[[meta.reflection.queries]]）。

## 常见错误

!!! pitfall "`is_pointer` 不认智能指针和成员指针"
    `is_pointer_v<std::unique_ptr<int>>` 为假，它是类类型；`is_pointer_v<int S::*>` 也为假，成员指针是单独的主类别。泛型代码想表达可以解引用的东西，应该用概念，如 `std::indirectly_readable`。

## 思考题

!!! question "思考题"
    对哪些类型 `T`，`std::is_fundamental_v<T>` 和 `std::is_compound_v<T>` 都为假？

<details markdown="1">
<summary>答案</summary>

没有这样的类型。[[basic.compound]] 把除基本类型以外的所有类型都归为复合类型；15 个主类别也正好分成基本（`void`、`nullptr_t`、整型、浮点、`meta::info`）和复合（其余）两组。所以对所有类型都有 `is_compound_v<T> == !is_fundamental_v<T>`。
</details>

## 小结

| 组 | 要点 |
|---|---|
| 主类别（15 个） | 两两互斥，覆盖全部类型；不看 cv；`is_reflection` 是 C++26 新增 |
| 复合类别（7 个） | 主类别的组合，可以重叠；枚举不是算术类型但是标量类型 |
| 性质查询 | `alignment_of` 等于 `alignof`；`rank`、`extent` 只认内建数组，未知边界和越界都给 0 |
