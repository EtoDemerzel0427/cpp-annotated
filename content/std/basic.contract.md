---
title: 契约断言
summary: C++26 契约：pre / post / contract_assert 的谓词、四种求值语义（ignore / observe / enforce / quick-enforce）、契约违反与违反处理函数
status: draft
covers: *
since: c++26
papers: P2900, P1494, P0542R5
related: dcl.contract.func, dcl.contract.res, stmt.contract.assert, support.contract, intro.execution, intro.abstract, expr.prim.id.unqual
tags: 契约, C++26, 求值语义
updated: 2026-10-17
---

{{c++26}} **契约断言**（contract assertion）让程序员把"此处程序状态应当满足的性质"写成语言的一部分，而不是注释或宏。C++26 提供三种：

```cpp
int isqrt(const int x)
  pre (x >= 0)                          // 前置条件断言：进入函数时
  post (r : r * r <= x && (r + 1) * (r + 1) > x)   // 后置条件断言：正常返回时
{
  int r = 0;
  while ((r + 1) * (r + 1) <= x) ++r;
  contract_assert (r >= 0);             // 断言语句：执行到此处时
  return r;
}
```

本节（6.11）是契约的"运行时"部分：契约断言**是什么**（[[basic.contract.general]]）、**如何求值**（[[basic.contract.eval]]）、违反时调用的**处理函数**（[[basic.contract.handler]]）。语法与声明规则在 [[dcl.contract.func]]、[[dcl.contract.res]]、[[stmt.contract.assert]]；库接口在 [[support.contract]]。

!!! warning "编译器支持"
    截至写作时，GCC 与 Clang 都只有实验性的契约实现（开发分支或需要专门开关）；本站验证例子所用的 Homebrew Clang 23 尚不支持 `pre`/`post`/`contract_assert` 语法。所以本页的例子**没有经过编译器验证**，也没有 godbolt 按钮，判定依据完全是标准原文。草案的特性测试宏是 `__cpp_contracts`。

## 为什么需要语言级契约？

`assert` 宏已经存在了几十年，契约要解决它解决不了的问题：

