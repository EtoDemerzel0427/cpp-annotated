---
title: 契约断言
summary: C++26 契约在运行时的含义：pre、post、contract_assert 的谓词，四种求值语义（ignore、observe、enforce、quick-enforce），契约违反以及违反处理函数。
status: draft
covers: *
since: c++26
papers: P2900, P1494, P0542R5
related: dcl.contract.func, dcl.contract.res, stmt.contract.assert, support.contract, intro.execution, intro.abstract, expr.prim.id.unqual
tags: 契约, C++26, 求值语义
updated: 2026-10-19
---

!!! tldr
    - 契约断言有三种：函数声明上的 `pre`、`post`，以及语句 `contract_assert`。谓词里引用的外部变量、参数和 `*this` 都被视为 const，无意的修改会编译失败。
    - 每次求值一个断言都采用四种语义之一：ignore 不检查；observe 检查并在违反时调用处理函数，然后继续；enforce 调用处理函数后终止；quick-enforce 直接终止。用哪种由实现决定，通常由编译选项控制。
    - 即使是 ignore，谓词也要能编译、它用到的函数也要有定义；这和 `NDEBUG` 下整个消失的 `assert` 不同。
    - 谓词可能被求值 0 次、1 次或多次，所以谓词不应有副作用。
    - 检查前后各有一个可观察检查点：之后的 UB 不能抹掉检查之前的输出，也不能让编译器删掉检查本身。

## 一个例子

```cpp
int isqrt(const int x)
  pre (x >= 0)                                      // 前置条件：进入函数时
  post (r : r * r <= x && (r + 1) * (r + 1) > x)    // 后置条件：正常返回时
{
  int r = 0;
  while ((r + 1) * (r + 1) <= x) ++r;
  contract_assert (r >= 0);                         // 断言语句：执行到这里时
  return r;
}
```

{{c++26}} [[g:contract-assertion|**契约断言**]]（contract assertion）把此处程序状态应当满足的性质写成语言的一部分，而不是注释或宏。上例展示了全部三种：**前置条件断言**（`pre`）、**后置条件断言**（`post`，`r` 命名返回值）和**断言语句**（`contract_assert`）。

本节讲契约在运行时的含义。语法和声明规则在 [[dcl.contract.func]]、[[dcl.contract.res]]、[[stmt.contract.assert]]，库接口在 [[support.contract]]。

!!! warning "编译器支持"
    截至写作时，本机 Clang 23 还不支持 `pre`、`post`、`contract_assert` 语法，GCC 的开发分支有一个实验性实现（本机没有 GCC，未验证）。所以本页的例子都没有经过编译验证，也不带判定标记，结论完全依据标准原文。特性测试宏是 `__cpp_contracts`。

### 和 assert 有什么不同

`assert` 宏已经用了几十年。契约解决的是它解决不了的几个问题：

1. 前置条件和后置条件属于接口。`pre`、`post` 写在函数声明上，调用者、静态分析器和编译器都看得到；`assert` 只能写在函数体里。
2. 检查策略和代码分开。`assert` 只有开（没定义 `NDEBUG`）和关两种状态，按翻译单元决定，混用还会造成 ODR 问题。契约有四种求值语义，由实现选择，同一个断言的不同求值可以用不同语义。
3. 违反之后怎么办可以选择：记录后继续、记录后终止、立即终止，处理函数还可以由用户替换。
4. 和 UB 划清界限。检查前后都有可观察检查点（见下文 ¶6、¶15），编译器不能借后面的 UB 把检查优化掉。

## 谓词 [basic.contract.general]

