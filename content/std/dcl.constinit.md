---
title: constinit 说明符
summary: constinit 要求一个静态或线程存储期的变量在静态初始化阶段完成初始化，做不到就报错；它不让变量变成 const，也不要求能在编译期销毁，并且必须写在初始化声明上。
status: done
since: c++20
papers: P1143R2
related: basic.start.static, basic.start.dynamic, expr.const.init, dcl.constexpr, dcl.stc
tags: 声明, 初始化, 静态初始化顺序
updated: 2026-10-19
---

!!! tldr
    - `constinit` 只能用于静态或线程存储期的变量，要求它的初始化是常量初始化，也就是不需要在程序启动时运行任何代码。
    - 是否常量初始化按标准的规则判断；编译器即使能把某个动态初始化优化成静态的，也不算数。
    - `constinit` 变量不是 const，可以修改，可以有非平凡的析构函数，这是它与 `constexpr` 的主要区别。
    - 有声明带 `constinit` 时，初始化声明也必须带；违反这条但在当前翻译单元看不到 `constinit` 声明时，不要求诊断。

## 它解决什么问题

具有静态或线程存储期的变量，初始化分两类（[[basic.start]]）：

- **静态初始化**：零初始化，或者**常量初始化**（初始化器是常量表达式，[[expr.const.init]]）。它在所有动态初始化之前完成，通常就是目标文件 `.data`、`.rodata` 段里现成的字节，不运行任何代码。
- **动态初始化**：其余情况，要在程序启动时（或首次使用前）运行代码。不同翻译单元（TU）之间，动态初始化的先后顺序是不确定的。

如果 TU A 中某个全局变量的动态初始化读取了 TU B 中还没动态初始化的全局变量，读到的就是零值。这就是**静态初始化顺序问题**（static initialization order fiasco）。一个变量是否常量初始化，往往取决于某个构造函数是不是 constexpr、某个调用能否常量求值这类隐蔽的细节，一次改动就可能把它悄悄变成动态初始化。`constinit`（C++20，[[P1143R2]]）把这个性质写成编译器必须检查的声明。

## 只用于静态和线程存储期的变量（¶1）

```cpp run ok
constinit int counter = 0;                      // 命名空间作用域：静态存储期
constinit thread_local int tls_counter = 0;     // 线程存储期
struct S { static constinit int m; };
constinit int S::m = 42;
int f() { static constinit int calls = 0; return ++calls; }   // 块作用域 static
struct P { int a, b; };
constinit auto [pa, pb] = P{1, 2};              // 结构化绑定
int main() { return f() + counter + tls_counter + S::m + pa + pb - 46; }
```

¶1 `constinit` 只能用于具有静态或线程存储期的变量的声明，以及结构化绑定声明。注 1 说明，对结构化绑定，它作用于结构化绑定引入的那个隐藏变量（[[dcl.struct.bind]]）。

```cpp error
void g() { constinit int x = 1; }   // error: 自动存储期
constinit void h();                 // error: 不是变量
```

自动变量每次进入作用域都重新初始化，不存在静态初始化阶段，也就没有初始化顺序问题。想要求局部变量的初始化器是常量表达式，用 `constexpr`。

### 必须写在初始化声明上

¶1 后半部分规定，一个变量只要有一次声明带 `constinit`，它的**初始化声明**（带初始化器或作为定义的那次声明，[[dcl.init]]）就也要带。典型用法是头文件里声明、源文件里定义：

```cpp title="config.h"
extern constinit int max_connections;    // 告诉使用者：它是静态初始化的
```

```cpp title="config.cpp"
#include "config.h"
constinit int max_connections = 64;      // 初始化声明：必须带 constinit
```

只有在初始化声明处，编译器才看得到初始化器，才能检查。如果前面已经有可达的 `constinit` 声明，初始化声明却没写，程序非良构：

<div class="compare" markdown="1">

```cpp error
extern constinit int y;
int y = 1;   // error: 缺少 constinit
             // （Clang 只给警告）
```

```cpp run ok
extern int z;
constinit int z = 1;   // OK
int main() { return z - 1; }
```

</div>

反过来是允许的：前面的声明不带，只有初始化声明带。

如果在初始化声明处根本看不到任何 `constinit` 声明，则不要求诊断 {{ifndr}}：

```cpp title="a.cpp"
extern constinit int x;      // 只有 a.cpp 里有 constinit 声明
int use() { return x; }      // 编译器可以假设 x 已经静态初始化
```

```cpp title="b.cpp"
int compute();
int x = compute();           // 初始化声明没有 constinit，这个 TU 里也看不到
```

编译 b.cpp 时，编译器不知道别处有 `constinit` 声明，无法诊断；编译 a.cpp 时，它已经按 x 是静态初始化的来生成代码了。这种违约在单个 TU 内发现不了，所以是**非良构、不要求诊断**（IFNDR）：编译器可以不报，程序没有任何保证。

## 动态初始化即非良构（¶2–¶3）

