---
title: 动态内存管理
summary: 头文件 <new> 里有什么：全局分配函数与释放函数、nothrow_t / align_val_t / destroying_delete_t 三个标签类型、new_handler、std::launder，以及用来避免伪共享的两个缓存行大小常量。
status: done
covers: support.dynamic.general, new.syn, hardware.interference
related: new.delete, alloc.errors, ptr.launder, basic.stc, expr.new, expr.delete, basic.align, basic.life, intro.races
tags: 标准库, operator new, align_val_t, destroying_delete, 伪共享
updated: 2026-10-19
---

!!! tldr
    - `new` 和 `delete` 是语言里的表达式，但它们取得和归还内存时调用的 `operator new` / `operator delete` 由库提供，声明在 `<new>` 里。
    - 这些全局函数在每个翻译单元里都已隐式声明，不包含 `<new>` 也能用；`std::nothrow`、`std::align_val_t` 和 placement 形式才需要包含它。
    - `nothrow_t`、`align_val_t`、`destroying_delete_t` 是标签类型，作用是在重载决议里选出不同语义的分配函数或释放函数。
    - `hardware_destructive_interference_size` 用来把两个被不同线程写入的对象隔开，`hardware_constructive_interference_size` 用来把一起访问的数据放进同一缓存行。两者都由实现定义，写进头文件的 `alignas` 会带来 ABI 风险。

## `<new>` 里有什么 [new.syn]

```cpp
std::string* p = new std::string("hi");   // 调用 operator new(sizeof(std::string))，再构造
delete p;                                 // 析构，再调用 operator delete(p, ...)
```

*new-expression* 分两步：先调用一个**分配函数**（allocation function）取得原始内存，再在上面构造对象（[[expr.new]]）。*delete-expression* 反过来，先析构，再调用**释放函数**（deallocation function）归还内存（[[expr.delete]]）。核心语言在 [[basic.stc.dynamic]] 规定这两类函数的形式和必须遵守的约定；库在本节提供它们的默认版本，以及配套的类型。

¶1 [support.dynamic.general] 只有一句话：`<new>` 定义管理动态存储的函数，以及报告存储管理错误的组件。整个头文件是 freestanding 的，即使没有操作系统的独立实现也要提供。按用途分组，它的内容是：

```cpp
namespace std {
  class bad_alloc;                       // 分配失败，见 [alloc.errors]
  class bad_array_new_length;            // 数组长度非法

  struct destroying_delete_t { explicit destroying_delete_t() = default; };
  inline constexpr destroying_delete_t destroying_delete{};

  enum class align_val_t : size_t {};    // 传递对齐值

  struct nothrow_t { explicit nothrow_t() = default; };
  extern const nothrow_t nothrow;

  using new_handler = void (*)();        // 内存不足时的回调，见 [alloc.errors]
  new_handler get_new_handler() noexcept;
  new_handler set_new_handler(new_handler new_p) noexcept;

  template<class T> constexpr T* launder(T* p) noexcept;   // 见 [ptr.launder]

  inline constexpr size_t hardware_destructive_interference_size  = implementation-defined;
  inline constexpr size_t hardware_constructive_interference_size = implementation-defined;
}
// 全局作用域：operator new / new[] / delete / delete[] 的 22 个声明，见 [new.delete]
```

分配函数和释放函数声明在全局命名空间，不在 `std` 里。[[basic.stc.dynamic.general]] 要求它们在每个翻译单元中隐式声明，所以 `::operator new(16)` 不包含任何头文件也能调用。placement 形式 `operator new(size_t, void*)` 不会隐式声明，用 `new (buf) T` 之前要包含 `<new>`。

| 子条款 | 内容 | 详见 |
|---|---|---|
| [new.delete] | 22 个全局 `operator new` / `operator delete` 的契约与默认行为 | [[new.delete]] |
| [alloc.errors] | `bad_alloc`、`bad_array_new_length`、`new_handler` | [[alloc.errors]] |
| [ptr.launder] | `std::launder` | [[ptr.launder]] |
| [hardware.interference] | 两个缓存行大小常量 | 本页下文 |

