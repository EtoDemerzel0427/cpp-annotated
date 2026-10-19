---
title: 名字修饰（Itanium C++ ABI）
summary: GCC 和 Clang 怎样把 C++ 函数、变量、模板特化编码成链接器能比较的符号名，以及这种编码与标准里签名的对应关系。
group: 工具链
status: draft
order: 25
related: intro.defs, dcl.link, basic.link, over.load, temp.over.link, dcl.fct, expr.prim.lambda.closure, module.unit, toolchain/linking-and-symbols, toolchain/object-layout-and-vtables
tags: 工具链, ABI, Itanium, 名字修饰, 链接
updated: 2026-10-19
---

!!! tldr
    - 修饰名编码的是标准定义的签名：名字、所属作用域、形参类型列表；成员函数再加 cv 与引用限定，函数模板特化再加返回类型、模板实参和约束。
    - 非模板函数的返回类型和变量的类型不进修饰名，所以这两类不一致链接器发现不了。
    - Itanium 方案的骨架是 `_Z` + 名字 + 形参类型，嵌套名写在 `N…E` 里，重复出现的部分用 `S_`、`S0_` 等替换引用。
    - lambda、局部静态变量、无名命名空间、模块附属实体都有专门的编码，目的是让同一个实体在每个翻译单元里得到同一个名字。
    - `extern "C"` 的实体不修饰，命名空间和形参类型都被丢掉；MSVC 用另一套方案，还编码返回类型、调用约定和访问控制。

链接器只认字符串。C++ 却允许同名函数重载，允许同名实体分属不同的命名空间和类，模板还能生成无数个同名特化。这些同名的不同实体必须变成不同的字符串，而同一个实体在不同翻译单元（TU）中又必须变成相同的字符串。把 C++ 实体编码成符号名的规则叫做**名字修饰**（name mangling）。

标准没有规定修饰方案，但规定了修饰所依据的东西：**签名**（signature）。[[defns.signature]] 的注释说，签名是名字修饰和链接的基础。按 [[defns.signature]]、[[defns.signature.member]] 和 [[defns.signature.templ]]：

| 实体 | 签名包含 |
|---|---|
| 函数 | 名字、形参类型列表、所在命名空间 |
| 成员函数 | 名字、形参类型列表、所属类、cv 限定、引用限定、尾随 requires 子句 |
| 函数模板 | 名字、形参类型列表、所在命名空间、返回类型、模板头、尾随 requires 子句 |

签名里有的，修饰名里就有；签名里没有的，比如非模板函数的返回类型，修饰名里通常也没有。[[toolchain/linking-and-symbols]] 演示了这带来的后果。

本页讲 GCC 和 Clang 在 Windows 以外几乎所有平台上使用的 Itanium C++ ABI 方案。例子都用本机 Clang 23 以 `clang++ -std=c++2c --target=x86_64-linux-gnu -c` 编译，用 `llvm-nm` 列符号、`llvm-cxxfilt` 反修饰。macOS 的 Mach-O 符号在此基础上多一个前导下划线（`_Z3apiv` 变成 `__Z3apiv`），其余相同。

## 骨架：`_Z` + 名字 + 形参类型

```cpp
void f() {}
void f(int) {}
void f(int, double, char) {}
```

```text
_Z1fv                                    f()
_Z1fi                                    f(int)
_Z1fidc                                  f(int, double, char)
```

把 `_Z1fidc` 拆开：

| 片段 | 含义 |
|---|---|
| `_Z` | 表示这是修饰过的 C++ 名字。以 `_Z` 开头的标识符是保留给实现的（[[lex.name]]），不会与用户名字冲突 |
| `1f` | 源名字（source-name）：长度加标识符 |
| `idc` | 形参类型：`int`、`double`、`char` |

没有形参时写 `v`（void）。非模板函数的返回类型不编码：重载决议不看返回类型（[[over.load]]），签名里也没有它。

### 内建类型代码

```text
_Z1fmxbfwDuDsDi       f(unsigned long, long long, bool, float, wchar_t, char8_t, char16_t, char32_t)
_Z1fahstjeDn          f(signed char, unsigned char, short, unsigned short, unsigned int, long double, std::nullptr_t)
_Z1fiz                f(int, ...)
```

