---
title: 类型双关的合法与非法
summary: 把一块字节当作另一种类型来读，在 C++ 里什么时候合法；严格别名、union、reinterpret_cast、memcpy、std::bit_cast 和 std::start_lifetime_as 各自解决了什么问题。
status: done
order: 14
since: c++98
papers: P0476R2, P2590R2, P0593R6, P2738R1
related: basic.lval, intro.object, basic.compound, expr.reinterpret.cast, expr.static.cast, class.union, bit.cast, obj.lifetime, basic.types.trivial, expr.add, expr.const.core, topics/object-model, topics/casts, topics/undefined-behavior
tags: 类型双关, 严格别名, bit_cast, 对象模型, UB, 专题
updated: 2026-10-19
---

!!! tldr
    - 通过一种类型的指针或引用读写另一种类型的对象，只有目标是字节类型（`char`、`unsigned char`、`std::byte`）或对应的有/无符号类型时才合法；其余都是 UB，Clang `-O2` 会据此做出可见的错误优化。
    - `reinterpret_cast<T*>(p)` 只改变指针的类型，几乎从不改变它指向哪个对象；union 读非活跃成员在 C++ 中是 UB。
    - 把字节复制到一个新的、类型正确的对象（`std::memcpy`、C++20 的 `std::bit_cast`）总是正确的，编译器会把它优化成一次寄存器移动。
    - 不想复制时，用 C++23 的 `std::start_lifetime_as<T>(p)` 在原地创建对象并保留字节。
    - 常量求值中，`std::bit_cast` 是唯一可用的通用双关手段，但它不接受指针、union 等类型。

## 什么是类型双关

**类型双关**（type punning）指用一种类型去解读另一种类型对象的字节：把 `float` 的位模式当 `uint32_t` 看，把网络包的字节当结构体看，把 `int` 数组当 `unsigned` 数组遍历。C 程序员做这件事的工具是指针转换和 union。在 C++ 中，这两种工具在大多数情况下都是 UB。

判断一次双关是否合法，要依次回答三个问题，它们分属对象模型的不同层次（见 [[topics/object-model]]）：

