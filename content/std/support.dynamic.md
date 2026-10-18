---
title: 动态内存管理
summary: <new> 头文件总览——全局 operator new/delete 家族、nothrow_t、align_val_t、destroying_delete_t、new_handler、std::launder，以及 hardware_destructive/constructive_interference_size
status: done
covers: support.dynamic.general, new.syn, hardware.interference
related: new.delete, alloc.errors, ptr.launder, basic.stc, expr.new, expr.delete, basic.align, basic.life, intro.races
tags: 标准库, operator new, align_val_t, destroying_delete, 伪共享
updated: 2026-10-18
---

`new` 和 `delete` 是**核心语言**的表达式（[[expr.new]]、[[expr.delete]]），但它们获取和归还存储所用的**分配函数**和**释放函数**，是**库**提供的——就在 `<new>` 里。核心语言在 [[basic.stc.dynamic]] 里规定了这些函数"必须长什么样、必须满足什么契约"；本节规定标准库**提供的版本**做什么、程序**替换**它们时必须遵守什么。

¶1（[support.dynamic.general]）：`<new>` 定义了管理程序中动态存储分配的若干函数，以及报告存储管理错误的组件。

本节的子条款：

| 子条款 | 内容 | 笔记 |
|---|---|---|
| [new.syn] | `<new>` 概要 | 本页 |
| [new.delete] | 全局 `operator new`/`operator delete` 的 22 个签名 | [[new.delete]] |
| [alloc.errors] | `bad_alloc`、`bad_array_new_length`、`new_handler` | [[alloc.errors]] |
| [ptr.launder] | `std::launder` | [[ptr.launder]] |
| [hardware.interference] | 缓存行大小常量 | 本页 |

## `<new>` 概要：一张地图（[new.syn]）

整个头文件是 freestanding 的（`// all freestanding`）。按用途分组：

```cpp
namespace std {
  class bad_alloc;                       // 分配失败
  class bad_array_new_length;            // 数组长度非法

  struct destroying_delete_t { explicit destroying_delete_t() = default; };
  inline constexpr destroying_delete_t destroying_delete{};

  enum class align_val_t : size_t {};    // 对齐分配的标签

  struct nothrow_t { explicit nothrow_t() = default; };
  extern const nothrow_t nothrow;

  using new_handler = void (*)();
  new_handler get_new_handler() noexcept;
  new_handler set_new_handler(new_handler new_p) noexcept;

  template<class T> constexpr T* launder(T* p) noexcept;

  inline constexpr size_t hardware_destructive_interference_size  = implementation-defined;
  inline constexpr size_t hardware_constructive_interference_size = implementation-defined;
}
// 全局作用域：operator new/new[]/delete/delete[] 的 22 个声明，见 [new.delete]
```

注意分配/释放函数声明在**全局命名空间**，不在 `std` 里——这是 [[basic.stc.dynamic.general]] 的要求：它们在每个翻译单元中都**隐式声明**，即使不包含 `<new>`。包含 `<new>` 只是为了拿到 `std::nothrow`、`std::align_val_t` 等配套类型，以及 placement 形式（它们**不**隐式声明）。

### 三个"标签类型"

`nothrow_t`、`align_val_t`、`destroying_delete_t` 都不携带运行时数据（`align_val_t` 除外），它们的作用是**参与重载决议**，把不同语义的分配/释放函数区分开：

