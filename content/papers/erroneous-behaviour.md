---
title: 错误行为与未初始化读取（P2795）
summary: C++26 怎样处理读取未初始化局部变量这个常见的安全漏洞：为什么没有采纳全部零初始化，而是新增了一种行为类别"错误行为"，让未初始化的自动变量持有实现选定的错误值，再用 [[indeterminate]] 给需要性能的代码留出退路；以及 Clang 23 今天离这套语义还有多远。
status: draft
order: 36
group: C++26
since: c++26
papers: P2795R5, P2723R1, P2754R0, P0632R0, P3684R1, CWG3020
related: basic.indet, dcl.attr.indet, intro.abstract, intro.compliance.general, conv.lval, expr.const.core, expr.const.const, bit.cast, class.base.init, cpp.cond, basic.start.static, dcl.init, topics/undefined-behavior, topics/initialization, papers/contracts, papers/library-hardening
tags: 错误行为, 未初始化, UB, 安全, 提案, C++26
updated: 2026-10-19
---

!!! tldr
    - 在 C++23 中，读取一个没有初始化的局部变量是未定义行为。它既让优化器可以随意改写程序，也会把栈上残留的数据（比如上一次调用留下的密钥）原样读出来。
    - [[P2723R1]] 提议把所有自动变量零初始化。它堵住了漏洞，但让 `int x;` 变成了合法的写 0 的方式，工具从此无法再把忘记初始化报告为错误，所以没有被采纳。
    - [[P2795R5]] 新增了**错误行为**：行为有定义，但标准认定它是错误，建议实现诊断，允许实现终止程序。未初始化的自动变量持有实现选定的错误值，读取它就是错误行为。
    - 堆内存、标了 `[[indeterminate]]` 的变量仍是不确定值，读取仍是 UB；错误值对类型无效时（如 `bool`）读取也仍是 UB。
    - 本机 Clang 23 在 `-std=c++2c` 下还没有实现这套语义，默认仍按 UB 优化；`-ftrivial-auto-var-init=pattern` 或 `=zero` 提供了与之相当的行为，`[[indeterminate]]` 尚不识别。

## 一行 `int x;` 能泄露什么

下面的程序里，`report` 忘了初始化缓冲区，`login` 恰好刚在同一块栈空间里放过一个密钥：

```cpp title="stack-leak.cpp" run eb
#include <cstdio>
#include <cstring>

[[gnu::noinline]] void login() {
  char key[16];
  std::strcpy(key, "hunter2-secret");
  asm volatile("" : : "r"(key) : "memory");
}

[[gnu::noinline]] void report() {
  char msg[16];                 // 忘了初始化
  std::printf("%.15s\n", msg);  // 读取未初始化的字节
}

int main() {
  login();
  report();
}
```

`asm volatile` 一行只是为了让 `login` 里的写入不被优化掉。本机 Clang 23 以 `-std=c++2c -O2` 编译，程序输出 `hunter2-secret`；`-Wall -Wextra` 没有任何警告，`-fsanitize=address,undefined` 也不报告。`report` 读到的是 `login` 留在栈上的字节。

在 C++23 中，这次读取是[[g:undefined-behavior|未定义行为]]（UB）：标准对整个执行不作任何要求。实际上会发生两类事情：

- 数据泄露。如上例所示，变量占用的栈槽或寄存器里有什么就读出什么。[[P2723R1]] 引用了 Chrome 中 1100 多个"使用未初始化值"的安全缺陷，以及 Android 中约 12% 的可利用缺陷属于这一类的统计。
- 优化器改写程序。编译器可以假设读取不会发生，再据此删除分支或合并路径。[[topics/undefined-behavior]] 用一个 `if (b) x = 1; return x;` 的例子展示了 Clang 怎样让函数无论 `b` 是什么都返回 1。

问题的规模大到许多项目早已绕开标准自己解决：Clang 和 GCC 提供 `-ftrivial-auto-var-init=zero` 或 `=pattern`，把没有初始化器的自动变量自动填充，微软在 Windows 内部也用类似的机制。按 P2723R1 的描述，这类选项从 2018 年起陆续实现，已部署到主流操作系统和浏览器中。

## 设计空间

一个选项只在打开它的项目里有效，而且依赖它的代码在标准看来仍然是 UB。委员会要决定的是：语言本身该怎样规定这次读取。[[P2754R0]] 把讨论中出现过的方案整理成一张表，从三个角度评估：方案能否自洽地写进标准（可行性），已有代码是否照常编译和运行（兼容性），以及不写初始化器的声明是否还能表达作者的意图（表达力）：

