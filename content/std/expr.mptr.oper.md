---
title: 成员指针运算符
summary: .* 和 ->* 把成员指针绑定到一个具体对象上；本页讲操作数要求、结果的值类别和 cv、引用限定成员函数的限制，以及三种未定义行为。
status: done
papers: P0704R1, P0145R3
related: dcl.mptr, conv.mem, expr.ref, expr.unary.op, expr.call, over.match.oper, basic.compound
tags: 成员指针, 值类别, UB
updated: 2026-10-19
---

!!! tldr
    - `obj.*pm` 用成员指针 `pm` 访问对象 `obj` 的成员，`p->*pm` 就是 `(*p).*pm`。调用成员函数指针必须加括号：`(obj.*pmf)(args)`。
    - 结果的值类别和 cv 跟 `obj.member` 一样：数据成员的结果随 `obj` 是左值或亡值，`const` 对象得到 `const` 结果；但 `mutable` 不能经成员指针生效。
    - 对象是右值时不能调用 `&` 限定的成员函数，C++20 起 `const &` 除外；对象是左值时不能调用 `&&` 限定的成员函数。
    - 三种情况是 UB：成员指针为空；对象里根本没有这个成员；对象表达式的类型与实际对象不相似。
    - C++17 起左操作数先于右操作数求值。

## 成员指针要绑定到对象上

**成员指针**（pointer to member，[[dcl.mptr]]）不指向任何对象。`int S::*pm = &S::m;` 只记住了 `S` 里的哪一个成员，实现上通常就是一个偏移量。要访问数据，必须把它和一个具体对象结合起来，这就是 `.*` 和 `->*` 的作用：

```cpp run title="mptr-basic.cpp" ok
struct S { int a = 1, b = 2; int sum() const { return a + b; } };

int main() {
    int S::* pm = &S::b;
    int (S::*pmf)() const = &S::sum;
    S s;
    S* p = &s;
    int x = s.*pm;          // 2
    int y = (p->*pmf)();    // 3
    return x + y == 5 ? 0 : 1;
}
```

成员指针的隐式转换方向与对象指针相反：`int B::*` 可以隐式转成 `int D::*`，反过来不行（[[conv.mem]]）。

## 优先级与括号（¶1）

¶1 `.*` 和 `->*` 从左往右结合，自成一级 *pm-expression*，比 `*`、`/`、`%` 高，比一元运算符和强制转换低：

```text
pm-expression:
    cast-expression
    pm-expression .* cast-expression
    pm-expression ->* cast-expression
```

函数调用 `()` 是后缀运算符，优先级远高于 `.*`，所以调用成员函数指针必须加括号：

<div class="compare" markdown="1">

```cpp error
struct S { int f(int x) { return x; } };

int g(S& s, int (S::*pmf)(int)) {
  return s.*pmf(1);
  // error: 解析为 s.*(pmf(1))
}
```

```cpp ok
struct S { int f(int x) { return x; } };

int g(S& s, S* p, int (S::*pmf)(int)) {
  return (s.*pmf)(1) + (p->*pmf)(2);
}
```

</div>

左结合意味着 `a.*pm1.*pm2` 是 `(a.*pm1).*pm2`：先取出成员子对象，再对它应用第二个成员指针。

## 操作数要求（¶2–¶3）

¶2 `E1.*E2` 中，`E2` 必须是"`T` 的成员指针"类型的纯右值（是变量的话先读出它的值）。`E1` 必须是 glvalue，类型为 `T`，或者是以 `T` 为无二义、可访问基类的类。结果就是 `E2` 指定的那个对象或函数。

允许 `T` 的派生类，是因为派生类对象里一定有一个 `T` 子对象，也就一定有那个成员。反过来，`int D::*` 不能用在 `B` 对象上，`B` 对象里不一定有 `D` 的成员：

```cpp title="mptr-operands.cpp" error
struct B { int b = 1; };
struct D : B { int d = 2; };

struct A { int x; };
struct L : A {};
struct R : A {};
struct LR : L, R {};          // 两个 A 子对象
struct P : private A {};

void f(D& dobj, B& bobj, LR& lr, P& p) {
    int B::* pb = &B::b;
    int D::* pd = &D::d;
    dobj.*pb = 0;      // OK：B 是 D 的无二义可访问基类
    bobj.*pd = 0;      // error: B 对象未必含有 D::d
    int A::* pa = &A::x;
    lr.*pa = 1;        // error: A 是 LR 的二义基类
    p.*pa = 1;         // error: A 是 P 的不可访问基类
}
```

