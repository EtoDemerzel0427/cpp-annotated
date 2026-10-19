---
title: 其他变换
summary: decay、enable_if、conditional 等常用变换，common_type 与 common_reference 的求解算法，以及 underlying_type、invoke_result、unwrap_reference。
status: draft
covers: meta.trans.other
papers: P0898R3, P0887R1, P0550R2
related: meta.trans, type.traits, meta.rel, expr.cond, conv.lval, conv.array, conv.func, dcl.enum, func.require, temp.deduct.call, concepts
tags: 标准库, type_traits, common_type, common_reference, decay, SFINAE
updated: 2026-10-19
---

!!! tldr
    - `decay_t<T>` 模拟按值传参：去掉引用，数组和函数变成指针，再去掉顶层 cv；只想去掉引用和 cv 时用 `remove_cvref_t`。
    - `conditional_t<B, T, F>` 不会短路，两个分支的类型都必须能形成。
    - `common_type` 先把实参退化，再看用户特化，再用条件运算符求公共类型，多个实参时从左到右两两折叠。它复刻的是条件运算符的转换规则，不保证无损。
    - `common_reference` 在可能时给出引用类型，例如 `int&` 与 `const int&` 的公共引用是 `const int&`；范围库靠它和 `basic_common_reference` 处理 `zip` 这类代理引用。
    - `invoke_result` 按 *INVOKE* 求调用结果的类型，取代了 C++20 移除的 `result_of`。

[meta.trans.other] 收录了不属于 cv、引用、符号、数组、指针五组的变换（第 1 段）。它们都是变换特征：结果在嵌套的 `type` 里，另有 `_t` 别名（[[meta.trans]]）。其中几个在条件不满足时没有 `type` 成员，这是它们能用于 SFINAE 的原因。

## 常用的小工具

### `decay` 与 `remove_cvref`

```cpp run title="decay.cpp" ok
#include <type_traits>
using namespace std;

static_assert(is_same_v<decay_t<const int&>, int>);
static_assert(is_same_v<decay_t<const int[3]>, const int*>);
static_assert(is_same_v<decay_t<int(int)>, int (*)(int)>);
static_assert(is_same_v<remove_cvref_t<const int(&)[3]>, int[3]>);

int main() {}
```

`decay<T>` 的规则是：令 `U` 为 `remove_reference_t<T>`；如果 `U` 是数组，结果是 `remove_extent_t<U>*`；如果是函数，结果是 `add_pointer_t<U>`；否则结果是 `remove_cv_t<U>`。

它模拟的是一个实参按值传给函数时的类型变化（注 1）：左值到右值、数组到指针、函数到指针三种转换（[[conv.lval]]、[[conv.array]]、[[conv.func]]），外加去掉类类型的 cv。`std::make_pair`、`std::thread` 的构造函数、`std::bind` 都用 `decay_t` 决定保存一份什么类型的副本。数组退化时元素的 cv 会保留，所以 `decay_t<const int[3]>` 是 `const int*`。

`remove_cvref<T>` {{c++20}}（[[P0550R2]]）只做 `remove_cv_t<remove_reference_t<T>>`，不碰数组和函数。在它出现之前，人们常把 `decay_t` 当作去掉引用和 cv 的工具，遇到数组参数时就会得到意外的指针类型。

### `type_identity` {{c++20}}

`type_identity<T>::type` 就是 `T`（[[P0887R1]]）。它的用处是制造一个[[temp.deduct.type|不推导的语境]]：`type_identity_t<T>` 实际是 `type_identity<T>::type`，`::` 左边的 `T` 不参与模板实参推导。

```cpp run title="type-identity.cpp" ok
#include <type_traits>

template<class T>
T add(T a, std::type_identity_t<T> b) { return a + b; }

int main() {
  double d = add(1.0, 2);  // T 只从第一个实参推导
  (void)d;
}
```

如果第二个形参也写成 `T`，两个实参分别推导出 `double` 和 `int`，推导失败。用 `type_identity_t<T>` 后，`T` 只从第一个实参推导为 `double`，`2` 再隐式转换为 `double`。

### `enable_if`、`conditional`、`void_t`

