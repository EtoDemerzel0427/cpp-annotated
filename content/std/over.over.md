---
title: 重载集的地址
summary: 函数名不带实参出现（如取地址、赋给函数指针）而又指称一组重载函数时，编译器按语境要求的目标类型从中挑出唯一一个：非模板函数要求类型完全相同，模板靠推导，最后按约束和偏序淘汰到只剩一个。
status: done
since: c++98
related: over.match, temp.deduct.funcaddr, temp.deduct.call, conv.fctptr, expr.unary.op, dcl.type.auto.deduct, namespace.std
tags: 重载决议, 函数指针, 成员指针, 模板
updated: 2026-10-19
---

!!! tldr
    - 重载的函数名不带实参出现时，比如 `int (*p)(int) = &f;`，编译器按目标类型挑函数：初始化、赋值、函数实参、返回值、显式转换、常量模板实参都能提供目标类型。
    - 非模板函数的类型必须与目标完全相同，唯一允许的转换是去掉 `noexcept`；不做任何隐式转换，也没有协变。
    - 函数模板用目标类型推导模板实参。之后按顺序淘汰：约束不满足的、有非模板时的模板特化、约束更弱的非模板、不够特殊的模板特化，最后必须恰好剩一个。
    - 目标是模板形参时没有确定的目标类型，所以 `std::function<int(int)> fn = f;`、`std::transform(..., std::toupper)` 这类写法在 `f` 重载时会失败。

## 按目标类型选函数

```cpp run ok
int f(double) { return 1; }
int f(int)    { return 2; }

int (*p1)(int) = &f;       // 选 f(int)
int (&r1)(double) = f;     // 选 f(double)

int main() {
  return p1(0) + r1(0) - 3;
}
```

调用 `f(1)` 时，编译器看实参的类型来选重载，这是 [[over.match]] 的重载决议。函数名还可以不带实参出现：取它的地址、把它赋给函数指针、把它传给接受函数指针的函数。这时没有实参可看，标准换了个方向，看这个表达式要被转换成什么类型，选类型与之一致的那个函数。这个类型叫**目标类型**（target type）。

名字查找找到的声明全是函数或函数模板时，它们构成一个[[g:overload-set|重载集]]（[[basic.lookup.general]]），只有一个函数时也算。指称重载集的名字要经过重载决议，或者经过本节的规则，选出唯一一个函数（[[expr.prim.id]]）。

本节的规则与 [[over.match]] 几乎完全独立：没有隐式转换序列，也没有排序，只看类型是否完全相同，再加几条淘汰规则。

## 哪些语境提供目标（¶1）

¶1 指称重载集 `S`、不带实参出现的表达式，被解析为某个特定函数本身、它的指针或成员函数指针。这个函数按语境要求的目标类型从 `S` 中挑选。目标可以是：

| 列表项 | 目标 | 例子 |
|---|---|---|
| ¶1.1 | 被初始化的对象或引用 | `int (*p)(int) = f;`、`S s{f};` |
| ¶1.2 | 赋值的左侧 | `p = &f;` |
| ¶1.3 | 函数的形参 | `take(f)`，`take` 的形参是 `int(*)(int)` |
| ¶1.4 | 用户定义运算符的形参 | `std::cout << std::endl` |
| ¶1.5 | 函数、运算符函数或转换函数的返回值 | `return &f;` |
| ¶1.6 | 显式类型转换 | `static_cast<int(*)(int)>(f)` |
| ¶1.7 | 常量模板形参 | `X<f>`，`X` 的形参是 `int(*)(double)` |

如果目标类型含有占位类型（`auto`、`decltype(auto)`），先做占位类型推导（[[dcl.type.auto.deduct]]），本节其余部分使用推导出的类型。表达式前面可以有 `&`。注 1 补充，函数名外面多余的括号会被忽略（[[expr.prim.paren]]），但形成成员指针时例外，见下文例 2。

下面这些写法没有可用的目标：

```cpp error
int f(int);
int f(double);
auto a = &f;               // error: 两个候选推导出不同的类型
using T = decltype(&f);    // error: 没有目标
void g() { (void)&f; }     // error: 没有目标
```

`decltype(&f)`、`(void)&f` 没有目标。按 ¶2，这时选中所有非模板函数，有两个，所以非良构。`auto a = &f;` 要先推导 `auto`，而两个候选给出不同的类型，推导失败（见下文例 3 的讨论）。