1. 对象存在吗？那个地址上有没有一个生命周期内的 `T` 对象（[[intro.object]]、[[basic.life]]）。
2. 指针指向它吗？手里的 `T*` 的值是指向那个 `T` 对象，还是仍然指向原来的对象（[[basic.compound#7]]、[[expr.static.cast#12]]）。
3. 允许这样访问吗？通过 `T` 类型的 glvalue（指称一个对象的表达式，见 [[topics/value-categories]]）读写那个对象，是否满足访问规则（[[basic.lval#11]]）。

此外还有对齐这个物理前提（[[basic.align]]）。

`reinterpret_cast<T*>(p)` 一个问题也不回答。合法的双关手段，都是在某个问题上给出肯定答案的工具：

| 手段 | 解决哪个问题 | 作用 |
|---|---|---|
| 通过 `char`、`unsigned char`、`std::byte` 访问 | 访问 | 字节类型可以访问任何对象 |
| 通过对应的有/无符号类型访问 | 访问 | `int` 与 `unsigned` 可以互相访问 |
| 指针可互转 | 指向 | 标准布局类与首成员、union 与成员之间，`reinterpret_cast` 会改变指向 |
| `memcpy`、`std::bit_cast` | 全部绕过 | 把字节复制到一个新的、类型正确的对象 |
| `std::start_lifetime_as` | 存在、指向 | 原地创建对象，保留字节，返回指向它的指针 |
| `std::launder` | 指向 | 对象已经存在时，取得指向它的指针 |
| `-fno-strict-aliasing` | 访问（编译器扩展） | 编译器承诺不利用访问规则做优化 |

## 严格别名

### 一次真实的错误优化

```cpp run title="tbaa.cpp" ub
#include <cstdio>
[[gnu::noinline]] int store_and_read(int* i, float* f) {
  *i = 1;
  *f = 2.0f;        // 编译器认为 float 左值不可能改写 int 对象
  return *i;        // 于是直接返回常量 1
}
int main() {
  int x = 0;
  int r = store_and_read(&x, reinterpret_cast<float*>(&x));   // UB: 经 float 左值访问 int 对象
  std::printf("r = %d, x = %d\n", r, x);
}
```

本机 Clang 23（arm64）的结果：

```text
-O0                          r = 1073741824, x = 1073741824
-O2                          r = 1, x = 1073741824
-O2 -fno-strict-aliasing     r = 1073741824, x = 1073741824
```

`-O2` 下 `store_and_read` 存入 1，再存入 `0x40000000`，然后不重新加载 `*i`，直接返回常量 1：

```text
__Z14store_and_readPiPf:
	mov	w8, #1
	str	w8, [x0]
	mov	w8, #1073741824
	str	w8, [x1]
	mov	w0, #1          ; 不重新加载 *i
	ret
```

同一个变量 `x`，函数的返回值说它是 1，内存里却是 `2.0f` 的位模式。

### 访问规则（[basic.lval]/11）

编译器这样做的依据是 [[basic.lval#11]]：

!!! std
    An object of dynamic type Tobj is type-accessible through a glvalue of type Tref if Tref is similar to: Tobj, a type that is the signed or unsigned type corresponding to Tobj, or a char, unsigned char, or std::byte type.

对象的动态类型（它实际是什么类型的对象）为 `Tobj` 时，只能通过类型与下面之一相似的 glvalue 访问它：`Tobj` 本身；`Tobj` 对应的有/无符号类型；`char`、`unsigned char` 或 `std::byte`。**相似**（similar）大致是忽略各层 cv 限定后相同（[[conv.qual]]）。通过其他类型的 glvalue 读或写（[[defns.access]]）对象的存储值，行为未定义。逐项的细节，例如 `signed char`、`char8_t`、`int8_t` 不在豁免之列，见 [[basic.lval]]。

这条规则俗称**严格别名**（strict aliasing）。它允许编译器做**基于类型的别名分析**（type-based alias analysis，TBAA）：`int*` 和 `float*` 不可能指向同一个对象，所以通过 `float*` 写入不会改变 `*int_ptr` 的值。上面的错误优化就是这样来的。

!!! impl "谁能抓住它"
    UBSan 和 ASan 都抓不住。用 `-fsanitize=address,undefined` 编译上例，程序安静地输出 `r = 1073741824`（插桩恰好抑制了这次优化），没有任何报告。

    专门的检测器是 TypeSanitizer（`-fsanitize=type`，近几个版本的 Clang 才提供）。本机 Clang 23 的输出：

    ```text
    ==9400==ERROR: TypeSanitizer: type-aliasing-violation on address 0x00016f20674c (pc ...)
    WRITE of size 4 at 0x00016f20674c with type float accesses an existing object of type int
        #0 0x000100bffd5c in store_and_read(int*, float*)+0x54 (alt:arm64+0x100007d5c)
    ```

    它在运行时跟踪每块内存的有效类型，思路与 [[basic.lval#11]] 一致，开销较大，适合测试而不适合生产。

### -fno-strict-aliasing 改变了什么

GCC 和 Clang 的 `-fno-strict-aliasing` 关闭 TBAA，编译器不再假设不同类型的指针不重叠。Linux 内核等大量依赖指针双关的 C 代码库都这样编译。

从标准的角度看，这是一个合规的扩展（[[intro.compliance.general#11]]）：它给本来未定义的行为规定了含义，不改变任何良构程序的行为。但它只处理访问规则这一个问题：

- 对象不存在、指针不指向它、地址未对齐、读 union 的非活跃成员、指针算术越出数组（[[expr.add#6]]），这些仍然是 UB，编译器仍可能基于别的推理利用它们。
- 它不影响常量求值：常量表达式里根本不允许出现 `reinterpret_cast`（[[expr.const.core#2]] ¶2.16）。
- 依赖它的代码不可移植，换一组编译选项、做 LTO、换一个编译器，都可能重新出错。

所以它适合作为遗留代码的安全网，不适合作为写新代码的依据。

## union 双关：C 中合法，C++ 中是 UB

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

C++ 的 union 同一时刻至多有一个**活跃成员**（active member），即生命周期正在进行的那个成员（[[class.union.general#2]]）。`v.f = x` 使 `f` 活跃，`u` 的生命周期没有开始，读取 `v.u` 就是访问一个不在生命周期内的对象（[[basic.life#8]] ¶8.1）。

唯一的特例是公共初始序列：几个标准布局结构体成员开头的若干成员类型相同时，可以通过任一个结构体读取这段公共部分（[[class.mem]]）。

GCC 在 `-fstrict-aliasing` 的文档中说明，通过 union 类型访问内存时允许这种双关；Clang 实际行为一致。但这个扩展只覆盖直接写 `u.member` 的情形。取了成员地址再经由指针访问，又回到了严格别名的范围：

```cpp run title="union-pun.cpp" ub
#include <cstdio>
union U { int i; float f; };
[[gnu::noinline]] int direct(U& u) {
  u.i = 1;
  u.f = 2.0f;          // 经 union 成员访问表达式写入
  return u.i;          // C++：读非活跃成员，UB；按扩展语义得到 2.0f 的位模式
}
[[gnu::noinline]] int via_ptr(int* ip, float* fp) {
  *ip = 1;
  *fp = 2.0f;          // 指针已经离开了 union
  return *ip;
}
int main() {
  U u;
  std::printf("%d\n", direct(u));
  std::printf("%d\n", via_ptr(&u.i, &u.f));
}
```

本机 Clang 23 `-O2` 输出 `1073741824` 和 `1`。第一个函数按扩展语义工作，第二个函数被 TBAA 优化成返回常量 1。按标准，两者都是 UB。

在常量求值中，读非活跃成员必须诊断（[[expr.const.core#2]] ¶2.11）：

```cpp run title="union-constexpr.cpp" error
#include <cstdint>
union U { float f; std::uint32_t u; };
constexpr std::uint32_t via_union(float x) { U v{.f = x}; return v.u; }
static_assert(via_union(1.0f) == 0x3f800000);
// error: read of member 'u' of union with active member 'f' is not allowed in a constant expression
```

## reinterpret_cast：只改类型，几乎不改指向

对象指针之间的 `reinterpret_cast<T*>(p)` 定义为 `static_cast<T*>(static_cast<void*>(p))`（[[expr.reinterpret.cast#7]]）。从 `void*` 出发的 `static_cast` 只在一种情况下改变指针指向哪个对象：原指针指向的对象 *a*，与某个类型相似于 `T` 的对象 *b* **指针可互转**（pointer-interconvertible），这时结果指向 *b*。其他情况下，指针值不变，它仍然指向原来的对象，只是类型变了（[[expr.static.cast#12]]）。

[[basic.compound#7]] 列出的指针可互转关系很少：

| 关系 | 例子 | 转换后指向 |
|---|---|---|
| 同一个对象 | | 不变 |
| union 对象与它的非静态数据成员 | `reinterpret_cast<float*>(&u)` | 类型相似于目标类型的那个成员 |
| 标准布局类对象与它的首个非静态数据成员 | `reinterpret_cast<int*>(&hdr)` | `hdr` 的首成员 |
| 标准布局类对象与它的任一基类子对象 | `reinterpret_cast<Base*>(&derived)` | 基类子对象 |
| 以上关系的传递 | union → 成员 → 该成员的首成员 | 最终的对象 |

注 7 特别指出，数组与它的首元素地址相同，但不是指针可互转的。

除了这些情形，`reinterpret_cast` 得到的是一个类型为 `T*`、却指向别的类型对象的指针。解引用它能否合法访问，全看访问规则：只有 `T` 是字节类型或对应的有/无符号类型时才行。

### 陷阱：把字节缓冲区当结构体

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

坏版本同时违反两条规则：那里没有 `uint32_t` 对象，地址也没有按 4 对齐。UBSan 能报告后者，前者没有任何 sanitizer 能报告：

```text
packet.cpp:5:10: runtime error: load of misaligned address 0x00016b9d6641 for type 'const std::uint32_t' (aka 'const unsigned int'), which requires 4 byte alignment
```

ARM64 和 x86-64 硬件都容忍普通的未对齐加载，所以这类代码常常一直看不出问题，直到编译器把它向量化成要求对齐的 SIMD 指令，或者移植到严格对齐的平台。

### 陷阱：在双关指针上做算术

```cpp
int arr[5] = {1, 2, 3, 4, 5};
unsigned* p = reinterpret_cast<unsigned*>(arr + 1);
unsigned k = *p;          // OK：int 对象可以经由 unsigned 左值访问
unsigned* q = p + 1;      // UB：p 指向 int 数组的元素，unsigned 与 int 不相似
```

访问规则允许用 `unsigned` 读一个 `int`，但指针算术要求指针类型与数组元素类型相似（[[expr.add#6]]，这正是那里的标准例子）。所以把 `int[]` 当 `unsigned[]` 遍历，即使每一次单独的读取都合法，按字面也是 UB。

### 陷阱：逐字节遍历对象表示

`reinterpret_cast<const unsigned char*>(&obj)[k]` 是序列化和哈希的基本操作。但这个指针指向的是 `obj` 本身，不是某个 `unsigned char` 数组的元素；为了指针算术，`obj` 被看作只有一个元素、元素类型为 `obj` 的类型的数组。`unsigned char` 与这个元素类型不相似，所以按 [[expr.add#6]] 的字面，在这个指针上做加法就已经是 UB。

这是公认的措辞缺陷，[[P1839]] 试图给对象表示提供真正的字节数组语义。在此之前，所有编译器都支持这种写法。

## memcpy：复制到一个类型正确的对象

```cpp ok
#include <cstdint>
#include <cstring>
std::uint32_t bits_of(float f) {
  std::uint32_t u;
  std::memcpy(&u, &f, sizeof u);    // u 获得 f 的值表示（1.0f → 0x3f800000）
  return u;
}
```

`std::memcpy` 和 `std::memmove` 在复制前于目标区域隐式创建对象（[[cstring.syn#3]]）。对平凡可复制类型，把一个对象的字节复制到另一个对象里，目标就获得源的值（[[basic.types.trivial#4]]）。

这样做三个问题都没有障碍：`u` 是真实存在的 `uint32_t` 对象，指针指向它，访问类型就是它自己的类型。复制并不是用错误的类型看一个对象，而是把字节搬进一个类型正确的新对象。

编译器认识 `memcpy`，小尺寸的复制会内联成一次寄存器移动，不必担心性能：

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

## std::bit_cast {{c++20}}

`std::bit_cast<To>(from)`（[[bit.cast]]，[[P0476R2]]）把 `memcpy` 惯用法写成一个返回值的函数，而且可以在常量求值中使用：

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

它要求 `sizeof(To) == sizeof(From)`，并且两者都是平凡可复制类型（[[bit.cast#1]]）。结果的值表示逐位等于 `from` 的对象表示，结果里嵌套的对象被隐式创建。

### 两类失败

运行期的问题是不确定位（[[bit.cast#3]]）。源的填充位、不在生命周期内的子对象（如 union 的非活跃部分）、本身具有不确定值的对象，都产生不确定位。不确定位落进结果中非字节类型的对象时，行为未定义；落进 `unsigned char` 或 `std::byte` 时，只是那个字节的值不确定（¶3.1）。

常量求值的限制是 constexpr-unknown 表示（[[bit.cast#2]]）。编译期求值器不知道指针的数值，也不知道 union 里当前存的是哪种表示，所以只要 `To` 或 `From` 具有 **constexpr-unknown 表示**，这次 `bit_cast` 就不能出现在常量表达式中。[[expr.const.core#1]] 列出了这类类型：union、`std::meta::info`、指针和成员指针、volatile 限定的类型、含引用成员的类，以及含有这些类型的基类或成员的类型。

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

第二行在运行期同样是 UB，因为不确定位落进了 `uint64_t`。常量求值只是把它变成了必须给出的诊断。

## std::start_lifetime_as {{c++23}}

`memcpy` 和 `bit_cast` 都要复制。如果字节已经在那里，例如 `mmap` 进来的文件、DMA 写入的缓冲区、`recv` 收到的网络包，而对象又很大，复制就是浪费。`std::start_lifetime_as<T>(p)`（[[obj.lifetime]]，[[P2590R2]]）解决这个问题：

!!! std
    Implicitly creates objects within the denoted region consisting of an object *a* of type T whose address is p, and objects nested within *a*. The object representation of *a* is the contents of the storage prior to the call.

它在 `p` 处创建一个 `T` 对象（以及嵌套在其中的对象），对象表示就是调用前存储里的内容，然后返回指向它的指针。对象存在、指针指向它，两个问题一次解决。它要求 `T` 是隐式生存期类型（标量、数组、平凡的类等，[[basic.types.general]]），存储已分配且对齐（[[obj.lifetime#3]]、[[obj.lifetime#4]]）。另有 `start_lifetime_as_array<T>(p, n)`。

它与相近的工具区别如下：

| | 创建对象 | 保留原有字节 | 复制 | 返回指向新对象的指针 |
|---|---|---|---|---|
| `std::memcpy(dst, src, n)` | 是（在 `dst`） | 是（复制来的） | 是 | 是 |
| placement new `new (p) T` | 是 | 否，默认初始化后值不确定 | 否 | 是 |
| `std::launder(p)` | 否 | | 否 | 是，要求对象已存在 |
| `std::start_lifetime_as<T>(p)` | 是 | 是 | 否 | 是 |

!!! impl "libc++ 尚未提供"
    截至写作时，本机 Clang 23 自带的 libc++ 里找不到 `std::start_lifetime_as`，libstdc++ 的支持情况以其文档为准。C++20 起可用的替代写法是让 `memmove` 把缓冲区复制给自己：`memmove` 隐式创建对象，并返回指向合适的已创建对象的指针，再 `launder` 一次以防万一：

    ```cpp
    #include <cstdint>
    #include <cstring>
    #include <new>
    struct Header { std::uint32_t magic, length; };
    const Header* view_header(unsigned char* buf) {
      return std::launder(static_cast<Header*>(std::memmove(buf, buf, sizeof(Header))));
    }
    ```

    编译器认得这种自我复制，本机 Clang 23 `-O2` 把 `view_header` 编译成一条 `ret`。

## 在字节数组里放对象

在缓冲区里放对象的标准写法是 `alignas(T) unsigned char buf[sizeof(T)]` 或 `std::byte` 数组，再用 placement new，并保存它的返回值：

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

这里涉及对象模型的两条规则：

- 只有 `unsigned char` 和 `std::byte` 数组能为新建的完整对象**提供存储**（provide storage），数组自身的生命周期不受影响（[[intro.object#3]]）。`char` 数组不在其列：在 `char` 数组里建对象是复用存储，被覆盖的 `char` 元素的生命周期随之结束。
- `unsigned char` 或 `std::byte` 数组的生命周期开始时，会在其中隐式创建对象（[[intro.object#16]]）。所以 `alignas(Header) unsigned char buf[64]; recv(fd, buf, 64, 0);` 之后，`buf` 里可以已经有一个 `Header`。但从 `buf` 退化来的指针不指向它，需要 `std::launder`（见 [[topics/object-model]] 谜题 5）。

## 常量求值中的双关

编译期求值器会拒绝绝大多数双关手段：

| 手段 | 能否用于常量表达式 | 依据 |
|---|---|---|
| `reinterpret_cast` | 不能 | [[expr.const.core#2]] ¶2.16 |
| union 读非活跃成员 | 不能，必须诊断 | ¶2.11 |
| `static_cast<T*>(void_ptr)` | C++26 起可以，前提是确实指向类型相似于 `T` 的对象 | ¶2.15（[[P2738R1]]） |
| `memcpy` | 不能，它不是 constexpr 函数 | ¶2.3 |
| `std::bit_cast` | 可以，除非涉及 constexpr-unknown 表示 | [[bit.cast#2]] |
| 隐式创建对象 | 不发生 | [[intro.object#16]] |

所以 `std::bit_cast` 是唯一既能在编译期、又能在运行期使用的通用双关手段。

## 按需求选择

| 需求 | 用 | 不要用 |
|---|---|---|
| 看 `float`/`double` 的位模式 | `std::bit_cast<std::uint32_t>(f)` | union、`*(uint32_t*)&f` |
| 从字节流里读一个整数 | `memcpy` 到局部变量，再处理字节序 | `*reinterpret_cast<uint32_t*>(p)` |
| 把一大块已有字节当结构体用，不复制 | `std::start_lifetime_as<T>`；C++20 用 `memmove` 自身加 `launder` | `reinterpret_cast<T*>(buf)` |
| 逐字节检查或哈希任意对象 | `const unsigned char*` 或 `const std::byte*`；或 `bit_cast` 到 `std::array<std::byte, N>` | `std::int8_t*`、`char8_t*` |
| 在缓冲区里放对象 | `alignas(T) std::byte buf[N]` 加 placement new，保存返回值 | 不对齐的 `char buf[N]` |
| 带标签的多类型存储 | `std::variant`，或 union 加显式切换活跃成员 | 写一个成员、读另一个 |
| 有符号与无符号互看 | 直接经由对应类型的 glvalue 访问，这是合法的 | |
| 访问 C 风格的结构体头部 | 标准布局类型，利用与首成员的指针可互转 | 在非标准布局类型上同样写 |

## 思考题

!!! question "思考题 1"
    `std::uint8_t` 在主流平台上是 `unsigned char` 的别名。`reinterpret_cast<std::uint8_t*>(&obj)[0]` 合法吗？换成 `std::int8_t` 呢？

<details markdown="1">
<summary>答案</summary>

`uint8_t` 是 `unsigned char` 的 typedef 时合法。typedef 不引入新类型，这就是一个 `unsigned char` glvalue，满足 [[basic.lval#11]] ¶11.3。但标准不要求 `uint8_t` 必须是 `unsigned char`，它也可以是扩展整数类型，所以这种写法的可移植性依赖于实现。

`std::int8_t` 通常是 `signed char`，而 `signed char` 不在豁免之列。它只能访问 `signed char` 或 `unsigned char` 对象（经由 ¶11.1、¶11.2），用它访问 `float` 是 UB。（下标 `[0]` 本身的算术问题见上文逐字节遍历一节。）
</details>

!!! question "思考题 2"
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

`A` 与 `B` 的对象不是指针可互转的，所以 `pb` 的值仍然指向 `a`（[[expr.static.cast#12]]）。`pb->y` 是一次成员访问，而 `*pb` 指称的是一个 `A` 对象，`A` 与 `B` 不相似。[[expr.ref#10]] 明确规定这种情形是 UB，它的标准例子正是 `reinterpret_cast<B&>(d).j`。

所以第五行形成 `pb->y` 时就已经是 UB，不必等到第六行读取。`A` 和 `B` 布局完全相同这一点帮不上忙：布局兼容在 C++ 里只在 union 的公共初始序列中有意义。
</details>

!!! question "思考题 3"
    `std::bit_cast<std::array<unsigned char, 8>>(S{'a', 1})`（`S` 同上文，含 3 字节填充）在运行期合法吗？能用来初始化一个 `constexpr` 变量吗？

<details markdown="1">
<summary>答案</summary>

运行期合法。填充位产生的不确定位全部落在 `unsigned char` 元素里，按 [[bit.cast#3]] ¶3.1，只是那几个元素具有不确定值，不是 UB。之后读取这些元素的值仍受 [[basic.indet]] 约束。

但它不能初始化 `constexpr` 变量：常量表达式的结果不能含有不确定值。本机 Clang 23 对此报 "subobject '__elems_' is not initialized"。
</details>
