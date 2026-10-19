---
title: 反射
summary: C++26 静态反射库 <meta> 的总览：std::meta::info 与各组函数、总则、把编译期数据提升到静态存储的 define_static_* 函数、meta::exception 错误模型和运算符枚举。
status: draft
covers: meta.syn, meta.string.literal, meta.define.static, meta.reflection.exception, meta.reflection.operators
since: c++26
papers: P2996R13, P3394R4, P3068R6
related: meta, expr.reflect, basic.splice, expr.prim.splice, expr.const.reflect, basic.fundamental, meta.reflection.queries, meta.reflection.extract, meta.reflection.traits, temp.param, intro.object
tags: 反射, C++26, 标准库, consteval
updated: 2026-10-19
---

!!! tldr
    - 反射运算符 `^^` 把一个程序构造（类型、变量、函数、命名空间……）变成 `std::meta::info` 类型的值；`<meta>` 中的 `consteval` 函数对这个值做查询和变换；拼接 `[: r :]` 再把值变回程序构造。
    - `info` 是标量类型，可以复制、比较、作模板实参，但只能在编译期使用。
    - 常量求值中分配的内存必须在求值结束前释放，所以 `members_of` 返回的 `vector` 带不出编译期。`define_static_array`、`define_static_string` 把数据复制进静态存储，结果可以在编译期之外使用。
    - 反射函数在前置条件不满足时抛出 `std::meta::exception`，它可以在常量求值中被捕获；未被捕获时编译失败，诊断中带着错误信息。
    - 返回 `string_view` 的反射函数，结果都以 `'\0'` 结尾，可以直接当 C 字符串用。

!!! warning "本页示例未经本机验证"
    本机 Clang 23 加 libc++ 尚不支持 C++26 静态反射：没有 `^^` 运算符，也没有 `<meta>` 头文件。本页和 [[meta.reflection.queries]]、[[meta.reflection.extract]]、[[meta.reflection.traits]] 中的代码依据当前草案和标准自带的例子编写，没有编译验证，所以不标判定。

## 一个例子：枚举值转字符串

```cpp
#include <meta>
#include <string_view>

template<class E>
  requires std::is_enum_v<E>
constexpr std::string_view to_string(E value) {
  template for (constexpr auto e :
      std::define_static_array(std::meta::enumerators_of(^^E))) {
    if (value == [: e :])
      return std::meta::identifier_of(e);
  }
  return "<unnamed>";
}
```

这个函数用到了反射的全部三个环节：

1. `^^E` 是反射运算符（[[expr.reflect]]），得到代表枚举类型 `E` 的值，类型为 `std::meta::info`。
2. `enumerators_of` 和 `identifier_of` 是 `<meta>` 中的库函数，分别给出枚举的全部枚举项和一个枚举项的名字。
3. `[: e :]` 是拼接（[[basic.splice]]、[[expr.prim.splice]]），把反射 `e` 变回它代表的枚举项，可以和 `value` 比较。

`enumerators_of` 返回 `std::vector<info>`，而 `vector` 在常量求值中分配的内存必须在求值结束前释放，不能作为展开语句（[[stmt.expand]]）遍历的对象。`define_static_array` 把它复制进一个静态存储的数组，返回指向它的 `span`。这是使用 `<meta>` 时最常见的写法，原理见下文的提升到静态存储一节。

## `std::meta::info`

```cpp
namespace std::meta {
  using info = decltype(^^::);
}
```

