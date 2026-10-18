---
title: 其他编辑约定
summary: 库条文的"图例"第二部分：仅用于说明（exposition only）的实体与 decay-copy；命名要求、枚举类型与位掩码类型；ntbs / ntmbs 等字符序列术语；定制点对象（CPO）与算法函数对象（niebloid）的精确性质；未写出的特殊成员、私有成员；freestanding / hosted / freestanding-deleted 标注的规范含义。
status: done
covers: *
papers: P0896R4, P3136R1, P1642R11, P2407R5
related: description, structure.specifications, requirements, compliance, basic.lookup.argdep, temp.param, class.prop, intro.compliance
tags: 库, 阅读方法, CPO, niebloid, exposition only, freestanding
updated: 2026-10-18
---

[[description]] 讲了库条款的骨架和函数规范的各个要素；本节 [conventions] 补充其余的编辑约定。它们看似琐碎，却决定了很多"能不能这样写"的问题：能不能调用标准里那个叫 *decay-copy* 的函数？`std::ios_base::fmtflags` 能不能当 `int` 用？`std::ranges::find` 能不能被 ADL 找到、能不能当实参传递？`std::array::at` 在独立实现上存在吗？

¶1（[conventions.general]）说本节描述的约定用于描述实现定义的类型与成员函数。下面按子条款逐一展开。

## 仅用于说明的实体（[expos.only.entity]）

### "exposition only" 是什么（¶1）

¶1 第 17 章到第 33 章以及附录 D 中声明的若干实体[[g:exposition-only|**仅用于说明**]]（provided for exposition only）。这种实体的声明后面跟着一个以 *exposition only* 结尾的注释。

仅用于说明的实体**不是库提供给程序的东西**：程序不能命名它，实现也不必提供同名实体。它们只是规范写作的工具——为了用代码精确描述语义，标准需要一些辅助函数、辅助概念、辅助成员。为了不与真实名字冲突，标准刻意用**斜体加连字符**的写法（*decay-copy*、*synth-three-way*、*boolean-testable*）——连字符使它们**不可能**是合法的 C++ 标识符。

实现中通常会有对应物，但名字是保留标识符（[[lex.name]]）：例如 libc++ 的 `__boolean_testable`。依赖这些内部名字的代码不可移植。

### 四个全局通用的说明性实体（¶2）

¶2 下列实体仅用于说明，用来辅助库的规范：

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
| [[g:decay-copy|*decay-copy*]](v) | 按值拷贝/移动出一个"退化"后的副本（数组 → 指针、去掉引用和 cv） | `std::thread`、`std::async` 的参数复制，范围访问 CPO 的返回值等 |
| *synth-three-way* | 合成三路比较：若 `T`、`U` 支持 `<=>` 就用它，否则用两次 `<` 合成一个 `weak_ordering` | `pair`、`tuple`、`optional`、容器的 `operator<=>`——使它们对只有 `<` 的老类型也能工作 |
| *synth-three-way-result* | 上面那个的结果类型 | 同上 |
| *constexpr-wrapper-like* | "像 `integral_constant` / `constant_wrapper` 的类型"：可转换为 `T::value`、且其值在编译期可得 | `std::span` 由编译期常量推导静态 extent、`std::simd` 的广播构造等 |

*decay-copy* 在 C++23 之后大部分可以写成 `auto(x)`（[[expr.type.conv]]），但二者有细微差别：*decay-copy* 有 `requires convertible_to<T, decay_t<T>>` 约束，并使用**拷贝初始化**（`return` 语句），因此 `explicit` 拷贝构造函数会使其不可用；`auto(x)` 是直接初始化。

*synth-three-way* 的意义值得多说一句。C++20 把 `pair`、`tuple` 等的六个比较运算符替换为一个 `operator<=>`；但用户的老类型可能只定义了 `<`。*synth-three-way* 的回退分支让 `std::pair<OldType, int>` 依然可以比较大小，只是结果是 `weak_ordering`：

```cpp run ok
#include <compare>
#include <type_traits>
#include <utility>
struct Old { int v; bool operator<(const Old& o) const { return v < o.v; } };  // 只有 <
int main() {
  std::pair<Old, int> a{{1}, 2}, b{{2}, 0};
  auto r = a <=> b;                       // 通过 synth-three-way 用 < 合成
  static_assert(std::is_same_v<decltype(r), std::weak_ordering>);
  return r < 0 ? 0 : 1;
}
```

