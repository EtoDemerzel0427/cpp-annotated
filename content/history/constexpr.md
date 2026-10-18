---
title: constexpr：编译期计算的十五年扩张
summary: 从 C++98 的整型常量表达式和模板元编程，到 C++11 只能写一条 return 的 constexpr 函数，再到 C++20 的编译期 vector、consteval、constinit，以及 C++26 的编译期异常与静态反射：每一步放宽了什么、为什么放宽、委员会在哪些地方停下来
status: draft
since: c++11
order: 55
papers: N1521, N2235, N3652, P0170R1, P0292R2, P0784R7, P1073R3, P1143R2, P0595R2, P1938R3, P2242R3, P2448R2, P2738R1, P2747R2, P3068R6, P1235R0
related: expr.const, expr.const.core, history/template-metaprogramming, expr.const.imm, dcl.constexpr, dcl.constinit, stmt.if, meta.const.eval, topics/compile-time-programming, topics/undefined-behavior
tags: 沿革, constexpr, consteval, constinit, 常量求值
updated: 2026-10-18
---

C++11 的 `constexpr` 函数只能由一条 `return` 语句构成；C++26 的常量求值里可以分配内存、调用虚函数、抛出并捕获异常，还能通过静态反射查询程序自身的结构。这十五年里，几乎每一版标准都在放宽常量求值的限制，标准库里标上 `constexpr` 的函数也越来越多。

这一页按时间顺序讲这条线：每一版放宽了什么、提案给出的理由是什么、委员会在哪些地方选择了停下来。规则本身请看 [[expr.const]]、[[expr.const.core]]、[[dcl.constexpr]]，各工具的分工与用法见 [[topics/compile-time-programming]]。

本页的代码例子都用本机 Clang 23 在不同的 `-std` 模式下验证过，用来展示同一段代码在不同标准下的判定变化。文中多处用特性测试宏的值标注某个特性并入工作草案的年月：例如 `__cpp_constexpr` 的值 `201304L` 表示这一版规则在 2013 年 4 月的会议上通过。这些值列在 [[cpp.predefined]] 和 [[version.syn]] 中。

## 一、constexpr 之前：C++98 能在编译期算什么

### 整型常量表达式

C++98 从 C 继承了常量表达式的概念，而且只承认整型（和枚举）的版本。数组边界、`case` 标签、枚举值、非类型模板实参都要求整型常量表达式（integral constant expression）。能出现在里面的东西很少：字面量、枚举值、用常量表达式初始化的 `const` 整型变量、`sizeof`，以及它们之间的内置运算。函数调用一律不行。

这带来一个长期的尴尬。Dos Reis 与 Stroustrup 在 [[N2235]] §3.1 里举的第一个例子就是 `std::numeric_limits<int>::max()`：它在功能上等价于宏 `INT_MAX`，却因为是函数调用而不是整型常量表达式。结果是需要编译期常量的地方，程序员只能退回去用宏。

同一篇提案的 §3.4 还指出了另一个问题：一个看起来是常量的变量，可能悄悄地走了动态初始化。

```cpp
struct S { static const int size; };
const int limit = 2 * S::size;   // 动态初始化：S::size 的初始化在后面
const int S::size = 256;
const int z = std::numeric_limits<int>::max();   // 动态初始化：函数调用
```

`S::size` 虽然用常量初始化，但它的定义出现得太晚，`limit` 的初始化器就不是常量表达式了。语言没有提供一种手段让程序员要求某个变量必须在编译期初始化，编译器也不会提示。二十年后 C++20 用 `constinit` 才正面回答了这个问题（见第五节）。

### 模板元编程

另一条路是模板。C++ 的模板实例化机制可以用来在编译期计算值：用递归的类模板加一个特化作为终止条件，结果放在一个枚举成员里。

```cpp run std=c++98 ok
template <unsigned N> struct Factorial { enum { value = N * Factorial<N - 1>::value }; };
template <> struct Factorial<0> { enum { value = 1 }; };

int table[Factorial<5>::value];                           // 120 个元素
typedef char check[Factorial<5>::value == 120 ? 1 : -1];  // C++98 版的 static_assert
int main() {}
```

这种技术在 1990 年代后期被广泛使用（详见 [[history/template-metaprogramming]]）。它能工作，但有明显的代价：计算要用类型和特化来表达，条件分支要靠偏特化，循环要靠递归实例化；只能算整数和类型；出错时的诊断信息是一长串实例化栈；每一步计算都会在编译器里留下一个类模板实例，编译开销大。

Stroustrup 在 HOPL IV §4.2.7 中转述他与 Dos Reis 2010 年论文的评价，说这种做法 "tedious and error-prone"。

## 二、2003–2007：广义常量表达式

### 第一版提案：没有关键字

2003 年，Gabriel Dos Reis 提交了 *Generalized Constant Expressions*（[[N1521]]）。据 HOPL IV §4.2.7，这是他与 Stroustrup 一起提出的方案，目标包括：让编译期计算类型安全；把计算从运行期挪到编译期以提高效率；支持嵌入式系统（尤其是把数据放进 ROM）；让编译期编程和普通编程尽量相似。

核心想法很简单：允许足够简单的函数出现在常量表达式中，同时允许足够简单的用户定义类型（后来叫字面类型，literal type）的对象出现在常量表达式中。

最初的方案没有引入新关键字，打算由编译器自己识别哪些函数足够简单。[[N2235]] §4.5 记录了这一点的转折：2003 年 10 月 Kona 会议上，Evolution 工作组的共识是需要一个语法标记。于是有了 `constexpr`。

