---
title: 标准转换
summary: 语言内建的全部隐式转换：左值到右值、数组/函数到指针、临时量实质化、限定转换、整型与浮点提升、整型/浮点/指针/成员指针/函数指针/布尔转换，以及它们组成"标准转换序列"的顺序
status: draft
covers: "*"
papers: P0135R1, P0388R4, P0012R1, P1957R2, P1467R9
related: basic.lval, expr.arith.conv, over.best.ics, over.ics.rank, dcl.init, dcl.init.list, conv.rank, topics/value-categories
tags: 转换, 提升, 限定转换, 指针, UB
updated: 2026-10-17
---

**标准转换**（standard conversion）是具有内建含义的隐式转换，C++ 类型系统靠它们把各种类型衔接起来。`int` 能传给 `long` 形参，数组名能当指针用，`char*` 能赋给 `const char*`，`if (p)` 能判断指针非空，依据都在这一节。

本页覆盖 [conv] 的全部 15 个子条款。阅读时请记住两点：

1. 标准转换只规定能否转换；何时施行，由使用它们的地方决定，包括运算符对操作数的要求（[[expr.compound]]）、初始化（[[dcl.init]]）和重载决议中的隐式转换序列（[[over.best.ics]]）。
2. 重载决议给不同的标准转换以不同的等级（精确匹配 / 提升 / 转换，[[over.ics.scs]]），所以提升与转换的区分非常重要。两者在值上可能毫无差别，但在重载决议中排名不同。

| 子条款 | 转换 | 在重载决议中的等级 |
|---|---|---|
| [[conv.lval]] | 左值到右值 | 精确匹配（左值变换） |
| [[conv.array]] | 数组到指针 | 精确匹配（左值变换） |
| [[conv.func]] | 函数到指针 | 精确匹配（左值变换） |
| [[conv.rval]] | 临时量实质化 | （不属于标准转换序列的类别） |
| [[conv.qual]] | 限定转换 | 精确匹配（限定调整） |
| [[conv.prom]] | 整型提升 | 提升 |
| [[conv.fpprom]] | 浮点提升 | 提升 |
| [[conv.integral]] | 整型转换 | 转换 |
| [[conv.double]] | 浮点转换 | 转换 |
| [[conv.fpint]] | 浮点-整型转换 | 转换 |
| [[conv.ptr]] | 指针转换 | 转换 |
| [[conv.mem]] | 成员指针转换 | 转换 |
| [[conv.fctptr]] | 函数指针转换 | 精确匹配 |
| [[conv.bool]] | 布尔转换 | 转换 |

---

## 7.3.1 总则 [conv.general]

### 标准转换序列（¶1）

¶1 **标准转换序列**（[[g:standard-conversion-sequence]]）是按以下顺序排列的一串标准转换：

1. 零或一个：左值到右值 / 数组到指针 / 函数到指针；
2. 零或一个：整型提升 / 浮点提升 / 整型转换 / 浮点转换 / 浮点-整型转换 / 指针转换 / 成员指针转换 / 布尔转换；
3. 零或一个：函数指针转换；
4. 零或一个：限定转换。

序列可以为空。必要时，对表达式施加标准转换序列，以得到所需的目标类型与值类别。

每类至多一个、顺序固定，这个结构意味着**不能连做两次第 2 类转换**。`short` → `int`（提升）→ `double`（转换）不是一个标准转换序列；`short` 能直接转换为 `double`，是因为浮点-整型转换的源可以是任何整数类型，而不是因为先提升再转换。同样，`Derived*` → `Base*` → `void*` 不能构成一个标准转换序列，但 `Derived*` → `void*` 本身就是一个指针转换，所以没有问题。

```cpp ok
struct Base {}; struct Derived : Base {};
void take(const void*);

void demo(Derived* d, short s) {
    take(d);          // 指针转换（Derived* → void*）+ 限定转换（→ const void*）
    double x = s;     // 一步浮点-整型转换
    (void)x;
}
```

### 隐式转换的几种语境（¶2，注释）

¶2（注释）列举了表达式发生隐式转换的场合：作为运算符的操作数；作为 `if` 或循环的条件（目标类型为 `bool`）；作为 `switch` 的表达式（目标为整型）；作为初始化的源（包括函数实参与 `return`）。

### 可隐式转换、按语境转换为 bool、按语境隐式转换（¶3–¶5）

这三个定义经常被别处引用，它们都借助一个虚构的声明来定义：

| 术语 | 定义 | 用在哪里 |
|---|---|---|
| `E` 可隐式转换为 `T`（¶3） | `T t = E;` 良构 | 到处，如 `std::is_convertible` |
| `E` 按语境转换为 bool（¶4） | `bool t(E);` 良构 | `if`/`while`/`for` 条件、`!`、`&&`、`\|\|`、`?:` 第一操作数、`static_assert`、`noexcept(E)`、`explicit(E)` 等 |
| 类类型 `E` 按语境隐式转换为某类型（¶5） | 在类中查找非 explicit 的转换函数，其返回类型（cv `T` 或其引用）中的 `T` 要为语境所允许，且恰好只有一个这样的 `T` | `switch` 条件、数组 `new` 的长度、`delete` 的操作数 |

¶3 与 ¶4 的区别就是复制初始化与直接初始化的区别：直接初始化会考虑 `explicit` 转换函数。C++11 的 `explicit operator bool` 正是这样工作的，`if (e)` 可以，`bool b = e;` 不行：

```cpp error
struct Handle { explicit operator bool() const { return true; } };

void demo(Handle h) {
    if (h) {}                // OK：按语境转换为 bool，即 bool t(h);
    bool ok = h && true;     // OK：&& 的操作数也是按语境转换
    bool bad = h;            // error: 复制初始化不考虑 explicit 转换函数
    int n = h + 1;           // error: 不会经由 bool 再提升为 int
}
```

¶5 要求恰好一个 `T`，例如：

```cpp error
struct One { operator int() const; };
struct Two { operator int() const; operator long() const; };

void demo(One a, Two b) {
    switch (a) { case 1: break; }   // OK：唯一的整型 T = int
    switch (b) { case 1: break; }   // error: 有两个候选 T（int 与 long）
}
```

### 隐式转换的效果与值类别（¶6–¶8）

