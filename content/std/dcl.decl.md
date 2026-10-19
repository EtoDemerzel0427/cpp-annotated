---
title: 声明符
summary: 一个声明怎样由说明符和声明符组成，怎样读懂任意复杂的声明符，以及 type-id、尾置返回类型、尾置 requires 子句和限定名声明的规则。
status: draft
covers: dcl.decl.general, dcl.name, dcl.meaning, dcl.meaning.general
related: dcl.pre, dcl.spec, dcl.ambig.res, dcl.ptr, dcl.ref, dcl.array, dcl.fct, dcl.init, basic.scope.scope, temp.pre
tags: 声明符, 文法, type-id, 尾置返回类型
updated: 2026-10-19
---

!!! tldr
    - 一个声明由说明符序列和逗号分隔的若干声明符组成。`*`、`&`、`[]`、`()` 属于各自的声明符，所以 `int* a, b;` 里的 `b` 是 `int`。
    - 声明符里运算符的优先级和表达式一样：后缀的 `[]`、`()` 比前缀的 `*`、`&` 结合得紧。括号只改变结合方式，不改变类型。
    - 读复杂声明符的方法是从最外层运算符向内剥，或者从名字出发先向右读、再向左读。
    - *type-id* 是省略了名字的声明，名字本应出现的位置是唯一确定的。
    - 用限定名声明（`void N::f() {}`）不能引入新成员；块作用域里的函数声明和 `extern` 声明，声明的是外围命名空间的成员。

## 说明符与声明符 [dcl.decl.general]

```cpp
const int *p, a[3], f(int);
```

这个声明分成两部分。前面的 `const int` 是**声明说明符序列**（*decl-specifier-seq*，见 [[dcl.spec]]），它给出一个基础类型，以及存储期、链接这类属性。后面逗号分隔的 `*p`、`a[3]`、`f(int)` 是三个**声明符**（[[g:declarator|declarator]]）。

¶1 每个声明符声明一个实体：一个变量、函数或类型。

¶2 声明符可选地给实体命名，并用 `*`（指向……的指针）、`()`（返回……的函数）这样的运算符修饰说明符给出的类型。所以上面声明了指向 `const int` 的指针 `p`、3 个 `const int` 的数组 `a`，以及接受 `int`、返回 `const int` 的函数 `f`。

声明符后面可以跟初始化器（[[dcl.init]]），这样的组合叫 *init-declarator*。省略了名字的声明符叫**抽象声明符**（[[g:abstract-declarator|abstract-declarator]]），出现在没有名字的形参、*type-id* 和异常声明里。读它时，可以当作名字本应出现的位置上有一个独一无二的标识符（见下文 [dcl.name] 一节）。

### 多个声明符逐个分析（¶3）

¶3 同一个声明里的每个声明符都单独分析，如同它独自构成一个声明。所以 `T D1, D2;` 通常等价于 `T D1; T D2;`。

!!! pitfall "`int* a, b;` 中的 `b` 不是指针"
    `*` 属于声明符 `*a`，不属于说明符。说明符只有 `int`，所以 `b` 是 `int`。需要两个指针时，每个声明符都写 `*`，或者先定义别名 `using IP = int*; IP a, b;`，这时 `IP` 是说明符，两者都是指针。

标准的注 2 指出，通常等价有两个例外。第一个例外是声明符引入的名字遮住了说明符里的类型名：

<div class="compare" markdown="1">

```cpp run ok
struct S { };
void f() {
  S S, T;  // 两个 S 类型的对象
  (void)S; (void)T;
}
```

```cpp run error
struct S { };
void f() {
  S S;
  S T;     // error: S 现在是变量名
}
```

</div>

说明符 `S` 只在声明开始时查找一次，那时它还是类名。拆成两个声明后，第二个声明重新查找 `S`，找到的是刚声明的变量。

第二个例外是 `auto`：同一个声明里的所有声明符必须推导出同一个类型（[[dcl.spec.auto]]）。

