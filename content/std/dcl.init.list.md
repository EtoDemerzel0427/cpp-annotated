---
title: 列表初始化
summary: 一切花括号初始化的入口：¶3 的十二步决策流程、initializer_list 构造函数的"劫持"、backing array 的语义与寿命、窄化转换的完整定义，以及 auto 与 CTAD 遇到花括号时的特殊规则
status: draft
covers: dcl.init.list
papers: N3922, P0138R2, P0329R4, P1957R2, P1467R9, P2752R3
related: dcl.init, dcl.init.aggr, dcl.init.ref, over.match.list, over.ics.list, dcl.spec.auto, over.match.class.deduct, class.temporary, support.initlist, topics/initialization
tags: 初始化, 列表初始化, initializer_list, 窄化
updated: 2026-10-17
---

C++11 引入花括号初始化时，给它起了个雄心勃勃的名字：**统一初始化**（uniform initialization）。它承诺了四点：

1. 到处可用：变量、`new`、返回值、实参、成员初始化器、临时对象，都能用 `{…}`；
2. 没有最令人烦恼的解析：`T x{};` 永远是对象；
3. 禁止窄化：`int x{2.5};` 是编译错误；
4. 容器字面量：`std::vector<int> v{1, 2, 3};` 通过 `std::initializer_list` 实现。

前三点基本兑现了，第四点却和第一点相冲突。对于有 `initializer_list` 构造函数的类，这种统一的语法会被 `initializer_list` 构造函数抢先接管，`std::vector<int>{10, 20}` 与 `std::vector<int>(10, 20)` 的含义完全不同。理解这一切的关键是本节 ¶3 的**决策流程**。它与 [[dcl.init]] ¶15 是平行的两套流程：初始化器是花括号列表时，¶15.1 直接把控制权交给这里。

## 术语（¶1）

¶1 **列表初始化**（list-initialization）是从 *braced-init-list* 初始化对象或引用。这样的初始化器称为**初始化器列表**（initializer list），其中逗号分隔的子句（或指派子句）称为初始化器列表的元素。初始化器列表可以为空。

列表初始化可以出现在直接初始化或拷贝初始化的上下文中（[[dcl.init]] ¶13–¶14）：

| 名称 | 例子 |
|---|---|
| 直接列表初始化（direct-list-initialization） | `T x{a};`、`new T{a}`、`T{a}`、`: m{a}` |
| 拷贝列表初始化（copy-list-initialization） | `T x = {a};`、`f({a})`、`return {a};`、聚合元素 `{…, {a}}` |
| 直接非列表初始化（direct-non-list-initialization） | 不是列表初始化的直接初始化：`T x(a);` |

注 1 列出了列表初始化能出现的所有位置：变量初始化器、*new-expression*、`return`、范围 for 的初始化器、函数实参、模板实参、下标（`a[{1, 2}]`，调用重载的 `operator[]`）、构造函数调用实参、非静态数据成员的默认成员初始化器、*mem-initializer*、赋值运算符右侧。

```cpp
int a = {1};
std::complex<double> z{1, 2};
new std::vector<std::string>{"once", "upon", "a", "time"};   // 4 个 string
f({"Nicholas", "Annemarie"});                                // 传递一个两元素的列表
return {"Norah"};                                            // 返回一个单元素的列表
int* e{};                                                    // 空指针
x = double{1};                                               // 显式构造一个 double
std::map<std::string, int> anim = {{"bear", 4}, {"cassowary", 2}, {"tiger", 7}};
```

## initializer-list 构造函数（¶2）

¶2 如果构造函数的第一个形参是 `std::initializer_list<E>` 或 `cv std::initializer_list<E>&`，且其余形参（如果有）都有默认实参，就称它为 **initializer-list 构造函数**。

注 2：构造函数模板 `template<class T> C(T)` 不是 initializer-list 构造函数。花括号列表实参使对应形参成为不推导语境（[[temp.deduct.call]]），`T` 不会被推导为 `initializer_list<…>`。

`std::initializer_list` 不是语言内建的类型：如果在使用处（即使是隐式使用，比如 `auto x = {1, 2};`）`<initializer_list>`（或 `import std;`）中的声明不可达，程序非良构。这是核心语言依赖标准库的少数几个例子之一（类似的还有 `std::type_info`、`std::source_location`、`std::meta::info` 等）。

## 决策流程（¶3）

¶3 对 "*cv* `T`" 类型的对象或引用做列表初始化时，按以下顺序判定：

