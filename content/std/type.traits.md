---
title: 元编程与类型特征
summary: <type_traits> 的总则——trait 的三种形状（一元/二元/变换）与"基特征"、用户特化 trait 是 UB、不完整类型的两层规则（逐个 trait 的前置条件 + "补全后结果会变"即 UB）、头文件概要的分组，以及 integral_constant/bool_constant
status: draft
covers: type.traits.general, meta.rqmts, meta.type.synop, meta.help
papers: P0013R1, P3247R2
related: meta, meta.unary, meta.unary.prop, meta.rel, meta.trans, meta.logical, basic.types, namespace.std, res.on.functions, depr.meta.types
tags: 标准库, type_traits, 元编程, UB, 不完整类型
updated: 2026-10-18
---

[type.traits] 是第 21 章的主体：从 [[meta.unary]] 到 [[meta.const.eval]] 的十几个子条款都挂在它下面。本页覆盖其中的"总则"部分——**一个 trait 应该长什么样、用户能对它做什么、不能做什么**——以及 `<type_traits>` 的概要与基础设施 `integral_constant`。具体每个 trait 的语义见后续各页。

## 这一节要干什么（[type.traits.general]）

¶1 给出了 trait 的三重用途：让模板支持尽可能多的类型、优化模板代码（典型例子：对平凡可复制类型用 `memcpy`）、在编译期发现与类型相关的用户错误、做类型推断与变换。并把 trait 分成三类：

- **类型分类**（type classification）：给出一个覆盖所有 C++ 类型的**完整分类体系**，判断给定类型落在哪一格——对应 [[meta.unary.cat]]、[[meta.unary.comp]]；
- **类型性质检查**（type property inspection）：检查单个类型或几个类型组合的重要特征——[[meta.unary.prop]]、[[meta.rel]]；
- **类型变换**（type transformations）：操纵类型的某些性质——[[meta.trans]]。

¶2：[type.traits] 中规定的所有**函数**都是**信号安全**的（[[support.signal]]）。这里的"函数"指 `is_constant_evaluated`、`is_within_lifetime`、`is_pointer_interconvertible_with_class` 等少数真正的函数，以及 `integral_constant` 的成员函数——它们可以在信号处理函数里调用。

## trait 的三种形状（[meta.rqmts] ¶1–¶3）

标准没有用"概念"来约束 trait，而是用三组命名要求描述它们的**接口形状**：

| 要求 | 用途 | 形状 |
|---|---|---|
| *Cpp17UnaryTypeTrait*（¶1）| 描述**一个类型的性质** | 类模板，一个类型实参（可附加辅助实参，如 `extent<T, I>`）；公开、无歧义地（直接或间接）派生自它的**基特征** |
| *Cpp17BinaryTypeTrait*（¶2）| 描述**两个类型的关系** | 类模板，两个类型实参（可附加实参）；同样派生自基特征 |
| *Cpp17TransformationTrait*（¶3）| **修改**一个类型的性质 | 类模板，一个类型实参（可附加实参）；声明公开的嵌套类型 `type`，作为修改后类型的同义词 |

**基特征**（[[g:base-characteristic]]，*base characteristic*）是一个 `integral_constant<T, v>` 的特化，`T` 和 `v` 由具体 trait 的语义决定。例如 `is_trivially_copyable<T>` 的基特征是 `true_type` 或 `false_type`，`rank<int[2][3]>` 的基特征是 `integral_constant<size_t, 2>`。前两类 trait 还要求：

- 是 *Cpp17DefaultConstructible* 与 *Cpp17CopyConstructible* 的——所以 `std::is_integral<int>{}` 能写；
- 基特征的成员名**不得被隐藏**，且在 trait 中**无歧义可用**——所以 `is_integral<int>::value`、`::type`、`::value_type` 一定能访问到基特征的版本。

