---
title: 值提取
summary: 反射与 C++ 值之间的双向桥梁与"生成"能力——extract<T> 的三条路径（引用、成员/函数指针、值）及其严格的类型匹配；reflection_range、can_substitute/substitute 以反射作模板实参；reflect_constant/reflect_object/reflect_function 由值得到反射；data_member_spec 与 define_aggregate 在常量求值中注入类定义
status: draft
covers: meta.reflection.extract, meta.reflection.substitute, meta.reflection.result, meta.reflection.define.aggregate
since: c++26
papers: P2996R13
related: meta.reflection, meta.reflection.queries, meta.reflection.traits, expr.const.reflect, basic.splice, temp.param, temp.arg.nontype, temp.type, conv.qual, class.mem, temp.names
tags: 反射, C++26, 标准库, consteval, 代码生成
updated: 2026-10-18
---

!!! warning "未经本地验证"
    本地 Clang 23 不支持 C++26 反射。本页代码依据当前草案与标准自带例子编写，未经编译验证，不标判定。

[[meta.reflection.queries]] 中的函数"读"程序；本页的函数则在反射与普通 C++ 世界之间**搬运**，并且能**写**程序：

| 方向 | 函数 | 子条款 |
|---|---|---|
| 反射 → 值 | `extract<T>(r)` | [meta.reflection.extract] |
| 反射 → 新的反射（模板特化）| `can_substitute`、`substitute` | [meta.reflection.substitute] |
| 值 → 反射 | `reflect_constant`、`reflect_object`、`reflect_function` | [meta.reflection.result] |
| 反射 → 新的类定义 | `data_member_spec`、`define_aggregate` | [meta.reflection.define.aggregate] |

拼接 `[: r :]`（[[basic.splice]]）也能把反射变回值，但它要求 `r` 是**常量表达式**，只能用在模板实参、`template for` 之类能提供常量的地方；`extract` 是一个普通的 `consteval` 函数，接受任何（常量求值中的）`info` 值，可以在循环里、在 `vector<info>` 上直接用——代价是你必须**事先知道类型 `T`**。

## 一、`extract`（[meta.reflection.extract]）

```cpp
template<class T> consteval T extract(info r);
```

¶1：当反射的类型已知时，用 `extract` 从中取出值。¶11–¶12：令 `U = remove_cv_t<T>`，它等价于：

```cpp
if constexpr (is_reference_type(^^T)) {
  return extract-ref<T>(r);
} else if (is_nonstatic_data_member(r) || is_function(r)) {
  return extract-member-or-function<U>(r);
} else {
  return extract-value<U>(constant_of(r));
}
```

三条说明用路径，各有严格的匹配规则——`extract` 刻意**不做**一般的隐式转换，因为反射值的"静态类型"信息必须与 `T` 对上，否则就是在做无检查的类型双关。

**(1) *extract-ref*：`T` 是引用**（¶3–¶5）。返回对 `r` 所代表对象（或变量所声明/引用的对象）的引用。*Throws* 条件：`r` 代表类型为 `U` 的变量或对象，并且 `is_convertible_v<remove_reference_t<U>(*)[], remove_reference_t<T>(*)[]>` 为真——注 2 解释这个"数组指针转换"技巧的意图：**只允许限定转换**（加 `const`），不允许派生到基类之类的转换；变量还须可用于常量表达式或在当前求值中开始生存期。

**(2) *extract-member-or-function*：`r` 是非静态数据成员或函数**（¶6–¶7）。

- 非静态数据成员（非位域，类型 `X`，属于类 `C`）→ 成员指针 `X C::*`，要求 `T` 与它相似（[[conv.qual]]）且可转换；
- 隐式对象成员函数（类型 `F` 或 `F noexcept`）→ 必须恰好是 `F C::*`；
- 非成员函数、静态成员函数、显式对象成员函数 → 必须恰好是 `F*`。