| 步骤 | 条件 | 结果 |
|---|---|---|
| ¶3.1 | 有指派初始化器，`T` 不是引用 | `T` 必须是聚合类；指派顺序须不递减；聚合初始化 |
| ¶3.2 | `T` 是聚合类，列表恰有一个元素，类型为 `T` 或其派生类 | 从该元素拷贝/直接初始化（不是聚合初始化） |
| ¶3.3 | `T` 是字符数组，列表恰有一个字符串字面量 | [[dcl.init.string]] |
| ¶3.4 | `T` 是聚合 | 聚合初始化 [[dcl.init.aggr]] |
| ¶3.5 | 列表为空，`T` 是有默认构造函数的类 | 值初始化 |
| ¶3.6 | `T` 是 `std::initializer_list<E>` | 构造 backing array（¶5） |
| ¶3.7 | `T` 是类 | 构造函数重载决议，两阶段（[[over.match.list]]）；窄化则非良构 |
| ¶3.8 | `T` 是有固定底层类型的枚举，单个标量元素，直接列表初始化 | `T(v)`；窄化则非良构 {{c++17}} |
| ¶3.9 | 单个元素（非指派），`T` 不是引用或被引用类型与元素类型引用相关 | 从该元素拷贝/直接初始化；窄化则非良构 |
| ¶3.10 | `T` 是引用 | 生成纯右值（拷贝列表初始化），再用它直接初始化引用 |
| ¶3.11 | 列表为空 | 值初始化 |
| ¶3.12 | 其他 | 非良构 |

**顺序本身就是规则的一部分**。例如 ¶3.4 先于 ¶3.7，所以聚合永远不会走构造函数重载决议；¶3.5 先于 ¶3.7，所以 `T{}` 优先调用默认构造函数而不是 `initializer_list` 构造函数；¶3.9 在 ¶3.7 之后，所以对类类型而言单元素列表也会先找构造函数。

下面逐步展开。

### ¶3.1 指派初始化器 {{c++20}}

¶3.1 列表含有 *designated-initializer-list* 且 `T` 不是引用：`T` 必须是聚合类；各指派符所指成员的关联元素（[[dcl.init.aggr]] ¶3）必须按元素顺序不递减；然后做聚合初始化。

```cpp
struct A { int x; int y; int z; };
A a{.y = 2, .x = 1};          // error: 顺序与声明不一致
A b{.x = 1, .z = 2};          // OK: b.y 初始化为 0

struct B : A { int q; };
B e{.x = 1, .q = 3};          // 当前草案 OK：e.y、e.z 为 0（指派基类成员）
B f{.q = 3, .x = 1};          // error: 顺序

struct C { int p; int x; };
struct D : A, C { };
D g{.y = 1, .p = 2};          // 当前草案 OK
D h{.x = 2};                  // error: x 的查找有歧义（A::x 与 C::x）
```

要求不递减而不是严格递增，是因为多个指派符可以指向同一个关联元素，例如 `.x` 和 `.y` 都属于基类 `A`。B、D 两组例子用到了指派基类成员，这是当前草案相对 C++20/23 的扩展 {{c++26}}，截至写作时 Clang 尚未实现（详见 [[dcl.init.aggr]] ¶4）。

指派初始化器的其他限制（不能嵌套 `.a.b`、不能用于数组、不能重复、与普通子句不能混用）见 [[dcl.init.aggr]] 中的 C/C++ 对照表。

### ¶3.2 聚合从同类型对象初始化

¶3.2 `T` 是聚合类，列表恰有一个元素，元素类型是 *cv1* `U`（`U` 是 `T` 或其派生类）：用该元素初始化对象。拷贝列表初始化时用拷贝初始化，直接列表初始化时用直接初始化。

没有这一步会怎样？`struct S { int x; }; S a; S b{a};` 会走 ¶3.4 聚合初始化，用 `a` 去初始化 `b.x`，而 `S` 到 `int` 没有转换，于是非良构。这在 C++11 最初的规则中确实是个问题（`S b{a};` 无法拷贝聚合），后来通过解决一个核心问题加入了这一步，让用花括号拷贝聚合也能正常工作。

```cpp
struct S { int x; };
struct D : S { int y; };
S a{1};
S b{a};          // ¶3.2：拷贝构造，b.x == 1
D d{{1}, 2};
S c{d};          // ¶3.2：派生类 → 切片拷贝
```

### ¶3.3 花括号里的字符串字面量

¶3.3 `T` 是字符数组，列表只有一个类型合适的字符串字面量：按 [[dcl.init.string]] 初始化。`char s[] = {"abc"};` 与 `char s[] = "abc";` 等价。没有这一步，¶3.4 会把 `"abc"` 当作第一个 `char` 元素的初始化器。

### ¶3.4 聚合初始化

¶3.4 `T` 是聚合（数组或聚合类）：聚合初始化（[[dcl.init.aggr]]）。聚合的各元素从对应子句拷贝初始化；子句本身是花括号列表时，该元素递归地列表初始化。

聚合元素上的窄化同样是错误（下例出自标准）。不过要注意条文出处。C++23 的 [dcl.init.aggr] 明文规定“元素的初始化器是表达式且需要窄化转换时，程序非良构”；当前草案把聚合初始化改写为归属（appertain）模型之后，[[dcl.init.aggr]] ¶5.3 中已找不到这句对应的规范文字（只剩 ¶5.2.1 针对指派初始化器的那一句），但标准自己的例子和所有实现仍把它视为非良构。没有迹象表明语义有任何变化；如果要引用条文，C++23 的那一句是最直接的出处。

