---
title: 枚举
summary: 有作用域与无作用域枚举、底层类型（固定 vs 不固定）、枚举的值集合与"最小位域"规则、超出范围转换的 UB、不透明枚举声明、C++17 的花括号初始化、C++20 的 using enum
status: done
covers: dcl.enum, enum.udecl
papers: P0138R2, P1099R5, P1120R0, P2864R2, P2115R0
related: basic.compound, basic.scope.enum, conv.prom, expr.static.cast, expr.arith.conv, dcl.init.list, namespace.udecl, dcl.typedef, basic.link
tags: 枚举, 类型, 底层类型, using enum
updated: 2026-10-17
---

枚举（enumeration）是 C 继承来的最古老的用户定义类型之一，也是 C++ 中被修补次数最多的特性之一。C 的 `enum` 有三个毛病：枚举量**泄漏**到外层作用域、**隐式转换**为整数、**底层类型**和大小由实现决定（于是无法前置声明）。C++11 用两条正交的机制解决：

- [[g:scoped-enumeration|有作用域枚举]]（scoped enumeration，`enum class`/`enum struct`）：枚举量留在枚举自己的作用域里，不隐式转换为整数；
- [[g:fixed-underlying-type|固定底层类型]]（fixed underlying type，`enum E : T`）：底层类型由程序员指定，枚举从此可以**不透明声明**（前置声明）。

本页覆盖 [dcl.enum]（枚举声明）和 [enum.udecl]（`using enum` 声明）。读之前最好知道：枚举是**复合类型**（[[basic.compound]]），枚举量的作用域见 [[basic.scope.enum]]，整型提升见 [[conv.prom]]。

## 语法与总体（[dcl.enum] ¶1）

```text
enum-specifier:          enum-head { enumerator-list(opt) }   或带尾随逗号
enum-head:               enum-key attribute-specifier-seq(opt) enum-head-name(opt) enum-base(opt)
opaque-enum-declaration: enum-key attribute-specifier-seq(opt) enum-head-name enum-base(opt) ;
enum-key:                enum | enum class | enum struct
enum-base:               : type-specifier-seq
enumerator-definition:   enumerator | enumerator = constant-expression
```

¶1 的要点：

- 枚举是一个**不同的类型**（distinct type），带有具名常量；它的名字成为作用域内的 *enum-name*。
- *enum-head* 或不透明声明中的 *attribute-specifier-seq* 属于枚举本身，而且"以后每次提到这个枚举时都视为有这些属性"——例如 `enum [[deprecated]] E { };` 之后任何使用 `E` 都应引发弃用警告。
- **消歧规则**：在类的 *member-declaration* 中，`enum E` 后面的 `:` 一律被解析为 *enum-base*。这是为了消除"带底层类型的枚举声明"与"枚举类型的无名位域"之间的二义性：`enum E : int` 是哪一种？标准规定它总是前者。
- *enum-head-name* 中的标识符**不做名字查找**，它是被引入的。
- 不透明枚举声明如果带 *nested-name-specifier*（如 `enum class X::In;`），它必须是**显式特化**（用于类模板的成员枚举）。

```cpp title="enum-base-ambiguity.cpp" error
struct S {
    enum E : int {};
    enum E : int {};      // error: 枚举重定义——": int" 被解析为 enum-base，而不是位域
};
```

## 有作用域与无作用域（¶2）

¶2 定义两类枚举：

| | 无作用域枚举（unscoped） | 有作用域枚举（scoped） |
|---|---|---|
| *enum-key* | `enum` | `enum class` 或 `enum struct`（两者语义**完全相同**） |
| 名字可省略？ | 可以（匿名枚举） | 不可以 |
| 枚举量作用域 | 枚举作用域**和**外层作用域（¶12） | 只在枚举作用域 |
| 隐式转为整数 | 可以（整型提升，¶11） | 不可以 |
| 默认底层类型 | 不固定，由实现选择（¶7） | 固定为 `int`（¶5） |
| 不透明声明 | 必须写 *enum-base* | 可以省略（默认 `int`） |

