---
title: 类成员访问
summary: E1.E2 与 E1->E2：箭头如何化归为点；对象表达式何时被求值、何时必须是 glvalue；按 E2 的种类（引用成员、静态数据成员、非静态数据成员、成员函数、嵌套类型、枚举符、C++26 的直接基类关系）确定结果的类型与值类别；cv 的"并集"传播与 mutable；对象类型不相似时的 UB
status: draft
papers: P2996R13
related: expr.post, expr.call, basic.lookup.qual, class.member.lookup, class.access.base, basic.lval, basic.life, class.union, expr.prim.splice, expr.prim.id.dtor, conv.qual, topics/value-categories
tags: 表达式, 成员访问, 值类别, cv 限定, mutable, 反射
updated: 2026-10-17
---

`s.m`、`p->f()`、`std::move(s).m`、`obj.template get<0>()`、`obj.[: r :]`——**类成员访问**（class member access）是最常用的后缀表达式之一。本节回答三个问题：

1. **语法与化归**：`->` 如何变成 `.`？对象表达式何时被求值？
2. **类型与值类别**：`E1.E2` 的结果是左值、亡值还是纯右值？它带什么 cv？这取决于 `E2` 指代的是什么（引用成员？静态成员？成员函数？……），本节给出一张完整的分类。
3. **UB**：什么时候通过一个"其实不是那个类型的对象"访问成员会是 UB？

名字 `E2` **如何被查找**（在对象表达式的类中查找、二义性、`template` 关键字的需要）不归本节，见 [[basic.lookup.qual]] 和 [[class.member.lookup]]。

## 语法（¶1）

¶1：后缀表达式后跟 `.` 或 `->`，可选的 `template` 关键字，然后是 *id-expression* 或 *splice-expression* {{c++26}}，构成一个后缀表达式。

注 1：`template` 关键字使后面的非限定名被当作模板名（[[temp.names]]）——在依赖语境中 `obj.template get<0>()` 必须写，否则 `<` 会被解析为小于号。

## 箭头化归为点；对象表达式的要求（¶2）

¶2 的三条规定：

- 若点后面的表达式指代**静态成员**或**枚举符**，点前面的表达式是**弃值表达式**（[[expr.context]]）——它仍然会被求值（见下文 ¶3 的脚注），只是值被丢弃；
- 若点后面指代**非静态数据成员**或**直接基类关系** {{c++26}}，点前面的表达式必须是 **glvalue**——若写的是 prvalue（`S{}.m`），会施行临时量实质化（[[conv.rval]]）得到亡值；
- 箭头前面的表达式必须是**指针类型的 prvalue**；`E1->E2` 被转换为等价形式 `(*(E1)).E2`，本节其余部分只讨论点的形式。脚注 43 提醒：`(*(E1))` 是左值。

所以箭头没有独立的语义：`p->m` 的一切性质都来自 `(*p).m`，而 `*p` 是左值，于是 `p->m` 永远不会是亡值——即使 `p` 本身是 `std::move(p)`。

对**类类型**，`->` 可以被重载（[[over.ref]]）：`x->m` 被解释为 `(x.operator->())->m`，递归直到得到一个原生指针。这是智能指针和迭代器的基础，但那是 [[over.ref]] 的规则，不是本节的。

## 求值（¶3）

¶3：点前面的后缀表达式**会被求值**；求值结果与 `E2` 一起决定整个表达式的结果。脚注 44 强调：即使结果并不需要它——例如 `E2` 是静态成员——只要类成员访问表达式被求值，子表达式就会被求值。

```cpp run title="static-via-object.cpp" ok
#include <cstdio>

struct S { static int sm; };
int S::sm = 42;
S make() { std::puts("make() called"); return {}; }

int main() {
    int x = make().sm;   // 输出 "make() called"：对象表达式被求值，然后丢弃
    int y = S::sm;       // 不涉及任何对象
    return x == y ? 0 : 1;
}
```

这与 `sizeof(make().sm)` 不同：那是未求值操作数，`make()` 不会被调用。

## 对象表达式与伪析构（¶4）