**(3) *extract-value*：其他情况**（¶8–¶10）。先 `constant_of(r)` 取常量，再 `static_cast<T>([: R :])`。*Throws* 条件非常窄：`U`（值的类型）与 `T` 的 cv 无限定类型**相同**；或都是指针且相似（或都是函数指针）且可转换；或 `U` 是数组而 `T` 是相似的元素指针；或 `U` 是闭包类型而 `T` 是它可转换到的函数指针。

```cpp
constexpr int k = 42;
static_assert(std::meta::extract<int>(^^k) == 42);          // 值路径：类型完全一致
// std::meta::extract<long>(^^k);                            // 抛 meta::exception：int ≠ long，不做算术转换
constexpr const int& rk = std::meta::extract<const int&>(^^k);   // 引用路径：允许加 const

struct S { int m; int f(int); };
constexpr auto pm = std::meta::extract<int S::*>(^^S::m);   // 成员路径
constexpr auto pf = std::meta::extract<int (S::*)(int)>(^^S::f);
```

注解的值同样走值路径：`extract<int>(annotations_of(^^g)[0])`（见 [[meta.reflection.queries]]）。

## 二、模板替换（[meta.reflection.substitute]）

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

`reflection_range` 是"元素就是 `info` 的输入范围"，`vector<info>`、`span<const info>`、`initializer_list<info>` 都满足；默认模板实参 `initializer_list<info>` 让 `substitute(^^X, {^^int, ^^char})` 这种花括号写法能推导。

¶1 定义 *TARG-SPLICE*`(x)`：若 `x` 代表模板，为 `template [: x :]`；若代表类型，为 `typename [: x :]`；否则为 `([: x :])`——即把每个反射按其种类拼接成合适的模板实参形式。

- **`can_substitute(templ, args)`**（¶2–¶5）：若 `Z<TARG-SPLICE(Args)...>` 是有效的 *template-id*（[[temp.names]]），且不是一个类型中含未推导占位符的函数，则为真。*Throws*：`templ` 不是模板，或某个实参不能作模板实参。
- **`substitute(templ, args)`**（¶6–¶9）：返回 `^^Z<TARG-SPLICE(Args)...>`；`can_substitute` 为假时抛异常。

**直接语境之外的错误仍是硬错误**（注 1、注 2），与 [[meta.unary.prop]] 中 trait 的规则同理。标准例子把这一点和"返回类型推导"结合起来，非常有代表性：

```cpp
template<class T> auto fn1();
static_assert(!can_substitute(^^fn1, {^^int}));
constexpr info r1 = substitute(^^fn1, {^^int});       // error: fn1<int> 的返回类型含未推导占位符

template<class T> auto fn2() {
  static_assert(^^T != ^^int);
  return 0;
}
constexpr bool r2 = can_substitute(^^fn2, {^^int});   // error: 为推导返回类型需要实例化函数体，
                                                      //        而函数体中的 static_assert 失败是硬错误
```

另一个例子展示了值实参的用法：

```cpp
consteval info to_integral_constant(unsigned i) {
  return substitute(^^integral_constant, {^^unsigned, reflect_constant(i)});
}
constexpr info r = to_integral_constant(2);   // r 代表 integral_constant<unsigned, 2>
```

注意 `i` 是 `consteval` 函数的**普通形参**，不是常量表达式——无法直接写 `integral_constant<unsigned, i>`。`reflect_constant(i)` 把运行中的编译期值变成反射，`substitute` 再把它当作模板实参使用：**这就是反射把"值"提升为"模板实参"的方式**，在 C++26 之前只能靠 `integer_sequence` + 包展开或递归模板绕道实现。

## 三、由值得到反射（[meta.reflection.result]）

### `reflect_constant`

```cpp
template<class T> consteval info reflect_constant(T expr);
```

¶1 *Mandates*：`is_copy_constructible_v<T>`，且 `T` 是 cv 无限定、非引用的**结构化类型**（[[g:structural-type]]）。¶2–¶4：令 `V` 为 `expr` 的值（类类型则为与之模板实参等价的对象），想象一个模板 `template<T P> struct TCls;`，返回 `template_arguments_of(^^TCls<V>)[0]`。注 1：对类类型，结果是**对象**的反射（模板形参对象）；否则是**值**的反射。¶5 *Throws*：`TCls<V>` 不是有效的 *template-id*。

