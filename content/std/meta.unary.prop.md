---
title: 类型性质
summary: 表 54 的全部类型性质谓词——cv 与类性质（is_empty、is_final、is_aggregate、is_structural、is_signed）、核心性质（平凡可复制、标准布局、隐式生存期）、is_constructible 以"假想变量定义"给出的精确定义及其 trivially/nothrow 变体、is_assignable/is_swappable/is_destructible、has_unique_object_representations、C++23 的 reference_constructs/converts_from_temporary；以及各自的前置条件
status: draft
covers: meta.unary.prop
papers: P0258R2, P2255R2, P2674R1, P3247R2
related: type.traits, meta.unary, meta.rel, basic.types, class.prop, dcl.init, dcl.init.aggr, class.temporary, expr.unary.noexcept, temp.deduct, declval, special
tags: 标准库, type_traits, is_constructible, 平凡, noexcept, UB
updated: 2026-10-18
---

[meta.unary.prop] 是 `<type_traits>` 里**最有"法律含量"**的一节。前面的类别谓词只是给类型贴标签，这里的谓词却在回答"**这个类型能不能这样用**"——能否用这些实参构造？构造会不会抛异常？是不是"什么都不做"？能否按字节比较？每一个答案都必须精确地落到核心语言的某条规则上，否则 `std::vector` 的扩容策略、`std::optional` 的平凡性、`std::atomic` 的要求就会出错。

先记住本节的**总体结构**：表 54 有三列——模板、条件（Condition）、前置条件（Preconditions）。条件决定 `value`；前置条件违反则是 UB（[[structure.specifications]]，以及 [[type.traits]] 讨论的不完整类型规则）。

## 四条总括规则（¶1–¶5）

**¶2：库可能自带特化。** 是否为这些模板定义全特化或偏特化是未指明的。也就是说你不能假设 `is_trivially_copyable<X>` 一定是主模板的实例——实现可能为某些类型（例如它自己的内部类型）提供特化。

**¶3：不得多余地实例化实参。** 若模板实参是类模板特化，只有当 `X` 的语义**要求**该实参是完整类型时，才可以隐式实例化它。所以 `is_class_v<std::vector<Incomplete>>`、`is_const_v<Box<T>>` 这种只看"外形"的查询不会触发 `Box<T>` 的实例化（实例化可能失败或引起副作用），而 `is_trivially_copyable_v<Box<T>>` 必然实例化它。

**¶4：`declval` 被视为平凡调用，且不是 odr-use。** 下文的定义大量使用 `declval<T>()`。如果不加这条，`is_trivially_constructible<T, T&&>` 中那个 `declval<T&&>()` 调用本身就是一个"非平凡操作"，所有 `is_trivially_*` 都会被它污染；而 `declval` 只有声明没有定义、在求值语境中使用是非良构的（[[declval]]），这条也一并豁免。

**¶5：`VAL<T>`。** 为了定义 `reference_*_from_temporary`，标准引入了说明用的表达式 *VAL*`<T>`：

- 若 `T` 是引用或函数类型，*VAL*`<T>` 与 `declval<T>()` 有相同的类型和值类别；
- 否则，*VAL*`<T>` 是一个**最初类型为 `T` 的纯右值**（若 `T` 有 cv 限定，按 [[expr.type]] 调整）。

为什么不直接用 `declval<T>()`？因为对非引用的 `T`，`declval<T>()` 返回 `T&&`，是一个 **xvalue**；用它初始化 `const T&` 会**直接绑定**到这个 xvalue，不会产生临时对象。而 `reference_constructs_from_temporary<const int&, int>` 想问的恰恰是"从一个 `int` **纯右值**初始化 `const int&` 会不会绑定到临时对象"——答案是会。*VAL* 正是为了得到"真正的纯右值"。

## 一、cv 与简单的类性质

