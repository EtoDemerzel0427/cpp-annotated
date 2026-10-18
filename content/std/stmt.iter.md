---
title: 迭代语句：while、do、for
summary: 迭代语句的语法；循环体每轮进出一次的隐式块作用域；C++26 的平凡无限循环；while 的 goto 改写与条件变量的逐轮重建；do 的条件；for 与 while 的等价及两处例外。
status: draft
covers: stmt.iter.general, stmt.while, stmt.do, stmt.for
papers: P2809R3
related: stmt.pre, stmt.ranged, stmt.expand, stmt.cont, stmt.break, intro.progress, basic.scope.block, stmt.dcl
tags: 语句, 循环, 前进保证
updated: 2026-10-17
---

迭代语句（iteration statement）"指定循环"。C++ 有四种：`while`、`do`、经典 `for` 和范围 `for`。前三种本页讲解，范围 `for` 有自己的一页 [[stmt.ranged]]；C++26 新增的 `template for` 虽然长得像循环，却**不是**迭代语句，而是编译期展开的"展开语句"（[[stmt.expand]]）。

标准对循环的定义方式值得注意：只有 `while` 是"原语"（用 `if` + `goto` 定义），`for` 用 `while` 定义，范围 `for` 用 `for` 定义。所以理解了 [[stmt.while#2]] 的改写，就理解了所有循环里对象的构造/析构时机。

## 语法与隐式作用域 [stmt.iter.general]

### 语法（¶1）

¶1 四种迭代语句：

```text
while ( condition ) statement
do statement while ( expression ) ;
for ( init-statement condition(opt) ; expression(opt) ) statement
for ( init-statement(opt) for-range-declaration : for-range-initializer ) statement
```

注 1：*init-statement* 以分号结尾。所以经典 `for` 的 *init-statement* 是**必需的**——`for (;;)` 中第一个分号本身就是一个空的表达式语句（空语句）。

`while` 和 `for` 的括号里是 *condition*（可以是声明，规则见 [[stmt.pre]]）；`do` 的括号里只能是 *expression*。

### 循环体：每轮进出一次的块作用域（¶2）

¶2 迭代语句的子语句隐式定义一个**块作用域**，这个作用域**每一轮循环进入一次、退出一次**。如果子语句是单条语句而不是复合语句，就当作被改写为包含它的复合语句。

这条规定有两个后果：

1. 循环体里声明的变量在循环之后不可见（标准例 1）；
2. 循环体里的自动变量**每轮都被构造和销毁**——它们不是"同一个变量被反复赋值"，而是每轮一个新对象。

```cpp error
void f(int x) {
    while (--x >= 0)
        int i = x;   // 等价于 { int i = x; }
    i = 0;           // error: i 不在作用域内
}
```

```cpp run ok
#include <cstdio>
struct Noisy {
    int n;
    Noisy(int n) : n(n) { std::printf("ctor %d\n", n); }
    ~Noisy() { std::printf("dtor %d\n", n); }
};
int main() {
    for (int k = 0; k < 2; ++k) {
        Noisy x{k};    // 每轮构造一次……
    }                  // ……每轮析构一次
}
```

### 平凡空迭代语句与平凡无限循环（¶3）{{c++26}}

#### 背景：前进保证

[[intro.progress#1]] 允许实现**假定**每个线程最终会做以下之一：终止、调用 `std::this_thread::yield`、调用库 I/O 函数、通过 volatile glvalue 访问、执行原子或同步操作，或者（C++26 新增）继续执行一个平凡无限循环。违反这一假定是 UB。

这条"前进保证"（forward progress guarantee）的初衷是允许编译器删除、合并、重排**无法证明会终止**的空循环。例如编译器希望把

```cpp
for (Node* p = head; p != target; p = p->next) { }
```

当作没有副作用的计算直接删掉（或者推断出 `p == target` 之后的事实），而不必先证明链表是有限的。

代价是：`while (true) { }` 这种**明确写出来的**无限循环也变成了 UB。在嵌入式系统里，"出错后原地死循环、等待看门狗复位"是一种常见写法；在 C++23 及之前，优化器有权把它删掉，让控制"掉进"后面的任意代码。C 语言早在 C11 就把"控制表达式为常量的循环"排除在这种假定之外，C++ 则直到 C++26 才跟进（[[P2809R3]]）。

#### 规则

¶3 **平凡空迭代语句**（[[g:trivially-empty-iteration-statement|trivially empty iteration statement]]）是以下六种形式之一：

| 列表项 | 形式 |
|---|---|
| ¶3.1 | `while ( expression ) ;` |
| ¶3.2 | `while ( expression ) { }` |
| ¶3.3 | `do ; while ( expression ) ;` |
| ¶3.4 | `do { } while ( expression ) ;` |
| ¶3.5 | `for ( init-statement expression(opt) ; ) ;` |
| ¶3.6 | `for ( init-statement expression(opt) ; ) { }` |

它的**控制表达式**（controlling expression）是 `while`/`do`/`for` 中的那个 *expression*；`for` 省略条件时是 `true`。注意：

- 条件必须是**表达式**，不能是声明；
- `for` 必须**没有**迭代表达式（第二个分号后为空），但可以有 *init-statement*；
- 循环体必须为空（`;` 或 `{ }`）。

**平凡无限循环**（trivial infinite loop）是这样一个平凡空迭代语句：它的（转换为 bool 的）控制表达式作为 *constant-expression* 解释时是常量表达式，且值为 `true`。

平凡无限循环的**语句被替换为对 `std::this_thread::yield` 的调用**。由于调用 `yield` 本身就满足前进保证，这类循环不再是 UB：程序确实会永远循环下去。在独立实现（freestanding）上是否做这种替换是实现定义的。

```cpp ok
constexpr bool forever = true;
[[noreturn]] void halt1() { while (true) ; }        // 平凡无限循环（¶3.1）
[[noreturn]] void halt2() { for (;;) { } }          // 平凡无限循环（¶3.6，控制表达式视为 true）
[[noreturn]] void halt3() { do { } while (forever); } // 平凡无限循环（¶3.4）
```

下面这些都**不是**平凡无限循环，仍然受前进保证约束——如果它们真的永不终止且没有副作用，行为未定义：

```cpp ok
int flag;
void spin1() { while (flag) ; }                 // 控制表达式不是常量表达式
void spin2() { for (int i = 0; ; ++i) ; }       // 有迭代表达式：不是平凡空迭代语句
void spin3() { while (true) { int x = 0; (void)x; } }  // 循环体不为空
```

!!! warning "`while (flag) ;` 自旋等待是错误的"
    `spin1` 在另一个线程修改 `flag` 时也不安全：对非原子变量的并发读写是数据竞争（UB），而且编译器可以把 `flag` 的读取提到循环外，把它变成 `if (flag) for (;;);`——再结合前进保证，甚至可以假定循环不存在。正确做法是让 `flag` 成为 `std::atomic<bool>`（原子操作满足前进保证），或者使用条件变量。

!!! lawyer "为什么是 \"替换为 yield\"，而不是直接说 \"不是 UB\"？"
    把语句替换为 `yield()` 是一个**语义改写**：它让平凡无限循环落入 [[intro.progress#1]] 已有的"线程会调用 yield"这一条，因此无需修改前进保证本身的逻辑。注意替换后的循环不再是"空循环"，所以它也不能被删除或与其他代码重排。[[intro.progress#1]] 中新增的 ¶1.6"继续执行平凡无限循环"则从另一个方向确认了这一点。

## while 语句 [stmt.while]

¶1 子语句被反复执行，直到条件的值变为 `false`；测试发生在**每次执行子语句之前**。

¶2 `while ( condition ) statement` **等价于**

```text
label :
{
    if ( condition ) {
        statement
        goto label ;
    }
}
```

这个改写回答了"条件里声明的变量活多久"：它属于 `if` 的作用域，`goto label` 跳出这个作用域时它被销毁（[[stmt.dcl#2]]），回到 `label` 后重新求值条件时它被**重新创建**。注 1 的例子：条件成功一次、失败一次，构造和析构各发生两次。

```cpp run ok
#include <cstdio>
struct A {
    int val;
    A(int i) : val(i) { std::printf("A(%d)\n", i); }
    ~A() { std::printf("~A(%d)\n", val); }
    explicit operator bool() const { return val != 0; }
};
int main() {
    int i = 1;
    while (A a = i) {          // 第 1 轮：A(1) → body → ~A(1)；第 2 轮：A(0) → 条件失败 → ~A(0)
        std::printf("body %d\n", a.val);
        i = 0;
    }
}
```

输出：

```text
A(1)
body 1
~A(1)
A(0)
~A(0)
```

注意第二轮：条件为假时，`a` 在离开 `while` 时（即离开改写中 `if` 的作用域时）被销毁。

`continue` 在 `while` 中的效果是跳到子语句末尾（[[stmt.cont]]），也就是改写中的 `goto label;` 之前，于是下一步就是重新测试条件。

## do 语句 [stmt.do]

¶1 `do` 的括号里是 *expression*，按语境转换为 bool；转换非良构则程序非良构。

¶2 子语句被反复执行，直到表达式的值为 `false`；测试发生在**每次执行子语句之后**——所以子语句至少执行一次。

`do` 没有用 `while` 改写来定义，也没有 *condition*，所以：

- `do ... while (int x = f());` 是非良构的：括号里不能是声明；
- 循环体里声明的变量在 `while (...)` 里**不可见**：循环体是一个块作用域，到 `}` 就结束了。

```cpp error
int read();
void f() {
    do {
        int x = read();
    } while (x != 0);    // error: x 不在作用域内
}
```

```cpp ok
int read();
void f() {
    int x;
    do {
        x = read();
    } while (x != 0);    // 常见写法：把变量提到循环外
}
```

`do { ... } while (0)` 是宏里的经典惯用法：它把多条语句包装成一条**需要以分号结尾**的语句，使宏在 `if (c) MACRO(); else ...` 中仍然正确。

## for 语句 [stmt.for]

### 与 while 的等价（¶1）

¶1 `for ( init-statement condition(opt) ; expression(opt) ) statement` **等价于**

```text
{
    init-statement
    while ( condition ) {
        statement
        expression ;
    }
}
```

**但有两处例外**：

1. *init-statement* 与 *condition* 处于**同一作用域**；
2. *statement* 中的 `continue`（不在另一个迭代语句中）会**先执行 *expression*，再重新求值 *condition***。若按字面改写，`continue` 会跳到 `while` 体的末尾——但改写后的 `while` 体末尾在 `expression ;` 之后，也就是说 `continue` 会跳过 `expression`，这显然不是我们想要的。

注 1 总结：第一个语句是循环的初始化；条件是每轮之前的测试；表达式通常是每轮之后的"递增"。

```cpp run ok
int main() {
    int c = 0;
    for (int k = 0; k < 5; ++k) {
        if (k % 2) continue;   // continue 之后仍执行 ++k
        ++c;
    }
    return c == 3 ? 0 : 1;     // k = 0, 2, 4
}
```

### 作用域细节

*init-statement* 中声明的名字的作用域是整个 `for` 语句；它们与条件中声明的名字处于同一作用域，并且**不能在循环体的最外层块中重新声明**（[[basic.scope.block]]）：

```cpp error
void f() {
    for (int i = 0; i < 3; ++i) {
        int i = 5;               // error: 与 init-statement 中的 i 冲突
    }
    for (int i = 0; int i = 1; ) { }  // error: init-statement 与 condition 同一作用域
}
```

条件中也可以声明变量；和 `while` 一样，它**每轮重建**：

```cpp run ok
int main() {
    int s = 0;
    for (int k = 0; int j = 3 - k; ++k)   // j 依次为 3, 2, 1, 0（0 时退出）
        s += j;
    return s == 6 ? 0 : 1;
}
```

*init-statement* 中的变量则**只创建一次**，整个循环共享同一个对象。这与某些语言（例如 Go 1.22 之后）"每轮一个新循环变量"的语义不同，对按引用捕获的 lambda 尤其重要：

```cpp run ok
#include <functional>
#include <vector>
int main() {
    std::vector<std::function<int()>> fs;
    for (int i = 0; i < 3; ++i)
        fs.push_back([i] { return i; });   // 按值捕获：分别得到 0, 1, 2
    // 若写成 [&i]：所有 lambda 引用同一个 i，循环结束后 i 已经销毁 → 调用时是悬空引用
    return fs[2]() == 2 ? 0 : 1;
}
```

*init-statement* 是一个 *simple-declaration*，所以只能声明**同一基本类型**的若干变量。要声明不同类型的变量，可以用结构化绑定：

```cpp ok
#include <tuple>
void f(const int* a, int n) {
    for (int i = 0, *p = nullptr; i < n; ++i) { (void)p; }           // int 和 int*：同一 decl-specifier
    for (auto [i, p] = std::tuple{0, a}; i < n; ++i, ++p) { (void)*p; } // 不同类型：结构化绑定
}
```

### 省略条件或表达式（¶2）

¶2 条件和表达式可以省略其一或全部。省略条件时，隐含的 `while` 子句等价于 `while (true)`。

## 实现视角

!!! impl "循环体的析构"
    "循环体每轮进出一次块作用域"在代码生成上意味着：每轮迭代末尾（以及 `continue`、`break` 跳转处）都会插入循环体中已构造自动变量的析构调用。对于平凡析构的类型这没有成本；对于 `std::string` 之类的类型，把变量提到循环外复用其缓冲区，是常见的性能手段——它改变的正是 ¶2 规定的语义。

!!! impl "LLVM 的 mustprogress"
    LLVM IR 用 `mustprogress` 函数/循环属性表达"可以假定会前进"。Clang 为 C++ 代码生成这一属性，从而允许删除无副作用的循环；C++26 的平凡无限循环规则要求编译器对这类循环不做这种假定。具体从哪个版本开始、以什么方式处理，以各编译器的发布说明为准。

!!! impl "旧 MSVC 的 for 作用域"
    在 C++98 标准化之前，`for (int i = ...)` 中的 `i` 的作用域延伸到循环之后（ARM 时代的规则）。旧版 MSVC 长期保留这一行为，并提供 `/Zc:forScope` 开关切换为标准行为。现代代码不应依赖它。

## 历史与演进

!!! history
    - **C++98**：`for` 的 *init-statement* 中声明的变量作用域限定在循环内（此前的 ARM 规则是泄漏到外层）。
    - **C++11**：引入多线程内存模型和前进保证（[[intro.progress]]），无副作用的无限循环自此成为 UB。范围 `for`（见 [[stmt.ranged]]）。
    - **C++23**：*init-statement* 允许别名声明（影响 `for` 的 *init-statement*）。
    - **C++26**：平凡无限循环不再是 UB（[[P2809R3]]），其语句被替换为 `std::this_thread::yield()`。

## 陷阱

!!! pitfall "在循环条件中声明的对象每轮重建"
    `while (auto conn = pool.acquire())` 每一轮都获取并在本轮末尾释放连接——这通常正是想要的语义；但如果构造代价昂贵、本意是"复用同一个对象"，就应把它放到循环外。

!!! pitfall "for 的 init-statement 不能声明两种类型"
    `for (int i = 0, double d = 0.0; ...)` 是语法错误：*simple-declaration* 只有一个 *decl-specifier-seq*。用结构化绑定或把其中一个提到循环外。

!!! pitfall "\"空循环会被优化掉\" 不是总成立"
    C++26 起，`while (true);` 不会被删除；但 `while (x);`（`x` 不是常量）依然可以被假定终止。不要依赖空循环来"等待"任何东西。

## 思考题

!!! question "1. 下面哪些是平凡无限循环？"
    ```cpp
    for (int i = 0; true; ) ;            // (a)
    while (1) {}                         // (b)
    do ; while (sizeof(int));            // (c)
    for (;;) { ; }                       // (d)
    while (bool b = true) ;              // (e)
    ```

<details markdown="1">
<summary>答案</summary>

- (a) 是：形式 ¶3.5，有 *init-statement*、条件 `true`、无迭代表达式、体为空语句。
- (b) 是：`1` 按语境转换为 `bool` 后是常量表达式 `true`。
- (c) 是：`sizeof(int)` 非零，转换为 `true`。
- (d) **不是**：循环体 `{ ; }` 既不是 `;` 也不是 `{ }`，不匹配任何一种形式。它仍是一个没有副作用的无限循环，受前进保证约束，即 UB。
- (e) **不是**：条件是声明而不是 *expression*。
</details>

!!! question "2. 下面的 for 循环中，`S` 的构造和析构各发生几次？"
    ```cpp
    struct S { S(int); ~S(); explicit operator bool() const; };
    for (int i = 0; S s = i; ++i) { }   // 假设 S(i) 在 i == 3 时转换为 false
    ```

<details markdown="1">
<summary>答案</summary>

各 4 次。按 [[stmt.for#1]] 改写为 `while (S s = i)`，再按 [[stmt.while#2]] 改写为带 `goto` 的 `if`：每轮（`i` = 0, 1, 2, 3）都构造一次 `s`，测试后在离开 `if` 作用域时销毁。最后一次（`i == 3`）构造后条件为假，`s` 在离开循环时销毁。
</details>

## 小结

| 语句 | 测试时机 | 括号内 | 关键规则 |
|---|---|---|---|
| `while (c) s` | 每轮之前 | *condition* | 等价于 `L: { if (c) { s; goto L; } }`；条件变量每轮重建 |
| `do s while (e);` | 每轮之后 | *expression* | 至少执行一次；体内变量在条件中不可见 |
| `for (i c; e) s` | 每轮之前 | *init-statement* + *condition* + *expression* | 等价于 `{ i while (c) { s; e; } }`；i 与 c 同作用域；`continue` 先执行 e |
| 所有迭代语句 | — | — | 循环体是每轮进出一次的块作用域 |
| 平凡无限循环 {{c++26}} | — | 常量 `true` 的表达式，空体 | 语句被替换为 `std::this_thread::yield()`，不再是 UB |
