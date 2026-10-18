---
title: 说明符
summary: decl-specifier 的种类与组合限制；说明符序列中的属性属于类型；"遇到类型名时它算不算说明符"的最长匹配规则，以及由此产生的 typedef 名谜题
status: done
covers: dcl.spec.general
related: dcl.pre, dcl.type, dcl.type.simple, dcl.stc, dcl.meaning, dcl.ambig.res
tags: 声明, 说明符, 语法
updated: 2026-10-17
---

一条声明的开头那串关键字和类型名——`static constexpr unsigned long`、`inline virtual`、`typedef const char*`——在标准中叫 ***decl-specifier-seq***（说明符序列）。9.2 整节都在讲它们。本页对应 9.2.1 [dcl.spec.general]：列出说明符的种类，规定哪些不能重复，以及一条非常"语法律师"的规则——在说明符序列中遇到一个**类型名**时，它到底是类型说明符，还是将被声明的名字？

背景知识：声明的三段式结构见 [[dcl.pre#4]]；类型说明符的组合规则见 [[dcl.type.general]]。

## 说明符的种类（¶1）

¶1 *decl-specifier* 一共九类：

| 说明符 | 作用 | 详见 |
|---|---|---|
| *storage-class-specifier*：`static` `thread_local` `extern` `mutable` | 存储期、链接、可变成员 | [[dcl.stc]] |
| *defining-type-specifier*：类型说明符、类定义、枚举定义 | 给出基础类型 | [[dcl.type]] |
| *function-specifier*：`virtual` `explicit` `explicit(bool)` | 仅用于函数 | [[dcl.fct.spec]] |
| `friend` | 友元声明 | [[dcl.friend]]、[[class.friend]] |
| `typedef` | 类型别名 | [[dcl.typedef]] |
| `constexpr` `consteval` | 常量求值资格 | [[dcl.constexpr]] |
| `constinit` | 要求静态初始化 | [[dcl.constinit]] |
| `inline` | ODR 豁免 | [[dcl.inline]] |

几个**不是** *decl-specifier* 的东西也值得记住：

- `auto` 早已不是存储类说明符（C++11 起），而是占位**类型**说明符（[[dcl.spec.auto]]）；`register` 在 C++17 被移除（[[dcl.stc]]）。
- `override`、`final` 是 *virt-specifier*，写在声明符之后，不在说明符序列里（[[class.mem]]）。
- `noexcept` 是函数类型的一部分，写在声明符里（[[except.spec]]）。
- `extern "C"` 是 *linkage-specification*，不是存储类说明符（[[dcl.link]]）。

¶1 的语法还说明：*decl-specifier-seq* 末尾可以跟一个 *attribute-specifier-seq*，它**属于由前面的说明符确定的类型**，并且只影响本声明中的该类型，不影响涉及同一类型的其他声明。

!!! std
    The optional *attribute-specifier-seq* in a *decl-specifier-seq* appertains to the type determined by the preceding *decl-specifiers*.

这是 C++ 属性"位置决定归属"原则的一个实例（对比：声明开头的属性属于被声明的实体，[[dcl.pre#4]]；*declarator-id* 后的属性也属于实体）。标准属性中没有一个可以作用于类型，所以写在这个位置的标准属性都是错误：

```cpp error
int [[deprecated]] x;      // error: deprecated 不能作用于类型（它属于 int 这个类型，而不是 x）
[[deprecated]] int y;      // OK: 开头的属性属于 y
```

实现特有属性可以作用于类型（例如某些编译器的向量类型、地址空间属性），这正是该语法位置存在的理由。

## 不可重复的说明符（¶2）

¶2 `friend`、`typedef`、`inline` 在一个说明符序列中各至多出现一次；`constexpr`、`consteval`、`constinit` **三者合计**至多出现一个。

```cpp error
inline inline void f();          // error: inline 重复
constexpr constinit int x = 1;   // error: constexpr 与 constinit 不能并存
consteval constexpr int g();     // error: 同上
```

其他说明符的重复规则分散在各自的条款中：

- 存储类说明符至多一个，例外是 `thread_local` 可以与 `static` 或 `extern` 搭配（[[dcl.stc#1]]）；
- `virtual` 至多一个，*explicit-specifier* 至多一个（[[dcl.fct.spec#1]]）；
- 类型说明符的组合由 [[dcl.type.general#2]] 规定：`long long` 合法（`long` 可以和 `long` 组合），`const const` 不合法。

!!! impl "Clang 对重复只给警告"
    对 `inline inline` 和 `const const int`，Clang 给出的是 `-Wduplicate-decl-specifier` 警告（这是 C 语言的继承：C 允许重复的限定符和 `inline`）。按 C++ 标准它们都是非良构的，但警告已构成诊断。`constexpr constinit` 则是硬错误。

为什么 `constexpr` 和 `constinit` 不能并存？因为 `constexpr` 变量已经要求常量初始化（[[dcl.constexpr#6]]），`constinit` 只表达其中"必须常量初始化"这一半，同时写没有意义；而 `constexpr` 和 `consteval` 对函数是互斥的两种性质（可常量求值 vs 必须常量求值）。

## 类型名何时属于说明符序列（¶3–4）

这是本节的核心。看这个声明：

```cpp
typedef int I;
void f(unsigned I);
```

`unsigned I` 有两种读法：(a) `unsigned` + 类型名 `I` 组成说明符序列，参数无名；(b) `unsigned` 是说明符序列，`I` 是参数名（重新声明了名字 `I`）。由于 `unsigned I`（`unsigned` + typedef 名）本来就不是合法的类型组合，人们希望得到 (b)。但对 `const I` 呢？`const` + `I` 是合法组合。

¶3 给出了确定的规则：

!!! std
    If a *type-name* is encountered while parsing a *decl-specifier-seq*, it is interpreted as part of the *decl-specifier-seq* if and only if there is no previous *defining-type-specifier* other than a *cv-qualifier* in the *decl-specifier-seq*.

    解析说明符序列时遇到类型名：当且仅当前面**还没有**（除 cv 限定符外的）定义类型说明符时，它才是说明符序列的一部分。

换句话说，说明符序列**贪婪地吞下第一个类型名**，但一旦已经有了一个"真正的"类型说明符（`int`、`unsigned`、`long`、另一个类型名、`class X {…}`……），后面再出现的类型名就不再被吞下，而是作为声明符的开始——即被声明的名字。cv 限定符不算，因为 `const` 本身不能单独构成类型。

### 标准的例子逐一拆解

```cpp run ok
#include <type_traits>
typedef char* Pc;
void f(const Pc);          // Pc 是类型：const 之前没有类型说明符 → void f(char* const)
void g(const int Pc);      // int 之后的 Pc 是参数名 → void g(const int)
void h(unsigned Pc);       // unsigned 是类型说明符，Pc 是参数名 → void h(unsigned int)
void k(unsigned int Pc);   // 同上 → void k(unsigned int)

static_assert(std::is_same_v<decltype(f), void(char*)>);   // 顶层 const 从函数类型中去掉
static_assert(std::is_same_v<decltype(h), void(unsigned)>);
int main() { }
```

注意 `f(const Pc)` 的类型是 `char* const`，而**不是** `const char*`：typedef 不是宏替换，`const` 作用于 `Pc` 所代表的整个指针类型（[[dcl.type.cv]]、[[dcl.typedef]]）。这是 typedef 最常见的误解之一。

```cpp error
typedef char* Pc;
static Pc;                 // error: Pc 被吞进说明符序列，没有剩下声明符 —— 名字缺失
```

（Clang 对此只给出"declaration does not declare anything"警告，参见 [[dcl.pre#6]] 的实现说明。）想要声明一个名为 `Pc` 的 static 变量，必须先写一个非 cv 的类型说明符，让 `Pc` 落到声明符位置：`static char* Pc;`。

¶4（注）：`signed`、`unsigned`、`long`、`short` 默认隐含 `int`，所以它们之后的类型名被当作被声明的名字——`void h(unsigned Pc)` 就是这样。这条注释只是 ¶3 的推论，不是新规则。

### 更多边界情况

```cpp run ok
typedef int T;
void a(T const T);         // 第一个 T 是类型（之前无类型说明符），第二个 T 是参数名
void b() {
    T T = 1;               // 同理：声明一个名为 T 的 int 局部变量，隐藏了 typedef
    (void)T;               // 此后 T 指代变量
}
int main() { }
```

```cpp error
typedef long L;
void c(L long);            // error: L 被吞进说明符序列；然后 long 与 typedef 名组合 —— 非法
typedef int T;
unsigned T u;              // error: T 是变量名（unsigned 之后），后面多出来的 u 无法解析
```

`void c(L long)` 一例说明规则是**单向的**：它只决定"类型名是否被吞下"，不会因为后面组合失败而回头重新解析。`L` 被吞下后，`long` 也是一个类型说明符（不是类型名，所以 ¶3 不管它），于是 `L long` 违反了 [[dcl.type.general#2]] 的组合规则。

!!! lawyer "为什么是"类型名"而不是"标识符""
    ¶3 只在遇到 *type-name*（类名、枚举名、typedef 名，[[dcl.type.simple]]）时生效。普通变量名本来就不能出现在说明符序列中，不存在歧义。判断一个标识符是不是类型名需要**名字查找**——这就是 C++ 不能脱离语义做语法分析的原因之一（"lexer hack"的 C++ 版本）。

!!! note "与构造函数声明的关系"
    类内的 `S();` 中，`S` 查找到的是注入类名（一个类名）。如果按 ¶3 机械处理，`S` 会被吞进说明符序列，剩下 `()` 是一个抽象声明符——那就成了一个无名的函数声明。构造函数的识别由 [[class.ctor.general]] 的专门规则处理：形如"注入类名 `(` 参数列表 `)`"、且没有其他类型说明符的函数声明符声明的是构造函数。

### "自洽"要求

¶3 最后一句："序列必须是自洽的，如下所述"——指的是 9.2 后续各节对说明符组合的约束：[[dcl.stc]]（存储类说明符的组合与适用对象）、[[dcl.fct.spec]]（函数说明符只用于函数）、[[dcl.typedef]]（`typedef` 只能和类型说明符组合）、[[dcl.type.general]]（类型说明符的组合表）……这些规则加在一起，才确定了一个说明符序列是否合法。

## 说明符的顺序

标准不规定说明符的顺序：`int static const x = 0;`、`const static int y = 0;`、`static int const z = 0;` 完全等价（[[dcl.type.simple#4]] 明确说可以自由混排）。唯一的顺序敏感性就是 ¶3 的类型名规则。

```cpp run ok
int static const x = 0;
long unsigned long const static y = 0;   // unsigned long long，const，static
inline static int z = 0;                  // static inline 与 inline static 相同
int main() { return x + int(y) + z; }
```

!!! pitfall "风格 ≠ 规则"
    "`static` 应写在最前面"是 C 标准的一条**过时特性**说明（C 标准把不在开头的存储类说明符列为 obsolescent），C++ 标准没有这种说法。但为了可读性和与 C 共享头文件，惯例仍是把存储类说明符写在前面。

!!! summary "小结"
    - 说明符共九类，作用于整条声明；声明符只作用于单个名字。
    - `friend`/`typedef`/`inline` 各至多一次；`constexpr`/`consteval`/`constinit` 三选一。
    - 说明符序列末尾的属性属于**类型**，不属于实体。
    - 类型名规则：**前面没有非 cv 类型说明符**时，类型名才被当作说明符；否则它是被声明的名字。
    - typedef 不是宏：`const Pc` 是 `char* const`。

!!! question "思考题 1"
    以下每个声明中，被声明的名字是什么、类型是什么？

    ```cpp
    typedef int A;
    typedef int B;
    void f(A B);
    void g(const A, B);
    void h(A const B);
    ```

<details markdown="1">
<summary>答案</summary>

- `f(A B)`：`A` 被吞下（之前无类型说明符），`B` 位于已有类型说明符之后，是**参数名**。`f` 的类型是 `void(int)`。
- `g(const A, B)`：两个参数各有自己的 *decl-specifier-seq*。第一个：`const` 不算，`A` 被吞下 → 无名 `const int`；第二个：`B` 被吞下 → 无名 `int`。类型是 `void(int, int)`。
- `h(A const B)`：`A` 被吞下，`const` 是 cv，`B` 之前已有非 cv 类型说明符 `A`，所以 `B` 是参数名。类型 `void(int)`。
</details>

!!! question "思考题 2"
    `struct S { }; S S; S s2;` 为什么最后一个声明出错？怎样改？

<details markdown="1">
<summary>答案</summary>

`S S;` 中第一个 `S` 是类名（被吞进说明符序列），第二个 `S` 是变量名，于是声明了一个名为 `S` 的变量，它在后续查找中**隐藏**了类名 `S`（查找同时找到类和其他实体时丢弃类的声明，[[basic.lookup.general#4]]）。`S s2;` 里的 `S` 查找到的是变量，不是类型名，于是语法错误。改法是使用详述类型说明符 `struct S s2;`——它的查找忽略非类型名字（[[basic.lookup.elab]]）。
</details>
