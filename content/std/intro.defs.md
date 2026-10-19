---
title: 术语与定义
summary: 标准的词汇表，核心是一组描述代码后果的术语：非良构、IFNDR、未定义、未指定、实现定义和错误行为。
status: draft
related: intro.compliance, intro.abstract, topics/undefined-behavior, topics/how-to-read-the-standard
tags: 术语, UB, 行为分类, 基础
updated: 2026-10-18
---

!!! tldr
    - 编译器接受了代码，不等于代码符合标准：有些错误标准不要求编译器报告，有些错误只在运行时出现。
    - 标准分两层判断：程序本身是否合规（良构、非良构、IFNDR），合规的程序运行时有什么保证（实现定义、未指定、错误行为、未定义）。
    - 未定义行为意味着标准对结果不作任何要求，编译器会假设它不发生并据此优化；C++26 的错误行为结果确定，编译器不能这样假设。
    - 常量求值中不允许出现核心语言的未定义行为，所以 `constexpr` 可以在编译期替你抓住它。
    - 普通函数的签名不含返回类型，函数模板的签名含返回类型，这决定了能否重载以及链接时的符号名。

第 3 章是标准的词汇表，收录了 69 个跨章节使用的术语，每个词条有一个 stable name，如 [[defns.undefined]]。C++ 的大多数核心术语（*odr-use*、*glvalue* 等）不在这里，而是在使用它们的那一节里就地定义，见 [[topics/how-to-read-the-standard]]。


## 编译器接受了，代码就对吗？

<div class="compare" markdown="1">

```cpp error
void g(int n) {
  int a[n];  // error: VLA
  a[0] = 0;
}
```

```cpp run ub
#include <climits>
#include <cstdio>
int inc(int x) { return x + 1; }
int main() {
  // UB: 有符号溢出
  std::printf("%d\n", inc(INT_MAX));
}
```

</div>

左边的代码违反了语言规则：数组长度必须是常量表达式。可是 Clang 23 默认只给出一条 `-Wvla-cxx-extension` 警告，照样生成目标代码。

右边的代码没有违反任何规则，开着 `-Wall -Wextra -pedantic` 编译也没有一条警告。但这次调用让有符号整数溢出，标准对这次执行不作任何要求。本机运行打印 `-2147483648`，加上 `-fsanitize=undefined` 后，UBSan 报告 `signed integer overflow`。

可见编译器的反应只能作参考。要判断一段代码对不对，需要回答两个问题：程序本身是否符合语言规则？如果符合，运行时标准保证了什么？第 3 章为这两个问题提供了一套精确的术语。

## 第一层：程序是否合规

### 良构与非良构

**良构程序**（well-formed program，[[defns.well.formed]]）是按照语法规则和语义规则构造的程序。不是良构的程序叫**非良构程序**（ill-formed program，[[defns.ill.formed]]）。

良构是程序文本的性质，与运行时的输入无关。上面右边的程序是良构的，虽然某个输入会让它溢出。

