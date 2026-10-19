---
title: 存储的分配与释放
summary: 标准库的 22 个全局 operator new / operator delete：替换版本必须遵守什么、默认版本做什么，nothrow 版本如何转发，释放时大小和对齐要与分配时一致，placement 形式不可替换，以及分配与释放之间的同步保证。
status: done
covers: *
papers: N3778, P0035R4, P2747R2
related: support.dynamic, basic.stc, dcl.fct.def.replace, expr.new, expr.delete, alloc.errors, basic.align, intro.races, replacement.functions
tags: 标准库, operator new, operator delete, 可替换函数, 尺寸释放, 对齐分配
updated: 2026-10-19
---

!!! tldr
    - 程序可以替换全局 `operator new` / `operator delete`。替换版本必须满足 Required behavior：`operator new` 要么返回非空且对齐的指针，要么抛 `bad_alloc`。
    - 默认的 `operator new` 在一个循环里尝试分配，失败时调用 new_handler；它是否用 `malloc` 实现是未指定的，所以 `new` 出来的内存不能交给 `free`。
    - nothrow 版本默认转调普通版本并吞掉异常。只替换 `operator new(size_t)`，`new (std::nothrow)` 也会用到你的版本。
    - 释放时传入的指针、大小和对齐都必须与分配时一致；单对象形式和数组形式不能混用。替换带大小参数的 `operator delete` 时，必须同时替换不带大小参数的版本。
    - placement 形式 `operator new(size_t, void*)` 不可替换，C++26 起是 `constexpr`。同一块存储上的释放 happens before 下一次分配，替换版本也要保证这一点。

## 替换全局 `operator new`

```cpp run title="replace-new.cpp" ok
#include <cstdio>
#include <cstdlib>
#include <new>

void* operator new(std::size_t n) {
  std::printf("my operator new(%zu)\n", n);
  if (void* p = std::malloc(n ? n : 1)) return p;
  throw std::bad_alloc();
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

int main() {
  int* p = new (std::nothrow) int(1);  // 打印：my operator new(4)
  delete p;
}
```

在程序里定义一个签名相同的全局函数，就替换掉了库的版本，整个程序的 `new` 都会用它（[[dcl.fct.def.replace]]）。这个例子同时演示了下文的两条规则：nothrow 版本默认会转调你替换的 `operator new(size_t)`；`malloc(0)` 可能返回空指针，所以零字节的请求要改成至少 1 字节。

库条款用两种措辞描述这些函数（[[structure.specifications]]）：

- **Required behavior**（[[g:required-behavior]]）是对替换版本也有约束力的契约，条文里写作 "This requirement is binding on any replacement versions of these functions"。替换版本违反它，程序的行为未定义（[[res.on.functions]]）。
- **Default behavior**（[[g:default-behavior]]）只描述库自带的版本。替换之后，这部分就不适用了。

所以替换版本可以不调用 new_handler、可以不用 `malloc`，但不能在失败时返回空指针。

## 总则 [new.delete.general]

¶1 除非另有规定，[[basic.stc.dynamic]] 对分配函数和释放函数的要求也适用于库版本。传给这些函数的对齐实参如果不是有效的对齐值（2 的整数次幂，见 [[basic.align]]），行为未定义，例如 `::operator new(16, std::align_val_t(3))`。

¶2 在独立实现上，默认版本是否满足下文的要求由实现定义。注 1 说明，没有堆的平台上调用它们可以导致未定义行为；而在常量求值中这无关紧要，因为对可替换分配函数的调用总是被省略（[[expr.new]]）。*Recommended practice*：只要有一个默认版本满足宿主实现的要求，就应当全部满足。对应的特性测试宏是 `__cpp_lib_freestanding_operator_new`。

## 单对象形式 [new.delete.single]

### 抛异常的 `operator new`（¶1–¶4）

```cpp
void* operator new(std::size_t size);
void* operator new(std::size_t size, std::align_val_t alignment);
```

¶1 它们由 *new-expression* 调用，分配 `size` 字节。类型具有 new 扩展对齐（对齐要求超过 `__STDCPP_DEFAULT_NEW_ALIGNMENT__`）时用第二种，否则用第一种。

