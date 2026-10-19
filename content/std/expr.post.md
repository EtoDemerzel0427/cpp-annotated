---
title: 后缀表达式
summary: 后缀运算符的语法与结合方式；内置下标 E1[E2] 就是 *((E1)+(E2))，数组操作数决定结果是左值还是亡值；C++23 的多维下标；后缀 ++/-- 的结果、副作用与求值顺序。
status: done
covers: expr.post.general, expr.sub, expr.post.incr
papers: P0145R3, P1161R3, P2128R6, P2589R1, P0002R1, P1152R4
related: expr.compound, expr.call, expr.ref, expr.add, expr.unary.op, expr.pre.incr, over.sub, over.inc, intro.execution, basic.lval
tags: 表达式, 下标, 自增, 求值顺序, 值类别
updated: 2026-10-19
---

!!! tldr
    - 后缀运算符是结合得最紧的一层，从左到右结合：`a.b[c](d)` 是 `((a.b)[c])(d)`，`*p++` 是 `*(p++)`。
    - 内置下标 `E1[E2]` 按定义就是 `*((E1)+(E2))`，所以可以交换写成 `2[a]`，指针算术的全部限制也都适用。
    - 数组操作数是左值时下标结果是左值，否则是亡值；指针操作数的下标结果总是左值。
    - C++17 起方括号前的表达式先于方括号内求值；C++23 起 `a[i, j]` 是两个实参，不再是逗号表达式。
    - 后缀 `++` 的结果是旧值的 prvalue；`i = i++` 从 C++17 起有定义，`i++ + i++` 仍是 UB。

后缀表达式包括 `a[b]`、`f(x)`、`T(x)`、`a.b`、`a->b`、`a++`、`a--`、四个具名转换和 `typeid`。这一层的语法（[[expr.post.general]]）、下标（[[expr.sub]]）和后缀自增自减（[[expr.post.incr]]）合在这里讲。函数调用、成员访问和函数式转换见 [[expr.call]]、[[expr.ref]]、[[expr.type.conv]]，各种转换见 [[expr.compound]] 的地图。

## 语法与结合方向 [expr.post.general]

¶1 后缀表达式从左到右结合。语法的各个选项如下：

```text
postfix-expression:
    primary-expression
    postfix-expression [ expression-list(opt) ]
    postfix-expression ( expression-list(opt) )
    simple-type-specifier ( expression-list(opt) )      // 函数式转换
    typename-specifier ( expression-list(opt) )
    simple-type-specifier braced-init-list
    typename-specifier braced-init-list
    postfix-expression . template(opt) id-expression
    postfix-expression . splice-expression
    postfix-expression -> template(opt) id-expression
    postfix-expression -> splice-expression
    postfix-expression ++
    postfix-expression --
    dynamic_cast < type-id > ( expression )            // 以及 static_cast 等
    typeid ( expression )
    typeid ( type-id )
```

从语法里能直接读出几件事：

- 下标和调用的括号里是 *expression-list*，也就是 *initializer-list*，所以可以出现花括号列表和包展开：`f({1, 2})`、`f(args...)`、`m[is...]`。
- 函数式转换的类型部分只能是单个类型名，`unsigned int(x)`、`int*(p)` 都写不出来（[[expr.type.conv]]）。
- `.` 和 `->` 后面可以跟 *splice-expression* {{c++26}}，如 `obj.[: r :]`（[[expr.ref]]）。
- 四个具名转换和 `typeid` 与函数调用同属一层；C 风格的 `(T)e` 属于更松的 *cast-expression*（[[expr.cast]]）。

因为左结合，链式写法从左往右逐个套上去：`p->q++` 是 `(p->q)++`，`f()[0]` 是先调用再取下标。

¶2 是一个注：具名转换里 *type-id* 后面的 `>` 可以由一个 `>>` 拆出来（[[temp.names]]）。所以 C++11 起 `static_cast<std::vector<int>>(v)` 不必写成 `> >`。

## 下标 [expr.sub]

### 先求值方括号前的部分（¶1）

```cpp run title="sub-order.cpp" ok
#include <cstdio>

int* arr() { std::puts("arr"); static int a[4]{}; return a; }
int idx() { std::puts("idx"); return 1; }

int main() {
    arr()[idx()] = 42;   // C++17 起保证先输出 arr，再输出 idx
    idx()[arr()] = 7;    // 交换写法也合法；仍是方括号前的 idx 先求值
}
```

