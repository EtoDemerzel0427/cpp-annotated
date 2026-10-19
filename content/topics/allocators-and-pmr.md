---
title: 分配器与 pmr
summary: 从让一个 vector 和其中所有字符串都来自同一个 arena 这个需求出发，讲分配器的要求与 allocator_traits、有状态分配器在复制、移动赋值和交换时的传播规则、uses-allocator 构造与 scoped_allocator_adaptor，以及 std::pmr 的内存资源、性能和常见陷阱。
status: draft
order: 84
since: c++11
papers: N2982, N3916, P0220R1, P0339R6, P2868R3
related: allocator.traits, allocator.uses, allocator.adaptor, default.allocator, mem.res, mem.res.class, mem.poly.allocator.class, mem.res.monotonic.buffer, mem.res.pool, container.requirements.general, utility.requirements, topics/dangling-references, history/modern-library
tags: 分配器, pmr, 内存资源, arena, 专题
updated: 2026-10-19
---

!!! tldr
    - 经典分配器是容器类型的一部分：`vector<T, A>` 和 `vector<T>` 是两个类型，而且容器的分配器只管容器自己的缓冲区，元素（例如 `std::string`）照样用自己的分配器。
    - `allocator_traits` 给分配器补齐默认成员；有状态的分配器在复制赋值、移动赋值、交换时是否跟着走，由三个 `propagate_on_container_*` 决定。分配器不相等时，移动赋值退化为逐个移动元素，交换是 UB。
    - 容器靠 uses-allocator 构造把分配器传给元素。`scoped_allocator_adaptor` 和 `polymorphic_allocator` 的 `construct` 都做这件事，默认的 `allocator_traits::construct` 不做。
    - pmr 把分配策略放进运行期的 `memory_resource`：一个 `monotonic_buffer_resource` 加上 `pmr::vector<pmr::string>`，整个结构的内存都来自同一个 arena，类型却不随资源改变。
    - 用 pmr 要守三条纪律：资源必须比容器活得长；pmr 字符串和普通字符串不能混用；复制容器会退回默认资源。

## 问题：一个 arena 装下整个 `vector<string>`

**arena**（区域分配器）是一种很简单的分配策略：先拿一大块内存，每次分配只是把一个偏移量往前推，单个释放什么也不做，用完后整块一起丢掉。它适合先建一批对象、用一阵、再整体销毁的场景，比如一次请求、一帧画面。

先写一个最小的 arena 分配器，把它交给 `std::vector<std::string>`，并替换全局 `operator new` 来统计有多少次分配走了默认的堆：

```cpp run title="classic.cpp" ok
#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <new>
#include <string>
#include <vector>

int heap_allocs = 0;   // 统计全局 operator new 的调用次数
void* operator new(std::size_t n) {
  ++heap_allocs;
  if (void* p = std::malloc(n)) return p;
  throw std::bad_alloc{};
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

struct Arena {                       // 一块固定缓冲区，只进不退
  alignas(std::max_align_t) std::byte buf[64 * 1024];
  std::size_t used = 0;
  void* take(std::size_t n, std::size_t align) {
    used = (used + align - 1) / align * align;
    void* p = buf + used;
    used += n;
    return p;
  }
};

template <class T>
struct ArenaAlloc {
  using value_type = T;
  Arena* arena = nullptr;
  ArenaAlloc() = default;
  explicit ArenaAlloc(Arena* a) : arena(a) {}
  template <class U> ArenaAlloc(const ArenaAlloc<U>& o) : arena(o.arena) {}
  T* allocate(std::size_t n) {
    if (!arena) throw std::bad_alloc{};
    return static_cast<T*>(arena->take(n * sizeof(T), alignof(T)));
  }
  void deallocate(T*, std::size_t) {}
  bool operator==(const ArenaAlloc& o) const { return arena == o.arena; }
};

int main() {
  Arena arena;
  std::vector<std::string, ArenaAlloc<std::string>> v{ArenaAlloc<std::string>(&arena)};
  v.reserve(100);
  heap_allocs = 0;
  for (int i = 0; i < 100; ++i)
    v.emplace_back("a string long enough to need the heap");
  std::printf("arena bytes: %zu, heap allocs: %d\n", arena.used, heap_allocs);
}
```

```text
arena bytes: 2400, heap allocs: 100
```

arena 里只有 2400 字节，正好是 100 个 `std::string` 对象本身（本机每个 24 字节）。每个字符串的字符缓冲区仍然各自走了一次全局 `operator new`。原因在类型上：`std::string` 是 `basic_string<char, char_traits<char>, std::allocator<char>>`，它有自己的分配器类型，与外层 vector 的分配器毫无关系。

