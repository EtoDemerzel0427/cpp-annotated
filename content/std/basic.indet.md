---
title: 不确定值与错误值
summary: 未初始化的存储里是什么值，读它会怎样：C++26 起普通局部变量是错误值，读取属于错误行为；动态分配的内存和标了 [[indeterminate]] 的变量仍是不确定值，读取是未定义行为。
status: done
papers: P2795R5
related: dcl.attr.indet, conv.lval, dcl.init, basic.start.static, intro.abstract, defns.erroneous
tags: 未初始化, 错误行为, UB, C++26
updated: 2026-10-19
---

!!! tldr
    - C++26 起，没有初始化的局部变量里是一个由实现选定的**错误值**。读取它是错误行为：行为有定义，但实现可以报告或终止程序。
    - `new`/`malloc` 得到的内存，以及标了 `[[indeterminate]]` 的变量，里面是**不确定值**。读取它仍然是未定义行为。
    - 静态和线程存储期的变量总是先零初始化，不会有这两种值。
    - `unsigned char` 和 `std::byte` 有例外：初始化、赋值等只搬运值的操作不算读取，所以可以逐字节复制含有未初始化部分的对象。
    - 错误值也可能对类型无效（比如 `bool` 的某个位模式），这时读取仍是 UB。正确的做法依然是总是初始化。

## 未初始化的变量里是什么（¶1）

```cpp run title="initial-values.cpp" ok
int g;                       // 静态存储期：零初始化，值为 0

void f() {
    int a;                   // 自动存储期：错误值
    int b [[indeterminate]]; // 标了 [[indeterminate]]：不确定值
    int* p = new int;        // 动态存储期：*p 是不确定值
    static int s;            // 静态存储期：0
    (void)a; (void)b; (void)s;   // 弃值表达式不读取值，这里没有错误行为
    delete p;
}

int main() { f(); return g; }
```

¶1 规定了取得自动或动态存储期对象的存储时，这些字节的初值：

- ¶1.1 如果对象具有动态存储期，或者属于首次声明标了 `[[indeterminate]]` 的变量或函数参数，字节具有**不确定值**（indeterminate value）。
- ¶1.2 否则字节具有**错误值**（erroneous value）。每个错误值由实现决定，与程序状态无关。普通的局部变量、函数参数和临时对象都属于这一类。

如果对象（包括它的子对象）没有被初始化，这些字节就一直保持初值，直到被赋值或初始化替换。

整个对象的值按位判断。值表示（对象中真正参与表示值的那些位，见 [[basic.types.general]]）里只要有一位是不确定值，对象就是不确定值；否则只要有一位是错误值，对象就是错误值。不确定值优先。

注 2 提醒，静态和线程存储期的对象总是先零初始化（[[basic.start.static]]），所以永远不会有这两种值。

!!! note "为什么动态分配的内存仍是不确定值"
    要让 `new int` 也得到错误值，分配器就必须在每次分配时填充内存，成本太高。而且分配器会复用内存块，做不到值与程序状态无关。C++26 只处理自动变量，这部分成本最低：变量随后被完整赋值时，编译器通常能把填充消掉。

## 错误行为和未定义行为