大多数语法和语义规则是可诊断规则（diagnosable rules，[[intro.compliance#1]]）。程序违反其中任何一条，编译器必须至少发出一条**诊断信息**（diagnostic message，[[defns.diagnostic]]），见 [[intro.compliance#2.3]]。

### 警告也算诊断

诊断信息的定义只有一句：实现输出的信息中，由实现定义的某个子集。标准不区分错误和警告，也不要求编译器在诊断之后拒绝程序。

所以 Clang 对 VLA 的处理完全符合标准：那条警告就是它发出的诊断，之后照常编译，属于 [[intro.compliance#11]] 允许的扩展。加上 `-pedantic-errors`，这条警告就变成错误。

标准只在少数几处要求实现不得接受程序，最常见的是 `static_assert` 失败和 `#error` 指令（[[intro.compliance#2.4]]、[[intro.compliance#2.5]]）。

### 不要求诊断的非良构（IFNDR）

有一部分规则带着 "no diagnostic is required" 的注明。违反这种规则的程序同样是非良构的，但编译器可以一声不吭地接受它，而且标准对整个程序（不只是出错的那一处）都不再作任何要求（[[intro.compliance#2.2]]）。这种情况通常简称为 **IFNDR**（ill-formed, no diagnostic required）。

为什么不要求诊断？因为这些错误往往要看到整个程序才能发现，或者在一般情况下根本无法判定。最典型的是 ODR（单一定义规则，[[basic.def.odr]]）：同一个 inline 函数在不同翻译单元（TU）里的定义必须完全相同，而编译器每次只看见一个 TU。

```cpp title="a.cpp"
inline int answer() { return 42; }
int from_a() { return answer(); }
```

```cpp title="b.cpp" ifndr
#include <cstdio>
inline int answer() { return 43; }   // IFNDR: 与 a.cpp 中的定义不同，违反 ODR
int from_a();
int main() { std::printf("%d %d\n", from_a(), answer()); }
```

本机 Clang 23 编译、链接这两个文件都没有任何诊断。`-O0` 下按 `a.cpp b.cpp` 的顺序链接打印 `42 42`，换个顺序打印 `43 43`；`-O2` 下打印 `42 43`，因为 `from_a` 里的调用被内联了。这三种结果都不违反标准，因为标准对这个程序没有任何要求。

IFNDR 不是第 3 章的词条，是从 [[intro.compliance]] 推出来的说法。当前草案的资料性附录 [[ifndr]]（Annex G）列出了所有这类规则。

### 有条件支持的构造

有些构造在某些平台上没有合理的实现，在主流平台上又很有用，比如把函数指针转换成 `void*`。标准把它们标为**有条件支持的**（conditionally-supported，[[defns.cond.supp]]）：实现可以不支持，但要在文档里列出不支持哪些。

```cpp
void f();
void* p = reinterpret_cast<void*>(&f);   // 函数指针转对象指针：有条件支持
struct NT { NT(); NT(const NT&); ~NT(); };
void v(int, ...);
void call(NT x) { v(0, x); }             // 把非平凡类对象传给 ...：有条件支持
```

如果实现不支持某个构造而程序用了它，实现必须诊断（[[intro.compliance#2.3.3]]）。所以有条件支持的构造不会悄悄地变成未定义行为，要么被支持，要么报错。Clang 23 支持第一个，POSIX 的 `dlsym` 就依赖它；对第二个，Clang 选择不支持，给出一个默认即为错误的诊断（`-Wnon-pod-varargs`）。出处分别是 [[expr.reinterpret.cast#8]] 和 [[expr.call]]。

### 实现限制

抽象机的资源是无限的，真实的编译器不是。**实现限制**（implementation limit，[[defns.impl.limits]]）指实现施加给程序的限制，例如模板实例化深度、嵌套层数。没有违反任何规则的程序，实现必须接受并正确执行，除非超出了这些限制（[[intro.compliance#2.1]]）。附录 [[implimits]] 给出了一些建议的最小值，它们只是建议。

## 第二层：良构程序运行时有什么保证

良构的程序，运行时也不一定只有一种结果。标准按对结果的约束从强到弱，把运行时行为分成以下几类。

### 实现定义的行为

```cpp run impl
#include <climits>
#include <cstdio>
int main() {
  char c = '\xff';
  std::printf("%d %d\n", c, CHAR_MIN);   // char 是否有符号由实现定义
}
```

本机（Apple arm64）打印 `-1 -128`。同样是 AArch64，Linux 的 ABI 规定 `char` 无符号，会打印 `255 0`（Clang 的 `-funsigned-char` 可以模拟这种情况）。

**实现定义的行为**（implementation-defined behavior，[[defns.impl.defined]]）指良构的构造在正确的数据下，结果取决于实现，而且每个实现都必须在文档里写明。你可以查文档，可以在一个平台上依赖它，只是代码不可移植。常见的例子有 `sizeof(int)`、`char` 的符号性、`#pragma` 的含义、`std::type_info::name()` 返回的字符串。

[[intro.abstract#2]] 把这些行为看作抽象机的参数：每个实现在文档中把参数填好，就得到了它自己的抽象机实例。

有两个相近的类别。**实现的性质**（property of the implementation，[[defns.impl.prop]]）同样取决于实现，但不要求写进文档，例如类对象中的填充字节，通常由 ABI 决定。**特定于区域设置的行为**（locale-specific behavior，[[defns.locale.specific]]）取决于国家、文化和语言的本地约定，必须写进文档，例如非 "C" locale 下哪些字符算字母。

!!! history
    C++20 把几项原本由实现定义的行为固定了下来：有符号整数采用二进制补码表示，负数右移是算术右移，转换为有符号类型时按模取值。有符号整数溢出仍然是未定义行为。

### 未指定的行为

```cpp run unspecified
#include <cstdio>
int g = 0;
int a() { g += 1; return g; }
int b() { g *= 2; return g; }
void show(int x, int y) { std::printf("%d %d\n", x, y); }
int main() {
  show(a(), b());   // 先调 a 打印 "1 2"，先调 b 打印 "1 0"
}
```

函数实参的求值顺序没有规定（[[expr.call]]）。Clang 23 先调用 `a`，打印 `1 2`；另一个编译器可以先调用 `b`，打印 `1 0`。

**未指定的行为**（unspecified behavior，[[defns.unspecified]]）与实现定义的行为一样，针对良构的构造和正确的数据，结果取决于实现。区别是实现不必写文档，也不必保持一致：不同的优化级别、同一程序中的两处调用，都可以做出不同的选择。

可能的结果通常由标准划定。上例只能打印 `1 2` 或 `1 0`，不会是别的。两个字符串字面量 `"abc"` 是否是同一个对象，也是未指定的（[[lex.string]]）。

!!! pitfall "不确定顺序与无顺序"
    实参之间是不确定顺序（indeterminately sequenced）的，结果只是未指定。如果对同一个标量的两次修改之间是无顺序（unsequenced）的，比如 `i++ + i++`，那是未定义行为。

### 未定义的行为

**未定义的行为**（undefined behavior，简称 UB，[[defns.undefined]]）是标准不作任何要求的行为。这句话要按字面理解：标准既不要求实现做什么，也不禁止实现做什么。定义的注释列举了几种常见表现：忽略这种情况、产生不可预料的结果，按环境特有的方式处理，终止翻译或执行。这些只是举例。

UB 有两个来源。一是标准明确写了 "the behavior is undefined"，附录 [[ub]]（Annex F）汇总了核心语言中所有这类规定。二是标准对某种情况根本没有给出定义，这类 UB 没有汇总。

标准为什么容忍 UB？主要有三个原因。

1. 不同硬件对同一操作的反应不同。整数除以零在 x86 上会陷入，在 AArch64 上结果为 0。规定任何一种行为，都会让其他平台付出额外检查的代价。
2. 编译器可以假设 UB 不发生，从而推出更强的结论，做更多优化。
3. 很多错误（悬垂指针、数据竞争）在编译期无法判定，要求诊断就等于要求运行时检查。

第 2 点有一个直接的后果：

```cpp ub
int inc_checked(int x) {
  int y = x + 1;          // x == INT_MAX 时：UB
  if (y < x) return -1;   // 想在溢出后检查
  return y;
}
bool always(int x) { return x + 1 > x; }
```

Clang 23 在 `-O2` 下把 `inc_checked` 编译成一条加法指令，`if` 整个被删掉，因为只有发生了溢出它才可能成立，而编译器假设溢出不会发生。`always` 直接返回 1。

UB 是某一次执行的性质，不是程序的性质。`int f(int* p) { return *p; }` 本身没有问题，只有以空指针调用它的那次执行才包含 UB。[[intro.abstract]] 正是在一次执行、一组输入的层面上描述 UB 的后果，并用 observable checkpoint 限制了 UB 对之前已发生的行为的影响。

### 常量求值中的 UB

[[defns.undefined]] 的注释最后一句说，常量表达式的求值不会出现第 4 章到第 15 章（核心语言）中显式规定的 UB。换句话说，如果编译期求值遇到了核心语言 UB，这个表达式就不是常量表达式，在需要常量表达式的地方编译器必须报错。

这让 `constexpr` 成为一个现成的 UB 检测器。下面是同一个越界读取，分别在编译期和运行时执行：

<div class="compare" markdown="1">

```cpp error
constexpr int sum3(const int* a) {
  int s = 0;
  for (int i = 0; i <= 3; ++i)
    s += a[i];
  return s;
}
constexpr int arr[3] = {1, 2, 3};
// error: 越界读取，不是常量表达式
static_assert(sum3(arr) == 6);
```

```cpp run ub
#include <cstdio>
int sum3(const int* a) {
  int s = 0;
  for (int i = 0; i <= 3; ++i)
    s += a[i];  // UB: 读 a[3]
  return s;
}
int arr[3] = {1, 2, 3};
int main() {
  std::printf("%d\n", sum3(arr));
}
```

</div>

左边 Clang 报告 `read of dereferenced one-past-the-end pointer`。右边在本机 `-O0` 下打印 `6`，看起来一切正常；加上 `-fsanitize=address` 才报告 `global-buffer-overflow`。

这条保证只覆盖核心语言。违反库函数前置条件之类的库 UB，在常量求值中是否使表达式不再是常量，是未指定的（[[expr.const.core#4]]），因为编译器不一定能看穿库的实现。

### 错误行为 {{c++26}}

**错误行为**（erroneous behavior，简称 EB，[[defns.erroneous]]）是有明确定义、但建议实现诊断的行为。它总是代码有错的后果，正确的程序不会出现它。和 UB 一样，常量求值中不会出现核心语言的错误行为。

C++26 中错误行为的主要来源是读取未初始化的自动变量（[[basic.indet]]）：

```cpp eb
int f() {
  int x;          // 未初始化：x 的字节具有错误值
  return x + 1;   // C++26 中是错误行为；C++23 中是 UB
}
```

**错误值**（erroneous value）是由实现选定、与程序状态无关的一个值。读取它的结果就是这个值。实现可以在这里发出诊断并终止程序（[[intro.abstract#6]]），也可以继续执行，但不能像对待 UB 那样做任何事。

它和 UB 的根本差别是编译器不能假设错误行为不发生，因此不能据此删除代码路径。如果确实需要旧的语义，比如为了性能不想初始化一个大缓冲区，可以给变量加 `[[indeterminate]]`（[[dcl.attr.indet]]），这时读取它又回到 UB。

!!! impl
    截至写作时，Clang 23 还没有实现错误行为的语义。它对上面的 `f` 给出 `-Wuninitialized` 警告，`-O2` 下把 `f` 编译成一条 `ret`，直接返回寄存器里的残留值，仍是按 UB 处理；它也还不认识 `[[indeterminate]]`。Clang 和 GCC 的 `-ftrivial-auto-var-init=zero` 能得到接近的效果：本机加上这个选项后，`f` 固定返回 1。

!!! history
    错误行为由 [[P2795]] 引入。动机是安全：未初始化读取是一大类信息泄露漏洞的根源，而直接规定零初始化会把错误代码变成正确代码，工具就无法再报告它。错误行为让结果可预测，同时标准仍认定它是错误。

### 运行时未定义的行为

**运行时未定义的行为**（runtime-undefined behavior，[[defns.undefined.runtime]]）在运行时就是 UB，在常量求值中则由实现决定：可以把表达式当作非常量，也可以当它不存在（[[expr.const.core#3]]）。目前它只用于 `[[assume]]`（[[dcl.attr.assume]]）。

```cpp error
constexpr int g(int x) {
  [[assume(x > 0)]];
  return x;
}
constexpr int a = g(1);    // OK
constexpr int b = g(-1);   // error: Clang 选择把失败的假设视为非常量
```

Clang 23 报告 `assumption evaluated to false`。另一个实现可以接受 `b` 并把它初始化为 -1，同样符合标准，所以这里的 `error` 是 Clang 的选择。

为什么不直接说 UB？如果是普通 UB，按上一节的规则，编译器在常量求值中就必须检查每一个假设。而假设的表达式可能代价很高，甚至在设计上就不该被求值。

## 对比

| 类别 | 程序合规吗 | 标准对结果的要求 | 编译器的义务 | 例子 |
|---|---|---|---|---|
| 非良构 {{ill-formed}} | 否 | 无 | 至少一条诊断（警告也算） | 类型错误、VLA |
| IFNDR {{ifndr}} | 否 | 对整个程序无要求 | 无 | ODR 违规 |
| 有条件支持 | 支持时是 | 通常由实现定义 | 不支持时必须诊断 | 函数指针转 `void*` |
| 实现定义 {{impl}} | 是 | 实现选定一种 | 写进文档 | `sizeof(int)`、`char` 的符号性 |
| 未指定 {{unspec}} | 是 | 标准允许的结果之一 | 无，每次可以不同 | 实参求值顺序 |
| 错误行为 {{erroneous}} | 是 | 确定的结果 | 建议诊断，可以终止 | 读未初始化的自动变量 |
| 运行时未定义 | 是 | 运行时无要求 | 常量求值中自行选择 | `[[assume]]` 不成立 |
| 未定义 {{ub}} | 是（UB 属于某次执行） | 无 | 无；常量求值中必须拒绝核心语言 UB | 有符号溢出、越界访问 |

## 实践中怎么分辨

编译器能告诉你的，主要是第一层的事。第二层要靠工具、测试和查标准。

| 类别 | 编译器 | 其他手段 |
|---|---|---|
| 非良构 | 报错或警告；用 `-pedantic-errors` 把扩展相关的警告变成错误 | 换一个编译器交叉检查 |
| IFNDR | 通常什么都不说 | GCC 在 LTO 时的 `-Wodr` 能发现部分 ODR 违规；其余靠代码审查 |
| 实现定义 | 按自己的文档执行 | 查编译器和 ABI 文档；依赖它时写 `static_assert` 固定假设 |
| 未指定 | 不报告 | 不要依赖观察到的结果；多个编译器、多个优化级别测试 |
| 错误行为 | `-Wuninitialized` 等警告 | `-ftrivial-auto-var-init`；MemorySanitizer |
| 未定义 | 部分有警告 | UBSan、ASan、TSan；把逻辑放进 `constexpr` 测试 |

遇到一段可疑的代码，可以按这个顺序判断：

1. 它违反了某条语法或语义规则吗？违反了，再看规则有没有注明不要求诊断：有就是 IFNDR，没有就是非良构。
2. 合规的话，看标准对这个操作的结果怎么说。给出唯一结果，就是行为确定的。
3. 要求实现写文档，是实现定义的；给出若干可能结果而不要求文档，是未指定的。
4. 标准说 erroneous，是错误行为；说 undefined 或者根本没有规定，是未定义行为。

更多例子和成因见 [[topics/undefined-behavior]]。

## 类型与对象的词汇

### 静态类型与动态类型

```cpp run ok
#include <typeinfo>
#include <cstdio>
struct B { virtual ~B() = default; };
struct D : B { };
int main() {
  D d;
  B* p = &d;                                     // *p：静态类型 B，动态类型 D
  std::printf("%d\n", typeid(*p) == typeid(D));  // 1：typeid 看动态类型
  B b = *p;                                      // 切片：初始化只看静态类型
  std::printf("%d\n", typeid(b) == typeid(B));   // 1
}
```

**静态类型**（static type，[[defns.static.type]]）是只分析程序文本就能得到的表达式类型，执行期间不会改变。

**动态类型**（dynamic type，[[defns.dynamic.type]]）只对 glvalue（指代一个对象的表达式，见 [[basic.lval]]）有意义：它是该 glvalue 所指代的最派生对象的类型。prvalue 不指代对象，它的动态类型就是静态类型（[[defns.dynamic.type.prvalue]]）。两者不同，只会因为派生类到基类的转换。

很多规则建立在这对概念上：虚函数调用按动态类型分派（[[class.virtual]]）；`delete` 一个静态类型与动态类型不同的对象时，基类必须有虚析构函数（[[expr.delete]]）；严格别名规则（[[basic.lval]]）也要用到它们。

### 访问

**访问**（access，[[defns.access]]）指读取或修改一个对象的值。注释把范围收得很窄：只有标量类型的 glvalue 能访问对象。读标量见 [[conv.lval]]，改标量见 [[expr.assign]] 和自增自减。

```cpp ok
struct S { int a; double b; };
void f(S& s, S& t) {
  t = s;   // 调用复制赋值运算符，这次调用本身不是访问
           // 它内部读 s.a、s.b，写 t.a、t.b，这四次才是访问
}
```

复制一个类对象是调用构造函数或赋值运算符，这种调用本身不算访问。这个区分很有用，因为严格别名规则（[[basic.lval]]）、数据竞争（[[intro.races]]）和可观察行为（[[intro.abstract]]）都是用访问来表述的，把它限定在标量上，这些规则的边界才说得清。

### 可引用类型

**可引用类型**（referenceable type，[[defns.referenceable]]）是可以为之创建引用的类型：对象类型、引用类型，以及既没有 cv 限定符也没有引用限定符的函数类型。不可引用的只有 `void` 和 `int() const` 这种只能出现在成员函数声明里的函数类型。类型特征用这个术语规定边界情况：

```cpp ok
#include <type_traits>
template<class T> using LRef = std::add_lvalue_reference_t<T>;
static_assert(std::is_same_v<LRef<void>, void>);                // 不可引用：原样返回
static_assert(std::is_same_v<LRef<int() const>, int() const>);  // 不可引用：原样返回
static_assert(std::is_same_v<LRef<int()>, int(&)()>);           // 可引用
static_assert(std::is_same_v<LRef<int&&>, int&>);               // 引用折叠
```

## 签名

两个同名函数能不能共存？链接器怎么区分它们？这两个问题的基础都是**签名**（signature，[[defns.signature]]）。签名决定了名字修饰（name mangling），也就是编译器为每个函数生成的链接符号。

<div class="compare" markdown="1">

```cpp error
int  f(int);
long f(int);  // error: 只差返回类型
```

```cpp run ok
template<class T>
int f(T) { return 1; }   // #1
template<class T>
long f(T) { return 2; }  // #2: OK
int main() {
  int  (*p)(int) = &f<int>;  // #1
  long (*q)(int) = &f<int>;  // #2
  return p(0) + q(0);        // 3
}
```

</div>

普通函数的签名是名字、形参类型列表和所在命名空间，不含返回类型，所以左边两个声明冲突。函数模板的签名还包括返回类型和模板头，所以右边的 #1 和 #2 是两个不同的模板。直接写 `f(0)` 会有二义，但可以通过目标类型选择其中一个。

模板这样规定，是因为两个同样写作 `f<int>` 的特化可能来自不同的模板，链接时必须是不同的符号。在 Itanium C++ ABI（Linux、macOS 上的 GCC 和 Clang 使用）下，右边两个特化分别修饰为 `_Z1fIiEiT_` 和 `_Z1fIiElT_`，中间的 `i` 和 `l` 就是返回类型 `int` 和 `long`。普通函数 `int f(int)` 修饰为 `_Z1fi`，没有返回类型。

成员函数的签名还包括 cv 限定符和引用限定符，所以可以按它们重载：

```cpp ok
struct S {
  void g() &;
  void g() &&;     // OK: 引用限定符不同
  void h() const;
  void h();        // OK: cv 限定符不同
};
```

`S::h() const` 修饰为 `_ZNK1S1hEv`（`K` 表示 const），`S::g() &` 修饰为 `_ZNR1S1gEv`（`R` 表示 `&`）。

标准为九种实体分别定义了签名，各自的组成如下：

| 实体 | 签名包含 |
|---|---|
| 函数 | 名字、形参类型列表、所在命名空间 |
| 函数模板 | 上一行 + 返回类型、模板头的签名、尾随 *requires-clause* |
| 函数模板特化 | 模板的签名 + 模板实参 |
| 成员函数 | 名字、形参类型列表、所属的类、cv 限定符、引用限定符、尾随 *requires-clause* |
| 成员函数模板 | 上一行 + 返回类型、模板头的签名 |
| 成员函数模板特化 | 成员函数模板的签名 + 模板实参 |
| 带尾随 *requires-clause* 的非模板友元 | 名字、形参类型列表、所在的类、尾随 *requires-clause* |
| 约束涉及外围模板形参的友元函数模板 | 名字、形参类型列表、返回类型、所在的类、模板头的签名、尾随 *requires-clause* |
| 模板头 | 模板形参列表（去掉形参名和默认实参）、*requires-clause* |

两个友元词条是 C++20 引入约束之后才需要的：类模板里定义的约束友元，在每次实例化中是不同的函数，签名必须包括所在的类，否则 `A<int>` 和 `A<long>` 里的同名友元会冲突（[[temp.friend]]）。

!!! lawyer "判断重载时引用哪一条"
    今天的标准判断两个声明是否声明同一个实体、能否构成重载，用的是 [[basic.scope.scope]] 中的对应（correspond）规则，而不直接说签名相同。两者大体一致，需要精确论证时应引用 [[basic.scope.scope]]；签名主要服务于链接和库规范。

## 实参与形参

标准严格区分**实参**（argument，调用处给出的东西）和**形参**（parameter，声明处引入的名字）。两个词都按场合有不同定义：

| 场合 | 实参 | 形参 |
|---|---|---|
| 函数调用 | 括号内的表达式或 *braced-init-list* | 函数声明或 `catch` 子句里声明的对象或引用 |
| 函数式宏 | 括号内逗号分隔的预处理记号序列 | 宏名后括号里的标识符 |
| 模板 | 尖括号内的常量表达式、类型或 *id-expression* | *template-parameter-list* 的成员 |
| `throw` 表达式 | `throw` 的操作数 | |

宏的实参是记号序列，不是表达式，只有圆括号能保护其中的逗号。所以 `FIRST(std::pair<int, int>{}, 1)` 会被拆成三个实参，Clang 报告 `too many arguments provided to function-like macro invocation`。

## 库条款里的术语

下面这些术语主要出现在库的规范里。阅读 cppreference 或标准库条款时，它们会反复出现。

### 和常量表达式有关的

- **常量子表达式**（constant subexpression，[[defns.const.subexpr]]）：作为某个常量表达式的一部分求值时，不会妨碍它成为常量表达式的表达式。库规范用它说明某个调用能否用在编译期。
- **非常量库调用**（non-constant library call，[[defns.nonconst.libcall]]）：会使所在表达式不再是常量表达式的库函数调用，见 [[expr.const.core#2.35]]。
- **表达式等价**（expression-equivalent，[[defns.expression.equivalent]]）：一组表达式效果相同，并且是否可能抛异常、是否是常量子表达式也都一致。规定 `ranges::begin` 这类定制点对象（[[customization.point.object]]）时用它：说 `ranges::begin(E)` 与 `E.begin()` 表达式等价，同时意味着 `noexcept` 性和 constexpr 性一致。

### 算法

**投影**（projection，[[defns.projection]]）是算法在检查元素值之前对它施加的变换。**稳定算法**（stable algorithm，[[defns.stable]]）保持元素原有的顺序，对排序类算法来说，就是等价元素的相对顺序不变（[[algorithm.stable]]）。

```cpp run ok
#include <algorithm>
#include <cstdio>
#include <utility>
#include <vector>
int main() {
  std::vector<std::pair<int, char>> v{{2,'a'},{1,'b'},{2,'c'},{1,'d'}};
  // 投影：只按 first 比较
  std::ranges::stable_sort(v, {}, &std::pair<int, char>::first);
  for (auto [k, c] : v) std::printf("%d%c ", k, c);  // 1b 1d 2a 2c
}
```

### 对象的状态

**有效但未指定的状态**（valid but unspecified state，[[defns.valid]]）指对象的值没有规定，但它的不变式成立，对它的操作按其类型的规定工作。被移动之后的标准库对象通常处于这种状态（[[lib.types.movedfrom]]）。可以调用没有前置条件的操作，有前置条件的要先确认：

```cpp run ok
#include <string>
#include <utility>
int main() {
  std::string s = "hello, world, a fairly long string";
  std::string t = std::move(s);   // s 处于有效但未指定的状态
  s.clear();                      // OK: clear 没有前置条件
  s = "again";                    // OK: 赋值没有前置条件
  return s.back() == 'n' ? 0 : 1; // OK: 此时已知 s 非空
}
```

库的描述里还会用到这几个词：**修改函数**（modifier function）是改变对象状态的成员函数，不含构造、赋值和析构；**观察函数**（observer function）只读取状态，规定为 `const` 成员函数；**移动构造**和**移动赋值**指用同类型的右值初始化或赋值，它们只描述表达式的形式，不管实际调用了哪个构造函数。

### 程序可以提供的函数

| 术语 | 含义 | 例子 |
|---|---|---|
| 替换函数（replacement function） | 程序可以提供定义，替换掉库的默认版本 | 全局 `operator new`（[[new.delete]]） |
| 处理函数（handler function） | 程序提供定义，通过库函数安装 | 传给 `std::set_terminate` 的函数 |
| 保留函数（reserved function） | 由实现定义，程序提供定义则结果未定义 | |

替换函数和处理函数都有**要求的行为**（required behavior）：程序提供的版本运行时不满足它，行为未定义。实现自带的版本在要求的范围内具体怎么做，叫**默认行为**（default behavior），见 [[structure.specifications]]。

### 程序定义的类型

**程序定义的类型**（program-defined type，[[defns.prog.def.type]]）是不属于标准库、也不由实现定义的类类型或枚举类型，包括程序中 lambda 的闭包类型。**程序定义的特化**是程序写的显式特化或偏特化。

这两个词决定了程序能往 `std` 里加什么：只能为依赖至少一个程序定义类型的标准库模板添加特化（[[namespace.std]]）。为 `std::hash<MyType>` 写特化可以，为 `std::hash<int>` 不行。

### 指针的全序

内置的 `<` 比较两个不指向同一数组的指针，结果是未指定的（[[expr.rel]]）。标准库另外规定了一个**实现定义的指针严格全序**（[[defns.order.ptr]]），与内置运算符给出的偏序一致。`std::less<T*>` 等函数对象保证使用它（[[comparisons]]），所以可以用它给任意指针排序，或者把指针作为 `std::map` 的键。

## 常见误解

!!! pitfall "有符号溢出是实现定义的"
    不是。C++20 起有符号整数的表示固定为补码，但算术溢出仍是 UB（[[expr.pre#4]]）。无符号算术不会溢出，它按模 2ⁿ 回绕。

!!! pitfall "UB 就是程序会崩溃"
    崩溃只是可能的结果之一。更常见的是程序看起来正常（如上面越界读取打印的 `6`），或者优化器基于 UB 不发生删掉了你的检查。

!!! pitfall "IFNDR 只是链接期的问题"
    IFNDR 规则遍布全书：ODR、模板定义不可能有合法的实例化（[[temp.res]]）、同一约束在不同位置的满足结果不同等等。违反任何一条，标准对整个程序都不再有要求。

## 思考题

!!! question "思考题 1"
    下面这个程序在 C++23 中是否良构？在 C++26 中呢？它的执行有没有未定义行为？
    ```cpp
    int main() { int x; return x; }
    ```

<details markdown="1">
<summary>答案</summary>

两个版本中它都是良构的：它没有违反任何语法或语义规则，而良构与否与运行时行为无关。

区别在执行。C++23 中读取不确定值是 UB。C++26 中未初始化自动变量的字节具有错误值，读取它是错误行为：实现可以诊断并终止，否则 `main` 返回实现选定的那个值。只有给 `x` 加上 `[[indeterminate]]`，才回到 UB。
</details>

!!! question "思考题 2"
    同一个命名空间里能否同时声明 `template<class T> int f(T);` 和 `template<class T> long f(T);`？能否同时声明 `int g(int);` 和 `long g(int);`？

<details markdown="1">
<summary>答案</summary>

前者可以，后者不行。函数模板的签名包含返回类型，两个模板不对应（[[basic.scope.scope#4]]），可以共存；只是 `f(0)` 这样的调用会二义，需要借助目标类型选择。

后者的签名只有名字、形参类型列表和命名空间，两个声明声明的是同一个函数，类型却不同，违反 [[basic.link#11]]，必须诊断。
</details>

!!! question "思考题 3"
    `+"abc" == +"abc"` 属于哪一类？去掉两个一元 `+` 呢？`sizeof(long)` 呢？`reinterpret_cast<void*>(&main)` 呢？

<details markdown="1">
<summary>答案</summary>

- `+"abc" == +"abc"`：未指定。一元 `+` 让数组退化为指针，比较的是地址，两个字符串字面量是否为同一对象是未指定的（[[lex.string]]）。
- `"abc" == "abc"`：当前草案中非良构，两个数组类型的操作数不能直接比较（[[diff.cpp23.expr]]；C++20 到 C++23 中是弃用的）。Clang 23 在 `-std=c++2c` 下报错。
- `sizeof(long)`：实现定义。
- `reinterpret_cast<void*>(&main)`：非良构，程序不得 odr-use `main`（[[basic.start.main]]）。换成普通函数 `&f`，就是有条件支持的。
</details>

<details class="fine" markdown="1">
<summary>其余条文</summary>

¶1 除了本章的词条，ISO/IEC 2382（信息技术词汇）和 ISO 80000-2（数学符号）中的定义也适用，所以 *byte*、区间记号 `[a, b)` 等按这两份文件理解。它们列在 [[intro.refs]] 中。

¶2 给出 ISO 和 IEC 在线术语库的网址，是 ISO 文件的固定格式，与 C++ 无关。

同一个英文词在不同场合有不同定义时，用⟨⟩标出场合，如 *block* ⟨execution⟩ 与 *block* ⟨statement⟩。ISO 要求定义能直接替换正文中的术语，所以定义都写成不带冠词的名词短语。

几个与执行有关的词条：*block* ⟨execution⟩（[[defns.block]]）：等待某个条件满足后才继续执行；线程只是没被调度不算阻塞（见 [[intro.progress]]）。*block* ⟨statement⟩ 是复合语句（[[stmt.block]]）。*deadlock*：每个线程都阻塞在等待其他线程满足条件上。*unblock*：满足阻塞线程等待的条件。*constant evaluation*（[[defns.const.eval]]）：作为求值核心常量表达式的一部分而进行的求值。

字符与 C 库：*C standard library*：ISO/IEC 9899:2024 第 7 章描述的库，在 [[diff.library]] 等处注明的限定下是 C++ 标准库的子集。*character* ⟨library⟩：按顺序处理时可以表示文本的对象，不限于 `char` 系列，`std::basic_string<MyChar>` 的 `MyChar` 也算。*character container type*：表示字符的类型，`char_traits` 和 `basic_string` 等模板的模板形参。*NTCTS*：以 `charT()` 结尾的字符序列，即任意字符类型上的 C 风格字符串。

库的组织：*component*：通过成员、形参或返回类型直接关联的一组库实体，如 string 组件。*traits class*：封装一组类型和函数、供模板操作其实例化类型的类，如 `char_traits`、`iterator_traits`。

正则表达式库（[[re]]）专用的七个词条沿用 ECMAScript 和 POSIX 的概念：*collating element*、*finite state machine*、*format specifier*（如 `$1`）、*matched*、*primary equivalence class*、*regular expression*、*sub-expression*。

C++14 及以前，术语与定义是第 1 章的 1.3 节；C++17 按 ISO 文件结构把它移到第 3 章，stable name `[intro.defs]` 没有变。runtime-undefined behavior、Annex F 和 Annex G 是 C++23 之后加入的。

</details>