`E1` 是纯右值时，例如 `S{}.*pm`，它会先经过临时量实质化（[[conv.rval]]）变成亡值，这是期望 glvalue 处的一般规则（[[basic.lval]]）。

¶3 `E1->*E2` 的 `E1` 必须是指向 `U` 的指针，`U` 是 `T` 或以 `T` 为无二义、可访问基类的类。整个表达式改写成 `(*(E1)).*E2`，所以 `->*` 的全部规则都归结到 `.*`。

重载时两者不同。`->` 有特殊规则，会反复调用 `operator->` 直到得到原生指针（[[over.ref]]）；`->*` 只是普通的二元运算符（[[over.binary]]），不会链式调用。标准库的智能指针都不提供 `operator->*`，要写 `(*sp).*pm` 或 `std::invoke(pm, *sp)`：

```cpp run title="mptr-arrow.cpp" ok
#include <memory>
#include <functional>

struct S { int v = 7; int get() const { return v; } };

int main() {
    auto sp = std::make_unique<S>();
    int S::* pm = &S::v;
    int a = (*sp).*pm;                       // OK：先解引用再 .*
    int b = std::invoke(&S::get, *sp);       // OK
    // int c = sp->*pm;                      // error: unique_ptr 没有 operator->*
    return a + b == 14 ? 0 : 1;
}
```

## 结果的值类别（¶6）

¶6 第二操作数是数据成员指针时，第一操作数是左值则结果是左值，否则是亡值（xvalue）。第二操作数是成员函数指针时，结果是纯右值，而且只能立即调用。

这和 `E1.E2` 访问非静态数据成员的规则对应（[[expr.ref]]）。从将亡对象里取出的成员也是将亡的，所以 `std::move(obj).*pm` 可以被移动：

```cpp run title="mptr-valcat.cpp" ok
#include <utility>
#include <string>
#include <type_traits>

struct S { std::string name; };

int main() {
    S s{"hello"};
    std::string S::* pm = &S::name;
    static_assert(std::is_same_v<decltype((s.*pm)), std::string&>);             // 左值
    static_assert(std::is_same_v<decltype((std::move(s).*pm)), std::string&&>); // 亡值
    static_assert(std::is_same_v<decltype((S{}.*pm)), std::string&&>);          // 亡值
    std::string t = std::move(s).*pm;   // 移动构造
    return t == "hello" ? 0 : 1;
}
```

¶6 开头规定，`.*` 或 `->*` 的结果是函数时，只能用作函数调用 `()` 的操作数。绑定了对象的成员函数不能取地址、不能存起来，这和 `obj.memfn` 不能单独使用是同一回事。要把对象和成员函数打包，用 lambda 或 `std::bind_front`。

```cpp title="mptr-bound-fn.cpp" error
struct S { void f() {} };

void g(S& s) {
    void (S::*pmf)() = &S::f;
    auto x = s.*pmf;       // error: 结果是函数，只能立即调用
    (s.*pmf)();            // OK
}
```

## cv 限定与 `mutable`（¶5）

¶5 结果的 cv 限定，以及对操作数 cv 的限制，都与 `E1.E2` 相同（[[expr.ref]]）：`const` 对象的数据成员得到 `const` 结果。

不同之处在 `mutable`。`E1.E2` 访问 `mutable` 成员时不带上对象的 `const`；而 `mutable` 不是类型的一部分，`int S::*` 不记录它指向的成员是不是 `mutable`。所以注 1 说明，经成员指针访问 `const` 对象的 `mutable` 成员，结果仍然是 `const int` 左值：

```cpp title="mptr-mutable.cpp" error
struct S {
    mutable int i = 0;
};

void f() {
    const S cs;
    cs.i = 1;              // OK：经 . 访问 mutable 成员
    int S::* pm = &S::i;   // pm 指向 mutable 成员 S::i
    cs.*pm = 88;           // error: cs.*pm 是 const int 左值
}
```

成员指针在编译期一般不知道指向哪个成员，类型系统只能一律按 `const` 处理。

## 引用限定的成员函数（¶6）

