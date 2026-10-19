---
title: 存储类说明符
summary: static、thread_local、extern、mutable 能用在哪里、能怎样组合；同一实体的所有声明必须给出相同的链接；auto 和 register 为什么不再是存储类说明符。
status: done
papers: P0001R1
related: basic.stc, basic.link, basic.def, class.static, class.union.anon, dcl.inline
tags: 声明, 存储期, 链接
updated: 2026-10-19
---

!!! tldr
    - 存储类说明符有四个：`static`、`thread_local`、`extern`、`mutable`。一条声明至多写一个，只有 `thread_local` 可以和 `static` 或 `extern` 同时出现。
    - 命名空间作用域的变量本来就是静态存储期，`static` 在那里只把链接改为内部链接；在块里，`static` 才改变存储期。
    - 块作用域的 `thread_local` 变量隐含 `static`：每个线程一份，跨调用保留。
    - 同一实体的所有声明必须给出相同的链接：先 `static` 后 `extern` 可以（继承内部链接），先外部链接后 `static` 是错误。
    - `mutable` 只能用于非 const、非引用的非静态数据成员，让它在 const 对象里也能修改。

这四个说明符的名字来自 C，但只有 `static` 和 `thread_local` 真正决定存储期（[[basic.stc]]）。`extern` 主要影响链接以及声明是不是定义（[[basic.link]]、[[basic.def]]），`mutable` 与存储无关。本节规定它们能用在哪里、能怎样组合，语义效果大多由上面这些条款给出。

## 组合规则（¶1）

```cpp run ok
extern thread_local int counter;           // OK: thread_local 可以和 extern 一起写
thread_local int counter = 0;              // 所有声明都带 thread_local
static struct Point { int x, y; } origin;  // static 作用于 origin，不作用于 Point
static union { int u_i; float u_f; };      // 匿名联合体可以没有声明符
int main() { return counter + origin.x + u_i; }
```

¶1 规定：

