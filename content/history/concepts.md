---
title: 概念（concepts）三十年
summary: 模板为什么长期没有接口，C++0x 的概念为什么在 2009 年被撤出，C++20 又换了哪种设计；今天的满足、包含规则和 `Concept auto` 写法都是这些取舍留下的结果。
status: draft
order: 10
papers: N1510, N2773, N2906, N3580, P0240R0, P0587R0, P0717R1, P0696R1, P0734R0, P1141R2, P2963R3, P2841R7
related: temp.constr, temp.constr.order, temp.concept, expr.prim.req, concepts, temp.res, topics/concepts, topics/two-phase-lookup
tags: 概念, 约束, 泛型编程, SFINAE, 标准化历史
updated: 2026-10-19
---

!!! tldr
    - C++98 的模板没有接口：对模板实参的要求只写在文档里，错误要到实例化深处才暴露。约束类和 `enable_if` 是库作者的补救。
    - C++0x 的第一版概念把概念做成一组函数签名，类型要靠 concept map 声明自己满足概念，函数体还要按约束检查。规格膨胀、编译变慢、意见无法统一，2009 年整体撤出。
    - C++20 的概念是编译期谓词：类型是否满足由编译器计算，概念之间的强弱由约束的逻辑结构推算，函数体不做定义检查。
    - 包含关系只认出自同一处源码的原子约束，所以要让一个概念强于另一个，必须在定义里写出那个概念的名字。
    - `void f(Sortable auto&)` 里的 `auto` 是语法之争的妥协结果。C++26 又让折叠表达式约束能比较强弱，并允许把概念作为模板实参传递。

本页的史料主要来自 Stroustrup 的三份回顾：*The Design and Evolution of C++*（1994，下称 D&E）、HOPL III 论文 *Evolving a language in and for the real world: C++ 1991–2006*（2007）和 HOPL IV 论文 *Thriving in a Crowded and Changing World: C++ 2006–2020*（2020）。它们是当事人一方的回忆，涉及他人观点和会议气氛的地方标注"据 Stroustrup 回忆"。规则本身见 [[temp.constr]]、[[temp.concept]]、[[expr.prim.req]] 和 [[topics/concepts]]。

## 一、模板没有接口

### 三个目标只做到了两个

Stroustrup 回顾说，他设计模板时想要三样东西：足够通用；与手写代码相比零开销；有良好定义的接口，类型检查和重载能力与普通函数相当（HOPL IV §6.1）。当时没人知道怎样同时做到三点，C++ 得到了前两样。

结果是模板接口成了编译期的鸭子类型（duck typing）：模板用到了实参的什么操作，实参就得支持什么，但这些要求不写在声明里。标准库的要求（"输入迭代器"、"可小于比较"）只写在标准正文的要求表里，HOPL III §8.3.3 的说法是 "compilers don't read manuals"。用错了，错误信息指向模板内部的某一行，往往长达几屏。

为什么不像 Eiffel 那样要求实参派生自某个基类，写成 `template<class T : Base>`？Stroustrup 在 2003 年的 [[N1510]] 中说，这类基于签名的方案从 1986 年前后起多次被考虑，也多次被否决。它要求实参类型的操作签名与约定精确匹配，处理不了隐式转换、重载和混合类型运算，而这些正是 C++ 泛型代码的日常。

### 库作者的两种补救

第一种是**约束类**（constraints class）：写一个类模板，在里面把所需操作逐一用一遍，再在算法开头实例化它，让错误提前到入口处出现。Boost 的 Concept Check Library 把这一做法系统化了（HOPL III §8.3.3）。

```cpp run title="constraints_class.cpp" ok
// C++98 风格：T 不支持这些操作时，实例化 Forward_iterator<T> 出错
template<class T> struct Forward_iterator {
    static void constraints(T a) {
        ++a; a++;          // 能自增
        T b = a; b = a;    // 能复制
        *b = *a;           // 能解引用并赋值
    }
    Forward_iterator() { void (*p)(T) = constraints; (void)p; }
};

template<class In, class Pred>
In find_if2(In first, In last, Pred pred) {
    Forward_iterator<In>();                 // 在函数体开头检查
    while (first != last && !pred(*first)) ++first;
    return first;
}

bool even(int x) { return x % 2 == 0; }
int main() { int a[] = {1, 2, 3}; return *find_if2(a, a + 3, even) == 2 ? 0 : 1; }
```

