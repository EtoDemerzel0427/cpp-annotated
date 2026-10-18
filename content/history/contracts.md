---
title: 契约：从 C++20 撤回到 C++26 MVP
summary: C++ 契约二十余年的四个阶段：仿 D 语言的 N1613、Bloomberg 的宏契约、2018 年并入又在 2019 年 Cologne 会议被整体撤回的 C++20 契约（P0542），以及 SG21 从最小可行产品（MVP）重新出发、2025 年在 Hagenberg 并入 C++26 的 P2900；争论的焦点（继续执行、假设、构建级别、虚函数、安全性）、反对意见（P3506、P3573、P3829、P3835 等），与标准库加固的关系，以及 C++29 的后续扩展。
status: draft
since: c++26
order: 100
papers: N1613, N3604, P0380R1, P0542R5, P1429R3, P1607R1, P1823R0, P2076R0, P2388R4, P2521R5, P2695R1, P2900R14, P2899R1, P3573R0, P3471R4, P3097R3, P3850R0
related: basic.contract, basic.contract.eval, dcl.contract, stmt.contract.assert, support.contract, dcl.attr.assume, structure.specifications, topics/undefined-behavior
tags: 契约, 沿革, 安全性, 标准库加固
updated: 2026-10-18
---

契约（contracts）要表达的是函数的接口约定：调用前调用者必须保证什么（前置条件），返回时函数保证什么（后置条件），以及函数体里某一点上必然成立的条件（断言）。C 的 `assert` 宏能表达第三种，但它只能写在函数体里，只有开和关两种状态，违反时只能 `abort`。语言级契约要把前置条件和后置条件放到函数声明上，并且让程序可以选择发现违反之后如何处理。

这件事在 C++ 委员会里前后经历了四个阶段。2004 年的第一份提案仿照 D 语言，没有成功；2013 年 Bloomberg 提出基于宏的方案，也没有成功；2018 年一份由多方合写的设计并入 C++20 工作草案，却在 2019 年 7 月被整体撤回，这在 C++ 标准化历史上很少见；此后新成立的研究组 SG21 从一个最小可行产品（MVP）重新设计，成果 P2900 于 2025 年 2 月并入 C++26，并在 2026 年 3 月 C++26 定稿时经受住了最后一轮反对意见。

本页按时间顺序讲这段历史，重点是每一轮争论的技术理由。当前规则见 [[basic.contract]]（求值语义与违约处理）、[[dcl.contract]]（`pre` 与 `post`）、[[stmt.contract.assert]]（`contract_assert`）与 [[support.contract]]（`<contracts>` 库接口）。

本页的 C++26 契约代码无法在本机验证：本机 Homebrew Clang 23.1 不接受 `pre`/`post` 语法，也没有 `-fcontracts` 选项。这些代码块因此不标判定。

## 背景：Eiffel、D 与 assert 宏

Stroustrup 在 HOPL IV（§9.6.1）中回忆，他在 1970 年代初接触到 Peter Naur 的不变式（invariant）概念时就很受吸引；1990 年代初，C++ 曾考虑过一套名为 A++ 的断言系统，但被认为过于庞大而不实用。1980 年代后期，Bertrand Meyer 通过 Eiffel 语言推广了契约式设计（Design by Contract）：前置条件、后置条件和类不变式是接口的一部分。在覆盖函数上，前置条件不能加强、后置条件不能减弱，P2899R1（§3.3.2）把这称为 Eiffel、D 和 Ada 的经典模型。

D 语言把这套机制做进了语法，`in`、`out` 块分别写前置条件和后置条件。C++ 的第一份契约提案就直接借鉴了 D。

## 第一阶段：仿 D 的契约（2004–2006）

[[N1613]]（*Proposal to add Design by Contract to C++*，Thorsten Ottosen，2004 年 3 月）是第一份正式提案。P2899R1（§2.6，P2900 的设计说明）称它"heavily influenced by the D programming language"：前置条件和后置条件写在函数体前的 `in`、`out` 块中，还可以写类不变式，甚至在前置条件里内联写出违反时的处理方式：

```cpp title="N1613 的语法（历史提案，未被采纳）"
int foo(int& i)
in {                  // 前置条件块
    i > 0;
}
out {                 // 后置条件块
    i == in i + 1;
    return % 2 == 0;
}
do {                  // 函数体
    ++i;
    return 4;
}
```

这份提案又修订了四次：[[N1669]]、[[N1773]]（Abrahams、Crowl、Ottosen、Widman）、[[N1866]] 与 [[N1962]]（Crowl、Ottosen，2006 年）；同期还有 [[N1800]]（*Contract Programming For C++0x*）。修订中关键字改成了 `precondition`、`postcondition`，引用旧值的写法从 `std::old(x)` 改到 `__old(x)` 再到 `oldof(x)`，一度加入又删去了一种类似检查级别的重要性排序（importance ordering）（P2899R1 §2.6）。在虚函数上，N1613 采用与 D 相同的规则：覆盖函数继承被覆盖函数的契约，前置条件以逻辑或合并，后置条件以逻辑与合并（P2899R1 §3.3.2）。

这条路线最终没有进入 C++0x。Stroustrup 的说法是，这些提案在委员会受到认真对待，但失败的主要原因是 "perceived excess complexity and inelegant notation"（HOPL IV §9.6.1）。

## 第二阶段：宏契约（2013–2015）

