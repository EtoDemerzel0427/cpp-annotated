---
title: 实现的符合性与抽象机
summary: 标准与实现之间的"合同"：哪些错误必须诊断、哪些可以不管；as-if 规则与可观察行为；C++26 的 observable checkpoint 如何给 UB 的"时间旅行"划定边界；hosted/freestanding/hardened 实现与扩展。
status: done
covers: intro.compliance.general, intro.abstract
related: intro.defs, basic.contract.eval, intro.execution, compliance, topics/how-to-read-the-standard
tags: 符合性, as-if, UB, 可观察行为, 抽象机, contracts
updated: 2026-10-17
---

[intro.compliance] 是整本标准的"法律效力条款"。前面第 3 章（[[intro.defs]]）定义了 *ill-formed*、*undefined behavior* 这些词，这一节则说清楚：这些词对编译器厂商到底意味着什么义务。它分两部分：

- **[intro.compliance.general]**：静态的一面。一个程序拿到编译器面前，编译器必须接受、必须报错、还是可以随便处理？
- **[intro.abstract]**：动态的一面。编译出来的程序运行时，要表现得"像什么"？答案是：像一台**参数化的、非确定的抽象机**——但只在**可观察行为**上像。这就是 as-if 规则。

理解这一节，你就能回答这些问题："编译器只给了个警告，算符合标准吗？""为什么优化器能删掉我的溢出检查？""程序在第 100 行崩溃，为什么第 50 行的输出没了？""`-std=gnu++2c` 和 `-std=c++2c` 有什么区别？"

## 一、实现的符合性 [intro.compliance.general]

### 可诊断规则（¶1）

¶1 **可诊断规则**（diagnosable rules）是本文档中的全部语法和语义规则，除去两类：明确注明"no diagnostic is required"的规则，以及被描述为导致"undefined behavior"的规则。

这是一个排除式定义：**默认每条规则都可诊断**。标准不需要在每条规则后面写"违反者须诊断"，只需要在例外处注明。所以你读到一条 "shall" 规则（如"*X* shall not be a reference type"），如果附近没有 "no diagnostic is required"，违反它就是必须诊断的 ill-formed。

### 对程序的要求是怎样转化为对实现的要求的（¶2）

¶2 标准**只**对实现提要求。但很多要求如果说成对程序的要求会更好懂（"一个程序**应当**只包含一个 `main`"），所以标准经常这样写。¶2 给出了这种写法的翻译规则：

**¶2.1** 如果一个程序没有违反第 5 章 [[lex]] 到第 33 章 [[exec]] 以及 Annex D [[depr]] 的任何规则，符合标准的实现**应当接受并正确执行**这个程序——除非超出了实现的限制。

注意范围：从 [lex] 到 [exec]，**包括全部库条款**和弃用特性附录。脚注 3 补充说，"正确执行"可以包含未定义行为和错误行为，取决于所处理的数据——良构程序在某些输入下仍可能 UB，这不妨碍它被"正确执行"。

**¶2.2** 如果程序违反了某条不要求诊断的规则（IFNDR），本文档对实现**不施加任何要求**。

**¶2.3** **否则**，如果程序包含以下任何一项，符合标准的实现应当发出**至少一条**诊断信息：

- ¶2.3.1 违反任何可诊断规则；
- ¶2.3.2 一个含有 `#warning` 预处理指令的预处理翻译单元（[[cpp.error]]）；
- ¶2.3.3 使用了标为"conditionally-supported"而实现不支持的构造；
- ¶2.3.4 {{c++26}} 一个在**显然常量求值**（manifestly constant-evaluated，[[expr.const.defns]]）的语境中、以**检查型语义**（checking semantic）求值的契约断言（[[basic.contract.eval]]）发生了契约违反。

注 1：在模板实参推导和替换期间，某些在其他语境下需要诊断的构造会被区别对待，见 [[temp.deduct]]——这就是 SFINAE：替换失败只是让这个候选被丢弃，而不是报错。

**此外**，符合标准的实现**不得接受**：

- ¶2.4 含有 `#error` 指令的预处理翻译单元；
- ¶2.5 含有失败的 *static_assert-declaration* 的翻译单元（[[dcl.pre]]）；
- ¶2.6 {{c++26}} 在显然常量求值语境中以**终止型语义**（terminating semantic）求值、并发生契约违反的契约断言。

这一段有三个经常被忽视的要点。

