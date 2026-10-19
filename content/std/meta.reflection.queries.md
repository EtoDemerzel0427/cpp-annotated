---
title: 反射查询
summary: 给定一个 std::meta::info，问它是什么、叫什么、类型和值是什么、属于谁、有哪些成员、在内存里怎样布局、带了哪些注解。
status: draft
covers: meta.reflection.names, meta.reflection.queries, meta.reflection.scope, meta.reflection.access.context, meta.reflection.access.queries, meta.reflection.member.queries, meta.reflection.layout, meta.reflection.annotation
since: c++26
papers: P2996R13, P3394R4
related: meta.reflection, meta.reflection.extract, meta.reflection.traits, expr.reflect, basic.splice, expr.const.reflect, class.access, class.mem, dcl.attr.annotation, basic.link, meta.member
tags: 反射, C++26, 标准库, consteval, 访问控制
updated: 2026-10-19
---

!!! tldr
    - `<meta>` 中的查询函数都是 `consteval` 函数：参数是一个反射，结果是 `bool`、字符串、另一个反射或反射的 `vector`；不适用时抛 `std::meta::exception`，而 `is_*` 谓词从不抛出。
    - 查询结果取决于求值位置：哪些声明可达、类是否已完整，都按这次常量求值能看到的程序点来判断。
    - `members_of`、`bases_of` 等必须带一个 `access_context`：`current()` 按调用处的访问权限过滤，`unchecked()` 才能看到私有成员。
    - `template_arguments_of`、`type_of` 返回的类型反射总是去掉别名；比较类型时用 `dealias` 或 `is_same_type`，不要直接 `==`。
    - `offset_of`、`size_of` 能给出位域的位偏移和基类子对象的偏移；对引用类型，`size_of` 返回的是指针的大小，与 `sizeof` 不同。

!!! note "关于本页的例子"
    本机 Clang 23 还不支持 C++26 反射（没有 `^^` 运算符，也没有 `<meta>`）。本页代码依据当前草案和标准自带的例子编写，没有经过编译，因此不标判定。为简洁起见，大多数例子省略了 `#include <meta>` 和 `using namespace std::meta;`。

## 一个例子：打印结构体的每个字段

```cpp
#include <meta>
#include <print>

struct Point { int x; int y; };

template<class T>
void dump(const T& obj) {
  constexpr auto ctx = std::meta::access_context::current();
  template for (constexpr auto m :
      std::define_static_array(std::meta::nonstatic_data_members_of(^^T, ctx)))
    std::println("{} = {}", std::meta::identifier_of(m), obj.[:m:]);
}

int main() { dump(Point{1, 2}); }   // 打印 x = 1 和 y = 2
```

`^^T` 得到类型 `T` 的反射（[[expr.reflect]]），它是 `std::meta::info` 类型的一个值。`nonstatic_data_members_of` 返回 `T` 的非静态数据成员的反射，`identifier_of` 取出成员名，`obj.[:m:]` 用拼接（[[basic.splice]]）把反射变回成员访问。`define_static_array` 把编译期的 `vector` 转成静态数组，`template for` 才能逐个展开它（见 [[meta.reflection]]）。

本页的函数都像这里的 `nonstatic_data_members_of` 和 `identifier_of` 一样，接受反射、回答关于它的问题。它们都在命名空间 `std::meta` 中，都是 `consteval` 函数，只能在常量求值中调用。不适用时（例如对一个类型问它的值），函数抛出 `std::meta::exception`，在常量求值中没有被捕获的异常会使求值失败。

