---
title: STL 与 C++98 标准库的诞生
summary: 从 AT&T 的 task、complex 与 iostream 库，到 Stepanov 的 STL 在 1993–1994 年进入草案；被砍掉的哈希表、为分段内存设计的分配器、按字符类型模板化的 iostream 与 string、写时复制字符串被 C++11 排除、vector<bool> 与 auto_ptr 的长期争议、valarray 的来历，以及这些 1990 年代的决定如何留在今天的条文里。
status: draft
order: 60
since: c++98
papers: N1456, N1836, N1847, N2160, N2204, N2353, N2534, N2668, N1850, N2982, N1232, N1856, N4190, P0174R2, P0619R4
tags: 标准库, STL, 泛型编程, 分配器, iostream, string, vector<bool>, auto_ptr, valarray, C++98, C++03
related: library, containers, iterators, algorithms, basic.string, vector.bool, input.output, default.allocator, allocator.traits, unord, char.traits, localization, numarray, unique.ptr
updated: 2026-10-18
---

C++98 标准有 700 多页，其中一半以上在讲标准库。可是作为标准化起点的参考手册（*The C++ Programming Language* 第二版的附录）里，标准库只占一页（HOPL III §4）。从一页到三百多页，中间发生的事情大部分集中在 1993 年到 1997 年：Alexander Stepanov 的 STL 在最后时刻被接纳，iostream 和 string 被改写成以字符类型为参数的模板，分配器、`auto_ptr`、`vector<bool>`、`valarray` 这些后来争议不断的组件也在这几年里定型。

本页按时间顺序讲这段历史。读者会发现，今天标准里很多看起来别扭的条文都能在这里找到来由。[[default.allocator]] 只剩下三个成员函数，是因为 1994 年为 16 位分段内存设计的那些成员后来被逐个删掉了。[[vector.bool]] 至今不满足容器要求，是因为委员会讨论了十年也没找到不破坏现有代码的改法。[[zombie.names]] 里保留着 `auto_ptr` 的名字，是因为它被弃用、又被移除。[[string.require]] 里那串关于引用失效的列表，则是 C++11 为了排除写时复制实现而改写过的版本。

关于出处：本页的主要依据是 Stroustrup 的两篇 HOPL 论文、Stepanov 本人的访谈与回顾、Stepanov 与 Meng Lee 的 STL 技术报告，以及相关的 WG21 文档和 LWG issue。几份资料在个别日期上有出入，正文中会注明。

## 一、标准化之前：AT&T 的几个库（1980–1990）

### task、complex 与 stream

C with Classes 写出的第一批真正的代码是 task 库，它提供 Simula 风格的协程式并发，用于网络流量、电路板布线这类模拟（HOPL II §5.3）。Stroustrup 在 1984 年前后设计了复数库，与 Leonie Rose 一起实现（HOPL II §3）。复数库的说明后来收入 1985 年 11 月的 AT&T C++ 翻译器发行说明（HOPL III 参考文献 [91]）。

I/O 方面，C 的 `printf` 家族不是类型安全的，也无法扩展到用户定义的类型。Stroustrup 在 1984 年实现了第一版 stream I/O 库，用重载的 `<<` 作为输出运算符；用运算符而不是具名函数来做输出，是 Doug McIlroy 的建议（HOPL II §5.3.1）。随后 Dave Presotto 在不改接口的前提下重新实现了它。

1989 年 6 月发布的 Cfront 2.0 带来了 Jerry Schwarz 重写的 iostream 库。按 HOPL II 的说法，Schwarz 部分重新设计了这个库，让它适用于更多类型的应用、文件 I/O 更高效，并采用了 Andrew Koenig 提出的操纵符（manipulator）来控制格式。也正是在 stream 的使用经验推动下，C++ 修改了重载规则，让 `char` 被当作字符而不是小整数处理：在 1.x 版本里，`cout << 'a'` 输出的是一串数字。

这一代 iostream 的头文件叫 `<iostream.h>`，名字都在全局命名空间里。下面是那个年代常见的写法，仅作展示，今天的编译器不再提供这个头文件：

```cpp title="历史代码：标准化之前的 iostream（约 1990 年）"
#include <iostream.h>          // 预标准头文件，名字在全局命名空间

int main()
{
    cout << "x = " << 42 << endl;   // 没有 std::
    return 0;
}
```

C++98 把这些名字移进了 `std`，头文件改为不带 `.h` 的 `<iostream>`（见 [[headers]]）。

### 容器为什么迟迟没有出现

字符串、带范围检查的数组、动态数组、链表，这些类型在早期一直被用作设计和测试 C++ 的例子。Jonathan Shopiro 在 1983 年写的 list 和 string 类在 AT&T 内部用得很广，后来成为 USL 销售的 Standard Components 库的基础（HOPL II §5.3）。但在模板出现之前，参数化类型只能用宏来模拟，容器库始终停留在小范围使用的阶段。

Stroustrup 在 HOPL II（§7.3）里把这件事称为他最大的错误：1.0 版和《C++ 程序设计语言》第一版应该推迟发布，等到有了一个包含链表、关联数组、带范围检查的数组和简单字符串类的库再说。他的解释是，没有模板就写不好容器类。结果每个团队都在重新发明这些基础类，C++ 社区里出现了大量互不兼容的容器库，例如 Keith Gorlen 的 NIH 类库、Rogue Wave 和 Dyad 的商业库等（HOPL II §5.3.2）。

这些早期库多数采用 Simula 和 Smalltalk 的模式：元素必须派生自某个公共基类（`Object` 或 `Link`），容器里存的是指向基类的指针。HOPL III（§4.1.1）列出了 Stroustrup 不接受这种设计的理由：内建类型（如 `int`）放不进去，取出元素要做向下转型，不是静态类型安全的，而且每次访问都多一层间接。他想要的是能直接容纳内建类型、静态类型安全、没有额外开销的容器，而这在 1985 年的 C++ 里做不到。

## 二、标准库应该有多大

1990 年初，C++ 的定义工作交给了 ANSI 的 C++ 委员会（HOPL II §4），随后 ISO 的 WG21 也加入进来。委员会面前有两个参照物：一边是很小、各方都接受的 C 标准库，另一边是各家公司庞大的基础类库。Stroustrup 在标准化早期提出的指导方针（HOPL III §4.2 引述）大意是：

- 已经被普遍使用的关键库必须标准化，具体是 C++ 与 C 标准库的接口、iostream 和语言支持部分；
- 对于大家普遍要求的 string 之类的常用类，委员会要设法回应，但不能陷入委员会设计，也不能和商业库厂商竞争；
- C 库和 iostream 之外，委员会接受的库应当是积木（building blocks），而不是更大的框架。标准库的主要作用是让分别开发的库之间更容易互通。

这条方针后来被解读为对效率和通用性的极高要求。Stroustrup 常用的例子是：如果访问元素要经过虚函数调用，这个容器就不够高效；如果容器不能容纳任意类型，它就不够通用。

在 STL 出现之前，委员会讨论的库提案仍然以传统的类层次为主。1994 年的 San Diego 会议通过了以字符类型为模板参数的 string（HOPL III §3.2 年表）。这时离委员会原先设想的完成时间已经不远，按照 Stepanov 的回忆，上一次会议甚至通过了一项决议，不再接受大型提案（Dr. Dobb's 访谈，1995）。

## 三、Stepanov 与泛型编程的来路

STL 背后的思想比 C++ 标准化早了十几年。Stepanov 为 HOPL III 写过一段自述（HOPL III §4.1.8，原文另见 stepanovpapers.com 上的 *Short History of STL*），按时间可以整理如下：

