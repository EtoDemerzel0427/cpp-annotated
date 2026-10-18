---
title: 术语与定义
summary: 标准的词典：69 个按字母排序的术语，其中最要紧的是 UB / unspecified / implementation-defined / erroneous 这套行为分类，以及签名、静态/动态类型、access 等贯穿全书的基础词汇。
status: done
related: intro.compliance, intro.abstract, topics/how-to-read-the-standard
tags: 术语, UB, 行为分类, 基础
updated: 2026-10-17
---

第 3 章 [intro.defs] 是整本标准的词典。它按 ISO 文件的统一格式编排：每个词条有编号（3.1、3.2 …）、一个 stable name（`defns.access`、`defns.undefined` …）、可选的⟨领域⟩限定，然后是一句不带冠词、可以直接代入正文的定义，后面可能跟着注和例子。

读这一章之前，要先明白两件事。

1. **这里只收录跨章节使用、又不便在某一节里就地定义的术语。** C++ 绝大多数核心术语，如 *odr-use*、*glvalue*、*literal type*、*immediate function*，都是在使用它们的那一节里就地定义的：标准正文里以斜体出现、紧跟着定义的词，就是一处定义（见 [[topics/how-to-read-the-standard]]）。所以第 3 章的词条看起来有点杂，一半是行为分类这样的元术语，另一半是库条款要用的词汇。
2. **ISO 的术语定义是可替换的。** ISO 的起草规则要求，定义能够直接替换正文中的术语而不改变意思。所以定义都写成名词短语（"behavior for which this document imposes no requirements"），而不是句子。读条文时遇到 *undefined behavior*，可以在心里把它换成"本文档不施加任何要求的行为"，这往往有助于看清规则到底说了什么。

同一个英文词在不同领域可以有不同定义，用⟨⟩标出领域。比如 *argument* 有四个词条（函数调用、函数式宏、throw、模板实例化），*signature* 有九个。读正文时要按上下文选取对应的那一条。

本页把 69 个词条按主题重新分组讲解，而不是按字母顺序。重点是第二部分的行为分类，这是 language lawyer 的基本功。

## 适用的外部术语（¶1–¶2）

¶1 除了本章列出的词条，ISO/IEC 2382（信息技术词汇）和 ISO 80000-2:2019（数学符号与术语）中的定义也适用。这意味着像 *byte*、*bit* 这样的基础词，以及区间记号 `[a, b)` 之类的数学写法，标准默认读者按这两份文件理解。它们都列在 [[intro.refs]] 里，是规范性引用。

¶2 给出了 ISO 和 IEC 两个在线术语库的地址。这是 ISO 文件的固定格式要求，对理解 C++ 没有影响。

## 一、程序与诊断：well-formed、ill-formed、diagnostic message

### well-formed program（3.69 [defns.well.formed]）

!!! std
    well-formed program: C++ program constructed according to the syntax and semantic rules

**良构程序**是按照语法规则和语义规则构造的 C++ 程序。

要点在"语义规则"四个字。它包括所有语义规则，既包括必须诊断的规则（类型不匹配、访问控制……），也包括标注了 "no diagnostic required" 的规则（ODR、模板定义中的某些要求……）。因此：

- 违反了一条 IFNDR 规则的程序**不是良构程序**，即使编译器没有任何提示就编译通过了。
- 良构是程序的静态属性，与运行时输入无关。一个良构程序在某些输入下可能产生未定义行为（例如用户输入 0 作除数），这并不影响它是良构的。[[intro.compliance]] 的脚注 3 专门说明了这一点：正确执行可以包含取决于数据的未定义行为和错误行为。

### ill-formed program（3.26 [defns.ill.formed]）

**非良构程序**是不是良构的程序。定义只有这一句，它是 well-formed 的补集。

非良构程序分两类，学会区分它们是 language lawyer 的第一课：

