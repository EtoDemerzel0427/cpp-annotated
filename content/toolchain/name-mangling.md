---
title: 名字修饰（Itanium C++ ABI）
summary: C++ 的签名如何编码成链接器能比较的字符串：_Z 前缀、嵌套名 N…E、内建类型代码、指针/引用/cv、替换 S_/S0_、std 缩写 St/Sa/Ss/So、模板实参 I…E 与 T_、返回类型何时出现、noexcept、成员函数的 cv/ref 限定、构造/析构函数变体、lambda（UlvE_）、局部实体（Z…E）、无名命名空间、模块附属（W）、abi_tag、特殊名字（vtable/guard/thunk）；extern "C" 不修饰；反修饰工具；MSVC 修饰方案对照
status: draft
order: 25
related: intro.defs, dcl.link, basic.link, over.load, temp.over.link, dcl.fct, expr.prim.lambda.closure, module.unit, toolchain/linking-and-symbols, toolchain/object-layout-and-vtables
tags: 工具链, ABI, Itanium, 名字修饰, 链接
updated: 2026-10-18
---

链接器只认字符串。C++ 却允许同名函数重载、同名实体分属不同命名空间和类、模板生成无数个同名特化——这些"同名不同实体"必须变成**不同的字符串**，同一实体在不同 TU 中又必须变成**相同的字符串**。把 C++ 实体编码成符号名的规则叫**名字修饰**（name mangling）。

标准对此只字未提，但它定义了修饰所依据的东西：**签名**（signature）。[[defns.signature]] 的注释直白地说：签名是名字修饰和链接的基础。函数的签名包括名字、形参类型列表、所属命名空间；成员函数还有所属类、cv 限定、引用限定；函数模板还包括**返回类型**和模板头。凡是签名里有的，修饰名里都得有；签名里没有的（比如非模板函数的返回类型），修饰名里通常也没有——[[toolchain/linking-and-symbols]] 演示了这带来的后果。

本页讲 GCC、Clang 在除 Windows 以外的几乎所有平台上使用的 **Itanium C++ ABI** 修饰方案。所有例子都用本机 Homebrew Clang 23.1.3 以 `clang++ -std=c++2c --target=x86_64-linux-gnu -c` 编译，用 `llvm-nm` 列符号、`llvm-cxxfilt` 反修饰。Mach-O（macOS）上的符号在此基础上**再加一个前导下划线**（`_Z3apiv` → `__Z3apiv`），其余完全相同。

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

拆开 `_Z1fidc`：

| 片段 | 含义 |
|---|---|
| `_Z` | "这是一个修饰过的 C++ 名字"。以 `_Z` 开头的标识符是实现保留的（[[lex.name]]），所以不会与用户名字冲突 |
| `1f` | **源名字**（source-name）：长度 + 标识符 |
| `idc` | 形参类型：`int`、`double`、`char` |

没有形参写 `v`（void）。**非模板函数的返回类型不编码**——重载决议不看返回类型（[[over.load]]），签名里也没有它。

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

注意 `char`、`signed char`、`unsigned char` 是三个不同的代码——它们是三个不同的类型（[[basic.fundamental]]）。`int` 与 `long` 即使在某平台上大小相同，也是不同的代码。

### 指针、引用、cv、数组、函数类型

```text
_Z1fPiPKiRiRS0_OiPVi                     f(int*, int const*, int&, int const&, int&&, int volatile*)
_Z1fPiPA3_iRA4_i                         f(int*, int (*) [3], int (&) [4])
_Z1fPFviEPFidcE                          f(void (*)(int), int (*)(double, char))
```

| 代码 | 含义 |
|---|---|
| `P` | 指针 |
| `R` / `O` | 左值引用 / 右值引用 |
| `K` / `V` / `r` | const / volatile / restrict（写在被修饰类型之前：`PKi` = 指向 `const int` 的指针） |
| `A3_i` | `int[3]` |
| `F…E` | 函数类型：返回类型 + 形参类型 |
| `M<类><成员类型>` | 成员指针 |

第二行值得细看：源码里第一个形参写的是 `int[3]`，修饰名却是 `Pi`——形参类型列表是在**调整之后**确定的（[[dcl.fct]]：数组形参调整为指针，函数形参调整为函数指针，顶层 cv 被丢弃）。所以 `void f(int[3])` 与 `void f(int*)` 是同一个函数，`void f(const int)` 与 `void f(int)` 也是：