```cpp
double ad[] = { 1, 2.0 };     // OK
int ai[] = { 1, 2.0 };        // error: 窄化

struct S2 { int m1; double m2, m3; };
S2 s21 = { 1, 2, 3.0 };       // OK
S2 s22 { 1.0, 2, 3 };         // error: 窄化
S2 s23 { };                   // OK: 全部为 0
```

### ¶3.5 空列表 + 默认构造函数 = 值初始化

¶3.5 列表为空，`T` 是有默认构造函数的类：值初始化（[[dcl.init]] ¶8）。

这是防止 `initializer_list` 构造函数抢先接管的第一道防线：`std::vector<int> v{};` 调用默认构造函数，而不是用空的 `initializer_list` 调用 initializer-list 构造函数。两者对 `vector` 结果相同，但对某些类就不一样了，例如默认构造函数有副作用，或者 initializer-list 构造函数的语义不同。

```cpp
struct U {
  U(std::initializer_list<int>);   // #1
  U();                             // #2
};
U u1{};      // ¶3.5：#2
U u2{{}};    // ¶3.7：#1，列表含一个元素（值为 0 的 int）
U u3({});    // 非列表初始化：实参 {} 到 initializer_list<int> 是恒等转换，
             // 到 U 的拷贝/移动构造函数需要用户定义转换 → 选 #1（空列表）
```

### ¶3.6 `std::initializer_list` 本身

¶3.6 `T` 是 `std::initializer_list<E>` 的特化：按 ¶5 构造 backing array。例如 `std::initializer_list<int> il = {1, 2, 3};` 或作为 initializer-list 构造函数的实参。

### ¶3.7 构造函数：两阶段重载决议

¶3.7 `T` 是类类型（非聚合，且列表非空或没有默认构造函数）：考虑构造函数，按 [[over.match.list]] 做重载决议。**如果任何实参需要窄化转换，程序非良构**。

[[over.match.list]] 分两个阶段：

1. 第一阶段（列表非空或 `T` 没有默认构造函数时）：候选只有 initializer-list 构造函数，整个列表作为唯一的实参。
2. 第二阶段（第一阶段没有可行函数时）：候选是所有构造函数，列表的各元素分别作为实参。

在[[g:copy-list-initialization|拷贝列表初始化]]中，如果最终选中了 `explicit` 构造函数，程序非良构，而不是不考虑这个构造函数。

`initializer_list` 构造函数抢先接管的机制就在这里（参见术语 [[g:initializer-list-constructor]]）：只要 initializer-list 构造函数可行，第二阶段根本不会发生。而可行的门槛很低，窄化**不会**使转换不可行（[[over.ics.list]]），只会在选中之后使程序非良构：

```cpp
#include <vector>
#include <string>
std::vector<int> v1{10, 20};          // 第一阶段：initializer_list<int> 可行 → 2 个元素 {10, 20}
std::vector<int> v2(10, 20);          // 非列表：vector(size_type, const int&) → 10 个 20
std::vector<std::string> v3{3};       // 第一阶段：int → string 不可行 → 第二阶段：vector(size_type) → 3 个空串
std::vector<int> v4{3.0};             // error: 第一阶段可行（double→int 有转换序列），选中后发现窄化
```

`v4` 最违反直觉。程序员也许期望窄化使候选不可行，从而回退到 `vector(size_type)`，但规则不是这样设计的：窄化是错误，不是不匹配。这个设计是有意的，如果窄化只是使候选不可行，`v4` 就会悄悄地选择一个含义完全不同的构造函数。

标准的例 4 展示了另一种抢先接管的情形：

```cpp
struct S {
  S(std::initializer_list<double>);   // #1
  S(std::initializer_list<int>);      // #2
  S(std::initializer_list<S>);        // #3
  S();                                // #4
};
S s1 = { 1.0, 2.0, 3.0 };             // #1
S s2 = { 1, 2, 3 };                   // #2
S s3{s2};                             // #3（而不是拷贝构造函数！）
S s4 = { };                           // #4（¶3.5）
```

再看 `S s3{s2};`：`S` 不是聚合，¶3.2 不适用；第一阶段中，从 `{s2}` 构造 `initializer_list<S>` 是可行的（`s2` 拷贝初始化一个 `S` 元素），于是选中 #3。这是一个真实的风险：为类添加一个 `initializer_list<T>` 构造函数（`T` 可从该类转换），会改变所有 `X{x}` 形式的拷贝。

没有 initializer-list 构造函数时，¶3.7 就是普通的构造函数重载决议加窄化检查：

