---
title: constexpr 与 consteval 说明符
summary: constexpr 和 consteval 能写在哪些声明上；constexpr 函数的定义如今只要求不是协程，能否在编译期求值留到每次调用时判断；constexpr 变量必须是字面类型、可常量初始化、具有常量析构；以及随之而来的隐式 const 与隐式 inline。
status: done
since: c++11
papers: P2448R2, P2242R3, P2647R1, P1064R0, P0784R7, P1073R3, P1331R2, P2686R5, P3533R2, P3068R6, P2747R2, P2738R1
related: expr.const, expr.const.core, expr.const.imm, expr.const.init, dcl.constinit, dcl.inline, basic.types, stmt.if
tags: 声明, 常量求值, constexpr, consteval
updated: 2026-10-19
---

!!! tldr
    - `constexpr` 函数可以在常量表达式中调用，也可以在运行期像普通函数一样调用；`consteval` 函数（立即函数）的每次调用都必须在编译期完成。
    - 当前草案对 constexpr 函数的定义只剩一条要求：不能是协程。某次调用能不能在编译期求值，由那一次求值实际执行了什么决定。
    - 加上 `constexpr` 不改变函数在运行期的行为，也不改变函数的类型，所以不能按是否 constexpr 重载。
    - `constexpr` 变量是 const 的，必须是字面类型，初始化必须是常量表达式，并且能在编译期销毁。
    - constexpr 函数和首次声明带 `constexpr` 的静态数据成员隐式 inline；命名空间作用域的 constexpr 变量不是 inline 的。

`constexpr` 声明的东西可以参与**常量求值**（constant evaluation），也就是在翻译期间算出结果。一个表达式在什么条件下是常量表达式，由 [[expr.const]] 规定；这一节只规定说明符本身：能修饰什么，对函数和变量各自意味着什么。

## 能写在哪里（¶1）

```cpp error
constexpr void square(int& x);  // OK: 函数可以只声明
constexpr int bufsz = 1024;     // OK: 变量定义
constexpr struct pixel {        // error: pixel 是类型，不能是 constexpr
    int x, y;
};
int next(constexpr int x);      // error: 形参不能是 constexpr
extern constexpr int memsz;     // error: 变量只能在定义上写 constexpr
struct S { constexpr int m = 1; };   // error: 非静态数据成员不能是 constexpr
constexpr int f();
int f();                        // error: 各次声明必须一致
```

¶1 `constexpr` 只能用于变量或变量模板的定义、结构化绑定声明，以及函数或函数模板的声明。`consteval` 只能用于函数或函数模板的声明。一个函数的某次声明带了 `constexpr` 或 `consteval`，它的所有声明都必须带同一个说明符；注 1 补充，显式特化可以和主模板不同。

变量只能在定义上写 `constexpr`，因为 constexpr 变量的意义在于使用处就能知道它的值，而不带初始化器的声明不提供值。函数则可以先声明、后定义，只是在定义出现之前，对它的调用不能在编译期求值（见后文的 `pixel` 例子）。

注 2 说明形参不能是 `constexpr`。同一个函数会以不同的实参被调用，形参的值不可能在编译期确定。需要编译期的参数时，用模板形参（C++20 起可以是类类型），或者把整个函数声明为 `consteval`。

## constexpr 函数与立即函数（¶2）

```cpp run ok
consteval int sq(int n) { return n * n; }
constexpr int sq2(int n) { return n * n; }
int main(int argc, char**) {
    constexpr int a = sq(4);     // OK: 常量表达式
    int b = sq2(argc);           // OK: constexpr 函数可以在运行期调用
    // int c = sq(argc);         // error: 立即函数的调用必须是常量表达式
    return a + b - 17;           // argc == 1 时返回 0
}
```

¶2 函数声明带 `constexpr` 或 `consteval`，就声明了一个 **constexpr 函数**（[[g:constexpr-function]]）。注 3 指出，用 `consteval` 声明的函数是**立即函数**（immediate function）：除非调用本身位于另一个立即函数这类编译期语境中，对它的每次调用都必须是常量表达式（[[expr.const.imm]]）。