读取不确定值是**未定义行为**（UB）：标准对整个执行不作任何要求，优化器可以假设它不会发生。读取错误值是 C++26 新增的**错误行为**（erroneous behavior，EB）。[[defns.erroneous]] 把它定义为良定义的行为，同时建议实现诊断它。[[intro.abstract#6]] 进一步允许实现在执行到错误行为时发出诊断或终止程序。

| | 未定义行为 | 错误行为 |
|---|---|---|
| 程序是否正确 | 不正确 | 不正确 |
| 执行到之后 | 没有任何要求，甚至能影响之前的行为 | 得到规定的结果（这里就是那个错误值），继续执行 |
| 实现可以 | 做任何事 | 诊断、终止，或者继续执行 |
| 优化器能否假设它不发生 | 能 | 不能 |
| 在常量求值中 | 使表达式不是常量表达式 | 同样不是常量表达式（[[expr.const]]） |

C++26 没有直接规定未初始化变量为 0，原因有三：

1. 如果语言保证值为 0，忘记初始化就变成了合法地依赖 0，静态分析和 sanitizer 不能再把它当错误报告。错误行为仍然是错误，工具可以继续报告。
2. 实现有选择的余地：可以填 0 以求安全，可以填 `0xAA` 这样的模式值帮助调试，也可以在调试构建里直接终止。
3. 读取不再是 UB，编译器就不能以此为由删掉代码分支。错误值与程序状态无关，栈上残留的数据（比如上一次调用留下的密钥）也就不会被读出来。

!!! warning "错误值也可能是无效值"
    ¶1 的注 1 指出，如果错误值对对象的类型无效，左值到右值转换（读取对象的值）就是 UB（[[conv.lval]]）。例如 `bool` 只有 0 和 1 两种有效的值表示，若实现选的模式是 `0xAA`，读一个未初始化的 `bool` 就是 UB。对有无效位模式的类型，错误行为不比 UB 安全多少。

## 读取的后果（¶2）

### 一般规则

¶2 规定，除了下一节列出的例外，一次求值产生不确定值时行为未定义；产生错误值时是错误行为，求值结果就是那个错误值。产生值的典型场合是左值到右值转换，也就是读取变量的值。

错误值会沿运算传播。对产生 prvalue 的内置运算符，如果某个经过求值且不是弃值表达式的操作数产生了错误值，运算结果也是错误值。`x` 是错误值时，`x + 1` 同样是错误值。

```cpp run title="eb-vs-ub.cpp" eb
void use(int) {}

void g() {
    int x;               // 错误值
    use(x);              // 错误行为（C++23 中是 UB）
    int y [[indeterminate]];
    // use(y);           // UB：读取不确定值
    int* p = new int;
    // use(*p);          // UB：动态存储期，不确定值
    delete p;
}

int main() { g(); }
```

本机 Clang 23 对 `use(x)` 给出 `-Wuninitialized` 警告；对 `[[indeterminate]]` 给出 unknown attribute 警告并忽略它（见下文）。

### `unsigned char` 和 `std::byte` 的例外

`memcpy` 的朴素实现、序列化和哈希代码经常逐字节复制对象，而对象里可能有填充位或尚未初始化的部分。如果每复制一个这样的字节都是 UB 或 EB，这类代码就没法写。

所以对**无符号普通字符类型**（unsigned ordinary character type）和 `std::byte`，只搬运值的操作不算错误，只是把不确定值或错误值原样传下去。标准没有单独定义这个词，通常理解为 `unsigned char`，以及底层类型是 `unsigned char` 的平台上的 `char`（[[basic.fundamental#7]]）。

| 列表项 | 不确定值或错误值出现在 | 结果 |
|---|---|---|
| ¶2.1.1 | 条件表达式的第二或第三操作数 | 运算结果是同样的不确定值或错误值 |
| ¶2.1.2 | 逗号表达式的右操作数 | 同上 |
| ¶2.1.3 | 转换到无符号普通字符类型或 `std::byte` 的操作数 | 同上 |
| ¶2.1.4 | 弃值表达式 | 同上 |
| ¶2.2 | 简单赋值的右操作数，左操作数是这两种类型的左值 | 左边对象得到这个值 |
| ¶2.3 | 初始化一个无符号普通字符类型的对象 | 该对象得到这个值 |
| ¶2.4 | 初始化一个 `std::byte` 对象 | 同上 |

一旦从搬运变成使用，例如提升为 `int`、参与算术、作为 `if` 的条件，就回到一般规则。下面是标准的例 1，注释是我们加的：

```cpp title="indet-example.cpp"
#include <cassert>
#include <cstring>

int f(bool b) {
    unsigned char* c = new unsigned char;  // *c 是不确定值
    unsigned char d = *c;    // OK：¶2.3，d 得到不确定值
    int e = d;               // UB：提升到 int，产生了不确定值
    return b ? d : 0;        // b 为 true 时 UB：结果类型是 int，¶2.1.1 不适用
}

int g(bool b) {
    unsigned char c;         // 错误值
    unsigned char d = c;     // 没有错误行为（¶2.3），d 得到同一个错误值
    assert(c == d);          // 成立：两边的提升都是错误行为
    int e = d;               // 错误行为
    return b ? d : 0;        // b 为 true 时是错误行为
}

void h() {
    int d1, d2;
    int e1 = d1;             // 错误行为
    int e2 = d1;             // 错误行为
    assert(e1 == e2);        // 成立
    assert(e1 == d1);        // 成立，读 d1 是错误行为
    std::memcpy(&d2, &d1, sizeof(int));   // 没有错误行为，d2 得到同一个错误值
    assert(e1 == d2);        // 成立，错误行为
}
```

这个例子说明了两种值的根本区别。错误值是一个真实、稳定的值，两次读取一定相等，只是使用它是错误。不确定值则不保证是任何确定的值，两次读取可以不同。LLVM 的 `undef` 就有这种性质，优化后 `x == x` 可能为假。

## `[[indeterminate]]`：按需退出

有时不初始化是有意的，比如一个马上就会被整个写满的大缓冲区，填充一遍纯属浪费：

```cpp run title="indeterminate-attr.cpp" ok
#include <cstddef>
#include <cstring>

std::size_t fill(unsigned char* p, std::size_t n) {
    std::memset(p, 1, n);
    return n;
}

int main() {
    [[indeterminate]] unsigned char buf[4096];   // 不要求实现填充
    std::size_t n = fill(buf, sizeof buf);       // 立刻写满
    return buf[n - 1] == 1 ? 0 : 1;
}
```

[[dcl.attr.indet]] 规定，这个属性可以用在自动存储期块变量的定义上，或者函数声明的参数上。用在参数上时必须出现在函数的首次声明中；同一个参数在一个翻译单元的首次声明里标了、在另一个里没标，程序非良构，不要求诊断。标了它的变量恢复 C++23 的语义：初值是不确定值，读取未初始化的部分是 UB。

默认安全，需要性能时显式退出，退出点在代码里清晰可见，便于审查。

## 实现视角

!!! impl "编译器怎样提供错误值"
    - 最直接的手段是自动变量初始化。GCC 和 Clang 都有 `-ftrivial-auto-var-init=zero` 和 `=pattern`，把所有没有显式初始化的自动变量填成 0 或固定模式。本机 Clang 23 用 `=pattern` 时，未初始化的 `int` 读出来是 `-1431655766`，即 `0xAAAAAAAA`。浏览器、操作系统内核等大型项目早在 C++26 之前就在用这类选项，[[P2795R5]] 实际上是把这一做法标准化，并给它的行为起了名字。
    - Clang 的 `__attribute__((uninitialized))` 让单个变量退出自动初始化，`[[indeterminate]]` 是它的标准化版本。截至写作时，本机 Clang 23 还不认识 `[[indeterminate]]`，只给出 unknown attribute 警告并忽略它，上面的例子仍能编译。
    - 对随后被完整赋值的变量，优化器能消除多余的填充，几乎没有成本；对大数组和地址逃逸出去的变量，成本明显，这正是 `[[indeterminate]]` 的用处。
    - `-Wuninitialized`、`-Wmaybe-uninitialized` 在编译期报告，MemorySanitizer（`-fsanitize=memory`）在运行期报告。标准建议诊断错误行为，这些检测可以做得更激进而不违反标准。

## 历史与演进

!!! history
    - C++11 及以前：未初始化自动变量的值是不确定的，使用它是 UB，但没有逐字节的精细规定。
    - C++14：定义了不确定值的逐字节规则，并加入 `unsigned char` 的例外，使逐字节复制成为合法操作（[[CWG1787]]）。
    - C++17：例外扩展到新加入的 `std::byte`。
    - C++26：[[P2795R5]] 引入错误值和错误行为，自动存储期变量默认是错误值，新增 `[[indeterminate]]`；动态存储期保持不确定值。

## 常见误解

!!! pitfall "C++26 之后未初始化变量就安全了"
    错误行为仍然是错误。实现可以终止程序；值是实现选择的模式，不一定是 0；对 `bool`、某些枚举这类有无效位模式的类型，读取仍可能是 UB；动态存储期仍是 UB。

!!! pitfall "`unsigned char` 可以随便使用不确定值"
    例外只覆盖搬运值的操作：初始化、赋值、条件和逗号表达式、转换到字节类型、弃值。`if (c)`、`c + 1`、`printf("%d", c)` 都会把它提升为 `int`，立刻回到一般规则。

!!! pitfall "构造函数会自动初始化成员"
    `struct T { T() {} int x; };` 的用户提供构造函数没有初始化 `x`。`T t;`（自动存储期）的 `t.x` 是错误值，`new T` 的 `->x` 是不确定值。

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

`b` 具有自动存储期，值是错误值。`return b;` 读取 `b`：如果实现选的错误值对 `bool` 有效（例如 0），这是错误行为，返回该值；如果无效（例如 `0xAA`），按 [[conv.lval#3]] 是未定义行为（¶1 注 1）。是 EB 还是 UB 取决于实现选的值。无论哪种，代码都是错的。
</details>

!!! question "思考题 2"
    `unsigned char a; unsigned char b = true ? a : a;` 有错误行为吗？如果把 `b` 的类型换成 `int` 呢？

<details markdown="1">
<summary>答案</summary>

第一种，条件表达式的两个分支都是 `unsigned char` 左值，结果类型也是 `unsigned char`，¶2.1.1 适用，结果是错误值；再用它初始化 `unsigned char b`，¶2.3 适用。没有错误行为，`b` 得到错误值。

第二种，条件表达式本身仍不触发错误行为，但用 `unsigned char` 的错误值初始化 `int` 需要整型提升，不在例外之列，所以是错误行为。
</details>

## 小结

| 存储期或标记 | 未初始化字节的初值 | 读取的后果 |
|---|---|---|
| 静态、线程 | 不会出现：先零初始化 | 无 |
| 自动（默认） | 错误值 | 错误行为 {{c++26}}（C++23：UB） |
| 自动，标了 `[[indeterminate]]` | 不确定值 | UB |
| 动态（`new`、`malloc`） | 不确定值 | UB |
| 任意，以 `unsigned char`/`std::byte` 搬运 | 原样传递 | 无 UB，无 EB |
| 错误值对类型无效（如 `bool`） | 错误值 | UB（[[conv.lval]]） |
