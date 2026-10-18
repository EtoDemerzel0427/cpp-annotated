---
title: 类型间关系
summary: 二元类型关系谓词——is_same、is_base_of（不问访问与歧义）与 C++26 的 is_virtual_base_of、以假想 return 语句定义的 is_convertible、布局兼容与指针可互换、基于 INVOKE 的 is_invocable 系列与当前草案新增的 is_applicable；以及每个谓词的前置条件
status: draft
covers: meta.rel
papers: P0466R5, P2255R2
related: type.traits, meta.unary.prop, meta.trans.other, meta.member, class.derived, class.mi, basic.types, basic.compound, stmt.return, func.require, conv
tags: 标准库, type_traits, is_convertible, is_base_of, invoke
updated: 2026-10-18
---

[meta.rel] 回答"**两个类型之间是什么关系**"：是不是同一个类型？一个是不是另一个的基类？能不能隐式转换？能不能把一个当作函数、另一组当作实参去调用？

¶1–¶2：表 56 的每个模板都是 *Cpp17BinaryTypeTrait*（[[type.traits]]），条件为真时基特征为 `true_type`，否则为 `false_type`。¶4 与 [[meta.unary.prop]] ¶4 相同：定义中出现的 `declval<T>()` 被视为平凡调用，且不构成 odr-use。

## 总览

| 分组 | 谓词 | 条件（概要）| 前置条件 |
|---|---|---|---|
| 同一性 | `is_same<T, U>` | 同一类型，cv 也相同 | — |
| 继承 | `is_base_of<Base, Derived>` | `Base` 是 `Derived` 的基类（忽略 cv），或两者是同一个非联合类 | 若两者是不同的非联合类，`Derived` 须完整 |
| | `is_virtual_base_of<Base, Derived>` {{c++26}} | `Base` 是 `Derived` 的虚基类（忽略 cv）| 若两者都是非联合类，`Derived` 须完整 |
| | `is_pointer_interconvertible_base_of<Base, Derived>` {{c++20}} | `Derived` 无歧义地派生自 `Base` 且每个 `Derived` 对象与其 `Base` 子对象指针可互换，或两者是同一个非联合类 | 同 `is_base_of` |
| 转换 | `is_convertible<From, To>` | 见下文 ¶6 | 完整、*cv* `void` 或未知边界数组 |
| | `is_nothrow_convertible<From, To>` {{c++20}} | 可转换且转换已知不抛异常 | 同上 |
| 布局 | `is_layout_compatible<T, U>` {{c++20}} | 布局兼容（[[basic.types.general]]）| 同上 |
| 调用 | `is_invocable<Fn, Args...>` | *INVOKE*`(declval<Fn>(), declval<Args>()...)` 良构 | 同上 |
| | `is_invocable_r<R, Fn, Args...>` | *INVOKE*`<R>(...)` 良构 | 同上 |
| | `is_nothrow_invocable(_r)` | 上述且已知不抛异常 | 同上 |
| | `is_applicable<Fn, Tuple>` / `is_nothrow_applicable` | `Tuple` 是 *tuple-like*，且 *INVOKE*`(declval<Fn>(), ELEMS-OF(Tuple)...)` 良构 | `Fn`、`Tuple` 完整、*cv* `void` 或未知边界数组 |

## `is_same`：最严格的同一性

"`T` 和 `U` 命名同一类型且 cv 限定相同"。几个容易误判的点：

- 别名不产生新类型：`is_same_v<int, signed>`、`is_same_v<std::size_t, unsigned long>`（LP64 平台）为真；
- 同宽不等于同类型：`long` 与 `long long` 在 LP64 上都是 64 位，但 `is_same_v<long, long long>` 为假；`char`、`signed char`、`unsigned char` 是**三个**不同类型（[[basic.fundamental]]）；
- cv 有区别：`is_same_v<int, const int>` 为假——需要忽略 cv 时先 `remove_cv_t`。

它是 libc++ 中最常用的 trait 之一，实现为内建 `__is_same(_Tp, _Up)`。

