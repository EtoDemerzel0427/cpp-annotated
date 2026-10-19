---
title: 元编程库
summary: 第 21 章导读：编译期整数序列、<type_traits>、C++26 静态反射 <meta> 和编译期有理数 <ratio>，以及两代元编程接口的区别。
status: done
covers: meta.general
papers: P2996R13, P3247R2
related: intseq, type.traits, meta.unary.prop, meta.trans.other, meta.reflection, ratio, basic.types, expr.reflect
tags: 标准库, 元编程, type_traits, 反射
updated: 2026-10-19
---

!!! tldr
    - 第 21 章的组件全部在编译期工作：查询类型的性质、把一个类型变成另一个类型、在类型里携带整数和有理数，以及 C++26 的静态反射。
    - `<type_traits>` 是类模板接口：模板实参是输入，`::value` 或 `::type` 是输出。
    - C++26 的 `<meta>` 是值接口：反射值 `std::meta::info` 是输入和输出，查询是普通的 `consteval` 函数。
    - 大多数 trait 只是把核心语言里已有的定义（平凡可复制、聚合、可转换……）变成可以在代码里查询的形式，所以读懂 trait 要先读懂对应的核心规则。

## 四个部分

¶1 本章由四个子条款组成：

| 子条款 | 头文件 | 内容 |
|---|---|---|
| [[intseq]] | `<utility>` | `integer_sequence`、`make_index_sequence`：把 0..N-1 编码进一个类型，交给函数模板推导成形参包 |
| [[type.traits]] | `<type_traits>` | 类型分类、类型性质、类型关系、类型变换、逻辑组合、成员关系、常量求值语境 |
| [[meta.reflection]] | `<meta>` | {{c++26}} 静态反射库：`std::meta::info` 上的查询、成员枚举、`substitute`、`define_aggregate` |
| [[ratio]] | `<ratio>` | `std::ratio<N, D>`：编译期的精确有理数，`<chrono>` 的单位建立在它之上 |

`integer_sequence` 声明在 `<utility>` 而不是 `<type_traits>`。`<type_traits>` 和 `<ratio>` 的概要第一行都写着 `// all freestanding`：独立实现（不依赖操作系统的实现，见 [[g:freestanding-implementation]]）也必须完整提供它们，因为它们不需要任何运行时支持。

## 两代接口

本章并列着两代设计。

第一代是 `<type_traits>`，以类模板充当编译期函数。`std::is_trivially_copyable<T>` 的输入是模板实参，输出是基类 `integral_constant<bool, v>` 里的静态成员 `value`；`std::remove_cv<T>` 的输出是嵌套类型 `type`。分支靠偏特化或 SFINAE，循环靠递归实例化。[[type.traits]] 页讲这种接口的三种标准形状。

第二代是 C++26 的 `<meta>`。`std::meta::info` 是一个标量类型（[[basic.fundamental]]），`^^T` 得到它的值（[[expr.reflect]]），`[: r :]` 把它拼回代码（[[basic.splice]]）。`<meta>` 里的函数都是普通的 `consteval` 函数，参数是 `info`，返回 `bool`、`info` 或 `vector<info>`，可以用 `for` 循环和 `ranges` 算法处理。[[meta.reflection.traits]] 还给第一代的每个 trait 配了一个对应的函数。

```cpp
// 第一代：类型进，类型或布尔值出
static_assert(std::is_same_v<std::remove_cvref_t<const int&>, int>);

// 第二代：反射值进，反射值出
static_assert(std::meta::remove_cvref(^^const int&) == ^^int);
```

第二个断言没有经过编译验证：本机 Clang 23 不支持反射，libc++ 也没有 `<meta>` 头文件。

两代不是替代关系。`<type_traits>` 的 trait 大多是编译器内建函数的薄包装，实例化成本很低，仍然是日常泛型代码的主力。反射解决的是 trait 表达不了的问题：枚举一个类的成员、读出声明的名字、按描述生成一个新类。

## trait 在复述核心语言

本章很少定义新概念。大多数 trait 是把核心语言里的某个定义变成可以查询的接口：

| 库组件 | 对应的核心规则 |
|---|---|
| `is_trivially_copyable`、`is_standard_layout`、`is_implicit_lifetime` | [[basic.types.general#7]]、[[class.prop]] |
| `is_aggregate` | [[dcl.init.aggr]] |
| `is_structural` | [[temp.param]] 的结构化类型 |
| `is_layout_compatible`、`is_pointer_interconvertible_base_of` | [[basic.types]] 的布局兼容、[[basic.compound]] 的指针可互换 |
| `is_constructible`、`is_convertible` | 一个假想的变量定义或 `return` 语句是否良构（[[dcl.init]]、[[stmt.return]]） |
| `common_type` | 条件运算符 `?:` 的结果类型（[[expr.cond]]） |
| `reference_constructs_from_temporary` | 引用绑定与临时对象的生存期延长（[[class.temporary]]） |
| `is_constant_evaluated`、`is_within_lifetime` | 常量求值（[[expr.const]]）与生存期（[[basic.life]]） |
| `std::meta::*` | [[expr.reflect]]、[[basic.splice]] |

所以读一个 trait 时，先弄清它对应的核心定义，再看库的措辞在哪里和直觉不一样。例如 `is_signed<E>` 对枚举总是 `false`，`is_nothrow_constructible` 在 Clang 上还要看析构函数。

## 演进

!!! history
    - C++11 从 TR1 接收了 type traits，确立了 `integral_constant` 基类加 `::value`、`::type` 的接口，同时加入 `<ratio>`、`declval`、`common_type` 和依赖新语言特性的 `is_constructible` 系列。
    - C++14 加入 `_t` 别名模板（`remove_cv_t<T>`）和 `integer_sequence`。
    - C++17 加入 `_v` 变量模板、`void_t`、`conjunction` / `disjunction` / `negation`、`is_aggregate`、`has_unique_object_representations`，并用 `is_invocable` / `invoke_result` 取代 `result_of`。
    - C++20 加入 `remove_cvref`、`type_identity`、`common_reference`、`is_constant_evaluated`、布局兼容与指针可互换系列，弃用 `is_pod`。
    - C++23 加入 `is_scoped_enum`、`reference_constructs_from_temporary`、`is_implicit_lifetime`。
    - C++26 加入 `is_virtual_base_of`、`is_within_lifetime`、静态反射 `<meta>`（[[P2996R13]]），弃用 `is_trivial`（[[P3247R2]]），并让 `integer_sequence` 支持结构化绑定。

## 各页索引

1. [[intseq]]：`integer_sequence`、`make_integer_sequence` 和 C++26 的结构化绑定支持；
2. [[type.traits]]：trait 的三种形状、不得特化与不完整类型两条规则、`integral_constant`；
3. [[meta.unary]]：主类型类别、复合类型类别、`rank` / `extent` / `alignment_of`；
4. [[meta.unary.prop]]：类型性质，包括 `is_constructible` 的精确定义和它的平凡、不抛异常变体；
5. [[meta.rel]]：`is_same`、`is_base_of`、`is_convertible`、`is_invocable`、布局兼容；
6. [[meta.trans]] 与 [[meta.trans.other]]：各种类型变换，`decay`、`common_type`、`common_reference`；
7. [[meta.logical]]、[[meta.member]]、[[meta.const.eval]]；
8. [[meta.reflection]] 及其子页：C++26 反射库；
9. [[ratio]]。
