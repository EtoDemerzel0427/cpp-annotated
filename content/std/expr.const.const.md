---
title: 常量表达式
summary: 核心常量表达式还要满足什么才算常量表达式；数组边界、模板实参、case 标签等处要求的转换后的常量表达式只允许哪些转换；C++26 中只能在编译期存在的值与立即对象。
status: done
papers: P2996R13, P2686, P1401R5, P2795R5
related: expr.const.core, expr.const.init, expr.const.imm, temp.arg.nontype, dcl.init.list, stmt.switch, dcl.array
tags: 常量求值, 常量表达式, consteval
updated: 2026-10-19
---

!!! tldr
    - 核心常量表达式只约束求值过程。要成为常量表达式，结果中还不能有无效指针（例如指向已销毁的局部变量）、不确定值或错误值。
    - 数组边界、`case` 标签、常量模板实参等处要求转换后的常量表达式：只允许不丢失信息的隐式转换，窄化、整数与浮点之间的转换都不行。
    - `noexcept(...)` 和 `explicit(...)` 的条件不能是窄化到 `bool` 的整数；`static_assert` 和 `if constexpr` 从 C++23 起可以。
    - C++26 中，反射值和指向 `consteval` 函数的指针只在编译期有意义。含有这种值的对象只能存在于 constexpr 变量、模板实参或一次常量求值内部。

## 求值没有问题，结果却不能用（¶4）

```cpp
constexpr int* dang() {
  int x = 0;
  return &x;                      // 返回局部变量的地址
}
constexpr int* dp = dang();       // error: 结果是无效指针值

struct S {
  int x;
  constexpr S() {}                // 没有初始化 x
};
int f() {
  constexpr S s;                  // error: s.x 是错误值
  return 0;
}
```

`dang()` 的求值过程没有任何问题：取局部变量的地址、返回它，都不在[[expr.const.core|核心常量表达式]]的禁止清单上。问题出在结果，一个指向已销毁对象的指针被带出了求值。所以标准需要一条单独针对结果的规则。

!!! std
    A core constant expression is a constant expression unless it is a prvalue whose result object has a constituent value that is an invalid pointer value or is indeterminate or erroneous.

¶4 核心常量表达式就是**常量表达式**（constant expression），除非它是纯右值，而且结果对象的[[g:constituent-values|组成值]]（把对象一直展开到每个标量子对象后得到的全部值，[[intro.object]]）中有以下三种值之一：

1. **无效指针值**（invalid pointer value，[[basic.compound]]）：指向存储期已经结束的存储，典型来源就是上面的 `dang()`；
2. [[g:indeterminate-value|不确定值]]（[[basic.indet]]）；
3. [[g:erroneous-value|错误值]] {{c++26}}：C++26 中未初始化的自动变量默认具有的值（[[P2795R5]]）。上面的 `s.x` 就是这种情况，C++23 中它是不确定值。

