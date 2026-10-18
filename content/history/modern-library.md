---
title: 从 Boost、TR1 到 C++26：标准库的现代演进
summary: C++98 之后的标准库是怎样长大的：Boost 作为试验场，TR1 把智能指针、function、tuple、regex、哈希表带进 C++11；chrono 与日历时区，Filesystem 与 Library Fundamentals 两个 TS，optional/variant/any 与 valueless_by_exception 的妥协，string_view、PMR、expected 的长路；range-v3 到 C++20 Ranges，{fmt} 到 std::format/print；mdspan、linalg、simd、inplace_vector、hive；2020 年布拉格的 ABI 民意测验到底测了什么，它让哪些东西无法再改；Networking TS 与 2D 图形提案的结局，标准库加固，以及标准库该不该继续长大的争论
status: draft
order: 70
since: c++11
papers: N1836, N1856, N2661, N4190, N4100, P0218R1, P0220R1, P0088R3, P0323R12, P0355R7, N4128, P0896R4, P0645R10, P2093R14, P0009R18, P1673R13, P1928R15, P0447R28, P1863R1, P2028R0, P2000R4, P2453R0, P3471R4
related: utilities, smartptr, unique.ptr, util.sharedptr, function.objects, func.wrap, time, time.zone, filesystems, optional, variant, any, string.view, expected, mem.res, ranges, format, views.multidim, linalg, simd, inplace.vector, hive, exec, re, unord, toolchain/name-mangling, toolchain/object-layout-and-vtables
tags: 沿革, 标准库, Boost, TR1, ABI, Ranges, format, 委员会
updated: 2026-10-18
---

C++98 的标准库很小：容器、迭代器、算法（来自 STL），再加上 iostream、string、locale 和从 C 继承来的部分。哈希表、正则表达式、智能指针、线程、时间、文件系统，这些在别的语言里理所当然的东西都不在里面。今天的标准库则有 [[ranges]]、[[format]]、[[time.zone|时区]]、[[views.multidim|多维视图]]、[[linalg|线性代数]]、[[simd]]、[[exec|异步执行框架]]，还有 `expected`、`mdspan`、`hive` 这类二十年前没有人会想到要标准化的类型。

本页按时间顺序讲这二十多年里标准库是怎么扩充的：新组件从哪里来，在委员会里经历了哪些争论，最后以什么形状落地。贯穿全篇的有三条线索。第一条是先有实践、后有标准：几乎每个成功进入标准的组件都先在 Boost 或某个公司的代码库里用了很多年。第二条是 TS（Technical Specification，技术规范）这种中间形态：它让委员会可以先发布、收集经验、再决定是否并入，有时也成了组件的终点。第三条是 ABI 兼容性：组件一旦进入标准并被实现、被编译进千万个二进制文件，它的内存布局和函数签名就很难再改，这个约束越来越多地左右着标准库的设计。

阅读本页不需要预先了解委员会流程，但知道 WG21 下有 LEWG（库演进组，负责设计）和 LWG（库工作组，负责措辞）两个小组会有帮助。文中的论断都给出了出处：WG21 文档用 `[[N1836]]`、`[[P1863R1]]` 这样的链接，Stroustrup 的两篇 HOPL 论文简称 HOPL III（*Evolving a language in and for the real world: C++ 1991–2006*）和 HOPL IV（*Thriving in a Crowded and Changing World: C++ 2006–2020*），会议进展主要引自 Herb Sutter 等人的 trip report，完整列表见文末。

## 一、C++98 之后：库为什么不够，Boost 从哪里来

### 委员会自己的反思

C++98 完成时，委员会清楚标准库缺了很多东西。Stroustrup 在 HOPL III 中回忆，1997 年标准定稿时，库的内容只是"最急需而且已经可以交付"的那一部分，哈希表、正则表达式匹配、目录操作和线程都没有赶上。他还提到，在 1998 年标准收尾时，委员会里普遍觉得库方面做得不够，而且已批准的库缺少足够的试验和性能测量。怎样在以后避免这个问题，有两种思路：一种是传统的标准化路线，编写技术报告（technical report）；另一种是 Beman Dawes 在 1998 年发起的 Boost（HOPL III §4.2）。

哈希表是一个典型例子。HOPL III 说，1995 年 Javier Barreiro、Robert Fraley 和 David Musser 试图赶在标准定稿前提交一份哈希表提案，但委员会没有时间做细致的设计和规格工作。结果此后几年各家实现各自提供了互不兼容的 `hash_map`，等到 TR1 再标准化时，只好换一个名字叫 `unordered_map`。HOPL IV §4.6 补充说，哈希表是 C++0x 最早的提案之一。

### Boost：一个为标准化准备的仓库

根据 Boost 官方的历史页面，这个想法来自 1998 年 3 月在法国 Sophia Antipolis 举行的标准委员会会议上 Robert Klarer 与 Beman Dawes 的讨论；随后 Dave Abrahams 加入，三人建立了第一个 Boost 邮件列表，目标是讨论如何创建高质量、经过同行评审的 C++ 库。第一个正式发行版出现在 1999 年，包含 24 个库。

Dawes 当时写的文件题为 *Proposal for a C++ Library Repository Web Site*。HOPL IV 对这件事的描述是：Dawes 建立这个库仓库网站，明确目的就是开发 C++ 库来确立既有实践（existing practice），供将来的标准化工作在此基础上进行；在此之前，C++ 甚至没有一个公共的库仓库（HOPL IV §2.3）。Stroustrup 在 HOPL III 中引用了 2006 年 8 月 boost.org 上的自我介绍，其中有一句："We aim to establish 'existing practice' and provide reference implementations so that Boost libraries are suitable for eventual standardization."

这句话解释了 Boost 与标准的关系。委员会成员可以在 Boost 里提出一个库，接受邮件列表上的公开评审，让它在真实项目中被使用和批评；几年之后，如果这个库被证明有用，它的作者就带着实现经验和用户反馈去写标准提案。HOPL IV 列举了经由这条路进入标准的库：regex、thread、shared_ptr、variant、filesystem，并说 Boost 的库比对应的 ISO 标准版本早十多年可用，被社区当作一种"junior standard"来信任。

!!! note "Boost 不是标准库的唯一来源"
    后文会看到，string_view 的先例在 Google、LLVM 和 Bloomberg 的代码库里；PMR 来自 Bloomberg 的 BSL；span 来自 C++ Core Guidelines 的支持库（HOPL IV §9.3.8）；{fmt} 和 range-v3 是作者个人维护的开源库；date 库也是 Hinnant 个人的 GitHub 项目。Boost 开创的是先实践后标准化的模式，后来的提案者普遍沿用了这个模式，但不一定经过 Boost。

## 二、TR1：第一批扩展（2001–2007）

### 技术报告是什么

技术报告不是标准，没有强制力；它的作用是把一组被认为值得标准化的设计正式写下来，让实现者先去实现、用户先去使用。HOPL III 记载，委员会在 2001 年开始编写库技术报告，2004 年以全票通过了这份报告的技术内容。ISO 在 2007 年把它发布为 ISO/IEC TR 19768:2007，通称 TR1。

TR1 的草案（[[N1836]]，2005 年 6 月，编辑 Matt Austern）规定所有组件都声明在 `std::tr1` 命名空间里，并要求实现不要把这些名字默认暴露在标准头文件中。所以当时的代码要写 `std::tr1::shared_ptr`、`#include <tr1/memory>`（具体头文件路径由实现决定）。

### TR1 包含什么

按 [[N1836]] 的目录，TR1 的内容可以这样分组：

| 类别 | 组件 | 提案或先例 |
|---|---|---|
| 通用工具 | `shared_ptr`、`weak_ptr`、`enable_shared_from_this`，`reference_wrapper`，`tuple` | [[N1450]]（Dimov、Dawes、Colvin）；HOPL IV 说 `tuple` 源自 `boost::tuple` |
| 函数对象 | `function`、`bind`、`mem_fn`、`result_of` | [[N1402]]（Doug Gregor，Boost.Function） |
| 元编程 | `<type_traits>` | [[N1424]]（John Maddock） |
| 数值 | `<random>`，数学特殊函数，C99 数学函数 | [[N1932]]；HOPL IV 说 random 由 Jens Maurer 在 2002 年首先提出 |
| 容器 | `array`，`unordered_set`/`unordered_map` 及其 multi 版本 | [[N1456]]（Austern） |
| 文本 | `<regex>` | [[N1429]]（John Maddock）；HOPL IV 说它经由 Boost 而来 |
| C 兼容 | C99 库的各项补充 | — |

HOPL III 说，TR1 表决时每个组件都已经有原型或工业级实现。Stroustrup 特别挑出三个对应用程序员最重要的组件：正则表达式、通用智能指针和哈希表。关于智能指针，他提到 `shared_ptr` 的前身 `counted_ptr` 当年因为性能和容易被滥用的顾虑而没能进入 C++98。

