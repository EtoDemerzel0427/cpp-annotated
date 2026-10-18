---
title: 顺序执行
summary: 单线程内的求值顺序：完整表达式、值计算与副作用、sequenced-before / unsequenced / indeterminately sequenced，以及无序的冲突副作用导致 UB 的规则
status: draft
papers: P0145R3
related: intro.races, intro.abstract, expr.call, expr.assign, class.temporary, basic.contract.eval
tags: 求值顺序, UB, 表达式
updated: 2026-10-17
---

本节回答一个看似朴素的问题：同一个线程里，一段代码中的各个求值按什么顺序发生？
答案并不是从左到右、从上到下。C++ 只给出一个**偏序**：有些求值之间有先后（sequenced before），有些只保证不重叠、但先后未指定（indeterminately sequenced），还有些完全没有顺序约束（unsequenced），可以交叠执行。
在这个偏序之上，标准规定：如果对同一内存位置的修改与另一次访问无序，行为未定义。`i = i++ + i` 之所以是 UB，就出自本节第 10 段。

本节是 [[intro.races]]（多线程数据竞争）的单线程前身：后者定义的 *happens before* 关系正是以本节的 *sequenced before* 为基础构建的。读本节前最好了解[[intro.abstract|抽象机]]与[[intro.memory|内存位置]]的概念。

## 为什么不规定一个完整的求值顺序？

C 与 C++ 历来把操作数的求值顺序留给实现，理由是：

- 寄存器分配与调度：编译器可以先算需要更多寄存器的那一边（Sethi–Ullman 编号），或把加载提前以隐藏延迟。
- 调用约定：有的 ABI 从右往左压栈传参，从右往左求值实参更自然。
- 向量化与公共子表达式消除：无序意味着优化器可以自由合并、重排。

代价是可移植性陷阱：`f(i++, i++)`、`cout << i++ << i++` 在不同编译器上结果不同（C++17 之前甚至是 UB）。C++17 通过 [[P0145R3]] 给一部分人们习惯从左往右读的运算符补上了顺序（`<<`、`>>`、`=`、`[]`、`->*`、函数调用的被调函数先于实参……），但**普通算术运算符的操作数之间、函数实参之间仍然没有顺序**。这一折衷贯穿全节。

## 自动对象与块的关联（¶1）

¶1 每次进入一个块，块内每个自动存储期对象都对应一个新的实例。对象在块执行期间存在，并保持最后存入的值；即使块被挂起也是如此。调用其他函数、协程挂起（[[expr.await]]）、收到信号时，当前块的局部变量都保持原值。

这句话看似多余，实际上是递归正确性的基础：每层递归都有自己的一份局部变量；协程挂起后再恢复，局部变量（存在协程帧里）仍是挂起前的值。

## 构成表达式、直接子表达式、子表达式（¶2–¶4）

这三个定义是为第 5 段（完整表达式）和第 10 段（无序规则）服务的工具。

### 构成表达式（¶2）

¶2 **构成表达式**（constituent expression）把语法上的表达式展开成实际要求值的那些部分：

| 对象 E | E 的构成表达式 |
|---|---|
| 一个表达式 | 它本身（¶2.1） |
| 一个转换 | 对应的隐式函数调用（如转换函数、转换构造函数）；没有调用时就是被转换的表达式（¶2.2） |
| *braced-init-list* 或（可加括号的）*expression-list* | 各元素的构成表达式（¶2.3） |
| `= initializer-clause` 形式的初始化器 | *initializer-clause* 的构成表达式（¶2.4） |

标准的例子：`B b = { 5, { 1+1 } };` 的构成表达式是 `5` 和 `1+1`，嵌套的花括号被展平了。

### 直接子表达式（¶3）

¶3 表达式 E 的**直接子表达式**（immediate subexpression）包括：

- ¶3.1 E 的各操作数（[[expr.prop]]）的构成表达式；
- ¶3.2 E 隐式调用的任何函数（如重载运算符、转换函数、`new` 调用的分配函数）；
- ¶3.3 若 E 是 *lambda-expression*：按值捕获的实体的初始化，以及 *init-capture* 初始化器的构成表达式；
- ¶3.4 若 E 是函数调用或隐式调用函数：所用到的每个默认实参的构成表达式；
- ¶3.5 若 E 执行聚合初始化：所用到的每个默认成员初始化器的构成表达式。

