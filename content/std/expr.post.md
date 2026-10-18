---
title: 后缀表达式
summary: 后缀表达式的语法总览；内置下标 E1[E2] 按定义等于 *((E1)+(E2))，但数组操作数决定结果是左值还是亡值；C++23 多维 operator[] 与下标中逗号的废弃与移除；后缀 ++/-- 的值、副作用与单次求值规则
status: draft
covers: expr.post.general, expr.sub, expr.post.incr
papers: P0145R3, P1161R3, P2128R6, P2589R1, P0002R1, P1152R4
related: expr.compound, expr.call, expr.ref, expr.add, expr.unary.op, expr.pre.incr, over.sub, over.inc, intro.execution, basic.lval
tags: 表达式, 下标, 自增, 求值顺序, 值类别
updated: 2026-10-17
---

**后缀表达式**（postfix expression）是优先级最高的一层运算符：`a[b]`、`f(x)`、`T(x)`、`a.b`、`a->b`、`a++`、四个具名转换和 `typeid`。本页讲这一层的语法总览（[[expr.post.general]]），以及两个相对短小的子条款：下标（[[expr.sub]]）与后缀自增自减（[[expr.post.incr]]）。函数调用、成员访问、函数式转换和各种转换各有独立的页面（见 [[expr.compound]] 的地图）。

## 语法总览（[expr.post.general] ¶1–2）

¶1 只有一句规范性的话：后缀表达式从左到右结合（group left-to-right）。其余是语法：

```text
postfix-expression:
    primary-expression
    postfix-expression [ expression-list(opt) ]
    postfix-expression ( expression-list(opt) )
    simple-type-specifier ( expression-list(opt) )
    typename-specifier ( expression-list(opt) )
    simple-type-specifier braced-init-list
    typename-specifier braced-init-list
    postfix-expression . template(opt) id-expression
    postfix-expression . splice-expression
    postfix-expression -> template(opt) id-expression
    postfix-expression -> splice-expression
    postfix-expression ++
    postfix-expression --
    dynamic_cast < type-id > ( expression )
    static_cast < type-id > ( expression )
    reinterpret_cast < type-id > ( expression )
    const_cast < type-id > ( expression )
    typeid ( expression )
    typeid ( type-id )
```

几个值得注意的点：

- 下标和调用的括号里是 *expression-list*（即 *initializer-list*），所以可以出现花括号初始化列表和包展开：`f({1, 2})`、`x[{1, 2}]`、`f(args...)`、`m[is...]`。
- 函数式转换的类型部分只能是 *simple-type-specifier* 或 *typename-specifier*，也就是单个类型名。所以 `unsigned int(x)`、`int*(p)` 都不是合法的函数式转换（见 [[expr.type.conv]]）。
- `.`、`->` 后面除了名字还可以跟 *splice-expression* {{c++26}}：`obj.[: r :]`（见 [[expr.ref]]）。
- `dynamic_cast` 等四个具名转换和 `typeid` 在语法上是后缀表达式，优先级与函数调用相同；C 风格的 `(T)e` 则是更松的 *cast-expression*（[[expr.cast]]）。

左结合决定了链式后缀的含义：`a.b[c](d)` 是 `((a.b)[c])(d)`；`p->q++` 是 `(p->q)++`；`*p++` 中后缀 `++` 比一元 `*` 紧，所以是 `*(p++)`。

¶2 是一个注：具名转换中 *type-id* 后面的 `>` 可以来自把一个 `>>` 拆成两个 `>`（[[temp.names]]）。这是 C++11 修正 `>>` 问题的一部分，让 `static_cast<std::vector<int>>(v)` 不再需要写成 `> >`。

## 下标（[expr.sub]）

### 下标表达式与求值顺序（¶1）

¶1 定义**[[g:subscript-expression|下标表达式]]**（subscript expression）：后缀表达式后跟方括号，括号里是可能为空的、逗号分隔的 *initializer-clause* 列表，它们是下标运算符的实参。注意这里已经是 C++23 的写法，方括号里可以有零个、一个或多个实参（多个实参只对重载的 `operator[]` 有意义）。

然后是求值顺序：

!!! std
    The *postfix-expression* and the initialization of the object parameter of any applicable subscript operator function is sequenced before each expression in the *expression-list* and also before any default argument.

    方括号前的后缀表达式（以及重载时对象形参的初始化）先序于方括号内的每个表达式和默认实参。

