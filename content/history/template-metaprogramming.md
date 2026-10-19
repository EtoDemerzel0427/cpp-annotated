---
title: 模板元编程：从意外的图灵完备到静态反射
summary: 模板本来只为容器和算法设计，却意外成了一门编译期语言；C++11 以后，语言一步步用 constexpr、变参模板、if constexpr、概念和静态反射接手它的各项用途，旧写法的痕迹至今留在规则里。
status: draft
order: 50
papers: N2242, N2343, N2235, N2258, N3911, N4502, N3329, N3613, P0292R2, P0734R0, P1073R3, P0732R2, P0784R7, P0425R0, P0598R0, P1240R0, P0194R6, P2320R0, P3381R0, P2996R13, P1306R5, P3491R3, P3294R2, P2758R5
related: temp.deduct, temp.res, temp.variadic, temp.constr, expr.const, meta, meta.reflection, stmt.expand, expr.reflect, topics/compile-time-programming, topics/two-phase-lookup, history/concepts, history/constexpr
tags: 模板, 元编程, SFINAE, constexpr, 概念, 反射, 历史
updated: 2026-10-19
---

!!! tldr
    - 模板只为写 `vector<T>` 这类泛型代码而设计。特化、非类型参数和递归实例化凑在一起，意外构成了一门在编译期运行的语言。
    - C++98 的元编程把一切都编码成类型：特化充当分支，递归充当循环，`enum` 存放结果，SFINAE 加 `sizeof` 用来检测类型的性质。
    - 从 C++11 起，语言逐项接手这些用途：`constexpr` 函数计算值，变参模板取代类型列表，`if constexpr` 取代成对的 `enable_if`，概念把要求写进接口。
    - 反射没有沿用基于类型的 Reflection TS，而是改成基于值的 `std::meta::info`，因为编译期的值计算已经足够强，而且比实例化类型更省资源。C++26 采纳了这个设计。
    - `typename` 和 `template` 消歧符、两阶段查找、1024 层实例化深度的建议下限，以及至今悬而未决的友元注入问题，都是这段历史留在今天规则里的痕迹。

本页的史料主要来自 Stroustrup 的两篇 HOPL 论文（HOPL III：*Evolving a language in and for the real world: C++ 1991–2006*；HOPL IV：*Thriving in a Crowded and Changing World: C++ 2006–2020*）、WG21 文档和当事人自己的文章。规则本身的细节见各条款页和专题 [[topics/compile-time-programming]]。

## 一、模板没有被设计成一门语言

Stroustrup 回顾说，大约从 1987 年起设计模板时，他想要三样东西（HOPL IV §6.1）：

- 足够通用，能表达设计者没有预料到的用法；
- 与手写代码相比零开销，`vector` 要能和 C 数组竞争；
- 接口有良好的定义，模板实参的类型检查和重载与普通函数一样好。

前两条做到了，第三条没有。HOPL IV 的总结是：C++ 得到了图灵完备、胜过手写的性能，以及很差的接口。前两条让模板广受欢迎，也让模板成了一门编译期语言；第三条造成了三十年里难读的错误信息，最终引出了 C++20 的概念（见 [[history/concepts]]）。

## 二、1994 年：编译器在错误信息里列出素数

1994 年，西门子的 Erwin Unruh 在一次标准委员会会议上展示了一段不能通过编译的程序。编译器的错误信息里依次出现了 2、3、5、7、11……这些素数是编译器在实例化模板时算出来的（Unruh 的个人网页；HOPL III §7.2.2；委员会文档 N462）。

原版程序依赖 C++98 的一条规则：值为零的整型常量表达式都是空指针常量。合数让初始值为 0，转换成功；素数让初始值为 1，转换失败并报错。[[CWG903]] 后来把空指针常量限定为值为零的整数字面量，原版在今天的编译器上对每个数都报错。下面按今天的规则改写，思路不变，只让素数走进一条必然出错的路径：

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

