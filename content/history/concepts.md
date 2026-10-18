---
title: 概念（concepts）三十年
summary: 从 D&E 里对受约束模板的设想，到 C++0x 概念在 2009 年被整体撤出，再到 Concepts Lite、Concepts TS、C++20 的合并与语法妥协，以及 C++26 的折叠展开约束和概念模板形参；今天 [temp.constr] 里的满足、规范化与包含规则，大多能在这段历史里找到来由。
status: draft
order: 10
papers: N1510, N2081, N2773, N2906, N3580, P0734R0, P1141R2, P0898R3, P2963R3, P2841R7
related: temp.constr, temp.constr.order, temp.concept, expr.prim.req, concepts, temp.res, topics/concepts, topics/two-phase-lookup
tags: 概念, 约束, 泛型编程, SFINAE, 标准化历史
updated: 2026-10-18
---

C++20 的概念（concepts）是一个等了很久的特性。按 Stroustrup 本人的说法，他在 1987 年前后就尝试给模板设计像样的接口，没有成功（HOPL IV §6.1）；第一版标准化的概念设计在 2008 年进入 C++0x 工作草案，2009 年又被整体撤出；之后用了八年才以另一种设计进入 C++20 工作草案。期间有两条完全不同的技术路线、一份技术规范（TS）、一次在全体会议上未获通过的合并动议，以及一场持续到 2018 年底的语法争论。

这一页按时间顺序讲这段历史，重点放在每个阶段的设计取舍上，因为今天标准里的许多规则正是这些取舍的结果。例如：

- 为什么类型满足概念不需要任何声明（没有 concept map）？
- 为什么包含关系（subsumption）只认同一处源码写出的原子约束，`requires` 表达式内部不再拆分？
- 为什么受约束模板的函数体不按约束检查（没有定义检查），错误仍然在实例化时才报？
- 为什么缩写函数模板必须写成 `Sortable auto&`，而不是 `Sortable&`？

读这一页之前，最好对 [[topics/concepts]] 有个大致印象；规则本身请回到 [[temp.constr]]、[[temp.constr.order]]、[[temp.concept]]、[[expr.prim.req]] 和库概念 [[concepts]]。

!!! note "关于出处"
    本页的历史论断都标了出处。HOPL III 指 Stroustrup 的 *Evolving a language in and for the real world: C++ 1991–2006*（2007），HOPL IV 指 *Thriving in a Crowded and Changing World: C++ 2006–2020*（2020），D&E 指 *The Design and Evolution of C++*（1994）。HOPL 论文是当事人的回顾，其中对他人观点和会议气氛的描述属于一方视角，本页引用时会注明"据 Stroustrup 回忆"。WG21 文档号链接到 wg21.link。

## 一、前史：没有接口的模板（1987–2003）

### 1.1 三个目标只做到了两个

Stroustrup 在 HOPL IV §6.1 回顾，他设计模板时想要三样东西：

1. 足够通用，不只能表达设计者想得到的用法；
2. 与手写代码相比零开销，例如 `vector` 要能在时间和空间上与 C 数组竞争；
3. 良好定义的接口，类型检查和重载能力要与非泛型代码相当。

当时没有人知道怎样同时做到这三点，于是 C++ 得到了前两样：模板是图灵完备的，生成的代码性能很好，但接口只是编译期的鸭子类型（duck typing）。他认为第三点的缺失正是后来错误信息极其糟糕的原因，原话是 "spectacularly bad error messages for incorrect calls"（HOPL IV §6）。

D&E 在讨论模板时用了大约三页篇幅（§15.4）讨论模板实参的约束，其中一种做法是让构造函数去使用模板实参，借此在编译期触发检查（D&E §15.4.2，据 HOPL III §8.3.3 的转述）。另一种更常见的设想是像 Eiffel 那样要求实参派生自某个基类，即 `template<class T : Base>` 一类的写法。Stroustrup 在 2003 年的 [[N1510]] 中写到，这类基于签名的方案自 1986 年前后就多次被考虑，也多次被否决：它要求实参类型与模板约定的类型在操作签名上精确匹配，处理不了隐式转换、重载和混合类型运算，而这些恰恰是 C++ 泛型代码的日常。

所以 C++98 的模板是无约束的。标准库对模板实参的要求（"输入迭代器"、"可小于比较"之类）只写在标准正文的要求表里，编译器并不读它们。HOPL III §8.3.3 的说法是 "compilers don't read manuals"。

### 1.2 库作者的补救：约束类

在语言之外，社区发展出了约束类（constraints class）的技巧：写一个在实例化时把所需操作逐一用一遍的类模板，把错误提前到算法入口处。HOPL III §8.3.3 给出的例子大致如下，Boost 的 Concept Check Library 是这一思路的系统化版本（HOPL IV §6.1 提到它基于 Jeremy Siek 的工作）。

```cpp run title="constraints_class.cpp" ok
// C++98 风格的约束类：只要 T 不支持这些操作，实例化 Forward_iterator<T> 就会出错
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
    Forward_iterator<In>();                 // 在函数体开头"检查"
    while (first != last && !pred(*first)) ++first;
    return first;
}

bool even(int x) { return x % 2 == 0; }
int main() { int a[] = {1, 2, 3}; return *find_if2(a, a + 3, even) == 2 ? 0 : 1; }
```

这种做法的局限也很明显。检查写在定义里而不是声明里，调用者看不到；它不能参与重载决议，只能让错误早一点、短一点出现；而且要在各家编译器上都给出好的错误信息并不容易（HOPL III §8.3.3）。

### 1.3 SFINAE 与 `enable_if`

另一条路线利用了模板实参推导的一条规则：在函数模板的声明中替换模板实参时，如果产生了无效的类型或表达式，这个候选只是被丢弃，不算错误。这就是 [[g:sfinae]]（substitution failure is not an error）；Boost.Core 的 `enable_if` 文档在介绍这一术语时引用的是 Vandevoorde 与 Josuttis 的 *C++ Templates: The Complete Guide*（2002）。Järvi、Willcock、Lumsdaine 等人在 2003 年把它包装成 `enable_if`（论文 *Concept-controlled polymorphism*，GPCE 2003；Boost.Core 文档），C++11 把 `std::enable_if` 收入标准库。