| 时间 | 事件 |
|---|---|
| 1976 年 10 月 | 注意到并行归约算法与幺半群（具有结合运算的集合）相关联，由此认为每个有用的算法都可以与一个数学理论关联起来 |
| 1980 年 | 与 Dave Musser、Deepak Kapur 开始设计 Tecton 语言，用代数理论描述算法；这是一门函数式语言 |
| 1984 年 | 与图算法专家 Aaron Kershenbaum 合作，在 Scheme 里写了一大批泛型组件；Kershenbaum 让他认识到很多基本算法依赖随机访问，数组必须认真对待 |
| 1980 年代中后期 | Scheme 的工作带来了一笔经费，与 Musser 用 Ada 写了一个泛型库（处理链式结构），1989 年以 *The Ada Generic Library* 为名出版；同时与 Musser 发表论文，提出泛型编程的概念 |
| 1987 年 | 在 Bell Labs 工作期间，Andrew Koenig 给他讲了 C 的语义，C 背后的抽象机器对他是一个启发；但他认为当时的 C++ 还不足以承载这些想法 |
| 1993 年 | 在 HP Labs，经过五年做其他项目之后回到泛型编程 |

Stepanov 说他从 Ada 那里学到的最重要的东西是，静态类型可以作为设计工具。而他在 Ada 里没能完成的部分，是写出对链表和数组都适用的算法；他手里有很多与后来 STL 算法等价的 Ada 代码，但当时的 Ada 编译器编译不了。

他与 C++ 模板的关系也有一段插曲。按 Stepanov 在 1995 年 Dr. Dobb's 访谈中的说法，他在 Bell Labs 时曾和 Stroustrup 激烈争论，主张 C++ 的模板应该尽量像 Ada 的泛型，尤其是函数模板应该显式实例化。Stroustrup 没有采纳，函数模板可以从实参推导模板参数。Stepanov 在同一访谈里说，正是这个设计让 STL 里很多在 Ada 中不可能的写法成为可能。HOPL III（§4.1.2）从 Stroustrup 一方讲了同一件事：Stepanov 促使他更重视模板机制的通用性和效率，但幸好没能说服他把模板做成 Ada 泛型那样，否则 STL 就写不出来了。

## 四、从 San Jose 到 Waterloo（1993–1994）

这一节是整段历史里被引用最多的部分。下面的叙述以两份第一手资料为准：Stroustrup 的 HOPL III 论文 §4.1.2，以及 Stepanov 1995 年 3 月接受 Al Stevens 采访时的回忆（*Dr. Dobb's Journal*）。两者在细节上有出入的地方会分别注明。

### 1993 年：一场没有提到容器的演讲

据 Stepanov 回忆，1993 年夏天 Koenig 到斯坦福大学教一门 C++ 课，Stepanov 给他看了自己的库，Koenig 对此很感兴趣，并安排 Stepanov 在 San Jose 举行的标准委员会会议上做一次演讲。HOPL III 的记述是，Stepanov 先向 Koenig 讲解了这些想法，Koenig 试用了几天之后拿给 Stroustrup 看。Stroustrup 坦言他第一反应是困惑，觉得这种容器风格古怪、冗长，花了几个星期才适应。适应之后他发现，STL 满足了他多年来为容器总结的 12 条标准中的 11 条，只有通过公共基类提供持久化之类的公共服务这一条不满足。

演讲的题目是 *The Science of C++ Programming*。按 Stepanov 的描述，内容主要是正规类型（regular type）的公理，即构造、赋值和相等之间应当满足的关系，再加上后来称为前向迭代器的公理；没有讲任何容器，只讲了一个算法 `find`。演讲的时间，HOPL III 写的是 1993 年 10 月的 San Jose 会议；Stepanov 在 Dr. Dobb's 访谈中说是 11 月的会议，stepanovpapers.com 上保存的演讲幻灯片也标注为 1993 年 11 月 11 日，本页采用 11 月。Stroustrup 评价说，这次演讲让委员会的态度从这个阶段不可能再做大改动转向了不妨看一看。

### 1994 年 1 月到 3 月：赶在截止日期前写出提案

Stepanov 说，演讲之后他并没有想过标准的事。1994 年 1 月 6 日，身为标准文本项目编辑的 Koenig 发邮件告诉他，如果想让这个库进入标准，需要在 1 月 25 日之前提交提案。当时只有大量代码，没有文档，更没有正式的提案。Stepanov 和 Meng Lee 每周工作 80 小时赶出了提案，而在写提案的过程中又发现了许多设计缺陷，在 1 月的邮寄截止日和 3 月的下一次会议之间，几百个组件全部重新实现了一遍。

1994 年 3 月的 San Diego 会议上，Stepanov 完整介绍了 STL（stepanovpapers.com 上保存的演讲幻灯片日期为 1994 年 3 月 7 日）。按他的回忆，反对意见大多是同一种形式：这个提案太大、太晚，上次会议刚刚决定不再接受大型提案。表决的结果是绝大多数人同意在下一次会议上审议这份提案并投票。

HOPL III 正文开头的年表把 STL 列在 1994 年 San Diego 会议名下，正文则说 STL 是在 Waterloo 会议上进入标准的。两者并不矛盾：San Diego 的表决是同意审议，Waterloo 的表决才是把 STL 纳入工作草案。

### 删掉三分之二

San Diego 之后，委员会要求用新的语言特性重写 STL，其中一些特性当时还没有编译器实现。Stepanov 说他几乎每天都打电话问 Koenig 或 Stroustrup 某个写法在 C++ 里是否可行。STL 用到的两项较新的模板特性是成员模板（让容器可以从任意一对迭代器构造）和模板模板参数（最初的分配器就是这样设计的）。

1994 年晚些时候，Stepanov 在 HP 召集了一次库实现者会议，参加者有 Tom Keffer、Nathan Myers（均来自 Rogue Wave）、Meng Lee、Larry Podmolik、Mike Vilot、Stepanov 和 Stroustrup（HOPL III §4.1.2）。大家在原则和细节上达成了不少一致，但 STL 的规模成了主要障碍：对于其中很大一部分内容是否必要没有共识，委员会也担心没有时间认真审查和形式化这么大的规范。Stroustrup 回忆说，最后他应 Stepanov 的要求拿笔划掉了大约三分之二的文本，对每一项都要求 Stepanov 和其他库专家简短说明为什么不能删、为什么对大多数程序员有用。按他的说法，Stepanov 后来说这让他心碎。

### Waterloo：表决通过

Stepanov 说，到了 Waterloo，Stroustrup 花了很多时间安慰他，说这次很可能会失败，但大家已经尽力了。实际表决的结果出乎所有人意料，他估计大约 80% 赞成、20% 反对。HOPL III 记下了讨论中的两件事：Beman Dawes 告诉委员会，他原本认为 STL 对普通程序员来说太复杂，但作为练习自己实现了大约 10% 之后，不再这样认为；代表 Siemens 和德国的 Roland Hartinger 则担心接受 STL 会让他的部门花费一百万马克。这两件事都出自 Stroustrup 的回忆。

!!! note "Waterloo 会议的日期"
    HOPL III 正文写的是 1994 年 10 月的 Waterloo 会议。但 P. J. Plauger 在 1997 年 8 月的 *C/C++ Users Journal* 专栏中写的是 1994 年 7 月，Johannes Weidl 1996 年的 STL 教程更具体地写作 1994 年 7 月 14 日的会议。本页采用 1994 年 7 月。

即便删掉了三分之二，把这份精简后的 STL 改写成标准条文也让标准推迟了一年多（HOPL III §4.1.2）。纳入草案的文本以 Stepanov 和 Lee 的技术报告为基础：HP Labs 技术报告 HPL-94-34（1994 年 8 月），修订版为技术报告 95-11(R.1)（文档本身标注 1995 年 10 月 31 日，stepanovpapers.com 列为 1995 年 11 月 14 日）。Stepanov 说，STL 文档被拆开，放进工作草案中库的各个部分，这项编辑工作由库工作组组长 Mike Vilot 负责（Dr. Dobb's 访谈）。

### 名字与分工

STL 这个名字在它成为标准之前就有了。通常认为它是 Standard Template Library 的缩写；Stepanov 在 1995 年的访谈里半开玩笑地说过它代表 Stepanov and Lee，HOPL III 则引用他的另一个说法：STL 就代表 STL。

