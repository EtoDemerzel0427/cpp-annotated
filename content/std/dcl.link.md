---
title: 链接规格
summary: 语言链接是函数、变量和函数类型的属性；extern "C"/"C++" 链接规格可嵌套、不建立作用域；C 语言链接的同名函数/变量跨命名空间是同一个实体；函数类型的语言链接按标准是类型的一部分，但主流编译器都不区分
status: done
related: basic.link, dcl.stc, dcl.fct, namespace.udir, lex.string.uneval, module.import, alg.c.library
tags: 链接, extern "C", ABI, 互操作
updated: 2026-10-17
---

C++ 程序几乎总要和 C 代码打交道：调用 C 库、被 C 代码回调、导出 C 接口给其他语言。同一个函数在目标文件中如何表示，两种语言的做法不同：C++ 有命名空间和重载，需要名字修饰（name mangling），C 则没有。**链接规格**（linkage specification）`extern "C"` 的作用就是告诉编译器，这个声明按 C 语言的约定处理。

标准用[[g:language-linkage|语言链接]]（language linkage）这个抽象概念来描述它，刻意不提名字修饰、调用约定这些实现细节。本页覆盖 [dcl.link] 全部 10 段。有两个经常混淆的概念需要区分：

- 链接（linkage，[[basic.link]]）：名字能否在别的作用域或翻译单元中指代同一个实体（外部 / 模块 / 内部 / 无链接）；
- 语言链接（本节）：实体或函数类型按哪种语言的约定与外界连接（C++ / C / 实现定义的其他语言）。

两者正交。`extern "C" { static void f(); }` 中的 `f` 具有内部链接，因此没有语言链接，但它的函数类型仍有 C 语言链接（见 ¶5 例 2）。

## 什么东西有语言链接（¶1）

¶1 的内容如下：

- 名字具有外部链接的所有函数和变量，以及所有函数类型，都有语言链接；
- 注 1：语言链接所关联的一些性质是实现特定的，例如外部名字的表示形式、调用约定等，标准不加描述；
- 函数类型、函数、变量的默认语言链接是 C++ 语言链接；
- **两个仅语言链接不同的函数类型是不同的类型**。

!!! std
    Two function types with different language linkages are distinct types even if they are otherwise identical.

    两个函数类型语言链接不同就是不同的类型，即使其余部分完全相同。

为什么要让语言链接成为类型的一部分？因为 C 和 C++ 的调用约定可能不同（例如某个平台上 C 函数由调用方清理栈，C++ 函数由被调方清理）。如果把一个 C++ 函数的指针交给 C 代码去调用，调用方式就错了。把语言链接放进类型，编译器就可以在类型检查时拒绝这种混用。

!!! impl "实际上没有编译器这样做"
    GCC、Clang、MSVC 都不把语言链接视为函数类型的一部分。在它们支持的所有平台上，C 和 C++ 的调用约定相同，区分类型只会带来麻烦（例如 `qsort` 无法直接接受由 lambda 转换来的函数指针）。所以下面的程序按标准应当良构（两个 `take` 是重载），但在三大编译器上 `static_assert` 都会失败，第二个 `take` 被当作重声明：

    ```cpp
    extern "C" typedef void cfn();
    typedef void cppfn();
    void take(cfn*);
    void take(cppfn*);                 // 标准：重载；编译器：重声明
    #include <type_traits>
    static_assert(!std::is_same_v<cfn, cppfn>);   // 标准：成立；Clang 23：失败
    ```

    （据记载，历史上 Sun/Oracle Studio 的 C++ 编译器曾区分过这两种类型，并对混用给出警告。）标准库为此在 [[alg.c.library]] 中规定，`qsort` 和 `bsearch` 必须同时提供接受 C 语言链接比较函数和 C++ 语言链接比较函数的版本，否则按标准，把普通的 C++ 函数传给 `std::qsort` 就是类型错误。

## 语法与支持的语言（¶2–¶4）

```text
linkage-specification:
    extern unevaluated-string { declaration-seq(opt) }
    extern unevaluated-string name-declaration
```

¶2 的内容如下：

- 字符串是一个不求值字符串（unevaluated string，[[lex.string.uneval]]），不能带编码前缀，转义序列已被替换；
- 标准只规定 `"C"` 和 `"C++"` 的语义。其他字符串是有条件支持的，语义由实现定义 {{impl}}；
- 注 3：因此，实现不认识的语言链接必须诊断；
- 推荐做法：拼写取自定义该语言的文档，比如 `Ada`（不是 `ADA`），`Fortran` 还是 `FORTRAN` 视年代而定。

¶3 要求每个实现都必须支持 `"C"` 和 `"C++"`。

