---
title: 名字（id 表达式）
summary: 把名字当作表达式使用时，它的类型和值类别怎样确定、什么时候被改写成 (*this).m、什么时候会被隐式移动，以及限定名、包索引和伪析构函数的规则。
status: done
covers: expr.prim.id.general, expr.prim.id.unqual, expr.prim.id.qual, expr.prim.pack.index, expr.prim.id.dtor
related: expr.prim, basic.lookup, basic.lval, expr.ref, expr.prim.lambda.capture, temp.variadic, class.dtor, stmt.return
papers: P1825R0, P2266R3, P2036R3, P2662R3
tags: 表达式, 值类别, 名字查找, 隐式移动, 包展开
updated: 2026-10-19
---

!!! tldr
    - 成员函数里写成员名 `m`，会被改写成 `(*this).m`，之后按成员访问的规则确定类型，所以 `const` 成员函数里的 `m` 是 const。
    - 非静态成员名脱离对象只能做三件事：参与成员访问、形成成员指针、（数据成员）出现在 `sizeof` 等未求值操作数中。
    - 有名字的变量是 lvalue，右值引用变量也不例外；只有作为 `return`、`co_return`、`throw` 的操作数且满足条件时，它才是 xvalue，从而被隐式移动。
    - 非 `mutable` 的 lambda 中，按值捕获的名字带 const；类类型的非类型模板形参是 const lvalue，标量的则是 prvalue，不能取地址。
    - C++26 的 `ts...[I]` 取包的第 I 个元素，下标越界或为负都非良构。

**id 表达式**（id-expression）就是把一个名字当作表达式使用：`x`、`N::x`、`operator+`、`~T`、`f<int>`，以及 C++26 的 `ts...[0]`。名字查找（[[basic.lookup]]）确定这个名字指哪个实体；本节确定接下来的事：这个表达式是什么类型、哪种值类别（[[basic.lval]]）、可以用在哪里。

## 成员名与隐式的 this [expr.prim.id.general]

```cpp run ok
struct Base  { int bm; };
struct Other { int om; };

struct Der : Base {
  int dm;
  void h() const {
    (void)dm;                 // (*this).dm，const int lvalue
    (void)bm;                 // (*this).bm，Base 是基类
    (void)Base::bm;           // (*this).Base::bm
    (void)sizeof(Other::om);  // 不改写：见下文 ¶4.3
  }
};

int main() { }
```

成员函数里能直接写 `dm`，是因为编译器把它改写成了 `(*this).dm`。

¶2 设 id 表达式 `E` 指代某个类 `C` 的非静态成员（数据成员或成员函数），在 `E` 所在位置，当前类（[[g:current-class]]，包含该位置的最内层类）是 `X`。如果同时满足以下四条，`E` 就改写成以 `(*this)` 为对象的类成员访问：

- (2.1) `E` 是潜在求值的（[[g:potentially-evaluated]]，大致说就是不在 `sizeof`、`decltype` 这类不求值的操作数里），或者 `C` 就是 `X` 或 `X` 的基类；
- (2.2) `E` 不是某个成员访问 `a.E`、`p->E` 中的名字；
- (2.3) `E` 不是反射表达式 `^^E` 的操作数 {{c++26}}；
- (2.4) 如果 `E` 是限定名，它不是一元 `&` 的不加括号的操作数。

改写之后一切按成员访问（[[expr.ref]]）处理。在 `const` 成员函数里 `*this` 是 const，所以 `m` 是 const lvalue。

(2.1) 区分两种情况。上例的 `sizeof(Other::om)` 不求值，`Other` 也不是 `Der` 的基类，于是不改写，按后面的 ¶4.3 合法。如果改成潜在求值的 `(void)Other::om;`，就会改写成 `(*this).Other::om`，而 `Other` 不是 `Der` 的基类，非良构（注 2）。

(2.4) 只针对限定名。`&X::m` 是在形成成员指针（[[expr.unary.op]]），不能改写；`&(X::m)` 有括号，照常改写为 `&(*this).X::m`，得到普通指针。这是括号改变含义的一个例子（[[expr.prim.paren]]）。