```cpp run title="enable_if.cpp" ok
#include <iterator>
#include <list>
#include <type_traits>

template<class It>
using iter_cat = typename std::iterator_traits<It>::iterator_category;

template<class It,
         std::enable_if_t<std::is_base_of_v<std::random_access_iterator_tag, iter_cat<It>>, int> = 0>
void my_advance(It& it, int n) { it += n; }

template<class It,
         std::enable_if_t<!std::is_base_of_v<std::random_access_iterator_tag, iter_cat<It>>, int> = 0>
void my_advance(It& it, int n) { while (n--) ++it; }

int main() {
    int a[4]{};
    int* p = a;       my_advance(p, 2);   // 第一个重载
    std::list<int> l{1, 2, 3};
    auto i = l.begin(); my_advance(i, 2); // 第二个重载
}
```

`enable_if` 能做到约束类做不到的事：它参与重载决议。代价是写法晦涩，两个重载的条件必须由程序员手工写成互斥的，否则就会二义；而且约束藏在默认模板实参或返回类型里，还改变了函数模板的模板形参个数。Ville Voutilainen 在 2016 年的 [[P0225R0]] 中逐条列举了这些问题，作为尽快引入概念的理由。

HOPL IV §6.4 末尾的评价是：概念迟到的这些年里，基于 traits 和 `enable_if` 的临时设计大量扩散，一代程序员是在低层、无类型的元编程里成长起来的。这是 Stroustrup 的个人评价。

## 二、C++0x 概念（2003–2009）

### 2.1 两条路线

Stroustrup 回忆，概念一词来自 Alex Stepanov 的泛型编程工作，Stepanov 在 1990 年代末的讲座中用它指称对模板实参的要求，并写进了 Dehnert 与 Stepanov 2000 年的文章；Stepanov 大约在 2002 年第一个呼吁把概念做成 C++ 语言特性（HOPL III §8.3.3，HOPL IV §6.1）。

2003 年，Stroustrup 与 Gabriel Dos Reis 发表了一组论文，提出用使用模式（use pattern）来描述约束，也就是列出对某类型应当合法的表达式，而不是列出函数签名（[[N1510]]、[[N1522]]、[[N1536]]）。HOPL IV §6.1 总结说，这些论文已经包含了后来几乎所有的要素：概念是编译期谓词；多参数概念；值参数概念；`template<Iterator Iter>` 这样的简写；`void f(Comparable&)` 这样的简化写法；`auto` 作为最弱的约束。有意思的是，它们没有提出一般的 requires 子句。

HOPL IV §6.2 把 2004 年前后的局面描述为两个独立的设计，常被称为 Indiana 方案和 Texas 方案（主要成员分别来自印第安纳大学和德州农工大学）：

| | Indiana 方案 | Texas 方案 |
|---|---|---|
| 主要成员（据 HOPL IV） | Andrew Lumsdaine、Douglas Gregor、Jeremy Siek | Bjarne Stroustrup、Gabriel Dos Reis |
| 概念的表示 | 一组操作（伪签名）与关联类型，近似 Haskell 类型类 | 编译期类型谓词，用使用模式描述 |
| 类型如何满足概念 | 需要程序员显式声明类型建模（model）了概念 | 由编译器计算，不需要声明 |
| 代表文档 | [[N1758]]、[[N1849]] | [[N1782]]、[[N1886]] |

Stroustrup 当时认为两种方式理论上等价，后来承认在 C++ 的具体语言设计里它们并不等价（HOPL IV §6.2）。WG21 的共识文化鼓励合并提案而不是让两个方案最终对决，于是两组人合写了联合提案：2006 年 6 月的 [[N2042]] 和 9 月的修订版 [[N2081]]，作者都是 Douglas Gregor 和 Bjarne Stroustrup；同年发表在 OOPSLA 的论文 *Concepts: Linguistic Support for Generic Programming in C++* 也是这一联合设计的学术版本（HOPL IV §6.2）。

据 HOPL IV，合并后的设计主要以 Indiana 方案为基础，因为它的实现远远领先、参与者更多。剩下的问题看起来只是让编译器足够快、生成高效的代码、处理好重载和隐式转换。Stroustrup 的评价是，这个决定花掉了三年的艰苦工作和大量争议。

### 2.2 设计的样子

下面的代码是 C++0x 概念的写法，取自 HOPL IV §6.2 与 [[N2773]]。**这是从未进入正式标准的历史语法**，今天的编译器不接受。

```cpp
// 历史语法（C++0x 概念，2009 年撤出），不是合法的 C++
concept EqualityComparable<typename T> {          // 概念 = 一组操作
    bool operator==(const T& x, const T& y);
    bool operator!=(const T& x, const T& y) { return !(x == y); }
}

concept BidirectionalIterator<typename Iter>      // 显式精化（refinement）
    : ForwardIterator<Iter> { /* ... */ }

concept_map EqualityComparable<int> {}            // 显式声明 int 建模该概念

template<class T>
concept_map ForwardIterator<T*> {                 // 非侵入地给 T* 补上关联类型
    typedef T value_type;
}

auto concept LessThanComparable<typename T> {     // auto：允许隐式匹配
    bool operator<(const T&, const T&);
}

template<typename T>
    requires LessThanComparable<T>                // 早期草案里这个关键字是 where
const T& min(const T& x, const T& y) { return x < y ? x : y; }
```

几个要点：

- **概念映射**（concept map）显式声明一个类型怎样满足一个概念，还能顺便补上缺失的操作或关联类型。`int*` 没有成员 `value_type`，就靠 `concept_map ForwardIterator<T*>` 补上（HOPL III §8.3.3）。
- 显式与隐式之争。Indiana 一方认为显式总是好的，可以防止语法上碰巧匹配、语义上毫无关系的误用；Texas 一方认为，不增加任何功能的 concept map 只是负担。折中办法是允许概念的定义者写 `auto concept`，表示可以自动匹配（HOPL IV §6.2.3）。在 [[N2773]] 中，这一形式在措辞里正式称为 auto concepts（此前叫 implicit concepts）。
- 精化关系是显式声明的，像类派生一样逐层搭建概念的层次。HOPL IV §6.2.1 认为这带来了严重的不灵活：现实中的概念往往不是严格的层次结构。
- **定义检查**（definition checking）：受约束模板的函数体按约束检查，用了约束里没有的操作就报错（HOPL IV §6.2.4）。为了让受约束模板能调用尚未加约束的旧模板，又加入了 `late_check` 块，在块内放弃检查（[[N2773]] 中的措辞是 late-checked-block）。
- **公理**（axiom）可以写在概念里，表达语义性质，例如全序的反对称、传递、完全性。[[N2773]] 的语法里已有 *axiom-definition*；2009 年的 [[N2887]] 进一步阐述了公理的语义。按 Stroustrup 的回忆，公理设计者明确拒绝让编译器去检验公理，这一点在委员会里很难被接受（HOPL IV §6.2.5）。

