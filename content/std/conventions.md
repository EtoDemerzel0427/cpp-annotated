---
title: 其他编辑约定
summary: 库条文的其余写法约定：仅用于说明的实体（如 decay-copy）、定制点对象与算法函数对象、枚举类型与位掩码类型、ntbs 等字符串术语、没有写出的成员，以及 freestanding 标注的含义。
status: done
covers: *
papers: P0896R4, P3136R1, P1642R11, P2407R5
related: description, structure.specifications, requirements, compliance, basic.lookup.argdep, temp.param, class.prop, intro.compliance
tags: 库, 阅读方法, CPO, niebloid, exposition only, freestanding
updated: 2026-10-19
---

!!! tldr
    - 标准里带连字符的斜体名字（*decay-copy*、*synth-three-way*）和注释为 exposition only 的成员只是写规范的工具，程序不能使用，实现也不必提供。
    - 定制点对象（CPO）是无状态的函数对象，可以拷贝、传给高阶函数、作模板实参；实参不合要求时它没有可行的调用运算符，所以能被 `requires` 探测。
    - `std::ranges` 的算法是算法函数对象：ADL 找不到它们，非限定查找找到它们时也不再做 ADL。
    - 位掩码类型（如 `ios_base::iostate`）的底层类型未指明，只能使用标准给出的元素和运算符。
    - synopsis 里的 `// freestanding`、`// hosted`、`// freestanding-deleted` 注释是规范性的，决定独立实现必须提供什么。

## 仅用于说明的实体 [expos.only.entity]

### 带连字符的名字（¶1）

读库条文时常会看到这样的写法：`std::thread` 的构造函数把参数 *decay-copy* 一份，`pair` 的 `operator<=>` 用 *synth-three-way* 比较元素。这些名字在任何头文件里都找不到。

¶1 第 17–33 章和附录 D 声明的一些实体[[g:exposition-only|仅用于说明]]（exposition only），它们的声明后面跟着以 *exposition only* 结尾的注释。这类实体是写规范的工具：标准要用代码精确描述语义，就需要一些辅助函数、辅助概念和辅助成员。程序不能使用它们，实现也不必提供同名的东西。

为了不和真实的名字冲突，标准用斜体加连字符来写它们。连字符保证它们不可能是合法的 C++ 标识符。实现里通常有对应物，但用的是保留标识符（[[lex.name]]），例如 libc++ 的 `__boolean_testable`，依赖这些名字的代码不可移植。

### 四个通用的说明性实体（¶2）

¶2 下面四个实体在整个库规范中通用：

```cpp
namespace std {
  template<class T>
    requires convertible_to<T, decay_t<T>>
      constexpr decay_t<T> decay-copy(T&& v)          // exposition only
        noexcept(is_nothrow_convertible_v<T, decay_t<T>>)
      { return std::forward<T>(v); }

  constexpr auto synth-three-way = /* ... */;         // exposition only
  template<class T, class U = T>
  using synth-three-way-result = /* ... */;           // exposition only
  template<class T>
    concept constexpr-wrapper-like = /* ... */;       // exposition only
}
```

| 实体 | 作用 | 用在哪里 |
|---|---|---|
| [[g:decay-copy\|*decay-copy*]](v) | 按值得到一个退化后的副本：数组变指针，去掉引用和 cv 限定 | `std::thread`、`std::async` 复制参数，范围访问 CPO 的返回值 |
| *synth-three-way* | 合成三路比较：`T`、`U` 支持 `<=>` 就用它，否则用两次 `<` 合成一个 `weak_ordering` | `pair`、`tuple`、`optional`、容器的 `operator<=>` |
| *synth-three-way-result* | 上一项的结果类型 | 同上 |
| *constexpr-wrapper-like* | 像 `integral_constant` 的类型：能转换为 `T::value`，值在编译期可得 | `std::span` 的推导指引、`std::simd` |

*decay-copy* 在 C++23 之后大多可以写成 `auto(x)`（[[expr.type.conv]]）。两者有细微差别：*decay-copy* 带 `convertible_to` 约束，并且通过 `return` 语句做拷贝初始化，所以 `explicit` 拷贝构造函数会让它不可用；`auto(x)` 是直接初始化。

