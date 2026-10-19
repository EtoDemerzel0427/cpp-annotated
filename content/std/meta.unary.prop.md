---
title: 类型性质
summary: 表 54 的类型性质谓词：is_constructible 用一个假想的变量定义来定义，平凡和不抛异常变体看这个定义实际调用了什么；以及类性质、is_assignable、is_destructible、has_unique_object_representations 和 C++23 的 reference_constructs_from_temporary。
status: done
covers: meta.unary.prop
papers: P0258R2, P2255R2, P3247R2
related: type.traits, meta.unary, meta.rel, basic.types, class.prop, dcl.init, dcl.init.aggr, class.temporary, expr.unary.noexcept, temp.deduct, declval, special
tags: 标准库, type_traits, is_constructible, 平凡, noexcept, UB
updated: 2026-10-19
---

!!! tldr
    - `is_constructible_v<T, Args...>` 为真，当且仅当 `T t(declval<Args>()...);` 这个直接初始化的变量定义良构；所以 `explicit` 构造函数也算，私有构造函数不算。
    - 只检查初始化的直接语境：无约束的构造函数模板会让 trait 回答真，即使真正构造时函数体会编译失败。
    - `is_trivially_*` 和 `is_nothrow_*` 看的是那个变量定义实际调用的操作；Clang 把 `t` 的析构也算在内。
    - `is_trivially_copyable` 是核心语言的类性质，和 `is_trivially_copy_constructible` 不是一回事。
    - 表中大多数谓词要求实参是完整类型，违反是未定义行为。

