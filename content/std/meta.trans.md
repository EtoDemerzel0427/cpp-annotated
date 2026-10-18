---
title: 类型间变换
summary: 变换 trait 总则与五组"机械"变换——增删顶层 cv、增删引用（不可引用类型原样返回、遵循引用折叠）、make_signed/make_unsigned（按"对应类型"或"同 sizeof 的最小等级"）、去掉数组维度、增删指针；其余变换见 meta.trans.other
status: draft
covers: meta.trans.general, meta.trans.cv, meta.trans.ref, meta.trans.sign, meta.trans.arr, meta.trans.ptr
related: type.traits, meta.trans.other, basic.type.qualifier, dcl.ref, conv.rank, basic.fundamental, dcl.array, intro.defs, declval
tags: 标准库, type_traits, 类型变换
updated: 2026-10-18
---

[meta.trans] 是 `<type_traits>` 里"类型进、类型出"的那部分。¶1（[meta.trans.general]）：本子条款的模板按预定规则把一个类型变换为另一个类型；¶2：每一个都是 *Cpp17TransformationTrait*（[[type.traits]]）——提供嵌套 `type`，并有对应的 `_t` 别名。

本页覆盖五组"机械"变换，它们的规则都可以用一两句话说清，难点在于**边界类型**：引用、函数类型、数组、`void`。真正有算法的变换（`decay`、`common_type`、`common_reference` 等）见 [[meta.trans.other]]。

## cv 修改（[meta.trans.cv]）

| 模板 | `type` |
|---|---|
| `remove_const<T>` | 去掉**顶层** `const` |
| `remove_volatile<T>` | 去掉顶层 `volatile` |
| `remove_cv<T>` | 去掉顶层 cv |
| `add_const<T>` | `const T` |
| `add_volatile<T>` | `volatile T` |
| `add_cv<T>` | `add_const_t<add_volatile_t<T>>` |

"顶层"（[[g:top-level-cv-qualifiers]]）是关键：`remove_const_t<const int*>` 仍是 `const int*`（`const` 修饰的是被指向的 `int`），`remove_const_t<const int* const>` 才变成 `const int*`。

两个由核心语言带来的特例：

- **数组**：按 [[basic.type.qualifier]]，cv 限定的数组类型就是元素类型被 cv 限定的数组，所以 `remove_const_t<const int[3]>` 是 `int[3]`（[[meta.unary.prop]] ¶7 的例子）；
- **引用与函数类型**不能被 cv 限定（cv 被忽略），所以 `add_const` 的注 1 说：当 `T` 是引用、函数或已有顶层 `const` 的类型时，`const` 无效。`add_const_t<int&>` 仍是 `int&`；`remove_const_t<const int&>` 也仍是 `const int&`——这里的 `const` 不在顶层。想"去掉引用后的 const"请用 `remove_cvref`（[[meta.trans.other]]）。

```cpp run title="cv-mods.cpp" ok
#include <type_traits>
using namespace std;

static_assert(is_same_v<remove_const_t<const volatile int>, volatile int>);
static_assert(is_same_v<remove_const_t<const int*>, const int*>);          // 不是顶层
static_assert(is_same_v<remove_const_t<const int* const>, const int*>);
static_assert(is_same_v<remove_const_t<const int&>, const int&>);          // 引用没有顶层 cv
static_assert(is_same_v<remove_const_t<const int[3]>, int[3]>);            // 数组的 cv 即元素的 cv
static_assert(is_same_v<add_const_t<int&>, int&>);                         // 对引用无效
static_assert(is_same_v<add_const_t<void()>, void()>);                     // 对函数类型无效
static_assert(is_same_v<add_cv_t<int>, const volatile int>);

int main() {}
```

## 引用修改（[meta.trans.ref]）

| 模板 | `type` |
|---|---|
| `remove_reference<T>` | 若 `T` 是"对 `T1` 的引用"，为 `T1`；否则 `T` |
| `add_lvalue_reference<T>` | 若 `T` 可引用（[[g:referenceable-type]]），为 `T&`；否则 `T` |
| `add_rvalue_reference<T>` | 若 `T` 可引用，为 `T&&`；否则 `T` |

两条注释都说："本规则反映了**引用折叠**的语义"（[[dcl.ref]]，[[g:reference-collapsing]]）：

- `add_lvalue_reference_t<int&&>` 是 `int&`（`&&` + `&` → `&`）；
- `add_rvalue_reference_t<int&>` 是 `int&`——注 2 特意强调：对左值引用类型 `T1&`，`add_rvalue_reference_t` **不是**右值引用。

**不可引用类型**（`void`、带 cv/引用限定的函数类型）原样返回，而不是非良构——这让它们可以安全地用在 SFINAE 之外的地方。最著名的用户就是 `declval`：

```cpp
template<class T> add_rvalue_reference_t<T> declval() noexcept;   // [declval]
```

