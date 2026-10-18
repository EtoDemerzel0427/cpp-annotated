---
title: 值类别
summary: 每个表达式恰属 lvalue、xvalue、prvalue 之一；纯右值的"结果对象"与临时量实质化；何时自动插入左值到右值转换；严格别名规则（type-accessible）
status: draft
since: c++11
papers: N3055, P0135R1, P2266R3
related: topics/value-categories, conv.lval, conv.rval, class.temporary, dcl.init.ref, class.copy.elision, dcl.type.decltype, expr.type
tags: 值类别, 对象模型, 严格别名, UB
updated: 2026-10-17
---

**值类别**（value category）是每个表达式除了**类型**之外的第二个静态属性。它回答的问题是：这个表达式**指代**一个已经存在的东西（对象、函数……），还是**产生**一个值去初始化某个东西？如果它指代一个对象，这个对象的资源**能不能被偷走**？

几乎所有其他条款都依赖这个属性：引用绑定（[[dcl.init.ref]]）、重载决议中的引用绑定排序（[[over.ics.rank]]）、`decltype`（[[dcl.type.decltype]]）、复制消除（[[class.copy.elision]]）、内置运算符对操作数的要求（[[expr.compound]]）、以及本节最后一段——**严格别名规则**。

本页逐段释义 [basic.lval]。"如何快速判断任意表达式的值类别"、大张对照表和常见误解，见专题 [[topics/value-categories]]。

## 分类法：两个维度，三个基本类别（¶1、¶2）

¶1 用一张图（Figure 2）给出分类：

```text
            expression
           /          \
      glvalue        rvalue
      /     \        /    \
  lvalue     xvalue      prvalue
```

xvalue 同时属于 glvalue 和 rvalue。五个术语的定义：

- **glvalue**（泛左值）：其求值**确定**某个对象、函数、非静态数据成员或直接基类关系的**身份**（identity）的表达式。
- **prvalue**（纯右值）：其求值**初始化一个对象**，或**计算某个运算符操作数的值**（由所在上下文决定是哪一种）的表达式；或者类型为 cv `void` 的表达式。
- **xvalue**（亡值）：指代一个**资源可被复用**的对象（通常因为它的生命周期快结束了）的 glvalue。
- **lvalue**（左值）：不是 xvalue 的 glvalue。
- **rvalue**（右值）：prvalue 或 xvalue。

¶2 每个表达式**恰好属于** lvalue、xvalue、prvalue 三者之一，这称为它的**值类别**。注释提醒：各内置运算符的条款会说明它要求操作数是什么类别、产生什么类别；例如内置赋值要求左操作数是左值、右操作数是纯右值，结果是左值。用户定义的运算符是函数，其类别由参数类型和返回类型决定。

### 直觉：身份 × 可移动

最常用的理解方式是把分类看成两个二值属性的组合：

| | 可被移动（资源可复用） | 不可被移动 |
|---|---|---|
| **有身份**（指代一个确定的实体） | **xvalue** | **lvalue** |
| **无身份**（只是一个值 / 初始化配方） | **prvalue** | —（不存在） |

- 有身份的是 glvalue；可移动的是 rvalue。
- "无身份且不可移动"的格子是空的：一个连身份都没有的东西，自然也没有谁会在乎它被偷。

这张 2×2 表正是 C++11 引入 xvalue 时的设计动机（见文末"历史与演进"）。

!!! note "“身份” 的精确含义"
    "确定身份"指求值结果是**一个特定的实体**，可以取地址、可以比较是否是同一个对象。`x`、`*p`、`a[i]`、`std::move(x)` 都确定身份；`42`、`x + 1`、`T{}`（C++17 起）则不——它们只描述"一个值"或"如何初始化一个对象"。

    定义里还列出了"非静态数据成员"与"直接基类关系"：这是为 C++26 静态反射准备的——一个拼接表达式 `[: r :]` 可以指代一个非静态数据成员或一个直接基类关系，它是左值（[[expr.prim.splice]]、[[expr.ref]]）。

