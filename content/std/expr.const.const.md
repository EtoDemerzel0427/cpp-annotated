---
title: 常量表达式
summary: 核心常量表达式的结果还必须"能带出去"——不含无效指针、不确定值或错误值；consteval-only 值与立即对象；整型常量表达式、转换后的常量表达式与按语境转换为 bool 的常量表达式
status: done
papers: P2996R13, P2686, P1401R5, P2795R5
related: expr.const.core, expr.const.init, expr.const.imm, temp.arg.nontype, dcl.init.list, stmt.switch, dcl.array
tags: 常量求值, 常量表达式, consteval
updated: 2026-10-17
---

[[expr.const.core]] 规定了求值**过程**的约束；本节规定**结果**的约束，并定义各个上下文实际使用的几种常量表达式。逻辑顺序是：

1. ¶1–¶3 {{c++26}}：**consteval-only 值**与**立即对象**——带有反射值或指向立即函数的指针的对象，不能逃逸到运行期；
2. ¶4：**常量表达式**的定义——核心常量表达式 + 结果中没有无效指针、不确定值、错误值；
3. ¶5：**立即常量表达式**——结果是/指向立即对象或立即函数的常量表达式（供 [[expr.const.imm]] 使用）；
4. ¶6–¶9：**整型常量表达式**、**转换后的常量表达式**、**按语境转换为 bool 的常量表达式**。

## consteval-only 值（¶1）{{c++26}}

**consteval-only 值**（consteval-only value）是：

- ¶1.1 一个**非空**的反射值（`std::meta::info` 类型的值，[[basic.fundamental]]）；或
- ¶1.2 一个指向**立即函数**、或指向（或越过末尾）**立即对象**的指针或成员指针。

它们的共同点：**在运行期没有意义**。反射值是编译器内部数据结构的句柄，运行期不存在；立即函数（`consteval`）不会生成代码，运行期没有地址。如果这样的值进入运行期的对象，程序就会持有一个不存在的东西。

## 立即对象（¶2–¶3）{{c++26}}

¶2：一个对象是**立即对象**（immediate object），如果它的完整对象具有

- ¶2.1 一个 consteval-only 的**组成值**（constituent value），或
- ¶2.2 一个引用立即对象或立即函数的**组成引用**（constituent reference）。

"组成值/组成引用"（[[intro.object]]）大致是：对象的所有标量子对象的值和所有引用成员——即"展开到叶子"后的全部内容。所以只要结构体深处藏了一个 `std::meta::info` 成员（非空），整个完整对象就是立即对象。

¶3：每个立即对象**必须**是以下之一：

- ¶3.1 constexpr 变量关联的对象（或其子对象）；
- ¶3.2 模板参数对象（[[temp.param]]）或其子对象；
- ¶3.3 生命期在某个核心常量表达式的求值内开始并结束的对象。

也就是说，立即对象只能活在"纯编译期"的地方：constexpr 变量（编译器知道其全部值，运行期不必真的存在）、模板实参、或者一次常量求值内部的临时对象。

```cpp
consteval int plus1(int x) { return x + 1; }
template <auto V> struct C {};

auto a = plus1;                 // error: a 是运行期变量，却持有指向立即函数的指针
constexpr auto b = plus1;       // OK（C++26）：立即对象关联于 constexpr 变量
auto c = C<plus1>();            // OK：模板参数对象

auto d = ^^int;                 // error: 反射值不能进入非 constexpr 变量
auto e = C<^^char>();           // OK
```

