---
title: 如何读一篇提案
summary: WG21 提案的编号和修订版本怎么读、到哪里找，一篇提案由哪几部分组成，怎样把它的措辞改动对到当前草案上，以及怎样判断它最后是以新特性还是缺陷修正的身份进入标准。
status: draft
order: 1
group: 入门
since: c++98
papers: P2647R1, P2513R4, P2242R3, P2644R1, P2718R0, N4950, N5054
related: topics/how-to-read-the-standard, history/standards-timeline, expr.const.core, dcl.init.string, diff.cpp20, cpp.predefined, intro.compliance
tags: 提案, WG21, 方法, 导读, DR
updated: 2026-10-19
---

!!! tldr
    - P2647R1 这样的编号里，P2647 是提案号，R1 是第几次修订；一篇提案从 R0 开始改到通过为止，编号不变。`wg21.link/P2647` 总是指向最新修订。
    - 一篇提案通常先讲问题和动机，再比较几种设计，最后给出措辞（wording）：一份针对当时工作草案的修改清单，插入的文字和删除的文字分别标出。
    - 措辞里的章节号、段落号是写作时那一版草案的。对照今天的标准时，按稳定名去找，再用当前草案的文字核对，草案文字才是最终结论。
    - 以缺陷报告（DR）身份通过的提案被视为对旧标准的修正，编译器通常在旧的 `-std=` 模式下也照新规则处理；普通的新特性只在新模式下生效。
    - 判断一篇提案最后通过了什么，看提案状态页的标签、当前草案、附录 C 的兼容性条目和特性测试宏，而不是只看提案本身。

## 编号：N、P、R 和 issue

WG21（C++ 标准委员会）的每份文件都有编号。读提案时会遇到这几类：

| 编号 | 是什么 | 例子 |
|---|---|---|
| N + 四位数字 | 早期的提案，以及工作草案、会议纪要等正式文件 | [[N4950]] 是最接近 C++23 的公开草案，[[N5054]] 是 2026 年的一份工作草案 |
| P + 四位数字 + R + 修订号 | 2015 年前后起的提案 | [[P2647R1]]：P2647 的第 2 版（R0 是第 1 版） |
| CWG + 数字 | 核心语言 issue：条文中的错误、含糊或遗漏 | [[CWG2652]] |
| LWG + 数字 | 标准库 issue | [[LWG3000]] |

提案号在整个生命周期中不变。作者每次根据审议意见修改，就发一个新的修订版，R0、R1、R2……依次递增。所以讨论一篇提案时要写明修订号：R0 里的设计可能在 R3 里已被推翻。

一篇提案大致按这条路走：可选的研究组（SG，按主题划分，如 SG16 负责文本和 Unicode）先讨论，然后设计组审查设计（语言特性归 EWG，库归 LEWG），再由措辞组审查条文（语言归 CWG，库归 LWG），最后全体表决，编辑把措辞合入工作草案。[[P2513R4]] 就是先经 SG16、再经 EWG、最后由 CWG 审查措辞的。更多背景见 [[history/standards-timeline]]，条文本身怎样阅读见 [[topics/how-to-read-the-standard]]。

## 到哪里找

| 地址 | 用途 |
|---|---|
| `wg21.link/P2647R1` | 指定修订版的全文 |
| `wg21.link/P2647` | 不写修订号时跳到最新修订版 |
| `wg21.link/P2647/github` | 这篇提案在 github.com/cplusplus/papers 上的状态 issue |
| `wg21.link/cwg2652`、`wg21.link/lwg3000` | CWG / LWG issue 的页面 |
| `wg21.link/index.txt`、`wg21.link/index.json` | 全部文件的索引，带标题、作者、日期，可以按关键词搜 |
| `wg21.link/draft` | eel.is 上的当前工作草案（HTML） |
| open-std.org 的 `jtc1/sc22/wg21/docs/papers/<年份>/` | 按年份排列的邮件（mailing）列表，每期一批新文件 |
| cppreference 的 compiler support 页、Clang 的 C++ Status 和 DR Status 页 | 某篇提案在各编译器的哪个版本实现 |

本站的 `[[P2647R1]]`、`[[CWG2652]]` 写法也链接到 wg21.link。

github.com/cplusplus/papers 上每篇提案有一个 issue，它的标签记录了提案走到哪一步。例如 P2647 的 issue 标着 `EWG` 和 `plenary-approved`（全体会议已通过），P2513 的标着 `CWG`、`C++23` 和 `plenary-approved`。

## 一篇提案长什么样

以 [[P2647R1]]（*Permitting static constexpr variables in constexpr functions*）为例。它很短，结构却很完整。

**页眉。** 文档号、日期、目标小组（Audience: EWG）、作者联系方式。Audience 告诉你它在审议流程的哪一步。