¶2 Required behavior：返回指向适当对齐存储的非空指针，否则抛出 `bad_alloc`。

¶3 Default behavior 是一个循环：

1. 尝试分配。这次尝试是否调用 C 库的 `malloc` 或 `aligned_alloc` 是未指定的。
2. 成功就返回指针。失败时，如果当前的 new_handler（[[get.new.handler]]）是空指针，抛出 `bad_alloc`。
3. 否则调用 new_handler。它返回了就回到第 1 步。
4. 分配成功，或者 new_handler 不再返回（抛异常或终止程序），循环结束。

new_handler 的约定见 [[alloc.errors]]。第 4 段说明这两个函数是可替换的。

!!! note "不能用 `free` 释放 `new` 来的内存"
    即使你的平台上默认实现恰好是 `malloc`，标准也没有这样保证。用 `free` 释放 `operator new` 的结果，或者用 `operator delete` 释放 `malloc` 的结果，都违反了下文第 10 段的前置条件，是未定义行为。

### nothrow 版本（¶5–¶9）

```cpp
void* operator new(std::size_t size, const std::nothrow_t&) noexcept;
void* operator new(std::size_t size, std::align_val_t alignment, const std::nothrow_t&) noexcept;
```

¶5 它们由 `new (std::nothrow) T` 调用，供希望用空指针表示失败的程序使用。第 8 段的例子对比了两种写法：`new T` 失败时抛 `bad_alloc`，`new(nothrow) T` 失败时返回空指针。

¶6 Required behavior：返回非空的对齐指针，或者返回空指针。而且返回的指针如同是从对应的普通版本（可能已被替换）得到的。所以 `new (std::nothrow) T` 的结果可以用普通的 `delete` 释放。

¶7 Default behavior：调用 `operator new(size)` 或 `operator new(size, alignment)`，正常返回就返回其结果，抛了异常就返回空指针。这就是开头的例子里 nothrow 版本会调用替换函数的原因。

!!! pitfall "`new (std::nothrow) T` 照样可能抛异常"
    nothrow 只管分配这一步。`T` 的构造函数抛出的异常照样传播出去，在此之前刚分配的存储由 nothrow 版本的 `operator delete` 释放（下文第 19 段）。

### 释放函数（¶10–¶16）

```cpp
void operator delete(void* ptr) noexcept;
void operator delete(void* ptr, std::size_t size) noexcept;
void operator delete(void* ptr, std::align_val_t alignment) noexcept;
void operator delete(void* ptr, std::size_t size, std::align_val_t alignment) noexcept;
```

¶10–¶11 是前置条件，违反任何一条都是未定义行为：

- `ptr` 是空指针，或者是先前某次 `operator new(size_t)` 或 `operator new(size_t, align_val_t)` 返回、尚未被释放的地址；
- 没有对齐参数时，`ptr` 必须来自没有对齐参数的分配函数；有对齐参数时，它必须等于分配时的对齐实参；
- 有大小参数时，它必须等于分配时的大小实参。

换句话说，分配和释放必须配对：对齐分配的内存要用对齐版本释放，传入的大小要和申请时一样。

¶12 它们由 *delete-expression* 调用，使 `ptr` 的值成为无效指针值（[[g:invalid-pointer-value]]）。

¶15 Default behavior：`ptr` 为空时什么也不做，否则回收存储。第 16 段补充，回收的存储什么时候被后续的 `operator new`、`malloc` 等再次分配出去，是未指定的。

¶13 Required behavior：对带大小参数版本的调用可以改为对不带大小参数版本的调用，不影响内存分配。注 1 说明，实现可以让 `operator delete(ptr, size)` 直接调用 `operator delete(ptr)`。第 14 段规定的默认行为正是这样，`size` 被丢弃，只有替换版本才可能用上它。

### 替换时要成对（¶16）

!!! std
    If a replacement function with a size parameter is defined by the program, the program shall also define the corresponding version without the size parameter.

¶16 的规则是不对称的：