### 2.3 ConceptGCC 与进入工作草案

Douglas Gregor 在 GCC 上实现了原型编译器 ConceptGCC。[[N2081]] 说该提案的大部分内容已在 ConceptGCC 中实现，并邀请大家用它积累经验。

措辞文档从 2007 年 3 月的 [[N2193]] 开始，经过多次修订，到 2008 年 9 月的第 9 版 [[N2773]]。2008 年 9 月的 San Francisco 会议把 [[N2773]] 连同一整套给标准库加概念的文档（[[N2774]] *Foundational Concepts*、[[N2758]] 迭代器概念、[[N2776]] 容器等）一起并入了工作草案，这在会后的编辑报告 [[N2799]] 中有逐项记录。Herb Sutter 在 2009 年的 trip report 中也写到，2008 年秋季会议后发布的委员会草案（CD）已经大量使用概念。

### 2.4 问题积累

HOPL IV §6.2.6 列出了 Stroustrup 在 2009 年看到的问题，摘要如下：

- 显式还是隐式建模（是否普遍要求 concept map），仍然没有共识；
- 概念之间的关系是显式声明还是由编译器推算，也没有共识；
- 仍有受约束代码生成的机器码不如无约束模板的例子；
- 很难写出能覆盖 C++ 惯用的隐式转换和重载情形的概念；
- 复杂的 concept map 与 `late_check` 组合起来，会让同一个类型在程序不同位置呈现不一致的视图，相当于不易察觉的类型系统漏洞；
- 规格膨胀：核心语言部分约 91 页，不含库；描述标准库用了约 125 个概念，其中 103 个属于 STL；
- 支持概念的编译器比只支持无约束模板的编译器慢 10 倍以上。

最后一条还附带一段回忆：据 Stroustrup 说，有主要编译器厂商私下告诉他，如果开启概念的编译器比旧编译器慢 20% 以上，他们将不得不反对。这是当事人的回忆，没有公开文档可以核对。

HOPL IV 还讨论了一个更根本的困难：把概念定义为一组带具体类型的操作，就要决定参数按值、按左值引用、按 const 引用还是按右值引用传递。一个参数有四种选择，两个参数就是十六种；`x.f(y)` 与 `f(x, y)` 两种调用风格也要二选一或都写。设计逐渐倾向于照搬声明的参数类型，把匹配的负担推给类型作者和 concept map 的作者（HOPL IV §6.2.1）。

### 2.5 "Joe Coder" 讨论与 N2906

2009 年春天，标准委员会的邮件组（reflector）上有一场长讨论。起因是 Howard Hinnant 设计一个工具组件时面临选择：一种设计要求相当多的普通用户编写 concept map，另一种设计不那么优雅，但完全避开 concept map。讨论因此被称为 "Are concepts required of Joe Coder?"（[[N2906]] 引言；HOPL IV §6.2.6）。

Stroustrup 随后写了 [[N2906]] *Simplifying the use of concepts*（2009-06-21）。它的摘要提出：

- 让 concept map 变得罕见；
- 把所有概念都变成隐式（自动）的，并相应地把标准库概念全部改为隐式；
- 用显式精化（explicit refinement）这一更有针对性的手段，处理那些仅在语义上不同、因而必须区分的概念；
- 允许成员函数或自由函数任一种形式满足概念中的关联函数要求，从而省掉许多空的 concept map。

[[N2906]] 的论证从类型系统的光谱出发：名义（nominal）类型系统靠显式声明来捕获错误，结构（structural）类型系统靠结构相同即可互换使用来提高互操作性；模板本质上偏结构，这是泛型编程在 C++ 中成功的原因之一，也是错误信息差的根源。Stroustrup 认为当时的概念为了安全过度偏向了名义一端，原话是 "We have overreacted to the problems of structural typing."（[[N2906]]）。同期还有方向相反的文档，例如 Abrahams 与 Dawes 的 [[N2916]] *Intentional Concept Mapping* 和 Abrahams 与 Gregor 的 [[N2918]] *Exported Concept Maps*，可见显式建模在当时仍有坚定的支持者。

### 2.6 Frankfurt，2009 年 7 月

2009 年 7 月的 Frankfurt 会议上，委员会以大比数决定把概念从 C++0x 工作草案中撤出（HOPL IV §6.2；会议纪要见 [[N2920]]）。会后的编辑报告 [[N2961]] 写明：除两处（其中之一是随机数部分）外，概念已从工作草案中删除；撤出前最后一版带概念的工作草案是 [[N2914]]。会前，Martin Tasker 的 [[N2893]] *The long pole gets longer* 已经从进度角度指出概念是整个标准时间表上的关键路径。

关于撤出的原因，几份当事人的记录侧重不同：

- Herb Sutter 的 trip report（*Trip Report: Exit Concepts, Final ISO C++ Draft in ~18 Months*，2009-07-21）把它描述为项目管理上的取舍：概念的设计仍在变化，委员会选择先按期发布其余已完成的特性，同时为将来重新引入概念留出余地。
- Stroustrup 在 Dr. Dobb's 发表的 *The C++0x "Remove Concepts" Decision*（2009 年 7 月）中列出了三个选项：修正后发布（fix and ship，他倾向的选项，工作包括去掉显式概念、加入显式精化）、撤出后发布（yank and ship）、维持原样（status quo）。他写道，在撤出与维持原样两者之间，他也投票赞成撤出，并说 "I prefer a setback to a likely disaster."。
- HOPL IV §6.2.6 回顾说，会上的讨论几乎只围绕能否及时达成共识，结论是不太可能；发言者都重申想要概念，投票只表明这个设计还没有准备好标准化。他的进一步判断是，委员会成员对想要什么样的概念并没有共同的设计目标。

Stroustrup 在 HOPL IV 中总结了三条教训：过于看重早期实现，而没有先把需求、约束、使用模式和简单的实现模型想清楚；有些分歧是理念层面的，无法靠折中解决，应当尽早识别；没有任何一组设施能满足大型专家委员会的所有愿望而不膨胀。这些是他个人的结论，本页照录，不作评判。

