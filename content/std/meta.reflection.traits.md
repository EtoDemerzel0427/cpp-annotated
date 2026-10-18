---
title: 反射类型特征
summary: <type_traits> 中几乎每个 trait 在 std::meta 中都有一个 consteval 镜像（is_X_type、remove_cvref、common_type……），外加 tuple_size、variant_size、type_order 等；本节规定命名规则、实参须为类型反射、何时抛 meta::exception、前置条件违反时"是否常量子表达式未指明"，以及结果总是去别名的类型
status: draft
covers: meta.reflection.traits
since: c++26
papers: P2996R13
related: meta.reflection, type.traits, meta.unary, meta.unary.prop, meta.rel, meta.trans, meta.trans.other, meta.reflection.extract
tags: 反射, C++26, 标准库, type_traits
updated: 2026-10-18
---

!!! warning "未经本地验证"
    本地 Clang 23 不支持 C++26 反射。本页代码依据当前草案编写，未经编译验证，不标判定。

反射让"类型"变成了值，于是 `<type_traits>` 的整套查询就需要一个"值版本"：给一个 `info`，问它是否平凡可复制、去掉引用后是什么类型。[meta.reflection.traits] 不重新定义任何语义——¶1 说得很清楚：这里的每个 `consteval` 函数都有一个在别处声明的**关联类模板**，函数的结果就是那个类模板的结果。

## 命名规则

| 关联 trait 的种类 | 反射版的名字与签名 | 例 |
|---|---|---|
| 一元谓词 `std::X<T>` | `bool meta::X_type(info)`（`has_*` 与 `reference_*_from_temporary` 不加后缀）| `is_trivially_copyable_type(^^T)`、`has_virtual_destructor(^^T)` |
| 二元谓词 `std::X<T, U>` | `bool meta::X_type(info, info)` | `is_same_type`、`is_base_of_type`、`is_convertible_type` |
| 变参谓词 `std::X<T, U...>` | `bool meta::X_type(info, R&& args)` | `is_constructible_type(^^T, {^^int, ^^int})` |
| 变参谓词 `std::X<R, F, U...>` | `bool meta::X_type(info, info, R&& args)` | `is_invocable_r_type` |
| 一元变换 `std::X<T>::type` | `info meta::X(info)`（**不加**后缀）| `remove_cvref(^^T)`、`decay(^^T)` |
| 变参变换 | `info meta::X(R&& args)` / `info meta::X(info, R&& args)` | `common_type({...})`、`invoke_result(^^F, {...})` |

为什么谓词要加 `_type` 后缀？因为 `std::meta` 里已经有一批**同名但语义不同**的查询：`std::meta::is_const(r)` 问的是"这个反射所代表的东西是否 const"（可以是变量、函数类型，见 [[meta.reflection.queries]]），`std::meta::is_function(r)` 问的是"它是否代表一个函数"，而 `is_function_type(r)` 才是 `std::is_function` 的镜像。后缀消除了这种歧义。变换函数则没有冲突，直接沿用原名。

额外的几个函数没有对应的一元/二元模式，单独规定：

| 函数 | 结果 |
|---|---|
| `rank(type)`、`extent(type, i = 0)` | `std::rank<T>::value`、`std::extent<T, I>::value` |
| `tuple_size(type)`、`tuple_element(index, type)` | `std::tuple_size<T>::value`、`std::tuple_element<I, T>::type` 的反射 |
| `variant_size(type)`、`variant_alternative(index, type)` | 同理 |
| `type_order(t1, t2)` | `std::type_order<T1, T2>::value`（`strong_ordering`）|
| `is_applicable_type`、`is_nothrow_applicable_type`、`apply_result` | 概要（[meta.syn]）中与 `tuple_size` 等一同声明，对应 `is_applicable` 等 |

注意 `alignment_of` 没有出现在这里：`std::meta::alignment_of` 是 [[meta.reflection.queries]] 中的布局查询，语义更宽（接受变量、数据成员等）。

`index` 是普通函数形参（`size_t`），这是反射版相对于模板版最大的便利：`tuple_element(i, ^^T)` 中的 `i` 可以是循环变量，不必是常量表达式。

