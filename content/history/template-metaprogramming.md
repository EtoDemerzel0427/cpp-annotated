---
title: 模板元编程秘史：从意外的图灵完备到静态反射
summary: 模板本来是为容器和算法设计的参数化机制，1994 年有人用它让编译器在报错信息里列出素数。此后三十年，C++ 社区先在库里把这门意外的编译期语言用到极致，再由委员会一步步把它换成正式的语言设施，直到 C++26 的静态反射。
status: draft
order: 50
papers: N3911, N4502, N2242, N2258, N2235, N2343, N3651, N3652, N4295, P0292R2, P0734R0, P1073R3, P0732R2, P0784R7, P0194R6, P0598R0, P0425R0, P1240R0, P2320R0, P2996R13, P3381R0, P1306R5, P3394R4, P3294R2
related: temp.deduct, temp.res, temp.variadic, temp.friend, expr.const, meta, meta.reflection, stmt.expand, expr.reflect, topics/compile-time-programming, topics/two-phase-lookup, topics/concepts
tags: 模板, 元编程, SFINAE, constexpr, 概念, 反射, 历史
updated: 2026-10-18
---

C++ 模板最初的用途很朴素：写一个 `vector<T>`，让它对任何元素类型都和手写的版本一样快。没有人打算让它成为一门编程语言。可是模板支持特化、支持以常量为参数、实例化时会递归地实例化别的模板，这几样东西凑在一起，恰好构成了一台在编译期运行的计算机。1994 年，一段让编译器在错误信息里逐个报出素数的程序，第一次把这件事摆到了标准委员会面前。

本页按时间顺序讲这段历史：模板的设计目标，意外被发现的计算能力，社区把这门语言做成库的十几年，以及委员会从 C++11 起逐步提供正式设施、最终在 C++26 引入静态反射的过程。每一段都配一个小例子，展示那个年代的人实际怎么写。读这一页之前，最好知道模板实参推导（[[temp.deduct]]）和名字决议（[[temp.res]]）的基本规则；规则本身的细节请跳到对应条款页，本页只讲它们是怎么来的。

!!! note "关于出处"
    本页的历史论断都在句末或文末注明出处。主要依据是 Stroustrup 的两篇 HOPL 论文（下文简称 HOPL III、HOPL IV）、WG21 文档、当事人自己的网页和书。只有间接来源、或当事人的回忆与其他记录不完全一致的地方，会写明"据……"。

## 起点：模板的三个设计目标（1987–1991）

据 HOPL IV（§6.1）回忆，Stroustrup 在 1980 年前后曾以为 C 风格的宏就足以支持泛型编程，早期 C++ 也确实带着一套基于宏的 `<generic.h>`。宏在大项目里很快变得不可收拾。大约 1987 年，他开始设计带有正式接口的模板，并希望同时得到三样东西：

- 完全的通用性和表达力，不只能表达设计者想得到的用法；
- 与手写代码相比零开销，例如 `vector` 在时间和空间上要能和 C 数组竞争；
- 良好定义的接口，即对模板实参的类型检查和重载，要和非模板代码一样好。

当时没有人知道怎样三者兼得。HOPL IV 的总结是：C++ 最后得到了图灵完备、胜过手写的性能，以及很差的接口（实质上是编译期的鸭子类型，但仍然是静态类型安全的）。前两条让模板大获成功，第三条造成了此后三十年里难以阅读的错误信息，也直接引出了 C++20 的概念。本页后面的内容，大体上就是这三条结论各自的后续。

模板在 1990 年西雅图会议上被 ANSI 委员会接受；1991 年 10 月发布的 Cfront 3.0 是第一个支持模板的编译器（HOPL III，§2.5 的年表与 §3）。

## 1994 年：编译器在报错信息里列出了素数

1994 年的一次标准委员会会议上，西门子的代表 Erwin Unruh 带来了一段程序。它本身无法通过编译，但编译器给出的错误信息里依次出现了 2、3、5、7、11……也就是说，素数是编译器在实例化模板的过程中算出来的。

关于时间和地点，各方的记录略有出入：

- Unruh 在自己的网页上说，这段程序是他在 C++ 标准化的圣迭戈会议上写的，并在会上由 MetaWare 的 Tom Pennello 帮忙用 MetaWare 编译器试运行（Unruh，*Primzahlen* 页面）。
- HOPL III（§7.2.2）说 Unruh 是在 1994 年的一次扩展工作组会议上展示这段程序的，并记载他对 Stroustrup 等人的反应感到意外：大家觉得它"marvelous rather than scary"（了不起，而不是可怕）。HOPL III 的年表把圣迭戈会议定在 1994 年 3 月。
- 这段程序对应的委员会文档编号是 N462（X3J16/94-0075），题为 *Prime number computation*（HOPL III 参考文献 [143]）。

Unruh 的网页上保留了原版程序和 MetaWare High C/C++ R2.6 的输出。程序里的 `D<i>` 只有一个接受 `void*` 的构造函数，初始化 `D<i> d = prim;` 能否成功取决于 `prim` 的值：`prim` 为 0（合数）时，MetaWare 把它当作空指针常量接受了；为 1（素数）时转换失败，错误信息里带着 `D<i>` 中的 `i`。*C++ Templates* 收录的版本把初始值写成 `prim ? 1 : 0`，依赖的是 C++98 中值为零的整型常量表达式都是空指针常量这条规则。[[CWG903]] 后来把空指针常量限定为值为零的整数字面量，于是这个版本在今天的编译器上对每个 `i` 都会报错，不再能区分素数。下面是一个按今天的规则改写的版本，思路不变：只让素数走进一条必然出错的路径。

```cpp error title="unruh.cpp"
template <int i> struct D { D(void*); };            // 只能从指针构造

template <int p, int i> struct is_prime {
    static constexpr bool value = (p % i) && is_prime<(i > 2 ? p : 0), i - 1>::value;
};
template <> struct is_prime<0, 0> { static constexpr bool value = true; };
template <> struct is_prime<0, 1> { static constexpr bool value = true; };

template <int n, bool prime> struct Report { static void f() {} };
template <int n> struct Report<n, true> {
    static void f() { D<n> d = 1; }                 // error: 只有素数会实例化这一行
};

template <int n> struct Prime_print {
    Prime_print<n - 1> a;
    void f() { Report<n, is_prime<n, n - 1>::value>::f(); a.f(); }
};
template <> struct Prime_print<2> { void f() { Report<2, true>::f(); } };

int main() { Prime_print<20>{}.f(); }
```

用 Clang 23 编译，得到 8 条错误，形如 `no viable conversion from 'int' to 'D<19>'`，尖括号里依次是 2、19、17、13、11、7、5、3。计算全部发生在编译期，输出通道是诊断信息。