### TR1 进入 C++11

C++11 把 TR1 的绝大多数内容从 `std::tr1` 搬进了 `std`，并在此过程中借助右值引用、可变参数模板等新语言特性重写了接口（例如 `tuple` 不再需要模拟可变参数，`function` 和 `bind` 支持完美转发）。数学特殊函数是例外：它们没有进入 C++11，而是另外形成了一份国际标准（Mathematical Special Functions IS），到 C++17 才并入，它是 Sutter 在 2016 年 3 月 Jacksonville 会议报告中所列的 C++17 合并的四个分支之一。

HOPL IV §4.6 对 C++11 新增库组件的评价比较克制：这些组件质量很高，但由于来源不同，接口风格并不统一；C++11 没有明确的纳入标准，组件是"从现有的、在社区里被证明成功的东西中挑选的"，其中许多来自 Boost。这段评价预示了后来 [[P2000R4]] 对标准库一致性的批评，见第十三节。

TR1 之后委员会也计划过 TR2。HOPL III 引用的 2006 年 Boost 自我介绍说，更多 Boost 库已被提议纳入即将到来的 TR2；Boost.Filesystem（[[N1975]]）和 Asio（[[N2054]]）的提案标题都写明以 TR2 为目标。后来的扩展实际上是以按主题划分的 TS（Filesystem TS、Library Fundamentals TS、Networking TS 等）推进的。

## 三、智能指针：从 auto_ptr 到 unique_ptr

### auto_ptr 的问题

C++98 唯一的智能指针是 `auto_ptr`。它表示独占所有权，复制时会把所有权从源对象转移给目标对象，源对象变成空指针。这在 C++98 里是唯一能表达转移的方式，因为语言还没有移动语义。

Howard Hinnant 在 [[N1856]]（2005）中解释了这个设计为什么不可接受。他的说明是：`auto_ptr` 用复制的语法做移动的事，而泛型代码（比如某些 `sort` 实现）会假设复制之后源和目标等价。如果把 `auto_ptr` 放进容器再排序，某个实现可能把一个元素复制到局部变量当作枢轴，于是容器里的那个元素被置空，结果取决于实现，甚至会崩溃。也就是说，`auto_ptr` 违反了泛型代码对复制语义的基本假设。

### unique_ptr 的方案

[[N1856]] 提出的解决办法是：弃用 `auto_ptr`，新增 `unique_ptr`。`unique_ptr` 不可复制、只可移动，转移所有权必须显式写 `std::move`；它把这件事交给 C++11 的右值引用，而不是挪用复制语法。HOPL IV §4.2.4 记载，`shared_ptr` 和 `weak_ptr` 主要是 Peter Dimov 的工作，`unique_ptr` 是 Hinnant 作为 `auto_ptr` 的改进而贡献的；由于 `unique_ptr` 可以直接替代 `auto_ptr`，它给了委员会一个少有的机会，最终把一个有缺陷的设施从标准里移除。

`auto_ptr` 在 C++11 中被弃用，在 C++17 中由 Stephan T. Lavavej 的 [[N4190]] 移除。当前草案的兼容性附录 [[diff.cpp14.depr]] 把它与 `unary_function`、`bind1st`、`random_shuffle` 等一起列为"不再定义"，理由是"已被新特性取代"。

```cpp error
#include <memory>
int main() {
    std::auto_ptr<int> p(new int(1));   // error: C++17 起 std::auto_ptr 已被移除
}
```

`unique_ptr` 不可复制这一点正是它与 `auto_ptr` 的区别所在：本来会悄悄转移所有权的代码，现在变成编译错误。

```cpp error
#include <memory>
#include <vector>
int main() {
    std::vector<std::unique_ptr<int>> v;
    v.push_back(std::make_unique<int>(1));
    auto q = v[0];   // error: unique_ptr 的复制构造函数被删除
}
```

### 后续补充

C++11 有 `make_shared` 却没有 `make_unique`，后者由 Lavavej 的 [[N3656]] 在 C++14 补上。C++17 通过 [[P0414R2]] 让 `shared_ptr` 直接支持数组类型（这部分先在 Library Fundamentals TS 中试验）。这些条款现在在 [[smartptr]]、[[unique.ptr]] 和 [[util.sharedptr]]。

!!! impl "unique_ptr 的调用约定代价"
    `unique_ptr` 在源代码层面是零开销抽象，但在主流的 Itanium C++ ABI 下，带有非平凡析构函数的类类型按值传参时必须经由内存传递，不能放在寄存器里。Titus Winters 在 [[P1863R1]] 中把"按值传递 unique_ptr 的运行期开销"列为一个因 ABI 约束而无法消除的性能问题。第十二节会回到这个话题。参见 [[toolchain/object-layout-and-vtables]]。

## 四、std::function 与类型擦除

`std::function` 来自 Doug Gregor 的 Boost.Function，经 [[N1402]] 进入 TR1。它是一种[[g:type-erasure|类型擦除]]（type erasure）包装：任何签名匹配的可调用对象都能存进同一个类型 `function<R(Args...)>`，代价是可能的堆分配和一次间接调用。这个设计有几个后来被反复讨论的性质：

- 它要求被包装的对象可复制，因为 `function` 自身可复制。只能移动的 lambda（例如捕获了 `unique_ptr` 的 lambda）无法放进去。
- 它的 `operator()` 是 `const` 成员函数，但会调用被包装对象的非 `const` 调用运算符，这在常量正确性上是一个漏洞。
- 它原本支持自定义分配器，但各实现对此支持不一，C++17 通过 Jonathan Wakely 的 [[P0302R1]] 移除了这部分接口。

```cpp error
#include <functional>
#include <memory>
int main() {
    auto p = std::make_unique<int>(10);
    std::function<int(int)> g = [p = std::move(p)](int x) { return x + *p; };
    // error: std::function 要求可复制，而这个 lambda 只能移动
}
```

委员会没有修改 `std::function`（这会改变已有代码的行为，也涉及 ABI），而是增加了新的包装类型：

| 类型 | 所有权 | 可复制 | 标准 | 提案 |
|---|---|---|---|---|
| `function` | 拥有 | 是 | C++11 | [[N1402]]（TR1） |
| `move_only_function` | 拥有 | 否 | C++23 | [[P0288R9]]（最初名为 `any_invocable`） |
| `copyable_function` | 拥有 | 是 | C++26 | [[P2548R6]] |
| `function_ref` | 不拥有 | 是（浅复制） | C++26 | [[P0792R14]] |

`move_only_function` 于 2021 年 10 月的线上全体会议并入（C++23 的编辑报告 [[N4902]] 列出了 [[P0288R9]]）。`copyable_function` 和 `function_ref` 据 Sutter 的 2023 年 6 月 Varna 会议报告在那次会议并入 C++26，报告把前者描述为"以 move_only_function 为蓝本的、可复制的 std::function 替代品"。后两者修正了 `function` 的常量正确性问题：签名里可以写 `const`、`noexcept` 和引用限定符，例如 `copyable_function<int(int) const>`。

```cpp run
#include <functional>
#include <memory>
#include <print>
int call_twice(std::function_ref<int(int)> f, int x) { return f(f(x)); }   // 不拥有，不分配
int main() {
    auto p = std::make_unique<int>(10);
    std::move_only_function<int(int)> add = [p = std::move(p)](int x) { return x + *p; };
    std::println("{}", call_twice(add, 1));   // 21
}
```

上面这个例子按标准是良构的，但截至写作时，本机 Homebrew Clang 23 附带的 libc++ 还没有提供 `move_only_function` 和 `function_ref`，所以没有标判定；可以点 godbolt 按钮用 GCC trunk 的 libstdc++ 验证。

这个演变也招来了批评。David Sankel 在 [[P3023R1]] 中写道，委员会用"不少于三个"替代品取代了一个简单的 `std::function`，认为这无助于降低复杂度。支持者的理由则是三者的语义确实不同（拥有与否、可否复制），用一个类型无法同时满足。条款在 [[func.wrap]]、[[func.wrap.move]]、[[func.wrap.copy]]、[[func.wrap.ref]]。

## 五、时间：chrono（C++11）与日历、时区（C++20）

### chrono：为线程库服务的时间类型

C++11 的线程库需要表达睡眠时长和等待的截止时间。Howard Hinnant、Walter Brown、Jeff Garland 和 Marc Paterno 的 [[N2661]]（2008 年 6 月）以 *A Foundation to Sleep On* 为题，提出了 `duration`、`time_point` 和时钟三个概念。论文明确说，它的主要目标是满足标准库线程 API 的需要，同时做到易用、安全、高效，并且灵活到"10 年甚至 100 年后都不过时"。

设计上有几个关键选择，都在论文里有说明：

