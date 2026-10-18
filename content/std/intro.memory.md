---
title: 内存模型
summary: 字节是基本存储单位，每个字节有唯一地址；内存位置是标量对象或一串相邻非零宽位域——它是数据竞争的最小粒度
status: done
related: intro.races, intro.object, basic.types, class.bit
tags: 内存模型, 位域, 并发
updated: 2026-10-17
---

这一小节只有五段，却给整个标准打下了两块地基：

1. **字节**（byte）——存储的最小可寻址单位。所有"地址""对象表示""`sizeof`"最终都以字节计。
2. **内存位置**（memory location）——并发语义的最小单位。[[intro.races]] 中"数据竞争"、"冲突"的定义全部是以内存位置为单位的。

C++11 之前的标准没有线程，也就没有"内存位置"这个概念；编译器可以随意把对 `char a` 的写合并成一次 4 字节或 8 字节的读-改-写。C++11 引入多线程内存模型时，必须精确说清"哪些东西可以被两个线程同时改而互不干扰"——答案就是本节的 ¶3。

## 字节（¶1）

¶1 规定了字节的三个性质：

- **至少足够大**：能容纳基本字面量字符集（basic literal character set，见 [[lex.charset]]）里任意字符的普通字面量编码，也能容纳 UTF-8 的 8 位码元。后一条事实上强制了一个字节**至少 8 位**。
- **由连续的位组成**，位数是**实现定义**的（implementation-defined），即 `<climits>` 里的 `CHAR_BIT`。主流平台都是 8；某些 DSP 上 `CHAR_BIT` 是 16 或 32。
- 程序可用的内存由**一段或多段**连续字节组成，**每个字节有唯一地址**。

!!! std
    The memory available to a C++ program consists of one or more sequences of contiguous bytes. Every byte has a unique address.

    程序可用的内存是一段或多段连续字节，每个字节都有唯一的地址。

"一段或多段"是有意的：标准不要求整个地址空间是一个平坦数组。这正是为什么比较两个**无关**对象的指针 `p < q` 在 [[expr.rel]] 中得到的是未指定结果（而不是"按地址数值比较"），以及为什么 [[expr.add]] 只允许在同一个数组内做指针算术——分段内存模型（如老式 x86 实模式的 far 指针）下，跨段的指针比较没有意义。

