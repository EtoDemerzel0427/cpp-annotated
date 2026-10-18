---
title: 声明符
summary: 声明 = 说明符序列 + 若干声明符：声明符文法、"声明模仿使用"原则、按文法递归读懂任意复杂声明符、type-id 与 nofun-type-id、尾置返回类型、尾置 requires 子句、限定声明符与友元声明的目标作用域
status: draft
covers: dcl.decl.general, dcl.name, dcl.meaning, dcl.meaning.general
related: dcl.pre, dcl.spec, dcl.ambig.res, dcl.ptr, dcl.ref, dcl.array, dcl.fct, dcl.init, basic.scope.scope, temp.pre
tags: 声明符, 文法, type-id, 尾置返回类型
updated: 2026-10-17
---

一个简单声明 `const int *p, a[3], f(int);` 由两部分组成：前面的**声明说明符序列**（*decl-specifier-seq*，这里是 `const int`，见 [[dcl.spec]]）和后面逗号分隔的若干**声明符**（*declarator*，这里是 `*p`、`a[3]`、`f(int)`）。说明符给出一个"基础类型"以及存储期、链接等属性；每个声明符给出**一个**被声明的名字，并用 `*`、`&`、`[]`、`()` 等运算符把基础类型"加工"成最终类型。

本节（[dcl.decl]）规定声明符的文法和含义。它是整个声明体系的骨架：[[dcl.ptr]]、[[dcl.ref]]、[[dcl.mptr]]、[[dcl.array]]、[[dcl.fct]] 各自规定一种声明符运算符的含义，本页讲把它们组合起来的通用机制：

- [dcl.decl.general]：*init-declarator* 的文法、何时允许初始化器 / 尾置 requires 子句 / 契约说明符；
- [dcl.name]：没有名字的声明符——*type-id*，以及 C++26 之后新引入的 *nofun-type-id*；
- [dcl.meaning.general]：*declarator-id* 的约束、限定名声明符与友元声明的目标作用域，以及"从 `T D` 递归求类型"的总算法。

C 的设计者把这套语法称为"**声明模仿使用**"（declaration mirrors use）：`int *p` 的意思是"`*p` 是 `int`"，`int f(int)` 的意思是"`f(某个 int)` 是 `int`"，`int a[3]` 的意思是"`a[i]` 是 `int`"。声明符里的运算符与表达式里同名运算符的**优先级相同**——后缀的 `()`、`[]` 比前缀的 `*` 结合得紧——这就是 `int *f()` 与 `int (*f)()` 不同的原因。理解了这一点，再复杂的声明符也能机械地读出来。

## 一个声明符声明一个实体（¶1–2）

¶1 声明符在一个声明中声明**单个**变量、函数或类型。*simple-declaration* 中的 *init-declarator-list* 是逗号分隔的声明符序列，每个都可以带初始化器：

```
init-declarator:
    declarator initializer
    declarator requires-clause(opt) function-contract-specifier-seq(opt)
```

注意第二种形式：没有初始化器时，声明符后面可以跟**尾置 requires 子句**（¶5）和 C++26 的**函数契约说明符**（¶6，[[dcl.contract]]）。两者只对函数有意义，所以与初始化器互斥。

¶2 无论出现在哪里，声明符都按本节解释。在允许使用**抽象声明符**（*abstract-declarator*，即省略了名字的声明符，出现在形参声明、*type-id*、异常声明中）的地方，就当作在"合适的位置"有一个独一无二的标识符（见下文 [dcl.name]）。说明符决定类型、存储期、链接等属性；声明符指定一个实体，可选地给它命名，并用 `*`（指向）、`()`（返回……的函数）等运算符修饰说明符给出的类型。

## 多个声明符：逐个独立分析（¶3）

¶3 一个 *simple-declaration* 中的每个 *init-declarator*（以及 *member-declaration* 中的每个 *member-declarator*）都**单独分析**，如同它独自构成一个声明。所以 `T D1, D2;` 通常等价于 `T D1; T D2;`。

"通常"有两个例外（标准的注 2）：

```cpp title="decl-split.cpp" ok
struct S { };

void f() {
    S S, T;    // OK：两个 S 类型的对象，名字分别为 S 和 T
    (void)T;
}
// 如果拆成 S S; S T; ——第二句中的 S 已被变量 S 隐藏，不再是类型名，非良构
```

