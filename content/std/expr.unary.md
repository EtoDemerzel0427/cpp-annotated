---
title: 一元表达式
summary: 写在操作数前面的运算符：解引用、取地址、一元 + - ! ~、前缀自增自减，以及 sizeof、alignof 和 noexcept 运算符各自要求什么操作数、得到什么结果。
status: draft
covers: expr.unary.general, expr.unary.op, expr.pre.incr, expr.sizeof, expr.alignof, expr.unary.noexcept
related: expr.await, expr.new, expr.delete, expr.reflect, expr.post.incr, expr.context, conv.prom, over.over, except.spec, basic.lval, topics/value-categories
tags: 一元运算符, sizeof, alignof, noexcept, 成员指针, 未求值操作数
updated: 2026-10-19
---

!!! tldr
    - `*p` 要求 `p` 真的指向一个对象或函数，空指针、悬空指针、尾后指针都是 UB；C++ 里 `&*p` 也救不回来。
    - 只有显式写出 `&` 加不带括号的限定名（`&S::m`）才得到成员指针；`&(S::m)`、`&m` 都是普通指针。
    - `+ - ~` 先做整型提升：`-(unsigned short)1` 是 `int` 的 −1，`~(unsigned char)0` 是 `int` 的 −1。无符号取负有定义，有符号溢出是 UB。
    - `sizeof` 和 `noexcept` 的操作数不求值，但 prvalue 操作数仍要实质化成临时量，所以析构函数也要能用。
    - `noexcept(e)` 只看声明的异常规约，回答的是 `e` 会不会抛异常，与会不会出错无关。

一元表达式（*unary-expression*）是第 7 章里种类最杂的一组：除了 `* & + - ! ~` 和前缀 `++ --`，`sizeof`、`alignof`、`noexcept`、`co_await`、`new`、`delete` 和反射运算符 `^^` 在文法上也都是一元表达式。后几种内容较多，各自成页：[[expr.await|co_await]]、[[expr.new|new]]、[[expr.delete|delete]]、[[expr.reflect|^^]]。

下文常用几个概念：**值类别**（左值、prvalue 等，见 [[topics/value-categories]]）、**整型提升**（把比 `int` 窄的整数类型先转成 `int` 或 `unsigned int`，[[g:integral-promotion]]）和**未求值操作数**（只参与类型检查、运行时不执行的操作数，[[g:unevaluated-operand]]）。

## 结合方向与文法 [expr.unary.general]

```cpp ok
int x = 3;
int* p = &x;
int a = - - x;       // -(-x) == 3
int b = *&*p;        // *(&(*p)) == 3
bool c = !~x;        // !(~3) == false
auto d = -(long)x;   // 操作数可以是 C 风格转换
```

¶1 一元运算符从右向左结合。文法里，`* & + - ! ~` 和前缀 `++ --` 的操作数是 *cast-expression*，所以 `-(long)x`、`*(T*)p` 不需要额外的括号。

`sizeof` 不同，它的操作数是 *unary-expression* 或者带括号的类型名。`sizeof (int)x` 不会读成 `sizeof((int)x)`：`sizeof (int)` 先作为对类型求大小匹配完，剩下的 `x` 让整个表达式非良构。

```cpp error
int x = 3;
auto s = sizeof (int)x;   // error: sizeof(int) 之后多出一个 x
```

## 解引用：一元 `*` [expr.unary.op]

¶1 一元 `*` 执行**间接**（indirection，[[g:indirection]]），也就是常说的解引用。操作数必须是指向对象类型或函数类型 `T` 的指针 prvalue，结果是 `T` 类型的左值。

如果指针指向一个对象或函数，结果就指代它；否则行为未定义。空指针、悬空指针、尾后指针都属于不指向对象的情况。唯一的例外是 `typeid(*p)`：`p` 为空且 `*p` 是多态类类型时，抛出 `std::bad_typeid`（[[expr.typeid]]）。