于是 `declval<int>()` 的类型是 `int&&`（xvalue），`declval<int&>()` 是 `int&`（lvalue），`declval<void>()` 的类型是 `void`——正是 [[meta.unary.prop]] 与 [[meta.rel]] 中各种"假想表达式"所需要的值类别。

```cpp run title="ref-mods.cpp" ok
#include <type_traits>
#include <utility>
using namespace std;

static_assert(is_same_v<add_lvalue_reference_t<int&&>, int&>);     // 引用折叠
static_assert(is_same_v<add_rvalue_reference_t<int&>, int&>);      // 注 2
static_assert(is_same_v<add_lvalue_reference_t<void>, void>);      // 不可引用：原样返回
static_assert(is_same_v<add_lvalue_reference_t<void() &>, void() &>);
static_assert(is_same_v<decltype(declval<int>()), int&&>);
static_assert(is_same_v<decltype(declval<void>()), void>);

int main() {}
```

## 符号修改（[meta.trans.sign]）

`make_signed<T>` 的规则分三档（`make_unsigned` 对称）：

1. `T` 已是（可能 cv 限定的）**有符号整数类型** → `T` 本身；
2. `T` 是（可能 cv 限定的）**无符号整数类型** → **对应的**有符号整数类型（[[basic.fundamental]]），保留 cv；
3. 否则（`char`、`wchar_t`、`char8_t`、`char16_t`、`char32_t`、枚举）→ **满足 `sizeof(T) == sizeof(type)` 的等级（[[conv.rank]]）最小的**有符号整数类型，保留 cv。

*Mandates*：`T` 是除 *cv* `bool` 之外的整型或枚举类型。违反时非良构。

第三档的"等级最小"有一个常被忽视的后果：

```cpp run title="make-signed.cpp" ok
#include <type_traits>
using namespace std;

enum EL : long long {};

static_assert(is_same_v<make_signed_t<char>, signed char>);       // char 不是"有符号整数类型"，走第三档
static_assert(is_same_v<make_unsigned_t<char>, unsigned char>);
static_assert(is_same_v<make_signed_t<char16_t>, short>);
static_assert(is_same_v<make_signed_t<const volatile unsigned char>, const volatile signed char>);
static_assert(is_same_v<make_unsigned_t<long long>, unsigned long long>);   // 第二档：对应类型
static_assert(is_same_v<make_unsigned_t<EL>, unsigned long>);              // 第三档：LP64 上 unsigned long 等级更小！

int main() {}
```

`EL` 的底层类型是 `long long`，但 `make_unsigned_t<EL>` 在 LP64 平台上是 `unsigned long`——因为第三档只看 `sizeof`，而 `unsigned long` 与 `unsigned long long` 一样是 8 字节、等级更低。如果你想要"底层类型的无符号版本"，应写 `make_unsigned_t<underlying_type_t<E>>`。

注意 `char` 走的是第三档：按 [[basic.fundamental]]，`char` 与 `signed char`、`unsigned char` 是三个不同类型，`char` 既不属于"有符号整数类型"也不属于"无符号整数类型"（它是**普通字符类型**）。

!!! lawyer "底层类型为 `bool` 的枚举"
    *Mandates* 只排除了 *cv* `bool` 本身。`enum class EB : bool {};` 是枚举类型，按条文字面似乎满足 *Mandates*，第三档会给出 `signed char`。但 Clang 的内建 `__make_signed` 拒绝它："'make_signed' is only compatible with non-bool integers and enum types, but was given 'EB' whose underlying type is 'bool'"。这是实现比条文更严格的一处。

!!! impl "libc++：内建优先，退路是一张类型表"
    libc++ 在有 `__make_signed`/`__make_unsigned` 内建时直接使用它们；否则退回一张按 `sizeof` 查找的类型列表（`signed char, short, int, long, long long, __int128`）加上一组显式特化——这张表的顺序本身就编码了"等级最小优先"。本地测试中 `make_unsigned_t<__int128>` 为 `unsigned __int128`，`make_signed_t<unsigned _BitInt(7)>` 为 `_BitInt(7)`：扩展整数类型同样被支持。

## 数组修改（[meta.trans.arr]）

| 模板 | `type` |
|---|---|
| `remove_extent<T>` | 若 `T` 是"`U` 的数组"，为 `U`；否则 `T` |
| `remove_all_extents<T>` | 若 `T` 是"`U` 的多维数组"，为 `U`；否则 `T` |

注 1：多维数组只去掉第一维；"`const U` 的数组"去掉维度后得到 `const U`。¶2、¶3 的例子覆盖了未知边界数组：`remove_extent_t<int[][3]>` 是 `int[3]`，`remove_all_extents_t<int[][3]>` 是 `int`。

`remove_all_extents_t` 在本章中出现得极其频繁：表 54 的大量前置条件写作"`remove_all_extents_t<T>` 须为完整类型"，`is_destructible`、`is_trivially_destructible` 的定义也用它取元素类型。

## 指针修改（[meta.trans.ptr]）

