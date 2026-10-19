---
title: 声明与定义
summary: 声明默认就是定义，只有 22 种情形例外；什么是重声明和首次声明；特殊成员函数的隐式定义；被定义的对象不能是不完整类型或抽象类。
status: done
related: basic.pre, basic.def.odr, basic.link, dcl.stc, class.static.data, module.reach
tags: 声明, 定义, ODR
updated: 2026-10-19
---

!!! tldr
    - 声明告诉编译器一个实体存在、类型是什么；定义真正提供它：变量的存储、函数的函数体、类的完整成员列表。
    - 标准不正面定义什么是定义，而是规定每个声明都是定义，除非它属于 ¶2 列出的 22 种例外，例如没有函数体的函数声明、不带初始化器的 `extern` 声明、类内的非 inline 静态数据成员。
    - `extern "C" { int v; }` 是定义，`extern "C" int v;` 不是；`static const int` 成员在类内只是声明，`static constexpr` 成员是定义。
    - 如果从一个声明出发可以到达同一实体的另一个声明，它就是重声明，否则是首次声明。
    - 定义对象时，类型不能是不完整类型或抽象类；只是声明则没有这个限制。

## 声明与定义的区别

<div class="compare" markdown="1">

```cpp
// 只是声明
extern int a;
int f(int);
struct S;
struct X { static int y; };
```

```cpp
// 定义
int a;
int f(int x) { return x + a; }
struct S { int m; };
int X::y = 1;
```

</div>

**声明**（declaration，[[basic.pre]] 的 ¶5 列出了所有形式）告诉编译器有这样一个实体、它的类型是什么，这足以检查用法、生成调用。**定义**（definition）则真正提供它：为变量分配存储，为函数给出函数体，为类给出完整的成员列表。

C++ 把程序分成多个翻译单元分别编译，靠的就是这种区分。每个翻译单元只需要看到声明就能编译，定义只要在某一个翻译单元里出现一次，链接时就能找到。一个实体可以声明很多次，但定义的次数受 [[basic.def.odr|ODR]] 约束。

## 哪些声明不是定义（¶2）

¶2 规定，声明所声明的每个实体同时也由这个声明定义，除非属于下面 22 种例外之一。要让一个声明不成为定义，必须用某种明确的写法，例如省略函数体、加 `extern`、在类内声明 `static` 成员。

### 函数和变量：没有给出内容

| ¶ | 例外 | 例子 |
|---|---|---|
| 2.1 | 声明函数但不给函数体 | `int f(int);` |
| 2.2 | 带 `extern` 或链接规范，且既无初始化器也无函数体 | `extern int a;`、`extern "C" int g(int);` |
| 2.3 | 类定义里的非 inline 静态数据成员 | `struct X { static int y; };` |
| 2.4 | 在类外重新声明一个类内用 `constexpr` 定义的静态数据成员（已弃用） | `constexpr int X::n;` |
| 2.8 | 不属于函数定义的函数声明符里的形参声明 | `int f(int x);` 的 `x` |