| 谓词 | 条件 | 前置条件 |
|---|---|---|
| `is_const` / `is_volatile` | `T` 是 const / volatile 限定的（顶层，[[basic.type.qualifier]]）| — |
| `is_empty` | 非联合类，除零大小子对象外没有非静态数据成员，无虚函数、无虚基类、无非空基类 | 若是非联合类，须完整 |
| `is_polymorphic` | 多态类（[[class.virtual]]）| 同上 |
| `is_abstract` | 抽象类（[[class.abstract]]）| 同上 |
| `is_final` | 用 `final` 标记的类（含联合体）| 若是类，须完整 |
| `has_virtual_destructor` | 有虚析构函数（[[class.dtor]]）| 若是非联合类，须完整 |
| `is_aggregate` | 聚合类型（[[dcl.init.aggr]]）| 数组、完整类型或 *cv* `void` |
| `is_structural` | 结构化类型（[[temp.param]]，[[g:structural-type]]）| `remove_all_extents_t<T>` 完整或 *cv* `void` |
| `is_signed` | 若是算术类型，同 `T(-1) < T(0)`；否则 `false` | — |
| `is_unsigned` | 若是算术类型，同 `T(0) < T(-1)`；否则 `false` | — |
| `is_bounded_array` / `is_unbounded_array` | 已知 / 未知边界的数组 | — |
| `is_scoped_enum` | 有作用域枚举（[[dcl.enum]]）| — |

### `is_const`：只看顶层，数组看元素

¶6 的例子值得逐条品味：

```cpp
is_const_v<const volatile int>   // true
is_const_v<const int*>           // false：指针本身不是 const
is_const_v<const int&>           // false：引用不能被 cv 限定
is_const_v<int[3]>               // false
is_const_v<const int[3]>         // true：数组的 cv 就是元素的 cv（[basic.type.qualifier]）
```

`is_const_v<void() const>` 也是 `false`——函数类型上的 `const` 是**成员函数限定符**，不是类型的 cv 限定。

### `is_empty` 不是"`sizeof == 1`"

`is_empty` 的定义是**结构性**的：没有（非零大小的）数据成员、没有虚函数、没有虚基类、基类都空。它刻画的是"作为基类或 `[[no_unique_address]]` 成员时可以不占空间"，与 `sizeof` 无直接关系。C++20 的 `[[no_unique_address]]` 让"零大小子对象"进入了定义：

```cpp run title="is-empty.cpp" ok
#include <type_traits>

struct Empty {};
struct WithNUA { [[no_unique_address]] Empty e; };   // 唯一的成员是零大小子对象
struct D : Empty {};
struct Poly { virtual ~Poly(); };

static_assert(std::is_empty_v<WithNUA>);   // Clang 23：true，sizeof(WithNUA) == 1
static_assert(std::is_empty_v<D>);
static_assert(!std::is_empty_v<Poly>);    // 有 vptr
static_assert(!std::is_empty_v<int>);     // 不是类

int main() {}
```

### `is_final` 可以作用于联合体

¶8 的例子特意展示：`union U2 final {};` 合法，`is_final_v<U2>` 为真。`is_final` 的主要用途是在实现**空基类优化**（EBO）时判断能否从用户类型派生——`final` 类不能做基类，只能退回成员存储（或 `[[no_unique_address]]`）。

### `is_aggregate`：唯一允许未知边界数组的"类性质"

数组总是聚合（[[dcl.init.aggr]]），所以 `is_aggregate_v<int[]>` 合法且为真，这也是它的前置条件特意写成"数组类型、完整类型或 *cv* `void`"的原因。`is_aggregate` 在 C++17 加入，用来区分"能否用 `T{a, b}` 做聚合初始化"——在 C++20 允许用圆括号初始化聚合（`T(a, b)`）之后，它对实现 `std::make_from_tuple` 等工具仍然有用。

### `is_structural` 

结构化类型就是能做**常量模板形参**类型的类型（[[temp.param]]）。这个 trait 出现在当前草案中，与 C++26 反射一起使用（例如 `reflect_constant` 要求实参类型是结构化类型，见 [[meta.reflection.extract]]）。本地 libc++ 尚未提供 `std::is_structural`，Clang 23 也没有对应内建。

### `is_signed` / `is_unsigned`：用表达式定义

!!! std
    If `is_arithmetic_v<T>` is `true`, the same result as `T(-1) < T(0)`; otherwise, `false`.

    若 `is_arithmetic_v<T>` 为真，结果同 `T(-1) < T(0)`；否则为 `false`。

这个"用表达式定义"带来几个反直觉的结果：