反射可以代表很多种东西：值、对象、变量、函数、类型、类型别名、命名空间、模板、概念、枚举项、非静态数据成员、函数形参、注解，还有两种不对应任何声明的构造：**直接基类关系** `(D, B)`，表示类 `D` 以 `B` 为直接基类；以及 `data_member_spec` 产生的**数据成员描述**（[[g:data-member-description]]）。完整列表见 [[basic.fundamental#17]]。

## 它是什么：种类谓词 [meta.reflection.queries]

```cpp
int v;
using Int = int;
template<class T> struct Box {};

static_assert(is_variable(^^v));
static_assert(is_type(^^Int) && is_type_alias(^^Int));
static_assert(is_template(^^Box) && is_class_template(^^Box));
static_assert(!is_template(^^Box<int>));   // 模板的特化不是模板（注 5）
```

¶11 从第 11 段到第 49 段，大部分函数的规定都是同一种句式：如果 `r` 代表某种东西就返回 `true`，否则返回 `false`。这些谓词从不抛出异常，可以放心地对任何反射调用。按主题分组：

| 主题 | 函数 |
|---|---|
| 实体种类 | `is_variable`、`is_type`、`is_namespace`、`is_type_alias`、`is_namespace_alias`、`is_function`、`is_value`、`is_object`、`is_structured_binding`、`is_enumerator`、`is_annotation` |
| 模板 | `is_template`、`is_function_template`、`is_variable_template`、`is_class_template`、`is_alias_template`、`is_concept`，以及转换函数、运算符函数、字面量运算符、构造函数的模板版本 |
| 成员关系 | `is_class_member`、`is_namespace_member`、`is_nonstatic_data_member`、`is_static_member`、`is_base`、`is_bit_field`、`is_mutable_member`、`has_default_member_initializer` |
| 访问说明 | `is_public`、`is_protected`、`is_private`（类成员、无名位域、直接基类关系） |
| 虚函数 | `is_virtual`（虚成员函数或虚基类关系）、`is_pure_virtual`、`is_override`、`is_final`（final 类或 final 成员函数） |
| 函数的定义方式 | `is_deleted`、`is_defaulted`、`is_user_provided`、`is_user_declared`、`is_explicit`、`is_noexcept` |
| 特殊函数 | `is_special_member_function`、`is_constructor`、`is_default_constructor`、`is_copy_constructor`、`is_move_constructor`、`is_assignment`、`is_copy_assignment`、`is_move_assignment`、`is_destructor`、`is_conversion_function`、`is_operator_function`、`is_literal_operator` |
| 形参 | `is_function_parameter`、`is_explicit_object_parameter`、`has_default_argument`、`is_vararg_function` |
| 限定 | `is_const`、`is_volatile`、`is_lvalue_reference_qualified`、`is_rvalue_reference_qualified` |
| 存储期 | `has_static_storage_duration`、`has_thread_storage_duration`、`has_automatic_storage_duration` |
| 链接 | `has_internal_linkage`、`has_module_linkage`、`has_external_linkage`、`has_linkage`、`has_c_language_linkage` |
| 完整性 | `is_complete_type`、`is_enumerable_type` |

有几条容易误解：

- ¶17 `is_explicit` 和 `is_noexcept` 对模板永远是 `false`。模板上的 `explicit(expr)`、`noexcept(expr)` 一般依赖模板实参，在得到特化之前无法回答（注 1、注 2）。
- ¶21 `is_const`、`is_volatile` 先看 `r` 有没有类型：变量、成员、值等看 `type_of(r)`，类型则看它本身（去掉别名后）。所以 `const int` 变量的反射和类型 `const int` 的反射都得到 `true`。¶22 带 `const` 限定的函数类型 `void() const` 也得到 `true`，这一点与 `std::is_const_v` 不同。
- ¶26 有 `has_automatic_storage_duration`，但没有动态存储期的版本：反射不可能代表一个动态存储期的对象或变量（注 3）。
- ¶29 `is_complete_type(r)` 只要在求值上下文中的某个点上该类型是完整的，就返回 `true`。求值上下文的含义见下文。

## 类型、对象与常量值 [meta.reflection.queries]

### `type_of`（¶1–¶3）

¶2 `type_of(r)` 返回 `r` 所代表的东西的类型。几种特殊情况：

- 函数形参返回形参类型列表中的类型，也就是经过数组到指针等调整之后的类型（[[dcl.fct]]）；
- 注解返回它的常量值的类型；
- 直接基类关系 `(D, B)` 返回 `B`；
- 枚举项在枚举定义之外返回枚举类型本身；在 *enum-specifier* 内部（也就是枚举的花括号里）返回枚举项此时的类型，可能是底层整数类型而不是枚举（[[dcl.enum]]）。

¶1 能问类型的反射有：值、注解、对象、变量、枚举项、非静态数据成员、无名位域、直接基类关系、数据成员描述、函数形参，以及类型里不含未推导占位符（如 `auto` 返回类型还没推导出来）的非构造、非析构函数。¶3 其余反射调用 `type_of` 抛出异常。

### `object_of`：变量和它的对象（¶4–¶6）

```cpp
int x;
int& y = x;
static_assert(^^x != ^^y);                          // 两个不同的变量
static_assert(object_of(^^x) == object_of(^^y));    // 同一个对象
```

¶4 变量和对象是两回事：变量是一个声明引入的名字，对象是一块有类型的存储。`object_of` 从变量（或引用）走到对象，对对象则原样返回。¶5 它只接受静态存储期的对象；如果 `r` 代表一个引用变量，这个引用还必须可用于常量表达式，或者在当前这次常量求值中开始了生存期。

### `constant_of`：取出值（¶7–¶10）

```cpp
constexpr int a = 0, b = 0;
static_assert(^^a != ^^b);                              // 两个变量
static_assert(constant_of(^^a) == constant_of(^^b));    // 同一个值 0
static_assert(constant_of(^^a) == reflect_constant(0));
```

¶8 `constant_of(r)` 对注解返回它底层的常量；对其他反射，先把 `r` 拼接成表达式 `[: r :]`，再按类型交给 `reflect_constant_array`（数组）、`reflect_function`（函数）或 `reflect_constant`（其他）。¶9 `[: r :]` 不是合法的拼接表达式时抛出异常。

对类类型，结果是与原对象模板实参等价（[[g:template-argument-equivalent]]）的**模板形参对象**，而不是原对象：

```cpp
struct S { int m; };
constexpr S s {42};
static_assert(constant_of(^^s) != reflect_object(s));                // 不同的对象
static_assert(constant_of(^^s) == constant_of(reflect_object(s)));   // 同一个模板形参对象

consteval info fn() { constexpr int x = 42; return ^^x; }
constexpr info r = constant_of(fn());   // 错误：x 已在生存期之外
```

`reflect_constant`、`reflect_object` 的规则见 [[meta.reflection.extract]]。

## 名字与源码位置 [meta.reflection.names]

### 哪些东西有名字（¶1）

```cpp
struct S { S(); int operator+(int); };
static_assert(has_identifier(^^S));
static_assert(!has_identifier(^^int));                 // 内建类型没有标识符
static_assert(!has_identifier(^^std::vector<int>));    // 模板特化也没有
static_assert(identifier_of(^^S) == "S");
```

¶1 `has_identifier(r)` 判断 `r` 是否有一个能返回的标识符，按反射的种类逐条规定：

| 反射代表 | `has_identifier` 为 `true` 的条件 |
|---|---|
| 有用于链接目的的 typedef 名的实体（`typedef struct {} T;`） | 总是 |
| 无名实体 | 从不 |
| 类型别名 | 不是别名模板的特化 |
| 类型 | cv 无限定、不是模板特化的类类型，或 cv 无限定的枚举类型 |
| 函数 | 不是模板特化，也不是构造函数、析构函数、运算符函数、转换函数 |
| 模板 | 不是构造函数模板、运算符函数模板、转换函数模板 |
| 变量 | 不是从函数形参包实例化出来的，也不是模板特化 |
| 结构化绑定 | 不是从结构化绑定包实例化出来的 |
| 枚举项、非静态数据成员、命名空间、命名空间别名 | 总是 |
| 直接基类关系 | 看基类类型 |
| 数据成员描述 | 有名字 |
| 函数形参 | 见下一节 |

¶3 `identifier_of(r)` 返回这个标识符，`u8identifier_of(r)` 返回 UTF-8 版本（¶2）。有用于链接目的的 typedef 名的实体返回那个 typedef 名，字面量运算符返回它的 *ud-suffix*（如 `_km`），直接基类关系返回基类的名字。¶4 `has_identifier(r)` 为假，或者名字无法用目标编码表示时，抛出异常。

### 形参名：结果取决于求值位置（¶1.7–¶1.8）

C++ 允许同一个函数的不同声明给形参起不同的名字，或者不起名字。¶1.8 规定，形参有标识符，当且仅当在所有可达的声明中，至少有一个为它起了名字，而且没有任何声明用了别的名字：

```cpp
void fun(int);
constexpr std::meta::info r = parameters_of(^^fun)[0];
static_assert(!has_identifier(r));     // 目前所有声明都没有给名字

void fun(int x);
static_assert(has_identifier(r));      // 现在有了 x

void fun(int x);
static_assert(has_identifier(r));      // 同名，仍然一致

void poison() {
  void fun(int y);                     // 块作用域声明用了另一个名字
}
static_assert(!has_identifier(r));     // 名字不一致：没有标识符
```

同一个 `r`，在文件的不同位置得到不同的答案。原因是查询按**求值上下文**（[[g:evaluation-context]]，[[expr.const.reflect]]）判断哪些声明可达：大致说，就是当前这次常量求值所在的程序点，加上它的实例化上下文能看到的点。后面的 `is_complete_type`、`members_of`、`annotations_of` 也遵循同样的规则。

¶1.7 另一条规则：函数模板特化的形参如果来自一个形参包（如 `template<class... Ts> void f(Ts... ts)` 的某个 `ts`），它没有标识符。

### `display_string_of` 与 `source_location_of`（¶5–¶8）

¶5 `display_string_of(r)` 对任何反射都能调用，返回一个由实现定义的字符串。¶6 推荐实践是返回适合识别该构造的文字，例如 `std::vector<int>`。它适合用于诊断信息和日志，不能用于程序逻辑，因为内容不可移植。

¶7 `source_location_of(r)` 对值、非类非枚举的类型、全局命名空间和数据成员描述返回空的 `source_location{}`，其余情况返回由实现定义的位置。¶8 推荐返回可达的定义所在处。

## 在程序结构中导航 [meta.reflection.queries]

### 父级：`parent_of`（¶50–¶53）

```cpp
struct I { };
struct F : I {
  union { int o; };
  enum N { A };
};
constexpr auto ctx = std::meta::access_context::current();

static_assert(parent_of(^^F) == ^^::);
static_assert(parent_of(bases_of(^^F, ctx)[0]) == ^^F);
static_assert(is_union_type(parent_of(^^F::o)));
static_assert(parent_of(^^F::N) == ^^F);
static_assert(parent_of(^^F::A) == ^^F::N);
```

¶51 父级一般是包含该声明的最内层类、函数或命名空间。三种例外：匿名联合体的成员的父级是那个匿名联合体，枚举项的父级是它的枚举类型（即使是无作用域枚举），直接基类关系 `(D, B)` 的父级是 `D`。

¶50 `has_parent(r)` 对全局命名空间、C 语言链接的实体、非类非枚举的类型返回 `false`。¶52 对这些调用 `parent_of` 抛出异常。

### 去掉别名：`dealias`（¶54–¶55）

```cpp
using X = int;
using Y = X;
static_assert(^^Y != ^^int);            // 别名的反射与类型的反射不相等
static_assert(dealias(^^Y) == ^^int);   // 别名的别名也一路剥到底
```

¶54 `dealias` 把类型别名和命名空间别名换成它们代表的实体，其他反射原样返回。反射的 `==` 比较的是代表的构造本身，别名和类型是两个不同的构造，所以比较类型之前通常要先 `dealias`。

### 模板与模板实参（¶56–¶61）

```cpp
template<class T, class U = T> struct Pair { };
template<class T> using PairPtr = Pair<T*>;

static_assert(template_of(^^Pair<int>) == ^^Pair);
static_assert(template_arguments_of(^^Pair<int>).size() == 2);   // 默认实参也计入
static_assert(template_of(^^PairPtr<int>) == ^^PairPtr);         // 别名模板的特化
static_assert(template_arguments_of(^^PairPtr<int>).size() == 1);

struct S { };
int i;
template<int, int&, S, template<class> class> struct X { };
constexpr auto T = ^^X<1, i, S{}, PairPtr>;
static_assert(is_value(template_arguments_of(T)[0]));     // 1：值
static_assert(is_object(template_arguments_of(T)[1]));    // i：对象
static_assert(is_object(template_arguments_of(T)[2]));    // S{}：模板形参对象
static_assert(template_arguments_of(T)[3] == ^^PairPtr);
```

¶56 `has_template_arguments(r)` 判断 `r` 是否是函数模板、变量模板、类模板或别名模板的特化。¶57 `template_of` 返回它的模板，¶59 `template_arguments_of` 按顺序返回模板实参的反射：

- 类型实参总是代表类型，不代表别名（注 7）；
- 模板模板实参代表那个模板；
- 常量实参中，引用类型的形参得到所引用的对象或函数，类类型的形参得到模板形参对象，其他得到值。

### 形参与返回类型（¶62–¶67）

¶62 `parameters_of(r)` 对函数返回各形参的反射，对函数类型返回形参类型列表中各类型的反射。¶66 `return_type_of(r)` 返回函数或函数类型的返回类型。

¶64 `variable_of(r)` 把形参的反射换成**形参变量**的反射。形参属于函数的声明，在每个声明中可能叫不同的名字；形参变量属于函数定义，在函数体里被使用。¶65 所以 `variable_of` 只能在该函数的函数体内（准确地说，在它的函数形参作用域内）调用。

## 访问控制 [meta.reflection.access.context]

### 为什么查询成员要带访问语境

```cpp
class Account {
  int balance;
public:
  int id;
};
// 在命名空间作用域中：
static_assert(nonstatic_data_members_of(^^Account,
                access_context::current()).size() == 1);     // 只有 id
static_assert(nonstatic_data_members_of(^^Account,
                access_context::unchecked()).size() == 2);   // balance 也在内
```

如果反射能无条件地列出私有成员，访问控制就形同虚设。所以 `members_of` 一类函数都要求调用者显式给出一个**访问语境**（[[g:access-context]]）。默认写法 `current()` 与普通代码一样受访问控制约束；想越过它，必须写出 `unchecked()`，这在代码审查中一目了然。

### `access_context`（¶1–¶11）

```cpp
struct access_context {
  access_context() = delete;
  consteval info scope() const;
  consteval info designating_class() const;
  static consteval access_context current() noexcept;
  static consteval access_context unprivileged() noexcept;
  static consteval access_context unchecked() noexcept;
  consteval access_context via(info cls) const;
};
```

¶1 一个访问语境由两部分组成：作用域，即从哪个命名空间、类或函数出发做访问检查；以及可选的**指名类**（designating class，[[g:designating-class]]），即访问成员时经由的那个类（[[class.access.base]]），相当于 `p->T::m` 中的 `T`。

| 构造方式 | 作用域 | 指名类 | 效果 |
|---|---|---|---|
| `current()` | 调用处所在的函数、类或命名空间 | 空反射 | 与写在调用处的普通代码相同 |
| `unprivileged()` | 全局命名空间 | 空反射 | 只能访问 public 成员 |
| `unchecked()` | 空反射 | 空反射 | 不做访问检查 |
| `ctx.via(cls)` | 与 `ctx` 相同 | `cls` | 指定经由哪个类访问成员 |

¶3 `access_context` 是结构化类型，可以用作常量模板实参。¶6 `current()` 和下文的 `current_function()` 一样取的是调用处的信息，不能取地址；在模板中它是值依赖的（[[g:value-dependent]]），每个特化得到自己的结果。¶11 `via(cls)` 要求 `cls` 是空反射或完整的类类型。

### `is_accessible`（[meta.reflection.access.queries]）

```cpp
consteval access_context fn() { return access_context::current(); }

class Cls {
  int mem;
  friend consteval access_context fn();
public:
  static constexpr auto r = ^^mem;
};

static_assert( is_accessible(Cls::r, fn()));                        // 友元函数中
static_assert(!is_accessible(Cls::r, access_context::current()));   // 命名空间作用域中
static_assert( is_accessible(Cls::r, access_context::unchecked()));
```

`is_accessible(r, ctx)` 回答：从 `ctx` 的作用域出发，经由 `ctx` 的指名类，能不能访问 `r`。判断步骤：

1. 不是类成员、也不是直接基类关系的反射，总是可访问。无名位域被当作具有相同访问权限的数据成员。
2. 如果 `r` 根本不是指名类的成员（没有指定指名类时取 `r` 所在的类），不可访问。
3. 作用域为空（`unchecked()`）时，可访问。
4. 否则按 [[class.access.base]] 的规则判断，判断时忽略 using 声明的影响，也不考虑声明从那个点是否可达（注 2）。

第 6–10 段还提供了三个汇总函数：`has_inaccessible_nonstatic_data_members`、`has_inaccessible_bases` 和 `has_inaccessible_subobjects`。它们用 `unchecked()` 列出全部成员或基类，再看其中是否有在 `ctx` 下不可访问的。写逐成员序列化、比较之类的通用代码时，可以先用它们决定能否处理这个类。对闭包类型调用第一个函数会抛出异常，因为闭包有哪些成员由实现决定。

## 列出成员 [meta.reflection.member.queries]

### `members_of` 返回什么

```cpp
class B {};
struct S : B {
private:
  class I;
public:
  int m;
};

static_assert(members_of(^^S, access_context::current()).size() == 7);     // 6 个特殊成员 + m
static_assert(members_of(^^S, access_context::unchecked()).size() == 8);   // 再加上私有的 S::I
```

¶4 `members_of(r, ctx)` 返回类或命名空间的成员中，可访问并且可以被表示的那些，按声明顺序排列。注 2 补充了两点：基类不是成员，不在结果中；隐式声明的特殊成员排在所有用户声明的成员之后。上例中 `S` 的六个特殊成员（默认构造、复制构造、移动构造、复制赋值、移动赋值、析构）都是隐式声明的，所以排在 `m` 后面。

¶3 下面这些成员不会出现在结果里（注 1）：

- 无作用域枚举的枚举项（它们是外层作用域的成员，但要通过 `enumerators_of` 获取）；
- 模板的特化和偏特化；
- 闭包类型（lambda 的类型）；
- 友元声明引入的函数；
- 嵌套匿名联合体内部的变体成员；
- 类型中含有未推导占位符的变量和函数，约束不满足的函数，以及没被选中的预期析构函数。

¶5 `r` 去掉别名后必须是从求值上下文某处看已完整的类，或者是命名空间，否则抛出异常。类还会额外包含可访问的无名位域。

<details class="fine" markdown="1"><summary>members-of 的精确定义（¶1–¶3）</summary>

¶1 声明 `D` *members-of-precedes* 点 `P`，如果 `D` 在 `P` 之前，或者在这样一个点之前：`P` 处于某个最外层类的完整类上下文（[[g:complete-class-context]]）中时，那个类的 *class-specifier* 结束之后紧接着的点。

¶2 类或命名空间 `Q` 的成员 `M` 的声明 `D` 是 *Q-members-of-eligible* 的，当且仅当：`D` 的宿主作用域是 `Q` 的作用域；`D` 不是友元声明；`M` 不是闭包类型，也不是模板特化；如果 `Q` 是非闭包类，`M` 是 `Q` 的直接成员，且不是嵌套匿名联合体的变体成员；如果 `Q` 是闭包类型，`M` 是函数调用运算符或其模板。闭包的其他成员是否合格由实现定义。

¶3 `M` 从 `P` 是 *Q-members-of-representable* 的，当且仅当它有一个合格声明 members-of-precedes `P`，并且 `M` 是类或枚举类型、类型别名、类模板、函数模板、变量模板、别名模板、概念、类型中不含未推导占位符的变量、满足约束等条件的函数、非静态数据成员、命名空间或命名空间别名。

¶6 的例子还演示了模块的影响：模块接口中有内部链接的 `static int l;` 在导入它的翻译单元里不可达，所以那里的 `members_of(^^NS, ...)` 少一个元素。

</details>

### 可枚举类型（[meta.reflection.queries] ¶30–¶32）

```cpp
class S;
enum class E;
static_assert(!is_enumerable_type(^^S));
static_assert(!is_enumerable_type(^^E));

class S {
  void mfn() {
    static_assert(is_enumerable_type(^^S));    // 函数体是完整类上下文
  }
  static_assert(!is_enumerable_type(^^S));     // 类定义内部的其他位置
};
static_assert(is_enumerable_type(^^S));

enum class E {
  A = is_enumerable_type(^^E) ? 1 : 2          // 枚举说明符内部：不可枚举
};
static_assert(is_enumerable_type(^^E));
static_assert(static_cast<int>(E::A) == 2);
```

¶30 列出成员之前，要先确定成员已经全部声明完。类型 `T` 从点 `P` 是**可枚举的**（[[g:enumerable-type]]），如果它是在 `P` 处完整的类类型，或者是定义从 `P` 可达、而 `P` 又不在这个定义的花括号内的枚举类型。`members_of` 要求类完整，`enumerators_of` 要求枚举可枚举。

### 便捷函数（¶7–¶16）

| 函数 | 返回 |
|---|---|
| `bases_of(type, ctx)` | 可访问的直接基类关系，按 *base-specifier-list* 中的顺序 |
| `static_data_members_of(type, ctx)` | `members_of` 中的变量 |
| `nonstatic_data_members_of(type, ctx)` | `members_of` 中的非静态数据成员 |
| `subobjects_of(type, ctx)` | 先是 `bases_of`，再是 `nonstatic_data_members_of` |
| `enumerators_of(type_enum)` | 全部枚举项，按声明顺序；不带访问语境，因为枚举项没有访问控制 |

## 我在哪里：作用域识别 [meta.reflection.scope]

```cpp
consteval info current_function();
consteval info current_class();
consteval info current_namespace();
```

¶1 这三个函数返回的是它们被调用处所在的函数、类和命名空间。¶2 因此它们都不能取地址：通过函数指针间接调用就没有调用处可言了。

```cpp
consteval std::string_view caller_name(
    std::meta::info f = std::meta::current_function()) {
  return std::meta::identifier_of(f);
}

void work() {
  static_assert(caller_name() == "work");   // 不是 "caller_name"
}
```

¶3 默认实参中的 `current_function()` 按调用 `caller_name` 的位置计算，所以得到的是调用者 `work`。反射值只能存在于常量求值中，所以带 `info` 形参的函数要声明为 `consteval`（[[expr.const.const]]）。这与 `std::source_location::current()` 用作默认实参是同一个思路。¶3 用 *eval-point* 精确规定了调用处到底是哪里，其他几种特殊位置是：

- 默认成员初始化器中：按使用它的聚合初始化处，或使用它的构造函数（继承构造函数则是类作用域）计算；
- 函数声明的形参列表中、尾随 *requires-clause* 中：按函数声明所在的外层作用域计算；
- lambda 的尾随返回类型、尾随 *requires-clause* 中：按 lambda 引入符所在点计算；
- `consteval` 块（[[dcl.pre]]）内部：按最外层 `consteval` 块所在的作用域计算。

¶5 得到的位置再向外找到最近的函数、类或命名空间。¶8 `current_function()` 在它不是函数时抛出异常；¶12 `current_class()` 在类中返回类，在成员函数中返回其所属的类，¶13 其他情况抛出异常；¶16 `current_namespace()` 返回最近的外围命名空间。¶6 在模板中，三者都是值依赖的，每个特化得到各自的结果。

## 布局 [meta.reflection.layout]

```cpp
struct member_offset {
  ptrdiff_t bytes;
  ptrdiff_t bits;
  constexpr ptrdiff_t total_bits() const;      // bytes * CHAR_BIT + bits
  auto operator<=>(const member_offset&) const = default;
};
consteval member_offset offset_of(info r);
consteval size_t size_of(info r);
consteval size_t alignment_of(info r);
consteval size_t bit_size_of(info r);
```

```cpp
struct Flags {
  unsigned a : 3;
  unsigned b : 5;
};
static_assert(offset_of(^^Flags::b).total_bits() == 3);   // 常见 ABI 上如此
static_assert(bit_size_of(^^Flags::b) == 5);
```

位域在分配单元内的排列方式由实现定义（[[class.bit]]），所以第一条断言的结果取决于 ABI；宽度 5 则是确定的。

¶2 `offset_of(r)` 计算从 `parent_of(r)` 类型的完整对象起点到 `r` 对应子对象的位偏移 `V`，¶3 返回 `{V / CHAR_BIT, V % CHAR_BIT}`。与 `offsetof` 宏相比，它能处理位域（给出位级偏移）和基类子对象，也不要求类是标准布局的。¶4 它适用于非静态数据成员、无名位域和直接基类关系，只有抽象类的虚基类关系除外。

¶5 `size_of(r)` 对类型返回 `sizeof`，对非静态数据成员和数据成员描述返回其类型的 `sizeof`，对其他有类型的东西返回 `size_of(type_of(r))`。对引用类型 `T&` 它返回 `size_of(^^T*)`，即一个指针的大小，大致相当于引用作为成员时占用的空间；而 `sizeof(T&)` 是 `sizeof(T)`。注 1 还指出，空基类的直接基类关系 `b` 也有 `size_of(b) > 0`：返回的是基类类型的 `sizeof`，不是它在派生类中实际占用的大小。¶6 对位域和不完整类型调用 `size_of` 抛出异常。

¶7 `alignment_of(r)` 对类型返回对齐要求（引用同样按指针计算），对变量或对象考虑 `alignas`，对非静态数据成员返回它在完整对象中实际的对齐，对数据成员描述返回其中的对齐值（没有时取类型的对齐）。

¶9 `bit_size_of(r)` 对位域返回宽度，其他情况返回 `CHAR_BIT * size_of(r)`。

## 注解 [meta.reflection.annotation]

注解（[[g:annotation]]）是 C++26 新增的 `[[=expr]]` 语法（[[dcl.attr.annotation]]，[[P3394R4]]）：把一个常量值附加到声明上，供反射读取，不影响程序的其他语义。

```cpp
struct Option { bool value; };
struct C {
  [[=Option{true}]] int a;
  [[=Option{false}]] int b;
};
static_assert(extract<Option>(annotations_of(^^C::a)[0]).value);
static_assert(!extract<Option>(annotations_of(^^C::b)[0]).value);
```

¶2 `annotations_of(item)` 返回作用于 `item` 的全部注解：

- 函数的注解从它所有可达的声明上收集，函数形参的注解从每个声明中该形参上收集；
- 直接基类关系取对应 *base-specifier* 上的注解；
- 其他实体取它每个可达声明上的注解。

¶2 结果按出现顺序排列，同一翻译单元中的注解排在一起；来自不同翻译单元的注解之间的顺序未指明（注 1）。¶3 可以查询注解的有类型、类型别名、变量、函数、函数形参、命名空间、枚举项、直接基类关系和非静态数据成员。

```cpp
[[=1]] void f();
[[=2, =3]] void g();
void g [[=4]] ();

static_assert(annotations_of(^^f).size() == 1);
static_assert(annotations_of(^^g).size() == 3);                 // 两个声明上的注解都算
static_assert([: constant_of(annotations_of(^^g)[0]) :] == 2);
static_assert(extract<int>(annotations_of(^^g)[2]) == 4);

template<class T> struct [[=42]] D { };
constexpr std::meta::info a1 = annotations_of(^^D<int>)[0];
constexpr std::meta::info a2 = annotations_of(^^D<char>)[0];
static_assert(a1 != a2);                                        // 不同特化上的注解是不同的注解
static_assert(constant_of(a1) == constant_of(a2));              // 但值相同

[[=1]] int x, y;
static_assert(annotations_of(^^x)[0] == annotations_of(^^y)[0]);   // 同一个声明中的同一个注解
```

¶5 `annotations_of_with_type(item, type)` 只保留类型与 `type` 相同（忽略顶层 `const`）的注解。这是最常见的用法：序列化框架用它读取字段选项，命令行解析库用它读取参数描述。

## 常见误解

!!! pitfall "把查询结果当成全局不变的事实"
    `has_identifier`、`is_complete_type`、`members_of`、`annotations_of` 的结果都取决于求值上下文中哪些声明可达。把结果存进 `constexpr` 变量，得到的是那个位置的快照，之后新增的声明不会反映进去。

!!! pitfall "以为 `members_of` 能看到全部成员"
    在类外用 `access_context::current()` 调用时，私有和受保护的成员都会被过滤掉，而且没有任何提示。需要全部成员时显式使用 `unchecked()`，或者先用 `has_inaccessible_nonstatic_data_members` 检查。

!!! pitfall "用 `==` 比较类型"
    `^^Int == ^^int` 在 `Int` 是 `int` 的别名时为 `false`。`template_arguments_of`、`type_of` 的结果已经去掉了别名，但用户自己写的 `^^Int` 没有。比较前先 `dealias`，或者用 [[meta.reflection.traits]] 中的 `is_same_type`。