## 三、Concepts Lite 与 Concepts TS（2009–2016）

### 3.1 从用户出发重新设计

撤出之后，Stroustrup、Dos Reis 与 Andrew Sutton 几乎立刻开始重新设计（HOPL IV §6.3）。他们的出发点有三条：概念必须有语义含义；概念的数量应当相对少；概念应当是基础性的，而不是最小化的。

2011 年，在 Andrew Lumsdaine 的推动下，Alex Stepanov 在 Palo Alto 召集了为期一周的会议，参会者包括 C++0x 概念工作的多数核心成员和 Sean Parent。会议从用户的角度出发：一套恰当约束的 STL 算法理想中应该长什么样？会后形成的文档是 [[N3351]] *A Concept Design for the STL*（Stroustrup、Sutton，2012-01）。HOPL IV 认为，后来的 Concepts TS 和 C++20 概念都直接来自这次会议。据 Stroustrup 回忆，`requires` 表达式里那种列出表达式的写法是他在这次会议上当场提出的，基础是 2003 年的使用模式思想（HOPL IV §6.3.3）。

### 3.2 Concepts Lite：只检查使用，不检查定义

2013 年 3 月，Sutton、Stroustrup、Dos Reis 提交了 [[N3580]] *Concepts Lite: Constraining Templates with Predicates*。它的引言把新设计概括为：用谓词约束模板实参；约束用来保证模板的使用正确，而不是模板定义正确；支持基于约束的重载和类模板特化；在使用点给出更好的诊断；没有运行期开销，也不增加编译时间。[[N3580]] 同时说明，所有主要特性都已在 GCC 4.8 的一个分支上实现。

与 C++0x 概念相比，变化可以列成一张表（据 HOPL IV §6.3 与 [[N3580]]）：

| | C++0x 概念 | Concepts Lite / TS |
|---|---|---|
| 概念是什么 | 一组伪签名和关联类型 | 编译期谓词（起初是 `constexpr` 函数） |
| 类型如何满足概念 | concept map，或 `auto concept` 自动匹配 | 总是由编译器计算，没有 concept map |
| 概念之间的关系 | 显式精化 | 由约束的逻辑结构推算（包含关系） |
| 模板定义 | 按约束检查，`late_check` 例外 | 不检查 |
| 公理 | 有 | 没有（HOPL IV 说是为了不拖延设计而暂缓） |

不做定义检查是最有争议的决定。HOPL IV §6.3.1 记录了设计者当时的估计：大约九成的好处来自使用点检查，受约束模板的作者多半是专家，可以暂时不要定义检查。Stroustrup 承认这是一个粗略的估计，同时列举了他们在实践中发现的不做定义检查的好处：

- 开发初期往往还不知道完整的需求，部分约束可以先用起来；
- 有定义检查时，给函数加一行调试输出、统计或追踪代码，都要先修改约束，接口很难稳定；
- 没有定义检查，旧模板可以逐步迁移；有定义检查时，受约束模板无法调用无约束模板，因为不知道后者会用到哪些操作。

据 HOPL IV 引述，2014 年起任 EWG 主席的 Ville Voutilainen 说过 "I cannot support any proposal for concepts that includes definition checking."。Dos Reis 还设计了一门实验语言 Liz，在其中实现了包括定义检查在内的 Concepts TS 式设施（HOPL IV §6.3.1）。

研究小组 SG8（Concepts）由 Andrew Sutton 担任主席（HOPL IV §3.2）。规格在 2013 至 2015 年间几经修订：[[N3701]]、[[N3819]]、[[N3889]]、[[N3929]]，然后成为 TS 工作草案 [[N4040]]、[[N4205]]，再到 [[N4377]]（PDTS）和 [[N4549]]。

### 3.3 Concepts TS 的样子

ISO/IEC TS 19217:2015 *C++ Extensions for Concepts* 于 2015 年 11 月发布（ISO 目录记录的版本日期为 2015-11，现状态为已撤回）。GCC 6 起用 `-fconcepts` 提供实现（HOPL IV §6.3）。下面是 TS 中的几种写法，**同样是未进入 C++20 的历史语法**：

```cpp
// 历史语法（Concepts TS，ISO/IEC TS 19217:2015），不是合法的 C++20
template<typename T>
concept bool Sequence = Has_begin<T> && Has_end<T>;   // 变量形式，必须写 bool

template<typename T>
concept bool Sortable() { return /* ... */; }         // 函数形式，使用时要写 Sortable<T>()

void sort(Sortable& c);                               // 自然写法（terse/natural syntax）：
                                                      // 参数类型位置写概念名，函数自动成为模板

Mergeable{In1, In2, Out}                              // 概念名引入符（template introducer）
Out merge(In1, In1, In2, In2, Out);
```

HOPL IV §6.3.6 讲了 `concept bool` 的来历：Concepts Lite 起初把概念做成返回 `bool` 的 `constexpr` 函数；C++14 有了变量模板后，又允许变量形式。两种形式并存时，用户必须知道某个概念是哪种形式，才能决定要不要写括号，这很快变得不实用。显式写出 `bool` 本来就是多余的，设计者为了不动语法而保留了它，后来这反倒成了反对者的论据之一。

### 3.4 Jacksonville，2016 年 2–3 月：没有进入 C++17

2016 年初，围绕是否把 Concepts TS 并入 C++17，出现了两份针锋相对的文档：

- Ville Voutilainen 的 [[P0225R0]] *Why I want Concepts, and why I want them sooner rather than later* 认为，概念作为语言特性已经可以发布，不必等到标准库完成概念化；他认为对标准库施加概念不会导致概念的设计改变。
- Matt Calabrese 的 [[P0240R0]] *Why I want Concepts, but why they should come later rather than sooner* 认为，标准库的概念化版本本身就是检验设计、示范用法所必需的；更重要的是，TS 的设计很可能使将来无法以有意义的方式加入定义检查，除非做破坏性的修改。文中引用了 Douglas Gregor 的一段回复（经其许可），其中一句是 "putting concepts into the C++ standard without separate type checking of template definitions means that we will never get separate type checking"。

