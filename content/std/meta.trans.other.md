---
title: 其他变换
summary: type_identity、remove_cvref、decay、enable_if、conditional、void_t，以及本节的重头戏——common_type 的精确算法（退化、条件运算符、CREF 回退、左折叠、用户特化许可）与 common_reference 的 COMMON-REF 算法和 basic_common_reference 定制点；underlying_type、invoke_result、apply_result、unwrap_reference
status: draft
covers: meta.trans.other
papers: P0898R3, P0887R1, P0550R2
related: meta.trans, type.traits, meta.rel, expr.cond, conv.lval, conv.array, conv.func, dcl.enum, func.require, temp.deduct.call, concepts
tags: 标准库, type_traits, common_type, common_reference, decay, SFINAE
updated: 2026-10-18
---

[meta.trans.other] 收录了不能简单归入"cv/引用/符号/数组/指针"的变换。其中有几行就能说清的工具（`type_identity`、`remove_cvref`、`enable_if`、`conditional`），也有标准库中最精巧的**类型算法**：`common_type` 与 `common_reference`。后两者是 C++20 范围库与概念（`std::common_with`、`std::common_reference_with`、`iter_common_reference_t`）的地基。

## 表 62 速览

| 模板 | `type` | 何时没有 `type` |
|---|---|---|
| `type_identity<T>` {{c++20}} | `T` | — |
| `remove_cvref<T>` {{c++20}} | `remove_cv_t<remove_reference_t<T>>` | — |
| `decay<T>` | 模拟按值传参：数组→指针、函数→指针、否则去引用去 cv | — |
| `enable_if<B, T = void>` | `B` 为真时为 `T` | `B` 为假 |
| `conditional<B, T, F>` | `B ? T : F` | — |
| `common_type<T...>` | 见 ¶4 | 无公共类型时 |
| `basic_common_reference<T, U, TQual, UQual>` | 主模板没有；供用户偏特化 | 默认就没有 |
| `common_reference<T...>` {{c++20}} | 见 ¶6 | 无公共引用时 |
| `underlying_type<T>` | 枚举的底层类型 | `T` 不是枚举 |
| `invoke_result<Fn, Args...>` {{c++17}} | `decltype(INVOKE(declval<Fn>(), declval<Args>()...))` | 表达式非良构 |
| `apply_result<Fn, Tuple>` | `decltype(INVOKE(declval<Fn>(), ELEMS-OF(Tuple)...))` | 非 *tuple-like* 或表达式非良构 |
| `unwrap_reference<T>` {{c++20}} | `reference_wrapper<X>` → `X&`；否则 `T` | — |
| `unwrap_ref_decay<T>` {{c++20}} | `unwrap_reference_t<decay_t<T>>` | — |

此外概要里还有 `void_t`：`template<class...> using void_t = void;`。

## 简单工具

**`type_identity`**（[[P0887R1]]）：`type` 就是 `T`。它的价值在于 `type_identity_t<T>` 是一个**非推导语境**（[[temp.deduct.type]]）——嵌套名说明符左边的部分不参与推导。于是可以"关掉"某个形参的推导：

```cpp
template<class T> void f(T a, std::type_identity_t<T> b);
f(1.0, 2);   // T 只从第一个实参推导为 double；2 再隐式转换。没有它会推导冲突
```

**`remove_cvref`**（[[P0550R2]]）：先去引用再去 cv。C++20 之前人们常用 `decay_t` 代替它，但 `decay` 还会把数组和函数变成指针——`remove_cvref_t<const int(&)[3]>` 是 `int[3]`，而 `decay_t` 给出 `const int*`。

**`decay`**：

!!! std
    Let `U` be `remove_reference_t<T>`. If `is_array_v<U>` is `true`, ... `remove_extent_t<U>*`. If `is_function_v<U>` is `true`, ... `add_pointer_t<U>`. Otherwise ... `remove_cv_t<U>`.

    令 `U` 为 `remove_reference_t<T>`。若 `U` 是数组，结果为 `remove_extent_t<U>*`；若是函数，结果为 `add_pointer_t<U>`；否则为 `remove_cv_t<U>`。