`info` 定义为 `^^::`（全局命名空间的反射）的类型。它是一个基本类型，属于标量类型（[[basic.fundamental#17]]）。`info` 的值称为[[g:reflection|反射]]，其中有唯一的空反射，其他每个反射都代表一个程序构造：类型、变量、函数、命名空间、模板、枚举项、基类关系等。

因为是标量类型，`info` 值可以复制、用 `==` 比较、作为常量模板实参。但它是[[g:consteval-only-value|仅限 consteval 的值]]，只能存在于编译期，不能流入运行时的代码。

## 函数分组

`<meta>` 的概要（[meta.syn]）按子条款给函数分组。本站把它们分到四页：

| 子条款 | 代表函数 | 作用 | 页面 |
|---|---|---|---|
| [meta.string.literal] | `is_string_literal` | 判断指针是否指向字符串字面量 | 本页 |
| [meta.define.static] | `define_static_string`、`define_static_array`、`define_static_object` | 把编译期数据提升到静态存储 | 本页 |
| [meta.reflection.exception] | `meta::exception` | 反射函数的错误报告 | 本页 |
| [meta.reflection.operators] | `operators`、`operator_of`、`symbol_of` | 识别运算符函数 | 本页 |
| [meta.reflection.names] | `identifier_of`、`display_string_of`、`source_location_of` | 名字与位置 | [[meta.reflection.queries]] |
| [meta.reflection.queries] | `type_of`、`parent_of`、`dealias`、`is_*`、`has_*` | 查询单个反射 | [[meta.reflection.queries]] |
| [meta.reflection.scope] | `current_function`、`current_class` | 调用发生在哪里 | [[meta.reflection.queries]] |
| [meta.reflection.access.context] 等 | `access_context`、`is_accessible` | 访问控制 | [[meta.reflection.queries]] |
| [meta.reflection.member.queries] | `members_of`、`bases_of`、`enumerators_of` | 列出成员 | [[meta.reflection.queries]] |
| [meta.reflection.layout] | `offset_of`、`size_of`、`alignment_of` | 布局 | [[meta.reflection.queries]] |
| [meta.reflection.annotation] | `annotations_of` | 读取注解 `[[=...]]` | [[meta.reflection.queries]] |
| [meta.reflection.extract] | `extract<T>` | 从反射取回值 | [[meta.reflection.extract]] |
| [meta.reflection.substitute] | `can_substitute`、`substitute` | 用反射作模板实参 | [[meta.reflection.extract]] |
| [meta.reflection.result] | `reflect_constant`、`reflect_object` | 从值得到反射 | [[meta.reflection.extract]] |
| [meta.reflection.define.aggregate] | `data_member_spec`、`define_aggregate` | 生成类定义 | [[meta.reflection.extract]] |
| [meta.reflection.traits] | `is_trivially_copyable_type`、`remove_cvref` | `<type_traits>` 的反射版本 | [[meta.reflection.traits]] |

## 总则

[meta.syn] 的五段适用于 `<meta>` 中的所有函数。

¶1 除非另有规定，这些函数和函数模板特化都是可寻址函数（[[namespace.std]]），可以取地址，例如把 `std::meta::is_public` 作为谓词传给算法。[meta.reflection.scope] 中的函数和 `access_context::current` 是明确规定的例外，因为它们的结果取决于调用出现的位置。

¶2 当这些函数抛出 `meta::exception` 时，异常的 `from()` 是代表抛出它的函数的反射，`where()` 是调用那个函数的源码位置。

¶3 把一个代表标准没有规定的构造的反射传给 `std::meta` 中的函数，行为由实现定义。`info` 可以代表实现特有的构造（注 1）。注 2 指出一个副作用：许多函数的结果取决于类类型是否完整，所以只要 `dealias(r)` 代表一个有可达定义的类模板特化，这个特化就会被隐式实例化。例如 `size_of(^^X<int>)` 会实例化 `X<int>`。

¶4 返回 `string_view` 或 `u8string_view` 的函数，结果 `V` 满足 `V.data()[V.size()] == '\0'`。这些字符是静态存储期的、[[g:potentially-non-unique-object|可能不唯一的]]对象，可用于常量表达式，但指向它们的指针不能作为指针类型常量模板形参的实参（[[temp.arg.nontype]]）。所以 `identifier_of(r).data()` 可以直接当 C 字符串使用。

¶5 本条款中用 `^^E` 表示代表源码构造 `E` 的反射，只是叙述上的约定。

## 提升到静态存储

¶1（[meta.define.static]）：本子条款的函数把编译期存储提升为静态存储。

常量求值中用 `new` 分配的内存，包括 `std::vector`、`std::string` 的缓冲区，必须在这次求值结束前释放，这叫[[g:transient-allocation|瞬时分配]]（[[expr.const]]）。所以 `constexpr std::vector<info> v = members_of(...);` 非良构，反射函数返回的 `vector` 无法直接带出常量求值。

解决办法是把数据复制进一个[[g:template-parameter-object|模板形参对象]]。模板形参对象本来就具有静态存储期，而且可用于常量表达式，正好满足需要。

```cpp
#include <meta>
#include <string>

consteval const char* make_name(int n) {
  std::string s = "field_";  // 瞬时分配
  s += static_cast<char>('0' + n);
  return std::define_static_string(s);
}
constexpr const char* name = make_name(3);  // "field_3"
static_assert(!std::is_string_literal(name));
```

`s` 的缓冲区在 `make_name` 返回前就释放了，`define_static_string` 返回的指针指向一个内容相同的模板形参对象，所以可以存进 `constexpr` 变量。

### 五个函数

| 函数 | 结果 |
|---|---|
| `meta::reflect_constant_string(r)` | 代表模板形参对象 `const CharT[N+1]` 的反射，末尾补 `CharT()` |
| `meta::reflect_constant_array(r)` | 代表模板形参对象 `const T[N]` 的反射；空范围时是 `const array<T, 0>` |
| `define_static_string(r)` | 指向上述字符串对象的 `const CharT*` |
| `define_static_array(r)` | 指向上述数组的 `span<const T, N>` 或 `span<const T>` |
| `define_static_object(t)` | 指向与 `t` 等价的静态对象的 `const remove_cvref_t<T>*` |

`reflect_constant_*` 返回反射，可以继续交给其他反射函数或拼接；`define_static_*` 返回普通的指针或 `span`，可以在不涉及反射的代码中直接使用。后者都是用前者加上 `meta::extract` 定义的。

`reflect_constant_string`（第 2–7 段）要求元素类型 `CharT` 是字符类型（*Mandates*）。如果 `r` 引用的是一个字符串字面量对象，复制时不包括它末尾的空字符，避免结果中出现两个 `'\0'`。结果对象可能不唯一：内容相同的两次调用可能得到同一个对象，也可能不是（注 1）。

`reflect_constant_array`（第 8–14 段）要求元素类型 `T`（去掉所有数组维度后的类型）是[[g:structural-type|结构化类型]]，满足 `copy_constructible`，并且能从范围的引用类型构造。每个元素先 `static_cast<T>` 再交给 `reflect_constant`，元素本身是数组时递归处理；结果数组的第 `I` 个元素与第 `I` 个反射所代表的对象模板实参等价（[[temp.type]]）。范围操作抛出的异常照常传播；如果某次 `reflect_constant` 会以异常退出，则抛出 `meta::exception`（第 13 段）。

`define_static_string`（第 15 段）等价于 `meta::extract<const range_value_t<R>*>(meta::reflect_constant_string(r))`。

`define_static_array`（第 16–17 段）用 `reflect_constant_array` 的结果构造 `span`。如果 `ranges::size(r)` 是常量表达式，`span` 的长度就固定为这个值，否则是 `dynamic_extent`。

`define_static_object`（第 18–19 段）对类类型和联合体使用 `reflect_constant`，对数组使用 `reflect_constant_array`，对其他类型借用 `define_static_array` 处理一个元素的 `span`。对类类型，结果是与 `t` 模板实参等价的那个模板形参对象的地址（注 3）。

### `is_string_literal`

```cpp
consteval bool is_string_literal(const char* p);  // 另有 wchar_t、char8_t、char16_t、char32_t 版本
```

[meta.string.literal] 第 1 段：如果 `p` 指向一个[[expr.const.core|未指明的对象]]，返回 `false`；否则，如果 `p` 指向字符串字面量对象（[[lex.string]]）的子对象，返回 `true`；否则返回 `false`。

字符串字面量的地址不能作为常量模板实参（[[temp.arg.nontype]]），而 `define_static_string` 产生的模板形参对象可以。有了 `is_string_literal`，`consteval` 代码可以区分这两种指针，例如在收到字符串字面量时给出诊断，或者先用 `define_static_string` 转换一次。

## `meta::exception`

```cpp
namespace std::meta {
  class exception : public std::exception {
  public:
    consteval exception(u8string_view what, info from,
        source_location where = source_location::current()) noexcept;
    consteval exception(string_view what, info from,
        source_location where = source_location::current()) noexcept;
    constexpr const char* what() const noexcept override;
    consteval u8string_view u8what() const noexcept;
    consteval info from() const noexcept;
    consteval source_location where() const noexcept;
    // 复制、移动的构造与赋值都是默认的
  };
}
```

¶1：反射函数通过抛出 `meta::exception` 报告错误。

C++26 允许在常量求值中抛出和捕获异常（[[P3068R6]]），这个设计依赖于此。`<meta>` 的规格中大量出现 "*Throws*: `meta::exception` unless …"，意思是前置条件不满足时抛出异常，而不是未定义行为或非良构。调用者可以在 `consteval` 函数中捕获它；如果异常逃出了常量求值，这次求值就不是常量表达式，编译器报错。

```cpp
#include <meta>

consteval bool safe_has_parent(std::meta::info r) {
  try {
    (void)std::meta::parent_of(r);
    return true;
  } catch (const std::meta::exception& e) {
    // e.from() == ^^std::meta::parent_of
    // e.where() 是上面那次调用的位置
    return false;
  }
}
static_assert(!safe_has_parent(^^::));  // 全局命名空间没有父级
```

`parent_of` 在 `has_parent(r)` 为假时抛出 `meta::exception`（[[meta.reflection.queries]]），全局命名空间正是这种情况。

错误信息可以用普通字面量编码或 UTF-8 给出，两个构造函数各保存一份（第 2–4 段）。用 `u8string_view` 构造时，如果信息能用普通字面量编码表示，还会转码保存一份供 `what()` 使用，否则那一份为空。用 `string_view` 构造时，构造函数有一个 *Constant When* 条件：只有信息能编码为 UTF-8 时，这次调用才是常量表达式。

`what()`（第 5–6 段）的 *Constant When* 条件是普通编码的那一份不为空。也就是说，如果信息只能用 UTF-8 表示，在常量求值中调用 `what()` 就不是常量表达式，这时应改用 `u8what()`。`u8what()`、`from()`、`where()` 返回保存的对应值（第 7–9 段）。

## 运算符的表示

```cpp
enum class operators { /* op_new, op_delete, ..., op_comma */ };
using enum operators;
consteval operators operator_of(info r);
consteval string_view symbol_of(operators op);
consteval u8string_view u8symbol_of(operators op);
```

运算符函数 `operator+=` 没有标识符，[[meta.reflection.queries]] 中的 `has_identifier` 对它返回 `false`，`identifier_of` 也无从使用。这一组接口专门用来识别运算符函数。

¶1：枚举 `operators` 的每个枚举项对应一个可以重载的运算符，共 44 个，值互不相同（表 63）。名字按符号的英文读法拼写，例如 `op_plus`（`+`）、`op_plus_equals`（`+=`）、`op_equals_equals`（`==`）、`op_spaceship`（`<=>`）、`op_parentheses`（`()`）、`op_square_brackets`（`[]`）、`op_arrow_star`（`->*`）、`op_array_new`（`new[]`）、`op_co_await`（`co_await`）。

¶2–3：`operator_of(r)` 返回 `r` 所代表的运算符函数或运算符函数模板的名字对应的枚举项。如果 `r` 不代表运算符函数或运算符函数模板，抛出 `meta::exception`。

¶4–5：`symbol_of(op)` 和 `u8symbol_of(op)` 返回运算符的符号，例如 `"+="`，分别用普通字面量编码和 UTF-8 编码。如果 `op` 的值不对应任何枚举项，例如 `static_cast<operators>(-1)`，抛出 `meta::exception`。

## 设计选择：反射是值，不是类型

早期的 Reflection TS 采用基于类型的设计：每个反射是一个独立的类型，用类型特征来查询，和 `<type_traits>` 的风格一致，但每次查询都要实例化模板，编译代价高，也难以用循环处理。进入 C++26 的 [[P2996R13]] 改为基于值的设计：所有反射都是同一个类型 `info` 的值，查询是普通的 `consteval` 函数，可以存进 `vector`、用循环和算法处理。注解（[[P3394R4]]）、`define_static_*`、`meta::exception` 等由同期的其他提案补入。

## 速查

| 主题 | 要点 |
|---|---|
| `info` | `decltype(^^::)`；标量类型，可比较，只能在编译期使用 |
| 总则 | 函数可取地址；异常带 `from()` 和 `where()`；字符串结果以 `'\0'` 结尾且有静态存储期 |
| `define_static_*` | 把瞬时分配的数据复制进模板形参对象，得到静态存储 |
| `is_string_literal` | 区分字符串字面量与其他字符数组 |
| `meta::exception` | 前置条件不满足时抛出，可以在常量求值中捕获 |
| `operators` | 44 个可重载运算符；`operator_of`、`symbol_of` |
