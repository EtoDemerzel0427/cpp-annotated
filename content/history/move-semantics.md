---
title: 移动语义与值类别的演化
summary: 从 C 继承来的 lvalue/rvalue，到 C++98 允许的复制消除、2002 年的移动语义提案、右值引用的几次返工、glvalue/xvalue/prvalue 的命名、C++17 保证的复制消除，再到 C++20/23/26 一步步放宽和收紧的隐式移动与返回规则，以及 2025 年进入又移出 C++26 的平凡重定位
status: draft
order: 80
since: c++11
papers: N1377, N1385, N1690, N2118, N2812, N2844, N2855, N3050, N3053, N3055, N3153, N3203, P0135R1, P1825R0, P2266R3, P2748R5, P1144R13, P2786R13, P3920R0
related: basic.lval, class.temporary, class.copy.elision, dcl.init.ref, class.copy.ctor, class.copy.assign, unique.ptr, topics/value-categories, topics/special-members-and-elision, topics/dangling-references
tags: 移动语义, 右值引用, 值类别, 复制消除, 隐式移动, 平凡重定位
updated: 2026-10-18
---

今天的 C++ 程序员每天都在写 `std::move`，读标准时会碰到 glvalue、xvalue、prvalue、move-eligible、implicitly movable entity 这一整套术语。这套术语不是一次设计出来的。它的底子是 C 语言的 lvalue，2002 年为了解决复制代价问题加上了右值引用，2009 年发现右值引用绑定规则有安全漏洞而返工，2010 年为了让标准措辞自洽临时引入了五个值类别名称，2016 年又借这套名称重新定义了 prvalue 的含义。此后的三个标准版本都在修改同一段规则：`return x;` 什么时候可以移动。

本页按时间顺序讲这段历史，重点放在每一次改动解决了什么问题、留下了什么尾巴，以及哪些代码在不同标准版本下行为不同。规则本身的逐段释义在 [[basic.lval]]、[[class.temporary]]、[[class.copy.elision]]、[[dcl.init.ref]] 和 [[stmt.return]]；判定表达式值类别的方法见 [[topics/value-categories]]，特殊成员函数何时隐式生成见 [[topics/special-members-and-elision]]。

本页的代码示例都在本机 Clang 23 上用不同的 `-std=` 选项验证过。凡是行为随版本变化的例子，代码块不加判定标记，判定写在行尾注释里。

## 一、起点：C 的 lvalue 和 C++98 的两分法

lvalue 和 rvalue 这两个词比 C 还老。Stroustrup 在 2010 年的说明文章 *"New" Value Terminology* 中回顾，这对术语由 Christopher Strachey 为 CPL 引入；Dennis Ritchie 描述 C 时只用了 lvalue，认为"是 lvalue"和"不是 lvalue"两类就够了，C++ 的早期定义（1986 年的 *The C++ Programming Language*、1990 年的 ARM）也照此处理（Stroustrup, *"New" Value Terminology*）。

C++98 正式使用了 lvalue 和 rvalue 两个词：每个表达式要么是 lvalue，要么是 rvalue。这个两分法在当时够用，因为它只需要回答两个问题：

- 能不能对它取地址、能不能出现在内置赋值的左边；
- 能不能绑定到非 const 的左值引用 `T&`。

第二条规则是后来一切故事的伏笔。C++98 规定 rvalue 不能绑定到 `T&`，只能绑定到 `const T&`（见 [[dcl.init.ref]]）。这条规则保护了程序员：把临时对象传给一个打算修改实参的函数，几乎总是错误。它的代价是，程序在类型系统里无法区分马上就要销毁的临时对象和调用者之后还会用到的 const 对象。两者都只能以 `const T&` 接收，所以函数拿到它们之后只能复制，不能把资源拿走。

## 二、C++98 已有的部分答案：复制消除

返回大对象的代价问题在 C++ 标准化之前就有人在处理。Stroustrup 在 HOPL IV 论文中写道，早在 1982 年，他就在编译器中实现过一种优化：把返回值直接分配在调用者的栈帧上。他同时指出，这只是一种优化手段，处理不了更复杂的 return 语句，用户需要的是一种保证：大量数据一定不会被复制（Stroustrup, HOPL IV §4.2.3）。

Stanley Lippman 在 2004 年的一篇博客中回顾了具名返回值优化（NRVO）的来历：Michael Tiemann 曾提议一种语言扩展，在函数头里给返回对象起名字，并认为没有这种语法编译器就无法稳定地做这个优化；其他人不同意，ARM 第 12 章的评注里讨论过这个问题。据 Lippman 的记述，Walter Bright 在 Zortech C++ 中首先在不加扩展的情况下实现了 NRVO，随后 Nancy Wilkinson 在下一个版本的 Cfront 中也实现了它，这被当作不需要语言扩展的证明（Lippman, *The Name Return Value Optimization*, 2004）。Tiemann 的扩展没有进入标准。

C++98 把这种做法写成了许可而不是义务：在满足条件时（从函数返回一个局部对象、用同类型的临时对象初始化另一个对象等），实现可以省略复制构造，即使复制构造函数有副作用。这是 as-if 规则之外少数几个允许改变可观察行为的地方。由于只是许可，标准仍然要求被省略的复制构造函数可访问、可调用。下面这个类型在 C++98 到 C++14 中都不能按值返回，因为复制构造函数是私有的，虽然实际上没有一个主流编译器会调用它：

```cpp run title="private-copy.cpp" std=c++14
struct NoMove {
    NoMove() {}
private:
    NoMove(const NoMove&);   // C++98 风格的"禁止复制"：私有且不定义
};

NoMove make() { return NoMove(); }   // C++98–C++14: error，复制构造函数不可访问
                                     // C++17 起: OK，见第九节
int main() {
    NoMove x = make();               // 同上
    (void)x;
}
```

Lippman 在同一篇文章里指出了这种许可的另一个问题：程序员无法从源码判断优化是否发生。用 Clang 的 `-fno-elide-constructors` 关掉可选的消除，就能看到 C++98 语义下理论上存在的两次复制：