## 错误与前置条件（¶2–¶3）

¶2：每个函数在以下条件不满足时抛 `meta::exception`：类型为 `info` 的每个形参 `is_type(p)` 为真；受 `reflection_range` 约束的每个形参，其所有元素 `is_type` 为真。也就是说，`is_class_type(^^std::vector)`（模板，不是类型）或 `remove_cvref(^^some_variable)` 会抛异常。

¶3 处理"关联类模板会出错"的情况。设 `S` 是调用所对应的关联类模板特化：

1. （¶3.1）若 `S` 的模板实参违反该类模板的 *Mandates*；或调用应产生类型反射而 `S` 没有成员 `type`；或调用应返回 `S::value` 而它不是返回类型的有效转换后常量表达式——**抛 `meta::exception`**。注 1：第一种情况下 `S` **不会被实例化**。所以 `make_signed(^^bool)`、`common_type({^^int, ^^std::string})`、`underlying_type(^^int)` 都抛异常，可以在 `consteval` 代码里 `catch`——而对应的模板版本是硬错误或"没有 `type`"。
2. （¶3.2）否则，若 `S` 的实例化会因为依赖不完整类型而导致 UB（[[type.traits]] 讨论的 [meta.rqmts] ¶5），则调用**不是常量子表达式**——编译器必须拒绝，而不是给出一个可能错误的答案。
3. （¶3.3）否则，若 `S` 的模板实参不满足该类模板的**前置条件**（典型的"须为完整类型"），则调用**是否为常量子表达式是未指明的**；如果是，结果就像类模板没有那条前置条件时一样。

第 2、3 条是对 `<type_traits>` 中两层不完整类型规则（见 [[type.traits]]）的"反射化"：模板版是 UB，反射版则被收紧为"要么拒绝、要么给出明确定义的结果"——常量求值中不允许出现 UB，这是合乎逻辑的选择。

## 结果总是类型，而不是别名（¶4–¶6）

¶4 用表 64 统一规定了各种签名的返回值：谓词返回 `std::X<T...>::value`，变换返回代表 `std::X<T...>::type` 的反射，其中 `T` 是实参所代表的类型**或类型别名**。注 2：关联类模板**不必**被实例化——实现可以直接用编译器内建求值。

注 3：返回反射的函数，结果**总是代表类型，从不代表类型别名**。注 4 点出了一个容易绊倒人的地方：

```cpp
using Int = int;
static_assert(^^int != ^^Int);                        // 反射比较的是"代表的构造"：类型 vs 别名
static_assert(std::meta::is_same_type(^^int, ^^Int)); // 但它们是同一个类型
static_assert(^^int == std::meta::dealias(^^Int));
static_assert(std::meta::remove_cvref(^^const Int&) == ^^int);   // 变换结果总是去别名的类型
```

所以在反射代码里比较两个类型，应当用 `is_same_type`（或先 `dealias`），而不是直接 `==`。

## 用法示例

反射版 trait 最大的价值是能与普通的控制流和算法组合：

```cpp
// 依据草案编写，未验证：判断一个聚合的所有非静态数据成员是否都可平凡复制
consteval bool all_members_trivially_copyable(std::meta::info cls) {
    auto ctx = std::meta::access_context::unchecked();
    for (std::meta::info m : std::meta::nonstatic_data_members_of(cls, ctx)) {
        if (!std::meta::is_trivially_copyable_type(std::meta::type_of(m)))
            return false;
    }
    return true;
}
```

用 `<type_traits>` 写同样的东西需要先把成员类型变成一个类型包——而在 C++26 之前这根本无法做到。

## 小结

| 规则 | 要点 |
|---|---|
| 命名 | `is_*` 谓词加 `_type` 后缀，`has_*` 等与变换沿用原名 |
| 实参 | 必须是类型的反射，否则抛异常 |
| *Mandates* 违反 / 无 `type` | 抛 `meta::exception`，关联模板不实例化 |
| 不完整类型导致的 UB | 调用不是常量子表达式 |
| 前置条件违反 | 是否常量子表达式未指明；若是，按无前置条件计算 |
| 结果 | 反射结果总是类型，不是别名；比较类型用 `is_same_type` |