- 精度中立。`duration<Rep, Period>` 用编译期有理数 `ratio` 表示单位，`hours`、`nanoseconds` 都只是不同实例化的别名。论文说，日常使用的接口几乎与 Jeff Garland 的 Boost.Date_Time 时长类型相同，区别在于 Boost 用继承统一各单位，而这里用一个类模板统一。
- 只允许无损的隐式转换。粗单位可以隐式变成细单位，反过来必须写 `duration_cast`。
- 不做日历。论文有一节标题就是 *Sold Separately*：不提供日历服务，不规定纪元，不处理闰秒，但声称它会是将来日期/时间库的"出色基础"。

`common_type` 和 `ratio` 两个通用设施也是随 chrono 一起进入标准的。论文提出的 `monotonic_clock` 后来被 Lawrence Crowl 的 [[N3191]] 改为 `steady_clock`。HOPL IV §4.6 称 chrono 设计精巧，同时非常容易使用，用它可以让一年级学生直观体会不同算法和数据结构的代价。

### date：从个人项目到 C++20

N2661 许诺的日历库后来由 Hinnant 本人完成。他先在 GitHub 上以 date 和 tz 两个库发布，再与 Tomasz Kamiński 一起写成 [[P0355R7]] *Extending &lt;chrono&gt; to Calendars and Time Zones*，提案中列出了它在 Windows、Linux、Android 等平台上的移植和使用经验。Sutter 的 2018 年 3 月 Jacksonville 会议报告把它列在"Features adopted for C++20"之下。

HOPL IV §9.3.6 称它是"罕见的直接面向应用领域的标准库组件"，并强调它的细粒度静态类型检查：`year_month_day`、`weekday` 等是各自独立的类型，像 `ymd + 10` 这种分不清加的是日、月还是年的写法会被编译器拒绝；日期到 `sys_days` 的换算是 `constexpr` 的，可以出现在 `static_assert` 里。时区部分以 IANA 时区数据库为依据，提供 `zoned_time` 和 `tzdb`。

```cpp run ok
#include <chrono>
#include <print>
using namespace std::chrono;
static_assert(year_month_day{2016y / May / 29d}.ok());
static_assert(weekday{sys_days{2016y / May / 29}} == Sunday);   // 编译期算出星期
int main() {
    constexpr auto d = 2026y / October / 18d;
    std::println("{} is a {}", d, weekday{sys_days{d}});   // 2026-10-18 is a Sun
}
```

C++20 还通过 [[P1361R2]]（Zverovich、Engert、Hinnant）把 chrono 与 `std::format` 接上，所以上例可以直接格式化日期。条款在 [[time]]、[[time.cal]]、[[time.zone]]。

## 六、文件系统：Boost.Filesystem → TS → C++17

HOPL IV §8.6 记载，Beman Dawes 在 2002 年写了 Boost.Filesystem，它成为最受欢迎的 Boost 库之一。它在 2006 年以 TR2 为目标提交（[[N1975]]）；2013 年 Dawes 继续修订提案（[[N3505]]），同年的 [[N3803]] 已经是技术规范的形式，2014 年形成文件系统 TS 的文本（[[N4100]]），ISO 在 2015 年将其发布为 ISO/IEC TS 18822:2015。2016 年 3 月的 Jacksonville 会议通过 [[P0218R1]] 把它并入 C++17（编辑报告 [[N4583]] 记录了这一动议）。

Stroustrup 在 HOPL IV 中说，处理文件名和文件系统之所以棘手，是因为它涉及并发、多种自然语言和各操作系统之间的差异；核心类型 `path` 把字符集和路径写法抽象掉。设计上的一个特点是双重错误报告：大多数操作都有抛出 `filesystem_error` 的版本和接受 `error_code&` 参数、不抛异常的版本。HOPL IV 解释说，这是为了同时照顾罕见的（异常的）错误和常见的（预期的）错误。

文件系统是 TS 机制按设计运作的例子：TS 发布后各家实现在 `std::experimental::filesystem` 下提供了它，委员会收集经验后做了一些修改再并入。条款在 [[filesystems]]、[[fs.class.path]]。

## 七、Library Fundamentals TS 与 C++17 的词汇类型

### 一个 TS，多个组件

C++14 周期里，委员会把若干中小型库组件集中放进 Library Fundamentals TS（2015 年的草案 [[N4480]]，编号 ISO/IEC DTS 19568），其中包括 `optional`、`any`、`string_view`、多态内存资源、搜索器（searcher）、`sample`、`apply` 等。2016 年 3 月 Jacksonville 会议通过 [[P0220R1]] 把其中大部分并入 C++17。Sutter 的会议报告说，C++17 由此获得了"新一轮库组件"，包括 `any`、`optional`、`string_view`、内存池以及搜索和抽样算法。

`optional` 在进入 TS 之前有一段插曲。Fernando Cacciola 和 Andrzej Krzemieński 的 optional 提案（[[N3672]] 为第 4 版）曾进入 C++14 的工作草案；据 Christof Meerwald 对 2013 年 9 月芝加哥会议的记录，optional 与 `dynarray`、运行期大小数组一起被从 C++14 中移出。此后 optional 出现在 Library Fundamentals TS 中，最终随 P0220R1 进入 C++17。

### string_view

Jeffrey Yasskin 的 string_view 提案（第 3 版 [[N3609]] 到第 7 版 [[N3921]]）开头就说明了先例：Google、LLVM 和 Bloomberg 各自独立实现过字符串引用类型（Google 的 `StringPiece`、LLVM 的 `StringRef` 等），用来避免为了传参而构造 `std::string` 或把函数改写成模板。提案沿用 Chromium 和 Bloomberg 的做法，把它做成 `basic_string_view<charT, traits>`。

`string_view` 不拥有它指向的字符，这让它成为悬垂引用的常见来源（见 [[topics/dangling-references]]）。条款在 [[string.view]]。

### PMR：多态内存资源

C++98 的分配器是容器的模板参数，换一个分配器就换了一个类型：`vector<int, A1>` 和 `vector<int, A2>` 不能互相赋值，接受 `vector<int>` 的函数也不能接受它们。Pablo Halpern 的 [[N3916]]（*Polymorphic Memory Resources - r2*，2014）提出用一个虚基类 `memory_resource` 承载分配策略，再用一个固定的分配器类型 `polymorphic_allocator` 在运行期指向某个资源。这样所有使用 PMR 的容器都是同一个类型，例如 `std::pmr::vector<int>`。

提案说，`memory_resource`、`polymorphic_allocator`、`monotonic_buffer_resource` 和 `unsynchronized_pool_resource` 是对 Bloomberg 内部使用了十多年的设施（BSL 开源库）的小幅改动，并称这些设施显著提高了可测试性（可以注入测试用的资源），在使用竞技场分配器和线程专属分配器时也带来了性能收益。

```cpp run ok
#include <memory_resource>
#include <vector>
#include <cstddef>
#include <print>
int main() {
    std::byte buffer[1024];
    std::pmr::monotonic_buffer_resource arena(buffer, sizeof buffer);
    std::pmr::vector<int> v(&arena);   // 内存先从栈上的 buffer 里取，用完再向上游资源要
    for (int i = 0; i < 10; ++i) v.push_back(i);
    std::println("{}", v.size());      // 10
}
```

PMR 随 P0220R1 进入 C++17。C++20 的 [[P0339R6]]（Halpern、Kühl）把 `polymorphic_allocator<>` 的默认实参改为 `std::byte`，并增加 `allocate_bytes`、`new_object` 等成员，让它可以作为通用的词汇类型。条款在 [[mem.res]]、[[mem.poly.allocator.class]]。

### optional、variant、any 与 valueless_by_exception

HOPL IV §8.3 说，Boost 提供了三个封装联合体的类型：`optional<T>`（持有一个 `T` 或什么都没有）、`variant<T, U>`（持有 `T` 或 `U`）、`any`（持有任意类型）。`optional` 和 `any` 经 Library Fundamentals TS 进入 C++17；`variant` 则走了另一条路，由 Axel Naumann 的一系列提案（[[N4542]] 是第 4 版，[[P0088R3]] 是第 8 版）推进，在 2016 年 6 月的 Oulu 会议并入 C++17（Sutter 的会议报告称它补齐了 `any` 和 `optional`）。

`variant` 设计中争论最久的问题是：赋值时如果新值的构造抛出异常怎么办。[[N4542]] 用下面的情形说明问题：`v` 当前持有 `S`，要改为持有 `T`；`v` 必须先销毁 `S`，再在同一块存储上构造 `T`；如果 `T` 的构造抛出异常，`v` 里既没有 `S` 也没有 `T`。提案逐一讨论了几种出路：

