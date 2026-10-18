---
title: 显式生命周期管理
summary: start_lifetime_as / start_lifetime_as_array 在不触碰存储的前提下把已有字节"认作"对象（值按 bit_cast 规则得到）；C++26 的 start_lifetime 让联合体的聚合成员在不初始化的情况下成为活跃成员
status: done
related: intro.object, basic.life, basic.types, class.union, bit.cast, basic.compound, ptr.launder, c.malloc, memory
tags: 标准库, 对象模型, 隐式对象创建, start_lifetime_as, 联合体
papers: P2590R2, P2679R2, P3726R2
updated: 2026-10-18
---

[obj.lifetime] 只有三组函数，但每一条都是用核心语言对象模型的术语写成的，必须对照 [[intro.object]]（对象如何被创建、隐式对象创建）和 [[basic.life]]（生命周期何时开始）来读。

| 函数 | 版本 | 一句话 |
|---|---|---|
| `start_lifetime_as<T>(p)` | C++23 | 在 `p` 处隐式创建一个 `T`，**字节不变**，值等价于把原字节 `bit_cast` 成 `T` |
| `start_lifetime_as_array<T>(p, n)` | C++23 | 同上，创建 `T[n]` |
| `start_lifetime(r)` | C++26 | 让 `r` 所指的隐式生存期聚合对象的生命周期开始，**不做任何初始化**；用于让联合体成员变为活跃 |

## 问题背景：字节已经在那里了

隐式对象创建（[[intro.object]] ¶13–¶16，[[g:implicitly-create-objects]]）解决了 `malloc` + 直接使用的合法性问题，但触发它的操作是有限的：`malloc`/`operator new` 等分配函数、`memcpy`/`memmove`、开始 `unsigned char`/`std::byte` 数组的生命周期，等等。

现实中有大量场景是：**字节已经由外部写好**——从网络 `recv` 进来、`mmap` 一个文件、DMA 控制器写入共享内存——我们想把这段字节当作一个 `struct Header` 来读。直接 `reinterpret_cast<Header*>(buf)->length` 是 {{ub}}：`buf` 里没有 `Header` 对象，访问违反了 [[basic.lval]] 的类型别名规则（详见 [[intro.object]] "字节缓冲区 + reinterpret_cast 的陷阱"一节）。

C++20 下的可移植解法是"把字节自己拷给自己"：

```cpp title="memmove-trick.cpp" ok
#include <cstdint>
#include <cstring>
#include <cstdio>

struct Header { std::uint32_t magic; std::uint32_t length; };

// memmove 在拷贝之前隐式创建对象，并返回指向"合适的已创建对象"的指针（[cstring.syn]/3）
Header* as_header(void* p) {
    return static_cast<Header*>(std::memmove(p, p, sizeof(Header)));
}

int main() {
    alignas(Header) unsigned char packet[16] = {0x78, 0x56, 0x34, 0x12, 8, 0, 0, 0};
    Header* h = as_header(packet);
    std::printf("%x %u\n", (unsigned)h->magic, (unsigned)h->length);   // 小端机：12345678 8
}
```

注意这里**不需要** `std::launder`：[[cstring.syn]] ¶3 规定 `memcpy`/`memmove` 返回指向合适的已创建对象的指针（若有），返回值本身就是指向新 `Header` 的指针。（如果不用返回值而继续用 `packet` 去 `reinterpret_cast`，那才需要 `launder`。）

这个技巧可行，但意图晦涩，而且"拷贝"在语义上并不存在——编译器通常能把它优化掉，但也可能不能。C++23 的 `start_lifetime_as`（[[P2590R2]]）给了它一个名字。

## `start_lifetime_as`（¶3–¶6）{{c++23}}

```cpp
template<class T> T* start_lifetime_as(void* p) noexcept;
// 以及 const / volatile / const volatile 三个重载
```

### ¶3 *Mandates*

`T` 是**隐式生存期类型**（[[g:implicit-lifetime-type]]）且不是不完整类型。隐式生存期类型包括标量、隐式生存期类（[[g:implicit-lifetime-class]]，例如聚合或有平凡构造与析构的类）及其数组。`std::string` 不是，所以 `start_lifetime_as<std::string>` 是 {{ill-formed}}——你不可能"把字节认作一个 string"，它的不变式需要构造函数建立。"不是不完整类型"这一半同样来自 [[P2679R2]]：未知边界数组 `int[]` 是不完整类型，于是误用 `start_lifetime_as<int[]>(buf)`（本应调用 `_array` 版本）从 UB 变成了 {{ill-formed}}。

### ¶4 *Preconditions*

`[p, (char*)p + sizeof(T))` 是一段**已分配存储**，是**可经由 `p` 到达**的存储（[[g:reachable-through]]，[[basic.compound]]）的子集，并且对 `T` 适当对齐。三条都是 UB 级前置条件：

