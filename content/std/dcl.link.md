---
title: 链接规格
summary: extern "C" 怎样让 C++ 声明按 C 的约定与外界连接；什么东西有语言链接，链接规格怎样嵌套和作用；为什么不同命名空间里的同名 C 函数是同一个函数。
status: done
related: basic.link, dcl.stc, dcl.fct, namespace.udir, lex.string.uneval, module.import, alg.c.library
tags: 链接, extern "C", ABI, 互操作
updated: 2026-10-19
---

!!! tldr
    - `extern "C"` 给声明指定 C 语言链接，实践中就是用 C 的方式命名符号、按 C 的约定调用。它和名字的链接（外部、内部等）是两回事。
    - 链接规格可以嵌套，最内层的说了算；它不建立作用域，只能写在命名空间作用域。
    - 类成员忽略 C 语言链接，所以静态成员函数严格说不能当 C 回调。
    - C 语言链接的同名函数或变量，无论声明在哪个命名空间，都是同一个实体，因此它们不能重载。
    - 按标准，语言链接是函数类型的一部分；GCC、Clang、MSVC 都不区分。

## C 头文件里的 extern "C"

C++ 有命名空间和重载，所以要把参数类型、所在命名空间编进目标文件里的符号名，这叫名字修饰（name mangling）。C 没有这些，函数 `api` 的符号就是 `api`。C++ 代码要调用 C 库，或者导出一个让 C 调用的函数，就得让编译器对这个声明按 C 的约定处理：

```cpp
#ifdef __cplusplus
extern "C" {
#endif
int c_api(int);            // 在 C++ 中具有 C 语言链接
#ifdef __cplusplus
}
#endif
```

C 头文件用这个写法同时服务两种语言。`extern "C" { ... }` 叫做**链接规格**（linkage specification）。标准不谈名字修饰和调用约定，而是用一个抽象的概念描述它：**[[g:language-linkage|语言链接]]**（language linkage），即实体或函数类型按哪种语言的约定与外界连接。

语言链接和[[basic.link|链接]]（linkage）是两个独立的概念。链接说的是一个名字能否在别的作用域或翻译单元里指代同一个实体，分为外部、模块、内部和无链接。`extern "C" { static void f(); }` 里的 `f` 有内部链接，所以没有语言链接，但它的函数类型仍然有 C 语言链接（见下文例 2）。

## 什么东西有语言链接（¶1）

¶1 名字具有外部链接的函数和变量，以及所有函数类型，都有语言链接，默认是 C++ 语言链接。注 1 说明，语言链接关联的性质，比如外部名字的表示形式、调用约定，由各实现决定，标准不描述。

¶1 最后一句规定，两个函数类型只要语言链接不同，就是不同的类型：

!!! std
    Two function types with different language linkages are distinct types even if they are otherwise identical.

    两个函数类型如果语言链接不同，即使其余部分完全相同，也是不同的类型。

这样规定是因为 C 和 C++ 的调用约定在某些平台上可能不同。如果把 C++ 函数的指针交给 C 代码去调用，调用方式就可能错了；语言链接成为类型的一部分后，编译器可以在类型检查时拒绝这种混用。

!!! impl "实际上没有编译器这样做"
    GCC、Clang、MSVC 都不把语言链接当作函数类型的一部分。在它们支持的平台上，C 和 C++ 的调用约定相同，区分类型只会带来麻烦。所以下面的代码按标准应当成立，在本机 Clang 23 上 `static_assert` 却失败，第二个 `take` 被当作第一个的重复声明：

    ```cpp
    extern "C" typedef void cfn();
    typedef void cppfn();
    void take(cfn*);
    void take(cppfn*);                 // 标准：重载；编译器：重复声明
    #include <type_traits>
    static_assert(!std::is_same_v<cfn, cppfn>);   // 标准：成立；Clang 23：失败
    ```

    为了照顾按标准区分类型的实现，[[alg.c.library]] 要求 `std::qsort` 和 `std::bsearch` 同时提供接受 C 语言链接比较函数和接受 C++ 语言链接比较函数的版本。否则按标准，把普通的 C++ 函数传给 `std::qsort` 就是类型错误。

## 语法与支持的语言（¶2–¶4）

```text
linkage-specification:
    extern unevaluated-string { declaration-seq(opt) }
    extern unevaluated-string name-declaration
```