C++20 把 `pair`、`tuple` 等的六个比较运算符换成了一个 `operator<=>`，可是用户的旧类型可能只定义了 `<`。*synth-three-way* 的回退分支让这些类型仍能比较，只是结果类别是 `weak_ordering`：

```cpp run ok
#include <compare>
#include <type_traits>
#include <utility>
struct Old {   // 只有 <
  int v;
  bool operator<(const Old& o) const { return v < o.v; }
};
int main() {
  std::pair<Old, int> a{{1}, 2}, b{{2}, 0};
  auto r = a <=> b;              // 用 < 合成
  static_assert(std::is_same_v<decltype(r), std::weak_ordering>);
  return r < 0 ? 0 : 1;
}
```

¶3 如果对象 `dst` 的类型是 `decay_t<decltype((src))>`，就说 `dst` 是从子表达式 `src` 退化复制（decay-copied from）而来的。`decltype((src))` 的双括号给出 `src` 作为表达式的类型（左值得到左值引用），再去 `decay`。这个说法主要用在 `std::execution` 的规范里，描述发送器保存实参副本的方式。

## 定制点对象与算法函数对象

### 为什么要有定制点对象

库经常需要调用一个用户可以定制的操作，比如交换两个对象。C++17 及以前的惯用法分两步：

```cpp
using std::swap;
swap(a, b);   // 非限定调用：ADL 找到用户的 swap，找不到就用 std::swap
```

写成 `std::swap(a, b)` 就绕过了用户的定制；只写 `swap(a, b)` 而忘了 `using`，对 `int` 这样的基础类型又不起作用；而且库无法在这个调用点强制任何约束。C++20 的 Ranges（[[P0896R4]]）把这两步封装进一个函数对象：`std::ranges::swap(a, b)` 内部按规定顺序尝试 ADL 找到的 `swap`、移动交换等，用户只需写一个限定调用。

### 定制点对象的性质 [customization.point.object]

¶1 [[g:customization-point-object|定制点对象]]（customization point object，CPO）是字面类类型的函数对象，它与程序定义的类型交互，同时对这种交互施加语义要求。

¶2 CPO 的类型（忽略 cv 限定）必须建模 `semiregular`，必须是结构类型（[[temp.param]]）和可平凡复制类型（[[class.prop]]），所有构造函数都不抛异常。

¶3 同一个 CPO 类型的所有实例都相等，用相同的实参调用它们效果相同。¶5 进一步规定，`auto p = o;` 之后，`p(args...)`、`as_const(p)(args...)`、`std::move(p)(args...)`、`std::move(as_const(p))(args...)` 都与 `o(args...)` 等价。

这些要求让 CPO 成了一个无状态的函数名：可以随意拷贝、保存、作为常量模板实参，行为不变。

```cpp run ok
#include <algorithm>
#include <functional>
#include <ranges>
#include <vector>
template<auto F> struct holder {};
holder<std::ranges::begin> h;          // 结构类型：可作模板实参
int main() {
  std::vector<int> v{3, 1, 2};
  std::invoke(std::ranges::sort, v);   // 可以传给高阶函数
  auto first = std::ranges::begin;     // 拷贝一份，行为不变
  return *first(v) == 1 ? 0 : 1;
}
```

函数模板 `std::sort` 做不到这些：它是一个重载集，不是对象，`std::invoke(std::sort, ...)` 无法推导模板实参，是非良构的；它也不能作模板实参。

¶4 设 CPO 的类型为 `T`。实参类型 `Args...` 满足这个 CPO 的要求时，`T` 必须对 `T&`、`const T&`、`T`、`const T` 四种形式都建模 `invocable<..., Args...>`。实参不满足要求时，`T` 不能有参与重载决议的函数调用运算符。

后一半保证了 CPO 可以被探测。`std::ranges::begin(42)` 不会在 CPO 内部某处产生硬错误，`std::invocable<decltype(std::ranges::begin), int>` 只是为 `false`。`std::ranges::range` 概念正是用 `ranges::begin(t)` 定义的，靠的就是这一点。

