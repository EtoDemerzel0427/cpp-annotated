---
title: 类型说明符
summary: 类型说明符的分类与组合规则；const/volatile 的语义（修改 const 对象是 UB、volatile 访问由实现定义）；简单类型说明符与基础类型的对应表；C++26 的包索引说明符与类型拼接；详述类型说明符（struct X / enum E）
status: done
covers: dcl.type.general, dcl.type.cv, dcl.type.simple, dcl.type.pack.index, dcl.type.elab, dcl.type.splice
papers: P2662, P2996
related: dcl.spec, basic.type.qualifier, basic.fundamental, dcl.type.decltype, dcl.spec.auto, dcl.type.class.deduct, basic.lookup.elab
tags: 声明, 类型, cv 限定, 反射
updated: 2026-10-17
---

[dcl.type] 讲的是说明符序列中**决定类型**的那一部分。它包括：

| 小节 | 内容 | 本页 |
|---|---|---|
| 9.2.9.1 [dcl.type.general] | 类型说明符的分类；"至多一个类型说明符"及其例外 | ✓ |
| 9.2.9.2 [dcl.type.cv] | `const` / `volatile` | ✓ |
| 9.2.9.3 [dcl.type.simple] | 简单类型说明符：`int`、类型名、`decltype`、`auto`…… | ✓ |
| 9.2.9.4 [dcl.type.pack.index] | 包索引 `Ts...[I]` {{c++26}} | ✓ |
| 9.2.9.5 [dcl.type.elab] | 详述类型说明符 `struct X`、`enum E` | ✓ |
| 9.2.9.6 [dcl.type.decltype] | `decltype` | [[dcl.type.decltype]] |
| 9.2.9.7 [dcl.spec.auto] | `auto`、`decltype(auto)` | [[dcl.spec.auto]] |
| 9.2.9.8 [dcl.type.class.deduct] | CTAD 占位符 | [[dcl.type.class.deduct]] |
| 9.2.9.9 [dcl.type.splice] | 类型拼接 `[: r :]` {{c++26}} | ✓ |

背景：说明符序列与"类型名何时被吞下"的规则见 [[dcl.spec]]；类型如何由说明符和声明符共同确定见 [[dcl.meaning]]。

---

## 9.2.9.1 类型说明符的分类（[dcl.type.general]）

¶1 语法上有三层嵌套的概念：

- ***type-specifier***（类型说明符）：*simple-type-specifier*、*elaborated-type-specifier*、*typename-specifier*、*cv-qualifier*；
- ***defining-type-specifier***（定义类型说明符）：*type-specifier*，再加上 *class-specifier*（`struct X { … }`）和 *enum-specifier*（`enum E { … }`）——也就是**能定义新类型**的那些；
- *type-specifier-seq* / *defining-type-specifier-seq*：它们的序列，末尾可跟属性，属性属于前面说明符所确定的类型。

为什么要区分？因为有些语法位置**不允许定义类型**：例如 *type-id*（`sizeof(T)`、`static_cast<T>`、模板实参）用的是 *type-specifier-seq*，所以 `sizeof(struct { int x; })` 非良构；而声明的 *decl-specifier-seq* 和别名声明的 *defining-type-id* 可以定义类型。

### 至多一个类型说明符（¶2）

¶2 作为一般规则，一个完整的 *decl-specifier-seq* 或 *defining-type-specifier-seq* 中**至多一个**定义类型说明符，*type-specifier-seq* 中至多一个类型说明符。例外只有六条：

| ¶ | 例外 | 例子 |
|---|---|---|
| 2.1 | `const` 可与除自身外的任何类型说明符组合 | `const int`、`const T` |
| 2.2 | `volatile` 可与除自身外的任何类型说明符组合 | `volatile const int` |
| 2.3 | `signed`/`unsigned` 可与 `char`、`long`、`short`、`int` 组合 | `unsigned char`、`signed long` |
| 2.4 | `short`/`long` 可与 `int` 组合 | `short int` |
| 2.5 | `long` 可与 `double` 组合 | `long double` |
| 2.6 | `long` 可与 `long` 组合 | `long long` |