`enable_if<B, T = void>` 在 `B` 为真时 `type` 是 `T`，否则没有 `type` 成员。在模板实参推导中引用一个不存在的 `type` 会导致替换失败，候选被丢弃而不是报错（SFINAE，[[temp.deduct]]）。C++20 之后，大多数这类用法可以改写为 `requires` 子句。

`conditional<B, T, F>` 在 `B` 为真时 `type` 是 `T`，否则是 `F`。它是一个普通的类模板，`T` 和 `F` 在选择之前都要先形成，不存在短路：

<div class="compare" markdown="1">

```cpp error
#include <type_traits>
using namespace std;

template<class T>
using S = conditional_t<is_integral_v<T>,
                        make_signed_t<T>, T>;
S<double>* p;  // error: make_signed<double>
```

```cpp ok
#include <type_traits>
using namespace std;

template<class T>
using S = typename conditional_t<
    is_integral_v<T>,
    make_signed<T>, type_identity<T>>::type;
S<double>* p;  // OK: double
```

</div>

左边在 `T = double` 时要先形成 `make_signed_t<double>`，违反了 `make_signed` 的 *Mandates*。右边先在两个类模板之间选择，选出来之后才取 `::type`，没被选中的 `make_signed<double>` 不会实例化。

`void_t` 在 `<type_traits>` 的概要中定义为 `template<class...> using void_t = void;`。它把任意多个类型映射为 `void`，常和偏特化一起用来检测某个表达式是否合法：

```cpp run title="void-t.cpp" ok
#include <type_traits>
#include <utility>
#include <vector>

template<class T, class = void>
struct has_size : std::false_type {};

template<class T>
struct has_size<T,
    std::void_t<decltype(std::declval<T&>().size())>>
    : std::true_type {};

static_assert( has_size<std::vector<int>>::value);
static_assert(!has_size<int>::value);

int main() {}
```

对 `int`，偏特化中的 `decltype` 表达式替换失败，偏特化被丢弃，选中主模板。C++20 中同样的检测可以写成概念 `requires (T& t) { t.size(); }`。

## `common_type`

`common_type<T...>` 回答：这些类型的值放在一起时用什么类型表示。它是 `std::common_with` 等概念的基础，`<chrono>` 用它决定两个不同 `duration` 相加的结果类型。

```cpp run title="common-type.cpp" ok
#include <string>
#include <type_traits>
using namespace std;

struct B {};
struct D : B {};

static_assert(is_same_v<common_type_t<int, long>, long>);
static_assert(is_same_v<common_type_t<short, char>, int>);
static_assert(is_same_v<common_type_t<short, short>, short>);
static_assert(is_same_v<common_type_t<int, unsigned>, unsigned>);
static_assert(is_same_v<common_type_t<int&, const int&>, int>);
static_assert(is_same_v<common_type_t<void, void>, void>);
static_assert(is_same_v<common_type_t<B*, D*>, B*>);
static_assert(is_same_v<common_type_t<string, const char*>,
                        string>);
static_assert(is_same_v<common_type_t<char, unsigned char, float>,
                        float>);

int main() {}
```

这些结果都来自条件运算符 `false ? x : y` 的类型（[[expr.cond]]）。算术类型之间做常用算术转换，所以 `int` 与 `long` 得到 `long`，`short` 与 `char` 先提升为 `int`；两个指针得到复合指针类型；`const char*` 能转换为 `string` 而反过来不行，所以得到 `string`。精确的规则见第 4 段。

### 两个辅助记号

¶3 定义了几个说明用的记号，`common_type` 用到其中两个：

- *CREF*`(A)` 是 `add_lvalue_reference_t<const remove_reference_t<A>>`，对普通类型 `A` 就是 `const A&`。
- *COND-RES*`(X, Y)` 是 `decltype(false ? declval<X(&)()>()() : declval<Y(&)()>()())`。

*COND-RES* 的写法看起来绕。`declval<X(&)()>()` 得到一个返回 `X` 的函数，再调用它一次，得到的表达式类型正好是 `X`，值类别也和 `X` 对应：`X` 是左值引用时是左值，是右值引用时是 xvalue，不是引用时是纯右值。直接写 `declval<X>()` 得不到纯右值，因为 `declval` 总是返回引用。

### 求解步骤

