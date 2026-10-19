---
title: 读懂编译器生成的汇编
summary: 检查编译器把 C++ 变成了什么所需的最少汇编知识：怎样拿到汇编，AArch64 与 x86-64 的调用约定，常见 C++ 构造编译后的样子，以及怎样从汇编里找出多余的调用、寄存器溢出和没有向量化的循环。
group: 测量
status: draft
order: 20
since: c++98
related: intro.abstract, class.temporary, class.virtual, sequence.reqmts, intro.compliance.general, dcl.asm, toolchain/compilation-pipeline, toolchain/object-layout-and-vtables, toolchain/exception-implementation, toolchain/name-mangling, perf/compiler-optimizations, perf/vectorization
tags: 性能, 汇编, AArch64, x86-64, 调用约定, 代码生成
updated: 2026-10-19
---

!!! tldr
    - `clang++ -O2 -S x.cpp -o -` 输出汇编，`--target=x86_64-linux-gnu` 换成 x86-64；目标文件用 `llvm-objdump -d -C` 反汇编，修饰过的符号名用 `llvm-cxxfilt` 还原。
    - 参数和返回值放在寄存器里：AArch64 用 x0–x7 传参、x0 返回，x86-64 System V 用 rdi、rsi、rdx、rcx、r8、r9 传参、rax 返回。要活过一次调用的值放进被调用者保存寄存器，函数的序言和尾声负责保存、恢复它们。
    - 引用编译后就是指针；平凡可复制的小结构体拆进寄存器，带用户提供的复制构造函数的类按地址传；虚调用是两次加载加一次间接跳转；密集的 `switch` 可能变成跳转表。
    - 异常的正常路径上没有额外指令，清理代码放在函数末尾的着陆点里。libc++ 加固模式给 `operator[]` 加一次比较和一个分支，能提到循环外时几乎不花钱，提不出去时本机测得慢约 7%。
    - 看汇编主要找三样东西：意料之外的 `bl`/`call`（`memcpy`、`operator new`），标着 Spill/Reload 的栈读写，以及本该是向量指令却仍是标量指令的循环体。

## 拿到汇编

先看一个最小的函数：

```cpp godbolt title="square.cpp" flags="-std=c++2c -O2" ok
int square(int x) { return x * x; }
```

本机（Apple M2 Pro，Homebrew Clang 23.1.3）的两条命令，第一条生成原生 AArch64 汇编，第二条交叉编译到 x86-64 Linux，只生成汇编，不需要链接：

```bash
clang++ -std=c++2c -O2 -S square.cpp -o -
clang++ -std=c++2c -O2 -S --target=x86_64-linux-gnu square.cpp -o -
```

去掉以点开头的汇编器指令之后，剩下的是：

<div class="compare" markdown="1">

```asm title="AArch64"
__Z6squarei:            ; @_Z6squarei
; %bb.0:
  mul   w0, w0, w0
  ret
```

```asm title="x86-64（AT&T 语法）"
_Z6squarei:             # @_Z6squarei
# %bb.0:
  movl  %edi, %eax
  imull %edi, %eax
  retq
```

</div>

逐行读：

- `__Z6squarei:` 是**标签**（label），即函数入口的符号名。`_Z6squarei` 是 `square(int)` 修饰后的名字（规则见 [[toolchain/name-mangling]]），macOS 的 Mach-O 格式在所有 C 符号前再加一个下划线。
- `; %bb.0:` 是注释，标出 LLVM 内部的第 0 个**基本块**（basic block），即一段只从开头进入、只从结尾离开的直线代码。AArch64 汇编的注释以 `;` 开头（Linux 上的 AArch64 汇编用 `//`），x86-64 以 `#` 开头。
- AArch64 的 `w0` 是 64 位寄存器 `x0` 的低 32 位，`int` 是 32 位，所以用 `w`。参数从 `w0` 进来，结果也放回 `w0`。
- x86-64 的参数从 `edi` 进来，结果放在 `eax`。AT&T 语法把目的操作数写在最后，寄存器前加 `%`，指令后缀 `l` 表示 32 位、`q` 表示 64 位。加 `-masm=intel` 会改成 Intel 语法：目的在前，没有 `%` 和后缀（`mov eax, edi`、`imul eax, edi`）。

被去掉的那些行都是给汇编器和链接器看的：`.cfi_*` 描述栈帧，供异常回溯和调试器使用（见 [[toolchain/exception-implementation]]）；`.p2align` 是对齐；`.globl` 声明外部可见的符号。读代码时可以跳过它们。

<details class="fine" markdown="1"><summary>其他拿到汇编的方式</summary>

- Compiler Explorer。本站带 `godbolt ↗` 按钮的代码块一键在 Compiler Explorer 中打开，默认用 x86-64 上的 Clang trunk 和 GCC trunk；这里的按钮都带 `-O2`。它默认隐藏汇编器指令、给源码行和汇编行配色，也可以在编译器列表里加一个 ARM64 编译器做对照。
- 反汇编目标文件。`clang++ -O2 -g -c f.cpp` 之后，`llvm-objdump -d -C --no-show-raw-insn f.o` 反汇编，`-C` 顺便反修饰，`-S` 把源码行插在对应指令前（需要 `-g`），`-r` 显示重定位，即 `bl`/`call` 的目标还没填上时它要找哪个符号。macOS 自带的 `objdump` 是 Apple 的 LLVM 版本，用法相同。本机在 Mach-O 目标文件上反汇编时，第一个函数常被标成 `<ltmp0>` 而不是函数名；链接成可执行文件后再反汇编，或者直接用 `-S` 的输出即可。
- `-fverbose-asm`。本机 Clang 23 加不加这个选项输出完全相同，因为 Clang 的 `-S` 输出默认就带 `; @_Z6squarei`、`; %bb.0` 这类注释，`-fno-verbose-asm` 才会去掉。GCC 的同名选项会附加更多注释，可以在 Compiler Explorer 里对照。
- 反修饰。`llvm-cxxfilt` 和 `c++filt` 从标准输入读符号名，都能处理 Mach-O 多出的前导下划线：