!!! impl "libc++ 怎样定义 CPO"
    ```cpp
    namespace ranges {
    namespace __begin { struct __fn { /* 若干受约束的 operator() */ }; }
    inline namespace __cpo {
      inline constexpr auto begin = __begin::__fn{};
    }
    }
    ```
    多套一层内联命名空间是为了避免名字冲突。`std::ranges` 里一些迭代器把 `iter_move`、`iter_swap` 声明为隐藏友元，友元函数属于 `std::ranges`，会和同一命名空间里同名的变量冲突。变量放进 `__cpo` 之后两者不再冲突，用户写 `std::ranges::iter_move` 仍能通过内联命名空间找到它。CPO 的设计思路最早见于 Eric Niebler 的 [[N4381]]。

### 算法函数对象 [alg.func.obj]

¶1 [[g:algorithm-function-object|算法函数对象]]（algorithm function object）是规范中写成一个或多个重载函数模板的 CPO，这些函数模板的名字指称这个对象。标准在 [alg.find] 里用函数模板的形式写出 `ranges::find` 的几个签名，因为这样最清楚；实际提供的是一个对象。

¶2 设 `S` 是对应的函数模板集合，那么对任意实参，`o(args...)` 与对重载集 `S` 的调用表达式等价（[[defns.expression.equivalent]]）。

注 1 指出两个后果：算法函数对象不会被 ADL 找到，因为 ADL 只找函数（[[basic.lookup.argdep]]）；非限定查找找到它并用于函数调用时，查到的是对象而不是函数，于是不再做 ADL。

```cpp run ok
#include <algorithm>
#include <ranges>
#include <vector>
int main() {
  using namespace std::ranges;
  std::vector<int> vec{1, 2, 3};
  auto it = find(begin(vec), end(vec), 2);  // 调用 std::ranges::find，
                                            // 不会经 ADL 找到 std::find
  return *it == 2 ? 0 : 1;
}
```

`vec` 的迭代器的关联命名空间是 `std`。如果 `ranges::find` 是普通函数模板，ADL 会把无约束的 `std::find` 拉进候选集，它对一对迭代器可能是更好的匹配。算法函数对象让这种意外选择不可能发生。

!!! lawyer "同时 using 两个命名空间"
    写了 `using namespace std;` 和 `using namespace std::ranges;` 之后再调用 `find(v.begin(), v.end(), x)`，非限定查找同时找到函数模板 `std::find` 和变量 `std::ranges::find`。查找结果里既有函数又有变量，调用是歧义的（[[basic.lookup]]），本机 Clang 报 reference to 'find' is ambiguous。

!!! history "从 niebloid 到 CPO"
    C++20 只规定了 `std::ranges` 里的算法不被 ADL 找到、被非限定查找找到时抑制 ADL、不能显式指定模板实参，没有要求它们是对象。所有实现都把它们写成了函数对象，社区称之为 niebloid（得名于 Eric Niebler）。C++26 的 [[P3136R1]] 把它们正式规定为 CPO，于是它们也可以拷贝、传给高阶函数、作模板实参。

## 枚举类型与位掩码类型 [type.descriptions]

### 枚举类型（[enumerated.types]）

¶1 [[input.output]] 和 [[re]] 中的一些类型是[[g:enumerated-type|枚举类型]]（enumerated type），例如 `std::ios_base::seekdir`。每个枚举类型可以实现为一个枚举，也可以是某个枚举的同义词。

¶2–¶3 标准用一个说明性的写法刻画它：`enum enumerated { V0, V1, ... };` 再加一组常量 `C0`、`C1` 等，称为枚举元素（enumerated element），各元素的值互不相同。可移植代码只能依赖元素存在且互不相同，不能依赖具体数值，也不能假定它是 `enum class`。

### 位掩码类型（[bitmask.types]）

¶1 库中的一些类型是[[g:bitmask-type|位掩码类型]]（bitmask type），例如 `ios_base::iostate`、`ios_base::openmode`、`regex_constants::syntax_option_type`、`launch`、`filesystem::perms`。每个位掩码类型可以实现为重载了某些运算符的枚举、整数类型或 `bitset`。

¶2 标准用一个说明性的枚举加一组运算符刻画它的接口：`&`、`|`、`^`、`~`，以及 `&=`、`|=`、`^=`。

