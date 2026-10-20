---
title: 类类型作模板参数（P0732、P1907）
summary: C++20 怎样让类类型和浮点数成为常量模板形参：最初的方案用默认的 <=> 判断两个实参是否相同，暴露出一系列不一致之后改成了按成员比较的结构化类型，这个选择决定了今天 fixed_string、-0.0 和私有成员的各种规则。
status: draft
order: 22
group: 核心语言
since: c++20
papers: P0732R2, P1185R2, P1714R1, P1837R0, P1907R0, P1907R1, P0424R2, P2308R1, P2484R0, P3380R1, P2841R7
related: temp.param, temp.type, temp.arg, over.literal, lex.ext, dcl.type.class.deduct, class.compare, patterns/policy-based-design, topics/compile-time-programming, history/template-metaprogramming
tags: 提案, 模板, 常量模板形参, NTTP, 结构化类型, fixed_string, C++20
updated: 2026-10-19
---

!!! tldr
    - C++17 的常量模板形参只能是整数、枚举、指针、引用这类标量；想把一个字符串当模板实参，只能把它拆成一串 `char`。
    - 难点不在语法，而在判断 `X<a>` 和 `X<b>` 是不是同一个类型：这个判断要在每个翻译单元得出相同的结论，还要能编码进符号名交给链接器。
    - [[P0732R2]] 用编译器生成的比较运算符回答这个问题（先是默认的 `<=>`，后来改成默认的 `==`）；[[P1907R1]] 放弃了与比较运算符的联系，改为按成员逐个比较的结构化类型。
    - 因此今天的规则是：成员必须全部 public；用户写的 `operator==` 完全不参与；`0.0` 和 `-0.0` 是两个不同的实参；字符串字面量仍然不能直接作指针形参的实参，要先复制进一个类对象。

## 问题：字符串进不了模板

模板的**常量模板形参**（[[g:constant-template-parameter]]，以前叫非类型模板形参，即 NTTP）接受一个值而不是一个类型。到 C++17 为止，这个值只能是整数、枚举、指针、成员指针、左值引用或 `std::nullptr_t`。想让一个类型带上一个名字，只能把名字拆成字符：

```cpp run title="char-pack.cpp" std=c++17 ok
#include <cstdio>
// C++17：字符串只能拆成 char 包
template<char... Cs> struct Name {
  static void print() {
    static constexpr char s[] = {Cs..., '\0'};
    std::puts(s);
  }
};
using Hello = Name<'h','e','l','l','o'>;
int main() { Hello::print(); }
```

这种写法难读，也很难由计算得到。此前几篇提案想让字符串字面量运算符模板直接产生这样的 `char` 包，[[P0732R2]] 的动机一节总结说，反对意见主要是编译器处理长 `char` 包的时间和内存代价。[[P0424R2]] 换了思路，允许字符串作模板形参，但实参只能是字符串字面量本身，计算出来的字符串依然放不进模板。

更自然的写法是把字符放进一个类对象。C++11 起类对象已经可以是常量表达式，但它不能作模板实参：

<div class="compare" markdown="1">

```cpp std=c++17 error
struct Point { int x, y; };

// C++17: error
template<Point P> struct At {};
At<Point{1, 2}> a;
```

```cpp std=c++20 ok
struct Point { int x, y; };

// C++20 起 OK
template<Point P> struct At {};
At<Point{1, 2}> a;
```

</div>