¶2 的其他规则：

- *enum-base* 必须命名一个**整型**类型，cv 限定被忽略（`enum E : const int` 等同于 `: int`）；不能是 `bool` 以外的非整型——`bool` 本身是整型，所以 `enum B : bool { no, yes };` 合法。
- 同一个 *enumerator-list* 中不能重复同一个名字。
- 带 `=` 的枚举量取该常量表达式的值；不带 `=` 的：第一个为 0，其余为前一个加 1。

```cpp title="enum-values.cpp" ok
enum { a, b, c = 0 };          // a=0, b=1, c=0
enum { d, e, f = e + 2 };      // d=0, e=1, f=3
enum B : bool { no, yes };     // OK: bool 是整型
static_assert(a == c && f == 3 && yes == true);

int main() {}
```

注意 `c = 0` 与 `a` 值相同完全合法——枚举量的**名字**必须唯一，**值**不必。

## 重声明的一致性（¶3–¶4）

¶3：不透明枚举声明要么是当前作用域中某个枚举的**重声明**，要么声明一个新枚举。注 2 点明关键事实：**不透明声明之后，枚举具有固定底层类型并且是完整类型**——你可以 `sizeof` 它、定义它的对象、按值传递它，只是还不知道有哪些枚举量。

一致性要求：

- 有作用域枚举以后不能重声明为无作用域的，也不能换底层类型；
- 无作用域枚举以后不能重声明为有作用域的，而且每次重声明都必须带 *enum-base* 并指定**相同**的底层类型。

```cpp title="opaque-enum.cpp" error
enum class Color : unsigned char;            // 不透明声明：完整类型
static_assert(sizeof(Color) == 1);           // OK: 尚未看到枚举量也可以 sizeof
enum class Color : unsigned char { red, green };   // OK: 补全枚举量列表

enum class W;                                // OK: 有作用域枚举默认底层类型 int
enum U : int;                                // OK
enum V;                                      // error: 无作用域枚举的不透明声明必须带 enum-base
enum W2 : long;
enum class W2 : long;                        // error: 先前声明为无作用域枚举
enum class Color : int;                      // error: 底层类型不同
```

为什么无作用域枚举的不透明声明必须写 *enum-base*？因为它的默认底层类型"不固定"——要等看到全部枚举量才能决定（¶7）——而不透明声明的整个意义就是"在看到枚举量之前就让类型完整"，两者矛盾。

¶4：*enum-head-name* 带 *nested-name-specifier* 时（在类外定义成员枚举、或在命名空间外定义命名空间的枚举），这个声明不能位于类作用域，且必须对应于该类/命名空间中可提名的（nominable）声明；声明的目标作用域就是那个作用域。

```cpp title="enum-out-of-class.cpp" ok
struct X {
    enum class In;              // 在类中不透明声明
};
enum class X::In { a, b };      // OK: 在类外补全

namespace N { enum class E : int; }
enum class N::E : int { x };    // OK

int main() { return static_cast<int>(X::In::b) - 1; }
```

这是 pimpl 风格的一个小工具：头文件里的类只暴露 `enum class State;`，具体的状态列表放在实现文件里。

## 底层类型与枚举量的类型（¶5–¶7）

¶5：每个枚举都是与其他一切类型不同的类型，并且有一个[[g:underlying-type|底层类型]]（underlying type）。底层类型被称为**固定的**，如果：

- 用 *enum-base* 显式指定了；或者
- 是有作用域枚举（未指定时为 `int`）。

**枚举量的类型**在闭花括号前后不同——这是一个容易被忽略的细节：

