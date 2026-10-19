---
title: mixin
summary: 用继承把几个互不相关、可复用的小类拼成一个类：以派生类为参数的 CRTP 式 mixin 和以基类为参数的分层 mixin，构造函数怎样穿过各层，名字冲突怎样解决，空基类优化下的大小，overloaded 惯用法，以及 deducing this 能替代哪些 mixin。
status: draft
order: 40
since: c++98
papers: P0136R1, P0195R2, P0017R1, P1816R0, P0840R2, P0847R7, P1185R2
related: namespace.udecl, class.inhctor.init, class.member.lookup, class.mi, intro.object, dcl.attr.nouniqueaddr, class.prop, over.match.class.deduct, view.interface, patterns/crtp, patterns/policy-based-design, patterns/visitor, topics/two-phase-lookup, topics/lambdas, toolchain/object-layout-and-vtables
tags: mixin, 继承, CRTP, 继承构造函数, 空基类优化, deducing this, 模式
updated: 2026-10-19
---

!!! tldr
    - mixin 是只提供一种能力的小类，靠继承拼进目标类。以派生类为模板实参的叫自上而下的 mixin（CRTP 式），以基类为模板实参的叫自下而上的 mixin（分层式），后者的层次顺序决定行为。
    - 分层 mixin 靠名字隐藏截获调用，靠 `using Base::Base;` 继承构造函数；各层自己的数据成员必须有默认成员初始化器，否则继承来的构造函数不会初始化它们。
    - 两个 mixin 有同名成员时，成员名查找在重载决议之前就报歧义，参数列表不同也一样；在派生类里用 using 声明把它们拉进同一个作用域即可。
    - 空的 mixin 基类通常不占空间，但同类型的两个空基类子对象必须地址不同，会多占字节；`overloaded` 是最常见的空 mixin 组合。
    - C++23 的 deducing this 能替代只需要访问派生类的 mixin，不能替代需要每个派生类各有一份状态或需要在签名里写出派生类型的 mixin。

## 三种互不相关的能力

一个二维点类型需要三样东西：能用 `!=` 比较，能打印自己，能统计当前有多少个实例。这三样功能彼此无关，也会被许多其他类重复需要。

手写到每个类里会到处重复。做成虚函数接口也不合适：`!=` 要接收两个具体类型的参数，计数要求每个类有自己的计数器，而且虚函数给每个对象加一个 vptr。

**mixin** 的做法是把每种能力写成一个独立的小类，目标类继承它们，从而获得这些成员。这里的继承是为了复用代码，不表示目标类是一种 mixin。按小类怎样得知目标类，分成两个方向：

| | 写法 | 小类知道什么 | 典型用途 |
|---|---|---|---|
| 自上而下（mixin from above） | `struct Point : Printable<Point>` | 派生类的类型 | 根据派生类已有的成员生成新成员 |
| 自下而上（mixin from below） | `Logging<Stack>` | 基类的类型 | 包装基类已有的成员，加一层行为 |

## 自上而下：把派生类作为模板实参

```cpp run title="above.cpp" ok
#include <cstdio>
#include <string>

template<class D>
struct Equality {
  friend bool operator!=(const D& a, const D& b) {
    return !(a == b);
  }
};

template<class D>
struct Printable {
  void print() const {
    const D& self = static_cast<const D&>(*this);
    std::printf("%s\n", self.to_string().c_str());
  }
};

template<class D>
struct Counted {
  static inline int alive = 0;
  Counted() { ++alive; }
  Counted(const Counted&) { ++alive; }
  ~Counted() { --alive; }
};

struct Point : Equality<Point>, Printable<Point>,
               Counted<Point> {
  int x = 0, y = 0;
  Point(int x, int y) : x(x), y(y) {}
  friend bool operator==(const Point& a, const Point& b) {
    return a.x == b.x && a.y == b.y;
  }
  std::string to_string() const {
    return "(" + std::to_string(x) + ", " + std::to_string(y) + ")";
  }
};

int main() {
  Point a{1, 2}, b{3, 4};
  a.print();                                   // (1, 2)
  std::printf("%d\n", a != b);                 // 1
  std::printf("%d\n", Counted<Point>::alive);  // 2
}
```

每个 mixin 都以派生类 `D` 为模板实参，这种写法叫 CRTP（奇异递归模板模式），它本身的机制和变体见 [[patterns/crtp|CRTP 与静态多态]]。这里只看三个 mixin 各自依赖哪条规则：

