---
title: constexpr 与 consteval 说明符
summary: constexpr/consteval 能用在哪里；constexpr 函数在当前草案中只剩"不能是协程"一条结构要求；constexpr 函数与普通函数的行为一致性；constexpr 变量必须是字面类型、可常量初始化、具有常量析构；隐含的 const 与 inline
status: done
since: c++11
papers: P2448R2, P2242R3, P2647R1, P1064R0, P0784R7, P1073R3, P1331R2, P2686
related: expr.const, expr.const.imm, expr.const.init, dcl.constinit, dcl.inline, basic.types, stmt.if
tags: 声明, 常量求值, constexpr, consteval
updated: 2026-10-17
---

`constexpr` 是 C++11 以来变化最剧烈的特性之一：从"只能有一条 return 语句"的 C++11，到 C++20 可以分配内存、调用虚函数、使用 try 块，再到 C++23 取消了"必须**可能**在编译期求值"的要求，constexpr 函数在今天几乎就是"**允许**在常量表达式中被调用的普通函数"。本节（[dcl.constexpr]）只规定**说明符本身**：能修饰什么、对函数和变量各意味着什么。真正决定"某次求值是不是常量表达式"的规则在 [[expr.const]]——这是读懂本节的前提。

本节同时规定 `consteval`（C++20）：它声明**立即函数**（immediate function），对它的每次调用都**必须**在编译期求值（[[expr.const.imm]]）。

## 适用对象（¶1）

¶1 的规则逐条列出：

1. `constexpr` 只能用于：**变量或变量模板的定义**、**结构化绑定声明**、**函数或函数模板的声明**。
2. `consteval` 只能用于**函数或函数模板的声明**。
3. 在**首次声明**上带 `constexpr` 或 `consteval` 的**函数**或**静态数据成员**，隐式是 inline 的（[[dcl.inline]]）。
4. 若一个函数（模板）的任一声明带 `constexpr` 或 `consteval`，则它的**所有**声明都必须带**同一个**说明符。Note 1：显式特化可以与主模板不同。
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

为什么变量只能在**定义**上写 `constexpr`？因为 `constexpr` 变量的意义在于"编译器在使用点就知道它的值"；一个没有初始化器的声明不提供值，加 `constexpr` 毫无意义。函数则不同：一个 `constexpr` 函数可以先声明、后定义，只是在定义可达之前调用它不能产生常量表达式（见下面标准例子中的 `small(2)`）。

为什么不允许 `constexpr` 参数？因为同一个函数（同一段机器码）会被不同的实参调用，参数的值不可能是"编译期已知"的。需要编译期参数时，用模板参数（包括 C++20 的类类型 NTTP），或把函数声明为 `consteval`。

### 声明顺序很重要：标准的 pixel 例子

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

调用一个**未定义**的 constexpr 函数不是核心常量表达式（[[expr.const.core]]），所以 `small(2)` 不满足 `constexpr` 变量"必须可常量初始化"的要求（¶6）。这条规则意味着**常量求值是按"翻译到这一点为止"的状态进行的**——这与模板实例化点的"延后"语义不同。

### 隐式 inline

¶1 第三条：**函数**与**静态数据成员**在首次声明带 `constexpr`/`consteval` 时隐式 inline。这有两个后果：

- `constexpr` 函数可以（而且通常必须）定义在头文件中，每个使用它的 TU 都有一份定义，不违反 ODR（[[basic.def.odr]]）。
- C++17 起，`static constexpr` 数据成员在类内声明即是**定义**，不再需要类外的 `constexpr int S::m;`——那条类外声明现在是冗余的重声明，已被弃用（[[depr.static.constexpr]]）。

```cpp run ok
struct S { static constexpr int m = 1; };
const int* p = &S::m;     // C++17 起 OK: S::m 是 inline 变量，类内声明即定义
int main() { return *p - 1; }
```

