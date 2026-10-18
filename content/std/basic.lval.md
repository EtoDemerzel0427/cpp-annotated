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

**值类别**（value category）是每个表达式除类型之外的第二个静态属性。它回答的问题是：这个表达式是指代一个已经存在的实体（对象、函数等），还是产生一个值去初始化某个东西？如果它指代一个对象，这个对象的资源能不能被转移走？

几乎所有其他条款都依赖这个属性：引用绑定（[[dcl.init.ref]]）、重载决议中的引用绑定排序（[[over.ics.rank]]）、`decltype`（[[dcl.type.decltype]]）、复制消除（[[class.copy.elision]]）、内置运算符对操作数的要求（[[expr.compound]]），以及本节最后一段讲的严格别名规则。

本页逐段释义 [basic.lval]。如何快速判断任意表达式的值类别、完整的对照表和常见误解，见专题 [[topics/value-categories]]。

## 分类法：两个维度，三个基本类别（¶1、¶2）

¶1 用一张图（Figure 2）给出分类：

```text
            expression
           /          \
      glvalue        rvalue
      /     \        /    \
  lvalue     xvalue      prvalue
```

xvalue 同时属于 glvalue 和 rvalue。五个术语的定义如下：

- **glvalue**（泛左值）：其求值确定某个对象、函数、非静态数据成员或直接基类关系的身份（identity）的表达式。
- **prvalue**（纯右值）：其求值初始化一个对象，或计算某个运算符操作数的值（由所在上下文决定是哪一种）的表达式；类型为 cv `void` 的表达式也是 prvalue。
- **xvalue**（亡值）：指代一个资源可以复用的对象（通常因为它的生命周期即将结束）的 glvalue。
- **lvalue**（左值）：不是 xvalue 的 glvalue。
- **rvalue**（右值）：prvalue 或 xvalue。

¶2 每个表达式恰好属于 lvalue、xvalue、prvalue 三者之一，这称为它的值类别。注释提醒，各内置运算符的条款会说明它要求操作数是什么类别、产生什么类别。例如内置赋值要求左操作数是左值、右操作数是纯右值，结果是左值。用户定义的运算符是函数，其类别由参数类型和返回类型决定。

### 直观理解：身份与可移动性

最常用的理解方式，是把这种分类看成两个二值属性的组合：

| | 可被移动（资源可复用） | 不可被移动 |
|---|---|---|
| 有身份（指代一个确定的实体） | xvalue | lvalue |
| 无身份（只是一个值 / 初始化配方） | prvalue | —（不存在） |

- 有身份的是 glvalue；可移动的是 rvalue。
- 无身份且不可移动的格子是空的：一个连身份都没有的东西，自然也没有人在乎它的资源被转移走。

这张 2×2 表正是 C++11 引入 xvalue 时的设计动机（见文末的"历史与演进"）。

!!! note "身份的精确含义"
    确定身份，是指求值结果是一个特定的实体，可以取地址，也可以比较是否是同一个对象。`x`、`*p`、`a[i]`、`std::move(x)` 都确定身份；`42`、`x + 1`、`T{}`（C++17 起）则不确定身份，它们只描述一个值，或者如何初始化一个对象。

    定义里还列出了非静态数据成员与直接基类关系，这是为 C++26 静态反射准备的。拼接表达式 `[: r :]` 可以指代一个非静态数据成员或一个直接基类关系，它是左值（[[expr.prim.splice]]、[[expr.ref]]）。

### ¶3：名字的由来（注释）

lvalue/rvalue 最初得名于能出现在赋值号的左边还是右边（这早已不准确：`const int` 左值不能出现在左边，而 `std::string() = "x"` 的左边是纯右值）。glvalue 是 generalized lvalue 的缩写，prvalue 是 pure rvalue，xvalue 是 eXpiring value。注释特别强调，**这些术语描述的是表达式，不是值**。说"一个右值"，指的总是一个右值表达式。