为什么要显式标记？HOPL IV 给了两个理由。第一，如果不标记，一个函数能否用在常量表达式中就取决于各家编译器有多聪明，用户代码的可移植性无从保证。第二，编译器为了随时可能的常量求值，得把所有函数的函数体一直保留着。至于名字，Stroustrup 说选 `constexpr` 是因为它足够好记，又足够古怪，不会和现有代码冲突。

### N2235 的规则：一条 return 语句

经过多轮修订，2007 年 4 月的 [[N2235]]（第 5 版，作者 Dos Reis、Stroustrup、Maurer）成为并入 C++0x 工作草案的版本。按它 §4.1 的定义，一个常量表达式函数必须满足：

- 返回非 `void` 类型；
- 函数体只有一条形如 `return expr;` 的语句，并且把参数替换成常量表达式之后，`expr` 是常量表达式；
- 用关键字 `constexpr` 声明。

提案自己的说法是，这只是给"带参数的具名常量表达式"换一种写法。它同时引入了 `constexpr` 构造函数（使用户定义类型可以成为字面类型）和浮点常量表达式。

N2235 还明确禁止递归，并要求常量表达式函数在第一次使用之前定义。提案解释说，递归本可以靠实现限制来防止编译器无限递归，但在看到有说服力的用例之前不打算允许。这一条没有保留到最后：在 C++11 的最终文本里，递归的 `constexpr` 函数是允许的，实现可以对递归深度设上限（[[implimits]]）。

```cpp run std=c++11 ok
constexpr unsigned long long fact(unsigned n) {
    return n <= 1 ? 1 : n * fact(n - 1);   // 单条 return + 递归：C++11 允许
}
static_assert(fact(5) == 120, "");
int main() {}
```

同样的计算写成循环，在 C++11 下是非良构的：

```cpp run std=c++11 error
constexpr unsigned long long fact(unsigned n) {
    unsigned long long r = 1;                  // error（C++11）：constexpr 函数里不能声明变量
    for (unsigned i = 2; i <= n; ++i) r *= i;  // error（C++11）：不允许 for 语句
    return r;
}
int main() {}
```

于是 C++11 时代的 `constexpr` 函数普遍写成条件运算符加递归的函数式风格。

### 四年的争论

`constexpr` 的标准化并不顺利。Stroustrup 在 HOPL IV §4.2.7 回忆，这个提案曾被反复认为既没用又无法实现；后来各主要编译器的作者实现了它，证明无法实现的说法是错的。他对这段讨论的评价是：

> "The discussions about constexpr were about the most heated and unpleasant ever." （Stroustrup，HOPL IV §4.2.7）

他还写道，初版花了四年才通过标准化流程，此后又用了十二年才把这件事做完。这是当事人一方的回顾，委员会会议记录中的具体反对理由本页没有逐一核对。

与语言特性配套，Dos Reis 与 Stroustrup 在 [[N2219]] 中提出给标准库加 `constexpr`，后续又有 Kosnik 与 Krügler 的几篇 *Constexpr Library Additions*（如 [[N3302]]、[[N3470]]、[[N3471]]）。C++11 中 `numeric_limits` 的成员函数终于成了 `constexpr`，N2235 开头提到的那个尴尬得以消除。

## 三、C++14：允许局部变量和循环

C++11 发布后不久，用户开始要求放宽限制。HOPL IV §5.5 的描述是：到 2012 年，人们已经不再害怕 `constexpr` 函数，开始要求放宽对其实现的限制；有人希望在 `constexpr` 函数里什么都能做，但无论用户还是编译器实现者都还没准备好。

Richard Smith 先后提交了 [[N3597]] 和 [[N3652]]。后者 2013 年 4 月获得通过（`__cpp_constexpr` 的值随之变为 `201304L`），主要改动有：

- 函数体可以包含局部变量声明（必须初始化，且不能是 `static` 或 `thread_local`）、`if`/`switch`、各种循环；
- 可以修改生命期在本次常量求值中开始的对象；
- 返回类型可以是 `void`；
- `constexpr` 非静态成员函数不再隐式带 `const`。

最后一条是 N3652 标题的后半部分。C++11 中 `constexpr` 成员函数自动是 `const` 的，这和允许修改对象的新规则冲突，所以必须去掉。这是 `constexpr` 历史上少有的一次不兼容修改：C++11 代码里依赖隐式 `const` 的成员函数，在 C++14 下要显式补上 `const`。

```cpp run std=c++14 ok
struct Point {
    int x, y;
    constexpr Point(int x, int y) : x(x), y(y) {}
    constexpr void move(int dx) { x += dx; }   // C++11：隐式 const，不能赋值；返回类型也不能是 void
};
constexpr Point shifted() {
    Point p{1, 2};       // C++11：不能声明局部变量
    p.move(3);           // C++11：函数体只能有一条 return 语句
    return p;
}
static_assert(shifted().x == 4, "");
int main() {}
```

在 `-std=c++11` 下 Clang 对这段代码报出的错误与上面的注释一一对应，`static_assert` 也随之失败；在 `-std=c++14` 下没有任何诊断。

HOPL IV 特别指出，这些局部变量只存在于编译器里，求值过程不能对调用者的环境产生副作用。这一点决定了此后所有放宽的边界：常量求值可以做越来越多的事，但它的一切效果都必须在求值结束前收拢。

## 四、C++17：constexpr lambda 与 if constexpr

