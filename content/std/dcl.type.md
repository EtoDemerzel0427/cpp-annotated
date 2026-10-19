---
title: 类型说明符
summary: 声明里决定类型的那些关键字和名字：哪些可以组合、const 和 volatile 的语义、简单类型说明符对应的类型、struct X 这类详述写法，以及 C++26 的包索引和类型拼接。
status: done
covers: dcl.type.general, dcl.type.cv, dcl.type.simple, dcl.type.pack.index, dcl.type.elab, dcl.type.splice
papers: P2662, P2996
related: dcl.spec, basic.type.qualifier, basic.fundamental, dcl.type.decltype, dcl.spec.auto, dcl.type.class.deduct, basic.lookup.elab
tags: 声明, 类型, cv 限定, 反射
updated: 2026-10-19
---

!!! tldr
    - 一个声明里一般只能有一个类型说明符。`unsigned long long int` 能写，是因为标准列了六条组合例外，关键字的顺序可以任意。
    - C++ 没有隐式 int：除了构造、析构和转换函数，声明里必须有一个不是 `const`/`volatile` 的类型说明符。
    - 经由 const 访问路径不能修改对象；对象本身是 const 时，用 `const_cast` 去掉 const 再修改是未定义行为。
    - `char`、`signed char`、`unsigned char` 是三个不同的类型；`signed` 只对 `char` 有意义。
    - `struct X` 这类详述类型说明符可以前向声明、可以绕过名字隐藏，但不能指向 typedef 名，关键字还必须和类的种类相符。

## 哪些关键字可以组合 [dcl.type.general]

<div class="compare" markdown="1">

```cpp run ok
#include <type_traits>
// 顺序任意：unsigned long long
int long unsigned long x = 0;
static_assert(std::is_same_v<
    decltype(x), unsigned long long>);
int main() {}
```

```cpp error
long long long a;  // error
signed unsigned b; // error
unsigned double c; // error
int main() {}
```

</div>

左边四个关键字拼成了一个类型，右边每一行都非良构。区分它们的是本节的一条规则和六条例外。

¶1 **类型说明符**（type-specifier）是声明里描述类型的那部分说明符，共四种：简单类型说明符（`int`、类名、`decltype(…)` 等，见下一节）、详述类型说明符（`struct X`）、`typename` 说明符（`typename T::type`）和 cv 限定符（`const`、`volatile`）。在它的基础上再加上类定义 `struct X { … }` 和枚举定义 `enum E { … }`，就是**定义类型说明符**（defining-type-specifier）。

区分这两层，是因为有些位置不允许定义新类型。`sizeof(T)`、`static_cast<T>`、模板实参中的类型只能用类型说明符组成，所以 `sizeof(struct { int x; })` 非良构；普通声明和别名声明则可以定义类型。说明符序列末尾的属性属于前面这些说明符确定的类型，并且只在这一个声明里起作用。

### 至多一个，六条例外（¶2）

¶2 一般规则是：一个声明的完整说明符序列里至多有一个定义类型说明符。例外只有六条：

| ¶ | 例外 | 例子 |
|---|---|---|
| 2.1 | `const` 可以和除自身外的任何类型说明符组合 | `const int`、`const T` |
| 2.2 | `volatile` 可以和除自身外的任何类型说明符组合 | `volatile const int` |
| 2.3 | `signed`、`unsigned` 可以和 `char`、`long`、`short`、`int` 组合 | `unsigned char` |
| 2.4 | `short`、`long` 可以和 `int` 组合 | `short int` |
| 2.5 | `long` 可以和 `double` 组合 | `long double` |
| 2.6 | `long` 可以和 `long` 组合 | `long long` |

C 风格的多关键字类型名全部靠这六条成立。`long long long` 不合法，是因为 ¶2.6 只允许一个 `long` 和另一个 `long` 组合，没有哪一条允许第三个 `long` 再和 `long long` 组合。同理，`long double long` 也不合法。