"每个字节有唯一地址"则是对象地址唯一性规则（[[intro.object#10]]）的基础：既然字节有唯一地址，那么"两个对象地址不同"就等价于"它们的首字节不同"。

!!! note "字节 ≠ `char`，但两者大小相同"
    `sizeof(char)`、`sizeof(signed char)`、`sizeof(unsigned char)` 都是 1（[[expr.sizeof]]）——它们恰好占一个字节。`std::byte` 也是一个字节。所谓"字节"是存储单位，`char` 是类型；标准用"窄字符类型"和 `std::byte` 来访问字节（见 [[basic.lval]] 中的别名规则）。

¶2 是一个注，指向 [[basic.types.general]]：对象表示（object representation）是对象占据的 N 个 `unsigned char`，值表示（value representation）是其中参与表示值的那些位。

## 内存位置（¶3）

!!! std
    A *memory location* is the storage occupied by the object representation of either an object of scalar type that is not a bit-field or a maximal sequence of adjacent bit-fields all having nonzero width.

    内存位置是：一个非位域标量对象的对象表示所占的存储；或者一串**极大的**、相邻的、宽度都不为零的位域所占的存储。

拆开来读：

- **非位域的标量对象**（算术类型、枚举、指针、成员指针、`std::nullptr_t`）各自是一个内存位置。注意是**标量**——类对象、数组不是内存位置，它们由若干内存位置组成。
- **位域**不单独成为内存位置。相邻的非零宽位域合在一起，取"极大"序列（maximal sequence：能往两边延伸就延伸，直到碰到非位域成员、零宽位域或结构边界）构成**一个**内存位置。

为什么位域要合并？因为硬件无法只写 3 个位：要改一个位域，编译器必须读出包含它的整个存储单元，改掉那几位，再写回去。如果两个线程分别改同一个存储单元里的两个位域，这次读-改-写就会互相覆盖。标准的选择是：**承认这件事**，把这一串位域定义为同一个内存位置，于是同时修改它们就是数据竞争（UB），程序员需要自己加锁。

反过来，标准对实现施加了约束：**分开的内存位置必须能被独立访问**。¶3 最后一句：

!!! std
    Two or more threads of execution can access separate memory locations without interfering with each other.

    两个或多个执行线程可以访问各自不同的内存位置而互不干扰。

这是对**编译器**的硬性要求：它不能为了写 `s.a` 而生成一个顺带覆盖 `s.b` 的宽写入（除非能证明没有别的线程能观察到）。

```cpp run title="separate-locations.cpp" ok
#include <thread>

struct S {
    char a;
    char b;     // a 与 b 是两个内存位置
};

S s;

int main() {
    std::thread t1([] { for (int i = 0; i < 100000; ++i) s.a = char(i); });
    std::thread t2([] { for (int i = 0; i < 100000; ++i) s.b = char(i); });
    t1.join();
    t2.join();
}   // 没有数据竞争：两个线程写的是不同的内存位置
```

¶3 中的注 3 提醒：引用、虚函数等语言机制可能还会用到实现管理、程序不可访问的额外内存位置（例如 vptr）。这些位置的并发安全由实现自己负责。

## 哪些位域共享内存位置（¶4–¶5）

¶4 是注，但它把 ¶3 的定义翻译成了四条可操作的规则。两个位域落在**不同**内存位置，当且仅当它们之间被"隔断"了：

| 情形 | 是否同一内存位置 | 原因 |
|---|---|---|
| 位域与相邻的**非位域**成员 | 否 | 非位域成员本身是一个标量对象，打断了位域序列 |
| 两个位域之间夹着**零宽位域** `:0` | 否 | 序列要求"all having nonzero width" |
| 两个位域之间夹着**非位域**成员 | 否 | 同上，序列被打断 |
| 一个在**嵌套结构体**里，一个不在 | 否 | 嵌套结构体是另一个对象，其中的位域与外层的位域不"相邻" |
| 两个位域之间**全是**非零宽位域 | **是** | 构成同一个极大序列 |

¶5 的标准例子，加上我们的标注：

```cpp run title="bitfield-locations.cpp" ok
struct S {
    char a;          // 内存位置 #1
    int b : 5,       // ┐
        c : 11,      // ┘ 内存位置 #2（b、c 相邻且都非零宽）
          : 0,       // 零宽位域：断开序列，并让下一个位域从新的分配单元开始
        d : 8;       // 内存位置 #3
    struct {
        int ee : 8;  // 内存位置 #4（在嵌套结构体中）
    } e;
};

int main() {
    S s{};
    s.a = 1; s.b = 2; s.c = 3; s.d = 4; s.e.ee = 5;
}
```

结论：`a`、`d`、`e.ee` 可以与任何其他成员并发修改；`b` 和 `c` **不能**彼此并发修改，但 `b` 可以和 `a` 并发修改。

!!! warning "未命名的非零宽位域也算"
    规则说的是"adjacent bit-fields all having nonzero width"，并没有要求有名字。`int x : 3; int : 5; int y : 4;` 中的 `x`、无名位域、`y` 构成**同一个**内存位置，`x` 与 `y` 不能并发修改。只有**零宽**的无名位域才起隔断作用。

```cpp run title="bitfield-race.cpp" ub
#include <thread>

struct Flags {
    unsigned ready : 1;
    unsigned error : 1;   // 与 ready 处于同一内存位置
};

Flags f{};

int main() {
    std::thread t1([] { f.ready = 1; });
    std::thread t2([] { f.error = 1; });  // UB: 与 t1 冲突且无同步——数据竞争
    t1.join();
    t2.join();
}
```

修复方法三选一：加互斥锁；在两个位域之间插入 `unsigned : 0;`；或者干脆不用位域（改用 `std::atomic<unsigned>` 并用位运算）。

```cpp run title="bitfield-fixed.cpp" ok
#include <thread>

struct Flags {
    unsigned ready : 1;
    unsigned       : 0;   // 零宽位域：断开内存位置
    unsigned error : 1;
};

Flags f{};

int main() {
    std::thread t1([] { f.ready = 1; });
    std::thread t2([] { f.error = 1; });  // OK: 不同内存位置
    t1.join();
    t2.join();
}
```

## 实现视角

!!! impl "编译器为位域生成什么代码"
    - 在 Itanium C++ ABI（Linux/macOS 上的 GCC、Clang）下，位域的分配单元由声明类型决定（`int b:5` 放在一个 `int` 大小的单元里），相邻位域在单元内连续打包；`:0` 使下一个位域对齐到下一个分配单元。MSVC 的规则不同（例如声明类型不同的相邻位域不会共享单元），所以**同一个结构体在不同 ABI 下的 `sizeof` 可能不同**——但"哪些位域构成同一内存位置"是标准规定的，与 ABI 无关。
    - 写位域时，编译器通常生成"载入整个单元 → 掩码 → 或入新值 → 写回"的序列。C++11 内存模型要求这个读-改-写**不能越过**当前内存位置的边界：比如 ¶5 例子里写 `b` 时，载入/写回的范围不能包含 `a` 或 `d`。历史上曾有编译器在某些平台上为了写一个位域生成了覆盖相邻非位域成员的 64 位读-改-写，正是这类 bug 推动了对"内存位置"的严格定义。
    - 普通的 `char` 成员一般直接用字节宽度的 store 指令写入，天然满足 ¶3。在不支持字节 store 的古老硬件（早期 Alpha）上，实现要满足 C++11 的这一要求代价很高。

!!! history "历史与演进"
    - **C++98/03**：只有"字节"和"每个字节有唯一地址"，没有内存位置的概念，因为语言本身不知道线程的存在。
    - **C++11**：随多线程内存模型（[[intro.multithread]]）引入"内存位置"，并给出本节的位域规则和例子。C11 采用了几乎相同的定义。
    - 之后本节基本未变；措辞上把"基本执行字符集"改为与 C++23 起重新整理的字符集术语（[[lex.charset]]）一致。

## 陷阱

!!! pitfall "以为类对象是一个内存位置"
    `struct P { int x; int y; };` 中的 `p.x` 与 `p.y` 是两个内存位置；两个线程分别写 `p.x` 与 `p.y` 没有数据竞争。但两个线程同时对**整个** `p` 赋值（`p = P{...}`）会访问相同的内存位置，是数据竞争。

!!! pitfall "以为 `std::vector<bool>` 的元素是独立内存位置"
    `std::vector<bool>` 是按位压缩的特化，它的"元素"根本不是对象，并发修改不同元素的规则由库（[[container.requirements]] 中的数据竞争条款）规定，而不是由本节规定；实践上不同元素可能共享同一个字，因此不能并发修改。

## 思考题

!!! question "思考题 1"
    下面的结构体中，哪些成员可以被两个线程同时（无同步地）修改？

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

内存位置的划分：`{a, 无名4位, b}` 是一个（无名位域非零宽，不起隔断作用）；`c` 是一个；`d` 是一个（`c` 在前把序列断开，`:0` 在后断开）；`e` 是一个。所以 `a` 与 `b` 不能并发修改；其余任意两个分属不同位置的成员（如 `a` 与 `c`、`b` 与 `d`、`d` 与 `e`）都可以。
</details>

!!! question "思考题 2"
    `CHAR_BIT` 可以是 7 吗？可以是 9 吗？

<details markdown="1">
<summary>答案</summary>

不能是 7：¶1 要求字节能容纳 UTF-8 的八位码元，因此至少 8 位（C 标准也要求 `CHAR_BIT >= 8`）。可以是 9：位数是实现定义的，标准只给下限。实践中 9 位字节的机器早已绝迹，但标准文本仍然允许。
</details>

## 小结

| 概念 | 要点 |
|---|---|
| 字节 | 最小可寻址单位；位数 = `CHAR_BIT`（实现定义，≥ 8）；每个字节有唯一地址 |
| 内存 | 一段或多段连续字节——因此无关对象的指针比较不保证有意义 |
| 内存位置 | 非位域标量对象，或一串极大的相邻非零宽位域 |
| 并发 | 不同内存位置可以被不同线程无干扰地访问；同一内存位置的冲突访问需要同步，否则是数据竞争（[[intro.races]]） |
| 位域隔断 | 非位域成员、零宽位域、嵌套结构体边界 |
