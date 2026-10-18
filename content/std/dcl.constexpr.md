---
title: constexpr 与 consteval 说明符
summary: constexpr/consteval 能用在哪里；当前草案中 constexpr 函数只剩"不能是协程"一条结构要求；constexpr 函数与普通函数的行为一致性；constexpr 变量必须是字面类型、可常量初始化、具有常量析构；隐含的 const 与 inline
status: done
since: c++11
papers: P2448R2, P2242R3, P2647R1, P1064R0, P0784R7, P1073R3, P1331R2, P2686
related: expr.const, expr.const.imm, expr.const.init, dcl.constinit, dcl.inline, basic.types, stmt.if
tags: 声明, 常量求值, constexpr, consteval
updated: 2026-10-17
---

`constexpr` 是 C++11 以来变化最大的特性之一。C++11 的 constexpr 函数只能有一条 return 语句；到 C++20，它可以分配内存、调用虚函数、使用 try 块；C++23 又取消了函数必须有可能在编译期求值的要求。今天的 constexpr 函数几乎就是允许在常量表达式中调用的普通函数。本节（[dcl.constexpr]）只规定说明符本身，即它能修饰什么、对函数和变量各意味着什么。某次求值是不是常量表达式，由 [[expr.const]] 的规则决定，读懂本节需要先了解那些规则。

本节同时规定 C++20 的 `consteval`。它声明**立即函数**（immediate function），对立即函数的每次调用都必须在编译期求值（[[expr.const.imm]]）。

## 适用对象（¶1）

¶1 的规则逐条列出如下：

1. `constexpr` 只能用于变量或变量模板的定义、结构化绑定声明、函数或函数模板的声明。
2. `consteval` 只能用于函数或函数模板的声明。
3. 如果函数或静态数据成员的首次声明带有 `constexpr` 或 `consteval`，它隐式是 inline 的（[[dcl.inline]]）。
4. 如果一个函数（模板）的某个声明带有 `constexpr` 或 `consteval`，那么它的所有声明都必须带同一个说明符。Note 1 指出，显式特化可以与主模板不同。
5. Note 2：函数参数不能声明为 `constexpr`。

```cpp error
constexpr void square(int& x);  // OK: 声明（函数可以只声明）
constexpr int bufsz = 1024;     // OK: 定义
constexpr struct pixel {        // error: pixel 是类型，constexpr 不能修饰类
    int x, y;
};
int next(constexpr int x);      // error: 参数不能是 constexpr
extern constexpr int memsz;     // error: 变量只能在定义上用 constexpr
struct S { constexpr int m = 1; };   // error: 非静态数据成员不能是 constexpr
constexpr int f();
int f();                        // error: 所有声明必须一致
```

为什么变量只能在定义上写 `constexpr`？`constexpr` 变量的意义在于编译器在使用点就知道它的值，而没有初始化器的声明不提供值，加上 `constexpr` 没有意义。函数则不同，`constexpr` 函数可以先声明、后定义，只是在定义可达之前，对它的调用不能构成常量表达式（见下面标准例子中的 `small(2)`）。

为什么不允许 `constexpr` 参数？同一个函数（同一段机器码）会以不同的实参被调用，参数的值不可能在编译期已知。需要编译期参数时，可以用模板参数（包括 C++20 的类类型 NTTP），或者把函数声明为 `consteval`。

### 声明顺序的影响：标准的 pixel 例子

```cpp run ok
constexpr void square(int& x);           // 只声明
struct pixel {
    int x, y;
    constexpr pixel(int);                // 只声明
};
constexpr pixel::pixel(int a) : x(a), y(x) { square(x); }   // 定义
// constexpr pixel small(2);             // error: 此时 square 尚未定义，small(2) 不是常量表达式
constexpr void square(int& x) { x *= x; }
constexpr pixel large(4);                // OK: square 已定义
static_assert(large.x == 16 && large.y == 4);   // 注意 y 在 square 之前被初始化为 x 的旧值
int main() { }
```

调用一个尚未定义的 constexpr 函数不是核心常量表达式（[[expr.const.core]]），所以 `small(2)` 不满足 `constexpr` 变量必须可常量初始化的要求（¶6）。由此可见，常量求值依据的是翻译到当前位置为止的状态，这与模板实例化点那种推迟的语义不同。

### 隐式 inline