## `is_base_of`：只问"是不是基类"，不问"能不能转换"

¶5 的例子精确划出了边界：

```cpp run title="is-base-of.cpp" ok
#include <type_traits>

struct B {};
struct B1 : B {};
struct B2 : B {};
struct D : private B1, private B2 {};

static_assert( std::is_base_of_v<B, D>);          // 私有、且有歧义——仍然是基类
static_assert( std::is_base_of_v<const B, D>);    // 忽略 cv
static_assert( std::is_base_of_v<B, const B>);    // 同一个类也算
static_assert(!std::is_base_of_v<D, B>);
static_assert(!std::is_base_of_v<B&, D&>);        // 引用不是类
static_assert(!std::is_base_of_v<B[3], D[3]>);
static_assert(!std::is_base_of_v<int, int>);      // 非类类型：即使相同也为 false

static_assert(!std::is_convertible_v<D*, B*>);    // 但指针转换不可行（私有 + 歧义）

int main() {}
```

注 1：私有、受保护或有歧义的基类**仍然是**基类。这是 `is_base_of` 与 `is_convertible<Derived*, Base*>` 的本质区别：后者还要求基类**可访问且无歧义**（[[conv.ptr]]）。泛型代码想表达"能把 `Derived*` 当 `Base*` 用"时应选后者（或 C++20 的 `std::derived_from` 概念，它同时检查两者）。

"同一个类也算"这一规则只对**非联合**类成立：联合体既不能做基类也不能被派生，`is_base_of_v<U, U>` 为假。

### `is_virtual_base_of` {{c++26}}

`Base` 是 `Derived` 的**虚基类**（直接或间接，[[class.mi]]），忽略 cv。注 2：私有、受保护或有歧义的虚基类仍算；注 3：类永远不是自己的虚基类。

```cpp run title="is-virtual-base-of.cpp" ok
#include <type_traits>

struct V {};
struct M1 : virtual V {};
struct M2 : virtual V {};
struct MM : M1, M2 {};
struct B {};
struct N : B {};

static_assert( std::is_virtual_base_of_v<V, M1>);
static_assert( std::is_virtual_base_of_v<V, MM>);   // 间接虚基类
static_assert(!std::is_virtual_base_of_v<B, N>);    // 普通基类
static_assert(!std::is_virtual_base_of_v<V, V>);    // 注 3

int main() {}
```

它的实际用途是判断"从 `Base*` 到 `Derived*` 能否 `static_cast`"——虚基类不能静态下转换（[[expr.static.cast]]）——以及判断成员指针转换、对象布局是否在编译期可知。libc++ 在 `__builtin_is_virtual_base_of` 可用时提供它。

## `is_convertible`：一个假想的 `return` 语句（¶6）

!!! std
    The predicate condition for a template specialization `is_convertible<From, To>` shall be satisfied if and only if the return statement in the following code would be well-formed, including any implicit conversions to the return type of the function: `To test() { return declval<From>(); }`

    `is_convertible<From, To>` 的谓词条件成立，当且仅当下面代码中的 `return` 语句良构（包括到返回类型的所有隐式转换）：`To test() { return declval<From>(); }`

为什么用 `return` 而不是 `To t = declval<From>();`？注 4 给出答案：**这样对引用类型、数组类型、函数类型和 *cv* `void` 都能给出定义良好的结果**。逐一推演：

| `From → To` | 结果 | 推理 |
|---|---|---|
| `void → void` | `true` | `void` 函数可以 `return` 一个 `void` 表达式（[[stmt.return]]）|
| `int → void` / `void → int` | `false` | 返回类型与表达式不匹配 |
| `int → int[1]`、`int() → int()` | `false` | 函数不能返回数组或函数 |
| `int() → int(&)()`、`int() → int(*)()` | `true` | `declval<int()>()` 是函数左值，可绑定引用或退化为指针 |
| `int[3] → int*` | `true` | `declval<int[3]>()` 是数组 xvalue，可退化 |
| `int → Ex`（`explicit Ex(int)`）| `false` | `return` 是**复制初始化**，`explicit` 不可用 |