在 2016 年 2–3 月的 Jacksonville 会议上，Voutilainen 提出把 TS 的语言特性并入 C++17 的动议。据 HOPL IV §6.3.8，尽管 EWG 此前在同一周做过支持的表决，全体会议的结果是 25 票赞成、31 票反对、8 票弃权，未获通过。Herb Sutter 的 trip report（2016-03-11）对这一结果的描述是：TS 发布还不到一年，多数人希望再等一两年，积累实际编译器发布和实地使用的经验，少数人则认为它已经可以进入 C++17。

Stroustrup 在 HOPL IV 中对这次表决有自己的解读，他也提到当时对自然写法的强烈反对，以及有人用只适用于 C++0x 概念的理由反对 TS。这些属于一方的回忆。从文档层面能确认的反对理由主要有三类：缺少定义检查及其对未来的影响（[[P0240R0]]），缺少一个概念化的标准库（[[P0240R0]]），以及实现与使用经验不足（Sutter 2016 年 trip report）。

## 四、C++20：合并、修订与语法妥协（2017–2019）

### 4.1 合并前的修订

C++17 进入收尾阶段后，委员会重新审视 Concepts TS。两份文档尤其重要，因为它们直接塑造了今天的规则：

- Richard Smith 与 James Dennett 的 [[P0587R0]] *Concepts TS revisited*（2017-02）指出：所有概念都是布尔的，`concept bool` 是多余的；把概念建模为函数或变量会把实现细节泄漏进接口（`C<X>` 与 `C<X>()`），也带来取概念地址之类的荒谬可能；概念重载会造成认知上的二义；TS 把约束一路拆分到 `requires` 表达式内部的每个语句，导致包含关系依赖于两处约束在文本上恰好重复，一次重构就可能改变重载结果。
- Richard Smith 与 Andrew Sutton 的 [[P0717R1]] *Semantic constraint matching for concepts*（2017-07）指出，TS 用模板等价规则（比较记号序列）判断两个原子约束是否相同，代价高且脆弱：两个命名空间里写法相同、含义不同的概念会被视为等价，写法不同、含义相同的概念又互不包含。它提出的模型是：两个原子约束只有出自同一处源码构造时才可能相同。

同年 6 月，Stroustrup 的 [[P0694R0]] *Function declarations using concepts* 为自然写法辩护，认为它对许多泛型函数仍是最短、最简单的写法，统计下来大约可用于三分之二的 STL 算法；Tom Honermann 的 [[P0696R1]] *Remove abbreviated functions and template-introduction syntax from the Concepts TS* 则主张删除缩写函数和模板引入符，理由包括：`void f(X x)` 是不是模板取决于 `X` 是不是概念，这会影响转发引用、函数内静态变量和定义能否放在头文件之外，而代码审阅和 diff 工具看不出这种差别。[[P0696R1]] 于 2017 年 7 月 11 日在 Toronto 会议上报告。

### 4.2 Toronto，2017 年 7 月：P0734R0 进入 C++20 草案

2017 年 7 月的 Toronto 会议通过了 [[P0734R0]] *Wording Paper, C++ extensions for Concepts*（Andrew Sutton），作为 CWG 第 11 号动议并入工作草案（编辑报告 [[N4688]]）。Herb Sutter 在 trip report 中称它是第一个进入 C++20 草案的主要语言特性，并说明这次合并留下了 TS 的大部分内容，但没有包含模板引入符和自然写法，EWG 同意在相关设计问题解决后继续讨论简写语法。

[[P0734R0]] 里的概念已经是今天的形式：`template<typename T> concept C = ...;`，没有 `bool`，没有函数形式。把它与 [[P0587R0]]、[[P0717R1]] 对照，可以看出今天 [[temp.concept]] 与 [[temp.constr]] 的若干规则是怎么来的：

