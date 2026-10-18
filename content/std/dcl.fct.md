---
title: 函数声明符
summary: 函数类型由什么组成：形参声明子句、形参类型列表的调整（数组/函数→指针、去顶层 cv）、noexcept 与 cv/ref 限定属于类型而默认实参与 requires 子句不属于；省略号与 C++26 弃用的无逗号省略号；显式对象参数（deducing this）；"可憎的"函数类型；简写函数模板；返回类型的限制
status: draft
since: c++98
papers: P0012R1, P0847R7, P3176R1
related: dcl.decl, dcl.fct.default, dcl.fct.def, over.match.funcs, expr.call, except.spec, conv.fctptr, dcl.spec.auto, temp.variadic, expr.prim.lambda, depr.ellipsis.comma
tags: 函数类型, 形参, noexcept, deducing this, 简写函数模板
updated: 2026-10-17
---

函数声明符 `D1 ( 形参 ) cv ref noexcept` 是声明符家族中最复杂的一员。本节（[dcl.fct]）回答这些问题：

- 一个**函数类型**由哪些部分组成？哪些写在声明里的东西**不是**类型的一部分？
- 形参的类型在进入函数类型之前经过了怎样的**调整**？
- 省略号 `...`、形参包、简写函数模板 `auto` 形参如何在语法上区分？
- C++23 的**显式对象参数**（`this Self&& self`）有哪些限制？
- 带 `const`、`&` 的函数类型（`int() const`）在什么地方可以出现？

这些规则决定了重载（两个声明是不是同一个函数）、函数指针的类型匹配、名字修饰与 ABI。读之前最好熟悉 [[dcl.decl]] 中"从 `T D` 递归求类型"的框架。

## 函数类型的构成（¶1）

¶1 在声明 `T D` 中（`T` 可以为空——构造函数、析构函数、转换函数），若 `D` 形如

```
D1 ( parameter-declaration-clause ) cv-qualifier-seq(opt) ref-qualifier(opt)
   noexcept-specifier(opt) attribute-specifier-seq(opt) trailing-return-type(opt)
```

则：

- *derived-declarator-type-list* 照常从 `T D1` 获得（¶1.2）；但若 *declarator-id* 是**转换函数名**（`operator int`），它为空（¶1.1）——转换函数的"返回类型"由名字决定，不由外层说明符决定。
- **声明的返回类型** `U`（¶1.3–1.5）：有尾置返回类型时，`T` 必须是单独的 `auto`，`U` 是尾置返回类型给出的类型；转换函数见 [[class.conv.fct]]；否则 `U` 就是 `T`。

于是 *declarator-id* 的类型是：

> "*list* `noexcept`(可选) 函数（形参类型列表）*cv*(可选) *ref*(可选) 返回 `U`"

其中 `noexcept` 出现当且仅当异常规格是**不抛出的**（non-throwing，[[except.spec]]）。这样的类型称为**函数类型**；末尾的属性属于函数类型。

把它拆开看，一个函数类型由以下部分组成（¶13 再次确认）：

| 组成部分 | 例子 | 属于函数类型？ |
|---|---|---|
| 返回类型 | `int` vs `const int` | 是（脚注 68：cv 是返回类型的重要组成部分） |
| 形参类型列表（调整后） | `(int, char*)` | 是 |
| 是否有省略号 | `(int, ...)` | 是（属于形参类型列表） |
| cv 限定 | `() const` | 是 |
| 引用限定 | `() &&` | 是 |
| 异常规格 | `noexcept` | 是（C++17 起） |
| 默认实参 | `(int = 0)` | **否** |
| 尾置 requires 子句 | `requires C<T>` | **否** |
| 契约说明符 | `pre(x > 0)` | **否**（[[dcl.contract]]） |
| 形参名字 | `(int x)` | **否** |
| 属性（如 `[[nodiscard]]`） | | 否（属于函数实体或函数类型的属性语义各异） |

