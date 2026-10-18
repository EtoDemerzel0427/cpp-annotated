---
title: 名字（id 表达式）
summary: 用名字指代实体的表达式：类型与值类别如何确定、何时被隐式改写成 (*this).m、lambda 中被按值捕获的名字为何带 const、隐式移动（move-eligible）、限定名、伪析构函数与 C++26 包索引。
status: draft
covers: expr.prim.id.general, expr.prim.id.unqual, expr.prim.id.qual, expr.prim.pack.index, expr.prim.id.dtor
related: expr.prim, basic.lookup, basic.lval, expr.ref, expr.prim.lambda.capture, temp.variadic, class.dtor, stmt.return
tags: 表达式, 值类别, 名字查找, 隐式移动, 包展开
updated: 2026-10-17
---

**id 表达式**（*id-expression*）是"用一个名字当表达式"：`x`、`N::x`、`operator+`、`~T`、`f<int>`、以及 C++26 的 `ts...[0]`。名字查找（[[basic.lookup]]）回答"这个名字指的是哪个实体"；本节回答的是下一步：**这个表达式的类型、值类别是什么，它在什么场合可以用**。

这一节看似琐碎，却藏着大量日常编程中的"为什么"：

- 为什么成员函数里写 `m` 就能访问成员？——**隐式成员访问变换**（¶2）。
- 为什么 `sizeof(S::m)` 合法、`int i = S::m;` 却不合法？——¶4 的使用场合限制。
- 为什么 `[=]{ ... }` 里 `decltype((x))` 是 `const T&`？——[[expr.prim.id.unqual#4]]。
- 为什么 `return x;` 会移动、而 `return (x);` 也会、`return x.member;` 却不会？——**move-eligible**（[[expr.prim.id.unqual#15]]）。
- 为什么非类型模板形参 `N` 不能取地址，而类类型模板形参却可以？——¶9 与 ¶12。

## 总体规则（[expr.prim.id.general]）

### id 表达式的三种形式（¶1）

¶1 *id-expression* 是 *unqualified-id*、*qualified-id* 或 *pack-index-expression*。它是 *primary-expression* 的一种受限形式。注释提醒：*id-expression* 也会出现在 `.`/`->` 之后，那时它是成员访问的组成部分，而不是独立的基本表达式（[[expr.ref]]）。

### 隐式成员访问变换（¶2）

¶2 这是本节最重要的规则。若 id 表达式 `E` 指代某个类 `C` 的**非静态、非类型成员**（数据成员或成员函数），且在 `E` 所处位置**当前类**（[[expr.prim.this#2]]）是 `X`，同时满足：

- (2.1) `E` 是**潜在求值**的（[[basic.def.odr#3]]），**或者** `C` 就是 `X` 或 `X` 的基类；
- (2.2) `E` 本身不是类成员访问 `a.E` / `p->E` 的那个 id 表达式；
- (2.3) `E` 不是反射表达式 `^^E` 的操作数 {{c++26}}；
- (2.4) 若 `E` 是限定名，它不是一元 `&` 的**不加括号**的操作数（否则就是在形成成员指针）；

那么 `E` 被改写成以 `(*this)` 为对象表达式的类成员访问：`m` → `(*this).m`。

!!! std
    the *id-expression* is transformed into a class member access expression using `(*this)` as the object expression.

    满足条件时，裸成员名被改写成 `(*this).名字`，此后一切按 [[expr.ref]] 处理。

这条规则解释了很多现象：

1. **成员函数里能直接写 `m`**：这就是 `(*this).m`。之后类型、值类别、cv 都按成员访问规则：在 `const` 成员函数里 `*this` 是 const，所以 `m` 是 const lvalue。
2. **(2.1) 的"或者"**：为什么要区分"潜在求值"和"C 是 X 或其基类"？考虑 `sizeof(Other::om)` 出现在与 `Other` 无关的类 `X` 的成员函数里：它既不潜在求值、`Other` 也不是 `X` 的基类，于是**不变换**，作为 ¶4.3 的"未求值操作数中命名非静态数据成员"合法。而 `sizeof(m)`（`m` 是 `X` 自己的成员）会被变换成 `sizeof((*this).m)`，结果一样，但其类型现在受 `*this` 的 cv 影响。
3. **(2.4) 只针对限定名**：`&X::m` 是成员指针（[[expr.unary.op]]），所以不能变换；`&(X::m)` 有括号，则照常变换为 `&(*this).m`，得到普通指针。这正是 [[expr.prim.paren]] 中"括号改变含义"的一例。
4. **变换不在模板定义上下文中进行**（[[temp.dep.type]]）：在模板定义中是否要变换可能取决于依赖基类等，推迟到实例化时决定。

!!! note "注释 2：两种必然失败的情形"
    - 若 `C` 不是 `X` 或 `X` 的基类，变换出的 `(*this).C::m` 非良构——你不能在 `Der` 的成员里潜在求值地使用不相关类 `Other` 的成员。
    - 若 id 表达式出现在**静态成员函数**或**显式对象成员函数**（deducing this）内部，变换出的成员访问非良构——那里没有 `this`（[[expr.prim.this#4]]）。在显式对象成员函数中必须写 `self.m`。

```cpp run ok
struct Base  { int bm; };
struct Other { int om; };

struct Der : Base {
  int dm;
  void h() const {
    (void)dm;                    // (*this).dm，类型 const int lvalue
    (void)bm;                    // (*this).bm，Base 是 Der 的基类
    (void)Base::bm;              // 限定名同样变换：(*this).Base::bm
    (void)sizeof(Other::om);     // 不变换：未求值，且 Other 不是基类；由 ¶4.3 允许
  }
};

int main() { }
```

```cpp error
struct Other { int om; };
struct Der {
  void h() { (void)Other::om; }   // error: 潜在求值 → 变换为 (*this).Other::om，但 Other 不是 Der 的基类
  void e(this Der& self) { }
  int dm;
  void k(this Der& self) { (void)dm; }   // error: 显式对象成员函数中没有隐式 this
};
```

!!! std "C++26 契约中的附加限制"
    若变换发生在**构造函数的前置条件**或**析构函数的后置条件**的谓词中，表达式非良构 {{c++26}}。

    构造函数开始执行前成员尚未初始化，析构函数结束后成员已销毁，此时读成员必然出错；但未求值的 `sizeof(b)` 和显式写出的 `&this->b` 仍是允许的（后者不读值）。

!!! lawyer "静态成员函数中的 `sizeof(m)`"
    按当前措辞，在类 `X` 的静态成员函数中写 `sizeof(m)`（`m` 是 `X` 的非静态数据成员）：条件 (2.1) 的后半"C 是 X"成立，因此会被变换成 `sizeof((*this).m)`，而注释 2 说这在静态成员函数中非良构。C++11 的旧措辞则规定"只在可以使用 `this` 的上下文中才变换"，按旧措辞这是合法的。实践中 Clang 对**函数体**中的 `sizeof(m)` 接受，对**声明**中（如尾置返回类型 `-> decltype(sizeof(m))`）则拒绝。想写可移植代码，请用 `sizeof(std::declval<X&>().m)` 或直接写类型。

### 匿名联合体的成员（¶3）

¶3 若 `E` 指代某匿名联合体 `U`（[[class.union.anon]]）的变体成员 `M`：

- (3.1) 若 `U` 是一个**非静态数据成员**（类内的匿名联合体），`E` 被当作"`E` 终端名的查找上下文里的成员 `M`"——例如 `o.x` 被解释为 `o.u.x`（`u` 代表那个无名成员）。
- (3.2) 否则（命名空间作用域或块作用域的匿名联合体，引入了一个无名**变量**），`E` 被解释成对该匿名联合体变量的子对象 `M` 的成员访问，例如 `N::x` 被解释为 `N::u.x`。注释 3 强调：这样解释后 `E` **不再**指代非静态数据成员——所以命名空间作用域的匿名联合体成员可以像普通变量一样使用，不受 ¶4 限制。

```cpp run ok
namespace N { static union { int x; float f; }; }   // 命名空间作用域的匿名联合体必须是 static

struct O {
  union { int a; char c; };          // 类内匿名联合体：a、c 是 O 的变体成员
};

int main() {
  N::x = 1;            // 即 N::<匿名变量>.x
  O o;
  o.a = 2;             // 即 o.<匿名成员>.a
  return N::x + o.a - 3;
}
```

### 非静态成员名能用在哪里（¶4–5）

¶4 指代**非静态数据成员**或**隐式对象成员函数**的 id 表达式（或 splice 表达式），只能：

- (4.1) 作为类成员访问的一部分（含 ¶2 的隐式变换结果），且对象表达式的类型是该成员所属类或其派生类；
- (4.2) 用来形成成员指针（`&C::m`）；
- (4.3) 若指代的是**非静态数据成员**，出现在**未求值操作数**（[[expr.context]]，如 `sizeof`、`decltype`、`noexcept`、`requires` 中）里。

(4.3) 是 C++11 新增的：在此之前 `sizeof(S::m)` 是非良构的，人们只能写 `sizeof(((S*)0)->m)` 这种丑陋写法。注意 (4.3) 只对**数据成员**开放——成员函数名在未求值操作数中依然不能单独出现，因为"没有对象的成员函数"甚至没有一个可以描述的类型。

```cpp run ok
#include <type_traits>

struct S { int m; void mf(); };

int i = sizeof(S::m);                 // OK：(4.3)
int j = sizeof(S::m + 42);            // OK：整个操作数是未求值的
int S::* pm = &S::m;                  // OK：(4.2)
void (S::* pmf)() = &S::mf;           // OK：(4.2)
static_assert(std::is_same_v<decltype(S::m), int>);

int main() { }
```

```cpp error
struct S { int m; void mf(); };
int a = S::m;                  // error: 潜在求值地使用非静态数据成员，且无对象
auto b = S::mf;                // error: 非静态成员函数只能被调用或用于形成成员指针
auto c = sizeof(S::mf);        // error: (4.3) 只允许数据成员
```

¶5 {{c++26}} 指代**直接基类关系**的 splice 表达式只能作为类成员访问的第二操作数（`obj.[: base_rel :]`），用于取得基类子对象。见 [[expr.prim.splice#2]]。

### 重载集（¶6）

¶6 若 id 表达式指代一个**重载集**，就进行重载决议（[[over.match]]、取地址时用 [[over.over]]）选出唯一函数。注释 4 由此推出一个重要结论：带有**不被满足**的尾置 *requires-clause* 的函数**永远不会被选中**，所以根本无法被引用——不能调用、不能取地址、甚至不能出现在 `decltype` 里（虽然 `decltype` 的操作数不求值，但"引用到某个函数"这件事本身就需要先决定是哪个函数）。

```cpp error
template<typename T> struct A {
  static void f(int) requires false;
};

void g() {
  A<int>::f(0);                         // error: 约束不满足，无法调用
  void (*p1)(int) = A<int>::f;          // error: 无法取地址
  decltype(A<int>::f)* p2 = nullptr;    // error: 即使在未求值操作数中也需要约束满足
}
```

这条规则让"按条件禁用成员函数"比 C++20 之前的 SFINAE 技巧干净得多：`requires` 约束的成员在类模板实例化时**不会**导致硬错误，而只是让它在决议中不可见（参见 [[temp.constr]]）。

## 非限定名（[expr.prim.id.unqual]）

### 什么算 unqualified-id（¶1–3）

¶1 *unqualified-id* 包括：标识符、`operator@`（[[over.oper]]）、转换函数名 `operator T`（[[class.conv.fct]]）、字面量运算符名 `operator""_x`（[[over.literal]]）、`~类型名`/`~decltype(...)`（析构函数，见下文）、*template-id*。一个标识符只有在**被适当声明过**（或正在作为 *declarator-id* 被声明）时才是 id 表达式——换言之，未声明的名字不是表达式，而是错误（ADL 的情形例外由 [[basic.lookup.argdep]] 处理：`f(x)` 中 `f` 可以在普通查找中找不到）。

¶2 [[g:component-name|**组成名字**]]（component name）与[[g:terminal-name|**终端名字**]]（terminal name）是 C++23 起为统一名字查找措辞引入的术语：*unqualified-id* 的组成名字就是它本身（若是名字）或其中 *template-id*/*type-name* 的组成名字；一个构造的**终端名字**是它在词法上**最后出现**的组成名字。例如 `N::C<int>::f` 的终端名字是 `f`。这些术语在 [[basic.lookup.qual]] 中用来描述"哪个名字在哪个作用域里查"。

¶3 结果就是名字查找（[[basic.lookup.unqual]]）找到的实体。

### 类型：一串"否则"（¶4–10）

确定 unqualified-id 的类型时，标准依次检查以下情形，第一个匹配的生效：

| 段落 | 情形 | 表达式的类型 |
|---|---|---|
| ¶4 | lambda 中命名一个**会被按值捕获**的局部实体，且位于该 lambda 的函数形参作用域内 | 对应闭包成员通过对象参数访问的类型（通常带 const） |
| ¶5 | 协程形参 | 协程帧中那份**拷贝**的类型，且结果就是那份拷贝 |
| ¶6 {{c++26}} | 后置条件中的**结果绑定**（`post(r: ...)`）| `const T`（返回 `T&` 时）或 `const U` |
| ¶7 {{c++26}} | 契约谓词中命名谓词外声明的变量/引用/结构化绑定 | `const T` |
| ¶9 | 类类型的**模板形参对象** | `const T` |
| ¶10 | 其余 | 实体的类型 |

¶11 注释：所得类型再按 [[expr.type]] 调整——引用类型去掉引用，cv 限定的非类类型 prvalue 去掉 cv。

#### lambda 中的名字（¶4）

¶4 这条规则处理一个微妙的问题：**在 lambda 内部写 `decltype((x))`，`x` 还没被"变换"为闭包成员访问**（变换只针对 odr-use，见 [[expr.prim.lambda.capture#11]]；而 `decltype` 的操作数是未求值的），但程序员显然期望得到"lambda 里 `x` 的真实类型"。¶4 的四个条件：

- (4.1) unqualified-id 出现在 lambda 表达式中的程序点 P；
- (4.2) 实体是局部实体（[[basic.pre]]）或 init-capture 声明的变量；
- (4.3) 若在最内层 lambda 的复合语句中（非未求值操作数地）命名它，会引用到某个中间 lambda **按值**捕获的实体；
- (4.4) P 位于最内层这样的 lambda `E` 的**函数形参作用域内，但不在形参声明子句中**——也就是在尾置返回类型、noexcept 说明、函数体等位置。

满足时，表达式类型等于"通过 `E` 的函数调用运算符的对象参数访问那个**按值捕获产生的非静态数据成员**"的类型。非 `mutable` lambda 的调用运算符是 `const` 的，于是类型是 `const T`。

```cpp run ok
#include <type_traits>

void f() {
  float x, &r = x;

  [=]() -> decltype((x)) {     // 返回 const float&：P 在尾置返回类型中，满足 (4.4)
    decltype(x) y1;            // float   —— 不加括号的 decltype 看的是实体的声明类型，不受 ¶4 影响
    decltype((x)) y2 = y1;     // const float&
    decltype(r) r1 = y1;       // float&  —— 声明类型
    decltype((r)) r2 = y2;     // const float& —— 按值捕获引用时，捕获的是被引用的 float
    static_assert(std::is_same_v<decltype(y2), const float&>);
    static_assert(std::is_same_v<decltype(r2), const float&>);
    (void)r1; (void)r2;
    return y2;
  };

  [=](decltype((x)) y) {       // y 是 float&：形参声明子句不满足 (4.4)，看的是外面的 x
    static_assert(std::is_same_v<decltype(y), float&>);
  };

  [=]() mutable {              // mutable：调用运算符不是 const，成员不带 const
    static_assert(std::is_same_v<decltype((x)), float&>);
  };

  [=] {
    [](decltype((x)) y) { };   // 标准：y 的类型是 const float&（见下方说明；Clang 给出 float&）
  };
}

int main() { }
```

最后一个例子最考验对 (4.4) 的理解。P 位于**内层** lambda 的形参子句中，但 (4.4) 说的是"最内层的**这样的** lambda"——即按值捕获了 `x` 的那个 lambda，也就是外层的 `[=]`。P 位于外层 lambda 的函数形参作用域内（它的函数体里），且不在外层的形参子句中，所以条件成立，`decltype((x))` 是 `const float&`。标准原文的例子正是如此注释的。

!!! warning "编译器分歧"
    截至写作时，本机 Clang（Homebrew clang 23）对这个嵌套情形给出的是 `float&`，与标准例子不一致；前面几种情形则与标准一致。依赖此类细节的代码应当避免，或者显式写出类型。

!!! note "为什么形参子句被排除在外"
    (4.4) 中"但不在 *parameter-declaration-clause* 中"的理由：形参的类型决定了调用运算符的签名，而签名应当只依赖于外部可见的信息，不依赖于"这个名字是否会被捕获"——捕获集合甚至要等看完整个函数体才能确定（隐式捕获）。

#### 协程形参（¶5）

¶5 协程开始执行时，形参会被**拷贝**（或移动）到协程帧中（[[dcl.fct.def.coroutine]]），之后协程体里的形参名指代的是那份拷贝。这就是为什么协程按引用接受的参数在首次挂起之后可能悬垂：拷贝的只是引用本身。

#### 契约谓词中的 const 化 {{c++26}}（¶6–8）

¶6 后置条件的**结果绑定**（result binding，[[dcl.contract.res]]，`post(r : r > 0)` 中的 `r`）：若返回类型是 `T&`，`r` 的类型是 `const T`；否则是 `const U`。

¶7 契约断言 `C` 的谓词中命名**在 `C` 之外声明**的对象类型变量、引用类型变量或模板形参、结构化绑定，表达式类型是 `const T`。¶8 是一个长例子，要点：

- `pre(++i)`、`pre(++r)`、`pre(x.m())` 都非良构（`i`、`r`、`x` 被视为 const）；
- `pre(++(*p))`、`pre(px->m())` 良构——const 只加在**名字本身**上（`p` 是 `int* const`），不传递到它指向的对象；
- 谓词中 `[=] mutable { ++p; }` 良构——lambda 体内的 `p` 指的是闭包的（非 const，因为 mutable）成员，而 `[=,&i] mutable { ++i; }` 非良构——按引用捕获的 `i` 仍然指向那个被视为 const 的外部实体。

这组规则的动机是让契约检查**不改变**程序状态，同时保持"浅 const"的简单模型。C++23 及之前没有契约，自然也没有这些规则。

#### 模板形参对象（¶9）

¶9 类类型（或其他非标量结构化类型）的非类型模板形参，命名的是一个**模板形参对象**（template parameter object，[[temp.param]]）：一个静态存储期的 `const` 对象，整个程序中值相同的实参共享同一个对象。所以表达式类型是 `const T`，且（¶12）是 **lvalue**——你可以取它的地址。相比之下，标量类型的非类型模板形参 `N` 是 **prvalue**（¶12 的"否则"），`&N` 非良构。

```cpp run ok
#include <type_traits>

struct P { int x; };

template<P p> constexpr const P* addr() {
  static_assert(std::is_same_v<decltype((p)), const P&>);   // const lvalue
  return &p;                                               // OK：模板形参对象有地址
}
template<int N> void nn() {
  static_assert(std::is_same_v<decltype((N)), int>);      // prvalue
}

static_assert(addr<P{1}>() == addr<P{1}>());   // 值相同 → 同一个对象

int main() { nn<1>(); }
```

### 值类别（¶12）

¶12 unqualified-id 的值类别：

- 若 **move-eligible**（¶15）→ **xvalue**；
- 若实体是函数、变量、结构化绑定、结果绑定、数据成员、模板形参对象 → **lvalue**；
- 否则（枚举项、标量非类型模板形参……）→ **prvalue**。

若标识符指代位域，表达式就是位域。

注意"变量"包括**引用类型**的变量：`int&& rr = 1;` 之后 `rr` 是一个 lvalue（类型 `int`）。"有名字的右值引用是左值"正是这条规则——除非它 move-eligible。

### 隐式移动：move-eligible（¶15）

¶15 [[g:implicitly-movable-entity|**可隐式移动的实体**]]（implicitly movable entity）：自动存储期的变量，且是非 volatile 对象，或者是指向非 volatile 对象类型的**右值引用**。一个 id 表达式（或 splice 表达式）是 [[g:move-eligible|**move-eligible**]] 的，当且仅当：

- (15.1) 它指代可隐式移动的实体；
- (15.2) 它是 `return`、`co_return` 语句或 *throw-expression* 的（可加括号的）操作数；
- (15.3) 从实体声明处到表达式所在最内层作用域之间的每个中间作用域都是**块作用域**；对 `throw` 还要求这些块作用域不是 `try` 块的作用域。

move-eligible 的 id 表达式是 **xvalue**（¶12），于是重载决议会自然地优先选择移动构造函数——C++23 起不再需要 C++11–20 那种"先当右值做一次重载决议，失败再当左值做一次"的两阶段规则。

```cpp run ok
#include <memory>
using U = std::unique_ptr<int>;

U f1(U p)     { return p; }              // 形参也是自动存储期变量
U f2()        { U p; return (p); }       // 括号不影响
U f3(U&& p)   { return p; }              // 右值引用变量：C++23 起 move-eligible
U&& f4(U&& p) { return p; }              // C++23 起：p 是 xvalue，可绑定到 U&&
U f5()        { U p; { { return p; } } } // 中间都是块作用域
void t1()     { U p; throw p; }          // throw 也会移动

int main() { }
```

```cpp error
#include <memory>
using U = std::unique_ptr<int>;

void t2() { U p; try { throw p; } catch (...) {} }  // error: try 块作用域介于其间，拷贝 → 删除的拷贝构造
U f6()    { static U p; return p; }                  // error: 静态存储期，不可隐式移动
U f7()    { U p; return [&] { return p; }(); }       // error: lambda 作用域介于其间
struct H { U m; U get() { return m; } };             // error: 数据成员不是"变量"
```

!!! pitfall "C++23 隐式移动的破坏性变化"
    C++23 让右值引用变量的 `return` 成为 xvalue，导致下面原本合法的代码变成非良构：
    ```cpp
    std::string& bad(std::string&& s) { return s; }   // C++20 OK；C++23 起 error：xvalue 不能绑定到非 const 左值引用
    ```
    同样，`decltype(auto) f(T&& x) { return x; }` 在 C++23 起返回 `T&&` 而不是 `T&`。

### 契约中的形参与临时对象 {{c++26}}（¶13–14）

¶13 若函数的形参（或返回值，¶14）被实现以**临时对象**的方式传递（[[class.temporary]] 允许对平凡可拷贝的小对象这样做，以便放进寄存器），那么：

- 前置条件中，若前置条件的求值先于形参对象的初始化，名字指代**最近初始化的那个临时对象**；
- 后置条件中，名字指代临时对象还是形参对象是**未指定**的 {{unspec}}，但在同一次后置条件求值中保持一致。

¶14 后置条件中的结果绑定同理：若先于结果对象的初始化求值，指代最近初始化的临时对象。

这些规则承认了 ABI 现实：调用者传寄存器、被调用者再落到栈上，契约检查可能发生在"副本"上。只要不依赖对象地址的同一性，这对程序员是透明的。

## 限定名（[expr.prim.id.qual]）

### 文法与组成名字（¶1–2）

*qualified-id* 是 *nested-name-specifier* + 可选 `template` + *unqualified-id*。*nested-name-specifier* 可以是 `::`、类型名 `::`、命名空间名 `::`、`decltype(...)::`（*computed-type-specifier*，含 C++26 的包索引说明符）、以及 {{c++26}} 的 `[: r :]::`（*splice-scope-specifier*）。

¶1 定义组成名字：*qualified-id* 的组成名字是其 *nested-name-specifier* 和 *unqualified-id* 的组成名字之和。

¶2 {{c++26}} splice 说明符后**不跟** `::` 时，永远不会被当作 *splice-scope-specifier*。`template` 只有在前面有 `typename` 时才能从 `template [: r :]<args>::` 中省略。这是在给 splice 语法消歧：`[:^^TCls:]<3>::type` 中 `<` 被当作小于号，所以非良构，必须写 `template [:^^TCls:]<3>::type`。

### 声明性的嵌套名说明符（¶3）

¶3 若 *nested-name-specifier* 出现在类头名、枚举头名、声明符 id（如类外定义 `void N::f() {}`）、显式实例化的详细类型说明符中，它是[[g:declarative-nested-name-specifier|**声明性的**]]（declarative）。限制：

- 声明性的 *nested-name-specifier* 不能含 `decltype(...)` 或 splice；
- 使用它的声明要么是友元声明，要么必须位于**包含被重声明实体的作用域**中。

第二条的意思是：你只能在"从外面包住"目标的作用域里做类外定义，不能从不相关的命名空间里定义别人的函数：

```cpp error
namespace N { namespace M { void g(); } void h(); }

void N::h() {}                        // OK：全局作用域包含 N::h
namespace X { void N::M::g() {} }     // error: X 不包含 N::M::g
```

### nested-name-specifier 指代什么（¶4）

¶4 依次：`::` 指全局命名空间；`decltype(E)::` 指那个类型，必须是类或枚举；{{c++26}} `[: r :]::` 指 `r` 所反射的类/枚举/命名空间；`template [: r :]<A>::` 指相应特化（必须是类或指代类/枚举的别名）。

(4.5) 处理**类模板成员的类外定义**：`template<class T> void TT<T>::f() {}` 中，`TT<T>` 是声明性的且实参列表涉及模板形参。若实参列表恰好就是对应 *template-head* 的形参列表（`<T>` 对应 `template<class T>`），就指代**主模板**，且两个 template-head 必须等价；否则指代对应的**部分特化**，找不到就非良构。

(4.6) 其余情形就是名字所指的实体；非声明性的 nested-name-specifier 不能指代模板本身（必须带模板实参，例如不能写 `std::vector::size_type`）。

### 析构函数名的形式限制（¶5）

¶5 不允许 `N::~decltype(x)` 与 `decltype(x)::~T` 这两种形式。`~decltype(x)` 只能以非限定形式出现，如 `p->~decltype(*p)()`。

### 类型与值类别（¶6–9）

¶6 结果是限定名查找（[[basic.lookup.qual]]）找到的实体。¶7 契约中的 const 化同 [[expr.prim.id.unqual#7]]。¶8 否则类型就是结果的类型。

¶9 值类别：结果为 **lvalue** 当且仅当实体是

- 非成员函数或静态成员函数（9.1）；
- 非静态成员函数，**且**该限定名是一元 `&` 的操作数（9.2）；
- 变量、结构化绑定、数据成员（9.3–9.5）；

否则是 **prvalue**。(9.2) 很特别：`X::mf` 在 `&X::mf` 中是 lvalue（这样 `&` 才能作用于它），在其他场合（例如成员函数内 `X::mf()` 被变换为 `(*this).X::mf()` 之前的那个名字）则是 prvalue——C++ 中没有"非静态成员函数类型的 lvalue"可以单独存在。

## 包索引表达式 {{c++26}}（[expr.prim.pack.index]）

```
pack-index-expression:
    id-expression ... [ constant-expression ]
```

¶1 `P` 必须是指代**包**的标识符（函数形参包、非类型模板形参包、init-capture 包、结构化绑定包）。

¶2 下标必须是 `std::size_t` 类型的**转换常量表达式**（[[expr.const.const]]）——这意味着禁止窄化：`ts...[-1]` 非良构，而不是"环绕成很大的数再越界"。下标值 `V` 必须满足 `0 ≤ V < sizeof...(P)`。

¶3 包索引表达式**本身是一个包展开**（[[temp.variadic]]）。这听起来奇怪——它的结果只是一个元素，并不产生列表。原因是技术性的：把它归为包展开，`ts` 出现在其中就算"已展开"，因而不会被外层的 `...` 再次展开；实例化规则见 [[temp.variadic#11]]：实例化为第 K 个元素的 id 表达式 `E_K`。

¶4 注释：它指代包的第 V 个元素。由于实例化结果就是那个元素的 *id-expression*，所以其类型、值类别与直接写那个元素的名字完全一样：形参包元素是 lvalue，`decltype(ts...[0])` 给出声明类型，`decltype((ts...[0]))` 给出引用。

```cpp run ok
#include <cstddef>
#include <type_traits>
#include <utility>

template<class... Ts> constexpr auto first(Ts... ts) { return ts...[0]; }

template<std::size_t I, class... Ts>
constexpr decltype(auto) nth(Ts&&... ts) {
  return std::forward<Ts...[I]>(ts...[I]);   // 类型包索引 Ts...[I]（[[dcl.type.pack.index]]）+ 表达式包索引
}

template<class... Ts> void g(Ts... ts) {
  static_assert(std::is_same_v<decltype(ts...[0]), int>);     // 声明类型
  static_assert(std::is_same_v<decltype((ts...[0])), int&>);  // lvalue
}

static_assert(first(1, 2.0, 'c') == 1);
static_assert(std::is_same_v<decltype(first(1.0, 2)), double>);

int main() {
  g(1, 'x');
  int x = 3;
  static_assert(std::is_same_v<decltype(nth<0>(x, 2)), int&>);
  static_assert(std::is_same_v<decltype(nth<1>(x, 2)), int&&>);
}
```

```cpp error
template<class... Ts> auto bad(Ts... ts)  { return ts...[3]; }
int x = bad(1, 2);                                              // error: 下标 3 越界（包大小为 2）

template<class... Ts> auto bad2(Ts... ts) { return ts...[-1]; } // error: -1 到 size_t 是窄化
```

!!! history "C++26 之前"
    在 C++26 之前取包的第 N 个元素只能用递归模板、`std::get<N>(std::forward_as_tuple(ts...))` 或基于重载的技巧，编译开销大、可读性差。包索引在 C++26 中通过提案 [[P2662R3]] 引入。由于形参声明中的 `T...[N]` 在 C++23 中可以被解析为"无名的数组形参包"，该提案改变了这种写法的含义，是少见的语法层面的破坏性变化。

## 析构函数与伪析构函数（[expr.prim.id.dtor]）

¶1 指代类型 `T` 的析构函数的 id 表达式（`~T`、`~decltype(...)`），若 `T` 是类类型，就**命名析构函数**（[[class.dtor]]）；否则称为命名一个[[g:pseudo-destructor|**伪析构函数**]]（pseudo-destructor）。

¶2 命名伪析构函数时，`T` 必须是**标量类型**，并且该 id 表达式必须作为类成员访问的右操作数，而该成员访问又构成函数调用的后缀表达式——即只能写成 `obj.~T()` 或 `p->~T()` 的完整调用形式。注释：这样的调用**结束对象的生命周期**（[[basic.life]]）。

为什么需要伪析构函数？为了**泛型代码**：`template<class T> void destroy(T* p) { p->~T(); }` 在 `T = int` 时也要能工作。

```cpp run ok
struct C { };

template<class T> void destroy(T* p) { p->~T(); }   // T 为 int 时调用伪析构函数

int main() {
  C* pc = new C;
  using C2 = C;
  pc->C::~C2();           // OK：析构 *pc（限定名查 C，~C2 是别名）
  ::operator delete(pc);

  using T = int;
  0 .T::~T();             // OK：对 prvalue 0 物化出的临时对象调用伪析构
  int i = 0;
  i.~T();                 // OK：结束 i 的生命周期（C++20 起）
  int j = 0;
  j.~decltype(j)();       // OK：~decltype(...) 形式
  int k = 0;
  destroy(&k);
}
```

```cpp error
void f() {
  int i = 0;
  i.~int();          // error: ~ 之后必须是 type-name 或 decltype，int 是关键字不是 type-name
  using T = int;
  0.T::~T();         // error: 0.T 被词法分析为一个用户定义浮点字面量
}
```

标准例子中还有一行很有意思：

```cpp ub
struct C { };
void f() {
  C().C::~C();       // UB: 临时对象被显式析构一次，在完整表达式结束时又被析构一次
}
```

!!! history "伪析构函数从\"无操作\"到\"结束生命周期\""
    C++98–17 中，伪析构函数调用的唯一效果是对后缀表达式求值，**什么也不做**。C++20 起（随提案 [[P0593R6]] "隐式创建对象"一同修改），它**结束对象的生命周期**。这让 `std::destroy_at` 对标量和类类型行为一致：调用之后再读 `i` 就是读取生命周期已结束的对象。对常量求值器而言，这一区别是可观察的：在 `constexpr` 函数中对 `int` 调用伪析构函数后再读取它，不是常量表达式。

!!! lawyer "`~T()` 不是析构函数调用"
    单独写 `~T();`（`T` 为 `int`）是**一元按位取反**作用于值初始化的 `T()`，结果为 `-1`，与析构无关。[[expr.unary.op]] 中专门规定 `~X()` 形式按一元运算符解析。只有出现在 `.`/`->` 之后，`~T` 才是析构函数名。

## 实现视角

!!! impl
    - **隐式成员访问**在 Clang AST 中表现为一个 `MemberExpr`，其基对象是 `CXXThisExpr` 并带有 `implicit` 标记；`-Xclang -ast-dump` 可以清楚看到 ¶2 的变换结果。
    - **lambda 中的 `decltype((x))`**：本页的例子在 Clang 上均按 ¶4 的规则通过；这类规则跨编译器时最好用 `static_assert(std::is_same_v<...>)` 当场验证，而不是凭记忆。
    - **包索引**：Clang 19 起开始支持表达式与类型的包索引（参见 Clang 的 C++26 状态页）；它们在实例化时直接替换为对应元素，不会产生任何运行期代码。
    - **伪析构函数**在优化后通常不产生任何指令，但 UBSan/常量求值器会利用"生命周期已结束"的信息诊断后续读取。

## 历史与演进

!!! history
    - **C++98**：成员名的隐式 `this->` 变换已存在于 [class.mfct.non.static]；`sizeof(S::m)` 非良构。
    - **C++11**：允许在未求值操作数中命名非静态数据成员（¶4.3）；引入 lambda，于是有了"lambda 内名字的类型"问题。
    - **C++14**：init-capture 引入，lambda 中名字的类型规则随之需要覆盖 init-capture 声明的变量（现行 ¶4.2）。
    - **C++20**：类类型非类型模板形参 → 模板形参对象（¶9）；伪析构函数结束生命周期；隐式移动扩展到右值引用形参（仍是两阶段决议）。
    - **C++23**：lambda 尾置返回类型等位置中被按值捕获名字的类型规则（¶4 的现行形式，提案 [[P2036R3]]）；隐式移动重写为"move-eligible → xvalue"（提案 [[P2266R3]]）；组成名字/终端名字等术语随名字查找重写引入；显式对象成员函数不做 `this->` 变换。
    - **C++26**：包索引（[[P2662R3]]）；契约中名字的 const 化（¶6–8、¶13–14）；反射与 splice 相关规则（(2.3)、¶5、¶2 of qual）。

## 陷阱

!!! pitfall "按值捕获的变量在非 mutable lambda 中是 const"
    `[v]{ v.push_back(1); }` 非良构：`v` 被变换为闭包成员访问，而调用运算符是 const 的。要么加 `mutable`，要么按引用捕获。`decltype((v))` 也会如实地给出 `const std::vector<int>&`。

!!! pitfall "move-eligible 只看\"名字本身\""
    `return s.member;`、`return *p;`、`return std::get<0>(t);`、`return cond ? a : b;` 都**不是** move-eligible 的 id 表达式，会拷贝。结构化绑定 `return b;`（`auto [b] = ...`）也不会隐式移动——结构化绑定不是变量。

!!! pitfall "非类型模板形参不能取地址"
    `template<int N> void f() { const int* p = &N; }` 非良构：`N` 是 prvalue。若真需要地址，用 `static constexpr int n = N;` 或改用类类型形参（模板形参对象是 lvalue）。

## 思考题

!!! question "思考题 1"
    下面各 `decltype` 的结果是什么？
    ```cpp
    void f() {
      int x = 0;
      auto a = [x]() mutable { decltype((x)) r = x; };      // #1
      auto b = [&x] { decltype((x)) r = x; };                 // #2
      auto c = [y = x] { decltype((y)) r = y; };              // #3
    }
    ```

<details markdown="1">
<summary>答案</summary>

- `#1`：`int&`。lambda 是 `mutable`，调用运算符不是 const，闭包成员不加 const。
- `#2`：`int&`。¶4 只处理**按值**捕获（(4.3)），按引用捕获时就是外部 `x` 本身，`decltype((x))` 按普通规则得 `int&`。
- `#3`：`const int&`。init-capture `y` 按值捕获，非 mutable，类型为 `const int` 的 lvalue（(4.2) 明确包括 init-capture 声明的变量）。
</details>

!!! question "思考题 2"
    为什么下面的函数在 C++23 中返回 `std::string&&`，而 C++20 中返回 `std::string&`？
    ```cpp
    decltype(auto) pass(std::string&& s) { return s; }
    ```

<details markdown="1">
<summary>答案</summary>

`decltype(auto)` 对 `return s;` 按 `decltype(s)` 规则推导……但这里 `s` 不加括号，`decltype(s)` 看声明类型，本应是 `std::string&&`！实际上 C++20 中 `decltype(auto)` 推导出 `std::string&&`，然后 `return s;` 要用**左值** `s` 去初始化 `std::string&&`——非良构。C++23 起 `s` 是 move-eligible 的 xvalue，可以绑定，函数良构，返回 `std::string&&`。所以题干的说法有误：差别不在返回类型，而在 C++20 中这个函数**根本编译不过**。（这类"故意出错的题干"在 language lawyer 讨论中很常见，验证永远比记忆可靠。）
</details>

!!! question "思考题 3"
    在类 `X` 的成员函数中，`&X::m` 和 `&(X::m)` 的类型分别是什么？如果 `m` 是 `X` 的基类 `B` 的成员，`&X::m` 的类型又是什么？

<details markdown="1">
<summary>答案</summary>

`&X::m` 不变换（(2.4)），形成成员指针 `int X::*`；`&(X::m)` 带括号，(2.4) 不适用，变换为 `&(*this).X::m`，得到 `int*`。若 `m` 声明在基类 `B` 中，`&X::m` 的类型是 `int B::*`——[[expr.unary.op]] 规定成员指针的类是**声明该成员的类**，而不是限定名中写的类（它可以隐式转换为 `int X::*`）。
</details>

## 小结

!!! summary
    | 主题 | 要点 |
    |---|---|
    | 隐式成员访问 | 当前类的非静态成员名 → `(*this).m`；未求值且无关的类成员不变换；`&X::m` 不变换、`&(X::m)` 变换 |
    | 使用限制 | 非静态成员只能：成员访问、形成成员指针、（数据成员）在未求值操作数中 |
    | 类型 | lambda 按值捕获 → 闭包成员的类型（常带 const）；协程形参 → 帧中拷贝；契约谓词 → const {{c++26}}；模板形参对象 → `const T` |
    | 值类别 | move-eligible → xvalue；函数/变量/结构化绑定/数据成员/模板形参对象 → lvalue；其余（枚举项、标量 NTTP）→ prvalue |
    | 隐式移动 | 自动变量或右值引用，作为 `return`/`co_return`/`throw` 的（可带括号）操作数，中间只有块作用域 |
    | 限定名 | 声明性 nested-name-specifier 不能用 `decltype`/splice，且只能在包含目标的作用域中使用 |
    | 包索引 {{c++26}} | `ts...[I]`：I 为 `size_t` 转换常量表达式，必须在范围内；本身算包展开 |
    | 伪析构 | 标量类型的 `p->~T()`；C++20 起结束生命周期 |