关于分工，Stroustrup 在 HOPL III 中说 STL 应当归功于 Stepanov，同时提到 Musser 与 Stepanov 近二十年的合作、Meng Lee 在 HP 参与编写最初的 STL，以及 Stepanov 与 Koenig 的邮件讨论。他说自己除了删减之外技术贡献很小：一是建议把与内存相关的信息集中到一个对象里，这就是后来的分配器；二是在 Stepanov 的黑板上画出了最初的需求表（requirements table），也就是标准至今用来描述模板参数要求的那种表格形式。Stroustrup 在同一处补充说，需求表的存在恰恰说明语言表达能力不足，这些要求本应写在代码里。这句话在二十多年后由 C++20 的概念实现了一部分（见 [[topics/concepts]]）。

### STL 的模型

STL 的核心是把容器和算法完全分开：容器以元素类型为参数，每种容器提供自己的迭代器类型，算法只通过迭代器访问元素。迭代器的接口借用指针的写法（`*`、`++`、`!=`），所以普通指针本身就是迭代器，内建数组也能直接用于所有算法。Stepanov 1993 年在 San Jose 展示的就是下面这类例子（HOPL III §4.1.3），这段代码今天仍然原样可用：

```cpp run title="find.cpp" ok
#include <algorithm>
#include <list>
#include <string>
#include <vector>

int main() {
    std::vector<int> vi{3, 7, 42};
    std::list<std::string> ls{"Koenig", "Stepanov", "Lee"};
    auto p = std::find(vi.begin(), vi.end(), 7);
    auto q = std::find(ls.begin(), ls.end(), "Stepanov");
    int a[] = {1, 2, 3};
    int* r = std::find(a, a + 3, 2);   // 内建数组和指针同样适用
    return (p != vi.end() && q != ls.end() && *r == 2) ? 0 : 1;
}
```

同一个 `find` 用于 `vector<int>`、`list<string>` 和内建数组，没有虚函数，没有公共基类，元素也不必派生自任何东西。另一项在当时很新的做法是给每个操作和算法规定复杂度（HOPL III §4.1.7）。Stepanov 认为复杂度是概念接口的一部分，这个立场后来被标准沿用：今天 [[algorithms]] 里每个算法都有 *Complexity* 段落，[[container.requirements]] 的需求表也带有复杂度一栏。

## 五、迭代器分类与 traits

### 五种迭代器

如果所有迭代器都提供同一套操作，模型会很简单，但链表、数组和输出流的本质能力确实不同：数组可以下标访问，链表只能逐个前进或后退，输入流只能读一遍。STL 因此把迭代器分成五类：输入、输出、前向、双向、随机访问（HOPL III §4.1.6）。同一个算法可以为不同类别提供不同实现，在编译期通过重载选出最合适的一个。

1995 年的 STL 技术报告（§5.6）为此定义了五个空的标签类 `input_iterator_tag` 到 `random_access_iterator_tag`，并要求每个迭代器 `i` 都能通过表达式 `iterator_category(i)` 得到它的类别标签。迭代器的值类型和距离类型也用同样的方式获取：报告里定义了重载函数 `value_type(i)` 和 `distance_type(i)`，它们返回空指针，只用来把类型传给辅助函数。报告还举了一个例子：如果平台有一种 `__huge` 指针，它的差值类型是 `long long`，就再为 `const T __huge*` 重载一组 `value_type` 和 `distance_type`。这个例子说明了当时设计时所面对的平台环境，下文讲分配器时还会遇到。

### traits 的发明

用重载函数传递类型信息既不系统，也容易出错。HOPL III（§4.1.5）说，通用的解决办法是 Nathan Myers 在把 iostream 和 string 模板化的过程中发现的，也就是 traits：用一个辅助模板集中存放某一类类型的属性。Myers 在 1995 年 6 月的 *C++ Report* 上发表了 *Traits: a new and useful template technique*，介绍这一技术。用于迭代器时，它就是 `iterator_traits`：一般的迭代器从自己的成员类型取得 `value_type`，指针则通过偏特化取得所指类型。HOPL III 提到，偏特化本身是 1995 年才加入 C++ 的；按 Stepanov 的说法，Stroustrup 在 Valley Forge 会议上提出偏特化时，动机之一就是让 STL 更高效（Dr. Dobb's 访谈）。

标签派发加上 `iterator_traits`，是 C++98 到 C++17 标准库内部的标准写法，今天依然合法：

```cpp run title="tag-dispatch.cpp" ok
#include <iterator>
#include <list>
#include <vector>
#include <cassert>

template<class It>
void my_advance(It& it, int n, std::input_iterator_tag) {
    while (n-- > 0) ++it;                 // 只能一步一步走
}
template<class It>
void my_advance(It& it, int n, std::random_access_iterator_tag) {
    it += n;                              // 常数时间
}
template<class It>
void my_advance(It& it, int n) {
    my_advance(it, n, typename std::iterator_traits<It>::iterator_category{});
}

int main() {
    std::vector<int> v{0, 1, 2, 3};
    std::list<int>   l{0, 1, 2, 3};
    auto vi = v.begin(); my_advance(vi, 2);   // 选中 random_access 版本
    auto li = l.begin(); my_advance(li, 2);   // bidirectional 派生自 input，选中 input 版本
    assert(*vi == 2 && *li == 2);
}
```

这里依赖的是标签类之间的继承关系：`bidirectional_iterator_tag` 派生自 `forward_iterator_tag`，后者又派生自 `input_iterator_tag`，所以没有专门重载的类别会通过派生类到基类的转换落到最接近的版本上。

今天的标准里，这套体系分成了两层。原来的需求表保留下来，改名为 *Cpp17InputIterator* 等具名要求（[[iterator.cpp17]]），供仍以 C++98 风格描述的组件使用；C++20 的 ranges 工作（以 [[P0896R4]] 为主）则用概念重新定义了迭代器（[[iterator.concepts]]），并增加了 `contiguous_iterator` 这一类。标签类仍在 [[std.iterator.tags]]，`iterator_traits` 仍在 [[iterator.traits]]。

## 六、被砍掉的哈希表

1994 年的删减和后续的时间压力，让一类大家都想要的容器没能进入 C++98：哈希表。HOPL III（§6.2）的说法是，如果有时间做好详细设计和规范，哈希表本来会在 C++98 里。1995 年，Javier Barreiro、Robert Fraley 和 David Musser 试图赶在标准完成前准备好一份提案，他们的工作后来成为很多 `hash_map` 实现的基础，但委员会没有时间处理。

Stepanov 本人对此有另一种说法。在 Graziano Lo Russo 对他的一次访谈中，被问到为什么哈希表没有进入 STL 时，他的回答只有一个词：政治（politics），并说哈希表理应在其中。两种说法本页都照录，不做判断。

结果是各家实现自己提供了 `hash_map`、`hash_set`。Stepanov 在 SGI 与 Matt Austern、Hans Boehm 一起完成的新版 STL 就包含哈希容器（Lo Russo 访谈）。Austern 在 2003 年的 [[N1456]] 中提出了 `unordered_set`、`unordered_map`、`unordered_multiset`、`unordered_multimap` 四个容器。论文开头回顾说，哈希表在 1995 年就曾被提交给标准，因为时间原因被否决；当时 SGI、Dinkumware、Metrowerks 三家的库都以扩展形式提供了哈希容器，彼此相似但不相同，所以提案特意换用新名字，避免与这些既有的类冲突。这份提案随后进入 2005 年的库技术报告草案 [[N1836]]（通称 TR1），最终成为 C++11 的无序关联容器（[[unord]]）。HOPL III（§6.2）对命名的解释与此一致，它说当时已经有五六种互不兼容的 `hash_map` 在使用；名字里的 unordered 指遍历顺序没有保证，因为哈希函数不像 `map` 的 `<` 那样定义一种顺序。

```cpp run title="unordered.cpp" ok
#include <string>
#include <unordered_map>

int main() {
    std::unordered_map<std::string, int> freq;
    for (const char* w : {"vector", "list", "vector"})
        ++freq[w];
    return freq["vector"] == 2 ? 0 : 1;
}
```

## 七、分配器：为分段内存而设计

### 最初的目的