- 要求所有备选类型的复制构造都不抛异常。提案认为判断一个类型是否满足 `is_nothrow_copy_constructible` 对新手并不容易，而且这个集合取决于实现。
- 双缓冲。Boost.Variant 的做法是先在第二块缓冲区（对 Boost 而言在自由存储上按需分配）构造新值，成功后再销毁旧值。提案列出的缺点是：额外内存最多翻倍；内部存储的地址会变化；销毁和构造的顺序反直觉（先构造新值，再销毁旧值）。
- 引入一个可见的空状态。提案选择了这个方案，把它类比为被移动后的对象：处于有效但未指定的状态。

LEWG 在多次会议上就这个空状态投票。[[P0088R3]] 记录了过程：在 2015 年的 Lenexa 会议上，LEWG 决定 variant 应当建模为可辨识联合（discriminated union），并否决了让默认构造进入空状态的方案，改为默认构造第一个备选类型，需要时用 `monostate` 显式提供默认状态；在随后 Kona 会议的晚间讨论中，"P0088R0 加上对无效状态抛异常（从而不出现未定义行为）"以 SF=13、F=15、N=2、A=3、SA=0 获得支持，提案称之为 Kona 妥协：处于无效状态时 `get` 和 `visit` 抛出 `bad_variant_access`。这个状态的查询函数原名 `valid()`，LEWG 先投票改为 `!corrupted_by_exception()`，之后经 LWG 和 LEWG 邮件列表上 32 人回复的投票改为 `!valueless_by_exception()`。

```cpp run ok
#include <variant>
#include <stdexcept>
#include <cstdio>
struct Bomb {
    Bomb() = default;
    Bomb(Bomb&&) { throw std::runtime_error("boom"); }
};
int main() {
    std::variant<int, Bomb> v = 42;
    try {
        v.emplace<Bomb>(Bomb{});   // 先销毁 int，再用会抛异常的移动构造函数初始化 Bomb
    } catch (const std::runtime_error&) {}
    std::printf("%d %d\n", v.valueless_by_exception(), v.index() == std::variant_npos);   // 1 1
}
```

这种状态在实践中很少出现，名字本身也在提醒它只来自异常。后来的 `expected` 走了相反的方向：[[P0323R12]] 在 *Never-empty guarantee* 一节中说，`expected<T, E>` 像 `boost::variant<T, unexpected<E>>` 一样保证总持有 `T` 或 `E` 之一，从而让用户免于处理 `variant` 那种 `valueless_by_exception` 状态带来的额外复杂性。

Stroustrup 对这三个类型的评价并不高。HOPL IV §8.3 说，它们的设计被分开讨论，好像各自的用例互不相干，结果三个类型的接口（`*opt`、`get<int>(var)`、`any_cast<int>(a)`）差别很大，他称之为"委员会设计的经典例子"，并认为模式匹配才是更根本的解决办法。方向组的 [[P2000R4]] §5.3 也把"std::any、std::optional 和 std::variant 接口的巨大差异"列为标准库缺乏一致性的例证。条款在 [[optional]]、[[variant]]、[[any]]。

## 八、std::expected：九年的路

`expected<T, E>` 把"一个值或一个错误"做成返回类型。[[P0323R12]] 说，这个想法最初来自 Andrei Alexandrescu 在 C++ and Beyond 2012 上的报告 *Systematic Error Handling in C++*。提案的历史在它自己的修订记录里写得很清楚：

- 最早的版本是 Vicente Botet Escribá 和 Pierre Talbot 的 [[N4015]]（2014 年 5 月）和 [[N4109]]，标题是 *A proposal to add a utility class to represent expected monad*，在 2014 年 Rapperswil 会议上由 LEWG 审阅。
- 2016 年起以 P0323 编号继续，先后经过 LEWG（Oulu 2016、Toronto 2017、Albuquerque 2017）、EWG（Albuquerque 2017）和 LWG（Jacksonville 2018、Rapperswil 2018）审阅。修订记录还提到 SG14 在 2016 年 GDC 期间看过它。
- 这期间的讨论涉及它与其他错误处理方案的关系：Lawrence Crowl 的 [[P0157R0]] 讨论各种错误报告机制的适用场合，[[P0762R0]] 讨论它与 Boost.Outcome 的关系，Herb Sutter 的 [[P0709R4]] 提出确定性异常（deterministic exceptions）。在 Toronto 2017，LEWG 决定 `E` 不设默认模板实参（不默认为 `std::error_code`）。
- 提案原本以 TS 为目标。2021 年 4 月 6 日的 LEWG 电话会议决定改以国际标准为目标，相关投票为 SF 6、F 6、N 5、A 1、SA 0。
- 最终版本 [[P0323R12]]（作者为 Botet、JF Bastien 和 Jonathan Wakely）在 2022 年 2 月的线上全体会议并入 C++23（编辑报告 [[N4911]]）。

一元式（monadic）操作 `and_then`、`transform`、`or_else` 由 Sy Brand 的 [[P0798R8]] 先加给 `optional`，再由 Jeff Garland 的 [[P2505R5]] 加给 `expected`，两者都是 C++23。

```cpp run ok
#include <expected>
#include <charconv>
#include <string_view>
#include <print>
enum class parse_error { not_a_number, out_of_range };
std::expected<int, parse_error> parse_int(std::string_view s) {
    int value{};
    auto [ptr, ec] = std::from_chars(s.data(), s.data() + s.size(), value);
    if (ec == std::errc::invalid_argument) return std::unexpected(parse_error::not_a_number);
    if (ec == std::errc::result_out_of_range) return std::unexpected(parse_error::out_of_range);
    return value;
}
int main() {
    auto doubled = parse_int("21").transform([](int x) { return x * 2; });
    std::println("{}", doubled.value_or(-1));          // 42
    std::println("{}", parse_int("abc").has_value());  // false
}
```

从 N4015 到并入 C++23 用了将近八年，若从 Alexandrescu 的报告算起约十年。修订记录本身没有总结拖延的原因，但从被审阅的议题看，主要时间花在与异常、`error_code`、Outcome、确定性异常等方案的关系定位，以及接口细节（隐式转换、`void` 特化、异常类型）上。条款在 [[expected]]。

## 九、Ranges：range-v3 → Ranges TS → C++20 → 之后

### 起点

STL 用一对迭代器表示序列。Eric Niebler、Sean Parent 和 Andrew Sutton 的 [[N4128]] *Ranges for the Standard Library, Revision 1*（2014 年 10 月）提出直接以范围（range）作为算法的参数，并说明它借鉴了 Boost.Range、Adobe Source Libraries 的范围算法、Stepanov 和 McJones 的 *Elements of Programming*，以及 Stroustrup 与 Sutton 的 STL 概念设计（N3351）。论文明确选择继续以迭代器为基础（而不是像 D 语言那样以范围本身为原语），理由是迭代器作为算法基础有可靠的记录，社区在这个抽象上投入很大。它引入的一个关键改变是哨兵（sentinel）：范围的终点可以是与迭代器类型不同的类型，这样 `[first, 谓词)` 或 `[first, first + n)` 形式的序列不必伪造一个结束迭代器。论文中的示例和参考实现来自 Niebler 的开源库 range-v3。

HOPL IV §9.3.5 概括了范围库提供的三种序列表示：`(first, one_beyond_last)`、`(first, number_of_elements)` 和 `(first, termination_criteria)`。

### TS 与合并

Ranges 依赖概念（concepts），而概念直到 C++20 才进入语言，所以 Ranges 先以 Concepts TS 为基础写成 TS（[[N4560]] 是早期工作草案，[[N4685]] 是 2017 年的版本），ISO 在 2017 年发布为 ISO/IEC TS 21425:2017。合并分两步完成：2018 年 6 月 Rapperswil 会议先把标准库概念（[[P0898R3]]）并入 C++20 工作草案，Sutter 的报告称这是"Ranges TS 中第一部分"被并入；2018 年 11 月 San Diego 会议通过了 [[P0896R4]] *The One Ranges Proposal*（Niebler、Casey Carter、Christopher Di Bella），编辑报告 [[N4792]] 说这项动议带来了 208 页的措辞改动。Sutter 的 San Diego 报告引用了 Niebler 的话："If you liked the Ranges TS, you'll love C++20."

C++20 的 Ranges 位于 `std::ranges` 命名空间，原有的 `std::sort` 等算法保留不动，另有一套受约束的 `std::ranges::sort`，这样旧代码的行为不变。

```cpp run ok
#include <ranges>
#include <vector>
#include <print>
int main() {
    std::vector<int> v{1, 2, 3, 4, 5, 6, 7, 8, 9, 10};
    auto r = v | std::views::filter([](int i) { return i % 2 == 0; })
               | std::views::transform([](int i) { return i * i; })
               | std::views::take(3);
    std::println("{}", r);                                                    // [4, 16, 36]   (C++23 格式化范围)
    auto w = std::views::zip(v, v | std::views::drop(1)) | std::ranges::to<std::vector>();   // C++23
    std::println("{}", w.size());                                             // 9
}
```

### C++23 与 C++26 的补充