```cpp
struct S {
  S(int, double, double);   // #1
  S();                      // #2
};
S s1 = { 1, 2, 3.0 };       // OK: #1
S s2 { 1.0, 2, 3 };         // error: 窄化（double → int）
S s3 { };                   // OK: #2
```

`explicit` 在拷贝列表初始化中的行为：

```cpp
struct S { explicit S(int); S(long); };
S s1 = {1};     // error: 选中了 explicit S(int)（精确匹配），而这是拷贝列表初始化
S s2 = 1;       // OK: 拷贝初始化不考虑 explicit 构造函数，只剩 S(long)
S s3{1};        // OK: 直接列表初始化
```

`s1` 与 `s2` 的区别体现了 [[over.match.list]] 注 1：在拷贝列表初始化中，explicit 构造函数**参与**重载决议，只是一旦被选中，程序就非良构；而在普通拷贝初始化中，它们不参与。这样设计，是为了避免加上 explicit 之后悄悄选中另一个重载。

### ¶3.8 有固定底层类型的枚举 {{c++17}}

¶3.8 `T` 是有固定底层类型 `U` 的枚举（`enum class E`，或 `enum E : U`），列表只有一个标量元素 `v`，`v` 能隐式转换为 `U`，并且是直接列表初始化：对象的值为 `T(v)`；如果 `v` 到 `U` 需要窄化，程序非良构。

这条规则的动机（[[P0138R2]]）是让 `enum class byte : unsigned char {};` 这类强类型整数能用 `byte b{42};` 初始化，而不必写 `byte b = static_cast<byte>(42);`，同时保持不能隐式转换的类型安全：

```cpp
enum byte : unsigned char { };
byte b { 42 };              // OK
byte c = { 42 };            // error: 拷贝列表初始化
byte d = byte{ 42 };        // OK: 与 b 同值
byte e { -1 };              // error: 窄化

struct A { byte b; };
A a1 = { { 42 } };          // error: 聚合元素是拷贝初始化
A a2 = { byte{ 42 } };      // OK

void f(byte);
void g() { f({ 42 }); }     // error: 实参传递是拷贝初始化

enum class Handle : std::uint32_t { Invalid = 0 };
Handle h { 42 };            // OK
```

限定为直接列表初始化，正是为了防止 `f({42})`、`A{{42}}` 这样的隐式转换悄悄发生。C++17 之前，`byte b{42};` 非良构（整数不能隐式转换为枚举）。

### ¶3.9 单元素

¶3.9 列表不是指派列表，只有一个类型为 `E` 的元素，并且 `T` 不是引用（或者其被引用类型与 `E` 引用相关）：从该元素初始化（按上下文决定是拷贝还是直接初始化）；需要窄化则非良构。

这是标量最常走的分支：

```cpp
int x1 {2};          // OK
int x2 {2.0};        // error: 窄化
int i = 0;
int& r {i};          // ¶3.9：被引用类型 int 与 int 引用相关 → 直接初始化引用 → 绑定到 i
const long& rl {i};  // 不引用相关 → 跳到 ¶3.10
```

对引用要求引用相关，确保了 `int& r{i};` 真的绑定到 `i`，而不是先创建一个临时量。

### ¶3.10 引用

¶3.10 `T` 是引用（且不满足 ¶3.9）：生成一个纯右值，其结果对象由列表拷贝列表初始化；再用这个纯右值直接初始化引用。纯右值的类型是被引用类型；如果 `T` 是对未知边界数组 `U[]` 的引用，纯右值的类型就是 `U x[] H` 中 `x` 的类型（即由列表推导出边界）。

```cpp
struct S {
  S(std::initializer_list<double>);   // #1
  S(const std::string&);              // #2
};
const S& r1 = { 1, 2, 3.0 };          // OK: #1
const S& r2 { "Spinach" };            // OK: #2
S& r3 = { 1, 2, 3 };                  // error: 纯右值不能绑定到非 const 左值引用
const int& i1 = { 1 };                // OK（¶3.9）
const int& i2 = { 1.1 };              // error: 窄化
const int (&iar)[2] = { 1, 2 };       // OK: iar 绑定到临时数组
const int (&iau)[] = { 1, 2, 3 };     // OK: 临时数组类型为 int[3]

struct A { } a;
struct B { explicit B(const A&); };
const B& b2{a};                       // error: 不能从 A 拷贝列表初始化 B 临时量（explicit）

struct C { int x; };
C&& c = { .x = 1 };                   // OK
```

`const B& b2{a};` 很微妙：虽然整体是直接列表初始化，但 ¶3.10 生成的纯右值是拷贝列表初始化的，所以不能使用 explicit 构造函数。

!!! impl
    截至写作时，Clang 接受 `const B& b2{a};`（大概是把它当作直接初始化 `B` 临时量），只对 `const B& b3 = {a};` 报 "chosen constructor is explicit in copy-initialization"。按标准，两者都非良构。

### ¶3.11–¶3.12 空列表与兜底

