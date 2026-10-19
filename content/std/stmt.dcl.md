---
title: 声明语句
summary: 块里的声明什么时候构造、什么时候销毁；为什么 goto 和 switch 不能跳过变量的初始化；局部 static 变量在首次经过时初始化，线程安全，异常后重试，递归进入是 UB。
status: draft
papers: N2660
related: basic.life, basic.scope.block, stmt.jump, stmt.switch, basic.start.static, basic.start.term, basic.stc.auto, basic.indet
tags: 语句, 生命周期, 初始化, 并发
updated: 2026-10-19
---

!!! tldr
    - 控制每离开一个自动变量的作用域，这个变量就按构造的逆序销毁；每经过一条声明，它声明的变量就初始化。这是 RAII 的语言基础。
    - `goto` 或 `switch` 不能跳进一个变量的作用域而跳过它的初始化，只有什么也不做的初始化（如 `int x;`）可以跳过。
    - 局部 `static` 变量在控制第一次经过声明时初始化；初始化抛出异常则下次重试；多个线程同时到达时只有一个线程初始化，其余等待。
    - 初始化过程中递归地再次进入同一个声明是未定义行为。
    - 局部 `static` 对象只有构造过才会销毁。

## 声明语句（¶1）

¶1 **声明语句**（declaration statement）就是写在块里的 *block-declaration*（[[dcl.pre]]）：变量声明、`using` 声明、别名声明、`static_assert` 等。函数定义、命名空间定义、模板声明不是 *block-declaration*，所以不能写在函数体里。

如果新名字在外层块中已经声明过，外层的声明在本块剩下的部分里被隐藏，离开本块后恢复（注 1，[[basic.lookup.unqual]]）：

```cpp run ok
int x = 1;
int main() {
    int r = x;           // 全局 x，r = 1
    {
        int x = 10;      // 隐藏全局 x
        r += x;          // r = 11
    }
    r += x;              // 又是全局 x，r = 12
    return r == 12 ? 0 : 1;
}
```

隐藏从声明点开始（[[basic.scope.pdecl]]），所以 `int x = x;` 初始化器里的 `x` 已经是正在声明的这个 `x`，读到的是它自己尚未初始化的值。

## 构造、销毁与跳转（¶2）

