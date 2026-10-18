---
title: 类型双关的合法与非法
summary: "把这些字节当成另一种类型来看"在 C++ 里要过三道关——那里有没有该类型的对象、能不能通过该类型的 glvalue 访问、指针是不是指向它。逐一检视严格别名、union 双关、reinterpret_cast、memcpy、std::bit_cast（含 constexpr 规则）、std::start_lifetime_as、字节数组提供存储、指针可互转与 -fno-strict-aliasing，并附 Clang -O2 真实错误优化演示
status: draft
order: 14
since: c++98
papers: P0476R2, P2590R2, P0593R6, P2738R1
related: basic.lval, intro.object, basic.compound, expr.reinterpret.cast, expr.static.cast, class.union, bit.cast, obj.lifetime, basic.types.trivial, expr.add, expr.const.core, topics/object-model, topics/casts, topics/undefined-behavior
tags: 类型双关, 严格别名, bit_cast, 对象模型, UB, 专题
updated: 2026-10-18
---

**类型双关**（type punning）指用一种类型去解读另一种类型对象的字节：把 `float` 的位模式当 `uint32_t` 看、把网络包的字节当结构体看、把 `int` 数组当 `unsigned` 数组遍历。C 程序员做这件事的工具是指针转换和 union；在 C++ 里，这两种工具大多数时候都是 UB。

要判断一次双关是否合法，需要依次回答三个问题。它们分属对象模型的不同层次（见 [[topics/object-model]]）：

