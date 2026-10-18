---
title: typedef 说明符
summary: typedef 与别名声明引入的是类型别名而不是新类型；typedef 的组合限制；typedef 名不能用于详述类型说明符、类定义和构造/析构函数声明；用于链接目的的 typedef 名及其 C++20 限制
status: done
papers: P1766R1
related: dcl.pre, dcl.spec, basic.link, temp.alias, dcl.type.elab, basic.scope.pdecl
tags: 声明, 类型别名, typedef, 链接
updated: 2026-10-17
---

`typedef` 和 `using X = ...;` 都声明**类型别名**（*type alias*）：给一个已有类型起另一个名字。标准反复强调一点——**typedef 名不引入新类型**。`typedef int Meters;` 之后，`Meters` 和 `int` 是同一个类型，可以互相赋值、重载时视为相同参数类型。想要"强类型别名"，必须定义一个新的类或枚举。

本节还包含一个与 ABI 紧密相关的概念：**用于链接目的的 typedef 名**（*typedef name for linkage purposes*）——C 风格的 `typedef struct { ... } S;` 中，无名结构体如何获得一个可以跨翻译单元匹配的名字。

## typedef 说明符（¶1）

¶1 含有 `typedef` 的声明声明**类型别名**。约束：

1. `typedef` 只能和**定义类型说明符**（*defining-type-specifier*：类型说明符、类定义、枚举定义）组合，不能和 `static`、`inline`、`constexpr`、`friend` 等任何其他说明符组合；
2. 不能用于**参数声明**的说明符序列；
3. 不能用于**函数定义**的说明符序列；
4. 有 `typedef` 但没有声明符，非良构（`typedef int;`）。

用 `typedef` 声明的名字成为 *typedef-name*，其**底层实体**是与该标识符关联的类型（按 [[dcl.decl]] 的声明符规则包装后的类型）。

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

和普通声明一样，`typedef` 是**说明符**，作用于整行，而 `*`、`[3]`、`(*)(…)` 是**声明符**，只作用于各自的名字。把 typedef 读作"在变量声明前面加上 typedef，变量名就变成了它的类型的名字"，就不会出错。

```cpp error
typedef static int SI;            // error: typedef 不能与存储类说明符组合
typedef inline int II;            // error: 也不能与 inline 组合
void g(typedef int x);            // error: 不能用于参数声明
typedef int h(int) { return 0; }  // error: 不能用于函数定义
```

