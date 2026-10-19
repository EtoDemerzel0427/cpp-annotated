---
title: 核心语言未定义行为（Annex F）
summary: 资料性附录 Annex F 把核心语言正文中明文写出的 80 种未定义行为编成带 stable name 的目录；本页说明它收录什么、不收录什么、怎样用它查找规则，并汇总每一条在 Clang 23 上能否被 sanitizer 或常量求值发现。
status: done
covers: ub.general
papers: P1705
related: intro.defs, intro.compliance, expr.const.core, ifndr, basic.life
tags: UB, 附录, 未定义行为, sanitizer, 常量求值
updated: 2026-10-19
---

!!! tldr
    - Annex F 收录第 4 章到第 15 章（核心语言）中用 the behavior is undefined 等措辞明文写出的未定义行为，共 80 条，每条有一个 `[ub:…]` 形式的 stable name。
    - 它不收录隐式的 UB、标准库的 UB、错误行为和 IFNDR。附录里查不到，不代表不是 UB。
    - 附录是资料性的，不创造规则，个别例子还有错。判断和引用都以正文段落为准。
    - 常量求值是标准唯一保证能发现核心语言 UB 的手段，它的检查范围与 Annex F 的收录范围相同。
    - 运行时工具各管一类：UBSan 管算术和无效值，ASan 管内存，TSan 管数据竞争；对象模型层面的 UB 大多无法检测。

**未定义行为**（undefined behavior，UB，[[defns.undefined]]）是标准对结果不作任何要求的行为。正文里，这样的规则散落在上千页中，Annex F 把核心语言部分明文写出的那些收集成一份目录。每个条目有一个 stable name，例如 `[ub:expr.add.out.of.bounds]`，还有一个指回正文的链接、一句摘要和一段例子。这些 stable name 带 `ub:` 前缀，与正文条款的 stable name 是两个命名空间：`[ub:expr.add.out.of.bounds]` 不是 [[expr.add]] 的子条款。

逐条的解析放在七个子页面，每条给出正文出处、改写后可以编译的例子，以及 Clang 23 上 sanitizer 和常量求值的实测：

| 小节 | 页面 | 条目数 | 主要内容 |
|---|---|---|---|
| F.2 | [[ub.basic]] | 22 | 隐式对象创建、生命周期、不确定值、失效指针、无序修改、数据竞争、前进保证、静态析构 |
| F.3 | [[ub.expr]] | 34 | 溢出、除零、严格别名、转换越界、错误的下行转换、越界指针、new 与 delete 不匹配、移位 |
| F.4 | [[ub.stmt]] | 3 | 流出非 void 函数末尾、协程流出末尾、静态局部变量递归初始化 |
| F.5 | [[ub.dcl]] | 9 | 修改 const 对象、volatile、引用绑定、协程 resume 和 destroy、`[[assume]]`、`[[noreturn]]` |
| F.6 | [[ub.class]] | 10 | 重复析构、构造和析构期间的纯虚调用、成员访问、虚调用、`typeid`、`dynamic_cast` |
| F.7 | [[ub.temp]] | 1 | 模板实例化无限递归 |
| F.8 | [[ub.except]] | 1 | 构造函数和析构函数的 function-try-block 处理器中访问成员 |

## 收录范围（[ub.general]）

¶1 Annex F 收录从 [intro] 到 [cpp]（第 4 章到第 15 章，即整个核心语言）中用下列措辞之一明文写出的未定义行为：

- ¶1.1–¶1.3 *is undefined*、*the behavior is undefined*、*the behavior of the program is undefined*；
- ¶1.4–¶1.7 *has undefined behavior*、*have undefined behavior*、*result has undefined behavior*、*results in undefined behavior*。

每个条目包含标题、交叉引用、情形摘要和示例代码。示例只是触发这条 UB 的一种方式，不求穷尽。80 个条目按章分布为：[basic] 22、[expr] 34、[stmt] 3、[dcl] 9、[class] 10、[temp] 1、[except] 1。[lex]、[module]、[over]、[cpp] 四章没有条目，那里的违规要么是非良构，要么是 IFNDR（非良构但不要求诊断，见 [[ifndr]]）。

下面几类都不在附录里，但同样需要当心：

- **隐式的 UB**。¶1 明确说隐式的未定义行为不在范围内。按 [[defns.undefined]]，标准没有给出定义的行为也是 UB，这类 UB 没有一句话可以引用，也就无法编目。
- **标准库的 UB**。范围止于 [cpp]，第 16 章到第 33 章的前置条件违例（比如 `std::vector::operator[]` 越界）都不在其中。
- **错误行为**（erroneous behavior，EB）。EB 是有定义的行为，只是被标准认定为错误。附录唯一提到它的地方是 F.2.14：读取不确定值是 UB，读取错误值不是。
- **IFNDR**。违反不要求诊断的规则时，标准对整个程序也不作要求，但它们另有一份目录 Annex G（[[ifndr]]）。

