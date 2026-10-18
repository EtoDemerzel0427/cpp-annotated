---
title: 反射查询
summary: <meta> 中"读取程序"的函数族——名字与位置（has_identifier、identifier_of、display_string_of）、单个反射的查询（type_of、object_of、constant_of、is_*、parent_of、dealias、template_arguments_of、parameters_of）、作用域识别与 eval-point、access_context 与可访问性查询、members_of 的"可枚举"规则、布局查询（offset_of、size_of、alignment_of、bit_size_of）、注解反射
status: draft
covers: meta.reflection.names, meta.reflection.queries, meta.reflection.scope, meta.reflection.access.context, meta.reflection.access.queries, meta.reflection.member.queries, meta.reflection.layout, meta.reflection.annotation
since: c++26
papers: P2996R13, P3394R4
related: meta.reflection, meta.reflection.extract, meta.reflection.traits, expr.reflect, basic.splice, expr.const.reflect, class.access, class.mem, dcl.attr.annotation, basic.link, meta.member
tags: 反射, C++26, 标准库, consteval, 访问控制
updated: 2026-10-18
---

!!! warning "未经本地验证"
    本地 Clang 23 不支持 C++26 反射。本页代码依据当前草案与标准自带例子编写，未经编译验证，不标判定。

本页覆盖 [meta.reflection] 中所有"**读**"程序的函数：给定一个 `std::meta::info`，问它叫什么、是什么、属于谁、有哪些成员、放在内存哪里、带了什么注解。它们几乎都是 `consteval` 函数，失败时抛 `meta::exception`（[[meta.reflection]]）。

本页大量使用核心语言中的"反射可以代表什么"：值、对象、变量、函数、类型、类型别名、命名空间、命名空间别名、模板、概念、枚举项、非静态数据成员、无名位域、**直接基类关系** `(D, B)`、**数据成员描述** `(T, N, A, W, NUA, ANN)`（[[g:data-member-description]]）、函数形参、注解（[[basic.fundamental]] ¶17）。

## 一、名字与位置（[meta.reflection.names]）

### `has_identifier`（¶1）

"这个反射有没有一个能用的标识符"，按反射的种类逐条判定（¶1.1–¶1.14），要点：

| 反射代表 | `has_identifier` |
|---|---|
| 有"用于链接目的的 typedef 名"的实体 | `true` |
| 无名实体 | `false` |
| 类型别名 | `!has_template_arguments(r)`（别名模板的特化没有标识符）|
| 类型 | cv 无限定、非模板特化的类类型，或 cv 无限定的枚举类型 → `true`；其他（`int`、`const S`、`vector<int>`）→ `false` |
| 函数 | 非模板特化，且不是构造函数、析构函数、运算符函数、转换函数 |
| 模板 | 不是构造函数模板、运算符函数模板、转换函数模板 |
| 函数形参 | 见下 |
| 变量 | 不是从函数形参包实例化出来的，且不是模板特化 |
| 结构化绑定 | 不是从结构化绑定包实例化出来的 |
| 枚举项、非静态数据成员、命名空间、命名空间别名 | `true` |
| 直接基类关系 | 看基类类型 |
| 数据成员描述 | 名字 `N` 不是 ⊥ |

**函数形参**的规则（¶1.8）最有意思：C++ 允许同一个函数的不同声明给形参起不同的名字，甚至不起名字。标准规定：考虑从求值上下文可达的、声明该函数（或其模板）的所有声明 `S`（忽略显式实例化），**当且仅当**存在一个声明为该形参引入了名字 `N`，并且没有任何声明使用别的名字时，才有标识符。标准例子：

```cpp
void fun(int);
constexpr std::meta::info r = parameters_of(^^fun)[0];
static_assert(!has_identifier(r));     // 目前所有可达声明都没给名字

void fun(int x);
static_assert(has_identifier(r));      // 现在有了 x

void fun(int x);
static_assert(has_identifier(r));      // 同名，仍然一致

void poison() {
  void fun(int y);                     // 一个块作用域声明用了另一个名字
}
static_assert(!has_identifier(r));     // 名字不一致：无标识符
```