## 三个标签类型

标签类型不携带数据（`align_val_t` 例外），只用来让重载决议选中特定的函数。

### `std::nothrow`：失败时返回空指针

```cpp
T* p1 = new T;                 // 失败时抛 std::bad_alloc
T* p2 = new (std::nothrow) T;  // 失败时得到空指针
```

`new (std::nothrow) T` 把 `std::nothrow` 作为 placement 实参，于是调用 `operator new(size_t, const nothrow_t&)`，这个版本失败时返回空指针（[[new.delete.single#5]]）。

`nothrow_t` 的默认构造函数是 `explicit` 的，标准库的标签类型都这样写。这样 `{}` 不能隐式转换成标签，`std::nothrow_t t = {};` 是非良构的，`f({})` 也不会意外匹配到带标签参数的重载。本机 Clang 对前者报 "chosen constructor is explicit in copy-initialization"。

### `std::align_val_t`：过度对齐的类型 {{c++17}}

```cpp run title="align-val.cpp" ok
#include <cstdio>
#include <cstdlib>
#include <new>

void* operator new(std::size_t n, std::align_val_t al) {
  auto a = static_cast<std::size_t>(al);
  std::printf("new(%zu, align %zu)\n", n, a);
  if (void* p = std::aligned_alloc(a, (n + a - 1) / a * a))
    return p;
  throw std::bad_alloc();
}
void operator delete(void* p, std::align_val_t) noexcept {
  std::free(p);
}

struct alignas(64) Line { char data[64]; };

int main() {
  Line* p = new Line;   // 打印：new(64, align 64)
  delete p;
  int* q = new int;     // 普通对齐：不打印
  delete q;
}
```

宏 `__STDCPP_DEFAULT_NEW_ALIGNMENT__` 给出普通 `operator new(size_t)` 保证的对齐，本机是 16。对齐要求超过它的类型称为具有 **new 扩展对齐**（new-extended alignment，[[basic.align]]）。*new-expression* 为这种类型分配内存时，会多传一个 `std::align_val_t` 实参，调用带对齐参数的版本（[[expr.new]]）。

`align_val_t` 是底层类型为 `size_t` 的作用域枚举，而不是 `size_t` 本身。这样它不会和用户自己定义的 placement 形式 `operator new(size_t, size_t)` 冲突。`aligned_alloc` 要求大小是对齐值的倍数，所以例子里把 `n` 向上取整。

### `std::destroying_delete`：自己负责析构的 `operator delete` {{c++20}}

如果类的成员 `operator delete` 的第二个参数类型是 `std::destroying_delete_t`，它就是一个**销毁型 operator delete**（[[g:destroying-operator-delete]]）。*delete-expression* 遇到它时不调用析构函数，而是把还没析构的对象交给它，由它负责析构和释放（[[expr.delete]]、[[basic.stc.dynamic.deallocation]]）。

```cpp run title="destroying-delete.cpp" ok
#include <cstdio>
#include <new>

struct Shape {
  enum Kind { circle, square } kind;
  void operator delete(Shape* p, std::destroying_delete_t);
};
struct Circle : Shape {
  double r;
  ~Circle() { std::puts("~Circle"); }
};
struct Square : Shape {
  double a;
  ~Square() { std::puts("~Square"); }
};

void Shape::operator delete(Shape* p, std::destroying_delete_t) {
  // 进入这里时 *p 尚未析构；按 kind 分派
  if (p->kind == circle) ::delete static_cast<Circle*>(p);
  else                   ::delete static_cast<Square*>(p);
}

int main() {
  Shape* s = new Circle{{Shape::circle}, 1.0};
  delete s;   // 调用 Shape::operator delete，打印 ~Circle
}
```

`Shape` 没有虚析构函数，通过基类指针 `delete` 本来是未定义行为。销毁型 `operator delete` 让类自己根据 `kind` 字段找到正确的派生类，再以正确的静态类型析构并释放，省掉了虚表指针。

内部要写 `::delete`。`Circle` 自己没有声明 `operator delete`，类作用域查找会在基类里找到这个销毁型版本，不加 `::` 就会无限递归。

## 硬件干扰大小 [hardware.interference] {{c++17}}

```cpp run title="interference.cpp" ok
#include <atomic>
#include <new>
#include <thread>

struct Counters {
  alignas(std::hardware_destructive_interference_size)
    std::atomic<long> a{0};   // 线程 1 写
  alignas(std::hardware_destructive_interference_size)
    std::atomic<long> b{0};   // 线程 2 写
};

struct Together { std::atomic<int> dog; int puppy; };
static_assert(sizeof(Together)
              <= std::hardware_constructive_interference_size);

int main() {
  Counters c;
  std::thread t1([&] { for (int i = 0; i < 100000; ++i) ++c.a; });
  std::thread t2([&] { for (int i = 0; i < 100000; ++i) ++c.b; });
  t1.join(); t2.join();
}
```

如果 `a` 和 `b` 挨在一起，它们会落在同一缓存行。两个核心各写各的变量，但每次写都会让对方缓存里的这一行失效，这叫**伪共享**（false sharing）。两份数据在逻辑上互不相干，性能却像在争用同一个变量。

¶1 `hardware_destructive_interference_size` 是两个被并发访问的对象之间推荐的最小偏移，用来避免实现带来的这种争用。典型用法就是上面的 `alignas`。

¶2 `hardware_constructive_interference_size` 是被并发线程以时间局部性一起访问的两个对象所占连续内存的推荐最大值。把 `dog` 和 `puppy` 控制在这个大小之内，它们大概率在同一缓存行里，一次缓存未命中就能把两者都取进来。典型用法是上面的 `static_assert`。

两个常量都由实现定义，标准只要求它们至少是 `alignof(max_align_t)`。本机（AArch64 macOS）上 Clang 给出 destructive 为 128、constructive 为 64，`sizeof(Counters)` 是 256。destructive 大于 constructive 是常见情况：有的 CPU 会成对预取相邻的缓存行，要互不干扰得隔开两行，要保证在一起只能按一行算。

!!! impl "取值随编译选项变化，有 ABI 风险"
    libc++ 用编译器预定义宏 `__GCC_DESTRUCTIVE_SIZE` 和 `__GCC_CONSTRUCTIVE_SIZE` 定义这两个常量，它们可能随 `-mcpu`、`-mtune` 改变。如果头文件里的类用它们做 `alignas`，用不同选项编译的两个翻译单元会对同一个类得出不同的布局，违反 ODR（[[basic.def.odr]]）。GCC 为此提供 `-Winterference-size` 警告。需要跨越 ABI 边界的类型，应当直接写一个具体的数，比如 64 或 128。

## 思考题

!!! question "思考题"
    `struct alignas(32) S { int x; };`，平台上 `__STDCPP_DEFAULT_NEW_ALIGNMENT__` 是 16。`new S[10]` 调用哪个分配函数？如果 `S` 声明了成员 `operator new[](size_t)`，但没有带 `align_val_t` 的版本呢？

<details markdown="1">
<summary>答案</summary>

`alignof(S)` 是 32，超过 16，属于 new 扩展对齐。*new-expression* 以 `(size, std::align_val_t(32))` 为实参查找 `operator new[]`，没有成员版本时找到全局的 `operator new[](size_t, align_val_t)`。

如果 `S` 有成员 `operator new[](size_t)`，类作用域的查找先找到它。带对齐实参的重载决议失败后，按 [[expr.new#20]] 去掉对齐实参再做一次，于是调用成员的 `operator new[](size_t)`，满足 32 字节对齐成了这个函数自己的责任。只声明了非数组的成员 `operator new` 则与 `new S[10]` 无关。
</details>
