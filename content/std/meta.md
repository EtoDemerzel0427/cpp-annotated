---
title: 元编程库
summary: 第 21 章导读——编译期整数序列、<type_traits>、C++26 静态反射 <meta>、编译期有理数 <ratio>；从 TR1 的"类型进、布尔出"到 C++26 的"反射值进、反射值出"
status: draft
covers: meta.general
papers: P2996R13, P0013R1, P0595R2, P3247R2
related: intseq, type.traits, meta.unary.prop, meta.trans.other, meta.reflection, ratio, basic.types, expr.reflect
tags: 标准库, 元编程, type_traits, 反射
updated: 2026-10-18
---

第 21 章 [meta] 是标准库里**完全在编译期工作**的那一块：它不分配内存、不做 I/O，绝大多数组件根本不会生成一条机器指令。它要回答的问题是"**这个类型是什么、能做什么、怎样变成另一个类型**"，以及（C++26 起）"**这个程序里有哪些声明**"。

¶1 用一张表列出了本章的四个部分：

| 子条款 | 头文件 | 内容 | 本站笔记 |
|---|---|---|---|
| [intseq] | `<utility>` | `integer_sequence`、`make_index_sequence`：把"0..N-1"变成一个可推导、可展开的模板形参包 | [[intseq]] |
| [type.traits] | `<type_traits>` | 类型分类、类型性质、类型关系、类型变换、逻辑组合、成员关系、常量求值语境 | [[type.traits]] 起 |
| [meta.reflection] | `<meta>` | C++26 静态反射库：`std::meta::info` 上的查询、成员枚举、`substitute`、`define_aggregate` | [[meta.reflection]] 起 |
| [ratio] | `<ratio>` | `std::ratio<N, D>`：编译期精确有理数，`<chrono>` 的单位系统建立在它之上 | [[ratio]] |

注意 [intseq] 的组件声明在 `<utility>` 而不是 `<type_traits>`；`<type_traits>`、`<ratio>` 的概要第一行都写着 `// all freestanding`——独立实现（[[g:freestanding-implementation]]）也必须完整提供它们，因为它们不依赖任何运行时设施。

## 本章的两种"元编程范式"

读这一章，要意识到它其实并列着**两代**设计：

**第一代：类模板即函数（TR1 → C++23）**。`std::is_trivially_copyable<T>` 是一个类模板，"参数"是模板实参，"返回值"是基类 `integral_constant<bool, v>` 的静态成员 `value`；`std::remove_cv<T>` 的"返回值"是嵌套类型 `type`。计算靠模板实例化完成，分支靠偏特化或 SFINAE，循环靠递归实例化。[[meta.rqmts]] 把这种"函数"的形状正式规定为三种要求：*Cpp17UnaryTypeTrait*、*Cpp17BinaryTypeTrait*、*Cpp17TransformationTrait*（见 [[type.traits]]）。

**第二代：值即反射（C++26）**。`std::meta::info` 是一个**标量类型**（[[basic.fundamental]]），`^^T` 产生它的值（[[expr.reflect]]），`[: r :]` 把它拼回代码（[[basic.splice]]）。`<meta>` 里的函数都是普通的 `consteval` 函数：参数是 `info`，返回 `bool`、`info` 或 `vector<info>`，可以写 `for` 循环、用 `std::vector`、用 `ranges` 算法。[[meta.reflection.traits]] 甚至把第一代的每个 trait 都镜像成了一个 `consteval` 函数（`is_trivially_copyable_type(^^T)`、`remove_cv(^^T)`……）。

```cpp
// 第一代：类型进，类型/布尔出
static_assert(std::is_same_v<std::remove_cvref_t<const int&>, int>);

// 第二代（C++26 反射，本地 Clang 23 尚不支持，未验证）
// static_assert(std::meta::remove_cvref(^^const int&) == ^^int);
```

两代并非替代关系：`<type_traits>` 的几乎所有 trait 都是编译器内建函数的薄包装（例如 libc++ 的 `is_trivially_copyable` 就是 `integral_constant<bool, __is_trivially_copyable(_Tp)>`），实例化成本很低，仍然是日常泛型代码的主力；反射则解决 trait 根本无法表达的问题——**枚举一个类的成员、读出标识符、按描述生成一个新类**。

## 一条贯穿全章的主线：库在"翻译"核心语言

