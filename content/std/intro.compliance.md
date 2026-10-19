---
title: 实现的符合性与抽象机
summary: 编译器对一个程序必须做什么：哪些错误必须报告、哪些可以不管；编译出的程序要表现得像什么（抽象机、可观察行为、as-if 规则）；未定义行为为什么能影响它之前的代码，C++26 又怎样给它划了边界。
status: done
covers: intro.compliance.general, intro.abstract
related: intro.defs, basic.contract.eval, intro.execution, compliance, topics/how-to-read-the-standard
tags: 符合性, as-if, UB, 可观察行为, 抽象机, contracts
updated: 2026-10-18
---

!!! tldr
    - 程序违反一条普通规则时，编译器只需给出一条诊断，警告也算。必须拒绝编译的只有 `#error`、失败的 `static_assert`，以及常量求值中被终止的契约检查。
    - 有些规则标注了不要求诊断（例如跨翻译单元的 ODR）。违反它们的程序可能毫无提示地编译通过，运行结果没有任何保证。
    - 编译出的程序只需在可观察行为上与抽象机一致：volatile 访问、写进文件的数据、交互设备上的提示顺序。其余部分优化器都可以改写，这就是 as-if 规则。
    - 优化器可以假设未定义行为不会发生。C++26 起，UB 之前、被可观察检查点保护的输出必须如实产生。
    - `-std=gnu++2c` 这类默认模式通常不是符合标准的模式。扩展不能改变合法程序的含义。

## 编译器只给了一个警告，这符合标准吗 [intro.compliance.general]

```cpp run error
void f(int n) {
  int a[n];      // error: C++ 没有变长数组（VLA）
  (void)a;
}
int main() { f(3); }
```

C++ 的数组长度必须是常量表达式，所以这段代码不合法。但本机 Clang 23 只给出一条警告（`-Wvla-cxx-extension`），然后照常生成了可执行文件。这完全符合标准。要说明为什么，先要有几个词。

标准规定的是对**实现**（implementation）的要求。实现指编译器、标准库和运行环境的整体，见 [[intro.scope]]。按全部语法和语义规则写成的程序是**良构**（well-formed）的，否则就是**非良构**（ill-formed）的（[[defns.well.formed]]、[[defns.ill.formed]]）。**诊断信息**（diagnostic message）是实现输出的一类消息，具体形式由实现决定，错误和警告都算（[[defns.diagnostic]]）。

### 默认每条规则都要诊断（¶1）

¶1 标准把除去两类之外的全部语法和语义规则称为**可诊断规则**（diagnosable rules）。被除去的两类是：明确注明 "no diagnostic is required" 的规则，以及说明会导致未定义行为的规则。

所以标准不必在每条规则后面写上"违反者须诊断"。读到一条 shall 规则，比如 "*X* shall not be a reference type"，只要附近没有 no diagnostic is required，违反它的程序就是非良构的，而且编译器必须报告。

### 一个程序有三种结局（¶2）

¶2 标准经常把要求写成对程序的要求，例如"程序应当只有一个 `main`"，因为这样更好懂。¶2 规定了这种写法实际的意思，也就是它对实现提出了什么要求：

| 程序的情况 | 实现必须做什么 |
|---|---|
| ¶2.1 没有违反第 5–33 章和 Annex D 的任何规则 | 接受并正确执行，除非超出了实现的容量限制 |
| ¶2.2 违反了一条不要求诊断的规则 | 没有任何要求 |
| ¶2.3 否则，违反了一条可诊断规则（还有下面几种情形） | 至少发出一条诊断信息 |

¶2.3 除了违反可诊断规则，还列了三种必须诊断的情形：源文件里有 `#warning` 指令；用了标为有条件支持（conditionally-supported）而本实现不支持的构造；以及 C++26 契约在常量求值中的一种违反（见下文）。

正确执行并不意味着不会出错。脚注 3 说明，良构程序在某些输入下仍然可能出现未定义行为，比如用户输入的除数是 0。良构是程序的静态属性，与运行时数据无关。