而 `operator[]` 的各非对象形参的初始化之间是非决定性先序（indeterminately sequenced）的，这与函数调用的规则（[[expr.call#8]]）一致。

为什么要专门规定？C++17 之前，`E1[E2]` 中 `E1` 和 `E2` 的求值是无序的，`a[i] = i++` 这类代码或 `m[k()] = v()` 的行为难以推理。C++17 的求值顺序提案 [[P0145R3]] 规定 `E1` 先序于 `E2`；多维下标出现后，这条规则被推广为方括号前的部分先于全部实参。

```cpp run title="sub-order.cpp" ok
#include <cstdio>

int* arr() { std::puts("arr"); static int a[4]{}; return a; }
int idx() { std::puts("idx"); return 1; }

int main() {
    arr()[idx()] = 42;   // C++17 起保证先输出 "arr" 再输出 "idx"
    idx()[arr()] = 7;    // 交换写法也合法；仍是左边（idx）先求值
}
```

### 内置下标运算符（¶2）

¶2 规定内置下标的全部要求：

- 方括号里必须恰好有一个 *assignment-expression*，不能为空、不能有多个，也不能是花括号列表；
- 两个操作数中，一个是"`T` 的数组"类型的 glvalue 或"指向 `T` 的指针"类型的 prvalue，另一个是无作用域枚举或整型的 prvalue；
- 结果类型是 `T`，而 `T` 必须是完整定义的对象类型（脚注：即使在 `&x[0]` 这种惯用法里也一样）；
- 核心定义：

!!! std
    The expression `E1[E2]` is identical (by definition) to `*((E1)+(E2))`, except that in the case of an array operand, the result is an lvalue if that operand is an lvalue and an xvalue otherwise.

    `E1[E2]` 按定义就是 `*((E1)+(E2))`；唯一的例外是数组操作数：数组是左值则结果是左值，否则是亡值。

拆开看这句话的两部分。

先看"按定义等同于 `*((E1)+(E2))`"。下标不是一个独立的运算，而是指针加法（[[expr.add]]）加间接（[[expr.unary.op]]）的语法糖。于是指针算术的全部规则原封不动地适用于下标：越界即 UB，只能在同一个数组对象内移动，可以指向末尾之后但不能解引用。

再看数组操作数的例外。如果按字面展开，数组操作数会先经历数组到指针转换（[[conv.array]]），得到一个 prvalue 指针，而 `*` 的结果永远是左值，这样就丢失了数组本身是亡值这一信息。所以 C++11 起标准特意规定：如果数组操作数是亡值（例如 `std::move(arr)`、临时对象的数组成员），`arr[i]` 也是亡值。这与成员访问的规则（`std::move(s).m` 是亡值，[[expr.ref#8]]）一致：即将消亡的对象，其子对象也是即将消亡的。

```cpp run title="sub-category.cpp" ok
#include <type_traits>
#include <utility>

struct S { int arr[3]; };
int a[3];
int* p = a;
using A = int[3];

static_assert(std::is_same_v<decltype((a[0])), int&>);              // 左值数组 → 左值
static_assert(std::is_same_v<decltype((std::move(a)[0])), int&&>);  // 亡值数组 → 亡值
static_assert(std::is_same_v<decltype((S{}.arr[0])), int&&>);       // 临时对象的数组成员 → 亡值
static_assert(std::is_same_v<decltype((A{1, 2, 3}[0])), int&&>);    // 数组 prvalue 先实质化 → 亡值
static_assert(std::is_same_v<decltype((std::move(p)[0])), int&>);   // 指针操作数：总是左值

int main() {}
```

注意最后一行：指针操作数没有这个例外。`std::move(p)` 是一个亡值指针，但它指向的对象与指针本身是否将亡毫无关系，所以 `*p` 仍是左值。

`A{1, 2, 3}[0]` 那行的机制：¶2 要求数组操作数是 glvalue，而 `A{1, 2, 3}` 是 prvalue；凡是期望 glvalue 的地方出现 prvalue，都会施行临时量实质化转换（[[conv.rval]]、[[basic.lval]]），得到亡值。

### 下标的交换律（¶3）

¶3 是注：尽管外观不对称，下标满足交换律（求值顺序除外）。因为 `E1 + E2` 中指针和整数谁在左边都行，`a[2]`、`2[a]`、`*(a + 2)`、`*(2 + a)` 完全等价：

```cpp run title="commutative.cpp" ok
int main() {
    int a[] = {10, 20, 30};
    char c = 1["abc"];         // 'b'：字符串字面量是数组左值
    int x = 2[a];              // 等价于 a[2]
    return (x == 30 && c == 'b') ? 0 : 1;
}
```

求值顺序除外，指的是 ¶1：方括号前面的那个操作数总是先求值，无论它是数组还是下标。

### 操作数要求的边界

```cpp title="sub-errors.cpp" error
struct Incomplete;
extern Incomplete* pi;
int a[3];
enum class Color { red };

void f() {
    a[{1}];          // error: 内置下标的方括号里必须是 assignment-expression，不能是花括号列表
    a[1, 2];         // error: 内置下标只接受一个实参（C++23 起）
    a[Color::red];   // error: 有作用域枚举不会隐式转换为整数
    &pi[0];          // error: T 必须是完整的对象类型——即使只是取地址
    a[1.0];          // error: 下标必须是整型或无作用域枚举
}
```

`a[1.0]` 的错误来自"另一个操作数必须是整型或无作用域枚举的 prvalue"这一要求。这里不会发生浮点到整数的转换，因为 ¶2 并没有说"转换为整型"，而 `a + 1.0` 本身在 [[expr.add]] 中就是非良构的。

### 一个经典争论：`&a[N]`

`int a[N]; int* end = &a[N];` 很常见，它按定义等于 `&*(a + N)`。`a + N` 是合法的末尾之后指针，但 `*(a + N)` 是否已经是 UB？[[expr.unary.op]] 说一元 `*` 的结果是"指向对象或函数的左值"，而末尾之后的指针并不指向对象。C 语言有一条明文规定 `&*p` 不求值 `*`，C++ 没有对应的规定，这个问题长期作为核心语言 issue 悬而未决。主流编译器都把 `&a[N]` 当作 `a + N` 处理，实际不会出问题；但如果想避免争议，可以写 `a + N` 或 `std::end(a)`。

!!! lawyer "常量求值里的表现"
    常量求值中编译器必须诊断核心语言 UB，因此编译器在常量求值中如何处理 `&a[N]`，可以看作实现者的态度。Clang 在常量表达式中接受 `constexpr const int* e = &a[3];`（`a` 有 3 个元素），但拒绝读取 `a[3]`。这不是标准的规范，只是实现的选择。

### C++23：多维下标与下标中的逗号

C++20 之前，`a[i, j]` 中的逗号是逗号运算符，整个表达式等于 `a[j]`（丢弃 `i`）。这几乎总是 bug（从 Python/Fortran/MATLAB 过来的人会以为是二维下标），也让 `operator[]` 无法接受多个参数。演进分三步：

| 版本 | `a[i, j]` 的含义 |
|---|---|
| C++98–17 | 逗号表达式，等于 `a[(i, j)]` |
| C++20 | 仍是逗号表达式，但方括号内顶层的逗号表达式被废弃 {{deprecated}}（[[P1161R3]]） |
| C++23 起 | 逗号分隔实参列表：内置下标非良构；类类型调用 `a.operator[](i, j)`（[[P2128R6]]） |

[[diff.cpp20.expr]] 把它列为与 C++20 的不兼容变化。若确实需要逗号运算符，加一层括号：`a[(i, j)]`。

与之配套，[[over.sub]] 允许 `operator[]` 有任意数量的形参（包括零个）和默认实参；C++23 还允许 `operator[]` 是静态成员函数（[[P2589R1]]）。`std::mdspan` 是标准库中第一个使用多维下标的组件。

```cpp run title="multi-subscript.cpp" ok
#include <cstddef>

struct Matrix {
    double data[3][4]{};
    double& operator[](std::size_t i, std::size_t j) { return data[i][j]; }   // C++23
};

struct Table {
    static int operator[](int i) { return i * i; }    // C++23：静态 operator[]
};

int main() {
    Matrix m;
    m[1, 2] = 3.5;                 // m.operator[](1, 2)
    int a[5]{};
    int k = 0;
    a[(k++, 4)] = 1;               // OK：括号内是逗号表达式，等于 a[4]
    return (m[1, 2] == 3.5 && Table{}[3] == 9 && a[4] == 1) ? 0 : 1;
}
```

## 后缀自增与自减（[expr.post.incr]）

### 值、操作数与副作用（¶1）

¶1 把后缀 `++` 拆成几条精确的规定：

1. 值：后缀 `++` 表达式的值是对操作数施行左值到右值转换（[[conv.lval]]）得到的值，即旧值的一份拷贝（注 1）。
2. 操作数：必须是可修改的左值（[[basic.lval#10]]）；类型是除 cv `bool` 之外的算术类型，或指向完整对象类型的指针。
3. volatile：操作数是 volatile 限定类型的用法已废弃 {{deprecated}}（[[depr.volatile.type]]，C++20，[[P1152R4]]）。
4. 副作用：操作数对象被修改，"如同它是前缀 `++` 的操作数"（[[expr.pre.incr]]），也就是加 1；指针则前进一个元素（[[expr.add]]）。
5. 顺序：`++` 表达式的值计算先序于对操作数对象的修改。
6. 单次求值：相对于非决定性先序的函数调用，后缀 `++` 的整个操作是一次求值（single evaluation）。
7. 结果：prvalue，类型是操作数类型去掉 cv 限定后的版本。

第 5、6 条需要展开说明。第 5 条保证先取旧值、再写新值，所以 `i++` 的结果确实是旧值。第 6 条（配合注 2）说的是，函数调用不能插在读旧值和写新值之间。考虑 `f(i++) + g()`，如果 `g` 也读写 `i`，标准保证 `g` 看到的要么是 `i++` 完全没发生时的 `i`，要么是完全发生之后的 `i`，不会看到已读未写的中间状态。

```cpp run title="post-incr.cpp" ok
#include <type_traits>

int main() {
    int i = 5;
    const volatile int* cvp = nullptr;
    static_assert(std::is_same_v<decltype(i++), int>);           // prvalue，类型 int
    static_assert(std::is_same_v<decltype(cvp++), const volatile int*>);  // 去掉的是指针本身的 cv（这里没有）
    int old = i++;                // old == 5, i == 6
    double d = 1.5; d++;          // 浮点也可以
    int a[3]{}; int* p = a; p++;  // 指针前进一个元素
    return (old == 5 && i == 6 && d == 2.5 && p == a + 1) ? 0 : 1;
}
```

### 不允许的操作数

```cpp title="post-incr-errors.cpp" error
struct Incomplete;
void g(Incomplete* pi, void* vp, void (*fp)()) {
    bool b = false;
    b++;            // error: C++17 起 bool 不能自增（P0002R1）
    const int c = 0;
    c++;            // error: 不是可修改的左值
    5++;            // error: 不是左值
    pi++;           // error: 指向不完整类型
    vp++;           // error: void* 不是指向对象类型的指针（GCC 作为扩展接受，-pedantic 下警告）
    fp++;           // error: 函数指针不能自增
    int i = 0;
    i++++;          // error: i++ 是 prvalue，不能再自增
}
```

`bool` 的 `++` 在 C++98 中就被废弃（效果是置为 `true`），C++17 由 [[P0002R1]] 删除 {{removed:C++17}}；`bool` 的 `--` 从来都不允许。`++i++` 也是非良构的：后缀优先级更高，等于 `++(i++)`，而 `i++` 是 prvalue。相反，`(++i)++` 是合法的，因为前缀 `++` 的结果是左值。

### 自减（¶2）

¶2：后缀 `--` 与后缀 `++` 完全类似地递减操作数。前缀版本见 [[expr.pre.incr]]。

### C++17 之后哪些是未定义的

后缀 `++` 是关于求值顺序的经典考题。C++17 的 [[P0145R3]] 给赋值、移位、下标、成员访问补上了顺序，但二元算术运算符的两个操作数之间仍然无序：

```cpp title="incr-order.cpp"
void f(int, int);

void g() {
    int i = 0;
    i = i++;        // OK（C++17 起）：右操作数先序于赋值，结果 i 仍为 0
    i = i++ + 1;    // OK（C++17 起）：i 为 1
    int j = i++ + i++;  // UB: 同一标量的两次修改彼此无序（[intro.execution]）
    f(i++, i++);    // 未指定：两个形参的初始化非决定性先序，不是 UB
    (void)j;
}
```

最后一行常被误认为 UB。C++17 起函数实参的初始化彼此非决定性先序（[[expr.call#8]]），所以两次修改有先后，只是不知道哪个在先。Clang 的 `-Wunsequenced` 对这一行仍会报"multiple unsequenced modifications"，这个警告措辞对 C++17 而言并不准确（行为是未指定，不是无序），但作为代码异味的提醒仍然有价值。

### 重载的后缀 `++`

对类类型，`a++` 调用 `operator++(int)`（[[over.inc]]），那个 `int` 形参只是用来区分前缀和后缀的哑元。标准对重载版本的返回值不作要求，但惯例是按值返回旧值的副本，与内置版本结果是 prvalue 这一点一致。这也是迭代器循环里优先写 `++it` 的原因：后缀版本要多构造一个副本，非平凡迭代器未必能被优化掉。

## 陷阱

!!! pitfall "`*p++` 改的是谁"
    `*p++ = x` 是 `*(p++) = x`：把 `x` 写入 `p` 原来指向的位置，然后 `p` 前进。想自增被指向的值，要写 `(*p)++` 或 `++*p`。

!!! pitfall "`a[i, j]` 在不同标准下含义不同"
    同一份代码，C++17 下编译通过（访问 `a[j]`），C++20 下警告，C++23 下对内置数组报错、对有多参 `operator[]` 的类调用新的重载。跨版本代码中含逗号的下标应一律加括号。

!!! pitfall "`std::move(p)[i]` 不会移动元素"
    亡值例外只针对数组操作数。对指针或 `std::vector`，`std::move(v)[i]` 的结果仍是左值（`vector::operator[]` 没有 `&&` 重载），元素不会被移动。

## 思考题

!!! question "思考题 1"
    设 `int a[2][3];`，`decltype((std::move(a)[1][2]))` 是什么？

<details markdown="1">
<summary>答案</summary>

`int&&`。`std::move(a)` 是 `int[2][3]` 的亡值；它是数组操作数，所以 `std::move(a)[1]` 是 `int[3]` 的亡值；这又是一个数组操作数，所以 `[2]` 的结果也是亡值，类型 `int`。亡值这一属性沿着数组维度一路传递。
</details>

!!! question "思考题 2"
    `"abc"[3]` 是否合法？值是什么？`&"abc"[4]` 呢？

<details markdown="1">
<summary>答案</summary>

`"abc"` 的类型是 `const char[4]`（包括结尾的 `'\0'`），所以 `"abc"[3]` 合法，是 `'\0'` 的左值。`"abc" + 4` 是末尾之后的指针，合法；`&"abc"[4]` 即 `&*("abc" + 4)`，落入上文讨论的 `&a[N]` 灰色地带：标准没有明确的豁免，实践中当作 `"abc" + 4` 处理。如果读取 `"abc"[4]`，则是 UB；`"abc"[5]` 连形成指针都已越界，UB。
</details>

!!! question "思考题 3"
    `struct S { int operator[](int) &&; }; S s;` 下，`S{}[0]` 和 `s[0]` 哪个合法？与内置数组的亡值规则有何联系？

<details markdown="1">
<summary>答案</summary>

`S{}[0]` 合法：`S{}` 是 prvalue，绑定到 `&&` 限定的隐式对象形参；`s[0]` 非良构：左值不能绑定 `&&`。重载的 `operator[]` 通过引用限定符，让用户自己表达对将亡对象取下标的语义；内置数组则由 ¶2 的例外直接规定结果为亡值。两者表达的是同一个设计意图。
</details>

## 小结

!!! summary
    - 后缀表达式左结合，优先级最高；`*p++` 是 `*(p++)`。
    - 下标前缀先序于方括号内的所有实参（C++17 起）；重载 `operator[]` 的各实参之间非决定性先序。
    - 内置 `E1[E2]` ≡ `*((E1)+(E2))`，可交换；数组操作数是左值→结果左值，否则→亡值；指针操作数总是左值。
    - 内置下标恰好一个实参，类型须完整；C++23 起 `a[i, j]` 不再是逗号表达式。
    - 后缀 `++`：操作数是可修改左值（非 bool 算术类型或指向完整对象类型的指针），结果是旧值的 prvalue；值计算先于修改，对函数调用而言是一次不可分割的求值。
