---
title: 类成员访问
summary: E1.E2 与 E1->E2 的含义：箭头先化归为点；对象表达式总会被求值；结果的类型和值类别取决于 E2 指代的是引用成员、静态成员、非静态数据成员、成员函数还是枚举符；cv 取并集，mutable 例外；对象类型不相似时访问成员是 UB。
status: done
papers: P2996R13
related: expr.post, expr.call, basic.lookup.qual, class.member.lookup, class.access.base, basic.lval, basic.life, class.union, expr.prim.splice, expr.prim.id.dtor, conv.qual, topics/value-categories
tags: 表达式, 成员访问, 值类别, cv 限定, mutable, 反射
updated: 2026-10-19
---

!!! tldr
    - `E1->E2` 就是 `(*(E1)).E2`。`*E1` 是左值，所以箭头访问的结果永远不会是亡值。
    - 点前面的对象表达式总会被求值，即使 `E2` 是静态成员。
    - 非静态数据成员：左值对象的成员是左值，其他情况是亡值；cv 取对象和成员声明的并集，`mutable` 成员不继承 `const`。
    - 引用成员和静态数据成员的访问结果总是左值，不叠加对象的 cv；非静态成员函数的 `s.f` 只能立即调用。
    - 如果对象的实际类型与 `E1` 的类型不相似，访问非静态成员就是 UB，哪怕不读写成员的值。

```cpp run title="member-category.cpp" ok
#include <type_traits>
#include <utility>

int g = 0;
struct S {
    int m = 0;
    int& ref = g;
    mutable int mu = 0;
    static int sm;
};
int S::sm = 0;
S make() { return {}; }

S s;
const S cs;

static_assert(std::is_same_v<decltype((s.m)), int&>);               // 左值对象的成员：左值
static_assert(std::is_same_v<decltype((std::move(s).m)), int&&>);   // 亡值对象的成员：亡值
static_assert(std::is_same_v<decltype((make().m)), int&&>);         // prvalue 先实质化：亡值
static_assert(std::is_same_v<decltype((cs.m)), const int&>);        // 对象是 const：成员也是
static_assert(std::is_same_v<decltype((cs.mu)), int&>);             // mutable 不继承 const
static_assert(std::is_same_v<decltype((std::move(s).ref)), int&>);  // 引用成员：总是左值
static_assert(std::is_same_v<decltype((make().sm)), int&>);         // 静态成员：总是左值

int main() {}
```

`s.m`、`p->f()`、`std::move(s).m`、`obj.template get<0>()`、`obj.[: r :]` 都是**类成员访问**（class member access）。[expr.ref] 规定这种表达式的结果指代什么、是什么类型和值类别。名字 `E2` 怎样查找、是否需要 `template` 关键字，由 [[basic.lookup.qual]] 和 [[class.member.lookup]] 规定。

例子里的 `decltype` 都加了括号。不加括号时，`decltype(cs.m)` 给出成员的声明类型 `int`；加括号才按表达式的类型和值类别给出 `const int&`（[[dcl.type.decltype]]）。

## 语法（¶1）

¶1 后缀表达式后跟 `.` 或 `->`，可选地跟关键字 `template`，再跟 *id-expression* 或 *splice-expression* {{c++26}}，构成一个后缀表达式。

注 1 说明，`template` 让后面的非限定名被当作模板名（[[temp.names]]）。在依赖语境中要写 `obj.template get<0>()`，否则 `<` 会被解析为小于号。

## 箭头化归为点（¶2）

¶2 箭头前面必须是指针类型的 prvalue，`E1->E2` 被转换为 `(*(E1)).E2`，本节其余部分只讨论点的形式。脚注 43 提醒，`(*(E1))` 是左值。

所以箭头没有独立的语义。`p->m` 的一切性质都来自 `(*p).m`，而 `*p` 是左值，于是 `std::move(p)->m` 也是左值。要得到亡值，写 `std::move(*p).m`。

¶2 对点前面的表达式还有两条规定：

- `E2` 指代静态成员或枚举符时，点前面的表达式是[[g:discarded-value-expression|弃值表达式]]：照样求值，值被丢弃。
- `E2` 指代非静态数据成员或直接基类关系 {{c++26}} 时，点前面必须是 glvalue。写成 prvalue（`S{}.m`）时，先经临时量实质化（[[conv.rval]]）得到亡值。

