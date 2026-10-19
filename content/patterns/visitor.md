---
title: 访问者：双重分派与 std::visit
summary: 在不改动一组固定类型的前提下给它们增加操作：经典访问者怎样用两次虚调用实现双重分派，表达式问题的两个方向，无环访问者，std::variant 加 std::visit 的封闭集合写法、穷尽检查、多重分派和实现方式，递归 variant 的间接层，以及两种做法的实测代价。
status: draft
order: 55
since: c++17
papers: P0088R3, P0655R1, P2637R3, P3019R14, P2688
related: variant, variant.visit, variant.status, expr.call, class.virtual, expr.dynamic.cast, indirect, patterns/mixin, patterns/strategy, patterns/type-erasure, patterns/crtp, topics/ownership-and-smart-pointers, toolchain/object-layout-and-vtables
tags: 访问者, 双重分派, variant, visit, 设计模式
updated: 2026-10-19
---

!!! tldr
    - 重载决议看的是表达式的静态类型，虚调用只按一个对象的动态类型分派。经典访问者用两次虚调用（`accept` 一次、`visit` 一次）凑出按两个动态类型的分派。
    - 虚函数让新增类型容易、新增操作难，访问者正好反过来。这对矛盾叫表达式问题，选哪种写法取决于哪个方向更常变化。
    - 类型集合封闭时，`std::variant` 加 `std::visit` 是更直接的写法：值语义，不需要 `accept` 样板，漏掉一个类型就编译失败，还能同时按多个 variant 分派。
    - `std::visit` 用函数指针表把运行时下标变成编译期选好的调用；候选类型少时 Clang 会把它优化成几次比较加直接调用。
    - 递归的 variant 必须经过一层间接（`unique_ptr`、自写的值语义盒子或 C++26 的 `std::indirect`），因为 variant 把候选值直接放在自己体内。

## 问题：一棵表达式树，若干种操作

表达式 `(1 + 2) * 4` 可以表示成一棵树：叶子是数，内部节点是加法和乘法。要对这棵树做的事情有很多：求值、打印、常量折叠、类型检查、生成代码。节点的种类很少变化，操作却不断增加。

用虚函数的做法，每个操作是基类的一个虚函数：

```cpp
struct Expr {
  virtual double eval() const = 0;
  virtual std::string print() const = 0;
  virtual std::unique_ptr<Expr> fold() const = 0;   // 新操作：每个派生类都要改
  virtual ~Expr() = default;
};
```

每增加一个操作，所有节点类都要加一个函数，并重新编译所有包含 `Expr` 的代码。同一个操作的逻辑又分散在各个类里：求值的规则一部分在 `Add`，一部分在 `Mul`。访问者模式（visitor）把这个关系倒过来，让一个操作的全部逻辑集中在一个类里，节点类只提供一个固定的入口。

## 为什么不能只靠重载

最直接的想法是给每种节点写一个重载，让编译器去选：

```cpp run title="static-type.cpp" ok
#include <cstdio>
struct Expr { virtual ~Expr() = default; };
struct Num : Expr { double value = 1; };

void print(const Expr&) { std::printf("Expr\n"); }
void print(const Num&)  { std::printf("Num\n"); }

int main() {
  Num n;
  const Expr& e = n;
  print(n);   // Num：静态类型是 Num
  print(e);   // Expr：静态类型是 Expr，尽管对象是 Num
}
```

