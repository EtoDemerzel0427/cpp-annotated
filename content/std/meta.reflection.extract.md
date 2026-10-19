---
title: 值提取与代码生成
summary: 反射与普通值之间的转换（extract、reflect_constant、reflect_object、reflect_function），用反射作模板实参得到新的特化（substitute），以及在常量求值中为不完整的类生成定义（define_aggregate）。
status: draft
covers: meta.reflection.extract, meta.reflection.substitute, meta.reflection.result, meta.reflection.define.aggregate
since: c++26
papers: P2996R13
related: meta.reflection, meta.reflection.queries, meta.reflection.traits, expr.const.reflect, basic.splice, temp.param, temp.arg.nontype, temp.type, conv.qual, class.mem, temp.names
tags: 反射, C++26, 标准库, consteval, 代码生成
updated: 2026-10-19
---

!!! tldr
    - `extract<T>(r)` 把反射变回一个 `T` 类型的值。它几乎不做转换：值的类型必须与 `T` 相同，引用只允许加 `const`，否则抛出 `meta::exception`。
    - `reflect_constant(v)` 的结果与把 `v` 当作常量模板实参时得到的东西完全相同，所以 `v` 必须是结构化类型，也受模板实参的全部限制。
    - `substitute(^^Z, {args...})` 用反射作模板实参得到 `Z<args...>` 的反射，借此可以把 `consteval` 函数的普通形参变成模板实参。
    - `can_substitute` 只检查直接语境中的错误；需要实例化函数体才能发现的错误仍然使程序非良构。
    - `define_aggregate` 为一个从未完整过的类生成定义，成员只能是 public 的非静态数据成员和无名位域。

!!! note "关于本页的例子"
    本机 Clang 23 还不支持 C++26 反射。本页代码依据当前草案和标准自带的例子编写，没有经过编译，因此不标判定。大多数例子省略了 `#include <meta>` 和 `using namespace std::meta;`。

[[meta.reflection.queries]] 中的函数读取程序，本页的函数则在反射和普通 C++ 值之间转换，还能生成新的程序构造：

| 方向 | 函数 | 子条款 |
|---|---|---|
| 反射 → 值 | `extract<T>(r)` | [meta.reflection.extract] |
| 值 → 反射 | `reflect_constant`、`reflect_object`、`reflect_function` | [meta.reflection.result] |
| 反射 → 模板特化的反射 | `can_substitute`、`substitute` | [meta.reflection.substitute] |
| 反射 → 类的定义 | `data_member_spec`、`define_aggregate` | [meta.reflection.define.aggregate] |

## 从反射取值：`extract` [meta.reflection.extract]

```cpp
constexpr int k = 42;
static_assert(extract<int>(^^k) == 42);                // 类型一致
// extract<long>(^^k);                                 // 抛出 meta::exception：int 不是 long
constexpr const int& rk = extract<const int&>(^^k);    // 引用：允许加 const

struct S { int m; int f(int); };
constexpr auto pm = extract<int S::*>(^^S::m);          // 成员指针
constexpr auto pf = extract<int (S::*)(int)>(^^S::f);  // 成员函数指针
```

拼接 `[: r :]`（[[basic.splice]]）也能把反射变回表达式，但 `r` 必须是常量表达式。`extract` 是普通的 `consteval` 函数，可以作用于循环变量、`vector<info>` 的元素等任何常量求值中的 `info` 值，代价是调用者要事先知道类型 `T`。

¶1 `extract` 用于在类型已知时从反射中取出值。¶12 令 `U` 为 `remove_cv_t<T>`，它等价于下面的分派：

```cpp
if constexpr (is_reference_type(^^T)) {
  return extract-ref<T>(r);
} else if (is_nonstatic_data_member(r) || is_function(r)) {
  return extract-member-or-function<U>(r);
} else {
  return extract-value<U>(constant_of(r));
}
```

三条路径都只接受类型严格匹配的情况。反射携带了值的确切类型，如果 `extract` 允许任意转换，就等于在做不受检查的类型双关。

