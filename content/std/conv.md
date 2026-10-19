---
title: 标准转换
summary: 语言内建的全部隐式转换：左值到右值、数组和函数到指针、临时量实质化、限定转换、整型和浮点提升、各种算术转换、指针和成员指针转换、布尔转换，以及它们按什么顺序组成标准转换序列。
status: done
covers: "*"
papers: P0135R1, P0388R4, P0012R1, P1236R1, P1957R2, P1467R9, P0482R6
related: basic.lval, expr.arith.conv, over.best.ics, over.ics.rank, dcl.init, dcl.init.list, conv.rank, topics/value-categories
tags: 转换, 提升, 限定转换, 指针, UB
updated: 2026-10-19
---

!!! tldr
    - 一个标准转换序列最多由四步组成：读值或退化、一个算术或指针转换、去掉 `noexcept`、加 cv。所以 `Derived*` 不能先变 `Base*` 再变 `void*`，它直接变 `void*`。
    - 提升（`short` → `int`、`float` → `double` 等）和转换在值上可能毫无差别，但在重载决议中提升排名更高。
    - 整数之间的转换总是良定义的（模 2<sup>N</sup>）；浮点转整数在截断后放不下时是 UB。
    - `T**` 不能隐式转换为 `const T**`，只能转换为 `const T* const*`：内层加了 `const`，外面各层也必须是 `const`。
    - 空指针常量只有值为零的整数字面量和 `nullptr`；指针、成员指针和浮点数转换为 `bool` 在列表初始化中都是窄化。

## 标准转换序列 [conv.general]

```cpp ok
struct Base {}; struct Derived : Base {};
void take(const void*);

void demo(Derived* d, short s, int arr[3]) {
    take(d);          // 指针转换 Derived* → void*，再限定转换 → const void*
    double x = s;     // 一步：浮点-整型转换
    long n = arr[0];  // 读值，再整型转换
    (void)x; (void)n;
}
```

**标准转换**（standard conversion）是具有内建含义的隐式转换。`int` 能传给 `long` 形参、数组名能当指针用、`char*` 能赋给 `const char*`、`if (p)` 能判断指针非空，依据都在这一节。

¶1 **标准转换序列**（[[g:standard-conversion-sequence]]）是按下面顺序排列的一串标准转换，每一步最多一个，序列也可以为空：

1. 左值到右值、数组到指针、函数到指针三者之一；
2. 整型提升、浮点提升、整型转换、浮点转换、浮点-整型转换、指针转换、成员指针转换、布尔转换八者之一；
3. 函数指针转换；
4. 限定转换。

需要时，对表达式施加一个标准转换序列，把它变成所需的类型和值类别。

第 2 步只能有一个转换，所以不能连做两次。`short` 能转换为 `double`，是因为浮点-整型转换的源可以是任何整数类型，而不是先提升为 `int` 再转换。`Derived*` → `void*` 本身就是一个指针转换，不经过 `Base*`。

各转换在重载决议中的等级定义在 [[over.ics.scs]]。提升和转换的区分只在那里有意义：

| 转换 | 本页小节 | 重载决议中的等级 |
|---|---|---|
| 左值到右值、数组到指针、函数到指针 | [[conv.lval]]、[[conv.array]]、[[conv.func]] | 精确匹配 |
| 限定转换、函数指针转换 | [[conv.qual]]、[[conv.fctptr]] | 精确匹配 |
| 整型提升、浮点提升 | [[conv.prom]]、[[conv.fpprom]] | 提升 |
| 整型、浮点、浮点-整型、指针、成员指针、布尔转换 | [[conv.integral]] 等 | 转换 |
| 临时量实质化 | [[conv.rval]] | 不属于标准转换序列 |

### 隐式转换发生在哪里（¶2–¶8）

¶2 是一条注释，列出了表达式被隐式转换的场合：作为运算符的操作数；作为 `if` 或循环的条件（目标是 `bool`）；作为 `switch` 的表达式（目标是整数类型）；作为初始化的源，包括函数实参和 `return` 的操作数。

别处经常用到下面三个定义，它们都借助一个虚构的声明：

| 术语 | 定义 | 用在哪里 |
|---|---|---|
| ¶3 `E` 可隐式转换为 `T` | `T t = E;` 良构 | 到处都是，如 `std::is_convertible` |
| ¶4 `E` 按语境转换为 `bool` | `bool t(E);` 良构 | `if`、`while`、`for` 的条件，`!`、`&&`、`\|\|`，`?:` 的第一操作数，`static_assert`，`noexcept(E)`，`explicit(E)` |
| ¶5 类类型的 `E` 按语境隐式转换为某类型 | 在类中找非 explicit 的转换函数，其返回类型（cv `T` 或它的引用）中的 `T` 为语境所允许，这样的 `T` 必须恰好一个 | `switch` 的条件、数组 `new` 的长度、`delete` 的操作数 |

¶3 和 ¶4 的区别就是复制初始化和直接初始化的区别：直接初始化会考虑 `explicit` 转换函数。`explicit operator bool` 就是这样工作的：

```cpp error
struct Handle { explicit operator bool() const { return true; } };

void demo(Handle h) {
    if (h) {}                // OK：bool t(h);
    bool ok = h && true;     // OK：&& 的操作数也按语境转换
    bool bad = h;            // error: 复制初始化不考虑 explicit 转换函数
    int n = h + 1;           // error: 不会经由 bool 再提升为 int
}
```