1. **对象存在吗？** 那个地址上有没有一个（在生命周期内的）`T` 对象？——[[intro.object]]、[[basic.life]]
2. **指针指向它吗？** 我手里的 `T*` 的**值**是指向那个 `T` 对象，还是仍指向原来的对象？——[[basic.compound#7]]、[[expr.static.cast#12]]
3. **允许这样访问吗？** 通过 `T` 类型的 glvalue 读写那个对象，是否满足 type-accessible？——[[basic.lval#11]]

外加一个常被忽略的物理前提：**对齐**（[[basic.align]]）。

`reinterpret_cast<T*>(p)` 只改变指针的**类型**，三个问题一个都不回答。合法的双关手段，本质上都是"在某一关上给出肯定答案"的工具：

| 手段 | 解决哪一关 | 一句话 |
|---|---|---|
| `char`/`unsigned char`/`std::byte` 访问 | 第 3 关 | 字节类型可以访问任何对象 |
| 有/无符号对应类型访问 | 第 3 关 | `int` ↔ `unsigned` 互相访问 |
| 指针可互转 | 第 2 关 | 标准布局类与首成员、union 与成员之间 `reinterpret_cast` 会改变指向 |
| `memcpy` / `std::bit_cast` | 绕过全部 | 复制字节到一个**新的、正确类型**的对象 |
| `std::start_lifetime_as` | 第 1、2 关 | 原地创建对象、保留字节、返回指向它的指针 |
| `std::launder` | 第 2 关 | 对象已存在时，取得指向它的指针 |
| `-fno-strict-aliasing` | 第 3 关（编译器扩展） | 编译器承诺不利用别名规则优化 |

## 严格别名：type-accessible 规则

[[basic.lval#11]] 是整个话题的核心：

!!! std
    An object of dynamic type Tobj is type-accessible through a glvalue of type Tref if Tref is similar to: Tobj, a type that is the signed or unsigned type corresponding to Tobj, or a char, unsigned char, or std::byte type.

    动态类型为 Tobj 的对象，可以通过类型与以下之一**相似**的 glvalue 访问：Tobj 本身；Tobj 对应的有/无符号类型；`char`、`unsigned char` 或 `std::byte`。

通过不满足条件的 glvalue **访问**（读或写，[[defns.access]]）对象的存储值，是 UB。逐项解读、`signed char`/`char8_t`/`int8_t` 不在豁免之列等细节见 [[basic.lval]]。这里关心的是**后果**：这条规则授权编译器做**基于类型的别名分析**（TBAA）——`int*` 和 `float*` 不可能指向同一个对象，所以通过 `float*` 写入不会改变 `*int_ptr` 的值。

### 一次真实的错误优化

```cpp run title="tbaa.cpp" ub
#include <cstdio>
[[gnu::noinline]] int store_and_read(int* i, float* f) {
  *i = 1;
  *f = 2.0f;        // 编译器：float 左值不可能改写 int 对象
  return *i;        // 于是直接返回常量 1
}
int main() {
  int x = 0;
  int r = store_and_read(&x, reinterpret_cast<float*>(&x));   // UB: 经 float 左值访问 int 对象
  std::printf("r = %d, x = %d\n", r, x);
}
```

本机 Clang 23（Apple arm64）的结果：

```text
-O0                          r = 1073741824, x = 1073741824
-O2                          r = 1, x = 1073741824
-O2 -fno-strict-aliasing     r = 1073741824, x = 1073741824
```

`-O2` 下 `store_and_read` 被编译成"存 1、存 `0x40000000`、**返回常量 1**"：

```text
__Z14store_and_readPiPf:
	mov	w8, #1
	str	w8, [x0]
	mov	w8, #1073741824
	str	w8, [x1]
	mov	w0, #1          ; 不重新加载 *i
	ret
```

同一个变量 `x`，函数返回值说它是 `1`，内存里却是 `2.0f` 的位模式——这正是"UB 让程序前后矛盾"的典型样子。

!!! impl "谁能抓住它"
    - **UBSan 和 ASan 都抓不住**：用 `-fsanitize=address,undefined` 编译上例，程序安静地输出 `r = 1073741824`（插桩恰好抑制了这次优化），没有任何报告。
    - **TypeSanitizer**（`-fsanitize=type`，近几个版本的 Clang 才提供）是专门的检测器。本机 Clang 23 的输出：

    ```text
    ==9400==ERROR: TypeSanitizer: type-aliasing-violation on address 0x00016f20674c (pc ...)
    WRITE of size 4 at 0x00016f20674c with type float accesses an existing object of type int
        #0 0x000100bffd5c in store_and_read(int*, float*)+0x54 (alt:arm64+0x100007d5c)
    ```

    它在运行时跟踪每块内存的"有效类型"，与 [[basic.lval#11]] 的思路一致，但开销较大，适合测试而非生产。

### `-fno-strict-aliasing`：它到底改变了什么

GCC 和 Clang 的 `-fno-strict-aliasing` 关闭 TBAA：编译器不再假设不同类型的指针不重叠。Linux 内核等大量依赖指针双关的 C 代码库都这样编译。

从标准的角度看，这是一个**合规的扩展**（[[intro.compliance.general#11]]）：它给本来未定义的行为赋予了定义，不改变任何良构程序的行为。但要清楚它的边界：

- 它只处理**第 3 关**（访问规则）。对象不存在（第 1 关）、指针不指向它（第 2 关）、**未对齐**、读取联合体的非活跃成员、指针算术越出数组（[[expr.add#6]]）——这些仍然是 UB，编译器仍可能基于其他推理利用它们。
- 它不影响**常量求值**：`constexpr` 里 `reinterpret_cast` 根本不允许出现（[[expr.const.core#2]] ¶2.16）。
- 它让代码**不可移植**：别人的编译选项、单个 TU 的 LTO 合并、换一个编译器，都可能让依赖它的代码重新出错。

把 `-fno-strict-aliasing` 当作给遗留代码的安全网，而不是写新代码的许可。

## union 双关：C 合法，C++ UB

```cpp ub
#include <cstdint>
union U { float f; std::uint32_t u; };
std::uint32_t bits_of(float x) {
  U v;
  v.f = x;
  return v.u;     // C：OK，按 uint32_t 重新解释字节
                  // C++：UB，读取不在生命周期内的对象
}
```

在 C++ 中，联合体同一时刻至多有一个**活跃成员**（[[class.union#2]]）；`v.f = 1.0f` 使 `f` 活跃，`u` 的生命周期并未开始。读取 `v.u` 就是访问一个不在生命周期内的对象（[[basic.life#8]] ¶8.1）。唯一的特例是**公共初始序列**：几个标准布局结构体成员共享开头若干成员时，可以通过任一个结构体检查这段公共部分（[[class.mem]]）。

GCC 在文档中把"通过联合体成员访问表达式读取非活跃成员"列为扩展并保证其结果；Clang 实践中行为一致。但这个扩展**很窄**——只覆盖直接写 `u.member` 的情形，一旦取了成员地址再经由指针访问，就又回到了严格别名的领地：

```cpp run title="union-pun.cpp" ub
#include <cstdio>
union U { int i; float f; };
[[gnu::noinline]] int direct(U& u) {
  u.i = 1;
  u.f = 2.0f;          // 经联合体成员访问表达式写入
  return u.i;          // C++：读非活跃成员，UB；扩展语义：得到 2.0f 的位模式
}
[[gnu::noinline]] int via_ptr(int* ip, float* fp) {
  *ip = 1;
  *fp = 2.0f;          // 指针已"脱离"联合体
  return *ip;
}
int main() {
  U u;
  std::printf("%d\n", direct(u));
  std::printf("%d\n", via_ptr(&u.i, &u.f));
}
```

本机 Clang 23 `-O2` 输出 `1073741824` 和 `1`：第一个函数按扩展语义"正常"工作，第二个函数被 TBAA 优化成返回常量 `1`。两者在 C++ 标准下都是 UB。

在常量求值中，读取非活跃成员**必须**被诊断（[[expr.const.core#2]] ¶2.11）：

```cpp run title="union-constexpr.cpp" error
#include <cstdint>
union U { float f; std::uint32_t u; };
constexpr std::uint32_t via_union(float x) { U v{.f = x}; return v.u; }
static_assert(via_union(1.0f) == 0x3f800000);
// error: read of member 'u' of union with active member 'f' is not allowed in a constant expression
```

## `reinterpret_cast`：只改类型，几乎不改指向

对象指针之间的 `reinterpret_cast<T*>(p)` 被定义为 `static_cast<T*>(static_cast<void*>(p))`（[[expr.reinterpret.cast#7]]）。而从 `void*` 的 `static_cast`（[[expr.static.cast#12]]）只在一种情况下改变指针的**指向**：源指针指向的对象 *a* 与某个类型相似于 `T` 的对象 *b* **指针可互转**——此时结果指向 *b*。否则，"指针值不因转换而改变"：它仍然指向原来那个对象，只是类型变了。

[[basic.compound#7]] 列出的指针可互转关系很少：

| 关系 | 例子 | `reinterpret_cast` 后指向 |
|---|---|---|
| 同一个对象 | — | 不变 |
| union 对象与其非静态数据成员 | `reinterpret_cast<float*>(&u)` | 成员 `u.f`（类型相似于目标类型的那个成员） |
| 标准布局类对象与其**首个**非静态数据成员 | `reinterpret_cast<int*>(&hdr)` | `hdr.first` |
| 标准布局类对象与其**任一基类子对象** | `reinterpret_cast<Base*>(&derived)` | 基类子对象 |
| 以上关系的传递 | union → 成员 → 该成员的首成员 | 最终对象 |
| ~~数组与其首元素~~ | 注 7：**不是**指针可互转的，尽管地址相同 | 不变 |

除这些之外，`reinterpret_cast` 得到的是一个"类型为 `T*`、但指向别的类型对象"的指针。解引用它能否合法访问，就全看第 3 关：只有当 `T` 是字节类型、或对应的有/无符号类型时才行。

### 常见陷阱

**陷阱 1：把字节缓冲区当结构体**

```cpp run title="packet.cpp" ub
#include <cstdint>
#include <cstdio>
#include <cstring>
std::uint32_t read_u32_bad(const unsigned char* p) {
  return *reinterpret_cast<const std::uint32_t*>(p);     // UB：那里没有 uint32_t 对象（且可能未对齐）
}
std::uint32_t read_u32_good(const unsigned char* p) {
  std::uint32_t v;
  std::memcpy(&v, p, sizeof v);                           // OK：任何对齐、任何来源
  return v;
}
int main() {
  alignas(4) unsigned char packet[8] = {0, 1, 0, 0, 0, 0, 0, 0};
  std::printf("%u\n", read_u32_good(packet + 1));
  std::printf("%u\n", read_u32_bad(packet + 1));
}
```

坏版本同时违反两条规则：那里没有 `uint32_t` 对象（第 1、2 关），并且地址未按 4 对齐。后者 UBSan 能报告，前者没有任何 sanitizer 能报告：

```text
packet.cpp:5:10: runtime error: load of misaligned address 0x00016b9d6641 for type 'const std::uint32_t' (aka 'const unsigned int'), which requires 4 byte alignment
```

ARM64 和 x86-64 硬件都容忍普通的未对齐加载，所以这类代码"在我机器上一直没问题"——直到编译器把它向量化成要求对齐的 SIMD 指令，或移植到严格对齐的平台。

**陷阱 2：双关指针上做算术**

```cpp
int arr[5] = {1, 2, 3, 4, 5};
unsigned* p = reinterpret_cast<unsigned*>(arr + 1);
unsigned k = *p;          // OK：int 对象可经由 unsigned 左值访问
unsigned* q = p + 1;      // UB：p 指向 int 数组元素，unsigned 与 int 不相似（[expr.add]/6）
```

访问规则允许"用 `unsigned` 读一个 `int`"，但指针算术规则要求指针类型与**数组元素类型**相似。所以"把 `int[]` 当 `unsigned[]` 遍历"按字面是 UB——即使每一次单独的读取都合法。（这是 [[expr.add]] 的标准例子。）

**陷阱 3：逐字节遍历对象表示**

`reinterpret_cast<const unsigned char*>(&obj)[k]` 是序列化、哈希的基本操作。按 [[expr.add]] 的字面，`k > 1` 时它同样是 UB：这个指针指向的是 `obj` 本身，不是某个 `unsigned char` 数组的元素。这是公认的措辞缺陷，[[P1839]] 试图为对象表示提供真正的字节数组语义；在此之前，所有编译器都支持这种写法。详见 [[expr.add]]。

## `memcpy`：永远正确的老办法

`std::memcpy` / `std::memmove` 在复制之前于目标区域**隐式创建对象**（[[cstring.syn#3]]），而对于平凡可复制类型，把一个对象的底层字节复制到另一个对象中，目标就**获得**源的值表示（[[basic.types.trivial#4]]）。所以

```cpp ok
#include <cstdint>
#include <cstring>
std::uint32_t bits_of(float f) {
  std::uint32_t u;
  std::memcpy(&u, &f, sizeof u);    // u 获得 f 的值表示（1.0f → 0x3f800000）
  return u;
}
```

在三关上都没有问题：`u` 是一个真实存在的 `uint32_t` 对象，指针指向它，访问类型就是它的类型。复制不是"用错误的类型看对象"，而是"把字节搬进一个类型正确的新对象"。

担心性能是多余的。编译器认识 `memcpy`，小尺寸的复制会被内联成一次寄存器移动：

```cpp
#include <cstdint>
#include <cstring>
std::uint32_t by_memcpy(float x) { std::uint32_t r; std::memcpy(&r, &x, sizeof r); return r; }
```

```text
__Z9by_memcpyf:          ; Clang 23 -O2, arm64
	fmov	w0, s0
	ret
```

## `std::bit_cast` {{c++20}}

`std::bit_cast<To>(from)`（[[bit.cast]]，[[P0476R2]]）把 `memcpy` 惯用法变成一个返回值的函数，并且可以在**常量求值**中使用：

```cpp run title="bit-cast.cpp" ok
#include <bit>
#include <cstdint>
#include <cstring>
#include <cstdio>
constexpr std::uint32_t bits(float x) { return std::bit_cast<std::uint32_t>(x); }
static_assert(bits(1.0f) == 0x3f800000);          // 编译期可用
int main(int argc, char**) {
  float f = static_cast<float>(argc);
  std::uint32_t a = bits(f);
  std::uint32_t b; std::memcpy(&b, &f, sizeof b);
  std::printf("%x %x\n", a, b);                   // 3f800000 3f800000
}
```

约束（¶1）：`sizeof(To) == sizeof(From)`，两者都**平凡可复制**。结果的值表示逐位等于 `from` 的对象表示，并在结果中隐式创建嵌套对象。

### `bit_cast` 的两类失败

**运行期：不确定位。** 源的**填充位**、不在生命周期内的子对象（如 union 的非活跃部分）、具有不确定值的对象，产生的是**不确定**位。若某个不确定位落在结果中**非字节类型**的对象里，行为未定义；落在 `unsigned char`/`std::byte` 里则只是该字节的值不确定（[[bit.cast#3]]）。

**常量求值：`constexpr-unknown` 表示。** 编译期求值器不知道指针的数值、union 当前存的是哪种表示，所以 [[bit.cast#2]] 规定：只要 `To` 或 `From` 具有 **constexpr-unknown 表示**（[[expr.const.core#1]]：union、指针、成员指针、`volatile` 限定类型、含引用成员的类，以及含有这些的类/数组），这次 `bit_cast` 就不能出现在常量表达式中。

```cpp run title="bit-cast-constexpr.cpp" error
#include <bit>
#include <cstdint>
struct P { int* p; };
struct S { char c; int i; };       // c 之后有 3 字节填充
int g;
constexpr auto a = std::bit_cast<std::uintptr_t>(P{&g});    // error: 指针是 constexpr-unknown 表示
constexpr auto b = std::bit_cast<std::uint64_t>(S{'a', 1}); // error: 填充位进入 uint64_t 的值表示
```

本机 Clang 23 的诊断：

```text
note: bit_cast from a pointer type is not allowed in a constant expression
note: indeterminate value can only initialize an object of type 'unsigned char' or 'std::byte'; 'unsigned long long' is invalid
```

第二条在运行期同样是 UB（不确定位落进了 `uint64_t`）；常量求值只是把它变成了必须给出的诊断。

## `std::start_lifetime_as` {{c++23}}

`memcpy` 和 `bit_cast` 都要**复制**。如果字节已经在那里了——`mmap` 进来的文件、DMA 写入的缓冲区、`recv` 收到的网络包——而对象很大，复制就是纯粹的浪费。`std::start_lifetime_as<T>(p)`（[[obj.lifetime]]，[[P2590R2]]）解决这个问题：

!!! std
    Implicitly creates objects within the denoted region consisting of an object *a* of type T whose address is p, and objects nested within *a*. The object representation of *a* is the contents of the storage prior to the call.

    在 `p` 处隐式创建一个 `T` 对象 *a*（及其嵌套对象），*a* 的对象表示就是调用前存储的内容；返回指向 *a* 的指针。

它一次回答了第 1、2 关：对象被创建，返回的指针指向它。要求 `T` 是隐式生存期类型、存储已分配且对齐（¶3、¶4）。还有 `start_lifetime_as_array<T>(p, n)` 版本。

与相邻工具的区别：

| | 创建对象？ | 保留字节？ | 复制？ | 返回指向新对象的指针？ |
|---|---|---|---|---|
| `std::memcpy(dst, src, n)` | 是（在 `dst`） | 是（复制来的） | 是 | 是 |
| placement new `new (p) T` | 是 | **否**（默认初始化后值不确定） | 否 | 是 |
| `std::launder(p)` | **否** | — | 否 | 是（要求对象已存在） |
| `std::start_lifetime_as<T>(p)` | 是 | 是 | 否 | 是 |

!!! impl "libc++ 尚未提供"
    截至写作时，本机 Clang 23 自带的 libc++ 没有 `std::start_lifetime_as`（头文件中查不到该名字）；libstdc++ 的支持情况请以其文档为准。C++20 起可用的等价写法是"自己 `memmove` 给自己"——`memmove` 隐式创建对象并返回指向合适的已创建对象的指针，再 `launder` 一次以防万一：

    ```cpp
    #include <cstdint>
    #include <cstring>
    #include <new>
    struct Header { std::uint32_t magic, length; };
    const Header* view_header(unsigned char* buf) {
      return std::launder(static_cast<Header*>(std::memmove(buf, buf, sizeof(Header))));
    }
    ```

    编译器认得这个自我复制：本机 Clang 23 `-O2` 把 `view_header` 编译成单条 `ret`——零开销。

## 字节数组作为对象的家

"在一块缓冲区里放对象"的标准做法是 `alignas(T) unsigned char buf[sizeof(T)]` 或 `std::byte` 数组，再用 placement new。这里有两条来自 [[intro.object]] 的规则：

- **提供存储**（[[intro.object#3]]）：只有 `unsigned char` 和 `std::byte` 数组能为新建的完整对象"提供存储"，数组自身的生命周期不受影响。`char` 数组**不在清单里**：在 `char` 数组里建对象是复用存储，被覆盖的 `char` 元素的生命周期结束。
- **隐式创建**（[[intro.object#16]]）：`unsigned char`/`std::byte` 数组的生命周期开始时就隐式创建对象。这意味着 `alignas(Header) unsigned char buf[64]; recv(fd, buf, 64, 0);` 之后，buf 里"可以"已经有一个 `Header`——但你从 `buf` 退化来的指针**不指向它**，需要 `std::launder`（这是第 2 关的问题，详见 [[topics/object-model]] 谜题 3）。

```cpp run title="placement.cpp" ok
#include <cstddef>
#include <new>
#include <string>
int main() {
  alignas(std::string) std::byte storage[sizeof(std::string)];
  std::string* s = ::new (storage) std::string("pun-free");   // 使用 placement new 的返回值
  bool ok = s->size() == 8;
  s->~basic_string();
  return ok ? 0 : 1;
}
```

## 常量求值中的类型双关

编译期求值器是一台"严格模式"的抽象机，它会拒绝绝大多数双关手段：

| 手段 | 能否用于常量表达式 | 依据 |
|---|---|---|
| `reinterpret_cast` | 不能 | [[expr.const.core#2]] ¶2.16 |
| union 读非活跃成员 | 不能（必须诊断） | ¶2.11 |
| `static_cast<T*>(void_ptr)` | C++26 起可以，前提是确实指向类型相似于 `T` 的对象 | ¶2.15（[[P2738R1]]） |
| `memcpy` | 不能（不是 constexpr 函数） | ¶2.3 |
| `std::bit_cast` | 可以，除非涉及 constexpr-unknown 表示 | [[bit.cast#2]] |
| 隐式对象创建 | 不发生 | [[intro.object#16]] |

所以 `std::bit_cast` 是唯一既能在编译期、又能在运行期使用的通用双关手段。

## 决策表：我想……

| 我想…… | 用 | 不要用 |
|---|---|---|
| 看 `float`/`double` 的位模式 | `std::bit_cast<std::uint32_t>(f)` | union、`*(uint32_t*)&f` |
| 从字节流里读一个整数 | `memcpy` 到局部变量（再处理字节序） | `*reinterpret_cast<uint32_t*>(p)` |
| 把一大块已有字节当结构体用（不复制） | `std::start_lifetime_as<T>`；C++20：`memmove` 自身 + `launder` | `reinterpret_cast<T*>(buf)` |
| 逐字节检查/哈希任意对象 | `reinterpret_cast<const unsigned char*>` 或 `std::byte*`；或 `bit_cast` 到 `std::array<std::byte, N>` | `std::int8_t*`、`char8_t*` |
| 在缓冲区里放对象 | `alignas(T) std::byte buf[N]` + placement new，**保存返回值** | `char buf[N]` 不对齐 |
| 带标签的多类型存储 | `std::variant`；或 union + 显式切换活跃成员 | 写一个成员读另一个 |
| 有/无符号互看 | 直接经由对应类型的 glvalue 访问（合法） | — |
| 访问 C 风格"结构体头部" | 标准布局 + 首成员指针可互转 | 非标准布局类型上的同样写法 |

## 思考题

!!! question "1"
    `std::uint8_t` 在主流平台上是 `unsigned char` 的别名。那么 `reinterpret_cast<std::uint8_t*>(&obj)[0]` 合法吗？换成 `std::int8_t` 呢？

<details markdown="1">
<summary>答案</summary>

前者在 `uint8_t` 是 `unsigned char` 的 typedef 时合法——typedef 不引入新类型，所以它就是 `unsigned char` glvalue，满足 [[basic.lval#11]] ¶11.3。但标准没有要求 `uint8_t` 必须是 `unsigned char`（它可以是扩展整数类型），所以这是**可移植性依赖于实现**的写法。`std::int8_t` 通常是 `signed char`，而 `signed char` **不在**豁免清单里：只能访问 `signed char` 或 `unsigned char` 对象（经由 ¶11.1、¶11.2），访问 `float` 就是 UB。
</details>

!!! question "2"
    下面哪一行开始出问题？

    ```cpp
    struct A { int x; };
    struct B { int y; };
    A a{1};
    B* pb = reinterpret_cast<B*>(&a);
    int* py = &pb->y;
    int v = *py;
    ```

<details markdown="1">
<summary>答案</summary>

`pb` 的值仍指向 `a`（`A` 与 `B` 不是指针可互转的对象，[[expr.static.cast#12]]）。`pb->y` 是一次成员访问，而 `*pb` 的结果是一个类型为 `A`、与 `B` 不相似的对象——[[expr.ref#10]] 明确规定这种情形是 UB（标准例子正是 `reinterpret_cast<B&>(d).j`）。所以**第五行**（形成 `pb->y`）就已经是 UB，不必等到第六行的读取。很多人以为"`A` 和 `B` 布局完全相同，读 `int` 访问的又是 `int` 对象，所以没问题"——布局兼容在 C++ 里只在 union 的公共初始序列中有意义。
</details>

!!! question "3"
    `std::bit_cast<std::array<unsigned char, 8>>(S{'a', 1})`（`S` 同上文，含 3 字节填充）在运行期合法吗？能用来初始化一个 `constexpr` 变量吗？

<details markdown="1">
<summary>答案</summary>

运行期**合法**：填充位产生的不确定位全部落在 `unsigned char` 元素里，按 [[bit.cast#3]] ¶3.1 只是那几个元素具有不确定值，不是 UB（但之后读取它们的值仍受 [[basic.indet]] 约束）。常量求值中 `bit_cast` 本身也可以进行，但结果含有不确定值，不能作为 `constexpr` 变量的初始值——常量表达式的结果不允许含不确定值。本机 Clang 23 对此报"subobject ... is not initialized"。
</details>

## 小结

!!! summary
    - 类型双关要过**三关**：对象存在、指针指向它、访问类型被允许。`reinterpret_cast` 一关也不过；它只在指针可互转时改变指向。
    - **严格别名**授权 TBAA，Clang `-O2` 会真实地利用它（上文的 `r = 1`）。UBSan/ASan 抓不住，TypeSanitizer 可以。`-fno-strict-aliasing` 是合规扩展，只修补第 3 关。
    - **union 双关在 C++ 中是 UB**；GCC/Clang 的扩展只覆盖直接的成员访问表达式，常量求值中必被诊断。
    - **复制字节**（`memcpy`、`std::bit_cast`）总是正确且零开销；`bit_cast` 还能在编译期使用，但拒绝指针、union 等 constexpr-unknown 表示。
    - **原地解读已有字节**用 `std::start_lifetime_as`（libc++ 尚缺，可用 `memmove` 自身 + `launder` 替代）。
    - 放对象的缓冲区用 `unsigned char`/`std::byte` 数组，并**保存 placement new 的返回值**。