¶3.4 和 ¶3.5 很关键：默认实参、默认成员初始化器在源码上写在别处，但**它们在调用点或初始化点求值，属于调用表达式的一部分**。所以它们产生的临时对象在调用者的完整表达式结束时才销毁，它们的副作用也参与调用者表达式内的顺序分析（见 ¶6 的注）。

### 子表达式与潜在求值子表达式（¶4）

¶4 **子表达式**是直接子表达式关系的传递闭包。注 1 特别指出，lambda 的函数体（*compound-statement*）里的表达式不是 lambda-expression 的子表达式：函数体在闭包被调用时才执行，与创建闭包的表达式无关。

¶4 还定义了潜在求值子表达式（potentially-evaluated subexpressions）：E 的构成表达式，以及其中不属于嵌套不求值操作数（[[expr.context]]，如 `sizeof`、`decltype` 的操作数）的子表达式。这一概念被 [[basic.def.odr]] 等处用来判断哪些表达式确实可能被求值。

## 完整表达式（¶5–¶6）

¶5 [[g:full-expression|**完整表达式**]]（full-expression）是顺序规则的基本单位。¶9 规定相邻完整表达式之间严格有序，[[class.temporary]] 规定临时对象通常在完整表达式结束时销毁。下列都是完整表达式：

| 编号 | 种类 | 说明 |
|---|---|---|
| ¶5.1 | 不求值操作数 | `sizeof(f())` 中的 `f()` 自成一个完整表达式（但不求值） |
| ¶5.2 | *constant-expression* | 如数组界、`case` 标签、模板实参 |
| ¶5.3 | 立即调用（immediate invocation） | {{c++20}} `consteval` 函数调用本身就是完整表达式，它在编译期被整体求值 |
| ¶5.4 | *init-declarator* 或 *mem-initializer* | 包括初始化器的构成表达式；结构化绑定声明也算 |
| ¶5.5 | 对象生命周期结束时隐式生成的析构调用 | 不包括临时对象（那些在其所属完整表达式内销毁）以及生命周期被延长的临时对象 |
| ¶5.6 | 契约断言的谓词 | {{c++26}} `pre`/`post`/`contract_assert` 的谓词，见 [[basic.contract]] |
| ¶5.7 | 不是其他表达式子表达式、也不属于其他完整表达式的表达式 | 最常见的情形：表达式语句、`return` 的操作数、`if` 的条件…… |

¶5 后半部分的三条补充同样重要：

1. 如果某个语言构造按定义会产生隐式函数调用（如 range-for 调用 `begin()`、`new` 调用分配函数），那么对这个构造的使用本身就被视为一个表达式。
2. 为满足语言构造的要求而对表达式结果施加的转换（如 `if` 条件里的到 `bool` 的转换、左值到右值转换）也属于该完整表达式。
3. 对初始化器而言，执行初始化本身（包括聚合的默认成员初始化器求值）也属于完整表达式。

```cpp run title="full-expr.cpp" ok
#include <cstdio>
struct T {
  const char* n;
  T(const char* s) : n(s) { std::printf("ctor %s\n", n); }
  ~T() { std::printf("dtor %s\n", n); }
  int v() const { return 1; }
};
int use(int a, int b) { std::printf("use\n"); return a + b; }

int main() {
  int x = use(T("a").v(), T("b").v());  // 整个 init-declarator 是一个完整表达式
  std::printf("next %d\n", x);          // 两个临时对象在 use 返回之后、本行之前销毁
}
```