¶3.11 列表为空：值初始化。类类型已在 ¶3.4/¶3.5/¶3.7 处理完，所以走到这里的是标量等非类类型。`int** pp{};` 是空指针，`int k{};` 是 0。

¶3.12 其他情形非良构，例如 `int x{1, 2};`（标量的多元素列表）。

标准的例 11 总结了常见情形：

```cpp
struct A { int i; int j; };
A a1 { 1, 2 };            // 聚合初始化
A a2 { 1.2 };             // error: 窄化
struct B { B(std::initializer_list<int>); };
B b1 { 1, 2 };            // 构造 initializer_list<int> 并调用构造函数
B b2 { 1, 2.0 };          // error: 窄化
struct C { C(int i, double j); };
C c1 = { 1, 2.2 };        // 调用 C(1, 2.2)
C c2 = { 1.1, 2 };        // error: 窄化
int j { 1 };              // 1
int k { };                // 0
```

## 求值顺序（¶4）

¶4 花括号列表中的各子句（包括包展开产生的）**严格按出现顺序**求值：前一个子句的所有值计算和副作用都先于后一个子句。如果子句被解释为构造函数实参，用到的默认实参也按其对应子句本应所在的位置依次求值。

注 4 强调，这一顺序与初始化的语义无关。即使元素最终作为构造函数实参（普通函数调用的实参之间顺序不确定），花括号也保证从左到右。

```cpp run
#include <iostream>
struct I { I(int x) { std::cout << x; } };
struct S { S(I, I = 2) {} };
int main() {
  S(1, 2); std::cout << '\n';   // 未指定顺序：打印 12 或 21
  S{1, 2}; std::cout << '\n';   // 一定打印 12
  S{1};                         // 一定打印 12（默认实参按其位置求值）
}
```

因此，`T{f(), g()}` 是 C++ 中少数几种能保证实参求值顺序的写法，常用于在包展开中给副作用排序：`(void)std::initializer_list<int>{(process(args), 0)...};`（C++17 之前折叠表达式的替代品）。

## `std::initializer_list` 与 backing array（¶5–¶6）

¶5 从初始化器列表构造 `std::initializer_list<E>` 对象时，如同实现生成并实质化了一个类型为 “`N` 个 `const E` 的数组” 的纯右值（`N` 为元素个数），这个数组称为 **backing array**。数组的每个元素从列表的对应元素拷贝初始化，`initializer_list` 对象指向这个数组。

由此有三个推论：

1. 元素是 `const` 的，所以不能从 `initializer_list` 中移动出元素。`std::vector<std::unique_ptr<int>> v{std::make_unique<int>(1)};` 非良构，因为 `vector` 的 initializer-list 构造函数只能拷贝，而 `unique_ptr` 不可拷贝。
2. 元素是拷贝初始化的，所以不能使用 explicit 构造函数，选中的构造函数或转换函数需要在初始化器列表的上下文中可访问（注 5）。
3. 如果需要窄化，程序非良构。

注 6 {{c++26}}：backing array 是**潜在非唯一对象**（potentially non-unique objects，[[intro.object]]），和字符串字面量一样。这是 [[P2752R3]] 带来的变化：当元素都是常量时，实现可以把 backing array 放在静态只读存储中，并与其他内容相同的数组共享，而不必每次都在栈上构造一份拷贝。在 C++23 及以前，每次求值都必须产生一个不同的数组对象（理论上可以通过比较地址观察到），这妨碍了这一优化。

¶6 backing array 的寿命与其他临时对象相同（[[class.temporary]]），只是用这个数组初始化 `initializer_list` 对象时，会**像引用绑定临时量那样延长**数组的寿命：

```cpp
void f(std::initializer_list<double> il);
void g(float x) { f({1, x, 3}); }
void h() { f({1, 2, 3}); }
```

实现大致等价于：

```cpp
void g(float x) {
  const double __a[3] = {double{1}, double{x}, double{3}};             // backing array
  f(std::initializer_list<double>(__a, __a + 3));
}
void h() {
  static constexpr double __b[3] = {double{1}, double{2}, double{3}};  // backing array（C++26：可以是静态的）
  f(std::initializer_list<double>(__b, __b + 3));
}
```

寿命的几种典型情形（标准例 14）：

```cpp
std::vector<std::complex<double>> v1 = { 1, 2, 3 };   // initializer_list 是函数实参 → 数组活到完整表达式结束
void f() {
  std::initializer_list<int> i3 = { 1, 2, 3 };       // initializer_list 是变量 → 数组与 i3 同寿命
}
struct A {
  std::initializer_list<int> i4;
  A() : i4{ 1, 2, 3 } {}                              // error: 相当于把临时数组绑定到引用成员
};
```

而下面的情形不会诊断为非良构，却必然悬垂：

```cpp run ub
#include <initializer_list>
std::initializer_list<int> make() {
  return {1, 2, 3};             // backing array 在 return 语句结束时销毁
}
int main() {
  auto il = make();
  return *il.begin();           // UB: 读取已销毁的数组
}
```

