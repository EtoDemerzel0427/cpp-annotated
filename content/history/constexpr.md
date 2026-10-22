---
title: constexpr：编译期计算的十五年扩张
summary: 从 C++98 的整型常量表达式和模板元编程，到 C++11 只能写一条 return 的 constexpr 函数，再到 C++20 的编译期 vector、consteval、constinit 和 C++26 的编译期异常：每一步放宽了什么，为什么放宽，哪些边界始终没动。
status: draft
since: c++11
order: 55
papers: N2235, N3652, P0170R1, P0292R2, P0784R7, P1073R3, P1143R2, P0595R2, P1938R3, P2242R3, P2448R2, P2738R1, P2747R2, P3068R6, P1235R0
related: expr.const, expr.const.core, history/template-metaprogramming, expr.const.imm, dcl.constexpr, dcl.constinit, stmt.if, meta.const.eval, topics/compile-time-programming, topics/undefined-behavior
tags: 沿革, constexpr, consteval, constinit, 常量求值
updated: 2026-10-19
---

!!! tldr
    - C++98 在编译期只能算整型常量表达式，不能调用函数；更复杂的计算只能写成模板元编程。
    - C++11 的 `constexpr` 用关键字显式标出可在编译期调用的函数，规则保守到只允许一条 `return`。此后每一版都在放宽：C++14 允许局部变量和循环，C++20 允许虚调用和动态分配，C++26 允许抛出并捕获异常。
    - 有一条边界始终没动：常量求值的全部效果必须在求值结束前收拢。所以编译期 `new` 出来的内存必须在同一次求值中释放，`constexpr std::vector` 变量至今写不出来。
    - 常量求值从一开始就不允许未定义行为，这让 `static_assert` 成了一个只覆盖实际执行路径的 UB 检测器。
    - `consteval`、`constinit`、`if consteval` 分别回答了三个 `constexpr` 本身答不了的问题：只能在编译期调用、必须静态初始化、在函数内区分编译期和运行期。

规则本身见 [[expr.const]]、[[expr.const.core]] 和 [[dcl.constexpr]]，各工具的分工与用法见 [[topics/compile-time-programming]]。本页引用的 HOPL IV 指 Stroustrup 的 *Thriving in a Crowded and Changing World: C++ 2006–2020*（2020），是当事人一方的回顾。

## 一、C++98：编译期能算什么

### 只有整型常量表达式

C++98 从 C 继承了常量表达式，而且只有整型的版本。数组边界、`case` 标签、枚举值、非类型模板实参都要求**整型常量表达式**：字面量、枚举值、用常量初始化的 `const` 整型变量、`sizeof`，以及它们之间的内置运算。函数调用一律不行。

Dos Reis 与 Stroustrup 在 [[N2235]] §3.1 举的第一个例子是 `std::numeric_limits<int>::max()`。它在功能上等价于宏 `INT_MAX`，却因为是函数调用而不能用在数组边界里，程序员只能退回去用宏。

同一篇提案的 §3.4 还指出，看起来是常量的变量可能悄悄走了动态初始化，而且没有任何手段能要求它必须在编译期初始化。这个问题等到 C++20 的 `constinit` 才有答案：

<div class="compare" markdown="1">

```cpp run std=c++98 ok
#include <limits>
struct S { static const int size; };
const int limit = 2 * S::size;
// S::size 的定义在后面，limit 走了
// 动态初始化，编译器不会提示
const int S::size = 256;
const int z =
  std::numeric_limits<int>::max();
// 函数调用：也是动态初始化
int main() {}
```

```cpp run std=c++20 error
struct S { static const int size; };
constinit const int limit = 2 * S::size;
// error: 不是常量初始化。constinit
// 把隐患变成了编译错误
const int S::size = 256;
int main() {}
```

</div>

### 模板元编程

另一条路是让模板实例化替你计算：递归的类模板加一个终止特化，结果放在枚举成员里。

