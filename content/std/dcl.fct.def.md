---
title: 函数定义
summary: 函数定义由哪些部分组成、能写在哪里；函数体内自动可用的 __func__；= default 能用于哪些函数、类内预置与类外预置有什么区别；= delete 怎样参与重载决议；以及程序怎样替换 operator new 这类可替换函数。
status: done
covers: dcl.fct.def.general, dcl.fct.def.default, dcl.fct.def.delete, dcl.fct.def.replace
papers: N2346, P2573R2
related: dcl.fct, dcl.fct.def.coroutine, special, class.ctor, class.copy.ctor, class.copy.assign, class.dtor, class.compare.default, over.inc.default, basic.def.odr, dcl.inline, dcl.constexpr, replacement.functions, topics/special-members-and-elision
tags: 函数定义, default, delete, __func__, 可替换函数
updated: 2026-10-19
---

!!! tldr
    - 函数只能在命名空间或类作用域中定义；定义处的形参和返回类型必须是完整类型，弃置函数除外。
    - `= default` 只能用于特殊成员函数、比较运算符和后缀 `++`/`--`。在类内首次声明处预置的函数不算用户提供，可以是平凡的；在类外预置则是用户提供的，类型因此失去平凡性。
    - `= delete` 的函数照常参与重载决议，被选中就非良构，即使出现在 `sizeof`、`decltype` 这样不求值的操作数里也一样。弃置定义必须是函数的首次声明。
    - C++26 起可以写 `= delete("理由")`，理由文本会出现在诊断信息里。
    - 全局 `operator new`/`operator delete` 等可替换函数由程序提供唯一定义替换实现的版本；替换函数不能是 `inline`，必须有 C++ 语言链接并属于全局模块。

## 函数定义的组成（[dcl.fct.def.general]）

```cpp
int max(int a, int b, int c) {
  int m = (a > b) ? a : b;
  return (m > c) ? m : c;
}
```

标准例 1 中，`int` 是说明符序列（*decl-specifier-seq*），`max(int a, int b, int c)` 是声明符（*declarator*），花括号部分是函数体（*function-body*）。¶1 给出的文法可以概括为：

```text
function-definition:
    属性(可选) 说明符序列(可选) 声明符 virt-specifier-seq(可选) 契约说明符(可选) function-body
    属性(可选) 说明符序列(可选) 声明符 requires-clause 契约说明符(可选) function-body
function-body:
    ctor-initializer(可选) compound-statement
    function-try-block
    = default ;
    = delete ;
    = delete ( unevaluated-string ) ;
```

¶1 还规定了几件事：

- 说明符序列可以省略，构造函数、析构函数和转换函数就没有。
- 带 `override`/`final`（*virt-specifier-seq*）的定义必须是类成员声明；带 *requires-clause* 的定义必须定义模板化的函数。
- 开头的属性属于函数。契约说明符 `pre`/`post`（[[dcl.contract]]）写在函数体之前。
- 标准里非正式地说函数体时，指的是非终结符 *function-body*。对构造函数，它还包括没有 *mem-initializer* 时用来初始化基类和成员的默认成员初始化器或默认初始化。所以“构造函数体内抛出的异常”也涵盖这些成员初始化中抛出的异常。

¶2 在函数定义中，`void 声明符 ;` 或 `声明符 ;` 必须是良构的函数声明（[[dcl.fct]]）。函数只能在命名空间作用域或类作用域中定义；lambda 是表达式，不是函数定义。除非函数是弃置的，否则定义处的形参类型和返回类型不能是在函数体内不完整或抽象的类类型。

```cpp error
struct Inc;
Inc make();                     // OK：声明可以用不完整类型
Inc make() { return {}; }       // error: 定义中返回类型不完整
Inc oops(Inc) = delete;         // OK：弃置函数不受此限
void outer() {
  void inner() { }              // error: 不能在块作用域定义函数
}
```

弃置函数永远不会被调用，不需要知道形参和返回值的布局。这样，用来屏蔽某种调用的弃置重载可以针对还不完整的类型声明。

