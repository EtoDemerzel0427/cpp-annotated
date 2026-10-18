---
title: 未定义行为：标准视角与编译器视角
summary: 标准说 UB 是"不施加任何要求"，编译器把它读作"可以假设不会发生"。用 Clang -O2 的真实输出演示有符号溢出、空指针检查消除、无限循环删除（及 C++26 的平凡无限循环）、"时间旅行"；C++26 的可观察检查点与错误行为；常量求值作为 UB 探测器；UBSan/ASan/MSan/TSan/TySan 与 libc++ 加固模式
status: draft
order: 5
since: c++98
papers: P1494, P2795R5, P2809R3, P3471
related: intro.defs, intro.compliance, intro.progress, stmt.iter.general, basic.indet, expr.const.core, dcl.attr.assume, utility.undefined, ub, topics/type-punning, topics/dangling-references, topics/object-model
tags: UB, 优化, sanitizer, 加固, 错误行为, 专题
updated: 2026-10-18
---

**未定义行为**（undefined behavior，UB）在标准里只有一句定义（[[intro.defs]] 3.66）：

!!! std
    behavior for which this document imposes no requirements

    本文档对其不施加任何要求的行为。

这句话有两种读法。**标准的读法**是消极的：这里我们不说了，实现爱怎么办怎么办——可以忽略、可以按平台的方式做点有文档的事、可以终止。**编译器的读法**是积极的：既然一个正确的程序不会执行 UB，那么优化时就可以**假设它不会发生**，并据此推出关于程序的"事实"。几乎所有让人惊讶的 UB 现象，都是第二种读法的产物。

本专题先简要回顾行为分类，然后用 Clang 23（Apple arm64）的真实输出展示编译器如何利用 UB，再讨论 C++26 给 UB 加上的两道护栏（可观察检查点、错误行为），最后是检测与缓解工具。

## 行为分类：UB 在谱系中的位置

| 类别 | 谁负责 | 实现的义务 | 例子 |
|---|---|---|---|
| ill-formed（需诊断） | 编译期 | 至少一条诊断 | 类型不匹配 |
| IFNDR | 编译期（常跨 TU） | 无（程序没有任何意义） | ODR 违反 |
| implementation-defined | 运行期 | 从允许的行为中选一种，**写进文档** | `sizeof(int)` |
| unspecified | 运行期 | 从允许的行为中选一种，不必写文档 | 函数实参求值顺序 |
| **erroneous** {{c++26}} | 运行期 | 行为有定义；**建议**诊断，可以终止 | 读未初始化的自动变量 |
| **undefined** | 运行期 | **无** | 有符号溢出、空指针解引用 |
| runtime-undefined | 常量求值中特殊 | 运行期同 UB；常量求值中是否视为非常量由实现定义 | 违反 `[[assume]]` |

精确定义与区分见 [[intro.defs]]，它们如何转化为对实现的要求见 [[intro.compliance]]。两点值得强调：

