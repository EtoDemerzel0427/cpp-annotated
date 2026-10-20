---
title: 保证的复制省略（P0135）
summary: C++17 怎样让不可复制、不可移动的类型也能从工厂函数按值返回：P0135 没有把复制省略从允许改成必须，而是重新定义了 prvalue，让它在被实质化之前根本不是对象。
status: draft
order: 10
group: 核心语言
since: c++17
papers: P0135R0, P0135R1, CWG1565, CWG1590, CWG1599, CWG1697, CWG2022, CWG2327, P2828R2, CWG2403, P2025R2
related: basic.lval, conv.rval, class.temporary, dcl.init, class.copy.elision, stmt.return, expr.call, expr.cond, expr.context, dcl.type.decltype, meta.rel, cpp.predefined, topics/value-categories, topics/special-members-and-elision, history/move-semantics
tags: 提案, 复制消除, 值类别, prvalue, 临时量实质化, C++17
updated: 2026-10-19
---

!!! tldr
    - C++14 允许编译器省略从临时对象到目标对象的复制，但被省略的构造函数仍须可用，所以 `std::atomic`、`std::lock_guard` 这类类型写不出按值返回的工厂函数。
    - P0135 没有把这种省略改成必须，而是重新定义了 prvalue：prvalue 是一次初始化，不是一个对象；只有需要 glvalue 时，才经由临时量实质化创建临时对象。
    - 于是用同类型的 prvalue 初始化对象时，从语义上就没有复制或移动可省，也不需要复制或移动构造函数。
    - 保证只覆盖 prvalue。`return local;` 的 NRVO 仍然只是允许，基类子对象、转换函数直接初始化等边角情形还有未决的 CWG issue。
    - 平凡可复制的类型仍然允许实现额外复制一次（为了用寄存器传递），这时对象的地址会改变。

## C++14：写不出来的工厂函数

```cpp run title="factory.cpp" ok
#include <atomic>
#include <mutex>

std::atomic<int> make_counter() {
  return std::atomic<int>(0);           // C++14: 需要已删除的复制构造函数
}

struct Pinned {
  explicit Pinned(int v) : v(v) {}
  Pinned(const Pinned&) = delete;
  Pinned(Pinned&&) = delete;
  int v;
};
Pinned make_pinned(int v) { return Pinned(v); }

int main() {
  auto c = make_counter();
  auto p = make_pinned(42);
  std::mutex m;
  auto g = std::lock_guard<std::mutex>(m);   // auto x = T(...) 的写法
  return p.v - 42 + c.load();
}
```

本机 Clang 23 用 `-std=c++17` 编译通过；换成 `-std=c++14`，五处都报错：两个 `return` 和三个 `auto` 声明，诊断都是调用了被删除的（或被隐式删除的）构造函数。

C++14 的模型是这样的：`Pinned(v)` 创建一个临时对象，`return` 再从它复制或移动出返回值，调用方又从返回值复制或移动到 `p`。标准允许实现省略这些复制（C++14 的 [class.copy] ¶31），实践中编译器也总是省略，但省略之前必须先确认复制在语义上可行，被选中的构造函数要可访问、未删除。程序员和编译器都知道这个构造函数不会被调用，代码还是不能编译。

当时只能绕开：

<div class="compare" markdown="1">

```cpp
// 放到堆上
std::unique_ptr<Pinned>
make_pinned(int v) {
  return std::make_unique<Pinned>(v);
}
```

```cpp
// 两段式初始化
void init_pinned(Pinned& out, int v);

Pinned p(0);        // 先构造
init_pinned(p, 42); // 再填写
```

</div>

前者多一次动态分配和一层间接，后者要求类型有一个空状态。[[P0135R0]] 还举了一个风格上的问题：习惯写 `auto x = make();` 的人，遇到不可移动的类型就只能退回别的写法。即使类型可以移动，可移植的代码也不能依赖省略一定发生，对很大的对象仍有人宁可用输出参数。

## 设计空间

### 三条路

P0135R0 的作者 Richard Smith 在论文里列出了三种选择：