```cpp title="fn-type-parts.cpp" ok
#include <type_traits>

static_assert(!std::is_same_v<const int(), int()>);      // 返回类型的 cv 也算（Clang 会警告它"无效果"）
static_assert(!std::is_same_v<void() noexcept, void()>); // noexcept 属于类型

void nf() noexcept;
void (*pf)() = nf;                  // OK：函数指针转换可以丢掉 noexcept（[conv.fctptr]）
// void (*pnf)() noexcept = pf;     // error: 不能凭空加上 noexcept

int main() { }
```

## 形参声明子句（¶2–4）

¶2 文法：

```
parameter-declaration-clause:
    ...
    parameter-declaration-list(opt)
    parameter-declaration-list , ...
    parameter-declaration-list ...          // C++26 起弃用
parameter-declaration:
    attr(opt) this(opt) decl-specifier-seq declarator
    attr(opt) decl-specifier-seq declarator = initializer-clause
    attr(opt) this(opt) decl-specifier-seq abstract-declarator(opt)
    attr(opt) decl-specifier-seq abstract-declarator(opt) = initializer-clause
```

注意 `this` 与默认实参 `= …` 在文法上互斥：显式对象参数不能有默认实参。形参前的属性属于形参。

### 空形参列表与 (void)（¶3）

¶3 形参声明子句决定调用时能传哪些实参以及如何处理它们（[[expr.call]]）。

- 子句为空：函数不接受实参。（与 C 不同：C 中 `int f();` 是"未指定形参"，直到 C23 才改为与 C++ 一致。）
- 形参列表由**单个无名非对象形参**组成、且其类型**与 `void` 相同**（按 [[temp.over.link]] 判断）时，被解释为空形参列表。
- 除此特例外，形参不能具有 cv `void` 类型。
- volatile 限定的形参类型已弃用（[[depr.volatile.type]]）。

```cpp title="void-param.cpp" error
using V = void;
void g0(V);          // OK：类型与 void 相同的单个无名形参 ⇒ 零个形参
void p(void, int);   // error: void 必须是唯一的形参
void q(void x);      // error: 有名字的 void 形参

template<class T> struct S3 { void f(T); };
S3<void> z;          // error: 实例化后 f 有一个 void 类型的形参——不是"写成 (void)"
```

最后一个例子表明：只有在**声明时**形参列表就是 `(void)`（或等价的非依赖别名）才算空列表；模板实例化时替换出来的 `void` 不算。标准例 1 更精细地区分了两种情况：

```cpp title="void-t-param.cpp"
#include <type_traits>
template<class T> struct S  { void f(std::void_t<T*>); };     // #1：形参类型依赖于 T
S<int> x;            // error（按标准）：#1 有一个 void 类型的形参

template<class T> struct S2 { void f(std::void_t<int*>); };   // #2：形参类型不依赖于 T，就是 void
S2<int> y;           // OK：#2 是零形参函数
```

区别在于 `std::void_t<T*>` 是**依赖的**：声明时还不知道它是 `void`，所以它是"一个形参"；实例化后变成 `void` 形参，非良构。`std::void_t<int*>` 不依赖，声明时就"与 `void` 相同"，于是是空列表。截至写作时，Clang 23 对 `S<int>` 不报错（把它当作零形参函数），与标准例子不一致。

### 省略号（¶4、¶6）

¶4 子句以省略号或函数形参包结尾时，实参个数必须 **≥** 既没有默认实参、也不是形参包的形参个数。在语法正确且 `...` 不属于抽象声明符的位置，`...` 与 `, ...` 同义。

!!! warning "无逗号的省略号 {{deprecated}} {{c++26}}"
    形如 *parameter-declaration-list* `...`（`void f(int...)`）的子句已弃用（[[depr.ellipsis.comma]]，[[P3176R1]]）。原因是它与形参包的语法过于接近：`void f(auto...)` 是形参包，`void f(int...)` 却是 C 风格可变参数函数，`void h(auto......)` 则两者都有。新代码应一律写 `, ...`。Clang 23 对此给出 `-Wdeprecated-missing-comma-variadic-parameter` 警告。

¶6 形参类型列表含省略号的函数称为**可变参数函数**（vararg function）。通过省略号传入的实参经过默认实参提升（[[expr.call]]），在函数内用 `<cstdarg>` 的 `va_start`/`va_arg` 访问。`printf` 是典型：

