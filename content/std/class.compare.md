---
title: 比较
summary: C++20 的 = default 比较运算符：哪些声明可以预置，== 和 <=> 怎样逐个子对象比较，auto <=> 的返回类型怎样推导，只有 == 和 < 的旧类型怎样参与三路比较，以及什么时候预置的比较被定义为删除。
status: done
since: c++20
covers: class.compare.default, class.eq, class.spaceship, class.compare.secondary
papers: P0515R3, P1185R2, P1186R3, P2002R1, P2468R2
related: over.match.oper, over.match.best, expr.spaceship, expr.eq, expr.rel, cmp.categories, dcl.fct.def.default, over.binary
tags: 比较, 三路比较, operator<=>, 预置函数, C++20
updated: 2026-10-19
---

!!! tldr
    - 写一个 `auto operator<=>(const T&) const = default;`，就得到全部六个比较运算符：`==` 被隐式声明，`<`、`!=` 等由改写候选得到。
    - 预置的 `==` 和 `<=>` 按基类、成员的声明顺序逐个比较，数组逐元素展开；`==` 遇到第一个不等就返回 `false`，`<=>` 返回第一个非等于的结果。
    - `auto <=>` 的返回类型是各成员结果中最弱的比较类别；写出具体类别（如 `std::weak_ordering`）时，只有 `==` 和 `<` 的旧类型成员也能参与比较。
    - 只有预置的 `<=>` 才会隐式声明 `==`，而且只在类里没有任何名为 `operator==` 的声明时；`==` 从不改写成 `<=>`。
    - 有引用成员、联合体成员，或某个成员无法比较时，预置的比较被定义为删除，而不是报错。

## 写两个函数，得到六个运算符

```cpp run title="overview.cpp" ok
#include <compare>
#include <string>

struct Point {
  int x;
  int y;
  auto operator<=>(const Point&) const = default;
  // 同时隐式声明 bool operator==(const Point&) const = default;
};

struct Person {
  std::string name;
  int age;
  bool operator==(const Person&) const = default;   // 只要相等比较
};

int main() {
  Point a{1, 2}, b{1, 3};
  bool r1 = a < b;     // (a <=> b) < 0：x 相等，再比 y，2 < 3
  bool r2 = a != b;    // !(a == b)
  bool r3 = a >= b;    // (a <=> b) >= 0
  Person p{"Ann", 30}, q{"Ann", 30};
  bool r4 = p == q;    // 逐成员 ==
  bool r5 = p != q;    // !(p == q)
  // bool r6 = p < q;  // error: Person 没有 <=>
  return (r1 && r2 && !r3 && r4 && !r5) ? 0 : 1;
}
```

C++20 之前，一个类要支持全部比较，得手写 `==`、`!=`、`<`、`>`、`<=`、`>=` 六个函数，并自己保证它们一致。C++20 用两个机制解决这个问题。

第一个是**改写候选**（[[g:rewritten-candidate|rewritten candidates]]，[[over.match.oper]]）：编译器为 `a < b` 做重载决议时，也考虑把它解释成 `(a <=> b) < 0` 或 `0 < (b <=> a)`；`a != b` 可以解释成 `!(a == b)`；`a == b` 还可以把操作数对调成 `b == a`。于是只要有 `==` 和 `<=>`，六个运算符都能用，操作数顺序也可以对调。

第二个是本页的**预置比较**：`==` 和 `<=>` 本身可以写成 `= default`，由编译器逐个成员比较。`<=>` 的结果类型是三种**比较类别**之一：`std::strong_ordering`、`std::weak_ordering`、`std::partial_ordering`，后者允许无序的结果，例如 NaN（[[cmp.categories]]、[[expr.spaceship]]）。

## 哪些声明可以预置 [class.compare.default]

¶1 预置的比较运算符函数必须是非模板函数，并且：

- ¶1.1 是某个类 `C` 的非静态成员或友元；
- ¶1.2 在 `C` 里定义为预置，或者在 `C` 已经完整的地方定义为预置；
- ¶1.3 有两个 `const C&` 形参，或者两个 `C` 形参。成员函数的隐式对象形参算作第一个形参。

满足这些条件的叫作 `C` 的**预置比较运算符函数**（[[g:defaulted-comparison-operator-function|defaulted comparison operator function]]）。它的隐式定义在相当于函数体的语境中做名字查找和访问检查，所以能访问 `C` 的私有成员。在类里定义为预置的比较运算符必须是该函数的第一个声明。