重载决议（[[g:overload-resolution]]）在编译期进行，它比较的是实参表达式的**静态类型**（[[g:static-type]]，编译器从声明就能看出的类型），与运行时 `e` 实际指向什么无关（[[over.match.general#1]]）。树里的子节点只能以 `Expr&` 或 `Expr*` 的形式保存，所以对子节点调用 `print` 永远选中 `print(const Expr&)`；如果没有这个重载，就直接编译失败。

运行时才知道的那个类型叫**动态类型**（[[g:dynamic-type]]，对象实际所属的最派生类）。C++ 里唯一按动态类型选择函数的语言机制是虚函数调用：被调用的是对象动态类型中的最终覆盖函数（[[g:final-overrider]]，[[expr.call#2]]）。而且它只看一个对象，就是 `.` 或 `->` 左边那个。

所以问题变成：一次调用要同时依赖两个对象的动态类型（哪种节点、哪种操作），而语言只提供按一个对象分派的手段。

## 经典访问者

```cpp run title="classic-visitor.cpp" ok
#include <cstdio>
#include <memory>

struct Num; struct Add; struct Mul;

struct Visitor {                   // 每种节点一个 visit
  virtual void visit(const Num&) = 0;
  virtual void visit(const Add&) = 0;
  virtual void visit(const Mul&) = 0;
  virtual ~Visitor() = default;
};

struct Expr {
  virtual void accept(Visitor& v) const = 0;
  virtual ~Expr() = default;
};
using Ptr = std::unique_ptr<Expr>;

struct Num : Expr {
  double value;
  explicit Num(double v) : value(v) {}
  void accept(Visitor& v) const override { v.visit(*this); }
};
struct Add : Expr {
  Ptr lhs, rhs;
  Add(Ptr l, Ptr r) : lhs(std::move(l)), rhs(std::move(r)) {}
  void accept(Visitor& v) const override { v.visit(*this); }
};
struct Mul : Expr {
  Ptr lhs, rhs;
  Mul(Ptr l, Ptr r) : lhs(std::move(l)), rhs(std::move(r)) {}
  void accept(Visitor& v) const override { v.visit(*this); }
};

// 一个操作 = 一个访问者类
struct Eval : Visitor {
  double result = 0;
  double of(const Expr& e) { e.accept(*this); return result; }
  void visit(const Num& n) override { result = n.value; }
  void visit(const Add& a) override { result = of(*a.lhs) + of(*a.rhs); }
  void visit(const Mul& m) override { result = of(*m.lhs) * of(*m.rhs); }
};
struct Print : Visitor {
  void visit(const Num& n) override { std::printf("%g", n.value); }
  void visit(const Add& a) override { bin(*a.lhs, '+', *a.rhs); }
  void visit(const Mul& m) override { bin(*m.lhs, '*', *m.rhs); }
  void bin(const Expr& l, char op, const Expr& r) {
    std::printf("(");
    l.accept(*this);
    std::printf(" %c ", op);
    r.accept(*this);
    std::printf(")");
  }
};

int main() {
  Ptr e = std::make_unique<Mul>(               // (1 + 2) * 4
      std::make_unique<Add>(std::make_unique<Num>(1),
                            std::make_unique<Num>(2)),
      std::make_unique<Num>(4));
  Print p;
  e->accept(p);
  std::printf(" = %g\n", Eval{}.of(*e));     // ((1 + 2) * 4) = 12
}
```

增加一个操作，只需要再写一个 `Visitor` 的派生类，节点类一行都不用改。

### 双重分派：两次虚调用

以 `Eval{}.of(*e)` 中 `e` 指向 `Mul` 为例，跟踪一次 `e.accept(*this)`：

1. `accept` 是虚函数，按 `e` 的动态类型选中 `Mul::accept`。这一步分派了节点的类型。
2. 在 `Mul::accept` 里，`*this` 的静态类型是 `const Mul`。对 `v.visit(*this)` 做重载决议时，编译器在编译期就选定了 `visit(const Mul&)`。
3. `visit` 也是虚函数，按 `v` 的动态类型选中 `Eval::visit(const Mul&)`。这一步分派了操作的类型。

这就是**双重分派**（double dispatch）：最终执行的函数由两个对象的动态类型共同决定。关键在第 2 步，重载决议本来不认识动态类型，但 `accept` 已经被虚调用带进了正确的派生类，在那里 `*this` 的静态类型恰好就是动态类型。

这也解释了为什么每个节点类都要重复同一行 `v.visit(*this);`。把它写进基类 `Expr` 是不行的，那里 `*this` 的静态类型是 `const Expr`，见思考题 1。想去掉重复，可以让一个类模板替每个节点生成 `accept`，即 [[patterns/crtp|CRTP]]。

代价是每访问一个节点要做两次间接调用，每次都要先从对象读出 vptr，再从虚表读出函数地址（见 [[toolchain/object-layout-and-vtables]]）。两次调用都跨越了编译器看不见的边界，通常不能内联。

### 表达式问题

虚函数和访问者各自让一个方向容易、另一个方向困难：

| 写法 | 新增一种节点 | 新增一种操作 |
|---|---|---|
| 每个操作一个虚函数 | 写一个派生类，旧代码不动 | 每个节点类都要改 |
| 经典访问者 | `Visitor` 基类和所有访问者都要改 | 写一个访问者类，旧代码不动 |
| `variant` + `visit` | 改 variant 的类型列表，所有没处理它的 `visit` 编译失败 | 写一个函数，旧代码不动 |

这对矛盾叫做**表达式问题**（expression problem）：在不修改、不重新编译已有代码的前提下，同时支持新增类型和新增操作。C++ 的这几种写法都只解决一半。访问者适合节点种类基本固定、操作不断增加的场合，编译器、解释器、文档格式转换器都是这样。节点种类经常变化时，虚函数更合适。

### 无环访问者

经典访问者里，`Visitor` 提到每一种节点，每种节点又通过 `accept` 提到 `Visitor`，形成依赖环：加一种节点就要改 `Visitor`，所有访问者和节点都要重新编译。**无环访问者**（acyclic visitor）把 `Visitor` 拆开，用 `dynamic_cast` 在运行时询问访问者是否支持当前节点：

```cpp run title="acyclic.cpp" ok
#include <cstdio>

struct VisitorBase { virtual ~VisitorBase() = default; };   // 空的根
template<class T>
struct VisitorOf {
  virtual void visit(const T&) = 0;
  virtual ~VisitorOf() = default;
};

struct Expr {
  virtual void accept(VisitorBase&) const = 0;
  virtual ~Expr() = default;
};
template<class Self>
struct Acceptor : Expr {
  void accept(VisitorBase& v) const override {
    if (auto* p = dynamic_cast<VisitorOf<Self>*>(&v))   // 运行时询问
      p->visit(static_cast<const Self&>(*this));
    else
      std::printf("<unhandled>");
  }
};
struct Num : Acceptor<Num> { double value = 2; };
struct Neg : Acceptor<Neg> {};   // 新节点：已有的访问者不用改

struct PrintNums : VisitorBase, VisitorOf<Num> {
  void visit(const Num& n) override { std::printf("%g", n.value); }
};

int main() {
  PrintNums p;
  Num n;
  Neg g;
  n.accept(p);
  std::printf(" ");
  g.accept(p);
  std::printf("\n");   // 2 <unhandled>
}
```

`VisitorBase` 和 `VisitorOf<Num>` 是 `PrintNums` 的两个兄弟基类，从一个转到另一个叫交叉转换（cross cast），运行时检查要先找到最派生对象，再在它的基类里找目标类型（[[expr.dynamic.cast#9]]）。它比一次虚调用贵得多，而且漏处理一种节点不再是编译错误，只能在运行时发现。所以无环访问者只在依赖关系确实是问题（比如节点类型分布在多个库里）时才值得用。

## std::variant 与 std::visit

如果节点种类是一个在编译期就确定的封闭集合，就不需要继承体系。`std::variant<Num, Add, Mul>` 是一个对象，它在任一时刻持有其中一种类型的值（[[variant.variant.general#1]]），`std::visit` 根据它当前持有的类型调用对应的函数（[[variant.visit]]）：

```cpp run title="variant-ast.cpp" ok
#include <cstdio>
#include <format>
#include <memory>
#include <string>
#include <variant>

template<class T>   // 值语义的堆盒子：复制时深复制，见下文
class box {
  std::unique_ptr<T> p_;
public:
  box(T v) : p_(std::make_unique<T>(std::move(v))) {}
  box(const box& o) : p_(std::make_unique<T>(*o.p_)) {}
  box& operator=(const box& o) {
    p_ = std::make_unique<T>(*o.p_);
    return *this;
  }
  box(box&&) noexcept = default;
  box& operator=(box&&) noexcept = default;
  const T& operator*() const { return *p_; }
};

template<class... Fs>
struct overloaded : Fs... { using Fs::operator()...; };

struct Expr;   // 先声明，box<Expr> 才写得出来
struct Num { double value; };
struct Add { box<Expr> lhs, rhs; };
struct Mul { box<Expr> lhs, rhs; };
struct Expr : std::variant<Num, Add, Mul> { using variant::variant; };

double eval(const Expr& e) {
  return std::visit(overloaded{
    [](const Num& n) { return n.value; },
    [](const Add& a) { return eval(*a.lhs) + eval(*a.rhs); },
    [](const Mul& m) { return eval(*m.lhs) * eval(*m.rhs); },
  }, e);
}

std::string show(const Expr& e) {
  return e.visit(overloaded{   // C++26 的成员 visit
    [](const Num& n) { return std::format("{}", n.value); },
    [](const Add& a) {
      return "(" + show(*a.lhs) + " + " + show(*a.rhs) + ")";
    },
    [](const Mul& m) {
      return "(" + show(*m.lhs) + " * " + show(*m.rhs) + ")";
    },
  });
}

Expr num(double v)       { return Num{v}; }
Expr add(Expr l, Expr r) { return Add{std::move(l), std::move(r)}; }
Expr mul(Expr l, Expr r) { return Mul{std::move(l), std::move(r)}; }

// 常量折叠：返回一棵新树，原树不变
Expr fold(const Expr& e) {
  return std::visit(overloaded{
    [](const Num& n) -> Expr { return n; },
    [](const auto& op) -> Expr {   // Add、Mul 共用一个分支
      using Op = std::decay_t<decltype(op)>;
      Expr l = fold(*op.lhs), r = fold(*op.rhs);
      bool constant = std::holds_alternative<Num>(l) &&
                      std::holds_alternative<Num>(r);
      Expr out = Op{std::move(l), std::move(r)};
      return constant ? Num{eval(out)} : out;
    },
  }, e);
}

int main() {
  Expr e = mul(add(num(1), num(2)), num(4));
  Expr copy = e;   // 深复制整棵树
  std::printf("%s = %g\n", show(copy).c_str(), eval(copy));
  // ((1 + 2) * 4) = 12
  Expr f = fold(add(num(1), mul(num(2), num(3))));
  std::printf("%s\n", show(f).c_str());   // 7
}
```

和经典访问者相比，有几处不同：

- 节点类型不需要共同的基类，也没有 `accept`。`Num`、`Add`、`Mul` 是普通的聚合，可以放进任何别的 variant。
- 值语义。`Expr` 本身就是值，可以复制、比较、放进容器，不需要 `unique_ptr<Expr>` 加虚析构函数。
- 操作就是函数。`eval`、`show`、`fold` 是三个普通函数，各自的全部逻辑集中在一处。新增操作不碰任何已有代码。
- 一个分支可以处理多种类型。`fold` 用一个泛型 lambda 同时处理 `Add` 和 `Mul`，这在经典访问者里要靠在基类里写默认实现。

把一组 lambda 拼成一个访问者的 `overloaded`，靠的是继承闭包类型、`using Ts::operator()...` 和聚合的类模板实参推导，原理见 [[patterns/mixin]] 和 [[variant.visit]] 的 overload 模式一节。`show` 里的 `e.visit(f)` 是 C++26 加入的成员 `visit`（[[P2637R3]]），它等价于 `std::visit(f, e)`（[[variant.visit#11]]），本机 libc++ 已经支持。

`Expr` 写成从 variant 派生的结构体，而不是 `using Expr = std::variant<Num, Add, Mul>;`，因为别名不能先声明后定义，`Add` 里又必须先提到 `Expr`。`std::visit` 能直接接受这种派生类（[[variant.visit#1]]）。

### 穷尽检查

给 variant 加一种类型后，每个没有处理它的 `visit` 都会编译失败：

```cpp title="missing-case.cpp" error
#include <variant>
template<class... Fs>
struct overloaded : Fs... { using Fs::operator()...; };

struct Num { double value; };
struct Add {};
struct Neg {};   // 新加的节点类型
using Node = std::variant<Num, Add, Neg>;

double eval(const Node& n) {
  return std::visit(overloaded{
    [](const Num& x) { return x.value; },
    [](const Add&)   { return 0.0; },
  }, n);   // error: 没有处理 Neg
}
```

规则在 [[variant.visit#5]]：对每一种可能的下标组合，访问者的调用都必须合法，这是 *Mandates*，不满足就是非良构。

本机 Clang 23 加 libc++ 的诊断并不直接：首个错误是库内部的 "no matching function for call to '__invoke'"，要在随后的 note 里找 `const __alt<2UL, Neg> &` 才能看出缺的是 `Neg`。libc++ 有一条 "`std::visit` requires the visitor to be exhaustive." 的 `static_assert`，但在这种写法下，内部包装函数的返回类型推导先失败，那条断言没有机会触发；改用 `std::visit<double>(...)` 时它才会出现。

!!! pitfall "穷尽检查会被隐式转换和泛型分支绕过"
    穷尽检查只是要求每种类型都能调用访问者，不要求恰好有一个为它写的分支。两种情况会让漏掉的类型悄悄通过：一是某个分支能经过隐式转换接住它，比如没有 `char` 分支时 `char` 会提升后进入 `int` 分支（例子见 [[variant.visit]] 的 overload 模式一节）；二是访问者里有 `[](const auto&)` 这样的兜底分支。`fold` 里的泛型分支就是这样：以后加入 `Neg`，它会被当成二元运算处理，而 `Neg` 没有 `lhs`、`rhs`，这时才会编译失败。兜底分支最好用 `if constexpr` 或 concepts 限定它真正能处理的类型。

### 返回类型

不指定返回类型时，所有分支的返回类型和值类别必须完全相同（[[variant.visit#5]]），运行时实际走哪个分支无关紧要。`fold` 的两个 lambda 都写了 `-> Expr`，因为第一个分支原本返回 `Num`，第二个返回 `Expr`，类型不同就是编译错误。

另一种办法是 C++20 的 `std::visit<R>(f, v)`（[[P0655R1]]）：每个分支的结果都隐式转换为 `R`，`R` 为 `void` 时结果被丢弃（[[variant.visit#4]] 里的 *INVOKE*<R>）。完整规则见 [[variant.visit]]。

### 多重分派

`std::visit` 可以同时接受多个 variant，访问者按它们当前持有的类型组合来选择分支。这正是经典访问者要靠两次虚调用才能做到的事，而且不限于两个：

```cpp run title="multi-dispatch.cpp" ok
#include <cstdio>
#include <variant>

template<class... Fs>
struct overloaded : Fs... { using Fs::operator()...; };

struct Circle { double x, y, r; };
struct Rect   { double x0, y0, x1, y1; };
using Shape = std::variant<Circle, Rect>;

bool hit(const Shape& a, const Shape& b) {
  return std::visit(overloaded{
    [](const Circle& c, const Circle& d) {
      double dx = c.x - d.x, dy = c.y - d.y, s = c.r + d.r;
      return dx * dx + dy * dy <= s * s;
    },
    [](const Rect& p, const Rect& q) {
      return p.x0 <= q.x1 && q.x0 <= p.x1 &&
             p.y0 <= q.y1 && q.y0 <= p.y1;
    },
    [](const Circle& c, const Rect& r) {   // 粗略：用外接正方形
      return c.x + c.r >= r.x0 && c.x - c.r <= r.x1 &&
             c.y + c.r >= r.y0 && c.y - c.r <= r.y1;
    },
    [](const Rect& r, const Circle& c) {   // 交换参数，再分派一次
      return hit(c, r);
    },
  }, a, b);
}

int main() {
  Shape c = Circle{0, 0, 1}, r = Rect{0.5, 0.5, 3, 3};
  std::printf("%d %d %d\n", hit(c, c), hit(c, r), hit(r, c));   // 1 1 1
}
```

两个各有 2 种类型的 variant 有 2×2 = 4 种组合，访问者必须全部处理。组合数是各个 variant 类型数的乘积，所以标准只对单个 variant 要求常数时间，多个 variant 时不作复杂度要求（[[variant.visit#8]]）。实际的代价主要在编译期：每种组合实例化一个函数，组合多了编译时间和代码体积都会增长。

## std::visit 怎样实现

标准要求单个 variant 的访问在常数时间内完成，与候选类型的数量无关（[[variant.visit#8]]）。libc++ 的做法是在编译期为每个下标实例化一个分派函数，把它们的地址放进一个 `constexpr` 数组，运行时用 `index()` 取出一项并调用。多个 variant 时这个数组是多维的。

在调用之前还有一步检查。variant 可能处于不持有任何值的状态，叫 **valueless by exception**（[[g:valueless-by-exception]]）：改变候选类型的赋值或 `emplace` 中途抛出异常时，就可能出现这种状态，比如旧值已经销毁、新值的构造又失败了（[[variant.status#2]]）。这时 `index()` 返回 `variant_npos`（[[variant.status#3]]），它不是有效的表下标，所以 `visit` 必须先检查，并抛出 `bad_variant_access`（[[variant.visit#7]]）。

优化器能看穿这张 `constexpr` 表。本机（Apple M2 Pro，arm64，Clang 23，`-O2`）上，对一个有 5 种候选类型的 variant 调用 `std::visit([](auto y) { return f(y); }, x)`，其中 `f` 是 5 个外部函数的重载，生成的代码是：

```text
ldr   w8, [x0, #4]        ; 读出下标
cmn   w8, #1              ; 下标 == -1？即 valueless
b.eq  throw_bad_variant_access
ldr   w0, [x0]            ; 读出候选值（一个 int）
cmp   w8, #1
b.le  ...                 ; 按下标做二分比较
...
b     f(D)                ; 每个分支是一次直接的尾调用
```

没有间接跳转，每个分支都是对 `f` 的直接调用。本机把候选类型数从 5 逐个增加到 12 测试：不超过 10 种时都是这样的比较树；从 11 种开始，Clang 保留了函数指针表，生成 `ldr x8, [表, 下标, lsl #3]` 加 `blr x8` 的间接调用。这个阈值是本机编译器的启发式，不是语义上的保证。

作为对比，同样参数下一次虚调用 `b.g()` 编译成三条指令：读 vptr、从虚表读函数地址、间接跳转。

## 递归的 variant 需要间接层

表达式树是递归的：`Add` 的子节点又是 `Expr`。直接写成 `struct Add { Expr lhs, rhs; };` 是非良构的。原因有两层：

- 写 `Add` 时 `Expr` 还是不完整类型，非静态数据成员不能是不完整类型（[[class.mem.general#20]]）。
- 即使能写出来也没有意义。variant 把当前的候选值直接嵌套在自己的存储里（[[variant.variant.general#1]]），`Expr` 包含 `Add`，`Add` 又包含两个 `Expr`，大小无穷。

所以必须有一层指针。三种选择：

| 间接层 | 允许不完整类型 | 可以复制 | 说明 |
|---|---|---|---|
| `std::unique_ptr<Expr>` | 是（[[unique.ptr.general#4]]） | 否 | 整棵树只能移动；需要复制时要手写深复制 |
| 自写的值语义盒子，如上文的 `box` | 是 | 深复制 | 要自己处理被移动后的空指针 |
| `std::indirect<Expr>` {{c++26}} | 是（[[indirect.general#6]]） | 深复制 | 标准化的 `box`，`const` 会传播 |

标准库模板一般不允许以不完整类型实例化，否则行为未定义（[[res.on.functions#2.5]]）；只有明文允许的组件例外，`unique_ptr`、`vector`、`indirect` 都在此列，`variant` 不在。上面的写法里，实例化 `std::variant<Num, Add, Mul>` 时 `Add` 已经完整，不完整的只是 `box<Expr>` 里的 `Expr`，所以没有问题。

用 C++26 的 `std::indirect`（[[P3019R14]]），树的定义和 `box` 版本几乎一样：

```cpp
#include <memory>
#include <variant>

struct Expr;
struct Num { double value; };
struct Add { std::indirect<Expr> lhs, rhs; };
struct Mul { std::indirect<Expr> lhs, rhs; };
struct Expr : std::variant<Num, Add, Mul> { using variant::variant; };

Expr add(Expr l, Expr r) {
  return Add{std::indirect<Expr>(std::move(l)),   // 这个构造函数是 explicit
             std::indirect<Expr>(std::move(r))};
}
```

这段代码没有判定标记：截至写作时，本机 libc++（Clang 23 附带）还没有实现 `std::indirect`，无法验证。`indirect` 的完整规则和它与 `unique_ptr` 的对比见 [[topics/ownership-and-smart-pointers]]。

!!! pitfall "被移动后的盒子是空的"
    `box` 和 `indirect` 被移动之后都不再拥有对象。`indirect` 把这叫做无值（[[g:valueless]]，[[indirect.general#1]]），可以用 `valueless_after_move()` 查询；对它解引用是未定义行为。上面的 `box` 没有提供查询，复制一个被移走的 `box` 会解引用空指针。树的构造函数按值接收子树再移入，这是安全的；但不要在移走之后继续使用原来的变量。

## 代价：实测

`sizeof` 方面，本机 libc++ 上 `Expr`（两个 `unique_ptr` 加一个下标）是 24 字节；虚函数版本的 `Num` 是 16 字节（vptr 加 `double`），`Add` 是 24 字节。variant 的大小是最大候选类型加上下标、再按对齐取整，所有节点一样大。

下面是本机（Apple M2 Pro，Clang 23，`-O2`）的测量，取 7 次中最快的一次。第一组是一棵约 420 万个节点的随机满二叉表达式树（叶子 2^21 个），三种写法按相同顺序分配节点，都对整棵树求值。第二组是 1000 万个随机类型的图形求面积之和。

| 场景 | 写法 | 耗时 |
|---|---|---|
| 树求值 | 经典访问者（每节点两次虚调用） | 约 16 ms |
| 树求值 | 每个操作一个虚函数（每节点一次虚调用） | 约 15 ms |
| 树求值 | `variant` + `visit`，`unique_ptr` 子节点 | 约 12–13 ms |
| 扁平序列 | `vector<unique_ptr<Shape>>`，按分配顺序 | 约 57 ms |
| 扁平序列 | 同上，打乱指针顺序 | 约 147 ms |
| 扁平序列 | `vector<variant<C, S, T>>` | 约 42 ms |

几点观察：

- 在树上，三种写法差距不大。每个节点都要追一次指针，访存成本占了大头；双重分派比单次虚调用多出的那次间接调用，大约多了 7%。
- 在扁平序列上，variant 的优势主要来自内存布局，不是分派本身。variant 的元素连续存放在 `vector` 里；指针版本即使堆块恰好按顺序分配，也比 variant 慢约 35%，打乱后（更接近长期运行的程序里堆的样子）慢 3 倍多。
- 类型随机分布时，两种写法都难以预测分支：虚调用是间接跳转难以预测，variant 是比较分支难以预测。

这些数字只说明本机这一种负载；节点更大、操作更重、类型分布更有规律时，比例都会改变。

## 模式匹配：还没有进入标准

很多语言用模式匹配来做这件事：一个表达式按值的形状（类型、结构、取值）选择分支，编译器检查分支是否穷尽。C++ 的相应提案是 [[P2688]]，引入 `match` 表达式，可以直接按 variant 的候选类型、多态对象的动态类型或结构化的值来匹配。它没有进入 C++26，当前草案里也没有 `match` 关键字。在它被采纳之前，`std::visit` 加 `overloaded` 就是 C++ 里最接近的写法。

## 陷阱

!!! pitfall "构造和析构期间的 accept"
    在节点的构造函数或析构函数里调用 `accept`，虚调用按当前正在构造或析构的那一层类分派（[[class.cdtor]]），可能落到基类的纯虚函数上。访问一棵树之前，确认它已经完全构造。

!!! pitfall "递归访问与栈深度"
    上面的 `eval`、`show`、`fold` 和 `Eval` 访问者都是递归的。退化成链表的深树（比如一万层 `1 + (1 + (1 + ...))`）会让递归深度等于树高。树的形状来自外部输入时，改用显式栈遍历，或者限制深度。`unique_ptr` 链的析构同样是递归的。

!!! pitfall "多个 variant 的组合爆炸"
    三个各有 10 种类型的 variant 一起访问，就要实例化 1000 个分派函数，访问者也要对每一种组合可调用。真正需要特殊处理的组合往往只有几种，其余用泛型分支兜底，同时留意上文所说的兜底分支会掩盖遗漏。

## 什么时候用哪一种

| 情况 | 选择 |
|---|---|
| 类型集合封闭、在一处定义，操作经常增加 | `std::variant` + `std::visit` |
| 需要值语义、放进容器连续存储 | `std::variant` |
| 要同时按两个以上对象的类型分派 | `std::visit` 的多 variant 形式 |
| 类型集合开放，第三方要能增加新类型 | 虚函数；操作少而稳定时直接作为虚函数 |
| 类型层次已经存在且必须保留，又要不断加操作 | 经典访问者 |
| 节点类型分布在多个库里，不能互相依赖 | 无环访问者，接受运行时检查的代价 |
| 只是要在运行时替换一个算法 | 不需要访问者，见 [[patterns/strategy]] |
| 要对任意类型提供统一接口，不想要共同基类 | [[patterns/type-erasure]] |

## 思考题

!!! question "1"
    为了避免每个节点类重复写 `accept`，有人把它写进基类：
    ```cpp
    struct Expr {
      void accept(Visitor& v) const { v.visit(*this); }
    };
    ```
    这样能行吗？

<details markdown="1">
<summary>答案</summary>

不行。在 `Expr::accept` 里 `*this` 的静态类型是 `const Expr`，重载决议在编译期进行，只能在 `visit(const Num&)`、`visit(const Add&)` 等候选中寻找接受 `const Expr` 的那个。从基类到派生类没有隐式转换，所以没有可行函数，程序非良构；本机 Clang 23 报 "no viable conversion from 'const Expr' to ..."。如果 `Visitor` 恰好有一个 `visit(const Expr&)`，就会每次都选中它，双重分派退化成单次分派。

`accept` 必须在每个派生类里各写一份，才能让 `*this` 的静态类型等于动态类型。可以用 CRTP 中间层 `template<class Self> struct Node : Expr { void accept(Visitor& v) const override { v.visit(static_cast<const Self&>(*this)); } };` 让模板替每个类生成它，上文的 `Acceptor` 就是这个做法。
</details>

!!! question "2"
    下面的访问者用于 `std::variant<int, long>`，能编译吗？
    ```cpp
    std::visit(overloaded{
      [](int)    { return 1; },
      [](double) { return 2; },
    }, v);
    ```

<details markdown="1">
<summary>答案</summary>

不能。`int` 分支精确匹配 `int`，没有问题；问题在 `long`。`long` 到 `int` 是整数转换，`long` 到 `double` 是浮点整数转换，两者都是转换等级（Conversion rank，[[over.ics.scs]] 表 19），哪个也不比另一个好，对 `long` 的调用有歧义。[[variant.visit#5]] 要求每种组合的调用都合法，所以整个 `visit` 非良构。本机 libc++ 报的同样是 "no matching function for call to '__invoke'"，note 里指出出问题的是 `__alt<1UL, long>`。

这说明穷尽检查检查的是可调用性：如果只有 `[](double)` 一个分支，`int` 和 `long` 都能转换过去，程序反而能编译，而且两种整数都悄悄走了 `double` 分支。
</details>

!!! question "3"
    把上面的 `std::visit(..., a, b)` 换成访问三个各有 5 种类型的 variant。访问者要能处理多少种组合？标准对这次调用有复杂度要求吗？libc++ 怎么实现？

<details markdown="1">
<summary>答案</summary>

5×5×5 = 125 种组合，每一种都必须能调用访问者，否则非良构（[[variant.visit#5]]）。标准对多于一个 variant 的访问不作复杂度要求（[[variant.visit#8]]），因为一张覆盖所有组合的表大小随 variant 的个数指数增长，标准不想强迫实现这样做。libc++ 仍然构造一个 5×5×5 的三维函数指针数组，按三个下标逐维索引，运行时是常数时间，代价转移到了编译期：125 个分派函数的实例化和对应的目标代码。
</details>