!!! note "模板实参推导中的错误"
    ¶2 的注 1 提醒，在模板实参推导和替换期间，某些原本需要诊断的错误会得到不同的处理（[[temp.deduct]]）。这就是 SFINAE：替换失败只是把这个候选函数丢掉，不会报错。

### 诊断不等于拒绝（¶2.4–¶2.6）

回到开头的问题。对违反可诊断规则的程序，标准只要求至少一条诊断，没有要求拒绝编译。后文讲扩展时会看到，标准还明确允许实现诊断之后继续编译这样的程序。Clang 对 VLA 给一条警告然后生成可执行文件，两条义务都满足了。

标准要求必须拒绝的只有三种情形，它们都是程序员主动要求编译失败的手段：

- ¶2.4 含有 `#error` 指令；
- ¶2.5 有一条失败的 `static_assert`（[[dcl.pre]]）；
- ¶2.6 {{c++26}} 常量求值中以终止型语义检查的契约断言被违反（见下文）。

<div class="compare" markdown="1">

```cpp run ok
#warning "此头文件已弃用"
// 必须诊断（¶2.3.2），
// 但程序是良构的，可以接受
int main() {}
```

```cpp run error
static_assert(sizeof(int) == 2,
              "需要 16 位 int");
// 不得接受（¶2.5）
int main() {}
```

</div>

所以能编译通过从来不能证明代码合法。如果希望所有可诊断的违规都导致编译失败，Clang 和 GCC 用 `-pedantic-errors`，MSVC 用 `/permissive-`。