```cpp title="linkage-basic.cpp" error
struct complex { double re, im; };
complex sqrt(complex);          // 默认 C++ 语言链接
extern "C" {
    double sqrt(double);        // C 语言链接
}
extern "Ada" void ada_proc();   // error: 本机 Clang 23 不认识 "Ada"
```

¶2 引号里是一个不求值字符串（[[lex.string.uneval]]），不能带编码前缀。标准只规定 `"C"` 和 `"C++"` 的含义，第 3 段要求每个实现都支持这两种。其他字符串是有条件支持的，含义由实现定义 {{impl}}；注 3 指出，实现不认识的语言链接必须诊断。推荐做法是按定义该语言的文档拼写，例如 `Ada` 而不是 `ADA`。

两个 `sqrt` 是重载：同名函数中至多一个有 C 语言链接，就可以共存（原因见下文第 7 段）。

¶4 链接规格里的模块导入声明，如果语言链接不是 C++，就是有条件支持的，含义由实现定义。

## 嵌套、作用域与作用范围（¶5）

```cpp title="linkage-nest.cpp" error
extern "C++" {
    extern "C" void inner();          // OK：最内层是 "C"
}
extern "C" { int x_in_global; }       // x_in_global 是全局命名空间的成员
int* p = &::x_in_global;              // OK

void blk() {
    extern "C" void nope();           // error: 链接规格不能出现在块作用域
}
```

¶5 链接规格可以嵌套，由最内层决定语言链接。注 4 指出链接规格不建立作用域，所以上面的 `x_in_global` 就是全局命名空间的成员。链接规格只能出现在命名空间作用域。

在链接规格里，指定的语言链接作用于两类东西：所有函数声明符的函数类型，以及名字具有外部链接的函数和变量。于是函数本身和它的类型可以有不同的语言链接，标准例 2 展示了几种组合：

```cpp title="linkage-types.cpp" ok
extern "C"
    void f1(void (*pf)(int));   // f1 及其类型有 C 语言链接；pf 指向 C 函数

extern "C" typedef void FUNC();
FUNC f2;                        // f2 有 C++ 语言链接，它的类型有 C 语言链接

extern "C" FUNC f3;             // f3 及其类型都有 C 语言链接

void (*pf2)(FUNC*);             // pf2 有 C++ 语言链接；类型是指向 C++ 函数的指针，
                                // 该函数的形参是指向 C 函数的指针
extern "C" {
    static void f4();           // 内部链接，所以 f4 没有语言链接；它的类型有 C 语言链接
}

extern "C" void f5() {
    extern void f4();           // OK：链接（内部）和类型的语言链接（C）沿用先前的声明
}
extern void f4();               // OK：同上
void f6() {
    extern void f4();           // OK：同上
}

static void f4() {}
int main() {}
```

想单独表示一个 C 语言链接的函数类型，比如声明 C 回调的类型，只能像 `FUNC` 这样把 `typedef` 放进链接规格。

### 类成员忽略 C 语言链接

¶5 最后一句规定，确定下面三者的语言链接时，C 语言链接被忽略：类成员、带尾随 requires 子句的友元函数、非静态成员函数的函数类型。

```cpp title="linkage-members.cpp" ok
extern "C" typedef void FUNC_c();

class C {
    void mf1(FUNC_c*);          // mf1 及其类型有 C++ 语言链接；形参指向 C 函数
    FUNC_c mf2;                 // mf2 及其类型有 C++ 语言链接
    static FUNC_c* q;           // q 有 C++ 语言链接；类型是指向 C 函数的指针
};

extern "C" {
    class X {
        void mf();              // mf 及其类型有 C++ 语言链接
        void mf2(void(*)());    // mf2 有 C++ 语言链接；形参指向 C 函数
    };
}

int main() {}
```

C 代码没有 `this`，也没有类作用域，无法直接调用成员函数，给它 C 语言链接没有意义。而把含有结构体定义的 C 头文件包在 `extern "C" { }` 里又极其常见，所以标准选择静默忽略，而不是报错。注意 `X::mf2` 的形参类型仍受链接规格影响，`void(*)()` 是指向 C 函数的指针。

!!! pitfall "静态成员函数可以直接当 C 回调"
    按标准，静态成员函数作为类成员总是具有 C++ 语言链接。把 `&S::cb` 传给期望 `extern "C"` 函数指针的 C API（例如 `pthread_create`），按标准是类型不匹配。因为编译器都不区分，这在实践中能用；严格可移植的写法是在命名空间作用域定义一个 `extern "C"` 的转发函数。