¶1–¶2 每个契约断言有一个**契约断言谓词**（contract-assertion predicate），即括号里的条件按语境转换成的 `bool` 表达式，它的值用来识别预期的程序状态。谓词是一个完整表达式（[[intro.execution#5]]），其中的临时对象在谓词求值结束时销毁。

谓词的语法是 *conditional-expression* 而不是 *expression*，所以顶层不能出现逗号或赋值：`pre (a, b)` 是语法错误，要写成 `pre ((a, b))`。

¶3 `va_start` 宏的调用不能出现在谓词里，违反时不要求诊断 {{ifndr}}。`va_start` 依赖所在函数的栈帧，而谓词可能在调用点求值。

### 谓词里的变量是 const（¶4）

谓词不应该修改程序状态，语言借助类型系统让无意的修改变成编译错误。¶4 的注 2 总结了这条规则，规范性的条文在 [[expr.prim.id.unqual#7]] 和 [[expr.prim.this]]：

```cpp
int n = 0;
struct X { bool m(); bool cm() const; };
struct Y {
  int z = 0;
  void f(int i, int* p, int& r, X x, X* px)
    pre (++n)        // error: n 在谓词中是 const 左值
    pre (++i)        // error: 形参 i 也是 const
    pre (++(*p))     // OK：p 是 int* const，*p 是 int
    pre (++r)        // error: 引用所指的对象视为 const
    pre (x.m())      // error: 对 const 对象调用非 const 成员函数
    pre (x.cm())     // OK
    pre (px->m())    // OK：只有指针本身是 const
    pre (++z);       // error: this 是 const Y*
};
```

具体地说，在谓词中命名一个在断言外声明的变量（对象或引用）时，表达式的类型加上 const；`this` 是指向 const 的指针。后置条件里的返回值名字同样是 const（[[dcl.contract.res]]）。

这只是浅层的 const，通过指针间接修改不受限制，`++(*p)` 合法。设计上有意不做深层 const，因为那需要跨函数分析，也会拒绝太多合理的代码。确实需要在谓词里调用非 const 函数时，可以显式写 `const_cast`，让副作用在源码里一目了然。

谓词里的 lambda 有一个细节。按值捕获得到的副本是闭包的成员，不是断言外声明的变量，所以在 `mutable` lambda 里可以修改；但在 lambda 体内直接命名外层变量（例如按引用捕获的变量）时，它仍然是 const。

## 四种求值语义 [basic.contract.eval]

### 语义由实现选择（¶1–¶3）

¶1 契约断言的每次求值采用四种**求值语义**（evaluation semantic）之一：

| 语义 | 检查谓词 | 违反时调用处理函数 | 违反之后 |
|---|---|---|---|
| ignore | 否 | | |
| observe | 是 | 是 | 处理函数正常返回则继续执行 |
| enforce | 是 | 是 | 处理函数正常返回则终止程序 |
| quick-enforce | 是 | 否 | 立即终止程序 |

observe、enforce、quick-enforce 是**检查型语义**（checking semantics）；enforce 和 quick-enforce 是**终止型语义**（terminating semantics）。

¶2 每次求值采用哪种语义由实现定义 {{impl}}。注 1 补充，实现不必支持全部四种；同一个断言的不同求值可以用不同的语义，常量求值中也是如此。

标准有意不提供在源码里指定语义的语法（没有 `pre<enforce>(...)` 这种写法），而把选择交给构建系统。同一份库代码在开发、测试和生产构建中需要不同的检查策略，这是部署决策，不是编码决策。

¶3 标准建议实现提供两个选项：让所有断言都用 ignore，以及让所有断言都用 enforce；默认应当用 enforce。

### ignore：不求值，但要能编译（¶4）

¶4 以 ignore 语义求值契约断言没有任何效果。注 2 补充，谓词仍然是**潜在求值的**（potentially evaluated，[[basic.def.odr]]），只是没有被求值。

```cpp
int helper();                        // 只有声明
void f(int x) pre (x > helper());
// 只要 f 被 odr 使用，helper 就被 odr 使用，必须有定义，
// 即使所有断言都用 ignore 语义
```

所以谓词中用到的函数和变量仍然需要定义，模板仍然会被实例化（[[dcl.contract.func#9]]），谓词也必须良构。这和 `NDEBUG` 下 `assert(expr)` 整个消失不同：契约在任何构建中都要经过编译器检查，不会因为长期不编译而悄悄失效。

### 检查型语义：值可以推出来（¶5）

¶5 以检查型语义进行的求值 A 要确定谓词的值，但是否真的求值谓词是未指定的 {{unspec}}。设 B 是求值谓词将得到的值。注 3 说明，实现可以改用一个结果相同、但没有副作用的求值来确定 B。

```cpp
struct S { mutable int g = 5; } s;
void f() pre (( s.g++, false ));    // #1
void g() {
  f();   // 即使 #1 采用检查型语义，s.g 也不一定自增
}
```

编译器如果能推出 B，就可以直接用结果代替谓词，也可以合并多次求值。再加上下文 ¶18 允许重复求值，就得到一条编程纪律：

!!! warning "谓词不应有可观察的副作用"
    谓词的副作用可能发生 0 次、1 次或多次。依赖副作用的谓词（计数、记日志、更新缓存）在不同构建下表现不同。谓词中的变量是 const，是防止这类错误的第一道防线。

### 检查之前的可观察检查点（¶6）

¶6 每次检查型求值 A 之前都有一个**可观察检查点**（observable checkpoint）C：所有先于 A 发生的求值，也都先于 C 发生。可观察检查点的含义见 [[intro.abstract#5]]：未定义行为只能影响最后一个检查点之后的可观察行为，之前的必须如实产生。

```cpp
void f(int* p) pre (p != nullptr) {
  std::printf("calling f\n");
  *p = 42;      // p 为空时这里是 UB
}
```

没有检查点时，编译器可以这样推理：后面会解引用 `*p`，所以 `p` 一定不为空，`p != nullptr` 恒为真，检查可以删掉。这是 UB 影响它之前代码的典型情形。¶6 在检查之前放了一个检查点，检查之前的一切都受保护；只要语义是检查型的，检查本身也必须真的发生。可观察检查点这个概念来自 [[P1494]]，它同时引入了 `std::observable_checkpoint()`。

### 什么算违反（¶7）

¶7 下列情形发生[[g:contract-violation|**契约违反**]]（contract violation）：

- ¶7.1 B 为 `false`；
- ¶7.2 谓词的求值以异常退出；
- ¶7.3 谓词在**显然常量求值**（manifestly constant-evaluated，[[expr.const.defns]]）的语境中求值，而它不是核心常量表达式，比如调用了非 constexpr 函数。

注 4 说明，B 为 `true` 时不发生违反，控制流在断言之后正常继续。谓词的求值也可能既不产生值、也不构成违反，比如调用了 `longjmp` 或者终止了程序。

### 常量求值中的违反（¶8）

¶8 违反发生在显然常量求值的语境中、而语义是终止型的，程序非良构。注 5 说明，语义是 observe 时会产生一条诊断，程序仍然良构（参见 [[intro.compliance]]）。

```cpp
constexpr int safe_div(int a, int b) pre (b != 0) { return a / b; }
constexpr int k = safe_div(1, 0);
// enforce 或 quick-enforce：非良构
// observe：给出诊断后继续，但随后的 1 / 0 不是常量表达式，k 的初始化仍然失败
// ignore：跳过检查，1 / 0 使常量求值失败
```

注 6 指出一个不易察觉的后果。如果不同翻译单元对同一个断言选了不同的语义，而断言的副作用会改变常量表达式的值，就可能违反 ODR：

```cpp
constexpr int f(int i) {
  contract_assert((++const_cast<int&>(i), true));
  return i;
}
inline void g() {
  int a[f(1)];   // 数组大小是 1 还是 2，取决于 contract_assert 的求值语义
}
```

`g` 是 inline 函数，可以在多个翻译单元里定义。如果这些翻译单元用不同的语义编译，各处定义中 `a` 的类型就不同。这是谓词带副作用的又一个代价。

## 违反之后 [basic.contract.eval]

### 契约终止与 quick-enforce（¶9–¶10）

¶9 程序被**契约终止**（contract-terminated）时，具体是调用 `std::terminate`、调用 `std::abort`，还是直接结束执行，由实现定义，可以视语境而定 {{impl}}。注 7 说明此后不再有执行步骤（[[intro.progress]]）；注 8 说明，不真正调用库函数、直接执行 `terminate` 或 `abort` 的动作，也符合要求。

¶10 在非常量求值语境中，违反发生而语义是 quick-enforce 时，程序立即被契约终止，不调用违反处理函数。

quick-enforce 的目标是尽快终止，并把检查对代码体积的影响降到最小（注 11）。典型的实现是一条陷阱指令（x86 的 `ud2`、AArch64 的 `brk`），既不需要构造 `contract_violation` 对象，也不需要保存源码位置字符串。安全加固之类要求生产环境也开启检查、又不能接受代码膨胀的场景，正适合用它。

### 调用违反处理函数（¶11–¶16）

¶11 在非常量求值语境中，违反发生而语义是 enforce 或 observe 时，以一个指代 `const std::contracts::contract_violation` 对象 v 的左值调用**契约违反处理函数**（见下文 [basic.contract.handler]），v 里包含这次违反的信息。v 的存储以未指定的方式分配，不经过全局的 `operator new`（[[basic.stc.dynamic.allocation]]），生命周期持续到处理函数调用结束。

¶12 如果违反是谓词抛出异常引起的，处理函数在这个异常的一个活跃的隐式处理器（handler）中调用（[[except.handle]]）。注 9 指出，处理函数里因此可以查看或者重新抛出这个异常。处理函数正常返回、而语义是 observe 时，那个隐式处理器就不再活跃，相当于异常被捕获并吞掉了。

¶13 处理函数正常返回、而语义是 enforce 时，程序被契约终止。如果违反源于谓词抛出的异常，终止时那个隐式处理器仍然活跃。

¶14 注 10 说明，处理函数正常返回、而语义是 observe 时，控制流在断言之后正常继续。

¶15 处理函数正常返回之后也有一个可观察检查点：所有在返回之后发生的求值，都在这个检查点之后。这保证处理函数写出的日志属于受保护的部分，不会被之后的 UB 抹掉。这在 observe 下尤其重要，因为违反之后继续执行，往往很快就会进入 UB。

¶16 注 11 总结了三种检查型语义的用途：enforce 让程序在终止前有机会记录违反的信息，或者抛出异常来避免终止；quick-enforce 尽快终止并尽量不增加代码体积；observe 记录信息但不终止，适合在生产环境中逐步引入新的契约，先用 observe 运行一段时间确认没有误报，再切换到 enforce。

### 处理函数抛出异常（¶17）

¶17 由函数契约断言（`pre`、`post`）调用的处理函数以异常退出时，效果如同函数体以这个异常退出。

```cpp
void f(int x) noexcept pre (x > 0);
// 前置条件违反、处理函数抛出异常时：如同 f 的函数体抛出，而 f 是 noexcept，于是调用 std::terminate
```

注 12 补充了两个推论。*function-try-block* 本身就是函数体，所以它捕获不到这个异常。函数带不抛出的异常说明时，调用 `std::terminate`，`noexcept` 是函数对调用者的承诺，处理函数抛出的异常同样不能越过它。所以给 `noexcept` 函数加前置条件，就不能靠处理函数抛异常来恢复。

注 13 说明，由 `contract_assert` 调用的处理函数以异常退出时，异常从这条语句处继续传播，和普通的 `throw` 一样。

## 按序求值与重复求值（¶18–¶19）

¶18 **按序求值**（evaluate in sequence）一列契约断言 R，是指先构造一个列表 S：R 的每个元素都在 S 中，每个元素可以重复出现实现定义的次数，并且在 R 中靠前的断言在 S 中首次出现也靠前；然后依次求值 S 的元素，前一个先于（sequenced before）后一个。

```cpp
void f(int i) {
  contract_assert(i > 0);   // #1
  contract_assert(i < 10);  // #2
  // 合法的求值序列：#1 #2、#1 #1 #2 #2、#1 #2 #1 #2、#1 #2 #2 #1
  // 不合法：#2 #1（#2 的首次出现早于 #1）
}
```

函数的全部前置条件（[[expr.call#8]]）、全部后置条件（[[expr.call#10]]）以及连续的 `contract_assert` 语句（[[stmt.contract.assert#3]]）都按序求值。

允许重复，主要是为了让调用方和被调方都能检查：前置条件可以在调用点按调用方翻译单元的选项检查一次，又在函数入口按被调方翻译单元的选项再检查一次，实现不必去重。重复求值也是发现谓词带副作用的测试手段。¶19 建议实现提供让每个断言重复求值指定次数的选项，默认不重复。

## 契约违反处理函数 [basic.contract.handler]

¶1 程序的**契约违反处理函数**（contract-violation handler）是名为 `::handle_contract_violation` 的函数，有一个 `const std::contracts::contract_violation&` 类型的形参，返回 `void`，可以带不抛出的异常说明。实现必须提供一个定义，叫做**默认契约违反处理函数**。注 1 说明，没有任何标准库头文件声明默认处理函数；要显式调用它，用 `std::contracts::invoke_default_contract_violation_handler`（[[support.contract]]）。

¶2 标准建议默认处理函数输出格式适当的诊断信息，包含 `contract_violation` 中最相关的内容；对 observe 语义下反复发生的违反限制输出频率；然后正常返回。

¶3 处理函数是否**可替换**（replaceable，[[dcl.fct.def.replace]]）由实现定义 {{impl}}。实现不允许替换时，程序声明替换函数是非良构的，不要求诊断 {{ifndr}}。允许替换时，可以这样写：

```cpp
#include <contracts>
#include <cstdio>

void handle_contract_violation(const std::contracts::contract_violation& v) {
  using namespace std::contracts;
  auto loc = v.location();
  const char* what = v.kind() == assertion_kind::pre  ? "precondition"
                   : v.kind() == assertion_kind::post ? "postcondition"
                                                      : "assertion";
  std::fprintf(stderr, "%s:%u: %s violated: %s\n", loc.file_name(),
               static_cast<unsigned>(loc.line()), what, v.comment());
  if (v.detection_mode() == detection_mode::evaluation_exception)
    std::fputs("  (predicate threw an exception)\n", stderr);
  // 返回之后：observe 继续执行，enforce 终止程序
}
```

`contract_violation` 的接口如下（[[support.contract.violation]]）：

| 成员 | 含义 |
|---|---|
| `comment()` | 实现定义的字符串，建议是谓词的文本，可以截断，也可以为空 |
| `detection_mode()` | `predicate_false` 或 `evaluation_exception` |
| `is_terminating()` | 语义是否为终止型 |
| `kind()` | `pre`、`post` 或 `assert` |
| `location()` | 实现定义的 `source_location`；对前置条件，建议给出调用点的位置 |
| `semantic()` | 这次求值采用的语义；处理函数只在 observe 和 enforce 下调用，所以标准语义下只会是这两者之一 |

`contract_violation` 没有用户可以访问的构造函数，只能由实现创建。

## 与其他条款的联系

- 函数调用的顺序（[[expr.call#8]]、[[expr.call#10]]）：先初始化形参，然后求值前置条件、执行函数体；函数正常返回时求值后置条件，这发生在形参销毁之前。
- 后置条件使用形参（[[dcl.contract.func#7]]）：`post` 的谓词 odr 使用一个非引用形参时，这个形参在所有声明上都必须是 const 的。函数体可能修改形参，不加这条限制，后置条件看到的就不是调用者传入的值。

    ```cpp
    int f(int x) post (r : r > x);         // error: x 不是 const
    int g(const int x) post (r : r > x);   // OK
    ```

- 构造和析构（[[class.base.init#18]]）：在构造函数的前置条件或析构函数的后置条件里调用成员函数，是 UB，因为对象的生命周期这时还没开始或已经结束。
- 重复声明（[[dcl.contract.func#4]]、[[dcl.contract.func#5]]）：函数的契约只由首次声明引入，后续声明要么省略，要么写得完全相同。不同翻译单元中的首次声明不一致时，不要求诊断。
- deleted 函数、在首次声明上 defaulted 的函数不能带契约（[[dcl.contract.func#6]]）。
- 函数指针（[[dcl.contract.func#8]]）：契约属于函数而不属于类型；通过指针调用时仍然求值，函数指针类型本身不能带契约。
- 重载决议不考虑契约（[[dcl.contract.func#9]] 注 6）。

## 历史与演进

!!! history "从 C++20 契约到 C++26 契约"
    - [[P0542R5]] 曾把契约并入 C++20 的工作草案，用属性语法 `[[expects: x > 0]]`、`[[ensures r: r > 0]]`、`[[assert: ...]]`，并有 `default`、`audit`、`axiom` 三个检查级别。争议集中在假设语义（违反契约即 UB，允许编译器据此优化）和构建模式的设计上，契约最终在 C++20 发布前被整体移除。
    - 之后的重新设计从一个最小可行版本出发，明确排除了假设语义，逐步确立了 ignore、observe、enforce 和后来加入的 quick-enforce 这组求值语义。
    - C++26 通过 [[P2900]] 引入了现在的契约。语法改为上下文关键字 `pre`、`post` 和新关键字 `contract_assert`（不用 `assert`，以免和 C 的宏冲突）；可观察检查点来自 [[P1494]]。

## 常见误解

!!! pitfall "契约可以用来验证输入"
    契约检查可能被 ignore。来自用户或网络的不可信输入必须用普通代码验证。契约表达的是程序正确时这里一定成立的性质，违反就意味着程序有 bug。

!!! pitfall "谓词的副作用一定执行一次"
    ¶5 允许不求值（只要能确定值），¶18 允许重复求值。`pre (log_call())` 这样的写法在不同构建下行为不同。

!!! pitfall "抛出异常时也会检查后置条件"
    后置条件只和正常返回关联（[[dcl.contract.func#1]] 注 1）。函数因抛出异常或 `longjmp` 离开时，`post` 不会被求值。

!!! pitfall "observe 下违反之后程序是安全的"
    observe 下违反之后程序继续运行，而被违反的前置条件往往正是为了防止随后的 UB。¶15 的检查点只保证日志已经写出，不保证之后不会崩溃。

## 思考题

!!! question "思考题 1"
    下面的前置条件中，哪些是非良构的？
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
- `pre (b = 1)`：首先是语法错误，谓词必须是 *conditional-expression*，不能直接是赋值表达式。写成 `pre ((b = 1))` 也不行，`b` 所指的对象视为 const。
- `pre (*c = 1)`：同样是语法错误。写成 `pre ((*c = 1))` 就良构了，因为 `c` 是 `int* const`，`*c` 是可修改的 `int`，不过这是很糟糕的写法。
- `pre (m > 0)`：良构，只读。
- `pre ((g = 1, true))`：非良构，`g` 在谓词中是 const。
</details>

!!! question "思考题 2"
    一个断言以 observe 语义求值，谓词抛出了异常，处理函数正常返回。这个异常去了哪里？

<details markdown="1">
<summary>答案</summary>

被吞掉了。按 ¶12，处理函数在这个异常的活跃隐式处理器中调用；observe 下处理函数正常返回后，隐式处理器不再活跃，效果相当于一个 `catch (...) {}` 执行完毕，控制流在断言之后继续（¶14）。想让异常继续传播，处理函数可以在内部用 `throw;` 重新抛出；对 `pre`、`post` 来说，这如同函数体抛出了这个异常（¶17）。
</details>

!!! question "思考题 3"
    为什么 ignore 语义下谓词仍然是潜在求值的？这有什么代价和好处？

<details markdown="1">
<summary>答案</summary>

好处是谓词在任何构建中都要通过编译，名字查找、类型检查、模板实例化都照常进行。`NDEBUG` 下的断言表达式可能悄悄失效，比如引用了已经被删掉的变量也没人发现，契约没有这个问题。代价是谓词 odr 使用的函数和变量必须有定义，可能多出链接依赖；谓词中的模板会被实例化，增加编译时间。
</details>

## 小结

| 概念 | 要点 | 出处 |
|---|---|---|
| 三种断言 | `pre`、`post`、`contract_assert`；谓词是 `bool` 类型的完整表达式 | [[basic.contract.general#1]]、[[basic.contract.general#2]] |
| 谓词中的 const | 外部变量、形参、`*this` 都是 const（浅层） | [[basic.contract.general#4]] |
| 四种语义 | ignore、observe、enforce、quick-enforce，由实现选择，每次可以不同 | [[basic.contract.eval#1]]、[[basic.contract.eval#2]] |
| ignore | 不求值，但谓词潜在求值 | [[basic.contract.eval#4]] |
| 检查型语义 | 可以不真的求值；检查之前有可观察检查点 | [[basic.contract.eval#5]]、[[basic.contract.eval#6]] |
| 违反 | 谓词为假、抛出异常、常量求值中不是常量表达式 | [[basic.contract.eval#7]] |
| 常量求值中违反 | 终止型语义下非良构；observe 下给出诊断 | [[basic.contract.eval#8]] |
| 违反之后 | quick-enforce 直接终止；enforce、observe 调用处理函数，返回后分别终止、继续 | [[basic.contract.eval#10]]–[[basic.contract.eval#14]] |
| 处理函数抛异常 | `pre`、`post`：如同函数体抛出；`contract_assert`：从语句处传播 | [[basic.contract.eval#17]] |
| 按序求值 | 可以重复，但首次出现的顺序不变 | [[basic.contract.eval#18]] |
| 处理函数 | `::handle_contract_violation`，是否可替换由实现定义 | [[basic.contract.handler]] |