**修订历史。** 列出每一版相对上一版改了什么。P2647R1 的修订历史只有一句：相对 R0 更新了措辞，加了一个例子和特性测试宏。修订历史是追踪设计变化最快的入口，读一篇有十几个修订版的提案时尤其如此。

**动机。** 好的提案从一段写不出来或写得很别扭的代码开始。P2647 的出发点是一个把数字转成十六进制字符的函数：

<div class="compare" markdown="1">

```cpp title="C++20：可以" ok
char xdigit(int n) {
  static constexpr char digits[] =
      "0123456789abcdef";
  return digits[n];
}
```

```cpp title="C++20：加上 constexpr 就不行" error std=c++20
constexpr char xdigit(int n) {
  static constexpr char digits[] =
      "0123456789abcdef";
  return digits[n];
}
```

</div>

C++20 不允许 constexpr 函数在执行时经过一个静态变量的声明，即使这个变量本身就是 `constexpr` 的。本机 Clang 23 在 `-std=c++20` 下对右边的代码给出 `definition of a static variable in a constexpr function is a C++23 extension` 警告，加上 `-pedantic-errors` 就成为错误。

**设计讨论和替代方案。** 提案要说明为什么现有的写法不够好。P2647 列了四种绕过办法：直接对字面量取下标、把数组挪到命名空间作用域、去掉 `static`、包进一个 consteval lambda。每种都有代价，比如第二种让本该局部的数据暴露在外面。大提案的这一节会长得多，还会记录被否决的设计和理由，这往往是全文最值得读的部分。

动机里的论断要结合写作时间来读。P2647 说去掉 `static` 的版本在当时的编译器上代码更差；本机 Clang 23 在 `-O2` 下把两种写法都编译成一次查表，生成的代码相同。

**实现经验。** 较大的提案通常会说明是否已在某个编译器或库中实现、用户反馈如何。P2647 这样的小改动没有这一节。

**措辞。** 提案的规范部分：对工作草案的逐处修改。下一节专门讲怎样读它。

设计和措辞有时分成两篇提案。修正范围 `for` 中临时对象生命周期的设计在 [[P2644R1]] 里，CWG 审查通过的条文在单独的 [[P2718R0]] 里，它的标题就是 *Wording for P2644R1 Fix for Range-based for Loop*。这项改动的来龙去脉见 [[papers/range-for-temporaries|范围 for 与临时对象]]。

## 读措辞：P2647R1

### 提案里写了什么

P2647R1 的措辞只改了一处。它写作 Change 7.7 [expr.const]/5.2，插入的文字用绿色底标出（这里用 `+` 表示）：

```diff
 (5.2) a control flow that passes through a declaration of a
       variable with static ([basic.stc.static]) or thread
       ([basic.stc.thread]) storage duration
+      , unless that variable is usable in constant expressions
       ;
```

另外插入了一个例子，并把特性测试宏 `__cpp_constexpr` 的值从 `202207L` 改为 `20XXXXL`。值留空是常见做法，由编辑在合入草案时按通过的年月填写。

不同作者的标记方式不一样：有的用 `<ins>`、`<del>`，有的用绿色和红色底色，有的用下划线和删除线，提案开头一般会说明。读法都一样：带删除标记的文字是旧草案里有、改完后没有的，带插入标记的是新加的，其余是原样保留、只为提供上下文的文字。

### 在当前草案里找到它

提案里的 7.7 和 /5.2 是 2022 年那一版草案的编号。章节号和段落号随后可能变化，所以要按稳定名找，不要按数字找：

```bash
python3 tools/eel.py expr.const.core
```

