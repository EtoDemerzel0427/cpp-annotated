---
title: 枚举
summary: 有作用域与无作用域枚举的区别，底层类型何时固定、由谁决定，枚举能取哪些值、什么时候转换是 UB，不透明声明，以及 C++17 的花括号初始化和 C++20 的 using enum。
status: done
covers: dcl.enum, enum.udecl
papers: P0138R2, P1099R5, P1120R0, P2864R2, P2115R0
related: basic.compound, basic.scope.enum, conv.prom, expr.static.cast, expr.arith.conv, dcl.init.list, namespace.udecl, dcl.typedef, basic.link
tags: 枚举, 类型, 底层类型, using enum
updated: 2026-10-19
---

!!! tldr
    - `enum class` 的枚举量只在枚举自己的作用域里，也不会隐式转换成整数；普通 `enum` 的枚举量泄漏到外层作用域，并且会提升为整数。
    - 写了 `: T` 或者是 `enum class` 的枚举，底层类型是固定的，可以先做不透明声明、以后再给出枚举量；普通 `enum` 不写 `: T` 时，底层类型由实现按枚举量的值来选。
    - 底层类型固定时，枚举能取底层类型的全部值；不固定时，只能取能容纳所有枚举量的最小位域的值，`static_cast` 到范围之外是 UB。
    - C++17 起，底层类型固定的枚举可以写 `E{42}`；C++20 的 `using enum E;` 相当于为每个枚举量各写一条 using 声明。
    - C++26 起，两个不同枚举类型之间、枚举与浮点之间的算术和比较是非良构的。

## 两种枚举（¶2）

<div class="compare" markdown="1">

```cpp ok
enum color { red, green };
int i = green;       // OK: 提升为 1
color c = red;       // red 在外层作用域
int red_count = 0;   // 不能再叫 red
```

```cpp error
enum class Col { red, green };
int i = Col::green;  // error: 不转换
Col c = Col::red;    // 必须写 Col::
int red = 0;         // OK: 不冲突
```

</div>

**枚举**（enumeration）是带一组具名常量的独立类型（[[basic.compound]]），这些常量叫**枚举量**（enumerator）。从 C 继承来的 `enum` 有三个问题：枚举量泄漏到外层作用域，枚举会隐式转换成整数，底层的整数类型由实现决定、因而无法前置声明。

¶2 C++11 起，`enum class` 和 `enum struct`（两者完全等价）声明的是[[g:scoped-enumeration|有作用域枚举]]（scoped enumeration），只用 `enum` 声明的是[[g:unscoped-enumeration|无作用域枚举]]。两者的区别：

| | 无作用域枚举 `enum` | 有作用域枚举 `enum class` |
|---|---|---|
| 枚举量的作用域 | 枚举的作用域和外层作用域（¶12） | 只在枚举的作用域 |
| 隐式转为整数 | 会，通过整型提升（¶11） | 不会，也不能按上下文转换成 `bool` |
| 名字能否省略 | 能（匿名枚举） | 不能 |
| 不写 `: T` 时的底层类型 | 不固定，由实现选（¶7） | 固定为 `int`（¶5） |
| 不透明声明 | 必须写 `: T` | 可以不写 |

¶2 还规定了枚举量的值。写了 `=` 的取那个常量表达式的值；没写的，第一个是 0，之后每个是前一个加 1。同一个枚举里名字不能重复，值可以重复：

```cpp title="enum-values.cpp" ok
enum { a, b, c = 0 };          // a=0, b=1, c=0
enum { d, e, f = e + 2 };      // d=0, e=1, f=3
enum B : bool { no, yes };     // OK: bool 是整型
static_assert(a == c && f == 3 && yes == true);

int main() {}
```

`: T` 这一部分叫 *enum-base*，`T` 必须是整型，cv 限定被忽略（`: const int` 等于 `: int`）。`bool` 也是整型（[[basic.fundamental]]），所以 `enum B : bool` 合法；浮点类型和其他非整型都不行。