¶4 按实参个数分情况：

- (4.1) 没有实参时，没有 `type`。
- (4.2) 一个实参 `T0` 时，结果等于 `common_type_t<T0, T0>`。所以 `common_type_t<const int>` 是 `int`。
- (4.3) 两个实参 `T1`、`T2` 时，令 `D1`、`D2` 为它们的 `decay_t`，见下面四步。
- (4.4) 三个及以上时，先求 `C = common_type_t<T1, T2>`，再求 `common_type_t<C, R...>`，即从左到右两两折叠。任何一步没有结果，整体就没有 `type`。

两个实参的情况依次尝试：

1. (4.3.1) 如果 `T1` 或 `T2` 与它的退化类型不同，结果就是 `common_type_t<D1, D2>`。也就是先退化再递归，这样用户只需要为退化后的类型写特化。
2. (4.3.2) 如果存在用户特化 `common_type<D1, D2>`，直接用它，下面两步不适用（注 4）。
3. (4.3.3) 否则，如果 `decay_t<decltype(false ? declval<D1>() : declval<D2>())>` 是合法类型，它就是结果。
4. (4.3.4) 否则，如果 *COND-RES*`(`*CREF*`(D1),` *CREF*`(D2))` 是合法类型，结果是它的 `decay_t`。也就是用 `const D1&` 和 `const D2&` 再试一次条件运算符。

第 3 步用的 `declval<D1>()` 是 xvalue。有些类型只能从 const 左值转换，从右值转换不可行，第 3 步失败后由第 4 步补上：

```cpp run title="common-type-cref.cpp" ok
#include <type_traits>
#include <utility>

struct A {};
struct B {
  B(const A&);
  B(A&&) = delete;  // 不能从右值 A 转换
};

template<class T, class U>
concept HasCond = requires {
  false ? std::declval<T>() : std::declval<U>();
};

static_assert(!HasCond<A, B>);                // 第 3 步失败
static_assert( HasCond<const A&, const B&>);  // 第 4 步成功
static_assert(std::is_same_v<std::common_type_t<A, B>, B>);

int main() {}
```

### 用户特化

`common_type` 是 [[type.traits]] 禁止特化规则的例外之一。第 5 段允许程序为两个实参的 `common_type<T1, T2>` 写特化，条件是：

1. `T1` 和 `T2` 都是退化后的类型，即 `is_same_v<T1, decay_t<T1>>` 为真。为 `const X&` 写的特化永远不会被用到，因为第 1 步会先退化。
2. 如果特化提供了 `type`，它必须是无 cv 的非引用类型，`T1`、`T2` 都能显式转换为它。
3. `common_type_t<T1, T2>` 必须与 `common_type_t<T2, T1>` 相同，所以通常要成对特化。

违反这些条件的程序非良构，但不要求诊断。注 5 说明了需要这种特化的场合：两个类型之间只有显式转换，条件运算符找不到公共类型。

```cpp run title="common-type-spec.cpp" ok
#include <type_traits>

struct Meters { double v; };
struct Feet {
  double v;
  explicit operator Meters() const;
};

template<> struct std::common_type<Meters, Feet> {
  using type = Meters;
};
template<> struct std::common_type<Feet, Meters> {
  using type = Meters;
};

static_assert(std::is_same_v<
    std::common_type_t<const Meters&, Feet>, Meters>);

int main() {}
```

`common_type_t<const Meters&, Feet>` 先退化为 `common_type_t<Meters, Feet>`，再命中特化。标准库自己也这样做：`<chrono>` 为两个 `duration` 特化了 `common_type`。

## `common_reference` {{c++20}}

`common_type` 总是退化，结果不会是引用。范围库还需要回答另一个问题：`int&` 和 `const int&` 有没有一个引用类型能同时绑定两者？答案是 `const int&`。`common_reference`（[[P0898R3]]）回答的就是这个问题，它是概念 `std::common_reference_with` 和 `std::indirectly_readable` 的基础。

