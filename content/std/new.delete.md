---
title: 存储的分配与释放
summary: 全局 operator new/delete 的 22 个签名逐一拆解：Required behavior 与 Default behavior 的区别、new_handler 循环、nothrow 版本如何转发、尺寸与对齐释放的前置条件、替换规则、constexpr 的 placement 形式与数据竞争保证
status: done
covers: *
papers: N3778, P0035R4, P2747R2
related: support.dynamic, basic.stc, dcl.fct.def.replace, expr.new, expr.delete, alloc.errors, basic.align, intro.races, replacement.functions
tags: 标准库, operator new, operator delete, 可替换函数, 尺寸释放, 对齐分配
updated: 2026-10-18
---

[[basic.stc.dynamic]] 从核心语言的角度规定了分配函数和释放函数必须满足的条件：签名形式、返回非空且对齐的指针、失败时抛 `bad_alloc`、零大小请求也要返回唯一指针，等等。本节则是库的视角：标准库提供了哪 22 个全局函数，每个函数的默认行为是什么，程序替换它们时必须遵守什么。

读本节要先理解库条款的两个专用词（[[structure.specifications]]）：

- ***Required behavior***（要求的行为，[[g:required-behavior]]）：对替换版本也有约束力的契约。条文中反复出现 "This requirement is binding on any replacement versions of these functions"。违反它的替换函数会让程序的行为未定义（[[res.on.functions]]）。
- ***Default behavior***（默认行为，[[g:default-behavior]]）：库自带版本做的事。替换后，这部分就不再适用。

理解本节的关键就在这一区分。例如 `operator new` 的 *Required behavior* 是返回非空的适当对齐的指针，否则抛 `bad_alloc`；而 *Default behavior* 是循环尝试分配、调用 new_handler 等等。你的替换版本不必调用 new_handler，但不能返回空指针。

## 总则（[new.delete.general]）

¶1 有两条规则：

- 除非另有规定，[[basic.stc.dynamic]] 的条款适用于库版本的 `operator new` 和 `operator delete`。
- 如果传给这些函数的对齐实参不是有效的对齐值（[[basic.align]]：必须是 2 的非负整数次幂），行为未定义。所以手动调用 `::operator new(n, std::align_val_t(3))` 是 UB。

¶2：在独立实现上，可替换全局分配函数的默认版本是否满足 [new.delete.single] 和 [new.delete.array] 中的要求，是由实现定义的。注 1：独立实现的默认版本被调用时可以导致未定义行为（例如没有堆的嵌入式平台）；在常量求值中，这些默认版本的行为无关紧要，因为对它们的调用会被省略（[[expr.new]]）。*推荐实践*：如果默认版本中有任何一个满足宿主实现的要求，那么它们都应当满足。配套的特性测试宏是 `__cpp_lib_freestanding_operator_new`（[[version.syn]]）。

## 单对象形式（[new.delete.single]）

### 抛出版本的 `operator new`（¶1–¶4）

```cpp
void* operator new(std::size_t size);
void* operator new(std::size_t size, std::align_val_t alignment);
```

¶1 *Effects*：*new-expression* 调用的分配函数，用以分配 `size` 字节。第二种形式用于具有 new 扩展对齐的类型，第一种用于其他情况。

¶2 *Required behavior*：返回指向适当对齐存储的非空指针，否则抛出 `bad_alloc` 异常。

¶3 *Default behavior* 是一个循环：

- ¶3.1 尝试分配所请求的存储。这次尝试是否调用 C 库的 `malloc` 或 `aligned_alloc`，是未指明的。
- ¶3.2 成功则返回指针。否则，如果当前的 `new_handler`（[[get.new.handler]]）是空指针，抛出 `bad_alloc`。
- ¶3.3 否则调用当前的 `new_handler`；如果它返回，循环重来。
- ¶3.4 分配成功，或者所调用的 `new_handler` 不返回，循环就结束。

¶4 *Remarks*：此函数是可替换的（[[dcl.fct.def.replace]]）。

!!! note "“是否调用 malloc 是未指明的”"
    这句话的意思是：即使在你的平台上默认实现恰好就是 `malloc`，你也不能假设 `operator new` 分配的内存可以用 `free` 释放，或者 `malloc` 分配的内存可以用 `operator delete` 释放。混用属于违反 ¶10 的前置条件，是 UB。

### nothrow 版本（¶5–¶9）

```cpp
void* operator new(std::size_t size, const std::nothrow_t&) noexcept;
void* operator new(std::size_t size, std::align_val_t alignment, const std::nothrow_t&) noexcept;
```

¶5：与上面相同，只是它们由 placement 形式的 *new-expression* `new (std::nothrow) T` 调用，供更希望用空指针表示错误的程序使用。

