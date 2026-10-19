---
title: 值类别
summary: 每个表达式恰好属于 lvalue、xvalue、prvalue 之一；prvalue 的结果对象由语境提供；运算符需要另一种类别时自动插入哪些转换；通过什么类型的 glvalue 可以访问一个对象（严格别名）。
status: done
since: c++11
papers: N3055, P0135R1, P0298R3, P1825R0, P2266R3
related: topics/value-categories, conv.lval, conv.rval, class.temporary, dcl.init.ref, class.copy.elision, dcl.type.decltype, expr.type
tags: 值类别, 对象模型, 严格别名, UB
updated: 2026-10-19
---

!!! tldr
    - 每个表达式恰好属于三种值类别之一：lvalue 指代一个对象或函数，xvalue 指代一个资源可以被拿走的对象，prvalue 不指代对象，只用来初始化对象或算出一个值。
    - 具名的右值引用变量作为表达式是 lvalue；`std::move(x)` 这类无名的右值引用才是 xvalue。
    - prvalue 由语境决定它初始化哪个对象（结果对象），所以 `T x = T();` 只有一个对象，C++17 起不需要复制或移动构造函数。
    - 运算符要 prvalue 而操作数是 glvalue 时，自动读出它的值；要对象而操作数是 prvalue 时，自动实质化一个临时对象。
    - 只能通过相似类型、对应的有/无符号类型、`char`/`unsigned char`/`std::byte` 的 glvalue 访问一个对象，否则是 UB，这就是严格别名规则。

## 三种值类别（¶1–¶3）

```cpp ok
#include <utility>
#include <string>
std::string make();

void demo(std::string s, std::string&& rr) {
    std::string a = s;              // s 是 lvalue：复制
    std::string b = std::move(s);   // std::move(s) 是 xvalue：移动
    std::string c = make();         // make() 是 prvalue：直接初始化 c，不复制也不移动
    std::string d = rr;             // rr 是 lvalue（虽然声明为右值引用）：复制
}
```

同样是用一个 `std::string` 表达式初始化变量，四行的效果各不相同。决定效果的是表达式的**值类别**（value category），它是每个表达式除类型之外的第二个静态属性。

¶1 标准用一张图把表达式分成五类，其中三类是基本类别：

```text
            expression
           /          \
      glvalue        rvalue
      /     \        /    \
  lvalue     xvalue      prvalue
```

- **glvalue**（泛左值）：求值确定一个对象、函数、非静态数据成员或直接基类关系的身份的表达式。确定身份是说，求值结果是一个确定的实体，可以取地址，可以和别的实体比较是不是同一个。
- **prvalue**（纯右值）：求值初始化一个对象，或者算出某个运算符操作数的值的表达式；类型为 cv `void` 的表达式也是 prvalue。
- **xvalue**（亡值）：指代一个资源可以复用的对象的 glvalue，通常因为这个对象快要结束生命周期了。
- **lvalue**（左值）：不是 xvalue 的 glvalue。
- **rvalue**（右值）：prvalue 或 xvalue。

¶2 每个表达式恰好属于 lvalue、xvalue、prvalue 中的一种。各内置运算符的条款说明它要求操作数是什么类别、结果是什么类别，例如内置赋值要求左操作数是 lvalue，结果也是 lvalue。用户定义的运算符是函数，类别由形参和返回类型决定。

可以把三个基本类别看成两个性质的组合：

| | 资源可以被拿走 | 资源不能被拿走 |
|---|---|---|
| 有身份 | xvalue | lvalue |
| 无身份 | prvalue | （不存在） |

有身份的是 glvalue，资源可以拿走的是 rvalue。C++11 引入 xvalue 正是为了填上左上角这一格：移动语义需要一种表达式，它指代一个已经存在的对象，但允许别人拿走它的资源。

¶3 的注释解释了名字的来历：lvalue 和 rvalue 原指能出现在赋值号左边和右边的表达式，这早已不准确（`const int` 变量是 lvalue，却不能被赋值）。glvalue 是 generalized lvalue，prvalue 是 pure rvalue，xvalue 是 eXpiring value。这些术语描述的是表达式，不是值。

