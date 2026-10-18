---
title: 一元表达式
summary: 一元运算符 * & + - ! ~、前缀自增自减、sizeof / sizeof...、alignof 与 noexcept 运算符的操作数要求、结果类型与值类别；成员指针何时形成、无符号取负、未求值操作数与潜在抛出
status: draft
covers: expr.unary.general, expr.unary.op, expr.pre.incr, expr.sizeof, expr.alignof, expr.unary.noexcept
related: expr.await, expr.new, expr.delete, expr.reflect, expr.post.incr, expr.context, conv.prom, over.over, except.spec, basic.lval, topics/value-categories
tags: 一元运算符, sizeof, alignof, noexcept, 成员指针, 未求值操作数
updated: 2026-10-17
---

[expr.unary] 是第 7 章里运算符种类最杂的一节：它把十几种写在操作数前面的东西归到同一个文法非终结符 *unary-expression* 之下。本页覆盖其中较小的几种运算符：

| 运算符 | 条款 | 本页小节 |
|---|---|---|
| `*` `&` `+` `-` `!` `~` | [expr.unary.op] | 一元运算符 |
| 前缀 `++` `--` | [expr.pre.incr] | 前缀自增与自减 |
| `sizeof`、`sizeof...` | [expr.sizeof] | sizeof |
| `alignof` | [expr.alignof] | alignof |
| `noexcept( )` | [expr.unary.noexcept] | noexcept 运算符 |

内容较多的几种各自成页：[[expr.await|co_await]]、[[expr.new|new]]、[[expr.delete|delete]]、反射运算符 [[expr.reflect|^^]]。

阅读本页之前，最好先熟悉值类别（[[basic.lval]]、[[topics/value-categories]]）、整型提升（[[conv.prom]]）、未求值操作数（[[expr.context]]）和按语境转换为 `bool`（[[conv]]）。

## 文法与结合性（[expr.unary.general] ¶1）

¶1 一元运算符**从右向左**结合：`- - x` 是 `-(-x)`，`*&*p` 是 `*(&(*p))`，`!~x` 是 `!(~x)`。

文法里有两个值得注意的细节：

- 多数一元运算符的操作数是 *cast-expression* 而不是 *unary-expression*。所以 `-(int)x`、`*(T*)p`、`!(bool)v` 可以直接写，`(int)` 这种 C 风格转换与一元运算符处于同一优先级。
- `sizeof` 后接的是 *unary-expression* 而不是 *cast-expression*，所以 `sizeof (int)x` 不会读成 `sizeof((int)x)`：`sizeof (int)` 先匹配了 `sizeof ( nofun-type-id )`，剩下的 `x` 使整个表达式非良构。

```cpp ok
int x = 3;
int* p = &x;
int a = - - x;       // -(-x) == 3
int b = *&*p;        // *(&(*p)) == 3
bool c = !~x;        // !(~3) == false
auto d = -(long)x;   // 操作数是 cast-expression
```

```cpp error
int x = 3;
auto s = sizeof (int)x;   // error: sizeof(int) 之后多出一个 x
```

`sizeof`、`alignof` 与 *new-expression* 的括号形式里出现的是 *nofun-type-id*。这是当前草案对 *type-id* 的一个受限版本，它的 declarator 不能是函数类型（[[dcl.name]]）。这个语法上的区分影响 `sizeof(int())` 的解释，见下文 sizeof 一节。

## 一元运算符（[expr.unary.op]）

### 间接：一元 `*`（¶1）

¶1 一元 `*` 执行**间接**（[[g:indirection]]）。操作数必须是“指向 `T` 的指针”类型的 prvalue，`T` 是对象类型或函数类型；结果是类型为 `T` 的 lvalue。

- 操作数指向对象或函数时，结果就指代那个对象或函数。
- **否则是 UB**。空指针、悬空指针、尾后指针（past-the-end）都属于不指向对象的情况。唯一的例外在 [[expr.typeid]]：在 `typeid(*p)` 中，如果 `p` 为空且 `*p` 是多态类类型，会抛出 `std::bad_typeid`，而不是 UB。

两个注释划出了 `*` 合法但受限的使用范围：