- `is_unsigned_v<bool>` 为**真**：`bool(-1)` 是 `true`，`bool(0) < bool(-1)` 即 `false < true`；
- `is_signed_v<float>` 为**真**：浮点类型有负数；
- `is_signed_v<char>` 由实现决定——Apple arm64 上 `char` 是有符号的，为真；Linux AArch64 上通常为假；
- `is_signed_v<E>` 对任何枚举（即使底层类型是 `int`）都是**假**——枚举不是算术类型。要问枚举的符号性，写 `is_signed_v<underlying_type_t<E>>`。

```cpp run title="is-signed.cpp" ok
#include <type_traits>

enum E : int { e = -1 };

static_assert( std::is_unsigned_v<bool>);
static_assert( std::is_signed_v<float>);
static_assert(!std::is_signed_v<E> && !std::is_unsigned_v<E>);
static_assert( std::is_signed_v<std::underlying_type_t<E>>);

int main() {}
```

## 二、三大核心性质

| 谓词 | 条件 | 前置条件 |
|---|---|---|
| `is_trivially_copyable` | 平凡可复制类型（[[basic.types.general]]）| `remove_all_extents_t<T>` 完整或 *cv* `void` |
| `is_standard_layout` | 标准布局类型 | 同上 |
| `is_implicit_lifetime` {{c++23}} | 隐式生存期类型 | 数组、完整类型或 *cv* `void` |

这三个 trait 的语义完全由核心语言决定，详见 [[basic.types]] 与 [[class.prop]]。这里只补充 trait 视角下的几个要点：

- 它们都是**对象类型**的性质：`is_trivially_copyable_v<int&>`、`is_standard_layout_v<int&>` 都为假（引用不是对象类型）；cv 限定的标量类型是平凡可复制的（`is_trivially_copyable_v<const int>` 为真，尽管你不能给它赋值）。
- `is_implicit_lifetime_v<T[N]>` 与 `is_implicit_lifetime_v<T[]>` **对任何元素类型都为真**：[[basic.types.general]] 把数组类型无条件归为隐式生存期类型——创建数组对象本身不需要运行任何代码（元素的生存期另当别论）。于是 `is_implicit_lifetime_v<std::string[2]>` 为真，而 `is_implicit_lifetime_v<std::string>` 为假。
- `is_trivial`（"平凡可复制 + 平凡默认构造"）已在 C++26 移入附录 D（[[depr.meta.types]]，[[P3247R2]]），应改为分别询问 `is_trivially_copyable` 与 `is_trivially_default_constructible`。

```cpp run title="core-properties.cpp" ok
#include <string>
#include <type_traits>

struct Agg { int a; int b; };

static_assert(!std::is_trivially_copyable_v<int&>);
static_assert( std::is_trivially_copyable_v<const int>);
static_assert( std::is_implicit_lifetime_v<Agg>);
static_assert(!std::is_implicit_lifetime_v<std::string>);
static_assert( std::is_implicit_lifetime_v<std::string[2]>);   // 数组总是隐式生存期类型
static_assert( std::is_implicit_lifetime_v<int[]>);

int main() {}
```

## 三、`is_constructible`：一个假想的变量定义（¶9）

这是整个 `<type_traits>` 最重要的定义，`is_default/copy/move_constructible`、所有 `is_trivially_*constructible`、`is_nothrow_*constructible` 都建立在它之上。

!!! std
    The predicate condition for a template specialization `is_constructible<T, Args...>` shall be satisfied if and only if the following variable definition would be well-formed for some invented variable `t`: `T t(declval<Args>()...);`

    `is_constructible<T, Args...>` 的谓词条件成立，当且仅当对某个虚构变量 `t`，变量定义 `T t(declval<Args>()...);` 是良构的。

表 54 先排除两种情况：`T` 是函数类型或 *cv* `void` 时结果为 `false`。之后的每个细节都从"这是一个**直接初始化**的变量定义"推出：