```cpp error
const char* g() { return "dynamic initialization"; }
constexpr const char* f(bool p) { return p ? "constant initializer" : g(); }
constinit const char* c = f(true);    // OK: 求值只走 true 分支，不调用 g
constinit const char* d = f(false);   // error: 调用了非 constexpr 的 g
```

这是第 3 段的标准例子。`f` 是 constexpr 函数，有的调用能常量求值，有的不能；`constinit` 检查的是这一次具体的初始化。

¶2 带 `constinit` 的变量如果是动态初始化的，程序非良构，即使实现会把这个初始化当作静态初始化来做。

!!! std
    If a variable declared with the `constinit` specifier has dynamic initialization, the program is ill-formed, even if the implementation would perform that initialization as a static initialization.

[[basic.start.static]] 允许实现把某些动态初始化提前成静态初始化。如果 `constinit` 以这种优化为准，同一份代码就可能在一个编译器上通过、在另一个上失败。所以判断只看标准的规则。

## 与 constexpr、const 的区别

```cpp run ok
#include <mutex>
#include <cstdio>
struct Logger {
    constexpr Logger() = default;     // constexpr 构造函数：可以常量初始化
    ~Logger() { std::puts("bye"); }   // 析构函数不是 constexpr
    int lines = 0;
};
constinit Logger logger;              // OK
constinit std::mutex global_mutex;    // OK: mutex 的默认构造函数是 constexpr
int main() {
    std::lock_guard lk(global_mutex);
    ++logger.lines;                   // OK: constinit 变量不是 const
}
```

`Logger` 的析构函数不是 constexpr，所以它不是字面类型，`constexpr Logger lg;` 会被拒绝；`constinit` 不在乎这一点。`std::mutex` 的默认构造函数是 constexpr 的，目的就是让全局 mutex 能静态初始化，从而在任何动态初始化代码里都能安全使用。`constinit` 让编译器替你确认这一点。

| | `constexpr` 变量 | `constinit` 变量 | `const` 变量 |
|---|---|---|---|
| 初始化必须是常量初始化 | 是 | 是 | 否 |
| 变量是 const | 是 | 否，可修改 | 是 |
| 能用于常量表达式 | 能 | 不能（除非同时是 const 整型等） | 仅 const 整型、枚举且常量初始化 |
| 要求字面类型 | 是 | 否 | 否 |
| 要求能在编译期销毁 | 是 | 否 | 否 |
| 适用的存储期 | 任意 | 仅静态、线程 | 任意 |

需要在常量求值中分配内存的初始化不是常量初始化：

```cpp error
#include <string>
constinit std::string s2 = "a string too long for the small-string buffer of any implementation";
// error: 分配的内存在常量求值结束时没有释放
```

默认构造的空字符串 `constinit std::string s;` 通常良构，因为主流实现的默认构造函数是 constexpr 的，并且不分配内存。

!!! tip "constinit thread_local 与性能"
    从别的 TU 访问一个可能有动态初始化的 `thread_local` 变量时，编译器要先调用一个包装函数，确保它在当前线程已经初始化（见 [[dcl.stc]] 的实现视角）。如果声明上就写明 `constinit`（例如头文件里的 `extern constinit thread_local int x;`），编译器知道不存在动态初始化，可以直接访问 TLS 槽位，省掉一次调用。这是 `constinit` 少有的直接影响代码生成的场合。

!!! impl "实现视角"
    - 本机 Clang 23 对动态初始化的诊断是 "variable does not have a constant initializer"，并指出导致失败的子表达式。
    - 有可达的 `constinit` 声明而初始化声明缺了它，Clang 只给 `-Wmissing-constinit` 警告。按第 1 段，这是要求诊断的非良构情形，警告已经满足诊断要求。
    - C++20 之前，Clang 用属性 `[[clang::require_constant_initialization]]` 做同样的检查，`constinit` 相当于把它标准化了。

!!! pitfall "常见误解"
    - constinit 让变量成为编译期常量：它只保证初值在编译期确定，之后可以随意修改，也不能用在常量表达式中。
    - constinit 解决了所有静态初始化顺序问题：它保证别的全局变量在动态初始化时读到的一定是正确的初值，但管不了析构顺序。
    - constinit 就是去掉 const 的 constexpr：还去掉了字面类型和编译期销毁的要求，而且只能用于静态、线程存储期的变量。

!!! question "思考题"
    以下哪些声明良构？

    ```cpp
    int a = 1;
    constinit int& r1 = a;
    constinit int* p1 = &a;
    constinit int b = a;
    constexpr int c = 2;
    constinit int d = c;
    ```

<details markdown="1">
<summary>答案</summary>

- `r1` 良构：引用绑定到静态存储期的对象 `a`，`a` 的地址是常量表达式，所以是常量初始化。
- `p1` 良构，理由相同。
- `b` 非良构：读取 `a` 的值要做左值到右值转换，而 `a` 既不是 constexpr 变量，也不是 const 整型变量，不能在常量表达式中使用，所以 `b` 是动态初始化。实现很可能把它优化成静态初始化，但第 2 段规定这不算数。本机 Clang 23 报 "variable does not have a constant initializer"。
- `d` 良构：`c` 是 constexpr 变量，可以在常量表达式中使用。
</details>
