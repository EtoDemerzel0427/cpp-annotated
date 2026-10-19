---
title: 堆分配的代价
summary: 一次 new/delete 在本机要多少纳秒，怎样替换全局 operator new 来数分配次数，string、function、vector、节点容器、shared_ptr 和异常里藏着的分配，编译器何时可以删掉一对 new/delete，以及复用、对象池、内联存储、对齐分配和多线程分配的实测。
status: draft
order: 60
group: 内存
since: c++98
papers: N3664, P0035R4
related: new.delete.single, expr.new, expr.delete, dcl.fct.def.replace, basic.stc.dynamic.allocation, basic.align, allocator.members, func.wrap.func.con, vector.capacity, except.throw, util.smartptr.shared.create, inplace.vector, topics/allocators-and-pmr, topics/ownership-and-smart-pointers, toolchain/exception-implementation, perf/measuring, perf/copies-and-moves, perf/choosing-containers, perf/false-sharing
tags: 性能, 内存分配, operator new, SSO, 分配省略, 对象池, 对齐
updated: 2026-10-19
---

!!! tldr
    - 本机（Apple M2 Pro，macOS 自带的 libmalloc）上，一次小块 `malloc` + `free` 约 20 ns，64 KiB 以上的块约 100 ns。程序慢通常是因为分配次数多，而不是单次分配贵。
    - 替换全局 `operator new` 就能数出分配次数。但标准允许编译器省略 *new-expression* 对它的调用，开了优化后计数可能变少，被数的指针要先逃逸。
    - 很多分配藏在库里：超过 22 个字符的 `std::string`（libc++）、捕获超过 16 字节的 `std::function`、`vector` 的每次扩容、`map`/`list` 的每个节点、`shared_ptr<T>(new T)` 的控制块，还有异常对象。
    - 避免分配的办法有四种：`reserve`、`clear()` 之后复用容量、对象池或 arena、把前几个元素放在对象内部的小容器。
    - 过度对齐的 `new` 在本机没有额外开销；多个线程同时分配时，每次操作的 CPU 时间随线程数增加。