1. **什么都不做**。代价是上一节的那些问题：没有性能保证，要提供永远不会调用的构造函数，写不了不可移动类型的工厂函数。
2. **换一种方式保证复制省略**，也就是保留"`T(...)` 创建临时对象"的模型，只是规定这次复制必须省略。论文认为不清楚该怎样写这样的规则，而且会错过一次让值类别更好学的机会。
3. **改写值类别的定义**，让这次复制从一开始就不存在。这是最终的方案。

第二条路的困难可以这样理解：如果仍然说 `T x = T();` 有一个临时对象和一次复制，那么规定"必须省略、又不检查构造函数"等于说程序里有一次永远不允许发生的复制，模型本身就自相矛盾。论文指出，"`T(...)` 创建临时对象"这个模型本来就只对类类型成立：`int()` 从来不是对象，它只是一个值。

### 只管 prvalue，不管 NRVO

C++14 允许省略复制的场合有三类：用临时对象初始化另一个对象（包括返回值和异常对象）、`return` 或 `throw` 一个即将离开作用域的变量、按值 `catch`。P0135 只处理第一类。

论文承认可靠的 NRVO（named return value optimization，返回具名局部变量时省略复制）对推断性能很重要，但它能否发生取决于函数里所有 `return` 的形状，很难给出一个简单的保证。所以 `T f() { T t; return t; }` 的省略至今仍是允许而非保证，见下文。

### 换个角度定义 prvalue

方案的核心是一句话：prvalue 执行初始化，glvalue 给出位置。

```cpp
struct X { int n; };
extern X x;
X{4};      // prvalue：表示"初始化一个 X"
x.n;       // glvalue：表示 x 的成员 n 的位置
X{4}.n;    // glvalue（xvalue）：X{4} 的成员 n 的位置
```

论文强调，这一改写本身不改变任何表达式的分类，`X{4}` 仍然是 prvalue，`X{4}.n` 仍然是 xvalue。变化在后面：既然 prvalue 只是初始化，`T()` 就没有理由自己创建临时对象。是否需要一个临时对象，应当由 prvalue 所在的上下文决定，而用它初始化同类型对象的上下文根本不需要。

`T x = 5;` 这样的复制初始化也因此变了：

```cpp run title="convert.cpp" ok
struct Pinned {
  Pinned(int v) : v(v) {}               // 转换构造函数
  Pinned(const Pinned&) = delete;
  int v;
};
Pinned x = 5;   // C++14: 先构造临时对象，再复制，被删除；C++17: 直接构造 x
int main() { return x.v - 5; }
```

本机 Clang 23 在 `-std=c++14` 下报告 "copying variable of type 'Pinned' invokes deleted constructor"，`-std=c++17` 下通过。

## 最终的措辞

[[P0135R1]] 给出了措辞，同时解决了 [[CWG1565]]、[[CWG1590]]、[[CWG1599]]、[[CWG1697]] 四个 issue，并部分解决了 [[CWG2022]]（常量表达式中的复制省略，NRVO 除外）。下面按当前草案的位置列出关键改动。

### prvalue 与结果对象