模板形参也不提供目标。`template<class T> void call(T); call(f);` 中形参类型 `T` 本身有待推导，[[temp.deduct.call#6]] 规定这时只能逐个试推导，见下文 `std::toupper` 的例子。

## 非模板函数：类型完全相同（¶2）

¶2 没有目标时，选中所有被指称的非模板函数。有目标时，非模板函数被选中，当且仅当它的函数类型与目标中的函数类型完全相同，比较前可以先做一次函数指针转换（[[conv.fctptr]]）。

完全相同意味着不做任何隐式转换：形参类型、返回类型差一点都不行。标准例 1 中 `int (*pfe)(...) = &f;` 非良构，原因不是两个候选歧义，而是根本没有类型为 `int(...)` 的 `f`。同样，`long (*q)(int) = k;` 对返回 `int` 的 `k` 也非良构。

唯一的例外是函数指针转换，它允许去掉 `noexcept`：

```cpp
void f(int) noexcept;
void f(double);
void (*p)(int) = f;                // OK：void(int) noexcept 去掉 noexcept
void (*q)(double) noexcept = f;    // error: 不能加上 noexcept
```

注 2 说明，匹配成员函数指针类型时，忽略成员所属的类。目标 `void (D::*)()` 可以选中基类的成员 `B::f()`，`&D::f` 的类型是 `void (B::*)()`，再经成员指针转换（[[conv.mem]]）变成 `void (D::*)()`：

```cpp run ok
struct B { void f() {} void f(int) {} };
struct D : B {};
void (D::*p)() = &D::f;      // 选 B::f()，再转换为 void (D::*)()
void (B::*q)(int) = &D::f;   // 选 B::f(int)
int main() { D d; (d.*p)(); (d.*q)(1); }
```

¶8 注 5 指出，即使 `B` 是 `D` 的公有基类，返回类型和形参类型上也没有协变或逆变：

```cpp error
struct B {}; struct D : B {};
D* f();
B* (*p1)() = &f;     // error
void g(D*);
void (*p2)(B*) = &g; // error
```

## 函数模板：用目标推导（¶3）

```cpp run ok
template<class T> T twice(T x) { return x + x; }
int (*p)(int) = &twice;        // 从目标类型推出 T = int
auto q = &twice<double>;       // 没有目标，但 T 已显式给出
int main() { return p(1) + int(q(0.5)) - 3; }
```

¶3 对每个被指称的函数模板做模板实参推导（[[temp.over]]、[[temp.deduct.funcaddr]]、[[temp.arg.explicit]]），推导成功时把得到的特化加入候选。有目标时，用模板的函数类型和目标类型做推导；没有目标时，模板实参必须全部显式给出或有默认值（[[temp.deduct.funcaddr]]）。

## 哪种成员函数匹配哪种目标（¶4）

¶4 非成员函数、静态成员函数、显式对象成员函数（C++23 带 `this` 形参的成员函数）匹配函数指针或函数引用目标；隐式对象成员函数，也就是普通的非静态成员函数，匹配成员函数指针目标。

```cpp run ok
struct S {
  int f(this S) { return 1; }   // 显式对象成员函数
  int f(int) { return 2; }      // 隐式对象成员函数
};
int (*p)(S)      = &S::f;       // 选 f(this S)，类型是 int(*)(S)
int (S::*q)(int) = &S::f;       // 选 f(int)
int main() { S s; return p(s) + (s.*q)(0) - 3; }
```

显式对象成员函数在这一点上像静态成员函数：`&S::f` 是普通函数指针，对象形参变成第一个形参。注 3 指出，选中隐式对象成员函数时，结果只能用来形成成员指针，即必须写成 `&X::f`（[[expr.unary.op]]）。

标准例 2 把这几条放在一起，还说明了括号的作用：

```cpp error
struct X {
  int f(int);
  static int f(long);
};
int (X::*p1)(int)  = &X::f;    // OK
int    (*p2)(int)  = &X::f;    // error: f(int) 不匹配函数指针
int    (*p3)(long) = &X::f;    // OK
int (X::*p4)(long) = &X::f;    // error: 静态成员函数不匹配成员函数指针
int (X::*p5)(int)  = &(X::f);  // error: 加括号就不形成成员指针
int    (*p6)(long) = &(X::f);  // OK
```

只有 `&` 直接作用于限定名 `X::f` 时才形成成员指针（[[expr.unary.op]]），`&(X::f)` 不是这个形式。这是注 1 中多余括号被忽略的例外。

## 淘汰到只剩一个（¶5）

```cpp run ok
template<class T> int g(T)  { return 1; }
int g(int)                  { return 2; }
template<class T> int h(T)  { return 3; }
template<class T> int h(T*) { return 4; }

int (*pg)(int)  = g;   // g(int)
int (*ph)(int*) = h;   // h(T*)
int main() { return pg(0) + ph(nullptr) - 6; }
```

¶5 候选集合按下面的顺序淘汰：

1. 删除关联约束不满足的函数（[[temp.constr.decl]]）。
2. 如果剩下不止一个，而集合中有非模板函数，就删除所有函数模板特化。
3. 如果另一个非模板函数比非模板函数 `F0` 更偏序受约束（[[temp.constr.order]]），删除 `F0`。
4. 如果另一个函数模板特化的模板按 [[temp.func.order]] 比 `F1` 的模板更特殊，删除函数模板特化 `F1`。

淘汰之后必须恰好剩一个函数，否则非良构。

上例中 `pg` 的候选是 `g<int>` 和 `g(int)`，第 2 步删去模板特化。`ph` 的候选是 `h<int*>`（来自 `h(T)`）和 `h<int>`（来自 `h(T*)`），第 4 步留下更特殊的 `h(T*)`。第 2、4 步与 [[over.match.best]] 中非模板优先、更特殊的模板优先这两条决胜规则对应。

### 约束只在形参相同时比较

标准例 3：

```cpp error
template<bool B> struct X {
  void e(int) requires B;   // #1
  void e(int);              // #2
  void f(short) requires B;
  void f(long);
  template<typename> void g(short) requires B;
  template<typename> void g(long);
};
void test() {
  auto ep = &X<true>::e;    // OK：选 #1
  &X<true>::f;              // error: 歧义
  &X<true>::g<int>;         // error: 歧义
}
```

`auto ep = &X<true>::e;` 先推导 `auto`。[[temp.deduct.call#6.2]] 规定对重载集逐个试推导，如果所有成功的推导得到同一个类型，它就是结果。#1 和 #2 的类型都是 `void (X<true>::*)(int)`，推导成功。然后两者都与目标一致，第 3 步中 #1 比 #2 更受约束，#2 被删除。

`&X<true>::f` 没有目标，两个非模板函数都被选中。它们的形参类型不同，按 [[temp.constr.order]]，这时无法比较谁更受约束，两者都留下，歧义。`&X<true>::g<int>` 同理，两个模板的形参不同，偏序和约束都分不出高下。所以约束不是一般意义上的决胜规则。

如果唯一的函数约束不满足，集合就空了：

```cpp error
template<class T> struct A {
  static void g() requires (sizeof(T) > 100);
};
auto p = &A<int>::g;   // error: 约束不满足
```

!!! lawyer "占位类型与重载集"
    目标含占位类型时先推导再选择，以及 [[temp.deduct.call#6.2]] 中所有成功的推导得到同一类型即可，都是 C++23 之后的新措辞。效果是 `auto p = &X<true>::e;` 这种候选类型全都相同、只靠约束区分的写法合法；而 `f(int)` 和 `f(double)` 并存时 `auto p = &f;` 仍然非良构，因为两次推导得到不同的类型。本机 Clang 23 已按此实现。

## 两个重载集相遇（¶7）

```cpp run ok
int g(int)    { return 1; }
int g(double) { return 2; }
int f(int (*p)(int))  { return 10 + p(0); }
int f(int (*p)(char)) { return 20 + p(0); }   // 没有 g(char)
int main() { return f(g) - 11; }               // f(int(*)(int))，g(int)
```

¶7 注 4 指出，`f` 和 `g` 都是重载集时，解析 `f(&g)` 或 `f(g)` 要考虑所有组合：对 `f` 的每个候选，把对应形参的类型当作 `g` 的目标类型，能从 `g` 中选出函数，这个 `f` 才可行。上例第二个 `f` 找不到 `g(char)`，不可行。

如果两个 `f` 都能配上一个 `g`，就进入普通的重载决议，而两边的转换都是精确匹配，结果是歧义（思考题 2）。

## `std::endl` 与 `std::toupper`

`std::cout << std::endl` 能用：`std::endl` 是函数模板，`basic_ostream` 有一个成员 `operator<<(basic_ostream& (*pf)(basic_ostream&))`，它的形参是具体的函数指针类型，按 ¶1.4 提供目标，用它推导出 `std::endl` 的模板实参。

把 `std::toupper` 传给 `std::transform` 却常常编译失败：

```cpp error
#include <algorithm>
#include <cctype>
#include <locale>
#include <string>
void up(std::string& s) {
  std::transform(s.begin(), s.end(), s.begin(), std::toupper);   // error
}
```

`std::transform` 的第四个形参类型是模板形参 `UnaryOp`，不提供目标。实参 `std::toupper` 是一个重载集：`<cctype>` 的 `int toupper(int)`，加上 `<locale>` 的函数模板 `toupper(charT, const locale&)`。按 [[temp.deduct.call#6.1]]，重载集中含有函数模板时这个形参不参与推导，`UnaryOp` 推导不出来。如果只包含了 `<cctype>`，重载集只有一个非模板函数，试推导会成功。所以这段代码能否编译取决于标准库头文件之间的间接包含。

即使编译通过，这样写也不可移植。[[namespace.std#6]] 规定，除非标准库函数被指定为 addressable function，形成指向它的指针的行为是未指定的，可能非良构；`toupper` 不是这样的函数。另外，`toupper(int)` 接受负的 `char` 值是 UB。应当用 lambda：

```cpp run ok
#include <algorithm>
#include <cctype>
#include <string>
int main() {
  std::string s = "abc";
  std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c) {
    return static_cast<char>(std::toupper(c));
  });
  return s == "ABC" ? 0 : 1;
}
```

`f` 重载时 `std::function<int(int)> fn = f;` 失败也是同样的原因：`std::function` 的转换构造函数是模板。可以写 `static_cast<int(*)(int)>(f)`，或者用 lambda 包一层，lambda 里面是普通调用，走 [[over.match]]。

## 实现视角

!!! impl
    - 编译器把这一节叫做 address of overloaded function 的解析。Clang 在类型不符时报 "address of overloaded function 'f' does not match required type …"，没有目标时报 "reference to overloaded function could not be resolved; did you mean to call it?"，`auto` 推导失败时报 "variable 'a' with type 'auto' has incompatible initializer of type '&lt;overloaded function type&gt;'"。
    - 比较的是声明调整之后的函数类型：形参的顶层 `const`、数组和函数形参到指针的调整都已完成（[[dcl.fct]]），所以 `void f(const int)` 与目标 `void(*)(int)` 一致。
    - 编译器把这一步实现为隐式转换的特例：初始化或转换的源是重载集时，先按目标类型选出一个函数，再做普通的函数到指针转换和函数指针转换。

## 历史与演进

!!! history
    - C++98 已有目标类型、非模板优先、更特殊的模板优先和必须恰好剩一个的规则。
    - C++17 把 `noexcept` 纳入函数类型，¶2 允许比较前先做函数指针转换。
    - C++20 随概念加入 ¶5 的约束规则：先删除约束不满足的函数，再在非模板函数之间比较约束。
    - C++23 的显式对象成员函数（[[P0847R7]]）写入 ¶4，与静态成员函数一样匹配函数指针。
    - C++23 之后的新措辞规定目标含占位类型时先推导再选择。

## 常见误解

!!! pitfall "选函数时会做隐式转换"
    `f` 返回 `int` 时 `long (*p)(int) = f;` 非良构。这里只看类型是否完全相同，唯一允许的是去掉 `noexcept`。

!!! pitfall "重载函数可以直接传给模板形参"
    `std::thread t(f, 1);`、`std::invoke(f, 1)`、`std::bind(f, _1)` 的形参都是模板，没有目标类型，`f` 重载时一律失败。用 `static_cast` 转换成具体的指针类型，或者用 lambda 包装。

!!! pitfall "可以随意对标准库函数取地址"
    除非标准指定为 addressable function，对 `std::` 中的函数取地址（包括隐式地传函数名）是未指定的，可能非良构。实现有权给这些函数增加重载，或者把它们改成函数模板。

## 思考题

!!! question "思考题 1"
    下面哪些声明良构？
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

前四个（`y1`、`y2`、`arr`、`g`）良构：常量模板形参（¶1.7）、聚合初始化中被初始化的每个元素（¶1.1）、显式类型转换（¶1.6）都提供目标。

`decltype(f)* h = f;` 非良构：`decltype(f)` 中的 `f` 没有目标，按 ¶2 两个非模板函数都被选中，不是恰好一个。
</details>

!!! question "思考题 2"
    `int g(int); int g(double); int f(int (*)(int)); int f(int (*)(double));` 之后 `f(g);` 的结果是什么？

<details markdown="1">
<summary>答案</summary>

歧义。按 ¶7，两个 `f` 都可行：第一个配 `g(int)`，第二个配 `g(double)`。接下来是普通的重载决议（[[over.match.best]]），两边的实参转换都只有函数到指针转换，是精确匹配，分不出高下。本机 Clang 23 报 "call to 'f' is ambiguous"。
</details>