成员函数可以带**引用限定符**（ref-qualifier，[[dcl.fct]]）：`&` 限定的只能在左值上调用，`&&` 限定的只能在右值上调用。¶6 让 `.*` 遵守同样的规则：

| 对象表达式 | 成员函数的限定 | 结果 |
|---|---|---|
| 右值 | `&` | {{ill-formed}} |
| 右值 | `const &` | OK {{c++20}} |
| 右值 | `&&`、无引用限定 | OK |
| 左值 | `&&` | {{ill-formed}} |
| 左值 | `&`、`const &`、无引用限定 | OK |

<div class="compare" markdown="1">

```cpp ok
struct S {
  int lref() &       { return 1; }
  int cref() const & { return 2; }
  int rref() &&      { return 3; }
};
int main() {
  S s;
  int r = (s.*&S::lref)();
  r += (S{}.*&S::cref)();  // C++20 起
  r += (S{}.*&S::rref)();
  return r == 6 ? 0 : 1;
}
```

```cpp error
struct S {
  void lref() & {}
  void rref() && {}
};
void f(S& s) {
  (S{}.*&S::lref)();
  // error: 右值对象，& 限定
  (s.*&S::rref)();
  // error: 左值对象，&& 限定
}
```

</div>

第二行是 C++20 由 [[P0704R1]] 修正的。直接调用 `S{}.cref()` 一直合法，因为 `const&` 能绑定右值；但 C++11–17 的 `.*` 规则只写了右值不能配 `&`，没有为 `const &` 留例外，于是 `(S{}.*&S::cref)()` 反而非良构。泛型代码经 `std::invoke` 在临时对象上调用 `const&` 成员函数时会碰到这个问题。

## 未定义行为与求值顺序（¶4、¶6）

¶4 把 `E1.*E2` 中的 `E1` 称为**对象表达式**（object expression），与 [[expr.ref]] 用法相同。下面两种情况是 UB：

- `E1` 实际指代的对象，类型与 `E1` 的类型不相似（[[conv.qual]]）。这是经错误类型的 glvalue 访问对象的又一种形式。
- `E1` 实际指代的对象的最终派生对象里，不包含 `E2` 所指的成员。

第二种情况是可能出现的，因为 `static_cast` 允许把 `int D::*` 显式转回 `int B::*`（[[expr.static.cast]]）。转换本身合法，用在最终派生类型确实是 `D` 的对象上也没问题；用在一个纯粹的 `B` 对象上，就是在访问不存在的成员：

```cpp run title="mptr-not-contain.cpp" ub
struct B { int b; };
struct D : B { int d; };

int main() {
    int B::* pm = static_cast<int B::*>(&D::d);   // OK：显式转换

    D dobj{};
    B& ref = dobj;
    ref.*pm = 1;      // OK：ref 的最终派生对象是 D，含有 D::d

    B bobj{};
    return bobj.*pm;  // UB: bobj 只是 B，没有 D::d
}
```

本机 AddressSanitizer 把最后一行报告为 stack-buffer-overflow：读到了 `bobj` 之后的内存。

¶6 最后一句：第二操作数是空成员指针值时，行为未定义。数据成员指针和成员函数指针都一样：

```cpp title="mptr-null.cpp" ub
struct S { int m; };

int f(S& s) {
    int S::* pm = nullptr;
    return s.*pm;        // UB: 空成员指针
}
```

!!! std
    The expression E1 is sequenced before the expression E2.

¶4 的最后一句由 C++17 的 [[P0145R3]] 加入：`E1` 及其全部副作用先于 `E2` 完成。此前两者之间无序，`f().*g()` 中两个函数的调用顺序不确定。现在 `.*`、`->*` 和 `.`、`->`、`<<`、`>>`、`[]` 一样，严格先左后右（[[topics/order-of-evaluation]]）：

```cpp run title="mptr-order.cpp" ok
#include <cstdio>

struct S { int a = 1, b = 2; };
S s;
S& obj()          { std::puts("obj");    return s; }
int S::* member() { std::puts("member"); return &S::b; }

int main() {
    return obj().*member() == 2 ? 0 : 1;   // 先打印 obj，再打印 member
}
```

## 虚函数与成员函数指针

指向虚函数的成员函数指针，经 `.*` 调用时会做虚派发，调用对象动态类型中的最终覆盖函数（[[class.virtual]]、[[expr.call]]）。成员函数指针记住的是哪个虚函数，而不是哪个函数体：

