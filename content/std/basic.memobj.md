---
title: 内存与对象
summary: 6.8 节的导读：存储、存储期、对象、生命周期这四个概念的区别，以及七个子条款各自回答什么问题。
status: done
related: intro.memory, intro.object, basic.life, basic.stc, class.temporary
tags: 对象模型, 生命周期, 存储期
updated: 2026-10-19
---

!!! tldr
    - 存储、存储期、对象、生命周期是四个不同的概念：有字节不等于有对象，对象不在生命周期内时存储可能还在。
    - 对象只能由少数几种构造创建：定义、`new`、隐式创建对象的操作、切换联合体成员、临时对象。`reinterpret_cast` 不创建对象。
    - 判断一次访问是否合法，要问三个问题：那里有对象吗？它在生命周期内吗？手里的指针或引用指向它吗？
    - 6.8 节本身没有规范性段落，规则分布在七个子条款里。

## 四个概念

```cpp run title="four-concepts.cpp" ok
#include <new>
#include <cstdlib>
#include <string>

int main() {
    void* raw = std::malloc(sizeof(std::string));    // 获得存储
    // 此刻有存储，但没有 std::string 对象
    auto* s = ::new (raw) std::string("hello");      // 创建对象；构造完成，生命周期开始
    s->~basic_string();                              // 析构开始，生命周期结束；存储还在
    std::free(raw);                                  // 释放存储
}
```

这几行代码里先后出现了四样东西：

| 概念 | 是什么 | 由什么决定 | 定义在 |
|---|---|---|---|
| 存储（storage） | 一段连续的、有地址的字节 | 变量定义、分配函数、实现内部的分配 | [[intro.memory]] |
| 存储期（storage duration） | 存储至少存在多久：静态、线程、自动、动态四种 | 创建对象所用的语法构造 | [[basic.stc]] |
| 对象（object） | 占据一段存储、有类型的实体，可能有名字 | 定义、`new`、隐式创建、联合体成员切换、临时对象 | [[intro.object]] |
| 生命周期（lifetime） | 对象可以按它的类型正常使用的那段运行时间 | 初始化完成时开始；析构开始，或存储被释放、被复用时结束 | [[basic.life]] |

存储可以先于对象存在（`malloc` 之后、构造之前），也可以比对象存在得更久（析构之后、`free` 之前）。在这两段时间里，指针和引用只能有限地使用（[[basic.life#7]]、[[basic.life#8]]）。

同一块存储上可以先后创建多个对象。旧对象的指针、引用和名字能否自动指向新对象，由透明可替换规则决定（[[basic.life#9]]），不能时要用 `std::launder`。

`unsigned char` 或 `std::byte` 数组可以为在其中创建的对象**提供存储**（[[intro.object#3]]），这是手写缓冲区、`std::optional` 一类实现的基础。

一部分简单的类型（隐式生存期类型）不需要显式构造：`malloc`、`memcpy` 等操作会在需要时让这类对象出现（[[intro.object#13]]）。`std::string` 不在其中，所以上例必须用 placement new。

## 七个子条款

| 子条款 | 回答的问题 |
|---|---|
| [[intro.memory]] 内存模型 | 字节是什么；内存位置是什么，为什么它是数据竞争的最小单位；哪些位域共享内存位置 |
| [[intro.object]] 对象模型 | 哪些构造会创建对象；子对象、完整对象、提供存储；对象地址何时可以相同；隐式对象创建 |
| [[basic.align]] 对齐 | 对象可以放在哪些地址上；基本对齐与扩展对齐；over-aligned 类型怎样分配 |
| [[basic.life]] 生命周期 | 生命周期何时开始、何时结束；生命周期之外的指针能做什么；透明替换与 `std::launder` |
| [[basic.indet]] 不确定值与错误值 | 读一个未初始化的对象会怎样；C++26 中自动变量读到的是错误值 |
| [[basic.stc]] 存储期 | 四种存储期；全局分配函数和释放函数必须满足的约束 |
| [[class.temporary]] 临时对象 | 临时对象何时出现、何时销毁；引用绑定延长生命周期的规则和例外 |

[[intro.object]] 和 [[basic.life]] 是核心，前者讲对象从哪里来，后者讲对象什么时候能用，最好连着读。

几个紧密相关、但不在 6.8 节里的条款：

- [[basic.types]]：对象表示与值表示、平凡可复制类型、隐式生存期类型。
- [[basic.lval]]：通过别的类型的 glvalue 访问对象的限制，即严格别名规则。
- [[basic.compound]]：指针值的几种状态，指针可互转。
- [[expr.new]]、[[expr.delete]]：动态对象的创建与销毁。
- [[class.union]]：联合体活跃成员的切换。
- [[intro.races]]：以内存位置为单位定义的数据竞争。