## 底层类型（¶5、¶7）

¶5 每个枚举都是一个与其他所有类型不同的类型，并且有一个[[g:underlying-type|底层类型]]（underlying type），即它在内存里实际使用的整型。写了 enum-base，或者是没写 enum-base 的有作用域枚举（此时为 `int`），底层类型就是[[g:fixed-underlying-type|固定的]]（fixed）。

¶7 底层类型不固定时，它是某个能表示全部枚举量值的整型，具体是哪个由实现定义 {{impl}}。限制只有一条：除非某个枚举量的值放不进 `int` 或 `unsigned int`，否则底层类型不能大于 `int`。没有任何整型能表示全部值时，枚举非良构。枚举量列表为空时，按只有一个值为 0 的枚举量处理。

```cpp run title="underlying-unfixed.cpp" impl
#include <cstdio>
#include <type_traits>

enum E6 { i1 = 0x7fffffff, i2 };          // i2 = 2^31：int 放不下，unsigned int 可以
enum E7 { m = -1, n = 0x80000000u };      // 要同时表示 -1 和 2^31：int、unsigned 都不行

int main() {
    std::printf("E6: size=%zu signed=%d\n", sizeof(E6), std::is_signed_v<std::underlying_type_t<E6>>);
    std::printf("E7: size=%zu\n", sizeof(E7));
}
// 本机 Clang 23（arm64）：E6: size=4 signed=0；E7: size=8
```

### 闭花括号之前，枚举量是什么类型

¶5 闭花括号之后，每个枚举量的类型都是这个枚举类型。在花括号里面，后面的枚举量的初始化器可能用到前面的枚举量，这时它们的类型另有规定：

- 底层类型固定：枚举量的类型是底层类型，初始化器必须是底层类型的转换常量表达式（[[expr.const.const]]），因此不允许窄化；
- 底层类型不固定（¶5.1–¶5.3）：有初始化器的，取初始化表达式的类型（表达式是无作用域枚举类型时，取那个枚举的底层类型）；第一个枚举量没有初始化器时，是某个未指定的有符号整型；其余的与前一个相同，加 1 后放不下就换成一个放得下的未指定整型，不存在这样的类型则非良构。

```cpp title="enumerator-types.cpp" error
#include <type_traits>

enum E1 : unsigned char { a = 255, b };   // error: b = 256 不能表示为 unsigned char
enum E2 : unsigned { c = -1 };            // error: 转换常量表达式不允许 -1 → unsigned 的窄化
enum E3 { d = 1u, e = sizeof(d) };        // OK: 花括号内 d 的类型是 unsigned int
static_assert(std::is_same_v<decltype(d), E3>);   // 闭花括号后 d 的类型是 E3
```

## 不透明声明（¶3、¶4、¶6）

底层类型固定，就不必看到枚举量也能知道枚举的大小。于是可以先声明、以后再给出枚举量：

```cpp title="opaque-enum.cpp" error
enum class Color : unsigned char;            // 不透明声明，已是完整类型
static_assert(sizeof(Color) == 1);           // OK: 还没看到枚举量
enum class Color : unsigned char { red, green };   // OK: 补上枚举量

enum class W;                                // OK: 底层类型默认 int
enum U : int;                                // OK
enum V;                                      // error: 无作用域枚举必须写 enum-base
enum W2 : long;
enum class W2 : long;                        // error: 先前声明为无作用域枚举
enum class Color : int;                      // error: 底层类型不同
```

没有枚举量列表、以分号结束的声明叫[[g:opaque-enum-declaration|不透明枚举声明]]（opaque-enum-declaration）。¶3 规定它要么重声明当前作用域里的某个枚举，要么声明一个新枚举。注 2 指出，这样声明的枚举底层类型固定，并且已经是完整类型：可以用 `sizeof`、定义对象、按值传递，只是还不知道有哪些枚举量。

¶3 后半段要求重声明前后一致。有作用域枚举不能改成无作用域，也不能换底层类型；无作用域枚举不能改成有作用域，每次重声明都必须写 enum-base，并且指定相同的底层类型。

