---
title: 重载集的地址
summary: 没有实参的函数名（或 &函数名）指称一个重载集时，如何依据"目标类型"从中挑出唯一的函数：七种目标语境、模板实参推导、非模板优先、约束更强者优先、更特化的模板优先。
status: draft
since: c++98
related: over.match, temp.deduct.funcaddr, temp.deduct.call, conv.fctptr, expr.unary.op, dcl.type.auto.deduct, namespace.std
tags: 重载决议, 函数指针, 成员指针, 模板
updated: 2026-10-17
---

平常说的"重载决议"是**按实参选函数**：`f(1)` 看实参 `1` 的类型。可函数名还有另一种用法——**不带实参**出现，例如 `int (*p)(int) = &f;`、`std::sort(v.begin(), v.end(), cmp)` 里的 `cmp`、`std::cout << std::endl` 里的 `std::endl`。这时没有实参可看，标准换了个方向：**看目标类型**（target type）——这个表达式要被转换成什么类型，就选类型与之一致的那个函数。

本节就是这种"反向重载决议"的完整规则。它在第 12 章里自成一节，与 [[over.match]] 的机制几乎完全独立：没有隐式转换序列、没有排序，只有"类型是否**完全一致**"加上几条淘汰规则。

!!! note "读之前需要知道"
    - **重载集**（overload set）：名字查找找到的声明全是函数或函数模板时，它们构成重载集（[[basic.lookup.general#1]]）。只有一个函数时也是重载集——本节同样适用。
    - [[expr.prim.id#6]]：指称重载集的 *id-expression* 要经重载决议（[[over.match]] 或本节）选出唯一函数。
    - 函数指针转换（[[conv.fctptr]]）：`noexcept` 函数的指针可以转换为非 `noexcept` 函数的指针，反之不行。

## 什么叫"没有实参"的重载集表达式，目标有哪些（¶1）

¶1 一个指称重载集 `S`、且**不带实参**出现的表达式，被解析为某个特定函数的函数（左值）、函数指针或成员函数指针；这个函数从 `S` 中依据语境要求的**目标类型**挑选。目标可以是：

| 列表项 | 目标 | 例子 |
|---|---|---|
| ¶1.1 | 被初始化的对象或引用（[[dcl.init]]、[[dcl.init.ref]]、[[dcl.init.list]]） | `int (*p)(int) = f;`、`void (&r)(int) = f;`、`S s{f};` |
| ¶1.2 | 赋值的左侧（[[expr.assign]]） | `p = &f;` |
| ¶1.3 | 函数的形参（[[expr.call]]） | `take(f)`，`take` 的形参是 `int(*)(int)` |
| ¶1.4 | 用户定义运算符的形参 | `std::cout << std::endl` |
| ¶1.5 | 函数、运算符函数、转换函数的返回值（[[stmt.return]]） | `return &f;` |
| ¶1.6 | 显式类型转换（[[expr.type.conv]]、[[expr.static.cast]]、[[expr.cast]]） | `static_cast<int(*)(int)>(f)` |
| ¶1.7 | 常量模板形参（[[temp.arg.nontype]]） | `X<f>`，`X` 的形参是 `int(*)(double)` |

若目标类型含**占位类型**（`auto`、`decltype(auto)`），先做占位类型推导（[[dcl.type.auto.deduct]]），本节其余部分使用推导出的类型。表达式前面可以有 `&`。注 1：函数名外面多余的括号被忽略（[[expr.prim.paren]]）——但对成员指针例外，见下文 ¶6 的例 2。

```cpp run ok
int f(double) { return 1; }
int f(int)    { return 2; }

int (*p1)(int) = &f;                         // ¶1.1 初始化对象
int (&r1)(double) = f;                       // ¶1.1 初始化引用
void take(int (*)(int)) {}
int (*ret())(double) { return f; }           // ¶1.5 返回值
template<int (*P)(double)> struct NT {};
NT<f> nt;                                    // ¶1.7 常量模板形参

int main() {
  int (*p2)(double);
  p2 = &f;                                   // ¶1.2 赋值
  take(f);                                   // ¶1.3 函数形参
  auto p3 = static_cast<int (*)(int)>(f);    // ¶1.6 显式转换
  return p1(0) + r1(0) + p2(0) + p3(0) + ret()(0) - 7;   // 2+1+1+2+1 = 7
}
```

这张表也说明了**哪些地方不是目标**：

- `auto p = &f;`（`f` 有多个重载）——目标类型是占位类型，推导需要从 `&f` 得出一个类型，而各候选给出不同类型，推导失败（见下文 ¶5 后的讨论）。
- `decltype(&f)`、`sizeof(f)`、`(void)&f;`——没有目标，按 ¶2 选"所有非模板函数"，多于一个就非良构。
- **模板形参**：`template<class T> void call(T);  call(f);`——形参类型 `T` 本身待推导，不构成目标类型（[[temp.deduct.call#6]] 把它当作不推导语境或"试推导"，见下文）。这正是 `std::function<int(int)> fn = f;` 失败的原因：`std::function` 的转换构造函数是模板。

```cpp error
int f(int);
int f(double);
auto a = &f;                          // error: 两个候选推导出不同的类型
using T = decltype(&f);               // error: 没有目标，两个非模板函数都被选中
void g() { (void)&f; }                // error: 同上
```

## 选哪些函数：非模板按类型一致，模板按推导（¶2–¶4）

¶2 **没有目标**时，选中所有被指称的非模板函数。**有目标**时，非模板函数 `F` 被选中当且仅当它的函数类型（必要时先做函数指针转换 [[conv.fctptr]]）与目标类型中的函数类型 `FT` **完全相同**。

关键词是"完全相同"（identical）。这里**没有**任何隐式转换：形参类型、返回类型差一点都不行，参数个数不同更不行。所以标准例子里 `int (*pfe)(...) = &f;` 非良构，原因不是"两个候选歧义"，而是根本**没有**类型为 `int(...)` 的 `f`。同理，派生类到基类的协变在这里也不存在（¶8）。

唯一的"松动"是函数指针转换：

```cpp
void f(int) noexcept;
void f(double);
void (*p)(int) = f;                  // OK：void(int) noexcept 经函数指针转换成为 void(int)
void (*q)(double) noexcept = f;      // error: f(double) 不是 noexcept，不能反向转换
```

注 2：匹配**成员函数指针**类型时，忽略成员所属的类。也就是说 `void (D::*)()` 这个目标能选中基类 `B` 的成员 `B::f()`，结果 `&D::f` 的类型是 `void (B::*)()`，再经成员指针转换（[[conv.mem]]）成为 `void (D::*)()`：

```cpp run ok
struct B { void f() {} void f(int) {} };
struct D : B {};
void (D::*p)() = &D::f;              // 选中 B::f()，再转换为 void (D::*)()
void (B::*q)(int) = &D::f;           // 选中 B::f(int)
int main() { D d; (d.*p)(); (d.*q)(1); }
```

¶3 对每个被指称的**函数模板**，通过模板实参推导（[[temp.over]]、[[temp.deduct.funcaddr]]、[[temp.arg.explicit]]）生成的特化（若推导成功）加入被选集合。[[temp.deduct.funcaddr#1]] 规定：有目标时，用函数模板的函数类型作 `P`、目标类型作 `A` 做推导；没有目标时，以空的 `P`/`A` 推导——也就是说模板实参必须全部显式给出或有默认值。

```cpp run ok
template<class T> T twice(T x) { return x + x; }
int (*p)(int) = &twice;              // 从目标类型推导 T = int
auto q = &twice<double>;             // 没有目标（auto 推导前需要类型），但 T 已显式给出
int main() { return p(1) + int(q(0.5)) - 3; }
```

¶4 哪种函数匹配哪种目标：

- 非成员函数、**静态**成员函数、**显式对象**成员函数（C++23 的 `this` 形参）匹配**函数指针**或**函数引用**目标；
- **隐式对象**成员函数匹配**成员函数指针**目标。

注 3：若选中隐式对象成员函数，结果只能用来形成成员指针（[[expr.unary.op]]）——即必须写成 `&X::f`。

显式对象成员函数在这一点上更像静态成员函数：`&S::f` 的类型是普通函数指针，对象形参变成了第一个形参。

```cpp run ok
struct S {
  int f(this S) { return 1; }        // 显式对象成员函数
  int f(int) { return 2; }           // 隐式对象成员函数
};
int (*p)(S)       = &S::f;           // 选中 f(this S)：类型是 int(*)(S)
int (S::*q)(int)  = &S::f;           // 选中 f(int)
int main() { S s; return p(s) + (s.*q)(0) - 3; }
```

```cpp error
struct S { void f(this S); };
void (S::*q)() = &S::f;              // error: &S::f 的类型是 void(*)(S)，不是成员函数指针
```

## 淘汰规则：最终必须恰好剩一个（¶5）

¶5 依次进行：

1. 关联约束**不满足**的函数从被选集合中删除（[[temp.constr.decl]]）。
2. 若剩下不止一个：只要集合里有**非模板特化**的函数，就删除所有**函数模板特化**。（"非模板优先"，与 [[over.match.best#2.4]] 的决胜规则同一精神。）
3. 非模板函数 `F0`，若集合里有另一个非模板函数比它**更受偏序约束**（more partial-ordering-constrained，[[temp.constr.order]]），删除 `F0`。
4. 函数模板特化 `F1`，若集合里有另一个特化，其模板按 [[temp.func.order]] 的偏序比 `F1` 的模板**更特化**，删除 `F1`。

淘汰之后必须**恰好剩一个**，否则非良构。

```cpp run ok
template<class T> int g(T)   { return 1; }
int g(int)                   { return 2; }
template<class T> int h(T)   { return 3; }
template<class T> int h(T*)  { return 4; }

int (*pg)(int)  = g;         // 模板特化 g<int> 与非模板 g(int) 都被选中；删去模板特化 → g(int)
int (*ph)(int*) = h;         // h<int*>(T) 与 h<int>(T*) 都被选中；后者的模板更特化 → h(T*)
int main() { return pg(0) + ph(nullptr) - 6; }
```

### 约束：先删不满足的，再比"更受约束"

标准例 3 很值得逐行读：

```cpp
template<bool B> struct X {
  void e(int) requires B;       // #1
  void e(int);                  // #2
  void f(short) requires B;
  void f(long);
  template<typename> void g(short) requires B;
  template<typename> void g(long);
};
void test() {
  auto ep = &X<true>::e;        // OK：选中 #1
  &X<true>::f;                  // error: 歧义
  &X<true>::g<int>;             // error: 歧义
}
```

- `auto ep = &X<true>::e;`：目标类型是 `auto`，先做占位类型推导。[[temp.deduct.call#6.2]] 规定对重载集逐个**试推导**（只用约束满足的成员），若所有成功的推导得出**同一个** `A`，它就是结果——#1、#2 的类型都是 `void (X<true>::*)(int)`，于是推导出这个类型。然后回到本节：两者都与目标一致；¶5 第 3 步，#1 比 #2 更受约束（两者形参相同、#1 多了 `requires B`），删除 #2。
- `&X<true>::f`：没有目标，两个非模板函数都被选中。`f(short) requires B` 与 `f(long)` 的形参类型不同，[[temp.constr.order]] 意义下的"更受约束"只在两个函数的形参类型列表**对应**时才有意义，所以谁也删不掉——歧义。约束**不是**一般意义上的决胜规则。
- `&X<true>::g<int>`：两个模板特化，形参类型不同，偏序和约束都分不出高低，歧义。

!!! lawyer "占位类型与重载集：C++23 之后的新措辞"
    "目标含占位类型时先做推导，再用推导出的类型做选择"这句，以及 [[temp.deduct.call#6.2]] 中"所有成功的推导得出同一个 `A` 即为结果"，是较新的措辞。效果是：`auto p = &X<true>::e;` 这种"候选的类型全都一样、只靠约束区分"的写法合法了；而 `auto p = &f;`（`f(int)` 与 `f(double)`）依然非良构，因为两次推导得出不同的类型。Clang 23 已按此实现。

只有约束不满足的那一个时：

```cpp error
template<class T> struct A {
  static void g() requires (sizeof(T) > 100);
};
auto p = &A<int>::g;   // error: 唯一的 g 被删除，集合为空
```

## 标准例子与两条注（¶6–¶8）

¶6 例 1 已在上文吸收。例 2 展示静态与非静态成员函数在目标类型下的分流，以及括号的作用：

```cpp
struct X {
  int f(int);
  static int f(long);
};
int (X::*p1)(int)  = &X::f;     // OK
int    (*p2)(int)  = &X::f;     // error: f(int) 是隐式对象成员函数，不匹配函数指针
int    (*p3)(long) = &X::f;     // OK
int (X::*p4)(long) = &X::f;     // error: 静态成员函数不匹配成员函数指针
int (X::*p5)(int)  = &(X::f);   // error: 形成成员指针必须写成 &X::f，不能加括号
int    (*p6)(long) = &(X::f);   // OK：静态成员函数，括号无妨
```

`p5` 是注 1"多余括号被忽略"的例外：[[expr.unary.op]] 规定只有 `&` 直接作用于 *qualified-id* 时才形成成员指针，`&(X::f)` 不是这个形式。

¶7 注 4：若 `f` 和 `g` **都是**重载集，`f(&g)`（或等价的 `f(g)`）要考虑二者的**笛卡尔积**：对 `f` 的每个候选，把它对应形参的类型当作 `g` 的目标类型，看能否选出 `g` 的某个函数；能选出来，这个 `f` 候选才可行。

```cpp run ok
int g(int)    { return 1; }
int g(double) { return 2; }
int f(int (*p)(int))  { return 10 + p(0); }
int f(int (*p)(char)) { return 20 + p(0); }   // 没有 g(char)，这个 f 不可行
int main() { return f(g) - 11; }               // 选中 f(int(*)(int)) 与 g(int)
```

¶8 注 5：即使 `B` 是 `D` 的公有基类，返回 `D*` 的函数也**不能**选给 `B* (*)()` 目标，接受 `D*` 的函数也不能选给 `void (*)(B*)` 目标——"完全相同"就是完全相同，没有协变，也没有逆变。

```cpp error
struct B {}; struct D : B {};
D* f();
B* (*p1)() = &f;                // error
void g(D*);
void (*p2)(B*) = &g;            // error
```

## 经典难题：`std::toupper` 与 `std::endl`

**`std::endl` 为什么能用？** `std::cout << std::endl` 中 `std::endl` 是函数模板（重载集），没有实参。`basic_ostream` 有成员 `operator<<(basic_ostream& (*pf)(basic_ostream&))`——这个形参类型是**具体的**函数指针类型，于是构成 ¶1.4 的目标；按 ¶3 用它推导 `std::endl` 的模板实参 `charT`、`traits`，得到唯一特化。

**`std::transform(..., std::toupper)` 为什么常常编译不过？**

```cpp error
#include <algorithm>
#include <cctype>
#include <locale>
#include <string>
void up(std::string& s) {
  std::transform(s.begin(), s.end(), s.begin(), std::toupper);   // error
}
```

`std::transform` 的第四个形参类型是模板形参 `UnaryOp`——不是目标类型。实参是重载集：`<cctype>` 的 `int toupper(int)` 加上 `<locale>` 的函数模板 `template<class charT> charT toupper(charT, const locale&)`。[[temp.deduct.call#6.1]]：重载集含函数模板时，该形参是**不推导语境**，于是 `UnaryOp` 推导不出来，调用失败。只包含 `<cctype>` 时，重载集只有一个非模板函数，试推导成功——这就是"有的机器能编译、有的不能"的根源（取决于标准库头文件之间的间接包含）。

更要紧的是，即使编译通过，这么写也**不保证可移植**：[[namespace.std#6]] 规定，除非标准库函数被指定为 *addressable function*，形成指向它的指针（显式的 `&`，或隐式的函数到指针转换）的行为是**未指定的（可能非良构）**。`toupper` 不是 addressable function。另外，`toupper(int)` 对负的 `char` 值是 UB。正确写法：

```cpp run ok
#include <algorithm>
#include <cctype>
#include <string>
int main() {
  std::string s = "abc";
  std::transform(s.begin(), s.end(), s.begin(),
                 [](unsigned char c) { return static_cast<char>(std::toupper(c)); });
  return s == "ABC" ? 0 : 1;
}
```

同理，`std::function<int(int)> fn = f;`（`f` 重载）失败，因为 `std::function` 的构造函数形参是模板形参；需要 `static_cast<int(*)(int)>(f)` 或 lambda 包一层。

## 实现视角

!!! impl
    - 这一节在编译器里通常称为 "address of overloaded function" 解析。Clang 的诊断措辞是 "address of overloaded function 'f' does not match required type …"；没有目标时报 "reference to overloaded function could not be resolved; did you mean to call it?"；`auto` 推导失败时报 "variable 'p' with type 'auto' has incompatible initializer of type '&lt;overloaded function type&gt;'"。
    - "完全相同"的比较是在**规范化后的函数类型**上做的：顶层 `const` 形参、数组/函数形参的调整都已在声明时完成（[[dcl.fct]]），所以 `void f(const int)` 与目标 `void(*)(int)` 是一致的。
    - 目标类型来自"被转换到的类型"，所以编译器把这一步实现为隐式转换的一个特例：当初始化/转换的源是重载集时，先按目标类型解析出单个函数，再走普通的函数到指针转换与函数指针转换。

## 历史与演进

!!! history
    - **C++98**：本节基本形态已经确立——目标类型、"非模板优先"、"更特化的模板优先"、"恰好剩一个"。
    - **C++11**：`decltype`、`auto` 让"没有目标"的情形常见起来；`auto p = &f;` 只对单一函数有效。
    - **C++17**：`noexcept` 成为函数类型的一部分，¶2 加入"可先做函数指针转换"。
    - **C++20**：概念引入后加入 ¶5 的约束规则——先删除约束不满足者，再在非模板之间比较"更受约束"。
    - **C++23**：显式对象成员函数（[[P0847R7]]）加入 ¶4，与静态成员函数一样匹配函数指针。
    - **C++23 之后**：目标含占位类型时先推导再选择的措辞，以及 [[temp.deduct.call#6.2]] 的"所有成功推导结果相同即可"。

## 陷阱

!!! pitfall "以为会做隐式转换"
    `long (*p)(int) = f;`，而 `f` 返回 `int`——非良构。本节只看类型**完全一致**（外加 `noexcept` 的函数指针转换），不像函数调用那样考虑转换。

!!! pitfall "把重载函数传给模板形参"
    `std::thread t(f, 1);`、`std::invoke(f, 1)`、`std::bind(f, _1)`、`std::function<...> fn = f;`：形参都是模板，没有目标类型，重载的 `f` 一律失败。解决：`static_cast` 到具体指针类型，或者用 lambda 包装（lambda 内部是普通调用，走 [[over.match]]）。

!!! pitfall "对标准库函数取地址"
    除非标准明确指定为 addressable function，否则对 `std::` 函数取地址（包括隐式地传函数名）是未指定行为，可能非良构——标准库实现有权增加重载、改为函数模板或用其他机制实现。

!!! pitfall "括号与成员指针"
    `&(X::f)` 不形成成员指针。对隐式对象成员函数必须写 `&X::f`。

## 思考题

!!! question "1. 下面哪些行良构？"
    ```cpp
    void f(int);
    void f(long);
    template<void (*P)(long)> struct Y {};
    Y<f> y1;
    Y<&f> y2;
    void (*arr[2])(int) = { f, &f };
    auto g = static_cast<void (*)(int)>(f);
    decltype(f)* h = f;
    ```

<details markdown="1">
<summary>答案</summary>

前四个声明（`y1`、`y2`、`arr`、`g`）都良构：常量模板形参（¶1.7）、聚合初始化的每个元素（¶1.1，元素是被初始化的对象）、显式类型转换（¶1.6）都是目标。

`decltype(f)* h = f;` 非良构：`decltype(f)` 里的 `f` 没有目标（`decltype` 的操作数不是任何转换的源），¶2 选中两个非模板函数，不是恰好一个。
</details>

!!! question "2. 为什么 `&X<true>::e` 能选出 `#1`，`&X<true>::f` 却歧义？二者都有一个带 `requires B` 的版本。"

<details markdown="1">
<summary>答案</summary>

¶5 的第 3 步要求比较的两个非模板函数之间存在"更受偏序约束"的关系。按 [[temp.constr.order]]，这种比较只对形参类型列表**对应**（等价）的两个函数有意义：`e(int) requires B` 与 `e(int)` 形参相同，前者的约束包含后者的（空）约束，更受约束；`f(short) requires B` 与 `f(long)` 形参不同，无从比较，于是两者都保留，¶5 最后的"恰好剩一个"不成立。另外 `&X<true>::e` 本身的 `auto` 推导能成功，靠的是两个候选类型相同——若两个 `e` 的类型不同，推导就先失败了。
</details>

!!! question "3. `int g(int); int g(double); int f(int (*)(int)); int f(int (*)(double)); f(g);` 结果如何？"

<details markdown="1">
<summary>答案</summary>

歧义。按注 4 的笛卡尔积，两个 `f` 都可行：第一个配 `g(int)`，第二个配 `g(double)`。之后进入普通的重载决议 [[over.match.best]]：两个实参都是"重载集到函数指针"的转换，都是恒等转换（函数到指针转换属于左值变换，Exact Match），无法分出高下，调用非良构。
</details>

## 小结

!!! summary
    | 步骤 | 规则 |
    |---|---|
    | 确定目标 | 初始化、赋值、函数实参、运算符实参、返回值、显式转换、常量模板实参；`auto` 先推导 |
    | 非模板函数 | 类型与目标**完全一致**（允许 `noexcept` 函数指针转换）；成员指针忽略所属类 |
    | 函数模板 | 用目标类型推导，成功则加入特化 |
    | 种类匹配 | 非成员、静态、显式对象成员 ↔ 函数指针/引用；隐式对象成员 ↔ 成员函数指针 |
    | 淘汰 | 约束不满足 → 有非模板则删模板特化 → 删约束更弱的非模板 → 删不够特化的模板特化 |
    | 结论 | 恰好剩一个，否则非良构 |