```cpp title="linkage-basic.cpp" error
struct complex { double re, im; };
complex sqrt(complex);          // 默认 C++ 语言链接
extern "C" {
    double sqrt(double);        // C 语言链接
}
extern "Ada" void ada_proc();   // error (Clang 23)：实现不认识 "Ada"
```

注意 `sqrt(complex)` 与 `sqrt(double)` 是两个重载：只要至多一个具有 C 语言链接，同名函数就可以共存。

按 ¶4，出现在非 C++ 语言链接的链接规格中的 *module-import-declaration* 是有条件支持的，语义由实现定义。（`extern "C" { import m; }` 是什么意思？标准不打算回答。）

## 嵌套、作用域与作用范围（¶5）

¶5 的内容如下：

- 链接规格可以嵌套，由最内层决定语言链接；
- 注 4：链接规格不建立作用域，`extern "C" { int x; }` 中的 `x` 就是外层命名空间的成员；
- 链接规格只能出现在命名空间作用域（函数体内、类内都不行）；
- 在链接规格中，所指定的语言链接施加于所有函数声明符的函数类型，以及名字具有外部链接的所有函数和变量。

```cpp title="linkage-nest.cpp" error
extern "C++" {
    extern "C" void inner();          // OK: 最内层是 "C"
}
extern "C" { int x_in_global; }       // x_in_global 是全局命名空间的成员
int* p = &::x_in_global;              // OK

void blk() {
    extern "C" void nope();           // error: 链接规格不能出现在块作用域
}
```

标准例 2 展示了实体的语言链接与类型的语言链接如何分离：

```cpp title="linkage-types.cpp" ok
extern "C"
    void f1(void (*pf)(int));   // f1 及其函数类型有 C 语言链接；pf 是指向 C 函数的指针

extern "C" typedef void FUNC();
FUNC f2;                        // f2 本身有 C++ 语言链接，但它的类型有 C 语言链接

extern "C" FUNC f3;             // f3 及其类型都有 C 语言链接

void (*pf2)(FUNC*);             // 变量 pf2 有 C++ 语言链接；类型是
                                // "指向 C++ 函数的指针，该函数接受一个指向 C 函数的指针"
extern "C" {
    static void f4();           // f4 的名字有内部链接 ⇒ 没有语言链接；但其类型有 C 语言链接
}

extern "C" void f5() {
    extern void f4();           // OK: 名字链接（内部）和类型的语言链接（C）沿用先前声明
}
extern void f4();               // OK: 同上
void f6() {
    extern void f4();           // OK: 同上
}

static void f4() {}             // 补上定义
int main() {}
```

要让 C 语言链接的函数类型脱离具体函数而存在（比如声明一个 C 回调类型），唯一的办法是把 `typedef` 与链接规格组合起来。

### 类成员忽略 C 语言链接

¶5 最后一句规定，确定以下事物的语言链接时，忽略 C 语言链接：

- 类成员；
- 带尾随 requires 子句的友元函数；
- 非静态成员函数的函数类型。

```cpp title="linkage-members.cpp" ok
extern "C" typedef void FUNC_c();

class C {
    void mf1(FUNC_c*);          // mf1 及其类型有 C++ 语言链接；形参是"指向 C 函数的指针"
    FUNC_c mf2;                 // mf2 及其类型有 C++ 语言链接
    static FUNC_c* q;           // 数据成员 q 有 C++ 语言链接；类型是"指向 C 函数的指针"
};

extern "C" {
    class X {
        void mf();              // mf 及其类型有 C++ 语言链接
        void mf2(void(*)());    // mf2 有 C++ 语言链接；形参类型是"指向 C 函数的指针"
    };
}

int main() {}
```

这样规定的原因是：成员函数属于类，C 代码根本无法直接调用它（C 没有 `this`，也没有类作用域），给它 C 语言链接没有意义；而 `extern "C" { #include "c_header.h" }` 这种包含结构体定义的写法又极其普遍，所以标准选择静默忽略，而不是报错。注意 `mf2` 的形参类型仍然受链接规格影响：`void(*)()` 是指向 C 函数的指针。

!!! pitfall "静态成员函数不能作为 C 回调"
    按标准，作为类成员的 `static void cb(int)` 总是具有 C++ 语言链接，其类型是 C++ 函数。把 `&S::cb` 传给期望 `extern "C"` 函数指针的 C API（比如 `pthread_create`），按标准是类型不匹配。由于编译器都不区分，这在实践中能用；严格可移植的写法是在命名空间作用域定义一个 `extern "C"` 的转发函数。

## 一致性（¶6）

按 ¶6，如果同一实体的两个声明给出不同的语言链接，程序非良构；如果两个声明互相不可达，则不要求诊断（IFNDR {{ifndr}}）。不带链接规格的重声明继承该实体（以及适用时其类型）的语言链接。

