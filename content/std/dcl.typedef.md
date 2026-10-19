---
title: typedef 说明符
summary: typedef 和 using 别名声明给已有类型起另一个名字，不产生新类型；本节还规定 typedef 的组合限制、typedef 名不能出现的位置，以及 typedef struct { … } S; 中无名结构体怎样借用 S 参与链接。
status: done
papers: P1766R1
related: dcl.pre, dcl.spec, basic.link, temp.alias, dcl.type.elab, basic.scope.pdecl
tags: 声明, 类型别名, typedef, 链接
updated: 2026-10-19
---

!!! tldr
    - `typedef` 和 `using X = …;` 都声明类型别名：别名和原类型是同一个类型，不能用它做强类型。
    - `typedef` 只能与类型说明符组合，不能用于形参声明和函数定义；`using` 形式还能写成别名模板。
    - typedef 名不能用在 `struct T`、类定义、构造函数和析构函数的声明里。
    - `typedef struct { … } S;` 中的无名结构体借用 `S` 作为链接用的名字。C++20 起这样的结构体只能含 C 兼容的成员。

## 别名不是新类型（¶1）

```cpp run ok
#include <type_traits>
typedef int MILES, *KLICKSP;                 // MILES 是 int，KLICKSP 是 int*
typedef int ARR[3], (*FP)(MILES);            // 数组类型、函数指针类型
MILES distance = 0;
extern KLICKSP metricp;
static_assert(std::is_same_v<MILES, int>);   // 同一个类型
void f(int);
void f(MILES);                               // 同一个函数的重声明，不是重载
int main() { }
```

¶1 说明符序列含 `typedef` 的声明，声明的是**类型别名**（type alias）。这样声明的名字叫 *typedef-name*，它代表的类型就是同一个声明符在普通声明里会得到的类型。读 typedef 有一个简单的办法：把 `typedef` 去掉，剩下的是一个变量声明；加上 `typedef`，变量名就变成了这个变量类型的名字。所以上面 `*KLICKSP` 里的 `*` 只作用于 `KLICKSP`，`MILES` 仍然是 `int`。

typedef 名不像类声明（[[class.name]]）或枚举声明（[[dcl.enum]]）那样引入新类型。`typedef int Meters; typedef int Seconds;` 之后，两个名字都是 `int`，可以互相赋值，重载时也不加区分。需要强类型时，要定义一个新的类或枚举。

¶1 还规定了 `typedef` 能出现在哪里：

- 只能和定义类型说明符（*defining-type-specifier*：类型说明符、类定义、枚举定义）组合，不能和 `static`、`inline`、`constexpr`、`friend` 等任何其他说明符组合；
- 不能用于形参声明，也不能用于函数定义；
- 有 `typedef` 却没有声明符的声明（`typedef int;`）非良构。

```cpp error
typedef static int SI;            // error: 不能与存储类说明符组合
typedef inline int II;            // error: 也不能与 inline 组合
void g(typedef int x);            // error: 不能用于形参声明
typedef int h(int) { return 0; }  // error: 不能用于函数定义
```

对 `typedef int;`，本机 Clang 23 只给一条 `-Wmissing-declarations` 警告。警告也是诊断，满足标准的要求。