¶6 *Required behavior*：返回非空的适当对齐指针，或者返回空指针。并且，每个 nothrow 版本返回的指针，都如同是从（可能被替换的）对应非 placement 版本获得的。

¶7 *Default behavior*：调用 `operator new(size)` 或 `operator new(size, alignment)`；正常返回则返回其结果，否则（抛出异常）返回空指针。

¶6 的后半句保证了 `new (std::nothrow) T` 得到的指针可以用普通的 `delete` 释放，因为它如同来自 `operator new(size_t)`。¶7 则意味着，**只替换 `operator new(size_t)`，nothrow 版本的默认实现也会调用你的替换版本**。

```cpp
T* p1 = new T;                  // 失败时抛 bad_alloc
T* p2 = new(std::nothrow) T;    // 失败时返回 nullptr（¶8 例 1）
```

!!! pitfall "`new (std::nothrow)` 不是 `noexcept` 的 *new-expression*"
    nothrow 只管分配：如果 `T` 的构造函数抛出异常，异常照样传播出去（存储会先通过 `operator delete(void*, const nothrow_t&)` 释放，见 ¶19）。

### 释放函数（¶10–¶16）

```cpp
void operator delete(void* ptr) noexcept;
void operator delete(void* ptr, std::size_t size) noexcept;
void operator delete(void* ptr, std::align_val_t alignment) noexcept;
void operator delete(void* ptr, std::size_t size, std::align_val_t alignment) noexcept;
```

¶10–¶11 *Preconditions* 如下，违反即 UB：

- `ptr` 是空指针，或者其值表示一块由先前对（可能被替换的）`operator new(std::size_t)` 或 `operator new(std::size_t, std::align_val_t)` 的调用所分配、且尚未被中间的 `operator delete` 调用失效的内存块的地址。
- 若没有对齐参数，`ptr` 必须由没有对齐参数的分配函数返回；若有对齐参数，其值必须等于传给分配函数的对齐实参。
- 若有大小参数，其值必须等于传给分配函数的大小实参。

也就是说，**分配与释放必须配对**：对齐分配的指针必须用对齐释放；`new[]` 得来的必须用 `delete[]`（数组形式的前置条件要求来自 `operator new[]`）。

¶12 *Effects*：*delete-expression* 调用的释放函数（[[basic.stc.dynamic.deallocation]]），使 `ptr` 的值无效（[[g:invalid-pointer-value]]）。

¶13 *Required behavior*：对带大小参数的 `operator delete` 的调用，可以改为对相应不带大小参数版本的调用，而不影响内存分配。注 1：一个符合要求的实现可以让 `operator delete(void* ptr, std::size_t size)` 简单地调用 `operator delete(ptr)`。

¶14 *Default behavior*：带大小参数的函数把其他参数转发给对应的不带大小参数的函数。

¶15 *Default behavior*：`ptr` 为空则什么也不做；否则回收先前 `operator new` 分配的存储。

¶16 *Remarks*：回收的存储在什么条件下被后续的 `operator new` 或 `aligned_alloc`、`calloc`、`malloc`、`realloc` 再次分配，是未指明的。此函数是可替换的。接下来是替换的配对规则：

!!! std
    If a replacement function without a size parameter is defined by the program, the program should also define the corresponding function with a size parameter. If a replacement function with a size parameter is defined by the program, the program shall also define the corresponding version without the size parameter.

    如果程序定义了不带大小参数的替换函数，它应当（should）也定义对应的带大小参数的版本；如果定义了带大小参数的替换函数，它必须（shall）也定义对应的不带大小参数的版本。

注意 *should* 与 *shall* 的不对称：

- 只替换 `operator delete(void*)` 而不替换尺寸版本：合法，但不推荐。按 ¶14 的默认行为，尺寸版本会转发给你的 `operator delete(void*)`，暂时没问题；但注 3 提醒，默认行为将来可能改变。如果某天库的尺寸版本不再转发，你的 `operator new` 分配的内存就会交给库的默认 `operator delete` 释放，后果无法预料。
- 只替换尺寸版本而不替换无尺寸版本：违反 shall。原因是 ¶13 允许实现把尺寸调用改写为无尺寸调用，届时你替换的函数会被绕过。

!!! history "尺寸释放（C++14）与对齐分配（C++17）"
    带 `size_t` 参数的全局 `operator delete` 由 [[N3778]] 在 C++14 引入：现代分配器（tcmalloc、jemalloc）按大小类组织内存，释放时若知道大小就不必查元数据。带 `align_val_t` 的全部形式由 [[P0035R4]] 在 C++17 引入，此前 `new` 一个 `alignas(64)` 的类型只能得到基本对齐的内存，是一个长期的缺陷。编译器侧的开关见 [[basic.stc]] 的实现视角部分；对应预定义宏是 `__cpp_sized_deallocation` 和 `__cpp_aligned_new`（[[cpp.predefined]]）。

