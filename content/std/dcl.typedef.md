---
title: typedef 说明符
summary: typedef 与别名声明引入的是类型别名而不是新类型；typedef 的组合限制；typedef 名不能用于详述类型说明符、类定义和构造/析构函数声明；用于链接目的的 typedef 名及其 C++20 限制
status: done
papers: P1766R1
related: dcl.pre, dcl.spec, basic.link, temp.alias, dcl.type.elab, basic.scope.pdecl
tags: 声明, 类型别名, typedef, 链接
updated: 2026-10-17
---

`typedef` 和 `using X = ...;` 都声明**类型别名**（*type alias*），也就是给一个已有类型起另一个名字。标准反复强调一点：**typedef 名不引入新类型**。`typedef int Meters;` 之后，`Meters` 和 `int` 是同一个类型，可以互相赋值，重载时也视为相同的参数类型。如果想要强类型别名，必须定义一个新的类或枚举。

本节还包含一个与 ABI 紧密相关的概念，即**用于链接目的的 typedef 名**（*typedef name for linkage purposes*）。它回答的问题是：在 C 风格的 `typedef struct { ... } S;` 中，无名结构体如何获得一个可以跨翻译单元匹配的名字。

## typedef 说明符（¶1）

¶1 含有 `typedef` 的声明声明的是类型别名。它有以下约束：

1. `typedef` 只能和定义类型说明符（*defining-type-specifier*：类型说明符、类定义、枚举定义）组合，不能和 `static`、`inline`、`constexpr`、`friend` 等其他任何说明符组合；
2. 不能用于参数声明的说明符序列；
3. 不能用于函数定义的说明符序列；
4. 有 `typedef` 而没有声明符的声明非良构（`typedef int;`）。

用 `typedef` 声明的名字成为 *typedef-name*，它的底层实体是与该标识符关联的类型，即按 [[dcl.decl]] 的声明符规则包装之后的类型。

```cpp run ok
#include <type_traits>
typedef int MILES, *KLICKSP;                 // MILES = int，KLICKSP = int*
typedef int ARR[3], (*FP)(MILES);            // 数组类型、函数指针类型
MILES distance = 0;
extern KLICKSP metricp;
static_assert(std::is_same_v<MILES, int>);   // 不是新类型
void f(int);
void f(MILES);                               // 同一个函数的重声明，不是重载
int main() { }
```

和普通声明一样，`typedef` 是说明符，作用于整个声明；`*`、`[3]`、`(*)(…)` 是声明符，只作用于各自的名字。可以这样理解 typedef：在一个变量声明前面加上 typedef，变量名就变成了该变量类型的名字。按这个读法不会出错。

```cpp error
typedef static int SI;            // error: typedef 不能与存储类说明符组合
typedef inline int II;            // error: 也不能与 inline 组合
void g(typedef int x);            // error: 不能用于参数声明
typedef int h(int) { return 0; }  // error: 不能用于函数定义
```