所以按术语，consteval 函数也是 constexpr 函数。下面讲的隐式 inline、定义上的要求、行为一致性，对它同样适用。

¶2 最后一句规定，析构函数、分配函数（`operator new`）和释放函数（`operator delete`）不能是 `consteval`：

```cpp error
struct S {
    consteval ~S() { }                                  // error
    consteval void* operator new(decltype(sizeof 0));   // error
};
```

这几个函数由语言隐式调用：对象离开作用域时调用析构函数，`new` 表达式调用分配函数。如果它们是立即函数，运行期创建的对象就没法分配或销毁了。它们可以是 `constexpr` 的，C++20 起允许 constexpr 析构函数（[[P0784R7]]）。

## 定义上的唯一要求：不是协程（¶3）

```cpp run ok
constexpr int square(int x) { return x * x; }
constexpr int abs_(int x) { if (x < 0) x = -x; return x; }  // C++14 起：修改局部变量
constexpr int constant_non_42(int n) {
    if (n == 42) {
        static int value = n;    // C++23 起可以出现在 constexpr 函数里
        return value;            // 但这条路径不能在编译期求值
    }
    return n;
}
constexpr int pow_(int x, int n) {
    int r = 1;
    while (--n > 0) r *= x;      // C++14 起：循环
    return r;
}
static_assert(square(3) == 9 && abs_(-2) == 2);
static_assert(constant_non_42(7) == 7 && pow_(2, 4) == 8);
int main() { return constant_non_42(42) - 42; }   // 运行期走 n == 42 的路径：合法
```

`pow_(2, 4)` 等于 8 而不是 16：`--n > 0` 让循环只执行 3 次。这个函数照抄了标准例子中的 `g`。

¶3 不是协程的函数称为 **constexpr-suitable**。除了由模板实例化得到的 constexpr 函数，非模板的 constexpr 函数必须是 constexpr-suitable 的。协程的挂起和恢复需要协程帧和运行期调度，目前的常量求值模型表达不了。

除此之外，定义本身不再有任何限制。能不能声明 `static` 变量、能不能调用普通函数、能不能读未初始化的变量，都不在定义时检查，而是推迟到每一次常量求值：如果求值真的执行到了不允许的操作（[[expr.const.core]]），这一次求值就不是常量表达式。上面的 `constant_non_42` 就是这样，`n` 不等于 42 时可以在编译期求值，等于 42 时只能在运行期调用。

标准例子里还有一个 `uninit()`，注释写着 error：

```cpp run ok
constexpr int uninit() {
    struct { int a; } s;
    return s.a;          // 标准例子注释为 "error: uninitialized read of s.a"
}
int main() { }
```

这个 error 指的是任何一次对 `uninit()` 的常量求值都会失败，因为读取未初始化的值不是核心常量表达式。函数定义本身是良构的，本机 Clang 23 也接受它；写 `constexpr int u = uninit();` 时，出错的是那个变量的初始化。

!!! note "从 IFNDR 到良构：P2448"
    C++20 及以前有一条规则：如果一个非模板 constexpr 函数不存在任何实参能让对它的调用成为常量表达式，程序是**非良构、不要求诊断**（IFNDR，编译器可以报错也可以不报，程序没有任何保证）。问题在于，一个函数今天调用的库函数还不是 constexpr，它就永远不能常量求值；等那个库函数在下一版标准里变成 constexpr，同一份代码又变得合法了。[[P2448R2]] 在 C++23 删除了这条规则。注 5 保留了这层意思：完全可能写出一个任何调用都不是核心常量表达式的 constexpr 函数。

    ```cpp run ok
    int rt();
    constexpr int calls_rt() { return rt(); }   // C++23 起良构；C++20 中是 IFNDR
    int rt() { return 1; }
    int main() { return calls_rt() - 1; }
    ```

    本机 Clang 23 在 `-std=c++20` 下对这个函数报 `-Winvalid-constexpr` 错误（IFNDR 允许这样做），`-std=c++23` 起不再报。

