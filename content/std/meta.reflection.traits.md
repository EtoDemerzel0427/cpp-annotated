---
title: 反射类型特征
summary: <type_traits> 中几乎每个 trait 在 std::meta 中都有一个接受反射的 consteval 版本；本节规定它们的命名、出错时抛异常还是拒绝编译，以及结果总是去掉别名的类型。
status: draft
covers: meta.reflection.traits
since: c++26
papers: P2996R13
related: meta.reflection, type.traits, meta.unary, meta.unary.prop, meta.rel, meta.trans, meta.trans.other, meta.reflection.extract
tags: 反射, C++26, 标准库, type_traits
updated: 2026-10-19
---

!!! tldr
    - `std::is_X<T>` 对应 `std::meta::is_X_type(^^T)`，变换 `std::X<T>::type` 对应 `std::meta::X(^^T)`；结果与模板版本完全相同。
    - 谓词加 `_type` 后缀，是为了与 `std::meta::is_const`、`is_function` 等含义不同的反射查询区分开。
    - 实参不是类型的反射，或者模板版本会因违反 *Mandates* 而报错、没有 `type` 成员时，反射版本抛出 `meta::exception`，可以在 `consteval` 代码中捕获。
    - 返回反射的函数总是返回类型本身，从不返回别名；比较两个类型的反射要用 `is_same_type` 或先 `dealias`，不能直接 `==`。

!!! note "关于本页的例子"
    本机 Clang 23 还不支持 C++26 反射。本页代码依据当前草案编写，没有经过编译，因此不标判定。

```cpp
#include <meta>

// 判断一个类的所有非静态数据成员是否都可平凡复制
consteval bool all_members_trivially_copyable(std::meta::info cls) {
  auto ctx = std::meta::access_context::unchecked();
  for (std::meta::info m : std::meta::nonstatic_data_members_of(cls, ctx))
    if (!std::meta::is_trivially_copyable_type(std::meta::type_of(m)))
      return false;
  return true;
}
```

用 `<type_traits>` 写同样的检查，要先把成员类型组成一个类型包，而 C++26 之前的语言根本拿不到这个包。反射让类型成了普通的值，于是 trait 也需要一个接受值的版本，才能和 `for` 循环、`vector`、算法组合使用。

¶1 [meta.reflection.traits] 没有定义任何新的语义：这里的每个 `consteval` 函数都对应 [[meta.unary]]、[[meta.rel]] 或 [[meta.trans]] 中的一个类模板，称为它的关联类模板，函数的结果就是那个类模板给出的结果。

## 命名规则（¶4）

| 关联 trait 的种类 | 反射版本 | 例 |
|---|---|---|
| 一元谓词 `std::X<T>` | `bool X_type(info)` | `is_trivially_copyable_type(^^T)` |
| 二元谓词 `std::X<T, U>` | `bool X_type(info, info)` | `is_same_type`、`is_base_of_type`、`is_convertible_type` |
| 变参谓词 `std::X<T, U...>` | `bool X_type(info, R&& args)` | `is_constructible_type(^^T, {^^int, ^^int})` |
| 变参谓词 `std::X<R, F, U...>` | `bool X_type(info, info, R&& args)` | `is_invocable_r_type` |
| 一元变换 `std::X<T>::type` | `info X(info)`，不加后缀 | `remove_cvref(^^T)`、`decay(^^T)` |
| 变参变换 | `info X(R&& args)` 或 `info X(info, R&& args)` | `common_type({...})`、`invoke_result(^^F, {...})` |

其中 `R` 受 `reflection_range` 约束，即元素为 `info` 的范围（见 [[meta.reflection.extract]]），`{^^int, ^^int}` 这样的花括号列表也可以。

不加 `_type` 后缀的谓词只有 `has_virtual_destructor`、`has_unique_object_representations`、`reference_constructs_from_temporary` 和 `reference_converts_from_temporary`，它们的名字本来就不以 `is_` 开头。

为什么谓词要加后缀？因为 `std::meta` 里已经有一批同名、含义不同的查询（[[meta.reflection.queries]]）：

```cpp
const int v = 0;
static_assert(std::meta::is_const(^^v));                // 变量 v 的类型带 const
static_assert(std::meta::is_const_type(^^const int));   // 类型 const int
// std::meta::is_const_type(^^v);                       // 抛出异常：^^v 不是类型的反射
```