C++20 的 Ranges 缺少不少 range-v3 里已有的组件。Barry Revzin、Conor Hoekstra 和 Tim Song 的 [[P2214R2]] *A Plan for C++23 Ranges* 把待补的组件按优先级分档，C++23 据此加入了 `views::zip`（[[P2321R2]]）、`ranges::to`（[[P1206R7]]）、`views::join_with`、`views::chunk_by`、`views::cartesian_product`、`ranges::fold_left` 等，以及让用户自定义范围适配器支持 `|` 的 [[P2387R3]]。Revzin 的 [[P2760R1]] *A Plan for C++26 Ranges* 延续这种做法，C++26 加入了 `views::concat`（[[P2542R8]]）等组件。范围的格式化输出（[[P2286R8]]）属于下一节的 `format`。

条款在 [[ranges]]、[[range.adaptors]]、[[range.zip]]、[[range.utility.conv]]。

## 十、格式化输出：{fmt} → std::format → std::print

### 动机与起源

HOPL IV §9.3.7 说，iostream 提供了类型安全、可扩展的 I/O，但格式化能力很弱，有些人也不喜欢用 `<<` 分隔输出值；`format` 库提供类似 `printf` 的格式串写法，同时保持类型安全和可扩展，主要是 Victor Zverovich 的工作。

`std::format` 的原型是 Zverovich 维护的开源库 {fmt}。根据该库的更新日志，它原名 C++ Format（cppformat），在 2016 年 5 月发布的 3.0.0 版中为了与命名空间和宏前缀一致而改名 fmt。

### 提案过程

Zverovich 在 2019 年的博客文章 *std::format in C++20* 中按会议记录了提案过程，下面的时间线取自该文：

- 2016 年 8 月，他在 Reddit 上征求意见，随后在 GitHub 上提交初稿。
- 2017 年 7 月 Toronto，R0（[[P0645R0]]）首次提交给 LEWG，反响正面；委员会要求支持编译期处理格式串、输出迭代器、预先计算输出长度，并提供性能测试。
- 2018 年 3 月 Jacksonville（R1），确定采用 Python 风格的 `{}` 语法，不用 `%`，并批准用户可扩展格式语法；新增的 `format_to_n` 也来自这次的要求。
- 2018 年 6 月 Rapperswil（R2），Unicode 支持拆到单独的论文；决定以国际标准而不是 Library Fundamentals TS 为目标；委员会要求浮点数默认格式能精确往返。
- 2018 年 11 月 San Diego（R4），批准类型擦除的 `vformat` API 和 `std::formatter<T>` 特化这种扩展方式；浮点默认格式定为最短的正确舍入表示（通过 `std::to_chars`）。提案转入 LWG 做措辞审阅。
- 2019 年 2 月 Kona，进一步的接口改进获批，确定进入 C++20。
- 2019 年 7 月 Cologne，最终版本 [[P0645R10]] 在措辞审阅后通过，赶在 C++20 的特性冻结之前进入委员会草案。

Stroustrup 在 HOPL IV 中提到 `format` 默认不依赖 locale，需要时可以显式传入；这在不需要 locale 信息时显著提高了性能。

```cpp run ok
#include <format>
#include <string>
#include <print>
struct Point { int x, y; };
template <>
struct std::formatter<Point> : std::formatter<std::string> {
    auto format(Point p, std::format_context& ctx) const {
        return std::formatter<std::string>::format(std::format("({}, {})", p.x, p.y), ctx);
    }
};
int main() {
    std::println("{}", std::format("{:>8}|{:<6.2f}|{:#x}", "abc", 3.14159, 255));   //      abc|3.14  |0xff
    std::println("{}", Point{1, 2});                                                // (1, 2)
}
```

### 编译期检查与后续

C++20 刚发布时，格式串错误要到运行期才以异常报告。Zverovich 的 [[P2216R3]] *std::format improvements* 改为在编译期检查格式串（格式串参数类型变为 `consteval` 构造的 `basic_format_string`）；据 cppreference 的整理，这项改动按缺陷报告追溯适用于 C++20。于是下面的代码不能通过编译：

```cpp error
#include <format>
int main() {
    auto s = std::format("{:d}", "text");   // error: 字符串不能按 d 格式化，编译期即被拒绝
}
```

C++23 加入 `std::print` 和 `std::println`（[[P2093R14]]，2022 年 7 月线上全体会议，编辑报告 [[N4918]]）以及范围的格式化（[[P2286R8]]）。C++26 继续补充：[[P2918R2]] 为运行期才确定的格式串提供直接支持（Sutter 的 2023 年 11 月 Kona 报告），[[P3107R5]] 允许更高效地实现 `print`。条款在 [[format]]、[[format.string]]、[[format.formatter]]、[[print.fun]]。

## 十一、数值与容器：mdspan、linalg、simd、inplace_vector、hive

C++23 之后，标准库的增长重心转向了高性能计算和底层容器。这一节的组件都有较长的提案史，表中的首个版本与最终版本都可以在 wg21.link 上查到。

| 组件 | 首个版本 | 并入 | 来源与说明 |
|---|---|---|---|
| `mdspan` | [[P0009R0]]（2015，*Polymorphic Multidimensional Array View*） | C++23，[[P0009R18]]，2022 年 7 月（[[N4918]]） | 作者包括 Christian Trott、D. S. Hollman、Mark Hoemmen 等十余人；`submdspan`（[[P2630R4]]）在 2023 年 Varna 会议并入 C++26 |
| `linalg` | [[P1673R0]]（2019） | C++26，[[P1673R13]]，2023 年 11 月 Kona | 以 BLAS 为基础的自由函数接口，建立在 `mdspan` 之上；Sutter 的报告说它是这次会议上酝酿时间最长的提案 |
| `simd` | [[P0214R0]]（2016，*Data-Parallel Vector Types & Operations*） | C++26，[[P1928R15]]，2024 年 11 月 Wrocław | Matthias Kretz 的设计先进入 Parallelism TS 2，再由 P1928 并入 |
| `inplace_vector` | [[P0843R0]]（2017，名为 `fixed_capacity_vector`） | C++26，[[P0843]]，2024 年 6 月 St. Louis | 容量在编译期固定、元素就地存储的可变长数组 |
| `hive` | [[P0447R0]]（2016，名为 `colony`） | C++26，[[P0447R28]]，2025 年 2 月 Hagenberg | Matt Bentley 的设计；插入删除不使其他元素的迭代器失效 |

各组件的并入时间引自对应会议的 Sutter trip report 和 C++23 的编辑报告。`mdspan` 的多维下标写法 `m[i, j]` 依赖 C++23 的语言特性"多维下标运算符"（[[P2128R6]]），这是库需求推动语言改动的一个例子。

```cpp run ok
#include <mdspan>
#include <vector>
#include <print>
int main() {
    std::vector<double> buf(6);
    std::mdspan m(buf.data(), 2, 3);           // 2 行 3 列，默认行主序；不拥有内存
    for (std::size_t i = 0; i < m.extent(0); ++i)
        for (std::size_t j = 0; j < m.extent(1); ++j)
            m[i, j] = 10.0 * i + j;
    std::println("{}", buf);                   // [0, 1, 2, 10, 11, 12]
}
```

截至写作时，本机 libc++ 已提供 `mdspan`，但还没有 `<linalg>`、`<simd>`、`<inplace_vector>` 和 `<hive>` 头文件。

`hive` 的标准化引起过一场关于标准库范围的公开争论。Jonathan Müller、Zach Laine、Bryce Adelstein Lelbach 和 David Sankel 在 [[P3001R0]]（2023 年 10 月）中提出，标准库擅长的是需要编译器支持的设施、核心词汇类型、跨平台操作系统抽象和基础算法与数据结构；而高性能容器的价值在于持续跟进硬件和算法的进步，标准化之后接口和 ABI 都被冻结，实现质量又因厂商而异，所以 `hive` 这类容器"不适合"标准库。他们还写道，委员会已经决定不做"standard library 2.0"，所以标准化了什么就得一直背着。提案方的立场是 `hive` 已有成熟的参考实现和广泛使用，标准化可以让用户不依赖外部库就获得它。`hive` 最终在 2025 年 2 月通过。第十三节会再谈这类争论。

条款在 [[views.multidim]]、[[linalg]]、[[simd]]、[[inplace.vector]]、[[hive]]。

## 十二、ABI 稳定性：布拉格 2020

### 背景：C++11 的那次断裂

C++11 对 `basic_string` 和 `list` 的要求改变了它们的实现方式：[[diff.cpp03.strings]] 记载 `basic_string` 不再允许引用计数实现，[[diff.cpp03.containers]] 记载容器的 `size()` 必须是常数时间。libstdc++ 的文档说明，GCC 5.1 为此引入了新的库 ABI，其中包含 `std::string` 和 `std::list` 的新实现，这些改动是"为了符合 2011 年的 C++ 标准"。为了不让旧二进制失效，libstdc++ 从此同时提供新旧两套 ABI（dual ABI）。