### nothrow 释放函数（¶17–¶21）

```cpp
void operator delete(void* ptr, const std::nothrow_t&) noexcept;
void operator delete(void* ptr, std::align_val_t alignment, const std::nothrow_t&) noexcept;
```

*delete-expression* 不会调用它们（`delete` 语法无法传入 placement 实参）。¶19：实现只在一种情况下调用它们：nothrow placement *new-expression* 中调用的构造函数抛出异常时，用它们释放刚分配的存储（即 [[expr.new]] 中 placement 的匹配释放函数）。¶20 默认行为：调用 `operator delete(ptr)` 或 `operator delete(ptr, alignment)`。

## 数组形式（[new.delete.array]）

八个数组签名与单对象形式一一对应，规则几乎相同，差别在于默认行为都转发给单对象形式：

| 函数 | 默认行为 |
|---|---|
| `operator new[](size)` / `(size, al)` | ¶3：返回 `operator new(size)` / `operator new(size, al)` |
| nothrow `operator new[]` | ¶7：调用 `operator new[](size)` / `(size, al)`，抛异常则返回空 |
| `operator delete[](ptr)` 等四个 | ¶13：带大小的转发给不带大小的；不带大小的转发给对应的单对象 `operator delete` |
| nothrow `operator delete[]` | ¶18：调用 `operator delete[](ptr)` / `(ptr, al)` |

¶9 的前置条件要求 `ptr` 来自 `operator new[]`，并由 `operator delete[]` 失效。因此**单对象与数组形式不能混用**，哪怕默认实现之间是互相转发的。

脚注 168 澄清了一个常见误解：记录数组元素个数不是 `operator new[]`/`operator delete[]` 的职责，而是 *new-expression* 和 *delete-expression* 做的事。数组 *new-expression* 可以把传给 `operator new[]` 的 `size` 增大，多要一点空间存放数组 cookie（Itanium ABI 中，仅当元素类型有非平凡析构函数时才需要）。所以 `new T[n]` 传给 `operator new[]` 的 `size` 可能大于 `n * sizeof(T)`（[[expr.new]]）。

```cpp run title="array-cookie.cpp" impl
#include <cstdio>
#include <cstdlib>
#include <new>

void* operator new[](std::size_t n) {
    std::printf("operator new[](%zu)\n", n);
    if (void* p = std::malloc(n)) return p;
    throw std::bad_alloc();
}
void operator delete[](void* p) noexcept { std::free(p); }
void operator delete[](void* p, std::size_t) noexcept { std::free(p); }

struct Trivial    { int x; };
struct NonTrivial { int x; ~NonTrivial() {} };

int main() {
    delete[] new Trivial[4];      // 打印 16：无需 cookie
    delete[] new NonTrivial[4];   // AArch64 macOS 上打印 32：16 字节 cookie（ARM 风格 ABI 记录元素大小和个数）；
                                  // x86-64 Itanium ABI 上通常是 24（8 字节 cookie 只记录个数）
}
```

## 非分配形式（[new.delete.placement]）

```cpp
constexpr void* operator new  (std::size_t size, void* ptr) noexcept;
constexpr void* operator new[](std::size_t size, void* ptr) noexcept;
constexpr void  operator delete  (void* ptr, void*) noexcept;
constexpr void  operator delete[](void* ptr, void*) noexcept;
```

¶1：这些函数是保留的，程序不得定义取代标准库版本的函数（[[constraints]]）。[[basic.stc.dynamic]] 的条款对它们不适用，因为它们不分配任何东西，也不需要返回唯一指针。

- ¶2–¶3：`operator new(size, ptr)` 返回 `ptr`，并有意不执行其他任何动作。¶4 例 1 展示了在已知地址构造对象的用法：`new (place) Something()`。
- ¶5–¶6：数组版本同理。
- ¶7–¶10：两个 placement `operator delete` 什么也不做；placement *new-expression* 中的初始化抛出异常时，默认调用的就是它们（[[expr.new]]）。

!!! note "constexpr placement new {{c++26}}"
    这四个函数在 C++26 中成为 `constexpr`（[[P2747R2]]），于是在常量求值中可以使用 placement new 构造对象，这是 `std::inplace_vector`、constexpr 版 `std::optional` 等的基础。核心语言侧，[[expr.const]] 对常量求值中的 placement new 另有限制（指针必须指向类型相似的对象等）。libc++ 用 `_LIBCPP_CONSTEXPR_SINCE_CXX26` 标注了它们。

```cpp run title="constexpr-placement.cpp" ok
#include <memory>
#include <new>

constexpr int f() {
    std::allocator<int> a;
    int* p = a.allocate(1);
    int* q = ::new (p) int(42);     // C++26：常量求值中允许 placement new
    int r = *q;
    std::destroy_at(q);
    a.deallocate(p, 1);
    return r;
}
static_assert(f() == 42);

int main() {}
```