Clang 23 给出 8 条错误，形如 `no viable conversion from 'int' to 'D<19>'`，尖括号里依次是 2、19、17、13、11、7、5、3。

这段程序说明，模板实例化机制本身就能做非平凡的计算。HOPL III §7.2.2 记载，Stroustrup 等人觉得它了不起而不是可怕，因为完全的通用性正是模板的设计目标。2003 年 Todd Veldhuizen 写了一篇短文，给出模板图灵完备的半形式化证明；HOPL III 的表述更谨慎：在忽略编译器资源限制的前提下，模板实例化机制是图灵完备的。

## 三、C++98：用类型表示一切

C++98 的编译期语言只有类型和整型常量这两种数据。所有计算都要借道类型系统完成。

### 值、分支和循环

下面左边是 C++98 写法：类模板的特化充当递归的终止条件，结果存在 `enum` 里，断言靠数组长度不能为负来实现。右边是 C++14 的写法，同样在编译期求值：

<div class="compare" markdown="1">

```cpp run ok std=c++98
template <unsigned N>
struct fact {
  enum { value = N * fact<N - 1>::value };
};
template <>
struct fact<0> { enum { value = 1 }; };

int a[fact<5>::value == 120 ? 1 : -1];
```

```cpp run ok
constexpr unsigned fact(unsigned n) {
  unsigned r = 1;
  for (; n > 1; --n) r *= n;
  return r;
}

static_assert(fact(5) == 120);
```

</div>

左边每算一个值就要实例化一个类，`fact<5>` 会产生 6 个类。编译器要为每个实例化保存完整的类信息，这正是后来编译时间和内存消耗失控的根源。

编译期的条件分支也是一个类模板，选择结果是一个类型：

```cpp run ok std=c++98 title="if_.cpp"
template <bool B, class X, class Y> struct if_ { typedef X type; };
template <class X, class Y> struct if_<false, X, Y> { typedef Y type; };

typedef if_<(sizeof(int) < 4), long, int>::type small_int;
int main() { small_int x = 0; return x; }
```

Veldhuizen 1995 年在 *C++ Report* 上发表的 *Using C++ Template Metaprograms* 推广了这类写法。今天标准库里的 `std::conditional`（[[meta.trans.other]]）就是 `if_`。

### traits：编译期查询类型的性质

STL 需要在编译期问一个迭代器指向什么类型。早期 STL 靠重载来做，既不系统又容易出错。Nathan Myers 1995 年提出的解法是：用一个辅助模板集中存放类型的相关信息，再用偏特化处理指针这种没有成员类型的情况（HOPL III §4.1.5）。

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

偏特化本身也是 1995 年才加入 C++ 的。traits 是这一时期最成功的遗产：`std::iterator_traits` 至今仍在使用，`<type_traits>`（[[meta]]）把这种写法推广到所有类型性质。

### 表达式模板：零开销目标的副产品

`x = a + b + c` 按普通的运算符重载实现，会产生两个临时向量和三次循环。表达式模板让 `operator+` 不立即计算，而是返回一个记录计算方式的对象，等到赋值时用一个循环一次算完：

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

Veldhuizen 和 Daveed Vandevoorde 各自独立发现了这种技术（HOPL III §7.2.2）。它说明元编程不只是炫技：表达式的结构被编码进类型，编译器就能为整个表达式生成一个融合后的循环。Eigen 等线性代数库至今仍用这种方式。

### SFINAE：检测与重载开关