<div class="compare" markdown="1">

```cpp ok
struct Inc;          // 不完整类型
Inc& f(Inc* p) {
  return *p;   // OK：只用来绑定引用
}
```

```cpp run ub
int main() {
  int* p = nullptr;
  int& r = *p;  // UB: p 不指向对象
  (void)r;
}
```

</div>

两个注划出了合法但受限的用法。注 1：对指向生命周期之外的对象的指针做间接本身是合法的，得到的左值只能按 [[basic.life]] 做有限的使用。注 2：对指向不完整类型的指针做间接也合法，结果可以绑定引用、再取地址，但不能读取它的值（不能做左值到右值转换，[[conv.lval]]）。`void*` 不能解引用，因为 `void` 不是对象类型。

!!! lawyer "`&*p` 对空指针是不是 UB？"
    C 语言规定 `&*p` 等价于 `p`，而且 `*` 不求值。C++ 没有这条规则：按 ¶1 的字面意思，`p` 为空时 `*p` 本身就是 UB。允许空左值的提议在 [[CWG232]] 中讨论多年，没有被采纳。所以 C++ 里应写 `p` 或 `std::to_address(p)`。同理，数组 `a` 有 `N` 个元素时，`&a[N]` 就是 `&*(a + N)`，按字面也是经尾后指针做间接；要得到尾后指针，写 `a + N`。

## 取地址：一元 `&` [expr.unary.op]

¶2 `&`、`+`、`-`、`!`、`~` 的结果都是 prvalue。

¶3 `&` 的操作数必须是左值，所以 `&42`、`&f()`（`f` 返回非引用类型）都非良构。对一个 `cv T` 类型的变量取地址得到 `cv T*`，cv 限定保留下来（注 4）。

单个对象可以看作只有一个元素的数组（[[expr.add]]），所以例 1 中 `&a + 1` 是合法的尾后指针，与 `&a` 比较大小也有定义。

### 什么时候得到成员指针（¶3.1、¶4）

```cpp ok
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

在成员函数里，`S::m` 和 `m` 都可以表示当前对象的成员（隐含 `this->`），`&S::m` 因此有两种可能的意思。¶4 规定，只有显式写出 `&`，并且操作数是不带括号的限定名（*qualified-id*，或者 C++26 的 *splice-expression*）时，才形成成员指针。其余写法都按普通表达式处理：

| 写法 | 结果 |
|---|---|
| `&S::m` | 成员指针 `int S::*` |
| `&(S::m)` | 普通指针。成员函数内 `S::m` 等于 `(*this).m`（[[expr.prim.id]]）；类外非良构 |
| `&m` | 普通指针 `&this->m`；对成员函数则非良构 |
| `S::f`（不写 `&`） | 非静态成员函数不会像普通函数那样隐式转换成指针 |

¶3.1 成员指针的类型是 `T C::*`，其中 `C` 是声明该成员的类，不是写在 `::` 前面的类：

```cpp ok
#include <type_traits>
struct A { int i; };
struct B : A { };
static_assert(std::is_same_v<decltype(&B::i), int A::*>);
int B::* pb = &B::i;   // OK：int A::* 隐式转换为 int B::*（[conv.mem]）
```

注 5：`mutable` 数据成员形成的成员指针不带 `mutable` 属性，通过 `const` 对象用 `.*` 访问时结果是 `const` 的。

### 显式对象成员函数（¶3.2）

C++23 的显式对象成员函数（`void g(this S&)`，俗称 deducing this）在调用约定上更像普通函数。取它的地址必须用限定名，结果是普通函数指针，不是成员函数指针：

<div class="compare" markdown="1">

```cpp ok
#include <type_traits>
struct S {
  void g(this S&) {}
  void h() {}
};
static_assert(std::is_same_v<
  decltype(&S::g), void (*)(S&)>);
