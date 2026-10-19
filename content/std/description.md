---
title: 描述方法：如何读懂库条文
summary: 库条款写法的词典。每个库条款由概要、要求、详细规范组成；函数规范中的 Constraints / Mandates / Constant When / Preconditions / Hardened preconditions / Effects / Synchronization / Postconditions / Result / Returns / Throws / Complexity / Remarks / Error conditions 各有确切的法律后果；Equivalent to 后面的代码如何解读；Cpp17 命名要求与库概念的区别。
status: done
covers: description.general, structure, structure.elements, structure.summary, structure.requirements, structure.specifications, structure.see.also
papers: P0788R3, P3471R4, P2900R14
related: library, conventions, requirements, utility.requirements, res.on.requirements, intro.compliance, intro.defs, basic.contract, temp.constr, conforming
tags: 库, 阅读方法, Constraints, Mandates, Preconditions, 加固, UB
updated: 2026-10-18
---

核心语言条款用的是“语法 + 语义规则”的写法：违反了某条规则就是 ill-formed，发生了某种求值就是 UB。库条款换了一套写法，几乎每个函数都由一串带斜体标签的**要素**（element）来规定：*Constraints:*、*Mandates:*、*Preconditions:*、*Effects:*、*Returns:*、*Throws:*……这些标签不是排版装饰，每一个都对应一种确定的法律后果：

- 写在 [[g:constraints-element|*Constraints*]] 里的条件不满足，函数静默地退出重载决议；
- 写在 [[g:mandates-element|*Mandates*]] 里的条件不满足，程序非良构（必须诊断）；
- 写在 [[g:preconditions-element|*Preconditions*]] 里的条件不满足，行为未定义；
- 写在 [[g:hardened-precondition|*Hardened preconditions*]] 里的条件不满足，在加固实现上必定终止，在非加固实现上是 UB。

同样一句“`T` 是可拷贝构造的”，放在不同的标签下，意思完全不同。不会读这些标签，就不可能对库函数作出 language lawyer 级别的判断。本节 [description] 是这套写法的图例，读懂第 17–33 章（[[support]] 到 [[exec]]）以及附录 [[depr]] 都要靠它。

阅读前最好已经熟悉：行为分类（[[intro.compliance]]、[[intro.defs]]）、约束与概念（[[temp.constr]]）、契约断言（[[basic.contract]]）。

## 本节的地图（[description.general] ¶1）

[[description]] 分两部分：

| 子条款 | 内容 | 本站页面 |
|---|---|---|
| [structure] | 每个库条款的结构：概要、要求、详细规范、See also | 本页 |
| [conventions] | 其他编辑约定：仅用于说明的实体、类型描述（枚举类型、位掩码类型、字符序列）、定制点对象、算法函数对象、类内函数、私有成员、独立项 | [[conventions]] |

## 每个库条款的四种要素（[structure.elements] ¶1）

¶1 每个库条款（按适用情况）包含：**概要**（Summary）、**要求**（Requirements）、**详细规范**（Detailed specifications）、对 C 标准库的引用。不适用的部分直接省略，例如一章没有提出任何要求，就不会有 Requirements 子条款（脚注）。

拿第 23 章 [[containers]] 举例：开头 [containers.general] 是概要，[container.requirements] 是要求（所有容器共享的那几张大表），[sequences]、[associative] 等是各容器的详细规范。

## 概要：头文件 synopsis（[structure.summary]）

¶1 概要给出本类别的大纲，介绍第一级子条款。每个子条款也有自己的概要，列出该子条款规定的头文件，以及每个头文件提供的库实体。

¶2 概要和详细规范的内容包括：宏、值、类型与别名模板、类与类模板、函数与函数模板、对象与变量模板、概念。

这里列出头文件所提供实体的，就是标准里随处可见的 **header synopsis**（例如 [utility.syn]），以 `namespace std { ... }` 形式写出。读 synopsis 时要注意：