¶3–¶6 是例与注：¶4 说 *ctor-initializer* 只用于构造函数（[[class.base.init]]）；注 1 说成员函数声明符上的 cv 限定决定函数体中 `this` 的类型（[[expr.prim.this]]）；注 2 说不用的形参可以不命名，如 `void print(int a, int)`。

## `__func__`（¶7–¶8）

```cpp run ok
#include <cstdio>
struct S {
  S() : s(__func__) { }        // OK：ctor-initializer 属于函数体
  const char* s;
};
template<class T> void tf() { std::puts(__func__); }
int main() {
  std::puts(__func__);         // Clang/GCC："main"
  std::puts(S{}.s);            // Clang/GCC："S"
  tf<int>();                   // Clang/GCC："tf"，不含模板实参
  [] { std::puts(__func__); }();   // Clang/GCC："operator()"
  std::printf("%s\n", __PRETTY_FUNCTION__);   // 扩展："int main()"
}
```

¶7 **函数局部预定义变量**（function-local predefined variable）是在函数形参作用域中隐式定义的、具有静态存储期的变量。

¶8 `__func__` 就是这样一个变量，如同定义了

```cpp
static const char __func__[] = "function-name";
```

其中 *function-name* 是实现定义的字符串。它与程序中其他对象的地址是否不同是未指定的，实现可以把它和内容相同的字符串字面量合并。脚注说明，实现可以用保留名提供其他预定义变量，如 GCC/Clang 的 `__PRETTY_FUNCTION__`、MSVC 的 `__FUNCSIG__`；没有被 odr-use 的预定义变量，其字符串可以不出现在程序映像中。

标准例 2 指出，`void f(const char* s = __func__);` 非良构：`__func__` 只在函数定义之内可用，默认实参里没有这个名字。本机 Clang 23 对此只给出警告 `-Wpredefined-identifier-outside-function`，警告也满足诊断要求。

!!! tip "`std::source_location`"
    C++20 的 `std::source_location::current().function_name()` 也给出函数名（同样由实现定义），而且用作默认实参时得到的是调用者的位置（[[support.srcloc]]），比 `__func__` 更适合写日志。

## 显式预置的函数（[dcl.fct.def.default]）

### 哪些函数可以预置（¶1）

¶1 函数体为 `= default;` 的定义叫做**显式预置**（[[g:explicitly-defaulted|explicitly-defaulted]]）的定义。显式预置的函数必须：

- ¶1.1 是特殊成员函数（[[special]]：默认构造、复制或移动构造、复制或移动赋值、析构）、比较运算符函数（[[class.compare.default]]），或者后缀自增、自减运算符函数（[[over.inc.default]]）；
- ¶1.2 没有默认实参。

预置后缀 `++`/`--` 是 C++23 之后的新规则：`C operator++(int) = default;` 的含义是先复制 `*this`，再调用前缀 `++`，返回副本。本机 Clang 23 尚不支持，报 only special member functions and comparison operators may be defaulted。

### 预置版本可以和隐式版本有哪些差异（¶2）

```cpp error
struct S {
  S(int a = 0) = default;               // error: 有默认实参
  void operator=(const S&) = default;   // error: 返回类型应为 S&
  ~S() noexcept(false) = default;       // OK：异常规格可以不同
private:
  int i;
  S(S&);                                // OK：私有的复制构造函数
};
S::S(S&) = default;                     // OK：定义复制构造函数
```

¶2 设显式预置的特殊成员函数为 F1，类本来会隐式声明的对应函数为 F2。F1 与 F2 不能有差异，除了以下几种：

- ¶2.1 F1 是赋值运算符时，可以带 `&` 引用限定符；
- ¶2.2 F2 是赋值运算符时，F1 可以改用类型为 `C&` 的显式对象形参：`C& operator=(this C&, const C&) = default;`；
- ¶2.3 异常规格可以不同；
- ¶2.4 F2 的形参是 `const C&` 时，F1 的对应形参可以是 `C&`；
- ¶2.5 F2 的形参是 `C&`（某个成员或基类只能从非 const 左值复制）时，F1 可以是 `const C&`。这时若 F1 在首次声明上预置，它被定义为弃置的；否则程序非良构。

