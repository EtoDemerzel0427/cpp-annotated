---
title: C++ 异常是如何实现的
summary: GCC 和 Clang 在非 Windows 平台上采用的 Itanium ABI 表驱动异常处理：抛出时调用哪些运行时函数，两阶段回溯怎样找到 handler，着陆点怎样析构对象和进入 catch，noexcept 和 -fno-exceptions 对代码生成的影响，以及零开销的真实代价。
status: draft
order: 40
related: except, except.throw, except.handle, except.ctor, except.spec, except.special, toolchain/compilation-pipeline
tags: 异常, ABI, Itanium, 代码生成, 工具链
updated: 2026-10-19
---

!!! tldr
    - `throw` 编译成两次运行时调用：`__cxa_allocate_exception` 分配异常对象（不经过 `operator new`），`__cxa_throw` 启动回溯。不抛出的路径上没有任何额外指令。
    - 回溯分两遍：第一遍只读地逐帧查找 handler，找到后第二遍才执行析构并进入 handler。找不到 handler 时直接调用 `std::terminate`，栈完全没有回溯。
    - 每个函数的 LSDA 表记录了哪个调用点对应哪个着陆点、能接住哪些类型；`.eh_frame` 里的 CFI 记录怎样从一帧走到它的调用者。
    - Clang 把 `noexcept` 实现为包住整个函数体的 `catch (...)` 加 `std::terminate`，所以只回溯到这个函数为止，它自己的局部对象不析构。
    - 零开销指正常路径没有额外指令。抛出一次要几微秒，异常表占体积，可能抛出的调用还会限制优化。

## 标准留下的自由

标准第 14 章（[[except]]）只规定异常处理的语义，把实现方式留给实现：