```cpp title="vararg.cpp" ok
#include <cstdarg>
#include <cstdio>

int sum(int n, ...) {               // 推荐写法：带逗号
    std::va_list ap;
    va_start(ap, n);
    int s = 0;
    for (int i = 0; i < n; ++i) s += va_arg(ap, int);
    va_end(ap);
    return s;
}
void all(...) { }                   // C++ 一直允许只有省略号（C 直到 C23 才允许）

int main() {
    all(1, "two", 3.0);
    return sum(3, 1, 2, 3) == 6 ? 0 : 1;
}
```

¶27 补充了 `...` 前没有逗号时的歧义消解：若形参类型**命名了一个尚未展开的模板形参包**或**包含 `auto`**，`...` 属于抽象声明符（声明函数形参包）；否则属于形参声明子句（C 风格省略号）。

```cpp title="ellipsis-ambig.cpp" ok
template<class... T> void a(T...);   // T 是未展开的包 ⇒ 函数形参包
template<class T>    void b(T...);   // T 不是包 ⇒ 等价于 b(T, ...)（已弃用写法，Clang 警告）
void c(auto...);                     // 含 auto ⇒ 函数形参包
void d(int...);                      // ⇒ d(int, ...)（已弃用写法）
int main() { }
```

## 形参类型的调整（¶5）

¶5 函数类型按以下步骤确定：

1. 每个形参的类型（包括函数形参包）由它自己的 *parameter-declaration* 确定；
2. "`T` 的数组"类型或函数类型 `T` 的形参被**调整**为"指向 `T` 的指针"；
3. 得到形参类型列表后，**删除每个形参类型的顶层 cv 限定符**。

调整后的类型列表加上"是否有省略号或函数形参包"，就是函数的**形参类型列表**（parameter-type-list）。

```cpp title="param-adjust.cpp" error
void f(char*);                  // #1
void f(char[]) { }              // 定义 #1：char[] → char*
void f(const char*) { }         // OK：另一个重载（const 不是顶层的）
void f(char *const) { }         // error: 重定义 #1（顶层 const 被删除）

void g(char(*)[2]);             // #2
void g(char[3][2]) { }          // 定义 #2：char[3][2] → char(*)[2]（只调整最外层）
void g(char[3][3]) { }          // OK：另一个重载，char(*)[3]

void h(int x(const int));       // #3：形参是函数类型 → 指针；内层的 const 也是顶层的，被删除
void h(int (*)(int)) { }        // 定义 #3
```

为什么这样设计？

- **数组 → 指针**：C 的历史。数组不能按值传递，`f(char[])` 从来就意味着传指针。代价是边界信息丢失。
- **函数 → 指针**：函数也不能按值传递；`void h(int x(int))` 与 `void h(int (*x)(int))` 在 C 中就是同义写法。
- **删除顶层 cv**：顶层 cv 只影响函数**内部**能否修改形参副本，与调用者无关。若它属于函数类型，`void f(int)` 与 `void f(const int)` 将是两个可以重载的函数，而调用时无从区分——所以它们必须是同一个函数。

注 3 强调：**调整不影响形参本身的类型**。在函数体内，`const int p` 仍然是 const 的；`decltype(p)` 仍是 `const int`。所以 `int(*)(const int p, decltype(p)*)` 与 `int(*)(int, const int*)` 是同一类型——第二个形参中的 `decltype(p)` 是 `const int`，它的 const 不是顶层的（是指针指向的类型的 const），不会被删除。

```cpp title="adjust-not-param.cpp" ok
#include <type_traits>
static_assert(std::is_same_v<int(*)(const int p, decltype(p)*), int(*)(int, const int*)>);

void f(const int x) {
    static_assert(std::is_same_v<decltype(x), const int>);   // 形参本身仍是 const
}
void f(int);    // 与上面是同一个函数的重声明
int main() { f(1); }
```

!!! tip "在声明中省略顶层 const，在定义中加上"
    由于顶层 const 不属于函数类型，常见的风格是：头文件中声明 `void set(int v);`，实现中定义 `void set(const int v) { … }`，防止函数体内误改形参。这是合法且有意为之的。

## 显式对象参数 {{c++23}}（¶7–10）