```cpp run title="common-reference.cpp" ok
#include <type_traits>
#include <vector>
using namespace std;

struct B {};
struct D : B {};
using VBRef = vector<bool>::reference;

static_assert(is_same_v<common_reference_t<int&, const int&>,
                        const int&>);
static_assert(is_same_v<common_reference_t<int&&, int&>,
                        const int&>);
static_assert(is_same_v<common_reference_t<int&&, int&&>, int&&>);
static_assert(is_same_v<common_reference_t<B&, D&>, B&>);
static_assert(is_same_v<common_reference_t<int&, long&>, long>);
static_assert(is_same_v<common_reference_t<int>, int>);
static_assert(is_same_v<common_reference_t<VBRef, bool&>, bool>);

int main() {}
```

### *COMMON-REF*

¶3 先定义了两个引用类型之间的 *COMMON-REF*`(A, B)`。还要两个记号：*COPYCV*`(FROM, TO)` 是给 `TO` 加上 `FROM` 的顶层 cv；*XREF*`(A)` 是一个别名模板，把 `A` 的 cv 和引用限定加到它的实参上。令 `X`、`Y` 为去掉引用后的 `A`、`B`：

| 情形 | *COMMON-REF*`(A, B)` |
|---|---|
| (3.5) 都是左值引用 | *COND-RES*`(`*COPYCV*`(X, Y)&,` *COPYCV*`(Y, X)&)`，要求它存在且是引用类型 |
| (3.6) 都是右值引用 | 令 `C` 为 `remove_reference_t<COMMON-REF(X&, Y&)>&&`；如果 `A`、`B` 都能转换为 `C`，结果是 `C` |
| (3.7) `A` 是右值引用，`B` 是左值引用 | 令 `D` 为 *COMMON-REF*`(const X&, Y&)`；如果 `A` 能转换为 `D`，结果是 `D` |
| (3.8) `A` 是左值引用，`B` 是右值引用 | *COMMON-REF*`(B, A)` |
| (3.9) 其他 | 非良构 |

两个左值引用时，先把双方的 cv 合并（`int&` 与 `const int&` 都变成 `const int&`），再看条件运算符能否得到一个左值。一个左值引用和一个右值引用时，改用 `const X&`，因为它也能绑定右值。

### 求解步骤

¶6 规定：没有实参时没有 `type`；一个实参时结果就是它本身，不退化，这一点与 `common_type` 不同；三个及以上时与 `common_type` 一样从左到右折叠。两个实参 `T1`、`T2` 时依次尝试：

1. (6.3.1) 如果两者都是引用，*COMMON-REF*`(T1, T2)` 良构，而且 `T1*`、`T2*` 都能转换为结果的指针类型，就用它。
2. (6.3.2) 否则，如果 `basic_common_reference<remove_cvref_t<T1>, remove_cvref_t<T2>, XREF(T1), XREF(T2)>::type` 良构，就用它。这是留给用户的定制点。
3. (6.3.3) 否则，如果 *COND-RES*`(T1, T2)` 良构，就用它。
4. (6.3.4) 否则，如果 `common_type_t<T1, T2>` 良构，就用它。
5. 都不行就没有 `type`。

以 `common_reference_t<int&, long&>` 为例。第 1 步按 (3.5) 求 *COND-RES*`(int&, long&)`：两个不同类型的左值经过常用算术转换，得到 `long` 纯右值，不是引用类型，所以 *COMMON-REF* 非良构。第 2 步没有特化。第 3 步 *COND-RES*`(int&, long&)` 是 `long`，这就是结果。`const long&` 不在任何一步的候选中，而且 `int&` 无法直接绑定到 `long` 对象上，只能绑定到转换出的临时量，算不上公共引用。

### `basic_common_reference`

`basic_common_reference<T, U, TQual, UQual>` 的主模板没有 `type`。第 7 段允许程序偏特化它，这是禁止特化规则的另一个例外。条件与 `common_type` 类似：`T`、`U` 是退化后的类型；如果有 `type`，`TQual<T>` 和 `UQual<U>` 都要能转换为它；交换 `(T, U)` 后结果相同。违反这些条件同样不要求诊断。

`TQual` 和 `UQual` 就是 *XREF*`(T1)` 和 *XREF*`(T2)`，特化通过它们得知原来的实参带着什么 cv 和引用。标准库为 `pair`、`tuple`、`reference_wrapper` 提供了这样的偏特化。`views::zip` 的引用类型是 `tuple<int&, int&>`，值类型是 `tuple<int, int>`，两者能求出公共引用，`zip` 的迭代器才满足 `std::indirectly_readable`：