注 1 说明了它的意图：这类似左值用作右值时发生的左值到右值（[[conv.lval]]）、数组到指针（[[conv.array]]）、函数到指针（[[conv.func]]）转换，**但还会去掉类类型的 cv**，以便更贴切地模拟**按值传参**。`std::make_pair`、`std::thread` 的构造函数、`std::bind` 都用 `decay_t` 决定"存一份什么"。注意数组退化时**保留元素的 cv**：`decay_t<const int[3]>` 是 `const int*`。

**`enable_if`**：`B` 为真时 `type` 为 `T`，否则**没有** `type` 成员（"there shall be no member `type`"）。这一"没有"在模板实参推导中造成替换失败，从而实现 SFINAE（[[temp.deduct]]）。C++20 起大多数用法应改为 `requires` 子句。

**`conditional`**：编译期的 `?:`。它**不会短路**：`conditional_t<B, T, F>` 要求 `T` 和 `F` 都是合法类型，两个分支都会被"求值"（形成类型）。想延迟某个分支的实例化，要把"取 `::type`"放到选择之后：`typename conditional_t<B, type_identity<X>, Lazy<Y>>::type`。

**`void_t`**：把任意多个类型映射为 `void`，配合偏特化做"检测惯用法"：

```cpp run title="void-t.cpp" ok
#include <type_traits>
#include <utility>
#include <vector>

template<class T, class = void>
struct has_size : std::false_type {};
template<class T>
struct has_size<T, std::void_t<decltype(std::declval<T&>().size())>> : std::true_type {};

static_assert( has_size<std::vector<int>>::value);
static_assert(!has_size<int>::value);

int main() {}
```

## `common_type`：精确算法（¶4）

`common_type<T...>` 想回答"这些类型的值放在一起时，应该用什么类型表示"。它的规则看似复杂，其实是一个**以条件运算符为核心、外加两道保险的左折叠**。先看 ¶3 定义的说明用工具：

| 记号 | 含义 |
|---|---|
| *CREF*`(A)` | `add_lvalue_reference_t<const remove_reference_t<A>>`，即 `const A&`（`A` 可引用时）|
| *COND-RES*`(X, Y)` | `decltype(false ? declval<X(&)()>()() : declval<Y(&)()>()())` |

*COND-RES* 那个奇怪的写法 `declval<X(&)()>()()` 是在"调用一个返回 `X` 的函数"：这样得到的表达式**恰好**具有类型 `X` 和对应的值类别（`X` 是左值引用 → 左值；右值引用 → xvalue；非引用 → 纯右值）。直接写 `declval<X>()` 做不到"纯右值"——它总是返回引用。

### 按实参个数分情况

**(4.1) 零个类型**：没有 `type`。

**(4.2) 一个类型 `T0`**：等同于 `common_type_t<T0, T0>`。所以 `common_type_t<const int>`、`common_type_t<int&>` 都是 `int`——单个类型的公共类型是它"退化后"的样子。

**(4.3) 两个类型 `T1`、`T2`**：令 `D1 = decay_t<T1>`、`D2 = decay_t<T2>`。

- **(4.3.1)** 若 `T1` 或 `T2` 不等于其退化类型，结果就是 `common_type_t<D1, D2>`（如果有）。即：**先退化，再递归**。这一步保证用户只需为退化后的类型写特化（¶5），`common_type<const Meters&, Feet>` 也能找到 `common_type<Meters, Feet>` 的特化。
- **(4.3.2)** 注 4：如果存在特化 `common_type<D1, D2>`，下面两条都不适用——用户特化优先。
- **(4.3.3)** 否则，若 `decay_t<decltype(false ? declval<D1>() : declval<D2>())>` 是合法类型，它就是结果。
- **(4.3.4)** 否则，若 *COND-RES*`(`*CREF*`(D1),` *CREF*`(D2))` 是类型，结果是它的 `decay_t`——即**用 `const D1&` 和 `const D2&` 再试一次条件运算符**。
- 都不行则没有 `type`。

**(4.4) 三个及以上**：先求 `C = common_type_t<T1, T2>`，再求 `common_type_t<C, R...>`——**左折叠**；任何一步失败，整体没有 `type`。

### 推演几个例子