```cpp title="linkage-redecl.cpp" error
extern "C" void g();
void g();                       // OK: 继承 C 语言链接
extern "C++" void g();          // error: 与先前的 C 语言链接冲突
```

有了继承规则，头文件里的 `extern "C"` 声明配上实现文件里不带 `extern "C"` 的定义，就能正常工作：

```cpp
// c_api.h
extern "C" int api_version();
// c_api.cpp
#include "c_api.h"
int api_version() { return 3; }   // C 语言链接，导出的符号是未修饰的 api_version
```

反之，如果实现文件忘了包含头文件，定义就是 C++ 语言链接的另一个函数（修饰名不同），别的 TU 按 C 链接调用时会得到未定义符号的链接错误。不可达则不要求诊断，在现实中就是这个样子：编译器看不到冲突，只有链接器能发现。

## C 语言链接的实体没有命名空间（¶7）

按 ¶7，如果两个声明（重新）引入同一个名字，其中一个声明了 C 语言链接的函数或变量，另一个也声明了这样的实体，或者声明了一个属于全局作用域的变量，那么这两个声明声明的是同一个实体。

换句话说，**C 语言链接的函数/变量，不管声明在哪个命名空间，同名就是同一个实体**，因为 C 的外部名字空间是扁平的。

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
    extern "C" int g() { return 1; }  // error: C 语言链接的函数 g 有两个定义
}

int A::f() { return 98; }             // C 语言链接函数 f 的定义
extern "C" int h() { return 97; }     // C 语言链接函数 h 的定义；A::h 和 ::h 是同一个函数
```

- `A::x()` 与全局变量 `x` 冲突：在 C 的符号表里它们都叫 `x`，一个是函数，一个是变量，无法共存。规则中“或者声明了一个属于全局作用域的变量”这一条就是为此而设的：在 Itanium ABI 中，全局变量的修饰名恰好也是未修饰的 `x`。
- `B::g` 的定义与 `A::g` 的定义是同一个函数的两个定义，违反 ODR，并且必须诊断（同一 TU 中）。

```cpp run title="linkage-cross-ns.cpp" ok
namespace A { extern "C" int f(); }
namespace B { extern "C" int f(); }

int A::f() { return 7; }

int main() { return B::f() == 7 ? 0 : 1; }   // B::f 就是 A::f
```

这也是 [[namespace.udir#7]] 例子中 `g()` 不歧义的原因。

另一个后果是 **C 语言链接的函数不能重载**。同一作用域中两个参数不同的 `extern "C"` 同名函数声明的是同一个实体，类型却不同，因此非良构：

```cpp title="linkage-no-overload.cpp" error
extern "C" int over(int);
extern "C" int over(double);    // error: 同一实体，类型冲突
```

## 链接规格中的声明视为带 `extern`（¶8）

按 ¶8，直接包含在链接规格中的声明，在确定名字的链接以及是否为定义时，视为带有 `extern` 说明符（[[dcl.stc]]）。这样的声明不得带存储类说明符。

注意“直接包含”的含义：花括号形式 `extern "C" { ... }` 中的声明不算直接包含，花括号里的声明是 *declaration-seq* 的成员。两者的区别正好体现在变量上：

```cpp title="linkage-extern.cpp" error
extern "C" double f();
static double f();              // error: 先前声明不是 static（链接不一致）

extern "C" int i;               // 声明（视为 extern int i;）
extern "C" {
    int i;                      // 定义
}