| 推论 | 例子 | 结果 |
|---|---|---|
| 直接初始化：`explicit` 构造函数也算 | `struct Ex { explicit Ex(int); };` `is_constructible_v<Ex, int>` | `true`（但 `is_convertible_v<int, Ex>` 为 `false`）|
| C++20 起圆括号可以初始化聚合 | `is_constructible_v<Agg, int, int>`、`is_constructible_v<int[2], int, int>` | `true` |
| 引用的绑定规则（[[dcl.init.ref]]）| `is_constructible_v<int&, long&>` | `false`：非 const 左值引用不能绑定到转换出的临时量 |
| | `is_constructible_v<const int&, long>` | `true`：绑定到临时量 |
| | `is_constructible_v<int&&, int&>` | `false`：右值引用不能绑定到左值 |
| 零个实参 = 值初始化（注 7：从不解析为函数声明）| `is_constructible_v<int>`、`is_default_constructible_v<int[3]>` | `true` |
| 未知边界数组没有初始化器就不能定义变量 | `is_default_constructible_v<int[]>` | `false` |

注 7 专门堵住"最令人烦恼的解析"：`T t();` 在真实代码里是函数声明，但在这个假想定义里**从不**被解释为函数声明。

### "无关语境"的访问检查与"直接语境"

¶9 还规定了两件事，它们在 `is_assignable`、`is_convertible`、`invoke_result` 等定义中反复出现：

1. **访问检查如同在与 `T` 和 `Args` 都无关的语境中进行**。所以私有构造函数让结果为 `false`——即使你在 `T` 的成员函数或友元里询问 `is_constructible_v<T, int>`，答案也一样。trait 的结果不应依赖"在哪里问"，否则同一个特化在不同地方会有不同的值，违反 ODR。
2. **只考虑变量初始化的直接语境**（immediate context，与 [[temp.deduct.general]] 中的概念相同）。初始化可能引发类模板特化的实例化、函数模板特化的实例化、隐式定义函数的生成等副作用；**这些副作用不在直接语境中**，其中的错误会让程序非良构，而不是让 trait 返回 `false`（注 8）。

```cpp run title="immediate-context.cpp" ok
#include <type_traits>

struct Priv { private: Priv(int); };

struct Lazy {
    template<class T> Lazy(T t) { t.no_such_member(); }   // 函数体只在定义被实例化时检查
};

static_assert(!std::is_constructible_v<Priv, int>);   // 访问检查失败在直接语境中 → false
static_assert( std::is_constructible_v<Lazy, int>);   // 只看声明：构造函数模板可行 → true
// Lazy x(1);   // 真正构造时才实例化函数体 → 硬错误

int main() {}
```

`Lazy` 是 trait 与现实"说谎"的典型：构造函数模板**没有约束**，声明层面接受任何 `T`，于是 trait 回答 `true`；但真正调用时函数体实例化失败。这正是 C++20 概念要求"把需求写进约束"的原因——约束在直接语境中检查。

### 派生出的三个便捷 trait

| 谓词 | 定义 |
|---|---|
| `is_default_constructible<T>` | `is_constructible_v<T>` |
| `is_copy_constructible<T>` | 若 `T` 可引用（[[g:referenceable-type]]），同 `is_constructible_v<T, const T&>`；否则 `false` |
| `is_move_constructible<T>` | 若 `T` 可引用，同 `is_constructible_v<T, T&&>`；否则 `false` |

"可引用"排除了 `void` 和带 cv/引用限定的函数类型（你写不出 `const void&` 或 `void() const&`）。对引用类型 `T = int&`，`const T&` 按引用折叠就是 `int&`，所以 `is_copy_constructible_v<int&>` 为真。

!!! pitfall "“可移动构造”不等于“有移动构造函数”"
    `is_move_constructible_v<T>` 问的是 `T t(declval<T&&>())` 是否良构。一个只有拷贝构造函数（`T(const T&)`）、移动构造函数未声明的类，右值照样能绑定到 `const T&`，结果为真。反过来，移动构造函数被 `= delete` 显式删除时，重载决议选中被删除的函数，结果为假。

## 四、`is_assignable`、`is_swappable`、`is_destructible`

**`is_assignable<T, U>`**：表达式 `declval<T>() = declval<U>()` 作为不求值操作数是良构的；访问检查与直接语境的规则同上（注 3）。注意左边是 `declval<T>()`：

- `is_assignable_v<int, int>` 为**假**：`declval<int>()` 是 `int&&` 类型的 xvalue，内建赋值要求左操作数是可修改的左值；
- `is_assignable_v<int&, int>` 为真——所以 `is_copy_assignable<T>` 定义为 `is_assignable_v<T&, const T&>`，`is_move_assignable<T>` 为 `is_assignable_v<T&, T&&>`（`T` 须可引用）；
- 对类类型，`is_assignable_v<S, S>` 通常为**真**：对右值调用成员 `operator=` 是允许的，除非赋值运算符带 `&` 引用限定。

