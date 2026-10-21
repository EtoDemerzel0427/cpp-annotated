---
title: 第三卷 · 名字查找、重载决议与访问控制
summary: 25 道题，考查作用域与遮蔽、无限定与限定查找、ADL 与隐藏友元、using 声明与 using 指令、多重继承下的成员查找、重载决议的排序与决胜规则、C++20 的比较运算符改写，以及访问控制在整个流程中的位置。
status: done
order: 3
related: basic.scope, basic.lookup, basic.lookup.argdep, class.member.lookup, namespace.udecl, namespace.udir, over.match, over.ics.rank, over.match.best, over.match.oper, class.access, class.protected, topics/name-lookup-and-customization, topics/overload-resolution-walkthrough
tags: 考卷, 名字查找, ADL, 重载决议, 访问控制
updated: 2026-10-20
---

!!! tldr
    - 考查范围：作用域与遮蔽（[[basic.scope]]），无限定、限定和实参依赖查找（[[basic.lookup]]），using 声明与 using 指令，内联命名空间，多重继承下的成员查找（[[class.member.lookup]]），重载决议（[[over.match]]、[[over.ics.rank]]），运算符的改写候选（[[over.match.oper]]），访问控制（[[class.access]]）。
    - 一条主线贯穿全卷：先名字查找，再重载决议，然后检查访问，最后才看选中的函数是不是被删除。很多题的答案取决于某个错误出现在哪一步。
    - 模板的两阶段查找、初始化与值类别、常量求值不在本卷范围内，各有单独的考卷。
    - 建议用时 90 分钟。判定题按整个程序给出最重的一项判定；选择题如果问输出，都已实际运行核对。

## 一、作用域、遮蔽与无限定查找

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

判定整个程序。

```cpp run
int count_big(int limit) {
  int n = 0;
  for (int i = 0; i < limit; ++i) {
    int limit = i * 2;
    if (limit > 10) ++n;
  }
  return n;
}

int main() { return count_big(8); }
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：良构。**

参数 `limit` 的目标作用域是函数参数作用域（[[basic.scope.param#1]]）。`for` 语句本身引入一个块作用域，它的循环体（一个复合语句）又引入一个块作用域（[[basic.scope.block#1]]）。

[[basic.scope.block#2]] 只禁止两种情况：在函数体最外层的复合语句里，重新声明与其父作用域（即参数作用域）冲突的名字（¶2.1）；在选择、循环语句的子语句里，重新声明与该语句的作用域冲突的名字（¶2.2）。循环体的父作用域是 `for` 语句的作用域，那里只有 `i`，没有 `limit`。所以循环体里的 `int limit` 只是遮蔽了参数，合法。程序返回 2（`i` 为 6 和 7 时计数）。

改一处就变成非良构：在循环体里重新声明 `i`，或者在函数体最外层重新声明 `limit`。

```cpp error
int f(int limit) { int limit = 0; return limit; }               // error: 与参数冲突（¶2.1）
void g() { for (int i = 0; i < 3; ++i) { int i = 0; (void)i; } } // error: 与 for 的 i 冲突（¶2.2）
```

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

判定整个程序。

```cpp run
struct A { static int n; };
int A::n = 0;

