---
title: 单一定义规则（ODR）
summary: 每个 TU 内每个可定义项至多一个定义；被 odr-use 的非 inline 函数和变量在整个程序中恰好一个定义；允许多处定义的项（类、inline、模板……）各处的定义必须相同。本页还定义潜在求值、潜在结果集、odr-use 与 odr-usable。
status: done
papers: P0386R2, P1787R6, P1815R2, P2996R13
related: basic.def, basic.link, topics/value-categories, basic.pre, basic.scope, expr.const, dcl.inline, expr.prim.lambda.capture, module.reach, temp.point
tags: ODR, odr-use, 链接, inline, 模板, IFNDR
updated: 2026-10-17
---

**单一定义规则**（One-Definition Rule，ODR）是 C++ 分离编译模型的基本约定。C++ 程序由许多翻译单元（TU）分别编译，再由链接器拼接起来；链接器只看得到符号名，看不到类型和源码。这种模型要成立，就需要 ODR 作保证：

1. TU 内：每个可定义项在一个 TU 里至多定义一次（¶2）。违反时编译器必须报错。
2. 程序内恰好一次：被 odr-use 的非 inline 函数与变量，在整个程序里必须恰好有一个定义（¶12、¶16.1）。缺少定义（未定义引用）或定义多于一个（重复定义）都是 IFNDR，通常表现为链接错误，但标准不作保证。
3. 程序内处处一致：允许在多个 TU 中定义的东西（类、枚举、inline 函数/变量、模板等），每一处定义都必须相同，即记号序列相同、名字查找结果相同、重载决议结果相同等（¶16.3–¶16.12）。违反时 {{ifndr}}，编译器和链接器几乎都不会报错，结果是随意保留其中一个定义。

为了精确描述什么情况下因为用到了某个实体而需要它的定义，本节还定义了一组在整个标准中被引用的术语：**潜在求值**（potentially evaluated）、**潜在结果集**（set of potential results）、函数被**命名**（named）、**odr-use**、**odr-usable**、**定义域**（definition domain）。

阅读本节前需要了解：[[basic.pre]]（变量、局部实体）、[[basic.def]]（什么是定义）、[[basic.link]]（链接决定跨 TU 的名字是否指代同一实体）。

## 可定义项（¶1）

¶1 规定，下列东西称为**可定义项**（definable item）：