```cpp run error
auto i = 1, j = 2.0;   // error: i 推导为 int，j 推导为 double
```

不过说明符只查找一次，并不意味着后面的声明符看不到前面的名字。声明符内部的数组边界、初始化器，是在前面的名字已经可见之后才解析的：

```cpp run ok
const int n = 3, a[n] = {1, 2, 3};   // a[n] 里的 n 就是刚声明的 n
int main() { return a[0] - 1; }
```

这里 `a` 的类型是 `const int[3]`，`const` 同样作用于它，所以必须有初始化器。

## 声明符的文法与优先级 [dcl.decl.general]

### 声明模仿使用

C 的声明符文法遵循**声明模仿使用**（declaration mirrors use）的原则。`int *p` 的意思是 `*p` 是 `int`；`int a[3]` 的意思是 `a[i]` 是 `int`；`int f(int)` 的意思是用一个 `int` 调用 `f` 得到 `int`。

声明符里的运算符和表达式里同名的运算符优先级相同：后缀的 `()`、`[]` 比前缀的 `*` 结合得紧。所以下面两个声明完全不同：

<div class="compare" markdown="1">

```cpp
int *f();     // f 是函数，返回 int*
int *a[3];    // a 是数组，元素是 int*
```

```cpp
int (*f)();   // f 是指针，指向返回 int 的函数
int (*a)[3];  // a 是指针，指向 int[3]
```

</div>

### 文法本身编码了优先级（¶7）

¶7 下面是声明符文法的核心部分，略去了属性：

```
declarator:
    ptr-declarator
    noptr-declarator parameters-and-qualifiers trailing-return-type
ptr-declarator:
    noptr-declarator
    ptr-operator ptr-declarator                     // 前缀：* & && C::*
noptr-declarator:
    declarator-id
    noptr-declarator parameters-and-qualifiers      // 后缀：(形参) cv ref noexcept
    noptr-declarator [ constant-expression(opt) ]   // 后缀：[N]
    ( ptr-declarator )                              // 括号
```

从这个文法可以直接读出三条结论：

1. 后缀运算符只能接在 *noptr-declarator* 上，前缀运算符只能接在 *ptr-declarator* 上。所以 `*a[3]` 只能解析为 `*(a[3])`，后缀先结合。
2. 要让前缀先结合，必须用括号把 *ptr-declarator* 包成 *noptr-declarator*，写成 `(*a)[3]`。
3. *trailing-return-type* 只出现在顶层 *declarator* 的产生式里，所以尾置返回类型只能写在最外层的函数声明符上。

其余部件：*parameters-and-qualifiers* 是函数声明符的后缀，包括形参列表、cv 限定、引用限定、`noexcept`（见 [[dcl.fct]]）。*ptr-operator* 是 `*`、`&`、`&&` 或 `C::*`；`*` 和 `C::*` 后面可以跟 cv 限定符，`&` 和 `&&` 后面不能（[[dcl.ref]]）。*declarator-id* 是被声明的名字，前面可以有 `...`（声明函数形参包），名字本身可以是限定名、运算符函数名、*template-id* 等。

## 从声明符读出类型 [dcl.meaning.general]

### 说明符作用于每个名字（¶4）

¶4 `static`、`extern`、`thread_local`、`inline`、`constexpr`、`typedef` 这类说明符直接作用于声明中的每一个名字；每个名字的类型则由说明符序列和它自己的声明符共同决定。

```cpp run ok
static int a, *b, c[2];        // 三者都是 static
typedef int I, *IP, A3[3];     // 三个别名：int、int*、int[3]
static_assert(sizeof(A3) == 3 * sizeof(int));
int main() { (void)b; (void)c; return a; }
```

### 递归求类型（¶5–8）

¶5 对每个声明符，声明都可以看成 `T D` 的形式：`T` 是说明符序列，`D` 是声明符。标准用一个递归过程求出 `D` 中名字的类型。