- `Printable` 在成员函数里把 `*this` 向下转换成 `const D&`。只要这个对象确实是某个 `D` 对象的基类子对象，结果就指向那个 `D` 对象（[[expr.static.cast#2]]）。成员函数的定义要到被调用时才实例化（[[temp.inst#3]]），那时 `D` 已经是完整类型，所以能用 `D::to_string`。
- `Equality` 定义了一个隐藏友元（只在类内声明的友元函数），它不能被普通查找找到，只在实参类型的关联类里由 ADL 找到，见 [[topics/name-lookup-and-customization]]。签名里写的是 `D`，所以它只匹配 `Point`。
- `Counted<Point>` 和 `Counted<Line>` 是两个不同的类，各有一个静态成员 `alive`。每个派生类自动得到自己的计数器，这是把派生类型作为模板实参的直接收益。

标准库里的 `std::ranges::view_interface<D>`（[[view.interface.general]]）就是这种 mixin：派生类只要提供 `begin()` 和 `end()`，它就补上 `empty()`、`operator bool`、`front()`、`size()` 等成员。`std::enable_shared_from_this<T>`（[[util.smartptr.enab]]）也是。

有些 mixin 已经被语言特性取代。C++20 起，`a != b` 会被改写成 `!(a == b)`，`<`、`>` 等可以由默认的 `operator<=>` 生成（[[P1185R2]]），`Equality` 这类比较 mixin 就不再需要了：

<div class="compare" markdown="1">

```cpp
// C++17：靠 mixin 补齐 !=
struct P : Equality<P> {
  int x, y;
  friend bool operator==(
      const P&, const P&);
};
```

```cpp
// C++20：一行默认的 ==
#include <compare>
struct P {
  int x, y;
  bool operator==(const P&) const
    = default;
  auto operator<=>(const P&) const
    = default;
};
```

</div>

## 自下而上：把基类作为模板实参

另一个方向是让 mixin 继承自它的模板形参。`Counting<B>` 在 `B` 之上加一层计数，`B` 可以是任何有 `push` 的类：

```cpp run title="layers.cpp" ok
#include <cstdio>
#include <vector>

struct IntStack {
  std::vector<int> v;
  void push(int x) { v.push_back(x); }
  std::size_t size() const { return v.size(); }
};

template<class Base>
struct Counting : Base {
  int pushes = 0;
  void push(int x) { ++pushes; Base::push(x); }
};

template<class Base>
struct NonNegative : Base {
  void push(int x) {
    if (x < 0) return;          // 拒绝负数
    Base::push(x);
  }
};

template<class S>
void feed(S& s) { for (int x : {3, -1, 4, -1, 5}) s.push(x); }

int main() {
  Counting<NonNegative<IntStack>> a;   // 先计数，再过滤
  NonNegative<Counting<IntStack>> b;   // 先过滤，再计数
  feed(a); feed(b);
  std::printf("a: pushes=%d size=%zu\n", a.pushes, a.size());  // 5 3
  std::printf("b: pushes=%d size=%zu\n", b.pushes, b.size());  // 3 3
}
```

两个类型由同样的三个部件组成，行为却不同：`a` 统计所有调用，`b` 只统计通过过滤的调用。调用从最外层开始，一层层往里传，所以层次顺序就是执行顺序。这一点与下一节的并列 mixin 不同。

这种写法依赖两条查找规则。

第一，派生类里声明的 `push` 隐藏了基类的 `push`。在类 `C` 中查找名字时，只要 `C` 自己的作用域里有这个名字，查找就到此为止，不再进入基类（[[class.member.lookup#3]]）。所以 `a.push(x)` 找到的是最外层的 `Counting::push`，要调用下一层必须写 `Base::push`。

第二，`Base` 是**依赖基类**（[[g:dependent-base-class|dependent base class]]），即类型依赖于模板形参的基类。在模板定义中做非限定查找时，不会进入依赖基类的作用域（[[class.member.lookup#4]]）。所以各层用基类的成员时，要写 `Base::` 或 `this->`：

```cpp title="dependent.cpp" error
#include <cstddef>
struct IntStack {
  void push(int) {}
  std::size_t size() const { return 0; }
};
template<class Base>
struct Bounded : Base {
  void push(int x) {
    if (size() < 8)          // error: 依赖基类的成员不参与非限定查找
      Base::push(x);
  }
};
int main() { Bounded<IntStack> b; b.push(1); }
```

Clang 在模板定义处就报 `use of undeclared identifier 'size'`。改成 `this->size()` 后，名字成为依赖名，推迟到实例化时在 `Base` 里查找，详见 [[topics/two-phase-lookup]]。

<details class="fine" markdown="1"><summary>用一个元函数按顺序套上多层</summary>

层数多了以后，`Counting<NonNegative<Locked<IntStack>>>` 要从里往外读。可以写一个元函数，按书写顺序从内到外套：

```cpp run title="compose.cpp" ok
#include <type_traits>
struct IntStack { void push(int) {} };
template<class B> struct Counting : B {};
template<class B> struct NonNegative : B {};

template<class Base, template<class> class... Layers>
struct compose { using type = Base; };

template<class Base, template<class> class L,
         template<class> class... Rest>
struct compose<Base, L, Rest...>
  : compose<L<Base>, Rest...> {};

template<class Base, template<class> class... Layers>
using compose_t = compose<Base, Layers...>::type;

static_assert(std::is_same_v<
  compose_t<IntStack, NonNegative, Counting>,
  Counting<NonNegative<IntStack>>>);
int main() {}
```

结果类型没有变，错误信息和调试器里看到的仍是嵌套的全名。

</details>

## 构造函数怎样穿过各层

最底层的类往往需要构造参数。每一层都手写一遍转发构造函数很繁琐，C++11 的**继承构造函数**（[[g:inherited-constructor|inherited constructor]]）解决了这个问题：

```cpp run title="inherit_ctor.cpp" ok
#include <cstdio>
#include <string>
#include <utility>

struct Connection {
  std::string host; int port;
  Connection(std::string h, int p) : host(std::move(h)), port(p) {}
  explicit Connection(int p) : Connection("localhost", p) {}
};

template<class Base>
struct Retrying : Base {
  using Base::Base;           // 继承 Base 的全部构造函数
  int max_retries = 3;        // 必须有默认成员初始化器
};

template<class Base>
struct Timed : Base {
  using Base::Base;
  long timeout_ms = 1000;
};

int main() {
  Timed<Retrying<Connection>> c("example.org", 443);
  Timed<Retrying<Connection>> d(8080);
  auto e = c;                 // 复制构造函数是隐式声明的，不是继承来的
  std::printf("%s:%d retries=%d timeout=%ld\n",
              e.host.c_str(), e.port, e.max_retries, e.timeout_ms);
  std::printf("%s:%d\n", d.host.c_str(), d.port);
}
```

输出 `example.org:443 retries=3 timeout=1000` 和 `localhost:8080`。

¶2 如果 using 声明命名的是构造函数，派生类就**继承**基类的这组构造函数（[[namespace.udecl#2]]）。¶13 规定，查找派生类的构造函数、构建重载候选集时，它们被当作派生类的构造函数（[[namespace.udecl#13]]）。`Retrying` 继承了 `Connection` 的两个构造函数，`Timed` 又从 `Retrying` 继承了它们，所以两层之外仍能用 `("example.org", 443)` 构造。这是 C++17 按 [[P0136R1]] 重写后的模型：C++11、C++14 的措辞是在派生类里隐式声明一组对应的构造函数，现在则是直接让基类的构造函数参与查找。

用继承来的构造函数初始化时，对象的其余部分像被默认构造函数初始化一样：只有来源那个基类子对象调用该构造函数，其余基类和数据成员按默认方式初始化（[[class.inhctor.init#1]]）。各层的 `max_retries`、`timeout_ms` 因此由默认成员初始化器得到值。没有初始化器的 `int` 成员不会被初始化，这是分层 mixin 最容易漏掉的地方。

继承来的构造函数保留原来的性质。`Connection(int)` 是 `explicit` 的，`Timed<Retrying<Connection>> d = 8080;` 同样非良构。复制、移动构造函数实际上不会被继承：只有一个实参、而且实参类型与派生类相关时，继承来的复制、移动构造函数被排除出候选集（[[over.match.funcs.general#9]]），派生类使用自己隐式声明的版本。

!!! pitfall "不要用万能转发构造函数代替 `using Base::Base`"
    不用继承构造函数时，常见的写法是一个变参模板构造函数，把所有实参完美转发给基类。它会在复制时抢在复制构造函数之前被选中：
    ```cpp run title="forwarding.cpp" ok
    #include <cstdio>
    #include <utility>

    struct Base { int id = 0; Base(int i) : id(i) {} };

    template<class B>
    struct Counting : B {
      template<class... A>
      Counting(A&&... a) : B(std::forward<A>(a)...) {}
      int calls = 0;
    };

    int main() {
      Counting<Base> x(7);
      x.calls = 5;
      Counting<Base> y = x;   // 选中了模板，而不是复制构造函数
      std::printf("id=%d calls=%d\n", y.id, y.calls);   // id=7 calls=0
    }
    ```
    `x` 是非 const 左值，模板实例化出的 `Counting(Counting&)` 比隐式的 `Counting(const Counting&)` 匹配得更好。它把 `x` 转发给 `Base` 的复制构造函数，本层的 `calls` 被重新初始化为 0。程序良构，结果却不对。继承构造函数没有这个问题。

## 可变参数 mixin

自上而下的 mixin 数量可以由使用者决定。把它们写成模板模板形参包，在基类说明符里展开：

```cpp run title="variadic.cpp" ok
#include <cstdio>

template<class D>
struct Named {
  const char* name() const { return static_cast<const D&>(*this).tag; }
};

template<class D>
struct Greeter {
  void greet() const {
    std::printf("hello, %s\n", static_cast<const D&>(*this).name());
  }
};

template<template<class> class... Skills>
struct Robot : Skills<Robot<Skills...>>... {
  const char* tag = "R2";
};

int main() {
  Robot<Named, Greeter> r;
  r.greet();                                   // hello, R2
  static_assert(sizeof(r) == sizeof(const char*));
}
```

后接 `...` 的基类说明符是一个**包展开**（[[g:pack-expansion|pack expansion]]，[[class.derived.general#4]]），每个元素成为一个直接基类。

基类说明符里必须写 `Robot<Skills...>`，不能只写 `Robot`。类作用域只从成员说明开始（[[basic.scope.class#1]]），基类列表不在其中，那里还看不到**注入类名**（[[g:injected-class-name|injected-class-name]]），即类内部指代自身的那个名字。写成 `Skills<Robot>...` 时，`Robot` 指的是类模板本身，Clang 报 `use of class template 'Robot' requires template arguments`。

这些基类是并列的，彼此之间没有转发关系，调用哪个由名字查找决定，不存在上一节的层次顺序。顺序只影响构造和析构：直接基类按基类列表中的顺序初始化（[[class.base.init#15.2]]），逆序析构。

[[class.mi#3]] 禁止同一个类重复作为直接基类，所以 `Robot<Named, Named>` 非良构。

## 名字冲突

两个 mixin 都提供 `dump`，一个按 JSON 输出、带缩进参数，另一个按 XML 输出、不带参数：

```cpp title="clash.cpp" error
#include <string>
template<class D> struct JsonDump {
  std::string dump(int) const { return "{}"; }
};
template<class D> struct XmlDump {
  std::string dump() const { return "<x/>"; }
};
struct Doc : JsonDump<Doc>, XmlDump<Doc> {};
int main() {
  Doc d;
  d.dump();     // error: 两个基类里都找到 dump，查找有歧义
}
```

参数列表明明不同，调用却非良构。原因是成员名查找发生在重载决议之前，而且只看名字。`Doc` 自己没有 `dump`，于是查找进入两个基类，得到两个不同的声明集合。合并它们时，声明集合不同，结果是无效集合（[[class.member.lookup#5.2]]）；查找结果是无效集合时程序非良构（[[class.member.lookup#6]]）。重载决议根本没有机会运行。

解决办法是在派生类里写 using 声明，把两个 `dump` 都变成 `Doc` 作用域里的声明。查找在 `Doc` 中就找到了它们，不再进入基类：

```cpp run title="clash_fixed.cpp" ok
#include <cstdio>
#include <string>
template<class D> struct JsonDump {
  std::string dump(int indent) const { return "{" + std::to_string(indent) + "}"; }
};
template<class D> struct XmlDump {
  std::string dump() const { return "<x/>"; }
};
struct Doc : JsonDump<Doc>, XmlDump<Doc> {
  using JsonDump::dump;      // 两个 dump 都成为 Doc 作用域里的声明
  using XmlDump::dump;
};
int main() {
  Doc d;
  std::printf("%s %s\n", d.dump().c_str(), d.dump(2).c_str());  // <x/> {2}
}
```

做重载决议时，using 声明引入的函数被当作派生类的直接成员（[[namespace.udecl#12]]）。两个 `dump` 签名不同，可以正常重载。

可变参数的情况下，using 声明也可以展开：`using Skills<Robot>::dump...;`（[[P0195R2]]，C++17）。

using 声明不能解决另一种歧义：同一个基类经两条路径出现两次时，using 声明指定的是基类的成员，而不是某个具体的子对象，无法选出其中一个（[[namespace.udecl#15]]）。这种情况只能改继承结构，或者在调用处显式转换到某一条路径。

## overloaded：用 lambda 拼成的 mixin

最常见的 mixin 组合是把几个 lambda 合成一个重载集，传给 `std::visit`，即 **overload 模式**（[[g:overload-pattern|overload pattern]]）：

```cpp run title="overloaded.cpp" ok
#include <cstdio>
#include <string>
#include <variant>

template<class... Ts>
struct overloaded : Ts... {
  using Ts::operator()...;
};

int main() {
  std::variant<int, double, std::string> v = 3.5;
  auto f = overloaded{
    [](int i)                { std::printf("int %d\n", i); },
    [](double d)             { std::printf("double %g\n", d); },
    [](const std::string& s) { std::printf("string %s\n", s.c_str()); },
  };
  std::visit(f, v);                              // double 3.5
  static_assert(sizeof(f) == 1);
}
```

每个 lambda 都是一个类（闭包类型，见 [[topics/lambdas]]），`overloaded` 继承它们，就是以基类为参数的 mixin，只是各层并列、互不转发。这三行代码用到了四条规则：

| 写法 | 依赖的规则 |
|---|---|
| `: Ts...` | 基类说明符的包展开（[[class.derived.general#4]]） |
| `using Ts::operator()...;` | using 声明的包展开（[[P0195R2]]），否则 `operator()` 的查找有歧义，原因同上一节 |
| `overloaded{l1, l2, l3}` | 有基类的类也可以是聚合，基类是它的头几个元素（[[dcl.init.aggr#1]]、[[dcl.init.aggr#2]]，[[P0017R1]]） |
| 不写模板实参 | C++20 起，聚合类模板可以从花括号初始化器推导模板实参（[[over.match.class.deduct#1]]，[[P1816R0]]） |

C++17 没有聚合的类模板实参推导，需要补一条推导指引 `template<class... Ts> overloaded(Ts...) -> overloaded<Ts...>;`。本机 Clang 23 用 `-std=c++17` 编译上面的代码，报 `no viable constructor or deduction guide`。

三个 lambda 都没有捕获，是空类，`sizeof(f)` 为 1。如果它们分别按引用捕获一个变量，本机测得 `sizeof(f)` 为 16，即两个指针，空基类优化同样适用于各个闭包基类。具体的分派方式见 [[patterns/visitor|访问者：双重分派与 std::visit]]。

## 空基类优化：mixin 占多少空间

大多数 mixin 没有数据成员，只贡献成员函数。按 C++ 对象模型，一个完整对象至少占 1 字节，但**潜在重叠子对象**（[[g:potentially-overlapping-subobject|potentially-overlapping subobject]]）可以是零大小的。基类子对象就属于潜在重叠子对象（[[intro.object#7]]）；没有非静态数据成员的标准布局类作为基类时，标准直接规定它是零大小（[[intro.object#8]]）。这就是**空基类优化**（empty base optimization，EBO），它让 mixin 几乎没有空间代价。

但地址规则有一个例外。两个子对象可以同址的条件之一是：至少一个是零大小的，而且两者类型不相似（[[intro.object#10.3]]）。同类型的两个子对象必须地址不同。几个 mixin 共享一个空的标记基类时，就会碰到这条规则：

```cpp run title="ebo.cpp" impl
#include <cstdio>
struct Tag {};
template<class D> struct M1 {};
template<class D> struct M2 {};
template<class D> struct M3 {};
template<class D> struct T1 : Tag {};   // 三个 mixin 共享 Tag
template<class D> struct T2 : Tag {};
template<class D> struct T3 : Tag {};

struct A : M1<A>, M2<A>, M3<A> { int x; };
struct B : M1<B>, M2<B>, M3<B> {};
struct N : T1<N>, T2<N>, T3<N> {};
struct C : T1<C>, T2<C> { int x; };
struct K : T1<K>, T2<K> { char c; };
struct L : M1<L>, M2<L> { char c; };
struct E : Tag { Tag t; int x; };
struct F : Tag { [[no_unique_address]] Tag t; int x; };

int main() {
  std::printf("A=%zu B=%zu N=%zu C=%zu K=%zu L=%zu E=%zu F=%zu\n",
              sizeof(A), sizeof(B), sizeof(N), sizeof(C),
              sizeof(K), sizeof(L), sizeof(E), sizeof(F));
}
```

本机 Clang 23（arm64，Itanium ABI）的结果，偏移来自 `-Xclang -fdump-record-layouts`：

| 类 | 组成 | `sizeof` | 说明 |
|---|---|---|---|
| `A` | 三个不同的空 mixin + `int` | 4 | 三个基类都在偏移 0，与 `x` 同址 |
| `B` | 三个不同的空 mixin | 1 | 完整对象至少 1 字节 |
| `N` | 三个 mixin，各含一个 `Tag` | 3 | 三个 `Tag` 必须在不同地址：偏移 0、1、2 |
| `C` | 两个含 `Tag` 的 mixin + `int` | 4 | 第二个 `Tag` 在偏移 1，落在 `x` 的字节里，没有多占空间 |
| `K` | 两个含 `Tag` 的 mixin + `char` | 2 | 第二个 `Tag` 在偏移 1，`char` 只有 1 字节，多出 1 字节 |
| `L` | 两个不同的空 mixin + `char` | 1 | 对照组 |
| `E` | 空基类 `Tag` + `Tag` 成员 + `int` | 8 | 成员 `t` 不能与基类同址，放到偏移 1，`x` 只能对齐到 4 |
| `F` | 同上，成员标 `[[no_unique_address]]` | 4 | `t` 仍在偏移 1，但可以与 `x` 重叠 |

同类型的空子对象不一定多占空间：只要后面有足够大的、类型不同的数据成员，它们可以落在那些字节里（`C`、`F`）。代价出现在类本身几乎为空、或者数据很小的时候（`N`、`K`），而无状态的策略对象、标记类型恰好是这种情况。

同类型的基类还会让类失去**标准布局**（[[g:standard-layout-class|standard-layout class]]）：标准布局类最多有一个给定类型的基类子对象（[[class.prop#2.5]]）。本机 `std::is_standard_layout_v` 对 `A` 为真，对 `C`、`E` 为假。

!!! impl "MSVC 与多个空基类"
    以上是 Itanium C++ ABI（GCC 和 Clang 在 Linux、macOS 上使用）的行为。按微软的文档，MSVC 默认只对第一个空基类做空基类优化，多个空基类时要在类上加 `__declspec(empty_bases)` 才会全部压缩；它也忽略 `[[no_unique_address]]`，另有 `[[msvc::no_unique_address]]`。本机无法验证 MSVC，跨平台的库需要分别测量。

不想继承时，也可以把 mixin 改成 `[[no_unique_address]]` 成员（[[dcl.attr.nouniqueaddr]]），大小同样可以为零。但成员不会把自己的成员函数带进类的接口，需要再手写转发，这正是 mixin 要避免的。布局的更多细节见 [[toolchain/object-layout-and-vtables]]。

## deducing this：不用模板形参的 mixin

C++23 的**显式对象参数**（[[g:explicit-object-parameter|explicit object parameter]]，[[dcl.fct#8]]，[[P0847R7]]）让成员函数把调用它的对象作为第一个形参，类型由推导得到。很多 CRTP 式 mixin 因此不再需要模板形参：

<div class="compare" markdown="1">

```cpp
// CRTP：基类要知道 D
template<class D>
struct Printable {
  void print() const {
    auto& self =
      static_cast<const D&>(*this);
    puts(self.str().c_str());
  }
};
struct Point : Printable<Point> {
  std::string str() const;
};
```

```cpp
// C++23：self 的类型靠推导
struct Printable {
  void print(this const auto& self)
  {
    puts(self.str().c_str());
  }
};

struct Point : Printable {
  std::string str() const;
};
```

</div>

推导出的是调用表达式中对象的静态类型。这带来一个好处，也带来一个限制：

```cpp run title="deducing_this.cpp" ok
#include <cstdio>
#include <string>

struct Printable {                       // 不再是模板
  void print(this const auto& self) {
    std::printf("%s\n", self.to_string().c_str());
  }
};

struct Point : Printable {
  int x = 1, y = 2;
  std::string to_string() const {
    return std::to_string(x) + "," + std::to_string(y);
  }
};

struct Point3 : Point {
  int z = 3;
  std::string to_string() const {
    return Point::to_string() + "," + std::to_string(z);
  }
};

int main() {
  Point3 p;
  p.print();                         // 1,2,3：self 推导为 Point3
  const Point& r = p;
  r.print();                         // 1,2：self 推导为 Point
}
```

好处是 `Point3` 再派生一层也能用上自己的 `to_string`。CRTP 版本里 `Printable<Point>` 把 `D` 固定成了 `Point`，`Point3` 调用 `print` 只会打印 `1,2`。限制是通过 `const Printable&` 调用 `print` 时，`self` 就是 `Printable`，找不到 `to_string`，实例化失败。

deducing this 不能替代所有自上而下的 mixin：

| mixin 需要 | CRTP | deducing this |
|---|---|---|
| 成员函数里访问派生类成员 | 可以 | 可以，且对更深的派生类也有效 |
| 每个派生类各有一份静态状态（`Counted<D>`） | 可以 | 不行：基类只有一个，静态成员也只有一份 |
| 在签名里写出派生类型（`operator!=(const D&, const D&)`） | 可以 | 不行：非成员函数没有对象参数可推导 |
| 构造、析构时执行代码 | 可以 | 可以，但此时不知道派生类型 |
| 成员函数不是模板 | 是 | 否：每个调用类型实例化一次，必须放在头文件里 |

## 代价

运行时，分层 mixin 只是静态绑定的函数调用，内联后与手写代码相同。本机把前面的 `Counting<NonNegative<IntStack>>::push` 和一个手写的等价函数（计数、判断符号、写入数组）分别用 `-O2` 编译，两者生成的 arm64 指令逐条相同，共 9 条。

代价在编译期和可读性上。每一种组合都是一组新的模板特化，各层的成员函数分别实例化。类型名也随层数增长，五层包装的 `push` 在本机的修饰名有 131 个字符，反修饰后是：

```text
void Locked<Logging<NonEmpty<Counting<Stack<std::string>>>>>::push<std::string>(std::string)
```

（libc++ 的 `std::string` 还会展开成 `std::__1::basic_string<char, ...>`。）错误信息也会穿过所有层次。下面每层都用 `auto` 形参转发，传错类型时：

```cpp title="deep_error.cpp" error
#include <string>
#include <vector>
template<class T> struct Stack { std::vector<T> v; void push(T x) { v.push_back(std::move(x)); } };
template<class B> struct Counting : B { void push(auto x) { B::push(std::move(x)); } };
template<class B> struct NonEmpty : B { void push(auto x) { B::push(std::move(x)); } };
template<class B> struct Logging : B { void push(auto x) { B::push(std::move(x)); } };
template<class B> struct Locked : B { void push(auto x) { B::push(std::move(x)); } };
using S = Locked<Logging<NonEmpty<Counting<Stack<std::string>>>>>;
void use(S& s) { s.push(42); }   // error: int 不能转换为 std::string
```

Clang 23 在最内层 `Counting::push` 报错，再附上四条 `in instantiation of function template specialization ...` 的注释，每条带一个完整的嵌套类型名，整个诊断 40 行。如果各层的 `push` 用确定的参数类型，错误会直接出现在调用处。调试器里单步进入 `s.push` 也要依次经过每一层。

## 陷阱

### 层内的自调用会绕过外层

分层 mixin 没有虚函数，底层类调用自己的成员时，调用的是底层的版本：

```cpp run title="self_call.cpp" ok
#include <cstdio>
#include <initializer_list>
#include <vector>

struct IntStack {
  std::vector<int> v;
  void push(int x) { v.push_back(x); }
  void push_all(std::initializer_list<int> xs) {
    for (int x : xs) push(x);        // 调用的是 IntStack::push
  }
};

template<class Base>
struct NonNegative : Base {
  void push(int x) { if (x >= 0) Base::push(x); }
};

int main() {
  NonNegative<IntStack> s;
  s.push(-1);              // 被过滤
  s.push_all({-2, -3});    // 绕过了过滤层
  std::printf("%zu\n", s.v.size());   // 2
}
```

外层只能截获从外部、经过外层类型发起的调用。需要底层回调到最外层时，底层就得知道最外层的类型，这又回到了 CRTP 或 deducing this。

### 向基类转换也会绕过外层

`NonNegative<IntStack>` 可以隐式转换成 `IntStack&`，传给接受 `IntStack&` 的函数后，所有过滤都不再生效。不希望这样时用 `protected` 或 `private` 继承，再用 using 声明公开需要的成员。

### 本层的数据成员没有初始化器

继承构造函数不会初始化它们，见上文。

### 同类型的空基类

几个 mixin 继承同一个标记类，会多占空间并失去标准布局，见上文的表。

## 什么时候用

| 情形 | 建议 |
|---|---|
| 根据派生类已有的成员补齐一组接口（如 `view_interface`） | 自上而下的 mixin；只需访问派生类成员时，C++23 可改用 deducing this |
| 每个派生类需要独立的静态状态或以派生类型为参数的友元 | 自上而下的 mixin（CRTP） |
| 在已有类的操作前后加检查、计数、加锁、日志 | 自下而上的分层 mixin，注意顺序和自调用 |
| 运行时才决定加哪些行为 | 不适合 mixin，用装饰器或回调对象（运行时组合） |
| 要组合的是同一职责的不同实现（分配、线程模型、错误处理） | 见 [[patterns/policy-based-design\|基于策略的设计]]，它同样常用继承来承载策略 |
| 只是比较运算 | C++20 的默认 `==` 和 `<=>`，不需要 mixin |
| 把几个函数对象合成一个重载集 | `overloaded` |

## 思考题

!!! question "为什么 `using` 声明能解决 `dump` 的歧义，却不能解决下面的歧义？"
    ```cpp
    struct Base { void f(); };
    template<class D> struct M1 : Base {};
    template<class D> struct M2 : Base {};
    struct X : M1<X>, M2<X> { using Base::f; };
    void g(X& x) { x.f(); }
    ```

<details markdown="1">
<summary>答案</summary>

`dump` 的两个声明来自不同的类，using 声明把它们引入 `X` 的作用域后，查找在 `X` 中就结束了，得到两个可以重载的函数。

这里只有一个声明 `Base::f`，问题在于 `X` 里有两个 `Base` 子对象。using 声明指定的是基类的成员，而不是某一个子对象（[[namespace.udecl#15]] 的注），调用时仍要把 `x` 转换成 `Base&` 作为对象参数，这个转换有歧义。Clang 报 `ambiguous conversion from derived class 'X' to base class 'Base'`。改写成 `using M1<X>::f;` 也一样，它指定的仍是 `Base::f`。

可行的做法有三种：在 `X` 里定义 `void f() { M1<X>::f(); }`，限定名指明了经由哪个子对象；在调用处写 `static_cast<M1<X>&>(x).f()`；或者让 `M1`、`M2` 虚继承 `Base`，`X` 里就只有一个 `Base` 子对象。

</details>

!!! question "下面的 `Logged` 少了什么？`Logged<Widget> w(42);` 之后 `w.count` 的值是多少？"
    ```cpp
    struct Widget { explicit Widget(int); };
    template<class B> struct Logged : B {
      using B::B;
      int count;
    };
    ```

<details markdown="1">
<summary>答案</summary>

`count` 没有默认成员初始化器。用继承来的 `Widget(int)` 初始化 `Logged<Widget>` 时，除了 `Widget` 基类子对象，其余部分按默认构造函数的方式初始化（[[class.inhctor.init#1]]），`int` 被默认初始化，不执行任何初始化。如果 `w` 是自动存储期的对象，读 `w.count` 在 C++26 中得到错误值（erroneous value），是错误行为；在此之前是 UB。应写成 `int count = 0;`。

</details>

!!! question "`template<template<class> class... Ms> struct X : Ms<X>... {};` 为什么不能编译？"

<details markdown="1">
<summary>答案</summary>

基类列表不在 `X` 的类作用域之内（[[basic.scope.class#1]]），那里查找 `X` 找不到注入类名，只找到类模板 `X` 本身。类模板名不带实参不能作为类型使用，所以要写 `Ms<X<Ms...>>...`。进入类体之后，`X` 才指代当前特化。

</details>