这六条就是 C 风格多关键字类型名（`unsigned long long int`）合法的全部依据。由此可得：

```cpp error
long long long x;       // error: 第三个 long 无处可组合（"long 可与 long 组合"只允许一次）
long float f;           // error: long 只能与 int、double、long 组合
short long s;           // error
signed unsigned u;      // error: signed 与 unsigned 互不组合
unsigned double d;      // error: unsigned 只能与 char/long/short/int 组合
signed bool b;          // error
unsigned char8_t c;     // error: char8_t/char16_t/char32_t/wchar_t 不能带符号说明符
typedef int T;
T unsigned u2;          // error: 类型名不能和 unsigned 组合
```

```cpp run ok
#include <type_traits>
int long unsigned long x = 0;   // 顺序任意：unsigned long long
static_assert(std::is_same_v<decltype(x), unsigned long long>);
long double ld;
signed char sc;                 // signed char 与 char 是不同类型
static_assert(!std::is_same_v<char, signed char> && !std::is_same_v<char, unsigned char>);
int main() { }
```

`long long long` 不合法的论证有点"语法律师"：¶2.6 说 `long` 可以与 `long` 组合，得到 `long long`；但第三个 `long` 需要与 `long long` 组合，而没有任何一条例外允许这样做。

### 至少一个非 cv 类型说明符（¶3）

¶3 除了**构造函数、析构函数、转换函数**的声明，完整的 *decl-specifier-seq* 或 *type-specifier-seq* 中**至少要有一个**不是 cv 限定符的定义类型说明符。这就是 C++ 没有"隐式 int"的规则：C89 中 `const x = 1;`、`static y;`、`f() { }` 都隐含 `int`，C++ 中一律非良构。

```cpp error
const x = 1;     // error: 没有类型说明符（C89 中是 const int）
static y;        // error
f() { }          // error: 函数也需要返回类型（构造/析构/转换函数除外）
```

---

## 9.2.9.2 cv 限定符（[dcl.type.cv]）

cv 限定类型本身的定义（`const T`、`volatile T`、cv 组合的偏序）在 [[basic.type.qualifier]]；本节规定 cv 限定符作为**说明符**的规则，以及修改 const 对象、访问 volatile 对象的**行为**。

### 语法规则（¶1–2）

¶1：

- 两个 cv 限定符：`const` 和 `volatile`。每个在一个 *cv-qualifier-seq* 中至多出现一次。
- 若说明符序列中有 cv 限定符，则 *init-declarator-list* / *member-declarator-list* **不得为空**——`const struct S { };` 非良构（cv 修饰谁？）。
- **冗余的 cv 限定被忽略**。Note 2：例如由 typedef 引入的冗余。

```cpp run ok
#include <type_traits>
typedef const int CI;
const CI x = 1;             // const const int → const int：经由 typedef 的冗余被忽略
static_assert(std::is_same_v<decltype(x), const int>);
template<class T> using AddConst = const T;
static_assert(std::is_same_v<AddConst<const int>, const int>);   // 同理
int main() { }
```