```cpp error
struct M { M(M&); };                     // 只能从非 const 左值复制
struct H  { M m; H(const H&) = default; };   // ¶2.5：首次声明预置，定义为弃置
struct H2 { M m; H2(const H2&); };
H2::H2(const H2&) = default;             // error: ¶2.5，不是首次声明
```

¶4 的例子说明了 ¶2.3 的后果：如果成员 `T` 的移动构造函数可能抛出，而 `U(U&&) noexcept = default;`，那么 `T` 的移动构造函数真的抛出时，按 noexcept 函数的通常语义调用 `std::terminate`。

!!! warning "C++26 之后的收紧 {{c++29}}"
    [[diff.cpp26.dcl]] 记录了一项与 C++26 不兼容的修改：预置的赋值运算符不再允许 cv 限定符或 `&&` 引用限定符（¶2.1 只允许 `&`），预置的移动赋值运算符的形参也不能是 cv 限定的 `T&&`。

    ```cpp
    struct S { S& operator=(const S&) && = default; };     // 现在非良构；C++26 中良构
    struct T { T& operator=(const T&) const = default; };  // 现在非良构；C++26 中良构但弃置
    struct U { U& operator=(const U&&) = default; };       // 现在非良构；C++26 中良构但弃置
    ```

    理由是移除少用且容易误解的写法。本机 Clang 23 仍按 C++26 规则接受这三行，对后两行给出 implicitly deleted 警告。

### 隐式 inline 与 constexpr（¶3）

¶3 在首次声明上显式预置的函数是隐式 `inline` 的（[[dcl.inline]]）；如果它满足 constexpr-suitable 的条件（[[dcl.constexpr]]），还是隐式 `constexpr` 的。注 1 指出，其他预置函数，也就是在类外预置的，不是隐式 constexpr 的。

```cpp error
struct C1 { int x; constexpr C1() : x(0) { } C1(const C1&) = default; };
constexpr C1 a;
constexpr C1 b = a;        // OK：类内预置的复制构造函数隐式 constexpr

struct C2 { int x; constexpr C2() : x(0) { } C2(const C2&); };
C2::C2(const C2&) = default;
constexpr C2 c;
constexpr C2 d = c;        // error: 类外预置的复制构造函数不是 constexpr
```

### 用户提供与定义时机（¶5–¶6）

¶5 显式预置的函数和隐式声明的函数统称**预置函数**（defaulted functions）。实现为它们提供隐式定义（[[class.ctor]]、[[class.dtor]]、[[class.copy.ctor]]、[[class.copy.assign]]），其中有些会被定义为弃置的：

- 预置的预期析构函数（prospective destructor，C++20 起一个类可以有多个带约束的候选析构函数），如果最终没有成为析构函数，定义为弃置；
- 预置的特殊成员函数，如果既不是预期析构函数，也不是合格的（eligible，[[special]]）特殊成员函数，定义为弃置。

如果一个函数是用户声明的，并且没有在首次声明上显式预置或弃置，它就是**用户提供的**（[[g:user-provided|user-provided]]）：

| 写法 | 用户声明 | 用户提供 | 可能平凡 |
|---|---|---|---|
| 不写 | 否 | 否 | 是 |
| 类内 `S() = default;` | 是 | 否 | 是 |
| 类内 `S();`，类外 `S::S() = default;` | 是 | 是 | 否 |
| 类内 `S() = delete;` | 是 | 否 | 不适用 |
| 类内 `S() { }` | 是 | 是 | 否 |

用户提供的显式预置函数（在首次声明之后预置的）在预置处就被隐式定义；如果它会被定义为弃置，程序非良构。注 2 指出，这种写法可以兼顾高效和稳定的二进制接口：函数有一个真正的外部定义，以后可以换成手写实现，不必改头文件。

非用户提供的预置函数（隐式声明的，或者在类内预置的）如果没有被定义为弃置，要等到被 odr-use 或常量求值需要它（[[expr.const.defns]]）时才隐式定义。注 3 指出，这样的隐式定义不绑定任何名字。