!!! history "允许的结果"
    C++23 及以前，这里是一长段对常量表达式允许的结果（permitted result）的规定：泛左值必须指代静态存储期的对象或函数，纯右值中的指针必须指向静态存储期对象、函数，或为空。

    C++26 的 [[P2686]] 把是否具有静态存储期的要求挪了出去，改成对变量的要求，即 constexpr-representable（[[expr.const.init#3]]）。是不是常量表达式只看值是否确定；能不能存进某个 constexpr 变量，要看变量在哪里。函数内的 `constexpr int* p = &local;` 有确定的含义，命名空间作用域的 constexpr 指针则必须指向静态存储期对象。

注 1（在第 5 段之后）提醒，指代或指向一个未指定对象的泛左值核心常量表达式不是常量表达式。这关系到值未知的引用（[[expr.const.core#9]]）：在 `void f(int& r) { constexpr int* p = &r; }` 中，`r` 被看作绑定到一个未指定的对象，`&r` 不能作为常量表达式的结果。

## 转换后的常量表达式（¶8）

```cpp
template<char C>   struct TC {};
template<bool B>   struct TB {};
template<int N>    struct TI {};
template<double D> struct TD {};
template<const int& R> struct TR {};

TC<65>  c1;    // OK: int → char，65 可以表示
TC<300> c2;    // error: 300 不能用 char 表示，是窄化
TB<2>   b1;    // error: 2 → bool 是窄化
TI<2.0> i1;    // error: 不允许浮点 → 整数
TD<1>   d1;    // error: 不允许整数 → 浮点

long gl = 0;
TR<gl>  r1;    // error: 要绑定到临时对象，不是直接绑定
```

常量模板实参、数组边界、`case` 标签、*new-expression* 中的数组长度、底层类型固定的枚举的枚举量初值，以及 C++26 的 *splice-specifier*，要求的都是**转换后的常量表达式**（converted constant expression，注 3）。

¶8 类型 T 的转换后的常量表达式，是一个隐式转换到 T 的表达式：转换后的表达式必须是常量表达式，隐式转换序列只能包含下列转换；如果涉及引用绑定，必须直接绑定，不能绑定到临时对象。

| 允许的转换 | 列表项 | 说明 |
|---|---|---|
| 用户定义转换 | 8.1 | 选中的转换函数或构造函数要能在常量求值中调用 |
| 左值到右值、数组到指针、函数到指针 | 8.2–8.4 | |
| 限定转换 | 8.5 | 加 `const` |
| 整型提升 | 8.6 | |
| 整型转换，窄化除外 | 8.7 | 值能用目标类型表示就不算窄化（[[dcl.init.list]]） |
| 浮点提升 | 8.8 | `float` → `double` |
| 浮点转换，源值能精确表示 | 8.9 | `double` 1.0 → `float` 可以，0.1 不行 |
| 从 `std::nullptr_t` 到空指针、空成员指针 | 8.10–8.11 | |
| 函数指针转换 | 8.12 | 去掉 `noexcept` |

不在表里的转换都不允许：整数与浮点之间的转换、派生类指针到基类指针、指针到 `void*`、指针到 `bool`，以及窄化的整型转换。

为什么这么严格？这些地方需要一个精确的值。模板实参决定类型是否相同，如果 `TC<300>` 悄悄变成 `TC<44>`，两个看起来不同的实参就会得到同一个类型。禁止窄化与列表初始化（[[dcl.init.list]]）的思路一致。

```cpp
template<float F> struct TF {};
TF<1.0> f1;    // 按标准 OK: 1.0 能用 float 精确表示
TF<0.1> f2;    // error: 0.1 不能
```

!!! impl "Clang 的偏差"
    Clang 23 对 `TF<1.0>` 也报错（`conversion from 'double' to 'float' is not allowed in a converted constant expression`），还没有实现第 8.9 项允许的可精确表示的浮点转换。

### `case` 标签：先提升，再转换

`case` 标签的目标类型是 `switch` 条件经整型提升后的类型（[[stmt.switch]]）：

```cpp ok
void sw(unsigned char c) {
  switch (c) {          // 条件提升为 int
  case 1000: break;     // OK: 1000 是 int，没有窄化
  }
}
```

很多人以为 `case 1000` 对 `unsigned char` 是窄化错误。实际上目标类型是 `int`，这个 `case` 只是永远不会命中。

### 用户定义转换

第 8.1 项允许用户定义转换，字面类类型的对象因此可以用作数组边界或 `case` 标签：

```cpp ok
struct Idx {
  int v;
  constexpr operator int() const { return v; }
};
constexpr Idx three{3};
int arr[three];              // Idx → int → std::size_t，3 可以表示
void sw(int x) {
  switch (x) { case Idx{1}: break; }
}
```

## 按语境转换为 bool 的常量表达式（¶9）

```cpp
struct S { explicit(2) S(int); };   // error: 2 → bool 是窄化
void f() noexcept(2);               // error: 同上
static_assert(2);                   // OK: 不使用这个定义
void g() { if constexpr (2) {} }    // OK: 同上
```

¶9 **按语境转换为 bool 的常量表达式**（contextually converted constant expression of type bool）是按语境转换为 `bool`（[[conv]]）后得到常量表达式、且转换序列只含第 8 段所列转换的表达式。`noexcept(...)`（[[except.spec]]）和 `explicit(...)`（[[dcl.fct.spec]]）使用这个定义，所以窄化的 `2 → bool` 不允许。

!!! history "static_assert 和 if constexpr 的放宽"
    C++17 和 C++20 中，`if constexpr` 的条件也是按语境转换为 bool 的常量表达式，于是 `if constexpr (N % 4)`、`if constexpr (sizeof(T) & 1)` 都因窄化而非法，必须写成 `!= 0`。C++23 的 [[P1401R5]] 把 `static_assert` 和 `if constexpr` 改为只要求转换后是常量表达式，不再限制窄化（[[dcl.pre#13]]、[[stmt.if#2]]）；`noexcept` 和 `explicit` 保持不变。主流编译器在较早的语言模式下也采用了这一改动。

## 整型常量表达式（¶6–¶7）

¶6 **整型常量表达式**（integral constant expression）是整型或无作用域枚举类型的表达式，隐式转换为纯右值后是核心常量表达式。整型值不可能是无效指针，所以核心常量表达式就够了。位域长度（[[class.bit]]）、底层类型不固定的枚举的枚举量初值（[[dcl.enum]]）和对齐值（`alignas`）使用这个定义（注 2）。

¶7 在要求整型常量表达式的地方给出一个字面类类型的表达式时，它按语境隐式转换为整型或无作用域枚举类型（[[conv]]），选中的转换函数必须是 constexpr。这种转换要求恰好只有一个可行的目标类型，否则就有歧义：

```cpp error
struct A {
  constexpr A(int i) : val(i) { }
  constexpr operator int() const { return val; }
  constexpr operator long() const { return 42; }
private:
  int val;
};
constexpr A a = alignof(int);
alignas(a) int n;              // error: 转为 int 还是 long？
struct B { int n : a; };       // error: 同上
```

## 只能在编译期存在的值（¶1–¶3、¶5）{{c++26}}

```cpp
consteval int plus1(int x) { return x + 1; }
template <auto V> struct C {};

auto a = plus1;              // error: 运行期变量持有指向 consteval 函数的指针
constexpr auto b = plus1;    // OK
auto c = C<plus1>();         // OK: 模板参数对象

auto d = ^^int;              // error: 反射值进入了运行期变量
auto e = C<^^char>();        // OK
```

`consteval` 函数又叫[[g:immediate-function|立即函数]]，它只在编译期调用，不生成代码，运行期没有地址。反射值（`^^int` 的结果，类型是 `std::meta::info`）是编译器内部数据的句柄，运行期也不存在。这样的值一旦进入运行期的对象，程序就会持有一个不存在的东西。

¶1 下面两种值称为 **consteval-only 值**（[[g:consteval-only-value|consteval-only value]]）：

- 非空的反射值（[[basic.fundamental]]）；
- 指向立即函数，或指向（或越过末尾）立即对象的指针或成员指针。

¶2 如果一个对象的完整对象含有 consteval-only 的组成值，或者含有引用立即对象、立即函数的组成引用，这个对象就是**立即对象**（[[g:immediate-object|immediate object]]）。只要结构体深处有一个非空的 `std::meta::info` 成员，整个完整对象就是立即对象。

¶3 每个立即对象必须是以下之一：

- constexpr 变量关联的对象或它的子对象；
- 模板参数对象（[[temp.param]]）或它的子对象；
- 生命期在某次核心常量表达式求值中开始并结束的对象。

这三处都只存在于编译期：constexpr 变量的值编译器全部知道，模板实参是类型的一部分，求值内部的临时对象在求值结束时就没了。

第 3 段还要求，odr-use 了声明或引用立即对象的变量的表达式，必须处在[[g:immediate-function-context|立即函数语境]]中（[[expr.const.imm#1]]，例如立即函数体内或 `static_assert` 的条件里）。只有当包含该表达式的最内层声明与变量的定义之间有一方从另一方可达时，才要求诊断（3.4–3.5）。在模块或多个翻译单元的情形下，编译器在使用处可能看不到变量的定义，无从得知它引用了立即函数。

```cpp
consteval int plus1(int x) { return x + 1; }
constexpr auto b = plus1;
int use(int n) { return b(n); }   // error: 普通函数中使用了立即对象
static_assert(b(1) == 2);         // OK: static_assert 的条件处在立即函数语境中
```

¶5 如果一个常量表达式是指代立即对象或立即函数的泛左值，或者是结果对象为立即对象的纯右值，它就是**立即常量表达式**（[[g:immediate-constant-expression|immediate constant expression]]）。[[expr.const.imm#2]] 用它判断立即升级：模板实例化等函数中如果出现了不在立即函数语境中的立即常量表达式，这个函数自己就变成立即函数。上例中的 `use` 不是这样可以升级的函数，所以出错。

```cpp
consteval int f() { return 42; }
consteval auto g() { return f; }              // 返回指向立即函数的指针
consteval int h(int (*p)() = g()) { return p(); }
constexpr int r = h();                        // OK: 指针只在立即函数内部传递
constexpr auto e = g();                       // 标准的例子标为 error
```

`r` 合法，因为默认实参 `g()` 的结果只在 `h` 内部使用，最终结果是 `int`。

!!! lawyer "例子 2 中的 `e`"
    标准例子给 `e` 的注释是指向立即函数的指针不是常量表达式允许的结果，这是 C++23 的说法，而第 4 段已经没有允许的结果这个概念。按 C++26 的规则推理：constexpr 变量的初始化器是显然常量求值的，`g()` 处在立即函数语境中；`e` 关联的对象是立即对象，第 3.1 项允许它属于 constexpr 变量。这和 `constexpr auto b = plus1;` 合法的推理相同。这条注释很可能是改写第 1–3 段之后没有同步修改的遗留。

!!! impl "实现状态"
    这一节的例子都无法用 Clang 23 验证。它没有实现反射（`^^`），并且仍按 C++23 的规则拒绝 `constexpr auto b = plus1;`、`C<plus1>` 和 `e`，报告 `cannot take address of consteval function 'plus1' outside of an immediate invocation`。

## 实现视角

!!! impl "地址常量是符号值"
    `constexpr int* p = &global;` 是常量表达式，但它的值不是一个数，而是 `global` 的地址。目标文件里 `p` 的初始字节通常是 0，另有一条重定位记录，由链接器或加载器填入 `global` 的最终地址；在位置无关的可执行文件和共享库中，地址要到加载时才确定。常量表达式中不能把指针转换成整数（这需要 `reinterpret_cast`，见 [[expr.const.core#2.16]]），原因就在这里：编译期并不知道那个整数是多少。

## 常见误解

!!! pitfall "`const int` 总能当常量用"
    `const int n = f();` 中的 `n` 能不能用作数组边界，取决于 `f()` 能不能在编译期求值。给 `f` 加一行非 constexpr 的日志调用，远处的 `int a[n];` 就会变成变长数组（GCC 和 Clang 的扩展）或编译错误。需要常量时应写 `constexpr`。详见 [[expr.const.init]]。

## 思考题

!!! question "思考题 1"
    下列模板实参哪些合法？

    ```cpp
    template<unsigned N> struct U {};
    U<-1> u1;
    U<'a'> u2;
    U<sizeof(int)> u3;
    U<true> u4;
    ```

<details markdown="1">
<summary>答案</summary>

- `U<-1>` 非法。`int` → `unsigned` 是整型转换，-1 不能用 `unsigned` 表示，是窄化。
- `U<'a'>` 合法。`char` 提升的目标是 `int` 而不是 `unsigned`，所以这是整型转换；97 可以表示，不是窄化。
- `U<sizeof(int)>` 合法。`std::size_t` → `unsigned` 从较宽的类型转换，但源是常量表达式且值可以表示，不算窄化（[[dcl.init.list]]）。
- `U<true>` 合法。`bool` → `unsigned` 是整型转换，`true` 变为 1（[[conv.integral#2]]），不是窄化。

Clang 23 只拒绝 `U<-1>`。
</details>

!!! question "思考题 2"
    转换后的常量表达式允许 `float` → `double`，为什么不允许 `int` → `double`？32 位 `int` 的值不是都能用 `double` 精确表示吗？

<details markdown="1">
<summary>答案</summary>

允许的转换都在同一类别之内：整数到整数、浮点到浮点、指针的限定调整。整数与浮点之间的转换（[[conv.fpint]]）不在列表中，即使值能精确表示也不行。这条规则简单、可预测，模板实参 `TD<1>` 与 `TD<1.0>` 在写法上就不同，标准要求程序员写出 `1.0`。浮点到浮点的转换则只要源值能精确表示就允许（第 8.9 项）。
</details>

## 小结

| 名称 | 要求 | 用在哪里 |
|---|---|---|
| 常量表达式 | 核心常量表达式，结果中没有无效指针、不确定值、错误值 | constexpr 变量等一般要求常量的地方 |
| 转换后的常量表达式 | 只允许不丢失信息的转换，引用必须直接绑定 | 数组边界、`case`、常量模板实参、固定底层类型的枚举量、*splice-specifier* |
| 按语境转换为 bool 的常量表达式 | 同上，目标类型是 `bool` | `noexcept(...)`、`explicit(...)` |
| 整型常量表达式 | 整型或无作用域枚举，核心常量表达式即可；类类型要有唯一的 constexpr 转换 | 位域长度、底层类型不固定的枚举量、`alignas` |
| 立即常量表达式 {{c++26}} | 结果是立即对象或立即函数 | 立即升级的判断（[[expr.const.imm]]） |
| `static_assert`、`if constexpr` 的条件 | 转为 `bool` 后是常量表达式，允许窄化 | C++23 起 |
