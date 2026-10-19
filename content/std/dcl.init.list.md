---
title: 列表初始化
summary: 花括号初始化怎样选择初始化方式：¶3 的十二步判定、initializer-list 构造函数为什么总是优先、backing array 的类型与寿命、窄化转换的完整定义，以及 auto 和 CTAD 遇到花括号时的特殊规则。
status: done
covers: dcl.init.list
papers: N3922, P0138R2, P0329R4, P1957R2, P1467R9, P2752R3
related: dcl.init, dcl.init.aggr, dcl.init.ref, over.match.list, over.ics.list, dcl.spec.auto, over.match.class.deduct, class.temporary, support.initlist, topics/initialization
tags: 初始化, 列表初始化, initializer_list, 窄化
updated: 2026-10-19
---

!!! tldr
    - 花括号初始化按 ¶3 的固定顺序选择做法：聚合走聚合初始化，空列表优先调用默认构造函数，非空列表优先尝试 initializer-list 构造函数，标量走单元素初始化。
    - 只要 initializer-list 构造函数可行就会胜出，所以 `std::vector<int>{10, 20}` 是两个元素，`std::vector<int>(10, 20)` 是十个 20。
    - 窄化转换（如 `double` → `int`、非常量的 `int` → `char`、指针 → `bool`）在列表初始化的顶层是编译错误；它不会让候选函数不可行，而是在选中后报错。
    - `std::initializer_list` 指向一个 `const E[N]` 的 backing array，寿命和绑定到引用的临时对象一样；不要存储或返回它。
    - 花括号里的各子句严格从左到右求值；`auto x{1}` 推导为 `int`，`auto x = {1}` 推导为 `std::initializer_list<int>`。

## 同样的花括号，不同的做法

```cpp run ok
#include <vector>
#include <cstdio>
struct P { int x, y; };
int main() {
  std::vector<int> a{10, 20};   // 2 个元素：10, 20
  std::vector<int> b(10, 20);   // 10 个元素，每个都是 20
  P p{1, 2};                    // 聚合初始化
  int i{};                      // 值初始化：0
  std::printf("%zu %zu %d %d\n", a.size(), b.size(), p.y, i);   // 2 10 2 0
}
```

C++11 的花括号初始化想做到到处可用，并且禁止窄化、避免把对象定义误解析成函数声明。但同一对花括号对聚合、对有 `std::initializer_list` 构造函数的类、对标量，做的是完全不同的事。¶3 的判定顺序决定了每种情况走哪条路。[[dcl.init]] 遇到花括号初始化器时，¶15.1 直接把控制权交给这里。

## 术语（¶1）

¶1 从花括号列表（*braced-init-list*）初始化对象或引用，叫做**列表初始化**（list-initialization）。这样的初始化器叫**初始化器列表**（initializer list），其中逗号分隔的各子句（或指派子句）叫做它的**元素**。列表可以为空。

