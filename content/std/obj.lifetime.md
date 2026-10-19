---
title: 显式生命周期管理
summary: start_lifetime_as 把一段已经写好的字节直接当作对象使用，不拷贝也不读写内存；C++26 的 start_lifetime 让联合体成员不经初始化就成为活跃成员。
status: done
related: intro.object, basic.life, basic.types, class.union, bit.cast, basic.compound, ptr.launder, c.malloc, memory
tags: 标准库, 对象模型, 隐式对象创建, start_lifetime_as, 联合体
papers: P2590R2, P2679R2, P3726R2
updated: 2026-10-19
---

!!! tldr
    - 网络包、`mmap` 的文件这类外部写好的字节，用 `reinterpret_cast` 当作结构体来读是未定义行为；`std::start_lifetime_as<T>(p)` {{c++23}} 是合法的写法。
    - `start_lifetime_as` 在原地隐式创建一个 `T`，对象表示就是原来的字节，值按 `bit_cast` 的规则得到；它不读也不写存储，所以可以用于只读内存。
    - `T` 必须是隐式生存期类型，比如聚合或可平凡复制的结构体；`std::string` 这类需要构造函数的类型不行。
    - 运行期长度用 `start_lifetime_as_array<T>(p, n)`，它创建一个数组对象，`n == 0` 时 `p` 可以为空。
    - `std::start_lifetime(r)` {{c++26}} 用途不同：它让联合体里的一个聚合成员开始生命周期并成为活跃成员，不做任何初始化，主要用于常量求值。

## 字节已经在那里了

```cpp run ub
#include <cstdint>
#include <cstdio>
struct Header { std::uint32_t magic; std::uint32_t length; };
int main() {
  alignas(Header) unsigned char packet[16] = {0x78, 0x56, 0x34, 0x12, 8};
  auto* h = reinterpret_cast<Header*>(packet);
  std::printf("%u\n", (unsigned)h->length);   // UB: h 不指向 Header 对象
}
```

