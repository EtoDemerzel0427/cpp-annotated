---
title: 表达式中的运算符
summary: 有类或枚举操作数的运算符表达式怎样变成一次重载决议：成员、非成员、内建、改写四类候选，C++20 用 operator== 和 operator<=> 改写比较运算，以及配对的 operator!= 怎样关掉这种改写。
status: done
since: c++98
papers: P0515R3, P1185R2, P2468R2, P0145R3
related: over.match, over.match.best, over.built, over.oper, expr.eq, expr.rel, expr.spaceship, class.compare.default
tags: 重载决议, 运算符, 比较
updated: 2026-10-19
---

!!! tldr
    - 操作数都不是类或枚举类型时，运算符一定是内建的，不做重载决议。
    - 否则候选有四类：左操作数的成员函数、按非成员方式查找到的函数、假想的内建运算符函数，以及 C++20 起的改写候选。
    - C++20 起，`a != b` 可以用 `operator==` 实现，`a < b` 可以用 `operator<=>` 实现，两种都可以交换操作数。`==` 和 `<=>` 互不改写。
    - 如果为一个 `operator==` 写了配对的 `operator!=`，这个 `operator==` 就不参与改写和交换，行为退回 C++17。
    - 重载运算符的操作数按内建运算符的顺序求值，`std::cout << f() << g()` 保证先求值 `f()`。

```cpp run ok
#include <cassert>
struct S {
  int v;
  bool operator==(int i) const { return v == i; }
};
int main() {
  S s{1};
  assert(s == 1);       // 直接调用 S::operator==
  assert(1 == s);       // C++20：交换操作数，解释为 s == 1
  assert(!(s != 1));    // C++20：改写，解释为 !(s == 1)
  assert(!(1 != s));    // C++20：交换加改写，解释为 !(s == 1)
}
```

只写了一个 `operator==`，四种写法都能用。在 C++17 中，这需要写四个函数。只要一个操作数是类或枚举类型，运算符表达式就要做一次重载决议，候选来自四个方面。

## 内建类型之间不做重载决议（¶1）

¶1 如果运算符的操作数都既不是类类型也不是枚举类型，就认定它是内建运算符，按 [[expr.compound]] 解释，既不查找运算符函数，也不做重载决议。

```cpp error
struct String {
  String(const String&);
  String(const char*);
  operator const char*();
};
String operator+(const String&, const String&);

void f() {
  const char* p = "one" + "two";   // error: 两个指针不能相加，operator+ 根本不会被考虑
  int i = 1 + 1;                   // 永远是 2
}
```

[[over.oper]] 还要求运算符函数至少有一个类或枚举类型的形参。两条规则合起来，保证了用户代码无法改变内建类型上运算的含义。

注 1 提醒，`.`、`.*`、`::` 不能重载，总是内建的。`?:` 也不能重载，但第二、三操作数是类或枚举类型时，[[expr.cond]] 借用本节的规则决定怎样转换它们。

## 运算符写法变成函数调用（¶2）

¶2 只要有一个操作数是类或枚举类型，就可能存在实现这个运算符的用户定义函数，或者需要一次用户定义转换把操作数变成内建运算符接受的类型。为了在两者之间做决议，先把运算符写法变换成等价的函数调用写法：

| 运算符 | 表达式 | 成员函数形式 | 非成员函数形式 |
|---|---|---|---|
| 一元（[[over.unary]]） | `@a` | `(a).operator@()` | `operator@(a)` |
| 二元（[[over.binary]]） | `a@b` | `(a).operator@(b)` | `operator@(a, b)` |
| 赋值（[[over.assign]]） | `a=b` | `(a).operator=(b)` | 无 |
| 下标（[[over.sub]]） | `a[b]` | `(a).operator[](b)` | 无 |
| 成员访问（[[over.ref]]） | `a->` | `(a).operator->()` | 无 |
| 后缀自增自减（[[over.inc]]） | `a@` | `(a).operator@(0)` | `operator@(a, 0)` |

!!! std
    "However, the operands are sequenced in the order prescribed for the built-in operator."

    但操作数的定序遵循内建运算符的规定。