第二轮来自 Bloomberg。John Lakos 与 Alexei Zakharov 在 2013 年提交了 [[N3604]]（*Centralized Defensive-Programming Support for Narrow Contracts*），它基于 Bloomberg BDE/BSL 库中长期使用的断言宏。这份方案放弃了在接口上声明契约，改为在函数体里使用一组断言宏，带有三个检查级别（safe、debug、optimized）、不同的构建模式，以及一个可由用户定义的违约处理函数（P2899R1 §2.6）。

它随后修订了多次，直到 [[N4075]]、[[N4135]] 和 [[N4378]]（2015 年），宏的名字也几经更改，最后一版叫 `contract_assert(x)`，与 C++26 断言语句的关键字恰好相同。Stroustrup 说它很受欢迎，但遇到两个问题：它基于宏；它只是实现代码里的断言，而不是增强接口的东西（HOPL IV §9.6.1）。据 P2899R1，这份提案最终没有在 WG21 全会上获得共识。

## 第三阶段：C++20 契约（2015–2018）

在宏契约受挫的同时，其他几方在探索不同的设计，包括 [[N4110]]（J. Daniel García）、[[N4293]]（García）、[[N4319]]（Dos Reis 等，*Contracts for C++: What are the Choices*）以及 [[N4415]]（Dos Reis、García 等，*Simple Contracts for C++*）。Stroustrup 记述说，来自微软、Facebook、Google 和马德里卡洛斯三世大学的一组人提出了不用宏、支持前置条件和后置条件的"simple contracts"，它同样有大规模工业使用的背景，但更强调契约在静态分析中的作用（HOPL IV §9.6.1）。

两派先合并成 [[P0246R0]]（*Contract Assert Support Merged Proposal*，2016），再与更多人合作写成 [[P0380R1]]（*A Contract Design*，Dos Reis、García、Lakos、Meredith、Myers、Stroustrup，2016）。据 Stroustrup 回忆，这一步是两派请他出面协调的结果，他认为分歧集中在"细节"上，应当存在一个包含双方核心需求的最小方案（HOPL IV §9.6.1）。这份设计由 García 继续完善为 [[P0542R5]]（*Support for contract based programming in C++*），2018 年 6 月在 Rapperswil 会议上并入 C++20 工作草案；随后 [[P1289R1]]（契约条件中的访问控制）与 [[P1323R2]]（后置条件与返回类型推导）也被加入（P2899R1 §2.6）。GCC 有这一版本的实现（[[P1680R0]]）。

C++20 契约使用类似属性（但并不是属性）的语法：

```cpp title="C++20 工作草案中的契约语法（2019 年已移除）"
int f(int x, int y)
    [[expects: x > 0]]              // 前置条件
    [[expects audit: y != 0]]       // 带检查级别 audit 的前置条件
    [[ensures r: r > x + y]]        // 后置条件，r 指代返回值
{
    int n = get_n();
    [[assert: n > 0]];              // 断言
    return x + y + n;
}
```

它的行为由几组互相作用的开关决定：

- **检查级别**（contract level）：`default` 表示开销低、生产环境中也可以检查的条件；`audit` 表示开销高、只在专门构建中检查的条件；`axiom` 表示主要给静态分析器看、从不在运行时检查的条件。
- **构建级别**（build level）：`off`、`default`、`audit`，决定哪些级别的契约被检查。
- **违约继续模式**（violation continuation mode）：违约处理函数返回后，程序是终止还是继续执行。

继续模式是争议的种子。Stroustrup 记述说，他的第一反应是 "but that's insane!"，而 Lakos 根据 Bloomberg 的经验坚持认为，给大型老代码库加契约时一定会出现违反：有些代码违反了契约但并没有真正出错，有些新契约本身写错了。有了继续模式，就可以用违约处理函数记录违反后继续运行，从而在一次运行中发现多处问题，并在已上线的代码中保持契约开启；这一点被接受为渐进采用契约的关键（HOPL IV §9.6.1）。

## 2018–2019：并入之后的分歧

并入工作草案之后，两类问题浮现出来。

**未检查的契约被假设成立。** 按 P0542R5 的措辞，一个没有被检查的契约如果其谓词不为真，行为未定义。P2899R1（§3.5.4）指出，这等于把未检查时的语义从 ignore 变成了 assume，并说各方对这是否是原设计意图意见不一。Stroustrup 举了一个例子：

```cpp title="HOPL IV 中的例子（C++20 契约语法）"
[[assert: p != nullptr]]
p->m = 7;
```

如果契约检查失败后程序可以继续执行，编译器可以从后面的 `p->m` 推出 `p != nullptr`，再据此删掉前面的检查，这就是所谓的 time-travel optimization（HOPL IV §9.6.1）。为此有多份修正提案，包括 García 的 [[P1290R3]]（*Avoiding undefined behavior in contracts*）与 Voutilainen 的 [[P1321R0]]（*UB in contract violations*）；EWG 在 2018 年 11 月的 San Diego 会议和 2019 年 2 月的 Kona 会议上就这些论文进行了投票（P2899R1 §3.5.4）。同样的担忧后来也是 [[topics/undefined-behavior]] 一类讨论的常见例子。

**由源码直接指定语义。** 2018 年 10 月起，Bloomberg 的 Joshua Berne、John Lakos 等人提交了一系列论文，包括 [[P1332R0]]（长期路线图）、[[P1333R0]]、[[P1334R0]] 与 [[P1429R3]]（*Contracts That Work*）。它们主张在每条契约上直接写出它的语义，例如 `[[assert check_maybe_continue: x>0]]` 或 `[[assert assume: p!=nullptr]]`，而不是只靠全局的构建级别和继续模式来控制（HOPL IV §9.6.1）。