int main() {
  int A = 1;
  A::n = A;
  struct A* p = nullptr;
  return A::n + (p == nullptr);
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：良构，返回 2。**

局部变量 `int A` 遮蔽了类名 `A`，但三处 `A` 的查找方式不同：

1. `A::n` 里的 `A` 后面跟着 `::`。[[basic.lookup.qual.general#1]] 规定这种查找只考虑命名空间、类型和特化为类型的模板，局部变量被忽略，找到的是 `struct A`。
2. 赋值右边的 `A` 是普通的无限定查找，在块作用域里先找到 `int A`，值为 1。
3. `struct A*` 是 elaborated-type-specifier，其中名字的查找是 type-only 的（[[basic.lookup.elab#1]]），只看类型声明（[[basic.lookup.general#4]]），所以又找到 `struct A`。

去掉 `struct` 关键字，`A* p` 中的 `A` 会找到变量，整个声明被解析成表达式 `A * p`，`p` 未声明：

```cpp error
struct A { static int n; };
int main() { int A = 1; A* p = nullptr; (void)A; }   // error: p 未声明
```

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ifndr" markdown="1">

判定整个程序。

```cpp run
using T = double;

struct S {
  T scale() { return T(1) / 2; }
  using T = int;
};

int main() { return S{}.scale() == 0.5; }
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：IFNDR（非良构，不要求诊断）。**

两处 `T` 所处的上下文不同。

- 返回类型 `T` 不在**完整类上下文**（complete-class context）中。完整类上下文只包括函数体、默认实参、noexcept 说明符、契约说明符、默认成员初始化器等（[[class.mem.general#10]]）。在类作用域里查找 `T` 时，按 [[class.member.lookup#3]] 从当前位置向前搜索，此时 `S::T` 还没有声明，结果为空，于是继续到外层，找到 `::T`，即 `double`。
- 函数体里的 `T(1)` 处于完整类上下文，查找从类定义末尾开始，找到 `S::T`，即 `int`。

[[class.member.lookup#6]] 规定：在类作用域中的一次搜索，如果结果与在完整类上下文中搜索的结果不同，程序非良构，不要求诊断。返回类型处的搜索结果为空，完整类上下文中的结果是 `S::T`，二者不同。

Clang 23 不给任何诊断，按 `double scale()` 编译，函数体计算 `int(1) / 2` 得 0，`main` 返回 0。这正是 IFNDR 的含义：实现可以不报错，程序却没有意义。把 `using T = int;` 移到 `scale` 之前，两处查找都得到 `S::T`，程序良构：

```cpp ok
using T = double;
struct S {
  using T = int;
  T scale() { return T(1) / 2; }
};
int main() { return S{}.scale(); }
```

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="C" markdown="1">

程序输出什么？

```cpp run
#include <cstdio>
int x = 1;
namespace N {
  int x = 2;
  struct B { static constexpr int x = 3; };
  struct D : B { int get(); };
}
int N::D::get() { return x; }

int main() { std::printf("%d\n", N::D{}.get()); }
```

- A. `1`
- B. `2`
- C. `3`
- D. 编译失败：`x` 有歧义

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：C，输出 `3`。**

`get` 的定义写在全局作用域，但它的 declarator-id 是限定名 `N::D::get`。[[basic.scope.class#1]] 规定，这种重新声明在 declarator-id 之后的部分也属于类 `D` 的作用域。所以从函数体出发，作用域链是：块作用域、函数参数作用域、`D` 的类作用域、命名空间 `N`、全局作用域。

无限定查找逐层搜索，在第一个找到声明的作用域停下（[[basic.lookup.unqual#2]]）。搜索 `D` 的类作用域时，`D` 自己没有 `x`，于是按 [[class.member.lookup#4]] 到基类 `B` 中查找，找到 `B::x`。查找到此结束，`N::x` 和 `::x` 都不会被看到。

选 A 的理由是"函数定义写在全局作用域"，但决定查找范围的是作用域，不是文本位置。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

判定整个程序。

```cpp run
namespace A { int i = 1; }
int i = 2;

int main() {
  using namespace A;
  return i;
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：非良构，`i` 有歧义。**

using 指令不会把名字引入它所在的块作用域。[[basic.lookup.unqual#2]] 的 ¶2.2 规定：对作用域 S 做无限定搜索时，一并搜索 S 所包含的、被活跃 using 指令指定的命名空间。`A` 不包含在 `main` 的块作用域里，所以块作用域中找不到 `i`；查找到全局作用域时，全局作用域包含 `A`，于是同时搜索 `::` 和 `A`，找到 `::i` 和 `A::i`。[[namespace.udir#3]] 的注把效果概括为：`A` 的成员如同声明在同时包含该指令和 `A` 的最近命名空间中，这里就是全局命名空间。

两个声明都不是函数，指代不同实体，按 [[basic.lookup.general#1]] 属于歧义，程序非良构。

换成 using 声明，结果完全不同。using 声明在块作用域里绑定了名字 `i`，块作用域的搜索就能找到它，外层的 `::i` 被遮蔽：

```cpp ok
namespace A { int i = 1; }
int i = 2;
int main() {
  using A::i;
  return i;   // A::i，返回 1
}
```

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="B" markdown="1">

程序输出什么？

```cpp run
#include <cstdio>
namespace A { int f(int) { return 1; } }
using A::f;
namespace A { int f(char) { return 2; } }
int g() { return f('a'); }

namespace B { int h(int) { return 1; } }
using namespace B;
namespace B { int h(char) { return 2; } }
int k() { return h('a'); }

int main() { std::printf("%d%d\n", g(), k()); }
```

- A. `11`
- B. `12`
- C. `21`
- D. `22`

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：B，输出 `12`。**

using 声明命名的是它所在位置上对 `A::f` 做查找得到的那组声明（[[namespace.udecl#1]]）。那时 `A` 里只有 `f(int)`，之后再往 `A` 里添加的重载不会被它命名（[[namespace.udecl#9]] 的注里有同样的例子）。所以 `g` 里的 `f('a')` 只有一个候选 `f(int)`，返回 1。

using 指令不引入名字，它只让查找在被指定的命名空间里搜索。搜索发生在使用处，找到的是所有在使用处之前的声明（[[basic.lookup.general#3]]），包括指令之后才添加的 `B::h(char)`（[[namespace.udir#6]] 的注）。`h('a')` 的候选是 `h(int)` 和 `h(char)`，后者精确匹配，返回 2。

</details>
</div>

## 二、实参依赖查找、隐藏友元与内联命名空间

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

判定整个程序。

```cpp run
namespace N {
  struct S {};
  int f(S) { return 1; }
}
int f(int) { return 2; }

int main() {
  using ::f;
  N::S s;
  return f(s);
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：良构，调用 `N::f`，返回 1。**

[[basic.lookup.argdep#1]] 列出三种关闭 ADL 的情况：普通查找找到类成员（¶1.1）、找到位于块作用域的函数声明（¶1.2）、找到不是函数或函数模板的声明（¶1.3）。

块作用域的 `using ::f;` 看起来像是第二种情况（¶1.2），其实不是。查找找到 using 声明符后，按 [[basic.lookup.general#3]] 把它替换为它所命名的声明，也就是全局的 `f(int)`。这个声明位于全局命名空间，不在块作用域中，所以三种情况都不成立，ADL 照常进行，找到 `N::f(S)`。重载决议中 `f(int)` 不可行，选中 `N::f`。

`using std::swap; swap(a, b);` 这种写法能找到用户自己的 `swap`，靠的就是这条规则（见 [[topics/name-lookup-and-customization]]）。如果改成块作用域的函数声明，¶1.2 成立，ADL 被关闭：

```cpp error
namespace N {
  struct S {};
  int f(S) { return 1; }
}
int f(int) { return 2; }
int main() {
  int f(int);     // 块作用域函数声明，关闭 ADL
  N::S s;
  return f(s);    // error: 只有 f(int)，N::S 不能转换为 int
}
```

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="D" markdown="1">

`test` 中的四个调用，哪一个非良构？

```cpp run
namespace B {
  template<class T> struct W {};
  template<auto K>  struct Fixed {};
}
namespace A {
  struct X {};
  enum E { e };
  struct Y { int m; };
  void p(X**);
  void w(B::W<X>);
  void q(int Y::*);
  void v(B::Fixed<e>);
}

void test() {
  A::X* px = nullptr;
  B::W<A::X> wx;
  B::Fixed<A::e> fe;
  p(&px);
  w(wx);
  q(&A::Y::m);
  v(fe);
}
```

- A. `p(&px)`
- B. `w(wx)`
- C. `q(&A::Y::m)`
- D. `v(fe)`

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：D。**

四个函数都只声明在 `A` 中，`test` 里的普通查找一个也找不到，能否调用完全取决于 `A` 是不是关联命名空间。关联实体按 [[basic.lookup.argdep#3]] 逐个计算：

- A：实参类型 `A::X**`。指针的关联实体就是被指类型的关联实体（¶3.5），递归两层得到类 `A::X`，关联命名空间为 `A`。
- B：实参类型 `B::W<A::X>`，是类模板特化。除了类本身（关联到 `B`），类型模板实参 `A::X` 的关联实体也算在内（¶3.3），所以 `A` 是关联命名空间。
- C：实参类型 `int A::Y::*`，是数据成员指针。关联实体包括成员类型（`int`，没有）和类 `A::Y`（¶3.8），关联到 `A`。
- D：实参类型 `B::Fixed<A::e>`。`A::e` 是常量模板实参，[[basic.lookup.argdep#3]] 的注 3 明确指出常量模板实参不贡献关联实体。关联命名空间只有 `B`，找不到 `A::v`，调用非良构。

最容易误选的是 B：很多人以为模板实参不参与 ADL。类型模板实参参与，常量模板实参不参与。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

判定整个程序。

```cpp run
struct Meters {
  double v;
  Meters(double d) : v(d) {}
  friend Meters operator+(Meters a, Meters b) { return a.v + b.v; }
  friend double value(Meters m) { return m.v; }
};

int main() {
  Meters m = 1.0;
  Meters a = m + 2.0;
  Meters b = 2.0 + m;
  return static_cast<int>(value(a) + value(b) + value(3.0));
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：非良构，`value(3.0)` 找不到函数。**

只在类内声明的友元函数叫**隐藏友元**（hidden friend）。友元声明不绑定名字（[[dcl.meaning.general#2]] 的 ¶2.1，另见 [[class.friend#10]] 的注），所以普通的无限定查找永远找不到它，只有 ADL 能找到：[[basic.lookup.argdep#4]] 的 ¶4.2 规定，ADL 会找到关联类中声明的友元函数。

- `m + 2.0` 和 `2.0 + m`：运算符的非成员候选来自无限定查找加 ADL（[[over.match.oper#3]] 的 ¶3.2）。有一个操作数是 `Meters`，关联类是 `Meters`，找到友元 `operator+`，另一个操作数经转换构造函数变成 `Meters`。两行都合法。
- `value(a)`、`value(b)`：实参是 `Meters`，ADL 找到友元，合法。
- `value(3.0)`：实参是 `double`，基本类型没有关联实体（¶3.2），ADL 什么也找不到。普通查找也找不到，按 [[basic.lookup.general#1]] 非良构。

这正是隐藏友元的用处：至少有一个实参的类型已经是这个类时，函数才会进入候选集，不会因为某个实参恰好能隐式转换就被选中。实参先显式构造成 `Meters`，调用就合法：

```cpp ok
struct Meters {
  double v;
  Meters(double d) : v(d) {}
  friend double value(Meters m) { return m.v; }
};
int main() { return static_cast<int>(value(Meters(3.0))); }
```

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

判定整个程序。

```cpp run
namespace lib {
  inline namespace v1 {
    struct S {};
  }
  int f(S) { return 1; }

  struct T {};
  inline namespace v1 {
    int g(T) { return 2; }
  }
}

int main() {
  return f(lib::S{}) + g(lib::T{});
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：良构，返回 3。**

[[basic.lookup.argdep#4]] 规定，关联命名空间是关联实体所在的最内层**非内联**命名空间，再加上这些命名空间的内联命名空间集合中的每一个元素。内联命名空间集合是所有内联命名空间（含嵌套）的传递闭包（[[namespace.def.general#7]]）。

- `S` 声明在 `lib::v1` 中，最内层的非内联命名空间是 `lib`，关联命名空间是 `lib` 和 `lib::v1`。`f` 声明在 `lib` 中，能找到。
- `T` 声明在 `lib` 中，关联命名空间同样是 `lib` 和 `lib::v1`，`g` 声明在 `lib::v1` 中，也能找到。

两个方向都成立：[[namespace.def.general#6]] 规定，内联命名空间和它的外围命名空间只要有一个是关联命名空间，另一个也是。

内联命名空间也有代价。限定查找 `lib::f` 时，[[namespace.qual#1]] 总是同时搜索 `lib` 的内联命名空间集合，即使 `lib` 里已经有同名声明。下面两个 `f(int)` 是不同的实体，调用有歧义：

```cpp error
namespace lib {
  inline namespace v2 { int f(int) { return 2; } }
  int f(int) { return 1; }
}
int main() { return lib::f(0); }   // error: lib::f 与 lib::v2::f 歧义
```

</details>
</div>

<div class="quiz" data-kind="open" markdown="1">

下面的程序在 `#1` 处编译失败。说明候选集是怎样形成的、为什么全局的 `operator<<` 不在其中，并给出一种不需要改动 `std` 的修正方法。

```cpp run
#include <iostream>
#include <vector>

std::ostream& operator<<(std::ostream& os, const std::vector<int>& v) {
  for (int x : v) os << x << ' ';
  return os;
}

namespace app {
  struct Point { int x, y; };
  std::ostream& operator<<(std::ostream& os, const Point& p) {
    return os << p.x << ',' << p.y;
  }

  void dump(const std::vector<int>& v) {
    std::cout << v << '\n';   // #1
  }
}

int main() { app::dump({1, 2, 3}); }
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案要点：普通查找在 `app` 中找到 `operator<<` 就停下，全局版本被遮蔽；ADL 只看 `std`；两条途径都找不到全局的 `operator<<`。**

`std::cout << v` 的候选按 [[over.match.oper#3]] 形成：

1. 成员候选（¶3.1）：在 `std::ostream` 中搜索 `operator<<`，得到各种算术类型、指针等的重载，都不接受 `std::vector<int>`。
2. 非成员候选（¶3.2）：对 `operator<<` 做无限定查找，再加上 ADL。无限定查找从 `dump` 的函数体出发，搜索到命名空间 `app` 时找到 `app::operator<<(std::ostream&, const Point&)`，查找就此结束（[[basic.lookup.unqual#2]]），全局作用域不再被搜索。
3. ADL（仍属于 ¶3.2 的非成员候选）：两个操作数的类型分别是 `std::basic_ostream<char>` 和 `std::vector<int, std::allocator<int>>`，模板实参 `char`、`int` 没有关联实体，其余都在 `std` 中（[[basic.lookup.argdep#3]]）。关联命名空间只有 `std`。
4. 内建候选和改写候选与此无关。

全局的 `operator<<` 两条途径都没有被找到，候选中没有一个可行，程序非良构。Clang 列出的不可行候选里有 `app::operator<<`（`Point` 版本）和 `std` 中的各个重载，唯独没有全局版本，正好印证这一点。

修正方法之一是在 `dump` 中（或在 `app` 中）加一条 `using ::operator<<;`。using 声明把全局版本带进了无限定查找最先找到的那个作用域：

```cpp run ok
#include <iostream>
#include <vector>
std::ostream& operator<<(std::ostream& os, const std::vector<int>& v) {
  for (int x : v) os << x << ' ';
  return os;
}
namespace app {
  struct Point { int x, y; };
  std::ostream& operator<<(std::ostream& os, const Point& p) { return os << p.x << ',' << p.y; }
  void dump(const std::vector<int>& v) {
    using ::operator<<;
    std::cout << v << '\n';
  }
}
int main() { app::dump({1, 2, 3}); }
```

更稳妥的做法是不给别人的类型写运算符，把 `std::vector<int>` 包装成自己命名空间中的类型，让 ADL 能找到配套的运算符。把这个重载加进 `std` 则不行：向 `std` 添加声明是未定义行为（[[namespace.std#1]]）。

</details>
</div>

## 三、类成员查找与访问控制

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

判定整个程序。

```cpp run
struct A { int f(int)    { return 1; } };
struct B { int f(double) { return 2; } };
struct C : A, B {};

int main() {
  C c;
  return c.f(1);
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：非良构，`f` 的成员查找有歧义。**

名字查找先于重载决议（[[basic.lookup.general#1]]），而成员查找不会把不同基类中的同名函数合并成一个重载集。按 [[class.member.lookup]] 计算 S(f, C)：

1. `C` 自身没有 `f`，于是依次合并两个直接基类的查找集（¶4）。
2. S(f, A) = {{`A::f`}, {A}}，S(f, B) = {{`B::f`}, {B}}。
3. 合并时，两个子对象互不为对方的基类子对象，声明集又不同，结果是无效集（¶5.2）。
4. ¶6：查找结果是无效集，程序非良构。

`f(int)` 对实参 `1` 是精确匹配，重载决议本可以选出它，但重载决议根本没有机会开始。在 `C` 中用 using 声明把两个 `f` 引入同一个作用域，查找在 `C` 本身就找到两个声明（¶3），重载决议再选出 `A::f`：

```cpp ok
struct A { int f(int)    { return 1; } };
struct B { int f(double) { return 2; } };
struct C : A, B { using A::f; using B::f; };
int main() { C c; return c.f(1); }   // 调用 A::f，返回 1
```

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

判定整个程序。

```cpp run
class B { public: int v = 0; };
class D : private B {};

class E : public D {
  void reset() {
    B b;
    b.v = 1;
  }
};

int main() {}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：非良构，`B` 不可访问。**

`E::reset` 里的 `B` 是无限定名。查找经过 `E` 的类作用域时，按成员查找规则搜索基类，在 `D` 的基类 `B` 中找到 `B` 的**注入类名**（injected-class-name），即类名在自身类作用域中的绑定（[[class.pre#2]]）。查找到此停止，全局的 `::B` 没有机会被找到。

注入类名在访问检查中视为 `B` 的公有成员（[[class.pre#2]]）。它经私有继承成为 `D` 的私有成员（[[class.access.base#1]]），作为 `E` 的成员则不可访问。查找是在 `E` 的作用域中进行的，指名类是 `E`，按 [[class.access.base#5]] 逐条检查：¶5.4 到 ¶5.6 不成立；¶5.7 要求经某个在此处可访问的基类指名时可访问，经 `D` 指名时它是 `D` 的私有成员，而 `reset` 不是 `D` 的成员或友元；`B` 本身作为 `E` 的基类在此处不可访问（[[class.access.base#4]]）。所以访问非良构。

`b.v` 本身没有问题。[[class.access.base#3]] 的例子正是这个情形：通过 `::B` 显式指名全局的类，查找不经过 `E` 的类作用域，访问合法：

```cpp ok
class B { public: int v = 0; };
class D : private B {};
class E : public D {
  void reset() { ::B b; b.v = 1; }   // OK: ::B 不经过继承链
};
int main() {}
```

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

判定整个程序。`main` 只调用了公有的 `f(int)`。

```cpp run
class Base {
public:
  int f(int) { return 1; }
private:
  int f(char) { return 2; }
};

class Derived : public Base {
public:
  using Base::f;
};

int main() {
  Derived d;
  return d.f(0);
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：非良构，错误在 using 声明本身。**

普通调用中，访问控制只施加于重载决议选中的那个函数（[[class.access.general#4]]）。using 声明另有规定：[[namespace.udecl#14]] 要求，不命名构造函数的 using 声明符所命名的**每一个**声明都必须可访问。`Base::f(char)` 是 `Base` 的私有成员，在 `Derived` 中不可访问，因此 `using Base::f;` 非良构，与之后调用哪个重载无关。[[namespace.udecl#16]] 的例子是同一种情形。

把私有改成受保护，结论就变了：受保护成员在 `Derived` 的成员声明中可访问，using 声明合法，而且它位于 `public` 区，按 [[namespace.udecl#16]] 有普通成员声明的访问性。于是原本受保护的 `f(char)` 在 `Derived` 中成了公有的同义名，外部也能调用：

```cpp ok
class Base {
public:
  int f(int) { return 1; }
protected:
  int f(char) { return 2; }
};
class Derived : public Base {
public:
  using Base::f;
};
int main() {
  Derived d;
  return d.f('a');   // OK: 调用 Base::f(char)，返回 2
}
```

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

判定整个程序。

```cpp run
class Base {
protected:
  int n = 0;
};

class Derived : public Base {
public:
  void copy_from(const Base& other) { n = other.n; }
};

int main() {
  Derived a, b;
  a.copy_from(b);
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：非良构，`other.n` 违反受保护成员的附加规则。**

先看一般规则：`other.n` 的指名类是 `Base`（[[class.access.base#5]] 的 ¶5.2），`n` 作为 `Base` 的成员是受保护的，访问发生在派生类 `Derived` 的成员中，按 ¶5.6 本来可以访问。

但 [[class.protected#1]] 对非静态成员另加一条检查：访问之所以被允许，是因为它出现在某个类 C（这里是 `Derived`）的成员或友元中；如果访问经过对象表达式，对象表达式的类必须是 C 或 C 的派生类。`other` 的类型是 `Base`，不满足，访问非良构。左边的 `n` 是 `this->n`，对象表达式的类是 `Derived`，没有问题。

这条规则的理由是：`Derived` 只应该能访问自己这一支继承体系中的 `Base` 部分。`other` 实际上可能是另一个毫不相干的派生类 `Other : Base` 的对象。

参数改成 `const Derived&` 就合法。静态成员不受这条附加规则约束；形成成员指针时，要通过 `&Derived::n` 指名：

```cpp ok
class Base { protected: int n = 0; static int s; };
int Base::s = 0;
class Derived : public Base {
public:
  void copy_from(const Derived& other) { n = other.n + Base::s; }
  int Base::* pm() { return &Derived::n; }   // 类型是 int Base::*
};
int main() { Derived a, b; a.copy_from(b); }
```

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="A" markdown="1">

下面哪一个成员函数的函数体非良构？

```cpp run
class A {
  int secret = 0;
  friend struct F;
};
struct B : A {};

struct F {
  int a(A& x) { return x.secret; }
  int b(B& x) { return x.secret; }
  int d(A& x) {
    struct Local { static int get(A& y) { return y.secret; } };
    return Local::get(x);
  }
};
struct G : F {
  int c(A& x) { return x.secret; }
};
```

- A. `G::c`
- B. `F::b`
- C. `F::d` 中的 `Local::get`
- D. 都良构

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：A。**

- `G::c`：`G` 派生自友元 `F`，但友元关系既不继承也不传递（[[class.friend#9]]）。`G` 不是 `A` 的友元，`secret` 不可访问。
- `F::b`：指名类是 `B`。`secret` 是 `A` 的私有成员，作为 `B` 的成员不可访问，但 [[class.access.base#5]] 的 ¶5.7 还给了一条路：`A` 是 `B` 的基类，在此处可访问（公有继承，[[class.access.base#4]] 的 ¶4.1），并且 `secret` 以 `A` 为指名类时可访问（`F` 是 `A` 的友元，¶5.5）。另外 ¶6 要求 `x` 能隐式转换为指向指名类 `B` 的指针，显然满足。合法，这和 ¶5 的例 4 是同一种情形。
- `Local::get`：成员函数中的局部类可以访问该成员函数能访问的所有成员（[[class.access.general#2]]），`F::d` 能访问 `secret`，`Local` 也能。

如果 `B` 改为私有继承（`class B : A {};`），`F::b` 也会非良构：`A` 作为 `B` 的私有基类，在 `F` 中不可访问，¶5.7 不再成立。

</details>
</div>

<div class="quiz" data-kind="open" markdown="1">

写出 S(id, D) 的计算过程，说明 `probe()` 返回什么。再回答：如果把两处 `virtual` 都去掉，或者只去掉 `R` 的那一处，结果分别如何？

```cpp run
#include <cstdio>
struct V { int id() { return 1; } };
struct L : virtual V { int id() { return 2; } };
struct R : virtual V { };
struct D : L, R {
  int probe() { return id(); }
};
int main() { std::printf("%d\n", D{}.probe()); }
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案要点：原程序找到 `L::id`，输出 `2`；去掉两处或只去掉 `R` 的 `virtual`，查找都有歧义，程序非良构。**

按 [[class.member.lookup]] 计算：

1. `D` 本身没有 `id`，依次合并 S(id, L) 和 S(id, R)（¶4）。
2. S(id, L) = {{`L::id`}, {L}}：`L` 自己声明了 `id`（¶3）。
3. S(id, R)：`R` 没有 `id`，取其基类 `V` 的结果，得到 {{`V::id`}, {V}}。这里的 V 是虚基类子对象，全对象 `D` 中只有一个。
4. 合并：中间结果先是 S(id, L) 的副本。再并入 S(id, R) 时，它的子对象集只有那个共享的 V，而 V 正是 L 子对象的基类子对象，按 ¶5.1 中间结果保持不变。

结果是 `L::id`，`probe()` 返回 2。这就是 ¶9 的注所说的情形：`L::id` 遮蔽了 `V::id`，而经 `R` 到达 `V::id` 的路径不经过 `L`，这不算歧义，因为两条路径到达的是同一个 V 子对象。

去掉两处 `virtual` 后，`D` 中有两个 V 子对象。S(id, R) 的子对象是 R 中的那个 V，它不是 L 的基类子对象，L 也不是它的基类子对象，两个声明集不同（`L::id` 对 `V::id`），按 ¶5.2 得到无效集，¶6 判为非良构。

只去掉 `R` 的 `virtual` 也一样：`R` 中的 V 是一个独立的非虚子对象，同样不是 L 的基类子对象，查找有歧义。Clang 对后两种情况都报 `member 'id' found in multiple base classes of different types`。

</details>
</div>

## 四、重载决议与运算符改写

<div class="quiz" data-kind="choice" data-answer="B" markdown="1">

程序输出什么（每次调用占一行）？

```cpp run
#include <cstdio>
void f(bool)  { std::puts("bool"); }
void f(void*) { std::puts("void*"); }
void f(long)  { std::puts("long"); }

int main() {
  int x = 0;
  f(&x);
  f(nullptr);
  f(0L);
}
```

- A. `bool` / `bool` / `long`
- B. `void*` / `void*` / `long`
- C. `void*` / `bool` / `long`
- D. 编译失败，`f(nullptr)` 有歧义

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：B。**

- `f(&x)`：`int*` 到 `void*` 是指针转换（[[conv.ptr#2]]），`int*` 到 `bool` 是布尔转换（[[conv.bool#1]]），两者都是转换等级（[[over.ics.scs#3]]）。[[over.ics.rank#4]] 的 ¶4.1 规定，不把指针转换为 `bool` 的转换更好，所以选 `f(void*)`。`f(long)` 不可行。
- `f(nullptr)`：`nullptr` 到 `void*` 是空指针转换（[[conv.ptr#1]]）。[[conv.bool#1]] 的源类型不包括 `std::nullptr_t`；`nullptr_t` 到 `bool` 只在直接初始化中允许（[[dcl.init.general#15]] 的 ¶15.8），而形参初始化是复制初始化，所以 `f(bool)` 不可行，只剩 `f(void*)`。
- `f(0L)`：`long` 到 `long` 是恒等转换，精确匹配。

选 C 的人以为 `nullptr` 能隐式转换为 `bool`。对照一下 `0`：它是空指针常量，到 `void*`、`bool`、`long` 都是转换等级，¶4.1 只管指针到 `bool` 的转换，帮不上忙，调用歧义。`NULL` 是实现定义的空指针常量（[[support.types.nullptr#2]]），结果随实现而变：本机的 Clang 23 加 libc++ 上 `f(NULL)` 选中 `f(long)`。

```cpp error
void f(bool); void f(void*); void f(long);
void g() { f(0); }     // error: 三个候选都是转换等级，歧义
```

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

判定整个程序。

```cpp run
struct Flags {
  int mode : 3;
};
int load(int& r)  { return r; }
int load(long v)  { return static_cast<int>(v); }

int main() {
  Flags fl{2};
  return load(fl.mode);
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：非良构。**

形成隐式转换序列时只看类型、cv 限定和值类别，不看实参是不是位域（[[over.best.ics.general#2]] 的注 1）。[[over.ics.ref#4]] 专门举了这个例子：`int&` 形参对 `int` 位域左值，转换序列照样是恒等转换（[[over.ics.ref#1]] 的 ¶1.2），`load(int&)` 可行而且是精确匹配。`load(long)` 需要整型转换，是转换等级。重载决议选中 `load(int&)`。

选中之后才真正初始化引用：[[dcl.init.ref#5]] 的 ¶5.1.1 排除了位域，接下来 ¶5.2 规定非 const 左值引用在这种情况下非良构。所以本可以合法调用的 `load(long)` 被一个注定失败的候选挤掉了。

把引用改成 `const int&`，引用绑定到一个临时量，转换序列仍是精确匹配，程序良构，返回 2：

```cpp ok
struct Flags { int mode : 3; };
int load(const int& r) { return r; }
int load(long v)       { return static_cast<int>(v); }
int main() { Flags fl{2}; return load(fl.mode); }
```

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="C" markdown="1">

程序输出什么？

```cpp run
#include <cstdio>
template<class T> int f(T)  { return 1; }
int f(const int&)           { return 2; }

template<class T> int g(T&) { return 1; }
int g(const int&)           { return 2; }

int main() {
  int x = 0;
  std::printf("%d%d\n", f(x), g(x));
}
```

- A. `11`
- B. `12`
- C. `21`
- D. `22`

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：C，输出 `21`。**

非模板优先的决胜规则（[[over.match.best.general#2]] 的 ¶2.4）只在每个实参的转换序列都打平时才起作用。

- `f(x)`：模板推导出 `f<int>(int)`，`int` 左值到 `int` 只需左值到右值转换，属于精确匹配。`f(const int&)` 直接绑定到 `int` 左值，按 [[over.ics.ref#1]] 的 ¶1.2 是恒等转换。比较时排除左值转换（[[over.ics.rank#3]] 的 ¶3.2.1），两者都是恒等；¶3.2.6 只在两边都是引用绑定时适用，这里一边是值形参。转换序列不分高下，¶2.4 让非模板 `f(const int&)` 胜出，得 2。
- `g(x)`：模板推导出 `g<int>(int&)`。现在两边都是引用绑定，¶3.2.6 规定绑定 cv 限定较少的引用更好，`int&` 胜过 `const int&`。模板在转换序列上就赢了，决胜规则用不上，得 1。

同一节的 ¶3.2.3 处理另一种引用之争：右值实参绑定右值引用优于绑定左值引用。比如 `void h(const int&); void h(int&&);`，`h(0)` 选 `h(int&&)`。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

判定整个程序。

```cpp run
struct Num {
  operator int() const    { return 1; }
  operator double() const { return 2.0; }
};
int use(int)    { return 1; }
int use(double) { return 2; }

int main() { return use(Num{}); }
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：非良构，调用有歧义。**

两个候选的实参都需要用户定义转换序列，它由一个标准转换序列、一次用户定义转换和第二个标准转换序列组成（[[over.ics.user#1]]）。

1. 对 `use(int)`：用 `Num` 初始化 `int` 时，`operator int` 和 `operator double` 都是候选转换函数（[[over.match.conv#1]]）。前者之后无需转换，后者之后还要浮点到整型的转换，按 [[over.match.best.general#2]] 的 ¶2.2 选 `operator int`。转换序列是 U(`operator int`，恒等)。
2. 对 `use(double)`：同理得到 U(`operator double`，恒等)。
3. 比较两个用户定义转换序列：[[over.ics.rank#3]] 的 ¶3.3 只在两者使用**同一个**转换函数时才比较第二个标准转换。这里转换函数不同，两个序列不分高下，又没有别的实参可比，调用歧义。

容易误以为两边的第二个标准转换都是恒等，`use(int)` 又和 `operator int` 正好对应，总该选它。但 ¶3.3 只比较同一个转换函数后面的标准转换，不同转换函数之间没有可比的依据。只有一个转换函数时，¶3.3 才起作用：

```cpp ok
struct Num { operator short() const { return 1; } };
int use(int)    { return 1; }
int use(double) { return 2; }
int main() { return use(Num{}); }   // short→int 是提升，优于 short→double，选 use(int)
```

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

判定整个程序。

```cpp run
#include <initializer_list>
struct Vec {
  Vec(int, int) {}
  Vec(std::initializer_list<double>) {}
};

int main() {
  int a = 1, b = 2;
  Vec v{a, b};
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：非良构，`a`、`b` 到 `double` 是窄化转换。**

`Vec` 不是聚合，列表初始化按 [[dcl.init.list#3]] 的 ¶3.7 考虑构造函数，具体分两个阶段（[[over.match.list#1]]）：

1. 初始化列表非空，先只拿初始化列表构造函数做候选，把整个列表作为一个实参（¶1.1）。`int` 能隐式转换为 `double`，`Vec(std::initializer_list<double>)` 可行（[[over.ics.list#5]]），第一阶段就选中它。
2. 只有第一阶段找不到可行的初始化列表构造函数，才会把所有构造函数连同拆开的元素再做一次重载决议（¶1.2）。`Vec(int, int)` 根本没有参与比较。

选中之后用元素初始化 `const double` 的后备数组。整型到浮点是窄化转换，除非源是常量表达式且值能精确表示（[[dcl.init.list#7]] 的 ¶7.3）。`a`、`b` 不是常量表达式，按 [[dcl.init.list#5]] 程序非良构。窄化与否不影响可行性，只在选定之后检查。

写成 `Vec v{1, 2};` 时字面量是常量表达式，不窄化，仍然调用初始化列表构造函数；写成圆括号 `Vec v(a, b);` 则不进入列表初始化，调用 `Vec(int, int)`：

```cpp ok
#include <initializer_list>
struct Vec { Vec(int, int) {} Vec(std::initializer_list<double>) {} };
int main() {
  Vec v{1, 2};        // initializer_list<double>，常量不窄化
  int a = 1, b = 2;
  Vec u(a, b);        // Vec(int, int)
}
```

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="B" markdown="1">

用 `-std=c++2c` 编译，程序输出什么？

```cpp run
#include <cstdio>
struct Id {
  int v;
  Id(int x) : v(x) {}
  bool operator==(const Id& o) const {
    std::printf("this=%d o=%d\n", v, o.v);
    return v == o.v;
  }
};

int main() {
  bool b = 1 == Id(2);
  std::printf("%d\n", b);
}
```

- A. `this=1 o=2` / `0`
- B. `this=2 o=1` / `0`
- C. 编译失败：成员 `operator==` 要求左操作数是 `Id`
- D. 编译失败：两种解释有歧义

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：B。**

按 [[over.match.oper#3]] 列出 `1 == Id(2)` 的候选：

1. 成员候选（¶3.1）：左操作数是 `int`，不是类类型，成员候选为空。不能把 `1` 先转换成 `Id` 再调用成员函数，因为隐式对象形参不接受用户定义转换（[[over.best.ics.general#9]]）。
2. 非成员候选（¶3.2）：查找 `operator==` 时忽略成员函数，什么也找不到。
3. 内建候选：`Id` 不能转换为算术类型，`int == int` 等都不可行。
4. 改写候选（¶3.4.4）：对 `y == x`，即 `Id(2) == 1`，取其非改写候选 `Id::operator==`，合成一个参数顺序颠倒的候选。`Id` 中没有对应的 `operator!=`，所以它是改写目标（¶4）。合成候选的第一个形参 `const Id&` 接受 `1`（经转换构造函数），第二个形参是对象形参，接受 `Id(2)`。可行。

只有这一个可行候选。按 [[over.match.oper#10]] 的 ¶10.3，`x == y` 被解释为 `y == x`，即 `Id(2).operator==(Id(1))`，所以打印 `this=2 o=1`，结果为假。

选 A 的人以为 `1` 会变成左边的对象。选 C 是 C++17 的答案：用 `-std=c++17` 编译，Clang 报 `invalid operands to binary expression ('int' and 'Id')`。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

判定整个程序（按标准判定，不考虑编译器扩展）。

```cpp run
struct S {
  int v;
  bool operator==(const S& o) { return v == o.v; }
};

int main() {
  S a{1}, b{1};
  return a == b;
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：非良构，`a == b` 有歧义。Clang 作为扩展接受，只给警告。**

`operator==` 没有声明为 `const`。候选有两个（[[over.match.oper#3]]）：

- 普通成员候选 `a.operator==(b)`：形参依次是隐式对象形参 `S&`（[[over.match.funcs.general#4]]）和 `const S&`。
- 颠倒的合成候选，来自 `b == a` 的成员候选（¶3.4.4）：形参依次是 `const S&`（接受 `a`）和对象形参 `S&`（接受 `b`）。

逐个实参比较（[[over.ics.rank#3]] 的 ¶3.2.6，绑定 cv 限定较少的引用更好）：

| 实参 | 普通候选 | 颠倒候选 | 谁更好 |
|---|---|---|---|
| `a` | `S&` | `const S&` | 普通候选 |
| `b` | `const S&` | `S&` | 颠倒候选 |

两边各赢一个实参，按 [[over.match.best.general#2]] 谁也不比谁好。¶2.8 让非改写候选优先，但前提是它在每个实参上都不差，这里不满足。没有唯一的最佳函数，程序非良构（[[over.match.best.general#3]]）。

Clang 23 只给出 `-Wambiguous-reversed-operator` 警告（ISO C++20 considers use of overloaded operator '==' ... to be ambiguous），照常编译；加 `-pedantic-errors` 才变成错误。这是 Clang 有意保留的兼容扩展，不是标准的结论。

两种修正：把成员函数声明为 `const`，两个候选在每个实参上都打平，¶2.8 选非改写候选；或者按 [[over.match.oper#4]] 提供对应的 `operator!=`，`operator==` 就不再是改写目标，不会生成颠倒候选：

```cpp ok
struct S {
  int v;
  bool operator==(const S& o) { return v == o.v; }
  bool operator!=(const S& o) { return v != o.v; }
};
int main() { S a{1}, b{1}; return a == b; }
```

提供了 `operator!=` 就不生成颠倒候选，这条规则来自 [[P2468R2]]，目的是让这类 C++20 之前的代码继续可用。

</details>
</div>

<div class="quiz" data-kind="open" markdown="1">

对 `use` 中的四个调用，分别给出判定，并说明错误（如果有）出在名字查找、重载决议、访问检查、删除检查中的哪一步。

```cpp run
class Widget {
public:
  void set(long) {}
  void set(double) = delete;
private:
  void set(int) {}
};

void use(Widget& w) {
  w.set(1L);     // #1
  w.set(1.0f);   // #2
  w.set('c');    // #3
  w.set(1u);     // #4
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案要点：#1 良构；#2 选中被删除的函数；#3 选中私有函数；#4 重载决议歧义。**

顺序由 [[basic.lookup.general#1]] 规定：先名字查找，再重载决议，再检查访问。被删除的函数直到被选中才会出错（[[dcl.fct.def.delete#2]]）。

- 名字查找：在 `Widget` 中找到三个 `set`，不管它们是不是私有、是不是被删除。访问控制不影响查找（[[class.access.general#5]]）。
- 重载决议：形成转换序列时，访问性和删除与否都被忽略（[[over.best.ics.general#2]] 的注 1），三个函数都参与比较。

逐个调用：

1. `w.set(1L)`：`long` 精确匹配 `set(long)`，公有，未删除，良构。
2. `w.set(1.0f)`：`float` 到 `double` 是浮点提升，到 `long`、`int` 是浮点整型转换。提升胜出，选中 `set(double)`。访问检查通过，但它是被删除的函数，非良构。这正是 `= delete` 用来挡住某类实参的写法。即使出现在 `decltype(w.set(1.0f))` 这样的不求值语境中，也同样非良构（[[dcl.fct.def.delete#2]] 的注 1）。
3. `w.set('c')`：`char` 到 `int` 是整型提升，到 `long`、`double` 是转换，选中 `set(int)`。它是私有的，访问检查只针对这个被选中的函数（[[class.access.general#4]]），非良构。并不会因为它不可访问就退而选择公有的 `set(long)`。
4. `w.set(1u)`：`unsigned int` 到 `int`、`long` 是整型转换，到 `double` 是浮点整型转换，三者都是转换等级，[[over.ics.rank#4]] 的几条细分规则都不适用，重载决议歧义，在第二步就失败。

</details>
</div>

## 考查条款一览

| 题号 | 考查点 | 条款 |
|---|---|---|
| 1 | 块作用域中重新声明参数与循环变量 | [[basic.scope.block#2]] |
| 2 | `::` 前与 elaborated-type-specifier 中只看类型 | [[basic.lookup.qual.general#1]]、[[basic.lookup.elab#1]] |
| 3 | 类作用域查找结果与完整类上下文不一致 | [[class.member.lookup#6]]、[[class.mem.general#10]] |
| 4 | 类外定义的成员函数的作用域链 | [[basic.scope.class#1]]、[[basic.lookup.unqual#2]] |
| 5 | using 指令的名字出现在最近的共同命名空间 | [[basic.lookup.unqual#2]]、[[namespace.udir#3]] |
| 6 | using 声明只命名当时已有的重载 | [[namespace.udecl#1]]、[[namespace.udecl#9]] |
| 7 | 块作用域 using 声明不关闭 ADL | [[basic.lookup.argdep#1]]、[[basic.lookup.general#3]] |
| 8 | ADL 的关联实体，常量模板实参不参与 | [[basic.lookup.argdep#3]] |
| 9 | 隐藏友元只能经 ADL 找到 | [[basic.lookup.argdep#4]]、[[dcl.meaning.general#2]] |
| 10 | 内联命名空间与关联命名空间 | [[basic.lookup.argdep#4]]、[[namespace.def.general#6]]、[[namespace.qual#1]] |
| 11 | 运算符查找被内层声明遮蔽 | [[over.match.oper#3]]、[[basic.lookup.unqual#2]] |
| 12 | 多个基类中的同名成员导致查找歧义 | [[class.member.lookup#5]]、[[class.member.lookup#6]] |
| 13 | 经私有基类找到的注入类名不可访问 | [[class.pre#2]]、[[class.access.base#5]] |
| 14 | using 声明要求命名的每个声明都可访问 | [[namespace.udecl#14]]、[[namespace.udecl#16]] |
| 15 | 受保护成员的附加访问检查 | [[class.protected#1]] |
| 16 | 友元不继承；经派生类访问基类的私有成员 | [[class.friend#9]]、[[class.access.base#5]]、[[class.access.general#2]] |
| 17 | 虚基类下的遮蔽与查找集合并 | [[class.member.lookup#5]]、[[class.member.lookup#9]] |
| 18 | 指针到 `bool` 的转换，`nullptr` 不能复制初始化 `bool` | [[over.ics.rank#4]]、[[conv.bool#1]]、[[dcl.init.general#15]] |
| 19 | 位域实参与非 const 引用形参 | [[over.ics.ref#4]]、[[dcl.init.ref#5]] |
| 20 | 引用绑定的排序与非模板优先 | [[over.ics.rank#3]]、[[over.match.best.general#2]] |
| 21 | 不同转换函数的用户定义转换序列不可比较 | [[over.ics.rank#3]]、[[over.match.conv#1]] |
| 22 | 初始化列表构造函数优先，窄化在选定后检查 | [[over.match.list#1]]、[[dcl.init.list#5]] |
| 23 | `==` 的颠倒改写候选 | [[over.match.oper#3]]、[[over.match.oper#10]] |
| 24 | 非 const 的 `operator==` 与颠倒候选的歧义 | [[over.match.best.general#2]]、[[over.match.oper#4]] |
| 25 | 查找、重载决议、访问检查、删除检查的顺序 | [[basic.lookup.general#1]]、[[class.access.general#4]]、[[dcl.fct.def.delete#2]] |
