---
title: 弃用的核心语言特性（D.2–D.9）
summary: Annex D 中的 8 项核心语言弃用：非局部声明暴露 TU 局部实体、[=] 隐式捕获 *this、volatile 的自增/链式赋值/形参/返回类型/结构化绑定、省略号前缺逗号、隐式定义的复制操作、static constexpr 成员的类外重声明、operator "" _x 中的空格、无实参列表的 template 前缀。每项给出规则、动机、改写方法与 Clang 23 实际发出的警告。
status: draft
covers: depr.capture.this, depr.volatile.type, depr.ellipsis.comma, depr.impldec, depr.static.constexpr, depr.lit, depr.template.template
related: depr, basic.link, expr.prim.lambda, expr.assign, dcl.fct, class.copy.ctor, class.copy.assign, over.literal, temp.names
tags: 附录, 弃用, 兼容性
updated: 2026-10-18
---

这一页是 [[depr]] 的核心语言部分，对应 Annex D 的 D.2 到 D.9。这些规则本身大多写在正文里，正文在对应位置用"is deprecated ([depr.xxx])"指过来；Annex D 这一侧给出的是例子和"为了兼容而保留"的说明。

每一节都附有 Clang 23.1.3 的实测输出（`-fsyntax-only`，按需加 `-Wdeprecated`），路径和列号已删去。

## D.2 非局部使用 TU 局部实体 {#depr.local}

**[depr.local] ¶1**：一个**非 TU 局部**实体的声明，如果是一个**暴露**（[[g:exposure]]，见 [[basic.link]]），则已弃用。在可导入的模块单元中，这样的声明是非良构的。

先看术语。**TU 局部**（[[g:tu-local]]）实体大致是"只在本翻译单元内有意义"的东西：有内部链接的函数和变量、无名命名空间中的类型、仅在本 TU 中可见的 lambda 闭包类型等。一个声明如果**命名**了 TU 局部实体（不算非内联函数的函数体、非内联变量的初始化器等"不会泄露出去"的部分），就构成一个暴露。

```cpp
namespace {
  struct A {
    void f() {}
  };
}
A h();                          // 弃用：h 不是内部链接，却在签名中暴露了 TU 局部的 A
inline void g() { A().f(); }    // 弃用：g 是内联函数且不是内部链接，函数体会被其他 TU 看到
```

为什么要弃用？`h` 有外部链接，理论上其他 TU 可以声明并调用它；但它的返回类型 `A` 在每个 TU 里都是不同的类型（无名命名空间），别的 TU 根本写不出一个与之匹配的声明。`g` 更隐蔽：内联函数的定义要求在每个 TU 中完全相同（ODR），而每个 TU 的 `A` 都是不同的实体，`g` 在不同 TU 中的定义实际上引用了不同的类型，这是 ODR 违规。在模块里这类问题会被直接拒绝；在传统头文件模型里，委员会选择先弃用，因为现存代码中这种写法太多了。

**Clang 23 实测**：`-std=c++2c -Wall -Wextra -Wdeprecated` 下没有任何关于暴露的诊断（只有一条 `h` 未使用的警告）。

**改写**：把 `A` 移出无名命名空间（给它外部链接），或者把 `h`、`g` 声明为 `static` / 放进同一个无名命名空间。

## D.3 隐式按引用捕获 `*this` {#depr.capture.this}

**[depr.capture.this] ¶1**：为了与以前的版本兼容，*capture-default* 为 `=` 的 lambda 表达式可以隐式按引用捕获 `*this`（见 [[expr.prim.lambda.capture]]）。

```cpp
struct X {
  int x;
  void foo(int n) {
    auto f = [=]() { x = n; };          // 弃用：x 是 this->x，不是 x 的副本
    auto g = [=, this]() { x = n; };    // 推荐的替代写法
  }
};
```

问题出在 `[=]` 的字面含义是"按值捕获"，读者会以为 `x` 被复制了一份，lambda 改的是副本。实际上被捕获的是 `this` 指针，`x = n` 修改的是原对象。如果 lambda 活得比对象长（存进回调、交给另一个线程），就是悬空指针。C++20 要求把这件事写出来：`[=, this]` 表示"按引用捕获对象"，`[=, *this]`（C++17 起）表示"复制整个对象"。

**Clang 23 实测**：

```text
$ clang++ -std=c++20 -fsyntax-only d_this.cpp
warning: implicit capture of 'this' with a capture default of '=' is deprecated [-Wdeprecated-this-capture]
$ clang++ -std=c++17 -fsyntax-only d_this.cpp
warning: explicit capture of 'this' with a capture default of '=' is a C++20 extension [-Wc++20-extensions]
```

