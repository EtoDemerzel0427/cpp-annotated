---
title: 说明符
summary: 声明开头的说明符有哪几种、哪些不能重复；说明符序列末尾的属性属于类型；说明符序列里遇到类型名时，它是类型还是被声明的名字。
status: done
covers: dcl.spec.general
related: dcl.pre, dcl.type, dcl.type.simple, dcl.stc, dcl.meaning, dcl.ambig.res
tags: 声明, 说明符, 语法
updated: 2026-10-19
---

!!! tldr
    - 声明开头的 `static constexpr unsigned long`、`inline virtual` 这类关键字和类型名叫说明符序列，作用于整条声明；说明符之间的顺序是自由的。
    - `friend`、`typedef`、`inline` 各至多出现一次；`constexpr`、`consteval`、`constinit` 三者至多出现一个。
    - 说明符序列末尾的属性属于类型，不属于被声明的实体；标准属性都不能用在这个位置。
    - 说明符序列里遇到一个类型名时，只有前面还没有（cv 限定符以外的）类型说明符，它才算类型；否则它是被声明的名字。所以 `void h(unsigned Pc);` 中的 `Pc` 是参数名。
    - typedef 不是宏替换：`typedef char* Pc;` 之后，`const Pc` 是 `char* const`，不是 `const char*`。

## typedef 名什么时候是类型

```cpp run ok
#include <type_traits>
typedef char* Pc;
void f(const Pc);          // Pc 是类型 → void f(char* const)
void g(const int Pc);      // Pc 是参数名 → void g(const int)
void h(unsigned Pc);       // Pc 是参数名 → void h(unsigned int)

static_assert(std::is_same_v<decltype(f), void(char*)>);   // 参数的顶层 const 不进函数类型
static_assert(std::is_same_v<decltype(h), void(unsigned)>);
int main() { }
```

同一个名字 `Pc`，在 `f` 里是类型，在 `g`、`h` 里却是参数名。这由 [dcl.spec.general] 的第 3 段决定，下面先介绍说明符的种类，再回到这条规则。

## 说明符的种类（¶1）

¶1 声明开头的 **decl-specifier**（说明符）共有九种，组成的序列叫 *decl-specifier-seq*（说明符序列）：

| 说明符 | 作用 | 详见 |
|---|---|---|
| *storage-class-specifier*：`static` `thread_local` `extern` `mutable` | 存储期、链接、可变成员 | [[dcl.stc]] |
| *defining-type-specifier*：类型说明符、类定义、枚举定义 | 给出基础类型 | [[dcl.type]] |
| *function-specifier*：`virtual`、`explicit`、`explicit(bool)` | 只用于函数 | [[dcl.fct.spec]] |
| `friend` | 友元声明 | [[dcl.friend]] |
| `typedef` | 类型别名 | [[dcl.typedef]] |
| `constexpr` | 可以在常量求值中使用 | [[dcl.constexpr]] |
| `consteval` | 立即函数，只能在常量求值中调用 | [[dcl.constexpr]] |
| `constinit` | 要求静态初始化 | [[dcl.constinit]] |
| `inline` | 允许每个翻译单元各有一个定义 | [[dcl.inline]] |

有几样东西不是说明符：

- `auto` 从 C++11 起不再是存储类说明符，而是占位类型说明符，属于类型说明符（[[dcl.spec.auto]]）；`register` 在 C++17 被移除（[[dcl.stc]]）。
- `override`、`final` 写在声明符之后（[[class.mem]]）。
- `noexcept` 是函数类型的一部分，写在声明符里（[[except.spec]]）。
- `extern "C"` 是链接规格，不是存储类说明符（[[dcl.link]]）。