对于这批论文，各方的看法差异很大。Stroustrup 在 HOPL IV 中认为，这些提案在 C++20 的新提案截止日期之后才提出，与工作草案中已达成一致的设计根本不同，可能把契约从断言系统变成一种新的控制流机制，并且大量的论文和邮件讨论挤占了修复现有设计缺陷的时间。Bloomberg 一方的理由则写在 [[P1607R1]]（*Minimizing Contracts*，Berne、Snyder、McDougall）的摘要里：现有的 `default`/`audit`/`axiom` 级别是大量妥协的结果，对许多希望使用契约的大型机构并不理想；在未定义行为与检查之间二选一、再用一个全局开关控制是否继续，这样的语义同样难以大规模使用。

2019 年 2 月的 Kona 会议上，Nathan Myers 的 [[P1426R0]]（*Pull the Plug on Contracts?*）提议撤回契约，投票结果为强烈赞成 2、赞成 7、中立 4、反对 14、强烈反对 7，没有通过（据 P1823R0 引述）。

## 2019 年 7 月 Cologne：撤回

据 P2899R1，Cologne 会议是 C++20 的特性冻结点。EWG 先是接受了 P1607 的方向，随后又改为采纳 [[P1823R0]]（*Remove Contracts from C++20*）（EWG 状态报告 [[P1018R4]]）。P2899R1 记录的 EWG 投票（2019-07-17）是"撤回 P1607 并接受 D1823R0"：强烈赞成 24、赞成 25、中立 3、反对 6、强烈反对 5；全会随后批准了这一提案。

P1823R0 的作者是 Nicolai Josuttis、Ville Voutilainen、Roger Orr、Daveed Vandevoorde、John Spicer 和 Christopher Di Bella。论文开头写道 "This is a proposal nobody likes and we are not happy to make it"，给出的理由是：

- 本次会议上 EWG 刚刚接受了重大的设计修改，而对这些修改是改进还是倒退存在明显分歧，连原设计的作者之间也没有一致意见；
- 委员会还在讨论这些修改意味着什么，还在当场设计细节；
- 没有实现经验，例如没有在标准库中试用过；
- 按照火车模型（train model），如果列车出发时某个特性还没有在可接受的状态上达成共识，就应该让它搭下一班车；继续强求契约进入 C++20 会给整个 C++20 带来风险。

论文同时声明它不评判或比较各个提案，并以 C++11 时撤回 concepts、后来以更好的方案回归为例。

关于这次撤回，各方的叙述有所不同。Sutter 在会议报告中说委员会发现还没有及时完成设计，并说 "All the main contracts proposers unanimously agreed" 推迟发布；Red Hat 的 Jason Merrill 在会议报告中说双方同意从 C++20 中移除契约、留待下一个标准再议。P2899R1（由 P2900 的作者撰写）认为，P1607 这一 "late and massive change" 削弱了对设计的信任，最终使整个特性的共识消失。Stroustrup 在 HOPL IV 中则把最后一年的讨论称为 "a classic case of nobody getting anything"。

会后成立了契约研究组 SG21，由 John Spicer 主持（Sutter，Cologne 2019 trip report；HOPL IV §9.6.1）。同期，向编译器注入假设的需求被单独拿出来，以 [[P1774R8]] 的 `[[assume]]` 属性进入 C++23（见 [[dcl.attr.assume]]；P2899R1 §3.5.4）。

## 2019–2023：SG21 与最小可行产品

SG21 的第一项工作是弄清 C++20 契约为什么失败。Voutilainen 的 [[P2076R0]]（*Previous disagreements on Contracts*，2020 年 1 月）把分歧归纳为五点：

| 分歧 | 内容 |
|---|---|
| 继续执行（continuation） | 违约后能否继续执行；如果能，是全局开关还是逐条控制 |
| 构建级别（build levels） | 用一条线性的级别刻度控制检查是否可行，是否应是唯一的控制方式 |
| 全局开关（global toggles） | 全局启用/禁用是否必须影响所有契约 |
| 源码中的字面语义（literal semantics） | 能否在单条契约上写死它的语义，不受全局开关影响 |
| 假设（assumption） | 未检查的契约是否被假设成立 |

据 P2899R1（§2.6），SG21 决定从头设计，而不是在 C++20 设计上修补。它先整理用例与术语（[[P1995R1]]、[[P2038R0]] 等），再由 [[P2182R1]]（*Contract Support: Defining the Minimum Viable Feature Set*）提出最小功能集。第一份正式提案是 Krzemieński 与 Ažman 的 [[P2388R0]]（2021 年 6 月），最后一版 [[P2388R4]] 的标题说明了它的范围：*Minimum Contract Support: either No_eval or Eval_and_abort*，即只支持不求值（No_eval）与求值并在失败时终止（Eval_and_abort）两种模式。各项设计决定的共识记录在 [[P2521R5]] 中。

2021 年 10 月，SG21 决定继续探索语法、谓词语义和后置条件语义等问题，即使这意味着赶不上 C++23。2022 年 11 月的 Kona 会议上，SG21 通过了 Doumler 与 Spicer 的路线图 [[P2695R1]]，目标定为 C++26；同年 12 月，SG21 否决了把 C++20 契约的最后版本发布为 TS 的提议（[[P2659R2]]），以免分散 MVP 的工作。2023 年 9 月起，提案以 [[P2900R0]]（*Contracts for C++*，Berne、Doumler、Krzemieński）为主文档，设计理由与投票记录则汇总在 [[P2899R1]] 中（以上均据 P2899R1 §2.6）。

