---
title: 元编程与类型特征
summary: <type_traits> 的总则：trait 的三种形状与基特征，用户特化 trait 是未定义行为，不完整类型的两层规则，头文件概要，以及 integral_constant。
status: done
covers: type.traits.general, meta.rqmts, meta.type.synop, meta.help
papers: P3247R2
related: meta, meta.unary, meta.unary.prop, meta.rel, meta.trans, meta.logical, basic.types, namespace.std, structure.specifications, depr.meta.types
tags: 标准库, type_traits, 元编程, UB, 不完整类型
updated: 2026-10-19
---

!!! tldr
    - 谓词 trait（如 `is_integral<T>`）派生自 `true_type` 或 `false_type`，但本身是另一个类；变换 trait（如 `remove_cv<T>`）提供嵌套类型 `type`。
    - 除少数明确允许的例外（`common_type`、`basic_common_reference`），为 trait 添加特化是未定义行为；libc++ 直接把它变成编译错误。
    - trait 默认可以用不完整类型实例化，但如果类型补全后答案可能不同，程序就有未定义行为；很多 trait 还额外要求实参完整。
    - `integral_constant<T, v>` 是所有谓词 trait 的基础：`value`、`type`、隐式转换为值、`operator()`。

## trait 是什么

```cpp title="integral-constant.cpp" run ok
#include <cstdio>
#include <type_traits>

using five = std::integral_constant<int, 5>;
static_assert(five{} + five{} == 10);       // 隐式转换为 int
static_assert(std::is_integral<int>{}());   // operator()

template<class T> void kind(std::true_type)  { std::puts("integral"); }
template<class T> void kind(std::false_type) { std::puts("not integral"); }

int main() {
    kind<int>(std::is_integral<int>{});      // 派生类到基类 true_type 的转换
    kind<double>(std::is_integral<double>{});
}
```

**类型特征**（type trait）是在编译期回答关于类型的问题的类模板。`is_integral<int>` 的答案放在它的基类 `true_type` 里；把一个 `is_integral<T>` 对象传给分别接受 `true_type` 和 `false_type` 的重载，就能按类型选择实现，这种写法叫**标签分发**（tag dispatch）。

[type.traits.general] ¶1 把 trait 的用途概括为：让模板支持尽可能多的类型、优化模板代码（典型例子是对平凡可复制类型用 `memcpy`）、在编译期发现与类型有关的错误、做类型推断与变换。它也把 trait 分成三类：

- 类型分类：把所有 C++ 类型放进一个完整的分类体系，回答给定类型属于哪一格，见 [[meta.unary]]；
- 类型性质检查：检查单个类型或几个类型组合的性质，见 [[meta.unary.prop]]、[[meta.rel]]；
- 类型变换：修改类型的某些性质，见 [[meta.trans]]。

¶2 [type.traits] 中规定的所有函数都是信号安全的（[[support.signal]]），可以在信号处理函数里调用。这里的函数指 `is_constant_evaluated` 这类真正的函数，以及 `integral_constant` 的成员函数。

## 三种形状 [meta.rqmts]

标准用三组命名要求描述 trait 的接口：

| 要求 | 用途 | 形状 |
|---|---|---|
| ¶1 *Cpp17UnaryTypeTrait* | 一个类型的性质 | 一个类型实参（可以带辅助实参，如 `extent<T, I>`），派生自基特征 |
| ¶2 *Cpp17BinaryTypeTrait* | 两个类型的关系 | 两个类型实参（可以带辅助实参），派生自基特征 |
| ¶3 *Cpp17TransformationTrait* | 修改一个类型 | 一个类型实参（可以带辅助实参），有公开的嵌套类型 `type`，表示修改后的类型 |

**基特征**（[[g:base-characteristic]]，base characteristic）是一个 `integral_constant<T, v>` 的特化，`T` 和 `v` 由具体 trait 决定。`is_trivially_copyable<T>` 的基特征是 `true_type` 或 `false_type`，`rank<int[2][3]>` 的基特征是 `integral_constant<size_t, 2>`。