此后的 C++14、C++17、C++20 都尽量没有破坏 ABI。Titus Winters 在 [[P1863R1]] 中写道，过去三个版本"尽我们所能地保持了 ABI 稳定"，并说实现者已经非常清楚地表明，C++11 的那次断裂昂贵而痛苦。

### P1863 与 P2028 提出了什么

2020 年 1 月，Winters 提交了两篇论文。[[P2028R0]] *What is ABI, and What Should WG21 Do About It?* 介绍 ABI 的概念，估计断裂的价值，并列出如果决定断裂应当修改的东西。[[P1863R1]] *ABI - Now or Never* 是一篇立场论文，要点如下（均为论文原意的转述）：

- 有一部分性能因为 ABI 而无法收回：不能消除按值传递 `unique_ptr` 的开销；不改变全局重新编译，就不能修改 `std::hash` 或 `unordered_map` 的类布局。他估计 API 兼容、但布局不同的 `unordered_map`/`std::hash` 实现平均可以快 200–300%。`std::string` 的 SSO 调优预计能带来约 1% 的整体性能提升，但同样被 ABI 约束挡住。所有这类问题加起来，可能是 5–10% 的总体性能损失。
- 断裂的代价同样巨大。Google 的服务器生态几乎全部从源码构建，即便如此，最近一次破坏 ABI 的标准库修改也花了他们 5–10 个工程师年；整个 C++ 生态的代价应以"工程师千年"计。
- 他认为委员会只有三个真正的选项：选定一个版本（C++23 或 C++26）作为 ABI 断裂点，提前通知并提供工具；明确承诺 ABI 稳定，把现状正式化；或者什么也不决定，延续现状。他认为第三种最坏，即嘴上说性能优先、投票时却按 ABI 优先。

论文还说，如果选择 ABI 稳定，就应当公开告诉用户：需要极致性能的人应该使用 Boost、Folly、Abseil 这类库，标准库是用于兼容和稳定的。

### 布拉格会议实际投票了什么

2020 年 2 月的布拉格会议上，EWG 和 LEWG 就这两篇论文开了联合会议。需要说清楚的是，被表决的不是 P1863 本身（它不是要并入标准的提案），而是一组关于 ABI 政策方向的民意测验（straw poll）。会议的讨论记录 [[P2130R0]] 中，EWG 主席 JF Bastien 的报告这样概括结果：

- 有些投票结果难以解释。委员会决定不承诺 ABI 稳定。
- 多数人认为应当在每个 C++ 版本中考虑渐进的 ABI 变化。他强调这是说会考虑，不是说会去做。
- 对 C++23 进行大规模 ABI 断裂没有达成共识，但有很多人支持。
- 支持在将来某个时间进行大规模 ABI 断裂的人要多得多，但仍有 14 票强烈反对。他说严格来讲这不算强共识，但足以去考虑这样的断裂，而考虑不等于会做。
- 另有一项投票：当性能和 ABI 兼容性的冲突无法调和时，应优先考虑性能。赞成票多于反对票，但强烈反对的票很多。

Sutter 的会议报告给出的概括是：投票表明委员会肯定不愿意永远保证纯粹的 ABI 稳定，准备考虑可能需要在某些平台上对受影响的类型和函数做 ABI 断裂或迁移的提案（尤其是能带来性能提升的），但还没有准备好在整个标准库范围内进行广泛的 ABI 断裂。他把这称为对提案作者的邀请，请他们把因 ABI 被否决的提案重新带回来。Botond Ballo 的报告说这些投票远非一致，他归纳的主要倾向是：希望在某个时候断裂 ABI，但不是现在；比起完全断裂，更愿意接受部分断裂；一个库提案不应仅仅因为会破坏 ABI 就被自动否决。Corentin Jabot 在博客文章 *The Day The Standard Library Died* 中评论说，这些投票都有明显多数但没有共识，并指出投票措辞里断裂的时间点并不确定。

换句话说，布拉格没有选择 P1863 列出的前两个选项中的任何一个：既没有定下断裂的版本，也没有承诺永远稳定。

### 之后的立场

方向组的 [[P2000R4]]（2022）§7.2.2 表示，ABI 断裂应当按每个提案的具体得失来考虑，不认为把某个标准版本标为"可以断裂 ABI 的机会"是健康的做法；为此设立了 ABI 评审组（ABI Review Group），为可能破坏 ABI 的提案评估影响，该组只提供建议。2024 年 11 月 Wrocław 会议上，EWG 投票把 Herb Sutter 的 [[P3466R1]] *(Re)affirm design principles for future C++ evolution* 变为常设文件（Sutter 的报告给出的票数是 29 赞成、22 中立、2 反对）。其中一条原则是，与旧版 C++ 的链接兼容应当是默认要求，可以逐案决定接受 ABI 断裂，但必须明确讨论并记录理由。

### 被 ABI 挡住的东西

下面这些是文档中明确记载的、因 ABI 无法修改或无法通过的例子：

| 对象 | 问题 | 出处 |
|---|---|---|
| `unordered_map`、`std::hash` | 改进布局和哈希函数需要全局重新编译 | [[P1863R1]] |
| 按值传递 `unique_ptr` | 调用约定决定它不能放在寄存器里 | [[P1863R1]] |
| `std::string` | SSO 调优属于 ABI 改动 | [[P1863R1]] |
| `std::regex` | 布拉格会议上 SG16 因"严重的 ABI 考虑"否决了一项 regex 提案；有志愿者准备提出弃用 regex | [[P2130R0]]，SG16 主席 Tom Honermann 的报告 |

`std::regex` 的情况值得多说一句。同一份会议记录里，Peter Bindels 在 SG16 报告之后发言说，弃用 `std::regex` 的理由是它无法修复、无法使用。改进它的实现往往需要改变类的布局或内部模板的签名，而这些已经被编译进了用户的二进制文件。[[P3001R0]] 把 `std::vector<bool>`、`std::unordered_map` 和 `std::regex` 并列为不够好、但又没有坏到可以移除、所以"会一直留下"的设施。

!!! note "ABI 不是标准的概念"
    标准正文里没有 ABI 这个词，它只规定程序的可观察行为。ABI 约束来自实现：Itanium C++ ABI 规定了类布局、调用约定和名字修饰，标准库实现又在此之上固定了各个类的数据成员。改变一个类的数据成员，或改变一个函数模板的签名（从而改变修饰名），就会让新旧代码在链接或运行时不一致。参见 [[toolchain/name-mangling]] 和 [[toolchain/linking-and-symbols]]。

## 十三、未能进入标准的提案

### Networking TS

HOPL IV §8.8.1 记载了这段历史：Christopher Kohlhoff 从 2003 年开始开发 Asio，2005 年进入 Boost，2006 年提交给标准委员会（[[N2054]] 以 TR2 为目标），2018 年成为 TS（工作草案 [[N4771]]，编辑 Jonathan Wakely）。Stroustrup 写道，尽管有 13 年的大量生产使用，它没能进入 C++17，进入 C++20 的工作也停滞了。原因是委员会还在严肃讨论怎样最好地泛化 Asio 等库中的并发处理方式，也就是 executors 提案（[[P0443R14]]）。Stroustrup 把 C++20 没有 executors 和网络库视为"至善是善之敌"的一个例子。Sutter 的 2018 年 11 月 San Diego 报告说，委员会决定把网络库的目标定在 C++20 之后不久（即 C++23），而网络库依赖于 executors。

2021 年秋天，问题集中到了异步模型上。Ville Voutilainen 代表芬兰国家机构提交 [[P2464R0]]，认为不应按当前设计标准化 Networking TS，因为它所用的 P0443 executor 只是"工作提交者"，无法得知提交的工作是否成功，因而无法进行通用的错误处理。Kohlhoff 等人以 [[P2469R0]] 回应，题目就是 *The Networking TS is baked, P2300 Sender/Receiver is not*。Kohlhoff 还在 [[P2444R0]] 中阐述了 Asio 的异步模型。

2021 年 10 月，LEWG 和 SG1 用电子投票就此表决，投票题目见 [[P2452R0]]，结果见 [[P2453R0]]：

| 投票内容 | SF | WF | N | WA | SA | 结果 |
|---|---|---|---|---|---|---|
| Networking TS/Asio 的异步模型（P2444）是大多数异步用例（包括网络、并行和 GPU）的良好基础 | 5 | 10 | 6 | 14 | 18 | 弱共识反对 |
| sender/receiver 模型（P2300）是大多数异步用例的良好基础 | 24 | 16 | 3 | 6 | 3 | 共识赞成 |
| 停止把 Networking TS/Asio 设计作为标准库的网络方案 | 13 | 13 | 8 | 6 | 10 | 无共识 |
| 标准库中的网络应基于 sender/receiver 模型 | 17 | 11 | 10 | 4 | 6 | 弱共识 |
| 可以在标准库中提供不支持安全套接字（TLS/DTLS）的套接字网络 | 9 | 13 | 5 | 6 | 13 | 无共识 |

