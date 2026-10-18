---
title: 声明语句
summary: 块作用域中的声明语句；"活跃"变量与控制转移时的析构/初始化规则（不得跳过非 vacuous 初始化）；局部静态变量的首次经过初始化、异常重试、线程安全（magic statics）、递归 UB；局部静态对象的销毁。
status: draft
papers: N2660
related: basic.life, basic.scope.block, stmt.jump, stmt.switch, basic.start.static, basic.start.term, basic.stc.auto, basic.indet
tags: 语句, 生命周期, 初始化, 并发
updated: 2026-10-17
---

[[stmt.dcl]] 只有四段，但它是 C++ 对象模型在"控制流"方向上的核心：

- ¶2 回答"自动变量**什么时候**被构造、被销毁"，以及"哪些跳转是非法的"——RAII 的语言基础；
- ¶3 回答"局部 `static` 变量**什么时候**被初始化"，包括多线程下的保证（C++11 的 "magic statics"）；
- ¶4 回答"局部 `static` 对象会不会被销毁"。

前置概念：[[basic.life]] 中的**vacuous initialization**（空初始化），[[basic.stc.auto]] 的自动存储期，[[basic.start.static]] 的静态初始化。

## 声明语句（¶1）

¶1 **声明语句**（declaration statement）在块中引入一个或多个新名字，语法上就是一个 *block-declaration*（[[dcl.pre]]）：简单声明、`using` 声明/指令、别名声明、`static_assert`、`asm` 声明、不透明枚举声明等。函数定义、命名空间定义、模板声明**不是** *block-declaration*，不能出现在块中。

注 1：如果新名字在外层块中已经声明过，外层的声明在本块剩余部分被**隐藏**（[[basic.lookup.unqual]]），离开本块后恢复。

```cpp run ok
int x = 1;
int main() {
    int r = x;           // 全局 x = 1
    {
        int x = 10;      // 隐藏全局 x
        r += x;          // 10
    }
    r += x;              // 恢复为全局 x
    return r == 12 ? 0 : 1;
}
```

注意隐藏从**声明点**（[[basic.scope.pdecl]]）开始，所以 `int x = x;` 中初始化器里的 `x` 已经是新声明的那个（未初始化的）`x`。

## 活跃变量与控制转移（¶2）

### 规则

¶2 是本节最重要、也是近年被重新措辞过的一段。它引入一个概念：

> 块作用域中具有自动存储期的变量，在它所属作用域中、它的 *init-declarator* **之后**的所有地方都是**活跃的**（[[g:active-variable|active]]）。

然后对**每一次**函数内的控制转移（包括语句的顺序执行，但不包括函数调用）从点 P 到点 Q：

1. 在 P 活跃而在 Q 不活跃的变量，按构造的**逆序销毁**；
2. 然后，在 Q 活跃而在 P 不活跃的变量，按声明顺序**初始化**；
3. 除非第 2 步中的变量**全部是 vacuous initialization**，否则这次控制转移**不得是跳转**（jump）。

执行一条声明语句时，P 和 Q 分别是紧挨在它之前和之后的点；函数返回时，Q 在函数体之后（于是所有局部变量都不再活跃，全部被销毁）。脚注：从 `switch` 的条件转到 `case` 标号**也算跳转**。

### 为什么这样表述

这个"P → Q"的模型把三种看似不同的情形统一了起来：

| 控制转移 | 第 1 步（销毁） | 第 2 步（初始化） |
|---|---|---|
| 顺序执行一条声明语句 | 无 | 新声明的变量被初始化——这就是"执行声明" |
| 离开块（走到 `}`、`break`、`return`、向外 `goto`） | 块中已构造的变量逆序销毁 | 无 |
| 向后 `goto` 到某个声明之前 | 被跳过的变量销毁 | 无（之后顺序执行到声明时再初始化） |
| 向前 `goto`/`case` 进入某变量的作用域、越过其声明 | — | 变量需要被"初始化"，但跳转的目标处并没有它的初始化器——**除非初始化是 vacuous 的，否则非良构** |

最后一行就是著名的"跳过初始化"（jump past initialization）规则。它的动机很直接：如果允许 `goto` 越过 `std::string s = "x";` 进入 `s` 的作用域，那么之后对 `s` 的使用、以及离开作用域时对 `s` 的析构，都作用在一个从未构造过的对象上。vacuous initialization 是唯一的例外，因为它本来就**什么都不做**——跳过它与执行它没有区别。

### 标准例 1