¶3 位掩码元素 `C0`、`C1` 等的值互不相同且非零，各占不同的位：`Ci & Ci` 非零，`i ≠ j` 时 `Ci & Cj` 为零。值 0 表示空位掩码，没有任何元素被设置。

¶4 三个术语有精确定义：在对象 X 中**设置**（set）值 Y，就是求值 `X |= Y`；**清除**（clear）Y，就是求值 `X &= ~Y`；Y 在 X 中**被设置**（is set），指 `X & Y` 非零。

```cpp run ok
#include <ios>
#include <sstream>
int main() {
  std::istringstream in("abc");
  int x;
  in >> x;                                    // 提取失败，设置 failbit
  std::ios_base::iostate st = in.rdstate();
  bool failed = (st & std::ios_base::failbit) != 0;   // is set
  st &= ~std::ios_base::failbit;                      // clear
  return failed && st == std::ios_base::goodbit ? 0 : 1;
}
```

!!! pitfall "依赖位掩码的底层类型"
    本机 libc++ 中 `fmtflags`、`iostate`、`openmode` 都是 `unsigned int` 的别名，所以 `std::ios_base::openmode m = 0x10;`、`int i = std::ios_base::in;` 都能编译。在用强类型枚举实现它们的标准库上就不一定了。`std::launch` 则被规定为 `enum class launch : unspecified`（[[future.syn]]），它的 `|` 结果仍是 `launch`，不能隐式转成整数。

## 字符串术语 [character.seq]

库规范经常说一个函数返回 ntbs，或者要求实参指向 ntbs。这些术语定义在这里：

- **字符序列**（character sequence）：元素类型为 `char`、`unsigned char` 或 `signed char`（可带 cv）的数组，开头若干元素有确定内容，直到某个谓词决定的元素为止，可以用指向首元素的指针表示（[character.seq.general] ¶1.5）。
- [[g:ntbs|**ntbs**]]（null-terminated byte string，以零结尾的字节串）：最高地址的有确定内容的元素是零（终止空字符），其余元素都不是零的字符序列。它的长度是终止空字符之前的元素个数；静态 ntbs 是具有静态存储期的 ntbs，字符串字面量就是静态 ntbs（[byte.strings]）。
- [[g:ntmbs|**ntmbs**]]（以零结尾的多字节串）：由有效的多字节字符组成、在初始移位状态开始和结束的 ntbs。只含基本字面量字符集字符的 ntbs 也是 ntmbs（[multibyte.strings]）。