前两类 trait 必须可以默认构造和复制构造，所以 `std::is_integral<int>{}` 能写。它们必须公开且无歧义地派生自基特征，基特征的成员名不得被隐藏，所以 `::value`、`::type`、`::value_type` 总能访问到基特征的版本。

要求只说 trait 派生自基特征，没说 trait 就是基特征：

```cpp title="base-characteristic.cpp" run ok
#include <type_traits>

// trait 本身是另一个类
static_assert(!std::is_same_v<std::is_same<int, int>, std::true_type>);
// ::type 才是基特征
static_assert( std::is_same_v<std::is_same<int, int>::type, std::true_type>);
static_assert( std::is_base_of_v<std::true_type, std::is_same<int, int>>);

int main() {}
```

所以前面的标签分发靠的是派生类到基类的转换，而不是精确匹配。

[[meta.trans.other]] 中有几个变换 trait 在某些情况下没有 `type` 成员，例如 `enable_if<false>`、没有公共类型的 `common_type`、`underlying_type<int>`。在替换中访问不存在的 `type` 会让推导失败而不是报错，这就是它们能用于 SFINAE 的原因。

## 不得特化（¶4）

!!! std
    Unless otherwise specified, the behavior of a program that adds specializations for any of the templates specified in [type.traits] is undefined.

¶4 为 [type.traits] 中的任何模板添加特化，除非另有规定，都是未定义行为。

这比 [[namespace.std]] 的一般规则严格。一般情况下，用户可以为标准库类模板添加依赖于自己类型的特化（如 `std::hash<MyType>`），但 trait 不行。trait 的答案由核心语言规则决定，如果允许用户谎报，比如声称一个有虚函数的类是平凡可复制的，依赖它的库代码（`std::copy` 走 `memmove`）就会产生真正的 UB。

另有规定的例外只有两个，都在 [[meta.trans.other]]：

- `common_type<T1, T2>`：可以为退化后不变（`is_same_v<T, decay_t<T>>`）的类型特化，至少一个实参是程序定义的类型；
- `basic_common_reference<T, U, TQual, UQual>`：可以特化，用来影响 `common_reference` 的结果。

`is_integral_v` 这类变量模板同样不能特化。[[namespace.std]] 规定，除非明确允许，为标准库变量模板添加特化是未定义行为。

```cpp title="no-specialize.cpp" run error
#include <type_traits>

struct My {};
template<> struct std::is_trivially_copyable<My>  // error: libc++ 禁止
    : std::false_type {};
template<> inline constexpr bool
    std::is_integral_v<My> = true;                 // error: libc++ 禁止
template<> struct std::common_type<My, int> {
    using type = My;                               // OK：标准明确允许
};

int main() {}
```

标准只说这是 UB，不要求诊断。libc++ 用 Clang 的 `[[clang::no_specializations]]` 属性标注了几乎所有 trait，于是前两处特化得到 `'is_trivially_copyable' cannot be specialized` 错误。这个诊断属于默认即为错误的警告组 `-Winvalid-specialization`。

## 不完整类型（¶5）

不完整类型的规则有两层。

