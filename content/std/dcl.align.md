---
title: 对齐说明符
summary: alignas 可用于变量、数据成员和类，不能用于位域、函数形参、异常声明；取最严格的非零对齐；不能比自然对齐更弱；所有声明的对齐必须一致（跨 TU 不一致为 IFNDR）
status: done
papers: N2341, P0035R4
related: basic.align, dcl.attr.grammar, expr.alignof, expr.new, class.mem, intro.object
tags: 属性, 对齐, 布局
updated: 2026-10-17
---

`alignas` 是 C++11 引入的**对齐说明符**（alignment-specifier）。语法上它是一种 *attribute-specifier*（[[dcl.attr.grammar]]），所以出现的位置规则与属性一致；但和标准属性不同，它**确实改变程序语义**——对齐要求影响布局、`sizeof`、`alignof` 和动态分配。

读本页前需要知道对齐值（alignment）、基本对齐与扩展对齐的概念，见 [[basic.align]]：对齐值是 2 的非负整数次幂；不超过 `alignof(std::max_align_t)` 的是**基本对齐**（fundamental alignment），更大的是**扩展对齐**（extended alignment），实现定义是否支持、在哪些上下文中支持。

```text
alignment-specifier:
    alignas ( nofun-type-id ...(opt) )
    alignas ( constant-expression ...(opt) )
```

## 能用在哪里（¶1）

¶1：`alignas` 可以用于：

- **变量**；
- **类的数据成员**；
- **类的声明**（在 *class-head* 或 *elaborated-type-specifier* 中）。

不能用于：**位域**、**函数形参**、**异常声明**（*exception-declaration*，`catch` 的形参）。带省略号的 `alignas` 是**包展开**。

```cpp title="align-where.cpp" error
struct alignas(16) V { int i; };       // OK: 类
alignas(32) int g;                     // OK: 变量
struct M { alignas(8) char c; };       // OK: 数据成员

alignas(double) void f();              // error: 不能用于函数
void h(alignas(8) int p);              // error: 不能用于函数形参
struct BF { alignas(4) int b : 3; };   // error: 不能用于位域
using T = alignas(16) int;             // error: 不能出现在类型别名的类型中
```

为什么函数形参不行？形参的存储由调用约定决定（可能在寄存器中，可能在调用方的栈帧里），被调函数无法单方面要求更高的对齐；异常对象的存储由运行时库分配，同理。位域没有地址，"对齐"无从谈起。需要高对齐的形参，传指针或引用。

`alignas` 也不是类型的一部分：没有"`alignas(16) int` 类型"，`typedef`/`using` 不能携带它。想要一个高对齐的类型，就定义一个带 `alignas` 的类。

```cpp title="align-pack.cpp" ok
template<class... Ts>
struct alignas(Ts...) Storage {    // 包展开：等价于 alignas(T1) alignas(T2) ...
    unsigned char data[16];
};
static_assert(alignof(Storage<char, double, int>) == alignof(double));

int main() {}
```

## 两种形式（¶2–¶3）

¶2：`alignas( constant-expression )`：

- ¶2.1：表达式必须是**整型常量表达式**；
- ¶2.2：值不是对齐值（[[basic.align]]），或者是一个实现在该声明的上下文中不支持的扩展对齐，程序**非良构**。

¶3：`alignas( nofun-type-id )` 等价于 `alignas(alignof( nofun-type-id ))`（[[expr.alignof]]）。（*nofun-type-id* 是不能是函数类型的 *type-id*。）

```cpp title="align-values.cpp" error
alignas(3) int a;              // error: 3 不是 2 的幂
alignas(double) char b[8];     // OK: 等同 alignas(alignof(double))
alignas(1 << 20) char huge;    // 实现定义：扩展对齐，可能不被支持（Clang 在 macOS/Linux 上接受）
```

!!! lawyer "alignas(0)"
    C++11 的原文明确写着：常量表达式求值为 0 时，对齐说明符没有效果。当前草案的 ¶2 里已经没有这句话，¶2.2 只说"不是对齐值则非良构"——而 0 不是 2 的幂，按字面读 `alignas(0)` 应当非良构；但 ¶4 仍然保留着"最严格的**非零**对齐……否则没有效果"的措辞，暗示 0 仍被预期为合法且无效果。Clang 23 接受 `alignas(0) int y;` 且不警告。这是一个措辞上的灰色地带，建议不要依赖它（模板代码中 `alignas(N)` 的 `N` 可能为 0 时尤其要注意）。

