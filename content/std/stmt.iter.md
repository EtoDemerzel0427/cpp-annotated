---
title: 迭代语句：while、do、for
summary: while、do、for 的执行规则：循环体每轮是一个新的块作用域，while 用 if 加 goto 定义，for 用 while 定义；C++26 起平凡无限循环不再是未定义行为。
status: done
covers: stmt.iter.general, stmt.while, stmt.do, stmt.for
papers: P2809R3
related: stmt.pre, stmt.ranged, stmt.expand, stmt.cont, stmt.break, intro.progress, basic.scope.block, stmt.dcl
tags: 语句, 循环, 前进保证
updated: 2026-10-19
---

!!! tldr
    - 循环体每轮进入、退出一次自己的块作用域，体内的局部变量每轮构造一次、析构一次。
    - `while` 由 `if` 加 `goto` 定义，`for` 由 `while` 定义，范围 `for` 又由 `for` 定义；条件里声明的变量因此每轮重建。
    - `for` 的 *init-statement* 只执行一次，里面的变量整个循环共用一个对象；`continue` 会先执行迭代表达式再测试条件。
    - `do` 的括号里只能是表达式，循环体里声明的变量在 `while (...)` 里看不见。
    - C++26 起，`while (true);`、`for (;;) {}` 这类平凡无限循环被替换为反复调用 `std::this_thread::yield()`，不再是未定义行为；条件不是常量的空循环仍然可以被假定会终止。

C++ 有四种迭代语句：`while`、`do`、`for` 和范围 `for`。范围 `for` 见 [[stmt.ranged]]。C++26 的 `template for` 看起来像循环，其实是在编译期展开的展开语句，不是迭代语句（[[stmt.expand]]）。

标准只把 `while` 当作原语，用 `if` 加 `goto` 定义它，其余循环都改写成 `while`。理解了 `while` 的改写，就知道了所有循环里对象何时构造、何时析构。

## 循环体每轮是一个新作用域 [stmt.iter.general]

```cpp run ok
#include <cstdio>
struct Noisy {
    int n;
    Noisy(int n) : n(n) { std::printf("ctor %d\n", n); }
    ~Noisy() { std::printf("dtor %d\n", n); }
};
int main() {
    for (int k = 0; k < 2; ++k) {
        Noisy x{k};
    }   // 输出 ctor 0, dtor 0, ctor 1, dtor 1
}
```

¶2 迭代语句的子语句隐式定义一个块作用域，每轮循环进入一次、退出一次。所以 `x` 不是同一个变量被反复赋值，而是每轮一个新对象，在这一轮结束时析构。

如果子语句是单条语句而不是复合语句，就当作它外面套了一对花括号（标准例 1）。因此循环体里声明的变量，循环之后看不见：

```cpp error
void f(int x) {
    while (--x >= 0)
        int i = x;   // 等价于 { int i = x; }
    i = 0;           // error: i 不在作用域内
}
```

¶1 列出四种语法：

```text
while ( condition ) statement
do statement while ( expression ) ;
for ( init-statement condition(opt) ; expression(opt) ) statement
for ( init-statement(opt) for-range-declaration : for-range-initializer ) statement
```

`while` 和 `for` 的括号里是 *condition*，可以是声明（[[stmt.pre]]）；`do` 的括号里只能是 *expression*。*init-statement* 本身以分号结尾，所以 `for (;;)` 的第一个分号是一条空的表达式语句。

## while [stmt.while]

¶1 `while` 在每次执行循环体之前测试条件，直到条件为 `false`。

¶2 `while ( condition ) statement` 等价于

```text
label :
{
    if ( condition ) {
        statement
        goto label ;
    }
}
```

