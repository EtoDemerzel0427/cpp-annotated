---
title: 数组
summary: 数组声明符 `D1[N]` 与 `D1[]` 的含义：边界必须是大于零的 std::size_t 常量，哪些类型不能作元素，数组的 cv 就是元素的 cv，未知边界的数组怎样补全，多维数组的真实结构，以及 C++ 为什么没有变长数组。
status: draft
related: dcl.decl, dcl.init.aggr, dcl.init.string, conv.array, expr.sub, expr.new, basic.types, basic.type.qualifier, expr.const.const
tags: 数组, 声明符, 常量表达式, VLA
updated: 2026-10-19
---

!!! tldr
    - 数组的边界是类型的一部分：`int[3]`、`int[4]`、`int[]` 是三个不同的类型，其中未知边界的 `int[]` 是不完整类型。
    - 边界必须是 `std::size_t` 类型的转换常量表达式，并且大于零。浮点数、负数、有作用域枚举、运行期的值都不行，所以 C++ 没有变长数组（VLA）。
    - 元素不能是引用、函数、未知边界的数组或 `void`。给数组加 cv，实际加在元素上。
    - C++ 没有真正的多维数组，只有数组的数组。`int a[3][5]` 有 3 个元素，每个元素是 `int[5]`；只有第一维的边界可以省略。
    - 有初始化器时可以省略边界，由初始值个数决定；也可以从同一宿主作用域中先前的声明继承边界。

数组不能赋值，不能按值传参或返回，几乎在每个表达式里都会转换成指向首元素的指针。这一节规定数组声明符的含义和数组类型的基本性质。数组的初始化见 [[dcl.init.aggr]] 和 [[dcl.init.string]]，下标见 [[expr.sub]]，数组到指针的转换见 [[conv.array]]。

## 数组的边界（¶1）

<div class="compare" markdown="1">

```cpp run ok
enum E { e3 = 3 };
int a4[e3];   // 无作用域枚举
struct Conv {
  constexpr operator int() const
  { return 4; }
};
int a6[Conv{}];   // constexpr 转换
const int c = 5;
int a11[c];   // const 整型变量
int main() { }
```

```cpp run error
int a1[1.5];   // error: 浮点数
int a2[-1];    // error: 负数
enum class EC { k = 3 };
int a5[EC::k]; // error: 有作用域枚举
int n = 3;
int a7[n];     // error: 不是常量
```

</div>

¶1 如果声明 `T D` 中的 `D` 形如 `D1[N]`，名字的类型就是"`N` 个 `T` 的数组"，前面再加上内层声明符积累的修饰（见 [[dcl.decl]]）。

!!! std
    The *constant-expression* shall be a converted constant expression of type `std::size_t`. Its value N specifies the *array bound*, i.e., the number of elements in the array; N shall be greater than zero.

这句话里的每个限定都排除了一些写法：

- 常量表达式（[[expr.const]]）：边界必须在编译期确定，这就排除了变长数组。用常量表达式初始化的 `const int c` 可以用在常量表达式里，所以 `a11` 合法。
- 转换常量表达式（[[g:converted-constant-expression|converted constant expression]]，[[expr.const.const]]）：从表达式到 `std::size_t` 只允许不丢失信息的隐式转换，例如整型提升、不收窄的整型转换，以及 `constexpr` 的用户定义转换。浮点数到整数的转换不允许；`-1` 转换为 `std::size_t` 是收窄，也不允许。
- 类型 `std::size_t`：有作用域枚举不能隐式转换为整数，所以不能直接作边界。
- 大于零：C++ 没有零长度数组。GCC 和 Clang 把 `int a[0];` 作为扩展接受，`sizeof` 为 0，加 `-pedantic` 时给出 `-Wzero-length-array` 警告。

**数组边界**（[[g:array-bound|array bound]]）就是数组元素的个数 `N`。同一元素类型、不同边界的数组是不同的类型。

## 未知边界的数组（¶2–3）

¶2 如果 `D` 形如 `D1[]`，类型就是"`T` 的未知边界数组"，第 7、8 段说明了几种例外。