注意同一个 `r` 在不同位置给出不同结果——反射查询的结果取决于**求值上下文**（[[g:evaluation-context]]，[[expr.const.reflect]]）中哪些声明可达。

### `identifier_of` / `u8identifier_of`（¶2–¶4）

返回标识符（以普通字面量编码或 UTF-8 编码的 NTMBS）。几个特殊情况：有链接用 typedef 名的实体返回那个 typedef 名；字面量运算符返回 *ud-suffix*；函数形参返回上述"一致的名字"；直接基类关系返回基类的标识符；数据成员描述返回 `N`。¶4 *Throws*：`has_identifier(r)` 为假，或标识符无法用目标编码表示时，抛 `meta::exception`。

### `display_string_of` 与 `source_location_of`（¶5–¶8）

- `display_string_of(r)`：**由实现定义**的字符串；推荐实践是返回适合识别该构造的字符串（例如 `"std::vector<int>"`）。它可以用于任何反射（包括 `^^int`、模板特化），但内容不可移植——不要拿它做程序逻辑。
- `source_location_of(r)`：对值、非类非枚举的类型、全局命名空间、数据成员描述返回 `source_location{}`；否则返回由实现定义的位置，推荐为可达的定义处。

## 二、单个反射的查询（[meta.reflection.queries]）

### 类型、对象与常量：`type_of`、`object_of`、`constant_of`

说明用函数 *has-type*`(r)`（¶1）：`r` 代表值、注解、对象、变量、（类型中不含未推导占位符、且不是构造/析构函数的）函数、枚举项、非静态数据成员、无名位域、直接基类关系、数据成员描述或函数形参时为真。

**`type_of(r)`**（¶2–¶3）：返回"它的类型"。函数形参返回形参类型列表中的类型（即调整后的类型）；注解返回其常量的类型；枚举项有讲究——若在枚举定义可达且**不在**枚举说明符内部的位置求值，返回枚举类型本身；在枚举说明符内部，返回枚举项在右花括号之前的类型（[[dcl.enum]]，此时可能是底层类型而非枚举）；直接基类关系 `(D, B)` 返回 `B`。*has-type* 为假时抛异常。

**`object_of(r)`**（¶4–¶6）：对象返回自身；引用返回所引用的对象；变量返回其声明的对象。只接受**静态存储期**的对象，引用变量还须可用于常量表达式或在当前求值中开始生存期。标准例子说明了变量与对象的区别：

```cpp
int x;
int& y = x;
static_assert(^^x != ^^y);                          // 两个不同的变量
static_assert(object_of(^^x) == object_of(^^y));    // 同一个对象
```

**`constant_of(r)`**（¶7–¶10）：取出"常量值"的反射。对注解返回其底层常量；否则等价于对 `[: r :]` 做 `reflect_constant_array`（数组）、`reflect_function`（函数）或 `reflect_constant`（其他）——见 [[meta.reflection.extract]]。于是两个值都为 0 的不同 `constexpr` 变量，`constant_of` 结果相等；对类类型，`constant_of(^^s)` 代表的是与 `s` **模板实参等价**的模板形参对象，而不是 `s` 本身：

```cpp
struct S { int m; };
constexpr S s {42};
static_assert(constant_of(^^s) != reflect_object(s));                 // 不同的对象
static_assert(constant_of(^^s) == constant_of(reflect_object(s)));    // 同一个模板形参对象

consteval info fn() { constexpr int x = 42; return ^^x; }
constexpr info r = constant_of(fn());   // error: x 已在生存期之外
```

### 布尔谓词（¶11–¶49）

这一大串 `is_*`/`has_*` 都是"若 `r` 代表某种东西则为真，否则为假"，**从不抛异常**。按主题分组：