分配器是 STL 里离标准化前的硬件环境最近的部分。Stepanov 在 Dr. Dobb's 访谈中说，委员会成员希望容器独立于内存模型，希望库提供某种抽象内存模型的机制，尽管语言本身并没有内存模型这个概念。早期 STL 假定容器大小可以用 `size_t` 表示、两个迭代器的距离是 `ptrdiff_t`，现在这些都要抽象掉。如果连 `size_t` 都不能假定，`T*` 也就不能假定，因为不同内存模型下有不同的指针类型；引用类型同理。于是他们发明了分配器，把内存模型的信息封装起来，这给库里的每一个组件都带来了深远的影响。他在后来的 Lo Russo 访谈里说得更直接：“I invented allocators to deal with Intel's memory architecture.”

所谓 Intel 的内存架构，指的是 16 位 x86 上的分段内存：同一个程序里可能同时有 near、far、huge 几种指针，大小和运算规则各不相同。Pablo Halpern 在 2005 年的 [[N1850]]（§4.2）中也是这样概括分配器的初衷的。1995 年的 STL 技术报告（§7）开宗明义地说，分配器用来封装内存模型的信息，包括指针类型、指针差值的类型、对象大小的类型，以及在这个模型里分配和释放内存的原语；所有容器都以分配器为参数。报告里的分配器需求表因此有 `pointer`、`const_pointer`、`reference`、`const_reference`、`size_type`、`difference_type` 等成员类型，还有 `address`、`const_address`、`allocate`、`deallocate`、`construct` 等操作。

### 为什么后来很别扭

问题在于语言本身不支持这种抽象。Stepanov 在 Lo Russo 访谈中举了一个例子：两个 `vector<int>` 使用不同的分配器，`b[1]` 返回的是第二个分配器的 `reference` 类型，未必是 `int&`，把它交给 `find` 在第一个容器里查找时就可能出现类型不匹配。他的结论是，要让分配器真正有用，必须改变核心语言处理引用的方式。他认为 `T*` 是硬编码在语言里的。

委员会最终在 C++98 里给出了一个折中。C++98 的分配器要求（当时的 20.1.5 ¶4）允许实现假定：同一类型的分配器的所有实例都可以互换、总是比较相等；并且 `pointer`、`const_pointer`、`size_type`、`difference_type` 分别就是 `T*`、`const T*`、`size_t`、`ptrdiff_t`。换句话说，分配器最初要解决的问题（不同的指针类型），和后来人们想用它解决的问题（带状态的内存池），在 C++98 里都被允许实现不支持。Halpern 在 [[N1850]]（§4.1）里把前一条称为 equal-allocator assumption，并指出在这条假定下，带有逐实例状态的分配器实际上不可用。Scott Meyers 在 *Effective STL*（2001）条款 10 中也提醒读者注意分配器的这些约定和限制。

这些限制一直留到 C++11 才处理。C++11 的分配器模型以 [[allocator.traits]] 为中心（[[N2982]]），自定义分配器只需提供很少的成员，其余由 `allocator_traits` 补齐，带状态的分配器也有了明确的传播规则；作用域分配器模型来自 [[N2554]]。此后 `std::allocator` 本身逐步瘦身：C++17 通过 [[P0174R2]] 弃用了 `address`、`max_size`、`construct`、`destroy`、`rebind` 以及 `pointer`、`reference` 等冗余成员，理由是它们与 `allocator_traits` 的功能重复，而当初为扩展预留的 `reference` 类型实际并没有用处；C++20 通过 [[P0619R4]] 把它们移除。今天 [[default.allocator]] 的类定义里，除了构造、析构和赋值，只剩下 `allocate`、`allocate_at_least`（[[P0401R6]]）和 `deallocate`。

对照一下，1995 年报告里的需求表有十几项，今天一个能用于标准容器的分配器只需要这么多：

```cpp run title="minimal-allocator.cpp" ok
#include <cstddef>
#include <new>
#include <vector>

template<class T>
struct Mallocator {
    using value_type = T;
    Mallocator() = default;
    template<class U> constexpr Mallocator(const Mallocator<U>&) noexcept {}
    T* allocate(std::size_t n) {
        return static_cast<T*>(::operator new(n * sizeof(T)));
    }
    void deallocate(T* p, std::size_t) noexcept { ::operator delete(p); }
};
template<class T, class U>
bool operator==(const Mallocator<T>&, const Mallocator<U>&) { return true; }

int main() {
    std::vector<int, Mallocator<int>> v{1, 2, 3};   // 其余成员由 allocator_traits 补齐
    v.push_back(4);
    return v.size() == 4 ? 0 : 1;
}
```

C++17 另外引入了 `std::pmr::polymorphic_allocator`（来自 Library Fundamentals TS，经 [[P0220R1]] 并入），用运行期多态的内存资源解决分配器类型进入容器类型的问题。分配器的完整演变另见 [[allocator.requirements.general]] 与 [[mem.poly.allocator.class]]。

## 八、iostream、char_traits 与 locale

### 以字符类型为参数

标准化开始时，国际化就是库工作组的任务之一。Nathan Myers 在前面提到的 traits 文章开头说，这项任务的含义是逐渐清楚的，其中一点是：凡是处理字符的库设施，都必须以字符类型为模板参数。把已有的 iostream 和 string 改写成模板，比预想的难。

他的文章用 `streambuf` 说明了难在哪里。传统的 `streambuf` 和 C 的 stdio 一样，用一个与所有字符值都不同的 `EOF` 表示文件结束，所以读字符的函数返回 `int`。模板化之后，除了字符类型，还需要一个能容纳 EOF 的整数类型，以及 EOF 的值本身；如果都做成模板参数，用户每次都要写一长串与他无关的参数。traits 的做法是另外定义一个以字符类型为参数的模板，集中存放 `int_type`、`eof()` 这类信息，再让 `basic_streambuf<charT>` 通过它取得这些信息。标准里的 `char_traits`（[[char.traits]]）就是这样来的：`basic_string`、`basic_istream`、`basic_ostream` 都多了一个 `traits` 参数，默认为 `char_traits<charT>`，而 `string`、`istream`、`ostream` 成了 `char` 特化的类型别名。

这个设计的一个副作用是，字符的比较规则可以通过 traits 替换。下面是一个常见的例子，比较时忽略大小写：

```cpp run title="ci-string.cpp" ok
#include <cassert>
#include <cctype>
#include <cstddef>
#include <string>

struct ci_traits : std::char_traits<char> {
    static bool eq(char a, char b) {
        return std::tolower((unsigned char)a) == std::tolower((unsigned char)b);
    }
    static bool lt(char a, char b) {
        return std::tolower((unsigned char)a) < std::tolower((unsigned char)b);
    }
    static int compare(const char* p, const char* q, std::size_t n) {
        for (; n; --n, ++p, ++q) {
            if (lt(*p, *q)) return -1;
            if (lt(*q, *p)) return 1;
        }
        return 0;
    }
};
using ci_string = std::basic_string<char, ci_traits>;

int main() {
    ci_string a = "STL", b = "stl";
    assert(a == b);          // 比较规则来自 traits，而不是 basic_string 本身
}
```

### locale

标准 iostream 还隐含地依赖 locale（[[localization]]）：数值的格式化和解析通过 `num_put`、`num_get` 等 facet 完成，字符分类和转换通过 `ctype`、`codecvt` 完成。HOPL III（§6.1）说，locale 是为了支持英语以外的语言（尤其是日语）而加入的。

Stroustrup 对 iostream 和 locale 的总体评价并不高。他在 HOPL III（§4.2）里说，标准库中 STL 之外的组件大多各自独立开发，没有统一的设计理念，例如 `bitset` 做范围检查而 `string` 不做；string、complex 和 iostream 的设计受制于兼容性考虑；iostream 和 locale 则受到了第二系统效应（second-system effect）的影响，设计者想同时满足各种需求、约束和既有实践。他认为 complex 是个例外，基本上就是他最初的设计加上模板化。

1996 年前后，一些日本厂商提出了 Embedded C++（EC++），作为便于实现的近似子集。它去掉了模板、异常、多重继承、命名空间等特性，在库方面去掉了 STL 和 locale，并提供另一套 iostream。HOPL III（§6.1）说，EC++ 相对完整 C++ 最常被引用的开销就来自 iostream，主要原因正是 C++98 的 iostream 支持 locale 而旧版本不支持。Stroustrup 认为这些开销在不使用 locale 的环境里可以被优化掉。