`T("a")` 与 `T("b")` 的构造顺序未指定（它们分属两个形参的初始化，见下文 [[expr.call#8]]），但它们都在 `use` 返回之后、`printf("next")` 之前销毁，因为销毁发生在完整表达式的末尾。

标准例 2 里的几个要点值得逐条理解：

- `S s1(1);`：完整表达式包含对 `S::S(int)` 的调用（¶5.4：init-declarator 连同初始化）。
- `if (S(3).v())`：完整表达式包含左值到右值转换和 `int`→`bool` 转换，这些转换在临时对象销毁之前完成。所以 `v()` 返回的引用在转换时仍然有效。
- `bool b = noexcept(S(4));`：`noexcept` 的操作数是不求值操作数，但它仍是一个完整表达式，因此在完整表达式末尾销毁临时对象的那次隐含析构调用也要考虑在内：`~S()` 是 `noexcept(false)`，所以 `b` 是 `false`。
- `B b[2] = { B(), B() };`：整个初始化（包括默认实参 `S(0)` 产生的临时对象的销毁）是一个完整表达式。

```cpp run title="noexcept-dtor.cpp" ok
struct S {
  S(int) noexcept {}
  ~S() noexcept(false) {}
};
static_assert(!noexcept(S(4)));   // 临时对象的析构也是这个完整表达式的一部分
int main() {}
```

¶6 注 2：完整表达式的求值可以包括词法上不属于它的子表达式。典型的例子是默认实参：默认实参表达式写在函数声明处，却被视为在调用表达式中创建。

!!! note "C++23 的 range-for 临时对象"
    完整表达式的边界决定了临时对象的寿命。`for (auto x : make().items())` 在 C++20 及以前是悬垂引用的常见来源：`make()` 返回的临时对象在 *for-range-initializer* 这个完整表达式结束时就销毁了。C++23 修改了 [[stmt.ranged]]，把 *for-range-initializer* 中的临时对象的生命周期延长到整个循环结束。这不是改了 ¶5，而是在 [[class.temporary]] 中为该上下文增加了一个延长寿命的情形。

## 副作用与求值（¶7）

¶7 **副作用**（side effect）是执行环境或翻译环境状态的改变，包括以下操作：

- 读取 volatile glvalue 所指的对象（读 volatile 也算副作用，因为读设备寄存器可能改变设备状态）；
- 修改对象；
- {{c++26}} 产生一个注入声明（injected declaration，[[expr.const.reflect]]），这是静态反射中 `define_aggregate` 等元函数在翻译期造成的效果，所以定义里出现了翻译环境；
- 调用库 I/O 函数；
- 调用做了上述任一事情的函数。

一次表达式的**求值**（evaluation）一般包括两部分：

- 值计算（value computation）：对 glvalue 是确定它指代哪个对象（identity），对 prvalue 是取出先前存入的值；
- 发起副作用（initiation of side effects）。

C++11 顺序模型的核心就是把二者拆开。以 `i++` 为例：值计算得到旧值，副作用是把 `i` 加 1。[[expr.post.incr]] 规定值计算先于修改，但修改与外层表达式其他部分的先后，要看外层运算符的规定。

¶7 最后一句：库 I/O 调用返回、或 volatile 访问被求值时，副作用就视为完成，哪怕真正的 I/O（如数据写到磁盘）尚未发生。标准只管抽象机层面的完成，不管外设。

## 三种顺序关系（¶8–¶9）

¶8 [[g:sequenced-before|**sequenced before**]] 是同一线程内求值之间的一个非对称、传递的二元关系，构成偏序。若 A sequenced before B，则 A 的执行必须先于 B。由它派生出两种没有确定先后的情形：

| 关系 | 定义 | 能否重叠 | 典型来源 |
|---|---|---|---|
| A sequenced before B | A 必须先执行完 | 否 | `;` 分隔的语句、`&&` `\|\|` `,` `?:` 的左操作数、C++17 的 `<<` `=` 等 |
| indeterminately sequenced | A 在 B 之前或 B 在 A 之前，未指定哪个 | 否 | 函数调用与调用外的求值（第 12 段）、函数各形参的初始化（[[expr.call#8]]） |
| unsequenced | 两个方向都不是 sequenced before | 可以（注 3） | `+` `*` `==` 等普通运算符的操作数 |

注 3 和注 4 揭示了二者的本质区别：**unsequenced 的求值可以交叠**，编译器可能把 `a + b` 中 `a` 的一半指令和 `b` 的一半指令交错排列；而 indeterminately sequenced 的两个求值各自是不可分割的整体，只是谁先谁后不定。正因为可以交叠，unsequenced 的冲突访问才是 UB，而 indeterminately sequenced 的冲突访问只是结果未指定。

¶8 末句把关系推广到表达式：说"表达式 X sequenced before 表达式 Y"，意思是 X 关联的每个值计算和副作用都 sequenced before Y 关联的每个值计算和副作用。C++17 中"`<<` 的 E1 sequenced before E2"就是在这个强意义上说的，E1 的副作用也全部先于 E2。

¶9 相邻两个完整表达式之间：前一个关联的每个值计算和副作用都 sequenced before 下一个的每个值计算和副作用。这就是"分号是顺序点"这一说法的现代表述。脚注提醒：完整表达式结束后，还会发生零或多次临时对象的析构调用，通常按构造的逆序。

## 无序规则与未定义行为（¶10）

¶10 首先给出默认情形：**除非另有说明，单个运算符的各操作数、单个表达式的各子表达式之间的求值是无序的。** 然后给出两条保证与一条禁令：

- 注 5：同一个表达式多次求值时（如在循环中），无序或不定序的子表达式不必每次都按同样的顺序执行，不能根据第一次的顺序推断后续。
- 运算符各操作数的值计算先于运算符结果的值计算。这很自然，要先知道 `a` 和 `b` 才能算 `a+b`；但副作用不在此列。
- 禁令：若

    - ¶10.1 对某内存位置的副作用，或 ¶10.2 在某内存位置开始/结束对象生命周期，

    与以下之一无序：

    - ¶10.3 对同一内存位置的另一个副作用，
    - ¶10.4 在与该内存位置重叠的存储中开始/结束对象生命周期，
    - ¶10.5 使用同一内存位置中任何对象的值的值计算，

    且两个求值不是潜在并发的（[[intro.races#17]]），则行为未定义。

!!! std
    The behavior is undefined if a side effect on a memory location […] is unsequenced relative to […] another side effect on the same memory location […] or a value computation using the value of any object in the same memory location.

"不是潜在并发的"这个限定是为了与 [[intro.races]] 分工：不同线程间（或与信号处理函数间）的冲突由数据竞争规则处理，本段只管单线程内的无序冲突。注 7 也说明，下一节对并发求值施加类似但更复杂的限制。

这里的关键词是内存位置（memory location，[[intro.memory]]），而不是变量：相邻的位域可能共享一个内存位置，联合体的成员共享存储。¶10.2/¶10.4 把开始或结束生命周期也纳入进来，因为对联合体成员赋值可能隐式切换活跃成员（注 6：在某个内存位置开始一个对象的生命周期，可能结束其他内存位置中对象的生命周期，[[basic.life]]）。

### 标准例 3 逐行分析

```cpp run title="seq-std.cpp"
void g(int i) {
  i = 7, i++, i++;              // OK: 逗号运算符左先于右，i 变为 9

  i = i++ + 1;                  // OK (C++17 起): i 自增
  i = i++ + i;                  // UB: i++ 的副作用与右边 i 的值计算无序
  i = i + 1;                    // OK

  union U { int x, y; } u;
  (u.x = 1, 0) + (u.y = 2, 0);  // UB: 两个赋值各自开始一个成员的生命周期，彼此无序
}
int main() { g(0); }
```

- `i = 7, i++, i++;`：[[expr.comma]] 规定左操作数 sequenced before 右操作数（强意义，包括副作用），所以一路顺下来 `i` 为 9。
- `i = i++ + 1;`：这是 C++17 才变成良定义的。[[expr.assign]] 规定"右操作数 sequenced before 左操作数"，且赋值的副作用在两个操作数的值计算之后。于是 `i++` 的副作用（作为右操作数的一部分）先于赋值的副作用完成，二者有序。在 C++11/14 中，`i++` 的副作用与赋值的副作用无序，因此是 UB。
- `i = i++ + i;`：在右操作数 `i++ + i` 内部，`+` 的两个操作数无序，`i++` 的副作用与右边 `i` 的值计算无序 → UB。C++17 的改动没有触及 `+`。
- 联合体那行：`u.x = 1` 开始 `u.x` 的生命周期（并结束 `u.y` 的），`u.y = 2` 反之；`+` 的两个操作数无序 → 命中 ¶10.2 + ¶10.4 → UB。

### 边界例子

```cpp run title="seq-ok.cpp" ok
#include <cstdio>
int a[4] = {};
int main() {
  int x = 5;
  x = x++;              // C++17: OK，x 保持 5（先算右边得 5、自增为 6，再赋值 5）
  int i = 0;
  a[i] = i++ + 10;      // C++17: 右先于左 → 先 i++（i 变 1），再求 a[i] 即 a[1]
  std::printf("%d %d %d\n", x, a[0], a[1]);   // 5 0 10
}
```

```cpp run title="seq-ub.cpp" ub
int h(int i) {
  return i++ + i++;     // UB: + 的两个操作数都修改 i，彼此无序
}
int main() { return h(0); }
```

!!! impl "Clang 的 -Wunsequenced"
    Clang 对上面两个例子都会给出 `-Wunsequenced` 警告（`-Wall` 已包含）。不过截至写作时（Clang 23），对 C++17 起已经良定义的 `a[i] = i++ + 10` 它仍会警告，对 `f(i++, i++)` 也会报"multiple unsequenced modifications"。按 C++17 的 [[expr.call#8]]，形参初始化是 indeterminately sequenced 的，并非无序，所以那不是 UB，只是结果未指定。这类警告更像是可移植性提醒，不能当作标准的判定。GCC 对应的选项是 `-Wsequence-point`。

### C++17 之后哪些运算符有了顺序

本节只说"除非另有说明"，具体的说明分散在 [[expr]] 各处。汇总如下（✱ 表示 C++17 新增）：

| 表达式 | 顺序保证 | 出处 |
|---|---|---|
| `a && b`、`a \|\| b` | 若求值 b，则 a 先于 b | [[expr.log.and#2]]、[[expr.log.or#2]] |
| `a ? b : c` | a 先于 b 或 c | [[expr.cond#1]] |
| `a , b` | a 先于 b | [[expr.comma#1]] |
| `a << b`、`a >> b` ✱ | a 先于 b | [[expr.shift#4]] |
| `a = b`、`a += b` … ✱ | b 先于 a；赋值的副作用在两边值计算之后 | [[expr.assign#1]] |
| `a[b]` ✱ | a 先于 b | [[expr.sub#1]] |
| `a->*b`、`a.*b` ✱ | a 先于 b | [[expr.mptr.oper#4]] |
| `f(args…)` ✱ | 后缀表达式 f 先于每个实参和默认实参；各形参的初始化彼此 indeterminately sequenced | [[expr.call#8]] |
| `{a, b, c}` | 从左到右，即使它被解释为构造函数实参（C++11 起） | [[dcl.init.list#4]] |
| `new T(args)` | 分配函数调用先于 *new-initializer* 中的表达式（✱）；初始化先于 new 表达式的值计算 | [[expr.new#25]] |
| `a + b`、`a == b`、`a < b`、`a & b` … | 无序 | ¶10 |

!!! pitfall "重载运算符遵循内建运算符的顺序"
    C++17 起，以运算符记法调用重载运算符时，操作数按内建运算符的规定排序（[[over.match.oper]]，[[expr.call#8]] 注 8）。所以 `std::cout << i++ << i++` 打印 `0 1` 是有保证的。但如果写成函数调用记法 `operator<<(operator<<(std::cout, i++), i++)`，就回到普通函数调用的规则：实参之间不定序，结果未指定。标准例 5 正是对比 `S(i=1) << (i=2)`（i 一定是 2）与 `operator<<(S(j=1), j=2)`（j 是 1 还是 2 未指定）。

```cpp run title="cpp17-order.cpp" ok
#include <cstdio>
#include <iostream>
#include <map>
int main() {
  int i = 0;
  std::cout << i++ << ' ' << i++ << '\n';   // C++17 起保证打印 "0 1"

  std::map<int, int> m;
  m[0] = m.size();      // C++17: 右先于左，size() 在插入之前求值 → m[0] == 0
  std::printf("%d\n", m[0]);
}
```

`m[0] = m.size()` 是 P0145 动机部分里的一个知名例子：C++14 下结果可能是 0 也可能是 1（因为 `operator=` 和 `operator[]` 都是函数调用，二者不定序）。

## 函数调用的顺序（¶11–¶14）

¶11 调用函数 f 时（无论 f 是否 inline）：

| 阶段 | 内容 |
|---|---|
| 1 | 每个实参表达式，以及指代 f 的后缀表达式 |
| 2 | {{c++26}} 函数调用的每个前置条件断言 |
| 3 | 函数体中的每个表达式和语句 |
| 4 | {{c++26}} 函数调用的每个后置条件断言 |

每一阶段都 sequenced before 下一阶段。第 2、4 阶段是 C++26 契约带来的；在 C++23 中，这句话只规定实参和后缀表达式先于函数体内的每个表达式和语句。

"无论是否 inline"强调的是，内联展开只是实现手段，不能改变顺序语义：编译器不能因为把函数内联了，就让函数体内的求值跑到实参求值之前。

¶12 是本节在工程上最有意义的一条。设 F 是以下之一：

- ¶12.1 函数调用，
- ¶12.2 *await-expression* 的求值，
- ¶12.3 *throw-expression* 的求值，

那么同一线程上（若有信号处理函数调用，则属于同一次调用）不在 F 之内的每个求值，要么 sequenced before F 内的全部求值，要么 sequenced after F 内的全部求值。脚注概括为一句话：**函数的执行不会相互交织**。

协程有特殊处理：若 F 调用或恢复一个协程，只有上一次挂起之后、下一次挂起之前的那些求值算在 F 之内，也就是说协程每段连续执行的片段被看作一个整体。

```cpp run title="no-interleave.cpp" unspecified
#include <cstdio>
int i = 0;
int f() { return ++i; }
int main() {
  int r = i + f();    // 不是 UB：i 的值计算与 f() 内的 ++i 是 indeterminately sequenced
  std::printf("%d\n", r);   // 1 或 2，未指定
}
```

与 `i + i++`（UB）对比，区别就在于自增发生在函数内部。¶12 保证 `i` 的读取要么完整地在 `f` 之前、要么完整地在 `f` 之后，不可能与 `++i` 交叠。

这条规则也是 C++17 修复 `unique_ptr` 泄漏问题的关键：

```cpp run title="no-leak.cpp" ok
#include <memory>
struct A {};
int g() { throw 0; }
void h(std::unique_ptr<A>, int) {}
int main() {
  try {
    h(std::unique_ptr<A>(new A), g());   // C++17：g 抛异常时不会泄漏
  } catch (int) {}
}
```

C++14 中，实参的各子表达式之间无序，编译器可能按 `new A` → `g()` → `unique_ptr` 构造的顺序执行；若 `g()` 抛异常，`new A` 的内存就泄漏了（这个案例被反复讨论过，也是推荐使用 `make_unique` 的原因之一）。C++17 起，[[expr.call#8]] 规定每个形参的初始化"包括其所有值计算和副作用"与其他形参的初始化 indeterminately sequenced。`new A` 与 `unique_ptr` 构造是同一个形参初始化的一部分，`g()` 不可能插在中间。

¶13 许多语境会在没有函数调用语法的情况下调用函数：*new-expression* 调用分配函数和构造函数；隐式转换调用转换函数；作用域结束调用析构函数……¶14 说明，上述顺序约束是函数调用本身的属性，与调用的语法形式无关。所以 ¶12 的不交织规则同样适用于隐式调用的构造函数、转换函数、重载运算符。

```cpp run title="pmf-order.cpp" ok
#include <cstdio>
struct S { int m = 0; void set(int v) { m = v; } };
S* get(int& log) { log = log * 10 + 1; static S s; return &s; }
void (S::*getpm(int& log))(int) { log = log * 10 + 2; return &S::set; }
int main() {
  int log = 0;
  (get(log)->*getpm(log))(3);   // C++17: ->* 的 E1 先于 E2
  std::printf("%d\n", log);     // 12
}
```

### 标准自带的链式调用例子

[[expr.call#8]] 的例 4 也来自 P0145 的动机部分：

```cpp run title="chain.cpp" ok
#include <cassert>
#include <string>
int main() {
  std::string s = "but I have heard it works even if you don't believe in it";
  s.replace(0, 4, "").replace(s.find("even"), 4, "only").replace(s.find(" don't"), 6, "");
  assert(s == "I have heard it works only if you believe in it");
}
```

在 C++14 中，`s.find("even")` 可能在第一个 `replace` 之前求值，得到错误的下标。C++17 起，成员调用 `E.replace(...)` 的后缀表达式（包括 `E` 本身，也就是前面的 `replace` 调用）先于实参求值，链式调用就按从左往右的顺序执行了。

## 信号处理函数（¶15）

¶15 若信号处理函数是因为调用 `std::raise` 而执行的，其执行 sequenced after `raise` 的调用、sequenced before `raise` 的返回，就像一次普通的函数调用。注 8：因其他原因（异步信号）执行的处理函数，通常与程序其余部分无序。因此，异步信号处理函数只能安全地访问 `volatile std::sig_atomic_t` 或无锁原子对象（[[intro.races#18]]、[[support.signal]]）。

## 常量求值中的词法顺序（¶16）

¶16 把表达式作为核心常量表达式（[[expr.const.core]]）求值时，原本无序或不定序的运算符操作数和子表达式按词法顺序求值；函数调用中用到的默认实参，按如同在对应位置写了实参那样的顺序求值。

这样规定的动机是，常量求值的结果会参与类型系统（数组界、模板实参），必须在所有实现上一致；而且编译器的常量求值器本来就是按语法树顺序执行的解释器。规定词法顺序后，常量求值中不再有顺序未指定带来的不确定性。

```cpp run title="constexpr-order.cpp" ok
constexpr int h() {
  int i = 0;
  int r = i++ + i++;    // 常量求值中按词法顺序：0 + 1
  return r * 10 + i;
}
static_assert(h() == 12);
int main() {}
```

!!! lawyer "常量求值里的 i++ + i++ 还是 UB 吗？"
    ¶10 的 UB 以无序为前提，而 ¶16 规定这些求值在常量求值中按词法顺序进行。按字面读法，上例在常量求值时有确定结果，Clang 也确实接受并得到 12（同时照例给出 `-Wunsequenced` 警告）。不过同一个函数在运行期调用时，`i++ + i++` 依然是 UB。这条段落是较新草案中加入的，旧标准对常量求值的顺序没有专门规定；若要写可移植代码，不要依赖它。

## 实现视角

!!! impl "编译器如何利用无序性"
    - 求值顺序因 ABI 而异。在实参求值顺序未规定的地方，GCC 在 x86-64 上常常从右往左求值实参，Clang 通常从左往右。`f(i++, i++)` 在两个编译器上输出不同，原因就在这里。
    - C++17 顺序的取舍。P0145 的讨论中也考虑过让函数实参严格从左往右求值，但标准最终只采用了形参初始化彼此不定序这一较弱的保证，保留了实现按调用约定选择顺序的自由。
    - 与 `-fstrict-aliasing` 无关。无序 UB 与别名分析是两回事，但二者都让优化器可以假设同一位置不会在此处被别处修改。

## 历史与演进

!!! history "从顺序点到 sequenced-before"
    - **C++98/03**：使用 C 的顺序点（sequence point）模型：在两个相邻顺序点之间，一个对象最多被修改一次，且只能为了确定新值而读取旧值。`i = ++i + 1` 是 UB。
    - **C++11**：为了支持多线程内存模型，顺序点被替换为本节的 sequenced before / unsequenced / indeterminately sequenced 关系。副作用和值计算被分开描述，一些原先 UB 的表达式变成良定义，例如 `i = ++i + 1`（前置自增的副作用先于其值计算，而赋值又在其后）。
    - **C++17**：[[P0145R3]] 为 `<<` `>>` `=` `@=` `[]` `->*` `.*` 以及函数调用的后缀表达式规定了顺序，形参初始化变为不定序。`i = i++ + 1`、`cout << i++ << i++`、`m[0] = m.size()` 从此有确定结果。
    - **C++20**：协程引入 *await-expression* 的不交织规则；立即调用（`consteval`）成为完整表达式。
    - **C++26**：契约断言的谓词成为完整表达式；函数调用的顺序链中插入前置/后置条件；副作用的定义加入了反射的注入声明。

## 陷阱

!!! pitfall "“C++17 规定了求值顺序”只说对了一半"
    - `a + b`、`f(a, b)`、`a == b` 的操作数顺序仍然未规定。`f(g(), h())` 中 g 和 h 谁先调用仍未指定。
    - 变化只在于 `f(a, b)` 中两个实参不再交叠，每个实参作为整体执行。
    - `std::printf("%d %d", i++, i++)` 在 C++17 中不是 UB，但输出未指定。

!!! pitfall "逗号不总是逗号运算符"
    `f(a, b)` 中的逗号是实参分隔符，没有顺序；`int x = i++, y = i++;` 中的逗号分隔两个 *init-declarator*，每个都是一个完整表达式（¶5.4），所以有序；只有 `(a, b)` 这样的逗号运算符才是 [[expr.comma]] 所说的从左到右。被重载的 `operator,` 在 C++17 前失去顺序保证，C++17 起按运算符记法调用时也遵循内建的从左到右。

!!! pitfall "注 5：同一表达式不同次求值的顺序可以不同"
    在循环里写 `sum += f() * g();`，不能假设每次迭代都先调用 `f`。优化后的代码可能对第一次迭代剥离（peel）后改变调用顺序。

## 思考题

!!! question "1. 下面哪些是 UB？"
    ```cpp
    int i = 0, a[4] = {};
    i = ++i + i++;        // (a)
    a[i++] = i;           // (b)
    i += i++;             // (c)
    i = (i++, i);         // (d)
    ```

<details markdown="1">
<summary>答案</summary>

- (a) UB。右操作数 `++i + i++` 内部，`+` 的两个操作数都修改 `i`，彼此无序。
- (b) OK（C++17 起）。右操作数 `i` 的值计算先于左操作数 `a[i++]` 的全部求值（含 `i++` 的副作用），于是读到 0，写入 `a[0]`，之后 `i` 为 1。C++14 中是 UB。
- (c) OK（C++17 起）。复合赋值同样是右先于左；`i++` 的副作用完成后，再读左边 `i`（已自增）并加上右值。若 `i` 原为 0：右边值 0、`i` 变 1，然后 `i = 1 + 0 = 1`。
- (d) OK。逗号运算符左先于右；`i` 先自增，再读出新值赋回。
</details>

!!! question "2. 为什么 indeterminately sequenced 的冲突不是 UB，而 unsequenced 的冲突是？"

<details markdown="1">
<summary>答案</summary>

依据是注 3 和注 4：unsequenced 的求值可以交叠，编译器可能把一个写操作拆成多条指令，与另一个读写交错，结果可能是任何值（甚至是撕裂的值）。标准不愿约束这种情况，于是规定为 UB，以换取优化自由。而 indeterminately sequenced 的两个求值保证不交叠，只可能是其中之一先完成，只有两种结果，所以只是未指定（unspecified）。
</details>

!!! question "3. `std::cout << f() << g();` 中，f 一定在 g 之前调用吗？如果 `operator<<` 是成员函数呢？"

<details markdown="1">
<summary>答案</summary>

C++17 起一定。无论 `operator<<` 是成员还是非成员，只要用运算符记法，[[over.match.oper]] 都规定操作数按内建 `<<` 的顺序（E1 先于 E2）求值。`(cout << f()) << g()` 中，外层的 E1 是 `cout << f()`，它整体先于 `g()`。C++14 中，若是成员 `operator<<`，后缀表达式 `(cout << f()).operator<<` 与实参 `g()` 之间并无顺序，`g` 可能先被调用。
</details>

## 小结

| 规则 | 段落 |
|---|---|
| 相邻完整表达式严格有序 | ¶9 |
| 默认情况下，运算符操作数、子表达式之间无序；操作数的值计算先于结果的值计算 | ¶10 |
| 同一内存位置上无序的写-写或写-读（含生命周期开始/结束）→ UB | ¶10 |
| 函数调用不交织：调用外的求值与调用内的全部求值不定序 | ¶12 |
| 实参 → 前置条件 → 函数体 → 后置条件 | ¶11 |
| `raise` 触发的信号处理在 `raise` 内部执行 | ¶15 |
| 常量求值中按词法顺序 | ¶16 |
| C++17 给 `<<` `>>` `=` `[]` `->*` 和被调函数加了顺序；`+`、实参之间仍无序/不定序 | [[expr]] 各处 |
