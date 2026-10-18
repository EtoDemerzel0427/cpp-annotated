---
title: 不确定值与错误值
summary: 未初始化存储的初值——动态存储期或标记 indeterminate 属性者为不确定值（读取即 UB），其余自动存储期为错误值（C++26 起读取是错误行为而非 UB）；unsigned char/std::byte 的有限例外
status: done
papers: P2795R5
related: dcl.attr.indet, conv.lval, dcl.init, basic.start.static, intro.abstract, defns.erroneous
tags: 未初始化, 错误行为, UB, C++26
updated: 2026-10-17
---

"读未初始化变量"是 C 和 C++ 中历史最悠久、后果最严重的一类 bug：信息泄露（把栈上残留的密钥发到网络上）、不可复现的崩溃、以及优化器基于"UB 不会发生"做出的匪夷所思的变换。C++26 在这里做了一个原则性的改变：

- **C++23 及以前**：读取未初始化的自动变量的值是**未定义行为**（UB）。
- **C++26**：自动变量的未初始化字节具有**错误值**（erroneous value），读取它是**错误行为**（erroneous behavior，{{erroneous}}）——一种**有定义**的行为：结果就是那个错误值，实现被**建议**诊断它，也**允许**终止程序，但**不允许**像对待 UB 那样做任意假设。

这一变化来自 [[P2795R5]]（"Erroneous behaviour for uninitialized reads"），同时引入了 `[[indeterminate]]` 属性作为"退出"机制。

## 什么是错误行为