### lambda 默认是 constexpr

C++11 和 C++14 的 lambda 不能出现在常量表达式中。Faisal Vali 的 [[P0170R1]] 在 2016 年 3 月（Jacksonville 会议）获得通过：lambda 的函数调用运算符只要满足 `constexpr` 函数的要求，就隐式是 `constexpr` 的，也可以显式写 `constexpr`。

这是 `constexpr` 第一次不需要显式标注。后来主张所有函数默认 `constexpr` 的提案（第九节）就以此为论据之一。

```cpp run std=c++17 ok
auto square = [](int x) { return x * x; };   // 没写 constexpr
static_assert(square(7) == 49);              // C++17 起 OK；C++14 下不是常量表达式
int main() {}
```

### if constexpr：从 static_if 到丢弃语句

`if constexpr` 的前史比 `constexpr` lambda 更曲折。2012 年，Sutter、Bright 与 Alexandrescu 提出了借鉴 D 语言的 `static if`（[[N3329]]），它可以出现在命名空间和类作用域，并且不引入新的作用域。2013 年 Stroustrup、Dos Reis 与 Sutton 的 [[N3613]] 对此提出了系统的反对意见。他们的主要理由是：同一个语法在不同语境下有三种语义；未选中的分支不做语法分析，使程序更难阅读、维护和调试，也妨碍基于 AST 的工具；它还可能阻碍概念（concepts）等特性的发展。他们认为提案想解决的问题是真实存在的，其中约束模板这一部分应该由概念来解决。`static if` 此后没有继续推进。