`packet` 的内容可以来自 `recv`、`mmap` 或 DMA。程序想把开头 8 个字节当作一个 `Header` 来读。本机 Clang 23 编译运行都正常，打印 `8`，但按标准这是未定义行为：`reinterpret_cast` 只改变指针的类型，`h` 仍然指向 `packet[0]` 这个 `unsigned char`，那里没有一个可以通过 `h` 访问的 `Header` 对象（[[basic.lval#11]]）。

要让访问合法，那段存储里必须真的有一个 `Header` 对象。隐式生存期类型（[[g:implicit-lifetime-type]]：标量、聚合、有平凡构造和析构的类，以及它们的数组）的对象可以不经构造函数，由某些操作**隐式创建**（[[g:implicitly-create-objects]]，[[intro.object#13]]）。`malloc`、`operator new`、`memcpy`、`memmove` 都有这个效果。

所以在 C++20 里可移植的写法是把字节原地拷给自己：

```cpp run ok
#include <cstdint>
#include <cstdio>
#include <cstring>

struct Header {
  std::uint32_t magic;
  std::uint32_t length;
};

Header* as_header(void* p) {
  // memmove 隐式创建对象，返回值指向新建的 Header
  return static_cast<Header*>(
      std::memmove(p, p, sizeof(Header)));
}

int main() {
  alignas(Header) unsigned char packet[16] = {
      0x78, 0x56, 0x34, 0x12, 8, 0, 0, 0};
  Header* h = as_header(packet);
  std::printf("%x %u\n", (unsigned)h->magic,
              (unsigned)h->length);  // 小端机：12345678 8
}
```

[[cstring.syn#3]] 规定 `memcpy` 和 `memmove` 返回指向合适的已创建对象的指针，所以直接用返回值就行，不需要 `std::launder`。如果丢掉返回值，继续拿 `packet` 做 `reinterpret_cast`，就又回到了上面的问题。

这个写法能用，但意图不明显，而且要写存储，对只读映射的页会出错。C++23 的 `start_lifetime_as`（[[P2590R2]]）给这个操作起了名字，并去掉了对存储的读写。

## `start_lifetime_as` {{c++23}}

```cpp
template<class T> T* start_lifetime_as(void* p) noexcept;
// 另有 const void*、volatile void*、const volatile void* 三个重载，
// 返回相应限定的 T*
```

用它改写上面的例子：

```cpp
#include <memory>
#include <cstddef>
#include <cstdint>

struct Header { std::uint32_t magic; std::uint32_t length; };

const Header* parse(const std::byte* packet) {
  // 前置条件：packet 处有 sizeof(Header) 字节的已分配存储，并按 Header 对齐
  return std::start_lifetime_as<Header>(packet);   // 不拷贝，也不访问存储
}
```

截至写作时，本机 Clang 23 + libc++ 还没有提供 `start_lifetime_as`，这段代码没有经过编译验证。

### 对 `T` 的要求（¶3）

¶3 `T` 必须是隐式生存期类型，并且不是不完整类型，否则程序非良构。

`start_lifetime_as` 不调用构造函数，它创建对象靠的就是隐式对象创建，而只有隐式生存期类型的对象才能这样创建。`std::string` 的不变式要由构造函数建立，所以 `start_lifetime_as<std::string>` 是 {{ill-formed}}。不完整类型这一条排除了 `int[]` 这样的未知边界数组：本该调用 `start_lifetime_as_array` 时误写成 `start_lifetime_as<int[]>`，会在编译期报错。

### 对存储的要求（¶4）

¶4 前置条件有三条，违反任何一条都是未定义行为：

- `[p, (char*)p + sizeof(T))` 是一段已分配的存储；
- 这段存储在**经由 `p` 可达**的范围之内（[[g:reachable-through]]，[[basic.compound]]）。例如 `p` 指向某个结构体的 `int` 成员时，不能借它把相邻成员也当作新对象的一部分；
- 地址按 `T` 的要求对齐。库不检查这一点。

### 值从哪里来（¶5）

¶5 是这个函数的核心：

!!! std "[obj.lifetime]/5"
    The object representation of *a* is the contents of the storage prior to the call to start_lifetime_as.

`start_lifetime_as` 在 `p` 处隐式创建一个 `T` 类型的对象 *a*，以及嵌套在其中的对象。*a* 的对象表示就是调用之前存储里的字节。

每个被创建的对象的值按类型分两种：

- 可平凡复制类型 `U` 的对象，值的确定方式与 `bit_cast<U>(E)` 相同（[[bit.cast]]），只是不访问存储。这样它就沿用了 `bit_cast` 关于填充位和不确定值的全部规则：原来的字节是不确定值时，得到的值也相应地不确定。
- 其他对象的值是未指定的，注 2 说明它可以是不确定值。

和所有隐式对象创建一样，具体创建哪些嵌套对象，按能让程序具有定义行为的方式选择（[[intro.object#13]]）。

### 返回值（¶6）

¶6 返回指向 *a* 的指针。和 `memmove` 的写法一样，之后要通过这个返回值访问对象；继续用原来的 `unsigned char*` 做 `reinterpret_cast`，仍然需要 `std::launder`。

### `const` 与 `volatile` 重载

`memmove` 的写法要写存储，即使写回的是原值，对 `PROT_READ` 映射的只读页也会触发段错误。`start_lifetime_as` 不访问存储，`const void*` 重载返回 `const T*`，可以直接用于只读内存。`volatile` 重载用于内存映射的硬件寄存器。

## `start_lifetime_as_array`（¶7–¶10）{{c++23}}

```cpp
template<class T> T* start_lifetime_as_array(void* p, size_t n) noexcept;
// 同样有 const / volatile / const volatile 三个重载
```

`start_lifetime_as<T[4]>` 要求长度是常量表达式。长度在运行期才知道时，比如包头里写着后面有几条记录，就用 `start_lifetime_as_array`。

¶7 `T` 必须是完整类型。这里不要求 `T` 是隐式生存期类型，因为数组类型总是隐式生存期类型。元素的值仍按 ¶5 决定：可平凡复制的元素按 `bit_cast` 规则，其他元素的值未指定。

¶8 前置条件：`p` 按 `T` 的数组对齐，或者是空指针；`n <= size_t(-1) / sizeof(T)`，也就是 `n * sizeof(T)` 不溢出；`n > 0` 时，`[p, p + n * sizeof(T))` 是经由 `p` 可达的已分配存储。

¶9 `n > 0` 时，效果等价于 `start_lifetime_as<U>(p)`，`U` 是 `n` 个 `T` 的数组；否则什么也不做。

¶10 返回指向所创建数组首元素的指针；没有创建数组时，返回一个与 `p` 比较相等的指针。

`n == 0` 和空指针的规定由 [[P2679R2]] 在 C++23 发布前补上。最初的措辞下 `n == 0` 是未定义行为，泛型代码必须特判空范围；现在 `n == 0` 合法，此时 `p` 也可以为空。返回的指针只能像尾后指针那样使用，不能解引用。

!!! lawyer "为什么不能循环调用 n 次 `start_lifetime_as<T>`"
    `start_lifetime_as_array` 创建的是一个数组对象，返回的 `T*` 指向它的元素，在 `[0, n]` 范围内做指针算术是合法的。循环调用 `n` 次 `start_lifetime_as<T>` 得到的是 `n` 个互不相关的完整对象，[[expr.add]] 只允许在同一个数组对象内做指针算术，在它们之间移动指针是未定义行为。

## `start_lifetime`（¶1–¶2）{{c++26}}

```cpp
template<class T> constexpr void start_lifetime(T& r) noexcept;
```

这个函数由 [[P3726R2]] 加入，用途和前面两个完全不同。它解决的是这样一个问题：

```cpp
#include <cstddef>
#include <memory>

template<class T, std::size_t N>
struct Storage {
  union { T elems[N]; };          // 构造时不想初始化任何元素
  constexpr Storage() {
    std::start_lifetime(elems);   // elems 成为活跃成员；数组开始生命周期，元素没有
  }
  constexpr ~Storage() {}
};
```

`inplace_vector` 一类容器需要一块未初始化的存储，之后再用 `std::construct_at(&elems[i], ...)` 逐个构造元素。放进联合体可以避免构造时初始化元素。在运行期，隐式对象创建或者对成员赋值都能让成员变为活跃。常量求值则要求精确知道哪个成员活跃、哪些对象存在，访问非活跃成员会让表达式不是常量表达式。`start_lifetime` 给出一个显式的、不做任何初始化的信号。

¶1 `T` 必须是完整的、隐式生存期的聚合类型。数组满足这个条件。

¶2 如果 `r` 所指的对象已经在生命周期内，没有效果；否则开始它的生命周期。注 1 补充：不执行任何初始化，也不开始任何子对象的生命周期；如果 `r` 指代联合体 `U` 的成员，它成为 `U` 的活跃成员（[[class.union]]）。

截至写作时，本机 libc++ 还没有提供 `std::start_lifetime`，上面的代码没有经过编译验证。

## 与相关工具的对比

| 工具 | 创建对象 | 访问存储 | 得到的值 | 典型用途 |
|---|---|---|---|---|
| `reinterpret_cast<T*>(p)` | 否 | 否 | 没有对象可访问，{{ub}} | 错误用法 |
| `std::launder(p)` | 否 | 否 | 要求 `p` 处已经有 `T` 对象 | 修正指针值，见 [[ptr.launder]] |
| `memmove(p, p, n)` | 是 | 读和写 | 原来的字节 | C++20 的可移植写法 |
| `start_lifetime_as<T>(p)` | 是 | 否 | 原来的字节，按 `bit_cast` 规则 | 网络包、`mmap`、只读内存 |
| `start_lifetime(r)` | 开始 `r` 的生命周期 | 否 | 不初始化 | 常量求值中的联合体存储 |
| placement new / `construct_at` | 是 | 写 | 初始化的结果 | 一般的构造 |

最常见的混淆是 `launder` 和 `start_lifetime_as`。`launder` 从不创建对象，它只在对象已经存在、而手里的指针值不指向它时修正指针值；让对象出现的是 `start_lifetime_as`。

## 思考题

!!! question "思考题 1"
    对一段由 `recv` 写入的 `unsigned char buf[64]` 调用 `start_lifetime_as<Header>(buf)` 之后，还能读 `buf[0]` 吗？

<details markdown="1">
<summary>答案</summary>

可以，读到的仍是原来的字节。`unsigned char` 数组为在其中创建的对象提供存储（[[intro.object#3]]），数组和它的元素不会因为 `Header` 的出现而结束生命周期；通过 `unsigned char` 左值读取任何对象的字节也是允许的（[[basic.lval#11]]）。之后如果通过返回的 `Header*` 修改了 `length`，再读 `buf[4]` 看到的是新字节，因为它们是同一段存储。
</details>

!!! question "思考题 2"
    为什么 `start_lifetime_as` 只接受隐式生存期类型？

<details markdown="1">
<summary>答案</summary>

`start_lifetime_as` 不运行任何构造函数，¶5 说它隐式创建对象，而 [[intro.object#13]] 只允许隐式创建隐式生存期类型的对象。其他类型的对象必须经由构造函数开始生命周期（[[basic.life]]），否则它的不变式无从建立。
</details>