¶6 的标准例 2 展示了两种预置的区别：

```cpp run ok
#include <type_traits>
struct trivial {
  trivial() = default;                          // 首次声明预置：非用户提供
  trivial(const trivial&) = default;
  trivial(trivial&&) = default;
  trivial& operator=(const trivial&) = default;
  trivial& operator=(trivial&&) = default;
  ~trivial() = default;
};
struct nontrivial1 { nontrivial1(); };
nontrivial1::nontrivial1() = default;           // 不是首次声明：用户提供

static_assert(std::is_trivially_default_constructible_v<trivial>);
static_assert(!std::is_trivially_default_constructible_v<nontrivial1>);
static_assert(std::is_trivially_copyable_v<trivial>);
int main() { }
```

是否用户提供影响三件事：平凡性（[[class.default.ctor]] 等）；值初始化时是否先零初始化（[[dcl.init]]：没有用户提供的默认构造函数时，值初始化先把对象清零）；以及 const 对象能否不写初始化器（[[g:const-default-constructible]]）。

```cpp error
struct A { int x; A() = default; };
struct B { int x; B(); };
B::B() = default;

const A ca;   // error: A 没有用户提供的默认构造函数，x 也没有默认成员初始化器
const B cb;   // OK：B 有用户提供的默认构造函数，cb.x 的值是错误值
```

## 弃置的定义（[dcl.fct.def.delete]）

```cpp error
void g(int) = delete("use g(long) to make the width explicit");   // C++26
void g(long) { }

void use() {
  g(1L);                       // OK
  g(1);                        // error: 选中了弃置的 g(int)
  using R = decltype(g(1));    // error: 不求值的操作数中也一样
}
```

本机 Clang 23 对 `g(1)` 的诊断是 call to deleted function 'g': use g(long) to make the width explicit。

¶1 函数体为 `= delete;` 或 `= delete("...");` 的定义，以及被定义为弃置的显式预置定义，都叫函数的**弃置定义**（deleted definition）。具有弃置定义的函数，以及被隐式定义为弃置的函数，叫做**弃置函数**（[[g:deleted-function|deleted function]]）。

### 指代弃置函数即非良构（¶2）

!!! std
    A construct that designates a deleted function implicitly or explicitly, other than to declare it or to appear as the operand of a *reflect-expression*, is ill-formed.

¶2 除了声明它、或者作为反射运算符 `^^` 的操作数，任何隐式或显式指代弃置函数的构造都非良构。注 1 作了展开：

- 指代包括隐式或显式的调用，以及取函数的地址或成员指针。
- 即使在不潜在求值的表达式中，如 `sizeof(f(1))`、`decltype(f(1))`，也非良构。这和只声明不定义的函数不同，后者只要不被 odr-use 就没有问题。
- 对重载集合，只有重载决议选中的那个函数才算被指代。
- 虚函数的隐式 odr-use 本身不构成指代，所以虚函数可以是弃置的，只要从不调用。

标准建议（*Recommended practice*）：提供了 *unevaluated-string* 时，诊断信息应当包含它的文本。注中说明，可以用它解释弃置的理由或建议替代写法。

弃置函数要参与重载决议，正是为了让它被选中时报错。如果它不参与，`g(1)` 会悄悄选中 `g(long)`，这恰恰是作者想阻止的。C++03 的老办法是把函数声明为 private 且不定义，那样报的是访问错误，在类自己的成员里调用时更要拖到链接时才报错；`= delete` 在编译期就给出准确的错误。

### 典型用法（¶3）

标准给出三个例子：

```cpp error
#include <cstddef>
struct onlydouble {                    // 1. 只接受 double
  onlydouble() = delete;               // OK，但多余
  template<class T> onlydouble(T) = delete;
  onlydouble(double);
};
onlydouble b(1);                       // error: 选中弃置的 onlydouble<int>

struct sometype {                      // 2. 禁止用 new 创建
  void* operator new(std::size_t) = delete;
  void* operator new[](std::size_t) = delete;
};
sometype* p = new sometype;            // error: 弃置的类 operator new
sometype* q = new sometype[3];         // error: 弃置的类 operator new[]

struct moveonly {                      // 3. 只能移动
  moveonly() = default;
  moveonly(const moveonly&) = delete;
  moveonly(moveonly&&) = default;
  moveonly& operator=(const moveonly&) = delete;
  moveonly& operator=(moveonly&&) = default;
  ~moveonly() = default;
};
moveonly* mp;
moveonly mq(*mp);                      // error: 弃置的复制构造函数
```