## 哪些表达式是 xvalue（¶4，注释）

¶4（注释）列出了产生 xvalue 的全部表达式形式：

| 形式 | 例子 | 条款 |
|---|---|---|
| 可隐式移动（move-eligible）的 *id-expression* 或拼接表达式 | `return x;` 中的 `x`（`x` 是局部对象） | [[expr.prim.id.unqual]] |
| 调用返回类型为对象类型的右值引用的函数 | `std::move(x)`、`f()`（`A&& f();`） | [[expr.call]] |
| 转换到对象类型的右值引用 | `static_cast<A&&>(a)`、`(A&&)a` | [[expr.static.cast]] 等 |
| 下标运算，数组操作数是 xvalue | `std::move(arr)[0]` | [[expr.sub]] |
| 类成员访问，对象表达式是 xvalue，成员是非引用的非静态数据成员 | `std::move(a).m`、`f().m` | [[expr.ref]] |
| `.*`，第一操作数是 xvalue，第二操作数是数据成员指针 | `std::move(a).*pm` | [[expr.mptr.oper]] |

用一句话总结（也是注释原话的意思）：**具名的右值引用是左值；无名的、指向对象的右值引用是 xvalue；指向函数的右值引用无论具名与否都是左值。**

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

注意 `make().m`。`make()` 是纯右值，而成员访问要求对象表达式是 glvalue，于是先施行临时量实质化（¶7、[[conv.rval]]），得到一个 xvalue；按 [[expr.ref]] 的规则，xvalue 的成员也是 xvalue。

!!! lawyer "函数的右值引用为何是左值"
    函数没有资源可以转移，也不存在临时的函数。为了让 `void (&&rf)() = f;` 之类的代码与左值引用的行为一致（例如在重载决议和 `decltype` 中），标准规定指代函数的表达式总是左值。可以验证，`decltype((std::move(f)))` 是 `void(&)()`。

## 结果与结果对象（¶5）

¶5 定义了 glvalue 和 prvalue 各自的**结果**（result）：

- glvalue 的结果是它指代的实体。
- prvalue 的结果是它存入其上下文的值；类型为 cv `void` 的 prvalue 没有结果。
- prvalue 的**结果对象**（[[g:result-object]]）是由该 prvalue 初始化的那个对象；cv `void` 的 prvalue 没有结果对象。

注释 4 补充说，除了作为 `decltype` 的操作数之外，对象类型的 prvalue 总有一个结果对象；弃值的 prvalue 会实质化一个临时对象（[[expr.context]]）。

这是 C++17 值类别模型的核心思想：**prvalue 不是对象，而是初始化某个对象的配方**。这个对象由谁提供，取决于 prvalue 出现的上下文：