说明符的顺序是自由的。`int static const x = 0;`、`const static int y = 0;`、`static int const z = 0;` 完全等价，`unsigned long` 这样的多词类型也可以和其他说明符穿插（[[dcl.type.simple#4]]）：

```cpp run ok
int static const x = 0;
long unsigned long const static y = 0;   // static const unsigned long long
inline static int z = 0;                  // 与 static inline 相同
int main() { return x + int(y) + z; }
```

C 标准把不在开头的存储类说明符列为过时特性，C++ 标准没有这种规定。不过为了可读性和与 C 共用头文件，惯例仍然把 `static`、`extern` 写在最前面。

### 说明符序列末尾的属性

¶1 的语法还允许在说明符序列末尾写属性。这里的属性**属于前面的说明符确定的类型**，并且只在本声明中影响这个类型。声明开头的属性和名字后面的属性则属于被声明的实体（[[dcl.pre#4]]）。

```cpp error
int [[deprecated]] x;      // error: deprecated 不能用于类型，而这里它属于 int
[[deprecated]] int y;      // OK: 开头的属性属于 y
```

标准属性没有一个能用于类型，所以把标准属性写在这个位置都是错误的。这个位置是给实现特有的类型属性准备的。

## 不能重复的说明符（¶2）

¶2 `friend`、`typedef`、`inline` 在一个说明符序列中各至多出现一次；`constexpr`、`consteval`、`constinit` 三者合计至多出现一个。

```cpp error
inline inline void f();          // error: inline 重复
constexpr constinit int x = 1;   // error: constexpr 与 constinit 不能并存
consteval constexpr int g();     // error: 同上
```

本机 Clang 23 对 `inline inline` 和 `const const int` 只给出 `-Wduplicate-decl-specifier` 警告，这是沿用 C 的行为，C 允许重复的限定符和 `inline`。在 C++ 中它们都非良构，警告已经满足了诊断要求。`constexpr constinit` 则是错误。

`constexpr` 变量本来就要求常量初始化（[[dcl.constexpr#6]]），`constinit` 只表达其中的一半，两个一起写没有意义。对函数来说，`constexpr` 和 `consteval` 是互斥的两种性质：可以在常量求值中调用，与只能在常量求值中调用。

其他说明符的重复规则在各自的条款里：存储类说明符至多一个，只有 `thread_local` 可以和 `static` 或 `extern` 搭配（[[dcl.stc#1]]）；类型说明符的组合见 [[dcl.type.general#2]]，`long long` 合法，`const const` 不合法。

## 类型名属于说明符还是声明符（¶3–4）

回到开头的问题。`void h(unsigned Pc);` 中的 `unsigned Pc` 有两种读法：`unsigned` 加类型名 `Pc` 组成说明符序列，参数无名；或者 `unsigned` 是说明符序列，`Pc` 是参数名。`unsigned` 加一个 typedef 名本来就不是合法的类型，我们希望得到后一种。可是 `const Pc` 也有同样的两种读法，而 `const` 加 `Pc` 是合法的组合。

¶3 给出了确定的规则：

!!! std
    If a *type-name* is encountered while parsing a *decl-specifier-seq*, it is interpreted as part of the *decl-specifier-seq* if and only if there is no previous *defining-type-specifier* other than a *cv-qualifier* in the *decl-specifier-seq*.

    解析说明符序列时遇到类型名，当且仅当前面还没有 cv 限定符以外的类型说明符，它才属于说明符序列。

换句话说，说明符序列只吞下第一个类型。前面一旦已经有一个真正给出类型的说明符（`int`、`unsigned`、`long`、另一个类型名、`class X {…}` 等），后面再出现的类型名就不再属于说明符序列，而是声明符的开始，也就是被声明的名字。`const` 不算，因为它不能单独构成类型。

¶4（注）`signed`、`unsigned`、`long`、`short` 单独使用时隐含 `int`，所以它们之后的类型名是被声明的名字，`void h(unsigned Pc)` 就是这种情况。这只是 ¶3 的推论。

```cpp error
typedef char* Pc;
static Pc;                 // error: Pc 进了说明符序列，没有剩下声明符
```

这是标准例 1。要声明一个名为 `Pc` 的 static 变量，必须先写一个 cv 以外的类型说明符，让 `Pc` 落到声明符的位置：`static char* Pc;`。本机 Clang 23 对 `static Pc;` 只给出 declaration does not declare anything 的警告。

### 更多边界情况

```cpp run ok
typedef int T;
void a(T const T);         // 第一个 T 是类型，第二个 T 是参数名
void b() {
    T T = 1;               // 声明一个名为 T 的 int 局部变量
    (void)T;               // 此后在这个块里 T 指这个变量
}
int main() { }
```

<div class="compare" markdown="1">

```cpp error
typedef long L;
void c(L long);
// error: L 已是类型，
// long 不能再与它组合
```

```cpp error
typedef int T;
unsigned T u;
// error: T 成了变量名，
// 后面的 u 无法解析
```

</div>

`void c(L long)` 说明这条规则不会回头。`L` 被吞进说明符序列后，`long` 也是类型说明符，但它不是类型名，¶3 管不到它，于是 `L long` 违反了 [[dcl.type.general#2]] 的组合规则。编译器不会因为组合失败而把 `L` 改当参数名。

¶3 只对类型名（类名、枚举名、typedef 名，[[dcl.type.simple]]）起作用，普通变量名本来就不会出现在说明符序列里。判断一个标识符是不是类型名需要名字查找，这是 C++ 的语法分析离不开语义信息的原因之一。

!!! note "构造函数声明"
    类里的 `S();` 中，`S` 查到的是注入类名，按 ¶3 机械处理会被吞进说明符序列，剩下的 `()` 成了无名的函数声明符。构造函数的识别由 [[class.ctor.general]] 的专门规则处理：注入类名后面直接跟参数列表、且没有其他类型说明符的函数声明符，声明的是构造函数。

¶3 最后一句要求说明符序列自洽，具体约束分布在 9.2 后续各节：[[dcl.stc]]、[[dcl.fct.spec]]、[[dcl.typedef]]、[[dcl.type.general]] 等。

## 常见误解

!!! pitfall "`const Pc` 等于 `const char*`"
    typedef 不是文本替换。`Pc` 代表整个指针类型 `char*`，`const` 加在这个指针类型上，得到 `char* const`（[[dcl.type.cv]]、[[dcl.typedef]]）。

!!! pitfall "说明符的顺序有含义"
    `int const static` 和 `static const int` 完全相同。唯一与位置有关的是 ¶3：类型名出现在另一个类型说明符之后，就成了被声明的名字。

## 思考题

!!! question "思考题 1"
    以下每个函数的类型是什么？参数各叫什么？
    ```cpp
    typedef int A;
    typedef int B;
    void f(A B);
    void g(const A, B);
    void h(A const B);
    ```

<details markdown="1">
<summary>答案</summary>

- `f(A B)`：`A` 是类型；`B` 前面已有类型说明符 `A`，所以是参数名。类型是 `void(int)`。
- `g(const A, B)`：两个参数各有自己的说明符序列。第一个参数中 `const` 不算，`A` 是类型；第二个参数中 `B` 是类型。两个参数都无名，类型是 `void(int, int)`。
- `h(A const B)`：`A` 是类型，`const` 是 cv 限定符，`B` 前面已有 `A`，所以是参数名。类型是 `void(int)`。

本机 Clang 23 用 `__is_same` 验证了这三个类型。
</details>

!!! question "思考题 2"
    `struct S { }; S S; S s2;` 为什么最后一个声明出错？怎样改？

<details markdown="1">
<summary>答案</summary>

`S S;` 中第一个 `S` 是类名，第二个 `S` 是变量名，于是声明了一个名为 `S` 的变量。查找同时找到类和变量时，类的声明被隐藏（[[basic.lookup.general#4]]），所以 `S s2;` 里的 `S` 找到的是变量，不是类型名，产生语法错误。改成 `struct S s2;` 即可：详述类型说明符的查找会忽略非类型的名字（[[basic.lookup.elab]]）。
</details>
