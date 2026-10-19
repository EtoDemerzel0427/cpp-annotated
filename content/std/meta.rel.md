---
title: 类型间关系
summary: 判断两个类型之间关系的谓词：是否同一类型、是否基类、能否隐式转换、能否调用、是否布局兼容。
status: draft
covers: meta.rel
papers: P0466R5, P2255R2
related: type.traits, meta.unary.prop, meta.trans.other, meta.member, class.derived, class.mi, basic.types, basic.compound, stmt.return, func.require, conv
tags: 标准库, type_traits, is_convertible, is_base_of, invoke
updated: 2026-10-19
---

!!! tldr
    - `is_same` 要求类型完全相同，cv 限定也算在内；类型别名不产生新类型。
    - `is_base_of` 只问继承关系，私有或有歧义的基类也算；想知道能否把 `D*` 当 `B*` 用，要问 `is_convertible<D*, B*>` 或 `std::derived_from`。
    - `is_convertible<From, To>` 的定义是一条假想的 `return declval<From>();` 语句是否良构，所以它按复制初始化判断，不考虑 `explicit`，而且 `From` 是 xvalue。
    - `is_invocable` 系列按 *INVOKE* 判断能否调用，成员指针也算可调用对象；`is_invocable_r` 还拒绝返回悬垂引用的调用。
    - 这些谓词大多要求实参是完整类型；违反这个前置条件是未定义行为，编译器通常不报错。

[meta.rel] 中的模板回答两个类型之间是什么关系。每个模板都是一个**二元类型特征**（[[g:cpp17-binary-type-trait|Cpp17BinaryTypeTrait]]，[[meta.rqmts]]）：条件成立时它派生自 `true_type`，否则派生自 `false_type`（第 1–2 段）。日常使用的是对应的变量模板，如 `is_same_v<T, U>`。

## 同一类型：`is_same`

`is_same<T, U>` 当且仅当 `T` 和 `U` 是同一类型、cv 限定也相同时为真。

```cpp run title="is-same.cpp" ok
#include <cstddef>
#include <type_traits>

static_assert( std::is_same_v<int, signed>);         // 同一类型的两种写法
static_assert(!std::is_same_v<int, const int>);      // cv 不同
static_assert(!std::is_same_v<char, signed char>);   // 三种 char 互不相同
static_assert(!std::is_same_v<long, long long>);     // 宽度相同也是不同类型
static_assert( std::is_same_v<std::remove_cv_t<const int>, int>);

int main() {}
```

类型别名（`typedef`、`using`）只是给已有类型起了个名字，所以 `is_same_v<std::size_t, unsigned long>` 在 LP64 平台上为真。`char`、`signed char`、`unsigned char` 是三个不同的类型（[[basic.fundamental]]），`long` 与 `long long` 即使都是 64 位也是两个类型。需要忽略 cv 时，先用 `remove_cv_t` 去掉它。

## 基类关系：`is_base_of`

```cpp run title="is-base-of.cpp" ok
#include <type_traits>

struct B {};
struct B1 : B {};
struct B2 : B {};
struct D : private B1, private B2 {};

static_assert( std::is_base_of_v<B, D>);        // 私有且有歧义，仍是基类
static_assert( std::is_base_of_v<const B, D>);  // 忽略 cv
static_assert( std::is_base_of_v<B, const B>);  // 同一个类也算
static_assert(!std::is_base_of_v<D, B>);
static_assert(!std::is_base_of_v<B&, D&>);      // 引用不是类
static_assert(!std::is_base_of_v<int, int>);    // 不是类，相同也不算

static_assert(!std::is_convertible_v<D*, B*>);  // 指针却转换不了

int main() {}
```

这段代码改编自标准的例 1（第 5 段）。`D` 有两个 `B` 子对象，而且都经由私有继承得到。`B` 仍然是 `D` 的基类（注 1），所以 `is_base_of_v<B, D>` 为真；但 `D*` 到 `B*` 的转换既有歧义又不可访问（[[conv.ptr]]），所以 `is_convertible_v<D*, B*>` 为假。

`is_base_of<Base, Derived>` 的条件是：忽略 cv 后 `Base` 是 `Derived` 的基类（[[class.derived]]），或者两者是同一个非联合类。联合体不能参与继承，所以 `is_base_of_v<U, U>` 对联合体 `U` 为假。

泛型代码如果随后要做指针转换，约束应写成 `is_convertible_v<D*, B*>`，或者 C++20 的概念 `std::derived_from<D, B>`，它同时检查基类关系和可转换性。

### `is_virtual_base_of` {{c++26}}

