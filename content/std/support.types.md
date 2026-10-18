---
title: 公共定义
summary: <cstddef> 与 <cstdlib> 中的基础类型——size_t、ptrdiff_t、nullptr_t、max_align_t、std::byte——以及 NULL 和 offsetof 宏；offsetof 只对标准布局类有保证，其余情况是有条件支持的
status: done
covers: *
related: support, basic.fundamental, conv.ptr, expr.add, expr.sizeof, basic.align, class.prop, intro.object, basic.lval, support.start.term
tags: 标准库, cstddef, offsetof, byte, size_t
updated: 2026-10-18
---

[support.types] 是整个标准库里**最底层的一块地基**：几乎所有头文件都要用到 `size_t`；`ptrdiff_t` 是指针相减的结果类型；`nullptr_t` 是 `nullptr` 的类型；`max_align_t` 给出"任何上下文都支持的最大基本对齐"；`std::byte` 是 C++17 引入的"只表示字节、不表示数字也不表示字符"的类型。它们都是由**核心语言规则**决定其性质、再由库给出名字的——所以读这一节时你会不停地跳回 [[expr.add]]、[[expr.sizeof]]、[[basic.align]]、[[class.prop]]。

本节包含五个子条款：

| 子条款 | 内容 |
|---|---|
| [cstddef.syn] | `<cstddef>` 概要：`ptrdiff_t`、`size_t`、`max_align_t`、`nullptr_t`、`byte` 及其运算、`NULL`、`offsetof` |
| [cstdlib.syn] | `<cstdlib>` 概要：`exit`/`abort` 族、`malloc` 族、数值转换、`qsort`/`bsearch`、`abs`/`div` |
| [support.types.nullptr] | `nullptr_t` 与 `NULL` |
| [support.types.layout] | `offsetof`、`ptrdiff_t`、`size_t`、`max_align_t` |
| [support.types.byteops] | `std::byte` 的位运算与 `to_integer` |

## 两个头文件概要（[cstddef.syn]、[cstdlib.syn]）

### `<cstddef>`：全部 freestanding

`<cstddef>` 的概要第一行注释就是 `// all freestanding`：这个头文件的全部内容在**独立实现**（[[g:freestanding-implementation]]，例如内核、裸机固件）中也必须提供。核心声明只有这几行：

```cpp
namespace std {
  using ptrdiff_t   = /* see below */;
  using size_t      = /* see below */;
  using max_align_t = /* see below */;
  using nullptr_t   = decltype(nullptr);
  enum class byte : unsigned char {};
  // byte 的位运算与 to_integer ……
}
#define NULL             /* see below */
#define offsetof(P, D)   /* see below */
```

¶1 规定它的内容和含义与 C 标准库的 `<stddef.h>` 相同，但有几处差别：

- **不声明 `wchar_t`**——在 C++ 里 `wchar_t` 是关键字、是内建类型（[[basic.fundamental]]），不需要也不能由库 typedef；
- **不定义 `unreachable` 宏**——C23 的 `<stddef.h>` 有 `unreachable()` 宏，C++ 用的是 `<utility>` 里的函数 `std::unreachable()`；
- **额外声明 `byte`** 及其运算；
- 以及 [support.types.nullptr]、[support.types.layout] 所述的差别（`NULL` 的可选定义、`offsetof` 的限制）。

### `<cstdlib>`：一锅大杂烩

`<cstdlib>` 对应 C 的 `<stdlib.h>`，内容非常杂：程序终止（`abort`、`exit`、`quick_exit`、`atexit`……，见 [[support.start.term]]）、C 内存分配（`malloc`、`free`、C23 新增的 `free_sized`/`free_aligned_sized`/`memalignment`，见 [[c.malloc]]）、字符串转数值（`strtol` 等）、多字节转换、`qsort`/`bsearch`（[[alg.c.library]]）、`rand`/`srand`、`abs`/`div`。

几个值得注意的细节：