¶7 **显式对象参数声明**（explicit-object-parameter-declaration）是带 `this` 说明符的形参声明。它只能作为形参列表的**第一个**形参，并且只能出现在：

- ¶7.1 成员函数或成员函数模板的声明中；
- ¶7.2 模板化成员函数的显式实例化或显式特化中；
- ¶7.3 lambda 声明符中（[[expr.prim.lambda]]）。

带显式对象参数的 *member-declarator* 不能有 *ref-qualifier* 或 *cv-qualifier-seq*，也不能声明为 `static` 或 `virtual`。

¶8 以显式对象参数声明的形参称为**显式对象参数**（explicit object parameter），它不能是函数形参包。有显式对象参数的非静态成员函数称为**显式对象成员函数**（explicit object member function）；没有的称为**隐式对象成员函数**（implicit object member function）。

¶9 非静态成员函数的**对象参数**（object parameter）是显式对象参数或隐式对象参数（[[over.match.funcs]]）。

¶10 **非对象参数**（non-object parameter）是除显式对象参数外的形参。成员函数的**非对象形参类型列表**（non-object-parameter-type-list）是去掉显式对象参数后的形参类型列表。

```cpp run title="deducing-this.cpp" ok
#include <cstdio>
#include <type_traits>
#include <utility>

struct C {
    int v = 1;
    void f(this C& self) { self.v++; }               // 显式对象参数；体内没有 this
    template<class Self>
    int g(this Self&& self, int k) {                 // 推导 Self：一份代码覆盖 &、const&、&& 重载
        return std::forward<Self>(self).v + k;
    }
};
// 显式对象成员函数的地址是普通函数指针，不是成员函数指针
static_assert(std::is_same_v<decltype(&C::f), void (*)(C&)>);

struct Base {
    template<class Self> auto name(this const Self&) { return Self::tag; }  // "静态多态"无需 CRTP
};
struct D1 : Base { static constexpr const char* tag = "D1"; };

int main() {
    C c;
    c.f();                        // Self 不参与：调用 C::f
    auto pf = &C::f;
    pf(c);                        // 像普通函数一样调用
    std::printf("%d %d %d\n", c.v, c.g(10), std::move(c).g(20));   // 3 13 23
    std::printf("%s\n", D1{}.name());                              // D1：Self 推导为 D1

    auto fib = [](this auto const& self, int n) -> int {           // 递归 lambda
        return n < 2 ? n : self(n - 1) + self(n - 2);
    };
    std::printf("%d\n", fib(10));                                  // 55
}
```

限制汇总（标准例 4 扩展）：

```cpp title="deducing-this-bad.cpp" error
struct C {
    void h(this C) const;                    // error: 不能有 cv 限定
    void i(this C&) &;                       // error: 不能有引用限定
    static void s(this C);                   // error: 不能是 static
    virtual void v(this C&);                 // error: 不能是 virtual
    void k(int, this C&);                    // error: 只能是第一个形参
    template<class... Ts> void p(this Ts...);// error: 不能是形参包
    void body(this C& self) { this->k(1, self); }   // error: 体内不能用 this（[expr.prim.this]）
};
void free_fn(this int);                      // error: 只能用于成员函数
```

为什么禁止 cv/ref 限定与 `virtual`？cv 和 ref 限定符本来就是用来描述**隐式**对象参数的类型的（[[over.match.funcs]]）；有了显式对象参数，对象的类型已经写在 `this` 形参上，再写 `const` 既冗余又可能矛盾。`virtual` 被禁止是因为显式对象参数常常是模板（`this Self&&`），而函数模板不能是虚函数；即使不是模板，"对象参数类型可以是任意类型（甚至按值 `this C`）"也与虚分派的 `this` 调整模型不相容。此外，构造函数和析构函数也不能有显式对象参数（[[class.ctor]]、[[class.dtor]]）。

## 函数类型上的 cv 与 ref 限定（¶11–12）

带 *cv-qualifier-seq* 或 *ref-qualifier* 的函数类型，如 `int(int) const`、`void() &&`，社区称为"**可憎的函数类型**"（abominable function types）：它们是真实的类型，但几乎没有地方能用。