`is_virtual_base_of<Base, Derived>` 判断 `Base` 是否是 `Derived` 的虚基类（[[class.mi]]），直接或间接都算，忽略 cv。私有、受保护或有歧义的虚基类同样算（注 2），一个类永远不是它自己的虚基类（注 3）。

```cpp run title="is-virtual-base-of.cpp" ok
#include <type_traits>

struct V {};
struct M1 : virtual V {};
struct M2 : virtual V {};
struct MM : M1, M2 {};
struct B {};
struct N : B {};

static_assert( std::is_virtual_base_of_v<V, M1>);
static_assert( std::is_virtual_base_of_v<V, MM>);  // 间接虚基类
static_assert(!std::is_virtual_base_of_v<B, N>);   // 普通基类
static_assert(!std::is_virtual_base_of_v<V, V>);   // 注 3

int main() {}
```

虚基类子对象的位置要到运行时才知道，所以从虚基类到派生类不能用 `static_cast` 向下转换（[[expr.static.cast]]），成员指针也不能跨虚基类转换。写这类转换的泛型代码可以先用这个 trait 排除虚基类。

## 隐式转换：`is_convertible`

¶6 用一段代码定义 `is_convertible<From, To>`：

!!! std
    The predicate condition for a template specialization `is_convertible<From, To>` shall be satisfied if and only if the return statement in the following code would be well-formed, including any implicit conversions to the return type of the function: `To test() { return declval<From>(); }`

也就是说，`is_convertible` 问的是：一个 `From` 类型的表达式能否通过 `return` 语句变成 `To`。`return` 语句做的是复制初始化，由此得到三个性质。

第一，`explicit` 构造函数和 `explicit` 转换函数不参与。`is_convertible_v<int, Ex>` 对 `struct Ex { explicit Ex(int); };` 为假，而 `is_constructible_v<Ex, int>`（直接初始化）为真。`std::pair`、`std::optional` 等正是利用这个差别，写成 `explicit(!is_convertible_v<U, T>)`：只有元素能隐式转换时，包装类型才能隐式转换。

第二，`declval<From>()` 的类型是 `From&&`，这个表达式是 [[g:xvalue|xvalue]]，不是纯右值。C++17 保证的复制消除（[[class.copy.elision]]）只针对纯右值，所以从 xvalue 初始化返回对象需要移动构造函数：

```cpp run title="convertible-self.cpp" ok
#include <type_traits>

struct NM {
  NM() = default;
  NM(NM&&) = delete;
};

NM make() { return NM(); }  // OK：纯右值，不需要移动
static_assert(!std::is_convertible_v<NM, NM>);

int main() {}
```

一个不可移动的类型，按这个定义不能转换为它自己。这符合定义的本意：`is_convertible` 问的是表达式能否转换，而不可移动类型的 xvalue 确实无法初始化一个新对象。

第三，用 `return` 而不用 `To t = declval<From>();`，是为了让引用、数组、函数类型和 `void` 都有确定的结果（注 4）：

| `From → To` | 结果 | 原因 |
|---|---|---|
| `void → void` | `true` | `void` 函数可以 `return` 一个 `void` 表达式（[[stmt.return]]） |
| `int → void`、`void → int` | `false` | 表达式与返回类型不匹配 |
| `int → int[1]`、`int() → int()` | `false` | 函数不能返回数组或函数 |
| `int() → int(&)()`、`int() → int(*)()` | `true` | `declval<int()>()` 是函数左值，可以绑定引用或转换成指针 |
| `int[3] → int*` | `true` | 数组 xvalue 可以转换成指针 |

¶6 后半段说明了判断的范围。访问检查在一个与 `From`、`To` 都无关的语境中进行，所以私有的转换函数不算可用。`return` 的操作数是[[g:unevaluated-operand|不求值操作数]]，只看初始化的[[g:immediate-context|直接语境]]是否有效。注 5 提醒，初始化可能引起类模板实例化、隐式定义特殊成员函数等副作用，这些副作用不在直接语境内，其中出现的错误会让整个程序非良构，而不是让 trait 变成 `false`。

`is_nothrow_convertible` {{c++20}} 还要求这个转换已知不抛异常（按 `noexcept` 运算符的规则，[[expr.unary.noexcept]]）。

## 调用：`is_invocable` 系列