| 你替换了 | 标准的要求 | 原因 |
|---|---|---|
| 不带大小的 `operator delete(void*)` | 应当（should）同时替换带大小的版本 | 默认的带大小版本目前转发给你的版本，但注 3 提醒默认行为将来可能改变 |
| 带大小的 `operator delete(void*, size_t)` | 必须（shall）同时替换不带大小的版本 | ¶13 允许实现把带大小的调用改成不带大小的调用，你的函数会被绕过 |

!!! history "尺寸释放与对齐分配"
    带 `size_t` 参数的全局 `operator delete` 由 [[N3778]] 在 C++14 引入。tcmalloc、jemalloc 这类分配器按大小分类管理内存，释放时知道大小就不必查元数据。带 `align_val_t` 的各个形式由 [[P0035R4]] 在 C++17 引入；在那之前，`new` 一个 `alignas(64)` 的类型只能得到基本对齐的内存。对应的特性测试宏是 `__cpp_sized_deallocation` 和 `__cpp_aligned_new`。

### nothrow 释放函数（¶17–¶21）

```cpp
void operator delete(void* ptr, const std::nothrow_t&) noexcept;
void operator delete(void* ptr, std::align_val_t alignment, const std::nothrow_t&) noexcept;
```

`delete` 表达式无法传 placement 实参，所以它不会调用这两个函数。

¶19 实现只在一种情况下调用它们：`new (std::nothrow) T` 里的构造函数抛出异常，需要释放刚分配的存储（[[expr.new]] 中的匹配释放函数）。第 20 段规定默认行为是调用 `operator delete(ptr)` 或 `operator delete(ptr, alignment)`。

## 数组形式 [new.delete.array]

八个数组签名与单对象形式一一对应，Required behavior 相同，默认行为都转发到单对象形式：

| 函数 | 默认行为 |
|---|---|
| `operator new[](size)` / `(size, al)` | ¶3 返回 `operator new(size)` / `operator new(size, al)` |
| nothrow `operator new[]` | ¶7 调用 `operator new[](size)` / `(size, al)`，抛异常则返回空指针 |
| `operator delete[]` 的四个形式 | ¶13 带大小的转发给不带大小的，不带大小的转发给单对象 `operator delete` |
| nothrow `operator delete[]` | ¶18 调用 `operator delete[](ptr)` / `(ptr, al)` |

¶9 的前置条件要求 `ptr` 来自 `operator new[]`。所以即使默认实现之间互相转发，单对象形式和数组形式也不能混用：`delete` 一个 `new[]` 得到的指针是未定义行为。

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
void operator delete[](void* p, std::size_t) noexcept {
  std::free(p);
}

struct Trivial    { int x; };
struct NonTrivial { int x; ~NonTrivial() {} };

int main() {
  delete[] new Trivial[4];     // 16
  delete[] new NonTrivial[4];  // 本机 32：多了 16 字节 cookie
}
```

脚注 168 说明，记住数组有几个元素不是 `operator new[]` 的职责，而是 *new-expression* 和 *delete-expression* 的事。数组 *new-expression* 可以多申请一些空间，在数组前面存放元素个数，这块空间叫 **数组 cookie**。`delete[]` 要据此调用正确次数的析构函数，所以只有元素类型有非平凡析构函数时才需要它。

本机（AArch64 macOS）上 cookie 是 16 字节，记录元素大小和个数；x86-64 的 Itanium ABI 通常只用 8 字节记录个数，那里第二行会打印 24。总之，传给 `operator new[]` 的 `size` 可以大于 `n * sizeof(T)`（[[expr.new]]）。

## placement 形式 [new.delete.placement]

```cpp
constexpr void* operator new  (std::size_t size, void* ptr) noexcept;
constexpr void* operator new[](std::size_t size, void* ptr) noexcept;
constexpr void  operator delete  (void* ptr, void*) noexcept;
constexpr void  operator delete[](void* ptr, void*) noexcept;
```

¶2–¶6 两个 `operator new` 直接返回 `ptr`，有意不做任何其他事情。`new (place) T(...)` 就是借它在已知地址上构造对象。

¶7–¶10 两个 `operator delete` 什么也不做；placement *new-expression* 的初始化抛出异常时，调用的就是它们。

¶1 这四个函数是保留的，程序不能定义自己的版本取代它们（[[constraints]]）。它们不分配内存，所以 [[basic.stc.dynamic]] 的要求对它们不适用。

!!! pitfall "类里的 placement `operator new` 会挡住全局版本"
    在类作用域里声明 `operator new(size_t, void*)` 是允许的，它是这个类专属的分配函数，会使该类的 `new (buf) T` 调用你的版本。标准容器为此总是写 `::new (p) T(...)`，用 `::` 跳过类作用域的查找。

C++26 把这四个函数改成了 `constexpr`（[[P2747R2]]），常量求值中可以用 placement new 构造对象。`std::inplace_vector` 和 `constexpr` 版本的 `std::optional` 都依赖这一点。核心语言另有限制，比如指针必须指向类型合适的存储（[[expr.const]]）。

```cpp run title="constexpr-placement.cpp" ok
#include <memory>
#include <new>

