---
title: 非良构，不要求诊断（Annex G）
summary: 资料性附录 Annex G 把核心语言中所有"no diagnostic required"的规则编成 45 个带 stable name 的条目。本页逐条讲解规则内容、为什么标准不要求诊断（跨翻译单元、不可判定、保留名、解析器历史包袱），以及 Clang 23 与链接器在实践中对每一条做了什么。
status: draft
covers: *
related: ub, intro.compliance, intro.defs, basic.def.odr, temp.res, module.unit
tags: IFNDR, 附录, ODR, 模板, 模块, 链接
updated: 2026-10-18
---

**IFNDR**（*ill-formed, no diagnostic required*，非良构、不要求诊断）是 C++ 行为分类里最阴险的一种。它首先是**非良构**：程序违反了规则，不是一个合法的 C++ 程序（[[g:ifndr]]）。但标准又不要求实现发出诊断，于是编译器可以一声不吭地生成一个可执行文件——而按 [[intro.compliance.general#2.2]]，对这样的程序"本文档不对实现施加任何要求"。也就是说，IFNDR 的后果比 UB 更彻底：UB 只让**执行到那里的那次运行**失去约束，IFNDR 让**整个程序**失去约束，不管那段代码是否会被执行。

当前工作草案新增的 **Annex G（Ill-formed, no diagnostic required）**把这些规则收集成了 45 个条目。本页覆盖整个附录：先讲清附录本身与"为什么不要求诊断"，再逐条讲解。姊妹篇 [[ub]] 是 Annex F（核心语言 UB）的目录。

## 这份附录是什么（G.1 [ifndr.general]）

[ifndr.general] ¶1 给出了收录标准：从 Clause [intro] 到 Clause [cpp] 中，用以下措辞标出的规则：

- *no diagnostic is required*
- *no diagnostic required*
- *a diagnostic is required only if*

第三种措辞值得注意：它表示规则**有时**要求诊断、有时不要求。典型例子是 ODR：同一实体在不同翻译单元中的定义不一致，若它附属于命名模块并且前一个定义在后一个定义处可达，就必须诊断（编译器此时看得见两份定义）；否则不要求。

每个条目包含 stable name（`ifndr:` 前缀）、指向正文的交叉引用、对情形的摘要和示例，示例不求穷尽。和 Annex F 一样，Annex G 是**资料性**（*informative*）的，判定以正文为准；正文在每条规则后面加了 `([ifndr:…])` 标记指向附录条目。Annex F 与 G 都是 C++23 之后才加入工作草案的。

按章统计：[lex] 1、[basic] 9、[expr] 1、[stmt] 1、[dcl] 9、[module] 4、[class] 2、[over] 1、[temp] 14、[cpp] 3。

## 为什么不要求诊断

把 45 条放在一起看，标准放弃诊断要求的理由可以归成四类。理解这四类，比记住每一条更重要。

| 类别 | 原因 | 典型条目 |
|---|---|---|
| **需要全程序视野** | 违规只在把多个翻译单元放在一起时才存在，而编译器一次只看一个 TU；链接器又只看到符号，看不到源代码 | ODR 的各条、语言链接不一致、`alignas`/`[[noreturn]]`/`[[indeterminate]]`/默认实参/契约说明符跨 TU 不一致、显式特化或偏特化在别的 TU 中、实例化点在不同 TU 中含义不同 |
| **不可判定或代价过高** | 判断"两个表达式是否在所有模板实参下等价""一个 requirement 是否对所有实参都替换失败"等价于判定程序语义 | `temp.over.link.equiv.not.equiv`、`expr.prim.req.always.sub.fail`、约束满足性在不同点不同 |
| **保留给实现的名字** | 标准库头文件本身就要使用这些名字；编译器难以可靠地区分"用户代码"和"实现代码" | 保留标识符、保留模块名、保留字面量后缀 |
| **历史与实现分歧** | 要求诊断会强迫某些实现重写解析器或名字查找，委员会选择容忍 | 类作用域内名字含义改变、语句歧义消解时绑定不同、宏展开产生 `defined` |

实践中的推论：

- **链接器是最后一道（也是很弱的一道）防线。** 非 inline 实体的重复定义会被链接器发现（`duplicate symbol`），缺失定义会报 `Undefined symbols`；但 inline 函数、模板实例化、虚表这类以"弱符号/COMDAT"形式发出的实体，链接器只会**任选其一**，不比较内容——ODR 违规在这里完全沉默。
- **优化等级会改变"能不能发现"。** 缺少定义的函数若调用点被优化删掉，链接就成功了（见 G.3.2）；inline 函数在一个 TU 里被内联、在另一个 TU 里没有，同一程序会同时用到两个版本。
- **专门的工具。** GCC 在 LTO 时可以用 `-Wodr` 比较各 TU 中类型与虚表的定义（这是 GCC 文档中的功能，本机没有 GCC，未验证）。Clang 在模块场景下会做 ODR 检查（相关开关如 `-fskip-odr-check-in-gmf`/`-fno-skip-odr-check-in-gmf` 出现在本机 `clang++ --help` 中）。对传统的头文件 + 多 TU 构建，Clang 没有等价的跨 TU 检查。

以下各条的"实测"均为 Clang 23.1.3（arm64 macOS，Apple ld）上的观察。

## 第 [lex] 章：词法约定 {#lex}

### G.2.1 [ifndr:lex.name.reserved] {#lex.name.reserved}

**使用保留给实现的标识符** · 正文 [[lex.name#4]]

含双下划线 `__` 的标识符、以下划线加大写字母开头的标识符在任何地方都保留给实现；以下划线开头的标识符在全局命名空间中保留。使用它们是 IFNDR。不要求诊断的原因很现实：标准库头文件里满是 `__x`、`_Tp` 这样的名字，编译器很难判断一个名字是"用户写的"还是"实现写的"。

```cpp ifndr
int _z;            // IFNDR：全局作用域中以 _ 开头

int main() {
  int __x = 0;     // IFNDR：以 __ 开头
  int _Y = 0;      // IFNDR：_ 后跟大写字母
  int x__y = 0;    // IFNDR：包含 __
  return __x + _Y + x__y + _z;
}
```

**实测**：默认无任何诊断（`-Wall -Wextra -pedantic` 也没有）。显式开启 `-Wreserved-identifier` 后四处都有警告，例如 `identifier '_z' is reserved because it starts with '_' at global scope`。详见 [[lex.name]]。

## 第 [basic] 章：基础 {#basic}

### G.3.1 [ifndr:basic.link.consistent.types] {#basic.link.consistent.types}

**同一实体的多个声明种类或类型不一致，且彼此不可达** · 正文 [[basic.link#11]]

声明同一实体的两个声明必须一致：都声明变量则类型相同，都声明函数则类型相同，模板的 *template-head* 等价，等等。若两个声明互相**可达**（例如在同一 TU 中，或通过 import），编译器看得见，必须诊断；只有"互不可达"时才是 IFNDR。

```cpp title="M.cppm"
export module M;
void g();                       // #1
void h();                       // #2
template <typename T> int j;    // #3
```

```cpp title="N.cppm"
export module N;
int g();                        // 与 #1 同一实体？类型不同
namespace h {}                  // 与 #2 同一实体？不都是命名空间
template <int X> int j;         // 与 #3 同一实体？template-head 不等价
```

```cpp title="user.cpp" ifndr
import M;
import N;   // 附录：因上述三对声明互相矛盾而 IFNDR
```

!!! lawyer "附录这个例子有个漏洞"
    按 [[basic.link#8]]，不同 TU 中的两个声明要声明"同一实体"，必须都具有模块链接或外部链接，**并且附属于同一模块**（¶8.3）。`M` 的接口单元中的 `g` 附属于模块 `M`，`N` 中的 `g` 附属于模块 `N`，它们根本不是同一实体，也就谈不上"不一致"。要让这个例子成立，这些声明应附属于**全局模块**——例如分别写在两个头文件中、由两个互不包含的 TU 各自包含（或放在各自的全局模块片段里）。那时它们具有外部链接、附属于同一个（全局）模块，是同一实体；两个声明互不可达，矛盾无从诊断，于是 IFNDR。

### G.3.2 [ifndr:basic.def.odr.minimum.one.def] {#basic.def.odr.minimum.one.def}

**odr-use 了没有定义的函数或变量** · 正文 [[basic.def.odr#12]]

程序中每个被 odr-use（[[g:odr-use]]，在被丢弃语句之外）的函数或变量必须至少有一个定义。定义可能在任何 TU 里，所以编译器无法诊断；链接器通常能发现——但"通常"取决于调用是否真的出现在目标代码中。

```cpp ifndr
int f();   // 从未定义

int main(int argc, char**) {
  if (argc > 100 && argc < 50) f();   // 永远不会执行，但 f 被 odr-use 了
}
```

**实测**：`-O0` 链接失败（`Undefined symbols for architecture arm64`）；`-O2` 下条件被折叠、调用被删除，**链接成功**。同一个非良构程序，换个优化等级就"变好了"——这正是不能要求诊断的原因。

附录的例子则是一个**单个 TU 就能看出**的特例：函数的类型涉及无链接的局部类，它不可能在别的 TU 中定义。Clang 对此直接报错：`function 'g' is used but not defined in this translation unit, and cannot be defined in any other translation unit because its type does not have linkage`。

```cpp error
auto f() {
  struct A {};
  return A{};
}
decltype(f()) g();
auto x = g();   // error（Clang 选择诊断）：g 无法在任何 TU 中定义
```

### G.3.3 [ifndr:basic.def.odr.injected.match] {#basic.def.odr.injected.match}

**一个 TU 用注入声明定义，另一个 TU 用普通定义** · 正文 [[basic.def.odr#15]]

C++26 的静态反射允许在常量求值中通过 `std::meta::define_aggregate` 等**注入**声明（[[expr.const.reflect]]）。若一个 TU 中某个类由注入声明定义，另一个 TU 中的定义也必须是具有相同"特征序列"的注入声明。

```cpp title="tu1.cpp"
#include <meta>
struct S;
consteval { std::meta::define_aggregate(^^S, {}); }   // #1：注入的定义
```

```cpp title="tu2.cpp" ifndr
struct S {};   // IFNDR：这里是普通定义，而 #1 是注入声明
```

**实测**：Clang 23 尚未实现静态反射（`^^int` 无法解析），无法测试。

### G.3.4 [ifndr:basic.def.odr.maximum.one.def] {#basic.def.odr.maximum.one.def}

**非 inline、非模板的函数或变量在多个 TU 中有定义** · 正文 [[basic.def.odr#16.1]]

这是 ODR 最基本的一半：普通函数和变量全程序只能有一个定义。若它们附属于命名模块且前一个定义可达，则必须诊断。

```cpp title="a.cpp"
int x = 1;
int f() { return 1; }
```

```cpp title="b.cpp" ifndr
int x = 2;              // IFNDR：x 的第二个定义
int f() { return 2; }   // IFNDR：f 的第二个定义
int main() {}
```

**实测**：这一条链接器能抓：`duplicate symbol '_x'`、`duplicate symbol 'f()'`。普通的强符号重复定义是链接器的本职工作；IFNDR 的定性是为了覆盖那些链接器看不到的情况（例如两份定义都被内联、不发出符号，或者用了 `-Wl,-z,muldefs` 之类的选项）。附录的例子用的是两个模块分区，各自定义 `f()`：因为两份定义互不可达，同样是 IFNDR。

### G.3.5 [ifndr:basic.def.odr.definition.matches] {#basic.def.odr.definition.matches}

**允许多处定义的实体，各处定义不一致** · 正文 [[basic.def.odr#16.2]]

inline 函数与变量、类、模板等允许在多个 TU 中各有一份定义，但这些定义必须"相同"：相同的记号序列、名字查找到相同的实体、lambda 产生相同的闭包类型……（[[basic.def.odr#16]] 之后的一长串要求）。这是 ODR 最难察觉的一半。

```cpp title="tu1.cpp"
inline void f() {}          // #1
inline void g() {}          // #2
inline void h() {[]{}();}   // #3
namespace { int i = 0; }
inline void j() {++i;}      // #4
```

```cpp title="tu2.cpp" ifndr
inline void f() {}          // OK：与 #1 相同
inline void g() {;}         // IFNDR：记号序列与 #2 不同
inline void h() {[]{}();}   // IFNDR：闭包类型与 #3 中的不同
namespace { int i = 0; }
inline void j() {++i; }     // IFNDR：i 指代的是另一个 TU 的匿名命名空间中的实体
```

注意 `h` 与 `j`：两份定义**逐字相同**，却仍然违反 ODR——前者因为在非模板 inline 函数中每个 lambda 表达式产生唯一的闭包类型，后者因为匿名命名空间里的 `i` 在每个 TU 中是不同的实体。

**实测**：链接无任何诊断，链接器从各 TU 的 COMDAT 中任选一份。[[intro.defs]] 中给出了一个实测例子：同一 inline 函数在两个 TU 中返回不同值，`-O0` 下结果取决于链接顺序，`-O2` 下两个版本同时出现在同一次运行中。

### G.3.6 [ifndr:basic.def.odr.unnamed.enum.same.type] {#basic.def.odr.unnamed.enum.same.type}

**同一作用域中可达的多个无名枚举，首个枚举量同名却不是同一类型** · 正文 [[basic.def.odr#20]]

没有名字、也没有用于链接目的的 typedef 名的枚举，在不同 TU 之间靠**第一个枚举量的名字**来认定"是不是同一个"。若程序某处同时可达两个这样的定义，它们必须是同一个类型。

```cpp title="a.h"
enum { a };
```

```cpp title="b.h"
enum { a, b };
```

```cpp title="main.cpp" ifndr
import "a.h";
import "b.h";
auto n = decltype(a)::b;   // IFNDR：此处可达两个首枚举量都叫 a 的无名枚举，但它们不是同一类型
```

### G.3.7 [ifndr:basic.contract.vastart.contract.predicate] {#basic.contract.vastart.contract.predicate}

**在契约断言的谓词中调用 va_start** · 正文 [[basic.contract.general#3]]

C++26 契约断言的谓词可能被求值零次、一次或多次（取决于求值语义），在其中调用 `va_start` 这种改变函数状态的宏没有意义。

```cpp ifndr
#include <cstdarg>

void f(int n, ...) {
  va_list args;
  contract_assert((va_start(args, n), true));   // IFNDR
}
```

**实测**：Clang 23 尚未实现契约（`contract_assert` 与 `pre(...)` 都无法解析），无法测试。

### G.3.8 [ifndr:basic.contract.handler.replacing.nonreplaceable] {#basic.contract.handler.replacing.nonreplaceable}

**在违约处理函数不可替换的平台上声明替换函数** · 正文 [[basic.contract.handler#3]]

契约违约处理函数 `::handle_contract_violation` 是否可替换由**实现定义**。在不可替换的平台上，一个"可以充当替换品"的声明是 IFNDR——同一份代码在一个平台上合法、在另一个平台上非良构，这也是不要求诊断的原因之一。

```cpp ifndr
#include <contracts>
void handle_contract_violation(const std::contracts::contract_violation& violation);
// 若处理函数不可替换：IFNDR
```

### G.3.9 [ifndr:class.member.lookup.name.refers.diff.decl] {#class.member.lookup.name.refers.diff.decl}

**类中使用的名字，在类完成后重新查找会得到不同结果** · 正文 [[class.member.lookup#6]]

在类定义中某处使用名字 N 时查找到的声明，必须与在类的**完整类上下文**中查找 N 的结果相同。否则同一个名字在类的前半段和后半段（以及成员函数体中）含义不同。不要求诊断，是因为这需要在类结束时对每一个已使用的名字重新查找一遍。

```cpp ifndr
struct foo {};

struct bar {
  foo* m_foo;
  foo* foo() { return m_foo; }   // IFNDR：返回类型中的 foo 指 ::foo，
                                 // 但在 bar 的完整作用域中 foo 指成员函数 bar::foo
};
```

```cpp ifndr
struct B { static int f(); };

struct D : public B {
  using B::f;
  int g(decltype(f()) x) { return 0; }   // IFNDR：此处 f() 是 B::f()（int），
  static float f();                       // 而在 D 的完整作用域中 f() 会选 D::f()（float）
};
```

**实测**：Clang 对两个例子都没有任何诊断。（GCC 对第一种情况会报 "changes meaning" 错误，这是实现之间可以合法地不同的典型例子。）

## 第 [expr] 章：表达式 {#expr}

### G.4.1 [ifndr:expr.prim.req.always.sub.fail] {#expr.prim.req.always.sub.fail}

**requirement 对任何模板实参替换都会失败** · 正文 [[expr.prim.req.general#5]]

*requires-expression* 中的一个 requirement 若**无论模板实参是什么**都会替换失败，程序 IFNDR。这类似于模板定义中"不存在任何有效特化"的规则（[[temp.res.general]]）：编译器可以早早报错，也可以不报。判断"对所有实参都失败"在一般情况下不可判定。

```cpp ifndr
template <typename T> concept C = requires {
  new int[-(int)sizeof(T)];   // IFNDR：数组长度永远为负
};
```

**实测**：Clang 不诊断；`static_assert(!C<int>)` 通过——对具体实参，替换失败只是让 requirement 不满足。

## 第 [stmt] 章：语句 {#stmt}

### G.5.1 [ifndr:stmt.ambig.bound.diff.parse] {#stmt.ambig.bound.diff.parse}

**解析时模板实参中的名字绑定到了正在解析的声明本身** · 正文 [[stmt.ambig#3]]

表达式语句与声明的歧义（[[stmt.ambig]]）按纯语法方式消解：先"试探性解析"（*trial parse*），确定是声明后再正式解析。若正式解析时，模板实参中的某个名字被查找绑定到了**正在解析的这个声明**（而试探解析时它绑定到别处），程序 IFNDR。

```cpp ifndr
template <int N> struct A { const static int a = 20; };
template <> struct A<100> { using a = char; };

const int x = 10;

int main() {
  using T = const int;
  T(x)
  (100), (y)(A<x>::a);   // IFNDR：试探解析时 A<x> 中的 x 是全局 x（10），
                         // 正式解析时它绑定到本行刚声明的局部 x（100）
}
```

**实测**：Clang 接受，只给出未使用变量的警告。

## 第 [dcl] 章：声明 {#dcl}

### G.6.1 [ifndr:dcl.constinit.specifier.not.reachable] {#dcl.constinit.specifier.not.reachable}

**constinit 出现在初始化声明不可达的声明上** · 正文 [[dcl.constinit#1]]

`constinit` 若出现在某个变量的任一声明上，就必须出现在它的**初始化声明**上——编译器只有在初始化声明处才能检查"是否常量初始化"。别的 TU 中带 `constinit` 的 `extern` 声明，初始化声明那一侧根本看不见。

```cpp title="tu1.cpp"
int x = 5;   // x 的初始化声明，没有 constinit
```

```cpp title="tu2.cpp" ifndr
#include <cstdio>
extern constinit int x;   // IFNDR：带 constinit 的声明在初始化声明处不可达
int main() { std::printf("%d\n", x); }
```

**实测**：编译、链接均无诊断，打印 `5`。

### G.6.2 [ifndr:dcl.inline.missing.on.definition] {#dcl.inline.missing.on.definition}

**一个定义域中声明为 inline，另一个定义域的末尾看不到 inline 声明** · 正文 [[dcl.inline#4]]

具有外部或模块链接的函数/变量，若在某个**定义域**（[[g:definition-domain]]）中被声明为 inline，那么在它被声明的每个定义域的末尾都必须能看到一个 inline 声明。

```cpp title="tu1.cpp"
inline int f();
int g() { return f(); }
```

```cpp title="tu2.cpp" ifndr
#include <cstdio>
int f() { return 17; }   // IFNDR：此 TU 末尾看不到 f 的 inline 声明
int g();
int main() { std::printf("%d\n", g()); }
```

**实测**：TU1 得到一条警告 `inline function 'f' is not defined [-Wundefined-inline]`，链接成功并打印 `17`——TU1 期待一个 COMDAT 的 `f`，TU2 恰好提供了一个强符号。

### G.6.3 [ifndr:dcl.fct.default.inline.same.defaults] {#dcl.fct.default.inline.same.defaults}

**inline 函数在不同 TU 末尾累积的默认实参不同** · 正文 [[dcl.fct.default#4]]

默认实参在**调用处**由调用方 TU 代入，所以各 TU 的默认实参不一致时，函数本身毫不知情。

```cpp title="tu1.cpp"
inline int f(int x, int y = 2);
inline int f(int x = 1, int y);     // 累积后：f(1, 2)
inline int f(int x, int y) { return x * 10 + y; }
int from1() { return f(); }
```

```cpp title="tu2.cpp" ifndr
#include <cstdio>
inline int f(int x = 3, int y = 4); // IFNDR：累积后是 f(3, 4)，与 tu1 不同
inline int f(int x, int y) { return x * 10 + y; }
int from1();
int main() { std::printf("%d %d\n", from1(), f()); }
```

**实测**：无诊断，打印 `12 34`——两个 TU 各用各的默认实参。

### G.6.4 [ifndr:dcl.contract.func.mismatched.contract.specifiers] {#dcl.contract.func.mismatched.contract.specifiers}

**同一函数在不同 TU 中的首次声明，契约说明符不一致** · 正文 [[dcl.contract.func#4]]

同一 TU 中的重声明必须与可达的首次声明有相同的 `pre`/`post`（这可以诊断）；不同 TU 中**各自的首次声明**之间也必须一致，这就无法诊断了（除非附属于命名模块）。

```cpp title="tu1.cpp"
int f(int x) pre(x >= 0);   // IFNDR：另一 TU 的首次声明没有 pre
int g(int x) pre(x == 0);   // IFNDR：与另一 TU 的 pre 不同
int h(int x) pre(x <= 0);   // OK
```

```cpp title="tu2.cpp" ifndr
int f(int x);
int g(int x) pre(x != 0);
int h(int y) pre(y <= 0);   // OK：参数名不同不影响等价性
```

**实测**：Clang 23 尚未实现契约，无法测试。

### G.6.5 [ifndr:dcl.fct.def.replace.bad.replacement] {#dcl.fct.def.replace.bad.replacement}

**可替换函数的替换品不合规** · 正文 [[dcl.fct.def.replace#1]]

`operator new`/`operator delete`、契约违约处理函数等**可替换函数**（[[dcl.fct.def.replace]]）的替换品不得为 inline、必须附属于全局模块、具有 C++ 语言链接、返回类型正确，且若标准库头文件中有对应声明，必须能作为它的合法重声明。替换发生在"程序启动前"，本质是链接层面的事。

```cpp ifndr
#include <new>
#include <contracts>

extern "C"   // IFNDR：语言链接错误
inline       // IFNDR：inline
int          // IFNDR：返回类型错误
handle_contract_violation(const std::contracts::contract_violation&) {}

void* operator new(decltype(sizeof(0))) noexcept;   // IFNDR：异常说明与 <new> 中的声明不一致
```

**实测**：包含了 `<new>` 时，`operator new` 那一行能被 Clang 诊断：`exception specification in declaration does not match previous declaration`（这时它在同一 TU 中就是一个非法的重声明）。没有包含 `<new>` 时则无从比较。

### G.6.6 [ifndr:dcl.link.mismatched.language.linkage] {#dcl.link.mismatched.language.linkage}

**两个互不可达的声明给同一实体不同的语言链接** · 正文 [[dcl.link#6]]

```cpp title="tu1.cpp"
extern "C" { void f() {} }
```

```cpp title="tu2.cpp" ifndr
extern "C++" { void f(); }   // IFNDR：与 tu1 的语言链接不同
int main() { f(); }
```

**实测**：链接失败：`Undefined symbols … "f()"`——C 链接的 `f` 导出为 `_f`，C++ 链接的 `f()` 被修饰为 `__Z1fv`，两者对不上。这里是名字修饰"顺带"暴露了问题；若函数从未被调用，就不会有任何诊断。

### G.6.7 [ifndr:dcl.align.diff.translation.units] {#dcl.align.diff.translation.units}

**同一实体在不同 TU 中的对齐说明符不一致** · 正文 [[dcl.align#6]]

若定义声明带 *alignment-specifier*，非定义声明要么指定等价的对齐、要么不写；若任一声明带对齐说明符，每个定义声明都必须指定等价的对齐。跨 TU 时不要求诊断。

```cpp title="tu1.cpp"
struct S { int x; } s, *p = &s;
```

```cpp title="tu2.cpp" ifndr
struct alignas(16) S;   // IFNDR：S 的定义没有 alignas(16)
extern S* p;
int main() { return p != nullptr; }
```

**实测**：编译、链接、运行都无诊断。TU2 会假定 `*p` 按 16 字节对齐，并可能据此生成对齐访问指令。

### G.6.8 [ifndr:dcl.attr.indet.mismatched.declarations] {#dcl.attr.indet.mismatched.declarations}

**函数参数的 [[indeterminate]] 在不同 TU 的首次声明中不一致** · 正文 [[dcl.attr.indet#2]]

C++26 的 `[[indeterminate]]` 放在参数上，影响的是**调用方**如何处理未初始化的实参（错误值还是不确定值，见 [[basic.indet]]），所以所有首次声明必须一致。

```cpp title="tu1.cpp"
int h(int x [[indeterminate]]);   // IFNDR：与另一 TU 的首次声明不一致
```

```cpp title="tu2.cpp" ifndr
int h(int x);                     // IFNDR
```

**实测**：Clang 23 尚未实现 `[[indeterminate]]`（`unknown attribute 'indeterminate' ignored`）。

### G.6.9 [ifndr:dcl.attr.noreturn.trans.unit.mismatch] {#dcl.attr.noreturn.trans.unit.mismatch}

**函数在一个 TU 中带 [[noreturn]]，在另一个 TU 中不带** · 正文 [[dcl.attr.noreturn#1]]

同一 TU 内的规则是可诊断的：若任一声明带 `[[noreturn]]`，首次声明必须带。跨 TU 时不要求诊断。

```cpp title="tu1.cpp"
[[noreturn]] void f() { throw 0; }
```

```cpp title="tu2.cpp" ifndr
void f();   // IFNDR：没有 noreturn
int main() { try { f(); } catch (int) { return 0; } }
```

**实测**：无诊断，正常运行。这一条的危害方向值得想清楚：若是 TU2 带 `[[noreturn]]` 而定义会返回，TU2 中调用点之后的代码就可能被优化成"不可达"。

## 第 [module] 章：模块 {#module}

### G.7.1 [ifndr:module.unit.reserved.identifiers] {#module.unit.reserved.identifiers}

**模块名以 std 加数字开头，或含保留标识符** · 正文 [[module.unit#1]]

以 `std` 后跟零个或多个数字开头的模块名、含保留标识符的模块名都是保留的，不得出现在 *module-declaration* 中。标准库自己就要提供 `std` 与 `std.compat` 模块。

```cpp ifndr
export module std0;   // IFNDR：std 后跟数字
```

**实测**：Clang 对此有专门的警告，默认开启：`'std0' is a reserved name for a module [-Wreserved-module-identifier]`；`std`、`_Test`、`te__st` 同样如此。（附录例子里还有 `module module;`——[[module.unit#1]] 另有一句禁止 `module`/`import` 作为模块名中的标识符，那一句是要求诊断的。）

### G.7.2 [ifndr:module.unit.named.module.no.partition] {#module.unit.named.module.no.partition}

**命名模块没有恰好一个主模块接口单元** · 正文 [[module.unit#2]]

一个命名模块必须**恰好**有一个不带分区名的接口单元（主模块接口单元）。一个也没有或有多个，都是 IFNDR——各模块单元分别编译，没有哪一步能看到"全部单元"。

```cpp title="a1.cppm"
export module A;
```

```cpp title="a2.cppm" ifndr
export module A;   // IFNDR：模块 A 的第二个主模块接口单元
```

附录给的例子是 `module A;` 后跟 `export import :Internals;`。那里的 `export` 出现在模块实现单元中，违反的是 [[module.interface]] 中**要求诊断**的规则；它大概想表达"模块 A 只有实现单元、没有主接口单元"，但并没有很好地演示本条。

### G.7.3 [ifndr:module.unit.unexported.module.partition] {#module.unit.unexported.module.partition}

**接口分区没有被主模块接口单元（直接或间接）导出** · 正文 [[module.unit#3]]

同一段还规定一个命名模块不得有两个同名分区（同样不要求诊断）。

```cpp title="M.cppm"
export module M;
export import :A;
```

```cpp title="M-A.cppm"
export module M:A;   // OK：被 M 直接导出
export import :B;
```

```cpp title="M-B.cppm"
export module M:B;   // OK：被 M 间接导出
```

```cpp title="M-C.cppm" ifndr
export module M:C;   // IFNDR：没有被 M 直接或间接导出
```

**实测**：用 `--precompile` 分别编译各单元，Clang 不发出任何诊断。

### G.7.4 [ifndr:module.private.frag.other.module.units] {#module.private.frag.other.module.units}

**有私有模块片段的模块还有别的模块单元** · 正文 [[module.private.frag#1]]

私有模块片段（`module :private;`）的设计意图是"单文件模块"：接口和实现写在一个文件里，片段之后的内容对导入方不可达。所以带私有模块片段的模块单元必须是该模块**唯一**的单元。

```cpp title="M.cppm"
export module M;
module :private;
```

```cpp title="M-A.cppm" ifndr
module M:A;   // IFNDR：M 已有私有模块片段，不能再有其他模块单元
```

## 第 [class] 章：类 {#class}

### G.8.1 [ifndr:class.base.init.delegate.itself] {#class.base.init.delegate.itself}

**构造函数直接或间接委托给自己** · 正文 [[class.base.init#6]]

委托构造形成环，运行时就是无限递归。环可能跨越多个构造函数，而这些构造函数可能定义在不同 TU 中，所以不要求诊断。

```cpp ifndr
struct C {
  C(int) {}                // #1：非委托构造函数
  C() : C(42) {}           // #2：委托给 #1
  C(char c) : C(42.0) {}   // #3：IFNDR，与 #4 构成环
  C(double d) : C('a') {}  // #4：IFNDR，与 #3 构成环
};
```

**实测**：所有构造函数都在类内定义时，Clang 能看到整个环并**报错**：`constructor for 'C' creates a delegation cycle [-Wdelegating-ctor-cycles]`。"不要求诊断"不妨碍实现在看得见的时候诊断——Clang 把这条警告默认设为错误。

### G.8.2 [ifndr:class.virtual.pure.or.defined] {#class.virtual.pure.or.defined}

**非纯虚函数没有定义** · 正文 [[class.virtual#12]]

类中声明的虚函数必须有定义、或声明为纯虚，或两者兼有。虚函数即使从未被调用也是 odr-use 的（虚表要引用它），而定义可能在任何 TU 中。

```cpp ifndr
class A {
  virtual void f();   // 既没定义也不是纯虚
};

int main() {
  A a;   // IFNDR
}
```

**实测**：链接失败，但错误信息是 `Undefined symbols … "vtable for A"`，而不是 `A::f`——Itanium ABI 把虚表发在定义"关键函数"（第一个非 inline、非纯虚的虚函数，这里是 `f`）的 TU 中，`f` 没有定义，虚表就没人发。这是最经典的令人困惑的链接错误之一。

## 第 [over] 章：重载 {#over}

### G.9.1 [ifndr:over.literal.reserved] {#over.literal.reserved}

**字面量运算符使用保留的后缀** · 正文 [[over.literal#1]]

不以下划线开头的字面量后缀保留给标准（[[usrlit.suffix]]），例如 `s`、`h`、`i`、`if`。另外，字面量运算符的名字若写成 `operator"" _Bq`（引号与后缀之间有空格，这种写法已弃用），`_Bq` 是一个独立的标识符，而以下划线加大写字母开头的标识符是保留的。

```cpp ifndr
double operator"" _Bq(long double);   // IFNDR：_Bq 是保留标识符（且此写法已弃用）
double operator""_Bq(long double);    // OK：无空格时 _Bq 是 ud-suffix，不受标识符保留规则约束
```

**实测**：第一行只得到弃用警告：`identifier '_Bq' preceded by whitespace in a literal operator declaration is deprecated`。附录的另一个例子 `float operator ""E(const char*);` 会被 Clang 当作错误：`invalid suffix on literal; C++11 requires a space between literal and identifier [-Wreserved-user-defined-literal]`，并附带警告 `user-defined literal suffixes not starting with '_' are reserved`。

## 第 [temp] 章：模板 {#templates}

模板是 IFNDR 的重灾区：14 条，占全部条目的三分之一。根源有两个：模板在定义处与实例化处分两阶段处理，两处看到的"世界"可能不同；同一个特化又可能在多个 TU 中各实例化一次，标准要求它们一致却无从检查。

### G.10.1 [ifndr:temp.pre.reach.def] {#temp.pre.reach.def}

**隐式实例化的模板在定义域末尾看不到定义，又没有显式实例化** · 正文 [[temp.pre#10]]

函数模板、类模板的成员函数、变量模板、类模板的静态数据成员，若在某个定义域中被隐式实例化，其定义必须在该定义域末尾可达——除非对应特化在某个 TU 中被显式实例化。这就是"模板要写在头文件里"的标准出处。

```cpp title="a.h"
template <typename T>
void f();
```

```cpp title="a.cpp" ifndr
#include "a.h"
int main() {
  f<int>();   // IFNDR：隐式实例化 f<int>，但定义不可达，也没有显式实例化
}
```

**实测**：链接失败：`Undefined symbols … "void f<int>()"`。若另一个 TU 恰好有 `template void f<int>();` 显式实例化，程序就是合法的——这正是 IFNDR 而非 ill-formed 的原因。

### G.10.2 [ifndr:temp.arg.template.sat.constraints] {#temp.arg.template.sat.constraints}

**模板模板形参实例化时，本应选中的偏特化不可达** · 正文 [[temp.arg.template#2]]

```cpp ifndr
template <class T> struct A { int x; };

template <template <class U> class V> struct C {
  V<int> y;
  V<int*> z;
};

C<A> c;   // 此处实例化 A<int*>，用的是主模板

template <class T> struct A<T*> { long x; };   // IFNDR：若可达，A<int*> 本应选中它
```

**实测**：Clang 不诊断。

### G.10.3 [ifndr:temp.constr.atomic.equiv.but.not.equiv] {#temp.constr.atomic.equiv.but.not.equiv}

**程序的含义取决于两个"功能等价但不等价"的原子约束是否等价** · 正文 [[temp.constr.atomic#2]]

约束的包含关系（*subsumption*）按原子约束的**等价**（记号层面相同）来判定，而不是按语义。`2 * N` 与 `N * 2` 对所有 `N` 结果相同（**功能等价**，[[g:functionally-equivalent]]），但不**等价**。若决议的结果取决于它们是否被视为等价，程序 IFNDR——判断两个任意表达式是否功能等价是不可判定的。

```cpp ifndr
template <int N> concept Add1 = true;

template <unsigned N> void f2() requires Add1<2 * N>;
template <unsigned N> int  f2() requires Add1<N * 2> && true;

void h2() {
  f2<0>();   // IFNDR：选哪个取决于 Add1<2 * N> 与 Add1<N * 2> 是否等价
}
```

**实测**：Clang 不诊断，选中了返回 `int` 的第二个重载（`static_assert(__is_same(decltype(f2<0>()), int))` 通过）。

### G.10.4 [ifndr:temp.constr.atomic.sat.result.diff] {#temp.constr.atomic.sat.result.diff}

**同一原子约束、同一组模板实参，在程序不同点的满足结果不同** · 正文 [[temp.constr.atomic#3]]

最常见的触发方式是用 concept 检测"类型是否完整"：前后两次检查之间类型被补全了。

```cpp ifndr
template <class T>
concept Complete = sizeof(T) == sizeof(T);

struct A;
static_assert(!Complete<A>);   // #1：A 不完整，不满足
struct A {};
static_assert(Complete<A>);    // IFNDR：满足结果与 #1 不同
```

**实测**：Clang **缓存**了第一次的满足结果，于是第二个 `static_assert` 失败（`static assertion failed`）。实现"诊断"了问题，但诊断的理由是错的——它只是在用旧答案。这正好说明了为什么标准要把这种程序判为非良构：允许缓存是实现上的刚需。

### G.10.5 [ifndr:temp.constr.normal.invalid] {#temp.constr.normal.invalid}

**约束规范化时的替换产生无效类型或表达式** · 正文 [[temp.constr.normal#1]]

规范化（*normalization*）把 concept-id 展开成原子约束，并把实参代入各原子约束的**参数映射**。若代入产生了无效的类型或表达式——即使那个原子约束永远不会被求值——程序 IFNDR。

```cpp ifndr
template <typename T> concept A = T::value || true;
template <typename U> concept B = A<U*>;   // OK：映射 T ↦ U*
template <typename V> concept C = B<V&>;   // IFNDR：映射会形成 V&*（指向引用的指针）
```

附录条目在正文中的锚点位于 ¶1.5.3.1（折叠表达式中 concept 模板形参包的展开），而它的例子演示的是 ¶1.4.2 中措辞相同的另一句规则——两处都是"no diagnostic is required"。

**实测**：只定义这三个 concept 时 Clang 不诊断；一旦使用 `C<int>`，报错 `'type name' declared as a pointer to a reference of type 'V &'`。

### G.10.6 [ifndr:temp.spec.partial.general.partial.reachable] {#temp.spec.partial.general.partial.reachable}

**本应使用的偏特化在使用处不可达** · 正文 [[temp.spec.partial.general#1]]

```cpp ifndr
template <typename T> class X {
public:
  void foo() {}
};

template class X<void*>;   // IFNDR：显式实例化时，下面的偏特化还不可达

template <typename T> class X<T*> {
public:
  void baz();
};
```

**实测**：Clang 不诊断。

### G.10.7 [ifndr:temp.over.link.equiv.not.equiv] {#temp.over.link.equiv.not.equiv}

**程序的含义取决于两个功能等价但不等价的构造是否等价** · 正文 [[temp.over.link#7]]

G.10.3 的一般形式。两个函数模板声明是"同一个"还是"两个重载"，按 *template-head* 与签名中表达式的**等价**判定；`I+10` 与 `I+1+2+3+4` 功能等价但不等价。

```cpp ifndr
template <int I> struct A {};

// IFNDR：两者功能等价但不等价
template <int I> void f(A<I>, A<I+10>);
template <int I> void f(A<I>, A<I+1+2+3+4>);
```

**实测**：Clang 把它们当作两个不同的模板，声明本身不诊断；给出定义并调用 `f<0>(A<0>{}, A<10>{})` 时报 `call to 'f' is ambiguous`。

### G.10.8 [ifndr:temp.res.general.default.but.not.found] {#temp.res.general.default.but.not.found}

**实例化点可达、但查找找不到的默认实参会改变程序含义** · 正文 [[temp.res.general#2]]

模板中非依赖名字在**定义处**查找。若一个后来添加的声明引入了默认实参，它在实例化点可达，但对模板而言"看不见"；如果考虑它会改变结果，程序 IFNDR。

```cpp ifndr
#include <cstdio>

void f(long) { std::puts("f(long)"); }      // #1
void f(int, int) { std::puts("f(int,int)"); } // #2
template <typename T> void g(T t) { f(t); }
void f(int, int = 0);                        // #3：给 #2 加上默认实参

void h() { g(0); }   // IFNDR：若考虑 #3 会选 f(int, int = 0)，模板的查找却选了 #1
```

**实测**：Clang 不诊断，调用打印 `f(long)`。

### G.10.9 [ifndr:temp.point.diff.pt.diff.meaning] {#temp.point.diff.pt.diff.meaning}

**同一特化的不同实例化点按 ODR 给出不同含义** · 正文 [[temp.point#7]]

一个特化可以在多个 TU 中各有实例化点（函数模板在同一 TU 中还可能有多个）。若不同实例化点下它的含义不同，程序 IFNDR。经典例子是"类型是否完整"的 trait：

```cpp title="a.h"
#include <type_traits>

template <typename T, typename = void>
struct is_complete : std::false_type {};

template <typename T>
struct is_complete<T, std::void_t<decltype(sizeof(T))>> : std::true_type {};
```

```cpp title="a.cpp"
#include "a.h"
struct X;
bool in_a() { return is_complete<X>::value; }   // 在这里 X 不完整：false
```

```cpp title="b.cpp" ifndr
#include "a.h"
#include <cstdio>
struct X {};
bool in_a();
int main() {
  // IFNDR：is_complete<X> 在两个 TU 中选中了不同的特化
  std::printf("a: %d, b: %d\n", in_a(), (int)is_complete<X>::value);
}
```

**实测**：无任何诊断，打印 `a: 0, b: 1`——同一个类型 `is_complete<X>` 在同一个程序里有两个不同的定义。这就是为什么"检测类型是否完整"的 trait 被认为无法正确实现。

### G.10.10 [ifndr:temp.dep.candidate.different.lookup.different] {#temp.dep.candidate.different.lookup.different}

**考虑所有 TU 中的声明后，依赖调用会非良构或找到更好的匹配** · 正文 [[temp.dep.candidate#1]]

依赖调用通过 ADL 在**模板定义上下文与实例化上下文**中查找候选函数。若把所有 TU 中相关命名空间里具有外部链接的函数都算上，结果会不同，程序 IFNDR。

```cpp title="tu1.cpp"
namespace A {
  struct S {};
  void f(S&, long x, int y);   // #3
  void g(S&, int x);           // #4
}
```

```cpp title="tu2.cpp" ifndr
namespace A {
  struct S {};
  void f(S&, int x, long y);   // #5
  void g(S&, long x);          // #6
}
template <typename T>
void h(T& t) {
  f(t, 1, 1);   // h<A::S> 中选 #5；若考虑所有声明会产生歧义
  g(t, 1);      // h<A::S> 中选 #6；若考虑所有声明会选 #4
}
```

### G.10.11 [ifndr:temp.explicit.decl.implicit.inst] {#temp.explicit.decl.implicit.inst}

**有显式实例化声明的实体被隐式实例化地使用，却在全程序中没有显式实例化定义** · 正文 [[temp.explicit#12]]

`extern template` 告诉编译器"别在这里实例化，别处会提供"。若别处并没有提供，程序 IFNDR。

```cpp ifndr
#include <vector>
#include <cstdio>

extern template class std::vector<int>;   // 显式实例化声明

int main() {
  std::printf("%zu\n", std::vector<int>().size());   // IFNDR：全程序没有显式实例化定义
}
```

**实测**：链接成功并打印 `0`。显式实例化声明不阻止 inline 函数的实例化（[[temp.explicit]]），而 libc++ 的 `vector` 成员几乎都是 inline 的，所以缺失的显式实例化定义没有造成任何未定义符号。换成成员函数非 inline 定义的自定义类模板，就会得到链接错误。

### G.10.12 [ifndr:temp.expl.spec.unreachable.declaration] {#temp.expl.spec.unreachable.declaration}

**会导致隐式实例化的使用处看不到显式特化的声明** · 正文 [[temp.expl.spec#7]]

显式特化的声明必须在每个会引发隐式实例化的使用处可达，在每个这样的 TU 中都是如此。否则一个 TU 用特化、另一个 TU 用主模板，同一个 `S<int>` 有两种布局。

```cpp title="a.h"
template <typename T> struct S {};
```

```cpp title="tu2.cpp"
#include "a.h"
template <> struct S<int> { int oops; };   // #1
```

```cpp title="tu3.cpp" ifndr
#include "a.h"
S<int> s;   // IFNDR：#1 不可达，但它本应被选中
```

### G.10.13 [ifndr:temp.expl.spec.missing.definition] {#temp.expl.spec.missing.definition}

**显式特化被使用却没有定义** · 正文 [[temp.expl.spec#7]]

声明了显式特化却不提供定义，而该特化又以会引发隐式实例化的方式被使用（或者它是虚成员函数），程序 IFNDR。注意：声明了显式特化后，主模板的定义**不会**再被用来生成这个特化。

```cpp ifndr
template <typename T> int f(T&&) { return 0; }
template <> int f<int>(int&&);   // 只声明

int j = f(1);   // IFNDR：odr-use f<int>，但它没有定义
```

**实测**：链接失败（`Undefined symbols`）。

### G.10.14 [ifndr:temp.deduct.general.diff.order] {#temp.deduct.general.diff.order}

**对同一函数模板的不同声明做替换，会以不同顺序触发实例化** · 正文 [[temp.deduct.general#7]]

替换按词法顺序进行，遇到使推导失败的条件即停止。同一函数模板的不同声明（例如普通返回类型与尾置返回类型）若写法不同，替换时触发实例化的顺序就可能不同——一个是 SFINAE 失败、另一个是硬错误。

```cpp ifndr
template <class T> struct A { using X = typename T::X; };

template <class T> typename T::X h(typename A<T>::X);           // #1
template <class T> auto h(typename A<T>::X) -> typename T::X;   // 重声明 #2
template <class T> void h(...) {}

void x() {
  h<int>(0);   // IFNDR：按 #1 替换，T::X 先失败，不会实例化 A<int>；
               // 按 #2 替换，先实例化 A<int>，那是一个硬错误
}
```

**实测**：Clang 按 #2 的顺序处理并报硬错误：`type 'int' cannot be used prior to '::' because it has no members`（出自 `A<int>` 的实例化）。

## 第 [cpp] 章：预处理指令 {#cpp}

### G.11.1 [ifndr:cpp.cond.defined.after.macro] {#cpp.cond.defined.after.macro}

**在 #if 控制表达式中，宏展开产生了 defined** · 正文 [[cpp.cond#9]]

`defined` 应该在宏展开**之前**被识别。若它是宏展开的产物，不同的预处理器有不同的处理（GCC 与 MSVC 的历史行为就不同），标准选择不规定。

```cpp ifndr
#define X
#define D defined(X)
#if D        // IFNDR：defined 由宏替换产生
#endif
```

**实测**：Clang 给出警告 `macro expansion producing 'defined' has undefined behavior [-Wexpansion-to-defined]`——警告文字沿用了 C 标准的说法（C 中这是 UB），而 C++ 现在把它定为 IFNDR。附录例子 `#define A defined` / `#if A` 中，`defined` 后面什么也没有，Clang 直接报错 `macro name missing`。

### G.11.2 [ifndr:cpp.cond.defined.malformed] {#cpp.cond.defined.malformed}

**defined 的用法在宏替换前不符合两种合法形式** · 正文 [[cpp.cond#9]]

`defined` 只有两种合法形式：`defined X` 与 `defined ( X )`，判断以**宏替换之前**的记号为准。

```cpp ifndr
#define A
#define B A)
#if defined ( B   // IFNDR：替换前 defined ( B 缺少右括号
#endif
```

**实测**：Clang 报错 `missing ')' after 'defined'`。

### G.11.3 [ifndr:cpp.include.malformed.headername] {#cpp.include.malformed.headername}

**#include 宏替换后的记号无法组成 header-name** · 正文 [[cpp.include#7]]

`#include` 的第三种形式（后跟任意预处理记号，先做宏替换）要求替换结果能拼成 `<...>` 或 `"..."` 形式的 *header-name*，空白的处理由实现定义。拼不成则 IFNDR。

```cpp ifndr
#include “   // IFNDR：中文全角引号，不是两种合法形式之一
```

**实测**：Clang 报错 `expected "FILENAME" or <FILENAME>`。

## 常见误区

- **"能编译、能链接、能运行，所以程序没问题。"** IFNDR 程序的典型表现恰恰是这样。G.3.5、G.6.3、G.10.9 的例子都通过了编译和链接，却在同一个程序里同时存在两个版本的"同一个东西"。
- **"IFNDR 只是编译器懒得报错的 ill-formed。"** 后果完全不同。必须诊断的非良构程序至少会得到一条诊断；IFNDR 程序可以得到一个可执行文件，而标准对这个可执行文件的行为**没有任何要求**——包括那些与违规代码无关的部分。
- **"附录里列出的 IFNDR 编译器都不会报。"** 不要求诊断不等于禁止诊断。Clang 在看得见的时候常常会报：委托构造的环（G.8.1）、保留的模块名（G.7.1）、预处理器的几条（G.11.x）。
- **"只要每个 TU 自己没问题就行。"** 45 条中有一大半涉及多个 TU。构建系统里不同 TU 使用不同的宏定义、编译选项（例如影响结构体布局或 inline 函数体的 `-D` 开关），是现实中 ODR 违规最常见的来源。

## 思考题

!!! question "1. 为什么 ODR 的“相同定义”要求是 IFNDR，而模块中的同一要求在某些情况下必须诊断？"
    对比 [[basic.def.odr#16]] 的措辞"a diagnostic is required only if…"。

<details markdown="1">
<summary>展开查看答案与解析</summary>

[[basic.def.odr#16]] 说，只有当实体附属于**命名模块**、且前一个定义在后一个定义处**可达**时，才要求诊断。这正是编译器"看得见两份定义"的情形：导入模块时，编译器能拿到被导入模块的 BMI（模块接口的编译产物），里面有前一个定义。传统的头文件模型下，两个 TU 的编译互相独立，没有任何一步能同时看到两份定义，标准只能放弃诊断要求。模块的一个重要收益正是把一部分 IFNDR 变成了必须诊断的错误。

</details>

!!! question "2. G.10.4 中 Clang 让第二个 static_assert 失败。这是不是违反了标准？"
    `Complete<A>` 在 A 补全之后明明应该满足。

<details markdown="1">
<summary>展开查看答案与解析</summary>

不违反。按 [[temp.constr.atomic#3]]，同一原子约束、同一组实参在程序不同点的满足结果不同，程序 IFNDR，标准对实现没有任何要求，报错、不报错、给出任何结果都符合标准。Clang 缓存满足结果，是一个让约束检查的代价可控的实现选择；标准把这种程序定为 IFNDR，就是为了允许这样的缓存。

</details>

## 小结

| 问题 | 答案 |
|---|---|
| IFNDR 的后果 | 程序非良构，且实现不受任何约束（[[intro.compliance.general#2.2]]）；比 UB 更彻底，不需要"执行到" |
| Annex G 的地位 | 资料性，45 条，收录"no diagnostic (is) required"与"a diagnostic is required only if" |
| 不要求诊断的四类原因 | 需要全程序视野、不可判定、保留名、实现历史 |
| 链接器能发现什么 | 强符号重复定义、缺失定义（视优化而定）、语言链接不一致（视是否被调用而定） |
| 链接器发现不了什么 | inline/模板/虚表等 COMDAT 实体的定义不一致、默认实参不一致、实例化点含义不同 |
| 模块带来的改变 | 部分跨 TU 的 IFNDR 在定义可达时变为必须诊断 |