!!! note "重复的 typedef"
    在命名空间作用域或块作用域中，可以用 typedef 把一个名字再声明一次，只要指向同一类型（`typedef int I; typedef int I;` 合法）。在类定义里重复声明同一个成员 typedef 则非良构，因为类成员不能在类定义中声明两次（[[class.mem.general#8]]）。

## 别名声明（¶2）

```cpp run ok
#include <vector>
using handler_t = void (*)(int);
extern handler_t ignore;
extern void (*ignore)(int);         // OK: 同一个变量的重声明，类型相同
template<class T> using Vec = std::vector<T>;   // 别名模板
using Old [[deprecated("use New")]] = int;      // 属性作用于别名本身
int main() { Vec<int> v; return int(v.size()); }
```

¶2 **别名声明**（*alias-declaration*）`using 标识符 属性(可选) = 类型;` 声明的类型别名与 `typedef` 的语义完全相同。`using` 后面的标识符不做名字查找，直接成为 typedef 名；紧跟在标识符后面的属性属于这个别名。

`using` 形式有两个好处。一是名字在左、类型在右，函数指针类型更容易读：`using handler_t = void (*)(int);` 对比 `typedef void (*handler_t)(int);`。二是可以放进模板声明，成为**别名模板**（[[temp.alias]]），`typedef` 做不到。反过来，`typedef` 能在一条声明里定义多个别名，`using` 不能。

别名声明引入的名字到整个声明结束才可见（[[basic.scope.pdecl]]），所以别名不能在定义里引用自己：

```cpp error
template<class T> struct P { };
using cell = P<cell*>;            // error: 这里还找不到 cell
```

换成 `typedef P<cell*> cell;` 也一样，因为 `cell` 的声明点在它的声明符之后，而 `P<cell*>` 在声明符之前。要表达递归类型，只能借助类：`struct cell { P<cell*> p; };`。

¶2 最后一句规定，别名模板的类型里不能定义类或枚举：

```cpp error
template<class T> using Box = struct { T t; };   // error: 别名模板中不能定义类
```

别名模板的每个特化都等于它所指的类型。如果那里定义了一个类，`Box<int>` 和 `Box<long>` 各自是哪个类、属于哪个作用域、链接名是什么，都无从规定。非模板的 `using A = struct { int t; };` 没有这个问题，是合法的。

## typedef 名不能出现的位置（¶3）

```cpp error
struct S { S(); ~S(); };
typedef struct S T;
S a = T();                // OK: 把 T 当类型用没有问题
struct T* p;              // error: 详述类型说明符中不能用 typedef 名
struct T { };             // error: 不能通过 typedef 名定义类
```

¶3 注 1 列出了 typedef 名不能用来指代类的四个位置：

| 位置 | 例子（`T` 是 typedef 名） | 说明 |
|---|---|---|
| 详述类型说明符 | `struct T* p;` | `struct`、`class` 后面要的是类名（[[dcl.type.elab#6]]） |
| 类定义 | `struct T { };` | 不能通过别名定义类 |
| 构造函数声明 | 类内写 `T();` | 构造函数用注入类名声明（[[class.ctor.general]]） |
| 析构函数声明 | 类内写 `~T();` | 同上，析构函数名另有查找规则（[[class.dtor]]） |

typedef 名可以用来限定，只要构造函数本身的名字仍然是类名：

```cpp run ok
struct S { S(); };
typedef S T;
T::S() { }                // OK: 用 T 限定，构造函数名用的是 S
int main() { T t; (void)t; }
```

¶3 正文还规定，*simple-template-id*（形如 `X<int>` 的模板名加实参）只在模板名是别名模板或类型模板模板形参时才是 typedef 名；`std::vector<int>` 这样指向类模板特化的是类名。

## 无名结构体借用 typedef 名链接（¶4）

C 头文件里到处是这样的写法：

```cpp
typedef struct { int x, y; } Point;
void draw(Point p);       // 外部链接的函数，形参是一个无名结构体
```

`draw` 有外部链接，各个翻译单元（TU，单独编译的源文件及其包含的头文件）里的 `draw` 要能对上。可是它的修饰名里必须编码形参类型，而这个结构体没有名字。

¶4 的解决办法是：如果无名类或无名枚举 C 是在一个 typedef 声明中定义的，这条声明里第一个类型恰好为 C 的 typedef 名，就是 C 的**用于链接目的的 typedef 名**（typedef name for linkage purposes，[[g:typedef-name-for-linkage]]）。C 借用这个名字参与链接（[[basic.link#4]]）。在 Itanium ABI 下，`draw` 的修饰名是 `_Z4draw5Point`。

几个细节：

- 必须是类型恰好为 C 的第一个名字。`typedef struct { } *ps, S;` 中 `ps` 的类型是 `C*`，所以链接名是 `S`。
- 类必须是在这条 typedef 声明里定义的。`typedef decltype([]{}) C;` 不定义闭包类型（闭包类型由 lambda 表达式定义），所以闭包类型得不到链接名（注 2）。
- 无名枚举还可以借用它的第一个枚举项来链接（[[dcl.enum]]）。

!!! lawyer "别名声明也算吗"
    ¶4 字面上说的是 typedef 声明，而 `using A = struct { … };` 是别名声明。不过第 2 段规定两者语义相同，Clang 和 GCC 也都把 `A` 当作链接名。本机 Clang 23 下，`using A = struct { int t; }; void f(A) { }` 中 `f` 的符号是 `_Z1f1A`。

## C++20：只允许 C 兼容的结构体（¶5）

```cpp error
typedef struct {
    int f() { return 0; }   // error: 成员函数
} X;
struct B { };
typedef struct : B { } Y;                 // error: 基类
typedef struct { int m = 1; } Z;          // error: 默认成员初始化器
typedef struct { decltype([]{}) m; } W;   // error: 含 lambda 表达式
```

¶5 有用于链接目的的 typedef 名的无名类，不得：

- ¶5.1 声明非静态数据成员、成员枚举、成员类以外的任何成员，即不能有成员函数、静态数据成员、成员 typedef、`static_assert` 等；
- ¶5.2 有基类或默认成员初始化器；
- ¶5.3 含有 lambda 表达式。

它的成员类也要递归地满足这些要求。下面这种 C 风格的结构体不受影响：

```cpp run ok
typedef struct {
    int x, y;
    enum Kind { a, b } kind;      // OK: 成员枚举
    struct Inner { int z; } in;   // OK: 成员类，自身也满足要求
} CStyle;
int main() { CStyle c{}; return c.x; }
```

为什么要限制？编译器读到 `typedef struct {` 时，还不知道后面会有一个 typedef 名，也就不知道这个类有没有链接、叫什么。成员函数的修饰名要包含类名，lambda 闭包类型的身份依赖于外围实体，默认成员初始化器里也可能出现 lambda。如果类体里有这些东西，编译器就得回头修改已经做出的决定；对模块来说，这还影响一个声明能否导出。C++20 的 [[P1766R1]] 干脆把这种写法限制在 C 兼容的范围内，而兼容 C 正是这个特性存在的理由。

!!! impl "Clang 只给警告"
    对违反第 5 段的代码，本机 Clang 23 只给 `-Wnon-c-typedef-for-linkage` 警告（"anonymous non-C-compatible type given name for linkage purposes by typedef declaration; add a tag name here"），然后继续编译，以兼容大量旧代码。按标准这些代码都非良构。修复方法就是提示里说的：给结构体加上名字（`typedef struct X { … } X;`），它不再是无名类，第 5 段也就不适用了。

!!! history "历史与演进"
    - C++98 就有 `typedef` 和用于链接目的的 typedef 名，当时对无名类的内容没有限制。
    - C++11 加入别名声明和别名模板。
    - C++20 加入第 5 段的限制（[[P1766R1]]）。同时 lambda 可以出现在不求值操作数里，才有了 `typedef decltype([]{}) C;` 这种写法，注 2 说明它不给闭包类型带来链接名。

!!! pitfall "常见误解"
    - typedef 是文本替换：不是。`typedef char* P; const P p = nullptr;` 中 `p` 的类型是 `char* const`，不是 `const char*`（[[dcl.spec.general#3]]）。
    - `using` 比 `typedef` 能做更多事：除了别名模板，两者完全等价。
    - typedef 能创建强类型：不能，别名和原类型是同一个类型。

!!! question "思考题"
    下面的代码在 C++20 中是否良构？如果不是，最小的修改是什么？

    ```cpp
    typedef struct {
        static constexpr int version = 1;
        int data;
    } Header;
    ```

<details markdown="1">
<summary>答案</summary>

非良构：静态数据成员不是非静态数据成员、成员枚举或成员类（¶5.1）。实际上无名类本来就不能有静态数据成员（[[class.static.data#2]]），本机 Clang 23 对此直接报错。

最小的修改是给结构体起名：`typedef struct Header { … } Header;`，或者直接写 `struct Header { … };`。有名字的类不受第 5 段约束。如果这个结构体还要给 C 用，就把 `version` 移到外面，改成宏或命名空间作用域的常量。
</details>