¶3 "`N` 个 `U` 的数组"和"`U` 的未知边界数组"统称**数组类型**。`[]` 后面可以有属性，属性属于数组类型。

未知边界的数组是[[g:incomplete-type|不完整类型]]（[[basic.types]]）。可以声明这种类型的变量（`extern int a[];`），可以形成指向它的指针和引用（`int (*)[]`、`int (&)[]`），但不能定义这种类型的对象，也不能对它用 `sizeof`。

## 元素类型（¶4–6）

### 哪些类型不能作元素（¶4）

```cpp run error
int& a8[2];     // error: 引用数组
void a9[2];     // error: void 数组
int a10[2][];   // error: 元素是未知边界数组
int f[2]();     // error: 函数数组
```

¶4 数组的**元素类型**（[[g:array-element-type|element type]]）`U` 不能是：

- 引用，因为引用不是对象（[[dcl.ref#5]]）；
- 函数，函数不是对象，没有大小。想要的通常是函数指针数组 `int (*f[2])();`；
- 未知边界的数组，否则外层数组无法计算元素的大小。这就是多维数组只有第一维可以省略的原因；
- cv `void`，它是无法补全的不完整类型。

注 1 从正面列出了可以作元素的类型：除 `void` 以外的基本类型、指针、成员指针、类、枚举，以及已知边界的数组。定义数组对象时，类类型的元素必须完整；抽象类不能作元素类型（[[class.abstract]]）。

### 数组的 cv 就是元素的 cv（¶5）

```cpp run ok
#include <type_traits>
typedef int A[5], AA[2][3];
typedef const A  CA;    // 5 个 const int 的数组
typedef const AA CAA;   // 2 个〔3 个 const int 的数组〕的数组

static_assert(std::is_same_v<CA, const int[5]>);
static_assert(std::is_same_v<CAA, const int[2][3]>);
static_assert(std::is_const_v<CA>);   // 数组类型本身也算 const 限定
int main() { }
```

¶5 "cv `N` 个 `U` 的数组"一律调整为"`N` 个 cv `U` 的数组"，未知边界的数组也一样。对多维数组，cv 一直下沉到最内层的元素。注 2 补充，调整后的数组类型本身也算 cv 限定类型（[[basic.type.qualifier]]），所以 `std::is_const_v<CA>` 为真。

这样设计的理由是，数组不能作为整体修改，const 数组唯一可能的含义就是元素都是 const。把 cv 统一放到元素上，模板里的 `const T` 在 `T` 是数组时也有自然的含义。

### 元素连续存放（¶6）

¶6 "`N` 个 `U` 的数组"类型的对象由 `N` 个连续分配的 `U` 类型子对象组成，这些子对象叫数组的**元素**，编号从 0 到 `N-1`；0 号元素叫**首元素**。

连续意味着元素之间没有填充，`sizeof(U[N]) == N * sizeof(U)`（[[expr.sizeof#2]]）。每个元素需要的对齐已经包含在 `sizeof(U)` 的尾部填充里。指针算术（[[expr.add]]）只在同一个数组的元素和尾后位置之间有定义，依据正是这些元素都是同一个数组对象的子对象。

## 省略边界（¶7–8）

### 由初始化器决定（¶7）

```cpp run ok
#include <type_traits>
int b[] = {1, 2, 3};          // int[3]
char s[] = "abc";             // char[4]，包括结尾的 '\0'
static_assert(std::is_same_v<decltype(b), int[3]>);
static_assert(sizeof s == 4);
int main() {
  auto p = new int[]{1, 2, 3};   // new int[3]
  delete[] p;
}
```

¶7 除了本来就允许不完整对象类型的声明之外，还有两种情况可以省略边界：

- 函数形参（[[dcl.fct]]）。形参类型会被调整为指针，边界本来就没有作用。
- 对象（但不是非静态数据成员）的声明带有初始化器。这时边界由初始值的个数 `N` 计算（[[dcl.init.aggr]]），类型是"`N` 个 `U` 的数组"。这也适用于 `new int[]{1, 2, 3}`（[[expr.new]]）和 `int[]{1, 2}` 这样的函数式转换（[[expr.type.conv]]）。

```cpp run error
struct M { int m[] = {1, 2}; };   // error: 不能从默认成员初始化器推导边界
```

非静态数据成员不行，是因为类的布局必须在类定义结束时确定。默认成员初始化器只在构造函数没有给出初始化时才使用，不同的构造函数可能提供不同个数的初始值。

### 从先前的声明继承（¶8）

```cpp run error
extern int x[10];
struct S { static int y[10]; };

int x[];                // OK：边界是 10
int S::y[];             // OK：边界是 10

void f() {
  extern int x[];       // 宿主作用域是块，与前面的声明不同
  int i = sizeof(x);    // error: 不完整类型
}

namespace A { extern int z[3]; }
int A::z[] = {};        // OK：定义 3 个元素的数组
```

¶8 如果有一个可达的先前声明指定了边界，并且它和当前声明的宿主作用域相同，省略的边界就取那个声明中的值。类外定义静态数据成员时也一样。宿主作用域的定义见 [[basic.scope.scope]]：声明栖居在块作用域时，宿主作用域就是那个块；否则就是声明的目标作用域。

所以函数里的 `extern int x[];` 不继承边界：它的宿主作用域是函数体这个块，而前面的声明在全局命名空间。块作用域的重声明只引入一个局部可见的名字，不累积外层声明的信息。

## 多维数组（¶9）

```cpp run ok
#include <type_traits>
int x3d[3][5][7];
static_assert(std::is_same_v<decltype(x3d[1]),    int(&)[5][7]>);
static_assert(std::is_same_v<decltype(x3d[1][2]), int(&)[7]>);
static_assert(std::is_same_v<decltype(+x3d),      int(*)[5][7]>);  // 一元 + 触发数组到指针转换
static_assert(sizeof x3d == 3 * 5 * 7 * sizeof(int));

void g(int m[][5][7]);   // 形参调整为 int (*)[5][7]；后两维必须写出
int main() { }
```

¶9 是一条注：几个数组声明相邻时就形成多维数组类型，只有第一个边界可以省略。

按 [[dcl.decl]] 的方法读 `int x3d[3][5][7];`：后缀运算符从左到右结合，即 `((x3d[3])[5])[7]`，所以最外层是 `[7]`，它紧贴 `int`，得到"7 个 `int` 的数组"；然后是 `[5]`，最后是 `[3]`。于是 `x3d` 有 3 个元素，每个元素是 `int[5][7]`，后者的每个元素又是 `int[7]`。

在表达式里，`x3d[i]` 等价于 `*(x3d + i)`。`x3d` 先转换为指向首元素的 `int (*)[5][7]`；加 `i` 时，步长是 `sizeof(int[5][7])`；解引用得到第 `i` 个元素，一个 `int[5][7]` 类型的左值。再下标同理。

注的结论是：第一个边界决定数组占多少存储，但不参与任何下标计算。所以第一维可以省略，函数形参的第一维也会在调整为指针时丢掉。

¶10 这一段和第 11 段都是注：数组类型表达式的转换见 [[conv.array]]；下标运算符可以为类重载（[[over.sub]]），内置含义见 [[expr.sub]]。

## C++ 没有变长数组

```cpp run error
void f(int m) {
  int vla[m];             // error: 边界不是常量表达式
  int* ok = new int[m];   // OK：new 表达式的第一维可以是运行期的值
  delete[] ok;
  (void)vla;
}
```

C99 引入了变长数组（VLA），C11 把它改为可选特性。C++ 一直没有采纳：第 1 段要求边界是常量表达式，所以上面的 `int vla[m];` 非良构。

主要的理由有三个。第一，VLA 的类型依赖运行期的值，`sizeof` 变成运行期运算，模板实参推导、重载决议、`decltype` 都得处理运行期才确定的类型，这和 C++ 在编译期确定类型的设计相冲突。第二，在栈上分配任意大小的空间，`m` 过大时会直接栈溢出，而且无法检测。第三，已经有替代品：`std::vector`、`std::unique_ptr<T[]>`，以及 `new T[n]`（[[expr.new]] 允许 *new-declarator* 的第一维不是常量）。C++14 制定期间曾讨论过运行期边界的数组和 `std::dynarray`，最终都没有进入标准。

GCC 和 Clang 把 VLA 作为扩展接受。本机 Clang 23 默认给出 `-Wvla-cxx-extension` 警告（variable length arrays in C++ are a Clang extension），加 `-pedantic-errors` 时报错。MSVC 不支持 VLA。

## 实现视角

!!! impl
    - 柔性数组成员：C99 的 `struct S { int n; int data[]; };` 在 C++ 中非良构，因为非静态数据成员不能是未知边界的数组。GCC 和 Clang 作为扩展接受，Clang 加 `-pedantic` 时给出 `-Wc99-extensions` 警告。
    - 名字修饰：Itanium C++ ABI 把数组类型编码为 `A<N>_<元素类型>`，例如形参 `int(&)[3]` 修饰为 `RA3_i`；未知边界的数组编码为 `A_i`。
    - 数组类型的大小有上限。`int b[sizeof(int) - 5];` 的边界是 `SIZE_MAX`，本机 Clang 报 array is too large。

## 历史与演进

!!! history
    - 数组的语义继承自 C。C++98 要求边界是整型常量表达式。
    - C++11 加入了 `std::array`、统一的列表初始化，以及对数组的 range-for。
    - C++14 把边界的要求改为 `std::size_t` 的转换常量表达式。这样类类型可以通过 `constexpr` 转换函数作边界，负数边界也作为收窄转换由同一套规则拒绝。
    - C++20 允许指向已知边界数组的指针或引用转换为指向未知边界数组的（[[conv.qual]]），`new int[]{1, 2, 3}` 也可以推导边界。
    - C++23 允许重载的 `operator[]` 有多个形参（`m[i, j]`）。

## 陷阱

!!! pitfall "形参中的数组"
    `void f(int a[10])` 里的 `10` 被忽略，`a` 的类型是 `int*`（[[dcl.fct#5]]），`sizeof a` 是指针的大小。在形参上写 `sizeof(a) / sizeof(a[0])` 会得到错误的结果，Clang 对此给出 `-Wsizeof-array-argument` 和 `-Wsizeof-pointer-div` 警告。要保留边界，用引用 `int (&a)[10]` 或 `std::span<int, 10>`；求元素个数用 `std::size(a)`，它对指针会编译失败。

!!! pitfall "`int (*p)[3]` 与 `int *p[3]`"
    前者是指向 3 个 `int` 的数组的指针，后者是 3 个指针组成的数组。后缀 `[]` 比前缀 `*` 结合得紧（[[dcl.decl]]）。

!!! pitfall "数组不能赋值，也不能作返回类型"
    `int a[3], b[3]; a = b;` 非良构；函数不能返回数组类型（[[dcl.fct#16]]）。但包含数组成员的类可以复制和返回，隐式的复制构造函数会逐个复制元素。lambda 按值捕获数组时，也是逐个复制元素。

## 思考题

!!! question "思考题 1"
    下面哪些声明是良构的？
    ```cpp
    constexpr int k = -1;
    int a[k + 2];
    int c[true];
    int d['a'];
    ```

<details markdown="1">
<summary>答案</summary>

都良构。`k + 2` 的值是 1，`int` 转换为 `std::size_t` 时值可以表示，不算收窄。`true` 转换为 `std::size_t` 得到 1。`'a'` 的值是 97。转换常量表达式看的是值能否在目标类型中表示，而不只是源类型。
</details>

!!! question "思考题 2"
    为什么 `extern int a[]; int (*p)[] = &a;` 良构，而 `int (*q)[3] = &a;` 非良构？

<details markdown="1">
<summary>答案</summary>

`&a` 的类型是 `int (*)[]`，与 `p` 相同。从指向未知边界数组的指针到指向已知边界数组的指针，不是任何标准转换：C++20 只允许反方向（已知到未知，[[conv.qual]]），因为编译器无法验证边界真的是 3。本机 Clang 23 连 `static_cast<int(*)[3]>(&a)` 也拒绝，只能用 `reinterpret_cast`，而且只有 `a` 实际有至少 3 个元素时，这样得到的指针才有意义。
</details>