¶6 先由说明符序列确定一个类型 `T`。说明符的顺序不重要，`int unsigned i;` 里的 `int unsigned` 确定的是 `unsigned int`（[[dcl.type.simple]]）。

¶7 如果 `D` 只是一个名字，它的类型就是 `T`。

¶8 如果 `D` 形如 `( D1 )`，类型与 `T D1` 中的相同。括号不改变类型，只改变复杂声明符的结合方式。所以 `int (x);` 就是 `int x;`，[[dcl.ambig.res]] 里的各种歧义都源于这一点。

其余形式由后面几个子条款分别定义，模式完全一样。设 `T D1` 中名字的类型是"〔内层修饰〕`T`"，那么：

| `D` 的形式 | `D` 中名字的类型 | 条款 |
|---|---|---|
| `* cv D1` | 〔内层修饰〕cv 指向 `T` 的指针 | [[dcl.ptr]] |
| `& D1` / `&& D1` | 〔内层修饰〕`T` 的左值 / 右值引用 | [[dcl.ref]] |
| `C::* cv D1` | 〔内层修饰〕cv 指向 `C` 的 `T` 类型成员的指针 | [[dcl.mptr]] |
| `D1 [N]` | 〔内层修饰〕`N` 个 `T` 的数组 | [[dcl.array]] |
| `D1 ( 形参 ) cv ref noexcept` | 〔内层修饰〕接受这些形参、返回 `T` 的函数 | [[dcl.fct]] |

标准把〔内层修饰〕叫做 *derived-declarator-type-list*。换句话说，最外层运算符贡献的短语紧贴着 `T`，越往内的运算符，贡献的短语越靠前。

### 手工读一个声明符

把递归展开，就得到一个手工方法：找出 `D` 的最外层运算符，它贡献的短语紧贴当前的结果；然后对剩下的内层声明符重复，直到只剩名字。判断最外层时，前缀运算符比后缀运算符更靠外，一对括号整体算一个单元。

以 `int (*(*f)(int))[3];` 为例：

| 步骤 | 当前 `D` | 最外层运算符 | 累积的类型 |
|---|---|---|---|
| 1 | `(*(*f)(int))[3]` | 后缀 `[3]`（括号整体是一个单元） | 3 个 `int` 的数组 |
| 2 | `*(*f)(int)` | 去掉括号后，最外层是前缀 `*` | 指向〔3 个 `int` 的数组〕的指针 |
| 3 | `(*f)(int)` | 后缀 `(int)` | 接受 `int`、返回〔指向 `int[3]` 的指针〕的函数 |
| 4 | `*f` | 前缀 `*` | 指向〔上一行那种函数〕的指针 |
| 5 | `f` | 只剩名字 | |

所以 `f` 是函数指针，它指向的函数接受 `int`，返回指向 `int[3]` 的指针。

另一个常见的方法是**右左法则**（right-left rule），它是同一过程的反向：从名字出发，先向右读后缀运算符，碰到右括号就转向左读前缀运算符，碰到左括号就跳出这层括号，再继续向右。读出的短语顺序正好是自然语言的顺序。

也可以按声明模仿使用来读：`f` 要是什么，`(*(*f)(5))[2]` 才是一个 `int`？`*f` 能调用，所以 `f` 指向函数；调用结果能解引用，所以函数返回指针；解引用后能下标，所以那个指针指向数组。

```cpp run ok
#include <type_traits>

int (*(*f)(int))[3];
using A3  = int[3];
using Fn  = A3*(int);          // 接受 int、返回 int(*)[3] 的函数
static_assert(std::is_same_v<decltype(f), Fn*>);

// signal：接受 int 和函数指针，返回函数指针
void (*signal(int, void (*)(int)))(int);
auto signal2(int, void (*)(int)) -> void (*)(int);
static_assert(std::is_same_v<decltype(signal), decltype(signal2)>);

int (*arr[2])(int);            // 2 个函数指针组成的数组
static_assert(std::is_same_v<decltype(arr), int (*[2])(int)>);

int main() { }
```

