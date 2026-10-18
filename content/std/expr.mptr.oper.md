---
title: 成员指针运算符
summary: ".* 与 ->* 如何把“成员指针”绑定到对象上：操作数要求、结果的值类别与 cv、引用限定成员函数的限制（C++20 放宽 const&）、空成员指针与“对象里没有这个成员”的 UB、C++17 的求值顺序"
status: done
papers: P0704R1, P0145R3
related: dcl.mptr, conv.mem, expr.ref, expr.unary.op, expr.call, over.match.oper, basic.compound
tags: 成员指针, 值类别, UB
updated: 2026-10-17
---

成员指针（pointer to member，[[dcl.mptr]]）本身不指向任何对象：`int S::*pm = &S::m;` 只记住了 `S` 里的哪一个成员，实现上通常就是一个偏移量。它必须和一个具体对象绑定之后才能用来访问数据，完成这次绑定的就是本节的两个运算符：

- `obj.*pm`：左边是一个类对象（glvalue）；
- `ptr->*pm`：左边是一个指向类对象的指针，等价于 `(*(ptr)).*pm`。

本节回答这些问题：两个操作数各自要满足什么类型要求？结果是什么类型、什么值类别、带什么 cv？什么时候是 UB？它与普通成员访问 `E1.E2`（[[expr.ref]]）的规则如何对应？读本节之前，最好先了解成员指针类型本身（[[dcl.mptr]]）、成员指针的转换（[[conv.mem]]，其隐式转换方向与对象指针相反）以及取成员地址 `&S::m`（[[expr.unary.op]]）。

## 文法与结合性（¶1）

¶1 `.*` 和 `->*` 从左往右结合。它们单独构成一级 *pm-expression*，优先级比 `*` `/` `%` 高，比一元运算符和强制转换低：

```text
pm-expression:
    cast-expression
    pm-expression .* cast-expression
    pm-expression ->* cast-expression
```

最常见的错误由此而来。函数调用 `()` 是后缀运算符，优先级比 `.*` 高得多，所以调用成员函数指针时**必须加括号**：

```cpp title="mptr-paren.cpp" error
struct S { int f(int x) { return x; } };

int g(S& s, int (S::*pmf)(int)) {
    return s.*pmf(1);      // error: 解析为 s.*(pmf(1))，pmf 不是可调用对象
}
```

```cpp run title="mptr-paren-ok.cpp" ok
struct S { int f(int x) { return x; } };

int g(S& s, S* p, int (S::*pmf)(int)) {
    return (s.*pmf)(1) + (p->*pmf)(2);   // OK
}

int main() { S s; return g(s, &s, &S::f) == 3 ? 0 : 1; }
```

从左往右结合意味着 `a.*pm1.*pm2` 是 `(a.*pm1).*pm2`：先取出成员子对象，再在其上应用第二个成员指针。对嵌套结构来说，这样很自然。

## `.*` 的操作数（¶2）

¶2 对于 `E1.*E2`：

- 第二操作数 `E2` 必须是类型为 `T` 的成员指针（pointer to member of `T`）的 prvalue（如果它是变量，先做左值到右值转换）；
- 第一操作数 `E1` 必须是 glvalue，其类型为 `T`，或者是以 `T` 为无歧义且可访问基类的类；
- 结果是 `E2` 所指定类型的对象或函数。

要求 `T` 或其派生类，这与成员指针的转换方向一致。`int B::*` 可以用在 `D` 对象上，因为 `D` 对象里一定有一个 `B` 子对象，从而一定有那个成员。反过来，`int D::*` 不能直接用在 `B` 对象上，因为 `B` 对象里不一定有 `D` 的成员。

```cpp title="mptr-base-derived.cpp" ok
struct B { int b = 1; };
struct D : B { int d = 2; };

int f(D& dobj, B& bobj) {
    int B::* pb = &B::b;
    int D::* pd = &D::d;
    int r = dobj.*pb;           // OK: B 是 D 的无歧义可访问基类
    r += dobj.*pd;              // OK
    // r += bobj.*pd;           // error: B 不是 D，也不以 D 为基类
    (void)bobj;
    return r;
}
```

