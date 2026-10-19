---
title: 核心常量表达式
summary: 表达式在编译期求值时不能做哪些事：读写运行期的对象、调用非 constexpr 函数、触发未定义行为、类型双关、把分配的内存带出求值等；以及编译器怎样处理值未知的引用和对象。
status: done
papers: P2280R4, P0784R7, P2738R1, P2747R2, P3068, P2242R3, P2647R1, P2448R2, P1330R0, P2795R5
related: expr.const, expr.const.const, expr.const.init, dcl.constexpr, basic.life, intro.execution, topics/compile-time-programming
tags: 常量求值, constexpr, UB
updated: 2026-10-19
---

!!! tldr
    - 核心常量表达式用排除法定义：编译器按抽象机规则求值表达式，只要途中没有做第 2 段列出的 36 类操作，它就是核心常量表达式。
    - 清单只检查实际执行到的操作。写在没执行到的分支里的 `throw`、`goto`、非 constexpr 调用都没有影响。
    - 读写以生命期为界：本次求值中创建的对象可以随意读写；之前就存在的对象只能读，而且只能读可用于常量表达式的那些。constexpr 函数的形参在函数体内不是常量表达式，原因就在这里。
    - 核心语言的未定义行为和错误行为在常量求值中一律不允许，编译器因此能在编译期替你抓住它们；库的未定义行为不保证被发现。
    - 编译期不知道值的引用或对象（C++23 起）可以照常传递、取地址、调用不读成员的函数，只是不能读它的值或依赖它的动态类型。

## 同一个函数，有时是常量，有时不是

```cpp
#include <climits>
constexpr int add(int a, int b) { return a + b; }

constexpr int x = add(1, 2);         // OK
constexpr int y = add(INT_MAX, 1);   // error: 有符号溢出
int n = 1;
constexpr int z = add(n, 1);         // error: 读取了运行期变量 n
```

`add` 声明为 constexpr，只表示它可以在编译期调用。某一次调用能不能在编译期完成，要看那次求值实际做了什么。

¶2 标准用一份清单来回答这个问题。按抽象机（[[intro.execution]]）的规则求值表达式 E，如果途中不会求值清单列出的 36 类操作中的任何一种，E 就是**核心常量表达式**（core constant expression）。

这个定义有三个要点：

- 它只看实际执行的操作，不看代码里写了什么。`constexpr int f(bool b) { return b ? 1 : throw 0; }` 里有 `throw`，但 `f(true)` 不会执行它，所以 `f(true)` 是核心常量表达式。
- E 的求值包括它调用的所有函数。清单作用于整棵调用树，而不只是 E 本身的子表达式。
- 核心常量表达式只约束求值过程。结果还要满足额外的条件（不能带出悬空指针、不确定值等），才是**常量表达式**（constant expression），见 [[expr.const.const]]。数组边界、模板实参、constexpr 变量的初始化器要求的都是后者。

## 读与写：以生命期为界

### 读取（¶2.10）

¶2.10 在标准里，读取一个对象的值叫**左值到右值转换**（[[g:lvalue-to-rvalue-conversion|lvalue-to-rvalue conversion]]，[[conv.lval]]）。常量求值中，只有三种读取是允许的：