!!! pitfall "`const` 加在别名上不是文本替换"
    `typedef int *IP; const IP p;` 中 `p` 的类型是 `int *const`，不是 `const int *`。`const` 修饰的是说明符给出的整个类型 `IP`，也就是指针本身。

## type-id：省略名字的声明 [dcl.name]

### 名字的位置是唯一的（¶1）

`sizeof`、`new`、类型转换、模板实参、`using` 别名这些地方需要单独写一个类型，写法是 [[g:type-id|type-id]]。

¶1 type-id 在语法上就是一个省略了实体名字的声明：说明符加一个抽象声明符。

抽象声明符里，名字本应出现的位置是唯一确定的。把名字放回去，得到一个普通的声明，名字的类型就是这个 type-id 表示的类型：

| type-id | 放回名字 | 类型 |
|---|---|---|
| `int *` | `int *pi` | 指向 `int` 的指针 |
| `int *[3]` | `int *p[3]` | 3 个 `int*` 的数组 |
| `int (*)[3]` | `int (*p3i)[3]` | 指向 `int[3]` 的指针 |
| `int *()` | `int *f()` | 无形参、返回 `int*` 的函数 |
| `int (*)(double)` | `int (*pf)(double)` | 指向接受 `double`、返回 `int` 的函数的指针 |

找位置的方法：名字在所有前缀运算符之后、所有后缀运算符之前，并且位于最内层那对不是形参列表的括号里。例如 `int (*(*)(int))[3]` 的最内层括号是 `(*)`，名字放在 `*` 后面，得到 `int (*(*f)(int))[3]`。编译器在诊断里打印类型时用的正是 type-id 写法，学会读它也有助于读诊断。

¶2 的注提醒，类型也可以用 *typedef-name* 命名（[[dcl.typedef]]）。

### nofun-type-id

当前草案还定义了 [[g:nofun-type-id|nofun-type-id]]：最外层不能是函数声明符的 type-id。`int()`、`auto() -> int` 不是 nofun-type-id，`int(*)()`、`int(&)()` 是。这是 C++23 之后的新措辞。