[[defns.erroneous]] 的定义：**错误行为是良定义的行为，但建议实现对其进行诊断**。配合 [[intro.abstract#6]] 的规定（[[intro.abstract#7]] 是"建议实践：应当诊断"）：

!!! std
    If the execution of an operation is specified as having erroneous behavior, the implementation is permitted to issue a diagnostic and is permitted to terminate the execution of the program.

    若某操作的执行被规定为具有错误行为，实现可以发出诊断，也可以终止程序的执行。

把它和 UB 放在一起对比：

| | 未定义行为（UB） | 错误行为（EB） |
|---|---|---|
| 程序是否正确 | 不正确 | 不正确（注 1："错误行为总是不正确代码的后果"） |
| 行为是否有定义 | 无——整个执行无任何要求，包括"时间旅行"影响之前的行为 | 有——操作产生规定的结果（这里是错误值），程序继续 |
| 实现可以 | 做任何事；优化器可假设它不发生 | 诊断；终止程序；或者继续执行 |
| 优化器能否假设"不会发生" | 能 | **不能** |
| 常量求值中 | 使表达式不是常量表达式 | 同样使表达式不是常量表达式（[[expr.const]]） |

为什么要发明一个新类别，而不是直接规定"未初始化变量为 0"？

1. **零初始化会掩盖 bug**：如果语言保证为 0，那么"忘了初始化"就变成了"合法地依赖 0"，静态分析和 sanitizer 再也无法把它报告为错误。错误行为保留了"这是错的"的语义，工具可以继续报告。
2. **实现自由**：实现可以选一个**模式值**（如 `0xAA` 填充）帮助调试，可以选 0 帮助安全，也可以在调试模式下直接陷入（trap）。
3. **安全性**：不再是 UB，意味着编译器不能因为"读未初始化是 UB"就删除代码分支，消除了一大类由优化导致的安全漏洞。值是**由实现决定、与程序状态无关**的（¶1.2），所以栈上残留的数据不会泄露出去。

## 初始字节值（¶1）

当获得自动或动态存储期对象的存储时，构成存储的字节具有以下初值：

- ¶1.1 若对象具有**动态存储期**，或者是首次声明标有 `[[indeterminate]]` 的变量或函数参数所关联的对象：字节具有**不确定值**（indeterminate value）；
- ¶1.2 否则（即普通的自动存储期变量、参数、临时对象）：字节具有**错误值**（erroneous value），每个值**由实现决定、与程序状态无关**。

如果对象（包括子对象）没有进行初始化，字节保持初值，直到被替换（赋值，或 [[dcl.init.general]] 中的初始化）。

对象层面的结论：若值表示（value representation）中**有任一位**是不确定值，则对象具有不确定值；否则若有任一位是错误值，则对象具有错误值。（不确定"传染性"更强。）

注 2：**静态和线程存储期**的对象总是先被零初始化（[[basic.start.static]]），所以永远不会有不确定值或错误值。

```cpp run title="initial-values.cpp" ok
int g;                       // 静态存储期：零初始化，值为 0

void f() {
    int a;                   // 自动存储期：错误值
    int b [[indeterminate]]; // 自动存储期但标了 [[indeterminate]]：不确定值
    int* p = new int;        // 动态存储期：不确定值
    static int s;            // 静态存储期：0
    (void)a; (void)b; (void)s;   // 只是"提及"而不读取值（弃值表达式中的左值不做左值到右值转换）
    delete p;
}

int main() { f(); return g; }
```

!!! note "为什么动态存储期仍是“不确定”"
    `new int` / `malloc` 的内存若也要变成错误值，实现就必须在每次分配时填充内存（或者至少在 debug 模式下），这对分配器性能影响太大，而且分配器常常复用内存块，无法做到"值与程序状态无关"。P2795 只处理自动变量——这正是成本最低、收益最大的部分（栈上变量的初始化通常可以被优化掉）。

注 1 提醒一个重要细节：**错误值也可能是该类型的无效值**。比如 `bool` 只有 0 和 1 两个有效的值表示，若实现选的错误值模式恰好是 `0xAA`，那么对 `bool` 做左值到右值转换会落入 [[conv.lval#3]] 第 3.3 项——**值表示无效时行为未定义**。所以"EB 不是 UB"有一个限度：对于有无效位模式的类型，读未初始化变量仍可能是 UB。

## 运算与求值（¶2）

### 错误值的传播

¶2 第一句：若一个产生 prvalue 的**内置**运算符的某个被求值的、非弃值表达式的操作数产生了错误值，那么该运算符产生的值也是错误值。也就是说 `x + 1` 中 `x` 是错误值，结果也是错误值——"污点"会传播。

### 一般规则

除下面列出的例外外：

- 某次求值**产生不确定值** ⇒ **UB**；
- 某次求值**产生错误值** ⇒ **错误行为**，求值结果就是那个错误值。

"产生"（produced）通常发生在左值到右值转换（读取变量的值）时。

```cpp run title="eb-vs-undefined.cpp" eb
void use(int);

void g() {
    int x;               // 错误值
    use(x);              // 错误行为（C++26）；C++23 中是 UB
    int y [[indeterminate]];
    // use(y);           // UB：读不确定值
    int* p = new int;
    // use(*p);          // UB：动态存储期，不确定值
    delete p;
}

void use(int) {}
int main() { g(); }
```

### `unsigned char` 与 `std::byte` 的例外

字节类型需要特殊照顾：`memcpy` 的朴素实现、序列化代码、哈希函数常常逐字节复制可能包含**填充位**或尚未初始化部分的对象。如果每次复制一个不确定的字节都是 UB，这类代码就无法写了。所以对**无符号普通字符类型**（`unsigned char`，以及底层是 `unsigned char` 的 `char`——标准用词是 "unsigned ordinary character type"，见 [[basic.fundamental]]）和 `std::byte`，以下几种"搬运"不触发 UB/EB，只是把不确定值或错误值原样传递下去：

| 列表项 | 情形 | 结果 |
|---|---|---|
| ¶2.1.1 | 作为条件表达式的第二或第三操作数 | 结果为该不确定值 / 错误值 |
| ¶2.1.2 | 作为逗号表达式的右操作数 | 同上 |
| ¶2.1.3 | 作为转换到无符号普通字符类型或 `std::byte` 的转换/强转的操作数 | 同上 |
| ¶2.1.4 | 作为弃值表达式 | 同上 |
| ¶2.2 | 作为简单赋值的右操作数，且左操作数是无符号普通字符类型或 `std::byte` 的左值 | 左边对象的值被替换为该不确定值 / 错误值 |
| ¶2.3 | 用于初始化一个无符号普通字符类型的对象 | 该对象被初始化为该不确定值 / 错误值 |
| ¶2.4 | 用于初始化一个 `std::byte` 对象（源为无符号普通字符类型或 `std::byte`） | 同上 |

最后一句：转换无符号普通字符类型或 `std::byte` 的不确定/错误值，产生不确定/错误值；对错误值的情形，转换结果就是被转换操作数的值。

一旦"搬运"变成"使用"——比如把 `unsigned char` 提升为 `int`、参与算术、作为 `if` 条件——就又回到一般规则：不确定值 ⇒ UB，错误值 ⇒ EB。

标准例 1，加上逐行解释：

```cpp title="indet-example.cpp"
#include <cassert>
#include <cstring>

int f(bool b) {
    unsigned char* c = new unsigned char;   // 动态存储期：*c 是不确定值
    unsigned char d = *c;    // OK: ¶2.3，d 被初始化为不确定值（不是 UB）
    int e = d;               // UB: 整型提升到 int，"产生"了不确定值
    return b ? d : 0;        // b 为 true 时 UB：条件表达式的结果类型是 int（d 被提升），¶2.1.1 不适用
}

int g(bool b) {
    unsigned char c;         // 自动存储期：错误值
    unsigned char d = c;     // 没有错误行为（¶2.3），但 d 具有错误值
    assert(c == d);          // 成立：两边的整型提升都是错误行为，结果都是同一个错误值
    int e = d;               // 错误行为
    return b ? d : 0;        // b 为 true 时错误行为
}

void h() {
    int d1, d2;
    int e1 = d1;             // 错误行为
    int e2 = d1;             // 错误行为
    assert(e1 == e2);        // 成立：错误值是确定的某个值，两次读取得到相同结果
    assert(e1 == d1);        // 成立，读 d1 是错误行为
    std::memcpy(&d2, &d1, sizeof(int));   // 没有错误行为（memcpy 按字节复制），但 d2 现在具有错误值
    assert(e1 == d2);        // 成立，错误行为
}
```

这个例子揭示了错误值与不确定值的本质区别：**错误值是一个真实存在的、稳定的值**（`assert(e1 == e2)` 必然成立），只是"使用它"是一个错误；而**不确定值根本不是一个值**——标准不保证两次读取相同，事实上编译器（尤其是 LLVM 的 `undef`/`poison` 语义）确实会让 `x == x` 为假。

## `[[indeterminate]]`：显式退出

有时程序员**有意**不初始化一个大缓冲区，因为接下来马上会整体写满它，初始化纯属浪费：

```cpp run title="indeterminate-attr.cpp" ok
#include <cstddef>
#include <cstring>

std::size_t fill(unsigned char* p, std::size_t n) { std::memset(p, 1, n); return n; }

int main() {
    [[indeterminate]] unsigned char buf[4096];   // 不要求实现做任何初始化/填充
    std::size_t n = fill(buf, sizeof buf);       // 立刻写满
    return buf[n - 1] == 1 ? 0 : 1;
}
```

[[dcl.attr.indet]] 规定：该属性可用于自动存储期块变量的定义，或函数声明中的参数声明；对参数，必须出现在函数的**首次声明**中，不同 TU 不一致时 IFNDR。语义：存储的初值是**不确定值**而不是错误值——相当于把这个变量恢复到 C++23 的语义，读取未初始化部分就是 UB。

这样设计的取向是：**默认安全，需要性能时显式退出**，并且退出点在代码里清晰可见、可被审查。

## 实现视角

!!! impl "编译器如何实现错误值"
    - 最直接的实现手段是**自动变量初始化**：GCC 和 Clang 都提供 `-ftrivial-auto-var-init=zero` 或 `=pattern`，把所有未显式初始化的自动变量填成 0 或某种模式。本机 Clang 23 用 `=pattern` 时，未初始化的 `int` 读出来是 `-1431655766`（即 `0xAAAAAAAA`）。这类选项早于 C++26 就已存在（大型代码库如浏览器、操作系统内核已广泛使用），P2795 实质上是把这一实践标准化，并给"读到它"一个准确的名字。
    - 对应地，Clang 提供 `__attribute__((uninitialized))` 作为单个变量的退出，`[[indeterminate]]` 是其标准化版本。截至写作时，**本机 Clang 23 尚不认识 `[[indeterminate]]`**，会给出 unknown attribute 警告并忽略它（上例仍能编译）。
    - 填充的成本：对于后面立即被完全赋值的变量，优化器能消除死存储，几乎零成本；对于大数组和通过指针逃逸出去的变量，成本可见——这正是 `[[indeterminate]]` 的用武之地。
    - **诊断**：`-Wuninitialized` / `-Wmaybe-uninitialized` 在编译期给出警告；MemorySanitizer（`-fsanitize=memory`）在运行期报告使用未初始化值。C++26 的"建议诊断"允许实现把这些检测做得更激进而不违反标准。

## 历史与演进

!!! history "历史与演进"
    - **C++98–C++11**：未初始化自动变量的值是"不确定的"（indeterminate），使用它是 UB；措辞上没有逐字节的精细规定。
    - **C++14**：本节的前身成型——明确"不确定值"的概念，并引入 `unsigned char` 的例外，使逐字节复制不确定对象成为合法（以支持 `memcpy` 风格的代码）。
    - **C++17**：例外扩展到 `std::byte`。
    - **C++26**：[[P2795R5]] 引入**错误值**与**错误行为**；自动存储期变量默认是错误值；新增 `[[indeterminate]]`；动态存储期保持不确定值。

## 陷阱

!!! pitfall "以为 C++26 后未初始化变量就“安全”了"
    错误行为仍然是**错误**：实现可以终止你的程序；值是实现选择的任意模式，不会是你"期望"的 0；对有无效位模式的类型（`bool`、某些枚举、指针在某些平台上）仍可能是 UB；动态存储期仍是 UB。正确做法依然是：**总是初始化**。

!!! pitfall "以为 `unsigned char` 可以随便用不确定值"
    例外只覆盖"搬运"：初始化、赋值、条件/逗号表达式、转换到字节类型、弃值。`if (c)`、`c + 1`、`printf("%d", c)` 都会把它提升为 `int`，立刻落回 UB/EB。

!!! pitfall "以为类类型成员会被构造函数“自动”初始化"
    `struct T { T() {} int x; };` 的用户提供构造函数没有初始化 `x`。`T t;`（自动存储期）的 `t.x` 是错误值；`new T` 的 `->x` 是不确定值。

## 思考题

!!! question "思考题 1"
    在 C++26 中，下面的函数行为如何？

    ```cpp
    bool flag() {
        bool b;
        return b;
    }
    ```

<details markdown="1">
<summary>答案</summary>

`b` 是自动存储期，具有错误值。`return b;` 对 `b` 做左值到右值转换：如果实现选择的错误值位模式对 `bool` 有效（例如 0），行为是**错误行为**，返回该值；如果无效（例如 `0xAA`），[[conv.lval#3]] 第 3.3 项 规定为**未定义行为**（¶1 注 1）。所以这个函数的行为取决于实现选择的错误值——它是 EB 还是 UB 本身就由实现决定。无论哪种，代码都是错的。
</details>

!!! question "思考题 2"
    `unsigned char a; unsigned char b = true ? a : a;` 有错误行为吗？如果把 `b` 的类型换成 `int` 呢？

<details markdown="1">
<summary>答案</summary>

第一种：条件表达式的第二、第三操作数都是 `unsigned char` 左值，结果类型是 `unsigned char`，¶2.1.1 适用，结果是错误值；然后用它初始化 `unsigned char b`，¶2.3 适用。没有错误行为，`b` 具有错误值。

第二种：`int b = true ? a : a;` 条件表达式本身仍不触发错误行为（¶2.1.1），但用一个 `unsigned char` 的错误值初始化 `int` 需要整型提升——这不在例外之列，产生错误值 ⇒ 错误行为。
</details>

## 小结

| 存储期 / 标记 | 未初始化字节的初值 | 读取（产生该值）的后果 |
|---|---|---|
| 静态 / 线程 | 不存在：先零初始化 | — |
| 自动（默认） | 错误值 | **错误行为** {{c++26}}（C++23：UB） |
| 自动 + `[[indeterminate]]` | 不确定值 | UB |
| 动态（`new`、`malloc`） | 不确定值 | UB |
| 任意，类型为 `unsigned char`/`std::byte`，仅"搬运" | 原样传递 | 无 UB / 无 EB |
| 错误值对该类型无效（如 `bool`） | — | UB（[[conv.lval]]） |
