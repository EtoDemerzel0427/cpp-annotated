---
title: 对齐说明符
summary: alignas 用在变量、数据成员和类上，可以加强对齐但不能削弱；写了多个时取最严格的；同一实体的各个声明必须给出一致的对齐。
status: done
papers: N2341, P0035R4
related: basic.align, dcl.attr.grammar, expr.alignof, expr.new, class.mem, intro.object
tags: 属性, 对齐, 布局
updated: 2026-10-19
---

!!! tldr
    - `alignas` 可以用于变量、数据成员和类，不能用于函数、函数形参、位域和 `catch` 的形参；它也不是类型的一部分，`using` 别名带不上它。
    - `alignas(T)` 等价于 `alignas(alignof(T))`；同一声明写了多个时，取最严格（最大）的那个。
    - `alignas` 只能加强对齐。合并结果弱于实体本来需要的对齐，程序非良构；要打包结构体只能用编译器扩展。
    - 只要有一个声明写了 `alignas`，定义就必须写同样的对齐；跨翻译单元不一致不要求诊断。
    - C++17 起，`new` 一个对齐超过默认值的类型会调用带 `std::align_val_t` 的分配函数，得到正确对齐的内存。

## 用 alignas 加强对齐

```cpp run ok
struct alignas(64) CacheLine { int v; };
static_assert(alignof(CacheLine) == 64);
static_assert(sizeof(CacheLine) == 64);

struct Pair { alignas(64) int a; alignas(64) int b; };
static_assert(sizeof(Pair) == 128);   // a、b 各占一条缓存行

int main() {}
```

一个对象的地址必须是它的**对齐**（alignment）的整数倍。对齐值是 2 的幂，例如常见平台上 `int` 是 4，`double` 是 8，详见 [[basic.align]]。`alignas` 是 C++11 引入的**对齐说明符**（alignment-specifier），用来要求比默认更严格的对齐。

常见用途是让对象从缓存行或 SIMD 寄存器宽度的边界开始。上例中 `Pair` 的两个成员各自 64 字节对齐，于是分别落在两条缓存行上，两个线程分别写 `a` 和 `b` 时不会互相干扰（避免伪共享）。

语法上 `alignas(...)` 是一种 *attribute-specifier*（[[dcl.attr.grammar]]），所以它能写的位置与属性相同。但它和标准属性不同，会真正改变程序的含义：对齐影响布局、`sizeof`、`alignof` 和动态分配。

## 能用在哪里（¶1）

```cpp run error
struct alignas(16) V { int i; };      // OK：类
alignas(32) int g;                    // OK：变量
struct M { alignas(8) char c; };      // OK：数据成员

alignas(double) void f();             // error: 函数
void h(alignas(8) int p);             // error: 函数形参
struct BF { alignas(4) int b : 3; };  // error: 位域
using T = alignas(16) int;            // error: 不是类型的一部分
```

¶1 `alignas` 可以用于变量、类的数据成员，以及类的声明（写在 *class-head* 或 *elaborated-type-specifier* 里）。它不能用于位域、函数形参和异常声明（`catch` 的形参）。

形参和异常对象的存储位置不由被声明的那一方决定：形参由调用约定安排，可能在寄存器里；异常对象由运行时库分配。位域甚至没有地址。需要高对齐的形参时，传指针或引用。

`alignas` 也不是类型的一部分。没有 `alignas(16) int` 这样的类型，`typedef` 和 `using` 都带不上它，`decltype` 也看不到变量上的 `alignas`。想要一个可以复用的高对齐类型，就定义一个带 `alignas` 的类，比如 `struct alignas(16) A16 { int v; };`。

带 `...` 的 `alignas` 是包展开，展开成多个对齐说明符：

```cpp run ok
template<class... Ts>
struct alignas(Ts...) Storage {   // alignas(T1) alignas(T2) ...
  unsigned char data[16];
};
static_assert(alignof(Storage<char, double, int>)
              == alignof(double));
int main() {}
```

