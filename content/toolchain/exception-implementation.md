---
title: C++ 异常是如何实现的
summary: Itanium C++ ABI 的表驱动异常处理：__cxa_allocate_exception/__cxa_throw、两阶段回溯（搜索 + 清理）、personality routine 与 LSDA、.eh_frame 中的 DWARF CFI、着陆点、__cxa_begin_catch/__cxa_end_catch；"零开销"的真实代价；noexcept 对代码生成的影响；-fno-exceptions；MSVC 模型概览
status: draft
order: 40
related: except, except.throw, except.handle, except.ctor, except.spec, except.special
tags: 异常, ABI, Itanium, 代码生成, 工具链
updated: 2026-10-18
---

标准第 14 章（[[except]]）只规定异常处理的**语义**：异常对象存在哪"未指定"（[[except.throw#4]]），找不到 handler 时是否回溯"由实现定义"（[[except.handle#8]]），`noexcept` 违约时可以"部分回溯"（[[except.terminate#2]]）。这些自由度都是为某种具体的实现方案留的。本页讲 GCC 和 Clang 在 Linux、macOS 等平台上使用的方案——**Itanium C++ ABI** 的异常处理（尽管名字里有 Itanium，它是今天几乎所有非 Windows 平台的 C++ ABI）——并用本机编译的汇编验证。

本页的汇编都来自本机 Homebrew Clang 23：x86-64 Linux 目标用 `clang++ -std=c++2c -O1 -S --target=x86_64-linux-gnu`（只生成汇编，不需要链接），macOS arm64 原生目标用于测量。

## 两层结构

Itanium 方案分为两层：

| 层 | 组件 | 职责 |
|---|---|---|
| 语言无关的**回溯库** | `_Unwind_RaiseException`、`_Unwind_Resume` 等（libgcc_s / LLVM libunwind / macOS 系统 libunwind） | 遍历调用栈的帧：根据 `.eh_frame` 中的 DWARF CFI 恢复每一帧的寄存器；对每一帧调用它的 personality routine |
| C++ 专用的**运行时** | `__cxa_*` 函数和 `__gxx_personality_v0`（libstdc++/libsupc++ 或 libc++abi） | 分配异常对象、理解 C++ 的类型匹配规则、解析 LSDA、维护"当前处理的异常" |

回溯库不懂 C++。它只知道"帧"和"每帧有一个 personality routine 可以问"——这使得 C、C++、其他语言的帧可以混在同一个调用栈里回溯。

## 抛出：`__cxa_allocate_exception` + `__cxa_throw`

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

`thrower` 的 x86-64 汇编（`-O1`，去掉了部分伪指令）：

```text
_Z7throweri:
        testl   %edi, %edi
        js      .LBB0_2
        retq                            # 正常路径：一个测试、一个返回
.LBB0_2:
        pushq   %rbx
        movl    %edi, %ebx
        movl    $4, %edi                # sizeof(Err)
        callq   __cxa_allocate_exception@PLT
        movl    %ebx, (%rax)            # 在返回的内存里构造异常对象（[except.throw]/3）
        leaq    _ZTI3Err(%rip), %rsi    # 第二个参数：typeid(Err)
        movq    %rax, %rdi              # 第一个参数：异常对象
        xorl    %edx, %edx              # 第三个参数：析构函数指针（Err 平凡析构 ⇒ 空）
        callq   __cxa_throw@PLT         # 不返回
```

对应标准：

- `__cxa_allocate_exception(size)` 分配异常对象的存储。它在用户可见的对象**之前**还分配一个运行时头部（`__cxa_exception`，含类型信息、析构函数指针、引用计数、handler 计数、链表指针以及回溯库需要的 `_Unwind_Exception`）。实现通常用 `malloc`，失败时退回到一个预分配的**紧急缓冲区**——这就是标准把存储方式定为"未指定"、并声明不调用全局 `operator new`（[[basic.stc.dynamic.allocation#5]]）的原因。
- 异常对象在这块内存里被**就地构造**（这里只是一条 `movl`，因为 `Err` 是聚合；对类类型这里是构造函数调用）。若构造抛出，编译器生成的清理代码调用 `__cxa_free_exception` 释放这块内存，原来的 `throw` 视为没有发生——对应 [[except.throw#6]] 中"未捕获"始于异常对象**初始化完成之后**。
- `__cxa_throw(obj, type_info*, destructor)` 记录类型和析构函数，把 `uncaughtExceptions` 计数加一（`std::uncaught_exceptions()` 读的就是它），然后调用 `_Unwind_RaiseException`。只有找不到 handler 时它才会返回，此时 `__cxa_throw` 调用 `std::terminate`。

注意正常路径（`x >= 0`）上**没有任何**与异常相关的指令。

## 两阶段回溯

`_Unwind_RaiseException` 分两遍遍历调用栈：

1. **搜索阶段**（search phase，`_UA_SEARCH_PHASE`）：从抛出点开始逐帧向外，对每一帧调用其 personality routine，问"你这里有能接住这个异常的 handler 吗？"。这一阶段**只读**——不执行任何析构函数、不修改任何帧。
2. **清理阶段**（cleanup phase，`_UA_CLEANUP_PHASE`）：若搜索阶段找到了 handler，再从抛出点开始逐帧向外，这次让 personality routine 把控制转入每一帧的**着陆点**（landing pad）执行清理（析构），直到到达找到 handler 的那一帧，转入 handler 本身。

如果搜索阶段走到栈底仍没有 handler，`_Unwind_RaiseException` 返回错误，`__cxa_throw` 调用 `std::terminate`——**栈完全没有被回溯**。这就是主流实现在 [[except.handle#8]] 的实现定义选择上选"不回溯"的原因，也是为什么未捕获异常导致的 core dump 里能看到完整的抛出点调用栈。

为什么要两遍而不是一遍？

- **调试友好**：没有 handler 时保持现场。
- **语义需要**：某些语言（以及早期 C++ 设计讨论中的"可恢复异常"）需要在决定回溯之前先知道有没有 handler。
- **代价**：每次抛出都要遍历栈两次，并且两遍都要解析 CFI 和 LSDA——这是异常抛出昂贵的主要原因之一。

## 帧的描述：`.eh_frame` 与 DWARF CFI

要从一个帧走到它的调用者，回溯库必须知道：这个函数在**当前这条指令**处，返回地址存在哪、栈指针偏移了多少、哪些被调用者保存寄存器被存到了栈的什么位置。这些信息由编译器以 **DWARF 调用帧信息**（Call Frame Information, CFI）的形式写进 `.eh_frame` 段。在汇编中它们是 `.cfi_*` 伪指令：

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

`llvm-dwarfdump --eh-frame` 可以把它们解码成表格，例如 `thrower` 的 FDE：

```text
  0x0: CFA=RSP+8: RIP=[CFA-8]
  0x6: CFA=RSP+16: RBX=[CFA-16], RIP=[CFA-8]
```

意思是：执行到偏移 6 之后，"规范帧地址"（CFA）是 `RSP+16`，`RBX` 保存在 `CFA-16`，返回地址在 `CFA-8`。回溯库就是靠解释这样的"表格程序"一帧一帧往外走的。

`.eh_frame` 中，每个函数一个 **FDE**（Frame Description Entry），若干函数共享一个 **CIE**（Common Information Entry）。对有 personality 的函数，CIE 的增强串（augmentation string）里带 `P`（personality）和 `L`（LSDA）——本机 dump 中可以看到 `Augmentation: "zPLR"`。

!!! note "macOS"
    在 Apple 平台上，编译器还生成 `__LD,__compact_unwind`，由链接器转换为更紧凑的 `__TEXT,__unwind_info`；能用紧凑编码描述的帧就不再需要 DWARF FDE。本机 arm64 目标文件中可以看到 `__compact_unwind` 和 `__gcc_except_tab` 两个段。机制不同，但两阶段模型、personality routine 和 LSDA 都一样。

## personality routine 与 LSDA

回溯库对每一帧调用 CIE 中记录的 **personality routine**。对 C++ 代码它是 `__gxx_personality_v0`（GCC 和 Clang 都用这个名字；libc++abi 与 libsupc++ 各有一份实现）。personality routine 读取该函数的 **LSDA**（Language-Specific Data Area，位于 `.gcc_except_table` 段），回答两个问题：

- 搜索阶段：当前指令所在的调用点，有没有能匹配这个异常类型的 handler？
- 清理阶段：当前调用点的着陆点在哪？要把哪个"选择子"（selector）告诉着陆点？

`catcher` 的 LSDA（Clang 生成的注释已经说得很清楚）：

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

LSDA 由三张表组成：

1. **调用点表**（call-site table）：把函数内的指令区间映射到"着陆点地址 + 动作链"。上面第 1 项说：在 `.Ltmp0`–`.Ltmp1` 之间（即 `call may_throw`）抛出的异常，跳到 `.Ltmp2`，执行动作 2。不在任何区间内的调用若抛出，personality routine 会调用 `std::terminate`——所以编译器会为每个可能抛出的调用都列出一项，即使"没有着陆点"。
2. **动作表**（action table）：动作 2 = "若匹配类型表第 1 项则选择子为 1，否则继续动作 1"；动作 1 = "清理"（cleanup，即只需执行析构然后继续回溯）。
3. **类型表**（type table）：第 1 项是 `typeid(Err)`。`0`（空指针）表示 `catch (...)`。

这就是 [[except.handle#3]] 的匹配规则在运行时的实现位置：personality routine 拿异常对象的 `type_info`（来自 `__cxa_throw` 的第二个参数）和类型表中 handler 的 `type_info` 比较。派生到基类的匹配依靠 `__si_class_type_info`/`__vmi_class_type_info` 中记录的基类列表（含 public/歧义信息）；指针匹配依靠 `__pointer_type_info` 中记录的 cv 限定和 `noexcept` 标志。这也解释了为什么匹配规则不能包含任意转换：运行时手里只有 `type_info`。

## 着陆点：析构与 catch

`catcher` 的代码（`-O1`）：

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
        cmpl    $1, %edx                # edx = 选择子；1 = 匹配了 Err
        jne     .LBB1_5                 # 不是 Err：只做清理
        movq    %rbx, %rdi
        callq   __cxa_begin_catch@PLT   # 返回指向异常对象的指针；handler 变为活动
        movl    (%rax), %ebx            # e.code
.Ltmp3:
        callq   __cxa_end_catch@PLT     # handler 退出
.Ltmp4:
        jmp     .LBB1_3                 # 继续执行：析构 g，返回
.LBB1_4:
.Ltmp5:
        movq    %rax, %rbx
.LBB1_5:                                # 清理着陆点
        leaq    15(%rsp), %rdi
        callq   _ZN5GuardD1Ev@PLT       # 栈回溯：析构 g（[except.ctor]/2）
        movq    %rbx, %rdi
        callq   _Unwind_Resume@PLT      # 继续向外回溯
```

逐项对照标准：

- **正常路径**：`call may_throw` 之后直接析构 `g` 并返回，没有任何检查——"零开销"。
- **着陆点**由 personality routine 在清理阶段跳入，`%rax` 是异常头指针，`%edx` 是选择子。
- **`__cxa_begin_catch`**：把异常标为已捕获（`uncaughtExceptions` 减一，[[except.throw#8]]）、handler 计数加一、压入"已捕获异常栈"（这个栈的栈顶就是[[except.handle#10]] 中的**当前处理的异常**），并返回异常对象地址。按引用捕获时 `e` 就绑定到这个地址；按值捕获时编译器在这之后调用拷贝构造函数。
- **`__cxa_end_catch`**：handler 退出。handler 计数减一；若为零且未被重抛，销毁异常对象（调用 `__cxa_throw` 时记录的析构函数）并释放内存——这正是 [[except.throw#4]] 的"潜在销毁点 4.1"。若有 `std::exception_ptr` 持有它，引用计数会推迟销毁（"潜在销毁点 4.2"）。
- 注意 `__cxa_end_catch` 本身也在调用点表里（第 3 项，着陆点 `.Ltmp5`）：异常对象的析构函数可能抛出，那时需要继续清理 `g`。
- **清理着陆点**：只析构 `g`，然后 `_Unwind_Resume` 把控制交回回溯库，继续处理更外层的帧。
- **`throw;`** 编译为 `__cxa_rethrow()`：把当前处理的异常标为"重抛"、重新计入未捕获，再次 `_Unwind_RaiseException`。不创建新对象（[[expr.throw#3]]）。

## `noexcept` 与代码生成

比较两个只差 `noexcept` 的函数：

```cpp title="nx.cpp"
struct Guard { ~Guard(); };
void may_throw(int);
void f(int x) noexcept { Guard g; may_throw(x); }
void h(int x)          { Guard g; may_throw(x); }
```

`h`（潜在抛出）的着陆点要析构 `g`，然后 `_Unwind_Resume`：

```text
.LBB2_2:
        movq    %rax, %rbx
        leaq    15(%rsp), %rdi
        callq   _ZN5GuardD1Ev@PLT
        movq    %rbx, %rdi
        callq   _Unwind_Resume@PLT
```

`f`（`noexcept`）的着陆点：

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

可以看到：

1. Clang 把 `noexcept` 实现为一个**包住整个函数体的 `catch (...)`**，handler 里调用 `std::terminate`。由于搜索阶段会**找到**这个"handler"，清理阶段会回溯到 `f` 为止——比 `f` 更深的帧被正常回溯。
2. `f` 自己的 `g` **没有**被析构：着陆点直接 terminate，省掉了清理代码。这正是 [[except.terminate#2]] 允许"部分回溯"的用处。本机运行验证见 [[except.special]]。
3. `__clang_call_terminate` 先调用 `__cxa_begin_catch` 再 `std::terminate`，使异常成为"当前处理的异常"——这对应 [[except.handle#9]] 中"因抛出而进入 `std::terminate` 时，隐式 handler 是活动的"，terminate 处理函数因此可以用 `std::current_exception()` 拿到它。

更大的收益在**调用方**：若被调用函数是 `noexcept` 的，调用点在 LSDA 中就不需要着陆点；若一个函数的所有调用都不会抛出，它可能完全不需要 LSDA 与 personality。

## "零开销"的真实代价

"零开销"（zero-cost）指的是**不抛出时**正常路径上没有额外的**指令**。它不意味着没有代价：

| 代价 | 说明 |
|---|---|
| 抛出极其昂贵 | 分配异常对象、两遍遍历栈、解析 CFI 与 LSDA、`type_info` 比较、动态加载的模块还要查找所属的 `.eh_frame`。本机（Apple M 系列，macOS，libc++abi）一个仅跨一层函数调用的 `throw`/`catch` 往返约 **3 µs**，同样结构的普通返回不到 1 ns——相差三个数量级以上。 |
| 二进制体积 | 着陆点代码、LSDA、CFI 都占空间。本机对一个调用 `vector::push_back` 和 `to_string` 的小函数，`-O2` 下 `__text` 段 820 字节，加 `-fno-exceptions` 后 532 字节，另外还省掉了 36 字节 `__gcc_except_tab` 与 224 字节 `__compact_unwind`。 |
| 抑制优化 | 每个可能抛出的调用点都是一条隐式的控制流边：编译器不能随意把内存写入移过可能抛出的调用（异常路径上它们可能被观察到），着陆点会延长变量的活跃区间、增加寄存器压力，也影响内联决策。 |
| 冷路径与缓存 | 着陆点通常被放到函数末尾或独立的冷段中（`-O2` 时 GCC/Clang 都会做一定的冷热分离），所以对指令缓存的影响一般不大，但不是零。 |
| 抛出时的全局锁 | 某些平台上，查找 `.eh_frame`（如 glibc 的 `dl_iterate_phdr`）会在多线程大量抛出时出现竞争；新版本的运行时对此做过优化。这一点因平台和版本差异很大，应以实测为准。 |

结论是常见的工程准则：**异常用于真正异常的情况**（失败概率低、需要跨越多层传播），不要用于常规控制流。

## `-fno-exceptions`

GCC 和 Clang 都提供 `-fno-exceptions`，它让编译器进入一种**非标准的方言**：

```text
eh.cpp:7:14: error: cannot use 'throw' with exceptions disabled
eh.cpp:12:3: error: cannot use 'try' with exceptions disabled
```

（本机 Clang 23 的诊断。）在这种模式下：

- 不生成着陆点和 LSDA；在本机 macOS 上测量的那个例子中连 `__compact_unwind` 都省掉了（Linux 上是否仍生成 `.eh_frame` 取决于 `-fasynchronous-unwind-tables` 等其他选项，调试器和性能分析器也会用到它）。
- 标准库中本应抛出异常的地方，libc++ 和 libstdc++ 通常改为直接终止程序（例如调用 `std::abort`）。
- 若链接了以异常模式编译的代码，异常穿过 `-fno-exceptions` 编译的帧时，那一帧的局部对象**不会**被析构（那里没有着陆点）；能否穿过取决于是否仍有 CFI。混用两种模式是常见的隐蔽 bug 来源。

许多大型代码库（游戏引擎、某些浏览器和嵌入式项目）出于体积、可预测性或历史原因使用这种方言。它不是 C++ 标准的一部分。

## MSVC 模型（概览）

!!! warning "以下内容来自公开文档与通常的了解，未在本机验证"
    本机没有 MSVC，下面只做高层描述。

- 在 x86-64 和 ARM64 Windows 上，MSVC 同样采用**表驱动**的方案：函数的回溯信息记录在 PE 文件的 `.pdata`/`.xdata` 中，C++ 的抛出（`_CxxThrowException`）建立在 Windows **结构化异常处理**（SEH）的基础设施之上，由 `__CxxFrameHandler` 系列函数充当类似 personality routine 的角色。它也是"先搜索、再回溯"的两阶段模型。
- 32 位 x86 Windows 上的旧方案是**基于栈上链表注册**的：每个带 try 或需要清理的函数在进入时把一个异常注册记录挂到线程的链表上，并在运行中更新一个"状态号"——这在正常路径上有真实的指令开销，正是"零开销"模型所要避免的。
- 编译选项 `/EHsc` 表示只捕获 C++ 异常，并假定 `extern "C"` 函数不抛出；`/EHa` 让 `catch (...)` 也能捕获 SEH 异常（如访问违例）。
- MSVC 的异常对象在抛出过程中位于**栈上**（handler 运行时抛出点的栈帧尚未被弹出），这也是标准允许 `std::current_exception()` **复制**异常对象（[[propagation#9]]）的现实原因之一。

## 小结

!!! summary
    - Itanium ABI：`__cxa_allocate_exception` 分配（不走 `operator new`）→ `__cxa_throw` → `_Unwind_RaiseException` 两阶段回溯（只读搜索 + 清理）。
    - 每帧的 personality routine（`__gxx_personality_v0`）读取 LSDA（调用点表、动作表、类型表）决定着陆点和 handler 匹配；回溯库靠 `.eh_frame` 的 DWARF CFI 在帧间移动。
    - 着陆点执行析构后 `_Unwind_Resume`，或进入 catch：`__cxa_begin_catch`/`__cxa_end_catch` 维护"当前处理的异常"并在最后一个潜在销毁点销毁异常对象。
    - 搜索失败 ⇒ 直接 `std::terminate`，不回溯；`noexcept` ⇒ 函数体外包一个 `catch (...)` + terminate，只回溯到该帧。
    - 零开销 = 正常路径零指令；代价体现在抛出时间、二进制体积和被抑制的优化上。