模板实参推导有一条规则：把推导出的实参代入函数模板的声明时，如果产生了无效的类型或表达式，这个候选就被静默地移出重载集，而不是报错（[[temp.deduct#8]]）。这条规则原本只是为了让无关的模板不妨碍重载决议，后来被人当作编译期的开关使用。Vandevoorde 和 Josuttis 在 *C++ Templates*（2002）中给它起了名字 SFINAE（Substitution Failure Is Not An Error）。

C++98 里检测一个类型有没有 `size_type` 成员，要用 `sizeof` 测量重载调用的返回类型。C++20 可以直接写一个 requires 表达式：

<div class="compare" markdown="1">

```cpp run ok std=c++98
template <class T> struct has_size_type {
  typedef char yes[1];
  typedef char no[2];
  template <class U> static yes&
    test(typename U::size_type*);
  template <class U> static no& test(...);
  static const bool value =
    sizeof(test<T>(0)) == sizeof(yes);
};
```

```cpp run ok
template <class T>
concept has_size_type =
  requires { typename T::size_type; };
```

</div>

左边的 `sizeof` 不求值调用表达式，只计算返回类型的大小。`U::size_type` 无效时第一个 `test` 被 SFINAE 移除，只剩下返回 `no&` 的版本，两种结果靠数组大小区分。

把 SFINAE 包装成通用工具的是 `enable_if`：条件为假时它没有 `type` 成员，用它写的返回类型就会替换失败。Järvi、Willcock、Hinnant、Lumsdaine 在 2003 年发表了这一技术，Boost.enable_if 随 2004 年的 Boost 1.31 发布，C++11 收入标准库。

### 代价

2000 年代，*Modern C++ Design*（Alexandrescu，2001）、Boost.MPL（2003）等书和库把这些技法系统化了。HOPL IV §4.5.2 把那十年比作元编程的蛮荒西部：错误信息极其糟糕，编译时间很长，很容易耗尽编译器的内存和递归深度。Stroustrup 提到，他见过几百行元编程代码让编译耗时以分钟计，一个简单错误引出的诊断长达数千行（HOPL IV §10.5.2）。

根本原因仍是第一节说的第三个目标：模板对实参的要求只写在实现里，编译器只能在实例化的深处报告某个表达式无效。

## 四、C++11 到 C++17：语言接手

HOPL IV §4.5.2 把 C++11 对元编程的支持分成两条线：语言方面有 `constexpr` 函数、变参模板、别名模板、`decltype`，库方面有 `<type_traits>` 和 `enable_if`。共同的方向是让编译期计算不再需要借道类型系统。

### 变参模板取代类型列表

C++98 没有办法让一个模板接受任意多个类型。Loki 等库用嵌套的 `Typelist<Head, Tail>` 表示类型序列，每个操作都是一组递归特化。C++11 的变参模板（[[N2242]]，规则见 [[temp.variadic]]）把类型序列变成了语言内建的形参包：

<div class="compare" markdown="1">

```cpp run ok std=c++98
struct NullType {};
template <class H, class T>
struct Typelist { typedef H Head; typedef T Tail; };

template <class TL> struct Length;
template <> struct Length<NullType> {
  enum { value = 0 };
};
template <class H, class T>
struct Length<Typelist<H, T> > {
  enum { value = 1 + Length<T>::value };
};

typedef Typelist<int,
        Typelist<char,
        Typelist<double, NullType> > > L;
int check[Length<L>::value == 3 ? 1 : -1];
```

```cpp run ok
template <class... T> struct list {};

template <class L> struct length;
template <class... T>
struct length<list<T...>> {
  static constexpr auto value =
      sizeof...(T);
};

using L = list<int, char, double>;
static_assert(length<L>::value == 3, "");
```

</div>

左边求长度要实例化 4 个 `Length` 特化，右边只要 1 个。据 HOPL IV §4.3.2，Stroustrup 起初觉得变参模板的记法晦涩、过于依赖递归，后来被 Douglas Gregor 的测量说服：与当时的替代写法相比，变参模板有时能让编译快 20 倍。

Peter Dimov 2015 年在 *Simple C++11 metaprogramming* 一文中进一步指出，任何变参类模板都可以直接当类型列表用，任何别名模板都可以直接当元函数用（[[N2258]] 引入的别名模板省掉了 `typename ...::type`）。对每个元素做变换只需一次包展开，不再需要递归：

```cpp run ok std=c++17 title="transform.cpp"
#include <tuple>
#include <type_traits>

template <template <class...> class F, class L>
struct transform_impl;
template <template <class...> class F,
          template <class...> class L, class... T>
struct transform_impl<F, L<T...>> {
    using type = L<F<T>...>;                 // 一次包展开，没有递归
};
template <template <class...> class F, class L>
using transform = typename transform_impl<F, L>::type;

static_assert(std::is_same_v<
    transform<std::add_pointer_t, std::tuple<int, char>>,
    std::tuple<int*, char*>>);
```

这些原语后来成为 Boost.Mp11。标准库也沿着同一方向补了别名：C++14 的 `std::remove_cv_t` 等 `_t` 别名，C++17 的 `std::is_same_v` 等 `_v` 变量模板。

### decltype 让 SFINAE 作用于表达式

C++03 的 SFINAE 主要作用于类型，比如 `typename U::size_type`。想检测能否调用 `x.size()`，要绕很大的弯，而且表达式里的错误是否算替换失败，规则并不清楚。

C++11 有了 `decltype`（[[N2343]]）和尾置返回类型，可以直接写 `auto f(T& x) -> decltype(x.size())`：表达式无效就替换失败。这通常叫 expression SFINAE。HOPL IV §4.5.1 提到，SFINAE 的规则在 C++11 中变得更一般，代价是编译器必须能干净地撤销一次失败的替换。

### void_t 与检测惯用法

每检测一种性质仍要写一套重载。Walter Brown 在 [[N3911]] 中提议加入一个看起来什么也不做的别名模板 `template <class...> using void_t = void;`，它和偏特化配合，就能用一个特化表达一次检测：

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

表达式良构时 `void_t<...>` 就是 `void`，与主模板的默认实参一致，偏特化被选中；表达式非良构时替换失败，偏特化被丢弃。

这里有一个规则上的细节：别名模板中没有用到的实参是否参与替换，C++11 原本没有说清楚，[[CWG1558]] 才明确它们必须参与。所以早期一些编译器上的 `void_t` 要换一种写法才能生效。`void_t` 进入了 C++17；Brown 在 [[N4502]] 中把它推广成的 `is_detected` 只进入了 Library Fundamentals TS v2，因为 C++20 的 requires 表达式提供了更直接的写法。

### static if 被拒，if constexpr 被接受

C++11 中，按类型选择两种实现，要写两个条件互斥的 `enable_if` 重载。C++17 的 `if constexpr`（[[P0292R2]]，规则见 [[stmt.if]]）把分派写回了函数体：

<div class="compare" markdown="1">

```cpp run ok std=c++11
#include <string>
#include <type_traits>

template <class T>
typename std::enable_if<
  std::is_arithmetic<T>::value,
  std::string>::type
describe(const T& x) {
  return std::to_string(x);
}
template <class T>
typename std::enable_if<
  !std::is_arithmetic<T>::value,
  std::string>::type
describe(const T& x) {
  return std::string(x);
}
```

```cpp run ok
#include <string>
#include <type_traits>

template <class T>
std::string describe(const T& x) {
  if constexpr (std::is_arithmetic_v<T>)
    return std::to_string(x);
  else
    return std::string(x);
}
```

</div>

`if constexpr` 走过一段弯路。2012 年，Sutter、Bright、Alexandrescu 在 [[N3329]] 中提议仿照 D 语言引入 `static if`。它可以出现在命名空间和类作用域，用来控制一个声明是否存在：

```cpp title="static-if-sketch.cpp"
// 按 N3329 的思路写的示意，不是合法的 C++
template <class T>
struct Holder {
    static if (std::is_integral<T>::value) {
        long value;       // 成员是否存在取决于条件
    } else {
        double value;
    }
};
```

Stroustrup、Dos Reis、Sutton 在 [[N3613]] 中反对。他们的技术理由是：声明是否存在取决于任意编译期条件，代码会变得难以分析；而且这与当时正在设计的概念相冲突。2015 年 Ville Voutilainen 重新提出时，范围收窄到函数体内的语句，最终成为 `if constexpr`。

这次取舍留下的痕迹是：今天按条件选择成员类型仍要用 `std::conditional_t`，按条件启用成员函数用 C++20 的 requires 子句，C++ 至今没有按条件增删数据成员这类声明的语法。

同在 C++17 加入的折叠表达式（[[expr.prim.fold]]）去掉了另一类递归：`(xs + ... + 0)` 一行就能对整个包求和，不再需要递归主模板加终止重载。

## 五、C++20：要求写进接口

### 概念

概念的历史另有专页（[[history/concepts]]）。对元编程来说，概念取代了 `enable_if` 和检测惯用法的大部分用途：约束写在声明上，不满足时编译器能指出是哪一条要求不成立。

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

调用 `count(42)` 时，Clang 23 依次说明：候选被忽略，因为约束不满足；`int` 不满足 `Sized`；`x.size()` 无效，因为 `const int` 不是类类型。约束的规则见 [[temp.constr]]。

### consteval 与类类型的模板实参

C++20 还有两项与元编程关系密切的改动：

- `consteval` 函数（[[P1073R3]]）的每次调用都必须在编译期求值。P1073R3 说明，它的直接推动力是反射：反射查询只有在编译期才有意义。
- 类类型可以作非类型模板形参（[[P0732R2]]，后经 [[P1907R1]] 改为结构化类型的模型）。在此之前，想把一个字符串当模板实参，只能把它拆成字符的变参包。

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

int main() {
    using id = field<"id">;
    return id::name[0] == 'i' ? 0 : 1;
}
```

[[P0784R7]] 则允许在常量求值中使用 `new` 和 `delete`，于是 `std::vector`、`std::string` 可以在编译期使用（只要内存在常量求值结束前释放）。这一项是后来基于值的反射的前提，原因见下一节。

## 六、反射：从类型到值

### 模板元编程回答不了的问题

模板能计算类型，却回答不了一个类有哪些成员、一个枚举有哪些枚举项。2013 年 WG21 成立了反射研究组 SG7。据 HOPL IV §9.6.2，当时大家一致认为 C++ 需要的是静态反射：运行期遍历常驻的数据结构，数据量大、表示复杂，还有运行期开销。

### 第一版设计：反射结果是类型

最先成形的是 Matúš Chochlík 等人的设计（[[P0194R6]]），它成为 Reflection TS 的基础（工作草案 [[N4766]]，2021 年作为 ISO/IEC TS 23619 发布）。`reflexpr(X)` 产生一个元对象类型，查询用 traits 风格的模板完成。这和上一节的元编程是同一种风格。

2017 年起，SG7 的讨论转向了基于值的设计。Louis Dionne 在 [[P0425R0]] 中总结说，经典模板元编程很难用，也不能扩展；更好的方向是基于 `constexpr` 的元编程加上基于值的反射，第一步是让常量表达式支持可变长容器（后来的 P0784R7）。Vandevoorde 在 [[P0598R0]] 中提出让反射通过值而不是类型进行，2018 年的 [[P1240R0]] 给出了完整的方案：所有反射结果都是同一个类型 `std::meta::info` 的值，用 `consteval` 函数查询。

HOPL IV §9.6.2 列出了支持这次转向的理由：分析和生成代码本质上是函数式的；`constexpr` 计算已经强到可以承担元编程；编译器内部为函数建立的数据结构，比为类型建立的小得多、存在的时间也短得多，所以更省内存、编译更快。第三条针对的正是第三节里 `fact<5>` 要产生 6 个类的那类开销。

两种设计取同一个枚举的第一个枚举项名字，写法如下。本机 Clang 23 两者都不支持，均未编译验证：

<div class="compare" markdown="1">

```cpp
// Reflection TS（N4766）：结果是类型
namespace r = std::experimental::reflect;
using Es = r::get_enumerators_t<
    reflexpr(Color)>;
using E0 = r::get_element_t<0, Es>;
constexpr auto name = r::get_name_v<E0>;
```

```cpp
// C++26（P2996）：结果是值
constexpr auto name =
  std::meta::identifier_of(
    std::meta::enumerators_of(
      ^^Color)[0]);
```

</div>

右边的 `enumerators_of` 返回 `std::vector<std::meta::info>`，`[0]` 是普通的下标运算。左边的每一步都要实例化一个模板。

记法也换过几次。P1240R0 用关键字 `reflexpr`；2021 年的 [[P2320R0]] 改用一元 `^` 表示反射、用 `[: :]` 把反射值拼接（splice）回代码，理由之一是记法应当像取地址的 `&` 一样简短；2024 年的 [[P3381R0]] 又把 `^` 改成新记号 `^^`，因为 `^` 与 Clang 在 Objective-C++ 中使用的 block 扩展存在解析冲突。

### C++26 的静态反射

[[P2996R13]] *Reflection for C++26* 是 P1240 功能的一个子集，论文说明先从较小的范围开始，更强的功能以后再加。它和展开语句 `template for`（[[P1306R5]]）、注解、`define_static_array`（[[P3491R3]]）等论文一起进入了 C++26。

下面是 P2996 中枚举转字符串的例子，略有改写。本机 Clang 23 没有 `<meta>` 头文件，所以这段代码没有编译验证，也不标判定；GCC 16.1 可以用 `-std=c++26 -freflection` 试验（GCC 16.1 发布说明）。

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

每一样东西都对应前面的一段历史：`^^E` 是值而不是类型；`enumerators_of` 是 `consteval` 函数，返回编译期的 `std::vector`；`std::vector` 不能跨越常量求值的边界留到运行期，所以要用 `define_static_array` 转成静态数组；`template for` 以不同的常量实例化每次迭代的循环体，取代了过去的递归模板或 `index_sequence` 加折叠表达式。规则见 [[expr.reflect]]、[[stmt.expand]]、[[meta.reflection]]。

## 七、留在今天规则里的痕迹

### typename 与 template 消歧符

模板定义中的名字分两个阶段查找：不依赖模板形参的名字在定义处绑定，依赖的名字推迟到实例化时（[[temp.res]]，专题见 [[topics/two-phase-lookup]]）。这要求编译器在看到定义时就能解析它，于是程序员必须在依赖名前标出它是类型还是模板：

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

去掉 `first` 里的 `template`，Clang 23 报告缺少 `template` 关键字。C++20 的 [[P0634R3]] 让 `typename` 在若干只可能是类型的语境中变为可选，但 `template` 消歧符仍然需要。

### 两阶段查找

两阶段查找的后果常常出人意料：在模板定义之后才声明的非依赖重载，对模板不可见。

```cpp run ok title="two-phase.cpp"
void g(double) {}

template <class T>
void f(T) {
    g(1);          // 非依赖调用：在定义处查找，只看得到 g(double)
}

void g(int) {}     // 这个更好的匹配来得太晚

int main() { f(0); }   // 调用的是 g(double)
```

并非所有编译器都长期按这个模型实现。MSVC 过去把模板体记成一串记号，到实例化时才解析，直到 Visual Studio 2017 15.3 才在 `/permissive-` 下开始支持两阶段查找（Andrew Pardoe，*Two-phase name lookup support comes to MSVC*，Microsoft C++ Team Blog，2017）。所以老代码在不同编译器上可能有不同的行为。

### 友元注入与有状态元编程

模板元编程按理说是纯函数式的：同一个表达式求值两次，结果应该相同。2015 年，Filip Roséen 展示了一种打破这一点的办法。类模板里定义的友元函数要到类被实例化时才算定义，而一个函数是否已经定义，可以在编译期观察到：

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

Clang 23 接受这段代码。[[CWG2118]] *Stateful metaprogramming via friend injection* 认为这种技巧应当是非良构的，CWG 同意这个方向，但还没有确定禁止它的措辞。截至本页更新时这个问题仍未解决，所以代码不标判定：标准没有明确禁止它，依赖它的代码随时可能失效。

C++26 的反射换了一种方式处理编译期副作用。`define_aggregate` 这类能产生注入声明的调用，只允许出现在 consteval 块中；查询能看到哪些声明，由规定好的求值上下文决定，而不是取决于实例化的时机（[[expr.const.reflect]]）。

### 实现限额

附录 [[implimits]] 建议递归嵌套的模板实例化至少支持 1024 层，`constexpr` 函数的递归调用至少 512 层。这些只是建议的下限，同一个深度递归的元程序在一个编译器上能通过、在另一个上失败，是符合标准的。[[temp.inst]] 还规定无限递归实例化的结果是未定义的。C++11 以后的设计普遍用包展开、折叠表达式、`template for` 代替递归，原因之一就是它们的实例化深度是常数。

## 旧写法与今天的替代

| 用途 | C++98 写法 | 今天的写法 |
|---|---|---|
| 计算一个值 | 特化递归，结果存在 `enum` | `constexpr` / `consteval` 函数（C++11/14/20） |
| 编译期断言 | 长度可能为负的数组 | `static_assert`（C++11） |
| 类型序列 | 嵌套 `Typelist` 加递归 | 形参包、包展开、包索引（C++11/26） |
| 按条件选择实现 | 成对的 `enable_if` 重载 | `if constexpr`（C++17）、概念（C++20） |
| 检测类型性质 | `sizeof` 加重载 | `void_t`（C++17）、requires 表达式（C++20） |
| 对包求和等归约 | 递归主模板加终止重载 | 折叠表达式（C++17） |
| 把字符串当模板实参 | 字符的变参包 | 类类型非类型模板形参（C++20） |
| 列出成员、枚举项 | 无法实现 | 静态反射（C++26） |

HOPL IV §10.5.2 的看法是：需要一个值时，函数是计算它的最好方式，即使在编译期也一样；传统的模板元编程最好留给计算新类型。

## 仍在进行的工作

C++26 的反射主要用于读取程序结构，能生成的东西很有限，例如用 `define_aggregate` 补全一个类的定义。更一般的代码生成仍在提案阶段，例如用记号序列描述要注入代码的 [[P3294R2]]。[[P2758R5]] 提议让编译期代码输出自定义的诊断信息，正好对应本页开头的故事：1994 年 Unruh 只能借错误信息输出计算结果。截至写作时，这些提案都没有被采纳。

## 参考资料

- Bjarne Stroustrup，*Evolving a language in and for the real world: C++ 1991–2006*，HOPL III，2007（§4.1.5 traits，§7.2.2 模板元编程）。
- Bjarne Stroustrup，*Thriving in a Crowded and Changing World: C++ 2006–2020*，HOPL IV，2020（§4.3.2 变参模板，§4.5 SFINAE 与元编程，§6.1 模板的设计目标，§9.6.2 静态反射，§10.5.2 元编程）。
- Erwin Unruh，*Primzahlen* 个人网页（erwin-unruh.de），含 1994 年原版程序；委员会文档 N462（1994）。
- Todd Veldhuizen，*Using C++ Template Metaprograms*，C++ Report，1995；*C++ Templates are Turing Complete*，2003。
- Nathan C. Myers，*Traits: a new and useful template technique*，C++ Report，1995。
- David Vandevoorde、Nicolai M. Josuttis，*C++ Templates: The Complete Guide*，2002。
- Peter Dimov，*Simple C++11 metaprogramming*，2015（收录于 Boost.Mp11 文档）。
- Andrew Pardoe，*Two-phase name lookup support comes to MSVC*，Microsoft C++ Team Blog，2017。
- GCC 16.1 发布说明，2026。
- 核心语言问题：[[CWG903]]、[[CWG1558]]、[[CWG2118]]。