```cpp run title="zip-common-ref.cpp" ok
#include <ranges>
#include <tuple>
#include <type_traits>
#include <vector>
using namespace std;

using V = vector<int>;
using Zip = decltype(views::zip(declval<V&>(), declval<V&>()));
using Ref = ranges::range_reference_t<Zip>;

static_assert(is_same_v<Ref, tuple<int&, int&>>);
static_assert(is_same_v<
    common_reference_t<Ref&&, tuple<int, int>&>, Ref>);

int main() {}
```

## `underlying_type`

如果 `T` 是枚举类型，`underlying_type<T>::type` 是它的底层类型（[[dcl.enum]]）；否则没有 `type`。C++20 之前对非枚举类型使用它是未定义行为，现在可以用于 SFINAE。

*Mandates* 要求 `T` 不是不完整的枚举类型，也就是底层类型还没确定的枚举。没有固定底层类型的枚举在其定义的右花括号之前是不完整的；带固定底层类型的不透明声明 `enum Fwd : int;` 已经足够。

```cpp run title="underlying-type.cpp" ok
#include <type_traits>

enum Fwd : int;  // 不透明声明，底层类型已确定
static_assert(std::is_same_v<std::underlying_type_t<Fwd>, int>);

template<class T>
concept HasUT = requires { typename std::underlying_type<T>::type; };
static_assert(!HasUT<int>);  // 不是枚举：没有 type

int main() {}
```

## `invoke_result` 与 `apply_result`

`invoke_result<Fn, ArgTypes...>` {{c++17}} 在 *INVOKE*`(declval<Fn>(), declval<ArgTypes>()...)`（[[func.require]]）作为不求值操作数良构时，`type` 是这个表达式的 `decltype`；否则没有 `type`。与 [[meta.rel]] 中的 `is_invocable` 一样，访问检查在无关的语境中进行，只看直接语境；直接语境以外的错误（例如实例化某个函数体时出错）会让程序非良构（注 2）。各类型须是完整类型、`void` 或未知边界的数组（*Preconditions*）。

它取代了 C++17 弃用、C++20 移除的 `result_of<F(Args...)>`。`result_of` 借用函数类型 `F(Args...)` 来表示一次调用，于是 `F` 处在返回类型的位置，不能是函数或数组类型；`Args` 也会像函数形参一样被调整，数组和函数变成指针，顶层 cv 被丢掉。

¶8 的例子覆盖了 *INVOKE* 的各种形式：

```cpp run title="invoke-result.cpp" ok
#include <memory>
#include <type_traits>
using namespace std;

using PF1 = bool  (&)();
using PF2 = short (*)(long);

struct S {
  operator PF2() const;
  double operator()(char, int&);
  void fn(long) const;
  char data;
};

using PMF = void (S::*)(long) const;
using PMD = char S::*;

static_assert(is_same_v<invoke_result_t<S, int>, short>);
static_assert(is_same_v<invoke_result_t<S&, unsigned char, int&>,
                        double>);
static_assert(is_same_v<invoke_result_t<PF1>, bool>);
static_assert(is_same_v<invoke_result_t<PMF, unique_ptr<S>, int>,
                        void>);
static_assert(is_same_v<invoke_result_t<PMD, S>, char&&>);
static_assert(is_same_v<invoke_result_t<PMD, const S*>, const char&>);

int main() {}
```

第一行最值得细看。`declval<int>()` 不是左值，无法绑定 `operator()` 的 `int&` 形参，所以 `operator()` 不可行。`S` 还能通过 `operator PF2() const` 转换为函数指针，这样的转换函数在调用表达式中构成代理调用函数（[[over.call.object]]），最终调用的是 `short(*)(long)`，结果类型为 `short`。

倒数第二行：用右值对象访问数据成员，结果是 xvalue，所以类型是 `char&&`。

