---
title: C++ 的类型转换全家桶
summary: 隐式转换、四个具名转换、C 风格与函数式转换、std::bit_cast 各管什么；一张"我想做 X 该用什么"的决策表；合法的类型双关方式；最常见的转换相关 UB
status: draft
order: 45
since: c++98
papers: P0476R2, P0849R8, P2590R2, P0593R6
related: conv, expr.static.cast, expr.dynamic.cast, expr.reinterpret.cast, expr.const.cast, expr.cast, expr.type.conv, basic.lval, bit.cast, obj.lifetime, topics/value-categories
tags: 类型转换, 严格别名, 类型双关, UB
updated: 2026-10-17
---

C++ 有至少八种改变表达式类型的方式：隐式转换、`static_cast`、`dynamic_cast`、`const_cast`、`reinterpret_cast`、C 风格 `(T)e`、函数式 `T(e)` / `T{e}` / `auto(e)`，以及库函数 `std::bit_cast`（还有 `std::launder`、`std::start_lifetime_as` 这类"不改类型、改对象身份"的工具）。本专题把它们放在一起比较，回答一个实用问题：**我想做 X，应该用哪个？哪些写法看似可行其实是 UB？**

每种转换的逐段规则见各自的条款页，本页只给地图和判断方法。

## 一、两个维度：改"值"还是改"看法"

所有转换可以按它对**值**做了什么分成两大类：

| 类别 | 做了什么 | 代表 |
|---|---|---|
| **值转换** | 计算一个**新值**，类型不同、含义相同（3 → 3.0，`Derived*` → 调整过地址的 `Base*`） | 隐式转换、`static_cast`、`dynamic_cast`、函数式转换 |
| **重新解释** | **不改位置或位模式**，只换一个类型去看 | `reinterpret_cast`、`const_cast`（只改 cv）、`std::bit_cast`（复制位模式到新对象） |

