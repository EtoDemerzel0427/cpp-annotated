---
title: 数组
summary: 数组声明符 `D1[N]` 与 `D1[]`：边界是 std::size_t 的转换常量表达式且必须为正、元素类型的限制、数组的 cv 是元素的 cv、未知边界数组何时能补全、多维数组的真实结构、数组到指针的转换，以及 C++ 为什么没有 VLA
status: draft
related: dcl.decl, dcl.init.aggr, dcl.init.string, conv.array, expr.sub, expr.new, basic.types, basic.type.qualifier, expr.const.const
tags: 数组, 声明符, 常量表达式, VLA
updated: 2026-10-17
---

数组是 C++ 从 C 继承来的最古老的复合类型，也是行为最不像值的类型：不能赋值，不能按值传参，不能按值返回，在几乎所有表达式里一出现就退化为指针。本节（[dcl.array]）规定数组声明符的含义与数组类型的基本性质；数组的初始化见 [[dcl.init.aggr]] 与 [[dcl.init.string]]，下标见 [[expr.sub]]，退化见 [[conv.array]]。

理解本节的关键是两个事实：

1. **数组的边界是类型的一部分**。`int[3]` 和 `int[4]` 是不同的类型，`int[]`（未知边界）又是另一个类型，而且是不完整类型。
2. **C++ 没有真正的多维数组**，只有数组的数组。`int a[3][5]` 是含 3 个元素的数组，每个元素是 `int[5]`。

## 有边界的数组（¶1）

¶1 在声明 `T D` 中，如果 `D` 形如 `D1 [ constant-expression ] attr(opt)`，且 `T D1` 中 *declarator-id* 的类型是"*list* `T`"，那么 `D` 中 *declarator-id* 的类型是"*list* `N` 个 `T` 的数组"。

!!! std
    The *constant-expression* shall be a converted constant expression of type `std::size_t`. Its value N specifies the *array bound*, i.e., the number of elements in the array; N shall be greater than zero.

    边界表达式必须是 `std::size_t` 类型的转换常量表达式；其值 `N` 是**数组边界**，必须大于零。

逐项来看：

- 常量表达式：边界必须在编译期确定（[[expr.const]]），这就排除了变长数组（VLA）。
- 转换常量表达式（converted constant expression，[[expr.const.const]]）：只允许安全的隐式转换，如整型提升、不收窄的整型转换、用户定义转换（`constexpr` 转换函数）等。不允许浮点到整数的转换，也不允许收窄（负数转换为 `size_t` 就是收窄）。
- 类型 `std::size_t`：边界的值域就是 `size_t` 的值域。有作用域枚举不能隐式转换为整数，所以不能直接用作边界。
- 大于零：C++ 没有零长度数组。

```cpp title="array-bound.cpp" error
int a1[1.5];               // error: double → size_t 不是转换常量表达式允许的转换
int a2[-1];                // error: -1 → size_t 是收窄转换
int a3[0];                 // error: N 必须大于零（GCC/Clang 默认作为扩展接受，-pedantic 时警告）
enum class EC { k = 3 };
int a5[EC::k];             // error: 有作用域枚举不能隐式转换为 size_t
int n = 3;
int a7[n];                 // error: n 不是常量表达式（命名空间作用域）
```

```cpp title="array-bound-ok.cpp" ok
enum E { e3 = 3 };
int a4[e3];                // OK：无作用域枚举 → 整型提升 → size_t
struct Conv { constexpr operator int() const { return 4; } };
int a6[Conv{}];            // OK：constexpr 用户定义转换
const int c = 5;
int a11[c];                // OK：用常量表达式初始化的 const 整型变量可用于常量表达式
constexpr unsigned long long big = 2;
int a12[big];              // OK：值可以表示为 size_t，不收窄
int main() { }
```

!!! note "为什么是转换常量表达式"
    C++11 之前，标准要求边界是整型常量表达式，规则较宽，任何能转换为整数的常量都可以。C++14 起（随着整型常量表达式与转换常量表达式的统一）改为 `std::size_t` 的转换常量表达式。这样做的好处是，类类型可以通过 `constexpr` 转换函数用作边界；负数边界也不再依靠单独的语义检查，而是作为收窄转换，由统一的机制拒绝。

## 未知边界的数组（¶2–3）

¶2 如果 `D` 形如 `D1 [ ] attr(opt)`，类型就是"*list* `T` 的未知边界数组"（array of unknown bound），除非下文（¶7–8）另有规定。

¶3 "`N` 个 `U` 的数组"与"`U` 的未知边界数组"统称**数组类型**。可选的属性属于数组类型。

未知边界数组是不完整类型（[[basic.types]]）：可以声明（`extern int a[];`），可以形成指针和引用（`int (*)[]`、`int (&)[]`），但不能定义对象，也不能对它用 `sizeof`。