```cpp run title="elision-count.cpp" flags="-std=c++14 -fno-elide-constructors"
#include <cstdio>
struct S {
    S()         { std::puts("ctor"); }
    S(const S&) { std::puts("copy"); }
    ~S()        { std::puts("dtor"); }
};
S make() { return S(); }
int main() { S s = make(); }
// -std=c++98/c++14 -fno-elide-constructors: ctor copy dtor copy dtor dtor
// -std=c++17       -fno-elide-constructors: ctor dtor
```

C++17 下这个选项不再起作用，原因在第九节。

## 三、C++11 之前的绕行办法

复制消除只覆盖了从函数返回和用临时对象初始化两种情形。把对象放进容器、容器扩容、交换两个对象、在函数之间转交所有权，这些操作在 C++98 中都只能复制。Stroustrup 在 HOPL IV 中把这个问题描述为大量显式使用指针的主要来源之一：为了把大块数据交出函数，人们在自由存储上分配它，再传递指针（HOPL IV §4.2.3）。库作者和用户发展出了几种绕行办法。

### swap 技巧

标准容器的成员函数 `swap` 只交换内部的几个指针，复杂度是常数。于是先在局部构造好、再 swap 进目标成了一种惯用法，`vector<T>(v).swap(v)` 也成了 C++98 中缩减容量的标准写法：

```cpp run title="swap98.cpp" std=c++98 ok
#include <vector>
#include <string>
std::vector<std::string> v;

void refill() {
    std::vector<std::string> tmp(1000, std::string(100, 'x'));
    v.swap(tmp);                              // 交换三根指针，不复制元素
}
void shrink() {
    std::vector<std::string>(v).swap(v);      // 经典的 shrink-to-fit 写法
}
int main() { refill(); shrink(); return v.size() == 1000 ? 0 : 1; }
```

swap 技巧要求类型提供高效的 swap，而且只适用于能写成交换的操作。容器自己扩容时仍然会逐个复制元素。

### auto_ptr

C++98 的 `std::auto_ptr` 用复制的语法实现了所有权转移：它的复制构造函数接受非 const 引用，并把源对象置空。为了让 `auto_ptr` 能从函数返回的临时对象构造（临时对象不能绑定到非 const 引用），标准库还需要一个辅助类 `auto_ptr_ref` 和一个转换函数。

```cpp run title="auto-ptr.cpp" std=c++98 ok
#include <memory>
#include <cassert>
int main() {
    std::auto_ptr<int> p(new int(1));
    std::auto_ptr<int> q = p;     // 看起来是复制，实际上转移了所有权
    assert(p.get() == 0);         // p 被置空
    assert(*q == 1);
}
```

复制语法却不满足复制语义，后果是 `auto_ptr` 不能安全地放进标准容器，也不能交给假定复制之后两者相等的泛型算法。N1377 专门指出，有了右值引用之后，`auto_ptr` 可以不靠 `auto_ptr_ref` 重新表述（[[N1377]]）。C++11 中 `auto_ptr` 被弃用，由 [[unique.ptr]] 取代；C++17 依据 [[N4190]] 将它删除。Clang 23 搭配 libc++ 在三种模式下的表现如下：`-std=c++98` 正常编译；`-std=c++11` 和 `-std=c++14` 给出弃用警告；`-std=c++17` 报告 `no member named 'auto_ptr' in namespace 'std'`。

### Mojo

2003 年 2 月，Andrei Alexandrescu 在 *C/C++ Users Journal* 的 Generic&lt;Programming&gt; 专栏发表了 *Move Constructors* 一文，提出一个纯库的方案 Mojo。它的做法是给类型加上一个 CRTP 基类，提供到 `mojo::temporary<T>` 和 `mojo::constant<T>` 两个包装类型的转换；由于 `temporary<T>` 派生自 `constant<T>`，重载决议会对非 const 临时对象优先选择接受 `temporary<T>` 的重载，从而在库层面区分出可以拿走资源的实参（Alexandrescu, *Move Constructors*, CUJ 2003-02）。这篇文章的参考文献引用了 N1377，并在致谢中提到 Hinnant、Dimov 和 Abrahams 正在提议在语言中加入移动构造函数。Boost 后来的移动库也在源码注释中注明受 Mojo 启发。

Mojo 证明了这种区分在库层面可行，同时也说明了代价：每个类型都要改写，重载数目翻倍，对用户来说规则复杂。

## 四、2002 年：移动语义提案 N1377 与转发问题 N1385

2002 年 9 月，Howard Hinnant、Peter Dimov 和 Dave Abrahams 提交了 [[N1377]]（*A Proposal to Add Move Semantics Support to the C++ Language*）。它的核心是一种新的引用类型 `A&&`，称为右值引用。论文对动机的表述很直接："Move semantics is mostly about performance optimization"（[[N1377]]）。

N1377 中有几条后来一直保留下来的设计：

- `A&&` 是一个与 `A&` 不同的类型，可以和它构成重载；
- 有名字的右值引用当作左值处理，没有名字的右值引用当作右值处理。这条规则保证一个对象在函数体内被用过一次后，不会在下一次使用时被意外移走；
- 要从左值移动，需要显式转换，例如 `static_cast<A&&>(x)` 或一个名为 `move` 的辅助函数；
- 模板实参推导做了扩展：形参为 `T&&` 时，左值实参把 `T` 推导为左值引用类型，这是后来完美转发的基础。

有一条设计后来被推翻了：按 N1377，左值可以绑定到右值引用，只是在同时存在 `A&` 重载时，重载决议优先选择后者。第六节会讲这条规则带来的问题。

`&&` 这个写法的来历，Stroustrup 在 HOPL IV 中记载：它是 John Spicer 在 2002 年与 Abrahams、Hinnant 的一次会面中提出的（HOPL IV §4.2.3）。

同一批邮件中，Dimov、Hinnant 和 Abrahams 还提交了 [[N1385]]（*The Forwarding Problem: Arguments*）。它把转发问题表述为：给定依赖于泛型参数 `a1, ..., an` 的表达式 `E(a1, ..., an)`，在当时的语言中写不出一个函数 `f`，使 `f(a1, ..., an)` 与 `E(a1, ..., an)` 等价。C++98 中两种常见的写法各有缺陷：