| 方案 | 可行性 | 兼容性 | 表达力 |
|---|---|---|---|
| 全部零初始化 | 可行 | 兼容 | 变差 |
| 零初始化，能证明读取时报错 | 不明确 | 正确代码兼容 | 不变 |
| 必须在源码中初始化 | 可行 | 不兼容 | 变好 |
| 必须初始化，或显式标注延迟初始化 | 可行 | 不兼容 | 变好 |
| 填一个默认值，但读取仍是 UB | 不可行 | 兼容 | 不变 |
| 填一个默认值，读取是错误行为 | 可行 | 兼容 | 不变 |
| 取消默认初始化，只保留值初始化 | 不明确 | 不明确 | 不明确 |

表达力这一列需要解释。今天 `int x;` 只有两种可能的含义：作者忘了初始化（这是 bug），或者作者打算稍后再写入（读取前一定会写）。读代码的人和工具都可以据此推理：凡是在写入之前读取，就一定是错的。一个方案如果给 `int x;` 增加了第三种合法含义，表达力就变差了。

### 全部零初始化（P2723）

[[P2723R1]] 的方案最直接：把所有自动存储期对象零初始化，包括填充字节；动态存储期不变。理由有三条：这正是 `-ftrivial-auto-var-init=zero` 已经大规模部署的行为；作者报告的性能影响在 0.5% 以内；静态和线程存储期的对象本来就先零初始化（[[basic.start.static]]），这样自动存储期也一致了。

它没有被采纳，原因在论文自己的"注意事项"一节里就已经写明：

<div class="compare" markdown="1">

```cpp title="P2723：值为 0，行为有定义"
void f(int);

void g() {
  int x;   // 就是 int x = 0;
  f(x);    // 也许是故意的，也许是 bug
}
```

```cpp title="P2795：错误值，错误行为"
void f(int);

void g() {
  int x;   // 实现选定的错误值
  f(x);    // 一定是 bug，可以报告
}
```

</div>

- 掩盖 bug。零初始化成为语言保证后，有人会故意依赖它。从此 `int x;` 后面读到 0 可能是 bug，也可能是作者想要的 0，静态分析、MemorySanitizer、Valgrind 都无法再区分，只能放弃报告。P2723 的说法是，安全问题消除了，正确性问题却无法再被诊断。
- 零不一定安全。论文举了 Linux 的例子：`task->uid` 为 0 表示 root，读到未初始化的 0 曾经导致过 CVE。对某些枚举，0 根本不是有效的枚举值。
- 一个 `int` 没有天然的默认值。P2795 的作者指出，`std::vector<int> v;` 得到空容器是自然的，因为容器为空是一个合理的初始状态；`int` 却没有哪个数比别的数更合适。想要 0 就写 `int x = 0;`。

P2723 也讨论过把值换成 `0xAA` 这样的重复字节模式：指针读出来会立即触发访问错误，浮点数是带载荷的 NaN，便于追查。代价是在一些负载上约 1.5% 的体积和性能退化（论文引用的数字），而且很大的整数用作尺寸时可能让边界检查失效。这说明选什么值本身就是一个取舍，不同的构建也许需要不同的值。

### 保持 UB

不改标准，继续让各家提供编译选项。P2723 指出，实现者普遍不喜欢这条路：一个大家都会打开、都会依赖的选项，实际上分裂出了一种语言方言。

另一个变体是：规定变量填一个默认值，但读取仍是 UB。P2754 判定它不可行。UB 的意思是标准不作任何要求，一边规定填什么值一边说读取没有要求，前半句就没有约束力：为了优化而不填值的编译器照样符合标准。

### 让它非良构

要求每个自动变量都有初始化器，或者像 C#、Swift 那样要求编译器证明变量在读取前一定被赋值（definite initialization）。表达力最好，但两条路都走不通：

- 现存的大量正确代码先声明、后通过指针写入（比如 `int n; read_size(&n);`），全部要改。P2754 还担心大家会用脚本给所有变量补上 `= 0`，结果又一次抹掉了原作者的意图。
- 证明在读取前一定赋值需要一个数据流分析。分析太简单会误报大量正确代码；分析足够聪明，标准就得把一套复杂且会不断改进的算法写进去，否则各编译器接受的程序就不一样。

"零初始化，能证明读取时报错"有同样的问题：一个程序是否良构，取决于编译器的分析能力。

### 只保留值初始化