- synopsis 中的声明是规范性的：[[contents#1]] 说，库为 synopsis 中描述的实体和宏提供定义；[[res.on.headers#1]] 说，头文件必须提供其 synopsis 中出现的声明。
- synopsis 后面跟的注释有规范意义：`// freestanding`、`// hosted`、`// freestanding-deleted`（[[freestanding.item]]）；`// exposition only`（[[expos.only.entity]]）；`// see below`（类型或值在别处说明）。
- synopsis 中的 `constexpr`、`noexcept`、`explicit`、`[[nodiscard]]` 等也是规范的一部分；但实现可以加强 `noexcept`（[[res.on.exception.handling#5]]），不能随意添加 `constexpr`（[[constexpr.functions]]）。

## 要求：程序扩展库时必须满足的条件（[structure.requirements]）

### 三类扩展（¶1–¶2）

¶1 要求描述的是**扩展标准库的 C++ 程序**必须满足的约束。所谓扩展，通常是以下几种之一：

- **¶1.1 模板实参**：你把自己的类型 `T` 放进 `std::vector<T>`，或给 `std::sort` 传比较器；
- **¶1.2 派生类**：你从 `std::streambuf`、`std::exception` 派生；
- **¶1.3 满足某种接口约定或建模（model）某个概念的容器、迭代器、算法**：你写了一个自定义迭代器交给标准算法使用。

换句话说，Requirements 是库对用户代码提出的要求，与 *Preconditions*（对单次调用的要求）不同，它规定的是类型或组件在整体上必须具备的能力。违反后果见 [[res.on.functions#2.3]]（UB）与 [[res.on.requirements]]（IFNDR）。

¶2 string 与 iostream 组件对模板实参的要求用一个显式的类模板 `char_traits` 来表达（[char.traits]）。这是 C++98 时代表达概念的写法：不直接对 `charT` 提要求，而是让程序提供一个 traits 类，把需要的操作集中起来。

### 用表达式有效而非成员存在来表述（¶3–¶4）

¶3 接口约定的要求尽可能宽泛地表述。不说“类 `X` 必须定义成员函数 `operator++()`”，而说“对 `X` 类型的任意对象 `x`，`++x` 是有定义的”。因此运算符是否为成员是**未指明**的。

这条原则影响深远。标准从不要求你的迭代器 `it` 有成员 `operator++`，只要求表达式 `++it` 合法且语义正确，用非成员函数、隐藏友元或继承来的成员实现都行。同理，库实现也只能以表达式的形式使用你的类型（写 `++it`，而不是 `it.operator++()`）。

¶4 要求是以**良定义的表达式**（well-defined expressions）来陈述的，这些表达式定义了满足要求的类型的有效用法。每一组表达式要求都对应一个具名的概念，或一张表格，列出初始的有效表达式集合及其语义。任何使用这些表达式要求的泛型算法（[[algorithms]]）都以其模板类型形参的有效表达式来描述。

### 两套命名要求：*Cpp17Xxx* 与 `concept`（¶5–¶6）

¶5 库规范对要求的命名有一个排版约定：

| 写法 | 指什么 | 例子 | 本质 |
|---|---|---|---|
| 斜体、以 *Cpp17* 开头（[[g:cpp17-named-requirement]]） | 一组以表格形式给出、可能附带文字语义要求的有效表达式要求 | *Cpp17Destructible*（[[utility.arg.requirements]] 表 35）、*Cpp17InputIterator* | 纯文字约定，编译器不知道它的存在 |
| 等宽字体 | 库概念，以概念定义（[[temp]]）给出，可能附带文字语义要求 | `destructible`（[concept.destructible]） | 真正的 C++ `concept`，可以写在 `requires` 中 |

前缀 Cpp17 是这样来的：C++20 引入了概念库，许多老的命名要求（如 `EqualityComparable`、`InputIterator`）与新概念同名但含义不同。为避免混淆，C++20 给老的表格式要求统一加上 *Cpp17* 前缀，表示这是 C++17 时代的那套要求。两者并不等价，例如 *Cpp17InputIterator* 要求 `iterator_traits` 中的五个嵌套类型、要求可以后置 `++` 并返回可解引用的东西，而 `input_iterator` 概念不要求迭代器可拷贝、不要求可比较相等；一个迭代器可以建模 `std::input_iterator` 却不满足 *Cpp17InputIterator*，反之亦然。

¶6 模板实参的要求有时直接以名字引用，见 [[type.descriptions]]。

### 以代码说明的语义只是等价性规范（¶7）

¶7 有时语义要求以 C++ 代码的形式给出。这样的代码规定的是一种构造与另一种构造**等价**，并不一定是该构造必须采用的实现方式。脚注略带调侃地补了一句：尽管在某些情况下，给出的代码明显就是最优实现。

这与 *Effects: Equivalent to* 的规则（下文 ¶4）一脉相承：标准给出的代码描述的是可观察结果，不约束实现手段。

### 必需操作不必是全函数（¶8）

¶8 本文档定义的任何概念的**必需操作**（required operations）不必是**全函数**（total function）：某些实参可能导致必需的语义无法满足。标准举的例子是，`totally_ordered` 要求的 `<` 在 NaN 上不满足该概念的语义要求，但这不影响类型是否建模该概念。

这一句保住了 `double`。如果因为存在 NaN 就说 `double` 不建模 `totally_ordered`，那么 `std::ranges::sort` 就不能用于 `double` 范围了。¶8 的意思是：建模概念的是**类型**，至于具体的**值**是否落在必需操作的定义域内，属于调用时的前置条件。对含 NaN 的范围排序仍然违反了 `ranges::sort` 的语义要求（[[res.on.requirements]]），但这是这一次调用的问题，而不是 `double` 这个类型的问题。

```cpp run ok
#include <algorithm>
#include <concepts>
#include <vector>
static_assert(std::totally_ordered<double>);   // 类型层面：double 建模 totally_ordered
int main() {
  std::vector<double> v{3.0, 1.0, 2.0};
  std::ranges::sort(v);                         // OK：值都在 < 的定义域内
  return v.front() == 1.0 ? 0 : 1;
  // 若 v 中含 NaN，则 < 不构成严格弱序，违反 sort 的要求——UB
}
```

### 关联约束附带的语义要求（¶9）

¶9 声明可以通过其关联约束（[[temp.constr.decl]]）显式地施加要求。当关联约束引用了某个概念时，该概念规定的语义约束也一并施加于该声明的使用。

也就是说，库函数模板上写着 `template<std::regular T>`，不仅意味着编译器要检查 `regular<T>` 得到**满足**（satisfied，语法层面），还意味着 `T` 必须**建模** `regular`，即满足所有文字描述的语义要求（`==` 是等价关系、拷贝后相等……）。编译器只能检查前者；后者不满足时是 IFNDR（[[res.on.requirements#3]]）。

## 详细规范（[structure.specifications]）

### 详细规范的组成与成员排列顺序（¶1–¶2）

¶1 每个详细规范包含：名字与简要描述；synopsis（类定义或函数声明）；对模板实参的限制（若有）；类不变式的描述；函数语义的描述。

¶2 类成员函数的描述（按适用情况）依次为：构造函数与析构函数；拷贝、移动与赋值函数；比较运算符函数；修改器（modifier）；观察器（observer）；运算符和其他非成员函数。所以读 `std::optional` 时，你知道 [optional.ctor] 在 [optional.assign] 前面，[optional.observe] 在 [optional.mod] 后面。

### 函数语义的十四种要素（¶3）

¶3 是本页的核心。函数语义的描述（按适用情况）包含以下要素，不适用的要素直接省略（脚注：没有前置条件的函数就没有 *Preconditions:* 要素）。下面先看总表，再逐条细讲：

| ¶ | 要素 | 规定什么 | 不满足 / 违反的后果 | 在哪个阶段 |
|---|---|---|---|---|
| 3.1 | *Constraints* | 函数参与重载决议的条件 | 函数静默地不可行（non-viable） | 编译期，SFINAE 友好 |
| 3.2 | *Mandates* | 不满足就使程序非良构的条件 | {{ill-formed}}，必须诊断 | 编译期，不 SFINAE 友好 |
| 3.3 | *Constant When* | 调用成为常量子表达式所需的条件 | 调用不是常量子表达式 | 常量求值 |
| 3.4 | *Preconditions* | 函数在被调用时假定成立的条件 | {{ub}} | 运行期 |
| 3.5 | *Hardened preconditions* | 同上，但在加固实现中被检查 | 加固实现：契约违反并终止；非加固实现：{{ub}} | 运行期 |
| 3.6 | *Effects* | 函数执行的动作 | — | — |
| 3.7 | *Synchronization* | 适用的同步操作 | — | — |
| 3.8 | *Postconditions* | 函数建立的条件（可观察结果） | 实现的义务 | — |
| 3.9 | *Result* | 类型名的含义，或表达式的类型与值类别 | — | — |
| 3.10 | *Returns* | 返回值的描述 | — | — |
| 3.11 | *Throws* | 抛出的异常及其条件 | — | — |
| 3.12 | *Complexity* | 时间和/或空间复杂度 | 实现的义务（上界） | — |
| 3.13 | *Remarks* | 其他语义约束 | 视内容而定 | — |
| 3.14 | *Error conditions* | 通过错误码报告的错误条件 | — | — |

前五项是对**调用者**的要求，违反了由调用者负责；后九项是对**实现**的要求，即实现承诺做什么。

#### *Constraints*：不满足就退出重载决议（¶3.1）

!!! std
    *Constraints*: the conditions for the function's participation in overload resolution.

    *Constraints*：函数参与重载决议的条件。

Note 1 说得更直白：不满足这种条件会导致函数**静默地不可行**（silent non-viability）。Example 1 给出了实现手段，可以用 *constraint-expression*（`requires` 子句）。C++20 之前的实现用 `enable_if`，效果相同，这就是传统上说的 SFINAE 友好。

关键在“静默”二字：*Constraints* 不满足不是错误，函数只是从候选集中消失。因此：

- 若还有别的候选，重载决议会直接选中别的候选；
- 类型萃取 `is_constructible`、`is_invocable`、`is_convertible` 和 `requires` 表达式能够观测到它，结果为 `false`。

```cpp run ok
#include <functional>
#include <memory>
#include <type_traits>

// [func.wrap.func.con]：function(F&&) 的 Constraints 要求 F 可以按 R(Args...) 调用
static_assert(!std::is_constructible_v<std::function<void()>, int>);
static_assert( std::is_constructible_v<std::function<void()>, void(*)()>);

// [unique.ptr.create]：make_unique<T>(args...) 的 Constraints：T 不是数组类型
template<class T>
concept can_make_unique = requires { std::make_unique<T>(); };
static_assert( can_make_unique<int>);
static_assert(!can_make_unique<int[3]>);   // 匹配的是那个 = delete 的重载，requires 观测为 false

int main() { }
```

`std::make_unique<int[3]>()` 的情形值得细看。标准为已知边界的数组专门声明了一个带 *Constraints: T is an array of known bound.* 的删除重载，它参与重载决议并被选中，然后因为是删除的函数而使程序非良构。这正是下面要讲的 ¶3.2 Example 2 描述的技巧。

#### *Mandates*：不满足就是硬错误（¶3.2）

!!! std
    *Mandates*: the conditions that, if not met, render the program ill-formed.

    *Mandates*：若不满足，则使程序非良构的条件。

Example 2 给出两种实现手段：

1. 用 `static_assert`（最常见）；
2. 若希望在重载决议选中该函数之后才发出诊断，可以写成 *constraint-expression*，同时将函数定义为删除的。

关键差异在于，用 `static_assert` 实现的 *Mandates* 不影响重载决议，`requires` 表达式和类型萃取也观测不到它。后两者只检查**声明**，而 `static_assert` 在**函数体**里，只在函数体实例化时才触发，那时已经不在 SFINAE 的直接上下文中了。

```cpp run ok
#include <tuple>
std::tuple<int, int> t;
// [tuple.elem]：get<T>(t) 的 Mandates：T 在 Types 中恰好出现一次
constexpr bool callable = requires { std::get<int>(t); };
static_assert(callable);       // requires 表达式"以为"可以调用！
int main() { }
```

```cpp error
#include <tuple>
int main() {
  std::tuple<int, int> t;
  return std::get<int>(t);     // error: Mandates 不满足——int 出现了两次（libc++: static_assert 失败，
                               //        "type occurs more than once in type list"）
}
```

这就是 *Mandates* 不 SFINAE 友好的含义。如果在泛型代码里用 `requires { std::get<T>(x); }` 检测能否按类型取元素，会得到错误的肯定结果，然后在真正调用时遇到硬错误。

!!! tip "为什么不全都写成 Constraints？"
    两者的区分是有意的设计选择。*Constraints* 让函数退出候选集，适合用于重载之间的分派，例如 `optional<T>` 的多个构造函数按 `T` 能否从 `U` 构造、能否隐式转换来选择。*Mandates* 适合调用本身就写错了、应当明确报错的场合：如果 `get<int>` 静默消失，用户只会看到一条难以理解的 “no matching function”，远不如一句“类型出现了不止一次”清楚。另外，*Constraints* 会把条件暴露到函数签名中，增加编译开销，也可能导致不想要的递归约束检查。

#### *Constant When*：常量求值的前提（¶3.3）

¶3.3 *Constant When* 规定的是调用成为常量子表达式（[[defns.const.subexpr]]）所需的条件。它是 C++23 之后更新的措辞中新加的要素，用于这样一类函数：函数本身是 `constexpr` 的，但并非每次调用都能在编译期完成。例如 [bit.cast]：

!!! std
    *Constant When*: Neither `To` nor `From` has constexpr-unknown representation.

    *Constant When*：`To` 和 `From` 都不具有 constexpr-unknown 表示。

也就是说，`std::bit_cast` 总是 `constexpr` 的，但如果涉及的类型含有指针、联合体、引用成员等在编译期无法确定位模式的部分（[[expr.const]]），这次调用就不是常量子表达式，在需要常量表达式的上下文中使用它是非良构的。

它与 *Mandates* 的区别在于，*Constant When* 不满足时，调用在运行期仍然合法，只是不能在编译期求值。另一种常见写法是 “*Constant When*: Preconditions are met.”，意思是在常量求值中违反前置条件不会成为 UB，而是使表达式不成为常量表达式（编译器必须报错）。这与核心语言中常量求值不允许 UB 的设计（[[expr.const]]）一致。

#### *Preconditions*：违反就是 UB（¶3.4）

!!! std
    *Preconditions*: conditions that the function assumes to hold whenever it is called; violation of any preconditions results in undefined behavior.

    *Preconditions*：函数在每次被调用时假定成立的条件；违反任何前置条件都导致未定义行为。

这是库对调用者的要求：调用者负责保证条件成立，函数不检查（或者说标准不要求检查）。Example 3 提到实现可以用契约断言（例如 `pre` 断言，[[dcl.contract.func]]）来表达其中的一部分；[[res.contract.assertions]] 正式授权了这一点。但无论实现是否检查，在标准层面违反了就是 UB。

```cpp ub
#include <algorithm>
#include <vector>
int main() {
  std::vector<int> v{3, 1, 2};          // 未排序
  // [lower.bound] Preconditions：[first, last) 关于 e < value 是划分好的（partitioned）
  auto it = std::lower_bound(v.begin(), v.end(), 2);  // UB：违反前置条件
  return *it;
}
```

实践中这段代码几乎总是返回某个位置，因为二分查找本身不会越界。但从规则上讲，标准不对结果作任何要求，编译器也有权假定前置条件成立并据此优化。

*Preconditions* 与 *Constraints* / *Mandates* 的区别在于运行期与编译期：前置条件一般涉及**值**（指针非空、下标在范围内、范围已排序），编译器无法静态判定；后两者涉及**类型**与编译期属性。

#### *Hardened preconditions*：可强制检查的前置条件（¶3.5）{{c++26}}

¶3.5 *Hardened preconditions*：函数在每次被调用时假定成立的条件。

- **¶3.5.1** 在**加固实现**（hardened implementation，[[intro.compliance]]）中调用该函数时，在函数产生任何其他可观察副作用之前，以加固前置条件为谓词的契约断言以终止语义（terminating semantic，[[basic.contract.eval]]）求值。
- **¶3.5.2** 在非加固实现中调用该函数时，若违反任何加固前置条件，程序具有未定义行为。

一个实现是否是加固实现，是**实现定义**的（[intro.compliance] ¶8），实践中通常是一个编译开关。标为 *Hardened preconditions* 的大多是防止越界访问的前置条件，越界访问是内存安全漏洞最主要的来源：

| 函数 | 加固前置条件 |
|---|---|
| 序列容器 `a[n]`（[sequence.reqmts]） | `n < a.size()` 为 `true` |
| `optional::operator*`、`operator->` | `has_value()` 为 `true` |
| `span::operator[]` 等 | 下标在范围内 |

终止语义意味着程序在契约违反后终止（*enforce* 或 *quick-enforce*，[[basic.contract.eval]]），不能选择 *ignore* 或 *observe*。也就是说，加固实现保证越界访问不会悄悄发生。这是一项**安全性**保证，而不是调试上的便利。

```cpp run ok flags="-std=c++2c -stdlib=libc++ -D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_FAST" cc=clang_trunk
#include <cstdio>
#include <vector>
int main(int argc, char**) {
  std::vector<int> v{1, 2, 3};
  if (argc > 1)
    std::printf("%d\n", v[3]);  // 加固实现：在访问前检查 3 < size()，失败则终止
                                // 非加固实现：UB
}
```

在本机 libc++ 上实测：以 `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_FAST` 编译并带一个参数运行，进程收到 `SIGTRAP`（退出码 133）；改用 `_LIBCPP_HARDENING_MODE_DEBUG` 则打印 `libc++ Hardening assertion ... failed` 后 abort。默认（`_LIBCPP_HARDENING_MODE_NONE`）下什么也不检查，直接读越界内存。

加固实现还必须定义一组特性测试宏：`__cpp_lib_hardened_array`、`__cpp_lib_hardened_basic_string`、`__cpp_lib_hardened_vector` 等（[version.syn] ¶3）；非加固实现不应定义它们。代码可以据此判断自己是否运行在加固实现上。

!!! note "*Hardened preconditions* 与契约"
    加固与 C++26 的契约（[[P2900R14]]）是一起设计的。¶3.5.1 用以终止语义求值的契约断言来定义加固检查，因此违反时的行为（调用契约违反处理函数、`std::contracts::contract_violation` 对象……）与用户自己写的 `pre` 断言一致。标准库加固由 [[P3471R4]] 引入 C++26。

#### *Effects*、*Synchronization*、*Postconditions*（¶3.6–¶3.8）

- **¶3.6 *Effects***：函数执行的动作。最常见的写法是 “*Effects*: Equivalent to: …”，其解释规则见下文 ¶4。
- **¶3.7 *Synchronization***：函数适用的同步操作（[[intro.multithread]]）。例如 `std::thread` 构造函数的 *Synchronization* 是 “The completion of the invocation of the constructor synchronizes with the beginning of the invocation of the copy of f”。读并发代码时，库函数之间有没有 happens-before 关系，全看这个要素。
- **¶3.8 *Postconditions***：函数建立的条件（有时称为可观察结果）。这是实现的义务，调用返回后这些条件一定成立。Example 4 指出，实现可以用后置条件断言（`post`）来表达。例如 `vector::clear()` 的效果之一是 `empty()` 为 `true`。

#### *Result*：类型与值类别（¶3.9）

¶3.9 *Result*：对于 *typename-specifier*，描述所命名的类型；对于表达式，描述表达式的类型与值类别。类型是左值引用，表达式就是左值；是右值引用，就是 xvalue；否则是 prvalue。

*Result* 主要出现在以表格或“表达式 + 要素”形式给出的要求中，例如 [[allocator.requirements]] 中 `a.allocate(n)` 的 *Result* 是 `XX::pointer`。注意这里用的是从类型推出值类别的规则，与 `decltype` 的规则方向一致（[[topics/value-categories]]）：*Result* 写成 `T&` 就意味着该表达式是左值。

#### *Returns*、*Throws*（¶3.10–¶3.11）

- **¶3.10 *Returns***：返回值的描述。
- **¶3.11 *Throws***：函数抛出的异常，以及导致抛出的条件。

*Throws* 的常见措辞及其确切含义：

| 措辞 | 含义 |
|---|---|
| *Throws*: Nothing. | 不抛异常，但不等于声明为 `noexcept`，见下文陷阱 |
| *Throws*: `out_of_range` if `pos > size()`. | 抛 `out_of_range` 或其派生类型（[[res.on.exception.handling#1]]） |
| *Throws*: Any exception thrown by the constructor of `T`. | 透传 |
| 无 *Throws* 要素，但函数不是 `noexcept` | 可以抛实现定义的异常（[[res.on.exception.handling#4]]），典型是 `bad_alloc` |

#### *Complexity*（¶3.12、¶6、¶7）

¶3.12 *Complexity*：时间和/或空间复杂度。

¶6 若复杂度要求的公式算出负数次操作，实际要求是零次操作（脚注：这在某些情况下简化了复杂度要求的表述，例如“至多 `N - 1` 次比较”在 `N == 0` 时不需要特别说明）。

¶7 库条款中规定的复杂度要求是上界；提供更好复杂度保证的实现也满足要求。

读复杂度要素时要分清计数对象。标准通常数的是比较次数、谓词调用次数、赋值次数，而不是机器指令或时间。例如 `std::sort` 的 *Complexity* 是 O(N log N) 次比较和投影，`std::lower_bound` 至多 log₂(last − first) + O(1) 次比较，但对非随机访问迭代器，它移动迭代器的次数可以是线性的。另外，摊还常数时间（amortized constant time，如 `vector::push_back`）也是一种上界，单次操作可以是线性的。

#### *Remarks*（¶3.13）

¶3.13 *Remarks*：函数的其他语义约束。这一要素收纳各种零散内容，常见的有：

- 异常规范的精确条件：“The exception specification is equivalent to: …”（对应 synopsis 中的 `noexcept(see below)`），例如 `std::exchange`；
- `explicit(see below)` 的条件；
- 构造函数何时是平凡的、何时是 `constexpr` 的；
- 一些老措辞中残留的 “This function shall not participate in overload resolution unless …”，C++20 之后基本都已改写为 *Constraints*；
- 加固 / 前置条件之外的附加说明，如 allocator 要求中的 “Default: …”（见 [[allocator.requirements]]）。

#### *Error conditions*（¶3.14、¶8）

¶3.14 *Error conditions*：函数通过错误码报告的错误条件。¶8 进一步说明：错误条件列出函数可能失败的条件，连同合适的解释，以 `enum class errc` 常量（[syserr]）给出。例如 `std::mutex::lock()` 的 *Error conditions* 包括 `resource_deadlock_would_occur`、`operation_not_permitted`。错误码对象的 `category()` 如何选择，见 [[value.error.codes]]。

### Equivalent to 的解释规则（¶4）

库规范中最常见、也最容易误读的一句话是 *Effects: Equivalent to:* 后接一段代码。¶4 规定了它的精确含义：

1. F 自己的 *Constraints* 和 *Mandates* 先施加（“logically imposed prior to the equivalent-to semantics”）。
2. 代码序列的语义，由其中出现的那些函数调用的 *Constraints*、*Mandates*、*Constant When*、*Preconditions*、*Hardened preconditions*、*Effects*、*Synchronization*、*Postconditions*、*Returns*、*Throws*、*Complexity*、*Remarks*、*Error conditions* 决定。也就是说，被调函数的全部规范都**传递**过来。
3. 返回值：若 F 有 *Returns* 要素，由它决定；否则（非 `void` 返回）由代码序列中的 `return` 语句决定。
4. 若 F 自己有 *Throws*、*Postconditions* 或 *Complexity* 要素，则以 F 的为准，覆盖代码序列中那些调用的同名要素。

拿 [utility.exchange] 说明：

```cpp
template<class T, class U = T>
  constexpr T exchange(T& obj, U&& new_val) noexcept(see below);
// Effects: Equivalent to:
//   T old_val = std::move(obj);
//   obj = std::forward<U>(new_val);
//   return old_val;
// Remarks: The exception specification is equivalent to:
//   is_nothrow_move_constructible_v<T> && is_nothrow_assignable_v<T&, U>
```

按 ¶4 可以推出，`exchange` 的前置条件和可能抛出的异常，就是 `T` 的移动构造与 `T&` 从 `U` 赋值的前置条件和异常；它没有自己的 *Throws*，所以不覆盖。返回值由代码中的 `return old_val;` 决定。

等价于不等于必须这样实现（[structure.requirements] ¶7），实现可以换一种写法，只要可观察行为相同。但它也带来一些容易被忽略的连带后果：

- 代码序列中的拷贝、移动、临时对象都是语义的一部分。例如等价代码若写的是 `return T(x);`，`T` 的拷贝构造函数就会被调用（或可省略），因而对它有要求；
- 代码中的名字按 [[contents#3]] 解释：在 F 的声明处做非限定查找，**不做 ADL**（`swap` 等少数名字例外）；
- `Equivalent to: return f(args...);` 并不自动意味着 F 与 `f(args...)` 有相同的 `noexcept`，异常规范要看 synopsis 与 *Remarks*。

与此相关的另外两个术语：

- **as if**：比 equivalent to 宽松的描述，通常配合一段说明性代码，意在描述效果，不精确地传递全部要素。
- **表达式等价**（expression-equivalent，[[defns.expression.equivalent]]）：两个表达式效果相同，要么都可能抛出、要么都不抛出，要么都是常量子表达式、要么都不是。定制点对象（[[customization.point.object]]）和 `views::xxx` 范围适配器大量使用这个更强的说法，它连 `noexcept` 和能否在编译期求值都一并保证了。

### 替换函数与处理函数：必需行为与默认行为（¶5）

¶5 对非保留的替换函数和处理函数（`operator new`、`new_handler` 等），[[support]] 为相关函数规定两种行为：

- **默认行为**（*Default behavior*）：描述实现提供的函数定义做什么；
- **必需行为**（*Required behavior*）：描述无论由实现还是由 C++ 程序提供的函数定义，都必须具备的语义。

若描述中没有显式区分，所描述的行为是必需行为。例如全局 `operator new(size_t)` 的必需行为是返回指向适当对齐的、至少 `size` 字节存储的非空指针，或抛出 `bad_alloc`；默认行为则具体到在循环中尝试分配（是否调用 `malloc` / `aligned_alloc` 未指明），失败时若当前 new_handler 为空就抛 `bad_alloc`，否则调用它后重试。替换它时只需满足必需行为，不满足则是 UB（[[res.on.functions#2.1]]）。详见 [[constraints]]。

## See also（[structure.see.also]）

¶1 标为 See also 的段落包含对其他标准相关部分的交叉引用（[[intro.refs]]），主要是 C 标准。例如 `<cstring>` 的 synopsis 之后会有 “See also: ISO/IEC 9899:2024, 7.26”。这些段落只是指路，具体语义规则见 [[library.c]]。

## 实现视角

各要素在三大实现中的典型落地：

| 要素 | libc++ | libstdc++ | MSVC STL |
|---|---|---|---|
| *Constraints* | C++20 下用 `requires`，更早模式用 `enable_if`（`__enable_if_t`） | `requires` / `enable_if` / `_Require<...>` | `enable_if_t` / `requires` |
| *Mandates* | `static_assert`（如 `__tuple/find_index.h` 中的 “type occurs more than once in type list”） | `static_assert` | `static_assert` |
| *Preconditions* / *Hardened preconditions* | `_LIBCPP_ASSERT_*` 宏族，按 `_LIBCPP_HARDENING_MODE`（none / fast / extensive / debug）分级启用 | `__glibcxx_assert`，由 `_GLIBCXX_ASSERTIONS` 启用 | `_STL_VERIFY` 等，受 `_ITERATOR_DEBUG_LEVEL` 等开关控制 |

libc++ 的检查宏按类别划分（`_LIBCPP_ASSERT_VALID_ELEMENT_ACCESS`、`_LIBCPP_ASSERT_NON_NULL`、`_LIBCPP_ASSERT_VALID_INPUT_RANGE`……），再由硬化模式决定启用哪些类别。fast 模式只开启安全关键、常数时间的检查，例如本机 `__vector/vector.h` 中 `operator[]` 的实现：

```cpp
reference operator[](size_type __n) _NOEXCEPT {
  _LIBCPP_ASSERT_VALID_ELEMENT_ACCESS(__n < size(), "vector[] index out of bounds");
  return this->__layout_.__begin_ptr()[__n];
}
```

还可以看到 `_NOEXCEPT`：标准的 `vector::operator[]` 没有声明 `noexcept`，libc++ 利用 [[res.on.exception.handling#5]] 的许可加强了它。这与加固并不冲突，因为 fast 模式失败时是 trap，不是抛异常。libc++ 还提供 `_LIBCPP_ASSERTION_SEMANTIC`，其取值 ignore / observe / quick-enforce / enforce 与契约的四种求值语义一一对应。

## 历史与演进

- **C++98–C++17**：函数规范的要素是 *Requires:*、*Effects:*、*Postconditions:*、*Returns:*、*Throws:*、*Complexity:*、*Remarks:*、*Error conditions:*。*Requires:* 的含义并不统一，有时表示违反即 UB，有时表示违反即非良构，有时又被理解为不满足就不参与重载决议。最后一种另有固定说法，写在 *Remarks* 里：“This function shall not participate in overload resolution unless …”。
- **C++20**：[[P0788R3]]（“Standard Library Specification in a Concepts and Contracts World”）把 *Requires:* 拆成了含义明确的 *Constraints:*、*Mandates:*、*Expects:*（即前置条件），并引入 *Ensures:*。随后一系列逐章的 “Mandating the standard library” 提案把全部库条款改写为新写法。在 C++20 定稿前，*Expects:* / *Ensures:* 又改称 *Preconditions:* / *Postconditions:*。同时 C++20 给老的表格式命名要求加上 *Cpp17* 前缀。
- **C++23 之后**：工作草案新增了 *Constant When* 要素，用于描述 `constexpr` 函数的哪些调用可以在编译期完成。
- **C++26**：[[P3471R4]] 引入标准库加固与 *Hardened preconditions* 要素；[[P2900R14]] 引入契约，使 ¶3.4 的 Example 3、¶3.5.1 和 [[res.contract.assertions]] 有了语言层面的落脚点。

## 常见误区与陷阱

!!! pitfall "以为 Preconditions 会被检查"
    *Preconditions* 违反是 UB，标准从不要求检查。`std::vector::front()` 用在空容器上、`std::string_view` 用不以零结尾的指针构造、对未排序范围 `binary_search`，在非加固实现上都可能看起来一切正常。只有 *Hardened preconditions* 在加固实现中才有检查保证。

!!! pitfall "用 requires 表达式探测 Mandates"
    `requires { std::get<T>(t); }`、`std::is_invocable_v<decltype(f), ...>` 只能探测 *Constraints*。依赖 *Mandates* 的条件做分派，会在真正实例化时遭遇硬错误。

!!! pitfall "*Throws: Nothing* ≠ noexcept"
    Throws: Nothing 是行为承诺，正常情况下它不抛。但函数若有前置条件（窄契约），标准通常故意不把它声明为 `noexcept`（这一设计惯例常被称为 Lakos 规则），以便调试型实现可以在违反前置条件时抛出异常做测试。所以 `noexcept(v[0])` 的结果在不同实现上可能不同：本机 libc++ 为 `true`，因为它主动加强了异常规范。别在可移植代码中依赖它。

!!! pitfall "把 Complexity 当成性能保证"
    *Complexity* 是上界，且只计数特定操作。`std::list::size()` 在 C++11 之后是常数时间，但 `std::distance` 在非随机访问迭代器上是线性的；`std::unordered_map::find` 的平均常数、最坏线性也写在 *Complexity* 里。复杂度要素也不约束内存分配次数、缓存行为等。

!!! lawyer "Equivalent to 的代码里的 UB 也是你的 UB"
    若 F 的 *Effects* 等价于一段代码，而这段代码中某个调用的前置条件被违反，那么调用 F 就违反了前置条件，即便 F 本身没有 *Preconditions* 要素。¶4 把代码序列中各调用的 *Preconditions* 都传递了过来。

## 思考题

!!! question "思考题 1"
    `std::optional<T>` 的转换构造函数 `template<class U = T> constexpr explicit(see below) optional(U&& v);` 的条件写在 *Constraints* 里（`is_constructible_v<T, U>` 等）。如果改成写在 *Mandates* 里，`std::is_convertible_v<int, std::optional<std::string>>` 会是什么？对用户代码有什么影响？

<details markdown="1">
<summary>展开查看答案与解析</summary>

写在 *Constraints* 里时，`std::string` 不能从 `int` 构造，转换构造函数不参与重载决议，`is_convertible_v<int, optional<string>>` 为 `false`。

若改成 *Mandates*（函数体里的 `static_assert`），该构造函数总是参与重载决议，`is_convertible_v` 只检查声明，会返回 `true`；但真正写 `std::optional<std::string> o = 42;` 时才在实例化中硬错误。更糟的是，它会干扰重载决议：例如一个函数同时有 `f(std::optional<std::string>)` 和 `f(long)` 两个重载时，`f(42)` 可能因为 `optional` 的构造函数看起来可行而产生歧义或选错，然后硬错误。这正是 [structure.specifications] ¶3.1 / ¶3.2 区分两种要素的原因。
</details>

!!! question "思考题 2"
    在非加固实现上，`std::optional<int> o; int x = *o;` 是什么行为？在加固实现上呢？如果程序安装了一个契约违反处理函数并在其中直接返回，又会怎样？

<details markdown="1">
<summary>展开查看答案与解析</summary>

`optional::operator*` 有 *Hardened preconditions*: `has_value()` is `true`。

- 非加固实现：¶3.5.2，{{ub}}。
- 加固实现：¶3.5.1，在任何其他副作用之前，以终止语义求值一个谓词为 `has_value()` 的契约断言；谓词为 `false`，发生契约违反。终止语义下（enforce），先调用契约违反处理函数，若处理函数正常返回，程序随后仍以实现定义的方式终止（[[basic.contract.eval]]）；若是 quick-enforce，则不调用处理函数直接终止。无论哪种，都不会继续执行到解引用，所以处理函数直接返回也无济于事。这正是终止语义与 observe 语义的区别。
</details>

!!! question "思考题 3"
    *Effects: Equivalent to: `return std::invoke(f, args...);`* 与 “`f(args...)` is expression-equivalent to `std::invoke(f, args...)`” 有什么区别？

<details markdown="1">
<summary>展开查看答案与解析</summary>

前者只传递效果、前置条件、返回值、异常等语义（¶4），不保证 F 的 `noexcept` 与 `invoke` 相同，也不保证 F 的调用是常量子表达式当且仅当 invoke 的调用是常量子表达式，这些要看 F 自己的 synopsis 和 *Remarks*。还要注意 `return` 语句本身会引入一次返回值初始化。

后者用的是表达式等价（[[defns.expression.equivalent]]）：效果相同、都可能抛出或都不抛出、都是常量子表达式或都不是。它是更强的保证，通常用于 CPO 和范围适配器，使 `noexcept(f(args...))` 这类探测结果可以精确地转发。
</details>

## 小结

!!! summary "核心要点"
    - 库条款 = 概要（synopsis）+ 要求 + 详细规范 + C 库引用。synopsis 中的声明与注释（`freestanding`、`exposition only`、`see below`）都是规范性的。
    - Requirements 是对扩展库的用户代码的要求，以表达式有效而非成员存在来表述。斜体 *Cpp17Xxx* 是表格式要求，等宽 `xxx` 是真正的 concept；二者不等价。
    - 必需操作不必是全函数：NaN 不妨碍 `double` 建模 `totally_ordered`。
    - 四种对调用者的要求：

      | 要素 | 违反后果 | SFINAE 能看见吗 |
      |---|---|---|
      | *Constraints* | 不参与重载决议 | 能 |
      | *Mandates* | 非良构，必须诊断 | 不能 |
      | *Preconditions* | UB | — |
      | *Hardened preconditions* | 加固实现：终止；否则 UB | — |

    - *Constant When* 只影响能否成为常量子表达式。
    - *Effects: Equivalent to* = F 自己的 Constraints/Mandates 先行 + 代码中所有调用的规范传递 + F 自己的 Throws/Postconditions/Complexity 覆盖；不是实现指令。
    - *Complexity* 是上界、计数特定操作；*Throws: Nothing* 不等于 `noexcept`。