!!! note "非静态数据成员和直接基类关系"
    glvalue 定义里的这两项是为 C++26 静态反射加的。拼接表达式 `[: r :]` 在 `r` 反射一个非静态数据成员时是指代该成员的 lvalue（[[expr.prim.splice]]），`obj.[: r :]` 中的 `r` 也可以反射一个直接基类关系，结果指代对应的基类子对象（[[expr.ref]]）。

## 哪些表达式是 xvalue（¶4）

¶4 是一条注释，列出了产生 xvalue 的全部形式：

| 形式 | 例子 |
|---|---|
| 可隐式移动的 *id-expression* 或拼接表达式（[[expr.prim.id.unqual]]） | `return x;` 中的 `x`（`x` 是局部对象） |
| 调用返回对象类型右值引用的函数（[[expr.call]]） | `std::move(x)`，以及 `A&& f();` 的 `f()` |
| 转换到对象类型的右值引用 | `static_cast<A&&>(a)`、`(A&&)a` |
| 数组操作数是 xvalue 的下标运算（[[expr.sub]]） | `std::move(arr)[0]` |
| 对象表达式是 xvalue、成员是非引用的非静态数据成员的成员访问（[[expr.ref]]） | `std::move(a).m`、`f().m` |
| 第一操作数是 xvalue、第二操作数是数据成员指针的 `.*`（[[expr.mptr.oper]]） | `std::move(a).*pm` |

注释最后总结：具名的右值引用是 lvalue；无名的、指向对象的右值引用是 xvalue；指向函数的右值引用不论具名与否都是 lvalue。

```cpp ok
#include <utility>
struct A { int m; };
A&& operator+(A, A);
A&& f();
A make();

void demo(A a) {
    A&& ar = static_cast<A&&>(a);
    // xvalue：f()、f().m、static_cast<A&&>(a)、a + a、std::move(a)、make().m
    // lvalue：ar、a、a.m
    // prvalue：make()
    A b = ar;               // 复制构造：ar 是 lvalue
    A c = std::move(ar);    // 移动构造：std::move(ar) 是 xvalue
    (void)b; (void)c;
}
```

`make().m` 是 xvalue。`make()` 是 prvalue，成员访问需要一个对象，于是先把它实质化为临时对象（见下文），得到 xvalue；xvalue 的非引用成员也是 xvalue。

函数没有可以拿走的资源，也不存在临时的函数，所以指代函数的表达式总是 lvalue。`decltype((std::move(f)))` 是 `void(&)()`，而不是 `void(&&)()`。

## 结果与结果对象（¶5）

¶5 glvalue 的**结果**是它指代的实体。prvalue 的结果是它存入语境的值；prvalue 的**结果对象**（[[g:result-object]]）是由它初始化的那个对象。类型为 cv `void` 的 prvalue 既没有结果，也没有结果对象。

注 4 补充：除了作为 `decltype` 的操作数之外，对象类型的 prvalue 总有结果对象；如果语境没有提供，就实质化一个临时对象。

所以 C++17 起，prvalue 不是对象，而是初始化某个对象的方式。这个对象由语境提供：

| 语境 | 结果对象 |
|---|---|
| `T x = prvalue;`、`T x(prvalue);`、`T x{prvalue};`（同类型） | 变量 `x` 本身（[[dcl.init.general]]） |
| `return prvalue;`（同类型） | 调用方那个函数调用表达式的结果对象 |
| 按值形参的实参 `f(prvalue)` | 形参对象 |
| `new T(prvalue)` | 动态分配的对象 |
| `const T& r = prvalue;`、`prvalue.m`、弃值的 `prvalue;` | 实质化出来的临时对象 |

```cpp run title="no-copy.cpp" ok
struct NonMovable {
    NonMovable() = default;
    NonMovable(const NonMovable&) = delete;
    NonMovable(NonMovable&&) = delete;
};

NonMovable make() { return NonMovable{}; }  // prvalue 直接初始化调用方的对象

int main() {
    NonMovable a = make();                   // a 就是 make() 的结果对象
    NonMovable b = NonMovable(NonMovable()); // 只有一个对象 b
    (void)a; (void)b;
}
```