```cpp run title="forward98.cpp" std=c++98 error
void g(int&)       {}
void g(const int&) {}

template <class T> void wrap1(T& a)       { g(a); }   // 方案一：非 const 左值引用
template <class T> void wrap2(const T& a) { g(a); }   // 方案二：const 左值引用

int main() {
    int i = 0;
    wrap1(i);      // OK
    wrap1(42);     // error: 右值不能绑定到 T&（T 推导为 int）
    wrap2(i);      // 能编译，但 g 收到 const int&，选中了错误的重载
}
```

要在 C++98 中正确转发 n 个参数，需要为每个参数分别提供 `T&` 和 `const T&` 两个版本，共 2ⁿ 个重载。N1377 说明它的设计与 N1385 的方向兼容：借助右值引用和上面那条推导规则，一个 `T&&` 形参就能同时保留实参的 cv 限定和值类别。C++11 的最终形态是：

```cpp run title="forward11.cpp" std=c++11 ok
#include <utility>
#include <cstdio>
void g(int&)       { std::puts("g(int&)"); }
void g(const int&) { std::puts("g(const int&)"); }
void g(int&&)      { std::puts("g(int&&)"); }

template <class T> void wrap(T&& a) { g(std::forward<T>(a)); }

int main() {
    int i = 0; const int ci = 0;
    wrap(i);    // g(int&)
    wrap(ci);   // g(const int&)
    wrap(42);   // g(int&&)
}
```

`T&&` 在推导语境中的这种特殊行为，标准没有为它引入单独的类型。Sutter、Stroustrup 和 Dos Reis 在 [[N4164]]（2014 年）中提议把这种形参称为 forwarding reference（转发引用），C++17 起标准采用了这个术语。

## 五、2004–2006 年：从提案到工作草案

N1377 之后，提案经历了几轮修订：

- [[N1690]]（2004 年 9 月）把题目改为 *A Proposal to Add an Rvalue Reference to the C++ Language*，强调右值引用是一个语言机制，移动语义和完美转发是它的两种用途；
- [[N1770]]（2005 年 3 月）给出了核心语言的措辞，作者中增加了 J. Adamczyk 和 A. Hommel；同期的 [[N1771]] 分析了右值引用对标准库的影响，Hinnant 随后按章节提交了一系列库建议（[[N1856]]、[[N1857]]、[[N1858]]、[[N1859]]）；
- [[N2027]]（2006 年 6 月，Hinnant、Stroustrup、Kozicki）是一篇面向一般读者的介绍；
- [[N2118]]（2006 年 10 月）是措辞的第三次修订。

2006 年 10 月 Portland 会议的纪要 [[N2110]] 记录了动议：采纳 N2118，J16 投票 25 票赞成、0 票反对、0 票弃权。右值引用由此进入 C++0x 工作草案。此后几年，标准库按 N1771 的方向全面加入了移动操作；Stroustrup 在 HOPL IV 中提到，移动语义很快被用到所有标准容器上。

## 六、2008–2009 年：右值引用不再绑定到左值（N2812 / N2844）

右值引用能绑定到左值，这条规则在概念（concepts）进入 C++0x 草案之后暴露出问题。2008 年 12 月，Dave Abrahams 和 Doug Gregor 提交了 [[N2812]]（*A Safety Problem with RValue References (and what to do about it)*）。论文的例子是 `std::list<std::unique_ptr<int>>`：在受约束的模板中，`push_back(const value_type&)` 因为元素类型不可复制而被移除，剩下的 `push_back(value_type&&)` 却能接受左值，于是 `l.push_back(a)` 会悄悄地把左值 `a` 移走。论文指出 SFINAE 也会以同样的方式移除重载，并用一句话概括问题："the lvalue/rvalue overload set doesn't degrade safely"（[[N2812]]）。

N2812 提出的修正是禁止右值引用绑定到左值。这样一来，复制/移动这对重载中有一个被移除时，左值实参会得到编译错误，而不是被静默移走。修正的代价是标准库中依赖旧规则的地方要改写，例如 `std::forward` 的实现，以及若干接受右值引用的 `swap` 重载。

措辞在 [[N2831]] 中给出，修订版 [[N2844]] 提交到 2009 年 3 月的会议。会议纪要 [[N2847]] 记录了一个细节：Hinnant 在会上表示，N2844 对 `std::forward` 接口的修改有害，而且没有经过充分分析；他提出把 [forward] 一节从动议中剔除，修正动议以 19 票赞成、5 票反对、8 票弃权通过；剔除该节后的 N2844 以全体同意采纳。`forward` 的设计随后由 Hinnant 在 [[N2951]] 中单独讨论。

这次修改之后的规则就是今天的规则：

```cpp run title="rvalue-ref-binding.cpp" error
int main() {
    int i = 0;
    int&& r = i;     // error: 右值引用不能绑定到左值
    (void)r;
}
```

用 `-std=c++98` 编译时，Clang 23 把右值引用作为扩展接受（给出 `-Wc++11-extensions` 警告），但绑定规则用的是修正后的版本，同样报错。

## 七、2009–2010 年：noexcept、隐式移动与新术语

C++0x 在 2009 年夏天移除了概念之后，右值引用相关的遗留问题集中在 2010 年 3 月的 Pittsburgh 会议和同年 11 月的 Batavia 会议上处理。这一阶段有三条线索。

### 会抛异常的移动构造函数（N2855 → N3050）

2009 年 3 月，Gregor 和 Abrahams 在 [[N2855]]（*Rvalue References and Exception Safety*）中指出：`std::vector::push_back` 等操作在 C++98 中提供强异常安全保证，扩容时复制元素失败，原来的元素完好无损；如果改用移动，而移动构造函数在中途抛出异常，已经被移走的元素就无法恢复。N2855 提出了 `noexcept` 说明符。Abrahams、Rani Sharoni 和 Gregor 在 [[N2983]] 及其修订版 [[N3050]]（*Allowing Move Constructors to Throw*）中给出了最终方案：允许移动构造函数抛异常，标准库在需要强保证的地方使用 `std::move_if_noexcept`，只在移动不会抛异常（或类型不可复制）时才移动。Pittsburgh 会议纪要 [[N3094]] 记录 N3050 以 J16 16 票赞成、2 票反对、3 票弃权通过。

