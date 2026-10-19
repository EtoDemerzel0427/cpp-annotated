---
title: 名字查找、ADL 与定制点
summary: 编译器怎样为一个名字找到声明：限定查找与无限定查找、遮蔽、实参依赖查找及其关闭条件、隐藏友元和运算符的查找，以及标准库让用户定制行为的几代设计。
status: draft
order: 76
since: c++98
papers: N4381, P0551R3, P2602R2, P1895R0, P2855R1, P2547R1
related: basic.lookup, basic.lookup.unqual, basic.lookup.qual, basic.lookup.argdep, class.friend, over.match.oper, namespace.std, customization.point.object, range.access, concept.swappable, alg.func.obj, dcl.struct.bind, topics/two-phase-lookup, topics/overload-resolution-walkthrough
tags: 名字查找, ADL, 隐藏友元, 定制点, CPO, 专题
updated: 2026-10-19
---

!!! tldr
    - 限定名 `std::swap` 只在 `std` 里找；无限定名 `swap` 从调用处逐层向外找，找到第一个有这个名字的作用域就停下，外层的同名声明全被遮住。
    - 无限定的函数调用还会做 ADL：到实参类型（包括模板实参）所在的命名空间里找函数。`using std::swap; swap(a, b);` 能找到用户的 `swap`，靠的就是它。
    - 名字加了括号，或者普通查找找到了类成员、块作用域函数声明、变量或函数对象，ADL 就不做。
    - 只在类里声明的友元函数（隐藏友元）只能经 ADL 找到，运算符写成隐藏友元，重载集最小，也不会被隐式转换误选。
    - 标准库的定制点经历了四代：靠 ADL 的自由函数、特化 `std` 里的类模板、定制点对象（`std::ranges::swap`）、`tag_invoke`；C++26 的 `std::execution` 改为调用成员函数。往 `std` 里添加重载是 UB。

## 同一个 swap，两种调用

```cpp run title="swap.cpp" ok
#include <cstdio>
#include <utility>
#include <concepts>
namespace app {
struct Buf {
  int* data;
  friend void swap(Buf& a, Buf& b) noexcept {
    std::puts("app::swap");
    std::swap(a.data, b.data);
  }
};
}
int main() {
  app::Buf a{}, b{};
  std::swap(a, b);           // 限定名：只在 std 里找
  using std::swap;
  swap(a, b);                // 无限定名：ADL 找到 app::swap
  std::ranges::swap(a, b);   // 定制点对象：内部替你做 ADL
}
```

程序只输出两行 `app::swap`。第一次调用 `std::swap(a, b)` 用的是标准库的通用版本，通过一次移动构造和两次移动赋值完成交换，用户写的 `swap` 根本不在候选里。