想让字符也进 arena，字符串的类型就得换掉：

```cpp
using AString = std::basic_string<char, std::char_traits<char>, ArenaAlloc<char>>;
std::vector<AString, ArenaAlloc<AString>> v{ArenaAlloc<AString>(&arena)};
v.emplace_back("a string long enough to need the heap");   // 抛出 bad_alloc
```

这样仍然不行。vector 在构造元素时只把 `"a string..."` 传给 `AString` 的构造函数，没有传分配器，于是每个字符串拿到一个默认构造的 `ArenaAlloc`，它不指向任何 arena，第一次分配就抛出 `bad_alloc`。要么每次插入时手动补上 `emplace_back("...", ArenaAlloc<char>(&arena))`，要么让容器自动把分配器往里传。

这个小例子暴露了经典分配器的两个问题：分配策略写在类型里，换策略就要换掉所有相关的类型；容器的分配器不会自动传给元素。

## 分配器是什么

### 最小要求与 `allocator_traits`

标准把分配器的要求叫做 *Cpp17Allocator*（[[allocator.requirements.general]]，本站在 [[utility.requirements]] 里逐条讲解）。一个分配器是一个类类型，它知道怎样为 `T` 的数组分配和释放未初始化的存储。必须自己写的只有几样：`value_type`、`allocate(n)`、`deallocate(p, n)`、从同族分配器转换的构造函数，以及 `==`（[[allocator.requirements.general#98]] 的例 2 就是这样一个最小分配器）。

其余成员都是可选的，由 `allocator_traits<A>` 补上默认值（[[allocator.requirements.general#3]]）。容器从不直接调用分配器，而是一律通过 `allocator_traits` 访问它：

```cpp run title="mini.cpp" ok
#include <cstddef>
#include <list>
#include <memory>
#include <type_traits>

template <class T>
struct Mini {
  using value_type = T;
  Mini() = default;
  template <class U> Mini(const Mini<U>&) {}
  T* allocate(std::size_t n) { return std::allocator<T>{}.allocate(n); }
  void deallocate(T* p, std::size_t n) { std::allocator<T>{}.deallocate(p, n); }
  bool operator==(const Mini&) const = default;
};

using Tr = std::allocator_traits<Mini<int>>;
static_assert(std::is_same_v<Tr::pointer, int*>);
static_assert(std::is_same_v<Tr::size_type, std::make_unsigned_t<std::ptrdiff_t>>);
static_assert(std::is_same_v<Tr::rebind_alloc<long>, Mini<long>>);
static_assert(!Tr::propagate_on_container_move_assignment::value);
static_assert(Tr::is_always_equal::value);          // 空类

int main() {
  std::list<int, Mini<int>> l{1, 2, 3};   // 实际分配的是节点：Mini<节点类型>
}
```

每个默认值的规则见 [[allocator.traits.types]]。其中三条最常用：

- `pointer` 默认是 `T*`。分配器也可以给出类类型的[[g:fancy-pointer|花式指针]]，比如共享内存里用的偏移指针。
- `allocate` 只分配存储，不构造元素。构造和销毁由 `allocator_traits::construct`、`destroy` 完成，分配器没有提供这两个成员时，就直接调用 `construct_at(p, args...)` 和 `destroy_at(p)`（[[allocator.traits.members#6]]、[[allocator.traits.members#7]]）。
- `rebind_alloc<U>` 把 `Mini<int>` 变成 `Mini<U>`（[[allocator.traits.types#11]]）。`std::list<int, Mini<int>>` 真正要分配的是内部的节点类型，它通过 rebind 得到 `Mini<节点>`，再用转换构造函数从用户给的 `Mini<int>` 构造出来。

两个分配器 `a1 == a2` 的含义是：一个分配的存储可以由另一个释放（[[allocator.requirements.general#54]]）。下文讲传播时要用到这个定义。

### 为什么分配器是类型的一部分

容器把分配器对象存在自己里面，所有分配都是对它的普通（非虚）调用，编译器可以内联。分配器是空类时，库实现还可以把它压缩到零字节。这样的设计对 `std::allocator` 没有任何额外开销，代价是分配策略成了类型的一部分：

<div class="compare" markdown="1">

```cpp error
// Mini 是上文的分配器
void print(const std::vector<int>&);

void f() {
  std::vector<int, Mini<int>> v{1, 2};
  print(v);  // error: 类型不同
}
```

```cpp ok
void print(const std::pmr::vector<int>&);

void f() {
  std::pmr::monotonic_buffer_resource r;
  std::pmr::vector<int> v({1, 2}, &r);
  print(v);  // OK：资源不在类型里
}
```

</div>

左边，一个只想读 vector 的函数也得为每种分配器写一份，或者写成模板。右边是后文的 pmr 方案：分配策略换成运行期的指针，类型保持不变。

## 有状态的分配器与传播

`std::allocator` 没有数据成员，任何两个实例都相等。`ArenaAlloc` 存着一个 `Arena*`，指向不同 arena 的两个实例不相等，这种分配器叫做有状态的。它带来一个问题：容器复制、赋值、交换的时候，分配器要不要跟着元素走？

标准的回答是：容器的分配器在构造时确定，此后只能在复制赋值、移动赋值、交换时被替换，而且只有对应的特征为真时才替换（[[container.reqmts#64]]）：

| 操作 | 决定分配器的成员 | 默认值 | 标准分配器 |
|---|---|---|---|
| 复制构造 `X b(a)` | `select_on_container_copy_construction()` | 返回 `a` 的分配器的副本 | 同默认 |
| 移动构造 `X b(std::move(a))` | 总是从 `a` 的分配器移动构造 | | |
| 复制赋值 `b = a` | `propagate_on_container_copy_assignment`（POCCA） | `false_type` | 假 |
| 移动赋值 `b = std::move(a)` | `propagate_on_container_move_assignment`（POCMA） | `false_type` | `std::allocator` 为真 |
| 交换 `a.swap(b)` | `propagate_on_container_swap`（POCS） | `false_type` | 假 |
| 是否总相等 | `is_always_equal` | `is_empty<A>` | `std::allocator` 为真 |

这些默认值的出处是 [[allocator.requirements.general#79]]–¶91 与 [[allocator.traits.types#7]]–¶10；`std::allocator` 的两项见 [[default.allocator.general#2]] 和它的类定义。默认不传播的理由是：分配器代表这块内存属于谁。一个从 arena A 建起来的容器被赋值之后，通常应该仍然留在 arena A。

### 移动赋值：分配器不等时逐个移动

不传播时，复制赋值没有特别之处：左边保留自己的分配器，用它分配存储，再复制元素。移动赋值就不同了。`b = std::move(a)` 想直接接管 `a` 的缓冲区，但如果 `b` 的分配器不能释放这块内存，接管之后就没法正确释放它：

```cpp run title="move-assign.cpp" ok
#include <cstddef>
#include <cstdio>
#include <type_traits>
#include <utility>
#include <vector>

struct Arena {
  alignas(std::max_align_t) std::byte buf[4096];
  std::size_t used = 0;
};
template <class T>
struct ArenaAlloc {
  using value_type = T;
  Arena* arena = nullptr;
  explicit ArenaAlloc(Arena* a) : arena(a) {}
  template <class U> ArenaAlloc(const ArenaAlloc<U>& o) : arena(o.arena) {}
  T* allocate(std::size_t n) {
    void* p = arena->buf + arena->used;
    arena->used += n * sizeof(T);   // 示例只放 int，不处理对齐
    return static_cast<T*>(p);
  }
  void deallocate(T*, std::size_t) {}
  bool operator==(const ArenaAlloc& o) const { return arena == o.arena; }
};
using Vec = std::vector<int, ArenaAlloc<int>>;

int main() {
  Arena a1, a2;
  Vec x({1, 2, 3, 4}, ArenaAlloc<int>(&a1));
  Vec y({5, 6, 7, 8}, ArenaAlloc<int>(&a1));
  Vec z({9, 9, 9, 9, 9, 9}, ArenaAlloc<int>(&a2));

  const int* yd = y.data();
  x = std::move(y);                       // 分配器相等：直接接管缓冲区
  std::printf("same arena:  stole=%d a1.used=%zu\n", x.data() == yd, a1.used);

  const int* zd = z.data();
  x = std::move(z);                       // 分配器不等且 POCMA 为假：逐个移动
  std::printf("other arena: stole=%d a1.used=%zu\n", x.data() == zd, a1.used);

  static_assert(!std::is_nothrow_move_assignable_v<Vec>);
  static_assert(std::is_nothrow_move_assignable_v<std::vector<int>>);
}
```

```text
same arena:  stole=1 a1.used=32
other arena: stole=0 a1.used=56
```

第一次赋值，两个分配器指向同一个 arena，相等就意味着可以互相释放，`x` 直接接管了 `y` 的缓冲区。第二次，`z` 的内存在 `a2` 里，`x` 的分配器不能释放它，`x` 只好在 `a1` 里新分配 6 个 `int`（`a1.used` 增加 24），再把元素逐个移动过去。标准对移动赋值只要求已有元素要么被移动赋值、要么被销毁，复杂度是线性（[[container.alloc.reqmts#27]]、¶29）。

逐个移动需要分配内存，可能抛出异常。只有在编译期就能排除这种情况，也就是 POCMA 为真或 `is_always_equal` 为真时，`vector` 的移动赋值才是 `noexcept`。所以上面两个 `static_assert` 都成立：`std::allocator` 两项都为真，`ArenaAlloc` 两项都为假（它有数据成员，`is_empty` 为假）。

### 交换：分配器不等时是 UB

交换的规定更严格。POCS 为假时分配器不交换，两个分配器不相等则行为未定义（[[container.reqmts#65]]）。交换必须是常数时间、不抛异常，没有退化成逐个移动的余地：

```cpp run title="swap.cpp" ub
#include <memory_resource>
#include <vector>
int main() {
  std::pmr::monotonic_buffer_resource r1, r2;
  std::pmr::vector<int> a({1, 2}, &r1);
  std::pmr::vector<int> b({3}, &r2);
  a.swap(b);   // UB：分配器不相等，POCS 为假
}
```

本机 libc++ 默认构建下这段程序正常退出：两个 vector 交换了缓冲区但没有交换分配器，此后 `a` 会拿 `r1` 去释放来自 `r2` 的内存。加上 `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_EXTENSIVE` 后，程序在 `swap` 处陷入并终止。

## 把分配器传给元素：uses-allocator 构造

回到开头的问题。vector 构造元素时调用 `allocator_traits::construct(alloc, p, args...)`，默认就是 `construct_at(p, args...)`，参数里没有分配器。要让元素拿到分配器，`construct` 得改写参数列表。

标准为此定义了[[g:uses-allocator-construction|uses-allocator 构造]]：用分配器 `alloc` 和实参 `args...` 构造 `T` 时，如果 `T` 使用与 `alloc` 兼容的分配器，就按下面两种约定之一把它传进去，否则忽略它（[[allocator.uses.construction#2]]）：

1. 前置约定：调用 `T(allocator_arg, alloc, args...)`，`allocator_arg` 是一个标签对象，用来区分重载；
2. 后置约定：调用 `T(args..., alloc)`。`std::string`、各标准容器用的都是这种。

`T` 是否使用兼容的分配器，由特征 `uses_allocator<T, Alloc>` 判断：`T` 有嵌套类型 `allocator_type`，而且 `Alloc` 能转换成它（[[allocator.uses.trait#1]]）。`uses_allocator_construction_args` 按这些规则产生改写后的参数元组（[[allocator.uses.construction#5]]），对 `pair` 另有重载，逐个成员递归处理。本站的 [[allocator.uses]] 页讲了全部细节。

### `scoped_allocator_adaptor`

C++11 的 `scoped_allocator_adaptor<Outer, Inner...>` 是一个包装分配器：容器自己的内存用外层分配器分配，构造元素时则通过 uses-allocator 构造把内层分配器传给元素（[[allocator.adaptor.members#9]]）。只给一个分配器类型时，内层就是适配器自己，于是嵌套多少层容器都用同一个分配器（[[allocator.adaptor.syn#1]]）。

把开头的例子改成：

```cpp
using AString = std::basic_string<char, std::char_traits<char>, ArenaAlloc<char>>;
using Outer = std::scoped_allocator_adaptor<ArenaAlloc<AString>>;
std::vector<AString, Outer> v{Outer(ArenaAlloc<AString>(&arena))};
v.reserve(100);
for (int i = 0; i < 100; ++i)
  v.emplace_back("a string long enough to need the heap");
```

```text
arena bytes: 7200, heap allocs: 0
```

这次 100 个字符串的字符缓冲区也进了 arena，全局堆一次都没用。`emplace_back` 的参数在 `construct` 里被改写成 `("a string...", ArenaAlloc<char>(&arena))`，正好匹配 `basic_string` 的后置分配器构造函数。

<details class="fine" markdown="1"><summary>本机 libc++ 要求 ArenaAlloc 可默认构造</summary>

如果去掉 `ArenaAlloc() = default;`，上面这段在本机 Clang 23 / libc++ 下编译失败，错误出在 `basic_string(const char*, const Alloc& = Alloc())` 的默认实参。libc++ 的 `uses_allocator_construction_args` 先计算 `is_constructible_v<AString, const char(&)[38]>`，这一检查要实例化默认实参 `ArenaAlloc<char>()`，而这个错误不在 SFINAE 的直接语境里。按 [[allocator.uses.construction#5]] 的写法，`uses_allocator_v` 为真时本不需要看这一项，标准是否允许这样的实现，本页不下结论。给分配器一个默认构造函数可以绕开它。

</details>

scoped 适配器让元素拿到了分配器，但分配策略仍然写在类型里，而且 `AString` 这种类型很难和接受 `std::string` 的代码互通。

## pmr：把分配策略移到运行期

C++17 的 `<memory_resource>`（命名空间 `std::pmr`）换了一个思路：把分配策略放进一个带虚函数的对象里，分配器类型本身固定不变。

- `memory_resource` 是抽象基类，公有接口 `allocate(bytes, align)`、`deallocate(p, bytes, align)`、`is_equal(other)` 转调私有的虚函数 `do_allocate`、`do_deallocate`、`do_is_equal`（[[mem.res.class]]）。自己写一个资源，就是派生它并实现这三个函数。
- `polymorphic_allocator<T>` 满足 *Cpp17Allocator*，内部只存一个 `memory_resource*`。用不同资源构造的同一个特化，行为可以完全不同，类型却一样（[[mem.poly.allocator.class.general#1]]）。
- 标准容器和字符串在 `std::pmr` 里都有对应的别名，如 `namespace pmr { template<class T> using vector = std::vector<T, polymorphic_allocator<T>>; }`（[[vector.syn]]），`pmr::string` 就是 `basic_string<char, char_traits<char>, polymorphic_allocator<char>>`。

最关键的是 `polymorphic_allocator::construct`：它对元素做 uses-allocator 构造（[[mem.poly.allocator.mem#15]]）。所以 pmr 不需要 scoped 适配器，资源会自动传到嵌套的 pmr 元素里：

```cpp run title="pmr-arena.cpp" ok
#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <memory_resource>
#include <new>
#include <string>
#include <vector>

int heap_allocs = 0;
void* operator new(std::size_t n) {
  ++heap_allocs;
  if (void* p = std::malloc(n)) return p;
  throw std::bad_alloc{};
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

int main() {
  alignas(std::max_align_t) std::byte buf[16 * 1024];
  std::pmr::monotonic_buffer_resource arena(
      buf, sizeof buf, std::pmr::null_memory_resource());   // 用完就抛 bad_alloc

  std::pmr::vector<std::pmr::string> v(&arena);
  for (int i = 0; i < 100; ++i)
    v.emplace_back("a string long enough to need the heap");

  std::printf("heap allocs: %d\n", heap_allocs);
  std::printf("same resource: %d\n",
              v[42].get_allocator().resource() == &arena);
}
```

```text
heap allocs: 0
same resource: 1
```

vector 的缓冲区、每次扩容后的新缓冲区、100 个字符串的字符，全部来自栈上的 16 KB 缓冲区。上游资源设成 `null_memory_resource()`，缓冲区一旦不够用就抛出 `bad_alloc`，而不是悄悄改用堆，所以程序正常结束本身就证明了所有内存都来自 arena。

### 标准提供的资源

| 资源 | 行为 | 条款 |
|---|---|---|
| `new_delete_resource()` | 用 `::operator new`、`::operator delete`；默认资源的初始值 | [[mem.res.global#1]] |
| `null_memory_resource()` | `allocate` 总是抛出 `bad_alloc`，`deallocate` 什么也不做 | [[mem.res.global#2]] |
| `monotonic_buffer_resource` | arena：在当前缓冲区里推进指针，不够时向上游要一块更大的；`deallocate` 什么也不做，析构或 `release()` 时整体归还 | [[mem.res.monotonic.buffer]] |
| `unsynchronized_pool_resource` | 按块大小分成若干池，释放的块可以复用；不能多线程同时访问 | [[mem.res.pool]] |
| `synchronized_pool_resource` | 同上，但可以多线程同时访问 | [[mem.res.pool]] |

后三种都有一个上游资源（upstream），自己的内存从上游取。资源可以这样一层层叠起来，例如池资源以 arena 为上游。

`monotonic_buffer_resource` 的 `do_deallocate` 什么也不做（[[mem.res.monotonic.buffer.mem#7]]），占用的内存只增不减（¶9）。vector 扩容时丢下的旧缓冲区、被删除的字符串，在 arena 销毁前都不会回收。往 arena 里放会反复增删的容器时，先 `reserve`，或者改用池资源。

### 默认资源

没有显式给资源时，pmr 用[[g:default-memory-resource-pointer|默认内存资源指针]]：初值是 `new_delete_resource()`，可以用 `set_default_resource` 修改，用 `get_default_resource` 读取（[[mem.res.global#3]]–¶7）。默认构造的 `polymorphic_allocator` 取当时的默认资源（[[mem.poly.allocator.ctor#1]]），`monotonic_buffer_resource()` 和池资源的默认构造函数也把当时的默认资源当作上游。

测试时常把默认资源设成 `null_memory_resource()`：任何本应指定资源却忘了指定的地方都会立刻抛出 `bad_alloc`。下文的陷阱一节就用了这个办法。

### `polymorphic_allocator` 为什么不传播

`polymorphic_allocator` 的设计原则是：容器在构造时绑定一个资源，一生不变（[[mem.poly.allocator.class]] 页有详细讨论）。具体有三条：

1. 复制赋值运算符被弃置，分配器对象不能改指向别的资源；
2. 没有定义任何 `propagate_on_container_*`，三项都取默认的假；
3. `select_on_container_copy_construction()` 返回默认构造的 `polymorphic_allocator`，也就是默认资源，标准的注明说内存资源不传播（[[mem.poly.allocator.mem#18]]、¶19）。

资源往往绑定在某个作用域上，比如函数里的一个 arena。如果复制容器时自动继承资源，副本被存到别处、活得比 arena 更久，就会悬垂。让副本退回默认资源，是用一点意外换安全。需要副本也在同一个资源里时，显式地传进去：`std::pmr::vector<T> copy(v, &arena);`。

不传播的另一面是：pmr 容器的 `is_always_equal` 也为假，所以 `pmr::vector` 的移动赋值不是 `noexcept`，用不同资源的两个 pmr 容器之间移动赋值会逐个移动元素，交换则是上一节的 UB。

## 性能：本机观测

下面比较三种方式构造一个装着 10 万个 37 字符字符串的 vector，再销毁它。字符串长度超过[[g:short-string-optimization|短字符串优化]]的内部缓冲区，每个都要单独分配：

```cpp run title="bench.cpp" ok
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <memory_resource>
#include <string>
#include <vector>

constexpr int N = 100'000, ROUNDS = 50;
const char* text = "a string long enough to need the heap";

template <class F> double best_ms(F f) {
  double best = 1e9;
  for (int r = 0; r < ROUNDS; ++r) {
    auto t0 = std::chrono::steady_clock::now();
    f();
    auto t1 = std::chrono::steady_clock::now();
    best = std::min(best, std::chrono::duration<double, std::milli>(t1 - t0).count());
  }
  return best;
}

int main() {
  double heap = best_ms([] {
    std::vector<std::string> v;
    v.reserve(N);
    for (int i = 0; i < N; ++i) v.emplace_back(text);
  });
  double mono = best_ms([] {
    std::pmr::monotonic_buffer_resource arena;
    std::pmr::vector<std::pmr::string> v(&arena);
    v.reserve(N);
    for (int i = 0; i < N; ++i) v.emplace_back(text);
  });
  double pool = best_ms([] {
    std::pmr::unsynchronized_pool_resource pool;
    std::pmr::vector<std::pmr::string> v(&pool);
    v.reserve(N);
    for (int i = 0; i < N; ++i) v.emplace_back(text);
  });
  std::printf("std::allocator   %.2f ms\n", heap);
  std::printf("monotonic arena  %.2f ms\n", mono);
  std::printf("unsync pool      %.2f ms\n", pool);
}
```

本机（Apple M2 Pro，macOS，Clang 23 `-O2`，libc++）连续三次运行，每项取 50 轮中最快的一轮：

| 方式 | 时间 |
|---|---|
| `std::vector<std::string>` | 约 3.3 ms |
| `monotonic_buffer_resource` | 约 1.2 ms |
| `unsynchronized_pool_resource` | 约 1.6 ms |

arena 快的原因有两个：每次分配只是推进指针，不经过系统分配器；销毁时 10 万次 `free` 变成了一次整体归还。这只是一台机器、一种负载上的观测，换一个系统分配器（如 jemalloc、mimalloc）、换字符串长度，差距都会变。另外 pmr 的每次分配多一次虚函数调用，分配很少的场合不会有收益。是否值得用，以自己程序的测量为准。

## 陷阱

### 资源比容器先死

```cpp run title="lifetime.cpp" ub
#include <cstdio>
#include <memory_resource>
#include <string>
#include <vector>

std::pmr::vector<std::pmr::string> load() {
  std::pmr::monotonic_buffer_resource arena;   // 局部资源
  std::pmr::vector<std::pmr::string> v(&arena);
  v.emplace_back("a string long enough to need the heap");
  return v;                                    // v 被移出，资源却在这里销毁
}

int main() {
  auto v = load();
  std::printf("%s\n", v[0].c_str());           // UB：内存已还给上游
}
```

`return v;` 移动构造返回值，分配器随之移动，返回的 vector 仍然指向局部的 `arena`。`arena` 在函数结束时析构，把所有内存还给上游，返回的 vector 从此悬垂（参见 [[topics/dangling-references]]）。容器析构时还会对一个已经销毁的资源调用虚函数 `deallocate`，同样是 UB。AddressSanitizer 的报告：

```text
$ clang++ -std=c++2c -g -gdwarf-4 -fsanitize=address,undefined lifetime.cpp && ./a.out
==ERROR: AddressSanitizer: heap-use-after-free on address 0x61d000000877 ...
    #4 ... in main lifetime.cpp:15
freed by thread T0 here:
    #2 ... in std::__1::pmr::monotonic_buffer_resource::release() ...
    #3 ... in std::__1::pmr::monotonic_buffer_resource::~monotonic_buffer_resource() ...
    #5 ... in load() lifetime.cpp:11
```

编译器对此没有任何警告。资源要放在比所有使用者都长的作用域里，常见做法是由调用方持有资源，把指针传进来。

### pmr 字符串和普通字符串混用

`std::string` 和 `std::pmr::string` 是两个不相关的类型，彼此之间没有隐式转换：

```cpp
void take_std(const std::string&);
void take_view(std::string_view);

void f(std::pmr::vector<std::pmr::string>& v, const std::string& s) {
  take_std(v[0]);              // error: 没有匹配的函数
  v.push_back(s);              // error: 没有匹配的成员函数
  std::string t = v[0];        // error: 没有可行的转换
  take_std(std::string(v[0])); // OK：复制一份到默认堆
  v.emplace_back(s);           // OK：在 v 的资源里复制一份
  take_view(v[0]);             // OK：不复制
}
```

能编译的写法都要显式构造一个新字符串，每次都是一次分配加一次复制。接口的形参用 `std::string_view` 可以同时接受两种字符串，而且不复制。

更隐蔽的是元素类型写错了：`std::pmr::vector<std::string>` 能编译，vector 的缓冲区在 arena 里，但 `std::string` 的 `allocator_type` 是 `std::allocator<char>`，`polymorphic_allocator` 不能转换成它，`uses_allocator` 为假，资源被忽略，字符照样走全局堆。即使把默认资源设成 `null_memory_resource()` 也查不出来，因为 `std::string` 根本不经过 pmr。

### 复制容器退回默认资源

```cpp run title="copy.cpp" ok
#include <cstdio>
#include <memory_resource>
#include <new>
#include <string>
#include <vector>

int main() {
  std::pmr::monotonic_buffer_resource arena;   // 上游取此刻的默认资源：new_delete
  std::pmr::set_default_resource(std::pmr::null_memory_resource());  // 守卫

  std::pmr::vector<std::pmr::string> v(&arena);
  v.emplace_back("a string long enough to need the heap");

  auto moved = std::move(v);                        // 移动：分配器跟着走
  std::printf("moved uses arena: %d\n",
              moved.get_allocator().resource() == &arena);

  std::pmr::vector<std::pmr::string> same(moved, &arena);   // 显式指定资源
  std::printf("explicit copy ok, size %zu\n", same.size());

  try {
    auto copy = moved;                              // 复制：退回默认资源
  } catch (const std::bad_alloc&) {
    std::puts("copy went to the default resource");
  }
}
```

```text
moved uses arena: 1
explicit copy ok, size 1
copy went to the default resource
```

移动构造从原容器的分配器移动构造新分配器（[[container.alloc.reqmts#16]]），资源不变。`auto copy = moved;` 是复制构造，分配器来自 `select_on_container_copy_construction()`，即默认资源，这里被守卫拦下。注意 `arena` 要在设置守卫之前构造，否则它的上游也会是 `null_memory_resource()`。

同样的退回也发生在按值传参、按值返回一个数据成员、lambda 按值捕获等一切复制构造的场合。凡是需要副本留在原资源里的地方，都要用带分配器参数的构造函数 `X(t, alloc)`（[[container.alloc.reqmts#14]]）。

!!! history
    C++98 的分配器被认为是无状态的，实现可以假定同类型的分配器都相等。C++11 以 `allocator_traits` 重建了分配器模型（[[N2982]]），有状态的分配器从此有了明确的传播规则，同一时期还加入了 `scoped_allocator_adaptor`。pmr 由 [[N3916]] 提出，先进入库基础技术规范，C++17 经 [[P0220R1]] 并入标准。C++20 的 [[P0339R6]] 把 `polymorphic_allocator` 的默认模板实参定为 `byte`，并加入 `allocate_bytes`、`new_object` 等成员，让 `polymorphic_allocator<>` 可以作为通用的分配器类型使用。

## 思考题

!!! question "1"
    `std::pmr::vector<std::pmr::vector<int>> outer(&arena); outer.emplace_back();` 新插入的内层 vector 用哪个资源？如果写成 `outer.push_back(std::pmr::vector<int>{1, 2});` 呢？

<details markdown="1">
<summary>答案</summary>

`emplace_back()` 用 uses-allocator 构造，内层 vector 调用 `vector(const allocator_type&)`，资源是 `arena`。

`push_back(std::pmr::vector<int>{1, 2})` 先用默认资源构造一个临时 vector，再用它构造元素。`polymorphic_allocator::construct` 把实参改写成 `(std::move(tmp), alloc)`，调用的是带分配器的移动构造函数 `X(rv, m)`。新元素的资源是 `arena`；临时量的资源是默认资源，两者不相等，所以元素被逐个移动到 arena 中，复杂度是线性的（[[container.alloc.reqmts#19]]、¶20）。临时量本身的那次分配走的是默认资源。
</details>

!!! question "2"
    一个分配器把 POCCA、POCMA、POCS 都设为 `true_type`。用它的两个容器交换之后，各自的元素还在原来的 arena 里吗？

<details markdown="1">
<summary>答案</summary>

在。POCS 为真时，交换会同时交换缓冲区和分配器（[[container.reqmts#65]]），元素的内存没有移动，只是换了主人，而新主人拿到的正是能释放这块内存的分配器。所以交换不再是 UB。代价是容器的主人随交换改变：交换前属于 arena A 的容器，交换后用的是 arena B，如果 B 先销毁，这个容器就悬垂了。
</details>

!!! question "3"
    `std::allocator` 曾经定义成员类型 `is_always_equal = true_type`，C++26 把它删除了（[[P2868R3]]），而 `allocator_traits<std::allocator<T>>::is_always_equal` 仍然为真。删除它有什么好处？

<details markdown="1">
<summary>答案</summary>

`allocator_traits` 在分配器没有这个成员时取 `is_empty<A>`，`std::allocator` 是空类，结果照样为真，所以删除对它自己没有影响。

问题出在派生类。有人从 `std::allocator<T>` 派生出一个带状态的分配器（比如加一个 `Arena*` 成员），成员类型 `is_always_equal` 也被继承下来，容器就会认为任意两个实例都相等：移动赋值直接接管另一个 arena 的缓冲区，用错误的分配器释放内存。删除成员后，派生类的 `is_always_equal` 回到 `is_empty`，为假，这才是正确的答案。本机 libc++ 在 `-std=c++20` 下对这样的派生类给出 `true`，在 `-std=c++2c` 下给出 `false`。继承来的 POCMA 为真则没有这个问题，它只是让分配器随缓冲区一起移动，不会造成错误的释放。
</details>

## 小结

| 问题 | 经典分配器 | pmr |
|---|---|---|
| 分配策略在哪里 | 分配器类型里，编译期确定 | `memory_resource` 对象里，运行期确定 |
| 不同策略的容器类型相同吗 | 不同 | 相同 |
| 元素怎样拿到分配器 | 默认拿不到；用 `scoped_allocator_adaptor` | `polymorphic_allocator::construct` 自动做 uses-allocator 构造 |
| 复制构造 | 默认复制分配器 | 退回默认资源 |
| 赋值、交换 | 看 POCCA、POCMA、POCS | 都不传播；资源不同时移动赋值逐个移动，交换是 UB |
| 每次分配的开销 | 可以内联 | 一次虚函数调用 |
| 主要风险 | 类型膨胀，接口难以复用 | 资源寿命、混用字符串、复制后换了资源 |
