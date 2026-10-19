---
title: 类型间变换
summary: 把一个类型变成另一个类型的基础 trait：增删顶层 cv、增删引用、改变整数符号、去掉数组维度、增删指针。
status: draft
covers: meta.trans.general, meta.trans.cv, meta.trans.ref, meta.trans.sign, meta.trans.arr, meta.trans.ptr
related: type.traits, meta.trans.other, basic.type.qualifier, dcl.ref, conv.rank, basic.fundamental, dcl.array, intro.defs, declval
tags: 标准库, type_traits, 类型变换
updated: 2026-10-19
---

!!! tldr
    - `remove_const` 等只去掉顶层 cv：`remove_const_t<const int*>` 不变，`remove_const_t<const int&>` 也不变。
    - `add_lvalue_reference` 和 `add_rvalue_reference` 遵循引用折叠，对 `void` 这类不能被引用的类型原样返回，`declval` 正是靠这一点工作的。
    - `make_unsigned` 对枚举和字符类型按 `sizeof` 选等级最小的整数类型，所以底层类型为 `long long` 的枚举在 LP64 上得到 `unsigned long`。
    - `remove_pointer` 不认成员指针；`add_pointer` 先去掉引用再加指针。

[meta.trans] 中的模板接收一个类型，按固定规则产生另一个类型（[meta.trans.general] 第 1 段）。每个模板都是一个**变换特征**（*Cpp17TransformationTrait*，[[meta.rqmts]]）：结果放在嵌套的 `type` 里，另有 `_t` 别名直接给出结果，如 `remove_const_t<T>` 就是 `typename remove_const<T>::type`。

本页讲五组规则简单的变换，难点只在引用、函数类型、数组、`void` 这些边界类型上。`decay`、`common_type`、`invoke_result` 等更复杂的变换见 [[meta.trans.other]]。

## cv 修改 [meta.trans.cv]

```cpp run title="cv-mods.cpp" ok
#include <type_traits>
using namespace std;

static_assert(is_same_v<remove_const_t<const volatile int>, volatile int>);
static_assert(is_same_v<remove_const_t<const int*>, const int*>);
static_assert(is_same_v<remove_const_t<const int* const>, const int*>);
static_assert(is_same_v<remove_const_t<const int&>, const int&>);
static_assert(is_same_v<remove_const_t<const int[3]>, int[3]>);
static_assert(is_same_v<add_const_t<int&>, int&>);
static_assert(is_same_v<add_const_t<void()>, void()>);
static_assert(is_same_v<add_cv_t<int>, const volatile int>);

int main() {}
```

`remove_const`、`remove_volatile`、`remove_cv` 去掉的是[[g:top-level-cv-qualifiers|顶层 cv 限定]]，也就是直接修饰这个类型本身的 cv。`const int*` 中的 `const` 修饰被指向的 `int`，不在顶层，所以 `remove_const_t<const int*>` 不变；`const int* const` 末尾那个 `const` 修饰指针本身，才会被去掉。

引用本身不能有 cv 限定，`const int&` 中的 `const` 属于被引用的 `int`，同样不在顶层。所以对引用类型，`remove_const` 什么也不做。想去掉引用后面的 cv，要先 `remove_reference_t`，或者直接用 `remove_cvref_t`（[[meta.trans.other]]）。

数组是另一个特例。按 [[basic.type.qualifier]]，cv 限定的数组类型就是元素带 cv 的数组，所以 `const int[3]` 的顶层 cv 就是元素的 cv，`remove_const_t<const int[3]>` 是 `int[3]`。

`add_const<T>` 给出 `const T`，`add_volatile`、`add_cv` 同理。引用和函数类型上的 cv 会被忽略，所以 `add_const_t<int&>` 仍是 `int&`（注 1、注 2）。

## 引用修改 [meta.trans.ref]

```cpp run title="ref-mods.cpp" ok
#include <type_traits>
#include <utility>
using namespace std;

static_assert(is_same_v<remove_reference_t<int&&>, int>);
static_assert(is_same_v<add_lvalue_reference_t<int&&>, int&>);
static_assert(is_same_v<add_rvalue_reference_t<int&>, int&>);
static_assert(is_same_v<add_lvalue_reference_t<void>, void>);
static_assert(is_same_v<add_lvalue_reference_t<void() &>, void() &>);
static_assert(is_same_v<decltype(declval<int>()), int&&>);
static_assert(is_same_v<decltype(declval<void>()), void>);

int main() {}
```