## 附录与正文的关系

Annex F 和收录 IFNDR 的 Annex G 都是 C++23 之后才加入工作草案的，编目工作源自提案 [[P1705]]。Annex F 是资料性（informative）附录，不创造任何规则。一个行为是不是 UB 由正文决定，两者矛盾时以正文为准，引用时也应引用正文段落。

两边可以互相查找。正文在每一处明文写出的 UB 后面都加了指向附录的标记，例如 [[basic.life#7]] 中的这一句：

> the pointer is used as the operand of a *delete-expression* ([ub:lifetime.outside.pointer.delete]),

附录条目的 Specified in 一栏再链回正文。所以在一节正文里搜索 `[ub:`，就能列出这一节的全部显式 UB。

附录可能有错，读的时候应当对照正文。当前草案中有以下几处（细节见子页面）：

- F.2.4 的摘要仍是旧的措辞，只针对带非平凡析构函数的类类型；当前正文 [[basic.life#7.1]] 已经去掉这个限定（见 [[ub.basic#lifetime.outside.pointer.delete]]）。
- F.2.17 的摘要说间接或调用释放函数都是 UB，当前正文 [[basic.compound#6.1]] 只把间接列为 UB；重复释放的问题由 `operator delete` 的前置条件处理（见 [[ub.basic#basic.compound.invalid.pointer]]）。
- F.3.22 与 F.3.23 的摘要和例子对调了。正文 [[expr.delete#2]] 把 `[ub:expr.delete.mismatch]` 挂在单对象 delete 那一句上，附录的例子却是对单对象 new 的结果用 `delete[]`（见 [[ub.expr#expr.delete.mismatch]]）。
- F.5.5 的例子其实没有 UB。`int& ir1 = i3;` 是常量初始化，先于 `int i2 = ir1;` 的动态初始化完成（见 [[ub.dcl#dcl.ref.uninitialized.reference]]）。
- F.5.7 的例子没有演示它的标题。在 `current_value()` 中调用 `destroy()` 时协程处于挂起状态，例子真正的问题是销毁之后再访问。
- F.3.28 的例子注释说，在能表示无穷的浮点系统上 `1.0 / 0.0` 不是 UB，但正文 [[expr.mul#4]] 的除数为零即 UB 没有这个例外。
- F.2.3 的例子写的是 `new (&s+1) S()`。`&s + 1` 指向整个数组之后，与注释所说的差 1 字节不符，应为 `s + 1`。
- F.3.21 的例 1 替换了 placement 形式的 `operator new`，而标准规定这个函数不可替换（[[new.delete.placement]]）。

## 怎样发现这些 UB

### 常量求值

```cpp error
constexpr int f(int d) { return 1 / d; }
constexpr int x = f(0);  // error: 不是常量表达式（note: division by zero）
```

[[expr.const.core#2.8]] 规定，会求值 [intro] 到 [cpp] 中规定的未定义或错误行为的表达式，不是核心常量表达式。这个范围与 Annex F 的收录范围完全相同。所以把可疑代码放进 `constexpr` 变量的初始化或 `static_assert`，是标准层面唯一保证能诊断核心语言 UB 的手段。

有两类例外：

- **运行时未定义行为**（runtime-undefined behavior，[[g:runtime-undefined-behavior]]）。[[expr.const.core#3]] 规定，求值只因这类行为出问题时，表达式是否为核心常量表达式由实现定义。Annex F 中有两条属于这一类：`[[assume]]` 的假设为假（F.5.8，Clang 拒绝），以及 `[[noreturn]]` 函数返回（F.5.9，Clang 接受）。
- **标准库的 UB**。[[expr.const.core#4]] 规定，求值库条款规定的 UB 时，表达式是否为常量是未指定的。这与 Annex F 不收录库 UB 相呼应。

实现也会有遗漏。Clang 23 对 `constexpr int f(int i) { i = i++ + i; return i; }` 只给出 `-Wunsequenced` 警告，常量求值照样算出了 `f(1)` 的结果，而按标准它不是常量表达式。因此 constexpr 能通过，不能证明没有 UB。

### sanitizer

运行时的 UB 只能靠工具在某条执行路径上碰到。下表汇总了本机（Clang 23.1.3，arm64 macOS）的实测，可以用来估计一类 UB 能不能被抓到：

| 工具 | 开关 | 能抓到的条目 |
|---|---|---|
| UBSan | `-fsanitize=undefined` | 有符号溢出、除零、`INT_MIN / -1`、移位越界、浮点转整数越界、`bool` 和枚举的无效值、空指针解引用、未对齐的构造、经不兼容函数类型的调用、流出非 void 函数末尾、`[[assume]]` 为假、`[[noreturn]]` 函数返回、placement new 得到空指针 |
| UBSan vptr | `-fsanitize=vptr`（本机不在 `undefined` 的默认集合里） | 多态类型的错误下行转换、在虚基类成员未构造时取其地址 |
| ASan | `-fsanitize=address` | 释放后使用、重复释放、越界访问、对错误的地址调用 `free`，以及许多类型错误的 UB 造成的越界读写 |
| ASan 选项 | `ASAN_OPTIONS=alloc_dealloc_mismatch=1`（macOS 上默认关闭） | `new` 与 `delete[]` 形式不匹配 |
| TSan | `-fsanitize=thread` | 数据竞争 |
| TySan | `-fsanitize=type` | 违反严格别名规则 |

几乎所有对象模型层面的 UB 都抓不到：隐式创建无解、生命周期之外的指针和 glvalue、联合的复制、成员访问时类型不相似、指针算术中类型不相似、构造和析构期间的种种限制。它们在运行时不留下可检测的痕迹。MSan（检测未初始化读取）不支持 macOS，本页没有测试。

### 编译器警告

有些 UB 在编译期就能静态地看出来：`-Wreturn-type`（F.4.1、F.4.2）、`-Wunsequenced`（F.2.18）、`-Wmismatched-new-delete`（F.3.22、F.3.23）、`-Winvalid-noreturn`（F.5.9）、`-Wcall-to-pure-virtual-from-ctor-dtor`（F.6.2）。它们只能是警告，因为程序本身是良构的：UB 是执行的属性，只有执行到那里才发生。

## 全部条目

实测一栏概括 Clang 23 上的结果：列出能发现问题的工具；常量求值表示同样的操作在常量求值中被拒绝；无表示 ASan 和 UBSan 运行时都没有报告。具体输出见各条目。


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
| [[ub.basic#basic.compound.invalid.pointer\|basic.compound.invalid.pointer]] | 间接访问失效指针 | [[basic.compound#6.1]] | ASan、常量求值 |
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
| [[ub.dcl#dcl.attr.noreturn.eventually.returns\|dcl.attr.noreturn.eventually.returns]] | `[[noreturn]]` 函数返回（runtime-undefined） | [[dcl.attr.noreturn#2]] | 警告、UBSan；常量求值接受 |

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

## 常见误解

!!! pitfall "附录里没有，所以不是 UB"
    附录只收核心语言中明文写出的 UB。隐式的 UB 和标准库的 UB 都不在里面，它们同样是 UB。

!!! pitfall "sanitizer 没报，所以没有 UB"
    上面的表中，实测为无的条目接近一半，其中大多数在任何执行下都不会留下可检测的痕迹。

!!! pitfall "-O0 下结果正确，所以没问题"
    严格别名（F.3.2）、流出函数末尾（F.4.1）、线程不前进（F.2.20）、`[[noreturn]]` 函数返回（F.5.9）的例子都在 `-O2` 下改变了行为。UB 的后果主要来自优化器的推理，而不是硬件。

## 思考题

!!! question "1. 为什么 Annex F 的收录范围与 [expr.const.core] ¶2.8 完全一致？"
    两处都写着 Clause [intro] through Clause [cpp]，这是巧合吗？

<details markdown="1">
<summary>答案</summary>

不是巧合。[[expr.const.core#2.8]] 要求实现在常量求值中识别 [intro] 到 [cpp] 中规定的 UB 和 EB，[[expr.const.core#4]] 则把库 UB 的处理留成未指定。要让常量求值必须诊断哪些 UB 成为一份可以核对的有限清单，就需要把这些 UB 一条条列出来，Annex F 正是这份清单的 UB 部分。F.5.8 和 F.5.9 被写成运行时未定义行为，作用就是让它们不必在常量求值中检查：是否因此判定为非常量由实现定义（[[expr.const.core#3]]）。
</details>

!!! question "2. F.3.30 和 F.2.17 都和坏指针有关，区别在哪里？"
    `int a[10]; int* p = a + 11;` 和 `int* q = new int; delete q; q + 1;` 各是什么行为？

<details markdown="1">
<summary>答案</summary>

`a + 11` 创建了一个越界指针，按 [[expr.add#4.3]] 直接是 UB，哪怕从不解引用。`q` 在 `delete` 之后成为在当前求值中无效的指针值。按 [[basic.compound#6]]，对它做间接是 UB（F.2.17），而用它做加法、比较是实现定义的。所以前者是 UB，后者的行为由实现定义。标准在失效指针上留出这个余地，是因为很多真实代码会在释放后比较指针值。
</details>
