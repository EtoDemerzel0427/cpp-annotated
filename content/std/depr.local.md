---
title: 弃用的核心语言特性（D.2–D.9）
summary: Annex D 中的 8 项核心语言弃用：隐式定义的复制操作、[=] 隐式捕获 this、volatile 的几种用法、static constexpr 成员的类外重新声明、operator "" _x 中的空白、省略号前缺逗号、多余的 template 前缀、暴露 TU 局部实体的声明；每项给出动机、改法和 Clang 23 的警告。
status: done
covers: depr.capture.this, depr.volatile.type, depr.ellipsis.comma, depr.impldec, depr.static.constexpr, depr.lit, depr.template.template
related: depr, basic.link, expr.prim.lambda, expr.assign, dcl.fct, class.copy.ctor, class.copy.assign, over.literal, temp.names
tags: 附录, 弃用, 兼容性
updated: 2026-10-19
---

!!! tldr
    - 类有用户声明的析构函数或复制操作时，编译器隐式生成的复制操作已弃用，将来可能改为删除。这是三法则的标准化表述。
    - `[=]` 隐式捕获 `this` 已弃用：`[=]` 看起来是按值捕获，实际捕获的是指针。要写成 `[=, this]` 或 `[=, *this]`。
    - `volatile` 对象的 `++`/`--`、使用对 `volatile` 赋值的结果、`volatile` 的形参、返回类型和结构化绑定都已弃用，它们要么暗示了不存在的原子性，要么毫无意义。
    - 其余几项是语法上的清理：类外重新声明 `static constexpr` 成员、`operator "" _x` 中的空白、`void f(int...)` 中缺少的逗号、后面没有实参列表的 `template` 前缀。
    - D.2、D.9 两项 Clang 不给任何警告，D.6、D.7 要加 `-Wextra` 或 `-Wdeprecated` 才有警告。

这些规则大多写在正文里，正文在相应位置注明 "is deprecated" 并指向这里；Annex D 这一侧给出例子和保留它们的理由。是否弃用、弃用意味着什么，见 [[depr]]。下文的警告都是 Clang 23.1.3 的实测结果。

## 隐式定义的复制函数 {#depr.impldec}

```cpp
struct S {
  int* p;
  ~S() { delete p; }   // 用户提供的析构函数
};
void f() {
  S a{new int};
  S b = a;   // 弃用：隐式复制构造函数
}            // b.p 与 a.p 相同，析构时重复释放
```

¶1 类有用户声明的复制赋值运算符或析构函数时，把复制构造函数隐式定义为默认的做法已弃用；类有用户声明的复制构造函数或析构函数时，把复制赋值运算符隐式定义为默认的做法已弃用。标准指出，将来的版本可能把这些隐式定义改为删除（[[dcl.fct.def.delete]]）。

这就是三法则（rule of three）：一个类需要自定义析构函数或某个复制操作，几乎一定是在管理某种资源，编译器生成的逐成员复制大概率是错的。C++11 引入移动语义时规定，有用户声明的复制操作或析构函数的类不再隐式声明移动操作；复制操作出于兼容仍然隐式生成，但列为弃用。

Clang 默认不警告。`-Wextra` 只打开复制操作那一半（`-Wdeprecated-copy-with-user-provided-copy`）；析构函数那一半要 `-Wdeprecated`，用户提供的析构函数对应 `-Wdeprecated-copy-with-user-provided-dtor`，`~S() = default;` 这样仅由用户声明的对应 `-Wdeprecated-copy-with-dtor`。

需要逐成员复制时，显式写 `S(const S&) = default;` 和 `S& operator=(const S&) = default;`。管理资源的类更好的做法是用 `std::unique_ptr` 这样的成员，让类根本不需要自定义析构函数（零法则）。

## 隐式按引用捕获 `*this` {#depr.capture.this}

```cpp ok
struct X {
  int x;
  void foo(int n) {
    auto f = [=]() { x = n; };        // 弃用
    auto g = [=, this]() { x = n; };  // 推荐写法
    f(); g();
  }
};
```

¶1 为了与以前的版本兼容，默认捕获为 `=` 的 lambda 表达式可以隐式按引用捕获 `*this`（[[expr.prim.lambda.capture]]）。这种隐式捕获已弃用。

`[=]` 的字面意思是按值捕获，读者会以为 `x` 被复制了一份。实际上 `x` 是 `this->x`，被捕获的是 `this` 指针，`x = n` 修改的是原对象。lambda 如果比对象活得长，比如存进回调或交给另一个线程，就会通过悬空指针访问。C++20 要求把这件事写出来：`[=, this]` 按引用捕获对象，`[=, *this]` 复制整个对象。

Clang 在 C++20 及以后默认给出 `-Wdeprecated-this-capture` 警告。`[=, this]` 在 C++17 中是非良构的，Clang 作为扩展接受，并给出 `-Wc++20-extensions` 警告。需要同时兼容 C++17 和 C++20 时，写不带默认捕获的显式列表，如 `[this, n]`。

## `volatile` 的几种用法 {#depr.volatile.type}