```text
error: redefinition of 'f'
note: previous definition is here
    2 | void f(int) {}
```

而 `int (*)[3]`（`PA3_i`）中的数组边界不会被调整，它是类型的一部分。

### 替换：`S_`、`S0_`、`S1_`……

修饰名会变得很长，于是 ABI 规定：已经出现过的"组件"（带限定的名字、复合类型、模板参数等，但**不包括**内建类型）按出现顺序编号，之后再出现时用**替换**（substitution）引用：第一个是 `S_`，第二个 `S0_`，然后 `S1_`……（序号是 36 进制，数字加大写字母）。

`_Z1fPiPKiRiRS0_OiPVi` 中：

| 编号 | 组件 |
|---|---|
| `S_` | `Pi`（`int*`） |
| `S0_` | `Ki`（`const int`） |
| `S1_` | `PKi` |
| `S2_` | `Ri` |

于是第四个形参 `const int&` 写成 `RS0_`，而不是 `RKi`。命名空间也是组件：

```text
_ZN2ns5inner1hENS0_3TagES1_              ns::inner::h(ns::inner::Tag, ns::inner::Tag)
```

`S_` = `ns`，`S0_` = `ns::inner`；`NS0_3TagE` 即 `ns::inner::Tag`，成为 `S1_`，第二个形参直接写 `S1_`。

## 命名空间与类：嵌套名 `N…E`

```text
_ZN2ns1gEi                         ns::g(int)
_ZN2ns3varE                        ns::var
_ZN1S5countE                       S::count
ns_var                             ns_var
```