结果文件特意写明了这些投票不意味着什么：第一项不意味着 Asio 模型不适合网络本身；第三项不意味着 Networking TS 已经死了，但作者需要做大量工作来建立共识，而且设计修改和共识形成几乎不可能快到赶上 C++23。关于 TLS，赞成方认为不安全的部分是安全部分的构件，而且 ABI 会成为 TLS 支持的大问题；反对方认为与互联网上的许多站点通信需要安全套接字，不提供它是不负责任的。

此后 sender/receiver 框架 `std::execution`（[[P2300R10]]）在 2024 年 6 月的 St. Louis 会议并入 C++26（Sutter 的报告）。网络库没有进入 C++26。基于 sender/receiver 的网络接口（[[P2762R2]]，Dietmar Kühl）和基于 IETF TAPS 的方向（[[P3185R0]]、[[P3482R0]]）仍在提案阶段。条款 [[exec]] 讲的是 `std::execution` 本身。

### 2D 图形：P0267

Guy Davidson 在 [[P0988R0]] *Ruminations on 2D graphics in the C++ International Standard*（2018 年 4 月）中回顾了这个提案的经过，下面的过程和票数取自该文：

- 2013 年 9 月芝加哥会议，成立了由 Herb Sutter 主持的 SG13（图形）研究组，建议从一个现有库出发，把它改造成现代 C++ 接口。
- 2014 年，Michael McLaughlin 提出了对 Cairo 的机械转换（[[N3888]] 起），在 Issaquah 和 Rapperswil 都受到欢迎。
- 2016 至 2017 年，提案以 [[P0267R0]] 起的编号在 LEWG 审阅。2017 年 7 月 Toronto 会议上，"是否希望以 TS 形式提供图形支持"的投票为 9|3|0|1|0。
- 2018 年 3 月 Jacksonville，作者认为 API 和措辞已可交给 LWG，但有人认为这个提案已不适合进入国际标准：文本超过 140 页，LWG 核对措辞要花掉整整两次会议，而 LWG 和 LEWG 每次会议处理的论文都少于收到的论文；也有人认为国际标准里根本不该有 2D 图形 API，或认为这套 API 停留在 1990 年代。"是否把论文推进到 LWG"的投票为 1|3|3|3|2。

2018 年 6 月 Rapperswil 会议专门安排了晚间讨论。据 Botond Ballo 的报告，一篇主张坚持原方向的论文和一份更轻量的替代方案（[[P1062R0]] *Diet Graphics*）都没有获得推进的共识，图形 TS 暂时被放弃；他提到的顾虑之一是专业图形程序员和游戏开发者不太可能使用这个库，因此逐字审阅措辞不值得占用委员会时间。Sutter 的报告写道，委员会决定此时不再以任何形式继续图形方面的工作，但 io2d 项目会继续，并会在包管理器上提供。此后 P0267 又发布了几个修订版（最后一版是 2019 年 10 月的 [[P0267R10]]），但没有再进入表决流程。

值得注意的是，方向组的 [[P2000R4]] 在 2022 年仍把"简单的图形和交互"列为具体建议之一，希望标准库提供带基本几何绘图、文本渲染的图形画布和简单的输入 API，理由主要是教学：学生不能指望在第一天就去下载安装第三方库。这说明标准库该覆盖多大范围，委员会内部并没有统一的看法。

## 十四、标准库加固（C++26）