!!! note "typedef 的重复声明"
    同一个命名空间或块作用域中，可以用 typedef 把一个名字**再次**声明为同一类型的别名（`typedef int I; typedef int I;` 合法），但不能指向不同类型。在**类作用域**中，重复的成员 typedef 是非良构的（[[class.mem.general#8]]：成员不能在类定义中声明两次）。

## 别名声明（¶2）

¶2 *alias-declaration* `using 标识符 属性(opt) = 定义类型标识;` 也声明类型别名，语义与 `typedef` **完全相同**。`using` 后的标识符**不被查找**，它直接成为 typedef 名；其后的属性属于这个类型别名。

`using` 形式的优点：

- **可读性**：名字在左、类型在右，函数指针一目了然：`using handler_t = void (*)(int);` 对比 `typedef void (*handler_t)(int);`。
- **可以模板化**：*alias-declaration* 可以作为模板声明的 *declaration*，形成**别名模板**（[[temp.alias]]）；`typedef` 不行。

```cpp run ok
#include <vector>
using handler_t = void (*)(int);
extern handler_t ignore;
extern void (*ignore)(int);       // OK: 同一个变量的重声明——类型完全相同
template<class T> using Vec = std::vector<T>;   // 别名模板
using Old [[deprecated("use New")]] = int;      // 属性作用于别名本身
int main() { Vec<int> v; return int(v.size()); }
```

**声明点**：别名声明的名字在整个 *alias-declaration* **之后**才可见（[[basic.scope.pdecl]]），所以不能在自己的定义里递归引用：

```cpp error
template<class T> struct P { };
using cell = P<cell*>;            // error: cell 在这里还没被声明
```

对比 `typedef`：`typedef P<cell*> cell;` 同样不行，因为 typedef 名的声明点在其完整声明符之后，而 `P<cell*>` 在声明符之前。要表达"递归类型"，只能借助类：`struct cell { P<cell*> p; };`。

¶2 最后一句：若 *alias-declaration* 是**模板声明**的一部分（别名模板），其类型标识中**不能定义类或枚举**。

```cpp error
template<class T> using Box = struct { T t; };   // error: 别名模板中不能定义类
```

为什么？别名模板的每个特化都"等于"其类型标识所指的类型；如果类型标识里定义了一个类，那么 `Box<int>` 与 `Box<int>` 是不是同一个类、它属于哪个作用域、链接名是什么，都无从规定。非模板的 `using A = struct { int t; };` 则没有这个问题，是合法的。

## typedef 名与类名的区别（¶3）

¶3 *simple-template-id* 只有在其模板名指向**别名模板**或**类型模板模板参数**时才是 *typedef-name*；指向类模板特化的 *simple-template-id* 是 *class-name*。

Note 1 列出了 typedef 名**不能**出现的四个位置：

| 位置 | 例子 | 原因 |
|---|---|---|
| *elaborated-type-specifier* | `struct T* p;`（T 是 typedef） | 详述类型说明符要的是"类的名字"（[[dcl.type.elab#6]]） |
| 类定义 | `struct T { };` | 不能"通过别名定义类" |
| 构造函数声明 | `T();`（类内，T 是类的别名） | 构造函数用注入类名声明（[[class.ctor.general]]） |
| 析构函数声明 | `~T();` | 同上（析构函数**名**的查找另有规则，[[class.dtor]]） |

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

¶4 在 typedef 声明中**定义**的无名类或无名枚举 C，以该声明中**第一个**类型为 C 的 typedef 名作为它的**用于链接目的的 typedef 名**（[[g:typedef-name-for-linkage]]，[[basic.link]]）。

!!! std
    An unnamed class or enumeration C defined in a typedef declaration has the first *typedef-name* declared by the declaration to be of type C as its *typedef name for linkage purposes*.

为什么需要这个概念？无名类没有名字，按理说没有链接，不能在多个 TU 之间被识别为"同一个类型"。但 C 头文件中大量存在

```cpp
typedef struct { int x, y; } Point;
void draw(Point p);       // 外部链接的函数，参数类型是一个无名结构体
```

若 `Point` 所指的无名结构体没有链接，`draw` 就无法在不同 TU 中匹配（它的 mangled 名中必须编码参数类型）。所以标准规定：这个无名类借用 typedef 名 `Point` "当作"自己的名字参与链接（[[basic.link#4]] 的 ¶4.3、¶4.4），mangled 名中也就使用 `Point`（Itanium ABI 下 `draw` 被修饰为 `_Z4draw5Point`）。

注意几个细节：

- 是**第一个**"类型为 C"的 typedef 名：`typedef struct { } *ps, S;` 中 `ps` 的类型是 `C*` 而不是 `C`，所以 `S` 才是链接名。
- 只有在 typedef 声明中**定义**的类才有：`typedef decltype([]{}) C;` 不定义闭包类型（闭包类型是 lambda 表达式定义的），所以闭包类型**没有**用于链接目的的 typedef 名（Note 2）。
- 无名**枚举**还有另一种获得链接名的方式：用它的第一个枚举项（[[dcl.enum]]）。

!!! lawyer "别名声明也算吗？"
    ¶4 的字面措辞是"typedef 声明"（[[dcl.pre#8]]：说明符序列含 `typedef` 的声明），而 `using A = struct { … };` 是 *alias-declaration*。不过 ¶2 说别名声明"与 typedef 引入的别名语义相同"，实现（Clang、GCC）也把它同样视为给出用于链接目的的名字——例如 Clang 下 `using A = struct { int t; }; void f(A) { }` 中 `f` 的符号是 `_Z1f1A`。

## C++20 的限制（¶5）

¶5 具有用于链接目的的 typedef 名的无名类**不得**：

- ¶5.1 声明除**非静态数据成员、成员枚举、成员类**以外的成员（即：不能有成员函数、静态数据成员、成员 typedef、`static_assert`……）；
- ¶5.2 有**基类**或**默认成员初始化器**；
- ¶5.3 包含 **lambda 表达式**；

并且所有成员类也递归地满足这些要求。

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

!!! note "动机：鸡生蛋问题"
    编译器处理 `typedef struct { ... } X;` 时，读到类体时**还不知道**后面会有 typedef 名 `X`——也就是不知道这个类有没有链接、链接名叫什么。如果类体里有成员函数、lambda、默认成员初始化器等需要"知道所在类的身份"才能处理的东西（例如成员函数的 mangled 名包含类名、lambda 闭包类型的 ODR 身份依赖于外围实体），编译器就必须**回过头**修改之前的决定。对模块而言，这还会影响一个声明是否能被导出。C++20 的 [[P1766R1]] 干脆把这种写法限制为"C 兼容"的结构体——正是这个特性存在的唯一理由。

!!! impl "Clang 只给警告"
    对违反 ¶5 的代码，Clang 给出 `-Wnon-c-typedef-for-linkage` **警告**（"anonymous non-C-compatible type given name for linkage purposes by typedef declaration; add a tag name here"）并继续编译，以兼容大量旧代码。按标准这些都是非良构的。修复方法正如提示：给结构体加一个名字（`typedef struct X { ... } X;`），它就不再是无名类，¶5 不再适用。

!!! history "历史与演进"
    - C++98：`typedef`；用于链接目的的 typedef 名已存在，对无名类的内容没有额外限制。
    - C++11：*alias-declaration*（`using X = …;`）和别名模板。
    - C++20：[[P1766R1]] 引入 ¶5 的限制（与模块的设计一并考虑）；C++20 也允许 lambda 出现在不求值操作数中，于是才有 `typedef decltype([]{}) C;` 这种写法，Note 2 说明它不会给闭包类型链接名。

!!! pitfall "常见误解"
    - "typedef 是宏替换"——不是。`typedef char* P; const P p;` 中 `p` 是 `char* const`，不是 `const char*`（[[dcl.spec.general#3]]）。
    - "`using` 比 `typedef` 能做更多事"——除了别名模板，两者完全等价；`using` 不能做而 `typedef` 能做的事情是一次声明多个别名。
    - "typedef 可以创建强类型"——不能，`typedef int Meters; typedef int Seconds;` 的两个名字是同一类型。

!!! summary "小结"
    - typedef 与 *alias-declaration* 声明类型别名，**不引入新类型**。
    - `typedef` 只能与类型说明符组合，不能用于参数和函数定义。
    - 别名声明名字的声明点在声明之后；别名模板中不能定义类/枚举。
    - typedef 名不能用于 `struct T`、类定义、构造/析构函数声明。
    - `typedef struct { … } S;` 中 `S` 是无名结构体的链接名；C++20 起该结构体必须"C 兼容"（无成员函数、无基类、无默认成员初始化器、无 lambda）。

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

非良构：静态数据成员不是"非静态数据成员、成员枚举或成员类"（¶5.1）。（事实上无名类本来就不能有静态数据成员，[[class.static.data#2]]，Clang 对此直接报错。）最小修改是给结构体命名：`typedef struct Header { ... } Header;` 或直接 `struct Header { ... };`——有名字的类不受 ¶5 约束。若必须与 C 共享，就把 `version` 移出结构体，改用宏或命名空间作用域的常量。
</details>