!!! lawyer "\"派生自\"而不是\"就是\""
    要求只说 trait **派生自**基特征，并没有说 trait **就是**基特征。所以 `std::is_same<int, int>` 和 `std::true_type` 是**两个不同的类型**，而 `std::is_same<int, int>::type` 才是 `true_type`：

    ```cpp run title="base-characteristic.cpp" ok
    #include <type_traits>

    static_assert(!std::is_same_v<std::is_same<int, int>, std::true_type>);       // trait 本身是另一个类
    static_assert( std::is_same_v<std::is_same<int, int>::type, std::true_type>); // ::type 才是基特征
    static_assert( std::is_base_of_v<std::true_type, std::is_same<int, int>>);

    int main() {}
    ```

    这一点在**标签分发**（tag dispatch）里很重要：把 `std::is_integral<T>{}` 传给重载 `f(std::true_type)` / `f(std::false_type)` 时，靠的是**派生类到基类的转换**，而不是精确匹配。

变换 trait 只要求有 `type` 成员。注意 [[meta.trans.other]] 中的若干变换 trait（`enable_if<false>`、`common_type`、`underlying_type<非枚举>`、`invoke_result`）在某些情况下**没有** `type` 成员——这正是它们"SFINAE 友好"的来源；因此严格说它们只在 `type` 存在时才是 *Cpp17TransformationTrait*。

## 红线一：不得特化（¶4）

!!! std
    Unless otherwise specified, the behavior of a program that adds specializations for any of the templates specified in [type.traits] is undefined.

    除非另有规定，为 [type.traits] 中规定的任何模板添加特化的程序，其行为未定义。

这比 [[namespace.std]] 的一般规则更严：一般情况下用户**可以**为标准库类模板添加依赖于程序定义类型的特化（例如 `std::hash<MyType>`），但 type traits 默认**不可以**——哪怕特化的实参是你自己的类型。原因很直接：trait 的值是由核心语言规则决定的"事实"，允许用户撒谎（例如声称一个带虚函数的类 `is_trivially_copyable`）会让依赖它的库代码（`std::copy` 走 `memmove`、`std::atomic` 的要求检查）产生真正的 UB。

"另有规定"的例外只有两个，都在 [[meta.trans.other]]：

- `common_type<T1, T2>`（¶5）：可以为**退化后不变**（`is_same_v<T, decay_t<T>>`）的程序定义类型特化；
- `basic_common_reference<T, U, TQual, UQual>`（¶7）：可以偏特化，以影响 `common_reference` 的结果。

另外，`_v` 变量模板（`is_integral_v` 等）同样不能特化——[[namespace.std]] 规定，除非明确允许，为标准库**变量模板**添加特化是 UB。

!!! impl "libc++ 把这条 UB 变成了编译错误"
    libc++ 用 Clang 的 `[[clang::no_specializations]]` 属性标注了几乎所有 trait（宏 `_LIBCPP_NO_SPECIALIZATIONS`，定义在 `__configuration/attributes.h`）：

    ```cpp
    template <class _Tp>
    struct _LIBCPP_NO_SPECIALIZATIONS is_trivially_copyable
        : integral_constant<bool, __is_trivially_copyable(_Tp)> {};
    ```

    于是在 Clang 23 + libc++ 下：

    ```cpp run title="no-specialize.cpp" error
    #include <type_traits>

    struct My {};
    template<> struct std::is_trivially_copyable<My> : std::false_type {};   // error: cannot be specialized
    template<> inline constexpr bool std::is_integral_v<My> = true;          // error: cannot be specialized
    template<> struct std::common_type<My, int> { using type = My; };        // OK：标准明确允许

    int main() {}
    ```

    诊断是 `'is_trivially_copyable' cannot be specialized: Users are not allowed to specialize this standard library entity [-Winvalid-specialization]`——它是一个默认即为错误的警告组。标准只说"UB"，实现完全可以选择给出诊断；这是"UB 允许实现做任何事"的一个良性用法。

## 红线二：不完整类型（¶5 与各 trait 的前置条件）

不完整类型的规则分**两层**，非常容易混淆：

**第一层：逐个 trait 的前置条件**。[[meta.unary.prop]]、[[meta.rel]]、[[meta.trans.other]] 的表格里，大多数 trait 都有一列 *Preconditions*，典型措辞是"`T` shall be a complete type, *cv* `void`, or an array of unknown bound"。违反 *Preconditions* 是 **UB**（库的一般规则，见 [[structure.specifications]] ¶3.4），并不要求诊断。

**第二层：¶5 的总括规则**。