第一层是各个 trait 自己的前置条件。[[meta.unary.prop]]、[[meta.rel]]、[[meta.trans.other]] 的表格里，大多数 trait 都有一列 *Preconditions*，典型措辞是 `T` 必须是完整类型、*cv* `void` 或未知边界数组。违反库函数或库模板的前置条件是 UB（[[structure.specifications#3.4]]）。

第二层是 ¶5 的总括规则：

!!! std
    The behavior of a program is undefined if an instantiation of a template specified in [type.traits] directly or indirectly depends on an incompletely-defined object type `T`, and that instantiation could yield a different result were `T` hypothetically completed.

¶5 先规定，除非另有说明，可以用不完整类型实例化 [type.traits] 中的模板。这和 [[res.on.functions]] 的一般规则相反：一般情况下用不完整类型实例化库模板是 UB。所以 `is_class_v<S>`、`is_same_v<S, int>`、`add_pointer_t<S>` 对只声明未定义的 `S` 都没有问题，补全与否不影响答案。

随后 ¶5 又规定，如果实例化直接或间接依赖于一个不完全定义的对象类型（[[g:incompletely-defined-object-type]]，如只声明未定义的类），并且假如这个类型被补全，结果可能不同，那么行为未定义。

需要这条规则，是因为一个模板特化只实例化一次。第一次实例化时编译器用当时的信息算出答案，之后同一个特化在整个程序里都是这个答案。类型如果在中途补全，旧答案就错了：

```cpp title="incomplete-trait.cpp" run ub
#include <cstdio>
#include <type_traits>

struct Base {};
struct Derived;                       // 此时只声明、未定义

constexpr bool before =
    std::is_convertible_v<Derived*, Base*>;   // UB：结果依赖不完整类型

struct Derived : Base {};             // 现在完整了

constexpr bool after = std::is_convertible_v<Derived*, Base*>;

int main() {
    Derived d;
    Base* pb = &d;                    // 语言本身允许这个转换
    std::printf("before=%d after=%d real=%d\n", before, after, pb != nullptr);
}
```

本机 Clang 23 + libc++ 输出 `before=0 after=0 real=1`。变量模板特化 `is_convertible_v<Derived*, Base*>` 第一次使用时被实例化为 `false`，补全 `Derived` 之后再问，得到的还是同一个特化的 `false`。`Derived*` 本身是完整类型，第一层前置条件没有被违反，是 ¶5 让这段代码成为 UB。

!!! impl "编译器能查出多少"
    对第一层前置条件，Clang 的内建 trait 大多会报错：incomplete type 'S' used in type trait expression，`is_trivially_copyable`、`is_constructible`、`is_base_of`、`is_empty` 都是如此。但并非全部：本机测试中，对不完整类 `S`，`std::is_convertible_v<S, int>` 静默地得到 `false`，尽管它违反了前置条件。

    第二层是否补全后会变，编译器原则上无法检测，上面的例子没有任何诊断。

## 头文件概要 [meta.type.synop]

概要以 `// all freestanding` 开头，独立实现也要完整提供。按子条款分组：

| 分组 | 代表成员 | 页面 |
|---|---|---|
| 辅助类 | `integral_constant`、`bool_constant`、`true_type`、`false_type` | 见下文 [meta.help] |
| 主类型类别 | `is_void` … `is_function`、`is_reflection` | [[meta.unary]] |
| 复合类型类别 | `is_reference`、`is_arithmetic`、`is_object`、`is_scalar` … | [[meta.unary]] |
| 类型性质 | `is_const`、`is_aggregate`、`is_constructible` 系、`is_assignable` 系、`is_destructible` 系、`has_unique_object_representations` … | [[meta.unary.prop]] |
| 类型性质查询 | `alignment_of`、`rank`、`extent` | [[meta.unary]] |
| 类型关系 | `is_same`、`is_base_of`、`is_convertible`、`is_invocable` 系 … | [[meta.rel]] |
| 类型变换 | `remove_const`、`add_lvalue_reference`、`make_signed`、`decay`、`common_type`、`void_t` … | [[meta.trans]]、[[meta.trans.other]] |
| 逻辑组合 | `conjunction`、`disjunction`、`negation` | [[meta.logical]] |
| 成员关系 | `is_pointer_interconvertible_with_class`、`is_corresponding_member` | [[meta.member]] |
| 常量求值语境 | `is_constant_evaluated`、`is_within_lifetime` | [[meta.const.eval]] |

命名约定：

- 每个变换 trait `X` 都有别名模板 `X_t<T>`，等于 `X<T>::type`（C++14 起）。
- 每个谓词和查询 trait 都有变量模板 `X_v<...>`，等于 `X<...>::value`（C++17 起）。
- `void_t` 是唯一没有对应类模板的别名：`template<class...> using void_t = void;`。它的用处是让实参替换失败触发 SFINAE。
- 已弃用的 `is_trivial`、`is_pod`、`aligned_storage`、`aligned_union` 不在这份概要里，而在附录 D 的 [[depr.meta.types]]。`is_trivial` 是 C++26 弃用的（[[P3247R2]]）。libc++ 仍然提供它们，使用时给出 `-Wdeprecated-declarations` 警告。

## `integral_constant` [meta.help]

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

¶1 这几个类型用作基类，为各种 trait 定义统一的接口。设计上值得注意的几点：

- `type` 指向自己。所以取 `::type` 是幂等的，`is_same<A, B>::type` 正好就是基特征。
- 转换函数 `operator value_type()` 让对象可以隐式转换为它的值，`if (std::is_integral<T>{})` 和 `five{} + five{}` 都能写。
- `operator()()` 让 trait 对象可以当作无参可调用对象传递。
- `value` 是 `static constexpr` 数据成员，C++17 起隐式为 inline 变量，不需要类外定义。

## 实现：trait 是编译器内建函数的包装

需要知道类内部结构的 trait（是否平凡、是否标准布局、能否构造）在反射之前无法用纯 C++ 模板实现，只能由编译器提供。libc++ 的 `__type_traits/` 目录里，绝大多数 trait 直接转发给 Clang 内建函数：

| trait | libc++ 实现 |
|---|---|
| `is_trivially_copyable` | `__is_trivially_copyable(_Tp)` |
| `is_constructible` | `__is_constructible(_Tp, _Args...)` |
| `is_convertible` | `__is_convertible(_T1, _T2)` |
| `is_same` | `__is_same(_Tp, _Up)` |
| `decay` | `__decay(_Tp)` |
| `make_integer_sequence` | `__make_integer_seq<...>` |

`is_same`、`decay` 这类用纯模板也能写的 trait 同样改用内建，原因是编译速度：内建函数不需要实例化任何类模板。

## 常见错误

!!! pitfall "能编译不等于没问题"
    第一层前置条件被违反时 Clang 通常会报错，容易让人以为编译器会兜底。但 `is_convertible` 等少数 trait 会静默给出答案，第二层规则则完全没有诊断。在头文件里只前向声明了某个类，就对它的指针问 `is_convertible` 或 `is_base_of`，是实际项目里出现过的 bug。

!!! pitfall "不要为了修正结果去特化 trait"
    想让 `is_trivially_copyable<MyType>` 为真（比如让某个容器走 `memcpy`），正确的做法是让 `MyType` 真的平凡可复制，例如把特殊成员函数都默认化。直接特化是 UB，在 libc++ 下是编译错误。

## 思考题

!!! question "思考题 1"
    `std::is_same_v<std::true_type, std::integral_constant<bool, true>>` 和 `std::is_same_v<std::true_type, std::is_void<void>>` 分别是什么？

<details markdown="1">
<summary>答案</summary>

前者为 `true`：`true_type` 是 `bool_constant<true>`，也就是 `integral_constant<bool, true>` 的别名（[meta.help]）。后者为 `false`：`is_void<void>` 只是派生自基特征 `true_type`（[meta.rqmts] ¶1），本身是另一个类，`is_void<void>::type` 才是 `true_type`。
</details>

!!! question "思考题 2"
    `struct S; static_assert(std::is_class_v<S>);` 是否属于 [meta.rqmts] ¶5 所说的 UB？`std::is_empty_v<S>` 呢？

<details markdown="1">
<summary>答案</summary>

`is_class_v<S>` 没有问题：`is_class` 没有完整性前置条件，`S` 补全后仍然是类，结果不会变，¶5.2 的条件不满足。

`is_empty_v<S>` 违反了 [[meta.unary.prop]] 表中非联合类类型必须完整的前置条件，属于第一层，是 UB。Clang 在这里报错 incomplete type 'S' used in type trait expression。
</details>

## 小结

| 规则 | 要点 |
|---|---|
| 三种形状 | 谓词 trait 派生自 `integral_constant` 基特征；变换 trait 提供 `type` |
| ¶4 不得特化 | 默认 UB；例外是 `common_type` 和 `basic_common_reference`；`_v` 变量模板也不能特化 |
| ¶5 不完整类型 | 默认允许；补全后结果可能不同则 UB；各 trait 还有自己的完整性前置条件 |
| `integral_constant` | `value`、`value_type`、`type`（自身）、隐式转换、`operator()` |
