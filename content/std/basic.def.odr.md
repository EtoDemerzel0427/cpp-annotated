---
title: 单一定义规则（ODR）
summary: 每个 TU 内每个可定义项至多一个定义；被 odr-use 的非 inline 函数和变量在整个程序中恰好一个定义；允许多处定义的项（类、inline、模板……）各处定义必须"相同"。本页还定义潜在求值、潜在结果集、odr-use 与 odr-usable。
status: done
papers: P0386R2, P1787R6, P1815R2, P2996R13
related: basic.def, basic.link, topics/value-categories, basic.pre, basic.scope, expr.const, dcl.inline, expr.prim.lambda.capture, module.reach, temp.point
tags: ODR, odr-use, 链接, inline, 模板, IFNDR
updated: 2026-10-17
---

**单一定义规则**（One-Definition Rule，ODR）是 C++ 分离编译模型的"宪法"。C++ 程序由许多翻译单元（TU）分别编译、再由链接器拼起来；链接器只看得到符号名，看不到类型和源码。ODR 就是让这种模型成立的契约：

1. **TU 内**：每个可定义项在一个 TU 里至多被定义一次（¶2）。违反时编译器**必须**报错。
2. **程序内，"恰好一次"**：被 **odr-use** 的非 inline 函数与变量，整个程序里必须恰好有一个定义（¶12、¶16.1）。少了（未定义引用）或多了（重复定义）都是 IFNDR——通常表现为链接错误，但标准不保证。
3. **程序内，"处处一致"**：允许在多个 TU 中定义的东西（类、枚举、inline 函数/变量、模板……），每一处定义必须"相同"——同样的记号序列、同样的名字查找结果、同样的重载决议……（¶16.3–¶16.12）。违反时 {{ifndr}}，编译器和链接器几乎都**不会**报错，后果是"随机挑一个定义"。

为了精确地说"被使用了所以需要定义"，本节还定义了一组被全标准引用的术语：**潜在求值**（potentially evaluated）、**潜在结果集**（set of potential results）、函数被**命名**（named）、**odr-use**、**odr-usable**、**定义域**（definition domain）。

阅读前需要：[[basic.pre]]（变量、局部实体）、[[basic.def]]（什么是定义）、[[basic.link]]（链接决定跨 TU 是否同一实体）。

## 可定义项（¶1）

¶1 下列东西称为**可定义项**（definable item）：