## 直接包含的声明视为带 extern（¶8）

```cpp title="linkage-extern.cpp" error
extern "C" double f();
static double f();              // error: 与先前的外部链接不一致

extern "C" int i;               // 声明，如同 extern int i;
extern "C" {
    int i;                      // 定义
}

extern "C" static void g();     // error: 不能带存储类说明符
```

¶8 直接包含在链接规格里的声明，在确定名字的链接以及是不是定义时，视为带有 `extern` 说明符（[[dcl.stc]]），而且不能再带存储类说明符。

直接包含指的是不带花括号的形式 `extern "C" 声明`。花括号里的声明不算直接包含，所以 `extern "C" int i;` 只是声明，`extern "C" { int i; }` 却是定义。在头文件里给变量加 C 语言链接时，这个区别决定了会不会出现多重定义。

## 同一实体的声明必须一致（¶6）

```cpp title="linkage-redecl.cpp" error
extern "C" void g();
void g();                       // OK：沿用 C 语言链接
extern "C++" void g();          // error: 与先前的 C 语言链接冲突
```

¶6 同一实体的两个声明给出不同的语言链接，程序非良构。如果两个声明互相不可达，比如分别在两个翻译单元里，则不要求诊断 {{ifndr}}：编译器和链接器都可以不报告，程序的行为没有任何保证。不带链接规格的重新声明，沿用实体（以及适用时其类型）原有的语言链接。

有了这条沿用规则，头文件里的 `extern "C"` 声明配上实现文件里不带 `extern "C"` 的定义，就能正常工作：

```cpp
// c_api.h
extern "C" int api_version();
// c_api.cpp
#include "c_api.h"
int api_version() { return 3; }   // C 语言链接，符号是未修饰的 api_version
```

反过来，如果实现文件忘了包含头文件，这个定义就是另一个具有 C++ 语言链接的函数，符号名是修饰过的。别的翻译单元按 C 语言链接调用 `api_version` 时，链接器报告未定义的符号。这就是互不可达时不要求诊断的实际样子：编译器看不到冲突，往往只有链接器能发现。

## C 函数不分命名空间（¶7）

```cpp run title="linkage-cross-ns.cpp" ok
namespace A { extern "C" int f(); }
namespace B { extern "C" int f(); }

int A::f() { return 7; }

int main() { return B::f() == 7 ? 0 : 1; }   // B::f 就是 A::f
```

¶7 两个声明引入同一个名字时，如果其中一个声明了 C 语言链接的函数或变量，另一个也声明了这样的实体，或者声明了一个属于全局作用域的变量，这两个声明就声明同一个实体。