按 ¶1 第三条，函数与静态数据成员在首次声明带 `constexpr`/`consteval` 时隐式 inline。这带来两个后果：

- `constexpr` 函数可以（而且通常必须）定义在头文件中。每个使用它的 TU 都有一份定义，这不违反 ODR（[[basic.def.odr]]）。
- C++17 起，`static constexpr` 数据成员在类内的声明就是定义，不再需要类外的 `constexpr int S::m;`。那条类外声明现在是多余的重声明，已经弃用（[[depr.static.constexpr]]）。

```cpp run ok
struct S { static constexpr int m = 1; };
const int* p = &S::m;     // C++17 起 OK: S::m 是 inline 变量，类内声明即定义
int main() { return *p - 1; }
```

!!! pitfall "命名空间作用域的 constexpr 变量不是 inline"
    隐式 inline 只适用于静态数据成员。命名空间作用域的 `constexpr int N = 10;` 不是 inline 变量。它是 const 的，因此具有内部链接（[[basic.link#3]]），每个包含该头文件的 TU 都有一个独立的对象，`&N` 在不同 TU 中各不相同。这通常无害，但如果需要唯一的地址，或者要在 inline 函数中 odr-use 它而不违反 ODR，就应写成 `inline constexpr int N = 10;`。标准库中 `std::is_same_v` 等变量模板都写成了 `inline constexpr`。

## constexpr 函数与立即函数（¶2）

¶2 规定，在函数声明中使用 `constexpr` 或 `consteval`，就把该函数声明为 **constexpr 函数**（[[g:constexpr-function]]）。Note 3 指出，用 `consteval` 声明的函数是立即函数（[[expr.const.imm]]）。

所以从术语上说，consteval 函数也是 constexpr 函数，适用于 constexpr 函数的规则（隐式 inline、¶3 的结构要求、¶4 的行为一致性）同样适用于 consteval 函数。两者的区别在于，立即函数的每次调用都必须是常量表达式，除非调用本身位于立即函数上下文中。

¶2 最后一句规定，析构函数、分配函数、释放函数不能是 `consteval`。

```cpp error
struct S {
    consteval ~S() { }                          // error: 析构函数不能是 consteval
    consteval void* operator new(decltype(sizeof 0));   // error: 分配函数不能是 consteval
};
```

为什么？析构函数和 `operator new/delete` 由语言隐式调用：对象离开作用域时自动调用析构函数，`new` 表达式隐式调用分配函数。如果它们是立即函数，运行期创建的该类型对象就都无法分配或销毁，一个只能在编译期销毁的类型基本没法使用。（它们可以是 `constexpr` 的，C++20 起 constexpr 析构函数是合法的，见 [[P0784R7]]。）

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

## constexpr-suitable（¶3）

当前草案中的 ¶3 只剩下一条：

!!! std
    A function is *constexpr-suitable* if it is not a coroutine. Except for instantiated constexpr functions, non-templated constexpr functions shall be constexpr-suitable.

    函数若不是协程，就是 constexpr-suitable 的。除实例化而来的 constexpr 函数外，非模板化的 constexpr 函数必须是 constexpr-suitable 的。

也就是说，constexpr 函数的定义本身只剩一条结构性要求：不能是协程。协程的挂起和恢复需要堆分配的协程帧和运行期调度，目前的常量求值模型无法表达。其余的限制，比如能否声明静态变量、能否调用非 constexpr 函数、能否有未初始化的变量，都不再是对定义的要求，而是推迟到某次常量求值时由 [[expr.const.core]] 检查：如果求值真的执行到了不允许的操作，这次求值就不是常量表达式。

再看"除实例化而来的 constexpr 函数外"这半句。由模板实例化得到的 constexpr 函数即使不满足要求（例如由于模板参数的缘故，函数体变成了协程，实际上很难发生），也不会使程序非良构，只是不能用于常量求值。

```cpp run ok
constexpr int square(int x) { return x * x; }
constexpr int abs_(int x) { if (x < 0) x = -x; return x; }   // C++14 起：可修改局部变量
constexpr int constant_non_42(int n) {
    if (n == 42) {
        static int value = n;    // C++23 起允许出现在 constexpr 函数中
        return value;            // 但这条路径永远不能常量求值
    }
    return n;
}
constexpr int pow_(int x, int n) {
    int r = 1;
    while (--n > 0) r *= x;      // C++14 起：循环
    return r;
}
static_assert(square(3) == 9 && abs_(-2) == 2 && constant_non_42(7) == 7 && pow_(2, 4) == 8);
int main() { return constant_non_42(42) - 42; }   // 运行期调用 n == 42 的路径：完全合法
```

（`pow_(2, 4)` 等于 8，因为循环 `--n > 0` 只执行 3 次，这与标准例子中 `g` 的逻辑完全相同。）

标准例子中还有一个 `uninit()`：

```cpp
constexpr int uninit() {
    struct { int a; } s;
    return s.a;          // 标准注释为 "error: uninitialized read of s.a"
}
```

这里的 "error" 应该理解为：对 `uninit()` 的任何常量求值都会失败，因为读取未初始化的值不是核心常量表达式；函数定义本身并不是非良构的。按 C++23 起的规则，这个定义是良构的，Clang 也接受它。如果在常量表达式中调用它，出错的是那个常量表达式。

```cpp run ok
constexpr int never_constant(int n) { static int k = 0; return n + k++; }   // 定义良构
int rt();
constexpr int calls_rt() { return rt(); }   // 也良构：C++23 前是 IFNDR
int rt() { return 1; }
int main() { return never_constant(0) + calls_rt() - 1; }
```

!!! history "constexpr 函数要求的演变"
    | 标准 | 函数体允许什么 | 关键提案 |
    |---|---|---|
    | C++11 | 基本上只有一条 `return`（外加 `static_assert`、typedef、using 等）；成员函数隐含 const | — |
    | C++14 | 局部变量、赋值、`if`/`switch`/循环；不再隐含 const | （放宽 constexpr 函数限制的提案） |
    | C++17 | lambda 可以是 constexpr；`if constexpr` | — |
    | C++20 | 虚函数（[[P1064R0]]）、`try` 块（但不能真的抛出）、平凡默认初始化（[[P1331R2]]）、`asm` 声明（只要不被求值）、改变联合体活跃成员、constexpr 析构函数与 `new`/`delete`（[[P0784R7]]）、`consteval`（[[P1073R3]]） | |
    | C++23 | 非字面类型的变量、`goto`、标号、`static`/`thread_local` 变量（只要不被求值，[[P2242R3]]）；不再要求存在至少一组实参使调用成为常量表达式（[[P2448R2]]）；`static constexpr` 局部变量可在常量求值中使用（[[P2647R1]]） | |
    | C++26 | 结构要求只剩不是协程；常量求值中可以使用 placement new、可以从 `void*` 转换、可以抛出并捕获异常；具有虚基类的类也可以有 constexpr 构造/析构函数 | |

!!! note "P2448：从 IFNDR 到良构"
    C++20 及之前有一条规则：对非模板的 constexpr 函数，如果不存在任何实参值能使对它的调用成为核心常量表达式，程序就非良构，不要求诊断（IFNDR）。这条规则的问题在于，一个函数在 C++20 下可能永远不能常量求值（例如它调用了一个尚未 constexpr 化的库函数），到了 C++23 那个库函数变成 constexpr 后，它又可以常量求值了。同一份代码是否良构，会随标准库版本而变化。[[P2448R2]] 删除了这条规则，constexpr 函数可以永远不被常量求值，程序依然良构。Note 5 至今保留了这层意思："可以写出一个 constexpr 函数，它的任何调用都不满足核心常量表达式的要求。"

!!! impl "实现尚未跟上的部分"
    截至写作时，本机 Clang（23）有以下几处尚未跟上：
    - 仍然拒绝具有虚基类的类的 constexpr 构造函数（诊断为 "constexpr constructor not allowed in struct with virtual base class"），这是 C++23 的旧规则；
    - 尚不支持在常量求值中抛出异常（`try { throw 1; } catch (int) { … }` 在 `static_assert` 中求值失败）；
    - 在 `-std=c++20` 下，仍按旧规则对永远不能常量求值的函数报 `-Winvalid-constexpr` 错误（这在 C++20 中是 IFNDR，报错是允许的）。

## 行为一致性（¶4）

¶4 规定，在给定上下文中调用 constexpr 函数，结果在所有方面都与调用一个等价的非 constexpr 函数相同，只有两点例外：

- ¶4.1 constexpr 函数的调用可以出现在常量表达式中；
- ¶4.2 常量表达式中不进行复制消除（[[class.copy.elision]]）。

这是对程序员的承诺：给函数加上 `constexpr` 不会改变它在运行期的行为。为什么常量求值中不做复制消除？除了 C++17 的强制消除，复制消除是一种可选的优化。如果常量求值可以自行选择做或不做，常量表达式的值就可能取决于实现的选择（例如复制构造函数有可观察的副作用时）。规定一律不做，结果就是确定的。

Note 4 指出了一个细微之处：加上 `constexpr` 可能改变某个表达式是否为常量表达式，从而间接改变函数内部 `std::is_constant_evaluated()`（或 `if consteval`）的结果：

```cpp run ok
#include <type_traits>
constexpr int which() { return std::is_constant_evaluated() ? 1 : 2; }
int non_constexpr_twin() { return std::is_constant_evaluated() ? 1 : 2; }
const int a = which();               // const int 的初始化会先尝试常量求值 → 1
int main() {
    int b = which();                 // 非 const 变量：不是明显常量求值 → 2
    return (a == 1 && b == 2 && non_constexpr_twin() == 2) ? 0 : 1;
}
```

## constexpr 不影响函数类型（¶5）

¶5 规定，`constexpr` 和 `consteval` 不影响 constexpr 函数的类型。所以不能根据是否 constexpr 来重载，也不能让一个 constexpr 定义和一个非 constexpr 定义共存：

```cpp error
constexpr int bar(int x, int y) { return x + y + x * y; }
int bar(int x, int y) { return x * 2 + 3 * y; }   // error: bar 的重定义
```

如果想在编译期用一种实现、运行期用另一种实现，正确的做法是在同一个函数里用 `if consteval`（C++23，[[stmt.if]]）或 `std::is_constant_evaluated()` 做分支。函数指针 `int(*)(int, int)` 同样可以指向 constexpr 函数。constexpr 不是类型的一部分，所以也不会随函数指针传递（通过函数指针在常量表达式中调用时，要求指针值本身是常量）。

## constexpr 变量（¶6）

¶6 规定了在对象声明中使用 `constexpr` 的效果和要求：

1. 使对象成为 const；
2. 对象必须是字面类型（[[basic.types.general]]），并且必须有初始化；
3. 变量必须**可常量初始化**（constant-initializable，[[expr.const.init#4]]）；
4. 作为对象的 constexpr 变量，以及 constexpr 引用所绑定的临时对象，必须具有**常量析构**（constant destruction，[[expr.const]]）。

```cpp error
struct pixel { int x, y; };
constexpr pixel ur = { 1294, 1024 };     // OK
constexpr pixel origin;                  // error: 缺少初始化器
struct NonLit { NonLit(); };
constexpr NonLit nl{};                   // error: 不是字面类型
constexpr int* leak = new int(1);        // error: 分配的内存在常量求值结束时未释放
```

`constexpr` 与 `const` 的区别在于：`const` 只表示不能通过这个名字修改对象，初始化可以发生在运行期；`constexpr` 要求初始化必须是常量表达式，因此值在翻译期就已知。整型和枚举类型的 const 变量如果恰好用常量表达式初始化，也可以在常量表达式中使用（[[expr.const.init#6]]、¶7），这是 C++98 遗留的特例。其他类型（如 `double`、类类型）的变量，只有声明为 `constexpr` 才能用于常量表达式。

常量析构保证编译期创建的对象在编译期也能销毁。例如在 C++20 中，`constexpr std::vector<int> v{1,2,3};` 非良构，因为 `v` 持有在常量求值中分配的堆内存，而这块内存必须在同一次常量求值中释放（瞬态分配，transient allocation）。

### constexpr 引用与可 constexpr 表示 {{c++26}}

```cpp
namespace N {
    void f() {
        int x;
        constexpr int& ar = x;              // C++26: OK
        static constexpr int& sr = x;       // error: x 在下面的命名空间作用域点上不可 constexpr 引用
    }
    // 此处的直接作用域是 N
}
```

在 C++23 及之前，constexpr 引用只能绑定到具有静态存储期的对象，因为地址必须是常量表达式。C++26（[[P2686]]）引入了 **constexpr-referenceable** 和 **constexpr-representable** 两个概念（[[expr.const.init#2]]、¶3）：从某个点 P 看，如果一个自动变量与 P 位于同一个函数参数作用域内（中间只隔着块作用域），它就是可 constexpr 引用的。于是：

- `ar` 是块作用域的自动 constexpr 引用。在它的初始化声明之后，`x` 与它同在 `f` 的函数作用域内，所以 OK；
- `sr` 是 `static` 的。[[expr.const.init#4]] 的 ¶4.3 要求它在其后最近的、直接作用域为命名空间作用域的那个点上也可表示，而那个点在 `f` 之外，`x` 在那里不可引用，所以非良构。

这一改动的直接动机是 C++26 的 `constexpr` 结构化绑定：`constexpr auto& [a, b] = local;` 需要绑定到局部对象。截至写作时，Clang 尚未实现这一点，对 `ar` 一行仍然报错。

!!! lawyer "constexpr 变量与 ODR"
    `constexpr` 变量是 const 的。如果读取它的值（左值到右值转换）可以在常量表达式中完成，这次读取就不构成 odr-use（[[basic.def.odr]]）。所以在函数内写了 `constexpr int n = 3;` 之后，lambda 可以不捕获 `n` 而直接使用它的值；但取 `&n` 或绑定引用属于 odr-use，需要捕获。

!!! pitfall "常见误解"
    - 误以为 constexpr 函数一定在编译期执行。实际上只有在需要常量表达式的上下文（或明显常量求值的上下文）中，才保证在编译期求值；在其他地方它就是普通的函数调用（编译器可以选择常量折叠，但那属于优化）。需要保证编译期求值时，用 `consteval`，或把结果赋给 `constexpr` 变量。
    - 误以为 constexpr 成员函数隐含 const。C++11 是这样，C++14 起不再隐含。
    - 误以为 `constexpr` 变量放在头文件中会违反 ODR。不会：命名空间作用域的 constexpr 变量具有内部链接（每个 TU 一份），静态数据成员则是 inline 的。
    - 误以为 consteval 函数不是 constexpr 函数。按 ¶2 的定义，它是。

!!! summary "小结"
    | | `constexpr` 函数 | `consteval` 函数 | `constexpr` 变量 |
    |---|---|---|---|
    | 能否运行期调用/使用 | 能 | 不能（调用必须是常量表达式） | 值在翻译期已知，对象在运行期也存在 |
    | 隐式 inline | 是 | 是 | 仅静态数据成员 |
    | 隐式 const | 否（C++14 起） | 否 | **是** |
    | 结构要求 | 不是协程 | 不是协程；不能是析构/分配/释放函数 | 字面类型、有初始化器、可常量初始化、常量析构 |
    | 所有声明一致 | 必须 | 必须 | 只能在定义上写 |

!!! question "思考题 1"
    下面的程序在 C++20 和 C++23 中分别是什么状态？

    ```cpp
    #include <cstdio>
    constexpr void log(const char* s) { std::puts(s); }
    int main() { log("hi"); }
    ```

<details markdown="1">
<summary>答案</summary>

`std::puts` 不是 constexpr 函数，所以对 `log` 的任何调用都不可能是核心常量表达式。在 C++20 中，这是一个没有任何实参能使其常量求值的非模板 constexpr 函数，属于 IFNDR（实现可以拒绝，Clang 会报 `-Winvalid-constexpr` 错误）。C++23 起（P2448），程序良构，`log("hi")` 在运行期正常打印。
</details>

!!! question "思考题 2"
    为什么 `constexpr std::string s = "hello";` 在 C++20 中通常非良构，而 `constexpr std::string_view sv = "hello";` 良构？

<details markdown="1">
<summary>答案</summary>

¶6 要求 `constexpr` 变量具有常量析构，且其初始化是常量表达式；[[expr.const]] 要求常量求值中分配的内存必须在该次求值结束前释放。`std::string` 的内容超出短字符串优化（SSO）的容量时会分配堆内存，初始化完成时它仍持有这块内存，因此初始化不是常量表达式。即使字符串很短、走了 SSO（是否如此取决于实现），能否成为 constexpr 变量也取决于实现，libc++ 和 libstdc++ 的结果就可能不同。`string_view` 只保存指向字符串字面量（静态存储期对象）的指针和长度，不分配内存，是字面类型且析构平凡，所以良构。
</details>