这一阶段确定了两件影响很大的事。

**语法。** SG21 起初沿用 C++20 的类属性语法，但很多人认为双方括号过重，而且契约与属性的性质不同（属性可以被忽略、可以重排）。经过对类属性语法、闭包式语法（[[P2461R1]]）和条件中心语法（[[P2737R0]]）的比较，2023 年 11 月的 Kona 会议上 SG21 否决了所有类属性语法的变体，采纳了 [[P2961R2]] 提出的自然语法（natural syntax）（P2899R1 §3.2）：

```cpp title="C++26 契约语法（本机无法验证）"
int f(int x)
    pre(x > 0)              // 前置条件，pre 是上下文关键字
    post(r: r > x)          // 后置条件，r 指代返回值
{
    contract_assert(x != 42);   // 断言语句，contract_assert 是关键字
    return x + 1;
}
```

断言用新关键字 `contract_assert` 而不是 `assert`，是为了不与 C 的 `assert` 宏冲突。

**求值语义。** C++20 中，一条契约检不检查、失败后做什么，要从检查级别、构建级别和继续模式三者的组合推出来。P2900 把可能的行为直接列为四种具名的求值语义：ignore、observe、enforce、quick-enforce（见 [[basic.contract.eval]]）。observe 与 enforce 的区分来自 [[P2877R0]]（Berne、Honermann），quick-enforce 来自 Dionne、Na、Varlamov 的 [[P3191R0]]，后者面向不能承受违约处理机制开销、或需要尽量缩小攻击面的场合（P2899R1 §3.5.4）。assume 语义被有意排除，但允许实现作为扩展提供。

| | C++20 契约（P0542R5） | C++26 契约（P2900R14） |
|---|---|---|
| 语法 | `[[expects: …]]`、`[[ensures r: …]]`、`[[assert: …]]` | `pre(…)`、`post(r: …)`、`contract_assert(…)` |
| 选择行为的方式 | 检查级别 × 构建级别 × 继续模式 | 每次求值使用一种实现定义的求值语义 |
| 未检查时 | 谓词为假则 UB（即 assume） | ignore：没有效果，谓词仍是潜在求值的 |
| 检查失败后继续执行 | 继续模式为 on 时 | observe 语义 |
| 检查失败后终止 | 继续模式为 off 时 | enforce（先调用违约处理函数）与 quick-enforce（立即终止） |
| 违约处理函数 | 以实现定义的方式设置 | 可替换的 `::handle_contract_violation`（[[basic.contract]]） |
| 虚函数 | 覆盖函数的契约必须与被覆盖函数相同 | C++26 中非良构；C++29 草案中各自独立（见下文） |

## P2900 的设计原则：对历史分歧的回答

P2900R14 第 3.1 节列出了 16 条设计原则。把它们与 P2076 总结的 C++20 分歧对照来读，可以看出新设计在每个分歧点上选择了哪一边，或者有意不选：

| C++20 时的分歧 | P2900 的处理 | 相关原则 |
|---|---|---|
| 假设 | 不提供 assume 语义；契约不引入新的未定义行为（谓词中原有的未定义行为除外） | 原则 13：Explicitly Define All New Behavior |
| 继续执行 | 保留 observe 语义，但同时规定契约断言不是控制流，不能用于错误处理或输入校验 | 原则 12：Contract Assertions Are Not Flow Control |
| 构建级别 | 取消级别；每次求值使用哪种语义由实现定义 | 原则 5：Independence from Chosen Semantic |
| 全局开关与源码中的字面语义 | 都不在 C++26 中规定，留给实现与以后的扩展（P2900 脚注称将来的局部控制只能是显式的选择性标注） | 原则 14：Choose Ill-Formed to Enable Flexible Evolution |

其余几条原则解释了 C++26 中一些乍看奇怪的规则：