| 主题 | 函数 |
|---|---|
| 访问说明 | `is_public`、`is_protected`、`is_private`（类成员、无名位域、直接基类关系）|
| 虚函数 | `is_virtual`（虚成员函数或虚基类关系）、`is_pure_virtual`、`is_override`、`is_final`（final 类或 final 成员函数）|
| 函数定义方式 | `is_deleted`、`is_defaulted`、`is_user_provided`、`is_user_declared`、`is_explicit`、`is_noexcept` |
| 成员种类 | `is_bit_field`、`is_enumerator`、`is_annotation`、`is_mutable_member` |
| cv 与引用限定 | `is_const`、`is_volatile`、`is_lvalue_reference_qualified`、`is_rvalue_reference_qualified` |
| 存储期 | `has_static_storage_duration`、`has_thread_storage_duration`、`has_automatic_storage_duration` |
| 链接 | `has_internal_linkage`、`has_module_linkage`、`has_external_linkage`、`has_c_language_linkage`、`has_linkage` |
| 完整性 | `is_complete_type`、`is_enumerable_type` |
| 实体种类 | `is_variable`、`is_type`、`is_namespace`、`is_type_alias`、`is_namespace_alias`、`is_function`、`is_value`、`is_object`、`is_structured_binding` |
| 特殊函数 | `is_conversion_function`、`is_operator_function`、`is_literal_operator`、`is_special_member_function`、`is_constructor`、`is_default_constructor`、`is_copy_constructor`、`is_move_constructor`、`is_assignment`、`is_copy_assignment`、`is_move_assignment`、`is_destructor` |
| 形参 | `is_function_parameter`、`is_explicit_object_parameter`、`has_default_argument`、`is_vararg_function` |
| 模板 | `is_template`、`is_function_template`、`is_variable_template`、`is_class_template`、`is_alias_template`、`is_conversion_function_template`、`is_operator_function_template`、`is_literal_operator_template`、`is_constructor_template`、`is_concept` |
| 成员关系 | `is_class_member`、`is_namespace_member`、`is_nonstatic_data_member`、`is_static_member`、`is_base`、`has_default_member_initializer` |

值得注意的几条：

- **`is_explicit`、`is_noexcept` 对模板永远为假**（注 1、注 2）：模板的 `explicit(expr)`/`noexcept(expr)` 一般依赖模板实参，"在一般情况下无法回答"。
- **`is_const`/`is_volatile`**（¶21–¶22）：若 *has-type*`(r)`，看 `type_of(r)`；否则看 `dealias(r)`。所以对 `const int` 变量的反射为真，对类型 `const int` 的反射也为真，对 `void() const` 这样的函数类型同样为真（与 `std::is_const_v` 不同！）。
- **`has_automatic_storage_duration`** 存在，但注 3 说明：不可能得到代表**动态**存储期对象或变量的反射。
- **`is_complete_type`**（¶29）：在求值上下文中某个点上类型不是不完整的。
- **`is_enumerable_type`**（¶30–¶32）：类型 `T` 从点 `P` **可枚举**（[[g:enumerable-type]]），当且仅当它是在 `P` 完整的类类型，或者是其定义可达、且 `P` 不在其枚举说明符内部的枚举类型。这决定了 `members_of`、`enumerators_of` 能否调用。标准例子：

    ```cpp
    class S;
    enum class E;
    static_assert(!is_enumerable_type(^^S));
    static_assert(!is_enumerable_type(^^E));

    class S {
      void mfn() {
        static_assert(is_enumerable_type(^^S));    // 完整类语境：S 视为完整
      }
      static_assert(!is_enumerable_type(^^S));     // 类定义内部、非完整类语境
    };
    static_assert(is_enumerable_type(^^S));

    enum class E {
      A = is_enumerable_type(^^E) ? 1 : 2          // 枚举说明符内部：不可枚举
    };
    static_assert(is_enumerable_type(^^E));
    static_assert(static_cast<int>(E::A) == 2);
    ```

