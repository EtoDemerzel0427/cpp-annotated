---
title: 公共定义
summary: <cstddef> 与 <cstdlib> 中最基础的类型和宏：size_t、ptrdiff_t、nullptr_t、NULL、std::byte、max_align_t 和 offsetof。
status: done
covers: *
related: support, basic.fundamental, conv.ptr, expr.add, expr.sizeof, basic.align, class.prop, intro.object, basic.lval, support.start.term
tags: 标准库, cstddef, offsetof, byte, size_t
updated: 2026-10-19
---

!!! tldr
    - `size_t` 是 `sizeof` 的结果类型，`ptrdiff_t` 是指针相减的结果类型。两者具体是哪个整数类型由实现决定，Linux 和 Windows 上就不一样。
    - `NULL` 可能是 `0`、`0L` 或 `nullptr`，所以 `f(NULL)` 选中哪个重载不可移植；应该写 `nullptr`。
    - `std::byte` 能像 `unsigned char` 一样访问任何对象的字节，但它不是算术类型，只支持位运算。
    - `alignof(std::max_align_t)` 是基本对齐的上限，它的值随平台变化，不要把 16 写死。
    - `offsetof` 只对标准布局类有保证，用于其他类是有条件支持的。

这些名字都由核心语言规则决定性质，再由库给出名字：`size_t` 对应 [[expr.sizeof]]，`ptrdiff_t` 对应 [[expr.add]]，`max_align_t` 对应 [[basic.align]]，`nullptr_t` 对应 [[basic.fundamental]]。

## `size_t` 与 `ptrdiff_t`（[support.types.layout] ¶2–¶4）

¶3 `size_t` 是一个由实现定义的无符号整数类型，大到足以容纳任何对象的字节数。[[expr.sizeof]] 规定 `sizeof` 和 `alignof` 的结果类型都是 `std::size_t`。由于它能容纳任何对象的大小，大小超过 `SIZE_MAX` 的类型根本无法定义，编译器会报告数组过大。

¶2 `ptrdiff_t` 是一个由实现定义的有符号整数类型，能容纳同一数组中两个下标之差。[[expr.add]] 规定指针相减的结果类型是 `std::ptrdiff_t`，结果无法用 `ptrdiff_t` 表示时行为未定义。实现靠限制对象的最大大小来满足这条要求，例如 glibc 的 `malloc` 拒绝分配超过 `PTRDIFF_MAX` 字节的块。

| 平台 | `size_t` | `ptrdiff_t` |
|---|---|---|
| Linux、macOS 的 x86-64 与 AArch64（LP64） | `unsigned long` | `long` |
| Windows x64（LLP64） | `unsigned long long` | `long long` |
| 多数 32 位平台（ILP32） | `unsigned int` | `int` |

¶4 是一条推荐实践：除非需要更大的类型才能容纳所有可能的值，`ptrdiff_t` 和 `size_t` 的整数转换等级（[[conv.rank]]）不应高于 `long`。这条建议来自 C，目的是避免选用不必要的宽类型，让混合运算中的类型提升出乎意料。Windows x64 就是需要更大类型的情况：那里的 `long` 只有 32 位，容纳不了 64 位地址空间中的对象大小。

!!! pitfall "无符号的下标倒序循环"
    `for (std::size_t i = v.size() - 1; i >= 0; --i)` 是死循环：`size_t` 是无符号类型，`i >= 0` 永远成立。空容器上 `v.size() - 1` 还会回绕成 `SIZE_MAX`。C++20 的 `std::ssize()` 返回有符号的大小，就是为这类场景准备的。

## `nullptr_t` 与 `NULL`（[support.types.nullptr]）

¶1 `nullptr_t` 就是 `decltype(nullptr)`，它的性质由 [[basic.fundamental]] 和 [[conv.ptr]] 规定：它是一个独立的基本类型，既不是指针类型也不是成员指针类型，它的值可以转换为任何指针或成员指针类型的空值。注 1 补充，`nullptr` 本身不能取地址，但类型为 `nullptr_t` 的左值对象可以：

```cpp run title="nullptr-t.cpp" ok
#include <cstddef>

int main() {
    std::nullptr_t n = nullptr;
    std::nullptr_t* p = &n;      // OK：n 是左值
    int* ip = n;                 // OK：转换为空指针
    // auto q = &nullptr;        // error: nullptr 是纯右值
    return (p != nullptr && ip == nullptr) ? 0 : 1;
}
```

