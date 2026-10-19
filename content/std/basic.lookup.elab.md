---
title: 详述类型说明符的查找
summary: struct X、class X、union X、enum X 中的名字只查找类型，同名的变量和函数被跳过；不带限定的写法找不到时会顺带声明一个新类，带限定的写法则必须找到已有的类型。
status: done
related: basic.lookup, dcl.type.elab, basic.lookup.qual, basic.lookup.unqual, class.friend, class.name
tags: 名字查找, 详述类型说明符
updated: 2026-10-19
---

!!! tldr
    - `struct X`、`enum X` 里的 `X` 只查找类型，所以能越过同名的变量或函数找到被挡住的类。
    - 不带限定的 `struct X*` 如果找不到 `X`，会在最近的外围命名空间或块作用域里顺带声明一个类，而不是在当前类里。
    - `enum X` 不能顺带声明枚举；带限定的 `struct N::X` 也从不声明新类型，找不到就是错误。
    - 关键字必须和类型的种类一致：`enum` 对枚举，`union` 对联合，`struct` 和 `class` 可以互换。

## 带关键字的类型名

```cpp run ok
#include <sys/stat.h>
int size_of(const char* path) {
    struct stat st;          // 函数 stat 挡住了类 stat，加上 struct 才能指类型
    if (stat(path, &st) != 0) return -1;
    return static_cast<int>(st.st_size);
}
```