### "从 src 退化复制"（¶3）

¶3 若对象 `dst` 的类型是 `decay_t<decltype((src))>`，就说 `dst` 是从子表达式 `src` **退化复制**而来（*decay-copied from*）的。这是给"存储参数副本"类的规范用的说法——例如 `std::bind_front` 存储的就是从实参退化复制来的对象。注意 `decltype((src))` 的双括号：它给出 `src` 作为表达式的类型（含值类别对应的引用），然后再 `decay`。

## 类型描述（[type.descriptions]）

### 命名要求（[type.descriptions.general]）

¶1 "Requirements" 子条款可以描述一些名字，用来规定模板实参的约束（脚注列举：[[utility.requirements]] 中的 *Cpp17EqualityComparable*、*Cpp17LessThanComparable*、*Cpp17CopyConstructible*；[iterator.requirements] 中的 *Cpp17InputIterator*、*Cpp17ForwardIterator*）。库条款用这些名字描述程序在实例化库模板时可以提供的类型。

¶2 [[input.output]] 中出现的某些类型用来描述**实现定义**的类型，它们基于其他类型，但附加了约束。

所以当标准在模板形参处写 `template<class ForwardIterator>` 时，这个**形参名本身**就带着要求：[[algorithms.requirements]] 规定，名为 `ForwardIterator` 的模板形参对应的实参必须满足 *Cpp17ForwardIterator*。这是一种"以名字传达要求"的约定，与 C++20 风格的 `template<forward_iterator I>` 不同——后者是真的约束，前者只是文字要求（违反时是 UB，见 [[res.on.functions#2.3]]）。

### 枚举类型（[enumerated.types]）

¶1 [[input.output]] 与 [re] 中的若干类型是[[g:enumerated-type|**枚举类型**]]（enumerated types）。每个枚举类型可以实现为一个枚举，或某个枚举的同义词（脚注：例如一个整数类型，带有常量整数值）。

¶2–¶3 枚举类型 *enumerated* 可以写成：

```cpp
enum enumerated { V0, V1, V2, V3, … };
inline const enumerated C0(V0);
inline const enumerated C1(V1);
  ⋮
```

名字 `C0`、`C1` 等是该枚举类型的**枚举元素**（enumerated elements），各元素的值互不相同。

例子：`std::ios_base::seekdir`（元素 `beg`、`cur`、`end`）。本机 libc++ 的 `<ios>` 中就是一个普通枚举 `enum seekdir { beg, cur, end };`。可移植代码只能依赖"元素存在且互不相同"，不能依赖具体数值，也不能假定它是 `enum class`。

### 位掩码类型（[bitmask.types]）

¶1 第 17 章到第 33 章及附录 D 中的若干类型是[[g:bitmask-type|**位掩码类型**]]（bitmask types）。每个位掩码类型可以实现为重载了某些运算符的枚举类型、整数类型，或者 `bitset`。

¶2 标准用一个说明性的枚举 + 一组运算符重载来刻画它的接口：`&`、`|`、`^`、`~`（`constexpr`），以及 `&=`、`|=`、`^=`。

¶3 名字 `C0`、`C1` 等表示**位掩码元素**（bitmask elements）：值互不相同且非零，对任意 i ≠ j，`Ci & Ci` 非零而 `Ci & Cj` 为零（即各占不同的位）。值 0 表示**空位掩码**（empty bitmask），没有任何元素被设置。

¶4 术语：

- **¶4.1 设置**（set）对象 X 中的值 Y：求值 `X |= Y`；
- **¶4.2 清除**（clear）对象 X 中的值 Y：求值 `X &= ~Y`；
- **¶4.3** 值 Y 在对象 X 中**被设置**（is set）：表达式 `X & Y` 非零。

标准中的位掩码类型包括 `ios_base::fmtflags`、`ios_base::iostate`、`ios_base::openmode`、`regex_constants::syntax_option_type`、`launch`、`filesystem::perms`、`filesystem::copy_options` 等。

```cpp run ok
#include <ios>
#include <sstream>
int main() {
  std::istringstream in("abc");
  int x;
  in >> x;                                          // 提取失败，设置 failbit
  std::ios_base::iostate st = in.rdstate();
  bool failed = (st & std::ios_base::failbit) != 0; // "is set"：X & Y 非零
  st &= ~std::ios_base::failbit;                    // "clear"：X &= ~Y
  return failed && st == std::ios_base::goodbit ? 0 : 1;
}
```

!!! pitfall "位掩码类型的可移植写法"
    只能使用 ¶2 列出的运算符和标准给出的元素。本机 libc++ 中 `fmtflags`、`iostate`、`openmode` 都是 `unsigned int` 的 typedef——所以 `std::ios_base::openmode m = 0x10;`、`int i = std::ios_base::in;`、`switch (state) { case ... }` 都能编译——但在把它实现为带强类型运算符的 `enum` 的实现上就不一定。另外 `std::launch` 在 [future.syn] 中被规定为 `enum class launch : unspecified`，它的 `|` 结果仍是 `launch`，不能隐式转成整数。

### 字符序列（[character.seq]）

#### 一般约定（[character.seq.general]）

¶1 C 标准库广泛使用遵循几条统一约定的字符和字符序列：

- **¶1.1 locale-specific**：标为"locale 相关"的属性可以在程序执行中通过 `setlocale` 或改变 locale 对象而改变。
- **¶1.2 执行字符集**与**执行宽字符集**：都是基本字面量字符集（[[lex.charset]]）的超集；它们的编码和额外元素的集合是 locale 相关的；执行宽字符集的每个元素编码为单个 `wchar_t` 码元。Note 1 特别指出：执行字符集的编码可以与任何**字面量编码**无关——即源代码里 `"é"` 被编译成的字节，不一定是运行时 locale 所理解的编码。
- **¶1.3 字母**（letter）：基本字符集中 26 个小写和 26 个大写字母之一。
- **¶1.4 小数点字符**（decimal-point character）：在单字节字符序列与浮点值之间转换的函数使用的 locale 相关的单字节字符，标示小数部分的开始；在规范中写作 `'.'`，这也是它在 `"C"` locale 中的值。所以 `std::strtod("1,5", ...)` 在德语 locale 下可能解析为 1.5——而 `std::from_chars` 不受 locale 影响（[charconv]）。
- **¶1.5 字符序列**（character sequence）：可以声明为 `T A[N]` 的数组对象 `A`，`T` 是 `char`、`unsigned char` 或 `signed char`（可带 cv 限定）；数组开头的若干元素有确定内容，直到由某个谓词决定的元素为止（含）。字符序列可以用指向首元素的指针值 `S` 来指明。
- **¶1.6** *STATICALLY-WIDEN*<charT>("...")：`charT` 为 `char` 时是 `"..."`，为 `wchar_t` 时是 `L"..."`。这是 `<format>`、`<chrono>` 规范中用来写"同一个字符串字面量的窄/宽版本"的说明性记法。

#### 字节串（[byte.strings]）

- ¶1 [[g:ntbs|**以零结尾的字节串**]]（null-terminated byte string，**ntbs**）：一个字符序列，其最高地址的有确定内容的元素值为零（**终止空字符**），其他元素都不为零。
- ¶2 **ntbs 的长度**：终止空字符之前的元素个数；**空 ntbs** 长度为零。
- ¶3 **ntbs 的值**：直到并包括终止空字符为止的元素值序列。
- ¶4 **静态 ntbs**：具有静态存储期的 ntbs。脚注：字符串字面量（如 `"abc"`）就是静态 ntbs。

这些术语在整个库中被大量引用：例如 `std::exception::what()` 的 *Returns* 是"一个由实现定义的 ntbs"；`std::string(const char* s)` 的 *Effects* 是"Equivalent to: `basic_string(s, traits::length(s), a)`"，按 [[structure.specifications#4]] 传递过来的是 `traits::length(s)` 的前置条件——实际上就是要求 `s` 指向一个 ntbs。

#### 多字节串（[multibyte.strings]）

- ¶1 **多字节字符**（multibyte character）：一个或多个字节组成的序列，表示执行字符集中某个已编码字符的码元序列。
- ¶2 [[g:ntmbs|**以零结尾的多字节串**]]（**ntmbs**）：一个 ntbs，它构成有效多字节字符的序列，在初始移位状态开始和结束。脚注：只含基本字面量字符集字符的 ntbs 也是 ntmbs，每个多字节字符只有一个字节。
- ¶3 **静态 ntmbs**：具有静态存储期的 ntmbs。

[[namespace.std#7]] 中 `meta::identifier_of` 返回的就是一个 ntmbs。

### 定制点对象（[customization.point.object]）

定制点对象（customization point object，CPO）是 C++20 Ranges（[[P0896R4]]）带来的设计模式，用来解决一个老问题：库如何调用**用户可定制**的操作（`swap`、`begin`、`size`……）？

C++17 及以前的惯用法是"两步式"（two-step）：

```cpp
using std::swap;
swap(a, b);        // 非限定调用：ADL 找用户的 swap，找不到就用 std::swap
```

问题在于：写成 `std::swap(a, b)` 就绕过了用户定制；写成 `swap(a, b)` 而忘了 `using` 就对基础类型不工作；而且库无法在这个调用点**强制**任何约束（比如"用户的 `swap` 必须真的交换值"）。CPO 把这个两步式封装进一个**函数对象**：`std::ranges::swap(a, b)` 内部按规定顺序尝试 ADL 找到的 `swap`、成员、移动交换……用户只需写一个限定调用。

#### CPO 必须是什么样的（¶1–¶3）

¶1 **定制点对象**是一个具有字面类类型的函数对象（[function.objects]），它与程序定义的类型交互，同时对这种交互强制施加语义要求。

¶2 CPO 的类型（忽略 cv 限定）必须建模 `semiregular`，必须是**结构类型**（[[temp.param]]）和**可平凡复制类型**（[[class.prop]]）；该类型的每个构造函数都必须具有不抛出的异常规范。

¶3 某个 CPO 类型的所有实例必须相等（[concepts.equality]）；用同样实参调用同一 CPO 类型的不同实例，效果等价。

这些要求保证了 CPO 可以被随意**拷贝、存储、作为模板实参**，而行为不变——它本质上是一个无状态的"函数名"：

```cpp run ok
#include <algorithm>
#include <functional>
#include <ranges>
#include <vector>
template<auto F> struct holder { };
holder<std::ranges::begin> h;            // 结构类型：可以作为常量模板实参
int main() {
  std::vector<int> v{3, 1, 2};
  std::invoke(std::ranges::sort, v);     // 算法函数对象可以直接传给高阶函数
  auto first = std::ranges::begin;       // 拷贝一份 CPO，行为不变（¶5）
  return *first(v) == 1 ? 0 : 1;
}
```

对比函数模板 `std::sort`：它是一个**重载集**，不是对象，不能直接传给 `std::invoke`（`std::invoke(std::sort, ...)` 无法推导，非良构），也不能作为常量模板实参。

#### 调用约束（¶4–¶5）

¶4 设 CPO 的类型（忽略 cv）为 `T`。当 `Args...` 满足该 CPO 定义中规定的要求时，`T` 必须建模 `invocable<T&, Args...>`、`invocable<const T&, Args...>`、`invocable<T, Args...>`、`invocable<const T, Args...>`。当 `Args...` **不满足**要求时，`T` 必须**没有**参与重载决议的函数调用运算符。

后半句非常重要：CPO 是 **SFINAE 友好**的。`std::ranges::begin(42)` 不会在 CPO 内部某处产生硬错误，而是 `std::invocable<decltype(std::ranges::begin), int>` 为 `false`——这正是 `std::ranges::range` 概念能用 `ranges::begin(t)` 来定义的前提。

¶5 对 CPO `o`，令 `p` 是按 `auto p = o;` 初始化的变量。则对任意实参序列 `args...`，`p(args...)`、`as_const(p)(args...)`、`std::move(p)(args...)`、`std::move(as_const(p))(args...)` 的效果都等价于 `o(args...)`。

#### 实现视角

在 libc++ 中，`std::ranges::begin` 的定义是：

```cpp
namespace ranges {
namespace __begin { struct __fn { /* 若干受约束的 operator() */ }; }
inline namespace __cpo {
  inline constexpr auto begin = __begin::__fn{};
}
}
```

为什么多套一层 `inline namespace __cpo`？因为 `std::ranges` 里的许多类会声明与 CPO 同名的**隐藏友元**——例如 `join_view` 等视图的迭代器把 `iter_move`、`iter_swap` 声明为友元函数，而 `std::ranges::iter_move` 恰好也是一个 CPO。友元函数在语义上是最内层外围命名空间（这里是 `std::ranges`）的成员，与同一命名空间中同名的**变量**冲突，程序就非良构了。把变量放进内联命名空间后，它属于 `std::ranges::__cpo`，与隐藏友元不冲突，而用户写 `std::ranges::iter_move` 仍能通过内联命名空间找到它。这一技巧来自 Eric Niebler 的 [[N4381]]（"Suggested Design for Customization Points"）。

### 算法函数对象（[alg.func.obj]）

¶1 [[g:algorithm-function-object|**算法函数对象**]]（algorithm function object）是被规定为**一个或多个重载函数模板**的定制点对象。这些函数模板的名字指称相应的算法函数对象。

¶2 对算法函数对象 `o`，令 `S` 是相应的函数模板集合。对任意实参序列 `args...`，`o(args...)` 与 `s(args...)` **表达式等价**（[[defns.expression.equivalent]]），其中对 `s` 的名字查找结果是重载集 `S`。

也就是说：标准在 [alg.find] 中以函数模板的形式写出 `ranges::find` 的几个签名（这样写最清楚），但实际提供的是一个**对象**，调用它和调用"那组函数模板"效果完全一样。

Note 1 指出两个后果：

- 算法函数对象**不会被 ADL 找到**（ADL 只找函数和函数模板，[[basic.lookup.argdep]]）；
- 当它被非限定查找找到、作为函数调用的后缀表达式时，**抑制 ADL**——因为非限定查找找到的是一个对象而非函数，[basic.lookup.argdep] ¶1 规定此时不做 ADL。

```cpp run ok
#include <algorithm>
#include <ranges>
#include <vector>
int main() {
  using namespace std::ranges;
  std::vector<int> vec{1, 2, 3};
  auto it = find(begin(vec), end(vec), 2);  // #1：调用 std::ranges::find，
                                            // 而不是经由 ADL 找到的 std::find
  return *it == 2 ? 0 : 1;
}
```

`vec` 的迭代器类型的关联命名空间是 `std`，如果 `find` 是普通函数模板，ADL 会把 `std::find` 也拉进候选集——而 `std::find` 是无约束的模板，对迭代器对来说可能是更好的匹配，造成意外选择。算法函数对象使这种"劫持"不可能发生。

!!! history "从 niebloid 到 CPO"
    C++20 中 `std::ranges` 里的算法被规定为一类特殊的"实体"：标准只说它们"不被 ADL 找到"、"被非限定查找找到时抑制 ADL"，以及"不能为它们指定显式模板实参"，并未要求它们是对象——但所有实现都把它们实现为函数对象，社区称之为 **niebloid**（得名于 Eric Niebler）。C++26 通过 [[P3136R1]]（"Retiring niebloids"）把它们正式规定为定制点对象，于是它们获得了 CPO 的全部性质：可以拷贝、可以传递给高阶函数、可以作模板实参。

## 类中的函数（[functions.within.classes]）

¶1 为了便于说明，第 17–33 章和附录 D 不描述与默认生成的版本语义相同的拷贝/移动构造函数、赋值运算符或（非虚）析构函数。实现是否为这些成员函数签名，或为可以默认生成的虚析构函数提供显式定义，是**未指明**的。

后果：

- 读类的 synopsis 时，没写拷贝构造函数**不等于**没有拷贝构造函数——它有"像默认生成那样语义"的拷贝构造函数。
- 由于是否"显式定义"是未指明的，这些特殊成员是否**平凡**也就没有保证。这与 [[library.class.props]] 一致：库类是否可平凡复制是未指明的，除非另有说明。

## 私有成员（[objects.within.classes]）

¶1 第 17–33 章和附录 D 不规定类的表示，有意省略类成员的规范。实现可以按需定义静态或非静态类成员，以实现规定的成员函数语义。

¶2 为便于说明，有些子条款会给出私有成员的**代表性**声明和语义要求，这些声明后跟以 *exposition only* 结尾的注释，例如：

```cpp
streambuf* sb;      // exposition only
```

¶3 实现可以使用任何提供等价可观察行为的技术。

说明性私有成员不能被程序访问，也不保证存在——`sizeof(std::optional<int>)` 不必等于 `sizeof(bool) + sizeof(int)` 加填充。少数类有**规范性的**非私有数据成员，那就不是 exposition only：例如 `std::reverse_iterator` 的 `protected: Iterator current;`、`std::pair` 的 `first` / `second`。派生类可以依赖它们。

## 独立项（[freestanding.item]）

独立实现（freestanding implementation，[[intro.compliance]]）只需要提供库的一个子集（[[compliance]]）。C++23 起（[[P1642R11]] 等一系列提案），标准不再按"整个头文件"划分，而是在 synopsis 中**逐条标注**哪些声明属于独立子集。本小节规定这些标注的精确含义。

### 定义与默认规则（¶1–¶2）

¶1 [[g:freestanding-item|**独立项**]]（freestanding item）是在独立实现和宿主实现中都必须存在的声明、实体或宏。

¶2 除非另有说明，独立实现对独立项的要求与宿主实现相同，只是这些项的**成员**不一定全部提供。

### freestanding-deleted（¶3）

¶3 后跟包含 *freestanding-deleted* 的注释的函数声明和函数模板声明是[[g:freestanding-deleted-function|**独立删除函数**]]（freestanding deleted functions）。在独立实现中，由独立删除函数引入的每个实体，是**删除函数**（[[dcl.fct.def.delete]]）还是与宿主实现相同的要求，由实现定义。

Note 1 解释了为什么要"删除"而不是"省略"：删除的定义降低了从独立实现迁移到宿主实现时**重载决议静默改变**的可能。例如：

```cpp
double abs(double j);           // freestanding-deleted
```

设想独立实现干脆不声明 `std::abs(double)`，只有 `std::abs(int)`。那么 `std::abs(-2.5)` 会悄悄选中 `abs(int)`，结果是 2；挪到宿主实现上，同样的代码得到 2.5。若把 `abs(double)` 声明为删除的，它仍参与重载决议并被选中，于是在独立实现上**编译失败**，而不是悄悄改变语义。

### 哪些声明是独立项（¶4–¶6）

¶4 synopsis 中的声明在以下情况下是独立项：

- **¶4.1** 后跟包含 *freestanding* 的注释；
- **¶4.2** 后跟包含 *freestanding-deleted* 的注释；
- **¶4.3** 头文件 synopsis 以包含 *freestanding* 的注释开头，且该声明后没有包含 *hosted* 的注释。

Note 2：独立头文件中后跟 *hosted* 的声明不是独立项。因此对这类函数的名字查找结果，在宿主实现与独立实现之间可能不同。

¶5 实体或推导指引是独立项，如果其引入声明后没有包含 *hosted* 的注释，并且它是：由独立项声明引入的（5.1）；独立项（命名空间除外）的成员（5.2）；独立项的枚举符（5.3）；独立项的推导指引（5.4）；独立项的外围命名空间（5.5）；独立项的友元（5.6）；由作为独立项的类型别名（5.7）或别名模板（5.8）指称的。

这几条让标注可以"继承"：类模板 `std::array` 是独立项，那么它的成员、它的推导指引、它的友元默认也都是，除非单独标了 *hosted*。

¶6 宏是独立项，如果它在头文件 synopsis 中定义，并且（6.1）定义后跟包含 *freestanding* 的注释，或（6.2）头文件 synopsis 以包含 *freestanding* 的注释开头且定义后没有包含 *hosted* 的注释。例如 `#define NULL see below      // freestanding`。

### 非规范性的书写惯例（¶7）

¶7 Note 3 说明了几种不施加额外规范要求的标注惯例：

| 注释 | 含义 |
|---|---|
| `// all freestanding`（头文件开头） | 该头文件不含 hosted 项，也不含 freestanding-deleted 函数 |
| `// mostly freestanding`（头文件开头） | 至少含一个 hosted 项或 freestanding-deleted 函数 |
| `// partially freestanding`（类或类模板后） | 该类至少含一个 hosted 项或 freestanding-deleted 函数 |

Example 4 正是 `std::array`：`operator[]` 是独立的，而会抛 `out_of_range` 的 `at()` 是 *freestanding-deleted*——独立实现可能不支持异常，但又不能让 `at` 静默消失。"部分独立的类"这一机制来自 [[P2407R5]]。

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

## 常见误区

!!! pitfall "试图使用 exposition-only 名字"
    在 cppreference 或标准中看到 *decay-copy*、*boolean-testable*、*can-reference*，以为可以 `std::decay_copy(x)`——不存在。需要时自己写，或用 `auto(x)`、`std::convertible_to` 等公开设施。

!!! pitfall "以为 CPO 只是“函数的另一种写法”"
    CPO 是对象，因此：不能对它做 ADL；不能用它重载（你不能在 `std::ranges` 中给 `begin` 加一个重载——那本来就是 UB，见 [[namespace.std]]）；定制它要通过它规定的途径（成员 `begin()`、ADL 可找到的非成员 `begin`、`enable_borrowed_range` 等），而不是特化它。

!!! lawyer "using namespace std 与算法函数对象"
    同时 `using namespace std;` 和 `using namespace std::ranges;` 后写 `find(v.begin(), v.end(), x)`：非限定查找同时找到函数模板 `std::find` 和变量 `std::ranges::find`。查找结果中既有函数又有非函数的变量，按 [[basic.lookup]] 的规则是歧义的——非良构（本机 Clang：`reference to 'find' is ambiguous`）。

## 思考题

!!! question "思考题 1"
    标准为什么要求 CPO 的类型是"结构类型"和"可平凡复制类型"，且所有实例相等？如果某个实现让 `std::ranges::begin` 带有一个 `int` 状态成员，会破坏什么？

<details markdown="1">
<summary>展开查看答案与解析</summary>

结构类型（[[temp.param]]）使 CPO 可以作为常量模板实参：`holder<std::ranges::begin>`。可平凡复制保证拷贝不会有副作用、可以按位复制。"所有实例相等且效果等价"（¶3）保证了 CPO 是无状态的"纯名字"：¶5 要求 `auto p = o;` 后 `p(args...)` 与 `o(args...)` 等价。若有状态成员，不同实例可能行为不同，`holder<o1>` 与 `holder<o2>` 也可能成为不同的类型——这都违反 ¶2–¶3，所以这样的实现不符合标准。
</details>

!!! question "思考题 2"
    假设某独立实现提供了 `<cmath>`，但把 `double abs(double)` 实现为删除函数。下面的代码在该实现上是什么行为？

    ```cpp
    #include <cmath>
    int f() { return std::abs(-2.5) > 2 ? 1 : 0; }
    ```

<details markdown="1">
<summary>展开查看答案与解析</summary>

`std::abs(-2.5)` 的重载决议中 `abs(double)` 是精确匹配，被选中；它是删除函数，所以程序非良构（[[dcl.fct.def.delete]]），编译器必须报错。这正是 [freestanding.item] ¶3 Note 1 的目的：如果 `abs(double)` 干脆不存在，`abs(int)` 会通过浮点-整数转换被选中，返回 2，`f()` 返回 0；而在宿主实现上 `f()` 返回 1——静默的语义差异。
</details>

## 小结

!!! summary "核心要点"
    - *exposition only* 的实体（*decay-copy*、*synth-three-way*、说明性私有成员）只是写规范的工具，程序不能命名，实现不必提供。
    - 模板形参名本身可以携带命名要求（`ForwardIterator` → *Cpp17ForwardIterator*）。
    - 枚举类型、位掩码类型的底层实现是未指明的：只能用标准给出的元素与运算符；"set/clear/is set" 有精确定义。
    - ntbs / ntmbs / 静态 ntbs 是全库引用的字符串术语；字符串字面量是静态 ntbs。
    - CPO：字面、semiregular、结构、可平凡复制、构造不抛、实例无差别；不满足要求时无可行 `operator()`（SFINAE 友好）。
    - 算法函数对象（niebloid）是 CPO，ADL 找不到，并在被非限定查找找到时抑制 ADL；C++26 起正式成为 CPO。
    - 未写出的特殊成员"存在且语义如默认"，但是否平凡未指明；类表示未指明。
    - *freestanding* / *hosted* / *freestanding-deleted* 注释是规范性的；删除定义防止迁移时重载决议静默改变。