检查写在函数体里，调用者看不到，也不能参与重载决议，只是让错误早一点、短一点。

第二种利用了 [[g:sfinae]]：在函数模板声明里替换模板实参时，如果产生了无效的类型或表达式，这个候选只是被丢掉，不算错误。Järvi、Willcock、Lumsdaine 等人在 2003 年把它包装成 `enable_if`（*Concept-controlled polymorphism*，GPCE 2003），C++11 收入标准库。它能参与重载决议，但两个重载的条件必须手工写成互斥的。下面左边是 `enable_if` 的写法，右边是 C++20 的写法：

<div class="compare" markdown="1">

```cpp run ok
#include <iterator>
#include <list>
#include <type_traits>
template<class It>
using cat = typename
  std::iterator_traits<It>::iterator_category;
template<class It>
constexpr bool is_ra = std::is_base_of_v<
  std::random_access_iterator_tag, cat<It>>;

template<class It,
         std::enable_if_t<is_ra<It>, int> = 0>
void my_advance(It& it, int n) { it += n; }

template<class It,
         std::enable_if_t<!is_ra<It>, int> = 0>
void my_advance(It& it, int n)
{ while (n--) ++it; }   // 条件必须写成互斥

int main() {
  int a[4]{}; int* p = a;
  my_advance(p, 2);
  std::list<int> l{1, 2, 3};
  auto i = l.begin(); my_advance(i, 2);
}
```

```cpp run ok
#include <iterator>
#include <list>

template<std::random_access_iterator It>
void my_advance(It& it, int n) { it += n; }

template<std::input_iterator It>
void my_advance(It& it, int n)
{ while (n--) ++it; }
// 两个都满足时，选更受约束的那个，
// 不必手工写互斥条件

int main() {
  int a[4]{}; int* p = a;
  my_advance(p, 2);
  std::list<int> l{1, 2, 3};
  auto i = l.begin(); my_advance(i, 2);
}
```

</div>

左边的约束藏在一个默认模板实参里，读声明的人很难看出它要求什么。2016 年 Ville Voutilainen 在 [[P0225R0]] 中逐条列举这些问题，作为尽快引入概念的理由。右边能工作，靠的是 C++20 的包含规则（[[temp.constr.order]]）：`random_access_iterator` 的定义里写了 `bidirectional_iterator`，后者又写了 `forward_iterator`、`input_iterator`，所以它比 `input_iterator` 更受约束。这条规则是怎么来的，下文会讲到。

## 二、第一次尝试：C++0x 概念（2003–2009）

### 两条路线

2003 年，Stroustrup 与 Gabriel Dos Reis 提出用**使用模式**（use pattern）描述约束：列出对某类型应当合法的表达式，而不是列出函数签名（[[N1510]] 等）。几乎同时，印第安纳大学的 Douglas Gregor、Jeremy Siek、Andrew Lumsdaine 等人提出了另一种设计（[[N1758]]）。两者的分歧可以概括成一张表（HOPL IV §6.2）：

| | Indiana 方案 | Texas 方案 |
|---|---|---|
| 概念是什么 | 一组操作（伪签名）与关联类型，近似 Haskell 的类型类 | 编译期类型谓词，用使用模式描述 |
| 类型如何满足概念 | 程序员显式声明 | 由编译器计算 |

委员会鼓励合并而不是对决，两组人在 2006 年写出联合提案 [[N2081]]。据 HOPL IV，合并后的设计以 Indiana 方案为主，因为它的实现（Gregor 在 GCC 上做的原型 ConceptGCC）远远领先。2008 年 9 月，措辞文档 [[N2773]] 连同一整套给标准库加概念的文档一起并入了 C++0x 工作草案。

### 它长什么样

下面是 C++0x 概念的写法（据 HOPL IV §6.2 与 [[N2773]]）。这套语法从未进入正式标准，今天的编译器不接受。