static_assert(std::is_same_v<
  decltype(&S::h), void (S::*)()>);
```

```cpp error
struct S {
  void g(this S&);
  void f();
};
void S::f() {
  auto x = &g;  // error: 必须写 &S::g
}
```

</div>

### 重载的 `operator&` 与位域（¶5）

类可以重载一元 `&`（[[over.oper]]），所以 `&x` 不一定是 `x` 的地址。需要真实地址的泛型代码要用 `std::addressof`，它绕开用户定义的 `operator&`，也可以在常量求值中使用。

```cpp run ok
#include <memory>
struct Evil { Evil* operator&() const { return nullptr; } };

int main() {
  Evil e;
  Evil* p1 = &e;                  // 调用 Evil::operator&，得到 nullptr
  Evil* p2 = std::addressof(e);   // 真实地址
  return (p1 == nullptr && p2 != nullptr) ? 0 : 1;
}
```

¶5 对不完整类类型的左值用 `&`，而这个类完整后声明了 `operator&`，那么用内建含义还是调用重载是未指定的。原因是编译器处理 `&x` 时还看不到那个重载。

同一段还规定 `&` 的操作数不能是位域：位域不一定从字节边界开始，没有地址可言（[[class.bit]]）。

```cpp error
struct BF { int b : 3; };
void f(BF& x) { auto p = &x.b; }   // error: 不能对位域取地址
```

### 重载集的地址（¶6）

¶6 是一个注：对重载函数名取地址，只能出现在能唯一确定目标函数的语境里，例如初始化一个函数指针（[[over.over]]）。语境既可能选中静态成员函数，也可能选中非静态成员函数，所以同一个 `&M::s` 可能是普通函数指针，也可能是成员函数指针：

```cpp ok
void over(int) {}
void over(double) {}
struct M {
  static void s(int) {}
  void s(double) {}
};
void (*pf)(double) = &over;      // 由目标类型挑出 over(double)
void (*ps)(int) = &M::s;         // 选中静态成员：普通函数指针
void (M::*pm)(double) = &M::s;   // 选中非静态成员：成员函数指针
```

## 算术一元运算符 `+ - ! ~` [expr.unary.op]

### 一元 `+`（¶7）

¶7 操作数必须是算术、无作用域枚举或指针类型的 prvalue，结果就是它的值。整数和枚举操作数先做整型提升，结果类型是提升后的类型。

一元 `+` 看起来什么也不做，实际有两个常见用途。`+c`（`c` 是 `char`）得到 `int`，可以让 `std::cout << +c` 打印数值而不是字符。操作数是类类型时，内建候选 `T* operator+(T*)` 会触发类的转换函数（[[over.built]]），`+[]{ ... }` 就这样把无捕获 lambda 变成函数指针。

```cpp ok
#include <type_traits>
static_assert(std::is_same_v<decltype(+'a'), int>);       // 整型提升
auto fp = +[](int x) { return x * 2; };                   // 闭包 → 函数指针
static_assert(std::is_same_v<decltype(fp), int (*)(int)>);
int arr[3];
static_assert(std::is_same_v<decltype(+arr), int*>);      // 数组先转换为指针
```

有作用域枚举（`enum class`）不在允许之列，`+E::a` 非良构。

### 一元 `-`（¶8）

¶8 操作数必须是算术或无作用域枚举类型的 prvalue，不能是指针。整数操作数先提升。

无符号数取负有定义：结果是 2ⁿ 减去操作数的值，n 是提升后类型的位数（注 8：也就是补码取负）。所以 `-1u == UINT_MAX` 是可移植的写法。

需要注意的是提升。`unsigned short`、`unsigned char` 通常提升为 `int`，取负就成了有符号运算：

```cpp ok
#include <climits>
#include <type_traits>
static_assert(-1u == UINT_MAX);
static_assert(std::is_same_v<decltype(-(unsigned short)1), int>);
static_assert(-(unsigned short)1 == -1);    // 有符号 -1，不是 65535
```

有符号数没有回绕：`-INT_MIN` 的数学结果不能用 `int` 表示，按 [[expr.pre#4]] 是 UB。

```cpp run ub
#include <climits>
int main(int argc, char**) {
  int x = INT_MIN + argc - 1;   // 运行时得到 INT_MIN
  return -x;                    // UB: 结果不能用 int 表示
}
```

本机 Clang 23 加 `-fsanitize=undefined` 运行，UBSan 报告 `negation of -2147483648 cannot be represented in type 'int'`。

无符号类型本来就是模 2ⁿ 算术（[[basic.fundamental]]），取负只是其中一种运算。有符号溢出定为 UB，是为了让优化器可以做代数化简。C++20 规定有符号整数用补码表示，但没有让溢出变得有定义。

### 逻辑非 `!`（¶9）

¶9 `!` 的操作数**按语境转换为 `bool`**（[[g:contextually-converted-to-bool]]），效果相当于 `bool t(e);`，所以 `explicit operator bool` 也能用。结果类型是 `bool`。

```cpp ok
struct Flag { explicit operator bool() const { return true; } };
Flag f;
bool b = !f;     // OK：按语境转换可以用 explicit 转换函数
bool d = !!f;    // 常见的转成 bool 的写法
// bool c = f;   // error: 复制初始化不考虑 explicit 转换函数
```

### 按位取反 `~`（¶10）

¶10 操作数必须是整数或无作用域枚举类型的 prvalue，先做整型提升，结果的每一个二进制位都与操作数相反。整数用补码表示，所以 `~x == -x - 1` 对有符号数也成立，而且不会溢出。

提升同样会带来意外：`~uc`（`uc` 是 `unsigned char`）的类型是 `int`，高位全是 1。

```cpp ok
unsigned char uc = 0x0F;
auto r = ~uc;                                          // int，值为 -16
unsigned char back = static_cast<unsigned char>(~uc);  // 0xF0，需要显式截断
static_assert(~0 == -1);
```

¶10 最后解决了一个文法歧义。`~` 后面跟一个类型名（或 `decltype(x)` 这类 *computed-type-specifier*）时，既可以读成一元 `~`，也可以读成析构函数名的开头。标准规定按运算符处理：

```cpp ok
struct X {
  int operator~() const { return 1; }
  void f() {
    ~X();          // 对临时量 X() 调用 X::operator~，不是析构
    this->~X();    // -> 之后只能是析构函数名
  }
};
```

注 10 解释了为什么 `.`、`->`、`::` 之后没有歧义：文法不允许运算符直接跟在这些记号后面，所以 `p->~X()`、`X::~X` 一定是析构函数名。

## 前缀自增与自减 [expr.pre.incr]

¶1 `++x` 等价于 `x += 1`，`--x` 等价于 `x -= 1`（[[expr.assign]]）。由此可知操作数必须是可修改的左值，结果也是左值。后置 `x++` 的结果则是 prvalue（[[expr.post.incr]]）。

<div class="compare" markdown="1">

```cpp ok
int i = 0;
int& r = ++i;     // 结果是左值
int& s = ++++i;   // ++(++i)，i == 3
double d = 0.5;
double& t = --d;  // 浮点数也可以
```

```cpp error
void f() {
  bool b = false;
  ++b;           // error: 操作数是 bool
  int i = 0;
  int& r = i++;  // error: 后置结果是 prvalue
}
```

</div>

操作数不能是 `cv bool`。C++98 允许 `++b`（效果是置为 `true`），但一开始就标为弃用，C++17 删除了它 {{removed:C++17}}；`--b` 从来都不合法。

操作数是 volatile 类型时，这种用法已弃用（C++20，[[depr.volatile.type]]）。`++v` 看起来是一次操作，实际是一次读和一次写，既不是原子的，也不是一次 volatile 访问。本机 Clang 23 对此默认给出 `-Wdeprecated-volatile` 警告。

## sizeof [expr.sizeof]

### 结果是什么（¶1、¶5）

¶1 `sizeof` 给出操作数类型的一个**非潜在重叠**对象所占的字节数。潜在重叠子对象是基类子对象和 `[[no_unique_address]]` 成员（[[g:potentially-overlapping-subobject]]），它们可以比同类型的完整对象更小，所以要排除在外。

操作数有两种写法：一个表达式，它是未求值操作数；或者一个带括号的类型名。

```cpp ok
int i = 0;
auto n = sizeof(i++);   // i 不会自增：操作数不求值
int runtime_value();
constexpr auto k = sizeof(runtime_value());   // 不调用函数，结果仍是常量
```

¶5 结果是 `std::size_t` 类型的 prvalue，而且是整型常量表达式（注 3）。操作数里的表达式本身不是常量也没关系，因为它根本不求值。Clang 对 `sizeof(i++)` 会警告有副作用的表达式在未求值语境中没有效果。

窄字符类型（`char`、`signed char`、`unsigned char`、`char8_t`，[[g:narrow-character-type]]）的 `sizeof` 是 1。其他基础类型的 `sizeof` 都由实现定义，包括 `bool`、`wchar_t`、`char16_t`、`char32_t`；脚注特别指出 `sizeof(bool)` 不要求是 1。

下面几种情况非良构：操作数具有函数类型或不完整类型，或者是这样的类型名；操作数是指代位域的表达式。

```cpp error
struct Inc;
void f();
struct BF { int b : 3; };
auto a = sizeof(Inc);       // error: 不完整类型
auto b = sizeof(f);         // error: 函数类型（不会退化为指针，见下文）
auto c = sizeof(BF{}.b);    // error: 位域
auto d = sizeof(void);      // error: void 是不完整类型
```

### 引用、类和数组（¶2）

```cpp ok
struct Empty {};
struct Holder { [[no_unique_address]] Empty e; int x; };
static_assert(sizeof(Empty) == 1);             // 完整对象至少 1 字节
static_assert(sizeof(Holder) == sizeof(int));  // e 与 x 重叠（Itanium ABI）
static_assert(sizeof(Holder::e) == 1);         // 子对象：仍报告 Empty 的大小
static_assert(sizeof(int&) == sizeof(int));
static_assert(sizeof(char[10]) == 10);
```

¶2 对引用类型，结果是被引用类型的大小。对一个引用变量 `r`，`sizeof(r)` 也是如此，因为表达式 `r` 的类型本来就不是引用（[[expr.type]]）。

对类，结果包括把对象放进数组所需的尾部填充。空类的 `sizeof` 至少是 1，因为每个完整对象至少占一个字节（[[intro.object]]）。对潜在重叠子对象使用 `sizeof`，得到的是它的类型的大小，不是这个子对象实际占的空间。

对数组，结果是整个数组的字节数，也就是元素个数乘以元素大小，元素之间没有额外填充。

`sizeof(Holder) == sizeof(int)` 依赖实现对 `[[no_unique_address]]` 的处理：Itanium ABI 下成立；MSVC 默认忽略这个属性，要写 `[[msvc::no_unique_address]]`。

### 不做的转换（¶3）

¶3 `sizeof` 的操作数不做左值到右值、数组到指针、函数到指针转换。所以 `sizeof(arr)` 得到整个数组的大小，`sizeof(f)` 非良构，而不是得到函数指针的大小。

!!! pitfall "数组形参的 sizeof"
    函数形参写成 `int a[10]` 时，它的类型在声明处就调整成了 `int*`（[[dcl.fct]]），`sizeof(a)` 得到指针的大小。Clang 对此有 `-Wsizeof-array-argument` 警告。需要保留长度时传引用 `int (&a)[10]`，或者用 `std::span`。

如果操作数是 prvalue，要做**临时量实质化转换**（[[g:temporary-materialization-conversion]]），也就是在概念上创建一个临时对象。临时量从不真正创建，但它的析构函数必须可用：

<div class="compare" markdown="1">

```cpp error
struct D { D(); ~D() = delete; };
D make();
auto s = sizeof(make());
// error: 实质化要求析构函数可用
```

```cpp ok
struct D { D(); ~D() = delete; };
D make();
using T = decltype(make());
// OK：decltype 不做实质化
```

</div>

[[dcl.type.decltype#2]] 明确规定 `decltype` 的 prvalue 操作数不做实质化，`sizeof` 没有这项豁免。

!!! note "`sizeof(int())` 是表达式还是类型"
    C++23 及以前，`sizeof ( type-id )` 中的类型可以是函数类型。按能读成类型就读成类型的规则（[[dcl.ambig.res]]），`sizeof(int())` 是对函数类型 `int()` 求大小，非良构。当前草案把这个位置改成了 *nofun-type-id*（不能是函数类型的类型名，[[g:nofun-type-id]]），于是 `int()` 只能是表达式，`sizeof(int())` 等于 `sizeof(int)`，[[dcl.ambig.res#2]] 的例子也这样标注。这是 C++23 之后的新措辞。截至写作时，Clang 23 仍按旧文法报错 `invalid application of 'sizeof' to a function type`。

### sizeof...（¶4）

¶4 `sizeof...(id)` 中的 `id` 必须是一个包（[[g:pack]]），结果是包中元素的个数（[[temp.variadic]]）。它本身算一次包展开，所以不必再写 `...`。

```cpp ok
#include <cstddef>
template<class... Ts>
constexpr std::size_t count = sizeof...(Ts);
static_assert(count<> == 0);
static_assert(count<int, char, double> == 3);