- 概要用了四个**仅用于说明**（exposition only）的函数类型别名：`c-atexit-handler`（`extern "C"` 的 `void()`）与 `atexit-handler`（`extern "C++"` 的 `void()`），`c-compare-pred` 与 `compare-pred`。于是 `atexit`、`at_quick_exit`、`qsort`、`bsearch` 各有**两个重载**：一个接受 C 语言链接的函数指针，一个接受 C++ 语言链接的函数指针。这是因为按 [[dcl.link]]，语言链接是函数类型的一部分——理论上 `extern "C"` 函数与 C++ 函数的调用约定可以不同。主流实现上两者相同，编译器也不把语言链接计入类型（这是 Clang/GCC 长期存在的偏离），所以你基本感觉不到这两个重载的存在。
- `abs`、`labs`、`div` 等是 `constexpr` 的（C++23 起）。
- ¶1 说 `<cstdlib>` 不声明 `wchar_t`、`once_flag` 和 `call_once`——C23 的 `<stdlib.h>` 有 `call_once`，C++ 用 `<mutex>` 的 `std::call_once`。
- 注 1：若干函数在本文档中有额外的重载（例如 `abs` 的整数/浮点重载），但行为与 C 库相同。

## `nullptr_t` 与 `NULL`（[support.types.nullptr]）

¶1：`nullptr_t` 就是 `decltype(nullptr)` 的同义词，其性质由 [[basic.fundamental]] 和 [[conv.ptr]] 规定：它是一个独立的基本类型，不是指针类型也不是成员指针类型；`sizeof(std::nullptr_t) == sizeof(void*)`；它的 prvalue 是**空指针常量**（[[g:null-pointer-constant]]），可以转换为任何指针或成员指针类型；它能转换为 `bool`（只在直接初始化中）。

注 1 指出一个容易被忽视的事实：`nullptr` 本身是 prvalue，不能取地址；但一个类型为 `nullptr_t` 的**左值**对象是可以取地址的：

```cpp run title="nullptr-t.cpp" ok
#include <cstddef>

int main() {
    std::nullptr_t n = nullptr;
    std::nullptr_t* p = &n;      // OK：n 是左值
    int* ip = n;                 // OK：nullptr_t 的值可以转换为任何指针类型
    // auto q = &nullptr;        // error: nullptr 是 prvalue
    return (p != nullptr && ip == nullptr) ? 0 : 1;
}
```

¶2：`NULL` 是一个**由实现定义的**空指针常量，并且必须是一个**字面量**（[[lex.icon]] 或 [[lex.nullptr]]）。脚注给出了可能的定义：`nullptr`、`0`、`0L`，但**不能**是 `(void*)0`——因为在 C++ 中 `void*` 不能隐式转换为其他对象指针类型，`int* p = (void*)0;` 是非良构的。

!!! std
    The macro `NULL` is an implementation-defined null pointer constant that is a literal.

    `NULL` 宏是一个由实现定义的、作为字面量的空指针常量。

!!! impl "Clang 与 GCC 的 `__null`"
    在 C++ 模式下，Clang 的 `<stddef.h>`（`__stddef_null.h`）把 `NULL` 定义为 `__null`（MinGW/MSVC 环境下是 `0`）。`__null` 是 GCC 引入、Clang 跟进的一个特殊的整数字面量：它的类型是与指针同宽的整数（LP64 上是 `long`），但编译器知道它"其实是 NULL"，于是能对 `int x = NULL;` 这种可疑用法给出警告（Clang 的 `-Wnull-conversion`）。严格说来，标准要求 `NULL` 是"字面量"，而 `__null` 是一个编译器扩展记号，这属于实现自由——由实现定义的东西实现可以自己选。

`NULL` 是整数还是 `nullptr` 是由实现定义的，因此**对 `NULL` 做重载决议是不可移植的**：

```cpp run title="null-overload.cpp"
#include <cstddef>

int f(int)   { return 1; }
int f(char*) { return 2; }

int main() {
    // f(NULL);   // 取决于实现：NULL 为 0 → 选 f(int)；为 0L → 歧义（long→int 与 long→char* 都需要转换）；
                  //            为 __null → Clang 报歧义；为 nullptr → 选 f(char*)
    return f(nullptr);   // 总是 f(char*)：这是 nullptr 被发明出来的原因
}
```

## `offsetof`（[support.types.layout] ¶1）