- **`is_template`**（注 5）：模板特化不是模板——`is_template(^^std::vector)` 为真，`is_template(^^std::vector<int>)` 为假。

### 导航：`parent_of`、`dealias`、模板与形参

- **`has_parent` / `parent_of`**（¶50–¶53）：全局命名空间、C 语言链接的实体、非类非枚举的类型没有父级；其他语言链接由实现定义。父级是：匿名联合体的直接成员 → 最内层匿名联合体；枚举项 → 枚举类型；直接基类关系 `(D, B)` → `D`；否则是包含声明目标作用域的最内层类、函数或命名空间（`consteval` 块的闭包会被跳过，¶51.4.1）。
- **`dealias`**（¶54–¶55）：剥掉类型别名和命名空间别名，返回底层实体；`dealias(^^Y) == ^^int`，即使 `Y` 是别名的别名。
- **`has_template_arguments` / `template_of` / `template_arguments_of`**（¶56–¶61）：对函数模板、变量模板、类模板、别名模板的特化可用。`template_arguments_of` 返回的反射：类型实参总是代表**类型而非别名**（注 7）；模板模板实参代表那个模板；常量实参中，引用形参 → 所引用的对象或函数，类类型形参 → 模板形参对象，其他 → 值。

    ```cpp
    template<class T, class U = T> struct Pair { };
    template<class T> using PairPtr = Pair<T*>;

    static_assert(template_of(^^Pair<int>) == ^^Pair);
    static_assert(template_arguments_of(^^Pair<int>).size() == 2);   // 默认实参也计入
    static_assert(template_of(^^PairPtr<int>) == ^^PairPtr);         // 别名模板特化保留别名身份
    static_assert(template_arguments_of(^^PairPtr<int>).size() == 1);
    ```

- **`parameters_of`**（¶62–¶63）：对函数返回形参的反射（按声明顺序）；对函数**类型**返回形参类型列表中各类型的反射。
- **`variable_of`**（¶64–¶65）：从"形参"反射得到"形参变量"反射——只能在该函数的函数形参作用域内（即函数体中）调用。形参（属于函数声明）与形参变量（属于某次调用的定义）是两个概念。
- **`return_type_of`**（¶66–¶67）：函数或函数类型的返回类型。

## 三、作用域识别（[meta.reflection.scope]）

```cpp
consteval info current_function();
consteval info current_class();
consteval info current_namespace();
```

¶1–¶2：它们获取**被调用处**的信息，因此都**不是**可寻址函数（取地址再调用就失去了"调用处"）。

难点在于"调用处"到底是哪里。¶3 定义了 *eval-point*`(P)`：

- 默认成员初始化器中的表达式 → 使用该初始化器的聚合初始化处、继承构造函数的类作用域，或使用它的构造函数的形参作用域；
- 默认实参中的表达式 → **函数调用处**；
- 函数声明的形参作用域中、位于其声明点之前或尾随 *requires-clause* 中 → 声明所在的外层作用域；
- lambda 的尾随返回类型或尾随 *requires-clause* 中 → lambda 引入符所在点；
- `consteval` 块（[[dcl.pre]]）内部 → 最外层 `consteval` 块所在的作用域；
- 否则就是 `P` 本身。

¶4–¶5 再由 *ctx-scope* 把块作用域向外归约到最近的函数形参作用域、类作用域或命名空间作用域，得到 *CURRENT-SCOPE*`(P)`。于是：

- `current_function()`（¶6–¶9）返回 *CURRENT-SCOPE*，若它不是函数则抛异常；
- `current_class()`（¶10–¶13）：是类则返回它，是成员函数则返回其所属类，否则抛异常；
- `current_namespace()`（¶14–¶16）：是命名空间则返回它，否则返回其最近的外围命名空间。