¶3 的后半段：每个 odr-use 一个"声明或引用立即对象的变量"的表达式 E，都必须处在**立即函数语境**（immediate function context，[[expr.const.imm#1]]）中。此外，即便没有 odr-use，在运行期代码里**提到**这样的变量也通不过：`b` 作为 *id-expression* 是"指代立即对象的泛左值"，即**立即常量表达式**（¶5.1），在非立即升级函数中出现就违反 [[expr.const.imm#3]]。

```cpp
consteval int plus1(int x) { return x + 1; }
constexpr auto b = plus1;
int use(int n) { return b(n); }   // error: b 是立即常量表达式，出现在普通函数中
static_assert(b(1) == 2);         // OK：static_assert 的条件是显然常量求值的，处于立即函数语境
```

诊断要求是有条件的：只有当"包含 E 的最内层声明"与"该变量的定义性声明"二者之一可从另一者到达时，才要求诊断（¶3.4–3.5）。这是为了照顾模块/多 TU 的情形：编译器在 E 处可能根本看不到变量的定义，无法知道它引用了立即函数。

!!! history "C++20/23 的做法"
    C++20 的 `consteval` 已经有"不能取立即函数的地址并带到运行期"的规则，但它是写在"permitted result of a constant expression"里的：常量表达式的结果不能是指向立即函数的指针。C++26 为了支持静态反射（[[P2996R13]]），把这个思想一般化为 consteval-only 值 / 立即对象，并允许 `constexpr auto b = plus1;` 这样的写法。在 C++23 中 `b` 的初始化是 ill-formed。

!!! impl "实现状态"
    本站测试的 Clang 23 仍按 C++23 规则拒绝 `constexpr auto b = plus1;` 和 `C<plus1>`（"pointer to a consteval declaration is not a constant expression"），也没有实现反射（`^^`）。

## 常量表达式的定义（¶4）

!!! std
    A core constant expression is a constant expression unless it is a prvalue whose result object has a constituent value that is an invalid pointer value or is indeterminate or erroneous.

    核心常量表达式是常量表达式，除非它是一个纯右值，其结果对象有某个组成值是无效指针值，或是不确定值或错误值。

这是 C++26 中**大幅简化**后的定义。只排除三种结果：

1. **无效指针值**（invalid pointer value，[[basic.compound]]）——指向已结束存储期的存储的指针。典型来源是返回局部变量的地址；
2. **不确定值**（indeterminate value，[[basic.indet]]）；
3. **错误值**（erroneous value）{{c++26}}——C++26 中未初始化自动变量的默认状态（[[P2795R5]]）。

```cpp
constexpr int* dang() { int x = 0; return &x; }   // 返回悬空指针
constexpr int* dp = dang();                       // error: 结果是无效指针值

struct S {
    int x;
    constexpr S() {}      // 不初始化 x
};
int f() {
    constexpr S s;        // error: s.x 的值是错误值（C++26）/不确定值（C++23）
    return 0;
}
```

注意 `dang()` 本身的**求值过程**是干净的——取局部变量地址、返回它，都不在黑名单上。问题出在结果：一个指向已死对象的指针被带出了求值。这就是为什么需要 ¶4 这条独立的"结果"规则。

### "允许的结果"去哪了？

C++23 及之前，¶4 的位置上是一长段"permitted result of a constant expression"：

- 泛左值常量表达式必须指代**静态存储期**对象（非临时对象，或满足约束的临时对象）或非立即函数；
- 纯右值常量表达式中，指针必须指向静态存储期对象（或越过其末尾）、非立即函数，或为空；引用成员同理……

C++26 把"必须是静态存储期"的约束移出了"常量表达式"的定义，改为对**变量**的约束：**constexpr-representable**（[[expr.const.init#3]]，来自 [[P2686]]）。理由是：

- "是不是常量表达式"本应只看表达式的值是否确定；
- "能不能存进一个 constexpr 变量"则取决于**变量在哪里**：函数内的 `constexpr int* p = &local;` 完全可以有确定的含义（只要 `p` 只在 `local` 存活的作用域内被使用）；而命名空间作用域的 constexpr 指针则必须指向静态存储期对象。

于是在 C++26 中，`&local` 是常量表达式；它能否初始化某个 constexpr 变量、能否作模板实参，由 [[expr.const.init]] 和 [[temp.arg.nontype]] 决定。注 1（¶5 之后）仍然提醒：**指代或指向未指定对象的泛左值核心常量表达式不是常量表达式**——这关系到 [[expr.const.core#9]] 的 constexpr-unknown 引用：`void f(int& r) { constexpr int* p = &r; }` 中 `&r` 指向的是一个"未指定对象"，不能作为常量表达式的结果。

## 立即常量表达式（¶5）

**立即常量表达式**（immediate constant expression）是满足下列之一的常量表达式：

- ¶5.1 指代立即对象或立即函数的泛左值；
- ¶5.2 结果对象（如果有）是立即对象的纯右值。

它是 [[expr.const.imm#2]] 判断"立即升级"（immediate-escalating）的依据之一：一个表达式如果是立即常量表达式，又不在立即函数语境中，它所在的函数就会被"升级"为立即函数。

```cpp
consteval int f() { return 42; }
consteval auto g() { return f; }            // 返回指向立即函数的指针
consteval int h(int (*p)() = g()) { return p(); }
constexpr int r = h();                      // OK：指针只在立即函数内部流转
constexpr auto e = g();                     // 标准例子标为 error（见下文讨论）
```

`r` 合法的原因：`h()` 是立即调用，默认实参 `g()` 的结果（指向 `f` 的指针）只在 `h` 内部被使用，最终结果是 `int`。

`e` 的情况值得 language lawyer 留意。标准例子把它判为 error，注释是"指向立即函数的指针不是常量表达式的允许结果"——这是 C++20/23 措辞（permitted result）的表述，而 C++26 的 ¶4 已经没有"允许的结果"这一概念了。按 C++26 的新框架推理：constexpr 变量的初始化器是显然常量求值的（[[expr.const.defns#1.6]]），其中的 `g()` 处于立即函数语境（[[expr.const.imm#1.2]]）；`e` 关联的对象是立即对象，而 ¶3.1 允许 constexpr 变量关联立即对象——这与 ¶3 的例子中 `constexpr auto b = plus1;` 被判为 OK 的推理完全相同。因此这个例子的注释与 ¶3 存在张力，很可能是反射提案改写 ¶1–¶3 后尚未同步清理的遗留。Clang 23 按旧规则拒绝 `e`（也拒绝 `b`）。

## 整型常量表达式（¶6–¶7）

¶6：**整型常量表达式**（integral constant expression）是整型或无作用域枚举类型的表达式，隐式转换为纯右值后，转换后的表达式是**核心**常量表达式。

注意是"核心"——整型值不可能是无效指针，所以核心常量表达式就够了。注 2 列出用途：位域长度（[[class.bit]]）、底层类型**未固定**的枚举的枚举量初值（[[dcl.enum]]）、对齐（`alignas`）。

¶7：如果需要整型常量表达式的地方给了一个**字面类类型**的表达式，它被**按语境隐式转换**为整型或无作用域枚举类型，选中的转换函数必须是 constexpr。转换函数有多个候选时可能产生歧义：

```cpp
struct A {
    constexpr A(int i) : val(i) { }
    constexpr operator int() const { return val; }
    constexpr operator long() const { return 42; }
private:
    int val;
};
constexpr A a = alignof(int);
alignas(a) int n;              // error: 歧义——int 还是 long？
struct B { int n : a; };       // error: 同上
```

"按语境隐式转换"（contextually implicitly converted，[[conv]]）是一种特殊的转换规则：在所有能转换到整型/无作用域枚举的非 explicit 转换函数中，如果恰好只有一个可行目标类型才成功。这里 `int` 与 `long` 两个目标都可行，歧义。

## 转换后的常量表达式（¶8）

**转换后的常量表达式**（converted constant expression）of type T：隐式转换为 T 的表达式，转换后的表达式是常量表达式，并且隐式转换序列**只包含**：

| 允许的转换 | 条目 | 说明 |
|---|---|---|
| 用户定义转换 | ¶8.1 | 转换函数/构造函数须为 constexpr |
| 左值到右值、数组到指针、函数到指针 | ¶8.2–8.4 | |
| 限定转换 | ¶8.5 | |
| 整型提升 | ¶8.6 | |
| 整型转换，**窄化除外** | ¶8.7 | 窄化的定义见 [[dcl.init.list]]：值不能被目标类型表示 |
| 浮点提升 | ¶8.8 | `float` → `double` |
| 浮点转换，**源值可被精确表示** | ¶8.9 | `double` 1.0 → `float` 可以，0.1 不行 |
| 从 `std::nullptr_t` 的空指针/空成员指针转换 | ¶8.10–8.11 | |
| 函数指针转换 | ¶8.12 | 去掉 `noexcept` |

并且引用绑定（如有）必须**直接绑定**（不能绑定到临时对象）。

明显被排除的有：**浮点与整型之间的转换**、**指针转换**（派生类指针到基类指针、到 `void*`）、**布尔转换**（指针到 `bool`）、窄化的整型转换。

注 3 列出用途：*new-expression* 中的数组维度、`case` 标签、底层类型**固定**的枚举的枚举量初值、数组边界、常量模板实参、*splice-specifier* {{c++26}}。

```cpp
template<char C>   struct TC {};
template<int N>    struct TI {};
template<bool B>   struct TB {};
template<double D> struct TD {};
template<const int& R> struct TR {};

TC<65>  c1;    // OK：int → char，65 可表示，不窄化
TC<300> c2;    // error: 300 不能被 char 表示（窄化）
TB<2>   b1;    // error: 2 → bool 是窄化
TI<2.0> i1;    // error: 浮点-整型转换不在列表中
TD<1>   d1;    // error: 整型-浮点转换不在列表中

long gl = 0;
TR<gl>  r1;    // error: 需要绑定到临时对象，不是直接绑定
```

为什么这么严格？因为这些上下文需要的是一个**精确**的值。模板实参决定类型的同一性：`TC<300>` 若悄悄变成 `TC<44>`，两个看似不同的实参会产生同一个类型，这是灾难性的。窄化的禁止与列表初始化（[[dcl.init.list]]）的理念一致。

```cpp
template<float F> struct TF {};
TF<1.0> f1;    // 按 ¶8.9：OK，1.0 可被 float 精确表示
TF<0.1> f2;    // error: 0.1 不能被 float 精确表示
```

!!! impl "Clang 的分歧"
    本站测试的 Clang 23 对 `TF<1.0>` 也报错（"conversion from 'double' to 'float' is not allowed in a converted constant expression"），即尚未实现 ¶8.9 的"可精确表示的浮点转换"。

!!! lawyer "`switch` 的 case 标签：先提升再转换"
    `case` 标签是"调整后的条件类型"（条件经整型提升后的类型）的转换后的常量表达式（[[stmt.switch]]）。所以：

    ```cpp
    void sw(unsigned char c) {
        switch (c) {          // 条件提升为 int
        case 1000: break;     // OK：1000 是 int，不窄化——这个 case 永远不会命中
        }
    }
    ```

    很多人以为 `case 1000` 对 `unsigned char` 会是窄化错误，其实不会。

### 用户定义转换

¶8.1 允许用户定义转换，这让字面类类型可以用作数组边界、`case` 标签等：

```cpp ok
struct Idx {
    int v;
    constexpr operator int() const { return v; }
};
constexpr Idx three{3};
int arr[three];                 // 转换为 std::size_t：Idx → int → size_t（非窄化，3 可表示）
void sw(int x) {
    switch (x) { case Idx{1}: break; }
}
```

## 按语境转换为 bool 的常量表达式（¶9）

**按语境转换为 bool 的常量表达式**（contextually converted constant expression of type bool）：按语境转换为 `bool`（[[conv]]）后是常量表达式，且转换序列只包含 ¶8 列出的转换。

目前使用它的有：`noexcept(expr)`（[[except.spec]]）和 `explicit(expr)`（[[dcl.fct.spec]]）。由于整型转换中的**窄化**被排除，`noexcept(2)` 是 ill-formed：

```cpp
struct S { explicit(2) S(int); };   // error: 2 → bool 窄化
void f() noexcept(2);               // error: 同上
static_assert(2);                   // OK：static_assert 不使用本定义
void g() { if constexpr (2) {} }    // OK：同上
```

!!! history "P1401：static_assert 与 if constexpr 允许窄化到 bool"
    C++17/20 中 `if constexpr` 的条件是"按语境转换为 bool 的常量表达式"，于是 `if constexpr (N % 4)`、`if constexpr (sizeof(T) & 1)` 都因窄化而 ill-formed，必须写 `!= 0`。C++23 的 [[P1401R5]] 让 `static_assert` 与 `if constexpr` 改为"按语境转换为 bool，转换后的表达式须为常量表达式"（[[dcl.pre#13]]、[[stmt.if#2]]），不再禁止窄化；但 `noexcept` 与 `explicit` 保持原状。主流编译器把这一改动作为缺陷修复应用到了较早的语言模式。

## 实现视角

!!! impl "常量表达式的'值'是符号性的"
    `constexpr int* p = &global;` 是常量表达式，但它的值不是一个数，而是"`global` 的地址"。编译器把它表达为一个**带重定位的符号引用**：目标文件里 `p` 的初始字节是 0，外加一条重定位记录让链接器/加载器填入 `global` 的最终地址（在 PIE/共享库中，这甚至要到加载时才能确定）。这就是为什么常量表达式中不能把指针转成整数（需要 `reinterpret_cast`，[[expr.const.core#2.16]]）——编译期根本不知道那个整数是多少。

## 陷阱

!!! pitfall "核心常量表达式 ≠ 常量表达式"
    `static_assert(dang() != nullptr);` 能否通过？`dang()` 的结果是无效指针值，但 `static_assert` 要求的是**比较结果** `bool` 是常量表达式。比较的过程中要对一个无效指针做相等比较——这在运行期是实现定义的行为（[[basic.compound]]），在常量求值中各家编译器的处理不一。不要写这种代码。

!!! pitfall "整型 `const` 变量的常量性依赖初始化器"
    `const int n = f();` 中 n 是否能用于数组边界，取决于 `f()` 是否是常量表达式。修改 f 的实现（比如加了一句日志）可能让远处的 `int a[n];` 突然变成 VLA（GCC/Clang 扩展）或编译错误。需要常量时写 `constexpr`。

## 思考题

!!! question "思考题 1"
    下列哪些模板实参合法？

    ```cpp
    template<unsigned N> struct U {};
    U<-1> u1;
    U<'a'> u2;
    U<sizeof(int)> u3;
    U<true> u4;
    ```

<details markdown="1">
<summary>答案</summary>

- `U<-1>`：error。`int` → `unsigned` 是整型转换，-1 不能被 `unsigned` 表示，是窄化。
- `U<'a'>`：OK。`char` → `unsigned`：先看是否整型提升（`char` 提升为 `int`，不是 `unsigned`），所以是整型转换；值 97 可表示，不窄化。
- `U<sizeof(int)>`：OK。`std::size_t` → `unsigned`，从更宽的类型转换，但**值**可表示时不算窄化（[[dcl.init.list]] 对常量表达式源值有特殊规定）。
- `U<true>`：OK。`bool` → `unsigned` 是整型转换（[[conv.integral#2]]：true 变为 1），不窄化。
</details>

!!! question "思考题 2"
    为什么转换后的常量表达式允许 `float → double`（浮点提升）却不允许 `int → double`？`int` 的值不也都能被 `double` 精确表示吗？

<details markdown="1">
<summary>答案</summary>

列表允许的转换都限定在"同一类别"之内（整型→整型、浮点→浮点、指针→指针的限定调整），跨类别的整型-浮点转换（[[conv.fpint]]）一律不在列表中——即使值能精确表示（32 位 `int` 的值都能被 `double` 表示）。这是一个简单、可预测的规则：模板实参 `TD<1>` 与 `TD<1.0>` 在拼写上就是不同的东西，标准宁可要求程序员显式写出 `1.0`。而浮点→浮点的转换在当前草案中允许，条件是"源值可被精确表示"（¶8.9）。
</details>

## 小结

| 名称 | 定义要点 | 主要使用者 |
|---|---|---|
| 常量表达式 | 核心常量表达式 + 结果无无效指针/不确定值/错误值 | 一般性的"要求常量"之处 |
| 立即常量表达式 | 结果是立即对象/立即函数 {{c++26}} | 立即升级判定 [[expr.const.imm]] |
| 整型常量表达式 | 整型/无作用域枚举，核心常量表达式；类类型须唯一 constexpr 转换 | 位域、未固定底层类型的枚举、`alignas` |
| 转换后的常量表达式 | 仅允许安全转换，禁窄化，引用须直接绑定 | 数组边界、`case`、NTTP、固定底层类型的枚举、*splice-specifier* |
| 按语境转换为 bool 的常量表达式 | 同上，目标为 `bool` | `noexcept(...)`、`explicit(...)` |
| （非本定义）`static_assert` / `if constexpr` | 按语境转 bool 后为常量表达式，允许窄化 | C++23 起 |