## 两种写法（¶2–¶3）

```cpp run error
alignas(3) int a;             // error: 3 不是 2 的幂
alignas(double) char b[8];    // OK：即 alignas(alignof(double))
alignas(1 << 20) char huge;   // 能否接受由实现决定
```

¶2 `alignas(表达式)` 里的表达式必须是整型常量表达式（¶2.1）。如果它的值不是一个合法的对齐值，或者是一个**扩展对齐**（extended alignment，超过 `alignof(std::max_align_t)` 的对齐），而实现在这个声明的上下文中不支持它，程序就是非良构的（¶2.2）。

能否支持扩展对齐取决于上下文。静态存储期的对象受目标文件格式和加载器的限制，栈上的变量受编译器重新对齐栈的能力限制，所以同一个 `alignas(N)` 可能在一处可行、在另一处非良构。本机 Clang 23 在全局和局部变量上都接受 `alignas(1 << 20)`。

¶3 `alignas(类型)` 等价于 `alignas(alignof(类型))`（[[expr.alignof]]）。这里的类型不能是函数类型。

!!! lawyer "alignas(0)"
    C++11 明文规定 `alignas(0)` 没有效果。当前草案的 ¶2 已经没有这句话，按 ¶2.2，0 不是对齐值（对齐值是 2 的幂），应当非良构；可是 ¶4 仍然说取最严格的非零对齐、否则没有效果，又像是默认 0 是合法的。本机 Clang 23 接受 `alignas(0) int y;` 而且没有警告。模板里 `alignas(N)` 的 `N` 可能为 0 时，不要依赖这一点。

## 写了多个：取最严格的（¶4）

¶4 实体的对齐要求是它的各个对齐说明符中最严格的非零对齐。没有对齐说明符时，它们当然不起作用。

```cpp run ok
alignas(4) alignas(16) alignas(8) int z;
int main() { return alignof(decltype(z)) == 4 ? 0 : 1; }   // z 本身按 16 对齐
```

最后一行也说明了 `alignas` 不进入类型：`decltype(z)` 就是 `int`，对齐仍是 4。

## 不能削弱（¶5）

```cpp run error
struct alignas(8) S {};
struct alignas(1) U {
  S s;
};                     // error: U 本来需要 8，alignas(1) 更弱

alignas(1) int weak;   // error: int 本来需要 4
```

¶5 一个声明中全部对齐说明符的合并效果，不得弱于去掉它们之后该实体本来需要的对齐。也就是说，`alignas` 只能加强对齐，不能减弱。

要减弱对齐（打包结构体），只能用 `#pragma pack`、`[[gnu::packed]]` 这类实现扩展。它们不在标准之内，访问打包成员可能产生未对齐访问。

¶5 检查的是合并后的效果，不是每个说明符单独检查。¶7 的例子利用这一点写出了一个通用的缓冲区声明，对齐为 A、能放 N 个 T：

```cpp
alignas(T) alignas(A) T buffer[N];
```

如果 A 小于 `alignof(T)`，单写 `alignas(A)` 会违反 ¶5；加上 `alignas(T)` 之后，¶4 取两者中较严格的，结果总是合法的。

## 所有声明必须一致（¶6）

```cpp run error
alignas(double) unsigned char c[sizeof(double)];  // 定义
extern unsigned char c[sizeof(double)];   // OK：可以不写
alignas(float)
  extern unsigned char c[sizeof(double)]; // error: 对齐不同
```

¶6 有三条要求：

- 定义带了对齐说明符，那么其他非定义的声明要么写等价的对齐，要么不写；
- 反过来，只要任何一个声明写了对齐说明符，每个定义都必须写等价的对齐；
- 不同翻译单元里的声明对齐说明符不同，程序非良构，但不要求诊断（{{ifndr}}，编译器不必报错，程序也没有任何保证）。