iostream 的格式化接口在之后二十年里没有大的变化。直到 C++20 加入 `std::format`（[[P0645R10]]），C++23 加入 `std::print`（[[P2093R14]]），标准库才有了另一套类型安全且可扩展的格式化输出。参见 [[format]] 与 [[input.output]]。

## 九、std::string：委员会设计的字符串

### 多种风格并存

`basic_string` 是 STL 进入草案之前就已经存在的提案，STL 被接纳之后又补上了迭代器接口和容器式的成员。HOPL III（§4.2）评价说，string 同时呈现了好几种风格。从接口上也能看出这一点：它既有以下标和长度为参数的成员函数，也有以迭代器为参数的成员函数，还有一批接受 C 风格字符串的重载。Herb Sutter 在 GotW #84（*Monoliths "Unstrung"*）里数过，连构造函数在内 `basic_string` 有 103 个成员函数，他认为其中只有 32 个真正需要是成员，其余 71 个都可以写成非成员非友元函数。

### 写时复制与引用失效

C++98 的措辞允许 `basic_string` 采用引用计数的写时复制（copy-on-write，COW）实现：复制字符串时只增加引用计数，等到可能修改时再真正复制。为此，C++98 的 [lib.basic.string] 列出的引用失效条件里有一条很特殊：在构造或某些操作之后，第一次调用非 const 的 `operator[]`、`at`、`begin`、`rbegin`、`end`、`rend` 也可能使已有的引用、指针和迭代器失效。原因是 COW 实现必须在交出一个可写引用之前先取消共享。当时的标准还附有一个注和例子，专门说明引用计数实现的行为。

1999 年前后，多线程程序越来越普遍，COW 的代价开始受到关注。Sutter 在 *C/C++ Users Journal* 1999 年 6 月号发表了 *Optimizations That Aren't (In a Multithreaded World)*，并在 GotW #45 中给出测量：线程安全的 COW 必须对引用计数做原子操作或加锁，结论是一旦需要线程安全，COW 会让所有用户付出明显的性能代价，包括只运行单线程代码的用户。Meyers 在 *Effective STL* 条款 15 中也专门讨论了不同 string 实现之间的差异。

C++11 引入了内存模型和线程，库要规定哪些操作可以并发调用。Alisdair Meredith、Hans Boehm、Lawrence Crowl、Peter Dimov 的 [[N2534]] 及其修订版 [[N2668]]（2008 年 6 月，Daniel Krügler 加入署名）指出了旧规则的问题。论文举的例子是：对于提供容器线程安全的 `vector`，可以直接并行地给每个元素赋值；而对于 `basic_string`，必须先在并行循环之前调用一次 `v[0]`，否则第一次非 const 访问可能使其他线程拿到的引用失效。连 `s[0] + s[1]` 这样的表达式，如果一次通过 const 访问、一次通过非 const 访问，第二次 `operator[]` 也可能使第一次得到的引用失效。

论文的提案是让所有迭代器和元素访问操作都可以安全地并发执行，并直接说明这一改动实际上不允许 COW 实现，对已经采用 COW 的实现还意味着 ABI 改变。它附了一张各厂商实现的调查表：在 '98 和 '03 两栏里，GNU libstdc++ 等多家实现都是 COW，而在 '0x 一栏里大多已不是。具体的措辞修改是：删去关于构造之后第一次调用非 const `operator[]` 等函数的那条失效条件，删去关于引用计数实现的注和例子，并把 `data()`、`c_str()` 从失效条件中去掉。

今天的 [[string.require]] ¶4 就是这次修改的结果。Annex C 的 [[diff.cpp03.strings]] 把它记为 C++03 与 C++11 之间的一项不兼容：`basic_string` 的要求不再允许引用计数实现，理由是引用计数实现的失效行为与其他实现有细微差别。下面的代码在 C++11 之后是确定可行的：

```cpp run title="string-invalidation.cpp" ok
#include <cassert>
#include <string>

int main() {
    std::string s = "abc";
    const char* p = s.c_str();
    char& c = s[0];          // C++11 起：非 const operator[] 不再使引用失效
    c = 'x';
    assert(p[0] == 'x');     // p 仍然有效，指向同一块缓冲区
}
```

在 C++03 的规则下，`char& c = s[0];` 这一行调用的非 const `operator[]` 是构造之后的第一次此类调用，标准允许它使 `p` 失效。

实现跟进花了几年。GCC 的 libstdc++ 由于 ABI 稳定性的要求，到 2015 年的 GCC 5 才默认启用新的 `std::string` 实现，用短字符串优化（small string optimization）取代写时复制的引用计数；旧 ABI 仍可通过宏 `_GLIBCXX_USE_CXX11_ABI=0` 选用（GCC 5 发布说明）。同一次 ABI 变更还让 `std::list::size()` 变成了常数时间，这对应 [[diff.cpp03.containers]] 中的另一项要求。

另一个相关的修订是 [[LWG530]]：C++03 并没有要求 string 的字符连续存储，C++11 才把这一点写进标准。

## 十、`vector<bool>`

### 不是容器的容器

C++98 为 `vector<bool>` 规定了一个特化，以位为单位存储元素，并额外提供 `flip()`（今天在 [[vector.bool.pspc]]）。因为不能返回一个位的引用，它的 `reference` 是一个代理类，而容器要求规定 `reference` 必须是 `T&`。1998 年，法国国家成员体 AFNOR 提交了 [[LWG96]]，标题就是 *Vector&lt;bool&gt; is not a container*，指出它的引用和指针类型并不是真正的引用和指针，并且这个特化强制选择了空间优化而不是速度优化。

问题在泛型代码里表现得最明显。下面的函数对除 `bool` 以外的所有 `T` 都成立：

```cpp title="vector-bool-ref.cpp" error
#include <vector>

template<class T>
void first_ref(std::vector<T>& v) {
    T& r = v.front();        // 对除 bool 以外的所有 T 都成立
    (void)r;
}

int main() {
    std::vector<int> vi{1};
    std::vector<bool> vb{true};
    first_ref(vi);           // OK
    first_ref(vb);           // error: 非 const 左值引用 bool& 不能绑定到代理对象
}
```

反过来，用 `auto` 接住 `vb[0]` 时得到的不是 `bool` 的拷贝，而是一个仍然指向容器的代理：

```cpp run title="vector-bool-proxy.cpp" ok
#include <cassert>
#include <type_traits>
#include <vector>

int main() {
    std::vector<bool> vb{true, false};
    auto x = vb[0];          // x 不是 bool，而是 vector<bool>::reference 代理
    static_assert(!std::is_same_v<decltype(x), bool>);
    vb[0] = false;
    assert(x == false);      // 通过代理看到了修改：x 并不是一份拷贝
}
```

### 十年的讨论

Sutter 在 1999 年连续写了两篇论文。第一篇总结了三个问题：`vector<bool>` 不是容器，它的迭代器也不是随机访问迭代器；它把一种可能并不合适的优化强加给所有用户；可是修正前两个问题又可能破坏依赖其空间特性或 `flip()` 接口的代码。第二篇在 1999 年 Kona 会议上提出，但没有进入会后邮寄，2005 年原样以 [[N1847]] 重新发布。它补充了一个更基本的问题：C++98 只给出了 `vector<bool>` 的声明，没有规定任何一个成员函数的语义，因此任何使用都谈不上有明确规定的行为。Sutter 的建议是要么补全规范，要么干脆移除。他在 GotW #50 里也写道，`vector<bool>` 不满足标准自己的容器要求，而 `bitset` 本来就是为这类用途设计的。Meyers 在 *Effective STL* 条款 18 中的建议是避免使用 `vector<bool>`。

[[LWG96]] 的讨论记录展示了委员会的分歧。1999 年 Kona 会议讨论 Sutter 的论文时，对先弃用、再替换这一方案的试探性表决是 1 票赞成、11 票可以接受、2 票坚决反对，之后又有几位委员表示坚决反对。2005 年的 Lillehammer 会议上，记录写的是大体同意弃用 `vector<bool>`，并以另一个名字（例如 `bit_vector`）提供同样的功能，但这个方向始终没有形成可以投票的方案。2006 年到 2007 年间陆续出现了几份提案：[[N2050]] 提议增加动态大小的 bitset，Beman Dawes 的 [[N2160]] 讨论如何修正这个 issue，Alisdair Meredith 先后写了弃用 `vector<bool>` 的规范 [[N2204]] 和补全其规范的 [[N2353]]。