!!! note "模板里的 `static_assert(false)`"
    一条 `static_assert` 在模板定义中求值时不算失败，只有实例化时求值为 `false` 才算失败（[[dcl.pre#13]]）。[[temp.res.general#6]] 在判断模板能否生成有效特化时也忽略失败的 `static_assert`。C++23 的 [[P2593]] 引入了这两点，于是可以在不该被实例化的模板里直接写 `static_assert(false, ...)`：

    ```cpp run ok
    template<class T>
    void f() {
      static_assert(false, "f 不应被实例化");   // OK：f 从未被实例化
    }
    int main() {}
    ```

### 不要求诊断的规则（IFNDR）

有些规则编译器很难甚至不可能检查。最典型的是 ODR：同一个 inline 函数在每个翻译单元（单独编译的一个源文件，连同它包含的头文件）里的定义必须完全相同。编译器一次只看一个翻译单元，看不到冲突。

```cpp title="a.cpp"
inline int answer() { return 42; }
int from_a() { return answer(); }
```

```cpp title="b.cpp" ifndr
#include <cstdio>
inline int answer() { return 0; }   // 与 a.cpp 中的定义不同：违反 ODR
int from_a();
int main() { std::printf("%d %d\n", from_a(), answer()); }
```

本机 Clang 23 编译和链接都没有任何提示。`-O0` 下输出 `42 42`，`-O2` 下输出 `42 0`，把两个文件在命令行上调换顺序后 `-O0` 输出 `0 0`。

这类规则在条文里注明 no diagnostic is required，违反它们的程序叫做**非良构、不要求诊断**（ill-formed, no diagnostic required），简称 **IFNDR**。按 ¶2.2，标准对这样的程序没有任何要求：编译器可以报错，可以不报，生成的程序做什么都可以。附录 Annex G [[ifndr]] 汇总了所有这类规则。

!!! lawyer "IFNDR 优先于一切"
    ¶2.3 以 Otherwise 开头，只在 ¶2.2 不适用时才生效。所以一个程序如果同时有一处 IFNDR 违规和一处类型错误，适用的是 ¶2.2，标准连那个类型错误的诊断都不要求。实际的编译器当然照样报错，但那是实现质量问题，不是符合性问题。

### 常量求值中的契约违反（¶2.3.4、¶2.6）{{c++26}}

C++26 引入了**契约断言**（contract assertion）：写在函数声明上的 `pre`、`post`，以及语句 `contract_assert`（[[basic.contract]]）。每次求值一个契约断言，都采用四种语义之一：ignore、observe、enforce、quick-enforce。后三种会检查条件，叫做检查型语义；enforce 和 quick-enforce 在违反时终止程序，叫做终止型语义。具体用哪一种由实现决定，通常由编译选项控制（[[basic.contract.eval]]）。

在常量求值中违反契约时，结局取决于这次求值采用的语义：

```cpp
constexpr int half(int n) pre(n % 2 == 0) { return n / 2; }
constexpr int a = half(4);   // OK
constexpr int b = half(3);   // 契约违反：
                             //   enforce / quick-enforce → 不得接受（¶2.6）
                             //   observe → 必须诊断（¶2.3.4），可以接受，b == 1
                             //   ignore  → 不检查，b == 1
```

observe 的本意是报告之后继续执行，所以在编译期它表现为一条必须发出的诊断，通常是警告，而不是硬错误。截至写作时，本机 Clang 23 还不支持契约语法，这段代码按标准原文分析，没有经过编译验证。

### 标准里的 shall、should、may、can

读条文时要分清下面这几个词。标准按 ISO 的起草规则使用它们：

| 词 | 含义 | 效果 |
|---|---|---|
| shall / shall not | 要求 / 禁止 | 对程序：违反即非良构（除非注明不要求诊断或导致 UB）；对实现：符合性要求 |
| should / should not | 建议 | 不影响符合性，常见于 *Recommended practice* 段落 |
| may / need not | 允许 | 授予实现自由 |
| can / cannot | 能够、可能 | 陈述事实，常见于注中，不构成要求 |

注（Note）、例子（Example）和脚注都只是说明性的，不能单独作为规范依据。库条款还有一套更细的说法，如 *Mandates*（不满足则非良构）、*Constraints*（不满足则不参与重载决议）、*Preconditions*（违反则 UB），定义在 [[structure.specifications]]。

## 抽象机与 as-if 规则 [intro.abstract]

### 生成的代码不必照着源码走

```cpp run ok
int sum_to(int n) {
  int s = 0;
  for (int i = 1; i <= n; ++i) s += i;
  return s;
}
```

本机 Clang 23 用 `-O2` 编译这个函数，生成的代码里没有循环，而是用乘法和移位直接算出 n(n+1)/2。源码说要循环 n 次，编译器却没有循环。这是合法的，理由就在 [intro.abstract]。

¶1 标准的语义描述定义的是一台**参数化的非确定抽象机**（parameterized nondeterministic abstract machine）。标准不要求实现的结构与抽象机相同，实现只需模拟抽象机的可观察行为，而且只需模拟可观察行为。

脚注 5 给这条原则起了名字，叫 **as-if 规则**：只要从程序的可观察行为看不出区别，实现可以不遵守标准的任何要求，结果如同遵守了一样。例如一个子表达式的值没有被使用、也没有影响可观察行为的副作用，就可以不求值。`sum_to` 的循环和闭式公式在可观察行为上无法区分，所以可以互换。

!!! tip "判断 UB 要看抽象机，不要看汇编"
    标准里"先求值 A 再求值 B""对象在这里创建""读取这个值"之类的描述，说的都是抽象机。生成的机器码只对可观察行为负责。所以"汇编里没有这次读内存，因此不是 UB"或者"这里有一条 load 指令，因此发生了访问"这类论证都不成立。

### 抽象机的三类自由度（¶2–¶4）

标准没有规定一台确定的机器，而是留下了三类自由度。

¶2 第一类是参数。有些方面由实现决定，叫做**实现定义行为**（implementation-defined behavior），例如 `sizeof(int)`；还有一些是实现的性质，例如类类型中的填充。实现必须在文档中说明它对实现定义行为的选择。选定这些参数，就得到了与这个实现对应的一台抽象机，标准称之为**对应实例**（corresponding instance）。

¶3 第二类是非确定性。有些方面是**未指定行为**（unspecified behavior），标准通常给出一组允许的结果，实现每次可以任选其一，不必写进文档。例如 `f(a(), b())` 中 `a()` 和 `b()` 谁先求值（[[expr.call]]）。因此同一个程序、同一组输入，在同一台抽象机上也可以有不止一种可能的执行。

¶4 第三类是**未定义行为**（undefined behavior，UB），例如试图修改一个 const 对象。标准对这样的操作不施加任何要求（[[defns.undefined]]）。

### 可观察行为（¶8）

¶8 程序的**可观察行为**（observable behavior）只有三项：

- ¶8.1 通过 volatile glvalue 的访问严格按抽象机的规则求值；
- ¶8.2 交付给宿主环境、要写入文件的数据；
- ¶8.3 交互式设备上的输入输出：程序等待输入之前，提示性的输出必须已经送达。什么算交互式设备由实现定义。

内存里的内容、执行时间、函数调用了几次，都不在其中。所以 as-if 规则允许任意改变它们，几乎所有优化（内联、常量传播、死代码消除、循环变换）都以此为依据。迭代器、智能指针、lambda 这些抽象在优化后能完全消失，也是因为这一点。

volatile 是在语言层面要求编译器保留每一次内存访问的唯一手段，主要用于内存映射的硬件寄存器：

<div class="compare" markdown="1">

```cpp run ok
int plain;
void store_plain() {
  plain = 1;
  plain = 2;   // 可以合并成一次写入 2
}
```

```cpp run ok
volatile int reg;
void store_volatile() {
  reg = 1;
  reg = 2;     // 必须两次写入，顺序不变
}
```

</div>

本机 Clang 23 `-O2` 对左边只生成一条 store，对右边生成两条。volatile 与多线程无关：它不提供原子性，也不建立线程间的先后关系，跨线程通信要用 `std::atomic`（[[atomics]]）。

¶8.3 保证的是先提示、后等待。`std::cout << "Password: "; std::cin >> pw;` 中，提示一定在等待输入之前显示出来。标准库通过把 `cin` 绑定（tie）到 `cout` 做到这一点：从 `cin` 读取之前先刷新 `cout`（[[istream.sentry]]）。

## 未定义行为与时间旅行 [intro.abstract]

### 优化器可以假设 UB 不发生

```cpp run ub
int g(int x) {
  int y = x + 1;           // x == INT_MAX 时有符号溢出：UB
  if (y < x) return -1;    // 只有发生溢出时才可能为真
  return y;
}
```

本机 Clang 23 `-O2` 把 `g` 编译成一条加法，溢出检查被整个删掉了。理由是：实现只对没有 UB 的执行负责，而在没有 UB 的执行里 `y < x` 永远为假。正确的写法是在做加法之前检查 `x == INT_MAX`，或者改用 C++26 的饱和加法 `std::add_sat`（[[numeric.sat]]）。

### UB 可以影响它之前的代码

C++23 及以前，[intro.abstract] 说：如果某条可能的执行含有未定义操作，标准对执行这个程序的实现不施加任何要求，甚至对第一个未定义操作之前的操作也不施加要求。这就是常说的 UB 时间旅行。

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

在本机把输出重定向到文件再运行，程序以 SIGSEGV 结束，文件是空的。重定向到文件时 stdout 是全缓冲的，`puts` 只把字符串放进了程序内部的缓冲区，进程崩溃时缓冲区没有刷新。按 C++23 的措辞，即使数据已经写出，标准也不保证它出现，因为 UB 之前的操作同样不受保护。编译器还可以从之后必然发生的 UB 反推某个分支不会执行，从而删掉那个分支里的输出。

### 可观察检查点（¶5–¶6）{{c++26}}

C++26 通过 [[P1494]] 给时间旅行设了边界。

¶5 程序执行中的某些事件叫做**可观察检查点**（observable checkpoint）。注 1 举了两个例子：调用 `std::observable_checkpoint()`（[[utility.undefined]]），以及契约断言求值中的某些时刻。

¶6 一次执行的**定义前缀**（defined prefix）由这样的操作 *O* 组成：对其中每一个未定义操作 *U*，都有一个检查点 *C*，*O* 先于 *C* 发生，*C* 又先于 *U* 发生。换句话说，一个操作只要和后面的每个 UB 之间都隔着检查点，它就在定义前缀里。

!!! std
    A conforming implementation executing a well-formed program shall produce the observable behavior of the defined prefix of one of the possible executions of the corresponding instance of the abstract machine with the same program and the same input.

实现执行一个良构程序时，必须产生对应实例在同一程序、同一输入下某一条可能执行的定义前缀的可观察行为。选中的那条执行如果含有未定义操作，实现在那之后可以产生任意额外的可观察行为。

分两种情况看这句话：

- 没有 UB 的执行，所有操作都在定义前缀里，实现必须产生整条执行的可观察行为。这就是普通的 as-if 规则。
- 有 UB 的执行，UB 之前、最后一个检查点之前的可观察行为必须如实产生；检查点之后、UB 之前的部分仍然不受保护。

数据竞争（[[intro.races]]）是一个特例。注 2 说明，它产生的 UB 发生在所有参与的线程上。

下面这些事件是检查点：

| 检查点 | 出处 |
|---|---|
| 调用 `std::observable_checkpoint()` | [[utility.undefined]] |
| 以检查型语义求值契约断言之前，以及违反处理函数正常返回之后 | [[basic.contract.eval]] ¶6、¶15 |
| 把数据交付给宿主环境以写入文件的 C stdio 函数调用返回时 | [[cstdio.syn]] ¶2 |
| `basic_filebuf::overflow` 把数据写出之后；`std::print` 直接写终端之后 | [[filebuf.virtuals]]、[[print.fun]] |

交付给宿主环境，指数据真正离开了程序。`puts` 把数据放进缓冲区就返回，不算交付，这次返回也就不是检查点。在上面的例子里，`puts` 之后加上 `std::fflush(stdout);`，`fflush` 的返回就是检查点，"about to read" 必须出现在输出里，编译器也不能再以之后的 UB 为由删掉或推迟它。

`std::observable_checkpoint()` 本身不刷新缓冲区，只保证在它之前已经发生的可观察行为不会因为之后的 UB 而失效。截至写作时，本机 Clang 23 + libc++ 还没有提供这个函数。

!!! warning "volatile 访问是可观察行为，但不是检查点"
    一次 volatile 写之后紧跟着 UB，如果两者之间没有检查点，那次写入不在定义前缀里，同样不受保护。

### 错误行为（¶6–¶7）{{c++26}}

C++26 还引入了**错误行为**（erroneous behavior，EB）：标准认定是错误、但仍然给出了定义的行为（[[defns.erroneous]]）。典型例子是读取未初始化的自动变量，它在 C++26 中读到的是一个错误值，而不再是 UB（[[basic.indet]]）。

¶6 最后一句规定，执行到错误行为时，实现可以发出诊断，也可以终止程序。¶7 建议实现在执行这样的操作时发出诊断。注 3 补充，实现也可以在编译期根据自己的假设判断错误行为可达并提前诊断，代价是可能误报。

| | UB | EB |
|---|---|---|
| 之后的行为 | 任意 | 继续按定义执行，或者诊断，或者终止 |
| 之前的可观察行为 | 只有检查点之前的受保护 | 全部受保护，EB 不是未定义操作 |
| 优化器能否假设它不发生 | 能 | 不能 |

## 实现的种类 [intro.compliance.general]

### hosted 与 freestanding（¶7）

¶7 实现分为**宿主实现**（hosted implementation）和**独立实现**（freestanding implementation）。独立实现是执行时可以没有操作系统支持的实现，常见于内核和嵌入式开发。

- 宿主实现支持标准描述的全部设施。
- 独立实现支持第 5–15 章的全部语言，但标准库只要求 [[compliance]] 列出的子集。异常、RTTI、虚函数在语言层面都必须支持。嵌入式工具链常用的 `-fno-exceptions`、`-fno-rtti` 是不符合标准的方言。
- 独立实现中程序如何启动和终止、是否需要 `main`，都由实现定义（[[basic.start.main]]）。
- 宏 `__STDC_HOSTED__` 在宿主实现中为 1，否则为 0（[[cpp.predefined]]）。本机 Clang 默认是 1，加 `-ffreestanding` 后是 0。

### 加固实现（¶8）{{c++26}}

¶8 实现是否为**加固实现**（hardened implementation）由实现定义。在加固实现中，违反标准库函数的加固前置条件（hardened precondition）会导致契约违反，而不是 UB。

```cpp run ub
#include <span>
#include <cstdio>
int main(int argc, char**) {
  int a[3] = {1, 2, 3};
  std::span<int> s(a);
  std::printf("%d\n", s[argc + 5]);   // 违反加固前置条件 idx < size()
}
```

`std::span::operator[]` 的加固前置条件是 `idx < size()`（[[span.elem]]）。按 [[structure.specifications]] ¶3.5，加固实现会在函数产生任何其他副作用之前，以终止型语义检查这个条件；非加固实现中违反它就是 UB。

本机用 libc++ 默认配置编译，程序打印了一个垃圾值。加上 `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_FAST` 后，程序在越界处陷入并终止。libstdc++ 的对应开关是 `-D_GLIBCXX_ASSERTIONS`。加固模式把最常见的一类内存安全漏洞，越界访问，从 UB 变成了有保证的终止（[[P3471]]）。

### 扩展（¶11）

¶11 实现可以提供扩展，包括额外的库函数，条件是不改变任何良构程序的行为。使用了扩展、按标准是非良构的程序，实现必须诊断；诊断之后可以照常编译执行。

合规的扩展通常使用保留名字。以双下划线、或下划线加大写字母开头的标识符保留给实现（[[lex.name]]），良构程序不会声明它们，所以 `__builtin_expect`、`__int128` 这类扩展不会与任何良构程序冲突。开头的 VLA 属于另一种：它让一段非良构的代码可以使用，同时发出了诊断，所以也合规。

下面两个例子分别违反了这一段的两个条件：

<div class="compare" markdown="1">

```cpp run error
// GNU 语句表达式，不是合法的 C++
int f() {
  return ({ int t = 1; t + 1; });
}
```

```cpp run ok
// 良构：typeof 在 C++ 里是普通标识符
int typeof = 1;
int main() { return typeof; }
```

</div>

左边的代码，本机 Clang 23 默认不给任何诊断，加 `-pedantic` 才有 `-Wgnu-statement-expression` 警告，所以不带 `-pedantic` 时少了一条必须的诊断。右边的代码，`-std=c++2c` 下正常编译，`-std=gnu++2c` 下报错，因为 GNU 模式把 `typeof` 当作关键字，改变了良构程序的含义。

所以符合标准的往往是编译器加上一组特定选项，例如 `-std=c++2c -pedantic-errors`，而不是编译器的默认模式。

`-fwrapv`（有符号溢出按补码回绕）、`-fno-strict-aliasing` 这类选项给原本未定义的情形规定了行为，不影响任何良构程序，因此是合规的扩展。sanitizer 在执行到 UB 时报告并终止，同样合规，因为 UB 之后实现做什么都可以。

## 标准库由谁提供（¶3–¶6）[intro.compliance.general]

¶3 对类和类模板，库条款只给出部分定义，私有成员由实现补全。libstdc++ 的 `std::vector` 里有 `_M_impl`，libc++ 里有 `__begin_`，这些都是实现细节，程序不能依赖。

¶4 对函数、对象和值，库条款给出声明，实现提供与描述一致的定义。规范里的签名是描述性的，实现可以添加默认实参或额外的重载（[[member.functions]]、[[global.functions]]）。这也是为什么取大多数标准库函数的地址是未指定甚至非良构的（[[namespace.std]]）。

¶5 翻译单元通过 `#include` 标准库头文件，或者 `import` 相应的头文件单元来使用库中的名字（[[using.headers]]）。C++23 起还可以 `import std;`（[[std.modules]]）。

¶6 库中的模板、类、函数和对象都有外部链接，实现在链接阶段按需提供它们的定义（[[lex.phases]]）。

<details class="fine" markdown="1"><summary>其余条文</summary>

¶9 *Recommended practice*：鼓励实现在文档中说明它能处理的程序规模和复杂度的限制。Annex B [[implimits]] 列出了一些可能受限的量和建议的最小值，例如复合语句嵌套 256 层。这些都不是要求，¶2.1 已经允许实现以超出限制为由拒绝程序。

¶10 实现可以使用比 [[intro.refs]] 所引用的更新的 Unicode 版本，具体版本由实现定义。这会影响标识符中允许哪些字符（[[lex.name]]）和 `std::format` 的宽度估计。

¶12 每个实现都要提供文档，列出它不支持的所有有条件支持的构造，并定义所有与区域设置相关（locale-specific）的特性。脚注 4 补充，这份文档同时也定义实现定义行为。实践中 GCC 手册有专门的 C++ Implementation-Defined Behavior 一章，但没有哪个主流实现完整列出了所有实现定义行为。

</details>

## 历史与演进

!!! history
    - C++98 起标准就有 as-if 规则（作为脚注）和实现定义、未指定、未定义三类行为，基本沿用 C 标准的框架。抽象机最初写在 [intro.execution] 开头，后来独立成 [intro.abstract]，[intro.execution] 本身移到了第 6 章的 [[basic.exec]]。
    - C++11 起，有条件支持成为正式的一类构造。
    - C++23 把 `#warning` 标准化，列入 ¶2.3.2。
    - C++26 加入了错误行为（[[P2795]]）、契约断言及其在常量求值中的诊断要求（[[P2900]]）、加固实现（[[P3471]]），以及可观察检查点和定义前缀（[[P1494]]）。最后一项取代了 UB 对其之前的操作也不施加要求的措辞。

## 常见误解

!!! pitfall "编译通过就说明程序合法"
    反过来也不成立。良构程序可能收到警告，甚至因超出实现限制被拒绝；非良构程序可以在诊断后被接受，IFNDR 程序可以没有任何提示地通过。

!!! pitfall "C++26 之后 UB 不会再时间旅行"
    时间旅行只是受到了限制。定义前缀只保护检查点之前的可观察行为；检查点之后、UB 之前的输出，比如还在缓冲区里的数据或一次 volatile 写，仍然不受保护。检查点保护的也只是可观察行为，不是程序状态。

!!! pitfall "程序退出是可观察行为"
    ¶8 的三项里没有程序终止或返回码。`main` 的返回值经由 `exit` 交给宿主环境（[[support.start.term]]）。一个没有副作用的无限循环和一个立即返回的程序之间的区别，由 [[intro.progress]] 的前进保证处理，不由 ¶8 处理。

## 思考题

!!! question "思考题 1"
    下面的程序运行时 `p` 为空。在 C++26 下，stdout 是终端（行缓冲）时是否保证打印出 "start"？重定向到文件呢？
    ```cpp
    std::puts("start");
    *p = 0;
    ```

<details markdown="1">
<summary>答案</summary>

行缓冲时，`puts` 输出整行后就把数据交付给宿主环境，这次返回是一个可观察检查点（[[cstdio.syn]] ¶2），"start" 在定义前缀中，必须出现。

重定向到文件时 stdout 是全缓冲的，`puts` 只把数据放进缓冲区，它的返回不是检查点，"start" 不保证出现。想在两种情况下都得到保证，在 `puts` 后加 `std::fflush(stdout)`。（stdout 何时刷新由 C 标准和实现决定，以上按典型的 POSIX 行为分析。）
</details>

!!! question "思考题 2"
    GCC 和 Clang 的 `-std=gnu++2c` 把 `typeof` 当关键字；Clang 默认接受 GNU 语句表达式而不给诊断。它们分别违反了 ¶11 的哪一部分？

<details markdown="1">
<summary>答案</summary>

前者违反了扩展不得改变良构程序行为这一条：`int typeof = 1;` 是良构的 C++，在 GNU 模式下却成了错误。后者违反了必须诊断使用扩展的非良构程序这一条。两者都说明编译器的默认模式通常不是符合标准的模式。
</details>