C 的外部名字是扁平的，没有命名空间，所以 C 语言链接的同名函数或变量，无论声明在哪个命名空间，都是同一个实体。[[namespace.udir#7]] 的例子里 `g()` 没有歧义，原因就在这里。标准例 4：

```cpp title="linkage-same-entity.cpp" error
int x;
namespace A {
    extern "C" int f();
    extern "C" int g() { return 1; }
    extern "C" int h();
    extern "C" int x();               // error: 与全局变量 x 同名
}

namespace B {
    extern "C" int f();               // A::f 和 B::f 是同一个函数
    extern "C" int g() { return 1; }  // error: C 语言链接的 g 有两个定义
}

int A::f() { return 98; }             // C 语言链接的 f 的定义
extern "C" int h() { return 97; }     // 定义 h；A::h 和 ::h 是同一个函数
```

- `A::x()` 与全局变量 `x` 是同一个实体，一个是函数，一个是变量，所以非良构。规则里专门提到全局作用域的变量，是因为在主流 ABI 里全局变量的符号本来就不修饰，C++ 的全局变量 `x` 和 C 语言链接的 `x` 在符号层面无法区分。
- `B::g` 和 `A::g` 是同一个函数的两个定义，违反 ODR。两者在同一个翻译单元里，必须诊断。

由此还可以推出：C 语言链接的函数不能重载。同一作用域里参数不同的两个 `extern "C"` 同名函数声明的是同一个实体，类型却不同，所以非良构：

```cpp title="linkage-no-overload.cpp" error
extern "C" int over(int);
extern "C" int over(double);    // error: 同一实体，类型冲突
```

## 跨语言的边界（¶9、¶10）

¶9 注 5：语言链接是函数类型的一部分，所以通过指向 C 函数的指针调用时，被调用的函数被视为 C 函数。

¶10 从 C++ 链接到其他语言定义的实体，或者反过来，是实现定义的，并且依赖于具体语言 {{impl}}。只有两种语言实现的对象布局策略足够相似时，这种链接才可能实现。

也就是说，`extern "C"` 只保证名字和调用层面的对接。结构体布局是否与 C 编译器一致、`bool` 与 `_Bool` 是否兼容、异常能否穿过 C 的栈帧，都由实现决定。实践中，平台 ABI 保证标准布局类型与 C 结构体的布局一致，例如 Linux 上的 Itanium C++ ABI 加 System V psABI，Windows 上的 Microsoft x64 ABI。

## 实现视角

!!! impl "符号名"
    - Itanium ABI 平台上，C 语言链接的函数和变量用未修饰的名字，macOS 还会统一加一个前导下划线。C++ 语言链接的函数用 `_Z` 开头的修饰名，其中编码了命名空间和参数类型。
    - MSVC 在 32 位 x86 上按调用约定给 C 函数的符号加 `_` 前缀或 `@n` 后缀，x64 上基本不修饰；C++ 名字用 `?` 开头的修饰。
    - C 语言链接的符号里没有参数类型，链接器发现不了声明为 `int f(int)`、定义为 `int f(double)` 这类错误。这是与 C 互操作时最危险的一类问题。

!!! impl "模板必须是 C++ 语言链接"
    在 `extern "C" { }` 里包含 C++ 头文件时，其中的模板会出问题：本机 Clang 23 对 `extern "C" { template<class T> void f(T); }` 报错 "templates must have C++ linkage"，GCC 同样拒绝。较早的标准明文规定模板不得具有 C 语言链接；当前草案里能看到的相关措辞是模板声明里的声明不能是链接规格（[[temp.pre]]）。需要时可以在里面嵌套 `extern "C++" { }` 恢复 C++ 语言链接。

## 常见误解

!!! pitfall "extern \"C\" 让函数按 C 编译"
    函数体仍然按 C++ 编译，可以用模板、抛异常、调用重载函数，只是函数本身的名字按 C 的约定导出。让异常从 `extern "C"` 函数传播到 C 调用方，结果由实现决定，后果通常和未定义行为一样严重。

!!! pitfall "可以在不同命名空间各写一份同名的 C 接口"
    不行。按第 7 段它们是同一个实体：两个定义会冲突，两个声明会悄悄合并成一个。

!!! pitfall "extern \"C\" int i; 是定义"
    不带花括号的形式视为带 `extern`，只是声明（第 8 段），必须在某处另行定义。

## 思考题

!!! question "思考题 1"
    下面每个函数有什么语言链接？它们的函数类型呢？

    ```cpp
    extern "C" {
        static int s();
        namespace N { int t(); }
        struct S { static int u(); };
    }
    ```

<details markdown="1">
<summary>答案</summary>

- `s`：名字有内部链接，所以没有语言链接；它的函数类型有 C 语言链接，与例 2 的 `f4` 相同。
- `N::t`：链接规格不建立作用域，里面可以有命名空间定义。`t` 有外部链接，所以它和它的类型都有 C 语言链接。按第 7 段，它与任何命名空间里的 `extern "C" int t()` 都是同一个函数。
- `S::u`：类成员忽略 C 语言链接，所以 `u` 有 C++ 语言链接。但第 5 段只对非静态成员函数的函数类型忽略 C 语言链接，`u` 是静态成员函数，按字面规则它的函数类型有 C 语言链接。由于编译器都不区分函数类型的语言链接，这一点在实践中观察不到。
</details>

!!! question "思考题 2"
    为什么第 7 段把全局作用域的变量也算进同一实体的判断，却不算全局作用域的 C++ 函数？

<details markdown="1">
<summary>答案</summary>

函数可以靠重载区分：`extern "C" int f(int);` 和全局的 `int f(double);` 是两个函数，后者的符号是修饰过的。变量不能重载，而且主流 ABI 里全局变量的符号本来就不修饰，与 C 语言链接的同名实体在符号层面无法区分。如果允许 `namespace A { extern "C" int x(); }` 和全局的 `int x;` 作为两个实体共存，链接器会看到两个同名符号。所以标准把它们规定为同一个实体，再由类型不一致得出非良构。
</details>