- 注 1：对指向生命周期之外的对象的指针做间接是合法的，所得左值只能按 [[basic.life#8]] 做有限的使用。
- 注 2：对指向不完整类型（`cv void` 除外）的指针做间接也是合法的。所得左值可以用来绑定引用、取地址，但不能做左值到右值转换（[[conv.lval]]）。`void*` 则根本不能解引用，因为 `void` 不是对象类型。

```cpp title="indirection.cpp" ok
struct Inc;                    // 不完整类型
Inc& f(Inc* p) { return *p; }  // OK：*p 是 Inc 类型的左值，只用于绑定引用

int g(int* p) {
    int& r = *p;               // OK：p 必须指向一个 int 对象，否则这里已经是 UB
    return r;
}
```

```cpp title="indirection-ub.cpp" ub
int main() {
    int* p = nullptr;
    int& r = *p;      // UB: p 不指向任何对象（¶1）
    (void)r;
}
```

!!! lawyer "`&*p` 对空指针是不是 UB？"
    C 语言明确规定 `&*p` 等价于 `p`，且不对 `*` 求值。C++ 没有这条规则：按 ¶1 的字面意思，`p` 为空时 `*p` 本身就是 UB，后面的 `&` 也挽救不了。这个问题曾作为核心语言 issue 长期讨论（“空左值”提议），但至今没有被采纳。所以在 C++ 里应写 `p` 或 `std::to_address(p)`，而不是 `&*p`。同理，`&a[N]`（`a` 有 `N` 个元素）在 C++ 中就是 `&*(a + N)`，按字面也是经尾后指针做间接。要得到尾后指针，请写 `a + N`。

### 取地址：一元 `&`（¶3–¶6）

¶3 操作数必须是某类型 `T` 的 lvalue。不能对 prvalue 取地址，`&42`、`&f()`（`f` 返回非引用）都是非良构的。结果分两种：

**¶3.1 成员指针。** 如果操作数是一个指代非静态成员 `m` 的 *qualified-id*（或 *splice-expression*），并且 `m` 不是显式对象成员函数，那么 `m` 必须是某个类 `C`（非匿名联合体）的直接成员，结果类型是“类 `C` 的、类型为 `T` 的成员指针”，即 `T C::*`。

注意 `C` 是声明该成员的那个类，而不是写在 `::` 前面的类：

```cpp title="ptr-to-member-type.cpp" ok
#include <type_traits>
struct A { int i; };
struct B : A { };
static_assert(std::is_same_v<decltype(&B::i), int A::*>);   // 是 A 的成员指针，不是 B 的
int B::* pb = &B::i;   // OK：int A::* 可以隐式转换为 int B::*（[conv.mem]）
```

**¶3.2 普通指针。** 其他情况下，结果类型是“指向 `T` 的指针”，指向被指代的对象或函数。注 4：对类型为 `cv T` 的变量取地址得到 `cv T*`，cv 限定会保留下来。

如果操作数指代一个显式对象成员函数（C++23 的 deducing this，`void f(this S&)`），它必须写成 *qualified-id*（或 splice）。`&S::f` 合法，结果是普通函数指针而不是成员指针；在成员函数里写 `&f` 则是非良构的。

```cpp title="explicit-object-address.cpp" ok
#include <type_traits>
struct S {
    void g(this S&) {}
    void h() {}
};
auto pg = &S::g;   // 显式对象成员函数：普通函数指针
static_assert(std::is_same_v<decltype(pg), void (*)(S&)>);
auto ph = &S::h;   // 隐式对象成员函数：成员函数指针
static_assert(std::is_same_v<decltype(ph), void (S::*)()>);
```

例 1 的后半段提醒了一个容易忽视的事实：单个对象可以当作只有一个元素的数组（[[expr.add]]），所以 `&a + 1` 是合法的尾后指针，`p2 > p1` 有定义。

注 5：由 `mutable` 数据成员形成的成员指针不携带 `mutable` 属性，通过 `const S` 对象用 `.*` 访问时，结果是 `const` 的。

### 成员指针只在显式 `&` 加无括号的限定名时形成（¶4）

¶4 只有显式写出 `&`，并且其操作数是未加括号的 *qualified-id*（或 *splice-expression*）时，才形成成员指针。注 6 把几种反例说得很清楚：

| 写法 | 结果 |
|---|---|
| `&S::m` | 成员指针 `int S::*` |
| `&(S::m)` | **不是**成员指针。在 `S` 的成员函数内，`S::m` 被转换为 `(*this).m`（[[expr.prim.id]]），结果是 `int*`；在类外则非良构 |
| `S::f`（无 `&`，`f` 是非静态成员函数） | 不会像普通函数那样隐式转换成成员函数指针 |
| `&m`（在类作用域内的无限定名） | 不是成员指针；对数据成员就是 `&this->m`，对成员函数则非良构 |

为什么这样规定？因为在成员函数内部，`S::m` 和 `m` 都可以表示当前对象的成员 `m`（隐含 `this->`），于是 `&S::m` 有歧义：是取当前对象成员的地址，还是取成员指针？标准的选择是，**只有最明确的写法 `&S::m` 才形成成员指针**，其他写法一律按普通表达式处理。

```cpp title="paren-member.cpp" ok
struct S {
    int m;
    void f() {
        int S::* pm = &S::m;   // 成员指针
        int* p = &(S::m);      // 普通指针：&this->m
        int* q = &m;           // 普通指针：&this->m
        (void)pm; (void)p; (void)q;
    }
};
```

```cpp title="paren-member-error.cpp" error
struct S { int m; void f(); void g(this S&); };
int* p = &(S::m);              // error: 类外没有 this，S::m 不能作为表达式使用
void S::f() { auto x = &g; }   // error: 显式对象成员函数必须用限定名取地址
```

### `operator&` 重载与 `std::addressof`（¶5）

¶5 有两句话：

1. 如果对一个不完整类类型的左值使用 `&`，而该类型的完整定义声明了 `operator&()`，那么用的是内建含义还是重载，**未指明**（unspecified）。这是对单遍编译的让步：编译器看到 `&x` 时还不知道 `operator&` 是否存在，只能按内建处理；等类完整之后，同样的写法却会调用重载。
2. `&` 的操作数不能是位域。位域不一定从字节边界开始，没有可表示的地址（[[class.bit]]）。

类可以重载一元 `&`（[[over.oper]]），所以 `&x` 不一定是 `x` 的地址。需要真实地址的泛型代码（容器、`std::optional`、分配器）必须用 `std::addressof`，它绕开用户定义的 `operator&`，并且是 `constexpr` 的。

```cpp title="addressof.cpp" run ok
#include <memory>
struct Evil { Evil* operator&() const { return nullptr; } };   // 重载一元 &

int main() {
    Evil e;
    Evil* p1 = &e;                  // 调用 Evil::operator&，得到 nullptr
    Evil* p2 = std::addressof(e);   // 真实地址
    return (p1 == nullptr && p2 != nullptr) ? 0 : 1;
}
```

```cpp title="bit-field-address.cpp" error
struct BF { int b : 3; };
void f(BF& x) { auto p = &x.b; }   // error: 不能对位域取地址（¶5）
```

### 重载集的地址（¶6）

¶6 是一个注：对重载集取地址，只能出现在能唯一确定所指函数的语境里（[[over.over]]），例如初始化一个函数指针、作为函数指针形参的实参、用 `static_cast` 指定目标类型等。由于语境可能选中静态成员函数，也可能选中非静态成员函数，同一个 `&C::f` 可能是函数指针，也可能是成员函数指针。

```cpp title="overload-address.cpp" ok
void over(int) {}
void over(double) {}
struct M {
    static void s(int) {}
    void s(double) {}
};
void (*pf)(double) = &over;      // 由目标类型挑出 over(double)
void (*ps)(int) = &M::s;         // 选中静态成员：普通函数指针
void (M::*pm)(double) = &M::s;   // 选中非静态成员：成员函数指针
// auto bad = &over;             // error: 无法确定是哪个 over
```

### 一元 `+`（¶7）

¶7 操作数必须是算术、无作用域枚举或指针类型的 prvalue，结果是操作数的值。整型或枚举操作数先做整型提升，结果类型是提升后的类型。

一元 `+` 看似无用，实际上是两个常见惯用法的基础：

- 强制提升：`+c`（`c` 是 `char`）得到 `int`，常用于让 `std::cout << +c` 打印数值而不是字符。
- 强制转换为指针：操作数是类类型时，按 [[over.built]]，候选中有 `T* operator+(T*)`，于是会触发类的转换函数。`+[]{...}` 就是这样把无捕获 lambda 变成函数指针的。

```cpp title="unary-plus.cpp" ok
#include <type_traits>
static_assert(std::is_same_v<decltype(+'a'), int>);       // 整型提升
auto fp = +[](int x) { return x * 2; };                   // 闭包 → 函数指针
static_assert(std::is_same_v<decltype(fp), int (*)(int)>);
int arr[3];
static_assert(std::is_same_v<decltype(+arr), int*>);       // 数组到指针转换后的 prvalue
enum class E { a };
// auto e = +E::a;   // error: 有作用域枚举不在允许之列
```

### 一元 `-` 与无符号取负（¶8）

¶8 操作数必须是算术或无作用域枚举类型的 prvalue，不能是指针；整型操作数先提升。

**无符号取负有定义**：结果是 2ⁿ − 值，n 是提升后操作数的位数。注 8 换了一种说法：把操作数和结果都看成无符号数，结果就是补码取负。所以 `-1u == UINT_MAX`，这是完全可移植的写法。

真正的陷阱在于提升：`unsigned short` 和 `unsigned char` 通常提升为 `int`，于是取负成了有符号运算。

```cpp title="unsigned-negate.cpp" ok
#include <climits>
#include <type_traits>
static_assert(-1u == UINT_MAX);                                      // 2^32 - 1
static_assert(-0u == 0u);
static_assert(std::is_same_v<decltype(-(unsigned short)1), int>);    // 先提升为 int
static_assert(-(unsigned short)1 == -1);                             // 有符号 -1，不是 65535
```

有符号整数取负则没有这样的回绕：`-INT_MIN` 的数学结果不能用 `int` 表示，按 [[expr.pre#4]] 是 UB。

```cpp title="negate-int-min.cpp" run ub
#include <climits>
int main(int argc, char**) {
    int x = INT_MIN + argc - 1;   // 运行期得到 INT_MIN
    return -x;                    // UB: 结果不能用 int 表示
}
```

用 `-fsanitize=undefined` 运行时，UBSan 会报告“negation of -2147483648 cannot be represented in type 'int'”。

!!! note "为什么无符号取负有定义，而有符号溢出却是 UB？"
    无符号类型的语义本身就是模 2ⁿ 算术（[[basic.fundamental]]），取负只是这种算术的一部分。有符号溢出定为 UB，是为了让优化器能做代数化简（例如把 `-x < 0` 视作 `x > 0`）。C++20 规定有符号整数采用补码表示，但并没有让溢出变得有定义。

### 逻辑非 `!`（¶9）

¶9 `!` 的操作数**按语境转换为 `bool`**（contextually converted to bool，[[conv]]），相当于直接初始化 `bool t(e);`，所以 `explicit operator bool` 也能用。结果类型为 `bool`，值为转换结果取反。

```cpp title="logical-not.cpp" ok
struct Flag { explicit operator bool() const { return true; } };
Flag f;
bool b = !f;        // OK：按语境转换，explicit 也可以
// bool c = f;      // error: 复制初始化不考虑 explicit 转换函数
bool d = !!f;       // 常见的"转成 bool"写法
```

### 按位取反 `~`（¶10）

¶10 操作数必须是整型或无作用域枚举类型的 prvalue，先做整型提升，结果类型是提升后的类型。结果的每一个二进制位都与操作数相反（注 9：反码）。由于 C++20 起整数采用补码表示（[[basic.fundamental]]），`~x == -x - 1` 对有符号数也成立，而且不会溢出。

同样要警惕提升：`~uc`（`unsigned char`）的类型是 `int`，高位全是 1。

```cpp title="bitwise-not.cpp" ok
unsigned char uc = 0x0F;
auto r = ~uc;                                      // int，值为 -16（0xFFFFFFF0）
unsigned char back = static_cast<unsigned char>(~uc);   // 0xF0，需要显式截断
static_assert(~0 == -1);
```

#### `~X()`：运算符还是析构函数名？

¶10 末尾解决了一个文法歧义：`~` 后面跟一个 *type-name* 或 *computed-type-specifier*（如 `decltype(x)`）时，既可以理解为一元 `~`，也可以理解为析构函数名的开头。标准规定**按运算符处理**。

```cpp title="tilde-ambiguity.cpp" ok
struct X {
    int operator~() const { return 1; }
    void f() {
        ~X();          // 一元 ~ 作用于临时量 X()，调用 X::operator~，不是析构函数调用
        this->~X();    // 在 -> 之后：只能是析构函数名（注 10）
    }
};
```

注 10 解释了为什么 `.`、`->`、`::` 后面没有歧义：文法不允许运算符直接跟在这些记号之后，所以 `p->~X()`、`X::~X` 一定是析构函数名。

## 前缀自增与自减（[expr.pre.incr] ¶1）

¶1 前缀 `++x` 等价于 `x += 1`，`--x` 等价于 `x -= 1`（[[expr.assign]]），因此：

- 操作数必须是可修改的左值，结果也是左值（后置 `x++` 则返回 prvalue，见 [[expr.post.incr]]）；
- 操作数类型不能是 `cv bool`。C++17 起 `++b` 非良构（此前是已弃用的置为 true），`--b` 则从来都是非良构的；
- 操作数是 `volatile` 限定类型时，这种用法**已弃用**（C++20，见 [[depr.volatile.type]]）。理由是 `++v` 看似一次操作，实际上是读、改、写两次访问，并不是原子的，容易误导。

```cpp title="pre-incr.cpp" ok
int i = 0;
int& r = ++i;          // 前缀自增的结果是左值，可以绑定到 int&
int& s = ++++i;        // OK：++(++i)，左值可以连续自增；i == 3
double d = 0.5;
double& t = --d;       // 浮点数同样适用
```

```cpp title="pre-incr-error.cpp" error
void f() {
    bool b = false;
    ++b;                    // error: C++17 起不允许对 bool 自增
    int i = 0;
    int& r = i++;           // error: 后置自增结果是 prvalue
}
```

!!! history "bool 的自增"
    C++98 允许 `++b`（效果是置为 `true`），但在 C++98 中就已将其列为弃用；C++17 正式删除 {{removed:C++17}}。`b--` / `--b` 从一开始就不允许。

## sizeof（[expr.sizeof]）

### 结果：非潜在重叠对象占用的字节数（¶1）

¶1 `sizeof` 给出其操作数类型的一个**非潜在重叠**对象所占的字节数。之所以加上非潜在重叠这个限定，是因为同一类型作为基类子对象或 `[[no_unique_address]]` 成员时可以更小（见 ¶2）。

操作数有两种形式：

- 一个表达式，它是**未求值操作数**（[[expr.context]]）；
- 一个加括号的 *nofun-type-id*。

以下情况是非良构的：

- 表达式具有函数类型或不完整类型，或者括号里是这样的类型；
- 表达式是指代位域的 glvalue。

**窄字符类型**（narrow character types：`char`、`signed char`、`unsigned char` 与 `char8_t`，[[basic.fundamental#7]]）的 `sizeof` 为 1；其他所有基础类型的 `sizeof` 都是**实现定义**的，包括 `bool`（脚注 51：`sizeof(bool)` 不要求为 1）、`wchar_t`、`char16_t`、`char32_t`。

```cpp title="sizeof-basic.cpp" ok
static_assert(sizeof(char) == 1 && sizeof(signed char) == 1 && sizeof(unsigned char) == 1);
static_assert(sizeof(char8_t) == 1);
// sizeof(int)、sizeof(bool)、sizeof(void*) 等：实现定义
int i = 0;
auto n = sizeof(i++);   // i 不会自增：操作数未求值（Clang 会警告"有副作用的表达式在未求值语境中无效果"）
```

```cpp title="sizeof-error.cpp" error
struct Inc;
void f();
struct BF { int b : 3; };
auto a = sizeof(Inc);       // error: 不完整类型
auto b = sizeof(f);         // error: 函数类型（函数名不会退化为指针，见 ¶3）
auto c = sizeof(BF{}.b);    // error: 位域
auto d = sizeof(void);      // error: void 是不完整类型
```

### 引用、类、数组（¶2）

¶2 规定了几种类型的结果：

- 引用类型：结果是被引用类型的大小。`sizeof(int&) == sizeof(int)`；对一个引用变量 `r` 求 `sizeof(r)` 也一样，因为表达式 `r` 的类型本来就不是引用（[[expr.type]]）。想知道引用本身占多少空间，只能间接地看包含引用成员的类有多大。
- 类：结果包括为了把对象放进数组所需的**尾部填充**，填充的数量和位置由实现决定。空类的 `sizeof` 至少为 1，因为 [[intro.object]] 要求每个对象至少占一个字节（潜在重叠子对象除外）。
- 潜在重叠子对象：对这样的子对象应用 `sizeof`，得到的是其类型的大小，而不是该子对象实际占用的大小。脚注解释说，由于虚基类和更宽松的填充要求，子对象实际占用的空间可能更小。
- 数组：结果是整个数组的字节数，即 n × 元素大小，数组元素之间没有额外填充。

```cpp title="sizeof-class.cpp" ok
struct Empty {};
struct Holder { [[no_unique_address]] Empty e; int x; };
static_assert(sizeof(Empty) == 1);            // 完整对象至少 1 字节
static_assert(sizeof(Holder) == sizeof(int)); // e 与 x 重叠（主流 ABI 下）
static_assert(sizeof(Holder::e) == 1);        // 子对象：仍报告类型 Empty 的大小
static_assert(sizeof(int&) == sizeof(int));
static_assert(sizeof(char[10]) == 10);
```

（`sizeof(Holder) == sizeof(int)` 依赖实现对 `[[no_unique_address]]` 的处理。它在 Itanium ABI 下成立；MSVC 默认忽略该属性，需要改用 `[[msvc::no_unique_address]]`。）

### 不做的转换与临时量实质化（¶3）

¶3 `sizeof` 的操作数不做左值到右值、数组到指针、函数到指针转换。正因如此，`sizeof(arr)` 才能得到整个数组的大小，`sizeof(f)` 才是非良构的，而不是得到函数指针的大小。

但如果操作数是 prvalue，就要应用**临时量实质化转换**（[[conv.rval]]）。其效果是，即使临时量从未真正创建，它的析构函数也必须可用（即 [[class.temporary#1]] 所说的仿佛创建并销毁）：

```cpp title="sizeof-materialize.cpp" error
struct D { ~D() = delete; };
auto s = sizeof(D{});   // error: 实质化要求析构函数可用，而它被删除了
```

对比 `decltype(D{})`：[[dcl.type.decltype#2]] 规定，`decltype` 的操作数如果是 prvalue（立即调用除外），不应用实质化，于是 `decltype(D{})` 是良构的，结果为 `D`。`sizeof` 没有这项豁免，它需要的是一个真实存在过的对象的大小。

!!! pitfall "数组形参的 sizeof"
    函数形参写成 `int a[10]` 时，它的类型会调整为 `int*`（[[dcl.fct]]），`sizeof(a)` 得到的是指针的大小。这并不违反 ¶3，因为数组到指针的调整发生在声明处，而不是在 `sizeof` 里。Clang 对此有 `-Wsizeof-array-argument` 警告。需要保留数组大小时，可以传引用 `int (&a)[10]`，或者用 `std::span`。

#### `sizeof(int())`：表达式还是类型？

在 C++23 及以前，`sizeof ( type-id )` 中的 *type-id* 可以是函数类型。按照能解析为 type-id 就解析为 type-id 的规则（[[dcl.ambig.res]]），`sizeof(int())` 被解析成对函数类型 `int()` 求 `sizeof`，因而非良构。当前草案把这个位置改成了 *nofun-type-id*，它根本不能表示函数类型，于是 `int()` 只能是表达式（值初始化的 `int` prvalue），`sizeof(int())` 等于 `sizeof(int)`。[[dcl.ambig.res#2]] 的例 2 明确把 `sizeof(int());` 标为 "expression"。

截至写作时，Clang 23 仍按旧文法处理：`sizeof(int())` 报 “invalid application of 'sizeof' to a function type”。同理，`sizeof(D())`（`D` 是类）在 Clang 中被解析为函数类型而报错，按当前草案它则是一个类类型 prvalue 表达式。

### sizeof...（¶4）

¶4 `sizeof...(id)` 中的 *identifier* 必须命名一个**包**（类型包、值包、模板模板包都可以），结果是包中元素的个数（[[temp.variadic]]）。它本身被视为一个包展开，所以可以出现在需要展开包的语境中，而且不需要再写 `...`。

```cpp title="sizeof-pack.cpp" ok
#include <cstddef>
template<class... Ts>
constexpr std::size_t count = sizeof...(Ts);
static_assert(count<> == 0);
static_assert(count<int, char, double> == 3);

template<auto... Vs>
constexpr std::size_t nvals() { return sizeof...(Vs); }
static_assert(nvals<1, 'a', true>() == 3);

template<class... Ts>
constexpr std::size_t bytes = (sizeof(Ts) + ... + 0);   // 对比：sizeof 作用于每个元素再折叠
static_assert(bytes<char, char> == 2);
```

### 结果类型（¶5）

¶5 `sizeof` 和 `sizeof...` 的结果都是 `std::size_t` 类型的 prvalue。注 3：`sizeof` 表达式是**整型常量表达式**。即便操作数里的表达式本身不是常量表达式也是如此，因为它根本不被求值。

```cpp ok
#include <cstddef>
#include <type_traits>
int runtime_value();
static_assert(std::is_same_v<decltype(sizeof(int)), std::size_t>);
constexpr std::size_t k = sizeof(runtime_value());   // OK：未求值，结果仍是常量
```

## alignof（[expr.alignof]）

¶1 `alignof` 给出其操作数类型的**对齐要求**（[[basic.align]]）。操作数只能是 *nofun-type-id*，表示一个完整对象类型、其数组，或指向这两者的引用。

¶2 结果是 `std::size_t` 类型的 prvalue，是整型常量表达式。

¶3 应用于引用类型时，结果是被引用类型的对齐；应用于数组类型时，结果是元素类型的对齐。

```cpp title="alignof.cpp" ok
struct alignas(32) V { float f[8]; };
static_assert(alignof(char) == 1);
static_assert(alignof(V) == 32);
static_assert(alignof(V&) == 32);       // 引用 → 被引用类型
static_assert(alignof(V[4]) == 32);     // 数组 → 元素类型
static_assert(alignof(int[]) == alignof(int));   // 未知边界数组也可以：元素类型完整即可
```

与 `sizeof` 不同，**标准的 `alignof` 只接受类型，不接受表达式**。GCC 和 Clang 作为扩展支持 `alignof(expr)`，在 `-pedantic` 下 Clang 会警告 “'alignof' applied to an expression is a GNU extension”。可移植的写法是 `alignof(decltype(expr))`。要注意 `decltype` 对带括号的表达式和左值会得到引用类型，好在 ¶3 让引用类型的结果与被引用类型相同。

```cpp title="alignof-expr.cpp" ok
int x;
constexpr auto a1 = alignof(decltype(x));     // 可移植
constexpr auto a2 = alignof(decltype((x)));   // decltype((x)) 是 int&，结果相同
static_assert(a1 == a2);
```

```cpp title="alignof-error.cpp" error
struct Inc;
void f();
auto a = alignof(Inc);      // error: 不完整类型
auto b = alignof(void());   // error: 函数类型不是 nofun-type-id（且不是对象类型）
```

!!! note "alignof 与 std::alignment_of"
    `std::alignment_of_v<T>` 定义为 `alignof(T)`（对引用类型取被引用类型），二者没有区别。C++11 之前没有 `alignof`，常见的替代办法是 GCC 的 `__alignof__`，或者求 `struct { char c; T t; }` 中 `t` 的偏移。

## noexcept 运算符（[expr.unary.noexcept]）

### 操作数未求值（¶1）

¶1 `noexcept(e)` 的操作数是**未求值操作数**。与 `sizeof` 一样，如果操作数是 prvalue，要应用临时量实质化。这一点很关键，因为它把临时量的析构函数也纳入了判断范围。

### 结果：是否潜在抛出（¶2）

¶2 结果是 `bool` 类型的 prvalue（整型常量表达式）：如果操作数的完整表达式是**潜在抛出的**（potentially-throwing，[[except.spec#6]]），结果为 `false`，否则为 `true`。

[[except.spec#6]] 给出了潜在抛出表达式的完整定义。表达式 `E` 潜在抛出，当且仅当：

| 列表项 | 情形 | 例子 |
|---|---|---|
| ¶6.1 | 调用一个异常规约为潜在抛出的函数（经函数或函数指针） | `f()`，`f` 未声明 `noexcept` |
| ¶6.2 | 隐式调用一个潜在抛出的函数 | 重载运算符、*new-expression* 的分配函数、实参的构造函数、析构函数 |
| ¶6.3 | *throw-expression* | `throw 1` |
| ¶6.4 | 需要运行期检查、目标是引用的 `dynamic_cast` | `dynamic_cast<D&>(b)` |
| ¶6.5 | `typeid` 作用于对多态类指针的内建 `*` | `typeid(*p)` |
| ¶6.6 | 任一非未求值的直接子表达式潜在抛出 | `g() + f()` |

几个要点：

- 只看声明，不看函数体。`noexcept(f())` 只检查 `f` 的异常规约；即便 `f` 的函数体从不抛出，只要没写 `noexcept`，结果就是 `false`。
- 完整表达式包括临时量的析构。`make()` 本身是 `noexcept` 的，但如果返回的临时量的析构函数是 `noexcept(false)`，`noexcept(make())` 就为 `false`。
- UB 不是异常。`noexcept(1 / zero)` 是 `true`：除零是 UB，不会抛出异常。
- 名字不等于调用。`noexcept(f)` 只是命名了函数，结果是 `true`。

```cpp title="noexcept-operator.cpp" ok
#include <typeinfo>
void f();
void g() noexcept;
struct T { ~T() noexcept(false); };
T make() noexcept;
struct P { virtual ~P(); };
struct Q : P {};
extern P* pp;
extern int zero;

static_assert(!noexcept(f()));                    // ¶6.1
static_assert(noexcept(g()));
static_assert(noexcept(f));                       // 只是名字，不是调用
static_assert(!noexcept(new int));                // ¶6.2：分配函数可能抛 bad_alloc
static_assert(!noexcept(throw 1));                // ¶6.3
static_assert(!noexcept(make()));                 // 临时量的析构函数潜在抛出
static_assert(!noexcept(dynamic_cast<Q&>(*pp)));  // ¶6.4
static_assert(noexcept(dynamic_cast<Q*>(pp)));    // 指针形式失败时返回空，不抛
static_assert(!noexcept(typeid(*pp)));            // ¶6.5
static_assert(noexcept(1 / zero));                // UB 不是异常
static_assert(noexcept(sizeof(make())));          // sizeof 的操作数未求值，不算子表达式的"抛出"
```

（Clang 对 `new int`、`throw 1`、`dynamic_cast<Q&>(*pp)` 会给出“有副作用的表达式在未求值语境中无效果”的警告，这只是提醒。）

### 典型用途：条件 noexcept

`noexcept` 运算符最常出现在 *noexcept-specifier* 里，形成 `noexcept(noexcept(...))` 这种双重写法：外层是说明符，内层是运算符。

```cpp title="conditional-noexcept.cpp" ok
#include <utility>
template<class T>
void my_swap(T& a, T& b)
    noexcept(noexcept(T(std::move(a))) && noexcept(a = std::move(b)))
{
    T tmp(std::move(a));
    a = std::move(b);
    b = std::move(tmp);
}

struct Throwy { Throwy(Throwy&&); Throwy& operator=(Throwy&&); };
static_assert(noexcept(my_swap(std::declval<int&>(), std::declval<int&>())));
static_assert(!noexcept(my_swap(std::declval<Throwy&>(), std::declval<Throwy&>())));
```

`std::vector` 扩容时用 `std::move_if_noexcept` 决定移动还是复制，这个判断就建立在 `noexcept` 运算符之上：如果移动构造潜在抛出而类型又可复制，就退回复制，以保证强异常安全。

!!! pitfall "`T(std::move(a))` 也包括析构"
    `noexcept(T(std::move(a)))` 中的 `T(...)` 是 prvalue，按 ¶1 实质化后要算上临时量的析构函数。如果 `T` 的析构函数是 `noexcept(false)`，即使移动构造函数是 `noexcept` 的，结果也是 `false`。想单独检查构造，可以改用 `noexcept(::new (p) T(std::move(a)))` 这类不产生临时量的表达式（placement new 的分配函数是 `noexcept` 的），或者直接用类型特征。

## 实现视角

!!! impl "编译器与 ABI"
    - `sizeof`/`alignof` 在前端就折叠为常量，不生成任何代码。`sizeof(bool)`、`sizeof(wchar_t)`、`sizeof(long)` 等属于 ABI 的一部分：Itanium/SysV x86-64 上 `long` 是 8 字节，Windows x64（LLP64）上是 4 字节；`wchar_t` 在 Linux/macOS 上是 4 字节，在 Windows 上是 2 字节。
    - `noexcept` 运算符完全在编译期计算，依据是声明中的异常规约。`-fno-exceptions` 并不改变它的结果，规约仍然按声明计算。
    - `operator&` 与 `std::addressof`：libc++ 和 libstdc++ 的 `addressof` 都实现为编译器内建函数 `__builtin_addressof`，因此既能绕开重载，又能用于常量求值。
    - 成员指针的表示（Itanium ABI）：数据成员指针是一个 `ptrdiff_t` 偏移，空值用 −1 表示（因为偏移 0 是合法的）；成员函数指针占两个字宽，分别是函数地址或虚表偏移 +1，以及 `this` 调整量。MSVC 根据类的继承模型使用不同大小的表示。
    - 前缀 `++` 对 `volatile` 的弃用警告：Clang 中是 `-Wdeprecated-volatile`（C++20 起默认开启）。

## 历史与演进

!!! history "C++98 → 当前草案"
    - **C++11**：新增 `alignof`、`noexcept` 运算符、`sizeof...`；`sizeof` 可以用于非静态数据成员而无需对象（`sizeof(S::m)`，[[expr.prim.id]]）。
    - **C++17**：删除 `bool` 的 `++`；异常规约成为函数类型的一部分，影响 `noexcept(fp())` 对函数指针调用的判断。
    - **C++20**：整数统一采用补码表示，`~` 与 `-` 对有符号数的语义描述随之简化；对 `volatile` 操作数的前缀自增自减被弃用。
    - **C++23**：显式对象成员函数引入 ¶3.2 中必须用限定名取地址的规则。
    - **C++26**：*splice-expression* 加入 ¶3.1 和 ¶4，与 *qualified-id* 同等对待 {{c++26}}；*reflect-expression* 加入 *unary-expression*。
    - **当前草案**：引入 *nofun-type-id*，`sizeof(int())` 由非良构的函数类型变为表达式。

## 陷阱

!!! pitfall "以为 `-u` 一定是无符号运算"
    `unsigned short`、`unsigned char`、`char16_t` 等窄于 `int` 的无符号类型会先提升为 `int`。`-(unsigned short)1` 是 `int` 的 `-1`；`~(unsigned char)0` 是 `int` 的 `-1`，不是 255。

!!! pitfall "用 `&x` 取泛型对象的地址"
    类可以重载一元 `&`，模板代码里应使用 `std::addressof(x)`。

!!! pitfall "以为 `sizeof` 会求值"
    `sizeof(f())` 不调用 `f`，`sizeof(i++)` 不改变 `i`。也正因如此，只声明而未定义的函数可以出现在 `sizeof` 中。

!!! pitfall "`noexcept(expr)` 回答的是会不会抛出，而不是会不会出错"
    UB、`std::terminate`、断言失败都不在它的考虑范围内。它只看异常规约和少数几种内建的会抛出的构造。

## 思考题

!!! question "思考题 1"
    在 `struct S { int m; void f(); };` 的成员函数 `S::f` 里，`&S::m`、`&(S::m)`、`&m`、`&this->m` 的类型分别是什么？

<details markdown="1">
<summary>答案</summary>

`&S::m` 是 `int S::*`（¶3.1，¶4：显式 `&` 加无括号的 qualified-id）。其余三个都是 `int*`：`(S::m)` 加了括号，不形成成员指针，`S::m` 在成员函数中变换为 `(*this).m`（[[expr.prim.id]]）；`&m` 用的是无限定名，注 6 明确它不是成员指针；`&this->m` 显然是普通指针。
</details>

!!! question "思考题 2"
    `static_assert(noexcept(std::declval<std::string>()));` 能通过吗？

<details markdown="1">
<summary>答案</summary>

能。`std::declval<std::string>()` 返回 `std::string&&`，是 xvalue 而不是 prvalue，不触发临时量实质化，也就没有临时量的析构；`declval` 本身声明为 `noexcept`。再看 `noexcept(std::string())`：这是 prvalue，实质化后要算上 `~basic_string()`（隐式 `noexcept`）和默认构造函数（标准库将其声明为 `noexcept(noexcept(Allocator()))`，对 `std::allocator` 为 `true`），所以结果也是 `true`。
</details>

!!! question "思考题 3"
    设 `unsigned short a = 65535;`。`-a`、`~a`、`a * a` 在 32 位 `int` 的平台上分别是什么？哪一个有 UB？

<details markdown="1">
<summary>答案</summary>

三者都先把 `a` 提升为 `int` 65535。`-a` 是 `int` −65535；`~a` 是 `int` −65536（即 `0xFFFF0000`）；`a * a` 是 `int` 乘法 65535 × 65535 = 4294836225，超出了 `int` 的范围，**是 UB**（[[expr.pre#4]]）。这是无符号短类型提升为有符号 `int` 最著名的后果。
</details>

## 小结

| 运算符 | 操作数要求 | 结果 | 要点 |
|---|---|---|---|
| `*p` | 指向对象/函数类型的指针 prvalue | `T` 左值 | 不指向对象则 UB（`typeid` 例外） |
| `&x` | 左值；非位域 | `T*` 或 `T C::*` | 成员指针只由 `&C::m`（无括号）形成；可被重载，用 `addressof` |
| `+x` | 算术、无作用域枚举、指针 | 提升后的值 | 强制提升；`+lambda` 转函数指针 |
| `-x` | 算术、无作用域枚举 | 提升后的类型 | 无符号：2ⁿ − x；有符号溢出 UB |
| `!x` | 按语境转换为 `bool` | `bool` | `explicit operator bool` 可用 |
| `~x` | 整型、无作用域枚举 | 提升后的类型 | `~X()` 当作运算符 |
| `++x` `--x` | 可修改左值，非 `bool` | 左值 | ≡ `x += 1`；`volatile` 已弃用 |
| `sizeof` | 表达式（未求值）或 nofun-type-id；非函数、非不完整、非位域 | `size_t` 常量 | 引用→被引用类型；类含尾部填充；prvalue 要实质化 |
| `sizeof...` | 包名 | `size_t` 常量 | 本身是包展开 |
| `alignof` | 完整对象类型/数组/引用 | `size_t` 常量 | 只接受类型；数组→元素对齐 |
| `noexcept(e)` | 表达式（未求值） | `bool` 常量 | 看完整表达式是否潜在抛出，含临时量析构 |