**第一，"诊断"和"拒绝"是两回事。** 对于违反可诊断规则的程序，标准只要求"至少一条诊断信息"，**没有**要求拒绝编译。结合 [[intro.defs]] 中 *diagnostic message* 的宽松定义，一条警告就够了，实现完全可以接着生成可执行文件（¶11 明确允许这种"先诊断再接受"）。标准**唯一**禁止实现接受的，是 ¶2.4–¶2.6 这三种情形——它们是程序员**主动要求**编译失败的手段。

```cpp run ok
#warning "这个头文件已弃用"   // 必须诊断（¶2.3.2），但程序是良构的，可以被接受
int main() {}
```

```cpp run error
static_assert(sizeof(int) == 2, "需要 16 位 int");   // 不得接受（¶2.5）
```

```cpp run error
int x = "hello";   // error: 违反可诊断规则——必须诊断；理论上实现诊断后仍可接受
```

**第二，"否则"（Otherwise）的优先级。** ¶2.3 以"Otherwise"开头：如果一个程序**既**违反了 IFNDR 规则、**又**违反了可诊断规则，适用的是 ¶2.2——对实现没有任何要求，连诊断都不要求。当然，实际的编译器不会因此闭嘴，但在法律意义上，IFNDR 吞掉了一切。

**第三，契约在常量求值中的三种结局。** C++26 的契约断言在常量求值中被违反时，后果取决于这次求值采用的语义（由实现定义，[[basic.contract.eval]] ¶2）：

```cpp
constexpr int half(int n) pre(n % 2 == 0) { return n / 2; }
constexpr int a = half(4);   // OK
constexpr int b = half(3);   // 契约违反：
                             //   enforce / quick-enforce（终止型）→ 不得接受（¶2.6）
                             //   observe（检查型、非终止）     → 必须诊断（¶2.3.4），可以接受，b == 1
                             //   ignore                         → 什么都不发生，b == 1
```

observe 语义的设计意图是"报告但继续"，所以在编译期它表现为一条必须发出的诊断（通常是警告），而不是硬错误。截至写作时，本机 Clang 23 还不支持契约语法，这段代码无法验证，以上按标准原文分析。