`initializer_list` 本身没有引用成员（它通常是一个指针加一个长度），所以 [[stmt.return]] ¶6 关于组成引用绑定临时量的规则不覆盖它。应该把 `initializer_list` 看作指向临时数组的视图，就像 `std::string_view` 指向字符串一样，不要存储，也不要返回。

## 窄化转换（¶7）

¶7 **窄化转换**（narrowing conversion）是以下几种隐式转换：

| 编号 | 从 | 到 | 例外（不算窄化） |
|---|---|---|---|
| ¶7.1 | 浮点 | 整数 | 无，总是窄化，即使是常量 `2.0` |
| ¶7.2 | 浮点 `T` | 浮点转换等级既不高于也不等于 `T` 的浮点类型 | 结果是常量表达式，且值有限且未溢出，或者转换前后都不是有限值 |
| ¶7.3 | 整数或无作用域枚举 | 浮点 | 源是常量表达式，转换后的值能放进目标类型，且转换回去得到原值 |
| ¶7.4 | 整数或无作用域枚举 | 不能表示源类型所有值的整数类型 | ¶7.4.1 源是宽度 w 小于其类型宽度的位域，且目标能表示 w 位同符号整数的所有值；¶7.4.2 源是常量表达式，其值（整型提升后）能放进目标类型 |
| ¶7.5 | 指针或成员指针 | `bool` | 无 {{c++20}} |

注 7：这些转换只在列表初始化的顶层被禁止，嵌套在其他表达式里的转换不受影响：

```cpp
int f(int);
int a[] = { 2, f(2), f(2.0) };   // OK: double→int 发生在函数实参中，不在列表初始化的顶层
```

标准例 15 及若干补充：

```cpp
int x = 999;                    // x 不是常量表达式
const int y = 999;
const int z = 99;
char c1 = x;                    // OK: 不是列表初始化（尽管确实窄化了）
char c2{x};                     // error: 可能窄化
char c3{y};                     // error: 窄化（设 char 为 8 位）
char c4{z};                     // OK: 常量 99 放得下
unsigned char uc1 = {5};        // OK
unsigned char uc2 = {-1};       // error
unsigned int ui1 = {-1};        // error
signed int si1 = { (unsigned int)-1 };   // error
int ii = {2.0};                 // error: ¶7.1，浮点到整数没有常量例外
float f1 { x };                 // error: 可能窄化
float f2 { 7 };                 // OK: 7 能被 float 精确表示
bool b = {"meow"};              // error: ¶7.5，指针到 bool
```

### 每条规则背后的考量

- ¶7.1 浮点 → 整数没有常量例外：即使 `2.0` 能精确转换为 `2`，写 `int i{2.0}` 几乎肯定意味着类型写错了；而且浮点常量的精确值在不同平台上可能不同。
- ¶7.2 浮点 → 浮点的常量例外允许不精确：`float f{0.1};` 合法，尽管 `0.1` 不能用 `float` 精确表示，否则几乎所有浮点字面量都无法初始化 `float`。要求的只是值有限且未溢出，所以 `float f{1e300};` 非良构。无穷与 NaN 可以互相转换（`float f{inf};` 合法）。C++23 起改用**浮点转换等级**（[[conv.rank]]）描述，以纳入扩展浮点类型（[[P1467R9]]）：`std::float16_t` 与 `std::bfloat16_t` 的等级互不可比，二者之间的转换双向都是窄化。
- ¶7.3 整数 → 浮点要求往返精确：`float f{16777217};` 非良构（2²⁴+1 不能用 `float` 精确表示），`float f{16777216};` 合法。
- ¶7.4.1 位域例外：`unsigned v : 4` 的值总在 0–15 之间，用它初始化 `unsigned char` 不会丢失信息，所以即使 `v` 不是常量，也不算窄化。这是较新的规则（通过缺陷报告加入）。
- ¶7.5 指针 → `bool`：由 [[P1957R2]]（C++20，作为缺陷报告）加入。动机是 `std::variant<bool, std::string> v = "abc";` 曾经选中 `bool` 备选项，因为 `const char*` → `bool` 是标准转换，优于到 `std::string` 的用户定义转换。`variant` 的转换构造函数用能否（无窄化地）列表初始化来筛选备选项，把指针到 `bool` 列为窄化就修复了这个问题。

```cpp
double d = 0.1;
float f1{d};                // error: 非常量
float f2{0.1};              // OK: 常量，有限（不精确也可以）
float f3{1e300};            // error: 溢出
long double ld{d};          // OK: 等级更高
float f5{16777217};         // error: 不能往返
struct BF { unsigned v : 4; } bf;
unsigned char uc{bf.v};     // OK: ¶7.4.1
bool b1{1};                 // OK: 常量 1 放得下
bool b2{2};                 // error
int* p = nullptr;
bool b3{p};                 // error: ¶7.5
```

