---
title: 未定义行为：标准视角与编译器视角
summary: 标准说 UB 是不施加任何要求的行为，编译器把它读作可以假设不会发生；本页用 Clang -O2 的真实输出说明这会造成什么后果，C++26 怎样给它设边界，以及怎样检测和缓解。
status: done
order: 5
since: c++98
papers: P1494, P2795R5, P2809R3, P3471
related: intro.defs, intro.compliance, intro.progress, stmt.iter.general, basic.indet, expr.const.core, dcl.attr.assume, utility.undefined, ub, topics/type-punning, topics/dangling-references, topics/object-model
tags: UB, 优化, sanitizer, 加固, 错误行为, 专题
updated: 2026-10-19
---

!!! tldr
    - 标准对 UB 不施加任何要求；优化器据此假设正确的程序不会执行 UB，然后删除检查、折叠比较、删除循环。
    - UB 的影响可以作用到它之前的代码。C++26 的可观察检查点只保护检查点之前已经产生的可观察行为，不保护普通的计算。
    - C++26 的错误行为（读未初始化的局部变量）有定义，优化器不能假设它不发生；但截至写作时 Clang 默认仍按 UB 处理它。
    - 常量求值会拒绝核心语言 UB，是编译期的检测手段；运行期用 UBSan、ASan、TSan、TySan，标准库 UB 用加固模式变成确定的终止。
    - `[[assume]]` 和 `std::unreachable()` 是程序员主动写下的 UB，用来向优化器传递信息。

## 两种读法

```cpp
bool always(int x) { return x + 1 > x; }
```

本机 Clang 23 `-O2` 把这个函数编译成 `return true;`。`x == INT_MAX` 时 `x + 1` 溢出，看起来结果应该是假，编译器却没有考虑这种情况。

原因在 UB 的定义里。**未定义行为**（undefined behavior，UB）是本文档对其不施加任何要求的行为（[[defns.undefined]]）。这句话有两种读法：

- 标准的读法是消极的：这里标准不作规定，实现可以忽略它，可以按平台的方式做一件有文档的事，也可以终止程序。
- 编译器的读法是积极的：正确的程序不会执行 UB，所以优化时可以假设 UB 不会发生，并据此推出关于程序的结论。

`always` 就是第二种读法的产物：如果 `x + 1` 不溢出，`x + 1 > x` 成立；如果溢出，就是 UB，返回什么都符合标准。两种情况下返回 `true` 都正确。几乎所有让人意外的 UB 现象都来自这种推理。

## UB 在行为分类中的位置

| 类别 | 什么时候发生 | 实现的义务 | 例子 |
|---|---|---|---|
| 非良构（ill-formed） | 编译期 | 至少一条诊断 | 类型不匹配 |
| 非良构、不要求诊断（IFNDR） | 编译期，常跨翻译单元 | 无，程序没有任何意义 | 违反 ODR |
| 实现定义（implementation-defined） | 运行期 | 从允许的行为中选一种，写进文档 | `sizeof(int)` |
| 未指定（unspecified） | 运行期 | 从允许的行为中选一种，不必写文档 | 函数实参的求值顺序 |
| 错误行为（erroneous）{{c++26}} | 运行期 | 行为有定义；建议诊断，可以终止 | 读未初始化的自动变量 |
| 未定义（undefined） | 运行期 | 无 | 有符号溢出、空指针解引用 |
| 运行期未定义（runtime-undefined） | 运行期 | 同 UB；常量求值中是否因此视为非常量由实现定义 | 违反 `[[assume]]` |

精确定义见 [[intro.defs]]，它们怎样转化为对实现的要求见 [[intro.compliance]]。关于 UB 本身，还要区分三种来源：