```cpp run std=c++98 ok
template <unsigned N> struct Factorial {
  enum { value = N * Factorial<N - 1>::value };
};
template <> struct Factorial<0> {
  enum { value = 1 };
};

// C++98 版的 static_assert：条件为假时数组长度为 -1
typedef char check[Factorial<5>::value == 120 ? 1 : -1];
int main() {}
```

这能工作，但代价明显：分支要靠特化，循环要靠递归实例化，只能算整数和类型，出错时得到一长串实例化栈，每一步计算都在编译器里留下一个类模板实例（详见 [[history/template-metaprogramming]]）。HOPL IV §4.2.7 的评价是 "tedious and error-prone"。

## 二、C++11：为什么要关键字，为什么只有一条 return

### 一个显式的标记

2003 年，Gabriel Dos Reis 提出了广义常量表达式（[[N1521]]）：允许足够简单的函数和足够简单的用户定义类型出现在常量表达式中。后一种类型后来叫[[g:literal-type|字面类型]]。目标包括让编译期计算类型安全、把数据放进 ROM、让编译期编程和普通编程尽量相似（HOPL IV §4.2.7）。

最初的方案没有关键字，打算由编译器自己判断哪些函数足够简单。委员会要求加一个语法标记（[[N2235]] §4.5），于是有了 `constexpr`。HOPL IV 给了两个理由：

- 如果不标记，一个函数能否用在常量表达式中就取决于各家编译器有多聪明，代码没有可移植性；
- 编译器为了应付随时可能的常量求值，得把所有函数体一直保留着。

第一个理由说明了 `constexpr` 的本质：它是函数接口的一部分，是作者对调用者的承诺。这一点在后来要不要让所有函数默认 `constexpr` 的争论中（第九节）还会出现。

### 保守的起点

2007 年并入 C++0x 的 [[N2235]] 规定，`constexpr` 函数的函数体只能是一条 `return expr;`，提案自己说这只是给"带参数的具名常量表达式"换一种写法。同时引入的还有 `constexpr` 构造函数和浮点常量表达式。

N2235 原本还禁止递归，理由是在看到有说服力的用例之前不打算允许。这一条没留到最后：C++11 允许递归的 `constexpr` 函数，实现可以限制递归深度（[[implimits]]）。于是 C++11 的 `constexpr` 函数普遍写成条件运算符加递归：

<div class="compare" markdown="1">

```cpp run std=c++11 ok
constexpr unsigned long long
fact(unsigned n) {
  return n <= 1 ? 1 : n * fact(n - 1);
}
static_assert(fact(5) == 120, "");
int main() {}
```

```cpp run std=c++14 ok
constexpr unsigned long long
fact(unsigned n) {
  unsigned long long r = 1;  // C++11 不行
  for (unsigned i = 2; i <= n; ++i)
    r *= i;                  // C++11 不行
  return r;
}
static_assert(fact(5) == 120, "");
int main() {}
```

</div>

右边在 C++11 下是非良构的。本机 Clang 23 在 `-std=c++11` 下对局部变量只给出扩展警告，对 `for` 语句报错。

据 Stroustrup 回忆，这个提案曾被反复认为既没用又无法实现，直到各主要编译器实现了它；初版花了四年才通过（HOPL IV §4.2.7）。与之配套，C++11 让 `numeric_limits` 的成员函数成为 `constexpr`，N2235 开头的那个尴尬就此消除。

## 三、C++14：允许局部变量和循环

C++11 发布后，用户很快开始要求放宽。Richard Smith 的 [[N3652]] 在 2013 年通过，允许函数体里有局部变量、`if`/`switch` 和循环，返回类型可以是 `void`，也可以修改生命期在本次常量求值中开始的对象。

它的标题后半部分是 *constexpr member functions and implicit const*。C++11 的 `constexpr` 非静态成员函数自动是 `const` 的，这和允许修改对象的新规则冲突，所以 C++14 去掉了隐式 `const`。这是 `constexpr` 历史上少有的不兼容修改：依赖隐式 `const` 的 C++11 代码要显式补上 `const`。

