---
title: 更简单的隐式移动（P1825、P2266）
summary: return x; 什么时候移动而不是复制：从 C++11 借用复制消除条件的两阶段重载决议，到 CWG1579 和 P1825 逐步放宽，再到 C++23 的 P2266 把被返回的名字直接定为 xvalue，以及每一步改变了哪些代码的含义。
status: draft
order: 18
group: 核心语言
since: c++11
papers: CWG1579, P0527R1, P1155R3, P1825R0, P2266R3, LWG2993
related: expr.prim.id.unqual, class.copy.elision, basic.lval, dcl.type.auto.deduct, stmt.return, expr.throw, diff.cpp17.class, diff.cpp20.expr, topics/special-members-and-elision, topics/value-categories, perf/copies-and-moves, history/move-semantics, topics/dangling-references
tags: 隐式移动, 值类别, xvalue, 复制消除, return, 提案
updated: 2026-10-19
---

!!! tldr
    - 隐式移动指 `return x;`、`throw x;` 不写 `std::move` 也会移动局部变量 `x`。它补的是复制消除没有发生时的那一次初始化。
    - C++11 到 C++20 的规则是两阶段重载决议：先把 `x` 当右值决议一次，不行再当左值决议一次。CWG1579 和 P1825 只是不断放宽第一阶段的适用范围。
    - C++23 的 P2266 去掉了两阶段：在 `return`、`co_return`、`throw` 的操作数里，指代可隐式移动实体的名字本身就是 xvalue，只做一次重载决议。
    - 代价是一批旧代码改变含义：`int& f(int&& x) { return x; }` 变成非良构，`decltype(auto)` 配 `return (x);` 推出 `T&&`。这些不兼容被明确接受，并写进了 Annex C。
    - P1825 被实现当作缺陷报告应用到所有旧模式；P2266 不是缺陷报告，Clang 只在 `-std=c++23` 及以后启用它。

## 同一行 `return x;` 的五种结局

下面这些函数都只写了 `return 名字;`。`W` 是一个有复制和移动构造函数的类，`Der` 从 `W` 公有派生：

| 函数 | C++11 原始措辞 | 加上 CWG1579 | C++20（P1825） | C++23（P2266） |
|---|---|---|---|---|
| `W f() { W w; return w; }` | 移动 | 移动 | 移动 | 移动 |
| `unique_ptr<B> f() { unique_ptr<D> p; return p; }` | 非良构 | 移动 | 移动 | 移动 |
| `W f() { Der d; return d; }` | 复制 | 复制 | 移动 | 移动 |
| `W f(W&& r) { return r; }` | 复制 | 复制 | 移动 | 移动 |
| `void f(W w) { throw w; }` | 复制 | 复制 | 移动 | 移动 |
| `W&& f(W&& r) { return r; }` | 非良构 | 非良构 | 非良构 | 良构 |
| `int& f(int&& r) { return r; }` | 良构 | 良构 | 良构 | 非良构 |

第一行的移动还可以被复制消除（NRVO）省掉，这里只说没有省略时用哪个构造函数。表中每一格都由当时的标准措辞决定，下文逐步解释。

用今天的编译器只能看到其中一部分：CWG1579 和 P1825 被当作缺陷报告，Clang 23 在 `-std=c++11` 下也已经按 C++20 的规则移动；只有最后两行会随 `-std=c++20` 和 `-std=c++23` 而变化。

