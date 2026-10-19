---
title: 特殊成员函数
summary: 编译器可以替类声明和定义的六种成员函数：何时隐式声明、何时被定义为弃置、何时真正生成，以及 C++20 怎样用约束让它们按条件平凡。
status: draft
papers: P0848R3
related: class.ctor, class.copy.ctor, class.copy.assign, class.dtor, class.prop, dcl.fct.def, depr.impldec
tags: 特殊成员函数, Rule of five, 弃置函数, 平凡性
updated: 2026-10-19
---

!!! tldr
    - 六种特殊成员函数：默认构造、复制构造、移动构造、复制赋值、移动赋值和析构。程序没有声明它们时，编译器在类定义的 `}` 处替你声明。
    - 自己声明一个特殊成员函数会影响其他几个：声明析构函数或复制操作会让移动操作不再隐式声明，声明移动操作会让复制操作被删除。
    - 移动操作没有声明时，右值会退回去用复制构造，程序照常编译，只是悄悄变成了复制。
    - 编译器生成的版本如果会出错（比如类有引用成员时的赋值），它会被定义为弃置，类照常可用，只有真正用到这个操作时才报错。
    - C++20 起可以用 `requires` 为同一种特殊成员函数写多个版本，由约束选出合格的那个，让类模板按模板实参决定是否平凡。

```cpp run ok
#include <string>
struct Person {
  std::string name;
  int age;
};
int main() {
  Person a{"Ada", 36};
  Person b = a;             // 复制构造
  Person c = std::move(a);  // 移动构造
  b = c;                    // 复制赋值
  c = Person{"Bob", 1};     // 移动赋值
}                           // 析构
```

`Person` 一个成员函数也没写，却可以复制、移动、赋值、销毁。这些操作由编译器替它声明和定义，这样的成员函数叫**特殊成员函数**（special member function，[[g:special-member-function]]）。本页讲它们的总规则，每一种的细节在各自的条款里。

| 特殊成员函数 | 典型签名 | 细节 |
|---|---|---|
| 默认构造函数 | `X()` | [[class.default.ctor]] |
| 复制构造函数 | `X(const X&)` | [[class.copy.ctor]] |
| 移动构造函数 | `X(X&&)` | [[class.copy.ctor]] |
| 复制赋值运算符 | `X& operator=(const X&)` | [[class.copy.assign]] |
| 移动赋值运算符 | `X& operator=(X&&)` | [[class.copy.assign]] |
| 析构函数 | `~X()` | [[class.dtor]] |

转换构造函数、转换函数（[[class.conv]]）不是特殊成员函数。预置的比较运算符（[[class.compare.default]]）虽然也能写 `= default`，也不是。

## 编译器替你声明了什么（¶1–¶4）

¶1 标准的列表里，析构函数的位置写的是**预期析构函数**（prospective destructor，[[g:prospective-destructor]]）。一个类可以声明多个预期析构函数，最终选出一个作为真正的析构函数，见下文带约束的特殊成员函数一节。

程序没有声明某个特殊成员函数时，编译器会为某些类**隐式声明**它，并在需要时**隐式定义**它。这里有两个时间点要分开：

