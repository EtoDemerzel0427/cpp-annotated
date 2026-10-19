---
title: 表达式中的运算符
summary: 运算符表达式如何变成一次重载决议：成员、非成员、内建、改写四类候选；C++20 的 ==/!=/<=> 改写与参数反转，以及改写目标规则如何修复兼容性问题。
status: draft
since: c++98
papers: P0515R3, P1185R2, P2468R2, P0145R3
related: over.match, over.match.best, over.built, over.oper, expr.eq, expr.rel, expr.spaceship, class.compare.default
tags: 重载决议, 运算符, 比较
updated: 2026-10-17
---

`a + b` 看起来只是一个表达式，但只要有一个操作数是类或枚举类型，它就会变成一次重载决议：候选包括 `a` 的成员 `operator+`、通过普通查找与 ADL 找到的非成员 `operator+`，以及一批假想的内建 `operator+(int, int)`、`operator+(double, double)`……C++20 起，比较运算符还多了第四类候选，即**改写候选**：`a < b` 可以用 `operator<=>` 实现，`a != b` 可以用 `operator==` 实现，`1 == x` 可以用 `x == 1` 的那个函数实现。

本页是 [[over.match]] 七种语境中的第三种（[[over.match.general#2.3]]），也是 C++20 以来变化最大的一种。

## 何时根本不做重载决议（¶1）

¶1 若运算符的所有操作数都既不是类类型也不是枚举类型，就直接视为内建运算符，按 [[expr.compound]] 解释，既不查找，也不做决议。

```cpp
struct String {
  String(const String&);
  String(const char*);
  operator const char*();
};
String operator+(const String&, const String&);

void f() {
  const char* p = "one" + "two";   // error: 两个指针不能相加；operator+ 根本不会被考虑
  int i = 1 + 1;                   // 永远是 2，无论定义了什么类或枚举
}
```

这条规则起到隔离作用，用户代码无法改变 `int + int` 或 `指针 + 指针` 的含义。重载运算符的声明也受同样的约束：[[over.oper]] 要求运算符函数至少有一个类或枚举类型的形参。两条规则合起来保证了内建类型上的运算永远是内建语义。

注 1：`.`、`.*`、`::` 不能重载，总是内建的；`?:` 也不能重载，但 [[expr.cond]] 借用本节的规则来决定第二、三操作数为类/枚举类型时如何转换。

## 运算符到函数调用的变换（¶2）

¶2 只要有一个操作数是类或枚举类型，就可能存在用户定义的运算符函数，或者需要一次用户定义转换把操作数变成内建运算符能接受的类型。此时用重载决议决定调用哪个运算符函数或内建运算符。为此，先把运算符写法变换为等价的函数调用写法（表 18）：

| 子条款 | 表达式 | 成员函数形式 | 非成员函数形式 |
|---|---|---|---|
| [[over.unary]] | `@a` | `(a).operator@()` | `operator@(a)` |
| [[over.binary]] | `a@b` | `(a).operator@(b)` | `operator@(a, b)` |
| [[over.assign]] | `a=b` | `(a).operator=(b)` | — |
| [[over.sub]] | `a[b]` | `(a).operator[](b)` | — |
| [[over.ref]] | `a->` | `(a).operator->()` | — |
| [[over.inc]] | `a@`（后缀） | `(a).operator@(0)` | `operator@(a, 0)` |

`=`、`[]`、`->`（以及表中未列的 `()`）只能是成员函数。

!!! std
    "However, the operands are sequenced in the order prescribed for the built-in operator."

    但操作数的定序遵循内建运算符的规定。

这句话是 C++17 加进来的（[[P0145R3]]，"Refining Expression Evaluation Order"）。按照这条规定，`std::cout << f() << g()` 即使调用的是重载的 `operator<<`，`f()` 也保证先于 `g()` 求值；`a = b` 中 `b` 先于 `a` 定序。在 C++14 及以前，重载运算符按函数调用规则对待，实参求值顺序未指定。

## 四类候选（¶3）

¶3 对一元运算符 `@`（操作数类型 `cv1 T1`）和二元运算符 `@`（左操作数 `cv1 T1`、右操作数 `cv2 T2`），构造四个候选集：

### 成员候选（¶3.1）

若 `T1` 是完整类类型或正在定义的类，成员候选是在 `T1` 作用域中搜索 `operator@` 的结果；否则为空。

注意成员候选只看左操作数：`1 + x` 不会考虑 `x` 的成员 `operator+`（C++20 的反转候选是另一回事，见下文）。正因为如此，对称的二元运算符传统上写成非成员（或隐藏友元）。

### 非成员候选（¶3.2）

对 `=`、`[]`、`->`，非成员候选集为空。否则，它是对 `operator@` 在改写后的函数调用中做非限定查找（[[basic.lookup.unqual]]）和实参依赖查找（[[basic.lookup.argdep]]）的结果，并且**忽略所有成员函数**。

忽略成员函数这一点，使运算符表达式的行为与普通函数调用不同（本节末段的注 3）：

```cpp
struct A {};
void operator+(A, A);

struct B {
  void operator+(B);
  void f();
};
A a;
void B::f() {
  a + a;              // OK：运算符表达式的非成员查找忽略成员，找到全局 operator+
  operator+(a, a);    // error: 函数调用语法，非限定查找先在类 B 中找到 B::operator+，全局的被隐藏
}
```

还有一条限制：若没有操作数是类类型（即只有枚举），那么只有第一形参是 `T1`（或到 `cv T1` 的引用，`T1` 是枚举时）、或第二形参是 `T2`（或其引用，`T2` 是枚举时）的非成员函数才是候选。这样做是为了防止借助类的转换构造函数接管枚举上的运算：

```cpp run ok
enum E { a = 1 };
struct S { S(E) {} };
int operator+(S, S) { return 42; }   // 形参是 S 而不是 E
int main() {
  return a + a;    // 内建加法，结果 2：operator+(S, S) 的形参不是 E，根本不是候选
}
```

（就这个例子而言，即便 `operator+(S,S)` 是候选也会输给内建的 `operator+(int,int)`；但若内建候选不可行，或有多个用户定义转换路径，这条规则就决定了结果。它的本意是：只有专门为这个枚举写的运算符，才会用于这个枚举。）

### 内建候选（¶3.3）

对 `,`、一元 `&`、`->`，内建候选集为空。对其他运算符，内建候选是 [[over.built]] 中定义的那些候选运算符函数里：

- ¶3.3.1 运算符名字相同，
- ¶3.3.2 操作数个数相同，
- ¶3.3.3 给定操作数能按 [[over.best.ics]] 转换到其形参类型，
- ¶3.3.4 与任何非模板的非成员候选（或改写的非成员候选）的形参类型列表不相同。

[[over.built]] 列出的是一族假想的函数，如对每对提升后的算术类型 `L`、`R` 有 `LR operator+(L, R)`，对每个枚举类型 `T` 有 `bool operator==(T, T)`。有了它们，内建运算符和用户定义运算符就能放在一起比较，例如类类型操作数经用户定义转换变成 `int` 去用内建 `+`。

¶3.3.4 避免了用户为枚举定义的运算符与同签名的内建候选打成平局：

```cpp run ok
enum class Color { red };
bool operator==(Color, Color) { return false; }   // 用户版本，与内建 bool operator==(Color, Color) 同签名
int main() {
  return Color::red == Color::red;   // 0：内建候选被剔除，调用用户版本
}
```

### 改写候选（¶3.4）{{c++20}}

改写候选是 C++20 三路比较的核心机制：

| 表达式 | 改写候选包括 |
|---|---|
| `x < y`、`x <= y`、`x > y`、`x >= y` | ① 对 `x <=> y` 的所有非改写候选；② 对 `y <=> x` 的每个非改写候选合成一个参数反转的候选 |
| `x <=> y` | 对 `y <=> x` 的每个非改写候选合成反转候选 |
| `x != y` | ① 对 `x == y` 的非改写候选中，以 `x` 为第一操作数的改写目标；② 对 `y == x` 的、以 `y` 为第一操作数的改写目标合成反转候选 |
| `x == y` | 对 `y == x` 的、以 `y` 为第一操作数的改写目标合成反转候选 |
| 其他运算符 | 空 |

有两点设计值得注意：

- **`==` 不会被改写成 `<=>`**。最初的 [[P0515R3]] 允许 `==` 用 `<=>` 实现，但很快人们发现，`std::vector`、`std::string` 这类先比较长度就能快速得出不等的类型会因此付出性能代价，于是 [[P1185R2]] 把相等性与排序分开：`==`/`!=` 只用 `operator==` 改写，`<`、`<=`、`>`、`>=`、`<=>` 只用 `operator<=>` 改写。
- **改写只以非改写候选为原料**，不会递归改写（`x < y` 不会经由 `y <=> x` 再反转回来）。

注 2：由成员候选合成的反转候选，其对象形参变成了第二个形参，于是第一个形参（原来的显式形参）上可以做隐式转换，第二个（对象形参）上不能做用户定义转换。

```cpp run ok
#include <cassert>
struct S {
  int v;
  bool operator==(int i) const { return v == i; }
};
int main() {
  S s{1};
  assert(s == 1);       // 普通候选
  assert(1 == s);       // 反转候选：解释为 s == 1
  assert(!(s != 1));    // 改写候选：解释为 !(s == 1)
  assert(!(1 != s));    // 反转 + 改写：解释为 !(s == 1)
}
```

在 C++17 中，要支持这四种写法得写四个函数（`==` 与 `!=` 各两个方向）；C++20 只需一个。

## 改写目标：P2468 的修复（¶4）

C++20 的反转候选破坏了一批既有代码（见下文"兼容性"一节）。最常受影响的是这样一种旧写法：既写了 `operator==` 又写了 `operator!=`，但签名不对称（比如成员函数忘了 `const`）。C++23 的 [[P2468R2]]（作为对 C++20 的缺陷报告）引入了**改写目标**（[[g:rewrite-target|rewrite target]]）的概念：

¶4 名为 `operator==` 的非模板函数或函数模板 `F` 是以 `o` 为第一操作数的改写目标，除非在作用域 `S` 中搜索 `operator!=` 时，找到一个函数或函数模板，它若改名为 `operator==` 就会与 `F` 对应（[[basic.scope.scope]]）。其中 `S` 是：若 `F` 是类成员，`o` 的类类型的作用域；否则 `F` 所在的命名空间作用域。函数模板特化是否是改写目标，取决于其模板。

!!! std
    "A non-template function or function template F named operator== is a rewrite target with first operand o unless a search for the name operator!= in the scope S … finds a function or function template that would correspond … to F if its name were operator==."

    简单地说，**如果为某个 `operator==` 写了与之配对的 `operator!=`，这个 `operator==` 就不参与反转和改写**。这样的代码显然是按 C++17 的方式写的，编译器也就按 C++17 的方式对待它。

```cpp
struct A {};
template<typename T> bool operator==(A, T);     // #1
bool a1 = 0 == A();                             // OK：调用反转的 #1
template<typename T> bool operator!=(A, T);     // 与 #1 "对应"的 operator!=
bool a2 = 0 == A();                             // error: #1 不再是改写目标，没有可行候选
```

`a1` 处还没有声明 `operator!=`，`#1` 是改写目标，`0 == A()` 用反转的 `#1`（`A() == 0`）。`a2` 处搜索已经能找到配对的 `operator!=`，`#1` 不再是改写目标；而 `int` 与 `A` 之间没有别的 `==`，所以非良构。注意搜索是从运算符表达式的实例化语境进行的，所以同一个 `operator==` 在翻译单元的不同位置，可能是改写目标，也可能不是。

成员函数的情形：

```cpp nocheck
struct B {
  bool operator==(const B&);    // #2（非 const）
};
struct C : B {
  C();
  C(B);
  bool operator!=(const B&);    // #3
};
bool c1 = B() == C();   // OK：调用 #2；在 C 中搜索 operator!= 找到 #3，所以反转的 #2 不是候选
bool c2 = C() == B();   // error: 歧义——在 C 中查找得到的 #2，与在 B 中查找得到的反转 #2
```

这个例子说明了 ¶4 中"`o` 的类类型的作用域"的确切含义。对同一个成员函数 `#2`，判断它是否是以 `C` 对象为第一操作数的改写目标时，要在 `C` 中搜索 `operator!=`（找到 #3，因此不是）；以 `B` 对象为第一操作数时，则在 `B` 中搜索（找不到，因此是）。

- `B() == C()`：反转候选需要以 `C()` 为第一操作数的改写目标，在 `C` 里找到 #3，所以 `#2` 不是改写目标，没有反转候选，只剩 `B().operator==(C())`。
- `C() == B()`：普通候选 `C().operator==(B())`（经派生到基类）；反转候选需要以 `B()` 为第一操作数的改写目标，在 `B` 里找不到 `operator!=`，所以 `#2` 是改写目标，得到反转候选 `B().operator==(C())`。二者各在一个实参上更好，因而歧义。（对第一个实参 `C()`，普通候选把它绑定到隐式对象形参 `B&`，反转候选绑定到 `const B&`，前者 cv 更少而更好；第二个实参 `B()` 恰好相反。）Clang 23 对 `c2` 只给 `-Wambiguous-reversed-operator` 警告并选择普通候选；按标准它是非良构的。

命名空间的情形。注意搜索的是 `F` 所在的命名空间作用域，不包括内联命名空间以外的地方：

```cpp
struct D {};
template<typename T> bool operator==(D, T);     // #4
inline namespace N {
  template<typename T> bool operator!=(D, T);   // #5
}
bool d1 = 0 == D();   // OK：调用反转的 #4；#5 不在 #4 所在的作用域中，不影响 #4 作为改写目标
```

## 赋值、并集与实参列表（¶5–¶8）

¶5 内建赋值运算符的第一个形参只考虑标准转换序列。¶6 其他运算符没有此限制。

¶5 的意义：`x = 1` 中若 `x` 是类类型且可以经转换函数变成 `int&`，内建的 `int& operator=(int&, int)` 也不会选中；否则给类对象赋值，实际上会悄悄修改转换函数返回的某个 `int`。这和隐式对象形参不允许用户定义转换（[[over.best.ics#9]]）是同一个思路。

¶7 候选集是成员、非成员、内建、改写四个候选集的并集。

¶8 实参列表包含运算符的所有操作数。然后按 [[over.match.viable]] 与 [[over.match.best]] 选最佳函数。脚注 96：候选集为空时决议失败。

```cpp
struct A {
  operator int();
};
A operator+(const A&, const A&);
void m() {
  A a, b;
  a + b;     // 选 operator+(a, b)，而不是 int(a) + int(b)
}
```

`operator+(const A&, const A&)` 两个实参都是引用绑定（恒等，Exact Match）；内建 `operator+(int, int)` 两个实参都需要用户定义转换。标准转换序列优于用户定义转换序列（[[over.ics.rank#2.1]]）。

## 改写候选被选中之后（¶9–¶10）

¶9 若对运算符 `@` 选中了改写的 `operator<=>` 候选：

- 若它是反转的合成候选，`x @ y` 解释为 `0 @ (y <=> x)`；
- 否则解释为 `(x <=> y) @ 0`。

在结果表达式的语境中不再考虑改写候选，因此不会无限改写。

¶10 若对运算符 `@` 选中了改写的 `operator==` 候选，其返回类型必须是 `cv bool`，并且：

| `@` | 选中的是 | 解释为 |
|---|---|---|
| `!=` | 反转合成候选 | `!(y == x)` |
| `!=` | 非反转改写候选 | `!(x == y)` |
| `==` | （必然是反转候选） | `y == x` |

之所以限制返回类型，是因为 `!(x == y)` 只对 `bool` 有明确含义。如果 `operator==` 返回表达式模板或其他代理对象（数值库中很常见），自动生成的 `!=` 很可能是错的。所以标准规定返回类型不是 `bool` 时直接非良构，而不是去调用代理对象的 `operator!`。

```cpp nocheck
struct V { int operator==(const V&) const; };
bool f(V v, V w) { return v != w; }   // error: 选中改写的 operator==，但它返回 int
struct Q { int operator==(int) const; };
bool g(Q q) { return 1 == q; }        // error: 选中反转的 operator==，同样要求返回 bool
```

!!! impl "Clang 的偏离"
    截至写作时（Clang 23），上面两处 Clang 只给警告（`-Wrewrite-not-bool`："ISO C++20 requires return type of selected 'operator==' function for rewritten '!=' comparison to be 'bool'"），然后照常编译。按标准它们是非良构的；GCC 会报错。

`<=>` 的例子，同时演示 [[over.match.best#2.8]] 的非改写候选优先规则：

```cpp run ok
#include <compare>
#include <cassert>
struct P {
  int x;
  auto operator<=>(const P&) const = default;   // 也隐式声明了预置的 operator==
};
struct S {
  friend auto operator<=>(const S&, const S&) = default;  // #1
  friend bool operator<(const S&, const S&) { return true; }  // #2
};
int main() {
  P a{1}, b{2};
  assert(a < b);          // (a <=> b) < 0
  assert(b > a);          // (b <=> a) > 0
  assert(a != b);         // !(a == b)，用的是预置的 operator==
  assert(S() < S());      // #2：#1 的改写候选与 #2 同样匹配，非改写者胜出
}
```

## 选中内建候选时（¶11）

¶11 若选中内建候选，类类型操作数转换到所选内建运算的相应形参类型，但不应用用户定义转换序列中的第二个标准转换序列。然后把运算符当作相应的内建运算符，按 [[expr.compound]] 解释。

```cpp
struct X { operator double(); };
struct Y { operator int*(); };
int* a = Y() + 100.0;   // error: 指针算术要求整型操作数
int* b = Y() + X();     // error: 同上
```

`Y() + 100.0`：内建候选 `T* operator+(T*, std::ptrdiff_t)` 可行（`100.0 → ptrdiff_t` 是浮点-整型转换），选中它之后，类类型操作数 `Y()` 转换为 `int*`，但非类操作数 `100.0` 不做任何转换，于是变成内建的 `int* + double`，非良构。`Y() + X()` 中 `X()` 是类类型操作数，按 ¶11 只应用用户定义转换 `operator double()` 本身，不再应用其后的 `double → ptrdiff_t`，结果同样是 `int* + double`。

这条规则看似奇怪，它保证的是：选中内建候选，只是借用它的类型签名来决定怎样转换类对象，真正的运算仍按内建规则，对原始的算术操作数做寻常算术转换等处理。

## `->`、`,`、一元 `&` 的特殊处理（¶12–¶13）

¶12 `operator->` 的第二操作数（成员名）在选择 `operator->` 时不予考虑，也不作为实参。`operator->` 返回后，再对返回值应用 `->` 与原来的第二操作数。脚注 97：如果返回的是类类型，这可能再选择并调用另一个 `operator->`，如此反复，直到返回非类类型。智能指针的逐层转发就是靠这个机制实现的。

```cpp run ok
struct T { int v = 7; };
struct Inner { T t; T* operator->() { return &t; } };
struct Outer { Inner i; Inner& operator->() { return i; } };
int main() {
  Outer o;
  return o->v == 7 ? 0 : 1;   // o.operator->() → Inner&；再 .operator->() → T*；最后内建 ->
}
```

¶13 对 `,`、一元 `&`、`->`，若没有可行函数，就当作内建运算符。（它们的内建候选集是空的，所以需要这条兜底规则。）

```cpp run ok
struct S {
  int operator&(int) const { return 0; }   // 二元 &
};
int main() {
  S s;
  S* p = &s;          // 一元 &：成员候选 operator&(int) 不可行（个数不符），回退到内建取址
  return p == &s ? s & 1 : 1;
}
```

## 兼容性：C++20 的改写候选打破了什么

C++20 的反转候选是一次有意的、经过权衡的不兼容改动。附录 [[diff.cpp17.over]] 列出了两类影响：

**1. 某些调用改选了别的函数，或变成歧义。**当一个类型能转换为另一个类型时会出现这种情况：

```cpp nocheck
struct A {
  operator int() const;
};
bool operator==(A, int);        // #1
// 内建候选：bool operator==(int, int)、bool operator!=(int, int)

int check(A x, A y) {
  return (x == y) +             // 非良构（C++17 良构：内建 int == int）
         (10 == x) +            // 调用反转的 #1（C++17 调用内建 ==）
         (10 != x);             // 调用反转改写的 #1（C++17 调用内建 !=）
}
```

`x == y` 在 C++20 中：普通 `#1`（`x` 精确、`y` 用户定义转换）与反转 `#1`（`y` 精确、`x` 用户定义转换）各赢一个实参，因而歧义；内建 `int == int` 两个实参都是用户定义转换，更差。（Clang 对此只给 `-Wambiguous-reversed-operator` 警告并选择普通候选；按标准是非良构。）

**2. 不对称的成员 `operator==` 变成歧义**：

```cpp nocheck
struct B {
  bool operator==(const B&);    // 忘了 const
};
B b1;
bool eq = (b1 == b1);           // C++20：歧义；C++17：良构
```

普通候选：对象实参 `b1 → B&`（更好），实参 `b1 → const B&`。反转候选：`b1 → const B&`，对象实参 `b1 → B&`（更好）。两者各赢一个。虽然二者有非改写与改写之分，但决胜规则 [[over.match.best#2.8]] 只在所有 ICS 都不更差时才起作用，而这里每个候选都在某个实参上更差，根本到不了决胜规则那一步。

这类代码在实际项目中很普遍（成员 `operator==` 漏写 `const` 是常见错误）。Clang 与 GCC 都把它作为扩展接受并给出警告（Clang 的 `-Wambiguous-reversed-operator`，提示"mark 'operator==' as const or add a matching 'operator!='"）。[[P2468R2]] 则在标准层面给出了解决办法：如果同时声明了配对的 `operator!=`，这个 `operator==` 就不是改写目标，行为退回 C++17。所以 `==` 与 `!=` 成对出现的 C++17 风格代码基本不受影响；只写了 `==` 的代码则适用 C++20 的新语义，无论好坏。

!!! tip "迁移建议"
    - 成员 `operator==` 一律 `const`，参数类型与类类型对称。
    - 只写 `operator==`，不写 `operator!=`（让编译器改写）。
    - 需要排序时写（或 `= default`）`operator<=>`，不要再写 `<`、`<=`、`>`、`>=` 四个函数。
    - 与可隐式转换的类型比较时，留意反转候选带来的歧义；必要时把转换构造函数/转换函数标 `explicit`。

## 实现视角

!!! impl
    - **内建候选不会真的生成成千上万个函数。**[[over.built]] 的候选族在逻辑上是无限的（每个指针类型、每个枚举类型各一套），编译器按操作数类型按需生成可能可行的那几个。Clang 的 `BuiltinCandidateTypeSet` 先收集操作数可转换到的指针/枚举/算术类型，再只为这些类型添加候选。
    - 反转候选的诊断：Clang 会标注"candidate function (with reversed parameter order)"；GCC 标注"(reversed)"。
    - ABI：改写与反转是纯粹的语义变换，不产生任何新符号。调用的仍是原来的 `operator==`/`operator<=>`，只是实参顺序交换，并可能在结果上套 `!` 或 `@ 0`。

## 历史与演进

!!! history
    - **C++98**：成员/非成员/内建三类候选；运算符函数至少一个类或枚举形参；`->` 链式调用；`,`、`&` 与 `->` 无可行函数时回退内建。
    - **C++17**：[[P0145R3]] 规定重载运算符的操作数按内建运算符的顺序定序。
    - **C++20**：[[P0515R3]] 引入 `<=>` 与改写候选；[[P1185R2]] 把 `==` 与 `<=>` 分开（`==` 不再改写为 `<=>`，反之亦然）；¶10 要求改写的 `operator==` 返回 `bool`。
    - **C++23（对 C++20 的缺陷报告）**：[[P2468R2]] 引入改写目标，配对的 `operator!=` 会关闭 `operator==` 的改写与反转。

## 陷阱

!!! pitfall "成员 `operator==` 不是 `const`"
    C++20 下 `a == a` 有歧义（按标准非良构，多数编译器只给警告）。解决办法是加 `const`，或者加一个配对的 `operator!=`。

!!! pitfall "以为 `a != b` 会调用 `operator!=`"
    若只定义了 `operator==`，`a != b` 调用的是 `!(a == b)`。若 `operator==` 返回的不是 `bool`，则非良构。

!!! pitfall "在成员函数里用 `operator+(a, b)` 的函数调用写法"
    函数调用语法走普通非限定查找，全局函数会被同名成员隐藏；而 `a + b` 的非成员候选查找忽略成员。两种写法可能找到不同的函数。

## 思考题

!!! question "1. 只有 `auto operator<=>(const P&) const` 由用户提供（不是 `= default`）时，`a == b` 合法吗？"

<details markdown="1">
<summary>答案</summary>

不合法（除非另有 `operator==`）。`==` 的改写候选只来自 `operator==`（¶3.4.4），不会用 `<=>` 改写；而只有预置的 `operator<=>` 才会隐式声明一个预置的 `operator==`（[[class.compare.default]]）。用户提供的 `<=>` 不会。这正是 [[P1185R2]] 的设计：相等比较可能有比三路比较快得多的实现，不应默默地用 `<=>` 代替。
</details>

!!! question "2. 设 `struct T {};` 并在同一命名空间中声明 `bool operator==(const T&, int);` 与 `bool operator!=(const T&, int);`。`1 == T{}` 合法吗？如果把这两个函数改成 `T` 的隐藏友元呢？"

<details markdown="1">
<summary>答案</summary>

命名空间作用域版本：在 `operator==` 所在的命名空间搜索 `operator!=`，找到一个改名后会与之对应的声明，于是 `operator==` 不是改写目标，`1 == T{}` 没有反转候选，非良构——与 C++17 的行为一致。

隐藏友元版本：¶4 规定的仍是在 `F` 所属的命名空间作用域中搜索，而友元声明不绑定名字（[[basic.scope.scope#2]] 注 1、[[dcl.meaning]]），一次 search 找不到隐藏友元 `operator!=`。于是 `operator==` 仍是改写目标，`1 == T{}` 选中反转候选，良构。Clang 的行为与此一致：

```cpp
struct S {
  friend bool operator==(const S&, int);
  friend bool operator!=(const S&, int);
};
bool x1 = 1 == S{};        // OK：隐藏友元 operator!= 不能被 search 找到
struct T {};
bool operator==(const T&, int);
bool operator!=(const T&, int);
bool x2 = 1 == T{};        // error: operator== 不是改写目标
```

这是改写目标规则中一个不太直观的地方：用隐藏友元成对声明 `==`/`!=` 并不能关掉反转。
</details>

## 小结

!!! summary
    - 没有类/枚举操作数时直接用内建运算符，不做决议。
    - 四类候选：成员（只看左操作数）、非成员（非限定查找 + ADL，忽略成员）、内建（[[over.built]]，剔除与非模板非成员候选同签名者）、改写（C++20）。
    - 改写规则：`<`/`<=`/`>`/`>=` → `<=>`（含反转）；`<=>` → 反转；`!=` → `==`（含反转）；`==` → 反转。`==` 与 `<=>` 互不改写。
    - 写了配对 `operator!=` 的 `operator==` 不是改写目标（P2468）。
    - 选中改写的 `operator==` 时返回类型必须是 `bool`。
    - 平局时：非改写候选优于改写候选，非反转优于反转（[[over.match.best#2.8]]、[[over.match.best#2.9]]）。
