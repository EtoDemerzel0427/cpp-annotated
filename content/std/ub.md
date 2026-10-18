---
title: 核心语言未定义行为（Annex F）
summary: 资料性附录 Annex F 把第 4–15 章里所有"明文写出"的核心语言 UB 编成 80 个带 stable name 的条目。本页讲清它是什么、不是什么、怎么用它，并给出全部条目的总表与 Clang 23 上 sanitizer 和常量求值的实测结果；逐条解析分布在七个子页面。
status: draft
covers: ub.general
related: intro.defs, intro.compliance, expr.const.core, ifndr, implimits, basic.life
tags: UB, 附录, 未定义行为, sanitizer, 常量求值
updated: 2026-10-18
---

"这算不算 UB？"是 language lawyer 被问得最多的问题。过去回答它要在一千多页的正文里翻找散落各处的"the behavior is undefined"。当前工作草案新增的 **Annex F（Core undefined behavior，核心语言未定义行为）**把这些散落的规则收集成了一份目录：每条一个 stable name、一句摘要、一个指回正文的链接和一段例子。

本页是这份目录的总览。逐条的解析——中文要点、正文出处、改写后可编译的例子、Clang 23 上 ASan/UBSan 与常量求值的实测——按附录自己的分组放在七个子页面：

| 小节 | 页面 | 条目数 | 主要内容 |
|---|---|---|---|
| F.2 | [[ub.basic]] | 22 | 隐式对象创建、生命周期、不确定值、失效指针、无序修改、数据竞争、前进保证、静态析构 |
| F.3 | [[ub.expr]] | 34 | 溢出、除零、严格别名、转换越界、cast 目标错误、越界指针、new/delete 不匹配、移位 |
| F.4 | [[ub.stmt]] | 3 | 流出非 void 函数末尾、协程流出末尾、静态局部变量递归初始化 |
| F.5 | [[ub.dcl]] | 9 | 修改 const 对象、volatile、引用绑定、协程 resume/destroy、`[[assume]]`、`[[noreturn]]` |
| F.6 | [[ub.class]] | 10 | 重复析构、构造/析构期间的纯虚调用、成员访问、虚调用、`typeid`、`dynamic_cast` |
| F.7 | [[ub.temp]] | 1 | 模板实例化无限递归 |
| F.8 | [[ub.except]] | 1 | 构造/析构函数的 function-try-block 处理器中访问成员 |

阅读本页前最好先熟悉 [[intro.defs]] 中的行为分类（UB、unspecified、implementation-defined、erroneous、IFNDR），以及 [[intro.compliance]] 对"实现必须做什么"的规定。

## 这份附录是什么（F.1 [ub.general]）

### 它收录什么

[ub.general] ¶1 给出了收录标准：从 Clause [intro] 到 Clause [cpp]（即第 4 章到第 15 章，整个**核心语言**部分）中，用下列七种措辞之一**明文写出**的未定义行为：

- *is undefined*
- *the behavior is undefined*
- *the behavior of the program is undefined*
- *has undefined behavior* / *have undefined behavior*
- *result has undefined behavior*
- *results in undefined behavior*

每个条目包含标题（stable name）、指向正文的交叉引用、对情形的摘要和示例代码；附录特别声明示例**不求穷尽**——它们只是触发该条 UB 的一种方式。

按章统计，80 个条目分布为：[basic] 22、[expr] 34、[stmt] 3、[dcl] 9、[class] 10、[temp] 1、[except] 1。[lex]、[module]、[over]、[cpp] 四章没有条目——这些章节里的违规要么是 ill-formed，要么是 IFNDR（见 [[ifndr]]）。

### 它不收录什么