constexpr int f() {
  std::allocator<int> a;
  int* p = a.allocate(1);
  int* q = ::new (p) int(42);   // C++26 起可在常量求值中使用
  int r = *q;
  std::destroy_at(q);
  a.deallocate(p, 1);
  return r;
}
static_assert(f() == 42);

int main() {}
```

本机 Clang 23 在 `-std=c++2c` 下接受这段代码，在 `-std=c++23` 下拒绝 `static_assert`。

## 分配与释放之间的同步 [new.delete.dataraces]

线程 A 写完一个对象后 `delete` 它，线程 B 随后 `new` 一个对象，恰好拿到同一块内存并写入。两个线程之间没有任何其他同步。如果没有额外的规定，A 的写和 B 的写会构成数据竞争。

¶1 规定了两件事。第一，库版本和替换版本的 `operator new` / `operator delete`，以及 C 库的 `aligned_alloc`、`calloc`、`malloc`、`free`、`realloc`，都不能引入数据竞争（[[res.on.data.races]]）。第二：

!!! std
    Calls to these functions that allocate or deallocate a particular unit of storage shall occur in a single total order, and each such deallocation call shall happen before the next allocation (if any) in this order.

对同一块存储的分配和释放构成一个全序，每次释放都 happens before 下一次分配（[[intro.races]]）。于是 A 在释放之前的写 happens before B 在分配之后的写，上面的场景没有数据竞争。

这条规定同样约束替换版本。自己写的无锁内存池必须提供这个 happens-before 关系，一般意味着释放用 release 语义、分配用 acquire 语义。

## 思考题

!!! question "思考题 1"
    下面这个替换版本违反了什么？
    ```cpp
    void* operator new(std::size_t n) { return std::malloc(n); }
    ```

<details markdown="1">
<summary>答案</summary>

违反了第 2 段的 Required behavior：失败时必须抛 `bad_alloc`，而 `malloc` 失败返回空指针。另外 `malloc(0)` 可以返回空指针，违反了 [[basic.stc.dynamic.allocation]] 对零字节请求也要返回非空唯一指针的要求。

Required behavior 约束替换版本，所以这样的程序行为未定义。编译器确实会利用这一点：分配函数没有非抛出的异常说明时，*new-expression* 的结果不会是空指针，之后的空指针检查可以删掉（[[expr.new]]）。
</details>

!!! question "思考题 2"
    程序只替换了 `operator new(size_t)`，没有替换任何 `operator delete`。`delete new int` 能正常工作吗？

<details markdown="1">
<summary>答案</summary>

不一定。`delete` 会调用库默认的 `operator delete`，它回收的是一块由你的 `operator new` 分配的存储。能否工作取决于两者是否恰好使用同一个底层分配器。libc++ 的默认实现基于 `malloc` / `free`，替换版本也用 `malloc` 时碰巧可行，但这不是标准的保证。可移植的做法是替换 `operator new` 时总是同时替换对应的 `operator delete`，包括带大小的版本。
</details>
