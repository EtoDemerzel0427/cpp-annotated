---
title: 详述类型说明符的查找
summary: struct X / class X / union X / enum X 中的名字做"仅类型查找"——忽略变量、函数等非类型声明；限定形式必须找到已声明的类型，非限定形式找不到时则声明一个新类。
status: done
related: basic.lookup, dcl.type.elab, basic.lookup.qual, basic.lookup.unqual, class.friend, class.name
tags: 名字查找, 详述类型说明符
updated: 2026-10-17
---

**详述类型说明符**（elaborated-type-specifier）是带了 *class-key*（`class`/`struct`/`union`）或 `enum` 关键字的类型名：`struct stat`、`class std::string`、`enum Color`。它在 C++ 里有三个用途：

1. **绕过隐藏**：同一作用域里有同名的变量或函数时，用 `struct X` 指名被隐藏的类型（C 兼容，见 [[basic.lookup#4]]）；
2. **顺带声明**：`struct Node* next;`——若 `Node` 尚未声明，这同时声明了一个类（[[dcl.type.elab#3]]）；
3. **前置声明与友元**：`struct X;`、`friend class Y;`。

本节只有三段，规定这些名字怎么**查找**；查找之后"声明了什么、声明到哪里"由 [[dcl.type.elab]] 规定。两者要配合着读。

## 非限定形式：仅类型查找（¶1）

¶1 若 *class-key* 或 `enum` 后跟一个**不再后跟 `::`** 的*标识符*，对该标识符的查找是**仅类型查找**（type-only，[[basic.lookup#4]]）：只考虑类型声明与特化是类型的模板。

注 1：详述类型说明符的识别一般取决于后面的记号——`struct X::Y` 中 `X` 后跟 `::`，那么 `X` 属于 *nested-name-specifier*，按 [[basic.lookup.qual]] 查找（只考虑命名空间与类型），终端名 `Y` 按 ¶2 处理。

仅类型查找的效果是：**非类型声明完全透明**。它不仅能绕过同一作用域里隐藏类名的变量/函数，还能"穿过"内层作用域里的同名变量，找到外层的类型：

```cpp run error
struct S { int m; };
void f() {
    int S = 0;                       // 局部变量 S 隐藏了 ::S（对普通查找而言）
    struct S s{};                    // OK：仅类型查找忽略局部 int S，继续往外找到 ::S
    static_assert(sizeof(struct S) == sizeof(int));
    (void)S; (void)s;
}

namespace A { struct X {}; }
namespace B { int X; }
using namespace A;
using namespace B;
struct X* px;    // OK：B::X 不是类型，被忽略 → A::X
X* py;           // error: 普通查找同时找到 A::X 与 B::X（不同搜索，类不被丢弃）→ 二义
```

仅类型查找还规定：同时找到类型别名与其底层类型时，**丢弃别名**。这与 [[dcl.type.elab#6]]"详述类型说明符解析为 typedef 名则非良构"配合——只要能找到原类型，就不会因为碰巧也找到了别名而出错（例子见 [[basic.lookup]]）。

### 找不到时：声明新类

若非限定的标识符经（仅类型的）无限定查找**什么也没找到**，[[dcl.type.elab#3]] 规定：

- 不能用 `enum` 关键字（不能这样"顺带"声明枚举——枚举的前置声明必须写完整的 *opaque-enum-declaration*，带底层类型）；
- 它把该标识符声明为一个**类名**，其目标作用域是**最近的外围命名空间或块作用域**——注意**不是类作用域**。

```cpp run error
struct Outer {
    struct Inner* q;          // Inner 没找到 → 在最近的外围命名空间（全局）声明 ::Inner
};
Inner* gi;                    // OK：::Inner

struct L {
    void g() {
        struct Fn* r = nullptr;   // 最近的外围块作用域：Fn 是 g 的函数体中的局部类
        (void)r;
    }
};
Fn* bad;                      // error: Fn 不在全局作用域中

enum Color* pc;               // error: 不能用 enum 顺带声明枚举
```

例外：若详述类型说明符**单独构成**声明（`struct X;`），按 [[dcl.type.elab#2]] 它在**当前**作用域声明 X（可以是类作用域），这是普通的前置声明，并不先做"找不到才声明"的查找。

### 友元：只看最近的外围命名空间

`friend class Y;` 的查找有额外限制（[[dcl.type.elab#4]]）：非限定查找**不考虑包含最近外围命名空间（或块作用域）的那些作用域**，且不绑定名字。即：只在类自身、外围类、以及最近的外围命名空间里找；找不到就把它当作最近外围命名空间中的类的友元声明（但名字不可见，直到有真正的声明）。

## 限定形式：必须已存在（¶2）

¶2 若详述类型说明符的终端名是**限定名**（`struct N::X`、`class C::Inner`），查找也是仅类型的；若没有找到**先前声明的**类型名，详述类型说明符非良构。

换句话说，**限定的详述类型说明符永远不会声明新类型**。理由很直接：声明需要一个目标作用域，而 `struct N::X*` 出现在 N 之外，不能"远程"往别的命名空间或类里塞一个新名字。要在 N 中前置声明 X，得写 `namespace N { struct X; }`。

## 标准例逐行解读（¶3）

```cpp run error
struct Node {
    struct Node* Next;            // OK：找到 Node 的注入类名
    struct Data* Data;            // OK：Data 没找到 → 在全局声明 ::Data，并声明成员 Data
};

struct Data {
    struct Node* Node;            // OK：仅类型查找找到 ::Node（成员名 Node 在此之后才声明）
    friend struct ::Glob;         // error: Glob 未声明，限定名不能引入类型
    friend struct Glob;           // OK：指最近外围命名空间（全局）中尚未声明的 Glob
};

struct Base {
    struct Data;                  // OK：单独成声明 → 声明嵌套类 Base::Data
    struct ::Data*     thatData;  // OK：::Data
    struct Base::Data* thisData;  // OK：嵌套的 Data
    friend class ::Data;          // OK：全局 Data 是友元
    friend class Data;            // OK：嵌套的 Data 是友元（类作用域中先找到）
    struct Data { };              // 定义嵌套的 Data
};

struct Data;                      // OK：重声明全局 Data
struct ::Data;                    // error: 不能用限定名"引入"类型（[dcl.type.elab]）
struct Base::Data;                // error: 同上
struct Base::Datum;               // error: Datum 未声明
struct Base::Data* pBase;         // OK：指嵌套的 Data
```

几个值得停下来想的地方：

- **`struct Data* Data;`** 同时做了两件事：详述类型说明符声明全局类 `::Data`，声明符声明成员变量 `Node::Data`。之后在 Node 内部，普通查找 `Data` 找到的是成员变量；要指类型就得写 `struct Data`。
- **`struct ::Data;`、`struct Base::Data;`** 即使所指的类型已经存在也是错误的——不是查找失败，而是 [[dcl.type.elab#2]] 不允许单独成声明的详述类型说明符带有 *nested-name-specifier*（显式特化/实例化等除外）。这样的声明没有意义（不能"重声明到别处"）。
- **`friend class Data;`** 在 Base 中，类作用域里已经有 `Base::Data`，所以指的是嵌套类——友元查找先看类自身。

## 种类必须一致

[[dcl.type.elab#7]]：*class-key* 或 `enum` 必须与所指声明的种类一致——`enum` 指枚举，`union` 指联合，`class`/`struct` 指非联合类（二者可以互换）。

```cpp run error
enum class E { a, b };
enum E x = E::a;                  // OK：作用域枚举也可以用 enum（而非 enum class）详述
struct S { } s;
class S* p = &s;                  // OK：struct/class 互换
union U { };
struct U* pu;                     // error: U 是联合
```

!!! warning "struct/class 混用的 ABI 隐患"
    标准允许 `struct`/`class` 互换，但 MSVC 的名字修饰区分二者（`class` 与 `struct` 在修饰名中编码不同），前置声明写 `class X;`、定义写 `struct X {}` 会导致链接时找不到符号，MSVC 为此有专门的警告。Itanium ABI 不区分。

## 模板参数不能用 class-key 详述

[[dcl.type.elab#6]] 注 3：在以 `T` 为类型模板参数的类模板中，`friend class T;` 非良构（`T` 解析到模板参数，模板参数在此视同 typedef 名），而 `friend T;` 合法（[[class.friend]]，C++11 起）。

```cpp run error
template<class T> struct TT {
    friend T;          // OK
    friend class T;    // error
};
```

!!! impl "实现视角"
    Clang 对"类型被同作用域的函数隐藏"给出专门提示，要求加 `struct` 标签（见 [[basic.lookup]] 中 `stat` 的例子）；对 `enum` 的顺带声明报告"ISO C++ 禁止对 enum 类型的前向引用"（这是 C 中的一个扩展，C++ 不允许）。

!!! history "历史与演进"
    - **C++98**：本节规则基本成形，包括"未找到则在最近外围命名空间/块作用域声明"。
    - **C++11**：作用域枚举与 *opaque-enum-declaration*；`friend T;` 简单友元声明。
    - **C++23**：P1787R6 把"仅类型查找"提为 [basic.lookup.general] 中的通用概念，并加上"同时找到别名与底层类型时丢弃别名"的规则；本节缩为三段，声明语义集中到 [dcl.type.elab]。

## 陷阱

!!! pitfall "以为 struct X* 在类里会声明嵌套类"
    `struct Outer { struct Inner* q; };` 声明的是**全局**（命名空间作用域）的 `Inner`，不是 `Outer::Inner`。之后若在别处定义 `struct Outer::Inner {}`，会出错——两者不是同一个类。想要嵌套类，先在类内写 `struct Inner;`。

!!! pitfall "顺带声明的位置在块作用域"
    在函数体内写 `struct Impl* p;` 声明的是局部类，函数外看不见，也不能在函数外定义它。

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

`struct B* p;` 在 A 中查找 B（仅类型）：A、N、全局都还没有 B（全局的 `struct B` 在其后），什么也没找到，于是在**最近的外围命名空间 N** 中声明 `N::B`。所以 (1) 合法（指向不完整类型 `N::B` 的指针），(2) 也合法，但 `::B` 与 `N::B` 是**两个不同的类**——`A::p` 不能指向一个全局 `B` 对象。
</details>

## 小结

| 情形 | 查找 | 找不到时 |
|---|---|---|
| `struct X`（非限定，非单独声明） | 仅类型，无限定查找 | 在最近外围命名空间/块作用域声明类 X |
| `enum X`（非限定） | 仅类型 | 非良构 |
| `struct X;`（单独声明） | 不需要 | 在当前作用域声明 X |
| `friend struct X;` | 仅类型，不超出最近外围命名空间 | 指那个命名空间中的 X（不绑定名字） |
| `struct N::X`（限定） | 仅类型，限定查找 | 非良构，永不声明新类型 |
| 别名与原类型同时找到 | 丢弃别名 | — |
| 只找到 typedef 名 | — | 非良构 |