| 代码 | 类型 | 代码 | 类型 | 代码 | 类型 |
|---|---|---|---|---|---|
| `v` | void | `c` | char | `a` | signed char |
| `h` | unsigned char | `s` | short | `t` | unsigned short |
| `i` | int | `j` | unsigned int | `l` | long |
| `m` | unsigned long | `x` | long long | `y` | unsigned long long |
| `b` | bool | `w` | wchar_t | `f` | float |
| `d` | double | `e` | long double | `z` | `...` |
| `Du` | char8_t | `Ds` | char16_t | `Di` | char32_t |
| `Dn` | `std::nullptr_t` | `Da` | `auto` | `Dc` | `decltype(auto)` |

`char`、`signed char`、`unsigned char` 是三个不同的类型（[[basic.fundamental]]），所以有三个不同的代码。`int` 和 `long` 即使在某个平台上大小相同，也是不同的代码。

### 复合类型

```cpp
void f(int*, const int*, int&, const int&, int&&, volatile int*) {}
void f(int[3], int (*)[3], int (&)[4]) {}
void f(void (*)(int), int (*)(double, char)) {}
```

```text
_Z1fPiPKiRiRS0_OiPVi                     f(int*, int const*, int&, int const&, int&&, int volatile*)
_Z1fPiPA3_iRA4_i                         f(int*, int (*) [3], int (&) [4])
_Z1fPFviEPFidcE                          f(void (*)(int), int (*)(double, char))
```

| 代码 | 含义 |
|---|---|
| `P` | 指针 |
| `R` / `O` | 左值引用 / 右值引用 |
| `K` / `V` / `r` | const / volatile / restrict，写在被修饰的类型之前：`PKi` 是指向 `const int` 的指针 |
| `A3_i` | `int[3]` |
| `F…E` | 函数类型：返回类型加形参类型 |
| `M<类><成员类型>` | 成员指针 |

第二个函数的第一个形参在源码里写的是 `int[3]`，修饰名却是 `Pi`。这是因为形参类型列表是在调整之后确定的（[[dcl.fct]]）：数组形参调整为指针，函数形参调整为函数指针，顶层 cv 限定被丢弃。所以下面两对声明各自是同一个函数：

```cpp error
void f(int[3]) {}
void f(int*) {}         // error: redefinition of 'f'
void g(const int) {}
void g(int) {}          // error: redefinition of 'g'
```

`int (*)[3]`（`PA3_i`）中的数组边界不会被调整，它是指针所指类型的一部分。

### 替换：`S_`、`S0_`、`S1_`

修饰名很容易变长，所以 ABI 规定：已经出现过的组件（带限定的名字、复合类型、模板参数等，但不包括内建类型）按出现顺序编号，再次出现时用**替换**（substitution）引用。第一个是 `S_`，第二个是 `S0_`，然后是 `S1_`，序号是 36 进制（数字加大写字母）。

在 `_Z1fPiPKiRiRS0_OiPVi` 中：

| 编号 | 组件 |
|---|---|
| `S_` | `Pi`（`int*`） |
| `S0_` | `Ki`（`const int`） |
| `S1_` | `PKi` |
| `S2_` | `Ri` |

所以第四个形参 `const int&` 写成 `RS0_`，而不是 `RKi`。命名空间也是组件：

```text
_ZN2ns5inner1hENS0_3TagES1_              ns::inner::h(ns::inner::Tag, ns::inner::Tag)
```

这里 `S_` 是 `ns`，`S0_` 是 `ns::inner`。`NS0_3TagE` 就是 `ns::inner::Tag`，它成为 `S1_`，第二个形参直接写 `S1_`。

## 命名空间与类：嵌套名 `N…E`

```cpp
namespace ns { void g(int) {} int var; }
struct S { static int count; };
int S::count;
int ns_var;
```

```text
_ZN2ns1gEi                         ns::g(int)
_ZN2ns3varE                        ns::var
_ZN1S5countE                       S::count
ns_var                             ns_var
```