```cpp run std=c++14 ok
struct Point {
    int x, y;
    constexpr Point(int x, int y) : x(x), y(y) {}
    constexpr void move(int dx) { x += dx; }   // C++11：隐式 const，不能赋值；也不能返回 void
};
constexpr Point shifted() {
    Point p{1, 2};       // 局部变量
    p.move(3);           // 修改本次求值中创建的对象
    return p;
}
static_assert(shifted().x == 4, "");
int main() {}
```

在 `-std=c++11` 下，Clang 对 `move` 报两个错误（给 `const` 成员函数里的成员赋值、返回类型 `void` 不是字面类型），并警告它在 C++14 中不再隐式 `const`。

HOPL IV 特别指出，这些局部变量只存在于编译器里，求值不能对调用者的环境产生副作用。这条边界决定了之后所有的放宽：常量求值能做的事越来越多，但它的一切效果都必须在求值结束前收拢。

## 四、C++17：lambda 与 if constexpr

### lambda 默认可以常量求值

[[P0170R1]] 规定，lambda 的函数调用运算符只要满足 `constexpr` 函数的要求，就隐式是 `constexpr` 的。这是 `constexpr` 第一次不需要写出来。

```cpp run std=c++17 ok
auto square = [](int x) { return x * x; };   // 没写 constexpr
static_assert(square(7) == 49);              // C++14 下不是常量表达式
int main() {}
```

### if constexpr：被缩小的 static if

2012 年有人提出借鉴 D 语言的 `static if`（[[N3329]]）：它可以出现在命名空间和类作用域，不引入新作用域，未选中的分支连语法分析都不做。Stroustrup、Dos Reis 与 Sutton 的 [[N3613]] 系统地反对它：同一个语法在不同语境下有三种语义；不做语法分析的分支让程序难以阅读、调试，也妨碍基于语法树的工具；其中约束模板的那部分需求应该交给概念。