先区分两个经常混在一起的机制。**复制消除**（[[g:copy-elision|copy elision]]）决定一次初始化能不能整个省掉，见 [[class.copy.elision#1]] 和 [[papers/guaranteed-copy-elision|保证的复制消除]]。**隐式移动**决定这次初始化没有省掉时，源对象被当作左值还是右值，从而选中复制还是移动构造函数。本页讲的是后者。

## C++11：借用复制消除的条件

C++11 引入右值引用后，按值返回只能移动的类型（如 `std::unique_ptr`）需要 `return p;` 能自动移动，否则每处都要写 `std::move`。C++11 的规则写在复制消除那一条里（当时的 [class.copy]/32），大意是：

1. 如果复制消除的条件满足，或者只差源对象是函数形参这一点，就先把源对象当作右值做一次重载决议，挑选构造函数；
2. 如果这次决议失败，或者选中的构造函数的第一个形参不是该对象类型的右值引用，就把它当作左值重新决议一次。

这就是**两阶段重载决议**（two-stage overload resolution）。第二阶段是一张安全网：右值决议找不到合适的移动构造函数时，退回到 C++03 的行为，原来能编译的代码照样选中复制构造函数。

问题在于第 1 步借用了复制消除的条件，而 NRVO 要求被返回对象与返回类型是同一个类型（忽略 cv）。类型一旦不同，隐式移动就不发生：

```cpp title="cwg1579.cpp" run std=c++11 ok
#include <memory>
struct B { virtual ~B() = default; };
struct D : B {};

std::unique_ptr<B> f() {
  std::unique_ptr<D> p(new D);
  return p;   // C++11 原始措辞：p 是左值，
}             // 只能复制，而 unique_ptr 不可复制
int main() { return f() ? 0 : 1; }
```

`unique_ptr<B>` 的转换构造函数接受 `unique_ptr<D>&&`，左值绑不上去；复制构造函数被弃置。按 C++11 的原始措辞，这个函数非良构，程序员必须写 `return std::move(p);`。

### CWG1579：不再要求同一类型

[[CWG1579]] 把条件从复制消除中独立出来：只要 `return` 的操作数是一个（可加括号的）*id-expression*，指名函数体或形参列表里声明的自动存储期对象，就先按右值决议。这样 `optional<T> f() { T t; return t; }` 能用 `optional(T&&)`，上面的 `unique_ptr` 例子也成了移动。它作为缺陷报告并入 C++14，本机 Clang 23 在 `-std=c++11` 下就接受上面的程序。

不过第 2 步的那句限制原样保留：选中的构造函数的第一个形参必须是该对象类型的右值引用，否则仍然退回左值。于是 `W f() { Der d; return d; }` 第一阶段选中 `W(W&&)`，形参是 `W&&` 而不是 `Der&&`，判为不合格，重新决议后复制。

## C++20：P1825 补上四个缺口

[[P1825R0]] 本身只是一份措辞，合并了两篇各自通过的提案：[[P0527R1]] 和 [[P1155R3]]。它们分别从两个方向放宽规则。

### 右值引用类型的变量（P0527）

```cpp title="rref.cpp" run ok
#include <memory>
std::unique_ptr<int> f(std::unique_ptr<int>&& p) {
  return p;   // C++20 起移动；此前 p 是引用而非对象，只能复制
}
int main() { return *f(std::make_unique<int>(0)); }
```

C++20 之前，隐式移动只针对对象，`p` 是引用，不在其列，上面的函数非良构。P0527 的理由是：一个右值引用变量要么绑定到一个 prvalue（临时对象），要么调用方显式写了 `std::move` 一类的转换，无论哪种，从它移动都是调用方已经同意的。为此它引入了术语**可隐式移动的实体**（[[g:implicitly-movable-entity|implicitly movable entity]]）：自动存储期的变量，或者是非 volatile 对象，或者是指向非 volatile 对象类型的右值引用。

P0527 还把 `throw` 和 `return` 统一起来：函数形参和 `catch` 子句的形参在 `throw` 中也可以隐式移动。原来的措辞把它们排除在外，因为它们不能做复制消除。

这一放宽对调用方是可观察的。被调函数 `return s;` 时，调用方的对象被掏空：

```cpp title="consume.cpp" run ok
#include <cstdio>
#include <string>
#include <utility>

std::string consume(std::string&& s) {
  return s;   // 移动，不是复制
}

int main() {
  std::string s(100, 'x');
  std::string t = consume(std::move(s));
  std::printf("%zu %zu\n", t.size(), s.size());
}
```

本机 Clang 23（libc++）在 `-std=c++11` 到 `-std=c++23` 下都输出 `100 0`。`s` 处于有效但未指定的状态，libc++ 把它清空了。Annex C 的 [[diff.cpp17.class#3]] 用一个自定义类型给出了同样的例子：被移动后的指针成员变成空指针，调用方原来合法的解引用变成未定义行为。

### 去掉第一个形参的限制（P1155）

P1155 列出了 C++17 措辞下四种违背直觉的复制，并指出它们各自来自原措辞里的哪一个词：

| 写法 | C++17 措辞 | 原因 |
|---|---|---|
| `void f(W w) { throw w; }` | 复制 | `throw` 排除了函数形参 |
| `W f() { To t; return t; }`，`To` 有 `operator W() &&` | 复制 | 只考虑构造函数，不考虑转换函数 |
| `Fowl f() { W w; return w; }`，`Fowl(W)` 按值接收 | 复制 | 形参不是右值引用 |
| `W f() { Der d; return d; }` | 复制 | 形参不是该对象类型的右值引用 |

P1825 删掉了第 2 步里关于第一个形参的整句话。从此规则变成：第一阶段把操作数当右值决议，只要决议成功就用它的结果，选中转换函数、按值形参的构造函数、基类的移动构造函数都可以；第一阶段失败才退回左值。

```cpp title="more-moves.cpp" run std=c++20 ok
#include <cstdio>
struct W {
  W() {}
  W(const W&) { std::puts("copy"); }
  W(W&&) { std::puts("move"); }
};
struct Der : W {};
struct Fowl { Fowl(W) {} };
struct To {
  operator W() const& { std::puts("conv&"); return W(); }
  operator W() && { std::puts("conv&&"); return W(); }
};

W    slice() { Der d; return d; }
Fowl sink()  { W w; return w; }
W    conv()  { To t; return t; }

int main() { slice(); sink(); conv(); }
```

本机 Clang 23 在 `-std=c++11` 到 `-std=c++2c` 下都输出 `move`、`move`、`conv&&`（`conv&&` 里的 `return W();` 是 prvalue，不再产生移动）。实现把 P1825 当作缺陷报告应用到了所有语言模式，所以今天的编译器里已经看不到 C++17 原始措辞的行为。

这一步也有不兼容：如果基类的移动构造函数是 private，`return d;` 第一阶段选中它，访问检查失败，程序变成非良构，而 C++17 下会退回到可访问的复制构造函数。这条记录在 [[diff.cpp17.class#3]]。

## C++20 还剩下的问题

P1825 之后规则仍是两次重载决议，而且只在初始化返回对象时才生效。[[P2266R3]] 从这两点出发列出了剩下的问题。

### 返回引用的函数得不到隐式移动

两阶段规则写在复制消除一节，说的是选哪个构造函数。返回类型是引用时根本不调用构造函数，规则不适用，名字仍是左值：

```cpp title="backwarding.cpp" run std=c++23 ok
struct W {};

template<class T>
T&& seven(T&& x) { return x; }   // T = W 时：C++20 error

W&& four(W&& w) { return w; }    // C++20 error，C++23 OK

int main() {
  W w;
  W& r = seven(w);
  W&& rr = seven(static_cast<W&&>(w));
  (void)r; (void)rr; (void)four;
}
```

在 C++20 中，`four` 的返回类型 `W&&` 不能绑定到左值 `w`。同一个 `w`，返回类型是 `W` 时被当作右值，返回类型是 `W&&` 时却被当作左值。这在模板里尤其别扭：`seven` 想原样返回转发引用，`T` 推导为 `W` 时就不能编译。本机 Clang 23 在 `-std=c++20` 下对两处都报告 rvalue reference to type 'W' cannot bind to lvalue of type 'W'，在 `-std=c++23` 下接受。

转换函数也有同样的不一致：`operator int*() &&` 能被 `return x;` 用上，`operator int&() &&` 却不能，因为后者初始化的是引用返回值。

### 两次决议本身带来的怪异结果

P2266 的作者指出，就他所知，这是语言里唯一一处对同一个操作数做两次重载决议的地方，它的结果有时违反直觉：

- `Sam(W&)` 与 `Sam(const W&)` 并存时，`return w;` 第一阶段把 `w` 当右值，只有 `const W&` 可行，于是选中它。按左值决议本来会选中更好的 `Sam(W&)`。
- `Frodo(W&)` 与 `Frodo(W&&) = delete` 并存时，第一阶段选中弃置函数。这算决议成功（随后报错）还是失败（退回左值）？按 [[over.match.general#3]]，只要存在唯一的最佳可行函数，决议就成功，弃置与否不影响这一点；之后使用弃置函数才是非良构（[[dcl.fct.def.delete#2]]）。论文记录了当时各编译器在这里的实现并不一致。
- `Quest(Merry&&)`、`Quest(Pippin&&)`、`Quest(Together&)` 并存，返回一个同时派生自 `Merry` 和 `Pippin` 的 `Together` 局部变量：第一阶段二义，算作失败，第二阶段悄悄选中 `Quest(Together&)`。

最危险的是 `std::reference_wrapper`：

```cpp title="refwrap.cpp" run std=c++20
#include <functional>
std::reference_wrapper<int> f() {
  int i = 0;
  return i;   // C++20：良构，返回悬垂引用；C++23：error
}
int main() {}
```

`reference_wrapper` 的构造函数被约束为不接受右值，正是为了不让它绑定到临时对象（[[LWG2993]]）。两阶段规则下，第一阶段找不到可行函数，算作失败；第二阶段把 `i` 当左值，成功绑定，返回一个指向已销毁局部变量的包装。本机 Clang 23 在 `-std=c++20 -Wall` 下对此没有任何警告；在 `-std=c++23` 下报错 no viable conversion。

## 设计空间

面对这些问题，可以走三条路。

**只补洞。** 把两阶段规则推广到引用的初始化，让 `four`、`seven` 能编译。这能修好最明显的缺陷，但两次决议和它带来的 `Sam`、`Frodo`、`Quest`、`reference_wrapper` 问题都留着，编译器对决议失败的不同理解也会继续存在。

**发明新的值类别。** P2266 提到，P1825 通过后核心组内部讨论过 `Sam` 这类问题，提出过"优先绑定右值引用的左值"或"不情愿地绑定左值引用的右值"之类的概念。按论文的记述，那次讨论没有结论，只形成了一个共识：这些方案都比现状更糟。不难看出原因：值类别已经有五种，再加一种只在 `return` 里出现的半左值半右值，规则只会更难懂。

**让名字直接成为 xvalue。** 这是 P2266 的方案。在 `return`、`co_return` 的操作数和 `throw` 的操作数里，指代可隐式移动实体的 *id-expression* 本身就是 xvalue（[[g:xvalue]]），称为 **move-eligible**（[[g:move-eligible]]）。之后的一切照常进行，只做一次重载决议：初始化返回对象时它像 `std::move(x)` 一样选中移动构造函数；返回类型是 `W&&` 时它能绑定上去；返回类型是 `int&` 时它绑不上去。

第三条路换来的是一条可以独立陈述的规则：值类别由表达式所在的语境决定，后续的重载决议、引用绑定、`decltype` 都不必再知道隐式移动的存在。代价是所有依赖于被返回的名字是左值的代码都改变了含义：

<div class="compare" markdown="1">

```cpp title="C++20 良构"
int& g(int&& x) {
  return x;   // 左值绑定到 int&
}

struct Weird {
  Weird();
  Weird(Weird&);
};
Weird h() {
  Weird w;
  return w;  // 第二阶段：Weird(Weird&)
}
```

```cpp title="C++23 非良构"
int& g(int&& x) {
  return x;   // xvalue 不能绑定到 int&
}

struct Weird {
  Weird();
  Weird(Weird&);
};
Weird h() {
  Weird w;
  return w;  // xvalue 绑不上 Weird&
}
```

</div>

第一组直接对应 [[diff.cpp20.expr#1]] 的例子。第二组是 [[class.copy.elision#3]] 里标准自带的例子，`Weird` 的复制构造函数只接受非 const 左值引用。本机 Clang 23 在 `-std=c++23` 下对 `g` 报告 non-const lvalue reference to type 'int' cannot bind to a temporary of type 'int'（`x` 其实不是临时量，这是诊断措辞不准确），对 `h` 报告 no matching constructor。

`decltype(auto)` 的推导也随之改变。它把 `return` 的操作数当作 `decltype` 的操作数（[[dcl.type.auto.deduct#4]]），而带括号的 `decltype((e))` 反映 `e` 的值类别：

```cpp title="decltype-auto.cpp" run std=c++23 ok
#include <type_traits>
decltype(auto) f(int&& x) { return (x); }
decltype(auto) g(int x)   { return (x); }

static_assert(std::is_same_v<decltype(f(0)), int&&>);  // C++20: int&
static_assert(std::is_same_v<decltype(g(0)), int&&>);  // C++20: int&
int main() {}
```

`g` 返回一个绑定到形参的右值引用，函数返回后就悬垂了；C++20 下它返回 `int&`，同样悬垂。本机 Clang 23 在两种模式下都对 `g` 给出 `-Wreturn-stack-address` 警告。P2266 的看法是，`decltype(auto)` 附近的括号本来就是需要警惕的地方，这里没有增加多少新的意外。悬垂引用的其他形式见 [[topics/dangling-references]]。

`std::reference_wrapper`、`Quest` 这两个例子在 C++23 下都变成非良构。P2266 把前者看作改进：编译器终于诊断出了悬垂引用。

### 实际破坏了多少代码

P2266R1 在 2021 年作为默认行为实现在 Clang 13 的 `-std=c++2b` 模式里。论文报告了这期间在业界代码中发现的三处破坏，都被认为是可疑的写法并已修改：

| 原写法 | 问题 | 修改 |
|---|---|---|
| `istream& getline(istream&& in, …) { …; return in; }` | 右值引用形参返回为左值引用 | `return static_cast<istream&>(in);` |
| `template<class T> T& temporary(T&& x) { return x; }` | 同上 | `return static_cast<T&>(x);` |
| `X f() { char a[10]; return a; }`，`X(auto&)` | `a` 成为 `char(&&)[10]`，绑不上 `auto&` | `return X(a);` |

第三种比较隐蔽：返回类型是类，但它的构造函数是只接受左值的模板。本机 Clang 23 在 `-std=c++20` 下接受，`-std=c++23` 下报告 no viable conversion。

因为会破坏良构的旧代码，委员会没有把 P2266 当作缺陷报告，它只属于 C++23。特性测试宏是 `__cpp_implicit_move`，本机 Clang 23 在 `-std=c++23` 下定义为 `202207L`，在 `-std=c++20` 下不定义。

## 措辞的变化

C++20 中隐式移动是 [class.copy.elision] 的第 3 段，描述两阶段决议。P2266 认为复制消除一节不再是讲隐式移动的合适位置，把它整体移到了名字表达式的值类别规则里，原段落删除。今天的 [[class.copy.elision#3]] 只剩下一个例子，说明 `Weird`、`int& h(bool, int)`、`decltype(auto)` 在新规则下的结果。

新的规则分两处。[[expr.prim.id.unqual#12]] 把值类别的判断改成先看 move-eligible：

!!! std
    The expression is an xvalue if it is move-eligible (see below); an lvalue if the entity is a function, variable, structured binding, ...
    
    名字表达式如果是 move-eligible 的，就是 xvalue；否则按实体的种类决定是 lvalue 还是 prvalue。

[[expr.prim.id.unqual#15]] 定义可隐式移动的实体和 move-eligible：

- ¶15.1 表达式指代一个可隐式移动的实体；
- ¶15.2 它是 `return`、`co_return` 语句或 *throw-expression* 的操作数，可以带括号；
- ¶15.3 从实体的声明到表达式所在的最内层作用域，中间隔着的都是块作用域；对 `throw` 而言，这些作用域还不能是 `try` 块或函数 `try` 块的块作用域。

¶15.3 与 P2266 原文的写法不同。P2266 说的是"在最内层外围函数或 lambda 的函数体或形参列表中声明"，当前草案改用作用域来表述，含义相同：lambda 体里 `return` 外层函数的局部变量，中间隔着 lambda 的作用域，不算 move-eligible。¶15 还提到 *splice-expression*，这是 C++26 静态反射加入的。

其余改动都是非规范性的：[[basic.lval#4]] 的注把 move-eligible 的名字列为 xvalue 的第一种；[[dcl.type.auto.deduct#4]] 的例子加上了 `auto f2(int x) -> decltype(auto) { return (x); }` 推出 `int&&`；[[diff.cpp20.expr#1]] 记录了这项不兼容。[[stmt.return#2]] 的注 2 仍然说返回自动变量时复制可以被省略或转换为移动，具体规则见 [[class.copy.elision]]。

## 今天怎样写

**返回局部变量和形参时直接写名字。** `return std::move(local);` 把表达式变成函数调用，它不再是一个名字，于是失去了 NRVO 的资格。Clang 的 `-Wall` 中，`-Wpessimizing-move` 报告阻止了复制消除的 `std::move`，`-Wredundant-move` 报告对按值形参多余的 `std::move`。本机 Clang 23 对 `std::string a(std::string&& s) { return std::move(s); }` 在任何模式下都不报告多余，虽然 C++20 起这个 `std::move` 也已经不需要了。

**右值引用形参要以左值引用返回时，写出转换。** 例如 `return static_cast<T&>(x);`。这正是上面三处业界代码的修法。

**下面这些不是 move-eligible 的名字，仍然复制：**

```cpp title="not-eligible.cpp" run ok
#include <cstdio>
struct W {
  W() {}
  W(const W&) { std::puts("copy"); }
  W(W&&) { std::puts("move"); }
};
struct P { W a, b; };

W sb()   { auto [a, b] = P{}; return a; }        // 结构化绑定不是变量
W lam()  { W w; return [&] { return w; }(); }    // w 属于外层函数
W memb() { P p; return p.a; }                    // 成员访问不是名字

int main() { sb(); lam(); memb(); }
```

本机 Clang 23 在 `-std=c++20`、`-std=c++23`、`-std=c++2c` 下都输出三行 `copy`。要移动，就写 `std::move`。条件表达式、`*p`、`std::get<0>(t)` 也一样，它们各自多付出的代价见 [[perf/copies-and-moves]]。

各特殊成员何时被调用、隐式移动与 NRVO 的配合，见 [[topics/special-members-and-elision]]；从 C++11 到 C++26 的完整演进见 [[history/move-semantics]]。

## 编译器支持

下表是本机 Clang 23.1.3 的实测，`-fsyntax-only` 判断能否编译，有 `main` 的例子另外运行。

| 例子 | `-std=c++11` | `-std=c++17` | `-std=c++20` | `-std=c++23` |
|---|---|---|---|---|
| `unique_ptr<D>` 返回为 `unique_ptr<B>` | 移动 | 移动 | 移动 | 移动 |
| `return d;` 切片到基类、按值形参、转换函数 | 移动 | 移动 | 移动 | 移动 |
| `W f(W&& r) { return r; }`、`throw` 形参 | 移动 | 移动 | 移动 | 移动 |
| `W&& f(W&& w) { return w; }` | 报错 | 报错 | 报错 | 通过 |
| `int& g(int&& x) { return x; }` | 通过 | 通过 | 通过 | 报错 |
| `Weird(Weird&)`、`Quest`、`reference_wrapper`、`X(auto&)` | 通过 | 通过 | 通过 | 报错 |
| `Frodo(W&&) = delete` | 报错 | 报错 | 报错 | 报错 |

前三行说明 CWG1579 和 P1825 在 Clang 中按缺陷报告处理，后几行说明 P2266 只在 C++23 起生效。`Frodo` 在所有模式下都报错，与 [[over.match.general#3]] 的严格读法一致。GCC 和 MSVC 本机未验证。

## 思考题

!!! question "1. 尾置返回类型里的括号"
    下面的函数在 C++20 和 C++23 中各返回什么类型、是否良构？
    
    ```cpp
    auto f(int x) -> decltype((x)) { return (x); }
    ```

<details markdown="1">
<summary>答案</summary>

尾置返回类型不在 `return` 语句里，`decltype((x))` 中的 `x` 是普通的左值，返回类型是 `int&`，两个版本相同。函数体里的 `(x)` 在 C++23 中是 move-eligible 的 xvalue（[[expr.prim.id.unqual#15]]），不能绑定到 `int&`，所以 C++23 中非良构；C++20 中良构，但返回了对形参的悬垂引用。本机 Clang 23 在 `-std=c++20` 下给出 `-Wreturn-stack-address` 警告，在 `-std=c++23` 下报错。

</details>

!!! question "2. 为什么 `throw x;` 有作用域条件"
    ```cpp
    void g(const W&);
    void f() {
      W x;
      try { g(x); throw x; }
      catch (...) { g(x); }
    }
    ```
    这里的 `throw x;` 会移动 `x` 吗？

<details markdown="1">
<summary>答案</summary>

不会。`x` 的声明和 `throw` 之间隔着 `try` 块的块作用域，不满足 ¶15.3，`x` 不是 move-eligible 的，异常对象由复制初始化（本机 Clang 23 运行时输出 `copy`）。原因是异常可能被同一个函数里的 `catch` 捕获，之后还会用到 `x`；如果此时移动了它，`catch` 里看到的就是一个被掏空的对象。[[class.copy.elision#4]] 的例子展示了同样的情形。

</details>