第一个例外的原因是：说明符 `S` 在整个声明开始时只查找了一次，此时 `S` 还是类名；拆开后，第二个声明重新查找 `S`，找到的是刚声明的变量。

第二个例外是 `auto`：同一声明中的所有声明符必须推导出同一个类型（[[dcl.spec.auto]]）。

```cpp title="auto-multi.cpp" error
auto i = 1, j = 2.0;    // error: i 推导为 int，j 推导为 double，不一致
```

!!! pitfall "`int* a, b;` 中 b 不是指针"
    `*` 属于声明符，不属于说明符。`int* a, b;` 的说明符是 `int`，两个声明符是 `*a` 和 `b`——`b` 是 `int`。把 `*` 贴在类型旁边的写法掩盖了这一事实；需要多个指针时要么每个声明符都写 `*`，要么用别名 `using IP = int*; IP a, b;`（此时两者都是指针，因为 `IP` 是说明符）。

## 何时允许初始化器（¶4）

¶4 *init-declarator* 的初始化器只能在**声明符声明的是变量**、**并且**该声明的**宿主作用域**（host scope，[[basic.scope.scope]]）与其**目标作用域**相同时出现。宿主作用域：若声明所居（inhabit）的是块作用域，则为该块作用域；否则为目标作用域。

这一条排除了两类情形：

- 声明的不是变量：函数（`int f() = 0;` 不是纯虚声明——那是 *pure-specifier*，只出现在 *member-declarator* 中）、类型别名等；
- 块作用域的 `extern` 声明：它居于块作用域，但目标作用域是外围命名空间（[[dcl.meaning.general]] ¶3.5），二者不同。

```cpp title="extern-init.cpp" error
int x;
void f() {
    extern int x = 1;   // error: 宿主作用域是块，目标作用域是全局命名空间
}
```

为什么？块作用域 `extern` 声明的意思是"这里引用一个在别处定义的变量"，在块内给它初始化器等于在函数里定义一个命名空间作用域的变量，这与"块内声明"的直觉和存储期都矛盾。相比之下，`int A::s = 2;`（类外定义静态数据成员）居于命名空间作用域而不是块作用域，按定义其宿主作用域就是目标作用域（类 `A` 的作用域），所以初始化器合法。

## 尾置 requires 子句（¶5）

¶5 *init-declarator* 或 *member-declarator* 上的 *requires-clause* 只能出现在声明**模板化函数**（templated function，[[temp.pre]]）的声明符上。出现在声明符之后的 requires 子句称为**尾置 requires 子句**（trailing *requires-clause*）；它把其中的 *constraint-logical-or-expression* 解释为约束表达式引入。

"模板化函数"不只是函数模板，还包括类模板的成员函数、泛型 lambda 的调用运算符等——任何处于模板化实体内的函数。这正是尾置 requires 子句最常见的用途：按类模板实参有条件地启用非模板成员函数。

```cpp title="trailing-requires.cpp" ok
#include <type_traits>

template<class T>
struct Box {
    T value;
    // 非模板成员函数，但它是"模板化函数"，可以有尾置 requires 子句
    void increment() requires std::is_arithmetic_v<T> { ++value; }
};

int main() {
    Box<int> b{1};
    b.increment();          // OK
    Box<void*> p{nullptr};  // OK：只要不调用 increment
    (void)p;
}
```

位置与对象的限制（标准例 1 改编）：

```cpp title="trailing-requires-bad.cpp" error
void f1(int a) requires true;                       // error: 非模板化函数
template<typename T>
  auto f2(T a) -> bool requires true;               // OK
template<typename T>
  auto f3(T a) requires true -> bool;               // error: requires 子句必须在尾置返回类型之后
void (*pf)() requires true;                         // error: 约束变量
void g(int (*)() requires true);                    // error: 约束形参
```