¶11 这样的函数类型（包括通过 typedef 名得到的）**只能**出现在：

- ¶11.1 非静态成员函数的函数类型；
- ¶11.2 成员指针所指向的函数类型（`int (S::*)(int) const`）；
- ¶11.3 函数 typedef 或别名声明的顶层函数类型（`using F = int(int) const;`）；
- ¶11.4 类型模板形参的默认实参中的 *type-id*；
- ¶11.5 类型模板形参的模板实参（`std::is_function<int() const>`）；
- ¶11.6 *reflect-expression* 的操作数（`^^void(int) const &`）{{c++26}}。

```cpp title="abominable.cpp" error
#include <type_traits>
typedef int FIC(int) const;
FIC f;                    // error: 不是成员函数
FIC* pf;                  // error: 不能形成指向它的普通指针
FIC& rf = *pf;            // error: 不能形成指向它的引用
struct S {
    FIC f;                // OK：声明成员函数 int f(int) const
};
FIC S::*pm = &S::f;       // OK：成员指针
static_assert(std::is_function_v<FIC>);   // OK：作为模板实参
```

它们存在的意义：成员函数的类型需要一个"去掉类之后"的表示，元编程（如 `std::is_function` 的实现、成员函数指针的类型分解）需要能匹配 `R(Args...) const &&` 这些形式——标准库中 `std::is_function` 的朴素实现需要 48 个偏特化（cv × ref × noexcept × 省略号）正是因为它们。

¶12 函数声明符中的 *cv-qualifier-seq* 与"在函数类型外面加 cv"不是一回事：后者被**忽略**。注 5：带 cv-qualifier-seq 的函数类型**不是** cv 限定类型；不存在 cv 限定的函数类型。

```cpp title="const-fn-typedef.cpp" ok
#include <type_traits>
typedef void F();
struct S {
    const F f;            // OK：等价于 void f();——const 被忽略，不是 void f() const
};
void S::f() { }
static_assert(std::is_same_v<decltype(&S::f), void (S::*)()>);
int main() { }
```

## 什么属于函数类型（¶13）

¶13 返回类型、形参类型列表、*ref-qualifier*、*cv-qualifier-seq*、异常规格——**是**函数类型的一部分；默认实参（[[dcl.fct.default]]）与尾置 *requires-clause*——**不是**。注 6：函数类型在函数指针、函数引用、成员函数指针的赋值与初始化时被检查。

后果：

- **默认实参不随函数指针传递**：`int (*p)(int) = &f;` 之后 `p()` 非良构，即使 `f` 有默认实参。
- **noexcept 影响重载与重声明**：不能仅以 `noexcept` 区分重载；同一函数的所有声明必须有兼容的异常规格（[[except.spec]]）。
- **noexcept 可以被推导**：`template<class R, class... A, bool NE> void g(R(*)(A...) noexcept(NE));` 能推导出 `NE`。
- **requires 子句不是类型的一部分，却能区分声明**：两个只有约束不同的函数模板（或模板化函数）声明不**对应**（[[basic.scope.scope]]），是不同的实体。

```cpp title="noexcept-redecl.cpp" error
void ne() noexcept;
void ne();                // error: 与前一声明的异常规格不一致
void ov(int) noexcept;
void ov(int);             // error: 不能仅以 noexcept 重载
```

¶14–15（例、注）`int fseek(FILE*, long, int);` 的读法；同一个名字可以用于同一作用域中的多个函数——即重载（[[over]]）。

## 返回类型的限制（¶16–18）

¶16 返回类型必须是**非数组的对象类型**、**引用类型**或 **cv `void`**。也就是说函数**不能返回数组**、**不能返回函数**（但可以返回指向它们的指针或引用）。注 8：占位符类型的数组也被视为数组类型（所以 `auto f() -> auto[3]` 一类写法同样被禁止）。

```cpp title="return-type.cpp" error
int arr()[3];             // error: 不能返回数组
int fn()();               // error: 不能返回函数
auto ok() -> int(*)[3];   // OK：返回指向数组的指针
auto ok2() -> int(&)();   // OK：返回函数引用

struct A { virtual void f() = 0; };
A g();                    // OK：声明返回抽象类的函数（C++20 起只在定义与调用处检查）
```