`offsetof(type, member-designator)` 产生一个 `size_t` 类型的整型常量表达式：成员相对于类对象起始地址的字节偏移。¶1 在 C 语义之上加了五条 C++ 专属规则：

1. **只有标准布局类有保证**。对**非标准布局**（[[class.prop]]）的类型使用 `offsetof` 是**有条件支持**的（[[g:conditionally-supported]]）——实现可以拒绝（必须给出诊断），也可以接受并给出有意义的结果。在 C++11 之前，限制是"POD"，C++11 起放宽为标准布局，C++17 起改为"有条件支持"而非 UB。
2. **类型依赖性**：`offsetof(type, member-designator)` **永远不是**类型依赖的（结果类型总是 `size_t`）；当且仅当 *type* 是依赖类型时，它是**值依赖**的（[[temp.dep.constexpr]]）。
3. 对**静态数据成员**或**成员函数**应用 `offsetof`，结果是**未定义的**——这里说的是"结果未定义"（The result ... is undefined），实践中编译器直接报错。
4. `offsetof` 调用的操作**不得抛出异常**，且 `noexcept(offsetof(type, member-designator))` 必须为 `true`。
5. 脚注 149：即使涉及的类型**重载了一元 `operator&`**，`offsetof` 也必须正确工作——所以老式的 `((size_t)&((T*)0)->m)` 写法不符合 C++ 的要求（它本来就是对空指针做成员访问的 UB），实现必须用编译器内建（Clang/GCC 的 `__builtin_offsetof`）。

!!! std
    Use of the `offsetof` macro with a *type* other than a standard-layout class is conditionally-supported.

    对非标准布局类的 *type* 使用 `offsetof` 宏，是有条件支持的。

为什么是"标准布局"？标准布局类保证了成员的布局可以与 C 的 struct 对应（[[class.mem]] 里的"首成员与类对象指针可互相转换"、公共初始序列等）。一旦出现虚函数、虚基类、混合访问控制或多个类层次都有非静态数据成员，布局就交给 ABI 自由决定：虚基类子对象相对于派生类对象的偏移甚至**不是常量**——它取决于最终的最派生类型，只能运行时通过 vtable 查到。

```cpp run title="offsetof.cpp"
#include <cstddef>

struct S  { char c; double d; int operator&() const; };   // 重载了一元 &
struct V  { virtual ~V(); int x; };                       // 非标准布局：有虚函数
struct B  { int b; };
struct VB : virtual B { int x; };                         // 虚基类
struct M  { static int s; int f(); int arr[4]; struct { int y; } in; };

static_assert(offsetof(S, d) == alignof(double));         // OK：标准布局，operator& 不影响
static_assert(noexcept(offsetof(S, d)));                  // OK：¶1 要求为 true
constexpr auto e = offsetof(M, arr[2]);                   // OK：成员指示符可以带下标
constexpr auto g = offsetof(M, in.y);                     // OK：也可以是嵌套成员
auto v  = offsetof(V, x);    // 有条件支持：Clang 接受并给出 -Winvalid-offsetof 警告
// auto w = offsetof(VB, b); // error: Clang 拒绝"对虚基类的字段应用 offsetof"
// auto s = offsetof(M, s);  // 结果未定义：Clang 报错"no member named 's'"
// auto f = offsetof(M, f);  // 同上

template<class T> constexpr auto off = offsetof(T, b);    // 值依赖，但不是类型依赖：类型总是 size_t

int main() { (void)e; (void)g; (void)v; return off<B>; }
```

!!! impl
    Clang 的 `offsetof` 宏就是 `__builtin_offsetof(t, d)`（定义在 Clang 资源目录的 `__stddef_offsetof.h`）。对非标准布局但偏移在编译期已知的类型（例如只因有虚函数而非标准布局），Clang 接受并给出 `-Winvalid-offsetof` 警告；对虚基类成员这种偏移不是编译期常量的情形，则直接报错。这正是"有条件支持"的典型用法：实现选择支持一部分，并对不支持的部分给出诊断。