1. 一个说明符序列中至多一个存储类说明符，例外是 `thread_local` 可以和 `static` 或 `extern` 同时出现。
2. 变量的任何一个声明带 `thread_local`，它的所有声明都必须带。
3. 不能和 `typedef` 同时出现，类型别名没有存储期。
4. 声明符列表不能为空，命名空间作用域的匿名联合体除外。存储类说明符修饰的是被声明的变量或函数，没有声明符就没有修饰对象。
5. 它只作用于声明符声明的名字，不作用于其他说明符顺带声明的名字。所以上例中的 `static` 不会让类 `Point` 获得内部链接，类名的链接由 [[basic.link#4]] 决定。

```cpp error
thread_local int x;
extern int x;                  // error: x 的声明必须都带 thread_local
typedef static int SI;         // error: typedef 不能和存储类说明符组合
static struct T { };           // error: 没有声明符
```

本机 Clang 23 对最后一行只给出警告，警告也满足诊断要求。注 1 提醒，显式特化（[[temp.expl.spec]]）和显式实例化（[[temp.explicit]]）对存储类说明符另有限制。

¶2（注）块里声明的变量和函数参数，如果没有存储类说明符，默认具有自动存储期。

## static（¶4）

¶4 `static` 只能用于变量和函数的声明、结构化绑定声明和匿名联合体的声明。块里不能有 `static` 函数声明，函数参数也不能是 `static`。用于变量时，它让变量具有静态存储期（[[basic.stc.static]]）；和 `thread_local` 一起用时则是线程存储期。

`static` 在不同位置的效果，都是赋予静态存储期和决定链接这两件事的组合：

| 位置 | `static` 的效果 | 依据 |
|---|---|---|
| 命名空间作用域的变量、函数 | 内部链接（变量本来就是静态存储期） | [[basic.link#3]] |
| 块里的变量 | 静态存储期，第一次经过声明时初始化 | [[basic.stc.static]]、[[stmt.dcl]] |
| 类的数据成员 | 静态数据成员，不属于任何对象 | [[class.static.data]] |
| 类的成员函数 | 静态成员函数，没有 `this` | [[class.static.mfct]] |
| 命名空间作用域的匿名联合体 | 所在命名空间具有外部链接时必须写 | [[class.union.anon#2]] |
| 块里的函数声明、函数参数 | 非良构 | ¶4 |

```cpp error
void f() {
    static void g();         // error: 块里不能声明 static 函数
}
void h(static int x);        // error: 参数不能是 static
union { int a; float b; };   // error: 全局命名空间里的匿名联合体必须是 static
```

块里的函数声明总是指向命名空间作用域的某个函数，链接从先前的声明继承。在块里写 `static` 想表达内部链接，却又不能在块里定义这个函数（函数定义不是块声明，[[dcl.pre#1]]），这种写法没有用处，C 和 C++ 都禁止它。

## thread_local（¶3）

¶3 `thread_local` 表示实体具有**线程存储期**（[[g:thread-storage-duration|thread storage duration]]，[[basic.stc.thread]]）：每个线程有自己的一份对象，线程结束时销毁。它只能用于命名空间作用域或块作用域的变量、结构化绑定声明和静态数据成员，不能用于非静态数据成员和函数。

在块里，`thread_local` 没有伴随其他存储类说明符时**隐含 `static`**。所以块作用域的 `thread_local` 变量不是每次进入块都新建的自动变量，而是每个线程一份、跨调用保留：

```cpp run ok
#include <thread>
#include <cstdio>
struct S { static thread_local int per_thread; };
thread_local int S::per_thread = 0;          // 静态数据成员的定义也要带 thread_local

int next_id() {
    thread_local int id = 0;                 // 隐含 static
    return ++id;
}

int main() {
    next_id(); next_id();
    std::thread t([] { std::printf("worker: %d\n", next_id()); });   // 新线程从 1 开始
    t.join();
    std::printf("main: %d\n", next_id());                             // 3
}
```

```cpp error
struct S { thread_local int m; };     // error: 非静态数据成员不能是 thread_local
thread_local void f();                // error: 函数不能是 thread_local
```

!!! impl "TLS 与包装函数"
    主流平台用操作系统和动态链接器提供的 TLS 机制实现 `thread_local`（ELF 的 `.tbss`、`.tdata` 段，访问时可能经过 `__tls_get_addr`）。变量需要动态初始化或有非平凡析构函数时，Itanium C++ ABI 会为它生成一个包装函数（符号名以 `_ZTW` 开头）和一个初始化函数（`_ZTH`）。其他翻译单元访问这个变量时先调用包装函数，确保本线程的初始化已经完成，所以访问外部的 `thread_local` 变量可能比访问普通全局变量贵得多。能保证常量初始化时，写成 `constinit thread_local`（[[dcl.constinit]]）可以省掉这层包装。

## extern（¶5、¶7）

¶5 `extern` 只能用于变量和函数的声明，不能用于类成员和函数参数。`extern template`（显式实例化声明）和 `extern "C"`（链接规格）里的 `extern` 不是存储类说明符（注 3）。

```cpp run ok
extern const int limit = 100;   // 定义：有初始化器；extern 让 const 变量具有外部链接
extern int later;               // 声明，不是定义
int later = 5;                  // 定义
int use() {
    extern int later;           // 块里的 extern：指向全局的 later
    return later + limit;
}
int main() { return use() - 105; }
```

`extern` 的效果分布在几个条款里：

1. 没有初始化器时，它让声明不成为定义（[[basic.def#2]]）。`extern int x = 1;` 是定义。
2. 它影响链接。命名空间作用域的 const 变量默认是内部链接，加 `extern` 后是外部链接（[[basic.link#3]]）；之前的声明是内部链接时，`extern` 声明继承内部链接（见 ¶6）。
3. 块里的 `extern int n;` 声明的是外围命名空间的成员，名字只绑定在块里（[[dcl.meaning.general#3.5]]）。它不能带初始化器，因为初始化器只能出现在目标作用域与所在作用域相同的变量声明上（[[dcl.decl.general#4]]）。

```cpp error
struct X { extern int a; };     // error: 不能用于类成员
void f() { extern int y = 1; }  // error: 块里的 extern 声明不能有初始化器
```

¶7 只声明而尚未定义的类，可以出现在 `extern` 声明中，但只能以不需要完整类型的方式使用：

```cpp error
struct S;
extern S a;           // OK: 不是定义，不需要 S 完整
extern S f();         // OK
extern void g(S);     // OK
void h() {
    g(a);             // error: 按值传参需要 S 完整
    f();              // error: 调用返回不完整类型的函数
}
```

只有定义才要求对象类型完整（[[basic.def#5]]），所以 `extern S a;` 合法，`&a` 也可以，取地址不需要完整类型。

## 所有声明的链接必须相同（¶6）

¶6 同一实体的所有声明必须给出相同的链接。注 4 补充：有些声明的链接受先前声明的影响；重载的函数是不同的实体，互不影响。

标准例 1 的要点：

| 先 | 后 | 结果 |
|---|---|---|
| `static char* f();` | `char* f() {…}` | OK，仍是内部链接 |
| `char* g();` | `static char* g() {…}` | error：链接不一致 |
| `void h();` | `inline void h();` | OK，外部链接，`inline` 不影响链接 |
| `static void n();` | `inline void n();` | OK，内部链接 |
| `static int b;` | `extern int b;` | OK，`b` 仍是内部链接 |
| `int c;` | `static int c;` | error：链接不一致 |
| `extern int d;` | `static int d;` | error：链接不一致 |
| `static int a;` | `int a;` | error：两个定义 |

先内部后 `extern` 可以，反过来却不行。`extern` 的意思是指向一个已有的实体，前面有可见的声明就沿用它的链接；`static` 则主动声明内部链接。如果允许后者覆盖前者，同一个名字在翻译单元的前后两部分就会指向不同的实体。

```cpp run ok
static int counter;          // 内部链接
extern int counter;          // 仍是内部链接
static void helper();
void helper() { }            // 仍是内部链接
void f(int);                 // 外部链接
static void f(char);         // OK：重载是不同的实体
static void f(char) { }
int main() { helper(); f('x'); return counter; }
```

表中最后一行的错误不在链接上：`int a;` 继承了内部链接，但它本身也是一个定义，于是 `a` 有两个定义（[[basic.def.odr]]）。本机 Clang 23 的报错说的是非 static 声明跟在 static 声明之后，标准例子给出的理由是两个定义。

## mutable（¶8–9）

¶8 `mutable` 只能用于**非静态数据成员**，并且该成员的类型既不是 const 限定的，也不是引用类型。

```cpp run ok
#include <mutex>
class Cache {
    mutable std::mutex m;          // 在 const 成员函数里也能加锁
    mutable int hits = 0;          // 统计信息
    int value = 42;
public:
    int get() const {
        std::lock_guard lk(m);     // m 不是 const，可以 lock()
        ++hits;                    // OK
        return value;
    }
};
int main() { const Cache c; return c.get() - 42; }
```

```cpp error
class X {
    mutable const int* p;     // OK: p 本身不是 const，它指向 const int
    mutable int* const q;     // error: q 本身是 const
    mutable int& r;           // error: 引用类型
    mutable static int s;     // error: 至多一个存储类说明符
};
```

¶9（注）`mutable` 抵消了外层对象的 const：即使对象是 const，这个成员也能修改（[[basic.type.qualifier]]）。通过 const 对象访问 mutable 成员得到的是非 const 左值（[[expr.ref]]）。mutable 成员不是 const 对象，所以修改它不是 [[dcl.type.cv#4]] 所说的修改 const 对象的 UB。

`mutable const int` 自相矛盾；引用不能重新绑定，`mutable` 对它也没有意义，所以两者都被禁止。

lambda 的 `[x]() mutable { ++x; }` 里的 `mutable` 是 lambda 说明符（[[expr.prim.lambda.general]]），它让闭包的调用运算符不是 const 成员函数，与本节无关。

## auto 与 register 的退役

!!! history
    - C++98/03 的存储类说明符有 `auto`、`register`、`static`、`extern`、`mutable`。`auto` 显式表示自动存储期，与默认相同，几乎没人用；`register` 是寄存器分配的提示。
    - C++11 把 `auto` 改作占位类型说明符（[[dcl.spec.auto]]），理由是旧用法几乎不存在；同时加入 `thread_local`，并弃用 `register`。
    - C++17 移除了作为存储类说明符的 `register`（[[P0001R1]]），关键字保留以备将来使用。C 语言里 `register` 仍然有效。

```cpp error
void f() {
    register int x = 0;    // error: C++17 起 register 不是存储类说明符
    auto int y = 0;        // error: C++11 起 auto 不是存储类说明符
}
```

本机 Clang 23 对 `register` 报错，诊断属于 `-Wregister`，可以关掉以兼容 C 头文件；对 `auto int` 只给出 `-Wauto-storage-class` 警告。按标准两者都非良构。

## 常见误解

!!! pitfall "static 全局变量和普通全局变量的存储期不同"
    命名空间作用域的变量本来就是静态存储期，`static` 只改变链接。

!!! pitfall "extern 声明不能有初始化器"
    命名空间作用域的 `extern` 声明可以有初始化器，这样的声明是定义。只有块里的 `extern` 声明不能有。

!!! pitfall "const 全局变量是外部链接"
    在 C 里是这样，在 C++ 里命名空间作用域的非 volatile const 变量默认是内部链接（[[basic.link#3]]）。例外有四种：显式写了 `extern`；是 `inline` 变量；之前已有一个非内部链接的声明；或者它声明在模块接口单元或模块分区里。最后一种情况下按一般规则得到外部链接或模块链接（[[basic.link#4]]），所以头文件里的 `const int N = 10;` 搬进模块接口后，含义会有变化。

## 思考题

!!! question "思考题 1"
    下面的程序良构吗？两个 `x` 是同一个实体吗？
    ```cpp
    namespace {
        int x;
    }
    extern int x;
    ```

<details markdown="1">
<summary>答案</summary>

良构，而且是两个实体。`extern int x;` 位于全局命名空间，声明的是 `::x`，具有外部链接；无名命名空间里的 `x` 具有内部链接。两者的目标作用域不同，互不冲突。

但此后在全局作用域写 `x` 会产生歧义：无名命名空间带有一条隐式的 using 指令，非限定查找会同时找到两个 `x`（[[basic.lookup.unqual]]、[[namespace.unnamed]]）。本机 Clang 23 在 `int y = x;` 处报告对 `x` 的引用有歧义。
</details>

!!! question "思考题 2"
    `struct A { mutable int n; }; const A a{1};` 之后，`const_cast<A&>(a).n = 2;` 和 `a.n = 2;` 分别是什么行为？去掉 `mutable` 呢？

<details markdown="1">
<summary>答案</summary>

有 `mutable` 时两者都良构，行为确定：`a.n` 本身就是非 const 左值（[[expr.ref]]），`n` 不是 const 对象。去掉 `mutable` 后，`a.n = 2;` 非良构，因为它给 const 左值赋值；`const_cast<A&>(a).n = 2;` 能编译，但 `a.n` 是 const 对象的子对象，修改它是 UB（[[dcl.type.cv#4]]）。
</details>