这段程序的意义在于它说明了模板实例化机制本身就是一门能做非平凡计算的语言。Vandevoorde 和 Josuttis 在 *C++ Templates*（2002）第 17 章把它称为有文档记载的最早的元程序，并指出它并不可移植，因为错误信息的内容不受标准约束。Stroustrup 在 HOPL III（§7.2.2）里写道，他设计模板时追求的正是完全的通用性，而 Unruh 的程序清楚地展示了这种通用性。

## 1995–2003：命名、技法和最早的证明

### 元程序与表达式模板

把模板计算当作一种正经编程技术来推广的，是 Todd Veldhuizen。1995 年他在 *C++ Report* 上连续发表了两篇文章：5 月的 *Expression Templates* 和 6 月的 *Using C++ Template Metaprograms*（HOPL III 参考文献 [147][148]；*C++ Templates* 第 17.8 节）。后一篇展示了如何用模板写编译期的 `if` 和 `switch`，在不同的数据结构和算法之间做选择。HOPL III 记载，Stroustrup 第一次从 Jeremy Siek 那里看到这种编译期 `if_`（写法见下文的 tmp-98.cpp）时，对它的简单和巧妙印象很深。

表达式模板解决的是数值计算里的一个具体问题。`x = a + b + c` 若按普通运算符重载实现，会产生两个临时向量和三次循环。表达式模板让 `operator+` 不立即计算，而是返回一个记录了计算方式的对象，等到赋值时再用一个循环一次算完：

```cpp run ok std=c++98 title="expression-templates.cpp"
#include <cstddef>

template <class L, class R>
struct Sum {                                     // 表示 l + r，但还没有计算
    const L& l; const R& r;
    Sum(const L& l_, const R& r_) : l(l_), r(r_) {}
    double operator[](std::size_t i) const { return l[i] + r[i]; }
};

struct Vec {
    double d[3];
    double operator[](std::size_t i) const { return d[i]; }
    template <class E>
    Vec& operator=(const E& e) {                 // 一个循环算完整个表达式，没有临时 Vec
        for (std::size_t i = 0; i < 3; ++i) d[i] = e[i];
        return *this;
    }
};

inline Sum<Vec, Vec> operator+(const Vec& a, const Vec& b) { return Sum<Vec, Vec>(a, b); }
template <class L, class R>
Sum<Sum<L, R>, Vec> operator+(const Sum<L, R>& a, const Vec& b) { return Sum<Sum<L, R>, Vec>(a, b); }

int main() {
    Vec a = {{1, 2, 3}}, b = {{4, 5, 6}}, c = {{7, 8, 9}}, x;
    x = a + b + c;                               // a + b + c 的类型是 Sum<Sum<Vec, Vec>, Vec>
    return x[2] == 18 ? 0 : 1;
}
```

Veldhuizen 把这些技术用在了数值数组库 Blitz++ 中。HOPL III 还记载，Daveed Vandevoorde 独立发现了同一技术。

### Traits

同一年（1995 年 6 月），Nathan Myers 在 *C++ Report* 上发表 *Traits: a new and useful template technique*（HOPL III 参考文献 [88]）。HOPL III（§4.1.5）讲了它的来历：STL 需要在编译期询问类型的性质，例如迭代器指向的元素是什么类型，而早期 STL 靠重载来做，既不系统又容易出错。Myers 在把 iostream 和 string 模板化的过程中找到了一般解法：用一个辅助模板集中存放一组类型的相关信息，再用偏特化处理指针这类没有成员类型的情况。

```cpp run ok std=c++98 title="traits.cpp"
template <class Iter>
struct iterator_traits {                 // 一般情况：问迭代器自己
    typedef typename Iter::value_type value_type;
};
template <class T>
struct iterator_traits<T*> {             // 指针没有成员类型，用偏特化补上
    typedef T value_type;
};

template <class Iter>
typename iterator_traits<Iter>::value_type first(Iter it) { return *it; }

int main() { int a[] = {42}; return first(a) == 42 ? 0 : 1; }
```

偏特化本身也是 1995 年才加入 C++ 的（HOPL III，§4.1.5）。此后，traits 成为几乎所有模板库的基础设施，十几年后又以 `<type_traits>` 的形式进入标准（见 [[meta]]）。

### 图灵完备的证明

Unruh 的程序说明模板能做计算，但它究竟能算多少，是另一个问题。2003 年，Veldhuizen 写了一篇短文 *C++ Templates are Turing Complete*，给出了一个半形式化的证明（HOPL III 参考文献 [150]）。文中承认，严格的证明很难，因为模板实例化没有形式语义。HOPL III（§7.2.2）的表述更谨慎一些：在忽略编译器限制的前提下，模板实例化机制是图灵完备的。

这个前提并非可有可无。标准在附录 [[implimits]] 里给出了建议的最低实现限额，其中递归嵌套的模板实例化（包括模板实参推导中的替换）建议不少于 1024 层。[[temp.inst]] 还规定无限递归实例化的结果是未定义的。所以在实际的编译器上，模板计算总是有界的。

## 2000–2010：库的时代

### 书和库

进入 2000 年代，模板元编程从零散的技巧变成了有体系的方法，主要载体是几本书和 Boost：

| 年份 | 作品 | 作者 | 贡献 |
|---|---|---|---|
| 2000 | *Generative Programming* | Krzysztof Czarnecki、Ulrich Eisenecker | 把模板元编程放进生成式编程的框架；书中有一个编译期 Lisp 解释器（HOPL IV §10.5.2） |
| 2001 | *Modern C++ Design* 与 Loki 库 | Andrei Alexandrescu | 基于策略的设计（policy-based design）、类型列表（typelist）、编译期断言等 |
| 2002 | *C++ Templates: The Complete Guide* | David Vandevoorde、Nicolai Josuttis | 第一本系统讲解模板规则的书；命名了 SFINAE |
| 2003 | Boost.MPL 随 Boost 1.30 发布 | Aleksey Gurtovoy、David Abrahams | 把 STL 的容器、迭代器、算法概念搬到类型层面 |
| 2004 | *C++ Template Metaprogramming* | David Abrahams、Aleksey Gurtovoy | MPL 的配套书 |

Boost 本身成立于 1998 年（HOPL III，§4.2），它的同行评审制度，以及为将来的标准化提供参考实现的定位，使许多元编程技术后来能够顺利进入标准库。