!!! pitfall "成员指示符不是任意表达式"
    *member-designator* 沿用 C 的语法：一个标识符后面可以跟 `.标识符` 或 `[常量表达式]`。`offsetof(S, d)` 中的 `d` 不是一个 C++ 表达式，而是在 *type* 中查找的成员名序列。宏参数里出现顶层逗号（如 `offsetof(std::pair<int,int>, first)`）会被预处理器切开，需要先给类型起个别名。

## `ptrdiff_t` 与 `size_t`（¶2–¶4）

¶2：`ptrdiff_t` 是一个**由实现定义的**有符号整数类型，能够容纳同一数组对象中两个下标之差（[[expr.add]]）。¶3：`size_t` 是一个**由实现定义的**无符号整数类型，大到足以容纳**任何对象**的字节大小（[[expr.sizeof]]）。

这两句话要和核心语言对照着读：

- [[expr.add]] 规定指针相减的结果类型是 `std::ptrdiff_t`，并且如果结果无法用 `ptrdiff_t` 表示，行为是未定义的。换言之，**`ptrdiff_t` 不一定能装下任意两个元素的下标差**——一个 `char` 数组如果大于 `PTRDIFF_MAX` 字节，首尾指针相减就是 UB。标准只说它"能容纳差值"，这是一个对实现的要求；实际上实现靠限制最大对象大小来满足它（例如 glibc 的 `malloc` 拒绝分配超过 `PTRDIFF_MAX` 的块）。
- [[expr.sizeof]] 规定 `sizeof` 和 `alignof` 的结果类型是 `std::size_t`。由于 `size_t` "能容纳任何对象的大小"，`sizeof` 永远不会溢出——一个大小超过 `SIZE_MAX` 的类型无法被定义（实践中编译器报"array is too large"）。

¶4 是**推荐实践**（recommended practice，非强制）：实现应当让 `ptrdiff_t` 和 `size_t` 的整数转换等级（[[conv.rank]]）不高于 `signed long`，除非需要更大的类型才能容纳所有可能值。这条建议来自 C，目的是避免 `size_t` 被定义成 `unsigned long long` 这种在 LP64 上没必要的宽类型，导致混合运算时出乎意料地提升。

| 平台 | `size_t` | `ptrdiff_t` |
|---|---|---|
| Linux/macOS x86-64、AArch64（LP64） | `unsigned long` | `long` |
| Windows x64（LLP64） | `unsigned long long` | `long long` |
| 32 位平台（ILP32） | `unsigned int`（多数） | `int` |

Windows x64 是 ¶4 所说的"需要更大的类型"的例子：`long` 只有 32 位，装不下 64 位地址空间里的对象大小。

!!! pitfall "`size_t` 与 `ptrdiff_t` 的混用"
    `for (size_t i = v.size() - 1; i >= 0; --i)` 是一个死循环：`size_t` 无符号，`i >= 0` 永真。`v.size() - 1` 在空容器上回绕成 `SIZE_MAX`。C++20 的 `std::ssize()` 返回有符号的大小（通常是 `ptrdiff_t`），正是为了这类场景。

## `max_align_t`（¶5）

!!! std
    The type `max_align_t` is a trivially copyable standard-layout type whose alignment requirement is at least as great as that of every scalar type, and whose alignment requirement is supported in every context.

    `max_align_t` 是一个可平凡复制的标准布局类型，其对齐要求至少与每个标量类型一样严格，并且该对齐要求在每种上下文中都受支持。

另外，`std::is_trivially_default_constructible_v<max_align_t>` 为 `true`。

"在每种上下文中都受支持"把它和 [[basic.align]] 联系起来：`alignof(std::max_align_t)` 就是**基本对齐**（[[g:fundamental-alignment]]）的上限。任何不超过它的对齐都是基本对齐，任何超过它的对齐都是**扩展对齐**（[[g:extended-alignment]]），而扩展对齐是否被支持、在哪些上下文中被支持，是由实现定义的。

这个值的实际意义：

- `malloc` 返回的指针保证对任何基本对齐的类型都足够对齐，即至少按 `alignof(max_align_t)` 对齐（对足够大的请求而言）。
- `operator new(size_t)` 同样只保证基本对齐；超过 `__STDCPP_DEFAULT_NEW_ALIGNMENT__` 的类型由 C++17 起的对齐版本 `operator new(size_t, align_val_t)` 处理（见 [[new.delete]]）。`__STDCPP_DEFAULT_NEW_ALIGNMENT__`（[[cpp.predefined]]）与 `alignof(max_align_t)` 是两个不同的量，前者可以更大。

