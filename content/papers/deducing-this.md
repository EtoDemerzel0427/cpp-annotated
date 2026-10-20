---
title: 显式对象形参（P0847）
summary: C++23 允许成员函数把调用它的对象写成带 this 的第一个形参，从而推导出对象的类型、const 和值类别：它要解决的重复代码，提案比较过的几种语法和查找规则，为什么最后不给函数体 this、取地址得到普通函数指针、不允许 virtual，以及推导出派生类型带来的隐藏问题和标准库的用法。
status: draft
order: 16
group: 核心语言
since: c++23
papers: P0847R7, P0839R0, P2445R1, P2637R3, P2797R0, LWG3617, CWG2554, CWG2653, CWG2674, CWG2789
related: dcl.fct, expr.prim.this, over.match.funcs, over.call.func, expr.unary.op, over.over, class.virtual, expr.prim.lambda.closure, forward, variant.visit, expr.cast, patterns/crtp, patterns/mixin, patterns/named-parameters, topics/lambdas, topics/value-categories, topics/type-deduction
tags: deducing this, 显式对象形参, 成员函数, CRTP, lambda, 提案, C++23
updated: 2026-10-19
---

!!! tldr
    - 成员函数的 `const`、`&`、`&&` 限定只能逐个写出，一个访问器要写四遍。P0847R7 让对象成为一个写出来的形参 `this Self&& self`，于是可以像普通函数模板一样推导，一份代码覆盖四种情况。
    - 提案比较了四种语法和三种函数体内的查找规则，最后选择：`this` 写在第一个形参前面；函数体里没有 `this`，也没有隐式的成员访问，一切都经过 `self`。
    - 这样的函数从外面看是非静态成员函数（用 `obj.f()` 调用，不能写 `static`），从里面看像静态成员函数（`&C::f` 是普通函数指针）。它暂时不能是 `virtual`。
    - `Self` 会推导成派生类，这是它能取代一部分 CRTP 的原因，也是最主要的陷阱：`self.x` 可能找到派生类里同名的成员。标准库的成员 `visit` 用 C 风格转换回到基类来避开它。
    - 它是纯扩展，附录 C 没有相关条目。之后有一批 CWG 修正补全规则，其中重写虚函数的问题（CWG2554）仍未解决。

## 同一个函数写四遍

C++11 给成员函数加上了引用限定符（ref-qualifier）：`f() &` 只能在左值上调用，`f() &&` 只能在右值上调用。再加上 C++98 就有的 `const`，一个想把对象的值类别（[[g:value-category|value category]]，见 [[topics/value-categories]]）原样转发出去的访问器，要写四个重载。`std::optional::value()` 就是这样规定的：

```cpp title="before.cpp" run ok
#include <stdexcept>
#include <utility>

template<class T>
class opt {
  T v_; bool has_ = true;
public:
  T& value() & {
    if (!has_) throw std::logic_error("empty");
    return v_;
  }
  const T& value() const& {
    if (!has_) throw std::logic_error("empty");
    return v_;
  }
  T&& value() && {
    if (!has_) throw std::logic_error("empty");
    return std::move(v_);
  }
  const T&& value() const&& {
    if (!has_) throw std::logic_error("empty");
    return std::move(v_);
  }
};
int main() { opt<int> o; o.value() = 1; }
```

四个函数体只有类型和 `std::move` 不同。常见的省事办法是让三个重载转调第四个，中间夹着 `const_cast`；或者都转调一个私有的静态函数模板，把 `*this` 当实参传进去。后者已经说明了问题所在：对普通函数来说，转发引用 `Opt&&` 一次就能推导出四种情况，唯独调用成员函数的那个对象没法这样推导。