这段代码里根本没有可以复制的东西，所以复制和移动构造函数被删除也没有关系。C++14 中三处都非良构，因为那时即使复制被省略，也要求复制或移动构造函数可用。

具名对象不同。`NonMovable x; return x;` 中的 `x` 是已经存在的对象，返回时要移动它（NRVO 只是允许，不保证），所以需要可用的移动构造函数，见 [[class.copy.elision]]。

## 运算符需要另一种类别时（¶6、¶7）

### glvalue 变成 prvalue（¶6）

¶6 glvalue 出现在要求 prvalue 的操作数位置时，自动施行下面三种标准转换之一：

- 一般对象：左值到右值转换（[[conv.lval]]），也就是读出它的值；
- 数组：数组到指针转换（[[conv.array]]）；
- 函数：函数到指针转换（[[conv.func]]）。

```cpp ok
struct S { unsigned bits : 3; };
const int ci = 41;

int use(S s) {
    int a = ci + 1;     // ci 是 const int 的 lvalue，读出后是 int 的 prvalue
    auto b = s.bits;    // b 的类型是 unsigned（位域的声明类型）
    auto c = +s.bits;   // c 的类型是 int：读出后又做了整型提升
    return a + b + c;
}
```

¶6 附了三条注释：

- 注 5：把右值引用绑定到 lvalue 不属于这种语境。`int&& r = x;` 不会先读出 `x` 的值再实质化一个临时对象，而是直接非良构（[[dcl.init.ref]]）。
- 注 6：转换成 prvalue 时，非类类型的 cv 限定被去掉，所以 `const int` 的 lvalue 可以用在需要 `int` prvalue 的地方。
- 注 7：不存在 prvalue 位域。位域读出后得到一个位域声明类型的普通 prvalue，之后可能再做整型提升（[[conv.prom]]）。`unsigned bits : 3` 参与运算时提升为 `int`，是因为 `int` 能表示 3 位无符号数的所有值。

### prvalue 变成 xvalue（¶7）

¶7 除了 [[expr.reinterpret.cast]] 和 [[expr.const.cast]] 另有规定的情形，一个 prvalue 作为运算符的操作数出现、而它又不是左值到右值转换的结果时，就对它施行**临时量实质化转换**（[[g:temporary-materialization-conversion]]，[[conv.rval]]），把它变成指代一个临时对象的 xvalue。

```cpp ok
#include <string>
struct P { int m; int get() const { return m; } };
P make();

char first = std::string("abc")[0];   // 实质化 std::string 临时对象，再下标
int  v = make().m + make().get();     // 两个 P 临时对象
```

`.`、`[]` 这类运算符需要一个对象，prvalue 本身不是对象，所以先实质化。prvalue 不作为运算符操作数时不会被实质化，例如作为同类型变量的初始化器或 `return` 的操作数，这正是上一节没有复制的原因。

!!! lawyer "`1 + 2` 也实质化吗"
    按字面读，`1` 和 `2` 都是不由左值到右值转换得来的 prvalue 操作数，所以先实质化为临时对象（xvalue）；`+` 需要 prvalue，再按 ¶6 读出它们的值。读出的结果是左值到右值转换的结果，¶7 不再适用，所以不会循环。这样一来，运算符读到的每个值都来自某个对象。对标量来说这不可观察，实现不会真的分配存储。C++17 的措辞只在操作数位置需要 glvalue 时才实质化，当前草案把范围扩大到了所有运算符操作数。

¶8 是一条注释，指出 lvalue 和 rvalue 在引用初始化（[[dcl.init.ref]]）和临时对象（[[class.temporary]]）中的行为由那两个条款描述。

## 类型的限制（¶9、¶10）

### 完整性与 cv（¶9）

¶9 除了 `decltype` 的操作数（[[dcl.type.decltype]]），prvalue 的类型必须是完整类型或 `void`；如果是类类型或类类型的数组，这个类不能是抽象类（[[class.abstract]]）。glvalue 的类型不能是 cv `void`。