**引用**（¶3–¶5）。`r` 必须代表一个类型为 `U` 的变量或对象，结果是对该对象的引用。¶5 要求 `is_convertible_v<remove_reference_t<U>(*)[], remove_reference_t<T>(*)[]>` 为真。转成指向数组的指针来比较，是为了只放行限定转换（加 `const`、`volatile`），挡住派生类到基类等转换（注 2）。如果 `r` 代表变量，它还必须可用于常量表达式，或者在当前这次常量求值中开始了生存期。

**成员与函数**（¶6–¶7）。非静态数据成员（不能是位域）得到成员指针 `X C::*`，`T` 必须与之相似（[[conv.qual]]）并可由它转换而来。隐式对象成员函数要求 `T` 恰好是 `F C::*`，非成员函数、静态成员函数和显式对象成员函数要求 `T` 恰好是 `F*`。

**值**（¶8–¶10）。先用 `constant_of` 取出值，再 `static_cast<T>`。¶10 只允许四种情况：值的类型与 `T` 去掉 cv 后相同；两者都是指针，彼此相似（或都是函数指针）且可以转换；值是数组而 `T` 是相似的元素指针；值是闭包对象而 `T` 是它能转换成的函数指针。

注解的值也走这条路径：`extract<int>(annotations_of(^^g)[0])`，见 [[meta.reflection.queries]]。

## 从值得到反射 [meta.reflection.result]

### `reflect_constant`（¶1–¶6）

```cpp
template<auto D> struct A { };
struct N { int x; };
struct K { char const* p; };

constexpr info r1 = reflect_constant(42);
static_assert(is_value(r1) && r1 == template_arguments_of(^^A<42>)[0]);

constexpr info r2 = reflect_constant(N{42});
static_assert(is_object(r2) && r2 == template_arguments_of(^^A<N{42}>)[0]);

constexpr info r3 = reflect_constant(K{nullptr});   // OK
constexpr info r4 = reflect_constant(K{"ebab"});    // 错误：指针指向字符串字面量
```

¶3 标准用一个虚构的模板 `template<T P> struct TCls;` 定义 `reflect_constant(v)`：¶4 结果就是 `template_arguments_of(^^TCls<V>)[0]`，其中 `V` 是 `v` 的值。换句话说，结果等于把 `v` 用作常量模板实参时得到的东西：对类类型是一个模板形参对象的反射，对其他类型是值的反射（注 1）。

这也决定了它的限制。¶1 `T` 必须可复制构造，并且是 cv 无限定、非引用的**结构化类型**（[[g:structural-type]]），即可以作常量模板形参的类型。¶5 `TCls<V>` 不合法时抛出异常，上例的 `r4` 就是这样：字符串字面量的地址不能作模板实参（[[temp.arg.nontype]]）。解决办法是先用 `define_static_string("ebab")` 得到一个可以作模板实参的字符数组（见 [[meta.reflection]]）。

### `reflect_object` 与 `reflect_function`（¶7–¶12）

```cpp
template<class T> consteval info reflect_object(T& expr);   // T 必须是对象类型
template<class T> consteval info reflect_function(T& fn);   // T 必须是函数类型
```

¶8 它们返回实参所指的那个对象或函数本身的反射。¶9 这个对象或函数必须适合作为 `T&` 类型的常量模板实参：例如自动存储期的对象、字符串字面量对象都不行。

`reflect_object(s)` 与 `reflect_constant(s)` 的区别在于身份：前者代表 `s` 这个对象，后者代表一个与 `s` 模板实参等价的模板形参对象，两者不相等（见 [[meta.reflection.queries]] 中 `constant_of` 的例子）。

## 用反射作模板实参：`substitute` [meta.reflection.substitute]

```cpp
consteval info to_integral_constant(unsigned i) {
  return substitute(^^integral_constant, {^^unsigned, reflect_constant(i)});
}
constexpr info r = to_integral_constant(2);   // r 代表 integral_constant<unsigned, 2>
```