这句话由 C++17 的 [[P0145R3]] 加入。所以即使调用的是重载的 `operator<<`，`std::cout << f() << g()` 也保证 `f()` 先于 `g()` 求值；`a = b` 中 `b` 先于 `a` 定序。C++14 及以前，重载运算符按普通函数调用对待，实参的求值顺序未指定。

## 四类候选（¶3）

¶3 设一元运算符 `@` 的操作数类型是 `cv1 T1`，二元运算符 `@` 的左操作数类型是 `cv1 T1`、右操作数类型是 `cv2 T2`。候选分四类：**成员候选**、**非成员候选**、**内建候选**和**改写候选**。

### 成员候选（¶3.1）

¶3.1 如果 `T1` 是完整的类类型或正在定义的类，成员候选就是在 `T1` 的作用域里查找 `operator@` 的结果；否则为空。

成员候选只看左操作数，`1 + x` 不会考虑 `x` 的成员 `operator+`。所以对称的二元运算符传统上写成非成员函数或隐藏友元。

### 非成员候选（¶3.2）

¶3.2 对 `=`、`[]`、`->`，非成员候选为空，这几个运算符只能重载为成员函数。对其他运算符，非成员候选是对 `operator@` 做非限定查找（[[basic.lookup.unqual]]）和实参依赖查找（[[basic.lookup.argdep]]）的结果，**忽略所有成员函数**。

忽略成员函数，使运算符表达式与写成函数调用的形式行为不同（¶14 的注 3）：

```cpp error
struct A {};
void operator+(A, A);

struct B {
  void operator+(B);
  void f();
};
A a;
void B::f() {
  a + a;             // OK：非成员查找忽略成员，找到全局的 operator+
  operator+(a, a);   // error: 普通的非限定查找先在 B 中找到 B::operator+，全局的被隐藏
}
```

¶3.2 还有一条限制：如果没有操作数是类类型（只有枚举），那么只有第一个形参是 `T1`（或到 `cv T1` 的引用）、或第二个形参是 `T2`（或其引用）的非成员函数才是候选。换句话说，只有专门为这个枚举写的运算符，才会用于这个枚举，借助某个类的转换构造函数不行：

```cpp error
enum class E { a };
struct S { S(E) {} };
int operator+(S, S) { return 42; }
int x = operator+(E::a, E::a);   // OK：函数调用写法，经 S(E) 转换
int y = E::a + E::a;             // error: operator+(S, S) 的形参不是 E，不是候选
```

### 内建候选（¶3.3）

[[over.built]] 列出了一族假想的函数，代表内建运算符，例如对每对提升后的算术类型 `L`、`R` 有 `operator+(L, R)`，对每个枚举类型 `T` 有 `bool operator==(T, T)`。有了它们，内建运算符就能和用户定义的运算符放在一起比较，例如类类型的操作数经转换函数变成 `int` 后使用内建 `+`。

¶3.3 对 `,`、一元 `&` 和 `->`，内建候选为空。对其他运算符，内建候选是 [[over.built]] 中满足以下条件的那些函数：

- ¶3.3.1 运算符名字相同；
- ¶3.3.2 操作数个数相同；
- ¶3.3.3 给定的操作数能按 [[over.best.ics]] 转换到它的形参类型；
- ¶3.3.4 形参类型列表与任何非模板的非成员候选（包括改写出的非成员候选）都不相同。

¶3.3.4 避免了用户为枚举定义的运算符与同签名的内建候选打成平局：

```cpp run ok
enum class Color { red };
bool operator==(Color, Color) { return false; }   // 与内建的 bool operator==(Color, Color) 同签名
int main() {
  return Color::red == Color::red;   // 返回 0：内建候选被剔除，调用用户版本
}
```

### 改写候选（¶3.4）{{c++20}}

¶3.4 改写候选让比较运算符可以由 `operator==` 或 `operator<=>` 实现：

