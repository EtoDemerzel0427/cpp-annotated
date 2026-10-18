---
title: constinit 说明符
summary: constinit 断言一个静态/线程存储期变量在静态初始化阶段完成初始化；它不使变量成为 const，也不要求常量析构；必须出现在初始化声明上
status: done
since: c++20
papers: P1143R2
related: basic.start.static, basic.start.dynamic, expr.const.init, dcl.constexpr, dcl.stc
tags: 声明, 初始化, 静态初始化顺序
updated: 2026-10-17
---

`constinit`（C++20，[[P1143R2]]）是一个**断言**：它不改变变量的任何语义，只要求编译器**证明**该变量是在**静态初始化**阶段完成初始化的（[[basic.start.static]]），否则报错。它要解决的是 C++ 最臭名昭著的问题之一——**静态初始化顺序灾难**（static initialization order fiasco）。

背景：具有静态或线程存储期的变量，初始化分为两类（[[basic.start]]）：

- **静态初始化**：零初始化，或者**常量初始化**（初始化器是常量表达式，[[expr.const.init]]）。在任何动态初始化之前完成，通常直接体现为目标文件中 `.data`/`.rodata` 段里的字节，不需要运行任何代码。
- **动态初始化**：其他情况，需要在程序启动时（或首次使用前）运行代码。不同 TU 之间的动态初始化顺序**未规定**。

若 TU A 中的全局变量的动态初始化读取了 TU B 中尚未被动态初始化的全局变量，就会读到零初始化的值——这就是"灾难"。而一个变量"是否被常量初始化"往往取决于很隐蔽的细节（某个构造函数是不是 constexpr、某个函数调用能否常量求值），代码改动可能悄悄把它从静态初始化变成动态初始化。`constinit` 把这个隐含的性质变成可检查的声明。

## 适用对象（¶1）

¶1 `constinit` 只能用于：

- 具有**静态或线程存储期**的变量的声明；
- **结构化绑定声明**（Note 1：作用于结构化绑定引入的那个唯一命名的隐藏变量）。

```cpp run ok
constinit int counter = 0;                      // 命名空间作用域：静态存储期
constinit thread_local int tls_counter = 0;     // 线程存储期
struct S { static constinit int m; };
constinit int S::m = 42;
int f() { static constinit int calls = 0; return ++calls; }   // 块作用域 static：静态存储期
struct P { int a, b; };
constinit auto [pa, pb] = P{1, 2};              // 结构化绑定
int main() { return f() + counter + tls_counter + S::m + pa + pb - 46; }
```

```cpp error
void g() { constinit int x = 1; }   // error: 自动存储期的变量
constinit void h();                 // error: 不是变量
```

为什么不允许用于自动变量？自动变量每次进入作用域都会重新初始化，不存在"静态初始化阶段"，也就不存在初始化顺序问题。若想要求局部变量的初始化器是常量表达式，用 `constexpr`。

### 必须出现在初始化声明上

¶1 后半：若某个声明带了 `constinit`，那么**初始化声明**（initializing declaration，即带初始化器或作为定义的那个声明，[[dcl.init]]）也必须带。若在初始化声明处**没有任何** `constinit` 声明可达，则不要求诊断 {{ifndr}}。

典型用法是在头文件中声明、在源文件中定义：

```cpp title="config.h"
extern constinit int max_connections;    // 告诉使用者：这个变量是静态初始化的
```

```cpp title="config.cpp"
#include "config.h"
constinit int max_connections = 64;      // 初始化声明：必须带 constinit
```

为什么要求它出现在**初始化声明**上？因为只有在那里编译器才看得到初始化器，才能检查它。而 IFNDR 的那半句针对的是这种情形：

```cpp title="a.cpp"
extern constinit int x;      // 只在 a.cpp 中有 constinit 声明
int use() { return x; }      // 编译器可以假设 x 已静态初始化（不必插入初始化检查）
```

```cpp title="b.cpp"
int compute();
int x = compute();           // 初始化声明没有 constinit，且 b.cpp 中看不到任何 constinit 声明
```

b.cpp 的编译器根本不知道别处有 `constinit` 声明，无法诊断；而 a.cpp 的编译器已经基于"x 静态初始化"的承诺生成了代码。这种违约无法在单个 TU 内发现，所以是 IFNDR。

```cpp error
extern constinit int y;
int y = 1;                   // error: 已有 constinit 声明可达，初始化声明也必须带（Clang 仅给 -Wmissing-constinit 警告）
```

反过来是允许的：前面的声明不带 `constinit`，只有初始化声明带——`constinit` 只需出现在初始化声明上。

```cpp run ok
extern int z;
constinit int z = 1;         // OK
int main() { return z - 1; }
```

## 动态初始化即非良构（¶2）

¶2 若带 `constinit` 的变量具有**动态初始化**，程序非良构——**即使实现会把这个动态初始化作为静态初始化来执行**（[[basic.start.static]] 允许实现把某些动态初始化提前为静态初始化）。

!!! std
    If a variable declared with the `constinit` specifier has dynamic initialization, the program is ill-formed, even if the implementation would perform that initialization as a static initialization.

