---
title: 反射
summary: C++26 静态反射库 <meta> 总览——std::meta::info 与函数族地图、四条总则（可寻址、异常的 from/where、实现扩展构造、string_view 结果以 '\0' 结尾）、is_string_literal、把编译期数据"提升"到静态存储的 define_static_string/array/object 与 reflect_constant_string/array、meta::exception 错误模型、operators 枚举
status: draft
covers: meta.syn, meta.string.literal, meta.define.static, meta.reflection.exception, meta.reflection.operators
since: c++26
papers: P2996R13, P3394R4
related: meta, expr.reflect, basic.splice, expr.prim.splice, expr.const.reflect, basic.fundamental, meta.reflection.queries, meta.reflection.extract, meta.reflection.traits, temp.param, intro.object
tags: 反射, C++26, 标准库, consteval
updated: 2026-10-18
---

!!! warning "本页示例未经本地验证"
    截至本文编写，本地工具链（Clang 23 + libc++）尚不支持 C++26 静态反射：没有 `^^` 运算符，也没有 `<meta>` 头文件。本页及 [[meta.reflection.queries]]、[[meta.reflection.extract]]、[[meta.reflection.traits]] 中的代码均依据当前草案条文与标准自带的例子编写，**未经编译验证**，因此不标判定、不提供运行按钮。

C++26 的静态反射由**语言**和**库**两半组成。语言部分在核心条款里：反射运算符 `^^`（[[expr.reflect]]）把程序构造变成一个 `std::meta::info` 值；拼接 `[: r :]`（[[basic.splice]]、[[expr.prim.splice]]）把值变回构造；[[expr.const.reflect]] 规定常量求值如何"注入声明"。库部分就是 [meta.reflection]：一组在 `std::meta::info` 上工作的 `consteval` 函数，回答"这个反射代表什么、叫什么、有哪些成员、偏移是多少"，以及"用这些反射替换出一个新的模板特化、定义一个新的类"。

## `std::meta::info` 与函数族地图（[meta.syn]）

```cpp
namespace std::meta {
  using info = decltype(^^::);
}
```