¶5 要求恰好一个 `T`：

```cpp error
struct One { operator int() const; };
struct Two { operator int() const; operator long() const; };

void demo(One a, Two b) {
    switch (a) { case 1: break; }   // OK：只有 T = int
    switch (b) { case 1: break; }   // error: int 和 long 两个候选
}
```

¶6 隐式转换的效果等同于执行那个虚构的声明和初始化，再把虚构的变量当作结果。`T` 是左值引用或函数的右值引用时，结果是 lvalue；是对象的右值引用时，结果是 xvalue；否则是 prvalue。这和显式转换（[[expr.static.cast]]）的规则一致。

¶7 和 ¶8 是注释。类类型还要考虑用户定义转换（[[class.conv]]），一般的隐式转换序列是标准转换序列、用户定义转换、再一个标准转换序列（[[over.best.ics]]）。有些语境会抑制某些转换，例如一元 `&` 的操作数不做左值到右值转换。

## 左值到右值转换 [conv.lval]

这个名字有误导性，脚注也承认是出于历史原因。它把任何非函数、非数组类型的 glvalue（lvalue 和 xvalue 都可以）变成 prvalue，本质上就是读出对象的值。

### 类型（¶1）

¶1 非函数、非数组类型 `T` 的 glvalue 可以转换为 prvalue。`T` 是不完整类型时，需要这个转换的程序非良构。`T` 是非类类型时，prvalue 的类型是去掉 cv 的 `T`，所以 `const int` 读出来是 `int`；类类型则保留 cv。脚注指出，C++ 的类和数组 prvalue 可以带 cv，这一点与 C 不同。

### 什么时候不真的读（¶2）

¶2 对表达式 `E` 施行左值到右值转换时，如果 `E` 不是潜在求值的（如在 `sizeof` 中），或者 `E` 的求值落在它潜在结果中的某个 `Ex` 上，而 `Ex` 命名的变量 `x` 没有被 odr-use（[[basic.def.odr]]），就不访问对象中的值。第二种情形主要是常量：constexpr 变量在常量表达式中使用时不构成 odr-use，值在编译期就已知。

```cpp run title="not-accessed.cpp" ub
struct S { int n; };

auto f() {
    S x{1};
    constexpr S y{2};
    return [&](bool b) { return (b ? y : x).n; };
}

int main() {
    auto g = f();
    int n = g(true);     // OK：不访问 y.n
    int m = g(false);    // UB：访问 x.n，而 x 的生命周期已经结束
    return n + m;
}
```

`(b ? y : x).n` 的潜在结果包括 `y.n` 和 `x.n`。`g(true)` 选中 `y.n`，`y` 是 constexpr 且没有被 odr-use，于是转换直接产生常量 2，不访问那个早已销毁的 `y`。

### 结果（¶3）

¶3 结果按以下规则确定：

- ¶3.1 `T` 是 cv `std::nullptr_t` 时，结果是空指针常量。它不访问对象，所以即使 `T` 带 `volatile` 也没有副作用，glvalue 甚至可以指代 union 的非活跃成员。
- ¶3.2 `T` 是类类型时，用这个 glvalue 复制初始化结果对象，也就是调用复制构造函数（xvalue 则调用移动构造函数）。读一个类对象不是访问，而是一次构造函数调用。
- ¶3.3 对象值表示中的位对它的类型无效时，行为未定义。
- ¶3.4 否则读取对象（[[defns.access]]）。设对象中的值为 `V`：`T` 是整数类型时，结果是与 `V` 同余的 `T` 类型的值；`T` 带 `volatile` 而 `V` 是在该求值中无效的指针值时，结果是 `reinterpret_cast<T>(reinterpret_cast<std::uintptr_t>(V))`；其他情况结果就是 `V`。

```cpp run title="bad-bool.cpp" ub
#include <cstring>
#include <cstdio>

bool f() {
    bool b = true;
    char c = 42;
    std::memcpy(&b, &c, 1);
    return b;    // UB：42 不是 bool 的有效值表示
}

int main() { std::printf("%d\n", f()); }
```

用 `-fsanitize=undefined` 运行，UBSan 报告 `load of value 42, which is not a valid value for type 'bool'`。不开 sanitizer 时后果可能很奇怪：编译器知道 `bool` 只有 0 和 1，可能用它直接索引一个两元素的表，也可能让 `b` 和 `!b` 同时为真。