1. 读 `std::nullptr_t` 类型的对象（2.10.1）。它只有一个可能的值，读取不需要访问内存，哪怕对象未初始化也没关系。
2. 读一个[[g:usable-in-constant-expressions|可用于常量表达式]]的对象，且不经过 volatile（2.10.2）。这类对象的值在编译期确定，包括 constexpr 变量、用常量初始化的 `const` 整型或枚举变量、字符串字面量、模板参数对象，以及它们的非 mutable 子对象。完整定义见 [[expr.const.init#7]]。
3. 读一个生命期始于 E 的求值之内的字面类型对象，同样不经过 volatile（2.10.3）。也就是本次求值自己创建的局部变量、临时对象和 `new` 出来的对象。

```cpp
const int ci = 5;          // const int，用常量初始化
static_assert(ci == 5);    // OK: 可用于常量表达式

int nc = 5;
static_assert(nc == 5);    // error: nc 不是 const

const double cd = 1.0;
static_assert(cd == 1.0);  // error: 只有整型和枚举享有这条特例

const volatile int vi = 1;
static_assert(vi == 1);    // error: volatile

constexpr int local() {
  int x = 1;               // 生命期始于本次求值
  x += 2;
  return x;
}
static_assert(local() == 3);   // OK

constexpr bool np() {
  decltype(nullptr) p;     // 未初始化
  return p == nullptr;     // OK: 读 nullptr_t 不访问内存
}
static_assert(np());
```

`const int` 不写 constexpr 也能用在常量表达式里，`const double` 却不行，这是 C++98 留下的特例：当时允许用常量初始化的 const 整型变量做数组边界，后来的标准保留了它，但没有推广到其他类型。[[expr.const.init#6]] 把这类变量称为 potentially-constant。想让 `double` 变量可用于常量表达式，要写 `constexpr`。

### 修改与析构（¶2.18–¶2.19）

```cpp
int g = 0;
constexpr int touch() { return ++g; }
constexpr int e1 = touch();      // error: g 不是本次求值创建的

constexpr int k = 1;
constexpr int cheat() { return ++const_cast<int&>(k); }
constexpr int e2 = cheat();      // error: 同上（在运行期这也是 UB）
```

¶2.18 赋值、复合赋值、自增自减只能作用于本次求值中创建的、非 volatile 的字面类型对象。修改外部对象会让编译期求值留下副作用，而编译期的副作用无法带到运行期。

C++11 的常量求值完全不允许修改。C++14 放宽到今天的规则，循环和局部变量才能写进 constexpr 函数。

¶2.19 析构同理：不能在常量求值中调用析构函数或伪析构函数，去结束一个求值之外的对象的生命期。

### 形参为什么不是常量表达式（¶5）

¶5 标准的例子把生命期这条线讲得很清楚：

```cpp
constexpr int f1(int k) {
  constexpr int x = k;     // error: k 的生命期始于 x 的初始化器之外
  return x;
}
constexpr int f2(int k) {
  int x = k;               // OK: 非 constexpr 变量不要求常量初始化器
  return x;
}

constexpr int incr(int& n) { return ++n; }
constexpr int g(int k) {
  constexpr int x = incr(k);   // error: 修改了 k，而 k 不是 incr(k) 创建的
  return x;
}
constexpr int h(int k) {
  int x = incr(k);             // OK
  return x;
}
constexpr int y = h(1);        // OK: y == 2
```

关键是弄清 E 指的是哪个表达式。`f1` 里的 `constexpr int x = k;` 本身就要求一个常量表达式，这里 E 是 `k`，而形参 `k` 不是在求值 `k` 的过程中创建的。所以无论 `f1` 是不是在编译期被调用，这一行都非法。

`y = h(1)` 则不同。这里 E 是 `h(1)`，形参 `k` 是这次求值创建的，`incr` 可以随意修改它。

`static_assert`、数组边界、模板实参也都是独立的常量表达式，所以下面的写法同样非法：

```cpp error
#include <array>
constexpr int size_of(int n) {
  std::array<int, n> a{};    // error: n 不是常量表达式
  return a.size();
}
```

想把一个值作为编译期常量传进函数，要用模板参数。

## 未定义行为一律不允许

### 核心语言的 UB 和错误行为（¶2.8）

!!! std
    an operation that would have undefined or erroneous behavior as specified in Clause [intro] through Clause [cpp];

    一个按第 4 章到第 15 章（核心语言部分）的规定会有未定义行为或错误行为的操作。

```cpp
#include <climits>
constexpr int add(int a, int b) { return a + b; }
constexpr int a1 = add(INT_MAX, 1);   // error: 有符号溢出

constexpr int oob() { int a[3]{}; return a[3]; }
constexpr int a2 = oob();             // error: 越界读

constexpr int a3 = 1 / 0;             // error: 除以零
constexpr int a4 = 1 << 32;           // error: 移位量不小于位宽

constexpr int dangling() {
  int* p;
  { int x = 1; p = &x; }
  return *p;                          // 读生命期已结束的对象
}
constexpr int a5 = dangling();        // error
```

上面五个初始化 Clang 都拒绝。脚注 62 列出的例子是有符号溢出、某些指针算术、除以零和某些移位，实际范围是核心语言中所有的 UB，还包括解引用空指针、违反严格别名等。

标准这样规定有两个理由。第一，常量的值必须确定：如果 UB 也能产生一个值，不同编译器会把不同的值写进程序，`X<INT_MAX + 1>` 这样的类型就没有可移植的含义。第二，编译器本来就在模拟抽象机，知道每个对象的类型、边界和生命期，检查这些错误比运行期容易得多。

C++26 引入了**错误行为**（[[g:erroneous-behavior|erroneous behavior]]，[[P2795R5]]）：读未初始化的自动变量从 UB 变成了错误行为，结果是一个确定的错误值。第 2.8 项把错误行为也列了进去，所以这种读取在常量求值中仍然不允许：

```cpp error
constexpr int uninit() {
  int x;        // C++26: x 具有错误值
  return x;     // 错误行为
}
constexpr int v = uninit();   // error
```

### 联合体、不确定值、未知边界数组（¶2.11、¶2.12、¶2.17）

还有几项列出的也是 UB 的具体情形。

¶2.11 读联合体的非活跃成员不允许。C++20 起，常量求值中可以通过赋值切换活跃成员（[[P1330R0]]）：

```cpp
union U { int i; float f; };
constexpr float pun() { U u{.i = 1}; return u.f; }
constexpr float x = pun();       // error: 读非活跃成员 f

constexpr int sw() {
  U u{.i = 1};
  u.f = 2.0f;                    // 活跃成员切换为 f
  return (int)u.f;
}
static_assert(sw() == 2);        // OK
```

¶2.12 读具有[[g:indeterminate-value|不确定值]]的对象不允许。C++26 中多数未初始化的自动变量具有错误值，由第 2.8 项处理；不确定值仍然存在，例如标了 `[[indeterminate]]` 的变量和刚分配、未初始化的动态对象。

¶2.17 指针的一侧指向未知边界数组的首元素、另一侧是非零整数时，指针算术不允许。编译器不知道数组有多长，无法判断是否越界；加零总是安全的。

```cpp
extern int ea[];                 // 未知边界
constexpr int* p0 = ea + 0;      // OK
constexpr int* p1 = ea + 1;      // error
```

### 浮点运算（¶2.9）

¶2.9 IEEE 754 规定 `1.0 / 0.0` 得到无穷大，但标准把结果不在可表示范围内、或数学上无定义的运算算作 UB（[[expr.pre#4]]）。第 2.9 项精确地划了线，以下三种算术运算不允许：

- 操作数都是有限值，结果却不是（溢出到无穷、`1.0 / 0.0`、`0.0 / 0.0`）；
- 有操作数是 signaling NaN；
- 没有操作数是 NaN，结果却是 NaN。

换句话说，已有的无穷大和 quiet NaN 可以继续参与运算，但常量求值中不能产生新的。

```cpp
#include <limits>
using L = std::numeric_limits<double>;
constexpr double d1 = L::infinity() * 2;   // OK: 操作数已经是无穷大
constexpr double d2 = 1.0 / 0.0;           // error
constexpr double d3 = 0.0 / 0.0;           // error
constexpr double d4 = L::max() * 2;        // 按标准是 error
```

!!! impl "Clang 的偏差"
    Clang 23 拒绝 `d2` 和 `d3`（报告除以零），却接受 `d4`。有限值相乘溢出为无穷大，按第 2.9.1 项不是常量，这是 Clang 尚未跟进的地方。

### 库的 UB：未指定（¶4）

¶4 如果 E 会执行库条款（第 16 章及以后）规定为 UB 的操作，或者调用 `va_start`，E 是否是核心常量表达式是未指定的。

要求每个库实现在常量求值中检查所有前置条件，代价太高。实际上 `std::array<int, 3>{}[3]` 这类代码在常量求值中通常会被拒绝，因为库的实现最终做了一次核心语言层面的越界访问。但这只是实现的副产品，标准没有保证。

### `[[assume]]` 失败：实现定义（¶3）

¶3 **运行时未定义的行为**（runtime-undefined behavior，[[defns.undefined.runtime]]）在运行期是 UB，在常量求值中是否使 E 不是常量由实现定义。目前它只有一个来源：`[[assume(expr)]]` 中的 `expr` 为假（[[dcl.attr.assume]]）。

```cpp impl
constexpr int as(int x) {
  [[assume(x > 0)]];
  return x;
}
constexpr int e = as(-1);   // Clang 选择拒绝
```

不强制诊断的原因是，假设表达式本来不会被求值。要检查它，编译器就得额外求值一个可能代价很高的表达式。

## 函数调用（¶2.3–¶2.7）

```cpp
constexpr int f();                 // 只声明
constexpr int a = f();             // error: 此时 f 还没有定义
constexpr int f() { return 1; }
constexpr int b = f();             // OK

int rt();                          // 非 constexpr
constexpr int g(bool x) { return x ? 1 : rt(); }
constexpr int c = g(true);         // OK: rt() 没有被调用
constexpr int d = g(false);        // error: 调用了非 constexpr 函数
```

下列调用不允许：

- ¶2.3 调用非 constexpr 函数。脚注 61 说明重载决议照常进行，不会因为某个候选不是 constexpr 就改选别的。
- ¶2.4 调用在求值点还没有定义的 constexpr 函数。
- ¶2.5 调用一个不是 [[g:constexpr-suitable]] 的 constexpr 函数实例化。目前唯一的情形是协程：函数模板声明为 constexpr，某个实例化却是协程。这个实例化仍然合法，只是不能在常量求值中调用（[[dcl.constexpr#3]]）。
- ¶2.6 对动态类型未知的对象调用虚函数，见下文的 constexpr-unknown。动态类型已知时，C++20 起可以调用虚函数。

C++20 及以前，一个不可能产生常量的 constexpr 函数（比如 `constexpr int g() { return rt(); }`）是 IFNDR（非良构，但不要求诊断）。C++23 的 [[P2448R2]] 删除了这条规则，这样的函数现在合法，每次在常量求值中调用都会命中第 2.3 项。Clang 在 `-std=c++20` 下仍会报告 `constexpr function never produces a constant expression`。

¶2.7 超出实现限制的表达式也不是核心常量表达式。附录 [[implimits]] 建议的数量包括递归 constexpr 调用至少 512 层、一次求值至少 1 048 576 个完整表达式。有了这一项，死循环的常量求值就有了确定的结局：表达式不是常量，编译器不会卡死。

!!! impl "调整限制"
    Clang 用 `-fconstexpr-depth=`（默认 512）和 `-fconstexpr-steps=`（默认 1048576）；GCC 用 `-fconstexpr-depth=`、`-fconstexpr-loop-limit=`、`-fconstexpr-ops-limit=`；MSVC 用 `/constexpr:depth`、`/constexpr:steps`。

## 静态局部变量（¶2.2）

¶2.2 控制流经过一个静态或线程存储期的块变量的声明时，这个变量必须可用于常量表达式。

<div class="compare" markdown="1">

```cpp ok
constexpr char test() {
  static const int x = 5;
  static constexpr char c[] =
      "Hello World";
  return *(c + x);
}
static_assert(' ' == test());
```

```cpp error
constexpr int counter() {
  static int k = 0;
  return ++k;
}
// error: 经过了可变的 static
constexpr int c = counter();
```

</div>

运行期的静态局部变量在控制流第一次经过时初始化，值在多次调用之间共享。如果常量求值可以经过一个可变的 `static int`，编译期和运行期看到的状态就会分叉。左边的 `x` 和 `c` 都不可变，没有这个问题。

C++20 及以前，constexpr 函数体里根本不能定义静态变量。C++23 先允许它们出现在不执行的分支里（[[P2242R3]]），又允许控制流经过 `static constexpr` 变量（[[P2647R1]]），合起来就是今天的第 2.2 项。

## 类型双关（¶2.15–¶2.16）

¶2.15 {{c++26}} 从 `void*` 转换到 `T*` 时，指针必须是空指针，或者确实指向一个类型与 `T` [[g:similar-types|相似]]的对象。

```cpp
constexpr int ok() {
  int x = 42;
  void* p = &x;
  return *static_cast<int*>(p);     // OK: p 确实指向 int
}
static_assert(ok() == 42);

constexpr int bad() {
  int x = 42;
  void* p = &x;
  return *static_cast<short*>(p);   // 指向的是 int
}
constexpr int b = bad();            // error
```

C++23 及以前，任何从 `void*` 出发的 `static_cast` 都使表达式不是常量，类型擦除的容器因此无法在编译期使用。编译器本来就知道每个对象的真实类型，检查转回原类型的代价很低，于是 [[P2738R1]] 放开了这一情形。

¶2.16 `reinterpret_cast` 一律不允许，哪怕这次转换在运行期是合法的：

```cpp error
constexpr int first_byte() {
  int x = 1;
  return *reinterpret_cast<unsigned char*>(&x);   // 运行期合法的字节访问
}
constexpr int fb = first_byte();   // error
```

编译器的常量求值器维护的是一个有类型的对象模型，没有对象表示（字节）的概念。需要在编译期查看字节时，用 `std::bit_cast`（[[bit.cast]]）。

## 动态内存：分配必须在求值内释放（¶2.20–¶2.23、¶6）

```cpp
#include <vector>
constexpr int sum() {
  std::vector<int> v{1, 2, 3};
  v.push_back(4);
  int s = 0;
  for (int x : v) s += x;
  return s;                    // 返回前 v 已释放内存
}
static_assert(sum() == 10);    // OK

constexpr int* leak() { return new int(1); }
constexpr int* p = leak();     // error: 分配没有在求值内释放

constexpr std::vector<int> gv{1, 2, 3};   // error: 同上
```

C++20 的 [[P0784R7]] 允许常量求值使用动态内存，条件是分配是瞬时的（transient）：

- ¶2.20.1 *new-expression* 只能调用可替换的全局分配函数，且分配的存储必须在 E 的求值之内释放；
- ¶2.21 *delete-expression* 只能释放 E 之内分配的存储；
- ¶2.22–¶2.23 `std::allocator<T>::allocate` 和 `deallocate` 同理。

为什么不允许分配的内存留到运行期？那样编译期分配的内存就得变成静态存储，而运行期代码可能对它调用 `delete`，释放一块从没由运行期分配器分配过的内存。这个问题到 C++26 仍未解决，所以 `constexpr std::vector` 变量依然不能写。

¶2.20.2 {{c++26}} [[P2747R2]] 又允许了不分配内存的 placement new（`::new (p) T(...)`），条件是 `p` 指向的存储在 E 之内获得，且原有对象可以被新对象透明替换（[[basic.life]]）。

```cpp ok
#include <memory>
#include <new>
constexpr int pn() {
  std::allocator<int> al;
  int* p = al.allocate(1);
  ::new (p) int(7);            // C++26: 常量求值中的 placement new
  int r = *p;
  std::destroy_at(p);
  al.deallocate(p, 1);
  return r;
}
static_assert(pn() == 7);
```

C++20 和 C++23 只能用 `std::construct_at` 完成同样的事，引入它本来就是为了绕开 placement new 不能用于常量求值的限制。

¶6 判断时不看 `std::allocator<T>` 成员函数的函数体。库的实现内部可能用了不能常量求值的手段，标准只关心调用了 `allocate` 和 `deallocate` 这件事本身。

## 异常（¶2.24–¶2.25、¶2.31）{{c++26}}

```cpp
constexpr int ex() {
  try { throw 1; }
  catch (int e) { return e; }
}
static_assert(ex() == 1);   // C++26: OK；C++23: error
```

C++26 的 [[P3068]] 允许在常量求值中抛出并捕获异常，但异常不能逃出这次求值：

- ¶2.24 构造的异常对象，连同经 `std::current_exception`、`std::rethrow_exception` 产生的副本，都必须在 E 之内销毁；
- ¶2.25 不带操作数的 `throw;` 只能重新抛出 E 之内构造的异常；
- ¶2.31 `dynamic_cast`、`typeid`、*new-expression* 需要抛出 `std::bad_cast`、`std::bad_typeid`、`std::bad_alloc` 之类的异常，但异常类型的定义不可达（比如没有包含 `<typeinfo>`、`<new>`）时，不允许。

!!! impl "实现状态"
    Clang 23 仍拒绝上面的 `ex()`，尚未实现 [[P3068]]。在 C++23 及以前，求值到 *throw-expression* 就不是常量；`try` 块从 C++20 起可以出现在 constexpr 函数里，但 `catch` 在常量求值中永远执行不到。

## 指针的相等比较（¶2.28–¶2.29、¶1）

¶2.28 结果未指定的比较不允许。最常见的是比较两个无关对象地址的大小：

```cpp
int g1, g2;
constexpr bool c1 = &g1 < &g2;     // error: 大小关系未指定
constexpr bool c2 = &g1 == &g2;    // OK: false
```

¶2.29 字符串字面量、`std::initializer_list` 的底层数组等属于**可能非唯一对象**（potentially non-unique object，[[intro.object#9]]）。实现可以让内容相同或重叠的这类对象共用存储，所以 `"foo" == "foo"` 在运行期可能为真，也可能为假。

如果两个指针值来自不同的求值（[[basic.compound#4]]），用 `==` 比较它们时出现下面任一情况，就不是核心常量表达式：

- 两者可能指向同一个可能非唯一对象中的同一偏移；
- 其中一个指向的对象类型具有 constexpr-unknown 表示（见下）。

```cpp
constexpr const char* f() { return "foo"; }

constexpr bool b1 = +"foo" == "foo";              // error: 两个字面量可能共用存储
constexpr bool b2 = f() == f();                   // error: 同上
constexpr const char* p = f();
constexpr bool b3 = p == p;                       // OK: true，同一个指针值
constexpr bool b4 = "xfoo" + 1 == "foo\0y";       // error: 可能合并成 "xfoo\0y"
constexpr bool b5 = "foo" == "bar" + 0;           // OK: false，内容不同
constexpr bool b6 = (const char*)"foo" == "oo";   // OK: false，合并后偏移也不同
```

`b4` 中 `"xfoo" + 1` 与 `"foo\0y"` 的前四个字符相同，两者可以放进同一块存储，结果取决于实现。`b5`、`b6` 则可以证明不会指向同一位置，结果确定为 false。

¶1 第二种情况用到了一个辅助概念。类型 T **具有 constexpr-unknown 表示**（[[g:constexpr-unknown-representation|constexpr-unknown representation]]），如果它是联合体、`std::meta::info`、指针或成员指针、volatile 限定的类型、含引用成员的类，或者有基类或成员的类型具有这种表示。这些类型的字节在编译期无法确定：指针的位模式取决于加载地址，空指针也不一定是全零；联合体的字节取决于活跃成员。`std::bit_cast` 的常量求值条件（[[bit.cast]]）用的也是这个概念。

```cpp
#include <initializer_list>
constexpr std::initializer_list<int*> il1 = {(int*)nullptr};
constexpr std::initializer_list<unsigned long> il2 = {0};
constexpr bool b7 = il1.begin() == (void*)il2.begin();   // 按标准是 error
```

编译器不知道 `nullptr` 和 `0UL` 的字节是否相同，所以不能排除两个底层数组被合并。Clang 23 接受 `b7`，还没有实现这条规则。

## 编译期不知道的引用与对象（¶9）

```cpp ok
#include <cstddef>
template <typename T, std::size_t N>
constexpr std::size_t array_size(T (&)[N]) { return N; }

void use_array(int const (&arr)[2]) {
  constexpr auto n = array_size(arr);   // C++23 起 OK
  static_assert(n == 2);
}
```

`array_size` 根本不读数组，只用模板参数 `N`。但在 C++20 中，把引用形参 `arr` 作为实参传递要求值 `arr`，而引用必须用常量初始化才能在常量表达式中使用，形参显然不满足，所以这段代码非法。`std::size(arr)` 也有同样的问题。

¶9 [[P2280R4]] 修正了这一点。在常量求值中，指代求值之外的对象或引用的 *id-expression*、*splice-expression* 和 `*this`，都被看作指代一个特定的实例，它和它的全部子对象在整个求值期间都存活：

- 如果这个对象不可用于常量表达式，它的动态类型是 **constexpr-unknown**（[[g:constexpr-unknown]]）；
- 如果这个引用不可用于常量表达式，它被看作绑定到被引用类型的一个未指定对象，该对象的动态类型也是 constexpr-unknown。

直观地说，编译器可以拿着一个值未知的引用做不需要它的值的事：取地址、传递、调用不读成员的非虚函数。一旦要读值、调用虚函数、做 `dynamic_cast` 或多态 `typeid`，就会命中清单。

```cpp
#include <typeinfo>
struct Swim {
  constexpr int phelps() { return 28; }
  virtual constexpr int lochte() { return 12; }
  int coughlin = 12;
};

constexpr int how_many(Swim& swam) {
  Swim* p = &swam;
  return (p + 1 - 1)->phelps();
}

void splash(Swim& swam) {
  static_assert(swam.phelps() == 28);       // OK: 不读 swam 的任何值
  static_assert((&swam)->phelps() == 28);   // OK
  Swim* pswam = &swam;
  static_assert(pswam->phelps() == 28);     // error: 读了指针变量 pswam
  static_assert(how_many(swam) == 28);      // OK: p 是求值内创建的
  static_assert(Swim().lochte() == 12);     // OK: 动态类型已知
  static_assert(swam.lochte() == 12);       // error: 动态类型未知，不能调虚函数
  static_assert(swam.coughlin == 12);       // error: 读了不可用于常量表达式的对象
}

extern Swim dc;
extern Swim& trident;
constexpr auto& sandeno   = typeid(dc);       // OK: 只能是 typeid(Swim)
constexpr auto& gallagher = typeid(trident);  // error: 动态类型未知
```

¶2.30 对动态类型未知的对象做 `dynamic_cast` 或多态 `typeid` 不允许，调用虚函数也不允许（第 2.6 项）。`trident` 是引用，可能绑定到 `Swim` 的派生类对象上，所以 `typeid(trident)` 非法。`dc` 是一个声明为 `Swim` 的变量，它的最派生类型只能是 `Swim`，标准的例子因此把 `typeid(dc)` 判为 OK，Clang 也接受。

!!! lawyer "措辞与例子的出入"
    按第 9 段的字面意思，`dc` 不可用于常量表达式，动态类型就是 constexpr-unknown，`typeid(dc)` 应当命中第 2.30 项。标准的例子却判它合法。合理的理解是：变量直接声明的完整对象，动态类型只能是声明类型。规范文字本身没有写明这一点。

本机 Clang 23 在 `-std=c++23` 及以后接受 `use_array`，在 `-std=c++20` 下仍然拒绝。

### `this`（¶2.1）

¶2.1 `this` 只能在两种情况下求值：在作为 E 的一部分被求值的 constexpr 函数里（2.1.1），或者作为成员访问 `this->m`（含隐式的 `m`）的左侧（2.1.2）。第二种情况配合第 9 段：在非 constexpr 成员函数里，`*this` 是一个动态类型未知的对象，只要被调用的成员函数不读它的成员，就不需要知道它的值。

```cpp
struct S {
  static constexpr int cap() { return 4; }
  constexpr int sz() const { return 3; }   // 不读任何成员
  void f() {                               // 非 constexpr 成员函数
    static_assert(this->cap() == 4);       // 按标准 OK
    static_assert(sz() == 3);              // 按标准 OK
  }
};
```

!!! impl "Clang 的偏差"
    Clang 23 拒绝这两条 `static_assert`，报告 `static assertion expression is not an integral constant expression`，尚未实现第 2.1.2 项。

## lambda、联合体复制与结构化绑定

### lambda 中对外层变量的 odr-use（¶2.14）

¶2.14 在 lambda 中引用 `this` 或 lambda 外的自动变量，如果构成 [[g:odr-use]]（需要变量本身而不只是它的值，见 [[basic.def.odr]]），表达式就不是核心常量表达式。

```cpp
void g() {
  const int n = 0;
  [=] {
    constexpr int i = n;       // OK: 只用到 n 的值，不是 odr-use
    constexpr int j = *&n;     // error: 取地址是对 n 的 odr-use
  };
}
```

odr-use 会触发捕获，被捕获的 `n` 实际是闭包对象的成员，而闭包对象存在于运行期。`constexpr int i = n;` 只读一个可用于常量表达式的变量的值，不算 odr-use，也就不需要捕获。

注 1 补充：闭包的函数调用运算符被调用时，被捕获的名字已经变换成对闭包成员的访问（[[expr.prim.lambda.capture]]），不再指代外层变量，不受第 2.14 项约束。所以在常量求值内部创建和调用闭包完全没有问题：

```cpp ok
auto monad = [](auto v) { return [=] { return v; }; };
auto bind  = [](auto m) { return [=](auto fvm) { return fvm(m()); }; };
static_assert(bind(monad(2))(monad)() == monad(2)());
```

!!! impl "Clang 的偏差"
    Clang 23 没有拒绝上面的 `constexpr int j = *&n;`（lambda 从未被调用，Clang 没有检查这个初始化器）。按标准它是非良构的。

### 联合体的复制（¶2.13、¶7）

¶7 联合体平凡的复制或移动在运行期就是复制字节，但常量求值器没有字节的概念。标准规定，判断时把它看作复制活跃成员，活跃成员随之转移。

```cpp ok
union U { int i; float f; };
constexpr float h() {
  U a{.f = 1.5f};
  U b = a;         // 看作复制活跃成员 f
  return b.f;      // OK
}
static_assert(h() == 1.5f);
```

¶2.13 如果活跃成员是 `mutable` 的，复制就等于读取一个运行期可以改变的值。所以除非联合体对象是本次求值创建的，这种复制不允许：

```cpp
union V { mutable int m; int n; };
constexpr V u{.m = 1};
constexpr V v = u;          // error: 活跃成员 m 是 mutable

constexpr int local() { V a{.m = 1}; V b = a; return b.m; }
static_assert(local() == 1);   // OK: a 是本次求值创建的
```

### 结构化绑定（¶8）

¶8 常量求值中，结构化绑定的名字按它实际指代的东西处理（[[dcl.struct.bind]]）：如果它绑定到一个虚构的引用（tuple 协议的情形），就当作指名那个引用；如果它指代数组元素或类成员，就当作求值 `e[i]` 或 `e.m`，`e` 是结构化绑定声明引入的无名变量。

```cpp
#include <tuple>
struct S {
  mutable int m;
  constexpr S(int m) : m(m) {}
  virtual int g() const;
};
void f(std::tuple<S&> t) {
  auto [r] = t;
  static_assert(r.g() >= 0);        // error: r 的动态类型未知
  constexpr auto [m] = S(1);
  static_assert(m == 1);            // error: 等价于 e.m，读 mutable 成员
  using A = int[2];
  constexpr auto [v0, v1] = A{2, 3};
  static_assert(v0 + v1 == 5);      // OK: 等价于 e[0] + e[1]
}
```

constexpr 结构化绑定本身是 C++26 的新特性（[[P2686]]）。

## 其余条目

- ¶2.26–¶2.27 `co_await`、`co_yield` 不允许。协程帧需要运行期分配，协程也不是 constexpr-suitable 的函数。
- ¶2.32 {{c++26}} 产生注入声明的表达式（例如 `std::meta::define_aggregate`）只能出现在 `consteval { ... }` 块中，这样修改程序本身的操作就有了确定的位置和时机。详见 [[expr.const.reflect]]。
- ¶2.33 *asm-declaration* 不能被求值。C++20 起它可以写在 constexpr 函数中，供 `std::is_constant_evaluated()` 或 `if consteval` 的运行期分支使用。
- ¶2.34 `va_arg` 不允许；`va_start` 的情形见上文第 4 段。
- ¶2.35 **非常量库调用**（[[g:non-constant-library-call|non-constant library call]]）不允许，即库规范说明会阻止表达式成为常量的调用，例如不满足 *Constant When* 条件的调用。
- ¶2.36 `goto` 语句不允许。注 2 说明，标准用 goto 描述语义的那些语句（例如 `while`）不在此列。

```cpp
constexpr int gt(int n) {
  if (n < 0) goto bad;     // C++23 起可以写
  return n;
bad:
  return 0;
}
constexpr int a = gt(1);     // OK: 没有执行 goto
constexpr int b = gt(-1);    // error
```

禁止 `goto` 主要是出于实现成本：常量求值器通常是在语法树上执行的解释器，任意跳转很难支持，而 `goto` 能做的事都能用结构化的控制流完成。

## 实现视角

!!! impl "常量求值器是一个解释器"
    Clang 的常量求值器传统上是在 AST 上执行的解释器（`ExprConstant.cpp`），它为每个对象记录类型、生命期和活跃的联合体成员，指针表示为对象加上路径，所以能精确发现越界、悬空和类型双关；新的字节码解释器（`-fexperimental-new-constant-interpreter`）正在逐步替代它。GCC 的 `constexpr.cc` 也在 AST 上求值。

    这类实现里的指针都不是整数，而是对象加偏移的符号值，求值器里根本没有地址。`reinterpret_cast`、指针转整数、比较无关对象地址的大小都无法支持，原因就在这里。

## 常见误解

!!! pitfall "constexpr 函数里的 UB 一定会被发现"
    同样是 `add(INT_MAX, 1)`，在 `constexpr int x = ...` 里是编译错误，在 `int x = ...` 里是运行期的 UB，编译器不会给出任何提示。constexpr 函数通过了 `static_assert` 测试，只说明测过的那几组实参没有 UB。

!!! pitfall "不是常量就会编译失败"
    在不要求常量的地方，例如 `const int n = f();` 或命名空间作用域的 `int x = f();`，表达式不是常量只意味着它改为在运行期初始化，程序仍然合法。想确保在编译期计算，要写 `constexpr` 或 `constinit`。

## 思考题

!!! question "思考题 1"
    下面哪些 `static_assert` 合法？

    ```cpp
    struct P { int x; constexpr int get() const { return 7; } };
    void f(P& r, P v) {
      static_assert(r.get() == 7);   // (a)
      static_assert(v.get() == 7);   // (b)
      static_assert(&r == &r);       // (c)
      static_assert(v.x == v.x);     // (d)
    }
    ```

<details markdown="1">
<summary>答案</summary>

- (a) 合法。按第 9 段，`r` 被看作绑定到一个未指定的 `P` 对象；`get` 是在求值中被调用的 constexpr 函数，可以使用 `this`（第 2.1.1 项），而它不读任何成员。
- (b) 合法。`v` 是求值之外的对象，同样被看作一个特定实例。
- (c) 合法。两侧指代同一个实例，取地址不读值，结果是 true。
- (d) 非法。读 `v.x` 是对一个不可用于常量表达式、也不是本次求值创建的对象做左值到右值转换（第 2.10 项）。

在 P2280 之前，(a) 和 (c) 也非法，因为它们要求值引用 `r`。Clang 23 的结果与上面的分析一致。
</details>

!!! question "思考题 2"
    为什么 `a` 合法而 `b` 不合法？

    ```cpp
    constexpr int f(int* p) { return p ? *p : 0; }
    constexpr int a = f(nullptr);
    int g = 1;
    constexpr int b = f(&g);
    ```

<details markdown="1">
<summary>答案</summary>

`f(nullptr)` 没有执行 `*p`，而清单只看实际执行的操作。`f(&g)` 中，`&g` 本身没有问题（`g` 有静态存储期，地址是常量），但 `*p` 要读 `g` 的值，而 `g` 不是 const，不可用于常量表达式，也不是本次求值创建的，命中第 2.10 项。
</details>

!!! question "思考题 3"
    `constexpr std::string s = "hi";` 在 libc++ 下能编译，换成一个长字符串就不行。为什么？这段代码可移植吗？

<details markdown="1">
<summary>答案</summary>

短字符串优化（SSO）把短字符串存在 `std::string` 对象内部，不分配内存，所以 `s` 的初始化没有动态分配。长字符串要分配堆内存，而这块内存在求值结束时没有释放，违反了第 2.20 项。

标准没有规定在常量求值中是否使用 SSO，也没有规定 SSO 的容量，所以这段代码不可移植。本机 libc++（随 Clang 23）接受 `"hi"`，拒绝超过 SSO 容量的字符串。
</details>

## 小结

| 想在常量求值中做的事 | 什么时候可以 | 列表项 |
|---|---|---|
| 读一个对象 | 它可用于常量表达式，或者是本次求值创建的 | ¶2.10 |
| 修改一个对象 | 它是本次求值创建的 | ¶2.18 |
| 调用函数 | constexpr、已定义、不是协程 | ¶2.3–¶2.5 |
| 调虚函数、`dynamic_cast`、多态 `typeid` | 动态类型已知 | ¶2.6、¶2.30 |
| `new` / `delete` | 在本次求值内配对 | ¶2.20–¶2.23 |
| placement new | 存储是本次求值获得的 {{c++26}} | ¶2.20.2 |
| 从 `void*` 做 `static_cast` | 指向的对象类型与目标相似 {{c++26}} | ¶2.15 |
| 抛出异常 | 在本次求值内抛出并处理完 {{c++26}} | ¶2.24–¶2.25 |
| `reinterpret_cast`、`goto`、`asm`、`co_await` | 求值到就不行 | ¶2.16、¶2.36、¶2.33、¶2.26 |
| 核心语言的 UB、错误行为 | 永远不行，必须诊断 | ¶2.8 |
| 库的 UB | 未指定 | ¶4 |
| `[[assume]]` 为假 | 实现定义 | ¶3 |