```cpp run title="is-assignable.cpp" ok
#include <type_traits>

struct S { int a; };
struct RQ { RQ& operator=(const RQ&) & = default; };   // 只能对左值赋值

static_assert(!std::is_assignable_v<int, int>);
static_assert( std::is_assignable_v<int&, int>);
static_assert( std::is_assignable_v<S, S>);            // 对类右值赋值是允许的
static_assert(!std::is_assignable_v<RQ, const RQ&>);
static_assert( std::is_copy_assignable_v<RQ>);

int main() {}
```

**`is_swappable_with<T, U>`**：`swap(declval<T>(), declval<U>())` 与 `swap(declval<U>(), declval<T>())` 都良构，且是在"可交换值的重载决议语境"（[[swappable.requirements]]）中——也就是同时考虑 `std::swap` 与 ADL 找到的 `swap`。`is_swappable<T>` = `is_swappable_with_v<T&, T&>`。`std::swap` 要求实参可移动构造、可移动赋值，所以移动构造被删除的类型 `is_swappable_v` 为假。

**`is_destructible<T>`**：定义相当别扭——要么 `T` 是引用类型，要么 `T` 是**完整对象类型**且 `declval<U&>().~U()` 良构（`U = remove_all_extents_t<T>`）。于是：

| `T` | `is_destructible_v<T>` | 原因 |
|---|---|---|
| `int&` | `true` | 引用类型直接为真 |
| `int[3]` | `true` | 看元素 |
| `int[]` | `false` | 不是完整对象类型 |
| `void`、`void()` | `false` | 不是对象类型 |
| 析构函数被删除或私有的类 | `false` | 伪析构表达式非良构 |

## 五、"平凡地"：`is_trivially_*`

!!! std
    `is_constructible_v<T, Args...>` is `true` and the variable definition for `is_constructible` ... is known to call no operation that is not trivial.

    `is_constructible_v<T, Args...>` 为真，并且 `is_constructible` 中的那个变量定义**已知不调用任何非平凡操作**。

"已知不调用任何非平凡操作"——关键在于"**那个变量定义实际会调用什么**"，而不是"这个类的某个特殊成员函数平凡不平凡"。几个推论：

1. **重载决议选中哪个函数，就看哪个函数**。类可以有平凡的拷贝构造函数，但 `Tmpl&` 实参可能选中一个更匹配的构造函数模板（非平凡）；
2. **默认成员初始化器使默认构造非平凡**；
3. **析构函数是否计入**？变量定义 `T t(...)` 意味着 `t` 最终要被销毁。Clang 的实现把析构也算进去：析构函数非平凡的类，`is_trivially_default_constructible` 为假——即使它的默认构造函数本身是平凡的。
4. 对标量类型，`is_trivially_constructible_v<int, long>` 为真（内建转换是平凡的）。

```cpp run title="trivially.cpp" ok
#include <type_traits>

struct DMI { int x = 0; };                 // 默认成员初始化器
static_assert( std::is_trivially_copyable_v<DMI>);
static_assert(!std::is_trivially_default_constructible_v<DMI>);

struct Tmpl {
    Tmpl() = default;
    Tmpl(const Tmpl&) = default;           // 平凡的拷贝构造函数
    template<class T> Tmpl(T&);            // 对非 const 左值更匹配
};
static_assert( std::is_trivially_copy_constructible_v<Tmpl>);      // 实参 const Tmpl& → 拷贝构造
static_assert(!std::is_trivially_constructible_v<Tmpl, Tmpl&>);    // 实参 Tmpl& → 模板，非平凡

struct NonTrivDtor { ~NonTrivDtor(); };
static_assert(!std::is_trivially_default_constructible_v<NonTrivDtor>);  // Clang：析构也算

struct MoveOnly {
    MoveOnly(MoveOnly&&) = default;
    MoveOnly& operator=(MoveOnly&&) = default;
};
static_assert( std::is_trivially_copyable_v<MoveOnly>);             // 有一个合格的平凡移动构造即可
static_assert(!std::is_trivially_copy_constructible_v<MoveOnly>);   // 但根本不可拷贝构造

static_assert( std::is_trivially_constructible_v<int, long>);

int main() {}
```