### 跳回去可以，跳过去不行

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
    if (k < 3) goto ly;      // 每次跳回：先销毁 a，再重新构造
}                            // 输出：X(1) ~X(1) X(2) ~X(2) X(3) ~X(3)
```

向后跳到 `a` 的声明之前，`a` 先被销毁，执行到声明时再重新构造。反方向就不行了：

```cpp error
struct X { X(int); ~X(); };
void f() {
    goto lx;          // error: 跳进 a 的作用域，跳过了它的初始化
ly:
    X a = 1;
lx:
    goto ly;          // OK: 先销毁 a，跳到 ly 后再重新构造
}
```

如果允许第一个 `goto`，到达 `lx` 时 `a` 从未构造过，而离开作用域时却要析构它，之后对 `a` 的使用也都作用在一个不存在的对象上。

### 规则

¶2 标准用活跃变量把这些情形统一起来。块作用域中具有自动存储期的变量，从它的 *init-declarator* 之后到所属作用域结束，都是**活跃的**（[[g:active-variable|active]]）。

函数内控制每次从点 P 转移到点 Q（包括顺序执行下一条语句，但不包括函数调用）时：

1. 在 P 活跃而在 Q 不活跃的变量，按构造的逆序销毁；
2. 然后，在 Q 活跃而在 P 不活跃的变量，按声明顺序初始化；
3. 如果第 2 步中有变量的初始化不是空初始化，这次转移就不能是跳转（jump）。

执行一条声明语句时，P 和 Q 就是紧挨在它前后的两个点；函数返回时，Q 在函数体之后，于是所有局部变量都被销毁。脚注 67 补充，从 `switch` 的条件转到某个 `case` 标号也算跳转。

| 控制转移 | 第 1 步：销毁 | 第 2 步：初始化 |
|---|---|---|
| 顺序执行一条声明语句 | 无 | 新声明的变量，也就是执行这条声明 |
| 离开块（走到 `}`、`break`、`return`、向外 `goto`） | 块中已构造的变量 | 无 |
| 向后 `goto` 到某个声明之前 | 被跳过的变量 | 无 |
| 向前 `goto` 或 `case` 跳过某个声明 | 无 | 需要初始化，但目标处没有初始化器，所以只有空初始化才允许 |

### 空初始化

**空初始化**（[[g:vacuous-initialization|vacuous initialization]]，[[basic.life#2]]）是指变量被默认初始化，没有执行其他初始化，并且如果它是类类型（或类类型的数组），默认初始化选中的是平凡构造函数。这种初始化本来就什么也不做，跳过它和执行它没有区别。

| 声明 | 空初始化吗 | 能被跳过吗 |
|---|---|---|
| `int x;`、`int a[10];` | 是 | 能 |
| `int x = 0;`、`int x{};` | 否 | 不能 |
| `struct P { int a; }; P p;` | 是，平凡默认构造函数 | 能 |
| `P p{};` | 否，值初始化 | 不能 |
| `std::string s;` | 否，构造函数不平凡 | 不能 |
| `static int s = 1;` | 规则只管自动变量 | 能 |

<div class="compare" markdown="1">

```cpp ok
struct P { int a; };
void h(int k) {
  switch (k) {
  case 0:
    P p;      // 空初始化
    p.a = 1;
    (void)p;
    break;
  case 1:     // OK
    break;
  }
}
```

```cpp error
struct P { int a; };
void h(int k) {
  switch (k) {
  case 0:
    P p{};    // 值初始化
    (void)p;
    break;
  case 1:     // error: 跳过 p 的初始化
    break;
  }
}
```

</div>

条件和 *init-statement* 里声明的变量同样受这条规则约束：

```cpp error
int f();
void g() {
    goto L;                  // error: 跳过了条件中 x 的初始化
    if (int x = f()) {
    L: ;
    }
}
```

跳过 `int x;` 是合法的，但被跳过的变量没有确定的值。C++26 起，没有初始化的自动变量持有错误值（[[g:erroneous-value|erroneous value]]，[[basic.indet]]），读取它是错误行为 {{erroneous}}，不再是 UB；变量带 `[[indeterminate]]` 属性时除外，那时读取仍是 UB。

!!! lawyer "非平凡析构函数还算数吗"
    C++11 到 C++17 的措辞要求被跳过的变量具有标量类型，或者是带平凡默认构造函数和平凡析构函数的类类型，并且没有初始化器。现行草案改为只看空初始化，而空初始化只涉及构造函数。按字面读，下面的跳转现在是良构的：`d` 的初始化什么也不做，离开作用域时照常析构。

    ```cpp
    struct D { int v; ~D() {} };   // 平凡默认构造，非平凡析构
    void f(int k) {
        switch (k) {
        case 0: D d; break;
        case 1: break;             // 跳过了 d 的声明
        }
    }
    ```

    本机 Clang 23 仍然拒绝它，诊断是跳转绕过了带非平凡析构函数的变量，也就是沿用了旧规则。

## 局部 static 变量的初始化（¶3）

### 第一次经过时初始化

¶3 块作用域里具有静态或线程存储期的变量，其动态初始化在控制**第一次经过它的声明**时执行；初始化完成后，变量才算已初始化。

这里只说动态初始化。如果变量可以常量初始化（[[basic.start.static]]），比如 `static int n = 42;`、`static constexpr ...`、`static constinit ...`，它在程序启动前就初始化好了，运行时不需要任何判断。

如果函数从未被调用，或者控制从未走到这条声明，变量就永远不会初始化。Meyers 单例的惰性初始化依靠的就是这一点。

### 初始化抛出异常时，下次重试

初始化以异常退出时不算完成，下次控制进入这条声明时会再试一次：

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

### 并发：只初始化一次 {{c++11}}

如果一个线程正在初始化这个变量，另一个线程也进入了声明，后者必须等待初始化完成。所以局部 static 变量的初始化是线程安全的，这一保证由 C++11 引入（[[N2660]]），常被称为 magic statics。下面的单例写法在多线程下不需要任何额外的锁：

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

注 2 要求实现不得因为它自己的同步操作而在初始化器周围引入死锁。因此实现不能用一把全局锁保护所有局部 static 变量：否则 A 的初始化器等待另一个线程初始化 B 时就会卡死。程序逻辑本身造成的死锁则不在保证之内，见思考题 2。

### 递归进入是 UB

如果初始化尚未完成，控制在同一线程里又递归地进入这条声明，行为未定义 {{ub}}（标准例 2）：

```cpp run ub
int foo(int i) {
    static int s = foo(2 * i);    // UB: 递归调用在 s 初始化完成前再次进入这里
    return i + 1;
}
int main() { return foo(1); }
```

本机（macOS，libc++abi）运行这个程序，以 `abort` 终止，并打印以 `__cxa_guard_acquire detected recursive initialization` 开头的消息。libstdc++ 的实现也会检测这种情况并抛出异常。

!!! impl "Itanium C++ ABI 的 guard 变量"
    GCC 和 Clang 为每个需要动态初始化的局部 static 变量生成一个 guard 变量，代码大致如下：

    ```text
    if (guard 的首字节 == 0)                        // acquire 读；已初始化则直接跳过
        if (__cxa_guard_acquire(&guard)) {          // 加锁并再查一次
            try { 初始化变量; }
            catch (...) { __cxa_guard_abort(&guard); throw; }   // 下次重试
            __cxa_guard_release(&guard);            // 标记完成，唤醒等待者
            用 __cxa_atexit 注册析构函数;
        }
    ```

    初始化完成后，每次经过声明只需一次 acquire 读和一次比较。`-fno-threadsafe-statics` 去掉加锁部分，只适用于确定单线程的代码。MSVC 从 Visual Studio 2015 起默认提供线程安全的初始化，`/Zc:threadSafeInit-` 可以关闭。

## 局部 static 对象的销毁（¶4）

¶4 局部 static 或 thread_local 变量所关联的对象，当且仅当它构造过才会销毁。销毁顺序见 [[basic.start.term]]：静态存储期的对象按构造完成的逆序销毁，线程存储期的对象在线程退出时销毁。

所以 `get()` 从未被调用时，其中的 `static Res r;` 也不会析构。上面的伪代码里，析构函数在初始化完成时才注册，正好满足这一点，注册的时刻也决定了它在逆序销毁中的位置。

!!! pitfall "静态对象的销毁顺序"
    如果全局对象 `A` 的析构函数调用了 `get()`，而 `get()` 里的 `static Res r` 比 `A` 晚构造完成，`r` 就会比 `A` 先销毁。`A` 析构时控制经过 `r` 的声明，行为未定义（[[basic.start.term#5]]）。一种常见的规避办法是让对象永不销毁：

    ```cpp ok
    struct Logger { void log(const char*) {} };
    Logger& logger() {
        static Logger& l = *new Logger;   // 有意泄漏：任何静态对象的析构函数里都能安全使用
        return l;
    }
    ```

## 历史与演进

!!! history
    - C++98：局部 static 变量在第一次经过时初始化，异常后重试；跳转规则要求被跳过的变量是 POD 类型且没有初始化器。没有线程，也就没有并发规定。
    - C++11：局部 static 变量的初始化必须线程安全（[[N2660]]），递归进入是 UB；跳转规则改为要求平凡默认构造函数和平凡析构函数。
    - 后来的修订把跳转规则改为基于空初始化，并改写成现在活跃变量加 P→Q 控制转移的形式。
    - C++26：未初始化的自动变量持有错误值，跳过 `int x;` 之后读 `x` 是错误行为（[[basic.indet]]）。

## 常见误解

!!! pitfall "局部 static 变量每次调用都初始化"
    `void f(int n) { static int cache = compute(n); }` 中，`cache` 只用第一次调用时的 `n` 初始化，之后传入的 `n` 不再起作用。

!!! pitfall "局部 static 变量没有开销"
    动态初始化的局部 static 变量每次经过都要做一次 acquire 读和比较，还会妨碍内联后的常量传播。能常量初始化的，写成 `constexpr` 或 `constinit`。

## 思考题

!!! question "思考题 1"
    下面的跳转合法吗？
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

合法，本机 Clang 也接受。`arr` 是默认初始化的 `int` 数组，属于空初始化，可以跳过。`s` 是静态存储期变量，¶2 只管自动变量；况且 `s = 1` 是常量初始化，程序启动前就已完成。`(void)arr` 不读取任何元素，所以也没有错误行为。
</details>

!!! question "思考题 2"
    一个局部 static 变量的初始化器启动了一个线程，这个线程调用同一个函数，初始化器随后 `join` 它。会发生什么？

<details markdown="1">
<summary>答案</summary>

死锁。新线程进入声明时发现变量正在初始化，按 ¶3 必须等待；原线程的初始化器又在等新线程结束。这是程序逻辑造成的死锁，注 2 只要求实现不因自己的同步操作引入死锁，所以标准不保证任何结果。这也不是递归进入，因为再次进入声明的是另一个线程。
</details>