这就是今天 `std::vector` 扩容时只对 `noexcept` 移动构造函数使用移动的原因，细节见 [[topics/special-members-and-elision]]。

### 隐式生成移动操作（N3053 → N3153 → N3203）

右值引用进入草案时，编译器不会为类隐式生成移动构造函数和移动赋值运算符。Stroustrup 和 Lawrence Crowl 在 [[N2904]]、[[N2953]]、[[N3044]] 中逐步提出了隐式生成规则，最后一版 [[N3053]]（*Defining Move Special Member Functions*）在 Pittsburgh 会议上以全体同意采纳（[[N3094]]）。按 N3053 的措辞，如果类没有用户声明的复制构造函数，并且隐式移动构造函数不会被定义为弃置的，就隐式声明一个移动构造函数；移动赋值的条件类似。用户声明的析构函数不在抑制条件之列。

2010 年 10 月，Abrahams 发表了 [[N3153]]（*Implicit Move Must Go*），主张把隐式移动从草案中删除。他的例子是一个维护不变式的类：成员 `vector` 总是有 5 个元素，析构函数读取 `v[0]`。在 N3053 的规则下，`y.push_back(X())` 会隐式移动临时对象，把它的 `vector` 掏空，析构函数随即越界读取。论文记录了 g++ 4.6 的 `--std=c++0x` 模式确实让这个原本正确的 C++03 程序出错。论文还逐一说明了几个简单的补救规则（有析构函数时不生成、有构造函数时不生成、成员为私有时不生成）各自仍然存在的反例，并认为在标准化后期接受这种不确定性风险太大。Stroustrup 同期以 [[N3174]]（*To move or not to move*）和 [[N3201]]（*Moving right along*）回应，主张保留隐式移动但收紧条件。

Batavia 会议（2010 年 11 月）上同时摆着两个动议：采纳 Jens Maurer 的 [[N3203]]（*Tightening the conditions for generating implicit moves*），或采纳 Anthony Williams 和 Jason Merrill 的 [[N3216]]（*Removing Implicit Move Constructors and Move Assignment Operators*）。纪要 [[N3213]] 记录了较长的讨论，各方的技术论点大致如下：

- 主张收紧而保留的一方认为，删除隐式移动会让聚合体之类的简单类型失去移动能力（Matt Austern 指出 `std::array` 会因此变得不那么有用），而用户为每个类写一组 `= default` 的负担会催生宏；
- 主张删除的一方认为，隐式移动会让一部分现有代码在升级标准后改变行为，而这类问题依赖于类的不变式，静态分析很难发现，用户甚至可能不知道移动操作的存在；
- 也有人指出，在 C++03 中没有移动操作、在 C++0x 中有了移动操作的类，可以被工具机械地找出来，供人工审查。

依据纪要，N3216 的动议在一系列意向投票（straw poll）之后被撤回；N3203 以 J16 20 票赞成、1 票反对、2 票弃权，WG21 8 票赞成、0 票反对通过。N3203 的规则是：只要类有用户声明的复制构造函数、复制赋值运算符、移动赋值运算符（或移动构造函数）或析构函数，就不隐式声明移动构造函数（或移动赋值运算符）。同时，在有用户声明的析构函数或另一个复制操作时，隐式生成复制操作被标为弃用。这就是今天常说的 Rule of Five 背后的规则，也解释了下面这个程序的输出：

```cpp run title="implicit-move.cpp" std=c++11 ok
#include <cstdio>
#include <utility>
struct Tracer {
    Tracer() {}
    Tracer(const Tracer&) { std::puts("copy"); }
    Tracer(Tracer&&)      { std::puts("move"); }
};
struct Plain    { Tracer t; };                 // 隐式声明移动构造函数
struct WithDtor { Tracer t; ~WithDtor() {} };  // 有用户声明的析构函数：不隐式声明移动
int main() {
    Plain a;    Plain b = std::move(a);        // 输出 move
    WithDtor c; WithDtor d = std::move(c);     // 输出 copy：重载决议落到复制构造函数
}
```

Clang 23 在 C++11 和 C++2c 模式下都对第二个类给出 `-Wdeprecated-copy-with-user-provided-dtor` 警告，对应的正是 N3203 引入的弃用。这条弃用至今没有变成删除，见 [[depr.impldec]]。

### glvalue、xvalue、prvalue 的诞生（N3030 → N3055）

右值引用给核心语言措辞带来的问题是：`static_cast<T&&>(x)` 或返回 `T&&` 的函数调用，这种表达式应该叫什么？它指代一个确定的对象，像 lvalue；它又可以绑定到右值引用、可以被移动，像 rvalue。Stroustrup 在 HOPL IV 中提到，由于术语问题，右值引用这个词在核心语言部分和标准库部分的用法已经出现分歧，草案因此不自洽。

EDG 的 William M. Miller 先在 [[N3010]] 及其修订版 [[N3030]]（*Rvalue References as "Funny" Lvalues*）中提出调整术语。据 Stroustrup 回忆，他起初认为在标准化后期改术语不是好主意；Daniel Krügler 指出该提案中 rvalue 的定义与标准库的用法不一致后，他认为这个提案已经没有希望了。但 CWG 的多数成员坚持认为需要新的术语来消除已知的问题（Stroustrup, *"New" Value Terminology*）。

Stroustrup 在这篇文章和 HOPL IV 中都记述了接下来的经过。在 2010 年 3 月 Pittsburgh 会议期间的 CWG 讨论中，各种命名建议持续了几天也没有结论，他担心讨论正走向"an impasse or a mess or both"（HOPL IV §4.2.3）。他利用午餐时间分析了值的性质，结论是只有两个相互独立的性质：