```cpp title="mptr-ambiguous.cpp" error
struct A { int x; };
struct L : A {};
struct R : A {};
struct D : L, R {};
struct P : private A {};

void f(D& d, P& p) {
    int A::* pm = &A::x;
    d.*pm = 1;      // error: A 是 D 的有歧义基类
    p.*pm = 1;      // error: A 是 P 的不可访问基类
}
```

第一操作数应为 glvalue。若写 `S{}.*pm`，prvalue `S{}` 会经过临时量实质化（temporary materialization，[[conv.rval]]）成为 xvalue。这是 [[basic.lval]] 中的一般规则（期望 glvalue 时对 prvalue 做实质化），不需要本节单独规定。

## `->*`：改写为 `.*`（¶3）

¶3 `E1->*E2` 的第一操作数必须是指向 `U` 的指针，其中 `U` 是 `T` 或以 `T` 为无歧义可访问基类的类；整个表达式改写成 `(*(E1)).*E2`。也就是说，`->*` 没有任何独立语义，所有规则都归结到 `.*`。

它与 `->` 的不同之处在于重载。重载 `->` 时有一条特殊规则：反复调用 `operator->`，直到得到原生指针（[[over.ref]]）。而 `->*` 只是一个**普通的二元运算符**（[[over.binary]]），重载它就是写一个二元 `operator->*`，不会链式调用。正因为如此，大多数智能指针根本不提供 `operator->*`，用户只能写 `((*sp).*pm)` 或 `std::invoke(pm, sp)`。

```cpp run title="mptr-arrow.cpp" ok
#include <memory>
#include <functional>

struct S { int v = 7; int get() const { return v; } };

int main() {
    std::unique_ptr<S> sp = std::make_unique<S>();
    int S::* pm = &S::v;
    int a = (*sp).*pm;                       // OK: 先解引用再 .*
    int b = std::invoke(&S::get, *sp);       // OK: std::invoke 内部就是 .*
    // int c = sp->*pm;                      // error: unique_ptr 没有 operator->*
    return a + b == 14 ? 0 : 1;
}
```

## 对象表达式、UB 与求值顺序（¶4）

¶4 在 `E1.*E2` 中，`E1` 称为**对象表达式**（object expression），与 [[expr.ref]] 的同名术语一致。以下两种情况是 UB：

1. `E1` 的结果对象的类型与 `E1` 的类型不相似（not similar，[[conv.qual]]）。这是通过错误类型的 glvalue 访问对象的又一种形式，与 [[basic.lval]] 的类型访问规则出于同样的考虑；
2. `E1` 的结果对象的最终派生对象（most derived object）不包含 `E2` 所指的成员。

第 2 条之所以可能发生，是因为 [[expr.static.cast]] 允许把 `int D::*` 显式转回 `int B::*`（[[conv.mem]] 的逆方向）。转换本身合法，但用这样的成员指针去访问一个最终派生类型就是 `B` 的对象，就是在访问一个根本不存在的成员：

```cpp run title="mptr-not-contain.cpp" ub
struct B { int b; };
struct D : B { int d; };

int main() {
    int B::* pm = static_cast<int B::*>(&D::d);   // OK: 基←派生方向的显式转换

    D dobj{};
    B& ref = dobj;
    ref.*pm = 1;      // OK: ref 的最终派生对象是 D，包含 D::d

    B bobj{};
    return bobj.*pm;  // UB: bobj 的最终派生对象是 B，不包含 D::d
}
```

!!! std
    The expression E1 is sequenced before the expression E2.

    `E1` 先于 `E2` 求值（含全部副作用）。

这句话是 C++17 由 [[P0145R3]] 加入的。此前 `E1` 与 `E2` 之间无序，`f().*g()` 中 `f` 与 `g` 的调用顺序不确定，若两者修改同一对象（且不是各自在函数体内）还可能构成 UB。现在 `.*`、`->*` 与 `.`、`->`、`<<`、`>>`、`[]` 一样，严格先左后右。详见 [[topics/order-of-evaluation]]。