同样，访问检查在与两者无关的语境中进行，且只看 `return` 操作数（包括返回对象的初始化）的直接语境（注 5）。

!!! lawyer "`is_convertible_v<T, T>` 可能为假"
    `declval<From>()` 返回的是 `From&&`——一个 **xvalue**，不是纯右值。所以 C++17 的保证复制消除（[[class.copy.elision]]）帮不上忙：`return declval<NM>();` 需要从 xvalue 移动构造返回对象。

    ```cpp run title="convertible-self.cpp" ok
    #include <type_traits>

    struct NM { NM() = default; NM(NM&&) = delete; };

    NM make() { return NM(); }                   // OK：纯右值，保证消除，不需要移动构造
    static_assert(!std::is_convertible_v<NM, NM>);   // 但 trait 说"不可转换"

    int main() {}
    ```

    这不是缺陷：`is_convertible` 问的是"一个 `From` 类型的**表达式**（以 `declval` 的方式给出）能否隐式转换为 `To`"，而不是"一个纯右值能否初始化 `To`"。不可移动的类型确实不能从 xvalue "转换"为自身。

`is_convertible` 与 `is_constructible` 的根本差异就是**复制初始化 vs 直接初始化**：前者不考虑 `explicit` 构造函数和 `explicit` 转换函数。`std::pair`、`std::tuple`、`std::optional` 等用 `explicit(!is_convertible_v<U, T>)` 让自身的转换构造函数"有条件地 explicit"——仅当元素本身是隐式可转换时，包装类型才隐式可转换。

`is_nothrow_convertible` {{c++20}}：可转换，且该转换（按 `is_convertible` 的定义）已知不抛异常。

## 布局兼容与指针可互换 {{c++20}}

这两个 trait 来自 [[P0466R5]]，把核心语言中 [[basic.types.general]] 的**布局兼容类型**（[[g:layout-compatible-types]]）与 [[basic.compound]] 的**指针可互换**（[[g:pointer-interconvertible]]）概念暴露给库。同一提案还加入了 [[meta.member]] 中的两个函数。

- `is_layout_compatible<T, U>`：`T` 与 `U` 布局兼容。对标准布局类，这意味着它们的**公共初始序列**（[[g:common-initial-sequence]]）覆盖了全部成员；对枚举，意味着底层类型相同（[[dcl.enum]]）；cv 被忽略。
- `is_pointer_interconvertible_base_of<Base, Derived>`：`Derived` 无歧义地派生自 `Base`（忽略 cv），并且**每个** `Derived` 对象都与它的 `Base` 子对象指针可互换——按 [[basic.compound]]，这要求 `Derived` 是标准布局类且 `Base` 是它的（首个）基类子对象；或者两者是同一个非联合类。

!!! impl "libc++ 未提供，但 Clang 有内建"
    本地 libc++ 尚未提供 `std::is_layout_compatible` 与 `std::is_pointer_interconvertible_base_of`（也没有定义 `__cpp_lib_is_layout_compatible`、`__cpp_lib_is_pointer_interconvertible`），但 Clang 23 提供了它们背后的内建，可以直接验证语义：

    ```cpp run title="layout-builtins.cpp" ok
    struct A { int a; };
    struct B { int b; };
    struct C : A, B {};                  // 成员分散在两个基类中：不是标准布局
    struct D : A {};                     // 标准布局，A 是首个基类子对象

    struct P { int x; char y; };
    struct Q { const int u; char v; };   // cv 不影响布局兼容
    struct R { int x; char y; char z; };
    enum class E1 : int {};
    enum class E2 : int {};

    static_assert( __is_layout_compatible(P, Q));
    static_assert(!__is_layout_compatible(P, R));
    static_assert( __is_layout_compatible(E1, E2));       // 底层类型相同的枚举
    static_assert(!__is_layout_compatible(E1, int));
    static_assert( __is_pointer_interconvertible_base_of(A, D));
    static_assert(!__is_pointer_interconvertible_base_of(A, C));   // C 不是标准布局
    static_assert( __is_pointer_interconvertible_base_of(A, A));   // 同一个类

    int main() {}
    ```

    其他标准库实现（如 GCC 的 libstdc++）提供了 `std::` 版本，可以在 Compiler Explorer 上对照。