注 9 补充：glvalue 可以有不完整的非 `void` 类型，例如 `extern int arr[];` 中的 `arr`。类和数组的 prvalue 可以带 cv 限定，其他 prvalue 一律不带（[[expr.type#2]]）。

```cpp ok
#include <type_traits>
struct A {};
const A   h();    // h() 是 const A 类型的 prvalue
const int g();    // g() 的类型被调整为 int

static_assert(std::is_same_v<decltype(h()), const A>);
static_assert(std::is_same_v<decltype(g()), int>);

struct Incomplete;
Incomplete make_inc();
using T = decltype(make_inc());   // decltype 的操作数不要求完整类型
```

类 prvalue 保留 cv，是因为它可以调用成员函数，`const` 会影响重载决议。这也带来一个副作用：`x = h();` 的右操作数是 `const A` 的 prvalue，`A::operator=(A&&)` 的形参绑定不了它，只能选复制赋值。所以按 `const` 值返回会妨碍移动。

```cpp error
struct Abstract { virtual void f() = 0; };
Abstract make_abs();          // 只是声明：C++20 起不在这里检查
void use() { make_abs(); }    // error: prvalue 不能是抽象类类型
```

!!! impl "Clang 的遗漏"
    截至写作时，Clang 23 接受上例中对 `make_abs()` 的调用（连 `auto&& r = make_abs();` 也接受），不给诊断。按 ¶9 这是非良构的，这个调用也无法实现，因为抽象类不可能有完整对象。

### 可修改的左值（¶10）

¶10 lvalue 的类型不带 `const` 也不是函数类型时，它是**可修改的**（modifiable）。通过不可修改的 lvalue 或通过 rvalue 修改对象的程序是非良构的（[[expr.assign]]、[[expr.pre.incr]]、[[expr.post.incr]]）。这条限制针对内置运算符，类类型的赋值是函数调用，不受影响。

<div class="compare" markdown="1">

```cpp error
const int c = 0;
int f();
void demo() {
    c = 1;     // error: 不可修改
    f() = 1;   // error: 不是 lvalue
}
```

```cpp ok
#include <string>
void demo() {
    // 调用 std::string::operator=，
    // 作用在临时对象上
    std::string() = "ok";
}
```

</div>

## 严格别名：通过什么类型访问对象（¶11）

```cpp run title="tbaa.cpp" ub
#include <cstdio>
int f(int* i, float* fp) {
    *i = 1;
    *fp = 2.0f;     // 编译器假设 *fp 不可能是 *i
    return *i;      // 于是直接返回常量 1
}

int g(int* i, unsigned* u) {
    *i = 1;
    *u = 2;         // unsigned 可以别名 int：必须重新读 *i
    return *i;
}

int main() {
    int x;
    std::printf("%x\n", f(&x, reinterpret_cast<float*>(&x)));  // UB：通过 float 的 lvalue 修改 int 对象
}
```

本机 Clang 23 在 `-O2` 下把 `f` 编译成两次存储之后直接返回 1，而 `g` 在第二次存储后会重新读 `*i`。这个程序在 `-O0` 下打印 `40000000`（2.0f 的位模式），在 `-O2` 下打印 `1`。编译器这样做的依据是 ¶11。

¶11 先定义一个术语。动态类型为 `Tobj` 的对象可以通过类型为 `Tref` 的 glvalue **类型访问**（[[g:type-accessible]]），如果 `Tref` 与下列类型之一相似：

1. `Tobj` 本身；
2. `Tobj` 对应的有符号或无符号类型；
3. `char`、`unsigned char` 或 `std::byte`。

通过一个不能类型访问该对象的 glvalue 去访问（读或写，[[defns.access]]）对象的存储值，行为未定义。

!!! std
    If a program attempts to access the stored value of an object through a glvalue through which it is not type-accessible, the behavior is undefined.

逐项说明：

1. **相似**（[[g:similar-types|similar]]，[[conv.qual]]）大致是说，把各层 cv 限定都去掉、并忽略数组边界之后两个类型相同。所以通过 `const int` 的 lvalue 读 `int` 对象、通过 `int* const*` 读 `int**` 对象都可以。
2. `int` 对象可以通过 `unsigned int` 的 glvalue 访问，反之亦然。读出的值由 [[conv.lval]] 规定为同余的值，`-1` 读成 `UINT_MAX`。
3. `char`、`unsigned char`、`std::byte` 的 glvalue 可以访问任何对象，`memcpy`、序列化、哈希这类字节级操作靠的就是这一项。`signed char` 不在其中，`char8_t` 也不在。

脚注说明这个列表的目的就是规定对象在什么情况下可以有别名。反过来，编译器可以假设类型不符合这些条件的两个 glvalue 不指向同一个对象，这叫基于类型的别名分析（TBAA）。

### 正确的类型双关

```cpp run title="punning.cpp" ok
#include <bit>
#include <cstdio>
#include <cstring>

int main() {
    float f = 1.0f;

    unsigned a = std::bit_cast<unsigned>(f);          // C++20 起的首选
    unsigned b; std::memcpy(&b, &f, sizeof f);        // 经典做法，编译器会优化成一次移动

    auto* bytes = reinterpret_cast<const unsigned char*>(&f);
    unsigned char first = bytes[0];                   // unsigned char 可以访问任何对象

    int i = -1;
    unsigned u = *reinterpret_cast<unsigned*>(&i);    // 对应的无符号类型

    std::printf("%x %x %u %u\n", a, b, first, u);
}
```

!!! pitfall "通过 union 做类型双关在 C++ 中是 UB"
    C 允许写一个 union 成员再读另一个成员。C++ 不允许：读非活跃成员就是读一个不在生命周期内的对象（[[class.union]]、[[basic.life]]）。GCC 以扩展的形式保证这种写法的行为，但它不是可移植的 C++。

!!! pitfall "`std::int8_t` 和 `char8_t` 不能别名一切"
    `std::uint8_t` 通常是 `unsigned char` 的别名，所以碰巧可以；`std::int8_t` 通常是 `signed char`，不行。`char8_t` 是独立的类型，C++20 有意不给它别名能力，好让编译器优化 UTF-8 字符串处理。

### 类类型与 union 的复制

只有标量类型的 glvalue 才能访问对象（[[defns.access]] 的注释）。复制一个类对象是调用构造函数或赋值运算符，这些调用本身不是访问，其中对标量子对象的读写才是，各自受 ¶11 约束。注 11 对比了 C：C 可以通过结构体类型的 lvalue 整体访问结构体对象，C++ 没有通过类类型 lvalue 访问类对象这个概念。

这留下了一个缺口：union 的预置复制和移动按对象表示整体复制（它不知道哪个成员是活跃的），里面没有任何标量访问。所以 ¶11 最后专门加了一句：调用 union `U` 的预置复制或移动构造函数、复制或移动赋值运算符时，如果实参 glvalue 并不指代一个在生命周期内的 cv `U` 对象，行为未定义。

```cpp ub
union U { int i; float f; };

void copy_from_raw(void* raw) {
    U u = *static_cast<U*>(raw);   // raw 并不指向 U 对象：UB
    (void)u;
}

int main() {
    double d = 0;
    copy_from_raw(&d);
}
```

## 实现视角

!!! impl
    - 值类别在 ABI 层面不存在。`T&` 和 `T&&` 形参在 Itanium ABI 中都按指针传递，只是改编名不同（`f(int&&)` 改编为 `_Z1fOi`，`f(int&)` 为 `_Z1fRi`）。值类别只影响编译期的重载决议和语义检查。
    - 类类型按值返回而不能放进寄存器时，Itanium ABI 让调用方传入一块存储的地址，被调函数直接在里面构造返回值。这就是 prvalue 的结果对象由语境提供在机器层面的样子，C++17 的保证复制消除把这种早已存在的实现方式写进了语义。
    - Clang 在 LLVM IR 的每次加载和存储上附加 `!tbaa` 元数据，`char` 一族位于类型树的根部附近，所以可以和所有类型互为别名。`-fno-strict-aliasing` 关掉这类优化（Linux 内核就这样编译），Clang 的 `-fsanitize=type` 可以在运行时检测一部分违规。

## 历史与演进

!!! history
    - C++98/03 只有 lvalue 和 rvalue 两类。类类型的 rvalue 可以调用成员函数、可以带 cv 限定（C 的非左值从不带限定），已经有几分像对象。
    - C++11 为了右值引用和移动语义，需要一种有身份、资源又可以拿走的表达式。[[N3055]] 引入了 xvalue、glvalue、prvalue，形成今天的分类。
    - C++17 的 [[P0135R1]] 把 prvalue 重新定义为初始化对象的方式，引入结果对象和临时量实质化，用 prvalue 初始化同类型对象时不再有复制。同年 `std::byte` 加入了别名列表（[[P0298R3]]）。
    - C++20 的 [[P1825R0]] 和 C++23 的 [[P2266R3]] 扩大并简化了隐式移动。C++23 起，`return x;` 中可隐式移动的 `x` 本身就是 xvalue。
    - 早期的别名列表还有包含上述类型成员的聚合或 union 类型、对象动态类型的基类类型等项。C++ 中没有对类对象的访问，这些项后来被删去；当前草案用类型访问这个术语重新表述，并加了 union 预置复制的规则。

## 常见误解

!!! pitfall "右值引用类型的变量是右值"
    在 `void f(std::string&& s)` 中，表达式 `s` 是 lvalue，类型是 `std::string`（引用已被 [[expr.type]] 去掉）。要把它继续当右值传下去，必须写 `std::move(s)`。值类别是表达式的属性，和变量的声明类型是两回事。

!!! pitfall "`std::move` 移动了对象"
    `std::move` 只是一个到 `T&&` 的 `static_cast`，产生一个 xvalue，自己什么也不做。真正移动的是随后被重载决议选中的移动构造函数或移动赋值运算符。类型没有移动构造函数，或者对象是 `const` 的，`std::move` 之后照样复制。

!!! pitfall "prvalue 就是临时对象"
    C++17 起 prvalue 不是对象。`T{}` 本身不创建临时对象，只有在需要对象而语境又不提供时（绑定引用、成员访问、弃值等）才实质化出一个。

## 思考题

!!! question "思考题 1"
    设 `struct A { int m; int& r; static int s; };` 和 `A make();`。`make().m`、`make().r`、`make().s` 分别是什么值类别？

<details markdown="1">
<summary>答案</summary>

- `make().m` 是 xvalue：`make()` 实质化为 xvalue，非引用的非静态数据成员与对象表达式同类别（[[expr.ref]]）。
- `make().r` 是 lvalue：引用成员的访问结果总是 lvalue，它指代引用绑定的对象，与临时对象无关。
- `make().s` 是 lvalue：静态数据成员的访问结果总是 lvalue。

`decltype((make().m))` 等分别是 `int&&`、`int&`、`int&`，可以用 `static_assert` 验证。
</details>

!!! question "思考题 2"
    `int& f(int&& x) { return x; }` 在 C++20 和 C++23 中分别是否良构？

<details markdown="1">
<summary>答案</summary>

C++20 中良构：`x` 是 lvalue，可以绑定到 `int&`。

C++23 中非良构。[[P2266R3]] 之后，`return x;` 中的 `x` 可隐式移动，是 xvalue，不能绑定到非 `const` 的左值引用。这是有意的破坏性改动：返回绑定到右值引用形参的左值引用，几乎总会悬垂。
</details>

!!! question "思考题 3"
    在 `long` 和 `long long` 都是 64 位的平台上，通过 `long` 的 glvalue 读一个 `long long` 对象是否合法？

<details markdown="1">
<summary>答案</summary>

是 UB。类型访问只看类型，不看表示。`long` 和 `long long` 是不同的类型，既不相似，也不是对方对应的有符号或无符号类型。编译器确实利用这一点：Clang `-O2` 把 `long f(long* a, long long* b) { *a = 1; *b = 2; return *a; }` 编译成直接返回 1。
</details>