| | 何时出现 | 实现必须做什么 |
|---|---|---|
| ill-formed（必须诊断） | 违反任一可诊断规则（[[intro.compliance#1]]） | 至少发出一条诊断信息 |
| ill-formed, no diagnostic required（IFNDR） | 违反明确标注 "no diagnostic is required" 之类的规则 | 什么也不用做；对整个程序不施加任何要求 |

注意，IFNDR 不是第 3 章里的一个词条，它是由 [[intro.compliance]] ¶1 和 ¶2.2 推出来的：可诊断规则的定义排除了标注 "no diagnostic required" 的规则，而违反这种规则的后果是本文档对实现不再施加任何要求。当前草案新增的资料性附录 Annex G [[ifndr]] 收集了所有这类规则。

```cpp title="a.cpp"
inline int answer() { return 42; }
int from_a() { return answer(); }
```

```cpp title="b.cpp" ifndr
#include <cstdio>
inline int answer() { return 43; }   // IFNDR：同一 inline 函数在两个 TU 中定义不同，违反 ODR
int from_a();
int main() { std::printf("%d %d\n", from_a(), answer()); }
```

本机 Clang 23 链接这两个 TU 时没有任何诊断；`-O0` 下按 `a.cpp b.cpp` 的顺序链接打印 `42 42`，换个顺序打印 `43 43`，`-O2` 下打印 `42 43`（`from_a` 里的调用被内联了）。这正是 IFNDR 的含义：编译器看不到全局，标准就不要求它报错，而结果没有任何保证。详见 [[basic.def.odr]]。

### diagnostic message（3.18 [defns.diagnostic]）

!!! std
    diagnostic message: message belonging to an implementation-defined subset of the implementation's output messages

**诊断信息**是实现的输出信息中、属于某个由实现定义的子集的信息。

这个定义有意写得非常宽松：**标准不区分错误和警告**。只要实现在文档里说明它的警告也属于诊断信息，那么对一个必须诊断的非良构程序发出一条警告，然后照样生成可执行文件，就完全符合标准。[[intro.compliance]] ¶11 正是借此允许扩展：先诊断，再接受。

```cpp error
void g(int n) {
  int a[n];   // error: 数组边界不是常量表达式（VLA 不是 C++）
  a[0] = 0;
}
```

这段代码非良构。本机 Clang 23 默认只给出一条 `-Wvla-cxx-extension` 警告并照常编译，这条警告就是它履行诊断义务的方式；加 `-pedantic-errors` 后变为错误。两种做法都符合标准。

!!! pitfall "“编译通过”不等于“良构”"
    反过来也成立：编译器报了警告的程序未必是非良构的（警告大多针对良构但可疑的代码），编译器没报任何东西的程序也未必良构（IFNDR）。良构与否只能对照标准判断。

## 二、行为分类

这是第 3 章的核心。标准用一组精确定义的术语来描述程序做了某件事时，标准对实现有什么要求。按要求从强到弱排列如下：

```text
行为完全确定（标准规定唯一结果）
  │
  ├─ implementation-defined   结果取决于实现，实现必须写进文档
  ├─ property of the implementation   结果取决于实现，无需文档
  ├─ locale-specific          取决于本地化约定，实现必须写进文档
  ├─ unspecified              从一组允许的结果里任选，无需文档，每次可以不同
  ├─ erroneous (C++26)        行为是确定的，但它是程序错误；实现可以诊断、可以终止
  ├─ runtime-undefined        运行时是 UB；常量求值时不是
  └─ undefined                标准不施加任何要求
```

另外两个维度与之正交：conditionally-supported（实现可以不支持某个构造，但必须诊断）和 implementation limit（实现可以拒绝超出其能力的程序）。

### undefined behavior（3.66 [defns.undefined]）{{ub}}

!!! std
    undefined behavior: behavior for which this document imposes no requirements

**未定义行为**是本文档对其不施加任何要求的行为。

不施加任何要求就是字面意思：标准既不要求实现做什么，也不禁止实现做什么。注 1 列举了常见的实际表现：完全忽略这种情况并产生不可预料的结果，以环境特有的、有文档的方式处理（可以带也可以不带诊断），终止翻译或执行。但这只是注，范围并不限于此。

UB 的来源有两种（注 1 第一句）。

1. **显式 UB**：标准明确写了 "the behavior is undefined" 等字样。当前草案新增的资料性附录 Annex F [[ub]] 把第 4 章到第 15 章中所有显式 UB 都收集了起来。
2. **隐式 UB**：标准没有给出某种情况下的行为定义。例如标准规定了对象在生命周期内如何访问，没有规定生命周期外的访问，于是那就是 UB（虽然 [[basic.life]] 后来也把很多情况写成了显式 UB）。Annex F 明说不覆盖隐式 UB。

为什么需要 UB？有三个原因。

- 可移植性：不同硬件对同一操作的反应不同（越界访问、空指针解引用、整数除以零在 x86 上会陷入、在 AArch64 上结果为 0）。规定任何一种行为都会让另一些平台付出检查的代价。
- 可优化性：编译器可以假设 UB 不发生，从而推出更强的结论。有符号整数溢出是 UB，所以 `x + 1 > x` 可以直接折叠成 `true`；指针解引用之后，可以推断它不为空。
- 可诊断性的极限：很多错误（悬垂指针、数据竞争）在一般情况下无法在编译期判定，要求诊断就等于要求运行时检查。

```cpp run ub
int g(int x) {
  int y = x + 1;                        // x == INT_MAX 时：UB
  if (y < x) return -1;                 // "溢出检查"
  return y;
}
bool h(int x) { return x + 1 > x; }     // 恒为 true
```

本机 Clang 23 `-O2` 把 `g` 编译成一条加法指令，溢出检查整个被删掉了，因为只有发生了 UB 它才可能为真；`h` 直接返回 1。

注 1 的最后一句很重要，也常被忽略：

!!! std
    Evaluation of a constant expression never exhibits behavior explicitly specified as undefined in Clause [intro] through Clause [cpp].

**常量求值中不会出现核心语言的显式 UB。** 结合 [[expr.const.core]] 的规则，这意味着：如果常量求值过程中遇到了核心语言 UB，这个表达式就不是常量表达式，而在要求常量表达式的地方，这就是一个必须诊断的错误。所以编译器在编译期必须抓住核心语言 UB。

```cpp run error
#include <climits>
constexpr int inc(int x) { return x + 1; }
constexpr int a = inc(41);        // OK
constexpr int b = inc(INT_MAX);   // error: 求值中有符号溢出，不是常量表达式
```

注意范围限定在 "Clause [intro] through Clause [cpp]"，即核心语言。库的 UB（比如违反库函数的前置条件）在常量求值中是否使表达式成为非常量，是 unspecified 的（[[expr.const.core#4]]），因为编译器不一定能看穿库的实现。

!!! lawyer "UB 是针对执行而言的，不是针对程序"
    UB 描述的是某个操作在某次执行中的后果，而不是程序的静态属性。`int f(int* p) { return *p; }` 本身没有任何问题；只有当某次执行以空指针调用它时，那次执行才包含未定义操作。[[intro.abstract]] 正是在某次执行、某个输入的层面上描述 UB 的后果的；而且当前草案用 *observable checkpoint* 限制了 UB 对它之前已发生行为的影响，详见 [[intro.compliance]]。

### unspecified behavior（3.67 [defns.unspecified]）{{unspec}}

!!! std
    unspecified behavior: behavior, for a well-formed program construct and correct data, that depends on the implementation

**未指定行为**是对良构的程序构造和正确的数据而言，取决于实现的行为。注 1 补充说，实现无须在文档中说明会发生哪一种，可能的行为范围通常由标准划定。

它与 UB 的本质区别在于：未指定行为的前提是良构的构造加上正确的数据，**结果一定落在标准允许的集合里**，只是不说是哪一个。在抽象机的描述中（[[intro.abstract]] ¶3），这正是非确定性的来源：同一个程序、同一个输入，可以有多条合法的执行。

下面是几个典型例子：

```cpp run unspecified
#include <cstdio>
int g = 0;
int a() { g += 1; return g; }
int b() { g *= 2; return g; }
void show(int x, int y) { std::printf("%d %d\n", x, y); }
int main() {
  show(a(), b());                  // 打印 "1 2" 或 "1 0"：参数的求值顺序未指定
  const char* p = "abc";
  const char* q = "abc";
  std::printf("%d\n", p == q);     // 1 还是 0：两个字符串字面量是否为同一对象未指定
}
```

- 函数实参之间的求值是不确定顺序（indeterminately sequenced）的，见 [[expr.call]]。注意这与无顺序（unsequenced）不同：对同一标量的两次无顺序修改是 UB，而不确定顺序只是 unspecified。
- 字符串字面量是否共享存储，见 [[lex.string]]。

!!! pitfall "“未指定”不意味着“每次运行都一样”"
    实现无须写进文档，也无须保持一致：同一个程序在同一台机器上，不同的优化级别，甚至同一可执行文件中的两处调用，都可以做出不同的选择。不要依赖观察到的行为。

另一个容易混淆的点是：有些地方标准规定结果是未指定的，但如果某个选择会导致 UB，那么程序在那种选择下就是 UB。例如 [[cstdio.syn]] 对 `%p` 输入的规定是，结果是若干候选指针值中未指定的一个，而且只在那些"使程序具有已定义行为"的值中选取；如果没有这样的值，则行为未定义。

### implementation-defined behavior（3.27 [defns.impl.defined]）{{impl}}

!!! std
    implementation-defined behavior: behavior, for a well-formed program construct and correct data, that depends on the implementation and that each implementation documents

**实现定义行为**是对良构的程序构造和正确的数据而言，取决于实现、且每个实现都要写进文档的行为。

与未指定行为相比，定义里只多了 documents 一个词，但意义很大：**实现定义行为是抽象机的参数**（[[intro.abstract]] ¶2）。一个实现的文档把这些参数全部填好，就得到了这个实现对应的抽象机实例（corresponding instance）。程序员可以查文档，可以在一个实现上依赖它，只是不可移植。

```cpp run impl
#include <climits>
#include <cstdio>
int main() {
  std::printf("sizeof(int)=%zu CHAR_MIN=%d\n", sizeof(int), CHAR_MIN);
  char c = '\xff';
  std::printf("%d\n", c);          // -1 还是 255：char 是否有符号由实现定义
}
```

在本机（Apple arm64）上打印 `sizeof(int)=4 CHAR_MIN=-128` 和 `-1`；同样是 AArch64，Linux 上 `char` 通常是无符号的，打印 `255`。这就是取决于实现的含义，它甚至不取决于硬件，而取决于平台 ABI 的约定。

常见的实现定义行为：`sizeof` 除 `char` 系列以外的类型、`char` 的符号性、位域的分配细节、`#pragma` 的含义、`asm` 声明的含义、`reinterpret_cast` 在整数和指针之间的映射、`main` 以外的启动函数（freestanding）、`std::type_info::name()` 返回的字符串等。

!!! history
    一些曾经是实现定义的行为，后来由标准明确规定了下来。最著名的是 C++20：有符号整数的表示规定为二进制补码，负数右移成为算术右移，整数转换为有符号类型时按模运算取值。这些在 C++17 中都是实现定义的（或部分是 UB）。注意，有符号整数溢出在 C++20 之后仍然是 UB。

### property of the implementation（3.45 [defns.impl.prop]）

**实现的性质**是对良构的程序构造和正确的数据而言，取决于实现的行为。

这个定义和 implementation-defined 只差一处：没有 "each implementation documents"。[[intro.abstract]] ¶2 举的例子是类类型中的填充（padding）。它也是抽象机的参数，但实现没有义务写文档。例如编译器在两个成员之间插入多少填充字节，通常由 ABI 决定，不需要每个编译器在自己的文档里重复一遍。

### locale-specific behavior（3.30 [defns.locale.specific]）

**特定于区域设置的行为**是取决于国籍、文化和语言的本地约定，且每个实现都要写进文档的行为。

它是实现定义行为的一个特例，专门用于 `<locale>`、`<cctype>` 之类的设施，例如在非 "C" locale 下哪些字符算字母，小数点是 `.` 还是 `,`。[[intro.compliance]] ¶12 要求实现在文档中定义所有 locale-specific 特性。

### conditionally-supported（3.13 [defns.cond.supp]）

**有条件支持的**构造是实现不必支持的程序构造。注 1：每个实现都要在文档中列出它不支持的那些构造。

关键在 [[intro.compliance]] ¶2.3.3：如果实现不支持某个有条件支持的构造，而程序用了它，实现必须诊断。所以**有条件支持的构造从不会悄悄地变成 UB**：要么支持（且通常含义是实现定义的），要么报错。

```cpp
void f();
void* p = reinterpret_cast<void*>(&f);   // 函数指针 ↔ 对象指针：conditionally-supported
struct NT { NT(); NT(const NT&); ~NT(); };
void v(int, ...);
void call(NT x) { v(0, x); }             // 向 ... 传非平凡类对象：conditionally-supported
asm("nop");                              // asm 声明：conditionally-supported
```

本机 Clang 23 支持第一个（POSIX 的 `dlsym` 依赖这一点）；对第二个，Clang 选择不支持，给出一个默认即为错误的诊断（`-Wnon-pod-varargs`），这正体现了不支持就必须诊断的规定。出处分别是 [[expr.reinterpret.cast#8]]、[[expr.call]]、[[dcl.asm]]。

为什么要有这个类别？有些构造在某些平台上根本没有合理的实现（比如函数指针和数据指针大小不同的哈佛架构），但在主流平台上又很有用。有了"有条件支持"这个类别，标准就可以描述它们，而不必把它们变成 UB 或者直接禁止。

### erroneous behavior（3.21 [defns.erroneous]）{{c++26}} {{erroneous}}

!!! std
    erroneous behavior: well-defined behavior that the implementation is recommended to diagnose

**错误行为**是有明确定义、但建议实现加以诊断的行为。

这是 C++26 新增的类别，介于行为确定和 UB 之间。注 1 说明了三点：

1. 错误行为总是程序代码错误的后果，良构的、正确的程序不会出现它。
2. 实现可以诊断它，但不是必须。[[intro.abstract]] ¶6 进一步允许实现在执行到错误行为时发出诊断并终止程序，¶7 建议这样做。
3. 常量表达式的求值永远不会表现出错误行为，与 UB 一样，编译期必须抓住。

它和 UB 的根本差别是：**编译器不能假设错误行为不发生。** 这种行为有定义，所以优化器不能据此删掉代码路径，也不能推出矛盾。

核心语言中错误行为的主要来源是读取未初始化的自动变量（[[basic.indet]]）：

```cpp eb
int f() {
  int x;          // 自动变量、未初始化：其字节具有 erroneous value
  return x + 1;   // C++26：erroneous behavior；C++23：UB
}
```

在 C++26 中，未初始化的自动变量的字节具有**错误值**（erroneous value），即一个由实现选定、与程序状态无关的值。读取它是错误行为，结果就是那个值（加 1）。实现可以在这里报错终止，也可以返回那个固定的值，但不能像对待 UB 那样做任何事。如果确实需要旧的语义（比如为了性能避免初始化大缓冲区），可以给变量加 `[[indeterminate]]` 属性（[[dcl.attr.indet]]），这时读取它又回到 UB。

!!! impl
    截至写作时，本机 Clang 23 尚未实现 C++26 的错误行为语义：它对上面的 `f` 给出 `-Wuninitialized` 警告，`-O2` 下把 `f` 编译成一条 `ret`，直接返回寄存器里的残留值，这仍是 UB 的处理方式。它也还不认识 `[[indeterminate]]`（报 "unknown attribute" 警告）。Clang 和 GCC 的 `-ftrivial-auto-var-init=zero`/`pattern` 选项可以得到接近 EB 的效果，即把自动变量初始化成一个固定值。

!!! history
    错误行为由 [[P2795]]（Erroneous behaviour for uninitialized reads）引入 C++26。该提案的动机是安全：未初始化读取是一大类信息泄露漏洞的根源，而直接规定零初始化，又会把错误代码变成正确代码，使工具无法再报告它。错误行为同时做到了两点：行为可预测（安全），而且标准仍认定它是错误（可诊断）。

### runtime-undefined behavior（3.51 [defns.undefined.runtime]）

**运行时未定义行为**是除了在常量求值期间发生的情形之外，都属于未定义的行为。注 1：在常量求值期间，它是否使表达式被视为非常量是实现定义的（[[expr.const.core#3]]），除此之外没有任何效果。

目前它用于 `[[assume]]` 属性（[[dcl.attr.assume]]）。假设不成立时，运行时是 UB，优化器可以利用假设；而在常量求值中，实现可以选择把它当作非常量报告出来，也可以选择忽略这个假设。

```cpp error
constexpr int g(int x) {
  [[assume(x > 0)]];
  return x;
}
constexpr int a = g(1);    // OK
constexpr int b = g(-1);   // 假设不成立：在 Clang 上 error（实现定义的选择）
```

本机 Clang 23 选择把它视为非常量，报告 "assumption evaluated to false"。另一个实现可以接受 `b` 并初始化为 -1，同样符合标准。这里标注的 `error` 是针对 Clang 的选择而言的。

为什么不直接说 UB？因为常量求值中不允许出现核心语言 UB（见上文），如果 `[[assume]]` 失败是普通 UB，实现就必须在常量求值中检查每个假设，而假设的表达式可能代价很高，甚至在设计上就不应该被求值。runtime-undefined 把这个检查变成了可选项。

!!! history
    C++23 引入 `[[assume]]` 时，措辞是假设不成立时 "the behavior is undefined"，同时在 [expr.const] 中把它列为"是否为核心常量表达式未指定"的情形之一。runtime-undefined behavior 这一术语是之后才加入草案的，它把常量求值时的处理改成了实现定义。

### implementation limit（3.29 [defns.impl.limits]）

**实现限制**是实现施加于程序的限制。

[[intro.compliance]] ¶2.1 说，对于没有违反任何规则的程序，实现必须接受并正确执行，"除非超出了实现的限制"。抽象机的资源是无限的，真实的编译器则不然：模板实例化深度、嵌套层数、标识符长度、对象大小……Annex B [[implimits]] 列出了一些量和建议的最小值（例如复合语句嵌套 256 层），但这些数字不是要求，只是建议。

### 行为分类对比

| 类别 | 程序是否良构 | 结果范围 | 须写入文档 | 编译器可假设它不发生 | 常量求值中 | 典型例子 |
|---|---|---|---|---|---|---|
| implementation-defined {{impl}} | 是 | 实现选定、文档说明 | 是 | 否 | 按实现的选择求值 | `sizeof(int)`、`char` 的符号性 |
| property of the implementation | 是 | 实现选定 | 否 | 否 | 同上 | 类的填充 |
| locale-specific | 是 | 依本地约定 | 是 | 否 | — | `isalpha` 对非基本字符 |
| unspecified {{unspec}} | 是 | 标准给出的集合之一 | 否 | 否 | 求值可得任一允许结果 | 实参求值顺序 |
| conditionally-supported | 是（若支持） | 通常实现定义 | 须列出不支持的 | — | — | `asm`、函数指针转 `void*` |
| erroneous {{erroneous}} | 是 | 确定（如错误值） | — | 否 | 不会出现（必须报错） | 读未初始化自动变量 |
| runtime-undefined | 是 | 运行时无要求 | — | 是 | 是否视为非常量由实现定义 | `[[assume(false)]]` |
| undefined {{ub}} | 是（UB 是执行的属性） | 无要求 | — | 是 | 核心语言 UB 不会出现（必须报错）；库 UB 未指定 | 有符号溢出、越界 |
| ill-formed {{ill-formed}} | 否 | — | — | — | — | 类型错误 |
| IFNDR {{ifndr}} | 否 | 对整个程序无要求 | — | — | — | ODR 违规 |

可以按下面的流程简单判断：

1. 这个问题能在翻译期决定吗？如果违反的是语法/语义规则，有 "no diagnostic required" 就是 IFNDR，否则是 ill-formed。
2. 如果是运行时的事情，看标准有没有给出唯一结果。有，就是确定行为。
3. 如果没有唯一结果，看标准有没有给出允许的集合或要求文档。要求文档 → implementation-defined（或 locale-specific）；给出集合而不要求文档 → unspecified。
4. 标准说 erroneous → EB；说 undefined 或者根本没有规定 → UB。

## 三、类型、表达式与求值

### static type（3.62 [defns.static.type]）与 dynamic type（3.19、3.20 [defns.dynamic.type]、[defns.dynamic.type.prvalue]）

**静态类型**是不考虑执行语义、仅通过分析程序得到的表达式类型。注 1：它只取决于表达式在程序中的形式，执行期间不会改变。

**动态类型**有两条定义，按值类别区分。

- ⟨glvalue⟩：该 glvalue 所指代的最派生对象的类型。
- ⟨prvalue⟩：就是该 prvalue 表达式的静态类型。

prvalue 没有所指代的对象，所以它的动态类型就是静态类型。只有 glvalue（左值和亡值）才可能出现静态类型和动态类型不同的情况，而这只会因为派生类到基类的转换而发生。

```cpp run ok
#include <typeinfo>
#include <cstdio>
struct B { virtual ~B() = default; };
struct D : B { };
int main() {
  D d;
  B* p = &d;
  // 表达式 *p：静态类型 B，动态类型 D
  std::printf("%d\n", typeid(*p) == typeid(D));   // 1：对多态类型的 glvalue，typeid 看动态类型
  std::printf("%d\n", typeid(p)  == typeid(B*));  // 1：p 是指针 prvalue/lvalue，类型就是 B*
  B b2 = *p;                                       // 切片：初始化看的是静态类型 B
  std::printf("%d\n", typeid(b2) == typeid(B));    // 1
}
```

这两个概念是很多规则的基础：虚函数调用按动态类型分派（[[class.virtual]]）；[[basic.lval]] 的别名规则所说的"通过某类型的 glvalue 访问对象"，以及 [[expr.delete]] 中静态类型与动态类型不同时基类必须有虚析构函数的规定，也都用到了它们。

### access（3.1 [defns.access]）

!!! std
    access ⟨execution-time action⟩: read or modify the value of an object

**访问**是读取或修改对象的值。

注 1 是理解这个术语的关键。

- 只有标量类型的 glvalue 才能用来访问对象。读标量见 [[conv.lval]]（左值到右值转换），改标量见 [[expr.assign]] 和自增自减。
- 对类类型对象的读写通常是调用构造函数或赋值运算符，这种调用本身不算访问，虽然它可能包含对标量子对象的访问。

为什么要这么精确？因为很多规则是用访问来表述的：[[basic.lval]] 的严格别名规则限制的是"通过某类型的 glvalue 访问"；[[intro.races]] 中数据竞争的定义涉及对同一内存位置的冲突访问；[[intro.abstract]] 的可观察行为第一条是"通过 volatile glvalue 的访问"。如果把类对象的复制也算成一次访问，这些规则的边界就说不清了。

```cpp ok
struct S { int a; double b; };
void f(S& s, S& t) {
  t = s;           // 调用隐式的复制赋值运算符：这次调用本身不是"访问"
                   // 但它内部读取 s.a、s.b，修改 t.a、t.b：那四次才是访问
}
```

### constant evaluation（3.14）、constant subexpression（3.15）、non-constant library call（3.35）

- **常量求值**（[defns.const.eval]）是作为求值一个核心常量表达式（[[expr.const.core]]）的一部分而进行的求值。
- **常量子表达式**（[defns.const.subexpr]）：如果把一个表达式作为某个条件表达式 `CE` 的子表达式求值，不会阻止 `CE` 成为核心常量表达式，它就是常量子表达式。这个绕弯的定义是为库服务的：库规范用它（以及 *Constant When* 要素，见 [[structure.specifications]]）来说明在什么条件下，对某个函数的调用可以出现在常量表达式里。
- **非常量库调用**（[defns.nonconst.libcall]）：如果一次库函数调用作为求值某个表达式 `E` 的一部分，会阻止 `E` 成为核心常量表达式，它就是非常量库调用。[[expr.const.core]] ¶2.35 把它列为使表达式不是核心常量表达式的条件之一。

### referenceable type（3.46 [defns.referenceable]）

**可引用类型**是对象类型、不带 cv 限定符和引用限定符的函数类型，或引用类型。注 1：即可以为之创建引用的类型（包括引用类型本身）。

不可引用的类型只有两种：`void`（及其 cv 变体），以及形如 `int() const`、`void() &` 的"可恶的函数类型"（abominable function types），后者只能出现在成员函数的声明里。类型特征 `std::add_lvalue_reference` 等用这个术语规定行为：

```cpp ok
#include <type_traits>
static_assert(std::is_same_v<std::add_lvalue_reference_t<void>, void>);               // 不可引用：原样返回
static_assert(std::is_same_v<std::add_lvalue_reference_t<int() const>, int() const>); // 不可引用：原样返回
static_assert(std::is_same_v<std::add_lvalue_reference_t<int()>, int(&)()>);          // 可引用
static_assert(std::is_same_v<std::add_lvalue_reference_t<int&&>, int&>);              // 引用类型也算：引用折叠
```

## 四、实参、形参与执行中的阻塞

### argument（3.2–3.5）与 parameter（3.38–3.40）

标准严格区分**实参**（argument，调用处给出的东西）和**形参**（parameter，声明处引入的东西）。两者各有若干领域：

| 术语 | 领域 | 定义要点 |
|---|---|---|
| argument | 函数调用表达式 | 括号内逗号分隔列表中的表达式或 *braced-init-list* |
| argument | 函数式宏 | 括号内逗号分隔的预处理记号序列 |
| argument | throw 表达式 | `throw` 的操作数 |
| argument | 模板实例化 | 尖括号内的 *constant-expression*、*type-id* 或 *id-expression* |
| parameter | 函数或 catch 子句 | 函数声明/定义或异常处理器 catch 子句中声明的、在进入时获得值的对象或引用 |
| parameter | 函数式宏 | 宏名之后括号中逗号分隔的标识符 |
| parameter | 模板 | *template-parameter-list* 的成员 |

有几个细节值得注意。

- 函数调用的 argument 包括 *braced-init-list*：`f({1, 2})` 中 `{1, 2}` 是一个实参，尽管它本身不是表达式。
- 函数式宏的 argument 是记号序列，不是表达式：`MAX(a, (b, c))` 中第二个实参是 `(b, c)` 这五个记号。逗号只有在不被括号包围时才分隔实参，但这里只认圆括号，所以 `MAX(std::pair<int, int>{}, x)` 会被拆成三个实参。
- 模板实参（3.5）的三种形态正对应模板形参的三种：非类型、类型、模板模板。

### block（3.6、3.7）、deadlock（3.16）、unblock（3.65）

- **block** ⟨execution⟩：等待某个条件（而不是等待实现去执行该线程的执行步骤）得到满足之后，才继续执行、越过阻塞操作。括号里的排除很重要：一个线程只是没有被调度到 CPU 上运行，不叫阻塞；只有它在等待别的线程做某件事（释放锁、通知条件变量）时才叫阻塞。这与 [[intro.progress]] 的前进保证密切相关。
- **block** ⟨statement⟩：复合语句，即 `{ ... }`，见 [[stmt.block]]。两个领域同名，读正文时按上下文区分。
- **deadlock** ⟨library⟩：一个或多个线程无法继续执行，因为每个都被阻塞，等待其他线程满足某个条件。
- **unblock**：满足一个或多个被阻塞的执行线程正在等待的条件。

## 五、签名（3.52–3.60）

**签名**（signature）在标准中有九个词条，对应九种实体。注 1 说明了它的用途：签名是名字修饰（name mangling）和链接的基础。

| 领域 | 签名包含 |
|---|---|
| 函数（3.52） | 名字、形参类型列表、所在命名空间 |
| 带尾随 *requires-clause* 的非模板友元函数（3.53） | 名字、形参类型列表、所在类、尾随 *requires-clause* |
| 函数模板（3.54） | 名字、形参类型列表、所在命名空间、返回类型、*template-head* 的签名、尾随 *requires-clause*（如有） |
| 带有涉及外围模板形参之约束的友元函数模板（3.55） | 名字、形参类型列表、返回类型、所在类、*template-head* 的签名、尾随 *requires-clause*（如有） |
| 函数模板特化（3.56） | 所特化的模板的签名 + 模板实参（显式指定或推导的） |
| 类成员函数（3.57） | 名字、形参类型列表、所属的类、cv 限定符（如有）、*ref-qualifier*（如有）、尾随 *requires-clause*（如有） |
| 类成员函数模板（3.58） | 上一行的全部 + 返回类型（如有）+ *template-head* 的签名 |
| 类成员函数模板特化（3.59） | 成员函数模板的签名 + 模板实参 |
| *template-head*（3.60） | 模板形参列表（去掉形参名和默认实参）、*requires-clause*（如有） |

最值得记住的一点是：**普通函数的签名不含返回类型，函数模板的签名含返回类型。**

```cpp error
int  f(int);
long f(int);          // error: 两个声明只差返回类型
```

```cpp run ok
template<class T> int  f(T) { return 1; }   // #1
template<class T> long f(T) { return 2; }   // #2：签名包含返回类型，与 #1 是两个不同的模板
int main() {
  // f(0);                          // 若写出来：二义，#1 和 #2 都可行且无优劣之分
  int  (*p)(int) = &f<int>;         // OK：按目标类型选中 #1 的特化
  long (*q)(int) = &f<int>;         // OK：选中 #2 的特化
  return p(0) + q(0);               // 3
}
```

为什么模板要把返回类型放进签名？因为两个同样写作 `f<int>` 的特化可能来自不同的模板，它们在链接时必须是不同的符号。在 Itanium C++ ABI 下，上面两个特化分别修饰为 `_Z1fIiEiT_` 和 `_Z1fIiElT_`，中间的 `i`/`l` 就是返回类型 `int`/`long`；而普通函数 `int f(int)` 修饰为 `_Z1fi`，不含返回类型。

成员函数的签名包含 cv 限定符和引用限定符，所以它们可以重载：

```cpp ok
struct S {
  void g() &;
  void g() &&;          // OK：ref-qualifier 不同
  void h() const;
  void h();             // OK：cv-qualifier 不同
};
```

（`void S::g() const &` 在 Itanium ABI 下修饰为 `_ZNKR1S1gEv`：`K` 是 const，`R` 是 `&`。）

带尾随 *requires-clause* 的友元（3.53、3.55）是 C++20 引入约束之后才需要的特殊情形：类模板里定义的约束友元函数，在类模板的每次实例化中都是不同的函数，所以签名要包括所在的类，否则 `A<int>` 和 `A<long>` 里的同名友元会冲突。见 [[temp.friend]]。

!!! lawyer "签名与对应（correspond）"
    在今天的标准里，签名主要服务于链接和库规范。[[P1787R6]]（C++23 周期）重写了声明与查找的措辞，此后判断两个声明是否声明同一个实体、能否构成重载，用的是 [[basic.scope.scope]] 中**对应**（correspond）和对应的重载（corresponding overloads）的规则。那里使用的是形参类型列表、等价的尾随 *requires-clause*、对应的对象形参等更精细的条件，而不直接说签名相同。两者大体一致，但需要精确论证时，应该引用 [[basic.scope.scope]]。

## 六、库条款使用的术语

以下术语带有⟨library⟩限定或主要在库条款中使用。它们看起来琐碎，但库规范的每一句都建立在这些定义之上。

### 与 C 的关系、字符

- **C standard library**（3.8 [defns.c.lib]）：ISO/IEC 9899:2024 第 7 章描述的库。注 1：在第 17–33 章和 [[diff.library]] 所注明的限定下，C 标准库是 C++ 标准库的子集。
- **character** ⟨library⟩（3.9 [defns.character]）：按顺序处理时可以表示文本的对象。注 1 强调它不只是 `char`、`char8_t` 等，而是任何满足 [[strings]]、[[localization]]、[[input.output]]、[[re]] 要求的类型的值。所以 `std::basic_string<MyChar>` 中的 `MyChar` 也是字符。
- **character container type** ⟨library⟩（3.10）：用来表示 *character* 的类或类型；它是 `char_traits` 以及 `basic_string`、iostream、regex 等模板的模板形参。
- **NTCTS** ⟨library⟩（3.36 [defns.ntcts]）：null-terminated character type string，以 `charT()` 终止的字符类型值序列，即 C 风格字符串在任意字符类型上的推广。

### 库的组织与描述

- **component** ⟨library⟩（3.12）：通过成员、形参或返回类型直接关联的一组库实体。例如 `basic_string` 及操作字符串的非成员函数模板合称 string 组件。
- **traits class** ⟨library⟩（3.64）：封装了一组类型和函数的类，类模板和函数模板借助它来操作其实例化所用类型的对象（如 `char_traits`、`iterator_traits`、`allocator_traits`）。
- **modifier function** ⟨library⟩（3.32）：改变对象状态的成员函数（构造函数、赋值、析构除外）。**observer function** ⟨library⟩（3.37）：访问但不改变对象状态的成员函数；注 1：观察函数都规定为 `const` 成员函数。[[structure.specifications]] ¶2 规定，类成员的描述按构造/析构 → 复制/移动/赋值 → 比较 → 修改器 → 观察器 → 非成员的顺序排列。
- **move construction**（3.34）：用同类型的右值直接初始化某类型的对象。**move assignment**（3.33）：把某对象类型的右值赋给同类型的可修改左值。注意这两个定义只说右值，不涉及是否调用移动构造函数，因为库要求（如 *Cpp17MoveConstructible*）是用表达式描述的。
- **expression-equivalent** ⟨library⟩（3.22）：一组表达式具有相同的效果，要么都可能抛出要么都不可能抛出，要么都是常量子表达式要么都不是。这是规定 `ranges::begin` 这类 CPO（customization point object）时的核心词汇：说 `ranges::begin(E)` 与 `E.begin()` 表达式等价，不仅是说效果相同，也是说 `noexcept` 性和 constexpr 性相同。
- **projection** ⟨library⟩（3.44）：算法在检查元素值之前对其施加的变换。
- **stable algorithm** ⟨library⟩（3.61）：（按具体算法而言适当地）保持元素顺序的算法。具体要求见 [[algorithm.stable]]：对排序类算法，等价元素的相对顺序保持不变。

```cpp run ok
#include <algorithm>
#include <cstdio>
#include <utility>
#include <vector>
int main() {
  std::vector<std::pair<int, char>> v{{2,'a'},{1,'b'},{2,'c'},{1,'d'}};
  std::ranges::stable_sort(v, {}, &std::pair<int, char>::first);  // 投影：只按 first 比较
  for (auto [k, c] : v) std::printf("%d%c ", k, c);              // 1b 1d 2a 2c：等键元素保持原相对顺序
}
```

- **valid but unspecified state** ⟨library⟩（3.68）：对象的值未指定，但对象的不变式成立，对它的操作按其类型的规定工作。例子：处于此状态的 `std::vector<int>` 可以无条件调用 `empty()`，只有在 `empty()` 为 `false` 时才能调用 `front()`。被移动后的库对象通常处于这种状态（[[lib.types.movedfrom]]）。

```cpp run ok
#include <string>
#include <utility>
int main() {
  std::string s = "hello, world, a fairly long string";
  std::string t = std::move(s);
  // s 处于 valid but unspecified state：
  s.clear();          // OK：clear 没有前置条件
  s = "again";        // OK：赋值没有前置条件
  // s.back();        // 只有确认 !s.empty() 之后才能调用：back 有前置条件
}
```

### 程序可以替换或提供的函数

- **handler function** ⟨library⟩（3.25）：非保留的、其定义可以由 C++ 程序提供的函数。程序通过调用安装处理函数的库函数（`std::set_new_handler`、`std::set_terminate`）来指定它。
- **replacement function** ⟨library⟩（3.48）：非保留的、其定义由 C++ 程序提供的函数。典型例子是全局 `operator new`/`operator delete`（[[new.delete]]）。注 1：程序执行期间只有一个定义有效，这是程序构建和链接的结果。
- **required behavior** ⟨library⟩（3.49）：替换函数和处理函数的语义描述，同时适用于实现提供的和程序提供的定义。注 1：如果程序提供的定义在执行时不满足 required behavior，行为未定义。
- **default behavior** ⟨library implementation⟩（3.17）：实现提供的具体行为，在 required behavior 的范围之内。[[structure.specifications]] ¶5 解释了这对概念。
- **reserved function** ⟨library⟩（3.50）：作为标准库一部分、由实现定义的函数。注 1：如果程序为保留函数提供定义，结果未定义。

换句话说，替换函数是程序可以换掉的函数，换的时候要满足 required behavior；保留函数则是程序完全不能替换的函数。

### 程序定义的东西

- **program-defined specialization** ⟨library⟩（3.42）：不属于标准库、也不是由实现定义的显式特化或偏特化。
- **program-defined type** ⟨library⟩（3.43）：不属于标准库也不由实现定义的非闭包类类型或枚举类型；或者非实现提供的 lambda 表达式的闭包类型；或者程序定义的特化的实例化。注 1：实现定义的类型包括扩展和库内部使用的类型。

这两个术语决定了程序在 `std` 里能做什么：[[namespace.std]] 只允许为至少依赖一个程序定义类型的标准库类模板添加特化。例如为 `std::hash<MyType>` 特化是允许的，为 `std::hash<int>` 特化不允许。

### 指针的全序

- **implementation-defined strict total order over pointers** ⟨library⟩（3.28）：对所有指针值的实现定义的严格全序，与内置运算符 `<`、`>`、`<=`、`>=`、`<=>` 所施加的偏序一致。内置的 `<` 对不指向同一数组的两个指针给出的结果是未指定的（[[expr.rel]]），而 `std::less<T*>` 等函数对象保证使用这个全序（[[comparisons]]），所以可以放心地用它给任意指针排序、作为 `std::map` 的键。

### 正则表达式术语

以下七个词条带⟨regular expression⟩限定，或只用于 [[re]]：**collating element**（3.11，在当前 locale 下作为单个字符参与排序的一个或多个字符的序列，如某些语言中的 "ch"）、**finite state machine**（3.23，表示正则表达式、用于高效匹配的未指定数据结构）、**format specifier**（3.24，预期被匹配的某部分替换的字符序列，如 `$1`）、**matched**（3.31）、**primary equivalence class**（3.41，主排序键相同的字符集合，即只看字形，不看重音、大小写和本地裁剪）、**regular expression**（3.47）、**sub-expression**（3.63，用括号标记的正则表达式子集）。它们基本沿用 ECMAScript 和 POSIX 的概念，后者都是 [[intro.refs]] 中的规范性引用。

## 历史与演进

!!! history
    - C++98/03/11/14 中，术语与定义是第 1 章的一个小节（1.3 [intro.defs]）。C++17 按照 ISO 文件的标准结构重排了开头几章：第 1 章范围、第 2 章规范性引用、第 3 章术语和定义、第 4 章总则。stable name `[intro.defs]` 一直没变，这正是 stable name 的价值。
    - 词条的写法也随之按 ISO 格式统一：定义不带冠词、可以代入正文，注和例子作为编号的 Note/Example 跟在后面。
    - 一些旧术语已经移除，例如早期版本中的 *multibyte character*（多字节字符）等，字符集与编码相关的措辞全面重写之后，它们不再需要。
    - C++26 加入了 *erroneous behavior*（[[P2795]]）。此外，与 C++23 相比，当前草案还加入了 *runtime-undefined behavior* 等词条，以及资料性的 Annex F（核心语言 UB 汇总）和 Annex G（IFNDR 汇总）。
    - 签名的两个友元相关词条（3.53、3.55）是 C++20 引入约束（concepts）之后才需要的；`ref-qualifier` 随 C++11 的引用限定成员函数进入成员函数签名。

## 陷阱与常见误解

!!! pitfall "“有符号溢出是实现定义的”"
    不是。有符号整数的表示自 C++20 起固定为补码，但算术溢出仍是 UB（[[expr.pre]] ¶4）。无符号算术不会溢出，它按模 2ⁿ 回绕。

!!! pitfall "“UB 就是程序会崩溃”"
    UB 意味着标准不施加任何要求，崩溃只是可能的结果之一。更常见也更危险的情况是程序看起来正常运行，或者优化器基于 UB 不会发生做出了意想不到的推论。

!!! pitfall "“unspecified 和 implementation-defined 是一回事”"
    差别在于文档义务和一致性。实现定义的行为可以查文档，并在该平台上依赖；未指定的行为则不能依赖任何观察结果，即使是同一个编译器，在两处也可以做出不同的选择。

!!! pitfall "“IFNDR 只是链接期的问题”"
    IFNDR 规则遍布全书：ODR、模板定义没有任何合法实例化（[[temp.res]]）、概念的满足性结果在不同点不同……违反任何一条，标准对整个程序都不再有任何要求，在编译期也是如此。

!!! pitfall "“EB 就是 UB 换了个名字”"
    关键差别在于编译器不能假设 EB 不发生。对 UB，优化器可以删掉只有发生 UB 才会走到的路径；对 EB 则不行。

## 思考题

!!! question "思考题 1"
    下面这个程序在 C++23 中是否良构？在 C++26 中呢？它的执行有没有未定义行为？
    ```cpp
    int main() { int x; return x; }
    ```

<details markdown="1">
<summary>答案</summary>

在两个版本中它都是良构的：它没有违反任何语法或语义规则，而良构与否与运行时行为无关。

区别在于执行。C++23 中读取不确定值（indeterminate value）是 UB；C++26 中，未初始化自动变量的字节具有错误值，读取它是错误行为，实现可以诊断并终止，否则 `main` 返回某个由实现确定的值。只有给 `x` 加上 `[[indeterminate]]`，才会回到 UB。
</details>

!!! question "思考题 2"
    同一个命名空间里能否同时声明 `template<class T> int f(T);` 和 `template<class T> long f(T);`？能否同时声明 `int g(int);` 和 `long g(int);`？为什么标准要这样区别对待？

<details markdown="1">
<summary>答案</summary>

前者可以，后者不行。函数模板的签名（3.54）包含返回类型，两个模板并不对应（[[basic.scope.scope]] ¶4.5 要求 *corresponding signatures*，其中包括等价的返回类型），所以是两个不同的模板，可以共存；只是像 `f(0)` 这样的调用会有二义，需要通过取地址时给定目标类型等方式来选择。

后者的签名（3.52）只有名字、形参类型列表和命名空间，两个声明对应（声明同一个函数）但类型不同，违反 [[basic.link#11]]（同一实体的两个声明必须是同一类型），是必须诊断的错误。

理由在于链接：来自不同模板的特化 `f<int>` 必须可以区分，所以名字修饰里要编码返回类型（Itanium ABI 中的 `_Z1fIiEiT_` 与 `_Z1fIiElT_`）；普通函数不需要这样做，也不允许仅靠返回类型重载，否则 `g(0)` 这样的调用根本无法确定调用哪一个。
</details>

!!! question "思考题 3"
    `+"abc" == +"abc"` 的结果属于哪一类行为？去掉两个一元 `+` 呢？`sizeof(long)` 呢？`reinterpret_cast<void*>(&main)` 呢？

<details markdown="1">
<summary>答案</summary>

- `+"abc" == +"abc"`：unspecified。一元 `+` 让数组退化为指针，比较的是地址；两个字符串字面量是否为同一对象是未指定的（[[lex.string]]），实现无须写进文档。
- `"abc" == "abc"`：在当前草案中是 ill-formed，直接比较两个数组类型的操作数不再合法（见 [[diff.cpp23.expr]]；在 C++20 到 C++23 中它是弃用的）。本机 Clang 23 在 `-std=c++2c` 下报错。
- `sizeof(long)`：implementation-defined，实现必须写进文档。
- `reinterpret_cast<void*>(&main)`：ill-formed。`main` 不能被 odr-use（[[basic.start.main]]），取它的地址违反了可诊断规则。如果换成普通函数 `&f`，就是 conditionally-supported，其含义由实现定义。
</details>

## 小结

!!! summary
    - 第 3 章只收录跨章节的术语；大多数核心术语在正文中就地定义（斜体）。定义可以直接代入正文。
    - 良构要求满足所有语义规则（含 NDR 规则）；非良构分为必须诊断的和 IFNDR。诊断信息不区分错误和警告。
    - 行为分类：implementation-defined（须文档）、property of the implementation（无须文档）、locale-specific、unspecified（允许集合之一，无须文档）、erroneous（C++26，定义了但是错误，可诊断可终止、不能被假设不发生）、runtime-undefined（运行时 UB，常量求值中由实现决定是否非常量）、undefined（无要求）；外加正交的 conditionally-supported 和 implementation limit。
    - 常量求值中不会出现核心语言的 UB 和 EB，编译期必须抓住它们；库 UB 则是未指定的。
    - 静态类型来自程序文本；动态类型只对 glvalue 有意义（最派生对象的类型）。
    - 访问仅指通过标量 glvalue 读写；类对象的复制是函数调用，不是访问。
    - 普通函数签名不含返回类型，函数模板签名含返回类型；成员函数签名含 cv 和 ref 限定符。