## 多个 alignas：取最严格（¶4）

¶4：实体的对齐要求是其所有对齐说明符所指定的**最严格的非零对齐**；如果没有（或全为零），对齐说明符没有效果。

```cpp title="align-strictest.cpp" ok
alignas(4) alignas(16) alignas(8) int z;     // 对齐为 16
struct Pair { alignas(64) int a; alignas(64) int b; };
static_assert(sizeof(Pair) == 128);          // 每个成员独占一条 64 字节缓存行

int main() {}
```

## 不能削弱（¶5）

¶5：一个声明中所有对齐说明符的**合并效果**，不得比"去掉这些对齐说明符时该实体本来需要的对齐"**更弱**。

```cpp title="align-weaken.cpp" error
struct alignas(8) S {};
struct alignas(1) U {
    S s;
};                        // error: U 指定的对齐比去掉 alignas(1) 时更弱（本来需要 8）

alignas(1) int weak;      // error: int 本来需要 4（在常见平台上）
```

`alignas` 只能**加强**对齐，不能**减弱**。要减弱对齐（打包结构体），只能用实现扩展：`#pragma pack`、`[[gnu::packed]]`——这些不在标准之内，访问打包成员可能产生未对齐访问。

¶7 的标准例子给出了一个惯用法：声明一个对齐为 A、能放 N 个 T 的缓冲区：

```cpp
alignas(T) alignas(A) T buffer[N];
```

加上 `alignas(T)` 是为了保证最终对齐不弱于 `alignof(T)`——如果 A 比 `alignof(T)` 小，单独写 `alignas(A)` 会违反 ¶5 而非良构；有了 `alignas(T)`，¶4 的"取最严格"规则会自动选对。

## 所有声明必须一致（¶6）

¶6：

- 实体的**定义性声明**有对齐说明符时，它的任何**非定义性声明**要么指定**等价**的对齐，要么不带对齐说明符；
- 反过来，实体的**任何**声明有对齐说明符时，**每个**定义性声明都必须指定等价的对齐；
- 不同 TU 中的声明对齐说明符不同，**不要求诊断**（IFNDR {{ifndr}}）。

```cpp title="align-redecl.cpp" error
alignas(double) unsigned char c[sizeof(double)];   // 定义：适合存放 double 的字符数组
extern unsigned char c[sizeof(double)];            // OK: 非定义声明可以不写 alignas
alignas(float)
    extern unsigned char c[sizeof(double)];        // error: 与定义的对齐不同
```

```cpp title="tu1.cpp"
struct S { int x; } s, *p = &s;
```

```cpp title="tu2.cpp" ifndr
struct alignas(16) S;     // IFNDR: S 的定义（在 tu1 中）没有这个对齐
extern S* p;
```

规则的方向性很重要：非定义声明**可以省略** `alignas`（使用者不需要知道对齐细节也能声明 `extern`），但只要**有一个**声明写了，**定义**就必须写一致的。原因：对齐影响的是对象的**存储**如何分配，只有定义才分配存储；如果某个 TU 中看到 `alignas(16)` 的声明而假设对象 16 字节对齐（例如生成了对齐的 SIMD 加载指令），而定义却没有给出这个对齐，运行期就会崩溃——而这类跨 TU 的不一致编译器无法检查，于是 IFNDR。

## 与动态分配

`alignas` 声明的类型如果具有扩展对齐（大于 `alignof(std::max_align_t)`：x86-64 Linux 上是 16，arm64 macOS 上是 8），C++17 之前 `new` 并不保证尊重它——`operator new` 只保证基本对齐。C++17（[[P0035R4]]）为此加入了带 `std::align_val_t` 参数的分配函数，`new` 表达式对**新扩展对齐**（new-extended alignment，即超过 `__STDCPP_DEFAULT_NEW_ALIGNMENT__` 的对齐，[[basic.align]]）类型会自动调用它们（[[expr.new]]、[[basic.stc.dynamic.allocation]]）。