`is_invocable<Fn, Args...>` 判断表达式 *INVOKE*`(declval<Fn>(), declval<Args>()...)` 作为不求值操作数是否良构。*INVOKE* 是 [[func.require#1]] 定义的说明用操作，`std::invoke` 就是按它实现的。它统一了三种调用：

1. 普通的函数调用 `f(args...)`，`f` 可以是函数、函数指针或带 `operator()` 的对象；
2. 成员函数指针加对象：对象可以是类对象、`reference_wrapper` 或指针（包括智能指针这类可以解引用的对象）；
3. 数据成员指针加对象，结果是那个成员的引用。

```cpp run title="is-invocable.cpp" ok
#include <functional>
#include <memory>
#include <type_traits>

struct S { int m; int f(int) const; };
using PMF = int (S::*)(int) const;
using RW = std::reference_wrapper<S>;
using UP = std::unique_ptr<S>;

static_assert( std::is_invocable_v<PMF, const S&, int>);
static_assert( std::is_invocable_v<PMF, S*, long>);  // long → int
static_assert( std::is_invocable_v<PMF, RW, int>);
static_assert( std::is_invocable_v<PMF, UP&, int>);  // 先 *t1
static_assert(!std::is_invocable_v<PMF, S*>);        // 缺实参
static_assert( std::is_invocable_r_v<long, int S::*, S&>);
static_assert( std::is_invocable_r_v<void, int (*)()>);

int main() {}
```

`is_invocable_r<R, Fn, Args...>` 改用 *INVOKE*`<R>`：如果 `R` 是 `void`，调用结果被丢弃；否则结果必须能隐式转换为 `R`。C++23 起（[[P2255R2]]）又加了一条：如果把结果绑定到引用类型 `R` 会绑定到一个临时对象，*INVOKE*`<R>` 非良构。按这条规则，`is_invocable_r_v<const long&, int(*)()>` 应为假，因为 `int` 结果要先转换成一个临时的 `long`，再被引用绑定，返回后立即悬垂。

!!! impl "libc++ 尚未实现悬垂检查"
    本机 Clang 23 加 libc++ 中，`std::is_invocable_r_v<const long&, int(*)()>` 为 `true`，与当前草案不符。

`is_nothrow_invocable` 和 `is_nothrow_invocable_r` 还要求调用已知不抛异常。C++17 起 `noexcept` 是函数类型的一部分，所以只有 `void(*)() noexcept` 这样的类型才能让 `is_nothrow_invocable_v` 为真，普通的 `void(*)()` 不行。

### `is_applicable`

`is_applicable<Fn, Tuple>` 和 `is_nothrow_applicable` 是 C++23 之后的新措辞，对应 `std::apply`：能否把一个 tuple 的元素展开成实参去调用 `Fn`。它的结果类型由 [[meta.trans.other]] 的 `apply_result` 给出。

¶3 为此定义了说明用的 *ELEMS-OF*`(T)`：设 `n` 为 `tuple_size_v<remove_reference_t<T>>`，它就是形参包 `get<0>(declval<T>()), …, get<n-1>(declval<T>())`。条件中还要求 `Tuple` 满足说明用概念 *tuple-like*（[[tuple.like]]），所以对 `int` 这类不是 tuple 的类型，结果是 `false`，不会在实例化时报错。本机 libc++ 尚未提供这两个 trait。

## 布局兼容与指针可互换 {{c++20}}

这两个 trait 来自 [[P0466R5]]，它们把核心语言里的两个概念交给库来查询：

- `is_layout_compatible<T, U>`：`T` 与 `U` [[g:layout-compatible-types|布局兼容]]（[[basic.types.general]]），cv 不影响结果。对标准布局类，这意味着两者的[[g:common-initial-sequence|公共初始序列]]包含了全部非静态数据成员；对枚举，意味着底层类型相同（[[dcl.enum]]）。
- `is_pointer_interconvertible_base_of<Base, Derived>`：`Derived` 无歧义地派生自 `Base`，而且每个 `Derived` 对象都与它的 `Base` 子对象[[g:pointer-interconvertible|指针可互换]]（[[basic.compound]]），即两者地址相同、可以用 `reinterpret_cast` 互相转换；或者两者是同一个非联合类。实际上这要求 `Derived` 是标准布局类。

同一提案还在 [[meta.member]] 中加入了判断成员的两个函数。

!!! impl "libc++ 没有提供这两个 trait"
    本机 libc++ 没有 `std::is_layout_compatible` 和 `std::is_pointer_interconvertible_base_of`，也没有定义对应的特性测试宏。Clang 23 提供了它们背后的内建，可以直接验证语义；GCC 的 libstdc++ 提供了 `std::` 版本。

    ```cpp run title="layout-builtins.cpp" ok
    struct A { int a; };
    struct B { int b; };
    struct C : A, B {};  // 成员分散在两个类中：不是标准布局
    struct D : A {};     // 标准布局

    struct P { int x; char y; };
    struct Q { const int u; char v; };  // cv 不影响
    struct R { int x; char y; char z; };
    enum class E1 : int {};
    enum class E2 : int {};

    static_assert( __is_layout_compatible(P, Q));
    static_assert(!__is_layout_compatible(P, R));
    static_assert( __is_layout_compatible(E1, E2));
    static_assert(!__is_layout_compatible(E1, int));
    static_assert( __is_pointer_interconvertible_base_of(A, D));
    static_assert(!__is_pointer_interconvertible_base_of(A, C));
    static_assert( __is_pointer_interconvertible_base_of(A, A));

    int main() {}
    ```

## 前置条件

这些模板大多要求实参是完整类型、`void` 或未知边界的数组。`is_base_of` 和 `is_pointer_interconvertible_base_of` 放宽了一点：只有当两者是不同的非联合类时，才要求 `Derived` 完整，因为不看到类的定义就不知道它的基类。

违反前置条件是未定义行为，编译器通常不诊断。本机 Clang 对 `is_convertible<Incomplete, int>` 静默地给出 `false`。即使实参满足前置条件，如果结果取决于某个尚未定义完整的类型，而这个类型完整之后结果会不同，行为同样未定义（[[meta.rqmts#5]]）。例如对 `Incomplete*` 问它能否转换为 `Base*`，在 `Incomplete` 定义之前和之后答案可能不一样。

¶4 说明，定义中出现的 `declval<T>()` 当作一次平凡的函数调用，而且不算对 `declval` 的 [[g:odr-use|odr-use]]。`declval` 本来只能出现在不求值操作数中，这条规定让上面的定义不必顾虑这个限制。

## 陷阱

!!! pitfall "参数顺序各不相同"
    `is_convertible<From, To>` 源在前，`is_base_of<Base, Derived>` 基类在前，`is_assignable<T, U>` 目标在前。C++20 的概念 `std::convertible_to<From, To>` 与 `is_convertible` 一致，`std::derived_from<Derived, Base>` 却是派生类在前。

## 思考题

!!! question "思考题 1"
    设 `struct A {}; struct B : A {};`。`is_convertible_v<B, A>`、`is_convertible_v<A, B>`、`is_convertible_v<B&, A&>`、`is_convertible_v<B[2], A*>` 分别是什么？

<details markdown="1">
<summary>答案</summary>

依次为 `true`、`false`、`true`、`true`（本机 Clang 23 验证）。

- `B → A`：`return declval<B>();` 用 `B` 的 xvalue 复制初始化 `A`，选中 `A` 的移动构造函数（形参 `A&&` 可以绑定到派生类对象），即对象切片。
- `A → B`：基类到派生类没有隐式转换。
- `B& → A&`：引用可以绑定到派生类对象的基类子对象。
- `B[2] → A*`：先做数组到指针转换得到 `B*`，再做派生类到基类的指针转换，两者可以组成一个标准转换序列（[[over.ics.scs]]）。

最后一个说明能转换不等于能安全使用：通过这个 `A*` 做指针算术去访问第二个元素是 UB，因为指针算术要求指向的类型与数组元素类型相似（[[expr.add]]）。
</details>

!!! question "思考题 2"
    `is_invocable_v<int (S::*)(), S>` 与 `is_invocable_v<int (S::*)() &, S>` 有什么不同？

<details markdown="1">
<summary>答案</summary>

`declval<S>()` 是 `S` 类型的 xvalue。第一个成员函数没有引用限定，可以在 xvalue 上调用，结果为真。第二个带 `&` 限定，只能在左值对象上调用（[[over.match.funcs]]），结果为假。改成 `is_invocable_v<int (S::*)() &, S&>` 就为真。
</details>

## 速查

| 谓词 | 条件 |
|---|---|
| `is_same<T, U>` | 同一类型，cv 也相同 |
| `is_base_of<Base, Derived>` | 基类（含私有、有歧义的）或同一非联合类，忽略 cv |
| `is_virtual_base_of<Base, Derived>` {{c++26}} | 虚基类，忽略 cv；类不是自己的虚基类 |
| `is_convertible<From, To>` | `To test() { return declval<From>(); }` 良构 |
| `is_nothrow_convertible<From, To>` {{c++20}} | 可转换且不抛异常 |
| `is_layout_compatible<T, U>` {{c++20}} | 布局兼容 |
| `is_pointer_interconvertible_base_of<Base, Derived>` {{c++20}} | 无歧义的基类且与派生类对象指针可互换，或同一非联合类 |
| `is_invocable<Fn, Args...>` | *INVOKE*`(declval<Fn>(), declval<Args>()...)` 良构 |
| `is_invocable_r<R, Fn, Args...>` | *INVOKE*`<R>(...)` 良构，结果不绑定到临时对象 |
| `is_nothrow_invocable(_r)` | 上述且不抛异常 |
| `is_applicable<Fn, Tuple>` | `Tuple` 是 *tuple-like*，展开后可调用 |
