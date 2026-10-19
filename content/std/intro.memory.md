---
title: 内存模型
summary: 字节是存储的基本单位，每个字节有唯一的地址；内存位置是一个标量对象或一串相邻的非零宽位域，两个线程可以无干扰地访问不同的内存位置。
status: done
related: intro.races, intro.object, basic.types, class.bit
tags: 内存模型, 位域, 并发
updated: 2026-10-19
---

!!! tldr
    - 字节是最小的可寻址存储单位，至少 8 位，具体位数是实现定义的 `CHAR_BIT`。
    - 程序的内存是一段或多段连续字节，每个字节有唯一的地址。
    - 内存位置是一个非位域的标量对象，或者一串相邻的、宽度都不为零的位域。
    - 两个线程同时写不同的内存位置不会互相干扰；同时写同一个内存位置而不同步，就是数据竞争。
    - 相邻的位域默认共享一个内存位置，用零宽位域 `: 0` 可以把它们分开。

## 字节（¶1–¶2）

¶1 C++ 内存模型的基本存储单位是**字节**（[[g:byte|byte]]）。标准对它有三点要求：

- 一个字节至少能放下基本字面量字符集（[[lex.charset]]）里任意字符的普通字面量编码，以及 UTF-8 的一个 8 位码元。后一条意味着字节至少有 8 位。
- 字节由连续的若干位组成，位数是实现定义的，就是 `<climits>` 里的 `CHAR_BIT`。主流平台都是 8，有些 DSP 上是 16 或 32。
- 程序可用的内存由一段或多段连续字节组成，每个字节有唯一的地址。

`sizeof(char)`、`sizeof(signed char)`、`sizeof(unsigned char)` 都是 1（[[expr.sizeof]]），`std::byte` 也占一个字节。字节是存储单位，`char` 是类型，二者大小相同。

标准写的是一段或多段，而不要求整个地址空间是一个平坦的数组。所以比较两个无关对象的指针（`p < q`）结果是未指定的（[[expr.rel]]），指针算术也只能在同一个数组之内进行（[[expr.add]]）。在分段内存上，跨段比较地址没有意义。