!!! note "typedef 的重复声明"
    在同一个命名空间作用域或块作用域中，可以用 typedef 把一个名字再次声明为同一类型的别名（`typedef int I; typedef int I;` 合法），但不能让它指向不同的类型。在类作用域中，重复的成员 typedef 是非良构的（[[class.mem.general#8]]：成员不能在类定义中声明两次）。

## 别名声明（¶2）

¶2 *alias-declaration* `using 标识符 属性(opt) = 定义类型标识;` 也声明类型别名，语义与 `typedef` 完全相同。`using` 后面的标识符不参与名字查找，直接成为 typedef 名；标识符后面的属性属于这个类型别名。

`using` 形式有两个优点：

- 可读性更好。名字在左、类型在右，函数指针类型一目了然：`using handler_t = void (*)(int);` 对比 `typedef void (*handler_t)(int);`。
- 可以模板化。*alias-declaration* 可以作为模板声明中的 *declaration*，构成**别名模板**（[[temp.alias]]），`typedef` 做不到。

```cpp run ok
#include <vector>
using handler_t = void (*)(int);
extern handler_t ignore;
extern void (*ignore)(int);       // OK: 同一个变量的重声明——类型完全相同
template<class T> using Vec = std::vector<T>;   // 别名模板
using Old [[deprecated("use New")]] = int;      // 属性作用于别名本身
int main() { Vec<int> v; return int(v.size()); }
```

再看声明点。别名声明引入的名字在整个 *alias-declaration* 之后才可见（[[basic.scope.pdecl]]），所以不能在自己的定义里递归引用自己：

```cpp error
template<class T> struct P { };
using cell = P<cell*>;            // error: cell 在这里还没被声明
```

换成 `typedef` 也一样，`typedef P<cell*> cell;` 同样不行：typedef 名的声明点在其完整声明符之后，而 `P<cell*>` 位于声明符之前。要表达递归类型，只能借助类：`struct cell { P<cell*> p; };`。

¶2 最后一句规定，如果 *alias-declaration* 是模板声明的一部分（即别名模板），它的类型标识中不能定义类或枚举。

```cpp error
template<class T> using Box = struct { T t; };   // error: 别名模板中不能定义类
```

为什么？别名模板的每个特化都等同于其类型标识所指的类型。如果类型标识里定义了一个类，那么 `Box<int>` 与 `Box<int>` 是不是同一个类、这个类属于哪个作用域、链接名是什么，都无从规定。非模板的 `using A = struct { int t; };` 没有这个问题，是合法的。

## typedef 名与类名的区别（¶3）

¶3 *simple-template-id* 只有在其模板名指向别名模板或类型模板模板参数时，才是 *typedef-name*；指向类模板特化的 *simple-template-id* 是 *class-name*。

Note 1 列出了 typedef 名不能出现的四个位置：

| 位置 | 例子 | 原因 |
|---|---|---|
| *elaborated-type-specifier* | `struct T* p;`（T 是 typedef） | 详述类型说明符要求的是类的名字（[[dcl.type.elab#6]]） |
| 类定义 | `struct T { };` | 不能通过别名来定义类 |
| 构造函数声明 | `T();`（类内，T 是类的别名） | 构造函数用注入类名声明（[[class.ctor.general]]） |
| 析构函数声明 | `~T();` | 同上（析构函数名的查找另有规则，[[class.dtor]]） |

```cpp error
struct S { S(); ~S(); };
typedef struct S T;
S a = T();                // OK: T 作为类型使用没有问题
struct T* p;              // error: 详述类型说明符中不能用 typedef 名
struct T { };             // error: 不能通过 typedef 名定义类
```

```cpp run ok
struct S { S(); };
typedef S T;
T::S() { }                // OK: 通过 typedef 名限定，但构造函数名本身用的是 S
int main() { T t; (void)t; }
```

## 用于链接目的的 typedef 名（¶4）

¶4 如果无名类或无名枚举 C 是在一个 typedef 声明中定义的，那么该声明中第一个类型为 C 的 typedef 名就是 C 的用于链接目的的 typedef 名（[[g:typedef-name-for-linkage]]，[[basic.link]]）。

!!! std
    An unnamed class or enumeration C defined in a typedef declaration has the first *typedef-name* declared by the declaration to be of type C as its *typedef name for linkage purposes*.

为什么需要这个概念？无名类没有名字，按理说也就没有链接，无法在多个 TU 之间被识别为同一个类型。但 C 头文件中大量存在这样的写法：

```cpp
typedef struct { int x, y; } Point;
void draw(Point p);       // 外部链接的函数，参数类型是一个无名结构体
```

如果 `Point` 所指的无名结构体没有链接，`draw` 就无法在不同 TU 之间匹配，因为它的 mangled 名中必须编码参数类型。所以标准规定，这个无名类借用 typedef 名 `Point` 作为自己的名字参与链接（[[basic.link#4]] 的 ¶4.3、¶4.4），mangled 名中使用的也是 `Point`（Itanium ABI 下 `draw` 修饰为 `_Z4draw5Point`）。

有几个细节需要注意：

- 起作用的是第一个类型为 C 的 typedef 名。`typedef struct { } *ps, S;` 中 `ps` 的类型是 `C*` 而不是 `C`，所以链接名是 `S`。
- 只有在 typedef 声明中定义的类才有这个名字。`typedef decltype([]{}) C;` 并不定义闭包类型（闭包类型由 lambda 表达式定义），所以闭包类型没有用于链接目的的 typedef 名（Note 2）。
- 无名枚举还有另一种获得链接名的方式，即使用它的第一个枚举项（[[dcl.enum]]）。

!!! lawyer "别名声明也算吗？"
    ¶4 字面上说的是 typedef 声明（[[dcl.pre#8]]：说明符序列含 `typedef` 的声明），而 `using A = struct { … };` 是 *alias-declaration*。不过 ¶2 规定别名声明与 typedef 声明的语义相同，实现（Clang、GCC）也同样认为它给出了用于链接目的的名字。例如在 Clang 下，`using A = struct { int t; }; void f(A) { }` 中 `f` 的符号是 `_Z1f1A`。

## C++20 的限制（¶5）

¶5 具有用于链接目的的 typedef 名的无名类不得：

- ¶5.1 声明非静态数据成员、成员枚举、成员类以外的成员（也就是说，不能有成员函数、静态数据成员、成员 typedef、`static_assert` 等）；
- ¶5.2 有基类或默认成员初始化器；
- ¶5.3 包含 lambda 表达式；

并且它的所有成员类也必须递归地满足这些要求。

```cpp error
typedef struct {
    int f() { return 0; }   // error: 成员函数
} X;
struct B { };
typedef struct : B { } Y;   // error: 基类
typedef struct { int m = 1; } Z;          // error: 默认成员初始化器
typedef struct { decltype([]{}) m; } W;   // error: 包含 lambda
```

```cpp run ok
typedef struct {
    int x, y;
    enum Kind { a, b } kind;      // OK: 成员枚举
    struct Inner { int z; } in;   // OK: 成员类（自身也满足要求）
} CStyle;
int main() { CStyle c{}; return c.x; }
```

!!! note "动机：先有鸡还是先有蛋"
    编译器处理 `typedef struct { ... } X;` 时，读到类体的时候还不知道后面会出现 typedef 名 `X`，也就不知道这个类有没有链接、链接名是什么。有些成员需要知道所在类的身份才能处理，例如成员函数的 mangled 名包含类名，lambda 闭包类型的 ODR 身份依赖于外围实体。如果类体里有成员函数、lambda、默认成员初始化器这类东西，编译器就必须回过头修改之前的决定。对模块来说，这还会影响一个声明能否导出。C++20 的 [[P1766R1]] 因此直接把这种写法限制为 C 兼容的结构体，而兼容 C 正是这个特性存在的唯一理由。

!!! impl "Clang 只给警告"
    对违反 ¶5 的代码，Clang 给出 `-Wnon-c-typedef-for-linkage` 警告（"anonymous non-C-compatible type given name for linkage purposes by typedef declaration; add a tag name here"）并继续编译，以兼容大量旧代码。按标准，这些代码都是非良构的。修复方法就是提示里说的：给结构体加一个名字（`typedef struct X { ... } X;`），它就不再是无名类，¶5 也就不再适用。

!!! history "历史与演进"
    - C++98：`typedef`。用于链接目的的 typedef 名已经存在，对无名类的内容没有额外限制。
    - C++11：*alias-declaration*（`using X = …;`）和别名模板。
    - C++20：[[P1766R1]] 引入 ¶5 的限制（与模块的设计一并考虑）。C++20 还允许 lambda 出现在不求值操作数中，所以才有了 `typedef decltype([]{}) C;` 这种写法，Note 2 说明它不会给闭包类型带来链接名。

!!! pitfall "常见误解"
    - 误以为 typedef 是宏替换。实际上不是：`typedef char* P; const P p;` 中 `p` 的类型是 `char* const`，而不是 `const char*`（[[dcl.spec.general#3]]）。
    - 误以为 `using` 比 `typedef` 能做更多事。除了别名模板，两者完全等价；反过来，`typedef` 能一次声明多个别名，`using` 做不到。
    - 误以为 typedef 可以创建强类型。它不能，`typedef int Meters; typedef int Seconds;` 声明的两个名字是同一个类型。

!!! summary "小结"
    - typedef 与 *alias-declaration* 声明类型别名，不引入新类型。
    - `typedef` 只能与类型说明符组合，不能用于参数声明和函数定义。
    - 别名声明所引入名字的声明点在整个声明之后；别名模板中不能定义类或枚举。
    - typedef 名不能用于 `struct T`、类定义、构造/析构函数声明。
    - `typedef struct { … } S;` 中 `S` 是无名结构体的链接名；C++20 起该结构体必须与 C 兼容（无成员函数、无基类、无默认成员初始化器、无 lambda）。

!!! question "思考题"
    下面的代码在 C++20 中是否良构？若不良构，最小的修改是什么？

    ```cpp
    typedef struct {
        static constexpr int version = 1;
        int data;
    } Header;
    ```

<details markdown="1">
<summary>答案</summary>

非良构，因为静态数据成员不属于非静态数据成员、成员枚举或成员类（¶5.1）。（事实上无名类本来就不能有静态数据成员，见 [[class.static.data#2]]，Clang 对此直接报错。）最小的修改是给结构体命名：`typedef struct Header { ... } Header;`，或者直接写 `struct Header { ... };`。有名字的类不受 ¶5 约束。如果必须与 C 共享这个结构体，就把 `version` 移出去，改用宏或命名空间作用域的常量。
</details>
