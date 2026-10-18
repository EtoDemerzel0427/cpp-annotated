---
title: 声明与定义
summary: 每个声明默认都是定义，除了 22 种例外；重声明与首次声明；隐式定义的特殊成员函数；被定义的对象不能是不完整类型或抽象类。
status: done
related: basic.pre, basic.def.odr, basic.link, dcl.stc, class.static.data, module.reach
tags: 声明, 定义, ODR
updated: 2026-10-17
---

"声明"与"定义"的区分是 C++ 分离编译模型的核心：**声明**告诉编译器"有这么个东西，它的类型是这样的"，足以让编译器检查用法、生成调用；**定义**则真正提供它——为变量分配存储、为函数给出函数体、为类给出完整的成员列表。一个实体可以声明很多次，但只能（按 [[basic.def.odr]] 的规则）定义一次或"一致地"定义多次。

本节的写法很有意思：它不去正面描述"什么是定义"，而是说**每个声明都是定义，除非**它落在 22 种例外之一（¶2）。这是个"默认是定义"的规则——想让声明不成为定义，必须用某个明确的语法手段（省略函数体、加 `extern`、写在类内的 `static` 成员……）。

阅读前需要：[[basic.pre]] 中"声明"（¶5 的清单）、"实体"的含义。

## 声明的作用；重声明与首次声明（¶1）

¶1 一个声明可以向翻译单元（重新）引入一个或多个名字和/或实体。如果引入了，声明就规定了这些名字的解释和语义性质（类型、链接、存储期……）。

**重声明**（redeclaration）与**首次声明**（first declaration）的定义：实体 X 的一个声明，如果从它出发**可达**（reachable，[[module.reach]]）X 的另一个声明，它就是 X 的重声明；否则是首次声明。

!!! std
    A declaration of an entity X is a *redeclaration* of X if another declaration of X is reachable from it; otherwise, it is a *first declaration*.

为什么用"可达"而不是"在它前面"？因为模块：在模块单元中，一个声明是否"之前出现过"不再是简单的文本先后，而取决于导入关系形成的可达性。用"可达"统一了头文件时代和模块时代的说法。不少规则正是围绕"首次声明"或"之前可达的声明"来写的，例如：