```cpp run title="mptr-order.cpp" ok
#include <cstdio>

struct S { int a = 1, b = 2; };
S s;
S& obj()          { std::puts("obj");  return s; }
int S::* member() { std::puts("member"); return &S::b; }

int main() {
    return obj().*member() == 2 ? 0 : 1;   // C++17 起保证先打印 obj，再打印 member
}
```

## cv 限定的组合（¶5）

¶5 结果的 cv 限定以及对操作数 cv 的限制，与 `E1.E2`（[[expr.ref]]）的规则相同：对 `const` 对象取数据成员得到 `const` 的结果，`volatile` 同理。

但在 `mutable` 上，结果与 `E1.E2` 不同。[[expr.ref]] 规定访问 `mutable` 成员时不继承对象表达式的 `const`；而 `mutable` 不是类型的一部分，成员指针 `int S::*` 并不记录它指向的成员是否为 `mutable`。因此通过成员指针访问 `const` 对象的 `mutable` 成员时，**结果仍然是 `const int` 左值**，不能赋值：

```cpp title="mptr-mutable.cpp" error
struct S {
    mutable int i = 0;
};

void f() {
    const S cs;
    cs.i = 1;              // OK: mutable 成员，经由 . 访问
    int S::* pm = &S::i;   // pm 指向 mutable 成员 S::i
    cs.*pm = 88;           // error: cs.*pm 是 const int 左值
}
```

这是一种保守的设计。成员指针的值在编译期一般未知，可能指向 `mutable` 成员，也可能不指向；类型系统无法根据运行期指向哪个成员来决定结果的 cv，只能一律按 `const` 处理。

## 成员函数指针与引用限定（¶6）

¶6 如果 `.*` / `->*` 的结果是函数，它只能用作函数调用运算符 `()` 的操作数，不能取地址、不能绑定到引用、也不能存起来。这和 `obj.memfn` 不能单独使用（[[expr.ref]]）是同一回事：绑定了对象的成员函数在 C++ 里不是一等公民，这也是需要 `std::bind_front` 和 lambda 的原因。

```cpp title="mptr-bound-fn.cpp" error
struct S { void f() {} };

void g(S& s) {
    void (S::*pmf)() = &S::f;
    auto x = s.*pmf;       // error: .* 的结果是函数，只能立即调用
    (s.*pmf)();            // OK
}
```

### 引用限定成员函数

¶6 接着规定了带 *ref-qualifier* 的成员函数（[[dcl.fct]]）能否通过 `.*` 调用，规则与直接调用 `obj.f()` 时重载决议对隐式对象参数的要求一致：

| 对象表达式 | 成员函数的限定 | 结果 |
|---|---|---|
| rvalue | `&` | {{ill-formed}} |
| rvalue | `const &` | OK {{c++20}} |
| rvalue | `&&`、无引用限定 | OK |
| lvalue | `&&` | {{ill-formed}} |
| lvalue | `&`、`const &`、无引用限定 | OK |

第二行是 C++20 由 [[P0704R1]] 修正的。直接调用 `S{}.cf()`（`cf` 是 `const&` 成员）一直合法，因为 `const&` 可以绑定右值；但 C++11–17 的 `.*` 规则只规定 rvalue 不能配 `&`，没有为 `const&` 留出例外，于是 `(S{}.*&S::cf)()` 反而非良构。这在泛型代码里很不方便（比如用 `std::invoke` 在临时对象上调用一个 `const&` 成员函数），C++20 把它改成与直接调用一致。

```cpp run title="mptr-refqual.cpp" ok
struct S {
    int lref() &       { return 1; }
    int cref() const & { return 2; }
    int rref() &&      { return 3; }
};

int main() {
    S s;
    int r = (s.*&S::lref)();       // OK: lvalue + &
    r += (S{}.*&S::cref)();        // OK（C++20 起）: rvalue + const&
    r += (S{}.*&S::rref)();        // OK: rvalue + &&
    return r == 6 ? 0 : 1;
}
```