- **显式 UB**：标准用 "the behavior is undefined" 之类的措辞写明。资料性附录 Annex F [[ub]] 把核心语言的显式 UB 汇编成表，每条有一个稳定标识，例如严格别名违反是 `[ub:expr.basic.lvalue.strict.aliasing.violation]`。
- **隐式 UB**：标准没有给出任何定义的情形，同样是 UB（定义的注 1）。这类 UB 不在附录中。
- **库 UB**：违反库函数的前置条件（*Preconditions*）是 UB（[[structure.specifications#3]] ¶3.4）。`vector::operator[]` 越界、给 `std::sort` 一个不满足严格弱序的比较器都属于此类。加固模式主要针对它们。

## 编译器怎样利用 UB

优化器并不是在利用程序的错误，它只是在推理时用上了程序没有 UB 这个前提。下面每个例子都是本机 `clang++ -std=c++2c -O2`（arm64）的真实产物。

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

`count` 更有代表性。编译器假设 `i` 不会溢出，于是断定循环一定终止，并且恰好执行 `n + 1` 次，整个循环被一个公式取代。`n == INT_MAX` 时 `++i` 会溢出，这个输入不在编译器的考虑范围内。

在实际代码中，这条规则最大的收益来自 64 位平台上的 `int` 循环变量。它不会回绕，所以编译器可以把它提升为 64 位的地址偏移，而不必每次迭代都做符号扩展。

`-fwrapv` 让有符号运算按补码回绕，把这种 UB 变成有定义的行为，是合规的扩展（[[intro.compliance.general#11]]）。用它编译，`always` 变回 `x != INT_MAX` 的比较。

### 空指针检查被删除

```cpp
int read(int* p) {
  int v = *p;            // 若 p 为空：UB
  if (p == nullptr)      // 编译器：上面已经解引用了，p 必不为空
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

判空被整个删掉了。Linux 内核出过这种模式的漏洞：先解引用、后判空，判空被优化掉，而内核里地址 0 可能被映射，解引用并不崩溃。内核此后改用 `-fno-delete-null-pointer-checks` 编译。

### 没有副作用的无限循环

[[intro.progress#1]] 允许实现假设每个线程最终都会做下列事情之一：终止、调用 `std::this_thread::yield`、调用库 I/O 函数、进行 volatile 访问、执行原子或同步操作，或者继续执行一个平凡无限循环（见下文）。一个什么都不做又不终止的循环违反了这个假设，编译器可以认为它不会无限执行下去：

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

`fermat` 被编译成 `mov w0, #1; ret`。推理过程是：循环唯一的出口是 `return true`；循环没有可观察的副作用，按 [[intro.progress#1]] 它必须终止；所以函数必然返回 `true`。实际上 1000 以内的立方和不超出 32 位，不会因回绕产生伪解，这个循环永远不会终止。

#### 平凡无限循环 {{c++26}}

`while (true);` 这种有意的死循环在嵌入式和操作系统代码里很常见，例如停在这里等看门狗或中断。[[P2809R3]] 在 [[stmt.iter.general#3]] 中定义了**平凡无限循环**（trivial infinite loop）：循环体为空（`;` 或 `{}`），控制表达式是求值为 `true` 的常量表达式。它的循环体视为替换成对 `std::this_thread::yield` 的调用，执行它也算取得进展（[[intro.progress#1]] ¶1.6），所以不再是 UB。

```cpp
void spin()       { while (true) ; }                  // 平凡无限循环：C++26 中有定义
void spin2(int n) { while (n) ; }                     // 条件不是常量表达式：n != 0 时仍是 UB
void spin3()      { for (int i = 1; i > 0; ) { } }    // 同上：不是平凡无限循环
```

本机 Clang 23 的结果，`-std=c++23` 与 `-std=c++2c` 相同：

```text
__Z4spinv:       LBB0_1: b LBB0_1      ; 保留为真正的死循环
__Z5spin2i:      ret                   ; 循环被删除：n != 0 时直接返回
__Z5spin3v:      brk #0x1              ; 推出必然 UB，生成陷阱指令
```

Clang 在 P2809 之前就保留条件为常量的空循环，所以 `spin` 在各语言模式下都是死循环，这里是标准向实践看齐。`spin3` 被证明永不终止且没有副作用，于是这条路径不可达，在 Darwin 上生成一条 `brk` 陷阱指令。

### 调用从未被调用的函数

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

`action` 具有内部链接，只可能被赋值为 `nullptr` 或 `format_disk`。调用空指针是 UB，所以在任何有定义的执行中，`main` 里的 `action` 只能是 `format_disk`。优化器于是把间接调用改成了直接调用，一个从未被调用的函数被执行了。

## UB 影响之前的代码

UB 的影响不只作用在它之后。C++23 的 [intro.abstract] 写明，如果一次执行包含未定义操作，标准对执行这个程序的实现不施加任何要求，甚至对第一个未定义操作之前的操作也不施加要求。这常被称为**时间旅行**：编译器从之后会发生 UB 反推这条路径不会走到，从而改变之前的行为。

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
	strb	wzr, [x2]        ; was_zero = false，无条件
	sdiv	w0, w0, w1
	ret
```

除法之后的 UB 改写了除法之前那次赋值的结果：既然执行了 `a / b`，`b` 就不可能是 0，所以 `b == 0` 为假。ARM64 的 `sdiv` 除以零得 0 而不陷入，所以程序没有崩溃，只是安静地给出了错误的答案。

### 可观察检查点 {{c++26}}

[[P1494]] 引入了**可观察检查点**（observable checkpoint，[[intro.abstract#5]]）和执行的**定义前缀**（defined prefix，[[intro.abstract#6]]）。一个操作只要与之后的每个未定义操作之间都隔着检查点，就在定义前缀里，实现必须如实产生定义前缀中的可观察行为。调用 `std::observable_checkpoint()`、把数据真正交付给宿主环境（例如 `fflush` 返回）都是检查点。完整的规则和缓冲区的细节见 [[intro.compliance]]。

套用到上面的例子：

- `was_zero = …` 是对普通内存的写，不是可观察行为。可观察行为只有 volatile 访问、交付给文件的数据和交互设备上的 I/O（[[intro.abstract#8]]）。所以即使在 C++26 下，`-O2` 的结果也完全符合标准。
- 如果 UB 之前有一次 `std::printf` 并接着 `std::fflush(stdout)`，这次输出就必须出现，编译器不能以之后会发生 UB 为由抹去它。

!!! impl
    截至写作时，本机 Clang 23 自带的 libc++ 还没有提供 `std::observable_checkpoint`。实践中，Clang 对可能不返回的外部调用（如 `fprintf`）本来就不做跨调用的时间旅行：把上例的 `was_zero = …` 换成 `if (b == 0) std::fprintf(stderr, …);`，`-O2` 下那次输出仍然保留。检查点把这种实践中的克制变成了标准的保证。

## 错误行为 {{c++26}}

[[P2795R5]] 引入了**错误行为**（erroneous behavior，EB，[[defns.erroneous]]）：标准认定是错误，但仍然给出了定义的行为，并建议实现诊断。核心语言中最主要的应用是未初始化的自动变量（[[basic.indet]]）：它的字节具有**错误值**（erroneous value），由实现决定且与程序状态无关，读取它是错误行为而不是 UB。

| | UB | EB |
|---|---|---|
| 程序行为 | 无任何要求 | 有定义，读出那个错误值 |
| 实现可以诊断吗 | 可以 | 可以，而且建议诊断（允许误报） |
| 实现可以终止吗 | 可以 | 可以 |
| 优化器能假设它不发生吗 | 能 | 不能 |
| 之前的可观察行为 | 只有检查点之前的受保护 | 全部受保护 |
| 常量求值中 | 使表达式不是常量 | 同样使表达式不是常量（[[expr.const.core#2]] ¶2.8） |

一个例外：错误值对这个类型无效时（例如 `bool` 的某些位模式），左值到右值转换仍是 UB（[[basic.indet#1]] 注 1）。

关键的区别是优化器能否假设它不发生。看本机 Clang 23 对下面这个函数做了什么：

```cpp eb
int f(bool b) {
  int x;            // C++26：x 具有错误值
  if (b) x = 1;
  return x;         // b 为 false 时：错误行为（C++23：UB）
}
```

```text
-std=c++2c -O2                                 mov w0, #1 ; ret      不论 b 都返回 1
-std=c++2c -O2 -ftrivial-auto-var-init=pattern b ? 1 : 0xAAAAAAAA
-std=c++2c -O2 -ftrivial-auto-var-init=zero    b ? 1 : 0
```

默认配置下，Clang 仍把读未初始化变量当作 UB 来优化：`b == false` 那条路径读到的值可以是任意值，就选 1，让两条路径合并。单看这个例子还有争议：一个固定的 1 也许可以算作"与程序状态无关"的实现选定值（[[basic.indet#1]]）。更明确的证据是 `int x; return x;` 直接返回寄存器里残留的值，以及栈上残留的旧数据能被读出来（见 [[papers/erroneous-behaviour]]），这些都取决于程序状态。所以截至写作时，Clang 23 在 `-std=c++2c` 下还没有实现 EB 的语义；`-ftrivial-auto-var-init=pattern` 或 `zero` 产生的才是 EB 预期的行为。编译期的 `-Wsometimes-uninitialized` 警告早已存在，正是建议诊断的一种形式。

如果明确知道一个大缓冲区会在读取前被填满，想省掉初始化的开销，可以用 C++26 的 `[[indeterminate]]`（[[dcl.attr.indet]]）退出 EB。被标注的变量回到旧的语义：值不确定，读取即 UB。

## 程序员主动写下的 UB

UB 也可以用来向编译器传递信息。C++23 提供了两个标准化的工具：

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
__Z4picki:        cmp w0, #0 ; csel w0, w9(10), w8(20), eq    ; 没有边界检查和跳转表
```

`[[assume(E)]]`（[[dcl.attr.assume]]）中的 `E` 不求值；如果它在该处会求值为 `false`，行为是运行期未定义。`std::unreachable()`（[[utility.undefined]]）的前置条件是 false 为 true，所以调用它就是 UB。两者都把我保证这不会发生翻译成编译器能用的前提。保证不成立时，就是自己亲手写下的 UB。

## 检测与缓解

### 常量求值：编译期的检测器

常量求值器严格按抽象机的规则执行。[[expr.const.core#2]] ¶2.8 规定，如果求值会执行第 4 到 15 章规定的未定义或错误行为，表达式就不是核心常量表达式。在要求常量表达式的地方（`static_assert`、`constexpr` 变量、模板实参），这意味着编译器必须报错：

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

把核心算法写成 `constexpr`，再用 `static_assert` 在编译期跑几组用例，就能对实际执行到的路径检查出全部核心语言 UB。它有三个局限：

- 库 UB 不一定被发现：违反库前置条件时，表达式是否为核心常量表达式是未指定的（[[expr.const.core#4]]）。
- 运行期未定义行为（如违反 `[[assume]]`）是否被诊断由实现定义（[[expr.const.core#3]]）。
- `reinterpret_cast`、`memcpy`、内联汇编根本不能出现在常量求值中，涉及它们的 UB（如严格别名）无从检测，见 [[topics/type-punning]]。

### 运行期：sanitizer

| 工具 | 开关 | 检测 | 本机可用 | 典型开销 |
|---|---|---|---|---|
| UBSan | `-fsanitize=undefined` | 有符号溢出、移位越界、空指针、未对齐、静态大小数组越界、`unreachable`、非法 `enum`/`bool` 值、vptr 类型错误等 | 是 | 低 |
| ASan | `-fsanitize=address` | 堆、栈、全局越界，use-after-free、use-after-scope、use-after-return，double free | 是 | 约 2× |
| MSan | `-fsanitize=memory` | 读取未初始化内存 | 否，只支持 Linux 等平台 | 约 3× |
| TSan | `-fsanitize=thread` | 数据竞争（[[intro.races#17]]） | 是 | 5–15× |
| TySan | `-fsanitize=type` | 严格别名违反（[[basic.lval#11]]） | 是 | 高 |

本机 Clang 23 对 MSan 报 "unsupported option '-fsanitize=memory' for target 'arm64-apple-darwin25.5.0'"。

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

ASan 的各类报告见 [[topics/dangling-references]]。使用时要注意：

- ASan 与 TSan、ASan 与 MSan 不能同时开启（Clang：`'-fsanitize=address' not allowed with '-fsanitize=thread'`），UBSan 可以和任何一个组合。
- sanitizer 是动态工具，只能发现实际执行到的 UB，覆盖率取决于测试。
- 插桩会改变优化。上文时间旅行的例子在 UBSan 下打印 `was_zero=1`，不仅报告了 UB，还改变了程序的行为。所以开 sanitizer 时没问题，不能证明不开时也没问题。
- `-fsanitize-trap=undefined` 让 UBSan 检测到问题时直接执行陷阱指令，不需要运行时库，可以作为生产环境的最小加固。

### 加固：把库 UB 变成确定的终止

C++26 承认了一种实现形态：**加固实现**（hardened implementation，[[intro.compliance.general#8]]，[[P3471]]）。标准库函数可以规定加固前置条件，在加固实现中违反它们会导致契约违反并终止，而不是 UB（[[structure.specifications#3]] ¶3.5）。`vector::operator[]`、`span::operator[]`、`optional::operator*`、`string_view::front()` 等都有这样的前置条件。

```cpp run title="hardening.cpp" ub
#include <cstdio>
#include <vector>
int main(int argc, char**) {
  std::vector<int> v{1, 2, 3};
  std::printf("%d\n", v[argc + 2]);    // 越界：违反 operator[] 的加固前置条件
}
```

libc++ 用宏 `_LIBCPP_HARDENING_MODE` 选择加固级别：

| 取值 | 含义（据 libc++ 头文件注释） | 上例的结果 |
|---|---|---|
| `_LIBCPP_HARDENING_MODE_NONE`（默认） | 关闭所有运行期加固检查 | 打印 0，读到了垃圾值 |
| `_LIBCPP_HARDENING_MODE_FAST` | 只开启安全关键、常数时间、开销很低的检查 | 退出码 133（SIGTRAP） |
| `_LIBCPP_HARDENING_MODE_EXTENSIVE` | FAST 的超集，加上开销较低、防止常见逻辑错误的检查 | 退出码 133（SIGTRAP） |
| `_LIBCPP_HARDENING_MODE_DEBUG` | 全部检查，包括内部断言；开销可能很大，用于测试 | 打印下面的消息，退出码 134（SIGABRT） |

```text
vector.h:414: libc++ Hardening assertion __n < size() failed: vector[] index out of bounds
```

检查失败后的动作由断言语义决定，与 C++26 契约的求值语义对应：`_LIBCPP_ASSERTION_SEMANTIC_IGNORE`、`_OBSERVE`、`_QUICK_ENFORCE`（陷阱）、`_ENFORCE`（记录后终止）。不显式指定时，FAST 和 EXTENSIVE 用 quick-enforce，DEBUG 用 enforce，这就是上面 SIGTRAP 与 SIGABRT 的区别。头文件注释说明，由用户选择断言语义目前是实验性功能，而且 ignore 语义不构成合规的加固实现。

libstdc++ 的对应开关是 `-D_GLIBCXX_ASSERTIONS`。

## 思考题

!!! question "思考题 1"
    为什么 `unsigned` 循环变量有时会让循环变慢？

<details markdown="1">
<summary>答案</summary>

无符号回绕是有定义的。对 `for (unsigned i = start; i != end; ++i) a[i] = …;` 这类循环，编译器必须考虑 `i` 从 `UINT_MAX` 回绕到 0 的可能，在 64 位平台上不能直接把 `i` 提升为 64 位的地址偏移，也难以算出循环次数。有符号 `int` 的溢出是 UB，没有这个顾虑。这是 UB 带来性能最常被引用的例子。实践中用与指针等宽的 `std::size_t` 作索引，可以同时避免两种问题。
</details>

!!! question "思考题 2"
    C++26 引入可观察检查点之后，时间旅行是不是就不存在了？

<details markdown="1">
<summary>答案</summary>

仍然存在。定义前缀只保护可观察行为，而且只保护被检查点与 UB 隔开的那部分。上文 `div_report` 的例子在 C++26 下依然可以输出 `was_zero=0`：对 `was_zero` 的写入不是可观察行为，而读出它的 `printf` 在 UB 之后。检查点只阻止已经交付给外界的输出被抹掉，不阻止编译器基于之后的 UB 改写之前的计算。
</details>

!!! question "思考题 3"
    一个 `constexpr` 函数在 `static_assert` 里跑通了，能说明它在运行期没有 UB 吗？

<details markdown="1">
<summary>答案</summary>

只能说明对那组实参、在那条执行路径上没有核心语言 UB 和错误行为（[[expr.const.core#2]] ¶2.8）。其他实参可能走其他路径；违反库前置条件不保证被诊断（[[expr.const.core#4]]）；`if consteval` 或 `std::is_constant_evaluated()` 分支在运行期可能执行完全不同的代码。它是一个有力的单元测试，不是证明。
</details>