- 异常对象的内存以未指定的方式分配（[[except.throw#4]]）；
- 找不到匹配的 handler 时，调用 `std::terminate` 之前是否回溯栈由实现定义（[[except.handle#8]]）；
- 异常离开 `noexcept` 函数时，可以完全回溯、部分回溯或不回溯（[[except.terminate#2]]）。

GCC 和 Clang 在 Linux、macOS 等平台上使用 **Itanium C++ ABI** 的异常处理方案。名字里虽然有 Itanium，它实际上是今天几乎所有非 Windows 平台的 C++ ABI。下面用本机 Homebrew Clang 23 生成的汇编看这些自由度被怎样使用。

!!! note "实验环境"
    x86-64 Linux 的汇编用 `clang++ -std=c++2c -O1 -S --target=x86_64-linux-gnu` 生成，只编译不链接；运行时间和体积在本机 macOS arm64 上测量。

## 两层运行时

Itanium 方案把工作分给两个库：

| 层 | 组件 | 职责 |
|---|---|---|
| 与语言无关的回溯库 | `_Unwind_RaiseException`、`_Unwind_Resume` 等（libgcc_s、LLVM libunwind、macOS 系统 libunwind） | 按 `.eh_frame` 中的帧描述逐帧恢复寄存器；对每一帧调用它的 personality routine |
| C++ 运行时 | `__cxa_*` 函数和 `__gxx_personality_v0`（libsupc++ 或 libc++abi） | 分配异常对象、实现 C++ 的类型匹配、解析 LSDA、维护当前处理的异常 |

回溯库不懂 C++。它只知道调用栈由帧组成，每一帧有一个 **personality routine**（与语言相关的回调函数）可以询问。所以 C、C++ 和其他语言的帧可以混在同一个调用栈里一起回溯。

## 抛出

```cpp title="eh.cpp"
struct Guard { ~Guard(); };
struct Err { int code; };
void may_throw(int);

void thrower(int x) {
    if (x < 0) throw Err{x};
}

int catcher(int x) {
    Guard g;
    try {
        may_throw(x);
    } catch (const Err& e) {
        return e.code;
    }
    return 0;
}
```

`thrower` 的汇编，删去了部分伪指令：

```text
_Z7throweri:
        testl   %edi, %edi
        js      .LBB0_2
        retq                            # 正常路径：一次测试、一次返回
.LBB0_2:
        pushq   %rbx
        movl    %edi, %ebx
        movl    $4, %edi                # sizeof(Err)
        callq   __cxa_allocate_exception@PLT
        movl    %ebx, (%rax)            # 在返回的内存里构造异常对象
        leaq    _ZTI3Err(%rip), %rsi    # 第二个参数：typeid(Err)
        movq    %rax, %rdi              # 第一个参数：异常对象
        xorl    %edx, %edx              # 第三个参数：析构函数指针，Err 可平凡析构，所以为空
        callq   __cxa_throw@PLT         # 不返回
```

正常路径（`x >= 0`）上没有任何与异常有关的指令。抛出路径做了三件事。

`__cxa_allocate_exception(size)` 分配异常对象的存储。它在用户可见的对象之前还多分配一个运行时头部 `__cxa_exception`，里面有类型信息、析构函数指针、引用计数、handler 计数，以及回溯库需要的 `_Unwind_Exception`。实现通常用 `malloc`，失败时退回到一块预先分配的紧急缓冲区。标准把存储方式定为未指定，并规定这里不调用全局 `operator new`（[[basic.stc.dynamic.allocation#5]]），就是为了允许这种做法。

接着在这块内存里就地构造异常对象（[[except.throw#3]]）。`Err` 是聚合，所以只是一条 `movl`；类类型在这里调用构造函数。如果构造函数抛出，编译器生成的清理代码调用 `__cxa_free_exception` 释放内存，向外传播的是构造函数抛出的那个异常。[[except.throw#6]] 规定异常对象初始化完成之后异常才算未捕获，与此一致。

最后 `__cxa_throw(obj, type_info*, destructor)` 记录类型和析构函数，把未捕获异常计数加一（`std::uncaught_exceptions()` 读的就是它），然后调用 `_Unwind_RaiseException`。只有找不到 handler 时它才会返回，此时 `__cxa_throw` 调用 `std::terminate`。

## 两阶段回溯

`_Unwind_RaiseException` 把调用栈遍历两遍。

1. **搜索阶段**（search phase）：从抛出点开始逐帧向外，对每一帧调用它的 personality routine，问这一帧有没有能接住这个异常的 handler。这一遍只读，不执行析构函数，也不修改任何帧。
2. **清理阶段**（cleanup phase）：找到 handler 之后，再从抛出点开始逐帧向外。这一遍 personality routine 把控制转入每一帧的**着陆点**（landing pad），执行析构等清理，直到找到 handler 的那一帧，进入 handler 本身。

如果搜索阶段走到栈底仍然没有 handler，`_Unwind_RaiseException` 返回错误，`__cxa_throw` 调用 `std::terminate`，栈完全没有被回溯。这就是主流实现在 [[except.handle#8]] 中的选择。好处是未捕获异常产生的 core dump 里还保留着抛出点的完整调用栈。

分两遍的代价是每次抛出都要遍历栈两次，两遍都要解析帧描述和 LSDA。这是抛出异常开销大的主要原因之一。

## 帧描述：`.eh_frame` 与 CFI

要从一帧走到它的调用者，回溯库必须知道：执行到当前这条指令时，返回地址存在哪里，栈指针偏移了多少，哪些需要恢复的寄存器保存在栈上的什么位置。编译器把这些信息以 DWARF **调用帧信息**（Call Frame Information，CFI）的形式写进 `.eh_frame` 节。在汇编里它们是 `.cfi_*` 伪指令：

```text
_Z7catcheri:
        .cfi_startproc
        .cfi_personality 155, DW.ref.__gxx_personality_v0   # 本函数的 personality routine
        .cfi_lsda 27, .Lexception0                          # 本函数的 LSDA 在哪
        pushq   %rbx
        .cfi_def_cfa_offset 16
        subq    $16, %rsp
        .cfi_def_cfa_offset 32
        .cfi_offset %rbx, -16
```

`llvm-dwarfdump --eh-frame` 把它们解码成表格。`thrower` 的那一项是：

```text
  0x0: CFA=RSP+8: RIP=[CFA-8]
  0x6: CFA=RSP+16: RBX=[CFA-16], RIP=[CFA-8]
```

意思是执行到偏移 6 之后，规范帧地址（CFA）是 `RSP+16`，`RBX` 保存在 `CFA-16`，返回地址在 `CFA-8`。回溯库就是解释这样的表，一帧一帧往外走。

`.eh_frame` 里每个函数有一个 FDE（Frame Description Entry），若干函数共用一个 CIE（Common Information Entry）。有 personality routine 的函数，其 CIE 的增强串里带 `P`（personality）和 `L`（LSDA），本机的 dump 中是 `Augmentation: "zPLR"`。

!!! note "macOS"
    Apple 平台上编译器还生成 `__LD,__compact_unwind` 节，链接器再把它转换成更紧凑的 `__TEXT,__unwind_info`。能用紧凑编码描述的帧就不再需要 DWARF FDE。本机 arm64 目标文件中可以看到 `__compact_unwind` 和 `__gcc_except_tab` 两个节。格式不同，但两阶段模型、personality routine 和 LSDA 都一样。

## personality routine 与 LSDA

回溯库对每一帧调用 CIE 中记录的 personality routine。C++ 代码的 personality routine 是 `__gxx_personality_v0`，GCC 和 Clang 都用这个名字，libc++abi 和 libsupc++ 各有一份实现。它读取函数的 **LSDA**（Language-Specific Data Area，位于 `.gcc_except_table` 节），回答两个问题：

- 搜索阶段：当前调用点有没有能匹配这个异常类型的 handler？
- 清理阶段：当前调用点的着陆点在哪里，要告诉着陆点哪个选择子（selector）？

`catcher` 的 LSDA，注释由 Clang 生成：

```text
GCC_except_table1:
.Lexception0:
        .byte   255                     # @LPStart Encoding = omit
        .byte   155                     # @TType Encoding = indirect pcrel sdata4
        .uleb128 .Lttbase0-.Lttbaseref0
        .byte   1                       # Call site Encoding = uleb128
        .uleb128 .Lcst_end0-.Lcst_begin0
.Lcst_begin0:
        .uleb128 .Ltmp0-.Lfunc_begin0   # >> Call Site 1 <<
        .uleb128 .Ltmp1-.Ltmp0          #   Call between .Ltmp0 and .Ltmp1
        .uleb128 .Ltmp2-.Lfunc_begin0   #     jumps to .Ltmp2
        .byte   3                       #   On action: 2
        .uleb128 .Ltmp1-.Lfunc_begin0   # >> Call Site 2 <<
        .uleb128 .Ltmp3-.Ltmp1          #   Call between .Ltmp1 and .Ltmp3
        .byte   0                       #     has no landing pad
        .byte   0                       #   On action: cleanup
        ...
.Lcst_end0:
        .byte   0                       # >> Action Record 1 <<
                                        #   Cleanup
        .byte   0                       #   No further actions
        .byte   1                       # >> Action Record 2 <<
                                        #   Catch TypeInfo 1
        .byte   125                     #   Continue to action 1
                                        # >> Catch TypeInfos <<
.Ltmp6:                                 # TypeInfo 1
        .long   .L_ZTI3Err.DW.stub-.Ltmp6
```

LSDA 由三张表组成。

**调用点表**（call-site table）把函数内的指令区间映射到着陆点地址和动作。第 1 项说，在 `.Ltmp0` 到 `.Ltmp1` 之间（即 `call may_throw`）抛出的异常跳到 `.Ltmp2`，执行动作 2。如果一个调用不在任何区间内却抛出了异常，personality routine 会调用 `std::terminate`。所以编译器为每个可能抛出的调用都列一项，即使它没有着陆点。

**动作表**（action table）：动作 2 是"如果匹配类型表第 1 项，选择子为 1，否则继续动作 1"；动作 1 是清理，即只执行析构，然后继续回溯。

**类型表**（type table）：第 1 项是 `typeid(Err)`。空指针表示 `catch (...)`。

[[except.handle#3]] 的匹配规则就在 personality routine 里实现：它拿异常对象的 `type_info`（`__cxa_throw` 的第二个参数）和类型表里 handler 的 `type_info` 比较。派生类到基类的匹配依靠 `__si_class_type_info`、`__vmi_class_type_info` 中记录的基类列表，包括是否 public、是否有歧义；指针的匹配依靠 `__pointer_type_info` 中记录的 cv 限定和 `noexcept` 标志。运行时手里只有 `type_info`，这也解释了为什么 handler 匹配不允许任意的类型转换。

## 着陆点：析构与 catch

`catcher` 的代码：

```text
        xorl    %ebx, %ebx
.Ltmp0:
        callq   _Z9may_throwi@PLT       # 调用点 1
.Ltmp1:
.LBB1_3:                                # 正常路径与 catch 之后的汇合点
        leaq    15(%rsp), %rdi
        callq   _ZN5GuardD1Ev@PLT       # ~Guard()
        movl    %ebx, %eax
        addq    $16, %rsp
        popq    %rbx
        retq
.LBB1_1:                                # 着陆点 .Ltmp2
.Ltmp2:
        movq    %rax, %rbx              # rax = _Unwind_Exception*
        cmpl    $1, %edx                # edx = 选择子；1 表示匹配了 Err
        jne     .LBB1_5                 # 不是 Err：只做清理
        movq    %rbx, %rdi
        callq   __cxa_begin_catch@PLT   # 返回异常对象的地址；handler 变为活动
        movl    (%rax), %ebx            # e.code
.Ltmp3:
        callq   __cxa_end_catch@PLT     # handler 退出
.Ltmp4:
        jmp     .LBB1_3                 # 继续执行：析构 g，返回
.LBB1_4:
.Ltmp5:
        movq    %rax, %rbx
.LBB1_5:                                # 清理用的着陆点
        leaq    15(%rsp), %rdi
        callq   _ZN5GuardD1Ev@PLT       # 栈回溯时析构 g
        movq    %rbx, %rdi
        callq   _Unwind_Resume@PLT      # 继续向外回溯
```

正常路径在 `call may_throw` 之后直接析构 `g` 并返回，没有任何检查。

着陆点由 personality routine 在清理阶段跳入，`%rax` 是异常头部的指针，`%edx` 是选择子。选择子不是 1 时，跳到清理用的着陆点：析构 `g`（[[except.ctor#2]]），然后 `_Unwind_Resume` 把控制交回回溯库，继续处理更外层的帧。

`__cxa_begin_catch` 把异常标为已捕获（未捕获计数减一，[[except.throw#8]]），handler 计数加一，把异常压入已捕获异常的栈，并返回异常对象的地址。这个栈的栈顶就是 [[except.handle#10]] 所说的[[g:currently-handled-exception|当前处理的异常]]。按引用捕获时 `e` 直接绑定到这个地址；按值捕获时，编译器在这之后调用复制构造函数。

`__cxa_end_catch` 在 handler 退出时调用。它把 handler 计数减一，如果计数为零且异常没有被重新抛出，就调用记录下来的析构函数销毁异常对象并释放内存。这对应 [[except.throw#4]] 的第一种潜在销毁点。如果有 `std::exception_ptr` 还引用着这个对象，引用计数会把销毁推迟到最后一个 `exception_ptr` 析构时，即第二种潜在销毁点。

`__cxa_end_catch` 自己也在调用点表里（第 3 项，着陆点 `.Ltmp5`），因为异常对象的析构函数可能抛出，那时仍要清理 `g`。

`throw;` 编译成 `__cxa_rethrow()`。它把当前处理的异常标为重新抛出，重新计入未捕获，然后再次调用 `_Unwind_RaiseException`，不创建新的异常对象（[[expr.throw#3]]）。

## `noexcept` 与代码生成

比较两个只差一个 `noexcept` 的函数：

```cpp title="nx.cpp"
struct Guard { ~Guard(); };
void may_throw(int);
void f(int x) noexcept { Guard g; may_throw(x); }
void h(int x)          { Guard g; may_throw(x); }
```

`h` 可能抛出，它的着陆点析构 `g` 后继续回溯：

```text
.LBB2_2:
        movq    %rax, %rbx
        leaq    15(%rsp), %rdi
        callq   _ZN5GuardD1Ev@PLT
        movq    %rbx, %rdi
        callq   _Unwind_Resume@PLT
```

`f` 是 `noexcept` 的，它的着陆点和 LSDA 是：

```text
.LBB0_2:
        movq    %rax, %rdi
        callq   __clang_call_terminate     # = __cxa_begin_catch + std::terminate
...
                                           # LSDA 中：
        .byte   1                          # >> Action Record 1 <<
                                           #   Catch TypeInfo 1
        .long   0                          # TypeInfo 1 = 0，即 catch (...)
```

Clang 把 `noexcept` 实现为一个包住整个函数体的 `catch (...)`，handler 里调用 `std::terminate`。搜索阶段会找到这个 handler，所以清理阶段回溯到 `f` 为止，比 `f` 更深的帧照常析构。

`f` 自己的 `g` 没有被析构，着陆点直接终止，省掉了清理代码。[[except.terminate#2]] 允许部分回溯，用处就在这里。本机运行的验证见 [[except.special]]。

`__clang_call_terminate` 先调用 `__cxa_begin_catch`，再调用 `std::terminate`，于是这个异常成了当前处理的异常。这对应 [[except.handle#9]]：因抛出而进入 `std::terminate` 时，有一个隐式的 handler 处于活动状态。terminate 处理函数因此可以用 `std::current_exception()` 拿到异常。

更大的收益在调用方。被调用的函数是 `noexcept` 时，这个调用点在 LSDA 里不需要着陆点。如果一个函数里所有的调用都不会抛出，它可能完全不需要 LSDA 和 personality routine。

## 零开销的真实代价

零开销（zero-cost）指不抛出时正常路径上没有额外的指令。其他方面仍有代价：

| 代价 | 说明 |
|---|---|
| 抛出很慢 | 要分配异常对象，遍历栈两遍，解析 CFI 和 LSDA，比较 `type_info`，对动态加载的模块还要查找它的 `.eh_frame`。本机（Apple M 系列，libc++abi，`-O2`）一个只跨一层函数调用的 `throw`/`catch` 约 3 µs，结构相同的普通返回不到 1 ns。 |
| 二进制体积 | 着陆点代码、LSDA 和 CFI 都占空间。本机一个调用 `vector::push_back` 和 `to_string` 的小函数，`-O2` 下 `__text` 节 820 字节，加 `-fno-exceptions` 后 532 字节，还省掉了 36 字节的 `__gcc_except_tab` 和 224 字节的 `__compact_unwind`。 |
| 限制优化 | 每个可能抛出的调用都是一条隐式的控制流边。编译器不能随意把内存写入移过这样的调用，因为异常路径上可能观察到它们；着陆点延长了变量的活跃区间，增加寄存器压力，也影响内联决策。 |
| 缓存 | 着陆点通常放在函数末尾或单独的冷代码区，对指令缓存的影响一般不大，但不是零。 |
| 多线程抛出 | 某些平台上查找 `.eh_frame`（如 glibc 的 `dl_iterate_phdr`）在多线程频繁抛出时会产生锁竞争，新版本的运行时做过优化。差异因平台和版本而异，要以实测为准。 |

所以常见的工程准则是：异常用于失败概率低、需要跨越多层调用传播的情况，不用于常规的控制流。

## `-fno-exceptions`

GCC 和 Clang 都提供 `-fno-exceptions`，它让编译器接受一种不符合标准的方言。在这种模式下编译上面的 `eh.cpp`，本机 Clang 23 报告：

```text
eh.cpp:6:16: error: cannot use 'throw' with exceptions disabled
eh.cpp:11:5: error: cannot use 'try' with exceptions disabled
```

这种模式不生成着陆点和 LSDA。本机 macOS 上测量的那个例子连 `__compact_unwind` 也省掉了。Linux 上是否仍生成 `.eh_frame` 取决于 `-fasynchronous-unwind-tables` 等其他选项，调试器和性能分析器也要用到它。

标准库中本应抛出异常的地方，libc++ 和 libstdc++ 通常改为直接终止程序，例如调用 `std::abort`。

与以异常模式编译的代码混用时要小心。异常如果穿过以 `-fno-exceptions` 编译的帧，那一帧的局部对象不会析构，因为那里没有着陆点；能不能穿过取决于是否还有 CFI。这是一类不容易发现的 bug。

许多大型代码库，如游戏引擎、某些浏览器和嵌入式项目，出于体积、可预测性或历史原因使用这种方言。它不属于标准 C++：[[intro.compliance]] 要求即使独立实现也要支持异常。

## MSVC 的模型

!!! warning "未在本机验证"
    本机没有 MSVC。以下内容来自公开文档，只做概述。

x86-64 和 ARM64 Windows 上，MSVC 同样采用表驱动的方案。函数的回溯信息记录在 PE 文件的 `.pdata` 和 `.xdata` 中。C++ 的抛出（`_CxxThrowException`）建立在 Windows **结构化异常处理**（SEH）之上，`__CxxFrameHandler` 系列函数起类似 personality routine 的作用，同样先搜索、后回溯。

32 位 x86 Windows 上的旧方案是在栈上注册：每个含 `try` 或需要清理的函数在进入时把一条记录挂到线程的链表上，执行中还要更新一个状态号。这在正常路径上有实际的指令开销，正是零开销模型要避免的。

编译选项 `/EHsc` 只捕获 C++ 异常，并假定 `extern "C"` 函数不抛出；`/EHa` 让 `catch (...)` 也能捕获 SEH 异常，如访问违例。

MSVC 抛出时异常对象位于栈上，handler 运行期间抛出点的栈帧还没有弹出。标准允许 `std::current_exception()` 返回异常对象的副本（[[propagation#9]]），这是现实原因之一。

## 小结

| 环节 | Itanium ABI 的实现 |
|---|---|
| 分配异常对象 | `__cxa_allocate_exception`：`malloc` 加紧急缓冲区，不调用 `operator new` |
| 启动抛出 | `__cxa_throw` → `_Unwind_RaiseException` |
| 查找 handler | 搜索阶段：每帧的 personality routine 读 LSDA 的调用点表、动作表、类型表 |
| 帧间移动 | `.eh_frame` 中的 DWARF CFI（macOS 上多为 compact unwind） |
| 析构局部对象 | 清理阶段跳入着陆点，析构后 `_Unwind_Resume` |
| 进入和离开 catch | `__cxa_begin_catch`、`__cxa_end_catch`，后者在最后一个 handler 退出时销毁异常对象 |
| 没有 handler | `std::terminate`，栈不回溯 |
| `noexcept` | 函数体外的 `catch (...)` 加 `std::terminate`，只回溯到这一帧 |