列表初始化可以出现在直接初始化或拷贝初始化的语境中（[[dcl.init#13]]、[[dcl.init#14]]）：

| 名称 | 例子 |
|---|---|
| **直接列表初始化**（direct-list-initialization） | `T x{a};`、`new T{a}`、`T{a}`、`: m{a}` |
| **拷贝列表初始化**（copy-list-initialization） | `T x = {a};`、`f({a})`、`return {a};`、聚合元素中的 `{a}` |
| **直接非列表初始化**（direct-non-list-initialization） | 不是列表初始化的直接初始化：`T x(a);` |

注 1 列出了列表初始化能出现的位置：变量初始化器、*new-expression*、`return`、范围 `for` 的初始化器、函数实参、模板实参、下标 `a[{1, 2}]`、构造函数调用的实参、默认成员初始化器、*mem-initializer*，以及赋值运算符右侧。

```cpp
int a = {1};
std::complex<double> z{1, 2};
new std::vector<std::string>{"once", "upon", "a", "time"};  // 4 个 string
f({"Nicholas", "Annemarie"});         // 传递一个两元素的列表
return {"Norah"};                     // 返回一个单元素的列表
int* e{};                             // 空指针
x = double{1};                        // 显式构造一个 double
std::map<std::string, int> anim = {{"bear", 4}, {"cassowary", 2}, {"tiger", 7}};
```

## initializer-list 构造函数（¶2）

¶2 如果构造函数的第一个形参是 `std::initializer_list<E>` 或 `cv std::initializer_list<E>&`，而且其余形参（如果有）都有默认实参，它就是 **initializer-list 构造函数**（[[g:initializer-list-constructor]]）。注 2 指出，列表初始化会优先考虑这类构造函数（[[over.match.list]]）。

构造函数模板 `template<class T> C(T)` 不是 initializer-list 构造函数：花括号列表实参让对应的形参成为不推导语境（[[temp.deduct.call]]），`T` 不会被推导成 `initializer_list<...>`。

`std::initializer_list` 不是语言内建的类型。在用到它的地方，即使是 `auto x = {1, 2};` 这种不写出类型名的隐式使用，如果 `<initializer_list>` 中的声明（或 `import std;` 提供的声明）不可达，程序非良构。

## 判定顺序（¶3）

¶3 对 *cv* `T` 类型的对象或引用做列表初始化时，按下表顺序检查，第一个满足的条件决定做法：

| 步骤 | 条件 | 做法 |
|---|---|---|
| ¶3.1 | 有指派初始化器，`T` 不是引用 | `T` 必须是聚合类；聚合初始化 |
| ¶3.2 | `T` 是聚合类，列表只有一个元素，类型是 `T` 或其派生类 | 从该元素初始化（复制或移动） |
| ¶3.3 | `T` 是字符数组，列表只有一个字符串字面量 | 按 [[dcl.init.string]] 初始化 |
| ¶3.4 | `T` 是聚合 | 聚合初始化（[[dcl.init.aggr]]） |
| ¶3.5 | 列表为空，`T` 是有默认构造函数的类 | 值初始化 |
| ¶3.6 | `T` 是 `std::initializer_list<E>` | 构造 backing array（¶5） |
| ¶3.7 | `T` 是类 | 构造函数重载决议（[[over.match.list]]）；窄化则非良构 |
| ¶3.8 | `T` 是有固定底层类型的枚举，单个标量元素，直接列表初始化 | `T(v)`；窄化则非良构 |
| ¶3.9 | 单个元素，`T` 不是引用，或者被引用类型与元素类型引用相关 | 从该元素初始化；窄化则非良构 |
| ¶3.10 | `T` 是引用 | 生成一个纯右值，再用它初始化引用 |
| ¶3.11 | 列表为空 | 值初始化 |
| ¶3.12 | 其他 | 非良构 |

顺序本身就是规则。¶3.4 在 ¶3.7 之前，所以聚合从不走构造函数重载决议；¶3.5 在 ¶3.7 之前，所以 `T{}` 调用默认构造函数，而不是用空列表调用 initializer-list 构造函数；¶3.9 在 ¶3.7 之后，所以类类型的单元素列表也先找构造函数。

### 指派初始化器（¶3.1）{{c++20}}

```cpp error
struct A { int x; int y; int z; };
A a{.y = 2, .x = 1};   // error: 顺序与声明顺序不一致
A b{.x = 1, .z = 2};   // OK：b.y 初始化为 0
```

¶3.1 花括号列表含有指派初始化器（*designated-initializer-list*）且 `T` 不是引用时，`T` 必须是聚合类；各指派符所指成员的关联元素（[[dcl.init.aggr#3]]）在元素顺序上必须不递减；然后做聚合初始化。本机 Clang 23 对 `a` 只给出 `-Wreorder-init-list` 警告（这是从 C 继承的扩展），按标准它是非良构的，警告满足了诊断要求。

当前草案还允许指派基类的成员 {{c++29}}，这是 C++26 之后的修改（[[diff.cpp26]] 记录了它带来的一处不兼容）。要求不递减而不是严格递增，正是因为多个指派符可以对应同一个关联元素：下例中 `.x` 和 `.y` 都属于基类 `A`。

```cpp
struct B : A { int q; };
B e{.x = 1, .q = 3};   // OK：e.y、e.z 为 0
B f{.q = 3, .x = 1};   // error: 顺序

struct C { int p; int x; };
struct D : A, C { };
D g{.y = 1, .p = 2};   // OK
D h{.x = 2};           // error: x 的查找有歧义

struct NonAggr { int na; NonAggr(int); };
struct E : NonAggr { int e; };
E i{.na = 1, .e = 2};  // error: na 属于 NonAggr，它不是 E 的聚合基类
```

截至写作时，本机 Clang 23 还不支持指派基类成员，这段代码按草案原文分析。指派初始化器的其他限制（不能嵌套 `.a.b`、不能用于数组、不能与普通子句混用）见 [[dcl.init.aggr]]。

### 聚合：同类型拷贝、字符串、聚合初始化（¶3.2–¶3.4）

```cpp run ok
struct S { int x; };
struct D : S { int y; };
int main() {
  S a{1};
  S b{a};          // ¶3.2：复制，b.x == 1
  D d{{1}, 2};
  S c{d};          // ¶3.2：从派生类复制（切片）
  char s[] = {"abc"};   // ¶3.3：与 char s[] = "abc"; 相同
  (void)b; (void)c; (void)s;
}
```

¶3.2 `T` 是聚合类，列表只有一个元素，元素类型是 *cv1* `U`，`U` 是 `T` 或其派生类：直接用这个元素初始化对象。拷贝列表初始化时是拷贝初始化，直接列表初始化时是直接初始化。

没有这一步，`S b{a};` 会走聚合初始化，用 `a` 去初始化 `b.x`，而 `S` 到 `int` 没有转换。C++11 最初的规则确实有这个问题，后来通过一个核心问题的解决加入了 ¶3.2。

¶3.3 `T` 是字符数组，列表只有一个类型合适的字符串字面量：按 [[dcl.init.string]] 初始化。没有这一步，¶3.4 会把 `"abc"` 当作第一个 `char` 元素的初始化器。

¶3.4 `T` 是聚合（数组或聚合类）：做聚合初始化（[[dcl.init.aggr]]）。元素的初始化器本身是花括号列表时，该元素递归地列表初始化。聚合元素上的窄化同样是错误：

```cpp error
double ad[] = { 1, 2.0 };     // OK
int ai[] = { 1, 2.0 };        // error: 窄化

struct S2 { int m1; double m2, m3; };
S2 s21 = { 1, 2, 3.0 };       // OK
S2 s22 { 1.0, 2, 3 };         // error: 窄化
S2 s23 { };                   // OK：全部为 0
```

!!! lawyer "聚合元素窄化的出处"
    C++23 的 [dcl.init.aggr] 明文规定，元素的初始化器是表达式且需要窄化转换时程序非良构。当前草案把聚合初始化改写为子句归属（appertain）的模型后，[[dcl.init.aggr#5.3]] 里找不到这句话，只剩 [[dcl.init.aggr#5.2.1]] 针对指派初始化器的那一句。标准自己的例 3 和所有实现仍把 `ai`、`s22` 视为非良构，没有迹象表明意图有变。

### 空列表调用默认构造函数（¶3.5）

```cpp run ok
#include <initializer_list>
#include <cstdio>
struct U {
  U(std::initializer_list<int>) { std::puts("#1"); }
  U() { std::puts("#2"); }
};
int main() {
  U u1{};      // ¶3.5：#2
  U u2{{}};    // ¶3.7：#1，列表有一个元素（值为 0 的 int）
  U u3({});    // 非列表初始化：#1，空的 initializer_list
}
```

¶3.5 列表为空，`T` 是有默认构造函数的类：值初始化（[[dcl.init#8]]）。这挡住了 initializer-list 构造函数对 `T{}` 的抢占。

`u3` 不是列表初始化，而是以 `{}` 为实参的普通构造函数重载决议。`{}` 到 `initializer_list<int>` 是恒等转换，到 `U` 的拷贝或移动构造函数需要用户定义转换，所以选中 #1。

### `std::initializer_list` 本身（¶3.6）

¶3.6 `T` 是 `std::initializer_list<E>` 的特化：按 ¶5 构造 backing array，例如 `std::initializer_list<int> il = {1, 2, 3};`，或者 initializer-list 构造函数的实参。

### 构造函数：两阶段重载决议（¶3.7）

¶3.7 `T` 是类类型（不是聚合，并且列表非空或没有默认构造函数）：按 [[over.match.list]] 做构造函数重载决议。如果有实参需要窄化转换，程序非良构。[[over.match.list]] 分两个阶段：

1. 列表非空或 `T` 没有默认构造函数时，候选只有 initializer-list 构造函数，整个列表作为唯一的实参。
2. 第一阶段没有可行函数时，候选是全部构造函数，列表的各元素分别作为实参。

```cpp error
#include <vector>
#include <string>
std::vector<int> v1{10, 20};       // 第一阶段可行：2 个元素
std::vector<int> v2(10, 20);       // 非列表：10 个 20
std::vector<std::string> v3{3};    // int → string 不可行，第二阶段：3 个空串
std::vector<int> v4{3.0};          // error: 第一阶段选中，然后发现窄化
```

`v4` 最违反直觉。窄化不会让转换不可行（[[over.ics.list]]），只会在选中之后让程序非良构，所以不会回退到 `vector(size_type)`。这是有意的设计：如果窄化只是让候选不可行，`v4` 就会悄悄选中一个含义完全不同的构造函数。

只要 initializer-list 构造函数可行，就连拷贝构造函数也会被它挡住。标准例 4：

```cpp
struct S {
  S(std::initializer_list<double>);   // #1
  S(std::initializer_list<int>);      // #2
  S(std::initializer_list<S>);        // #3
  S();                                // #4
};
S s1 = { 1.0, 2.0, 3.0 };             // #1
S s2 = { 1, 2, 3 };                   // #2
S s3{s2};                             // #3，不是拷贝构造函数
S s4 = { };                           // #4（¶3.5）
```

`S` 不是聚合，¶3.2 不适用；第一阶段中，用 `s2` 拷贝初始化一个 `S` 元素来构造 `initializer_list<S>` 是可行的，于是选中 #3。所以给类添加一个 `initializer_list<T>` 构造函数，如果 `T` 能从这个类转换而来，就会改变所有 `X{x}` 形式的复制。

没有 initializer-list 构造函数时，¶3.7 就是普通的构造函数重载决议加上窄化检查。拷贝列表初始化还有一条特别之处：

```cpp error
struct S { explicit S(int); S(long); };
S s1 = {1};     // error: 选中了 explicit S(int)
S s2 = 1;       // OK：拷贝初始化不考虑 explicit，选 S(long)
S s3{1};        // OK：直接列表初始化
```

在[[g:copy-list-initialization|拷贝列表初始化]]中，explicit 构造函数参与重载决议，一旦被选中程序就非良构（[[over.match.list]]）；普通拷贝初始化则根本不考虑它们。这样，给构造函数加上 `explicit` 不会让 `= {...}` 悄悄改选另一个重载。

### 有固定底层类型的枚举（¶3.8）{{c++17}}

```cpp error
#include <cstdint>
enum byte : unsigned char { };
byte b { 42 };              // OK
byte c = { 42 };            // error: 拷贝列表初始化
byte d = byte{ 42 };        // OK：与 b 同值
byte e { -1 };              // error: 窄化

struct A { byte b; };
A a1 = { { 42 } };          // error: 聚合元素是拷贝初始化
A a2 = { byte{ 42 } };      // OK

void f(byte);
void g() { f({ 42 }); }     // error: 实参传递是拷贝初始化

enum class Handle : std::uint32_t { Invalid = 0 };
Handle h { 42 };            // OK
```

¶3.8 `T` 是有固定底层类型 `U` 的枚举（`enum class E` 或 `enum E : U`），列表只有一个能隐式转换为 `U` 的标量元素 `v`，并且是直接列表初始化：对象的值为 `T(v)`。`v` 到 `U` 需要窄化时程序非良构。

[[P0138R2]] 加入这条规则，让 `std::byte` 这类强类型整数可以写成 `byte b{42};`，不必 `static_cast`。整数到枚举本来没有隐式转换，只允许直接列表初始化，就保证了 `f({42})`、`return {42};` 这类隐式场合仍然不能把整数变成枚举。

### 单元素（¶3.9）

```cpp error
int x1 {2};          // OK
int x2 {2.0};        // error: 窄化
int i = 0;
int& r {i};          // 被引用类型 int 与 int 引用相关：绑定到 i
const long& rl {i};  // 不引用相关：交给 ¶3.10
```

¶3.9 列表不是指派列表，只有一个类型为 `E` 的元素，并且 `T` 不是引用，或者其被引用类型与 `E` [[g:reference-related|引用相关]]：从这个元素初始化（拷贝或直接，按语境）；需要窄化时非良构。这是标量最常走的一步。对引用要求引用相关，保证了 `int& r{i};` 真的绑定到 `i`。

### 引用（¶3.10）

```cpp
struct S {
  S(std::initializer_list<double>);   // #1
  S(const std::string&);              // #2
};
const S& r1 = { 1, 2, 3.0 };          // OK：#1
const S& r2 { "Spinach" };            // OK：#2
S& r3 = { 1, 2, 3 };                  // error: 纯右值不能绑定到非 const 左值引用
const int& i1 = { 1 };                // OK（¶3.9）
const int& i2 = { 1.1 };              // error: 窄化
const int (&iar)[2] = { 1, 2 };       // OK：绑定到临时数组
const int (&iau)[] = { 1, 2, 3 };     // OK：临时数组类型为 const int[3]

struct A { } a;
struct B { explicit B(const A&); };
const B& b2{a};                       // error: 不能从 A 拷贝列表初始化 B 临时对象

struct C { int x; };
C&& c = { .x = 1 };                   // OK
```

¶3.10 `T` 是引用（且 ¶3.9 不适用）：生成一个纯右值，它的结果对象从列表拷贝列表初始化，再用这个纯右值直接初始化引用（[[dcl.init.ref]]）。纯右值的类型是被引用类型；如果 `T` 是“`U` 的未知边界数组的引用”，纯右值的类型就是声明 `U x[] H`（`H` 是这个列表）中 `x` 的类型，也就是从列表推出边界。

`const B& b2{a};` 整体是直接列表初始化，但 ¶3.10 生成的纯右值是拷贝列表初始化的，所以不能用 explicit 构造函数。

!!! impl
    本机 Clang 23 接受 `const B& b2{a};`，只对 `const B& b3 = {a};` 报 chosen constructor is explicit in copy-initialization。按标准两者都非良构。

### 空列表与其余情形（¶3.11–¶3.12）

¶3.11 列表为空：值初始化。类类型已在前面处理完，走到这里的是标量等非类类型：`int** pp{};` 是空指针，`int k{};` 是 0。

¶3.12 其余情形非良构，例如 `int x{1, 2};`。

## 花括号保证从左到右求值（¶4）

```cpp run ok
#include <iostream>
struct I { I(int x) { std::cout << x; } };
struct S { S(I, I = 2) {} };
int main() {
  S(1, 2); std::cout << '\n';   // 顺序未指定：打印 12 或 21
  S{1, 2}; std::cout << '\n';   // 一定打印 12
  S{1};                         // 一定打印 12：默认实参按其位置求值
}
```

¶4 花括号列表中的各子句，包括包展开产生的子句，按出现的顺序求值：前一个子句的所有值计算和副作用都先于后一个。如果这些子句被当作构造函数的实参，用到的默认实参也按它们本应所在的位置依次求值。

注 4 强调，这个顺序与初始化的语义无关。即使元素最终是构造函数的实参（普通函数调用的实参之间没有顺序），花括号也保证从左到右。所以 `T{f(), g()}` 是少数几种能保证求值顺序的写法，C++17 之前常用 `(void)std::initializer_list<int>{(process(args), 0)...};` 给包展开中的副作用排序。

## `std::initializer_list` 与 backing array（¶5–¶6）

¶5 从初始化器列表构造 `std::initializer_list<E>` 对象时，如同实现生成并实质化了一个“`N` 个 `const E` 的数组”类型的纯右值，`N` 是元素个数。这个数组叫做 **backing array**。数组的每个元素从列表的对应元素拷贝初始化，`initializer_list` 对象指向这个数组。由此有三个推论：

1. 元素是 `const` 的，不能从中移走。`std::vector<std::unique_ptr<int>> v{std::make_unique<int>(1)};` 非良构：`vector` 的 initializer-list 构造函数只能复制元素，而 `unique_ptr` 不可复制。
2. 元素是拷贝初始化的，不能用 explicit 构造函数；选中的构造函数或转换函数要在列表所在的语境中可访问（注 5）。
3. 需要窄化时程序非良构。

注 6 {{c++26}} 说明 backing array 是**潜在非唯一对象**（potentially non-unique object，[[intro.object]]），和字符串字面量一样。这来自 [[P2752R3]]：元素都是常量时，实现可以把数组放进静态只读存储，并与内容相同的其他数组共享，不必每次在栈上构造。C++23 及以前，每次求值都必须得到一个不同的数组对象，这妨碍了上述优化。

¶6 backing array 的寿命和其他临时对象相同（[[class.temporary]]），只是用它初始化 `initializer_list` 对象时，数组的寿命会像引用绑定临时对象那样被延长。标准例 13：

```cpp
void f(std::initializer_list<double> il);
void g(float x) { f({1, x, 3}); }
void h() { f({1, 2, 3}); }

struct A { mutable int i; };
void q(std::initializer_list<A>);
void r() { q({A{1}, A{2}, A{3}}); }
```

实现大致相当于：

```cpp
void g(float x) {
  const double __a[3] = {double{1}, double{x}, double{3}};             // backing array
  f(std::initializer_list<double>(__a, __a + 3));
}
void h() {
  static constexpr double __b[3] = {double{1}, double{2}, double{3}};  // 可以是静态的
  f(std::initializer_list<double>(__b, __b + 3));
}
void r() {
  const A __c[3] = {A{1}, A{2}, A{3}};   // 有 mutable 成员，不能放进只读存储
  q(std::initializer_list<A>(__c, __c + 3));
}
```

这里假设实现能用一对指针构造 `initializer_list`。即使 `__b` 是静态的，按标准它的寿命也不超过对 `f` 的调用。

标准例 14 展示了几种寿命：

```cpp
std::vector<std::complex<double>> v1 = { 1, 2, 3 };  // initializer_list 是函数实参：数组活到完整表达式结束
void f() {
  std::initializer_list<int> i3 = { 1, 2, 3 };      // initializer_list 是变量：数组与 i3 同寿命
}
struct A {
  std::initializer_list<int> i4;
  A() : i4{ 1, 2, 3 } {}   // error: 相当于把临时数组绑定到引用成员
};
```

返回 `initializer_list` 不会被诊断为非良构，但一定悬垂：

```cpp run ub
#include <initializer_list>
#include <cstdio>
std::initializer_list<int> make(int n) {
  return {n, n + 1, n + 2};     // backing array 在 return 语句结束时销毁
}
int main(int argc, char**) {
  auto il = make(argc);
  std::printf("%d\n", *il.begin());   // UB：读取已销毁的数组
}
```

本机 Clang 23 对 `return` 给出 `-Wreturn-stack-address` 警告；用 `-fsanitize=address` 编译并设置 `ASAN_OPTIONS=detect_stack_use_after_return=1` 运行，会报告 stack-use-after-return。如果元素都是常量（`return {1, 2, 3};`），Clang 会把数组放进静态存储，程序看起来正常，但按标准仍然是 UB。

`initializer_list` 本身没有引用成员（通常是一个指针加一个长度），所以 [[stmt.return#6]] 关于组成引用绑定临时对象的规则管不到它。把它看成指向临时数组的视图，像 `std::string_view` 一样，不要存储，也不要返回。

## 窄化转换（¶7）

```cpp error
int x = 999;          // 不是常量表达式
const int y = 999;
const int z = 99;
char c1 = x;          // OK：不是列表初始化（尽管确实窄化了）
char c2{x};           // error: 可能窄化
char c3{y};           // error: 窄化（设 char 为 8 位）
char c4{z};           // OK：常量 99 放得下
unsigned char uc1 = {5};    // OK
unsigned char uc2 = {-1};   // error
unsigned int ui1 = {-1};    // error
signed int si1 = { (unsigned int)-1 };   // error
int ii = {2.0};       // error: 浮点到整数没有常量例外
float f1 { x };       // error: 可能窄化
float f2 { 7 };       // OK：7 能被 float 精确表示
bool b = {"meow"};    // error: 指针到 bool
int f(int);
int a[] = { 2, f(2), f(2.0) };   // OK：double → int 不在顶层
```

¶7 **窄化转换**（[[g:narrowing-conversion|narrowing conversion]]）是以下几种隐式转换：

| 段 | 从 | 到 | 不算窄化的例外 |
|---|---|---|---|
| ¶7.1 | 浮点 | 整数 | 无，即使是常量 `2.0` |
| ¶7.2 | 浮点 `T` | 浮点转换等级既不高于也不等于 `T` 的浮点类型 | 结果是常量表达式，并且值有限、未溢出，或者转换前后都不是有限值 |
| ¶7.3 | 整数或无作用域枚举 | 浮点 | 源是常量表达式，转换后的值放得下，并且转换回去得到原值 |
| ¶7.4 | 整数或无作用域枚举 | 不能表示源类型所有值的整数类型 | ¶7.4.1 源是宽度 w 小于其类型宽度的位域，目标能表示 w 位同符号整数的所有值；¶7.4.2 源是常量表达式，值（整型提升后）放得下 |
| ¶7.5 | 指针或成员指针 | `bool` | 无 |

注 7 指出，这些转换只在列表初始化的顶层被禁止，嵌套在其他表达式里的不受影响，例如上例中 `f(2.0)` 里的 `double` → `int`。

```cpp error
double d = 0.1;
float f1{d};                // error: 不是常量
float f2{0.1};              // OK：常量且有限，不精确也可以
float f3{1e300};            // error: 溢出
long double ld{d};          // OK：等级更高
float f5{16777217};         // error: 2²⁴+1 不能往返
float f6{16777216};         // OK
struct BF { unsigned v : 4; } bf;
unsigned char uc{bf.v};     // OK：¶7.4.1
bool b1{1};                 // OK：常量 1 放得下
bool b2{2};                 // error
int* p = nullptr;
bool b3{p};                 // error: ¶7.5
```

每条例外都有它的道理：

- ¶7.1 浮点到整数没有常量例外。写 `int i{2.0}` 几乎总是类型写错了。
- ¶7.2 浮点降级的常量例外允许不精确：否则 `float f{0.1};` 都写不了，因为 `0.1` 不能用 `float` 精确表示。只要求值有限且未溢出，所以 `float f{1e300};` 非良构；无穷和 NaN 之间可以转换。C++23 起改用**浮点转换等级**（[[conv.rank]]）描述，以纳入扩展浮点类型（[[P1467R9]]）：`std::float16_t` 与 `std::bfloat16_t` 的等级互不可比，二者之间双向都是窄化。
- ¶7.3 整数到浮点要求能精确往返，所以 `float f{16777217};` 非良构，`float f{16777216};` 合法。
- ¶7.4.1 `unsigned v : 4` 的值总在 0–15 之间，用它初始化 `unsigned char` 不会丢失信息，所以即使 `v` 不是常量也不算窄化。这是通过缺陷报告加入的较新规则。
- ¶7.5 指针到 `bool` 由 [[P1957R2]] 加入（C++20，作为缺陷报告）。此前 `std::variant<bool, std::string> v = "abc";` 会选中 `bool`，因为 `const char*` → `bool` 是标准转换，优于到 `std::string` 的用户定义转换。`variant` 的转换构造函数用能否无窄化地列表初始化来筛选备选类型，把指针到 `bool` 算作窄化就修复了这个问题。

## `auto` 与花括号

```cpp error
#include <initializer_list>
auto x1 = { 1, 2 };         // std::initializer_list<int>
auto x2 = { 1, 2.0 };       // error: 无法推导元素类型
auto x3{ 1, 2 };            // error: 直接列表初始化只能有一个元素
auto x4 = { 3 };            // std::initializer_list<int>
auto x5{ 3 };               // int
decltype(auto) x6 = { 1, 2 };   // error: { 1, 2 } 不是表达式
```

[[dcl.spec.auto]] 对花括号初始化器有专门的推导规则。`x4` 与 `x5` 的不同来自 [[N3922]]：C++11/14 最初的规则中 `auto x5{3};` 也推导为 `initializer_list<int>`，这被普遍认为是设计错误。N3922 在 C++17 中把直接列表初始化改为推导出元素类型，主流编译器把它当作缺陷修复，用于 C++11 以后的所有模式。

从花括号列表推导出 `initializer_list` 是 `auto` 的特例，函数模板实参推导和返回类型推导都不会这样做：

```cpp error
#include <initializer_list>
template<class T> void f(T);
template<class T> void g(std::initializer_list<T>);
void test() {
  f({1, 2});      // error: 花括号列表让 T 处于不推导语境
  g({1, 2});      // OK：T = int
}
auto lam = [] { return {1, 2}; };   // error: 不能从花括号列表推导返回类型
```

## 类模板实参推导与花括号

```cpp run ok
#include <vector>
#include <type_traits>
std::vector v{1, 2, 3};          // vector<int>
std::vector v2{v};               // vector<int>：复制
std::vector v3{v, v};            // vector<vector<int>>
static_assert(std::is_same_v<decltype(v2), std::vector<int>>);
static_assert(std::is_same_v<decltype(v3), std::vector<std::vector<int>>>);
int main() {}
```

`v2` 与 `v3` 的不一致常让人困惑。[[over.match.class.deduct#6]] 规定，类模板实参推导（CTAD）时，如果列表只有一个表达式，而它的类型是被推导模板的特化或其派生类，就跳过 [[over.match.list]] 的第一阶段（initializer-list 构造函数），于是复制推导候选胜出。

这与 ¶3.7 中 `S s3{s2}` 选中 `initializer_list<S>` 构造函数恰好相反：CTAD 这一步优先复制，推导完类型之后选择构造函数仍按 ¶3.7 进行。

## 实现视角

!!! impl
    - `std::initializer_list` 的布局：libc++ 与 libstdc++ 是指针加长度，MSVC STL 是首尾两个指针。编译器通过私有构造函数直接构造它，所以它必须来自标准库头文件。
    - backing array 的存放：元素全为常量时，编译器早就会把数组放进只读数据段，这在地址不可观察时是 as-if 规则允许的；[[P2752R3]] 让这一优化在地址可被观察时也合法。
    - Clang 的窄化诊断属于 `-Wc++11-narrowing` 组，C++11 及以后的模式下默认是错误，诊断形如 type 'double' cannot be narrowed to 'int' in initializer list。

## 历史与演进

!!! history
    - C++11：列表初始化、`std::initializer_list` 与窄化转换。
    - C++14：放宽聚合初始化中的花括号省略；有默认成员初始化器的类也可以是聚合（[[dcl.init.aggr]]）。
    - C++17：[[N3922]] 让 `auto x{1}` 推导为 `int`；[[P0138R2]] 允许有固定底层类型的枚举从整数直接列表初始化；¶3.2 等缺陷修复。
    - C++20：[[P0329R4]] 指派初始化器；[[P1957R2]] 指针到 `bool` 算作窄化；未知边界数组的引用可以从列表推出边界。
    - C++23：[[P1467R9]] 扩展浮点类型，窄化规则改用浮点转换等级。
    - C++26：[[P2752R3]] 允许 backing array 放在静态存储中并共享。
    - C++26 之后：允许指派基类的成员。

## 常见误解

!!! pitfall "`vector<int>{n, v}` 等于 `vector<int>(n, v)`"
    对有 initializer-list 构造函数的类型，非空的花括号几乎总是选中它。需要接受大小和值的构造函数时，用圆括号。

!!! pitfall "两层花括号的 `vector<string>`"
    `std::vector<std::string> v{{"a", "b"}};` 的外层花括号对应 `initializer_list<string>`，内层 `{"a", "b"}` 只初始化一个 `string`，调用的是迭代器区间构造函数 `string(const char*, const char*)`。两个指针指向不同的字面量，行为未定义。正确的写法是 `{"a", "b"}`。

!!! pitfall "窄化只是让候选不可行"
    窄化是错误，不是不匹配。`std::vector<int> v{3.0};` 不会回退到 `vector(size_type)`。泛型代码中 `T{args...}` 可能因窄化失败，而 `T(args...)` 能成功。

!!! pitfall "从 `initializer_list` 移动元素"
    backing array 的元素是 const 的，`std::vector<std::unique_ptr<T>> v{std::make_unique<T>()};` 非良构。可以改用 `reserve` 加 `emplace_back`，或者从数组、范围构造。

!!! pitfall "把 `initializer_list` 当容器保存"
    它只是指向临时 backing array 的视图，作为数据成员或返回值都会悬垂。作为数据成员在 *mem-initializer* 中初始化时有诊断，返回它时只有警告。

## 思考题

!!! question "思考题 1"
    下面各行调用哪个构造函数？
    ```cpp
    struct X {
      X(int, int);                             // #1
      X(std::initializer_list<long>);          // #2
      explicit X(std::initializer_list<int>);  // #3
    };
    X a{1, 2};
    X b = {1, 2};
    X c(1, 2);
    ```

<details markdown="1">
<summary>答案</summary>

- `a`：直接列表初始化。第一阶段的候选是 #2、#3。`{1, 2}` 到 `initializer_list<int>` 是恒等转换，到 `initializer_list<long>` 需要整数转换，#3 更好。直接初始化允许 explicit，选中 #3。
- `b`：拷贝列表初始化。第一阶段同样选中 #3，explicit 构造函数参与重载决议，选中后程序非良构，不会退回 #2。
- `c`：不是列表初始化，普通重载决议只有 #1 可行。
</details>

!!! question "思考题 2"
    `struct S { int x; }; S s{S{1}};` 走 ¶3 的哪一步？如果给 `S` 加上构造函数 `S(std::initializer_list<S>)` 呢？

<details markdown="1">
<summary>答案</summary>

`S` 是聚合，列表只有一个元素，类型是 `S`，走 ¶3.2：用 `S{1}` 直接初始化 `s`。按 [[dcl.init#15.6.1]]，同类型的纯右值直接成为 `s`，没有复制。

加上这个构造函数后，`S` 有用户声明的构造函数，不再是聚合，¶3.2 和 ¶3.4 都不适用。先看内层的 `S{1}`：它走 ¶3.7，第一阶段要从 `1` 初始化一个 `S` 元素，但 `S` 没有接受 `int` 的构造函数，不可行；第二阶段也没有可行的构造函数。所以 `S{1}` 非良构，整个声明也就非良构。
</details>

!!! question "思考题 3"
    为什么 ¶3.8 只允许直接列表初始化，而 ¶3.9 对标量同时允许直接和拷贝列表初始化？

<details markdown="1">
<summary>答案</summary>

¶3.9 处理的是本来就允许隐式转换的情形，例如 `int` → `long`。花括号只是额外加了窄化检查，`long l = {1};` 与 `long l = 1;` 含义相同，没有理由禁止。

¶3.8 处理的是本来不允许隐式转换的情形：整数到枚举没有隐式转换，花括号在这里新增了一种转换能力。如果允许拷贝列表初始化，`f({42})`、`return {42};`、聚合成员 `{42}` 都会悄悄地把整数变成枚举，违背强类型枚举的初衷。只允许直接列表初始化，就要求在初始化处写出类型：`byte b{42}` 或 `byte{42}`。
</details>