<div class="compare" markdown="1">

```cpp run ok
#include <compare>
struct A { int x;
  bool operator==(const A&) const
    = default; };
struct B { int x;
  friend bool operator==(const B&,
    const B&) = default; };
struct C { int x;
  friend auto operator<=>(C, C)
    = default; };       // 按值
struct D { int x;
  bool operator==(this D, D)
    = default; };       // 显式对象形参
struct G { int x;
  bool operator==(const G&) const; };
bool G::operator==(const G&) const
  = default;            // 类外预置
int main() {
  static_assert(A{1} == A{1});
  static_assert(C{1} < C{2});
  static_assert(D{1} == D{1});
  return G{1} == G{1} ? 0 : 1;
}
```

```cpp error
#include <compare>
struct M1 { int x;
  bool operator==(const M1&)
    = default; };
// error: 隐式对象形参是 M1&
struct M2 { int x;
  bool operator==(M2) const
    = default; };
// error: const M2& 与 M2 不同
struct S2 {
  friend bool operator==(S2,
    const S2&) = default; };
// error: 两个形参类型不同
enum E {};
bool operator==(E, E) = default;
// error: 不是类的成员或友元
```

</div>

因为隐式对象形参算第一个形参，成员形式只能写成 `bool operator==(const C&) const`，漏了 `const` 就不合格。想让两个形参都按值传递，可以用友元，或者 C++23 的显式对象形参。

类外预置（`G`）可以把比较的定义放进 `.cpp` 文件，头文件里只留声明。

### 何时被定义为删除（¶2、¶3）

¶2 如果 `C` 有引用类型的非静态数据成员，或者有变体成员（即 `C` 是联合体或含匿名联合体，[[class.union.anon]]），`C` 的预置 `<=>` 和 `==` 被定义为删除。

```cpp title="deleted-cases.cpp" error
struct Ref {
  int& r;
  bool operator==(const Ref&) const = default;   // 被定义为删除
};

struct HasUnion {
  union { int i; float f; };
  bool operator==(const HasUnion&) const = default;   // 被定义为删除
};

bool f(Ref a, Ref b) { return a == b; }   // error: 使用了被删除的函数
```

引用成员的比较有两种同样合理的含义：比较引用到的值，或比较是否绑定到同一个对象。标准不替程序员选。联合体则无法知道哪个成员是活跃的。Clang 对这两个声明都给出 `-Wdefaulted-function-deleted` 警告。

其他删除条件都依赖第 3 段定义的**可用**（[[g:usable-comparison|usable]]）：二元表达式 `a @ b` 是可用的，如果