把默认初始化整个取消，让 `T x;` 总是值初始化。这会顺带简化初始化规则，但 P2723 指出，它要么调用构造函数从而改变已有类类型的行为，要么对 `int` 仍然什么也不做；P2754 也认为它涉及面太广，短期内无法完成。

### 新的行为类别

剩下的那一行就是 [[P2795R5]] 的方案：变量的字节由实现填上一个值，读取它是一种新的行为，既不是 UB，也不是普通的良定义行为。P2723 自己在第 4.14 节就记录了这个想法，把它称为一种新的"标准用语"（word of power）。P2754 的表里，它是唯一同时可行、兼容、不损失表达力的方案。

## 最终设计

### 错误行为

[[defns.erroneous]] 定义了这个新类别：

!!! std
    erroneous behavior: well-defined behavior that the implementation is recommended to diagnose
    
    错误行为是良定义的行为，建议实现对它进行诊断。

定义下的注说，错误行为总是由不正确的程序代码引起。[[intro.abstract#6]] 规定了实现能做什么：执行到一个被规定为错误行为的操作时，实现可以发出诊断，可以终止程序；[[intro.abstract#7]] 的推荐做法是在执行到它时发出诊断，并用一个注允许诊断有误报。[[intro.compliance.general#2]] 的脚注 3 相应地补充：正确执行的程序可以包含错误行为，取决于处理的数据。

[[g:erroneous-behavior|错误行为]]与 UB 的区别在于执行到它之后：

- UB 之后标准不作任何要求，优化器可以假设它不发生；
- 错误行为之后程序必须按规定继续执行（这里就是读出那个错误值），除非实现选择诊断后终止。

两者都表示代码写错了。所以工具可以同样对待：sanitizer 照样报告，编译器照样警告；而在没有工具介入的生产构建里，程序的行为是确定的。

### 错误值由实现选定

[[basic.indet#1]] ¶1.2 规定，自动存储期对象的存储取得时，字节具有[[g:erroneous-value|错误值]]，每个值由实现决定，与程序的状态无关。与程序状态无关这一句排除了直接沿用栈上残留数据的做法，上面泄露密钥的程序在 C++26 中不能再输出 `hunter2-secret`。

标准没有规定这个值是 0。P2795 的理由是，允许实现在不同的构建模式下使用不同的"毒值"：调试时用容易识别的模式，生产时用 0。值固定为 0 更可预测，但也更容易被程序员有意依赖。逐字节的细节（值表示中哪一位是错误值、`unsigned char` 的搬运例外）见 [[basic.indet]]。

### 适用范围的反复

P2795 的修订历程里，适用范围变过一次。R3 把它收窄到非静态局部变量，因为函数形参和临时对象不好提供退出的语法。EWG 随后要求所有自动存储期对象一视同仁，让心智模型简单，安全收益也覆盖所有情况，R4 于是恢复为全部自动存储期对象，包括形参和临时对象。临时对象没有退出手段，论文认为它们很少能被观察到，优化器通常能消掉多余的写入。

### 仍然是 UB 的情形

P2795 只改了自动存储期对象的初值，其余都保持原样：

| 情形 | C++26 中读取的后果 | 依据 |
|---|---|---|
| 动态存储期（`new int`、`malloc`） | UB | [[basic.indet#1]] ¶1.1 |
| 标了 `[[indeterminate]]` 的变量或形参 | UB | [[basic.indet#1]] ¶1.1 |
| 错误值对类型无效（如 `bool` 读到 `0xAA`） | UB | [[conv.lval#3]] ¶3.3 |
| 把不确定值复制进一个已初始化的变量后再读 | UB | 值仍是不确定值 |
| 在局部数组上 placement new 一个默认初始化的 `char` | 原有内容不被覆盖 | 只影响存储取得时的初值 |

第三行最容易被忽略。下面的函数是错误行为还是 UB，取决于实现选的值：

```cpp title="bool-flag.cpp" run
#include <cstdio>
[[gnu::noinline]] bool flag() {
  bool b;      // 错误值，可能不是有效的 bool
  return b;    // 值有效：错误行为；无效：UB
}
int main() { std::printf("%d\n", flag() ? 1 : 0); }
```

本机 Clang 23 以 `-O0 -fsanitize=undefined -ftrivial-auto-var-init=pattern` 编译运行，UBSan 报告 load of value 170, which is not a valid value for type 'bool'，170 就是 `0xAA`。换成 `=zero` 则没有报告，输出 0。指针同理：未初始化的指针即使有确定的错误值，解引用它仍是 UB。

### `[[indeterminate]]`：退出机制

R2 之前没有退出手段，是核心组要求加上的：对已经正确的代码，填充只有成本、没有收益，大缓冲区尤其明显。被标注的对象回到 C++23 的语义，初值是[[g:indeterminate-value|不确定值]]，读取是 UB，编译器可以照旧据此优化。

```cpp title="indeterminate.cpp" run ok
#include <cstddef>
#include <iostream>

void compute(int* a, int* b, std::size_t n) {
  *a = 0;
  for (std::size_t i = 0; i < n; ++i) b[i] = int(i);
}

int main() {
  int x [[indeterminate]];         // 只作用于 x
  std::cin >> x;                   // 读入失败时 x 被置 0

  [[indeterminate]] int a, b[10];  // 作用于 a 和 b
  compute(&a, b, 10);
  return a + b[9] - 9 + x * 0;
}
```

这个例子改编自 P2795。属性写在声明开头时作用于所有声明符，写在声明符名字之后时只作用于这一个。[[dcl.attr.indet#1]] 只允许它用在自动存储期块变量的定义和函数形参上；¶2 规定形参上的属性必须出现在函数的首次声明里，不同翻译单元的首次声明一个标了、一个没标，程序非良构，不要求诊断。

退出的语法有过三种候选：属性 `int x [[foo]];`、关键字 `int x = noinit;`、库类型 `int x = std::uninitialized;`。按 P2795 的记录，前两种在委员会的投票中都没有形成共识，库类型只得到轻微支持。论文仍然选了属性，理由是另两种都是全新的机制、没有实现经验，而属性是成熟的机制，写进代码后在 C++11 起的任何版本都能编译（Clang 也早有功能相同的 `[[clang::uninitialized]]`）。属性还可以被忽略：一个带着属性正确的程序，去掉属性仍然正确，属性只会让代码更不宽容。

名字的选择受一个陷阱影响，P2795 称之为**意外的自我文档化陷阱**：如果退出语法看起来像是在说明这里故意不初始化，代码规范要求每个变量都写初始化器的团队就会把它当作规范写法：

```cpp
int x;            // C++23 的旧写法
int x = noinit;   // 假想语法：看上去是更规范的同一件事
```

后一行其实关掉了安全机制。所以 `[[uninitialized]]`（[[P0632R0]] 提议过的名字）、`noinit`、`for_overwrite` 都被否决，`not_zeroed` 又暗示了错误值是 0。最后选了 `indeterminate`：与核心措辞中的术语一致，而且足够陌生，使用者需要先查清楚它是什么意思。

P2795 没有提供特性测试宏，理由是它没有增加面向用户的特性；需要时用 `__has_cpp_attribute(indeterminate)` 检测属性。这个属性值起初被漏掉了，后来由 [[CWG3020]] 补进 [[cpp.cond]] 的表中，值为 `202403L`。

## 措辞

P2795R5 改动的条款如下，¶ 号按当前草案：

| 条款 | 改动 |
|---|---|
| [[defns.erroneous]] | 新增术语"错误行为"；[defns.undefined] 的注里原先说 erroneous construct、erroneous data，改为 incorrect、invalid，把这个词腾出来 |
| [[intro.compliance.general#2]] 脚注 3 | 正确执行可以包含 UB 和错误行为 |
| [[intro.abstract#6]]、¶7 | 错误行为允许诊断和终止，推荐诊断，允许误报 |
| [[basic.indet]] | 标题改为不确定值与错误值；¶1 区分两种初值，¶2 规定读取错误值是错误行为，并把 `unsigned char`、`std::byte` 的例外推广到错误值 |
| [[conv.lval#3]] ¶3.3 | 值表示对类型无效时仍是 UB |
| [[expr.const.core#2]] ¶2.8、[[expr.const.const#4]] | 错误行为不能出现在常量求值中，常量表达式的结果不能含错误值 |
| [[dcl.attr.indet]] | 新增 `[[indeterminate]]` |
| [[bit.cast#3]] | 源对象中的错误位对应到结果；目标是 `unsigned char`、`std::byte` 时原样传递，否则是错误行为，结果按位复制但不再含错误值 |
| [[class.base.init#9]] 的注 | 构造函数没有初始化的成员具有不确定值或错误值 |

常量求值的部分在本机 Clang 23 上已经按预期工作：

```cpp title="constexpr-read.cpp" error
constexpr int f() {
  int x;
  return x;   // 常量求值中读取错误值
}
constexpr int v = f();  // error: 不是常量表达式
```

Clang 报告 read of uninitialized object is not allowed in a constant expression。这一点 C++23 中本来就成立，读取不确定值是 UB，同样不能出现在常量求值中。

这项改动没有 Annex C 条目。它把 UB 改成有定义的行为，没有让任何正确的程序改变含义；[[diff.cpp23]] 里与错误行为有关的条目是另一件事：用非空指针和大小 0 调用 `realloc` 也被规定为错误行为（[[c.malloc]]）。

### 后续修正：错误值会传播（P3684）

P2795R5 原先的 [intro.abstract] 允许实现在错误行为发生后、在一个未指定的时间终止程序。这是为 MemorySanitizer 这类实现留的余地：它对机器码插桩，读取本身往往不报告，要等到依赖这个值的分支才报告，这时离读取可能已经很远。

[[P3684R1]] 指出这样写的代价：程序一旦执行过一次错误行为，此后任何时刻都可能被终止，即使它正在做完全无关的事。这既让程序难以推理，也妨碍把错误行为推广到其他场合，例如与契约违反的语义统一（契约见 [[papers/contracts|契约（P2900）]]）。它的修正是让错误值具有黏性，用传播代替延迟终止：

- [[intro.abstract#6]] 删去"在之后某个未指定的时间"，实现只能在执行错误行为的那个操作上诊断或终止；
- [[basic.indet#2]] 开头新增一句：产生 prvalue 的内置运算符，只要某个经过求值、不是弃值表达式的操作数产生了错误值，运算结果也是错误值；同时把读取错误值的结果从"不是错误值"改成"就是那个错误值"。

```cpp title="propagate.cpp" eb
int g(bool c) {
  int x;                // 错误值
  int y = x * 0;        // 错误行为；y 也是错误值
  bool t = c && x > 0;  // c 为 false 时不求值 x > 0
  return t ? 1 : y;     // 返回 y：错误行为
}
```

`x * 0` 在数学上与 `x` 无关，P3684 仍然让结果是错误值：要在标准里逐一列出乘 0、模 1 这类结果不依赖操作数的情形太复杂，而且浮点的 NaN、整数的陷阱表示都会让这种推理失效。实现可以自行更宽松，MemorySanitizer 实际上就把乘 0 的结果当作干净的值。短路运算符没有求值的右操作数不参与传播。这样一来，MemorySanitizer 在下游分支上报错时，那个分支本身就在使用错误值，属于在错误行为发生处终止。P3684R1 作为对 C++26 的国家团体意见的处理并入，当前草案中的 [[basic.indet#2]] 已是修正后的写法。

## 代价与现状

### 性能

填充的成本取决于对象有多大、填充能否被证明是多余的。标量和随后被完整赋值的小对象，优化器通常能把填充消掉，或者只多一两条指令；大缓冲区只用了一小部分时，成本最明显。下面的函数在本机测量：

```cpp
[[gnu::noinline]] int work() {
  char buf[4096];   // 只用前 16 字节
  fill(buf, 16);    // fill、sum 定义在另一个翻译单元
  return sum(buf, 16);
}
```

| 编译选项（`-O2`） | 每次调用 |
|---|---|
| 不填充（`=uninitialized`，即默认） | 约 4.6–5.0 ns |
| `-ftrivial-auto-var-init=zero` | 约 54–83 ns |
| `-ftrivial-auto-var-init=pattern` | 约 55–90 ns |
| `=pattern`，`buf` 标 `[[clang::uninitialized]]` | 约 4.7–5.9 ns |
| `=pattern`，缓冲区缩小为 16 字节 | 约 4.8–5.1 ns |

数据来自 Apple M2 Pro 上的本机 Clang 23，每种配置 7 轮取最快一轮、重复 3 次。测量时机器负载很高（load average 超过 100），绝对值噪声较大，只应看量级：4 KB 的填充让这个函数慢了约十倍，标注退出后完全恢复，小缓冲区则看不出差别。`=pattern` 下的汇编里，`work` 多了一次对 `memset` 的调用，标注后消失。

这与 P2723 报告的大型代码库上不足 0.5% 的整体开销并不矛盾：大多数函数没有大块的栈缓冲区。少数热点函数正是 `[[indeterminate]]` 要处理的地方。

### Clang 23 的实现状态

截至写作时，Clang 的 C++ 状态页把 P2795R5 和 P3684R1 都标为未实现。本机 Clang 23.1.3 的实测：

| 检查 | 结果 |
|---|---|
| `-std=c++2c -O2`，`int x; if (c) x = 42; return x;` | 不论 `c` 都返回 42，与 `-std=c++23` 相同 |
| `-std=c++2c -O2`，`int x; return x;` | 不写返回寄存器，返回调用前残留在里面的值 |
| 上面泄露密钥的程序，默认选项 | 输出 `hunter2-secret` |
| 同一程序，`-ftrivial-auto-var-init=zero` / `=pattern` | 输出空串 / 15 个 `0xAA` 字节 |
| `-fsanitize=address,undefined` | 不检测未初始化读取 |
| `-fsanitize=memory` | 不支持 arm64 macOS 目标 |
| `[[indeterminate]]` | 警告 unknown attribute 并忽略；`__has_cpp_attribute(indeterminate)` 为 0 |
| `[[clang::uninitialized]]` | 在 `-ftrivial-auto-var-init` 下按变量退出，效果与 `[[indeterminate]]` 的意图相同 |
| 常量求值中读取未初始化变量 | 报错 |

返回 42 的那一行，单独看还可以争辩 42 是不是实现选定的值；返回寄存器残留和泄露密钥则显然依赖程序状态，违反 [[basic.indet#1]] ¶1.2。所以默认选项下的 Clang 23 在这一点上还不符合 C++26。要得到 C++26 的保证，目前需要显式加上 `-ftrivial-auto-var-init=zero` 或 `=pattern`；P2795 本身就把这两个选项列为现成的实现方式，只是它们不会诊断。`-Wuninitialized` 只能抓住同一函数内显而易见的情形，像上面通过 `printf` 读取数组的例子就不报告。GCC 和 MSVC 本机未验证。

### 今天怎样写

- 写初始化器。`int x = 0;` 表达的是需要 0，`int x;` 在 C++26 中仍然是一个等待被写入的变量，在写入前读取仍然是 bug，只是后果被限制住了。
- 在测试构建里用 `-ftrivial-auto-var-init=pattern`，让错误值容易被认出；能用 MemorySanitizer 的平台上用它查找读取。生产构建在支持 C++26 语义之前，可以考虑 `=zero` 或 `=pattern`。
- 确认某个大缓冲区一定会先被写满、且性能剖析显示填充是热点时，再加 `[[indeterminate]]`（在 Clang 上暂时配合 `[[clang::uninitialized]]`）。
- 对 `bool`、枚举和指针，错误值不能带来安全感：无效的位模式仍是 UB，空指针或模式指针被解引用也仍是 UB。

初始化的各种形式何时留下未初始化的对象，见 [[topics/initialization]]；UB、错误行为与其他行为类别的完整对比，见 [[topics/undefined-behavior]]；库一侧用加固前置条件处理越界等错误，见 [[papers/library-hardening|标准库加固]]。

## 思考题

!!! question "1. 形参也有错误值吗"
    ```cpp
    struct T { T() {} int x; };
    int h(T t) { return t.x; }
    int main() { return h(T()); }
    ```
    在 C++26 中，`return t.x;` 是什么行为？如果把形参写成 `T t [[indeterminate]]` 呢？

<details markdown="1">
<summary>答案</summary>

`T` 的默认构造函数是用户提供的，但没有初始化 `x`，所以 `x` 保持存储取得时的初值（[[class.base.init#9]] 的注）。形参 `t` 具有自动存储期，按 [[basic.indet#1]] ¶1.2，它的字节是错误值，读取 `t.x` 是错误行为。加上 `[[indeterminate]]` 后适用 ¶1.1，字节是不确定值，读取是 UB。这正是 [[dcl.attr.indet#3]] 的例子。P2795 在 R3 一度把形参排除在外，R4 才恢复。

</details>

!!! question "2. 为什么不让 `new int` 也得到错误值"
    P2795 和 P2723 都没有改变动态存储期对象的初值。从实现的角度看，难处在哪里？

<details markdown="1">
<summary>答案</summary>

自动变量的填充发生在函数内，编译器看得到之后的写入，能消掉大多数多余的填充。堆分配则要在分配器里填充每一块内存，编译器很难证明它多余，而且大块分配常常本来就会被整个覆盖写入，这部分成本难以消除。P2723 在注意事项里说，堆内存的自动初始化还是较新的研究和部署领域，各代码库的取舍不同，没有公认的方案。所以 C++26 中 `new int` 的值仍是不确定值，读取仍是 UB（[[basic.indet#1]] ¶1.1）。

</details>