`i` 是 `consteval` 函数的普通形参，不是常量表达式，不能直接写 `integral_constant<unsigned, i>`。`reflect_constant(i)` 把它的值变成反射，`substitute` 再把这个反射当作模板实参使用。在 C++26 之前，同样的事情只能借助 `integer_sequence` 和包展开，或者递归模板来绕道实现。

```cpp
template<class R>
concept reflection_range =
  ranges::input_range<R> &&
  same_as<ranges::range_value_t<R>, info> &&
  same_as<remove_cvref_t<ranges::range_reference_t<R>>, info>;

template<reflection_range R = initializer_list<info>>
  consteval bool can_substitute(info templ, R&& arguments);
template<reflection_range R = initializer_list<info>>
  consteval info substitute(info templ, R&& arguments);
```

`reflection_range` 是元素类型为 `info` 的输入范围，`vector<info>`、`span<const info>`、`initializer_list<info>` 都满足。默认模板实参 `initializer_list<info>` 让 `substitute(^^X, {^^int, ^^char})` 这种花括号写法能通过推导。

¶1 每个实参反射按它的种类拼接成模板实参：模板写成 `template [: x :]`，类型写成 `typename [: x :]`，其余写成 `([: x :])`。¶3 `can_substitute` 判断拼出的 `Z<...>` 是否是合法的 *template-id*（[[temp.names]]），并且不是一个类型中还含有未推导占位符的函数。¶7 `substitute` 返回 `^^Z<...>`，¶8 不合法时抛出异常。¶4 `templ` 不是模板，或者某个实参不能用作模板实参时，两者都抛出异常。

### 直接语境之外的错误

```cpp
template<class T> auto fn1();
static_assert(!can_substitute(^^fn1, {^^int}));
constexpr info r1 = substitute(^^fn1, {^^int});       // 错误：fn1<int> 的返回类型还未推导

template<class T> auto fn2() {
  static_assert(^^T != ^^int);
  return 0;
}
constexpr bool r2 = can_substitute(^^fn2, {^^int});   // 错误：推导返回类型要实例化函数体，
                                                      // 函数体中的 static_assert 失败
```

¶5 与 SFINAE 一样，只有在**直接语境**（[[g:immediate-context]]）中出现的错误才会让 `can_substitute` 返回 `false`。形成 `Z<...>` 时如果在直接语境之外失败，例如实例化函数体或类模板定义时出错，程序就是非良构的（注 1、注 2）。`fn1` 没有定义，无从推导返回类型，`can_substitute` 返回 `false`，`substitute` 抛出异常；`fn2` 有定义，推导返回类型需要实例化函数体，函数体里的 `static_assert` 失败是硬错误，连 `can_substitute` 本身都通不过。

## 生成类的定义 [meta.reflection.define.aggregate]

```cpp
struct Point;                                   // 只声明
consteval {                                     // consteval 块（[dcl.pre]）
  define_aggregate(^^Point, {
    data_member_spec(^^int, {.name = "x"}),
    data_member_spec(^^int, {.name = "y"}),
  });
}
// 此后 Point 相当于 struct Point { int x; int y; };
constexpr Point p{1, 2};
static_assert(p.x + p.y == 3);
```

这是 C++26 反射中唯一能生成新声明的接口：在常量求值中为一个不完整的类注入定义。生成的类只能有 public 的非静态数据成员和无名位域，也就是一个聚合。成员函数、基类、访问控制、构造函数的生成牵涉很多尚未解决的设计问题，C++26 没有包含。即便如此，配合 `nonstatic_data_members_of` 已经可以做很多事，例如把结构体数组转换成数组结构体（AoS → SoA）、按字段生成元组类型。

### 描述一个成员：`data_member_spec`（¶1–¶6）

```cpp
struct data_member_options {
  struct name-type { /* 可由 string 或 u8string 构造 */ };
  optional<name-type> name;
  optional<int> alignment;
  optional<int> bit_width;
  bool no_unique_address = false;
  vector<info> annotations;
};
consteval info data_member_spec(info type, data_member_options options);
consteval bool is_data_member_spec(info r);
```