`volatile` 的正当用途，如映射硬件寄存器的内存、与信号处理函数共享的 `sig_atomic_t` 变量、`setjmp` 前后使用的局部变量，只需要一种语义：每次访问都真正读写内存。C++20 把几种与此无关或容易误解的写法列为弃用。

```cpp
volatile int velociraptor;
++velociraptor;   // 弃用
```

¶1 `volatile` 限定的算术类型和指针类型上的前缀、后缀 `++` 和 `--` 已弃用（[[expr.post.incr]]、[[expr.pre.incr]]）。`++v` 实际上是读、加一、写三步，既不是原子操作，也不是一次访问，写成 `++` 会让人误以为它是。

```cpp
int neck, tail;
volatile int brachiosaur;
brachiosaur = neck;          // OK
tail = brachiosaur;          // OK
tail = brachiosaur = neck;   // 弃用
brachiosaur += neck;         // OK
```

¶2 左操作数是 `volatile` 限定的非类类型时，某些赋值已弃用。具体规则在 [[expr.assign#5]]：赋值表达式不是弃值表达式（[[g:discarded-value-expression]]）、也不是不求值操作数时，即它的结果被使用时，弃用。`tail = brachiosaur = neck` 中，`tail` 的值来自 `neck` 还是重新读一次 `brachiosaur`，不同的人有不同的预期。

复合赋值的情况有过反复。C++20 把对 `volatile` 左值的复合赋值都列为弃用，C++23 撤销了其中按位复合赋值的弃用，因为嵌入式代码大量用 `|=`、`&=` 操作寄存器的位。当前草案只看结果是否被使用，所以作为独立语句的 `brachiosaur += neck;` 不弃用，而 `int x = (brachiosaur += 1);` 弃用。Clang 对后者没有警告。

```cpp
volatile struct amber jurassic();                              // 弃用
void trex(volatile short left_arm, volatile short right_arm);  // 弃用
void fly(volatile struct pterosaur* pteranodon);               // OK
```

¶3 形参或返回类型带 `volatile` 限定的函数类型已弃用（[[dcl.fct]]）。按值传递的形参和返回值都是副本，`volatile` 对调用者毫无意义，形参的顶层 cv 限定甚至不属于函数类型。指向 `volatile` 的指针形参不受影响。

```cpp
struct linhenykus { short forelimb; };
void park(linhenykus alvarezsauroid) {
  volatile auto [what_is_this] = alvarezsauroid;   // 弃用
}
```

¶4 `volatile` 限定类型的结构化绑定已弃用（[[dcl.struct.bind]]）。`volatile` 限定的是绑定背后那个隐藏的对象，结构化绑定引入的名字只是它的成员或元素的别名，再经过元组协议时语义不清。

上面的写法，Clang 在 C++20 及以后默认给出 `-Wdeprecated-volatile` 警告，C++17 下都没有警告。改法是：`++v` 写成 `v = v + 1`，明确是一次读、一次写；链式赋值拆成两条语句；删掉形参和返回类型上的 `volatile`。

## `static constexpr` 数据成员的重新声明 {#depr.static.constexpr}

```cpp ok
struct A {
  static constexpr int n = 5;   // 定义（C++14 中只是声明）
};
constexpr int A::n;             // 冗余的声明（C++14 中是定义）
```

¶1 为了与以前的版本兼容，`constexpr` 静态数据成员可以在类外被冗余地重新声明，不带初始化器（[[basic.def]]、[[class.static.data]]）。这种用法已弃用。

C++14 中类内的那一行只是声明，一旦 `A::n` 被 odr-use，比如绑定到 `const int&`，就必须在某个源文件里写一次类外定义，否则链接失败。C++17 让 `constexpr` 静态数据成员隐式成为 inline 变量（[[dcl.inline]]），类内那一行本身就是定义，类外那一行变得多余。

Clang 在 C++17 及以后加 `-Wdeprecated` 时给出 `-Wdeprecated-redundant-constexpr-static-def` 警告。删掉类外的那一行即可；还要支持 C++14 时，用 `#if __cplusplus < 201703L` 包起来。

## 字面量运算符名中的空白 {#depr.lit}

```cpp ok
long double operator"" _km(long double);  // 弃用
long double operator""_m(long double);    // OK
```

¶1 形如 `operator` *unevaluated-string* *identifier* 的字面量运算符名已弃用（[[over.literal]]），也就是 `""` 与后缀之间有空白的写法。推荐写 `operator""_m`，此时 `""_m` 是一个记号，后缀属于这个记号。

问题出在保留名规则上。有空白时，`_km` 是一个独立的标识符，受 [[lex.name]] 的保留规则约束：以下划线加大写字母开头的标识符保留给实现，用户写 `operator "" _KM` 就违反了规则。没有空白时，后缀是记号的一部分，不受这条规则约束。两种写法本应等价，却因为一个空白适用不同的规则，于是带空白的写法被弃用。

Clang 默认给出 `-Wdeprecated-literal-operator` 警告，从 `-std=c++11` 起就有。标准库自己的后缀，如 `operator""s`、`operator""ms`，一直是无空白的写法。

## 省略号前缺少逗号 {#depr.ellipsis.comma}

```cpp
void f(int...);      // 弃用：等价于 void f(int, ...)
void g(auto...);     // OK：声明一个函数形参包
void h(auto......);  // 弃用：形参包后又跟着 C 风格的省略号
```

形如 *parameter-declaration-list* `...` 的形参声明子句，即省略号前没有逗号，已弃用（[[dcl.fct]]）。{{c++26}}

`void f(int...)` 是 C++ 一直允许的写法，表示 C 风格的可变参数。但函数形参包也用 `...`：`void g(T...)` 中 `T` 是模板形参包时，它声明的是形参包。两者只靠类型是不是包来区分，很容易混淆，`auto......` 更是两种含义叠在一起。要求 C 风格省略号前必须有逗号之后，紧贴类型的 `...` 就只表示形参包。C 语言一直要求这个逗号。

Clang 在 C++26 模式下对 `f` 和 `h` 默认给出 `-Wdeprecated-missing-comma-variadic-parameter` 警告；在 C++20 下只对 `h` 给出 `-Wambiguous-ellipsis`。改法是加逗号：`void f(int, ...)`、`void h(auto..., ...)`。

## 限定名前多余的 `template` {#depr.template.template}

```cpp ok
template<template<class> class TT> struct W {};
namespace N { template<class T> struct V {}; }
W<N::template V> w;   // 弃用
W<N::V> w2;           // OK
```

¶1 在类模板或别名模板的限定名前写 `template` 关键字、后面却没有模板实参列表，已弃用（[[temp.names]]）。

`template` 消歧义符的作用是在依赖的限定名中告诉编译器后面的 `<` 开始一个模板实参列表，如 `T::template apply<int>`。把模板本身作为模板模板实参传递时，后面根本没有 `<`，这个关键字起不到消歧义的作用。[[temp.names#11]] 规定：带 `template` 前缀的名字要么后跟模板实参列表，要么指称类模板或别名模板，后一种情况已弃用。

这条弃用不区分依赖与否。[[temp.names]] 的例子明确把依赖名也算进去：

```cpp ok
template <class T> struct B {
  template <class T2> struct C { };
};
// 弃用：T::C 被假定为指称一个类模板
template <class T,
          template <class X> class TT = T::template C>
struct D { };
D<B<int>> db;
```

Clang 对这两个例子都没有任何诊断。反过来，把依赖情形中的 `template` 去掉写成 `TT = T::C`，Clang 报错 `default template argument for a template template parameter must be a class template`。所以非依赖名删掉多余的 `template` 即可；依赖名作模板模板实参时，在 Clang 上目前只有弃用的写法可用。

## 暴露 TU 局部实体的声明 {#depr.local}

```cpp
namespace {
  struct A {
    void f() {}
  };
}
A h();                        // 弃用：h 没有内部链接
inline void g() { A().f(); }  // 弃用：g 是内联函数，也没有内部链接
```

无名命名空间中的 `A` 是一个 TU 局部（[[g:tu-local]]）实体：每个翻译单元里的 `A` 都是不同的类型，其他翻译单元无法命名它。一个声明如果在会被其他翻译单元看到的部分命名了 TU 局部实体，就叫暴露（[[g:exposure]]，见 [[basic.link]]）。非内联函数的函数体不算这样的部分，内联函数的函数体算，因为它的定义要出现在每个使用它的翻译单元里。

¶1 一个非 TU 局部实体的声明如果是暴露，就已弃用。注 1 指出，这样的声明出现在可导入的模块单元中是非良构的。

`h` 有外部链接，理论上其他翻译单元可以声明并调用它，但它的返回类型 `A` 在别的翻译单元里根本写不出来。`g` 更隐蔽：内联函数的定义在每个翻译单元中必须相同，而各翻译单元的 `A` 是不同的实体，`g` 的各份定义实际上引用了不同的类型，违反 ODR。模块中这类声明直接非良构；传统的头文件模型中这种写法太多，于是先弃用。

Clang 在 `-Wall -Wextra -Wdeprecated` 下对它没有任何诊断。改法是把 `A` 移出无名命名空间，或者让 `h`、`g` 有内部链接，比如声明为 `static` 或放进同一个无名命名空间。

## 小结

| 条款 | Clang 23 默认警告 | 需要的选项 |
|---|---|---|
| D.2 暴露 TU 局部实体 | 否 | 没有对应的警告 |
| D.3 `[=]` 捕获 `this` | 是（C++20 起） | |
| D.4 `volatile` | 是（C++20 起），使用复合赋值结果的情形没有警告 | |
| D.5 `int...` | 是（C++26 模式） | |
| D.6 隐式复制操作 | 否 | `-Wextra`（复制操作的情形）、`-Wdeprecated`（析构函数的情形） |
| D.7 `static constexpr` 重新声明 | 否 | `-Wdeprecated` |
| D.8 `operator "" _x` | 是 | |
| D.9 多余的 `template` | 否 | 没有对应的警告 |