最终，LWG 在 2009 年 Santa Cruz 会议上以 NAD（Not A Defect）关闭了 [[LWG96]]。记录中的理由是：委员会希望支持代理迭代器，但那是另外的工作；能想到的接近的修改都会破坏现有代码；移除它不可行。动态 bitset 的需求被拆分为 [[LWG1184]]。

### 问题在名字

Howard Hinnant 在 2012 年的文章 *On vector&lt;bool&gt;* 中给出了另一个角度。他把问题拆成两个：位数组是不是一种好的数据结构？它应不应该叫 `vector<bool>`？他对前者的回答是肯定的，位数组在正确实现时往往既省空间又更快，而且标准库可以为位迭代器专门优化 `find` 这类算法，一次检查一整个字的位；对后者的回答是否定的，因为它的行为并不完全等同于一个 `bool` 数组，就不应假装是。按他的看法，错误在于命名，而不在于数据结构本身。

今天的 [[vector.bool]] 仍然是 C++98 的那个特化，只是规范已经补全，C++23 还为它的 `reference` 增加了 `formatter` 特化（[[vector.bool.fmt]]，来自 [[P2286R8]]）。

## 十一、auto_ptr 的反复

### 三个版本

`auto_ptr` 是 C++98 里唯一的智能指针。HOPL III（§6.2）提到，引用计数的智能指针（`shared_ptr` 的前身 `counted_ptr`）因为对性能和可能被滥用的担心，没能进入 C++98；`auto_ptr` 则以转移所有权的语义进入了标准。它在标准化过程中改过三次。Scott Meyers 为他的书维护过一份 *auto_ptr Update* 勘误页，整理了这几个版本：

| 版本 | 时间 | 语义 |
|---|---|---|
| CD-1 | 1996 年 3 月以前 | 复制时把源对象的指针置空，有 `reset` |
| CD-2 | 1996 年 3 月至 1997 年 11 月 | 复制时不改变源对象的指针，而是用一个 owner 标志转移所有权；复制操作的参数是 const 引用；去掉了 `reset` |
| FDIS | 1997 年 11 月之后 | 恢复 CD-1 的语义，增加辅助类 `auto_ptr_ref` |

第三个版本来自 Bill Gibbons 和 Greg Colvin 的论文 *Fixing auto_ptr*（J16/97-0090R1，1997 年 11 月 14 日）。论文开头说，CD-2 的 `auto_ptr` 既不受欢迎也危险：复制操作接受 const 引用，很容易通过一个 const 引用意外地破坏 `auto_ptr`；复制之后留下的非拥有指针又容易造成悬垂引用。CD-1 的复制操作本来接受非 const 引用，改成 const 是为了能按值传入和返回 `auto_ptr`，因为临时对象不能绑定到非 const 引用。

Colvin 和 Gibbons 的解决办法后来被称为 Colvin-Gibbons trick：复制构造函数和赋值运算符改回接受非 const 引用，同时增加一个私有的辅助类 `auto_ptr_ref` 和一组转换函数。函数返回的 `auto_ptr` 右值先通过转换函数变成 `auto_ptr_ref`，再通过接受 `auto_ptr_ref` 的构造函数变回 `auto_ptr`，从而绕开临时对象不能绑定到非 const 引用的限制。这在 C++ 有右值引用之前模拟出了移动语义。

```cpp title="历史代码：C++98 的 auto_ptr（C++11 弃用，C++17 移除）"
#include <memory>

std::auto_ptr<int> source() { return std::auto_ptr<int>(new int(42)); }
void sink(std::auto_ptr<int> p) { }        // 按值接收，取得所有权

int main()
{
    std::auto_ptr<int> a(new int(1));
    std::auto_ptr<int> b = a;    // 看起来是复制，实际上转移了所有权：a 变为空
    sink(source());              // 右值经由 auto_ptr_ref 传入
}
```

### 语言层面的漏洞

这个技巧依赖重载决议和复制初始化规则里一个很微妙的地方。EDG 的 J. Stephen Adamczyk 在 1998 年底提出了核心语言问题 [[CWG84]]，2000 年又写了 [[N1232]]（*The core language auto_ptr problem*）详细分析。他以 Greg Colvin 提供的例子说明，把 `auto_ptr<Derived>` 右值传给 `auto_ptr<Base>` 形参时，按照当时的规则要依次调用两个转换函数、一个复制构造函数和一个构造函数，这违背了隐式转换最多只调用一次用户定义转换的原则。他的建议实际上是什么都不做，让 `auto_ptr` 保持部分不可用的状态。库方面，Colvin 提交的 [[LWG127]] 修正了 `auto_ptr` 与 `auto_ptr_ref` 之间的转换，随 2003 年的技术勘误进入 C++03。

### 弃用与移除

`auto_ptr` 的根本问题在于它用复制的语法做移动。Hinnant 在 2005 年的 [[N1856]] 中提议弃用它，并以新的 `unique_ptr` 取代。他的论证是：早期允许从 const `auto_ptr` 转移所有权的设计可以把 `auto_ptr` 放进容器，而某些 `sort` 实现会把一个元素复制到局部变量作为基准，再假定两者相等，遇到 `auto_ptr` 时这个假定不成立，程序可能出错甚至崩溃。后来禁止从 const 对象复制，只是让标准容器拒绝 `auto_ptr`，用户自己的容器和内建数组仍然可以编译。他的结论是，不应该用复制的语法从左值移动，否则泛型代码会在想复制的时候发起移动。

C++11 弃用了 `auto_ptr`，由基于右值引用的 [[unique.ptr]] 取代。Billy Baker 的 [[N4168]] 和 Stephan T. Lavavej 的 [[N4190]] 提议在 C++17 中移除它，[[diff.cpp14.depr]] 记录了这一变化。今天 `auto_ptr` 和 `auto_ptr_ref` 都列在 [[zombie.names]] 里，作为“为以往标准保留”的名字，用户代码不得使用。

## 十二、valarray

`valarray` 的来历和 STL 几乎同时，但路径完全不同。P. J. Plauger 在 1997 年 8 月 *C/C++ Users Journal* 的专栏中介绍了它的由来：`valarray` 在 1993 年就已提出，早于 STL 进入草案，当时以它是一项重大的库扩充、实际使用经验有限为由被搁置；1994 年 7 月 STL 被投票纳入之后，库小组在同一次会议上投票恢复了 `valarray` 的提案，几乎没有讨论就把它加了进去。Plauger 说，它的设计主要基于 Sandia 国家实验室的经验。

`valarray` 的目标是在向量处理器上获得 Fortran 那样的性能。为此，草案专门放宽了对 `valarray` 元素访问的通常的顺序和别名规则（Plauger 同一专栏），今天的 [[valarray.syn]] 仍然说明，这些数值数组类型被定义为不存在某些形式的别名，从而允许实现做相应的优化。

它在标准化后的评价不高。2000 年 6 月，Nathan Myers 在 libstdc++ 邮件列表上说，库工作组差不多把 `valarray` 看作一次失败的实验，不愿意再给一个他们宁愿弃用的东西增加复杂度。同年法国国家成员体提交了 [[N1246]]（*Fixing valarray for Real-World Use*），[[LWG253]] 则指出 valarray 的辅助函数几乎完全无用。`valarray` 至今仍在标准里（[[numarray]]），C++11 为它加上了 `begin`/`end`，[[P3016R5]] 又修正了一些不一致之处。标准库在数值计算方面的新方向则是 C++23 的 `mdspan`（[[P0009R18]]）和 C++26 基于 BLAS 的线性代数接口（[[P1673R13]]）。

## 十三、异常与标准库