| 模板 | `type` |
|---|---|
| `remove_pointer<T>` | 若 `T` 是"（可能 cv 限定的）指向 `T1` 的指针"，为 `T1`；否则 `T` |
| `add_pointer<T>` | 若 `T` 可引用或是 *cv* `void`，为 `remove_reference_t<T>*`；否则 `T` |

- `remove_pointer` 会穿过**指针自身**的 cv：`remove_pointer_t<int* const>` 是 `int`；它只去一层：`remove_pointer_t<int**>` 是 `int*`；它不认成员指针。
- `add_pointer` 先去掉引用：`add_pointer_t<int&&>` 是 `int*`（不存在"指向引用的指针"）；对函数类型得到函数指针，对数组得到数组指针；对不可引用的函数类型（如 `void() const`）原样返回——那种类型不存在指针。

```cpp run title="arr-ptr-mods.cpp" ok
#include <type_traits>
using namespace std;

static_assert(is_same_v<remove_extent_t<const int[2][3]>, const int[3]>);
static_assert(is_same_v<remove_all_extents_t<int[][3]>, int>);
static_assert(is_same_v<remove_pointer_t<int* const>, int>);
static_assert(is_same_v<remove_pointer_t<int**>, int*>);
static_assert(is_same_v<add_pointer_t<int&&>, int*>);
static_assert(is_same_v<add_pointer_t<int[3]>, int (*)[3]>);
static_assert(is_same_v<add_pointer_t<int(int)>, int (*)(int)>);
static_assert(is_same_v<add_pointer_t<void() const>, void() const>);   // 不可引用、不是 void：原样
static_assert(is_same_v<add_pointer_t<const void>, const void*>);

int main() {}
```

## 实现视角

!!! impl "变换 trait 也是内建"
    libc++ 中这五组变换全部转发给 Clang 的**类型变换内建**：`__remove_cv(_Tp)`、`__remove_reference_t(_Tp)`、`__add_lvalue_reference(_Tp)`、`__add_pointer(_Tp)`、`__remove_extent(_Tp)`、`__make_signed(_Tp)` 等。值得注意的是 `_t` 别名的写法：

    ```cpp
    template <class _Tp>
    struct _LIBCPP_NO_SPECIALIZATIONS remove_cv {
      using type _LIBCPP_NODEBUG = __remove_cv(_Tp);
    };
    template <class _Tp>
    using __remove_cv_t _LIBCPP_NODEBUG = __remove_cv(_Tp);   // 不经过 remove_cv<T>
    template <class _Tp>
    using remove_cv_t = __remove_cv_t<_Tp>;
    ```

    `remove_cv_t<T>` **不实例化** `remove_cv<T>` 这个类模板，而是直接调用内建——对大量使用 `_t` 别名的泛型代码，这省下了成千上万次类模板实例化。标准只要求 `remove_cv_t<T>` 与 `remove_cv<T>::type` 指称同一类型，并不要求经过类模板，所以这完全合法。（用 GCC 编译 libc++ 时走的是 `typename remove_cv<_Tp>::type` 分支。）

## 陷阱

!!! pitfall "`remove_const` 对引用无效"
    `template<class T> void f(T&& x) { using U = remove_const_t<T>; ... }` 中，若实参是 `const int` 左值，`T` 是 `const int&`，`U` 仍是 `const int&`。应先 `remove_reference_t` 再 `remove_const_t`，或直接用 `remove_cvref_t`。

!!! pitfall "`make_unsigned` 用于枚举时不一定得到底层类型的无符号版"
    见上文 `EL` 的例子。凡是要和底层类型做位运算、`memcpy` 的地方，写 `make_unsigned_t<underlying_type_t<E>>`。

## 思考题

!!! question "思考题"
    `std::add_pointer_t<std::remove_reference_t<int(&)(int)>>`、`std::add_pointer_t<int(&)(int)>`、`std::remove_pointer_t<void (S::*)()>` 分别是什么类型？

<details markdown="1">
<summary>展开查看答案与解析</summary>

前两个都是 `int (*)(int)`：`add_pointer` 自己就会先 `remove_reference_t`，再对函数类型加指针。第三个是 `void (S::*)()` 本身：`remove_pointer` 只认"指向 `T1` 的指针"，成员指针不是指针类型（[[basic.compound]]），原样返回。
</details>

## 小结

| 组 | 规则要点 | 边界行为 |
|---|---|---|
| cv | 只动顶层 | 数组 cv = 元素 cv；引用、函数类型无顶层 cv |
| 引用 | 遵循引用折叠 | 不可引用类型原样返回；`declval` 依赖于此 |
| 符号 | 已是 → 本身；有对应 → 对应；否则同 `sizeof` 最小等级 | `char` 走第三档；枚举可能得到"意外"的类型；`bool` 非良构 |
| 数组 | `remove_extent` 一层，`remove_all_extents` 全部 | 支持未知边界 |
| 指针 | `remove_pointer` 穿过指针自身 cv；`add_pointer` 先去引用 | 成员指针不是指针；不可引用函数类型原样 |