| 表达式 | 结果 | 走到哪一步 |
|---|---|---|
| `common_type_t<int, long>` | `long` | 4.3.3：`?:` 做常用算术转换（[[expr.cond]] → [[expr.arith.conv]]）|
| `common_type_t<short, short>` | `short` | 4.3.3：两边同类型，`?:` 不提升 |
| `common_type_t<short, char>` | `int` | 4.3.3：不同类型 → 整型提升 |
| `common_type_t<int, unsigned>` | `unsigned` | 常用算术转换 |
| `common_type_t<int&, const int&>` | `int` | 4.3.1 先退化成 `<int, int>` |
| `common_type_t<void, void>` | `void` | 4.3.3：`false ? void : void` 合法，类型为 `void` |
| `common_type_t<B*, D*>`（`D : B`）| `B*` | 4.3.3：复合指针类型（[[expr.type]]）|
| `common_type_t<std::string, const char*>` | `std::string` | 4.3.3：`const char*` 可转换为 `string`，反之不行 |
| `common_type_t<int, std::string>` | 无 | 两边都不能转换为对方 |
| `common_type_t<char, unsigned char, float>` | `float` | 4.4：`<char, unsigned char>` → `int`，`<int, float>` → `float` |

4.3.4 那道"保险"在什么时候起作用？当条件运算符对 xvalue 失败、对 const 左值却成功时：

```cpp run title="common-type-cref.cpp" ok
#include <type_traits>
#include <utility>

struct A {};
struct B {
    B(const A&);
    B(A&&) = delete;          // 从右值 A 转换被删除
};

template<class T, class U>
concept HasCond = requires { false ? std::declval<T>() : std::declval<U>(); };

static_assert(!HasCond<A, B>);                 // 4.3.3：A&& 转 B 选中被删除的构造函数 → 失败
static_assert( HasCond<const A&, const B&>);   // 4.3.4：const A& 转 B 可行
static_assert(std::is_same_v<std::common_type_t<A, B>, B>);

int main() {}
```

4.3.4 是 C++20 与 `common_reference` 同期加入的；有了它，只能从 `const` 左值转换（而从右值转换不可行）的类型也能得到公共类型。

### 用户特化许可（¶5）

!!! std
    Notwithstanding the provisions of [meta.rqmts], and pursuant to [namespace.std], a program may specialize `common_type<T1, T2>` for types `T1` and `T2` such that `is_same_v<T1, decay_t<T1>>` and `is_same_v<T2, decay_t<T2>>` are each `true`.

    尽管有 [meta.rqmts] 的规定，并依据 [namespace.std]，程序可以为满足 `is_same_v<T1, decay_t<T1>>` 与 `is_same_v<T2, decay_t<T2>>` 均为真的类型 `T1`、`T2` 特化 `common_type<T1, T2>`。

这是 [[type.traits]] "不得特化"红线的第一个例外，附带三个条件：

1. 只能特化**两个实参**、且都是**退化后类型**的版本（特化 `common_type<const X&, Y>` 永远不会被用到，因为 4.3.1 会先退化）；
2. 若提供 `type`，它必须是 cv 无限定的非引用类型，且 `T1`、`T2` 都能**显式**转换为它；
3. `common_type_t<T1, T2>` 与 `common_type_t<T2, T1>` 必须相同——所以通常要成对特化。

违反这些规则**不需要诊断**（[[g:ifndr]]）。注 5 说明了这种特化的动机：当两个类型之间**只有显式转换**时，条件运算符找不到公共类型，必须由用户声明。标准库自己的例子是 `<chrono>` 中 `common_type<duration<...>, duration<...>>` 的特化。

```cpp run title="common-type-spec.cpp" ok
#include <type_traits>

struct Meters { double v; };
struct Feet   { double v; explicit operator Meters() const; };

template<> struct std::common_type<Meters, Feet> { using type = Meters; };
template<> struct std::common_type<Feet, Meters> { using type = Meters; };   // 对称性

static_assert(std::is_same_v<std::common_type_t<const Meters&, Feet>, Meters>);   // 先退化，再命中特化

int main() {}
```

## `common_reference`：引用感知的公共类型（¶3、¶6、¶7）

`common_type` 总是退化，结果永远是非引用类型。但范围库需要回答另一个问题：**"一个 `int&` 和一个 `const int&`，有没有一个引用类型能同时绑定它们？"**——答案是 `const int&`。`common_reference`（[[P0898R3]]）就是为此设计的。

### ¶3 的 *COMMON-REF*

令 *COPYCV*`(FROM, TO)` 为给 `TO` 加上 `FROM` 的顶层 cv；*XREF*`(A)` 为一个一元别名模板，把 `A` 的 cv 和引用限定"复制"到它的实参上。给定 `A`、`B`，令 `X = remove_reference_t<A>`、`Y = remove_reference_t<B>`：