异常和模板几乎同时进入 C++，标准库是第一个大规模同时使用两者的地方。HOPL III（§5.3）回忆说，在为 STL 写规范的过程中，委员会发现自己不知道该如何描述模板与异常之间的相互作用。一些人把问题归咎于模板，另一些人开始认为异常本身有根本缺陷，至少在没有垃圾回收时如此。Nathan Myers、Greg Colvin、Dave Abrahams 等人研究后认为，问题在于资源（更一般地说，不变量）与异常之间的关系，需要一个系统的思考框架。

这个框架的核心是 Abrahams 在 1997 年初提出的三个保证：基本保证（不变量得以保持、没有资源泄漏）、强保证（操作要么成功完成，要么抛出异常并使程序状态保持操作前的样子）、不抛出保证。库工作组用这三个概念描述了整个标准库：所有操作都提供基本保证（前提是析构函数不通过抛出异常退出），关键操作提供强保证或不抛出保证。第一批按这些概念实现异常安全的 STL 是 Matt Austern 的 SGI STL，以及 Boris Fomitchev 的 STLport 加上 Abrahams 的异常安全容器和算法，都出现在 1997 年春（HOPL III §5.3）。

今天这些保证分散在各处条文里：[[res.on.exception.handling]] 规定库函数在什么情况下可以抛出异常，[[string.require]] ¶2 规定 `basic_string` 的成员抛出异常时没有其他效果，`vector::push_back` 等操作单独规定了强保证。C++98 的库用空的动态异常规范 `throw()` 标注不抛出的函数，C++11 把它们改为 `noexcept`（[[N3148]]），并按照 [[N3279]] 的保守原则，只给宽契约（没有前置条件）的函数加上 `noexcept`。动态异常规范本身在 C++17 中被移除（[[P0003R5]]）。

## 十四、C++03：一次修订

ISO/IEC 14882:1998 发布之后，委员会进入维护模式，主要处理缺陷报告。HOPL III（§6）说，这一阶段的修改大多是澄清文字或消除矛盾，极少引入新规则，刻意避免创新，目标是稳定。2003 年，这些修正以技术勘误（Technical Corrigendum 1）的形式发布，修订后的标准即 ISO/IEC 14882:2003，通称 C++03。它的草案由当时的项目编辑 Koenig 准备（[[N1316]]、[[N1334]]）。英国国家成员体的 Francis Glassborow 和 Lois Goldthwaite 还推动 Wiley 出版了这份标准的印刷版，在此之前公众只能从 ISO 或 INCITS 购买（HOPL III §6）。

库方面，C++03 里最常被提到的修正有两项。一是 [[LWG69]]：Koenig 在 1998 年提出 `vector` 的元素是否必须连续存储，C++03 明确规定必须连续，从此 `&v[0]` 可以当作 C 数组传给 C 接口。二是前面提到的 [[LWG127]]，修正了 `auto_ptr` 的转换。

C++98 没能容纳的库，则交给了技术报告。HOPL III（§6.2）说，委员会在完成标准时就清楚，已经纳入的只是当时最急需、也已经准备好的那部分，哈希表、正则表达式、目录操作、线程等都还缺着。Beman Dawes 在 1998 年发起了 Boost，为未来的标准化积累实践经验（HOPL III §4.2）；库技术报告从 2001 年开始起草，HOPL III 记载它在 2004 年获得一致通过，其中的哈希表、智能指针、正则表达式等后来大多进入了 C++11。

## 时间线

| 时间 | 事件 | 出处 |
|---|---|---|
| 1980 | C with Classes 的 task 库 | HOPL II §5.3 |
| 1983 | Shopiro 的 list 与 string 类，后来成为 USL Standard Components 的基础 | HOPL II §5.3 |
| 1984 | Stroustrup 实现 stream I/O 库；与 Leonie Rose 实现 complex 库 | HOPL II §3、§5.3.1 |
| 1989 年 6 月 | Cfront 2.0，Jerry Schwarz 重写的 iostream，加入 Koenig 的操纵符 | HOPL II §4、§5.3.1 |
| 1989 | Stepanov 与 Musser 出版 *The Ada Generic Library* | HOPL III 参考文献 [101] |
| 1993 年 11 月 | Stepanov 在 San Jose 会议上演讲 *The Science of C++ Programming* | Dr. Dobb's 访谈；演讲幻灯片（11 月 11 日）；HOPL III 记为 10 月 |
| 1994 年 1 月 | Koenig 邀请 Stepanov 在 1 月 25 日前提交 STL 提案 | Dr. Dobb's 访谈 |
| 1994 年 3 月 | San Diego 会议：STL 完整介绍，表决同意下次会议审议；以字符类型为参数的 string 获得通过 | Dr. Dobb's 访谈；HOPL III §3.2 |
| 1994 | HP 的实现者会议，STL 删去约三分之二 | HOPL III §4.1.2 |
| 1994 年 7 月 | Waterloo 会议：STL 纳入工作草案；同一会议恢复 valarray 提案 | Plauger（CUJ 1997）；HOPL III 记为 10 月 |
| 1994 年 8 月 | Stepanov 与 Lee 的技术报告 HPL-94-34 | HOPL III 参考文献 [103] |
| 1995 | Myers 发表 traits 技术；偏特化加入 C++ | *C++ Report* 1995 年 6 月；HOPL III §4.1.5 |
| 1995 | Barreiro、Fraley、Musser 的哈希表提案未能赶上 C++98 | HOPL III §6.2 |
| 1997 年初 | Abrahams 提出异常安全的三个保证 | HOPL III §5.3 |
| 1997 年 11 月 | Colvin 与 Gibbons 的 *Fixing auto_ptr*，auto_ptr_ref 进入 FDIS | J16/97-0090R1；Meyers *auto_ptr Update* |
| 1997 | 最终的委员会投票（Morristown） | HOPL III §3.2 |
| 1998 | ISO/IEC 14882:1998 发布；[[LWG96]] 指出 vector&lt;bool&gt; 不是容器 | HOPL III §3.2；LWG96 |
| 1999 | Sutter 关于 vector&lt;bool&gt; 的论文（后以 N1847 重发）；Sutter 在 CUJ 上分析 COW 字符串的多线程代价 | [[N1847]]；CUJ 1999 年 6 月 |
| 2000 | Adamczyk 的 [[N1232]] 分析 auto_ptr 的核心语言问题 | N1232 |
| 2003 | 技术勘误 TC1，即 C++03；含 LWG69（vector 连续存储）与 LWG127 | HOPL III §6 |
| 2003–2005 | Austern 的 unordered 容器提案 [[N1456]] 进入库技术报告草案 [[N1836]] | N1456、N1836 |
| 2005 | Hinnant 的 [[N1856]] 提议弃用 auto_ptr；Halpern 的 [[N1850]] 分析 C++98 分配器模型的缺陷 | N1856、N1850 |
| 2008 | [[N2668]] 修改 basic_string 的失效规则，实际上排除了 COW 实现 | N2668 |
| 2009 | LWG96 以 NAD 关闭；[[N2982]] 确立 allocator_traits 模型 | LWG96；N2982 |
| 2011 | C++11：unordered 容器、unique_ptr、allocator_traits；auto_ptr 弃用；string 不再允许引用计数 | [[diff.cpp03.strings]] |
| 2015 | GCC 5 默认启用不使用 COW 的 std::string | GCC 5 发布说明 |
| 2017 | C++17：移除 auto_ptr（[[N4190]]）；弃用 std::allocator 的冗余成员（[[P0174R2]]）；引入 pmr | [[diff.cpp14.depr]] |
| 2020 | C++20：移除 std::allocator 的冗余成员（[[P0619R4]]）；迭代器概念与 ranges（[[P0896R4]]）；std::format | P0619R4、P0896R4、P0645R10 |

## 现状与未来

1990 年代的这些决定在今天的条文里留下了清晰的痕迹，读标准时值得留意几处：