- "已分配存储"排除了指向寄存器或无存储的东西；
- "可经由 `p` 到达"禁止越过 `p` 所指对象的边界。例如 `p` 指向某个 `struct` 的 `int` 成员，不能用它去覆盖相邻成员；
- 对齐要求不会被检查。

### ¶5 *Effects*：值从哪里来

¶5 是本节的核心：

!!! std "[obj.lifetime]/5"
    Implicitly creates objects within the denoted region consisting of an object *a* of type T whose address is p, and objects nested within *a* … The object representation of *a* is the contents of the storage prior to the call to start_lifetime_as.

    在该区域内隐式创建一个地址为 `p` 的 `T` 类型对象 *a* 以及嵌套于其中的对象……*a* 的对象表示就是调用之前存储里的内容。

细节：

- 对每个创建出的**可平凡复制**类型 `U` 的对象 *o*，其值的确定方式与 `bit_cast<U>(E)` 相同（[[bit.cast]]），其中 `E` 是指代 *o* 的 `U` 左值——"**只是存储不被访问**"。这句话的分量在于：它借用了 `bit_cast` 关于填充位、不确定位、错误值的全部规则，例如原字节对应于不确定值时，结果相应地不确定。
- 其他（非可平凡复制的隐式生存期类型）对象的值**未指明**，注 2 补充：可能是不确定值。
- 和所有隐式对象创建一样，"创建哪些嵌套对象"按"使程序有定义行为"的原则选择（[[intro.object]] ¶13）。

"存储不被访问"意味着 `start_lifetime_as` 本身不读不写内存——它是纯粹的编译期"类型重新解释"指令，对优化器而言是一道屏障：此前对这段存储的类型假设全部作废。

### ¶6 *Returns*

返回指向 *a* 的指针。与 `memmove` 技巧一样，**用返回值访问**；继续用原来的 `unsigned char*` 去 `reinterpret_cast` 仍需 `launder`。

### `const` 与 `volatile` 重载

`const void*` 重载返回 `const T*`。这对只读映射（`PROT_READ` 的 `mmap`）很重要：`memmove` 技巧需要**写**存储（哪怕写的是原值），对只读页会段错误；`start_lifetime_as` 不访问存储，所以可以用于只读内存。`volatile` 重载则服务于内存映射 I/O。

```cpp title="start-lifetime-as.cpp" ok
#include <memory>
#include <cstddef>
#include <cstdint>

struct Header { std::uint32_t magic; std::uint32_t length; };

const Header* parse(const std::byte* packet) {
    // 前置条件：packet 处有 sizeof(Header) 字节已分配存储，且按 Header 对齐
    return std::start_lifetime_as<Header>(packet);   // 不拷贝、不访问；字节即对象表示
}
```

（截至写作时，本机 Clang 23 + libc++ 尚未提供 `start_lifetime_as`（`<version>` 中没有 `__cpp_lib_start_lifetime_as`），此例未在本地编译验证。）

## `start_lifetime_as_array`（¶7–¶10）

```cpp
template<class T> T* start_lifetime_as_array(void* p, size_t n) noexcept;
```

- ¶7 *Mandates*：`T` 是完整类型。（不要求 `T` 是隐式生存期类型——但 ¶9 转发到 `start_lifetime_as<T[n]>`，而**数组类型总是隐式生存期类型**，所以元素类型无所谓。元素的值按 ¶5：可平凡复制的元素用 `bit_cast` 规则，其他元素未指明。）
- ¶8 *Preconditions*：`p` 对 `T` 数组适当对齐**或为空**；`n <= size_t(-1) / sizeof(T)`（不溢出）；若 `n > 0`，`[p, p + n*sizeof(T))` 是可经由 `p` 到达的已分配存储。
- ¶9：`n > 0` 时等价于 `start_lifetime_as<U>(p)`，`U` 是 "`n` 个 `T` 的数组"；否则无效果。
- ¶10：返回指向所创建数组首元素的指针（若有），否则返回一个与 `p` 比较相等的指针。

`n == 0` 与空指针的处理由 [[P2679R2]] 在 C++23 发布前修补（解决 NB 意见 CA-086）：最初的措辞下传 `0` 是 UB，泛型代码必须对空范围特判；修补后 `n == 0` 合法，且此时 `p` 可以为空。`n == 0` 时返回的指针只能像尾后指针那样使用，不能解引用。

!!! lawyer "为什么数组版本需要单独的函数？"
    `start_lifetime_as<T[n]>` 要求 `n` 是常量表达式；运行期长度只能用 `start_lifetime_as_array`。它创建的是**一个数组对象**，因此返回的 `T*` 指向数组元素，可以合法地做指针算术遍历 `[0, n]`（[[expr.add]] 要求指针算术在同一数组对象内）。如果循环调用 `n` 次 `start_lifetime_as<T>`，得到的是 `n` 个**互不相关**的完整对象，在它们之间做指针算术反而是 UB。