!!! pitfall "无法“替换”placement new"
    写 `void* operator new(std::size_t, void*)` 的全局定义会与 `<new>` 中的 inline 定义冲突（重定义），而且 ¶1 明确禁止。但你可以在类作用域声明 `operator new(size_t, void*)`。那是类专属的分配函数，会隐藏全局的 placement 形式，使该类的 `new (buf) T` 调用你的版本。标准容器为此总是写 `::new (p) T(...)`，用 `::` 跳过类作用域查找。

## 数据竞争（[new.delete.dataraces]）

!!! std
    Calls to these functions that allocate or deallocate a particular unit of storage shall occur in a single total order, and each such deallocation call shall happen before the next allocation (if any) in this order.

    分配或释放某一特定存储单元的调用必须构成单一全序，并且这个顺序中的每次释放都 happens before 下一次分配（如果有的话）。

¶1 第一句：为判定数据竞争，库版本的 `operator new`/`operator delete`、用户替换版本，以及 C 库的 `aligned_alloc`、`calloc`、`malloc`、`free`、`realloc`，都不得引入数据竞争（[[res.on.data.races]]）。第二句（上面引用的）给出了一个跨线程的同步保证：如果线程 A 释放了一块内存，线程 B 随后分配到了同一块内存，那么 A 的释放 happens before B 的分配（[[intro.races]]）。

这条保证的实际含义是：即使 A 和 B 之间没有任何其他同步，**线程 B 在新分配的内存上写，也不会与线程 A 在释放之前对这块内存的写构成数据竞争**。没有这条规则，线程 A 写完对象后 `delete`、线程 B 再 `new` 得到同一地址，这样一个普通程序在形式上就有数据竞争。

注意这同样约束替换版本：自己写的无锁内存池必须提供这个 happens-before 关系，通常意味着释放时用 release 语义、分配时用 acquire 语义。

## 思考题

!!! question "思考题"
    1. 一个程序只替换了 `void* operator new(std::size_t)`，使用了 `new (std::nothrow) int`，然后 `delete` 它。调用链是怎样的？
    2. 下面的替换违反了什么？
       ```cpp
       void* operator new(std::size_t n) { return std::malloc(n); }
       ```
    3. `operator delete(void*, std::size_t)` 的默认版本会用到 `size` 参数吗？

<details markdown="1">
<summary>展开查看答案与解析</summary>

1. `new (std::nothrow) int` 调用库的 nothrow `operator new(size_t, const nothrow_t&)`，其默认行为（¶7）调用 `operator new(size)`，也就是你的替换版本。`delete` 调用 `operator delete(void*)` 或尺寸版本（由实现选择），尺寸版本默认转发到无尺寸版本（¶14），最终由库默认的 `operator delete(void*)` 回收一块由你的 `operator new` 分配的存储。能否正常工作取决于两者是否恰好使用同一个底层分配器（libc++ 的默认实现基于 `malloc`/`free`，所以替换版本若也用 `malloc` 就碰巧可行）。可移植的做法是：替换 `operator new` 时总是同时替换对应的 `operator delete`。
2. 违反 ¶2 的 *Required behavior*：失败时必须抛 `bad_alloc`，而 `malloc` 失败返回空指针。另外 `malloc(0)` 可以返回空指针，违反 [[basic.stc.dynamic.allocation]] 对零大小请求的要求。由于 *Required behavior* 对替换版本有约束力，这样的程序行为未定义；编译器在 *new-expression* 之后可以假设指针非空并删除空指针检查（当分配函数没有非抛出异常说明时，[[expr.new]] 规定结果非空）。
3. 不会。¶14 规定默认行为是转发给 `operator delete(ptr)`，丢弃 `size`。只有替换的释放函数才可能利用尺寸信息。
</details>

## 小结

!!! summary
    - *Required behavior* 约束替换版本，*Default behavior* 只描述库版本。
    - 抛出版本：成功返回非空对齐指针，失败抛 `bad_alloc`；默认实现循环调用 new_handler；是否用 `malloc` 未指明。
    - nothrow 版本默认转发给抛出版本并吞掉异常；其返回值如同来自抛出版本，可用普通 `delete` 释放。
    - 释放的前置条件：指针来源、对齐实参、大小实参都必须与分配时一致；单对象与数组形式不能混用。
    - 替换无尺寸版本时应当（should）同时替换尺寸版本；替换尺寸版本时必须（shall）同时替换无尺寸版本。
    - placement 形式保留不可替换，C++26 起为 `constexpr`。
    - 对同一存储单元的分配/释放形成全序，释放 happens before 下一次分配，替换版本也要保证这一点。