**`std::nothrow_t` / `std::nothrow`**：`new (std::nothrow) T` 会把 `std::nothrow` 作为 placement 实参传给 `operator new(size_t, const nothrow_t&)`，分配失败时返回空指针而不是抛异常（[[new.delete.single#5]]）。构造函数是 `explicit` 的默认构造函数——这是 C++ 库中"标签类型"的惯用写法，目的是禁止从 `{}` 隐式构造出标签（`std::nothrow_t t = {};` 非良构）。

**`std::align_val_t`**（C++17）：一个底层类型为 `size_t` 的作用域枚举，用来传递对齐值。当 *new-expression* 分配的类型具有**超出 new 扩展对齐**（new-extended alignment，即 `alignof(T) > __STDCPP_DEFAULT_NEW_ALIGNMENT__`，见 [[basic.align]]）时，编译器调用带 `align_val_t` 参数的版本（[[expr.new]]）。之所以用枚举而不是直接用 `size_t`，是为了不与 `operator new(size_t, size_t)` 这种用户自定义的 placement 形式冲突。

```cpp run title="align-val.cpp" ok
#include <cstdio>
#include <cstdlib>
#include <new>

void* operator new(std::size_t n, std::align_val_t al) {
    std::printf("aligned new: size=%zu align=%zu\n", n, static_cast<std::size_t>(al));
    std::size_t a = static_cast<std::size_t>(al);
    if (void* p = std::aligned_alloc(a, (n + a - 1) / a * a)) return p;   // aligned_alloc 要求 size 为 align 的倍数
    throw std::bad_alloc();
}
void operator delete(void* p, std::align_val_t) noexcept { std::free(p); }

struct alignas(64) CacheLine { char data[64]; };

int main() {
    auto* p = new CacheLine;    // alignof(CacheLine) = 64 > __STDCPP_DEFAULT_NEW_ALIGNMENT__ (16)
    delete p;                   // 调用 operator delete(void*, align_val_t)（或其尺寸版本）
    auto* q = new int;          // 普通对齐：调用 operator new(size_t)，不打印
    delete q;
}
```

**`std::destroying_delete_t` / `std::destroying_delete`**（C++20）：类的成员 `operator delete` 如果第二个参数是 `std::destroying_delete_t`，它就是一个**销毁型 operator delete**（[[g:destroying-operator-delete]]）。*delete-expression* 遇到它时**不先调用析构函数**，而是把尚未析构的对象指针直接交给这个函数，由它负责析构和释放（[[expr.delete]]、[[basic.stc.dynamic.deallocation]]）。典型用途：通过基类指针删除对象时，不用虚析构函数，而是根据对象里的"种类"字段手动分派到正确的派生类析构，并按正确的大小释放存储。

```cpp run title="destroying-delete.cpp" ok
#include <cstdio>
#include <new>

struct Shape {
    enum Kind { circle, square } kind;
    void operator delete(Shape* p, std::destroying_delete_t);   // 销毁型
};
struct Circle : Shape { double r; ~Circle() { std::puts("~Circle"); } };
struct Square : Shape { double a; ~Square() { std::puts("~Square"); } };

void Shape::operator delete(Shape* p, std::destroying_delete_t) {
    // 没有虚析构函数：根据 kind 手动分派，并以正确的静态类型调用 ::delete 以匹配大小
    if (p->kind == circle) ::delete static_cast<Circle*>(p);
    else                   ::delete static_cast<Square*>(p);
}

int main() {
    Shape* s = new Circle{{Shape::circle}, 1.0};
    delete s;      // 调用 Shape::operator delete(s, destroying_delete)，此时 *s 尚未析构
}
```

（`::delete` 跳过类作用域的查找，直接使用全局释放函数；`Circle` 与 `Square` 本身没有声明 `operator delete`，但成员查找会在基类 `Shape` 中找到销毁型版本，所以内部必须用 `::delete` 避免无限递归。）

### `new_handler` 与 `launder`

`new_handler`、`set_new_handler`、`get_new_handler` 见 [[alloc.errors]]；`launder` 见 [[ptr.launder]]。

## 硬件干扰大小（[hardware.interference]）{{c++17}}

两个 `inline constexpr size_t` 常量，值由实现定义，都**至少为 `alignof(max_align_t)`**：

!!! std
    `hardware_destructive_interference_size`: This number is the minimum recommended offset between two concurrently-accessed objects to avoid additional performance degradation due to contention introduced by the implementation.

    两个被并发访问的对象之间推荐的**最小偏移**，以避免由实现引入的争用造成额外的性能下降。

- ¶1 **`hardware_destructive_interference_size`**（"破坏性干扰"）：两个被不同线程频繁写入的对象，应当至少相隔这么远，否则会落在同一缓存行上造成**伪共享**（false sharing）——每次写入都使另一个核心的缓存行失效。用法是 `alignas(std::hardware_destructive_interference_size)`。
- ¶2 **`hardware_constructive_interference_size`**（"建设性干扰"）：两个被**同一线程**以时间局部性一起访问的对象，所占连续内存的推荐**最大**大小——放在这么大的范围内，它们大概率位于同一缓存行，一次缓存未命中就能把两者都带进来。用法是 `static_assert(sizeof(together) <= std::hardware_constructive_interference_size)`。

```cpp run title="interference.cpp" ok
#include <atomic>
#include <new>
#include <thread>

struct Counters {
    alignas(std::hardware_destructive_interference_size) std::atomic<long> a{0};   // 线程 1 写
    alignas(std::hardware_destructive_interference_size) std::atomic<long> b{0};   // 线程 2 写
};

struct Together { std::atomic<int> dog; int puppy; };
static_assert(sizeof(Together) <= std::hardware_constructive_interference_size);

int main() {
    Counters c;
    std::thread t1([&] { for (int i = 0; i < 100000; ++i) c.a.fetch_add(1, std::memory_order_relaxed); });
    std::thread t2([&] { for (int i = 0; i < 100000; ++i) c.b.fetch_add(1, std::memory_order_relaxed); });
    t1.join(); t2.join();
    return c.a + c.b == 200000 ? 0 : 1;
}
```

两个值通常不同：在同一编译目标上，destructive 可能大于 constructive。原因是现代 CPU 的**相邻行预取器**（adjacent-line prefetcher）会成对拉取缓存行，于是"保证不干扰"需要两倍的行宽，而"保证在同一行"只能按一行算。

!!! impl "Clang/libc++ 的取值与 ABI 隐患"
    libc++ 把它们定义为编译器预定义宏 `__GCC_DESTRUCTIVE_SIZE` 和 `__GCC_CONSTRUCTIVE_SIZE`。本机（AArch64 macOS）上 Clang 给出 destructive = 128、constructive = 64。

    这两个值是**由实现定义的编译期常量**，并且可能随 `-mtune`/`-mcpu` 而变。一旦它们出现在头文件里的 `alignas` 中，就影响了类的**布局**——用不同选项编译的两个翻译单元会对同一个类得出不同的布局，违反 ODR（[[basic.def.odr]]）。GCC 为此提供了 `-Winterference-size` 警告。需要跨 ABI 边界的类型，应当硬编码一个具体数值（例如 64 或 128）。

## 思考题

!!! question "思考题"
    1. 为什么 `std::nothrow_t` 的默认构造函数要声明为 `explicit`？
    2. 一个类型 `alignas(32) struct S { ... };`，在 `__STDCPP_DEFAULT_NEW_ALIGNMENT__` 为 16 的平台上，`new S[10]` 调用哪个分配函数？如果 `S` 有成员 `operator new(size_t)` 但没有带 `align_val_t` 的版本呢？

<details markdown="1">
<summary>展开查看答案与解析</summary>

1. 防止从空花括号 `{}` 隐式构造标签。若构造函数不是 `explicit`，一个 `{}` 实参就能复制列表初始化出 `nothrow_t`，标签就失去了"必须显式写出"的意义，并可能让 `f({})` 这类调用意外匹配到带标签参数的重载。复制列表初始化选中 `explicit` 构造函数是非良构的（[[over.match.list]]），所以 `nothrow_t x = {};` 无法编译，只能写 `nothrow_t{}` 或使用 `std::nothrow`。
2. `alignof(S) = 32 > 16`，属于 new 扩展对齐，*new-expression* 先以 `(size, std::align_val_t(32))` 为实参查找 `operator new[]`，找到全局的 `operator new[](size_t, align_val_t)`。若 `S` 声明了成员 `operator new[]`（注意是数组形式）但只有 `(size_t)` 版本，按 [[expr.new#20]]，第一次带对齐实参的重载决议失败后，会**去掉对齐实参**再做一次，于是调用成员的 `operator new[](size_t)`——此时由该函数自己负责满足对齐。若只声明了成员 `operator new`（非数组）则与 `new S[10]` 无关，仍用全局的对齐版本。
</details>

## 小结

!!! summary
    - `<new>` 全部 freestanding；全局分配/释放函数在每个 TU 中隐式声明，placement 形式需要包含 `<new>`。
    - `nothrow_t`、`align_val_t`、`destroying_delete_t` 是用于重载决议的标签；`align_val_t` 是 `size_t` 底层的作用域枚举。
    - 超出 `__STDCPP_DEFAULT_NEW_ALIGNMENT__` 的类型走 `align_val_t` 版本的分配/释放函数。
    - 销毁型 `operator delete` 接管析构与释放，可以替代虚析构函数。
    - `hardware_destructive_interference_size` 用于隔离（防伪共享），`hardware_constructive_interference_size` 用于聚拢；值由实现定义，放进头文件的 `alignas` 有 ABI 风险。