## 元素类型的限制（¶4）

¶4 数组的**元素类型**（element type）`U` 不能是：

- 引用：引用不是对象（[[dcl.ref#5]]）；
- 函数：函数不是对象，没有大小；
- 未知边界数组：否则外层数组无法计算元素大小，这也是只有第一维可以省略的原因；
- cv `void`：它是不完整类型，且无法补全。

```cpp title="array-elem.cpp" error
int& a8[2];       // error: 引用数组
void a9[2];       // error: void 数组
int a10[2][];     // error: 元素是未知边界数组
int f[2]();       // error: 函数数组（想要函数指针数组：int (*f[2])();）
```

注 1 从正面列出了可以作为元素的类型：除 `void` 外的基本类型、指针、成员指针、类、枚举、已知边界的数组。注意，定义数组对象时类类型元素必须是完整的；抽象类不能作为元素类型（[[class.abstract]]）。

## 数组的 cv 就是元素的 cv（¶5）

¶5 任何"cv `N` 个 `U` 的数组"都调整为"`N` 个 cv `U` 的数组"，未知边界数组同理。注 2 补充说，调整后的"`N` 个 cv `U` 的数组"本身也算 cv 限定类型（[[basic.type.qualifier]]）。

```cpp title="array-cv.cpp" ok
#include <type_traits>
typedef int A[5], AA[2][3];
typedef const A  CA;     // "5 个 const int 的数组"
typedef const AA CAA;    // "2 个〔3 个 const int 的数组〕的数组"——const 一路下沉到最内层元素

static_assert(std::is_same_v<CA, const int[5]>);
static_assert(std::is_same_v<CAA, const int[2][3]>);
static_assert(std::is_const_v<CA>);   // 数组类型本身也被视为 const 限定
int main() { }
```

为什么这样设计？数组不能作为整体修改（不能赋值），所以 const 数组唯一可能的含义就是元素都是 const。把 cv 统一放在元素上，`const T` 在 `T` 为数组时也有自然的语义，模板代码不必做特殊处理。

## 元素是连续的子对象（¶6）

¶6 "`N` 个 `U` 的数组"类型的对象由 `N` 个 `U` 类型的子对象连续分配而成，这些子对象称为数组的**元素**，编号 0 到 `N-1`；0 号是**首元素**。

连续意味着元素之间没有填充：`sizeof(U[N]) == N * sizeof(U)`（[[expr.sizeof#2]]）。每个元素的对齐由 `sizeof(U)` 中已经包含的尾部填充保证。指针算术（[[expr.add]]）只在同一个数组的元素（及尾后位置）之间有定义，其前提正是这些元素都是同一数组对象的子对象。

## 省略边界（¶7–8）

¶7 除了允许不完整对象类型的声明外，以下情形可以省略边界：

- 函数形参（[[dcl.fct]]，形参会调整为指针，边界本来就无关紧要）；
- 对象（不包括非静态数据成员）的声明带有初始化器时：边界由初始值的个数 `N` 计算（[[dcl.init.aggr]]），类型为"`N` 个 `U` 的数组"。这也适用于 `new int[]{1, 2, 3}`（[[expr.new]]）和 `int[]{1, 2}` 这样的函数式转换（[[expr.type.conv]]）。

```cpp title="array-infer.cpp" ok
#include <type_traits>
int b[] = {1, 2, 3};          // int[3]
char s[] = "abc";             // char[4]，含结尾的 '\0'（[dcl.init.string]）
static_assert(std::is_same_v<decltype(b), int[3]>);
static_assert(sizeof s == 4);
auto p = new int[]{1, 2, 3};  // new int[3]
int main() { delete[] p; }
```

非静态数据成员为什么不行？类的布局必须在类定义结束时确定，而默认成员初始化器只在构造函数没有提供初始化时才使用，不同构造函数可能给出不同个数的初始值。

```cpp title="array-member.cpp" error
struct M { int m[] = {1, 2}; };   // error: 不能从默认成员初始化器推导边界
```

¶8 此外，如果有一个可达的、宿主作用域相同的先前声明指定了边界，省略的边界就取该声明中的值；静态数据成员的类外定义同理。

```cpp title="array-redecl.cpp" error
extern int x[10];
struct S { static int y[10]; };

int x[];                // OK：边界是 10
int S::y[];             // OK：边界是 10

void f() {
    extern int x[];     // 宿主作用域是块，与前面的声明不同 ⇒ 不继承边界
    int i = sizeof(x);  // error: 不完整类型
}

namespace A { extern int z[3]; }
int A::z[] = {};        // OK：定义 3 个元素的数组（全部值初始化）
```

块作用域的 `extern int x[];` 不继承边界。这与 [[dcl.fct.default]] 中不同宿主作用域的声明各有独立的默认实参集合是同一个设计思路：块作用域的重声明只引入一个局部可见的名字，不累积外层声明的信息。

## 多维数组（¶9）

¶9（注）多个数组规格相邻时，形成多维数组类型；只有第一个边界可以省略。

按 [[dcl.decl]] 的递归规则分析 `int x3d[3][5][7];`。`x3d[3][5][7]` 中的后缀运算符从左到右结合（`((x3d[3])[5])[7]`），所以最外层是 `[7]`，它紧贴 `int`，得到"7 个 int 的数组"；然后是 `[5]`，得到"5 个〔7 个 int 的数组〕的数组"；最后是 `[3]`。所以 `x3d` 是含 3 个元素的数组，每个元素是含 5 个元素的数组，后者的每个元素是 7 个 `int` 的数组。

在表达式中：

- `x3d[i]` 等价于 `*(x3d + i)`。`x3d` 经数组到指针转换（[[conv.array]]）成为指向首元素的 `int (*)[5][7]`；加 `i` 时步长是 `sizeof(int[5][7])`；解引用得到第 `i` 个元素，即一个 `int[5][7]` 左值；
- 再下标同理，`x3d[i][j]` 是 `int[7]` 左值，`x3d[i][j][k]` 是 `int` 左值。

注的结论是：**第一个边界决定存储大小，但不参与任何下标计算**。正因如此，第一维可以省略，函数形参的第一维也会在调整中去掉。

```cpp title="multidim.cpp" ok
#include <type_traits>
int x3d[3][5][7];
static_assert(std::is_same_v<decltype(x3d[1]),    int(&)[5][7]>);   // 左值：int[5][7]
static_assert(std::is_same_v<decltype(x3d[1][2]), int(&)[7]>);
static_assert(std::is_same_v<decltype(+x3d),      int(*)[5][7]>);   // 一元 + 触发数组到指针转换
static_assert(sizeof x3d == 3 * 5 * 7 * sizeof(int));

void g(int m[][5][7]);   // 形参：调整为 int (*)[5][7]；后两维必须写出
int main() { }
```

## 数组到指针的转换与下标（¶10–11）

¶10（注）数组类型表达式的转换见 [[conv.array]]：数组类型的左值或右值可以转换为指向首元素的指针 prvalue。函数实参、算术、比较、条件表达式中几乎处处发生这个转换，例外只有 `sizeof`、`alignof`、一元 `&`、`decltype`、引用绑定、`typeid` 以及以数组初始化字符数组等少数场合。

¶11（注）下标运算符可以为类重载（[[over.sub]]）；内置含义见 [[expr.sub]]。C++23 起重载的 `operator[]` 可以有多个形参（`m[i, j]`）。

## C++ 中没有 VLA

C99 引入了变长数组（`int a[n];`，`n` 在运行期确定），C11 改为可选特性。C++ 从未采纳它。¶1 要求边界是常量表达式，所以 `void f(int m) { int vla[m]; }` 在 ISO C++ 中非良构。

理由如下：

- 类型系统：VLA 的类型依赖运行期值，`sizeof` 变成运行期运算，模板实参推导、重载决议、`decltype` 都要处理运行期才确定的类型，这与 C++ 的编译期类型系统根本冲突；
- 安全性：在栈上分配任意大小，`n` 过大时直接栈溢出，且无法检测；
- 已有替代品：`std::vector`、`std::unique_ptr<T[]>`，以及 `new T[n]`（[[expr.new]] 中 *noptr-new-declarator* 的第一维允许非常量表达式）。C++ 曾讨论过 `std::dynarray` 和运行期边界数组（ARB），最终都没有进入标准。

```cpp title="vla.cpp" error
void f(int m) {
    int vla[m];             // ISO C++: error: 边界不是常量表达式（Clang/GCC 作为扩展接受，仅警告）
    int* ok = new int[m];   // OK：new 表达式的第一维可以是运行期值
    delete[] ok;
    (void)vla;
}
```

GCC 与 Clang 作为扩展接受 VLA，Clang 默认给出 `-Wvla-cxx-extension` 警告（"variable length arrays in C++ are a Clang extension"）；使用 `-pedantic-errors` 时报错。MSVC 不支持。

## 实现视角

!!! impl
    - 零长度数组：GCC 与 Clang 接受 `int a[0];` 作为 GNU 扩展（`-Wzero-length-array`），`sizeof` 为 0。标准要求给出诊断，一个警告就满足了这一要求。
    - 柔性数组成员：C99 的 `struct S { int n; int data[]; };` 在 C++ 中非良构（非静态数据成员不能是未知边界数组），GCC/Clang 作为扩展接受（`-Wc99-extensions`）。
    - 名字修饰：Itanium ABI 把数组类型编码为 `A<N>_<元素>`，如 `int(&)[3]` 形参修饰为 `RA3_i`；未知边界为 `A_i`。
    - 大数组：数组类型的大小上限由实现定义，超过时 Clang 报 "array is too large"。

## 历史与演进

!!! history
    - C++98：边界须为整型常量表达式；数组语义继承自 C。
    - C++11：`std::array` 作为具有值语义的数组进入标准库；列表初始化统一了数组的初始化语法；range-for 支持数组。
    - C++14：边界改为 `std::size_t` 的转换常量表达式。曾计划加入运行期边界数组（ARB）与 `std::dynarray`，最终撤回。
    - C++20：允许把已知边界的数组转换为未知边界的数组（指针 `int(*)[]`、引用 `int(&)[]`，[[conv.qual]]）；`new int[]{1,2,3}` 可以推导边界。
    - C++23：多维下标运算符 `operator[](i, j)`。

## 陷阱

!!! pitfall "形参中的数组"
    `void f(int a[10])` 中的 `10` 会被忽略，`a` 的类型是 `int*`（[[dcl.fct#5]]），`sizeof a` 是指针的大小。要保留边界，可以用引用 `int (&a)[10]` 或 `std::span<int, 10>`。

!!! pitfall "`T (*)[N]` 与 `T *[N]`"
    `int (*p)[3]` 是指向 3 个 int 的数组的指针，`int *p[3]` 是 3 个指针组成的数组。后缀 `[]` 比前缀 `*` 结合得紧（[[dcl.decl]]）。

!!! pitfall "数组不能赋值也不能返回"
    `int a[3], b[3]; a = b;` 非良构；函数不能返回数组类型（[[dcl.fct#16]]）。但包含数组的类可以复制和返回，隐式复制构造函数会逐元素复制数组成员。lambda 按值捕获数组也是逐元素复制。

!!! pitfall "`sizeof(arr) / sizeof(arr[0])`"
    数组退化为指针后，这个惯用法会给出错误结果而没有任何提示。应改用 `std::size(arr)`（对指针会编译失败）或 `std::extent_v<decltype(arr)>`。

## 思考题

!!! question "思考题 1"
    下面哪些声明良构？
    ```cpp
    constexpr int k = -1;
    int a[k + 2];
    int b[sizeof(int) - 5];
    int c[true];
    int d['a'];
    ```

<details markdown="1">
<summary>答案</summary>

- `a`：`k + 2` 是 1，`int` → `size_t` 且值可表示，不收窄，良构。
- `b`：`sizeof(int) - 5` 的类型是 `size_t`（无符号），在 `sizeof(int) == 4` 的平台上值为 `SIZE_MAX`。这是合法的 `size_t` 值，也大于零，语法与常量表达式规则都满足，但大小超出了实现限制，实践中会报数组太大。这属于实现限制，并不违反 ¶1。
- `c`：`bool` → `size_t` 是整型提升或转换，`true` 为 1，良构。（转换常量表达式不允许的是到 `bool` 的收窄，而不是从 `bool` 出发的转换。）
- `d`：`'a'` 为 97，良构。
</details>

!!! question "思考题 2"
    为什么 `extern int a[]; int (*p)[] = &a;` 良构，而 `int (*q)[3] = &a;` 非良构？

<details markdown="1">
<summary>答案</summary>

`&a` 的类型是 `int (*)[]`，与 `p` 相同。`q` 的类型是 `int (*)[3]`，而从指向未知边界数组的指针到指向已知边界数组的指针不是任何标准转换（C++20 只允许反方向，即已知到未知，[[conv.qual]]），因为编译器无从验证边界确实是 3。这时需要显式的 `static_cast` 或 `reinterpret_cast`（只有 `a` 实际至少有 3 个元素时才有意义）。
</details>

## 小结

!!! summary
    | 主题 | 要点 |
    |---|---|
    | 边界 | `std::size_t` 的转换常量表达式，> 0；不允许浮点、负数、有作用域枚举、运行期值 |
    | 未知边界 | `T[]` 是不完整类型；可由初始化器或同宿主作用域的先前声明补全；非静态数据成员不行 |
    | 元素类型 | 不能是引用、函数、未知边界数组、`void` |
    | cv | 数组的 cv 下沉到元素；`const T[N]` 也被视为 const 类型 |
    | 布局 | `N` 个元素连续分配，无间隙 |
    | 多维 | 数组的数组；只有第一维可省略；第一维不参与下标计算 |
    | VLA | ISO C++ 没有；GCC/Clang 扩展；用 `std::vector` 或 `new T[n]` |