¶1 方括号前跟一个可能为空、逗号分隔的 *initializer-clause* 列表，这样的表达式叫做 [[g:subscript-expression|下标表达式]]。列表里的各项就是下标运算符的实参。多个实参或零个实参只对重载的 `operator[]` 有意义。

求值顺序的规定是：方括号前的后缀表达式，以及重载时对象形参的初始化，先序于方括号内的每个表达式和每个默认实参。重载 `operator[]` 的各个非对象形参之间，初始化是[[g:indeterminately-sequenced|非决定性先序]]的，也就是有先后但不规定谁先，这与函数调用一致（[[expr.call#8]]）。

C++17 之前 `E1` 与 `E2` 之间无序，`m[k()] = v()` 这类代码难以推理。C++17 的求值顺序提案 [[P0145R3]] 规定 `E1` 先于 `E2`；有了多个实参之后，这条规则改写成了上面的形式。

### 内置下标就是指针加法加间接（¶2）

¶2 内置下标要求方括号里恰好有一个 *assignment-expression*。两个操作数中，一个是"`T` 的数组"类型的 glvalue 或"指向 `T` 的指针"类型的 prvalue，另一个是整型或无作用域枚举类型的 prvalue。结果类型是 `T`，`T` 必须是完整定义的对象类型；脚注说明，即使在 `&x[0]` 这种只取地址的写法里也一样。

!!! std
    The expression `E1[E2]` is identical (by definition) to `*((E1)+(E2))`, except that in the case of an array operand, the result is an lvalue if that operand is an lvalue and an xvalue otherwise.

下标不是一种独立的运算，而是指针加法（[[expr.add]]）加一元 `*`（[[expr.unary.op]]）。指针算术的规则因此原样适用于下标：只能在同一个数组对象内移动，可以形成末尾之后的指针，但不能通过它访问。

```cpp title="sub-errors.cpp" error
struct Incomplete;
extern Incomplete* pi;
int a[3];
enum class Color { red };

void f() {
    a[{1}];          // error: 内置下标里不能是花括号列表
    a[1, 2];         // error: 内置下标只接受一个实参（C++23 起）
    a[Color::red];   // error: 有作用域枚举不会隐式转换为整数
    &pi[0];          // error: T 必须完整，即使只是取地址
    a[1.0];          // error: 下标必须是整型或无作用域枚举
}
```

`a[1.0]` 不会把 `1.0` 转换为整数。¶2 只接受整型或无作用域枚举的操作数，`a + 1.0` 在 [[expr.add]] 里本身就是非良构的。

### 结果是左值还是亡值

如果按 `*((E1)+(E2))` 字面展开，数组会先转换成指针（[[conv.array]]），而 `*` 的结果总是左值，数组本身即将消亡这一信息就丢了。所以 ¶2 对数组操作数另作规定：数组是左值，结果是左值；数组是亡值，结果也是亡值。这与成员访问一致，`std::move(s).m` 也是亡值（[[expr.ref#8]]）。

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

最后一行中，`std::move(p)` 是亡值指针，但指针本身即将消亡，与它所指的对象无关，所以结果仍是左值。`A{1, 2, 3}[0]` 那一行里，数组操作数要求 glvalue，而 `A{1, 2, 3}` 是 prvalue，于是先经[[g:temporary-materialization-conversion|临时量实质化转换]]（[[conv.rval]]）得到亡值。

### 下标可以交换（¶3）

¶3 是注：下标看起来不对称，但除了求值顺序外满足交换律。`E1 + E2` 中指针和整数谁在左边都行，所以 `a[2]`、`2[a]`、`*(a + 2)` 完全等价。

```cpp run title="commutative.cpp" ok
int main() {
    int a[] = {10, 20, 30};
    char c = 1["abc"];         // 'b'：字符串字面量是数组左值
    int x = 2[a];              // 等价于 a[2]
    return (x == 30 && c == 'b') ? 0 : 1;
}
```

除了求值顺序，指的是 ¶1：方括号前的那个操作数总是先求值，不管它是数组还是下标。

### `&a[N]` 是否合法

`int a[N]; int* end = &a[N];` 很常见，它按定义是 `&*(a + N)`。`a + N` 是合法的末尾之后指针，问题在于 `*`。当前草案的 [[expr.unary.op#1]] 写明：操作数指向一个对象或函数时，结果指代它，否则行为未定义。末尾之后的指针不指向任何对象，所以按当前草案 `&a[N]` 是 UB。C 语言有明文规定 `&*p` 不对 `*` 求值，C++ 没有对应的豁免。

主流编译器实际上都把 `&a[N]` 当作 `a + N` 处理。本机 Clang 23 在常量表达式里也接受 `constexpr const int* e = &a[3];`（`a` 有 3 个元素），只拒绝读取 `a[3]`；按草案这里应当诊断。要避免争议，写 `a + N` 或 `std::end(a)`。

### C++23：多维下标

C++20 之前，`a[i, j]` 中的逗号是逗号运算符，整个表达式等于 `a[j]`。这几乎总是 bug，也让 `operator[]` 无法接受多个参数。

| 版本 | `a[i, j]` 的含义 |
|---|---|
| C++98–17 | 逗号表达式，等于 `a[(i, j)]` |
| C++20 | 仍是逗号表达式，但方括号内顶层的逗号表达式已废弃 {{deprecated}}（[[P1161R3]]） |
| C++23 起 | 两个实参：内置下标非良构，类类型调用 `a.operator[](i, j)`（[[P2128R6]]） |

[[diff.cpp20.expr]] 把它列为与 C++20 的不兼容变化。确实需要逗号运算符时加一层括号：`a[(i, j)]`。

与此配套，[[over.sub]] 允许 `operator[]` 有任意多个形参（包括零个）和默认实参；C++23 还允许它是静态成员函数（[[P2589R1]]）。`std::mdspan` 用的就是多维下标。

```cpp run title="multi-subscript.cpp" ok
#include <cstddef>

struct Matrix {
    double data[3][4]{};
    double& operator[](std::size_t i, std::size_t j) { return data[i][j]; }
};

struct Table {
    static int operator[](int i) { return i * i; }    // 静态 operator[]
};

int main() {
    Matrix m;
    m[1, 2] = 3.5;                 // m.operator[](1, 2)
    int a[5]{};
    int k = 0;
    a[(k++, 4)] = 1;               // 括号内是逗号表达式，等于 a[4]
    return (m[1, 2] == 3.5 && Table{}[3] == 9 && a[4] == 1 && k == 1) ? 0 : 1;
}
```

## 后缀自增与自减 [expr.post.incr]

### 结果与副作用（¶1）

```cpp run title="post-incr.cpp" ok
int main() {
    int i = 5;
    int old = i++;                // old == 5, i == 6
    double d = 1.5; d++;          // 浮点也可以
    int a[3]{}; int* p = a; p++;  // 指针前进一个元素
    return (old == 5 && i == 6 && d == 2.5 && p == a + 1) ? 0 : 1;
}
```

¶1 后缀 `++` 的规定可以按下面的顺序理解：

1. 操作数必须是可修改的左值（[[basic.lval#10]]），类型是除 cv `bool` 以外的算术类型，或指向完整对象类型的指针。
2. 表达式的值是对操作数做左值到右值转换（[[conv.lval]]）得到的值。注 1 说明，这是原值的一份拷贝。
3. 操作数对象被修改，效果如同它是前缀 `++` 的操作数（[[expr.pre.incr]]）：数值加 1，指针前进一个元素。
4. 取值先序于修改。
5. 对于与它非决定性先序的函数调用来说，后缀 `++` 的整个操作是一次求值。
6. 结果是 prvalue，类型是操作数类型去掉 cv 限定。

此外，操作数是 volatile 限定类型的用法已经废弃 {{deprecated}}（[[depr.volatile.type]]，C++20 的 [[P1152R4]]）。

第 5 条配合注 2 的意思是，函数调用不能插进读旧值和写新值之间。在 `f(i++) + g()` 中，如果 `g` 也读写 `i`，`g` 看到的要么是自增完全没发生时的 `i`，要么是完全发生之后的 `i`，不会看到读了还没写的中间状态。

### 不允许的操作数

```cpp title="post-incr-errors.cpp" error
struct Incomplete;
void g(Incomplete* pi, void* vp, void (*fp)()) {
    bool b = false;
    b++;            // error: C++17 起 bool 不能自增
    const int c = 0;
    c++;            // error: 不是可修改的左值
    5++;            // error: 不是左值
    pi++;           // error: 指向不完整类型
    vp++;           // error: void* 不是指向对象类型的指针
    fp++;           // error: 函数指针不能自增
    int i = 0;
    i++++;          // error: i++ 是 prvalue，不能再自增
}
```

`bool` 的 `++` 在 C++98 中效果是置为 `true`，当时就已废弃，C++17 由 [[P0002R1]] 删除 {{removed:C++17}}；`bool` 的 `--` 一直不允许。`vp++` 被 GCC 作为扩展接受，加 `-pedantic` 时警告。`++i++` 等于 `++(i++)`，同样非良构；`(++i)++` 则合法，因为前缀 `++` 的结果是左值。

¶2 后缀 `--` 以同样的方式让操作数减 1。前缀版本见 [[expr.pre.incr]]。

### 哪些写法仍是 UB

C++17 的 [[P0145R3]] 给赋值、移位、下标、成员访问补上了顺序，但 `+`、`*` 这类二元算术运算符的两个操作数之间仍然无序：

```cpp title="incr-order.cpp"
void f(int, int);

void g() {
    int i = 0;
    i = i++;            // OK（C++17 起）：右操作数先序于赋值，i 仍为 0
    i = i++ + 1;        // OK（C++17 起）：i 为 1
    int j = i++ + i++;  // UB: 对同一标量的两次修改彼此无序
    f(i++, i++);        // 未指定：两个形参的初始化非决定性先序，不是 UB
    (void)j;
}
```

最后一行常被误认为 UB。C++17 起，函数各形参的初始化（连同各自实参的求值）彼此非决定性先序（[[expr.call#8]]），两次修改有先后，只是不规定哪个在先。本机 Clang 23 对这一行仍报 `-Wunsequenced`（multiple unsequenced modifications），这个措辞在 C++17 下不准确，但作为提醒仍然有用。

### 重载的后缀 `++`

对类类型，`a++` 调用 `operator++(int)`（[[over.inc]]），那个 `int` 形参只用来和前缀版本区分。标准不限制重载版本的返回值，惯例是按值返回旧值的副本，与内置版本一致。正因为要多构造一个副本，迭代器循环里通常写 `++it`。

## 常见误解

!!! pitfall "`*p++` 改的是指针"
    `*p++ = x` 是 `*(p++) = x`：把 `x` 写入 `p` 原来指向的位置，然后 `p` 前进。要自增被指向的值，写 `(*p)++` 或 `++*p`。

!!! pitfall "`a[i, j]` 在不同标准下含义不同"
    同一份代码，C++17 下访问 `a[j]`，C++20 下得到废弃警告，C++23 下对内置数组报错、对有多参 `operator[]` 的类调用新的重载。要兼容多个版本，下标里的逗号表达式一律加括号。

!!! pitfall "`std::move(v)[i]` 会移动元素"
    亡值的规定只针对内置数组操作数。`std::vector::operator[]` 没有 `&&` 重载，`std::move(v)[i]` 仍是左值，元素不会被移动。

## 思考题

!!! question "思考题 1"
    设 `int a[2][3];`，`decltype((std::move(a)[1][2]))` 是什么？

<details markdown="1">
<summary>答案</summary>

`int&&`。`std::move(a)` 是 `int[2][3]` 的亡值，作为数组操作数，`std::move(a)[1]` 是 `int[3]` 的亡值；它又是数组操作数，所以 `[2]` 的结果也是亡值，类型是 `int`。亡值沿着数组的每一维传下去。
</details>

!!! question "思考题 2"
    `"abc"[3]` 合法吗？值是什么？`&"abc"[4]` 呢？

<details markdown="1">
<summary>答案</summary>

`"abc"` 的类型是 `const char[4]`，包括结尾的 `'\0'`，所以 `"abc"[3]` 合法，是 `'\0'` 的左值。`"abc" + 4` 是末尾之后的指针，合法；`&"abc"[4]` 即 `&*("abc" + 4)`，按当前草案的 [[expr.unary.op#1]]，对不指向对象的指针做 `*` 是 UB，和上文的 `&a[N]` 一样，实践中编译器当作 `"abc" + 4` 处理。`"abc"[5]` 连指针都已越界，是 UB。
</details>

!!! question "思考题 3"
    `struct S { int operator[](int) &&; }; S s;` 下，`S{}[0]` 和 `s[0]` 哪个合法？这与内置数组的亡值规则有什么联系？

<details markdown="1">
<summary>答案</summary>

`S{}[0]` 合法：`S{}` 是 prvalue，可以绑定到 `&&` 限定的隐式对象形参。`s[0]` 非良构：左值不能绑定 `&&`。重载的 `operator[]` 通过引用限定符区分对将亡对象取下标的情形，内置数组则由 ¶2 直接规定结果为亡值，两者表达的是同一个意图。
</details>