### ¶3：名字的由来（注释）

lvalue/rvalue 最初得名于"能出现在赋值号左边/右边"（现在早已不准确：`const int` 左值不能出现在左边，而 `std::string() = "x"` 中左边是纯右值）；glvalue = generalized lvalue，prvalue = pure rvalue，xvalue = eXpiring value。注释特别强调：**这些术语描述的是表达式，不是值**。说"一个右值"永远是在说"一个右值表达式"。

## 哪些表达式是 xvalue（¶4，注释）

¶4（注释）列出了产生 xvalue 的全部表达式形式：

| 形式 | 例子 | 条款 |
|---|---|---|
| 可隐式移动（move-eligible）的 *id-expression* 或拼接表达式 | `return x;` 中的 `x`（`x` 是局部对象） | [[expr.prim.id.unqual]] |
| 调用返回类型为"对象类型的右值引用"的函数 | `std::move(x)`、`f()`（`A&& f();`） | [[expr.call]] |
| 转换到对象类型的右值引用 | `static_cast<A&&>(a)`、`(A&&)a` | [[expr.static.cast]] 等 |
| 下标运算，数组操作数是 xvalue | `std::move(arr)[0]` | [[expr.sub]] |
| 类成员访问，对象表达式是 xvalue，成员是非引用的非静态数据成员 | `std::move(a).m`、`f().m` | [[expr.ref]] |
| `.*`，第一操作数是 xvalue，第二操作数是数据成员指针 | `std::move(a).*pm` | [[expr.mptr.oper]] |

一句话总结（也是注释原话的意思）：**具名的右值引用是左值；无名的、指向对象的右值引用是 xvalue；指向函数的右值引用无论具名与否都是左值。**

```cpp ok
#include <utility>
struct A { int m; };
A&& operator+(A, A);
A&& f();
A make();

void demo(A a) {
    A&& ar = static_cast<A&&>(a);
    // xvalue：f()、f().m、static_cast<A&&>(a)、a + a、std::move(a)、make().m
    // lvalue：ar（具名的右值引用！）、a、a.m
    // prvalue：make()
    A b = ar;                 // 调用复制构造：ar 是左值
    A c = std::move(ar);      // 调用移动构造：std::move(ar) 是 xvalue
    (void)b; (void)c;
}
```

注意 `make().m`：`make()` 是纯右值，成员访问要求对象表达式是 glvalue，于是先施行**临时量实质化**（¶7、[[conv.rval]]），得到一个 xvalue，再按 [[expr.ref]] 的规则，xvalue 的成员也是 xvalue。

!!! lawyer "函数的右值引用为何是左值"
    函数没有"资源"可以偷，也没有临时的函数。为了让 `void (&&rf)() = f;` 之类的代码与左值引用的行为一致（例如重载决议、`decltype`），标准规定指代函数的表达式总是左值。可以验证：`decltype((std::move(f)))` 是 `void(&)()`。

## 结果与结果对象（¶5）

¶5 定义了 glvalue 和 prvalue 各自的**结果**（result）：

- glvalue 的结果是它**指代的实体**。
- prvalue 的结果是它**存入其上下文的值**；类型为 cv `void` 的 prvalue 没有结果。
- prvalue 的**结果对象**（[[g:result-object]]）是**被该 prvalue 初始化的那个对象**；cv `void` 的 prvalue 没有结果对象。

注释 4 补充：除了作为 `decltype` 的操作数，**对象类型的 prvalue 总有一个结果对象**；被弃值的 prvalue 会实质化一个临时对象（[[expr.context]]）。

这是 C++17 值类别模型的核心思想：**prvalue 不是对象，而是"初始化某个对象的配方"**。由谁来提供这个对象，取决于 prvalue 出现的上下文：