| 情形 | *COMMON-REF*`(A, B)` |
|---|---|
| (3.5) 都是左值引用 | *COND-RES*`(`*COPYCV*`(X, Y)&,` *COPYCV*`(Y, X)&)`，前提是它存在且**是引用类型** |
| (3.6) 都是右值引用 | 令 `C = remove_reference_t<COMMON-REF(X&, Y&)>&&`；若 `A`、`B` 都能转换为 `C`，则为 `C` |
| (3.7) `A` 右值、`B` 左值 | 令 `D = COMMON-REF(const X&, Y&)`；若 `A` 能转换为 `D`，则为 `D` |
| (3.8) `A` 左值、`B` 右值 | *COMMON-REF*`(B, A)` |
| (3.9) 其他 | 非良构 |

直觉：两个左值引用时，先把双方的 cv "合并"（`int&` 与 `const int&` 都变成 `const int&`），再看条件运算符能否产生一个**左值**；一个左值一个右值时，退而求其次用 `const X&`（它能绑定右值）。

### ¶6 的算法

1. 零个类型：无 `type`；一个类型：就是它本身（**不退化**——与 `common_type` 不同）。
2. 两个类型 `T1`、`T2`，依次尝试：
    - (6.3.1) 若两者都是引用，*COMMON-REF*`(T1, T2)` 良构，且 `T1*`、`T2*` 都能转换为结果的指针类型 → 用它；
    - (6.3.2) 否则，若 `basic_common_reference<remove_cvref_t<T1>, remove_cvref_t<T2>, XREF(T1), XREF(T2)>::type` 良构 → 用它（**用户定制点**）；
    - (6.3.3) 否则，若 *COND-RES*`(T1, T2)` 良构 → 用它；
    - (6.3.4) 否则，若 `common_type_t<T1, T2>` 良构 → 用它；
    - 否则无 `type`。
3. 三个以上：左折叠，同 `common_type`。

```cpp run title="common-reference.cpp" ok
#include <ranges>
#include <tuple>
#include <type_traits>
#include <vector>
using namespace std;

struct B {}; struct D : B {};

static_assert(is_same_v<common_reference_t<int&, const int&>, const int&>);   // 6.3.1
static_assert(is_same_v<common_reference_t<int&&, int&>, const int&>);        // 3.7
static_assert(is_same_v<common_reference_t<int&&, int&&>, int&&>);            // 3.6
static_assert(is_same_v<common_reference_t<B&, D&>, B&>);
static_assert(is_same_v<common_reference_t<int&, long&>, long>);              // 6.3.3：?: 产生纯右值 long
static_assert(is_same_v<common_reference_t<int>, int>);                       // 单个：不退化
static_assert(is_same_v<common_reference_t<vector<bool>::reference, bool&>, bool>);

// zip 的引用类型是 tuple<int&, int&>；它与值类型 tuple<int, int> 的公共引用
// 靠标准库为 tuple 提供的 basic_common_reference 偏特化得出
using ZipRef = ranges::range_reference_t<
    decltype(views::zip(declval<vector<int>&>(), declval<vector<int>&>()))>;
static_assert(is_same_v<ZipRef, tuple<int&, int&>>);
static_assert(is_same_v<common_reference_t<tuple<int&, int&>&&, tuple<int, int>&>, tuple<int&, int&>>);

int main() {}
```

### `basic_common_reference`（¶7）

主模板**没有** `type`。¶7 允许程序**偏特化**它（这是"不得特化"的第二个例外），条件与 `common_type` 类似：`T`、`U` 是退化后的类型；若有 `type`，`TQual<T>` 与 `UQual<U>` 都须能（隐式）转换为它；且对 `(T, U)` 与 `(U, T)` 的结果须相同；违反不需诊断。注 6：它用于影响 `common_reference` 的结果，以及在模板实参间只有显式转换时提供结果。