"即使实现会……"这半句保证了**可移植性**：是否常量初始化由标准的规则判定，不取决于某个编译器的优化能力。否则同一份代码可能在一个编译器上通过、在另一个上失败。

¶3 标准例子：

```cpp error
const char* g() { return "dynamic initialization"; }
constexpr const char* f(bool p) { return p ? "constant initializer" : g(); }
constinit const char* c = f(true);    // OK: 常量求值走 true 分支，不调用 g
constinit const char* d = f(false);   // error: 调用了非 constexpr 的 g，不是常量初始化
```

注意 `f` 是一个 constexpr 函数，它**有些**调用可以常量求值、有些不行。`constinit` 检查的是**这一次**初始化。

## constinit 与 constexpr、const 的区别

| | `constexpr` 变量 | `constinit` 变量 | `const` 变量 |
|---|---|---|---|
| 初始化必须是常量初始化 | 是 | 是 | 否 |
| 变量是 const | **是** | **否**（可修改） | 是 |
| 可用于常量表达式 | 是 | 否（除非另外是 const 整型等） | 仅 const 整型/枚举且常量初始化 |
| 要求字面类型 | 是 | 否（构造用的构造函数须是 constexpr） | 否 |
| 要求常量析构 | 是 | **否** | 否 |
| 适用存储期 | 任意 | 仅静态/线程 | 任意 |
| 隐式 inline | 静态数据成员是 | 否 | 否 |

最重要的区别：`constinit` 变量**可以修改**，析构函数**可以不平凡**。

```cpp run ok
#include <mutex>
#include <cstdio>
struct Logger {
    constexpr Logger() = default;          // constexpr 构造：可以常量初始化
    ~Logger() { std::puts("bye"); }        // 非平凡析构：constexpr 变量不行，constinit 可以
    int lines = 0;
};
constinit Logger logger;                   // OK
constinit std::mutex global_mutex;         // OK: std::mutex 的默认构造函数是 constexpr
int main() {
    std::lock_guard lk(global_mutex);
    ++logger.lines;                        // OK: constinit 变量不是 const
}
```

`std::mutex` 是 `constinit` 的典型受益者：它的默认构造函数是 `constexpr` 的，正是为了让全局 mutex 能被静态初始化，从而在任何动态初始化代码中安全使用。`constinit` 让这一点得到编译器保证。

```cpp error
#include <string>
constinit std::string s2 = "a string too long for the small-string buffer of any implementation";
// error: 需要在常量求值中分配内存，而这块内存在求值结束时没有释放 → 不是常量初始化
```

（`constinit std::string s;`——默认构造的空字符串——通常是良构的，因为主流实现的默认构造函数是 constexpr 且不分配。）

!!! tip "`constinit thread_local` 与性能"
    跨 TU 访问一个具有动态初始化的 `thread_local` 变量时，编译器必须调用 TLS 包装函数，以确保本线程中该变量已初始化（见 [[dcl.stc]] 的实现视角）。若在**声明**（如头文件中的 `extern constinit thread_local int x;`）上就标明 `constinit`，编译器知道不存在动态初始化，可以直接访问 TLS 槽位，省掉函数调用。这是 `constinit` 少有的"直接影响代码生成"的场合。

!!! impl "实现视角"
    - Clang 对动态初始化的诊断为 "variable does not have a constant initializer"，并附上导致失败的子表达式。
    - 对"已有 `constinit` 声明可达、但初始化声明缺少 `constinit`"的情形，Clang 只给出 `-Wmissing-constinit` 警告；按 ¶1 这是要求诊断的非良构情形（警告即满足诊断要求）。
    - 在 C++20 之前，Clang 提供 `[[clang::require_constant_initialization]]` 属性实现同样的检查，`constinit` 实际上是把它标准化。

!!! pitfall "常见误解"
    - "constinit 让变量成为编译期常量"——不。它只保证**初始值**是编译期确定的；之后变量可以随意修改，也不能用在常量表达式中。
    - "constinit 解决了所有静态初始化顺序问题"——它只保证**这个**变量不会在动态初始化阶段才被赋值；若其他全局变量的动态初始化读取了它，读到的一定是正确的初值；但它不能保证**析构**顺序（静态析构顺序问题依然存在）。
    - "`constinit` 等于 `constexpr` 去掉 const"——还要去掉"字面类型"与"常量析构"的要求，而且只能用于静态/线程存储期变量。

!!! summary "小结"
    - `constinit` = "请证明这个静态/线程存储期变量是常量初始化的"。
    - 必须出现在初始化声明上；仅在别的 TU 中有 `constinit` 声明时，不要求诊断。
    - 是否常量初始化按标准规则判断，与实现是否做了"提前"无关。
    - 变量**不是** const，可以有非平凡析构。

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

- `r1`：良构。引用绑定到静态存储期对象 `a`，`a` 的地址是常量表达式；这是常量初始化。
- `p1`：良构，理由同上。
- `b`：非良构。读取 `a` 的值需要左值到右值转换，`a` 不是 constexpr、也不是 const 整型变量，不能在常量表达式中使用，所以 `b` 是动态初始化（尽管实现很可能把它优化成静态初始化——¶2 明确说这不算数）。
- `d`：良构。`c` 是 constexpr 变量，可在常量表达式中使用。
</details>