- **隐式 UB**。¶1 明说"隐式的未定义行为不在本附录范围内"。[[defns.undefined]] 规定，标准对某种行为**没有给出定义**时，那也是 UB——例如在一个从未被描述过的情形下使用某个构造。这类 UB 没有一句话可以引用，自然也无法编目。
- **库的 UB**。范围止于 [cpp]，第 16 章 [library] 到第 33 章 [exec] 中的前置条件违例（例如对 `std::vector` 越界调用 `operator[]`）都不在其中。
- **错误行为**（*erroneous behavior*，EB）。EB 是有定义的行为，只是"错的"。附录唯一提到它的地方是 F.2.14：读取**不确定值**是 UB，读取**错误值**不是。
- **IFNDR**。违反"不要求诊断"的规则也让实现不受任何约束，但那是另一本目录：Annex G [[ifndr]]。

### 它的法律地位：资料性

Annex F 标注为 **(informative)**，即**资料性**附录。它不创造任何规则：一个行为是不是 UB，由正文决定。附录与正文矛盾时以正文为准；引用时也应引用正文段落，而不是附录条目。

为了让两边能互相找到，正文在每一处显式 UB 的句子后面都加了一个指向附录的标记，例如 [[basic.life#7]] 里的

> the pointer is used as the operand of a *delete-expression* ([ub:lifetime.outside.pointer.delete]),

在 eel.is 上点它就跳到附录条目；附录条目的"Specified in:"再链回正文。这种双向标记本身就很有用：在正文中搜索 `[ub:` 就能列出一节里的全部显式 UB。

!!! history "来历"
    Annex F 与 Annex G 都是 C++23 之后才加入工作草案的，C++23 及更早的标准里没有它们。编目核心语言 UB 的工作由 Shafik Yaghmour 长期推动，起点是提案 [[P1705]]（*Enumerating Core Undefined Behavior*）。stable name 带 `ub:` 前缀，与正文条款的 stable name 是两个命名空间：`[ub:expr.add.out.of.bounds]` 不是 [[expr.add]] 的子条款。

### 附录本身的毛病

既然是资料性的，附录就可能有错；读的时候要带着核对的习惯。在当前草案中我们注意到这些地方（各条细节见子页面）：

- **F.3.22 与 F.3.23 的摘要和例子互换了**：正文 [[expr.delete#2]] 把 `[ub:expr.delete.mismatch]` 挂在单对象 delete 那句上，附录的例子却是"对单对象 new 的结果用 `delete[]`"（见 [[ub.expr#expr.delete.mismatch]]）。
- **F.5.5 的例子其实没有 UB**：`int& ir1 = i3;` 是常量初始化，先于 `int i2 = ir1;` 的动态初始化完成（见 [[ub.dcl#dcl.ref.uninitialized.reference]]）。
- **F.5.7 的例子没有演示它的标题**：在 `current_value()` 里调用 `destroy()` 时协程处于挂起状态，那个例子真正的问题是销毁后再访问。
- **F.3.28 的例子注释**说在有无穷的浮点系统上 `1.0 / 0.0` "不是 UB"，但正文 [[expr.mul#4]] 的"除数为零即 UB"没有这个例外。
- **F.2.3 的例子**写的是 `new (&s+1) S()`：`&s + 1` 指向整个数组之后，与注释所说的"差 1 字节"不符，应为 `s + 1`。
- 若干例子有排版错误：`#include new>`、协程例子中 `suspend_always` 漏了 `std::`、F.3.21 示例去"替换"一个标准规定不可替换的 placement `operator new`。

## 三道防线：怎样真正发现这些 UB

### 第一道：常量求值

[[expr.const.core#2.8]] 规定，一个表达式若会求值"Clause [intro] 到 Clause [cpp] 中规定的具有未定义或错误行为的操作"，它就**不是核心常量表达式**。注意这个范围与 Annex F 的收录范围**一模一样**——Annex F 实际上就是"编译器在常量求值中必须抓住的东西"的清单。把可疑代码放进 `constexpr` 变量的初始化或 `static_assert`，是标准层面唯一**保证**能诊断核心 UB 的手段：

```cpp error
constexpr int f(int d) { return 1 / d; }
constexpr int x = f(0);   // error: 不是常量表达式（note: division by zero）
```

有两类例外：

- **runtime-undefined behavior**（[[g:runtime-undefined-behavior]]）：[[expr.const.core#3]] 规定，若违规属于这一类，表达式是否因此非常量由**实现定义**。Annex F 中有两条：`[[assume]]` 的假设为假（F.5.8，Clang 拒绝）与 `[[noreturn]]` 函数返回（F.5.9，Clang 接受）。
- **库的 UB**：[[expr.const.core#4]] 规定由库条款规定的 UB 是否使表达式非常量是**未指明**的。这也是 Annex F 不收库 UB 的一个呼应。

实现也会有缺口。本机 Clang 23 对 `i = i++ + i`（F.2.18）只发 `-Wunsequenced` 警告，常量求值照样算出了结果——按标准它不应是常量表达式。"constexpr 能过"不能作为"没有 UB"的证明。

### 第二道：sanitizer

运行时的 UB 只能靠工具在特定执行路径上碰到。下表汇总了本机（Clang 23.1.3，arm64 macOS）的实测，用于判断一类 UB "大概能不能被抓到"：

| 工具 | 开关 | 本页条目中能抓到的 |
|---|---|---|
| UBSan | `-fsanitize=undefined` | 有符号溢出、除零、`INT_MIN / -1`、移位越界、浮点转整数越界、`bool`/枚举的无效值、空指针解引用、未对齐构造、函数类型不匹配的调用、流出非 void 函数末尾、`[[assume]]` 为假、`[[noreturn]]` 返回、placement new 得到空指针 |
| UBSan vptr | `-fsanitize=vptr`（本机不在 `undefined` 默认集合里） | 多态类型的错误下行转换、在虚基类成员未构造时取其地址 |
| ASan | `-fsanitize=address` | 释放后使用、double free、越界访问、错误地址的 `free`；以及许多"类型错了"的 UB 的**后果**（越界读写） |
| ASan 选项 | `ASAN_OPTIONS=alloc_dealloc_mismatch=1`（macOS 默认关） | `new`/`delete[]` 形式不匹配 |
| TSan | `-fsanitize=thread` | 数据竞争 |
| TySan | `-fsanitize=type` | 严格别名违例 |

抓不到的同样值得记住：几乎所有"对象模型"层面的 UB——隐式创建无解、生命周期外的指针与 glvalue、联合复制、成员访问时类型不相似、指针算术类型不相似、构造/析构期间的种种限制——运行时都没有可检测的痕迹。MSan（未初始化读取）不支持 macOS，本文没有测试。

### 第三道：编译器警告

部分 UB 能在编译期被**静态**地看出来：`-Wreturn-type`（F.4.1、F.4.2）、`-Wunsequenced`（F.2.18）、`-Wmismatched-new-delete`（F.3.22、F.3.23）、`-Winvalid-noreturn`（F.5.9）、`-Wcall-to-pure-virtual-from-ctor-dtor`（F.6.2）。这些都只是警告，因为程序本身并不是非良构的——UB 是**执行**的属性，只有执行到那里才发生。

## 全部条目总表

"实测"一栏是 Clang 23 上的结果概括：列出能发现问题的工具；"常量求值"表示同样的操作放进常量求值时被拒绝；"无"表示 ASan/UBSan 运行无报告。具体输出见各条目。

### F.2 [basic]

| 条目 | 要点 | 正文 | 实测 |
|---|---|---|---|
| [[ub.basic#intro.object.implicit.create\|intro.object.implicit.create]] | 隐式创建对象无解 | [[intro.object#13]] | 无 |
| [[ub.basic#intro.object.implicit.pointer\|intro.object.implicit.pointer]] | 找不到合适的被创建对象 | [[intro.object#14]] | 无 |
| [[ub.basic#basic.align.object.alignment\|basic.align.object.alignment]] | 在未对齐的存储里创建对象 | [[basic.align#1]] | UBSan |
| [[ub.basic#lifetime.outside.pointer.delete\|lifetime.outside.pointer.delete]] | delete 生命周期已结束的对象 | [[basic.life#7.1]] | 无 |
| [[ub.basic#lifetime.outside.pointer.member\|lifetime.outside.pointer.member]] | 经此类指针访问成员 | [[basic.life#7.2]] | 常量求值 |
| [[ub.basic#lifetime.outside.pointer.virtual\|lifetime.outside.pointer.virtual]] | 此类指针转虚基类指针 | [[basic.life#7.3]] | 无 |
| [[ub.basic#lifetime.outside.pointer.dynamic.cast\|lifetime.outside.pointer.dynamic.cast]] | 此类指针做 `dynamic_cast` | [[basic.life#7.4]] | 无 |
| [[ub.basic#lifetime.outside.glvalue.access\|lifetime.outside.glvalue.access]] | 经此类 glvalue 访问对象 | [[basic.life#8.1]] | 常量求值 |
| [[ub.basic#lifetime.outside.glvalue.member\|lifetime.outside.glvalue.member]] | 经此类 glvalue 调用成员函数 | [[basic.life#8.2]] | 无 |
| [[ub.basic#lifetime.outside.glvalue.virtual\|lifetime.outside.glvalue.virtual]] | 此类 glvalue 绑定到虚基类引用 | [[basic.life#8.3]] | 无 |
| [[ub.basic#lifetime.outside.glvalue.dynamic.cast\|lifetime.outside.glvalue.dynamic.cast]] | 此类 glvalue 做 `dynamic_cast`/`typeid` | [[basic.life#8.4]] | 无 |
| [[ub.basic#original.type.implicit.destructor\|original.type.implicit.destructor]] | 隐式析构时存储里已换了类型 | [[basic.life#11]] | 无 |
| [[ub.basic#creating.within.const.complete.obj\|creating.within.const.complete.obj]] | 在 const 完整对象的存储里建对象 | [[basic.life#12]] | — |
| [[ub.basic#basic.indet.value\|basic.indet.value]] | 求值产生不确定值 | [[basic.indet#2]] | 常量求值 |
| [[ub.basic#basic.stc.alloc.dealloc.constraint\|basic.stc.alloc.dealloc.constraint]] | 替换的分配/释放函数违反契约 | [[basic.stc.dynamic.general#3]] | ASan（间接） |
| [[ub.basic#basic.stc.alloc.zero.dereference\|basic.stc.alloc.zero.dereference]] | 解引用零字节分配的结果 | [[basic.stc.dynamic.allocation#2]] | ASan |
| [[ub.basic#basic.compound.invalid.pointer\|basic.compound.invalid.pointer]] | 间接或释放失效指针 | [[basic.compound#6.1]] | ASan、常量求值 |
| [[ub.basic#intro.execution.unsequenced.modification\|intro.execution.unsequenced.modification]] | 无序的副作用 | [[intro.execution#10]] | 仅 `-Wunsequenced` |
| [[ub.basic#intro.races.data\|intro.races.data]] | 数据竞争 | [[intro.races#17]] | TSan |
| [[ub.basic#intro.progress.stops\|intro.progress.stops]] | 线程不再前进 | [[intro.progress#1]] | 无（`-O2` 生成陷阱指令） |
| [[ub.basic#basic.start.main.exit.during.destruction\|basic.start.main.exit.during.destruction]] | 静态析构期间调用 `std::exit` | [[basic.start.main#4]] | 无 |
| [[ub.basic#basic.start.term.use.after.destruction\|basic.start.term.use.after.destruction]] | 使用已销毁的块作用域静态变量 | [[basic.start.term#5]] | 无 |

### F.3 [expr]

| 条目 | 要点 | 正文 | 实测 |
|---|---|---|---|
| [[ub.expr#expr.expr.eval\|expr.expr.eval]] | 结果无定义或不可表示（溢出） | [[expr.pre#4]] | UBSan、常量求值 |
| [[ub.expr#expr.basic.lvalue.strict.aliasing.violation\|expr.basic.lvalue.strict.aliasing.violation]] | 违反严格别名 | [[basic.lval#11]] | TySan |
| [[ub.expr#expr.basic.lvalue.union.initialization\|expr.basic.lvalue.union.initialization]] | 联合的默认复制作用于非该联合对象 | [[basic.lval#11]] | 无 |
| [[ub.expr#expr.type.reference.lifetime\|expr.type.reference.lifetime]] | 求值引用时对应指针无效 | [[expr.type#1]] | ASan、常量求值 |
| [[ub.expr#conv.lval.valid.representation\|conv.lval.valid.representation]] | 读取无效值表示 | [[conv.lval#3]] | UBSan、常量求值 |
| [[ub.expr#conv.double.out.of.range\|conv.double.out.of.range]] | 浮点转换超出范围 | [[conv.double#2]] | IEEE 754 下不触发 |
| [[ub.expr#conv.fpint.float.not.represented\|conv.fpint.float.not.represented]] | 浮点转整数不可表示 | [[conv.fpint#1]] | UBSan、常量求值 |
| [[ub.expr#conv.fpint.int.not.represented\|conv.fpint.int.not.represented]] | 整数转浮点超出范围 | [[conv.fpint#2]] | IEEE 754 下不触发 |
| [[ub.expr#conv.ptr.virtual.base\|conv.ptr.virtual.base]] | 无效指针转虚基类 | [[conv.ptr#3]] | ASan（间接） |
| [[ub.expr#conv.member.missing.member\|conv.member.missing.member]] | 成员指针转到不含该成员的派生类 | [[conv.mem#2]] | 无 |
| [[ub.expr#expr.call.different.type\|expr.call.different.type]] | 经不兼容的函数类型调用 | [[expr.call#6]] | UBSan |
| [[ub.expr#expr.ref.member.not.similar\|expr.ref.member.not.similar]] | 成员访问时对象类型不相似 | [[expr.ref#10]] | 无 |
| [[ub.expr#expr.dynamic.cast.pointer.lifetime\|expr.dynamic.cast.pointer.lifetime]] | `dynamic_cast` 的指针不指向合适对象 | [[expr.dynamic.cast#7]] | 无 |
| [[ub.expr#expr.dynamic.cast.glvalue.lifetime\|expr.dynamic.cast.glvalue.lifetime]] | `dynamic_cast` 的 glvalue 不指代合适对象 | [[expr.dynamic.cast#7]] | — |
| [[ub.expr#expr.static.cast.base.class\|expr.static.cast.base.class]] | 引用下行转换目标错误 | [[expr.static.cast#2]] | vptr、常量求值 |
| [[ub.expr#expr.static.cast.enum.outside.range\|expr.static.cast.enum.outside.range]] | 转换到枚举时超出值范围 | [[expr.static.cast#8]] | UBSan（读取时）、常量求值 |
| [[ub.expr#expr.static.cast.fp.outside.range\|expr.static.cast.fp.outside.range]] | 显式浮点转换超出范围 | [[expr.static.cast#9]] | IEEE 754 下不触发 |
| [[ub.expr#expr.static.cast.downcast.wrong.derived.type\|expr.static.cast.downcast.wrong.derived.type]] | 指针下行转换目标错误 | [[expr.static.cast#10]] | vptr |
| [[ub.expr#expr.static.cast.does.not.contain.original.member\|expr.static.cast.does.not.contain.original.member]] | 成员指针转到无关的基类 | [[expr.static.cast#11]] | — |
| [[ub.expr#expr.unary.dereference\|expr.unary.dereference]] | 间接一个不指向对象的指针 | [[expr.unary.op#1]] | UBSan、常量求值 |
| [[ub.expr#expr.new.non.allocating.null\|expr.new.non.allocating.null]] | placement new 得到空指针 | [[expr.new#22]] | UBSan |
| [[ub.expr#expr.delete.mismatch\|expr.delete.mismatch]] | 单对象 delete 的操作数不来自单对象 new | [[expr.delete#2]] | 警告、ASan（需开选项）、常量求值 |
| [[ub.expr#expr.delete.array.mismatch\|expr.delete.array.mismatch]] | 数组 delete 的操作数不来自数组 new | [[expr.delete#2]] | 警告、ASan（需开选项）、常量求值 |
| [[ub.expr#expr.delete.dynamic.type.differ\|expr.delete.dynamic.type.differ]] | 无虚析构函数的多态删除 | [[expr.delete#3]] | 多继承时 ASan、常量求值 |
| [[ub.expr#expr.delete.dynamic.array.dynamic.type.differ\|expr.delete.dynamic.array.dynamic.type.differ]] | 数组的多态删除 | [[expr.delete#3]] | 无 |
| [[ub.expr#expr.mptr.oper.not.contain.member\|expr.mptr.oper.not.contain.member]] | `.*` 的对象不含该成员 | [[expr.mptr.oper#4]] | ASan（间接）、常量求值 |
| [[ub.expr#expr.mptr.oper.member.func.null\|expr.mptr.oper.member.func.null]] | `.*` 的成员指针为空 | [[expr.mptr.oper#6]] | ASan（SEGV）、常量求值 |
| [[ub.expr#expr.mul.div.by.zero\|expr.mul.div.by.zero]] | 除以零 | [[expr.mul#4]] | UBSan、常量求值 |
| [[ub.expr#expr.mul.representable.type.result\|expr.mul.representable.type.result]] | 商不可表示（`INT_MIN / -1`） | [[expr.mul#4]] | UBSan、常量求值 |
| [[ub.expr#expr.add.out.of.bounds\|expr.add.out.of.bounds]] | 创建越界指针 | [[expr.add#4.3]] | 常量求值（运行时仅在访问时报） |
| [[ub.expr#expr.add.sub.diff.pointers\|expr.add.sub.diff.pointers]] | 不同数组的指针相减 | [[expr.add#5.3]] | 常量求值 |
| [[ub.expr#expr.add.not.similar\|expr.add.not.similar]] | 指针算术类型与元素类型不相似 | [[expr.add#6]] | 无 |
| [[ub.expr#expr.shift.neg.and.width\|expr.shift.neg.and.width]] | 移位量为负或不小于位宽 | [[expr.shift#1]] | UBSan、常量求值 |
| [[ub.expr#expr.assign.overlap\|expr.assign.overlap]] | 赋值源与目标部分重叠 | [[expr.assign#7]] | 无 |

### F.4 [stmt]

| 条目 | 要点 | 正文 | 实测 |
|---|---|---|---|
| [[ub.stmt#stmt.return.flow.off\|stmt.return.flow.off]] | 流出非 void 函数末尾 | [[stmt.return#4]] | 警告、UBSan、常量求值 |
| [[ub.stmt#stmt.return.coroutine.flow.off\|stmt.return.coroutine.flow.off]] | 协程流出末尾而无 `return_void` | [[stmt.return.coroutine#3]] | 警告 |
| [[ub.stmt#stmt.dcl.local.static.init.recursive\|stmt.dcl.local.static.init.recursive]] | 静态局部变量递归初始化 | [[stmt.dcl#3]] | libc++abi 中止 |

### F.5 [dcl]

| 条目 | 要点 | 正文 | 实测 |
|---|---|---|---|
| [[ub.dcl#dcl.type.cv.modify.const.obj\|dcl.type.cv.modify.const.obj]] | 修改 const 对象 | [[dcl.type.cv#4]] | 只读段时 ASan、常量求值 |
| [[ub.dcl#dcl.type.cv.access.volatile\|dcl.type.cv.access.volatile]] | 以非 volatile glvalue 访问 volatile 对象 | [[dcl.type.cv#5]] | — |
| [[ub.dcl#dcl.ref.incompatible.function\|dcl.ref.incompatible.function]] | 函数引用绑定到不兼容的函数 | [[dcl.ref#6]] | UBSan（调用时） |
| [[ub.dcl#dcl.ref.incompatible.type\|dcl.ref.incompatible.type]] | 对象引用绑定到不可访问的对象 | [[dcl.ref#6]] | 无 |
| [[ub.dcl#dcl.ref.uninitialized.reference\|dcl.ref.uninitialized.reference]] | 引用初始化前被求值 | [[dcl.ref#6]] | ASan（SEGV） |
| [[ub.dcl#dcl.fct.def.coroutine.resume.not.suspended\|dcl.fct.def.coroutine.resume.not.suspended]] | resume 未挂起的协程 | [[dcl.fct.def.coroutine#8]] | ASan（SEGV） |
| [[ub.dcl#dcl.fct.def.coroutine.destroy.not.suspended\|dcl.fct.def.coroutine.destroy.not.suspended]] | destroy 未挂起的协程 | [[dcl.fct.def.coroutine#11]] | ASan |
| [[ub.dcl#dcl.attr.assume.false\|dcl.attr.assume.false]] | `[[assume]]` 为假（runtime-undefined） | [[dcl.attr.assume#1]] | UBSan、常量求值 |
| [[ub.dcl#dcl.attr.noreturn.eventually.returns\|dcl.attr.noreturn.eventually.returns]] | `[[noreturn]]` 函数返回（runtime-undefined） | [[dcl.attr.noreturn#2]] | 警告、UBSan；常量求值**接受** |

### F.6 [class]、F.7 [temp]、F.8 [except]

| 条目 | 要点 | 正文 | 实测 |
|---|---|---|---|
| [[ub.class#class.dtor.no.longer.exists\|class.dtor.no.longer.exists]] | 对已死对象再调析构函数 | [[class.dtor#18]] | ASan（若析构释放资源）、常量求值 |
| [[ub.class#class.abstract.pure.virtual\|class.abstract.pure.virtual]] | 构造/析构中虚调用纯虚函数 | [[class.abstract#6]] | 警告（直接调用时）、运行库中止 |
| [[ub.class#class.base.init.mem.fun\|class.base.init.mem.fun]] | 基类初始化完成前调用成员函数 | [[class.base.init#18]] | 无 |
| [[ub.class#class.cdtor.before.ctor\|class.cdtor.before.ctor]] | 构造开始前引用成员或基类 | [[class.cdtor#1]] | vptr（涉及虚基类时） |
| [[ub.class#class.cdtor.after.dtor\|class.cdtor.after.dtor]] | 析构完成后引用成员或基类 | [[class.cdtor#1]] | 无 |
| [[ub.class#class.cdtor.convert.pointer\|class.cdtor.convert.pointer]] | 构造前/析构后转换为基类指针 | [[class.cdtor#3]] | 无 |
| [[ub.class#class.cdtor.form.pointer\|class.cdtor.form.pointer]] | 构造前/析构后形成成员指针 | [[class.cdtor#3]] | 无 |
| [[ub.class#class.cdtor.virtual.not.x\|class.cdtor.virtual.not.x]] | 经"x 以外的部分"做虚调用 | [[class.cdtor#4]] | 无 |
| [[ub.class#class.cdtor.typeid\|class.cdtor.typeid]] | 构造/析构中 `typeid` 的静态类型不对 | [[class.cdtor#5]] | 无 |
| [[ub.class#class.cdtor.dynamic.cast\|class.cdtor.dynamic.cast]] | 构造/析构中 `dynamic_cast` 的静态类型不对 | [[class.cdtor#6]] | 无 |
| [[ub.temp#temp.inst.inf.recursion\|temp.inst.inf.recursion]] | 模板实例化无限递归 | [[temp.inst#18]] | 编译期 fatal error（深度上限） |
| [[ub.except#except.handle.handler.ctor.dtor\|except.handle.handler.ctor.dtor]] | function-try-block 处理器中访问成员 | [[except.handle#11]] | 无 |

## 常见误区

- **"附录里没有，所以不是 UB。"** 附录只收**显式**的核心语言 UB。隐式 UB 和库 UB 都不在里面，而它们同样是 UB。
- **"sanitizer 没报，所以没有 UB。"** 上表中"无"的条目占了将近一半，其中大多数在任何执行下都不会留下可检测的痕迹。
- **"`-O0` 下结果正确，所以没问题。"** 严格别名（F.3.2）、流出函数末尾（F.4.1）、线程不前进（F.2.20）、`[[noreturn]]` 返回（F.5.9）的例子都在 `-O2` 下改变了行为。UB 的后果主要来自优化器的推理，而不是硬件。
- **"附录条目就是规则。"** 它是资料性的摘要，而且有错（见上文）。引用规则时引正文段落。

## 思考题

!!! question "1. 为什么 Annex F 的收录范围与 [expr.const.core] ¶2.8 完全一致？"
    两者都写着"Clause [intro] through Clause [cpp]"。这只是巧合吗？

<details markdown="1">
<summary>展开查看答案与解析</summary>

不是巧合，而是同一个设计的两面。[[expr.const.core#2.8]] 要求实现在常量求值中识别"本文档 [intro] 到 [cpp] 中规定的 UB 与 EB"；[[expr.const.core#4]] 则把库 UB 的处理留成未指明。为了让"常量求值必须诊断哪些 UB"成为一个可检查的有限清单，就需要把这些 UB 一条条列出来——Annex F 正是这个清单的 UB 部分（附录只收 UB，不收 EB）。反过来，F.5.8 与 F.5.9 在正文中被写成 runtime-undefined，这个类别的作用就是让它们**不必**在常量求值中被检查：是否据此判定非常量由实现定义（[[expr.const.core#3]]）。

</details>

!!! question "2. F.3.30 与 F.2.17 看起来都是“坏指针”，区别在哪里？"
    `int a[10]; int* p = a + 11;` 和 `int* q = new int; delete q; q + 1;` 各是什么行为？

<details markdown="1">
<summary>展开查看答案与解析</summary>

`a + 11` 是**创建**越界指针，按 [[expr.add#4.3]] 直接 UB，哪怕从不解引用。`q + 1` 则不同：`q` 在 `delete` 之后成为在当前求值中**无效**的指针值，按 [[basic.compound#6]]，对它做间接或释放是 UB（F.2.17），而用于加法运算是**实现定义**的（¶6.2）。所以前者是 UB，后者的行为由实现定义——这是标准在"失效指针"问题上刻意留出的余地，因为很多真实代码会在释放后比较指针值。

</details>

## 小结

| 问题 | 答案 |
|---|---|
| Annex F 是规范性的吗？ | 不是，是资料性的；判定以正文为准 |
| 收录范围 | [intro] 到 [cpp] 中用七种措辞明文写出的 UB，共 80 条 |
| 不收录 | 隐式 UB、库 UB、EB、IFNDR（后者见 Annex G [[ifndr]]） |
| 如何互查 | 正文句末的 `[ub:…]` 标记 ↔ 附录条目的 "Specified in" |
| 标准保证的检测手段 | 常量求值（[[expr.const.core#2.8]]），runtime-undefined 两条除外 |
| 实用的检测手段 | UBSan（算术、空指针、无效值）、ASan（内存）、TSan（竞争）、TySan（别名）；对象模型类 UB 基本无法检测 |