## `auto` 与花括号

[[dcl.spec.auto]] 对花括号初始化器有特殊的推导规则，可以看作 `initializer_list` 抢先接管在类型推导中的翻版：

```cpp
auto x1 = { 1, 2 };         // std::initializer_list<int>
auto x2 = { 1, 2.0 };       // error: 无法推导元素类型
auto x3{ 1, 2 };            // error: 直接列表初始化只能有一个元素
auto x4 = { 3 };            // std::initializer_list<int>
auto x5{ 3 };               // int
decltype(auto) x6 = { 1, 2 };   // error: { 1, 2 } 不是表达式
```

`x4` 与 `x5` 的不同来自 [[N3922]]。在 C++11/14 最初的规则中，`auto x5{3};` 也推导为 `initializer_list<int>`，这被普遍认为是设计错误。N3922 在 C++17 中改为直接列表初始化推导为元素类型，主流编译器把它作为缺陷修复，应用于 C++11 以后的所有模式。拷贝列表初始化 `auto x = {…}` 仍然推导为 `initializer_list`。

函数模板的实参推导不会从花括号列表推导出 `initializer_list`（这是 `auto` 的特例，不是一般规则）：

```cpp
template<class T> void f(T);
template<class T> void g(std::initializer_list<T>);
void test() {
  f({1, 2});                   // error: 花括号列表使 T 处于不推导语境
  g({1, 2});                   // OK: T = int
}
auto lam = [] { return {1, 2}; };   // error: 不能从花括号列表推导返回类型
```

## 类模板实参推导（CTAD）与花括号

CTAD（[[over.match.class.deduct]]）遇到花括号时同样有 initializer-list 优先的问题，但有一条特殊规则处理单个元素是同一模板特化的情形：

```cpp run ok
#include <vector>
#include <type_traits>
std::vector v{1, 2, 3};          // vector<int>
std::vector v2{v};               // vector<int>（拷贝推导候选优先），而不是 vector<vector<int>>
std::vector v3{v, v};            // vector<vector<int>>
static_assert(std::is_same_v<decltype(v2), std::vector<int>>);
static_assert(std::is_same_v<decltype(v3), std::vector<std::vector<int>>>);
int main() {}
```