`sizeof`、`alignof`、C 风格转换 `(T)e`、`new (T)` 和尾置返回类型都改用了 nofun-type-id。这些位置本来就不能出现函数类型。改用之后，`sizeof(int())` 不可能再读成函数类型，只能读成表达式，原来非良构的写法变得良构，详见 [[dcl.ambig.res#2]]。`typeid(…)` 和模板实参仍然用 type-id，因为函数类型在那里有意义，比如 `std::function<int()>`。

## 尾置返回类型 [dcl.decl.general]

`auto f(形参) -> R` 声明一个返回 `R` 的函数。按 [[dcl.fct#1.3]]，这种写法要求说明符恰好是单独的 `auto`。它解决两个问题：

1. 返回函数指针、数组指针的函数，不必把返回类型拆成两半写在名字两边，比较上面的 `signal` 与 `signal2`。
2. 返回类型写在形参之后，可以使用形参（`decltype(t + u)`）；在类外定义成员函数时，它已经处在类的作用域里，可以直接用成员类型名。

```cpp run ok
struct C {
  using size_type = unsigned;
  size_type n() const;
  auto m() const -> size_type;
};
C::size_type C::n() const { return 1; }     // 前置：必须写 C::size_type
auto C::m() const -> size_type { return 0; } // 尾置：已在 C 的作用域中

template<class T, class U>
auto add(T t, U u) -> decltype(t + u) { return t + u; }

auto (*fp)(int) -> long = nullptr;          // 函数指针也可以用尾置写法

int main() { return add(1, 2L) == 3 && C{}.m() == 0 ? 0 : 1; }
```

```cpp run error
auto *g() -> int;   // error: 说明符必须是单独的 auto
```

## 初始化器、requires 子句与契约说明符 [dcl.decl.general]

¶1 的文法规定，*init-declarator* 有两种形式：声明符后面跟初始化器；或者声明符后面跟可选的尾置 requires 子句和可选的函数契约说明符。后两者只对函数有意义，所以不会与初始化器同时出现。

### 何时可以写初始化器（¶4）

要讲这一段，先要两个术语（[[basic.scope.scope]]）。一个声明写在哪个作用域里，就说它**栖居**（inhabit）在那个作用域。名字被引入、实体归属的作用域叫声明的**目标作用域**（[[g:target-scope|target scope]]），通常就是它栖居的作用域。**宿主作用域**（host scope）定义为：如果声明栖居在块作用域，宿主作用域就是这个块作用域；否则就是目标作用域。

¶4 只有当声明符声明的是变量，并且声明的宿主作用域与目标作用域相同时，才能带初始化器。这排除了两类情形：

- 声明的不是变量，比如函数。`virtual void f() = 0;` 里的 `= 0` 是纯说明符（*pure-specifier*），属于类成员声明的文法，不是初始化器。
- 块作用域的 `extern` 声明。它栖居在块里，宿主作用域是这个块；但它的目标作用域是外围命名空间（见下文第 3.5 项），两者不同。

<div class="compare" markdown="1">

```cpp run ok
void f() {
  static int x = 1;  // 宿主 = 目标 = 块
  (void)x;
}
```

```cpp run error
int x;
void f() {
  extern int x = 1;  // error
}
```

</div>

块作用域的 `extern int x;` 是在引用一个别处定义的命名空间变量。在块里给它初始化器，等于在函数体里定义一个命名空间作用域的变量，所以不允许。相比之下，类外定义静态数据成员 `int A::s = 2;` 栖居在命名空间作用域，宿主作用域就是目标作用域（类 `A` 的作用域），可以初始化。

### 尾置 requires 子句（¶5）

¶5 写在声明符之后的 requires 子句叫**尾置 requires 子句**（trailing *requires-clause*），它只能出现在声明**模板化函数**（templated function，[[temp.pre]]）的声明符上。模板化函数不只是函数模板，还包括类模板的成员函数、泛型 lambda 的调用运算符等位于模板化实体内部的函数。最常见的用法是按类模板实参有条件地启用一个普通成员函数：

```cpp run ok
#include <type_traits>

template<class T>
struct Box {
  T value;
  void increment() requires std::is_arithmetic_v<T> { ++value; }
};

int main() {
  Box<int> b{1};
  b.increment();          // OK
  Box<void*> p{nullptr};  // OK：只要不调用 increment
  (void)p;
}
```

标准例 1 列出了不允许的位置：

```cpp run error
void f1(int a) requires true;                 // error: 不是模板化函数
template<typename T>
  auto f2(T a) -> bool requires true;         // OK
template<typename T>
  auto f3(T a) requires true -> bool;         // error: 必须在尾置返回类型之后
void (*pf)() requires true;                   // error: 约束变量
void g(int (*)() requires true);              // error: 约束形参
auto* p = new void(*)(char) requires true;    // error: 不是函数声明
```

尾置 requires 子句不是函数类型的一部分（[[dcl.fct#13]]），但两个声明是否对应（声明同一个实体，[[basic.scope.scope]]）时要比较它。所以两个只有尾置 requires 子句不同的成员函数是两个重载，重载决议按约束的偏序（[[temp.constr.order]]）选择。

### 契约说明符（¶6）{{c++26}}

¶6 函数契约说明符 `pre(…)`、`post(…)` 只能出现在声明函数的声明符上，见 [[dcl.contract.func]]。

## 名字与目标作用域 [dcl.meaning.general]

### declarator-id（¶1）

¶1 一个声明符恰好包含一个 *declarator-id*，它就是被声明的名字。如果这个名字是 *template-id*（如 `f<int>`），声明必须是模板声明、显式特化或显式实例化：

```cpp run error
template<class T> void tf(T);
void tf<int>(int);              // error: 需要 template<>
template<> void tf<int>(int);   // OK：显式特化
```

名字不是普通标识符时（`operator+`、`operator int`、`~C`、`operator""_x`），声明的是相应的特殊函数（[[class.conv.fct]]、[[class.dtor]]、[[over.oper]]、[[over.literal]]）。紧跟在名字后面的属性属于被声明的实体；跟在 `*` 后面的属性属于指针类型，跟在 `[]` 后面的属于数组类型。

### 用限定名声明（¶3.1–3.4）

```cpp run error
namespace Q {
  namespace V { void f(); }
  void V::f() { }        // OK
  void V::g() { }        // error: g 还不是 V 的成员
  namespace V { void g(); }
}
namespace R {
  void Q::V::g() { }     // error: R 不包围 Q
}
```

¶3.1 名字是限定名时，声明必须栖居在命名空间作用域里，不能在函数体或类里写 `void N::f() {}`。

¶3.4 此时不查找新名字，而是要求声明符对应限定名所指作用域中一个或多个已有的声明；目标作用域就是那些声明的目标作用域。换句话说，限定名只能重新声明或定义已有的成员，不能引入新成员。

`R` 里那一行的错误来自 [[basic.scope.scope]] 的另一条要求：限定声明必须出现在包围目标命名空间的作用域里，而 `R` 不包围 `Q::V`。

¶3.3 显式实例化、偏特化和显式特化不绑定名字。识别它们声明的是哪个函数模板特化时，只考虑在限定名所指作用域中**可提名**（nominable）的查找结果。标准例 1 中，`using P::f` 引入的 `P::f` 在 `N` 中不可提名，所以 `template<> void N::f(int*)` 特化的是内联命名空间 `O` 里的版本。

### 块作用域的函数声明与 extern 声明（¶3.5）

¶3.5 如果一个声明栖居在块作用域，并且声明的是函数或带 `extern`，那么它的目标作用域是最内层的外围命名空间，但名字只绑定在这个块里。这样的声明不能附属于具名模块。

```cpp run error
namespace X {
  void p() {
    q();               // error: q 尚未声明
    extern void q();   // q 是 X 的成员，名字只在 p 的块内可见
    extern void r();   // r 也是 X 的成员
  }
  void middle() {
    q();               // error: 这里找不到 q
  }
  void q() { }         // X::q 的定义
}
void X::r() { }        // error（标准例 3）：r 不能用限定名声明
```

最后一行违反第 3.4 项：块作用域的 `extern` 声明在 `X` 中不可提名，限定名找不到可以对应的声明。截至写作时，本机 Clang 23 接受这一行，没有给出诊断。

块内写 `void helper();` 声明的也是外围命名空间的函数。它不能在块里定义（[[dcl.fct.def.general#2]]），也不能是简写函数模板（[[dcl.fct#25]]）。再加上 [[dcl.ambig.res]] 的规则，块内的 `T x();` 就成了这样一个函数声明，这就是所谓[[g:most-vexing-parse|最令人烦恼的解析]]。

### 友元声明（¶2）

¶2.1 友元声明的声明符不绑定名字。所以只在类里声明或定义的友元函数（隐藏友元）不能被普通查找找到，只能经由实参依赖查找（ADL）找到：

```cpp run error
struct N {
  friend void hf(N) { }   // 目标作用域是全局命名空间，但不绑定名字
};
void use()  { hf(N{}); }      // OK：ADL 在关联类 N 中找到它
void use2() { auto p = &hf; } // error: 普通查找找不到 hf
```

其余规则按名字的形式区分：

- ¶2.3 名字不是限定名，也不是 *template-id*：不查找这个名字，目标作用域是最内层的外围命名空间。如果友元声明在局部类里，它必须对应最内层块作用域中一个可达的声明。
- ¶2.2 名字是限定名（`friend void N::f(int);`）或 *template-id*（`friend void g<>(int);`）：查找这个名字，声明符必须对应至少一个找到的声明，这些声明的目标作用域相同，它也就是友元声明的目标作用域。所以限定的友元声明同样不能顺带声明新函数。

在第 2.2 项的查找中，如果友元声明本身不是模板声明，结果要先过滤：名字是 *template-id* 时丢弃所有非模板函数（第 2.2.1.1 项）；否则，如果声明符对应某个找到的非模板函数，就丢弃所有函数模板（第 2.2.1.2 项）；剩下的函数模板通过推导（[[temp.deduct.decl]]）换成具体的特化，推导失败的丢弃（第 2.2.1.3 项）。

## 实现视角

!!! impl
    C++ 的声明文法要知道一个名字是不是类型才能解析：`a * b;` 可以是乘法，也可以是声明指针 `b`。GCC 和 Clang 都用试探性解析（tentative parsing）：遇到可能是声明的记号序列，先试着按声明解析，失败再回退按表达式解析。[[dcl.ambig.res]] 的规则就是在规定这种取舍。

## 历史与演进

!!! history
    - 声明符文法继承自 C。C++ 在此基础上增加了引用 `&`、成员指针 `C::*`，以及函数声明符上的 cv 限定（用于成员函数）。
    - C++11 加入了尾置返回类型、右值引用 `&&`、引用限定符、`noexcept`、属性，以及声明形参包的 `...`。
    - C++20 加入了尾置 requires 子句和简写函数模板（[[dcl.fct#23]]）。
    - C++26 加入了函数契约说明符（[[dcl.contract.func]]）。
    - C++23 之后的草案引入了 *nofun-type-id*。

## 思考题

!!! question "思考题 1"
    写出 `extern char *(*(**foo[][8])())[];` 中 `foo` 的类型，并用 `using` 别名把它拆成可读的形式。

<details markdown="1">
<summary>答案</summary>

从外向内剥。整个声明符是 `*(*(**foo[][8])())[]`。

1. 最外层是开头的前缀 `*`：指向 `char` 的指针，即 `char*`。
2. 剩下 `(*(**foo[][8])())[]`，最外层是后缀 `[]`：`char*` 的未知边界数组。
3. 剩下 `*(**foo[][8])()`，最外层是前缀 `*`：指向〔`char*` 的未知边界数组〕的指针。
4. 剩下 `(**foo[][8])()`，最外层是后缀 `()`：无形参、返回〔上一步那种指针〕的函数。
5. 剩下 `**foo[][8]`，两个前缀 `*`：指向〔指向该函数的指针〕的指针。
6. 剩下 `foo[][8]`：未知边界的数组，元素是 8 个〔上一步那种指针〕的数组。

```cpp run ok
using CPArr = char*[];      // char* 的未知边界数组
using Fn    = CPArr*();     // 返回指向它的指针的函数
using Elem  = Fn**;         // 指向函数指针的指针
extern Elem foo[][8];
extern char *(*(**foo[][8])())[];   // 同一个类型，重声明成功
int main() { }
```

这里必须写 `extern`：没有初始化器的未知边界数组变量只能声明，不能定义（[[dcl.array#7]]）。
</details>

!!! question "思考题 2"
    `template<class T> struct S { void f() requires true; };` 中的 `f` 不是函数模板，为什么可以有尾置 requires 子句？`S<int>::f` 的类型里有这个约束吗？

<details markdown="1">
<summary>答案</summary>

¶5 要求的是模板化函数。按 [[temp.pre]]，类模板的成员函数是模板化实体，所以允许。约束不是函数类型的一部分（[[dcl.fct#13]]），`S<int>::f` 的类型就是 `void()`。约束只影响这个函数在重载决议中是否可行，以及判断两个声明是否对应。
</details>