```cpp title="mptr-refqual-bad.cpp" error
struct S {
    void lref() & {}
    void rref() && {}
};

void f(S& s) {
    (S{}.*&S::lref)();   // error: rvalue 对象，& 限定（且非 const）
    (s.*&S::rref)();     // error: lvalue 对象，&& 限定
}
```

### 结果的值类别

¶6 的后半部分给出值类别：

- 第二操作数是数据成员指针：第一操作数是 lvalue 则结果是 lvalue，否则是 xvalue；
- 第二操作数是成员函数指针：结果是 prvalue（当然它只能立即调用）。

这与 `E1.E2` 访问非静态数据成员的规则完全对应，保证从将亡对象里取出的成员也是将亡的，因此 `std::move(obj).*pm` 可以被移动：

```cpp run title="mptr-valcat.cpp" ok
#include <utility>
#include <string>
#include <type_traits>

struct S { std::string name; };

int main() {
    S s{"hello"};
    std::string S::* pm = &S::name;
    static_assert(std::is_same_v<decltype((s.*pm)), std::string&>);             // lvalue
    static_assert(std::is_same_v<decltype((std::move(s).*pm)), std::string&&>); // xvalue
    static_assert(std::is_same_v<decltype((S{}.*pm)), std::string&&>);          // xvalue
    std::string t = std::move(s).*pm;   // 移动构造
    return t == "hello" ? 0 : 1;
}
```

### 空成员指针

¶6 最后一句规定，若第二操作数是空成员指针值（null member pointer value），行为未定义 {{ub}}。这同时适用于数据成员指针和成员函数指针：

```cpp run title="mptr-null.cpp" ub
struct S { int m; void f() {} };

int main() {
    S s{};
    int S::* pm = nullptr;
    void (S::*pmf)() = nullptr;
    if (pm == nullptr && pmf == nullptr) { /* 应当在这里返回 */ }
    (s.*pmf)();          // UB: 空成员函数指针
    return s.*pm;        // UB: 空数据成员指针
}
```

## 虚函数与成员函数指针

本节没有专门提到，但需要说明：通过 `.*` 调用指向虚成员函数的指针时，会进行**虚派发**，调用的是对象动态类型中的最终覆盖函数（[[class.virtual]]、[[expr.call]]）。成员函数指针记住的是哪个虚函数槽位，而不是哪个函数体：

```cpp run title="mptr-virtual.cpp" ok
struct B { virtual int f() { return 1; } virtual ~B() = default; };
struct D : B { int f() override { return 2; } };

int main() {
    int (B::*pmf)() = &B::f;
    D d;
    B& b = d;
    return (b.*pmf)() == 2 ? 0 : 1;   // OK: 调用 D::f，结果 2
}
```

要绕过虚派发、强制调用 `B::f`，只能写限定名调用 `b.B::f()`，成员函数指针做不到。

!!! impl "实现视角：成员指针的表示"
    - **Itanium C++ ABI**（GCC、Clang 在 Linux/macOS 上）：数据成员指针是一个 `ptrdiff_t` 偏移量，空值用 `-1` 表示（因为偏移 0 是合法的第一个成员）。成员函数指针是两个字宽的 `{ptr, adj}`：非虚函数时 `ptr` 是函数地址；虚函数时 `ptr` 是 1 加上虚表内偏移（利用函数地址的对齐，最低位为 1 表示虚函数）；`adj` 是调用前对 `this` 的调整量（多继承时需要）。于是 `(obj.*pmf)()` 编译出来的步骤是：调整 `this` → 判断最低位 → 必要时查虚表 → 间接调用。
    - **MSVC**：成员函数指针的大小随类的继承模型变化。单继承类是 8 字节（x64 上一个指针），多继承类再加一个 `this` 调整量，虚继承还要额外信息；对不完整类声明成员指针时，编译器不知道继承模型，只好用最大的表示。`/vmg` 与 `__single_inheritance` 等关键字控制这一行为。这也是 `sizeof(void (S::*)())` 在不同平台上不同的原因。
    - 因此把成员指针 `reinterpret_cast` 成普通指针，或者用 `memcpy` 查看其内容，都是不可移植的。