这个对象在重载决议里早就是一个形参。标准把它叫做**隐式对象形参**（[[g:implicit-object-parameter|implicit object parameter]]，[[over.match.funcs.general#2]]），它的类型由函数后面的限定符决定：没有限定或带 `&` 时是 "cv `X` 的左值引用"，带 `&&` 时是右值引用（[[over.match.funcs.general#4]]）。问题只在于它不能写出来，也就不能是模板形参。

另外两件事也卡在同一处。lambda 体里没有名字能指代闭包对象自己，所以写不出直接递归的 lambda（[[topics/lambdas]]）。基类想拿到派生类的类型，只能把派生类作为模板实参传给自己，也就是 CRTP（[[patterns/crtp]]）。

## 提案的核心：把对象形参写出来

[[P0847R7]] 允许非静态成员函数的第一个形参前面加 `this`。这个形参叫**显式对象形参**（[[g:explicit-object-parameter|explicit object parameter]]），调用时对象表达式就是它的实参，括号里的第一个实参对应第二个形参（[[expr.call#7]]）。它的类型可以是模板形参，按普通的函数模板实参推导规则推导（[[temp.deduct.call]]）：

<div class="compare" markdown="1">

```cpp
// C++20：四个重载
T& value() &;
const T& value() const&;
T&& value() &&;
const T&& value() const&&;
```

```cpp
// C++23：一个模板
template<class Self>
auto&& value(this Self&& self) {
  if (!self.has_) throw /* … */;
  return std::forward<Self>(self).v_;
}
```

</div>

`Self&&` 是转发引用（[[g:forwarding-reference|forwarding reference]]），在 `const` 左值上调用时 `Self` 推导为 `const opt&`，在右值上调用时推导为 `opt`。`std::forward<Self>(self).v_` 的值类别和 const 于是跟着对象走：

```cpp title="after.cpp" run ok
#include <cstdio>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <utility>

template<class T>
class opt {
  T v_{};
  bool has_ = true;
public:
  template<class Self>
  auto&& value(this Self&& self) {
    if (!self.has_) throw std::logic_error("empty");
    return std::forward<Self>(self).v_;
  }
};

int main() {
  opt<std::string> o;
  const opt<std::string>& c = o;
  static_assert(std::is_same_v<decltype(o.value()), std::string&>);
  static_assert(std::is_same_v<decltype(c.value()), const std::string&>);
  static_assert(std::is_same_v<decltype(std::move(o).value()), std::string&&>);
  static_assert(std::is_same_v<decltype(std::move(c).value()), const std::string&&>);
  o.value() = "hello";
  std::string s = std::move(o).value();     // 移动出来
  std::printf("[%s] [%s]\n", s.c_str(), c.value().c_str());   // [hello] []
}
```

提案的摘要只有一句话：提供一种办法，在成员函数内部得知调用它的表达式是左值还是右值、带不带 const，以及它的类型。下面几节的每个决定，都是在回答"既然对象成了普通形参，其余规则要跟着怎么变"。

## 设计空间

### 语法：四个候选

R0 把 `this` 放在形参声明的中间，写作 `X& this self`。之后的修订版本列出了四种写法（[[P0847R7]] §6.5 保留了这段历史）：

```cpp
// 提案比较过的候选写法，只有 #1 是今天的 C++
struct A {
  int get(this A const& a) { return a.i; }   // #1 带 this 标记的第一个形参
  int get(A const& this) { return this.i; }  // #2 名为 this 的形参
  int get() A const& self { return self.i; } // #3 尾置的对象类型和名字
  int get() A const& { return this->i; }     // #4 尾置的对象类型
  int i;
};
```

#3 和 #4 把类型放在今天写 `const &` 的位置，看起来最接近旧写法，但都有硬伤。#3 有解析问题；#4 没有名字，函数体只能继续用 `this`，而 `this` 的类型要随推导结果变化，lambda 也无处安放这个类型。两者都不能表示按值传递对象。#2 让形参的名字带上语义，并把 `this` 从指针变成对象，与 lambda 捕获 `this` 的含义冲突。#1 没有这些问题，这就是 [[dcl.fct#2]] 文法里 *parameter-declaration* 前面那个可选的 `this`。

### 函数体里还有没有 this

对象形参可以推导成派生类，这让函数体内的名字查找变得微妙。提案用同一个例子比较了三种规则：

```cpp
struct B {
  int i = 0;
  template<class Self> auto&& f1(this Self&&)      { return i; }
  template<class Self> auto&& f2(this Self&&)      { return this->i; }
  template<class Self> auto&& f5(this Self&& self) { return std::forward<Self>(self).i; }
};
struct D : B { double i = 3.14; };   // 隐藏 B::i
```

| 方案 | `this` | 隐式成员访问 `i` | 结果 |
|---|---|---|---|
| 1 | 不可用 | 不可用 | 只有 `f5` 良构；`D().f5()` 返回 `D::i` |
| 2 | 可用，指向 `B` 子对象 | 不可用 | `f2` 总是返回 `B::i`，但 `this` 的 const 要随 `Self` 变化，成了依赖类型 |
| 3 | 可用 | 可用（同 C++17） | `f1` 等同于 `f2` |

最后选的是方案 1。理由是它给出最简单的模型：带显式对象形参的函数就是一个调用语法更方便的静态函数，函数体里唯一的对象就是写出来的那个形参。代价也很清楚，作者必须自己防备 `Self` 是派生类（见后文"推导出派生类型"）。

今天的规则正是这样。`this` 只指向隐式对象成员函数的对象（[[expr.prim.this#1]]），在显式对象成员函数的声明里不能出现（[[expr.prim.this#4]]）；不加限定地使用非静态成员，本来会被改写成 `(*this).m`，在显式对象成员函数里这个改写非良构（[[expr.prim.id.general#2]] 的注）：

```cpp title="no-this.cpp" error
struct B {
  int i = 0;
  void g();
  template<class Self> auto&& f1(this Self&&) { return i; }        // error: 没有隐式的 this->i
  template<class Self> auto&& f2(this Self&&) { return this->i; }  // error: 没有 this
  void f3(this B& self) { g(); }                                   // error: g 需要对象
  void f4(this B& self) { self.g(); }                              // OK
};
```

### 静态还是非静态

方案 1 让这种函数从里面看像静态成员函数，从外面看又必须像非静态成员函数：要用 `obj.f()` 调用，不能单独写出名字。提案把三类函数并排比较：

| | 普通非静态 | 显式对象 | 静态 |
|---|---|---|---|
| 需要对象实参 | 是 | 是 | 否 |
| 函数体内有隐式 `this` | 是 | 否 | 否 |
| 能声明运算符 | 是 | 是 | 否 |
| `&C::f` 的类型 | 成员函数指针 | 函数指针 | 函数指针 |
| `auto f = x.f;` | 不行 | 不行 | 行 |
| 能否 `virtual` | 能 | 待定 | 不能 |

如果把它归为静态成员函数，就得决定 `static` 关键字怎么办：可写可不写，写了等于没写；必须写，lambda 就得写成 `[](this auto self) static {…}`。这两种都不好。R6 起提案改为把它定义成非静态成员函数，并给两类非静态成员函数起了名字：有显式对象形参的叫**显式对象成员函数**（[[g:explicit-object-member-function|explicit object member function]]），其余的叫隐式对象成员函数（[[dcl.fct#8]]）。两者的对象形参合称**对象形参**（[[g:object-parameter|object parameter]]，[[dcl.fct#9]]）。作者还指出，同时适用于两类非静态成员函数的规则，远多于同时适用于静态函数和新函数的规则，按非静态处理需要改的措辞也更少。

实现过程中还出现一个问题：在隐式对象成员函数里不加 `this->` 调用显式对象成员函数，应不应该允许？提案的回答是允许，理由是类的使用者不应受实现方式影响。从 `std::optional<int>` 派生的类在成员函数里写 `value()`，不管标准库用哪种方式实现 `value`，这句话都应该能编译：

```cpp title="implicit-call.cpp" run ok
#include <cstdio>
#include <optional>

struct C {
  int v = 7;
  int get(this const C& self) { return self.v; }
  int twice() const { return get() * 2; }     // 隐式的 (*this).get()
};

struct Big : std::optional<int> {
  using std::optional<int>::optional;
  bool is_big() const { return value() > 42; }   // 不必知道 value() 怎么实现
};

int main() {
  std::printf("%d %d\n", C{}.twice(), Big{50}.is_big());   // 14 1
}
```

这条规则落在 [[over.call.func#3]]：在类的成员里不加限定地调用成员函数时，隐含的对象实参是 `(*this)`，与被调函数是哪一类无关。

### 取地址得到什么

隐式对象成员函数取地址得到成员函数指针。显式对象成员函数有两个选择，提案最初选了成员函数指针，后来改成了普通函数指针。

理由是按值的对象形参。`int h(this Y, int)` 在旧语言里没有对应物，`&Y::h` 只能是函数指针。如果 `int g(this const Y&, int)` 反而得到成员函数指针，同一种语法会产生两类不同的类型，一个模板实例化出来是"成员函数还是自由函数"要看实参。统一为函数指针以后，这些函数在取地址之后就是以对象为第一个实参的普通函数：

```cpp title="pointer.cpp" run ok
#include <cstdio>
#include <functional>
#include <type_traits>

struct Y {
  int v = 10;
  int f(int a) const& { return v + a; }
  int g(this const Y& self, int a) { return self.v + a; }
};
static_assert(std::is_same_v<decltype(&Y::f), int (Y::*)(int) const&>);
static_assert(std::is_same_v<decltype(&Y::g), int (*)(const Y&, int)>);

int main() {
  Y y;
  auto pf = &Y::f;
  auto pg = &Y::g;
  std::printf("%d %d\n", (y.*pf)(1), pg(y, 2));        // 11 12
  std::printf("%d %d\n", std::invoke(pf, y, 3),
                         std::invoke(pg, y, 4));        // 13 14
}
```

对应的措辞有三处。`&` 作用于显式对象成员函数时得到 "指向 T 的指针" 而不是成员指针，并且操作数必须是限定名 `&Y::g`（[[expr.unary.op#3]]）。从重载集合取地址时，显式对象成员函数匹配函数指针类型的目标（[[over.over#4]]）。反过来，`(y.*pg)(1)` 非良构，`y.g` 也不能不调用就单独使用。

### 能不能是 virtual

不能（[[dcl.fct#7]]）。提案讨论了两个障碍。第一是语义差别：`B::f()` 没有引用限定时也能在右值上调用，而 `this D&` 不接受右值。第二是更大的问题，调用约定：显式对象成员函数的调用约定和自由函数一样，虚分派要么生成转接的 thunk，要么把函数按两种约定各生成一份，要么引入一种能表示按值对象形参的新成员指针类型。

提案认为允许 `virtual` 不会带来新的能力，只是风格上的选择，因此先禁止，把门留着：将来如果放开，也只允许同类函数互相重写，显式对象成员函数只重写显式对象成员函数。

为了让这扇门真的留着，提案明确说 `struct D3 : B3 { void f(this D3&); };` 良构，它只是隐藏了 `B3::f`，不重写它。按当前草案，`D3::f` 的对象形参去掉引用后是 `D3`，与 `B3::f` 的 `B3` 不同，两者不对应（[[basic.scope.scope#3]]），也就不重写（[[class.virtual#2]]）。本机 Clang 23 却报告 "an explicit object parameter cannot appear in a virtual function"。重写判定本身还有一个未解决的问题 [[CWG2554]]（当前状态 review）：它指出 [[basic.scope.scope#3]] 的对应规则连 `struct D : B { void f(); }` 是否重写 `B::f` 都判断错了，建议的修正是比较时"忽略显式对象形参"，那样 `D3::f` 就会重写 `B3::f` 并因此非良构。[[dcl.fct]] 的思考题 3 讨论了同一个例子。

### 按值的对象形参

写出来的形参可以不是引用。提案给了三个用途：

- `sorted(this my_vector self)` 这样的函数天然要在副本上工作，右值对象会直接移动进来，不需要模板。
- 小对象按值传递可以少一次间接访问。隐式对象形参总是引用，`string_view` 这类类型的成员函数如果没有内联，就要先从指针里取数据。
- 成员函数协程按值接收对象，协程帧里存的就是副本，不会像 `this` 那样悬垂。

第二点在本机可以直接看到。下面两个函数分别定义在类外，用 `-O2` 编译：

```cpp title="by-value.cpp" ok
#include <cstddef>
struct View {
  const char* p;
  std::size_t n;
  std::size_t size_ref() const;
  std::size_t size_val(this View self);
};
std::size_t View::size_ref() const { return n; }
std::size_t View::size_val(this View self) { return self.n; }
```

本机 Clang 23（arm64）为 `size_ref` 生成 `ldr x0, [x0, #8]`，从 `this` 指向的内存读 `n`；为 `size_val` 生成 `mov x0, x1`，两个成员直接装在寄存器里传进来。这取决于平台的调用约定，16 字节的结构在 AArch64 上按寄存器传递。

### 只推导限定符做不到

多数时候作者只想推导 const 和值类别，并不想要派生类型。`Self&&` 却会把派生类也推导出来，带来两个副作用：后文的隐藏问题，以及每个派生类各实例化一份。提案在 FAQ 里承认了这一点，认为"限制推导结果"是一个与本提案正交的特性，自由函数模板早就有同样的需求，应当一般地解决，而不是为对象形参单独设计一套规则。

## 措辞

!!! std
    An *explicit-object-parameter-declaration* is a *parameter-declaration* with a `this` specifier. ([[dcl.fct#7]])

    带 `this` 说明符的形参声明就是显式对象形参声明。它只能是成员函数或 lambda 的第一个形参，所在函数不能带 cv 或引用限定，不能是 `static` 或 `virtual`。

P0847R7 的措辞分散在五章里，按当前草案的位置整理如下。逐条的规则见各条款页，[[dcl.fct]] 有完整的释义和例子。

| 条款 | 改动 |
|---|---|
| [[dcl.fct#2]] | 形参声明前可以加 `this` |
| [[dcl.fct#7]]–[[dcl.fct#10]] | 出现位置与限制；定义显式对象形参、显式/隐式对象成员函数、对象形参、非对象形参 |
| [[basic.scope.scope#3]] | 两个成员函数何时有对应的对象形参，决定 `void f() const&;` 与 `void f(this const X&);` 是否重复声明 |
| [[expr.prim.this#1]]、[[expr.prim.this#4]] | `this` 只属于隐式对象成员函数 |
| [[expr.call#7]] | 对象表达式成为第一个实参 |
| [[expr.unary.op#3]]、[[over.over#4]] | 取地址得到函数指针 |
| [[over.match.funcs.general#2]] | 只有隐式对象成员函数才额外假设一个隐式对象形参 |
| [[over.best.ics.general#9]] | 转换到隐式对象形参只允许标准转换；注明转换到显式对象形参可以用用户定义转换 |
| [[expr.prim.lambda.closure#6]]、[[expr.prim.lambda.closure#7]] | 有捕获的 lambda，对象形参必须是闭包类型或其派生类；有显式对象形参的调用运算符不是 `const` |
| [[class.mfct.non.static#3]] | 只有隐式对象成员函数可以是虚函数 |

还有一个特性测试宏 `__cpp_explicit_this_parameter`，当前值 `202110L`（[[cpp.predefined]]）。

`this` 原本就是关键字，不可能出现在形参声明开头，所以这是纯扩展，没有旧代码改变含义。

## 后果

### 推导出派生类型：隐藏问题

函数体内的成员访问全都经过 `self`，而 `self` 的静态类型可能是派生类。派生类有同名成员时，`self.i` 找到的就是派生类的那个：

```cpp title="shadow.cpp" run ok
#include <cstdio>
#include <utility>

struct B {
  int i = 1;
  template<class Self>
  auto&& get(this Self&& self) {
    return std::forward<Self>(self).i;        // 从 Self 开始查找 i
  }
  template<class Self>
  auto&& get_b(this Self&& self) {
    return std::forward<Self>(self).B::i;     // 固定为 B::i
  }
};

struct D : B {
  double i = 2.5;                             // 隐藏 B::i
};

int main() {
  D d;
  std::printf("%g\n", static_cast<double>(d.get()));    // 2.5
  std::printf("%d\n", d.get_b());                       // 1
  std::printf("%d\n", static_cast<B&>(d).get());        // 1
}
```

这不是虚函数意义上的覆盖，结果取决于调用处对象的静态类型。在 mixin 和 CRTP 式的用法里，这正是想要的行为；在 `optional::value` 这样只想推导限定符的函数里，它是缺陷。写 `self.B::i` 可以固定到基类成员。

提案把最坏的情形称为"私有继承问题"：派生类私有继承基类，再用 using 声明公开基类的函数。这时 `Self` 是 `D`，而 `D` 到 `B` 的转换在 `B` 的成员函数里不可访问，`self.B::i` 也就非良构：

```cpp title="private-base-bad.cpp" error
#include <utility>
class B {
  int i = 1;
public:
  template<class Self>
  auto&& get(this Self&& self) {
    return std::forward<Self>(self).B::i;
  }
};
struct D : private B {
  double i = 2.5;
  using B::get;
};
int main() {
  D d;
  d.get();   // error: D 到私有基类 B 的转换不可访问
}
```

提案给出的办法是 C 风格转换。用 C 风格转换把派生类转换成它无歧义的基类时，不检查基类的可访问性（[[expr.cast#4.6]]）。先用 `std::forward_like` 算出带上 `Self` 的 const 和值类别的 `B` 引用类型，再转换过去：

```cpp title="private-base.cpp" run ok
#include <cstdio>
#include <type_traits>
#include <utility>

class B {
  int i = 1;
public:
  template<class Self>
  auto&& get(this Self&& self) {
    // B 带上 Self 的 const 和值类别：B&、const B&、B&& ……
    using Base = decltype(std::forward_like<Self>(std::declval<B&>()));
    return ((Base)self).i;   // C 风格转换不检查基类的可访问性
  }
};

struct D : private B {
  double i = 2.5;
  using B::get;
};

int main() {
  D d;
  static_assert(std::is_same_v<decltype(d.get()), int&>);
  static_assert(std::is_same_v<decltype(std::move(d).get()), int&&>);
  std::printf("%d\n", d.get());   // 1
}
```

!!! pitfall "把 `this auto&& self` 当成 `this` 的直接替代"
    把旧代码里的 `this->m` 机械地改成 `self.m`，在没有派生类时行为不变；一旦有派生类定义了同名的 `m`，结果就变了，编译器不会提示。只想推导限定符时，访问成员要写 `self.Base::m`，或者像上面那样先转换回基类。

### 标准库怎样用它

`std::forward_like`（[[P2445R1]]，C++23）是提案里假设存在、但没有一并提出的库设施。`std::forward<decltype(self)>(self).m` 只对真正的成员有效；lambda 的捕获不是可以经由 `self.` 访问的成员，指针、容器里"远处"的数据也不跟着对象的值类别走。`forward_like<T>(x)` 把 `T` 的 const 合并到 `x` 上，再采用 `T` 的值类别（[[forward#6]]）：

```cpp title="forward-like.cpp" run ok
#include <cstdio>
#include <string>
#include <utility>

void submit(const std::string&) { std::puts("copy"); }
void submit(std::string&&)      { std::puts("move"); }

int main() {
  auto cb = [m = std::string("msg")](this auto&& self) {
    submit(std::forward_like<decltype(self)>(m));
  };
  cb();              // copy：左值闭包，可以再调用
  std::move(cb)();   // move：右值闭包，最后一次使用
}
```

P2445R1 说这是 deducing this 最早的用例：同一个回调既能交给会重试的算法（按左值调用），也能交给只调用一次的算法（按右值调用，把捕获移动出去）。

C++26 的成员 `variant::visit`（[[P2637R3]]）是标准里用显式对象形参声明的成员函数，它的 *Effects* 写作 `std::visit(std::forward<Visitor>(vis), (V)self)`，其中 `V` 是带上 `Self` 的 const 和值类别的 `variant` 引用（[[variant.visit#9]]–[[variant.visit#11]]）。这里的 C 风格转换是有意的：提案说明 `variant` 可能是 `Self` 的私有基类，非成员 `std::visit` 不支持这种情况，而库演化组希望成员 `visit` 支持。这正是上一节的私有继承问题和它的解法。

```cpp title="member-visit.cpp" ok
#include <cstdio>
#include <variant>

struct Shape : private std::variant<int, double> {
  using variant::variant;
  using variant::visit;          // 成员 visit：C++26
};

int main() {
  Shape s = 2.5;
  s.visit([](auto x) { std::printf("%g\n", static_cast<double>(x)); });   // 2.5
}
```

按标准这段代码良构。本机 Clang 23 自带的 libc++ 拒绝它：libc++ 用 `static_cast` 实现这次转换，报告 "cannot cast 'Shape' to its private base class"。

另一方面，`std::optional` 的 `value()` 和 `operator*` 在当前草案里仍然是四个重载（[[optional.observe]]）。提案在 FAQ 中转述了标准库实现者的意见：实现内部愿意用它，但要写进标准接口，需要先能约束推导出的类型。原因就是上面两节：推导出的派生类型会改变查找结果，还会为每个派生类多一份实例化。

### 取代一部分 CRTP

基类不再需要知道派生类的名字，派生类型在调用处推导出来。提案用"后置 `++` 由前置 `++` 生成"作为例子：

<div class="compare" markdown="1">

```cpp
template<class D>
struct add_postfix {
  D operator++(int) {
    auto& self =
      static_cast<D&>(*this);
    D tmp(self);
    ++self;
    return tmp;
  }
};
struct Counter
  : add_postfix<Counter> {
  using add_postfix<Counter>
    ::operator++;
  int n = 0;
  Counter& operator++();
};
```

```cpp
struct add_postfix {
  template<class Self>
  auto operator++(this Self& self,
                  int) {
    auto tmp = self;
    ++self;
    return tmp;
  }
};
struct Counter : add_postfix {
  using add_postfix::operator++;
  int n = 0;
  Counter& operator++();
};
```

</div>

两边都需要 using 声明：派生类声明的前置 `operator++` 会隐藏基类所有名为 `operator++` 的函数，这与对象形参怎么写无关。提案里的这个例子省略了它，照抄会在 `c++` 处报错。完整可运行的版本：

```cpp title="postfix.cpp" run ok
#include <cstdio>

struct add_postfix_increment {
  template<class Self>
  auto operator++(this Self& self, int) {
    auto tmp = self;     // Self 是派生类：复制整个对象
    ++self;
    return tmp;
  }
};

struct Counter : add_postfix_increment {
  using add_postfix_increment::operator++;   // 否则被下面的前置 ++ 隐藏
  int n = 0;
  Counter& operator++() { ++n; return *this; }
};

int main() {
  Counter c;
  Counter old = c++;
  std::printf("%d %d\n", old.n, c.n);   // 0 1
}
```

方法链（builder）是另一个典型场景：基类的 setter 返回 `Self&`，派生 builder 的链就不会退化成基类类型，见 [[patterns/named-parameters]]。哪些 CRTP 用法仍然无法替代（每个派生类一份静态数据、基类的成员类型要用到派生类、通过基类引用保留派生类型），见 [[patterns/crtp]] 和 [[patterns/mixin]]。

### 递归 lambda

lambda 的调用运算符也可以有显式对象形参，形参就是闭包对象自己（[[expr.prim.lambda.closure#5]] 的例子）：

<div class="compare" markdown="1">

```cpp
// C++14：把自己当实参传进去
auto fib = [](auto& self, int n)
    -> int {
  return n < 2 ? n
    : self(self, n - 1)
    + self(self, n - 2);
};
fib(fib, 20);   // 6765
```

```cpp
// C++23
auto fib = [](this auto& self,
              int n) -> int {
  return n < 2 ? n
    : self(n - 1) + self(n - 2);
};
fib(20);        // 6765
```

</div>

更早的 [[P0839R0]] 提议为 lambda 引入名字，写作 `[] self (int n) {…}`。P0847R7 的 FAQ 解释了它为什么更容易实现：非泛型 lambda 的体不是模板，`sizeof(self)` 这类表达式必须立即求出答案，而此时闭包类型还不完整。用 `this auto` 时闭包类型写不出来，`self` 的类型总是依赖类型，函数体按现有的模板规则处理，不需要新机制。

有捕获的 lambda 对对象形参的类型多一条限制：它必须是闭包类型、从闭包类型公开且无歧义地派生的类，或者它们的引用（[[expr.prim.lambda.closure#6]]）。否则函数体里访问捕获时，手里的对象根本不是闭包。lambda 的其余细节见 [[topics/lambdas]]。

### 一个模板代替四个重载，重载决议也变了

把四个重载合成一个模板，不只是少写代码。提案指出 `std::not_fn` 这类调用包装器用四个重载实现时有两个无法修正的问题，其中一个是"悄悄退回"：被包装对象的非 const `operator()` 被删除了，包装器的非 const 重载因 SFINAE 被剔除，const 重载却仍然可行，于是调用成功并走了错误的路径。只有一个候选时就不会这样：

```cpp title="not-fn.cpp" run ok
#include <cstdio>
#include <functional>
#include <utility>

// 按限定符分别重载（只写出两个，已足以说明问题）
template<class F>
struct not_fn4 {
  F f;
  template<class... A>
  auto operator()(A&&... a) & -> decltype(!std::invoke(f, std::forward<A>(a)...)) {
    return !std::invoke(f, std::forward<A>(a)...);
  }
  template<class... A>
  auto operator()(A&&... a) const& -> decltype(!std::invoke(f, std::forward<A>(a)...)) {
    return !std::invoke(f, std::forward<A>(a)...);
  }
};

// 一个模板
template<class F>
struct not_fn1 {
  F f;
  template<class Self, class... A>
  auto operator()(this Self&& self, A&&... a)
      -> decltype(!std::invoke(std::forward<Self>(self).f, std::forward<A>(a)...)) {
    return !std::invoke(std::forward<Self>(self).f, std::forward<A>(a)...);
  }
};

struct fun {
  template<class... A> bool operator()(A&&...) = delete;        // 非 const 版本被删除
  template<class... A> bool operator()(A&&...) const { return true; }
};

template<class W>
concept callable = requires(W w) { w(); };

int main() {
  not_fn4<fun> a{};
  std::printf("%d\n", a());                 // 0：悄悄退回到 const 重载
  static_assert(!callable<not_fn1<fun>&>);  // 只有一个候选，不会退回
}
```

本机 Clang 23 的 libc++ 已经这样实现 `std::bind_front` 的调用运算符。

### 后续修正

P0847R7 进入 C++23 之后，下面这些问题陆续得到处理：

| 编号 | 问题 | 结果 |
|---|---|---|
| [[CWG2653]] | 显式对象形参能不能有默认实参 | 不能，文法里 `this` 和 `= 初始化器` 不再出现在同一个形参声明中（[[dcl.fct#2]]） |
| [[CWG2674]] | 构造函数能不能有显式对象形参 | 不能（[[class.ctor.general#7]]） |
| [[CWG2789]] | `f()` 和 `f(this S&) requires true` 之间调用有歧义 | 比较约束时改为比较非对象形参列表和对象形参类型，选更受约束的那个（[[over.match.best.general#2.6]]、[[temp.constr.order#6]]） |
| [[P2797R0]] | `static void f(A);` 与 `void f(this A);` 能否共存 | 能，不视为重复声明；`(&A::f)(A())` 先把重载集合中的每个函数取地址再做重载决议（[[over.call.func#3]]） |
| [[LWG3617]] | `std::function` 的推导指引不认识函数指针形式的 `&F::operator()` | 增加 `R(*)(G, A...)` 形式，推导出 `function<R(A...)>` |
| [[CWG2554]] | 重写虚函数时对象形参怎样比较 | 仍在 review，见上文"能不能是 virtual" |

前三项在本机 Clang 23 上都已按修正后的规则处理：默认实参报告 "the explicit object parameter cannot have a default argument"，构造函数报告 "an explicit object parameter cannot appear in a constructor"，CWG2789 的例子调用带约束的那个。

LWG3617 的结果是 `struct F { int operator()(this const F&, int); };` 时，`std::function h = F{};` 应推导为 `std::function<int(int)>`（[[func.wrap.func.con#16]]）。本机 libc++ 推导成 `std::function<int(const F&, int)>`，随后初始化失败，与标准不符。

### 编译器支持

本机 Clang 23 在 `-std=c++23` 和 `-std=c++2c` 下定义 `__cpp_explicit_this_parameter` 为 `202110L`，本页所有核心语言例子的表现都与标准一致，只有两处例外：`struct D3 : B3 { void f(this D3&); }` 被拒绝（见"能不能是 virtual"），以及上面列出的两处 libc++ 库问题。其他编译器的支持情况本页没有验证。

## 思考题

!!! question "思考题 1"
    `struct X { void k(); void k(this X&); };` 和 `struct Y { void k() &&; void k(this Y&); };` 分别是否良构？

<details markdown="1">
<summary>答案</summary>

`X` 非良构。`X::k()` 是不带引用限定的隐式对象成员函数，比较时去掉引用：它的对象形参类型 `X&` 与 `this X&` 去掉引用后都是 `X`，两个声明有对应的对象形参，非对象形参列表也相同，于是对应，构成重复声明（[[basic.scope.scope#3]]、[[basic.scope.scope#4]]）。

`Y` 良构。`Y::k() &&` 带引用限定，不适用"去掉引用"的那一条，要求对象形参类型完全相同；`Y&&` 与 `Y&` 不同，两者是不同的重载。提案特意让没有引用限定的旧式函数同时与 `&` 和 `&&` 版本冲突，因为没有理由认为不带限定更接近其中某一个。
</details>

!!! question "思考题 2"
    在下面的代码里，`d.name()` 实例化哪个特化，返回什么？如果把 `name` 改成 `std::string name(this const Base& self)`，结果又如何？
    ```cpp
    struct Base {
      std::string tag() const { return "base"; }
      template<class Self>
      std::string name(this const Self& self) { return self.tag(); }
    };
    struct D : Base { std::string tag() const { return "d"; } };
    D d;
    ```

<details markdown="1">
<summary>答案</summary>

模板版本中，`d.name()` 把 `Self` 推导为 `D`，实例化 `Base::name<D>`，`self.tag()` 从 `D` 开始查找，找到 `D::tag`，返回 `"d"`。`static_cast<Base&>(d).name()` 则实例化 `Base::name<Base>`，返回 `"base"`。

非模板版本里对象形参的类型固定为 `const Base&`，`d` 经派生类到基类的转换绑定上去，`self.tag()` 找到 `Base::tag`，返回 `"base"`。两种写法都不涉及虚函数：前者绑定到调用处的静态类型，后者绑定到声明时写下的类型。
</details>

## 小结

| 决定 | 选项 | 理由 |
|---|---|---|
| 语法 | `this` 加在第一个形参前 | 能推导、能按值、能用于 lambda、没有解析问题 |
| 函数体内 | 没有 `this`，没有隐式成员访问 | 模型最简单；代价是要防备派生类的同名成员 |
| 分类 | 非静态成员函数，不能写 `static` | 从外面看与普通成员函数一致，措辞改动更少 |
| 从其他成员调用 | 允许省略 `this->` | 派生类不必知道基类用哪种写法实现 |
| `&C::f` | 普通函数指针 | 与按值形参统一，模板结果类型一致 |
| `virtual` | 暂不允许 | 调用约定和语义差别，且不提供新能力；CWG2554 仍未解决 |
| 只推导限定符 | 不提供 | 与自由函数模板的同类需求一起解决更好 |