## `start_lifetime`（¶1–¶2）{{c++26}}

```cpp
template<class T> constexpr void start_lifetime(T& r) noexcept;
```

这是 C++26 随 [[P3726R2]] 加入的，与上面两个函数的用途完全不同：

- ¶1 *Mandates*：`T` 是完整的、**隐式生存期的聚合**类型。
- ¶2 *Effects*：若 `r` 所指对象已在生命周期内，无效果；否则**开始它的生命周期**。注 1：不执行任何初始化，也不开始任何子对象的生命周期；若 `r` 指代联合体 `U` 的成员，它成为 `U` 的活跃成员（[[class.union]]）。

它是 `constexpr` 的，主要服务于常量求值中的"手动存储管理"。典型场景是 `inplace_vector` 一类容器：

```cpp title="start-lifetime-union.cpp" ok
#include <memory>
#include <cstddef>

template<class T, std::size_t N>
struct Storage {
    union { T elems[N]; };          // 不想在构造时初始化任何元素
    constexpr Storage() {
        std::start_lifetime(elems); // elems 成为活跃成员；数组的生命周期开始，元素没有
    }
    constexpr ~Storage() {}
};
```

在运行期，"写一个联合体成员即令其活跃"（[[class.union]] 的赋值规则）或隐式对象创建可以做到同样的事；但常量求值器需要**显式地**知道哪个成员活跃、哪些元素存在——访问非活跃成员在常量求值中是硬错误。`start_lifetime` 给出了这样一个显式的、不引发任何初始化的信号；之后再用 `construct_at(&elems[i], ...)` 逐个构造元素。

（本机 libc++ 尚未提供 `std::start_lifetime`，此例未在本地编译验证。）

## 与相关工具的对比

| 工具 | 创建对象？ | 访问存储？ | 结果值 | 典型用途 |
|---|---|---|---|---|
| `reinterpret_cast<T*>(p)` | 否 | — | 无对象可访问，{{ub}} | （错误用法） |
| `std::launder(p)` | 否 | 否 | 要求 `p` 处**已有** `T` 对象 | 透明替换失败后取得新对象的指针（[[ptr.launder]]） |
| `memmove(p, p, n)` | 是 | 读+写 | 原字节 | C++20 可移植替代 |
| `start_lifetime_as<T>(p)` | 是 | 否 | 原字节（`bit_cast` 语义） | 网络包、`mmap`、只读内存 |
| `start_lifetime(r)` | 是（开始 `r` 的生命周期） | 否 | 无初始化 | 常量求值中的联合体存储 |
| placement new / `construct_at` | 是 | 写 | 初始化的结果 | 一般构造 |

最常见的混淆是 `launder` 与 `start_lifetime_as`：`launder` **从不创建对象**，它只在"对象已经在那里、但你手里的指针值不指向它"时修正指针值；`start_lifetime_as` 才是"让对象出现"。

## 思考题

<details markdown="1">
<summary>1. 对一段由 `recv` 写入的 `unsigned char buf[64]` 调用 `start_lifetime_as<Header>(buf)` 后，`buf[0]` 还能读吗？</summary>

可以，读到的仍是原字节。`unsigned char` 数组为其中隐式创建的对象**提供存储**（[[intro.object]] ¶3），数组本身和它的元素并不因为 `Header` 的出现而结束生命周期；而且通过 `unsigned char` 左值访问任何对象的表示都是允许的（[[basic.lval]] ¶11）。但若之后通过 `Header*` 修改了 `length`，再经 `buf[4]` 读到的是新字节——它们是同一段存储。
</details>

<details markdown="1">
<summary>2. 为什么 `start_lifetime_as` 只接受隐式生存期类型，而不能"顺便"支持任意可平凡复制类型以外的类型？</summary>

因为 `start_lifetime_as` 不运行任何构造函数，它创建对象的机制就是隐式对象创建（¶5 原文是"implicitly creates objects"），而 [[intro.object]] ¶13 只允许隐式创建**隐式生存期类型**的对象。非隐式生存期类型（例如有用户提供构造函数且无平凡合格构造函数的类）的对象必须经由构造函数才能开始生命周期（[[basic.life]] ¶2），否则其不变式无从保证。
</details>

## 小结

- `start_lifetime_as<T>(p)`：隐式创建 `T`，对象表示 = 原字节，值按 `bit_cast` 规则；不访问存储（可用于只读内存）；`T` 必须是隐式生存期类型；用返回值访问。
- `start_lifetime_as_array<T>(p, n)`：运行期长度版本，创建**一个**数组对象；`n == 0` 时允许 `p` 为空。
- `start_lifetime(r)` {{c++26}}：常量求值友好地开始隐式生存期聚合（通常是联合体成员）的生命周期，不初始化任何东西。
- `launder` 不创建对象；`memmove(p, p, n)` 是 C++20 的替代写法，且其返回值无需 `launder`。