## 调用：`is_invocable` 系列

`is_invocable<Fn, ArgTypes...>`：*INVOKE*`(declval<Fn>(), declval<ArgTypes>()...)` 作为不求值操作数良构。*INVOKE* 由 [[func.require]] ¶1 定义，统一了五种"调用"：

1. 普通函数调用 `f(args...)`；
2. 成员函数指针 + 对象（`(t1.*f)(args...)`）、+ `reference_wrapper`（`(t1.get().*f)(...)`）、+ 指针或类指针（`((*t1).*f)(...)`）；
3. 数据成员指针 + 对象/`reference_wrapper`/指针，结果是成员的引用。

```cpp run title="is-invocable.cpp" ok
#include <functional>
#include <memory>
#include <type_traits>

struct S { int m; int f(int) const; };
using PMF = int (S::*)(int) const;

static_assert( std::is_invocable_v<PMF, const S&, int>);
static_assert( std::is_invocable_v<PMF, S*, long>);                          // long → int
static_assert( std::is_invocable_v<PMF, std::reference_wrapper<S>, int>);
static_assert( std::is_invocable_v<PMF, std::unique_ptr<S>&, int>);         // 类指针：*t1
static_assert(!std::is_invocable_v<PMF, S*>);                                // 缺实参
static_assert( std::is_invocable_r_v<long, int S::*, S&>);                  // 数据成员指针也"可调用"
static_assert( std::is_invocable_r_v<void, int (*)()>);                     // R 为 void：丢弃结果

int main() {}
```

`is_invocable_r<R, Fn, ArgTypes...>` 用 *INVOKE*`<R>`：若 `R` 是 *cv* `void`，结果被 `static_cast<void>` 丢弃；否则结果须**隐式转换**为 `R`。C++23 起（[[P2255R2]]）还有一条：若 `reference_converts_from_temporary_v<R, decltype(INVOKE(...))>` 为真，*INVOKE*`<R>` 非良构——"调用结果绑定到返回类型引用时会悬垂"直接判为不可调用。按此，`is_invocable_r_v<const long&, int(*)()>` 应为假。

!!! impl "libc++ 尚未落实 *INVOKE*`<R>` 的悬垂检查"
    本地 Clang 23 + libc++ 中 `std::is_invocable_r_v<const long&, int(*)()>` 为 `true`，与当前草案不符。

`is_nothrow_invocable(_r)`：额外要求表达式已知不抛异常。注意对普通函数指针类型，`noexcept` 是函数类型的一部分（C++17），`void(*)() noexcept` 才能让 `is_nothrow_invocable` 为真。

### `is_applicable`

当前草案新增了 `is_applicable<Fn, Tuple>` 与 `is_nothrow_applicable`，配合 [[meta.trans.other]] 的 `apply_result`，对应 `std::apply` 的"能否调用 / 结果类型"。¶3 为此定义了说明用的 *ELEMS-OF*`(T)`：

!!! std
    Let *ELEMS-OF*(T) be the parameter pack `get<N>(declval<T>())`, where *N* is the pack of `size_t` template arguments of the specialization of `index_sequence` denoted by `make_index_sequence<tuple_size_v<remove_reference_t<T>>>`.

    令 *ELEMS-OF*(T) 为形参包 `get<N>(declval<T>())`，其中 *N* 是 `make_index_sequence<tuple_size_v<remove_reference_t<T>>>` 所表示的 `index_sequence` 特化的 `size_t` 模板实参包。