- 需求表与概念并存。Stroustrup 在 Stepanov 黑板上画出的需求表，今天以 *Cpp17* 前缀的具名要求保留在 [[utility.requirements]]、[[iterator.cpp17]]、[[allocator.requirements.general]] 中；C++20 又用概念重写了迭代器和算法的约束（[[iterator.concepts]]、[[alg.req]]）。同一个迭代器类型可能满足其中一套而不满足另一套，例如 C++20 的某些视图迭代器建模 `forward_iterator` 却不满足 *Cpp17ForwardIterator*，原因是后者要求 `reference` 是真正的引用，而这个要求正是 `vector<bool>` 当年违反的那一条。
- 分配器只剩下骨架。[[default.allocator]] 和 [[allocator.traits]] 的现状是一个三十年的收缩过程：为分段内存设计的 `pointer`、`reference`、`address` 等成员先被允许忽略，再被弃用，最后被移除。`allocator_traits` 仍然提供 `pointer`、`size_type`、`difference_type` 等成员类型（`pointer` 默认为 `value_type*`），这些名字本身就是 1994 年那张需求表里的条目。
- traits 参数仍在每一个字符串和流的类型里。`basic_string<charT, traits, Allocator>` 和 `basic_ostream<charT, traits>` 的形参列表来自 1994–1995 年的模板化工作。C++17 的 `basic_string_view` 沿用了同样的设计（[[string.view]]）。
- C++11 对 string 的修改记录在 Annex C。[[diff.cpp03.strings]] 记录了不再允许引用计数实现，以及为短字符串优化放宽失效规则这两项变化；[[string.require]] ¶4 的失效列表里那个脚注提到的 `swap`、`operator>>`、`getline`，正是 [[N2668]] 改写的内容。
- vector&lt;bool&gt; 与 valarray 仍在原处。二者都被广泛批评，也都因为兼容性而保留。代理引用的问题后来在 ranges 的设计中被正面处理：C++20 的迭代器概念通过 `iter_reference_t` 与 `common_reference` 允许代理引用，`views::zip` 的设计（[[P2321R2]]）也围绕代理元组展开。
- 被移除的名字并没有消失。[[zombie.names]] 保留了 `auto_ptr`、`auto_ptr_ref`、`binary_function` 等名字，以便实现可以继续为旧代码提供它们，而不与用户代码冲突。

STL 把算法与数据结构分离、以迭代器为接口、为每个操作规定复杂度的做法，在 C++20 的 ranges 和 C++26 的线性代数库里依然是基本的设计方法。

## 参考资料

### Stroustrup

- Bjarne Stroustrup, *A History of C++: 1979–1991*, ACM HOPL-II, 1993（文中记为 HOPL II）。§3、§5.3 讲早期的 task、complex、stream 库；§7.3 讲没有在 1.0 版提供更大的库这一“最大的错误”。
- Bjarne Stroustrup, *Evolving a language in and for the real world: C++ 1991–2006*, ACM HOPL-III, 2007（文中记为 HOPL III）。§3.2 年表；§4.1 STL（§4.1.2 STL 的出现与接纳，§4.1.5 traits，§4.1.6 迭代器分类，§4.1.8 Stepanov 的自述）；§4.2 其他库组件与标准库的范围；§5.3 异常安全；§6 C++03、EC++ 与库技术报告。
- Bjarne Stroustrup, *The Design and Evolution of C++*, Addison-Wesley, 1994。§9.2.3 讨论未提供标准库的问题，§15.6.3.1 的例子来自 STL。

### Stepanov 与 STL 的原始资料

- Al Stevens, *Al Stevens Interviews Alex Stepanov*, *Dr. Dobb's Journal*, 1995 年 3 月（stepanovpapers.com 有转载）。文中记为 Dr. Dobb's 访谈。
- Graziano Lo Russo, *An Interview with A. Stepanov*, Edizioni Infomedia（stepanovpapers.com 有转载；Halpern 在 N1850 中标注为 2001 年）。文中记为 Lo Russo 访谈。
- Alexander Stepanov, *Short History of STL*（为 HOPL III 撰写，stepanovpapers.com）。
- Alexander Stepanov, Meng Lee, *The Standard Template Library*, HP Labs 技术报告 HPL-94-34（1994 年 8 月），修订版 95-11(R.1)（1995 年 10 月 31 日）。
- Alexander Stepanov, *Science of C++ Programming*（1993 年 11 月 11 日 San Jose 会议邀请报告的幻灯片，stepanovpapers.com）。
- Alexander Stepanov, Meng Lee, *The Standard Template Library*（1994 年 3 月 7 日 San Diego 会议演讲幻灯片，stepanovpapers.com）。
- A. A. Stepanov, D. R. Musser, *The Ada Generic Library: Linear List Processing Packages*, Springer-Verlag, 1989。

### iostream、traits 与 valarray

- Nathan C. Myers, *Traits: a new and useful template technique*, *C++ Report*, 1995 年 6 月。
- P. J. Plauger, *Standard C/C++: The Header &lt;valarray&gt;*, *C/C++ Users Journal*, 1997 年 8 月。
- Nathan Myers, libstdc++ 邮件列表，2000 年 6 月 19 日（关于 valarray）。
- AFNOR, [[N1246]] *Fixing valarray for Real-World Use*, 2000；[[LWG253]]。

### string

- Herb Sutter, *Optimizations That Aren't (In a Multithreaded World)*, *C/C++ Users Journal* 17(6), 1999 年 6 月。
- Herb Sutter, GotW #43–#45 *Reference Counting*（Part I–III）；GotW #84 *Monoliths "Unstrung"*。
- A. Meredith, H. Boehm, L. Crowl, P. Dimov, [[N2534]]（2008 年 3 月）与 [[N2668]]（2008 年 6 月，D. Krügler 加入署名）*Concurrency Modifications to Basic String*。
- GCC 5 Release Series: Changes, New Features, and Fixes（libstdc++ 部分，2015）。
- [[LWG530]] *Must elements of a string be contiguous?*

### vector&lt;bool&gt;

- [[LWG96]] *Vector&lt;bool&gt; is not a container*（AFNOR，1998；2009 年以 NAD 关闭）。
- Herb Sutter, [[N1847]] *vector&lt;bool&gt;: More Problems, Better Solutions*（1999 年 Kona 会议论文，2005 年重发）；GotW #50 *Using Standard Containers*。
- [[N2050]]、[[N2160]]、[[N2204]]、[[N2353]]；[[LWG1184]]。
- Howard E. Hinnant, *On vector&lt;bool&gt;*, 2012 年 8 月。
- Scott Meyers, *Effective STL*, Addison-Wesley, 2001，条款 10、15、18。

### auto_ptr

- Bill Gibbons, Greg Colvin, *Fixing auto_ptr*, J16/97-0090R1, 1997 年 11 月 14 日。
- Scott Meyers, *auto_ptr Update*（aristeia.com 勘误页）。
- [[CWG84]]；J. Stephen Adamczyk, [[N1232]] *The core language auto_ptr problem*, 2000；[[LWG127]]。
- Howard E. Hinnant, [[N1856]] *Rvalue Reference Recommendations for Chapter 20*, 2005。
- Billy Baker, [[N4168]] *Removing auto_ptr*；Stephan T. Lavavej, [[N4190]] *Removing auto_ptr, random_shuffle(), And Old &lt;functional&gt; Stuff*, 2014。

### 分配器

- Pablo Halpern, [[N1850]] *Towards a Better Allocator Model*, 2005；[[N2554]] *The Scoped Allocator Model (Rev 2)*, 2008；[[N2982]] *Allocators post Removal of C++ Concepts (Rev 1)*, 2009。
- Alisdair Meredith, [[P0174R2]] *Deprecating Vestigial Library Parts in C++17*, 2016；A. Meredith, S. T. Lavavej, T. Kamiński, [[P0619R4]] *Reviewing Deprecated Facilities of C++17 for C++20*, 2018。
- [[P0220R1]]；[[P0401R6]]。

### 其他

- Matthew Austern, [[N1456]] *A Proposal to Add Hash Tables to the Standard Library (revision 4)*, 2003；[[N1836]] *Draft Technical Report on C++ Library Extensions*, 2005。
- [[LWG69]] *Must elements of a vector be contiguous?*；[[N1316]]、[[N1334]]（技术勘误草案）。
- [[N3148]]、[[N3279]]、[[P0003R5]]（异常规范与 `noexcept`）。
- [[P0645R10]]、[[P2093R14]]（`std::format` 与 `std::print`）；[[P0896R4]]（ranges）。