!!! history "constexpr 函数能做的事"
    | 标准 | 新增 | 提案 |
    |---|---|---|
    | C++11 | 函数体基本只能是一条 `return`（另可有 `static_assert`、typedef 等）；成员函数隐含 const | |
    | C++14 | 局部变量、赋值、`if`、`switch`、循环；成员函数不再隐含 const | |
    | C++17 | constexpr lambda；`if constexpr` | |
    | C++20 | 虚函数；`try` 块（但不能真的抛出）；平凡默认初始化；不被求值的 `asm`；改变联合体的活跃成员；constexpr 析构函数与 `new`/`delete`；`consteval` | [[P1064R0]]、[[P1331R2]]、[[P0784R7]]、[[P1073R3]] |
    | C++23 | 非字面类型的变量、`goto`、标号、`static`/`thread_local` 变量（只要不被求值）；删除存在常量实参的要求；`static constexpr` 局部变量可在常量求值中使用 | [[P2242R3]]、[[P2448R2]]、[[P2647R1]] |
    | C++26 | 从 `void*` 转换；placement new；抛出并捕获异常；有虚基类的类也可以有 constexpr 构造函数和析构函数，定义上只剩不是协程一条要求 | [[P2738R1]]、[[P2747R2]]、[[P3068R6]]、[[P3533R2]] |

## 先定义，后在编译期调用

```cpp run ok
constexpr void square(int& x);           // 只声明
struct pixel {
    int x, y;
    constexpr pixel(int);                // 只声明
};
constexpr pixel::pixel(int a) : x(a), y(x) { square(x); }
// constexpr pixel small(2);             // error: square 还没有定义
constexpr void square(int& x) { x *= x; }
constexpr pixel large(4);                // OK: square 已定义
static_assert(large.x == 16 && large.y == 4);   // y 在 square 之前取了 x 的旧值
int main() { }
```

这是标准例 1 的后半部分。调用一个还没有定义的 constexpr 函数不是核心常量表达式（[[expr.const.core]]），所以 `small(2)` 不满足 constexpr 变量必须能常量初始化的要求（¶6）。常量求值看的是翻译到当前位置为止已有的定义，不会像模板实例化那样推迟到后面。

## 加 constexpr 不改变函数的行为（¶4–¶5）

¶4 在同一个语境中调用 constexpr 函数，结果在所有方面都与调用一个等价的非 constexpr 函数相同，只有两点例外：

- ¶4.1 constexpr 函数的调用可以出现在常量表达式中；
- ¶4.2 常量表达式中不做复制消除（[[class.copy.elision]]）。

**复制消除**（copy elision）指省略按值返回或传递时的复制、移动构造。除了 C++17 起强制的那几种情形，它是一项可选的优化。如果常量求值可以自己决定做不做，复制构造函数有可观察效果时，常量表达式的值就取决于实现的选择。规定一律不做，结果就是确定的。

注 4 指出一个微妙之处：加上 `constexpr` 可能改变某个表达式是不是常量表达式，从而间接改变函数里 `std::is_constant_evaluated()`（或 `if consteval`）的结果：

```cpp run ok
#include <type_traits>
constexpr int which() { return std::is_constant_evaluated() ? 1 : 2; }
int non_constexpr_twin() { return std::is_constant_evaluated() ? 1 : 2; }
const int a = which();      // const int 的初始化先尝试常量求值：1
int main() {
    int b = which();        // 普通变量的初始化不在常量求值中：2
    return (a == 1 && b == 2 && non_constexpr_twin() == 2) ? 0 : 1;
}
```

¶5 `constexpr` 和 `consteval` 不影响函数的类型。所以不能按是否 constexpr 重载，一个 constexpr 定义和一个普通定义不能共存：

```cpp error
constexpr int bar(int x, int y) { return x + y + x * y; }
int bar(int x, int y) { return x * 2 + 3 * y; }   // error: bar 的重定义
```

想在编译期和运行期用不同的实现，就在同一个函数里用 `if consteval`（C++23，[[stmt.if]]）或 `std::is_constant_evaluated()` 分支。普通的函数指针 `int(*)(int, int)` 也可以指向 constexpr 函数。

## constexpr 变量（¶6）