| 上下文 | 结果对象是 |
|---|---|
| `T x = prvalue;` / `T x(prvalue);` / `T x{prvalue};`（同类型） | 变量 `x` 本身（[[dcl.init.general#15]]） |
| `return prvalue;`（同类型） | 调用方提供的那个对象（返回值的结果对象） |
| 函数实参 `f(prvalue)`（按值形参） | 形参对象 |
| `new T(prvalue)` | 动态分配的对象 |
| 引用绑定 `const T& r = prvalue;` | 实质化出来的临时对象 |
| 成员访问 `prvalue.m`、弃值 `prvalue;` | 实质化出来的临时对象 |
| 内置算术运算的操作数 `1 + 2` | 实质化出来的临时对象（见 ¶7 的讨论） |

于是"复制消除"在 C++17 起不再是一种优化，而是**根本没有东西可复制**：

```cpp run title="no-copy.cpp" ok
struct NonMovable {
    NonMovable() = default;
    NonMovable(const NonMovable&) = delete;
    NonMovable(NonMovable&&) = delete;
};

NonMovable make() { return NonMovable{}; }  // OK：prvalue 直接初始化调用方的对象

int main() {
    NonMovable a = make();                   // OK：a 就是 make() 的结果对象
    NonMovable b = NonMovable(NonMovable()); // OK：只有一个对象 b
    (void)a; (void)b;
}
```

在 C++14 下，上例的三处都非良构（需要可访问的复制/移动构造函数，即便实际被省略）。而**具名返回值**仍然不同：`NonMovable x; return x;` 里 `x` 是一个已存在的对象，返回时需要移动（或 NRVO 优化，但 NRVO 是"允许"而非"保证"），所以要求可移动构造函数——见 [[class.copy.elision]]。

## 何时把 glvalue 变成 prvalue（¶6）

¶6 当一个 glvalue 出现在**要求 prvalue 的操作数位置**时，自动施行三种标准转换之一，把它变成 prvalue：

- 左值到右值转换（[[conv.lval]]）——对一般对象：读取它的值；
- 数组到指针转换（[[conv.array]]）——对数组；
- 函数到指针转换（[[conv.func]]）——对函数。

三个注释各有深意：

- **注 5**：把右值引用绑定到左值**不是**这种语境——`int&& r = x;` 不会因为"需要右值"就对 `x` 做左值到右值转换再实质化一个临时量，而是直接非良构（[[dcl.init.ref]]）。
- **注 6**：转换成 prvalue 时，非类类型的 cv 限定被去掉，所以 `const int` 左值可以用在需要 `int` 纯右值的地方。
- **注 7**：**不存在纯右值位域**。位域经左值到右值转换后得到一个位域类型的普通 prvalue，然后可能被整型提升（[[conv.prom]]）——这是 `unsigned x : 3` 参与运算时被提升为 `int` 的原因。

```cpp ok
struct S { unsigned bits : 3; };
const int ci = 41;

int use(S s) {
    int a = ci + 1;     // ci：const int 左值 → 左值到右值 → int 纯右值
    auto b = s.bits;    // b 的类型是 unsigned（位域的声明类型）
    auto c = +s.bits;   // c 的类型是 int：位域转换后被提升（int 能表示 3 位无符号的全部值）
    return a + b + c;
}
```

## 何时把 prvalue 变成 xvalue（¶7）

¶7 除非另有规定（[[expr.reinterpret.cast]]、[[expr.const.cast]]），每当一个**不是左值到右值转换之结果**的 prvalue 作为**运算符的操作数**出现时，就施行**临时量实质化转换**（temporary materialization conversion，[[conv.rval]]），把它变成 xvalue。

!!! std
    whenever a prvalue that is not the result of the lvalue-to-rvalue conversion appears as an operand of an operator, the temporary materialization conversion is applied to convert the expression to an xvalue.

    只要不是由左值到右值转换得来的纯右值作为运算符的操作数出现，就对它施行临时量实质化。

这条规则值得仔细读：

- 对 `make().m`、`make().f()`、`std::string("a")[0]`：运算符（`.`、`[]`）需要一个对象，prvalue 被实质化成临时对象——这是 ¶7 最直观的用途。
- 对 `1 + 2`：字面理解，`1` 和 `2` 也会先被实质化为临时对象（xvalue），然后因 `+` 要求 prvalue 操作数，按 ¶6 再做左值到右值转换——得到的 prvalue 是"左值到右值转换的结果"，¶7 不再适用，不会无限循环。这样，**运算符读取的每个值都是从某个对象中读出的**，[[conv.lval]] 的"读取对象"语义统一适用于所有操作数。对标量而言这是不可观察的，实现当然不会真的分配存储。
- C++17 的措辞较窄："prvalue 出现在**期望 glvalue** 的操作数位置时"才实质化。当前草案扩大到所有运算符操作数，上面第二点的效果是新措辞带来的。

不属于"运算符操作数"的地方，prvalue **不会**被实质化，例如作为同类型变量的初始化器、作为 `return` 的操作数——这正是保证复制消除的来源。

## ¶8：指路（注释）

¶8 指向 [[dcl.init.ref]]（引用初始化）和 [[class.temporary]]（临时对象）：左值与右值在这些"其他重要语境"中的行为在那里描述。

## 类型完整性与 cv 限定（¶9）

¶9 除非另有说明（[[dcl.type.decltype]]），

- **prvalue 必须具有完整类型或 void 类型**；
- 若其类型为类类型或类类型的（多维）数组，该类**不得是抽象类**（[[class.abstract]]）；
- **glvalue 不得具有 cv `void` 类型**。

注释 9：glvalue 可以是不完整的非 void 类型（例如 `extern int arr[];` 中的 `arr`，或指向不完整类的 `*p`）；**类与数组的 prvalue 可以带 cv 限定，其他 prvalue 总是 cv 无限定的**（[[expr.type#2]] 负责把非类 prvalue 的 cv 去掉）。

```cpp ok
#include <type_traits>
struct A {};
const A  h();          // 返回 const A：调用表达式是类型为 const A 的 prvalue
const int g();         // 返回 const int：调用表达式的类型被调整为 int

static_assert(std::is_same_v<decltype(h()), const A>);
static_assert(std::is_same_v<decltype(g()), int>);

struct Incomplete;
Incomplete make_inc();
using T = decltype(make_inc());   // OK：decltype 的操作数例外，不要求完整
```

为什么类 prvalue 保留 cv？因为它可以调用成员函数，而 `const` 会影响重载决议：`h().mutate()` 在 `const A` 上调用非 const 成员函数是非良构的。正因为如此，"返回 `const T`"会**阻止移动**：`x = h();` 中右操作数是 `const A` 类型的 prvalue，`A::operator=(A&&)` 的形参无法绑定到它，只能退而选择复制赋值——这是"不要按 const 值返回"这条老建议的语言层原因。

```cpp error
struct Abstract { virtual void f() = 0; };
Abstract make_abs();          // 声明 OK（C++20 起不再在声明处检查）
void use() { make_abs(); }    // error: prvalue 不得具有抽象类类型
```

!!! impl "Clang 的遗漏"
    截至写作时，Clang 23 **接受**上例中对 `make_abs()` 的调用（甚至 `auto&& r = make_abs();`），没有给出诊断。按 ¶9 这是非良构的；这一调用也无法真正实现（没有办法构造一个抽象类的完整对象）。

## 可修改的左值（¶10）

¶10 左值是**可修改的**（modifiable），除非其类型带 `const` 限定或是函数类型。注释：通过不可修改的左值或通过右值去修改对象的程序是**非良构**的（[[expr.assign]]、[[expr.post.incr]]、[[expr.pre.incr]]）。注意这里"非良构"的对象是**内置**运算符；类类型的赋值是函数调用，不受此限。

```cpp error
#include <string>
const int c = 0;
int f();

void demo() {
    c = 1;                       // error: c 不是可修改的左值
    f() = 1;                     // error: 内置 = 的左操作数必须是左值
    std::string() = "ok";        // OK：调用 std::string::operator=，在临时对象上
}
```

## 严格别名：type-accessible（¶11）

¶11 是整节在实践中影响最大的一段，即人们常说的**严格别名规则**（strict aliasing rule）。当前草案用一个新术语 [[g:type-accessible]] 来表述它：

!!! std
    An object of dynamic type Tobj is type-accessible through a glvalue of type Tref if Tref is similar to: Tobj, a type that is the signed or unsigned type corresponding to Tobj, or a char, unsigned char, or std::byte type.

    动态类型为 Tobj 的对象可以通过类型为 Tref 的 glvalue 访问，当且仅当 Tref 与以下之一**相似**：Tobj；Tobj 对应的有符号/无符号类型；`char`、`unsigned char` 或 `std::byte`。

若程序通过一个**不能 type-access** 该对象的 glvalue 去**访问**（[[defns.access]]：读或改）对象的存储值，行为未定义。

逐项理解：

1. **相似类型**（similar，[[conv.qual]]）：去掉各层 cv 限定后相同（数组边界的已知/未知也可以不同）。所以通过 `const int` 左值读 `int` 对象、通过 `int* const*` 读 `int**` 对象都可以。
2. **有符号/无符号对应类型**：`int` 对象可以通过 `unsigned int` glvalue 访问，反之亦然。读出的值由 [[conv.lval#3]] 的"同余值"规则确定（`-1` 读成 `UINT_MAX`）。
3. **`char`、`unsigned char`、`std::byte`**：这三种类型的 glvalue 可以访问**任何**对象——这是 `memcpy`、序列化、哈希等字节级操作合法的基础。注意 **`signed char` 不在此列**：它只能通过第 2 项访问 `unsigned char` 对象或通过第 1 项访问 `signed char` 对象。

这个列表的目的（脚注）就是规定"什么情况下对象可以被别名"。反过来说，**编译器可以假设类型不相容的 glvalue 不指向同一对象**，这就是基于类型的别名分析（TBAA）。

```cpp ub
int f(int* i, float* fp) {
    *i = 1;
    *fp = 2.0f;     // 编译器假设 *fp 不可能是 *i
    return *i;      // 于是直接返回常量 1
}

int g(int* i, unsigned* u) {
    *i = 1;
    *u = 2;         // unsigned 可以别名 int：必须重新读取 *i
    return *i;
}

int main() {
    int x;
    return f(&x, reinterpret_cast<float*>(&x));   // UB：通过 float 左值修改 int 对象
}
```

!!! impl "TBAA 的实际后果"
    在 Apple arm64 上用 Clang `-O2` 编译上例，`f` 被编译为"存 1、存 2.0f、**返回常量 1**"，而 `g` 在第二次存储后**重新从内存加载** `*i`。同一段代码在 `-O0` 下会返回 `0x40000000`——这正是 UB "看起来随优化级别变化"的典型表现。
    
    - GCC 与 Clang 提供 `-fno-strict-aliasing` 关闭这类优化（Linux 内核就这样编译）；GCC 的 `-Wstrict-aliasing` 能发现部分违规。
    - Clang 的 TypeSanitizer（`-fsanitize=type`）是较新的运行时检测工具，在支持的平台上可以捕捉此类违规。

### 正确的类型双关（type punning）方式

```cpp run title="punning.cpp" ok
#include <bit>
#include <cstdio>
#include <cstring>
#include <cstddef>

int main() {
    float f = 1.0f;

    unsigned a = std::bit_cast<unsigned>(f);          // C++20：首选
    unsigned b; std::memcpy(&b, &f, sizeof f);        // 经典做法，编译器会优化成一次移动

    const unsigned char* bytes = reinterpret_cast<const unsigned char*>(&f);
    unsigned char first = bytes[0];                   // OK：unsigned char 可访问任何对象

    int i = -1;
    unsigned u = *reinterpret_cast<unsigned*>(&i);    // OK：对应的无符号类型

    std::printf("%x %x %u %u\n", a, b, first, u);
}
```

!!! pitfall "union 双关在 C++ 中是 UB"
    C 明确允许通过 union 的另一个成员读取（"type punning through union"），C++ **不允许**：读取非活跃成员是读取一个不在生命周期内的对象（[[class.union]]、[[basic.life]]）。GCC 作为扩展保证这种写法的行为，但它不是可移植的 C++。

!!! pitfall "“char 可以别名一切” 只对 char/unsigned char/std::byte 成立"
    `std::uint8_t` 通常是 `unsigned char` 的别名，所以"恰好"可以；但 `std::int8_t`（通常是 `signed char`）不行，`char8_t` 也不行——`char8_t` 是独立类型，C++20 刻意没有给它别名能力，以便编译器优化 UTF-8 字符串处理。

### 类类型与访问：注 11 和 union 复制规则

**访问**只针对标量：只有标量类型的 glvalue 能访问对象（[[defns.access]] 的注释）。类类型对象的"复制"是调用构造函数/赋值运算符，这些调用本身不是访问，但其中会访问标量子对象——这些子访问各自受 ¶11 约束。注 11 对比了 C：C 中可以通过结构体类型的左值整体访问一个结构体对象（如赋值），而 **C++ 中没有"通过类类型左值访问类对象"这一概念**。

由此产生一个漏洞：**union 的默认复制/移动**是按对象表示整体复制的（它不知道哪个成员活跃），其中没有任何标量访问。为此 ¶11 专门加了一句：若以一个**并非指代处于生命周期内的 cv `U` 对象**的 glvalue 实参调用 union `U` 的预置复制/移动构造函数或复制/移动赋值运算符，行为未定义。

```cpp ub
union U { int i; float f; };

void copy_from_raw(void* raw) {
    U u = *static_cast<U*>(raw);   // 若 raw 并不指向一个 U 对象：UB
    (void)u;
}

int main() {
    double d = 0;
    copy_from_raw(&d);
}
```

## 实现视角

!!! impl
    - **值类别在 ABI 层面不存在**：`T&` 与 `T&&` 形参在 Itanium ABI 中都按指针传递，混淆名分别用 `R` 与 `O` 编码（例如 `f(int&&)` 混淆为 `_Z1fOi`）。值类别只影响编译期的重载决议与语义检查。
    - **prvalue 的结果对象与 ABI 的返回槽**：非平凡可复制的类类型按值返回时，Itanium ABI 让调用方传入一块存储的地址（隐式的 sret 指针），被调函数直接在其中构造——这正是"prvalue 的结果对象由上下文提供"的物理实现，C++17 的保证复制消除只是把早已存在的实现方式写进了语义。
    - **TBAA**：Clang 在 LLVM IR 中为每次加载/存储附加 `!tbaa` 元数据（类型树），`char` 系列类型位于树根附近，因此可与一切类型别名。

## 历史与演进

!!! history
    - **C++98/03**：只有 lvalue 与 rvalue 两类。类类型的 rvalue 可以调用成员函数、可以带 cv 限定（与 C 不同，C 的非左值从不带限定），因而早就"有点像对象"。别名规则的列表还包括"包含上述类型成员的聚合或联合类型"和"动态类型的（可能 cv 限定的）基类类型"等项。
    - **C++11**：为了支持右值引用与移动语义，需要一种"有身份但可以被移动"的表达式。[[N3055]]（"A Taxonomy of Expression Value Categories"）引入了 xvalue、glvalue、prvalue，形成今天的三分法。
    - **C++17**：[[P0135R1]] 重新定义 prvalue 为"初始化对象的配方"，引入**结果对象**和**临时量实质化转换**，使复制消除在纯右值初始化同类型对象时成为语言保证。同年 `std::byte`（[[P0298R3]]）加入别名列表。
    - **C++20/23**：[[P1825R0]]（C++20）与 [[P2266R3]]（C++23）扩展并简化了"隐式移动"：C++23 起 `return x;` 中可隐式移动的 `x` 直接就是一个 **xvalue**（¶4.1 中的 move-eligible *id-expression*）。
    - **后续修订**：别名列表中的"聚合/联合"与"基类"项被删去（因为 C++ 中对类对象不存在"访问"）；当前草案用 **type-accessible** 这一术语重新表述，并增加了 union 默认复制的 UB 条款；¶7 的临时量实质化从"期望 glvalue 的操作数"扩大到所有运算符操作数。

## 陷阱 / 常见误解

!!! pitfall "“右值引用类型的变量是右值”"
    错。`void f(std::string&& s)` 中，表达式 `s` 是**左值**（类型是 `std::string`，引用已被 [[expr.type]] 剥去）。要把它继续"作为右值"传下去必须写 `std::move(s)`。值类别是表达式的属性，与变量的声明类型是两回事。

!!! pitfall "“std::move 移动了对象”"
    `std::move` 只是一个到 `T&&` 的 `static_cast`，它产生 xvalue，本身不做任何事。真正"移动"的是随后被重载决议选中的移动构造函数/移动赋值运算符。如果类型没有移动构造函数，或对象是 `const`，`std::move` 之后照样复制。

!!! pitfall "“临时对象” 与 “纯右值” 不是一回事"
    C++17 起 prvalue **不是**对象。`T{}` 本身不创建临时量；只有当它需要一个对象而上下文又不提供时（绑定引用、成员访问、弃值……），才实质化出临时对象。

## 思考题

!!! question "1. 设 `struct A { int m; int& r; static int s; };`，`A make();`。`make().m`、`make().r`、`make().s` 分别是什么值类别？"

<details markdown="1">
<summary>答案</summary>

- `make().m`：**xvalue**。`make()` 被实质化为 xvalue，非引用非静态数据成员的访问结果与对象表达式同类别（[[expr.ref]] ¶8.2）。
- `make().r`：**lvalue**。引用成员的访问结果总是左值（[[expr.ref]] ¶8）：它指代的是引用所绑定的那个对象，与临时量的寿命无关。
- `make().s`：**lvalue**。静态数据成员访问总是左值（¶8.1）。

可以用 `decltype((make().m))` 等验证：分别是 `int&&`、`int&`、`int&`。
</details>

!!! question "2. 下面的函数在 C++20 和 C++23 中分别如何？"

```cpp
int& f(int&& x) { return x; }
```

<details markdown="1">
<summary>答案</summary>

C++20：良构。`x` 是左值，可以绑定到 `int&`。

C++23：**非良构**。[[P2266R3]] 之后，`return x;` 中的 `x` 是可隐式移动的实体，于是 `x` 是 **xvalue**，不能绑定到非 const 左值引用。这是 C++23 的一个有意的破坏性变化：返回右值引用形参的左值引用几乎总是悬垂引用的前兆。
</details>

!!! question "3. 通过 `long` 类型的 glvalue 读取一个 `long long` 对象，在 `long` 与 `long long` 都是 64 位的平台上是否合法？"

<details markdown="1">
<summary>答案</summary>

**UB**。type-accessible 只看类型，不看表示：`long` 与 `long long` 是不同的类型，彼此既不相似，也不是对方对应的有符号/无符号类型。实践中这确实会被 TBAA 利用：在 Clang 中，`long f(long* a, long long* b) { *a = 1; *b = 2; return *a; }` 在 `-O2` 下直接返回常量 1——两次存储带着不同的 `!tbaa` 类型标记。
</details>

## 小结

!!! summary
    | 概念 | 要点 |
    |---|---|
    | 三个基本类别 | lvalue（有身份、不可移动）、xvalue（有身份、可移动）、prvalue（无身份） |
    | prvalue 的本质 | 初始化某个对象的"配方"；**结果对象**由上下文提供 |
    | glvalue → prvalue（¶6） | 左值到右值 / 数组到指针 / 函数到指针；去掉非类 cv；位域被提升 |
    | prvalue → xvalue（¶7） | 作为运算符操作数时实质化为临时对象 |
    | 类型约束（¶9） | prvalue 完整且非抽象（decltype 除外）；glvalue 非 void；只有类/数组 prvalue 带 cv |
    | 可修改左值（¶10） | 非 const、非函数 |
    | 严格别名（¶11） | 只能经相似类型、对应有/无符号类型、`char`/`unsigned char`/`std::byte` 访问 |