`apply_result<Fn, Tuple>` 是 C++23 之后的新措辞。如果 `Tuple` 满足 *tuple-like* 且 *INVOKE*`(declval<Fn>(), ELEMS-OF(Tuple)...)` 良构，`type` 是这个表达式的 `decltype`。*ELEMS-OF* 把 tuple 按 `get<0>`、`get<1>`…… 展开，定义见 [[meta.rel#3]]。本机 libc++ 尚未提供 `apply_result`。

## `unwrap_reference` 与 `unwrap_ref_decay` {{c++20}}

`unwrap_reference<T>` 在 `T` 是 `reference_wrapper<X>` 时给出 `X&`，否则给出 `T`。它不先退化，所以 `unwrap_reference_t<const reference_wrapper<int>>` 仍是 `const reference_wrapper<int>`。

`unwrap_ref_decay<T>` 是 `unwrap_reference_t<decay_t<T>>`，它描述了 `std::make_pair` 和 `std::make_tuple` 的元素类型：实参按值退化，但用 `std::ref` 包装的实参变成引用。

¶2：这两个模板及其 `_t` 别名在包含 `<functional>` 时也可以使用，因为它们和 `reference_wrapper` 关系密切。

!!! impl "libc++ 的 `common_type`"
    Clang 提供内建模板 `__builtin_common_type`，libc++ 在可用时直接使用它。内建接受几个回调模板：一个用于递归查询（这样才能命中用户特化），一个用于包装结果，一个表示没有 `type`。没有这个内建时，libc++ 退回到纯模板实现，代码注释逐条对应第 4 段的各个子项。

## 陷阱

!!! pitfall "`common_type` 不保证无损"
    `common_type_t<int, unsigned>` 是 `unsigned`，负数会变成很大的正数；`common_type_t<long long, double>` 是 `double`，大整数会丢失精度。它复刻的是条件运算符的常用算术转换，不是一个能无损容纳两者的类型。

## 思考题

!!! question "思考题 1"
    `std::common_type_t<int[3], int*>` 与 `std::common_type_t<int(), int(*)()>` 分别是什么？

<details markdown="1">
<summary>答案</summary>

都在第 1 步先退化：`decay_t<int[3]>` 是 `int*`，`decay_t<int()>` 是 `int(*)()`。于是两者分别化为 `common_type_t<int*, int*>` 和 `common_type_t<int(*)(), int(*)()>`，结果是 `int*` 和 `int(*)()`。
</details>

!!! question "思考题 2"
    为什么 `common_reference_t<int&&, int&>` 是 `const int&`，而不是 `int&`？

<details markdown="1">
<summary>答案</summary>

按 (3.8)，*COMMON-REF*`(int&&, int&)` 化为 (3.7) 的情形：令 `D` 为 *COMMON-REF*`(const int&, int&)`。按 (3.5)，双方 cv 合并后都是 `const int&`，条件运算符得到 `const int` 左值，所以 `D` 是 `const int&`。`int&&` 能转换为 `const int&`，于是结果是 `const int&`。

`int&` 不行，因为右值不能绑定到非 const 的左值引用。
</details>

## 速查

| 模板 | `type` | 没有 `type` 的情况 |
|---|---|---|
| `type_identity<T>` {{c++20}} | `T` | |
| `remove_cvref<T>` {{c++20}} | `remove_cv_t<remove_reference_t<T>>` | |
| `decay<T>` | 按值传参后的类型 | |
| `enable_if<B, T>` | `T` | `B` 为假 |
| `conditional<B, T, F>` | `B ? T : F` | |
| `common_type<T...>` | 见第 4 段 | 没有公共类型 |
| `basic_common_reference<T, U, TQ, UQ>` | 主模板没有，供用户偏特化 | 默认 |
| `common_reference<T...>` {{c++20}} | 见第 6 段 | 没有公共引用 |
| `underlying_type<T>` | 枚举的底层类型 | `T` 不是枚举 |
| `invoke_result<Fn, Args...>` {{c++17}} | *INVOKE* 表达式的类型 | 表达式非良构 |
| `apply_result<Fn, Tuple>` | 展开 tuple 后 *INVOKE* 的类型 | 不是 tuple-like 或表达式非良构 |
| `unwrap_reference<T>` {{c++20}} | `reference_wrapper<X>` 变成 `X&`，否则 `T` | |
| `unwrap_ref_decay<T>` {{c++20}} | `unwrap_reference_t<decay_t<T>>` | |