template<class... Ts>
constexpr std::size_t bytes = (sizeof(Ts) + ... + 0);   // 对比：每个元素求 sizeof 再折叠
static_assert(bytes<char, char> == 2);
```

## alignof [expr.alignof]

```cpp ok
struct alignas(32) V { float f[8]; };
static_assert(alignof(char) == 1);
static_assert(alignof(V) == 32);
static_assert(alignof(V&) == 32);                // 引用 → 被引用类型
static_assert(alignof(V[4]) == 32);              // 数组 → 元素类型
static_assert(alignof(int[]) == alignof(int));   // 未知边界数组也可以
```

¶1 `alignof` 给出操作数类型的对齐要求（[[basic.align]]）。操作数只能是带括号的类型名，表示一个完整对象类型、它的数组，或者指向这两者的引用。¶2 结果是 `std::size_t` 类型的整型常量。¶3 对引用类型，结果是被引用类型的对齐；对数组类型，结果是元素类型的对齐。

与 `sizeof` 不同，标准的 `alignof` 只接受类型，不接受表达式。GCC 和 Clang 把 `alignof(expr)` 作为扩展接受，Clang 在 `-pedantic` 下警告 `'alignof' applied to an expression is a GNU extension`。可移植的写法是 `alignof(decltype(expr))`。`decltype` 对带括号的表达式会得到引用类型，好在 ¶3 让引用的结果与被引用类型相同：

```cpp ok
int x;
static_assert(alignof(decltype(x)) == alignof(decltype((x))));   // int 与 int&
```

```cpp error
struct Inc;
auto a = alignof(Inc);      // error: 不完整类型
auto b = alignof(void());   // error: 函数类型
```

`std::alignment_of_v<T>` 就定义为 `alignof(T)`，两者没有区别。

## noexcept 运算符 [expr.unary.noexcept]

¶1 `noexcept(e)` 的操作数是未求值操作数。与 `sizeof` 一样，prvalue 操作数要做临时量实质化，所以临时量的析构函数也算在内。

¶2 结果是 `bool` 类型的整型常量：操作数所在的完整表达式是**潜在抛出**（potentially-throwing，[[g:potentially-throwing-expression]]）的，结果就是 `false`，否则是 `true`。

[[except.spec#6]] 定义了什么表达式是潜在抛出的：

| 列表项 | 情形 | 例子 |
|---|---|---|
| ¶6.1 | 调用一个异常规约为潜在抛出的函数 | `f()`，`f` 没有声明 `noexcept` |
| ¶6.2 | 隐式调用一个潜在抛出的函数 | 重载运算符、*new-expression* 的分配函数、析构函数 |
| ¶6.3 | *throw-expression* | `throw 1` |
| ¶6.4 | 需要运行时检查、目标是引用的 `dynamic_cast` | `dynamic_cast<D&>(b)` |
| ¶6.5 | `typeid` 作用于多态类指针的内建 `*` | `typeid(*p)` |
| ¶6.6 | 任一求值的直接子表达式潜在抛出 | `g() + f()` |

```cpp ok
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
static_assert(noexcept(f));                       // 只是命名函数，没有调用
static_assert(!noexcept(new int));                // ¶6.2：分配函数可能抛 bad_alloc
static_assert(!noexcept(make()));                 // 临时量的析构函数潜在抛出
static_assert(!noexcept(dynamic_cast<Q&>(*pp)));  // ¶6.4
static_assert(noexcept(dynamic_cast<Q*>(pp)));    // 指针形式失败时返回空，不抛
static_assert(!noexcept(typeid(*pp)));            // ¶6.5
static_assert(noexcept(1 / zero));                // 除零是 UB，不是异常
static_assert(noexcept(sizeof(make())));          // sizeof 的操作数不求值
```

从这个例子能看出几点。判断只看声明：`f` 的函数体即使从不抛出，没写 `noexcept` 结果就是 `false`。完整表达式包括临时量的析构，所以 `make()` 本身是 `noexcept` 的，`noexcept(make())` 仍然是 `false`。UB 不是异常，`noexcept(1 / zero)` 是 `true`。

### 条件 noexcept

`noexcept` 运算符最常出现在异常规约里，写成 `noexcept(noexcept(...))`：外层是说明符，内层是运算符。

```cpp ok
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