!!! pitfall "命名空间作用域的 constexpr 变量不是 inline"
    隐式 inline **只适用于静态数据成员**。命名空间作用域的 `constexpr int N = 10;` 不是 inline 变量；它因为是 const 而具有**内部链接**（[[basic.link#3]]），每个包含该头文件的 TU 都有一个**独立的对象**——`&N` 在不同 TU 中不同。通常无害，但若需要唯一地址（或在 inline 函数中 odr-use 它而不想违反 ODR），应写成 `inline constexpr int N = 10;`。标准库中的 `std::is_same_v` 等变量模板都写成了 `inline constexpr`。

## constexpr 函数与立即函数（¶2）

¶2 在函数声明中使用 `constexpr` 或 `consteval`，就把该函数声明为 **constexpr 函数**（[[g:constexpr-function]]）。Note 3：用 `consteval` 声明的函数是**立即函数**（[[expr.const.imm]]）。

所以从术语上说，consteval 函数**也是** constexpr 函数——凡是对"constexpr 函数"适用的规则（隐式 inline、¶3 的结构要求、¶4 的行为一致性）也适用于 consteval 函数。区别在于立即函数的每次调用都必须是常量表达式（除非它本身位于立即函数上下文中）。

¶2 最后一句：**析构函数、分配函数、释放函数**不能是 `consteval`。

```cpp error
struct S {
    consteval ~S() { }                          // error: 析构函数不能是 consteval
    consteval void* operator new(decltype(sizeof 0));   // error: 分配函数不能是 consteval
};
```

为什么？析构函数和 `operator new/delete` 是被语言**隐式调用**的：对象离开作用域时自动调用析构、`new` 表达式隐式调用分配函数。如果它们是立即函数，那么运行期创建的任何该类型对象都无法销毁/分配——一个只能在编译期销毁的类型基本没法用。（它们可以是 `constexpr` 的：C++20 起 constexpr 析构函数是合法的，[[P0784R7]]。）

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

¶3 在当前草案中只剩下一条：

!!! std
    A function is *constexpr-suitable* if it is not a coroutine. Except for instantiated constexpr functions, non-templated constexpr functions shall be constexpr-suitable.

    函数若不是协程，就是 constexpr-suitable 的。除实例化而来的 constexpr 函数外，非模板化的 constexpr 函数必须是 constexpr-suitable 的。

也就是说，对一个 constexpr 函数**定义本身**的结构性要求，只剩"**不能是协程**"（协程的挂起/恢复需要堆分配的协程帧和运行期调度，目前的常量求值模型无法表达）。其余一切——能不能声明静态变量、能不能调用非 constexpr 函数、能不能有未初始化的变量——都不再是定义层面的要求，而是推迟到**某次常量求值**时由 [[expr.const.core]] 检查：真的执行到不允许的操作，该次求值就不是常量表达式。

"除实例化而来的 constexpr 函数外"：模板实例化出的 constexpr 函数即便不满足（例如由于模板参数，函数体变成了协程——实际上很难发生），也不会使程序非良构，只是不能用于常量求值。

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

（`pow_(2, 4)` 等于 8，因为循环 `--n > 0` 只执行 3 次——这是标准例子 `g` 的原样逻辑。）

标准例子中的 `uninit()`：

```cpp
constexpr int uninit() {
    struct { int a; } s;
    return s.a;          // 标准注释为 "error: uninitialized read of s.a"
}
```

这里的 "error" 应理解为：**任何**对 `uninit()` 的常量求值都会失败（读取未初始化的值不是核心常量表达式），而不是函数定义本身非良构——按 C++23 起的规则，定义本身是良构的，Clang 也接受它。若在常量表达式中调用它，则那个常量表达式出错。

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
    | C++14 | 局部变量、赋值、`if`/`switch`/循环；不再隐含 const | （"放宽 constexpr 函数的限制"提案） |
    | C++17 | lambda 可以是 constexpr；`if constexpr` | — |
    | C++20 | 虚函数（[[P1064R0]]）、`try` 块（但不能真的抛出）、平凡默认初始化（[[P1331R2]]）、`asm` 声明（只要不被求值）、改变联合体活跃成员、constexpr 析构函数与 `new`/`delete`（[[P0784R7]]）、`consteval`（[[P1073R3]]） | |
    | C++23 | 非字面类型的变量、`goto`、标号、`static`/`thread_local` 变量（只要不被求值，[[P2242R3]]）；不再要求"存在至少一组实参使其成为常量表达式"（[[P2448R2]]）；`static constexpr` 局部变量可在常量求值中使用（[[P2647R1]]） | |
    | C++26 | 结构要求只剩"不是协程"；常量求值中可以 placement new、可以从 `void*` 转换、可以抛出并捕获异常；具有虚基类的类也可以有 constexpr 构造/析构函数 | |

!!! note "P2448：从 IFNDR 到良构"
    C++20 及之前有一条规则：对非模板的 constexpr 函数，若**不存在任何**实参值使得对它的调用能成为核心常量表达式，则程序非良构、不要求诊断（IFNDR）。这条规则的问题是：一个函数在 C++20 下"永远不能常量求值"（例如调用了一个尚未 constexpr 化的库函数），到了 C++23 那个库函数变成 constexpr 了，它就又"能"了——同一份代码的良构性随标准库版本漂移。[[P2448R2]] 删除了这条规则：constexpr 函数可以永远不被常量求值，程序依然良构。Note 5 至今保留了这层意思："可以写出一个 constexpr 函数，它的任何调用都不满足核心常量表达式的要求。"

!!! impl "实现尚未跟上的部分"
    截至写作时，本机 Clang（23）：
    - 仍然拒绝具有虚基类的类的 constexpr 构造函数（诊断为 "constexpr constructor not allowed in struct with virtual base class"），这是 C++23 的旧规则；
    - 尚不支持常量求值中的异常抛出（`try { throw 1; } catch (int) { … }` 在 `static_assert` 中求值失败）；
    - 在 `-std=c++20` 下仍按旧规则对"永远不能常量求值"的函数报 `-Winvalid-constexpr` 错误（这在 C++20 中是 IFNDR，报错是允许的）。

## 行为一致性（¶4）

¶4 在给定上下文中调用 constexpr 函数，结果与调用一个**等价的非 constexpr 函数**在**所有方面**都相同，除了：

- ¶4.1 constexpr 函数的调用**可以出现在常量表达式中**；
- ¶4.2 在常量表达式中**不进行复制消除**（[[class.copy.elision]]）。

这是对程序员的承诺：给函数加上 `constexpr` 不会改变它在运行期的行为。为什么常量求值中不做复制消除？因为复制消除是**可选的**优化（除了 C++17 的强制消除），若常量求值中可以选择做或不做，常量表达式的值就可能依赖于实现的选择（例如复制构造函数有可观察的副作用时）。规定"一律不做"，结果就是确定的。

Note 4 指出一个微妙之处：加上 `constexpr` 可能改变**某个表达式是否为常量表达式**，进而间接改变函数内部 `std::is_constant_evaluated()`（或 `if consteval`）的结果：

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

¶5 `constexpr` 和 `consteval` 对 constexpr 函数的**类型**没有影响。所以不能基于 constexpr 性重载，也不能让一个 constexpr 定义和一个非 constexpr 定义共存：

```cpp error
constexpr int bar(int x, int y) { return x + y + x * y; }
int bar(int x, int y) { return x * 2 + 3 * y; }   // error: bar 的重定义
```

想要"编译期一个实现、运行期另一个实现"，正确工具是在同一个函数里用 `if consteval`（C++23，[[stmt.if]]）或 `std::is_constant_evaluated()` 分支。函数指针 `int(*)(int, int)` 同样可以指向 constexpr 函数——constexpr 性不是类型的一部分，也就不会随函数指针传递（通过函数指针在常量表达式中调用则要求指针值本身是常量）。

## constexpr 变量（¶6）

¶6 在对象声明中使用 `constexpr`：

1. **使对象为 const**；
2. 对象必须是**字面类型**（[[basic.types.general]]）且**必须被初始化**；
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

`constexpr` 与 `const` 的区别：`const` 只说"不能通过这个名字修改"，初始化可以在运行期；`constexpr` 要求初始化**必须是常量表达式**，因此值在翻译期已知。对整型和枚举类型的 const 变量，若恰好用常量表达式初始化，也可以在常量表达式中使用（[[expr.const.init#6]]、¶7），这是 C++98 遗留的特例；对其他类型（如 `double`、类类型），只有 `constexpr` 变量才能用于常量表达式。

"常量析构"保证编译期创建的对象在编译期也能销毁——例如 C++20 中 `constexpr std::vector<int> v{1,2,3};` 非良构，因为 `v` 持有在常量求值中分配的堆内存，而这块内存必须在**同一次**常量求值中释放（瞬态分配，transient allocation）。

### constexpr 引用与"可 constexpr 表示"{{c++26}}

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

在 C++23 及之前，constexpr 引用只能绑定到具有**静态存储期**的对象（地址必须是常量表达式）。C++26（[[P2686]]）引入了 **constexpr-referenceable** / **constexpr-representable**（[[expr.const.init#2]]、¶3）：从某个点 P 看，若自动变量与 P 位于**同一个函数参数作用域**内（中间只隔着块作用域），它就是"可 constexpr 引用"的。于是：

- `ar` 是块作用域的自动 constexpr 引用，在它的初始化声明之后，`x` 与之同在 `f` 的函数作用域内——OK；
- `sr` 是 `static` 的，[[expr.const.init#4]] 的 ¶4.3 要求它在**其后最近的、直接作用域为命名空间作用域的点**上也可表示——那个点在 `f` 之外，`x` 不再可引用——非良构。

这一改动的直接动机是 C++26 的 `constexpr` 结构化绑定：`constexpr auto& [a, b] = local;` 需要绑定到局部对象。截至写作时 Clang 尚未实现这一点，对 `ar` 一行仍报错。

!!! lawyer "constexpr 变量与 ODR"
    `constexpr` 变量是 const 的，读取它的值（左值到右值转换）若可以在常量表达式中完成，就**不构成 odr-use**（[[basic.def.odr]]）。所以在函数内 `constexpr int n = 3;` 之后，lambda 可以**不捕获**而直接使用 `n` 的值；但取 `&n` 或绑定引用就是 odr-use，需要捕获。

!!! pitfall "常见误解"
    - "constexpr 函数一定在编译期执行"——错。只有在需要常量表达式的上下文（或明显常量求值的上下文）中才保证在编译期求值；其他地方是普通函数调用（编译器可以选择常量折叠，但那是优化）。需要保证编译期求值时用 `consteval` 或把结果赋给 `constexpr` 变量。
    - "constexpr 成员函数隐含 const"——C++11 如此，C++14 起不再隐含。
    - "`constexpr` 变量在头文件中会违反 ODR"——不会：命名空间作用域的是内部链接（每个 TU 一份），静态数据成员是 inline。
    - "consteval 函数不是 constexpr 函数"——按 ¶2 的定义，它是。

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

`std::puts` 不是 constexpr 函数，所以 `log` 的任何调用都不可能是核心常量表达式。C++20：非模板 constexpr 函数没有任何实参能使其常量求值 → IFNDR（实现可以拒绝，Clang 会报 `-Winvalid-constexpr` 错误）。C++23 起（P2448）：良构，`log("hi")` 在运行期正常打印。
</details>

!!! question "思考题 2"
    为什么 `constexpr std::string s = "hello";` 在 C++20 中通常非良构，而 `constexpr std::string_view sv = "hello";` 良构？

<details markdown="1">
<summary>答案</summary>

¶6 要求 `constexpr` 变量具有常量析构，且其初始化是常量表达式；[[expr.const]] 要求常量求值中分配的内存必须在该次求值结束前释放。`std::string` 在内容超出短字符串优化（SSO）容量时会分配堆内存，它在初始化完成时仍持有这块内存，因此不是常量表达式；即使字符串很短而走了 SSO（是否如此取决于实现），能否成为 constexpr 变量也是实现相关的——libc++ 和 libstdc++ 的结果就可能不同。`string_view` 只保存指向字符串字面量（静态存储期对象）的指针和长度，没有分配，是字面类型且析构平凡，所以良构。
</details>