`N` 与 `E` 之间是从外到内的各级名字。后三行是变量：命名空间或类中的变量只编码限定名，不编码类型。全局命名空间中的变量 `ns_var` 完全不修饰，与 C 的变量同名。[[dcl.link#7]] 规定 C 语言链接的变量与全局作用域中同名的变量是同一个实体，靠的就是这一点。

### 成员函数的 cv 与引用限定

```cpp
struct S {
    void m() {}
    void m() const {}
    void m() volatile {}
    void r() & {}
    void r() && {}
    static void s() {}
};
```

```text
_ZN1S1mEv                          S::m()
_ZNK1S1mEv                         S::m() const
_ZNV1S1mEv                         S::m() volatile
_ZNR1S1rEv                         S::r() &
_ZNO1S1rEv                         S::r() &&
_ZN1S1sEv                          S::s()
```

成员函数的 cv 限定和引用限定紧跟在 `N` 之后（`NK`、`NV`、`NR`、`NO`），对应成员函数签名中的这两项。静态成员函数 `s()` 的修饰名与形参相同的非静态、非 const 成员函数一样，因为两者本来就不能互相重载（[[over.load]]）。

### 运算符与转换函数

```text
_ZN1SaSERKS_                       S::operator=(S const&)
_ZNK1SeqERKS_                      S::operator==(S const&) const
_ZN1SixEi                          S::operator[](int)
_ZNK1ScviEv                        S::operator int() const
_ZN1SclEv                          S::operator()()
```

运算符用两个小写字母编码：`aS` 是 `=`，`eq` 是 `==`，`ix` 是 `[]`，`cl` 是 `()`，`cv` 是转换函数（后面跟目标类型），此外还有 `nw`（new）、`pl`（+）、`gt`（>）、`st`（sizeof 类型）等。`RKS_` 里的 `S_` 是类 `S` 本身，它是第一个出现的组件。

### 构造函数与析构函数的变体

构造函数和析构函数没有可用的名字，修饰时用 `C` 或 `D` 加一个数字表示。一个构造函数会生成不止一个符号：

```cpp
struct T { T(); ~T(); virtual void v(); };
T::T() {} T::~T() {} void T::v() {}
```

```text
$ llvm-nm ctor.o
0000000000000060 T _ZN1TC1Ev
0000000000000060 T _ZN1TC2Ev
0000000000000080 T _ZN1TD1Ev
0000000000000080 T _ZN1TD2Ev
...
```

| 代码 | 含义 |
|---|---|
| `C1` | **完整对象构造函数**（complete object constructor）：构造整个对象，包括虚基类 |
| `C2` | **基类子对象构造函数**（base object constructor）：本类作为别的类的基类被构造时使用，不构造虚基类 |
| `D0` | **删除析构函数**（deleting destructor）：析构后调用 `operator delete`，`delete p` 通过 vtable 调用它 |
| `D1` | 完整对象析构函数 |
| `D2` | 基类子对象析构函数 |

区分 C1 和 C2 是为了虚基类：虚基类只能由最派生类构造一次（[[class.base.init]]）。没有虚基类时两者的代码完全一样，所以上面 `C1` 和 `C2` 地址相同，Clang 在 Linux 目标下默认让 C1 成为 C2 的别名。`D0` 只在析构函数是虚函数时才生成，`T` 的析构函数不是虚函数，所以没有它。VTT 怎样借助 C2 传递构造期间的 vtable，见 [[toolchain/object-layout-and-vtables]]。

## 模板

```cpp
template <class T> T twice(T x) { return x + x; }
template <class T> void ignore(T) {}
template <class T, int N> struct Arr { T data[N]; void fill(T) {} };
template <class... Ts> void pack(Ts...) {}
template <auto V> void val() {}
template <class T> auto deduced(T x) { return x; }
template <class T> struct Outer { template <class U> static void mem(T, U) {} };
template <class T> void cond(T) requires (sizeof(T) > 1) {}
```

```text
_Z5twiceIiET_S0_                     int twice<int>(int)
_Z5twiceIdET_S0_                     double twice<double>(double)
_Z6ignoreIiEvT_                      void ignore<int>(int)
_Z6ignoreIPKcEvT_                    void ignore<char const*>(char const*)
_ZN3ArrIcLi16EE4fillEc               Arr<char, 16>::fill(char)
_Z4packIJidcEEvDpT_                  void pack<int, double, char>(int, double, char)
_Z4packIJEEvDpT_                     void pack<>()
_Z3valITnDaLi42EEvv                  void val<42>()
_Z3valITnDaLc97EEvv                  void val<(char)97>()
_Z3valITnDaLb1EEvv                   void val<true>()
_Z7deducedIlEDaT_                    auto deduced<long>(long)
_ZN5OuterIiE3memIfEEviT_             void Outer<int>::mem<float>(int, float)
_Z4condIiEvT_QgtstS0_Li1E            void cond<int>(int) requires (sizeof (int) > 1)
```

### 模板实参

模板实参写在 `I…E` 之间：`IiE` 就是 `<int>`。非类型实参编码成字面量 `L<类型><值>E`：`Li16E` 是 `16`，`Lc97E` 是 `(char)97`，`Lb1E` 是 `true`。实参包写成 `J…E`，函数形参里的包展开写成 `Dp`。`TnDa` 标记一个类型为 `auto` 的非类型模板参数。

### 函数模板特化编码返回类型

`twice<int>` 的修饰名在 `IiE` 之后先是返回类型 `T_`，再是形参 `S0_`；`ignore<int>` 中的 `v` 也是返回类型。这对应 [[defns.signature.templ]]：函数模板的签名包含返回类型。

所以两个只有返回类型不同的函数模板可以共存，它们的特化有不同的符号：

```cpp
template <class T> int  h(T) { return 0; }
template <class T> long h(T) { return 0; }
```

```text
_Z1hIiEiT_                     int h<int>(int)
_Z1hIiElT_                     long h<int>(int)
```

直接调用 `h(1)` 有歧义，要用 `static_cast<long (*)(int)>(&h<int>)` 这样的写法选中其中一个。

### 类型按模板中的写法编码

`twice<int>` 的返回类型和形参写成 `T_`（第一个模板参数），而不是 `i`。修饰名编码的是模板声明中写的类型，不是替换之后的结果。`_Z5twiceIiET_S0_` 中的 `S_` 是模板名 `twice`，`S0_` 是 `T_`。

`Outer<int>::mem<float>` 的两个形参分别写成 `i` 和 `T_`。外层类模板的 `T` 在这里已经确定为 `int`，只有成员模板自己的参数 `U` 写成 `T_`。这样，两个功能等价但写法不同的函数模板声明能得到不同的名字（[[temp.over.link]]）。

`deduced` 的返回类型编码为 `Da`（`auto`），因为签名里的返回类型就是占位符 `auto`。`cond` 末尾的 `Q…` 编码尾随 requires 子句，其中 `gt` 是 `>`，`st` 是 `sizeof(类型)`。签名包含约束，所以约束不同的两个同名模板能有不同的符号。

### 表达式

表达式也能出现在修饰名里，例如 `decltype` 返回类型：

```cpp
template <class T> auto add(T a, T b) -> decltype(a + b) { return a + b; }
```

```text
_Z3addIiEDTplfp_fp0_ET_S1_  decltype(fp + fp0) add<int>(int, int)
```

`DT…E` 是 `decltype(表达式)`，`pl` 是 `+`，`fp_` 和 `fp0_` 是第一个和第二个函数形参。

## 标准库的名字

### `std` 的缩写

`std` 中的名字极其常见，ABI 为它们预留了固定缩写，不占替换编号：

| 缩写 | 含义 |
|---|---|
| `St` | `::std::` |
| `Sa` | `std::allocator` |
| `Sb` | `std::basic_string` |
| `Ss` | `std::basic_string<char, std::char_traits<char>, std::allocator<char>>` |
| `Si` / `So` / `Sd` | `std::basic_istream<char, ...>` / `basic_ostream` / `basic_iostream` |

下面在 `std` 中手写几个声明，看编译器怎样使用这些缩写。这只是为了观察修饰：用户向 `std` 添加声明是未定义行为（[[namespace.std]]）。

```text
_Z1gSt5thing                             g(std::thing)
_Z1gSaIiE                                g(std::allocator<int>)
_Z1gRKSs                                 g(std::string const&)
_Z1gSt6vectorISsSaISsEE                  g(std::vector<std::string, std::allocator<std::string>>)
```

### 内联命名空间与 ABI 版本

真实的标准库很少直接用上这些缩写，因为它们把实现放在内联命名空间里：

- libc++ 用 `std::__1`。本机原生编译 `void f(const std::string&)` 得到 `__Z1fRKNSt3__112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEEE`。`Ss` 只匹配恰好位于 `::std` 中的 `basic_string`，这里用不上；`NS_` 是第一个替换 `std::__1`。
- libstdc++ 自 GCC 5 起，`std::string` 是 `std::__cxx11::basic_string`（据 libstdc++ 文档对 dual ABI 的说明，本机没有 libstdc++）。它的默认构造函数是 `_ZNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEC1Ev`。`std::ostream` 等没有放进内联命名空间的类仍然使用缩写：`std::cout << 1` 调用的是 `_ZNSolsEi`。

标准库正是靠内联命名空间管理 ABI 版本的。改变 `std::string` 的布局时换一个内联命名空间，所有用到它的符号名随之改变。新旧二进制混用时，错误就出现在链接阶段，而不是运行时。

### `abi_tag`

libstdc++ 还用了 GCC 扩展属性 `abi_tag`。如果返回类型带标签而形参中没有，标签会挂到函数名上，否则只有返回类型不同的两个函数会得到相同的符号：

```cpp
namespace std { inline namespace __cxx11 __attribute__((abi_tag("cxx11"))) { struct string {}; } }
std::string make() { return {}; }
void take(std::string) {}
```

```text
_Z4makeB5cxx11v                make[abi:cxx11]()
_Z4takeNSt7__cxx116stringE     take(std::__cxx11::string)
```

`B5cxx11` 就是标签。`take` 的形参里已经有带标签的类型，不需要另加标签。

## 局部实体、lambda 与无名命名空间

### 局部实体：`Z <函数> E <名字>`

```cpp
int init();
int local_static() {
    static int counter = init();
    struct Local { int get() { return 1; } };
    return counter + Local{}.get();
}
inline int locals(bool b) {
    if (b) { static int n = 1; return n; }
    else   { static int n = 2; return n; }
}
```

```text
_ZZ12local_staticvE7counter              local_static()::counter
_ZGVZ12local_staticvE7counter            guard variable for local_static()::counter
_ZZ12local_staticvEN5Local3getEv         local_static()::Local::get()
_ZZ6localsbE1n                           locals(bool)::n
_ZZ6localsbE1n_0                         locals(bool)::n
```

函数内的静态变量和局部类的成员函数，修饰名以 `Z <所在函数的完整编码> E` 开头。同一个函数里同名的局部实体用**判别符**（discriminator）区分：`locals` 中两个块里的 `static int n` 分别是 `1n` 和 `1n_0`。

`_ZGV` 前缀表示**守卫变量**（guard variable）。局部静态变量在控制流第一次经过声明时初始化，并发进入时其他线程要等待（[[stmt.dcl#3]]），守卫变量记录初始化是否已经完成。只有需要动态初始化的局部静态变量才有它，`locals` 中常量初始化的 `n` 就没有。

局部实体也需要跨 TU 稳定的名字，因为它们可能位于 inline 函数中。[[basic.def.odr]] 要求所有 TU 里的 `locals(bool)::n` 是同一个变量，链接器只能靠名字相同来合并它们。

### lambda：`Ul <形参> E <编号> _`

闭包类型没有名字（[[expr.prim.lambda.closure]]）。当 lambda 出现在 inline 函数、模板、inline 变量这些可能在多个 TU 中定义的地方时，它的闭包类型就需要一个各 TU 一致的名字：

```cpp
template <class F> void call(F f) { f(); }
inline void twolambdas() {
    call([] {});
    call([] {});
    auto l = [](int, char) {}; l(1, 2);
}
inline auto lam_var = [] { return 0; };
```

```text
_Z4callIZ10twolambdasvEUlvE_EvT_             void call<twolambdas()::'lambda'()>(twolambdas()::'lambda'())
_Z4callIZ10twolambdasvEUlvE0_EvT_            void call<twolambdas()::'lambda0'()>(twolambdas()::'lambda0'())
_ZZ10twolambdasvENKUlvE_clEv                 twolambdas()::'lambda'()::operator()() const
_ZZ10twolambdasvENKUlicE_clEic               twolambdas()::'lambda'(int, char)::operator()(int, char) const
_ZNK7lam_varMUlvE_clEv                       lam_var::'lambda'()::operator()() const
```

`UlvE_` 是形参为 `()` 的第一个 lambda，`UlvE0_` 是第二个，`UlicE_` 是形参为 `(int, char)` 的第一个。编号在形参列表相同的 lambda 之间分别计数。`lam_var` 初始化器中的 lambda 以 `7lam_varM` 为前缀，`M` 表示它属于这个变量的初始化器。

只要 inline 函数在各 TU 中的定义相同（这是 ODR 的要求），每个 lambda 在各 TU 中就得到相同的名字，`call<那个 lambda>` 的多份定义才能被链接器合并。

非 inline 函数里的 lambda，闭包类型只会出现在本 TU 中。这时 Clang 不用 ABI 规定的编号，而是给一个内部名字：

```cpp
void use() {
    call([] {});
    auto g = [](auto x) { return x; };
    g(1);
}
```

```text
_Z4callIZ3usevE3$_1EvT_                  void call<use()::$_1>(use()::$_1)
_ZZ3usevENK3$_1clEv                      use()::$_1::operator()() const
_ZZ3usevENK3$_0clIiEEDaT_                _ZZ3usevENK3$_0clIiEEDaT_
```

`$_0`、`$_1` 不是合法的 C++ 标识符，也不是 ABI 规定的编码。这些符号都是局部符号，不需要跨 TU 一致。最后一行是泛型 lambda 的 `operator()<int>`，本机 `llvm-cxxfilt` 无法反修饰这种名字，原样输出。

### 无名命名空间：`_GLOBAL__N_1`

```cpp
namespace { int anon_fn(int x) { return x; } struct Hidden { void m() {} }; }
static int file_static(int x) { return x; }
```

```text
_ZN12_GLOBAL__N_17anon_fnEi              (anonymous namespace)::anon_fn(int)
_ZN12_GLOBAL__N_16Hidden1mEv             (anonymous namespace)::Hidden::m()
_ZL11file_statici                        file_static(int)
```

无名命名空间编码成一个名叫 `_GLOBAL__N_1` 的命名空间，每个 TU 都用这个名字。不同 TU 的同名符号不会冲突，因为它们都是局部符号：无名命名空间具有内部链接，其中的实体也随之具有内部链接（[[basic.link#4]]）。`static` 函数则在名字前加 `L` 标记内部链接：`_ZL11file_statici`。

## 模块附属：`W`

C++20 起，附属于具名模块的实体与全局模块中的同名实体是不同的实体（[[module.unit]]）。Itanium ABI 用 `W` 编码实体所附属的模块：

```cpp title="mm.cppm"
module;
int from_gmf(int x) { return x; }
export module app.core;
export import :detail;
export int answer() { return 42; }
int helper() { return 1; }
export namespace ns {
    struct Widget { void draw() {} };
    void use(Widget w) { w.draw(); }
}
extern "C++" int legacy() { return 0; }
```

```cpp title="mp.cppm"
export module app.core:detail;
int part_fn() { return 3; }
```

```text
_Z8from_gmfi                             from_gmf(int)
_ZW3appW4core6answerv                    answer@app.core()
_ZW3appW4core6helperv                    helper@app.core()
_ZN2nsW3appW4core3useENS_S1_6WidgetE     ns::use@app.core(ns::Widget@app.core)
_ZN2nsW3appW4core6Widget4drawEv          ns::Widget@app.core::draw()
_Z6legacyv                               legacy()
_ZGIW3appW4core                          initializer for module app.core
_ZW3appW4core7part_fnv                   part_fn@app.core()
_ZGIW3appW4coreWP6detail                 initializer for module app.core:detail
```

从输出可以看出：

- 点分模块名 `app.core` 逐段编码为 `W3appW4core`。
- 导出与否不影响符号。`answer`（导出）和 `helper`（未导出）同样带 `W`，同样是全局符号。
- 分区不出现在实体名中。`part_fn` 定义在分区 `:detail` 中，但它附属于模块 `app.core`，符号是 `_ZW3appW4core7part_fnv`。只有分区的初始化函数带 `WP6detail`。
- 全局模块片段中的 `from_gmf` 和 `extern "C++"` 中的 `legacy` 附属于全局模块，符号与普通的非模块代码完全相同。`extern "C++"` 在模块中的用途正是这个：让模块提供与旧代码二进制兼容的实体。
- 命名空间不附属于模块，所以 `ns` 本身不带 `W`；`W` 插在 `ns` 之后、附属实体的名字之前。

主模块接口里的 `export import :detail;` 不能省：一个模块的所有接口分区都必须由主模块接口直接或间接导出，否则程序非良构，不要求诊断（[[module.unit#3]]）。模块的构建流程见 [[toolchain/modules-in-practice]]。

## 函数类型中的 `noexcept`

C++17 起，`noexcept` 是函数类型的一部分（[[except.spec]]），所以它出现在函数类型的编码里：

```cpp
void take_fp(void (*)() noexcept, void (*)()) {}
void nx() noexcept {}
```

```text
_Z7take_fpPDoFvvEPFvvE                   take_fp(void (*)() noexcept, void (*)())
_Z2nxv                                   nx()
```

`Do` 标记 noexcept 函数类型。函数 `nx` 自己的符号却是 `_Z2nxv`：不能仅凭 noexcept 重载，签名里也没有它。

## `extern "C"`：不修饰

```cpp
extern "C" int c_func(int x) { return x; }
extern "C" int c_var = 1;
namespace ns { extern "C" int c_in_ns(int x) { return x; } }
```

```text
0000000000000000 T c_func
0000000000000010 T c_in_ns
0000000000000000 D c_var
```

具有 C 语言链接（[[dcl.link]]）的函数和变量按 C 的规则命名，符号就是标识符本身（Mach-O 上再加 `_`）。命名空间被丢掉了，`ns::c_in_ns` 的符号与全局的 `c_in_ns` 一样。所以 [[dcl.link#7]] 规定，不同命名空间中同名的 C 语言链接函数声明的是同一个函数。形参类型也被丢掉了，所以 C 语言链接的函数不能重载。

!!! lawyer "函数类型的语言链接：标准说是不同类型，编译器不这么做"
    按 [[dcl.link#1]]，语言链接不同的两个函数类型是不同的类型，即使其他方面完全相同。Itanium ABI 也为此预留了编码，即函数类型前的 `Y`。但 GCC 和 Clang 都忽略函数类型的语言链接：

    ```cpp
    extern "C" typedef void CFn();
    typedef void CppFn();
    void take(CFn*) {}
    void take(CppFn*) {}   // 按标准是合法的重载
    ```

    本机 Clang 23 报 `error: redefinition of 'take'`。`llvm-cxxfilt` 能解析含 `Y` 的修饰名（`_Z4takePFYvvE` 反修饰为 `take(void (*)())`），但编译器不会生成它。这是主流实现长期存在的不符合之处。

## 编译器生成的特殊名字

ABI 还为编译器生成的辅助实体规定了名字。下表的每一项都在本机实验的目标文件里出现过：

| 前缀 | 含义 | 例子 |
|---|---|---|
| `_ZTV` | 虚函数表（vtable） | `_ZTV5Shape` |
| `_ZTI` | `type_info` 对象 | `_ZTI5Shape` |
| `_ZTS` | 类型名字符串，`type_info::name()` 的来源 | `_ZTS5Shape` |
| `_ZTT` | VTT，构造含虚基类的对象时使用的 vtable 表 | `_ZTT1D` |
| `_ZTC` | 构造 vtable | `_ZTC1D0_1L`（`L` 作为 `D` 的基类） |
| `_ZTh` | 非虚 thunk：固定量调整 `this` | `_ZThn16_N1C2fbEv` |
| `_ZTv` | 虚 thunk：经 vtable 查出调整量 | `_ZTv0_n24_N1D2fvEv` |
| `_ZGV` | 守卫变量 | `_ZGVZ12local_staticvE7counter` |
| `_ZGR` | 引用绑定的、生存期被延长的临时对象 | `_ZGR1r_`（`const int& r = 42;`） |
| `_ZTW` | thread_local 变量的包装函数 | `_ZTWN2ns1tE` |
| `_ZGI` | 模块初始化函数 | `_ZGIW1m` |

vtable、VTT 和 thunk 的内容见 [[toolchain/object-layout-and-vtables]]。

## 反修饰

```text
$ echo _ZN2ns5inner1hENS0_3TagES1_ | llvm-cxxfilt
ns::inner::h(ns::inner::Tag, ns::inner::Tag)
$ echo __Z5twiceIiET_S0_ | c++filt          # Mach-O 的额外下划线也能处理
int twice<int>(int)
$ llvm-nm -C a.o                              # 列符号时直接反修饰
$ llvm-objdump -d -C a.o                      # 反汇编时反修饰
```

程序内部可以调用 Itanium ABI 的 `abi::__cxa_demangle`（`<cxxabi.h>`）。在 Itanium 平台上，`typeid(T).name()` 返回的就是 `_ZTS` 字符串去掉前缀后的部分，例如 `"5Shape"`。

!!! note "反修饰会丢信息"
    反修饰得到的是给人读的文本，并不保留全部信息。`_Z1fSs` 反修饰为 `f(std::string)`，从文本看不出原名用的是 `Ss` 缩写还是展开写法。用反修饰后的文本判断两个符号是否相同，结论可能是错的。

## MSVC 的修饰方案

下面的 MSVC 修饰名由本机 Clang 以 `--target=x86_64-pc-windows-msvc` 生成，用 `llvm-undname` 反修饰。Clang 在 Windows 目标上实现了与 MSVC 兼容的修饰，以便与 MSVC 编译的代码互通；本机没有 MSVC，没有逐字核对两者一致。

```text
?f@@YAXH@Z                   void __cdecl f(int)
?f@@YAXHND@Z                 void __cdecl f(int, double, char)
?f2@@YAHH@Z                  int __cdecl f2(int)
?g@ns@@YAXPEAH@Z             void __cdecl ns::g(int *)
?m@S@@QEBAXXZ                public: void __cdecl S::m(void) const
??0S@@QEAA@XZ                public: __cdecl S::S(void)
??1S@@UEAA@XZ                public: virtual __cdecl S::~S(void)
??_GS@@UEAAPEAXI@Z           public: virtual void * __cdecl S::`scalar deleting dtor'(unsigned int)
??_7S@@6B@                   const S::`vftable'
?count@S@@2HA                public: static int S::count
??$twice@H@@YAHH@Z           int __cdecl twice<int>(int)
c_func                       (extern "C"，不修饰)
```

与 Itanium 方案的主要差别：

- 以 `?` 开头，各级限定从内到外书写，用 `@` 分隔，以 `@@` 结束。
- 非模板函数也编码返回类型（`?f2@@YAHH@Z` 中的第一个 `H` 是返回的 `int`），变量也编码类型（`?count@S@@2HA` 中的 `H`）。[[toolchain/linking-and-symbols]] 中返回类型不一致却能链接的例子，在这种方案下符号名不同，会链接失败。
- 编码调用约定（`A` 是 `__cdecl`）和访问控制（`Q` 是 public 成员函数，`2` 是 public 静态数据成员）。把成员从 `private` 改成 `public` 会改变符号名，破坏二进制兼容；Itanium 不编码访问控制。
- 构造函数是 `??0`，析构函数是 `??1`，vtable 是 `??_7`，RTTI 相关对象是 `??_R0` 到 `??_R4`。

## 思考题

!!! question "思考题 1"
    `a.cpp` 定义了 `long size() { return 1; }`，`b.cpp` 声明 `int size();` 并调用它。在 Linux 上用 GCC 编译链接会怎样？在 Windows 上用 MSVC 呢？

<details markdown="1">
<summary>答案</summary>

两边声明的是同一个函数，但类型不同。两个声明互不可达，所以程序非良构、不要求诊断（[[basic.link#11]]）。Itanium 方案不编码非模板函数的返回类型，两边的符号都是 `_Z4sizev`，链接成功，运行结果没有保证。MSVC 方案编码返回类型，两个符号分别是 `?size@@YAJXZ` 和 `?size@@YAHXZ`，链接时报未解析的外部符号。
</details>

!!! question "思考题 2"
    为什么 inline 函数里的 lambda 要用 `UlvE_` 这种按顺序编号的名字，而普通函数里的 lambda 可以用 `$_0` 这种实现自定的名字？

<details markdown="1">
<summary>答案</summary>

inline 函数可以在多个 TU 中定义，[[basic.def.odr]] 要求这些定义表示同一个实体，其中的 lambda 闭包类型在各 TU 中也必须是同一个类型。以它为实参的模板特化（如 `call<那个 lambda>`）会在多个 TU 中生成，链接器只能靠名字相同来合并它们，所以名字必须由各 TU 都能独立算出的规则决定。普通函数只在一个 TU 中定义，其中的 lambda 不会出现在别的 TU 里，相关符号都是局部符号，叫什么都不影响链接。
</details>