¶2 `NULL` 是一个由实现定义的空指针常量，而且必须是字面量（[[lex.icon]]、[[lex.nullptr]]）。脚注 148 列出的可能定义有 `nullptr`、`0` 和 `0L`，但不能是 `(void*)0`：它不是字面量，而且 C++ 不允许 `void*` 隐式转换为其他对象指针类型，`int* p = (void*)0;` 是非良构的。

由于 `NULL` 的类型由实现决定，用它调用重载函数的结果不可移植：

```cpp run title="null-overload.cpp" ok
#include <cstddef>

int f(int)   { return 1; }
int f(char*) { return 2; }

int main() {
    // f(NULL);  NULL 是 0 → f(int)；是 0L → 歧义；
    //           是 nullptr → f(char*)；本机 Clang 报歧义
    return f(nullptr);   // 总是 f(char*)
}
```

!!! impl "Clang 与 GCC 的 `__null`"
    在 C++ 模式下，Clang 和 GCC 在多数平台上把 `NULL` 定义为 `__null`。它是一个与指针同宽的整数常量（LP64 上相当于 `0L`），但编译器知道它代表空指针，所以能对 `int x = NULL;` 给出 `-Wnull-conversion` 警告。本机 Clang 23 对 `f(NULL)` 报告调用有歧义。

## `std::byte`（[cstddef.syn]、[support.types.byteops]）

`std::byte` 的定义只有一行：

```cpp
enum class byte : unsigned char {};
```

它是一个作用域枚举，底层类型是 `unsigned char`，没有任何枚举项。C++17 引入它，是为了有一个只表示原始字节、既不表示数字也不表示字符的类型：

- 和 `unsigned char` 一样，它可以访问任何对象的字节：[[basic.lval]] 允许通过 `char`、`unsigned char` 或 `std::byte` 类型的左值访问任何对象。`unsigned char` 和 `std::byte` 的数组还可以为其他对象提供存储（[[intro.object]]），`char` 数组不行。
- 它不是算术类型：不能写 `b + 1`，不能隐式转换为 `int`，输出到 `std::cout` 时也不会被当作字符。需要数值时用 `std::to_integer<int>(b)`。
- 底层类型固定的枚举可以用 `T{v}` 列表初始化（[[dcl.init.list]]），所以 `std::byte{0x2A}` 合法；`std::byte{300}` 是窄化转换，非良构。

库提供的运算全部是 `constexpr` 和 `noexcept` 的，效果都写成先转换为 `unsigned int` 运算、再 `static_cast` 回 `byte`：

| 运算 | 约束 | 等价于 |
|---|---|---|
| `b << n`、`b >> n`（¶3–¶4、¶7–¶8） | `n` 是整数类型 | `static_cast<byte>(static_cast<unsigned int>(b) << n)` |
| `l \| r`、`l & r`、`l ^ r`（¶10、¶12、¶14） | 无 | 对两个 `unsigned int` 做位运算后转回 |
| `~b`（¶15） | 无 | `static_cast<byte>(~static_cast<unsigned int>(b))` |
| `<<=`、`\|=` 等复合赋值 | 同上 | `return b = b << n;` 等 |
| `to_integer<T>(b)`（¶16–¶17） | `T` 是整数类型 | `static_cast<T>(b)` |

```cpp run title="byte-ops.cpp" ok
#include <cstddef>

constexpr std::byte f() {
    std::byte b{0x0F};
    b <<= 4;                         // 0xF0
    b |= std::byte{0x01};            // 0xF1
    return ~b;                       // 0x0E
}
static_assert(std::to_integer<int>(f()) == 0x0E);
static_assert((std::byte{0x80} << 1) == std::byte{0});  // 高位截掉

int main() {
    std::byte b{42};
    // int i = b;         // error: 作用域枚举不能隐式转换
    // auto c = b + 1;    // error: byte 没有算术运算
    // auto d = b << 1.0; // error: 约束不满足
    int i = std::to_integer<int>(b);
    return i == 42 ? 0 : 1;
}
```

两个细节值得注意。第一，约束（*Constraints*）不满足时，这个运算符模板不参与重载决议，所以 `b << 1.0` 报的是找不到匹配的运算符。

第二，Equivalent to 意味着那段代码中的未定义行为也一并照搬。`b << 8` 合法，结果是 `byte{0}`：`unsigned int` 的结果转换回 `byte` 时，先转换到底层类型 `unsigned char`，只留下低 8 位（[[expr.static.cast]]）。`b << 32` 却是未定义行为，因为移位量不小于 `unsigned int` 的位宽（[[expr.shift]]），尽管结果马上就要截成 8 位。本机 Clang 在常量求值中拒绝了 `std::byte{1} << 32`。

