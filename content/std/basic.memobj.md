---
title: 内存与对象
summary: 6.8 节导读——字节与内存位置、对象模型、对齐、生命周期、不确定值/错误值、存储期、临时对象，七个子条款如何拼成 C++ 的对象模型
status: done
related: intro.memory, intro.object, basic.life, basic.stc, class.temporary
tags: 对象模型, 生命周期, 存储期
updated: 2026-10-17
---

[[basic.memobj]] 本身没有规范性段落，它只是一个容器，把七个子条款装在一起。但这七个子条款合起来就是整本标准里最"底层"的一层抽象：**C++ 抽象机到底操作的是什么东西**。几乎所有 language lawyer 的争论——"这段 `reinterpret_cast` 是不是 UB"、"`placement new` 之后旧指针还能不能用"、"`malloc` 来的内存能不能直接当 `struct` 用"、"返回 `const T&` 会不会悬垂"——最后都要回到这里来裁决。

## 一张图：四个经常被混为一谈的概念

读这一节最大的障碍是把下面四个概念混在一起。它们是**正交**的：

| 概念 | 是什么 | 由谁决定 | 在哪里定义 |
|---|---|---|---|
| **存储**（storage） | 一段连续的字节，有地址 | 分配（变量定义、分配函数、实现内部） | [[intro.memory]] |
| **存储期**（storage duration） | 存储"至少"能活多久——静态、线程、自动、动态四类 | 创建对象所用的语法构造 | [[basic.stc]] |
| **对象**（object） | 占据一段存储、有类型、（可能）有名字和值的实体 | 定义、*new-expression*、隐式创建操作、切换联合体活跃成员、临时对象 | [[intro.object]] |
| **生命周期**（lifetime） | 对象"作为该类型的对象"可被正常使用的运行期区间 | 初始化完成时开始；析构开始 / 存储被释放或复用时结束 | [[basic.life]] |

用一个比喻把它们串起来：**存储是地皮，存储期是地契的年限，对象是盖在地皮上的房子，生命周期是房子可以住人的那段时间**。

- 地皮可以先于房子存在（`malloc` 之后、构造之前），也可以比房子活得长（析构之后、`free` 之前）——这两段"有地无房"的时间正是 [[basic.life#7]]、[[basic.life#8]] 规定"指针只能有限使用"的地方。
- 同一块地皮上可以先后盖好几栋房子（placement new 复用存储），旧房子的"门牌号"（指针、引用、名字）能不能自动指向新房子，由 [[basic.life#9|透明可替换]] 规则决定，否则要用 `std::launder`。
- 房子里可以有房间（子对象），也可以在一块"空地仓库"（`unsigned char`/`std::byte` 数组）上盖别的房子——这叫**提供存储**（provides storage），见 [[intro.object#3]]。
- 有一类特别简单的房子（隐式生存期类型）甚至不需要动工：标准允许某些操作（`malloc`、`memcpy`……）"凭空"让它们存在，只要这样做能让程序有定义行为，见 [[intro.object#13]]。

```cpp run title="four-concepts.cpp" ok
#include <new>
#include <cstdlib>
#include <string>

int main() {
    void* raw = std::malloc(sizeof(std::string));    // 获得存储：动态存储期的一块字节
    // 此刻：有存储，但没有 std::string 对象（string 不是隐式生存期类型）
    auto* s = ::new (raw) std::string("hello");      // 创建对象，构造完成时生命周期开始
    s->~basic_string();                              // 析构开始 → 生命周期结束；存储仍在
    std::free(raw);                                  // 释放存储 → 存储期结束
}
```

## 七个子条款各管什么

| 子条款 | 中文 | 核心问题 |
|---|---|---|
| [[intro.memory]] | 内存模型 | 字节、地址、**内存位置**（memory location）——数据竞争的最小单位；相邻位域何时共享内存位置 |
| [[intro.object]] | 对象模型 | 什么构造会创建对象；子对象、完整对象、最派生对象；提供存储、嵌套于；地址唯一性与零大小子对象；**隐式对象创建** |
| [[basic.align]] | 对齐 | 对齐要求、基本/扩展对齐、`alignof`、over-aligned 类型 |
| [[basic.life]] | 生命周期 | 生命周期何时开始/结束；生命周期之外的指针和 glvalue 能做什么；透明替换与 `std::launder` |
| [[basic.indet]] | 不确定值与错误值 | 未初始化读取：动态存储期仍是 UB，自动存储期在 C++26 变为**错误行为**（erroneous behavior） |
| [[basic.stc]] | 存储期 | 四种存储期；全局分配/释放函数的约束 |
| [[class.temporary]] | 临时对象 | 临时对象何时物化、何时销毁；引用绑定的生命周期延长及其例外 |

## 推荐阅读顺序

1. 先读 [[intro.memory]]（短）建立"字节—内存位置"的底层图景。
2. 再读 [[intro.object]] 和 [[basic.life]]，这两页是本节的核心，最好一起读：前者回答"对象从哪里来"，后者回答"对象什么时候能用"。
3. [[basic.stc]] 和 [[basic.align]] 是对"存储"一侧的补充。
4. [[basic.indet]] 回答"对象有了、但没初始化时值是什么"。
5. [[class.temporary]] 是一个专题：C++17 起 prvalue 不再是对象，临时对象只在**物化**时才出现。

与本节紧密相关、但不在本节内的条款：

- [[basic.types]]：对象表示与值表示、平凡可复制类型、隐式生存期类型的定义。
- [[basic.lval]]：值类别，以及通过别的类型的 glvalue 访问对象的限制（严格别名规则）。
- [[basic.compound]]：指针值的四种状态（指向对象、尾后、空、无效），指针可互转（pointer-interconvertible）。
- [[expr.new]]、[[expr.delete]]：动态对象的创建与销毁。
- [[class.union]]：联合体活跃成员的切换。
- [[class.cdtor]]：构造和析构期间的对象。
- [[intro.races]]：数据竞争以"内存位置"为单位定义。

!!! summary "小结"
    - **存储 ≠ 对象**：有字节不代表有对象；C++ 的对象是抽象机里的实体，不是"内存里恰好长成那样的字节"。
    - **存储期 ≠ 生命周期**：存储期描述存储，生命周期描述对象；后者总是包含在前者之内。
    - 读写一个对象之前，问三个问题：对象**存在**吗（[[intro.object]]）？在**生命周期内**吗（[[basic.life]]）？我的指针/glvalue **指向它**吗（[[basic.life#10]]、[[basic.compound]]）？