```text
$ echo __Z6squarei | llvm-cxxfilt
square(int)
$ nm f.o | llvm-cxxfilt
```

</details>

下文的 AArch64 汇编取自本机 macOS，x86-64 汇编取自 `--target=x86_64-linux-gnu`。用到标准库头文件的例子在本机没有 Linux 的头文件和库，改用 `--target=x86_64-apple-macos`，两者使用同一套 x86-64 System V 调用约定，区别只在符号名的前导下划线和帧指针的默认设置。为了排版，列表里的 tab 换成了空格，删掉了汇编器指令和部分注释，指令本身没有改动。

## 一个函数的骨架

汇编里看不到形参名，只能看到寄存器。参数、返回值放在哪个寄存器，哪些寄存器在调用前后必须保持不变，由**调用约定**（calling convention）规定。它属于平台 ABI，不是 C++ 标准的内容；标准只要求程序的可观察行为与抽象机一致（[[intro.abstract#1]]），寄存器怎么分配完全由实现决定。

```cpp godbolt title="call.cpp" flags="-std=c++2c -O2" ok
long g(long);                 // 定义在别的 TU

long f(long a, long b) {
  long t = g(a);              // a 传给 g
  return t + b;               // b 要活过这次调用
}
```

<div class="compare" markdown="1">

```asm title="AArch64"
__Z1fll:
  stp  x20, x19, [sp, #-32]!
  stp  x29, x30, [sp, #16]
  add  x29, sp, #16
  mov  x19, x1        ; b 存进 x19
  bl   __Z1gl         ; a 已在 x0
  add  x0, x0, x19    ; g 的结果 + b
  ldp  x29, x30, [sp, #16]
  ldp  x20, x19, [sp], #32
  ret
```

```asm title="x86-64"
_Z1fll:
  pushq %rbx
  movq  %rsi, %rbx    # b 存进 rbx
  callq _Z1gl@PLT     # a 已在 rdi
  addq  %rbx, %rax    # g 的结果 + b
  popq  %rbx
  retq
```

</div>

`a` 本来就在第一个参数寄存器里，调用 `g` 时不用搬。`b` 在第二个参数寄存器里，但 `g` 可以随意改写参数寄存器，所以 `f` 先把 `b` 挪到一个 `g` 承诺不改的寄存器：AArch64 的 `x19`，x86-64 的 `rbx`。

这类寄存器叫**被调用者保存寄存器**（callee-saved）：哪个函数要用它，就由那个函数先把旧值存起来、返回前恢复。反过来，**调用者保存寄存器**（caller-saved）在调用之后可能被改掉，调用者要么不在里面放需要保留的值，要么自己先存好。所以 `f` 用 `x19` 之前要先保存它，这就是函数开头的**序言**（prologue）；返回前恢复它，这就是**尾声**（epilogue）。

AArch64 的 `bl` 把返回地址写进 `x30`（链接寄存器，lr），而不是压栈，所以一个还要调用别的函数的函数必须保存 `x30`。`x29` 是帧指针，`stp x29, x30, [sp, #16]` 加 `add x29, sp, #16` 是 Apple 平台上每个非叶函数都有的固定写法。`x20` 被一起保存只是因为 `stp` 一次存两个寄存器，并且栈要保持 16 字节对齐。

x86-64 的 `call` 把返回地址压栈。`pushq %rbx` 一方面保存 `rbx`，一方面让栈指针在下一次 `call` 时回到 16 字节对齐。本机 `--target=x86_64-linux-gnu -O2` 默认不保留帧指针，所以没有 `push rbp; mov rbp, rsp`。

| | AArch64（AAPCS64，Apple 平台） | x86-64 System V（Linux、macOS） |
|---|---|---|
| 整数、指针参数 | x0–x7 | rdi, rsi, rdx, rcx, r8, r9 |
| 浮点参数 | d0–d7（`float` 用 s0–s7） | xmm0–xmm7 |
| 整数返回值 | x0；16 字节的用 x0、x1 | rax；16 字节的用 rax、rdx |
| 浮点返回值 | d0 / s0 | xmm0 |
| 大对象返回 | 调用者在 x8 里给出存放结果的地址 | 调用者在 rdi 里给出地址，函数返回时放回 rax |
| 返回地址 | x30（lr） | 栈顶 |
| 被调用者保存 | x19–x28、x29（帧指针）、sp；d8–d15 | rbx、rbp、r12–r15、rsp |
| 调用者保存 | x0–x17（x18 为平台保留，不要用）；v0–v7、v16–v31，以及 v8–v15 的高 64 位 | rax、rcx、rdx、rsi、rdi、r8–r11；全部 xmm |
| 调用时栈对齐 | 16 字节 | 16 字节 |

<details class="fine" markdown="1"><summary>验证返回值约定的例子</summary>

```cpp godbolt title="ret.cpp" flags="-std=c++2c -O2" ok
struct P { long x, y; };
struct B { long a, b, c; };
P make_p(long v) { return {v, v + 1}; }
B make_b(long v) { return {v, v, v}; }
double half(double d, int) { return d / 2; }
```

<div class="compare" markdown="1">

```asm title="AArch64"
__Z6make_pl:
  add   x1, x0, #1     ; x0 不变
  ret
__Z6make_bl:
  stp   x0, x0, [x8]   ; 写到 x8 指处
  str   x0, [x8, #16]
  ret
__Z4halfdi:
  fmov  d1, #0.50000000
  fmul  d0, d0, d1
  ret
```

```asm title="x86-64"
_Z6make_pl:
  movq  %rdi, %rax
  leaq  1(%rdi), %rdx
  retq
_Z6make_bl:
  movq  %rdi, %rax     # 返回地址
  movq  %rsi, (%rdi)   # v 在 rsi
  movq  %rsi, 8(%rdi)
  movq  %rsi, 16(%rdi)
  retq
_Z4halfdi:
  mulsd .LCPI2_0(%rip), %xmm0
  retq
```

</div>

`make_b` 返回 24 字节的对象，x86-64 用 rdi 传结果地址，于是 `v` 挪到了 rsi。`d / 2` 被换成乘以 0.5，因为 0.5 能精确表示，两者对所有输入结果相同，这是 as-if 规则允许的变换。

</details>

`-O0` 下的汇编几乎没法用来判断性能：每个局部变量都放在栈上，每次使用都重新从栈里读。下面讨论的都是 `-O2` 的结果。

## C++ 构造编译后的样子

### 引用就是指针

```cpp godbolt title="ref.cpp" flags="-std=c++2c -O2" ok
void by_ref(int& r) { r += 1; }
void by_ptr(int* p) { *p += 1; }
```

两个函数的汇编一模一样：AArch64 是 `ldr w8, [x0]`、`add w8, w8, #1`、`str w8, [x0]`，x86-64 是一条 `incl (%rdi)`。引用形参在 ABI 里就是一个地址。标准说引用是否占存储是未指定的（[[dcl.ref#4]]），这给了编译器把局部的引用完全优化掉的自由，但跨函数边界传递时，它总要以某种形式传过去，主流 ABI 选的就是指针。

### 小结构体：寄存器还是内存

```cpp godbolt title="structs.cpp" flags="-std=c++2c -O2" ok
struct P {                    // 平凡可复制
  long x, y;
};
struct Q {                    // 用户提供的复制构造
  long x, y;
  Q(const Q& o) : x(o.x), y(o.y) {}
};
long sum_p(P p) { return p.x + p.y; }
long sum_q(Q q) { return q.x + q.y; }
```

<div class="compare" markdown="1">

```asm title="AArch64"
__Z5sum_p1P:
  add   x0, x0, x1      ; 两个成员在寄存器
  ret
__Z5sum_q1Q:
  ldp   x8, x9, [x0]    ; x0 是地址
  add   x0, x9, x8
  ret
```

```asm title="x86-64"
_Z5sum_p1P:
  leaq  (%rdi,%rsi), %rax
  retq
_Z5sum_q1Q:
  movq  8(%rdi), %rax   # rdi 是地址
  addq  (%rdi), %rax
  retq
```

</div>

`P` 和 `Q` 的布局完全相同，传法却不同。`P` 的两个成员直接放进两个参数寄存器；`Q` 由调用者在自己的栈上复制出一个对象，再把它的地址传进来。看调用者一侧就更清楚：

```cpp godbolt title="caller.cpp" flags="-std=c++2c -O2" ok
struct Q {
  long x, y;
  Q(const Q& o) : x(o.x), y(o.y) {}
};
long sum_q(Q q);
long call_q(const Q& q) { return sum_q(q); }
```

```asm title="AArch64"
__Z6call_qRK1Q:
  sub   sp, sp, #32
  stp   x29, x30, [sp, #16]
  add   x29, sp, #16
  ldr   q0, [x0]          ; 读 16 字节
  str   q0, [sp]          ; 在栈上复制出形参对象
  mov   x0, sp            ; 传它的地址
  bl    __Z5sum_q1Q
  ldp   x29, x30, [sp, #16]
  add   sp, sp, #32
  ret
```

原因在标准里。按值传参时，形参对象由实参初始化，它有自己的地址，复制构造函数可以把这个地址记下来。只有当类型的复制、移动构造函数都平凡，析构函数平凡或被弃置时，[[class.temporary#3]] 才允许实现多造几个临时对象来传递形参或返回值，也就是允许先拆进寄存器、到被调函数里再拼回一个对象。`Q` 有用户提供的复制构造函数，不满足这个条件，对象只能留在内存里按地址传。

!!! std
    if X is ... a class type that has at least one eligible copy or move constructor, where each such constructor is trivial, and the destructor of X is either trivial or deleted, implementations are permitted to create temporary objects to hold the function parameter or result object
    
    满足这些条件的类型（以及标量类型）按值传递时，实现可以经由临时对象中转。ABI 正是借这条把小对象放进寄存器（[[class.temporary#3]]）。

这个条件与[[g:trivially-copyable-class|平凡可复制类]]相近但不相同：平凡可复制还要求复制、移动赋值运算符平凡，而 [[class.temporary#3]] 不看赋值运算符。

满足条件也不保证放进寄存器，还要看大小。下面的 `B` 平凡可复制，但有 24 字节：

```cpp godbolt title="big.cpp" flags="-std=c++2c -O2" ok
struct B { long a, b, c; };   // 24 字节，平凡可复制
long sum_b(B b) { return b.a + b.b + b.c; }
```

<div class="compare" markdown="1">

```asm title="AArch64"
__Z5sum_b1B:
  ldp   x8, x9, [x0]   ; 调用者复制，传地址
  ldr   x10, [x0, #16]
  add   x8, x9, x8
  add   x0, x8, x10
  ret
```

```asm title="x86-64"
_Z5sum_b1B:
  movq  16(%rsp), %rax  # 复制在栈上的实参区
  addq  8(%rsp), %rax
  addq  24(%rsp), %rax
  retq
```

</div>

AArch64 对超过 16 字节的结构体由调用者复制一份、传地址；x86-64 把整个对象复制到栈上的实参区，被调函数从 `rsp` 往上读（`0(%rsp)` 是返回地址）。大体上，两种 ABI 都只把 16 字节以内、满足上述平凡条件的类拆进寄存器。AArch64 有一个例外：最多 4 个成员、全是同一种浮点类型的结构体用 d0–d3 传，本机 `struct V4 { double a, b, c, d; }` 的 32 字节就整个放在 d0–d3 里，而 x86-64 仍从栈上读。

### 虚调用

```cpp godbolt title="virt.cpp" flags="-std=c++2c -O2" ok
struct Shape {
  virtual ~Shape() = default;
  virtual double area() const = 0;
};
double area_of(const Shape& s) {
  return s.area();
}
```

<div class="compare" markdown="1">

```asm title="AArch64"
__Z7area_ofRK5Shape:
  ldr   x8, [x0]       ; 读 vptr
  ldr   x1, [x8, #16]  ; 读第 3 个槽
  br    x1             ; 跳过去
```

```asm title="x86-64"
_Z7area_ofRK5Shape:
  movq  (%rdi), %rax   # 读 vptr
  jmpq  *16(%rax)      # TAILCALL
```

</div>

对象开头是 vptr，第一次加载读出它；vtable 的前两个槽是虚析构函数的两个变体（完整对象析构和删除析构），`area` 在第三个槽，偏移 16；第二次加载读出函数地址，最后间接跳转。vtable 的完整结构见 [[toolchain/object-layout-and-vtables]]。

这里用的是 `br`/`jmp` 而不是 `blr`/`call`：调用 `area` 是 `area_of` 做的最后一件事，返回值原样返回，编译器直接跳过去，让 `area` 返回到 `area_of` 的调用者。这叫**尾调用**（tail call）。

如果编译器能确定动态类型，就不需要查表。把参数换成 `final` 类的引用：

```cpp godbolt title="final.cpp" flags="-std=c++2c -O2" ok
struct Shape {
  virtual ~Shape() = default;
  virtual double area() const = 0;
};
struct Square final : Shape {
  double side;
  double area() const override { return side * side; }
};
double area_of(const Square& s) {
  return s.area();
}
```

AArch64 输出变成 `ldr d0, [x0, #8]`、`fmul d0, d0, d0`、`ret`：直接读 `side`（vptr 之后，偏移 8），调用被内联了。x86-64 同样是 `movsd 8(%rdi), %xmm0` 加 `mulsd`。这种把虚调用变成直接调用的优化叫去虚化，什么时候能做到见 [[perf/compiler-optimizations|编译器能做的优化]]。

### 内联与不内联

```cpp godbolt title="inl.cpp" flags="-std=c++2c -O2" ok
static int twice(int x) { return 2 * x; }
int opaque(int x);            // 定义在别的 TU

int a(int x) { return twice(x) + 1; }
int b(int x) { return opaque(x) + 1; }
```

<div class="compare" markdown="1">

```asm title="AArch64"
__Z1ai:
  mov   w8, #1
  orr   w0, w8, w0, lsl #1
  ret
__Z1bi:
  stp   x29, x30, [sp, #-16]!
  mov   x29, sp
  bl    __Z6opaquei
  add   w0, w0, #1
  ldp   x29, x30, [sp], #16
  ret
```

```asm title="x86-64"
_Z1ai:
  leal  1(,%rdi,2), %eax
  retq
_Z1bi:
  pushq %rax           # 只为对齐栈
  callq _Z6opaquei@PLT
  incl  %eax
  popq  %rcx
  retq
```

</div>

`twice` 被内联进 `a` 之后，`2 * x + 1` 只剩一两条指令：AArch64 把 `x` 左移一位再或上 1，x86-64 用一条 `lea` 算出 `x*2 + 1`。`twice` 本身也没有出现在输出里，因为它是 `static` 的，所有调用都已内联，不需要再生成它。`b` 调用的 `opaque` 在别的翻译单元，编译器看不到函数体，只能老老实实 `bl`，并为此付出序言和尾声。

判断有没有内联，就看汇编里有没有对那个函数的 `bl`/`call`。跨翻译单元的内联要靠 LTO，见 [[perf/lto-pgo|LTO 与 PGO]]。

### 循环及其向量化形式

```cpp godbolt title="sum.cpp" flags="-std=c++2c -O2" ok
int sum(const int* p, long n) {
  int s = 0;
  for (long i = 0; i < n; ++i)
    s += p[i];
  return s;
}
```

先用 `-fno-vectorize -fno-unroll-loops` 关掉向量化和展开，看循环本来的样子：

<div class="compare" markdown="1">

```asm title="AArch64"
  cmp   x1, #1
  b.lt  LBB0_4         ; n < 1 直接返回 0
  mov   w8, #0
LBB0_2:                ; 循环头
  ldr   w9, [x0], #4   ; 读 *p，p += 4
  add   w8, w9, w8
  subs  x1, x1, #1     ; --n，设置标志
  b.ne  LBB0_2         ; n != 0 继续
```

```asm title="x86-64"
  xorl  %eax, %eax
  testq %rsi, %rsi
  jle   .LBB0_3        # n <= 0 跳过
  xorl  %ecx, %ecx
.LBB0_2:               # 循环头
  addl  (%rdi,%rcx,4), %eax
  incq  %rcx
  cmpq  %rcx, %rsi
  jne   .LBB0_2
```

</div>

认循环的办法是找向回跳的条件分支：`b.ne LBB0_2` 跳回到它上面的标签。Clang 还会在循环头标签后面加上注释 `=>This Inner Loop Header: Depth=1`。

AArch64 的 `[x0], #4` 是后变址寻址：先按 `x0` 读，再把 `x0` 加 4。x86-64 的 `(%rdi,%rcx,4)` 表示地址 `rdi + rcx*4`，它直接作为 `addl` 的内存操作数。

默认的 `-O2` 会向量化这个循环。主循环变成：

```asm title="AArch64"
LBB0_7:
  ldp    q4, q5, [x8, #-32]
  ldp    q6, q7, [x8], #64
  add.4s v0, v4, v0
  add.4s v1, v5, v1
  add.4s v2, v6, v2
  add.4s v3, v7, v3
  subs   x11, x11, #16
  b.ne   LBB0_7
```

```asm title="x86-64"
.LBB0_6:
  movdqu (%rdi,%rax,4), %xmm2
  paddd  %xmm2, %xmm1
  movdqu 16(%rdi,%rax,4), %xmm2
  paddd  %xmm2, %xmm0
  addq   $8, %rax
  cmpq   %rax, %rcx
  jne    .LBB0_6
```

`q4` 是 128 位向量寄存器，一次装 4 个 `int`；`add.4s` 是 4 路 32 位整数加法。每一轮读 16 个 `int`，分到 4 个累加器 `v0`–`v3` 里，循环结束后再把它们加起来，用 `addv.4s` 把一个向量的 4 个元素横向求和。`add.4s v0, v4, v0` 是 Apple 汇编器的写法，Linux 上的 AArch64 汇编写成 `add v0.4s, v4.4s, v0.4s`，指令相同。

x86-64 默认只能用 SSE2，`movdqu` 读 16 字节，`paddd` 做 4 路 32 位加法，每轮 8 个 `int`。加 `-march=x86-64-v3` 允许 AVX2 后，本机看到的是 `vpaddd` 作用于 256 位的 `ymm` 寄存器。

向量化后的函数比原来长得多：主循环前要判断 `n` 够不够大，主循环后还有处理剩余元素的循环，所以同一个函数里会看到三个循环头。读的时候先找带 `q`/`v` 寄存器（或 `xmm`/`ymm`）的那个循环，它是热路径。向量化的条件和代价见 [[perf/vectorization|向量化]]。

### switch 与跳转表

```cpp godbolt title="dispatch.cpp" flags="-std=c++2c -O2" ok
void on_a(); void on_b(); void on_c();
void on_d(); void on_e();

void dispatch(int op) {
  switch (op) {
    case 0: on_a(); break;
    case 1: on_b(); break;
    case 2: on_c(); break;
    case 3: on_d(); break;
    case 4: on_e(); break;
  }
}
```

```asm title="x86-64"
_Z8dispatchi:
  cmpl    $4, %edi
  ja      .LBB0_7                  # 无符号 > 4：不在表内
  movl    %edi, %eax
  leaq    .LJTI0_0(%rip), %rcx     # 表的地址
  movslq  (%rcx,%rax,4), %rax      # 取第 op 项
  addq    %rcx, %rax
  jmpq    *%rax                    # 跳过去
.LBB0_2:
  jmp     _Z4on_av@PLT             # TAILCALL
  ...
.LBB0_7:
  retq
.LJTI0_0:
  .long   .LBB0_2-.LJTI0_0
  .long   .LBB0_3-.LJTI0_0
  ...
```

**跳转表**（jump table）是一个数组，第 `i` 项存放 `case i` 的代码相对于表的偏移。先用一次无符号比较把负数和大于 4 的值一起排除（负数按无符号看是很大的数），然后按下标取表项、加上表地址、间接跳转。无论多少个 case，分派代价都是固定的几条指令。

同样的代码在本机 AArch64 上编译成了比较树：`cmp w0, #1`、`b.le`、`cmp w0, #2`、`b.eq`……逐个比较。在本机这个版本上，AArch64 要 10 个连续的 case 才生成跳转表（表项是一个字节，`ldrb` 读出后左移 2 位加到基址上，再 `br`），x86-64 从 4 个起就生成。这是各后端的启发式阈值，随编译器版本和 `-mcpu` 变化，标准对 `switch`（[[stmt.switch]]）的实现方式没有任何要求。

### 异常：正常路径上没有指令

```cpp godbolt title="eh.cpp" flags="-std=c++2c -O2" ok
struct Guard {
  ~Guard();                   // 非平凡析构，定义在别处
};
void work();                  // 可能抛出

int run() {
  Guard g;
  work();
  return 0;
}
```

```asm title="AArch64"
__Z3runv:
Lfunc_begin0:
  sub   sp, sp, #48
  stp   x20, x19, [sp, #16]
  stp   x29, x30, [sp, #32]
  add   x29, sp, #32
Ltmp0:                        ; EH_LABEL
  bl    __Z4workv
Ltmp1:                        ; EH_LABEL
  add   x0, sp, #15           ; 正常路径：析构 g
  bl    __ZN5GuardD1Ev
  mov   w0, #0
  ldp   x29, x30, [sp, #32]
  ldp   x20, x19, [sp, #16]
  add   sp, sp, #48
  ret
LBB0_2:                       ; 着陆点
Ltmp2:                        ; EH_LABEL
  mov   x19, x0               ; 保存异常对象指针
  add   x0, sp, #15
  bl    __ZN5GuardD1Ev        ; 析构 g
  mov   x0, x19
  bl    __Unwind_Resume       ; 继续向上传播
GCC_except_table0:
  ...                         ; Ltmp0..Ltmp1 之间的调用
  ...                         ; 出异常时跳到 Ltmp2
```

从 `bl __Z4workv` 到 `ret` 的正常路径上没有任何检查或分支，调用 `work` 之后直接析构 `g` 并返回，与加 `-fno-exceptions` 编译的版本一样。抛出异常时，运行时库根据 `GCC_except_table0` 这张表查到 `work` 的调用点对应的**着陆点**（landing pad）`Ltmp2`，跳到那里析构 `g`，再调用 `_Unwind_Resume` 继续回溯。x86-64 的结构相同，着陆点里用 `rbx` 暂存异常对象指针。

代价并非为零：着陆点要占用一个被调用者保存寄存器（这里是 `x19`），于是序言多存了一对寄存器，本机 `-fno-exceptions` 的版本只保存 `x29`、`x30`；着陆点和表本身也占代码体积。表的格式和回溯过程见 [[toolchain/exception-implementation]]。

### 加固模式的边界检查

`vector::operator[]` 对下标的要求是一条**加固前置条件**（[[g:hardened-precondition|hardened precondition]]）：`n < a.size()`（[[sequence.reqmts#122]]）。在加固实现中，违反它是契约违反而不是 UB（[[intro.compliance.general#8]]）。是否加固由实现定义；libc++ 用宏 `_LIBCPP_HARDENING_MODE` 选择，本机 Homebrew libc++ 的默认值是不加固。

```cpp godbolt title="index.cpp" flags="-std=c++2c -O2" ok
#include <vector>
int at_index(const std::vector<int>& v, std::size_t i) {
  return v[i];
}
```

<div class="compare" markdown="1">

```asm title="AArch64，默认"
  ldr   x8, [x0]       ; begin
  ldr   w0, [x8, x1, lsl #2]
  ret
```

```asm title="AArch64，FAST 加固"
  ldp   x8, x9, [x0]   ; begin, end
  sub   x9, x9, x8
  cmp   x1, x9, asr #2 ; i 与 size()
  b.hs  LBB0_2         ; 无符号 >=
  ldr   w0, [x8, x1, lsl #2]
  ret
LBB0_2:
  brk   #0x1           ; 陷阱
```

</div>

右边用 `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_FAST` 编译。多出来的是一次加载、一次减法、一次比较和一个几乎从不跳转的分支；检查失败时执行 `brk`（x86-64 上是 `ud2`），进程收到信号终止。本机用越界下标运行这样编译的程序，退出码是 133，即 SIGTRAP。

`(end - begin) >> 2` 算出元素个数，`b.hs` 是无符号的大于等于。负的下标转成 `size_t` 后是很大的数，所以一次无符号比较就同时检查了上下界。

在循环里，检查往往能提到循环外。`for (i = 0; i < v.size(); ++i) s += v[i];` 加固之后汇编里一个 `brk` 都没有，因为循环条件已经保证了前置条件。`for (i = 0; i < n; ++i) s += v[i];` 则在循环开始前比较一次 `n - 1` 和 `size()`，失败就直接陷入，循环体照常向量化。提前陷入是允许的：求和本身没有可观察行为，提前终止与执行到第一个越界下标再终止，从外部看不出差别（[[intro.abstract#1]]）。

下标来自数据时检查就提不出去了。下面的基准测试按随机下标求和：

```cpp run title="hardening_bench.cpp" ok flags="-std=c++2c -O2"
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <random>
#include <vector>

// 阻止编译器把结果当作无用而删掉：
// 空的内联汇编声称会读取 v，编译器只好真的算出 v。
template <class T> void keep(T const& v) {
  asm volatile("" : : "r"(v) : "memory");
}

__attribute__((noinline))
long gather(const std::vector<int>& v,
            const std::vector<unsigned>& idx) {
  long s = 0;
  for (unsigned k : idx) s += v[k];   // 每次都检查 k < size()
  return s;
}

__attribute__((noinline))
long linear(const std::vector<int>& v) {
  long s = 0;
  for (std::size_t i = 0; i < v.size(); ++i) s += v[i];
  return s;
}

template <class F> double median_ns(F f, std::size_t n) {
  std::vector<double> t;
  for (int r = 0; r < 4; ++r) keep(f());      // 预热
  for (int r = 0; r < 31; ++r) {
    auto t0 = std::chrono::steady_clock::now();
    keep(f());
    auto t1 = std::chrono::steady_clock::now();
    t.push_back(std::chrono::duration<double, std::nano>(t1 - t0).count() / n);
  }
  std::ranges::sort(t);
  return t[t.size() / 2];
}

int main() {
  const std::size_t n = 1 << 16;            // 256 KiB 的 int，放得进 L2
  std::vector<int> v(n, 1);
  std::vector<unsigned> idx(n);
  std::mt19937 rng(42);
  for (auto& k : idx) k = rng() % n;
  std::printf("gather: %.3f ns/elem\n",
              median_ns([&] { return gather(v, idx); }, n));
  std::printf("linear: %.3f ns/elem\n",
              median_ns([&] { return linear(v); }, n));
}
```

计时框架很简单：`steady_clock` 计时，先空跑 4 次预热缓存，再测 31 次取中位数。`keep` 里的空 `asm volatile` 告诉编译器它要读取结果，这样求和不会因为结果没人用而被删掉。`asm` 声明的含义由实现定义（[[dcl.asm#1]]），这是 GCC/Clang 的扩展写法。测量方法本身见 [[perf/measuring|怎样测量]]。

本机分别用 `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_NONE` 和 `..._FAST` 加 `-std=c++2c -O2` 编译，交替运行 5 次：

| | 不加固 | FAST 加固 |
|---|---|---|
| `gather`（随机下标） | 0.387–0.388 ns/元素 | 0.415–0.419 ns/元素 |
| `linear`（顺序下标） | 0.046 ns/元素 | 0.046 ns/元素 |

`gather` 慢了约 7%。汇编给出了原因：不加固时循环展开成 4 路、用 4 个累加器；加固后每个元素都要 `cmp` 加 `b.ls`，循环也不再展开。`linear` 的检查被完全消除，两种模式的汇编在热循环上相同，时间也相同。这是本机 M2 Pro 上的观察，换硬件、换编译器、换数据规模都可能不同。

## 从汇编里找问题

### 意料之外的调用

先把函数里所有的调用列出来：

```bash
clang++ -std=c++2c -O2 -S copy.cpp -o - | grep -E '\b(bl|call)'
```

```cpp godbolt title="copy.cpp" flags="-std=c++2c -O2" ok
#include <vector>
long count(std::vector<int> v);   // 按值接收

long caller(const std::vector<int>& v) {
  return count(v);                 // 复制一份
}
```

本机 AArch64 输出里依次出现 `bl __Znwm`（`operator new(unsigned long)`）、`bl _memcpy`、`bl __Z5countNSt3__16vector...`、`bl __ZdlPvm`（`operator delete`），后面还有抛 `length_error` 和 `_Unwind_Resume` 的冷路径。一次看起来无害的按值传参，换来了一次堆分配、一次内存复制和一次释放。x86-64（`--target=x86_64-apple-macos`）的调用序列相同。

大对象按值传递也会冒出 `memcpy`：

```cpp godbolt title="msg.cpp" flags="-std=c++2c -O2" ok
struct Msg { char buf[1024]; };
void send(Msg m);
void forward(const Msg& m) { send(m); }
```

本机 AArch64 是 `sub sp, sp, #1040` 加 `bl _memcpy`；x86-64 先 `callq memcpy@PLT` 复制一次，再用 `rep movsq` 把它复制到实参区，同一份数据复制了两次。缩小到 256 字节时 AArch64 改用 8 对 `ldp`/`stp`（每条搬 32 字节）内联复制，没有 `memcpy` 调用，但复制量不变。

AArch64 的这段输出里还有对 `___stack_chk_guard` 的读取和对 `___stack_chk_fail` 的调用，这是栈保护：函数栈上有字符数组，编译器在返回前检查数组之后的哨兵值有没有被改写。本机 Clang 在 macOS 目标上默认开启它（`-fno-stack-protector` 关闭），`--target=x86_64-linux-gnu` 下默认没有。看到不认识的调用，先 `llvm-cxxfilt` 还原名字，再判断它来自自己的代码、标准库还是编译选项。复制何时发生、怎样避免，见 [[perf/copies-and-moves|复制与移动]]；堆分配见 [[perf/allocation|内存分配]]。

### 溢出

寄存器不够用时，编译器把值暂存到栈上，用的时候再读回来，这叫**溢出**（spill）。Clang 在这些指令后面加注释 `Folded Spill` / `Folded Reload`，用 `grep -E 'Spill|Reload'` 就能找到。不过序言里保存被调用者保存寄存器的指令也带同样的注释，要区分开。

```cpp godbolt title="spill.cpp" flags="-std=c++2c -O2" ok
long h(long);
long many(const long* p) {
  long a = p[0], b = p[1], c = p[2], d = p[3],
       e = p[4], f = p[5], g = p[6], i = p[7],
       j = p[8], k = p[9], l = p[10], m = p[11];
  long r = h(0);              // 12 个值都要活过这次调用
  return r + a*b + c*d + e*f + g*i + j*k + l*m;
}
```

```asm title="AArch64"
__Z4manyPKl:
  sub   sp, sp, #112
  stp   x28, x27, [sp, #16]     ; 16-byte Folded Spill  ← 序言
  ...                           ;  x19–x28、x29、x30 全部保存
  ldp   x9, x8, [x0]            ; 读 p[0]、p[1]
  stp   x8, x9, [sp]            ; 16-byte Folded Spill  ← 真正的溢出
  ldp   x21, x22, [x0, #16]
  ldp   x23, x24, [x0, #32]
  ldp   x25, x26, [x0, #48]
  ldp   x27, x28, [x0, #64]
  ldp   x19, x20, [x0, #80]
  mov   x0, #0
  bl    __Z1hl
  ldp   x9, x8, [sp]            ; 16-byte Folded Reload ← 读回
  mul   x8, x9, x8
  madd  x8, x22, x21, x8        ; x8 += x22 * x21
  ...
```

`h` 可能修改 `*p`，所以 12 个值必须在调用前读出来。编译器选择调用之后再做乘法，于是 12 个值都要活过调用，而被调用者保存寄存器只有 x19–x28 这 10 个，剩下 2 个只能溢出到栈上。

同一段代码在 x86-64 上做了不同的选择：调用之前先把 6 个乘积算出来，并且把它们部分相加，只剩 3 个值要跨越调用，放进 `rbx`、`r14`、`r15`，没有溢出。x86-64 的被调用者保存寄存器只有 6 个，后端的调度会更早地压缩活跃值。两种结果都正确，这个例子只说明溢出是寄存器压力和调度共同决定的，要看实际的汇编才知道。

热循环里出现溢出才值得关注，因为每一轮都要多一次存和读。函数开头和结尾的一次性保存通常无关紧要。

### 没有向量化的循环

把 `sum` 的 `int` 换成 `float`：

```cpp godbolt title="fsum.cpp" flags="-std=c++2c -O2" ok
float fsum(const float* p, long n) {
  float s = 0;
  for (long i = 0; i < n; ++i)
    s += p[i];
  return s;
}
```

`-Rpass=loop-vectorize -Rpass-missed=loop-vectorize -Rpass-analysis=loop-vectorize` 让 Clang 报告向量化的决定。本机两个目标的报告不一样：

```text
# --target=x86_64-linux-gnu
fsum.cpp:4:7: remark: loop not vectorized: cannot prove it is safe to
reorder floating-point operations; ...
# 本机 AArch64
fsum.cpp:3:3: remark: vectorized loop (vectorization width: 4,
interleaved count: 4) [-Rpass=loop-vectorize]
```

AArch64 声称向量化了，汇编却显示加法仍然是标量的，并且一个接一个地串在同一个寄存器 `s0` 上：

```asm title="AArch64 主循环（节选）"
LBB0_7:
  ldp   q1, q2, [x10, #-32]   ; 向量加载
  mov   s3, v1[3]             ; 把元素一个个拆出来
  mov   s4, v1[2]
  mov   s5, v1[1]
  ...
  fadd  s0, s0, s1            ; 标量加法，严格按顺序
  fadd  s0, s0, s5
  fadd  s0, s0, s4
  fadd  s0, s0, s3
  ...
  subs  x11, x11, #16
  b.ne  LBB0_7
```

x86-64 上则是 8 条 `addss` 串在 `xmm0` 上（`ss` 表示 scalar single，单个 `float`；`ps` 才是 packed single，4 个 `float`）。两种写法本质相同：每次加法都依赖上一次的结果，不能并行。

原因是浮点加法不满足结合律，`(a + b) + c` 和 `a + (b + c)` 的结果可能不同。按 as-if 规则，编译器只能做不改变可观察行为的变换（[[intro.abstract#1]]），而 `s` 的值迟早会被输出，所以不能把一条加法链拆成 4 个独立的累加器。加 `-ffast-math`（或更窄的 `-fassociative-math -fno-signed-zeros -fno-trapping-math`）后，两边都出现了真正的向量加法 `fadd.4s` / `addps`。这些选项让编译器放弃严格的 IEEE 语义，结果可能与源码顺序计算的值不同。

这个例子说明，向量化报告只是线索，最终要看循环体里的指令：是 `.4s`、`ps`、`pd`、`ymm` 一类的向量运算，还是逐个元素的标量运算。整数和浮点在这一点上的差别，以及其他阻止向量化的原因，见 [[perf/vectorization|向量化]]。

## 指令速查

左栏是 Apple 汇编器的 AArch64 写法，右栏是 AT&T 语法的 x86-64。x86-64 的指令后缀 `b`/`w`/`l`/`q` 表示 8/16/32/64 位；AArch64 用寄存器名区分宽度：`w` 是 32 位、`x` 是 64 位，`s`/`d`/`q` 是 32/64/128 位浮点或向量寄存器。

| 作用 | AArch64 | x86-64 |
|---|---|---|
| 寄存器复制 | `mov x0, x1` | `movq %rsi, %rdi`（源在前） |
| 加载 | `ldr w8, [x0, #8]`、`ldr w8, [x0, x1, lsl #2]` | `movl 8(%rdi), %eax`、`movl (%rdi,%rsi,4), %eax` |
| 存储 | `str w8, [x0]` | `movl %eax, (%rdi)` |
| 成对加载、存储 | `ldp x8, x9, [x0]`、`stp x29, x30, [sp, #16]` | 无；保存寄存器用 `pushq`/`popq` |
| 后变址、前变址 | `ldr w9, [x0], #4`（读后 `x0 += 4`）、`stp ..., [sp, #-32]!`（先减后存） | 无 |
| 地址计算 | `add x0, x1, x2, lsl #2`；全局变量 `adrp` + `add` | `leaq 8(%rdi,%rsi,4), %rax`；全局变量 `leaq sym(%rip)` |
| 加减乘 | `add`、`sub`、`mul`、`madd`（乘加）、`neg` | `addq`、`subq`、`imulq`、`incq`、`negq` |
| 除法 | `sdiv`、`udiv` | `idivq`、`divq`（被除数在 rdx:rax） |
| 位运算与移位 | `and`、`orr`、`eor`、`lsl`、`lsr`、`asr` | `andq`、`orq`、`xorq`、`shlq`、`shrq`、`sarq` |
| 清零 | `mov w8, #0` | `xorl %eax, %eax` |
| 比较，设置标志 | `cmp x0, x1`、`tst w8, #0x80` | `cmpq %rsi, %rdi`、`testq %rdi, %rdi` |
| 条件选择 | `csel x0, x1, x2, eq`、`cset w0, lt` | `cmoveq %rsi, %rax`、`setl %al` |
| 有符号条件跳转 | `b.lt`、`b.le`、`b.gt`、`b.ge` | `jl`、`jle`、`jg`、`jge` |
| 无符号条件跳转 | `b.lo`、`b.ls`、`b.hi`、`b.hs` | `jb`、`jbe`、`ja`、`jae` |
| 相等、为零 | `b.eq`、`b.ne`、`cbz x0`、`cbnz x0` | `je`、`jne` |
| 无条件跳转、尾调用 | `b label`、`b func` | `jmp label`、`jmp func` |
| 间接跳转 | `br x8` | `jmpq *%rax`、`jmpq *16(%rax)` |
| 调用 | `bl func`；间接调用 `blr x8` | `callq func`；间接调用 `callq *%rax` |
| 返回 | `ret`（跳到 x30） | `retq`（弹出返回地址） |
| 浮点标量 | `fadd s0, s0, s1`、`fmul d0, d0, d1` | `addss`、`mulsd`（`ss` 单精度、`sd` 双精度） |
| 向量加载 | `ldr q0, [x0]`、`ldp q0, q1, [x0]` | `movdqu`、`movups`（`ymm` 为 AVX） |
| 向量运算 | `add.4s`、`fadd.4s`、`addv.4s`（横向求和） | `paddd`、`addps`、`vpaddd`（`ps`/`pd` 为打包） |
| 陷阱 | `brk #0x1` | `ud2` |

Clang 的输出里还有一些注释值得认识：`=>This Inner Loop Header` 标出循环头，`TAILCALL` 标出尾调用，`Folded Spill`/`Folded Reload` 标出栈上的保存与读回，`EH_LABEL` 标出异常表引用的位置。x86-64 输出中的 `# kill: def $edi ...` 是寄存器分配器留下的说明，表示只用到了寄存器的一部分，不对应任何指令。

## 思考题

!!! question "一段虚调用"
    下面是某个函数的全部 AArch64 汇编，参数是一个多态类的引用。它在做什么？被调用的虚函数在类定义里大概处在什么位置？

    ```asm
    ldr   x8, [x0]
    ldr   x1, [x8, #24]
    br    x1
    ```

<details markdown="1">
<summary>答案</summary>

第一条从对象开头读出 vptr，第二条读出 vtable 中偏移 24 处的函数指针，第三条跳过去，并且是尾调用：这个函数只做了一次虚调用，并原样返回它的结果。偏移 24 是第 4 个 8 字节槽（从 0 数起是第 3 个）。在 Itanium ABI 下，如果类的第一个虚函数是虚析构函数，它占前两个槽，那么这里调用的是析构函数之后声明的第二个虚函数。vtable 的槽位规则见 [[toolchain/object-layout-and-vtables]]。

</details>

!!! question "提前陷入"
    开启 libc++ FAST 加固后，`for (std::size_t i = 0; i < n; ++i) s += v[i];` 在循环开始前比较 `n - 1` 与 `v.size()`，不满足就立刻执行 `brk`。如果 `n == v.size() + 1`，前 `v.size()` 次访问本来都是合法的，编译器这样做是否改变了程序的行为？

<details markdown="1">
<summary>答案</summary>

没有改变可观察行为。照源码逐次执行，前 `v.size()` 次迭代只是读内存、做加法，这些都不是可观察行为（[[intro.abstract#8]] 列出的只有 volatile 访问、写文件和交互设备的输入输出）；第 `v.size() + 1` 次访问违反加固前置条件，程序终止。提前终止和执行几次加法之后再终止，在可观察行为上没有区别，所以按 as-if 规则（[[intro.abstract#1]]）允许把检查合并成一次。如果循环里有 `printf`，编译器就不能这样提前，必须先产生前面的输出。

</details>

## 小结

| 想确认的事 | 在汇编里找什么 |
|---|---|
| 函数有没有被内联 | 调用者里还有没有对它的 `bl`/`call` |
| 参数怎么传 | 函数开头直接用 x0/rdi 的值，还是从 `[x0]`/`(%rdi)` 读 |
| 有没有多余的复制、分配 | `memcpy`、`__Znwm`（`operator new`）、`__ZdlPv`（`operator delete`） |
| 虚调用有没有去虚化 | `ldr`+`ldr`+`blr`/`br`，或 `call *off(%reg)` 是否还在 |
| 循环有没有向量化 | 循环体里是 `.4s`/`q` 寄存器、`ps`/`xmm`/`ymm`，还是逐元素的标量指令 |
| 有没有寄存器溢出 | 循环体里带 `Folded Spill`/`Folded Reload` 注释的 `str`/`ldr` |
| 加固检查是否留在热循环里 | 循环体里的比较加 `b.hs`/`b.ls`/`jae`，以及函数末尾的 `brk`/`ud2` |