- 有身份（has identity）：有地址，能判断两个副本是否是同一个；
- 可以被移动（can be moved from）：允许把源对象留在某种不确定但有效的状态。

两个性质组合出四种可能，其中"没有身份又不能移动"在 C++ 中没有用处，剩下三种基本类别，加上按两个性质各自归并出的两个大类，在白板上画成一个 W 形的图。命名受到几条约束：W 左边两点必须叫某种 lvalue，右边两点必须叫某种 rvalue；要保留"每个值要么是 lvalue 要么是 rvalue"的性质；标准库措辞中的 rvalue 指的是"可以被移动"这一大类。Doug Gregor 带头逐条清点了核心语言中 lvalue 一词的用法，发现在大多数情形、尤其是最微妙的条文里，lvalue 指的是"有身份且不能移动"这一类。于是：

| 性质 | 名称 | 命名理由（据 Stroustrup） |
|---|---|---|
| 有身份，不能移动 | lvalue | 保留传统含义 |
| 有身份 | glvalue | generalized lvalue，对 lvalue 的推广 |
| 有身份，能移动 | xvalue | 找不到约束来指导命名，选了 x |
| 没有身份，能移动 | prvalue | pure rvalue；Stroustrup 本人更倾向 specialized rvalue |
| 能移动 | rvalue | 与标准库措辞一致 |