本机 Clang 23 用 `-std=c++17` 编译左边，报告 `a non-type template parameter cannot have type 'Point' before C++20`。数组也帮不上忙：形参写成 `char s[6]` 会像函数形参一样调整为 `char*`（[[temp.param#15]]），值又变回了指针。

## 真正的难题：两个实参什么时候相同

模板的每一组实参对应一个特化。`At<Point{1, 2}>` 出现在两个翻译单元里，必须是同一个类型；它的静态成员、成员函数也必须只有一份。标准用 [[temp.type#1]] 判断两个 *template-id* 是否相同，其中常量实参一项要求两个值**模板实参等价**（[[g:template-argument-equivalent]]，¶1.3）。

对标量来说这很简单：整数值相同就相同，指针指向同一个对象就相同。实现上，编译器把实参的值编码进修饰后的符号名，链接器比较符号名就能合并同一个特化。

类类型没有现成的相同概念。[[P0732R2]] 第 4 节把问题表述为一个不变式：对 `template<auto> int i;`，希望 `&i<a> == &i<b>` 当且仅当 `a == b`。C++17 的标量实参基本满足它。到了类类型，论文列出三条路：

| 方案 | 做法 | 代价 |
|---|---|---|
| 放弃不变式 | 按成员比较，不管类自己的 `==` | 类型身份和用户看到的相等可能不一致 |
| 调用用户的 `==` | 编译器、链接器都去求值用户写的比较 | 要验证用户的比较自洽，链接器做不到 |
| 只接受按成员相等的类 | 要求类的比较由编译器生成 | 需要一种语言机制保证这一点 |

P0732R2 选了第三条。第二条不可行的原因在于，链接器只看符号名，只能比较编码后的值；用户的 `operator==` 可能不是等价关系，可能在不同翻译单元里不同，也可能在第一次使用之后才声明，而模板特化的身份必须在全程序一致，否则就是 ODR 违反（[[basic.def.odr]]）。

## P0732R2：用默认的 `<=>` 担保

C++20 同期引入了可以 `= default` 的三路比较运算符 `<=>`（[[class.compare]]）。P0732R2 借用它：如果类和它的所有成员、基类都有类内默认的 `<=>`，结果类型是 `strong_ordering` 或 `strong_equality`，就说这个类型有**强结构相等**（strong structural equality），可以作常量形参。这保证三件事：类有比较运算符，各翻译单元看到同一个比较，而且这个比较就是逐成员比较。

论文给出的概念模型是：一个类类型的形参，相当于为它的每个基类、每个成员（数组则是每个元素）各写一个常量形参。`template<pair<int,int> x>` 约等于 `template<int first, int second>`。

<div class="compare" markdown="1">

```cpp ok
// P0732R2 要求的写法
#include <compare>
struct Point {
  int x, y;
  auto operator<=>(const Point&)
      const = default;
};
template<Point P> struct At {};
At<{1, 2}> a;
```

```cpp ok
// 今天：不需要任何比较运算符
struct Plain { int x, y; };

template<Plain P> struct At2 {};
At2<{1, 2}> b;
```

</div>

两段在今天的 Clang 23 上都能编译，左边多写的 `<=>` 无害但已不必要。同一篇论文还确定了几项保留至今的设计：

- 类类型形参在模板里是一个 `const T` 左值，指称一个具有静态存储期的**模板形参对象**（[[g:template-parameter-object]]）。每个不同的值在全程序只有一个这样的对象，所以可以取它的地址、调用它的 `const` 成员函数（今天的 [[temp.param#13]]）。
- 形参类型可以只写类模板名，由类模板实参推导决定具体类型，`template<fixed_string S>` 配合推导指引就能写 `A<"hello">`（[[temp.param#11]]，¶11.3）。
- 新增**字符串字面量运算符模板**（[[g:string-literal-operator-template]]）：形参是单个类类型常量形参的字面量运算符模板，`"hello"_udl` 被当作 `operator""_udl<"hello">()`（[[over.literal#5]]、[[lex.ext#5]]）。这吸收了 P0424R2 的语法，但形参换成了类类型。
- 含有引用成员的类不能作形参类型。原因是引用有两种相等：`==` 比较被引用的值，而模板实参比较被引用对象的身份。

随后 [[P1185R2]] 把默认 `<=>` 与默认 `==` 拆开，强结构相等也改为要求类内默认的 `==`，P0732 的思路不变：类型身份通过编译器生成的比较运算符来担保。

## 担保失效的地方

P0732 进入 C++20 草案之后，[[P1837R0]] 主张把它整体撤回，[[P1907R0]] 则系统整理了不一致之处。问题都出在同一个前提：相等和身份是两回事，C++17 里早就如此。

第一个例子是枚举。枚举有强结构相等，但用户可以在任何地方为它重载 `operator==`。下面的代码在 C++17 就合法，`==` 说两个枚举值相等，模板却认为它们是两个实参：

```cpp run title="enum-eq.cpp" ok
#include <type_traits>
enum E { ONE, TWO };
constexpr bool operator==(E, E) { return true; }
static_assert(ONE == TWO);

template<E> struct X {};
static_assert(!std::is_same_v<X<ONE>, X<TWO>>);
int main() {}
```

P1837R0 指出，在 P0732 的措辞下，一个含 `E` 成员、带默认 `==` 的类该怎样比较就说不清了：默认的 `==` 要不要调用这个用户写的 `operator==(E, E)`？如果它在类定义之后才声明呢？

P1907R0 把不一致分成两类：

- **(A) 类**：运行期 `x == y` 的结果与 `std::is_same_v<A<x>, A<y>>` 不一致。
- **(B) 类**：一个值直接作模板实参时的行为，与它作为类成员、随类对象作实参时的行为不一致。

它逐一检查了已有的类型：

| 类型 | 直接作实参 | 作类成员 | 不一致 |
|---|---|---|---|
| 引用 | 比被引用对象的身份 | 有引用成员的类不允许 | (A)、(B) |
| 成员指针 | 联合体的 `&U::x`、`&U::y` 是不同实参，但 `==` 为真（[[expr.eq#5]]，¶5.5） | 按 `==` 比较 | (A)、(B) |
| 浮点数 | [[P1714R1]] 提议按位比较 | 浮点的 `<=>` 只是 `partial_ordering`，没有强结构相等 | (A)、(B) |
| 有用户 `==` 的类型 | 枚举可以 | 类不允许 | (A) |

浮点一行值得展开。P1714R1 想支持 `template<double Exp> double pow(double)` 这类接口，提议浮点实参按值表示比较，于是 `A<+0.0>` 和 `A<-0.0>` 是两个类型，而 `+0.0 == -0.0` 为真。按 P0732 的模型，`double` 却不能出现在类成员里，因为它永远不会有强结构相等。P1714R1 自己提到，曾考虑把浮点数拆成符号、指数、尾数三个整数再套用 P0732 的规则，但那样区分不了 `+0.0` 和 `-0.0`，处理无穷和 NaN 也困难。

P1907R0 提出两条出路：要么把模板实参的相等与 `operator==` 彻底分开，对类成员也使用顶层实参的那套规则，接受更多 (A) 类不一致；要么禁止更多类型作类成员。它推荐前者，理由是 (A) 类不一致在引用和成员指针上早已存在多年，而 (B) 类可以借此全部消除。

## P1907R1：结构化类型

[[P1907R1]] 按这个方向重写了规则，C++20 发布时采用的就是它。强结构相等这个术语被删除，常量形参的类型改为**结构化类型**（[[g:structural-type]]）：

!!! std
    a literal class type with the following properties: all base classes and non-static data members are public and non-mutable and the types of all base classes and non-static data members are structural types […]

    （[[temp.param#12]]，¶12.3）结构化类型是标量、左值引用，或者所有基类和成员都 public、非 mutable、类型本身也是结构化类型（或其数组）的字面类。

这个定义里完全没有比较运算符。相同与否改由 [[temp.type#2]] 逐类定义的模板实参等价判断：整数值相同，浮点值完全相同（identical），指针值相同，引用指向同一对象，成员指针指向同一成员，类类型则是对应的直接子对象和引用成员都等价。类成员和顶层实参用的是同一套规则，(B) 类不一致因此消失。

下面每一组断言都对应上表的一行，左右两侧的 `==` 和类型身份分道扬镳：

```cpp run title="equivalence.cpp" ok
#include <type_traits>

// 用户写的 == 不参与
struct Mod10 {
  int v;
  constexpr bool operator==(const Mod10& o) const {
    return v % 10 == o.v % 10;
  }
};
template<Mod10 M> struct T {};
static_assert(Mod10{3} == Mod10{13});
static_assert(!std::is_same_v<T<Mod10{3}>, T<Mod10{13}>>);

// 删除了 == 也照样能作形参类型
struct NoEq {
  int v;
  bool operator==(const NoEq&) const = delete;
};
template<NoEq N> struct U {};
static_assert(std::is_same_v<U<NoEq{1}>, U<NoEq{1}>>);

// 引用成员现在允许，比较的是身份
int a = 1, b = 1;
struct Ref { const int& r; };
template<Ref R> struct V {};
static_assert(!std::is_same_v<V<Ref{a}>, V<Ref{b}>>);
static_assert(std::is_same_v<V<Ref{a}>, V<Ref{a}>>);

// 成员指针作类成员，与作顶层实参的规则相同
union Un { int x; int y; };
template<int Un::*p> struct W {};
struct PM { int Un::*p; };
template<PM p> struct W2 {};
static_assert(!std::is_same_v<W<&Un::x>, W<&Un::y>>);
static_assert(!std::is_same_v<W2<PM{&Un::x}>, W2<PM{&Un::y}>>);

int main() {}
```

!!! impl "Clang 对联合体成员指针的 `==`"
    按 [[expr.eq#5]]（¶5.5），`&Un::x == &Un::y` 为真。本机 Clang 23 在运行期得到 1，但在常量求值中把它算成 false，`static_assert(&Un::x == &Un::y)` 失败。所以上面的例子没有写这条断言。这是 Clang 的偏差，与模板实参无关。

### 为什么必须是 public

规则不再需要比较运算符，代价是编译器要能看到并编码类的每个成员。P1907R1 选择只接受成员全部 public 的类，有私有成员的类型一律被拒绝，即使它的构造函数是 `constexpr` 的：

```cpp title="private.cpp" error
#include <string_view>
class Version {
  int major_, minor_;
public:
  constexpr Version(int a, int b) : major_(a), minor_(b) {}
  constexpr int major() const { return major_; }
};
template<Version V> struct Api {};          // error: 有私有成员
template<std::string_view S> struct Tag {}; // error: libc++ 的成员是私有的
```

Clang 23 在形参声明处就报错，并附注 `'Version' is not a structural type because it has a non-static data member that is not public`。

论文本身没有为 public 要求写理由。从它解决的问题可以看出这个要求的作用：类型身份由全部成员的值决定，如果有成员不可见，类的作者就可能把成员当作实现细节（例如缓冲区里用不到的尾部），以为两个值相等，编译器却把它们当作不同的特化。成员全部 public，至少表明逐成员比较是类作者公开接受的语义。后来的 [[P3380R1]] 用一个小字符串类详细分析了这个问题，见下文。

### 指针可以指向子对象了

P1907R1 还修改了 [[temp.arg.nontype]] 的限制清单。C++17 的指针、引用实参不能指向子对象；新规则删除了这一项，改为禁止指向临时对象、字符串字面量、`typeid` 结果、`__func__` 以及它们的子对象（今天的 [[temp.arg.nontype#6]]）。`P<&arr[1]>`、`P<&s.m>` 从此合法，例子见 [[temp.arg]] 的相应一节。

## 浮点：`-0.0` 与 NaN

结构化类型的第一项是标量，浮点数也是标量，于是 `double` 顺带成为合法的形参类型，而且可以出现在类成员里。等价要求浮点值 identical，不是 `==`：

```cpp run title="double-nttp.cpp" ok
#include <cmath>
#include <cstdio>
#include <limits>
#include <type_traits>

template<double Exp>
double power(double base) {
  if constexpr (Exp == 2.0)      return base * base;
  else if constexpr (Exp == 0.5) return std::sqrt(base);
  else                           return std::pow(base, Exp);
}

template<double D> struct F {
  static constexpr double value = D;
};
static_assert(0.0 == -0.0);
static_assert(!std::is_same_v<F<0.0>, F<-0.0>>);   // 两个特化
static_assert(std::is_same_v<F<0.5>, F<1.0 / 2>>); // 值相同即同一个

constexpr double qnan = std::numeric_limits<double>::quiet_NaN();
static_assert(!(qnan == qnan));
static_assert(std::is_same_v<F<qnan>, F<qnan>>);   // 同一个特化

struct Scale { double factor; };
template<Scale S> struct G {};
static_assert(!std::is_same_v<G<Scale{0.0}>, G<Scale{-0.0}>>);

int main() {
  std::printf("%g %g %g\n", power<2.0>(3), power<0.5>(9), power<3.0>(2));
  std::printf("%g %g\n", 1 / F<0.0>::value, 1 / F<-0.0>::value);
}
```

本机输出 `9 3 8` 和 `inf -inf`。区分 `0.0` 和 `-0.0` 是有意的：两者在运行期可以观察到区别（`1 / -0.0` 是负无穷），P1714R1 也是以此为由选择按表示比较。反过来，`NaN != NaN`，但同一个 NaN 作实参时仍是同一个特化。

如果为 `0.0` 写了一个显式特化，`F<-0.0>` 不会用到它。这是 P1714R1 在缺点一节自己承认的后果。

!!! impl "浮点实参的符号名"
    本机 Clang 23 把 `f<0.0>()` 和 `f<-0.0>()` 分别修饰为 `_Z1fILd0000000000000000EEiv` 和 `_Z1fILd8000000000000000EEiv`。Itanium ABI 直接编码 `double` 的位模式，两个零的符号位不同，自然是两个符号。

## 字符串字面量仍然不能直接用

C++20 解决了把字符串放进模板的问题，但走的是复制进类对象这条路。指针形参、或类里的指针成员，依然不能指向字符串字面量（[[temp.arg.nontype#6]]，¶6.2），因为两个相同的字面量是不是同一个对象是未指定的，不同翻译单元里通常不是：

<div class="compare" markdown="1">

```cpp error
struct str_ref {
  const char* p;
  constexpr str_ref(const char* s)
    : p(s) {}
};
template<str_ref S> struct Tag {};

Tag<"price"> t;  // error
```

```cpp ok
struct str_ref {
  const char* p;
  constexpr str_ref(const char* s)
    : p(s) {}
};
template<str_ref S> struct Tag {};

static constexpr char name[] = "price";
Tag<name> t;     // OK：具名数组
```

</div>

Clang 23 对左边报告 `pointer to subobject of string literal is not allowed in a template argument`。能工作的做法是把字符复制进成员数组，这正是 P0732R2 当年设想的 `fixed_string`：

```cpp run title="fixed-string.cpp" ok
#include <cstddef>
#include <cstdio>
#include <type_traits>

template<std::size_t N>
struct fixed_string {
  char data[N]{};
  constexpr fixed_string(const char (&s)[N]) {
    for (std::size_t i = 0; i < N; ++i) data[i] = s[i];
  }
  constexpr std::size_t size() const { return N - 1; }
};

template<fixed_string Name>      // 类模板实参推导出 N
struct Field {
  static void print() { std::printf("%s (%zu)\n", Name.data, Name.size()); }
};

// 字符串字面量运算符模板
template<fixed_string S>
constexpr auto operator""_f() { return Field<S>{}; }

// 编译期算出来的字符串也能作实参
constexpr fixed_string<4> make() {
  fixed_string<4> s("abc");
  s.data[0] = 'x';
  return s;
}

int main() {
  Field<"price">::print();
  decltype("qty"_f)::print();
  Field<make()>::print();
  static_assert(std::is_same_v<Field<"id">, decltype("id"_f)>);
}
```

本机输出 `price (5)`、`qty (3)`、`xbc (3)`，`-std=c++20` 同样通过。`fixed_string` 的构造函数只把字面量当作实参使用，模板形参对象里存的是字符的值。`Field<make()>` 用的是函数算出的值，这是 `char` 包和 P0424R2 都做不到的。

模板形参对象在全程序只有一个。把 `template<fixed_string S> const void* where() { return &S; }` 放进头文件，在两个翻译单元里分别取 `where<"hi">()`，本机链接后比较结果为 1（同一地址）。目标文件中这个对象的符号是 `_ZTAXtl12fixed_stringILm3EEtlA3_cLc104ELc105EEEE`，`c++filt` 显示为 `template parameter object for fixed_string<3ul>{"hi"}`：类名之后是逐个元素编码的 `'h'`（104）和 `'i'`（105），正是 P0732R2 的逐成员模型。

## 后来的变化

C++20 之后，规则又有几处修改和若干未完成的方向。

**初始化的细节**。P0732R2 和 P1907R1 只说实参要转换到形参的类型，没有说明类类型的模板形参对象怎样从实参构造。[[P2308R1]] 补上了这一块：先用实参初始化一个临时的 `constexpr T v = A;`（称为候选初始化器），再从与它等价的候选初始化器复制初始化模板形参对象，复制结果必须与 `v` 等价，否则非良构（[[temp.arg.nontype#3]]、[[temp.arg.nontype#4]]）。这排除了复制构造函数改变值的类型，例子见 [[temp.arg]]。

**改名**。当前草案把非类型模板形参统一改称**常量模板形参**（[[temp.param#2]]，¶2.2），这是编辑性修改。[[P2841R7]] 在此基础上加入了概念模板形参和变量模板模板形参，修订记录里写明它的措辞已按新名称改写。

**让更多类型可用**。`std::string_view`、`std::optional`、`std::tuple` 的成员是私有的，至今不能作形参类型。[[P2484R0]] 提议让类型提供一个转换，把自己表示成某个结构化类型的值；[[P3380R1]] 把这个问题重新表述为序列化、规范化和反序列化三步，并用一个 `SmallString` 说明为什么只做序列化不够：两个内容相同、缓冲区尾部不同的字符串如果被当作同一个实参，依赖尾部内容的代码就会得到两种结果，形成 ODR 违反。P3380R1 还提出用规范化让字符串字面量也能作实参。截至当前草案，这两篇提案都没有并入。

**Annex C**。C++20 的 [[diff.cpp17]] 没有与这两篇提案相关的条目：它们只是让以前非良构的程序变得良构。

## 编译器支持

| 特性 | 提案 | Clang |
|---|---|---|
| 类类型常量形参 | P0732R2 | Clang 12 起 |
| 结构化类型、浮点、子对象指针 | P1907R1 | Clang 18 起，部分支持 |

表中版本取自 Clang 的 C++ 支持状态页，它注明 P1907R1 中引用模板内部声明的对象及其子对象的情况尚未完全支持。本页的例子都在本机 Clang 23 上按标注的判定通过或被拒绝。

功能测试宏 `__cpp_nontype_template_args` 从 C++20 起是 `201911L`，当前草案仍是这个值（[[cpp.predefined]]）。本机 Clang 23 在 `-std=c++2c` 下仍报告 `201411L`（C++17 的值），与上面的部分支持一致；可移植代码不宜用这个宏判断 Clang 是否支持类类型形参。

## 小结

| 问题 | P0732R2 的回答 | P1907R1 之后（今天） |
|---|---|---|
| 哪些类可以作形参类型 | 有类内默认 `<=>`（后为 `==`）的字面类 | 结构化类型：成员全部 public、非 mutable、类型结构化 |
| 两个实参何时相同 | 按默认比较运算符的结果 | 按 [[temp.type#2]] 逐子对象判断，与 `==` 无关 |
| 浮点数 | 不允许 | 允许，按值完全相同判断，`0.0` 与 `-0.0` 不同 |
| 引用成员 | 不允许 | 允许，比较被引用对象的身份 |
| 指向子对象的指针 | 不允许 | 允许 |
| 字符串字面量 | 只能用来构造类对象 | 不变 |

命名模板实参是这一特性的一个常见用途：把一组选项写成聚合，用指派初始化器传给模板，见 [[patterns/policy-based-design|基于策略的设计]]中的默认策略与命名模板实参一节。

## 思考题

!!! question "思考题 1"
    下面两个类型是否相同？如果把 `operator==` 改成比较 `abs(v)`，结论会变吗？

    ```cpp
    struct S { int v; bool operator==(const S&) const = default; };
    template<S s> struct X {};
    using A = X<S{-1}>;
    using B = X<S{1}>;
    ```

<details markdown="1">
<summary>答案</summary>

不同，改了 `operator==` 也不会变。`S` 是结构化类型（[[temp.param#12]]），两个实参的唯一直接子对象 `v` 分别是 `-1` 和 `1`，整数值不同，所以不是模板实参等价的（[[temp.type#2]]，¶2.1、¶2.12）。等价的判断从不调用 `operator==`。
</details>

!!! question "思考题 2"
    为什么 `template<std::array<char, 6> s> struct T {};` 在本机能编译，`template<std::string_view s> struct U {};` 却不能？标准保证前者可移植吗？

<details markdown="1">
<summary>答案</summary>

`std::array` 是聚合，实现中它的唯一成员是一个 public 的数组，满足结构化类型的条件；`std::string_view` 的实现把指针和长度设为私有成员，违反 ¶12.3.1。标准只规定库类型的接口，没有逐个规定它们是否是结构化类型，所以前者能否作形参类型取决于实现，见 [[temp.param]] 中关于标准库类型的提醒。即使 `string_view` 可以，它指向字符串字面量时也会被 [[temp.arg.nontype#6]] 拒绝。
</details>