```cpp error
long float f;       // error: long 只能和 int、double、long 组合
short long s;       // error
signed bool b;      // error
unsigned char8_t c; // error: char8_t、char16_t、char32_t、wchar_t 不能带符号说明符
typedef int T;
T unsigned u;       // error: 类型名不能和 unsigned 组合
```

[[dcl.type.simple#4]] 补充了一点：允许组合的这些关键字可以和其他说明符以任意顺序混排，`long static unsigned const long x = 0;` 等价于 `static const unsigned long long x = 0;`。

直接写 `const const int` 违反了 ¶2.1，本机 Clang 23 只给出 `-Wduplicate-decl-specifier` 警告，这满足必须诊断的要求。经由 typedef 或模板参数产生的重复 const 则是另一回事，见下文 cv 限定符一节。

### 没有隐式 int（¶3）

¶3 除了构造函数、析构函数和转换函数的声明，完整的说明符序列里至少要有一个不是 cv 限定符的定义类型说明符。C89 允许省略类型、默认为 `int`，C++ 不允许：

```cpp error
const x = 1;     // error: C89 中是 const int
static y;        // error
f() { }          // error: 函数也必须写返回类型
```

## 简单类型说明符 [dcl.type.simple]

### 关键字与类型的对应（表 17）

¶1 **简单类型说明符**（simple-type-specifier）包括基础类型的关键字（`char`、`int`、`long`、`unsigned`、`double`、`void` 等）、类型名（类名、枚举名、typedef 名，可以带限定）、模板特化 `std::vector<int>`、不带实参列表的类模板名（CTAD）、占位类型 `auto` 和 `decltype(auto)`，以及三种**计算类型说明符**（computed-type-specifier）：`decltype(e)`、包索引 `Ts...[I]` 和类型拼接 `[: r :]`。其中 `decltype`、`auto` 和 CTAD 各有单独的页面：[[dcl.type.decltype]]、[[dcl.spec.auto]]、[[dcl.type.class.deduct]]。

¶3 表 17 列出了基础类型关键字的全部合法组合。按得到的类型整理如下，同一行的写法等价，关键字顺序任意：

| 类型 | 写法 |
|---|---|
| `char`、`signed char`、`unsigned char` | 各自只有这一种写法，三者是不同的类型 |
| `char8_t`、`char16_t`、`char32_t`、`wchar_t`、`bool` | 各自唯一的关键字 |
| `int` | `int`、`signed`、`signed int` |
| `unsigned int` | `unsigned`、`unsigned int` |
| `short int` | `short`、`short int`、`signed short`、`signed short int` |
| `unsigned short int` | `unsigned short`、`unsigned short int` |
| `long int` | `long`、`long int`、`signed long`、`signed long int` |
| `unsigned long int` | `unsigned long`、`unsigned long int` |
| `long long int` | `long long`、`long long int`、`signed long long`、`signed long long int` |
| `unsigned long long int` | `unsigned long long`、`unsigned long long int` |
| `float`、`double`、`long double`、`void` | 各自唯一 |

¶4 注 2 指出，`signed` 只对 `char` 有作用。`char` 有没有符号由实现定义 {{impl}}，`signed char` 强制有符号；而且 `char`、`signed char`、`unsigned char` 是三个不同的类型（[[basic.fundamental]]）。`signed int` 和 `int` 却是同一个类型。

```cpp run ok
#include <type_traits>
static_assert(std::is_same_v<signed int, int>);
static_assert(!std::is_same_v<char, signed char>);
static_assert(!std::is_same_v<char, unsigned char>);
int main() {}
```

### 推导类类型的占位符（¶3）

¶3 前半段规定，类型说明符在下面三种形式之一时是**推导类类型的占位符**（placeholder for a deduced class type），用于类模板实参推导（CTAD，[[dcl.type.class.deduct]]）：

- ¶3.1 没有模板实参列表的模板名，可以带限定，如 `std::pair p(1, 2.0);` 中的 `std::pair`；
- ¶3.2 `pack-index-template-name`，即用包索引从模板模板参数包里取出的模板名；
- ¶3.3 {{c++26}} 指代类模板或别名模板的拼接 `[: r :]`。

其中的限定部分必须是非依赖的，而且这个模板必须是**可推导模板**（deducible template）：

- ¶3.4 类模板；
- ¶3.5 类型模板模板参数；
- ¶3.6 别名模板 A，它定义的类型形如 `nested-name-specifier(opt) template(opt) simple-template-id`，限定部分非依赖，而 `simple-template-id` 的模板名又指向一个可推导模板（不能是 A 自己的模板模板参数）。

¶3.6 就是 C++20 的别名模板 CTAD。`template<class T> using Vec = std::vector<T>;` 是可推导模板，`template<class T> using Ptr = T*;` 不是，因为 `T*` 不是一个模板特化。

```cpp run ok
#include <vector>
#include <utility>
template<class T> using Vec = std::vector<T>;
int main() {
    std::pair p(1, 2.0);   // std::pair<int, double>
    Vec v{1, 2, 3};        // C++20：std::vector<int>
    return int(v.size()) - 3 + (p.first - 1);
}
```

注 1 指出，在会进行 CTAD 的位置，**注入类名**（类模板内部对自身名字的隐式声明，[[temp.local]]）不会被当作模板名。所以在类模板 `A` 内部写 `A x(…);`，`A` 就是当前特化 `A<T>`，不会触发推导。

## const 与 volatile [dcl.type.cv]

const 限定类型本身怎样定义，见 [[basic.type.qualifier]]。本节讲 cv 限定符作为说明符的规则，以及修改 const 对象、访问 volatile 对象的后果。

### 写法上的规则（¶1–¶2）

¶1 一个 cv 限定符序列里，`const` 和 `volatile` 各自至多出现一次。说明符序列里有 cv 限定符时，后面必须有声明符，所以 `const struct S { };` 非良构：不知道 const 修饰的是谁。

经由 typedef 或模板参数产生的重复 cv 限定会被忽略：

```cpp run ok
#include <type_traits>
typedef const int CI;
const CI x = 1;        // const const int，即 const int
static_assert(std::is_same_v<decltype(x), const int>);
template<class T> using AddConst = const T;
static_assert(std::is_same_v<AddConst<const int>, const int>);
int main() {}
```

¶2 是一条注：变量声明为 const 会影响它的链接（命名空间作用域的非 volatile const 变量默认是内部链接，[[basic.link#3]]）和能否用于常量表达式（[[expr.const.init]]）。const 对象的定义必须有初始化器，或者它的类型能被默认初始化成确定的值（[[dcl.init.general]]）。

### 访问路径与对象本身（¶3–¶4）

```cpp run ub
int main() {
    int i = 2;
    const int* cip = &i;   // const 访问路径，指向非 const 对象
    // *cip = 4;           // error: 不能经由 const 访问路径修改
    int* ip = const_cast<int*>(cip);
    *ip = 4;               // OK: i 本身不是 const 对象

    const int* ciq = new const int(3);
    int* iq = const_cast<int*>(ciq);
    *iq = 4;               // UB: 修改 const 对象
    delete ciq;
}
```

¶3 指向 cv 限定类型的指针或引用，不一定真的指向 cv 限定的对象，但要按 cv 限定的对象对待：即使对象本身可以修改，也不能经由 const 访问路径修改它。注 4 指出，不用强制转换就无法绕过这一限制。

¶4 在 const 对象的生存期内试图修改它，行为未定义 {{ub}}。

!!! std
    Any attempt to modify a const object during its lifetime results in undefined behavior.

这样就有两个问题要分开问。表达式的类型带不带 const，决定编译期能不能写 `*p = 4`；对象本身是不是 const，决定运行时修改它是不是 UB。`const_cast` 只改变前者。

**const 对象**的定义在 [[basic.type.qualifier]]：类型为 `const T` 的对象，或者这种对象的非 mutable 子对象。mutable 成员不是 const 对象：

```cpp run ub
struct X { mutable int i; int j; };
struct Y { X x; Y() { } };
const Y y;            // 有用户提供的构造函数，可以不写初始化器

int main() {
    y.x.i++;          // OK: mutable 成员
    Y* p = const_cast<Y*>(&y);
    p->x.i = 99;      // OK
    p->x.j = 99;      // UB: y.x.j 是 const 对象的子对象
}
```

把修改 const 对象定为 UB，给了实现两项自由：把 const 对象放进只读存储，以及假设它的值不变、把读取替换成初值。

```cpp run ub
#include <cstdio>
const int limit = 10;
int main() {
    int* p = const_cast<int*>(&limit);
    *p = 20;                        // UB
    std::printf("%d\n", limit);
}
```

本机（Apple Silicon，Clang 23）`-O0` 时程序在写入处因 Bus error 崩溃，因为 `limit` 位于只读段；`-O2` 时打印 `10` 并正常退出，读取被替换成了常量，写入也被删掉了。加上 `-fsanitize=address,undefined` 也不会得到写 const 对象的诊断：UBSan 不检查这类写入，ASan 只报告了随后的 BUS 信号。

!!! note "构造和析构期间"
    ¶4 只管生存期内的修改。const 对象在构造函数和析构函数执行期间还不是、或者已经不再是 const 的（[[class.ctor.general]]、[[class.dtor]]），所以构造函数可以给成员赋值。

### volatile（¶5–¶6）

¶5 经由 volatile glvalue（指代对象的表达式，见 [[basic.lval]]）访问对象，语义由实现定义 {{impl}}。对象定义为 volatile 类型、却经由非 volatile 的 glvalue 访问它，行为未定义 {{ub}}：

```cpp ub
volatile int reg = 0;
int read_wrong() {
    return *const_cast<int*>(&reg);   // UB: 去掉了 volatile
}
```

¶6 是一条注：volatile 提示实现，对象的值可能以实现察觉不到的方式改变，不要做激进的优化；在某些实现上访问它需要特殊的硬件指令。在 C++ 中它的语义意图与 C 相同。

volatile 访问属于可观察行为（[[intro.abstract]]），不能被合并、删除或相互重排，内存映射的硬件寄存器靠的就是这一点。它不提供原子性，也不建立线程间的先后关系。多线程通信要用 `std::atomic`，对普通变量的并发读写即使加了 volatile，仍然是数据竞争（[[intro.races]]）。

C++20 弃用了 volatile 的若干用法，其中复合赋值的弃用后来撤回了。当前草案仍然弃用的是：volatile 对象的自增自减、把对 volatile 对象的赋值结果再拿来用（如 `a = v = b`）、volatile 形参和返回类型，以及 volatile 结构化绑定（[[depr.volatile.type]]）。

## 详述类型说明符 [dcl.type.elab]

```cpp run ok
struct T { int v; };
int main() {
    int T = 0;          // 变量 T 隐藏了类名 T
    struct T obj{T};    // struct T 找到类；{T} 中的 T 是变量
    return obj.v;
}
```

**详述类型说明符**（elaborated-type-specifier）是带上 `class`、`struct`、`union` 或 `enum` 关键字的类型名。前三个关键字统称 *class-key*。它有三个用途：

1. 前向声明：`struct S;`；
2. 在声明中顺带引入一个还没声明过的类名：`struct Node* next;`；
3. 引用被非类型名字隐藏的类名，如上例，又如 POSIX 的 `struct stat st;`（`stat` 同时是函数名）。

¶5 是一条注：查找详述类型说明符中的名字时只考虑类型（[[basic.lookup.elab]]），所以第 3 种用法成立。

### 前向声明（¶2）

¶2 声明如果只由一个详述类型说明符构成，就只能是显式特化、偏特化、显式实例化，或者下面两种形式之一：

```text
class-key attribute-specifier-seq(opt) identifier ;
class-key attribute-specifier-seq(opt) simple-template-id ;
```

第一种把标识符声明为类名，也就是前向声明；第二种只能出现在显式特化或偏特化里。属性属于被声明的类。

```cpp error
struct S;                  // OK: 前向声明
struct [[deprecated]] D;   // OK: 属性属于 D
namespace N { struct Inner; }
struct N::Inner;           // error: 不能带限定名
enum E;                    // error: enum 不是 class-key
enum class F : int;        // OK: 这是不透明枚举声明，不归本节管
```

`struct N::Inner;` 被禁止，是因为带限定名的声明只能重新声明已有的实体：如果 `Inner` 已经存在，这一行没有作用；如果不存在，也不能从外面往 `N` 里添加成员。无作用域枚举的前向声明必须写出底层类型（`enum E : int;`），见 [[dcl.enum]]。

### 顺带声明的类名放在哪里（¶3）

¶3 在其他场合，详述类型说明符不能带属性。如果它只有一个标识符、没有限定，而且对这个标识符的查找什么也没找到，它就把这个标识符声明为类名（这时不能用 `enum`）。新类名的目标作用域是最近的外围命名空间作用域或块作用域：

```cpp run ok
void f(struct Fwd* p);     // 形参作用域被跳过：Fwd 声明在全局
Fwd* r = nullptr;          // OK
struct List { struct Node* head; };   // 类作用域也被跳过
Node* n = nullptr;         // OK: Node 是全局的类，不是 List::Node
int main() {}
```

```cpp error
void g() { struct Q* q; (void)q; }   // Q 声明在 g 的块作用域
Q* bad;                    // error: 全局没有 Q
```

!!! pitfall "与 C 不同"
    在 C 中，`void f(struct Fwd* p);` 里的 `struct Fwd` 只在函数原型作用域可见，之后在文件作用域定义的 `struct Fwd` 是另一个类型，导致 `f` 无法调用。C++ 把它放进外围命名空间，避免了这个问题。另一方面，在类里写 `struct Node* head;` 引入的 `Node` 不是嵌套类；要嵌套类，必须在类里单独写 `struct Node;`。

### 友元声明（¶4）

¶4 在友元声明 `friend class X;` 中，详述类型说明符只能是 class-key 加名字（可以带限定或模板实参），不能带属性，也不能用 `enum`。不带限定的名字查找时不会越过最近的外围命名空间或块作用域；查不到时，这个声明在那个作用域里引入一个类，但不让普通查找找到它的名字，直到出现正式的声明（[[dcl.friend]]）。注 1 补充，目标作用域里指向外部命名空间的 using 指令在这里被忽略。

```cpp run ok
namespace N {
    class X { friend class Helper; int secret = 7; };   // 声明 N::Helper
    class Helper { public: int peek(X& x) { return x.secret; } };   // 同一个类
}
int main() { N::X x; return N::Helper{}.peek(x) - 7; }
```

### 不能指向 typedef 名（¶6）

¶6 如果名字解析为类名或枚举名，详述类型说明符就像简单类型说明符一样引入这个类型；如果解析为 typedef 名（包括别名模板的特化），则非良构。注 3 指出，所以在以类型参数 `T` 为参数的类模板里，`friend class T;` 非良构，`friend T;` 良构（[[class.friend]]）。

```cpp error
struct S { };
typedef S TS;
struct TS* p;          // error: TS 是 typedef 名
template<class T> struct W { friend class T; };   // error
```

### 关键字要和类的种类相符（¶7）

¶7 `enum` 只能指枚举，`union` 只能指联合体，`class` 和 `struct` 只能指非联合体的类，但二者可以互换。

<div class="compare" markdown="1">

```cpp run ok
enum class E { a, b };
enum E x = E::a;  // 不写 class 也行
struct S { } s;
class S* p = &s;  // class、struct 可互换
int main() {}
```

```cpp error
union U { };
struct U* pu;  // error: 要用 union
struct V;
enum V* pv;    // error: V 不是枚举
int main() {}
```

</div>

!!! impl "MSVC 与 class/struct 互换"
    标准允许 `struct S` 和 `class S` 混用，但 MSVC 的名字修饰编码了 class-key（`class` 为 `V`，`struct` 为 `U`）。一个翻译单元声明 `class S`、另一个定义 `struct S`，在 MSVC 上可能导致链接错误。Clang 的 `-Wmismatched-tags` 警告会提醒这一点。Itanium ABI 不编码 class-key。

## 包索引说明符 [dcl.type.pack.index] {{c++26}}

```cpp run ok
#include <type_traits>
template<class... Ts> using First = Ts...[0];
template<class... Ts> using Last  = Ts...[sizeof...(Ts) - 1];
static_assert(std::is_same_v<First<int, char, double>, int>);
static_assert(std::is_same_v<Last<int, char, double>, double>);

template<class... Ts>
auto second(Ts... ts) {
    Ts...[1] x = ts...[1];   // 类型的包索引 + 表达式的包索引
    return x;
}
int main() { return int(second(1, 2.5, 'c')) - 2; }
```

C++23 及以前，取包里的第 N 个类型要借助递归模板或 `std::tuple_element_t<N, std::tuple<Ts...>>`，编译开销都不小。C++26 的**包索引**（[[P2662]]）把它变成了语言内建的操作，写作 `P...[I]`。表达式的包索引 `ts...[1]` 见 [[expr.prim.pack.index]]。

¶1 `P` 必须是一个表示包的标识符。¶2 下标必须是 `std::size_t` 类型的转换常量表达式，它的值 V 叫做**索引**，必须满足 0 ≤ V < `sizeof...(P)`。越界是非良构，在编译期报错：

```cpp error
template<class... Ts> using Bad = Ts...[2];
Bad<int, char> b;      // error: 索引 2 越界
```

¶3 包索引说明符本身算一个包展开（[[temp.variadic]]），所以它可以单独出现，不需要再写 `...`。¶4 的注说明它表示包中第 V 个元素的类型。

!!! lawyer "与 C++23 不兼容的一处语法"
    在 C++23 中，`template<class... T> void f(T... [1]);` 声明的是一个未命名的函数形参包，每个形参的类型是 `T[1]`（再调整为指针）。C++26 把 `T...[1]` 解析为包索引，这样的代码变成非良构。带名字的 `void g(T... ptr[1]);` 不受影响（[[diff.cpp23.dcl.dcl]]）。

## 类型拼接 [dcl.type.splice] {{c++26}}

```text
splice-type-specifier:
    typename(opt) splice-specifier
    typename(opt) splice-specialization-specifier
```

C++26 的静态反射（[[P2996]]）用 `^^T` 得到一个反射值（类型为 `std::meta::info`），用 `[: r :]` 把它拼接回代码里。本节规定拼接出类型的情形。截至写作时本机 Clang 23 还没有实现静态反射，本节的例子取自标准，没有经过编译验证。

```cpp
template<std::meta::info R> void tfn() {
    typename [:R:]::type m;       // OK: typename 作用于整个限定名
}
struct S { using type = int; };
void fn() {
    [:^^S::type:] *var;           // error: 这里 [: :] 是表达式，整行是乘法
    typename [:^^S::type:] *var;  // OK: 声明 int* var
}
using alias = [:^^S::type:];      // OK: 仅类型上下文
```

¶1 给出两条消歧规则。后面紧跟 `::` 的拼接永远不算类型拼接，它是限定名的一部分。不带 `typename` 的拼接，只有在**仅类型上下文**（type-only context，例如别名声明的右侧，见 [[temp.res.general]]）里才被当作类型；在其他地方，`[: r :]` 默认是表达式（[[expr.prim.splice]]）。这与依赖名前的 `typename` 道理相同：解析时还不知道 `r` 反射的是类型还是值。

¶2 `[: r :]` 形式的类型拼接必须指代类型、类模板或别名模板，结果就是这个实体；指代模板时，它就是上文 ¶3.3 的 CTAD 占位符。¶3 `[: r :]<args>` 形式要求 `r` 指代类模板或别名模板，结果是对应这组实参的特化。

<details class="fine" markdown="1"><summary>其余条文</summary>

[dcl.type.general] ¶4 是一条注，指出类定义、枚举定义和 `typename` 说明符分别在 [[class]]、[[dcl.enum]] 和 [[temp.res]] 中讲。

[dcl.type.simple] ¶2 和 [dcl.type.elab] ¶1 定义了**组成名字**（component names）：说明符中出现的限定部分、类型名、模板名等。[[basic.lookup]] 和 [[module.reach]] 等条款用这个概念判断一个声明用到了哪些名字。

[dcl.type.cv] ¶1 的注 1 指出，cv 限定符对对象类型和函数类型的影响分别见 [[basic.type.qualifier]] 和 [[dcl.fct]]。

</details>

## 历史与演进

!!! history
    - C++98 去掉了 C 的隐式 int，并区分了类型说明符和定义类型说明符。
    - C++11 加入 `char16_t`、`char32_t`、`long long`、`decltype` 和作为占位类型的 `auto`。
    - C++17 加入 CTAD 的占位符；C++20 加入 `char8_t`、别名模板 CTAD 和受约束的占位符 `Concept auto`，并弃用了一批 volatile 用法。
    - C++26 加入包索引说明符（[[P2662]]）和类型拼接（[[P2996]]）。

## 常见误解

!!! pitfall "用 `const_cast` 就能修改 const 对象"
    能通过编译，但对象本身是 const 时，运行时修改是 UB。`const_cast` 只在访问路径是 const、对象本身不是 const 时才安全。

!!! pitfall "`char` 就是 `signed char`"
    它们是不同的类型，`char` 的符号性由实现定义；ARM 上的 Linux 通常是无符号的。

!!! pitfall "volatile 可以用于线程同步"
    不能。volatile 不提供原子性和线程间顺序，应该用 `std::atomic`。

## 思考题

!!! question "思考题 1"
    下面哪些是合法的类型？`unsigned`、`signed long long int`、`long signed`、`short unsigned int`、`long double long`、`unsigned signed char`。

<details markdown="1">
<summary>答案</summary>

`unsigned`（即 `unsigned int`）、`signed long long int`（即 `long long`）、`long signed`（即 `long`）、`short unsigned int`（即 `unsigned short`）都合法。`long double long` 不合法：一个 `long` 和 `double` 组合之后，第二个 `long` 没有可以组合的对象，标准也没有 `long long double`。`unsigned signed char` 不合法，`signed` 和 `unsigned` 不能组合（[[dcl.type.general#2]]）。
</details>

!!! question "思考题 2"
    下面的代码中，`N::f` 的参数类型是 `::S*` 还是 `N::S*`？

    ```cpp
    struct S { int x; };
    namespace N {
        void f(struct S* p);
        struct S { double y; };
    }
    ```

<details markdown="1">
<summary>答案</summary>

是 `::S*`。声明 `f` 时，对 `S` 的查找找到了全局的 `::S`，而 [[dcl.type.elab#3]] 只在查找什么也没找到时才声明新类。随后定义的 `N::S` 是另一个类，与 `f` 无关。如果删掉第一行，`struct S` 就会在最近的外围命名空间 `N` 中声明 `N::S`，后面的定义正好定义它，参数类型就是 `N::S*`。
</details>