| 上下文 | 结果对象是 |
|---|---|
| `T x = prvalue;` / `T x(prvalue);` / `T x{prvalue};`（同类型） | 变量 `x` 本身（[[dcl.init.general#15]]） |
| `return prvalue;`（同类型） | 调用方提供的那个对象（返回值的结果对象） |
| 函数实参 `f(prvalue)`（按值形参） | 形参对象 |
| `new T(prvalue)` | 动态分配的对象 |
| 引用绑定 `const T& r = prvalue;` | 实质化出来的临时对象 |
| 成员访问 `prvalue.m`、弃值 `prvalue;` | 实质化出来的临时对象 |
| 内置算术运算的操作数 `1 + 2` | 实质化出来的临时对象（见 ¶7 的讨论） |

于是从 C++17 起，这种情形下的复制消除不再是一种优化，因为根本没有可以复制的东西：

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

在 C++14 下，上例的三处都非良构（即使复制实际被省略，也需要可访问的复制/移动构造函数）。具名返回值的情况仍然不同：`NonMovable x; return x;` 中的 `x` 是一个已经存在的对象，返回时需要移动（或者做 NRVO，但 NRVO 只是允许，并不保证），所以要求可用的移动构造函数，见 [[class.copy.elision]]。

## 何时把 glvalue 变成 prvalue（¶6）

¶6 当一个 glvalue 出现在要求 prvalue 的操作数位置时，自动施行以下三种标准转换之一，把它变成 prvalue：

- 对一般对象，施行左值到右值转换（[[conv.lval]]），即读取它的值；
- 对数组，施行数组到指针转换（[[conv.array]]）；
- 对函数，施行函数到指针转换（[[conv.func]]）。

三个注释各有用意：

- 注 5：把右值引用绑定到左值不属于这种语境。`int&& r = x;` 不会因为需要右值，就对 `x` 做左值到右值转换再实质化一个临时量，而是直接非良构（[[dcl.init.ref]]）。
- 注 6：转换成 prvalue 时，非类类型的 cv 限定被去掉，所以 `const int` 左值可以用在需要 `int` 纯右值的地方。
- 注 7：**不存在纯右值位域**。位域经左值到右值转换后，得到一个位域类型的普通 prvalue，之后可能再经整型提升（[[conv.prom]]）。`unsigned x : 3` 参与运算时提升为 `int`，原因就在这里。

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

¶7 除非另有规定（[[expr.reinterpret.cast]]、[[expr.const.cast]]），每当一个不是由左值到右值转换得来的 prvalue 作为运算符的操作数出现时，就对它施行**临时量实质化转换**（temporary materialization conversion，[[conv.rval]]），把它变成 xvalue。

!!! std
    whenever a prvalue that is not the result of the lvalue-to-rvalue conversion appears as an operand of an operator, the temporary materialization conversion is applied to convert the expression to an xvalue.

    只要不是由左值到右值转换得来的纯右值作为运算符的操作数出现，就对它施行临时量实质化。

这条规则值得仔细读：

- 对 `make().m`、`make().f()`、`std::string("a")[0]` 来说，运算符（`.`、`[]`）需要一个对象，prvalue 就被实质化成临时对象。这是 ¶7 最直观的用途。
- 对 `1 + 2` 来说，按字面理解，`1` 和 `2` 也会先被实质化为临时对象（xvalue）；由于 `+` 要求 prvalue 操作数，再按 ¶6 做左值到右值转换。这样得到的 prvalue 是左值到右值转换的结果，¶7 不再适用，所以不会无限循环。其效果是，运算符读取的每个值都是从某个对象中读出的，[[conv.lval]] 中读取对象的语义可以统一适用于所有操作数。对标量而言这是不可观察的，实现当然不会真的分配存储。
- C++17 的措辞较窄，只有 prvalue 出现在期望 glvalue 的操作数位置时才实质化。当前草案把范围扩大到所有运算符操作数，上面第二点的效果就来自新措辞。

在不属于运算符操作数的地方，prvalue 不会被实质化，例如作为同类型变量的初始化器，或作为 `return` 的操作数。保证复制消除正是由此而来。

## ¶8：指路（注释）

¶8 指向 [[dcl.init.ref]]（引用初始化）和 [[class.temporary]]（临时对象）：左值与右值在这些重要语境中的行为，在那两处描述。

## 类型完整性与 cv 限定（¶9）

¶9 除非另有说明（[[dcl.type.decltype]]），

- prvalue 必须具有完整类型或 void 类型；
- 如果其类型为类类型或类类型的（多维）数组，该类不得是抽象类（[[class.abstract]]）；
- glvalue 不得具有 cv `void` 类型。

注释 9：glvalue 可以具有不完整的非 void 类型（例如 `extern int arr[];` 中的 `arr`，或者 `p` 指向不完整类时的 `*p`）；**类与数组的 prvalue 可以带 cv 限定，其他 prvalue 总是 cv 无限定的**（由 [[expr.type#2]] 把非类 prvalue 的 cv 去掉）。

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

为什么类 prvalue 保留 cv？因为类 prvalue 可以调用成员函数，而 `const` 会影响重载决议：`h().mutate()` 在 `const A` 上调用非 const 成员函数，是非良构的。也正因为如此，返回 `const T` 会阻止移动。`x = h();` 中右操作数是 `const A` 类型的 prvalue，`A::operator=(A&&)` 的形参无法绑定到它，只能退而选择复制赋值。"不要按 const 值返回"这条老建议，在语言层面的原因就在这里。

```cpp error
struct Abstract { virtual void f() = 0; };
Abstract make_abs();          // 声明 OK（C++20 起不再在声明处检查）
void use() { make_abs(); }    // error: prvalue 不得具有抽象类类型
```

!!! impl "Clang 的遗漏"
    截至写作时，Clang 23 接受上例中对 `make_abs()` 的调用（连 `auto&& r = make_abs();` 也接受），没有给出诊断。按 ¶9，这是非良构的；这一调用也无法真正实现，因为没有办法构造一个抽象类的完整对象。

## 可修改的左值（¶10）

¶10 除非左值的类型带 `const` 限定或是函数类型，否则它是**可修改的**（modifiable）。注释指出，通过不可修改的左值或通过右值去修改对象的程序是非良构的（[[expr.assign]]、[[expr.post.incr]]、[[expr.pre.incr]]）。注意这条非良构规则针对的是内置运算符；类类型的赋值是函数调用，不受此限。

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

¶11 是整节在实践中影响最大的一段，也就是人们常说的**严格别名规则**（strict aliasing rule）。当前草案用一个新术语 [[g:type-accessible]] 来表述它：

!!! std
    An object of dynamic type Tobj is type-accessible through a glvalue of type Tref if Tref is similar to: Tobj, a type that is the signed or unsigned type corresponding to Tobj, or a char, unsigned char, or std::byte type.

    动态类型为 Tobj 的对象可以通过类型为 Tref 的 glvalue 访问，当且仅当 Tref 与以下之一**相似**：Tobj；Tobj 对应的有符号/无符号类型；`char`、`unsigned char` 或 `std::byte`。

如果程序通过一个不能 type-access 该对象的 glvalue 去访问（[[defns.access]]：读或改）对象的存储值，行为未定义。

逐项来看：

1. 相似类型（similar，[[conv.qual]]）：去掉各层 cv 限定后相同（数组边界已知与未知也可以不同）。所以通过 `const int` 左值读 `int` 对象、通过 `int* const*` 读 `int**` 对象都是可以的。
2. 对应的有符号/无符号类型：`int` 对象可以通过 `unsigned int` glvalue 访问，反之亦然。读出的值由 [[conv.lval#3]] 的同余值规则确定（`-1` 读成 `UINT_MAX`）。
3. `char`、`unsigned char`、`std::byte`：这三种类型的 glvalue 可以访问任何对象，`memcpy`、序列化、哈希等字节级操作就是以此为基础的。注意 **`signed char` 不在此列**，它只能按第 2 项访问 `unsigned char` 对象，或按第 1 项访问 `signed char` 对象。

脚注说明，这个列表的目的是规定对象在什么情况下可以有别名。反过来说，**编译器可以假设类型不相容的 glvalue 不指向同一对象**，这就是基于类型的别名分析（TBAA）。

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
    在 Apple arm64 上用 Clang `-O2` 编译上例，`f` 被编译为存 1、存 2.0f、然后返回常量 1，而 `g` 在第二次存储后会重新从内存加载 `*i`。同一段代码在 `-O0` 下会返回 `0x40000000`。UB 的表现随优化级别而变，这就是一个典型的例子。
    
    - GCC 与 Clang 提供 `-fno-strict-aliasing` 来关闭这类优化（Linux 内核就是这样编译的）；GCC 的 `-Wstrict-aliasing` 能发现一部分违规。
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
    C 明确允许通过 union 的另一个成员读取（type punning through union），C++ 不允许：读取非活跃成员，就是读取一个不在生命周期内的对象（[[class.union]]、[[basic.life]]）。GCC 作为扩展保证这种写法的行为，但它不是可移植的 C++。

!!! pitfall "char 可以别名一切，只对 char/unsigned char/std::byte 成立"
    `std::uint8_t` 通常是 `unsigned char` 的别名，所以碰巧可以；但 `std::int8_t`（通常是 `signed char`）不行，`char8_t` 也不行。`char8_t` 是独立的类型，C++20 有意没有给它别名能力，以便编译器优化 UTF-8 字符串处理。

### 类类型与访问：注 11 和 union 复制规则

访问只针对标量，只有标量类型的 glvalue 才能访问对象（[[defns.access]] 的注释）。复制类类型的对象，是调用构造函数或赋值运算符，这些调用本身不是访问，但其中会访问标量子对象，这些访问各自受 ¶11 约束。注 11 与 C 作了对比：C 中可以通过结构体类型的左值整体访问一个结构体对象（如赋值），而 **C++ 中没有通过类类型左值访问类对象这一概念**。

这就留下了一个漏洞：union 的默认复制/移动是按对象表示整体复制的（它不知道哪个成员处于活跃状态），其中没有任何标量访问。为此 ¶11 专门加了一句：如果调用 union `U` 的预置复制/移动构造函数或复制/移动赋值运算符时，glvalue 实参并不指代一个处于生命周期内的 cv `U` 对象，行为未定义。

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
    - 值类别在 ABI 层面不存在。`T&` 与 `T&&` 形参在 Itanium ABI 中都按指针传递，混淆名分别用 `R` 与 `O` 编码（例如 `f(int&&)` 混淆为 `_Z1fOi`）。值类别只影响编译期的重载决议与语义检查。
    - prvalue 的结果对象与 ABI 的返回槽：非平凡可复制的类类型按值返回时，Itanium ABI 让调用方传入一块存储的地址（隐式的 sret 指针），被调函数直接在其中构造对象。这正是 prvalue 的结果对象由上下文提供在机器层面的实现；C++17 的保证复制消除，只是把早已存在的实现方式写进了语义。
    - TBAA：Clang 在 LLVM IR 中为每次加载/存储附加 `!tbaa` 元数据（类型树），`char` 系列类型位于树根附近，因此可以与一切类型互为别名。

## 历史与演进

!!! history
    - C++98/03：只有 lvalue 与 rvalue 两类。类类型的 rvalue 可以调用成员函数，可以带 cv 限定（与 C 不同，C 的非左值从不带限定），因而早就有几分像对象。别名规则的列表中还有"包含上述类型成员的聚合或联合类型"和"动态类型的（可能 cv 限定的）基类类型"等项。
    - C++11：为了支持右值引用与移动语义，需要一种有身份、但可以被移动的表达式。[[N3055]]（A Taxonomy of Expression Value Categories）引入了 xvalue、glvalue、prvalue，形成了今天的三分法。
    - C++17：[[P0135R1]] 把 prvalue 重新定义为初始化对象的配方，引入了结果对象和临时量实质化转换，使得用纯右值初始化同类型对象时，复制消除成为语言保证。同年 `std::byte`（[[P0298R3]]）加入了别名列表。
    - C++20/23：[[P1825R0]]（C++20）与 [[P2266R3]]（C++23）扩展并简化了隐式移动。从 C++23 起，`return x;` 中可隐式移动的 `x` 直接就是一个 xvalue（¶4.1 中的 move-eligible *id-expression*）。
    - 后续修订：别名列表中的聚合/联合项与基类项被删去（因为 C++ 中不存在对类对象的访问）；当前草案用 type-accessible 这一术语重新表述，并增加了 union 默认复制的 UB 条款；¶7 的临时量实质化从期望 glvalue 的操作数扩大到所有运算符操作数。

## 陷阱 / 常见误解

!!! pitfall "误解：右值引用类型的变量是右值"
    这是错的。在 `void f(std::string&& s)` 中，表达式 `s` 是**左值**（类型是 `std::string`，引用已被 [[expr.type]] 剥去）。要把它作为右值继续传下去，必须写 `std::move(s)`。值类别是表达式的属性，与变量的声明类型是两回事。

!!! pitfall "误解：std::move 移动了对象"
    `std::move` 只是一个到 `T&&` 的 `static_cast`，它产生 xvalue，本身不做任何事。真正执行移动的，是随后由重载决议选中的移动构造函数或移动赋值运算符。如果类型没有移动构造函数，或者对象是 `const` 的，`std::move` 之后照样会复制。

!!! pitfall "临时对象与纯右值不是一回事"
    从 C++17 起，prvalue 不是对象。`T{}` 本身不创建临时量；只有在需要一个对象而上下文又不提供时（绑定引用、成员访问、弃值等），才实质化出临时对象。

## 思考题

!!! question "1. 设 `struct A { int m; int& r; static int s; };`，`A make();`。`make().m`、`make().r`、`make().s` 分别是什么值类别？"

<details markdown="1">
<summary>答案</summary>

- `make().m` 是 xvalue。`make()` 被实质化为 xvalue，而非引用的非静态数据成员的访问结果与对象表达式同类别（[[expr.ref]] ¶8.2）。
- `make().r` 是 lvalue。引用成员的访问结果总是左值（[[expr.ref]] ¶8），它指代的是引用所绑定的对象，与临时量的寿命无关。
- `make().s` 是 lvalue。静态数据成员的访问结果总是左值（¶8.1）。

可以用 `decltype((make().m))` 等来验证，结果分别是 `int&&`、`int&`、`int&`。
</details>

!!! question "2. 下面的函数在 C++20 和 C++23 中分别如何？"

```cpp
int& f(int&& x) { return x; }
```

<details markdown="1">
<summary>答案</summary>

在 C++20 中良构，`x` 是左值，可以绑定到 `int&`。

在 C++23 中非良构。[[P2266R3]] 之后，`return x;` 中的 `x` 是可隐式移动的实体，于是 `x` 是 xvalue，不能绑定到非 const 左值引用。这是 C++23 有意引入的破坏性变化：返回绑定到右值引用形参的左值引用，几乎总预示着悬垂引用。
</details>

!!! question "3. 通过 `long` 类型的 glvalue 读取一个 `long long` 对象，在 `long` 与 `long long` 都是 64 位的平台上是否合法？"

<details markdown="1">
<summary>答案</summary>

这是 UB。type-accessible 只看类型，不看表示。`long` 与 `long long` 是不同的类型，彼此既不相似，也不是对方对应的有符号/无符号类型。实践中，TBAA 确实会利用这一点：在 Clang 中，`long f(long* a, long long* b) { *a = 1; *b = 2; return *a; }` 在 `-O2` 下直接返回常量 1，因为两次存储带有不同的 `!tbaa` 类型标记。
</details>

## 小结

!!! summary
    | 概念 | 要点 |
    |---|---|
    | 三个基本类别 | lvalue（有身份、不可移动）、xvalue（有身份、可移动）、prvalue（无身份） |
    | prvalue 的本质 | 初始化某个对象的配方；结果对象由上下文提供 |
    | glvalue → prvalue（¶6） | 左值到右值 / 数组到指针 / 函数到指针；去掉非类 cv；位域被提升 |
    | prvalue → xvalue（¶7） | 作为运算符操作数时实质化为临时对象 |
    | 类型约束（¶9） | prvalue 完整且非抽象（decltype 除外）；glvalue 非 void；只有类/数组 prvalue 带 cv |
    | 可修改左值（¶10） | 非 const、非函数 |
    | 严格别名（¶11） | 只能经相似类型、对应有/无符号类型、`char`/`unsigned char`/`std::byte` 访问 |