```cpp error
struct X { X(int); ~X(); };
void f() {
    goto lx;          // error: 跳进 a 的作用域（越过其非 vacuous 初始化）
ly:
    X a = 1;
lx:
    goto ly;          // OK: 跳转意味着先析构 a，然后在 ly 之后重新构造
}
```

第二个 `goto ly` 合法：从 `lx` 到 `ly`，`a` 在 P 活跃、在 Q 不活跃，所以 `a` 被销毁；第 2 步没有需要初始化的变量。接下来顺序执行 `X a = 1;` 时 `a` 被重新构造。

```cpp run ok
#include <cstdio>
struct X {
    int n;
    X(int n) : n(n) { std::printf("X(%d) ", n); }
    ~X() { std::printf("~X(%d) ", n); }
};
int main() {
    int k = 0;
ly:
    X a = ++k;
    if (k < 3) goto ly;      // 每次跳回：先 ~X，再重新构造
}                            // 输出：X(1) ~X(1) X(2) ~X(2) X(3) ~X(3)
```

### 什么是 vacuous initialization

[[basic.life#2]]：变量**默认初始化**、没有执行其他初始化，并且（若是类类型或其数组）默认初始化选中的是**平凡**构造函数。

| 声明 | vacuous? | 能被跳过吗 |
|---|---|---|
| `int x;` | 是 | 能 |
| `int x = 0;` / `int x{};` | 否 | 不能 |
| `struct P { int a; }; P p;` | 是（平凡默认构造） | 能 |
| `P p{};` | 否（值初始化） | 不能 |
| `std::string s;` | 否（非平凡默认构造函数） | 不能 |
| `int a[10];` | 是 | 能 |
| `static int s = 1;`（局部静态） | 不适用：规则只针对自动存储期变量 | 能 |

```cpp ok
struct P { int a; };
void h(int k) {
    switch (k) {
    case 0:
        P p;            // vacuous：允许被跳过
        p.a = 1;
        (void)p;
        break;
    case 1:
        break;
    }
}
```

```cpp error
struct P { int a; };
void h2(int k) {
    switch (k) {
    case 0:
        P p{};          // 值初始化：不是 vacuous
        (void)p;
        break;
    case 1:             // error: 跳转会越过 p 的初始化
        break;
    }
}
```

规则同样适用于条件和 *init-statement* 中声明的变量：

```cpp error
int f();
void g() {
    goto L;                  // error: 越过条件中 x 的初始化，跳进其作用域
    if (int x = f()) {
    L: ;
    }
}
```

!!! lawyer "非平凡析构函数还算数吗？"
    早期标准（例如 C++17）的措辞是：跳过的变量必须"具有标量类型、具有平凡默认构造函数**和平凡析构函数**的类类型……并且没有初始化器"。现行草案改为只看 vacuous initialization，而 vacuous initialization 只涉及构造函数，**不涉及析构函数**。按字面读，下面的跳转在现行草案中是良构的（`d` 的初始化是 vacuous 的，它的生命周期也随之开始，离开作用域时正常析构）：

    ```cpp
    struct D { int v; ~D() {} };   // 平凡默认构造，非平凡析构
    void f(int k) {
        switch (k) {
        case 0: D d; break;
        case 1: break;            // 越过 d 的声明
        }
    }
    ```

    但截至写作时，Clang 仍然拒绝它（诊断说跳转"绕过了具有非平凡析构函数的变量"）。这是实现沿用旧规则还是标准有意放宽，值得留意。

!!! note "跳过 `int x;` 之后读 x"
    跳过 vacuous 初始化是合法的，但被跳过的变量没有确定的值。C++26 起，自动变量在没有初始化时持有**错误值**（erroneous value，[[basic.indet]]），读取它是**错误行为**（erroneous behavior）{{erroneous}}，而不再是 UB（除非变量带 `[[indeterminate]]` 属性）。

## 局部静态变量的初始化（¶3）

### 首次经过时初始化

¶3 块作用域中具有静态或线程存储期的变量，其**动态初始化**在**控制首次经过其声明时**执行；初始化**完成时**变量才被视为已初始化。

要点：

- 这里只说**动态**初始化。如果变量可以**常量初始化**（[[basic.start.static]]），它在程序启动前（静态初始化阶段）就已经初始化好了，根本不需要"首次经过"的判断，也没有任何运行期开销。`static int n = 42;`、`static constexpr ...`、`static constinit ...` 都是这种情况。
- "首次经过"意味着：如果函数从未被调用，或者控制从未走到这个声明，变量**永远不会被初始化**（也不会被销毁，见 ¶4）。这就是"Meyers 单例"实现惰性初始化的原理。

### 初始化抛出异常：下次重试

如果初始化**以异常退出**，初始化不算完成，下次控制进入该声明时**再试一次**。

```cpp run ok
#include <cstdio>
#include <stdexcept>
int attempts = 0;
struct Res {
    Res() {
        if (++attempts < 3) throw std::runtime_error("retry");
        std::puts("constructed");
    }
};
Res& get() { static Res r; return r; }
int main() {
    for (int i = 0; i < 5; ++i) {
        try { get(); std::printf("ok at %d\n", i); break; }
        catch (const std::exception& e) { std::printf("failed: %s\n", e.what()); }
    }
    return attempts == 3 ? 0 : 1;   // 前两次失败，第三次成功
}
```

### 并发：magic statics {{c++11}}

如果控制**并发地**进入声明，而变量正在被初始化，并发的执行**必须等待**初始化完成。也就是说，局部静态变量的初始化是**线程安全**的：只有一个线程执行初始化，其他线程阻塞直到它完成（或因异常放弃，此时另一个线程会重试）。

注 2：实现**不得**在初始化器的执行周围引入死锁。程序逻辑本身仍可能导致死锁（比如两个局部静态变量的初始化互相等待对方，或初始化器里等待另一个也要访问这个变量的线程），实现只需要保证不因**它自己**的同步操作而死锁——这意味着实现不能简单地用一把全局锁保护所有局部静态变量的初始化（否则 A 的初始化器在另一个线程中等待 B 的初始化时就会死锁）。

这一保证由 C++11 引入（[[N2660]]），俗称 **magic statics**。它使得下面这种单例写法在多线程下正确，不需要双重检查锁定：

```cpp run ok
#include <thread>
#include <vector>
struct Config {
    int value;
    Config() : value(42) {}
};
const Config& config() {
    static const Config c;     // 只初始化一次，并发调用安全
    return c;
}
int main() {
    std::vector<std::thread> ts;
    for (int i = 0; i < 8; ++i) ts.emplace_back([] { (void)config().value; });
    for (auto& t : ts) t.join();
    return config().value == 42 ? 0 : 1;
}
```

### 递归进入：UB

如果控制在变量初始化期间**递归地**重新进入该声明，行为未定义 {{ub}}。标准例 2：

```cpp ub
int foo(int i) {
    static int s = foo(2 * i);    // UB: 递归调用在 s 的初始化完成前再次进入此声明
    return i + 1;
}
```

为什么是 UB 而不是要求实现报错？因为检测"是同一线程递归进入"需要额外的记录（谁在初始化），而"等待其他线程完成"的机制在同一线程中只会变成死锁。标准把它留作 UB，允许实现自由处理。实际中，libc++abi 和 libstdc++ 的 guard 实现都会检测这种情况：在本机（macOS，libc++abi）上运行上例，程序以 `abort` 终止，并打印 `__cxa_guard_acquire detected recursive initialization` 开头的消息。

### 实现视角

!!! impl "Itanium C++ ABI 的 guard 变量"
    GCC 和 Clang（Itanium ABI）为每个需要动态初始化的局部静态变量生成一个 **guard 变量**，并生成大致如下的代码：

    ```text
    if (guard 的首字节 == 0 (acquire load)) {          // 快路径：已初始化则直接跳过
        if (__cxa_guard_acquire(&guard)) {             // 加锁并再次检查
            try { 初始化变量; } catch (...) { __cxa_guard_abort(&guard); throw; }
            __cxa_guard_release(&guard);               // 标记完成，唤醒等待者
            注册析构函数 (__cxa_atexit);
        }
    }
    ```

    初始化完成后，每次经过声明的成本只是一个带 acquire 语义的字节读取和一次比较。`-fno-threadsafe-statics` 可以关闭加锁部分（只适用于确定单线程的代码）。`__cxa_guard_abort` 正是 ¶3 "异常时下次重试"的实现。

!!! impl "MSVC"
    MSVC 从 Visual Studio 2015 起默认实现线程安全的局部静态初始化（此前的版本不保证），使用基于线程局部"纪元"计数的方案，快路径同样只是一次比较。`/Zc:threadSafeInit-` 可关闭。

## 局部静态对象的销毁（¶4）

¶4 与块作用域静态/线程存储期变量关联的对象，**当且仅当它被构造过**时才会被销毁。注 3：销毁顺序见 [[basic.start.term]]——静态存储期对象按其**构造完成**的逆序销毁（与 `atexit` 注册的函数交错），线程存储期对象在线程退出时销毁。

"当且仅当被构造过"让惰性初始化的对象也能被正确清理：从未被调用的 `get()` 中的 `static Res r;` 不会被析构。实现上，析构函数是在初始化**完成时**才通过 `__cxa_atexit` 注册的（见上面的伪代码），所以自然满足这一点，并且注册时机决定了逆序销毁中的位置。

!!! pitfall "静态销毁顺序问题"
    如果全局对象 `A` 的析构函数调用了 `get()`，而 `get()` 里的 `static Res r` 在 `A` **之后**完成构造（于是在 `A` **之前**被销毁），`A` 的析构函数就会访问一个已销毁的对象：UB。[[basic.start.term#5]] 明确规定：在静态对象的析构期间调用某函数，而控制流经过该函数中一个**已被销毁**的块作用域静态变量的定义时，行为未定义。常见的规避办法是"泄漏的单例"：`static Res& r = *new Res;`，永不销毁。

```cpp ok
struct Logger { void log(const char*) {} };
Logger& logger() {
    static Logger& l = *new Logger;   // 永不销毁：任何静态对象的析构函数中都可以安全使用
    return l;
}
```

## 历史与演进

!!! history
    - **C++98**：局部静态变量在首次经过时初始化；异常时下次重试；跳过初始化的规则（要求标量或 POD 类型且无初始化器）。并发行为未规定（C++98 没有线程）。
    - **C++11**：局部静态变量初始化线程安全（[[N2660]]），递归进入为 UB；跳过规则的措辞改为基于平凡默认构造函数与平凡析构函数。
    - **此后的修订**（C++23 前后）：跳过规则改为基于 [[basic.life]] 中的 vacuous initialization；本节后来又被改写为"活跃变量 + P→Q 控制转移"的统一表述。
    - **C++26**：未初始化的自动变量持有错误值，读取是错误行为（见 [[basic.indet]]），这影响"被跳过的 `int x;`"之后的读取。

## 陷阱

!!! pitfall "`static` 局部变量的初始化器只运行一次"
    `void f(int n) { static int cache = compute(n); ... }`：`cache` 只用第一次调用时的 `n` 初始化，之后的 `n` 被无视。这是有意的语义，但经常被误解为"每次调用都初始化"。

!!! pitfall "局部静态变量的快路径并非免费"
    在热循环中反复调用一个含局部静态变量的函数，每次都要做一次 acquire load 和比较，且会阻碍部分优化（例如内联后的常量传播）。可以常量初始化的就写 `constexpr`/`constinit`。

## 思考题

!!! question "1. 下面的跳转合法吗？"
    ```cpp
    void f(bool b) {
        if (b) goto skip;
        int arr[4];
        static int s = 1;
    skip:
        (void)arr; (void)s;
    }
    ```

<details markdown="1">
<summary>答案</summary>

合法。跳转到 `skip` 使 `arr` 和 `s` 进入作用域。`arr` 是 vacuous initialization（默认初始化、无平凡性问题的标量数组）；`s` 是静态存储期变量，¶2 只针对自动存储期变量，而且 `s = 1` 是常量初始化，在程序启动前就完成了。注意 `(void)arr` 只是弃值表达式，不读取元素，所以也没有错误行为。
</details>

!!! question "2. 在一个局部静态变量的初始化器中启动一个线程，该线程调用同一个函数并 join，会发生什么？"

<details markdown="1">
<summary>答案</summary>

死锁。新线程进入声明时发现变量"正在被初始化"，按 ¶3 必须等待初始化完成；而初始化器（在原线程中）在等待新线程 join。这是程序逻辑导致的死锁，注 2 明确说实现只需避免由它**自己**的同步引起的死锁，所以标准不保证任何结果——程序会永远挂起（这不是"递归进入"，因为是另一个线程）。
</details>

## 小结

| 规则 | 内容 |
|---|---|
| 声明语句 | *block-declaration*；隐藏外层同名声明直到块结束 |
| 活跃 | 自动变量在其作用域中、*init-declarator* 之后活跃 |
| 控制转移 P→Q | 先逆序销毁"P 活跃、Q 不活跃"的变量，再按声明序初始化"Q 活跃、P 不活跃"的变量 |
| 跳转限制 | 需要初始化的变量全部 vacuous 时才允许是跳转；`switch` 到 `case` 也是跳转 |
| 局部静态初始化 | 动态初始化在首次经过时进行；异常则下次重试；并发等待；递归进入 UB |
| 局部静态销毁 | 构造过才销毁；顺序见 [[basic.start.term]] |