## 陷阱

!!! pitfall "`s.*pmf(args)` 少了括号"
    `.*` 的优先级低于函数调用，必须写 `(s.*pmf)(args)`。编译器会报“pmf 不是函数”一类的错误，第一次遇到时往往不容易看懂。

!!! pitfall "以为 `mutable` 能穿透成员指针"
    `cs.*pm` 永远带上 `cs` 的 `const`，即使 `pm` 指向 `mutable` 成员。

!!! pitfall "以为 `->*` 会像 `->` 一样链式调用"
    重载的 `operator->*` 只是普通二元运算符。智能指针上请用 `(*p).*pm` 或 `std::invoke`。

!!! pitfall "派生→基的 `static_cast` 后在基类对象上使用"
    `static_cast<int B::*>(&D::d)` 合法，但只能用在最终派生对象确实是 `D`（或其派生类）的对象上；用在最终派生类型就是 `B` 的对象上是 UB（¶4）。

## 思考题

!!! question "思考题 1"
    下面的代码良构吗？若良构，`r` 是什么值类别？

    ```cpp
    struct S { int m; };
    const S make();
    auto&& r = make().*&S::m;
    ```

<details markdown="1">
<summary>答案</summary>

良构。`make()` 是 `const S` 类型的 prvalue，实质化后成为 xvalue；按 ¶6，第一操作数不是 lvalue，所以数据成员的结果是 xvalue；按 ¶5（同 [[expr.ref]]），cv 取并集，结果类型是 `const int`。所以 `make().*&S::m` 是 `const int` xvalue，`r` 的类型是 `const int&&`。它引用的是临时对象的子对象，[[class.temporary]] 的生命周期延长规则也适用于绑定临时对象子对象的情形，而 `.*` 作用于数据成员指针的结果明确列在可以延长生命周期的表达式形式中，所以临时量一直存活到 `r` 的作用域结束。
</details>

!!! question "思考题 2"
    为什么 C++20 只为 `const &` 开了口子，而 `volatile &`、`const volatile &` 限定的成员函数仍然不能通过 `.*` 在右值上调用？

<details markdown="1">
<summary>答案</summary>

因为普通的引用绑定规则就是如此：`const T&` 可以绑定右值，但 `volatile T&`、`const volatile T&` 不能绑定右值（[[dcl.init.ref]]：要绑定右值，引用必须是 const 且非 volatile 的左值引用，或右值引用）。直接调用 `S{}.f()` 时隐式对象参数的类型就是对应的引用类型，所以 `const volatile&` 成员函数在右值上本来就不可调用。¶6 的措辞 "unless its *cv-qualifier-seq* is `const`" 恰好只放过恰为 `const` 的情形，使 `.*` 与直接调用保持一致。
</details>

## 小结

| 方面 | 规则 | 段落 |
|---|---|---|
| 结合性 | 左结合；优先级低于 `()`，调用需加括号 | ¶1 |
| `E1.*E2` | `E2`：`T` 的成员指针 prvalue；`E1`：`T` 或以 `T` 为无歧义可访问基类的类的 glvalue | ¶2 |
| `E1->*E2` | 等价 `(*(E1)).*E2`；重载时是普通二元运算符 | ¶3 |
| UB | 对象类型不相似；最终派生对象不含该成员；空成员指针 | ¶4、¶6 |
| 顺序 | `E1` 先于 `E2`（C++17） | ¶4 |
| cv | 同 `E1.E2`；`mutable` 不穿透成员指针 | ¶5 |
| 引用限定 | rvalue 不能配 `&`（`const&` 除外，C++20）；lvalue 不能配 `&&` | ¶6 |
| 值类别 | 数据成员：随 `E1`（lvalue / xvalue）；成员函数：prvalue，只能立即调用 | ¶6 |
