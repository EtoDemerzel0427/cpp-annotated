---
title: 类型转换总览
summary: 隐式转换、四个具名转换、C 风格与函数式转换、std::bit_cast 各自做什么，想做某件事时该选哪一个，哪些类型双关是合法的，以及最常见的转换相关 UB。
status: draft
order: 45
since: c++98
papers: P0476R2, P0849R8, P2590R2, P0593R6
related: conv, expr.static.cast, expr.dynamic.cast, expr.reinterpret.cast, expr.const.cast, expr.cast, expr.type.conv, basic.lval, bit.cast, obj.lifetime, topics/value-categories
tags: 类型转换, 严格别名, 类型双关, UB
updated: 2026-10-19
---

!!! tldr
    - 转换分两类：值转换算出一个新值（`3` 变成 `3.0`），重新解释只换一个类型去看同一块存储或同一组位。
    - `reinterpret_cast` 的转换本身几乎总是合法的，出问题的是通过结果去读写对象，那常常违反严格别名规则。
    - 想看一个 `float` 的位模式，用 `std::bit_cast` 或 `std::memcpy`；经 `unsigned char`、`std::byte` 逐字节访问也合法；联合体双关在 C++ 中是 UB。
    - 向下转换时，确定类型正确用 `static_cast`，不确定用 `dynamic_cast`。
    - C 风格转换 `(T)e` 会按上下文选择不同的具名转换，同一行代码的含义可能随类型是否完整而改变。

## 能跑出正确结果的 UB

<div class="compare" markdown="1">

```cpp run ub
#include <cstdint>
#include <cstdio>
int main() {
  float f = 1.0f;
  auto u = *reinterpret_cast<
      std::uint32_t*>(&f);  // UB
  std::printf("%x\n", u);
}
```

```cpp run ok
#include <bit>
#include <cstdint>
#include <cstdio>
int main() {
  float f = 1.0f;
  auto u = std::bit_cast<
      std::uint32_t>(f);    // OK
  std::printf("%x\n", u);
}
```

</div>