每个字节有唯一的地址，这是对象地址规则（[[intro.object#10]]）的基础：对象的地址就是它第一个字节的地址。

¶2 是一个注，指向 [[basic.types.general]]：类型的对象表示和值表示在那里定义。

## 内存位置（¶3）

```cpp run title="separate-locations.cpp" ok
#include <thread>

struct S {
    char a;
    char b;     // a 和 b 是两个内存位置
};

S s;

int main() {
    std::thread t1([] { for (int i = 0; i < 100000; ++i) s.a = char(i); });
    std::thread t2([] { for (int i = 0; i < 100000; ++i) s.b = char(i); });
    t1.join();
    t2.join();
}   // 没有数据竞争：两个线程写的是不同的内存位置
```

两个线程同时写同一个结构体的相邻成员，没有加锁，程序却是正确的。原因在于两个成员是不同的**内存位置**（[[g:memory-location|memory location]]）：

!!! std
    A *memory location* is the storage occupied by the object representation of either an object of scalar type that is not a bit-field or a maximal sequence of adjacent bit-fields all having nonzero width.

¶3 内存位置有两种：

- 一个不是位域的标量对象（算术类型、枚举、指针、成员指针、`std::nullptr_t`）占据的存储。类对象和数组本身不是内存位置，它们由若干内存位置组成。
- 一串相邻的、宽度都不为零的位域，并且取尽可能长的一串，直到遇到非位域成员、零宽位域或者结构体的边界为止。

¶3 的最后一句是对实现的要求：两个或多个执行线程可以访问不同的内存位置而互不干扰。编译器不能为了写 `s.a` 而生成一次顺带覆盖 `s.b` 的宽写入，除非能证明没有别的线程能观察到。

数据竞争（[[intro.races]]）就是以内存位置为单位定义的：两个线程访问同一个内存位置，至少一个是写，又没有同步，行为未定义。

注 3 补充，引用、虚函数这些语言机制可能用到程序访问不到的额外内存位置，例如 vptr，它们的并发安全由实现负责。

### 为什么位域要合在一起

硬件不能只写 3 个位。要修改一个位域，编译器必须读出包含它的整个存储单元，改掉其中几位，再写回去。两个线程分别修改同一个单元里的两个位域，两次读-改-写就会互相覆盖。

标准承认了这一点，把一串相邻的位域定义成同一个内存位置。同时修改它们就是数据竞争，需要程序员自己同步：

```cpp run title="bitfield-race.cpp" ub
#include <thread>

struct Flags {
    unsigned ready : 1;
    unsigned error : 1;   // 与 ready 在同一个内存位置
};

Flags f{};

int main() {
    std::thread t1([] { f.ready = 1; });
    std::thread t2([] { f.error = 1; });  // UB: 与 t1 访问同一内存位置且没有同步，数据竞争
    t1.join();
    t2.join();
}
```

本机用 `-fsanitize=thread` 编译运行，ThreadSanitizer 报告 `data race`。修复的办法有三种：加互斥锁；在两个位域之间插入零宽位域；或者不用位域，改用 `std::atomic<unsigned>` 加位运算。

```cpp run title="bitfield-fixed.cpp" ok
#include <thread>

struct Flags {
    unsigned ready : 1;
    unsigned       : 0;   // 零宽位域：把两个位域分到不同的内存位置
    unsigned error : 1;
};

Flags f{};

int main() {
    std::thread t1([] { f.ready = 1; });
    std::thread t2([] { f.error = 1; });  // OK：不同的内存位置
    t1.join();
    t2.join();
}
```

## 哪些位域共享内存位置（¶4–¶5）

¶4 是一个注，把 ¶3 的定义展开成几条可以直接套用的结论。两个位域只要中间有东西把序列隔断，就在不同的内存位置：

| 情形 | 同一内存位置吗 |
|---|---|
| 位域与相邻的非位域成员 | 否 |
| 两个位域之间有零宽位域 `: 0` | 否 |
| 两个位域之间有非位域成员 | 否 |
| 一个在嵌套的结构体里，一个不在 | 否 |
| 两个位域之间全是非零宽的位域 | 是 |

¶5 的例子：

```cpp run title="bitfield-locations.cpp" ok
struct S {
    char a;          // 内存位置 #1
    int b : 5,       // ┐
        c : 11,      // ┘ 内存位置 #2：b、c 相邻且宽度都不为零
          : 0,       // 零宽位域：断开序列
        d : 8;       // 内存位置 #3
    struct {
        int ee : 8;  // 内存位置 #4：在嵌套的结构体里
    } e;
};

int main() {
    S s{};
    s.a = 1; s.b = 2; s.c = 3; s.d = 4; s.e.ee = 5;
}
```

`a`、`d`、`e.ee` 可以与其他任何成员同时修改；`b` 和 `c` 不能同时修改，但 `b` 和 `a` 可以。

!!! warning "无名的非零宽位域不会隔断"
    规则只要求位域宽度不为零，没有要求它有名字。`int x : 3; int : 5; int y : 4;` 里的 `x`、无名位域和 `y` 是同一个内存位置，`x` 和 `y` 不能同时修改。只有宽度为零的无名位域才起隔断作用。

## 实现视角

!!! impl "编译器怎样写位域"
    - 在 Itanium C++ ABI（Linux、macOS 上的 GCC 和 Clang）下，位域的分配单元由声明的类型决定，相邻位域在单元里连续存放，`: 0` 让下一个位域从新的分配单元开始。MSVC 的规则不同，例如声明类型不同的相邻位域不共享单元，所以同一个结构体在不同 ABI 下 `sizeof` 可能不同。但哪些位域构成同一个内存位置由标准规定，与 ABI 无关。
    - 写位域时，编译器生成读出整个单元、掩码、或入新值、写回的指令序列。C++11 的内存模型要求这次读-改-写不越过当前内存位置的边界：在 ¶5 的例子里写 `b` 时，读写的范围不能包含 `a` 或 `d`。
    - 普通的 `char` 成员用单字节的存储指令写入，天然满足 ¶3。在没有单字节存储指令的老式硬件上，满足这个要求的代价很高。

!!! history "历史与演进"
    C++98/03 只规定了字节和每个字节有唯一地址，没有内存位置的概念，因为语言本身不知道线程的存在，编译器可以把对 `char a` 的写合并成一次更宽的读-改-写。C++11 引入多线程内存模型（[[intro.multithread]]）时加入了内存位置和本节的位域规则，C11 采用了几乎相同的定义。

## 常见误解

!!! pitfall "类对象是一个内存位置"
    `struct P { int x; int y; };` 里 `p.x` 和 `p.y` 是两个内存位置，两个线程分别写它们没有数据竞争。但两个线程同时给整个 `p` 赋值（`p = P{...}`），访问的是相同的内存位置，是数据竞争。

!!! pitfall "`std::vector<bool>` 的元素是独立的内存位置"
    `std::vector<bool>` 按位压缩存储，它的元素不是对象。同时修改不同元素是否安全，由库的数据竞争条款（[[container.requirements]]）规定，而不是由本节规定；实际上不同元素往往在同一个字里，不能同时修改。

## 思考题

!!! question "思考题 1"
    下面的结构体中，哪些成员可以由两个线程不加同步地同时修改？

    ```cpp
    struct T {
        int  a : 4;
        int    : 4;
        int  b : 4;
        char c;
        int  d : 4;
        int    : 0;
        int  e : 4;
    };
    ```

<details markdown="1">
<summary>答案</summary>

内存位置的划分是：`a`、无名的 4 位位域和 `b` 是一个（无名位域宽度不为零，不起隔断作用）；`c` 是一个；`d` 是一个（前面有 `c` 隔断，后面有 `: 0` 隔断）；`e` 是一个。所以 `a` 和 `b` 不能同时修改，分属不同位置的任意两个成员（如 `a` 与 `c`、`b` 与 `d`、`d` 与 `e`）都可以。
</details>

!!! question "思考题 2"
    `CHAR_BIT` 可以是 7 吗？可以是 9 吗？

<details markdown="1">
<summary>答案</summary>

不能是 7：¶1 要求字节能放下 UTF-8 的 8 位码元，所以至少 8 位（C 标准也要求 `CHAR_BIT >= 8`）。可以是 9：位数是实现定义的，标准只给了下限。
</details>