默认开启。注意第二条：`[=, this]` 在 C++17 中是非良构的（Clang 作为扩展接受）。需要同时兼容 C++17 和 C++20 时，改用不带默认捕获的显式列表，如 `[this, n]`。

## D.4 弃用的 `volatile` 类型用法 {#depr.volatile.type}

C++20 对 `volatile` 做了一次清理，把几种语义含糊、几乎总是误用的写法列为弃用。`volatile` 的正当用途（映射硬件寄存器的内存、与信号处理函数共享的 `sig_atomic_t`、`setjmp` 前后的局部变量）只需要"每次访问都真正读/写内存"这一种语义，这几种写法要么隐含了"读-改-写是一个操作"的错误暗示，要么对 `volatile` 毫无意义。

**¶1** `volatile` 限定的算术类型和指针类型上的前缀、后缀 `++` 和 `--` 已弃用（[[expr.post.incr]]、[[expr.pre.incr]]）。`++v` 实际上是"读、加一、写"三步，不是原子的，也不是一次访问，写成 `++` 让人误以为它是。

**¶2** 左操作数为 `volatile` 限定的非类类型的某些赋值已弃用，见 [[expr.assign]]：按当前草案 [[expr.assign#5]]，当赋值表达式的**结果被使用**（它不是弃值表达式，也不是不求值操作数）时，弃用。`tail = v = neck` 里，`v = neck` 的结果是 `v` 的左值，`tail` 的值到底来自 `neck` 还是来自重新读一次 `v`？不同的人有不同的预期。

```cpp
int neck, tail;
volatile int brachiosaur;
brachiosaur = neck;          // OK
tail = brachiosaur;          // OK
tail = brachiosaur = neck;   // 弃用：使用了对 volatile 赋值的结果
brachiosaur += neck;         // OK
```

复合赋值的历史有点曲折：C++20 把对 `volatile` 左值的所有复合赋值（`+=`、`|=` 等）都列为弃用；C++23 撤销了其中按位复合赋值（`|=`、`&=`、`^=`）的弃用，因为嵌入式代码里大量用它们操作寄存器的位。当前草案的规则只看"结果是否被使用"，`brachiosaur += neck;` 作为一条独立的语句不再弃用。

**¶3** 形参为 `volatile` 限定类型、或返回类型为 `volatile` 限定的**函数类型**已弃用（[[dcl.fct]]）。按值传递的形参和返回值都是副本，`volatile` 限定在调用者一侧完全没有意义（形参的顶层 cv 限定甚至不属于函数类型）。指向 `volatile` 的指针形参不受影响：

```cpp
volatile struct amber jurassic();                               // 弃用
void trex(volatile short left_arm, volatile short right_arm);   // 弃用
void fly(volatile struct pterosaur* pteranodon);                // OK
```

**¶4** `volatile` 限定类型的结构化绑定已弃用（[[dcl.struct.bind]]）。结构化绑定引入的名字是隐藏对象的成员的别名，`volatile` 限定的是那个隐藏对象，再经过元组协议时语义不清。

```cpp
struct linhenykus { short forelimb; };
void park(linhenykus alvarezsauroid) {
  volatile auto [what_is_this] = alvarezsauroid;   // 弃用
}
```

**Clang 23 实测**（`-std=c++20` 与 `-std=c++2c` 相同，默认开启）：

```text
warning: increment of object of volatile-qualified type 'volatile int' is deprecated [-Wdeprecated-volatile]
warning: use of result of assignment to object of volatile-qualified type 'volatile int' is deprecated [-Wdeprecated-volatile]
warning: volatile-qualified return type 'volatile amber' is deprecated [-Wdeprecated-volatile]
warning: volatile-qualified parameter type 'volatile short' is deprecated [-Wdeprecated-volatile]
warning: volatile qualifier in structured binding declaration is deprecated [-Wdeprecated-volatile]
```

`-std=c++17` 下这些全部没有警告。复合赋值（包括 `int x = (v += 1);` 这种使用了结果的写法）在 C++20 模式下也没有警告。

**改写**：`++v` → `v = v + 1`（明确是一次读、一次写）；链式赋值拆成两条语句；删掉形参和返回类型上的 `volatile`。

## D.5 省略号前缺少逗号的形参声明子句 {#depr.ellipsis.comma}

**[depr.ellipsis.comma]**：形如 *parameter-declaration-list* `...`（省略号前没有逗号）的 *parameter-declaration-clause* 已弃用（[[dcl.fct]]）。

```cpp
void f(int...);       // 弃用：等价于 void f(int, ...)
void g(auto...);      // OK：声明一个函数形参包
void h(auto......);   // 弃用：形参包后面又跟了一个 C 风格的省略号
```

这条弃用是为了消除歧义。`int...` 是 C++ 从早期就允许的写法，意思是 C 风格可变参数；但模板形参包也用 `...`，`void g(T...)` 是形参包，`void f(int...)` 是可变参数，只靠一个类型是否是包来区分，读者很容易混淆。`auto......` 更是两种含义叠在一起。要求 C 风格省略号前必须有逗号之后，`...` 紧贴类型就只表示包展开。这也是 C 语言的写法（C 一直要求逗号）。

**Clang 23 实测**：

```text
$ clang++ -std=c++2c -fsyntax-only d_ell.cpp
warning: declaration of a variadic function without a comma before '...' is deprecated [-Wdeprecated-missing-comma-variadic-parameter]
warning: declaration of a variadic function without a comma before '...' is deprecated [-Wdeprecated-missing-comma-variadic-parameter]
warning: '...' in this location creates a C-style varargs function [-Wambiguous-ellipsis]
note: insert ',' before '...' to silence this warning
```

前两条分别对应 `f` 和 `h`，C++26 模式下默认开启；`-std=c++20` 下只有针对 `h` 的 `-Wambiguous-ellipsis`。

**改写**：加逗号：`void f(int, ...)`、`void h(auto..., ...)`。

## D.6 隐式定义的复制函数 {#depr.impldec}

**[depr.impldec] ¶1**：

- 如果类有用户声明的**复制赋值运算符**或用户声明的**析构函数**，那么把复制构造函数隐式定义为默认的做法已弃用；
- 如果类有用户声明的**复制构造函数**或用户声明的**析构函数**，那么把复制赋值运算符隐式定义为默认的做法已弃用。

将来的版本可能把这些隐式定义改成**删除**（[[dcl.fct.def.delete]]）。

这就是"三法则"（rule of three）的标准化表述：一个类既然需要自定义析构函数或其中一个复制操作，几乎可以肯定它管理着某种资源，编译器生成的逐成员复制大概率是错的（双重释放、浅拷贝）。C++11 引入移动语义时就规定：用户声明了复制操作或析构函数的类，不再隐式声明移动操作；复制操作则出于兼容考虑仍然隐式生成，但列为弃用。

```cpp
struct S {
  int* p;
  ~S() { delete p; }   // 用户提供的析构函数
};
void f() {
  S a{new int};
  S b = a;   // 弃用：隐式复制构造函数；b.p 与 a.p 指向同一块内存，析构时双重释放
}
```

**Clang 23 实测**：默认不警告。`-Wextra` 只开启"有用户**提供**的复制操作"的那一半；析构函数那一半要 `-Wdeprecated`：

```text
$ clang++ -std=c++2c -fsyntax-only -Wextra d_impl.cpp
warning: definition of implicit copy constructor for 'T' is deprecated because it has a user-provided copy assignment operator [-Wdeprecated-copy-with-user-provided-copy]
$ clang++ -std=c++2c -fsyntax-only -Wdeprecated d_impl.cpp
warning: definition of implicit copy constructor for 'S' is deprecated because it has a user-provided destructor [-Wdeprecated-copy-with-user-provided-dtor]
warning: definition of implicit copy assignment operator for 'S' is deprecated because it has a user-provided destructor [-Wdeprecated-copy-with-user-provided-dtor]
```

如果析构函数只是**用户声明**而不是用户提供（`~S() = default;`），对应的警告是 `-Wdeprecated-copy-with-dtor`，同样由 `-Wdeprecated` 开启。

**改写**：遵循"三/五/零法则"。确实需要逐成员复制的，显式写 `S(const S&) = default;`、`S& operator=(const S&) = default;`；管理资源的，用 `std::unique_ptr` 之类的成员，让类根本不需要自定义析构函数（零法则）。

## D.7 `static constexpr` 数据成员的重声明 {#depr.static.constexpr}

**[depr.static.constexpr] ¶1**：为了与以前的版本兼容，`constexpr` 静态数据成员可以在类外被冗余地重新声明，不带初始化器（[[basic.def]]、[[class.static.data]]）。这种用法已弃用。

```cpp
struct A {
  static constexpr int n = 5;   // 定义（C++14 中只是声明）
};
constexpr int A::n;             // 冗余的声明（C++14 中是定义）
```

C++17 让 `constexpr` 静态数据成员隐式成为 **inline 变量**（[[dcl.inline]]），类内的那一行本身就是定义。在 C++14 中它只是声明，一旦 `A::n` 被 odr-use（比如绑定到 `const int&`），就必须在某个 `.cpp` 里写一次类外定义，否则链接失败。C++17 之后那行类外定义变得多余，但为了让老代码继续编译，标准允许它作为一个冗余声明存在。

**Clang 23 实测**：需要 `-Wdeprecated`：

```text
$ clang++ -std=c++17 -fsyntax-only -Wdeprecated d_sc.cpp
warning: out-of-line definition of constexpr static data member is redundant in C++17 and is deprecated [-Wdeprecated-redundant-constexpr-static-def]
```

**改写**：删掉类外的那一行。需要同时支持 C++14 时，用 `#if __cplusplus < 201703L` 包起来。

## D.8 使用标识符的字面量运算符函数声明 {#depr.lit}

**[depr.lit] ¶1**：形如 `operator` *unevaluated-string* *identifier* 的 *literal-operator-id*（[[over.literal]]）已弃用。也就是 `operator "" _km` 这种在 `""` 与后缀名之间有空白的写法；推荐的写法是 `operator""_km`（此时 `""_km` 是一个 *user-defined-string-literal* 记号）。

```cpp
long double operator"" _km(long double);   // 弃用
long double operator""_m(long double);     // OK
```

弃用的原因在保留名规则上：带空格的形式中，`_km` 是一个独立的标识符，受 [[lex.name]] 的保留规则约束——以下划线加大写字母开头的名字（如 `_KM`）是保留给实现的，用户写 `operator "" _KM` 就是 IFNDR。而无空格的形式中，后缀是 *ud-suffix* 的一部分，不受这条规则约束。两种写法应当等价，却因为一个空格适用不同的规则，于是委员会弃用了带空格的那种。

**Clang 23 实测**：默认开启，`-std=c++17` 起即警告：

```text
warning: identifier '_km' preceded by whitespace in a literal operator declaration is deprecated [-Wdeprecated-literal-operator]
```

**改写**：删掉空格。注意标准库自己的后缀（`operator""s`、`operator""ms`）一直是无空格的写法。

## D.9 限定名前的 `template` 关键字 {#depr.template.template}

**[depr.template.template] ¶1**：在**类模板或别名模板**的有限定名字前使用 `template` 关键字、而后面**没有**模板实参列表，已弃用（[[temp.names]]）。

```cpp
template<template<class> class TT> struct W {};
namespace N { template<class T> struct V {}; }

W<N::template V> w;   // 弃用：N::V 不是依赖名，也没有 <...>，template 是多余的
W<N::V> w2;           // OK
```

`template` 消歧义符的本意是在**依赖**的限定名中告诉编译器"后面的 `<` 是模板实参列表的开始"，如 `T::template apply<int>`。当后面根本没有 `<` 时（例如把模板本身作为模板模板实参传递），这个关键字不起消歧义的作用。正文 [[temp.names#11]] 规定：带 `template` 前缀的名字要么后跟模板实参列表，要么指称类模板或别名模板，**后一种情况已弃用**。

值得注意的是，这条弃用**不区分依赖与否**。[[temp.names]] 的例子明确把依赖名也算进去：

```cpp
template <class T> struct B {
  template <class T2> struct C { };
};

// 弃用：T::C 被假定为指称一个类模板
template <class T, template <class X> class TT = T::template C> struct D { };
D<B<int>> db;
```

**Clang 23 实测**：上面两个例子在 `-Wall -Wextra -Wdeprecated -pedantic` 下都没有诊断。反过来，如果把依赖情形中的 `template` 去掉（`TT = T::C`），Clang 在 `-std=c++20` 和 `-std=c++2c` 下都报 `default template argument for a template template parameter must be a class template`。也就是说，对依赖名而言，目前在 Clang 上**只有被弃用的写法能用**。

**改写**：非依赖名删掉多余的 `template` 即可。依赖名作模板模板实参的情形暂时没有可移植的替代写法，保持现状，等编译器跟进。

## 小结

| 条款 | Clang 23 默认警告？ | 需要的选项 |
|---|---|---|
| D.2 暴露 TU 局部实体 | 否 | 无 |
| D.3 `[=]` 捕获 `this` | 是（C++20 起） | — |
| D.4 `volatile` | 是（C++20 起） | — |
| D.5 `int...` | 是（C++26 模式） | — |
| D.6 隐式复制操作 | 否 | `-Wextra`（复制操作那一半）、`-Wdeprecated`（析构函数那一半） |
| D.7 `static constexpr` 重声明 | 否 | `-Wdeprecated` |
| D.8 `operator "" _x` | 是 | — |
| D.9 多余的 `template` | 否 | 无 |