`std::vector` 扩容时用 `std::move_if_noexcept` 决定移动还是复制，依据的就是这类判断：移动构造潜在抛出、而类型又可以复制时，退回复制，以保证强异常安全。

!!! pitfall "`noexcept(T(std::move(a)))` 也算析构"
    `T(std::move(a))` 是 prvalue，实质化之后要算上临时量的析构函数。`T` 的析构函数是 `noexcept(false)` 时，即使移动构造函数是 `noexcept` 的，结果也是 `false`。只想检查构造时，可以用 `std::is_nothrow_move_constructible_v<T>`。

## 实现视角

!!! impl "编译器与 ABI"
    - `sizeof`、`alignof`、`noexcept` 都在前端算成常量，不生成代码。`-fno-exceptions` 不改变 `noexcept` 运算符的结果。
    - 基础类型的大小属于 ABI：x86-64 Linux/macOS 上 `long` 是 8 字节，Windows x64 上是 4 字节；`wchar_t` 在 Linux/macOS 上是 4 字节，在 Windows 上是 2 字节。
    - libc++ 和 libstdc++ 的 `std::addressof` 都用编译器内建函数 `__builtin_addressof` 实现，所以既能绕开重载，又能用于常量求值。
    - Itanium ABI 中，数据成员指针是一个偏移量，空值用 −1 表示（偏移 0 是合法值）；成员函数指针占两个字，分别是函数地址（或虚表偏移加 1）和 `this` 调整量。MSVC 按类的继承模型使用不同大小的表示。