```cpp run title="align-new.cpp" ok
#include <cstdint>
#include <cstdio>
#include <cstddef>

struct alignas(64) CacheLine { int v; };
static_assert(sizeof(CacheLine) == 64 && alignof(CacheLine) == 64);

int main() {
    auto* p = new CacheLine[3];                       // C++17：调用 operator new[](size_t, align_val_t)
    std::printf("misalign=%d max_align=%zu\n",
                static_cast<int>(reinterpret_cast<std::uintptr_t>(p) % 64),
                alignof(std::max_align_t));
    delete[] p;
}
// 输出：misalign=0；max_align 在 arm64 macOS 上是 8，在 x86-64 Linux 上是 16
```

## 实现视角

!!! impl "实现细节"
    - GCC/Clang 把 `alignas` 映射到与 `__attribute__((aligned(N)))` 相同的内部机制，但标准语法禁止削弱对齐，而 GNU 的 `aligned` 属性在某些位置（如 typedef 上）可以用于**降低**对齐——那是扩展。
    - 栈上的超对齐变量（如 `alignas(64)` 的局部数组）要求编译器在函数序言中**重新对齐栈指针**（x86-64 上会看到 `and rsp, -64` 之类的指令），并可能需要帧指针。
    - 静态存储期对象的对齐受目标文件格式与加载器限制，自动变量的对齐受栈重新对齐能力限制，不同平台的上限不同。这正是 ¶2.2 "实现在该声明的上下文中不支持"的含义：同一个 `alignas(N)` 在一个上下文中可行、在另一个上下文中可能非良构。
    - 硬件破坏性干扰尺寸 `std::hardware_destructive_interference_size`（C++17，`<new>`）常与 `alignas` 一起用于避免伪共享。

## 历史与演进

!!! history "C++11 → C++26"
    - **C++11**：`alignas`、`alignof`、`std::aligned_storage`（[[N2341]]）；`alignas(0)` 明确无效果。
    - **C++17**：`new` 支持超对齐类型（[[P0035R4]]）；`std::hardware_destructive_interference_size`。
    - **C++23**：`std::aligned_storage` 和 `std::aligned_union` 被弃用——推荐直接用 `alignas(T) std::byte buf[sizeof(T)];`。
    - 当前草案：`alignas(0)` 的特殊规则从 ¶2 中消失，¶4 保留"非零"字样（见上文 lawyer 框）。

## 陷阱

!!! pitfall "`alignas` 不是类型的一部分"
    `using A16 = alignas(16) int;` 非良构；`alignas` 加在变量上不影响 `decltype(var)`。需要可复用的高对齐类型，就写 `struct alignas(16) A16 { int v; };`。

!!! pitfall "成员上的 alignas 会改变类的 sizeof"
    类的对齐是其成员对齐的最大值，`sizeof` 必须是对齐的整数倍。一个 `alignas(64)` 的 `int` 成员会让整个类至少 64 字节。

!!! pitfall "malloc 不尊重 alignas"
    `std::malloc` 只保证基本对齐。超对齐类型用 `new`（C++17 起）或 `std::aligned_alloc`。

## 思考题

!!! question "思考题"
    下面的声明各自良构吗？最终对齐是多少？

    ```cpp
    alignas(2) alignas(char) short s1;
    alignas(char) short s2;
    alignas(short) alignas(1) short s3;
    ```

<details markdown="1">
<summary>答案</summary>

假设 `alignof(short) == 2`：

- `s1`：最严格的是 `alignas(2)`，对齐 2，不弱于 `short` 的自然对齐，良构。
- `s2`：合并效果是 1，弱于去掉后的 2，违反 ¶5，非良构。
- `s3`：最严格的是 2，满足 ¶5，良构——这正是 ¶7 中 `alignas(T) alignas(A)` 惯用法的原理：¶5 检查的是**合并后**的效果，而不是每个说明符单独检查。
</details>

## 小结

!!! summary "要点"
    - 用于变量、数据成员、类；不能用于函数、形参、位域、异常声明；不是类型的一部分。
    - `alignas(expr)` 必须是有效对齐值（2 的幂、实现支持）；`alignas(T)` = `alignas(alignof(T))`；可以包展开。
    - 多个说明符取最严格的非零值；合并结果不能弱于自然对齐。
    - 有一个声明写了 `alignas`，所有定义都必须写等价的；跨 TU 不一致是 IFNDR。
    - C++17 起 `new` 尊重扩展对齐。