```cpp error
struct pixel { int x, y; };
constexpr pixel ur = { 1294, 1024 };     // OK
constexpr pixel origin;                  // error: 没有初始化
struct NonLit { NonLit(); };
constexpr NonLit nl{};                   // error: 不是字面类型
constexpr int* leak = new int(1);        // error: 分配的内存在求值结束时没有释放
```

¶6 声明对象时使用 `constexpr`：

1. 对象成为 const 的；
2. 对象必须是**字面类型**（literal type，大致是能在常量求值中创建和销毁的类型，[[basic.types.general]]），并且必须初始化；
3. 变量必须**可常量初始化**（constant-initializable）：初始化的完整表达式是常量表达式，并且得到的值里的指针和引用都指向编译期可以引用的对象（[[expr.const.init#4]]）；
4. 作为对象的 constexpr 变量，以及 constexpr 引用绑定的临时对象，必须具有**常量析构**（constant destruction）：销毁它也能在编译期完成（[[expr.const.defns#3]]）。

`const` 只表示不能通过这个名字修改对象，初始化可以发生在运行期；`constexpr` 要求初始化本身是常量表达式，值在翻译期就已确定。C++98 留下一个特例：整型或枚举类型的 const 变量，如果恰好用常量表达式初始化，也能在常量表达式中使用（[[expr.const.init#6]]、[[expr.const.init#7]]）。`double` 和类类型的变量只有声明为 `constexpr` 才行。

第 4 条保证编译期创建的对象在编译期也能销毁。常量求值中用 `new` 分配的内存必须在同一次求值里释放，这叫**瞬态分配**（transient allocation）。所以 `constexpr std::vector<int> v{1, 2, 3};` 非良构：初始化结束时 `v` 仍然持有堆内存。

### constexpr 引用绑定局部变量 {{c++26}}

```cpp
namespace N {
    void f() {
        int x;
        constexpr int& ar = x;              // C++26: OK
        static constexpr int& sr = x;       // error: x 在下面标出的位置不可引用
    }
    // 这里的直接作用域是 N
}
```

C++23 及以前，constexpr 引用只能绑定到静态存储期的对象，因为对象的地址必须是常量。C++26 引入了**可 constexpr 引用**（constexpr-referenceable）：从某一点 P 看，一个自动变量如果和 P 位于同一个函数的作用域内（中间只隔着块作用域），它就是可 constexpr 引用的（[[expr.const.init#2]]）。一个对象或引用里的所有指针和引用都指向这样的对象时，称它在 P 点**可 constexpr 表示**（constexpr-representable，[[expr.const.init#3]]）。

- `ar` 是函数内的自动变量。它的声明之后，`x` 和它同在 `f` 里，所以 OK。
- `sr` 是 `static` 的，[[expr.const.init#4]] 的第 4.3 项还要求它在声明之后第一个直接作用域为命名空间作用域的位置上可表示。那个位置在 `f` 外面，`x` 在那里不可引用，所以非良构。

这一改动（[[P2686R5]]）的直接动机是 C++26 的 constexpr 结构化绑定：`constexpr auto& [a, b] = local;` 需要绑定局部对象。本机 Clang 23 还没有实现，对 `ar` 一行也报错。

!!! lawyer "constexpr 变量与 odr-use"
    constexpr 变量是 const 的。读取它的值如果能在常量表达式中完成，这次读取就不算 **odr-use**（要求变量必须有定义的那种使用，[[basic.def.odr]]）。所以函数里写了 `constexpr int n = 3;` 之后，lambda 不捕获 `n` 也能直接用它的值；但取 `&n` 或绑定引用就是 odr-use，需要捕获。

## 隐式 inline（¶1）

¶1 还规定：函数或静态数据成员的首次声明带 `constexpr` 或 `consteval` 时，它隐式是 inline 的（[[dcl.inline]]）。inline 的意思是允许在多个翻译单元里各有一份相同的定义。这带来两个后果：

- constexpr 函数可以而且通常应该定义在头文件里，每个使用它的翻译单元都有一份定义，不违反 ODR（[[basic.def.odr]]）。
- C++17 起，类内的 `static constexpr` 数据成员声明本身就是定义，不再需要类外的 `constexpr int S::m;`。那条类外声明现在是多余的重声明，已经弃用（[[depr.static.constexpr]]）。

```cpp run ok
struct S { static constexpr int m = 1; };
const int* p = &S::m;     // C++17 起 OK: S::m 是 inline 变量，类内声明就是定义
int main() { return *p - 1; }
```

!!! pitfall "命名空间作用域的 constexpr 变量不是 inline"
    隐式 inline 只适用于静态数据成员。命名空间作用域的 `constexpr int N = 10;` 不是 inline 变量；它是 const 的，因此有内部链接（[[basic.link#3]]），每个包含这个头文件的翻译单元都有自己的对象，`&N` 各不相同。这通常无害。但如果需要唯一的地址，或者要在 inline 函数里 odr-use 它而不违反 ODR，就要写成 `inline constexpr int N = 10;`。标准库的 `std::is_same_v` 等都是这样写的。

!!! impl "Clang 23 尚未实现的部分"
    - 有虚基类的类仍不能有 constexpr 构造函数或析构函数，诊断是 "constexpr constructor not allowed in struct with virtual base class"。这是 C++23 的旧规则，C++26 已经删除（[[P3533R2]]）。
    - 常量求值中还不能抛出异常：`try { throw 1; } catch (int) { … }` 在 `static_assert` 中求值失败。
    - constexpr 引用还不能绑定局部变量（见上）。

!!! pitfall "常见误解"
    - constexpr 函数一定在编译期执行：只有在需要常量表达式的地方才保证；别处它就是普通的调用，编译器做常量折叠只是优化。要保证编译期求值，用 `consteval`，或者把结果赋给 constexpr 变量。
    - constexpr 成员函数隐含 const：只在 C++11 如此，C++14 起不再隐含。
    - 头文件里的 constexpr 变量违反 ODR：不会。命名空间作用域的有内部链接，每个翻译单元一份；静态数据成员是 inline 的。
    - consteval 函数不是 constexpr 函数：按第 2 段的定义，它是。

!!! summary "小结"
    | | constexpr 函数 | consteval 函数 | constexpr 变量 |
    |---|---|---|---|
    | 运行期能否使用 | 能 | 不能，调用必须是常量表达式 | 值在翻译期已知，对象运行期也存在 |
    | 隐式 inline | 是 | 是 | 只有静态数据成员是 |
    | 隐式 const | 否（C++14 起） | 否 | 是 |
    | 结构要求 | 不是协程 | 不是协程；不能是析构、分配、释放函数 | 字面类型、有初始化、可常量初始化、常量析构 |
    | 各次声明 | 必须一致 | 必须一致 | 只能写在定义上 |

!!! question "思考题 1"
    下面的程序在 C++20 和 C++23 中分别是什么状态？

    ```cpp
    #include <cstdio>
    int now();
    constexpr int stamp() { return now(); }
    int now() { return 42; }
    int main() { std::printf("%d\n", stamp()); }
    ```

<details markdown="1">
<summary>答案</summary>

`now` 不是 constexpr 函数，所以对 `stamp` 的任何调用都不可能是核心常量表达式。C++20 中这是一个不存在常量实参的非模板 constexpr 函数，属于 IFNDR，实现可以拒绝；本机 Clang 23 在 `-std=c++20` 下报 `-Winvalid-constexpr` 错误。C++23 起（[[P2448R2]]）程序良构，运行期正常打印 42。
</details>

!!! question "思考题 2"
    为什么 `constexpr std::string_view sv = "hello";` 总是良构，`constexpr std::string s = "...";` 却要看字符串的长度和标准库实现？

<details markdown="1">
<summary>答案</summary>

¶6 要求 constexpr 变量的初始化是常量表达式并且具有常量析构，而常量求值中分配的内存必须在同一次求值里释放。字符串超出短字符串优化（SSO）的容量时，`std::string` 会分配堆内存，初始化结束时仍持有它，所以不是常量表达式。短字符串放在对象内部，不分配内存，能否通过取决于实现：本机 libc++ 接受 `constexpr std::string s = "hello";`，拒绝一个长字符串。`string_view` 只保存指向字符串字面量（静态存储期对象）的指针和长度，不分配内存，是字面类型，析构平凡，所以总是良构。
</details>