这些术语在全库中被引用。`std::exception::what()` 返回实现定义的 ntbs；反射的 `std::meta::identifier_of` 和契约的 `contract_violation::comment()` 返回 ntmbs。`std::string(const char* s)` 的 *Effects* 等价于 `basic_string(s, traits::length(s), a)`，按 [[structure.specifications#4]]，`traits::length(s)` 的前置条件传递过来，实际上就是要求 `s` 指向一个 ntbs。

[character.seq.general] ¶1 还规定了几条与 locale 有关的约定。执行字符集的编码由 locale 决定，可以与源代码中字面量的编码无关（注 1）。小数点字符也随 locale 变化，所以 `std::strtod("1,5", ...)` 在德语 locale 下可能解析为 1.5；`std::from_chars` 不受 locale 影响（[[charconv]]）。

## 没有写出的成员

¶1（[functions.within.classes]）为了简洁，库条款不写出与默认生成的版本语义相同的拷贝和移动构造函数、赋值运算符和非虚析构函数。实现是否为它们提供显式定义是未指明的。

所以 synopsis 里没写拷贝构造函数，不等于类没有拷贝构造函数。也因为是否显式定义未指明，这些成员是否平凡没有保证，这与 [[library.class.props]] 一致：除非另有说明，库类是否可平凡复制是未指明的。

¶1–¶3（[objects.within.classes]）库条款不规定类的表示，实现可以按需添加任何静态或非静态成员。有些子条款为了说明语义，给出代表性的私有成员声明，后面同样注释 exposition only，例如 `streambuf* sb;      // exposition only`。实现可以用任何可观察行为相同的技术。

说明性私有成员不能被程序访问，也不保证存在，`sizeof(std::optional<int>)` 不必等于 `sizeof(bool) + sizeof(int)` 加填充。少数类有规范性的非私有数据成员，它们不是 exposition only，例如 `std::pair` 的 `first`、`second`，`std::reverse_iterator` 的 `protected` 成员 `current`，派生类可以依赖它们。

## 独立项 [freestanding.item]

**独立实现**（freestanding implementation）是可以在没有操作系统的环境下运行的实现，只需提供标准库的一个子集（[[intro.compliance]]、[[compliance]]）。C++23 起（[[P1642R11]] 等提案），这个子集不再按整个头文件划分，而是在 synopsis 中逐条标注。

### 什么是独立项（¶1–¶2、¶4–¶6）

¶1 [[g:freestanding-item|**独立项**]]（freestanding item）是独立实现和宿主实现都必须提供的声明、实体或宏。¶2 除非另有说明，独立实现对独立项的要求与宿主实现相同，只是这些项的成员不必全部提供。

¶4 synopsis 中的一个声明在以下情况下是独立项：后面的注释含 *freestanding*（¶4.1）或 *freestanding-deleted*（¶4.2）；或者头文件 synopsis 以含 *freestanding* 的注释开头，而这个声明后面没有含 *hosted* 的注释（¶4.3）。注 2 提醒，这意味着同一个名字的查找结果在宿主实现和独立实现上可能不同。

¶5 独立项的属性会传递：由独立项声明引入的实体、独立项的成员、枚举符、推导指引、友元、外围命名空间，以及由独立项别名指称的实体，只要它们的引入声明没有标 *hosted*，也都是独立项。所以 `std::array` 是独立项，它的成员和推导指引默认也是。¶6 对宏有同样的规则，例如 `#define NULL see below      // freestanding`。

### freestanding-deleted（¶3）

¶3 声明后注释含 *freestanding-deleted* 的函数是[[g:freestanding-deleted-function|独立删除函数]]（freestanding deleted function）。在独立实现中，它们是删除函数（[[dcl.fct.def.delete]]）还是与宿主实现的要求相同，由实现定义。

注 1 说明了为什么要删除而不是省略：删除的定义能防止程序从独立实现迁移到宿主实现时，重载决议的结果悄悄改变。

<div class="compare" markdown="1">

```cpp error
int    mag(int);
double mag(double) = delete;
double d = -2.5;
auto r = mag(d);   // error: 选中删除函数
```

```cpp ok
int mag(int);
// mag(double) 被省略
double d = -2.5;
auto r = mag(d);   // 悄悄转换成 int
```

</div>

右边省略了 `double` 版本，调用悄悄选中 `mag(int)`，得到 -2；换到提供了 `mag(double)` 的宿主实现上，同一段代码得到 -2.5。左边把它声明为删除的，它仍然参与重载决议并被选中，于是在独立实现上编译失败，问题当场暴露。

标准的例 1 是 `double abs(double j);  // freestanding-deleted`。例 4 是 `std::array`：`operator[]` 是独立的，会抛 `out_of_range` 的 `at()` 标为 *freestanding-deleted*，因为独立实现可能不支持异常，又不能让 `at` 悄悄消失。

```cpp
template<class T, size_t N> struct array;               // partially freestanding
template<class T, size_t N>
struct array {
  constexpr reference       operator[](size_type n);
  constexpr const_reference operator[](size_type n) const;
  constexpr reference       at(size_type n);            // freestanding-deleted
  constexpr const_reference at(size_type n) const;      // freestanding-deleted
};
```

¶7 注 3 说明了几种不带额外规范要求的书写惯例：头文件开头的 `// all freestanding` 表示其中没有 hosted 项和 freestanding-deleted 函数；`// mostly freestanding` 表示至少有一个；类后面的 `// partially freestanding` 表示这个类至少有一个 hosted 成员或 freestanding-deleted 函数。部分独立的类这一机制来自 [[P2407R5]]。

## 常见误解

!!! pitfall "试图使用 exposition only 的名字"
    在标准或 cppreference 上看到 *decay-copy*、*boolean-testable*，以为可以写 `std::decay_copy(x)`。这些名字不存在，需要时用 `auto(x)`、`std::convertible_to` 等公开设施，或者自己写。

!!! pitfall "把 CPO 当成普通函数"
    CPO 是对象，所以 ADL 找不到它，也不能为它添加重载（在 `std::ranges` 里添加声明本来就是 UB，见 [[namespace.std]]）。定制它要走它规定的途径：成员 `begin()`、ADL 能找到的非成员 `begin`、`enable_borrowed_range` 等，而不是特化它。

## 思考题

!!! question "思考题 1"
    标准为什么要求 CPO 的类型是结构类型、可平凡复制，而且所有实例相等？如果某个实现让 `std::ranges::begin` 带一个 `int` 状态成员，会破坏什么？

<details markdown="1">
<summary>答案</summary>

结构类型（[[temp.param]]）让 CPO 可以作常量模板实参，如 `holder<std::ranges::begin>`。可平凡复制保证拷贝没有副作用。所有实例相等且效果相同（¶3），加上 ¶5 要求 `auto p = o;` 之后 `p(args...)` 与 `o(args...)` 等价，保证了 CPO 是无状态的名字。

如果带状态成员，不同实例的行为可能不同，`holder<o1>` 和 `holder<o2>` 也可能成为不同的类型。这违反了 ¶2–¶3，这样的实现不符合标准。
</details>

!!! question "思考题 2"
    某个独立实现提供了 `<cmath>`，把 `double abs(double)` 实现为删除函数。下面的代码在这个实现上是什么结果？

    ```cpp
    #include <cmath>
    int f() { return std::abs(-2.5) > 2 ? 1 : 0; }
    ```

<details markdown="1">
<summary>答案</summary>

重载决议中 `abs(double)` 是精确匹配，被选中；它是删除函数，所以程序非良构（[[dcl.fct.def.delete]]），编译器必须报错。这正是 ¶3 注 1 的目的：如果 `abs(double)` 干脆不存在，调用会落到剩下的整数版本上，要么悄悄截断，要么因为几个整数版本同样好而歧义，前一种情况下程序在两种实现上得到不同的结果。
</details>

<details class="fine" markdown="1"><summary>其余条文</summary>

[conventions.general] ¶1：本节描述库规范中用来描述实现定义的类型和成员函数的几条编辑约定。

[type.descriptions.general] ¶1：Requirements 子条款可以定义一些名字，用来规定模板实参的约束，脚注列举了 *Cpp17EqualityComparable*、*Cpp17CopyConstructible*、*Cpp17InputIterator* 等。库条款用这些名字描述程序实例化库模板时可以提供的类型。例如 [[algorithms.requirements]] 规定，名为 `ForwardIterator` 的模板形参对应的实参必须满足 *Cpp17ForwardIterator*。这种要求只是文字约定，不是 `template<forward_iterator I>` 那样的真正约束，违反时是 UB（[[res.on.functions#2.3]]）。¶2：[[input.output]] 中的一些类型用来描述实现定义的类型，它们基于其他类型，但附加了约束。

[character.seq.general] ¶1 的其余各项：locale-specific 的属性可以在执行中通过 `setlocale` 或改变 locale 对象而改变（¶1.1）；执行字符集和执行宽字符集是基本字面量字符集（[[lex.charset]]）的超集，执行宽字符集的每个元素用一个 `wchar_t` 码元表示（¶1.2）；字母指基本字符集中的 52 个大小写拉丁字母（¶1.3）；*STATICALLY-WIDEN*<charT>("...") 在 `charT` 为 `char` 时是 `"..."`，为 `wchar_t` 时是 `L"..."`，`<format>` 和 `<chrono>` 的规范用它写同一字符串的窄、宽两个版本（¶1.6）。

[byte.strings] ¶2–¶3：ntbs 的长度是终止空字符之前的元素个数，空 ntbs 长度为零；ntbs 的值是直到并包括终止空字符的元素值序列。[multibyte.strings] ¶1：多字节字符是表示执行字符集中某个字符的一个或多个字节；¶3：静态 ntmbs 是具有静态存储期的 ntmbs。

</details>