- ¶3.1 `a` 或 `b` 是类或枚举类型，并且对 `a @ b` 的重载决议得到一个可用候选，即选中的函数未被删除且可访问（[[over.match.general#4]]）；或者
- ¶3.2 `a` 和 `b` 都不是类或枚举类型，并且 `a @ b` 是合法的表达式。

能否比较完全交给普通的重载决议判断，包括改写候选。所以对一个只定义了 `<=>` 的成员类型，`x == x` 不可用（`==` 不会改写成 `<=>`），`x < x` 却是可用的。

### 隐式声明的 `==`（¶4）

¶4 如果类的成员说明里没有显式声明任何名为 `operator==` 的成员或友元，那么对其中每个定义为预置的三路比较运算符，都隐式声明一个 `operator==`：访问权限、定义方式、所在的类作用域都与那个 `<=>` 相同，只是返回类型换成 `bool`，名字换成 `operator==`。

注 1 补充：隐式的 `==` 在类定义里定义为预置，形参和尾随 *requires-clause* 与 `<=>` 相同；`<=>` 是 `friend`、`virtual`、`constexpr`、`consteval` 的，`==` 也是。如果 `<=>` 没有 *noexcept-specifier*，`==` 有自己的隐式异常说明，两者可能不同。注 2：即使 `<=>` 被定义为删除，`==` 照样被隐式声明，是否删除另行判断。

标准例 2 展示了隐式声明的样子：

```cpp run title="implicit-eq.cpp" ok
#include <compare>

template<typename T> struct X {
  friend constexpr std::partial_ordering operator<=>(X, X)
      requires (sizeof(T) != 1) = default;
  // 隐式声明：friend constexpr bool operator==(X, X)
  //               requires (sizeof(T) != 1) = default;

  [[nodiscard]] virtual std::strong_ordering operator<=>(const X&) const = default;
  // 隐式声明：[[nodiscard]] virtual bool operator==(const X&) const = default;
};

int main() {
  X<char> a, b;      // 友元的约束不满足，只剩成员版本
  (void)(a <=> b);
  (void)(a == b);    // 隐式声明的成员 ==
}
```

这个例子只用来演示声明。换成 `X<int>`，按值的友元和 `const&` 的成员对左值实参匹配得一样好，本机 Clang 报告 `a <=> b` 和 `a == b` 都有歧义。

为什么 `<=>` 不直接兼任 `==`？C++20 最初的设计（[[P0515R3]]）确实允许把 `a == b` 改写成 `(a <=> b) == 0`。后来 [[P1185R2]] 指出这有性能问题：`std::vector`、`std::string` 的 `==` 可以先比较长度，长度不同立即返回；`<=>` 却必须按字典序逐元素比较才能给出大小。如果 `==` 一律经由 `<=>` 实现，所有逐成员比较的类都会悄悄变慢。所以现在 `==` 从不改写成 `<=>`，预置的 `<=>` 另外隐式声明一个逐成员调用 `==` 的预置 `==`。

第 4 段的条件是没有任何名为 `operator==` 的声明。只要自己写了一个，哪怕形参类型完全不同，隐式的 `==` 就不会出现：

```cpp title="no-implicit-eq.cpp" error
#include <compare>

struct U {
  int x;
  std::strong_ordering operator<=>(const U& o) const { return x <=> o.x; }   // 手写，不是预置
};

struct V {
  int x;
  auto operator<=>(const V&) const = default;
  bool operator==(int) const;   // 显式声明了一个 operator==
};

bool t1(U a, U b) { return a < b; }    // OK: (a <=> b) < 0
bool t2(U a, U b) { return a == b; }   // error: 手写的 <=> 不会隐式声明 ==
bool t3(V a, V b) { return a == b; }   // error: 已有 operator==(int)，不再隐式声明 V == V
```

### 展开的子对象列表（¶5）

¶5 预置比较按对象 `x` 的**展开的子对象列表**（[[g:expanded-list-of-subobjects|expanded list of subobjects]]）逐个比较：

1. 先是 `C` 的直接基类子对象，按基类列表中的声明顺序；
2. 然后是 `C` 的非静态数据成员，按声明顺序；
3. 数组类型的子对象递归展开为各个元素，下标从小到大。

列表的第 *i* 个元素记作 x<sub>i</sub>。只列直接基类，基类自己的成员由基类的比较运算符负责；静态数据成员不在列表里。基类排在成员前面，与构造顺序一致。

```cpp run title="subobject-order.cpp" ok
#include <compare>
#include <cstdio>

struct Loud {
  int v;
  bool operator==(const Loud& o) const {
    std::printf("==%d ", v); return v == o.v;
  }
  std::strong_ordering operator<=>(const Loud& o) const {
    std::printf("<=>%d ", v); return v <=> o.v;
  }
};

struct B { Loud b; auto operator<=>(const B&) const = default; };
struct D : B {
  Loud m1, m2;
  auto operator<=>(const D&) const = default;
};

int main() {
  D x{{{0}}, {1}, {2}}, y{{{0}}, {9}, {2}};
  bool e = x == y;  std::printf("-> %d\n", e);   // ==0 ==1 -> 0
  bool l = x < y;   std::printf("-> %d\n", l);   // <=>0 <=>1 -> 1
  bool n = x != y;  std::printf("-> %d\n", n);   // ==0 ==1 -> 1
}
```

输出显示先比较基类 `B` 的成员，再比较 `m1`，`m1` 不相等就停止，`m2` 没有被比较。

## 预置的 `==` [class.eq]

¶1 预置的 `==` 的声明返回类型必须是 `bool`。

¶2 只要展开列表中有一个 x<sub>i</sub> 使 `xi == xi` 不可用，`C` 的预置 `==` 就被定义为删除。

¶3 返回值按下标从小到大比较 x<sub>i</sub> 与 y<sub>i</sub>，遇到第一个 `xi == yi` 转换为 `bool` 后为 `false` 的下标就返回 `false`，否则返回 `true`。换句话说，就是短路的逐成员 `&&`；没有子对象的空类总是返回 `true`。

¶4 是标准例 1：

```cpp run title="eq-example.cpp" ok
struct D {
  int i;
  friend bool operator==(const D& x, const D& y) = default;   // 返回 x.i == y.i
};

int main() { return D{1} == D{1} ? 0 : 1; }
```

## 预置的 `<=>` [class.spaceship]

### `auto` 返回类型（¶2.1、¶4）

```cpp run title="common-category.cpp" ok
#include <compare>
#include <string>
#include <type_traits>

struct Weak {
  int v;
  std::weak_ordering operator<=>(const Weak&) const = default;
};

struct A { int i; std::string s; auto operator<=>(const A&) const = default; };
struct B { int i; Weak w;        auto operator<=>(const B&) const = default; };
struct C { int i; Weak w; double d;
           auto operator<=>(const C&) const = default; };
struct E { auto operator<=>(const E&) const = default; };              // 空类
struct F { int a[3]; auto operator<=>(const F&) const = default; };    // 数组

static_assert(std::is_same_v<decltype(A{} <=> A{}), std::strong_ordering>);
static_assert(std::is_same_v<decltype(B{} <=> B{}), std::weak_ordering>);
static_assert(std::is_same_v<decltype(C{} <=> C{}), std::partial_ordering>);
static_assert(std::is_same_v<decltype(E{} <=> E{}), std::strong_ordering>);
static_assert(F{{1, 2, 3}} < F{{1, 2, 4}});

int main() {}
```

¶2.1 返回类型写作 `auto` 时，设 R<sub>i</sub> 是 `xi <=> xi` 的类型。只要有一个表达式不可用，或者某个 R<sub>i</sub> 不是比较类别类型，函数就被定义为删除。否则返回类型推导为所有 R<sub>i</sub> 的**公共比较类型**（[[g:common-comparison-type|common comparison type]]）。

¶4 公共比较类型取其中最弱的类别：

- ¶4.1 只要有一个是 `std::partial_ordering`，结果就是 `std::partial_ordering`；
- ¶4.2 否则，只要有一个是 `std::weak_ordering`，结果就是 `std::weak_ordering`；
- ¶4.3 否则是 `std::strong_ordering`。注 2 指出，列表为空时（如上例的空类 `E`）也是这个结果。

`strong` 可以转换为 `weak`，`weak` 可以转换为 `partial`，反过来不行，所以只能取最弱的。上例中 `double` 的 `<=>` 是 `partial_ordering`，于是 `C` 的结果也是。标准库的 `std::common_comparison_category` 做同样的计算（[[cmp.common]]）。

### 返回值（¶3）

¶3 返回值按下标从小到大比较 x<sub>i</sub> 与 y<sub>i</sub>，遇到第一个结果 v<sub>i</sub> 满足 `vi != 0` 就返回它；全部相等时返回 `static_cast<R>(std::strong_ordering::equal)`。这就是字典序比较。

对 `partial_ordering` 来说，`unordered != 0` 为真，所以遇到 NaN 这类无序的成员会立即返回 `unordered`：

```cpp run title="nan.cpp" ok
#include <cmath>
#include <compare>

struct P {
  double x;
  int y;
  auto operator<=>(const P&) const = default;
};

int main() {
  P a{NAN, 1}, b{NAN, 2};
  auto r = a <=> b;                          // 第一个成员就无序，立即返回
  bool ok = r == std::partial_ordering::unordered
            && !(a < b) && !(a > b) && !(a == b);
  return ok ? 0 : 1;
}
```

### 只有 `==` 和 `<` 的成员：合成三路比较（¶1、¶2.2）

很多 C++20 之前写的类型只有 `==` 和 `<`，没有 `<=>`。`auto <=>` 遇到这样的成员会被删除，因为 `xi <=> xi` 不可用。把返回类型写成具体的比较类别，编译器就会用 `==` 和 `<` 拼出三路比较：

```cpp run title="synthesized.cpp" ok
#include <compare>

struct Legacy {                  // 只有 == 与 <
  int v;
  constexpr bool operator==(const Legacy& o) const { return v == o.v; }
  constexpr bool operator<(const Legacy& o) const  { return v < o.v; }
};

struct W {
  Legacy l;
  std::strong_ordering operator<=>(const W&) const = default;   // OK: 用 == 与 < 合成
};

struct W2 {
  Legacy l;
  auto operator<=>(const W2&) const = default;   // 被定义为删除
};

static_assert(W{{1}} < W{{2}});
static_assert(W{{1}} == W{{1}});   // 隐式声明的 ==，调用 Legacy::operator==

int main() {}
```

这个拼法叫类型 `R` 的**合成三路比较**（[[g:synthesized-three-way-comparison|synthesized three-way comparison]]），由 [[P1186R3]] 引入。¶1 对同类型的 glvalue `a`、`b` 定义它：

- ¶1.1 如果 `a <=> b` 可用，并且能用 `static_cast` 转换为 `R`，结果就是 `static_cast<R>(a <=> b)`；
- ¶1.2 否则，如果 `a <=> b` 可用，或者对它的重载决议至少找到一个可行候选，合成三路比较没有定义；
- ¶1.3 否则，如果 `R` 不是比较类别，或者 `a == b`、`a < b` 有一个不可用，没有定义；
- ¶1.4 `R` 是 `strong_ordering` 时，结果是 `a == b ? equal : a < b ? less : greater`；
- ¶1.5 `R` 是 `weak_ordering` 时同上，只是 `equal` 换成 `equivalent`；
- ¶1.6 `R` 是 `partial_ordering` 时，结果是 `a == b ? equivalent : a < b ? less : b < a ? greater : unordered`。

注 1：如果重载决议找到了可用的候选，但它们不满足上述表达式的其他要求（例如 `a < b` 的结果不能转换为 `bool`），合成三路比较是非良构的。

第 1.2 项防止擅自退回：只要类型有 `<=>`，哪怕它的结果转换不成 `R`，或者调用有歧义，也不改用 `==` 和 `<` 拼。类型作者显然对三路比较有自己的设计，悄悄绕开它是危险的。`partial_ordering` 需要多比一次 `b < a`，才能区分 `greater` 和 `unordered`。

¶2.2 返回类型不是 `auto` 时，`R` 不能含占位符类型（例如不能写 `decltype(auto)`）。只要某个 x<sub>i</sub> 与自身的类型 `R` 的合成三路比较没有定义，函数就被定义为删除。

## 预置的 `!=`、`<` 等 [class.compare.secondary]

¶1 **次级比较运算符**（[[g:secondary-comparison-operator|secondary comparison operator]]）指 `<`、`>`、`<=`、`>=` 和 `!=`。预置的次级比较运算符的声明返回类型必须是 `bool`。

¶2 对形参 `x`、`y`，出现下面任一情况时，这个运算符函数被定义为删除：

- ¶2.1 对 `x @ y` 的第一次重载决议没有得到可用候选（¶2.1.1），或者选中的不是改写候选（¶2.1.2）；
- ¶2.2 用选中的改写候选解释 `x @ y` 得到的表达式（例如 `(x <=> y) @ 0`），对它的第二次重载决议没有得到可用候选；
- ¶2.3 `x @ y` 不能隐式转换为 `bool`。

两次重载决议都不把这个预置函数自己算作候选，否则它会选中自己。没有被删除时，函数返回 `x @ y`。

也就是说，预置的 `<` 就是用 `<=>` 实现的 `<`，预置的 `!=` 就是用 `==` 实现的 `!=`。改写候选已经自动提供了这些，预置它们是为了得到一个真实存在的函数：可以取地址，可以作为虚函数被覆盖。

```cpp run title="secondary.cpp" ok
#include <compare>

struct HasNoLessThan {};

struct C {
  friend HasNoLessThan operator<=>(const C&, const C&);
  bool operator<(const C&) const = default;   // OK: 被定义为删除（¶2.2）
};

template<class T> concept LessComparable = requires(T a) { a < a; };
static_assert(!LessComparable<C>);

struct Good {
  int v;
  auto operator<=>(const Good&) const = default;
  bool operator<(const Good&) const = default;   // 返回 (x <=> y) < 0
};
static_assert(Good{1} < Good{2});
static_assert(&Good::operator< != nullptr);     // 可以取地址

int main() {}
```

`C` 是 [class.compare.secondary] 的标准例 1：`(x <=> y) < 0` 中 `HasNoLessThan < int` 不可用，所以 `<` 被删除。

!!! note "Clang 的诊断位置"
    真的调用 `C` 的 `<` 时，按标准是使用了被删除的函数。本机 Clang 23 报告的错误却在预置函数内部：`invalid operands to binary expression ('HasNoLessThan' and 'int')`。对写成 `std::strong_ordering` 而成员是 `double` 的 `<=>`，Clang 同样在函数内部报告 `static_cast` 失败。程序非良构的结论一致；在 `requires` 等语境中，Clang 也正确地把它们当作删除。

## 与改写候选的交互

预置比较只生成 `==` 和 `<=>`。让它们支持六种运算符和对调操作数的，是 [[over.match.oper]] 的改写候选：

| 表达式 | 额外考虑的候选 | 选中后的含义 |
|---|---|---|
| `x < y`（`>`、`<=`、`>=` 同理） | `x <=> y` 和对调的 `y <=> x` | `(x <=> y) < 0` 或 `0 < (y <=> x)` |
| `x <=> y` | 对调的 `y <=> x` | `0 <=> (y <=> x)` |
| `x != y` | `x == y` 和对调的 `y == x` | `!(x == y)` 或 `!(y == x)` |
| `x == y` | 对调的 `y == x` | `y == x` |

两个候选同样好时，[[over.match.best]] 让非改写候选胜过改写候选（[[over.match.best#2.8]]），未对调的胜过对调的（[[over.match.best#2.9]]）。

### 对调带来的歧义

对调让 `1 == s` 这样的写法自动可用，也让一类旧代码出了问题：非 `const` 的成员 `operator==` 会和自己的对调版本产生歧义。

```cpp run title="reversed-ambiguity.cpp" error
struct S {
  int x;
  bool operator==(const S& o) { return x == o.x; }   // 忘了 const
};

bool f(S a, S b) { return a == b; }
// a.operator==(b)：a 绑定 S&（精确），b 绑定 const S&
// 对调的 b.operator==(a)：a 绑定 const S&，b 绑定 S&（精确）
// 各有一个实参更好，按标准是歧义

int main() { S a{1}, b{1}; return f(a, b) ? 0 : 1; }
```

两个候选各在一个实参上更好，[[over.match.best#2.9]] 的未对调优先只在各实参都不更差时才起作用，所以按标准是歧义，程序非良构。为了不让大量旧代码在升级到 C++20 后无法编译，Clang 和 GCC 都接受它，选未对调的那个并给出警告。本机 Clang 23 报告 `-Wambiguous-reversed-operator`：ISO C++20 认为这次使用有歧义，尽管存在唯一的最佳可行函数。正确的修复是给成员 `operator==` 加上 `const`。

### 写了 `!=` 就不再改写 `==`

[[over.match.oper#4]] 规定，名为 `operator==` 的函数 *F* 是**改写目标**，除非在相应作用域里能找到一个与 *F* 对应（改名为 `operator==` 后就会对应）的 `operator!=`。只有改写目标才能被对调或用来实现 `!=`。这条规则来自 [[P2468R2]]，作为对 C++20 的缺陷报告：既然作者自己成对写了 `==` 和 `!=`，编译器就不再替他改写。

```cpp title="rewrite-target.cpp" error
struct A {
  int x;
  bool operator==(int i) const { return x == i; }
  bool operator!=(int i) const { return x != i; }   // 与 operator==(int) 对应
};
struct B {
  int x;
  bool operator==(int i) const { return x == i; }   // 没有对应的 !=
};

bool f1(A a) { return 1 == a; }   // error: A::operator== 不是改写目标，不能对调
bool f2(B b) { return 1 == b; }   // OK: 对调为 b == 1
bool f3(B b) { return 1 != b; }   // OK: !(b == 1)
```

!!! impl "生成的代码"
    预置的 `<=>` 就是 [[class.spaceship#3]] 的直译：逐个子对象比较，结果非零即返回；预置的 `==` 是短路的逐成员 `&&`。优化器能看到全部比较，生成的代码通常与手写的同等逻辑相同。预置的比较满足条件时隐式为 `constexpr`（[[dcl.fct.def.default]]），异常说明也是隐式的：只有用到的成员比较都不抛出时才是 `noexcept`（[[except.spec]]）。

!!! history
    C++20 的 [[P0515R3]] 引入 `<=>`、比较类别和预置 `<=>`。随后 [[P1185R2]] 让 `==` 不再改写成 `<=>`，改由预置 `<=>` 隐式声明预置 `==`；[[P1186R3]] 加入合成三路比较，让只有 `==` 和 `<` 的旧类型也能用于预置 `<=>`；[[P2002R1]] 整理了可预置的形式、删除条件和查找语境。[[P2468R2]] 作为对 C++20 的缺陷报告引入改写目标，存在对应的 `operator!=` 时不再改写 `operator==`。

## 常见误解

!!! pitfall "自己写了 `<=>`，`==` 就有了"
    只有预置的 `<=>` 才会隐式声明 `==`。手写 `<=>` 时要再写 `bool operator==(const T&) const = default;` 或手写 `==`。

!!! pitfall "加一个 `operator==(int)` 不影响同类比较"
    [[class.compare.default#4]] 的条件是没有任何名为 `operator==` 的成员或友元。任何一个都会抑制隐式的 `==`，这时需要显式写 `bool operator==(const T&) const = default;`。

!!! pitfall "`auto <=>` 能处理只有 `<` 的旧类型"
    `auto` 不做合成（[[class.spaceship#2.1]]），整个 `<=>` 被删除，`<`、`>` 等也随之不可用。把返回类型写成具体的类别，例如 `std::weak_ordering`。

!!! pitfall "含浮点成员的类可以声明 `std::strong_ordering <=>`"
    `double` 的 `<=>` 返回 `partial_ordering`，不能 `static_cast` 为 `strong_ordering` 或 `weak_ordering`，合成三路比较没有定义（[[class.spaceship#1.2]]），外层的 `<=>` 被删除。需要全序时手写比较，例如对浮点成员用 `std::strong_order`。

!!! pitfall "指针成员按指向的内容比较"
    预置比较比较的是指针本身的值，也就是地址。需要按内容比较时要手写。

## 思考题

!!! question "1. `a == b` 和 `a < b` 各调用了哪些函数？"
    ```cpp nocheck
    struct Str {
      bool operator==(const Str&) const;
      std::strong_ordering operator<=>(const Str&) const;
    };
    struct T {
      int n;
      Str s;
      auto operator<=>(const T&) const = default;
    };
    T a, b;
    ```

<details markdown="1">
<summary>答案</summary>

`a == b` 调用隐式声明的预置 `T::operator==`（[[class.compare.default#4]]），它依次计算 `a.n == b.n`（内建）和 `a.s == b.s`（`Str::operator==`），前者为假时不再比较后者。不调用任何 `<=>`。

`a < b`：`T` 没有 `operator<`，改写为 `(a <=> b) < 0`，调用预置的 `T::operator<=>`。它依次计算 `a.n <=> b.n`（内建）和 `a.s <=> b.s`（`Str::operator<=>`），返回第一个非零的结果。返回类型推导为 `strong_ordering`。
</details>

!!! question "2. `struct X { int v; bool operator<(const X&) const; bool operator==(const X&) const; };`，下面哪些类的 `<=>` 可用？"
    ```cpp nocheck
    struct Y1 { X x; auto operator<=>(const Y1&) const = default; };
    struct Y2 { X x; std::weak_ordering operator<=>(const Y2&) const = default; };
    struct Y3 { X x; std::partial_ordering operator<=>(const Y3&) const = default; };
    ```

<details markdown="1">
<summary>答案</summary>

`Y1` 的 `<=>` 被定义为删除：返回类型是 `auto`，`x <=> x` 不可用（[[class.spaceship#2.1]]）。`Y2` 可用，合成三路比较按 [[class.spaceship#1.5]] 计算。`Y3` 可用，按 [[class.spaceship#1.6]] 计算，会多调用一次 `y < x`。三者都隐式声明预置的 `==`，它调用 `X::operator==`。本机 Clang 的检查结果与此一致。
</details>

!!! question "3. 为什么只要 `a <=> b` 的重载决议找到了可行候选，哪怕最后歧义，合成三路比较也不退回到用 `==` 和 `<`？"

<details markdown="1">
<summary>答案</summary>

这说明类型作者确实为它提供了三路比较，只是这次调用有问题（歧义、结果类型不对、已删除等）。此时悄悄改用 `==` 和 `<` 拼，可能得到与作者设计不一致的语义，还会掩盖错误。让预置的 `<=>` 变成删除，问题会在使用处暴露。只有类型完全没有三路比较时才退回，这是 [[P1186R3]] 的设计意图。
</details>