两段代码在本机都打印 `3f800000`。左边的转换本身没有问题，问题在解引用：它通过 `uint32_t` 类型的左值去读一个 `float` 对象。按严格别名规则（[[basic.lval#11]]），一个对象只能通过与它的类型相似的类型、对应的有符号或无符号类型，或者 `char`、`unsigned char`、`std::byte` 去访问，否则是 UB。编译器的别名分析依赖这条规则，优化后左边的代码可能读到过时的值。

右边的 `std::bit_cast` 创建一个新的 `uint32_t` 对象，复制 `f` 的位，不涉及别名问题。

这个例子说明了转换的两类风险。下面先给转换分类，再列出每种转换的能力，最后讲类型双关和常见的 UB。

## 两类转换

| 类别 | 做了什么 | 代表 |
|---|---|---|
| 值转换 | 计算一个新值，类型不同、含义相同，例如 `3` 变成 `3.0`，`Derived*` 变成地址调整过的 `Base*` | 隐式转换、`static_cast`、`dynamic_cast`、函数式转换 |
| 重新解释 | 不改变地址或位模式，只换一个类型去看 | `reinterpret_cast`、`const_cast`（只改 cv 限定）、`std::bit_cast`（把位模式复制到新对象） |

值转换的风险在于信任。`static_cast` 做向下转换时，相信程序员给出的类型是对的；错了就是 UB。

重新解释的风险在于访问。转换得到的指针或引用通常是合法的，但通过它读写对象可能违反严格别名规则。

## 每种转换能做什么

| 转换 | 条款 | 能力 | 检查 | 常量求值 |
|---|---|---|---|---|
| 隐式转换 | [[conv]]、[[over.best.ics]] | 标准转换序列加至多一次用户定义转换 | 编译期；只有列表初始化禁止窄化 | 可以 |
| `static_cast` | [[expr.static.cast]] | 隐式转换及其逆向、显式构造函数和转换函数、向下转换、`void*` 到 `T*`、枚举 | 编译期；向下转换不检查动态类型 | 可以（`void*` 到 `T*` 从 C++26 起） |
| `dynamic_cast` | [[expr.dynamic.cast]] | 多态类型的向下转换和交叉转换、取最派生对象的地址 | 运行期；失败得到空指针或抛出 `bad_cast` | 可以（C++20 起） |
| `const_cast` | [[expr.const.cast]] | 只改 cv 限定 | 编译期 | 可以，但不能借此修改 const 对象 |
| `reinterpret_cast` | [[expr.reinterpret.cast]] | 指针与整数互转、无关指针类型互转、函数指针互转、引用的重新解释 | 无 | 不可以 |
| `(T)e` | [[expr.cast]] | 按顺序尝试 `const_cast`、`static_cast`、`reinterpret_cast` 及其组合；可以无视私有继承 | 由选中的那个决定 | 由选中的那个决定 |
| `T(e)` | [[expr.type.conv]] | 单个实参时与 `(T)e` 相同；多个实参时是直接初始化 | 同上 | 同上 |
| `T{e}` | [[expr.type.conv]]、[[dcl.init.list]] | 直接列表初始化 | 禁止窄化 | 可以 |
| `auto(e)` | [[expr.type.conv]] | 复制出一个 prvalue（C++23，[[P0849R8]]） | 编译期 | 可以 |
| `std::bit_cast<T>(e)` | [[bit.cast]] | 把对象表示复制到一个新的 `T` 对象（C++20，[[P0476R2]]） | 大小相等，两边都可平凡复制 | 可以，但类型中不能有指针、引用、联合体 |

还有两个工具不改变表达式的类型，而是处理对象的身份：`std::launder`（[[ptr.launder]]）和 `std::start_lifetime_as`（[[obj.lifetime]]）。后者在下文类型双关一节介绍。

## 想做某件事该用哪个

| 想做的事 | 用 | 不要用 |
|---|---|---|
| 数值类型之间转换，允许截断 | `static_cast<T>(x)` | `(T)x`、`T(x)`：意图不清楚 |
| 数值转换，但禁止丢失信息 | `T{x}` | |
| 有作用域枚举与整数互转 | `static_cast`，或 C++23 的 `std::to_underlying(e)` | `reinterpret_cast`：非良构 |
| 整数转换到没有固定底层类型的枚举 | 先检查值域，再 `static_cast` | 直接转换：超出值域是 UB |
| 派生类指针转换为基类指针 | 隐式转换 | `reinterpret_cast`：不调整地址 |
| 基类转换为派生类，确定类型正确 | `static_cast` | C 风格转换：见下文 |
| 基类转换为派生类，不确定类型 | `dynamic_cast`（要求多态类型） | `static_cast`：错了是 UB |
| 经过虚基类向下转换，或者交叉转换 | `dynamic_cast` | `static_cast`：非良构 |
| 取多态对象的完整对象地址 | `dynamic_cast<void*>(p)` | `static_cast<void*>(p)`：只是子对象的地址 |
| 调用不够 const 正确的旧接口 | `const_cast`，并确保不写入 | C 风格转换 |
| 把左值标记为可以移动 | `std::move(x)`，即 `static_cast<T&&>(x)` | |
| 完美转发 | `std::forward<T>(x)` | 手写 `static_cast<T&&>`：容易写错 |
| 得到一个副本 prvalue | `auto(x)`（C++23） | |
| 丢弃一个值，例如压制 `[[nodiscard]]` 警告 | `static_cast<void>(x)` 或 `(void)x` | |
| 指针转换为整数（哈希、检查对齐） | `reinterpret_cast<std::uintptr_t>(p)` | `static_cast`：非良构 |
| 整数转换为指针（内存映射的硬件地址） | `reinterpret_cast<T*>(addr)`，结果由实现定义 | |
| 存储不同类型的函数指针 | `reinterpret_cast<void(*)()>(f)`，调用前转回原类型 | 以错误的类型调用：UB |
| 查看对象的原始字节 | `reinterpret_cast<const unsigned char*>(&obj)` 或 `std::as_bytes` | 经 `uint32_t*` 读：UB |
| 取 `float` 的位模式 | `std::bit_cast<std::uint32_t>(f)` | 经 `uint32_t*` 读、联合体双关：UB |
| 把一段字节缓冲区当作结构体使用 | `std::start_lifetime_as<T>(buf)`（C++23），或 `memcpy` 到局部对象 | `reinterpret_cast<T*>(buf)` 之后直接访问 |

### C 风格转换的含义会变

`(T)e` 依次尝试几种具名转换，取第一个合法的（[[expr.cast#4]]）。同一行代码选中哪一种，取决于此处可见的声明：

```cpp run unspecified
#include <cstdio>
struct A { int a; };
struct B { int b; };
struct C;                          // 此处只有前向声明
B* early(C* c) { return (B*)c; }   // Clang 按 reinterpret_cast 解释
struct C : A, B {};
B* late(C* c) { return (B*)c; }    // 按 static_cast 解释
int main() {
  C c;
  std::printf("%d\n", early(&c) == late(&c));   // 0
}
```

`C` 完整时，`(B*)c` 按 `static_cast` 解释，地址加上 `B` 子对象的偏移。`C` 不完整时，标准规定选用 `static_cast` 还是 `reinterpret_cast` 的解释是未指定的（[[expr.cast#5]]）：一个多遍扫描的编译器可以看到后面的定义。Clang 一遍扫描，此时不知道 `B` 是 `C` 的基类，只能按 `reinterpret_cast` 解释，地址不变。

本机运行打印 `0`，编译时没有任何警告。写成 `static_cast<B*>(c)`，不完整的情况会直接报错。

## 类型双关：哪些写法合法

**类型双关**（type punning，[[g:type-punning]]）指把一个对象的存储当作另一种类型来读。C++ 中合法的方式只有下面几种。

### std::bit_cast

```cpp run title="pun-bitcast.cpp" ok
#include <bit>
#include <cstdint>

constexpr std::uint32_t float_bits(float f) { return std::bit_cast<std::uint32_t>(f); }
static_assert(float_bits(1.0f) == 0x3f800000u);   // 可以在编译期使用

int main() { return float_bits(-0.0f) == 0x80000000u ? 0 : 1; }
```

`bit_cast` 要求两个类型大小相同，并且都可平凡复制。它创建一个新对象，所以不存在别名问题。在常量求值中，类型里还不能有指针、引用、联合体或 volatile 成员。

### std::memcpy

```cpp run title="pun-memcpy.cpp" ok
#include <cstdint>
#include <cstring>

std::uint32_t float_bits(float f) {
  std::uint32_t u;
  std::memcpy(&u, &f, sizeof u);   // 复制对象表示
  return u;
}

int main() { return float_bits(1.0f) == 0x3f800000u ? 0 : 1; }
```

C++20 之前这是唯一可移植的做法。现代编译器会把这次 `memcpy` 优化成一次寄存器移动，没有额外开销。

### 经 char、unsigned char、std::byte 访问

严格别名规则明确允许经这三种类型访问任何对象（[[basic.lval#11]] ¶11.3），`memcpy`、序列化、哈希函数都依赖这一点。这个豁免是单向的：经 `unsigned char*` 读一个 `float` 合法，把一个 `unsigned char` 数组经 `float*` 读出来不合法，因为那里没有 `float` 对象。

### 对应的有符号和无符号类型

`int` 对象可以经 `unsigned int` 类型的左值访问，反过来也可以（¶11.2）。

### std::start_lifetime_as（C++23）

```cpp title="pun-start-lifetime.cpp"
#include <cstdint>
#include <memory>
#include <cstddef>

struct Header { std::uint16_t type; std::uint16_t len; };

void parse(std::byte* buf) {   // buf 来自网络，内容已就绪，对齐满足 Header 的要求
  Header* h = std::start_lifetime_as<Header>(buf);   // 在原地开始一个 Header 的生命周期，保留字节
  // 使用 h->type、h->len ...
}
```

`start_lifetime_as`（[[P2590R2]]，[[obj.lifetime]]）在已有的存储上隐式创建一个隐式生存期类型（[[g:implicit-lifetime-type]]）的对象，并保留原有的字节值。把网络缓冲区当作结构体读取，以前只能靠 UB 或 `memcpy`，这个函数提供了合法的写法。本机的 libc++ 还没有提供它，这个例子没有经过编译。

### 不合法的写法

| 写法 | 为什么是 UB |
|---|---|
| `*reinterpret_cast<std::uint32_t*>(&f)` | 经 `uint32_t` 左值访问 `float` 对象，违反 [[basic.lval#11]] |
| `*static_cast<std::uint32_t*>(static_cast<void*>(&f))` | 与上一行完全等价（[[expr.reinterpret.cast#7]]） |
| 联合体双关：写 `x.f`，再读 `x.u` | `x.u` 不是活跃成员，不在生命周期内（[[class.union]]）。C 允许这种写法，C++ 不允许；GCC 作为扩展保证它的行为 |
| `reinterpret_cast<Header*>(buf)->len`，`buf` 是普通字节数组 | 那里没有 `Header` 对象 |

```cpp run title="pun-union.cpp" ub
#include <cstdint>

int main() {
  union { float f; std::uint32_t u; } x;
  x.f = 1.0f;
  return x.u == 0x3f800000u ? 0 : 1;   // UB：u 不是活跃成员（C 中这是合法的类型双关）
}
```

## 常见的转换相关 UB

| UB | 规则 | 怎样避免 |
|---|---|---|
| `static_cast` 向下转换到错误的派生类 | [[expr.static.cast#2]]、[[expr.static.cast#10]] | 用 `dynamic_cast`，或者在设计上避免 |
| 整数转换为没有固定底层类型的枚举时超出值域 | [[expr.static.cast#8]] | 给枚举指定底层类型 |
| 浮点转换为整数时超出范围，例如 `(int)1e10` | [[conv.fpint]] | 先检查范围 |
| 经 `const_cast` 修改 const 对象 | [[dcl.type.cv]] | 只对本来不是 const 的对象去掉 const |
| 经 `reinterpret_cast` 得到的指针读写不兼容类型的对象 | [[basic.lval#11]] | `bit_cast` 或 `memcpy` |
| 经 `reinterpret_cast` 得到的指针访问类成员，而对象类型不相似 | [[expr.ref#10]] | 用 `static_cast` 做基类转换 |
| 以不兼容的函数类型调用函数 | [[expr.call#6]] | 调用前转回原类型 |
| 对生命周期已结束的对象做 `dynamic_cast` | [[expr.dynamic.cast#7]] | 管理好生命周期 |
| `void*` 转换为 `T*` 时地址未对齐，然后解引用 | [[expr.static.cast#12]]、[[basic.align]] | 检查对齐，或者用 `memcpy` |

## 编译器和工具

!!! impl
    - 警告：`-Wold-style-cast`（C 风格转换）、`-Wcast-qual`（去掉 cv 限定）、`-Wcast-align`（对齐要求提高）、Clang 的 `-Wreinterpret-base-class`（对偏移非零的基类用 `reinterpret_cast`）、GCC 的 `-Wstrict-aliasing`。
    - 运行期检查：UBSan 的 `-fsanitize=vptr` 检查按错误动态类型做的成员访问和向下转换（需要 RTTI）；`-fsanitize=function` 检查以错误类型调用函数指针；`-fsanitize=float-cast-overflow` 检查浮点到整数的溢出；`-fsanitize=enum` 检查读到不合法的枚举值。
    - `-fno-strict-aliasing` 关闭基于类型的别名分析，让违反严格别名规则的代码按程序员预期的方式运行。它不改变标准层面的 UB，也不能移植到其他编译器。
    - `-fno-rtti` 下，`typeid` 和大多数 `dynamic_cast` 不可用；向上转换和 Clang 中的 `dynamic_cast<void*>` 仍然可以。

```cpp run title="ubsan-vptr.cpp" flags="-std=c++2c -fsanitize=vptr,undefined" ub
struct B { virtual ~B() = default; };
struct D1 : B { int x = 1; };
struct D2 : B { int y = 2; };

int main() {
  D2 d2;
  B* b = &d2;
  D1* p = static_cast<D1*>(b);   // UB：b 实际指向 D2
  return p->x;
}
```

本机运行时 UBSan 报告 `downcast of address … which does not point to an object of type 'D1'`。

## 演进

!!! history
    - C 和早期 C++ 只有 `(T)e`。函数式写法 `T(e)` 是为了让内置类型和类类型的构造写法统一。
    - C++98 加入四个具名转换，C 风格转换被重新定义为它们的组合；同时加入 RTTI（`dynamic_cast`、`typeid`）。
    - C++11 加入列表初始化与窄化检查，以及右值引用和 `std::move`、`std::forward`，后两者本质上是 `static_cast`。
    - C++17 重写了对象模型，引入指针可互转（pointer-interconvertible）的概念和 `std::launder`。
    - C++20 加入 `std::bit_cast`（[[P0476R2]]）和对象的隐式创建（[[P0593R6]]）；`dynamic_cast`、`typeid` 可以用于常量求值。
    - C++23 加入 `auto(x)`（[[P0849R8]]）、`std::start_lifetime_as`（[[P2590R2]]）和 `std::to_underlying`。
    - C++26 允许在常量求值中把 `void*` 转换为 `T*`。