¶4：把 `E1.E2` 中的 `E1` 称为**对象表达式**（object expression）。若对象表达式是**标量类型**，`E2` 必须指名**同一类型**（忽略 cv）的**伪析构函数**（[[expr.prim.id.dtor]]），而 `E1.E2` 是"返回 `void` 的无参函数"类型的 prvalue——它只能用于一次"名义上的"函数调用。这就是 `p->~T()` 在 `T = int` 时仍然合法的原因（调用的效果见 [[expr.call#4]]：销毁该标量对象）。

```cpp run title="pseudo-dtor-access.cpp" ok
#include <new>

using I = int;

int main() {
    int x = 0;
    x.~I();          // OK：伪析构函数调用，结束 x 的生命周期（C++20 起）
    ::new (&x) int(1);
    int* p = &x;
    p->~I();         // OK：等价于 (*p).~I()
    ::new (p) int(2);
    return x == 2 ? 0 : 1;
}
```

## 类类型必须完整（¶5）

¶5：否则，对象表达式必须是**类类型**，而且该类必须**完整**——除非成员访问出现在**该类自身的定义中**（例如成员函数体内、默认成员初始化器中写 `this->m`）。注 3：若"类完整时的查找结果"与"此处的查找结果"不同，程序非良构（[[class.member.lookup]]）。

```cpp title="incomplete-access.cpp" error
struct Fwd;
int get(Fwd& f);

struct Self {
    int a = 1;
    int b = this->a + 1;          // OK：在类自身的定义中，类此时尚不完整
};

int get(Fwd& f) { return f.x; }   // error: Fwd 不完整
```

## splice 作为成员（¶6）{{c++26}}

¶6：若 `E2` 是 *splice-expression*（[[expr.prim.splice]]），设 `T1` 为 `E1` 的类型，则 `E2` 必须指代 `T1` 的**成员**，或者一个**直接基类关系** `(T1, B)`。也就是说，`obj.[: r :]` 中反射 `r` 所代表的成员必须属于 `obj` 的类本身（静态反射 [[P2996R13]]）。

## 结果的类型与值类别（¶7–8）

¶7：若 `E2` 指代**位域**，`E1.E2` 也是位域（于是不能取地址、不能绑定非 `const` 引用）。接下来用 *cq* 表示 `const` 或无，*vq* 表示 `volatile` 或无，*cv* 表示任意 cv 限定集合。

¶8 是本节的核心，按 `E2` 的种类分派。先处理**引用**：

!!! std
    If E2 designates an entity that is declared to have type "reference to T", then E1.E2 is an lvalue of type T.

    若 `E2` 被声明为"`T` 的引用"，则 `E1.E2` 是类型为 `T` 的左值。

无论 `E1` 是左值还是亡值、是否 `const`——引用成员访问的结果**总是左值**，类型就是被引用的类型 `T`，**不叠加 `E1` 的 cv**。理由：引用成员所指的对象不是 `E1` 的子对象，`E1` 的生命周期和 const 性与它无关。

然后对非引用的情形：

| 列表项 | `E2` 指代 | `E1.E2` 的值类别 | 类型 |
|---|---|---|---|
| ¶8.1 | 静态数据成员（类型 `T`） | **lvalue** | `T`（不叠加 `E1` 的 cv） |
| ¶8.2 | 非静态数据成员（类型 *cq2 vq2* `T`） | `E1` 是 lvalue ⇒ **lvalue**；否则 ⇒ **xvalue** | *cq12 vq12* `T`；若成员是 `mutable` 则 *vq12* `T` |
| ¶8.3 | 重载集（成员函数） | 静态成员函数 ⇒ **lvalue**；非静态成员函数 ⇒ **prvalue** | `E2` 的函数类型 |
| ¶8.4 | 嵌套类型 | **非良构** | — |
| ¶8.5 | 成员枚举符（类型 `T`） | **prvalue** | `T`，值为枚举符的值 |
| ¶8.6 | 直接基类关系 `(D, B)` {{c++26}} | `E1` 是 lvalue ⇒ **lvalue**；否则 ⇒ **xvalue** | cv `B` |
| ¶8.7 | 其他 | **非良构** | — |

### ¶8.2：非静态数据成员与 cv 的"并集"

`E1` 的类型是 *cq1 vq1* `X`，成员声明的类型是 *cq2 vq2* `T`。结果类型的 cv 取二者的**并集**：只要对象或成员之一是 `const`，结果就是 `const`；`volatile` 同理。唯一例外：**`mutable` 成员**不继承 `const`（但仍继承 `volatile`）。

值类别跟随对象表达式：**左值对象的成员是左值，亡值对象的成员是亡值**（prvalue 对象已被实质化为亡值）。这是"移动一个将亡对象时，可以逐成员移动"的语言基础：`std::move(s).m` 自然就是亡值，可以直接绑定到 `T&&`。

```cpp run title="member-category.cpp" ok
#include <type_traits>
#include <utility>

int g = 0;
struct S {
    int m = 0;
    int& ref = g;
    mutable int mu = 0;
    static int sm;
    enum { E = 5 };
    int f() { return 1; }
    static int sf() { return 2; }
};
int S::sm = 0;
S make() { return {}; }

S s;
const S cs;
volatile S vs;

// ¶8.2：非静态数据成员
static_assert(std::is_same_v<decltype((s.m)), int&>);              // 左值.成员 → 左值
static_assert(std::is_same_v<decltype((std::move(s).m)), int&&>);  // 亡值.成员 → 亡值
static_assert(std::is_same_v<decltype((make().m)), int&&>);        // prvalue 实质化 → 亡值
static_assert(std::is_same_v<decltype((cs.m)), const int&>);       // cv 并集：const
static_assert(std::is_same_v<decltype((vs.m)), volatile int&>);    // cv 并集：volatile
static_assert(std::is_same_v<decltype((cs.mu)), int&>);            // mutable：不继承 const
// 引用成员：总是左值，不叠加 cv
static_assert(std::is_same_v<decltype((std::move(s).ref)), int&>);
static_assert(std::is_same_v<decltype((cs.ref)), int&>);
// ¶8.1：静态数据成员：总是左值
static_assert(std::is_same_v<decltype((make().sm)), int&>);
static_assert(std::is_same_v<decltype((cs.sm)), int&>);
// ¶8.3.1：静态成员函数：左值
static_assert(std::is_same_v<decltype((s.sf)), int (&)()>);
// ¶8.5：枚举符：prvalue
static_assert(std::is_same_v<decltype((s.E)), decltype(S::E)>);

int main() {}
```

!!! note "`decltype(s.m)` 与 `decltype((s.m))`"
    不带括号的 `decltype(e)`，当 `e` 是不加括号的类成员访问时，给出的是成员的**声明类型**（[[dcl.type.decltype]]）：`decltype(cs.m)` 是 `int`，不是 `const int`。只有加括号才按表达式的类型和值类别给出 `const int&`。上例因此一律加了括号。

### ¶8.3：成员函数

`E2` 指代重载集时，`E1.E2` 必须是成员函数调用的（可带括号的）左操作数，由重载决议（[[over.match]]）选出具体函数：

- ¶8.3.1 静态成员函数 ⇒ `E1.E2` 是**左值**（可以取出来用：`int (*p)() = s.sf;` 合法）；
- ¶8.3.2 非静态成员函数 ⇒ `E1.E2` 是**纯右值**，而且只能被立即调用。

为什么非静态成员函数的 `s.f` 不能单独存在？因为它代表的是"绑定了对象的函数"，C++ 没有这样的一等值（不像 C# 的 delegate 或 Python 的 bound method）。想要"绑定的函数"，请用 lambda 或 `std::bind_front`。

```cpp title="member-fn-access.cpp" error
struct S {
    int f() { return 1; }
    static int sf() { return 2; }
    struct Nested {};
};

void t(S s) {
    int (*p)() = s.sf;      // OK：¶8.3.1，静态成员函数是左值
    auto q = s.f;           // error: 非静态成员函数只能被调用（¶8.3）
    auto r = &s.f;          // error: 不能对绑定的成员函数取地址；应写 &S::f
    S::Nested n = s.Nested{};   // error: ¶8.4，不能经对象访问嵌套类型
    (void)p;
}
```

注 5：任何多余的括号都会被忽略，所以 `(s.f)()` 和 `((s.f))()` 都是合法的调用。

### ¶8.6：直接基类关系 {{c++26}}

静态反射引入了一种新的"成员"：**直接基类关系**。`std::meta::bases_of(^^D, ctx)[i]` 返回的反射代表"`D` 以 `B` 为直接基类"这一关系，而 `d.[: r :]` 指代 `d` 的那个**直接**基类子对象。¶8.6：若 `E2` 指代直接基类关系 `(D, B)`，且 `D` 是 `E1` 的 cv 去除类类型或其基类，则先把 `E1` 隐式转换为"cv `D` 的引用"（左值或右值引用随 `E1`），结果指代其类型为 `B` 的直接基类子对象，类型为 cv `B`，值类别随 `E1`。

标准例 1 的意义在于消歧：

```cpp title="splice-base.cpp"
#include <meta>

struct B { int b; };
struct C : B { int get() const { return b; } };
struct D : B, C { };          // D 有两个 B 子对象：直接的，以及经 C 间接的

constexpr int f() {
    D d = {1, {}};
    // 通过 bases_of 得到的反射，精确指代 D 的"直接" B 子对象，
    // 而普通的 static_cast<B&>(d) 在这里是二义的
    B& b = d.[: std::meta::bases_of(^^D, std::meta::access_context::current())[0] :];
    b.b += 10;
    return 10 * b.b + d.get();
}
static_assert(f() == 110);
```

（本机 Clang 尚未实现静态反射，此例未经编译验证。）

## 二义的基类（¶9）

¶9：若 `E2`（必要时经重载决议后）指代**非静态成员**，而 `E2` 所直接属于的类是 `E2` 的**指派类**（designating class，[[class.access.base]]）的**二义基类**，程序非良构。注 6：若命名类是对象表达式类型的二义基类，同样非良构。

```cpp title="ambiguous-base.cpp" error
struct A { int x; };
struct L : A {};
struct R : A {};
struct D : L, R {};

int f(D& d) {
    int a = d.L::x;     // OK：命名类 L，A 是 L 的无二义基类
    return d.x + a;     // error: 名字查找二义（两个 A::x）
}

int g(D& d) {
    return d.A::x;      // error: A 是 D 的二义基类
}
```

## 对象类型不相似：UB（¶10）

!!! std
    If E2 designates a non-static member (possibly after overload resolution) or direct base class relationship and the result of E1 is an object whose type is not similar to the type of E1, the behavior is undefined.

    若 `E2` 指代非静态成员或直接基类关系，而 `E1` 的结果是一个类型与 `E1` 的类型不相似的对象，行为未定义。

"相似"见 [[conv.qual]]（忽略各层 cv）。这条规则把"经由错误类型访问成员"明确定为 UB，而不必等到真正读写成员的值时才由 [[basic.lval#11]] 的严格别名规则判定——**仅仅形成成员访问表达式**就已经是 UB，哪怕成员是不读的（比如只取 `&p->m` 的地址或调用一个不访问数据的成员函数）。标准例 2：

```cpp run title="not-similar.cpp" ub
struct A { int i; };
struct B { int j; };
struct D : A, B {};

int main() {
    D d{};
    int a = static_cast<B&>(d).j;        // OK：对象表达式指代 d 的 B 子对象
    int b = reinterpret_cast<B&>(d).j;   // UB: reinterpret_cast 不调整地址；结果指代的是 d（或其 A 子对象），类型不是 B
    return a + b;
}
```

`reinterpret_cast<B&>(d)` 的结果仍然指代 `d` 本身（`D` 与 `B` 不是指针可互转的，见 [[expr.reinterpret.cast]]），所以 `.j` 访问的对象类型是 `D` 而不是 `B`——UB。`static_cast` 则做了正确的指针调整。Clang 对这种写法有专门的警告 `-Wreinterpret-base-class`（"behaves differently from 'static_cast'"）。

与此相关的还有：

- **生命周期之外的访问**：在对象的生命周期开始前或结束后访问其非静态数据成员或调用非静态成员函数，是 UB（[[basic.life#7]]、[[basic.life#8]]）。
- **联合体的非活跃成员**：`u.f` 若 `f` 不是活跃成员，读取其值是 UB（`u.f` 不在生命周期内）；但**赋值** `u.f = x` 可以通过 [[class.union]] 的规则隐式切换活跃成员。形成表达式 `u.f` 本身不是 UB——联合体的所有成员都与联合体指针可互转，`u` 的类型就是 `U`，¶10 不适用。

```cpp run title="union-access.cpp" ok
union U { int i; float f; };

int main() {
    U u{.i = 1};
    u.f = 2.0f;           // OK：赋值使 f 成为活跃成员（[class.union]）
    float x = u.f;        // OK
    // int y = u.i;       // UB: i 不在生命周期内
    return x == 2.0f ? 0 : 1;
}
```

## 实现视角

!!! impl
    - 非静态数据成员访问编译为"对象基址 + 常量偏移"；`p->m` 就是一次带偏移的加载。这也是为什么 `offsetof` 对标准布局类型有定义。
    - 编译器利用 ¶10 和严格别名规则做**基于类型的别名分析**（TBAA）：经 `A*` 和 `B*` 的成员访问被假定不重叠。
    - 对 `p->static_member`，即使 `p` 是空指针，生成的代码通常也不会解引用 `p`——但标准层面 `*p` 已经对空指针求值了（¶2 的化归），是 UB；UBSan 的 `-fsanitize=null` 会报告这种访问。

## 陷阱

!!! pitfall "`std::move(obj).ref` 不是亡值"
    引用成员总是左值。泛型代码中逐成员转发时，若成员可能是引用，需要用 `std::forward_like<Self>(self.m)`（C++23）这类工具来按对象表达式的值类别转发，而不是依赖 `std::move(self).m`。

!!! pitfall "`p->m` 永远不是亡值"
    `std::move(p)->m` 仍是左值：箭头先化归为 `(*p).m`，而 `*p` 是左值。要得到亡值，写 `std::move(*p).m`。

!!! pitfall "`const` 成员函数里修改成员"
    在 `const` 成员函数中，`this->m` 的对象表达式类型是 `const X`，按 ¶8.2 结果是 `const` 的——这就是 `const` 成员函数不能修改成员的语言机制。`mutable` 是唯一的豁免，而它对 `const` **对象**同样有效：修改 `const` 对象的 `mutable` 成员不是 UB（[[dcl.type.cv]]）。

## 思考题

!!! question "思考题 1"
    `struct S { const int c = 0; int& r; }; S s{0, x};` 中，`decltype((std::move(s).c))` 和 `decltype((std::move(s).r))` 分别是什么？

<details markdown="1">
<summary>答案</summary>

`std::move(s).c`：¶8.2，`E1` 是亡值 ⇒ 亡值；cv 并集：`s` 非 const，成员是 `const int` ⇒ `const int`。结果 `const int&&`。`std::move(s).r`：引用成员 ⇒ 总是左值，类型 `int` ⇒ `int&`。
</details>

!!! question "思考题 2"
    `struct S { static int n; }; S* p = nullptr; int x = p->n;` 是否 UB？`int y = decltype(*p)::n;` 呢？

<details markdown="1">
<summary>答案</summary>

`p->n` 化归为 `(*p).n`，¶3 规定对象表达式 `*p` 会被求值（脚注 44 明确说即使 `E2` 是静态成员也要求值），而对空指针求值一元 `*` 是 UB（[[expr.unary.op]]）。实践中编译器不会生成解引用指令，但它仍是 UB，且在常量求值中会被拒绝。`decltype(*p)` 是未求值操作数，得到 `S&`；`decltype(*p)::n` 不合法——`S&` 不能作为嵌套名说明符（需要 `std::remove_reference_t<decltype(*p)>::n`），但无论如何不涉及求值。
</details>

## 小结

!!! summary
    - `E1->E2` ≡ `(*(E1)).E2`；`(*E1)` 是左值，所以箭头访问永远不会产生亡值。
    - 对象表达式总会被求值，即使 `E2` 是静态成员；访问非静态成员时它必须是 glvalue（prvalue 被实质化）。
    - 引用成员 ⇒ 左值，类型为被引用类型，不叠加 cv；静态数据成员 ⇒ 左值；非静态数据成员 ⇒ 值类别随对象，cv 取并集，`mutable` 免 `const`；静态成员函数 ⇒ 左值；非静态成员函数 ⇒ 只能调用的 prvalue；枚举符 ⇒ prvalue；嵌套类型 ⇒ 非良构。
    - C++26：`.` 后可跟 splice；直接基类关系作为"成员"，精确指代直接基类子对象。
    - 对象实际类型与 `E1` 的类型不相似时访问非静态成员 ⇒ UB（¶10），与严格别名规则互为补充。