- 闭花括号**之后**，每个枚举量的类型都是该枚举类型；
- 闭花括号**之前**（即在后面的枚举量初始化器里引用前面的枚举量时）：
    - 底层类型固定：枚举量的类型是底层类型；初始化器必须是底层类型的**转换常量表达式**（[[expr.const.const]]）——因此不允许窄化；
    - 底层类型不固定（¶5.1–5.3）：
        - 有初始化器：必须是整型常量表达式；若它是无作用域枚举类型，枚举量取那个枚举的底层类型，否则取表达式的类型；
        - 第一个枚举量没有初始化器：类型是某个未指定的有符号整型；
        - 其余：与前一个相同，除非加 1 后放不下，那么取一个足以容纳的未指定整型；不存在这样的类型则非良构。

```cpp title="enumerator-types.cpp" error
#include <type_traits>

enum E1 : unsigned char { a = 255, b };   // error: b = 256 不能表示为 unsigned char
enum E2 : unsigned { c = -1 };            // error: 转换常量表达式不允许窄化 -1 → unsigned
enum E3 { d = 1u, e = sizeof(d) };        // OK: 闭花括号前 d 的类型是 unsigned int
static_assert(std::is_same_v<decltype(d), E3>);   // 闭花括号后 d 的类型是 E3
```

¶6：何时成为完整类型——

- 底层类型固定：在 *enum-base* 之后（如果有）**立即**完整；所以枚举量的初始化器里就可以 `sizeof(E)`；
- 底层类型不固定：直到 *enum-specifier* 的闭花括号 `}` 才完整。

¶7：底层类型不固定时，它是一个**能表示所有枚举量值**的整型；具体是哪个由实现定义 {{impl}}，但**不得大于 `int`**，除非某个枚举量的值放不进 `int` 或 `unsigned int`。没有任何整型能表示全部值时非良构。枚举量列表为空时，视为只有一个值为 0 的枚举量。

```cpp run title="underlying-unfixed.cpp" impl
#include <cstdio>
#include <type_traits>

enum E6 { i1 = 0x7fffffff, i2 };          // i2 = 2^31：int 放不下，unsigned int 可以
enum E7 { m = -1, n = 0x80000000u };      // 需要同时表示 -1 和 2^31：int/unsigned 都不行

int main() {
    std::printf("E6: size=%zu signed=%d\n", sizeof(E6), std::is_signed_v<std::underlying_type_t<E6>>);
    std::printf("E7: size=%zu\n", sizeof(E7));
}
// Clang/x86-64 或 arm64：E6: size=4 signed=0；E7: size=8
```

## 枚举的值集合（¶8）——"最小位域"规则

这是枚举一节中 language lawyer 最常被问的一段。

¶8：

- 底层类型**固定**：枚举的值就是**底层类型的所有值**。`enum class E : int {}` 能表示任何 `int`。
- 底层类型**不固定**：枚举的值是"一个**假想的、宽度最小为 M 的整数类型**所能表示的值"，其中 M 是能表示全部枚举量的最小宽度。换句话说，**能容纳所有枚举量的最小位域**的宽度就是 M。
- 允许定义一个"含有不对应任何枚举量的值"的枚举（标志位组合就是这样）。
- 空枚举的值集合与"只有一个值为 0 的枚举量"相同。

这个假想整数类型是有符号还是无符号？看枚举量：若有负值，就是有符号（补码，范围 −2^(M−1) … 2^(M−1)−1）；否则是无符号（0 … 2^M−1）。

| 枚举 | 枚举量 | M | 值的范围 |
|---|---|---|---|
| `enum A { a = 1, b = 4 };` | 1, 4 | 3（无符号） | 0 … 7 |
| `enum B { c = -1, d = 2 };` | −1, 2 | 3（有符号） | −4 … 3 |
| `enum C { };` | 视为 0 | 1 | 0 … 1 |
| `enum D : int { };` | 固定 | — | 全部 `int` |