换句话说，`reflect_constant(x)` 的结果**精确等于**"把 `x` 当作常量模板实参时得到的东西"。这也决定了它的限制：

```cpp
template<auto D> struct A { };
struct N { int x; };
struct K { char const* p; };

constexpr info r1 = reflect_constant(42);
static_assert(is_value(r1) && r1 == template_arguments_of(^^A<42>)[0]);

constexpr info r2 = reflect_constant(N{42});
static_assert(is_object(r2) && r2 == template_arguments_of(^^A<N{42}>)[0]);

constexpr info r3 = reflect_constant(K{nullptr});   // OK
constexpr info r4 = reflect_constant(K{"ebab"});    // error: 成员指针指向字符串字面量，不能作模板实参
```

`r4` 正是 [[meta.reflection]] 中 `is_string_literal`、`define_static_string` 要解决的问题：先 `define_static_string("ebab")` 得到一个模板形参对象的地址，就可以放进 `K` 了。

### `reflect_object` 与 `reflect_function`

```cpp
template<class T> consteval info reflect_object(T& expr);   // Mandates: T 是对象类型
template<class T> consteval info reflect_function(T& fn);   // Mandates: T 是函数类型
```

返回所指对象 / 函数的反射。*Throws*：若该对象/函数不适合作为 `T&` 类型常量模板形参的实参（[[temp.arg.nontype]]）——例如自动存储期对象、字符串字面量对象（[[temp.arg.nontype]]）。与 `reflect_constant` 的区别是**身份**：`reflect_object(s)` 代表 `s` 这个对象本身，`reflect_constant(s)` 代表与 `s` 等值的模板形参对象，二者不相等（见 [[meta.reflection.queries]] 中 `constant_of` 的例子）。

## 四、生成类定义（[meta.reflection.define.aggregate]）

这是 C++26 反射中唯一一个"写"的能力：在常量求值中为一个**不完整的类**注入定义。

### `data_member_options` 与 `data_member_spec`

```cpp
struct data_member_options {
  struct name-type { /* 接受 string 或 u8string 可构造的实参 */ };
  optional<name-type> name;
  optional<int> alignment;
  optional<int> bit_width;
  bool no_unique_address = false;
  vector<info> annotations;
};
consteval info data_member_spec(info type, data_member_options options);
consteval bool is_data_member_spec(info r);
```

¶1：`data_member_options` 与 *name-type* **不是结构化类型**，其值都是仅限编译期的值。¶2–¶3：*name-type* 让 `.name` 既能接受普通字符串（`"x"`、`string_view`、`string`）也能接受 UTF-8 字符串（`u8"x"`）。

¶4 `data_member_spec` 返回一个**数据成员描述** `(T, N, A, W, NUA, ANN)` 的反射（[[class.mem]]）：类型 `T`（去别名）、名字 `N`、对齐 `A`、位宽 `W`、`[[no_unique_address]]` 标志 `NUA`、注解常量序列 `ANN`；未提供的项为 ⊥。注 2：这种反射主要配合 `define_aggregate`，也可以用 `type_of`、`identifier_of`、`size_of` 等查询。

¶5 *Throws* 列出了一个数据成员声明本该满足的全部规则：类型必须是对象或引用类型；名字必须是合法的标识符记号（注 3：**不**处理通用字符名，`R"(α)"` 不会被当作 `α`）；没有名字时必须有位宽且没有注解（只能是无名位域）；有位宽时类型须为整型或枚举、不能同时指定对齐或 `no_unique_address`、宽度非负、宽度为 0 则不能有名字、无名位域不能是 cv 限定的；对齐值须合法且不小于类型的对齐；每个注解须有非数组对象类型且求常量不抛异常。

### `define_aggregate`

```cpp
template<reflection_range R = initializer_list<info>>
  consteval info define_aggregate(info class_type, R&& mdescrs);
```

¶8 *Constant When*（不满足则调用不是常量表达式）：