几年后这一想法以小得多的范围回来，成了 C++17 的 `if constexpr`（[[P0292R2]]）：只是一条语句，只能出现在函数体内，有自己的作用域，未选中的分支仍要做语法分析。今天它的规则里仍能看到这些限制：未选中的分支叫**丢弃语句**（discarded statement），在模板中不实例化，但它必须是语法正确的代码（[[stmt.if#2]]）。

<div class="compare" markdown="1">

```cpp run std=c++17 error
#include <string>
#include <type_traits>
template <class T>
std::string describe(T v) {
  if (std::is_integral_v<T>)
    return "int:" + std::to_string(v);
  else return "other";
}
int main() { describe("x"); }
// error: 两个分支都要实例化，
// 没有 to_string(const char*)
```

```cpp run std=c++17 ok
#include <string>
#include <type_traits>
template <class T>
std::string describe(T v) {
  if constexpr (std::is_integral_v<T>)
    return "int:" + std::to_string(v);
  else return "other";
}
int main() { describe("x"); }
// OK：T = const char* 时
// 第一个分支被丢弃，不实例化
```

</div>

`if constexpr` 没有扩大常量求值能做的事，它让模板按编译期条件选择要实例化的代码，取代了大量标签分派和 SFINAE 的写法。

## 五、C++20：编译期的动态分配

### 虚函数、try、union、new

2018–2019 年的一组提案把常量求值中禁止的东西一项项去掉：虚函数调用（[[P1064R0]]）、`try` 块（[[P1002R1]]，但求值走到 `throw` 仍然失败）、`dynamic_cast` 和多态 `typeid`（[[P1327R1]]）、改变 union 的活跃成员（[[P1330R0]]）、不初始化的局部变量（[[P1331R2]]，只要求值时不读它）。

影响最大的是 [[P0784R7]] *More constexpr containers*。它的目标是让 `std::vector` 能在编译期使用，为此需要两件事：析构函数可以是 `constexpr` 的，常量求值中可以 `new`/`delete`。

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

在 `-std=c++17` 下，Clang 报告析构函数和虚函数都不能是 `constexpr`。

### 瞬时分配：内存不能带出编译期

分配遵循[[g:transient-allocation|瞬时分配]]的规则：常量求值中分配的内存必须在同一次求值结束之前释放，否则表达式不是常量表达式（[[expr.const.core]]）。这正是第三节那条边界的延续。Louis Dionne 的 [[P1004R2]] 和 [[P0980R1]] 据此让 `vector` 和 `string` 成为 `constexpr`：

<div class="compare" markdown="1">

```cpp run std=c++20 ok
#include <numeric>
#include <vector>
constexpr int sum_squares(int n) {
  std::vector<int> v;
  for (int i = 1; i <= n; ++i)
    v.push_back(i * i);
  return std::accumulate(
    v.begin(), v.end(), 0);
}  // v 析构，内存在求值内释放
static_assert(sum_squares(4) == 30);
int main() {}
```

```cpp run std=c++20 error
#include <vector>
constexpr std::vector<int> v =
  {1, 2, 3};
// error: 求值结束时内存还没释放
int main() {}
```

</div>

右边 Clang 的说明是 `pointer to subobject of heap-allocated object is not a constant expression`。为什么不让编译期分配的内存留到运行期？那样就要回答编译期的堆对象如何变成程序映像里的静态数据、运行期由谁来释放它，这些问题至今没有被接受的答案（[[P3032R2]] 是一个尝试）。C++26 换了一种办法：用 `std::define_static_array` 等函数（[[P3491R3]]）把编译期得到的数据显式复制成静态存储期的数组。

### consteval：只能在编译期调用

`constexpr` 函数既能在编译期调用，也能在运行期调用。有些函数只应该存在于编译期。[[P1073R3]] 引入了**立即函数**（immediate function），关键字 `consteval`；早期修订版里它叫 `constexpr!`。提案说主要动机来自正在设计的静态反射：反射的查询函数应当只在编译期存在，不生成目标代码。

```cpp run std=c++20 error
consteval int sq(int x) { return x * x; }
constexpr int a = sq(4);          // OK
int runtime_value();
int b = sq(runtime_value());      // error: 立即函数的调用必须是常量表达式
int main() {}
```

这条线延续到了 C++26：`std::meta` 里的反射函数全部是 `consteval` 的。

### constinit：只要求静态初始化

第一节的动态初始化问题由 [[P1143R2]] 回答。它最初提议的是属性 `[[constinit]]`，后来改成关键字，理由是这个特性的目的就是强制检查，而属性可以被编译器忽略。`constinit` 只要求变量是常量初始化的（[[dcl.constinit]]），并不使变量成为 `const`，这是它和 `constexpr` 变量的区别：

```cpp run std=c++20 ok
consteval int sq(int x) { return x * x; }
constinit int counter = sq(3);    // 保证静态初始化
int next() { return ++counter; }  // counter 不是 const，可以修改
int main() { return next() == 10 ? 0 : 1; }
```

### is_constant_evaluated 和它的陷阱

库作者常希望同一个函数在编译期用可常量求值的写法，在运行期用更快的写法（内建函数、SIMD）。[[P0595R2]] 为此提供了 `std::is_constant_evaluated()`（[[meta.const.eval]]）。它有一个出名的陷阱：放在 `if constexpr` 的条件里，条件本身就在常量求值中计算，结果永远是 `true`。

```cpp run std=c++20
#include <type_traits>
constexpr int f(int x) {
    if constexpr (std::is_constant_evaluated())   // 恒为 true
        return x;
    else
        return -x;
}
int main() { return f(1) == 1 ? 0 : 1; }   // 运行期调用也走第一个分支
```

这段代码良构，只是不做程序员想做的事。Clang 警告 `'std::is_constant_evaluated' will always evaluate to 'true' in a manifestly constant-evaluated expression`。

## 六、C++23：修补不一致

### if consteval

`is_constant_evaluated()` 还有第二个问题：即使写对了 `if (std::is_constant_evaluated())`，分支里也不能把函数参数传给 `consteval` 函数，因为编译器不能确定这个分支只在编译期执行。[[P1938R3]] 的 `if consteval` 同时解决了两个问题：它没有条件表达式，不可能写错；它的第一个分支是立即函数语境（[[stmt.if#5]]）。

<div class="compare" markdown="1">

```cpp run std=c++20 error
#include <type_traits>
consteval int sq(int x) { return x * x; }
constexpr int g(int x) {
  if (std::is_constant_evaluated())
    return sq(x);  // error: x 不是常量
  return x * x;
}
int main() {}
```

```cpp run std=c++23 ok
consteval int sq(int x) { return x * x; }
constexpr int g(int x) {
  if consteval { return sq(x); }  // OK
  else { return x * x; }
}
static_assert(g(3) == 9);
int main(int argc, char**) {
  return g(argc) == 1 ? 0 : 1;
}
```

</div>

### 从语法检查改为求值检查

C++20 对 `constexpr` 函数体做语法上的检查：只要出现了非字面类型的变量、`static` 变量、`goto` 或标号，整个函数就不能是 `constexpr`，哪怕这些代码只在运行期分支里。[[P2242R3]] 把它们改成求值时的检查：只要常量求值没有走到这些代码，就可以出现。

```cpp run std=c++23 ok
constexpr int h(int x) {
    if (x < 0) {
        static int calls = 0;  // C++20：非良构；C++23：常量求值不走到这里即可
        return ++calls;
    }
    return x;
}
static_assert(h(1) == 1);
int main() { return h(-1) == 1 ? 0 : 1; }
```

本机 Clang 23 在 `-std=c++20` 下对 `static` 变量只给出扩展警告。

### constexpr 的含义变弱了

C++11 起一直有一条规则：如果一个 `constexpr` 函数对任何实参都不可能产生常量表达式，程序非良构，不要求诊断。Barry Revzin 的 [[P2448R2]] 删掉了它。理由是这条规则惩罚的是将来可能变得合法的代码：一个 `constexpr` 函数今天调用了某个非 `constexpr` 的库函数，明天那个库函数可能就变成 `constexpr` 了。

```cpp run std=c++23 ok
int g();                            // 不是 constexpr
constexpr int f() { return g(); }   // C++20：IFNDR（Clang 报错）；C++23：良构
int g() { return 0; }
int main() { return f(); }
```

在 `-std=c++20` 下 Clang 报 `constexpr function never produces a constant expression`。从此 `constexpr` 修饰函数时只表示这个函数允许在常量求值中调用，不再保证任何一次调用都能常量求值。

## 七、C++26：类型擦除、异常与反射

### 从 void* 转回来，placement new

`std::any`、`std::function` 这类类型擦除工具的核心操作是把地址存成 `void*`，用时再转回原类型。C++23 的常量求值禁止从 `void*` 转换，所以它们都不能在编译期使用。[[P2738R1]] 允许了这种转换，前提是 `void*` 实际指向的对象类型与目标类型相符。C++20 允许了 `std::construct_at`，但没允许直接写 placement new，[[P2747R2]] 补上了这一点。

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

C++20 允许 `try` 块，但求值一走到 `throw` 就失败。Hana Dusíková 的 [[P3068R6]] 允许异常在常量求值内部抛出，只要在同一次求值中被捕获，这又是"效果不能带出求值"那条边界。C++26 的反射库用异常报告错误（[[P3560R2]]），依赖的正是这一步。

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
static_assert(safe(1, 0) == 0);   // C++26：异常在常量求值内部抛出并被捕获
int main() {}
```

按标准这段代码在 C++26 下良构。本机 Clang 23 尚未实现 P3068，对第二个 `static_assert` 报 `subexpression not valid in a constant expression`，所以这里不标判定。

C++26 还允许把结构化绑定声明为 `constexpr`（[[P2686R5]]），允许常量求值中的虚继承（[[P3533R2]]），并让更多标准库组件成为 `constexpr`。

```cpp run std=c++2c ok
struct P { int x, y; };
constexpr P pt{1, 2};
constexpr auto [a, b] = pt;   // C++23：error；C++26：OK
static_assert(a + b == 3);
int main() {}
```

到 C++26 为止，常量求值仍然禁止的主要是：`reinterpret_cast`、读取运行期才有值的对象、调用非 `constexpr` 函数、不匹配的分配与释放，以及核心语言的未定义行为。完整清单见 [[expr.const.core]]。

### 反射：consteval 编程

C++26 的静态反射（[[P2996R13]]）是这条线的延续。`consteval` 当初的主要动机就是反射；P0784 的动态分配让反射函数能返回 `std::vector<std::meta::info>`；P3068 的异常为反射提供了错误处理。元编程从此可以用普通函数、循环和容器来写，不必再借助模板特化。

```cpp
#include <meta>
struct S { int a; double b; };
constexpr auto ctx = std::meta::access_context::unchecked();
static_assert(std::meta::nonstatic_data_members_of(^^S, ctx).size() == 2);
```

这段代码按 C++26 良构。本机 Clang 23 没有提供 `<meta>` 头文件，未能验证，所以不标判定。规则见 [[expr.const.reflect]]。

## 八、常量求值作为 UB 检测器

从 N2235 开始，常量表达式就不允许包含未定义行为。当前草案的 [[expr.const.core#2]] 第 2.8 项写明：求值中执行了核心语言规定为未定义行为或错误行为（erroneous behavior）的操作，表达式就不是核心常量表达式。

```cpp run std=c++2c error
#include <climits>
constexpr int add(int a, int b) { return a + b; }
constexpr int x = add(INT_MAX, 1);      // error: 有符号溢出是 UB
constexpr int arr[3] = {1, 2, 3};
constexpr int y = arr[3];               // error: 越界读取
int main() {}
```

Clang 对两处分别说明 `value 2147483648 is outside the range of representable values of type 'int'` 和 `read of dereferenced one-past-the-end pointer is not allowed in a constant expression`。同样的代码在运行期不会得到任何诊断。

于是有了一种常见用法：在 `static_assert` 里调用待测函数，让编译器检查 UB（见 [[topics/compile-time-programming]] 和 [[topics/undefined-behavior]]）。它有三个局限：

- 只检查这一次求值实际走过的路径；
- 只覆盖核心语言的 UB。标准库的 UB 是否被检出是未指定的（[[expr.const.core#4]]），因为要求编译器检查所有库前置条件不现实；
- `[[assume]]` 这类只在运行期才算未定义的情况（runtime-undefined behavior），常量求值是否拒绝由实现定义（[[expr.const.core#3]]）。

这种需求也反过来推动了标准本身的精确化。Stroustrup 在 HOPL IV §9.3.3 写道，一个构造要成为 `constexpr`，就必须被精确地规定，并且 "stripped of the possibility of undefined behavior"。当前草案新增的附录 [[ub]] 系统列出了核心语言的全部 UB（[[P3596R3]]）。

## 九、要不要 constexpr 一切

既然能常量求值的函数越来越多，为什么还要手工标 `constexpr`？

2018 年的 [[P1235R0]] *Implicit constexpr* 主张：在常量表达式中调用一个没标 `constexpr`、但定义可见的函数时，把它当作 `constexpr` 处理。理由是手工标注在标准库和第三方库中都成了负担，而且 C++17 已经让 lambda 隐式 `constexpr`，函数和 lambda 之间出现了不一致。这个提案没有进入标准。GCC 有一个实验性选项 `-fimplicit-constexpr`，把 `inline` 函数当作 `constexpr` 处理；本机 Clang 23 不支持它。

反对的理由主要有三条：

- **接口承诺**。能被常量求值就成了接口的一部分。默认如此的话，用户会依赖它，库作者以后改用不可常量求值的实现（P1235 自己举的例子是改用 SIMD 内建函数）就会破坏用户代码。P1235 的回应是提供 `constexpr(false)` 让作者退出。
- **编译代价**。这正是当年要求显式标记的第二个理由。HOPL IV §9.3.3 也说，C++ 程序员必须学会只在值得的地方使用编译期计算。
- **边界在哪里**。Stroustrup 承认有人希望所有 C++ 构造都能在编译期使用，他的回应是 "That may be too much of a good thing"，并问编译期真的需要线程吗？同时他也承认，目前哪些可以、哪些不可以的划分 "a bit ad hoc and not coherent"（HOPL IV §9.3.3）。

C++23 的 [[P2448R2]] 走了中间路线：保留关键字，但把它的含义弱化为允许在常量求值中调用。库作者可以先标上 `constexpr`，等依赖的东西也变成 `constexpr` 之后自然生效。

## 时间线

| 标准 | 常量求值新增的能力 | 主要提案 |
|---|---|---|
| C++98 | 只有整型常量表达式；复杂计算靠模板元编程 | |
| C++11 | `constexpr` 函数（单条 `return`）、字面类型、`constexpr` 构造函数 | [[N2235]] |
| C++14 | 局部变量、循环、修改局部对象；成员函数不再隐式 `const` | [[N3652]] |
| C++17 | lambda 隐式 `constexpr`；`if constexpr` | [[P0170R1]]、[[P0292R2]] |
| C++20 | 虚调用、`try` 块、瞬时动态分配、`constexpr` 析构；`vector`/`string`；`consteval`、`constinit`、`is_constant_evaluated` | [[P0784R7]]、[[P1073R3]]、[[P1143R2]]、[[P0595R2]] |
| C++23 | `if consteval`；不求值的部分不受限；删除"至少一组实参可常量求值"的要求 | [[P1938R3]]、[[P2242R3]]、[[P2448R2]] |
| C++26 | 从 `void*` 转换、placement new、编译期异常、`constexpr` 结构化绑定；静态反射 | [[P2738R1]]、[[P2747R2]]、[[P3068R6]]、[[P2996R13]] |

## 还在进行的方向

- constexpr 协程（[[P3367]]），截至 2026 年 10 月尚未并入草案；
- 非瞬时分配，即让编译期分配的内存留到运行期（[[P3032R2]]）；
- 更多库函数的 `constexpr` 化，几乎每次会议都有新的提案；
- UB 的系统梳理：[[ub]] 附录与 [[P3100R8]] 提出的框架，会影响哪些操作在常量求值中被拒绝。

回头看，`constexpr` 的十五年一直是同一个模式：先用最保守的规则进入标准，等实现经验和用户需求积累之后再逐条放宽。不变的是那条边界：常量求值的效果不能带出求值。

## 参考资料

- Bjarne Stroustrup. *Thriving in a Crowded and Changing World: C++ 2006–2020*. HOPL IV, Proc. ACM Program. Lang. 4 (HOPL), 2020. §4.2.7、§5.5、§9.3.3。
- Gabriel Dos Reis, Bjarne Stroustrup, Jens Maurer. *Generalized Constant Expressions — Revision 5*. [[N2235]], 2007.
- Richard Smith. *Relaxing constraints on constexpr functions / constexpr member functions and implicit const*. [[N3652]], 2013.
- Bjarne Stroustrup, Gabriel Dos Reis, Andrew Sutton. *"Static If" Considered*. [[N3613]], 2013.
- Peter Dimov, Louis Dionne, Nina Ranns, Richard Smith, Daveed Vandevoorde. *More constexpr containers*. [[P0784R7]], 2019.
- Richard Smith, Andrew Sutton, Daveed Vandevoorde. *Immediate functions*. [[P1073R3]], 2018.
- Eric Fiselier. *Adding the constinit keyword*. [[P1143R2]], 2019.
- Barry Revzin, Daveed Vandevoorde, Richard Smith, Andrew Sutton. *if consteval*. [[P1938R3]], 2021.
- Barry Revzin. *Relaxing some constexpr restrictions*. [[P2448R2]], 2022.
- Hana Dusíková. *Allowing exception throwing in constant-evaluation*. [[P3068R6]], 2024.
- Bryce Adelstein Lelbach, Hana Dusíková. *Implicit constexpr*. [[P1235R0]], 2018.