几年后，Ville Voutilainen 以范围小得多的 `constexpr_if`（[[P0128R1]]）重新提出这一想法：只作为语句，只出现在函数体内，并且有自己的作用域。Jens Maurer 的 [[P0292R2]] 把语法改成了 `if constexpr`，2016 年 6 月通过（`__cpp_if_constexpr` 为 `201606L`）。它的关键语义是未选中的分支成为丢弃语句（discarded statement），在模板中不实例化（[[stmt.if#2]]）。

```cpp run std=c++17 ok
#include <string>
#include <type_traits>
template <class T>
std::string describe(T v) {
    if constexpr (std::is_integral_v<T>) return "int:" + std::to_string(v);
    else return "other";   // T = const char* 时，上一分支被丢弃，不会实例化 to_string(const char*)
}
int main() { describe(1); describe("x"); }
```

`if constexpr` 本身不是常量求值能力的扩张，它的作用是让模板代码根据编译期条件选择要实例化的代码，取代了大量基于标签分派和 SFINAE 的写法。

## 五、C++20：几乎完整的语言子集

C++20 是 `constexpr` 扩张最快的一版。HOPL IV §9.3.3 列出了这一版与编译期计算有关的主要工作，下面分语言、库和新关键字三部分讲。

### 语言：虚函数、try、union、动态分配

2018–2019 年间通过的一组提案，把常量求值中禁止的东西一项项去掉：

| 提案 | 内容 |
|---|---|
| [[P1064R0]]（Dimov、Vassilev） | 常量求值中可以调用虚函数 |
| [[P1002R1]]（Dionne） | `constexpr` 函数中可以出现 `try` 块（但求值到 `throw` 仍然不是常量表达式） |
| [[P1327R1]]（Dimov、Vassilev、Smith） | 允许 `dynamic_cast` 和多态 `typeid` |
| [[P1330R0]]（Dionne、Vandevoorde） | 常量求值中可以改变 union 的活跃成员 |
| [[P1331R2]]（Johnson） | 允许平凡默认初始化（不初始化的局部变量），只要求值时不读取 |
| [[P1668R1]]（Keane） | `constexpr` 函数中可以出现不被求值的内联汇编 |
| [[P0784R7]]（Dimov、Dionne、Ranns、Smith、Vandevoorde） | `constexpr` 析构函数；常量求值中可以 `new`/`delete` |

最后一项影响最大。[[P0784R7]] 的标题是 *More constexpr containers*，它的目标是让 `std::vector` 这样的容器能在编译期使用。为此需要两件事：析构函数可以是 `constexpr` 的；常量求值中可以分配内存。

分配的规则是**瞬时分配**（transient allocation）：常量求值中通过 `new` 或 `std::allocator<T>::allocate` 分配的内存，必须在同一次求值结束之前释放。编译器在求值时跟踪每一块分配，求值结束时如果还有没释放的，或者释放方式不匹配，表达式就不是常量表达式（[[expr.const.core]]）。

```cpp run std=c++20 ok
struct Shape {
    virtual constexpr ~Shape() = default;
    virtual constexpr int area() const = 0;
};
struct Square : Shape {
    int s;
    constexpr explicit Square(int s) : s(s) {}
    constexpr int area() const override { return s * s; }
};
constexpr int total() {
    Shape* p = new Square(3);   // 常量求值中分配
    int a = p->area();          // 常量求值中的虚调用
    delete p;                   // 必须在求值结束前释放
    return a;
}
static_assert(total() == 9);
int main() {}
```

在 `-std=c++17` 下这段代码报错：析构函数不能是 `constexpr`，虚函数也不能是 `constexpr`。

### 库：vector 和 string

有了语言层面的支持，Louis Dionne 的 [[P1004R2]] 和 [[P0980R1]] 分别让 `std::vector` 和 `std::string` 的成员函数成为 `constexpr`，2019 年 7 月（Cologne 会议）通过，`__cpp_lib_constexpr_vector` 为 `201907L`。同一时期还有 `<algorithm>`（[[P0202R3]]）、`swap` 相关函数（[[P0879R0]]）、`<numeric>`（[[P1645R1]]）等一批库提案。

```cpp run std=c++20 ok
#include <numeric>
#include <string>
#include <vector>
constexpr int sum_squares(int n) {
    std::vector<int> v;
    for (int i = 1; i <= n; ++i) v.push_back(i * i);
    return std::accumulate(v.begin(), v.end(), 0);
}   // v 在这里析构，内存在求值结束前释放
static_assert(sum_squares(4) == 30);

constexpr std::string greet() { return std::string("hello, ") + "world"; }
static_assert(greet().size() == 12);
int main() {}
```

瞬时分配的限制意味着 `vector` 不能跨越常量求值的边界留下来：

```cpp run std=c++20 error
#include <vector>
constexpr std::vector<int> v = {1, 2, 3};   // error: 分配的内存在求值结束时没有释放
int main() {}
```

Clang 的诊断是 `pointer to subobject of heap-allocated object is not a constant expression`。允许编译期分配的内存留到运行期（非瞬时分配）是后来一直有人提、但至今没有进入标准的方向，例如 Barry Revzin 的 [[P3032R2]] *Less transient constexpr allocation*。C++26 采取了另一种办法：用 `std::define_static_array` 等函数（[[P3491R3]]）把编译期得到的数据显式复制成静态存储期的数组。

### consteval：只能在编译期调用的函数

`constexpr` 函数可以在编译期调用，也可以在运行期调用。有些函数只应该在编译期存在。Smith、Sutton 与 Vandevoorde 的 [[P1073R0]] 最初把这种函数叫作 `constexpr!` 函数，修订到 R2 时改称立即函数（immediate function），关键字定为 `consteval`，[[P1073R3]] 于 2018 年 11 月（San Diego 会议）通过。

提案开宗明义，主要动机来自 SG7 正在做的编译期反射：反射的查询函数很可能就是立即函数。其他动机还包括替代函数式宏、让 `source_location::current()` 报告最外层调用的位置等。P1073R0 还指出，立即函数永远不需要被后端看到，也就是不会生成目标代码。

```cpp run std=c++20 error
consteval int sq(int x) { return x * x; }
constexpr int a = sq(4);          // OK
int runtime_value();
int b = sq(runtime_value());      // error: 立即函数的调用必须是常量表达式
int main() {}
```

这条线一直延续到 C++26：[[P2996R13]] 中 `std::meta` 命名空间里的反射函数全部是 `consteval` 的（见第七节）。C++23 的 [[P2564R3]] *consteval needs to propagate up* 又补了一个缺口：模板和 lambda 中调用立即函数时，外层函数可以自动升级为立即函数，而不是直接报错。

### constinit：要求静态初始化

第一节提到的变量悄悄走了动态初始化的问题，到 C++20 才有了语言层面的答案。Eric Fiselier 的 [[P1143R0]] 最初提议一个属性 `[[constinit]]`，参考了 Clang 已有的 `require_constant_initialization` 属性。到 R1 改成了关键字，理由是这个特性的目的就是强制检查，而属性可以被编译器忽略。[[P1143R2]] 2019 年 7 月通过。

提案的动机直接点名静态初始化顺序问题（static initialization order fiasco），并说明常量初始化的规则复杂、各方言不一致，读代码的人无法判断到底发生的是哪种初始化。`constinit` 只要求变量是常量初始化的（[[dcl.constinit]]），并不使变量成为 `const`：

```cpp run std=c++20 ok
consteval int sq(int x) { return x * x; }
constinit int counter = sq(3);    // 保证静态初始化
int next() { return ++counter; }  // counter 不是 const，可以修改
int main() { return next() == 10 ? 0 : 1; }
```

### is_constant_evaluated：一个函数，两种实现

库作者常常希望同一个函数在编译期用一种可常量求值的写法，在运行期用更快的写法（内联汇编、SIMD 内建函数、`memcpy`）。Daveed Vandevoorde 的 [[P0595R0]] 最初提议的是一个 `constexpr` 运算符；到 R1 改成了库函数 `std::is_constant_evaluated()`，[[P0595R2]] 于 2018 年 11 月通过（[[meta.const.eval]]）。

HOPL IV 说它让库实现者可以少用平台相关的编译器内建函数。但这个设计有一个出名的陷阱：如果把它放在 `if constexpr` 的条件里，条件本身就是在常量求值中计算的，结果永远是 `true`。

```cpp run std=c++20
#include <type_traits>
constexpr int f(int x) {
    if constexpr (std::is_constant_evaluated())   // 恒为 true：运行期调用也走这个分支
        return x;
    else
        return -x;
}
int main() { return f(1) == 1 ? 0 : 1; }
```

Clang 对此给出警告 `'std::is_constant_evaluated' will always evaluate to 'true' in a manifestly constant-evaluated expression`。C++23 的 `if consteval` 就是为了解决这个问题以及下面要讲的另一个问题。

## 六、C++23：补洞

C++23 在常量求值方面没有大的新能力，主要是修补 C++20 留下的不一致。

### if consteval

[[P1938R3]]（Revzin、Vandevoorde、Smith、Sutton）2021 年 6 月通过（`__cpp_if_consteval` 为 `202106L`）。它解决 `is_constant_evaluated()` 的两个问题。第一个是上面那个 `if constexpr` 陷阱：`if consteval` 不需要条件表达式，也就不可能写错。第二个问题更根本：在 `if (std::is_constant_evaluated())` 的分支里，仍然不能用函数参数去调用 `consteval` 函数，因为这个分支并不是立即函数语境。

```cpp run std=c++20 error
#include <type_traits>
consteval int sq(int x) { return x * x; }
constexpr int g(int x) {
    if (std::is_constant_evaluated()) return sq(x);   // error: x 不是常量表达式
    return x * x;
}
int main() {}
```

`if consteval` 的第一个分支是立即函数语境（[[stmt.if#4]]），在里面可以把参数传给 `consteval` 函数：

```cpp run std=c++23 ok
consteval int sq(int x) { return x * x; }
constexpr int g(int x) {
    if consteval { return sq(x); }   // 立即函数语境
    else { return x * x; }
}
static_assert(g(3) == 9);
int main(int argc, char**) { return g(argc) == 1 ? 0 : 1; }
```

### 不求值的部分不再受限

C++20 的规则对 `constexpr` 函数的函数体做语法上的检查：只要函数体里出现了某些东西（非字面类型的变量、`static` 变量、`goto`、标号），整个函数就不能是 `constexpr` 的，哪怕这些代码只在运行期的分支里。

Ville Voutilainen 的 [[P2242R3]] 把这类检查改成了求值时的检查：只要常量求值没有走到这些代码，它们就可以出现（`__cpp_constexpr` 为 `202110L`）。随后 Revzin 与 Wakely 的 [[P2647R1]] 进一步允许在常量求值中使用 `static constexpr` 局部变量（`202211L`）。

```cpp run std=c++23 ok
constexpr int h(int x) {
    if (x < 0) {
        static int calls = 0;  // C++20：error；C++23：只要常量求值不走到这里就行
        ++calls;
    }
    return x;
}
static_assert(h(1) == 1);
int main() { return h(-1) == -1 ? 0 : 1; }
```

### 不再要求至少有一组实参能常量求值

C++11 起，标准一直有一条规则：如果一个 `constexpr` 函数对任何实参都不可能产生常量表达式，程序是非良构的，不要求诊断（IFNDR）。Barry Revzin 的 [[P2448R2]] 主张删除这条规则，并删除对参数和返回类型必须是字面类型的要求（2022 年 7 月通过，`202207L`）。他的论点是：这条规则惩罚的是将来可能变得合法的代码。一个 `constexpr` 函数今天调用了某个非 `constexpr` 的库函数，明天那个库函数可能就变成 `constexpr` 了；为了不触发 IFNDR，作者不得不写条件宏或者干脆等待。提案的原话是：

> "The goal of this paper is to stop diagnosing problems that don't exist." （Revzin，[[P2448R2]]）

```cpp run std=c++23 ok
int g();                            // 不是 constexpr
constexpr int f() { return g(); }   // C++20：IFNDR（Clang 报错）；C++23：良构
int g() { return 0; }
int main() { return f(); }
```

在 `-std=c++20` 下 Clang 把它当错误处理（`constexpr function never produces a constant expression`，属于 `-Winvalid-constexpr` 组，默认是错误）；在 `-std=c++23` 下没有诊断。从此 `constexpr` 修饰函数时的含义更明确了：它表示这个函数可以在常量求值中调用，而不保证任何一次调用都能常量求值。

### 库：cmath、optional、unique_ptr

C++23 的库方面，Edward Rosten 与 Oliver Rosten 的 [[P0533R9]] 让 `<cmath>` 中一部分函数成为 `constexpr`。浮点数学函数是 `constexpr` 化最慢的部分之一：这些函数可能设置 `errno`，结果还受浮点环境（如舍入模式）影响，而常量求值不能读写这类全局状态。此外还有 `optional` 和 `variant` 的补充（[[P2231R1]]）、`unique_ptr`（[[P2273R3]]）等。

## 七、C++26：类型擦除、placement new、异常，以及反射

### 从 void* 转回来：类型擦除

`std::any`、`std::function` 这类类型擦除的实现，核心操作是把对象地址存成 `void*`，用的时候再 `static_cast` 回原来的类型。C++23 之前的常量求值禁止从 `void*` 转换，所以这类工具都不能在编译期使用。Corentin Jabot 与 David Ledger 的 [[P2738R1]] *constexpr cast from void\*: towards constexpr type-erasure* 在 2023 年 6 月 Varna 会议（C++26 的第一次会议）上通过（`__cpp_constexpr` 为 `202306L`）。规则是：如果 `void*` 实际指向的对象类型与目标类型相符，转换在常量求值中就是允许的；不符则不是常量表达式。

### placement new

C++20 的 [[P0784R7]] 允许了 `std::construct_at`，但没有允许直接写 placement new。Revzin 的 [[P2747R2]] 补上了这一点，2024 年 6 月（St. Louis 会议）通过（`__cpp_constexpr` 为 `202406L`）。

```cpp run std=c++2c ok
#include <memory>
#include <new>
constexpr int via_void_ptr() {
    int x = 42;
    void* p = &x;
    return *static_cast<int*>(p);          // C++26：P2738
}
static_assert(via_void_ptr() == 42);

constexpr int placement() {
    std::allocator<int> a;
    int* p = a.allocate(1);
    ::new (static_cast<void*>(p)) int(7);  // C++26：P2747
    int r = *p;
    std::destroy_at(p);
    a.deallocate(p, 1);
    return r;
}
static_assert(placement() == 7);
int main() {}
```

在 `-std=c++23` 下 Clang 报 `cast from 'void *' is not allowed in a constant expression in C++ standards before C++2c`。

### 编译期异常

C++20 允许 `constexpr` 函数里有 `try` 块，但常量求值一旦走到 `throw` 就失败。Hana Dusíková 的 [[P3068R6]] *Allowing exception throwing in constant-evaluation* 在 2024 年 11 月 Wrocław 会议上通过：异常可以在常量求值内部抛出，只要在同一次求值中被捕获（核心语言的特性测试宏 `__cpp_constexpr_exceptions` 为 `202411L`）。配套的 [[P3378R2]] 让标准异常类型可以在常量求值中构造，2025 年 2 月 Hagenberg 会议通过。

这一步的意义不只在于让已有代码可以常量求值。C++26 的反射库用异常报告错误（[[P3560R2]] *Error Handling in Reflection*），这依赖 P3068 先落地。

```cpp run std=c++2c
#include <stdexcept>
constexpr int checked_div(int a, int b) {
    if (b == 0) throw std::domain_error("division by zero");
    return a / b;
}
constexpr int safe(int a, int b) {
    try { return checked_div(a, b); }
    catch (const std::domain_error&) { return 0; }
}
static_assert(safe(6, 3) == 2);
static_assert(safe(1, 0) == 0);   // C++26 起 OK：异常在常量求值内部抛出并被捕获
int main() {}
```

按标准这段代码在 C++26 下是良构的。截至写作时，本机 Clang 23 尚未实现 P3068：它没有定义 `__cpp_constexpr_exceptions`，对第二个 `static_assert` 报 `subexpression not valid in a constant expression`。

### 其他放宽

C++26 中与常量求值相关的其他提案还有：

- [[P2686R5]]（Jabot、Bi）：结构化绑定可以声明为 `constexpr`，2024 年 11 月通过；
- [[P3533R2]]（Dusíková）：常量求值中允许虚继承，2025 年 6 月 Sofia 会议通过（`__cpp_constexpr_virtual_inheritance` 为 `202506L`）；
- 库方面：`<cmath>` 和 `<complex>` 的进一步 `constexpr` 化（[[P1383R2]]）、稳定排序（[[P2562R1]]）、`atomic`（[[P3309R3]]）、其余标准容器与容器适配器（[[P3372R3]]）、`shared_ptr`（[[P3037R6]]）等。

```cpp run std=c++2c ok
struct P { int x, y; };
constexpr P pt{1, 2};
constexpr auto [a, b] = pt;   // C++23：error；C++26：OK（P2686）
static_assert(a + b == 3);
int main() {}
```

到 C++26 为止，常量求值仍然禁止的主要是：`reinterpret_cast`、读取运行期才有值的对象、不匹配的分配与释放、未定义行为（见第八节），以及调用非 `constexpr` 函数（完整清单见 [[expr.const.core]]）。

### 反射：consteval 编程

2025 年 6 月 Sofia 会议通过了 [[P2996R13]] *Reflection for C++26* 及配套的六篇提案，包括注解（[[P3394R4]]）、expansion statement（`template for`，[[P1306R5]]）、`define_static_{string,object,array}`（[[P3491R3]]）等（据 Sutter 的 Sofia 会议报告）。C++26 还加入了可以在命名空间和类作用域执行编译期代码的 `consteval` 块（[[P3289R1]]）。

从 `constexpr` 的历史看，反射是这条线的延续。P1073 当年把 `consteval` 的主要动机归为反射；P0784 的动态分配让 `std::vector<std::meta::info>` 这样的返回值成为可能；P3068 的异常为反射提供了错误处理机制。反射的查询结果是 `std::meta::info` 类型的值，所有查询函数都是 `consteval` 的，元编程从此可以用普通函数、循环和容器来写，而不必再借助模板特化。

```cpp
#include <meta>
struct S { int a; double b; };
constexpr auto ctx = std::meta::access_context::unchecked();
static_assert(std::meta::nonstatic_data_members_of(^^S, ctx).size() == 2);
```

这段代码按 C++26 是良构的。本机的 Clang 23 发行版没有提供 `<meta>` 头文件，未能验证；规则见 [[expr.const.reflect]]。

## 八、常量求值作为 UB 检测器

从 N2235 开始，常量表达式就不允许包含未定义行为。随着常量求值能执行的代码越来越多，这条规则的分量也越来越重。

当前草案在 [[expr.const.core#2]] 的列表里写明：求值中执行了 [intro] 到 [cpp] 各章（即核心语言部分）规定为未定义行为或错误行为（erroneous behavior）的操作，表达式就不是核心常量表达式（¶2.8）。对标准库部分规定的未定义行为，¶4 只说"是否为核心常量表达式是未指定的"，因为要求编译器检查所有库前置条件不现实。C++23 之后的新措辞还引入了 runtime-undefined behavior 这一术语（[[intro.defs]]），用于 `[[assume]]` 这类只在运行期才算未定义的情况，常量求值时是否把它们判为非常量由实现定义（¶3）。

```cpp run std=c++2c error
#include <climits>
constexpr int add(int a, int b) { return a + b; }
constexpr int x = add(INT_MAX, 1);      // error: 有符号溢出是 UB
constexpr int arr[3] = {1, 2, 3};
constexpr int y = arr[3];               // error: 越界读取
int main() {}
```

Clang 对这两处分别报告 `value 2147483648 is outside the range of representable values of type 'int'` 和 `read of dereferenced one-past-the-end pointer is not allowed in a constant expression`。运行期的同样代码不会得到任何诊断。

这产生了一种常见的用法：在 `static_assert` 里调用待测函数，让编译器充当一个只覆盖实际求值路径的 UB 检查器（更多讨论见 [[topics/compile-time-programming]] 和 [[topics/undefined-behavior]]）。需要注意它的局限：只检查这一次求值实际走过的路径；只覆盖核心语言的 UB；编译器对 UB 的检测是否完整，取决于实现。

这种需求反过来也推动了标准本身的精确化。Stroustrup 在 HOPL IV §9.3.3 写道，要让一个语言构造或库组件成为 `constexpr`，它必须被非常精确地规定，并且 "stripped of the possibility of undefined behavior"；因此编译期求值的推进成为更精确规范、分析平台依赖和考察 UB 根源的一大动力。后来的工作沿着这个方向走得更远：Sutter 在 2024 年 Wrocław 会议报告中介绍的 [[P3436R1]] 提出默认消除与安全相关的 UB，明确以常量求值已经禁止 UB 为出发点（该提案未被采纳为标准文本）；2026 年 6 月 Brno 会议把 [[P3596R3]] 并入 C++29 草案，以附录形式列出标准中所有 UB 与 IFNDR 的情形。

## 九、争论：要不要 constexpr 一切

每一次放宽都伴随着同一个问题：既然越来越多的函数都能常量求值，为什么还要手工标 `constexpr`？

### 主张：隐式 constexpr

Bryce Adelstein Lelbach 与 Hana Dusíková 在 2018 年提交了 [[P1235R0]] *Implicit constexpr*。理由有三点：`constexpr` 限制一再放宽，不能标 `constexpr` 的函数越来越少；需要在常量表达式中使用的函数越来越多，手工标注在标准库和第三方库中都成了负担；C++17 已经让 lambda 隐式 `constexpr`，函数和 lambda 之间出现了人为的不一致。

提案的设计是：在常量表达式中调用一个没有标 `constexpr`、但定义在当前翻译单元中的函数时，把它当作 `constexpr` 函数处理。提案同时承认需要一个退出机制，建议用 `constexpr(false)` 让库作者阻止用户依赖某个函数可常量求值，`constexpr(true)` 则表示只能在常量表达式中调用。这一提案没有进入标准。

GCC 提供了一个实验性的 `-fimplicit-constexpr` 选项，把 `inline` 函数当作 `constexpr` 处理；据 GCC 的提交说明，它由 Jason Merrill 加入，目的是不必到处添加关键字。本机 Clang 23 不支持这个选项。

### 反对与保留

反对把 `constexpr` 变成默认，主要有三类理由，大多数在上述文献中已经出现：

- **接口承诺**。一个函数能被常量求值，就成了它对外接口的一部分。如果默认可常量求值，用户就可能依赖这一点，库作者以后改用不可常量求值的实现（P1235 自己举的例子是改用 SIMD 内建函数）就会破坏用户代码。P1235 用 `constexpr(false)` 回应这个问题，代价是退出需要显式标注。
- **实现与编译时间**。HOPL IV 解释最初为何要求显式标记时提到，否则编译器要把所有函数体一直保留以备常量求值。§9.3.3 又说编译期计算给编译器带来更多工作，C++ 程序员必须学会只在紧凑性和运行期性能值得的地方使用编译期计算和元编程。
- **范围是否该有边界**。HOPL IV §9.3.3 承认有人希望所有 C++ 构造都能在编译期使用，包括整个标准库。Stroustrup 的回应是 "That may be too much of a good thing"，并举例：编译期真的需要线程吗？他同时指出，不让所有函数都可编译期使用，就要决定哪些可以、哪些不可以，而目前的答案 "a bit ad hoc and not coherent"。

P2448 走的是一条中间路线：保留 `constexpr` 关键字，但把它的含义弱化为允许在常量求值中调用，不再要求作者证明它真的能常量求值。这样库作者可以先标上 `constexpr`，等依赖的东西也变成 `constexpr` 之后自然生效。

## 时间线

| 年份 | 标准 | 事件 | 文献 |
|---|---|---|---|
| 1998 | C++98 | 只有整型常量表达式，不能调用函数；模板元编程成为编译期计算的主要手段 | HOPL IV §9.3.3 |
| 2003 | | Dos Reis 提出广义常量表达式（无关键字）；同年 10 月 Kona 会议 EWG 要求加语法标记 | [[N1521]]，[[N2235]] §4.5 |
| 2007 | C++0x | 第 5 版提案并入工作草案：单条 `return`、字面类型、`constexpr` 构造函数 | [[N2235]] |
| 2011 | C++11 | `constexpr` 正式进入标准；`numeric_limits` 等成为 `constexpr` | [[N2219]] |
| 2013 | C++14 | 允许局部变量、循环、修改局部对象、`void` 返回；成员函数不再隐式 `const` | [[N3652]] |
| 2016 | C++17 | lambda 隐式 `constexpr`；`if constexpr` | [[P0170R1]]，[[P0292R2]] |
| 2018 | C++20 | `consteval`、`is_constant_evaluated`、虚函数调用、`try` 块、`dynamic_cast` | [[P1073R3]]，[[P0595R2]]，[[P1064R0]]，[[P1002R1]]，[[P1327R1]] |
| 2019 | C++20 | 瞬时动态分配与 `constexpr` 析构；`vector`/`string`；`constinit` | [[P0784R7]]，[[P1004R2]]，[[P0980R1]]，[[P1143R2]] |
| 2021 | C++23 | `if consteval`；不求值部分可含非字面类型变量、`goto` | [[P1938R3]]，[[P2242R3]] |
| 2022 | C++23 | 删除要求至少一组实参可常量求值的 IFNDR 规则；`consteval` 向上传播 | [[P2448R2]]，[[P2564R3]] |
| 2023 | C++26 | 从 `void*` 转换（Varna） | [[P2738R1]] |
| 2024 | C++26 | placement new（St. Louis）；编译期异常、`constexpr` 结构化绑定（Wrocław） | [[P2747R2]]，[[P3068R6]]，[[P2686R5]] |
| 2025 | C++26 | 标准异常类型、容器（Hagenberg）；虚继承、静态反射（Sofia） | [[P3378R2]]，[[P3372R3]]，[[P3533R2]]，[[P2996R13]] |
| 2026 | C++29 草案 | UB 与 IFNDR 附录（Brno）；`constexpr` 协程等仍在修订 | [[P3596R3]]，[[P3367]] |

## 现状与未来

截至 2026 年 10 月，C++26 的技术工作已在 2026 年 3 月 London Croydon 会议上完成（据 Sutter 的会议报告），常量求值的能力定格在上面第七节描述的状态。几个还在进行中的方向：

- constexpr 协程：Dusíková 的 [[P3367]] 截至 2026 年 7 月已修订到 R5，尚未并入草案。
- 非瞬时分配：让编译期分配的内存留到运行期（如 [[P3032R2]]），涉及对象在两个世界之间如何迁移的根本问题，目前 C++26 用 `define_static_array` 一类显式复制的办法绕过。
- 更多库函数：每次会议几乎都有新的 `constexpr` 库提案，例如 2026 年 6 月 Brno 会议并入 C++29 草案的 constexpr pointer tagging（[[P3125R6]]）。
- UB 的系统梳理：[[P3596R3]] 的 UB 附录与 [[P3100R8]] 提出的框架，会影响哪些操作在常量求值中被拒绝。

回头看，`constexpr` 的十五年基本是同一个模式反复出现：先用最保守的规则让特性进入标准，等实现经验积累、用户需求明确，再逐条放宽。C++11 的单条 `return` 规则在当时是为了让提案能通过，现在看来是一个过渡阶段。哪些东西永远不该进入常量求值，Stroustrup 在 HOPL IV 中说目前的划分还不够系统，这个问题至今没有定论。

## 参考资料

- Gabriel Dos Reis, Bjarne Stroustrup, Jens Maurer. *Generalized Constant Expressions — Revision 5*. [[N2235]], 2007.
- Gabriel Dos Reis. *Generalized Constant Expressions*. [[N1521]], 2003.
- Gabriel Dos Reis, Bjarne Stroustrup. *General Constant Expressions for System Programming Languages*. SAC '10, 2010.
- Bjarne Stroustrup. *Thriving in a Crowded and Changing World: C++ 2006–2020*. HOPL IV, Proc. ACM Program. Lang. 4 (HOPL), 2020. §4.2.7、§5.5、§9.3.3。
- Richard Smith. *Relaxing constraints on constexpr functions / constexpr member functions and implicit const*. [[N3652]], 2013.
- Faisal Vali. *Wording for Constexpr Lambda*. [[P0170R1]], 2016.
- Herb Sutter, Walter Bright, Andrei Alexandrescu. *Proposal: static if declaration*. [[N3329]], 2012；Bjarne Stroustrup, Gabriel Dos Reis, Andrew Sutton. *"Static If" Considered*. [[N3613]], 2013.
- Ville Voutilainen. *constexpr_if*. [[P0128R1]]；Jens Maurer. *constexpr if: A slightly different syntax*. [[P0292R2]], 2016.
- Peter Dimov, Louis Dionne, Nina Ranns, Richard Smith, Daveed Vandevoorde. *More constexpr containers*. [[P0784R7]], 2019.
- Richard Smith, Andrew Sutton, Daveed Vandevoorde. *Immediate functions*. [[P1073R3]], 2018；*std::is_constant_evaluated*. [[P0595R2]], 2018.
- Eric Fiselier. *Adding the constinit keyword*. [[P1143R2]], 2019.
- Barry Revzin, Daveed Vandevoorde, Richard Smith, Andrew Sutton. *if consteval*. [[P1938R3]], 2021.
- Ville Voutilainen. *Non-literal variables (and labels and gotos) in constexpr functions*. [[P2242R3]], 2021.
- Barry Revzin. *Relaxing some constexpr restrictions*. [[P2448R2]], 2022.
- Corentin Jabot, David Ledger. *constexpr cast from void\*: towards constexpr type-erasure*. [[P2738R1]], 2023.
- Barry Revzin. *constexpr placement new*. [[P2747R2]], 2024.
- Hana Dusíková. *Allowing exception throwing in constant-evaluation*. [[P3068R6]], 2024.
- Bryce Adelstein Lelbach, Hana Dusíková. *Implicit constexpr*. [[P1235R0]], 2018.
- Herb Sutter 的会议报告（Sutter's Mill）：Varna 2023 年 6 月、St. Louis 2024 年 7 月发布、Wrocław 2024 年 11 月、Hagenberg 2025 年 2 月、Sofia 2025 年 6 月、London Croydon 2026 年 3 月、Brno 2026 年 6 月。
- GCC 提交记录与 Bugzilla #110127（`-fimplicit-constexpr`）。