`onlydouble() = delete;` 多余，是因为类已经声明了别的构造函数，默认构造函数本来就不会隐式声明。其他常见用法有 `void f(std::nullptr_t) = delete;`（禁止传 `nullptr`），以及禁止绑定临时对象的 `void ref(const T&&) = delete;`，标准库的 `std::ref` 就是这样做的。

### 弃置定义必须是首次声明（¶4）

<div class="compare" markdown="1">

```cpp ok
template<class T> void process(T) { }
template<> void process<bool>(bool)
    = delete;  // 特化的首次声明
int main() { process(1); }
```

```cpp error
struct sometype { sometype(); };
sometype::sometype() = delete;
  // error: 不是首次声明
```

</div>

¶4 弃置函数是隐式 `inline` 的（[[dcl.inline]]）；注 2 指出 ODR 也适用于弃置定义，各翻译单元中必须一致。

弃置定义必须是函数的首次声明；对函数模板的显式特化，必须是这个特化的首次声明。这样，每个能看到函数的地方都知道它是弃置的。如果允许先声明、后弃置，在弃置定义之前的调用点上编译器会认为函数可用，指代即非良构的规则就无法一致地执行。对显式特化的放宽，让主模板正常可用、只弃置某一个特化成为可能。

隐式声明的全局分配和解分配函数（[[basic.stc.dynamic]]）不能被定义为弃置的。

## 可替换函数（[dcl.fct.def.replace]）

```cpp run ok
#include <cstdio>
#include <cstdlib>
#include <new>

static int allocations = 0;

void* operator new(std::size_t n) {     // 替换函数
  ++allocations;
  if (void* p = std::malloc(n ? n : 1)) return p;
  throw std::bad_alloc{};
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

int main() {
  delete new int(1);
  std::printf("allocations: %d\n", allocations);   // 至少 1
}
```

¶1 某些由实现提供定义的函数是**可替换的**（[[g:replaceable-function|replaceable]]）。程序可以提供一个签名相同的定义，叫做**替换函数**（[[g:replacement-function|replacement function]]），程序就会使用它而不是实现的默认版本。替换在程序启动前完成（[[basic.def.odr]]、[[basic.start]]），不是运行时切换。替换函数的声明必须：

- ¶1.1 不是 `inline` 的；
- ¶1.2 属于全局模块，不能在具名模块中替换；
- ¶1.3 具有 C++ 语言链接；
- ¶1.4 返回类型与可替换函数相同；
- ¶1.5 如果该函数在标准库头文件中声明，替换函数的声明必须能作为那个声明的合法重声明。

违反其中任何一条都是 {{ifndr}}：非良构，但不要求编译器诊断。

注 1 指出，ODR 适用于程序提供的替换定义，整个程序只能有一个；实现提供的定义是一个没有名字、没有链接的函数，所以二者不构成 ODR 冲突。

不能是 `inline`，是因为替换函数必须在程序启动前接管所有调用，包括标准库内部和其他翻译单元的调用；`inline` 函数可以在多个翻译单元中各有定义，还可能被内联进调用点，与全程序替换的含义冲突。

可替换函数的清单散在各处，最主要的是全局 `operator new`/`operator delete` 的各种形式（[[replacement.functions]]、[[new.delete]]）；C++26 的契约违反处理函数 `::handle_contract_violation` 也是可替换的（[[basic.contract.handler]]）。

## 实现视角