这个改写决定了条件里声明的变量活多久。它属于 `if` 的作用域；`goto label` 跳出这个作用域时它被销毁（[[stmt.dcl#2]]），回到 `label` 重新求值条件时它被重新创建：

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
    while (A a = i) {
        std::printf("body %d\n", a.val);
        i = 0;
    }
}
```

```text
A(1)
body 1
~A(1)
A(0)
~A(0)
```

条件成功一次、失败一次，构造和析构各两次，这正是 ¶2 的注 1 所举的例子。条件失败的那一次，`a` 在离开 `while` 时析构。

`while` 里的 `continue` 跳到循环体末尾（[[stmt.cont]]），也就是改写中 `goto label;` 之前，所以下一步就是重新测试条件。

## do [stmt.do]

¶2 `do` 在每次执行循环体之后测试，所以循环体至少执行一次。¶1 括号里的表达式按语境转换为 `bool`，转换非良构则程序非良构。

`do` 没有用 `while` 改写来定义，括号里也不能是声明。循环体是一个块作用域，到 `}` 就结束了，所以体内的变量在条件里看不见：

<div class="compare" markdown="1">

```cpp error
int read();
void f() {
    do {
        int x = read();
    } while (x != 0);  // error
}
```

```cpp ok
int read();
void f() {
    int x;
    do {
        x = read();
    } while (x != 0);  // OK
}
```

</div>

`do { ... } while (0)` 是宏的常见写法：它把多条语句包成一条必须以分号结尾的语句，使宏放在 `if (c) MACRO(); else ...` 里仍然正确。

## for [stmt.for]

### 与 while 的等价和两处例外

¶1 `for ( init-statement condition(opt) ; expression(opt) ) statement` 等价于

```text
{
    init-statement
    while ( condition ) {
        statement
        expression ;
    }
}
```

有两处例外。第一，*init-statement* 与条件在同一个作用域。第二，循环体里的 `continue`（不在内层循环里）会先执行 *expression*，再重新求值条件。按字面改写，`continue` 会跳到 `while` 体的末尾，也就是 `expression ;` 之后，从而跳过递增，这显然不是想要的。

```cpp run ok
int main() {
    int c = 0;
    for (int k = 0; k < 5; ++k) {
        if (k % 2) continue;   // 之后仍执行 ++k
        ++c;
    }
    return c == 3 ? 0 : 1;     // k = 0, 2, 4
}
```

¶2 条件和迭代表达式都可以省略。省略条件时，隐含的 `while` 相当于 `while (true)`。

### 作用域和对象的生存期

*init-statement* 里声明的名字作用域是整个 `for` 语句，与条件里的名字在同一作用域，也不能在循环体的最外层重新声明（[[basic.scope.block]]）：

```cpp error
void f() {
    for (int i = 0; i < 3; ++i) {
        int i = 5;              // error: 与外面的 i 冲突
    }
    for (int i = 0; int i = 1; ) { }  // error: 同一作用域
}
```

条件里声明的变量和 `while` 一样每轮重建：

```cpp run ok
int main() {
    int s = 0;
    for (int k = 0; int j = 3 - k; ++k)   // j 依次为 3, 2, 1, 0
        s += j;
    return s == 6 ? 0 : 1;
}
```

*init-statement* 里的变量只创建一次，整个循环共用一个对象。有些语言（例如 Go 1.22 起）每轮给循环变量一个新对象，C++ 不是这样。这对 lambda 的捕获很重要：

```cpp run ok
#include <functional>
#include <vector>
int main() {
    std::vector<std::function<int()>> fs;
    for (int i = 0; i < 3; ++i)
        fs.push_back([i] { return i; });   // 按值捕获：0, 1, 2
    return fs[2]() == 2 ? 0 : 1;
}
```

如果写成 `[&i]`，三个 lambda 引用的都是同一个 `i`，而循环结束后 `i` 已经销毁，调用时就是悬空引用。

*init-statement* 是一条简单声明，只有一组声明说明符，所以 `for (int i = 0, double d = 0; ...)` 是语法错误。不同类型的变量可以用结构化绑定：

```cpp ok
#include <tuple>
void f(const int* a, int n) {
    for (int i = 0, *p = nullptr; i < n; ++i) { (void)p; }
    for (auto [i, p] = std::tuple{0, a}; i < n; ++i, ++p) { (void)*p; }
}
```

第一行能写，是因为 `int` 和 `int*` 共用声明说明符 `int`，`*` 属于声明符。

## 平凡无限循环 {{c++26}}

### 问题：空循环可以被删掉

```cpp
void halt() { while (true) ; }
int  wait(int x) { while (x) ; return 1; }
```

用本机 Clang 23 以 `-O2` 编译，`halt` 被编译成一个真正的死循环，`wait` 却被编译成直接返回 1，循环整个消失了。

原因是**前进保证**（forward progress guarantee，[[intro.progress#1]]）：实现可以假定每个线程最终会做下面的事之一：终止、调用 `std::this_thread::yield`、调用库 I/O 函数、访问 volatile 对象、执行原子或同步操作。一个既不终止也不做这些事的循环是未定义行为，编译器可以假定它不存在。这让编译器能删掉无法证明会终止的空循环，例如遍历链表找某个节点而不做其他事的循环，不必先证明链表有限。

代价是 `while (true) ;` 这种有意写下的死循环也成了未定义行为。嵌入式程序出错后原地死循环、等待看门狗复位，是常见写法。C 从 C11 起就把控制表达式是常量的循环排除在这一假定之外，C++26 通过 [[P2809R3]] 跟进。

### 规则

¶3 **平凡空迭代语句**（[[g:trivially-empty-iteration-statement|trivially empty iteration statement]]）是循环体为空的下面六种形式之一：

| 列表项 | 形式 |
|---|---|
| ¶3.1、¶3.2 | `while ( expression ) ;`、`while ( expression ) { }` |
| ¶3.3、¶3.4 | `do ; while ( expression ) ;`、`do { } while ( expression ) ;` |
| ¶3.5、¶3.6 | `for ( init-statement expression(opt) ; ) ;`、`for ( init-statement expression(opt) ; ) { }` |

条件必须是表达式而不是声明；`for` 可以有 *init-statement*，但不能有迭代表达式。括号里的那个表达式叫**控制表达式**，`for` 省略条件时控制表达式是 `true`。

如果控制表达式转换为 `bool` 后是常量表达式，值为 `true`，这个语句就是**平凡无限循环**（[[g:trivial-infinite-loop|trivial infinite loop]]）。平凡无限循环的循环体被替换为对 `std::this_thread::yield` 的调用。调用 `yield` 本身就满足前进保证，所以这样的循环不再是未定义行为，程序确实一直循环下去。在独立实现（freestanding，没有完整标准库的环境）上是否做这个替换由实现定义。

```cpp ok
constexpr bool forever = true;
[[noreturn]] void halt1() { while (true) ; }           // ¶3.1
[[noreturn]] void halt2() { for (;;) { } }             // ¶3.6，控制表达式视为 true
[[noreturn]] void halt3() { do { } while (forever); }  // ¶3.4
```

下面这些都不是平凡无限循环，仍受前进保证约束：如果它们真的永不终止，又不做任何可观察的事，行为未定义。

```cpp
int flag;
void spin1() { while (flag) ; }            // 控制表达式不是常量
void spin2() { for (int i = 0; ; ++i) ; }  // 有迭代表达式
void spin3() { while (true) { int x = 0; (void)x; } }  // 循环体不空
```

!!! warning "`while (flag) ;` 不能用来等待另一个线程"
    另一个线程写 `flag`、这里读 `flag`，本身就是数据竞争，即未定义行为。编译器还可以把读取提到循环外，再按前进保证假定循环会终止。要等待另一个线程，把 `flag` 改成 `std::atomic<bool>`（原子操作满足前进保证），或者用条件变量。

## 实现视角

!!! impl "循环体变量的析构"
    循环体每轮进出一次作用域，意味着每轮末尾，以及 `continue`、`break` 处，都要析构体内已经构造的局部变量。对平凡析构的类型没有开销；对 `std::string` 这类类型，把变量提到循环外以复用缓冲区是常见的优化，它改变的正是 ¶2 规定的语义。

!!! impl "旧 MSVC 的 for 作用域"
    C++98 之前，`for (int i = ...)` 里 `i` 的作用域延伸到循环之后。旧版 MSVC 长期保留这一行为，用 `/Zc:forScope` 切换到标准行为。

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

- (a) 是：形式 ¶3.5，有 *init-statement*，没有迭代表达式，条件是 `true`。
- (b) 是：`1` 转换为 `bool` 后是常量 `true`。
- (c) 是：`sizeof(int)` 非零，转换为 `true`。
- (d) 不是：循环体 `{ ; }` 既不是 `;` 也不是 `{ }`。它仍是没有副作用的无限循环，因此是未定义行为。
- (e) 不是：条件是声明，不是表达式。
</details>

!!! question "2. 下面的循环里，`S` 构造和析构各几次？"
    ```cpp
    struct S { S(int); ~S(); explicit operator bool() const; };
    for (int i = 0; S s = i; ++i) { }   // 假设 S(3) 转换为 false，其余为 true
    ```

<details markdown="1">
<summary>答案</summary>

各 4 次。按 [[stmt.for#1]] 改写成 `while (S s = i)`，再按 [[stmt.while#2]] 改写成带 `goto` 的 `if`。`i` 为 0、1、2、3 时各构造一次 `s`，每次都在离开 `if` 的作用域时析构；最后一次条件为假，`s` 在离开循环时析构。
</details>

## 小结

| 语句 | 何时测试 | 括号内 | 要点 |
|---|---|---|---|
| `while (c) s` | 每轮之前 | *condition* | 等价于 `L: { if (c) { s; goto L; } }`，条件变量每轮重建 |
| `do s while (e);` | 每轮之后 | *expression* | 至少执行一次；体内变量在条件里不可见 |
| `for (i c; e) s` | 每轮之前 | *init-statement*、*condition*、*expression* | 等价于 `{ i while (c) { s; e; } }`；i 只执行一次；`continue` 先执行 e |
| 所有迭代语句 | | | 循环体每轮是一个新的块作用域 |
| 平凡无限循环 {{c++26}} | | 常量 `true`，空循环体 | 循环体替换为 `std::this_thread::yield()`，不再是未定义行为 |