¶17 volatile 限定的返回类型已弃用（[[depr.volatile.type]]）。

¶18 **不能在返回类型或形参类型中定义类型**：

```cpp title="no-define.cpp" error
void def(struct S { } s);   // error: 不能在形参类型中定义 S
struct S2 { } ret();        // error: 不能在返回类型中定义 S2
```

（C 允许前者，但定义的类型作用域只在原型内，几乎没用；C++ 直接禁止。）

## 用 typedef 声明函数（¶19）

¶19 函数类型的 typedef 可以用来**声明**函数，但**不能用来定义**函数。

```cpp title="typedef-fn.cpp" error
typedef void F();
F  fv;              // OK：等价于 void fv();
F  fv { }           // error: 不能用 typedef 定义函数
void fv() { }       // OK：fv 的定义
```

理由：定义需要形参的**名字**，而函数类型（typedef）中没有形参名。

## 形参名（¶20–21）

¶20 形参名字是可选的；若出现在函数定义中，它命名形参。注 9：形参名在函数定义中也可以省略（未使用的形参），不同声明之间形参名可以不同。

¶21（例）比较 `*fpi(int)`（函数，返回 `int*`）与 `(*pif)(const char*, const char*)`（函数指针）：前者的结合是 `*(fpi(int))`，声明与表达式中的用法一致——"先调用，再解引用"。注 10：复杂的返回类型用 typedef 或尾置返回类型更清楚：`auto fpif(int) -> int(*)(int);`。尾置返回类型的真正用武之地是返回类型依赖形参的场合：`auto add(T t, U u) -> decltype(t + u)`。

## 非模板函数（¶22）

¶22 **非模板函数**（non-template function）是不是函数模板特化的函数。注 11：函数模板不是函数。类模板的成员函数（实例化后）是非模板函数——它不是函数模板的特化，尽管它是"模板化的"。这个区分在重载决议的决胜规则中出现（[[over.match.best]]：非模板函数优先于函数模板特化）。

## 简写函数模板 {{c++20}}（¶23–25）

¶23 **简写函数模板**（abbreviated function template）是形参类型中含有一个或多个**泛型形参类型占位符**（[[dcl.spec.auto]]）的函数声明。它等价于一个函数模板，模板形参列表中按出现顺序为每个占位符引入一个虚构的类型模板形参：

- `auto` → 无约束的类型形参；
- `C auto` → 带类型约束 `C` 的类型形参；
- 对应的形参声明是函数形参包时，虚构的形参也是模板形参包；
- 占位符含 `decltype(auto)` 时非良构。

```cpp title="abbrev.cpp" ok
#include <concepts>
#include <type_traits>

void g1(const std::integral auto*, std::floating_point auto&);
// 功能上等价于：template<std::integral T, std::floating_point U> void g1(const T*, U&);

template<> void g1<int>(const int*, double&);     // 可以像普通函数模板一样特化

auto sum(auto... xs) { return (xs + ... + 0); }    // 虚构的形参是模板形参包
static_assert(std::is_same_v<decltype(sum(1, 2L)), long>);

int main() { return sum(1, 2, 3) - 6; }
```

"功能上等价（但不等价）"（functionally equivalent but not equivalent）是 [[temp.over.link]] 的术语：两种写法接受和拒绝同样的程序，但它们不是同一个模板的重声明——不能一处用简写形式声明、另一处用完整形式定义。

¶24 简写函数模板也可以有模板头，虚构的形参**追加**在显式声明的模板形参之后：

```cpp title="abbrev-head.cpp" ok
#include <concepts>
template<typename T, std::integral U>
void g(T x, U y, std::integral auto z) { (void)x; (void)y; (void)z; }
// 等价于 template<typename T, std::integral U, std::integral W> void g(T, U, W);

int main() {
    g<double, int, long>(1.0, 2, 3L);   // 第三个显式模板实参对应 auto 引入的形参
}
```

¶25 块作用域中的函数声明不能声明简写函数模板（模板只能在命名空间或类作用域声明，[[temp.pre]]）。