1. **前置/后置条件属于接口**。`pre`/`post` 写在函数声明上，调用者、静态分析器、编译器都能看到；`assert` 只能写在函数体里。
2. **检查策略与代码分离**。`assert` 只有开（`NDEBUG` 未定义）和关两种状态，而且是**按 TU** 决定的，混用会造成 ODR 问题。契约有四种求值语义，由实现（通常是编译选项）选择，标准明确允许同一断言的不同求值采用不同语义（[[basic.contract.eval#2]] 注 1）。
3. **违反后的处理可定制**。可以记录日志后继续（observe）、记录后终止（enforce）、立即终止（quick-enforce），或由用户替换违反处理函数。
4. **与 UB 划清界限**。标准为契约检查规定了**可观察检查点**（[[basic.contract.eval#6]]、[[basic.contract.eval#15]]），保证"违反之后才发生的 UB"不会"时间旅行"到检查之前，把检查本身优化掉。

## 一般规定（basic.contract.general）

[[basic.contract.general#1]] 契约断言由 *precondition-specifier*（`pre`）、*postcondition-specifier*（`post`，[[dcl.contract.func]]）和 *assertion-statement*（`contract_assert`，[[stmt.contract.assert]]）引入。

[[basic.contract.general#2]] 每个契约断言有一个**契约断言谓词**（contract-assertion predicate），是一个 `bool` 类型的表达式（`pre`/`post`/`contract_assert` 括号中的 *conditional-expression* 按语境转换为 `bool`）。谓词的值用来识别**预期的**程序状态。由 [[intro.execution#5]] 第 5.6 项，谓词是一个**完整表达式**——其中的临时对象在谓词求值结束时销毁。

注意语法用的是 *conditional-expression* 而不是 *expression*：谓词中不能直接出现顶层逗号或赋值，`pre (a, b)` 是语法错误，需要写成 `pre ((a, b))`（标准例子中 `pre(( s.g++, false ))` 用了双括号，正是这个原因）。

[[basic.contract.general#3]] `va_start` 宏的调用不得是契约断言谓词的子表达式，不要求诊断 {{ifndr}}。（`va_start` 依赖于它所在函数的栈帧，而谓词可能在调用点或被复制到别处求值。）

[[basic.contract.general#4]] 注 2 总结了谓词中名字的特殊含义：

- 指代**断言之外声明的变量**的 *id-expression* 是 `const` 的（[[expr.prim.id.unqual#7]]）；
- `this` 是指向 const 的指针（[[expr.prim.this]]）；
- 若指定了 *result-name-introducer*，可以命名结果对象（[[dcl.contract.res]]）。

### 隐式 const 化

这是契约设计中最有特色的一条：谓词**不应该**修改程序状态，语言就通过类型系统让"不小心修改"变成编译错误。

```cpp
int n = 0;
struct X { bool m(); bool cm() const; };
struct Y {
  int z = 0;
  void f(int i, int* p, int& r, X x, X* px)
    pre (++n)        // error: n 在谓词中是 const 左值
    pre (++i)        // error: 参数 i 也是 const
    pre (++(*p))     // OK: p 是 int* const，但 *p 是 int
    pre (++r)        // error: 引用所指的对象被视为 const
    pre (x.m())      // error: 对 const 对象调用非 const 成员函数
    pre (x.cm())     // OK
    pre (px->m())    // OK: 只是指针本身 const，指向的对象不是
    pre (++z);       // error: this 是 const Y*
};
```

这些规则只是**浅层** const：通过指针间接修改不受限制（`++(*p)` 合法）。设计者有意不做"深 const"——那需要跨函数的分析，且会破坏太多合理代码。若确实需要在谓词里调用非 const 函数，可以显式 `const_cast`，这样"有副作用"就在源码中清晰可见。

标准例中还有 lambda 的细节：谓词里的 lambda 按值捕获时，捕获的副本是闭包的成员，在 `mutable` lambda 中可以修改（因为它们不是"断言之外声明的变量"）；但在 lambda 体内直接引用外层变量（通过引用捕获或隐式使用）时仍然是 const。

## 四种求值语义（basic.contract.eval ¶1–¶4）

[[basic.contract.eval#1]] 契约断言的每次求值使用四种**求值语义**（evaluation semantic）之一：

| 语义 | 检查谓词？ | 违反时调用处理函数？ | 违反后 | 分类 |
|---|---|---|---|---|
| **ignore** | 否 | — | — | |
| **observe** | 是 | 是 | 处理函数正常返回则**继续执行** | 检查语义 |
| **enforce** | 是 | 是 | 处理函数正常返回则**契约终止** | 检查语义、终止语义 |
| **quick-enforce** | 是 | **否** | 立即契约终止 | 检查语义、终止语义 |

observe、enforce、quick-enforce 是**检查语义**（checking semantics）；enforce 和 quick-enforce 是**终止语义**（terminating semantics）。

[[basic.contract.eval#2]] 对任何一次给定的求值使用哪种语义，**由实现定义** {{impl}}。注 1：实现提供的选择范围和灵活性取决于实现，不必支持全部四种；同一断言的不同求值可以使用不同语义——**包括在常量求值期间**。

这是一个经过深思熟虑的"不规定"：标准不提供在源码中指定语义的语法（例如没有 `pre<enforce>(...)`），把决定权交给构建系统。理由是：同一份库代码，在开发构建、测试构建、生产构建中需要不同的检查策略，这是部署决策而不是编码决策。

[[basic.contract.eval#3]] 建议实践：实现应当提供"所有断言都用 ignore"和"所有断言都用 enforce"的翻译选项；**默认**应使用 enforce。

[[basic.contract.eval#4]] ignore 语义的求值**没有效果**。注 2：谓词是**潜在求值的**（[[basic.def.odr]]），只是不被求值。这意味着：谓词中 odr 使用的函数和变量仍然需要定义，模板仍会被实例化（所谓"needed"，[[dcl.contract.func#9]]），谓词仍需是良构的。这与 `NDEBUG` 下 `assert(expr)` 的宏展开完全消失截然不同——契约在 ignore 下仍然受编译器检查，不会"腐烂"。

```cpp ok
int helper();     // 只声明，未定义
void f(int x) pre (x > helper());
// 即使所有契约都用 ignore 语义，若 f 被 odr 使用，helper 也被 odr 使用，必须有定义
```

## 检查语义下的求值（¶5–¶7）

[[basic.contract.eval#5]] 用检查语义的求值 A **确定**谓词的值。**是否真的求值谓词是未指定的** {{unspec}}。设 B 是"若求值谓词将得到的值"。注 3：为了确定谓词是真还是假，可以进行一次**产生相同值但没有副作用**的替代求值。

```cpp unspecified
struct S { mutable int g = 5; } s;
void f() pre (( s.g++, false ));    // #1
void g() {
  f();   // 即使 #1 使用检查语义，s.g 也不一定自增
}
```

这一规定让编译器可以：把谓词替换为已知结果（若它能证明 B 的值），或在多处求值时合并。结合 [[basic.contract.eval#18]] 允许**重复**求值，可以得出一个重要的编程纪律：

!!! warning "谓词不应有可观察的副作用"
    谓词的副作用可能发生 0 次、1 次或多次。依赖副作用的谓词（计数器、日志、修改缓存）会在不同构建中表现不同。隐式 const 化（[[basic.contract.general#4]]）是对此的第一道防线。

[[basic.contract.eval#6]] 存在一个**可观察检查点**（observable checkpoint，[[intro.abstract#5]]）C，它 happens before A，并且任何其他 happens before A 的求值也 happens before C。

这条与 [[intro.abstract#6]] 的"已定义前缀"配合：UB 只能"抹掉"最近一个可观察检查点之后的行为。因此：

```cpp
void f(int* p) pre (p != nullptr) {
  std::printf("calling f\n");
  *p = 42;      // 若 p 为空，这里是 UB
}
```

若没有检查点，编译器可以推理"既然后面 `*p` 会解引用，p 必定非空，那么 `p != nullptr` 恒真，删掉检查"——这是 UB 的"时间旅行"。¶6 在检查之前放了一个检查点，于是检查之前的一切（包括调用者的输出）都属于已定义前缀，而检查本身必须真的发生（若语义是检查语义）。观察检查点的概念来自 [[P1494]]（部分程序正确性），它同时引入了 `std::observable_checkpoint()`。

[[basic.contract.eval#7]] [[g:contract-violation|**契约违反**]]（contract violation）在以下情况发生：

- ¶7.1 B 为 `false`；
- ¶7.2 谓词的求值以异常退出；
- ¶7.3 谓词在**显然常量求值**（manifestly constant-evaluated，[[expr.const.defns]]）的语境中求值，而谓词不是核心常量表达式。

注 4：若 B 为 `true`，不发生违反，控制流正常继续。谓词求值也可能**既不产生值也不导致违反**——例如调用 `longjmp` 或终止程序。

¶7.3 很有意思：在常量求值中，谓词若调用了非 constexpr 函数，不是"常量表达式求值失败"，而是"契约违反"。这让契约可以在常量求值中被"跳过"——取决于语义（ignore 则无事）。

## 常量求值中的违反（¶8）

[[basic.contract.eval#8]] 若违反发生在显然常量求值的语境中，且求值语义是**终止语义**，程序**非良构**。注 5：若语义是 observe，则产生一个诊断（警告），程序仍是良构的。

```cpp
constexpr int safe_div(int a, int b) pre (b != 0) { return a / b; }
constexpr int k = safe_div(1, 0);
// 若该断言在常量求值中以 enforce 或 quick-enforce 求值：非良构（必须诊断）
// 若以 observe 求值：给出诊断，然后继续——但随后的 1 / 0 不是常量表达式，k 的初始化依然失败
// 若以 ignore 求值：跳过检查，1 / 0 使常量求值失败
```

注 6 指出一个微妙后果：不同 TU 中对同一断言选择不同语义，若断言有改变常量表达式值的副作用，可能导致**违反 ODR**：

```cpp
constexpr int f(int i) {
  contract_assert((++const_cast<int&>(i), true));
  return i;
}
inline void g() {
  int a[f(1)];   // 数组大小取决于 contract_assert 的求值语义：1 或 2
}
```

`g` 是 inline 函数，在两个 TU 中定义；若两个 TU 用不同语义编译，两份定义中 `a` 的类型不同。这是"谓词有副作用"的又一个代价。

## 契约终止（¶9–¶10）

[[basic.contract.eval#9]] 程序被**契约终止**（contract-terminated）时，由实现定义（可依语境而定） {{impl}} 是：

- ¶9.1 调用 `std::terminate`，
- ¶9.2 调用 `std::abort`，或
- ¶9.3 直接终止执行。

注 7：之后不再有执行步骤（[[intro.progress]]）。注 8：不真的调用库函数而执行 `std::terminate` 或 `std::abort` 的动作，也是契约终止的合规实现。

[[basic.contract.eval#10]] 在非常量求值语境中，若发生违反且语义是 **quick-enforce**，程序立即被契约终止——**不调用**违反处理函数。

quick-enforce 的设计目标（注 11）：尽快终止，并把检查对代码体积的影响降到最低。典型实现是一条陷阱指令（`ud2`、`brk`），不需要构造 `contract_violation` 对象、不需要源码位置字符串。这对需要"生产环境也开启检查，但不能忍受膨胀"的场景（安全加固）很重要。

## 调用违反处理函数（¶11–¶17）

[[basic.contract.eval#11]] 在非常量求值语境中，若发生违反且语义是 **enforce 或 observe**，则以一个指向 `const std::contracts::contract_violation` 类型对象 v 的左值调用**契约违反处理函数**。v 的存储以未指定方式分配（不会调用全局分配函数，[[basic.stc.dynamic.allocation#5]] 注 2），其生命周期持续到处理函数调用结束。

[[basic.contract.eval#12]] 若违反是因为谓词求值抛出异常，处理函数**在该异常的一个活跃的隐式处理器之内**被调用（[[except.handle]]）。注 9：所以处理函数中可以用 `std::current_exception()` 查看异常，或用 `throw;` 重新抛出。若处理函数正常返回且语义是 observe，该隐式处理器不再活跃（异常被"吞掉"，执行继续）。

[[basic.contract.eval#13]] 若处理函数正常返回且语义是 **enforce**，程序被契约终止；若违反源于谓词抛出的异常，终止时该隐式处理器仍是活跃的。

[[basic.contract.eval#14]] 注 10：若处理函数正常返回且语义是 **observe**，控制流在断言求值点之后正常继续。

[[basic.contract.eval#15]] 存在一个可观察检查点 C，它 happens after 处理函数正常返回，且任何 happens after 处理函数返回的求值也 happens after C。——这保证处理函数中的输出（日志）属于"已定义前缀"，不会被后续的 UB 抹掉。observe 语义下尤其重要：违反之后继续执行往往会进入 UB，而日志必须已经写出。

[[basic.contract.eval#16]] 注 11 总结三种检查语义的用途：

- **enforce**：终止前给机会记录违反信息，或**抛出异常**以避免终止；
- **quick-enforce**：尽快终止，最小化代码体积影响；
- **observe**：记录信息而不终止——适合在生产环境中**逐步引入**新的契约：先 observe 一段时间，确认没有误报，再切换到 enforce。

### 处理函数抛出异常（¶17）

[[basic.contract.eval#17]] 若由**函数契约断言**（`pre`/`post`）调用的处理函数以异常退出，行为**如同函数体以该异常退出**。注 12：若存在 *function-try-block*，它就是函数体，因而**没有机会**捕获这个异常；若函数有不抛出的异常说明（如 `noexcept`），调用 `std::terminate`。注 13：若由 `contract_assert` 调用的处理函数以异常退出，异常从该语句处继续传播，像普通的 `throw` 一样。

```cpp
void f(int x) noexcept pre (x > 0);
// 若处理函数在 f 的前置条件违反时抛出异常：如同 f 的函数体抛出 → noexcept → std::terminate
```

这一规则引发过大量争论：`noexcept` 函数加上前置条件后，"违反时抛异常"的策略就失效了。当前草案的立场是：`noexcept` 是函数对调用者的承诺，处理函数抛出的异常同样不能越过它。

## 按序求值（¶18–¶19）

[[basic.contract.eval#18]] **按序求值**（evaluate in sequence）一个契约断言列表 R：

1. 构造列表 S：R 的元素都在 S 中；R 的每个元素可以在 S 中重复**实现定义次数**；若 A 在 R 中先于 B，则 A 在 S 中的**首次出现**先于 B 的首次出现。
2. 依次求值 S 的元素，前一个 sequenced before 后一个。

```cpp
void f(int i) {
  contract_assert(i > 0);   // #1
  contract_assert(i < 10);  // #2
  // 合法序列：#1 #2、#1 #1 #2 #2、#1 #2 #1 #2、#1 #2 #2 #1
  // 非法序列：#2 #1（#2 的首次出现先于 #1）
}
```

谁按序求值？函数的所有前置条件（[[expr.call#8]]）、所有后置条件（[[expr.call#10]]），以及连续的 `contract_assert` 语句（[[stmt.contract.assert#3]]）。

为什么允许重复？主要动机是**调用方与被调方都可以检查**：前置条件可能在调用点（调用方 TU 的编译选项）检查一次，又在函数入口（被调方 TU 的编译选项）检查一次，实现不必去重。另外，重复求值是发现"谓词有副作用"这类错误的测试手段——¶19 建议实现提供"重复求值指定次数"的选项，默认不重复。

## 契约违反处理函数（basic.contract.handler）

[[basic.contract.handler#1]] 程序的**契约违反处理函数**是名为 `::handle_contract_violation` 的函数，有单个 `const std::contracts::contract_violation&` 类型的参数，返回 `void`，可以有不抛出的异常说明。实现必须提供一个定义，称为**默认契约违反处理函数**。注 1：任何标准库头文件都不提供默认处理函数的声明。（但可以通过 `std::contracts::invoke_default_contract_violation_handler` 调用它，[[support.contract.invoke]]。）

[[basic.contract.handler#2]] 建议实践：默认处理函数应当输出适当格式化的诊断信息（包含 `contract_violation` 中最相关的内容），对 observe 语义下反复发生的违反进行**限速**，然后正常返回。

[[basic.contract.handler#3]] 处理函数是否**可替换**（replaceable，[[dcl.fct.def.replace]]）由实现定义 {{impl}}。若不可替换，声明一个替换函数是非良构的，不要求诊断 {{ifndr}}。

```cpp
#include <contracts>
#include <cstdio>
#include <exception>

// 替换默认处理函数（仅当实现允许替换时）
void handle_contract_violation(const std::contracts::contract_violation& v) {
  auto loc = v.location();
  std::fprintf(stderr, "%s:%u: %s violated: %s\n",
               loc.file_name(), static_cast<unsigned>(loc.line()),
               v.kind() == std::contracts::assertion_kind::pre  ? "precondition"  :
               v.kind() == std::contracts::assertion_kind::post ? "postcondition" : "assertion",
               v.comment());
  if (v.detection_mode() == std::contracts::detection_mode::evaluation_exception)
    std::fputs("  (predicate threw an exception)\n", stderr);
  // 返回后：observe → 继续执行；enforce → 契约终止
}
```

`contract_violation` 的接口（[[support.contract.violation]]）：

| 成员 | 含义 |
|---|---|
| `comment()` | 实现定义的字符串，建议为谓词的文本（可截断、可为空） |
| `detection_mode()` | `predicate_false` 或 `evaluation_exception` |
| `is_terminating()` | 语义是否为终止语义 |
| `kind()` | `pre`、`post` 或 `assert` |
| `location()` | 实现定义的 `source_location`；建议对前置条件给出**调用点**的位置 |
| `semantic()` | 违反时使用的求值语义（处理函数只在 observe/enforce 下被调用，所以对标准语义而言只会是这两者之一） |

`contract_violation` 不可复制，没有用户可访问的构造函数——只能由实现创建。

## 与其他条款的交互

- **函数调用的顺序**（[[intro.execution#11]]、[[expr.call#8]]）：实参与后缀表达式 → 前置条件 → 函数体 → 后置条件。后置条件在结果对象初始化之后（或与之不定序，若有临时对象）、函数参数销毁之前求值（[[expr.call#10]]）。
- **后置条件中使用参数**（[[dcl.contract.func#7]]）：若 `post` 谓词 odr 使用一个非引用参数，该参数在**所有声明**上都必须是 `const` 的。原因：函数体可能修改参数，后置条件看到的将不再是调用者传入的值。

```cpp
int f(int x) post (r : r > x);         // error: x 不是 const
int g(const int x) post (r : r > x);   // OK
```

- **构造与析构**（[[class.base.init#18]]）：在构造函数的前置条件、析构函数的后置条件中调用成员函数（包括虚函数）、对对象使用 `typeid`/`dynamic_cast`，是 UB——此时对象尚未开始/已经结束生命周期。
- **首次声明**（[[dcl.contract.func#3]]–[[dcl.contract.func#5]]）：函数契约说明符只由**首次声明**引入；后续声明要么省略，要么完全相同（按 ODR 意义比较）。不同 TU 的首次声明不一致是 IFNDR。
- **deleted / defaulted 函数**（[[dcl.contract.func#6]]）：不能有契约说明符。
- **函数指针**（[[dcl.contract.func#8]]）：契约属于函数而非类型；通过指针调用时仍会求值；函数指针类型本身不能带契约。
- **重载决议**不考虑契约说明符（[[dcl.contract.func#9]] 注 6）。

## 历史与演进

!!! history "从 C++20 契约到 C++26 契约"
    - **C++20 契约**：[[P0542R5]] 于 2018 年并入 C++20 工作草案，使用属性语法 `[[expects: x > 0]]`、`[[ensures r: r > 0]]`、`[[assert: ...]]`，有 `default`/`audit`/`axiom` 三个"级别"和"构建级别"、"继续模式"等概念。
    - **2019 年 7 月（科隆会议）**：在关于"假设"语义（违反契约即 UB，允许编译器据此优化）和构建模式等问题的争议无法调和之后，契约被整体移出 C++20。
    - **SG21**：随后成立了契约研究组，从一个"最小可行产品"（MVP）重新开始设计，明确地把"假设"语义排除在外，并逐步确立了 ignore/observe/enforce（以及后来的 quick-enforce）这组求值语义。
    - **C++26**：[[P2900]]（"Contracts for C++"）在 2025 年被采纳进 C++26 工作草案。语法改为上下文关键字 `pre`/`post` 与新关键字 `contract_assert`（而不是 `assert`，以免与 C 的宏冲突）。可观察检查点来自同期的 [[P1494]]。此后草案仍在根据各国家成员体的意见修订契约的措辞（当前草案中 `__cpp_contracts` 的值为 `202606L`）。

## 陷阱

!!! pitfall "契约不是用来做输入验证的"
    契约检查可能被 ignore。不可信输入（用户输入、网络数据）的验证必须写成普通代码；契约表达的是"程序正确时这里一定成立"，违反即意味着**程序有 bug**。

!!! pitfall "谓词的副作用可能执行 0 次或多次"
    ¶5 允许不求值（只要能确定值），¶18 允许重复求值。`pre (log_call())` 这样的写法在不同构建下行为不同。

!!! pitfall "后置条件不检查异常退出"
    [[dcl.contract.func#1]] 注 1：后置条件只与**正常返回**关联。函数抛出异常或 `longjmp` 离开时，`post` 不会被求值。

!!! pitfall "observe 之后继续执行，可能直接进入 UB"
    observe 语义下违反后程序继续运行，而违反的前置条件往往正是为了防止随后的 UB。¶15 的检查点保证日志已经输出，但不保证之后不崩溃。

## 思考题

!!! question "1. 下面的前置条件中，哪些是非良构的？"
    ```cpp
    int g;
    struct S {
      int m;
      void f(int a, int& b, int* c) const
        pre (a++ > 0)
        pre (b = 1)
        pre (*c = 1)
        pre (m > 0)
        pre ((g = 1, true));
    };
    ```

<details markdown="1">
<summary>答案</summary>

- `pre (a++ > 0)`：非良构，`a` 在谓词中是 const。
- `pre (b = 1)`：首先是语法问题——谓词是 *conditional-expression*，不能直接是赋值表达式；即使加了括号写成 `pre ((b = 1))`，`b` 被视为 const 左值，也是非良构。
- `pre (*c = 1)`：同样是语法问题（赋值不是 *conditional-expression*）；写成 `pre ((*c = 1))` 则良构——`c` 是 `int* const`，`*c` 是可修改的 `int`。（当然这是糟糕的写法。）
- `pre (m > 0)`：良构，只读。
- `pre ((g = 1, true))`：非良构，`g` 在谓词中是 const。
</details>

!!! question "2. 若断言使用 observe 语义，谓词抛出了异常，处理函数正常返回。异常去哪了？"

<details markdown="1">
<summary>答案</summary>

被吞掉了。¶12：处理函数在该异常的活跃隐式处理器中被调用；observe 下处理函数正常返回后，该隐式处理器不再活跃——相当于一个 `catch (...) {}` 结束。控制流在断言之后正常继续（¶14）。若想让异常继续传播，处理函数应在内部 `throw;` 重新抛出；对 `pre`/`post`，这会如同函数体抛出该异常（¶17）。
</details>

!!! question "3. 为什么 ignore 语义下谓词仍然是“潜在求值”的？这有什么代价和好处？"

<details markdown="1">
<summary>答案</summary>

好处：谓词在任何构建中都要通过编译——名字查找、类型检查、模板实例化都照常进行，不会出现 `NDEBUG` 下断言表达式"腐烂"（引用了已经不存在的变量也没人发现）的问题；同一份代码在不同语义下的 ODR 行为也更一致。代价：谓词 odr 使用的函数、变量必须有定义，可能引入链接依赖；谓词中的模板会被实例化，增加编译时间。
</details>

## 小结

| 概念 | 要点 | 段落 |
|---|---|---|
| 三种断言 | `pre`、`post`、`contract_assert`；谓词是 bool 的完整表达式 | general ¶1–¶2 |
| 隐式 const | 谓词中外部变量、参数、`*this` 都是 const（浅层） | general ¶4 |
| 四种语义 | ignore / observe / enforce / quick-enforce，由实现选择，可以每次不同 | eval ¶1–¶2 |
| ignore | 不求值，但潜在求值 | eval ¶4 |
| 检查语义 | 可能不真的求值；之前有可观察检查点 | eval ¶5–¶6 |
| 违反 | 谓词为假 / 抛异常 / 常量求值中非常量表达式 | eval ¶7 |
| 常量求值中违反 | 终止语义 → 非良构；observe → 诊断 | eval ¶8 |
| 违反后 | quick-enforce 直接终止；enforce/observe 调用处理函数，返回后分别终止/继续 | eval ¶10–¶14 |
| 处理函数抛异常 | 函数契约：如同函数体抛出；`contract_assert`：从语句处传播 | eval ¶17 |
| 按序求值 | 可重复，但首次出现保持顺序 | eval ¶18 |
| 处理函数 | `::handle_contract_violation`，是否可替换由实现定义 | handler ¶1–¶3 |