¶2.2 的关键是既无初始化器这个条件。`extern const int c = 1;` 有初始化器，所以是定义。在命名空间作用域定义一个有外部链接的 `const` 变量，就要这样写，因为不加 `extern` 的 `const` 变量具有内部链接（[[basic.link#3]]）。

脚注 12 补充：写在 `extern "C" { ... }` 大括号里的声明，是否为定义不受链接规范影响。

```cpp run ok
extern "C" int cvar2;      // 声明：单个声明形式的链接规范相当于 extern
extern "C" { int cvar; }   // 定义：和写在大括号外面一样
extern "C" int cfun(int);  // 声明：本来就没有函数体
int main() { }
```

¶2.3 解释了为什么 C++17 之前类内的 `static const int N = 10;` 还要在类外补一个定义。C++17 引入 inline 变量之后，`static inline` 成员和 `static constexpr` 成员（`constexpr` 隐含 `inline`，[[dcl.constexpr]]）在类内声明就是定义。`static const int` 成员不是 inline 的，在类内仍然只是声明，见下文的常见误解。

¶2.4 是为 C++14 代码保留的兼容规则。C++14 里为 `static constexpr` 成员写的类外定义 `constexpr int X::n;`，到 C++17 变成了多余的重声明，被标为弃用（[[depr.static.constexpr]]）。它不能算定义，否则就和类内的 inline 定义重复了。

### 类型：只给名字或别名

| ¶ | 例外 | 例子 |
|---|---|---|
| 2.5 | *elaborated-type-specifier* | `struct S;`、`struct S* p;` 里的 `struct S` |
| 2.6 | *opaque-enum-declaration*（不带枚举项列表的枚举声明） | `enum class E : int;` |
| 2.9 | typedef 声明 | `typedef int Int;` |
| 2.10 | *alias-declaration* | `using Int = int;` |

类型别名只是给已有类型起一个新名字，不定义任何东西。所以同一作用域里可以重复写一致的 `typedef`，ODR 也不管它。

### 只起指示作用的声明

| ¶ | 例外 |
|---|---|
| 2.7 | 模板形参 |
| 2.11 | *namespace-alias-definition*（名字里有 definition，却不是定义） |
| 2.12 | *using-declaration* |
| 2.13 | 推导指引 |
| 2.14 | `static_assert` 声明 |
| 2.15 | `consteval { ... }` 块 {{c++26}} |
| 2.16 | 属性声明 `[[attr]];` |
| 2.17 | 空声明 `;` |
| 2.18 | *using-directive* |
| 2.19 | `using enum` 声明 |

¶2.15 的 `consteval` 块是 C++26 静态反射带来的声明形式，它在常量求值中执行一段代码，自身不定义任何东西。它可以通过 `std::meta::define_aggregate` 生成一个类的定义，那个定义叫注入声明（[[expr.const.reflect]]），是另一个声明。

### 模板

| ¶ | 例外 | 例子 |
|---|---|---|
| 2.20 | 模板声明，模板头后面既不是概念定义，也不是定义函数、类、变量或静态数据成员的声明 | `template<class T> void f(T);` |
| 2.21 | 显式实例化声明 | `extern template struct Box<long>;` |
| 2.22 | 显式特化，其中的声明不是定义 | `template<> struct Box<void>;` |

¶2.20 的意思很简单：模板声明是不是定义，看模板头后面的那个声明是不是定义。

```cpp run ok
template<class T> struct Box;           // 声明
template<class T> struct Box { T t; };  // 定义
template<> struct Box<void>;            // 显式特化的声明（¶2.22）
template struct Box<int>;               // 显式实例化定义：是定义
extern template struct Box<long>;       // 显式实例化声明（¶2.21）
template<class T> concept C = true;     // 概念定义：是定义
int main() { }
```

显式实例化定义 `template struct Box<int>;` 不在例外里，所以它定义了 `Box<int>` 及其成员。`extern template` 配合它，可以让一个特化只在一个翻译单元里实例化（[[temp.explicit]]）。

### 标准的例子

¶2 的例 1 汇总了上面的规则：

```cpp run ok
int a;                        // 定义：没有 extern，无初始化器也是定义
extern const int c = 1;       // 定义：有 extern 但有初始化器
int f(int x) { return x+a; }  // 定义 f 和形参 x
struct S { int a; int b; };   // 定义 S、S::a、S::b
struct X {                    // 定义 X
  int x;                      // 定义非静态数据成员 x
  static int y;               // 只声明（¶2.3）
  X(): x(0) { }               // 定义构造函数
};
int X::y = 1;                 // 定义 X::y
enum { up, down };            // 定义 up 和 down
namespace N { int d; }        // 定义 N 和 N::d
X anX;                        // 定义 anX

extern int a;                 // 以下都只是声明
extern const int c;
int f(int);
struct S;
typedef int Int;
namespace N1 = N;
extern X anotherX;
using N::d;
int main() { }
```

类内的 `int x;` 不属于任何例外，所以它定义了非静态数据成员 `X::x`。成员没有独立的存储，但标准仍然说它被定义了：定义是语义上的概念，不等于分配存储。

`namespace N { }` 也是定义，但命名空间不是 ODR 的可定义项（[[basic.def.odr#1]]），所以可以反复打开同一个命名空间。

## 重声明与首次声明（¶1）

¶1 一个声明可以向翻译单元引入一个或多个名字或实体，并规定它们的类型、链接等性质。

!!! std
    A declaration of an entity X is a *redeclaration* of X if another declaration of X is reachable from it; otherwise, it is a *first declaration*.

如果从实体 X 的一个声明出发，可以到达（reachable，[[module.reach]]）X 的另一个声明，这个声明就是**重声明**（redeclaration），否则是**首次声明**（first declaration）。在普通头文件代码里，可到达大致就是出现在前面；在模块里，还取决于导入关系。用可到达来表述，同一条规则就能同时覆盖两种情形。

不少规则是围绕首次声明写的：

- 不能先定义、后补 `inline`：如果在首次声明为 inline 的位置已经能看到定义，程序非良构（[[dcl.inline#4]]）；
- 如果任何一个声明带 `[[noreturn]]`，首次声明就必须带它（[[dcl.attr.noreturn]]）；
- 后面的声明不能重新给出默认实参，值相同也不行（[[dcl.fct.default]]）。

注 1 列出了声明除了引入名字以外的作用：静态断言、控制模板实例化、为构造函数提供推导指引、使用属性，以及空声明什么也不做。

## 被定义的对象必须完整、非抽象（¶5）

¶5 定义对象时，对象的类型不能是不完整类型（[[basic.types.general]]）、抽象类（[[class.abstract]]），或它们的数组。

定义要分配存储并构造对象，所以编译器必须知道大小，而且必须能构造出一个完整对象。只是声明一个对象不需要这些，`extern Inc ei;` 是合法的，只要别处有定义。

```cpp error
struct Inc;
struct Abs { virtual void f() = 0; };

Inc i;           // error: 不完整类型
Abs a;           // error: 抽象类
Abs arr[2];      // error: 抽象类的数组
extern Inc ei;   // OK：只是声明
extern Abs ea;   // 按标准 OK，但 Clang 拒绝，见下
Inc* pi;         // OK：指针类型是完整的
void take(Inc);  // OK：非定义的函数声明
Abs make();      // OK：同上
```

!!! impl "Clang 对 `extern Abs ea;` 的处理"
    C++20 的 [[P0929R2]] 把抽象类的限制收窄到真正需要完整对象的场合：定义对象，定义或调用以它为形参或返回类型的函数，显式转换到它（[[class.abstract#3]] 的注）。按此，`extern Abs ea;` 只是声明，是良构的。本机 Clang 23 仍然报 "variable type 'Abs' is an abstract class"，这是实现落后于标准的地方；`Abs make();` 则正常接受。

## 隐式定义的特殊成员函数（¶3）

```cpp run ok
#include <string>
struct C {
  std::string s;
};
int main() {
  C a;      // 用到默认构造函数，它被隐式定义
  C b = a;  // 拷贝构造函数
  b = a;    // 拷贝赋值运算符
}           // 析构函数
```

¶3 是一条注：在某些情况下，实现会**隐式定义**默认构造函数、拷贝和移动构造函数、拷贝和移动赋值运算符以及析构函数。

这里有两步。类定义结束时，如果用户没有声明某个特殊成员、它也没有被抑制，编译器就隐式声明它。之后只有当它被 odr-use（被实际用到，因而需要定义，见 [[basic.def.odr]]）或者常量求值需要它时，才会被隐式定义（例如 [[class.default.ctor#4]]）。

标准的例 2 说，上面的 `C` 等价于下面的写法：

```cpp
struct C {
  std::string s;
  C() : s() { }
  C(const C& x): s(x.s) { }
  C(C&& x): s(static_cast<std::string&&>(x.s)) { }
  C& operator=(const C& x) { s = x.s; return *this; }
  C& operator=(C&& x) {
    s = static_cast<std::string&&>(x.s); return *this;
  }
  ~C() { }
};
```

这只是语义上的近似。隐式定义的版本保留着默认函数的性质：可能是平凡的，可能是 `constexpr` 的，`noexcept` 由子对象推导。手写的版本会丢掉这些性质。

隐式定义也受 ODR 约束：[[basic.def.odr#17]] 规定，它视为在每个用到它的翻译单元里各发生一次，各处必须调用相同的子对象构造函数。

¶4 是另一条注：*elaborated-type-specifier* 也能隐式声明一个类名。

```cpp run ok
void f(struct Q* q);  // 第一次出现 Q：同时声明了全局的类 Q
Q* p = nullptr;       // OK
int main() { }
```

`Q` 为什么属于全局命名空间而不属于函数形参作用域，见 [[dcl.type.elab]]。

## 实现视角

!!! impl "声明与定义在目标文件里的样子"
    - 只有声明的函数或变量被用到时，目标文件里出现一个未定义符号（`nm` 显示为 `U`），由链接器到别的目标文件里找。定义产生已定义符号（代码为 `T`，数据为 `D` 或 `B`）。
    - C 语言的 `int a;` 是[[g:tentative-definition|试探性定义]]，C 编译器曾长期把它放进 common 段，允许多个翻译单元重复（GCC 10、Clang 11 起 C 也默认 `-fno-common`）。C++ 没有试探性定义，两个翻译单元都写 `int a;` 就违反了 ODR（[[basic.def.odr#16]]），链接时报重复符号。
    - 类定义、类型别名、模板声明本身不产生符号，只有由它们产生的函数、变量、vtable、typeinfo 才会。

## 历史与演进

!!! history
    - C++98 就采用了声明默认是定义、列出例外的写法，当时的例外不到十条。
    - C++11 加入了别名声明、`static_assert`、属性声明、空声明、opaque enum 声明和 `extern template`。
    - C++17 的 inline 变量（[[P0386R2]]）让类内的 `static inline` 和 `static constexpr` 成员成为定义，并留下了 ¶2.4 的弃用条款；同时加入推导指引。
    - C++20 加入 `using enum` 和概念；因为模块，重声明改用可到达来定义。
    - C++26 加入 `consteval` 块（¶2.15）。

## 常见误解

!!! pitfall "C++17 之后类内的静态常量成员都是 inline 的"
    只有 `constexpr` 静态数据成员隐含 inline（[[dcl.constexpr]]）。`static const int N = 0;` 在类内仍然只是声明。只读它的值不需要定义，所以平时看不出问题；一旦把它绑定到引用，比如传给形参是 `const int&` 的 `std::max`，就需要定义了。

    ```cpp
    #include <algorithm>
    struct S { static const int N = 0; };     // 只是声明
    int main() { return std::max(S::N, 1); }  // 需要 S::N 的定义
    ```

    本机 Clang 23 在 `-O0` 下链接失败（`"S::N", referenced from`），在 `-O2` 下调用被内联、常量被折叠，碰巧链接成功。按标准，这个程序缺少定义，属于不要求诊断的错误。修复办法是写成 `static constexpr int N = 0;` 或 `static inline const int N = 0;`，或者在某个 .cpp 里补上 `const int S::N;`。

!!! pitfall "`extern` 声明一定不是定义"
    `extern int x = 1;` 是定义，因为 ¶2.2 只排除没有初始化器的情形。把它放进头文件，被两个翻译单元包含就是重复定义。Clang 对它给出 `-Wextern-initializer` 警告，但它确实合法。

## 思考题

!!! question "思考题 1"
    下面哪些声明是定义？

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

- `A` 的类定义定义了 `A`。
- `A::n`：类内是定义（`constexpr` 隐含 inline），类外的 `constexpr int A::n;` 不是定义（¶2.4，已弃用）。
- `A::m`：类内是声明（¶2.3），类外的 `const int A::m;` 是定义。
- `A::k`：只有类内声明，没有定义。
- `template<class T> void f(T);` 不是定义（¶2.20）；`template<> void f<int>(int);` 也不是（¶2.22）；`template<> void f<char>(char) { }` 是显式特化的定义。
- `namespace NS = std;` 不是定义（¶2.11）。
- `extern "C" { void g(); int v; }`：`g` 没有函数体，只是声明；`v` 是定义（脚注 12）。
</details>

!!! question "思考题 2"
    `extern Abs ea;` 和 `Abs make();`（`Abs` 是抽象类）合法吗？

<details markdown="1">
<summary>答案</summary>

都合法。¶5 只约束对象的定义。[[class.abstract#3]] 的注说明，抽象类不能用作被定义或被调用的函数的形参或返回类型，单纯的函数声明不受影响。
</details>

## 小结

- 声明默认是定义，¶2 列出 22 种例外。
- 常见的非定义声明：没有函数体的函数声明、不带初始化器的 `extern`、类内非 inline 静态数据成员、`struct S;`、opaque enum、类型别名、各种 using、`static_assert`、没有定义体的模板声明、`extern template`、没有定义体的显式特化。
- 名字容易误导的两个：*namespace-alias-definition* 不是定义，概念定义是定义。
- `extern "C" { int v; }` 是定义，`extern "C" int v;` 不是。
- 特殊成员函数在被用到时才被隐式定义，并受 ODR 约束。
- 对象的定义不能是不完整类型或抽象类，声明可以。