`v2` 与 `v3` 的不一致经常让人困惑。[[over.match.class.deduct#6]] 规定，如果列表只有一个表达式，且其类型是被推导模板的特化（或其派生类），就**省略** [[over.match.list]] 的第一阶段（initializer-list 构造函数），于是拷贝推导候选胜出。这和 ¶3.7 中 `S s3{s2}` 选中 `initializer_list<S>` 构造函数的行为恰好相反：在 CTAD 层面优先拷贝，而 CTAD 之后的构造函数选择仍按 ¶3.7 进行。

## 实现视角

!!! impl
    - `std::initializer_list` 的布局：libc++ 与 libstdc++ 都实现为指针加长度，MSVC STL 则是首尾两个指针。编译器（通过私有构造函数）直接构造它，所以它必须来自标准库头文件，编译器需要知道这个类型的确切定义。
    - backing array 的存放：元素全为常量时，编译器早就会把数组放在 `.rodata` 中（这是 as-if 规则允许的优化）；[[P2752R3]] 让这一优化在地址可被观察的情况下也合法。
    - 窄化诊断：Clang 的窄化诊断属于 `-Wc++11-narrowing` 组，在 C++11 及以后的模式下默认就是错误（诊断文字形如 "type 'double' cannot be narrowed to 'int' in initializer list"）。

## 历史与演进

!!! history
    - **C++11**：列表初始化、`std::initializer_list`、窄化转换、统一初始化。
    - **C++14**：放宽聚合的花括号省略；聚合可以有默认成员初始化器（[[dcl.init.aggr]]）。
    - **C++17**：[[N3922]] `auto x{1}` 推导为 `int`；[[P0138R2]] 有固定底层类型的枚举可从整数直接列表初始化；聚合从同类型对象的列表初始化（¶3.2）等缺陷修复。
    - **C++20**：[[P0329R4]] 指派初始化器（¶3.1）；[[P1957R2]] 指针到 `bool` 是窄化；未知边界数组的引用可以从列表推导边界。
    - **C++23**：[[P1467R9]] 扩展浮点类型，窄化规则改用浮点转换等级。
    - **C++26**：[[P2752R3]] backing array 可以放在静态存储中；当前草案还允许指派基类成员。

## 陷阱

!!! pitfall "`vector<int>{n, v}` 不是 `vector<int>(n, v)`"
    对于有 initializer-list 构造函数的类型，花括号几乎总是选中它。需要接受大小和值的那个构造函数时，应该用圆括号。

!!! pitfall "`vector<string>{{“a”, “b”}}`"
    第一阶段从 `{{"a", "b"}}` 构造 `initializer_list<string>`：外层花括号对应 `initializer_list`，内层 `{"a", "b"}` 初始化**一个** `string`，调用的是 `string(const char*, const char*)`（迭代器区间构造函数）。两个指针指向不同的字面量，所以行为未定义。正确的写法是 `{"a", "b"}`。

!!! pitfall "窄化是错误，不是不匹配"
    `std::vector<int> v{3.0};` 不会回退到 `vector(size_type)`。在泛型代码中，`T{args...}` 可能因为窄化而失败，`T(args...)` 却能成功。

!!! pitfall "不能从 `initializer_list` 移动"
    `std::vector<std::unique_ptr<T>> v{std::make_unique<T>()};` 非良构。可以用 `reserve` 加 `emplace_back`，或者从数组或范围构造。

!!! pitfall "不要存储或返回 `initializer_list`"
    它只是指向临时 backing array 的视图，作为数据成员或返回值都会悬垂（作为数据成员在 *mem-initializer* 中初始化时会有诊断）。

## 思考题

!!! question "1. 下面各行调用哪个构造函数？"
    ```cpp
    struct X {
      X(int, int);                        // #1
      X(std::initializer_list<long>);     // #2
      explicit X(std::initializer_list<int>);  // #3
    };
    X a{1, 2};
    X b = {1, 2};
    X c(1, 2);
    ```

<details markdown="1">
<summary>答案</summary>

- `a`：直接列表初始化。第一阶段的候选是 #2、#3（都是 initializer-list 构造函数）。`{1, 2}` 到 `initializer_list<int>` 是恒等转换，到 `initializer_list<long>` 需要整数转换，所以 #3 更好。选中 #3，直接初始化允许 explicit。
- `b`：拷贝列表初始化。第一阶段同样选中 #3（explicit 构造函数参与重载决议），然后因为拷贝列表初始化选中了 explicit 构造函数而**非良构**，不会退回 #2。
- `c`：非列表初始化，普通重载决议，只有 #1 可行（`initializer_list` 不能从两个 `int` 实参构造）。
</details>

!!! question "2. `struct S { int x; }; S s{S{1}};` 走 ¶3 的哪一步？如果 `S` 有一个 `S(std::initializer_list<S>)` 构造函数呢？"

<details markdown="1">
<summary>答案</summary>

`S` 是聚合，列表只有一个元素，类型是 `S` → ¶3.2：从 `S{1}` 直接初始化 `s`，按 [[dcl.init]] ¶15.6.1（同类型纯右值）直接成为 `s`，无拷贝。

加上 `S(std::initializer_list<S>)` 后，`S` 有用户声明的构造函数，不再是聚合；¶3.2、¶3.4 都不适用，走 ¶3.7：第一阶段 `initializer_list<S>` 从 `{S{1}}` 构造可行——但 `S{1}` 本身也要重新分析：它现在同样走 ¶3.7，第一阶段 `initializer_list<S>` 从 `{1}` 构造要求 `1` → `S`，没有可行转换（`S` 没有接受 `int` 的构造函数），第二阶段也没有，`S{1}` 非良构。即：加上这个构造函数后整个声明非良构。
</details>

!!! question "3. 为什么 ¶3.8 只允许**直接**列表初始化，而 ¶3.9 对标量同时允许直接和拷贝列表初始化？"

<details markdown="1">
<summary>答案</summary>

¶3.9 处理的是"本来就允许隐式转换"的情形（例如 `int` → `long`），花括号只是额外加上窄化检查，`long l = {1};` 与 `long l = 1;` 语义一致，没有理由禁止。

¶3.8 处理的是"本来**不允许**隐式转换"的情形：整数到枚举没有隐式转换。花括号在这里**新增**了一种转换能力。若允许拷贝列表初始化，`void f(byte); f({42});`、`return {42};`、聚合成员 `{42}` 都会悄悄地把整数变成枚举，破坏强类型枚举的初衷。只允许直接列表初始化，意味着程序员必须在声明处明确写出类型（`byte b{42}` 或 `byte{42}`）。
</details>

## 小结

!!! summary
    - 花括号初始化的十二步：指派 → 聚合同类拷贝 → 字符数组字符串 → 聚合 → 空列表默认构造 → `initializer_list` 本身 → 构造函数（两阶段）→ 固定底层类型枚举 → 单元素 → 引用 → 空列表值初始化 → 非良构。
    - 对于非空列表，initializer-list 构造函数总是最先考虑，只要可行就胜出；窄化让程序非良构，而不是让候选不可行。
    - backing array 是 `const E[N]`，元素拷贝初始化，寿命像绑定到引用的临时量；C++26 起可以是静态共享的。
    - 窄化：浮点→整数（总是）、浮点降级（常量有限值例外）、整数→浮点（常量往返例外）、整数缩窄（常量与位域例外）、指针→`bool`。只在列表初始化的顶层检查。
    - `auto x{1}` 是 `int`，`auto x = {1}` 是 `initializer_list<int>`。