```cpp
// 历史语法（C++0x 概念），不是合法的 C++
concept EqualityComparable<typename T> {          // 概念 = 一组操作
    bool operator==(const T& x, const T& y);
    bool operator!=(const T& x, const T& y) { return !(x == y); }
}

concept BidirectionalIterator<typename Iter>      // 显式精化
    : ForwardIterator<Iter> { /* ... */ }

concept_map EqualityComparable<int> {}            // 显式声明 int 满足该概念

template<class T>
concept_map ForwardIterator<T*> {                 // 给 T* 补上关联类型
    typedef T value_type;
}

auto concept LessThanComparable<typename T> {     // auto：允许自动匹配
    bool operator<(const T&, const T&);
}

template<typename T>
    requires LessThanComparable<T>
const T& min(const T& x, const T& y) { return x < y ? x : y; }
```

这里有四个后来都被放弃的设计：

- **概念映射**（concept map）显式声明一个类型怎样满足一个概念，还能补上缺失的操作或类型。`int*` 没有成员 `value_type`，就靠 `concept_map ForwardIterator<T*>` 补上。Indiana 一方认为显式声明能防止语法上碰巧匹配、语义上无关的误用；Texas 一方认为不增加功能的 concept map 只是负担。折中办法是 `auto concept`，由概念的定义者决定能否自动匹配（HOPL IV §6.2.3）。
- **显式精化**：像类派生一样用 `: ForwardIterator<Iter>` 逐层搭建概念层次。HOPL IV §6.2.1 认为这很僵硬，现实中的概念往往不是严格的层次。
- **定义检查**（definition checking）：受约束模板的函数体按约束检查，用了约束里没有的操作就报错。为了能调用还没加约束的旧模板，又加了 `late_check` 块，在块内放弃检查（HOPL IV §6.2.4）。
- **公理**（axiom）：在概念里写语义性质，比如全序的传递性。编译器可以用它们做假设，但不检验它们（[[N2887]]）。

### 为什么撤出

HOPL IV §6.2.6 列出了 2009 年积累的问题，可以归成三类：

- 意见没有统一。要不要普遍要求 concept map、精化关系是声明还是推算，始终没有共识。
- 规格太大。核心语言部分约 91 页，描述标准库用了约 125 个概念。
- 实现代价高。支持概念的编译器比不支持的慢 10 倍以上；仍有受约束代码生成的机器码不如无约束模板的例子。concept map 与 `late_check` 组合起来，还会让同一个类型在程序不同位置呈现不一致的视图。

还有一个更根本的困难。把概念写成带具体类型的签名，就要决定参数按值、按 `const&` 还是按 `&&` 传，`x.f(y)` 还是 `f(x, y)`。每多一个参数，组合数就翻几倍，匹配的负担最后落在类型作者和 concept map 作者身上（HOPL IV §6.2.1）。

2009 年春，邮件组上一场讨论把问题摆到了明处：标准库的一个组件，如果按某种设计实现，普通用户就得自己写 concept map（[[N2906]] 引言）。Stroustrup 随后写了 [[N2906]]，主张把所有概念改成自动匹配，让 concept map 变得罕见。他的论证是：名义（nominal）类型系统靠显式声明捕获错误，结构（structural）类型系统靠结构相同就能互换使用；模板本质上偏结构，这是泛型编程在 C++ 中成功的原因，而当时的设计为了安全过度偏向了名义一端。同期也有方向相反、坚持显式建模的提案。

2009 年 7 月，委员会决定把概念从 C++0x 中撤出（HOPL IV §6.2；Herb Sutter 当月的 trip report）。Sutter 把它描述为进度上的取舍：设计仍在变，先按期发布其余特性。Stroustrup 在 Dr. Dobb's 上发表的 *The C++0x "Remove Concepts" Decision* 说，他倾向于修正后再发布，但在撤出和维持原样之间，他也投票赞成撤出。

## 三、第二次设计：概念是谓词（2009–2016）

### 从用户的角度重来

撤出之后，Stroustrup、Dos Reis 与 Andrew Sutton 重新设计（HOPL IV §6.3）。2011 年，Alex Stepanov 召集了一次为期一周的会议，从用户的角度问：一套恰当约束的 STL 算法应该长什么样？结果是 [[N3351]] *A Concept Design for the STL*（2012）。据 Stroustrup 回忆，今天 `requires` 表达式里列出表达式的写法就是在这次会议上提出的，基础是 2003 年的使用模式（HOPL IV §6.3.3）。

2013 年的 [[N3580]] *Concepts Lite* 把新设计概括为：用谓词约束模板实参；约束保证模板的使用正确，而不是定义正确；支持基于约束的重载；没有运行期开销。和 C++0x 概念对比：