`enum V;` 被禁止，是因为不固定的底层类型要看到全部枚举量才能确定，而不透明声明的用途恰恰是在看到枚举量之前就让类型完整。如果允许，不同的翻译单元可能对 `V` 的大小有不同的假设。

¶6 相应地规定了枚举何时完整。底层类型固定的，在 enum-base 之后（没有 enum-base 就在名字之后）立即完整，所以枚举量的初始化器里就可以写 `sizeof(E)`；不固定的，到闭花括号 `}` 才完整。

¶4 枚举的名字可以带限定，用来在类外或命名空间外补全先前声明的枚举。这样的声明不能出现在类作用域里，并且必须对应那个类或命名空间里已有的声明：

```cpp title="enum-out-of-class.cpp" ok
struct X {
    enum class State;               // 只在类里不透明声明
};
enum class X::State { idle, busy }; // 在类外（比如实现文件里）补全

namespace N { enum class E : int; }
enum class N::E : int { x };        // OK

int main() { return static_cast<int>(X::State::busy) - 1; }
```

头文件里的类只暴露 `enum class State;`，具体的状态列表可以放在实现文件里。¶1 另外规定，带限定名的不透明声明（如 `enum class X::State;`）只能是显式特化，用于类模板的成员枚举。

## 枚举能取哪些值（¶8）

```cpp title="enum-range-ub.cpp" error
#include <cstdint>

enum A { a = 1, b = 4 };                  // 值集合 0..7
constexpr A x1 = static_cast<A>(7);       // OK: 在值集合内，虽然没有对应的枚举量
constexpr A x2 = static_cast<A>(8);       // error: 超出范围是 UB，常量求值中必须诊断

enum class S : std::uint8_t { };          // 底层类型固定：值集合是全部 uint8_t
constexpr S s = static_cast<S>(255);      // OK
```

¶8 规定了[[g:enumeration-values|枚举的值]]（values of the enumeration）：

- 底层类型固定时，就是底层类型的全部值。`enum class E : int {}` 能表示任何 `int`。
- 不固定时，是能容纳所有枚举量的最小位域所能表示的值。设这个最小宽度为 M：没有负枚举量时，范围是 0 到 2<sup>M</sup>−1；有负枚举量时，按补码取 −2<sup>M−1</sup> 到 2<sup>M−1</sup>−1。
- 枚举可以取不对应任何枚举量的值，位标志的组合就是这样。空枚举按只有一个值为 0 的枚举量处理。

| 枚举 | 枚举量 | M | 值的范围 |
|---|---|---|---|
| `enum A { a = 1, b = 4 };` | 1, 4 | 3 | 0 … 7 |
| `enum B { c = -1, d = 2 };` | −1, 2 | 3 | −4 … 3 |
| `enum C { };` | 按 0 处理 | 1 | 0 … 1 |
| `enum D : int { };` | 固定 | — | 全部 `int` |