¶4 `data_member_spec` 返回一个**数据成员描述**（[[g:data-member-description]]）的反射。它是一个六元组 `(T, N, A, W, NUA, ANN)`，依次为类型（去掉别名）、名字、对齐、位域宽度、是否 `[[no_unique_address]]`、注解的值；没有提供的项记作 ⊥。这种反射主要交给 `define_aggregate` 使用，也可以用 `type_of`、`identifier_of`、`size_of` 等查询（注 2）。

¶3 `name` 既可以给普通字符串（`"x"`、`string_view`、`string`），也可以给 UTF-8 字符串（`u8"x"`）。¶1 `data_member_options` 不是结构化类型，它的值只能在常量求值中存在。

¶5 列出了一个数据成员声明本来就要满足的规则，不满足时抛出异常：

- 类型必须是对象类型或引用类型；
- 名字必须是一个合法的标识符记号。通用字符名不会被处理，`R"(\u03B1)"` 是非法的名字，不会被当作 `α`（注 3）；
- 没有名字时必须指定位宽，且不能带注解，也就是只能是无名位域；
- 指定了位宽时，类型必须是整型或枚举，不能同时指定对齐或 `no_unique_address`，宽度不能为负，宽度为 0 时不能有名字，无名位域的类型不能有 cv 限定；
- 对齐必须是合法的对齐值，且不小于类型本身的对齐；
- 每个注解必须有非数组的对象类型，且取其常量值时不抛出异常。

### `define_aggregate`（¶7–¶11）

```cpp
template<reflection_range R = initializer_list<info>>
  consteval info define_aggregate(info class_type, R&& mdescrs);
```

¶8 调用只有满足以下条件时才是常量表达式：

1. `class_type` 代表一个 cv 无限定的类类型 `C`；
2. 从求值上下文中的每一个点看，`C` 都不完整；
3. 每个实参都是数据成员描述，且其类型是完整类型；
4. 有名字的成员两两不同名，除非名字是 `_`（[[g:name-independent-declaration]]）。

第 2 条意味着同一个类只能定义一次：第二次调用时它已经完整了。`C` 可以是类模板的特化，此时生成的是一个显式特化（注 4）。

¶9 效果是产生一个定义 `C` 的**注入声明**（[[g:injected-declaration]]，[[expr.const.reflect]]）：

- 它位于 `C` 所属的作用域中，声明点紧跟在当前正在求值的那个核心常量表达式之后。所以在同一个表达式内部，`C` 仍然不完整；
- 每个数据成员描述对应一个 public 成员：没有名字的是无名位域，有名字的是同名的非静态数据成员；位宽、`alignas`、`[[no_unique_address]]` 和注解都按描述设置；
- 成员按 `mdescrs` 中的顺序声明；
- 这串数据成员描述构成注入声明的特征序列，用于跨翻译单元的 ODR 判断（[[expr.const.reflect]]）。

¶10 返回值就是 `class_type`。¶11 如果 `C` 是一个尚未实例化的模板化类的特化，它被当作显式特化。

## 常见误解

!!! pitfall "以为 `extract` 会做算术转换"
    `extract<long>(^^some_int_constant)` 抛出异常，不会把 `int` 转成 `long`。需要转换时先用 `type_of` 判断类型，或者使用拼接 `[: r :]`：拼接得到的是普通表达式，之后的隐式转换照常进行。

!!! pitfall "以为 `can_substitute` 永远不会报错"
    `can_substitute` 只检查直接语境。返回类型需要推导的函数模板、实例化时会触发 `static_assert` 的类模板，都可能让 `can_substitute` 本身成为硬错误，如上文的 `fn2`。

!!! pitfall "对已经定义过的类调用 `define_aggregate`"
    第 8.2 段要求 `C` 从求值上下文的每个点看都不完整。对已有定义的类调用，或者同一个类调用两次，调用都不是常量表达式，程序无法编译。