脚注 75 说明：这个值集合**用于定义提升和转换的语义**，并不排除枚举类型的表达式取到范围之外的值。真正有后果的规则在 [[expr.static.cast#8]]：

!!! std
    If the enumeration type does not have a fixed underlying type, the value is unchanged if the original value is within the range of the enumeration values, and otherwise, the behavior is undefined.

    底层类型不固定时，范围内的值保持不变；超出范围则是未定义行为。

```cpp title="enum-range-ub.cpp" error
#include <cstdint>

enum A { a = 1, b = 4 };                  // 值集合 0..7
constexpr A x1 = static_cast<A>(7);       // OK: 在值集合内，即使不对应任何枚举量
constexpr A x2 = static_cast<A>(8);       // error: 超出范围是 UB，常量求值中必须被诊断

enum class S : std::uint8_t { };          // 固定底层类型：值集合 = 全部 uint8_t
constexpr S s = static_cast<S>(255);      // OK
```

运行期的 `static_cast<A>(8)` 是 {{ub}}。为什么标准要这样规定？因为它允许实现**用更窄的存储或寄存器来表示枚举**，也允许优化器利用值域信息：一个只能取 0…7 的值，`switch` 可以省掉范围检查。Clang 在 `-fstrict-enums` 下确实会利用这一点（默认不开启）；而 UBSan 的 `-fsanitize=enum` 可以检测"加载了超出值域的枚举值"。

!!! tip "要可靠地存放任意整数，就固定底层类型"
    `enum Flags : unsigned { A = 1, B = 2, C = 4 };` 的值集合是全部 `unsigned`，`A | B | C | 1024` 转换回 `Flags` 永远不是 UB。这也是 `std::byte`（`enum class byte : unsigned char {}`）选择固定底层类型的原因之一。

## 大小、表示与布局兼容（¶9–¶10）

¶9：枚举与其底层类型有**相同的大小、值表示和对齐要求**；而且每个枚举值与底层类型对应值的表示相同。所以 `memcpy` 一个 `enum E : int` 到 `int` 得到的就是那个整数值。

¶10：两个枚举是[[g:layout-compatible-enumerations|布局兼容枚举]]（layout-compatible enumerations），如果它们有相同的底层类型和相同的值集合。这被 [[basic.types.general]] 中"布局兼容类型"的定义引用，进而影响公共初始序列（common initial sequence）规则。

## 向整数的转换（¶11）

¶11：无作用域枚举量或无作用域枚举对象的值，通过**整型提升**（[[conv.prom]]）转换为整数：

- 底层类型不固定：提升为 `int`、`unsigned`、`long`、`unsigned long`、`long long`、`unsigned long long` 中**第一个能表示全部值**的类型（[[conv.prom#3]]）；
- 底层类型固定：可以转换为底层类型，若底层类型可以继续提升，也可以转换为提升后的类型（[[conv.prom#4]]）。

有作用域枚举**没有**任何隐式转换——不能转 `int`，也不能上下文转换为 `bool`：

```cpp title="enum-conversions.cpp" error
enum color { red, yellow, green = 20, blue };
enum class Col { red, yellow, green };

void f() {
    color c1 = 1;            // error: int 不能隐式转换为枚举
    int i = yellow;          // OK: 整型提升，i == 1
    int x = Col::red;        // error: 有作用域枚举不转换为 int
    Col y = Col::red;
    if (y) { }               // error: 不能上下文转换为 bool
    int j = static_cast<int>(Col::green);   // OK: 显式转换（[expr.static.cast]/7）
    bool same = (y == Col::red);            // OK: 同类型比较
    (void)i; (void)j; (void)same;
}
```

### 与算术运算的交互：C++20 弃用、C++26 删除

[[expr.arith.conv#1]] 第 1.2、1.3 项：

- 一个操作数是有作用域枚举时，不做任何转换，另一个操作数不是同一类型就非良构；
- 一个操作数是枚举、另一个是**不同的**枚举类型或**浮点类型**时，非良构 {{c++26}}。

```cpp title="enum-arith.cpp" error
enum A { a }; enum B { b };
int x = a + b;          // error (C++26)；C++20/23 中弃用
double y = a + 1.0;     // error (C++26)；C++20/23 中弃用
bool z = (a == b);      // error (C++26)：比较也执行常用算术转换
int w = a + 1;          // OK: 枚举与整数
int v = a | a;          // OK: 同一枚举
```

C++20 用 [[P1120R0]] 弃用了这些混合运算，C++26 用 [[P2864R2]] 把它们改为非良构。Clang 23 在 `-std=c++2c` 下报错、在 `-std=c++23` 下给弃用警告。

## 花括号初始化：C++17 的"强类型整数"（[[dcl.init.list#3.8]]）

C++17 加入了一条规则（[[P0138R2]]）：底层类型**固定**的枚举 `T`（底层类型 `U`），如果用**直接列表初始化**、初始化列表只有一个标量元素 `v`，且 `v` 能隐式转换为 `U`，那么对象被初始化为 `T(v)`；需要窄化则非良构。

```cpp title="enum-brace-init.cpp" error
enum byte : unsigned char { };
byte b { 42 };           // OK (C++17)
byte c = { 42 };         // error: 复制列表初始化不适用
byte d = byte{ 42 };     // OK: 同 b
byte e { 256 };          // error: 窄化

enum class Handle : int { };
Handle h { 7 };          // OK: 构造"强类型整数"
Handle h2 ( 7 );         // error: 不是列表初始化
```

动机：`enum class Handle : int {};` 是零开销的**强类型整数**（不同 handle 类型之间不能混用），但 C++14 中构造它必须写 `static_cast<Handle>(7)`，相当啰嗦。花括号形式不允许窄化，又只适用于固定底层类型（这样才知道 `U` 是谁），因此是安全的。`std::byte` 正是这一规则的主要受益者。

## 枚举量的名字与链接（¶12）

¶12：每个**无作用域**枚举量的名字也被绑定到**直接包含该 *enum-specifier* 的作用域**中。所以既可以写 `left`，也可以写 `direction::left`（C++11 起允许用枚举名限定无作用域枚举量）。有作用域枚举量只能限定访问。

```cpp title="enum-scope.cpp" error
enum direction { left = 'l', right = 'r' };
enum class altitude { high = 'h', low = 'l' };

void g() {
    direction d;
    d = left;                 // OK
    d = direction::right;     // OK (C++11)
    altitude a;
    a = high;                 // error: high 不在作用域中
    a = altitude::low;        // OK
    (void)d; (void)a;
}
```

¶12 后半段解决一个链接问题：在头文件里写 `enum { A, B };`（无名、无用于链接的 typedef 名），多个翻译单元里的这个"同一个"枚举是否是同一个类型？[[basic.def.odr]] 要求定义相同，但无名类型如何跨 TU 识别？规则是：**有第一个枚举量**的无名枚举，在链接意义上由"**底层类型 + 第一个枚举量**"表示，称为"以枚举量作为用于链接的名字"（[[P2115R0]]，C++20）。注 3：没有枚举量的无名枚举，每一个都是不同的类型。

## using enum 声明（[enum.udecl]）{{c++20}}

```text
using-enum-declaration: using enum using-enum-declarator ;
using-enum-declarator:  nested-name-specifier(opt) identifier
                      | nested-name-specifier(opt) simple-template-id
                      | splice-type-specifier
```

[enum.udecl] ¶1：*using-enum-declarator* 若是 *splice-type-specifier*（[[dcl.type.splice]]，C++26 反射），就指代它所指的类型；否则做**仅类型查找**（type-only lookup，[[basic.lookup.general]]）——非类型的同名声明被忽略。它必须指代一个**非待决**的、*enum-specifier* 可达（即已完整定义）的枚举类型。

¶2：`using enum E;` **等价于对每个枚举量各写一个 using 声明**（[[namespace.udecl]]）。这一句就决定了所有行为：冲突规则、类作用域中的成员查找、访问控制，都沿用 using 声明的规则。

```cpp title="using-enum.cpp" ok
enum class Color { red, green, blue };

const char* name(Color c) {
    switch (c) {
        using enum Color;           // 只在 switch 体内生效
        case red:   return "red";
        case green: return "green";
        case blue:  return "blue";
    }
    return "?";
}

enum E { x };
void f() {
    int E;
    using enum E;                   // OK: 仅类型查找，忽略 int E
}

using F = E;
using enum F;                       // OK: 通过别名
template<class T> using EE = T;
void g() { using enum EE<E>; }      // OK: simple-template-id

int main() { return name(Color::green)[0] == 'g' ? 0 : 1; }
```

¶3（注）：类作用域中的 `using enum` 让枚举量可通过**成员查找**访问：

```cpp title="using-enum-class.cpp" ok
enum class fruit { orange, apple };
struct S {
    using enum fruit;          // 把 orange、apple 引入 S
};
void f() {
    S s;
    (void)s.orange;            // OK: fruit::orange
    (void)S::orange;           // OK
}

int main() {}
```

这让"把枚举挪进类里"的重构变得无痛：原来写 `S::orange` 的代码在枚举移到类外后，只需在类中加一行 `using enum`。

¶4（注）：两个 `using enum` 引入同名枚举量会冲突（因为两个 using 声明命名的不是函数，按 [[namespace.udecl#10]] 非良构）：

```cpp title="using-enum-conflict.cpp" error
enum class fruit { orange, apple };
enum class color { red, orange };

void f() {
    using enum fruit;          // OK
    using enum color;          // error: color::orange 与 fruit::orange 冲突
}

template<class T> void h() {
    using enum T;              // error: 不能是待决类型
}

enum class Fwd;
void m() {
    using enum Fwd;            // error: 只有不透明声明，没有可达的 enum-specifier
}
```

为什么要求非待决、且 *enum-specifier* 可达？因为编译器必须在看到 `using enum` 的那一刻就知道要引入哪些名字——名字查找在模板定义时进行（[[temp.res]]），引入的名字集合不能等到实例化才确定。

## 实现视角

!!! impl "底层类型的选择与 ABI"
    - 对不固定底层类型的枚举，GCC 和 Clang（Itanium ABI 平台）选择 `unsigned int`（全部非负且放得下）或 `int`，放不下再升级到 64 位类型；`-fshort-enums` 让 GCC/Clang 选择最小的能容纳的类型——这会改变 ABI，必须全程序一致。
    - MSVC 对不固定底层类型的无作用域枚举通常直接使用 `int`，与 GCC/Clang 的选择不同；跨编译器共享的头文件中的枚举如果关心大小，应当固定底层类型。
    - 枚举在 Itanium 修饰名中与类一样按名字编码，底层类型不出现在修饰名里；所以改变底层类型不会导致链接错误，却会静默破坏 ABI（大小改变）。

!!! impl "值域优化"
    GCC 和 Clang 都有 `-fstrict-enums` 选项（默认关闭），允许优化器假设枚举对象只取值集合内的值（¶8）。若代码依赖"在不固定底层类型的枚举中塞任意整数"，在这些优化下可能出错——固定底层类型可以彻底消除这类问题。

## 历史与演进

!!! history "C++98 → C++26"
    - **C++98**：只有无作用域枚举，底层类型实现定义，不能前置声明；值集合由"最小位域"规则定义（当时措辞基于 b_min/b_max）。
    - **C++11**：有作用域枚举、固定底层类型、不透明枚举声明；允许 `E::enumerator` 限定无作用域枚举量；`std::underlying_type`。
    - **C++17**：固定底层类型的枚举可以从整数直接列表初始化（[[P0138R2]]）；`std::byte`。
    - **C++20**：`using enum`（[[P1099R5]]）；弃用不同枚举之间、枚举与浮点之间的算术与比较（[[P1120R0]]）；无名枚举以第一个枚举量作为用于链接的名字（[[P2115R0]]）。
    - **C++23**：标准库 `std::to_underlying`、`std::is_scoped_enum`。
    - **C++26**：上述弃用的混合运算改为非良构（[[P2864R2]]）；`using enum` 可以使用 *splice-type-specifier*（静态反射）；超出值集合的转换在当前草案中被归入核心语言 UB 汇总（`[ub:expr.static.cast.enum.outside.range]`）。

## 陷阱

!!! pitfall "\"枚举只能取枚举量的值\"是错的"
    `enum A { a = 1, b = 4 };` 可以合法地持有 0、2、3、5、6、7。`switch` 中漏掉 `default` 时，编译器的 `-Wswitch` 只检查枚举量，不代表值不可能出现。

!!! pitfall "不固定底层类型的枚举不能装任意 int"
    `static_cast<A>(100)` 对上面的 `A` 是 UB。位标志枚举请固定底层类型。

!!! pitfall "`enum class E : int` 的 `E{1}` 可以，`E e = {1};` 不行"
    C++17 规则只适用于**直接**列表初始化。

!!! pitfall "using enum 只是一组 using 声明"
    它不让枚举隐式转换为整数，也不改变枚举量的类型；它只是让名字在当前作用域可见，并且会与同名声明冲突。

## 思考题

!!! question "思考题 1"
    `enum E { a = -3, b = 3 };` 的值集合是什么？`static_cast<E>(4)` 与 `static_cast<E>(-4)` 哪个是 UB？

<details markdown="1">
<summary>答案</summary>

需要有符号表示 −3 和 3：宽度 3 的有符号位域范围 −4…3 能容纳，所以 M = 3，值集合是 −4…3。`static_cast<E>(-4)` 合法（在值集合内，即便不对应任何枚举量）；`static_cast<E>(4)` 超出范围，是 UB，在常量求值中会被诊断。
</details>

!!! question "思考题 2"
    为什么 `enum class E;` 可以不写底层类型，而 `enum E;` 不行？如果允许后者，会有什么问题？

<details markdown="1">
<summary>答案</summary>

有作用域枚举的底层类型未指定时**固定**为 `int`（¶5），所以不透明声明后就是完整类型，大小已知。无作用域枚举不写 *enum-base* 时底层类型不固定，要看完所有枚举量才能决定（¶7），可能是 `int`、`unsigned` 甚至 64 位类型；如果允许 `enum E;` 之后就使用 `E`（例如作为函数参数按值传递），不同翻译单元可能对 `E` 的大小有不同假设，ABI 无法确定。
</details>

!!! question "思考题 3"
    下面的代码良构吗？`S::apple` 的类型是什么？

    ```cpp
    enum class fruit { orange, apple };
    struct S { using enum fruit; };
    auto v = S::apple;
    ```

<details markdown="1">
<summary>答案</summary>

良构。`using enum fruit;` 等价于 `using fruit::orange; using fruit::apple;`（[enum.udecl]/2），在类作用域中允许 using 声明命名枚举量（[[namespace.udecl#3]]）。`S::apple` 通过成员查找找到 using 声明，进而找到 `fruit::apple`，类型是 `fruit`，不会变成整数。
</details>

## 小结

!!! summary "要点"
    - 两条正交的维度：**有/无作用域**（名字是否泄漏、能否隐式转整数）× **底层类型固定/不固定**（能否不透明声明、值集合多大）。
    - 有作用域枚举的底层类型默认固定为 `int`。
    - 不固定底层类型的值集合 = 能容纳全部枚举量的最小位域；超出范围的 `static_cast` 是 UB。固定底层类型的值集合 = 底层类型的全部值。
    - 枚举与底层类型大小、对齐、值表示相同。
    - C++17：固定底层类型可 `E{n}`；C++20：`using enum`；C++26：不同枚举/枚举与浮点的混合运算非良构。