¶6 隐式转换的效果，等同于执行对应的声明与初始化，再把那个虚构的变量用作转换结果。如果 `T` 是左值引用类型或函数的右值引用，结果是左值；如果 `T` 是对象的右值引用，结果是 xvalue；否则是 prvalue。当且仅当该初始化把表达式 `E` 用作 glvalue 时，`E` 才被用作 glvalue。

这条规则统一了转换到引用类型时的值类别：隐式转换到 `const T&` 产生左值，到 `T&&` 产生 xvalue，与显式转换（[[expr.static.cast]]）的规则完全一致。

¶7（注释）对类类型还要考虑用户定义转换（[[class.conv]]）；一般的隐式转换序列由"标准转换序列 + 用户定义转换 + 标准转换序列"组成（[[over.best.ics]]）。

¶8（注释）某些语境会抑制某些转换，例如一元 `&` 的操作数不做左值到右值转换。

---

## 7.3.2 左值到右值转换 [conv.lval]

这是名字最容易误导人的转换（脚注说这个名字出于历史原因）。它把任何非函数、非数组类型的 glvalue（不只是左值，xvalue 也可以）变成 prvalue，本质上就是**读取对象的值**。

### 适用范围与类型（¶1）

¶1 非函数、非数组类型 `T` 的 glvalue 可以转换为 prvalue。

- 如果 `T` 是不完整类型，需要此转换的程序非良构。
- 如果 `T` 是非类类型，prvalue 的类型是 `T` 的 cv 无限定版本。`const int` 读出来是 `int`，原因就在这里。
- 否则（类类型），prvalue 的类型就是 `T`（保留 cv）。脚注：C++ 的类与数组 prvalue 可以带 cv，这一点与 C 不同。

### 何时不访问对象（¶2）

¶2 对表达式 `E` 施行左值到右值转换时，如果

- `E` 不是潜在求值的（如在 `sizeof` 中），或者
- `E` 的求值会求值其潜在结果集中的某个成员 `Ex`，而 `Ex` 命名的变量 `x` 没有被 `Ex` odr-use（[[basic.def.odr]]），

就**不访问**所引用对象中的值。第二种情形典型地出现在常量上：`constexpr` 变量在常量表达式中使用时不构成 odr-use，它的值在编译期就已知，根本不需要读内存。

改编自标准的例子：

```cpp run title="not-accessed.cpp" ub
struct S { int n; };

auto f() {
    S x{1};
    constexpr S y{2};
    return [&](bool b) { return (b ? y : x).n; };
}

int main() {
    auto g = f();
    int n = g(true);     // OK：y.n 不被访问——y 未被 odr-use，值在编译期已知
    int m = g(false);    // UB：访问 x.n，而 x 的生命周期已经结束
    return n + m;
}
```

`g(true)` 没有问题，原因如下：`(b ? y : x).n` 的潜在结果集包含 `y.n` 与 `x.n`；求值时选中的是 `y.n`，而 `y` 是 constexpr，`y.n` 满足不 odr-use 的条件，于是左值到右值转换直接产出常量 2，不访问那个早已销毁的 `y`。

### 转换的结果（¶3）

¶3 结果按以下规则确定：

¶3.1 `std::nullptr_t`：如果 `T` 是 cv `std::nullptr_t`，结果是一个空指针常量。注释：这一转换不访问对象，所以即使 `T` 是 volatile 也没有副作用，并且 glvalue 可以指代 union 的非活跃成员。`nullptr_t` 只有一个值，不需要读取。

¶3.2 类类型：转换复制初始化结果对象，即调用复制构造函数（如果 glvalue 是 xvalue，则调用移动构造函数）。所以读取类类型的对象不是访问，而是一次构造函数调用。

¶3.3 无效的值表示：如果 glvalue 所指对象的值表示中的位对该对象的类型无效，行为未定义。

```cpp run title="bad-bool.cpp" ub
#include <cstring>
#include <cstdio>

bool f() {
    bool b = true;
    char c = 42;
    std::memcpy(&b, &c, 1);
    return b;    // UB：42 不是 bool 的有效值表示（bool 通常只有 0 和 1 两种）
}

int main() { std::printf("%d\n", f()); }
```

用 `-fsanitize=undefined` 运行时，UBSan 报告 "load of value 42, which is not a valid value for type 'bool'"。实际后果可能很奇怪：编译器知道 `bool` 只有 0/1 两个值，可能直接用 `b` 索引一个两元素的表，也可能让 `b` 与 `!b` 同时为真。

¶3.4 一般情形：读取 glvalue 所指的对象（[[defns.access]]）。设对象中的值为 `V`，结果是：