基于策略的设计用模板参数来组装类的行为：一个智能指针的所有权语义、线程模型、检查策略各由一个模板实参决定，组合在编译期完成。Loki 的类型列表则在没有变参模板的年代，用 `Typelist<H, Typelist<...>>` 这样的嵌套结构和一组宏来表示任意长度的类型序列。这两样东西都要靠大量的递归特化来操作。

### SFINAE 有了名字

模板实参推导有一条规则：如果把推导出的实参代入函数模板的声明时产生了无效的类型或表达式，推导就失败，这个候选被静默地从重载集中移除，而不是报错（今天的条文见 [[temp.deduct#8]]）。这条规则原本是为了让重载决议在面对不相干的模板时能正常工作，后来被人用作在编译期选择重载的开关。

SFINAE（Substitution Failure Is Not An Error）这个缩写出自 *C++ Templates*。Vandevoorde 后来解释说，标准术语 deduction failure 太强调"失败"，容易让读者困惑，他造这个词是为了"facilitate the explanation of the associated techniques"（便于讲解相关技法）（引自 Jonathan Wakely 在 ACCU 2013 的演讲幻灯片）。

把 SFINAE 包装成可用工具的是 `enable_if`。Jaakko Järvi、Jeremiah Willcock、Howard Hinnant 和 Andrew Lumsdaine 在 2003 年 6 月的 *C/C++ Users Journal* 上发表了 *Function overloading based on arbitrary properties of types*；Järvi、Willcock、Lumsdaine 编写的 Boost.enable_if 随 2004 年 1 月的 Boost 1.31 发布，发布说明称它是一项利用 SFINAE 原则的重要新技术（Boost 1.31.0 发布说明；Boost.Core 中 enable_if 文档的参考文献）。

C++03 时代的检测写法通常长这样：用 `sizeof` 测量一个重载调用的返回类型，从而在编译期得到一个布尔值。

```cpp run ok std=c++98 title="sfinae-03.cpp"
template <class T> struct has_size_type {
    typedef char yes[1];
    typedef char no[2];
    template <class U> static yes& test(typename U::size_type*);   // U::size_type 无效时被 SFINAE 移除
    template <class U> static no&  test(...);
    static const bool value = sizeof(test<T>(0)) == sizeof(yes);
};

template <bool B, class T = void> struct enable_if { typedef T type; };
template <class T> struct enable_if<false, T> {};             // 没有 type 成员

struct Vec { typedef unsigned size_type; };

template <class T>
typename enable_if<has_size_type<T>::value, int>::type kind(const T&) { return 1; }
template <class T>
typename enable_if<!has_size_type<T>::value, int>::type kind(const T&) { return 2; }

int main() { return kind(Vec()) + kind(42) == 3 ? 0 : 1; }
```

C++98 风格的值计算也一样依赖特化。下面的 `fact` 与 `if_` 都取自 HOPL 论文中的例子，略有改写：

```cpp run ok std=c++98 title="tmp-98.cpp"
template <bool B, class X, class Y> struct if_ { typedef X type; };
template <class X, class Y> struct if_<false, X, Y> { typedef Y type; };

template <unsigned N> struct fact { enum { value = N * fact<N - 1>::value }; };
template <> struct fact<0> { enum { value = 1 }; };          // 特化充当递归的终止条件

typedef if_<(sizeof(int) < 4), long, int>::type small_int;
int check[fact<5>::value == 120 ? 1 : -1];   // C++98 没有 static_assert，用数组长度做断言

int main() { small_int x = 0; return x; }
```

### 代价

HOPL IV（§4.5.2）把 2000 年代的头十年比作元编程的蛮荒西部：错误信息极其糟糕，编译时间常常极长，很容易耗尽编译器的内存、递归深度和标识符长度等资源，不同的人还在反复重新发现同样的问题和技巧。Stroustrup 在 HOPL IV（§10.5.2）里还提到，他见过几百行元编程代码让编译耗时以分钟计，甚至在 30GB 内存的机器上因内存耗尽而失败，一个简单错误引出的诊断可以长达数千行。

错误信息难读的根源，正是前面说的第三个设计目标没有实现：模板对实参的要求只写在实现里，没有写在接口上，编译器只能在实例化的深处报告某个表达式无效。

## C++11：语言开始接手

HOPL IV（§4.5.2）把 C++11 对元编程的支持分成两条线：语言方面有概念（未能进入 C++11）、`constexpr` 函数、lambda、别名模板，以及对模板实例化更精确的规定；库方面有 tuple、type traits 和 `enable_if`。与元编程关系最密切的几项如下。

| 特性 | 提案 | 对元编程的影响 |
|---|---|---|
| 变参模板 | [[N2242]]（Gregor、Järvi、Maurer、Merrill） | 类型列表成为语言内建的形参包，不再需要嵌套结构和宏 |
| `decltype` | [[N2343]] | 可以直接问一个表达式的类型；配合尾置返回类型，SFINAE 可以作用于任意表达式 |
| `constexpr` 函数 | [[N2235]] | 值的计算可以用普通函数写 |
| 别名模板 | [[N2258]] | 元函数可以写成 `template<class T> using f = ...;`，省掉 `typename ...::type` |
| `static_assert` | [[N1720]] | 编译期断言有了正式语法和可读的消息 |
| `<type_traits>`、`enable_if`、`conditional` | TR1 中的 type traits（源自 Boost，[[N1424]]）；[[N2240]] | traits 和 `enable_if` 进入标准库 |

变参模板的提案始于 2004 年，作者是当时都在印第安纳大学的 Douglas Gregor、Jaakko Järvi 和 Gary Powell（[[N1704]]）。据 HOPL IV（§4.3.2）回忆，Stroustrup 起初觉得这个方案过于复杂、记法晦涩、风格太依赖递归，后来被 Gregor 的演示说服，其中一个理由是编译时间的测量：与当时的替代写法相比，变参模板有时快 20 倍。规则本身见 [[temp.variadic]]。

`decltype` 带来的变化不太显眼，影响却很大。在 C++03 里，SFINAE 主要作用于类型（比如 `typename U::size_type`），表达式中的错误是否算替换失败，规则并不清楚，想检测能否调用 `x.size()` 需要绕很大的弯。有了 `decltype` 和尾置返回类型，可以直接写 `auto f(T& x) -> decltype(x.size())`，表达式无效就替换失败。这通常被称为 expression SFINAE。HOPL IV（§4.5.1）提到，在用户的持续推动下，SFINAE 的规则在 C++11 的制定过程中变得更简单、更一般；作为副作用，编译器必须能够干净地撤销一次失败的实例化，这也改善了编译器的内部结构。

有了变参模板和别名模板，类型列表的写法完全变了。Peter Dimov 在 2015 年的文章 *Simple C++11 metaprogramming* 里提出，任何变参类模板都可以直接当作类型列表，任何别名模板都可以直接当作元函数；他的开场判断是"C++11 changed the playing field"（C++11 改变了游戏规则），并认为 Boost.MPL 已经不够用了。下面的 `mp_rename` 和 `mp_transform` 就是那篇文章里的核心原语，它们后来成为 Boost.Mp11（随 2017 年 12 月的 Boost 1.66 发布）的一部分：

```cpp run ok std=c++17 title="mp11-style.cpp"
#include <tuple>
#include <type_traits>

template <class... T> struct mp_list {};

// 把 A<T...> 改成 B<T...>：任何变参模板都可以当类型列表
template <class L, template <class...> class B> struct mp_rename_impl;
template <template <class...> class A, class... T, template <class...> class B>
struct mp_rename_impl<A<T...>, B> { using type = B<T...>; };
template <class L, template <class...> class B>
using mp_rename = typename mp_rename_impl<L, B>::type;

// 对每个元素应用 F：一次包展开，没有递归
template <template <class...> class F, class L> struct mp_transform_impl;
template <template <class...> class F, template <class...> class L, class... T>
struct mp_transform_impl<F, L<T...>> { using type = L<F<T>...>; };
template <template <class...> class F, class L>
using mp_transform = typename mp_transform_impl<F, L>::type;

using L1 = mp_list<int, const char, double>;
using L2 = mp_transform<std::add_pointer_t, L1>;
static_assert(std::is_same_v<mp_rename<L2, std::tuple>,
                             std::tuple<int*, const char*, double*>>);
int main() {}
```

与 MPL 相比，这里没有迭代器、没有占位符、没有 `typename ...::type` 链，递归也被包展开取代。

## void_t 与检测惯用法（2014–2015）

C++11 的 expression SFINAE 让检测变得容易了，但每检测一种性质仍要写一套重载。Walter E. Brown 在 2014 年的 [[N3911]] 里提议在标准库中加入一个看起来什么也不做的别名模板：

```cpp
template <class...> using void_t = void;
```

它的用处在于和偏特化配合。主模板给出默认答案 false；偏特化的第二个实参写成 `void_t<要检测的表达式的类型>`，表达式良构时它就是 `void`，与主模板的默认实参一致，偏特化被选中；表达式非良构时替换失败，偏特化被丢弃。

```cpp run ok std=c++17 title="void_t.cpp"
#include <type_traits>
#include <utility>

template <class, class = void>
struct has_begin : std::false_type {};                    // 默认：没有

template <class T>
struct has_begin<T, std::void_t<decltype(std::declval<T&>().begin())>>
    : std::true_type {};                                  // 表达式良构时匹配

struct Range { int* begin(); };
static_assert(has_begin<Range>::value);
static_assert(!has_begin<int>::value);

int main() {}
```

`void_t` 以 N3911 进入 C++17（`<type_traits>` 中 `__cpp_lib_void_t` 的值是 201411，对应 2014 年 11 月）。这里有一个规则上的细节：别名模板中没有用到的实参是否参与 SFINAE，C++11 原本没有说清楚，直到 [[CWG1558]] 才明确它们必须参与，所以早期的一些编译器需要换一种写法才能让 `void_t` 生效。

Brown 随后在 [[N4436]] 和 [[N4502]] 里把这一模式推广为检测惯用法（detection idiom）：`is_detected<Op, Args...>` 判断 `Op<Args...>` 是否良构，`detected_or` 在不良构时给出默认类型。这组工具进入了 Library Fundamentals TS v2（`std::experimental::is_detected`），但没有进入 C++ 标准本身。C++20 的 requires 表达式提供了更直接的写法，见下文。

## C++14 与 C++17：编译期代码越来越像普通代码

C++14 和 C++17 的改动大多在做同一件事：让编译期计算不必再借道类型系统。

| 版本 | 特性 | 提案 |
|---|---|---|
| C++14 | 变量模板 | [[N3651]] |
| C++14 | 放宽 `constexpr` 函数的限制（局部变量、循环、多条语句） | [[N3652]] |
| C++14 | `std::integer_sequence` | [[N3658]] |
| C++14 | 变换类 traits 的 `_t` 别名（`std::remove_cv_t` 等） | [[N3655]] |
| C++17 | traits 的 `_v` 变量模板（`std::is_same_v` 等） | [[P0006R0]] |
| C++17 | 折叠表达式 | [[N4295]] |
| C++17 | `if constexpr` | [[P0292R2]] |
| C++17 | `auto` 非类型模板形参 | [[P0127R2]] |
| C++17 | `std::conjunction` 等逻辑 traits | [[P0013R1]] |

`if constexpr` 走了一段弯路。Walter Brown（[[N3322]]）以及 Herb Sutter、Walter Bright、Andrei Alexandrescu（[[N3329]]）在 2011–2012 年先后提出了仿照 D 语言的 `static if`。Stroustrup、Dos Reis 和 Sutton 在 [[N3613]]（2013）中提出反对，他们的技术理由主要是：`static if` 可以出现在命名空间和类作用域，可以控制声明是否存在，这会让代码难以分析，也和当时正在设计的概念相冲突。2015 年 Ville Voutilainen 以 [[N4461]] 重新提出，范围收窄到函数体内的语句，几经修改后以 [[P0292R2]] 的 `if constexpr` 语法进入 C++17（规则见 [[stmt.if]]）。

```cpp run ok std=c++17 title="cxx17.cpp"
#include <string>
#include <type_traits>

template <class T>
std::string describe(const T& x) {
    if constexpr (std::is_arithmetic_v<T>)
        return std::to_string(x);      // 只有 T 是算术类型时才实例化这一支
    else
        return std::string(x);         // 只有 T 不是算术类型时才实例化这一支
}

template <class... Ts>
constexpr auto sum(Ts... xs) { return (xs + ... + 0); }   // 折叠表达式，不再需要递归

static_assert(sum(1, 2, 3, 4) == 10);
static_assert(sum() == 0);

int main() { return describe(42) == "42" && describe("hi") == "hi" ? 0 : 1; }
```

在 C++11 中，同样的分派需要两个用 `enable_if` 互斥的重载，`sum` 需要一个递归的主模板加一个终止重载。

## 两个流派：Hana 与 Mp11

C++14 之后，元编程库分成了两种思路，代表分别是 Louis Dionne 的 Boost.Hana（随 2016 年 5 月的 Boost 1.61 发布）和 Peter Dimov 的 Boost.Mp11（2017 年 12 月，Boost 1.66）。

Mp11 继续在类型层面工作，但用的是 C++11 之后的原语：别名模板、包展开、变参类模板。前面的 `mp_transform` 就是这种风格。它的优点是贴近编译器的实现方式，编译速度通常较快。

Hana 走的是另一条路：把类型包装成值，于是可以用普通函数、lambda、`constexpr` 运算来做类型计算，异构容器和类型计算用同一套接口。下面是一个不依赖 Hana 的最小示意：

```cpp run ok std=c++17 title="hana-style.cpp"
#include <type_traits>

template <class T> struct type_ { using type = T; };
template <class T> constexpr type_<T> type_c{};           // 类型 T 对应的值

template <class T, class U>
constexpr bool operator==(type_<T>, type_<U>) { return std::is_same_v<T, U>; }

constexpr auto add_pointer = [](auto t) {                  // 类型计算写成普通的 lambda
    return type_c<typename decltype(t)::type*>;
};
static_assert(add_pointer(type_c<int>) == type_c<int*>);

// 检测也变成对值的提问：is_valid(f)(type_c<T>) 问的是 f 能否以 T 调用
constexpr auto is_valid = [](auto f) {
    return [](auto... t) {
        return std::is_invocable_v<decltype(f), typename decltype(t)::type...>;
    };
};
constexpr auto has_size = is_valid([](auto&& x) -> decltype(x.size()) {});

struct S { int size() const; };
static_assert(has_size(type_c<S>));
static_assert(!has_size(type_c<int>));

int main() {}
```

两种思路的分歧最终影响了反射的设计。Dionne 在 2017 年给 SG7 的 [[P0425R0]] 中写道，经典的模板元编程"very difficult to use, does not scale well"（很难用，扩展性差），Hana 风格更好用，但编译时间同样不能扩展；最好的方向是基于 `constexpr` 的元编程加上同质的、基于值的反射。他列出的第一步是让常量表达式支持可变长容器。这一步后来由 [[P0784R7]]（C++20，允许常量求值中的动态内存分配）实现，而基于值的反射正是 C++26 最终采用的模型。

## C++20：约束写在接口上

### 概念

概念的历史另有专页（[[topics/concepts]]），这里只说它和元编程的关系。C++0x 的概念设计在 2009 年被移出草案；之后 Sutton、Stroustrup、Dos Reis 提出了简化的 Concepts Lite（[[N3580]]），先以 Concepts TS 的形式发布。2016 年 2 月的 Jacksonville 会议上，把概念加入 C++17 的动议以 25 票赞成、31 票反对、8 票弃权未获通过；2017 年，Concepts TS 中基础的部分以 [[P0734R0]] 进入 C++20 工作草案（HOPL IV，§6.3–6.4）。

对元编程来说，概念取代了大部分 `enable_if` 和检测惯用法的用途。约束写在声明上，不满足时编译器能指出是哪一条要求不成立：

```cpp run ok std=c++20 title="concepts.cpp"
#include <cstddef>
#include <concepts>

template <class T>
concept Sized = requires(const T& x) {
    { x.size() } -> std::convertible_to<std::size_t>;
};

template <Sized T>                       // 约束写在接口上，不再藏进返回类型
std::size_t count(const T& x) { return x.size(); }

struct Box { std::size_t size() const { return 3; } };

int main() { return count(Box{}) == 3 ? 0 : 1; }
```

如果调用 `count(42)`，Clang 23 会依次说明：候选被忽略，因为约束不满足；`int` 不满足 `Sized`；`x.size()` 无效，因为 `const int` 不是类或联合体。和 C++03 时代动辄数千行的实例化回溯相比，这正是第一节所说的第三个设计目标迟到了三十年的兑现。约束的规则见 [[temp.constr]]。

### consteval 与类类型非类型模板形参

C++20 还有两项与元编程关系密切的改动：

- `consteval`（立即函数，[[P1073R3]]）：每次调用都必须在编译期求值。P1073R3 在动机部分说明，它的直接推动力是 SG7 在编译期反射方面的工作，反射查询函数通常只能在编译期求值（规则见 [[expr.const]]）。
- 类类型作为非类型模板形参（[[P0732R2]]，后经 [[P1907R1]] 改为结构化类型的模型）：字符串字面量等复合值可以直接当模板实参，以前这类需求只能靠字符序列的变参模板来模拟。

```cpp run ok std=c++20 title="nttp.cpp"
#include <algorithm>
#include <cstddef>

template <std::size_t N>
struct fixed_string {
    char data[N]{};
    consteval fixed_string(const char (&s)[N]) { std::copy_n(s, N, data); }
};

template <fixed_string Name>                     // 类类型的模板形参
struct field { static constexpr const char* name = Name.data; };

consteval int square(int n) { return n * n; }   // 只能在编译期调用

int main() {
    using id = field<"id">;
    static_assert(square(7) == 49);
    return id::name[0] == 'i' ? 0 : 1;
}
```

## 反射的长路（2013–2025）

### SG7 与 reflexpr

模板元编程能计算类型，却无法回答一个类有哪些成员、一个枚举有哪些枚举项这类问题。2013 年，WG21 成立了反射研究组 SG7，并由 Jeffrey Snyder 和 Chandler Carruth 发出征集提案的号召（[[N3814]]）。据 HOPL IV（§9.6.2）记载，当时大家普遍认为 C++ 需要静态反射，并且一致认为依赖运行期遍历常驻数据结构的反射不适合 C++，因为数据量大、要完整表示语言构造很复杂，而且遍历有运行期开销。

最先成形的是 Matúš Chochlík 的设计（[[N3996]]，2014），后来与 Axel Naumann、David Sankel 合作发展为 [[P0194R6]]。它是基于类型的：`reflexpr(X)` 产生一个元对象类型，查询通过 traits 风格的模板完成，各种元对象用概念组织成层次。这套设计成为 Reflection TS 的基础（工作草案 [[N4766]]）。据 HOPL IV，这份 TS 在 2019 年获批；它在 2021 年正式发布，编号 ISO/IEC TS 23619:2021。

### 转向基于值的反射

在 TS 推进的同时，`constexpr` 计算的能力在快速增长。2017 年，Daveed Vandevoorde 在 [[P0598R0]] 中提议让反射通过值而不是类型来进行；同年他与 Dionne 在 [[P0633R0]] 中梳理了元编程和反射的设计空间，把它分成反射、控制流、代码合成三个大体正交的部分。2018 年，Sutton、Vali、Vandevoorde 的 [[P1240R0]] *Scalable Reflection in C++* 给出了完整的基于值的方案：所有反射结果都是同一个类型 `std::meta::info` 的值，用 `consteval` 函数查询。

HOPL IV（§9.6.2）总结了支持这次转向的理由：分析和生成代码本质上是函数式的；`constexpr` 计算已经发展到元编程和反射可以合流的程度；还有一条由 Vandevoorde 首先提出：编译器内部为函数建立的数据结构，比为类型层次建立的小得多、存在的时间也短得多，所以占用内存更少、编译更快。2019 年，Sankel 与 Vandevoorde 在 [[P1733R0]] 中提出了折中方案：底层只有一个 `meta::info` 类型，在其上可以按需加一层有类型的接口。

语法也几经变化。P1240R0 使用关键字 `reflexpr`；2021 年 Sutton、Childers、Vandevoorde 在 [[P2320R0]] 中提议用一元 `^` 表示反射、用 `[: :]` 把反射值拼接（splice）回代码，理由之一是将来可能需要按反射传递实参（pass arguments by reflection），记法应当像取地址的 `&` 一样简短；2024 年的 [[P3381R0]] 又把 `^` 改成新词法记号 `^^`，因为 `^` 与 Clang 的 block 扩展（Objective-C++ 中使用）存在解析冲突。

### P2996 与 C++26

2023 年 10 月，Barry Revzin、Wyatt Childers、Peter Dimov、Andrew Sutton、Faisal Vali、Daveed Vandevoorde 发表了 [[P2996R0]] *Reflection for C++26*，提案的主体是 P1240 中功能的一个子集。论文的解释是，先从较小的范围开始可以提高被采纳的机会，更强的功能以后再逐步加上（后来 Dan Katz 加入作者行列）。2025 年 6 月的索非亚会议上，委员会把 [[P2996R13]] 连同另外六篇论文投票并入 C++26 草案（Herb Sutter 的索非亚会议报告）：

| 论文 | 内容 |
|---|---|
| [[P2996R13]] | 反射的基础：`^^`、拼接、`std::meta::info` 与查询函数 |
| [[P3394R4]] | 注解（annotation），`[[=expr]]` |
| [[P3293R3]] | 拼接基类子对象 |
| [[P3491R3]] | `define_static_string`、`define_static_object`、`define_static_array` |
| [[P1306R5]] | 展开语句 `template for` |
| [[P3096R12]] | 函数形参的反射 |
| [[P3560R2]] | 反射中的错误处理（以编译期异常为模型） |

展开语句也有自己的前史：Andrew Sutton 在 2017 年的 [[P0589R0]] 中提出了基于 tuple 的 `for` 循环，2018 年 Sutton、Goodrick、Vandevoorde 提出了 [[P1306R0]] *Expansion statements*。consteval 块（[[P3289R1]]）没有单独表决；据 CWG 的论文跟踪记录，它的内容并入了 P2996 的后续修订。

下面是 P2996 中经典的枚举转字符串例子，略有改写。本地的 Clang 23 不支持反射，所以这段代码没有在本地编译验证，也不标判定；据 GCC 16.1 的发布说明，可以用 `-std=c++26 -freflection` 试验。

```cpp title="enum-to-string.cpp"
#include <meta>
#include <string_view>
#include <type_traits>

template <class E>
    requires std::is_enum_v<E>
constexpr std::string_view enum_to_string(E value) {
    template for (constexpr std::meta::info e :
                  std::define_static_array(std::meta::enumerators_of(^^E))) {
        if (value == [:e:])                       // 把反射值拼接回表达式
            return std::meta::identifier_of(e);
    }
    return "<unnamed>";
}

enum class Color { red, green, blue };
static_assert(enum_to_string(Color::green) == "green");
```

这段代码里每一样东西都对应本页前文的一段历史：`^^E` 产生的是值而不是类型（基于值的反射）；`enumerators_of` 是 `consteval` 函数，返回 `std::vector`（C++20 的编译期动态内存）；`define_static_array` 把编译期容器转成可以跨越常量求值边界的静态数组；`template for` 在每次迭代中以不同的常量实例化循环体，替代了过去的递归模板或 `index_sequence` 加折叠表达式。相关规则见 [[expr.reflect]]、[[stmt.expand]]、[[meta.reflection]]，以及专题 [[topics/compile-time-programming]]。

## 几处反复出现的暗角

模板元编程的历史里，有几样东西一直让人意外，也一直在被委员会修补。

### 两阶段查找、typename 与 template

模板定义中的名字分两个阶段查找：非依赖名在定义处绑定，依赖名推迟到实例化时（[[temp.res]]，专题见 [[topics/two-phase-lookup]]）。这个模型要求编译器在看到模板定义时就能解析它，于是需要程序员在依赖名前面标出它是类型（`typename`）还是模板（`template`）：

```cpp run ok title="keywords.cpp"
template <class T>
struct Holder {
    using value_type = typename T::value_type;   // 依赖名默认不是类型，要写 typename
};

template <class Tuple>
int first(Tuple& t) {
    return t.template get<0>();                   // 依赖名后的 < 默认是小于号，要写 template
}

struct P { template <int I> int get() { return I + 1; } };

int main() { P p; return first(p) == 1 ? 0 : 1; }
```

去掉 `first` 里的 `template`，Clang 23 报告 `missing 'template' keyword prior to dependent template name 'get'`。C++20 的 [[P0634R3]] *Down with typename!* 让 `typename` 在若干只可能是类型的语境中变为可选，但 `template` 消歧符仍然需要。

两阶段查找本身的后果也常常出人意料：定义之后才声明的非依赖重载，对模板来说是不可见的。

```cpp run ok title="two-phase.cpp"
void g(double) {}

template <class T>
void f(T) {
    g(1);          // 非依赖调用：在定义处查找，只看得到 g(double)
}

void g(int) {}     // 这个更好的匹配来得太晚

int main() { f(0); }   // 调用的是 g(double)
```

长期以来，并非所有编译器都按这个模型实现。微软的 Visual C++ 团队在 2017 年 9 月的博客文章中说明，MSVC 过去把模板体记录为一串记号，到实例化时才解析；Visual Studio 2017 15.3 在 `/permissive-` 模式下才开始部分支持两阶段查找（Andrew Pardoe，*Two-phase name lookup support comes to MSVC*）。在那之前，同一段模板代码在不同编译器上的行为可能不同。

### 借助友元注入的有状态元编程

模板元编程按理说是纯函数式的：同一个表达式求值两次，结果应该相同。2015 年，Filip Roséen 在博客文章 *Non-Constant Constant-Expressions in C++* 中展示了一种打破这一点的办法，并于 2015 年 4 月在 isocpp 的 std-discussion 邮件列表上询问标准中是否有条文禁止它。办法的核心是友元注入：在类模板里定义的友元函数，要到该类模板被实例化时才算被定义，而某个函数是否已被定义，可以在编译期观察到。

```cpp title="friend-injection.cpp"
template <int N>
struct flag {
    friend constexpr auto adl(flag<N>);                  // 只声明；返回类型待推导
};

template <int N>
struct setter {
    friend constexpr auto adl(flag<N>) { return true; }  // setter<N> 实例化时才定义
};

template <int N = 0, auto = [] {}>
consteval int next() {
    if constexpr (requires { adl(flag<N>{}); })          // 定义之前无法推导返回类型，表达式非良构
        return next<N + 1>();
    else
        return (void)setter<N>{}, N;
}

static_assert(next() == 0);
static_assert(next() == 1);   // 字面上相同的表达式，结果变了
static_assert(next() == 2);
```

截至写作时，Clang 23 接受这段代码。核心语言问题 [[CWG2118]] *Stateful metaprogramming via friend injection* 由 Richard Smith 于 2015 年 4 月 27 日提交，其中写道"This technique is arcane and should be made ill-formed"（这种技巧晦涩难懂，应当使之非良构）。2015 年 5 月的 CWG 会议记录写明，CWG 同意这类技巧应当非良构，但禁止它的机制尚未确定。截至本页更新时，该问题仍是 open 状态，所以这段代码不标判定：标准没有明确禁止它，但委员会的意向是禁止，依赖它的代码随时可能失效。与此相关的另一条规则是 [[temp.res]] 中的假设实例化规则（由 [[CWG1850]] 引入）：如果一个构造在假设实例化和实际实例化中的解释不同，程序是 IFNDR。

C++26 的反射从设计上换了一种方式来处理编译期的副作用。`define_aggregate` 这类调用会产生注入声明（injected declaration），而能产生注入声明的表达式只允许出现在 consteval 块中；每个注入声明有规定好的合成点，查询看到哪些声明由求值上下文决定，而不是依赖实例化时机这种实现细节（[[expr.const.reflect]]，以及 [[expr.const.core#2.32]]）。

### 编译期资源限制

前面提到，标准对递归模板实例化建议的最低限额是 1024 层（[[implimits]]）。同一附录还给出了 `constexpr` 函数递归调用至少 512 层、一个核心常量表达式中求值的完整表达式至少 1 048 576 个等建议值。编译器通常提供开关来调整这些限制（如 Clang 的 `-ftemplate-depth=`）。这些数字只是建议的下限，所以同一个深度递归的元程序在一个编译器上能通过、在另一个编译器上失败，是符合标准的。这也是 C++11 以后的设计普遍用包展开、折叠表达式、`template for` 替代递归的原因之一：它们的实例化深度是常数。

## 时间线

| 年份 | 事件 | 出处 |
|---|---|---|
| 约 1987 | Stroustrup 开始设计模板，追求通用、零开销、良好接口三个目标 | HOPL IV §6.1 |
| 1990 | 模板在西雅图会议上被 ANSI 委员会接受 | HOPL III §2.5 |
| 1991 | Cfront 3.0 成为第一个支持模板的编译器 | HOPL III §3 |
| 1994 | Unruh 在委员会会议上展示用错误信息输出素数的程序（N462） | Unruh 网页；HOPL III §7.2.2 |
| 1995 | Veldhuizen 发表 *Expression Templates* 与 *Using C++ Template Metaprograms*；Myers 发表 *Traits*；偏特化加入 C++ | HOPL III §4.1.5、§7.2.2 |
| 1998 | C++98 发布；Boost 成立 | HOPL III §4.2 |
| 2000 | Czarnecki、Eisenecker 出版 *Generative Programming* | HOPL IV §10.5.2 |
| 2001 | Alexandrescu 出版 *Modern C++ Design*，发布 Loki | 原书 |
| 2002 | Vandevoorde、Josuttis 出版 *C++ Templates*，提出 SFINAE 一词 | 原书；Wakely 2013 |
| 2003 | Boost.MPL 随 Boost 1.30 发布；Veldhuizen 发表 *C++ Templates are Turing Complete*；enable_if 论文发表 | Boost 发布说明；HOPL III |
| 2004 | Boost.enable_if 随 Boost 1.31 发布；Abrahams、Gurtovoy 出版 *C++ Template Metaprogramming*；变参模板首次提出（N1704） | Boost 发布说明；[[N1704]] |
| 2008 | Boost.Fusion（1.35）、Boost.Proto（1.37）发布 | Boost 发布说明 |
| 2009 | C++0x 概念被移出草案 | HOPL IV §6 |
| 2011 | C++11：变参模板、`decltype`、`constexpr`、别名模板、`static_assert`、`<type_traits>` | HOPL IV §4 |
| 2013 | SG7 成立，发出反射提案征集（N3814） | HOPL IV §9.6.2 |
| 2014 | C++14：变量模板、放宽的 `constexpr`；`void_t` 提出（N3911） | [[N3651]]、[[N3652]]、[[N3911]] |
| 2015 | 检测惯用法（N4502）；Dimov 发表 *Simple C++11 metaprogramming*；CWG2118 提交 | [[N4502]]；[[CWG2118]] |
| 2016 | Boost.Hana 随 Boost 1.61 发布 | Boost 发布说明 |
| 2017 | C++17：`if constexpr`、折叠表达式、`void_t`；Boost.Mp11 随 Boost 1.66 发布；SG7 讨论转向基于值的反射（P0598、P0633、P0425） | 各提案；Boost 发布说明 |
| 2018 | P1240R0 *Scalable Reflection in C++* | [[P1240R0]] |
| 2020 | C++20：概念、`consteval`、类类型非类型模板形参、编译期动态内存 | [[P0734R0]]、[[P1073R3]]、[[P0732R2]]、[[P0784R7]] |
| 2021 | Reflection TS 以 ISO/IEC TS 23619:2021 发布；P2320 提出 `^` 与 `[: :]` | ISO 目录；[[P2320R0]] |
| 2023 | P2996R0 *Reflection for C++26* | [[P2996R0]] |
| 2024 | P3381 把反射运算符改为 `^^` | [[P3381R0]] |
| 2025 | 索非亚会议把 P2996R13、P1306R5、P3394R4 等七篇反射论文并入 C++26 | Sutter 会议报告 |
| 2026 | GCC 16.1 发布，实现 P2996R13、P1306R5 等（`-freflection`） | GCC 16.1 发布公告 |

## 现状与未来

到 C++26 为止，模板元编程的大部分传统用途都有了更直接的替代：值的计算用 `constexpr` 函数，按类型分派用 `if constexpr` 和概念，类型列表的操作用包展开、折叠表达式和 C++26 的包索引（[[P2662R3]]），对程序结构的查询用反射。HOPL IV（§10.5.2）的看法是，需要一个值时，函数是计算它的最好方式，即使在编译期也是如此；传统的模板元编程最好留给计算新类型和控制结构。

实现方面，GCC 16.1（2026 年 4 月）已经在 `-std=c++26 -freflection` 下实现了 P2996R13 和展开语句等论文（GCC 16.1 发布公告）。Bloomberg 维护着一个实现 P2996 的实验性 Clang 分支 clang-p2996。本页写作所用的 Homebrew Clang 23 没有提供 `<meta>` 头文件，也不识别 `-freflection`。

C++26 的反射主要用于读取程序结构，能生成的东西很有限（例如用 `define_aggregate` 补全一个类的定义）；更一般的代码生成仍在提案阶段。已经公开的方向包括：

- [[P3294R2]] *Code Injection with Token Sequences*（Revzin、Alexandrescu、Vandevoorde）：用记号序列描述要注入的代码；
- [[P3157R1]] *Generative Extensions for Reflection*（Alexandrescu、Revzin、Lelbach、Garland）：讨论反射在代码生成方面应具备的能力；
- [[P3420R1]] *Reflection of Templates*：反射模板本身，而不只是它的特化；
- [[P0707R5]] *Metaclass functions for generative C++*（Sutter）：在类定义时运行编译期函数来生成成员，这是 2017 年起的 metaclass 提案的后续；
- [[P2758R5]] *Emitting messages at compile time*（Revzin）：让编译期代码输出自定义的诊断信息。

最后一项与本页开头的故事正好对应：1994 年，Unruh 只能借编译器的错误信息输出计算结果；P2758 提议的是让编译期程序用正式的手段输出诊断。以上提案目前都没有被采纳，内容也可能大幅改变。

## 参考资料

当事人与一手资料

- Erwin Unruh，*Primzahlen* 与 *Primzahlen Original*，个人网页 erwin-unruh.de（2002 年 1 月 1 日更新），含 1994 年原版程序与 MetaWare 编译器输出。
- E. Unruh，*Prime number computation*，ISO SC22 WG21 N462 = ANSI X3J16 94-0075（1994）。
- Todd Veldhuizen，*Expression Templates*，C++ Report 7(4)，1995 年 5 月；*Using C++ Template Metaprograms*，C++ Report 7(5)，1995 年 6 月；*C++ Templates are Turing Complete*，2003。
- Nathan C. Myers，*Traits: a new and useful template technique*，C++ Report，1995 年 6 月。
- J. Järvi、J. Willcock、H. Hinnant、A. Lumsdaine，*Function overloading based on arbitrary properties of types*，C/C++ Users Journal 21(6)，2003 年 6 月。
- Jonathan Wakely，*SFINAE Functionality Is Not Arcane Esoterica*，ACCU 2013 演讲幻灯片（引用了 Vandevoorde 对 SFINAE 一词来历的说明）。
- Peter Dimov，*Simple C++11 metaprogramming*，2015（收录于 Boost.Mp11 文档）。
- Filip Roséen，*Non-Constant Constant-Expressions in C++*，博客文章，2015；std-discussion 邮件列表同名讨论，2015 年 4 月。
- Andrew Pardoe，*Two-phase name lookup support comes to MSVC*，Microsoft C++ Team Blog，2017 年 9 月 11 日。
- Herb Sutter，*Trip report: June 2025 ISO C++ standards meeting (Sofia, Bulgaria)*，2025 年 6 月 21 日。
- GCC 16.1 发布公告，isocpp.org 转载，2026 年 4 月 30 日。
- Boost 1.30.0、1.31.0、1.35.0、1.37.0、1.61.0、1.66.0 发布说明。

书与综述

- Bjarne Stroustrup，*The Design and Evolution of C++*，Addison-Wesley，1994。
- Bjarne Stroustrup，*Evolving a language in and for the real world: C++ 1991–2006*，HOPL III，2007（§4.1.5 traits，§7.2.2 模板元编程）。
- Bjarne Stroustrup，*Thriving in a Crowded and Changing World: C++ 2006–2020*，HOPL IV，2020（§4.3.2 变参模板，§4.5 SFINAE 与元编程支持，§6 概念，§9.6.2 静态反射，§10.5.2 元编程）。
- Krzysztof Czarnecki、Ulrich Eisenecker，*Generative Programming*，Addison-Wesley，2000。
- Andrei Alexandrescu，*Modern C++ Design*，Addison-Wesley，2001。
- David Vandevoorde、Nicolai M. Josuttis，*C++ Templates: The Complete Guide*，Addison-Wesley，2002（第 8 章 SFINAE，第 17 章元程序及其历史注记）。
- David Abrahams、Aleksey Gurtovoy，*C++ Template Metaprogramming*，Addison-Wesley，2004。

WG21 文档（按主题）

- C++11：[[N1704]]、[[N2242]]（变参模板）；[[N2343]]（decltype）；[[N2235]]（constexpr）；[[N2258]]（别名模板）；[[N1720]]（static_assert）；[[N1424]]（type traits）；[[N2240]]（enable_if 与 conditional）。
- 检测：[[N3911]]（void_t）；[[N4436]]、[[N4502]]（检测惯用法）；[[CWG1558]]。
- C++14/17：[[N3651]]、[[N3652]]、[[N3655]]、[[N3658]]、[[P0006R0]]、[[N4295]]、[[P0127R2]]、[[P0013R1]]；`static if` 与 `if constexpr`：[[N3322]]、[[N3329]]、[[N3613]]、[[N4461]]、[[P0292R2]]。
- C++20：[[N3580]]、[[P0734R0]]（概念）；[[P1073R3]]（consteval）；[[P0732R2]]、[[P1907R1]]（类类型 NTTP）；[[P0784R7]]（编译期动态内存）；[[P0634R3]]（typename 可选）。
- 反射：[[N3814]]、[[N3996]]、[[P0194R6]]、[[N4766]]、[[P0598R0]]、[[P0633R0]]、[[P0425R0]]、[[P1240R0]]、[[P1733R0]]、[[P2320R0]]、[[P2996R0]]、[[P2996R13]]、[[P3381R0]]、[[P0589R0]]、[[P1306R0]]、[[P1306R5]]、[[P3394R4]]、[[P3293R3]]、[[P3491R3]]、[[P3096R12]]、[[P3560R2]]、[[P3289R1]]。
- 后续提案：[[P3294R2]]、[[P3157R1]]、[[P3420R1]]、[[P0707R5]]、[[P2758R5]]；包索引 [[P2662R3]]。
- 核心语言问题：[[CWG903]]、[[CWG1850]]、[[CWG2118]]。