最后一组对照非常重要：**`is_trivially_copyable` 不等于 `is_trivially_copy_constructible && is_trivially_copy_assignable`**。前者是核心语言的类性质（[[class.prop]]：至少一个合格的复制/移动操作，且所有合格的都平凡、析构平凡），后者是"某个具体表达式是否平凡"。泛型库判断"能否 `memcpy`"应该用 `is_trivially_copyable`；判断"能否用 `memcpy` 来**实现拷贝构造**"则还需要类型可拷贝构造。

`is_trivially_destructible<T>`：`is_destructible_v<T>` 为真，且 `remove_all_extents_t<T>` 是非类类型或析构函数平凡的类类型。注意 `is_trivially_destructible_v<int&>` 为真（引用可析构，且是非类类型）。

## 六、"不抛异常地"：`is_nothrow_*`

`is_nothrow_constructible<T, Args...>`：`is_constructible_v` 为真，且那个变量定义**已知不抛出任何异常**（[[expr.unary.noexcept]]）。其余 `is_nothrow_*` 同理。它们是 `std::vector` 扩容时选择"移动还是拷贝"的依据（`std::move_if_noexcept`）：只有 `is_nothrow_move_constructible_v<T>` 为真（或不可拷贝）时才移动，以保证强异常安全。

!!! lawyer "析构函数算不算？"
    与平凡性一样，"变量定义"是否包括 `t` 的析构，标准措辞并没有直说，这是一个长期存在的 LWG 议题。Clang 的 `__is_nothrow_constructible` 选择**计入**析构函数：

    ```cpp run title="nothrow-dtor.cpp" ok
    #include <type_traits>

    struct ND { ~ND() noexcept(false); };

    static_assert( std::is_default_constructible_v<ND>);
    static_assert(!std::is_nothrow_default_constructible_v<ND>);   // Clang 23：析构可能抛 → false

    int main() {}
    ```

    析构函数默认就是 `noexcept` 的（[[except.spec]]），所以只有显式写 `noexcept(false)` 的类型才会撞上这个差别。

`is_nothrow_destructible<T>`：`is_destructible_v<T>` 为真且所指的析构函数已知不抛异常。`is_nothrow_swappable_with` 要求两个 `swap` 表达式都不抛。

## 七、`has_unique_object_representations`（¶10）

!!! std
    `T` is trivially copyable, and any two objects of type `T` with the same value have the same object representation.

    `T` 平凡可复制，并且任意两个**值相同**的 `T` 对象具有**相同的对象表示**。

这是"能否按字节哈希/比较"的判据：若为真，"值相等 ⇔ 字节相等"中的 ⇒ 方向成立，于是可以对对象表示（[[g:object-representation]]）直接做 `memcmp` 或哈希。C++17 加入（[[P0258R2]]），最初的动机正是 `std::hash` 的高效实现。

¶10 精确定义了类类型"值相同"的含义：数组或非联合类，逐个直接子对象值相同；联合体，活跃成员相同且该成员值相同。对标量类型，满足条件的集合是**由实现定义**的；注 9 给出提示：有填充位就不满足，否则整型满足。

| 类型 | Clang 23（arm64 macOS）| 原因 |
|---|---|---|
| `int`、`int*`、成员指针 | `true` | 无填充，值与表示一一对应 |
| `bool` | `true` | 只有 0/1 两种合法表示 |
| `float`、`double`、`long double` | `false` | `+0.0 == -0.0` 但表示不同；NaN |
| `struct { char c; int i; }` | `false` | 有填充字节 |
| `struct { int a, b; }` | `true` | 无填充 |
| 含位域 `int x : 3` 的类 | `false` | 位域外的位是填充 |
| 数组 | 同元素类型 | 表 54 的明确规定 |

注意"值相同 ⇒ 表示相同"只是单向的：浮点类型的 NaN 与自身"不相等"，但这并不是它被排除的原因——是 `+0.0`/`-0.0` 这对"值相等、表示不同"的反例让它被排除。

## 八、绑定到临时对象：`reference_constructs_from_temporary` / `reference_converts_from_temporary` {{c++23}}