三者在模板中都是**值依赖**的（[[temp.dep.constexpr]]）：同一份模板代码在不同特化中给出不同答案。"默认实参在调用处求值"这一规则让 `void log(info where = current_function())` 这样的写法能拿到**调用者**——这正是 `std::source_location::current()` 的同款技巧。

## 四、访问控制（[meta.reflection.access.context]、[meta.reflection.access.queries]）

### `access_context`

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

¶1–¶2：**访问语境**（[[g:access-context]]）代表"从哪个命名空间、类或函数出发去做访问检查"，外加一个可选的**指定类**（designating class，[[g:designating-class]]，[[class.access.base]]）。¶3：它是结构化的非聚合类型，可作常量模板实参；当 `scope()` 或 `designating_class()` 是仅限编译期的值时，它也是。

| 工厂 | 作用域 | 指定类 | 含义 |
|---|---|---|---|
| `current()` | *CURRENT-SCOPE*（调用处）| 空反射 | 像普通代码一样，按当前位置的访问权限 |
| `unprivileged()` | 全局命名空间 | 空反射 | 只能看到 public |
| `unchecked()` | 空反射 | 空反射 | 不做访问检查，看到一切 |
| `ctx.via(cls)` | 不变 | `cls` | 指定通过哪个类去命名成员（`cls` 须为空或完整类类型）|

**为什么 `members_of` 必须带访问语境？** 因为反射如果能无条件枚举私有成员，就是对封装的公开破坏。P2996 的设计把选择权显式交给调用者：默认（`current()`）尊重访问控制，要越过它必须明确写出 `unchecked()`——在代码审查中一目了然。`current()` 同样不可寻址，且在模板中值依赖。

### `is_accessible` 与"有不可访问的子对象"

`is_accessible(r, ctx)`（¶1–¶5）：

1. 无名位域被当作具有相同访问权限的假想数据成员；
2. 不是类成员也不是直接基类关系的反射 → `true`；
3. 若 `r` 根本不是*指定类*（`ctx.designating_class()`，为空则取 `r` 的父类）的成员（或其基类关系不在其中）→ `false`；
4. `ctx.scope()` 为空（`unchecked`）→ `true`；
5. 否则，按 [[class.access.base]] 判断在 `ctx.scope()` 所对应的程序点上是否可访问——**忽略 using 声明的影响**；注 2：可访问性判断不考虑声明从那个点是否可达。

```cpp
consteval access_context fn() { return access_context::current(); }

class Cls {
  int mem;
  friend consteval access_context fn();
public:
  static constexpr auto r = ^^mem;
};

static_assert( is_accessible(Cls::r, fn()));                        // 友元函数中的语境
static_assert(!is_accessible(Cls::r, access_context::current()));   // 命名空间作用域
static_assert( is_accessible(Cls::r, access_context::unchecked()));
```

`has_inaccessible_nonstatic_data_members`、`has_inaccessible_bases`、`has_inaccessible_subobjects`（¶6–¶10）：用 `unchecked()` 枚举全部成员/基类，再看是否有任一不可访问——这正是"能否对这个类做逐成员的序列化/比较"的前置检查。对闭包类型调用前者会抛异常（闭包的成员由实现决定）。

## 五、成员枚举（[meta.reflection.member.queries]）

`members_of(r, ctx)` 的规则是本章最精细的部分之一，因为"类有哪些成员"在 C++ 里比想象中复杂（隐式声明的特殊成员、匿名联合体的变体成员、友元、闭包类型、模板特化……）。

¶1：声明 `D` **members-of 先于**点 `P`，若 `D` 先于 `P`，或先于"`P` 处于其完整类语境的最外层类的类说明符结束之后"的那个点。

¶2：类或命名空间 `Q` 的成员 `M` 的声明 `D` 是 **`Q`-members-of-合格的**，当且仅当：`D` 的宿主作用域是 `Q` 的作用域；`D` 不是友元声明；`M` 不是闭包类型；`M` 不是模板特化；（`Q` 是非闭包类时）`M` 是 `Q` 的直接成员且不是嵌套匿名联合体的变体成员；（`Q` 是闭包类型时）`M` 是函数调用运算符或其模板——闭包的其他成员是否合格由实现定义。