`is_const(r)` 问反射所代表的东西是否带 `const`，可以作用于变量、函数类型等；`is_const_type(r)` 才是 `std::is_const` 的对应物，只接受类型。同理，`is_function(r)` 问 `r` 是否代表一个函数，`is_function_type(r)` 问它是否是函数类型。变换函数没有这种冲突，直接沿用原名。

### 不套用上面模式的函数（¶7–¶13）

| 函数 | 结果 |
|---|---|
| `rank(type)`、`extent(type, i = 0)` | `std::rank<T>::value`、`std::extent<T, I>::value` |
| `tuple_size(type)`、`tuple_element(index, type)` | `std::tuple_size<T>::value`、`std::tuple_element<I, T>::type` 的反射 |
| `variant_size(type)`、`variant_alternative(index, type)` | 同理 |
| `type_order(t1, t2)` | `std::type_order<T1, T2>::value`，类型为 `strong_ordering` |

这里的 `index` 和 `i` 是普通的函数形参，不必是常量表达式：`tuple_element(i, ^^T)` 中的 `i` 可以是循环变量。这是反射版本比模板版本方便的地方。

`<meta>` 的概要（[[meta.syn]]）还声明了 `is_applicable_type`、`is_nothrow_applicable_type` 和 `apply_result`，对应 `std::is_applicable` 等。注意 `alignment_of` 不在本节：`std::meta::alignment_of` 是 [[meta.reflection.queries]] 中的布局查询，除了类型还接受变量、数据成员等。

## 出错时怎么办（¶2–¶3）

```cpp
consteval bool has_signed_version(std::meta::info t) {
  try {
    (void)std::meta::make_signed(t);
    return true;
  } catch (const std::meta::exception&) {
    return false;
  }
}
static_assert( has_signed_version(^^unsigned));
static_assert(!has_signed_version(^^bool));   // std::make_signed<bool> 违反 Mandates
```

¶2 实参必须是类型的反射。类型为 `info` 的每个形参都必须满足 `is_type`，`reflection_range` 实参的每个元素也一样，否则抛出 `meta::exception`。所以 `is_class_type(^^std::vector)`（模板不是类型）和 `remove_cvref(^^some_variable)` 都会抛出异常。

¶3 处理关联类模板本身出问题的情况。设 `S` 是这次调用对应的类模板特化：

1. ¶3.1 如果 `S` 的模板实参违反了类模板的 *Mandates*，或者调用要返回类型而 `S` 没有成员 `type`，或者 `S::value` 不能转换成函数的返回类型，就抛出 `meta::exception`。第一种情况下 `S` 不会被实例化（注 1）。所以 `make_signed(^^bool)`、`common_type({^^int, ^^std::string})`、`underlying_type(^^int)` 都抛出异常，可以在 `consteval` 代码中捕获；而对应的模板版本要么是硬错误，要么没有 `type`。
2. ¶3.2 否则，如果实例化 `S` 会因为依赖不完整类型而导致未定义行为（[[meta.rqmts]] 第 5 段），这次调用就不是常量子表达式，编译器必须拒绝。
3. ¶3.3 否则，如果模板实参不满足类模板的前置条件（最常见的是要求类型完整），调用是否是常量子表达式未指明；如果是，结果就和类模板没有这条前置条件时一样。

第 2、3 条对应 [[type.traits]] 中关于不完整类型的两层规则。模板版本违反这些规则是未定义行为；常量求值中不允许出现未定义行为，所以反射版本把它收紧为要么拒绝编译，要么给出一个确定的结果。

## 结果是类型，不是别名（¶4–¶6）

```cpp
using Int = int;
static_assert(^^int != ^^Int);                          // 类型与别名是不同的构造
static_assert(std::meta::is_same_type(^^int, ^^Int));   // 但它们是同一个类型
static_assert(^^int == std::meta::dealias(^^Int));
static_assert(std::meta::remove_cvref(^^const Int&) == ^^int);   // 结果已去掉别名
```

¶4 表 64 统一规定了各种签名的返回值：谓词返回 `std::X<T...>::value`，变换返回代表 `std::X<T...>::type` 的反射，其中 `T` 是实参所代表的类型或类型别名。实现不必真的实例化关联类模板，可以直接用编译器内建的方式计算（注 2）。

¶5 返回反射的函数，结果总是代表类型，从不代表类型别名（注 3）。¶6 反过来，反射的 `==` 比较的是所代表的构造：`^^int` 代表类型，`^^Int` 代表别名，两者不相等，但 `is_same_type` 认为它们是同一个类型（注 4）。所以在反射代码里比较类型，要用 `is_same_type`，或者先 `dealias` 再比较。
