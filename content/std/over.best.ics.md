---
title: 隐式转换序列
summary: 重载决议用来衡量实参与形参匹配程度的工具：标准转换序列及其三个等级、用户定义转换序列、省略号转换序列，引用绑定和花括号列表实参的专门规则，以及一次转换最多只能有一次用户定义转换、歧义转换序列等特殊规则。
status: done
covers: over.best.ics.general, over.ics.scs, over.ics.user, over.ics.ellipsis, over.ics.ref, over.ics.list
papers: P0388R4
related: over.ics.rank, over.match.best, conv, class.conv, dcl.init.ref, dcl.init.list, over.match.list, topics/overload-resolution-walkthrough
tags: 重载决议, 转换, 初始化
updated: 2026-10-19
---

!!! tldr
    - 隐式转换序列描述的是用实参拷贝初始化形参这件事，只看类型、cv 限定和值类别。访问权限、位域、函数是否被删除、窄化，都要等函数选定之后才检查。
    - 隐式转换序列有三种形式：标准转换序列、用户定义转换序列、省略号转换序列。标准转换序列再分三个等级：精确匹配、提升、转换，整个序列的等级取决于最差的一步。
    - 按值传同类对象算恒等转换，传派生类对象算转换等级，尽管实际上调用了构造函数。
    - 一个实参的隐式转换中最多有一次用户定义转换；隐式对象形参只接受标准转换。
    - 实参是花括号列表时，`std::initializer_list`、数组、聚合、非聚合类、标量各有一条规则。

## 一个出人意料的重载

```cpp run ok
#include <string>
#include <cstdio>
void f(const char*) { std::puts("f(const char*)"); }
void f(std::string) { std::puts("f(std::string)"); }
void g(bool)        { std::puts("g(bool)"); }
void g(std::string) { std::puts("g(std::string)"); }
int main() {
  f("abc");   // f(const char*)
  g("abc");   // g(bool)
}
```