| 表达式 | 改写候选 |
|---|---|
| `x < y`、`x <= y`、`x > y`、`x >= y` | `x <=> y` 的所有非改写候选；`y <=> x` 的每个非改写候选交换形参顺序后合成的候选 |
| `x <=> y` | `y <=> x` 的每个非改写候选交换形参顺序后合成的候选 |
| `x != y` | `x == y` 的非改写候选中，以 `x` 为第一操作数的改写目标；`y == x` 中以 `y` 为第一操作数的改写目标交换后合成的候选 |
| `x == y` | `y == x` 中以 `y` 为第一操作数的改写目标交换后合成的候选 |
| 其他运算符 | 无 |

改写目标的含义见下文 ¶4，大致是没有配对 `operator!=` 的 `operator==`。

这里有两点设计：

- `==` 不会改写成 `<=>`。最初的 [[P0515R3]] 允许用 `<=>` 实现 `==`，但 `std::vector`、`std::string` 这类类型比较相等时可以先比长度，长度不同就立即得出结果，用 `<=>` 实现会付出不必要的代价。[[P1185R2]] 于是把相等与排序分开：`==`、`!=` 只用 `operator==` 改写，`<`、`<=`、`>`、`>=`、`<=>` 只用 `operator<=>` 改写。
- 改写只以非改写候选为原料，不会递归改写。

注 2：由成员候选交换得到的候选，对象形参变成了第二个形参，所以第一个形参上可以做隐式转换，第二个形参上不能做用户定义转换。

## 选中改写候选之后（¶9–¶10）

¶9 如果为运算符 `@` 选中了改写的 `operator<=>` 候选，交换过的候选把 `x @ y` 解释为 `0 @ (y <=> x)`，否则解释为 `(x <=> y) @ 0`。解释出的表达式里不再考虑改写候选，所以不会无限改写下去。

¶10 如果为运算符 `@` 选中了改写的 `operator==` 候选，它的返回类型必须是 `cv bool`，并且：

| `@` | 选中的候选 | 解释为 |
|---|---|---|
| `!=` | 交换过的 | `!(y == x)` |
| `!=` | 没交换的 | `!(x == y)` |
| `==` | 必然是交换过的 | `y == x` |

返回类型要求是 `bool`，因为 `!(x == y)` 只对 `bool` 有明确的含义。数值库里的 `operator==` 常常返回表达式模板之类的代理对象，自动生成的 `!=` 对它们很可能是错的。所以返回类型不是 `bool` 时程序直接非良构，而不是去调用代理对象的 `operator!`。

```cpp error
struct V { int operator==(const V&) const; };
bool f(V v, V w) { return v != w; }   // error: 选中改写的 operator==，但它返回 int
struct Q { int operator==(int) const; };
bool g(Q q) { return 1 == q; }        // error: 选中交换过的 operator==，同样要求返回 bool
```

!!! impl "Clang 的偏离"
    本机 Clang 23 对这两处只给出 `-Wrewrite-not-bool` 警告，然后照常编译。按标准它们是非良构的。