也就是"把 tuple 按 `get<0>`、`get<1>`…… 展开成实参包"，正是 [[intseq]] 的经典用法。条件中额外要求 *tuple-like*`<Tuple>`（[[tuple.like]]），所以对非 tuple-like 类型它是 `false` 而不是硬错误。本地 libc++ 尚未提供这两个 trait。

## 陷阱

!!! pitfall "用 `is_base_of` 代替 `is_convertible<D*, B*>`"
    `is_base_of` 对私有基类、歧义基类都为真，但 `static_cast<B*>(d)` 或隐式转换会失败。如果你的模板随后要做指针转换，约束应该写 `is_convertible_v<D*, B*>`（或 `std::derived_from<D, B>`）。

!!! pitfall "`is_convertible` 的参数顺序"
    是 `is_convertible<From, To>`——"从"在前；`is_base_of<Base, Derived>`——"基"在前；`is_assignable<T, U>`——"目标"在前。三者方向不一致，是常见笔误来源。C++20 的概念 `std::convertible_to<From, To>`、`std::derived_from<Derived, Base>` 又换了一个方向（派生在前）。

!!! ub "不完整类型"
    `is_convertible<Incomplete, int>` 违反前置条件。在本地测试中 Clang **不会**诊断，静默给出 `false`；而 [[type.traits]] 中演示过，对 `Incomplete*` 问转换关系即使不违反前置条件，也可能因 [meta.rqmts] ¶5 而成为 UB。

## 思考题

!!! question "思考题 1"
    `struct A {}; struct B : A {};` 中 `is_convertible_v<B, A>`、`is_convertible_v<A, B>`、`is_convertible_v<B&, A&>`、`is_convertible_v<B[2], A*>` 分别是什么？

<details markdown="1">
<summary>展开查看答案与解析</summary>

依次为 `true`、`false`、`true`、`true`（本地 Clang 23 验证）：

- `B → A`：`return declval<B>();` 用 `B` 的 xvalue 复制初始化 `A`，选中 `A` 的隐式移动构造函数（形参 `A&&` 可绑定到派生类对象），即"切片"；
- `A → B`：基类到派生类没有隐式转换；
- `B& → A&`：派生到基类的引用绑定；
- `B[2] → A*`：`declval<B[2]>()` 是数组 xvalue，先做数组到指针转换得到 `B*`，再做派生到基类的指针转换——两者可以组成一个标准转换序列（[[over.ics.scs]]）。

最后一个是"能转换"不等于"能安全使用"的好例子：通过这个 `A*` 做指针算术去访问第二个元素是 UB，因为指针算术要求指向类型与数组元素类型相似（[[expr.add]]）。
</details>

!!! question "思考题 2"
    `is_invocable_v<int (S::*)(), S>` 与 `is_invocable_v<int (S::*)() &, S>` 有何不同？

<details markdown="1">
<summary>展开查看答案与解析</summary>

`declval<S>()` 是 `S` 类型的 xvalue。前者调用无引用限定的成员函数，xvalue 对象表达式可以调用，结果为真。后者成员函数带 `&` 限定，只能在左值对象上调用（[[over.match.funcs]]），对 xvalue 不可行，结果为假；若改成 `is_invocable_v<int (S::*)() &, S&>` 则为真。
</details>

## 小结

| 谓词 | 一句话 |
|---|---|
| `is_same` | 精确同一，cv 敏感；别名不产生新类型 |
| `is_base_of` | 基类关系（含私有/歧义）或同一非联合类；不检查可转换性 |
| `is_virtual_base_of` | C++26；虚基类关系，类不是自己的虚基类 |
| `is_convertible` | `To test() { return declval<From>(); }` 良构；复制初始化；`From` 是 xvalue |
| `is_layout_compatible` / `is_pointer_interconvertible_base_of` | C++20；libc++ 未提供，Clang 有内建 |
| `is_invocable(_r)` | 基于 *INVOKE*；`_r` 版 C++23 起拒绝悬垂引用（libc++ 未落实）|
| `is_applicable` | 当前草案新增；按 *ELEMS-OF* 展开 tuple-like |