`TQual`/`UQual` 就是 *XREF*`(T1)`/*XREF*`(T2)`：特化可以据此知道原来的实参带着什么 cv 和引用，从而算出"正确限定"的公共引用。标准库为 `pair`、`tuple`、`reference_wrapper` 等提供了这种偏特化，这正是 `views::zip` 的代理引用 `tuple<int&, int&>` 能与 `tuple<int, int>&` 建立公共引用、从而满足 `std::indirectly_readable` 的原因。

## `underlying_type`

若 `T` 是枚举类型，`type` 为其底层类型（[[dcl.enum]]）；否则**没有** `type`（C++20 起，此前对非枚举是 UB）。*Mandates*：`T` 不是不完整的枚举类型。

所谓"不完整的枚举类型"，是底层类型尚未确定的枚举：没有固定底层类型的枚举，在其枚举说明符的右花括号之前是不完整的（[[dcl.enum]]、[[basic.types.general#3]]）。带固定底层类型的不透明声明 `enum Fwd : int;` 已经足够：`underlying_type_t<Fwd>` 是 `int`。

```cpp run title="underlying-type.cpp" ok
#include <type_traits>

enum Fwd : int;                                   // 不透明声明，底层类型已固定
static_assert(std::is_same_v<std::underlying_type_t<Fwd>, int>);

template<class T>
concept HasUT = requires { typename std::underlying_type<T>::type; };
static_assert(!HasUT<int>);                        // 非枚举：没有 type，SFINAE 友好

int main() {}
```

## `invoke_result` 与 `apply_result`

`invoke_result<Fn, ArgTypes...>`：若 *INVOKE*`(declval<Fn>(), declval<ArgTypes>()...)`（[[func.require]]）作为不求值操作数良构，`type` 为它的 `decltype`；否则没有 `type`。访问检查在无关语境中进行，只看直接语境（注 2，同 [[meta.unary.prop]]）。*Preconditions*：各类型完整、*cv* `void` 或未知边界数组。

它在 C++17 取代了 `result_of<F(Args...)>`——后者借用函数类型 `F(Args...)` 充当"调用签名"，于是 `F` 被放在了返回类型的位置（不能是函数或数组类型），`Args` 也会经历函数形参的类型调整（数组、函数退化为指针，顶层 cv 被丢弃），C++17 弃用、C++20 移除。

¶8 的例子把 *INVOKE* 的各种形态都走了一遍：

```cpp run title="invoke-result.cpp" ok
#include <memory>
#include <type_traits>
using namespace std;

using PF1 = bool  (&)();
using PF2 = short (*)(long);

struct S {
    operator PF2() const;               // S 可转换为函数指针：代理调用函数
    double operator()(char, int&);
    void fn(long) const;
    char data;
};

using PMF = void (S::*)(long) const;
using PMD = char S::*;

static_assert(is_same_v<invoke_result_t<S, int>, short>);                     // 经由转换函数调用 PF2
static_assert(is_same_v<invoke_result_t<S&, unsigned char, int&>, double>);   // operator() 更好
static_assert(is_same_v<invoke_result_t<PF1>, bool>);
static_assert(is_same_v<invoke_result_t<PMF, unique_ptr<S>, int>, void>);      // 类指针对象
static_assert(is_same_v<invoke_result_t<PMD, S>, char&&>);                     // 数据成员 + 右值对象 → xvalue
static_assert(is_same_v<invoke_result_t<PMD, const S*>, const char&>);

int main() {}
```

第一行值得细想：`S` 有非 `const` 的 `operator()(char, int&)`，但 `declval<S>()` 是 xvalue，`int` 实参无法绑定 `int&`，于是 `operator()` 不可行；`S` 还能通过 `operator PF2() const` 转换为函数指针，这在函数调用中构成**代理调用函数**（[[over.call.object]]），最终调用 `short(*)(long)`。

`apply_result<Fn, Tuple>`（当前草案新增）：若 *tuple-like*`<Tuple>` 为真且 *INVOKE*`(declval<Fn>(), ELEMS-OF(Tuple)...)` 良构，`type` 为其 `decltype`。*ELEMS-OF* 的定义见 [[meta.rel]] ¶3。本地 libc++ 尚未提供。

## `unwrap_reference` 与 `unwrap_ref_decay`

`unwrap_reference<T>`：若 `T` 是 `reference_wrapper<X>` 的特化，`type` 为 `X&`；否则为 `T`。注意它**不先退化**：`unwrap_reference_t<const reference_wrapper<int>>` 仍是 `const reference_wrapper<int>`。`unwrap_ref_decay<T>` 先 `decay_t` 再 `unwrap_reference_t`，正好描述了 `std::make_pair(x, std::ref(y))` 的成员类型：按值退化，但 `std::ref` 包装的会变成引用。

¶2：这四个模板（含 `_t` 别名）在包含 `<functional>` 时也可用——它们与 `reference_wrapper` 同住一处更合理。

## 实现视角

!!! impl "libc++ 的 `common_type`：内建优先，回退时逐条对照标准"
    Clang 提供内建模板 `__builtin_common_type`，libc++ 优先使用：

    ```cpp
    #if __has_builtin(__builtin_common_type)
    template <class... _Args>
    struct common_type : __builtin_common_type<__common_type_t, __type_identity, __empty, _Args...> {};
    #else
    // ... 纯模板实现，注释里逐条标注 "bullet 1 - sizeof...(Tp) == 0"、
    //     "sub-bullet 3 - if decay_t<decltype(false ? declval<D1>() : declval<D2>())> ..."
    ```

    内建接受三个"回调"模板：`__common_type_t` 用于递归查询（以便命中用户特化）、`__type_identity` 用于包装结果、`__empty` 表示"没有 `type`"。回退实现的 sub-bullet 3 写的是 `true ? declval<_Tp>() : declval<_Up>()`——条件运算符的类型与条件的值无关，`true` 与标准中的 `false` 等价。

## 陷阱

!!! pitfall "`common_type` 不是\"能装下两者的类型\""
    `common_type_t<int, unsigned>` 是 `unsigned`——负数会回绕。`common_type_t<long long, double>` 是 `double`——大整数会丢精度。它复刻的是条件运算符的常用算术转换，而不是"无损公共表示"。

!!! pitfall "`conditional` 两个分支都会形成"
    `conditional_t<is_integral_v<T>, make_signed_t<T>, T>` 在 `T = double` 时非良构：`make_signed_t<double>` 在选择之前就被形成了。改为 `typename conditional_t<is_integral_v<T>, make_signed<T>, type_identity<T>>::type`。

!!! pitfall "为非退化类型特化 `common_type` 是白费功夫"
    4.3.1 总是先退化再递归，`template<> struct common_type<const X&, Y>` 永远不会被选中，而且违反了 ¶5 的许可条件。

## 思考题

!!! question "思考题 1"
    `std::common_type_t<int[3], int*>` 与 `std::common_type_t<int(), int(*)()>` 分别是什么？

<details markdown="1">
<summary>展开查看答案与解析</summary>

都走 4.3.1 先退化：`decay_t<int[3]>` 是 `int*`，`decay_t<int()>` 是 `int(*)()`。于是分别化为 `common_type_t<int*, int*>` = `int*` 和 `common_type_t<int(*)(), int(*)()>` = `int(*)()`。
</details>

!!! question "思考题 2"
    为什么 `common_reference_t<int&, long&>` 是 `long` 而不是 `long&` 或 `const long&`？

<details markdown="1">
<summary>展开查看答案与解析</summary>

6.3.1：两个都是左值引用，*COMMON-REF*`(int&, long&)` 按 3.5 计算 *COND-RES*`(int&, long&)`。条件运算符的两个操作数是不同类型的左值，需要常用算术转换，结果是 `long` **纯右值**（[[expr.cond]]），不是引用类型，所以 3.5 不成立，*COMMON-REF* 非良构。6.3.2 没有 `basic_common_reference` 特化。6.3.3 *COND-RES*`(int&, long&)` 良构，得到 `long`。`const long&` 不会被选中：没有任何一步把 `const long&` 当作候选——`int&` 不能直接绑定到 `long` 对象，只能绑定到转换出的临时量，那不是"公共引用"。
</details>

## 小结

| 工具 | 一句话 |
|---|---|
| `type_identity` | 制造非推导语境 |
| `remove_cvref` vs `decay` | 前者只去引用和 cv；后者还做数组/函数到指针 |
| `enable_if` / `void_t` | 靠"没有 `type`"/"替换失败"实现 SFINAE |
| `conditional` | 不短路，两个分支都要合法 |
| `common_type` | 先退化 → 用户特化 → `?:`（xvalue）→ `?:`（const 左值）→ 左折叠 |
| `common_reference` | *COMMON-REF* → `basic_common_reference` → `?:` → `common_type` |
| `underlying_type` | 非枚举时无 `type`（C++20 起）|
| `invoke_result` | 取代 `result_of`；基于 *INVOKE* |
| `unwrap_ref_decay` | `make_pair`/`make_tuple` 的成员类型规则 |