```cpp title="abbrev-bad.cpp" error
void f(decltype(auto) x);         // error: decltype(auto) 不能作为泛型形参占位符
void blk() { void h(auto); }      // error: 块作用域中不能声明简写函数模板
```

## 形参包（¶26）

¶26 含省略号的 *declarator-id* 或抽象声明符只能用在 *parameter-declaration* 中：在形参声明子句中，它声明**函数形参包**；在模板形参列表中，它声明**模板形参包**（[[temp.param]]）。函数形参包是一个包展开（[[temp.variadic]]）。

```cpp title="fn-param-pack.cpp" ok
template<typename... T> void f(T (* ...t)(int, int)) { }   // t 是函数指针的包
int add(int, int) { return 0; }
float subtract(int, int) { return 0; }
int main() { f(add, subtract); }   // T = {int, float}
```

## 实现视角

!!! impl
    - **名字修饰**：Itanium ABI 中函数类型编码为 `F <返回类型> <形参类型…> E`，`noexcept` 函数类型编码为 `Do F…E`（C++17 起），ref 限定符 `R`/`O` 放在 `E` 之前，cv 限定的成员函数在嵌套名里以 `K`（const）、`V`（volatile）标记。顶层 cv 被删除的规则使 `f(int)` 与 `f(const int)` 修饰为同一个名字 `_Z1fi`。
    - **noexcept 与 ABI**：C++17 把 noexcept 纳入类型系统后，作为形参的函数指针类型（如 `void g(void(*)() noexcept)`）的修饰名会变化，这是 C++14 → C++17 少数影响 ABI 的语言改动之一；GCC 为此提供了 `-Wnoexcept-type` 警告。
    - **显式对象成员函数的调用约定**：它们本质上就是以对象为第一个实参的普通函数。`&C::f` 得到普通函数指针，调用约定与自由函数相同；Itanium ABI 中其修饰名带 `H` 标记以区别于隐式对象成员函数。
    - **可变参数函数**：在 x86-64 System V ABI 上，调用可变参数函数时 `%al` 存放使用的向量寄存器个数；AArch64 的 Apple 平台则把所有可变实参放在栈上——这是为什么用错误的原型（缺少 `...`）调用可变参数函数在 Apple Silicon 上会得到错误结果。

## 历史与演进

!!! history
    - **C++98**：形参类型调整规则、cv 限定成员函数、异常规格 `throw(...)`（不属于类型）。
    - **C++11**：尾置返回类型、引用限定符、`noexcept`、函数形参包。
    - **C++17**：`noexcept` 成为函数类型的一部分（[[P0012R1]]）；动态异常规格 `throw(T)` 被移除（C++20 移除了 `throw()`）。
    - **C++20**：简写函数模板（`auto` 形参，来自 Concepts TS 的"简写语法"的一部分）；volatile 形参与返回类型弃用；抽象类返回类型只在定义与调用处检查。
    - **C++23**：显式对象参数（deducing this，[[P0847R7]]）。
    - **C++26**：无逗号的省略号 `f(int...)` 弃用（[[P3176R1]]）；可憎函数类型可以作为 `^^` 的操作数。

## 陷阱

!!! pitfall "`void f(int a[10])` 的 10 没有意义"
    边界被调整掉，`sizeof(a)` 是指针大小，传入任何 `int*` 都可以。用 `int (&a)[10]` 或 `std::span<int, 10>` 保留边界。

!!! pitfall "默认实参不是类型的一部分"
    `std::function<int()> fn = f;`（`f` 为 `int f(int = 0)`）非良构：`f` 的类型是 `int(int)`。需要包一层 lambda：`[] { return f(); }`。

!!! pitfall "`int f(int...)` 不是形参包"
    它是 `int f(int, ...)`——C 风格可变参数函数，而且 C++26 起已弃用。形参包需要 `template<class... T> int f(T...)` 或 `int f(auto...)`。

!!! pitfall "显式对象参数按值"
    `void f(this C self)` 每次调用都**复制**对象，函数体内对 `self` 的修改不影响调用者。这有时正是想要的（如小型值类型），有时则是隐蔽的 bug。另外，`this Self&& self` 在派生类对象上调用时 `Self` 推导为**派生类**，访问 `self.member` 可能找到派生类中隐藏了基类成员的同名成员。