- ¶3.4.1 如果 `T` 是整数类型，结果是与 `V` 同余的 `T` 类型的值。这照顾了通过对应的有符号/无符号类型访问对象的情形（[[basic.lval#11]] 允许的别名）：用 `unsigned` glvalue 读取一个值为 −1 的 `int` 对象，得到 `UINT_MAX`。
- ¶3.4.2 如果 `T` 是 volatile 限定的，且 `V` 在该求值语境中是无效的指针值，结果是 `reinterpret_cast<T>(reinterpret_cast<std::uintptr_t>(V))`。也就是说，通过 volatile 读出的失效指针被当作由整数转换而来的指针。volatile 存储可能被外部修改，编译器不能对其中指针的来源做任何假设。
- ¶3.4.3 否则，结果是 `V`。

!!! note "未初始化的值：indeterminate 与 erroneous {{c++26}}"
    读取未初始化对象时发生什么，不在本节规定，而在 [[basic.indet]]。从 C++26 起，自动存储期变量（未标 `[[indeterminate]]`）的未初始化字节具有**错误值**（erroneous value），读取它是**错误行为**（erroneous behavior）{{erroneous}}：结果是实现选定的某个值，实现可以给出诊断，但这不再是 UB。动态存储期对象和标了 `[[indeterminate]]` 的变量则仍具有不确定值，读取通常为 {{ub}}。在 C++23 及之前，读取任何不确定值（除少数 `unsigned char` 例外）都是 UB。注意 [[basic.indet]] 的注释：如果错误值恰好不是该类型的有效值（如 `bool`），仍按 ¶3.3 为 UB。

```cpp eb
int main() {
    int x;          // C++26：x 的字节具有错误值
    return x;       // 错误行为（erroneous behavior），而非 UB
}
```

---

## 7.3.3 数组到指针转换 [conv.array]

¶1 类型为"`N` 个 `T` 的数组"或"`T` 的未知边界数组"的表达式 `E` 可以转换为类型为"指向 `T` 的指针"的 prvalue。

- 如果 `E` 是 prvalue，先施行临时量实质化（[[conv.rval]]）。数组 prvalue 也需要一个对象，指针才有可指的东西。
- 如果 `E`（可能经过转换）的结果是一个类型与 `E` 的类型相似的对象，结果是指向数组首元素的指针；**否则行为未定义**。

最后这一句处理的是表达式的类型与实际对象的类型不符的情形：

```cpp run title="array-ub.cpp" ub
int main() {
    int a3[3] = {1, 2, 3};
    int (&r4)[4] = reinterpret_cast<int(&)[4]>(a3);   // 转换本身可以
    int* p = r4;    // UB：r4 指代的对象类型是 int[3]，与 int[4] 不相似
    return p[0] - 1;
}
```

有了这条规则，即使有人通过 `reinterpret_cast` 伪造了一个边界错误的数组引用，编译器也可以信赖数组表达式的类型（例如它的边界）。

```cpp ok
using Arr = int[3];
int k = Arr{1, 2, 3}[1];      // OK：数组 prvalue 被实质化，k == 2
int* dangling = Arr{1, 2, 3}; // 良构，但临时数组在完整表达式结束时销毁：悬垂指针
```

（Clang 对第二行会给出 `-Wdangling` 警告。）

---

## 7.3.4 函数到指针转换 [conv.func]

¶1 函数类型 `T` 的左值可以转换为"指向 `T` 的指针"类型的 prvalue，结果是指向该函数的指针。

脚注：这一转换从不适用于非静态成员函数，因为根本无法得到一个指代非静态成员函数的左值。`obj.mf` 是 prvalue，只能立即调用（[[expr.ref]]）；`&C::mf` 产生的是成员指针，而不是函数指针。

```cpp ok
void f(int);
void (*p1)(int) = f;    // 函数到指针转换
void (*p2)(int) = &f;   // 取地址：没有转换，直接得到指针
void (&r)(int) = f;     // 绑定函数引用：不转换
auto p3 = *****f;       // 每个 * 都对指针解引用得到函数左值，再退化为指针
```

---

## 7.3.5 临时量实质化转换 [conv.rval]

¶1 类型 `T` 的 prvalue 可以转换为类型 `T` 的 xvalue。这一转换以临时对象作为结果对象来求值 prvalue，从而初始化一个临时对象（[[class.temporary]]），并产生一个指代该临时对象的 xvalue。`T` 必须是完整类型。注释：如果 `T` 是类类型（或其数组），它必须有可访问且未删除的析构函数。

!!! std
    This conversion initializes a temporary object of type T from the prvalue by evaluating the prvalue with the temporary object as its result object, and produces an xvalue denoting the temporary object.

    该转换以临时对象作为结果对象来求值纯右值，从而初始化临时对象，并产出指代它的亡值。

在 C++17 的值类别模型中，这个转换连接了 prvalue 与对象。prvalue 本身不是对象；当需要一个对象（glvalue），而上下文又没有提供结果对象时，就通过这个转换实质化出一个。触发的场合见 [[basic.lval#7]] 与 [[class.temporary#2]]，包括绑定引用、成员访问、数组下标/退化、弃值表达式、`std::initializer_list` 的底层数组等。

```cpp ok
struct X { int n; };
int k = X().n;          // X() 是 prvalue；成员访问要求 glvalue → 实质化为 xvalue
const X& r = X{42};     // 绑定引用：实质化，临时量的寿命延长到 r 的寿命
```

!!! note "命名之争"
    这个条款的 stable name 仍然是 `conv.rval`，它在 C++17 之前描述的是旧模型中的另一种转换。条款名与内容不一致，是历史遗留问题。

---

## 7.3.6 限定转换 [conv.qual]

这是 [conv] 中形式化程度最高的一节，也是理解 [[expr.type#3]]（复合指针类型）、[[dcl.init.ref]]（引用相关）、[[basic.lval#11]]（相似类型）的基础。

### 限定分解（¶1）

¶1 类型 `T` 的一个**限定分解**（qualification-decomposition）是一列 cv<sub>i</sub> 与 P<sub>i</sub>，使 `T` 是

> cv<sub>0</sub> P<sub>0</sub> cv<sub>1</sub> P<sub>1</sub> ⋯ cv<sub>n−1</sub> P<sub>n−1</sub> cv<sub>n</sub> U （n ≥ 0）

其中每个 P<sub>i</sub> 是"指向"、"指向类 C<sub>i</sub> 的类型为……的成员"、"N<sub>i</sub> 个元素的数组"或"未知边界数组"。如果 P<sub>i</sub> 是数组，元素类型上的 cv<sub>i+1</sub> 也被视为数组的 cv<sub>i</sub>（数组本身没有独立的 cv，[[basic.type.qualifier]]）。

标准的例子是：`const int**` 有三个限定分解，`U` 分别取 `int`、"指向 const int 的指针"和"指向指向 const int 的指针的指针"。通常我们关心的是最长的那个分解（n 最大）。

| `const int**` 最长分解 | cv<sub>0</sub> | P<sub>0</sub> | cv<sub>1</sub> | P<sub>1</sub> | cv<sub>2</sub> | U |
|---|---|---|---|---|---|---|
| | （无） | 指向 | （无） | 指向 | `const` | `int` |

### 相似类型（¶2）

¶2 如果两个类型 `T1`、`T2` 有 n 相同的限定分解，对应的 P<sub>i</sub> 相同（或一个是"N<sub>i</sub> 个元素的数组"、另一个是"未知边界数组"），且 `U` 相同，就称它们**相似**（[[g:similar-types|similar]]）。

直观地说，把所有层的 cv 全部去掉（并忽略数组边界）之后，两个类型相同，它们就相似。

| T1 | T2 | 相似？ |
|---|---|---|
| `int**` | `const int* const*` | 是 |
| `int[3]` | `const int[]` | 是 |
| `int B::* const*` | `const int B::**` | 是 |
| `int*` | `unsigned*` | 否（U 不同） |
| `Derived*` | `Base*` | 否 |
| `int(*)[3]` | `int**` | 否（P<sub>1</sub> 一个是数组，一个是指针） |

### 限定合成类型与限定转换（¶3）

¶3 `T1` 与 `T2` 的**限定合成类型**（qualification-combined type）`T3` 是与 `T1` 相似、限定分解满足以下条件的类型：

- ¶3.1 对每个 i > 0，cv3<sub>i</sub> 是 cv1<sub>i</sub> 与 cv2<sub>i</sub> 的并；
- ¶3.2 如果 P1<sub>i</sub> 或 P2<sub>i</sub> 是"未知边界数组"，P3<sub>i</sub> 就是"未知边界数组"，否则是 P1<sub>i</sub>；
- ¶3.3 如果得到的 cv3<sub>i</sub> 与 cv1<sub>i</sub> 或 cv2<sub>i</sub> 不同，或者 P3<sub>i</sub> 与 P1<sub>i</sub> 或 P2<sub>i</sub> 不同，就对所有 0 < k < i，给 cv3<sub>k</sub> 加上 `const`。

**当且仅当 `T1` 与 `T2` 的限定合成类型就是 `T2` 时，`T1` 类型的 prvalue 可以转换为 `T2`。**

换句话说，`T1` → `T2` 合法，当且仅当：

1. 两者相似；
2. 每一层上 `T2` 的 cv 都不少于 `T1` 的（只加不减），数组边界只能从已知变为未知；
3. 如果某一层 i 发生了变化（加了 cv 或丢了边界），那么第 1 到 i−1 层在 `T2` 中都必须是 `const`。

最外层的 cv<sub>0</sub> 不参与，因为它是 prvalue 自身的顶层限定，本来就会被丢弃。

### 为什么 `T**` → `const T**` 不安全

标准注释给出了一个反例（这里略加注解）：

```cpp error
int main() {
    const char c = 'c';
    char* pc;
    const char** pcc = &pc;   // #1：假如允许……（实际上 error）
    *pcc = &c;                // 通过 pcc 把 const char* 写进了 pc 这个 char* 槽位
    *pc = 'C';                // #2：通过 pc 修改了 const 对象 c！
}
```

问题出在中间层。`const char**` 的中间层是 `const char*`，即一个可写的、指向 const char 的指针槽位。允许 `char**` → `const char**`，就等于允许把指向 const 的指针写进原本只能存放指向非 const 的指针的槽位。

修复办法正是 ¶3.3：如果内层加了 `const`，中间层也必须是 `const`。`char**` → `const char* const*` 是合法的，因为中间层不可写，就没有办法把 `&c` 放进去。

```cpp ok
void demo(int** pp, int (*pa)[3]) {
    const int* const* a = pp;        // OK：内层加 const，中间层也是 const
    int* const* b = pp;              // OK：只在中间层加 const
    const int (*c)[3] = pa;          // OK：数组元素加 const（数组的 cv 即元素的 cv）
    int (*d)[] = pa;                 // OK（C++20）：丢掉数组边界
    const int* const* const* e = (int***)nullptr;   // OK：多层
    (void)a; (void)b; (void)c; (void)d; (void)e;
}
```

```cpp error
void demo(int** pp, int (**ppa)[3]) {
    const int** a = pp;      // error: 内层加了 const，中间层却不是 const
    int (**b)[] = ppa;       // error: 第 2 层丢了边界，第 1 层必须是 const：应写 int (* const*)[]
}
```

!!! lawyer "为什么丢掉数组边界也需要外层 const"
    假设允许 `int(**)[3]` → `int(**)[]`。那么通过后者可以写入一个指向 `int[5]` 的指针（`int(*)[5]` 可以转换为 `int(*)[]`），原来的 `int(*)[3]` 槽位就指向了一个 5 元素的数组，边界信息遭到破坏。这和 `const` 的漏洞结构相同，所以用同一条规则堵上。

¶3 的注释 2：给定相似的 `T1` 与 `T2`，这一构造保证两者都能转换为它们的限定合成类型。[[expr.type#3]] ¶3.8 正因此用它来定义复合指针类型。

### 单层的情形与成员指针（¶4、¶5，注释）

¶4（注释）单层的常见情形是：如果 *cv2* `T` 比 *cv1* `T` 限定更多，"指向 *cv1* `T`"可以转换为"指向 *cv2* `T`"；成员指针同理。¶5（注释）函数类型（包括成员函数指针中的函数类型）从不带 cv 限定（[[dcl.fct]]）。成员函数的 `const` 是函数类型中的 *cv-qualifier-seq*，不是 cv 限定，所以 `void (C::*)()` 不能经限定转换变为 `void (C::*)() const`。

---

## 7.3.7 整型提升 [conv.prom]

**整型提升**（integral promotion）把比 `int` 窄的整数类型提升为 `int`（或 `unsigned int`）。它源自 C：机器的自然字长对应 `int`，所有比 `int` 窄的运算都先扩展到 `int` 再做。提升发生在算术运算的操作数上（[[expr.arith.conv]]）和可变参数函数的实参上（[[expr.call]]），在重载决议中排名高于一般的整型转换。

### 被转换的位域（¶1）

¶1 在本节中，**被转换的位域**（converted bit-field）是指对位域施行左值到右值转换得到的 prvalue。位域的提升规则（¶5）看的是位宽，而不是声明类型。

### 窄整数（¶2）

¶2 对于不是被转换位域的 prvalue，如果其类型是 `bool`、`char8_t`、`char16_t`、`char32_t`、`wchar_t` 以外的整数类型，且整数转换等级（[[conv.rank]]）低于 `int`，那么当 `int` 能表示源类型的全部值时，它可以转换为 `int`，否则可以转换为 `unsigned int`。

典型的情况是：在 `int` 为 32 位的平台上，`signed char`、`unsigned char`、`char`、`short`、`unsigned short` 都提升为 `int`。如果某平台上 `short` 与 `int` 同宽，`unsigned short` 会提升为 `unsigned int`。

### 无固定底层类型的无作用域枚举（¶3）

¶3 底层类型不固定的无作用域枚举，提升为 `int`、`unsigned int`、`long`、`unsigned long`、`long long`、`unsigned long long` 中第一个能表示该枚举全部值（[[dcl.enum]]）的类型；如果都不能，就提升为等级高于 `long long`、能表示全部值的最低等级扩展整数类型（如果有两个，选有符号的）。

注意这里看的是枚举的值域，而不是它的底层类型。

### 固定底层类型的无作用域枚举（¶4）

¶4 底层类型固定的无作用域枚举可以提升为其底层类型；如果底层类型本身可以经整型提升，它也可以提升为提升后的底层类型。两者都属于提升，但 [[over.ics.rank]] 规定前者更好：

```cpp ok
#include <type_traits>
enum E : short { e };
int  g(short);
long g(int);
static_assert(std::is_same_v<decltype(g(e)), int>);  // 选 g(short)：提升到底层类型更优
static_assert(std::is_same_v<decltype(+e), int>);    // 算术中则继续提升为 int
```

注释：枚举类型的被转换位域按普通枚举值处理。**有作用域枚举（`enum class`）没有任何提升。**

### 位域（¶5）

¶5 对整型的被转换位域，如果 `int` 能表示位域的全部值，就提升为 `int`；否则，如果 `unsigned int` 能表示，就提升为 `unsigned int`。如果都不能，¶5 不适用，按 ¶2（比较声明类型的等级）处理，例如 40 位的 `unsigned long long` 位域不提升。

```cpp ok
#include <type_traits>
struct BF {
    unsigned a : 3;               // int 能表示 0..7 → int
    unsigned u31 : 31;            // int 能表示 0..2^31-1 → int
    unsigned u32 : 32;            // int 不能，unsigned 能 → unsigned
    unsigned long long big : 40;  // 都不能 → 不提升，仍为 unsigned long long
};
BF bf;
static_assert(std::is_same_v<decltype(+bf.a), int>);
static_assert(std::is_same_v<decltype(+bf.u31), int>);
static_assert(std::is_same_v<decltype(+bf.u32), unsigned>);
static_assert(std::is_same_v<decltype(+bf.big), unsigned long long>);
```

!!! pitfall "无符号位域参与运算变成有符号"
    `unsigned x : 3;` 参与运算时提升为 `int`，于是 `bf.a - 4` 可以是负数，这与 `unsigned` 变量的行为截然不同。

### 字符类型（¶6）

¶6 `char8_t`、`char16_t`、`char32_t`、`wchar_t`（包括尚未按上文提升为 `int`/`unsigned int` 的被转换位域）提升为 `int`、`unsigned int`、`long`、`unsigned long`、`long long`、`unsigned long long` 和其底层类型中，第一个能表示其底层类型全部值的类型。

| 类型 | 底层类型（典型） | 提升为（`int` 为 32 位） |
|---|---|---|
| `char8_t` | `unsigned char` | `int` |
| `char16_t` | `uint_least16_t` | `int` |
| `char32_t` | `uint_least32_t` | `unsigned int` |
| `wchar_t` | Linux/macOS：`int`；Windows：`unsigned short` | `int` |

### `bool`（¶7）与命名（¶8）

¶7 `bool` 可以提升为 `int`：`false` → 0，`true` → 1。¶8 以上统称整型提升。

```cpp run title="promotion-overload.cpp" ok
#include <cstdio>
int f(int)      { return 1; }
int f(long)     { return 2; }
int f(unsigned) { return 3; }

int main() {
    short s = 1; unsigned short us = 1; char c = 'a'; bool b = true;
    // 全部选中 f(int)：提升（等级"提升"）优于转换（等级"转换"）
    std::printf("%d %d %d %d\n", f(s), f(us), f(c), f(b));   // 1 1 1 1
}
```

---

## 7.3.8 浮点提升 [conv.fpprom]

¶1 `float` 类型的 prvalue 可以转换为 `double`，值不变。¶2 这称为**浮点提升**。

**只有 `float` → `double` 是提升**。`float` → `long double`、`double` → `long double`，以及涉及扩展浮点类型的转换（如 `std::float16_t` → `float`）都是浮点转换，在重载决议中排名较低：

```cpp ok
int g(double);
int g(long double);
int h(long double);
int h(int);
int x = g(1.0f);   // 选 g(double)：提升
// int y = h(1.0f);   // 歧义：float→long double 与 float→int 都是"转换"
```

可变参数函数调用中也会发生浮点提升：`printf("%f", 1.0f)` 中的实参提升为 `double`，所以 `%f` 对 `float` 和 `double` 都适用（[[expr.call]]）。

---

## 7.3.9 整型转换 [conv.integral]

¶1 整数类型的 prvalue 可以转换为另一种整数类型；无作用域枚举的 prvalue 可以转换为整数类型。

¶2 目标为 `bool` 时，见 [[conv.bool]]。源为 `bool` 时，`false` → 0，`true` → 1。

¶3 否则，结果是**目标类型中与源整数模 2<sup>N</sup> 同余的唯一值**，其中 N 是目标类型的宽度。

!!! std
    the result is the unique value of the destination type that is congruent to the source integer modulo 2^N, where N is the width of the destination type.

    结果是目标类型中与源整数模 2^N 同余的唯一值。

这意味着**所有整型转换都是良定义的**，既没有 UB，也没有实现定义的行为：

```cpp run title="modular.cpp" ok
#include <cstdio>
int main(int argc, char**) {
    long long ll = 1LL << 40;
    int i = (int)ll;                         // 2^40 mod 2^32 = 0
    signed char sc = (signed char)(200 * argc);  // 200 - 256 = -56
    unsigned u = -1;                         // UINT_MAX
    std::printf("%d %d %u\n", i, sc, u);     // 0 -56 4294967295
}
```

¶4 可以作为整型提升的转换不算整型转换，也就是说 `short` → `int` 是提升，不是转换（这会影响重载决议）。

!!! history "C++20 之前"
    C++20 之前，转换到有符号类型而值无法表示时，结果是实现定义的。C++20 规定有符号整数采用二进制补码表示（[[P1236R1]]），这一转换随之定义为模运算。注意这与算术溢出不同：`INT_MAX + 1` 仍是 UB（[[expr.pre]]），而 `(int)(INT_MAX + 1LL)` 是良定义的，结果为 `INT_MIN`。

---

## 7.3.10 浮点转换 [conv.double]

¶1 浮点类型的 prvalue 可以转换为浮点转换等级大于或等于它的另一浮点类型；标准浮点类型（`float`、`double`、`long double`）之间可以任意互相转换。

这种不对称是 C++23 引入扩展浮点类型（[[P1467R9]]）带来的：

- `float` → `double` → `long double`：等级递增，总是可以隐式转换。
- `double` → `float`：两者都是标准类型，可以隐式转换（为了与 C 兼容），只是在列表初始化中属于窄化。
- `double` → `std::float16_t`：目标等级更低，又不是标准类型之间的转换，所以不能隐式转换，必须显式写 `static_cast`。
- `std::float32_t` ↔ `float`（假设值集相同）：等级相等，可以隐式转换。

等级的定义见 [[conv.rank#2]]。

¶2 转换的值：如果源值能在目标类型中精确表示，结果就是它；如果源值落在两个相邻的目标值之间，结果是两者之一，选哪个由实现定义（通常按当前舍入模式就近舍入）；**否则行为未定义**。对 IEEE 754 类型，通常认为最大有限值与 +∞ 是两个相邻的可表示值，于是 `1e300` → `float` 属于落在两值之间的情形，结果由实现定义（实践中得到 +∞），而不是 UB。对没有无穷大的浮点格式，越界才真正是 UB。

¶3 可以作为浮点提升的转换不算浮点转换。

---

## 7.3.11 浮点-整型转换 [conv.fpint]

### 浮点 → 整数（¶1）

¶1 浮点类型的 prvalue 可以转换为整数类型。转换时截断，即丢弃小数部分。如果截断后的值不能用目标类型表示，行为未定义。注释：目标为 `bool` 时，见 [[conv.bool]]。

注意它与整型转换的鲜明对比：整数 → 整数是模运算（总是良定义的），而**浮点 → 整数越界是 UB**。

```cpp run title="fpint.cpp" ub
#include <cstdio>
int main(int argc, char**) {
    double d = 3e10 * argc;
    int i = (int)d;                       // UB：3e10 不能用 int 表示
    unsigned ok = (unsigned)(-0.5 * argc);  // OK：截断为 0，0 可以表示
    unsigned bad = (unsigned)(-1.5 * argc); // UB：截断为 -1，unsigned 不能表示
    std::printf("%d %u %u\n", i, ok, bad);
}
```

UBSan（`-fsanitize=float-cast-overflow`，包含在 `undefined` 中）会报告 "3e+10 is outside the range of representable values of type 'int'"。

!!! impl "为什么是 UB 而不是饱和"
    不同硬件对越界的浮点 → 整数转换行为各异：x86 的 `cvttsd2si` 返回整数不定值 `0x80000000`，ARM 的 `fcvtzs` 则饱和到最小值或最大值。把它定为 UB，编译器就可以直接使用单条硬件指令。需要确定的结果时，应先做范围检查。

### 整数 → 浮点（¶2）

¶2 整数类型或无作用域枚举的 prvalue 可以转换为浮点类型。能精确表示时，结果是精确的；在可表示范围内但不能精确表示时，结果是相邻的较低或较高可表示值，选哪个由实现定义；超出可表示范围则行为未定义。源为 `bool` 时，`false` → 0，`true` → 1。

```cpp ok
float f = 16777217;     // 2^24 + 1：float 不能精确表示，实现定义地得到 16777216 或 16777218
double d = 1LL << 62;   // 精确
```

---

## 7.3.12 指针转换 [conv.ptr]

### 空指针常量（¶1）

¶1 **空指针常量**（[[g:null-pointer-constant]]）是值为零的整数字面量，或 `std::nullptr_t` 类型的 prvalue。空指针常量可以转换为指针类型，结果是该类型的空指针值（[[basic.compound]]），它与任何对象指针或函数指针的值都可以区分。这称为空指针转换。

有两个细节：

- 空指针常量转换为指向 cv 限定类型的指针，是单一的转换，而不是由指针转换和限定转换组成的序列。这一点在重载决议中有意义。
- 整数类型的空指针常量可以转换为 `std::nullptr_t` 类型的 prvalue。注释：结果不是空指针值（`nullptr_t` 不是指针类型）。

```cpp error
int* p1 = 0;            // OK：整数字面量 0
int* p2 = 0L;           // OK：整数字面量
int* p3 = nullptr;      // OK
const int zero = 0;
int* p4 = zero;         // error: zero 不是字面量（C++03 中曾经可以）
int* p5 = '\0';         // error: 字符字面量不是整数字面量
int* p6 = false;        // error: 布尔字面量不是整数字面量
```

!!! history "空指针常量的收紧"
    在 C++03 中，空指针常量是"值为零的整型常量表达式"，于是 `zero`、`'\0'`、`false`，甚至 `1 - 1` 都算。这在模板中引起了麻烦：一个值依赖的表达式是不是空指针常量，要等到实例化时才知道，而这会改变重载决议。[[CWG903]] 把它收紧为"值为零的整数字面量"（作为缺陷报告，适用于 C++11 及之后）。

### 到 `void*`（¶2）

¶2 "指向 cv `T`"（`T` 为对象类型）可以转换为"指向 cv `void`"，指针值不变（[[basic.compound]]）。

函数指针不能隐式转换为 `void*`（`T` 必须是对象类型），成员指针也不能（[[conv.mem]] 脚注）。

### 派生到基（¶3）

¶3 "指向 cv `D`"（`D` 为完整类类型）可以转换为"指向 cv `B`"，`B` 是 `D` 的基类：

- 如果 `B` 是 `D` 的不可访问或有歧义的基类，需要此转换的程序非良构。
- 空指针值转换为空指针值。
- 如果 `B` 是 `D` 的虚基类（或虚基类的基类），而 `v` 并不指向一个类型与 `D` 相似、且处于生命周期内或处于构造/析构期间的对象，行为未定义。
- 否则，结果是指向派生类对象中基类子对象的指针。

虚基类那一条出于实现上的原因。非虚基类的偏移量在编译期已知，转换只是加一个常数；**虚基类的偏移量要从对象的虚表中读取**，如果指针不指向一个存活的 `D`，就没有虚表可读。

```cpp ub
struct V { int v; };
struct D : virtual V { int d; };

int main() {
    D* p = static_cast<D*>(::operator new(sizeof(D)));   // 存储，但没有 D 对象
    V* pv = p;          // UB：V 是虚基类，p 不指向活着的 D——需要读虚表
    (void)pv;
    ::operator delete(p);
}
```

在 Clang/arm64 上实际运行这个例子，会直接段错误：转换代码从那块未初始化的存储中读出一个所谓的虚表指针，并对它解引用。

```cpp error
struct A {}; struct B1 : A {}; struct B2 : A {};
struct D : B1, B2 {};
struct P : private A {};

void demo(D* d, P* p) {
    A* a1 = d;          // error: A 是 D 的歧义基类
    A* a2 = p;          // error: A 是 P 的不可访问基类（在 P 之外）
}
```

---

## 7.3.13 成员指针转换 [conv.mem]

### 空成员指针（¶1）

¶1 空指针常量可以转换为成员指针类型，结果是空成员指针值，它与任何不是由空指针常量产生的成员指针都可以区分。同样，这是单一的转换，不是成员指针转换加限定转换。

### 基到派生：方向反转（¶2）

¶2 "`B` 的类型为 cv `T` 的成员指针"可以转换为"`D` 的类型为 cv `T` 的成员指针"，其中 `D` 是从 `B` 派生的完整类：

- 如果 `B` 是 `D` 的不可访问、有歧义或虚的基类（或虚基类的基类），程序非良构。
- 如果 `D` 不包含原成员，也不是包含原成员的类的基类，行为未定义。
- 否则，结果指代同一成员，但视为 `D` 的成员；用一个 `D` 对象解引用它，等价于用该 `D` 对象的 `B` 子对象解引用原成员指针。

为什么方向与对象指针相反（脚注称之为"为保证类型安全所必需的反转"）？

- 对象指针：`Derived*` → `Base*` 是安全的，因为每个 `Derived` 对象都包含一个 `Base`。
- 成员指针：`int Base::*` → `int Derived::*` 是安全的，因为 `Base` 的每个成员也是 `Derived` 的成员；反过来，`int Derived::*` 可能指向 `Derived` 独有的成员，用在 `Base` 对象上就会越界。

```cpp ok
struct B { int x; void mf(); };
struct D : B { int y; };

int D::* pd = &B::x;          // OK：基到派生
void (D::* pmf)() = &B::mf;   // OK：成员函数指针同理

int read(D& d) { return d.*pd; }    // 读取 d 的 B 子对象中的 x
```

```cpp error
struct B { int x; };
struct D : B { int y; };
struct VD : virtual B {};

int B::* pb = &D::y;      // error: 派生到基方向不能隐式转换
int VD::* pv = &B::x;     // error: B 是虚基类——成员指针无法编码"经由虚表的偏移"
```

禁止虚基类的原因与指针的情形相似：数据成员指针在 Itanium ABI 中就是一个编译期常量偏移量（空成员指针用 −1 表示），无法表达运行时才知道的虚基类偏移。

`D` 不包含原成员这种 UB，只能借助显式转换才会出现：

```cpp ub
struct B {};
struct D1 : B { int x; };
struct D2 : B {};

int main() {
    int B::* pb = static_cast<int B::*>(&D1::x);  // 显式的派生到基（static_cast 允许）
    int D2::* p2 = pb;   // UB：D2 不含 D1::x，也不是 D1 的基类
    (void)p2;
}
```

脚注最后一句说，成员指针不是对象指针，也不是函数指针，指针转换的规则不适用于它；特别是，成员指针**不能转换为 `void*`**。

---

## 7.3.14 函数指针转换 [conv.fctptr]

¶1 "指向 noexcept 函数的指针"可以转换为"指向函数的指针"，结果指向该函数。成员函数指针同理。

方向只能是丢掉 noexcept：一个承诺不抛异常的函数，当然可以当作可能抛异常的函数来调用；反之则不行。

下面是改编自标准的例子：

```cpp error
void (*p)();
void (**pp)() noexcept = &p;   // error: 不能转换为指向 noexcept 函数的指针

struct S { typedef void (*fp)(); operator fp(); };
void (*q)() noexcept = S();    // error: 转换函数返回的是非 noexcept 函数指针
```

```cpp ok
void h() noexcept;
void (*fp)() = h;              // OK：函数到指针 + 函数指针转换
void (*fp2)() = &h;            // OK：函数指针转换
struct C { void m() noexcept; };
void (C::*pm)() = &C::m;       // OK：成员函数指针同理
```

注意，它在标准转换序列中单独占一个位置（第 3 类），排在指针转换之后、限定转换之前。在重载决议中，它属于精确匹配等级。

!!! history
    C++17 之前，异常规范不是函数类型的一部分，所以不需要这一转换。[[P0012R1]] 让 `noexcept` 成为类型系统的一部分（`void() noexcept` 与 `void()` 是不同的类型），同时加入了这一转换以保持兼容。

---

## 7.3.15 布尔转换 [conv.bool]

¶1 算术类型、无作用域枚举、指针、成员指针类型的 prvalue 可以转换为 `bool`：零值、空指针值、空成员指针值转换为 `false`，其他值转换为 `true`。

有几个边界情况：

- `std::nullptr_t` 不在列表中：`bool b = nullptr;` 非良构；但 [[dcl.init]] 的特殊规则允许直接初始化 `bool b(nullptr);`（结果为 `false`）。
- 有作用域枚举不在列表中：`if (scoped_enum_value)` 非良构。
- 列表初始化中的窄化：从指针或成员指针类型到 `bool` 的转换是窄化转换（[[dcl.init.list#7]] ¶7.5），所以 `bool b{ptr};` 非良构。这一规则由 [[P1957R2]] 引入（作为缺陷报告，适用于 C++20）。
- 浮点 → `bool` 也是布尔转换（`0.0` 与 `-0.0` → `false`，NaN → `true`）；在列表初始化中不算窄化。

```cpp error
#include <cstddef>
enum class Color { red };
void f();

bool a = &f;            // OK（Clang 警告：函数地址总为真）
bool b{&f};             // error: 指针到 bool 是窄化转换（C++20 起）
bool c = nullptr;       // error: nullptr_t 不能隐式转换为 bool
bool d(nullptr);        // OK：直接初始化的特例，d == false
bool e = Color::red;    // error: 有作用域枚举没有布尔转换
```

!!! pitfall "指针到 bool 的意外重载"
    布尔转换属于转换等级，而 `const char*` → `std::string` 需要用户定义转换。所以对于 `void f(bool); void f(const std::string&);`，`f("hello")` 选中的是 **`f(bool)`**：字符串字面量退化为指针，再做布尔转换，而标准转换序列总是优于用户定义转换序列。`std::string_view` 等可以由字符串隐式构造的类型也有同样的问题。

---

## 实现视角

!!! impl
    - 左值到右值转换对应一条加载指令；临时量实质化对应在栈上分配一块存储；数组/函数到指针对应取地址（零开销）。限定转换、函数指针转换、`void*` 转换、非虚的派生到基转换（单继承时偏移为 0）在机器层面通常不产生任何代码。
    - 多继承下的派生到基转换需要加偏移，并且必须先检查空指针（空指针转换后仍是空指针，不能加偏移）。这就是 `static_cast<Base2*>(d)` 有时会生成一条条件跳转的原因。
    - 数据成员指针在 Itanium ABI 中是 `ptrdiff_t` 偏移量，空值为 −1（因为偏移 0 可以是合法的成员）；成员函数指针占两个字（函数指针或虚表偏移，加上 `this` 调整量）。基到派生转换只需调整偏移或 `this` 调整量。MSVC 的成员指针表示更复杂，取决于类的继承模型（单继承、多继承或虚继承）。
    - 浮点 → 整数：x86 的 `cvttsd2si` 越界时得到 `0x80000000…`，ARM 的 `fcvtzs` 则饱和。标准把越界定为 UB，正是为了容纳这种差异。

## 历史与演进

!!! history
    - C++98：基本框架已经具备；空指针常量为"值为零的整型常量表达式"；有符号整型转换越界时结果由实现定义。
    - C++11：加入 `std::nullptr_t` 与 `nullptr`，`char16_t`、`char32_t` 的提升，`explicit` 转换函数与按语境转换为 bool。[[CWG903]] 把空指针常量收紧为整数字面量。
    - C++14：按语境隐式转换（¶5）放宽为恰好一个 `T` 的规则，允许类同时有其他非整型的转换函数。
    - C++17：[[P0135R1]] 引入临时量实质化转换；[[P0012R1]] 引入函数指针转换。
    - C++20：二进制补码使整型转换成为模运算（[[P1236R1]]）；加入 `char8_t`（[[P0482R6]]）；限定转换支持数组边界（[[P0388R4]]）；指针到 `bool` 在列表初始化中成为窄化（[[P1957R2]]）。
    - C++23：引入扩展浮点类型与浮点转换等级（[[P1467R9]]），浮点转换从可以任意方向改为等级不降，或在标准类型之间。
    - 当前草案：[[conv.lval]] 明确了无效值表示为 UB、整数读取取同余值，以及 volatile 读出失效指针时的处理；[[conv.array]] 增加了对象类型与表达式类型不相似时为 UB 的规定；[[conv.ptr]] 增加了虚基类转换的 UB 条件。

## 思考题

!!! question "1. `int*` 能隐式转换为 `const void*` 吗？`int**` 能隐式转换为 `const void**` 吗？`void**` 呢？"

<details markdown="1">
<summary>答案</summary>

- `int*` → `const void*`：可以。先做指针转换（→ `void*`），再做限定转换（→ `const void*`），符合标准转换序列的顺序。
- `int**` → `const void**`：不可以。`int*` → `void*` 这种指针转换只适用于最外层被指类型是对象类型的情形，而 `int**` 的被指类型是 `int*`。把它当成 `void**`，意味着把 `int*` 槽位当作 `void*` 槽位，两者不相似，没有任何标准转换能做到。
- `int**` → `void**`：同理，不可以。但 `int**` → `void*` 可以（被指类型 `int*` 是对象类型）。
</details>

!!! question "2. 对 `void f(int); void f(double);`，`f('a')`、`f(1.0f)`、`f(1L)` 分别调用哪个？"

<details markdown="1">
<summary>答案</summary>

- `f('a')`：`char` → `int` 是提升，`char` → `double` 是转换，所以选 `f(int)`。
- `f(1.0f)`：`float` → `double` 是提升，`float` → `int` 是转换，所以选 `f(double)`。
- `f(1L)`：`long` → `int` 是整型转换，`long` → `double` 是浮点-整型转换，两者都属于转换等级，因此有歧义，非良构。
</details>

!!! question "3. `int* const*` → `const int* const*` 合法吗？`int* const*` → `const int**` 呢？"

<details markdown="1">
<summary>答案</summary>

第一个合法。两者相似；最内层（第 2 层）加了 `const`，按 ¶3.3，第 1 层在目标中必须是 `const`，而目标的第 1 层正是 `const`。限定合成类型等于目标类型，所以转换合法。

第二个非法。目标的第 1 层去掉了 `const`：合成类型的第 1 层取两者之并，即 `const`，与目标不同，所以合成类型不等于目标类型。限定转换只能加 cv，不能减。

一般来说，只要每层的 cv 只加不减（数组边界只能由已知变为未知），并且发生变化的层外侧的所有层（不含最外层）在目标中都是 `const`，转换就合法。
</details>

## 小结

!!! summary
    | 转换 | 关键规则 | 值的结果 |
    |---|---|---|
    | 左值到右值 | 非函数非数组 glvalue → prvalue；去非类 cv；不完整类型非良构 | 读取对象；无效位模式 UB；`nullptr_t` 不读取 |
    | 数组/函数到指针 | 数组 prvalue 先实质化；成员函数不适用 | 指向首元素/函数 |
    | 临时量实质化 | prvalue → xvalue；完整类型；需要析构函数 | 创建临时对象 |
    | 限定转换 | 相似 + 只加 cv/丢边界 + 变化层之外补 `const` | 值不变 |
    | 整型提升 | 窄整数/位域/字符/`bool`/无作用域枚举 → `int` 系列 | 值不变 |
    | 浮点提升 | 仅 `float` → `double` | 值不变 |
    | 整型转换 | 任意整数之间 | 模 2<sup>N</sup>（C++20 起） |
    | 浮点转换 | 等级不降或标准类型之间 | 精确 / 实现定义舍入 / 越界 UB |
    | 浮点-整型 | 双向 | 浮点 → 整数截断，越界 UB |
    | 指针转换 | 空指针常量（字面量 0 / `nullptr`）、→ `void*`、派生 → 基 | 歧义/不可访问非良构；虚基类需活对象 |
    | 成员指针转换 | 基 → 派生（反向）；禁止虚基类 | 同一成员 |
    | 函数指针转换 | 丢掉 `noexcept` | 同一函数 |
    | 布尔转换 | 算术/无作用域枚举/指针/成员指针 → `bool` | 零/空 → `false`；指针 → `bool` 在列表初始化中是窄化 |