¶3.4 的同余规则照顾的是通过对应的有/无符号类型访问对象（[[basic.lval#11]] 允许的别名）：用 `unsigned` 的 glvalue 读一个值为 −1 的 `int` 对象，得到 `UINT_MAX`。volatile 那一条的意思是，volatile 存储可能被外部修改，从中读出的失效指针按由整数转换来的指针对待，编译器不能对它的来源做任何假设。

!!! note "读未初始化的变量 {{c++26}}"
    读未初始化对象的规则不在这里，而在 [[basic.indet]]。C++26 起，自动存储期变量（没有标 `[[indeterminate]]`）未初始化时具有错误值，读它是错误行为 {{erroneous}}：得到实现选定的某个值，实现可以诊断，但不再是 UB。动态存储期对象和标了 `[[indeterminate]]` 的变量仍具有不确定值，读它通常是 UB。如果错误值恰好不是该类型的有效值（比如 `bool`），仍按上面的无效值表示规则是 UB。

    ```cpp eb
    int main() {
        int x;          // C++26：x 具有错误值
        return x;       // 错误行为，不是 UB
    }
    ```

## 数组到指针、函数到指针 [conv.array] [conv.func]

[conv.array] ¶1 类型为 `N` 个 `T` 的数组或 `T` 的未知边界数组的表达式 `E`，可以转换为指向 `T` 的指针。如果 `E` 是 prvalue，先实质化（数组 prvalue 也需要一个对象，指针才有东西可指）。如果 `E` 的结果是一个类型与 `E` 的类型相似的对象，结果指向它的首元素；否则行为未定义。

```cpp ok
using Arr = int[3];
int k = Arr{1, 2, 3}[1];      // 数组 prvalue 被实质化，k == 2
int* dangling = Arr{1, 2, 3}; // 良构，但临时数组在完整表达式结束时销毁：悬垂指针
```

Clang 对第二行给出 `-Wdangling` 警告。最后那条 UB 规则处理的是表达式类型与实际对象不符的情形，有了它，编译器可以信赖数组表达式的类型，包括它的边界：

```cpp run title="array-ub.cpp" ub
int main() {
    int a3[3] = {1, 2, 3};
    int (&r4)[4] = reinterpret_cast<int(&)[4]>(a3);   // 转换本身可以
    int* p = r4;    // UB：r4 指代的对象是 int[3]，与 int[4] 不相似
    return p[0] - 1;
}
```

[conv.func] ¶1 函数类型 `T` 的 lvalue 可以转换为指向 `T` 的指针，结果指向该函数。脚注指出，它从不适用于非静态成员函数，因为得不到指代非静态成员函数的 lvalue：`obj.mf` 只能立即调用，`&C::mf` 得到的是成员指针而不是函数指针。

```cpp ok
void f(int);
void (*p1)(int) = f;    // 函数到指针转换
void (*p2)(int) = &f;   // 取地址：不需要转换
void (&r)(int) = f;     // 绑定函数引用：不转换
auto p3 = *****f;       // 每个 * 都把指针解引用为函数 lvalue，它又退化为指针
```

## 临时量实质化 [conv.rval]

¶1 类型 `T` 的 prvalue 可以转换为类型 `T` 的 xvalue。转换以一个临时对象（[[class.temporary]]）作为 prvalue 的结果对象来求值它，从而初始化这个临时对象，并产生指代它的 xvalue。`T` 必须是完整类型；注释补充，类类型（或其数组）还必须有可访问、未删除的析构函数。

```cpp ok
struct X { int n; };
int k = X().n;          // X() 是 prvalue，成员访问需要对象：实质化
const X& r = X{42};     // 绑定引用：实质化，临时对象的生命周期延长到 r 结束
```

C++17 起 prvalue 本身不是对象（[[basic.lval#5]]）。需要一个对象而语境又没有提供结果对象时，就靠这个转换实质化出一个。触发的场合见 [[basic.lval#7]] 和 [[class.temporary#2]]：绑定引用、成员访问、数组下标和退化、弃值表达式、`std::initializer_list` 的底层数组等。这个条款的 stable name `conv.rval` 是沿用旧名，C++17 之前它描述的是另一种转换。

## 限定转换 [conv.qual]

限定转换允许给指针（和成员指针、数组）的各层加上 cv。它定义的几个概念也被别处使用：[[expr.type#3]] 的复合指针类型、[[dcl.init.ref]] 的引用相关、[[basic.lval#11]] 的相似类型。

### 限定分解和相似类型（¶1、¶2）

¶1 把一个类型写成

> cv<sub>0</sub> P<sub>0</sub> cv<sub>1</sub> P<sub>1</sub> ⋯ cv<sub>n−1</sub> P<sub>n−1</sub> cv<sub>n</sub> U （n ≥ 0）

的形式，叫做它的一个**限定分解**（qualification-decomposition）。每个 P<sub>i</sub> 是指向、类 C<sub>i</sub> 的成员指针、N<sub>i</sub> 个元素的数组、未知边界数组之一。数组本身没有 cv，所以元素类型的 cv<sub>i+1</sub> 也当作数组的 cv<sub>i</sub>。

一个类型可以有多个分解，取决于剥到哪一层为止。`const int**` 的分解中 `U` 可以是 `int`、指向 `const int` 的指针、指向指向 `const int` 的指针的指针。最长的分解是：

| cv<sub>0</sub> | P<sub>0</sub> | cv<sub>1</sub> | P<sub>1</sub> | cv<sub>2</sub> | U |
|---|---|---|---|---|---|
| 无 | 指向 | 无 | 指向 | `const` | `int` |

¶2 两个类型如果有 n 相同的分解，对应的 P<sub>i</sub> 相同（或一个是已知边界数组、另一个是未知边界数组），并且 `U` 相同，就说它们**相似**（[[g:similar-types|similar]]）。直观地说，把所有层的 cv 都去掉、并忽略数组边界之后两个类型相同。

| T1 | T2 | 相似？ |
|---|---|---|
| `int**` | `const int* const*` | 是 |
| `int[3]` | `const int[]` | 是 |
| `int B::* const*` | `const int B::**` | 是 |
| `int*` | `unsigned*` | 否：`U` 不同 |
| `Derived*` | `Base*` | 否 |
| `int(*)[3]` | `int**` | 否：P<sub>1</sub> 一个是数组，一个是指针 |

### 什么转换是安全的

```cpp error
int main() {
    const char c = 'c';
    char* pc;
    const char** pcc = &pc;   // #1：假如允许（实际上 error）
    *pcc = &c;                // 通过 pcc 把 const char* 写进 pc 这个 char* 槽位
    *pc = 'C';                // #2：通过 pc 修改了 const 对象 c
}
```

这是标准注释里的反例。问题出在中间层：`const char**` 的中间层是一个可写的、指向 `const char` 的指针槽位。允许 `char**` → `const char**`，就等于允许把指向 const 的指针写进只该存放指向非 const 的指针的槽位。

修复办法是：内层加了 `const`，中间层也必须是 `const`。`char**` → `const char* const*` 是安全的，因为中间层不可写，没法把 `&c` 放进去。

### 限定合成类型（¶3）

¶3 把这个规则写成了精确的算法。`T1` 和 `T2` 的**限定合成类型**（qualification-combined type）`T3` 是与 `T1` 相似、并且分解满足下列条件的类型：

- ¶3.1 每个 i > 0，cv3<sub>i</sub> 是 cv1<sub>i</sub> 和 cv2<sub>i</sub> 的并；
- ¶3.2 P1<sub>i</sub> 或 P2<sub>i</sub> 是未知边界数组时，P3<sub>i</sub> 是未知边界数组，否则是 P1<sub>i</sub>；
- ¶3.3 如果得到的 cv3<sub>i</sub> 与 cv1<sub>i</sub> 或 cv2<sub>i</sub> 不同，或者 P3<sub>i</sub> 与 P1<sub>i</sub> 或 P2<sub>i</sub> 不同，就给所有 0 < k < i 的 cv3<sub>k</sub> 加上 `const`。

`T1` 和 `T2` 的限定合成类型恰好是 `T2` 时，`T1` 类型的 prvalue 可以转换为 `T2`。换句话说，`T1` → `T2` 合法当且仅当：两者相似；每一层 `T2` 的 cv 都不少于 `T1`，数组边界只能从已知变为未知；某一层发生了变化时，它外面第 1 到 i−1 层在 `T2` 中都是 `const`。最外层的 cv<sub>0</sub> 不参与，它是 prvalue 自己的顶层限定，本来就会被去掉。

注 2 指出，对任意两个相似类型，两者都能转换为它们的限定合成类型，[[expr.type#3]] 正是利用这一点定义复合指针类型。

<div class="compare" markdown="1">

```cpp ok
void demo(int** pp, int (*pa)[3]) {
    const int* const* a = pp;
    int* const* b = pp;
    const int (*c)[3] = pa;
    int (*d)[] = pa;       // C++20
    (void)a; (void)b;
    (void)c; (void)d;
}
```

```cpp error
void demo(int** pp,
          int (**ppa)[3]) {
    // error: 中间层不是 const
    const int** a = pp;
    // error: 应为 int (* const*)[]
    int (**b)[] = ppa;
}
```

</div>

!!! lawyer "丢掉数组边界为什么也要外层 const"
    假如允许 `int(**)[3]` → `int(**)[]`，就可以通过后者写入一个指向 `int[5]` 的指针（`int(*)[5]` 能转换为 `int(*)[]`），原来的 `int(*)[3]` 槽位就指向了一个 5 个元素的数组，边界信息被破坏。这和 `const` 的漏洞结构相同，所以用同一条规则堵上。

¶4 和 ¶5 是注释。¶4 给出最常见的单层情形：*cv2* `T` 比 *cv1* `T` 限定更多时，指向 *cv1* `T` 的指针可以转换为指向 *cv2* `T` 的指针，成员指针同理。¶5 指出函数类型从不带 cv 限定（[[dcl.fct]]）：成员函数的 `const` 是函数类型的一部分，不是 cv 限定，所以 `void (C::*)()` 不能经限定转换变为 `void (C::*)() const`。

## 整型提升与浮点提升 [conv.prom] [conv.fpprom]

```cpp run title="promotion-overload.cpp" ok
#include <cstdio>
int f(int)      { return 1; }
int f(long)     { return 2; }
int f(unsigned) { return 3; }

int main() {
    short s = 1; unsigned short us = 1; char c = 'a'; bool b = true;
    // 全部选中 f(int)：提升优于转换
    std::printf("%d %d %d %d\n", f(s), f(us), f(c), f(b));   // 1 1 1 1
}
```

**整型提升**（[[g:integral-promotion]]）把比 `int` 窄的整数类型变成 `int` 或 `unsigned int`。它来自 C：`int` 对应机器的自然字长，比它窄的运算都先扩展到 `int` 再做。提升发生在算术运算的操作数上（[[expr.arith.conv]]）和可变参数函数的实参上（[[expr.call]]），在重载决议中排名高于一般的整型转换。

### 窄整数（¶1、¶2）

¶2 对于不是位域的 prvalue，如果它的类型是整数转换等级（[[conv.rank]]）低于 `int` 的整数类型（`bool`、`char8_t`、`char16_t`、`char32_t`、`wchar_t` 除外），`int` 能表示源类型的全部值时提升为 `int`，否则提升为 `unsigned int`。

在 `int` 是 32 位的平台上，`signed char`、`unsigned char`、`char`、`short`、`unsigned short` 都提升为 `int`。如果某个平台上 `short` 与 `int` 一样宽，`unsigned short` 就提升为 `unsigned int`。

¶1 为位域定义了一个术语：**被转换的位域**（converted bit-field）是对位域施行左值到右值转换得到的 prvalue。位域另有规则（¶5），看位宽而不是声明类型。

### 枚举（¶3、¶4）

¶3 底层类型不固定的无作用域枚举，提升为 `int`、`unsigned int`、`long`、`unsigned long`、`long long`、`unsigned long long` 中第一个能表示该枚举全部值（[[dcl.enum]]）的类型。这里看的是枚举的值域，不是底层类型。都不能表示时，提升为等级高于 `long long` 的、能表示全部值的最低等级扩展整数类型（有两个时选有符号的）。

¶4 底层类型固定的无作用域枚举可以提升为它的底层类型；底层类型自己还能提升时，也可以提升为提升后的类型。两者都是提升，但 [[over.ics.rank]] 规定前者更好：

```cpp ok
#include <type_traits>
enum E : short { e };
int  g(short);
long g(int);
static_assert(std::is_same_v<decltype(g(e)), int>);  // 选 g(short)：提升到底层类型更好
static_assert(std::is_same_v<decltype(+e), int>);    // 算术中继续提升为 int
```

¶4 的注释说明，枚举类型的位域按普通枚举值处理。有作用域枚举（`enum class`）没有任何提升。

### 位域（¶5）

¶5 整数类型的被转换位域，`int` 能表示它的全部值时提升为 `int`，否则 `unsigned int` 能表示时提升为 `unsigned int`。两者都不能时 ¶5 不适用，回到 ¶2 按声明类型的等级处理，例如 40 位的 `unsigned long long` 位域不提升。

```cpp ok
#include <type_traits>
struct BF {
    unsigned a : 3;               // int 能表示 0..7 → int
    unsigned u31 : 31;            // int 能表示 → int
    unsigned u32 : 32;            // int 不能，unsigned 能 → unsigned
    unsigned long long big : 40;  // 都不能 → 不提升
};
BF bf;
static_assert(std::is_same_v<decltype(+bf.a), int>);
static_assert(std::is_same_v<decltype(+bf.u31), int>);
static_assert(std::is_same_v<decltype(+bf.u32), unsigned>);
static_assert(std::is_same_v<decltype(+bf.big), unsigned long long>);
```

!!! pitfall "无符号位域参与运算后是有符号的"
    `unsigned a : 3;` 参与运算时提升为 `int`，所以 `bf.a - 4` 可以是负数，这和 `unsigned` 变量的行为不同。

### 字符类型和 `bool`（¶6–¶8）

¶6 `char8_t`、`char16_t`、`char32_t`、`wchar_t`（包括还没按上文提升的这些类型的位域）提升为 `int`、`unsigned int`、`long`、`unsigned long`、`long long`、`unsigned long long`、其底层类型中第一个能表示底层类型全部值的类型。

| 类型 | 底层类型（典型） | 提升为（`int` 为 32 位） |
|---|---|---|
| `char8_t` | `unsigned char` | `int` |
| `char16_t` | `uint_least16_t` | `int` |
| `char32_t` | `uint_least32_t` | `unsigned int` |
| `wchar_t` | Linux、macOS 上是 `int`，Windows 上是 `unsigned short` | `int` |

¶7 `bool` 可以提升为 `int`，`false` 变成 0，`true` 变成 1。¶8 以上统称整型提升。

### 浮点提升

[conv.fpprom] ¶1 `float` 可以转换为 `double`，值不变；¶2 这叫**浮点提升**。只有这一种是提升。`float` → `long double`、`double` → `long double` 以及涉及扩展浮点类型的转换都是浮点转换，在重载决议中排名更低：

```cpp error
int g(double);
int g(long double);
int h(long double);
int h(int);
int x = g(1.0f);   // 选 g(double)：提升
int y = h(1.0f);   // error: float → long double 和 float → int 都是转换，有歧义
```

可变参数函数的实参也会做浮点提升，所以 `printf("%f", 1.0f)` 收到的是 `double`，`%f` 对 `float` 和 `double` 都适用（[[expr.call]]）。

## 算术类型之间的转换 [conv.integral] [conv.double] [conv.fpint]

### 整型转换总是良定义的

[conv.integral] ¶1 整数类型可以转换为另一种整数类型，无作用域枚举也可以转换为整数类型。¶2 目标是 `bool` 时见下文的布尔转换；源是 `bool` 时，`false` 变成 0，`true` 变成 1。¶3 其他情况：

!!! std
    the result is the unique value of the destination type that is congruent to the source integer modulo 2^N, where N is the width of the destination type.

    结果是目标类型中与源整数模 2^N 同余的唯一值，N 是目标类型的宽度。

所以整型转换既没有 UB，也没有实现定义的行为：

```cpp run title="modular.cpp" ok
#include <cstdio>
int main(int argc, char**) {
    long long ll = 1LL << 40;
    int i = (int)ll;                             // 2^40 mod 2^32 = 0
    signed char sc = (signed char)(200 * argc);  // 200 - 256 = -56
    unsigned u = -1;                             // UINT_MAX
    std::printf("%d %d %u\n", i, sc, u);         // 0 -56 4294967295
}
```

¶4 能作为整型提升的转换不算整型转换，所以 `short` → `int` 是提升而不是转换，这会影响重载决议。

!!! history "C++20 之前"
    C++20 之前，转换到有符号类型而值放不下时，结果由实现定义。C++20 规定有符号整数用二进制补码表示（[[P1236R1]]），这种转换随之定义为模运算。它和算术溢出不同：`INT_MAX + 1` 仍是 UB（[[expr.pre]]），`(int)(INT_MAX + 1LL)` 则良定义，结果是 `INT_MIN`。

### 浮点转换

[conv.double] ¶1 浮点类型可以转换为浮点转换等级（[[conv.rank]]）大于或等于它的另一种浮点类型；三种标准浮点类型（`float`、`double`、`long double`）之间可以任意互相转换。这种不对称来自 C++23 的扩展浮点类型（[[P1467R9]]）：

- `float` → `double` → `long double`：等级递增，总能隐式转换。
- `double` → `float`：都是标准类型，为了与 C 兼容可以隐式转换。不过在列表初始化中，除非源是常量且转换后不溢出，否则是窄化。
- `double` → `std::float16_t`：目标等级更低，又不是两个标准类型之间，不能隐式转换，必须写 `static_cast`。
- `std::float32_t` ↔ `float`（两者值集相同时）：等级相等，可以隐式转换。

¶2 源值能在目标类型中精确表示时，结果就是它；源值落在两个相邻的目标值之间时，结果是两者之一，选哪个由实现定义（通常按当前舍入模式就近舍入）；否则行为未定义。超出 `float` 范围的 `double`（如 `1e300`）算不算落在最大有限值和 +∞ 之间，条文没有明说；实践中 IEEE 实现得到 +∞，Clang 在常量求值中也接受 `constexpr float f = 1e300;`。¶3 能作为浮点提升的转换不算浮点转换。

### 浮点转整数：越界是 UB

[conv.fpint] ¶1 浮点类型可以转换为整数类型，转换时截断，丢弃小数部分。截断后的值放不下时，行为未定义。目标是 `bool` 时见布尔转换。

```cpp run title="fpint.cpp" ub
#include <cstdio>
int main(int argc, char**) {
    double d = 3e10 * argc;
    int i = (int)d;                          // UB：3e10 放不进 int
    unsigned ok = (unsigned)(-0.5 * argc);   // OK：截断为 0
    unsigned bad = (unsigned)(-1.5 * argc);  // UB：截断为 -1，unsigned 放不下
    std::printf("%d %u %u\n", i, ok, bad);
}
```

UBSan（`-fsanitize=float-cast-overflow`，包含在 `undefined` 中）报告 `3e+10 is outside the range of representable values of type 'int'`。整数之间的转换是模运算，浮点到整数却是 UB，原因在硬件：x86 的 `cvttsd2si` 越界时返回 `0x80000000`，ARM 的 `fcvtzs` 饱和到最大或最小值（本机 arm64 上 `i` 打印为 2147483647）。定为 UB，编译器就可以直接用一条硬件指令。需要确定结果时，先检查范围。

¶2 整数类型或无作用域枚举可以转换为浮点类型。能精确表示时结果精确；在可表示范围内但不能精确表示时，结果是相邻的较低或较高的可表示值，选哪个由实现定义；超出可表示范围时行为未定义。源是 `bool` 时，`false` 变成 0，`true` 变成 1。

```cpp ok
float f = 16777217;     // 2^24 + 1：float 不能精确表示，得到 16777216 或 16777218
double d = 1LL << 62;   // 精确
```

## 指针转换 [conv.ptr]

### 空指针常量（¶1）

```cpp error
int* p1 = 0;            // OK：值为零的整数字面量
int* p2 = 0L;           // OK
int* p3 = nullptr;      // OK
const int zero = 0;
int* p4 = zero;         // error: zero 不是字面量（C++03 中可以）
int* p5 = '\0';         // error: 字符字面量不是整数字面量
int* p6 = false;        // error: 布尔字面量不是整数字面量
```

¶1 **空指针常量**（[[g:null-pointer-constant]]）是值为零的整数字面量，或 `std::nullptr_t` 类型的 prvalue。它可以转换为任何指针类型，结果是该类型的空指针值（[[basic.compound]]），与任何对象指针或函数指针的值都不同。这叫空指针转换。

两个细节。第一，空指针常量转换为指向 cv 限定类型的指针是一个转换，而不是指针转换加限定转换，这在重载决议中有意义。第二，整数类型的空指针常量可以转换为 `std::nullptr_t` 类型的 prvalue；注释提醒，结果不是空指针值，因为 `std::nullptr_t` 不是指针类型。

!!! history "空指针常量的收紧"
    C++03 的空指针常量是值为零的整型常量表达式，`zero`、`'\0'`、`false`、`1 - 1` 都算。这在模板中带来麻烦：一个值依赖的表达式是不是空指针常量，要到实例化时才知道，而这又会改变重载决议。[[CWG903]] 把它收紧为值为零的整数字面量，作为缺陷报告适用于 C++11 及以后。

### 到 `void*`（¶2）

¶2 指向 cv `T`（`T` 是对象类型）的指针可以转换为指向 cv `void` 的指针，指针值不变。函数指针不能隐式转换为 `void*`，成员指针也不能（[[conv.mem]] 的脚注）。

### 派生类到基类（¶3）

¶3 指向 cv `D`（`D` 是完整类类型）的指针 `v` 可以转换为指向 cv `B` 的指针，`B` 是 `D` 的基类：

- `B` 是 `D` 的不可访问或有歧义的基类时，需要这个转换的程序非良构；
- 空指针值转换为空指针值；
- `B` 是 `D` 的虚基类（或虚基类的基类），而 `v` 并不指向一个类型与 `D` 相似、在生命周期内或正在构造、析构的对象时，行为未定义；
- 否则结果指向派生类对象中的基类子对象。

```cpp error
struct A {}; struct B1 : A {}; struct B2 : A {};
struct D : B1, B2 {};
struct P : private A {};

void demo(D* d, P* p) {
    A* a1 = d;          // error: A 是 D 的有歧义的基类
    A* a2 = p;          // error: A 是 P 的不可访问的基类（在 P 之外）
}
```

虚基类那一条是因为实现。非虚基类的偏移在编译期已知，转换只是加一个常数；虚基类的偏移要从对象的虚表里读，指针不指向一个活着的 `D`，就没有虚表可读：

```cpp run title="vbase.cpp" ub
#include <new>
struct V { int v; };
struct D : virtual V { int d; };

int main() {
    D* p = static_cast<D*>(::operator new(sizeof(D)));   // 有存储，但没有 D 对象
    V* pv = p;          // UB：V 是虚基类，要读虚表
    (void)pv;
    ::operator delete(p);
}
```

本机 Clang 23 在 arm64 上 `-O0` 运行这个例子会段错误：转换代码从未初始化的存储里读出一个所谓的虚表指针，再解引用它。

## 成员指针转换 [conv.mem]

¶1 空指针常量可以转换为成员指针类型，结果是**空成员指针值**，与任何不是由空指针常量得到的成员指针都不同。同样，转换为指向 cv 限定类型的成员指针是一个转换，不是成员指针转换加限定转换。

¶2 `B` 的类型为 cv `T` 的成员指针，可以转换为 `D` 的类型为 cv `T` 的成员指针，其中 `D` 是从 `B` 派生的完整类：

- `B` 是 `D` 的不可访问、有歧义或虚的基类（或虚基类的基类）时，程序非良构；
- `D` 既不包含原来的成员，也不是包含原成员的类的基类时，行为未定义；
- 否则结果指代同一个成员，但当作 `D` 的成员。用 `D` 对象解引用它，等价于用该对象的 `B` 子对象解引用原来的成员指针。

```cpp ok
struct B { int x; void mf(); };
struct D : B { int y; };

int D::* pd = &B::x;          // 基类到派生类
void (D::* pmf)() = &B::mf;   // 成员函数指针同理

int read(D& d) { return d.*pd; }   // 读 d 的 B 子对象中的 x
```

方向和对象指针相反，脚注说这种反转是类型安全所必需的。`Derived*` → `Base*` 安全，因为每个 `Derived` 对象都包含一个 `Base`；`int Base::*` → `int Derived::*` 安全，因为 `Base` 的每个成员也是 `Derived` 的成员。反过来，`int Derived::*` 可能指向 `Derived` 独有的成员，用在 `Base` 对象上就越界了。

```cpp error
struct B { int x; };
struct D : B { int y; };
struct VD : virtual B {};

int B::* pb = &D::y;      // error: 派生类到基类方向不能隐式转换
int VD::* pv = &B::x;     // error: B 是虚基类
```

禁止虚基类的原因和指针类似：Itanium ABI 中数据成员指针就是一个编译期常量偏移，表达不了运行时才知道的虚基类偏移。

`D` 不包含原成员这种 UB 只有借助显式转换才会出现：

```cpp ub
struct B {};
struct D1 : B { int x; };
struct D2 : B {};

int main() {
    int B::* pb = static_cast<int B::*>(&D1::x);  // 显式的派生类到基类，static_cast 允许
    int D2::* p2 = pb;   // UB：D2 不含 D1::x，也不是 D1 的基类
    (void)p2;
}
```

脚注最后指出，成员指针既不是对象指针也不是函数指针，指针转换的规则不适用于它，特别是它不能转换为 `void*`。

## 函数指针转换 [conv.fctptr]

¶1 指向 `noexcept` 函数的指针可以转换为指向函数的指针，结果指向同一个函数；成员函数指针同理。方向只能是去掉 `noexcept`：承诺不抛异常的函数当然可以当作可能抛异常的函数来调用，反之不行。

<div class="compare" markdown="1">

```cpp ok
void h() noexcept;
void (*fp)() = h;
void (*fp2)() = &h;
struct C { void m() noexcept; };
void (C::*pm)() = &C::m;
```

```cpp error
void (*p)();
// error: 不能加上 noexcept
void (**pp)() noexcept = &p;

struct S {
  typedef void (*fp)();
  operator fp();
};
// error: 同上
void (*q)() noexcept = S();
```

</div>

右边改编自标准的例子。它在标准转换序列中单独占第 3 步，排在指针转换之后、限定转换之前，在重载决议中属于精确匹配。C++17 让 `noexcept` 成为函数类型的一部分（[[P0012R1]]），`void() noexcept` 和 `void()` 成了不同的类型，这个转换是为了兼容旧代码而同时加入的。

## 布尔转换 [conv.bool]

¶1 算术类型、无作用域枚举、指针、成员指针类型的 prvalue 可以转换为 `bool`。零值、空指针值、空成员指针值变成 `false`，其他值变成 `true`。

```cpp error
#include <cstddef>
enum class Color { red };
void f();
int* ptr();

bool a = &f;            // OK（Clang 警告：函数地址总为真）
bool b{ptr()};          // error: 指针到 bool 是窄化转换
bool c = nullptr;       // error: nullptr_t 没有布尔转换
bool d(nullptr);        // OK：直接初始化的特例，d == false
bool e = Color::red;    // error: 有作用域枚举没有布尔转换
bool g{0.5};            // error: 浮点到 bool 是窄化转换
```

几个边界情况：

- `std::nullptr_t` 不在列表中，`bool b = nullptr;` 非良构；[[dcl.init]] 有一条特殊规则允许直接初始化 `bool b(nullptr);`，结果是 `false`。
- 有作用域枚举不在列表中，`if (scoped_value)` 非良构。
- 浮点转 `bool` 时 `0.0` 和 `-0.0` 变成 `false`，NaN 变成 `true`。
- 在列表初始化中，指针或成员指针转 `bool` 是窄化（[[dcl.init.list#7]] 的第 7.5 项，由 [[P1957R2]] 引入，作为缺陷报告适用于 C++20）。浮点转 `bool` 也是窄化，因为 `bool` 是整数类型，属于浮点到整数（第 7.1 项），而且这一项没有常量例外，连 `bool b{0.0};` 都非良构。

!!! pitfall "字符串字面量选中了 `f(bool)`"
    对 `void f(bool); void f(const std::string&);`，`f("hello")` 调用的是 `f(bool)`。字符串字面量退化为指针再做布尔转换，这是标准转换序列；转换为 `std::string` 需要用户定义转换。标准转换序列总是优于用户定义转换序列。`std::string_view` 这类可以由字符串隐式构造的类型也有同样的问题。

## 实现视角

!!! impl
    - 左值到右值转换对应一条加载指令；临时量实质化对应在栈上留出一块存储；数组和函数到指针只是取地址。限定转换、函数指针转换、到 `void*` 的转换、单继承下非虚的派生类到基类转换通常不产生任何代码。
    - 多继承下的派生类到基类转换要加偏移，并且必须先检查空指针（空指针转换后仍是空指针，不能加偏移）。所以 `static_cast<Base2*>(d)` 有时会生成一条条件跳转。
    - Itanium ABI 中数据成员指针是一个 `ptrdiff_t` 偏移，空值用 −1 表示（偏移 0 可能是合法成员）；成员函数指针占两个字：函数指针或虚表偏移，加上 `this` 的调整量。基类到派生类的转换只需调整偏移或调整量。MSVC 的成员指针表示更复杂，取决于类的继承模型。

## 历史与演进

!!! history
    - C++98 已有基本框架。空指针常量是值为零的整型常量表达式；有符号整型转换越界时结果由实现定义。
    - C++11 加入 `std::nullptr_t`、`char16_t`、`char32_t` 的提升、`explicit` 转换函数和按语境转换为 `bool`；[[CWG903]] 把空指针常量收紧为整数字面量。
    - C++14 把按语境隐式转换放宽为恰好一个 `T` 的规则，类可以同时有其他非整数类型的转换函数。
    - C++17：[[P0135R1]] 引入临时量实质化转换，[[P0012R1]] 引入函数指针转换。
    - C++20：二进制补码让整型转换成为模运算（[[P1236R1]]）；加入 `char8_t`（[[P0482R6]]）；限定转换支持数组边界（[[P0388R4]]）；指针到 `bool` 在列表初始化中成为窄化（[[P1957R2]]）。
    - C++23 引入扩展浮点类型和浮点转换等级（[[P1467R9]]），浮点转换从任意方向改为等级不降低或在标准类型之间。
    - C++23 之后的新措辞：左值到右值转换明确了无效值表示为 UB、整数读取取同余值和 volatile 读出失效指针的处理；数组到指针转换加入对象类型与表达式类型不相似时为 UB；指针转换加入虚基类的 UB 条件。

## 思考题

!!! question "思考题 1"
    `int*` 能隐式转换为 `const void*` 吗？`int**` 能隐式转换为 `const void**` 或 `void**` 吗？

<details markdown="1">
<summary>答案</summary>

- `int*` → `const void*`：可以，先指针转换为 `void*`，再限定转换为 `const void*`，顺序符合标准转换序列。
- `int**` → `const void**`：不可以。`int**` 的被指类型是 `int*`，把它当作 `void**` 意味着把 `int*` 槽位当作 `void*` 槽位，两者不相似，没有标准转换能做到。
- `int**` → `void**`：同理不可以。但 `int**` → `void*` 可以，因为被指类型 `int*` 是对象类型。
</details>

!!! question "思考题 2"
    对 `void f(int); void f(double);`，`f('a')`、`f(1.0f)`、`f(1L)` 分别调用哪个？

<details markdown="1">
<summary>答案</summary>

- `f('a')`：`char` → `int` 是提升，`char` → `double` 是转换，选 `f(int)`。
- `f(1.0f)`：`float` → `double` 是提升，`float` → `int` 是转换，选 `f(double)`。
- `f(1L)`：`long` → `int` 是整型转换，`long` → `double` 是浮点-整型转换，等级相同，有歧义，非良构。
</details>

!!! question "思考题 3"
    `int* const*` → `const int* const*` 合法吗？`int* const*` → `const int**` 呢？

<details markdown="1">
<summary>答案</summary>

第一个合法。两者相似；最内层加了 `const`，按限定合成类型的第三条规则，第 1 层在目标中必须是 `const`，而它正是 `const`。限定合成类型等于目标类型。

第二个不合法。目标的第 1 层去掉了 `const`，合成类型的第 1 层取并集仍是 `const`，与目标不同。限定转换只能加 cv，不能减。
</details>