在模板定义中不做改写（[[temp.dep.type]]），因为是否需要改写可能取决于依赖的基类，要等实例化时才知道。

注 2 还指出，在静态成员函数或显式对象成员函数（deducing this）里，改写出的成员访问非良构，因为那里没有 `this`（[[expr.prim.this#4]]）。显式对象成员函数中必须写 `self.m`。

```cpp error
struct Other { int om; };
struct Der {
  int dm;
  void h() { (void)Other::om; }          // error: Other 不是基类
  void k(this Der& self) { (void)dm; }   // error: 没有隐式 this
};
```

¶2 的最后一句是 C++26 的附加规则：如果改写发生在 `X` 的构造函数的前置条件，或析构函数的后置条件中，表达式非良构 {{c++26}}。前置条件检查时成员还没有初始化，后置条件检查时成员已经销毁。不求值的 `sizeof(b)` 和不读值的 `&this->b` 仍然可以用。

!!! lawyer "静态成员函数中的 `sizeof(m)`"
    在类 `X` 的静态成员函数中写 `sizeof(m)`，`m` 是 `X` 的非静态数据成员。按当前措辞，(2.1) 的后半句 `C` 就是 `X` 成立，`m` 会被改写成 `(*this).m`，在静态成员函数中非良构。C++11 的措辞是只在可以使用 `this` 的地方才改写，按那时的规则它是合法的。Clang 23 接受函数体中的 `sizeof(m)`，却拒绝声明中的，例如尾置返回类型 `-> decltype(sizeof(m))`。可移植的写法是 `sizeof(std::declval<X&>().m)`，或者直接写类型。

### 非静态成员名能用在哪里

¶4 指代非静态数据成员或隐式对象成员函数的 id 表达式（或 splice 表达式）只能这样用：

- (4.1) 作为类成员访问的一部分（包括 ¶2 改写的结果），对象表达式的类型是该成员所属的类或其派生类；
- (4.2) 形成成员指针（`&C::m`）；
- (4.3) 如果指代的是数据成员，出现在未求值操作数（[[g:unevaluated-operand]]，`sizeof`、`decltype`、`noexcept` 等的操作数）中。

<div class="compare" markdown="1">

```cpp ok
struct S { int m; void mf() {} };

int i = sizeof(S::m);       // (4.3)
int j = sizeof(S::m + 42);  // (4.3)
int S::* pm = &S::m;        // (4.2)
void (S::* pmf)() = &S::mf; // (4.2)
```

```cpp error
struct S { int m; void mf() {} };

int a = S::m;           // error: 没有对象
auto b = S::mf;         // error
auto c = sizeof(S::mf); // error: 成员函数
```

</div>

(4.3) 是 C++11 加入的，此前只能写 `sizeof(((S*)0)->m)`。它只对数据成员开放：脱离对象的成员函数名连一个可以描述的类型都没有。

¶5 {{c++26}} 指代直接基类关系的 splice 表达式只能作为成员访问的第二个操作数（`obj.[: base :]`），用来取得基类子对象，见 [[expr.prim.splice]]。

### 重载集与不满足的约束

¶6 如果名字指代一个重载集，就做重载决议（[[over.match]]；取地址时按 [[over.over]]）选出唯一的函数。注 4 由此推出：尾置 *requires-clause* 不满足的函数永远不会被选中，所以根本无法引用它，即使在 `decltype` 这样的未求值操作数里也不行。

```cpp error
template<typename T> struct A {
  static void f(int) requires false;
};

void g() {
  A<int>::f(0);                        // error: 无法调用
  void (*p1)(int) = A<int>::f;         // error: 无法取地址
  decltype(A<int>::f)* p2 = nullptr;   // error: 同样需要约束满足
}
```

这让带约束的成员函数可以安全地留在类模板里：约束不满足时，实例化类模板不会出错，只是这个函数在重载决议中不可见（[[temp.constr]]）。

### 匿名联合体的成员

¶3 匿名联合体（[[class.union.anon]]）的成员名会被解释成对那个无名对象的成员访问。类内的匿名联合体是一个无名的非静态数据成员，`o.x` 解释为 `o.u.x`（`u` 代表那个无名成员）。命名空间或块作用域的匿名联合体是一个无名变量，`N::x` 解释为 `N::u.x`。注 3 指出，后一种情况下 `x` 不再算非静态数据成员，所以可以像普通变量一样使用，不受 ¶4 限制。

```cpp run ok
namespace N { static union { int x; float f; }; }  // 命名空间作用域的必须是 static

struct O {
  union { int a; char c; };   // a、c 是 O 的变体成员
};

int main() {
  N::x = 1;    // N::<无名变量>.x
  O o;
  o.a = 2;     // o.<无名成员>.a
  return N::x + o.a - 3;
}
```

## 非限定名的类型 [expr.prim.id.unqual]

¶1 *unqualified-id* 包括标识符、`operator+` 这样的运算符函数名、转换函数名 `operator T`、字面量运算符名 `operator""_x`、析构函数名 `~T`，以及 *template-id*。标识符只有在被声明过（或正在作为声明符被声明）时才是 id 表达式；ADL 是例外，`f(x)` 中的 `f` 可以在普通查找中找不到（[[basic.lookup.argdep]]）。

¶3 结果就是名字查找（[[basic.lookup.unqual]]）找到的实体。它的类型按下表依次检查，第一个适用的生效：

| 段落 | 情形 | 表达式的类型 |
|---|---|---|
| ¶4 | lambda 中命名一个被按值捕获的局部实体 | 对应闭包成员的类型，非 `mutable` 时带 const |
| ¶5 | 协程的形参 | 协程帧中那份副本的类型，结果也是那份副本 |
| ¶6 {{c++26}} | 后置条件的结果绑定 `post(r: ...)` | `const T` |
| ¶7 {{c++26}} | 契约谓词中命名谓词外声明的变量 | `const T` |
| ¶9 | 类类型的模板形参对象 | `const T` |
| ¶10 | 其余 | 实体的类型 |

¶11 的注释提醒，得到的类型还要按 [[expr.type]] 调整：引用类型去掉引用，非类类型的 prvalue 去掉 cv。

### lambda 中按值捕获的名字

```cpp
void f() {
  int x = 0;
  auto a = [x] { decltype((x)) r = x; };          // const int&
  auto b = [x] mutable { decltype((x)) r = x; };  // int&
  auto c = [&x] { decltype((x)) r = x; };         // int&
}
```

lambda 体里用到按值捕获的 `x` 时，实际访问的是闭包对象的一个数据成员（[[expr.prim.lambda.capture#11]]）。非 `mutable` lambda 的调用运算符是 const 成员函数，这个成员访问是 const 的，所以 `x` 不能修改。

但那条改写只针对 odr-use，即真正需要读写那个对象的使用。`decltype((x))` 的操作数不求值，不会触发改写。¶4 补上了这个缺口，让 `decltype((x))` 也给出 `x` 在 lambda 里的实际类型。它的四个条件是：

- (4.1) 名字出现在 lambda 表达式中的某一点 P；
- (4.2) 实体是局部实体（[[basic.pre]]）或 init-capture 声明的变量；
- (4.3) 如果在 P 所在的最内层 lambda 的函数体中命名这个实体，会引用到某个中间层 lambda 按值捕获的实体；
- (4.4) P 在最内层的这样一个 lambda `E` 的函数形参作用域内，但不在它的形参列表里，也就是在尾置返回类型、`noexcept` 说明或函数体中。

满足时，表达式的类型就是通过 `E` 的调用运算符的对象形参访问那个捕获成员时的类型。

```cpp run
#include <type_traits>

void f() {
  float x, &r = x;

  [=]() -> decltype((x)) {     // 返回 const float&
    decltype(x) y1;            // float：不加括号看声明类型
    decltype((x)) y2 = y1;     // const float&
    decltype(r) r1 = y1;       // float&：声明类型
    decltype((r)) r2 = y2;     // const float&：捕获的是被引用的 float
    static_assert(std::is_same_v<decltype(y2), const float&>);
    static_assert(std::is_same_v<decltype(r2), const float&>);
    (void)r1;
    return y2;
  };

  [=](decltype((x)) y) {       // 形参列表不满足 (4.4)：float&
    static_assert(std::is_same_v<decltype(y), float&>);
  };

  [=] {
    [](decltype((x)) y) { };   // 标准：const float&；Clang 23：float&
  };
}

int main() { }
```

最后一个例子考验对 (4.4) 的理解。P 在内层 lambda 的形参列表里，但 (4.4) 说的是最内层的这样一个 lambda，即按值捕获了 `x` 的外层 `[=]`。P 在外层 lambda 的函数体中，不在外层的形参列表里，所以条件成立，类型是 `const float&`。标准的例子就是这样注释的。

这个代码块没有标判定，因为 Clang 23 对嵌套的情形给出 `float&`，与标准不一致；其余几种情形与标准一致。如果在最后一个 lambda 里加上 `static_assert(std::is_same_v<decltype(y), const float&>)`，Clang 会报断言失败。

形参列表被排除在外，是因为形参类型决定了调用运算符的签名，签名应当只依赖外部可见的信息。何况隐式捕获时，要看完整个函数体才知道捕获了哪些变量。

### 协程形参

¶5 协程开始执行时，形参被复制或移动到协程帧中（[[dcl.fct.def.coroutine]]），之后协程体里的形参名指的是那份副本。按引用接受的形参只复制了引用本身，所以首次挂起之后它可能悬垂。

### 模板形参对象

¶9 类类型的非类型模板形参命名的是一个**模板形参对象**（[[g:template-parameter-object|template parameter object]]，[[temp.param]]）：一个静态存储期的 const 对象，整个程序中值相同的实参共享同一个对象。所以表达式类型是 `const T`，按 ¶12 是 lvalue，可以取地址。标量类型的非类型模板形参 `N` 落入 ¶12 的其他情况，是 prvalue，`&N` 非良构。

```cpp run ok
#include <type_traits>

struct P { int x; };

template<P p> constexpr const P* addr() {
  static_assert(std::is_same_v<decltype((p)), const P&>);  // const lvalue
  return &p;                                               // OK：有地址
}
template<int N> void nn() {
  static_assert(std::is_same_v<decltype((N)), int>);       // prvalue
}

static_assert(addr<P{1}>() == addr<P{1}>());   // 值相同，同一个对象

int main() { nn<1>(); }
```

### 契约谓词中的名字 {{c++26}}

契约断言应该只观察程序状态。所以谓词里命名外部的变量时，类型一律带 const，但这个 const 是浅的，只加在名字本身上。

¶6 后置条件的结果绑定（[[dcl.contract.res]]，`post(r: r > 0)` 中的 `r`）：函数返回 `T&` 时 `r` 的类型是 `const T`，否则是 `const U`（`U` 是返回类型）。

¶7 在契约断言 `C` 的谓词中命名以下实体时，类型是 `const T`：`C` 之外声明的对象类型变量（类型 `T`）、`C` 之外声明的引用类型变量或模板形参（类型为 `T` 的引用）、对应变量在 `C` 之外声明的结构化绑定。

¶8 是一个长例子，要点如下：

- `pre(++i)`、`pre(++r)`、`pre(x.m())` 非良构，因为 `i`、`r`、`x` 被当作 const；
- `pre(++(*p))`、`pre(px->m())` 良构，const 只加在 `p` 本身上，不传到它指向的对象；
- 模板形参 `template<int N, int& R>` 中，`pre(++N)` 非良构是因为 `N` 是 prvalue，`pre(++R)` 非良构是因为 `R` 按 const 处理；
- 谓词里的 `[=] mutable { ++p; }` 良构，lambda 体内的 `p` 指的是闭包自己的成员；而按引用捕获的 `i` 在 lambda 里仍然指向那个被当作 const 的外部实体，`++i` 非良构。

截至写作时，Clang 23 还不支持契约，这些规则无法在本地验证。

## 值类别 [expr.prim.id.unqual]

¶12 非限定名的值类别：

- move-eligible（见下一节）时是 xvalue；
- 实体是函数、变量、结构化绑定、结果绑定、数据成员或模板形参对象时是 lvalue；
- 其他情况（枚举项、标量类型的非类型模板形参等）是 prvalue。

如果名字指代位域，表达式也是位域。

变量包括引用类型的变量。`int&& rr = 1;` 之后，`rr` 是 `int` 类型的 lvalue。常说的有名字的右值引用是左值，就是这条规则。

## 隐式移动 [expr.prim.id.unqual]

<div class="compare" markdown="1">

```cpp ok
#include <memory>
using U = std::unique_ptr<int>;

U f1(U p)   { return p; }
U f2()      { U p; return (p); }
U f3(U&& p) { return p; }
U&& f4(U&& p) { return p; }
U f5() { U p; { { return p; } } }
void t1()   { U p; throw p; }
```

```cpp error
#include <memory>
using U = std::unique_ptr<int>;

void t2() {
  U p;
  try { throw p; } catch (...) {}
}
U f6() { static U p; return p; }
U f7() {
  U p;
  return [&] { return p; }();
}
struct H { U m; U get() { return m; } };
```

</div>

左边每个 `p` 都被移动，右边每一处都试图复制 `unique_ptr`，全部报错。区别在于名字是否 move-eligible。

¶15 **可隐式移动的实体**（[[g:implicitly-movable-entity|implicitly movable entity]]）是自动存储期的变量，并且是非 volatile 对象，或者指向非 volatile 对象类型的右值引用。一个 id 表达式是 [[g:move-eligible|**move-eligible**]] 的，当且仅当：

- (15.1) 它指代可隐式移动的实体；
- (15.2) 它是 `return`、`co_return` 语句或 `throw` 表达式的操作数，可以带括号；
- (15.3) 从实体的声明到表达式所在的最内层作用域，中间隔着的都是块作用域；对 `throw`，这些块作用域还不能是 `try` 块的作用域。

move-eligible 的名字是 xvalue（¶12），重载决议自然选中移动构造函数。右边四个例子分别是：`try` 块介于其间、静态存储期、lambda 的作用域介于其间、`m` 是数据成员而不是变量。

!!! pitfall "C++23 的不兼容变化"
    C++23 起，`return` 一个右值引用变量得到 xvalue，下面原本合法的代码变成非良构：
    ```cpp
    std::string& bad(std::string&& s) {
      return s;   // C++20 OK；C++23 error: xvalue 不能绑定到非 const 左值引用
    }
    ```
    Clang 23 在 `-std=c++20` 下接受，在 `-std=c++23` 下拒绝。

!!! pitfall "只看名字本身"
    `return s.member;`、`return *p;`、`return std::get<0>(t);`、`return cond ? a : b;` 都不是 move-eligible 的名字，会复制。结构化绑定不是变量，`return b;`（`auto [b] = ...`）也不会隐式移动。

<details class="fine" markdown="1"><summary>契约中的形参与临时对象（¶13–14）</summary>

¶13 [[class.temporary]] 允许实现用临时对象传递平凡可复制的形参，以便放进寄存器。这时如果函数契约断言的谓词中命名了形参：前置条件的求值若先于形参对象的初始化，名字指代最近初始化的那个临时对象；后置条件中，名字指代临时对象还是形参对象是未指定的，但在同一次求值中保持一致。

¶14 后置条件中的结果绑定同理：如果求值先于结果对象的初始化，它指代最近初始化的临时对象。

这两条承认了调用约定的实际情况，只要不依赖对象地址的同一性，程序员感觉不到差别。

</details>

## 限定名 [expr.prim.id.qual]

*qualified-id* 由嵌套名说明符（*nested-name-specifier*，即 `::` 前面的部分）和一个 *unqualified-id* 组成。嵌套名说明符可以是 `::`、类型名、命名空间名、`decltype(...)`，以及 C++26 的 splice 说明符 `[: r :]`。

### 类外定义只能写在外围作用域

¶3 嵌套名说明符出现在被声明的名字里时，叫做**声明性的**（[[g:declarative-nested-name-specifier|declarative]]），例如类外定义 `void N::f() {}`、类头 `struct N::S { ... };`。它有两条限制：不能含 `decltype(...)` 或 splice；使用它的声明要么是友元声明，要么位于包含被重声明实体的作用域中。

```cpp error
namespace N { namespace M { void g(); } void h(); }

void N::h() {}                      // OK：全局作用域包含 N::h
namespace X { void N::M::g() {} }   // error: X 不包含 N::M::g
```

### 值类别

¶9 限定名在下列情况下是 lvalue，否则是 prvalue：

- (9.1) 非成员函数或静态成员函数；
- (9.2) 非静态成员函数，并且限定名是一元 `&` 的操作数；
- (9.3)–(9.5) 变量、结构化绑定、数据成员。

(9.2) 的意思是，`X::mf` 只在 `&X::mf` 中是 lvalue，这样 `&` 才能作用于它。C++ 中不存在可以单独使用的、非静态成员函数类型的 lvalue。

¶6–¶8 规定结果就是限定名查找（[[basic.lookup.qual]]）找到的实体，类型就是它的类型；契约谓词中的 const 规则与 [[expr.prim.id.unqual#7]] 相同。

<details class="fine" markdown="1"><summary>其余条文</summary>

¶1 *qualified-id* 的组成名字是它的嵌套名说明符和 *unqualified-id* 的组成名字。**组成名字**（[[g:component-name|component name]]）和**终端名字**（[[g:terminal-name|terminal name]]，词法上最后出现的组成名字，如 `N::C<int>::f` 中的 `f`）是 C++23 重写名字查找时引入的术语，定义在 [[expr.prim.id.unqual#2]]，[[basic.lookup.qual]] 用它们说明哪个名字在哪个作用域里查找。

¶2 {{c++26}} splice 说明符后面不跟 `::` 时，不会被当作嵌套名说明符的一部分。`template [: r :]<args>::` 中的 `template` 只有在前面有 `typename` 时才能省略。所以 `[:^^TCls:]<3>::type v6 = 6;` 非良构，`<` 会被当作小于号。

¶4 规定嵌套名说明符指代什么：`::` 指全局命名空间；`decltype(E)::` 指那个类型，它必须是类或枚举；`[: r :]::` 指 `r` 反射的类、枚举或命名空间。(4.5) 处理类模板成员的类外定义：`template<class T> void TT<T>::f() {}` 中，如果实参列表恰好是对应模板头的形参列表，就指代主模板，两个模板头必须等价；否则指代对应的部分特化，不存在就非良构。(4.6) 规定非声明性的嵌套名说明符不能指代模板本身，不能写 `std::vector::size_type`。

¶5 不允许 `N::~decltype(x)` 与 `decltype(x)::~T` 两种形式。`~decltype(x)` 只能以非限定形式出现，如 `p->~decltype(*p)()`。

</details>

## 包索引 {{c++26}} [expr.prim.pack.index]

```cpp run ok
#include <cstddef>
#include <type_traits>
#include <utility>

template<class... Ts> constexpr auto first(Ts... ts) { return ts...[0]; }

template<std::size_t I, class... Ts>
constexpr decltype(auto) nth(Ts&&... ts) {
  return std::forward<Ts...[I]>(ts...[I]);   // 类型包索引 + 表达式包索引
}

template<class... Ts> void g(Ts... ts) {
  static_assert(std::is_same_v<decltype(ts...[0]), int>);     // 声明类型
  static_assert(std::is_same_v<decltype((ts...[0])), int&>);  // lvalue
}

static_assert(first(1, 2.0, 'c') == 1);

int main() {
  g(1, 'x');
  int x = 3;
  static_assert(std::is_same_v<decltype(nth<0>(x, 2)), int&>);
  static_assert(std::is_same_v<decltype(nth<1>(x, 2)), int&&>);
}
```

¶1 `ts...[I]` 中的 `ts` 必须是一个指代包的标识符：函数形参包、非类型模板形参包、init-capture 包或结构化绑定包。类型的包索引 `Ts...[I]` 见 [[dcl.type.pack.index]]。

¶2 下标必须是 `std::size_t` 类型的转换常量表达式（[[expr.const.const]]），值 V 满足 0 ≤ V < `sizeof...(ts)`。转换常量表达式禁止窄化，所以 `ts...[-1]` 直接非良构，不会回绕成一个很大的数。

```cpp error
template<class... Ts> auto bad(Ts... ts)  { return ts...[3]; }
int x = bad(1, 2);                                               // error: 越界

template<class... Ts> auto bad2(Ts... ts) { return ts...[-1]; }  // error: 窄化
```

¶3 包索引表达式本身算一个包展开（[[temp.variadic]]），虽然它只产生一个元素。这样规定是技术上的需要：其中的 `ts` 算是已经展开过，不会被外层的 `...` 再展开一次。实例化时它直接替换成第 V 个元素的名字（[[temp.variadic#11]]），所以类型和值类别与直接写那个元素完全一样。

!!! history
    C++26 之前，取包的第 N 个元素只能用递归模板或 `std::get<N>(std::forward_as_tuple(ts...))`，编译慢，也难读。包索引由 [[P2662R3]] 引入。它改变了一种旧写法的含义：C++23 中 `template<class... T> void f(T...[1]);` 声明一个无名的数组形参包，C++26 中 `T...[1]` 是包索引（[[diff.cpp23.dcl.dcl#2]]）。

## 伪析构函数 [expr.prim.id.dtor]

```cpp run ok
template<class T> void destroy(T* p) { p->~T(); }

int main() {
  using T = int;
  int i = 0;
  i.~T();             // 结束 i 的生命周期
  int j = 0;
  j.~decltype(j)();   // ~decltype(...) 形式
  int k = 0;
  destroy(&k);        // T 为 int：伪析构函数调用
}
```

泛型代码需要对任意类型调用析构函数，`destroy<int>` 也要能编译。为此，标量类型也有一个可以调用的析构函数名。

¶1 名字 `~T` 指代类型 `T` 的析构函数。`T` 是类类型时，它就是真正的析构函数（[[class.dtor]]）；否则它命名一个[[g:pseudo-destructor|**伪析构函数**]]（pseudo-destructor）。

¶2 伪析构函数只能用于标量类型，并且只能写成完整的调用形式 `obj.~T()` 或 `p->~T()`。注 1 指出，这样的调用会结束对象的生命周期（[[basic.life]]）。C++17 及以前，伪析构函数调用除了求值左边的表达式外什么也不做；C++20 起它结束生命周期，`std::destroy_at` 对标量和类类型的行为因此一致。之后再读 `i` 就是读取生命周期已结束的对象，常量求值器会拒绝：

```cpp error
constexpr int g() {
  int i = 1;
  using T = int;
  i.~T();
  return i;   // 读取生命周期已结束的对象
}
constexpr int v = g();   // error: 不是常量表达式
```

¶3 标准的例子还给出了几种边界情况：

```cpp ub
struct C { };
void f() {
  C* pc = new C;
  using C2 = C;
  pc->C::~C2();   // OK：析构 *pc，~C2 经别名指向 C
  C().C::~C();    // UB: 临时对象被析构两次
  using T = int;
  0 .T::~T();     // OK：没有效果
  ::operator delete(pc);
}
```

`C().C::~C()` 显式析构了临时对象，完整表达式结束时它又被析构一次。

`0 .T::~T()` 中间的空格必不可少。写成 `0.T::~T()`，`0.T` 会被切成一个记号，标准说它是一个用户定义浮点字面量（[[lex.ext]]），非良构；Clang 23 报告的是 `invalid suffix 'T' on floating constant`。`i.~int()` 也非良构，`~` 后面必须是类型名或 `decltype`，`int` 是关键字。

!!! lawyer "`~T()` 不是析构函数调用"
    单独写 `~T();`（`T` 是 `int`）是对值初始化的 `T()` 做按位取反，结果是 `-1`。[[expr.unary.op]] 规定，`~` 后面跟类型名时，这个歧义按一元运算符解析。只有在 `.` 或 `->` 之后，`~T` 才是析构函数名。

## 实现视角

!!! impl
    在 Clang 的 AST 中，隐式的成员访问是一个 `MemberExpr`，它的对象是一个标记为 implicit 的 `CXXThisExpr`，用 `-Xclang -ast-dump` 可以直接看到 ¶2 的改写。包索引在实例化时直接替换为对应的元素，不产生任何运行时代码。伪析构函数调用在优化后通常不生成指令，但常量求值器和 sanitizer 会利用生命周期已结束这一信息诊断后续的读取。

## 历史

!!! history
    成员名的隐式 `this->` 从 C++98 起就有。C++11 允许在未求值操作数中使用非静态数据成员（¶4.3），并引入 lambda，从而有了 lambda 中名字的类型问题；C++14 的 init-capture 让这条规则要覆盖 init-capture 声明的变量。C++20 让类类型的非类型模板形参命名模板形参对象，让伪析构函数结束生命周期，并通过 [[P1825R0]] 把隐式移动扩展到右值引用变量，当时仍按先当右值、失败再当左值的两阶段重载决议。C++23 由 [[P2036R3]] 确定了 lambda 尾置返回类型中按值捕获的名字的类型，由 [[P2266R3]] 把隐式移动简化为 move-eligible 的名字就是 xvalue。C++26 加入包索引、契约中的 const 规则和反射相关的规则。

## 思考题

!!! question "1. 下面三个 `r` 分别是什么类型？"
    ```cpp
    void f() {
      int x = 0;
      auto a = [x]() mutable { decltype((x)) r = x; };   // #1
      auto b = [&x] { decltype((x)) r = x; };             // #2
      auto c = [y = x] { decltype((y)) r = y; };          // #3
    }
    ```

<details markdown="1">
<summary>答案</summary>

`#1` 是 `int&`：lambda 是 `mutable`，调用运算符不是 const，闭包成员不加 const。

`#2` 是 `int&`：¶4 只处理按值捕获（(4.3)），按引用捕获时 `x` 就是外面的变量，`decltype((x))` 按普通规则得到 `int&`。

`#3` 是 `const int&`：(4.2) 明确包括 init-capture 声明的变量，`y` 按值捕获，lambda 不是 `mutable`。
</details>

!!! question "2. 下面的函数在 C++20 和 C++23 中分别是否良构？返回类型是什么？"
    ```cpp
    decltype(auto) pass(std::string&& s) { return s; }
    ```

<details markdown="1">
<summary>答案</summary>

返回类型在两个版本中都是 `std::string&&`：`decltype(auto)` 对不加括号的 `s` 给出声明类型。差别在于能否用 `s` 初始化这个返回值。

C++20 中，`s` 是 lvalue。[[P1825R0]] 的两阶段规则只用于选择构造函数，而这里是绑定引用，不涉及构造函数，于是 lvalue 不能绑定到 `std::string&&`，函数非良构。

C++23 中，`s` 是 move-eligible 的 xvalue，可以绑定，函数良构。Clang 23 的表现与此一致：`-std=c++20` 下报告 `rvalue reference to type ... cannot bind to lvalue`，`-std=c++23` 下通过。
</details>

!!! question "3. 在类 `X` 的成员函数中，`&X::m` 和 `&(X::m)` 分别是什么类型？如果 `m` 声明在 `X` 的基类 `B` 中，`&X::m` 又是什么类型？"

<details markdown="1">
<summary>答案</summary>

`&X::m` 不改写（(2.4)），形成成员指针 `int X::*`；`&(X::m)` 带括号，(2.4) 不适用，改写为 `&(*this).X::m`，得到 `int*`。如果 `m` 声明在基类 `B` 中，`&X::m` 的类型是 `int B::*`：[[expr.unary.op]] 规定成员指针的类是声明该成员的类，而不是限定名里写的类。它可以隐式转换为 `int X::*`。
</details>