第一类的危险在于**信任**：`static_cast` 向下转换时相信你说的类型是对的。第二类的危险在于**访问**：转换本身几乎总是合法的，但通过结果去读写对象往往违反严格别名规则（[[basic.lval#11]]）。

## 二、各成员一览

| 转换 | 条款 | 能力 | 检查 | 常量求值 |
|---|---|---|---|---|
| 隐式转换 | [[conv]]、[[over.best.ics]] | 标准转换序列 + 至多一次用户定义转换 | 编译期；窄化只在列表初始化中禁止 | ✓ |
| `static_cast` | [[expr.static.cast]] | 隐式转换及其"逆"、显式构造/转换函数、向下转换、`void*` → `T*`、枚举 | 编译期；向下转换不检查 | ✓（`void*` → `T*` 需 C++26） |
| `dynamic_cast` | [[expr.dynamic.cast]] | 多态类型的向下/交叉转换、取最派生对象 | **运行期**；失败得空指针或 `bad_cast` | ✓（C++20） |
| `const_cast` | [[expr.const.cast]] | 只改 cv | 编译期 | ✓（修改 const 对象除外） |
| `reinterpret_cast` | [[expr.reinterpret.cast]] | 指针 ↔ 整数、无关指针、函数指针、引用双关 | 无 | ✗ |
| `(T)e` | [[expr.cast]] | 按顺序尝试 const/static/reinterpret 组合；可无视私有继承 | 无（由选中的那个决定） | 取决于选中的 |
| `T(e)` | [[expr.type.conv]] | 单实参 ≡ `(T)e`；多实参 / 花括号 = 直接初始化 | 同上 | 同上 |
| `T{e}` | [[expr.type.conv]]、[[dcl.init.list]] | 直接列表初始化 | **禁止窄化** | ✓ |
| `auto(e)` | [[expr.type.conv]] | decay-copy（C++23，[[P0849R8]]） | 编译期 | ✓ |
| `std::bit_cast<T>(e)` | [[bit.cast]] | 复制对象表示到新的 `T` 对象（C++20，[[P0476R2]]） | 大小相等、可平凡复制 | ✓（无指针/联合体等） |

## 三、决策表：我想……

| 我想…… | 用 | 不要用 |
|---|---|---|
| 数值类型之间转换（可能截断） | `static_cast<T>(x)` | `(T)x`、`T(x)`（意图不清） |
| 数值转换但**禁止**丢失信息 | `T{x}` | — |
| 有作用域枚举 ↔ 整数 | `static_cast` / `std::to_underlying(e)`（C++23） | `reinterpret_cast`（非良构） |
| 整数 → 无固定底层类型的枚举 | 先检查值域，再 `static_cast` | 直接转换（超出值域是 UB） |
| 派生类指针 → 基类指针 | 隐式转换 | `reinterpret_cast`（不调整地址） |
| 基类 → 派生类，**确定**类型正确 | `static_cast` | C 风格（会在类型关系变化时静默变为 `reinterpret_cast`） |
| 基类 → 派生类，**不确定** | `dynamic_cast`（要求多态） | `static_cast`（错了是 UB） |
| 经虚基类向下转换 / 交叉转换 | `dynamic_cast` | `static_cast`（非良构） |
| 取得多态对象的完整对象地址 | `dynamic_cast<void*>(p)` | `static_cast<void*>(p)`（只是子对象地址） |
| 调用不够 const 正确的旧接口 | `const_cast`（确保不写入） | C 风格 |
| 把左值标记为可移动 | `std::move(x)`（即 `static_cast<T&&>`） | — |
| 完美转发 | `std::forward<T>(x)` | 手写 `static_cast<T&&>`（易错） |
| 制造一个副本 prvalue | `auto(x)`（C++23） | — |
| 丢弃一个值（压制 `[[nodiscard]]`） | `static_cast<void>(x)` 或 `(void)x` | — |
| 指针 → 整数（哈希、对齐检查） | `reinterpret_cast<std::uintptr_t>(p)` | `static_cast`（非良构） |
| 整数 → 指针（MMIO 地址） | `reinterpret_cast<T*>(addr)`（实现定义） | — |
| 存储异构函数指针 | `reinterpret_cast<void(*)()>(f)`，调用前转回原类型 | 以错误类型调用（UB） |
| 查看对象的原始字节 | `reinterpret_cast<const unsigned char*>(&obj)` 或 `std::as_bytes(std::span{...})` | 经 `uint32_t*` 读（UB） |
| 把 `float` 的位模式当 `uint32_t` | `std::bit_cast<std::uint32_t>(f)` | `*reinterpret_cast<uint32_t*>(&f)`、联合体双关（UB） |
| 把字节缓冲区当作结构体使用 | `std::start_lifetime_as<T>(buf)`（C++23）或 `memcpy` 到局部对象 | `reinterpret_cast<T*>(buf)` 后直接访问 |

## 四、类型双关：哪些合法

"类型双关"（type punning）指把一个对象的存储当作另一种类型来读。C++ 里**合法**的方式只有这些：

### 1. `std::bit_cast`（首选）

```cpp run title="pun-bitcast.cpp" ok
#include <bit>
#include <cstdint>

constexpr std::uint32_t float_bits(float f) { return std::bit_cast<std::uint32_t>(f); }
static_assert(float_bits(1.0f) == 0x3f800000u);   // 可在编译期使用

int main() { return float_bits(-0.0f) == 0x80000000u ? 0 : 1; }
```

`bit_cast` 要求两个类型大小相同且**可平凡复制**；它创建一个**新对象**，所以不存在别名问题。常量求值中还要求类型不含指针、引用、联合体、`volatile` 成员。

### 2. `std::memcpy`

```cpp run title="pun-memcpy.cpp" ok
#include <cstdint>
#include <cstring>

std::uint32_t float_bits(float f) {
    std::uint32_t u;
    std::memcpy(&u, &f, sizeof u);   // 复制对象表示：合法，编译器会优化为一次寄存器移动
    return u;
}

int main() { return float_bits(1.0f) == 0x3f800000u ? 0 : 1; }
```

这是 C++20 之前唯一可移植的做法，现代编译器会把它优化掉，没有性能代价。

### 3. 经 `char` / `unsigned char` / `std::byte` 访问

严格别名规则明确豁免这三种类型（[[basic.lval#11]]，11.3）：任何对象都可以经它们逐字节读（和写）。这就是 `memcpy`、序列化、哈希函数的基础。注意豁免是**单向**的：经 `unsigned char*` 看 `float` 合法，把一个 `unsigned char` 数组经 `float*` 读出来则不合法（那里没有 `float` 对象）。

### 4. 有/无符号对应类型

`int` 对象可以经 `unsigned int` glvalue 访问（11.2），反之亦然。

### 5. `std::start_lifetime_as`（C++23）

```cpp title="pun-start-lifetime.cpp"
#include <cstdint>
#include <memory>
#include <cstddef>

struct Header { std::uint16_t type; std::uint16_t len; };

void parse(std::byte* buf) {   // buf 来自网络，内容已就绪，且对齐满足 Header 的要求
    Header* h = std::start_lifetime_as<Header>(buf);   // 在原地开始一个 Header 对象的生命周期，保留字节
    // 使用 h->type, h->len ...
}
```

`start_lifetime_as`（[[P2590R2]]，[[obj.lifetime]]）在已有存储上隐式创建一个隐式生存期类型的对象，**保留原有的字节值**。它解决的正是"网络缓冲区 → 结构体"这个长久以来只能靠 UB 或 `memcpy` 的问题。截至写作时，本机的 libc++ 尚未提供它，此例未经编译验证。

### 不合法的方式

| 写法 | 为什么 UB |
|---|---|
| `*reinterpret_cast<std::uint32_t*>(&f)` | 经 `uint32_t` glvalue 访问 `float` 对象，违反 [[basic.lval#11]] |
| `*static_cast<std::uint32_t*>(static_cast<void*>(&f))` | 与上一行**完全等价**（[[expr.reinterpret.cast#7]]） |
| `union { float f; std::uint32_t u; } x; x.f = 1; return x.u;` | 读非活跃成员，`x.u` 不在生命周期内（[[basic.life]]、[[class.union]]）。C 允许，C++ 不允许；GCC 作为扩展保证其行为 |
| `reinterpret_cast<Header*>(buf)->len`（`buf` 是普通字节数组、没有隐式创建对象） | 那里没有 `Header` 对象 |

```cpp run title="pun-union.cpp" ub
#include <cstdint>

int main() {
    union { float f; std::uint32_t u; } x;
    x.f = 1.0f;
    return x.u == 0x3f800000u ? 0 : 1;   // UB（C++）：u 不是活跃成员；C 中这是合法的类型双关
}
```

## 五、最常见的转换相关 UB 清单

| UB | 规则 | 怎么避免 |
|---|---|---|
| `static_cast` 向下转换到错误的派生类 | [[expr.static.cast#2]]、[[expr.static.cast#10]] | `dynamic_cast` 或设计上避免 |
| 整数转换为无固定底层类型枚举时超出值域 | [[expr.static.cast#8]] | 给枚举指定底层类型 |
| 浮点 → 整数超出范围（`(int)1e10`） | [[conv.fpint]] | 先检查范围 |
| 经 `const_cast` 修改 const 对象 | [[dcl.type.cv]] | 只对本不是 const 的对象去 const |
| 经 `reinterpret_cast` 的指针读写不兼容类型的对象 | [[basic.lval#11]] | `bit_cast` / `memcpy` |
| 经 `reinterpret_cast` 访问类成员（对象类型不相似） | [[expr.ref#10]] | 用 `static_cast` 做基类转换 |
| 以不调用兼容的函数类型调用函数 | [[expr.call#6]] | 调用前转回原类型 |
| 对悬垂指针 `dynamic_cast` / `typeid` | [[expr.dynamic.cast#7]]、[[basic.life#7]] | 管理生命周期 |
| `void*` → `T*` 未对齐，然后解引用 | [[expr.static.cast#12]]、[[basic.align]] | 检查对齐或 `memcpy` |

## 六、实现与工具

!!! impl
    - **警告**：`-Wold-style-cast`（C 风格转换）、`-Wcast-qual`（去掉 cv）、`-Wcast-align`（对齐要求提高）、Clang 的 `-Wreinterpret-base-class`（`reinterpret_cast` 用于有偏移的基类）、GCC 的 `-Wstrict-aliasing`。
    - **运行期检查**：UBSan 的 `-fsanitize=vptr` 检查经错误动态类型的成员访问和向下转换（需要 RTTI）；`-fsanitize=function` 检查经错误类型的函数指针调用；`-fsanitize=float-cast-overflow` 检查浮点到整数的溢出；`-fsanitize=enum` 检查读取越界的枚举值。
    - **编译选项**：`-fno-strict-aliasing` 关闭基于类型的别名分析，让违反严格别名规则的代码"按预期"运行——但它不改变标准层面的 UB，也不能移植到其他编译器。
    - **RTTI**：`-fno-rtti` 下 `dynamic_cast`（除向上转换和 `void*` 外）与 `typeid` 不可用。

```cpp run title="ubsan-vptr.cpp" flags="-std=c++2c -fsanitize=vptr,undefined" ub
struct B { virtual ~B() = default; };
struct D1 : B { int x = 1; };
struct D2 : B { int y = 2; };

int main() {
    D2 d2;
    B* b = &d2;
    D1* p = static_cast<D1*>(b);   // UB：b 实际指向 D2；-fsanitize=vptr 会在运行期报告
    return p->x;
}
```

## 七、历史脉络

!!! history
    - **C 与早期 C++**：只有 `(T)e`；函数式写法 `T(e)` 为统一内置类型与类类型的"构造"而引入。
    - **C++98**：四个具名转换，C 风格转换被重新定义为它们的组合；RTTI（`dynamic_cast`、`typeid`）。
    - **C++11**：列表初始化与窄化检查（`T{e}`）；右值引用与 `std::move`/`std::forward`（本质是 `static_cast`）；`reinterpret_cast` 对象指针以 `static_cast` 经 `void*` 定义。
    - **C++17**：指针可互转与 `std::launder` 的对象模型。
    - **C++20**：`std::bit_cast`（[[P0476R2]]）；对象的隐式创建（[[P0593R6]]）；`dynamic_cast`/`typeid` 可用于常量求值。
    - **C++23**：`auto(x)`（[[P0849R8]]）；`std::start_lifetime_as`（[[P2590R2]]）；`std::to_underlying`。
    - **C++26**：常量求值中的 `void*` → `T*`。

## 小结

!!! summary
    - 优先级：**不转换** > 隐式转换 > `T{x}` > `static_cast` > `dynamic_cast` > `const_cast` > `reinterpret_cast` > C 风格 / 单参数函数式转换。
    - 具名转换表达意图、便于搜索；C 风格与 `T(x)` 隐藏意图并随上下文改变含义。
    - `reinterpret_cast` 的转换几乎总是合法，**使用**结果才是问题；位模式重解释用 `std::bit_cast`，字节访问用 `unsigned char`/`std::byte`，原地"视为"结构体用 `std::start_lifetime_as`。
    - 向下转换：确定时 `static_cast`，不确定时 `dynamic_cast`；两者都无法替你管理生命周期。