- 若某函数/变量的定义在它**首次被声明为 inline** 的位置已经可达，程序非良构——不能先定义、后补 `inline`（[[dcl.inline#4]]）；
- `[[noreturn]]` 只要出现在任一声明上，就必须出现在函数的**首次声明**上（[[dcl.attr.noreturn]]）；
- 默认实参不能被后面的声明重新给出，哪怕值相同（[[dcl.fct.default]]）。

Note 1 列举了声明除"引入名字"之外的其他作用：静态断言、控制模板实例化（显式实例化）、为构造函数提供推导指引、使用属性，以及空声明——什么都不做。

## 什么样的声明不是定义（¶2）

¶2 **声明所声明的每个实体，同时也被这个声明定义**，除非下列之一成立。为了便于记忆，按类别分组：

### 函数与变量：没有"实体内容"

| ¶ | 例外 | 例子 |
|---|---|---|
| 2.1 | 声明函数但不给出函数体 | `int f(int);` |
| 2.2 | 含 `extern` 说明符或 *linkage-specification*，且既无初始化器也无函数体 | `extern int a;`、`extern "C" int g(int);` |
| 2.3 | 类定义中的非 inline 静态数据成员 | `struct X { static int y; };` |
| 2.4 | 在类外再次声明一个类内用 `constexpr` 定义的静态数据成员（**已弃用**） | `constexpr int X::n;` |
| 2.8 | 不是函数定义一部分的函数声明符里的 *parameter-declaration* | `int f(int x);` 里的 `x` |

¶2.2 的关键是"**且**既无初始化器也无函数体"：`extern const int c = 1;` 有初始化器，所以**是定义**——这是在命名空间作用域定义一个具有外部链接的 `const` 变量的标准写法（否则 `const` 会让它获得内部链接，[[basic.link#3]]）。

脚注 12 点出一个容易误解的地方：`extern "C" { ... }` 大括号形式里的声明，是否为定义**不受**链接规范影响。所以：

```cpp run ok
extern "C" int cvar2;          // 声明：单个声明形式的 linkage-specification 相当于加了 extern
extern "C" { int cvar; }       // 定义！大括号内的 int cvar; 和外面写一样
extern "C" int cfun(int);      // 声明（本来也没有函数体）
int main() { }
```

¶2.3 是 C++17 之前"类内 `static const int N = 10;` 还要在类外补一个定义"的根源；C++17 引入 inline 变量后，`static inline` 和 `static constexpr`（隐式 inline，[[dcl.constexpr]]）的静态数据成员在类内声明即是定义。但注意：**`static const int` 不是隐式 inline**，它在类内仍然只是声明，被 odr-use 时仍需类外定义（见下方陷阱）。

¶2.4 是 C++17 遗留的兼容规则：C++14 代码里为 `static constexpr` 成员写的类外定义 `constexpr int X::n;`，在 C++17 里变成了一个冗余的**重声明**（不是定义，否则就和类内的 inline 定义重复了），并被标为弃用（[[depr.static.constexpr]]）。

### 类型：只给名字，不给内容

| ¶ | 例外 | 例子 |
|---|---|---|
| 2.5 | *elaborated-type-specifier* | `struct S;`、`struct S* p;` 中的 `struct S` |
| 2.6 | *opaque-enum-declaration* | `enum class E : int;`、`enum F : long;` |
| 2.9 | typedef 声明 | `typedef int Int;` |
| 2.10 | *alias-declaration* | `using Int = int;` |

类型别名不是定义——它定义不了任何新东西，只是给已有类型一个新名字。所以 `typedef` 可以在同一作用域重复（只要一致），而且不受 ODR "每个 TU 一个定义"的约束。

### 纯"指令性"的声明

| ¶ | 例外 |
|---|---|
| 2.7 | *template-parameter* |
| 2.11 | *namespace-alias-definition*（名字里虽有 definition，却**不是定义**） |
| 2.12 | *using-declaration* |
| 2.13 | *deduction-guide* |
| 2.14 | *static_assert-declaration* |
| 2.15 | *consteval-block-declaration* {{c++26}} |
| 2.16 | *attribute-declaration* |
| 2.17 | *empty-declaration* |
| 2.18 | *using-directive* |
| 2.19 | *using-enum-declaration* |

¶2.11 是标准里一个著名的"名字骗人"：语法非终结符叫 *namespace-alias-definition*，语义上却不是定义。同理 *concept-definition* 名字里有 definition，**是**定义（见 ¶2.20）。

¶2.15 的 `consteval { ... }` 块 {{c++26}} 是静态反射带来的新声明形式：它在常量求值中执行一段代码（例如调用 `std::meta::define_aggregate` 生成一个类的定义），自身不定义任何东西。它**产生**的注入声明（injected declaration）可以是定义，那是另一回事（[[expr.const.reflect]]、[[basic.def.odr#15]]）。

### 模板相关

| ¶ | 例外 | 例子 |
|---|---|---|
| 2.20 | *template-declaration*，其 *template-head* 之后既不是 *concept-definition*，也不是定义函数/类/变量/静态数据成员的声明 | `template<class T> struct Box;`、`template<class T> void f(T);` |
| 2.21 | 显式实例化**声明** | `extern template struct Box<long>;` |
| 2.22 | *explicit-specialization*，其 *declaration* 不是定义 | `template<> struct Box<void>;` |

¶2.20 说白了就是：模板声明是否为定义，取决于模板头后面那个声明是否为定义。

```cpp run ok
template<class T> struct Box;          // 声明
template<class T> struct Box { T t; }; // 定义（定义了类模板 Box）
template<> struct Box<void>;           // 显式特化的声明，不是定义（¶2.22）
template struct Box<int>;              // 显式实例化定义：是定义
extern template struct Box<long>;      // 显式实例化声明：不是定义（¶2.21）
template<class T> concept C = true;    // concept-definition：是定义
int main() { }
```

!!! note "显式实例化定义"
    `template struct Box<int>;` 不在例外清单中，所以是（`Box<int>` 及其成员的）定义；这正是它能和 `extern template` 配合、实现"只在一个 TU 里实例化"的语义基础（[[temp.explicit]]）。

### 标准例子的逐行注释

¶2 的 Example 1 值得逐行看一遍，下面是加了解释的版本：

```cpp run ok
int a;                          // 定义 a：没有 extern，即使无初始化器也是定义
extern const int c = 1;         // 定义 c：有 extern 但也有初始化器
int f(int x) { return x+a; }    // 定义 f，并定义形参 x（¶2.8 只排除非定义的函数声明符）
struct S { int a; int b; };     // 定义 S、S::a、S::b
struct X {                      // 定义 X
  int x;                        // 定义非静态数据成员 x
  static int y;                 // 只声明静态数据成员 y（¶2.3）
  X(): x(0) { }                 // 定义 X 的构造函数
};
int X::y = 1;                   // 定义 X::y
enum { up, down };              // 定义 up 和 down（以及这个无名枚举类型）
namespace N { int d; }          // 定义 N 和 N::d
X anX;                          // 定义 anX

extern int a;                   // 只声明
extern const int c;             // 只声明
int f(int);                     // 只声明
struct S;                       // 只声明
typedef int Int;                // 只声明
namespace N1 = N;               // 只声明
extern X anotherX;              // 只声明
using N::d;                     // 只声明
int main() { }
```

!!! lawyer "非静态数据成员的声明是定义"
    `struct S { int a; };` 里的 `int a;` 不在任何例外中，所以它**定义**了非静态数据成员 `S::a`。这与"类内的 `static int y;` 只是声明"形成对照。非静态数据成员没有独立存储，但标准仍然说它被定义了——"定义"是一个纯语义概念，并不等同于"分配存储"。

!!! lawyer "命名空间定义可以出现多次"
    `namespace N { }` 是 *namespace-definition*，它确实定义了 N。但命名空间不是 [[basic.def.odr#1]] 所列的"可定义项"，所以 ODR 的"每个 TU 至多一个定义"不约束它——这就是命名空间可以反复打开的原因。

## 隐式定义的特殊成员函数（¶3）

¶3（注）在某些情况下，实现会**隐式定义**默认构造函数（[[class.default.ctor]]）、拷贝/移动构造函数（[[class.copy.ctor]]）、拷贝/移动赋值运算符（[[class.copy.assign]]）和析构函数（[[class.dtor]]）。

精确地说，"隐式**声明**"和"隐式**定义**"是两步：

1. 类定义结束时，编译器按规则隐式**声明**这些特殊成员（如果用户没声明、且没被抑制）；
2. 当某个特殊成员被 **odr-use**（或常量求值需要它）时，它才被隐式**定义**（[[class.default.ctor#4]] 等）。

第二步正是 ODR 的一部分：[[basic.def.odr#17]] 规定，隐式定义要视为在**每个**odr-use 它的 TU 中各发生一次，而且各 TU 里的隐式定义必须调用相同的子对象构造函数——否则违反 ODR。

标准的 Example 2：

```cpp run ok
#include <string>

struct C {
  std::string s;
};

int main() {
  C a;        // odr-use 默认构造函数 → 隐式定义
  C b = a;    // odr-use 拷贝构造函数 → 隐式定义
  b = a;      // odr-use 拷贝赋值 → 隐式定义
}             // 析构函数被潜在调用 → 隐式定义
```

实现会使 `C` 的定义**等价于**：

```cpp
struct C {
  std::string s;
  C() : s() { }
  C(const C& x): s(x.s) { }
  C(C&& x): s(static_cast<std::string&&>(x.s)) { }
  C& operator=(const C& x) { s = x.s; return *this; }
  C& operator=(C&& x) { s = static_cast<std::string&&>(x.s); return *this; }
  ~C() { }
};
```

"等价于"只是语义上的近似：真正的隐式定义还保留着 `= default` 的特性——例如它们可能是平凡的（trivial）、可能是 `constexpr` 的、`noexcept` 由子对象推导，而手写版本都会丢掉这些性质。

## elaborated-type-specifier 也能声明类名（¶4）

¶4（注）类名也可以由 *elaborated-type-specifier* 隐式声明（[[dcl.type.elab]]）。例如：

```cpp run ok
void f(struct Q* q);   // 这里第一次出现 Q：同时声明了类 Q（属于全局命名空间）
Q* p = nullptr;        // OK：Q 已经声明
int main() { }
```

它的目标作用域规则（为什么 `Q` 属于全局命名空间而不是函数形参作用域）见 [[basic.scope.pdecl#7]] 与 [[dcl.type.elab]]。

## 被定义的对象必须是完整的、非抽象的（¶5）

¶5 在**对象的定义**中，对象的类型不能是：

- 不完整类型（[[basic.types.general]]），
- 抽象类类型（[[class.abstract]]），
- 或它们的（可能多维的）数组。

为什么只约束**定义**？因为定义要分配存储并初始化——编译器必须知道大小（不完整类型做不到），也必须能构造出一个**完整对象**（抽象类不允许作为最派生对象存在）。只是**声明**一个对象则不需要这些信息：`extern Incomplete obj;` 完全合法，等它在别处定义即可。

```cpp error
struct Inc;
struct Abs { virtual void f() = 0; };

Inc i;          // error: 定义不完整类型的对象
Abs a;          // error: 定义抽象类类型的对象
Abs arr[2];     // error: 抽象类的数组
extern Inc ei;  // OK：只是声明
extern Abs ea;  // OK（按标准）：只是声明——但 Clang 也会拒绝，见下
Inc* pi;        // OK：指针类型是完整的
void take(Inc); // OK：函数声明（非定义）中形参类型可以不完整
```

!!! impl "Clang 对 `extern Abs ea;` 的处理"
    C++20 起，抽象类的限制被收窄到"定义对象、定义或调用以它为形参/返回类型的函数、显式转换"等真正需要完整对象的场合（[[class.abstract#3]] 的注）。按此，`extern Abs ea;` 只是一个声明，是良构的。截至写作时，本机的 Clang 23 仍对它报"variable type 'Abs' is an abstract class"——这是实现落后于标准的地方。

## 实现视角

!!! impl "声明与定义在目标文件中的样子"
    - 对一个只声明、被 odr-use 的函数或变量，编译器在目标文件里产生一个**未定义符号**（`nm` 中的 `U`），留给链接器去别的目标文件里找。定义则产生一个**已定义符号**（`T` 代码、`D`/`B` 数据等）。
    - "声明 vs 定义"决定了 `extern int a;` 不占空间，而 `int a;` 在 `.bss` 中分配 4 字节。C 语言里 `int a;` 是"试探性定义"（tentative definition），C 编译器曾长期把它放进 common 段、允许多个 TU 重复（GCC 10、Clang 11 起 C 也默认 `-fno-common`）——**C++ 没有试探性定义**，两个 TU 都写 `int a;` 就违反了 ODR（[[basic.def.odr#16]]），C++ 编译器把它当普通的强定义，链接时报重复符号。
    - 类定义、类型别名、模板声明本身不产生任何符号；只有它们引出的函数、变量、vtable、typeinfo 才会。

## 历史与演进

!!! history "C++98 → C++26"
    - C++98 就有"声明默认是定义，除非……"的写法，当时的例外不到十条（无函数体、`extern`、类内静态成员、类名声明、模板形参、函数声明中的形参、typedef、using 声明/指令）。
    - C++11：加入 *alias-declaration*、*static_assert-declaration*、*attribute-declaration*、*empty-declaration*、opaque enum 声明、显式实例化声明（`extern template`）。
    - C++17：inline 变量（P0386）让类内 `static inline` / `static constexpr` 成员成为定义，同时加入 ¶2.4 的弃用条款；加入推导指引。
    - C++20：*using-enum-declaration*；概念（*concept-definition* 是定义）；模块让"重声明"改用"可达"来定义。
    - C++26：`consteval` 块（¶2.15）；注入声明。

## 陷阱

!!! pitfall "`static const int` 成员不是隐式 inline"
    常见误解："C++17 后类内静态常量成员都是 inline 的。"错——只有 `constexpr` 静态数据成员是隐式 inline（[[dcl.constexpr]]）。`static const int N = 0;` 在类内仍然**只是声明**（¶2.3）。只读它的值不构成 odr-use，所以平时看不出问题；一旦把它绑定到引用（例如 `std::max(S::N, 1)`，形参是 `const int&`），就 odr-use 了它，链接时会报 `S::N` 未定义——即使用 `-std=c++2c`。

    ```cpp
    #include <algorithm>
    struct S { static const int N = 0; };      // 声明，不是定义
    int main() { return std::max(S::N, 1); }   // odr-use S::N：链接失败（IFNDR）
    ```

    修复：写成 `static constexpr int N = 0;` 或 `static inline const int N = 0;`，或在某个 .cpp 中补 `const int S::N;`。

!!! pitfall "`extern` 加初始化器就成了定义"
    `extern int x = 1;` 是定义（¶2.2 要求"无初始化器"才算例外）。把它放进头文件，包含两次就是重复定义。Clang/GCC 会对 `extern` 带初始化器给出警告，但它确实合法。

## 思考题

!!! question "思考题 1"
    以下声明中，哪些是定义？

    ```cpp
    struct A { static constexpr int n = 1; static const int m = 2; static int k; };
    constexpr int A::n;
    const int A::m;
    template<class T> void f(T);
    template<> void f<int>(int);
    template<> void f<char>(char) { }
    namespace NS = std;
    extern "C" { void g(); int v; }
    ```

<details markdown="1">
<summary>答案</summary>

- `A::n`：类内声明**是定义**（`constexpr` 静态成员隐式 inline）；类外 `constexpr int A::n;` 不是定义（¶2.4，已弃用）。
- `A::m`：类内是声明（¶2.3）；类外 `const int A::m;` 是定义。
- `A::k`：只有类内声明，没有定义。
- `A` 本身：类定义，定义了 `A`。
- `template<class T> void f(T);`：不是定义（¶2.20）。
- `template<> void f<int>(int);`：显式特化，其声明不是定义（¶2.22）。
- `template<> void f<char>(char) { }`：显式特化的定义。
- `namespace NS = std;`：不是定义（¶2.11）。
- `extern "C" { void g(); int v; }`：`g` 是声明（无函数体）；`v` 是**定义**（脚注 12：大括号形式不影响是否为定义）。
</details>

!!! question "思考题 2"
    为什么 `extern Abs ea;` 应该是合法的，而 `Abs f();`（函数声明，返回抽象类）呢？

<details markdown="1">
<summary>答案</summary>

两者都合法。¶5 只约束对象的**定义**；[[class.abstract]] 的注说明抽象类不能用作"被**定义**或被**调用**的函数"的形参或返回类型——单纯的函数声明不受影响。这是 C++20 收窄抽象类限制后的结果：只有真正需要构造一个抽象类完整对象的地方才报错。
</details>

## 小结

- 声明**默认**是定义；¶2 列出 22 种例外。
- 常见的"非定义"：无函数体的函数声明、`extern` 且无初始化器、类内非 inline 静态数据成员、`struct S;`、opaque enum、typedef/using 别名、各种 using、`static_assert`、模板（未定义体的）声明、`extern template`、无定义体的显式特化。
- 名字骗人的两个：*namespace-alias-definition* **不是**定义；*concept-definition* **是**定义。
- `extern "C" { int v; }` 是定义；`extern "C" int v;` 不是。
- 隐式特殊成员函数在被 odr-use 时才被隐式定义，并受 ODR 约束（[[basic.def.odr#17]]）。
- 对象的**定义**不能是不完整类型或抽象类（及其数组），声明可以。