差别全在**名字查找**（[[g:name-lookup|name lookup]]）：编译器为代码里出现的一个名字找到它的声明。查找先于重载决议进行，只有被找到的函数才有资格参加重载决议（[[basic.lookup.general#1]]）。所以这里要回答的问题是查找找到了哪些函数，而不是哪个函数更匹配。

## 两种查找：限定与无限定

`std::swap` 是**限定名**（[[g:qualified-name|qualified name]]）：名字前面有 `X::`，或者出现在 `obj.`、`p->` 之后。限定名只在指定的那个类或命名空间里查找（[[basic.lookup.qual]]）。在命名空间里查找时，还会搜索它的内联命名空间；什么都没找到时，再沿着这个命名空间里的 using 指令继续找（[[namespace.qual#1]]）。`std::swap` 因此只会找到 `std` 里的 `swap`。

`swap` 是**无限定名**（[[g:unqualified-name|unqualified name]]）。它从名字出现的位置开始，在当前作用域里搜索；什么都没找到，才到外一层作用域继续，一直到全局命名空间（[[basic.lookup.unqual#2]]）。因此，只要某一层找到了这个名字的任何声明，查找就停在这一层。

<div class="compare" markdown="1">

```cpp error
void log(int);
namespace app {
void log(const char*);
void run() {
  log(42);   // error: ::log 被遮住
}
}
```

```cpp ok
void log(int);
namespace app {
void log(const char*);
using ::log;   // 把 ::log 引入 app
void run() {
  log(42);     // OK：调用 ::log(int)
}
}
```

</div>

左边的查找在 `app` 里找到了 `log(const char*)`，就不再去全局命名空间，`::log(int)` 从未成为候选。本机 Clang 23 只列出一个候选：

```text
error: no matching function for call to 'log'
note: candidate function not viable: no known conversion from 'int' to 'const char *' for 1st argument
```

这种现象叫**遮蔽**（hiding）。遮蔽只看名字，不看参数类型是否匹配，更不看哪个更好。右边的 using 声明把 `::log` 也放进 `app`，两个函数就在同一层被找到，再交给重载决议。

类作用域也一样，派生类声明了 `f`，基类的所有 `f` 就被遮住，在成员函数里调用 `f(42)` 只会看到派生类的版本（[[class.member.lookup]]）。修法同样是在派生类里写 `using Base::f;`。

## ADL：到实参类型的命名空间里找

如果无限定查找就是全部规则，`using std::swap; swap(a, b);` 只会找到 `std::swap`。它之所以能找到 `app::swap`，是因为函数调用里的无限定名还要做**实参依赖查找**（[[g:argument-dependent-lookup|argument-dependent lookup]]，ADL）：根据实参的类型确定一组**关联命名空间**（[[g:associated-namespaces|associated namespaces]]），在这些命名空间里再找同名的函数，结果与普通查找的结果合并成一个重载集（[[basic.lookup.argdep#1]]）。

`a` 的类型是 `app::Buf`，关联命名空间是 `app`，于是 `app::swap` 加入候选。重载集是 `{std::swap<Buf>, app::swap}`，后者不是模板，胜出（[[over.match.best]]）。对 `int`，基本类型没有关联命名空间，ADL 什么也不加，用的是 `std::swap`。`using std::swap;` 这一行就是为这种情况准备的后备。

关联命名空间由实参类型的**关联实体**（[[g:associated-entities|associated entities]]）决定，规则在 [[basic.lookup.argdep#3]]，[[basic.lookup.argdep]] 有逐条的例子。要点如下：

| 实参类型 | 带来的关联实体 |
|---|---|
| `int`、`double`、`nullptr_t` 等基本类型 | 无 |
| 类 `C` | `C` 本身；`C` 是嵌套类时还有外围类；`C` 完整时还有它的所有基类 |
| 类模板特化 `X<A, B>` | 上一行的全部，加上类型模板实参 `A`、`B` 各自的关联实体 |
| 枚举 | 枚举本身；它是类成员时还有那个类 |
| 指针、数组 | 元素类型的关联实体 |
| 函数类型、函数指针 | 参数类型和返回类型的关联实体 |

关联命名空间是这些实体最内层的外围命名空间，再加上其中的内联命名空间（[[basic.lookup.argdep#4]]）。typedef 和别名不起作用，只看它代表的类型。

最容易出乎意料的是模板实参这一行。`std::vector<app::Point>` 的关联命名空间是 `std` 和 `app`，于是泛型代码里的一次无限定调用，可能被这两个命名空间里碰巧同名的函数接走：

```cpp run title="hijack.cpp" ok
#include <cstdio>
#include <vector>
namespace lib {
template<class C> int size(const C& c) { return int(c.size()); }
template<class C> void report(const C& c) {
  std::printf("%d\n", size(c));   // 作者的本意：调用 lib::size
}
}
namespace app {
struct Point { int x, y; };
int size(const std::vector<Point>&) { return -1; }
}
int main() {
  std::vector<app::Point> v(3);
  lib::report(v);   // 输出 -1
}
```

`report` 里的 `size(c)` 依赖于模板形参，ADL 在实例化时进行（见 [[topics/two-phase-lookup]]）。候选有三个：普通查找找到的 `lib::size`，ADL 在 `std` 里找到的 `std::size`（C++17 起），ADL 在 `app` 里找到的 `app::size`。最后一个不是模板，胜出。

删掉 `app::size` 也不能回到作者的本意：`lib::size` 和 `std::size` 的形参都是 `const C&`，一样好，本机 Clang 23 报告 `call to 'size' is ambiguous`。同一个机制，类型作者有意提供时叫定制，碰巧同名时叫劫持。

## 什么时候没有 ADL

[[basic.lookup.argdep#1]] 规定，只有被调用的部分是一个不带括号的无限定名，并且普通的无限定查找没有找到以下三种声明，才做 ADL：

- 类成员的声明（¶1.1）；
- 块作用域里的函数声明（¶1.2）；
- 不是函数或函数模板的声明，比如变量、函数对象、类型（¶1.3）。

```cpp title="no-adl.cpp" error
namespace N {
struct S {};
void f(S);
}
void a() { N::S s; f(s); }     // OK：ADL 找到 N::f
void b() { N::S s; (f)(s); }   // error: 括号关掉 ADL
void c() {
  N::S s;
  void f(int);                 // 块作用域函数声明
  f(s);                        // error: 关掉 ADL，只剩 f(int)
}
```

本机 Clang 23 对 `b` 报 `use of undeclared identifier 'f'; did you mean 'N::f'?`，对 `c` 报 `no viable conversion from 'N::S' to 'int'`。

块作用域里的 `using std::swap;` 不会关掉 ADL。using 声明被找到时，要换成它指名的声明（[[basic.lookup.general#3]]），也就是 `std` 里的函数模板。它们不栖居于块作用域，不属于 ¶1.2。

¶1.3 是后文定制点对象的基础：普通查找找到一个变量，ADL 就不做了。

```cpp run title="object.cpp" ok
#include <cstdio>
namespace N {
struct S {};
void f(S) { std::puts("N::f"); }
}
inline constexpr auto f = [](auto) { std::puts("::f 对象"); };
int main() {
  N::S s;
  f(s);   // 找到变量 ::f，ADL 被关掉，输出 "::f 对象"
}
```

¶1.1 最常在成员函数里出问题。类自己有一个名为 `swap` 的成员，在它的成员函数里写无限定的 `swap(x, y)`，查找在类作用域找到成员，ADL 被关掉：

<div class="compare" markdown="1">

```cpp error
#include <string>
#include <utility>
struct Person {
  std::string name;
  void swap(Person& o) noexcept {
    swap(name, o.name);
    // error: 找到成员 swap
  }
};
```

```cpp ok
#include <string>
#include <utility>
struct Person {
  std::string name;
  void swap(Person& o) noexcept {
    using std::swap;
    swap(name, o.name);   // OK
  }
};
```

</div>

左边的错误信息是 `too many arguments to function call, expected 1, have 2`：编译器只看见了成员 `Person::swap(Person&)`。右边的块作用域比类作用域先被搜索，查找在 using 声明处停下，找到的是命名空间里的函数，ADL 照常进行。

## 隐藏友元

```cpp title="hidden-friend.cpp" error
namespace geo {
struct Point {
  int x, y;
  friend bool operator==(const Point&, const Point&) = default;
};
}
bool a(geo::Point p, geo::Point q) { return p == q; }            // OK：ADL
bool b(geo::Point p, geo::Point q) { return operator==(p, q); }  // OK：也是 ADL
bool c(geo::Point p, geo::Point q) {
  return geo::operator==(p, q);   // error: 限定查找找不到
}
```

类里的友元声明 `friend bool operator==(...)` 声明的是外围命名空间 `geo` 里的函数，但友元声明不把名字引入任何作用域（[[dcl.meaning.general#2]] ¶2.1，[[class.friend#10]]）。只要命名空间作用域里没有再声明一次，普通查找和限定查找都找不到它，本机 Clang 23 对 `c` 报 `no member named 'operator==' in namespace 'geo'`。

ADL 是唯一的例外：它还会找到关联类里声明的友元函数（[[basic.lookup.argdep#4]] ¶4.2）。这种只在类里声明的友元函数叫**隐藏友元**（[[g:hidden-friend|hidden friend]]）。把运算符和 `swap` 这类定制函数写成隐藏友元，有三个好处。

第一，重载集更小。命名空间作用域的运算符会参与这个命名空间里每一次同名运算符的查找。下面两段代码都在命名空间 `big` 里定义 100 个类型和它们的 `operator<<`，然后对一个没有 `operator<<` 的 `big::Unprintable` 写 `os << x`：

| 写法 | 本机 Clang 23 列出的候选数 |
|---|---|
| 100 个命名空间作用域的 `operator<<` | 151（100 个来自 `big`，51 个来自 libc++） |
| 100 个隐藏友元 `operator<<` | 51（全部来自 libc++） |

隐藏友元只在实参的关联类恰好是它所在的类时才进入候选集。命名空间作用域的版本每次都要为它们做模板实参推导和隐式转换检查，编译变慢，错误信息变长。

第二，不会因为隐式转换被误选。一个只是能转换成 `Point` 的类型，关联实体里没有 `Point`，找不到 `Point` 的隐藏友元。[[basic.lookup.argdep]] 有可运行的对比。

第三，可以访问私有成员，不必为了写运算符而公开 getter。

## 运算符怎样查找

运算符表达式 `a << b` 先改写成函数调用的形式，再按 [[over.match.oper#3]] 收集三类候选：

- 成员候选：在 `a` 的类里搜索 `operator<<`（¶3.1）；
- 非成员候选：对 `operator<<` 做无限定查找加 ADL，并且忽略找到的所有成员函数（¶3.2）；
- 内置候选：比如 `int << int` 的内置移位（¶3.3）。

运算符没有带括号或带限定的写法，所以总会做 ADL。¶3.2 忽略成员函数这一点，还带来一个和具名调用不同的结果：

<div class="compare" markdown="1">

```cpp run ok
#include <iostream>
#include <string>
struct Logger {
  Logger& operator<<(int) {
    return *this;
  }
  void dump(const std::string& s) {
    std::cout << s << '\n';   // OK
  }
};
int main() { Logger{}.dump("hi"); }
```

```cpp error
#include <iostream>
#include <string>
struct Logger {
  Logger& operator<<(int) {
    return *this;
  }
  void dump(const std::string& s) {
    operator<<(std::cout, s);
    // error: 找到成员，ADL 被关掉
  }
};
```

</div>

左边在 `Logger` 的成员函数里写 `std::cout << s`，无限定查找先在类作用域找到了 `Logger::operator<<`，但运算符的非成员查找忽略成员，ADL 照常进行，找到 `std` 里接受 `std::string` 的 `operator<<`。右边把同一件事写成具名的函数调用，适用的是 [[basic.lookup.argdep#1]] ¶1.1，ADL 被关掉，本机 Clang 23 报 `too many arguments to function call, expected 1, have 2`。

运算符的非成员查找仍然会被遮蔽：命名空间里只要声明了任何一个 `operator<<`，外层命名空间里的 `operator<<` 就只能靠 ADL 找到。在全局命名空间为 `std::vector<int>` 写的 `operator<<`，ADL 永远找不到，因为 `std::vector<int>` 的关联命名空间只有 `std`。[[topics/two-phase-lookup]] 的谜题 2 演示了这个后果。为一个类型写的运算符，应当放在这个类型的命名空间里，最好写成隐藏友元。

## 定制点的几代设计

泛型库常常需要调用一个由用户类型决定行为的操作：交换两个对象、取一个范围的起点、计算哈希。库里调用这个操作的地方叫**定制点**（customization point）。C++ 先后用过几种设计，每一种都在补上一种的问题。

### 第一代：可重载的自由函数

`swap`、`begin`/`end`、`operator<<` 都是这一代。库在泛型代码里写无限定调用，用户在自己的命名空间里提供同名函数，ADL 把两者连起来。它的问题前面都已经出现过：

- 调用方必须记得写成 `using std::swap; swap(a, b);`，写成 `std::swap(a, b)` 就悄悄绕过了用户的定制；
- 无限定调用会被碰巧同名的函数劫持，或者变得二义（`hijack.cpp`）；
- 库无法检查用户的函数是否真的满足要求，比如 `swap` 是否真的交换了两个值。

### 第二代：特化 std 里的类模板

`std::hash`、`std::tuple_size`、`std::formatter` 属于这一代：用户为自己的类型特化标准库的类模板。

```cpp run title="hash.cpp" ok
#include <cstddef>
#include <functional>
#include <string>
#include <unordered_set>
namespace app {
struct Id {
  std::string name;
  int n;
  bool operator==(const Id&) const = default;
};
}
template<>
struct std::hash<app::Id> {
  std::size_t operator()(const app::Id& id) const noexcept {
    return std::hash<std::string>{}(id.name) ^ std::size_t(id.n);
  }
};
int main() {
  std::unordered_set<app::Id> s{{"a", 1}, {"a", 1}};
  return int(s.size()) - 1;   // 返回 0
}
```

特化不需要写进 `namespace std { }` 里，写成 `std::hash<app::Id>` 这样的限定名就可以在全局声明（[[temp.expl.spec#3]]）。这种设计不依赖 ADL，类模板的特化总能被找到；代价是用户必须离开自己的命名空间写一大段样板代码，而且只能用于类模板。

结构化绑定的元组协议把两代混在一起。类型要能写 `auto [k, v] = e;`，需要特化 `std::tuple_size` 和 `std::tuple_element`，再提供 `get<i>`。按 [[dcl.struct.bind#7]]，类里有合适的成员模板 `get` 就调用 `e.get<i>()`，否则调用 `get<i>(e)`，并且只做 ADL，不做普通的无限定查找：

```cpp run title="tuple-protocol.cpp" ok
#include <cstddef>
#include <cstdio>
#include <string>
#include <tuple>
namespace app {
class Entry {
  std::string key_ = "k";
  int value_ = 42;
  template<std::size_t I>
  friend auto get(const Entry& e) {      // 隐藏友元：经 ADL 找到
    if constexpr (I == 0) return e.key_;
    else return e.value_;
  }
};
}
template<>
struct std::tuple_size<app::Entry> : std::integral_constant<std::size_t, 2> {};
template<std::size_t I>
struct std::tuple_element<I, app::Entry> {
  using type = std::conditional_t<I == 0, std::string, int>;
};
int main() {
  auto [k, v] = app::Entry{};
  std::printf("%s %d\n", k.c_str(), v);   // 输出 k 42
}
```

### 第三代：定制点对象 {{c++20}}

[[N4381]] 提出把定制点做成一个全局的函数对象，C++20 的 ranges 库照此设计。标准把这样的对象称为**定制点对象**（[[g:customization-point-object|customization point object]]，CPO，[[customization.point.object#1]]）。`std::ranges::swap`、`std::ranges::begin` 都是 CPO。

它同时解决了第一代的三个问题：

- 调用方只写 `std::ranges::swap(a, b)`。这是限定名，找到的是一个对象，不会被劫持，也不需要两步法。
- ADL 只收集函数，永远找不到这个对象（[[basic.lookup.argdep#4]]）；有人写了 `using namespace std::ranges;` 再无限定地调用 `swap(a, b)`，普通查找找到变量，按 ¶1.3 关掉 ADL。
- 对象的 `operator()` 内部以受控的方式查找用户的定制，并检查语义要求。找不到合适的定制时，它退回到通用实现；`operator()` 本身受约束，不满足要求时不参与重载决议（[[customization.point.object#4]]）。

以 `ranges::swap(E1, E2)` 为例，[[concept.swappable#2]] 依次尝试三种做法：

1. 某个实参是类或枚举类型，并且无限定调用 `swap(E1, E2)` 有效，就调用它。这次重载决议所在的语境里没有 `ranges::swap` 本身，而是有一个被删除的声明 `template<class T> void swap(T&, T&) = delete;`（¶2.1）；
2. 两个实参是同样长度的数组，就逐个元素交换（¶2.2）；
3. 两个实参是同类型的左值，并且可以移动构造、移动赋值，就用移动完成交换（¶2.3）。

第 1 步里那个被删除的声明，俗称**毒丸**（poison pill）。它让查找停在那里，不会向外找到 `std::swap` 这类不受约束的模板。它也参与重载决议，这带来一个意外：用户在自己的命名空间里写的不受约束的 `swap` 模板，和毒丸一样好，结果是二义，第 1 步无效，用户的 `swap` 被悄悄跳过。

```cpp run title="poison-pill.cpp" ok
#include <concepts>
#include <cstdio>
#include <utility>
namespace app {
struct A { int v; };
template<class T> void swap(T& x, T& y) {   // 不受约束的模板
  std::puts("app::swap<T>");
  std::swap(x.v, y.v);
}
struct B { int v; };
void swap(B& x, B& y) {                     // 非模板
  std::puts("app::swap(B&, B&)");
  std::swap(x.v, y.v);
}
}
int main() {
  app::A a1{1}, a2{2};
  app::B b1{1}, b2{2};
  std::ranges::swap(a1, a2);   // 不输出：退回到第 3 步，按移动交换
  std::ranges::swap(b1, b2);   // 输出 app::swap(B&, B&)
  std::printf("%d %d\n", a1.v, b1.v);   // 2 2
}
```

¶2.1 的注明确说，这种写法排除了不受约束的用户 `swap`，用户的重载必须比毒丸更特化才会被选中。为具体类型写的非模板 `swap`，或者写成隐藏友元，都满足这一点。

`ranges::begin` 原来也有毒丸，C++23 的 [[P2602R2]] 以缺陷报告的形式去掉了它。现在的规则是：成员 `t.begin()` 可用就用它；否则对类或枚举类型调用 `begin(t)`，并且如同只做 ADL（[[range.access.begin#2]] ¶2.5）。经 ADL 找到的非成员 `begin` 和成员版本一样，返回类型必须满足 `input_or_output_iterator`，否则这一步不成立。细节见 [[range.access]]。

`std::ranges` 里的算法（`find`、`sort`……）也是对象，标准称为**算法函数对象**（algorithm function object，[[alg.func.obj#2]]），俗称 niebloid。它们不定制任何东西，做成对象只是为了不被 ADL 找到，并在被普通查找找到时关掉 ADL，保证 `using namespace std::ranges;` 之后的 `find(...)` 调用的就是受约束的 ranges 版本。

### 第四代：tag_invoke

CPO 解决了调用方的问题，但每个 CPO 都要库作者手写一套查找规则，用户还要知道每个 CPO 认的是哪个名字。[[P1895R0]] 提出了 `tag_invoke`：所有定制点共用一个函数名 `tag_invoke`，用 CPO 自己的类型作为第一个实参区分不同的定制点。

```cpp run title="tag-invoke.cpp" ok
#include <cstdio>
#include <string>
#include <utility>

namespace lib {
namespace detail {
void tag_invoke();   // 让下面的查找停在这里，不向外找
struct tag_invoke_fn {
  template<class Tag, class... Args>
  constexpr auto operator()(Tag tag, Args&&... args) const
      -> decltype(tag_invoke(tag, std::forward<Args>(args)...)) {
    return tag_invoke(tag, std::forward<Args>(args)...);   // 唯一的 ADL 调用点
  }
};
}
inline constexpr detail::tag_invoke_fn tag_invoke{};

struct to_string_fn {   // 一个定制点 = 一个类型
  template<class T>
  std::string operator()(const T& x) const { return lib::tag_invoke(*this, x); }
};
inline constexpr to_string_fn to_string{};
}

namespace app {
struct Point {
  int x, y;
  friend std::string tag_invoke(lib::to_string_fn, const Point& p) {
    return std::to_string(p.x) + "," + std::to_string(p.y);
  }
};
}

int main() { std::puts(lib::to_string(app::Point{1, 2}).c_str()); }   // 输出 1,2
```

用户定制时写的是 `tag_invoke(lib::to_string_fn, ...)`，不会和别的库里叫 `to_string` 的函数冲突。库作者只需要写一次 ADL 调用点。

它的缺点也明显。所有定制都叫 `tag_invoke`，一个类型可能有几十个这样的重载，每次调用都要对它们全部做重载决议，编译慢，错误信息难读；定制函数的签名看不出它定制的是什么，只能看第一个形参的类型。有提案（如 [[P2547R1]]）尝试用语言机制直接支持可定制的函数，截至当前草案没有进入标准。

### C++26 的 std::execution：成员函数 {{c++26}}

`std::execution`（发送者/接收者模型）在设计过程中用的是 `tag_invoke`，[[P2855R1]] 把它改成了直接调用成员函数，C++26 采纳的是这个版本。例如：

- `execution::connect(sndr, rcvr)` 在可行时等价于 `new_sndr.connect(rcvr)`，`new_sndr` 是对 `sndr` 做完变换之后的发送者（[[exec.connect#6]]）；
- `execution::set_value(rcvr, vs...)` 等价于 `rcvr.set_value(vs...)`，并且要求 `rcvr` 是非 const 右值（[[exec.set.value#1]]）；
- `execution::get_env(o)` 调用 `o.get_env()`，没有这个成员时返回空环境（[[exec.get.env#1]]）。

于是一个接收者就是一个普通的类：

```cpp
struct print_receiver {
  using receiver_concept = std::execution::receiver_tag;
  void set_value(int v) && noexcept { std::printf("%d\n", v); }
  void set_error(std::exception_ptr) && noexcept {}
  void set_stopped() && noexcept {}
};
```

`connect`、`set_value` 这些名字仍然是 CPO，调用方的写法没有变；变的是用户提供定制的方式，从 ADL 找到的自由函数变成了成员函数，查找规则就是普通的成员查找，没有劫持，也没有庞大的重载集。需要按执行资源定制算法时，用的是**域**（domain）：一个类，它的成员 `transform_sender` 负责改写发送者（[[exec.snd.transform#3]]）。上例里的 `receiver_tag` 是当前草案中的名字（[[exec.recv.concepts#1]]）。本机 libc++ 还没有实现 `std::execution`，这段代码没有验证。

### 四代对比

| 设计 | 例子 | 用户怎样定制 | 调用方怎样写 | 主要问题 |
|---|---|---|---|---|
| ADL 自由函数 | `swap`、`begin`、`operator<<` | 在自己的命名空间写同名函数 | `using std::swap; swap(a, b);` | 容易写错；会被劫持；不检查语义 |
| 特化类模板 | `std::hash`、`tuple_size`、`formatter` | 特化 `std` 里的类模板 | `std::hash<T>{}(x)` | 样板多；只能是类模板 |
| CPO | `ranges::swap`、`ranges::begin` | 同名自由函数（隐藏友元）或成员 | `std::ranges::swap(a, b)` | 每个 CPO 规则各异；毒丸的意外 |
| `tag_invoke` | 早期的 `std::execution` | `tag_invoke(cpo_type, ...)` | `cpo(args...)` | 重载集庞大；签名难读 |
| 成员函数 | C++26 `std::execution` | 写成员函数 | `cpo(args...)` | 只能定制自己的类型 |

## std 里能加什么

既然 `std::swap` 找不到用户的函数，一个常见的想法是把重载直接写进 `std`：

<div class="compare" markdown="1">

```cpp ub
#include <utility>
namespace app { struct X {}; }
namespace std {
void swap(app::X&, app::X&) noexcept;
// UB：向 std 添加声明
}
```

```cpp ok
#include <utility>
namespace app {
struct X {
  friend void swap(X&, X&) noexcept {}
};
}
```

</div>

[[namespace.std#1]] 规定，除非另有说明，向 `std` 或其中的命名空间添加声明或定义是未定义行为。另有说明的情形主要是 ¶2：可以为标准库的类模板添加特化，条件是特化依赖至少一个程序定义的类型，并且满足原模板的要求。`std::hash<app::Id>`、`std::tuple_size<app::Entry>` 就属于这一类。

C++20 起，标准库的函数模板不能再特化（[[P0551R3]]），`template<> void std::swap<app::X>(...)` 也是 UB。定制 `swap` 的唯一正确方式是在类型自己的命名空间里写重载，最好写成隐藏友元。完整的清单见 [[namespace.std]]。

## 常见误解

!!! pitfall "重载决议会从所有同名函数里挑最好的"
    重载决议只在查找找到的函数之间挑选。外层的函数被遮住、ADL 被关掉时，更好的函数根本不是候选，编译器也不会提示它存在。

!!! pitfall "写 std::swap 最保险"
    在泛型代码里，`std::swap(a, b)` 永远不会调用用户为自己的类型写的 `swap`，结果是正确但更慢的三次移动。要么写两步法，要么用 `std::ranges::swap`。

!!! pitfall "ADL 只看实参自己的类型"
    模板实参、基类、外围类、函数指针的参数类型都会带来关联命名空间。给泛型库里的辅助函数起 `size`、`distance`、`find` 这类常见的名字时，用户类型或 `std` 里的同名函数都可能被 ADL 带进来。

!!! pitfall "隐藏友元可以用 N::f 调用"
    友元声明不绑定名字，隐藏友元只能经 ADL 找到。需要能限定调用的函数，就在命名空间作用域再声明一次，但这样它也就不再是隐藏友元。

## 思考题

!!! question "1"
    ```cpp
    #include <vector>
    struct Range {
      std::vector<int> v;
      std::vector<int>::iterator begin() { return begin(v); }
    };
    ```
    这段代码能编译吗？

<details markdown="1">
<summary>答案</summary>

不能。在成员函数 `begin` 里，无限定查找先在类作用域找到成员 `Range::begin()`，按 [[basic.lookup.argdep#1]] ¶1.1 关掉 ADL，`std::begin` 没有机会进入候选。本机 Clang 23 报 `too many arguments to function call, expected 0, have 1; did you mean 'std::begin'?`。改成 `using std::begin; return begin(v);`，或者直接写 `v.begin()`。
</details>

!!! question "2"
    `app` 里只有一个不受约束的 `template<class T> void swap(T&, T&)`。对 `app::A` 写 `using std::swap; swap(x, y);`，结果如何？换成 `std::ranges::swap(x, y)` 呢？

<details markdown="1">
<summary>答案</summary>

两步法是二义的。重载集里有 `std::swap<app::A>` 和 `app::swap<app::A>`，两个模板的形参都是 `T&`，偏序上一样特化，本机 Clang 23 报 `call to 'swap' is ambiguous`。

`std::ranges::swap` 能编译，但不调用 `app::swap`。第 1 步里用户的模板与毒丸二义，表达式无效；第 3 步用移动完成交换（[[concept.swappable#2]]）。两种写法都不调用这个 `swap`，它应当改成针对 `A` 的非模板函数，或者加上约束。
</details>

!!! question "3"
    `int arr[3]; auto b = begin(arr);` 不加 `using std::begin;` 能编译吗？`std::vector<int> v; auto a = begin(v);` 呢？

<details markdown="1">
<summary>答案</summary>

`begin(v)` 可以：`std::vector<int>` 的关联命名空间是 `std`，ADL 找到 `std::begin`。`begin(arr)` 不行：数组的关联实体是元素类型的关联实体，`int` 什么也不带来，本机 Clang 23 报 `use of undeclared identifier 'begin'; did you mean 'std::begin'?`。`std::ranges::begin(arr)` 对数组有专门的规则（[[range.access.begin#2]] ¶2.3），不需要 ADL。
</details>

## 小结

| 问题 | 规则 |
|---|---|
| `X::f` 在哪里找 | 只在 `X` 里（命名空间还包括内联命名空间和 using 指令） |
| 无限定的 `f` 在哪里找 | 从内向外，第一个有 `f` 的作用域就停下，外层全被遮住 |
| ADL 什么时候做 | 无限定、不带括号的函数调用，普通查找没找到类成员、块作用域函数声明或非函数 |
| ADL 到哪里找 | 实参类型的关联命名空间，包括模板实参、基类、外围类带来的；还有关联类的友元 |
| 隐藏友元 | 只能经 ADL 找到；重载集小，不被隐式转换误选 |
| 运算符 | 成员候选 + 非成员候选（无限定查找忽略成员，加 ADL）+ 内置候选 |
| 泛型代码里交换 | `std::ranges::swap(a, b)`，或 `using std::swap; swap(a, b);` |
| 能往 std 里加什么 | 只有依赖自己类型的类模板特化等明确允许的情形，其他都是 UB |