`info` 被定义为 `^^::`（全局命名空间的反射）的类型——它是一个**标量**的基本类型（[[basic.fundamental]] ¶17、[[basic.types.general#7]]），值称为**反射**（[[g:reflection]]），有唯一的**空反射**。因为是标量类型，`info` 值可以复制、用 `==` 比较、作常量模板实参；但它是 [[g:consteval-only-value]]，只能活在编译期。

`<meta>` 概要按子条款分组，构成一张函数族地图：

| 子条款 | 代表函数 | 作用 | 页面 |
|---|---|---|---|
| [meta.string.literal] | `is_string_literal` | 判断指针是否指向字符串字面量 | 本页 |
| [meta.define.static] | `define_static_string`、`define_static_array`、`define_static_object`、`reflect_constant_string/array` | 把编译期数据提升为静态存储 | 本页 |
| [meta.reflection.exception] | `meta::exception` | 反射函数的错误报告 | 本页 |
| [meta.reflection.operators] | `operators`、`operator_of`、`symbol_of` | 运算符函数的表示 | 本页 |
| [meta.reflection.names] | `identifier_of`、`display_string_of`、`source_location_of` | 名字与位置 | [[meta.reflection.queries]] |
| [meta.reflection.queries] | `type_of`、`is_*`、`has_*`、`parent_of`、`dealias`、`template_arguments_of`、`parameters_of` | 对单个反射的查询 | [[meta.reflection.queries]] |
| [meta.reflection.scope] | `current_function`、`current_class`、`current_namespace` | "我在哪里" | [[meta.reflection.queries]] |
| [meta.reflection.access.*] | `access_context`、`is_accessible` | 访问控制 | [[meta.reflection.queries]] |
| [meta.reflection.member.queries] | `members_of`、`bases_of`、`nonstatic_data_members_of`、`enumerators_of` | 枚举成员 | [[meta.reflection.queries]] |
| [meta.reflection.layout] | `offset_of`、`size_of`、`alignment_of`、`bit_size_of` | 布局 | [[meta.reflection.queries]] |
| [meta.reflection.annotation] | `annotations_of` | 读取注解 `[[=...]]` | [[meta.reflection.queries]] |
| [meta.reflection.extract] | `extract<T>` | 从反射取回 C++ 值 | [[meta.reflection.extract]] |
| [meta.reflection.substitute] | `can_substitute`、`substitute` | 用反射作模板实参 | [[meta.reflection.extract]] |
| [meta.reflection.result] | `reflect_constant`、`reflect_object`、`reflect_function` | 从 C++ 值得到反射 | [[meta.reflection.extract]] |
| [meta.reflection.define.aggregate] | `data_member_spec`、`define_aggregate` | 生成类定义 | [[meta.reflection.extract]] |
| [meta.reflection.traits] | `is_trivially_copyable_type`、`remove_cvref`、`common_type`、`type_order` | `<type_traits>` 的反射版 | [[meta.reflection.traits]] |

一个把语言与库拼在一起的典型例子——把枚举值转成字符串（依据草案编写，未验证）：

```cpp
#include <meta>
#include <string_view>

template<class E>
  requires std::is_enum_v<E>
constexpr std::string_view to_string(E value) {
    template for (constexpr auto e : std::define_static_array(std::meta::enumerators_of(^^E))) {
        if (value == [: e :])
            return std::meta::identifier_of(e);
    }
    return "<unnamed>";
}
```

这里 `enumerators_of` 返回 `vector<info>`，而 `vector` 的存储在常量求值结束时必须释放；`define_static_array` 把它提升为静态存储的数组，展开语句（[[stmt.expand]]）才能遍历它。这是使用 `<meta>` 时最常见的模式，下文详述。

## 四条总则（[meta.syn] ¶1–¶5）

**¶1：可寻址。** 除非另有规定，本头文件中的每个函数、每个函数模板特化都是**指定可寻址函数**（designated addressable function，[[namespace.std]]）——可以取地址，例如把 `std::meta::is_public` 传给 `std::ranges::filter` 之类的算法。[meta.reflection.scope] 中的函数和 `access_context::current` 是明确的例外。

**¶2：异常的来源与位置。** 当 `<meta>` 中的函数 `F` 抛出 `meta::exception` `E` 时，`E.from()` 是代表 `F` 的反射，`E.where()` 是调用 `F` 的源码位置。

**¶3：实现特有的构造。** `info` 可以代表实现特有的构造（[[basic.fundamental]]），把这种反射传给 `std::meta` 函数时行为由实现定义。注 2 补充了一条重要的副作用：许多函数的语义取决于类类型是否完整；对任何 `dealias(r)` 代表一个有可达定义的模板化类的特化的反射，该特化会被**隐式实例化**——例如 `size_of(^^X<int>)` 会实例化 `X<int>`。

**¶4：字符串结果以 `'\0'` 结尾。** 返回 `string_view`/`u8string_view` 的函数，其结果 `V` 满足 `V.data()[V.size()] == '\0'`；`V.data()` 起的每个元素是一个**可能非唯一的对象**（[[g:potentially-non-unique-object]]），具有静态存储期、可用于常量表达式；但指向它的指针**不能**作为指针类型常量模板形参的实参（[[temp.arg.nontype]]）。所以 `identifier_of(r).data()` 可以直接当 C 字符串用。

¶5：为了说明方便，本条款中用 `^^E` 表示代表源构造 `E` 的反射。

## 检查字符串字面量（[meta.string.literal]）

```cpp
consteval bool is_string_literal(const char* p);   // 以及 wchar_t、char8_t、char16_t、char32_t 版本
```

¶1：若 `p` 指向**未指明的对象**（[[expr.const.core]]），返回 `false`；否则若 `p` 指向字符串字面量对象（[[lex.string]]）的子对象，返回 `true`；否则 `false`。

它存在的理由是：字符串字面量的地址**不能**作为常量模板实参（[[temp.arg.nontype]]），也不能出现在结构化类型的常量模板实参中。库函数（例如下面的 `reflect_constant_array`）需要在编译期区分"指向字符串字面量的指针"与"指向普通静态数组的指针"，以便给出诊断或换一种处理方式。注意它只能在常量求值中调用（`consteval`），而且只对编译期可知的指针有意义。

## 提升到静态存储（[meta.define.static]）

¶1：本子条款的函数把**编译期存储**提升为**静态存储**。

为什么需要？常量求值中 `new` 出来的内存（包括 `std::vector`、`std::string` 的缓冲区）必须在求值结束前释放（[[expr.const]] 的**瞬时分配**规则，[[g:transient-allocation]]）。所以 `constexpr std::vector<info> v = members_of(...);` 非良构，`members_of` 的结果无法直接带出常量求值。解决办法是把数据复制进一个**模板形参对象**（[[g:template-parameter-object]]）——它天然具有静态存储期且可用于常量表达式。

| 函数 | 结果 |
|---|---|
| `meta::reflect_constant_string(r)` | 字符范围 → 代表模板形参对象 `const CharT[N+1]`（末尾补 `CharT()`）的反射 |
| `meta::reflect_constant_array(r)` | 范围 → 代表模板形参对象 `const T[N]` 的反射；空范围时为 `const array<T, 0>` |
| `define_static_string(r)` | `const CharT*`，指向上述字符串对象 |
| `define_static_array(r)` | `span<const T, N 或 dynamic_extent>` |
| `define_static_object(t)` | `const remove_cvref_t<T>*`，指向与 `t` 模板实参等价的对象 |

细节：

- **`reflect_constant_string`**（¶2–¶7）：*Mandates* `CharT` 是字符类型。若 `r` 是对字符串字面量对象的引用，**不包含**其末尾的 `'\0'`（避免出现两个结尾零）。注 1：结果 `P` 是可能非唯一的对象——两次以相同内容调用可能得到同一个对象，也可能不同。
- **`reflect_constant_array`**（¶8–¶14）：*Mandates* 元素类型 `T`（`remove_all_extents_t<U>`）是**结构化类型**（[[g:structural-type]]）、满足 `copy_constructible`，并且（若 `U` 不是数组）`is_constructible_v<T, range_reference_t<R>>`。每个元素先经 `reflect_constant(static_cast<T>(*it))`（元素本身是数组时递归 `reflect_constant_array`），再组成数组 `P`，使 `P[I]` 与第 `I` 个反射所代表的对象**模板实参等价**（[[temp.type]]）。¶13 *Throws*：范围操作抛出的异常、`reflect_constant` 抛出的异常照原样传播；若某次 `reflect_constant` 会以异常退出，则抛 `meta::exception`。
- **`define_static_string`**（¶15）：等价于 `return meta::extract<const range_value_t<R>*>(meta::reflect_constant_string(r));`。
- **`define_static_array`**（¶16–¶17）：用 `reflect_constant_array` 的结果构造 `span`；若 `ranges::size(r)` 是常量表达式，`span` 的 extent 就是这个大小，否则为 `dynamic_extent`。
- **`define_static_object`**（¶18–¶19）：类类型走 `reflect_constant`，数组走 `reflect_constant_array`，其他类型走 `define_static_array(span(addressof(t), 1)).data()`。注 3：对类类型，它给出的是与 `t` 模板实参等价的**模板形参对象**的地址。

```cpp
// 依据草案编写，未验证
#include <meta>

consteval const char* make_name(int n) {
    std::string s = "field_";                       // 编译期 std::string：瞬时分配
    s += static_cast<char>('0' + n);
    return std::define_static_string(s);           // 提升为静态存储，可带出常量求值
}
constexpr const char* name = make_name(3);         // "field_3"，以 '\0' 结尾
static_assert(!std::is_string_literal(name));      // 它是模板形参对象，不是字符串字面量
```

!!! note "为什么叫 “reflect_constant_*” 而函数族里又有 “define_static_*”"
    `reflect_constant_*` 返回**反射**（`info`），可以继续交给其他反射函数或拼接；`define_static_*` 返回普通的 C++ 指针/`span`，可以直接在非反射代码中使用。后者都用前者 + `extract` 定义。

## `meta::exception`：反射的错误模型（[meta.reflection.exception]）

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
    // 复制/移动构造与赋值均为默认
  };
}
```

¶1：反射函数通过抛出 `meta::exception` 来报告错误。这是 C++26 允许在常量求值中抛出并捕获异常（[[P3068R6]]）之后才可能的设计：在 `<meta>` 的规格里大量出现 "*Throws*: `meta::exception` unless ..."，意思是**前置条件不满足时抛异常**，而不是 UB 或非良构。调用者可以在 `consteval` 函数里 `try`/`catch` 它；若异常逃出了常量求值，求值就不是常量表达式，编译器会给出包含 `what()` 信息的诊断。

- ¶2：`u8string_view` 构造函数保存 UTF-8 文本；若它能用普通字面量编码表示，还把转码结果存进 *what_*，否则 *what_* 为空。
- ¶3–¶4：`string_view` 构造函数的 *Constant When*：文本能编码为 UTF-8；保存原文并转码一份 UTF-8。
- ¶5–¶6：`what()` 的 *Constant When* 是 *what_* 有值——若消息只能用 UTF-8 表示，在常量求值中调用 `what()` 不是常量表达式；
- ¶7–¶9：`u8what()`、`from()`、`where()` 返回对应成员。

```cpp
// 依据草案编写，未验证
consteval bool safe_has_parent(std::meta::info r) {
    try {
        (void)std::meta::parent_of(r);
        return true;
    } catch (const std::meta::exception& e) {
        // e.from() == ^^std::meta::parent_of；e.where() 是上面那次调用的位置
        return false;
    }
}
static_assert(!safe_has_parent(^^::));   // 全局命名空间没有父级
```

## 运算符的表示（[meta.reflection.operators]）

```cpp
enum class operators { /* op_new, op_delete, ..., op_comma */ };
using enum operators;
consteval operators operator_of(info r);
consteval string_view symbol_of(operators op);
consteval u8string_view u8symbol_of(operators op);
```

¶1：`operators` 的枚举项对应所有**可重载**的运算符（表 63），值互不相同。命名规则是"按符号的英文名拼写"：`op_plus`（`+`）、`op_plus_equals`（`+=`）、`op_equals_equals`（`==`）、`op_spaceship`（`<=>`）、`op_parentheses`（`()`）、`op_square_brackets`（`[]`）、`op_arrow_star`（`->*`）、`op_array_new`（`new[]`）、`op_co_await`（`co_await`）等，一共 44 个。

- ¶2–¶3 `operator_of(r)`：返回 `r` 所代表的运算符函数（或运算符函数模板）名字对应的枚举项；若 `r` 不是运算符函数或运算符函数模板，抛 `meta::exception`。
- ¶4–¶5 `symbol_of(op)` / `u8symbol_of(op)`：返回运算符的符号字符串（如 `"+="`）；若 `op` 的值不对应任何枚举项（例如 `static_cast<operators>(-1)`），抛 `meta::exception`。

运算符函数没有"标识符"——[[meta.reflection.queries]] 中的 `has_identifier` 对运算符函数为假——所以需要这套专门的接口来识别它们。

## 历史与演进

!!! history "从 Reflection TS 到值反射"
    C++ 的反射走过两条路：早期的 Reflection TS 采用**基于类型**的设计（每个反射是一个独特的类型，用 trait 查询），这与 `<type_traits>` 一脉相承但编译代价高昂；最终进入 C++26 的 [[P2996R13]] 采用**基于值**的设计——所有反射都是同一个类型 `std::meta::info` 的值，查询是普通的 `consteval` 函数，可以用循环、容器和算法处理。注解（[[P3394R4]]）、`define_static_*`、`meta::exception` 错误模型、函数形参反射等由同期的后续提案补入；[meta.reflection] 现在是第 21 章中篇幅最大的部分。

## 小结

| 主题 | 要点 |
|---|---|
| `info` | `decltype(^^::)`；标量、可比较、仅限编译期 |
| 总则 | 函数可寻址；异常带 `from`/`where`；字符串结果以 `'\0'` 结尾且有静态存储期 |
| `is_string_literal` | 区分字符串字面量与其他字符数组 |
| `define_static_*` | 把瞬时分配的编译期数据复制进模板形参对象，得到静态存储 |
| `meta::exception` | 前置条件不满足时抛出，可在常量求值中捕获 |
| `operators` | 44 个可重载运算符；`operator_of`、`symbol_of` |