extern "C" static void g();     // error: 直接包含的声明不能带存储类说明符
```

所以 `extern "C" int i;` 只是声明，而 `extern "C" { int i; }` 是定义。头文件中给变量加 C 链接时，这个区别决定了会不会产生多重定义。

## 通过指针调用（¶9）与跨语言链接（¶10）

¶9 是一条注：由于语言链接是函数类型的一部分，通过指向 C 函数的指针间接调用时，得到的左值所指代的函数被视为 C 函数。

按 ¶10，从 C++ 链接到用其他语言定义的实体，以及从其他语言链接到用 C++ 定义的实体，是**实现定义且依赖于语言**的 {{impl}}。只有当两种语言实现的对象布局策略足够相似时，这种链接才可能实现。

¶10 坦白地划清了界限：`extern "C"` 只保证名字和调用层面的对接；`struct` 的布局是否与 C 编译器一致、`bool` 和 `_Bool` 是否兼容、异常能否穿越 C 栈帧，全都由实现决定。实践中，平台 ABI（Itanium C++ ABI + System V psABI，或 Microsoft x64 ABI）保证了标准布局类型与 C 结构体的布局一致。

## 实现视角

!!! impl "名字修饰与符号"
    - 在 Itanium ABI 平台上，C 语言链接的函数/变量使用未修饰的名字（macOS 上还会加前导下划线，这是平台对 C 符号的统一约定）；C++ 语言链接的函数使用 `_Z` 开头的修饰名，其中编码了命名空间、参数类型等。全局变量在 Itanium ABI 中本来就不修饰，¶7 让全局作用域的变量与 C 链接实体冲突，背景就在这里。
    - MSVC 中 C 函数的符号在 x86 上根据调用约定加 `_` 或 `@n` 后缀，x64 上基本未修饰；C++ 名字用 `?` 开头的修饰。
    - 由于 C 语言链接的名字没有参数类型信息，链接器无法发现声明为 `int f(int)` 而定义为 `int f(double)` 这类错误，这是 C 互操作中最危险的一类 bug。

!!! impl "常见惯用法"
    ```cpp
    #ifdef __cplusplus
    extern "C" {
    #endif
    int c_api(int);
    #ifdef __cplusplus
    }
    #endif
    ```
    C 头文件用它同时服务两种语言。反过来，如果 C++ 中需要在 `extern "C"` 区块里包含 C++ 头文件（例如模板），可以嵌套 `extern "C++" { ... }` 恢复 C++ 链接。这对模板尤其必要：Clang 对 `extern "C" { template<class T> void f(T); }` 报错 "templates must have C++ linkage"，GCC 也同样拒绝（较早的标准明文规定模板不得具有 C 语言链接；当前草案 [[temp.pre]] 中可见的相关措辞是模板声明内的声明不得是链接规格）。

## 陷阱

!!! pitfall "`extern “C”` 不会让代码变成 C"
    函数体仍然按 C++ 编译，可以抛异常、使用模板、重载其他函数，只是这个函数本身的名字按 C 约定导出。但让异常从 `extern "C"` 函数传播到 C 调用方，行为取决于实现（后果通常和 UB 一样严重）。

!!! pitfall "两个命名空间里的 `extern “C”` 同名函数是同一个"
    无法在不同命名空间各写一份同名 C 接口：它们要么冲突（两个定义），要么悄悄合并（两个声明）。

!!! pitfall "`extern “C” int i;` 不是定义"
    单声明形式等价于 `extern`，必须在某处另行定义。

## 思考题

!!! question "思考题 1"
    下面每个实体的语言链接是什么？函数类型的语言链接又是什么？

    ```cpp
    extern "C" {
        static int s();
        namespace N { int t(); }
        struct S { static int u(); };
    }
    ```

<details markdown="1">
<summary>答案</summary>

- `s`：名字有内部链接，所以没有语言链接；它的函数类型有 C 语言链接（¶5 例 2 的 `f4`）。
- `N::t`：链接规格不建立作用域，命名空间定义可以出现在其中；`t` 有外部链接，所以有 C 语言链接，其类型也是。并且按 ¶7，它与任何其他命名空间中的 `extern "C" int t()` 是同一个函数。
- `S::u`：类成员，确定其语言链接时 C 语言链接被忽略，所以 `u` 有 C++ 语言链接。但 ¶5 只对非静态成员函数的函数类型忽略 C 语言链接；`u` 是静态成员函数，它的函数类型不在豁免之列，按字面规则具有 C 语言链接。（这一区分在实践中没有可观察的效果，因为编译器都不区分函数类型的语言链接。）
</details>

!!! question "思考题 2"
    为什么 ¶7 要把属于全局作用域的变量也纳入同一实体的判断，却不纳入全局作用域的函数？

<details markdown="1">
<summary>答案</summary>

C 语言链接的函数和全局 C++ 函数可以靠重载区分：`extern "C" int f(int);` 与全局 `int f(double);` 是两个不同的函数（后者有修饰名）。但变量不能重载，而且在主流 ABI 中全局作用域的 C++ 变量本来就使用未修饰的名字，与 C 链接的同名实体在符号层面无法区分；如果允许 `namespace A { extern "C" int x(); }` 与全局 `int x;` 作为两个实体共存，链接器会看到两个同名符号。所以标准规定它们是同一个实体，再由类型不一致导致非良构。
</details>

## 小结

!!! summary "要点"
    - 语言链接 ≠ 链接。有外部链接的函数/变量以及所有函数类型都有语言链接；默认是 C++。
    - 按标准，语言链接是函数类型的一部分；主流编译器都不区分，这是标准与实践之间长期存在的分歧。
    - 链接规格可嵌套、不建立作用域、只能在命名空间作用域；直接包含的声明视为 `extern`，花括号中的则不是。
    - 类成员、非静态成员函数的类型、带尾随 requires 子句的友元忽略 C 语言链接。
    - C 语言链接的同名函数/变量跨命名空间是同一实体，不能重载；与全局变量同名也冲突。
    - 同一实体的语言链接必须一致；跨 TU 不一致是 IFNDR，通常表现为链接错误。