`<=>` 的例子，同时演示了非改写候选优先的决胜规则（[[over.match.best#2.8]]）：

```cpp run ok
#include <compare>
#include <cassert>
struct P {
  int x;
  auto operator<=>(const P&) const = default;   // 同时隐式声明了预置的 operator==
};
struct S {
  friend auto operator<=>(const S&, const S&) = default;       // #1
  friend bool operator<(const S&, const S&) { return true; }   // #2
};
int main() {
  P a{1}, b{2};
  assert(a < b);       // (a <=> b) < 0
  assert(b > a);       // (b <=> a) > 0
  assert(a != b);      // !(a == b)，用的是预置的 operator==
  assert(S() < S());   // #2：#1 的改写候选与 #2 同样好，非改写的胜出
}
```

## 配对的 operator!= 关闭改写（¶4）

C++20 的交换候选让一批旧代码有了歧义（见下文的兼容性一节）。受影响最多的是 C++17 风格的代码：`operator==` 和 `operator!=` 都写了，但签名不对称，比如成员函数忘了 `const`。[[P2468R2]] 作为对 C++20 的缺陷报告，引入了**改写目标**（[[g:rewrite-target|rewrite target]]）的概念来处理这个问题。

¶4 名为 `operator==` 的函数或函数模板 `F`，是以 `o` 为第一操作数的改写目标，除非在作用域 `S` 中查找 `operator!=` 能找到一个函数，它如果改名为 `operator==` 就会与 `F` 对应（[[basic.scope.scope]]），即形参相同、是同一个函数的重新声明。如果 `F` 是类成员，`S` 是 `o` 的类的作用域；否则 `S` 是 `F` 所在的命名空间作用域。

简单地说，为某个 `operator==` 写了配对的 `operator!=`，这个 `operator==` 就不参与交换和改写。这样的代码显然是按 C++17 的方式写的，编译器也按 C++17 的方式对待它。

```cpp error
struct A {};
template<typename T> bool operator==(A, T);   // #1
bool a1 = 0 == A();                           // OK：调用交换过的 #1
template<typename T> bool operator!=(A, T);   // 与 #1 配对
bool a2 = 0 == A();                           // error: #1 不再是改写目标，没有可行的候选
```

查找从运算符表达式的实例化语境进行，所以同一个 `operator==` 在翻译单元的不同位置，可能是改写目标，也可能不是。

成员函数的情形说明了 `o` 的类的作用域是什么意思：

```cpp
struct B {
  bool operator==(const B&);    // #2，非 const
};
struct C : B {
  C();
  C(B);
  bool operator!=(const B&);    // #3
};
bool c1 = B() == C();   // OK：调用 #2
bool c2 = C() == B();   // error: 歧义
```

对同一个 #2，判断它是否是以某个对象为第一操作数的改写目标时，查找的作用域随那个对象的类而变：

- `B() == C()`：交换候选要求 #2 是以 `C()` 为第一操作数的改写目标。在 `C` 中查找 `operator!=` 找到了 #3，所以不是，没有交换候选，只剩 `B().operator==(C())`。
- `C() == B()`：普通候选是 `C().operator==(B())`。交换候选要求 #2 是以 `B()` 为第一操作数的改写目标，在 `B` 中找不到 `operator!=`，所以是，得到交换候选 `B().operator==(C())`。普通候选把 `C()` 绑定到隐式对象形参 `B&`，交换候选把它绑定到 `const B&`，前者 cv 限定更少，更好；第二个实参 `B()` 恰好相反。两者各赢一个实参，因而歧义。

本机 Clang 23 对 `c2` 只给出 `-Wambiguous-reversed-operator` 警告并选择普通候选。按标准它是非良构的。

命名空间的情形，查找的只是 `F` 所在的那个命名空间作用域：

```cpp run ok
struct D {};
template<typename T> bool operator==(D, T) { return true; }   // #4
inline namespace N {
  template<typename T> bool operator!=(D, T);                 // #5
}
int main() {
  return 0 == D() ? 0 : 1;   // 调用交换过的 #4：#5 不在 #4 所在的作用域里
}
```

## 候选的并集与实参（¶5–¶8）

¶5 内建赋值运算符的第一个形参只考虑标准转换序列。¶6 其他运算符没有这个限制。

¶5 的意义在于，`x = 1` 中即使类对象 `x` 能经转换函数变成 `int&`，也不会选中内建的 `int& operator=(int&, int)`；否则给类对象赋值，实际上会修改转换函数返回的某个 `int`。这和隐式对象形参上不做用户定义转换（[[over.best.ics#9]]）是同一个思路。

¶7 候选集是成员、非成员、内建、改写四类候选的并集。¶8 实参列表包含运算符的全部操作数，然后按 [[over.match.viable]] 和 [[over.match.best]] 选出最佳函数。候选集为空时决议失败（脚注 96）。

```cpp
struct A {
  operator int();
};
A operator+(const A&, const A&);
void m() {
  A a, b;
  a + b;   // 选 operator+(a, b)，而不是 int(a) + int(b)
}
```

`operator+(const A&, const A&)` 的两个实参都是引用直接绑定，属于精确匹配。内建的 `operator+(int, int)` 两个实参都要经过用户定义转换。标准转换序列优于用户定义转换序列（[[over.ics.rank#2.1]]）。

## 选中内建候选之后（¶11）

¶11 如果选中的是内建候选，类类型的操作数转换到所选内建运算对应形参的类型，但用户定义转换序列中的第二个标准转换序列不做。然后把运算符当作内建运算符，按 [[expr.compound]] 解释。

```cpp error
struct X { operator double(); };
struct Y { operator int*(); };
int* a = Y() + 100.0;   // error: 指针算术要求整型操作数
int* b = Y() + X();     // error: 同上
```

`Y() + 100.0` 中，内建候选 `T* operator+(T*, std::ptrdiff_t)` 可行，因为 `100.0` 能转换成 `ptrdiff_t`。选中之后只转换类类型的操作数 `Y()`，变成 `int*`；`100.0` 不是类类型，不做转换，于是表达式成了内建的 `int* + double`，非良构。`Y() + X()` 中，`X()` 只经过转换函数 `operator double()`，后面的 `double` 到 `ptrdiff_t` 不做，结果同样是 `int* + double`。

选中内建候选只是借用它的签名决定怎样转换类对象，真正的运算仍然按内建规则进行。

## `->`、`,` 与一元 `&`（¶12–¶13）

¶12 选择 `operator->` 时不考虑 `->` 右边的成员名，它也不作为实参。`operator->` 返回之后，再对返回值应用 `->` 和原来的成员名。如果返回的仍是类类型，就再选择并调用一次 `operator->`，直到返回非类类型为止（脚注 97）。智能指针的逐层转发就是这样实现的：

```cpp run ok
struct T { int v = 7; };
struct Inner { T t; T* operator->() { return &t; } };
struct Outer { Inner i; Inner& operator->() { return i; } };
int main() {
  Outer o;
  return o->v == 7 ? 0 : 1;   // Outer::operator-> 得到 Inner&，Inner::operator-> 得到 T*，最后是内建 ->
}
```

¶13 对 `,`、一元 `&` 和 `->`，如果没有可行函数，就当作内建运算符。它们的内建候选为空，所以需要这条规则兜底。

```cpp run ok
struct S {
  int operator&(int) const { return 0; }   // 二元 &
};
int main() {
  S s;
  S* p = &s;   // 一元 &：成员 operator&(int) 个数不符，不可行，退回内建取地址
  return p == &s ? s & 1 : 1;
}
```

## C++20 带来的不兼容

交换候选是一次有意的不兼容改动，附录 [[diff.cpp17.over]] 列出了它的影响。第一类是某些调用改选了别的函数，或者变成歧义，常见于一个类型能隐式转换成另一个类型时：

```cpp
struct A {
  operator int() const;
};
bool operator==(A, int);   // #1
// 内建候选：bool operator==(int, int)、bool operator!=(int, int)

int check(A x, A y) {
  return (x == y) +        // C++20 非良构（C++17 调用内建的 int == int）
         (10 == x) +       // 调用交换过的 #1（C++17 调用内建的 ==）
         (10 != x);        // 调用交换并改写的 #1（C++17 调用内建的 !=）
}
```

`x == y` 中，普通的 #1（`x` 精确匹配，`y` 用户定义转换）与交换过的 #1（`y` 精确匹配，`x` 用户定义转换）各赢一个实参，因而歧义。内建的 `int == int` 两个实参都要用户定义转换，更差。本机 Clang 23 对此只给出 `-Wambiguous-reversed-operator` 警告并选择普通候选。

第二类是不对称的成员 `operator==`：

```cpp
struct B {
  bool operator==(const B&);   // 忘了 const
};
B b1;
bool eq = (b1 == b1);          // C++20 有歧义，C++17 良构
```

普通候选的对象实参绑定到 `B&`，另一个实参绑定到 `const B&`；交换候选正好相反。两者各在一个实参上更好。虽然一个是改写候选、一个不是，但非改写者优先的规则（[[over.match.best#2.8]]）只在所有转换序列都不更差时才适用，这里用不上。

漏写 `const` 的成员 `operator==` 在实际项目中很常见。Clang 把它作为扩展接受，给出 `-Wambiguous-reversed-operator` 警告。[[P2468R2]] 在标准层面给出了解决办法：同时声明配对的 `operator!=`，`operator==` 就不是改写目标，行为退回 C++17。`==` 和 `!=` 成对出现的旧代码因此基本不受影响；只写了 `==` 的代码适用 C++20 的新语义。

!!! tip "迁移建议"
    - 成员 `operator==` 一律加 `const`，形参类型与类类型对称。
    - 只写 `operator==`，不写 `operator!=`，让编译器改写。
    - 需要排序时写 `operator<=>`（或 `= default`），不再写 `<`、`<=`、`>`、`>=` 四个函数。
    - 与能隐式转换的类型比较时，留意交换候选带来的歧义，必要时把转换构造函数或转换函数标成 `explicit`。

## 实现视角

!!! impl
    - [[over.built]] 的候选族在逻辑上是无限的（每个指针类型、每个枚举类型各一套）。编译器按操作数类型只生成可能可行的那几个。
    - Clang 的诊断把交换候选标注为 candidate function (with reversed parameter order)。
    - 改写和交换是纯粹的语义变换，不产生新符号。调用的仍是原来的 `operator==` 或 `operator<=>`，只是实参顺序交换，结果外面可能套一层 `!` 或 `@ 0`。

## 历史与演进

!!! history
    - C++98 已有成员、非成员、内建三类候选，`->` 的链式调用，以及 `,`、`&`、`->` 无可行函数时退回内建的规则。
    - C++17：[[P0145R3]] 规定重载运算符的操作数按内建运算符的顺序定序。
    - C++20：[[P0515R3]] 引入 `<=>` 和改写候选；[[P1185R2]] 把 `==` 与 `<=>` 分开，并要求改写的 `operator==` 返回 `bool`。
    - [[P2468R2]] 作为对 C++20 的缺陷报告引入改写目标，配对的 `operator!=` 关闭 `operator==` 的改写与交换。

## 常见误解

!!! pitfall "`a != b` 一定调用 `operator!=`"
    如果只定义了 `operator==`，`a != b` 调用的是 `!(a == b)`。这时 `operator==` 的返回类型必须是 `bool`。

!!! pitfall "成员函数里写 `operator+(a, b)` 和写 `a + b` 等价"
    函数调用写法走普通的非限定查找，全局函数会被同名成员隐藏；`a + b` 的非成员候选查找忽略成员。两种写法可能找到不同的函数。

## 思考题

!!! question "思考题 1"
    只有用户提供的 `auto operator<=>(const P&) const`（不是 `= default`）时，`a == b` 合法吗？

<details markdown="1">
<summary>答案</summary>

不合法，除非另有 `operator==`。`==` 的改写候选只来自 `operator==`（¶3.4.4），不会用 `<=>` 改写。只有预置的 `operator<=>` 才会隐式声明一个预置的 `operator==`（[[class.compare.default]]），用户提供的不会。这正是 [[P1185R2]] 的设计：相等比较可能有比三路比较快得多的实现，不应默默地用 `<=>` 代替。
</details>

!!! question "思考题 2"
    在同一命名空间中声明 `struct T {};`、`bool operator==(const T&, int);` 和 `bool operator!=(const T&, int);`，`1 == T{}` 合法吗？如果把这两个函数改成 `T` 的隐藏友元呢？

<details markdown="1">
<summary>答案</summary>

命名空间里的版本：在 `operator==` 所在的命名空间中查找 `operator!=`，找到了配对的声明，所以 `operator==` 不是改写目标，`1 == T{}` 没有交换候选，非良构，与 C++17 一致。

隐藏友元的版本：¶4 仍然在 `F` 所在的命名空间作用域中查找，但友元声明不绑定名字（[[basic.scope.scope#2.9]]），这次查找找不到隐藏友元 `operator!=`。于是 `operator==` 仍是改写目标，`1 == T{}` 选中交换候选，良构。本机 Clang 23 与此一致：

```cpp error
struct S {
  friend bool operator==(const S&, int);
  friend bool operator!=(const S&, int);
};
bool x1 = 1 == S{};   // OK：隐藏友元 operator!= 查找不到
struct T {};
bool operator==(const T&, int);
bool operator!=(const T&, int);
bool x2 = 1 == T{};   // error: operator== 不是改写目标
```

用隐藏友元成对声明 `==` 和 `!=`，并不能关掉交换。
</details>