C++26 新增了[[g:hardened-implementation|加固实现]]（hardened implementation）的概念。按当前草案 [[intro.compliance#8]]，一个实现是否是加固实现由实现定义；在加固实现中，违反[[g:hardened-precondition|加固前置条件]]会导致契约违反。[[structure.specifications#3.5]] 规定，加固实现在调用函数时，会在任何其他可观察副作用之前，以终止语义求值描述这些前置条件的契约断言；在非加固实现中，违反加固前置条件仍是未定义行为。

这项改动来自 Apple 的 Konstantin Varlamov 和 Louis Dionne 的 [[P3471R4]] *Standard library hardening*，它在 2025 年 2 月 Hagenberg 会议通过（Sutter 的报告）。提案说，它基于两位作者在 libc++ 中实现加固模式并广泛部署的经验。论文列出的动机和设计原则包括：

- 三大标准库实现都已有某种加固或调试模式，但覆盖范围、性能保证和启用方式各不相同，标准化可以提供可移植的保证。
- 只检查已有的前置条件（如 `vector::operator[]` 的下标范围、`optional::operator*` 要求有值），不新增前置条件；检查全部前置条件明确不是目标。
- 开销要低到可以在生产环境中开启。论文引用 Google 的公开报告：在数亿行代码上部署后性能影响低至 0.3%，并发现了一千多个缺陷。
- 设计上避免要求改变实现的 ABI，使实现可以允许加固代码和非加固代码混在同一个程序中。

提案的修订记录显示，R0 最初规定违反时"以实现定义的方式终止"，R1 起改为基于 C++26 契约（[[P2900R14]]）的契约违反。加固的范围见当前草案中的 `__cpp_lib_hardened_*` 特性测试宏，涵盖 `array`、`vector`、`span`、`string_view`、`optional`、`expected`、`mdspan` 等。

```cpp ub
#include <vector>
#include <cstdio>
int main() {
    std::vector<int> v{1, 2, 3};
    std::printf("%d\n", v[3]);   // UB: 非加固实现中越界访问；加固实现中是契约违反，程序终止
}
```

用 libc++ 时，可以用 `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_FAST` 打开它的加固模式。本机 Clang 23 以 `-O2` 和该宏编译上例，程序在越界访问处以 trap 终止（退出码 133，即 SIGTRAP），而不是读取越界内存。2024 年 11 月 Wrocław 会议上，EWG 审阅 P3471R0 时一致通过（Sutter 的报告称"没有人投中立票"）。

## 十五、标准库应该多大

上面几节反复出现同一个问题：什么东西应当进入标准库。各方的立场都有文档可查。

第一种看法来自对 C++98 的回顾。[[P2000R4]] §5.3 说，第一份标准制定初期提出过几条纳入原则：语言支持、人人都需要的设施、独立开发的库之间通信所需的设施。方向组认为这些原则合理，但实践中作用不大：各个组件被单独打磨甚至过度设计（它举的例子是 `std::string`），彼此不能很好地配合，风格差异明显；是 Stepanov 的 STL 以一个连贯、完整的设计"把我们从灾难中救了出来"。方向组因此建议每个新特性都要有人明确考虑它与其他特性的交互，并鼓励讨论标准库应该包含什么、不包含什么。

第二种看法把标准库看作获得兼容性的工具。[[P1863R1]] 提出，如果委员会选择 ABI 稳定，标准库的定位可能需要改变：它是用来获得兼容性和稳定性的，追求极致性能的用户应当使用外部库；标准库的设计应更多考虑面对需求变化的灵活性，而不是纯粹的性能。

第三种看法主张克制。[[P3001R0]] 列出了标准库擅长的四类东西（需要编译器支持的设施、词汇类型、跨平台操作系统抽象、基础算法与数据结构），认为高性能容器以及图形、网络这类大型设施不属于这些类别，标准化它们要付出大量委员会时间，结果却是一个接口和 ABI 都被冻结、实现质量不一的组件。[[P3023R1]]（Sankel）主张委员会应当更多地说"不"，以 `std::function` 的三个替代品为例批评复杂度的增长，同时提出了一些他认为值得做的方向，如更现代的哈希容器接口、JSON 解析和命令行解析。

第四种看法主张覆盖更多领域。[[P2000R4]] §5.4 建议提供网络（"我们迫切需要网络"）、简单图形与交互、对现代硬件（executors、SIMD、并发数据结构）的支持。它的理由之一是教学：学生应当能只用每个实现都提供的东西开始学习。

这些立场并不完全对立。P3001R0 承认词汇类型和操作系统抽象应当标准化，P2000R4 也强调一致性和连贯性。分歧主要在于具体组件属于哪一类，以及委员会的时间应当优先花在哪里。从结果看，C++26 同时接纳了 `hive`、`simd`、`linalg` 这类领域性组件，也没有接纳网络库。

## 时间线

| 年份 | 事件 | 出处 |
|---|---|---|
| 1998 | C++98 发布；3 月 Sophia Antipolis 会议期间 Klarer 与 Dawes 讨论建立 Boost，Dawes 随后发布库仓库网站提案 | HOPL III、HOPL IV、Boost 历史页面 |
| 1999 | Boost 第一个正式发行版，24 个库 | Boost 历史页面 |
| 2001 | 委员会开始编写库技术报告 | HOPL III |
| 2002 | Boost.Filesystem；Hinnant 等提出移动语义与 unique_ptr 的早期方案 | HOPL IV |
| 2004 | TR1 技术内容以全票通过 | HOPL III |
| 2005 | TR1 草案 [[N1836]]；[[N1856]] 提议弃用 `auto_ptr`、新增 `unique_ptr`；Asio 进入 Boost | 原文、HOPL IV |
| 2007 | ISO 发布 TR1（ISO/IEC TR 19768:2007） | ISO 目录 |
| 2008 | chrono 提案 [[N2661]] | 原文 |
| 2011 | C++11：TR1 大部分并入 `std`，加入 chrono、`unique_ptr`，弃用 `auto_ptr` | HOPL IV |
| 2014 | [[N4015]]（expected）；[[N4128]]（Ranges）；文件系统 TS 文本 [[N4100]] | 原文 |
| 2015 | 文件系统 TS（ISO/IEC TS 18822:2015）；Library Fundamentals TS；variant 在 Kona 达成妥协 | ISO 目录、[[N4480]]、[[P0088R3]] |
| 2016 | Jacksonville：文件系统、Library Fundamentals 大部分、并行算法并入 C++17；Oulu：variant 并入 | Sutter 报告、[[N4583]] |
| 2017 | C++17 发布，移除 `auto_ptr`；Ranges TS（ISO/IEC TS 21425:2017）；`format` 首次提交 | [[N4190]]、ISO 目录、Zverovich |
| 2018 | Jacksonville：日历与时区并入 C++20，图形提案失去推进共识；Rapperswil：标准库概念并入，图形工作搁置；Networking TS 发布；San Diego：Ranges 并入 | Sutter、Ballo 报告，[[P0988R0]]，[[N4792]] |
| 2019 | Cologne：`std::format` 并入 C++20 | Zverovich |
| 2020 | 布拉格：ABI 政策投票（不承诺 ABI 稳定，C++23 不做大规模断裂）；C++20 发布 | [[P2130R0]]、Sutter 报告 |
| 2021 | 10 月：`move_only_function` 并入；LEWG 关于 Networking 与 sender/receiver 的电子投票 | [[N4902]]、[[P2453R0]] |
| 2022 | 2 月：`expected` 并入；7 月：`mdspan`、`print` 并入 C++23 | [[N4911]]、[[N4918]] |
| 2023 | Varna：`function_ref`、`copyable_function`、`submdspan` 并入 C++26；Kona：`linalg` 并入 | Sutter 报告 |
| 2024 | St. Louis：`std::execution`、`inplace_vector` 并入；Wrocław：`simd` 并入，EWG 采纳 [[P3466R1]] 为常设文件 | Sutter 报告 |
| 2025 | Hagenberg：`hive`、标准库加固、`indirect`/`polymorphic` 并入 C++26 | Sutter 报告 |

## 现状与未来

截至 2026 年，C++26 的标准库已经包含本页提到的大部分组件。从这二十多年的历史可以看出几个稳定的模式。

第一，几乎每个成功的组件都有多年的独立实现经验：Boost 的十年、range-v3 和 {fmt} 的多年开源维护、Hinnant 的 date 库、Bloomberg 内部十多年的 PMR。但实现经验并不足以保证进入标准。2D 图形提案有可用的实现（io2d），失去支持的原因是篇幅和审阅成本，以及它是否属于标准库的争议；Networking TS 有十几年的生产使用，却被异步模型的争论拖住。

第二，TS 作为中间站的作用变了。Filesystem、Library Fundamentals、Ranges 都通过 TS 进入标准；而 `expected` 在 2021 年从 TS 目标改为国际标准目标，`format` 在 2018 年也放弃了 TS 路线。这两个例子说明，近年的库提案更常直接以国际标准为目标。

第三，ABI 的约束越来越明显。布拉格的投票没有给出明确方向，后续的 [[P2000R4]] 和 [[P3466R1]] 都采取逐案评估的立场。实际效果是，已有组件的布局很难再改，改进往往以新增类型的方式出现（`function` 之后的三个包装器就是例子），这又引出了关于复杂度的批评。

仍在进行中的工作包括：基于 sender/receiver 的网络库、标准库与反射（[[meta.reflection]]）的结合、更多容器和算法的 `constexpr` 化、并发队列，以及加固范围的扩大。这些工作的结果要等将来的标准版本才能知道。

## 参考资料

**WG21 文档**（构建时链接到 wg21.link）

- TR1 与 C++11：[[N1836]]（TR1 草案）、[[N1402]]（function）、[[N1424]]（type traits）、[[N1429]]（regex）、[[N1450]]（智能指针）、[[N1456]]（哈希表）、[[N1932]]（random）、[[N1856]]（unique_ptr 与弃用 auto_ptr）、[[N2661]]（chrono）、[[N3191]]（steady_clock）、[[N3656]]（make_unique）、[[N4190]]（移除 auto_ptr）
- 文件系统与 Library Fundamentals：[[N1975]]、[[N3505]]、[[N4100]]、[[P0218R1]]、[[N4480]]、[[P0220R1]]、[[N3672]]（optional）、[[N3609]]、[[N3921]]（string_view）、[[N3916]]（PMR）、[[P0339R6]]、[[P0302R1]]、[[P0414R2]]
- variant 与 expected：[[N4542]]、[[P0088R3]]、[[N4015]]、[[N4109]]、[[P0323R12]]、[[P0157R0]]、[[P0762R0]]、[[P0709R4]]、[[P0798R8]]、[[P2505R5]]
- 函数包装器：[[P0288R9]]、[[P2548R6]]、[[P0792R14]]
- 时间：[[P0355R7]]、[[P1361R2]]
- Ranges：[[N4128]]、[[N4560]]、[[N4685]]、[[P0898R3]]、[[P0896R4]]、[[P2214R2]]、[[P2321R2]]、[[P1206R7]]、[[P2387R3]]、[[P2760R1]]、[[P2542R8]]
- 格式化：[[P0645R0]]、[[P0645R10]]、[[P2216R3]]、[[P2093R14]]、[[P2286R8]]、[[P2918R2]]、[[P3107R5]]
- 数值与容器：[[P0009R0]]、[[P0009R18]]、[[P2128R6]]、[[P2630R4]]、[[P1673R0]]、[[P1673R13]]、[[P0214R0]]、[[P1928R15]]、[[P0843R0]]、[[P0843]]、[[P0447R0]]、[[P0447R28]]、[[P3001R0]]
- ABI：[[P1863R1]]、[[P2028R0]]、[[P2130R0]]（布拉格会议讨论记录）、[[P3466R1]]
- 网络与图形：[[N2054]]、[[N4771]]、[[P0443R14]]、[[P2444R0]]、[[P2464R0]]、[[P2469R0]]、[[P2452R0]]、[[P2453R0]]、[[P2300R10]]、[[P2762R2]]、[[P3185R0]]、[[P3482R0]]、[[N3888]]、[[P0267R0]]、[[P0267R10]]、[[P0988R0]]、[[P1062R0]]
- 方向与加固：[[P2000R4]]、[[P3023R1]]、[[P3471R4]]、[[P2900R14]]
- 编辑报告：[[N4583]]（2016 年 3 月）、[[N4792]]（2018 年 11 月）、[[N4902]]（2021 年 10 月）、[[N4911]]（2022 年 2 月）、[[N4918]]（2022 年 7 月）

**论文与书**

- Bjarne Stroustrup, *Evolving a language in and for the real world: C++ 1991–2006*, HOPL III, 2007。§4.2（Boost）、§6.2（Library TR）。
- Bjarne Stroustrup, *Thriving in a Crowded and Changing World: C++ 2006–2020*, Proc. ACM Program. Lang. 4, HOPL (2020)。§2.3、§4.2.4、§4.6、§8.3、§8.6、§8.8.1、§9.3.5–§9.3.8。

**会议报告与文章**

- Herb Sutter 的 trip report：Jacksonville（2016 年 3 月）、Oulu（2016 年 6 月）、Jacksonville（2018 年 3 月）、Rapperswil（2018 年 6 月）、San Diego（2018 年 11 月）、Prague（2020 年 2 月）、Varna（2023 年 6 月）、Kona（2023 年 11 月）、St. Louis（2024 年 6 月）、Wrocław（2024 年 11 月）、Hagenberg（2025 年 2 月），均见 herbsutter.com。
- Botond Ballo, *Trip Report: C++ Standards Meeting in Rapperswil, June 2018*；*Trip Report: C++ Standards Meeting in Prague, February 2020*。
- Christof Meerwald 关于 2013 年 9 月芝加哥会议的博客记录（cmeerw.org）。
- Victor Zverovich, *std::format in C++20*（2019）；{fmt} 更新日志（3.0.0 版改名说明）。
- Corentin Jabot, *The Day The Standard Library Died*（2020）。
- Boost 官方历史页面（*History of Boost*）。
- libstdc++ 手册 *Dual ABI* 一节。