!!! note "static_assert(false) 在模板里"
    "失败的 *static_assert-declaration*"有精确的定义（[[dcl.pre#13]]）：若表达式在**模板定义的语境中**求值，该声明没有效果，不算失败；只有在实例化时求值为 `false` 才算失败。同时 [[temp.res.general#6]] 在判断"模板能否生成有效特化"（否则 IFNDR）时，明确忽略失败的 *static_assert-declaration*。这两点合起来（C++23 的 [[P2593]] 引入）使得在从未被实例化的模板里写 `static_assert(false, ...)` 成为良构的惯用法：

    ```cpp run ok
    template<class T>
    void f() {
      static_assert(false, "f 不应被实例化");   // OK：f 从未被实例化
    }
    int main() {}
    ```

### "shall"、"should"、"may"、"can"

¶2 的翻译规则解释了标准里 "shall" 的含义。按 ISO 起草规则（ISO/IEC Directives Part 2）：

| 词 | 含义 | 在 C++ 标准中的效果 |
|---|---|---|
| shall / shall not | 要求 / 禁止 | 对程序：违反即非良构（可诊断，除非注明 NDR 或 UB）；对实现：符合性要求 |
| should / should not | 建议 | 不影响符合性。常出现在"*Recommended practice*"段落中 |
| may / need not | 允许 | 对实现：授权（"实现可以…"） |
| can / cannot | 能力、可能性 | 陈述事实，通常出现在注里，不构成要求 |

注和例子（Note / Example）、脚注都是资料性的（informative），不能单独作为规范依据。所以在注里，标准刻意用 "can" 而不是 "may"——注不能授予许可。详见 [[topics/how-to-read-the-standard]]。

库条款里还有一套更细的分类：*Mandates*（不满足则非良构）、*Constraints*（不满足则不参与重载决议）、*Preconditions*（违反则 UB）、*Hardened preconditions*（见下文 ¶8）。它们定义在 [[structure.specifications]]，本质上是把上表的语义映射到函数规范上。

### 标准库由谁提供（¶3–¶6）

- ¶3 对类和类模板，库条款给出的是**部分**定义：私有成员不作规定，由实现补全。这就是为什么 libstdc++ 的 `std::vector` 里是 `_M_impl`，libc++ 里是 `__begin_`——它们都是实现私有的细节，程序不能依赖。
- ¶4 对函数、函数模板、对象和值，库条款给出**声明**；实现提供与描述一致的定义。注意，库规范中的签名是"描述性"的：实现可以添加默认实参、额外重载等，只要调用效果相同（详见 [[member.functions]]、[[global.functions]]）。
- ¶5 翻译单元通过 `#include` 相应的标准库头文件、或者 `import` 相应的标准库具名头文件单元来获得库中名字的访问（[[using.headers]]）。C++23 起还有 `import std;`，见 [[std.modules]]。
- ¶6 库中的模板、类、函数和对象具有外部链接。实现在把翻译单元组合成完整程序时（[[lex.phases]] 的第 8、9 阶段）按需提供库实体的定义。

外部链接意味着库实体在不同翻译单元中是同一个实体，受 ODR 约束。但这**不**意味着你可以对它们为所欲为：例如取大多数标准库函数的地址是未指定的甚至非良构的（[[namespace.std]] 中关于 *addressable function* 的规定），因为实现可能用重载或额外的默认实参实现它们。

### hosted 与 freestanding（¶7）

¶7 实现分为**宿主实现**（hosted implementation）和**独立实现**（freestanding implementation）。独立实现是执行时可以没有操作系统支持的实现。宿主实现支持本文档描述的全部设施；独立实现支持第 5 章到第 15 章描述的**全部语言**，以及 [[compliance]] 规定的**库子集**。

要点：

- **语言是完整的**：异常、RTTI、`new`、虚函数……在语言层面独立实现都必须支持。（实际上嵌入式工具链常提供 `-fno-exceptions`、`-fno-rtti`，但那是非符合的方言模式。）
- **库是子集**：[[compliance]] 的表格列出独立实现至少要提供的头文件（`<cstddef>`、`<limits>`、`<new>`、`<type_traits>`、`<utility>`、`<array>`、`<span>`、`<ranges>`、`<algorithm>` 等），每个头文件中只要求提供标为 *freestanding* 的条目（[[freestanding.item]]）。C++23 和 C++26 大幅扩充了这份清单。
- 独立实现中是否需要定义 `main`、程序如何启动和终止，都是实现定义的（[[basic.start.main]]）。
- 宏 `__STDC_HOSTED__` 在宿主实现中为 `1`，否则为 `0`（[[cpp.predefined]]）。

```cpp run ok
#if __STDC_HOSTED__
#include <cstdio>
int main() { std::puts("hosted"); }
#else
extern "C" void _start() { for (;;) {} }   // 启动方式由实现定义
#endif
```

本机 Clang 默认 `__STDC_HOSTED__` 为 1，加 `-ffreestanding` 后为 0。

### hardened implementation（¶8）{{c++26}}

¶8 实现是否为**加固实现**（hardened implementation）是实现定义的。在加固实现中，违反**加固前置条件**（hardened precondition）会导致契约违反。

[[structure.specifications]] ¶3.5 给出了细节：库函数可以规定 *Hardened preconditions*；

- 在加固实现中，调用该函数时，在其任何其他可观察副作用之前，以**终止型语义**求值相应的契约断言——违反即终止（经过契约违反处理）；
- 在非加固实现中，违反加固前置条件是**未定义行为**，与普通前置条件一样。

例如 `std::span::operator[]` 的加固前置条件是 `idx < size()`（[[span.elem]]），`vector::front()` 的是 `!empty()`（[[sequence.reqmts]]）。

```cpp run ub
#include <span>
#include <cstdio>
int main(int argc, char**) {
  int a[3] = {1, 2, 3};
  std::span<int> s(a);
  std::printf("%d\n", s[argc + 5]);   // 违反加固前置条件 idx < size()
                                      // 非加固实现：UB；加固实现：契约违反，程序终止
}
```

本机用 libc++ 默认配置编译，打印出一个垃圾值（UB）；加 `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_FAST` 编译后，程序在越界处陷入（SIGTRAP）终止。libstdc++ 的对应开关是 `_GLIBCXX_ASSERTIONS`。加固模式的意义在于：它把一大类最常见的内存安全漏洞（越界访问）从 UB 变成了有保证的终止，而且是**标准认可**的实现方式——见 [[P3471]]。

### 实现限制、Unicode 版本（¶9–¶10）

- ¶9 *Recommended practice*：鼓励实现在文档中说明它能处理的程序规模与复杂度的限制。Annex B [[implimits]] 列出了一些可能受限的量和建议的最小值（例如嵌套复合语句 256 层、模板递归实例化 1024 层）。这些都**不是要求**——¶2.1 已经给了实现以"超出限制"为由拒绝程序的权利。
- ¶10 实现可以使用比 [[intro.refs]] 引用的更新版本的 Unicode 标准（版本是实现定义的）。这影响标识符中允许哪些字符（[[lex.name]]）、`std::format` 的宽度估计等。

### 扩展（¶11）

¶11 符合标准的实现可以有扩展（包括额外的库函数），**前提是它们不改变任何良构程序的行为**。实现必须诊断使用了这些扩展、依照本文档为非良构的程序；诊断之后，可以编译和执行这些程序。

这一段同时给了实现两样东西：一是自由（扩展），二是约束（不得改变良构程序的行为，必须诊断非良构的使用）。

**合规的扩展**通常利用"保留名字"：以双下划线或下划线加大写字母开头的标识符保留给实现（[[lex.name]]），良构程序不会声明它们，所以 `__builtin_expect`、`__attribute__((...))`、`__int128` 这样的扩展不会与任何良构程序冲突。

**需要诊断的扩展**是那些让非良构代码"变得能用"的：VLA、GNU 语句表达式 `({ ... })`、零长数组等。

```cpp run error
int f() { return ({ int t = 1; t + 1; }); }   // GNU 语句表达式：非良构
```

本机 Clang 23 默认**静默接受**这段代码，只有加 `-pedantic` 才会给出 `-Wgnu-statement-expression` 警告。所以严格说来，不带 `-pedantic` 的 Clang 并不是一个符合标准的实现——它少发了诊断。VLA 则不同，Clang 默认就给出警告。

**不合规的扩展**会改变良构程序的含义。例如 GNU 方言模式把 `typeof` 当作关键字：

```cpp run ok
int typeof = 1;                      // 良构的 C++：typeof 只是个普通标识符
int main() { return typeof; }
```

在本机 Clang 23 上，`-std=c++2c` 正常编译；`-std=gnu++2c` 下第一行报错——因为在 GNU 模式中 `typeof` 是关键字。这就是为什么 `gnu++XX` 模式不是符合标准的模式。**"符合标准的实现"往往是"编译器 + 一组特定选项"**，比如 `-std=c++2c -pedantic-errors`。

### 文档义务（¶12）

¶12 每个实现都应当提供文档，说明它不支持的所有 *conditionally-supported* 构造，并定义所有 *locale-specific* 特性。脚注 4 补充：该文档也定义实现定义行为（见 [intro.abstract] ¶2）。

实践中，GCC 手册有专门的 "C++ Implementation-Defined Behavior" 章节，MSVC 文档也有类似内容；但坦白说，没有哪个主流实现的文档真正完整地列出了所有实现定义行为。

## 二、抽象机 [intro.abstract]

### 参数化的非确定抽象机（¶1）

¶1 本文档中的语义描述定义了一台**参数化的非确定抽象机**（parameterized nondeterministic abstract machine）。本文档对符合标准的实现的结构不作要求；特别地，它们不需要复制或模拟抽象机的结构。实现只需要模拟抽象机的（且**仅仅**是）**可观察行为**。

脚注 5 给了这条原则一个名字：**as-if 规则**。只要从程序的可观察行为来看，结果"如同"遵守了某条要求，实现就可以无视这条要求。例如，如果能推断出某个子表达式的值没被使用、也不产生影响可观察行为的副作用，实现就不必求值它。

```cpp run ok
int sum_to(int n) {
  int s = 0;
  for (int i = 1; i <= n; ++i) s += i;
  return s;
}
```

抽象机会老老实实循环 n 次。本机 Clang 23 `-O2` 生成的代码里没有循环，而是直接用乘法和移位计算 n(n+1)/2 的闭式公式。这完全合法：没有人能从可观察行为中区分出两者。

!!! tip "“抽象机”是 C++ 语义的唯一来源"
    标准里所有"先求值 A，再求值 B"、"对象在这里被创建"、"这个值被读出"的描述，都是对抽象机说的。编译器生成的机器码只对可观察行为负责。所以"我看了汇编，这里没有读内存，所以不是 UB"或者"这里有一条 load 指令，所以发生了访问"这类论证都是错的：UB 与否只能在抽象机上判断。

### 三类参数与非确定性（¶2–¶4）

¶2 抽象机的某些方面和操作是它的**参数**，被描述为**实现定义行为**（例如 `sizeof(int)`）或者**实现的性质**（例如类类型中的填充）。对实现定义行为，每个实现都要提供文档描述其特征和行为。这份文档定义了与该实现**对应的抽象机实例**（下文称"对应实例"，corresponding instance）。

¶3 抽象机的另一些方面和操作被描述为**未指定行为**（例如函数调用中实参的求值顺序，[[expr.call]]）。在可能的情况下，本文档给出一组允许的行为。这些构成了抽象机的**非确定**部分。因此，对于给定的程序和给定的输入，一个抽象机实例可以有不止一种可能的执行。

¶4 还有一些操作被描述为**未定义行为**（例如试图修改 const 对象的效果）。

把这三段串起来看，标准构建了一个层次清晰的模型：

1. 实现定义行为和实现的性质 → 确定"是哪一台抽象机"（对应实例）。
2. 未指定行为 → 这台抽象机上，同一程序同一输入可能有多条执行路径。
3. 未定义行为 → 某条执行路径上出现了"未定义的操作"。

接下来的 ¶6 用这个模型来规定实现的义务。

### 可观察检查点与定义前缀（¶5–¶6）{{c++26}}

¶5 程序执行中的某些事件被称为**可观察检查点**（observable checkpoints）。注 1：调用 `std::observable_checkpoint`（[[utility.undefined]]）是可观察检查点，契约断言求值的某些部分也是（[[basic.contract]]）。

¶6 先定义：一次执行的**定义前缀**（defined prefix）由这样的操作 *O* 组成——对于**每一个**未定义操作 *U*，都存在一个可观察检查点 *C*，使得 *O* happens-before *C*，且 *C* happens-before *U*。

注 2：数据竞争（[[intro.races]]）产生的未定义行为发生在**所有参与的线程**上。

然后是整个标准里最核心的一句要求：

!!! std
    A conforming implementation executing a well-formed program shall produce the observable behavior of the defined prefix of one of the possible executions of the corresponding instance of the abstract machine with the same program and the same input.

符合标准的实现执行一个良构程序时，必须产生：对应实例在同一程序、同一输入下的**某一条**可能执行的**定义前缀**的可观察行为。如果选中的那条执行包含未定义操作，实现在那之后可以产生任意额外的可观察行为。

把这个定义拆开来理解：

- **没有 UB 的执行**：不存在任何未定义操作 *U*，"对每个 *U*……"的条件自动（空真）成立，**所有**操作都在定义前缀中。实现必须产生整条执行的可观察行为。这就是普通的 as-if 规则。
- **有 UB 的执行**：一个操作要留在定义前缀里，必须有一个检查点把它和**每一个**未定义操作隔开。没有被检查点隔开的操作——哪怕它在时间上早于 UB——都不受保护。
- **"某一条"**：在未指定行为造成的多条可能执行中，实现可以任选一条。

**这解决了什么问题？** 在 C++23 及之前，对应的句子是：若某条可能的执行包含未定义操作，本文档对执行该程序的实现不施加任何要求，"甚至对第一个未定义操作**之前**的操作也不施加要求"。这就是所谓 UB 的"**时间旅行**"：UB 不仅让之后的事情没有保证，还能"回到过去"影响之前的行为。理论上，一个在第 100 行解引用空指针的程序，第 50 行的输出也可以不出现，因为编译器可以基于"第 100 行的 UB 不会发生"推出第 50 行所在的分支不会执行。

C++26 通过 [[P1494]]（Partial program correctness）引入了可观察检查点，给时间旅行设了一道墙：**UB 之前、最后一个检查点之前的可观察行为必须如实产生**。

哪些事件是检查点？

| 检查点 | 出处 |
|---|---|
| 调用 `std::observable_checkpoint()` | [[utility.undefined]] |
| 以检查型语义求值契约断言之前的某个点 | [[basic.contract.eval]] ¶6 |
| 每次把数据交付给宿主环境以写入文件的 C stdio 函数调用**返回**时 | [[cstdio.syn]] ¶2 |
| `basic_filebuf::overflow` 等把数据真正写出之后；`std::print` 写终端之后 | [[input.output]] 中的相应条款 |

**一个关键细节：缓冲。** "交付给宿主环境"指的是数据真的离开了程序——对 stdio 而言，是缓冲区被刷新到操作系统。`printf` 把数据写进用户态缓冲区并返回，并不算"交付"，因此这次返回**不是**检查点。

```cpp run ub
#include <cstdio>
int read(int* p) {
  std::puts("about to read");
  return *p;                 // p 为空：UB
}
int main(int argc, char**) {
  int* p = argc > 5 ? new int(1) : nullptr;
  return read(p);
}
```

在本机把输出重定向到文件（或管道）运行，程序以 SIGSEGV 结束，文件是**空的**：`puts` 只是把字符串写进了全缓冲的 stdout 缓冲区，进程崩溃时缓冲区没有被刷新，数据从未交付给宿主环境。C++26 下这也完全符合标准——没有检查点，"about to read" 不在定义前缀中。

如果在 `puts` 之后加上 `std::fflush(stdout);`，那么 `fflush` 的返回就是一个检查点（数据已交付），"about to read" 就**必须**出现在输出中：编译器不得再以"之后会 UB"为由把它优化掉或重排到 UB 之后。`std::observable_checkpoint()` 的作用类似，但它不刷新任何缓冲区——它只保证在它之前已经发生的可观察行为（例如已经完成的 volatile 访问、已经交付的数据）不会被之后的 UB "抹掉"。

!!! warning "volatile 访问是可观察行为，但不是检查点"
    ¶8.1 把 volatile 访问列为可观察行为，但 volatile 访问本身**不**建立检查点。一次 volatile 写之后紧跟 UB，那次写入并不在定义前缀里——除非两者之间还有一个检查点。

!!! impl
    截至写作时，本机 Clang 23 + libc++ 还没有提供 `std::observable_checkpoint`。对编译器而言，实现检查点的直观方式是把它当作一个"优化器看不透的调用"：优化器不能把 UB 带来的"不可达"推理传播过这样的调用，也不能把调用之前的可观察操作挪到它之后。

¶6 最后一句是关于错误行为的：如果某个操作的执行被规定为具有**错误行为**（[[intro.defs]]），实现**允许**发出诊断，并且**允许**终止程序的执行。

¶7 *Recommended practice*：实现**应当**在这样的操作被执行时发出诊断。注 3：实现也可以在能够确定"在实现特定的一组关于程序行为的假设下，错误行为是可达的"时就发出诊断——这可能产生误报。

这几句把 EB 和 UB 清晰地区分开了：

| | UB | EB |
|---|---|---|
| 对之后的可观察行为 | 任意 | 要么继续按定义执行，要么诊断，要么终止 |
| 对之前的可观察行为 | 检查点之前的受保护，之后的不受保护 | 全部受保护（EB 不是"未定义操作"） |
| 优化器能否假设它不发生 | 能 | 不能 |
| 编译期诊断 | 可以 | 可以（甚至允许误报，注 3） |

### 可观察行为（¶8）

¶8 以下规定了程序的**可观察行为**：

- ¶8.1 通过 volatile glvalue 的访问严格按照抽象机的规则求值。
- ¶8.2 数据被交付给宿主环境以写入文件（另见 ISO/IEC 9899:2024 7.23.3）。注 4：交付这样的数据之后紧接着一个可观察检查点（[[cstdio.syn]]）。并非所有宿主环境都能在程序终止之前访问文件内容。
- ¶8.3 交互式设备的输入输出动态应当这样进行：提示性输出在程序等待输入之前确实被交付。什么构成交互式设备是实现定义的。注 5：每个实现都可以定义抽象语义与实际语义之间更严格的对应。

就这三条。没有"内存的内容"，没有"执行时间"，没有"函数被调用了几次"——这些都不可观察，所以 as-if 规则允许任意改变它们。

**volatile（¶8.1）** 是程序员手里唯一的、在语言层面强制编译器保留每一次内存访问的工具，主要用于内存映射 I/O 和与信号处理程序通信：

```cpp run ok
int plain;
volatile int reg;
void store_plain()    { plain = 1; plain = 2; }   // 可以合并成一次 store 2
void store_volatile() { reg = 1;   reg = 2;   }   // 必须恰好两次 store，且顺序不变
```

本机 Clang 23 `-O2` 对 `store_plain` 只生成一条 store，对 `store_volatile` 生成两条。注意 volatile **与多线程同步无关**：它不提供原子性也不建立 happens-before，跨线程通信请用 `std::atomic`（[[atomics]]）。

**文件输出（¶8.2）** C++23 中这一条的措辞是"程序终止时，写入文件的所有数据应与按抽象语义执行程序可能产生的结果之一相同"——只约束**终止时**的文件内容。C++26 改为"数据被交付给宿主环境"，把关注点从"最终结果"移到了"交付这个事件"上，以配合检查点模型：一次交付发生了，它就是可观察的，之后的 UB 不能抹掉它。

**交互式设备（¶8.3）** 保证"提示先于等待"：`std::cout << "Password: "; std::cin >> pw;` 中，提示一定在等待输入前显示出来。标准库通过 `cin` 与 `cout` 的绑定（tie）实现这一点：从 `cin` 读之前会先刷新 `cout`（见 [[basic.ios.members]] 中的 `tie` 与 [[istream.sentry]]）。

### 为什么 as-if 只看可观察行为？

这是 C++ "零开销抽象"的根基。正因为内存内容、中间计算、函数调用都不可观察：

- 内联、常量传播、死代码消除、循环变换、寄存器分配……几乎所有优化都是 as-if 规则下的合法变换；
- 抽象层（迭代器、智能指针、lambda）可以在优化后完全消失；
- 但相应地，程序员**不能**依赖任何不可观察的东西：计时、栈布局、"这个变量应该还在内存里"，都可能被优化改变。

UB 让 as-if 规则更加锋利：优化器只需对**没有 UB 的执行**保持可观察行为，于是可以假设 UB 不发生，并据此推理。

```cpp run ub
int g(int x) {
  int y = x + 1;                 // x == INT_MAX 时：UB
  if (y < x) return -1;          // 只有发生了 UB 才可能为真
  return y;
}
```

本机 Clang 23 `-O2` 把 `g` 编译成单条加法：溢出检查被整个删除。对没有 UB 的执行，`y < x` 永远为假；而对有 UB 的执行，实现在 UB 之后可以做任何事。

## 实现视角

!!! impl
    - **诊断即警告**：GCC、Clang 对很多可诊断规则的违反只给警告（如 Clang 的 VLA、GCC 在某些上下文中的窄化转换），这在标准意义上是合规的。想要"所有可诊断违规都失败"，用 `-pedantic-errors`。MSVC 的符合模式是 `/permissive-`。
    - **方言模式**：`-std=gnu++XX`（GCC/Clang 的默认）不是符合模式；`-std=c++XX` 加 `-pedantic` 才是。
    - **UB 相关开关**：`-fwrapv`（让有符号溢出按补码回绕，把一种 UB 变成实现定义的选择）、`-fno-delete-null-pointer-checks`、`-fno-strict-aliasing` 都是"收窄 UB"的扩展——它们不改变良构程序的行为（只是给原本未定义的情形定义了行为），所以是合规的扩展。
    - **Sanitizer**：`-fsanitize=undefined,address` 在执行到 UB 时报告并（可选）终止。这完全合规：UB 之后实现做什么都行。
    - **加固**：libc++ 的 `_LIBCPP_HARDENING_MODE`、libstdc++ 的 `_GLIBCXX_ASSERTIONS` 等，是 C++26 加固实现的现实基础。
    - **freestanding**：`-ffreestanding` 让 `__STDC_HOSTED__` 为 0，并关闭对标准库函数语义的假设（例如不再把 `memcpy` 当作内建函数优化）。

## 历史与演进

!!! history
    - C++98 起标准就有"as-if"规则（作为脚注）和三类行为（实现定义、未指定、未定义），基本沿用 C 标准的框架。抽象机的描述最初是 [intro.execution] 的开头几段，后来独立成为 [intro.abstract]，[intro.execution] 本身也移到了第 6 章的 [[basic.exec]] 下。
    - C++11 起把 *conditionally-supported* 作为一类正式的构造。
    - C++23：`#warning` 被标准化（此前是常见扩展），列入 ¶2.3.2。
    - C++26：加入错误行为（[[P2795]]）、契约断言及其在常量求值中的诊断要求（[[P2900]]）、加固实现（[[P3471]]）、可观察检查点与定义前缀（[[P1494]]）。最后一项终结了"UB 甚至对其之前的操作也不施加要求"的措辞。
    - 独立实现的库子集在 C++20 之前非常小（基本只有语言支持库），C++23、C++26 通过一系列提案大幅扩展，并引入了"freestanding item"的标注方式和"删除定义"的做法（[[compliance]] ¶5）。

## 陷阱与常见误解

!!! pitfall "“编译器报错 = 程序非良构，编译通过 = 程序良构”"
    两个方向都不成立。良构程序可以收到警告（甚至因超出实现限制被拒绝）；非良构程序可以在诊断后被接受（扩展），IFNDR 程序可以毫无诊断地通过。

!!! pitfall "“C++26 之后 UB 不会再时间旅行了”"
    只是被限制了。定义前缀只保护**检查点之前**的可观察行为。两个检查点之间、UB 之前的可观察行为（比如还在缓冲区里的输出、一次 volatile 写）仍然不受保护。而且检查点保护的只是**可观察行为**，不是程序状态——UB 之前写入的普通内存照样可能"没写过"。

!!! pitfall "“程序终止是可观察行为”"
    ¶8 的三条里并没有"终止"或"返回码"。`main` 的返回值通过 `exit` 交给宿主环境，它的效果体现在宿主环境里（[[support.start.term]]），但抽象机层面的可观察行为只有那三条。一个无限循环、无副作用的程序和立即返回的程序之间的差别，由 [[intro.progress]] 的前进保证规则来处理，而不是由 ¶8。

!!! pitfall "“看汇编就能判断是不是 UB”"
    不能。UB 是抽象机层面的概念。今天的汇编看起来"没问题"，换个优化级别、换个编译器版本、改一行无关代码，结果可能完全不同。

## 思考题

!!! question "思考题 1"
    一个程序同时含有一处 ODR 违规（IFNDR）和一处类型错误（可诊断）。符合标准的实现必须对类型错误发出诊断吗？

<details markdown="1">
<summary>答案</summary>

不必须。¶2.3 以"Otherwise"开头，只在 ¶2.2 不适用时才适用；而程序含有 IFNDR 违规时，¶2.2 适用——"本文档对实现不施加任何要求"，自然也包括诊断义务。当然，任何实际的编译器都会报告类型错误，这是实现质量问题，不是符合性问题。
</details>

!!! question "思考题 2"
    下面的程序在 stdout 是终端（行缓冲）时运行，`p` 为空。C++26 是否保证 "start" 被打印出来？如果 stdout 被重定向到文件呢？
    ```cpp
    std::puts("start");
    *p = 0;
    ```

<details markdown="1">
<summary>答案</summary>

行缓冲时，`puts` 输出整行后会把数据交付给宿主环境，于是这次 `puts` 的**返回**是一个可观察检查点（[[cstdio.syn]] ¶2），"start" 的交付在定义前缀中，**必须**出现。

重定向到文件时 stdout 是全缓冲的，`puts` 只是写进缓冲区，没有交付，它的返回不是检查点；"start" 不在定义前缀中，不保证出现——本页的实验正是这种情况。想要无论如何都保证，在 `puts` 后加 `std::fflush(stdout)`。

（严格说，stdout 是否行缓冲、何时刷新，是 C 标准规定的、部分由实现定义的行为；以上分析假定典型的 POSIX 行为。）
</details>

!!! question "思考题 3"
    GCC 的 `-std=gnu++2c` 模式把 `typeof` 当关键字；Clang 默认接受 GNU 语句表达式而不发出任何诊断。哪一种违反了 ¶11 的哪一部分？

<details markdown="1">
<summary>答案</summary>

前者违反"扩展不得改变任何良构程序的行为"：`int typeof = 1;` 是良构的 C++，在 GNU 模式下却变成了错误。后者违反"实现必须诊断使用了扩展、按本文档为非良构的程序"：语句表达式不是合法 C++，Clang 默认却一声不吭。两者都说明：编译器的默认模式通常不是符合标准的模式。
</details>

## 小结

!!! summary
    - 可诊断规则 = 所有规则 − 注明 NDR 的 − 导致 UB 的。默认可诊断。
    - 违反可诊断规则：实现必须给**至少一条诊断**（警告即可），不必拒绝；必须**拒绝**的只有 `#error`、失败的 `static_assert`、常量求值中终止型语义下的契约违反。
    - IFNDR 优先于一切：程序中只要有 IFNDR 违规，实现就没有任何义务。
    - 独立实现支持完整语言 + 库子集；加固实现 {{c++26}} 把加固前置条件的违反变成契约违反（终止），而非 UB。
    - 扩展不得改变良构程序的行为，且必须诊断非良构的使用——GNU 方言模式和不带 `-pedantic` 的默认模式往往不满足这一点。
    - 抽象机 = 实现定义参数确定实例 + 未指定行为带来多条执行 + UB 标记未定义操作。
    - 实现只需复现**可观察行为**：volatile 访问、交付给宿主环境的文件数据、交互设备的提示顺序。
    - C++26 用**可观察检查点**和**定义前缀**限制了 UB 的时间旅行：被检查点隔开的、UB 之前的可观察行为必须如实产生。
    - EB 允许诊断和终止，但不是未定义操作，不能被优化器假设不发生。