¶3：`M` 从 `P` **`Q`-members-of-可表示**，当且仅当有合格声明 members-of 先于 `P`，且 `M` 是：类或枚举类型、类型别名、各类模板或概念、类型中不含未推导占位符的变量、（类型不含未推导占位符、约束满足、若是预期析构函数则为被选中的那个）函数、非静态数据成员、命名空间、命名空间别名。注 1：无作用域枚举的枚举项、模板的偏特化、闭包类型都不是可表示的直接成员。

¶4 *Returns*：`dealias(r)` 所代表的 `Q` 中、从求值上下文某点可表示且 `is_accessible(^^M, ctx)` 的所有成员；类还要加上可访问的无名位域。**按声明顺序**排列；注 2：基类不是成员；隐式声明的特殊成员排在所有用户声明的成员之后。

¶5 *Throws*：`dealias(r)` 不是（从求值上下文某点完整的）类类型或命名空间。

标准例子展示了模块与访问语境的影响：

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

其余便捷函数都基于 `members_of`：

| 函数 | 返回 |
|---|---|
| `bases_of(type, ctx)` | 可访问的直接基类关系，按 *base-specifier-list* 顺序 |
| `static_data_members_of(type, ctx)` | `members_of` 中 `is_variable` 的元素 |
| `nonstatic_data_members_of(type, ctx)` | `members_of` 中 `is_nonstatic_data_member` 的元素 |
| `subobjects_of(type, ctx)` | `bases_of` 后接 `nonstatic_data_members_of` |
| `enumerators_of(type_enum)` | 枚举的全部枚举项，按声明顺序；要求 `is_enumerable_type`；**不带访问语境**（枚举项没有访问控制）|

## 六、布局查询（[meta.reflection.layout]）

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

- **`offset_of(r)`**（¶2–¶4）：从 `parent_of(r)` 类型的**完整对象**起点到 `r` 对应子对象的偏移 `V`（以位计），返回 `{V / CHAR_BIT, V % CHAR_BIT}`。适用于非静态数据成员、无名位域和直接基类关系——但**虚基类关系在抽象类中**除外。与 `offsetof` 宏相比：它支持位域（给出位偏移）、支持基类子对象、不受"标准布局"限制（偏移相对于完整对象定义，因此对非标准布局类也有意义）。
- **`size_of(r)`**（¶5–¶6）：类型 → `sizeof(T)`；非静态数据成员或数据成员描述 → 其类型的 `sizeof`；**引用类型** → 返回 `size_of(add_pointer(^^T))`。注 1 特意指出：`sizeof(char&) == size_of(^^char&)` 可能为假（`sizeof` 对引用给出被引用类型的大小）；空基类的直接基类关系 `size_of(b) > 0`（返回的是基类类型的 `sizeof`，不是它在派生类中实际占用的大小）。位域、不完整类型等抛异常。
- **`alignment_of(r)`**（¶7–¶8）：类型的对齐（引用同样按指针算）；变量/对象的对齐（考虑 `alignas`）；非静态数据成员在完整对象中**实际的**对齐；数据成员描述的 `A`（若有）。
- **`bit_size_of(r)`**（¶9–¶10）：位域返回宽度，否则 `CHAR_BIT * size_of(r)`。

## 七、注解反射（[meta.reflection.annotation]）

注解（annotation，[[g:annotation]]）是 C++26 新增的 `[[=expr]]` 语法（[[dcl.attr.annotation]]，[[P3394R4]]）：把一个常量值挂到声明上，供反射读取，不影响程序的其他语义。