注意区分：**直接**写 `const const int` 违反的是 [[dcl.type.general#2]] 的组合规则（Clang 对此只给 `-Wduplicate-decl-specifier` 警告）；而经由 typedef、模板参数产生的重复限定是"冗余 cv"，被静默忽略。

¶2（注）：声明 `const` 会影响**链接**（命名空间作用域的 const 变量默认内部链接，[[basic.link#3]]）和**能否用于常量表达式**（[[expr.const.init]]）；const 对象的定义必须有初始化器，或者能被默认初始化为确定的值（const-default-constructible，[[dcl.init.general]]）。

### 通过 const 访问路径（¶3）

¶3 指向（或引用）cv 限定类型的指针（引用），不必真的指向 cv 限定的对象，但**被当作**是 cv 限定的：通过 const 访问路径不能修改对象，即使该对象本身不是 const、通过其他路径可以修改。Note 4：类型系统支持 cv，使其不经强制转换就无法被绕过。

这把两件事分开了：

- **访问路径**（表达式的类型）是否 const：决定**编译期**能否写 `*p = 4;`；
- **对象本身**是否 const：决定**运行期**修改它是否 UB（¶4）。

### 修改 const 对象是 UB（¶4）

¶4 在 const 对象的**生存期内**试图修改它，行为未定义 {{ub}}。

!!! std
    Any attempt to modify a const object during its lifetime results in undefined behavior.

"const 对象"的精确定义在 [[basic.type.qualifier]]：类型为 const T 的对象，或这种对象的非 mutable 子对象。所以：

```cpp run ub
struct X { mutable int i; int j; };
struct Y { X x; Y() { } };
const Y y;                       // const 对象（有用户提供的构造函数，因此可以没有初始化器）

int main() {
    int i = 2;
    const int* cip = &i;         // const 访问路径指向非 const 对象
    // *cip = 4;                 // error: 通过 const 访问路径修改
    int* ip = const_cast<int*>(cip);
    *ip = 4;                     // OK: i 本身不是 const 对象

    const int* ciq = new const int(3);   // 动态创建的 const 对象
    int* iq = const_cast<int*>(ciq);
    *iq = 4;                     // UB: 修改 const 对象

    y.x.i++;                     // OK: mutable 成员不是 const 对象
    Y* p = const_cast<Y*>(&y);
    p->x.i = 99;                 // OK: mutable 成员
    p->x.j = 99;                 // UB: y.x.j 是 const 对象的非 mutable 子对象
    delete ciq;
}
```

为什么修改 const 对象是 UB，而不是"良构但没有效果"之类？因为这给了实现两项重要自由：

1. **把 const 对象放进只读存储**：带常量初始化的 const 全局对象通常放在 `.rodata`，写入会触发段错误；
2. **常量传播**：编译器可以假设 const 对象的值从不改变，把读取替换为初值。

```cpp run ub
#include <cstdio>
const int limit = 10;
int main() {
    int* p = const_cast<int*>(&limit);
    *p = 20;                          // UB：实践中通常在这里崩溃（limit 位于只读段）
    std::printf("%d\n", limit);       // 若没崩溃，可能仍然打印 10（常量传播）
}
```

在本机（Apple Silicon，Clang 23）上实测：`-O0` 时程序在写入处因 Bus error 崩溃（`limit` 位于只读段）；`-O2` 时程序打印 `10` 并正常退出——编译器直接把 `limit` 替换为常量，写入被优化掉。同一份代码，两种截然不同的"表现"，这正是 UB 的典型面貌。

!!! note "生存期之外"
    ¶4 只管"在生存期内"。构造函数和析构函数执行期间，const 对象还**不是/不再是** const 的（[[class.ctor.general]]、[[class.dtor]]），所以构造函数可以给成员赋值。在 const 对象的存储上用 placement new 重建对象，则受 [[basic.life]] 的"透明可替换"规则约束。

!!! tip "UB 难以被检测"
    上面的例子在 `-fsanitize=address,undefined` 下运行并不会报告任何问题——UBSan 不检查对 const 对象的写入。这类 UB 只会以"只读段写入崩溃"或"优化后读到旧值"的形式间接出现。

### volatile（¶5–6）

¶5 通过 volatile glvalue 进行访问的语义**由实现定义** {{impl}}。若通过**非 volatile** 的 glvalue 访问一个**定义为** volatile 类型的对象，行为未定义 {{ub}}。

¶6（注）：volatile 是给实现的提示：对象的值可能以实现无法察觉的方式改变，应避免激进的优化；某些实现中 volatile 访问需要特殊的硬件指令。详细语义见 [[intro.execution]]（volatile 访问是**可观察行为**的一部分，[[intro.abstract]]）。C++ 中 volatile 的语义意图与 C 相同。

要点：

- volatile 访问不能被合并、删除或重排（相对于其他 volatile 访问）——因为它们是可观察行为。这是驱动程序访问内存映射 I/O 寄存器的基础。
- volatile **不提供**原子性，**不提供**线程间的内存序。多线程同步必须用 `std::atomic`（[[intro.multithread]]）；对普通变量的并发读写即使加 volatile 仍然是数据竞争，是 UB。
- C++20 弃用了 volatile 的若干用法（复合赋值与自增自减的 volatile 操作数、volatile 参数与返回类型、volatile 结构化绑定等，[[depr.volatile.type]]），其中复合赋值的弃用在 C++23 中又部分撤回（按位复合赋值）。

```cpp ub
volatile int reg = 0;          // 定义为 volatile
int read_wrong() {
    return *const_cast<int*>(&reg);   // UB: 通过非 volatile glvalue 访问 volatile 对象
}
```

---

## 9.2.9.3 简单类型说明符（[dcl.type.simple]）

### 语法（¶1–2）

¶1 *simple-type-specifier* 包括：

- （可限定的）*type-name*：类名、枚举名、typedef 名；
- `nested-name-specifier template simple-template-id`：依赖名中的模板特化；
- ***computed-type-specifier***：`decltype(…)`（[[dcl.type.decltype]]）、包索引 `T...[I]`（下文）、类型拼接 `[: r :]`（下文）；
- *placeholder-type-specifier*：`auto`、`decltype(auto)`，可带约束（[[dcl.spec.auto]]）；
- 模板名（CTAD 的推导类类型占位符）；
- 关键字：`char` `char8_t` `char16_t` `char32_t` `wchar_t` `bool` `short` `int` `long` `signed` `unsigned` `float` `double` `void`。

¶2 定义了**组成名字**（component names）：*nested-name-specifier*、*type-name*、*simple-template-id*、*simple-template-name*、（占位符的）*type-constraint* 中的名字；*type-name* 的组成名字是其中的第一个名字。这个概念供 [[basic.lookup]] 和 [[module.reach]] 等条款判断"哪些名字被这个声明使用了"。

### 推导类类型的占位符（¶3）

¶3 *placeholder-type-specifier* 是"待推导类型"的占位符（[[dcl.spec.auto]]）。一个类型说明符是**推导类类型的占位符**（CTAD，[[dcl.type.class.deduct]]），当它具有以下形式之一：

- ¶3.1 `typename(opt) nested-name-specifier(opt) 模板名`——即**没有模板实参列表**的模板名，如 `std::pair p(1, 2.0);` 中的 `std::pair`；
- ¶3.2 `typename(opt) pack-index-template-name`；
- ¶3.3 `typename(opt) splice-specifier`，且拼接的是类模板或别名模板 {{c++26}}。

其中的 *nested-name-specifier* 或 *splice-specifier* 必须是**非依赖的**，模板必须是**可推导模板**（deducible template）：

- ¶3.4 类模板；
- ¶3.5 类型模板模板参数；
- ¶3.6 别名模板 A，其定义类型标识形如 `typename(opt) nested-name-specifier(opt) template(opt) simple-template-id`，其中 *nested-name-specifier* 非依赖，*simple-template-id* 的模板名指向一个可推导模板（但不是 A 自己的类型模板模板参数）。

¶3.6 是 C++20 引入的"别名模板的 CTAD"：`template<class T> using Vec = std::vector<T>; Vec v{1, 2, 3};` 推导出 `std::vector<int>`。而 `template<class T> using Ptr = T*;` 不是可推导模板——定义类型标识不是 *simple-template-id*。

```cpp run ok
#include <vector>
#include <utility>
template<class T> using Vec = std::vector<T>;
int main() {
    std::pair p(1, 2.0);        // 推导类类型占位符：std::pair<int, double>
    Vec v{1, 2, 3};             // C++20: 别名模板 CTAD → std::vector<int>
    return int(v.size()) - 3 + (p.first - 1);
}
```

Note 1：在会进行 CTAD 的上下文中，注入类名**不会**被解释为模板名（[[temp.local]]）——所以在类模板 `A` 内部写 `A x(…);`，`A` 指的是当前特化 `A<T>`，不会触发推导。

### 简单类型说明符与类型的对应表（¶3，表 17）

表 17 列出所有合法的关键字组合及其表示的类型。按目标类型整理如下（同一行中的写法等价，顺序可任意排列）：

| 类型 | 合法写法 |
|---|---|
| `char` | `char` |
| `signed char` | `signed char` |
| `unsigned char` | `unsigned char` |
| `char8_t` / `char16_t` / `char32_t` / `wchar_t` / `bool` | 各自唯一的关键字 |
| `int` | `int`、`signed`、`signed int` |
| `unsigned int` | `unsigned`、`unsigned int` |
| `short int` | `short`、`short int`、`signed short`、`signed short int` |
| `unsigned short int` | `unsigned short`、`unsigned short int` |
| `long int` | `long`、`long int`、`signed long`、`signed long int` |
| `unsigned long int` | `unsigned long`、`unsigned long int` |
| `long long int` | `long long`、`long long int`、`signed long long`、`signed long long int` |
| `unsigned long long int` | `unsigned long long`、`unsigned long long int` |
| `float` / `double` | 各自唯一 |
| `long double` | `long double` |
| `void` | `void` |

另外：*type-name* → 它命名的类型；*simple-template-id* → [[temp.names]]；`decltype` → [[dcl.type.decltype]]；包索引 → 下文；占位符 → [[dcl.spec.auto]]；模板名 → [[dcl.type.class.deduct]]；类型拼接 → 下文。

值得注意的不对称：**`signed` 对 `int`、`short`、`long`、`long long` 是冗余的，对 `char` 不是**。¶4 的 Note 2 解释：`char` 是有符号还是无符号由实现定义 {{impl}}，`signed char` 强制有符号；而且 `char`、`signed char`、`unsigned char` 是**三个不同的类型**（[[basic.fundamental]]），不像 `int` 与 `signed int` 是同一类型。

### 顺序无关（¶4）

¶4 允许多个简单类型说明符时，它们可以与其他 *decl-specifier* **自由混排**，顺序任意：`long static unsigned const long x = 0;` 是合法的 `static const unsigned long long`。

---

## 9.2.9.4 包索引说明符（[dcl.type.pack.index]）{{c++26}}

```text
pack-index-specifier:
    typedef-name ... [ constant-expression ]
```

¶1 *typedef-name* P 必须是一个表示**包**的标识符（类型模板参数包，或别名形式的包）。

¶2 下标必须是 `std::size_t` 类型的**转换常量表达式**，其值 V（称为**索引**）满足 0 ≤ V < `sizeof...(P)`。越界是非良构（不是 UB）——这在编译期检查。

¶3 *pack-index-specifier* 是一个**包展开**（[[temp.variadic]]）——尽管它只产生一个类型。这意味着它满足"包必须被展开"的要求，可以单独出现。

¶4（注）：它表示包中第 V 个元素的类型。

```cpp run ok
#include <type_traits>
template<class... Ts> using First = Ts...[0];
template<class... Ts> using Last  = Ts...[sizeof...(Ts) - 1];
static_assert(std::is_same_v<First<int, char, double>, int>);
static_assert(std::is_same_v<Last<int, char, double>, double>);

template<class... Ts>
auto second(Ts... ts) {
    Ts...[1] x = ts...[1];        // 类型包索引 + 表达式包索引（[expr.prim.pack.index]）
    return x;
}
int main() { return int(second(1, 2.5, 'c')) - 2; }
```

```cpp error
template<class... Ts> using Bad = Ts...[2];
Bad<int, char> b;          // error: 索引 2 越界（包大小为 2）
```

在 C++23 及之前，取包中第 N 个类型需要递归模板、`std::tuple_element_t<N, std::tuple<Ts...>>`，或借助重载决议的各种技巧，编译开销都较大。包索引（[[P2662]]）让它成为语言内建操作。

!!! lawyer "语法上的一处破坏"
    C++23 中，`template<class... T> void f(T... [1]);` 声明的是一个**未命名的函数参数包**，每个参数的类型是 `T[1]`（随后调整为指针）。C++26 中 `T...[1]` 被解析为包索引说明符，这样的代码变得非良构；带名字的 `void g(T... ptr[1]);` 不受影响（[[diff.cpp23.dcl.dcl]]）。

---

## 9.2.9.5 详述类型说明符（[dcl.type.elab]）

```text
elaborated-type-specifier:
    class-key attribute-specifier-seq(opt) nested-name-specifier(opt) identifier
    class-key simple-template-id
    class-key nested-name-specifier template(opt) simple-template-id
    enum nested-name-specifier(opt) identifier
```

*class-key* 是 `class`、`struct` 或 `union`。**详述类型说明符**（elaborated type specifier）就是"带上 `struct`/`class`/`union`/`enum` 关键字的类型名"。它在 C++ 中有三个用途：

1. **前向声明**：`struct S;`；
2. **在声明中顺带引入类名**：`struct Node* next;`（若 `Node` 尚未声明）；
3. **引用被非类型名字隐藏的类名**：`struct stat st;`（POSIX 中 `stat` 既是函数又是结构体）。

¶1 组成名字：标识符，以及 *nested-name-specifier*、*simple-template-id* 中的名字。

### 单独成声明（¶2）

¶2 若一个声明**只由**详述类型说明符构成，那么它必须是显式特化、偏特化、显式实例化，或者是以下两种形式之一：

```text
class-key attribute-specifier-seq(opt) identifier ;
class-key attribute-specifier-seq(opt) simple-template-id ;
```

第一种把标识符声明为类名（**前向声明**）。第二种只能出现在显式特化或模板声明（偏特化）中。属性属于被声明的类或模板。

```cpp error
struct S;                  // OK: 前向声明
struct [[deprecated]] D;   // OK: 属性属于 D
struct N::Inner;           // error: 不能用限定名前向声明（N 也未声明，但即使声明了也不行）
enum E;                    // error: enum 不是 class-key；无作用域枚举的前向声明需要底层类型
enum class F : int;        // OK: 但这是 opaque-enum-declaration，不是详述类型说明符
```

为什么不能写 `struct N::Inner;`？带限定名的声明只能**重声明**已有的实体，而这种写法看起来像是要在 `N` 中引入新类——它要么是多余的（`Inner` 已存在），要么是错的（不能从外部向命名空间/类中添加成员）。

### 其他场合（¶3）

¶3 其他场合的详述类型说明符 E 不能带属性。若 E 只有标识符、没有 *nested-name-specifier*，且对该标识符的（非限定）查找**什么也没找到**，那么：E 不能以 `enum` 开头，它把标识符声明为一个**类名**，**目标作用域**是最近的外围**命名空间或块**作用域。

```cpp run ok
void f(struct Fwd* p);     // 参数作用域既不是命名空间也不是块 → Fwd 的目标作用域是全局命名空间
Fwd* r = nullptr;          // OK: Fwd 已声明于全局命名空间
struct List { struct Node* head; };   // 类作用域也跳过 → Node 声明在全局命名空间
Node* n = nullptr;         // OK
int main() { }
```

```cpp error
void g() { struct Q* q; (void)q; }   // Q 声明在 g 的块作用域中
Q* bad;                    // error: 全局作用域中没有 Q
```

!!! pitfall "与 C 不同"
    在 C 中，`void f(struct Fwd* p);` 中的 `struct Fwd` 只在**函数原型作用域**中可见，之后在文件作用域中定义 `struct Fwd` 会得到一个**不同的**类型，导致 `f` 不可调用（GCC 对此会警告 "declared inside parameter list"）。C++ 把它提到外围命名空间，避免了这个陷阱。同样，在类中 `struct Node* head;` 声明的 `Node` 不是嵌套类，而是外围命名空间中的类——想要嵌套类必须在类中单独写 `struct Node;`。

### 友元中的详述类型说明符（¶4）

¶4 作为 *friend-type-specifier* 的详述类型说明符只能是三种形式（无属性、无 `enum`）。第一种形式（`class-key nested-name-specifier(opt) identifier`）中的非限定查找**不考虑**最近外围命名空间或块作用域**之外**的作用域；而且**不绑定名字**——友元声明引入的类名，在外围作用域中不能被普通查找找到（见 [[dcl.friend]]）。Note 1：目标作用域中的 using 指令，若指向不包含于该作用域的命名空间，则被忽略。

```cpp run ok
namespace N {
    class X { friend class Helper; int secret = 7; };   // 声明 N::Helper（不绑定名字）
    class Helper { public: int peek(X& x) { return x.secret; } };   // 定义 N::Helper：同一个类
}
int main() { N::X x; return N::Helper{}.peek(x) - 7; }
```

### 隐藏的类名（¶5）

¶5（注）：名字查找见 [[basic.lookup.elab]]。详述类型说明符可以引用一个已被**非类型声明隐藏**的类名或枚举名——查找时只考虑类型：

```cpp run ok
struct T { int v; };
int main() {
    int T = 0;                  // 变量 T 隐藏了类名 T
    struct T obj{T};            // OK: struct T 仍找到类；{T} 中的 T 是变量
    return obj.v;
}
```

### 不能用 typedef 名（¶6）

¶6 若标识符或 *simple-template-id* 解析为类名或枚举名，详述类型说明符就像简单类型说明符一样引入它；若解析为 **typedef 名**（包括别名模板的特化），详述类型说明符非良构。

Note 3：因此在以类型参数 `T` 为参数的类模板中，`friend class T;` 非良构，而 `friend T;` 良构（[[class.friend]]）。

```cpp error
struct S { };
typedef S TS;
struct TS* p;               // error: TS 是 typedef 名
template<class T> struct W { friend class T; };   // error: T 是模板参数（视同 typedef 名）
```

### class-key 必须匹配（¶7）

¶7 详述类型说明符中的 *class-key* 或 `enum` 必须与名字所指的声明**种类一致**：`enum` 只能指枚举；`union` 只能指联合体；`class` 或 `struct` 只能指非联合体的类——但 `class` 和 `struct` **可以互换**。

```cpp run ok
enum class E { a, b };
enum E x = E::a;            // OK: 用 enum 引用有作用域枚举也可以（不写 class）
struct S { } s;
class S* p = &s;            // OK: class 与 struct 可以互换（Clang 给 -Wmismatched-tags 警告，见下）
int main() { return int(x) + (p != &s); }
```

```cpp error
union U { };
struct U* pu;               // error: union 必须用 union 引用
struct V;
enum V* pv;                 // error: V 是类不是枚举
```

!!! impl "MSVC 与 class/struct 互换"
    标准允许 `struct S` 与 `class S` 互换，但 MSVC 的名字修饰会编码 class-key（`class` 为 `V`、`struct` 为 `U`），所以在一个 TU 中声明为 `class S`、在另一个 TU 中定义为 `struct S`，可能在 MSVC 上导致链接错误。Clang 会给出 `-Wmismatched-tags` 警告提醒这一点（"this is valid, but may result in linker errors under the Microsoft C++ ABI"）。Itanium ABI 不编码 class-key。

---

## 9.2.9.9 类型拼接（[dcl.type.splice]）{{c++26}}

```text
splice-type-specifier:
    typename(opt) splice-specifier
    typename(opt) splice-specialization-specifier
```

这是 C++26 静态反射（[[P2996]]）的一部分：`[: r :]` 把一个反射值 `r`（类型为 `std::meta::info`）"拼接"回语法中。本节规定拼接作为**类型说明符**的情形。

!!! warning "尚无法本地验证"
    截至写作时，本机 Clang 未实现静态反射。本小节的例子取自标准并加以解释，未经编译器验证。

¶1 两条消歧规则：

- 紧跟 `::` 的 *splice-specifier*（或 *splice-specialization-specifier*）**永远不**被解释为类型拼接的一部分——`[:R:]::type` 中 `[:R:]` 是嵌套名说明符；
- 不带 `typename` 时，*splice-specifier* 只在**仅类型上下文**（type-only context，[[temp.res.general]]）中才被解释为类型拼接。其他地方，`[: r :]` 默认是**表达式**（[[expr.prim.splice]]）。

这与依赖名的 `typename` 规则如出一辙：编译器在解析时不知道 `r` 反射的是类型还是值，所以默认按表达式解析，需要类型时由程序员用 `typename` 标明。

```cpp
template<std::meta::info R> void tfn() {
    typename [:R:]::type m;       // OK: typename 作用于整个限定名 [:R:]::type
}
struct S { using type = int; };
void fn() {
    [:^^S::type:] *var;           // error: 这里 [: … :] 被解析为表达式，于是这是乘法
    typename [:^^S::type:] *var;  // OK: 声明 int* var
}
using alias = [:^^S::type:];      // OK: 别名声明的右侧是仅类型上下文
```

¶2 对 `typename(opt) splice-specifier` 形式，*splice-specifier* 必须指代**类型、类模板或别名模板**；类型拼接说明符指代同一实体。（指代类模板时，它就是 ¶3.3 所说的 CTAD 占位符。）

¶3 对 `typename(opt) splice-specialization-specifier` 形式（`[: r :]<args>`），*splice-specifier* 必须指代类模板或别名模板 T；结果是 T 对应于该模板实参列表的特化。

---

!!! history "历史与演进"
    - C++98：类型说明符包括基础类型关键字、类型名、详述类型说明符、`typename` 说明符、cv；去掉 C 的"隐式 int"。
    - C++11：`char16_t`、`char32_t`、`long long`、`decltype`、`auto`（占位符）。
    - C++17：CTAD（推导类类型占位符）。
    - C++20：`char8_t`；别名模板 CTAD；受约束占位符 `Concept auto`；弃用若干 volatile 用法。
    - C++26：包索引说明符（[[P2662]]）；类型拼接（[[P2996]]）。

!!! pitfall "常见误解"
    - "`const` 对象只要通过 `const_cast` 就能改"——编译能过，运行是 UB。
    - "`volatile` 能用于线程同步"——不能，用 `std::atomic`。
    - "`char` 就是 `signed char`"——它们是不同类型；`char` 的符号性由实现定义（ARM Linux 上通常无符号）。
    - "`class X` 和 `struct X` 必须一致"——标准不要求，但 MSVC ABI 会受影响。

!!! summary "小结"
    - 定义类型说明符 = 类型说明符 + 类定义 + 枚举定义；一般只能有一个，六条例外造就了 `unsigned long long int` 等写法。
    - 没有隐式 int：除构造/析构/转换函数外，必须有非 cv 类型说明符。
    - 修改 const 对象（生存期内）是 UB；mutable 成员不是 const 对象。通过非 volatile glvalue 访问 volatile 对象是 UB；volatile 访问的语义由实现定义。
    - 包索引 `Ts...[I]`：越界非良构；本身是包展开。
    - 详述类型说明符：可前向声明、可绕过隐藏、不能用 typedef 名、class-key 要匹配（class/struct 可互换）；首次出现时类名进入最近的命名空间/块作用域。
    - 类型拼接：非仅类型上下文中需要 `typename`。

!!! question "思考题 1"
    以下哪些是合法的类型？`unsigned`、`signed long long int`、`long signed`、`short unsigned int`、`long double long`、`unsigned signed char`。

<details markdown="1">
<summary>答案</summary>

`unsigned`（= unsigned int）、`signed long long int`（= long long）、`long signed`（= long）、`short unsigned int`（= unsigned short）都合法。`long double long` 不合法：`long` 与 `double` 组合一次后，第二个 `long` 无法再与 `long double` 组合（¶2.5、¶2.6 分别只允许一种组合，且没有 `long long double`）。`unsigned signed char` 不合法：`signed` 与 `unsigned` 互不组合。
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

是 `::S*`。`void f(struct S* p);` 中对 `S` 的非限定查找**找到了**全局的 `::S`（¶3 只在"查找什么也没找到"时才声明新类），所以参数类型是 `::S*`。随后在 `N` 中定义的 `N::S` 是另一个类，与 `f` 的参数类型无关。若删掉第一行的全局 `S`，那么 `struct S` 会在 `N` 中声明 `N::S`（最近的外围命名空间），之后的定义正好定义它，参数类型就是 `N::S*`。
</details>