POSIX 头文件里同时有类 `stat` 和函数 `stat`。同一作用域里，类名会被同名的函数或变量隐藏（[[basic.lookup#4]]），这是为了和 C 兼容。要指那个类，就得写 `struct stat`。

带了 `class`、`struct`、`union` 或 `enum` 关键字的类型名，叫做**详述类型说明符**（elaborated-type-specifier）。除了绕过隐藏，它还有两个用途：没有声明过的 `struct Node* next;` 会顺带声明类 `Node`；`struct X;` 和 `friend class Y;` 用来做前置声明和友元声明。

本节只有三段，规定其中的名字怎样查找。查找之后声明了什么、声明在哪里，由 [[dcl.type.elab]] 规定，这里一并讲。

## 不带限定：只查找类型（¶1）

¶1 关键字后面是一个标识符、且标识符后面不再跟 `::` 时，对它的查找是[[g:type-only-lookup|仅类型查找]]（type-only lookup，[[basic.lookup#4]]）：只考虑类型和特化为类型的模板。

注 1 说明，如果标识符后面跟 `::`，比如 `struct X::Y` 里的 `X`，它就属于 `X::` 前缀，按 [[basic.lookup.qual]] 查找；最后的 `Y` 按 ¶2 处理。

仅类型查找让非类型的声明完全不起作用。它不仅能绕过同一作用域里的变量或函数，还能越过内层作用域的同名变量，找到外层的类型：

```cpp run error
struct S { int m; };
void f() {
    int S = 0;                 // 对普通查找来说，局部变量 S 挡住了 ::S
    struct S s{};              // OK：仅类型查找跳过 int S，向外找到 ::S
    static_assert(sizeof(struct S) == sizeof(int));
    (void)S; (void)s;
}

namespace A { struct X {}; }
namespace B { int X; }
using namespace A;
using namespace B;
struct X* px;    // OK：B::X 不是类型，被跳过，得到 A::X
X* py;           // error: 普通查找同时找到 A::X 和 B::X，二义
```

`X* py` 二义，是因为 `A::X` 和 `B::X` 来自不同命名空间的搜索，类不会被另一处的变量隐藏（[[namespace.qual#4]]）。

仅类型查找还规定：同时找到一个类型别名和它代表的类型时，丢弃别名。[[dcl.type.elab#6]] 规定详述类型说明符解析成 typedef 名是非良构的，有了这条，只要能找到原类型，就不会因为碰巧也找到别名而出错。

### 找不到时顺带声明一个类

[[dcl.type.elab#3]] 规定，不带限定的标识符经无限定查找什么也没找到时：

- 不能用 `enum`，也就是不能这样顺带声明枚举。枚举的前置声明要写完整的不透明枚举声明（如 `enum E : int;`）；
- 它把这个标识符声明为类名，声明的位置是最近的外围命名空间或块作用域，不是类作用域。

```cpp run error
struct Outer {
    struct Inner* q;          // Inner 没找到，在全局声明 ::Inner
};
Inner* gi;                    // OK：::Inner

struct L {
    void g() {
        struct Fn* r = nullptr;   // 最近的外围块作用域：Fn 是 g 函数体里的局部类
        (void)r;
    }
};
Fn* bad;                      // error: 全局作用域没有 Fn

enum Color* pc;               // error: 不能用 enum 顺带声明枚举
```

`struct X;` 单独构成一条声明时是另一回事。按 [[dcl.type.elab#2]]，它在当前作用域（可以是类作用域）声明 `X`，这是普通的前置声明，不经过找不到再声明的过程。

### 友元只看到最近的外围命名空间

[[dcl.type.elab#4]] 对 `friend class Y;` 有额外的限制：无限定查找不考虑最近的外围命名空间（或块作用域）之外的作用域，而且这个声明不绑定名字。也就是说，只在类自身、外围类和最近的外围命名空间里找。找不到时，它指的是最近外围命名空间里一个尚未声明的类；在真正声明出现之前，这个名字仍然不可见。

## 带限定：必须已经存在（¶2）

¶2 如果详述类型说明符的最后一个名字是限定名（`struct N::X`、`class C::Inner`），查找同样只考虑类型；找不到已经声明过的类型名，就是非良构。

所以带限定的详述类型说明符从不声明新类型。声明需要一个目标作用域，而 `struct N::X*` 出现在 `N` 之外，不能从外面往别的命名空间或类里添加名字。要在 `N` 中前置声明 `X`，得写 `namespace N { struct X; }`。

## 标准例（¶3）

```cpp run error
struct Node {
    struct Node* Next;            // OK：找到 Node 的注入类名
    struct Data* Data;            // OK：没找到 Data，在全局声明 ::Data，同时声明成员 Data
};

struct Data {
    struct Node* Node;            // OK：仅类型查找找到 ::Node
    friend struct ::Glob;         // error: Glob 未声明，限定名不能引入类型
    friend struct Glob;           // OK：指全局作用域中尚未声明的 Glob
};

struct Base {
    struct Data;                  // OK：单独成声明，声明嵌套类 Base::Data
    struct ::Data*     thatData;  // OK：::Data
    struct Base::Data* thisData;  // OK：嵌套的 Data
    friend class ::Data;          // OK：全局 Data 是友元
    friend class Data;            // OK：嵌套的 Data 是友元
    struct Data { };              // 定义嵌套的 Data
};

struct Data;                      // OK：重新声明全局 Data
struct ::Data;                    // error: 不能用限定名引入类型
struct Base::Data;                // error: 同上
struct Base::Datum;               // error: Datum 未声明
struct Base::Data* pBase;         // OK：嵌套的 Data
```

有三处值得细看。

`struct Data* Data;` 一次做了两件事：详述类型说明符声明了全局类 `::Data`，声明符声明了成员变量 `Node::Data`。此后在 `Node` 里，普通查找找到的 `Data` 是成员变量，要指类型就得写 `struct Data`。

`struct ::Data;` 和 `struct Base::Data;` 即使类型已经存在也是错的。原因不在查找，而是 [[dcl.type.elab#2]] 不允许单独成声明的详述类型说明符带 `X::` 前缀（显式特化、显式实例化等除外）。这样的声明也没有意义，因为不能把声明放进别的作用域。

在 `Base` 里写 `friend class Data;` 时，类作用域里已经有 `Base::Data`。友元查找先看类自身，所以它指的是嵌套类。

## 关键字必须和种类一致

[[dcl.type.elab#7]] 规定，关键字必须和名字所指的声明一致：`enum` 对枚举，`union` 对联合，`class` 或 `struct` 对非联合的类，后两者可以互换。

```cpp run error
enum class E { a, b };
enum E x = E::a;                  // OK：作用域枚举也用 enum（不写 enum class）详述
struct S { } s;
class S* p = &s;                  // OK：struct 和 class 可以互换
union U { };
struct U* pu;                     // error: U 是联合
```

!!! warning "struct 和 class 混用的 ABI 隐患"
    标准允许 `struct` 和 `class` 互换，但 MSVC 的名字修饰区分两者。前置声明写 `class X;`、定义写 `struct X {}`，在 MSVC 上可能导致链接时找不到符号。Itanium ABI 不区分两者。Clang 对这种混用给出 `-Wmismatched-tags` 警告，提醒的正是这个问题。

## 模板参数不能加关键字

[[dcl.type.elab#6]] 注 3 指出，在以 `T` 为类型模板参数的类模板中，`friend class T;` 非良构，因为 `T` 在这里相当于 typedef 名；`friend T;` 则合法（[[class.friend]]，C++11 起）。

```cpp run error
template<class T> struct TT {
    friend T;          // OK
    friend class T;    // error
};
```

本机 Clang 23 拒绝第二个声明，诊断说的是它遮蔽了模板参数，与标准给出的理由不同，但结论一致。

!!! history "历史与演进"
    - C++98：本节规则基本成形，包括找不到时在最近的外围命名空间或块作用域里声明类。
    - C++11：引入作用域枚举和不透明枚举声明，以及 `friend T;`。
    - C++23：[[P1787R6]] 把仅类型查找提升为 [basic.lookup.general] 中的通用概念，加上同时找到别名和原类型时丢弃别名的规则；本节缩减为三段，声明的语义集中到 [dcl.type.elab]。

## 常见误解

!!! pitfall "类里的 struct X* 会声明嵌套类"
    `struct Outer { struct Inner* q; };` 声明的是命名空间作用域的 `Inner`，不是 `Outer::Inner`。之后在别处定义 `struct Outer::Inner {}` 会出错，因为两者不是同一个类。想要嵌套类，先在类里写 `struct Inner;`。

!!! pitfall "函数体里顺带声明的类在函数外可见"
    在函数体里写 `struct Impl* p;`，声明的是局部类。函数外看不见它，也不能在函数外定义它。

## 思考题

!!! question "思考题"
    ```cpp
    namespace N {
        struct A {
            struct B* p;
        };
    }
    struct B { };
    N::B* q;   // (1)
    ::B* r;    // (2)
    ```
    (1)、(2) 合法吗？

<details markdown="1">
<summary>答案</summary>

`struct B* p;` 在 `A`、`N`、全局依次查找类型 `B`。全局的 `struct B` 在它之后才声明，所以什么也没找到，于是在最近的外围命名空间 `N` 中声明 `N::B`。

(1) 合法，`q` 指向不完整类型 `N::B`。(2) 也合法，但 `::B` 和 `N::B` 是两个不同的类，`A::p` 不能指向一个全局 `B` 对象。本机 Clang 23 对 `a.p = &b`（`b` 是全局 `B`）报告指针类型不兼容。
</details>

## 小结

| 情形 | 查找 | 找不到时 |
|---|---|---|
| `struct X`（不带限定，不单独成声明） | 仅类型，无限定查找 | 在最近的外围命名空间或块作用域声明类 `X` |
| `enum X`（不带限定） | 仅类型 | 非良构 |
| `struct X;`（单独成声明） | 不查找 | 在当前作用域声明 `X` |
| `friend struct X;` | 仅类型，不超出最近的外围命名空间 | 指那个命名空间里的 `X`，不绑定名字 |
| `struct N::X`（带限定） | 仅类型，限定查找 | 非良构，从不声明新类型 |
| 同时找到别名和原类型 | 丢弃别名 | |
| 只找到 typedef 名 | | 非良构 |