类类型可以重载 `->`（[[over.ref]]）：`x->m` 被解释为 `(x.operator->())->m`，一直递归到得到原生指针。智能指针和迭代器靠的就是这条规则。

## 对象表达式总会被求值（¶3）

```cpp run title="static-via-object.cpp" ok
#include <cstdio>

struct S { static int sm; };
int S::sm = 42;
S make() { std::puts("make() called"); return {}; }

int main() {
    int x = make().sm;   // 输出 make() called：对象表达式被求值，然后丢弃
    int y = S::sm;       // 不涉及任何对象
    return x == y ? 0 : 1;
}
```

¶3 点前面的后缀表达式会被求值，求值结果和 `E2` 一起决定整个表达式的结果。脚注 44 强调，即使结果用不着它，例如 `E2` 是静态成员，只要成员访问表达式被求值，这个子表达式就会被求值。`sizeof(make().sm)` 则不同，那是不求值操作数，`make()` 不会被调用。

## 对象表达式的类型（¶4–¶6）

¶4 把 `E1.E2` 中的 `E1` 叫做[[g:object-expression|对象表达式]]。如果对象表达式是标量类型，`E2` 必须是同一类型（忽略 cv）的伪析构函数（[[expr.prim.id.dtor]]），`E1.E2` 是"无参、返回 `void` 的函数"类型的 prvalue，只能用来调用。所以 `p->~T()` 在 `T` 是 `int` 时也合法，调用的效果是结束这个标量对象的生命周期（[[expr.call#4]]）。

```cpp run title="pseudo-dtor-access.cpp" ok
#include <new>

using I = int;

int main() {
    int x = 0;
    x.~I();          // 伪析构函数调用，结束 x 的生命周期
    ::new (&x) int(1);
    int* p = &x;
    p->~I();         // 等价于 (*p).~I()
    ::new (p) int(2);
    return x == 2 ? 0 : 1;
}
```

¶5 否则对象表达式必须是类类型，而且类必须完整，除非成员访问出现在这个类自己的定义里（成员函数体、默认成员初始化器中的 `this->m`）。注 3：如果在类完整之后查找会得到不同的结果，程序非良构（[[class.member.lookup]]）。

```cpp title="incomplete-access.cpp" error
struct Fwd;
int get(Fwd& f);

struct Self {
    int a = 1;
    int b = this->a + 1;          // OK：在类自身的定义中
};

int get(Fwd& f) { return f.x; }   // error: Fwd 不完整
```

¶6 {{c++26}} 如果 `E2` 是 *splice-expression*（[[expr.prim.splice]]），它必须指代 `E1` 的类型 `T1` 的成员，或者直接基类关系 `(T1, B)`。也就是说，`obj.[: r :]` 中反射 `r` 代表的成员必须属于 `obj` 的类本身（[[P2996R13]]）。

## 结果的类型与值类别（¶7–¶8）

¶7 如果 `E2` 指代位域，`E1.E2` 也是位域，于是不能取地址，也不能绑定到非 `const` 引用。下面用 *cq* 表示 `const` 或无，*vq* 表示 `volatile` 或无。

### 引用成员

!!! std
    If E2 designates an entity that is declared to have type "reference to T", then E1.E2 is an lvalue of type T.

¶8 引用成员的访问结果总是左值，类型就是被引用的类型 `T`，不叠加 `E1` 的 cv，与 `E1` 是左值还是亡值无关。引用成员所指的对象不是 `E1` 的子对象，`E1` 是否即将消亡、是否是 `const` 都与它无关。

### 其余情形

| 列表项 | `E2` 指代 | 值类别 | 类型 |
|---|---|---|---|
| ¶8.1 | 静态数据成员（类型 `T`） | 左值 | `T` |
| ¶8.2 | 非静态数据成员（类型 *cq2 vq2* `T`） | `E1` 是左值则为左值，否则为亡值 | *cq12 vq12* `T`；`mutable` 成员为 *vq12* `T` |
| ¶8.3 | 成员函数（重载集） | 静态成员函数为左值，非静态成员函数为 prvalue | 函数类型 |
| ¶8.4 | 嵌套类型 | 非良构 | |
| ¶8.5 | 成员枚举符（类型 `T`） | prvalue | `T` |
| ¶8.6 | 直接基类关系 `(D, B)` {{c++26}} | `E1` 是左值则为左值，否则为亡值 | cv `B` |
| ¶8.7 | 其他 | 非良构 | |

### 非静态数据成员：cv 取并集（¶8.2）

设 `E1` 的类型是 *cq1 vq1* `X`，成员声明的类型是 *cq2 vq2* `T`。结果的 cv 取两者的并集：对象或成员只要有一方是 `const`，结果就是 `const`，`volatile` 同理。唯一的例外是 `mutable` 成员，它不继承 `const`，但仍继承 `volatile`。

`const` 成员函数不能修改成员，依据就在这里：在 `const` 成员函数中，`this->m` 的对象表达式类型是 `const X`，结果也就是 `const` 的。

值类别跟随对象表达式。移动一个即将消亡的对象时可以逐个成员移动，语言上的依据也在这里：`std::move(s).m` 本身就是亡值，可以直接绑定到 `T&&`。

### 成员函数（¶8.3）

`E2` 指代重载集时，`E1.E2` 必须是成员函数调用的左操作数（可以带括号），由重载决议（[[over.match]]）选出函数：

- ¶8.3.1 静态成员函数：`E1.E2` 是左值，可以取出来用，`int (*p)() = s.sf;` 合法。
- ¶8.3.2 非静态成员函数：`E1.E2` 是 prvalue，只能立即调用。

`s.f` 代表绑定了对象的函数，C++ 没有这种可以单独存放的值。需要时用 lambda 或 `std::bind_front`。注 5：多余的括号会被忽略，所以 `(s.f)()` 是合法的调用。

```cpp title="member-fn-access.cpp" error
struct S {
    int f() { return 1; }
    static int sf() { return 2; }
    struct Nested {};
};

void t(S s) {
    int (*p)() = s.sf;      // OK：¶8.3.1
    auto q = s.f;           // error: 非静态成员函数只能被调用
    auto r = &s.f;          // error: 不能对它取地址，应写 &S::f
    S::Nested n = s.Nested{};   // error: ¶8.4，不能经对象访问嵌套类型
    (void)p;
}
```

### 直接基类关系（¶8.6）{{c++26}}

静态反射引入了一种新的可访问对象：直接基类关系。`std::meta::bases_of(^^D, ctx)[i]` 返回的反射代表"`D` 以 `B` 为直接基类"，`d.[: r :]` 指代 `d` 的那个直接基类子对象。`E1` 先隐式转换为"cv `D` 的引用"（左值或右值引用随 `E1`），结果是类型为 cv `B` 的子对象，值类别随 `E1`。

标准例 1 说明了它在消除歧义上的用处：

```cpp title="splice-base.cpp"
#include <meta>

struct B { int b; };
struct C : B { int get() const { return b; } };
struct D : B, C { };          // D 有两个 B 子对象：直接的，以及经 C 间接的

constexpr int f() {
    D d = {1, {}};
    // 反射精确指代 D 的直接基类 B；static_cast<B&>(d) 在这里是二义的
    B& b = d.[: std::meta::bases_of(^^D, std::meta::access_context::current())[0] :];
    b.b += 10;
    return 10 * b.b + d.get();
}
static_assert(f() == 110);
```

本机 Clang 23 还没有实现静态反射（没有 `<meta>` 头文件），这个例子没有经过编译验证。

## 二义的基类（¶9）

¶9 如果 `E2` 指代非静态成员，而 `E2` 直接所属的类是 `E2` 的指派类（designating class，[[class.access.base]]）的二义基类，程序非良构。注 6：如果命名类是对象表达式类型的二义基类，同样非良构。

```cpp title="ambiguous-base.cpp" error
struct A { int x; };
struct L : A {};
struct R : A {};
struct D : L, R {};

int f(D& d) {
    int a = d.L::x;     // OK：A 是 L 的无二义基类
    return d.x + a;     // error: 名字查找二义，有两个 A::x
}

int g(D& d) {
    return d.A::x;      // error: A 是 D 的二义基类
}
```

## 对象类型不相似：UB（¶10）

```cpp run title="not-similar.cpp" ub
struct A { int i; };
struct B { int j; };
struct D : A, B {};

int main() {
    D d{};
    int a = static_cast<B&>(d).j;        // OK：对象表达式指代 d 的 B 子对象
    int b = reinterpret_cast<B&>(d).j;   // UB: 结果仍指代 d，类型不是 B
    return a + b;
}
```

!!! std
    If E2 designates a non-static member (possibly after overload resolution) or direct base class relationship and the result of E1 is an object whose type is not similar to the type of E1, the behavior is undefined.

¶10 两个类型[[conv.qual|相似]]，大致是说忽略各层 cv 后相同。`reinterpret_cast` 不调整地址，`D` 和 `B` 也不是指针可互转的（[[expr.reinterpret.cast]]），所以 `reinterpret_cast<B&>(d)` 指代的仍是 `d` 本身。`.j` 的对象表达式类型是 `B`，而实际对象的类型是 `D`，行为未定义。`static_cast` 做了正确的地址调整。Clang 对这种写法有专门的警告 `-Wreinterpret-base-class`。

这条规则让访问本身就构成 UB，不必等到读写成员的值时再由 [[basic.lval#11]] 的别名规则判断。只取 `&p->m` 的地址，或者调用一个不碰数据的成员函数，同样是 UB。

相关的规则还有两条：

- 在对象的生命周期开始之前或结束之后，访问它的非静态数据成员或调用非静态成员函数是 UB（[[basic.life#7]]、[[basic.life#8]]）。
- 读联合体的非活跃成员是 UB，因为它不在生命周期内；但对它赋值可以按 [[class.union]] 的规则切换活跃成员。写出 `u.f` 这个表达式本身不违反 ¶10：对象表达式 `u` 的类型就是联合体类型。

```cpp run title="union-access.cpp" ok
union U { int i; float f; };

int main() {
    U u{.i = 1};
    u.f = 2.0f;           // 赋值使 f 成为活跃成员
    float x = u.f;        // OK
    // int y = u.i;       // UB: i 不在生命周期内
    return x == 2.0f ? 0 : 1;
}
```

## 实现视角

!!! impl
    - 非静态数据成员的访问编译为对象基址加常量偏移，`p->m` 就是一次带偏移的加载。
    - 编译器依据 ¶10 和别名规则做基于类型的别名分析（TBAA），假定经 `A*` 与经 `B*` 的成员访问互不重叠。
    - `p->static_member` 在 `p` 为空指针时，生成的代码通常不会解引用 `p`。但按标准，¶3 要求求值 `*p`，而对不指向对象的指针做 `*` 是 UB（[[expr.unary.op#1]]）。本机 Clang 23 的 UBSan（`-fsanitize=null`）不报告这种情形，常量表达式里也接受，没有按要求诊断。

## 常见误解

!!! pitfall "`std::move(obj).ref` 是亡值"
    引用成员的访问结果总是左值。泛型代码逐成员转发时，如果成员可能是引用，要用 C++23 的 `std::forward_like<Self>(self.m)` 按对象的值类别转发，不能依赖 `std::move(self).m`。

!!! pitfall "修改 `const` 对象的 `mutable` 成员是 UB"
    不是。`mutable` 成员不继承 `const`，修改 `const` 对象的 `mutable` 成员有定义（[[dcl.type.cv]]）。

## 思考题

!!! question "思考题 1"
    `struct S { const int c = 0; int& r; }; S s{0, x};` 中，`decltype((std::move(s).c))` 和 `decltype((std::move(s).r))` 分别是什么？

<details markdown="1">
<summary>答案</summary>

`std::move(s).c`：按 ¶8.2，`E1` 是亡值，结果是亡值；`s` 不是 `const`，成员是 `const int`，并集是 `const int`。所以是 `const int&&`。`std::move(s).r`：引用成员总是左值，类型是 `int`，所以是 `int&`。
</details>

!!! question "思考题 2"
    `struct S { static int n; }; S* p = nullptr; int x = p->n;` 是不是 UB？`decltype(*p)::n` 呢？

<details markdown="1">
<summary>答案</summary>

`p->n` 化归为 `(*p).n`。¶3 和脚注 44 规定，即使 `n` 是静态成员，对象表达式 `*p` 也要求值；`p` 不指向对象，按 [[expr.unary.op#1]] 这是 UB。实践中编译器不会生成解引用指令，本机 Clang 23 在常量表达式里也接受它，但按标准仍是 UB。

`decltype(*p)` 是不求值操作数，得到 `S&`。`decltype(*p)::n` 非良构，因为引用类型不能作为嵌套名说明符；要写 `std::remove_reference_t<decltype(*p)>::n`。这两种写法都不对 `p` 求值。
</details>