!!! std
    Unless otherwise specified, an incomplete type may be used to instantiate a template specified in [type.traits]. The behavior of a program is undefined if an instantiation ... depends on an incompletely-defined object type `T`, and that instantiation could yield a different result were `T` hypothetically completed.

    除非另有规定，可以用不完整类型实例化 [type.traits] 中的模板。但如果某个实例化直接或间接依赖于某个**不完全定义的对象类型** `T`，并且假如 `T` 被补全后该实例化**可能得出不同的结果**，则程序的行为未定义。

¶5 先"开了门"：与 [[res.on.functions]] 的一般规则（用不完整类型实例化库模板是 UB，除非特别允许）相反，trait 默认**允许**不完整类型——`is_class_v<Incomplete>`、`is_same_v<Incomplete, int>`、`add_pointer_t<Incomplete>` 都没问题，因为补全与否都不影响答案。然后它又"关了门"：只要答案**可能**因补全而改变，就是 UB。这里的 [[g:incompletely-defined-object-type]] 指已声明未定义的类、某些语境下的枚举、未知边界数组或元素类型不完整的数组（[[basic.types.general#3]]）。

为什么要这条规则？因为**模板特化只实例化一次**。第一次实例化时编译器用当时的信息算出答案，之后同一个特化在整个程序中必须是同一个东西（[[temp.point]]、ODR）。如果中途类型被补全，旧答案就成了谎言：

```cpp run title="incomplete-trait.cpp" ub
#include <cstdio>
#include <type_traits>

struct Base {};
struct Derived;                                   // 此时只声明、未定义

constexpr bool before = std::is_convertible_v<Derived*, Base*>;   // UB：结果依赖不完整类型

struct Derived : Base {};                         // 现在完整了

constexpr bool after = std::is_convertible_v<Derived*, Base*>;

int main() {
    Derived d;
    Base* pb = &d;                                // 语言本身当然允许这个转换
    std::printf("before=%d after=%d real=%d\n", before, after, pb != nullptr);
}
```

在本地 Clang 23 + libc++ 下输出 `before=0 after=0 real=1`：`is_convertible_v<Derived*, Base*>` 这个**变量模板特化**在第一次用到时被实例化为 `false`，补全 `Derived` 之后再问，拿到的还是缓存的 `false`——与 `Base* pb = &d;` 的事实相矛盾。注意 `Derived*` 本身是完整类型，所以第一层前置条件并没有被违反；是 ¶5 让它成为 UB。

!!! impl "编译器能查出多少？"
    对第一层前置条件，Clang 的内建 trait 大多会报错："incomplete type 'Inc' used in type trait expression"——`is_trivially_copyable`、`is_constructible`、`is_base_of`、`is_empty` 等都是如此。但并非全部：本地测试中 `std::is_convertible_v<Inc, int>`（`Inc` 不完整）**静默地**得到 `false`，尽管它违反了 `From` 必须完整的前置条件。至于第二层（"补全后会变"），编译器原则上无法检测，上面的例子没有任何诊断。

## 头文件 `<type_traits>` 概要（[meta.type.synop]）

概要以 `// all freestanding` 开头。下面按子条款分组概览（完整列表见各页）：

| 分组 | 代表成员 | 页面 |
|---|---|---|
| 辅助类 | `integral_constant`、`bool_constant`、`true_type`、`false_type` | 本页 |
| 主类型类别 | `is_void` … `is_function`、`is_reflection`{{c++26}} | [[meta.unary]] |
| 复合类型类别 | `is_reference`、`is_arithmetic`、`is_fundamental`、`is_object`、`is_scalar`、`is_compound`、`is_member_pointer` | [[meta.unary]] |
| 类型性质 | `is_const` … `is_aggregate`、`is_structural`、`is_constructible` 系、`is_assignable` 系、`is_swappable` 系、`is_destructible` 系、`is_implicit_lifetime`、`has_unique_object_representations`、`reference_*_from_temporary` | [[meta.unary.prop]] |
| 类型性质查询 | `alignment_of`、`rank`、`extent` | [[meta.unary]] |
| 类型关系 | `is_same`、`is_base_of`、`is_virtual_base_of`、`is_convertible`、`is_layout_compatible`、`is_pointer_interconvertible_base_of`、`is_invocable` 系、`is_applicable` 系 | [[meta.rel]] |
| cv/引用/符号/数组/指针变换 | `remove_const`、`add_lvalue_reference`、`make_signed`、`remove_extent`、`add_pointer` … | [[meta.trans]] |
| 其他变换 | `type_identity`、`remove_cvref`、`decay`、`enable_if`、`conditional`、`common_type`、`common_reference`、`underlying_type`、`invoke_result`、`apply_result`、`unwrap_reference`、`void_t` | [[meta.trans.other]] |
| 逻辑组合 | `conjunction`、`disjunction`、`negation` | [[meta.logical]] |
| 成员关系 | `is_pointer_interconvertible_with_class`、`is_corresponding_member` | [[meta.member]] |
| 常量求值语境 | `is_constant_evaluated`、`is_within_lifetime` | [[meta.const.eval]] |

几个命名约定：

- 每个变换 trait `X` 都有别名 `X_t<T>` = `X<T>::type`（C++14）；概要里写作 `remove_cv<T>::type`，**不带 `typename`**——这是 C++20 起在某些语境下可以省略 `typename`（[[temp.res.general]]）带来的写法。
- 每个谓词/查询 trait 都有变量模板 `X_v<...>` = `X<...>::value`（C++17）。
- `void_t` 是唯一一个**没有**对应类模板的别名：`template<class...> using void_t = void;`，它的全部价值在于"让实参中的替换失败触发 SFINAE"。
- 已弃用的 `is_trivial`、`is_pod`、`aligned_storage`、`aligned_union` 不在这份概要里，而在附录 D 的 [[depr.meta.types]]（`is_trivial` 是 C++26 移入的，[[P3247R2]]）。libc++ 仍然提供它们，但会给出 `-Wdeprecated-declarations` 警告。

## 辅助类 `integral_constant`（[meta.help]）

```cpp
namespace std {
  template<class T, T v> struct integral_constant {
    static constexpr T value = v;
    using value_type = T;
    using type = integral_constant<T, v>;
    constexpr operator value_type() const noexcept { return value; }
    constexpr value_type operator()() const noexcept { return value; }
  };
  template<bool B> using bool_constant = integral_constant<bool, B>;
  using true_type  = bool_constant<true>;
  using false_type = bool_constant<false>;
}
```

¶1：它们被用作基类，为各种 trait 定义统一的接口。几个设计细节：

- `type` 指向**自身**。这让"取 `::type`"成为幂等操作，也让 trait 能直接充当返回 `integral_constant` 的元函数——`is_same<A, B>::type` 正是基特征。
- **转换函数** `operator value_type()`：`integral_constant` 的对象可以隐式转换为它的值，`if (std::is_integral<T>{})`、`five{} + five{}` 都能写。
- **函数调用运算符** `operator()()`（C++14）：`std::is_integral<int>{}()` 返回 `true`，使 trait 对象可以当作"无参可调用对象"传递。
- `value` 是 `static constexpr` 数据成员，自 C++17 起隐式为 inline 变量，不再需要类外定义。
- `bool_constant` 是 C++17 才加入的别名（之前很多库各自定义 `bool_constant`）。

```cpp run title="integral-constant.cpp" ok
#include <cstdio>
#include <type_traits>

using five = std::integral_constant<int, 5>;
static_assert(five{} + five{} == 10);                    // 隐式转换为 int
static_assert(std::is_integral<int>{}());                // operator()

template<class T> void kind(std::true_type)  { std::puts("integral"); }
template<class T> void kind(std::false_type) { std::puts("not integral"); }

int main() {
    kind<int>(std::is_integral<int>{});         // is_integral<int> → 派生类到基类 true_type
    kind<double>(std::is_integral<double>{});
}
```

## 实现视角：trait 是编译器内建的薄包装

!!! impl "libc++ 的 `<type_traits>` 几乎全是内建函数"
    凡是需要知道"类的内部结构"的 trait——是否平凡、是否标准布局、是否有虚函数、能否构造——都**无法**用纯 C++ 模板实现（C++26 反射之前），只能由编译器提供。打开 libc++ 的 `__type_traits/` 目录可以看到：

    | trait | libc++ 实现 |
    |---|---|
    | `is_trivially_copyable` | `__is_trivially_copyable(_Tp)` |
    | `is_constructible` | `__is_constructible(_Tp, _Args...)` |
    | `is_convertible` | `__is_convertible(_T1, _T2)` |
    | `is_same` | `__is_same(_Tp, _Up)` |
    | `is_base_of` / `is_virtual_base_of` | `__is_base_of` / `__builtin_is_virtual_base_of` |
    | `is_implicit_lifetime` | `__builtin_is_implicit_lifetime` |
    | `has_unique_object_representations` | `__has_unique_object_representations` |
    | `reference_constructs_from_temporary` | `__reference_constructs_from_temporary` |
    | `decay` | `__decay(_Tp)` |
    | `underlying_type` | `__underlying_type(_Tp)` |
    | `common_type` | `__builtin_common_type<...>`（有则用之，否则退回纯模板实现）|
    | `make_integer_sequence` | `__make_integer_seq<...>` |

    连 `is_same`、`decay` 这种纯模板能写的 trait 也改用内建，原因是**编译速度**：内建不需要实例化任何类模板。libc++ 甚至在内部用 `_IsSame<T, U>`（= `_BoolConstant<__is_same(T, U)>`）代替 `is_same`，注释解释说这样实例化的类型更少。

## 陷阱

!!! pitfall "\"能编译\"不等于\"没问题\""
    第一层前置条件违反时 Clang 通常会报错，这让人误以为"编译器会兜底"。但 `is_convertible` 等少数 trait 会静默给出答案，而第二层（补全前后结果不同）完全无诊断。头文件里只前向声明了某个类、就对它的指针问 `is_convertible`/`is_base_of` 关系，是真实项目中出现过的 bug 模式。

!!! pitfall "不要为了\"修正\"结果去特化 trait"
    想让 `std::is_trivially_copyable<MyType>` 为真（例如为了让某容器走 `memcpy`），正确的做法是让 `MyType` **真的**平凡可复制（默认化特殊成员函数），或者使用库提供的定制点；直接特化是 UB，在 libc++ 下是硬错误。

## 思考题

!!! question "思考题 1"
    `std::is_same_v<std::true_type, std::integral_constant<bool, true>>` 与 `std::is_same_v<std::true_type, std::is_void<void>>` 分别是什么？

<details markdown="1">
<summary>展开查看答案与解析</summary>

前者为 `true`：`true_type` 就是 `bool_constant<true>` 即 `integral_constant<bool, true>` 的别名，是同一个类型（[meta.help]）。后者为 `false`：`is_void<void>` 只是**派生自**基特征 `true_type`（[meta.rqmts] ¶1），本身是另一个类。`is_void<void>::type` 才是 `true_type`。
</details>

!!! question "思考题 2"
    `struct S; static_assert(std::is_class_v<S>);` 是否属于 [meta.rqmts] ¶5 所说的 UB？`std::is_empty_v<S>` 呢？

<details markdown="1">
<summary>展开查看答案与解析</summary>

`is_class_v<S>` 没问题：`is_class` 没有完整性前置条件，且 `S` 补全后仍是类，结果不可能改变，¶5 的条件 (5.2) 不满足。`is_empty_v<S>` 则违反了 [meta.unary.prop] 表中"若 `T` 是非联合类类型，`T` 应为完整类型"的前置条件（第一层），是 UB；Clang 在此报错 "incomplete type 'S' used in type trait expression"。
</details>

## 小结

| 规则 | 要点 |
|---|---|
| 三种形状 | 一元/二元谓词派生自 `integral_constant` 基特征；变换 trait 提供 `type` |
| ¶4 不得特化 | 默认 UB；例外：`common_type`、`basic_common_reference`；`_v` 变量模板也不能特化；libc++ 直接报错 |
| ¶5 不完整类型 | 默认允许；但若补全后结果可能不同则 UB；再叠加各 trait 自己的完整性前置条件（违反亦 UB） |
| `integral_constant` | `value`、`value_type`、`type`（自身）、隐式转换、`operator()` |
| 实现 | 几乎全部是编译器内建，库只是薄包装 |