| | C++0x 概念 | Concepts Lite 之后 |
|---|---|---|
| 概念是什么 | 一组伪签名和关联类型 | 编译期谓词 |
| 类型如何满足概念 | concept map，或 `auto concept` | 总是由编译器计算 |
| 概念之间的强弱 | 显式精化 | 由约束的逻辑结构推算 |
| 模板定义 | 按约束检查 | 不检查 |
| 公理 | 有 | 没有 |

今天 [[temp.constr.atomic#3]] 说，原子约束是否满足就看替换后的表达式是否为 `true`。没有任何声明能让一个类型满足或不满足概念，这就是 C++0x 那场显式与隐式之争的结论。

### 不做定义检查的取舍

不做定义检查是最有争议的决定。设计者估计大约九成的好处来自使用点检查，而受约束模板的作者多半是专家（HOPL IV §6.3.1）。Stroustrup 还列举了不做定义检查的实际好处：

- 开发初期需求往往不完整，部分约束可以先用起来；
- 有定义检查时，给函数加一行调试输出或统计代码，都得先改约束；
- 受约束模板可以调用无约束的旧模板，旧代码可以逐步迁移。

反对者担心的是将来。Matt Calabrese 在 2016 年的 [[P0240R0]] 中引用 Douglas Gregor 的意见：不带定义检查就把概念放进标准，意味着以后再也加不上定义检查。这个担忧至今成立：今天的受约束模板仍按 C++98 的两阶段规则检查（[[temp.res]]、[[topics/two-phase-lookup]]），约束只决定模板能不能被选中，不限制函数体能用哪些操作。

```cpp run title="no_definition_check.cpp" ok
#include <iterator>

template<std::forward_iterator I>
void advance_by(I& p, int n) {
    p += n;   // 约束里没有 +=，定义处不报错
}
// 用 std::list 的迭代器实例化时才会出错
```

HOPL IV §6.3.1 用的也是这个例子。Stroustrup 的立场是，如果将来加入定义检查，必须同时提供绕开它的机制，而 C++0x 的 `late_check` 不够用。

### Concepts TS 与它的写法

这套设计先以技术规范的形式发布：ISO/IEC TS 19217:2015 *C++ Extensions for Concepts*，GCC 6 用 `-fconcepts` 实现。TS 里有几种后来被删掉的写法：

```cpp
// 历史语法（Concepts TS），不是合法的 C++20
template<typename T>
concept bool Sequence = Has_begin<T> && Has_end<T>;   // 变量形式，必须写 bool

template<typename T>
concept bool Sortable() { return /* ... */; }         // 函数形式，用时写 Sortable<T>()

void sort(Sortable& c);                               // 自然写法：概念名当类型用，
                                                      // 函数自动成为模板
Mergeable{In1, In2, Out}                              // 模板引入符
Out merge(In1, In1, In2, In2, Out);
```

`concept bool` 的来历是：Concepts Lite 起初把概念做成返回 `bool` 的 `constexpr` 函数，C++14 有了变量模板后又允许变量形式。两种形式并存，用户就得记住每个概念是哪种，才知道要不要写括号（HOPL IV §6.3.6）。

2016 年初，委员会讨论过把 TS 并入 C++17，没有通过。从文档能确认的反对理由有三类：缺少定义检查及其对将来的影响、缺少一个概念化的标准库（[[P0240R0]]），以及 TS 发布不到一年、实现和使用经验不足（Sutter 2016 年 3 月的 trip report）。

## 四、C++20：删掉了什么，留下了什么

### 概念成为一等实体

2017 年的 [[P0587R0]]（Richard Smith、James Dennett）指出：概念都是布尔的，`concept bool` 是多余的；把概念建模成函数或变量，会把实现细节泄漏进接口（`C<X>` 还是 `C<X>()`），甚至让取概念地址成为可能。同年并入 C++20 草案的 [[P0734R0]] 采纳了这些意见，概念只剩一种形式：

<div class="compare" markdown="1">

```cpp
// Concepts TS
template<typename T>
concept bool Sortable() { ... }

template<typename T>
  requires Sortable<T>()
void sort(T&);
```

```cpp
// C++20
template<typename T>
concept Sortable = ...;

template<typename T>
  requires Sortable<T>
void sort(T&);
```

</div>

所以今天的概念只能定义在命名空间作用域，不能有关联约束，不会被实例化，也不能特化（[[temp.concept#3]]–[[temp.concept#5]]）。它不再借用函数模板或变量模板的外壳。

### 包含关系为什么只认源码位置

TS 判断两个原子约束是否相同，靠比较它们的记号序列，而且会把约束一路拆到 `requires` 表达式内部的每一条要求。[[P0587R0]] 和 Smith 与 Sutton 的 [[P0717R1]] 指出这既昂贵又脆弱：两个命名空间里写法相同、含义不同的概念会被当成等价；一次无害的重构可能改变重载结果。

[[P0717R1]] 提出的模型是：两个原子约束只有出自同一处源码时才可能相同。这成了今天的 [[temp.constr.atomic#2]]，同时 `requires` 表达式整体只算一个原子约束。后果是，想让一个概念比另一个更强，必须在定义里写出那个概念的名字：

<div class="compare" markdown="1">

```cpp run error
template<class T> concept HasF =
  requires(T t) { t.f(); };
template<class T> concept HasFG =
  requires(T t) { t.f(); t.g(); };

template<class T> requires HasF<T>
int pick(T) { return 1; }
template<class T> requires HasFG<T>
int pick(T) { return 2; }

struct S { void f(); void g(); };
int x = pick(S{});
// error: 二义。两个 requires 表达式
// 各是一个原子约束，互不包含
```

```cpp run ok
template<class T> concept HasF =
  requires(T t) { t.f(); };
template<class T> concept HasFG =
  HasF<T> && requires(T t) { t.g(); };

template<class T> requires HasF<T>
int pick(T) { return 1; }
template<class T> requires HasFG<T>
int pick(T) { return 2; }

struct S { void f(); void g(); };
int x = pick(S{});  // OK：选第二个
int main() { return x == 2 ? 0 : 1; }
```

</div>

C++0x 用 `: ForwardIterator<Iter>` 声明精化；C++20 没有精化语法，精化就是在定义里用 `&&` 合取另一个概念，再由规范化（[[temp.constr.normal]]）展开、由包含规则（[[temp.constr.order]]）推算。这仍是由编译器计算概念关系，只是依据从语义收窄到了源码结构。第一节 `my_advance` 的例子能工作，正是因为标准库的迭代器概念都是这样逐层写出名字的。

### 简写语法：为什么是 `Sortable auto&`

TS 的自然写法 `void sort(Sortable& c)` 没有随 [[P0734R0]] 进入 C++20。Tom Honermann 的 [[P0696R1]] 指出了它的问题：`void f(X x)` 是不是模板，取决于 `X` 是类型还是概念。这个差别影响转发引用、函数内 `static` 变量是否每个实例一份、定义能否放在头文件之外，而读代码的人和 diff 工具都看不出来。Stroustrup 的 [[P0694R0]] 则为它辩护，认为它对大约三分之二的 STL 算法是最简单的写法。

之后两年出现了一批互不兼容的替代语法。2018 年的 [[P1141R2]] 由此前多个方案的作者共同署名，给出的规则是：凡是能写 `auto` 的地方都能写 `Concept auto`，意思是像 `auto` 一样推导，再额外检查约束。

<div class="compare" markdown="1">

```cpp
// Concepts TS：看不出 f 是模板
void sort(Sortable& c);
Sortable x = make();
```

```cpp
// C++20：auto 标明这里有推导
void sort(Sortable auto& c);
Sortable auto x = make();
```

</div>

Stroustrup 支持了这个妥协，但在 HOPL IV §6.4 中写道，他认为概念名后面的 `auto` 是多余的。模板引入符 `Mergeable{In1, In2, Out}` 没有再获得共识。

[[P1141R2]] 还规定 `template<C T>` 里的 `T` 一定是类型形参，`template<C... T>` 表示 `(C<T> && ...)` 而不是 `C<T...>`。于是 C++20 给函数模板加约束有四种写法，对调用者效果相同，但作为声明并不等价，不能混用来重声明同一个模板（[[temp.over.link]]）：

```cpp run title="four_forms.cpp" ok
#include <concepts>

template<class T> concept Sortable = requires(T& c) { c.begin(); c.end(); };

template<class C> requires Sortable<C> void sort1(C&);   // requires 子句
template<Sortable C> void sort2(C&);                     // 类型约束
template<class C> void sort3(C&) requires Sortable<C>;   // 尾置 requires 子句
void sort4(Sortable auto&);                              // 缩写函数模板

std::integral auto twice(std::integral auto x) { return x * 2; }   // 也可用于返回类型

int main() { std::integral auto n = twice(21); return n == 42 ? 0 : 1; }
```

复合要求也在同一时期定型。[[P1084R2]] 规定 `{ E } -> C<Args>;` 的意思是 `C<decltype((E)), Args>`；[[P1452R2]] 删掉了 `{ E } -> Type;` 这种形式：它表示可隐式转换为 `Type`，与 `-> Concept` 的语义不统一。今天要写 `-> std::same_as<int>` 或 `-> std::convertible_to<int>`，把意思说明白（[[expr.prim.req]]）。

### 库概念：满足和建模是两回事

标准库概念来自 Ranges 的工作，2018 年以 [[P0898R3]] *Standard Library Concepts* 加入 `<concepts>`。它们起初用 CamelCase 命名（`ForwardIterator`），2019 年的 [[P1754R1]] 统一改成 `forward_iterator` 这样的标准库风格；HOPL IV §6.5 记录的一个动机是 CamelCase 名字开始和其他库的标识符冲突。

C++0x 的公理在库概念里留下了影子。语法上**满足**（satisfy）一个概念，与语义上[[g:models-concept|建模]]它是两回事：建模还要求符合规格中的语义要求，比如 [[concepts.equality]] 的保持相等性。编译器只检查满足；程序依赖建模而实参只满足不建模时，程序非良构但不要求诊断（[[res.on.requirements#2]]）。这与当年公理的定位一样：可以当作假设，但不由编译器检验。

## 五、C++26：两处补充

### 折叠表达式约束能比较强弱

在 C++20 中，`(C<Ts> && ...)` 这样的折叠表达式整体是一个原子约束，两个这样的约束无法比较谁更强。Corentin Jabot 的 [[P2963R3]] 引入了[[g:fold-expanded-constraint]]：规范化时折叠表达式成为一种新的约束形式，满足按元素逐个检查（[[temp.constr.fold]]），包含关系也能穿过它比较（[[temp.constr.order#1]]）。

```cpp run title="fold_expanded.cpp" ok
#include <concepts>

template<class... Ts> requires (std::integral<Ts> && ...)
int g(Ts...) { return 1; }

template<class... Ts> requires (std::signed_integral<Ts> && ...)
int g(Ts...) { return 2; }

int main() { return g(1, 2) == 2 ? 0 : 1; }   // C++26：选第二个
```

用 `clang++ -std=c++20` 编译，Clang 报告调用二义；`-std=c++2c` 下选第二个重载。

### 概念可以作为模板实参

C++20 的概念不能当模板实参传递，想写一个"所有类型都满足某个概念"的概念，只能对每个概念各写一遍。[[P2841R7]] 允许模板形参本身是一个概念或变量模板（语法见 [[temp.param]]）。约束里的概念名依赖模板形参时，规范化要等概念确定之后才能展开，这种约束叫[[g:concept-dependent-constraint]]（[[temp.constr.normal#1]]）。

```cpp run title="concept_tparam.cpp" ok
#include <concepts>

template<template<class> concept C, class... Ts>
concept all_satisfy = (C<Ts> && ...);

static_assert(all_satisfy<std::integral, int, long>);
static_assert(!all_satisfy<std::integral, int, double>);

int main() {}
```

## 六、今天的规则里留下的痕迹

| 今天的规则 | 位置 | 来由 |
|---|---|---|
| 类型满足概念不需要任何声明 | [[temp.constr.atomic#3]] | C++0x 的 concept map 之争；[[N2906]] 主张全部自动匹配 |
| 精化没有专门语法，强弱由约束结构推算 | [[temp.constr.normal]]、[[temp.constr.order]] | C++0x 的显式精化被认为过于僵硬 |
| 原子约束只有出自同一处源码才相同；`requires` 表达式不拆分 | [[temp.constr.atomic#2]] | [[P0587R0]]、[[P0717R1]] 对 TS 记号比较的批评 |
| 概念只有一种定义形式，不能特化或约束 | [[temp.concept]] | TS 的函数形式与 `concept bool` 被删除 |
| 受约束模板的函数体不按约束检查 | [[temp.res]] | Concepts Lite 有意推迟定义检查 |
| 缩写函数模板必须写 `C auto` | [[dcl.fct#23]] | 自然写法之争与 [[P1141R2]] 的妥协 |
| `{ E } -> C<Args>` 意为 `C<decltype((E)), Args>`，没有 `-> Type` | [[expr.prim.req]] | [[P1084R2]]、[[P1452R2]] |
| 满足但不建模的库概念导致 IFNDR | [[res.on.requirements]] | 语义要求与 C++0x 公理一样不由编译器检验 |
| 折叠表达式约束能参与包含比较 | [[temp.constr.fold]] | C++26，[[P2963R3]] |
| 约束中的概念名可以是模板形参 | [[temp.constr.normal]] | C++26，[[P2841R7]] |

## 七、时间线

| 年份 | 事件 |
|---|---|
| 1987 前后 | Stroustrup 尝试给模板设计接口，没有成功（HOPL IV §6.1） |
| 2003 | 使用模式的概念设计（[[N1510]]）；`enable_if` 发表 |
| 2006 | Indiana 与 Texas 方案合并（[[N2081]]） |
| 2008 | C++0x 概念并入工作草案（[[N2773]]） |
| 2009 | 概念从 C++0x 撤出 |
| 2013 | Concepts Lite（[[N3580]]） |
| 2015 | Concepts TS 发布 |
| 2016 | 未并入 C++17 |
| 2017 | 去掉 `bool`、函数形式和自然写法后并入 C++20 草案（[[P0734R0]]） |
| 2018 | `Concept auto` 简写语法（[[P1141R2]]）；标准库概念（[[P0898R3]]） |
| 2019 | 库概念改名为 standard_case（[[P1754R1]]） |
| 2020 | C++20 发布 |
| 2024–2025 | 折叠展开约束（[[P2963R3]]）；概念模板形参（[[P2841R7]]），均进入 C++26 |

## 八、还没解决的问题

定义检查至今没有。截至 2026 年 10 月，WG21 文档索引里没有以受约束模板的定义检查为主题、正在审议的提案。

诊断质量是另一个持续的话题，例如 [[P2429R0]] *Concepts Error Messages for Humans*（2022）。标准只规定程序是否良构，诊断的具体形式由实现决定，所以这类改进主要发生在编译器里。

## 参考资料

- Bjarne Stroustrup. *The Design and Evolution of C++*. Addison-Wesley, 1994. §15.4。
- Bjarne Stroustrup. *Evolving a language in and for the real world: C++ 1991–2006*. HOPL III, 2007. §8.3.3。
- Bjarne Stroustrup. *Thriving in a Crowded and Changing World: C++ 2006–2020*. Proc. ACM Program. Lang. 4, HOPL, 2020. §6。
- Bjarne Stroustrup. *The C++0x "Remove Concepts" Decision*. Dr. Dobb's, 2009 年 7 月。
- Herb Sutter. *Trip Report: Exit Concepts, Final ISO C++ Draft in ~18 Months*. 2009-07-21；以及 2016-03-11 的冬季会议报告。
- [[N1510]] Stroustrup, *Concept checking – A more abstract complement to type checking*, 2003。
- [[N2773]] Gregor, Stroustrup, Widman, Siek, *Proposed Wording for Concepts (Revision 9)*, 2008。
- [[N2906]] Stroustrup, *Simplifying the use of concepts*, 2009。
- [[N3580]] Sutton, Stroustrup, Dos Reis, *Concepts Lite: Constraining Templates with Predicates*, 2013。
- [[P0240R0]] Calabrese, *Why I want Concepts, but why they should come later rather than sooner*, 2016。
- [[P0587R0]] Smith, Dennett, *Concepts TS revisited*；[[P0717R1]] Smith, Sutton, *Semantic constraint matching for concepts*（2017）。
- [[P0696R1]] Honermann, *Remove abbreviated functions and template-introduction syntax from the Concepts TS*, 2017。
- [[P1141R2]] Voutilainen et al., *Yet another approach for constrained declarations*, 2018。
- [[P2963R3]] Jabot, *Ordering of constraints involving fold expressions*, 2024。
- [[P2841R7]] Jabot, Ažman, Touton, Tong, *Concept and variable-template template-parameters*, 2025。