尾置 requires 子句**不是函数类型的一部分**（[[dcl.fct#13]]），但它参与声明的**对应**（correspond，[[basic.scope.scope]]）判定：两个仅尾置 requires 子句不同的成员函数声明是不同的函数（重载），最终由约束的偏序（[[temp.constr.order]]）在重载决议中选择。

!!! note "为什么尾置 requires 必须在尾置返回类型之后"
    文法上，`requires` 后面是一个 *constraint-logical-or-expression*，可以吞下很多记号；若允许它出现在 `->` 之前，`requires A -> B` 的边界会变得模糊。规定 *trailing-return-type* 必须紧贴在 *parameters-and-qualifiers* 之后，也保证了"返回类型"在语法上属于声明符本身。

## 契约说明符（¶6）

¶6 *init-declarator* 上的 *function-contract-specifier-seq*（`pre(...)` / `post(...)`，{{c++26}}）只能出现在声明函数的声明符上。详见 [[dcl.contract]]。

## 声明符文法（¶7）

¶7 声明符的核心文法（略去属性）：

```
declarator:
    ptr-declarator
    noptr-declarator parameters-and-qualifiers trailing-return-type
ptr-declarator:
    noptr-declarator
    ptr-operator ptr-declarator           // 前缀：*  &  &&  C::*
noptr-declarator:
    declarator-id
    noptr-declarator parameters-and-qualifiers        // 后缀：( 形参 ) cv ref noexcept
    noptr-declarator [ constant-expression(opt) ]     // 后缀：[ N ]
    ( ptr-declarator )                                // 括号
```

这个文法本身就编码了**优先级**：

1. 后缀运算符 `()`、`[]` 只能接在 *noptr-declarator* 上；前缀运算符 `*`、`&`、`&&`、`C::*` 只能接在 *ptr-declarator* 上。所以 `*a[3]` 只能解析为 `*(a[3])`：后缀先结合。
2. 想让前缀先结合，必须用括号把 *ptr-declarator* 包成 *noptr-declarator*：`(*a)[3]`。
3. *trailing-return-type* 只出现在顶层 *declarator* 的产生式中，而 `( ptr-declarator )` 里只能放 *ptr-declarator*——因此尾置返回类型只能写在**最外层**的函数声明符上。

其余部件：

- *parameters-and-qualifiers*：`( 形参子句 ) cv限定 引用限定 noexcept 属性`，是函数声明符的后缀，见 [[dcl.fct]]；
- *ptr-operator*：`*` 后可跟 cv 限定（修饰指针本身）；`&` / `&&` 后不能跟 cv（引用没有 cv，见 [[dcl.ref]]）；`C::*` 是成员指针（[[dcl.mptr]]）；
- *declarator-id*：`...`(可选) *id-expression*。`...` 用于声明函数形参包（[[dcl.fct#26]]）；*id-expression* 可以是限定名（`N::f`、`C::C`）、运算符函数名、转换函数名、析构函数名、*template-id* 等。

## 类型名：type-id 与 nofun-type-id（[dcl.name]）

### type-id 是"省略了名字的声明"

¶1 需要单独写一个类型（`sizeof`、`alignof`、`new`、类型转换、模板实参、`using` 别名……）时，用 *type-id*、*nofun-type-id* 或 *new-type-id*（[[expr.new]]）。它们在语法上都是"省略了实体名字的变量（*type-id* 还可以是函数）声明"：

```
type-id:          type-specifier-seq abstract-declarator(opt)
abstract-declarator:
    ptr-abstract-declarator
    noptr-abstract-declarator(opt) parameters-and-qualifiers trailing-return-type
    abstract-pack-declarator
```

关键事实：在抽象声明符里，**名字本应出现的位置是唯一确定的**。把名字放回去，就得到一个普通声明，其中名字的类型就是这个 *type-id* 命名的类型。

| type-id | 放回名字 | 类型 |
|---|---|---|
| `int` | `int i` | `int` |
| `int *` | `int *pi` | 指向 `int` 的指针 |
| `int *[3]` | `int *p[3]` | 3 个指向 `int` 的指针组成的数组 |
| `int (*)[3]` | `int (*p3i)[3]` | 指向"3 个 `int` 的数组"的指针 |
| `int *()` | `int *f()` | 无形参、返回 `int*` 的函数 |
| `int (*)(double)` | `int (*pf)(double)` | 指向"形参 `(double)`、返回 `int` 的函数"的指针 |

怎样找到名字的位置？名字总是在：所有前缀运算符（`*`、`&`、`C::*`）**之后**、所有后缀运算符（`()`、`[]`）**之前**，并且在最内层的那对"不是函数形参列表"的括号里。例如 `int (*(*)(int))[3]`：最内层括号是 `(*)`，名字在 `*` 后面：`int (*(*f)(int))[3]`。

### nofun-type-id {{c++26}}

当前草案新增了 *nofun-type-id*，它与 *type-id* 的区别是：**最外层不能是函数声明符**（`noptr-nofun-declarator parameters-and-qualifiers` 要求左边非空）。所以 `int()`、`auto() -> int` 不是 *nofun-type-id*，但 `int(*)()`、`int(&)()` 是。

!!! note "这是 C++26 之后才出现的措辞"
    C++23/C++26 标准中只有 *type-id*。当前工作草案把 `sizeof(…)`、`alignof(…)`、C 风格转换 `(T)e`、`new (T)`、*trailing-return-type* 的语法都改成了 *nofun-type-id*。这些地方本来就不能是函数类型（`sizeof` 函数类型非良构、不能转换为函数类型、函数不能返回函数），改用 *nofun-type-id* 后，像 `sizeof(int())` 这样原本被当成 type-id（然后报错）的写法，现在只能解析为**表达式**（值初始化的 `int` 临时量），从而变得良构。详见 [[dcl.ambig.res#2]]。截至写作时 Clang 仍按旧规则处理。

`typeid(…)` 和模板实参仍使用 *type-id*，因为函数类型在那里是有意义的（`typeid(int())`、`std::function<int()>`）。

¶2（注）类型也可以通过 *typedef-name*（[[dcl.typedef]]）命名。

## declarator-id 的约束（[dcl.meaning.general] ¶1）

¶1 一个声明符**恰好包含一个** *declarator-id*，它命名被声明的实体。如果 *declarator-id* 中的 *unqualified-id* 是一个 *template-id*（如 `f<int>`），该声明符必须出现在模板声明、显式特化或显式实例化中：

```cpp title="template-id-declarator.cpp" error
template<class T> void tf(T);
void tf<int>(int);              // error: 需要 template<>（显式特化）
template<> void tf<int>(int);   // OK
```

*unqualified-id* 不是标识符时（`operator+`、`operator int`、`~C`、`operator""_x`），用来声明特殊的函数（[[class.conv.fct]]、[[class.dtor]]、[[over.oper]]、[[over.literal]]）。紧跟 *declarator-id* 的属性说明符序列属于**被声明的实体**（对比：跟在 `*` 后的属性属于指针类型，跟在 `[]` 后的属于数组类型）。

## 友元声明的目标作用域（¶2）

¶2 友元声明的声明符**不绑定名字**（¶2.1）——这就是"隐藏友元"（hidden friend）只能被 ADL 找到的根源。其余规则按 *declarator-id* 的形式区分：

- ¶2.2 名字是**限定名**或 *template-id*（`friend void N::f(int);`、`friend void g<>(int);`）：查找终端名字。若友元声明不是模板声明，查找结果按以下方式过滤：
    - ¶2.2.1.1 名字是 *template-id* ⇒ 丢弃所有非模板函数；
    - ¶2.2.1.2 否则，若声明符对应某个找到的非模板函数 ⇒ 丢弃所有函数模板（非模板优先）；
    - ¶2.2.1.3 剩下的函数模板通过推导（[[temp.deduct.decl]]）替换为特化，推导失败则丢弃。

    ¶2.2.2 声明符必须**对应**至少一个找到的声明，且它们的目标作用域相同，该作用域即友元声明的目标作用域。换句话说：限定的友元声明不能"顺便"声明新函数。
- ¶2.3 否则（非限定名）：**不查找**终端名字。目标作用域是最内层外围**命名空间**作用域；若友元声明位于块作用域中（局部类），则它必须对应最内层块作用域中一个可达的声明。

```cpp title="hidden-friend.cpp" error
struct N {
    friend void hf(N) { }   // 目标作用域是全局命名空间，但不绑定名字
};
void use()  { hf(N{}); }    // OK：ADL 在关联类 N 中找到友元
void use2() { auto p = &hf; }   // error: 普通查找找不到 hf
```

## 非友元声明的目标作用域（¶3）

¶3 对非友元声明：

- ¶3.1 *declarator-id* 是限定名 `Q` 时，令 *S* 为它的查找语境（[[basic.lookup.qual]]）；该声明必须**居于命名空间作用域**（不能在块作用域或类作用域里写 `void N::f() {}`）。
- ¶3.2 否则 *S* 是声明符所居作用域关联的实体。
- ¶3.3 显式实例化、偏特化或显式特化不绑定名字。若声明的是类成员，不查找终端名字；否则在识别所声明的函数模板特化时，只考虑在 *S* 中**可提名**（nominable）的查找结果。标准例 1 展示了这一点：`using P::f` 引入的 `P::f` 在 `N` 中不可提名，所以 `template<> void N::f(int*)` 特化的是内联命名空间 `O` 里的 `#1`。
- ¶3.4 其他情形不查找终端名字。若是限定名，声明符必须**对应**一个或多个在 *S* 中可提名的已有声明——**限定名不能引入新成员**；目标作用域就是那些声明的目标作用域。

```cpp title="qualified-declarator.cpp" error
namespace Q {
    namespace V { void f(); }
    void V::f() { }          // OK
    void V::g() { }          // error: g 尚未成为 V 的成员
    namespace V { void g(); }
}
namespace R {
    void Q::V::g() { }       // error: R 不包围 Q
}
```

`R` 中的错误来自 [[basic.scope.scope]] 和 ¶3.4 的组合：限定声明必须在包围被声明实体所在命名空间的作用域中出现，`R` 并不包围 `Q::V`。

- ¶3.5 若声明居于块作用域 *S*，并且声明的是函数或带 `extern`，则该声明不得附属于具名模块；其**目标作用域**是最内层外围命名空间作用域，**但名字绑定在 *S* 中**。

```cpp title="block-extern.cpp" error
namespace X {
    void p() {
        q();                 // error: q 尚未声明
        extern void q();     // q 是 X 的成员，但名字只在 p 的块内可见
        extern void r();     // r 也是 X 的成员
    }
    void middle() {
        q();                 // error: 这里找不到 q
    }
    void q() { }             // X::q 的定义
}
void X::r() { }              // error: r 不能用限定名声明——¶3.4 要求对应 X 中可提名的声明，
                             // 而块作用域的 extern 声明在 X 中不可提名
```

这就是"块作用域函数声明"的语义：它声明的是命名空间成员，但只在块内可见。

## 说明符作用于每个 declarator-id（¶4）

¶4 `static`、`thread_local`、`extern`、`mutable`、`friend`、`inline`、`virtual`、`constexpr`、`consteval`、`constinit`、`typedef` 以及 *explicit-specifier* **直接作用于每一个** *declarator-id*；每个 *declarator-id* 的类型则同时取决于说明符序列和它自己的声明符。

```cpp title="spec-each.cpp" ok
static int a, *b, c[2];          // 三者都是 static
typedef int I, *IP, A3[3];       // 三个类型别名：int、int*、int[3]
constexpr int x = 1, y = 2;      // 两者都是 constexpr
static_assert(sizeof(A3) == 3 * sizeof(int));
int main() { (void)b; (void)c; return a + x + y - 3; }
```

## 求类型的递归算法（¶5–8）

¶5 对每个声明符，声明的形式是 `T D`：`T` 是（可选属性 +）说明符序列，`D` 是声明符。标准给出一个递归过程求 `D` 中 *declarator-id* 的类型。

¶6 首先，说明符序列确定一个类型 `T`。说明符的顺序无关紧要：`int unsigned i;` 中 `int unsigned` 确定 `unsigned int`（[[dcl.type.simple]]）。

¶7 如果 `D` 就是一个裸的 *declarator-id*，被声明实体的类型就是 `T`。

¶8 如果 `D` 形如 `( D1 )`，类型与 `T D1` 中的相同。**括号不改变类型，只改变复杂声明符的结合方式。** 所以 `int (x);` 就是 `int x;`——这正是 [[dcl.ambig.res]] 中各种歧义的根源。

其余形式由各子条款定义，模式都一样：若 `T D1` 中 *declarator-id* 的类型是"*derived-declarator-type-list* `T`"，那么：

| `D` 的形式 | `D` 中 *declarator-id* 的类型 | 条款 |
|---|---|---|
| `* cv D1` | "*list* cv 指向 `T` 的指针" | [[dcl.ptr]] |
| `& D1` / `&& D1` | "*list* 指向 `T` 的左值/右值引用" | [[dcl.ref]] |
| `C::* cv D1` | "*list* cv 指向 `C` 中 `T` 类型成员的指针" | [[dcl.mptr]] |
| `D1 [N]` | "*list* `N` 个 `T` 的数组" | [[dcl.array]] |
| `D1 ( 形参 ) cv ref noexcept` | "*list* 形参为……、返回 `T` 的函数" | [[dcl.fct]] |

*derived-declarator-type-list* 是"内层声明符已经积累的修饰"。剥掉 `D` 的最外层运算符，它的修饰紧贴在 `T` 前面；内层的修饰排在更前面。

### 按文法读声明符

把上面的递归展开，就得到一个可靠的手工算法：

> **从外向内剥**：确定 `D` 的最外层运算符（考虑优先级：前缀 `*`/`&` 比后缀 `()`/`[]` 更"外"；括号把内容整体变成一个单元）；它贡献的短语紧贴在当前结果之前；然后对剩下的内层声明符重复，直到只剩名字。

例子：`int (*(*f)(int))[3];`

| 步骤 | 当前 `D` | 最外层运算符 | 累积的类型短语（从左往右读） |
|---|---|---|---|
| 0 | `(*(*f)(int))[3]` | 后缀 `[3]`（括号整体是一个 *noptr-declarator*） | 3 个 `int` 的数组 |
| 1 | `(*(*f)(int))` → `*(*f)(int)` | 括号：类型不变；去掉括号后最外层是前缀 `*` | 指向〔3 个 `int` 的数组〕的指针 |
| 2 | `(*f)(int)` | 后缀 `(int)` | 形参 `(int)`、返回〔指向 3 个 `int` 数组的指针〕的函数 |
| 3 | `(*f)` → `*f` | 前缀 `*` | 指向〔形参 `(int)`、返回指向 3 个 `int` 数组的指针的函数〕的指针 |
| 4 | `f` | 裸名字，结束 | |

所以 `f` 是"指向函数的指针，该函数接受 `int`，返回指向 `int[3]` 的指针"。

等价的"**右左法则**"（right-left rule）是同一过程的反向：从名字出发，先向右读后缀运算符，碰到右括号就转向左读前缀运算符，碰到左括号就跳出这一层括号，继续向右……读出的短语顺序正好是自然语言顺序。与流传的"螺旋法则"相比，右左法则直接对应文法中的优先级，不会在多维数组或多层函数上出错。

```cpp title="read-declarator.cpp" ok
#include <type_traits>

int (*(*f)(int))[3];

using A3  = int[3];
using PA3 = A3*;            // 指向 int[3] 的指针
using Fn  = PA3(int);       // 接受 int、返回 PA3 的函数
static_assert(std::is_same_v<decltype(f), Fn*>);

// 经典的 signal：接受 int 和函数指针，返回函数指针
void (*signal(int, void (*)(int)))(int);
auto signal2(int, void (*)(int)) -> void (*)(int);   // 尾置返回类型写法
static_assert(std::is_same_v<decltype(signal), decltype(signal2)>);

int (*arr[2])(int);         // 2 个函数指针组成的数组
static_assert(std::is_same_v<decltype(arr), int (*[2])(int)>);

int main() { }
```

!!! tip "声明模仿使用"
    `int (*(*f)(int))[3]` 可以按使用来读：`f` 是什么样的东西，才能让 `(*(*f)(5))[2]` 得到一个 `int`？——`*f` 能被调用，所以 `f` 指向函数；调用结果可以 `*`，所以返回指针；`*` 之后可以下标，所以指向数组。表达式与声明符的运算符优先级完全一致，这正是 C 的设计意图（[[dcl.fct#21]] 的例子专门比较了 `*fpi(int)` 与 `(*pif)(const char*, const char*)`）。

### 尾置返回类型

`auto D1(形参) -> R` 形式的函数声明符要求说明符恰好是 `auto`（[[dcl.fct#1]] ¶1.3），声明的返回类型是 `R`。它解决两个问题：

1. **可读性**：返回函数指针、数组指针的函数不必把返回类型"拆开包"在名字两边（见上面的 `signal2`）。
2. **作用域**：尾置返回类型出现在形参之后，所以可以用形参（`decltype(t + u)`）；在类外定义成员函数时，它位于类作用域内，可以直接使用成员类型名，不必再写 `C::`。

```cpp title="trailing-return.cpp" ok
struct C {
    using size_type = unsigned;
    size_type n() const;
    auto m() const -> size_type;
};
C::size_type C::n() const { return 1; }            // 前置返回类型：必须写 C::size_type
auto C::m() const -> size_type { return 0; }       // 尾置返回类型：已在 C 的作用域中

template<class T, class U>
auto add(T t, U u) -> decltype(t + u) { return t + u; }

auto (*fp)(int) -> long = nullptr;                 // 指向函数的指针也可以用尾置写法

int main() { return add(1, 2L) == 3 && C{}.m() == 0 ? 0 : 1; }
```

尾置返回类型只能附在**最外层**函数声明符上，且说明符必须是**单独的** `auto`：

```cpp title="trailing-return-bad.cpp" error
auto *f() -> int;        // error: 说明符必须是单独的 auto（这里 * 让最外层变成指针声明符）
```

## 实现视角

!!! impl
    - **解析器**：C++ 声明的文法不是上下文无关可判定的——同一串记号是声明还是表达式，取决于某个名字是不是类型（`a * b;`）。GCC 与 Clang 都采用"试探性解析"（tentative parsing）：先尝试按声明解析，失败再回退，这正是 [[dcl.ambig.res]] 的规则在实现上的体现。
    - **诊断**：Clang 对多种情形给出针对性诊断，例如 requires 子句放在尾置返回类型之前时提示 "trailing return type must appear before trailing requires clause"，对非模板函数上的 requires 子句提示 "non-templated function cannot have a requires clause"。
    - **类型名打印**：编译器在诊断中打印类型时使用的就是 *type-id* 写法（如 `int (*(*)(int))[3]`），学会读 type-id 对读诊断很有帮助。`c++filt` / `__cxa_demangle` 输出的也是这种形式。

## 历史与演进

!!! history
    - **C 与 C++98**：声明符文法继承自 C，"声明模仿使用"是 Dennis Ritchie 的设计。C++ 增加了引用 `&`、成员指针 `C::*`、函数声明符上的 cv 限定（成员函数）和异常规格。
    - **C++11**：尾置返回类型、右值引用 `&&`、引用限定符、`noexcept`、属性说明符序列（可出现在 *declarator-id*、`*`、`[]` 之后）、形参包声明符 `...`。
    - **C++17**：`noexcept` 成为函数类型的一部分（[[dcl.fct]]）。
    - **C++20**：尾置 requires 子句；简写函数模板（[[dcl.fct#23]]）。
    - **C++26**：函数契约说明符（[[dcl.contract]]）。
    - **C++26 之后的草案**：引入 *nofun-type-id*，消除 `sizeof(int())` 等 type-id/表达式歧义中"解析为函数类型然后报错"的情形。

## 陷阱

!!! pitfall "`const` 的位置"
    `const int *p`、`int const *p` 都是"指向 const int 的指针"；`int *const p` 是"const 指针"。规则：`*` 右边的 cv 修饰指针本身（[[dcl.ptr]]），说明符里的 cv 修饰基础类型。而 `typedef int *IP; const IP p;` 是 `int *const`——因为 `const` 修饰的是说明符给出的整个类型 `IP`，不是文本替换。

!!! pitfall "块作用域函数声明"
    在函数体内写 `void helper();` 声明的是外围命名空间的函数，名字只在块内可见；它**不能有定义**（函数只能在命名空间或类作用域定义，[[dcl.fct.def.general#2]]），也不能是简写函数模板（[[dcl.fct#25]]）。加上 [[dcl.ambig.res]] 的规则，`T x();` 在块内就是一个这样的函数声明——"最令人烦恼的解析"。

!!! pitfall "多声明符中的 `S S, T;`"
    同一声明中，后面的声明符看到的是**说明符开始时**查找到的名字含义，不受前面声明符引入的名字影响（说明符只查找一次）；但声明符内部（如数组边界、初始化器）是在前面声明符的名字已经可见之后才解析的：`int n = 3, a[n];` 中 `a[n]` 的 `n` 就是刚声明的 `n`（这里非良构，因为 `n` 不是常量表达式；换成 `const int n = 3, a[n] = {1, 2, 3};` 就良构——此时 `a` 也是 `const int` 数组，所以必须有初始化器）。

## 思考题

!!! question "思考题 1"
    写出 `extern char *(*(**foo[][8])())[];` 中 `foo` 的类型（用中文短语），并用 `using` 别名把它分解成可读的形式。

<details markdown="1">
<summary>答案</summary>

从外向内剥。注意优先级：整个声明符是 `*(*(**foo[][8])())[]`，前缀 `*` 比后缀 `[]` 更"外"，所以最外层是开头那个 `*`，贴着 `char` 的是"指向 `char` 的指针"。去掉它：`(*(**foo[][8])())[]`，最外层是后缀 `[]` → "〔char*〕的未知边界数组"。去掉：`*(**foo[][8])()` → 前缀 `*` → "指向〔char* 的未知边界数组〕的指针"。去掉：`(**foo[][8])()` → 后缀 `()` → "无形参、返回〔该指针〕的函数"。去掉：`**foo[][8]` → 两个前缀 `*` → "指向〔指向该函数的指针〕的指针"。最后 `foo[][8]` → "未知边界的数组，其元素是 8 个〔……〕的数组"。

合起来：`foo` 是"未知边界数组，元素为 8 个元素的数组，元素为指向指针的指针，该指针指向函数，函数无形参、返回指向'未知边界的 char* 数组'的指针"。

```cpp
using CPArr = char*[];          // 未知边界的 char* 数组
using Fn    = CPArr*();         // 返回指向它的指针的函数
using Elem  = Fn**;             // 指向函数指针的指针
extern Elem foo[][8];           // 与原声明同类型
```
（必须写 `extern`：不带初始化器的未知边界数组变量只能声明、不能定义，[[dcl.array#7]]。）
</details>

!!! question "思考题 2"
    为什么 `void f() { extern int x = 1; }` 非良构，而 `void f() { static int x = 1; }` 良构？用 ¶4 的术语回答。

<details markdown="1">
<summary>答案</summary>

¶4 要求初始化器只能出现在"宿主作用域等于目标作用域"的变量声明上。`static int x` 居于块作用域，目标作用域也是该块作用域（它是一个块变量），二者相同；`extern int x` 居于块作用域（宿主作用域 = 块），但按 [[dcl.meaning.general]] ¶3.5，它的目标作用域是最内层外围命名空间，二者不同。直觉上：前者定义一个块内可见的静态变量，后者只是"引用别处定义的变量"，不能在这里定义它。
</details>

!!! question "思考题 3"
    `template<class T> struct S { void f() requires true; };` 中的 `f` 不是函数模板，为什么可以有尾置 requires 子句？`S<int>::f` 的类型里有没有这个约束？

<details markdown="1">
<summary>答案</summary>

¶5 要求的是"模板化函数"（templated function），按 [[temp.pre]]，类模板的成员函数是模板化实体，所以允许。约束不是函数类型的一部分（[[dcl.fct#13]]），`S<int>::f` 的类型就是 `void()`（作为成员函数）；约束只影响该函数在重载决议中是否可行、以及多个声明之间的对应关系。
</details>

## 小结

!!! summary
    | 主题 | 要点 |
    |---|---|
    | 结构 | 声明 = 说明符序列（基础类型 + 属性）+ 若干声明符（每个一个实体） |
    | 多个声明符 | 逐个独立分析；说明符只查找一次（`S S, T;`）；`auto` 须推导一致 |
    | 初始化器 | 只用于变量，且宿主作用域 = 目标作用域（块作用域 `extern` 不行） |
    | 尾置 requires | 只用于模板化函数；位于尾置返回类型之后；不属于函数类型 |
    | 优先级 | 后缀 `()` `[]` 比前缀 `*` `&` `C::*` 紧；括号只改结合，不改类型 |
    | 读法 | 从外向内剥运算符，或从名字出发右左交替读 |
    | type-id | 省略名字的声明；名字位置唯一确定；*nofun-type-id* 的最外层不能是函数 |
    | 尾置返回类型 | 说明符须为单独的 `auto`；只在最外层；可用形参、在类作用域内查找 |
    | 限定声明符 | 必须居于命名空间作用域，且对应已有的可提名声明——不能引入新成员 |
    | 友元 | 不绑定名字；非限定友元的目标作用域是最内层外围命名空间 |