值类别的定义改成了按求值做什么来分（[[basic.lval#1]]）：

!!! std
    A *prvalue* is an expression whose evaluation initializes an object or computes the value of an operand of an operator, as specified by the context in which it appears, or an expression that has type cv void.

prvalue 初始化对象，或者为运算符计算一个操作数的值，具体是哪一种由它所在的上下文决定。它初始化的那个对象叫做**结果对象**（[[g:result-object|result object]]，[[basic.lval#5]]）。`T x = make();` 中，`make()` 的结果对象就是 `x`；`make` 里的 `return Pinned(v);` 又用 prvalue `Pinned(v)` 初始化调用的结果对象，所以 `Pinned(v)` 的结果对象也是 `x`。一层层传下去，构造函数最终直接在 `x` 的存储上运行。

### 临时量实质化

prvalue 出现在需要 glvalue 的地方时，例如绑定引用、访问成员，就要真的有一个对象。新增的**临时量实质化转换**（[[g:temporary-materialization-conversion|temporary materialization conversion]]，[[conv.rval#1]]）负责这件事：它创建一个临时对象，以它为结果对象求值 prvalue，得到一个指代它的 xvalue。

[[basic.lval#7]] 规定，prvalue 作为运算符的操作数出现时一般都要做这个转换；[[class.temporary#2]] 的注释列出了实质化发生的场合：绑定引用、对类 prvalue 做成员访问或调用隐式对象成员函数、对数组 prvalue 做下标或数组到指针转换、构造 `std::initializer_list`、`typeid` 和 `sizeof` 的部分操作数，以及作为弃值表达式（[[expr.context#2]]）。反过来，`decltype` 的操作数不实质化，类型可以不完整（[[dcl.type.decltype#2]]）。

这一来临时对象只剩两个来源（[[class.temporary#1]]）：实质化，以及下文讲的实现为传参和返回而额外创建的对象。C++14 中散落在各处的"创建一个临时对象"的说法都被删除或改写了。

### 用同类型的 prvalue 初始化

初始化规则里加了一条，排在调用构造函数之前（[[dcl.init#15.6.1]]）：

!!! std
    If the initializer expression is a prvalue and the cv-unqualified version of the source type is the same as the destination type, the initializer expression is used to initialize the destination object.

草案在这里附的例子是 `T x = T(T(T()));`，它只值初始化 `x` 一次。同时，C++14 [class.copy] ¶31 中允许省略"未绑定到引用的临时对象的复制"那一项被删除了，因为这种复制已经不存在。

其余条款跟着改成了结果对象的说法：

| 条款 | 现在的说法 |
|---|---|
| [[stmt.return#2]] | `return` 用复制初始化去初始化调用的 prvalue 结果对象 |
| [[expr.call#9]] | 函数调用的结果就是 `return` 操作数的结果 |
| [[expr.cond#7.1]] | 两个操作数同类型时，结果由被选中的操作数复制初始化 |
| [[expr.type.conv#1]] | `T(args)`、`T{args}` 是 prvalue，其结果对象由初始化器直接初始化 |
| [[expr.prim.lambda.general#2]] | lambda 表达式是 prvalue，它的结果对象叫闭包对象 |

在本机 Clang 23 上数一下构造次数（每行之后的析构略去）：

```cpp run title="count.cpp" ok
#include <cstdio>
struct T {
  T() { std::puts("T()"); }
  T(const T&) { std::puts("T(const T&)"); }
  T(T&&) noexcept { std::puts("T(T&&)"); }
  ~T() { std::puts("~T()"); }
};
T make() { return T(); }
int main() {
  std::puts("[1]"); T a = T(T(T()));
  std::puts("[2]"); T b = make();
  std::puts("[3]"); T c = true ? T() : make();
}
```

| 语句 | `-std=c++14 -fno-elide-constructors` | `-std=c++17 -fno-elide-constructors` |
|---|---|---|
| `T a = T(T(T()));` | 1 次构造 + 3 次移动 | 1 次构造 |
| `T b = make();` | 1 次构造 + 2 次移动 | 1 次构造 |
| `T c = true ? T() : make();` | 1 次构造 + 2 次移动 | 1 次构造 |

不加 `-fno-elide-constructors` 时两种模式都只有 1 次构造。区别在于 C++14 的结果来自一项可以关掉的优化，C++17 的结果来自语言规则，那个选项再也插不进移动。

## 后果

### 保证了什么，没保证什么

```cpp title="limits.cpp"
struct Pinned {
  Pinned() = default;
  Pinned(const Pinned&) = delete;
};
Pinned make() { return Pinned(); }                   // OK：prvalue

Pinned nrvo() { Pinned p; return p; }                // error: NRVO 不是保证
Pinned param(Pinned p) { return p; }                 // error: 形参不能省略
struct AsMember { Pinned m; AsMember() : m(make()) {} };   // OK
struct AsBase : Pinned { AsBase() : Pinned(make()) {} };   // error，见 CWG2403

class Hidden { ~Hidden() {} public: Hidden() {} };
Hidden h() { return Hidden(); }   // error: 析构函数是私有的
```

本机 Clang 23（`-std=c++2c`）恰好在标注 error 的四行报错。

- `nrvo`：`return p;` 中 `p` 是可隐式移动的，作为 xvalue 选中构造函数，`Pinned` 没有可用的移动或复制构造函数，所以非良构。省略这次移动只是 [[class.copy.elision#1]] ¶1.1 允许的优化。保证 NRVO 的 [[P2025R2]] 没有进入工作草案。
- `param`：形参本来就不在可省略的范围内。
- `AsBase`：按措辞，用 prvalue 初始化基类子对象和成员子对象并无区别，但基类子对象可能与派生类的其他成员共用尾部填充，直接在它的位置上构造会出问题。[[CWG2403]] 记录了这一点：各实现都把基类的情形当作需要复制，成员的情形则接受。该 issue 仍在起草中。
- `Hidden`：结果对象的析构函数是潜在调用的（[[stmt.return#3]]），必须可访问，与有没有复制无关。实质化时同样要求析构函数可访问、未删除（[[conv.rval#1]] 的注释）。

所以 P0135 之后，工厂函数的写法是 `return T(...);` 或 `return {...};`，不要先构造一个局部变量再返回它。实际开销的完整对照见 [[topics/special-members-and-elision]]。

### 聚合与 lambda 跟着受益

聚合的成员、lambda 的 init-capture 都是复制初始化，用 prvalue 初始化它们时同样不需要构造函数。闭包对象和聚合本身也是 prvalue 的结果对象：

```cpp run title="agg-lambda.cpp" ok
#include <atomic>
struct Pinned {
  Pinned(int v) : v(v) {}
  Pinned(const Pinned&) = delete;
  int v;
};
Pinned make(int v) { return v; }
struct Agg { Pinned p; std::atomic<int> n; };
Agg make_agg() { return Agg{make(1), 0}; }   // 成员和聚合本身都直接构造
int main() {
  Agg g = make_agg();
  auto l = [a = std::atomic<int>(0), p = make(3)]() mutable {
    return ++a + p.v;
  };   // 闭包有不可复制的成员，仍可这样初始化 l
  return g.p.v + l() - 5;
}
```

本机 Clang 23 在 `-std=c++17` 下编译运行，返回 0；`-std=c++14` 下 `make`、`make_agg`、`g`、`l` 各处都报调用了被删除的构造函数。

### 平凡可复制类型的例外

[[class.temporary#3]] 允许实现在传参和返回时额外创建临时对象，条件是类型有合格的复制或移动构造函数且都平凡、析构函数平凡或被删除。这条例外在 P0135R1 里就有，注释说明它是为了让这类对象能用寄存器传递。代价是对象的地址可能在返回途中改变：

```cpp run title="addr.cpp" unspecified
#include <cstdio>
struct Small {                 // 平凡可复制
  Small* self;
  Small() : self(this) {}
};
struct Big {                   // 用户提供的析构函数：不平凡
  Big* self;
  Big() : self(this) {}
  ~Big() {}
};
Small make_small() { return Small(); }
Big make_big() { return Big(); }
int main() {
  Small s = make_small();
  Big b = make_big();
  std::printf("Small: %s\n", s.self == &s ? "same" : "different");
  std::printf("Big:   %s\n", b.self == &b ? "same" : "different");
}
```

本机（arm64，Clang 23，`-O0` 和 `-O2` 相同）输出 `Small: different`、`Big: same`。`Small` 用寄存器返回，构造时的 `this` 是被调函数里的一块临时存储；`Big` 不允许这样做，构造函数直接运行在调用方的 `b` 上。需要在构造函数里记下 `this` 的类型，应当让它不平凡可复制。

### ABI 没有变

P0135 是把实现早已在做的事写成规则。对不能用寄存器返回的类型，主流 ABI 本来就让调用方分配返回值的存储，把地址作为隐藏参数传给被调函数。本机 arm64 上 `-O2` 编译 `Pinned make(int v) { return Pinned(v + 1); }`（`Pinned` 有非平凡的析构函数），整个函数是：

```text
add  w1, w0, #1
mov  x0, x8          // x8：调用方传入的结果对象地址
b    Pinned::Pinned(int)
```

构造函数的 `this` 就是调用方给的地址。把复制构造函数改成可用的（不删除）后，`-std=c++14` 和 `-std=c++17` 生成的汇编逐字相同。

### Annex C 里没有的变化

[[diff.cpp14]] 没有为这项改动列条目：C++14 早已允许省略这些复制，依赖复制次数的程序本来就不可移植。不过有一类可以观察到的差别，是在编译期询问能不能复制初始化的地方：

```cpp run title="trait.cpp" ok
#include <type_traits>
struct Pinned {
  Pinned(int) {}
  Pinned(const Pinned&) = delete;
};
static_assert(std::is_convertible<int, Pinned>::value, "");
int main() {}
```

`is_convertible<From, To>` 按 [[meta.rel#6]] 定义为 `To test() { return declval<From>(); }` 是否良构。这正是上面的 `return v;`：C++14 要先构造临时对象再复制，结果为假；C++17 为真。本机 Clang 23 在 `-std=c++14` 下这条 `static_assert` 失败，`-std=c++17` 下通过。依赖这类检测做重载选择的代码，在两个模式下可能选中不同的函数。

另一项随 P0135R1 进入的改动是形参的销毁时机：形参在函数返回时销毁，还是在调用所在的完整表达式结束时销毁，改为由实现定义（[[expr.call#7]]）。

### 遗留问题

- [[CWG2327]]：`Cat c(d);`，`d` 的类型有一个返回 `Cat` 的转换函数。这是直接初始化，按 [[dcl.init#15.6.2]] 只考虑 `Cat` 的构造函数，复制或移动构造函数的形参绑定到转换函数的结果，于是实质化一个临时对象再复制，保证落空。[[P2828R2]] 提议同时考虑转换函数。
- [[CWG2403]]：基类子对象，见上文。

```cpp title="cwg2327.cpp"
struct Cat { Cat() {} Cat(const Cat&) = delete; };
struct Dog { operator Cat() const { return Cat(); } };
int main() {
  Dog d;
  Cat a = d;   // 复制初始化：转换函数的结果直接初始化 a
  Cat b(d);    // 直接初始化：按现行措辞选中被删除的复制构造函数
}
```

按现行措辞第二行非良构；本机 Clang 23 接受两行，用 `-fno-elide-constructors` 时对有副作用的版本也不输出任何复制或移动，相当于已经按 issue 的方向处理。依赖这一点的写法，例如给 `std::optional<T>::emplace` 传一个带转换函数的惰性包装来原地构造不可移动的 `T`，在 Clang 上可行，但标准上还没有依据。

### 编译器支持

特性测试宏是 `__cpp_guaranteed_copy_elision`，值为 `201606L`（[[cpp.predefined]]）。本机 Clang 23 在 `-std=c++17` 及以上定义它，`-std=c++14` 下不定义。本页的例子都在 Clang 23 上验证过。

值类别的完整模型见 [[topics/value-categories]]，这一改动在移动语义演进中的位置见 [[history/move-semantics]]。

## 思考题

!!! question "1"
    `std::atomic<int> f() { std::atomic<int> a(0); return a; }` 在 C++17 中能编译吗？改成 `return std::atomic<int>(a.load());` 呢？

<details markdown="1">
<summary>答案</summary>

前者不能。`return a;` 返回的是具名变量，`a` 作为 xvalue 去初始化结果对象，需要移动或复制构造函数，`std::atomic` 两者都没有；NRVO 只是允许的省略（[[class.copy.elision#1]]），不免除这个检查。后者可以：操作数是同类型的 prvalue，按 [[dcl.init#15.6.1]] 直接初始化调用的结果对象。
</details>

!!! question "2"
    `struct P { std::mutex m; };` 之后，`const P& r = P();` 和 `P p = P();` 各创建了几个 `P` 对象？哪一个有临时对象？

<details markdown="1">
<summary>答案</summary>

各一个。`P p = P();` 中 `P()` 的结果对象就是 `p`，没有临时对象。`const P& r = P();` 中引用要绑定到 glvalue，`P()` 经临时量实质化（[[conv.rval#1]]）成为一个临时对象，其寿命延长到与 `r` 相同（[[class.temporary]]）。两者都不需要 `P` 的复制或移动构造函数。
</details>

!!! question "3"
    为什么 `T x = T(T(T()));` 在 C++17 中一定只构造一次，而 `T x = static_cast<T&&>(T());` 不是？

<details markdown="1">
<summary>答案</summary>

前者每一层都是同类型 prvalue 初始化同类型对象，结果对象一路传到 `x`。后者的 `static_cast<T&&>` 要把引用绑定到 `T()`，于是实质化一个临时对象，表达式成为 xvalue；`x` 再从这个 xvalue 移动构造，一共两个对象。只有 prvalue 能把结果对象传下去，任何产生 glvalue 的包装都会打断它。
</details>