1. `class_type` 代表一个 cv 无限定的类类型 `C`；
2. `C` 从求值上下文的**每一个**点看都不完整——注 4：`C` 可以是有可达定义的类模板的特化，此时注入的声明是一个**显式特化**；
3. 每个 `rK` 都是数据成员描述，且其类型 `TK` 是完整类型；
4. 有名字的成员两两不同名，除非名字是 `_`（[[g:name-independent-declaration]]）。

¶9 *Effects*：产生一个定义 `C` 的**注入声明** `D`（[[g:injected-declaration]]，[[expr.const.reflect]]）：

- 目标作用域是 `C` 所属的作用域；
- **声明点紧跟在当前正在求值的核心常量表达式之后**——所以在同一个表达式内部看，`C` 仍不完整；
- `D` 的特征序列是这些 `rK`（它参与跨翻译单元的 ODR 判定）；
- 若 `C` 是非局部的模板化类的特化，`D` 是显式特化；
- 每个 `rK` 对应一个**public** 成员 `MK`：`NK` 为 ⊥ 则是无名位域，否则是名为 `NK` 的非静态数据成员；类型 `TK`；`NUAK` 决定 `[[no_unique_address]]`；`WK` 决定位宽；`AK` 决定 `alignas`；每个注解常量成为一个注解；
- 成员按 `mdescrs` 的顺序声明。

¶10 返回 `class_type`。¶11：若 `C` 是尚未实例化的模板化类的特化，它被当作显式特化。

```cpp
// 依据草案编写，未验证
#include <meta>

struct Point;                                         // 只声明
consteval {                                           // consteval 块（[dcl.pre]）
    std::meta::define_aggregate(^^Point, {
        std::meta::data_member_spec(^^int, {.name = "x"}),
        std::meta::data_member_spec(^^int, {.name = "y"}),
    });
}
// 此处 Point 已完整：struct Point { int x; int y; };
constexpr Point p{1, 2};
static_assert(p.x + p.y == 3);
```

为什么只能生成**聚合**（只有 public 非静态数据成员和无名位域）？这是 C++26 有意收窄的范围：成员函数、基类、访问控制、构造函数的注入涉及大量尚未解决的设计问题。即便如此，配合 `nonstatic_data_members_of` 已经能实现"结构体的数组 ↔ 数组的结构体"（AoS → SoA）转换、按字段生成元组类型、根据配置生成消息结构等经典代码生成任务。

## 陷阱

!!! pitfall "`extract` 不做算术转换"
    `extract<long>(^^some_int_constant)` 抛异常，而不是把 `int` 转成 `long`。先用 `type_of` 判断类型，或用拼接 `[: r :]`（它产生的是正常的表达式，后续的隐式转换照常发生）。

!!! pitfall "`substitute` 的硬错误"
    `can_substitute` 只检查直接语境。带推导返回类型的函数模板、在实例化中会 `static_assert` 失败的类模板，都可能让 `can_substitute` 本身变成硬错误（例 1 中的 `fn2`）。

!!! pitfall "`define_aggregate` 只能对\"从未完整过\"的类调用"
    ¶8.2 要求 `C` 从求值上下文的每个点看都不完整。对已经定义的类、或在同一翻译单元中先被别处定义的类调用，都不是常量表达式。同一个类也只能被定义一次——第二次调用时它已经完整了。

## 小结

| 函数 | 方向 | 关键约束 |
|---|---|---|
| `extract<T>` | 反射 → 值 | 引用只允许加 cv；成员/函数指针类型须精确；值须同类型（无算术转换）|
| `can_substitute` / `substitute` | 反射 → 特化的反射 | 按种类拼接实参；直接语境外的错误仍是硬错误 |
| `reflect_constant` | 值 → 反射 | 结构化类型；等于"作常量模板实参的结果" |
| `reflect_object` / `reflect_function` | 左值 → 反射 | 须能作引用型常量模板实参 |
| `data_member_spec` | 选项 → 数据成员描述 | 复刻数据成员声明的全部合法性规则 |
| `define_aggregate` | 描述 → 类定义 | 类须从未完整；注入点在当前表达式之后；只生成 public 数据成员 |