```cpp run title="mptr-virtual.cpp" ok
struct B { virtual int f() { return 1; } virtual ~B() = default; };
struct D : B { int f() override { return 2; } };

int main() {
    int (B::*pmf)() = &B::f;
    D d;
    B& b = d;
    return (b.*pmf)() == 2 ? 0 : 1;   // 调用 D::f
}
```

想绕过虚派发、调用 `B::f`，只能写限定名 `b.B::f()`，成员函数指针做不到。

!!! impl "实现视角：成员指针的表示"
    - Itanium C++ ABI（Linux、macOS 上的 GCC 和 Clang）：数据成员指针是一个 `ptrdiff_t` 偏移量，空值是 `-1`，因为偏移 0 是第一个成员的合法值。成员函数指针占两个字 `{ptr, adj}`：非虚函数时 `ptr` 是函数地址，虚函数时 `ptr` 是 1 加虚表内偏移，最低位为 1 表示虚函数；`adj` 是调用前对 `this` 的调整量，多继承时需要。
    - MSVC：成员函数指针的大小随类的继承模型变化。单继承类在 x64 上是 8 字节，多继承再加一个 `this` 调整量，虚继承还要更多信息。对不完整类声明成员指针时，编译器不知道继承模型，只能用最大的表示，`/vmg` 和 `__single_inheritance` 等关键字可以控制这一点。
    - 所以把成员指针 `reinterpret_cast` 成普通指针，或用 `memcpy` 查看它的内容，都不可移植。

## 常见误解

!!! pitfall "`mutable` 能经成员指针生效"
    `cs.*pm` 总是带上 `cs` 的 `const`，即使 `pm` 指向 `mutable` 成员。

!!! pitfall "`->*` 会像 `->` 一样链式调用"
    重载的 `operator->*` 是普通二元运算符。智能指针上用 `(*p).*pm` 或 `std::invoke`。

## 思考题

!!! question "思考题 1"
    下面的代码良构吗？`r` 是什么类型？临时对象活多久？

    ```cpp
    struct S { int m; };
    const S make();
    auto&& r = make().*&S::m;
    ```

<details markdown="1">
<summary>答案</summary>

良构。`make()` 是 `const S` 类型的纯右值，实质化后成为亡值。按 ¶6，第一操作数不是左值，所以结果是亡值；按 ¶5，结果带上对象的 `const`。于是 `make().*&S::m` 是 `const int` 亡值，`r` 的类型是 `const int&&`。

[[class.temporary#6]] 列出的能延长临时量生命周期的形式里，包括右操作数是数据成员指针的 `.*` 表达式，所以临时对象一直活到 `r` 的作用域结束。
</details>

!!! question "思考题 2"
    为什么 C++20 只为 `const &` 开了口子，`const volatile &` 限定的成员函数仍然不能经 `.*` 在右值上调用？

<details markdown="1">
<summary>答案</summary>

因为引用绑定本来就是这样：`const T&` 能绑定右值，`volatile T&` 和 `const volatile T&` 不能（[[dcl.init.ref]]）。直接调用 `S{}.f()` 时，隐式对象形参就是对应的引用类型，所以 `const volatile &` 成员函数在右值上本来就不能调用。¶6 写的是 "unless its *cv-qualifier-seq* is `const`"，恰好只放过 `const` 一种，与直接调用一致。
</details>

## 小结

| 方面 | 规则 | 段落 |
|---|---|---|
| 优先级 | 左结合，低于 `()`，调用成员函数指针要加括号 | ¶1 |
| `E1.*E2` | `E2` 是 `T` 的成员指针；`E1` 是 `T` 或其无二义可访问派生类的 glvalue | ¶2 |
| `E1->*E2` | 等价于 `(*(E1)).*E2`；重载时是普通二元运算符 | ¶3 |
| 求值顺序 | `E1` 先于 `E2`（C++17） | ¶4 |
| cv | 同 `E1.E2`，但 `mutable` 不生效 | ¶5 |
| 值类别 | 数据成员随 `E1` 为左值或亡值；成员函数为纯右值，只能立即调用 | ¶6 |
| 引用限定 | 右值不能配 `&`（`const &` 除外，C++20）；左值不能配 `&&` | ¶6 |
| UB | 类型不相似；最终派生对象不含该成员；空成员指针 | ¶4、¶6 |