`remove_reference<T>` 在 `T` 是引用时给出被引用的类型，否则给出 `T`。

`add_lvalue_reference<T>` 给出 `T&`，`add_rvalue_reference<T>` 给出 `T&&`，结果遵循[[g:reference-collapsing|引用折叠]]（[[dcl.ref]]）：只要有一方是左值引用，结果就是左值引用。所以 `add_rvalue_reference_t<int&>` 是 `int&`，不是右值引用（注 2）。

这两个模板只对[[g:referenceable-type|可引用类型]]加引用。不能被引用的类型有 `void` 和带 cv 或引用限定的函数类型（如 `void() const`，只能出现在成员函数的声明里）。对它们，结果是 `T` 本身，而不是编译错误。

`declval` 的声明就利用了这一点：

```cpp
template<class T> add_rvalue_reference_t<T> declval() noexcept;
```

所以 `declval<int>()` 的类型是 `int&&`，是 xvalue；`declval<int&>()` 的类型是 `int&`，是左值；`declval<void>()` 的类型是 `void`，仍然可以写。[[meta.unary.prop]] 和 [[meta.rel]] 中用 `declval` 构造的假想表达式都依赖这些值类别。

## 符号修改 [meta.trans.sign]

`make_signed<T>` 按三条规则依次判断，`make_unsigned` 与之对称：

1. 如果 `T` 已经是有符号整数类型（可能带 cv），结果是 `T` 本身。
2. 如果 `T` 是无符号整数类型，结果是对应的有符号整数类型（[[basic.fundamental]]），保留 cv。
3. 否则，结果是满足 `sizeof(T) == sizeof(type)` 的、[[conv.rank|整数转换等级]]最小的有符号整数类型，保留 cv。

`T` 必须是整型或枚举类型，且不能是 `bool`，否则程序非良构（*Mandates*）。

```cpp run title="make-signed.cpp" ok
#include <type_traits>
using namespace std;

enum EL : long long {};
using CVU = const volatile unsigned char;

static_assert(is_same_v<make_signed_t<char>, signed char>);
static_assert(is_same_v<make_unsigned_t<char>, unsigned char>);
static_assert(is_same_v<make_signed_t<char16_t>, short>);
static_assert(is_same_v<make_signed_t<CVU>,
                        const volatile signed char>);
static_assert(is_same_v<make_unsigned_t<long long>,
                        unsigned long long>);
static_assert(is_same_v<make_unsigned_t<EL>, unsigned long>);  // LP64

int main() {}
```

第三条规则适用于字符类型和枚举。`char` 与 `signed char`、`unsigned char` 是三个不同的类型，它既不算有符号整数类型，也不算无符号整数类型，所以按第三条处理，得到同样大小的 `signed char`。

枚举的结果可能出乎意料。`EL` 的底层类型是 `long long`，但第三条只看大小：LP64 平台上 `unsigned long` 与 `unsigned long long` 都是 8 字节，前者等级更低，所以 `make_unsigned_t<EL>` 是 `unsigned long`。要得到底层类型的无符号版本，应写 `make_unsigned_t<underlying_type_t<E>>`。

!!! lawyer "底层类型为 `bool` 的枚举"
    *Mandates* 只排除了 `bool` 本身。`enum class EB : bool {};` 是枚举类型，按条文字面似乎可以用，第三条规则会给出 `signed char`。Clang 的内建 `__make_signed` 却拒绝它，报告 `EB` 的底层类型是 `bool`。这是实现比条文更严格的一处。

!!! impl "扩展整数类型"
    libc++ 直接使用 Clang 的内建 `__make_signed`、`__make_unsigned`。本机测试中，`make_unsigned_t<__int128>` 是 `unsigned __int128`，`make_signed_t<unsigned _BitInt(7)>` 是 `_BitInt(7)`，扩展整数类型也能正确处理。

## 数组修改 [meta.trans.arr]

`remove_extent<T>` 在 `T` 是 `U` 的数组时给出 `U`，否则给出 `T`。多维数组只去掉第一维；`const U` 的数组去掉维度后得到 `const U`（注 1）。`remove_all_extents<T>` 去掉全部维度。两者都支持未知边界的数组：