计时程序都用 [[perf/measuring#harness|bench.hpp]]：`bench::run` 先预热，再取 31 个样本的中位数；`bench::do_not_optimize(x)` 是一条不生成指令的内联汇编，让编译器认为 `x` 被读写过，不能删掉产生它的代码。

所有数字都是本机（Apple M2 Pro，macOS，Homebrew Clang 23 + libc++，`-O2`，arm64）的观测。测量时机器上有大量后台负载，表中取的是多次运行里稳定的中位数，绝对值只作量级参考，同一次运行中的相对比较更可靠。换硬件、换系统分配器（glibc、jemalloc、mimalloc），结果都会变。

## 一次分配要多少时间

```cpp title="malloc-sizes.cpp"
#include "bench.hpp"
#include <cstdio>
#include <cstdlib>

int main() {
  bench::prefer_performance_cores();
  constexpr int K = 1000;
  static void* ptrs[K];
  for (std::size_t n : {16, 64, 256, 1024, 4096, 16384,
                        65536, 262144, 1048576}) {
    char name[32];
    std::snprintf(name, sizeof name, "pair %zu", n);
    bench::run(name, [n] {               // 分配后立刻释放
      void* p = std::malloc(n);
      bench::do_not_optimize(p);
      std::free(p);
    });
    std::snprintf(name, sizeof name, "batch %zu (/%d)", n, K);
    bench::run(name, [n] {               // 先分配 K 块，再全部释放
      for (auto& p : ptrs) {
        p = std::malloc(n);
        bench::do_not_optimize(p);
      }
      for (auto p : ptrs) std::free(p);
    });
  }
}
```

`clang++ -std=c++2c -O2 malloc-sizes.cpp`，batch 一列已经除以 1000：

| 大小 | 分配后立刻释放 | 1000 块一批 |
|---|---|---|
| 16 B | 20.7 ns | 18.6 ns |
| 64 B | 21.8 ns | 20.2 ns |
| 256 B | 22.8 ns | 21.2 ns |
| 1 KiB | 26 ns | 34 ns |
| 4 KiB | 20.4 ns | 32 ns |
| 16 KiB | 26 ns | 47 ns |
| 64 KiB | 100 ns | 109 ns |
| 256 KiB | 105 ns | 108 ns |
| 1 MiB | 104 ns | 103 ns |

16 KiB 和 64 KiB 之间有一个台阶，说明分配器对大块走的是另一条更慢的路径。表里的数字是最好情况：同一块内存反复分配和释放，分配器的元数据和这块内存都在缓存里。真实程序里分配和释放交错、跨越很多大小，单次代价只会更高。

这里也没有算第一次写入新内存的代价。新拿到的内存页第一次被写时，操作系统要处理缺页，这部分开销不在 `malloc` 里，而是在之后第一次使用时出现。缓存和缺页的代价见 [[perf/memory-hierarchy|内存层次]]。

20 ns 看起来不多，但一个循环里每次迭代都分配一次，几百万次就是几十毫秒。所以下面先学会数分配次数，再看次数从哪里来。

## 数一数分配了几次

全局 `operator new(std::size_t)` 是**可替换函数**（replaceable function）：程序里定义一个签名相同的非 `inline` 全局函数，整个程序的默认版本就被它取代（[[new.delete.single#4]]、[[dcl.fct.def.replace#1]]）。替换版本仍要满足原来的要求：要么返回非空、对齐合适的指针，要么抛出 `std::bad_alloc`（[[new.delete.single#2]]）。规则的细节见 [[new.delete]]。

```cpp run title="count.cpp" ok
#include <cstdio>
#include <cstdlib>
#include <new>
#include <string>

static int g_news = 0;                 // 全局 operator new 被调用的次数

void* operator new(std::size_t n) {
  ++g_news;
  if (void* p = std::malloc(n ? n : 1)) return p;
  throw std::bad_alloc{};
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

template <class F>
int count_news(F f) {                  // f() 期间发生了几次分配
  int before = g_news;
  f();
  return g_news - before;
}

int main() {
  std::printf("int:        %d\n", count_news([] { delete new int; }));
  std::printf("string(22): %d\n", count_news([] { std::string s(22, 'x'); }));
  std::printf("string(23): %d\n", count_news([] { std::string s(23, 'x'); }));
}
```

本机输出：

| 编译选项 | `int` | `string(22)` | `string(23)` |
|---|---|---|---|
| `-O0` | 1 | 0 | 1 |
| `-O2` | 0 | 0 | 1 |

`-O2` 下 `delete new int` 一次分配也没数到，可是计数器的 `++g_news` 是一个看得见的副作用。编译器能删掉它，是因为标准专门允许这样做，见下一节。

后面的例子都用同一个计数头文件。为了防止分配被省略，它额外提供一个 `escape`，让指针看起来被外部读写过：

```cpp title="count_new.hpp"
#pragma once
#include <cstdio>
#include <cstdlib>
#include <new>

inline int g_news = 0;

// 替换函数不能是 inline，所以这个头文件只能被一个翻译单元包含
void* operator new(std::size_t n) {
  ++g_news;
  if (void* p = std::malloc(n ? n : 1)) return p;
  throw std::bad_alloc{};
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

inline void escape(void* p) { asm volatile("" : : "r"(p) : "memory"); }

template <class F>
int count_news(F f) {
  int before = g_news;
  f();
  return g_news - before;
}
```

## 编译器可以删掉 new 和 delete

```cpp godbolt title="elide.cpp" flags="-std=c++2c -O2" ok
#include <memory>
#include <vector>

int raw() {
  int* p = new int(42);
  int r = *p + 1;
  delete p;
  return r;
}

int smart() {
  auto p = std::make_unique<int>(42);
  return *p + 1;
}

int vec() {
  std::vector<int> v{1, 2, 3};
  return v[0] + v[1] + v[2];
}
```

`clang++ -std=c++2c -O2 -S elide.cpp`，三个函数里都没有对 `operator new` 的调用：

```asm title="AArch64"
__Z3rawv:
	mov	w0, #43
	ret
__Z5smartv:
	mov	w0, #43
	ret
__Z3vecv:
	mov	w0, #6
	ret
```

加上 `--target=x86_64-linux-gnu`，`raw` 同样只剩 `movl $43, %eax`。

!!! std "[expr.new]/14"
    An implementation is allowed to omit a call to a replaceable global allocation function. When it does so, the storage is instead provided by the implementation or provided by extending the allocation of another *new-expression*.

¶14 这句话让分配本身不再是可观察行为。按 [[g:as-if-rule|as-if 规则]]（[[intro.abstract]]），编译器只需保留可观察行为，但用户替换的 `operator new` 可以打印、计数，调用它本来就是可观察的。C++14 的 [[N3664]] 加入了这条许可：即使函数被替换了，*new-expression* 也可以不调用它。对应地，[[expr.delete#6.3]] 规定被省略的分配在 `delete` 时也不调用释放函数。¶16 还允许把满足条件的两次分配合并成一次，细节见 [[expr.new]]。

`vec` 的分配来自 `std::allocator`，不是 *new-expression*。它也能被删掉，是因为 [[allocator.members#5]] 规定存储通过 `::operator new` 获得，但调用的时机和次数未指定。libc++ 在 `std::allocator` 里调用的是 `__builtin_operator_new`，Clang 对它和 *new-expression* 一样处理。

省略需要编译器看清指针的整个生命周期。指针一旦传给看不见定义的函数，分配就留下了：

```cpp godbolt title="noelide.cpp" flags="-std=c++2c -O2" ok
void use(int*);                        // 定义在别的翻译单元
int sink() {
  int* p = new int(42);
  use(p);                              // 指针逃逸
  int r = *p;
  delete p;
  return r;
}
```

这里的汇编保留了 `bl __Znwm` 和 `bl __ZdlPvm`。用 `-fno-builtin` 编译 `elide.cpp`，三个函数也都会保留分配调用。省略是许可，不是义务：哪些分配被删掉取决于编译器、优化级别和内联结果，不可移植。不要指望它来消除热路径上的分配，要确认时就看汇编（[[perf/reading-assembly|读汇编]]）。

## 隐藏的分配

下面的计数都在 `-O2` 下得到，每个被测对象都先 `escape`，所以省略不会让计数变少。

### 字符串：SSO 的边界

**短字符串优化**（[[g:short-string-optimization|SSO]]）把短字符串直接存在 `std::string` 对象内部，不分配。上一节的 `count.cpp` 已经显示 libc++ 的边界：22 个字符不分配，23 个字符分配一次。`std::string{}.capacity()` 在本机是 22，`sizeof(std::string)` 是 24，24 字节里要放下 22 个字符、结尾的空字符和长度信息。标准不要求 SSO，容量多大由实现决定，别的标准库实现不同。

```cpp title="sso.cpp"
#include "bench.hpp"
#include <string>

int main() {
  bench::prefer_performance_cores();
  const char* src = "abcdefghijklmnopqrstuvwxyz";
  for (std::size_t n : {22, 23}) {
    bench::run(n == 22 ? "string(22 chars)" : "string(23 chars)", [&] {
      std::size_t len = n;
      bench::do_not_optimize(len);       // 长度对编译器不透明
      std::string s(src, len);
      bench::do_not_optimize(s);
    });
  }
}
```

本机构造并销毁一个 22 字符的字符串约 6 ns，23 字符约 30 ns，多出来的就是一次分配和释放。键名、标识符、短消息这类字符串如果能控制在 22 个字符以内，在 libc++ 上就不分配。

### `std::function`：小对象缓冲区只有 16 字节

`std::function` 要能存任意大小的可调用对象，放不进内部缓冲区时只能分配。

```cpp title="function.cpp"
#include "count_new.hpp"
#include <array>
#include <functional>

template <int N>
void test() {
  std::printf("%2d-byte capture: %d\n", N, count_news([] {
    std::array<char, N> a{};
    std::function<int()> f = [a] { return a[0]; };
    escape(&f);
  }));
}

int main() { test<16>(); test<17>(); test<24>(); }
```

本机 `sizeof(std::function<int()>)` 是 32，捕获 16 字节的闭包不分配，17 字节和 24 字节各分配一次。标准建议实现对小的可调用对象避免动态分配，举的例子是只含一个对象指针和一个成员函数指针的对象（[[func.wrap.func.con#15]]）。这样的闭包在 arm64 上是 24 字节，libc++ 仍然分配一次。这是建议（Recommended practice），不是要求，所以不算违规。

热路径上的回调可以改用模板参数直接接收可调用对象，或者用不拥有对象、不分配的 `std::function_ref`（{{c++26}}，[[func.wrap.ref]]）。

### `vector` 的增长

```cpp title="growth.cpp"
#include "count_new.hpp"
#include <vector>

int main() {
  std::vector<int> v;
  std::size_t last = v.capacity();
  int n = count_news([&] {
    for (int i = 0; i < 1000; ++i) {
      v.push_back(i);
      if (v.capacity() != last) std::printf("%zu ", last = v.capacity());
    }
  });
  std::printf("\nno reserve: %d allocations\n", n);
  std::printf("reserve:    %d allocation\n", count_news([] {
    std::vector<int> w;
    w.reserve(1000);
    for (int i = 0; i < 1000; ++i) w.push_back(i);
    escape(w.data());
  }));
}
```

```text
1 2 4 8 16 32 64 128 256 512 1024
no reserve: 11 allocations
reserve:    1 allocation
```

libc++ 每次容量翻倍，1000 个元素要分配 11 次，每次还要把已有元素搬到新缓冲区。增长因子是实现细节，标准只要求 `push_back` 的均摊复杂度为常数。`reserve(n)` 之后，只要大小不超过 `n` 就不会再重新分配（[[vector.capacity#7]]）。

计时比较三种写法，每轮都构造 100 个元素：

```cpp title="grow.cpp"
#include "bench.hpp"
#include <vector>

constexpr int N = 100;
std::vector<int> kept;                   // 跨轮复用的缓冲区

int main() {
  bench::prefer_performance_cores();
  bench::run("fresh", [] {
    std::vector<int> v;
    for (int i = 0; i < N; ++i) v.push_back(i);
    bench::do_not_optimize(v);
  });
  bench::run("reserve", [] {
    std::vector<int> v;
    v.reserve(N);
    for (int i = 0; i < N; ++i) v.push_back(i);
    bench::do_not_optimize(v);
  });
  bench::run("clear + reuse", [] {
    kept.clear();                        // 销毁元素，保留容量
    for (int i = 0; i < N; ++i) kept.push_back(i);
    bench::do_not_optimize(kept);
  });
}
```

| 写法 | 分配次数 | 本机中位数 |
|---|---|---|
| 新建，不 `reserve` | 8 | 约 260 ns |
| 新建，`reserve(100)` | 1 | 约 60 ns |
| `clear()` 后复用 | 0 | 约 39 ns |

<details class="fine" markdown="1"><summary>一个没有解释的反例</summary>

把 `N` 改成 1000 后，本机多次运行中 `reserve` 版本反而比不 `reserve` 慢，而两者内层循环的汇编完全相同。原因没有查清，可能和分配到的地址、内存写入模式或机器负载有关。分配次数的差别是确定的，时间上的差别要在自己的负载下测。
</details>

### `push_back` 与 `emplace_back`

`push_back(T(args))` 先构造一个临时对象再把它移进容器，`emplace_back(args)` 直接在容器里构造。对 `std::string` 这样移动只偷指针的类型，两者分配次数相同；只有当类型的移动退化为复制时，`push_back` 才多分配一次：

```cpp title="emplace.cpp"
#include "count_new.hpp"
#include <string>
#include <vector>

struct Legacy {                        // 声明了复制构造，没有移动构造
  std::string s;
  explicit Legacy(const char* p) : s(p) {}
  Legacy(const Legacy&) = default;
};

int main() {
  const char* text = "a string long enough to defeat SSO";
  std::vector<std::string> s;  s.reserve(4);
  std::vector<Legacy> l;       l.reserve(4);
  std::printf("%d %d\n",
    count_news([&] { s.push_back(std::string(text)); }),
    count_news([&] { s.emplace_back(text); }));
  std::printf("%d %d\n",
    count_news([&] { l.push_back(Legacy(text)); }),
    count_news([&] { l.emplace_back(text); }));
}
```

本机输出 `1 1` 和 `2 1`。复制与移动的代价见 [[perf/copies-and-moves|复制与移动的代价]]。

### 节点容器与 `shared_ptr`

同一个计数框架下，本机的结果是：

| 操作 | 分配次数 |
|---|---|
| `std::map<int,int>` 插入 100 个键 | 100 |
| `std::list<int>` `push_back` 100 次 | 100 |
| `std::shared_ptr<Big>(new Big)` | 2 |
| `std::make_shared<Big>()` | 1 |
| `std::vector<std::string>{"a", "b"}` | 1 |

`map`、`set`、`list`、`unordered_map` 的每个元素都在单独分配的节点里，插入一个元素就是一次分配。容器之间的取舍见 [[perf/choosing-containers|选择容器]]。`shared_ptr<T>(new T)` 一次给对象、一次给控制块；`make_shared` 把两者放在一起，标准建议实现只分配一次（[[util.smartptr.shared.create#7.1]]），代价是 `weak_ptr` 会推迟整块内存的释放，见 [[topics/ownership-and-smart-pointers]]。最后一行容易漏看：初始化列表里的两个短字符串都在 SSO 范围内，唯一的分配是 `vector` 的缓冲区。

### 异常

```cpp title="exception.cpp"
#include "count_new.hpp"
#include <malloc/malloc.h>             // macOS：malloc_zone_statistics

static int blocks() {                  // 默认 malloc 区域里存活的块数
  malloc_statistics_t st;
  malloc_zone_statistics(nullptr, &st);
  return int(st.blocks_in_use);
}

[[gnu::noinline]] void fail(int code) { throw code; }

void once(const char* label) {
  int before = blocks();
  int news = count_news([&] {
    try {
      fail(42);
    } catch (int) {
      std::printf("%s: in handler %+d blocks", label, blocks() - before);
    }
  });
  std::printf(", after %+d, operator new %d\n", blocks() - before, news);
}

int main() {
  once("1st throw");                   // 第一次还包括 stdout 缓冲区等初始化
  once("2nd throw");
}
```

```text
1st throw: in handler +2 blocks, after +2, operator new 0
2nd throw: in handler +1 blocks, after +0, operator new 0
```

第二次抛出时，处理器里多了一个 malloc 块，处理器结束后它被释放，而 `operator new` 一次也没被调用。标准规定异常对象的内存以未指定的方式分配（[[except.throw#4]]），并且明确说不调用全局分配函数（[[basic.stc.dynamic.allocation#5]] 的注）。libc++abi 在 `__cxa_allocate_exception` 里直接调用 `malloc`，所以替换 `operator new` 的计数器看不到它。

不过这次分配不是抛出异常的主要开销。本机 `throw` 一个 `int` 再在上一层 `catch` 约 3 µs，同一次运行里 `malloc(16)` + `free` 约 20 ns。时间主要花在栈回溯上，见 [[toolchain/exception-implementation]]。

## 少分配的几种办法

### 复用容量

`clear()` 销毁所有元素，但标准没有说它释放内存（[[sequence.reqmts#54]] 只规定元素被销毁、容器变空）。libc++ 的 `vector` 和 `string` 在 `clear()` 后都保留容量：本机 1000 个元素的 `vector` 清空后容量仍是 1000，`string` 仍是 111，再填回同样多的内容时分配 0 次。上面的表里，复用缓冲区比每次 `reserve` 再快约三分之一。

所以在循环里反复使用的临时容器，可以提到循环外面，每轮 `clear()`。反过来，想真正归还内存时，`shrink_to_fit()` 只是不具约束力的请求（[[vector.capacity#9]]），本机 libc++ 在 `clear()` 之后调用它会把容量降到 0，在容器非空时则降到 `size()`。

### 对象池

大量同类型、同大小的对象反复创建和销毁时，可以把它们放进**对象池**：一次申请一大块，空闲的槽位串成单链表，分配和释放都只是几条指针操作。

```cpp title="pool.cpp"
#include "bench.hpp"
#include <cstddef>
#include <memory>
#include <utility>
#include <vector>

struct Order { long id; double price; int qty; };

template <class T>
class Pool {
  union Slot {                         // 空闲时存 next，使用中存 T
    Slot* next;
    T obj;
    Slot() : next(nullptr) {}
    ~Slot() {}
  };
  std::vector<Slot*> chunks_;
  Slot* free_ = nullptr;

  void refill(std::size_t n = 1024) {
    Slot* c = new Slot[n];
    chunks_.push_back(c);
    for (std::size_t i = 0; i < n; ++i) { c[i].next = free_; free_ = &c[i]; }
  }

public:
  Pool() = default;
  Pool(const Pool&) = delete;
  Pool& operator=(const Pool&) = delete;
  ~Pool() { for (Slot* c : chunks_) delete[] c; }   // 假定所有对象都已 destroy

  template <class... Args> T* create(Args&&... args) {
    if (!free_) refill();
    Slot* s = free_;
    free_ = s->next;
    return std::construct_at(&s->obj, std::forward<Args>(args)...);
  }
  void destroy(T* p) {
    std::destroy_at(p);
    auto* s = reinterpret_cast<Slot*>(p); // 联合体与其成员可指针互转
    s->next = free_;
    free_ = s;
  }
};

int main() {
  bench::prefer_performance_cores();
  constexpr int K = 1000;
  static Order* live[K];
  bench::run("new/delete x1000", [] {
    for (int i = 0; i < K; ++i) {
      live[i] = new Order{i, 1.0, 1};
      bench::do_not_optimize(live[i]);
    }
    for (int i = 0; i < K; ++i) delete live[i];
  });
  Pool<Order> pool;
  bench::run("pool x1000", [&] {
    for (int i = 0; i < K; ++i) {
      live[i] = pool.create(i, 1.0, 1);
      bench::do_not_optimize(live[i]);
    }
    for (int i = 0; i < K; ++i) pool.destroy(live[i]);
  });
}
```

本机同一次运行中，`new`/`delete` 每个对象约 24 ns，对象池约 2.7 ns，差将近 10 倍。`std::construct_at` 在 `obj` 上开始一个对象的生存期，使它成为联合体的活跃成员；`destroy` 里对 `next` 赋值又让 `next` 成为活跃成员。联合体对象和它的非静态数据成员可以指针互转（[[basic.compound#7.2]]），所以 `reinterpret_cast<Slot*>(p)` 得到的就是指向 `Slot` 的指针。

这个池不是线程安全的，也不检查重复释放，ASan 也看不到池内部的错误用法，这些都是自己写分配器要付出的代价。

### arena 与 pmr

对象池管理同一种大小，**arena** 管理一批生存期相同的对象：分配只推进一个偏移量，释放什么也不做，最后整块丢掉。标准库用 `std::pmr::monotonic_buffer_resource` 提供 arena，用 `unsynchronized_pool_resource` 提供按大小分档的池，`pmr` 容器可以把元素的分配也交给同一个资源。它们的用法、传播规则和本机测量见 [[topics/allocators-and-pmr]]。

### 内联存储

很多小集合通常只有几个元素，偶尔才会变多。把前 `N` 个元素放在对象内部，超出后才去堆上分配，常见的情况就不分配：

```cpp title="small_vector.hpp"
#include <cstddef>
#include <cstring>
#include <new>
#include <type_traits>

// 前 N 个元素放在对象内部，超出后才去堆上分配
// 为了短小，只支持可平凡复制的 T
template <class T, std::size_t N>
  requires std::is_trivially_copyable_v<T>
class small_vector {
  T* data_ = inline_;
  std::size_t size_ = 0, cap_ = N;
  T inline_[N];

  void grow() {
    std::size_t cap = cap_ * 2;
    T* p = static_cast<T*>(::operator new(cap * sizeof(T)));
    std::memcpy(p, data_, size_ * sizeof(T));
    if (data_ != inline_) ::operator delete(data_);
    data_ = p;
    cap_ = cap;
  }

public:
  small_vector() = default;
  small_vector(const small_vector&) = delete;
  small_vector& operator=(const small_vector&) = delete;
  ~small_vector() { if (data_ != inline_) ::operator delete(data_); }

  void push_back(const T& v) {
    if (size_ == cap_) grow();
    data_[size_++] = v;
  }
  T* data() { return data_; }
  std::size_t size() const { return size_; }
  T& operator[](std::size_t i) { return data_[i]; }
};
```

本机 `small_vector<int, 8>` 放 8 个元素分配 0 次，放 20 个元素分配 2 次（容量 16、32）；`std::vector<int>` 放 8 个元素分配 4 次。同一次运行中构造 8 个元素的时间：`vector` 约 113 ns，`vector` 加 `reserve(8)` 约 29 ns，`small_vector` 约 4 ns。

代价是对象变大（本机 `sizeof(small_vector<int, 8>)` 是 56，`vector<int>` 是 24），以及 `data_` 可能指向对象自己，移动时不能只复制指针，复制和移动都要单独处理。这里为了简短直接删除了复制。LLVM 的 `SmallVector` 和 Boost 的 `small_vector` 是完整的实现。标准库的 `std::inplace_vector`（{{c++26}}，[[inplace.vector]]）容量固定、从不分配，超出容量时报错而不是改用堆；截至写作时本机 libc++ 还没有提供 `<inplace_vector>`。

## 对齐与过度对齐的 new

`alignof` 超过 `__STDCPP_DEFAULT_NEW_ALIGNMENT__` 的类型叫做具有 **new-extended 对齐**（[[g:new-extended-alignment]]，[[basic.align#3]]）。C++17（[[P0035R4]]）起，`new` 这样的类型时调用带 `std::align_val_t` 参数的分配函数，返回的地址满足类型的对齐要求（[[new.delete.single#1]]）。

```cpp title="aligned.cpp"
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <new>

int plain = 0, aligned = 0;
void* operator new(std::size_t n) {
  ++plain;
  if (void* p = std::malloc(n)) return p;
  throw std::bad_alloc{};
}
void* operator new(std::size_t n, std::align_val_t al) {
  ++aligned;
  auto a = static_cast<std::size_t>(al);
  // aligned_alloc 要求大小是对齐值的整数倍
  if (void* p = std::aligned_alloc(a, (n + a - 1) / a * a)) return p;
  throw std::bad_alloc{};
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::align_val_t) noexcept { std::free(p); }

inline void escape(void* p) { asm volatile("" : : "r"(p) : "memory"); }

struct alignas(16) A16 { char c[16]; };
struct alignas(64) Line { char c[64]; };   // 按缓存行对齐

int main() {
  std::printf("__STDCPP_DEFAULT_NEW_ALIGNMENT__ = %zu\n",
              std::size_t{__STDCPP_DEFAULT_NEW_ALIGNMENT__});
  A16* a = new A16;   escape(a);
  Line* b = new Line; escape(b);
  auto addr = reinterpret_cast<std::uintptr_t>(b);
  std::printf("plain=%d aligned=%d  addr %% 64 = %zu\n",
              plain, aligned, std::size_t(addr % 64));
  delete a;
  delete b;
}
```

```text
__STDCPP_DEFAULT_NEW_ALIGNMENT__ = 16
plain=1 aligned=1  addr % 64 = 0
```

本机默认的 new 对齐是 16，所以 `alignas(16)` 的类型走普通版本，`alignas(64)` 的类型走对齐版本。`std::allocator` 也会这样选，`std::vector<Line>` 的缓冲区同样按 64 对齐。

同一次运行中，`new`/`delete` 一个 64 字节的普通对象、一个 `alignas(64)` 的对象、一个 `alignas(4096)` 的对象都约 24 ns，本机看不出对齐分配的额外开销。别的平台上对齐分配可能要多分配一些再调整地址，代价不一定相同。按缓存行对齐常用来避免伪共享，见 [[perf/false-sharing|伪共享]]。

## 多线程同时分配

```cpp title="mt-alloc.cpp"
#include "bench.hpp"
#include <atomic>
#include <cstdlib>
#include <ctime>
#include <thread>

double cpu_ns() {                      // 当前线程消耗的 CPU 时间
  timespec ts;
  clock_gettime(CLOCK_THREAD_CPUTIME_ID, &ts);
  return ts.tv_sec * 1e9 + ts.tv_nsec;
}

// T 个线程同时做 malloc(64)+free，返回每次操作 CPU 时间的中位数
double run(int T, int iters) {
  std::vector<double> per(T);
  std::atomic<int> ready{0};
  {
    std::vector<std::jthread> ts;
    for (int t = 0; t < T; ++t)
      ts.emplace_back([&, t] {
        ready.fetch_add(1);
        while (ready.load() < T) {}    // 所有线程就位后再开始
        double c0 = cpu_ns();
        for (int i = 0; i < iters; ++i) {
          void* p = std::malloc(64);
          bench::do_not_optimize(p);
          std::free(p);
        }
        per[t] = (cpu_ns() - c0) / iters;
      });
  }                                    // jthread 析构时 join
  std::sort(per.begin(), per.end());
  return per[T / 2];
}

int main() {
  for (int T : {1, 2, 4, 8}) {
    std::vector<double> v;
    for (int r = 0; r < 7; ++r) v.push_back(run(T, 2'000'000));
    std::sort(v.begin(), v.end());
    std::printf("%d threads: %.1f ns CPU per malloc+free\n", T, v[3]);
  }
}
```

这里用线程自己的 CPU 时间而不是墙钟时间，这样线程被调度出去等待的时间不算在内，剩下的增长来自分配器内部的同步和缓存行在核心间的传递。本机两次运行的结果：

| 线程数 | 每次 `malloc` + `free` 的 CPU 时间 |
|---|---|
| 1 | 约 23 ns |
| 2 | 约 32 ns |
| 4 | 约 35 ns |
| 8 | 约 50–54 ns |

M2 Pro 有 8 个性能核和 4 个能效核，8 个线程时可能有线程跑在能效核上，测量时机器上还有其他负载，这一列只说明趋势：线程越多，每次分配越贵。各线程分配相互独立时，给每个线程一个自己的池或 `unsynchronized_pool_resource`，就完全避开了共享的分配器。jemalloc、mimalloc 这类分配器也用线程本地缓存来减少争用。

## 陷阱

!!! pitfall "开了优化，计数器少数了"
    替换 `operator new` 来数分配，是测试里常用的办法。但 [[expr.new#14]] 允许省略 *new-expression* 对它的调用，`-O2` 下 `delete new int` 一次也数不到。要数的分配，指针要先逃逸，或者干脆在 `-O0` 下数。反过来，测试里数到 0 次，也不代表生产代码里不分配。

!!! pitfall "只替换了一半的分配函数"
    只替换 `operator new(size_t)` 时，数组形式和 nothrow 形式默认会转到它，计数仍然完整；但对齐形式 `operator new(size_t, align_val_t)` 不会，过度对齐的对象要单独替换才能数到。释放端同理，替换了带大小的 `operator delete` 就要同时替换不带大小的版本，见 [[new.delete]]。

!!! pitfall "微基准里的分配太便宜"
    分配后立刻释放的循环，每次拿到的都是同一块热的内存，测出的是最好情况。程序里分配和释放的模式越分散，碎片和缓存缺失就越多。判断分配是否是瓶颈，要在真实负载下做 [[perf/profiling|性能剖析]]，看 `malloc`、`free` 和缺页占了多少时间。

## 思考题

!!! question "1"
    下面的函数在本机 `-O2` 下会调用几次 `operator new`？如果在 `sum` 外面替换了 `operator new` 并计数，结果会变吗？
    ```cpp
    int sum() {
      std::vector<int> v{1, 2, 3};
      return v[0] + v[1] + v[2];
    }
    ```

<details markdown="1">
<summary>答案</summary>

0 次，本机 Clang 23 把它编译成 `mov w0, #6; ret`。替换 `operator new` 不改变结果：标准允许省略可替换全局分配函数的调用，即使它被替换了（[[expr.new#14]]）；`std::allocator` 什么时候调用 `::operator new`、调用几次是未指定的（[[allocator.members#5]]）。是否真的省略取决于实现和优化，`-O0` 或 `-fno-builtin` 下就会保留这次分配。
</details>

!!! question "2"
    `std::vector<std::string> v; v.reserve(3); v.emplace_back("hello"); v.emplace_back(std::string(30, 'x')); v.push_back("short");` 在 libc++ 上一共分配几次？

<details markdown="1">
<summary>答案</summary>

2 次。`reserve(3)` 一次；`"hello"` 和 `"short"` 都不超过 22 个字符，在 SSO 范围内，不分配；`std::string(30, 'x')` 分配一次，随后移动进容器只是转移指针。`push_back("short")` 先构造一个临时 `string` 再移动，也不分配。
</details>

!!! question "3"
    一个函数在热路径上抛出异常来报告失败，把异常对象从 `std::runtime_error` 换成 `int`，能省掉多少开销？

<details markdown="1">
<summary>答案</summary>

很少。两者都要为异常对象分配内存（libc++abi 用 `malloc`，[[except.throw#4]] 只说以未指定的方式分配），`runtime_error` 还要为消息字符串额外分配。但本机一次 `throw` + `catch` 约 3 µs，一次分配约 20 ns，时间几乎全花在栈回溯上。热路径上的失败应当用返回值（例如 `std::expected`）报告，而不是换异常类型。
</details>

## 小结

| 来源 | 本机观测 | 怎样避免 |
|---|---|---|
| `malloc` + `free` | 小块约 20 ns，64 KiB 以上约 100 ns | 减少次数 |
| `std::string` | 超过 22 字符分配一次（libc++） | 控制长度，复用缓冲区 |
| `std::function` | 闭包超过 16 字节分配一次（libc++） | 模板参数、`function_ref` |
| `vector` 增长 | 1000 个元素 11 次 | `reserve`，`clear()` 后复用 |
| 节点容器 | 每个元素一次 | 换连续容器，或节点用池/pmr |
| `shared_ptr(new T)` | 2 次 | `make_shared` |
| 异常 | 每次抛出一次 `malloc`，不经过 `operator new` | 不在热路径上抛出 |
| new/delete 成对出现 | 指针不逃逸时可能被省略 | 不要依赖，看汇编确认 |