## 思考题

!!! question "思考题 1"
    下面哪些声明是同一个函数的重声明？
    ```cpp
    void f(int (*)[5]);
    void f(int [][5]);
    void f(int [5][5]);
    void f(int (*const)[5]);
    void f(const int (*)[5]);
    void f(int [5][6]);
    ```

<details markdown="1">
<summary>答案</summary>

前四个是同一个函数：数组形参调整为指向元素的指针（只调整最外层），`int [][5]`、`int [5][5]` 都变成 `int (*)[5]`；`int (*const)[5]` 的 `const` 是顶层的，被删除。第五个 `const int (*)[5]` 中 const 修饰元素（指向的类型），不是顶层，是另一个重载。第六个调整为 `int (*)[6]`，也是另一个重载。
</details>

!!! question "思考题 2"
    为什么 `struct S { void f() const; }; using T = decltype(&S::f);` 合法，但 `using U = std::remove_pointer_t<void (*)() const>;` 不合法？

<details markdown="1">
<summary>答案</summary>

`decltype(&S::f)` 是成员函数指针 `void (S::*)() const`，可憎函数类型 `void() const` 作为"成员指针所指向的函数类型"出现，属于 ¶11.2 允许的位置。而 `void (*)() const` 试图形成指向可憎函数类型的**普通指针**，不在 ¶11 的列表中，非良构——问题出在写下这个类型本身，与 `remove_pointer_t` 无关。
</details>

!!! question "思考题 3"
    `struct B { virtual void f(); };` 之后，`struct D : B { void f(this B&); };` 与 `struct D2 : B { void f(this D2&); };` 分别怎样？

<details markdown="1">
<summary>答案</summary>

按 [[class.virtual#2]]，派生类中的成员函数 G 若与基类虚函数 F 的声明**对应**（[[basic.scope.scope]]），就覆盖 F，从而成为虚函数。对应要求两者有"对应的对象参数"（[[basic.scope.scope#3]]）：恰有一个是无引用限定的隐式对象成员函数时，比较去掉引用后的对象参数类型。

- `D::f(this B&)`：`B::f` 的隐式对象参数类型是 `B&`，`D::f` 的显式对象参数类型也是 `B&`，去掉引用后相同 ⇒ 对应 ⇒ 覆盖 ⇒ 成为虚函数；但显式对象成员函数不能是虚函数（¶7），**非良构**。
- `D2::f(this D2&)`：对象参数去掉引用后是 `D2` 与 `B`，不同 ⇒ 按字面规则**不对应**，于是不覆盖，只是隐藏 `B::f` 的一个普通成员函数，看起来应当良构。截至写作时 Clang 23 对两种写法都报 "an explicit object parameter cannot appear in a virtual function"，后者与上述字面推理不一致——这是值得留意的边界情形。

教训：显式对象参数与虚函数是互斥的设计，需要虚分派时仍用隐式对象成员函数。
</details>

## 小结

!!! summary
    | 主题 | 要点 |
    |---|---|
    | 函数类型 | 返回类型 + 形参类型列表（含省略号）+ cv + ref + noexcept |
    | 不属于类型 | 默认实参、尾置 requires、契约、形参名 |
    | 形参调整 | 数组 → 指针、函数 → 指针（只调整最外层）；删除顶层 cv；不影响形参本身的类型 |
    | `(void)` | 仅当单个无名形参且类型非依赖地等于 `void` |
    | 省略号 | `, ...` 推荐；`int...` C++26 弃用；`T...`（T 是包）/`auto...` 是形参包 |
    | 显式对象参数 | C++23；第一个形参；不能有 cv/ref 限定、static、virtual；不能是包；体内无 `this` |
    | 可憎函数类型 | `R(A) const &` 只能用于成员函数、成员指针、typedef、模板实参、反射 |
    | 返回类型 | 不能是数组或函数；不能在返回/形参类型中定义类型 |
    | 简写函数模板 | `auto`/`C auto` 形参引入虚构模板形参；不能 `decltype(auto)`；不能在块作用域 |