表 54 有三列：模板、条件和前置条件。条件决定 `value`；前置条件被违反时行为未定义（[[structure.specifications#3.4]]，不完整类型的规则见 [[type.traits]]）。

## 一、`is_constructible`：一个假想的变量定义（¶9）

```cpp title="immediate-context.cpp" run ok
#include <type_traits>

struct Ex { explicit Ex(int); };
struct Priv { private: Priv(int); };
struct Lazy {
    template<class T> Lazy(T t) { t.no_such_member(); }
};

static_assert( std::is_constructible_v<Ex, int>);     // explicit 也算
static_assert(!std::is_convertible_v<int, Ex>);       // 隐式转换不行
static_assert(!std::is_constructible_v<Priv, int>);   // 访问检查失败 → false
static_assert( std::is_constructible_v<Lazy, int>);   // 只看声明 → true
// Lazy x(1);   // 真正构造时实例化函数体 → 硬错误

int main() {}
```

`is_default_constructible`、`is_copy_constructible`、所有 `is_trivially_*constructible` 和 `is_nothrow_*constructible` 都建立在 `is_constructible` 上。

!!! std
    The predicate condition for a template specialization `is_constructible<T, Args...>` shall be satisfied if and only if the following variable definition would be well-formed for some invented variable `t`: `T t(declval<Args>()...);`

¶9 `is_constructible<T, Args...>` 的条件成立，当且仅当对某个虚构的变量 `t`，变量定义 `T t(declval<Args>()...);` 是良构的。表 54 先排除了两种情况：`T` 是函数类型或 *cv* `void` 时结果为 `false`。

下面的结论都来自这是一个直接初始化的变量定义：

| 规则 | 例子 | 结果 |
|---|---|---|
| 直接初始化，`explicit` 构造函数可用 | `is_constructible_v<Ex, int>` | `true` |
| C++20 起圆括号可以初始化聚合 | `is_constructible_v<Agg, int, int>`、`is_constructible_v<int[2], int, int>` | `true` |
| 非 const 左值引用不能绑定到转换出的临时量（[[dcl.init.ref]]） | `is_constructible_v<int&, long&>` | `false` |
| const 左值引用可以 | `is_constructible_v<const int&, long>` | `true` |
| 右值引用不能绑定到左值 | `is_constructible_v<int&&, int&>` | `false` |
| 没有实参就是值初始化 | `is_constructible_v<int>`、`is_default_constructible_v<int[3]>` | `true` |
| 未知边界数组没有初始化器就不能定义变量 | `is_default_constructible_v<int[]>` | `false` |

注 7 规定这些记号从不被解释为函数声明。所以没有实参时的 `T t();` 在这里是值初始化，而不是真实代码里那种被解析成函数声明的情况。

¶9 还规定了两件事，`is_assignable`、`is_convertible`、`invoke_result` 等定义里也反复出现：

1. 访问检查如同在与 `T` 和 `Args` 都无关的语境中进行。所以私有构造函数让结果为 `false`，即使在 `T` 的成员函数或友元里询问也一样。trait 的答案不能取决于在哪里问，否则同一个特化在不同地方会有不同的值。
2. 只考虑变量初始化的**直接语境**（immediate context，与 [[temp.deduct.general]] 中的概念相同）。初始化可能引发类模板和函数模板的实例化、隐式定义函数的生成等副作用。注 8 说明，这些副作用不在直接语境中，其中的错误让程序非良构，而不是让 trait 返回 `false`。

开头的 `Lazy` 就是这种情况：构造函数模板没有约束，声明层面接受任何 `T`，trait 回答真；真正构造时函数体实例化失败。C++20 的概念把要求写进约束，约束在直接语境中检查，trait 就能给出准确的答案。

### 三个便捷 trait

| 谓词 | 定义 |
|---|---|
| `is_default_constructible<T>` | `is_constructible_v<T>` |
| `is_copy_constructible<T>` | `T` 可引用时同 `is_constructible_v<T, const T&>`，否则 `false` |
| `is_move_constructible<T>` | `T` 可引用时同 `is_constructible_v<T, T&&>`，否则 `false` |

**可引用类型**（[[g:referenceable-type]]）是能够形成引用的类型，排除了 `void` 和带 cv 或引用限定的函数类型。对 `T = int&`，`const T&` 按引用折叠就是 `int&`，所以 `is_copy_constructible_v<int&>` 为真。

!!! pitfall "可移动构造不等于有移动构造函数"
    `is_move_constructible_v<T>` 问的是 `T t(declval<T&&>())` 是否良构。只有复制构造函数 `T(const T&)`、没有声明移动构造函数的类，右值照样能绑定到 `const T&`，结果为真。反过来，移动构造函数被显式弃置时，重载决议选中弃置的函数，结果为假。

## 二、平凡地：`is_trivially_*`

!!! std
    `is_constructible_v<T, Args...>` is `true` and the variable definition for `is_constructible`, as defined below, is known to call no operation that is not trivial.

`is_trivially_constructible` 要求 `is_constructible_v` 为真，并且那个变量定义已知不调用任何非平凡操作。关键在于那个变量定义实际调用了什么，而不是类的某个特殊成员函数是否平凡：

```cpp title="trivially.cpp" run ok
#include <type_traits>

struct DMI { int x = 0; };                 // 默认成员初始化器
static_assert( std::is_trivially_copyable_v<DMI>);
static_assert(!std::is_trivially_default_constructible_v<DMI>);

struct Tmpl {
    Tmpl() = default;
    Tmpl(const Tmpl&) = default;           // 平凡的复制构造函数
    template<class T> Tmpl(T&);            // 对非 const 左值更匹配
};
static_assert( std::is_trivially_copy_constructible_v<Tmpl>);
static_assert(!std::is_trivially_constructible_v<Tmpl, Tmpl&>);

struct NonTrivDtor { ~NonTrivDtor(); };
static_assert(!std::is_trivially_default_constructible_v<NonTrivDtor>);

struct MoveOnly {
    MoveOnly(MoveOnly&&) = default;
    MoveOnly& operator=(MoveOnly&&) = default;
};
static_assert( std::is_trivially_copyable_v<MoveOnly>);
static_assert(!std::is_trivially_copy_constructible_v<MoveOnly>);

static_assert( std::is_trivially_constructible_v<int, long>);

int main() {}
```

逐条看：

1. 默认成员初始化器让默认构造函数非平凡，所以 `DMI` 平凡可复制，但不能平凡地默认构造。
2. 重载决议选中哪个函数就看哪个函数。`Tmpl` 的复制构造函数是平凡的，但实参是 `Tmpl&` 时选中的是构造函数模板，不平凡。
3. 变量定义 `T t(...)` 意味着 `t` 最终要被销毁。Clang 把析构也算进去，所以析构函数非平凡的类，`is_trivially_default_constructible` 为假，即使它的默认构造函数本身是平凡的。
4. 对标量类型，内建转换是平凡的，`is_trivially_constructible_v<int, long>` 为真。

`MoveOnly` 说明 `is_trivially_copyable` 不等于可以平凡地复制构造。前者是核心语言的类性质（[[class.prop]]）：至少有一个合格的复制或移动操作，所有合格的都平凡，析构函数平凡且未弃置。后者问的是一个具体的表达式。泛型库判断能否用 `memcpy` 复制对象表示，用 `is_trivially_copyable`；判断能否用 `memcpy` 实现复制构造，还需要类型可复制构造。

`is_trivially_assignable<T, U>` 同理，要求那个赋值表达式已知不调用非平凡操作。`is_trivially_destructible<T>` 要求 `is_destructible_v<T>` 为真，并且 `remove_all_extents_t<T>` 是非类类型或析构函数平凡的类类型，所以 `is_trivially_destructible_v<int&>` 为真。

## 三、不抛异常地：`is_nothrow_*`

`is_nothrow_constructible<T, Args...>` 要求 `is_constructible_v` 为真，并且那个变量定义已知不抛出任何异常（[[expr.unary.noexcept]]）。其他 `is_nothrow_*` 同理。

`std::vector` 扩容时据此在移动和复制之间选择（`std::move_if_noexcept`）：只有元素的移动构造不抛异常，或者元素不可复制时，才移动元素，以保证强异常安全。

!!! lawyer "析构函数算不算"
    和平凡性一样，标准措辞没有明说那个变量定义是否包括 `t` 的析构，这是一个长期悬而未决的库问题。Clang 的 `__is_nothrow_constructible` 选择计入析构函数：

    ```cpp title="nothrow-dtor.cpp" run ok
    #include <type_traits>

    struct ND { ~ND() noexcept(false); };

    static_assert( std::is_default_constructible_v<ND>);
    static_assert(!std::is_nothrow_default_constructible_v<ND>);   // Clang 23：析构可能抛 → false

    int main() {}
    ```

    析构函数默认是 `noexcept` 的（[[except.spec]]），只有显式写了 `noexcept(false)` 的类型才会遇到这个差别。

`is_nothrow_destructible<T>` 要求 `is_destructible_v<T>` 为真且析构函数已知不抛异常。`is_nothrow_swappable_with` 要求两个 `swap` 表达式都不抛。

## 四、赋值、交换和析构

**`is_assignable<T, U>`**：表达式 `declval<T>() = declval<U>()` 作为不求值操作数是良构的。访问检查和直接语境的规则与 `is_constructible` 相同（注 3）。注意左边是 `declval<T>()`：

```cpp title="is-assignable.cpp" run ok
#include <type_traits>

struct S { int a; };
struct RQ { RQ& operator=(const RQ&) & = default; };   // 只能对左值赋值

static_assert(!std::is_assignable_v<int, int>);    // int&& 不能被赋值
static_assert( std::is_assignable_v<int&, int>);
static_assert( std::is_assignable_v<S, S>);        // 可以对类的右值赋值
static_assert(!std::is_assignable_v<RQ, const RQ&>);
static_assert( std::is_copy_assignable_v<RQ>);

int main() {}
```

`declval<int>()` 是 `int&&` 类型的亡值，内建赋值要求左操作数是可修改的左值，所以 `is_assignable_v<int, int>` 为假。因此 `is_copy_assignable<T>` 定义为 `is_assignable_v<T&, const T&>`，`is_move_assignable<T>` 定义为 `is_assignable_v<T&, T&&>`（`T` 须可引用）。类的右值可以调用成员 `operator=`，除非赋值运算符带 `&` 限定。

**`is_swappable_with<T, U>`**：`swap(declval<T>(), declval<U>())` 和 `swap(declval<U>(), declval<T>())` 都良构，重载决议在可交换值的语境中进行（[[swappable.requirements]]），也就是同时考虑 `std::swap` 和 ADL 找到的 `swap`。`is_swappable<T>` 等于 `is_swappable_with_v<T&, T&>`。`std::swap` 要求实参可移动构造、可移动赋值，所以移动构造被弃置的类型 `is_swappable_v` 为假。

**`is_destructible<T>`**：要么 `T` 是引用类型，要么 `T` 是完整的对象类型并且 `declval<U&>().~U()` 良构，其中 `U` 是 `remove_all_extents_t<T>`：

| `T` | `is_destructible_v<T>` | 原因 |
|---|---|---|
| `int&` | `true` | 引用类型直接为真 |
| `int[3]` | `true` | 看元素 |
| `int[]` | `false` | 不是完整的对象类型 |
| `void`、`void()` | `false` | 不是对象类型 |
| 析构函数弃置或私有的类 | `false` | 伪析构表达式非良构 |

## 五、类性质与 cv

| 谓词 | 条件 | 前置条件 |
|---|---|---|
| `is_const`、`is_volatile` | 顶层有 const、volatile 限定（[[basic.type.qualifier]]） | |
| `is_empty` | 非联合类；除零大小子对象外没有非静态数据成员；没有虚函数、虚基类；基类都是空类 | 非联合类须完整 |
| `is_polymorphic` | 多态类（[[class.virtual]]） | 同上 |
| `is_abstract` | 抽象类（[[class.abstract]]） | 同上 |
| `is_final` | 标了 `final` 的类，包括联合体 | 类须完整 |
| `has_virtual_destructor` | 有虚析构函数（[[class.dtor]]） | 非联合类须完整 |
| `is_aggregate` | 聚合类型（[[dcl.init.aggr]]） | 数组、完整类型或 *cv* `void` |
| `is_structural` | 结构化类型（[[g:structural-type]]） | `remove_all_extents_t<T>` 完整或 *cv* `void` |
| `is_signed` | 算术类型时同 `T(-1) < T(0)`，否则 `false` | |
| `is_unsigned` | 算术类型时同 `T(0) < T(-1)`，否则 `false` | |
| `is_bounded_array`、`is_unbounded_array` | 已知、未知边界的数组 | |
| `is_scoped_enum` | 有作用域枚举（[[dcl.enum]]） | |

### `is_const` 只看顶层

¶6 的标准例子：

```cpp
is_const_v<const volatile int>   // true
is_const_v<const int*>           // false：指针本身不是 const
is_const_v<const int&>           // false：引用不能有 cv 限定
is_const_v<int[3]>               // false
is_const_v<const int[3]>         // true：数组的 cv 就是元素的 cv
```

数组的 cv 限定就是元素的 cv 限定（[[basic.type.qualifier]]）。`is_const_v<void() const>` 也为假，函数类型上的 `const` 是成员函数的限定符，不是类型的 cv 限定。¶7 的例子对 `remove_const_t` 给出了同样的结论。

### `is_empty` 与大小无关

`is_empty` 是按结构定义的，它刻画的是作为基类或 `[[no_unique_address]]` 成员时可以不占空间，与 `sizeof` 的值没有直接关系：

```cpp title="is-empty.cpp" run ok
#include <type_traits>

struct Empty {};
struct WithNUA { [[no_unique_address]] Empty e; };   // 唯一的成员是零大小子对象
struct D : Empty {};
struct Poly { virtual ~Poly(); };

static_assert( std::is_empty_v<WithNUA>);   // sizeof(WithNUA) == 1
static_assert( std::is_empty_v<D>);
static_assert(!std::is_empty_v<Poly>);      // 有虚函数
static_assert(!std::is_empty_v<int>);       // 不是类

int main() {}
```

### `is_final`、`is_aggregate`、`is_structural`

¶8 的例子表明 `union U2 final {};` 合法，`is_final_v<U2>` 为真。`is_final` 的主要用途是实现空基类优化：`final` 类不能做基类，只能改用成员存储（或 `[[no_unique_address]]`）。

数组总是聚合，所以 `is_aggregate` 的前置条件特意允许数组类型，`is_aggregate_v<int[]>` 为真。

结构化类型是可以做常量模板形参类型的类型（[[temp.param]]）。C++26 反射中，`reflect_constant` 要求实参类型是结构化类型（[[meta.reflection.extract]]）。本机 libc++ 还没有提供 `std::is_structural`。

### `is_signed` 用表达式定义

!!! std
    If `is_arithmetic_v<T>` is `true`, the same result as `T(-1) < T(0)`; otherwise, `false`.

这个定义有几个不那么直观的结果：

- `is_unsigned_v<bool>` 为真：`bool(-1)` 是 `true`，`false < true`。
- `is_signed_v<float>` 为真。
- `is_signed_v<char>` 由实现决定：Apple arm64 上 `char` 有符号，为真；Linux AArch64 上 `char` 无符号，为假。
- 枚举不是算术类型，所以 `is_signed_v<E>` 对任何枚举都为假。要问枚举的符号，写 `is_signed_v<underlying_type_t<E>>`。

```cpp title="is-signed.cpp" run ok
#include <type_traits>

enum E : int { e = -1 };

static_assert( std::is_unsigned_v<bool>);
static_assert( std::is_signed_v<float>);
static_assert(!std::is_signed_v<E> && !std::is_unsigned_v<E>);
static_assert( std::is_signed_v<std::underlying_type_t<E>>);

int main() {}
```

## 六、核心性质

| 谓词 | 条件 | 前置条件 |
|---|---|---|
| `is_trivially_copyable` | 平凡可复制类型（[[basic.types.general#7]]） | `remove_all_extents_t<T>` 完整或 *cv* `void` |
| `is_standard_layout` | 标准布局类型 | 同上 |
| `is_implicit_lifetime` {{c++23}} | 隐式生存期类型 | 数组、完整类型或 *cv* `void` |

这三个 trait 的含义完全由核心语言决定，见 [[basic.types]] 和 [[class.prop]]。从 trait 的角度补充几点：

- 它们都是对象类型的性质。`is_trivially_copyable_v<int&>` 和 `is_standard_layout_v<int&>` 都为假。cv 限定的标量类型是平凡可复制的，`is_trivially_copyable_v<const int>` 为真，尽管不能给它赋值。
- 数组类型无条件地是隐式生存期类型，因为创建数组对象本身不需要运行任何代码。所以 `is_implicit_lifetime_v<std::string[2]>` 为真，而 `is_implicit_lifetime_v<std::string>` 为假。
- `is_trivial`（平凡可复制且可平凡默认构造）在 C++26 被弃用，移到了附录 D（[[depr.meta.types]]，[[P3247R2]]）。应改为分别询问 `is_trivially_copyable` 和 `is_trivially_default_constructible`。

```cpp title="core-properties.cpp" run ok
#include <string>
#include <type_traits>

struct Agg { int a; int b; };

static_assert(!std::is_trivially_copyable_v<int&>);
static_assert( std::is_trivially_copyable_v<const int>);
static_assert( std::is_implicit_lifetime_v<Agg>);
static_assert(!std::is_implicit_lifetime_v<std::string>);
static_assert( std::is_implicit_lifetime_v<std::string[2]>);   // 数组总是隐式生存期类型
static_assert( std::is_implicit_lifetime_v<int[]>);

int main() {}
```

## 七、`has_unique_object_representations`（¶10）

¶10 条件成立，当且仅当 `T` 平凡可复制，并且任意两个值相同的 `T` 对象具有相同的对象表示（[[g:object-representation]]）。

这是能否按字节哈希或比较的判据：值相同就意味着字节相同，于是可以直接对对象表示做 `memcmp` 或哈希。它在 C++17 加入（[[P0258R2]]），动机就是高效地实现 `std::hash`。

¶10 还定义了值相同：数组和非联合类要求各个直接子对象的值相同；联合体要求活跃成员相同且其值相同。对标量类型，哪些满足条件由实现定义。注 9 提示，有填充位的类型不满足，否则整型满足。

| 类型 | 本机 Clang 23（arm64 macOS） | 原因 |
|---|---|---|
| `int`、`int*`、成员指针 | `true` | 没有填充，值与表示一一对应 |
| `bool` | `true` | 只有 0 和 1 两种合法表示 |
| `float`、`double`、`long double` | `false` | `+0.0 == -0.0`，但表示不同 |
| `struct { char c; int i; }` | `false` | 有填充字节 |
| `struct { int a, b; }` | `true` | 没有填充 |
| 含位域 `int x : 3` 的类 | `false` | 位域以外的位是填充 |
| 数组 | 同元素类型 | 表 54 的明确规定 |

条件只要求值相同推出表示相同。NaN 不等于自身并不是浮点类型被排除的原因，排除它们的是 `+0.0` 和 `-0.0` 这对值相等、表示不同的例子。

## 八、引用绑定到临时对象 {{c++23}}

¶5 先定义了说明用的表达式 *VAL*`<T>`：

- ¶5.1 `T` 是引用或函数类型时，*VAL*`<T>` 的类型和值类别与 `declval<T>()` 相同；
- ¶5.2 否则，*VAL*`<T>` 是一个最初类型为 `T` 的纯右值（`T` 有 cv 限定时按 [[expr.type]] 调整）。

| 谓词 | 条件 |
|---|---|
| `reference_constructs_from_temporary<T, U>` | `T` 是引用类型，`T t(VAL<U>);` 良构，并把 `t` 绑定到一个生存期被延长的临时对象 |
| `reference_converts_from_temporary<T, U>` | 同上，但初始化是复制初始化 `T t = VAL<U>;` |

两者的差别就是直接初始化和复制初始化：`explicit` 转换函数只在前者中可用。

```cpp title="ref-from-temp.cpp" run ok
#include <string>
#include <type_traits>

struct X { explicit operator int() const; };
using std::reference_constructs_from_temporary_v;
using std::reference_converts_from_temporary_v;

static_assert( reference_constructs_from_temporary_v<const int&, long>);  // long → int 临时量
static_assert( reference_constructs_from_temporary_v<const int&, int>);   // 纯右值 → 实质化
static_assert(!reference_constructs_from_temporary_v<const int&, int&>);  // 直接绑定左值
static_assert( reference_constructs_from_temporary_v<int&&, int>);
static_assert( reference_constructs_from_temporary_v<const std::string&, const char*>);
static_assert(!reference_constructs_from_temporary_v<int, int>);          // T 不是引用

static_assert( reference_constructs_from_temporary_v<const int&, X>);     // 可用 explicit
static_assert(!reference_converts_from_temporary_v<const int&, X>);       // 不可用 explicit

int main() {}
```

这里不能用 `declval<U>()`。对非引用的 `U`，`declval<U>()` 返回 `U&&`，是亡值；用它初始化 `const U&` 会直接绑定，不产生临时对象。而 `reference_constructs_from_temporary<const int&, int>` 想问的是用一个 `int` 纯右值初始化时会不会绑定到临时对象，答案是会。*VAL* 给出了真正的纯右值。

这对 trait 来自 [[P2255R2]]，用来在编译期拦住一类悬垂引用：

- `std::pair<const std::string&, int> p("x", 1);` 中，`first` 会绑定到一个在构造函数结束时就销毁的临时 `std::string`。C++23 起，如果 `reference_constructs_from_temporary_v<first_type, U1&&>` 为真，相应的构造函数定义为弃置（[[pairs.pair]]），`tuple` 也一样。
- [[func.require#2]] 规定，如果 `reference_converts_from_temporary_v<R, decltype(INVOKE(...))>` 为真，*INVOKE*`<R>` 非良构。按标准，`std::function<const int&()> f = []{ return 42; };` 这类必然悬垂的写法不能编译，`is_invocable_r_v<const long&, int(*)()>` 也为假。

!!! impl "libc++ 的落实程度"
    本机 Clang 23 + libc++ 中，`pair` 和 `tuple` 遇到上述情况时用 `static_assert` 报错（reference member 'first' binds to a temporary object…），而不是把构造函数定义为弃置。所以 `is_constructible_v<std::pair<const std::string&, int>, const char*, int>` 仍然为真，与标准不符。`std::is_invocable_r_v<const long&, int(*)()>` 在 libc++ 中也为真，*INVOKE*`<R>` 的这条规则在 trait 层面还没有落实。

<details class="fine" markdown="1"><summary>其余条文</summary>

¶1 表 54 中的模板提供对类型的一些较重要性质的访问。

¶2 库是否为这些模板定义全特化或偏特化是未指明的。所以不能假设 `is_trivially_copyable<X>` 一定是主模板的实例。

¶3 模板实参是类模板特化时，只有当 trait 的语义要求实参是完整类型时，才可以隐式实例化它。所以 `is_class_v<Box<T>>`、`is_const_v<Box<T>>` 这类只看外形的查询不会实例化 `Box<T>`，而 `is_trivially_copyable_v<Box<T>>` 必然实例化它。

¶4 为了定义本节的模板，`declval<T>()` 调用被视为一次平凡的函数调用，并且不是对 `declval` 的 odr-use。否则 `is_trivially_constructible<T, T&&>` 里的 `declval<T&&>()` 本身就是一次非平凡操作，所有 `is_trivially_*` 都会为假；`declval` 只有声明、不能在求值语境中使用（[[declval]]）的限制也一并豁免。

</details>

## 实现视角

!!! impl "全部是 Clang 内建"
    libc++ 中本节的 trait 几乎都直接转发给 Clang 内建：`__is_constructible`、`__is_trivially_constructible`、`__is_nothrow_constructible`、`__is_assignable`、`__is_trivially_copyable`、`__builtin_is_implicit_lifetime`、`__has_unique_object_representations`、`__reference_constructs_from_temporary` 等。例如：

    ```cpp
    template <class _Tp>
    struct _LIBCPP_NO_SPECIALIZATIONS is_copy_constructible
        : integral_constant<bool, __is_constructible(_Tp, __add_lvalue_reference_t<const _Tp>)> {};
    ```

    这里用 `__add_lvalue_reference_t<const _Tp>` 而不直接写 `const _Tp&`，是为了处理不可引用的类型：对 `void` 它得到 `const void`，`__is_constructible(void, const void)` 为假，与标准的否则为 `false` 一致。

    编译器内部，`__is_constructible` 确实是在语义分析中构造那个假想的变量定义，并在一个只记录失败、不报错的环境里检查它。

## 常见错误

!!! pitfall "无约束的转换构造函数让 trait 给出错误答案"
    `template<class T> Wrapper(T&&)` 这类无约束的完美转发构造函数，会让 `is_constructible_v<Wrapper, X>` 和 `is_convertible_v<X, Wrapper>` 对任何 `X` 都为真，进而影响 `std::variant`、`std::optional` 等依赖这些 trait 的重载决议。应当用 `requires` 或 `enable_if` 约束它。

!!! pitfall "`is_trivially_copyable` 为真不代表可以复制"
    `MoveOnly` 平凡可复制，却根本不能复制构造。依据 `is_trivially_copyable` 走 `memcpy` 的库代码，做的是按字节复制对象表示。这对平凡可复制类型在语言层面总是合法的（[[basic.types.general#2]]），即使类型的作者删除了复制构造函数，这有时违背作者的意图。

!!! ub "违反前置条件"
    表 54 几乎每一行都有必须是完整类型、*cv* `void` 或未知边界数组之类的前置条件。对不完整的类问 `is_constructible`、`is_trivially_copyable`、`is_nothrow_move_constructible` 等是 UB。Clang 大多会报错，但不要依赖这一点。

## 思考题

!!! question "思考题 1"
    `struct A { A(int) noexcept; ~A(); };` 中，`is_nothrow_constructible_v<A, int>` 和 `is_trivially_constructible_v<A, int>` 各是什么？

<details markdown="1">
<summary>答案</summary>

`~A()` 没有显式的异常说明，按 [[except.spec]] 隐式为 `noexcept`，所以 `is_nothrow_constructible_v<A, int>` 为真：构造函数不抛，析构也不抛。

`is_trivially_constructible_v<A, int>` 为假：被调用的 `A(int)` 是用户提供的构造函数，不是平凡操作，析构函数也是用户提供的、非平凡的。
</details>

!!! question "思考题 2"
    `is_unsigned_v<bool>` 为什么是 `true`？`is_signed_v<char8_t>` 呢？

<details markdown="1">
<summary>答案</summary>

`bool` 是算术类型，按表 54 计算 `bool(0) < bool(-1)`：`bool(-1)` 是 `true`，`false < true` 为真。

`char8_t` 的底层类型是 `unsigned char`（[[basic.fundamental]]），`char8_t(-1)` 是 255，`char8_t(-1) < char8_t(0)` 为假。所以 `is_signed_v<char8_t>` 为假，`is_unsigned_v<char8_t>` 为真。
</details>

## 小结

| 家族 | 定义依据 | 要点 |
|---|---|---|
| `is_constructible` 系 | `T t(declval<Args>()...);` 是否良构 | 直接初始化；在无关语境中做访问检查；只看直接语境；函数和 `void` 为假 |
| `is_assignable` 系 | `declval<T>() = declval<U>()` | 左边通常要写成 `T&` |
| `is_trivially_*` | 上述表达式已知不调用非平凡操作 | 看实际选中的函数；Clang 计入析构 |
| `is_nothrow_*` | 上述表达式已知不抛异常 | `move_if_noexcept` 的依据；Clang 计入析构 |
| 核心性质 | [[basic.types]]、[[class.prop]] | 数组总是隐式生存期类型 |
| `has_unique_object_representations` | 值相同则表示相同 | 浮点和有填充的类为假 |
| `reference_*_from_temporary` | 用纯右值 *VAL*`<U>` 初始化引用时是否绑定临时对象 | 用于 `pair`、`tuple`、*INVOKE*`<R>` 防止悬垂 |