关于 xvalue 的 x，Stroustrup 写道它可以理解为中心、未知、奇怪、仅限专家。标准今天的注释采用了另一种解读：xvalue 是 eXpiring 的值（[[basic.lval#3]]）。

Miller 据此写成 [[N3055]]（*A Taxonomy of Expression Value Categories*），Pittsburgh 会议以全体同意采纳，纪要注明它同时解决了 CWG issue 858（[[N3094]]）。Stroustrup 在 HOPL IV 中写道，这个方案被迅速接受，使移动语义得以留在 C++11 中。

N3055 有一点常被忽略：它没有改变 lvalue 和 rvalue 的外延，只是给"rvalue 中有身份的那部分"和"lvalue 加上这部分"起了名字。值类别仍然是表达式的性质，而不是值或对象的性质（[[basic.lval#3]] 的注释特意强调了这一点）。

## 八、C++11 定稿与 C++14 的修补

C++11（FDIS 为 [[N3290]]）在 2011 年发布，包含了上面所有内容：右值引用及其绑定规则、`std::move` 和 `std::forward`、隐式移动的生成与抑制、`noexcept`、五个值类别。与返回语句相关的规则是：当 return 的操作数是函数内的局部对象，并且满足复制消除的条件时，先把它当作 rvalue 做一次重载决议；如果选出的构造函数的第一个形参不是该对象类型的右值引用，再把它当作 lvalue 重新做一次。这条"两阶段重载决议"让 `return local;` 在不写 `std::move` 的情况下也能移动只能移动的类型，例如 `std::unique_ptr`。函数形参在 return 中的隐式移动由 [[CWG1148]] 在 C++11 中加入。

C++14 在这一领域没有大的语言特性，主要是几项修补：

- [[CWG1402]]（由 [[N3667]] 起草，2013 年 4 月作为缺陷报告处理）：C++11 的规则下，只要某个子对象没有对应的移动操作、而它的复制操作又不平凡，显式预置（`= default`）的移动构造函数就被定义为弃置的；弃置的函数仍参与重载决议，于是按值返回这样的类会选中它并报错。修正后，删除的条件变窄，并且被定义为弃置的预置移动操作不参与重载决议，重载决议会退回到复制。
- [[CWG1579]]：原来的规则要求 return 的操作数与返回类型相同才能隐式移动，`optional<T> f() { T t; return t; }` 只能复制。2014 年 2 月该 issue 作为缺陷报告处理，放宽为只要满足其余条件即可先按 rvalue 尝试。
- [[N3648]] 引入初始化捕获，`[p = std::move(p)]` 让 lambda 能捕获只能移动的对象；[[N3668]] 加入 `std::exchange`，常用于实现移动构造函数。

## 九、C++17：保证的复制消除与 prvalue 的新定义

到 2015 年，返回一个临时对象时，复制消除仍然只是许可，第二节的 `NoMove` 依旧不能按值返回。Richard Smith 在 [[P0135R0]]（2015 年 9 月）中提出的方案，没有简单地把许可改成义务，而是改变了 prvalue 的含义。

在 C++11/14 中，prvalue 表示一个临时对象（或一个值）；`T()` 创建一个临时对象，`T x = T();` 理论上是从这个临时对象复制或移动到 `x`。P0135 把 prvalue 重新定义为一个对象的初始化方式：prvalue 本身不是对象，只有当它初始化某个对象时，那个对象才被创建，称为它的结果对象（result object）。如果 prvalue 出现在需要 glvalue 的地方（例如绑定到引用、访问成员），才通过临时量实质化（temporary materialization）转换创建一个临时对象。现行草案对 prvalue 结果的定义见 [[basic.lval#5]]，实质化的时机见 [[class.temporary]]。

在这个模型下，`T x = T();` 中的 `T()` 直接初始化 `x`，中间根本没有临时对象，也就谈不上复制或移动，不需要复制/移动构造函数存在或可访问。返回一个 prvalue 也一样：函数的 return 语句直接初始化调用方的结果对象。措辞修订版 [[P0135R1]] 于 2016 年 6 月 Oulu 会议以全体同意采纳（会议纪要 [[N4597]]）。第二节的两个例子在 C++17 下的表现就是这样来的：`NoMove` 可以按值返回，`-fno-elide-constructors` 也不能让编译器再插入复制。

需要分清的是，C++17 保证的只是 prvalue 的情形。具名返回值优化，也就是 `T f() { T x; return x; }` 中省略 `x` 到结果对象的复制，至今仍然只是许可（[[class.copy.elision#1.1]]）。Anton Zhilin 的 [[P2025R2]]（*Guaranteed copy elision for return variables*）试图在一定条件下保证 NRVO，截至本文写作，它没有进入工作草案。

P0135 还带来了一个对 language lawyer 很重要的变化：表达式的值类别从此决定的是有没有对象，而不只是能绑定到哪种引用。`std::atomic<int> a = std::atomic<int>(0);` 在 C++14 中非良构（Clang 23 报告调用了被隐式删除的复制构造函数），在 C++17 中合法，原因就在这里。

## 十、C++20：更多的隐式移动（P1825）

C++11/14 的隐式移动规则仍然有几个缺口：

1. 局部变量是右值引用类型时，`return r;` 不移动，因为规则只覆盖对象，不覆盖引用；
2. 函数形参和 catch 子句的形参在 `throw` 中不移动；
3. 第一次重载决议选中的构造函数的第一个形参如果不是"该对象类型的右值引用"，就退回复制。所以 `Base f() { Derived d; return d; }` 会选中 `Base(Base&&)`，但因为 `Base&&` 不是 `Derived&&`，又退回 `Base(const Base&)`。

David Stone 的 [[P0527R1]] 处理第一点，Arthur O'Dwyer 和 David Stone 的 [[P1155R3]]（*More implicit moves*）处理后两点。两者修改同一段措辞，于是合并为 [[P1825R0]]，2019 年 7 月 Cologne 会议采纳，并且作为缺陷报告处理（会议纪要 [[N4826]]）。合并后的措辞引入了 implicitly movable entity 这个术语，并删除了"第一个形参必须是该对象类型的右值引用"这一条件。

```cpp run title="more-implicit-moves.cpp" std=c++20 ok
#include <cstdio>
struct Base {
    Base() {}
    Base(const Base&) { std::puts("copy"); }
    Base(Base&&)      { std::puts("move"); }
};
struct Derived : Base {};

Base f() { Derived d; return d; }        // C++17 措辞：copy；P1825 之后：move
Base g(Base&& r) { return r; }           // C++17 措辞：copy；P1825 之后：move

int main() { f(); Base b; g(static_cast<Base&&>(b)); }
```

由于 P1825 是缺陷报告，实现可以把它应用到旧的语言模式。Clang 23 在 `-std=c++11` 到 `-std=c++23` 下运行这个程序，都输出两行 move。所以在今天的编译器上，很难用一段代码直观地展示 C++17 原始措辞的行为。

P1825 的 Annex C 条目记录了它对旧代码的影响：如果类的移动构造函数是私有的，C++17 中能编译的 `throw b;` 和 `return d;` 会因为选中了不可访问的移动构造函数而变为非良构（[[P1825R0]]）。

## 十一、C++23：更简单的隐式移动（P2266）

P1825 之后，规则仍然是两阶段重载决议：先当 rvalue 试，失败了再当 lvalue 试。这带来两个问题。一是规则复杂，"失败"的定义牵涉到重载决议的细节；二是两阶段只适用于构造函数和 `return_value` 的选择，对返回引用的函数不起作用。例如：

```cpp
Widget&& pass(Widget&& w) { return w; }  // C++20: error，w 是左值，不能绑定到 Widget&&
```

Arthur O'Dwyer 的 [[P2266R3]]（*Simpler implicit move*）把两阶段决议换成一条规则：在 return、co_return 和 throw 中，指代 implicitly movable entity 的 id-expression 本身就是 xvalue（现行措辞中称为 move-eligible，见 [[expr.prim.id.unqual]]）。不再有第二次尝试。该提案在 2022 年 7 月的全体会议上采纳（会议纪要 [[N4916]]），进入 C++23。

从此，一个 id-expression 的值类别取决于它出现的语境：同一个名字 `w`，在 return 语句中是 xvalue，在别处是 lvalue。这一改动不是缺陷报告，Clang 只在 C++23 及以后的模式中应用它，因此可以直接对比：

```cpp run title="simpler-implicit-move.cpp" std=c++23
#include <type_traits>

struct Widget { Widget(); Widget(Widget&&); };
Widget&& pass(Widget&& w) {
    return w;          // C++20: error，w 是左值；C++23: OK，w 是 xvalue
}

int& bad(int&& x) {
    return x;          // C++20: OK；C++23: error，xvalue 不能绑定到 int&
}

decltype(auto) h(int&& x) { return (x); }
static_assert(std::is_same_v<decltype(h(0)), int&&>);   // C++23 成立；C++20 下是 int&

int main() {}
```

在 Clang 23 上，`-std=c++20` 报告 `pass` 中 `rvalue reference to type 'Widget' cannot bind to lvalue of type 'Widget'` 并使 `static_assert` 失败；`-std=c++23` 则只拒绝 `bad`。`bad` 这样的代码在 C++20 中合法，在 C++23 中非良构，这是 P2266 明确接受的不兼容。`decltype(auto)` 返回 `(x)` 的类型变化也是同一原因：`decltype` 作用于带括号的表达式时反映它的值类别，而这个值类别在 return 语句中变了。

## 十二、C++26：禁止返回绑定到临时对象的引用（P2748）

返回一个绑定到临时对象的引用，从来都是悬垂引用。C++11 之前的标准就规定，在 return 语句中绑定到函数返回值的临时对象，生命周期并不延长到函数调用之外（见 [[class.temporary]]），但程序本身是良构的，编译器只能给出警告。Brian Bi 的 [[P2748R5]]（*Disallow Binding a Returned Glvalue to a Temporary*）把这种情况改为非良构，2024 年 3 月东京会议以全体同意采纳（会议纪要 [[N4980]]），进入 C++26。

```cpp run title="return-temporary.cpp" std=c++2c
const int& f() {
    return 42;         // C++23 及以前：良构，Clang 给出 -Wreturn-stack-address 警告
}                      // C++26：error，返回的引用绑定到临时对象
struct S { };
const S& g() { return S(); }   // 同上
int main() {}
```

Clang 23 在 `-std=c++23` 下对两处给出 `returning reference to local temporary object` 警告，在 `-std=c++2c` 下把同样的诊断作为错误。

现行草案的 [[stmt.return#6]] 比 P2748 走得更远：除了返回的引用，被返回对象的 constituent reference（例如聚合体中的引用成员）绑定到临时对象，同样非良构。这是 C++23 之后的新措辞，本页没有核实它对应的具体提案。悬垂引用的其他形式见 [[topics/dangling-references]]。

## 十三、平凡重定位：进入 C++26 又被移出

移动加析构（把对象 A 移动到新位置 B，再析构 A）在很多类型上可以用一次 `memcpy` 完成，例如常见实现中的 `std::unique_ptr` 和 `std::vector`。容器扩容时如果知道这一点，就可以整块复制内存。[[P1144R13]] 的摘要列举了已经在使用这种平凡重定位的库，包括 Abseil、BSL、Folly、Qt 等；但按标准的对象模型，用 `memcpy` 搬运非平凡可复制的对象没有定义行为。对这种操作的标准化，WG21 中出现了两条主要路线：

- Arthur O'Dwyer 的 P1144 系列，最早版本 [[P1144R0]]（2018 年 10 月，与 Mingxin Wang 合著）题为 *Object relocation in terms of move plus destroy*，后来改名为 *std::is_trivially_relocatable*，最新的 [[P1144R13]] 有十位作者；
- P2786 系列，最早版本 [[P2786R0]]（2023 年 2 月，Mungo Gill 与 Alisdair Meredith）题为 *Trivial relocatability options*，后来定名为 *Trivial Relocatability For C++26*，作者也有变化。

两者的设计取舍不同，例如如何声明一个类型可平凡重定位、对 swap 和赋值能否同样优化（P2786 引入了 replaceable 的概念）等。2024 年出现了针对 P2786 的批评：Giuseppe D'Angelo 的 [[P3233R0]]（*Issues with P2786*），以及多位库作者联名的 [[P3236R1]]（*Please reject P2786 and adopt P1144*）。

2025 年 2 月，Hagenberg 会议采纳了 [[P2786R13]]。Herb Sutter 的会议报告写道，它为可用 memcpy 复制的类型提供了更强的语言支持，并感谢了"other trivial-relocation proposals that were not adopted"的作者（Sutter, Hagenberg trip report, 2025-02）。

2025 年 11 月的 Kona 会议是 C++26 处理国家成员体（NB）意见的会议。Louis Dionne 的 [[P3920R0]] 记录，EWG 和 LEWG 的联合会议达成共识，从 C++26 中移除 P2786R13 的平凡重定位特性，希望在 C++29 的时间框架内解决其问题；论文本身没有列出这些问题，只说它们在此不再重复。被移除的内容包括 `trivially_relocatable_if_eligible`、`replaceable_if_eligible` 两个上下文关键字，`is_trivially_relocatable`、`is_replaceable`、`is_nothrow_relocatable` 等类型特征，`std::trivially_relocate` 和 `std::relocate`，以及对应的特性测试宏。Sutter 的 Kona 会议报告的表述是，委员会发现了一个"showstopper bug"，认为无法在 C++26 的时间内修好，于是以强共识移除了这一特性（Sutter, Kona trip report, 2025-11）。

2026 年 4 月，D'Angelo 的 [[P4197R0]]（*Design questions for trivial relocation in C++29*）整理了下一轮设计需要回答的问题。该文说 P2786R13 是因为"a number of unresolved design concerns"被移出的，并列举了 C++26 设计中的若干具体问题，例如只有无条件的选择加入语法、只能重定位的类型无法作为自动变量、联合体的平凡重定位交由实现定义等。它没有提出新的设计，只列出了九个开放问题，包括重定位应当是字节复制还是一种专门的抽象机操作、是否允许需要修正（例如指针认证）的重定位、是否支持常量求值等。

截至本文写作，C++26 中没有平凡重定位；这一特性的标准化工作转入 C++29 周期。

## 时间线

| 时间 | 事件 | 文献 |
|---|---|---|
| 1982 | Stroustrup 在编译器中把返回值分配在调用者栈帧上 | HOPL IV §4.2.3 |
| 标准化之前 | Zortech C++、Cfront 先后实现 NRVO；ARM 第 12 章讨论 Tiemann 的具名返回值扩展 | Lippman 2004 |
| 1998 | C++98：lvalue/rvalue 两分法；允许复制消除；`auto_ptr` | ISO/IEC 14882:1998 |
| 2002-09 | 移动语义提案；转发问题 | [[N1377]]、[[N1385]] |
| 2003-02 | Alexandrescu 发表 Mojo | CUJ |
| 2004–2006 | 右值引用提案多次修订；2006-10 Portland 会议采纳 N2118 | [[N1690]]、[[N1770]]、[[N2118]]、[[N2110]] |
| 2008-12 – 2009-03 | 右值引用不再绑定到左值 | [[N2812]]、[[N2844]]、[[N2847]] |
| 2010-03 | Pittsburgh：noexcept 与 move_if_noexcept、隐式移动生成、值类别新术语 | [[N3050]]、[[N3053]]、[[N3055]]、[[N3094]] |
| 2010-10 | *Implicit Move Must Go* | [[N3153]] |
| 2010-11 | Batavia：收紧隐式移动条件，弃用部分隐式复制 | [[N3203]]、[[N3213]] |
| 2011 | C++11 发布 | [[N3290]] |
| 2012–2014 | 弃置的默认移动不参与重载决议；按转换构造函数隐式移动 | [[CWG1402]]、[[CWG1579]] |
| 2014 | 提议在 C++17 中删除 `auto_ptr` | [[N4190]] |
| 2016-06 | Oulu：保证的复制消除，prvalue 重新定义 | [[P0135R1]]、[[N4597]] |
| 2019-07 | Cologne：更多的隐式移动（作为 DR） | [[P1825R0]]、[[N4826]] |
| 2022-07 | 更简单的隐式移动，进入 C++23 | [[P2266R3]]、[[N4916]] |
| 2024-03 | 东京：禁止返回绑定到临时对象的引用，进入 C++26 | [[P2748R5]]、[[N4980]] |
| 2025-02 | Hagenberg：采纳平凡重定位 | [[P2786R13]] |
| 2025-11 | Kona：从 C++26 移除平凡重定位 | [[P3920R0]] |
| 2026-04 | 整理 C++29 平凡重定位的设计问题 | [[P4197R0]] |

## 现状与未来

回头看，这段历史一直在回答同一个问题：什么时候可以不复制。C++98 允许实现选择不复制；C++11 让程序员可以显式要求移动，并在返回局部变量时自动移动，这条规则此后逐步放宽；C++17 则让某些情形下根本不存在复制。每一步都带来新的术语，也带来新的边界情况。

对 language lawyer 来说，几个容易被历史包袱误导的地方值得记住：

- 值类别是表达式的性质。自 C++23 起，它还可能依赖于表达式所在的语境（return、co_return、throw 中的 move-eligible id-expression）。
- C++17 之后，prvalue 不是临时对象。讨论"这里有没有临时对象"时，要看 prvalue 是否被实质化（[[class.temporary]]），而不是看它是不是 rvalue。
- 保证的只是 prvalue 的复制消除。NRVO 仍然是许可，被消除的复制/移动构造函数仍须可用，这一点在 [[class.copy.elision]] 中至今没有变。
- 隐式移动的规则经历了 C++11、C++14（DR）、C++20（DR）、C++23 四次修改，其中两次是缺陷报告，编译器在旧语言模式下也可能已经应用了新规则。验证版本差异时，要分清标准的原始措辞和编译器的实际行为。

正在进行中的工作主要是平凡重定位的重新设计（[[P4197R0]] 列出的问题）和更一般的重定位语义。在此之前，WG21 还收到过几份探索破坏性移动或一般重定位的提案，例如 [[N4158]]（*Destructive Move*）、[[P1029R3]]（*move = bitcopies*）、[[P2785R3]]（*Relocating prvalues*）和 [[P2839R0]]（*Nontrivial relocation via a new "owning reference" type*）。这些提案都没有进入工作草案，C++29 会采纳哪种方向，目前没有定论。

## 参考资料

WG21 文档（均可通过 wg21.link 访问）：

- [[N1377]] H. Hinnant, P. Dimov, D. Abrahams, *A Proposal to Add Move Semantics Support to the C++ Language*, 2002-09-10.
- [[N1385]] P. Dimov, H. Hinnant, D. Abrahams, *The Forwarding Problem: Arguments*, 2002-09-09.
- [[N1690]]、[[N1770]]、[[N1771]]、[[N2118]]：右值引用提案及措辞的各次修订，2004–2006。
- [[N2027]] H. Hinnant, B. Stroustrup, B. Kozicki, *A Brief Introduction to Rvalue References*, 2006-06.
- [[N2110]] J16/WG21 会议纪要，Portland，2006-10。
- [[N2812]] D. Abrahams, D. Gregor, *A Safety Problem with RValue References (and what to do about it)*, 2008-12-05；[[N2831]]、[[N2844]] 为其措辞。
- [[N2847]] PL22.16 会议纪要，2009-03。
- [[N2855]] D. Gregor, D. Abrahams, *Rvalue References and Exception Safety*, 2009-03-23；[[N3050]] D. Abrahams, R. Sharoni, D. Gregor, *Allowing Move Constructors to Throw (Rev. 1)*, 2010-03-12。
- [[N3053]] B. Stroustrup, L. Crowl, *Defining Move Special Member Functions*, 2010-03-12.
- [[N3030]] W. M. Miller, *Rvalue References as "Funny" Lvalues*, 2010-02；[[N3055]] W. M. Miller, *A Taxonomy of Expression Value Categories*, 2010-03-12。
- [[N3094]] PL22.16 会议纪要，Pittsburgh，2010-03。
- [[N3153]] D. Abrahams, *Implicit Move Must Go*, 2010-10-17；[[N3174]] B. Stroustrup, *To move or not to move*；[[N3201]] B. Stroustrup, *Moving right along*。
- [[N3203]] J. Maurer, *Tightening the conditions for generating implicit moves*, 2010-11-11；[[N3216]] A. Williams, J. Merrill, *Removing Implicit Move Constructors and Move Assignment Operators*。
- [[N3213]] PL22.16 会议纪要，Batavia，2010-11。
- [[CWG1148]]、[[CWG1402]]（[[N3667]]）、[[CWG1579]]：C++11/14 期间关于隐式移动的核心语言 issue。
- [[N4190]] S. T. Lavavej, *Removing auto_ptr, random_shuffle(), And Old &lt;functional&gt; Stuff*, 2014-10.
- [[P0135R0]]、[[P0135R1]] R. Smith, *Guaranteed copy elision through simplified value categories*, 2015–2016；[[N4597]] Oulu 会议纪要。
- [[P0527R1]] D. Stone；[[P1155R3]] A. O'Dwyer, D. Stone；[[P1825R0]] D. Stone, *Merged wording for P0527R1 and P1155R3*, 2019-07；[[N4826]] Cologne 会议纪要。
- [[P2266R3]] A. O'Dwyer, *Simpler implicit move*, 2022-03；[[N4916]] 2022-07 全体会议纪要。
- [[P2748R5]] B. Bi, *Disallow Binding a Returned Glvalue to a Temporary*, 2024-03；[[N4980]] 东京会议纪要。
- [[P1144R13]]、[[P2786R13]]、[[P3233R0]]、[[P3236R1]]、[[P3920R0]]、[[P4197R0]]：平凡重定位相关文档。
- [[P2025R2]] A. Zhilin, *Guaranteed copy elision for return variables*, 2021-03.

其他文献：

- Bjarne Stroustrup, *"New" Value Terminology*, 2010，stroustrup.com/terminology.pdf。
- Bjarne Stroustrup, *Thriving in a Crowded and Changing World: C++ 2006–2020*, HOPL IV, 2020，§4.2.3 Move Semantics。
- Stanley B. Lippman, *The Name Return Value Optimization*, MSDN 博客，2004-02。
- Andrei Alexandrescu, *Generic&lt;Programming&gt;: Move Constructors*, C/C++ Users Journal, 2003-02。
- Herb Sutter, *Trip report: February 2025 ISO C++ standards meeting (Hagenberg, Austria)* 与 *Trip report: November 2025 ISO C++ standards meeting (Kona, USA)*，herbsutter.com。