```cpp run title="extents.cpp" ok
#include <type_traits>
using namespace std;

static_assert(is_same_v<remove_extent_t<int>, int>);
static_assert(is_same_v<remove_extent_t<int[2][3]>, int[3]>);
static_assert(is_same_v<remove_extent_t<int[][3]>, int[3]>);
static_assert(is_same_v<remove_extent_t<const int[2][3]>,
                        const int[3]>);
static_assert(is_same_v<remove_all_extents_t<int[][3]>, int>);

int main() {}
```

[meta.trans.arr] 第 2、3 段的两个例子就是这些断言。`remove_all_extents_t` 在 [[meta.unary.prop]] 中常用来取数组的元素类型，例如前置条件"`remove_all_extents_t<T>` 是完整类型"。

## 指针修改 [meta.trans.ptr]

```cpp run title="ptr-mods.cpp" ok
#include <type_traits>
using namespace std;

struct S;
static_assert(is_same_v<remove_pointer_t<int* const>, int>);
static_assert(is_same_v<remove_pointer_t<int**>, int*>);
static_assert(is_same_v<remove_pointer_t<void (S::*)()>,
                        void (S::*)()>);
static_assert(is_same_v<add_pointer_t<int&&>, int*>);
static_assert(is_same_v<add_pointer_t<int[3]>, int (*)[3]>);
static_assert(is_same_v<add_pointer_t<int(int)>, int (*)(int)>);
static_assert(is_same_v<add_pointer_t<void() const>, void() const>);
static_assert(is_same_v<add_pointer_t<const void>, const void*>);

int main() {}
```

`remove_pointer<T>` 在 `T` 是指向 `T1` 的指针（指针本身可以带 cv）时给出 `T1`，否则给出 `T`。它只去掉一层，而且不认成员指针，因为成员指针不是指针类型（[[basic.compound]]）。

`add_pointer<T>` 在 `T` 可引用或是 `void` 时给出 `remove_reference_t<T>*`，否则给出 `T`。不存在指向引用的指针，所以它先去掉引用。对函数类型得到函数指针，对数组得到指向数组的指针。`void() const` 这样的函数类型既不可引用也不是 `void`，没有对应的指针类型，原样返回。

!!! impl "`_t` 别名不实例化类模板"
    libc++ 把这些变换都转发给 Clang 的类型变换内建，如 `__remove_cv(T)`、`__add_pointer(T)`。它的 `remove_cv_t<T>` 直接定义为 `__remove_cv(T)`，并不经过 `remove_cv<T>::type`。标准只要求两者是同一类型，不要求 `_t` 别名实例化类模板。大量使用 `_t` 别名的泛型代码因此省掉了许多类模板实例化。

## 陷阱

!!! pitfall "转发引用上的 `remove_const`"
    在 `template<class T> void f(T&& x)` 中，如果实参是 `const int` 左值，`T` 推导为 `const int&`，`remove_const_t<T>` 仍是 `const int&`。应该用 `remove_cvref_t<T>`。

## 思考题

!!! question "思考题"
    `std::add_pointer_t<int(&)(int)>` 和 `std::remove_pointer_t<int (*const*)(int)>` 分别是什么类型？

<details markdown="1">
<summary>答案</summary>

第一个是 `int (*)(int)`：`add_pointer` 先去掉引用得到函数类型 `int(int)`，再加指针。

第二个是 `int (*const)(int)`：原类型是指向 const 函数指针的指针，`remove_pointer` 只去掉最外层的指针，留下被指向的类型，它本身带着顶层 `const`。
</details>

## 小结

| 组 | 规则 | 边界情况 |
|---|---|---|
| cv | 只动顶层 cv | 数组的 cv 就是元素的 cv；引用、函数类型没有顶层 cv |
| 引用 | 遵循引用折叠 | 不可引用的类型原样返回 |
| 符号 | 已是则不变；有对应类型取对应类型；否则取同大小的最小等级 | `char` 和枚举走第三条；`bool` 非良构 |
| 数组 | `remove_extent` 去一层，`remove_all_extents` 全去 | 支持未知边界 |
| 指针 | `remove_pointer` 去一层；`add_pointer` 先去引用 | 成员指针不是指针；不可引用的函数类型原样返回 |