- 概念只能定义在命名空间作用域，不能有关联约束，不会被实例化，不能显式实例化、显式特化或部分特化（[[temp.concept#3]]–[[temp.concept#5]]）。这与 [[P0587R0]] 的主张一致：概念应当是一等实体，而不是借用函数模板或变量模板来表示。
- 原子约束的同一性按出处判断：只有出自同一个表达式的同一次出现、参数映射又相同时才算相同（[[temp.constr.atomic#2]]）。[[P0717R1]] 的受众一栏写的是 for posterity，它记录的正是这个模型的理由。
- `requires` 表达式整体是一个原子约束，内部不再拆分。所以想让一个概念包含另一个，必须在定义里显式地写出那个概念的名字。

```cpp run title="subsume_by_name.cpp" error
template<class T> concept HasF  = requires(T t) { t.f(); };
template<class T> concept HasFG = requires(T t) { t.f(); t.g(); };  // 没有提到 HasF

template<class T> requires HasF<T>  int pick(T) { return 1; }
template<class T> requires HasFG<T> int pick(T) { return 2; }

struct S { void f(); void g(); };
int x = pick(S{});   // error: 二义。两个 requires 表达式各是一个原子约束，互不包含
```

```cpp run title="subsume_by_name_ok.cpp" ok
template<class T> concept HasF  = requires(T t) { t.f(); };
template<class T> concept HasFG = HasF<T> && requires(T t) { t.g(); };  // 通过名字精化

template<class T> requires HasF<T>  int pick(T) { return 1; }
template<class T> requires HasFG<T> int pick(T) { return 2; }

struct S { void f(); void g(); };
int x = pick(S{});   // OK：HasFG 规范化后含有 HasF 的原子约束，后者更受约束
int main() { return x == 2 ? 0 : 1; }
```

C++0x 用 `concept B : A` 显式声明精化；C++20 没有专门的精化语法，精化关系体现为在概念定义里用 `&&` 合取另一个概念，再由 [[temp.constr.normal]] 的规范化把 concept-id 展开、由 [[temp.constr.order]] 的包含规则推算。这延续了 Texas 路线由编译器计算概念关系的思路，只是计算的依据从语义收窄到了源码结构。

### 4.3 简写语法之争与 P1141R2

自然写法被搁置之后，2017–2018 年间出现了一批互不兼容的替代方案，例如 Herb Sutter 的 [[P0745R1]] *Concepts in-place syntax*、Thomas Köppe 的 [[P0807R0]] *An Adjective Syntax for Concepts*、Köppe 与 Hubert Tong 的 [[P1013R1]] *Explicit concept expressions*、Erich Keane 等人的 [[P0782R0]]、Corentin Jabot 的 [[P0873R0]]、Jakob Riedle 的 [[P0791R0]] *Concepts are Adjectives, not Nouns*，以及 Stroustrup 回应各类建议的 [[P0956R0]] 和他的折中方案 [[P1079R0]] *A minimal solution to the concepts syntax problems*。HOPL IV §6.4 回忆，2018 年中 Stroustrup 的方案和 Sutter 的方案都在 EWG 获得了多数支持，彼此却不兼容，这一僵局促成了 EWG 主席 Voutilainen 牵头的第三种方案。

那就是 [[P1141R2]] *Yet another approach for constrained declarations*，作者多达十五人，几乎涵盖了此前各方案的提出者。它的原则是 auto 能出现的地方，`Concept auto` 也能出现，语义是像 `auto` 一样推导，再额外检查约束。它提出三件事：

1. 约束的 `auto`：用于函数形参（由此产生缩写函数模板）、返回类型、变量和非类型模板形参；
2. 收紧 `template<C T>` 的含义：它总是声明类型形参，`template<C auto N>` 总是声明非类型形参，此处的 `C` 必须是类型概念；
3. 修改形参包的含义：`template<C... T>` 表示 `(C<T> && ...)`，而不是 `C<T...>`。

[[P1141R2]] 说明，R1 中让 `auto` 可省略的放宽方案和修改 `-> Concept auto` 含义的部分，EWG 决定不提出。2018 年 11 月的 San Diego 会议把它作为 CWG 第 15 号动议并入草案（编辑报告 [[N4792]]）。同一次会议还通过了 Walter Brown 与 Casey Carter 的 [[P1084R2]]，把复合要求 `{ E } -> Concept<Args>;` 的含义定为 `Concept<decltype((E)), Args>`。2019 年 7 月的 Cologne 会议又通过了 Hubert Tong 的 [[P1452R2]]，删除了 `{ E } -> Type;` 这种形式（[[N4829]] CWG 第 18 号动议）。这些规则今天都在 [[expr.prim.req]] 中。

于是 C++20 中给函数模板加约束有四种写法。它们对调用者的效果相同，但作为声明并不等价，不能混用来重声明同一个模板（见 [[temp.over.link]]）：

```cpp run title="four_forms.cpp" ok
#include <concepts>

template<class T> concept Sortable = requires(T& c) { c.begin(); c.end(); };

template<class C> requires Sortable<C> void sort1(C&);   // requires 子句
template<Sortable C> void sort2(C&);                     // 类型约束（type-constraint）
template<class C> void sort3(C&) requires Sortable<C>;   // 尾置 requires 子句
void sort4(Sortable auto&);                              // 缩写函数模板（P1141R2）

std::integral auto twice(std::integral auto x) { return x * 2; }   // 约束的 auto 也可用于返回类型

int main() { std::integral auto n = twice(21); return n == 42 ? 0 : 1; }
```

Stroustrup 支持了这个妥协，但在 HOPL IV 中写道，他认为概念名后面的 `auto` 是多余的，偏离了让泛型编程成为普通编程的目标。概念名引入符（`Mergeable{In1, In2, Out}`）则没有再获得共识（HOPL IV §6.4）。

### 4.4 标准库概念与 Ranges

库这一侧的工作一直是与语言特性并行的。Eric Niebler、Sean Parent、Andrew Sutton 的 [[N4128]] *Ranges for the Standard Library*（2014）开启了基于概念的范围库设计，随后形成 Ranges TS 工作草案（[[N4560]]、[[N4651]]、[[N4685]] 等），并以 ISO/IEC TS 21425:2017 发布。Ranges TS 包含了一套基础库概念，Voutilainen 在 [[P0225R0]] 中也提到了这一点。

C++20 分两步吸收这些成果：

- 2018 年 6 月 Rapperswil 会议通过 Casey Carter 与 Eric Niebler 的 [[P0898R3]] *Standard Library Concepts*，新增 `<concepts>` 头文件（[[N4764]] LWG 第 28 号动议）；
- 2018 年 11 月 San Diego 会议通过 [[P0896R4]] *The One Ranges Proposal*（[[N4792]] LWG 第 25 号动议），把 Ranges TS 的主体并入 C++20。

最初的库概念用 CamelCase 命名（`ForwardIterator`、`EqualityComparable`）。2019 年 7 月 Cologne 会议通过 [[P1754R1]] *Rename concepts to standard_case for C++20, while we still can*，作者包括 Herb Sutter、Casey Carter、Gabriel Dos Reis、Eric Niebler、Bjarne Stroustrup、Andrew Sutton、Ville Voutilainen，把它们统一改为 `forward_iterator`、`equality_comparable` 这样的标准库风格（[[N4829]] LWG 第 11 号动议）。HOPL IV §6.5 记录了改名的另一个动机：CamelCase 的库概念开始与其他库的同名标识符冲突。

库概念保留了 C++0x 公理的一点影子：语法上满足（satisfy）一个概念，与在语义上建模（[[g:models-concept]]）它是两回事。[[res.on.requirements#1]] 规定，模板实参建模一个概念，当且仅当它满足该概念并且符合规格中的全部语义要求；若程序的有效性依赖于建模而实际只满足不建模，程序 IFNDR（[[res.on.requirements#2]]）。语义要求写在标准正文里（如 [[concepts.equality]] 对保持相等性的要求），编译器不检查，这与当年公理的定位相近：可以作为假设，但不由编译器检验。

同一时期还有一些语言细节的修订，例如 [[P1616R1]] *Using unconstrained template template parameters with constrained templates*（Cologne 2019，[[N4829]] CWG 第 10 号动议）。

## 五、C++26：补上两块缺口

C++26 对概念做了两处扩展，分别针对 C++20 的两个限制：折叠表达式写出的约束不参与包含比较；概念不能作为模板实参传递。

### 5.1 折叠展开约束（P2963R3）

在 C++20 中，`(C<Ts> && ...)` 这样的折叠表达式整体是一个原子约束。两个重载即使一个用 `std::integral`、一个用 `std::signed_integral` 折叠，也无法比较谁更受约束，调用就会二义。Corentin Jabot 的 [[P2963R3]] *Ordering of constraints involving fold expressions* 引入了[[g:fold-expanded-constraint]]：规范化时，形如 `(E && ...)` 或 `(E || ...)` 的约束成为一种新的约束形式，它的满足按元素逐个检查（[[temp.constr.fold]]），包含关系也能穿过它比较（[[temp.constr.order#1]] 的第 (1.3) 项）。该提案在 2024 年 6 月的 St. Louis 会议通过（编辑报告 [[N4987]]）。

```cpp run title="fold_expanded.cpp" ok
#include <concepts>

template<class... Ts> requires (std::integral<Ts> && ...)
int g(Ts...) { return 1; }

template<class... Ts> requires (std::signed_integral<Ts> && ...)
int g(Ts...) { return 2; }

int main() { return g(1, 2) == 2 ? 0 : 1; }   // C++26：第二个更受约束；在 C++20 规则下二义
```

用 `clang++ -std=c++20` 编译上例，Clang 报告调用二义；`-std=c++2c` 下选择第二个重载。

### 5.2 概念模板形参与变量模板模板形参（P2841R7）

[[P2841R7]] *Concept and variable-template template-parameters*（Corentin Jabot、Gašper Ažman、James Touton、Hubert Tong）允许模板形参本身是一个概念或变量模板。2025 年 2 月的 Hagenberg 会议通过了它（编辑报告 [[N5009]] CWG 第 7 号投票）。规范化规则因此多了一种[[g:concept-dependent-constraint]]：当约束里的概念名本身依赖于模板形参时，规范化要等到概念确定之后才能展开（[[temp.constr.normal#1]] 的第 (1.4.1) 项）。语法见 [[temp.param]]。

```cpp run title="concept_tparam.cpp" ok
#include <concepts>

template<template<class> concept C, class... Ts>
concept all_satisfy = (C<Ts> && ...);

static_assert(all_satisfy<std::integral, int, long>);
static_assert(!all_satisfy<std::integral, int, double>);

template<template<class> concept C>
struct checker { template<class T> static constexpr bool ok = C<T>; };
static_assert(checker<std::floating_point>::ok<double>);

int main() {}
```

## 六、今天的规则里留下的痕迹

把上面的历史与当前草案对照，可以整理出下面这张表。左列是今天的规则，右列是它的来由。

| 今天的规则 | 位置 | 历史来由 |
|---|---|---|
| 类型满足概念不需要任何声明，满足与否完全由约束表达式求值决定 | [[temp.constr.atomic#3]] | C++0x 的 concept map 与 `auto concept` 之争；[[N2906]] 主张全部隐式；Concepts Lite 起彻底去掉 concept map |
| 精化不靠专门语法，由规范化后的约束结构推算包含关系 | [[temp.constr.normal]]、[[temp.constr.order]] | C++0x 的显式精化被认为过于僵硬（HOPL IV §6.2.1） |
| 原子约束只有出自同一处源码时才可能相同；`requires` 表达式不拆分 | [[temp.constr.atomic#2]] | [[P0587R0]]、[[P0717R1]] 对 TS 记号比较规则的批评 |
| 概念不能被约束、特化或实例化，只有变量式的一种定义形式 | [[temp.concept]] | TS 的函数形式与 `concept bool` 被 [[P0587R0]] 批评后删除 |
| 受约束模板的定义不按约束检查，错误在实例化时报出 | [[temp.res]] | Concepts Lite 有意推迟定义检查（HOPL IV §6.3.1）；[[P0240R0]] 对此的担忧 |
| 缩写函数模板必须写 `C auto`；`template<C T>` 中 `T` 一定是类型 | [[dcl.fct#23]]、[[temp.param]] | 自然写法之争与 [[P1141R2]] 的妥协 |
| `{ E } -> C<Args>` 意为 `C<decltype((E)), Args>`；没有 `-> Type` 形式 | [[expr.prim.req]] | [[P1084R2]]、[[P1452R2]] |
| 满足但不建模的库概念导致 IFNDR | [[res.on.requirements]] | 语义要求只写在正文里，与 C++0x 公理一样不由编译器检验 |
| 折叠表达式约束能参与包含比较 | [[temp.constr.fold]] | C++26，[[P2963R3]] |
| 约束中的概念名可以是模板形参 | [[temp.constr.normal]]、[[temp.param]] | C++26，[[P2841R7]] |

!!! history "关于没有定义检查"
    今天的规则仍然沿用 C++98 的两阶段检查：受约束模板的函数体里，不依赖模板形参的构造在定义时检查，依赖的构造在实例化时检查（见 [[temp.res]] 与 [[topics/two-phase-lookup]]）。约束只影响模板能否被选中，不改变函数体里的名字查找，也不限制函数体能用哪些操作。下面的 `advance_by` 只要求前向迭代器却用了 `+=`，定义本身可以通过编译，问题要等到用 `std::list` 的迭代器实例化时才暴露。HOPL IV §6.3.1 用的是同样的例子。

```cpp run title="no_definition_check.cpp" ok
#include <iterator>

template<std::forward_iterator I>
void advance_by(I& p, int n) {
    p += n;   // 约束里没有 +=；定义处不报错，用不支持 += 的迭代器实例化时才出错
}
```

## 七、时间线

| 年份 | 事件 | 文档 |
|---|---|---|
| 约 1987 | Stroustrup 尝试给模板设计接口未果，模板以无约束形式进入 C++ | HOPL IV §6.1 |
| 1994 | D&E §15.4 讨论模板实参约束 | D&E |
| 1998 | C++98：模板无约束，要求只写在标准库的要求表中 | — |
| 2000–2003 | 约束类技巧流行，Boost Concept Check Library；`enable_if` 发表 | HOPL III §8.3.3；Boost.Core 文档 |
| 2003 | Stroustrup、Dos Reis 提出基于使用模式的概念 | [[N1510]]、[[N1522]]、[[N1536]] |
| 2005 | Indiana 与 Texas 两条路线的提案 | [[N1758]]、[[N1782]]、[[N1849]]、[[N1886]] |
| 2006 | Gregor 与 Stroustrup 的联合提案；ConceptGCC | [[N2042]]、[[N2081]] |
| 2007–2008 | 措辞文档多次修订 | [[N2193]] → [[N2773]] |
| 2008 年 9 月 | San Francisco 会议把概念及库的概念化并入 C++0x 工作草案 | [[N2773]]、[[N2774]]、[[N2799]] |
| 2009 年 6 月 | Stroustrup 提出简化概念用法 | [[N2906]] |
| 2009 年 7 月 | Frankfurt 会议决定从 C++0x 撤出概念 | [[N2920]]、[[N2961]] |
| 2011–2012 | Palo Alto 会议，以 STL 为对象从用户角度重新设计 | [[N3351]] |
| 2013 年 3 月 | Concepts Lite | [[N3580]] |
| 2015 年 11 月 | Concepts TS 发布（ISO/IEC TS 19217:2015） | [[N4549]] |
| 2016 年 2–3 月 | Jacksonville 会议未把 TS 并入 C++17 | [[P0225R0]]、[[P0240R0]] |
| 2017 年 7 月 | Toronto 会议把概念并入 C++20 草案，不含自然写法和模板引入符 | [[P0734R0]]、[[N4688]] |
| 2018 年 6 月 | 标准库概念 | [[P0898R3]]、[[N4764]] |
| 2018 年 11 月 | `Concept auto` 简写语法；复合要求的新语义；Ranges 并入 | [[P1141R2]]、[[P1084R2]]、[[P0896R4]]、[[N4792]] |
| 2019 年 7 月 | 库概念改名为 standard_case；删除 `-> Type` 形式 | [[P1754R1]]、[[P1452R2]]、[[N4829]] |
| 2020 | C++20 发布，概念成为标准的一部分 | — |
| 2024 年 6 月 | 折叠展开约束 | [[P2963R3]]、[[N4987]] |
| 2025 年 2 月 | 概念模板形参与变量模板模板形参 | [[P2841R7]]、[[N5009]] |

## 八、现状与未来

截至本页更新时（2026 年 10 月），可以从文档确认的情况如下。

定义检查仍然没有。在本站缓存的 WG21 文档索引中，没有找到以受约束模板定义检查为主题、正在审议的提案。相关的公开讨论主要是 2016 年的 [[P0240R0]]（以及其中引用的 Gregor 意见）和 HOPL IV §6.3.1。Stroustrup 在 HOPL IV 中的立场是：如果将来加入定义检查，必须同时设计一个能绕开它的机制，以满足迁移和插入调试、统计代码的需要，C++0x 的 `late_check` 并不够用。这只是一种可能性的陈述，不代表委员会的计划。

仍有提案在扩展概念的表达力，例如 Corentin Jabot 的 [[P2970R0]] *Partial application of concepts in template arguments*（2025-05），以及 Hewill Kang 的 [[P4281R0]] *Type Aliases in Requires-Expressions*（2026-06）。本页只按标题列出，不推测它们的审议结果。

诊断质量是另一个持续的话题，例如 Sy Brand 的 [[P2429R0]] *Concepts Error Messages for Humans*（2022）。标准只规定程序是否良构，诊断的具体形式由实现决定，这类工作更多地体现在编译器上。

## 参考资料

### Stroustrup 的回顾

- Bjarne Stroustrup. *The Design and Evolution of C++*. Addison-Wesley, 1994. §15.4。
- Bjarne Stroustrup. *Evolving a language in and for the real world: C++ 1991–2006*. HOPL III, 2007. §8.3.3 Concepts。
- Bjarne Stroustrup. *Thriving in a Crowded and Changing World: C++ 2006–2020*. Proc. ACM Program. Lang. 4, HOPL, 2020. §6 Concepts。
- Bjarne Stroustrup. *The C++0x "Remove Concepts" Decision*. Dr. Dobb's, 2009 年 7 月。

### 会议报告与编辑报告

- Herb Sutter. *Trip Report: Exit Concepts, Final ISO C++ Draft in ~18 Months*. 2009-07-21（Frankfurt）。
- Herb Sutter. *Trip report: Winter ISO C++ standards meeting*. 2016-03-11（Jacksonville）。
- Herb Sutter. *Trip report: Summer ISO C++ standards meeting (Toronto)*. 2017-07-15。
- Herb Sutter. *Trip report: Fall ISO C++ standards meeting (San Diego)*. 2018-11-13。
- 编辑报告：[[N2799]]（San Francisco 2008）、[[N2961]]（Frankfurt 2009）、[[N4688]]（Toronto 2017）、[[N4764]]（Rapperswil 2018）、[[N4792]]（San Diego 2018）、[[N4829]]（Cologne 2019）、[[N4987]]（St. Louis 2024）、[[N5009]]（Hagenberg 2025）。

### C++0x 概念

- [[N1510]] Stroustrup, *Concept checking – A more abstract complement to type checking*, 2003。
- [[N1758]] Siek, Gregor et al., *Concepts for C++0x*, 2005；[[N1782]] Stroustrup, Dos Reis, *A concept design (Rev. 1)*, 2005。
- [[N2081]] Gregor, Stroustrup, *Concepts (Revision 1)*, 2006。
- [[N2773]] Gregor, Stroustrup, Widman, Siek, *Proposed Wording for Concepts (Revision 9)*, 2008。
- [[N2887]] Dos Reis, Stroustrup, Meredith, *Axioms: Semantics Aspects of C++ Concepts*, 2009。
- [[N2906]] Stroustrup, *Simplifying the use of concepts*, 2009。

### Concepts Lite、TS 与 C++20

- [[N3351]] Stroustrup, Sutton, *A Concept Design for the STL*, 2012。
- [[N3580]] Sutton, Stroustrup, Dos Reis, *Concepts Lite: Constraining Templates with Predicates*, 2013。
- ISO/IEC TS 19217:2015 *C++ Extensions for Concepts*；最终文本 [[N4549]]。
- [[P0225R0]] Voutilainen；[[P0240R0]] Calabrese（2016）。
- [[P0587R0]] Smith, Dennett, *Concepts TS revisited*；[[P0717R1]] Smith, Sutton, *Semantic constraint matching for concepts*（2017）。
- [[P0734R0]] Sutton, *Wording Paper, C++ extensions for Concepts*, 2017。
- [[P1141R2]] Voutilainen et al., *Yet another approach for constrained declarations*, 2018。
- [[P0898R3]] Carter, Niebler, *Standard Library Concepts*；[[P0896R4]] Niebler, Carter, Di Bella, *The One Ranges Proposal*（2018）。
- [[P1754R1]] Sutter et al., *Rename concepts to standard_case for C++20, while we still can*, 2019。

### C++26

- [[P2963R3]] Jabot, *Ordering of constraints involving fold expressions*, 2024。
- [[P2841R7]] Jabot, Ažman, Touton, Tong, *Concept and variable-template template-parameters*, 2025。