| ¶ | 可定义项 | 备注 |
|---|---|---|
| 1.1 | 类类型 | 包括 struct、union、闭包类型 |
| 1.2 | 枚举类型 | |
| 1.3 | 函数 | |
| 1.4 | 变量 | 按 [[basic.pre#7]]：不含非静态数据成员 |
| 1.5 | 模板化实体（templated entity） | 模板、模板中定义的实体、模板的成员……（[[temp.pre]]） |
| 1.6 | （某一作用域中某函数的）形参的默认实参 | |
| 1.7 | 默认模板实参 | |

不在清单中的：**命名空间**（所以可以反复打开）、**类型别名**、**概念**以外的各种 using、**宏**、**标号**。

默认实参被单独列为可定义项，是因为默认实参的"定义"是一段代码（在调用点才被代入求值），它本身就可能在不同 TU 里写得不一样——ODR 需要把它也纳入"必须一致"的范围（见 ¶16.11 与 ¶19 的例子）。"在给定作用域中"这个限定，是因为同一个函数在不同块作用域的重声明可以给出各自的默认实参（[[dcl.fct.default]]）。

## 每个 TU 至多一个定义（¶2）

¶2 任何翻译单元都不得包含任何可定义项的多于一个定义。

这是一条**需要诊断**的规则——编译器在一个 TU 内看得见所有定义，没有理由不报错。头文件保护（include guard / `#pragma once`）存在的意义就在这里：同一个头文件被同一 TU 间接包含两次，里面的类定义就出现了两次。

```cpp error
struct S { int a; };
struct S { int a; };      // error: S 在同一 TU 中被定义两次（哪怕完全相同）
inline void f() { }
inline void f() { }       // error: inline 也不能在同一 TU 定义两次
```

注意 ¶2 管的是**定义**，不是声明：`extern int x; extern int x;`、`void g(); void g();`、`typedef int I; typedef int I;` 都是合法的重复声明。

## 潜在求值（¶3 前半）

¶3 一个表达式或转换是**潜在求值**的（potentially evaluated），除非它是**不求值操作数**（unevaluated operand，[[expr.context]]）、不求值操作数的子表达式，或者这种上下文中的初始化/转换序列里的转换。

不求值操作数出现在：

| 上下文 | 例子 |
|---|---|
| `sizeof` 的表达式操作数 | `sizeof(f())` |
| `decltype` | `decltype(x + 1)` |
| `noexcept` 运算符 | `noexcept(g())` |
| `typeid` 的操作数，除非它是多态类类型的 glvalue | `typeid(expr)` |
| *requires-expression* 的 *requirement-body* 中的表达式 | `requires { t.foo(); }` |

"潜在"二字的含义：`if (false) g();` 中的 `g()` 仍是潜在求值的——它"可能"被求值，标准不做控制流分析。只有在**语法上**位于不求值操作数中的表达式才免于 odr-use。唯一的例外是**被丢弃的语句**（discarded statement，`if constexpr` 的未选分支，[[stmt.if]]），¶12、¶13 专门把它排除在外。

## 潜在结果集（¶3 后半）

ODR 要回答的核心问题是：**一个变量的名字出现在表达式里，是否需要这个变量真的有一块存储（有定义）？** 如果我们只是读它的值，而它的值在编译期就知道，那编译器直接把值代进去就行了；但如果我们要它的地址（取址、绑定引用），就必须有定义。

困难在于：名字往往不是"裸"出现的，而是被包在 `( )`、`?:`、`,`、`.`、`[]` 等运算里。`(c ? x : y) + 1` 读的是 `x` 或 `y` 的值，而 `&(c ? x : y)` 要的是地址。**潜在结果集**就是一个递归定义，用来"穿透"这些不改变对象身份的运算，找到最终被当作"那个对象本身"使用的 *id-expression*：

¶3 表达式 E 的潜在结果集：

| ¶ | E 的形式 | 潜在结果集 |
|---|---|---|
| 3.1 | *id-expression*，或 *splice-expression* {{c++26}} | {E} |
| 3.2 | 对数组操作数的下标运算 `a[i]` | `a` 的潜在结果集 |
| 3.3 | 类成员访问 `E1.E2`，E2 是非静态数据成员或直接基类关系 | `E1` 的潜在结果集 |
| 3.4 | 命名静态数据成员的类成员访问 `E1.s` | 指称该成员的 *id-expression* |
| 3.5 | 成员指针 `E1 .* E2` | `E1` 的潜在结果集 |
| 3.6 | 括号 `(E1)` | `E1` 的潜在结果集 |
| 3.7 | **glvalue** 条件表达式 `c ? E2 : E3` | `E2`、`E3` 潜在结果集之并 |
| 3.8 | 逗号表达式 `E1, E2` | `E2` 的潜在结果集 |
| 3.9 | 其他 | 空集 |

几个值得注意的地方：

- **函数调用、取址、算术运算**都落入 3.9：`f(x)` 的潜在结果集是空的，`x` 只在**实参** `x` 这个子表达式自己的潜在结果集里。判断 `x` 是否 odr-use，要看包含它的那个"最大的、仍以 `x` 为潜在结果"的表达式 E 被怎样使用——`f(x)` 中 E 就是实参 `x` 本身，然后看实参如何初始化形参（按值→左值到右值转换，按引用→绑定）。
- 3.2 只穿透**数组**操作数的下标：`p[i]`（`p` 是指针）不穿透，因为它等价于 `*(p+i)`，访问的是另一个对象。
- 3.3 只穿透**非静态数据成员**：`a.x` 读的是 `a` 的一个子对象，所以 `a` 是潜在结果；而 3.4 说 `a.s`（静态成员）的潜在结果是 `s` 本身，`a` 不在其中。
- 3.7 只对 **glvalue** 条件表达式成立：如果 `?:` 的结果是 prvalue（例如两边类型不同需要转换），潜在结果集为空，两个操作数各自已经做了左值到右值转换。
- 3.8 只取右操作数：`(x, y)` 的左操作数 `x` 是一个**丢弃值表达式**，单独判断。

标准的 Example 1（加注）：

```cpp
struct S { static const int x = 0; };
const int &f(const int &r);
extern bool b;
int n = b ? (1, S::x)           // S::x 是初始化器潜在结果集的元素，且只被读值 → 不 odr-use
          : f(S::x);            // 这个 S::x 不在初始化器的潜在结果集里（函数调用是 3.9）；
                                // 它作为实参绑定到 const int&，没有左值到右值转换 → odr-use
int o = [:^^S::x:];             // C++26：splice-expression 本身就是潜在结果
```

初始化器 `b ? (1, S::x) : f(S::x)` 是 prvalue 条件表达式吗？第二操作数 `(1, S::x)` 是 `const int` 左值，第三操作数 `f(S::x)` 也是 `const int` 左值——所以它是 glvalue 条件表达式，3.7 适用，潜在结果集 = {第一个 `S::x`} ∪ {}（函数调用为空）。

## 函数何时被"命名"（¶4）

¶4 函数被表达式或转换**命名**（named）的三种方式：

**¶4.1 重载决议选中**：函数是表达式或转换形成时所做的重载决议（[[basic.lookup]]、[[over.match]]、[[over.over]]）中**被选中的成员**，并且它**不是纯虚函数**，或者表达式是用**显式限定名**命名它、且不构成成员指针的 *id-expression*。

Note 2 列出了这条覆盖的场景：取函数地址、调用具名函数、运算符重载、用户定义转换、*new-expression* 的分配函数、非默认初始化（构造函数）。并且：

!!! std
    A constructor selected to copy or move an object of class type is considered to be named by an expression or conversion even if the call is actually elided by the implementation.

即：被**选中**用来拷贝/移动的构造函数，即使调用被省略（NRVO 等非强制省略），也算被命名，因而被 odr-use、必须有定义、必须可访问、不能是 deleted。注意这说的是"选中了拷贝/移动构造函数"的情形；C++17 起的**强制**省略（prvalue 直接初始化）根本不做重载决议去选拷贝构造函数，所以不命名它：

```cpp run ok
struct M { M() {} M(const M&) = delete; };
M make() { return M{}; }      // C++17：prvalue 直接初始化返回对象，不选择拷贝构造函数 → OK

struct N { N() {} N(const N&) {} };
N make2() { N n; return n; }  // NRVO 可能省略拷贝，但 N(const N&) 仍被选中 → 被命名、被 odr-use，
                              // 因此必须有定义（若它是 deleted 的，这里就是 error）
int main() { }
```

为什么纯虚函数要特殊处理？通过虚调用 `p->f()` 时，重载决议选中的是 `B::f`（纯虚），但运行时实际调用的是最终覆盖函数，根本不会调用 `B::f`——所以不应要求它有定义。可一旦写成限定名 `B::f()`，就是**非虚调用**，真的会调用 `B::f`，于是它被命名、被 odr-use：

```cpp
struct B { virtual void f() = 0; };          // 纯虚函数没有定义
struct D : B { void f() override { B::f(); } };  // 限定名调用：B::f 被 odr-use
int main() { D d; d.f(); }                   // 链接失败：B::f() 未定义（IFNDR）
```

而 `&B::f`（形成成员指针）虽然也是限定名，但成员指针调用依然是虚调用，所以被排除。

**¶4.2–¶4.3 释放函数**：类的释放函数（`operator delete`）被 *new-expression* 命名，如果它是被选中的分配函数的唯一匹配释放函数（用于构造函数抛异常时回收内存，[[expr.new]]）；被 *delete-expression* 命名，如果它是被选中的常规释放函数（[[expr.delete]]、[[class.free]]）。

## 变量何时被 odr-use（¶5）

¶5 先定义"命名"：变量被一个表达式**命名**，如果该表达式是指称（designate）它的 *id-expression* 或 *splice-expression*。

然后核心定义：变量 x 被出现在程序点 P 的**潜在求值**表达式 N 命名，则 x 被 N **odr-use**，**除非**：

- **¶5.1** x 是一个在 P 处**可用于常量表达式**（usable in constant expressions，[[expr.const.init]]）的**引用**；或
- **¶5.2** N 是某个表达式 E 的潜在结果集的元素，并且
    - **¶5.2.1** E 是一个**没有应用左值到右值转换**的**丢弃值表达式**（[[expr.context]]）；或
    - **¶5.2.2** x 是在 P 处可用于常量表达式的、**非 volatile** 对象，且**没有 mutable 子对象**，并且
        - **¶5.2.2.1** E 是命名**引用类型**非静态数据成员的类成员访问表达式，且对象表达式的类型不是 volatile 限定的；或
        - **¶5.2.2.2** 对 E 应用了**左值到右值转换**（[[conv.lval]]），且 E 的类型是非 volatile 的**非类**类型。

用一句话概括：**变量被潜在求值地命名就是 odr-use，除非我们"其实只需要它的值，而这个值编译期已知"，或者"根本没用到它"。**

### 为什么是这几条例外

**¶5.2.2.2——读常量的值**（值类别与左值到右值转换的背景见 [[topics/value-categories]]）。这是最常见的例外。`constexpr int N = 3;` 在 `int a[N];`、`return N + 1;`、`f(N)`（按值传参）中都只被读值（左值到右值转换），编译器直接把 3 代进去，`N` 不需要存储。条件"可用于常量表达式"保证了值在编译期已知；"非 volatile"保证读操作没有副作用；"非类类型"是因为对类类型应用左值到右值转换意味着调用拷贝构造函数——会把 `this` 绑定到对象上，需要地址；"没有 mutable 子对象"是因为 mutable 成员的值在运行期可能改变，编译期的值不可信。

**¶5.2.2.1——通过 constexpr 对象读引用成员**。`constexpr B b = {x};`（`B` 有引用成员 `int& r`），表达式 `b.r` 只需要知道 `b.r` 绑定到哪个对象——这在编译期就知道（`x`），不需要 `b` 本身的存储。

**¶5.1——可用于常量表达式的引用**。引用本身"是什么"（绑定到哪个对象）在编译期已知时，使用这个引用就无需引用本身的存储（引用通常实现为指针）。

**¶5.2.1——丢弃值表达式**。`x;`、`(void)x;` 根本没有读取 `x`，也没有取地址，自然不需要定义。但对 volatile glvalue，丢弃值表达式在某些形式下**会**应用左值到右值转换（[[expr.context#2]]），因而 odr-use。

这些例外都要求 N 在 E 的**潜在结果集**里——这就是潜在结果集存在的理由：`(c ? x : y)` 被读值时，`x`、`y` 都只是被读值；而 `&(c ? x : y)` 中取址运算的潜在结果集是空集，`c ? x : y` 作为取址的操作数既没有左值到右值转换也不是丢弃值表达式，于是 `x`、`y` 都被 odr-use。

### 边界例子

```cpp run ok
extern int e;               // 从未定义
int main() {
  e;                        // 丢弃值表达式，无左值到右值转换：不 odr-use（¶5.2.1）
  (void)e;                  // 同上
  (void)sizeof(e);          // 不求值操作数：根本不是潜在求值
  decltype(e) k = 0;        // 同上
  return k;
}                           // 链接成功：程序中从未 odr-use e
```

```cpp
extern volatile int ev;     // 从未定义
int main() { ev; }          // volatile 左值的丢弃值表达式：应用左值到右值转换 → odr-use
                            // 链接失败："_ev" 未定义
```

静态数据成员的经典例子（C++17 前后都一样适用，因为 `static const` **不是** inline）：

```cpp
struct S { static const int x = 0; };   // 类内只是声明（[basic.def]/2.3）
const int& f(const int& r) { return r; }
int g(int v) { return v; }
int main(int argc, char**) {
  bool b = argc > 1;
  int n = b ? (1, S::x) : S::x;  // 只读值：不 odr-use
  int a = g(S::x);               // 按值传参，左值到右值转换：不 odr-use
  const int& r = f(S::x);        // 绑定引用：odr-use → 需要类外定义 const int S::x;
  return n + a + r;              // 本机链接失败："S::x" 未定义
}
```

!!! note "关于标准的 Example 2"
    标准在 ¶5 给出的 Example 2 用**自动存储期**的 `constexpr` 对象演示 ¶5.2.2.1：`constexpr A a = {1}; constexpr const volatile A& r = a;`、`constexpr B b1 = {x};`（`x` 是局部变量）等。这些写法依赖 C++26 放宽的规则——`constexpr` 引用/指针可以指向**同一函数内**的自动变量（[[expr.const.init]] 中的 *constexpr-referenceable*；对应提案 P2686 "constexpr structured bindings and references to constexpr variables"）。截至写作时，本机 Clang 23 尚未实现这一点，会对 `r`、`b1`、`b2` 的初始化报"must be initialized by a constant expression"。

    该例子要说明的道理是：`f(cond ? a.x : r.x)` 中 `a.x` 和 `r.x` 只被读值，不 odr-use `a` 和 `r`（`r` 是可用于常量表达式的引用，¶5.1）；`g(cond ? b1.r : b2.r)` 只是通过引用成员拿到 `x`/`y`，不 odr-use `b1`/`b2`（¶5.2.2.1）；`((cond ? x : y), 0)` 中左操作数是丢弃值表达式（¶5.2.1）。而最后的 lambda 中 `return b1.r;` 之所以是 error，是因为在 lambda 内部 `b1.r` 所引用的 `x` 不再是 constexpr-referenceable 的，`b1` 在那里**不可用于常量表达式**，于是例外不适用、`b1` 被 odr-use，而它在 lambda 里不是 odr-usable 的（¶10）。

### 可用于常量表达式的变量

¶5 的例外依赖 [[expr.const.init]] 的"可用于常量表达式"。简要地说，变量 V 在 P 处可用于常量表达式，需要：V 是 **constexpr**，或者是**引用**或**非 volatile const 限定的整型/枚举类型**（合称 *potentially-constant*）；V 被**常量初始化**；V 的初始化声明在 P 处可达；以及一些关于 TU-local 值的条件。

所以 `const int m = 4;` 可以不捕获就在 lambda 里读，`const double d = 1.5;` 就不行（`double` 不是整型，`d` 不是 potentially-constant，读它的值就是 odr-use）：

```cpp error
void k() {
  constexpr int n = 3;
  const int m = 4;               // const 整型 + 常量初始化：可用于常量表达式
  const double d = 1.5;          // 非整型的 const：不可用于常量表达式
  auto l1 = [] { return n + m; };            // OK：只读值，不 odr-use，无需捕获
  auto l2 = [] { int a[m]; return sizeof a; }; // OK
  auto l3 = [] { return &n; };               // error: 取址 odr-use n，而 n 未被捕获
  auto l4 = [] { return d; };                // error: 读 d 也是 odr-use
}
```

## 结构化绑定与 `*this`（¶6–¶7）

¶6 结构化绑定被表达式**命名**，如果该表达式是指称它的 *id-expression* 或 *splice-expression*。结构化绑定只要被潜在求值的表达式命名就是 odr-use——**没有**变量那样的常量例外。

为什么？结构化绑定不是变量，它是"某个无名变量 `e` 的某个子对象/某个引用"的别名（[[dcl.struct.bind]]）。规则的简化选择是：用到它就算 odr-use，从而在 lambda 中使用它就必须捕获（C++20 起可以捕获结构化绑定）。

¶7 当 `this` 作为潜在求值表达式出现时，`*this` 被 odr-use——包括隐式出现：在成员函数中写 `m`（非静态成员）会被隐式变换成 `(*this).m`（[[expr.prim.id.general]]），这同样 odr-use `*this`。结合 ¶10，这就是 lambda 里访问成员需要捕获 `this`（或 `*this`）的规范依据。

```cpp error
struct W {
  int m = 0;
  auto get() {
    return [] { return m; };     // error: 隐式的 this->m odr-use 了 *this，但 lambda 未捕获 this
  }
  auto ok() {
    return [this] { return m; }; // OK
  }
};
```

## 函数何时被 odr-use（¶8–¶9）

¶8：

- **非纯虚的虚成员函数总是被 odr-use**——无论程序是否调用它。原因是实现层面的：vtable 必须填入每个虚函数的地址，类的构造函数会引用 vtable。标准用"无条件 odr-use"把这个实现需求变成语言规则，于是"声明了虚函数却不定义"就是 IFNDR。实践中这表现为著名的 `undefined reference to vtable for X` 或 `undefined reference to X::f()`。
- 函数被潜在求值的表达式或转换**命名**（¶4），就是被 odr-use。
- 类的**非 placement** 分配/释放函数被该类构造函数的**定义** odr-use；非 placement 释放函数被该类析构函数的定义 odr-use，或者被虚析构函数定义处的查找选中而 odr-use（[[class.dtor]]）。脚注 13 解释：实现不必真的在构造/析构函数里调用分配/释放函数，但这是被允许的实现技术——例如 Itanium ABI 的"删除析构函数"（deleting destructor，D0）变体在虚析构函数中调用 `operator delete`，使 `delete p` 通过 vtable 找到正确的释放函数。

¶9：

- 类中的赋值运算符被另一个类**隐式定义**的拷贝/移动赋值函数 odr-use（成员逐个赋值时调用，[[class.copy.assign]]）；
- 构造函数按 [[dcl.init]] 的规定被 odr-use；
- 析构函数在**潜在调用**（potentially invoked）时被 odr-use——例如自动变量的作用域结束、临时对象销毁、*new-expression* 中构造抛异常时清理已构造的子对象等（[[class.dtor]]）。

```cpp
struct S { ~S(); };            // 声明但不定义
void f(bool c) { if (c) { S s; } }
int main() { f(false); }       // ~S 被潜在调用 → odr-use → 链接失败（即使 f(false) 永远走不到那里）

struct B { virtual void v(); virtual void p() = 0; };
struct D : B { void p() override { } };
int g() { D d; return 0; }     // B::v 非纯虚 → 无条件 odr-use → 链接失败："B::v()" 被 D 的 vtable 引用
```

## odr-usable：局部实体能在哪里用（¶10–¶11）

¶10 局部实体（[[basic.pre#9]]：自动变量、相应的结构化绑定、结果绑定、`*this`）在某个作用域中是 **odr-usable** 的，当：

- **¶10.1**：如果它是 `*this`，则必须存在一个外围的类作用域或非 lambda 的函数形参作用域，并且如果最内层的这种作用域是函数形参作用域，它对应的必须是**非静态成员函数**；（不是 `*this` 的局部实体无此要求）
- **¶10.2**：从该实体被引入之处到该作用域之间的**每一个介于其间的作用域**（intervening scope，[[basic.scope.scope#1]]）都是下列之一：
    - 块作用域；
    - 契约断言作用域 {{c++26}}（[[basic.scope.contract]]）；
    - *lambda-expression* 或 *requires-expression* 的函数形参作用域；
    - *lambda-expression* 的 lambda 作用域，且该 lambda 有**命名这个实体的 simple-capture** 或有 **capture-default**，并且该 lambda 的块作用域（函数体）也是介于其间的作用域。

（`*this` 被视为在最内层的外围类作用域或非 lambda 函数形参作用域中引入。）

如果一个局部实体在它**不是** odr-usable 的作用域里被 **odr-use**，程序非良构。

!!! std
    If a local entity is odr-used in a scope in which it is not odr-usable, the program is ill-formed.

直觉：局部实体属于"某一次函数调用"。只有块作用域、契约断言、lambda 形参列表这种"仍在同一次调用里"的作用域可以透明穿越；**局部类的成员函数**、**嵌套函数声明的形参作用域**都是"另一个函数"，跨不过去；**lambda** 是一扇门，只有声明了捕获（或捕获默认）才打开，而且只有 lambda **函数体**里才算"进了门"——lambda 的形参默认实参在门外。

标准 Example 3（加注）：

```cpp error
void f(int n) {
  [] { n = 1; };                // error: lambda 作用域没有捕获 n
  struct A {
    void f() { n = 2; }         // error: A::f 的函数形参作用域介于其间
  };
  void g(int = n);              // error: g 的函数形参作用域介于其间
  [=](int k = n) {};            // error: 默认实参不在 lambda 的块作用域内，capture-default 帮不上忙
  [&] { [n]{ return n; }; };    // OK: 外层 [&] 有 capture-default，内层显式捕获 n
}
```

注意这些错误都需要 **odr-use** 才触发。如果只是读一个可用于常量表达式的变量的值（¶5 的例外），就根本不是 odr-use，odr-usable 与否无关紧要——这就是 `constexpr int n = 3; [] { return n; }` 合法的原因。

¶11（例）把这个推理推到模板实例化中：

```cpp
void g() {
  constexpr int x = 1;
  auto lambda = [] <typename T, int = ((T)x, 0)> {};    // OK
  lambda.operator()<int, 1>();          // OK：显式给出第二个实参，默认模板实参根本不被使用
  lambda.operator()<int>();             // OK：(int)x 是读值，不 odr-use x
  lambda.operator()<const int&>();      // error: (const int&)x 绑定引用，odr-use x，而此处 x 不是 odr-usable
}

void h() {
  constexpr int x = 1;
  auto lambda = [] <typename T> { (T)x; };      // OK
  lambda.operator()<int>();             // OK：读值
  lambda.operator()<void>();            // OK：(void)x 是丢弃值表达式（¶5.2.1）
  lambda.operator()<const int&>();      // error: odr-use x
}
```

关键点：是否 odr-use 在**实例化时**才能确定（取决于 `T`），所以同一个泛型 lambda 的不同特化可以一个合法一个非法。

!!! impl "Clang 与 Example 4"
    截至写作时，本机 Clang 23 对上面 `g()` 和 `h()` 中的 `<int>`、`<void>` 两种特化也报"variable 'x' cannot be implicitly captured in a lambda with no capture-default specified"——它在依赖于模板形参的转换上过早地认定了 odr-use。按标准，只有 `<const int&>` 那行应当出错。普通的非依赖情形（`[] { return x; }`）Clang 处理正确。

## 定义必须存在：odr-use 的后果（¶12）

¶12 每个程序必须为在其中被 odr-use（被丢弃语句中的除外）的每个**函数或变量**至少包含一个定义；**不要求诊断**。定义可以显式写在程序中、来自标准库或用户库，或（适用时）被隐式定义（特殊成员函数）。

为什么是 {{ifndr}}？因为定义可能在**任何**其他 TU 或库里，编译器看不到全局；链接器通常能发现（"未定义符号"），但标准不想把"必须由链接器诊断"写进语言——而且有些情况链接器也发现不了：

```cpp run ok
void never_defined();
template<class T> void h() {
  if constexpr (sizeof(T) > 100) never_defined();  // 被丢弃的语句：不算 odr-use（¶12 明文排除）
}
int main() { h<int>(); }
```

```cpp
void never_defined();
int main() { if (false) never_defined(); }
// 按标准：never_defined 被 odr-use 却没有定义 → IFNDR。
// 实际：Clang 即使在 -O0 下也把 if (false) 分支删掉了，链接成功——IFNDR 的典型表现："看起来没事"。
```

标准 Example 5 展示了一个**编译器能看出来**的情形：

```cpp error
auto f() {
  struct A {};
  return A{};
}
decltype(f()) g();   // g 返回局部类 A
auto x = g();        // odr-use g，但 g 没有定义……
```

`g` 被 odr-use 但本 TU 没有定义，而且**也不可能**在其他 TU 定义——它的返回类型是 `f` 内的局部类 `A`，在别的 TU 里根本写不出这个类型。所以这个程序必然违反 ¶12。Clang 会直接诊断（"function 'g' is used but not defined in this translation unit, and cannot be defined in any other translation unit because its type does not have linkage"）。

## 定义域与 inline（¶13）

¶13 **定义域**（definition domain）是一个 *private-module-fragment*，或者一个 TU 除去其 *private-module-fragment*（如果有）之外的部分。inline 函数或变量的定义，必须从**每个**在其中 odr-use 它（被丢弃语句中的除外）的定义域的**末尾**可达。

这就是"inline 函数必须在每个使用它的 TU 中都有定义"的现代表述，也是**头文件库必须把 inline 函数的实现写在头文件里**的规范依据。为什么要求每个 TU 都有？因为 inline 的本意就是允许编译器在调用点内联展开——它必须能看到函数体。注意是"从定义域**末尾**可达"：调用可以出现在定义之前（Note 3 of [[dcl.inline]]），只要在 TU 结束前能看到定义就行。

模块的 *private-module-fragment*（`module :private;`）自成一个定义域，它之后的内容对导入者不可达。如果 `module :private;` 之前的某个 inline 函数调用了一个只在私有片段中定义的 inline 函数，那么在"私有片段之前"这个定义域里后者被 odr-use，但从该定义域末尾看不到它的定义——违反本条。（另见 [[dcl.inline]]：附属于具名模块的 inline 函数/变量在哪个定义域中声明，就必须在那个定义域中定义。）

## 类的定义必须可达（¶14）

¶14 在每个**需要类类型完整**的上下文中，类的定义必须可达。Example 6：只用作指针的类不需要定义——

```cpp run ok
struct X;          // 声明 X 为结构体类型
struct X* x1;      // 形成指针：不需要 X 完整
X* x2;
int main() { }
```

Note 3 列出了需要 `T` 完整的场合（不具规范性，规范要求分散在各处）：定义 `T` 类型的对象；声明 `T` 类型的非静态数据成员；`new T` 或数组元素类型为 `T`；对 `T` 类型 glvalue 做左值到右值转换；转换到 `T`；把非空指针常量、非 `void*` 的表达式转换为 `T*` 或 `T&`（标准转换、`dynamic_cast`、`static_cast`）；对 `T` 类型表达式用成员访问运算符；`sizeof`/`typeid`/`alignof` 作用于 `T`；定义或调用返回/形参类型为 `T` 的函数；定义以 `T` 为基类的类；对 `T` 类型左值赋值；*exception-declaration* 的类型为 `T`、`T&` 或 `T*`。

这里说的是"**可达**"（reachable），不是"在本 TU 中"：模块中一个类的定义可以从导入的模块接口单元中可达，而不必重复写出。

## 注入声明的一致性（¶15）{{c++26}}

¶15 如果一个可定义项 D 在某 TU 中由一个**注入声明**（injected declaration，[[expr.const.reflect]]）X 定义，而另一个 TU 也包含 D 的定义，那么那个定义也必须是注入声明，并且**特征序列**（characteristic sequence）与 X 相同；只有当 D 附属于具名模块、且之前的定义在后一个定义处可达时才要求诊断。

背景：C++26 静态反射允许在常量求值中**生成**定义，例如 `consteval { std::meta::define_aggregate(^^S, {...}); }` 为不完整类 `S` 注入一个类定义。这样的定义没有对应的源码记号序列，¶16.4 的"相同记号序列"无从谈起，于是标准改用"特征序列"（生成它的那些反射值，例如数据成员描述的列表）来判断两个注入定义是否相同。在 C++23 及之前不存在注入声明。

## 多个 TU 中的定义（¶16）

¶16 是 ODR 的主体。对于在多个 TU 中有定义的其他可定义项 D：

- **¶16.1** 如果 D 是**非 inline、非模板化**的函数或变量，程序非良构——它们在整个程序中**至多一个**定义（结合 ¶12 的"至少一个"，被 odr-use 时就是**恰好一个**）；
- **¶16.2** 如果各 TU 中的定义不满足下面的要求，程序非良构；

**只有**当可定义项附属于**具名模块**、且在后一个定义处之前的定义可达时，才要求诊断。否则——也就是传统的头文件世界——全部是 {{ifndr}}。

那么，**哪些**东西可以在多个 TU 中各有一个定义？凡是不属于 ¶16.1 的可定义项：类类型、枚举类型、inline 函数、inline 变量、模板化实体（函数模板、类模板及其成员、模板中定义的实体……）、默认实参、默认模板实参。这正是"可以写在头文件里"的东西的完整清单。

!!! summary "定义数量一览"
    | 可定义项 | 每个 TU | 整个程序 |
    |---|---|---|
    | 非 inline 非模板化函数、变量 | ≤ 1 | 被 odr-use 则恰好 1；否则 ≤ 1 |
    | inline 函数、inline 变量 | ≤ 1；在 odr-use 它的每个定义域末尾可达 | 每个 TU 可各有一个，必须"相同" |
    | 类、枚举 | ≤ 1；在需要完整类型处可达 | 每个 TU 可各有一个，必须"相同" |
    | 模板化实体（含其成员） | ≤ 1 | 每个 TU 可各有一个，必须"相同" |
    | 默认实参、默认模板实参 | ≤ 1（在给定作用域） | 必须"相同"（通过 ¶16.11） |

接下来是"相同"的具体要求。给定这样的 D，对 D 的**所有**定义（如果 D 是**无名枚举**，则是在任一程序点可达的所有定义）：

### ¶16.3 不得附属于具名模块

每个这样的定义都不得附属于具名模块（[[module.unit]]）。换句话说，**具名模块中的实体只能有一个定义**——模块的接口单元编译一次，导入者通过可达性看到它的定义，不需要（也不允许）在别的 TU 中重复定义。只有附属于**全局模块**的实体（传统头文件代码、*global-module-fragment* 中的代码）才享受"多处定义、要求一致"的待遇。

### ¶16.4 相同的记号序列

每个定义必须由**相同的记号序列**组成；闭包类型的定义视为由对应 *lambda-expression* 的记号序列组成。

"记号"是翻译阶段 7 的记号（[[lex.phases]]），即预处理之后。所以：

- 空白、注释的差异无所谓；
- **宏展开后的结果**不同就违反——同一个头文件在两个 TU 里用不同的 `-D` 选项编译，就可能产生不同的记号序列；
- 记号相同但**含义**不同也不行，那由 ¶16.5 管。

### ¶16.5 名字查找得到相同的实体

每个定义中，对应的名字按 [[basic.lookup]] 查找后（经过重载决议、偏特化匹配）必须**指代相同的实体**。例外：

- **¶16.5.1** 名字可以指代一个**内部链接或无链接**的非 volatile const 对象，只要该对象在所有定义中类型相同（字面类型）、用常量表达式初始化、在任何定义中**都没有被 odr-use**、且值相同；
- **¶16.5.2** 名字可以指代一个内部链接或无链接、用常量表达式初始化的引用，只要它在所有定义中引用同一个对象或函数。

这条例外极其重要，因为它让下面这种**最常见的头文件写法**合法：

```cpp title="config.h"
const int kBufSize = 4096;            // 命名空间作用域 const：内部链接，每个 TU 一个独立对象
inline int buffer_bytes() {           // inline：每个 TU 一个定义
  return kBufSize * 2;                // 名字 kBufSize 在各 TU 中指代"不同"的实体！
}                                     // 但它满足 ¶16.5.1：只读值、常量初始化、值相同 → OK
inline const int* buffer_addr() {
  return &kBufSize;                   // 取址 → odr-use → 例外不适用 → 违反 ODR（IFNDR）
}
```

如果没有 ¶16.5.1，任何在 inline 函数里使用头文件中 `const` 常量的代码都会违反 ODR。`buffer_addr` 在不同 TU 中返回不同的地址，链接器却只会保留其中一个定义——取决于链接顺序，结果不可预测。修复方法：用 `inline constexpr int kBufSize = 4096;`（C++17 inline 变量，外部链接，全程序一个对象）。

!!! tip "为什么头文件常量推荐 `inline constexpr`"
    命名空间作用域的 `constexpr` 变量隐含 `const`，因而有**内部链接**（[[basic.link#3]]）。每个包含该头文件的 TU 都有一个副本（不被 odr-use 时通常会被优化掉）。加上 `inline` 后它获得外部链接，全程序只有一个对象，取址也安全、在 inline 函数里 odr-use 也不违反 ODR。这正是 C++17 标准库把 `std::is_same_v` 之类定义为 `inline constexpr` 变量模板的原因之一。

### ¶16.6 相同的闭包类型

每个定义中（D 的默认实参和默认模板实参**之内的**除外），对应的 *lambda-expression* 必须有**相同的闭包类型**。

正常情况下，每个 lambda 表达式都有一个独一无二的闭包类型；但 inline 函数在多个 TU 中的定义被视为"同一个定义"（¶18），其中的 lambda 也必须是"同一个类型"——这要求实现在 ABI 层面给它们相同的修饰名（Itanium ABI 用"所在实体 + lambda 序号"来编码，如 `f()::{lambda()#1}`）。默认实参中的 lambda 被排除，原因见 ¶18–¶19。

### ¶16.7 相同的语言链接

对应的实体必须有相同的语言链接（`extern "C"` vs `extern "C++"`，[[dcl.link]]）。

### ¶16.8 常量初始化的一致性

具有静态或线程存储期的 const 对象，如果在某个定义中是常量初始化的，就必须在所有定义中都是常量初始化的。原因：常量初始化与动态初始化决定了对象是在编译期被写进镜像，还是在运行期由初始化代码填入——两种 TU 混在一起，初始化顺序和值都会出问题。

### ¶16.9 显然常量求值的表达式值相同

对应的、非值依赖的**显然常量求值**表达式（manifestly constant-evaluated，[[expr.const]]）必须有相同的值。例如数组边界、`static_assert`、`if constexpr` 的条件、模板实参。这条防止"记号相同、名字查找相同，但常量值不同"的情况——例如依赖 `std::is_constant_evaluated()` 或实现定义的值。

### ¶16.10 隐式调用的函数相同

每个定义中，引用的**重载运算符**、对**转换函数**、**构造函数**、`operator new`、`operator delete` 的**隐式调用**都必须指向同一个函数。这些调用在源码中没有名字（不受 ¶16.5 约束），所以要单独规定。经典违反方式：在一个 TU 里某个运算符重载可见、在另一个 TU 里不可见，导致同一段 inline 代码选中不同的函数。

```cpp title="a.cpp"
struct P { int v; };
bool operator==(P, long);
inline bool is_zero(P p) { return p == 0; }   // 选中 operator==(P, long)
```

```cpp title="b.cpp"
struct P { int v; };
bool operator==(P, long);
bool operator==(P, int);                      // 只有 b.cpp 声明了这个更好的重载
inline bool is_zero(P p) { return p == 0; }   // 选中 operator==(P, int)
// is_zero 的两个定义记号相同，但 == 引用的重载运算符不同：违反 ¶16.10，IFNDR
```

### ¶16.11 默认实参递归纳入

被（隐式或显式）函数调用**使用**的默认实参、被 *template-id*/*simple-template-id*/*splice-specialization-specifier* 使用的默认模板实参，视为其记号序列出现在 D 的定义中——即它们也要（递归地）满足本段的所有要求。

为什么？默认实参是在**调用点**代入的。`inline void f() { g(); }`，若 `g` 的声明是 `void g(int = N);`，那么 `f` 的定义实际上包含了 `g(N)`。如果两个 TU 中 `g` 的默认实参不同，`f` 的两个定义就做了不同的事——所以要把默认实参"展开"进来检查。

### ¶16.12 反射表达式的值等价 {{c++26}}

对应的 *reflect-expression*（`^^x`）必须计算出**等价的值**（[[expr.eq]]）。`^^x` 的值是"表示 x 的反射"，如果两个 TU 中 `x` 指代不同的实体，反射值就不同，进而由反射驱动的代码生成也会不同。

## 隐式定义与模板的额外要求（¶17）

¶17 为了上面的要求：

**¶17.1** 如果 D 是具有隐式声明的构造函数的类，就当作该构造函数在每个 odr-use 它的 TU 中都被隐式定义，并且每个 TU 中的隐式定义必须为 D 的子对象调用**相同的构造函数**。Example 7：

```cpp title="tu1.cpp"
struct X {
  X(int, int);
  X(int, int, int);
};
X::X(int, int = 0) { }        // 在 tu1 中，X(int, int) 的第二个形参有默认实参
class D {
  X x = 0;                    // 默认成员初始化器 X x = 0 → 选 X(int, int)
};
D d1;                         // D() 的隐式定义调用 X(int, int)
```

```cpp title="tu2.cpp"
struct X {
  X(int, int);
  X(int, int, int);
};
X::X(int, int = 0, int = 0) { }  // 在 tu2 中，X(int, int, int) 的后两个形参有默认实参
class D {
  X x = 0;                    // 这次选 X(int, int, int)
};
D d2;                         // D() 的隐式定义调用 X(int, int, int) —— 违反 ODR
```

`D` 的两个定义记号完全相同，名字 `X` 指代同一个类，但由于类外定义追加的默认实参不同，`X x = 0` 的重载决议结果不同。类 `D` 本身的记号序列看不出这个差别——这就是要单独规定 ¶17.1 的原因。

**¶17.2** 对**默认的三路比较运算符**（`operator<=> = default`，[[class.spaceship]]）同理：视为在每个 odr-use 它的 TU 中隐式定义，各 TU 中必须为每个子对象调用相同的比较运算符。

**¶17.3** 如果 D 是在多个 TU 中定义的**模板**，要求既适用于模板定义中来自外围作用域的名字，也适用于**实例化点**处的**依赖名**（[[temp.dep]]、[[temp.point]]）。这意味着：模板特化 `f<T>` 的语义取决于实例化点可见的东西（ADL 找到的函数、显式特化……），如果不同 TU 中在实例化点看到的东西不同，就违反 ODR。显式特化必须在第一次使用之前声明（[[temp.expl.spec]]），否则同一特化在不同 TU 中可能分别用主模板和特化，这是 ODR 违规的常见来源。

## 视为"同一个实体、同一个定义"（¶18–¶19）

¶18 上述要求同样适用于在 D 的每个定义**内部**定义的对应实体（包括 lambda 的闭包类型，但不包括在 D 或"不是在 D 内部定义的实体"的默认实参/默认模板实参中定义的实体）。对每个这样的实体以及 D 本身，**行为如同只有一个实体、只有一个定义**，包括在把这些要求应用于其他实体时。

这句话的实际后果非常重要：

- **inline 函数里的 `static` 局部变量在整个程序里只有一个**。`inline int& counter() { static int c = 0; return c; }` 被 10 个 TU 包含，所有 TU 共享同一个 `c`。这正是 Meyers 单例能写在头文件里的原因。
- inline 函数中的字符串字面量、lambda 闭包类型、局部类，在各 TU 中都是"同一个"。
- `&f` 在各 TU 中得到相同的地址（对 inline 函数）。

Note 4 补充：实体仍然在多个 TU 中被**声明**，[[basic.link]] 依然适用于这些声明。特别是，出现在 D 的**类型**中的 lambda 可能导致不同声明有不同的类型，而出现在 D 的**默认实参**中的 lambda 在不同 TU 中仍可能是不同的类型。

¶19 Example 8：

```cpp
inline void f(bool cond, void (*p)()) {
  if (cond) f(false, []{});
}
inline void g(bool cond, void (*p)() = []{}) {
  if (cond) g(false);
}
struct X {
  void h(bool cond, void (*p)() = []{}) {
    if (cond) h(false);
  }
};
```

- `f`：lambda 在 `f` 的函数体内。`f` 的定义出现在多个 TU 时，行为如同只有一个 `f`，函数体里的 lambda 也是同一个闭包类型（¶16.6）。✔
- `g`：lambda 在 `g` 的**默认实参**里，而 `g` 的函数体通过 `g(false)` **使用**了这个默认实参。¶16.11 把默认实参的记号视为出现在 `g` 的定义中；但 ¶16.6 和 ¶18 都把"D 自己的默认实参里的 lambda"排除在"同一闭包类型"之外——每个 TU 中这个 lambda 是**不同**的闭包类型。于是 `g` 的各个定义使用了不同的实体，违反 ODR，{{ifndr}}。
- `X::h`：lambda 在 `X::h` 的默认实参里，但这个默认实参是在**类 X 的定义之内**。对 D = `X` 而言，`X::h` 是"在 D 内部定义的实体"，其默认实参中的 lambda 是"D 内部定义的实体"（排除只针对 D 自己的、或不在 D 内定义的实体的默认实参），所以各 TU 中是同一个闭包类型。✔

这个例子展示了 ¶18 排除条款的精细之处：排除的是"**D 本身**的默认实参"和"**不在 D 内部定义的实体**的默认实参"中的实体，所以对类 `X` 来说，成员函数默认实参里的 lambda 被视为同一个；而对独立的 inline 函数 `g` 来说，它自己的默认实参里的 lambda 不是。

## 无名枚举（¶20）

¶20 如果在程序的任一点，同一作用域中有多于一个**可达的无名枚举定义**，它们的第一个枚举项名字相同，并且都没有用于链接的 typedef 名，那么这些无名枚举类型必须是**同一个类型**；不要求诊断。

背景：`enum { red, green };` 这种无名枚举没有名字，按 [[basic.link]]，它的"用于链接的名字"是它的**第一个枚举项**（[[dcl.enum]]）。在头文件里写这样的枚举，被多个 TU 包含后，各 TU 的定义靠"第一个枚举项"来认定为同一个实体。模块使得同一 TU 中可能同时可达多个这样的定义（例如来自不同的头单元），¶20 要求它们被合并为同一类型。

## 实现视角

!!! impl "链接器如何\"合并\"多份定义：COMDAT 与弱符号"
    inline 函数、inline 变量、模板实例化、vtable、typeinfo、inline 函数中的静态局部变量及其守卫变量——这些"允许在多个 TU 中出现"的东西在目标文件中被标记为**可合并**的：

    - **ELF**（Linux）：放在 COMDAT 组中（`.group` 节，`.text._Z7versionv` 这种独立节），链接器对同名组只保留一份；符号通常是 `W`（weak）。
    - **Mach-O**（macOS）：标记为 weak definition。本机 `nm -m` 对 `inline int version()` 的输出是 `weak external __Z7versionv`。
    - **PE/COFF**（Windows）：COMDAT 节，选择策略通常是 "any"（任选一个）。

    Itanium C++ ABI 把这类发射方式称为 **vague linkage**。关键点：**链接器只按符号名合并，从不比较内容**——它假定你遵守了 ODR。这就是 ODR 违规（¶16.2）几乎永远不会被诊断的根本原因。

!!! impl "亲手制造一次 ODR 违规"
    ```cpp title="a.cpp"
    inline int version() { return 1; }
    int from_a() { return version(); }
    ```
    ```cpp title="b.cpp"
    inline int version() { return 2; }   // 同名 inline 函数，定义不同：违反 ODR
    int from_b() { return version(); }
    ```
    `main` 打印 `from_a()` 和 `from_b()`。在本机 Clang 23 上：

    | 选项 | 链接顺序 | 输出 |
    |---|---|---|
    | `-O0` | a.cpp b.cpp | `1 1` |
    | `-O0` | b.cpp a.cpp | `2 2` |
    | `-O2` | 任意 | `1 2` |

    `-O0` 时两处调用都走符号 `version()`，链接器保留**先看到的**那份；`-O2` 时调用被内联，各用各的定义。程序的行为随优化级别和链接顺序变化——这就是"{{ifndr}}"在实践中的样子：不报错、不警告，结果取决于构建细节。

!!! impl "同名类的不同定义：内存越界"
    更隐蔽也更危险的是两个 .cpp 各自定义了一个"私有的"同名类：

    ```cpp title="a.cpp"
    struct Node { int v; Node() : v(1) {} };          // 4 字节
    int from_a() { Node n; return n.v; }
    ```
    ```cpp title="b.cpp"
    struct Node { double d[4]; Node() : d{1, 2, 3, 4} {} };  // 32 字节
    double from_b() { Node n; return n.d[3]; }
    ```

    类内定义的构造函数是隐式 inline 的，两个 `Node::Node()` 修饰名相同，链接器只保留一个。本机实验：链接顺序为 b、a 时，`from_a` 里 4 字节的 `n` 被 b 版本的构造函数写入 32 字节——ASan 报告 `stack-buffer-overflow ... WRITE of size 32`，不开 ASan 时直接段错误；顺序为 a、b 时 `from_b` 读到未初始化的垃圾值。**修复**：把只在一个 .cpp 中使用的类型放进**无名命名空间**，使其获得内部链接（[[basic.link#4]]），各 TU 的 `Node` 就是不同的实体，修饰名也不同（`(anonymous namespace)::Node`）。

!!! impl "vtable 与 key function"
    Itanium ABI 中，含虚函数的类的 vtable 只在定义其 **key function**（第一个非 inline、非纯虚的虚函数）的 TU 中发射；如果没有 key function，则在每个需要它的 TU 中以 vague linkage 发射。¶8 "非纯虚的虚函数总被 odr-use"的规则与此吻合：忘记定义 key function，vtable 就哪里都不会生成，链接器报 `undefined reference to vtable for X`（GNU ld 的说法）。

!!! impl "检测 ODR 违规的工具"
    标准不要求诊断，但有一些工具能抓住一部分：

    - **GCC `-Wodr`**：配合 LTO（`-flto`）时，GCC 能比较不同 TU 中同名类型的定义，对布局或定义不一致给出警告——上面 `Node` 那种"同名类型、不同布局"正是它的目标。
    - **AddressSanitizer** 的 `detect_odr_violation` 选项（`ASAN_OPTIONS=detect_odr_violation=...`）：检测**被插桩的全局变量**在多个模块（如主程序和动态库）中重复定义，报 `odr-violation`。它不检查类型或 inline 函数的定义差异。
    - **C++20 模块**：对附属于具名模块的实体，¶16 要求在先前定义可达时给出诊断；Clang 在合并模块中的定义时也会比较定义的哈希，对来自不同模块的不一致定义报错。
    - 一些链接器能基于调试信息做 ODR 检查（例如 GNU gold 的 `--detect-odr-violations`），覆盖面有限。

    这些都只是"尽力而为"。最可靠的预防仍是：一个实体只在一个头文件里定义；TU 私有的东西放进无名命名空间；整个程序用一致的编译选项和宏。

## ODR 违规在实践中从哪里来

| 来源 | 机制 | 例子 |
|---|---|---|
| 不同的 `-D` / 预处理配置 | 同一头文件展开成不同记号（¶16.4） | 一部分 TU 定义了 `NDEBUG` 或调试宏，头文件里的类多了一个调试字段 |
| 同名的 TU 私有类型 | 两个 .cpp 各自定义 `struct Node`（¶16.4） | 见上方实验；修复：无名命名空间 |
| 头文件中的非 inline 定义 | ¶16.1：多于一个定义 | 在头文件写 `int counter = 0;` 或非 inline 非模板函数体 |
| 头文件常量被取址 | ¶16.5.1 例外不再适用 | inline 函数返回 `&kConst`、把 `kConst` 绑定到 `const int&`（如 `std::max(kConst, x)`） |
| 实例化点看到的东西不同 | ¶17.3 | 显式特化只在部分 TU 中声明；ADL 候选只在部分 TU 中可见 |
| 不一致的库版本 | 头文件与库二进制不匹配 | 用 v2 的头文件、链接 v1 的库 |
| 默认实参不一致 | ¶16.11、¶17.1 | 在不同 TU 的类外定义中追加不同的默认实参 |

MSVC 的标准库用 `#pragma detect_mismatch` 把 `_ITERATOR_DEBUG_LEVEL` 等配置写进目标文件，链接时发现不一致就报错（LNK2038）——这是实现方对"不同预处理配置导致 ODR 违规"这一问题的工程化补救。

## 历史与演进

!!! history "C++98 → C++26"
    - **C++98/03**：ODR 已有今天的骨架（每 TU 一个定义；被"使用"的非 inline 函数/对象恰好一个定义；类、inline 函数、模板等的多处定义必须由相同记号序列组成且名字含义相同）。"使用"（used）的定义比较粗糙：名字出现在潜在求值表达式中就算被使用；C++03 加入了"满足常量表达式要求、且立即应用左值到右值转换的对象"的例外。
    - **C++11**：术语改为 **odr-use**，以区别于日常意义的"使用"；constexpr 加入，例外条款随常量表达式的新定义改写。
    - **C++14 前后**：通过若干核心语言缺陷修正，引入**潜在结果集**，把"立即应用左值到右值转换"推广到穿透 `?:`、`,`、成员访问等的情形，并加入丢弃值表达式的例外。
    - **C++17**：**inline 变量**（P0386）——变量也能"在每个 TU 中各定义一次"，`static constexpr` 数据成员隐式 inline；保证的复制省略让"省略的拷贝构造是否被 odr-use"的问题只剩下非强制省略的情形。
    - **C++20**：**模块**——"可达"取代"出现在本 TU"，具名模块中的实体只能有一个定义，ODR 违规在可见时**要求诊断**；**TU-local** 实体与"暴露"（P1815）；lambda 可以出现在不求值操作数中，闭包类型的 ODR 规则随之细化；C++20 起结构化绑定可以被 lambda 捕获。
    - **C++23**：P1787R6 引入新的作用域模型，odr-usable 随之改用"介于其间的作用域"来表述。
    - **C++26**：静态反射（P2996）——*splice-expression* 可以命名变量和函数（¶3.1、¶5、¶6），注入声明的一致性规则（¶15），*reflect-expression* 的值等价（¶16.12）；契约断言作用域可以透明穿越（¶10.2.2）；`constexpr` 引用可以指向同一函数内的自动变量（P2686），这影响了 ¶5 Example 2 的写法。

## 陷阱

!!! pitfall "\"C++17 后 `static const int` 成员就不用类外定义了\""
    错。只有 `static constexpr` 与显式 `static inline` 的数据成员是 inline 的。`static const int N = 0;` 在被 odr-use（如传给 `const int&` 形参的 `std::max`、`std::min`、`std::vector::push_back`）时仍需要类外定义，否则链接失败——而且优化级别不同，表现不同（`-O2` 下调用被内联、常量被折叠，可能"碰巧"链接成功）。

!!! pitfall "\"IFNDR 就是链接错误\""
    不是。"多于一个定义"可能被链接器默默合并（inline、weak 符号），"缺少定义"可能因为优化删掉了调用而不报错，"定义不一致"几乎从不报错。IFNDR 的程序**没有任何行为保证**——不能指望"能链接成功就说明没问题"。

!!! pitfall "\"`if (false)` 里的调用不算使用\""
    算。odr-use 是语法层面的判定，没有控制流分析。只有 `if constexpr` 被丢弃的分支、不求值操作数才能真正"不使用"。析构函数也一样：`if (c) { S s; }` 会 odr-use `~S`。

!!! pitfall "\"命名空间常量在 inline 函数里用会违反 ODR\""
    通常不会——¶16.5.1 专门豁免了"只读值的内部链接常量"。但一旦取址或绑定引用，豁免就失效了。

## 思考题

!!! question "思考题 1"
    下面每一处 `x`，是否 odr-use 了 `x`？

    ```cpp
    struct S { static const int x = 1; int m; };
    void take(int);
    void take_ref(const int&);
    void t(bool c, S s) {
      take(c ? S::x : 2);          // (a)
      take_ref(c ? S::x : 2);      // (b)
      take(s.x);                   // (c)
      int arr[S::x];               // (d)
      take_ref(+S::x);             // (e)
    }
    ```

<details markdown="1">
<summary>答案</summary>

- (a) 不 odr-use。`c ? S::x : 2`：第二操作数是 lvalue `const int`，第三操作数是 prvalue `int`，所以整个条件表达式是 **prvalue**，¶3.7 不适用（潜在结果集为空）；但 `S::x` 作为第二操作数自己做了左值到右值转换——E = `S::x` 本身，`S::x` 可用于常量表达式，¶5.2.2.2 适用，不 odr-use。
- (b) 同 (a)：条件表达式是 prvalue，`S::x` 已经被转换成值，然后临时对象绑定到 `const int&`。不 odr-use。
- (c) 不 odr-use。`s.x` 命名静态数据成员，¶3.4 说其潜在结果集是指称该成员的 id-expression；按值传参应用左值到右值转换，¶5.2.2.2 适用。（`s` 本身作为对象表达式被求值，但 `s` 是形参，与此无关。）
- (d) 不 odr-use：数组边界是常量表达式，读值。
- (e) 不 odr-use：一元 `+` 对操作数做左值到右值转换（整型提升），结果是 prvalue。这是个常用的小技巧：`std::max(+S::x, y)` 可以避免 odr-use。
</details>

!!! question "思考题 2"
    头文件 `h.h` 中有 `const int N = 10; inline int f() { static int calls = 0; return ++calls + N; }`。它被 `a.cpp`、`b.cpp` 包含。问：(1) 有几个 `N` 对象？(2) 有几个 `calls` 对象？(3) 这符合 ODR 吗？

<details markdown="1">
<summary>答案</summary>

(1) 两个（若都未被优化掉）：`N` 是命名空间作用域的非 volatile `const` 非模板变量，内部链接（[[basic.link#3]]），每个 TU 各一个。

(2) 一个：`f` 是 inline 函数，¶18 说行为如同只有一个 `f`、一个定义，其中定义的实体（静态局部变量 `calls`）也只有一个。

(3) 符合。`f` 的两个定义记号相同；名字 `N` 在两个 TU 中指代不同实体，但满足 ¶16.5.1 的例外（字面类型 `const int`、常量初始化、未被 odr-use——`++calls + N` 只读 `N` 的值、两处值都是 10）。
</details>

!!! question "思考题 3"
    为什么 ¶16.1 不允许非 inline 函数有多个"相同的"定义，而 inline 函数就可以？如果标准允许，链接器需要做什么改变？

<details markdown="1">
<summary>答案</summary>

这是历史与实现模型的选择。非 inline 函数的定义被编译为**强符号**，传统链接器遇到同名强符号就报"重复定义"——这是一个有用的诊断，能抓住"头文件里不小心写了函数体"的错误。inline 的语义则显式声明"我会出现在多个 TU 里"，编译器把它发射成可合并的弱符号/COMDAT。如果允许非 inline 函数多处定义，所有函数都要用 COMDAT 发射，链接器就失去了检查重复定义的能力，而且不同定义间的不一致（链接器不比较内容）会更普遍。标准把选择权交给程序员：写 `inline` 就是承诺"所有定义一致"。
</details>

## 小结

| 概念 | 要点 |
|---|---|
| 可定义项 | 类、枚举、函数、变量、模板化实体、默认实参、默认模板实参 |
| 每 TU 至多一个定义 | ¶2，需诊断 |
| 潜在求值 | 不在 `sizeof`/`decltype`/`noexcept`/非多态 `typeid`/requires 中；`if (false)` 仍算 |
| [[g:potential-results|潜在结果集]] | 穿透 `()`、数组下标、非静态成员访问、`.*`、glvalue `?:`、逗号右操作数 |
| 变量 [[g:odr-use]] | 潜在求值地命名，除非：常量可用的引用；丢弃值且无左值到右值转换；常量可用、非 volatile、无 mutable 的对象被读值（非类类型）或读引用成员 |
| 函数 odr-use | 被重载决议选中（纯虚函数仅限定名调用时）；非纯虚的虚函数总是；析构函数被潜在调用 |
| [[g:odr-usable]] | 局部实体跨 lambda 需捕获，跨局部类/嵌套函数形参作用域不可用 |
| 恰好一个定义 | 被 odr-use 的非 inline 非模板化函数/变量（IFNDR） |
| 每 TU 一个、处处一致 | 类、枚举、inline 函数/变量、模板化实体：同记号、同查找结果、同重载、同闭包类型、同语言链接…… |
| 模块 | 具名模块中的实体只能有一个定义；可见的违规需诊断 |
| 实现 | COMDAT/weak 符号；链接器不比较内容；`-Wodr`+LTO、ASan 只能抓一部分 |