```cpp run title="max-align.cpp" impl
#include <cstddef>
#include <cstdio>

int main() {
    std::printf("alignof(max_align_t) = %zu, sizeof = %zu\n",
                alignof(std::max_align_t), sizeof(std::max_align_t));
    std::printf("__STDCPP_DEFAULT_NEW_ALIGNMENT__ = %zu\n",
                static_cast<std::size_t>(__STDCPP_DEFAULT_NEW_ALIGNMENT__));
}
```

!!! impl
    Clang 的 `max_align_t` 定义在 `__stddef_max_align_t.h`：在 Apple 平台上它是 `long double` 或 `double` 的 typedef，其他平台上模仿 GCC 定义为一个包含 `long long` 与 `long double` 成员（带对齐属性）的 struct。所以在 Apple Silicon（`long double` 与 `double` 同为 64 位）上上例打印 `8, 8`；在 x86-64 Linux 上通常是 `16, 32`。这再次说明它是**由实现定义的**——永远不要把 16 硬编码进分配器里。

## `std::byte` 及其运算（[support.types.byteops]）

`std::byte` 的定义只有一行：`enum class byte : unsigned char {};`。它是一个**作用域枚举**，底层类型是 `unsigned char`，**没有任何枚举项**。这个设计（C++17）的意图是：

- 它和 `unsigned char` 一样可以**访问任何对象的存储**：[[basic.lval]] 的类型别名规则把 `std::byte` 与 `char`、`unsigned char` 一同列为可以合法访问任何对象表示的类型；[[intro.object]] 规定 `unsigned char` 和 `std::byte` 的数组可以为其他对象**提供存储**（[[g:provides-storage]]）。注意：`signed char` 两者都不享有，`char` 只享有前者。
- 但它**不是算术类型**：不能 `b + 1`，不能隐式转成 `int`，不会被当作字符输出到 `std::cout`。想做算术必须显式 `std::to_integer<int>(b)`。
- 由于 [[dcl.init.list]] 允许用 `T{v}` 列表初始化底层类型固定的枚举，`std::byte{0x2A}` 是合法的；`std::byte{300}` 则因为窄化而非良构。

库提供的运算全部是 `constexpr` 和 `noexcept` 的，语义全都以"转换成 `unsigned int` 运算，再 `static_cast` 回 `byte`"给出：

| 运算 | 约束（Constraints） | 效果 |
|---|---|---|
| `b << shift`、`b >> shift` | `is_integral_v<IntType>` | `static_cast<byte>(static_cast<unsigned int>(b) << shift)` |
| `b <<= shift`、`b >>= shift` | `is_integral_v<IntType>` | `return b = b << shift;` |
| `l \| r`、`l & r`、`l ^ r` | — | 对 `unsigned int` 做位运算后转回 |
| `\|=`、`&=`、`^=` | — | `return l = l op r;` |
| `~b` | — | `static_cast<byte>(~static_cast<unsigned int>(b))` |
| `to_integer<IntType>(b)` | `is_integral_v<IntType>` | `static_cast<IntType>(b)` |

几点法律细节：

- **"Constraints" 意味着不满足时该重载不参与重载决议**（[[structure.specifications]]），而不是编译错误。`b << 1.0` 找不到可用的 `operator<<`——于是报"无匹配的运算符"。
- **"Equivalent to" 意味着包括 UB 在内的全部语义都照搬那段代码**。`static_cast<unsigned int>(b) << shift` 在 `shift` 为负或不小于 `unsigned int` 的位宽时是 UB（[[expr.shift]]），所以 `b << 32` 是 UB——尽管结果马上要被截断成 8 位。而 `b << 8` 合法，结果是 `byte{0}`（高位在 `static_cast<byte>` 时按模 256 截掉：转换到底层类型固定的枚举时，值先转换到底层类型 `unsigned char`，见 [[expr.static.cast]]）。
- `~b` 中 `~static_cast<unsigned int>(b)` 产生一个很大的 `unsigned int`，`static_cast` 回 `byte` 时同样取低 8 位，所以 `~byte{0x0F} == byte{0xF0}`。