!!! pitfall "`std::byte` 不能取代所有 `unsigned char`"
    `memcpy`、`fwrite` 这类接受 `void*` 的 C 函数可以直接接受 `std::byte*`。但 `std::string`、`std::string_view` 不接受 `std::byte`；`std::byte` 也不是字符类型，`std::byte` 数组不能用字符串字面量初始化。

## `max_align_t`（[support.types.layout] ¶5）

!!! std
    The type `max_align_t` is a trivially copyable standard-layout type whose alignment requirement is at least as great as that of every scalar type, and whose alignment requirement is supported in every context.

¶5 `max_align_t` 的对齐要求不低于任何标量类型，并且在任何上下文中都受支持。它还是可平凡复制、可平凡默认构造的标准布局类型。

在任何上下文中都受支持，把它和 [[basic.align]] 联系了起来：`alignof(std::max_align_t)` 是**基本对齐**（[[g:fundamental-alignment]]）的上限。不超过它的对齐都是基本对齐；超过它的是扩展对齐（[[g:extended-alignment]]），是否支持、在哪里支持由实现决定。

`malloc` 返回的指针对任何基本对齐的类型都足够对齐。`operator new(size_t)` 默认保证的对齐是另一个量 `__STDCPP_DEFAULT_NEW_ALIGNMENT__`（[[cpp.predefined]]），它可以比 `alignof(max_align_t)` 大；对齐要求更高的类型，`new` 会改用带 `std::align_val_t` 参数的分配函数（[[new.delete]]）。

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

在 Apple Silicon 上，Clang 把 `max_align_t` 定义为 `long double` 的别名，而那里的 `long double` 与 `double` 相同，所以上例打印 8、8 和 16。在 x86-64 Linux 上，`max_align_t` 是一个含 `long long` 和 `long double` 成员的结构体，通常打印 16、32 和 16。手写的内存分配器不应把 16 写死。

## `offsetof`（[support.types.layout] ¶1）

`offsetof(type, member-designator)` 是一个类型为 `size_t` 的整型常量表达式，值是成员相对于类对象起始地址的字节偏移。¶1 在 C 的语义上加了几条限制：

!!! std
    Use of the `offsetof` macro with a *type* other than a standard-layout class is conditionally-supported.

- 只有**标准布局类**（[[class.prop]]）有保证。对其他类型使用 `offsetof` 是**有条件支持**的（[[g:conditionally-supported]]）：实现可以不支持，但不支持时必须给出诊断。
- 对静态数据成员或成员函数使用 `offsetof`，结果未定义。
- `offsetof` 不能抛异常，`noexcept(offsetof(type, member-designator))` 必须为 `true`。
- `offsetof(type, member-designator)` 永远不是类型依赖的，它的类型总是 `size_t`；当且仅当 *type* 是依赖类型时，它是值依赖的（[[temp.dep.constexpr]]）。
- 脚注 149：即使涉及的类型重载了一元 `operator&`，`offsetof` 也必须正确工作。所以 C 里常见的 `((size_t)&((T*)0)->m)` 写法不能用来实现它，Clang 和 GCC 用的是内建的 `__builtin_offsetof`。

为什么限定为标准布局类？标准布局类的成员布局能与 C 的结构体对应。一旦有了虚函数、虚基类、混合的访问控制，布局就交给 ABI 决定。虚基类子对象的偏移甚至不是常量，它取决于最终的完整对象类型，只能在运行时查虚表得到。

```cpp run title="offsetof.cpp"
#include <cstddef>

struct S  { char c; double d; int operator&() const; };  // 重载了一元 &
struct V  { virtual ~V(); int x; };                      // 有虚函数，非标准布局
struct B  { int b; };
struct VB : virtual B { int x; };                        // 虚基类
struct M  { static int s; int f(); int arr[4]; struct { int y; } in; };

static_assert(offsetof(S, d) == alignof(double));  // OK：不受 operator& 影响
static_assert(noexcept(offsetof(S, d)));           // OK
constexpr auto e = offsetof(M, arr[2]);            // OK：可以带下标
constexpr auto g = offsetof(M, in.y);              // OK：可以是嵌套成员
auto v = offsetof(V, x);       // 有条件支持：Clang 接受并警告
// auto w = offsetof(VB, b);   // Clang 拒绝：虚基类的成员
// auto s = offsetof(M, s);    // 结果未定义：Clang 报错
// auto f = offsetof(M, f);    // 同上

template<class T>
constexpr auto off = offsetof(T, b);  // 值依赖，但类型总是 size_t

int main() { (void)e; (void)g; (void)v; return off<B>; }
```