## 历史与演进

!!! history
    - C++11 加入了 `alignof`、`noexcept` 运算符和 `sizeof...`，`sizeof` 也可以直接用于非静态数据成员（`sizeof(S::m)`）。
    - C++17 删除了 `bool` 的 `++`；异常规约成为函数类型的一部分，`noexcept(fp())` 因此可以看函数指针的类型判断。
    - C++20 规定整数用补码表示，弃用 volatile 操作数的前缀自增自减。
    - C++23 的显式对象成员函数带来了 ¶3.2 中必须用限定名取地址的规则。
    - C++26 把 *splice-expression* 加入 ¶3.1 和 ¶4，与限定名同等对待 {{c++26}}。

## 常见误解

!!! pitfall "以为 `-u` 一定是无符号运算"
    比 `int` 窄的无符号类型先提升为 `int`。`-(unsigned short)1` 是 `int` 的 −1；`~(unsigned char)0` 是 `int` 的 −1，不是 255。

!!! pitfall "以为 `sizeof` 会求值"
    `sizeof(f())` 不调用 `f`，`sizeof(i++)` 不改变 `i`。所以只声明、没有定义的函数也可以出现在 `sizeof` 里。

!!! pitfall "以为 `noexcept(e)` 能判断会不会出错"
    它只回答会不会抛出异常。UB、`std::terminate`、断言失败都不在考虑范围内。