- **显式 UB 与隐式 UB**。标准用"the behavior is undefined"等措辞写明的是显式 UB，当前草案的资料性附录 Annex F [[ub]] 把第 4 到 15 章的显式核心语言 UB 汇编成表，每条带一个稳定标识（例如严格别名违反是 `[ub:expr.basic.lvalue.strict.aliasing.violation]`）。此外，"标准没有给出任何定义"的情形也是 UB（定义的注 1），这类**隐式 UB** 不在附录中。
- **库 UB**。违反库函数的 *Preconditions* 是 UB（[[structure.specifications#3]] ¶3.4），`vector::operator[]` 越界、`std::sort` 用不满足严格弱序的比较器都是。这一类是加固模式的主要目标。

## 编译器视角：UB 是优化的前提

优化器不"利用 bug"，它只是在推理时用上了"程序没有 UB"这一前提。下面每个例子都是本机 `clang++ -std=c++2c -O2` 的真实产物。

### 有符号溢出

```cpp
bool always(int x)    { return x + 1 > x; }      // 有符号：溢出是 UB
bool wraps(unsigned x){ return x + 1 > x; }      // 无符号：按模 2ⁿ 回绕，有定义
int count(int n) {
  int c = 0;
  for (int i = 0; i <= n; ++i) ++c;
  return c;
}
```

```text
__Z6alwaysi:                 ; x + 1 > x 恒为真
	mov	w0, #1
	ret
__Z5wrapsj:                  ; 只有 x == UINT_MAX 时为假
	cmn	w0, #1
	cset	w0, ne
	ret
__Z5counti:                  ; 不循环：直接算出 max(n, -1) + 1
	orr	w8, w0, w0, asr #31
	add	w0, w8, #1
	ret
```

`always` 之所以能折成常量：若 `x + 1` 不溢出，则 `x + 1 > x` 成立；若溢出，则是 UB，编译器想返回什么都行——两种情况下返回 `true` 都"正确"。`count` 更有代表性：编译器假设 `i` 不会溢出，从而断定循环**一定终止**且恰好执行 `n + 1` 次，整个循环被闭式公式取代（`n == INT_MAX` 时抽象机里的 `++i` 溢出，所以这个输入不在编译器的考虑范围内）。

真实代码中这条规则最大的收益来自 64 位平台上的 `int` 循环变量：因为它不会回绕，编译器可以把它提升为 64 位的指针偏移，而不必每次迭代做符号扩展。

`-fwrapv` 让有符号运算按补码回绕——把 UB 变成有定义的行为（合规的扩展）。用它编译，`always` 变回 `x != INT_MAX` 的比较。

### 空指针检查消除

```cpp
int read(int* p) {
  int v = *p;            // 若 p 为空：UB
  if (p == nullptr)      // 编译器：既然上面解引用了，p 必不为空
    return -1;
  return v;
}
```

```text
__Z4readPi:                              ; -O2
	ldr	w0, [x0]
	ret
__Z4readPi:                              ; -O2 -fno-delete-null-pointer-checks
	cbz	x0, LBB0_2
	ldr	w0, [x0]
	ret
LBB0_2:
	mov	w0, #-1
	ret
```

检查被整个删掉了。这正是著名的 Linux 内核漏洞模式：先解引用、后判空，判空被优化掉，而在内核里地址 0 可能被映射，解引用并不崩溃。此后内核改用 `-fno-delete-null-pointer-checks` 编译。

### 无副作用的无限循环

[[intro.progress#1]] 允许实现假设每个线程最终会终止、调用 I/O、访问 volatile、执行同步操作……（或者继续执行一个**平凡无限循环**，见下文）。一个什么都不做、又不终止的循环违反了这个假设，编译器可以认为它不存在：

```cpp run title="fermat.cpp" ub
#include <cstdio>
bool fermat(unsigned limit) {        // 在 [1, limit] 里找 a³ + b³ == c³ 的反例
  for (unsigned a = 1;; a = a % limit + 1)
    for (unsigned b = 1; b <= limit; ++b)
      for (unsigned c = 1; c <= limit; ++c)
        if (a*a*a + b*b*b == c*c*c) return true;
}
int main() {
  if (fermat(1000)) std::puts("Fermat disproved!");
  else std::puts("Fermat holds");
}
```

```text
$ clang++ -std=c++2c -O2 fermat.cpp && ./a.out
Fermat disproved!
```

`fermat` 被编译为 `mov w0, #1; ret`。推理过程：循环唯一的出口是 `return true`；循环没有可观察副作用，所以按 [[intro.progress#1]] 它必须终止；因此函数必然返回 `true`。（1000 以内的立方和不会超出 32 位，没有回绕产生的伪解——费马大定理在这里成立，这个循环其实永不终止。）

#### C++26：平凡无限循环不再是 UB {{c++26}}

`while (true);` 这种**故意**的死循环在嵌入式与操作系统代码里很常见（"停在这里等看门狗/中断"）。[[P2809R3]] 在 [[stmt.iter.general#3]] 中定义了**平凡无限循环**：循环体为空（`;` 或 `{}`）、控制表达式是求值为 `true` 的**常量表达式**的 `while`/`do`/`for`。它的循环体被视为替换成对 `std::this_thread::yield` 的调用，并作为 ¶1.6 列入"取得进展"的清单——不再是 UB。

```cpp
void spin()       { while (true) ; }                  // 平凡无限循环：C++26 中有定义
void spin2(int n) { while (n) ; }                     // 条件不是常量表达式：n != 0 时仍是 UB
void spin3()      { for (int i = 1; i > 0; ) { } }    // 同上：不是平凡无限循环
```

本机 Clang 23 的结果（`-std=c++23` 与 `-std=c++2c` 完全相同）：

```text
__Z4spinv:       LBB0_1: b LBB0_1      ; 保留为真正的死循环
__Z5spin2i:      ret                   ; 循环被删除：n != 0 时直接返回
__Z5spin3v:      brk #0x1              ; 推出"必然 UB"，生成陷阱指令
```

Clang 早在 P2809 之前就把条件为常量的空循环保留下来，所以 `spin` 在各语言模式下都是死循环——这里标准是向实践看齐。`spin3` 最有意思：编译器证明了它永不终止、无副作用，于是这条路径"不可达"，在 Darwin 上落成一条 `brk` 陷阱指令。

### 调用"从未被调用"的函数

```cpp run title="never-called.cpp" ub
#include <cstdio>
static void (*action)() = nullptr;
static void format_disk() { std::puts("formatting disk..."); }
void never_called() { action = format_disk; }
int main() { action(); }          // 调用空函数指针：UB
```

```text
$ clang++ -std=c++2c -O0 never-called.cpp && ./a.out ; echo $?
139                                  # SIGSEGV
$ clang++ -std=c++2c -O2 never-called.cpp && ./a.out
formatting disk...
```

`action` 是内部链接的，只可能被赋值为 `nullptr` 或 `format_disk`。调用空指针是 UB，所以在任何有定义的执行中，`action` 在 `main` 里只能是 `format_disk`——优化器于是把间接调用改成了直接调用。从未被调用的函数"被执行了"。

## "时间旅行"与可观察检查点

UB 的影响不只向后。C++23 的 [intro.abstract]/5 明确写着：若一次执行包含未定义操作，标准对执行该程序的实现不施加任何要求，"甚至对第一个未定义操作**之前**的操作也不施加要求"。这就是所谓的**时间旅行**：编译器从"之后会 UB"反推"这条路径不会被走到"，从而改变之前的行为。

```cpp run title="time-travel.cpp" ub
#include <cstdio>
[[gnu::noinline]] int div_report(int a, int b, bool& was_zero) {
  was_zero = (b == 0);   // 先记录
  return a / b;          // 后除法：b == 0 时 UB
}
int main(int argc, char**) {
  bool z;
  int q = div_report(7, argc - 1, z);   // 不带参数运行：b == 0
  std::printf("q=%d was_zero=%d\n", q, z);
}
```

```text
-O0                          q=0 was_zero=1
-O2                          q=0 was_zero=0
-O2 -fsanitize=undefined     time-travel.cpp:4:12: runtime error: division by zero
                             q=0 was_zero=1
```

`-O2` 下 `div_report` 被编译成：

```text
	strb	wzr, [x2]        ; was_zero = false —— 无条件！
	sdiv	w0, w0, w1
	ret
```

除法**之后**的 UB 改写了除法**之前**那次赋值的结果：既然 `a / b` 执行了，`b` 就不可能是 0，所以 `b == 0` 是 `false`。（ARM64 的 `sdiv` 除以零得 0 而不陷入，所以程序没有崩溃，安静地给出了错误的答案。）

### C++26 的护栏：定义前缀 {{c++26}}

[[P1494]] 引入了**可观察检查点**（[[intro.abstract#5]]）和执行的**定义前缀**（[[intro.abstract#6]]）：只有被某个检查点与**所有**未定义操作隔开的操作才在定义前缀中，实现必须如实产生定义前缀的**可观察行为**。调用 `std::observable_checkpoint()`、把数据真正交付给宿主环境（如 `fflush` 返回）都是检查点。完整的规则、缓冲的细节和例子见 [[intro.compliance]]。

把它套到上例：

- `was_zero = …` 是对普通内存的写，**不是可观察行为**（可观察行为只有 volatile 访问、交付给文件的数据、交互设备的 I/O，[[intro.abstract#8]]）。所以即使在 C++26 下，`-O2` 的结果也完全合规——检查点保护的只是"已经被外界看到的东西"。
- 如果在 UB 之前有一次 `std::printf` 并 `std::fflush(stdout)`，那么这次输出**必须**出现，编译器不得以"之后会 UB"为由抹去它。

!!! impl
    截至写作时，本机 Clang 23 自带的 libc++ 尚未提供 `std::observable_checkpoint`（头文件中查不到该名字）。实践中，Clang 对可能不返回的外部调用（如 `fprintf`）本来就不做跨调用的时间旅行——把上例中的 `was_zero = …` 换成 `if (b == 0) fprintf(stderr, …);`，`-O2` 仍会保留那次输出。检查点把这种"实践中的克制"变成了标准的保证。

## 错误行为：C++26 的第三条路 {{c++26}}

[[P2795R5]] 引入了**错误行为**（erroneous behavior，EB，[[intro.defs]] 3.21）："行为有定义，但实现被建议诊断"。第一个、也是目前核心语言中最主要的应用是**未初始化的自动变量**（[[basic.indet]]）：其字节具有**错误值**——由实现决定、**与程序状态无关**的值；读取它是错误行为而不是 UB。

| | UB | EB |
|---|---|---|
| 程序行为 | 无任何要求 | 有定义（读出某个固定的错误值） |
| 实现可以诊断吗 | 可以 | 可以，且**建议**诊断（允许误报） |
| 实现可以终止吗 | 可以 | 可以 |
| 优化器能假设它不发生吗 | **能** | **不能** |
| 之前的可观察行为 | 检查点之前的受保护 | 全部受保护 |
| 常量求值中 | 使表达式非常量 | 同样使表达式非常量（[[expr.const.core#2]] ¶2.8） |

区别在"优化器能否假设它不发生"。看本机 Clang 23 对下面这个函数做了什么：

```cpp eb
int f(bool b) {
  int x;            // C++26：x 具有错误值
  if (b) x = 1;
  return x;         // b 为 false 时：错误行为（C++23：UB）
}
```

```text
-std=c++2c -O2                              mov w0, #1 ; ret           ← 无论 b 都返回 1
-std=c++2c -O2 -ftrivial-auto-var-init=pattern
                                            b ? 1 : 0xAAAAAAAA
-std=c++2c -O2 -ftrivial-auto-var-init=zero  b ? 1 : 0
```

默认配置下，Clang 仍把"读未初始化变量"当作 UB 来优化：既然 `b == false` 那条路径读到的是"任意值"，就选 `1`，让两条路径合并。这个"错误值"恰好等于程序在另一条路径上写入的值——它**依赖于程序本身**，与 [[basic.indet#1]] 要求的"独立于程序状态"不符。也就是说，截至本文，Clang 23 在 `-std=c++2c` 下尚未实现 EB 的语义；`-ftrivial-auto-var-init=pattern`/`zero` 产生的才是 EB 设想的行为（固定的、与程序无关的值）。编译期的 `-Wsometimes-uninitialized` 警告则早已存在，它正是 EB "建议诊断"的样子。

想退出 EB（例如为了性能，明确知道一个大缓冲区会在读之前被填满），C++26 提供 `[[indeterminate]]`（[[dcl.attr.indet]]），被标注的变量回到"不确定值、读取即 UB"的旧语义。

## 常量求值：编译期的 UB 探测器

常量求值器是一台严格执行抽象机规则的解释器。[[expr.const.core#2]] ¶2.8 规定：若求值会执行第 4 到 15 章规定的**未定义或错误行为**的操作，表达式就**不是**核心常量表达式。在要求常量表达式的地方（`static_assert`、`constexpr` 变量、模板实参），这意味着**必须诊断**：

```cpp run title="consteval-ub.cpp" error
#include <climits>
constexpr int add(int a, int b) { return a + b; }
constexpr int at(const int* p, int i) { return p[i]; }
constexpr int sum4() {
  int a[4] = {1, 2, 3, 4};
  int s = 0;
  for (int i = 0; i <= 4; ++i) s += a[i];   // 差一错误
  return s;
}
constexpr const int& dangle() { int x = 1; return x; }
constexpr int arr[3] = {1, 2, 3};
static_assert(add(INT_MAX, 1) > 0);
static_assert(at(arr, 3) == 0);
static_assert(sum4() == 10);
static_assert(dangle() == 1);
```

本机 Clang 23 的诊断（节选）：

```text
note: value 2147483648 is outside the range of representable values of type 'int'
note: read of dereferenced one-past-the-end pointer is not allowed in a constant expression
note: read of dereferenced one-past-the-end pointer is not allowed in a constant expression
note: read of object outside its lifetime is not allowed in a constant expression
```

这是一个被低估的测试手段：把核心算法写成 `constexpr`，再用 `static_assert` 在编译期跑几组用例，等于免费得到一个**对核心语言 UB 零漏报**的检查器（只对实际执行到的路径）。局限：

- **库 UB 不保证被发现**：违反库前置条件时是否为常量表达式是**未指定**的（[[expr.const.core#4]]）。
- **runtime-undefined 行为**（如违反 `[[assume]]`）是否被诊断由实现定义（¶3）。
- `reinterpret_cast`、`memcpy`、内联汇编等根本不能出现在常量求值中，涉及它们的 UB（如严格别名）无从检测——见 [[topics/type-punning]]。

## 运行期工具：Sanitizer

| 工具 | 开关 | 检测 | 本机可用 | 典型开销 |
|---|---|---|---|---|
| UBSan | `-fsanitize=undefined` | 有符号溢出、移位越界、空指针、未对齐、数组越界（静态大小）、`unreachable`、非法 `enum`/`bool` 值、vptr 类型错误…… | 是 | 低 |
| ASan | `-fsanitize=address` | 堆/栈/全局越界、use-after-free、use-after-scope、use-after-return、double free | 是 | ~2× |
| MSan | `-fsanitize=memory` | 读取未初始化内存 | **否**（Clang 23 报 "unsupported option '-fsanitize=memory' for target 'arm64-apple-darwin25.5.0'"；仅 Linux 等平台） | ~3× |
| TSan | `-fsanitize=thread` | 数据竞争（[[intro.races#17]]） | 是 | 5–15× |
| TySan | `-fsanitize=type` | 严格别名违反（[[basic.lval#11]]） | 是 | 高 |

UBSan 的输出（`-O0 -fsanitize=undefined`）：

```text
ub1.cpp:6:27: runtime error: signed integer overflow: 2147483647 + 1 cannot be represented in type 'int'
ub1.cpp:7:25: runtime error: shift exponent 32 is too large for 32-bit type 'int'
ub1.cpp:8:23: runtime error: index 4 out of bounds for type 'int[4]'
```

TSan 对一个两线程无锁自增的程序：

```text
WARNING: ThreadSanitizer: data race (pid=8655)
  Write of size 4 at 0x0001044b8090 by thread T1:
    #0 ... std::__1::__thread_proxy<...main::$_0...>(void*) ...
  Previous write of size 4 at 0x0001044b8090 by main thread:
    #0 main ...
  Location is global 'counter' at 0x0001044b8090 (race+0x10000c090)
```

ASan 的各类报告见 [[topics/dangling-references]]。使用要点：

- **组合限制**：ASan 与 TSan、ASan 与 MSan 互斥（Clang：`'-fsanitize=address' not allowed with '-fsanitize=thread'`）；UBSan 可以和任何一个组合。
- **只能发现执行到的 UB**。sanitizer 是动态工具，覆盖率取决于测试。
- **插桩会改变优化**。上文时间旅行的例子在 UBSan 下打印 `was_zero=1`——不仅报告了 UB，还"顺便"改变了程序行为。不要用"开 sanitizer 时没问题"证明"不开时没问题"。
- `-fsanitize-trap=undefined` 让 UBSan 在检测到问题时直接执行陷阱指令，不需要运行时库，可以用于生产环境的最小加固。

## 加固：把库 UB 变成确定的终止

C++26 承认了一种实现形态：**加固实现**（hardened implementation，[[intro.compliance.general#8]]，[[P3471]]）。标准库函数可以规定**加固前置条件**；在加固实现中违反它们会导致**契约违反**并终止，而不是 UB。`vector::operator[]`、`span::operator[]`、`optional::operator*`、`string_view::front()` 等都有这样的前置条件。

libc++ 通过 `_LIBCPP_HARDENING_MODE` 宏选择加固级别。本机 libc++ 头文件 `__configuration/hardening.h` 中定义的取值：

| 取值 | 含义（据头文件注释） |
|---|---|
| `_LIBCPP_HARDENING_MODE_NONE` | 关闭所有运行期加固检查 |
| `_LIBCPP_HARDENING_MODE_FAST` | 只开启安全关键、常数时间、开销很低的检查 |
| `_LIBCPP_HARDENING_MODE_EXTENSIVE` | FAST 的超集，加上开销较低、防止常见逻辑错误的检查 |
| `_LIBCPP_HARDENING_MODE_DEBUG` | 全部检查，包括内部断言；开销可能很大，用于测试 |

```cpp run title="hardening.cpp" ub
#include <cstdio>
#include <vector>
int main(int argc, char**) {
  std::vector<int> v{1, 2, 3};
  std::printf("%d\n", v[argc + 2]);    // 越界：违反 operator[] 的加固前置条件
}
```

```text
-O2                                                     0            （UB：读到了垃圾）
-O2 -D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_FAST       退出码 133（SIGTRAP）
-O2 -D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_EXTENSIVE  退出码 133（SIGTRAP）
-O2 -D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_DEBUG
    vector.h:414: libc++ Hardening assertion __n < size() failed: vector[] index out of bounds
                                                        退出码 134（SIGABRT）
```

检查失败后的动作由**断言语义**决定，与 C++26 契约的求值语义对应：`_LIBCPP_ASSERTION_SEMANTIC_IGNORE`、`_OBSERVE`、`_QUICK_ENFORCE`（陷阱）、`_ENFORCE`（记录后终止）。不显式指定时，FAST/EXTENSIVE 用 quick-enforce、DEBUG 用 enforce——正是上面看到的 SIGTRAP 与 SIGABRT 的区别。头文件注释说明，用户自选断言语义目前是**实验性**功能（需要启用 libc++ 的实验库），且 `ignore` 语义不构成合规的加固实现。

libstdc++ 的对应开关是 `-D_GLIBCXX_ASSERTIONS`。

## 程序员主动引入的 UB

UB 不只是"错误"，它也是向编译器传递信息的手段。C++23 提供了两个标准化的工具：

```cpp ok
#include <utility>
int half(int x)     { return x / 2; }
int half_pos(int x) { [[assume(x >= 0)]]; return x / 2; }   // 假设为假：runtime-undefined
int pick(int k) {
  switch (k) {
    case 0: return 10;
    case 1: return 20;
    default: std::unreachable();                             // 到达即 UB
  }
}
```

```text
__Z4halfi:        add w8, w0, w0, lsr #31 ; asr w0, w8, #1    ; 负数向零取整的修正
__Z8half_posi:    lsr w0, w0, #1                              ; 修正被省掉
__Z4picki:        cmp w0, #0 ; csel w0, w9(10), w8(20), eq    ; 没有边界检查与跳转表
```

`[[assume(E)]]`（[[dcl.attr.assume]]）：`E` 不求值；若它在该点会求值为 `false`，行为是 **runtime-undefined**。`std::unreachable()`（[[utility.undefined]]）：前置条件是 "false is true"，调用即 UB。两者都是把"我保证这不会发生"翻译成编译器能用的前提——用错了，就是你亲手写下的 UB。

## 思考题

!!! question "1"
    为什么 `unsigned` 循环变量有时会让循环**变慢**？

<details markdown="1">
<summary>答案</summary>

无符号回绕是有定义的。对 `for (unsigned i = start; i != end; ++i) a[i] = …;` 这类循环，编译器必须考虑 `i` 从 `UINT_MAX` 回绕到 0 的可能，在 64 位平台上不能把 `i` 直接提升为 64 位的地址偏移，也难以证明循环次数；有符号 `int` 因为溢出是 UB，就没有这个顾虑。这是"UB 带来性能"最常被引用的例子。实践中用 `std::size_t`（与指针等宽）作索引可以同时避免两种问题。
</details>

!!! question "2"
    C++26 引入可观察检查点之后，"时间旅行"是不是就不存在了？

<details markdown="1">
<summary>答案</summary>

没有。定义前缀只保护**可观察行为**，并且只保护被检查点与 UB 隔开的那部分。上文 `div_report` 的例子在 C++26 下依然可以输出 `was_zero=0`：对 `was_zero` 的写入不是可观察行为，而读出它的 `printf` 在 UB **之后**。检查点只阻止"已经交付给外界的输出被抹掉"，不阻止编译器基于未来的 UB 重写之前的计算。
</details>

!!! question "3"
    一个 `constexpr` 函数在 `static_assert` 里跑通了，能说明它在运行期没有 UB 吗？

<details markdown="1">
<summary>答案</summary>

只能说明**对那组实参、在那条执行路径上**没有核心语言 UB 和错误行为（[[expr.const.core#2]] ¶2.8）。其他实参可能走其他路径；库前置条件的违反不保证被诊断（¶4）；运行期分支（`if consteval`、`std::is_constant_evaluated()`）可能执行完全不同的代码。它是一个强有力的单元测试，不是证明。
</details>

## 小结

!!! summary
    - 标准说 UB 是"不施加任何要求"；编译器把它当作**推理前提**——"程序不会执行 UB"——并据此删除检查、折叠比较、删除循环、改写间接调用。
    - UB 的影响可以**向前**传播（时间旅行）。C++26 的可观察检查点只保护被检查点隔开的**可观察行为**，不保护普通计算。
    - **错误行为**是有定义的错误：可以诊断、可以终止，但**不能被优化器假设不发生**。截至本文，Clang 23 的默认代码生成仍按 UB 对待未初始化读取；`-ftrivial-auto-var-init` 提供了 EB 式的行为。
    - **常量求值**是零漏报的 UB 探测器（针对核心语言、针对实际路径）；**sanitizer** 是运行期探测器（UBSan、ASan、TSan、TySan；MSan 仅部分平台）；**加固模式**把最常见的库 UB 变成确定的终止。
    - 显式 UB 的完整清单在 Annex F [[ub]]；行为分类的定义在 [[intro.defs]]；实现义务在 [[intro.compliance]]。