```cpp title="tu1.cpp"
struct S { int x; } s, *p = &s;
```

```cpp title="tu2.cpp" ifndr
struct alignas(16) S;   // 但 tu1 中 S 的定义没有这个对齐
extern S* p;
```

这条规则有方向。只是使用一个对象的翻译单元可以不关心对齐，写一个不带 `alignas` 的 `extern` 声明就行。但只要某个翻译单元看到了 `alignas(16)`，它就可能据此生成要求 16 字节对齐的 SIMD 加载指令；而分配存储的是定义，定义没有给出这个对齐，运行时就会出错。编译器一次只看一个翻译单元，查不出这种不一致，所以规定为 IFNDR。

## 动态分配

`alignas` 声明的类型如果需要扩展对齐，C++17 之前的 `new` 并不保证满足它，因为 `operator new` 只保证基本对齐。C++17 的 [[P0035R4]] 加入了带 `std::align_val_t` 参数的分配函数。类型的对齐超过 `__STDCPP_DEFAULT_NEW_ALIGNMENT__` 时，`new` 表达式会自动调用它们（[[expr.new]]、[[basic.stc.dynamic.allocation]]）。

```cpp run ok
#include <cstdint>
#include <cstdio>
#include <cstddef>

struct alignas(64) CacheLine { int v; };

int main() {
  auto* p = new CacheLine[3];   // 调用 operator new[](size_t, align_val_t)
  auto addr = reinterpret_cast<std::uintptr_t>(p);
  std::printf("misalign=%d max_align=%zu\n",
              static_cast<int>(addr % 64), alignof(std::max_align_t));
  delete[] p;
}
```

本机（arm64 macOS）输出 `misalign=0 max_align=8`；x86-64 Linux 上 `max_align_t` 的对齐是 16。`std::malloc` 只保证基本对齐，不理会 `alignas`，需要超对齐的内存时用 `new` 或 `std::aligned_alloc`。

!!! impl "实现视角"
    - GCC 和 Clang 把 `alignas` 映射到与 `__attribute__((aligned(N)))` 相同的机制。GNU 的 `aligned` 属性在 typedef 上可以降低对齐，这属于扩展，标准写法不允许。
    - 栈上的超对齐变量要求编译器在函数开头重新对齐栈指针，x86-64 上会看到 `and rsp, -64` 之类的指令，通常还需要帧指针。
    - `std::hardware_destructive_interference_size`（C++17，`<new>`）给出避免伪共享所需的间隔，常和 `alignas` 一起使用。

## 历史与演进

!!! history
    - C++11：`alignas`、`alignof`、`std::aligned_storage`（[[N2341]]）；明确 `alignas(0)` 没有效果。
    - C++17：`new` 支持超对齐类型（[[P0035R4]]）；加入 `std::hardware_destructive_interference_size`。
    - C++23：弃用 `std::aligned_storage` 和 `std::aligned_union`，推荐直接写 `alignas(T) std::byte buf[sizeof(T)];`。
    - 当前草案的 ¶2 不再提 `alignas(0)`，¶4 仍保留非零的字样，见上文。

## 思考题

!!! question "思考题"
    假设 `alignof(short) == 2`，下面的声明各自良构吗？
    ```cpp
    alignas(2) alignas(char) short s1;
    alignas(char) short s2;
    alignas(short) alignas(1) short s3;
    ```

<details markdown="1">
<summary>答案</summary>

- `s1`：良构。最严格的是 2，不弱于 `short` 本来的对齐。
- `s2`：非良构。合并效果是 1，弱于去掉之后的 2，违反 ¶5。本机 Clang 报错 `requested alignment is less than minimum alignment of 2`。
- `s3`：良构。虽然 `alignas(1)` 单独看更弱，但 ¶5 只看合并效果，合并结果是 2。¶7 的 `alignas(T) alignas(A)` 写法依靠的正是这一点。
</details>