本章的条款很少自己定义新概念，绝大多数是在**把核心语言里的定义暴露成可查询的接口**：

| 库组件 | 对应的核心规则 |
|---|---|
| `is_trivially_copyable`、`is_standard_layout`、`is_implicit_lifetime` | [[basic.types.general#7]]、[[class.prop]] |
| `is_aggregate` | [[dcl.init.aggr]] |
| `is_structural` | [[temp.param]] 的结构化类型 |
| `is_layout_compatible`、`is_pointer_interconvertible_base_of` | [[basic.types]] 的布局兼容、[[basic.compound]] 的指针可互换 |
| `is_constructible`、`is_convertible` | 一个假想的变量定义 / `return` 语句是否良构（[[dcl.init]]、[[stmt.return]]） |
| `common_type` | 条件运算符 `?:` 的类型推导（[[expr.cond]]） |
| `reference_constructs_from_temporary` | 引用绑定与临时对象生存期延长（[[class.temporary]]） |
| `is_constant_evaluated`、`is_within_lifetime` | 常量求值（[[expr.const]]）与生存期（[[basic.life]]） |
| `std::meta::*` | [[expr.reflect]]、[[basic.splice]]、[[expr.const.reflect]] |

因此读这一章的正确姿势是：**先搞懂核心定义，再看库怎样精确地复述它**——尤其要看库在哪些地方**故意偏离**了直觉（例如 `is_signed<E>` 对枚举永远是 `false`，`is_trivially_constructible` 要考虑析构函数）。

## 历史与演进

!!! history "从 Boost 到反射"
    - **TR1（2005）/ C++11**：Boost.TypeTraits 进入标准，确立了 `integral_constant` 基类 + `::value` / `::type` 的接口。C++11 同时加入了 `<ratio>`（为 `<chrono>` 服务）、`declval`、`common_type`、`is_constructible` 系列等依赖新语言特性的 trait。
    - **C++14**：`_t` 别名模板（`remove_cv_t<T>`）、`integer_sequence`（[[N3658]]）。
    - **C++17**：`_v` 变量模板、`void_t`、`conjunction`/`disjunction`/`negation`（[[P0013R1]]）、`is_aggregate`、`has_unique_object_representations`、`is_invocable`/`invoke_result`（取代 `result_of`）。
    - **C++20**：`remove_cvref`（[[P0550R2]]）、`type_identity`（[[P0887R1]]）、`common_reference`（[[P0898R3]]）、`is_constant_evaluated`（[[P0595R2]]）、布局兼容与指针可互换系列（[[P0466R5]]）、`is_bounded_array`；`is_pod` 弃用。
    - **C++23**：`is_scoped_enum`（[[P1048R1]]）、`reference_constructs_from_temporary`（[[P2255R2]]）、`is_implicit_lifetime`（[[P2674R1]]）。
    - **C++26**：`is_virtual_base_of`、`is_within_lifetime`（[[P2641R4]]）、`is_trivial` 移入附录 D（[[P3247R2]]）、静态反射 `<meta>`（[[P2996R13]]）及其后续（注解 [[P3394R4]] 等）；`integer_sequence` 支持结构化绑定。

## 本章笔记索引

1. [[intseq]]：`integer_sequence` 与 `make_integer_sequence`，以及 C++26 的结构化绑定支持；
2. [[type.traits]]：trait 的三种形状、"不得特化"与"不完整类型"两条红线、`integral_constant`；
3. [[meta.unary]]：主类型类别、复合类型类别、`rank`/`extent`/`alignment_of`；
4. [[meta.unary.prop]]：类型性质——`is_constructible` 的精确定义、`is_trivially_*`、`is_nothrow_*`、`has_unique_object_representations`、`reference_constructs_from_temporary`；
5. [[meta.rel]]：`is_same`、`is_base_of`、`is_convertible` 的精确定义、`is_invocable`、布局兼容；
6. [[meta.trans]] 与 [[meta.trans.other]]：cv/引用/符号/数组/指针变换，`decay`、`common_type` 的完整算法、`common_reference`；
7. [[meta.logical]]、[[meta.member]]、[[meta.const.eval]]；
8. [[meta.reflection]]、[[meta.reflection.queries]]、[[meta.reflection.extract]]、[[meta.reflection.traits]]：C++26 反射库；
9. [[ratio]]。