| 谓词 | 条件 |
|---|---|
| `reference_constructs_from_temporary<T, U>` | `T` 是引用类型，且 `T t(VAL<U>);` 良构并把 `t` 绑定到一个生存期被延长的临时对象 |
| `reference_converts_from_temporary<T, U>` | 同上，但初始化是 `T t = VAL<U>;`（复制初始化）|

两者的差别就是直接初始化与复制初始化：`explicit` 转换函数只在前者中可用。

```cpp run title="ref-from-temp.cpp" ok
#include <string>
#include <type_traits>

struct X { explicit operator int() const; };

static_assert( std::reference_constructs_from_temporary_v<const int&, long>);   // long → int 临时量
static_assert( std::reference_constructs_from_temporary_v<const int&, int>);    // VAL<int> 是纯右值 → 物化临时量
static_assert(!std::reference_constructs_from_temporary_v<const int&, int&>);   // 直接绑定左值
static_assert( std::reference_constructs_from_temporary_v<int&&, int>);
static_assert( std::reference_constructs_from_temporary_v<const std::string&, const char*>);
static_assert(!std::reference_constructs_from_temporary_v<int, int>);           // T 不是引用

static_assert( std::reference_constructs_from_temporary_v<const int&, X>);      // 直接初始化可用 explicit
static_assert(!std::reference_converts_from_temporary_v<const int&, X>);        // 复制初始化不可用

int main() {}
```

这对 trait 来自 [[P2255R2]]，目标是在**编译期**拦住一类悬垂引用：

- `std::pair<const std::string&, int> p("x", 1);` 中，`first` 会绑定到一个在构造函数结束时就销毁的临时 `std::string`。C++23 起，[[pairs.pair]] 规定若 `reference_constructs_from_temporary_v<first_type, U1&&>` 为真，相应构造函数**定义为弃置**；`tuple` 同理。
- [[func.require]] ¶2 规定：若 `reference_converts_from_temporary_v<R, decltype(INVOKE(...))>` 为真，*INVOKE*`<R>` 非良构——于是 `std::function<const int&()> f = []{ return 42; };` 这种必然悬垂的写法不再能编译，`is_invocable_r_v<const long&, int(*)()>` 也应为假。

!!! impl "libc++ 的落实程度"
    本地 Clang 23 + libc++ 中，`pair`/`tuple` 对上述情况用 `static_assert` 报错（"reference member 'first' binds to a temporary object…"），而不是把构造函数定义为弃置——因此 `is_constructible_v<std::pair<const std::string&, int>, const char*, int>` 仍然为**真**，与标准的"弃置"语义不符。另外 `std::is_invocable_r_v<const long&, int(*)()>` 在 libc++ 中也为**真**，即 *INVOKE*`<R>` 的这条新规则在 trait 层面尚未落实。

## 实现视角

!!! impl "全部是内建"
    libc++ 中本节的 trait 几乎全部直接转发给 Clang 内建：`__is_constructible`、`__is_trivially_constructible`、`__is_nothrow_constructible`、`__is_assignable`、`__is_trivially_copyable`、`__is_standard_layout`、`__builtin_is_implicit_lifetime`、`__has_unique_object_representations`、`__reference_constructs_from_temporary` 等。例如：

    ```cpp
    template <class _Tp, class... _Args>
    struct _LIBCPP_NO_SPECIALIZATIONS is_constructible
        : integral_constant<bool, __is_constructible(_Tp, _Args...)> {};

    template <class _Tp>
    struct _LIBCPP_NO_SPECIALIZATIONS is_copy_constructible
        : integral_constant<bool, __is_constructible(_Tp, __add_lvalue_reference_t<const _Tp>)> {};
    ```

    `is_copy_constructible` 用 `__add_lvalue_reference_t<const _Tp>` 而不是直接写 `const _Tp&`，正是为了处理"不可引用类型"——对 `void` 它得到 `const void`，`__is_constructible(void, const void)` 为假，与标准"否则为 `false`"一致。

    编译器内部，`__is_constructible` 等就是**真的在语义分析器里构造那个假想的变量定义**，在一个 SFINAE 陷阱（不报错，只记录失败）中检查它——标准措辞与实现是一一对应的。

## 陷阱