`g("abc")` 选的是 `g(bool)`。字符串字面量先退化成 `const char*`，再经布尔转换变成 `bool`，全程只用语言内建的转换。转换成 `std::string` 则要调用 `std::string` 的构造函数，这是用户定义的转换。重载决议规定，只用内建转换的序列总是胜过用到用户定义转换的序列，不管内建转换看起来多么不合理（[[over.ics.rank#2]]）。

要理解这类结果，先要知道编译器怎样描述一个实参到一个形参的转换。

## 隐式转换序列是什么 [over.best.ics.general]

¶1 **隐式转换序列**（implicit conversion sequence，ICS）是把函数调用中的一个实参转换到对应形参类型所用的一串转换。它遵守用单个表达式初始化对象或引用的规则（[[dcl.init]]、[[dcl.init.ref]]）。换句话说，ICS 描述的就是用实参初始化形参的过程，[[over.match.best]] 逐个实参比较的正是它。

¶2 ICS 只关心实参的类型、cv 限定和值类别，以及怎样把它们变得与形参一致。

!!! std
    "Other properties, such as the lifetime, storage duration, linkage, alignment, accessibility of the argument, whether the argument is a bit-field, and whether a function is deleted, are ignored."

所以一个函数可能因为 ICS 存在而可行、被选中，然后在真正初始化形参时出错（注 1）：

```cpp error
struct S { int b : 3; };
void f(int&);
void use(S s) {
  f(s.b);   // error: 非 const 引用不能绑定位域
}
```

计算 ICS 时，位域 `s.b` 被当作普通的 `int` 左值，与 `int&` 精确匹配，`f` 可行（[[over.ics.ref#4]]）。选中之后，禁止把非 const 左值引用绑定到位域的规则（[[dcl.init.ref]]）才起作用。

¶3 良构的 ICS 有三种形式：

1. **标准转换序列**（standard conversion sequence）：只用语言内建的转换（[[conv]]）；
2. **用户定义转换序列**（user-defined conversion sequence）：中间经过一次构造函数或转换函数；
3. **省略号转换序列**（ellipsis conversion sequence）：实参对应的是 `...`。

比较时标准转换序列最好，省略号最差（[[over.ics.rank#2]]），这就是开头 `g(bool)` 胜出的原因。

¶10–¶11 不需要任何转换时，ICS 是只含恒等转换的标准转换序列。找不到任何转换时，ICS 无法形成，这个函数不可行。¶13 只是说明三种形式在后面的子条款里定义。

## 标准转换序列 [over.ics.scs]

### 分类与等级（¶1–¶3）

¶1 标准把 [[conv]] 中的各种转换分成四类，¶3 又给每种转换一个**等级**（rank）：精确匹配（Exact Match）、提升（Promotion）或转换（Conversion）。

| 转换 | 类别 | 等级 |
|---|---|---|
| 无需转换 | 恒等 | 精确匹配 |
| 左值到右值（[[conv.lval]]） | 左值变换 | 精确匹配 |
| 数组到指针（[[conv.array]]） | 左值变换 | 精确匹配 |
| 函数到指针（[[conv.func]]） | 左值变换 | 精确匹配 |
| 限定转换，如 `int*` → `const int*`（[[conv.qual]]） | 限定调整 | 精确匹配 |
| 函数指针转换，去掉 `noexcept`（[[conv.fctptr]]） | 限定调整 | 精确匹配 |
| 整型提升（[[conv.prom]]） | 提升 | 提升 |
| 浮点提升，仅 `float` → `double`（[[conv.fpprom]]） | 提升 | 提升 |
| 整型转换（[[conv.integral]]） | 转换 | 转换 |
| 浮点转换（[[conv.double]]） | 转换 | 转换 |
| 浮点-整型转换（[[conv.fpint]]） | 转换 | 转换 |
| 指针转换，含空指针、到 `void*`、派生类到基类（[[conv.ptr]]） | 转换 | 转换 |
| 成员指针转换（[[conv.mem]]） | 转换 | 转换 |
| 布尔转换（[[conv.bool]]） | 转换 | 转换 |

注 1 指出这四类互不重叠：左值变换只改变值类别，限定调整只改变 cv 限定，提升和转换只改变数据表示。

¶2 注 2 补充，一个标准转换序列要么只有恒等转换，要么由其余类别中的一到三个转换组成，并按固定顺序排列：左值变换，然后是提升或转换，最后是限定调整。例如字符串字面量 `"abc"` 到 `const void*`，是数组到指针，再接指针转换 `const char*` → `const void*`。

¶3 整个序列的等级看其中最差的一步，引用绑定也算一步：有转换等级就是转换，否则有提升就是提升，否则是精确匹配。上例的等级是转换。`int[3]` 到 `const int*` 是数组到指针加限定转换，等级是精确匹配。

### 容易判断错的等级

```cpp error
void f(int);    void f(long);
void g(double); void g(long double);
void h(int);    void h(unsigned);
void p(void*);  void p(const int*);
void q(int*);   void q(long);
void use(short s, float fl, char c, int* ip) {
  f(s);    // f(int)：short → int 是提升，short → long 是转换
  g(fl);   // g(double)：float → double 是提升，float → long double 是转换
  h(c);    // h(int)：char → int 是提升，char → unsigned 是转换
  p(ip);   // p(const int*)：限定转换是精确匹配，到 void* 是转换
  q(0);    // error: 歧义，0 → int* 与 0 → long 都是转换等级
}
```

- 浮点提升只有 `float` → `double` 一种。`float` → `long double`、`double` → `long double` 都是浮点转换。
- 整型提升的目标只有 `int`、`unsigned int` 等少数类型（字符类型、无作用域枚举、位域另有规定，见 [[conv.prom]]）。`short` → `long`、`int` → `long` 都是整型转换。`bool` → `int` 是提升。
- 限定转换是精确匹配，所以 `int*` → `const int*` 与恒等同一等级，二者另靠 [[over.ics.rank#3.2.1]] 分出高下。

`q(0)` 是使用 `NULL` 的老问题，也是 C++11 引入 `nullptr` 的原因之一。`nullptr` 能转换成任何指针类型，却不能转换成 `long`，所以 `q(nullptr)` 没有歧义。

## 用户定义转换序列 [over.ics.user]

¶1 用户定义转换序列由三段组成：

```text
第一段标准转换  →  一次用户定义转换（[class.conv]）  →  第二段标准转换
```

用户定义转换由构造函数完成时（[[class.conv.ctor]]），第一段把源类型转换到这个构造函数第一个形参的类型；由转换函数完成时，第一段把源类型转换到转换函数对象形参的类型。

¶2 第二段把用户定义转换的结果转换到目标类型，引用绑定也算在第二段里。以 `f("hello")` 调用 `void f(std::string)` 为例：第一段是数组到指针，用户定义转换是构造函数 `std::string(const char*)`，第二段是恒等。

第 2 段末句还说，挑选用哪一个构造函数或转换函数本身也是一次重载决议，适用用户定义转换进行初始化时的特殊规则，例如比较转换结果到目标的那一步（[[over.match.best#2.2]]）。

¶3 如果用户定义转换由转换函数模板的特化完成，第二段必须是精确匹配等级。`template<class T> operator T()` 能转换成任何类型，如果之后还允许再接一个提升或转换，它几乎对所有目标都可行，会和其他候选形成大量歧义。模板实参推导（[[temp.deduct.conv]]）通常会直接推出目标类型，第二段本来就是恒等；¶3 排除了其余情形。

### 按值传递类对象（¶6–¶7，[over.ics.user]/4）

```cpp error
struct A {
  A();
  A(A&);      // 只有接受非 const 的拷贝构造函数
};
void f(A);
void f(...);
void use(const A ca) {
  f(ca);      // error: 选中 f(A)，但没有构造函数能用 const A 初始化形参
}
```

[[over.best.ics#6]] 规定，形参不是引用时，ICS 描述的是用实参拷贝初始化形参，即把实参转换成形参类型的 prvalue。注 3 补充，形参是类类型时这只是为重载决议定义的概念上的转换，真正的初始化由构造函数完成。

[[over.best.ics#7]] 规定，实参类型去掉 cv 后与形参类型相同时，ICS 是**恒等转换**；形参是类类型、实参是它的派生类时，ICS 是**派生类到基类的转换**，等级是转换。注 4 说明，标准转换里并没有这样一种转换，它只存在于 ICS 的描述中。

上例中 `const A` 到 `A` 的 ICS 是恒等，不包含任何转换，尽管 `A` 根本没有能接受 `const A` 的构造函数（标准例 2）。于是 `f(A)` 可行，并以恒等胜过省略号，选定之后初始化形参时才报错。

[over.ics.user]/4 从另一个角度说了同一件事：类类型表达式转换到同一类类型时是精确匹配，转换到基类时是转换等级，尽管实际调用了构造函数。如果把按值传同类对象当成用户定义转换，`f(A)` 就会比 `f(const A&)` 差得多，按值和按引用接受对象的重载就无法正常比较了。

## 一次转换最多一次用户定义转换（¶4）

```cpp error
struct Y { Y(int); };
struct A { operator int(); };
Y y1 = A();   // error: 需要 A → int → Y，两次用户定义转换

struct X { X(); };
struct B { operator X(); };
B b;
X x{{b}};     // error: B::operator X() 不是候选
```

¶4 当一个构造函数或转换函数本身正被当作一次用户定义转换来调用时，它的实参不能再经过用户定义转换。具体地说，目标是以下两者之一：

- ¶4.1 构造函数的第一个形参；
- ¶4.2 用户定义转换函数的对象形参；

并且这个函数是通过以下途径成为候选的：

- ¶4.3 [[over.match.ctor]]，实参是类拷贝初始化第二步中的临时对象；
- ¶4.4 [[over.match.copy]]、[[over.match.conv]] 或 [[over.match.ref]]；
- ¶4.5 [[over.match.list]] 的第二阶段，花括号列表恰好有一个本身也是花括号列表的元素，目标是类 `X` 构造函数的第一个形参，且要转换成 `X` 或 cv `X` 的引用；

这时不考虑用户定义转换序列。注 2 说明了目的：防止重载决议中出现多于一次的用户定义转换，从而避免无限递归。

`Y y1 = A()` 是用 `A` 类型的值拷贝初始化 `Y`，候选由 [[over.match.copy]] 给出，其中 `Y(int)` 本身就是那一次用户定义转换。它的形参要求 `A → int`，这又是一次用户定义转换，按 ¶4.1 和 ¶4.4 不予考虑，所以 `Y(int)` 不可行。

`X x{{b}}` 中，`{b}` 要匹配 `X` 拷贝或移动构造函数的第一个形参 `const X&` 或 `X&&`，¶4.5 适用，`b → X` 的转换不予考虑。否则这个初始化就成了先用 `b` 转换出一个临时 `X`，再拿它构造 `x`。

只有一次用户定义转换的限制针对每一个实参。多形参构造函数的每个形参对应不同的实参，各自都可以有一次用户定义转换。

## 对象形参（¶8–¶9）

¶8 静态成员函数也被当作有一个隐式对象形参，以便和非静态成员函数放在同一个候选集里比较。这个形参的 ICS 既不比任何标准转换序列好，也不比它差，所以比较结果完全取决于其余实参。

¶9 转换到隐式对象形参，或转换到赋值运算的左操作数时，只允许标准转换序列。否则 `x.f()` 可能先把 `x` 转换成一个无关的类型，再调用那个类型的成员。注 5 指出，显式对象形参（C++23 的 `this` 形参）是普通形参，可以经用户定义转换匹配：

```cpp ok
struct C {
  void k(this int);   // 显式对象形参是 int
  operator int() const { return 0; }
  void m(this const C& c) {
    c.k();            // OK：c → int 经用户定义转换
  }
};
```

## 歧义转换序列（¶12）

```cpp error
class B;
class A { A(B&); };
class B { operator A(); };
class C { C(B&); };
void f(A) { }
void f(C) { }
B b;
void use() {
  f(b);   // error: 歧义
}
```

`b` 转换成 `A` 有两条路：`A` 的构造函数 `A(B&)`，以及 `B` 的转换函数 `operator A()`。这两个函数在例子里都是私有的，但 ICS 不看访问权限。

¶12 如果有多个良构的 ICS 能把实参转换到形参类型，这个形参的 ICS 就是**歧义转换序列**（ambiguous conversion sequence）。排序时，它被当作一个与任何其他用户定义转换序列都分不出好坏的用户定义转换序列。如果使用它的函数最终被选中，调用非良构。

所以 `f(A)` 仍然可行，它与 `f(C)` 的 ICS 都是用户定义转换，分不出高下，调用歧义。注 6 说明了设计意图：不要因为某个形参的转换有歧义，就悄悄把整个函数剔除。如果把歧义当作无法转换，`f(b)` 会选中 `f(C)`；以后有人删掉 `A` 的一条转换路径，`f(A)` 重新可行，调用目标就会悄悄改变。

再加一个 `void f(B)`，调用就不再歧义：`f(B)` 是恒等，胜过两个用户定义转换序列。

## 省略号转换序列 [over.ics.ellipsis]

¶1 实参与被调函数的 `...` 匹配时，形成省略号转换序列。几乎任何实参都能匹配 `...`，而它在三种形式里最差，所以 `f(...)` 可以充当兜底的重载。C++11 之前的 SFINAE 检测就常用这个技巧：

```cpp run ok
#include <type_traits>
template<class T> std::true_type  has_size_impl(decltype(&T::size));
template<class T> std::false_type has_size_impl(...);
struct A { int size(); };
struct B {};
static_assert(decltype(has_size_impl<A>(nullptr))::value);
static_assert(!decltype(has_size_impl<B>(nullptr))::value);
int main() {}
```

对 `A`，第一个重载可行，`nullptr` 到成员函数指针是转换等级，胜过省略号。对 `B`，第一个重载推导失败，只剩省略号。

在求值语境中，把有非平凡拷贝、移动构造函数或析构函数的类对象传给 `...` 是有条件支持的（[[expr.call]]）。上例在 `decltype` 里，不求值，没有这个问题。

## 引用绑定 [over.ics.ref]

### 直接绑定（¶1）

引用**直接绑定**（[[dcl.init.ref]]）指引用绑定到实参本身（或它的基类子对象），不经过临时对象。

¶1 到 cv `T` 的引用形参直接绑定到实参时：

- ¶1.1 实参类型 `D` 是 `T` 的派生类：ICS 是 `D` 到 `T` 的派生类到基类的转换，等级是转换；
- ¶1.2 否则，实参类型是（可能带 cv 的）`T`，或者 `T` 是元素类型为 `U` 的未知边界数组、实参是元素类型为（可能带 cv 的）`U` 的已知边界数组：ICS 是恒等；
- ¶1.3 否则，`T` 是函数类型：ICS 是函数指针转换（实参是 `noexcept` 函数，形参是不带 `noexcept` 的函数引用）；
- ¶1.4 否则：ICS 是限定转换。

```cpp
struct A {};
struct B : public A {} b;
int f(A&);
int f(B&);
int i = f(b);               // f(B&)：恒等胜过派生类到基类

void g() noexcept;
int h(void (&)() noexcept); // #1
int h(void (&)());          // #2
int j = h(g);               // #1：恒等胜过函数指针转换
```

按 ¶1.2，`const int&` 绑定 `int` 左值也是恒等，实参比形参少的 cv 不算一次转换，另由 [[over.ics.rank#3.2.6]] 比较。¶1.2 中关于未知边界数组的部分来自 C++20 的 [[P0388R4]]，它允许 `int(&)[]` 绑定 `int[3]`。¶1.4 出现在多级指针加 cv 的场合，例如 `const int* const&` 直接绑定 `int*` 左值。

如果引用直接绑定到对实参调用转换函数的结果上，ICS 是用户定义转换序列，第二段按上面四条确定。

!!! impl "Clang 的偏离"
    本机 Clang 23 对 `h(g)` 报 "call to 'h' is ambiguous"，没有把函数指针转换当作比恒等更差的序列。按标准（这是 [over.ics.ref] 的例 1），应调用 #1。`f(b)` 的结果与标准一致。

### 不直接绑定（¶2）

¶2 引用不直接绑定时，ICS 就是把实参转换到被引用类型所需的序列，相当于用实参拷贝初始化一个被引用类型的临时对象。例如 `void f(const long&)` 接受 `int` 实参，ICS 是 `int` → `long` 的整型转换。被引用类型上顶层 cv 的差异由初始化本身吸收，不算一次转换。

### 左值与右值的限制（¶3–¶4）

¶3 除隐式对象形参外（见 [[over.match.funcs]]），下面两种绑定无法形成 ICS：把左值引用绑定到右值，除非它引用的是非 volatile 的 const 类型；把右值引用绑定到对象类型的左值。

```cpp error
void f(const volatile int&);
void g(int&&);
void h(void(&&)());
void fn();
void use(int i) {
  f(1);    // error: const volatile 的左值引用不能绑定右值
  g(i);    // error: 右值引用不能绑定对象类型的左值
  h(fn);   // OK：右值引用可以绑定函数左值
}
```

注 1 指出，这意味着形参是非 const 左值引用时，如果实参需要创建临时对象，这个函数就不可行。函数只有左值，而右值引用可以绑定函数左值，所以 ¶3 只限制对象类型的左值。

¶4 其他不取决于引用和实参类型的绑定限制，不影响 ICS 的形成。前面位域的例子就属于这种情况（标准例 2）。

## 花括号列表实参 [over.ics.list]

¶1 实参是花括号列表（[[dcl.init.list]]）时，它不是表达式，没有类型，转换规则单独规定。下面各条以否则相连，按顺序找第一条适用的：

| 段落 | 形参类型 | 条件 | ICS |
|---|---|---|---|
| ¶2 | 非引用 | 列表带指派符 | 形参是能由它聚合初始化的聚合时，为用户定义转换序列（第二段恒等）；否则无法转换 |
| ¶3 | 聚合类 `X` | 只有一个元素，类型是 cv `U`，`U` 是 `X` 或其派生类 | 把这个元素转换到形参类型的序列 |
| ¶4 | 字符数组 | 只有一个元素，是类型合适的字符串字面量 | 恒等 |
| ¶5 | `std::initializer_list<X>` | 所有元素都能隐式转换为 `X` | 各元素转换中最差的那个；空列表为恒等 |
| ¶6 | `X[N]` 或 `X[]` | 每个元素（`N` 更大时还有补位的 `{}`）都能转换为 `X` | 其中最差的那个 |
| ¶7 | 非聚合类 `X` | [[over.match.list]] 选出唯一最佳构造函数 `C` | 见下文 |
| ¶8 | 聚合 | 能按聚合初始化规则初始化 | 用户定义转换序列（第二段恒等） |
| ¶9 | 引用 | | 按 [over.ics.ref]，本节规则用于初始化引用绑定的临时对象 |
| ¶10 | 非类类型 | 一个不是花括号列表的元素，或空列表 | 该元素的转换；空列表为恒等 |
| ¶11 | 其他 | | 无法转换 |

窄化不影响 ICS 的形成。下面的 `f({1.0})` 中 `double` → `int` 是浮点-整型转换，ICS 存在，`f` 被选中，然后按 [[dcl.init.list]] 检查出窄化，非良构。

### 标量与 `initializer_list`（¶5、¶10）

```cpp error
#include <initializer_list>
void f(std::initializer_list<int>);
void g(int);
void use() {
  f({});           // OK：恒等
  f({'a', 'b'});   // OK：整型提升
  f({1.0});        // error: 窄化
  g({'a'});        // OK：与 char → int 相同，提升
  g({});           // OK：恒等（值初始化）
}
```

¶5 元素到 `X` 的转换可以是用户定义转换，即使是在调用初始化列表构造函数的语境中。标准的例子里，`A(std::initializer_list<std::string>)` 能接受 `{"foo", "bar"}`，每个元素都经 `std::string` 的构造函数转换。

¶11 其余情况一律无法转换，例如对 `void g(int)` 调用 `g({1, 2})`，或 `g({{1}})`（元素本身是花括号列表）。

### 非聚合类（¶7）

¶7 形参是非聚合类 `X`，且 [[over.match.list]] 为用这个列表初始化 `X` 选出了唯一最佳的构造函数 `C`：

- ¶7.1 `C` 不是初始化列表构造函数，且列表只有一个类型为 cv `U` 的元素，`U` 是 `X` 或其派生类：`U` 是 `X` 时为精确匹配，是派生类时为转换等级；
- ¶7.2 否则：用户定义转换序列，第二段为恒等。

有多个构造函数可行但没有一个最好时，ICS 是歧义转换序列。

```cpp error
#include <initializer_list>
#include <string>
struct A { A(std::initializer_list<int>); };
struct B { B(int, double); };
struct C { C(std::string); };
void f(A);
void g(B);
void h(C);
void use() {
  f({'a', 'b'});   // OK：经 A(initializer_list<int>)
  g({'a', 'b'});   // OK：经 B(int, double)
  g({1.0, 1.0});   // error: 窄化
  h({"foo"});      // OK：经 C(std::string)
}
void f(B);
void use2() {
  f({'a', 'b'});   // error: f(A) 与 f(B) 歧义
}
```

`f({'a', 'b'})` 加入 `f(B)` 后歧义：两边都是用户定义转换序列，用的是不同的构造函数，无法比较（[[over.ics.rank#3.3]]）。

`h({"foo"})` 中，列表到 `C` 是一次用户定义转换，元素 `"foo"` 到 `std::string` 又是一次。列表初始化可以包含多于一次用户定义转换，[[over.match.funcs#6]] 明确把它排除在只能一次的限制之外。

### 带指派符的列表（¶2）{{c++20}}

```cpp error
struct A { int x, y; };
struct B { int y, x; };
void f(A a, int);         // #1
void f(B b, ...);         // #2
void g(A a);              // #3
void g(B b);              // #4
void h() {
  f({.x = 1, .y = 2}, 0); // OK：#1
  f({.y = 2, .x = 1}, 0); // error: 选中 #1，但指派顺序与 A 的成员顺序不符
  g({.x = 1, .y = 2});    // error: #3 与 #4 歧义
}
```

¶2 带指派符的列表只能转换成能由它聚合初始化的聚合。注 1 说明，判断可行性时不看指派符的顺序；选中的函数如果顺序不符，初始化形参时才非良构。所以 `g` 的两个重载都可行，ICS 都是用户定义转换，调用歧义。

前两个 `f` 调用中，两个重载的第一个实参都可行，`0` 匹配 `int` 胜过匹配 `...`，所以都选 #1。第二个调用随后因顺序不符而非良构。本机 Clang 23 对它只给出 `-Wreorder-init-list` 警告，作为扩展接受。

### 单元素的同类聚合（¶3）

```cpp run ok
struct Agg { int a; int b; };
struct D : Agg {};
int f(Agg) { return 1; }
int main() {
  Agg x{1, 2};
  D d{};
  return f({x}) + f({d}) == 2 ? 0 : 1;   // {x}：恒等；{d}：派生类到基类
}
```

没有 ¶3，`{x}` 会被理解为用 `x` 初始化 `Agg` 的第一个成员 `a`，而 `Agg` 无法转换成 `int`，转换失败。C++11 中确实如此，后来一个缺陷报告加入了这一条，并同步修改了 [[dcl.init.list]]。

### 数组、聚合与引用（¶6、¶8、¶9）

```cpp ok
typedef int IA[3];
void h(const IA&);
struct A { int m1; double m2; };
void f(A);
void g(const A&);
void k(const double&);
void use() {
  h({1, 2, 3});    // OK：恒等
  h({1, 2});       // OK：第三个元素由 {} 初始化
  f({'a', 'b'});   // OK：聚合初始化，用户定义转换
  g({'a', 'b'});   // OK：引用形参，规则用于底层的临时对象
  k({1});          // OK：与 int → double 相同的转换
}
```

¶6 的形参类型是数组，这只会出现在引用形参的被引用类型中，因为没有数组类型的形参（脚注 99）。到未知边界数组的转换，以及元素更少者更好的排序规则，都来自 C++20 的 [[P0388R4]]，见 [[over.ics.rank#3.1]]。

## 实现视角

!!! impl
    - Clang 用 `ImplicitConversionSequence` 表示 ICS，种类有标准、用户定义、省略号、歧义和无法转换五种。`StandardConversionSequence` 有 `First`、`Second`、`Third` 三个槽，分别对应左值变换、提升或转换、限定调整，与 [over.ics.scs] 的顺序一致。
    - 窄化、位域、访问权限这些在 ICS 阶段被忽略的检查，编译器也是分两步做的：先计算 ICS 并选出函数，再对选中的函数完整地执行一次初始化，这时才报错。

## 历史与演进

!!! history
    - C++98 已有三种形式、等级表、只允许一次用户定义转换的规则和歧义转换序列。
    - C++11 加入花括号列表实参的规则和右值引用的绑定限制。之后的缺陷报告加入了单元素同类聚合（¶3）和非聚合类单元素同类列表的等级（¶7.1）。
    - C++17 把 `noexcept` 纳入函数类型，函数指针转换作为限定调整加入，等级为精确匹配。
    - C++20 加入带指派符的列表（¶2）和到未知边界数组的转换（[[P0388R4]]）。
    - C++23 的显式对象形参可以经用户定义转换匹配（¶9 注 5）。

## 常见误解

!!! pitfall "`int` → `long` 是提升"
    整型提升只到 `int`、`unsigned int` 这一级。`int` → `long` 是整型转换，与 `int` → `double` 同为转换等级，所以 `f(long)` 和 `f(double)` 并存时 `f(1)` 歧义。

!!! pitfall "窄化会让重载不可行"
    窄化在函数选定之后才报错。`f(int)` 接受 `{1.5}` 时调用非良构，编译器不会因此改选其他重载，除非其他重载本来就更好，比如 `f(double)` 是恒等。

!!! pitfall "按值传递同类对象是用户定义转换"
    `f(A)` 接受 `A` 实参时 ICS 是恒等，尽管实际要调用拷贝构造函数（¶7、[over.ics.user]/4）。

## 思考题

!!! question "思考题 1"
    `void k(long); void k(std::string);` 并存时，`k(0)` 和 `k("x")` 各调用哪个？

<details markdown="1">
<summary>答案</summary>

`k(0)`：`0` → `long` 是整型转换，属于标准转换序列。`0` 是空指针常量，也能经 `std::string` 的构造函数转换成 `std::string`，但那是用户定义转换序列。标准转换序列更好，选 `k(long)`。

`k("x")`：`const char[2]` 无法经标准转换变成 `long`（指针不能隐式转换成整数），`k(long)` 不可行，只能选 `k(std::string)`。
</details>

!!! question "思考题 2"
    ¶12 把歧义转换序列当作用户定义转换序列参与比较，而不是当作无法转换。举一个两种处理给出不同结果的例子。

<details markdown="1">
<summary>答案</summary>

正文 `A`、`B`、`C` 的例子就是。如果把 `b → A` 的歧义当作无法转换，`f(A)` 不可行，`f(b)` 会选中 `f(C)`。按标准的处理，`f(A)` 可行，它与 `f(C)` 分不出高下，调用歧义。标准选择报错，是为了不让偶然存在两条转换路径这种情况悄悄决定调用目标。
</details>