脚注 75 说明，这个值集合只用来定义提升和转换的语义，并不保证枚举类型的表达式一定落在范围内。真正有后果的是 [[expr.static.cast#8]]：

!!! std
    If the enumeration type does not have a fixed underlying type, the value is unchanged if the original value is within the range of the enumeration values, and otherwise, the behavior is undefined.

    底层类型不固定时，范围内的值不变，范围外的是未定义行为。

所以运行时的 `static_cast<A>(8)` 是 {{ub}}。这让实现可以用更窄的存储表示枚举，也让优化器可以利用值域：一个只能取 0…7 的值，`switch` 可以省掉范围检查。GCC 和 Clang 在 `-fstrict-enums` 下会这样优化（默认关闭）；UBSan 的 `-fsanitize=enum` 能检测加载到的超出值域的枚举值。

!!! tip "要存放任意整数，就固定底层类型"
    `enum Flags : unsigned { A = 1, B = 2, C = 4 };` 的值集合是全部 `unsigned`，把 `A | B | C | 1024` 转换回 `Flags` 永远不是 UB。`std::byte` 定义为 `enum class byte : unsigned char {}`，固定底层类型也是为了这一点。

## 大小与表示（¶9–¶10）

¶9 枚举与它的底层类型有相同的大小、值表示和对齐要求，每个值的表示也与底层类型对应值的表示相同。所以把一个 `enum E : int` 的对象 `memcpy` 到 `int` 里，得到的就是那个整数值。

¶10 两个枚举的底层类型相同、值集合也相同时，它们是[[g:layout-compatible-enumerations|布局兼容枚举]]。[[basic.types.general]] 里布局兼容类型的定义用到了这个概念，并由此影响公共初始序列的规则。

## 转换为整数（¶11）

¶11 无作用域枚举的枚举量或对象，通过整型提升（[[conv.prom]]）转换成整数：

- 底层类型不固定：提升为 `int`、`unsigned`、`long`、`unsigned long`、`long long`、`unsigned long long` 中第一个能表示全部值的类型（[[conv.prom#3]]）；
- 底层类型固定：可以转换为底层类型，底层类型本身还能提升的话，也可以转换为提升后的类型（[[conv.prom#4]]）。

有作用域枚举没有任何隐式转换，既不能变成 `int`，也不能按上下文转换为 `bool`，只能用 `static_cast`（[[expr.static.cast]]）：

```cpp title="enum-conversions.cpp" error
enum color { red, yellow, green = 20, blue };
enum class Col { red, yellow, green };

void f() {
    color c1 = 1;            // error: int 不能隐式转换为枚举
    int i = yellow;          // OK: 整型提升，i == 1
    int x = Col::red;        // error: 有作用域枚举不转换为 int
    Col y = Col::red;
    if (y) { }               // error: 不能按上下文转换为 bool
    int j = static_cast<int>(Col::green);   // OK: 显式转换
    bool same = (y == Col::red);            // OK: 同类型比较
    (void)i; (void)j; (void)same;
}
```

### 混合运算：C++20 弃用，C++26 非良构

无作用域枚举虽然能提升为整数，但两个不同枚举之间、枚举与浮点之间的算术和比较通常是写错了。[[expr.arith.conv#1]] 第 1.2、1.3 项规定，一个操作数是有作用域枚举时另一个必须同类型；一个是枚举、另一个是不同的枚举类型或浮点类型时，非良构 {{c++26}}：

```cpp title="enum-arith.cpp" error
enum A { a }; enum B { b };
int x = a + b;          // error (C++26)；C++20/23 中弃用
double y = a + 1.0;     // error (C++26)；C++20/23 中弃用
bool z = (a == b);      // error (C++26)：比较也执行常用算术转换
int w = a + 1;          // OK: 枚举与整数
int v = a | a;          // OK: 同一枚举
```

C++20 的 [[P1120R0]] 弃用了这些写法，C++26 的 [[P2864R2]] 把它们改为非良构。本机 Clang 23 在 `-std=c++2c` 下报错，在 `-std=c++23` 下给弃用警告。

## 用花括号从整数构造（[[dcl.init.list#3.8]]）{{c++17}}

`enum class Handle : int {};` 是一个零开销的强类型整数：不同的 handle 类型之间不能混用。但在 C++14 中构造它只能写 `static_cast<Handle>(7)`。

C++17 的 [[P0138R2]] 加入了一条规则：底层类型 `U` 固定的枚举，用直接列表初始化、列表里只有一个能隐式转换为 `U` 的标量时，对象初始化为那个值；需要窄化则非良构。

```cpp title="enum-brace-init.cpp" error
enum byte : unsigned char { };
byte b { 42 };           // OK (C++17)
byte c = { 42 };         // error: 复制列表初始化不适用
byte d = byte{ 42 };     // OK: 同 b
byte e { 256 };          // error: 窄化

enum class Handle : int { };
Handle h { 7 };          // OK
Handle h2 ( 7 );         // error: 不是列表初始化
```

花括号形式不允许窄化，又只适用于固定底层类型（这样才知道 `U` 是什么），所以是安全的。`std::byte b{42};` 依靠的就是这条规则。

## 枚举量的名字与链接（¶12）

¶12 无作用域枚举量的名字同时绑定到直接包含这个枚举的作用域里。所以既可以写 `left`，也可以写 `direction::left`（C++11 起允许用枚举名限定无作用域枚举量）。有作用域枚举量只能用限定名：

```cpp title="enum-scope.cpp" error
enum direction { left = 'l', right = 'r' };
enum class altitude { high = 'h', low = 'l' };

void g() {
    direction d;
    d = left;                 // OK
    d = direction::right;     // OK
    altitude a;
    a = high;                 // error: high 不在作用域中
    a = altitude::low;        // OK
    (void)d; (void)a;
}
```

¶12 后半段处理链接。头文件里写 `enum { A, B };` 这样的无名枚举，被多个翻译单元包含时，它们算不算同一个类型？ODR（[[basic.def.odr]]）要求各处的定义相同，可无名类型要靠什么跨翻译单元对应起来？规则是：没有用于链接的 typedef 名（[[dcl.typedef]]）、但有枚举量的无名枚举，在链接上由底层类型加第一个枚举量来标识，称为以枚举量作为用于链接的名字（C++20，[[P2115R0]]）。注 3 指出，没有枚举量的无名枚举，每一个都是不同的类型。

## using enum（[enum.udecl]）{{c++20}}

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

int main() { return name(Color::green)[0] == 'g' ? 0 : 1; }
```

¶2 `using enum E;` 等价于为 `E` 的每个枚举量各写一条 using 声明（[[namespace.udecl]]）。它的冲突规则、在类作用域里的成员查找、访问控制，都沿用 using 声明的规则。它不改变枚举量的类型，也不让有作用域枚举变得能隐式转换为整数。

¶1 `using enum` 后面的名字做仅类型查找（type-only lookup，[[basic.lookup.general]]），忽略同名的非类型声明。它可以是别名、别名模板的特化，C++26 起还可以是反射的 *splice-type-specifier*（[[dcl.type.splice]]）。它必须指代一个非待决的、枚举定义可达的枚举类型：

```cpp title="using-enum-lookup.cpp" ok
enum E { x };
void f() {
    int E = 0;
    using enum E;                   // OK: 仅类型查找，忽略 int E
    (void)E;
}

using F = E;
using enum F;                       // OK: 通过别名
template<class T> using EE = T;
void g() { using enum EE<E>; }      // OK

int main() {}
```

不允许待决类型，也不允许只有不透明声明的枚举，是因为编译器必须在看到 `using enum` 时就知道要引入哪些名字。模板定义里的名字查找在定义时进行（[[temp.res]]），引入的名字集合不能等到实例化才确定。

¶4（注）两条 `using enum` 引入同名的枚举量时会冲突，因为这相当于两条命名非函数的 using 声明引入同一个名字（[[namespace.udecl#10]]）：

```cpp title="using-enum-errors.cpp" error
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
    using enum Fwd;            // error: 只有不透明声明，枚举量还未知
}
```

¶3（注）在类作用域里写 `using enum`，枚举量就能通过成员查找访问：

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

这方便把嵌套在类里的枚举挪到类外。原来枚举定义在 `S` 里面，代码写的是 `S::orange`；把枚举移到命名空间作用域之后，只要在 `S` 里加一行 `using enum fruit;`，这些代码不用改。

<details class="fine" markdown="1"><summary>其余条文</summary>

¶1 写在 `enum` 关键字后面或不透明声明里的属性属于枚举本身，以后每次用到这个枚举都视为带有这些属性。例如 `enum [[deprecated]] E { };` 之后，每次使用 `E` 都应引发弃用警告。写在枚举量后面的属性只属于那个枚举量（¶2）。

¶1 在类的成员声明里，`enum E` 后面的 `:` 一律解析为 enum-base。这消除了带 enum-base 的枚举声明与枚举类型的无名位域之间的歧义：

```cpp title="enum-base-ambiguity.cpp" error
struct S {
    enum E : int {};
    enum E : int {};      // error: 枚举重定义（": int" 解析为 enum-base，不是位域）
};
```

¶1 枚举名在声明它的地方不做名字查找，而是由这个声明引入。

</details>

## 实现视角

!!! impl "底层类型的选择与 ABI"
    - 对底层类型不固定的枚举，GCC 和 Clang 在 Itanium ABI 平台上选择 `unsigned int`（全部非负且放得下时）或 `int`，放不下再换成 64 位类型。`-fshort-enums` 让它们选能容纳全部值的最小类型，这会改变 ABI，必须全程序一致。
    - MSVC 对底层类型不固定的无作用域枚举通常直接用 `int`，与 GCC、Clang 的选择不同。跨编译器共享的头文件里，关心大小的枚举应当固定底层类型。
    - 在 Itanium 修饰名里，枚举像类一样只按名字编码，底层类型不出现。所以改了底层类型不会导致链接错误，却会悄悄改变对象大小、破坏 ABI。

## 历史与演进

!!! history
    - C++98 只有无作用域枚举，底层类型由实现决定，不能前置声明。值集合当时就由最小位域规则定义。
    - C++11 加入有作用域枚举、固定底层类型和不透明声明，允许用 `E::enumerator` 限定无作用域枚举量，库里加入 `std::underlying_type`。
    - C++17 允许底层类型固定的枚举从整数直接列表初始化（[[P0138R2]]），并加入 `std::byte`。
    - C++20 加入 `using enum`（[[P1099R5]]），弃用不同枚举之间、枚举与浮点之间的算术和比较（[[P1120R0]]），规定无名枚举以第一个枚举量作为用于链接的名字（[[P2115R0]]）。
    - C++23 库里加入 `std::to_underlying` 和 `std::is_scoped_enum`。
    - C++26 把上述混合运算改为非良构（[[P2864R2]]），`using enum` 可以接反射的 splice。

## 常见误解

!!! pitfall "枚举只能取枚举量的值"
    `enum A { a = 1, b = 4 };` 可以合法地持有 0、2、3、5、6、7。`-Wswitch` 只检查是否覆盖了所有枚举量，不说明其他值不可能出现，`switch` 仍然需要考虑 `default`。

!!! pitfall "无作用域枚举能装下任何 int"
    对上面的 `A`，`static_cast<A>(100)` 是 UB。用作位标志的枚举应当固定底层类型。

!!! pitfall "`E e = {1};` 和 `E e{1};` 一样"
    C++17 的规则只适用于直接列表初始化，`E e = {1};` 仍然非良构。

## 思考题

!!! question "思考题 1"
    `enum E { a = -3, b = 3 };` 的值集合是什么？`static_cast<E>(4)` 和 `static_cast<E>(-4)` 哪个是 UB？

<details markdown="1">
<summary>答案</summary>

有负值，所以按有符号补码计算。宽度为 3 的有符号位域范围是 −4…3，能容纳 −3 和 3，所以 M = 3，值集合是 −4…3。`static_cast<E>(-4)` 在值集合内，合法；`static_cast<E>(4)` 超出范围，是 UB，在常量求值中会得到诊断（¶8、[[expr.static.cast#8]]）。
</details>

!!! question "思考题 2"
    下面的代码良构吗？`S::apple` 的类型是什么？

    ```cpp
    enum class fruit { orange, apple };
    struct S { using enum fruit; };
    auto v = S::apple;
    ```

<details markdown="1">
<summary>答案</summary>

良构。`using enum fruit;` 等价于 `using fruit::orange; using fruit::apple;`（[enum.udecl]/2），类作用域里允许 using 声明命名枚举量（[[namespace.udecl#3]]）。`S::apple` 经成员查找找到这条 using 声明，进而找到 `fruit::apple`，类型是 `fruit`，不会变成整数。
</details>