- 隐式声明发生在类定义的闭花括号 `}` 处。所以在类的成员声明里还看不到它们，在成员函数体里可以用，因为函数体要到 `}` 之后才处理（[[class.mem#10]]）。
- 隐式定义，也就是真正生成函数体，要等到函数被用到时才发生，见下文。

程序不能定义一个隐式声明的特殊成员函数。想自己提供定义，必须先在类里声明它：

```cpp title="no-define-implicit.cpp" error
struct S { int x; };
S::S() : x(0) { }   // error: S::S() 是隐式声明的
```

### 两个术语：预置与弃置

**预置**（defaulted）的函数是指定义交给编译器生成的函数：隐式声明的特殊成员函数，以及写了 `= default` 的函数（[[dcl.fct.def.default#5]]）。**弃置**（deleted）的函数有声明，但任何使用它的代码都是非良构的（[[dcl.fct.def.delete]]）。弃置函数仍然参与重载决议，被选中才报错。

一个预置的函数可能被编译器定义为弃置，下文会多次用到这一点。另外，`= default` 和 `= delete` 都算**用户声明**（user-declared，[[g:user-declared]]），即使函数体由编译器生成。

### 可以显式调用隐式声明的函数（¶2）

¶2 隐式声明的特殊成员函数和普通成员函数一样，可以显式调用，也可以取成员指针：

```cpp run title="call-implicit.cpp" ok
struct A { int a = 1; };     // 隐式声明 A::operator=
struct B : A {
  int b = 2;
  B& operator=(const B& s) {
    this->A::operator=(s);   // OK: 调用隐式声明的版本
    b = s.b;
    return *this;
  }
};
int main() {
  B x, y;
  y.a = 10;
  x = y;
  A& (A::*pm)(const A&) = &A::operator=;  // OK
  (void)pm;
  return x.a - 10;
}
```

¶4 特殊成员函数遵守普通的访问规则（[[class.access]]）。把构造函数声明为 `protected`，就只有派生类和友元能创建对象，这是只供继承的基类的常见写法。

## 声明一个，影响其他几个

C++ 编程里最常查的一张表：用户声明了某个特殊成员函数之后，其他几个会怎样。行是用户声明的函数，列是编译器对其他函数的处理。

| 用户声明了 ↓ / 隐式的 → | 默认构造 | 析构 | 复制构造 | 复制赋值 | 移动构造 | 移动赋值 |
|---|---|---|---|---|---|---|
| 什么都没有 | 预置 | 预置 | 预置 | 预置 | 预置 | 预置 |
| 其他构造函数 | 不声明 | 预置 | 预置 | 预置 | 预置 | 预置 |
| 默认构造函数 | | 预置 | 预置 | 预置 | 预置 | 预置 |
| 析构函数 | 预置 | | 预置（弃用） | 预置（弃用） | 不声明 | 不声明 |
| 复制构造函数 | 不声明 | 预置 | | 预置（弃用） | 不声明 | 不声明 |
| 复制赋值运算符 | 预置 | 预置 | 预置（弃用） | | 不声明 | 不声明 |
| 移动构造函数 | 不声明 | 预置 | 弃置 | 弃置 | | 不声明 |
| 移动赋值运算符 | 预置 | 预置 | 弃置 | 弃置 | 不声明 | |

表中每一列来自对应条款的一句话：

- 默认构造函数：类没有任何用户声明的构造函数（包括复制、移动构造函数）时才隐式声明（[[class.default.ctor#1]]）。
- 析构函数：没有用户声明的预期析构函数就隐式声明，其他声明都不影响它（[[class.dtor#2]]）。
- 复制构造函数：没有用户声明的复制构造函数就隐式声明。类声明了移动操作时它被定义为弃置；类有用户声明的复制赋值或析构函数时，隐式声明的复制构造函数已弃用（[[class.copy.ctor#6]]、[[depr.impldec]]）。
- 复制赋值运算符：规则对称（[[class.copy.assign#2]]）。
- 移动构造函数：只有类没有用户声明的复制构造、复制赋值、移动赋值和析构函数时才隐式声明（[[class.copy.ctor#8]]）。
- 移动赋值运算符：只有类没有用户声明的复制构造、移动构造、复制赋值和析构函数时才隐式声明（[[class.copy.assign#4]]）。

### 不声明和弃置不是一回事

<div class="compare" markdown="1">

```cpp run ok
struct D {
  ~D() { }  // 移动操作不声明
};
int main() {
  D a;
  D b = static_cast<D&&>(a);
  // OK: 用复制构造
}
```

```cpp error
struct M {
  M() = default;
  M(M&&) = default;
  // 复制构造：弃置
};
int main() {
  M a;
  M b = a;  // error
}
```

</div>

左边的 `D` 没有移动构造函数。用右值初始化时，重载决议找到复制构造函数 `D(const D&)`，`const` 左值引用能绑定右值，于是程序照常编译，移动悄悄变成了复制。

右边的 `M` 声明了移动构造函数，复制构造函数因此被定义为弃置。弃置函数仍然参与重载决议，用左值初始化时它被选中，程序报错。`std::unique_ptr` 不可复制，就是这样来的。

下面用类型特征把表里的几格验证一遍：

```cpp run title="special-table.cpp" ok
#include <type_traits>
using namespace std;

struct Dtor { ~Dtor() { } };
static_assert(is_copy_constructible_v<Dtor>);
static_assert(is_move_constructible_v<Dtor>);  // 实际用的是复制构造
static_assert(!is_trivially_move_constructible_v<Dtor>);

struct CC { CC(const CC&) = default; };
static_assert(!is_default_constructible_v<CC>);

struct MC { MC(MC&&) = default; };
static_assert(!is_copy_constructible_v<MC>);   // 弃置
static_assert(!is_copy_assignable_v<MC>);      // 弃置
static_assert(!is_move_assignable_v<MC>);      // 移动赋值不声明，复制赋值弃置

struct MA { MA& operator=(MA&&) = default; };
static_assert(is_default_constructible_v<MA>);
static_assert(!is_move_constructible_v<MA>);

int main() { }
```

`is_move_constructible_v<Dtor>` 为真，只说明能用右值构造，不说明调用的是移动构造函数。

### 由此得出的写法

- **Rule of zero**：能不写就不写。让 `std::string`、`std::vector`、`std::unique_ptr` 这样的成员自己管理资源，六个特殊成员函数全部交给编译器，它们自动正确，并且在可能时是平凡的、`noexcept` 的。
- **Rule of five**：一旦需要自己写析构、复制、移动中的任何一个，就把五个都显式声明出来，可以写 `= default` 或 `= delete`。只写一个析构函数会让移动操作消失，隐式的复制又是弃用的。
- 表中标为弃用的四格，是 C++11 为了兼容 C++98 代码留下的。[[depr.impldec]] 说将来可能把它们改为弃置。

## 预置的函数何时被定义为弃置

```cpp title="defaulted-deleted.cpp" error
struct R { int& r; };       // 有引用成员
struct C { const int c; };  // 有 const 成员

void f(R& a, R& b, C& x, C& y) {
  R r;        // error: 默认构造函数被定义为弃置
  C c;        // error: 同上
  a = b;      // error: 复制赋值被定义为弃置
  x = y;      // error: 同上
  R r2 = a;   // OK: 复制构造没有问题
}
```

`R` 和 `C` 的定义本身没有错。编译器替它们生成的默认构造函数没法初始化引用和 `const int`，生成的赋值运算符没法给引用重新绑定、没法修改 `const` 成员。标准的处理是把这些预置函数定义为弃置，而不是让类定义出错。这样类照常可以用，只有真正调用这些操作时才报错。

### 潜在构造的子对象（¶7）

各种弃置条件都要检查子对象：成员和基类能不能构造、能不能析构。检查的范围有一个名字。

¶7 一个类的直接非静态数据成员、非虚直接基类，以及类不是抽象类时的虚基类，统称为它的**潜在构造的子对象**（potentially constructed subobjects，[[g:potentially-constructed-subobjects]]）。

抽象类排除虚基类，是因为虚基类只由最派生类的构造函数初始化（[[class.base.init]]）。抽象类不能有完整对象，永远不是最派生类，它的构造函数从不真正构造虚基类。所以即使虚基类没有默认构造函数，也没有理由删除抽象类的默认构造函数：

```cpp run title="abstract-vbase.cpp" ok
struct V { V(int) { } };   // 没有默认构造函数
struct A : virtual V {     // 抽象类
  virtual void f() = 0;
};                         // A() 不因 V 被删除
struct C : A {
  C() : V(42) { }          // 最派生类构造虚基类
  void f() override { }
};
int main() { C c; (void)c; }
```

### 弃置条件一览

下表汇总各条款中的弃置条件，细节见各页。

| 预置的函数 | 主要的弃置条件 |
|---|---|
| 默认构造函数 | 引用成员没有默认成员初始化器；非联合体类的 `const` 成员没有初始化器，且其类型不能默认初始化成确定的值；某个潜在构造的子对象没有可用的默认构造函数；某个子对象的析构函数被删除或不可访问（[[class.default.ctor#2]]） |
| 复制、移动构造函数 | 某个潜在构造的子对象没有可用的对应构造函数，或者变体成员（联合体的成员）的那个函数不平凡；某个子对象的析构函数被删除或不可访问；复制构造函数遇到右值引用成员（[[class.copy.ctor#10]]） |
| 复制、移动赋值运算符 | 有 `const` 的非类类型成员；有引用成员；某个直接成员或直接基类没有可用的对应赋值运算符，或者变体成员的那个函数不平凡（[[class.copy.assign#7]]） |
| 析构函数 | 非联合体类中某个潜在构造的子对象的析构函数被删除或不可访问；联合体的几种情形；虚析构函数找不到可用的 `operator delete`（[[class.dtor#7]]） |
| 任何一种 | 不是合格的特殊成员函数（见下一节），或者是没被选中的预期析构函数（[[dcl.fct.def.default#5]]） |

### 被删除的预置移动操作会被重载决议忽略

如果一个成员可以复制、不能移动，类的预置移动构造函数就被定义为弃置。按照弃置函数的一般规则，用右值初始化时它会被选中然后报错，虽然复制构造函数完全可以胜任。

所以标准另有一条：被定义为弃置的预置移动构造函数和移动赋值运算符不参与重载决议（[[class.copy.ctor#10]] 注 4、[[class.copy.assign#7]] 注 4）。显式写成 `= delete` 的移动操作不受这条影响，仍然参与重载决议。

```cpp run title="deleted-move-ignored.cpp" ok
#include <utility>

struct NM {                 // 可复制，显式删除移动
  NM() { }
  NM(const NM&) { }
  NM(NM&&) = delete;
};

struct Y {
  NM n;
  Y() = default;
  Y(const Y&) = default;
  Y(Y&&) = default;         // 被定义为弃置，也被忽略
};

int main() {
  Y a;
  Y b = std::move(a);       // OK: 选中 Y(const Y&)
  (void)b;
  NM m;
  // NM m2 = std::move(m);  // error: 选中显式删除的 NM(NM&&)
}
```

Clang 会对 `Y(Y&&) = default;` 给出 `-Wdefaulted-function-deleted` 警告，提示它实际上被删除了。

## 带约束的特殊成员函数（¶5–¶6）{{c++20}}

`std::optional<int>` 应当可以平凡复制，`std::optional<std::string>` 不行。在 C++20 之前，类模板要做到这一点，只能把实现拆进好几层基类，用偏特化分别处理。C++20 允许在同一个类里写多个带约束的版本：

```cpp run title="conditional-trivial.cpp" ok
#include <string>
#include <type_traits>

template<class T>
struct Box {
  T value;
  Box(T v) : value(v) { }
  Box(const Box&)
    requires std::is_trivially_copy_constructible_v<T>
    = default;                                    // #1
  Box(const Box& o) : value(o.value) { }          // #2
};

static_assert(std::is_trivially_copy_constructible_v<Box<int>>);
static_assert(!std::is_trivially_copy_constructible_v<Box<std::string>>);

int main() { Box<std::string> a{"x"}; Box<std::string> b = a; (void)b; }
```

`Box<int>` 中 #1 的约束满足，并且比没有约束的 #2 **更受约束**（[[g:more-constrained]]，按 [[temp.constr.order]] 比较），所以 #1 是合格的，#2 不是。类是否平凡可复制只看合格的那些函数，于是 `Box<int>` 平凡可复制。`Box<std::string>` 中 #1 的约束不满足，只剩 #2。

### 同类与合格

比较谁更受约束，只在同一种函数之间进行。第 5 段规定两个特殊成员函数满足下列条件之一时是**同类的**（of the same kind）：

- ¶5.1 都是默认构造函数；
- ¶5.2 都是复制或移动构造函数，并且第一个形参的类型相同；
- ¶5.3 都是复制或移动赋值运算符，并且第一个形参的类型相同，cv 限定和引用限定（如果有）也相同。

所以 `X(const X&)` 和 `X(X&)` 不是同类，可以同时合格。

¶6 **合格的特殊成员函数**（eligible special member function，[[g:eligible-special-member-function]]）满足三个条件：

- ¶6.1 没有被删除；
- ¶6.2 关联约束（如果有）得到满足；
- ¶6.3 不存在约束得到满足、并且更受约束的同类特殊成员函数。

合格这个概念用在几个地方：平凡可复制类只看合格的复制、移动操作和析构函数（[[class.prop#1]]）；隐式生存期类要求至少有一个合格的平凡构造函数（[[class.prop#8]]）；预置的特殊成员函数如果不合格，就被定义为弃置（[[dcl.fct.def.default#5]]）。

### 预期析构函数

析构函数没有形参，不能重载，带约束的多个版本只能另想办法。C++20 的做法是允许类声明多个预期析构函数，在类定义结束时，按空实参列表做一次重载决议选出真正的析构函数（[[class.dtor#4]]）：

```cpp run title="prospective-dtor.cpp" ok
#include <string>
#include <type_traits>

template<class T>
struct Holder {
  ~Holder()
    requires std::is_trivially_destructible_v<T>
    = default;                    // #1
  ~Holder() { /* 非平凡的清理 */ }  // #2
  T t;
};

static_assert(std::is_trivially_destructible_v<Holder<int>>);
static_assert(!std::is_trivially_destructible_v<Holder<std::string>>);

int main() { Holder<std::string> h{"x"}; (void)h; }
```

主流标准库的 `std::optional`、`std::variant`、`std::expected` 都用这套机制，在一个类模板里同时提供平凡和非平凡的版本。

## 预置的函数何时真正生成

编译器不会为每个类都生成六个函数体。[[dcl.fct.def.default#5]] 把预置的函数分成两种：

- 隐式声明的，或者在类内第一次声明时写 `= default` 的，不算**用户提供**（user-provided，[[g:user-provided]]）。如果没有被定义为弃置，它们在被 [[g:odr-use]] 或常量求值需要时才隐式定义。
- 先声明、之后在类外写 `= default` 的，算用户提供。它在 `= default` 处立即定义，而且因为是用户提供的，它不是平凡的。

```cpp run title="user-provided-default.cpp" ok
#include <type_traits>

struct A { A() = default; };  // 不是用户提供：可以平凡
struct B { B(); };
B::B() = default;             // 用户提供：不平凡

static_assert(std::is_trivially_default_constructible_v<A>);
static_assert(!std::is_trivially_default_constructible_v<B>);

int main() { }
```

类外 `= default` 的用处是把定义留在 .cpp 文件里，类的实现变了，头文件和二进制接口不变（[[dcl.fct.def.default#5]] 注 2）。Pimpl 类的析构函数常这样写：头文件里声明 `~Widget();`，在 `Impl` 已经完整的 .cpp 里写 `Widget::~Widget() = default;`。

隐式定义的特殊成员函数都是 `constexpr` 的（[[class.default.ctor#4]]、[[class.copy.ctor#13]]、[[class.copy.assign#10]]、[[class.dtor#9]]）。能不能在常量求值中调用，还要看函数实际做的事是否满足常量表达式的要求。

## 实现视角

!!! impl "惰性生成"
    隐式定义只在函数被 odr-use 时发生。所以一个含有不可复制成员的类，只要不复制它，就不会因为复制构造函数生成失败而报错。用 `clang++ -Xclang -ast-dump` 可以看到，隐式声明的成员在 AST 里标记为 `implicit`。

!!! impl "平凡与调用约定"
    平凡的复制、移动编译成 `memcpy` 或寄存器复制，平凡的默认构造和析构不生成任何代码。在 Itanium C++ ABI（Linux、macOS 上的 GCC 和 Clang）中，有不平凡的复制构造、移动构造或析构函数的类，以及复制、移动构造函数全部被删除的类，传参和返回时不能放进寄存器，要经过一个隐藏的指针。给类加一个空的析构函数，就可能改变它的调用约定。

## 历史与演进

!!! history "历史与演进"
    - C++98 有四个特殊成员函数：默认构造、复制构造、复制赋值和析构。用户不声明，编译器就隐式声明。
    - C++11 加入移动构造和移动赋值，引入 `= default` 和 `= delete`，形成了上面那张表。声明了析构或复制操作时仍然隐式声明另一个复制操作，这是为了不破坏 C++98 代码，所以只标为弃用。
    - C++20 引入合格、预期析构函数和条件平凡（[[P0848R3]]），析构函数也可以是 `constexpr` 的。
    - C++23 允许预置的复制赋值运算符使用显式对象形参（[[dcl.fct.def.default#2]]）。
    - C++26 中，联合体的默认构造函数和析构函数不再因为变体成员不平凡而被删除。弃用的隐式复制至今没有改为弃置。

## 常见误解

!!! pitfall "只加了一个析构函数，性能悄悄下降"
    `struct Big { std::vector<int> v; ~Big() { log(); } };` 中，用户声明的析构函数让移动操作不再隐式声明。`std::vector<Big>` 扩容、函数按值返回（不能省略复制时）都会复制整个 `v`。修复方法是补上 `Big(Big&&) = default;` 和 `Big& operator=(Big&&) = default;`，同时显式预置复制操作，否则它们会因为移动操作的声明而被删除。

!!! pitfall "以为 `= default` 一定可用"
    `= default` 只是请编译器按规则生成。如果规则要求删除，例如有引用成员的类的复制赋值，它就会被删除。Clang 默认开启的 `-Wdefaulted-function-deleted` 会提示这种情况。

!!! pitfall "以为构造函数模板会抑制隐式复制构造函数"
    模板永远不是复制或移动构造函数（[[class.copy.ctor#1]]），所以 `template<class T> X(T&&);` 不会阻止隐式声明 `X(const X&)`。但对非 `const` 左值，这个模板比 `X(const X&)` 匹配得更好，会抢走复制，见 [[class.copy.ctor]]。

!!! pitfall "预置函数的形参 const 与隐式版本不一致"
    [[dcl.fct.def.default#2]] 只允许预置的特殊成员函数在少数几处与隐式版本不同。隐式版本的形参是 `const C&` 时，可以预置一个形参为 `C&` 的版本（[[dcl.fct.def.default#2.4]]）。反过来，隐式版本是 `C&` 时（因为某个成员只有 `M(M&)` 这样的复制构造函数），预置 `const C&` 的版本：在第一次声明处预置，它被定义为弃置；在类外预置，程序非良构（[[dcl.fct.def.default#2.5]]）。

## 思考题

!!! question "思考题 1"
    下面这个类有哪些可用的特殊成员函数？

    ```cpp
    #include <string>
    struct S {
      S(int);
      S& operator=(const S&) = default;
      std::string s;
    };
    ```

<details markdown="1">
<summary>答案</summary>

- 默认构造函数：有用户声明的构造函数 `S(int)`，不声明。
- 复制构造函数：隐式声明为预置，但因为有用户声明的复制赋值运算符，这种情形已弃用，Clang 的 `-Wdeprecated-copy` 会警告。
- 复制赋值：用户声明，预置。
- 移动构造、移动赋值：有用户声明的复制赋值，都不声明。`S b = std::move(a);` 调用复制构造函数，`s` 被复制而不是移动。
- 析构函数：隐式声明为预置。
</details>

!!! question "思考题 2"
    声明了析构函数不会删除复制操作，声明了移动操作却会。C++11 为什么这样不对称？

<details markdown="1">
<summary>答案</summary>

为了兼容旧代码。C++98 代码里有大量只写了析构函数的类，有的析构函数只是打日志。如果 C++11 删除它们的复制操作，这些代码会无法编译，所以只能标为弃用。移动操作是 C++11 新增的，声明了移动操作的类一定是新代码，它的作者在考虑资源语义，这时逐成员复制很可能是错的（例如浅复制一个独占的资源），默认删除不会破坏任何旧代码。
</details>

!!! question "思考题 3"
    `struct A { int a; };` 之后写 `auto pm = &A::operator=;` 能编译吗？

<details markdown="1">
<summary>答案</summary>

不能。`A` 隐式声明了两个 `operator=`：复制赋值 `A& operator=(const A&)` 和移动赋值 `A& operator=(A&&)`。`&A::operator=` 是一个重载集，`auto` 无法推导出唯一的类型。要像 `call-implicit.cpp` 那样给出目标类型：`A& (A::*pm)(const A&) = &A::operator=;`。第 2 段说可以对隐式声明的函数取成员指针，规则与对普通重载函数取地址相同（[[over.over]]）。
</details>

## 小结

| 概念 | 要点 |
|---|---|
| 特殊成员函数 | 默认构造、复制构造、移动构造、复制赋值、移动赋值、（预期）析构 |
| 隐式声明 | 在类定义的 `}` 处；程序不能定义隐式声明的函数 |
| 相互影响 | 任何构造函数都抑制默认构造；复制操作或析构抑制移动操作；移动操作使复制操作被删除；复制操作或析构使另一个复制操作弃用 |
| 弃置 | 生成的版本会出错时定义为弃置；被删除的预置移动操作不参与重载决议 |
| 潜在构造的子对象 | 直接数据成员、非虚直接基类，以及非抽象类的虚基类 |
| 合格 | 未删除、约束满足、没有更受约束的同类函数；决定平凡可复制等性质 |
| 预期析构函数 | 可以有多个，类定义结束时由重载决议选出析构函数 |
| 隐式定义 | odr-use 或常量求值需要时才生成；类外 `= default` 是用户提供的，不平凡；隐式定义的都是 `constexpr` |

<details class="fine" markdown="1"><summary>其余条文</summary>

¶1 的注 1 说明实现会为某些类隐式声明特殊成员函数，并在需要时隐式定义它们（[[dcl.fct.def.default]]）。¶3 的注 2 说明特殊成员函数影响类对象怎样创建、复制、移动、销毁，以及值怎样转换为其他类型，它们往往是隐式调用的。

</details>