今天这条规则在 [[expr.const.core#2.2]]。[expr.const] 后来被拆成了几个子条款，核心常量表达式的规则搬进了 [expr.const.core]，所以 /5.2 变成了 /2.2：

!!! std
    a control flow that passes through a declaration of a block variable ([basic.scope.block]) with static ([basic.stc.static]) or thread ([basic.stc.thread]) storage duration, unless that variable is usable in constant expressions;

P2647 插入的从句原样在那里，提案加的例子成了这一条款的 Example 1。但开头的措辞已经和提案不同了：a variable 变成了 a block variable（块作用域变量）。这是之后的修改，不是 P2647 写的。草案在不断被后来的提案、issue 和编辑修改，所以提案里的条文只能告诉你它当时改了什么，现在的规则要以草案为准。

特性测试宏也一样。本机 Clang 23 的 `__cpp_constexpr` 在 `-std=c++23` 下是 `202211L`，也就是 P2647 填入的值；在 `-std=c++2c` 下是 `202406L`，与当前草案 [[cpp.predefined]] 一致，说明后来又有提案改过它。

这条规则在 [[expr.const.core]] 页上有完整解释，包括它前一步的 [[P2242R3]]：那篇提案先允许 constexpr 函数里出现静态变量，只要执行时不经过它们的声明。

## 读措辞：P2513R4，一个 DR

[[P2513R4]]（*char8_t Compatibility and Portability Fix*）的措辞改了三个地方，正好覆盖一篇提案常见的三类修改：正文、附录 C、特性测试宏。它的页眉写着 Target: C++23 (DR C++20)。

**问题。** C++20 把 `u8"…"` 的类型从 `const char[N]` 改成了 `const char8_t[N]`，于是 C++17 里合法的 `const char s[] = u8"abc";` 在 C++20 里不能编译了（[[diff.cpp17]]）。

**正文。** 提案修改 [dcl.init.string] 第 1 段，加入一句：

!!! std
    Additionally, an array of char or unsigned char may be initialized by a UTF-8 string literal, or by such a string literal enclosed in braces.

另外在段末加上必要时做整数转换的说明。提案里这一条款编号是 9.4.3，当前草案中是 9.5.3，稳定名没变。用 `eel.py dcl.init.string` 可以确认插入的句子原样在 [[dcl.init.string#1]] 中。

**附录 C。** 每当一处修改可能让原本合法的代码改变含义或无法编译，就要在 Annex C 加一条兼容性说明。P2513 加的这一条今天在 [[diff.cpp20]] 的 [diff.cpp20.dcl] 下：

```cpp title="annex-c.cpp" error
struct A { char8_t s[10]; };
struct B { char s[10]; };
void f(A);
void f(B);
int main() { f({u8""}); }   // error: 调用有歧义
```

在 C++20 原来的规则下，`u8""` 只能初始化 `char8_t` 数组，`f(A)` 是唯一可行的函数。修正以后两个聚合都能用 `u8""` 初始化，调用变得有歧义。读一篇提案时，附录 C 的条目是最快了解它破坏了什么的地方。

**特性测试宏。** `__cpp_char8_t` 从 `201811L` 改为新值，当前草案中是 `202207L`。

## DR 和新特性

P2513 和 P2647 都在 C++23 周期中通过，但身份不同：前者是对 C++20 的缺陷报告（defect report，DR），后者是 C++23 的新特性。

**缺陷报告**的意思是：委员会认定旧标准的规则本身就是错的，修正应当被视为旧标准的一部分。标准文本只有一份最新的，DR 的修正写进当前草案，旧标准的文本不会重新发布；DR 的效力体现在实现上。Clang 的状态页说明，它通常在所有修正有意义的旧语言模式下追溯实现 DR；其他编译器的做法以各自的文档为准。

在本机 Clang 23 上，区别很直接：

<div class="compare" markdown="1">

```cpp title="P2513（DR）" ok std=c++20
// clang++ -std=c++20：无诊断
const char a[] = u8"abc";
const unsigned char b[] = u8"abc";
// __cpp_char8_t == 202207L
```

```cpp title="P2647（新特性）" std=c++20
// clang++ -std=c++20：警告
// "... is a C++23 extension"
constexpr char xdigit(int n) {
  static constexpr char d[] = "0";
  return d[n];
}
// __cpp_constexpr == 202002L
```

</div>

左边的代码在 `-std=c++20` 下直接通过，`__cpp_char8_t` 也报告修正后的值 `202207L`，就像 C++20 一开始就是这样规定的。同一模式下，附录 C 那个歧义的例子也会报错。右边的代码在 `-std=c++20` 下只作为扩展接受，`__cpp_constexpr` 仍是 C++20 的 `202002L`。

这对写代码有两个影响。第一，DR 会改变旧模式下的行为，升级编译器而不改 `-std=` 也可能让代码的含义变化。第二，查一个特性能不能在 C++17 或 C++20 里用时，要先确认它是不是 DR。Clang、GCC 的状态页和 cppreference 的编译器支持表都会把 DR 单独标出。本站用 {{dr}} 标记这类修改。

<details class="fine" markdown="1"><summary>CWG issue 的状态</summary>

CWG issue 列表上的状态记录一个问题处理到了哪一步：Open（新问题）、Drafting（有初步共识，还没有措辞）、Review（有了措辞）、Ready / Tentatively Ready（措辞已就绪，等待全体会议），NAD（not a defect，认定不是缺陷）。

通过以后，状态记录它被纳入了哪份文件，如 CD7 或 C++26。按列表开头的说明，这类状态既可以是 DR，也可以是只针对工作草案的修改（accepted），所以状态本身不说明是否追溯适用。要知道这一点，看 issue 页面的处理记录，或者看 Clang 的 C++ Defect Report Support 页，它按 issue 号列出 Clang 从哪个版本起实现了每个 DR。

</details>

## 怎样判断最后通过的是什么

提案的最后一个修订版不一定就是通过的版本：有的提案通过后又被后续提案修改，有的在通过前被拆分或合并，有的一直没有通过。按下面的顺序核对：

1. **状态 issue。** `wg21.link/Pxxxx/github` 的标签里有 `plenary-approved`，说明全体会议通过了。没有这个标签，提案里的设计就只是设计。
2. **当前草案。** 用 `python3 tools/eel.py <稳定名>` 或 eel.is 找到措辞改动的位置，确认文字在那里，并留意之后的修改，就像 P2647 那一条后来多了 block。
3. **附录 C。** [[diff.cpp20]]、[[diff.cpp23]] 等列出每个版本破坏兼容性的修改，条目里写着受影响的条款。
4. **特性测试宏。** [[cpp.predefined]] 中的值以年月表示，修改一个特性的提案通常会把它改成新的年月。编译器报告的值大致说明它实现到了哪一步。
5. **编译器状态页。** 它们列出实现的修订号，以及是否作为 DR 处理。

## 阅读路线

本栏目的其余页面各讲一个设计决定，按提案追溯：问题是什么，考虑过哪些方案，最后的措辞改了标准的哪里，带来了什么后果。可以按兴趣挑着读，也可以按下面的顺序。

**对象、值和初始化**

- [[papers/guaranteed-copy-elision|保证的复制消除]]：C++17 怎样通过重新定义纯右值，让 `return T{};` 不再需要可调用的复制构造函数。
- [[papers/implicit-object-creation|隐式创建对象]]：`malloc` 出来的内存为什么在 C++20 之前严格来说没有对象。
- [[papers/implicit-move|隐式移动]]：`return x;` 什么时候按右值处理。
- [[papers/range-for-temporaries|范围 for 与临时对象]]：范围初始化器中临时对象的生命周期延长。
- [[papers/trivial-relocation|平凡重定位]]：用一次内存复制代替移动加析构。

**声明、模板和元编程**

- [[papers/declarations-and-lookup|声明与名字查找]]：名字查找规则的重写。
- [[papers/deducing-this|显式对象形参]]：`this auto self` 解决的问题。
- [[papers/class-type-template-parameters|类类型的模板形参]]：哪些类的对象可以当模板实参。
- [[papers/pack-indexing|包索引]]：`Ts...[0]`。
- [[papers/reflection|静态反射]]：C++26 的 `^^` 和 `std::meta`。

**错误、安全和常量求值**

- [[papers/contracts|契约]]：`pre`、`post` 和 `contract_assert`。
- [[papers/erroneous-behaviour|错误行为]]：读未初始化变量为什么从 UB 变成了错误行为。
- [[papers/constexpr-exceptions|常量求值中的异常]]：`throw` 进入 constexpr。
- [[papers/library-hardening|标准库加固]]：带检查的前置条件。

**标准库**

- [[papers/std-execution|std::execution]]：sender/receiver 模型。
- [[papers/mdspan|mdspan]]：多维视图的设计。
- [[papers/print-and-format|std::format 与 std::print]]：类型安全的格式化。
- [[papers/ranges-to|ranges::to]]：把 range 收集进容器。
- [[papers/generator|std::generator]]：标准库里第一个协程类型。

## 思考题

!!! question
    一篇提案的措辞写着 Change [expr.prim.lambda.closure]/4，你在当前草案的这一段里找不到它要改的那句话。可能是什么原因？该怎么办？

<details markdown="1">
<summary>答案</summary>

段落号是提案写作时那一版草案的。之后的提案、issue 或编辑修改可能插入或删除了段落，也可能把条款拆开（P2647 那一段就从 [expr.const]/5.2 搬到了 [expr.const.core]/2.2）。还有一种可能是这篇提案没有通过，或者它的修改后来又被别的提案替换。

做法是在当前草案的同一稳定名下搜索提案里那句话的关键词；搬家的话，到相邻的子条款里找。找到以后以草案文字为准，再用状态 issue 确认这篇提案是否通过。
</details>

!!! question
    你的项目用 `-std=c++20` 编译。升级编译器以后，一处 `f({u8""})` 调用突然报歧义错误，`-std=` 没改过。为什么？

<details markdown="1">
<summary>答案</summary>

[[P2513R4]] 是对 C++20 的 DR。新编译器在 `-std=c++20` 下也采用修正后的 [[dcl.init.string#1]]，允许 `u8""` 初始化 `char` 数组，所以原本只有一个可行函数的调用多了一个候选。附录 C 的 [[diff.cpp20]] 记录了这个例子。给实参写明类型，如 `f(A{u8""})`，就能消除歧义。
</details>