这段代码中 `V` 的那一行用的是有条件支持的特性，所以整段不加判定。本机 Clang 23 对它给出 `-Winvalid-offsetof` 警告并接受，对虚基类成员则直接报错 invalid application of 'offsetof' to a field of a virtual base。实现支持一部分、对不支持的部分给出诊断，这正是有条件支持的含义。

!!! pitfall "成员指示符不是表达式"
    *member-designator* 沿用 C 的语法：一个标识符，后面可以跟 `.标识符` 或 `[常量表达式]`。另外 `offsetof` 是宏，`offsetof(std::pair<int, int>, first)` 中模板实参列表里的逗号会被预处理器当作宏实参的分隔符，需要先给类型起个别名。

## 头文件 `<cstddef>` 与 `<cstdlib>`

[cstddef.syn] 的 synopsis 开头注明 all freestanding：`<cstddef>` 的全部内容在独立实现（[[g:freestanding-implementation]]）中也必须提供。¶1 规定它与 C 的 `<stddef.h>` 相同，只有几处差别：不声明 `wchar_t`，因为它在 C++ 中是关键字；不定义 C23 的 `unreachable` 宏，C++ 用 `<utility>` 的 `std::unreachable()`；额外声明了 `std::byte` 及其运算；`NULL` 和 `offsetof` 有上面讲过的限制。

[cstdlib.syn] 的 `<cstdlib>` 对应 C 的 `<stdlib.h>`，内容很杂：程序终止（`exit`、`atexit` 等，见 [[support.start.term]]）、`malloc` 一族（[[c.malloc]]）、`strtol` 等数值转换、`qsort` 和 `bsearch`（[[alg.c.library]]）、`rand`、`abs` 和 `div`。¶1 规定它不声明 `wchar_t`、`once_flag` 和 `call_once`，C++ 用的是 `<mutex>` 中的 `std::call_once`。注 1 说明一些函数在 C++ 中有额外的重载，例如 `abs` 有浮点版本，但行为与 C 库相同。

<details class="fine" markdown="1"><summary>其余条文</summary>

`<cstdlib>` 的 synopsis 用了四个仅用于说明的函数类型别名：`c-atexit-handler` 与 `atexit-handler` 都是 `void()`，前者具有 C 语言链接，后者具有 C++ 语言链接；`c-compare-pred` 与 `compare-pred` 同理。所以 `atexit`、`at_quick_exit`、`qsort`、`bsearch` 都各有两个重载。原因是按 [[dcl.link]]，语言链接是函数类型的一部分，C 函数和 C++ 函数的调用约定理论上可以不同。Clang 和 GCC 并不把语言链接算进函数类型，这是它们长期存在的偏离，实践中感觉不到这两个重载。

synopsis 还把 `abs`、`labs`、`div` 等声明为 `constexpr`，这是 C++23 的要求。本机 libc++ 尚未实现：`constexpr int y = std::abs(-1);` 报错。

</details>

## 思考题

!!! question "思考题"
    1. `struct A { int x; private: int y; };` 能否可移植地使用 `offsetof(A, x)`？
    2. `std::byte b{1}; auto r = b << 31;` 合法吗？
    3. 为什么 `NULL` 不能定义为 `(void*)0`，却可以定义为 `nullptr`？

<details markdown="1">
<summary>答案</summary>

1. 不能保证。`A` 的非静态数据成员具有不同的访问控制，按 [[class.prop]] 它不是标准布局类，所以 `offsetof` 是有条件支持的。本机 Clang 接受并给出 `-Winvalid-offsetof` 警告，但标准不保证每个实现都接受。
2. 合法，结果是 `byte{0}`。按 [support.types.byteops] ¶4，它等价于 `static_cast<byte>(static_cast<unsigned int>(b) << 31)`。在 32 位 `unsigned int` 上 `1u << 31` 是 `0x80000000`，转换回 `byte` 时只留下低 8 位，也就是 0。如果写成 `b << 32`，就是 [[expr.shift]] 中的未定义行为。
3. [support.types.nullptr] ¶2 要求 `NULL` 是空指针常量，并且是字面量。`(void*)0` 不是字面量，而且它的类型是 `void*`，C++ 不允许 `void*` 隐式转换为其他对象指针类型，`int* p = NULL;` 将无法编译。`nullptr` 是指针字面量（[[lex.nullptr]]），两项要求都满足。
</details>