!!! impl
    - 首次声明预置且平凡的函数不生成代码：复制就是逐字节复制，构造什么也不做。类外预置的函数是一个真正的外部函数，即使函数体为空也有调用开销（除非开启 LTO），而且类型失去平凡性。这会影响 ABI：Itanium C++ ABI 中，复制构造函数或析构函数非平凡的类型不能经寄存器传递，只能经内存间接传递。
    - 弃置函数不生成代码，也不产生符号。
    - 替换 `operator new` 在链接层面通常表现为用户目标文件中的定义优先于运行库中的定义；运行库是共享库时，还要靠动态链接器的符号介入（interposition），让库内部的调用也转到替换函数。

## 历史与演进

!!! history
    - C++98：函数定义与函数 try 块；替换全局 `operator new`/`delete` 的规则写在库条款中。
    - C++11：`= default` 与 `= delete`（[[N2346]]）；从 C99 引入 `__func__`。
    - C++20：可以预置比较运算符 `==` 和 `<=>`（[[class.compare.default]]）；引入预期析构函数。
    - C++23：预置的赋值运算符可以使用显式对象形参（¶2.2）。
    - C++26：`= delete("理由")`（[[P2573R2]]）；弃置函数可以作为 `^^` 的操作数；新增 [dcl.fct.def.replace]，在核心语言中统一描述可替换函数。
    - C++26 之后：预置的赋值运算符不再允许 cv 和 `&&` 限定（[[diff.cpp26.dcl]]）；可以预置后缀 `++`/`--`。

## 常见误解

!!! pitfall "类外 `= default` 和类内 `= default` 一样"
    `struct S { S(); }; S::S() = default;` 中 `S` 不再是平凡默认可构造的。只是想把实现移出头文件时这样做没有问题；需要平凡性（例如 `std::is_trivially_*` 优化或与 C 互操作）时，应在类内预置。

!!! pitfall "写了 `= default` 函数就存在"
    成员不可复制时，类内的 `S(const S&) = default;` 会被定义为弃置的。声明时不报错，用到时才报错。Clang 的 `-Wdefaulted-function-deleted` 会提示这种情况。

!!! pitfall "可以用 `decltype` 探测弃置函数的返回类型"
    即使不求值，指代弃置函数也非良构。在模板实参推导的替换中，这表现为替换失败，所以 `requires { f(x); }` 能检测出 `f(x)` 会选中弃置函数。

!!! pitfall "可以在 .cpp 里再把函数弃置"
    弃置定义必须是首次声明：不能在头文件中声明 `void f(int);`，再到 `.cpp` 中写 `void f(int) = delete;`。

## 思考题

!!! question "思考题 1"
    下面哪些类型的 `std::is_trivially_copyable_v` 为真？
    ```cpp
    struct A { A(const A&) = default; };
    struct B { B(const B&); };  B::B(const B&) = default;
    struct C { C(const C&) = delete; };
    struct D { D(const D&) = default; int& r; };
    ```

<details markdown="1">
<summary>答案</summary>

- `A`：真。复制构造函数在首次声明上预置，是平凡的。
- `B`：假。类外预置，所以是用户提供的，不平凡。
- `C`：真。平凡可复制要求至少有一个合格的复制或移动操作，并且所有合格的复制、移动操作和析构函数都平凡（[[class.prop]]）。弃置的复制构造函数不合格（[[special]]）；用户声明了复制构造函数，移动操作不会隐式声明；但复制赋值运算符仍被隐式声明为预置且平凡，于是有一个合格的平凡操作。不能复制构造的类型却是平凡可复制的，这个结论很反直觉。
- `D`：真。复制构造函数平凡；复制赋值因引用成员被定义为弃置，不合格；移动操作没有声明。仍有平凡且合格的复制构造函数和析构函数。

本机 Clang 23 的结果与上述一致。
</details>

!!! question "思考题 2"
    为什么 `template<class T> onlydouble(T) = delete;` 能阻止 `onlydouble x(1.0f);`？

<details markdown="1">
<summary>答案</summary>

重载决议中，模板特化 `onlydouble<float>(float)` 是精确匹配，`onlydouble(double)` 需要浮点提升，精确匹配更好（[[over.ics.rank]]），于是选中弃置的模板特化，调用非良构。只有实参恰好是 `double` 时，两者都是精确匹配，再按非模板优先的规则选中 `onlydouble(double)`。
</details>