- **原则 1、2**（Prime Directive 与 Redundancy Principle）：在正确的程序中契约断言是多余的，加上或去掉任何一部分都不应改变程序是否正确。这是整套设计的基础。
- **原则 3**（Concepts Do Not See Contracts）：契约的存在不应改变概念的满足、重载决议、`if constexpr` 的分支或 `noexcept` 运算符的结果。
- **原则 6–9**：谓词不应有破坏性副作用，各条断言、同一断言的各次求值之间互相独立。因此标准允许谓词被求值零次、一次或多次（见 [[basic.contract.eval#5]] 的例子）。
- **原则 14**：在没有共识的问题上选择非良构，而不是未指明或未定义，以便以后扩展。C++26 中虚函数不能带 `pre`/`post` 就是这条原则的应用；它也让 C++29 加入 P3097 时不会改变任何已有程序的含义。
- **原则 15、16**：给现有函数添加契约不应破坏现有的正确调用，也不应破坏 ABI。后来 P3911 讨论总是强制执行的断言时，ABI 影响正是悬而未决的问题之一。

违约处理函数的设计也体现了这种取舍。C++20 中违约处理函数以实现定义的方式设置；C++26 规定它是一个名为 `::handle_contract_violation` 的可替换函数，参数为 `const std::contracts::contract_violation&`（[[basic.contract]]、[[support.contract]]），可以从参数中查询断言种类、求值语义、源码位置等信息：

```cpp title="handler.cpp（C++26，本机无法验证）"
#include <contracts>
#include <cstdio>

void handle_contract_violation(const std::contracts::contract_violation& v) {
    std::fprintf(stderr, "contract violated: %s\n", v.comment());
    // 正常返回时：observe 语义下继续执行，enforce 语义下程序终止
}
```

## 2024：EWG 审查与争议

2024 年 2 月，SG21 把 [[P2900R6]] 转交 EWG 与 LEWG 做设计审查，目标仍是 C++26。2024 年 3 月的 Tokyo 会议是第一轮审查，EWG 以十个投票记录了尚待回答的问题（P2899R1 §2.6）。

从这时起，反对意见开始以论文形式系统地出现：

- 微软的 Dos Reis 在 [[P3173R0]]（*P2900R6 may be minimal, but it is not viable*，2024 年 2 月）中表示微软不认为该设计可行。理由包括：契约谓词求值本身可能出现未定义行为，这违背了 SG21 曾经同意的安全优先原则（论文引用了 SG21 在 2020 年 10 月的一次投票）；对虚函数、函数指针、协程的支持不足；缺少在标准库中应用的经验。Dos Reis 早先的 [[P2680R1]]（*Contracts for C++: Prioritizing Safety*）也是这个方向。
- Voutilainen 在 [[P3265R3]]（*Ship Contracts in a TS*，2024 年 5 月）中建议先以 TS 发布，理由是缺乏实现、部署和使用经验，WG21 范围内对虚函数、协程、函数指针等问题没有共识，谓词中的未定义行为也可能影响运行时检查与静态分析。SG21 对"以 TS 而非 IS 发布"的建议投票结果为强烈赞成 1、赞成 3、中立 3、反对 12、强烈反对 10，形成反对的共识（P2899R1 §2.6）。
- 契约与静态分析的关系另有一组论文讨论，例如 Voutilainen 的 [[P3362R0]]，以及作为回应的 [[P3376R0]]（Krzemieński）与 [[P3386R1]]（Berne）。

**虚函数**是这一年里反复最多的问题。2023 年 8 月，SG21 一度决定覆盖函数隐式继承被覆盖函数的契约（[[P2954R0]]）；2024 年 1 月又改为在 MVP 中禁止虚函数带 `pre`/`post`。Tokyo 会议上 EWG 就"MVP 是否应支持虚函数上的契约"投票，结果为强烈赞成 8、赞成 15、中立 10、反对 13、强烈反对 5，没有共识。此后出现两种模型：Doumler、Berne、Ažman 的 [[P3097R0]] 把契约分为调用方视角和被调用方视角，虚调用时先检查静态调用函数的前置条件，再检查最终覆盖函数的前置条件，各函数的契约彼此独立；Jonas Persson 的 [[P3169R0]] 则沿用 Eiffel、D、Ada 的继承模型。2024 年 6 月的 St. Louis 会议上，EWG 同意把 P3097 的模型并入 P2900，体现在 [[P2900R8]] 中（P2899R1 §3.3.2）。

2024 年 11 月的 Wrocław 会议上，EWG 与 LEWG 批准了 [[P2900R11]] 的设计，转交 CWG 和 LWG 做措辞审查。EWG 的投票为强烈赞成 25、赞成 17、中立 0、反对 3、强烈反对 12（P2899R1 §2.6）。

## 2025 年 2 月 Hagenberg：进入 C++26

Hagenberg 会议之前，又出现了两份综合性的反对意见：

- [[P3506R0]]（*P2900 Is Still not Ready for C++26*，Dos Reis）认为谓词求值中的未定义行为仍未得到处理；虚函数方案过于复杂，偏离了数十年来虚函数的典型用法；函数指针问题被推迟；标准库的实现经验只是把现有断言换成了 `contract_assert`，没有用到前置和后置条件。它还反对把谓词抛出的异常一律当作违约，认为这会带来代码体积和运行时开销。
- [[P3573R0]]（*Contract concerns*，Stroustrup、Hava、García、Regev、Dos Reis、Spicer、van Winkel、Vandevoorde、Voutilainen）逐条列出了十几项担忧，包括：constification（谓词中的变量被当作 const）收益小而代价大；谓词抛出异常不应被视为违约；虚函数模型未经验证；设计不稳定（"10+ papers suggesting changes, 1,000+ reflector messages"）；实现定义的内容过多，难以教学；不能把契约分组分别开关；与 profiles 和安全性的关系不明；不同契约设置的翻译单元链接在一起时的行为没有充分规定。论文的结论是，作者们怀疑这些问题能否在 C++26 之前解决。

P2900 的作者在 [[P3591R0]]（*Contextualizing Contracts Concerns*）中逐条回应。另有一种在会上多次提出、但没有写成论文的意见：契约检查可能以 observe 或 ignore 语义执行，因此不能提供安全保证。对此，[[P3500R1]]（*Are Contracts "safe"?*）与 [[P3578R0]] 区分了功能安全（functional safety）与语言安全（language safety），并介绍了在现有设计中让断言总是强制执行的几种做法；Berne 的 [[P3400R0]] 则提议以后用标签（label）支持这种用法（P2899R1 §2.6）。

EWG 在 Hagenberg 讨论了这些问题，并作了两个决定（P2899R1）：

1. 关于"从 C++26 中移除 P2900、另找发布载体"的投票，结果为强烈赞成 9、赞成 8、中立 3、反对 19、强烈反对 41，形成反对移除的共识。
2. 关于虚函数，EWG 认为调用方/被调用方模型还不够成熟、理解不够充分，又没有其他模型可选，于是决定完全禁止虚函数带 `pre`/`post`，推翻了 St. Louis 的决定。这一修改体现在 [[P2900R14]] 中。

2025 年 2 月 16 日的全会上，P2900R14 并入 C++26 工作草案。Sutter 后来在 2026 年 3 月的会议报告中给出了这次全会投票的数字：100 票赞成、14 票反对、12 票弃权。他在 Hagenberg 报告中指出，这是契约第二次被投票加入 C++ 草案。

同一次会议还通过了两份相关论文：Herring 的 [[P1494R5]]（*Partial program correctness*），引入可观察检查点（[[g:observable-checkpoint]]），防止编译器把检查点之后的未定义行为反过来作用到之前已经执行的契约检查上（[[basic.contract.eval#6]]）；以及下一节的标准库加固 [[P3471R4]]。

## 与标准库加固、profiles 的关系

[[P3471R4]]（*Standard Library Hardening*，Konstantin Varlamov、Louis Dionne）与 P2900 在同一次会议上并入 C++26。它在库规范中引入加固前置条件（[[g:hardened-precondition]]）：在加固的实现中，调用函数之前要以终止型求值语义检查这些条件；在未加固的实现中，违反它们仍是未定义行为（[[structure.specifications#3.5]]）。按 Sutter 的会议报告，它覆盖 `std::span`、`std::string_view`、各顺序容器、`std::string`、`std::mdspan`、`std::optional`、`std::expected` 等的越界和空值访问，是契约特性的第一个使用者；论文引用的数据是在 Google 部署时性能开销"as low as 0.3%"。

加固与契约的关系后来又出现过一次修改。Voutilainen、Wakely、Spicer 的 [[P3878R0]]（2025 年 10 月）标题是 *C++26 Contracts are not a good fit for standard library hardening*；修订版 [[P3878R1]]（加入 Lavavej）把诉求收窄为 *Standard library hardening should not use the 'observe' semantic*，并在 2025 年 11 月的 Kona 会议上被采纳（Sutter，Kona 2025 trip report）。当前草案要求以终止型语义检查加固前置条件，正是这一修改的结果。

profiles 是同一时期的另一条安全性路线。Sutter 的 [[P3081R2]]（*Core safety profiles for C++26*）等提案希望以可选启用的方式对一段代码提供整体性的安全保证。[[P3573R0]] 把契约与 profiles 的关系列为尚未解决的问题之一；Voutilainen、Wakely、Dos Reis 的 [[P3608R0]]（*Contracts and profiles: what can we reasonably ship in C++26*，2025 年 1 月）建议 C++26 只发布 profiles 框架、标准库加固，以及一个打开加固并在违反加固前置条件时直接终止的 profile，其余内容推后。按 Sutter 2026 年 3 月的会议报告，profiles 最终没有进入 C++26，相关论文在 SG23 中作为 C++29 的工作继续推进。

## 2025–2026：定稿前的最后一轮

C++26 草案在 2025 年夏天进行了国际意见投票（CD ballot）。在此前后，反对一方又提交了两份论文：

- [[P3829R0]]（*Contracts do not belong in the language*，Chisnall、Spicer、Dos Reis、Voutilainen、García，2025 年 9 月）讨论什么样的特性应当成为语言特性，并认为 P2900 那样把契约做成语言特性是错误的方向。
- [[P3835R0]]（*Contracts make C++ less safe — full stop*，Spicer、Voutilainen、García，2025 年 9 月）的论点是：同一个内联函数或模板可能在以不同求值语义编译的多个翻译单元中实例化，链接器最终保留哪一份是不确定的，于是一个库无法保证自己的契约一定以它要求的语义执行。论文提到，Clang 实现的主要作者 Eric Fiselier 在 Hagenberg 会议上也指出过需要某种标签机制。

2025 年 11 月的 Kona 会议用了周一、周二的大部分时间审议契约相关的国家成员体意见，其中有意见提议把契约移出 C++26。Sutter 的会议报告称，会上的"strong consensus"是把契约保留在 C++26 中；会议修复了两个规范缺陷（其一即上文的 P3878R1）；并决定为 2026 年 3 月的会议探索一种把单条 `pre`/`post`/`contract_assert` 标记为必须强制执行的方法，以罗马尼亚国家成员体意见 RO 2-056 对应的 [[P3911R0]]（Neațu、Alexandrescu、Teodorescu、Nichita）为基础。P3911 的修订版 [[P3911R2]]（加入 Sutter）给出了 `pre!(…)` 与 `pre<terminating>(…)` 等几种候选语法，只允许被标记的断言使用 enforce 或 quick-enforce 语义。相关的设计讨论还有 [[P3912R0]]、[[P3919R0]] 与 [[P3946R0]]。

这一扩展最终没有进入 C++26，当前草案中也没有这种语法。按 Doumler 与 Berne 在 [[P3850R0]]（*A proposed plan for extending Contracts in C++29*，2026 年 5 月）中的说法，总是强制执行的断言"still has some unresolved questions regarding ABI impact"，没有在 C++26 时间框架内解决；鉴于多个国家成员体都把它列为重要用例，应在 C++29 周期内集中解决。

2026 年 3 月的 London（Croydon）会议完成了 C++26 的技术工作。Sutter 的报告称，最终的全会投票为 114 票赞成、12 票反对、3 票弃权，未能全票通过主要是因为对契约的保留意见；契约留在了 C++26 中（Sutter，Croydon 2026 trip report）。

## C++26 之后：C++29 的扩展

P3850R0 把 C++26 契约称为"by design, a minimal viable product"，并提出了 C++29 的扩展路线。已经发生的进展有：

- **虚函数。** P3850R0 回顾说，P3097 的设计"only narrowly missed inclusion in C++26"，是因为 P3506 和 P3573 提出它偏离了 Eiffel 和 D 的经典模型、缺乏部署经验，才在最后时刻被移除。2026 年 6 月的 Brno 会议把 [[P3097R3]]（*Contracts for C++: Virtual functions*）并入 C++29 工作草案（Sutter，Brno 2026 trip report）。按该论文，覆盖函数的断言与被覆盖函数的断言彼此独立。当前草案中 `__cpp_contracts` 的值为 `202606L`，[[dcl.contract]] 中虚函数各自声明契约的规则就来自这一修改。
- **标签。** Berne 的 [[P3400R4]]（*Controlling Contract-Assertion Properties*）提出 `pre<my_library | audit>(…)` 这样的标签语法，用来实现总是强制执行的断言、按库分组控制语义、把开销大的断言标为 `audit` 等。这在一定程度上回应了 P3573 关于契约无法分组控制的意见，也让人想起 C++20 的检查级别。
- **与现有断言宏的整合。** [[P3290R6]]（Berne、Doumler、Lakos）提议让现有的断言宏能够接入契约的违约处理机制。
- **未定义行为。** Doumler 与 Berne 的 [[P3100R8]] 提出一个系统处理标准中未定义行为的框架，把部分未定义行为和错误行为视为隐式的契约违反。

## 常见误解

!!! pitfall "C++20 里有契约"
    没有。C++20 契约只在工作草案中存在了约一年（2018 年 6 月到 2019 年 7 月），在 C++20 定稿之前就被 P1823 整体移除，从未出现在已发布的标准中。GCC 曾有该版本的实验性实现（P1680R0），但那不是标准 C++。

!!! pitfall "C++26 契约默认会被检查"
    标准没有这样规定。每次求值使用哪种语义是实现定义的（[[basic.contract.eval#2]]），标准只是建议实现提供两种翻译选项，分别让所有断言使用 ignore 或 enforce，并建议默认使用 enforce（[[basic.contract.eval#3]]，属于 Recommended practice，不具强制力）。这正是 P3835、P3911 一类意见的出发点。

!!! pitfall "没有检查的契约会被优化器当作假设"
    这是 C++20 契约的问题，不是 C++26 契约的行为。C++26 的 ignore 语义没有任何效果，谓词虽然是潜在求值的，但不会被求值（[[basic.contract.eval#4]]）；P2900 有意不提供 assume 语义。需要向编译器注入假设时，应使用 C++23 的 `[[assume]]`（[[dcl.attr.assume]]）。

!!! pitfall "contract_assert 只是换了名字的 assert"
    两者有几处实质区别：`contract_assert` 是语句而不是宏，不受 `NDEBUG` 控制，其语义由实现在四种求值语义中选择；违反时调用可替换的违约处理函数；谓词求值抛出异常也算作违约（[[basic.contract.eval#7]]）。P3290 讨论的正是如何让现有断言宏接入同一套机制。

## 时间线

| 时间 | 事件 | 出处 |
|---|---|---|
| 1980 年代后期 | Meyer 通过 Eiffel 推广契约式设计 | HOPL IV §9.6.1 |
| 2004-03 | 第一份 C++ 契约提案，仿照 D 语言 | [[N1613]] |
| 2004–2006 | 四次修订，未进入 C++0x | [[N1669]]、[[N1773]]、[[N1866]]、[[N1962]] |
| 2013-03 | Bloomberg 的宏契约提案 | [[N3604]] |
| 2014–2015 | 宏契约多次修订；simple contracts 等不同设计 | [[N4378]]、[[N4415]] |
| 2016 | 合并提案；多方联名的契约设计 | [[P0246R0]]、[[P0380R1]] |
| 2018-06 | Rapperswil 会议，C++20 契约并入工作草案 | [[P0542R5]]；HOPL IV |
| 2018-10/11 | 由源码指定语义的系列提案；UB 问题的修正提案 | [[P1332R0]]、[[P1429R3]]、[[P1290R3]]、[[P1321R0]] |
| 2019-02 | Kona 会议，撤回契约的提议被否决 | [[P1426R0]]；[[P1823R0]] |
| 2019-07 | Cologne 会议，先接受 P1607，后撤回整个契约；成立 SG21 | [[P1607R1]]、[[P1823R0]]、[[P1018R4]] |
| 2020-01 | 整理 C++20 契约的分歧 | [[P2076R0]] |
| 2020–2021 | 最小功能集；第一份 MVP 提案 | [[P2182R1]]、[[P2388R4]] |
| 2021-10 | SG21 决定继续设计工作，放弃 C++23 | P2899R1 |
| 2022 | `[[assume]]` 单独进入 C++23 | [[P1774R8]] |
| 2022-11 | Kona 会议，SG21 通过以 C++26 为目标的路线图 | [[P2695R1]] |
| 2023-09 | P2900 第一版 | [[P2900R0]] |
| 2023-11 | Kona 会议，SG21 采纳自然语法 | [[P2961R2]] |
| 2024-02 | SG21 把 P2900R6 转交 EWG/LEWG | P2899R1 |
| 2024-03 | Tokyo 会议，EWG 首轮审查；微软的反对意见 | [[P3173R0]] |
| 2024-05 | 以 TS 发布的提议，SG21 反对 | [[P3265R3]] |
| 2024-06 | St. Louis 会议，虚函数支持并入 P2900 | [[P3097R0]]、[[P2900R8]] |
| 2024-11 | Wrocław 会议，EWG/LEWG 批准设计 | [[P2900R11]] |
| 2025-01 | 综合性反对意见与回应 | [[P3506R0]]、[[P3573R0]]、[[P3591R0]]、[[P3500R1]] |
| 2025-02 | Hagenberg 会议，移除虚函数支持后 P2900R14 并入 C++26；标准库加固并入 | [[P2900R14]]、[[P3471R4]]、[[P1494R5]] |
| 2025-09 | 两份要求移除契约的论文 | [[P3829R0]]、[[P3835R0]] |
| 2025-11 | Kona 会议，强共识保留契约；加固不得使用 observe | [[P3878R1]]、[[P3911R0]] |
| 2026-03 | Croydon 会议，C++26 定稿，全会投票 114 比 12 | Sutter，Croydon 2026 |
| 2026-05 | C++29 契约扩展路线图 | [[P3850R0]] |
| 2026-06 | Brno 会议，虚函数上的契约并入 C++29 草案 | [[P3097R3]] |

## 现状与未来

C++26 契约是一个有意做小的设计：三种断言（`pre`、`post`、`contract_assert`），四种求值语义，由实现决定每次求值使用哪一种（[[basic.contract.eval#2]]），并建议默认使用 enforce（[[basic.contract.eval#3]]）；可替换的违约处理函数；没有类不变式，没有 assume 语义，C++26 中也没有虚函数和函数指针上的契约。与 C++20 的设计相比，最明显的变化是去掉了未检查时假设谓词成立的语义，并把检查级别、构建级别、继续模式三个开关换成了直接命名的求值语义。

围绕它的争论并没有因为 C++26 定稿而结束。主要的分歧集中在几个问题上：同一份代码在不同翻译单元中以不同语义编译时，库作者能否得到可靠的保证（P3835、P3911）；契约应当提供哪一种安全，它与 profiles、标准库加固如何分工（P3500、P3573、P3608）；以及哪些功能应该放进最初的版本、哪些可以以后再加（P3573、P3850）。C++29 的工作正沿着 P3850 的路线推进：虚函数支持已经并入草案，标签、总是强制执行的断言等扩展仍在讨论中。

实现方面，GCC 16 的发布说明列出已实现 P2900R14；Clang 有由 Eric Fiselier 开发的实现（P2899R1、P3835R0 均提到），但截至写作时，本机的 Homebrew Clang 23.1 尚不接受契约语法。

## 参考资料

- Bjarne Stroustrup. *Thriving in a Crowded and Changing World: C++ 2006–2020*. Proc. ACM Program. Lang. 4, HOPL (2020)，§9.6.1 *Contracts*。
- Timur Doumler, Joshua Berne, Andrzej Krzemieński, Rostislav Khlebnikov. *Contracts for C++ — Rationale*，[[P2899R1]]，尤其是 §2.6（契约的简史）、§3.2（语法）、§3.3.2（虚函数）、§3.5.4（求值语义）。本页的大部分投票数字引自该文；它由 P2900 的作者撰写。
- 第一阶段：[[N1613]]、[[N1669]]、[[N1773]]、[[N1800]]、[[N1866]]、[[N1962]]。
- 第二阶段：[[N3604]]、[[N4075]]、[[N4135]]、[[N4378]]。
- 第三阶段：[[N4110]]、[[N4293]]、[[N4319]]、[[N4415]]、[[P0246R0]]、[[P0380R1]]、[[P0542R5]]、[[P1289R1]]、[[P1323R2]]、[[P1680R0]]。
- C++20 契约的争议与撤回：[[P1290R3]]、[[P1321R0]]、[[P1332R0]]、[[P1333R0]]、[[P1334R0]]、[[P1429R3]]、[[P1426R0]]、[[P1607R1]]、[[P1823R0]]、[[P1018R4]]（EWG 状态报告）、[[P2076R0]]。
- SG21 与 MVP：[[P1995R1]]、[[P2182R1]]、[[P2388R4]]、[[P2521R5]]、[[P2695R1]]、[[P2659R2]]、[[P2961R2]]、[[P2877R0]]、[[P3191R0]]、[[P1774R8]]。
- P2900 及其审查：[[P2900R0]]、[[P2900R6]]、[[P2900R8]]、[[P2900R11]]、[[P2900R14]]、[[P2954R0]]、[[P3097R0]]、[[P3169R0]]。
- 反对意见与回应：[[P2680R1]]、[[P3173R0]]、[[P3265R3]]、[[P3362R0]]、[[P3376R0]]、[[P3386R1]]、[[P3506R0]]、[[P3573R0]]、[[P3591R0]]、[[P3500R1]]、[[P3578R0]]、[[P3829R0]]、[[P3835R0]]。
- 加固与安全：[[P3471R4]]、[[P3878R0]]、[[P3878R1]]、[[P3081R2]]、[[P3608R0]]、[[P1494R5]]。
- 定稿前后：[[P3911R0]]、[[P3911R2]]、[[P3912R0]]、[[P3919R0]]、[[P3946R0]]、[[P3850R0]]、[[P3097R3]]、[[P3400R4]]、[[P3290R6]]、[[P3100R8]]。
- Herb Sutter 的会议报告（herbsutter.com）：Kona 2019（2019-02）、Cologne 2019（2019-07）、San Diego 2018（2018-11）、Hagenberg 2025（2025-02-17）、Kona 2025（2025-11-10）、*C++26 is done!* Croydon 2026（2026-03-29）、Brno 2026（2026-06-13）。
- Jason Merrill. *Report from the July 2019 ISO C++ meeting (core language)*，Red Hat Developer，2019-09-03。
- GCC 16 发布说明（gcc.gnu.org/gcc-16/changes.html）。