## 思考题

!!! question "思考题 1"
    在 `struct S { int m; void f(); };` 的成员函数 `S::f` 里，`&S::m`、`&(S::m)`、`&m`、`&this->m` 的类型分别是什么？

<details markdown="1">
<summary>答案</summary>

`&S::m` 是 `int S::*`：显式 `&` 加不带括号的限定名（¶3.1、¶4）。其余三个都是 `int*`：`(S::m)` 带了括号，不形成成员指针，在成员函数里它等于 `(*this).m`（[[expr.prim.id]]）；`&m` 用的是无限定名，注 6 说明它不是成员指针；`&this->m` 本来就是普通的成员访问。
</details>

!!! question "思考题 2"
    `static_assert(noexcept(std::declval<std::string>()));` 能通过吗？

<details markdown="1">
<summary>答案</summary>

能。`std::declval<std::string>()` 返回 `std::string&&`，是 xvalue 而不是 prvalue，不做实质化，也就没有临时量的析构；`declval` 本身声明为 `noexcept`。
</details>

!!! question "思考题 3"
    设 `unsigned short a = 65535;`，`int` 是 32 位。`-a`、`~a`、`a * a` 分别是什么？哪一个有 UB？

<details markdown="1">
<summary>答案</summary>

三者都先把 `a` 提升为 `int` 65535。`-a` 是 `int` −65535；`~a` 是 `int` −65536；`a * a` 是 `int` 乘法 65535 × 65535 = 4294836225，超出 `int` 的范围，是 UB（[[expr.pre#4]]）。
</details>

## 小结

| 运算符 | 操作数 | 结果 | 要点 |
|---|---|---|---|
| `*p` | 指向对象或函数的指针 | `T` 左值 | 不指向对象则 UB |
| `&x` | 左值，非位域 | `T*` 或 `T C::*` | 成员指针只由 `&C::m` 形成；可能被重载 |
| `+x` `-x` `~x` | 算术或整数类型 prvalue | 提升后的类型 | 先做整型提升；无符号取负有定义 |
| `!x` | 按语境转换为 `bool` | `bool` | `explicit operator bool` 可用 |
| `++x` `--x` | 可修改左值，非 `bool` | 左值 | 等价于 `x += 1` |
| `sizeof` | 表达式（不求值）或类型 | `size_t` 常量 | 引用取被引用类型；prvalue 要实质化 |
| `sizeof...` | 包 | `size_t` 常量 | 本身是包展开 |
| `alignof` | 类型 | `size_t` 常量 | 只接受类型 |
| `noexcept(e)` | 表达式（不求值） | `bool` 常量 | 看完整表达式是否潜在抛出 |