`annotations_of(item)`（¶1–¶4）返回作用于 `item` 的所有注解的反射：函数形参 → 该函数所有声明中该形参上的注解；函数 → 所有声明上的注解；直接基类关系 → 对应 *base-specifier* 上的；其他 → 实体每个声明上的。只考虑从求值上下文（或完整类语境结束点）可达的声明。**顺序**：同一翻译单元中，先出现的注解排在前面，且来自同一翻译单元的注解连续排列；跨翻译单元的相对顺序未指明。

```cpp
[[=1]] void f();
[[=2, =3]] void g();
void g [[=4]] ();

static_assert(annotations_of(^^f).size() == 1);
static_assert(annotations_of(^^g).size() == 3);                 // 两个声明上的注解都算
static_assert([: constant_of(annotations_of(^^g)[0]) :] == 2);
static_assert(extract<int>(annotations_of(^^g)[2]) == 4);

struct Option { bool value; };
struct C {
  [[=Option{true}]] int a;
  [[=Option{false}]] int b;
};
static_assert(extract<Option>(annotations_of(^^C::a)[0]).value);

template<class T> struct [[=42]] D { };
constexpr std::meta::info a1 = annotations_of(^^D<int>)[0];
constexpr std::meta::info a2 = annotations_of(^^D<char>)[0];
static_assert(a1 != a2);                                        // 不同特化上的注解是不同的注解
static_assert(constant_of(a1) == constant_of(a2));              // 但值相同

[[=1]] int x, y;
static_assert(annotations_of(^^x)[0] == annotations_of(^^y)[0]);   // 同一个声明中的同一个注解
```

`annotations_of_with_type(item, type)`（¶5–¶6）：筛选出 `remove_const(type_of(e)) == remove_const(type)` 的注解——"给我这个声明上所有 `Option` 类型的注解"，这是注解最常见的用法（序列化框架的字段选项、命令行解析的参数描述等）。

## 陷阱

!!! pitfall "查询结果依赖求值位置"
    `has_identifier`、`members_of`、`is_complete_type`、`annotations_of` 的结果都取决于在**求值上下文**中哪些声明可达。同一个 `info` 在文件不同位置查询可能给出不同答案（见 `has_identifier` 与 `is_enumerable_type` 的例子）。把反射查询的结果缓存到 `constexpr` 变量里，得到的是**那个点**的快照。

!!! pitfall "`members_of` 默认看不到私有成员"
    `members_of(^^S, access_context::current())` 在类外调用时只返回可访问的成员。写通用序列化时若需要全部成员，必须显式使用 `unchecked()`，并最好先用 `has_inaccessible_nonstatic_data_members` 决定策略。

!!! pitfall "`size_of(^^T&)` 不是 `sizeof(T&)`"
    对引用类型，`size_of` 返回**指针**的大小（引用作为成员时通常占用的空间），而 `sizeof(T&)` 返回 `sizeof(T)`。

## 小结

| 族 | 关键函数 | 要点 |
|---|---|---|
| 名字 | `has_identifier`、`identifier_of`、`display_string_of` | 形参名须在所有可达声明中一致；`display_string_of` 由实现定义 |
| 查询 | `type_of`、`object_of`、`constant_of`、`is_*` | 谓词从不抛；`is_explicit`/`is_noexcept` 对模板为假 |
| 导航 | `parent_of`、`dealias`、`template_arguments_of`、`parameters_of` | 类型实参总是去别名 |
| 作用域 | `current_function/class/namespace` | 基于 *eval-point*；默认实参取调用处；不可寻址 |
| 访问 | `access_context`、`is_accessible` | `current`/`unprivileged`/`unchecked`/`via` |
| 成员 | `members_of`、`bases_of`、`enumerators_of` | 按声明顺序；隐式特殊成员在后；须可枚举 |
| 布局 | `offset_of`、`size_of`、`alignment_of`、`bit_size_of` | 位级偏移；引用按指针计 |
| 注解 | `annotations_of(_with_type)` | 跨声明收集；同 TU 内按出现顺序 |