!!! pitfall "不受约束的转换构造函数会让 trait 说谎"
    `template<class T> Wrapper(T&&)` 这类无约束的完美转发构造函数，会让 `is_constructible_v<Wrapper, 任何东西>`、`is_convertible_v<任何东西, Wrapper>` 都为真，进而污染 `std::variant`、`std::optional` 等依赖这些 trait 的重载决议。务必用 `requires` 或 `enable_if` 约束它。

!!! pitfall "`is_trivially_copyable` 为真不代表可以拷贝"
    `MoveOnly` 例子说明，平凡可复制的类型可以根本不可拷贝构造。依据 `is_trivially_copyable` 走 `memcpy` 路径的库代码，实际上做的是"按字节复制对象表示"，这在语言层面对平凡可复制类型总是合法的（[[basic.types.general]] ¶2–¶3），即便类型的作者删除了拷贝构造函数——这有时违背作者的意图。

!!! ub "违反前置条件"
    表 54 几乎每行都有"须为完整类型、*cv* `void` 或未知边界数组"之类的前置条件。对不完整的类类型问 `is_constructible`、`is_trivially_copyable`、`is_nothrow_move_constructible` 等是 UB——Clang 大多会报错，但不要依赖。

## 思考题

!!! question "思考题 1"
    `struct A { A(int) noexcept; ~A(); };` 中，`is_nothrow_constructible_v<A, int>` 与 `is_trivially_constructible_v<A, int>` 各是什么？

<details markdown="1">
<summary>展开查看答案与解析</summary>

`~A()` 没有显式异常说明，按 [[except.spec]] 析构函数隐式为 `noexcept`，所以 `is_nothrow_constructible_v<A, int>` 为真（构造函数 `noexcept`，析构也不抛）。`is_trivially_constructible_v<A, int>` 为假：被调用的 `A(int)` 是用户提供的构造函数，不是平凡操作（何况析构函数也是用户提供的、非平凡的）。
</details>

!!! question "思考题 2"
    为什么 `reference_constructs_from_temporary` 要用 *VAL*`<U>` 而不是 `declval<U>()`？举一个两者给出不同答案的例子。

<details markdown="1">
<summary>展开查看答案与解析</summary>

`declval<int>()` 的类型是 `int&&`，是 xvalue；`const int& t(declval<int>());` 直接绑定到这个 xvalue，不创建临时对象。若用它定义，`reference_constructs_from_temporary_v<const int&, int>` 会是假。但该 trait 想问的是"拿一个 `int` 纯右值去初始化"，那会经过临时量实质化转换（[[conv.rval]]）创建临时对象并延长其生存期，应为真。*VAL*`<int>` 是真正的纯右值，给出正确答案 `true`（[meta.unary.prop] ¶5.2）。
</details>

!!! question "思考题 3"
    `is_unsigned_v<bool>` 为什么是 `true`？`is_signed_v<char8_t>` 呢？

<details markdown="1">
<summary>展开查看答案与解析</summary>

`bool` 是算术类型，按表 54 计算 `bool(0) < bool(-1)`：`bool(-1)` 是 `true`，`false < true` 为真。`char8_t` 的底层类型是 `unsigned char`（[[basic.fundamental]]），`char8_t(-1)` 为 255，`char8_t(-1) < char8_t(0)` 为假，所以 `is_signed_v<char8_t>` 为假、`is_unsigned_v<char8_t>` 为真。
</details>

## 小结

| 家族 | 定义的"锚点" | 要点 |
|---|---|---|
| `is_constructible` 系 | `T t(declval<Args>()...);` 是否良构 | 直接初始化；无关语境访问检查；只看直接语境；函数/`void` 为假 |
| `is_assignable` 系 | `declval<T>() = declval<U>()` | 左边常需写成 `T&` |
| `is_trivially_*` | 上述表达式"已知不调用非平凡操作" | 看实际选中的函数；Clang 计入析构 |
| `is_nothrow_*` | 上述表达式"已知不抛异常" | `move_if_noexcept` 的依据；Clang 计入析构 |
| 三大核心性质 | [[basic.types]]、[[class.prop]] | 数组总是隐式生存期类型 |
| `has_unique_object_representations` | 值同 ⇒ 表示同 | 浮点与有填充的类为假 |
| `reference_*_from_temporary` | 用纯右值 *VAL*`<U>` 初始化引用是否绑定临时量 | C++23；用于 `pair`/`tuple`/*INVOKE*`<R>` 防悬垂 |