```cpp run title="byte-ops.cpp" ok
#include <cstddef>

constexpr std::byte f() {
    std::byte b{0x0F};
    b <<= 4;                         // 0xF0
    b |= std::byte{0x01};            // 0xF1
    return ~b;                       // 0x0E
}
static_assert(std::to_integer<int>(f()) == 0x0E);
static_assert((std::byte{0x80} << 1) == std::byte{0});   // 高位被截掉，不是 UB

int main() {
    std::byte b{42};
    // int i = b;                    // error: 作用域枚举不能隐式转换
    // auto c = b + 1;               // error: byte 没有算术运算
    // auto d = b << 1.0;            // error: Constraints 不满足，无匹配的 operator<<
    int i = std::to_integer<int>(b);
    return i == 42 ? 0 : 1;
}
```

!!! impl
    libc++ 在 `<__cstddef/byte.h>` 中实现这些运算，形如 `static_cast<byte>(static_cast<unsigned char>(static_cast<unsigned int>(l) | static_cast<unsigned int>(r)))`——多了一次到 `unsigned char` 的显式转换，语义相同但避免了某些编译器关于截断的警告；带约束的模板通过 `enable_if_t<is_integral<_Integer>::value>` 实现。大部分运算标了 `[[nodiscard]]`，这是 libc++ 的扩展。

!!! pitfall "`std::byte` 不能替代所有 `unsigned char`"
    很多 C API（`memcpy`、`read`、`fwrite`）接受 `void*`，`std::byte*` 能隐式转换过去，没有问题。但 `std::string`/`std::string_view` 都不接受 `std::byte`；`std::byte` 也不是 [[g:character-type]]，所以 `std::byte` 数组**不能**像 `char` 数组那样用字符串字面量初始化。

## 思考题

!!! question "思考题"
    1. `struct A { int x; private: int y; };` 能否可移植地使用 `offsetof(A, x)`？
    2. 下面的代码合法吗？`std::byte b{1}; auto r = b << 31;`
    3. 为什么 `NULL` 不能定义为 `(void*)0`，却可以定义为 `nullptr`？

<details markdown="1">
<summary>展开查看答案与解析</summary>

1. 不能保证。`A` 的非静态数据成员具有不同的访问控制，按 [[class.prop]] 它不是标准布局类，`offsetof` 有条件支持（¶1）。主流实现会接受并给出警告，但标准不保证。
2. 合法，结果是 `byte{0}`。按 ¶4 它等价于 `static_cast<byte>(static_cast<unsigned int>(b) << 31)`；`1u << 31` 在 32 位 `unsigned int` 上合法（`0x80000000`），再转到 `byte` 时截断为 0。若是 `b << 32` 则是 [[expr.shift]] 中的 UB。
3. ¶2 要求 `NULL` 是**空指针常量**且是**字面量**。`(void*)0` 不是字面量；而且它的类型是 `void*`，C++ 不允许 `void*` 隐式转换为其他对象指针类型，`int* p = NULL;` 将无法编译。`nullptr` 是指针字面量（[[lex.nullptr]]），满足两项要求。
</details>

## 小结

!!! summary
    - `<cstddef>` 全部 freestanding；与 `<stddef.h>` 的差别：不声明 `wchar_t`，不定义 `unreachable`，额外有 `std::byte`。
    - `NULL`：由实现定义的空指针常量字面量，可以是 `0`、`0L`、`nullptr`，不能是 `(void*)0`；对 `NULL` 做重载决议不可移植。
    - `offsetof`：标准布局类有保证，其他类型**有条件支持**；对静态成员、成员函数结果未定义；永不类型依赖；`noexcept` 为真；不受重载 `operator&` 影响。
    - `size_t`、`ptrdiff_t`：由实现定义；分别对应 `sizeof` 和指针相减的结果类型。
    - `max_align_t`：其对齐即基本对齐的上限，值由实现定义。
    - `std::byte`：可访问对象表示、可提供存储，但不是算术类型；运算等价于 `unsigned int` 运算后截断，移位量越界仍是 UB。