`N` 与 `E` 之间是从外到内的各级名字。注意后三行是**变量**：命名空间或类中的变量名只编码限定名，**不编码类型**；而全局命名空间中的变量 `ns_var` **完全不修饰**，与 C 的变量同名——这正是 [[dcl.link#7]] 规定"C 语言链接的变量与全局作用域中同名的变量是同一实体"的物理基础。

### 成员函数：cv 与引用限定

```cpp
struct S {
    void m() {}
    void m() const {}
    void m() volatile {}
    void r() & {}
    void r() && {}
    static void s() {}
    // ...
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

成员函数的 cv 限定和引用限定紧跟在 `N` 之后（`NK`、`NV`、`NR`、`NO`），对应 [[defns.signature]] 中成员函数签名的"cv 限定符、引用限定符"。静态成员函数 `s()` 与同形参的非静态、非 const 成员函数修饰名一样——因为两者本来就不能重载（[[over.load]]）。

### 运算符与转换函数

```text
_ZN1SaSERKS_                       S::operator=(S const&)
_ZNK1SeqERKS_                      S::operator==(S const&) const
_ZN1SixEi                          S::operator[](int)
_ZNK1ScviEv                        S::operator int() const
_ZN1SclEv                          S::operator()()
```

运算符用两个小写字母编码：`aS`（=）、`eq`（==）、`ix`（[]）、`cl`（()）、`cv`（转换函数，后跟目标类型）、`nw`（new）、`pl`（+）、`gt`（>）、`st`（sizeof 类型）……注意 `RKS_`：`S_` 在这里是类 `S` 本身——它是第一个出现的组件。

### 构造函数与析构函数的变体

构造函数和析构函数没有可用的名字，用 `C`/`D` 加一个数字表示，而且**一个构造函数会生成多个符号**：

```cpp
struct T { T(); ~T(); virtual void v(); };
T::T() {} T::~T() {} void T::v() {}
```

```text
$ llvm-nm ctor.o
0000000000000000 T _ZN1TC1Ev
0000000000000000 T _ZN1TC2Ev
0000000000000020 T _ZN1TD1Ev
0000000000000020 T _ZN1TD2Ev
...
```

| 代码 | 含义 |
|---|---|
| `C1` | **完整对象**构造函数（complete object constructor）：构造整个对象，包括虚基类 |
| `C2` | **基类子对象**构造函数（base object constructor）：作为别人的基类被构造时使用，不构造虚基类 |
| `D0` | **删除**析构函数（deleting destructor）：析构后调用 `operator delete`，供 `delete p` 通过 vtable 调用 |
| `D1` | 完整对象析构函数 |
| `D2` | 基类子对象析构函数 |

区分 C1/C2 是为了虚基类：虚基类只能由**最派生类**构造一次（[[class.base.init]]）。没有虚基类时两者完全一样，所以上面 `C1` 与 `C2` 地址相同（Linux 目标下 Clang 默认 `-mconstructor-aliases`，让 C1 成为 C2 的别名）。`D0` 只在有虚析构函数时出现；[[toolchain/linking-and-symbols]] 中 `Shape` 的两个 `Shape::~Shape()` 就是 D0 和 D2。

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

规则要点：

- **模板实参**写在 `I…E` 之间：`IiE` 即 `<int>`。非类型实参是**字面量** `L<类型><值>E`：`Li16E` 即 `16`，`Lc97E` 即 `(char)97`，`Lb1E` 即 `true`。实参包写成 `J…E`。
- **函数模板特化编码返回类型**：`twice<int>` 是 `IiE` 后紧跟 `T_`（返回类型）再跟 `S0_`（形参）。`ignore<int>` 的 `v` 也是返回类型。这对应 [[defns.signature.templ]]：函数模板的签名包含返回类型。后果之一是，两个只有返回类型不同的函数模板可以共存，它们的特化有不同的符号：

    ```text
    _Z1hIiEiT_                     int h<int>(int)
    _Z1hIiElT_                     long h<int>(int)
    ```

- **类型以"模板中的写法"编码，而不是替换后的结果**。`twice<int>` 的返回类型和形参都写成 `T_`（第一个模板参数）而非 `i`——签名里的是模板中声明的 `T`，不是 `int`。这就是为什么 `_Z5twiceIiET_S0_` 里出现 `S0_`：`S_` 是模板名 `twice`，`S0_` 是 `T_`。`Outer<int>::mem<float>` 则形参写成 `i` 和 `T_`：外层类模板的 `T` 在这里已经是确定的 `Outer<int>` 的一部分，只有成员模板**自己的**参数 `U` 写成 `T_`。这一设计使得"功能等价但写法不同"的函数模板声明能被正确区分（[[temp.over.link]]）。
- `Dp` 是包展开，`Da` 是 `auto`（`deduced` 的返回类型以占位符形式编码，因为签名里的返回类型就是 `auto`）。
- `TnDa` 标记"类型为 `auto` 的非类型模板参数"；`Q…` 编码**尾随 requires 子句**（`gt` = `>`，`st` = `sizeof(类型)`）——签名包含约束（[[defns.signature.templ]]），约束不同的两个同名模板因此能有不同的符号。

表达式也能出现在修饰名中，例如 `decltype` 返回类型：

```text
_Z3addIiEDTplfp_fp0_ET_S1_  decltype(fp + fp0) add<int>(int, int)
```

`DT…E` 是 `decltype(表达式)`，`pl` 是 `+`，`fp_`/`fp0_` 是第一、第二个函数形参。

### 标准库缩写

`std` 中的名字极其常见，ABI 为它们预留了固定缩写，不占用替换编号：

| 缩写 | 含义 |
|---|---|
| `St` | `::std::` |
| `Sa` | `std::allocator` |
| `Sb` | `std::basic_string` |
| `Ss` | `std::basic_string<char, std::char_traits<char>, std::allocator<char>>` |
| `Si` / `So` / `Sd` | `std::basic_istream<char, ...>` / `basic_ostream` / `basic_iostream` |

（以上用 `llvm-cxxfilt` 反修饰 `_Z1fSi`、`_Z1fSo`、`_Z1fSd`、`_Z1fSbIwE`、`_Z1fSs` 核对过。）为了看到编译器真的生成它们，下面在 `std` 中手写几个声明——**这只是为了观察修饰**，用户向 `std` 添加声明是 UB（[[namespace.std]]）：

```text
_Z1gSt5thing                             g(std::thing)
_Z1gSaIiE                                g(std::allocator<int>)
_Z1gRKSs                                 g(std::string const&)
_Z1gSt6vectorISsSaISsEE                  g(std::vector<std::string, std::allocator<std::string>>)
```

但**真实的标准库很少直接用上这些缩写**，因为它们把实现放在内联命名空间里：

- **libc++** 用 `std::__1`。本机原生编译 `void f(const std::string&)` 得到 `__Z1fRKNSt3__112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEEE`——`Ss` 只匹配恰好位于 `::std` 中的 `basic_string`，这里用不上；`NS_` 即 `std::__1`（第一个替换）。
- **libstdc++** 自 GCC 5 起 `std::string` 是 `std::__cxx11::basic_string`（据 libstdc++ 文档的"dual ABI"说明；本机没有 libstdc++），例如 `_ZNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEC1Ev`（`llvm-cxxfilt` 本机反修饰核对）。`So`（`std::ostream`）等未进入内联命名空间的类仍然使用缩写：`std::cout << 1` 调用的是 `_ZNSolsEi`。

内联命名空间正是标准库实现 ABI 版本管理的手段：改变 `std::string` 的布局时换一个内联命名空间，所有用到它的符号名随之改变，新旧二进制混用就会在**链接时**失败而不是在运行时崩溃。

### abi_tag

libstdc++ 还用了 GCC 扩展属性 `abi_tag`。返回类型带标签而形参中没有时，标签被挂到**函数名**上，否则只改返回类型的两个函数会有相同的符号（返回类型不进修饰名）：

```cpp
namespace std { inline namespace __cxx11 __attribute__((abi_tag("cxx11"))) { struct string {}; } }
std::string make() { return {}; }
void take(std::string) {}
```

```text
_Z4makeB5cxx11v                make[abi:cxx11]()
_Z4takeNSt7__cxx116stringE     take(std::__cxx11::string)
```

`B5cxx11` 就是标签。`take` 的形参里已经含有带标签的类型，不需要额外标签。

## 局部实体、lambda、无名命名空间

### 局部实体：`Z <函数> E <名字>`

```text
_ZZ12local_staticvE7counter              local_static()::counter
_ZGVZ12local_staticvE7counter            guard variable for local_static()::counter
_ZZ12local_staticvEN5Local3getEv         local_static()::Local::get()
_ZZ6localsbE1n                           locals(bool)::n
_ZZ6localsbE1n_0                         locals(bool)::n
```

函数内的静态变量、局部类的成员函数以 `Z <所在函数的完整编码> E` 开头。同一函数内同名的多个局部实体用**判别符**（discriminator）区分：`locals` 里两个不同块中的 `static int n` 分别是 `1n` 和 `1n_0`。`_ZGV` 前缀是**守卫变量**（guard variable），用于实现"首次经过声明时初始化且线程安全"（[[stmt.dcl]]）——只有需要动态初始化的局部静态变量才有它，`locals` 中常量初始化的 `n` 就没有。

为什么局部实体需要跨 TU 稳定的名字？因为它们可能位于 inline 函数中，[[basic.def.odr]] 要求所有 TU 中的 `locals(bool)::n` 是**同一个**变量。

### lambda：`Ul <形参> E <编号> _`

闭包类型没有名字（[[expr.prim.lambda.closure]]）。它何时需要一个跨 TU 一致的名字？当它出现在 inline 函数、模板、inline 变量这些"可能在多个 TU 中定义"的上下文中时：

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

`UlvE_` = "形参为 `()` 的第一个 lambda"，`UlvE0_` = 第二个，`UlicE_` = "形参为 `(int, char)` 的第一个 lambda"——编号按**形参列表相同**的 lambda 分别计数。`lam_var` 的初始化器里的 lambda 以 `7lam_varM` 为前缀（`M` 表示"属于这个变量的初始化器"）。这套编号规则保证了：只要 inline 函数在各 TU 中的定义相同（ODR 要求的），每个 lambda 在各 TU 中就得到相同的名字，`call<那个 lambda>` 才能被链接器合并。

而在**非 inline 函数**里的 lambda，闭包类型只可能在本 TU 中出现。Clang 此时不用 ABI 规定的编号，而是给一个内部名字：

```text
_Z4callIZ3usevE3$_1EvT_                  void call<use()::$_1>(use()::$_1)
_ZZ3usevENK3$_1clEv                      use()::$_1::operator()() const
_ZZ3usevENK3$_0clIiEEDaT_                _ZZ3usevENK3$_0clIiEEDaT_
```

`$_1` 不是合法的 C++ 标识符，也不是 ABI 规定的编码——它只用于局部符号，不需要跨 TU 一致。（最后一行是泛型 lambda 的 `operator()<int>`，本机 `llvm-cxxfilt` 无法反修饰这种名字，原样输出。）

### 无名命名空间：`_GLOBAL__N_1`

```text
_ZN12_GLOBAL__N_17anon_fnEi              (anonymous namespace)::anon_fn(int)
_ZN12_GLOBAL__N_16Hidden1mEv             (anonymous namespace)::Hidden::m()
_ZL11file_statici                        file_static(int)
```

无名命名空间被编码为一个名叫 `_GLOBAL__N_1` 的命名空间。每个 TU 的无名命名空间都叫这个名字——不同 TU 的同名符号不会冲突，因为这些符号都是 `LOCAL` 的（[[basic.link#4]]：无名命名空间中的实体具有内部链接）。`static` 函数则用 `L` 前缀标记内部链接：`_ZL11file_statici`。

## 模块附属：`W`

C++20 起，附属于具名模块的实体与全局模块中的同名实体是**不同的实体**（[[basic.link#10]]、[[module.unit]]）。Itanium ABI 用 `W` 编码模块名：

```cpp title="mm.cppm"
module;
int from_gmf(int x) { return x; }
export module app.core;
export int answer() { return 42; }
int helper() { return 1; }
export namespace ns { struct Widget { void draw() {} }; void use(Widget w) { w.draw(); } }
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

观察：

- 点分模块名 `app.core` 逐段编码为 `W3appW4core`。
- **导出与否不影响符号**：`answer`（导出）与 `helper`（未导出）同样带 `W`、同样是全局符号。
- **分区不出现在实体名中**：`part_fn` 定义在分区 `:detail` 中，但它附属于模块 `app.core`，符号是 `_ZW3appW4core7part_fnv`——分区只是模块的组成部分，不是独立的附属对象。只有分区的初始化函数带 `WP6detail`。
- **全局模块片段**中的 `from_gmf` 和 `extern "C++"` 中的 `legacy` 附属于全局模块（[[module.unit]]），符号与普通的非模块代码完全相同——这正是 `extern "C++"` 在模块中的用途：让模块能提供与旧代码二进制兼容的实体。
- `ns` 本身不带 `W`（命名空间不附属于模块），`W` 插在 `ns` 之后、附属实体的名字之前。

模块的构建流程见 [[toolchain/modules-in-practice]]。

## 函数类型中的 `noexcept`

C++17 起 `noexcept` 是函数类型的一部分（[[except.spec]]），所以它出现在**函数类型**的编码里：

```text
_Z7take_fpPDoFvvEPFvvE                   take_fp(void (*)() noexcept, void (*)())
_Z2nxv                                   nx()
```

`Do` 标记 noexcept 函数类型。但函数 `void nx() noexcept` 本身的符号是 `_Z2nxv`——不能仅凭 noexcept 重载，签名里也没有它。

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

C 语言链接（[[dcl.link]]）的函数和变量使用 C 的命名规则：就是标识符本身（Mach-O 上加 `_`）。**命名空间被丢掉了**——`ns::c_in_ns` 的符号与全局的 `c_in_ns` 一样，所以 [[dcl.link#7]] 规定：不同命名空间中同名的 C 语言链接函数声明的是**同一个函数**。形参类型也被丢掉了，所以 C 语言链接的函数不能重载。

!!! lawyer "函数类型的语言链接：标准说是不同类型，编译器不这么做"
    [[dcl.link#1]] 规定：语言链接不同的两个函数类型是**不同的类型**，即使其他方面完全相同。Itanium ABI 也为此预留了编码（函数类型前的 `Y`）。但 GCC 和 Clang 都忽略函数类型的语言链接：

    ```cpp
    extern "C" typedef void CFn();
    typedef void CppFn();
    void take(CFn*) {}
    void take(CppFn*) {}   // 按标准是合法重载
    ```

    本机 Clang 23 报 `error: redefinition of 'take'`。（`llvm-cxxfilt` 能解析含 `Y` 的修饰名，`_Z4takePFYvvE` 反修饰为 `take(void (*)())`，但编译器不会生成它。）这是主流实现长期存在的不符合之处。

## 特殊名字

ABI 还为编译器生成的各种辅助实体规定了名字。下表的每一项都在本站实验的目标文件中实际出现过：

| 前缀 | 含义 | 例子 |
|---|---|---|
| `_ZTV` | 虚函数表（vtable） | `_ZTV5Shape` |
| `_ZTI` | `type_info` 对象 | `_ZTI5Shape` |
| `_ZTS` | 类型名字符串（`type_info::name()` 的来源） | `_ZTS5Shape` |
| `_ZTT` | VTT（虚基类构造用的 vtable 表） | `_ZTT1D` |
| `_ZTC` | 构造 vtable | `_ZTC1D0_1L`（L-in-D） |
| `_ZTh` | 非虚 thunk（固定 this 调整） | `_ZThn16_N1C2fbEv` |
| `_ZTv` | 虚 thunk（经 vtable 查 this 调整） | `_ZTv0_n24_N1D2fvEv` |
| `_ZGV` | 守卫变量 | `_ZGVZ12local_staticvE7counter` |
| `_ZGR` | 引用绑定的临时对象（生存期延长） | `_ZGR1r_`（`const int& r = 42;`） |
| `_ZTW` | thread_local 变量的包装函数 | `_ZTWN2ns1tE` |
| `_ZGI` | 模块初始化函数 | `_ZGIW1m` |

vtable、VTT、thunk 的内容见 [[toolchain/object-layout-and-vtables]]。

## 反修饰

```text
$ echo _ZN2ns5inner1hENS0_3TagES1_ | llvm-cxxfilt
ns::inner::h(ns::inner::Tag, ns::inner::Tag)
$ echo __Z5twiceIiET_S0_ | c++filt          # macOS 的 c++filt 自动处理额外的 _
int twice<int>(int)
$ llvm-nm -C a.o                              # nm 直接反修饰
$ llvm-objdump -d -C a.o                      # 反汇编时反修饰
```

本机的 `llvm-cxxfilt` 与 `c++filt` 对带或不带额外下划线的名字都能正确反修饰。程序内部可以调用 Itanium ABI 的 `abi::__cxa_demangle`（`<cxxabi.h>`）；`typeid(T).name()` 在 Itanium 平台返回的就是 `_ZTS` 字符串去掉前缀后的部分（如 `"5Shape"`）。

!!! note "反修饰不可逆"
    反修饰得到的是**人读的**文本，并不保留全部信息：`_Z1fSs` 反修饰为 `f(std::string)`，你无法从文本看出原名里用的是 `Ss` 缩写还是展开写法。用反修饰后的文本比较两个符号是否相同，结论可能是错的。

## MSVC 的修饰方案

!!! warning "以下 MSVC 修饰名由本机 Clang 以 `--target=x86_64-pc-windows-msvc` 生成、用 `llvm-undname` 反修饰，而不是由 MSVC 本身生成"
    Clang 在 Windows 目标上实现了与 MSVC 兼容的修饰方案，目的是与 MSVC 编译的代码二进制互通，但本机没有 MSVC，无法逐字核对两者一致。

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

与 Itanium 的主要差别：

- 以 `?` 开头，名字的各级限定**从内到外**书写，以 `@` 分隔、`@@` 结束。
- **非模板函数也编码返回类型**（`?f2@@YAHH@Z` 中的第一个 `H` 是返回的 `int`），**变量也编码类型**（`?count@S@@2HA` 中的 `H`）。[[toolchain/linking-and-symbols]] 中"返回类型不一致却能链接"的例子在这种修饰下符号名不同。
- 编码**调用约定**（`A` = `__cdecl`）和**访问控制**（`Q` = public 成员函数，`2` = public 静态数据成员）：把成员从 `private` 改成 `public` 会改变符号名，从而破坏二进制兼容；Itanium 不编码访问控制。
- 构造函数是 `??0`，析构函数 `??1`，vtable `??_7`，RTTI 系列 `??_R0`…`??_R4`。

## 小结

!!! summary
    - 修饰名编码的是**签名**（[[defns.signature]]）：名字、限定、形参类型列表；成员函数加 cv/ref 限定；函数模板特化加返回类型、模板实参和约束。
    - Itanium：`_Z` + 名字 + 形参；嵌套名 `N…E`；替换 `S_`/`S0_`… 压缩重复组件；`std` 缩写 `St`/`Sa`/`Ss`/`So`；模板实参 `I…E`，模板中的类型以 `T_` 形式编码。
    - 非模板函数的返回类型和变量的类型不编码——链接器发现不了这类不一致。
    - 局部实体 `Z…E` + 判别符，inline 上下文中的 lambda `Ul…E<n>_`；无名命名空间 `_GLOBAL__N_1`（局部符号）；模块附属 `W`，导出与否、分区都不影响实体的符号。
    - `extern "C"` 不修饰，丢掉命名空间和形参类型；主流编译器忽略函数类型的语言链接。
    - 一个构造/析构函数对应多个符号（C1/C2、D0/D1/D2）。
    - MSVC 方案编码返回类型、变量类型、调用约定和访问控制。