| ¶ | 可定义项 | 备注 |
|---|---|---|
| 1.1 | 类类型 | 包括 struct、union、闭包类型 |
| 1.2 | 枚举类型 | |
| 1.3 | 函数 | |
| 1.4 | 变量 | 按 [[basic.pre#7]]：不含非静态数据成员 |
| 1.5 | 模板化实体（templated entity） | 模板、模板中定义的实体、模板的成员……（[[temp.pre]]） |
| 1.6 | （某一作用域中某函数的）形参的默认实参 | |
| 1.7 | 默认模板实参 | |

不在清单中的有：命名空间（所以可以反复打开）、类型别名、概念以外的各种 using、宏、标号。

默认实参之所以单独列为可定义项，是因为默认实参的定义是一段代码（在调用点才代入求值），它本身就可能在不同 TU 里写得不一样，ODR 需要把它也纳入必须一致的范围（见 ¶16.11 与 ¶19 的例子）。加上“在给定作用域中”这个限定，是因为同一个函数在不同块作用域中的重声明可以各自给出默认实参（[[dcl.fct.default]]）。

## 每个 TU 至多一个定义（¶2）

¶2 规定，任何翻译单元都不得包含任何可定义项的多于一个定义。

这是一条需要诊断的规则：在一个 TU 内，编译器看得见所有定义，没有理由不报错。头文件保护（include guard / `#pragma once`）就是为此而存在的。同一个头文件被同一 TU 间接包含两次，里面的类定义就出现了两次。

```cpp error
struct S { int a; };
struct S { int a; };      // error: S 在同一 TU 中被定义两次（哪怕完全相同）
inline void f() { }
inline void f() { }       // error: inline 也不能在同一 TU 定义两次
```

注意 ¶2 管的是定义，不是声明：`extern int x; extern int x;`、`void g(); void g();`、`typedef int I; typedef int I;` 都是合法的重复声明。

## 潜在求值（¶3 前半）

¶3 规定，一个表达式或转换是**潜在求值**的，除非它是不求值操作数（unevaluated operand，[[expr.context]]）、不求值操作数的子表达式，或者是这类上下文中初始化或转换序列里的转换。

不求值操作数出现在：

| 上下文 | 例子 |
|---|---|
| `sizeof` 的表达式操作数 | `sizeof(f())` |
| `decltype` | `decltype(x + 1)` |
| `noexcept` 运算符 | `noexcept(g())` |
| `typeid` 的操作数，除非它是多态类类型的 glvalue | `typeid(expr)` |
| *requires-expression* 的 *requirement-body* 中的表达式 | `requires { t.foo(); }` |

“潜在”的意思是，`if (false) g();` 中的 `g()` 仍是潜在求值的，因为它有可能被求值，而标准不做控制流分析。只有在语法上位于不求值操作数中的表达式才免于 odr-use。唯一的例外是被丢弃的语句（discarded statement，即 `if constexpr` 未被选中的分支，[[stmt.if]]），¶12、¶13 专门把它排除在外。

## 潜在结果集（¶3 后半）

ODR 要回答的核心问题是：一个变量的名字出现在表达式里时，是否需要这个变量真的有一块存储，也就是有定义？如果只是读取它的值，而这个值在编译期就已知，编译器直接把值代进去即可；如果需要它的地址（取址、绑定引用），就必须有定义。

困难在于，名字往往不是单独出现的，而是包在 `( )`、`?:`、`,`、`.`、`[]` 等运算里。`(c ? x : y) + 1` 读的是 `x` 或 `y` 的值，而 `&(c ? x : y)` 要的是地址。**潜在结果集**是一个递归定义，它穿过这些不改变对象身份的运算，找到最终作为对象本身被使用的 *id-expression*。

¶3 规定，表达式 E 的潜在结果集如下：

| ¶ | E 的形式 | 潜在结果集 |
|---|---|---|
| 3.1 | *id-expression*，或 *splice-expression* {{c++26}} | {E} |
| 3.2 | 对数组操作数的下标运算 `a[i]` | `a` 的潜在结果集 |
| 3.3 | 类成员访问 `E1.E2`，E2 是非静态数据成员或直接基类关系 | `E1` 的潜在结果集 |
| 3.4 | 命名静态数据成员的类成员访问 `E1.s` | 指称该成员的 *id-expression* |
| 3.5 | 成员指针 `E1 .* E2` | `E1` 的潜在结果集 |
| 3.6 | 括号 `(E1)` | `E1` 的潜在结果集 |
| 3.7 | glvalue 条件表达式 `c ? E2 : E3` | `E2`、`E3` 潜在结果集之并 |
| 3.8 | 逗号表达式 `E1, E2` | `E2` 的潜在结果集 |
| 3.9 | 其他 | 空集 |

几个值得注意的地方：

- 函数调用、取址、算术运算都属于 3.9。`f(x)` 的潜在结果集是空的，`x` 只在实参 `x` 这个子表达式自己的潜在结果集里。判断 `x` 是否被 odr-use，要找出仍以 `x` 为潜在结果的最大表达式 E，看 E 怎样被使用。在 `f(x)` 中，E 就是实参 `x` 本身，接下来看实参如何初始化形参：按值传递时做左值到右值转换，按引用传递时绑定引用。
- 3.2 只穿过数组操作数的下标运算。`p[i]`（`p` 是指针）不穿过，因为它等价于 `*(p+i)`，访问的是另一个对象。
- 3.3 只穿过非静态数据成员。`a.x` 读的是 `a` 的一个子对象，所以 `a` 是潜在结果；而按 3.4，`a.s`（静态成员）的潜在结果是 `s` 本身，`a` 不在其中。
- 3.7 只对 glvalue 条件表达式成立。如果 `?:` 的结果是 prvalue（例如两边类型不同、需要转换），潜在结果集为空，两个操作数各自已经做了左值到右值转换。
- 3.8 只取右操作数。`(x, y)` 的左操作数 `x` 是一个丢弃值表达式，需要单独判断。

下面是加了注释的标准 Example 1：

```cpp
struct S { static const int x = 0; };
const int &f(const int &r);
extern bool b;
int n = b ? (1, S::x)           // S::x 是初始化器潜在结果集的元素，且只被读值 → 不 odr-use
          : f(S::x);            // 这个 S::x 不在初始化器的潜在结果集里（函数调用是 3.9）；
                                // 它作为实参绑定到 const int&，没有左值到右值转换 → odr-use
int o = [:^^S::x:];             // C++26：splice-expression 本身就是潜在结果
```

初始化器 `b ? (1, S::x) : f(S::x)` 是 prvalue 条件表达式吗？第二操作数 `(1, S::x)` 是 `const int` 左值，第三操作数 `f(S::x)` 也是 `const int` 左值，所以它是 glvalue 条件表达式，3.7 适用。潜在结果集为 {第一个 `S::x`} ∪ {}（函数调用的潜在结果集为空）。

## 函数何时被命名（¶4）

¶4 列出了函数被表达式或转换**命名**（named）的三种方式。

**¶4.1 重载决议选中**：函数是形成表达式或转换时所做的重载决议（[[basic.lookup]]、[[over.match]]、[[over.over]]）中被选中的成员，并且它不是纯虚函数，或者表达式是用显式限定名命名它、且不形成成员指针的 *id-expression*。

Note 2 列出了这条覆盖的场景：取函数地址、调用具名函数、运算符重载、用户定义转换、*new-expression* 的分配函数、非默认初始化（构造函数）。此外还有：

!!! std
    A constructor selected to copy or move an object of class type is considered to be named by an expression or conversion even if the call is actually elided by the implementation.

也就是说，被选中用来拷贝或移动的构造函数，即使调用被省略（NRVO 等非强制省略），也算被命名，因而被 odr-use，必须有定义、必须可访问、不能是 deleted。注意这里说的是确实选中了拷贝/移动构造函数的情形。C++17 起的强制省略（用 prvalue 直接初始化）根本不通过重载决议选择拷贝构造函数，所以不命名它：

```cpp run ok
struct M { M() {} M(const M&) = delete; };
M make() { return M{}; }      // C++17：prvalue 直接初始化返回对象，不选择拷贝构造函数 → OK

struct N { N() {} N(const N&) {} };
N make2() { N n; return n; }  // NRVO 可能省略拷贝，但 N(const N&) 仍被选中 → 被命名、被 odr-use，
                              // 因此必须有定义（若它是 deleted 的，这里就是 error）
int main() { }
```

为什么纯虚函数要特殊处理？通过虚调用 `p->f()` 时，重载决议选中的是 `B::f`（纯虚），但运行时实际调用的是最终覆盖函数，根本不会调用 `B::f`，所以不应要求它有定义。一旦写成限定名 `B::f()`，就是非虚调用，确实会调用 `B::f`，于是它被命名、被 odr-use：

```cpp
struct B { virtual void f() = 0; };          // 纯虚函数没有定义
struct D : B { void f() override { B::f(); } };  // 限定名调用：B::f 被 odr-use
int main() { D d; d.f(); }                   // 链接失败：B::f() 未定义（IFNDR）
```

`&B::f`（形成成员指针）虽然也是限定名，但通过成员指针调用依然是虚调用，所以被排除在外。

**¶4.2–¶4.3 释放函数**：如果类的释放函数（`operator delete`）是被选中的分配函数唯一匹配的释放函数（用于构造函数抛出异常时回收内存，[[expr.new]]），它就被 *new-expression* 命名；如果它是被选中的常规释放函数，就被 *delete-expression* 命名（[[expr.delete]]、[[class.free]]）。

## 变量何时被 odr-use（¶5）

¶5 先定义命名：如果一个表达式是指称（designate）某个变量的 *id-expression* 或 *splice-expression*，该变量就被这个表达式**命名**。

接着是核心定义：如果变量 x 被出现在程序点 P 的潜在求值表达式 N 命名，则 x 被 N **odr-use**，除非：

- **¶5.1** x 是一个在 P 处可用于常量表达式（usable in constant expressions，[[expr.const.init]]）的引用；或
- **¶5.2** N 是某个表达式 E 的潜在结果集的元素，并且
    - **¶5.2.1** E 是一个没有应用左值到右值转换的丢弃值表达式（[[expr.context]]）；或
    - **¶5.2.2** x 是在 P 处可用于常量表达式的非 volatile 对象，没有 mutable 子对象，并且
        - **¶5.2.2.1** E 是命名引用类型非静态数据成员的类成员访问表达式，且对象表达式的类型不是 volatile 限定的；或
        - **¶5.2.2.2** 对 E 应用了左值到右值转换（[[conv.lval]]），且 E 的类型是非 volatile 的非类类型。

概括起来，**变量被潜在求值的表达式命名就是 odr-use，除非实际上只需要它的值而这个值在编译期已知，或者根本没有用到它。**

### 为什么是这几条例外

**¶5.2.2.2，读取常量的值**（值类别与左值到右值转换的背景见 [[topics/value-categories]]）。这是最常见的例外。`constexpr int N = 3;` 在 `int a[N];`、`return N + 1;`、`f(N)`（按值传参）中都只被读值（左值到右值转换），编译器直接把 3 代进去，`N` 不需要存储。可用于常量表达式这一条件保证值在编译期已知；非 volatile 保证读操作没有副作用；要求非类类型，是因为对类类型应用左值到右值转换意味着调用拷贝构造函数，要把 `this` 绑定到对象上，需要地址；要求没有 mutable 子对象，是因为 mutable 成员的值在运行期可能改变，编译期的值不可信。

**¶5.2.2.1，通过 constexpr 对象读取引用成员**。设 `constexpr B b = {x};`，`B` 有引用成员 `int& r`。表达式 `b.r` 只需要知道 `b.r` 绑定到哪个对象，这在编译期就已知道（`x`），不需要 `b` 本身的存储。

**¶5.1，可用于常量表达式的引用**。如果引用绑定到哪个对象在编译期已知，使用这个引用就不需要引用本身的存储（引用通常实现为指针）。

**¶5.2.1，丢弃值表达式**。`x;`、`(void)x;` 既没有读取 `x`，也没有取地址，自然不需要定义。但对 volatile glvalue，丢弃值表达式在某些形式下会应用左值到右值转换（[[expr.context#2]]），因而构成 odr-use。

这些例外都要求 N 在 E 的潜在结果集里，潜在结果集正是为此而定义的。`(c ? x : y)` 被读值时，`x`、`y` 都只是被读值；而在 `&(c ? x : y)` 中，取址运算的潜在结果集是空集，`c ? x : y` 作为取址的操作数，既没有经过左值到右值转换，也不是丢弃值表达式，于是 `x`、`y` 都被 odr-use。

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

下面是静态数据成员的经典例子。它在 C++17 前后都适用，因为 `static const` 成员不是 inline 的：

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
    标准在 ¶5 给出的 Example 2 用自动存储期的 `constexpr` 对象演示 ¶5.2.2.1，例如 `constexpr A a = {1}; constexpr const volatile A& r = a;`、`constexpr B b1 = {x};`（`x` 是局部变量）。这些写法依赖 C++26 放宽的规则：`constexpr` 引用或指针可以指向同一函数内的自动变量（[[expr.const.init]] 中的 *constexpr-referenceable*，对应提案 P2686 "constexpr structured bindings and references to constexpr variables"）。截至写作时，本机 Clang 23 尚未实现这一点，会对 `r`、`b1`、`b2` 的初始化报 "must be initialized by a constant expression"。

    这个例子要说明的是：`f(cond ? a.x : r.x)` 中 `a.x` 和 `r.x` 只被读值，不 odr-use `a` 和 `r`（`r` 是可用于常量表达式的引用，¶5.1）；`g(cond ? b1.r : b2.r)` 只是通过引用成员取得 `x`/`y`，不 odr-use `b1`/`b2`（¶5.2.2.1）；`((cond ? x : y), 0)` 中左操作数是丢弃值表达式（¶5.2.1）。最后的 lambda 中 `return b1.r;` 是 error，因为在 lambda 内部，`b1.r` 所引用的 `x` 不再是 constexpr-referenceable 的，`b1` 在那里不可用于常量表达式。于是例外不适用，`b1` 被 odr-use，而它在 lambda 里不是 odr-usable 的（¶10）。

### 可用于常量表达式的变量

¶5 的例外依赖 [[expr.const.init]] 中可用于常量表达式的定义。简要地说，变量 V 在 P 处可用于常量表达式需要满足：V 是 constexpr，或者是引用，或者是非 volatile const 限定的整型或枚举类型（合称 *potentially-constant*）；V 是常量初始化的；V 的初始化声明在 P 处可达；此外还有一些关于 TU-local 值的条件。

所以 `const int m = 4;` 可以不捕获就在 lambda 里读取，`const double d = 1.5;` 则不行。`double` 不是整型，`d` 不是 potentially-constant，读取它的值就是 odr-use：

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

¶6 规定，如果一个表达式是指称某个结构化绑定的 *id-expression* 或 *splice-expression*，该结构化绑定就被这个表达式命名。结构化绑定只要被潜在求值的表达式命名就是 odr-use，没有变量那样的常量例外。

为什么？结构化绑定不是变量，它是某个无名变量 `e` 的某个子对象或某个引用的别名（[[dcl.struct.bind]]）。标准在这里选择了简单的规则：用到它就算 odr-use，因此在 lambda 中使用它就必须捕获（C++20 起可以捕获结构化绑定）。

¶7 规定，当 `this` 作为潜在求值表达式出现时，`*this` 被 odr-use，隐式出现也算在内。在成员函数中写 `m`（非静态成员）会被隐式变换成 `(*this).m`（[[expr.prim.id.general]]），这同样 odr-use 了 `*this`。结合 ¶10，这就是在 lambda 里访问成员需要捕获 `this`（或 `*this`）的规范依据。

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

¶8 规定：

- **非纯虚的虚成员函数总是被 odr-use**，无论程序是否调用它。原因在实现层面：vtable 必须填入每个虚函数的地址，而类的构造函数会引用 vtable。标准规定它们无条件地被 odr-use，把这个实现需求变成了语言规则，于是声明了虚函数却不定义就是 IFNDR。实践中，这表现为常见的 `undefined reference to vtable for X` 或 `undefined reference to X::f()`。
- 函数被潜在求值的表达式或转换命名（¶4），就是被 odr-use。
- 类的非 placement 分配/释放函数被该类构造函数的定义 odr-use；非 placement 释放函数被该类析构函数的定义 odr-use，或者在虚析构函数定义处被查找选中而 odr-use（[[class.dtor]]）。脚注 13 解释说，实现不必真的在构造或析构函数里调用分配/释放函数，但允许采用这种实现技术。例如 Itanium ABI 的删除析构函数（deleting destructor，D0）变体在虚析构函数中调用 `operator delete`，使 `delete p` 能通过 vtable 找到正确的释放函数。

¶9 规定：

- 类中的赋值运算符被另一个类隐式定义的拷贝/移动赋值函数 odr-use（逐个成员赋值时调用，[[class.copy.assign]]）；
- 构造函数按 [[dcl.init]] 的规定被 odr-use；
- 析构函数在潜在调用（potentially invoked）时被 odr-use，例如自动变量的作用域结束、临时对象销毁、*new-expression* 中构造抛出异常时清理已构造的子对象等（[[class.dtor]]）。

```cpp
struct S { ~S(); };            // 声明但不定义
void f(bool c) { if (c) { S s; } }
int main() { f(false); }       // ~S 被潜在调用 → odr-use → 链接失败（即使 f(false) 永远走不到那里）

struct B { virtual void v(); virtual void p() = 0; };
struct D : B { void p() override { } };
int g() { D d; return 0; }     // B::v 非纯虚 → 无条件 odr-use → 链接失败："B::v()" 被 D 的 vtable 引用
```

## odr-usable：局部实体能在哪里用（¶10–¶11）

¶10 规定，局部实体（[[basic.pre#9]]：自动变量、相应的结构化绑定、结果绑定、`*this`）在满足以下条件时，在某个作用域中是 **odr-usable** 的：

- **¶10.1**：如果它是 `*this`，则必须存在一个外围的类作用域或非 lambda 的函数形参作用域；如果最内层的这种作用域是函数形参作用域，它对应的必须是非静态成员函数。不是 `*this` 的局部实体没有这项要求。
- **¶10.2**：从引入该实体之处到该作用域之间，每一个介于其间的作用域（intervening scope，[[basic.scope.scope#1]]）都是下列之一：
    - 块作用域；
    - 契约断言作用域 {{c++26}}（[[basic.scope.contract]]）；
    - *lambda-expression* 或 *requires-expression* 的函数形参作用域；
    - *lambda-expression* 的 lambda 作用域，且该 lambda 有命名这个实体的 simple-capture 或有 capture-default，并且该 lambda 的块作用域（函数体）也是介于其间的作用域。

（`*this` 视为在最内层的外围类作用域或非 lambda 函数形参作用域中引入。）

如果一个局部实体在它不是 odr-usable 的作用域里被 odr-use，程序非良构。

!!! std
    If a local entity is odr-used in a scope in which it is not odr-usable, the program is ill-formed.

直观地说，局部实体属于某一次函数调用。块作用域、契约断言、lambda 形参列表这类作用域仍处在同一次调用之中，可以直接穿过。局部类的成员函数和嵌套函数声明的形参作用域属于另一个函数，穿不过去。lambda 则像一扇门，只有声明了捕获（或 capture-default）才打开，而且只有在 lambda 函数体里才算进了门，lambda 形参的默认实参仍在门外。

下面是加了注释的标准 Example 3：

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

注意，这些错误都要在 odr-use 时才会出现。如果只是读取一个可用于常量表达式的变量的值（¶5 的例外），就根本不构成 odr-use，是否 odr-usable 也就无关紧要。`constexpr int n = 3; [] { return n; }` 合法，原因就在这里。

¶11（例）把这一推理推广到模板实例化中：

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

关键在于，是否构成 odr-use 要到实例化时才能确定（取决于 `T`），所以同一个泛型 lambda 的不同特化可以一个合法、一个非法。

!!! impl "Clang 与 Example 4"
    截至写作时，本机 Clang 23 对上面 `g()` 和 `h()` 中的 `<int>`、`<void>` 两种特化也报 "variable 'x' cannot be implicitly captured in a lambda with no capture-default specified"。它在依赖于模板形参的转换上过早地认定了 odr-use。按标准，只有 `<const int&>` 那两行应当出错。普通的非依赖情形（`[] { return x; }`）Clang 处理正确。

## 定义必须存在：odr-use 的后果（¶12）

¶12 规定，对于程序中被 odr-use（被丢弃语句中的除外）的每个函数或变量，程序都必须至少包含一个定义；不要求诊断。定义可以显式写在程序中，可以来自标准库或用户库，在适用时也可以是隐式定义（特殊成员函数）。

为什么是 {{ifndr}}？因为定义可能在其他任何 TU 或库里，编译器看不到全局。链接器通常能发现这类问题（报未定义符号），但标准不想把必须由链接器诊断写进语言规则，而且有些情况连链接器也发现不了：

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

标准 Example 5 展示了一个编译器能够发现的情形：

```cpp error
auto f() {
  struct A {};
  return A{};
}
decltype(f()) g();   // g 返回局部类 A
auto x = g();        // odr-use g，但 g 没有定义……
```

`g` 被 odr-use，但本 TU 没有定义它，而且也不可能在其他 TU 中定义它：它的返回类型是 `f` 内的局部类 `A`，在别的 TU 里根本写不出这个类型。所以这个程序必然违反 ¶12。Clang 会直接诊断（"function 'g' is used but not defined in this translation unit, and cannot be defined in any other translation unit because its type does not have linkage"）。

## 定义域与 inline（¶13）

¶13 规定，**定义域**（definition domain）是一个 *private-module-fragment*，或者一个 TU 中除去 *private-module-fragment*（如果有）之外的部分。如果一个 inline 函数或变量在某个定义域中被 odr-use（被丢弃语句中的除外），它的定义就必须从该定义域的末尾可达。

这是“inline 函数必须在每个使用它的 TU 中都有定义”的现代表述，也是头文件库必须把 inline 函数的实现写在头文件里的规范依据。为什么要求每个 TU 都有定义？因为 inline 的本意是允许编译器在调用点内联展开，编译器必须能看到函数体。注意要求的是从定义域末尾可达，所以调用可以出现在定义之前（[[dcl.inline]] 的 Note 3），只要在 TU 结束前能看到定义即可。

模块的 *private-module-fragment*（`module :private;`）自成一个定义域，其中的内容对导入者不可达。如果 `module :private;` 之前的某个 inline 函数调用了一个只在私有片段中定义的 inline 函数，那么后者在私有片段之前的那个定义域里被 odr-use，但从该定义域末尾看不到它的定义，这就违反了本条。（另见 [[dcl.inline]]：附属于具名模块的 inline 函数或变量在哪个定义域中声明，就必须在那个定义域中定义。）

## 类的定义必须可达（¶14）

¶14 规定，在每个需要类类型完整的上下文中，类的定义必须可达。Example 6 说明，只用作指针的类不需要定义：

```cpp run ok
struct X;          // 声明 X 为结构体类型
struct X* x1;      // 形成指针：不需要 X 完整
X* x2;
int main() { }
```

Note 3 列出了需要 `T` 完整的场合（这个列表不具规范性，规范要求分散在各处）：定义 `T` 类型的对象；声明 `T` 类型的非静态数据成员；`new T` 或数组元素类型为 `T`；对 `T` 类型 glvalue 做左值到右值转换；转换到 `T`；把非空指针常量、非 `void*` 的表达式转换为 `T*` 或 `T&`（标准转换、`dynamic_cast`、`static_cast`）；对 `T` 类型表达式用成员访问运算符；`sizeof`/`typeid`/`alignof` 作用于 `T`；定义或调用返回/形参类型为 `T` 的函数；定义以 `T` 为基类的类；对 `T` 类型左值赋值；*exception-declaration* 的类型为 `T`、`T&` 或 `T*`。

这里要求的是可达，而不是出现在本 TU 中。在模块中，一个类的定义可以通过导入的模块接口单元变得可达，而不必重复写出。

## 注入声明的一致性（¶15）{{c++26}}

¶15 规定，如果一个可定义项 D 在某个 TU 中由一个注入声明（injected declaration，[[expr.const.reflect]]）X 定义，而另一个 TU 也包含 D 的定义，那么那个定义也必须是注入声明，并且**特征序列**（characteristic sequence）与 X 相同。只有当 D 附属于具名模块、且之前的定义在后一个定义处可达时，才要求诊断。

背景是，C++26 静态反射允许在常量求值中生成定义，例如 `consteval { std::meta::define_aggregate(^^S, {...}); }` 为不完整类 `S` 注入一个类定义。这样的定义没有对应的源码记号序列，¶16.4 的相同记号序列要求无从适用，于是标准改用特征序列（生成定义的那些反射值，例如数据成员描述的列表）来判断两个注入定义是否相同。C++23 及之前不存在注入声明。

## 多个 TU 中的定义（¶16）

¶16 是 ODR 的主体。对于在多个 TU 中有定义的其他可定义项 D：

- **¶16.1** 如果 D 是非 inline、非模板化的函数或变量，程序非良构。这类实体在整个程序中**至多一个**定义，结合 ¶12 的至少一个，被 odr-use 时就是**恰好一个**；
- **¶16.2** 如果各 TU 中的定义不满足下面的要求，程序非良构。

只有当可定义项附属于具名模块、且之前的定义在后一个定义处可达时，才要求诊断。其他情况，也就是传统的头文件代码，全部是 {{ifndr}}。

那么，哪些东西可以在多个 TU 中各有一个定义？凡是不属于 ¶16.1 的可定义项都可以：类类型、枚举类型、inline 函数、inline 变量、模板化实体（函数模板、类模板及其成员、模板中定义的实体等）、默认实参、默认模板实参。这就是可以写在头文件里的东西的完整清单。

!!! summary "定义数量一览"
    | 可定义项 | 每个 TU | 整个程序 |
    |---|---|---|
    | 非 inline 非模板化函数、变量 | ≤ 1 | 被 odr-use 则恰好 1；否则 ≤ 1 |
    | inline 函数、inline 变量 | ≤ 1；在 odr-use 它的每个定义域末尾可达 | 每个 TU 可各有一个，必须相同 |
    | 类、枚举 | ≤ 1；在需要完整类型处可达 | 每个 TU 可各有一个，必须相同 |
    | 模板化实体（含其成员） | ≤ 1 | 每个 TU 可各有一个，必须相同 |
    | 默认实参、默认模板实参 | ≤ 1（在给定作用域） | 必须相同（通过 ¶16.11） |

接下来是相同的具体要求。给定这样的 D，对 D 的所有定义（如果 D 是无名枚举，则是在任一程序点可达的所有定义）有以下要求。

### ¶16.3 不得附属于具名模块

每个这样的定义都不得附属于具名模块（[[module.unit]]）。换句话说，**具名模块中的实体只能有一个定义**。模块的接口单元只编译一次，导入者通过可达性看到它的定义，不需要也不允许在别的 TU 中重复定义。只有附属于全局模块的实体（传统头文件代码、*global-module-fragment* 中的代码）才适用多处定义、要求一致的规则。

### ¶16.4 相同的记号序列

每个定义必须由相同的记号序列组成；闭包类型的定义视为由对应 *lambda-expression* 的记号序列组成。

这里的记号是翻译阶段 7 的记号（[[lex.phases]]），也就是预处理之后的记号。所以：

- 空白、注释的差异没有影响；
- 宏展开后的结果不同就违反了这条要求。同一个头文件在两个 TU 里用不同的 `-D` 选项编译，就可能产生不同的记号序列；
- 记号相同但含义不同也不行，这由 ¶16.5 规定。

### ¶16.5 名字查找得到相同的实体

在每个定义中，对应的名字按 [[basic.lookup]] 查找（并经过重载决议、偏特化匹配）后，必须指代相同的实体。例外有两种：

- **¶16.5.1** 名字可以指代一个具有内部链接或无链接的非 volatile const 对象，只要该对象在所有定义中类型相同（字面类型）、用常量表达式初始化、在任何定义中都没有被 odr-use，并且值相同；
- **¶16.5.2** 名字可以指代一个具有内部链接或无链接、用常量表达式初始化的引用，只要它在所有定义中引用同一个对象或函数。

这条例外非常重要，下面这种最常见的头文件写法正是靠它才合法：

```cpp title="config.h"
const int kBufSize = 4096;            // 命名空间作用域 const：内部链接，每个 TU 一个独立对象
inline int buffer_bytes() {           // inline：每个 TU 一个定义
  return kBufSize * 2;                // 名字 kBufSize 在各 TU 中指代"不同"的实体！
}                                     // 但它满足 ¶16.5.1：只读值、常量初始化、值相同 → OK
inline const int* buffer_addr() {
  return &kBufSize;                   // 取址 → odr-use → 例外不适用 → 违反 ODR（IFNDR）
}
```

如果没有 ¶16.5.1，任何在 inline 函数里使用头文件中 `const` 常量的代码都会违反 ODR。`buffer_addr` 在不同 TU 中返回不同的地址，链接器却只保留其中一个定义，保留哪一个取决于链接顺序，结果不可预测。修复方法是改用 `inline constexpr int kBufSize = 4096;`（C++17 inline 变量，具有外部链接，全程序只有一个对象）。

!!! tip "为什么头文件常量推荐 `inline constexpr`"
    命名空间作用域的 `constexpr` 变量隐含 `const`，因而具有内部链接（[[basic.link#3]]）。每个包含该头文件的 TU 都有一个副本（不被 odr-use 时通常会被优化掉）。加上 `inline` 后，它获得外部链接，全程序只有一个对象，取址是安全的，在 inline 函数里 odr-use 它也不违反 ODR。C++17 标准库把 `std::is_same_v` 之类定义为 `inline constexpr` 变量模板，这是原因之一。

### ¶16.6 相同的闭包类型

在每个定义中（D 的默认实参和默认模板实参之内的除外），对应的 *lambda-expression* 必须有相同的闭包类型。

正常情况下，每个 lambda 表达式都有一个独一无二的闭包类型。但 inline 函数在多个 TU 中的定义视为同一个定义（¶18），其中的 lambda 也必须是同一个类型。这要求实现在 ABI 层面给它们相同的修饰名（Itanium ABI 用所在实体加 lambda 序号来编码，如 `f()::{lambda()#1}`）。默认实参中的 lambda 被排除在外，原因见 ¶18–¶19。

### ¶16.7 相同的语言链接

对应的实体必须有相同的语言链接（`extern "C"` vs `extern "C++"`，[[dcl.link]]）。

### ¶16.8 常量初始化的一致性

具有静态或线程存储期的 const 对象，如果在某个定义中是常量初始化的，就必须在所有定义中都是常量初始化的。原因在于，常量初始化还是动态初始化，决定了对象是在编译期写进镜像，还是在运行期由初始化代码填入。两种 TU 混在一起，初始化顺序和值都会出问题。

### ¶16.9 显然常量求值的表达式值相同

对应的、非值依赖的显然常量求值（manifestly constant-evaluated，[[expr.const]]）表达式必须有相同的值，例如数组边界、`static_assert`、`if constexpr` 的条件、模板实参。这条要求针对的是记号相同、名字查找结果相同，但常量值不同的情况，例如依赖 `std::is_constant_evaluated()` 或实现定义的值。

### ¶16.10 隐式调用的函数相同

在每个定义中，所引用的重载运算符，以及对转换函数、构造函数、`operator new`、`operator delete` 的隐式调用，都必须指向同一个函数。这些调用在源码中没有名字，不受 ¶16.5 约束，所以要单独规定。典型的违反方式是，某个运算符重载在一个 TU 里可见、在另一个 TU 里不可见，导致同一段 inline 代码选中了不同的函数。

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

被（隐式或显式）函数调用使用的默认实参，以及被 *template-id*/*simple-template-id*/*splice-specialization-specifier* 使用的默认模板实参，视为其记号序列出现在 D 的定义中，也就是说，它们也要递归地满足本段的所有要求。

为什么？因为默认实参是在调用点代入的。设有 `inline void f() { g(); }`，而 `g` 的声明是 `void g(int = N);`，那么 `f` 的定义实际上包含了 `g(N)`。如果两个 TU 中 `g` 的默认实参不同，`f` 的两个定义做的就是不同的事，所以要把默认实参展开进来一起检查。

### ¶16.12 反射表达式的值等价 {{c++26}}

对应的 *reflect-expression*（`^^x`）必须计算出等价的值（[[expr.eq]]）。`^^x` 的值是表示 x 的反射。如果两个 TU 中 `x` 指代不同的实体，反射值就不同，由反射驱动生成的代码也会随之不同。

## 隐式定义与模板的额外要求（¶17）

¶17 规定，在适用上面的要求时：

**¶17.1** 如果 D 是具有隐式声明的构造函数的类，就当作该构造函数在每个 odr-use 它的 TU 中都被隐式定义，并且每个 TU 中的隐式定义必须为 D 的子对象调用相同的构造函数。下面是 Example 7：

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

`D` 的两个定义记号完全相同，名字 `X` 指代同一个类，但由于类外定义追加的默认实参不同，`X x = 0` 的重载决议结果也不同。从类 `D` 本身的记号序列看不出这个差别，所以要单独规定 ¶17.1。

**¶17.2** 默认的三路比较运算符（`operator<=> = default`，[[class.spaceship]]）也是如此：视为在每个 odr-use 它的 TU 中隐式定义，各 TU 中必须为每个子对象调用相同的比较运算符。

**¶17.3** 如果 D 是在多个 TU 中定义的模板，这些要求既适用于模板定义中来自外围作用域的名字，也适用于实例化点处的依赖名（[[temp.dep]]、[[temp.point]]）。也就是说，模板特化 `f<T>` 的语义取决于实例化点可见的东西（ADL 找到的函数、显式特化等），如果不同 TU 在实例化点看到的东西不同，就违反了 ODR。显式特化必须在第一次使用之前声明（[[temp.expl.spec]]），否则同一特化在不同 TU 中可能分别使用主模板和显式特化，这是 ODR 违规的常见来源。

## 视为同一个实体、同一个定义（¶18–¶19）

¶18 规定，上述要求同样适用于在 D 的每个定义内部定义的对应实体（包括 lambda 的闭包类型，但不包括定义在 D 的默认实参/默认模板实参中、或定义在不属于 D 内部的实体的默认实参/默认模板实参中的实体）。对每个这样的实体以及 D 本身，**行为如同只有一个实体、只有一个定义**，在把这些要求应用于其他实体时也是如此。

这句话有很重要的实际后果：

- **inline 函数里的 `static` 局部变量在整个程序里只有一个**。`inline int& counter() { static int c = 0; return c; }` 即使被 10 个 TU 包含，所有 TU 也共享同一个 `c`。Meyers 单例能写在头文件里，就是因为这一点。
- inline 函数中的字符串字面量、lambda 闭包类型、局部类，在各 TU 中都是同一个。
- 对 inline 函数取 `&f`，在各 TU 中得到相同的地址。

Note 4 补充说，这些实体仍然在多个 TU 中被声明，[[basic.link]] 依然适用于这些声明。特别是，出现在 D 的类型中的 lambda 可能导致不同的声明有不同的类型，而出现在 D 的默认实参中的 lambda 在不同 TU 中仍可能是不同的类型。

下面是 ¶19 的 Example 8：

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
- `g`：lambda 在 `g` 的默认实参里，而 `g` 的函数体通过 `g(false)` 使用了这个默认实参。¶16.11 把默认实参的记号视为出现在 `g` 的定义中，但 ¶16.6 和 ¶18 都把 D 自己的默认实参里的 lambda 排除在同一闭包类型的要求之外，每个 TU 中这个 lambda 都是不同的闭包类型。于是 `g` 的各个定义使用了不同的实体，违反 ODR，{{ifndr}}。
- `X::h`：lambda 在 `X::h` 的默认实参里，但这个默认实参位于类 `X` 的定义之内。对 D = `X` 而言，`X::h` 是在 D 内部定义的实体，其默认实参中的 lambda 也是在 D 内部定义的实体（排除条款只针对 D 自己的默认实参，或不在 D 内定义的实体的默认实参），所以各 TU 中是同一个闭包类型。✔

这个例子显示了 ¶18 排除条款的细微之处。被排除的是 D 本身的默认实参中的实体，以及不在 D 内部定义的实体的默认实参中的实体。所以对类 `X` 来说，成员函数默认实参里的 lambda 视为同一个；而对独立的 inline 函数 `g` 来说，它自己的默认实参里的 lambda 不是同一个。

## 无名枚举（¶20）

¶20 规定，如果在程序的任一点，同一作用域中有多于一个可达的无名枚举定义，它们的第一个枚举项名字相同，并且都没有用于链接的 typedef 名，那么这些无名枚举类型必须是同一个类型；不要求诊断。

背景是，`enum { red, green };` 这样的无名枚举没有名字，按 [[basic.link]]，它用于链接的名字是它的第一个枚举项（[[dcl.enum]]）。在头文件里写这样的枚举，被多个 TU 包含后，各 TU 的定义靠第一个枚举项认定为同一个实体。有了模块之后，同一 TU 中可能同时有多个这样的定义可达（例如来自不同的头单元），¶20 要求把它们合并为同一个类型。

## 实现视角

!!! impl "链接器如何合并多份定义：COMDAT 与弱符号"
    inline 函数、inline 变量、模板实例化、vtable、typeinfo、inline 函数中的静态局部变量及其守卫变量，这些允许在多个 TU 中出现的东西在目标文件中被标记为可合并的：

    - **ELF**（Linux）：放在 COMDAT 组中（`.group` 节，`.text._Z7versionv` 这种独立节），链接器对同名组只保留一份；符号通常是 `W`（weak）。
    - **Mach-O**（macOS）：标记为 weak definition。本机 `nm -m` 对 `inline int version()` 的输出是 `weak external __Z7versionv`。
    - **PE/COFF**（Windows）：COMDAT 节，选择策略通常是 "any"（任选一个）。

    Itanium C++ ABI 把这类发射方式称为 **vague linkage**。关键在于，**链接器只按符号名合并，从不比较内容**，它假定程序遵守了 ODR。ODR 违规（¶16.2）几乎从不被诊断，根本原因就在这里。

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

    在 `-O0` 下，两处调用都通过符号 `version()`，链接器保留先看到的那份定义；在 `-O2` 下，调用被内联，各自使用自己的定义。程序的行为随优化级别和链接顺序而变化。{{ifndr}} 在实践中就是这个样子：不报错、不警告，结果取决于构建细节。

!!! impl "同名类的不同定义：内存越界"
    更隐蔽也更危险的情况是，两个 .cpp 各自定义了一个自认为私有的同名类：

    ```cpp title="a.cpp"
    struct Node { int v; Node() : v(1) {} };          // 4 字节
    int from_a() { Node n; return n.v; }
    ```
    ```cpp title="b.cpp"
    struct Node { double d[4]; Node() : d{1, 2, 3, 4} {} };  // 32 字节
    double from_b() { Node n; return n.d[3]; }
    ```

    类内定义的构造函数是隐式 inline 的，两个 `Node::Node()` 修饰名相同，链接器只保留一个。本机实验的结果是：链接顺序为 b、a 时，`from_a` 里 4 字节的 `n` 被 b 版本的构造函数写入 32 字节，ASan 报告 `stack-buffer-overflow ... WRITE of size 32`，不开 ASan 时直接段错误；顺序为 a、b 时，`from_b` 读到未初始化的垃圾值。修复的办法是把只在一个 .cpp 中使用的类型放进**无名命名空间**，使其获得内部链接（[[basic.link#4]]），这样各 TU 的 `Node` 就是不同的实体，修饰名也不同（`(anonymous namespace)::Node`）。

!!! impl "vtable 与 key function"
    在 Itanium ABI 中，含虚函数的类的 vtable 只在定义其 **key function**（第一个非 inline、非纯虚的虚函数）的 TU 中发射；如果没有 key function，就在每个需要它的 TU 中以 vague linkage 发射。¶8 中非纯虚的虚函数总被 odr-use 的规则与此吻合：如果忘记定义 key function，vtable 在哪里都不会生成，链接器报 `undefined reference to vtable for X`（GNU ld 的说法）。

!!! impl "检测 ODR 违规的工具"
    标准不要求诊断，但有一些工具能抓住一部分：

    - **GCC `-Wodr`**：配合 LTO（`-flto`）时，GCC 能比较不同 TU 中同名类型的定义，对布局或定义不一致给出警告。上面 `Node` 那种同名类型、不同布局的情况正是它要抓的。
    - **AddressSanitizer** 的 `detect_odr_violation` 选项（`ASAN_OPTIONS=detect_odr_violation=...`）：检测经过插桩的全局变量在多个模块（如主程序和动态库）中的重复定义，报 `odr-violation`。它不检查类型或 inline 函数的定义差异。
    - **C++20 模块**：对附属于具名模块的实体，¶16 要求在先前定义可达时给出诊断；Clang 在合并模块中的定义时也会比较定义的哈希，对来自不同模块的不一致定义报错。
    - 一些链接器能基于调试信息做 ODR 检查（例如 GNU gold 的 `--detect-odr-violations`），覆盖面有限。

    这些工具都只能尽力而为。最可靠的预防办法仍然是：一个实体只在一个头文件里定义；TU 私有的东西放进无名命名空间；整个程序使用一致的编译选项和宏。

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

MSVC 的标准库用 `#pragma detect_mismatch` 把 `_ITERATOR_DEBUG_LEVEL` 等配置写进目标文件，链接时发现不一致就报错（LNK2038）。对于不同预处理配置导致的 ODR 违规，这是实现方在工程上的补救措施。

## 历史与演进

!!! history "C++98 → C++26"
    - **C++98/03**：ODR 已有今天的骨架：每个 TU 一个定义；被使用的非 inline 函数或对象恰好一个定义；类、inline 函数、模板等的多处定义必须由相同的记号序列组成，且名字含义相同。当时对使用（used）的定义比较粗糙，名字出现在潜在求值表达式中就算被使用；C++03 加入了一个例外，即满足常量表达式要求、且立即应用左值到右值转换的对象。
    - **C++11**：术语改为 odr-use，以区别于日常意义上的使用；加入了 constexpr，例外条款随常量表达式的新定义改写。
    - **C++14 前后**：通过若干核心语言缺陷修正引入了潜在结果集，把立即应用左值到右值转换的情形推广到穿过 `?:`、`,`、成员访问等运算的情形，并加入了丢弃值表达式的例外。
    - **C++17**：引入 inline 变量（P0386），变量也可以在每个 TU 中各定义一次，`static constexpr` 数据成员隐式 inline；有了保证的复制省略之后，被省略的拷贝构造函数是否被 odr-use 的问题只剩下非强制省略的情形。
    - **C++20**：引入模块，可达取代了出现在本 TU 中的说法，具名模块中的实体只能有一个定义，ODR 违规在可见时要求诊断；引入 TU-local 实体与暴露（P1815）；lambda 可以出现在不求值操作数中，闭包类型的 ODR 规则随之细化；结构化绑定可以被 lambda 捕获。
    - **C++23**：P1787R6 引入新的作用域模型，odr-usable 随之改用介于其间的作用域来表述。
    - **C++26**：静态反射（P2996）让 *splice-expression* 可以命名变量和函数（¶3.1、¶5、¶6），并带来注入声明的一致性规则（¶15）和 *reflect-expression* 的值等价要求（¶16.12）；契约断言作用域可以直接穿过（¶10.2.2）；`constexpr` 引用可以指向同一函数内的自动变量（P2686），这影响了 ¶5 Example 2 的写法。

## 陷阱

!!! pitfall "误以为 C++17 之后 `static const int` 成员不再需要类外定义"
    这是错的。只有 `static constexpr` 与显式 `static inline` 的数据成员是 inline 的。`static const int N = 0;` 被 odr-use 时（如传给形参为 `const int&` 的 `std::max`、`std::min`、`std::vector::push_back`）仍需要类外定义，否则链接失败。而且表现随优化级别而不同：在 `-O2` 下调用被内联、常量被折叠，可能碰巧链接成功。

!!! pitfall "误以为 IFNDR 就是链接错误"
    并非如此。多于一个定义可能被链接器悄悄合并（inline、weak 符号）；缺少定义可能因为优化删掉了调用而不报错；定义不一致几乎从不报错。IFNDR 的程序**没有任何行为保证**，不能因为链接成功就认为没有问题。

!!! pitfall "误以为 `if (false)` 里的调用不算使用"
    这样的调用算作使用。odr-use 是语法层面的判定，不做控制流分析。只有 `if constexpr` 被丢弃的分支和不求值操作数才真正不构成使用。析构函数也是如此，`if (c) { S s; }` 会 odr-use `~S`。

!!! pitfall "误以为在 inline 函数里使用命名空间常量会违反 ODR"
    通常不会，¶16.5.1 专门豁免了只读取值的内部链接常量。但一旦取址或绑定引用，豁免就失效了。

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

- (a) 不 odr-use。在 `c ? S::x : 2` 中，第二操作数是 lvalue `const int`，第三操作数是 prvalue `int`，所以整个条件表达式是 prvalue，¶3.7 不适用（潜在结果集为空）。但 `S::x` 作为第二操作数自身做了左值到右值转换，此时 E 就是 `S::x` 本身，而 `S::x` 可用于常量表达式，¶5.2.2.2 适用，所以不 odr-use。
- (b) 同 (a)。条件表达式是 prvalue，`S::x` 已经转换成值，然后临时对象绑定到 `const int&`。不 odr-use。
- (c) 不 odr-use。`s.x` 命名静态数据成员，按 ¶3.4，其潜在结果集是指称该成员的 id-expression；按值传参时应用左值到右值转换，¶5.2.2.2 适用。（`s` 本身作为对象表达式被求值，但 `s` 是形参，与此无关。）
- (d) 不 odr-use。数组边界是常量表达式，只读取值。
- (e) 不 odr-use。一元 `+` 对操作数做左值到右值转换（整型提升），结果是 prvalue。这是一个常用的小技巧，`std::max(+S::x, y)` 可以避免 odr-use。
</details>

!!! question "思考题 2"
    头文件 `h.h` 中有 `const int N = 10; inline int f() { static int calls = 0; return ++calls + N; }`。它被 `a.cpp`、`b.cpp` 包含。问：(1) 有几个 `N` 对象？(2) 有几个 `calls` 对象？(3) 这符合 ODR 吗？

<details markdown="1">
<summary>答案</summary>

(1) 两个（如果都没有被优化掉）。`N` 是命名空间作用域的非 volatile `const` 非模板变量，具有内部链接（[[basic.link#3]]），每个 TU 各有一个。

(2) 一个。`f` 是 inline 函数，按 ¶18，行为如同只有一个 `f`、一个定义，其中定义的实体（静态局部变量 `calls`）也只有一个。

(3) 符合。`f` 的两个定义记号相同；名字 `N` 在两个 TU 中指代不同实体，但满足 ¶16.5.1 的例外：类型是字面类型 `const int`，常量初始化，没有被 odr-use（`++calls + N` 只读取 `N` 的值），两处的值都是 10。
</details>

!!! question "思考题 3"
    为什么 ¶16.1 不允许非 inline 函数有多个相同的定义，而 inline 函数就可以？如果标准允许，链接器需要做什么改变？

<details markdown="1">
<summary>答案</summary>

这是由历史和实现模型决定的。非 inline 函数的定义被编译为强符号，传统链接器遇到同名强符号就报重复定义。这个诊断很有用，能发现在头文件里不小心写了函数体的错误。inline 则显式表明这个函数会出现在多个 TU 里，编译器把它发射成可合并的弱符号或 COMDAT。如果允许非 inline 函数多处定义，所有函数都要用 COMDAT 发射，链接器就失去了检查重复定义的能力，而且由于链接器不比较内容，不同定义之间的不一致会更普遍。标准把选择权交给程序员：写 `inline` 就是承诺所有定义一致。
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
| 每 TU 一个、处处一致 | 类、枚举、inline 函数/变量、模板化实体：记号、查找结果、重载、闭包类型、语言链接等都要相同 |
| 模块 | 具名模块中的实体只能有一个定义；可见的违规需诊断 |
| 实现 | COMDAT/weak 符号；链接器不比较内容；`-Wodr`+LTO、ASan 只能抓一部分 |
