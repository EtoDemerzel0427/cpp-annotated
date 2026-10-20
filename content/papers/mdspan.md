---
title: mdspan（P0009）
summary: C++23 的 std::mdspan 是一块内存上的多维视图，由形状、布局、访问器三部分组成：它要替代的几种旧写法，从 Kokkos 带来的布局问题，形状为什么写成 extents 而不是数组类型，定制点为什么是两个策略，m[i, j] 为什么要先改语言，它为什么不是 range，以及 C++26 的 submdspan 和填充布局。
status: draft
order: 50
group: 标准库
since: c++23
papers: P0009R18, N4355, P0331R0, P0332R2, P1684R5, P2128R6, P1161R3, P2299R3, P2553R1, P2389R2, P2630R4, P2642R6, P2897R7, P0860R1
related: views.multidim, mdspan.overview, mdspan.extents, mdspan.layout, mdspan.accessor, mdspan.mdspan, mdspan.sub, expr.sub, over.sub, diff.cpp20.expr, views.contiguous, patterns/policy-based-design, perf/memory-hierarchy, perf/reading-assembly, topics/ranges-design
tags: mdspan, 多维数组, 视图, 布局, 访问器, 多参数下标, 提案, C++23
updated: 2026-10-19
---

!!! tldr
    - C++23 之前，运行期大小的多维数组只能写成 `vector<vector<T>>`（不连续、要追指针）或指针加手写下标（形状和步长全靠约定）。`std::mdspan`（[[P0009R18]]）把指针、形状和下标公式装进一个不拥有内存的视图。
    - 形状 `extents` 允许每一维分别是编译期常量或运行期值。静态的维不占存储，编译器还能把它折进地址计算：本机 `-O2` 下 4×4 矩阵求迹是 10 条指令，全动态版本是 82 条。
    - 定制点只有两个策略：布局决定下标怎样变成偏移，访问器决定偏移怎样变成元素引用。委员会否决了任意属性列表的设计，换来的是分配器式的、可以各自替换的两个接口。
    - `m[i, j]` 依赖语言改动 [[P2128R6]]：重载的 `operator[]` 可以有多个参数，代价是 C++20 已弃用的 `a[i, j]` 逗号表达式在 C++23 中非良构（附录 C）。
    - `mdspan` 没有迭代器，不是 range。C++26 补上了取子视图的 `submdspan` 和带填充的布局，本机 libc++ 都还没有实现。

## 没有 mdspan 时

函数要处理一个运行期才知道大小的矩阵，C++20 有三种常见写法：

```cpp title="before.cpp" run ok
#include <cstdio>
#include <vector>

// 1. 内建多维数组：除第一维外都必须是常量
void scale_fixed(double (*a)[4], int rows, double k) {
  for (int i = 0; i < rows; ++i)
    for (int j = 0; j < 4; ++j) a[i][j] *= k;
}

// 2. vector 的 vector：每行单独分配，访问要先读行指针
void scale_nested(std::vector<std::vector<double>>& a, double k) {
  for (auto& row : a)
    for (double& x : row) x *= k;
}

// 3. 指针加手写下标：形状和步长全靠约定
void scale_raw(double* a, int rows, int cols, int ld, double k) {
  for (int i = 0; i < rows; ++i)
    for (int j = 0; j < cols; ++j) a[i * ld + j] *= k;
}

int main() {
  double fixed[2][4] = {{1, 2, 3, 4}, {5, 6, 7, 8}};
  scale_fixed(fixed, 2, 2.0);

  std::vector<std::vector<double>> nested(2, std::vector<double>(3, 1.0));
  scale_nested(nested, 3.0);

  std::vector<double> flat(2 * 5, 1.0);   // 2 行 3 列，每行占 5 个位置
  scale_raw(flat.data(), 2, 3, 5, 4.0);

  std::printf("%g %g %g %g\n", fixed[1][3], nested[1][2], flat[5], flat[8]);  // 16 3 4 1
}
```

第一种的列数写死在类型里。C++ 没有变长数组，`double a[rows][cols]` 在 `cols` 不是常量时非良构（[[dcl.array]]）。第二种的每一行是一次单独的分配，数据不连续，不能整块交给 C 或 Fortran 写的数值库。第三种最常见，也最脆弱：行数、列数、行距 `ld` 是三个散落的整数，写错一个不会有任何诊断，换成列主序就要改每一处下标。

[[P0009R18]] 的动机一节逐一列出这几种做法的缺点，还加上了 `valarray` 配合 `gslice`：它能把一维的 `valarray` 当成多维数据来选取，但结果不保证有 `operator[]`，取单个元素也没有高效的办法。

访问一个元素的代价也不同。本机 Clang 23（arm64）`-O2` 下，`a[i][j]` 对 `vector<vector<float>>` 是三次内存读取：外层 `vector` 的数据指针、第 i 行的数据指针、元素本身；`a[i * ld + j]` 是一条乘加指令加一次读取。

`mdspan` 的写法是把指针、形状和下标公式合成一个对象，三种情况由同一个函数模板处理：

```cpp title="after.cpp" run ok
#include <array>
#include <cstdio>
#include <mdspan>
#include <vector>

// 一个函数接受任何形状、任何布局的二维视图
template<class T, class E, class L, class A>
void scale(std::mdspan<T, E, L, A> a, T k) {
  for (typename E::index_type i = 0; i < a.extent(0); ++i)
    for (typename E::index_type j = 0; j < a.extent(1); ++j)
      a[i, j] *= k;
}

int main() {
  double buf[8] = {1, 2, 3, 4, 5, 6, 7, 8};
  scale(std::mdspan<double, std::extents<int, 2, 4>>(buf), 2.0);   // 全静态

  std::vector<double> v(6, 1.0);
  scale(std::mdspan(v.data(), 2, 3), 3.0);                          // 全动态

  std::vector<double> flat(2 * 5, 1.0);   // 2 行 3 列，行距 5
  std::layout_stride::mapping m(std::dextents<int, 2>(2, 3), std::array{5, 1});
  scale(std::mdspan(flat.data(), m), 4.0);                          // 带步长

  std::printf("%g %g %g %g\n", buf[7], v[5], flat[5], flat[8]);   // 16 3 4 1
}
```

`mdspan<T, Extents, LayoutPolicy, AccessorPolicy>` 的四个模板参数分别是元素类型、形状、布局策略和访问器策略，后两个默认是行主序的 `layout_right` 和直接解引用指针的 `default_accessor<T>`。各部分的规则逐条见 [[views.multidim]]，这里只讲它们为什么是这样设计的。

## 起点：随硬件变化的数据布局

`mdspan` 的设计来自高性能计算（HPC）。它的前身是 Kokkos 库里的多维数组 `Kokkos::View`，Kokkos 早已实现了布局可替换的多维数组引用（[[P0331R0]]）。

[[N4355]] 把问题讲得很直接：科学计算代码的数组布局常常要为新硬件重新安排，早年为向量机排，后来为多级缓存排，今天又在"结构的数组"和"数组的结构"之间来回改。布局写死在下标表达式里，换布局就要重构代码，或者同时维护几份功能相同、布局不同的代码。它提出的目标是**多态布局**：布局作为一个可以替换的参数，改它不需要改算法。

[[P0009R18]] 用一个矩阵-向量乘法说明这一点：同一段并行代码，在 CPU 上用行主序的 `layout_right` 快；交给 NVIDIA GPU 执行时，列主序的 `layout_left` 快得多，因为相邻线程访问相邻的地址，访存可以合并（coalesced）。只改一个模板实参，算法本身不动。

在 CPU 上也能看到同样的效果。下面的函数固定按 i 外 j 内的顺序遍历，只换布局策略：

```cpp title="layout-swap.cpp" run ok
#include <chrono>
#include <cstdio>
#include <mdspan>
#include <vector>

template<class Layout>
double row_sums(std::mdspan<const double, std::dextents<int, 2>, Layout> a,
                std::mdspan<double, std::dextents<int, 1>> y) {
  for (int i = 0; i < a.extent(0); ++i) {   // 循环顺序固定：i 外、j 内
    double s = 0;
    for (int j = 0; j < a.extent(1); ++j) s += a[i, j];
    y[i] = s;
  }
  return y[0];
}

template<class Layout>
void run(const char* name, const std::vector<double>& buf, int n) {
  std::vector<double> out(n);
  std::mdspan<const double, std::dextents<int, 2>, Layout> a(buf.data(), n, n);
  std::mdspan<double, std::dextents<int, 1>> y(out.data(), n);
  auto t0 = std::chrono::steady_clock::now();
  double r = 0;
  for (int k = 0; k < 10; ++k) r += row_sums(a, y);
  auto t1 = std::chrono::steady_clock::now();
  std::printf("%-13s %6.1f ms  (%g)\n", name,
      std::chrono::duration<double, std::milli>(t1 - t0).count() / 10, r);
}

int main() {
  const int n = 4096;                       // 4096 × 4096 个 double = 128 MiB
  std::vector<double> buf(std::size_t(n) * n, 1.0);
  run<std::layout_right>("layout_right", buf, n);
  run<std::layout_left>("layout_left", buf, n);
}
```

本机（Apple Silicon，Clang 23，`-O2`）多次运行，`layout_right` 每轮约 16–20 ms，`layout_left` 约 65–110 ms。前者内层循环读相邻的元素，后者每一步跨过 32 KiB。原因和更系统的测量见 [[perf/memory-hierarchy|缓存、局部性与数据布局]]。同一块内存在两种布局下表示的是互为转置的矩阵，这个例子的数据全是 1，结果相同。

## 设计空间

### 视图，不是容器

`mdspan` 不分配、不释放内存，复制它只复制指针和形状，这一点和 `span` 一样（[[views.contiguous]]）。拥有内存的多维数组另有提案 `mdarray`（[[P1684R5]]），至今没有进入标准。

[[P0009R18]] 给了两个先做视图的理由。第一，并行计算里多个线程访问同一个数组的不同部分，分配和释放是同步点，所以视图才是并行代码表达"我访问哪些元素"的基本方式。第二，数据常常已经由别的语言分配好了，C、Fortran、Python 的 NumPy 都要能在不复制的情况下被看成多维数组。

### 形状怎么写

早期的提案想用数组类型写形状，`int[3][][5]` 表示第二维运行期才知道：

```cpp
// P0332 设想的写法（不是 C++）
using tensor = mdspan<double[][][], layout_left>;
// 今天的写法
using tensor = mdspan<double, dextents<size_t, 3>, layout_left>;
```

这需要放宽语言对数组类型的限制，`T[][]` 今天非良构，只有第一维可以省略。这部分被拆成独立的语言提案 [[P0332R2]]，它承认之前的版本没有回应演化工作组（EWG）提出的问题，最终没有被接受。

库这边于是改用一个类模板 `extents<IndexType, size_t... Extents>` 表示形状：每个模板实参要么是具体长度，即**静态长度**（[[g:static-extent|static extent]]）；要么是 `dynamic_extent`，即**动态长度**（[[g:dynamic-extent|dynamic extent]]），值存在对象里（[[mdspan.extents.overview#3]]）。它不需要语言改动，代价是写起来长。

[[N4355]] 还指出了当时另一个提案 `array_view` 的问题：它的模板参数 `N` 表示维数，而 `std::array<T, N>` 的 `N` 是长度，同一个字母含义相反；带步长的视图又是另一个类 `strided_array_view`。`extents` 把每一维的长度都放进模板实参，维数由实参个数决定；带步长只是一种布局，不需要另一个类。

### 静态长度换来什么

允许静态长度的根本理由是性能（[[P0009R18]] §2.5）：编译器知道长度，就能展开循环、预先算好偏移；不存储这一维，也省下寄存器和栈空间。很多问题天然是混合的：粒子数量运行期才知道，每个粒子的坐标却总是 3 个。

```cpp title="particles.cpp" run ok
#include <cstdio>
#include <mdspan>
#include <vector>

// n 个粒子 × 3 个坐标：粒子数运行期才知道，3 是空间的维数
using Positions = std::mdspan<double, std::extents<int, std::dynamic_extent, 3>>;

double norm2(Positions p, int k) {
  double s = 0;
  for (int d = 0; d < p.extent(1); ++d) s += p[k, d] * p[k, d];   // 内层循环次数是常量 3
  return s;
}

int main() {
  int n = 1000;
  std::vector<double> buf(n * 3, 1.0);
  Positions p(buf.data(), n);                  // 只给动态的那一维
  static_assert(Positions::rank() == 2 && Positions::rank_dynamic() == 1);
  std::printf("%g %zu\n", norm2(p, 42), sizeof p);   // 3 16（libc++，arm64）
}
```

本机 `-O2` 下，`norm2` 编译成 9 条指令：`k * 3` 用一条移位加法算出，3 次乘加完全展开，运行期的粒子数根本没有被读取。

把两维都变成静态或都变成动态，差别更明显。下面两个函数只有形状的类型不同：

```cpp title="static-vs-dynamic.cpp" ok
#include <mdspan>

using Static  = std::mdspan<const float, std::extents<int, 4, 4>>;
using Dynamic = std::mdspan<const float, std::dextents<int, 2>>;

float trace_s(Static m) {
  float s = 0;
  for (int i = 0; i < m.extent(0); ++i) s += m[i, i];
  return s;
}
float trace_d(Dynamic m) {
  float s = 0;
  for (int i = 0; i < m.extent(0); ++i) s += m[i, i];
  return s;
}
float at_s(Static m, int i, int j) { return m[i, j]; }
float at_d(Dynamic m, int i, int j) { return m[i, j]; }
```

本机 Clang 23（arm64，`-O2`）的结果：

| 函数 | 指令数 | 内容 |
|---|---|---|
| `trace_s` | 10 | 四次读取，偏移 0、20、40、60 字节直接写在指令里，没有循环 |
| `trace_d` | 82 | 判断长度、检查溢出、4 路展开的主循环加处理余数的尾循环 |
| `at_s` | 2 | `add w8, w2, w1, lsl #2` 算 `i * 4 + j`，再读一次 |
| `at_d` | 3 | 先从参数寄存器取出列数，再 `madd` 乘加，再读 |

`at_d` 和手写的 `a[i * ld + j]` 生成的代码基本相同，所以全动态的 `mdspan` 没有额外开销；静态长度是在此之上的收益。`Static` 只存一个指针（8 字节），`Dynamic` 存指针和两个 `int`（16 字节），两者都装在寄存器里传递。怎样读这些汇编见 [[perf/reading-assembly]]。

### 定制点：属性列表还是两个策略

`mdspan` 的前身叫 `array_ref`，它的定制方式是一个可变长的属性列表：`array_ref<T, Properties...>`，布局、访问方式等都作为属性塞进去。LEWG 早期的评审就要求提案说明用户怎样添加属性，并指出标准库里没有这种可变长属性列表的先例。[[P0860R1]] 提出的原子访问一开始也被设想成这样的一个属性。

图书馆演化工作组（LEWG）最后比较了两种形式，选择了第二种（[[P0009R18]] 的修订历史，R6）：

```cpp
basic_mdspan<T, Extents, Properties...>        // 任意属性列表：被否决
basic_mdspan<T, Extents, Mapper, Accessor>     // 两个概念，类似 Allocator：被采纳
```

两个策略的分工是：**布局策略**决定多维下标怎样换算成一维偏移，**访问器策略**（[[g:accessor-policy|accessor policy]]）决定怎样从数据句柄和偏移得到元素的引用。`m[i, j]` 就是先算偏移、再访问，[[mdspan.mdspan.members#4]] 把它写成一行：

```cpp
return acc_.access(ptr_, map_(static_cast<index_type>(std::move(indices))...));
```

这是典型的基于策略的设计（[[patterns/policy-based-design]]）：每个策略是一个有固定接口的类型，宿主类模板把它们组合起来，两个维度可以独立替换。同一次评审里，LEWG 也明确不想给一维的 `span` 加访问器参数。

布局策略本身不是映射。`LayoutPolicy::mapping<E>` 才是针对某个 `extents` 类型 `E` 的映射（[[mdspan.layout.policy.reqmts#1]]），这样同一种布局可以套在任何形状上，`layout_right` 本身只是一个空结构体。

### 布局能表达什么

标准给了三种布局：行主序的 `layout_right`（C 的习惯），列主序的 `layout_left`（Fortran 的习惯），每一维有任意步长的 `layout_stride`。[[P0009R18]] 举出的自定义布局包括分块（tiled，矩阵由小矩阵组成，改善局部性和向量化）、空间填充曲线，以及**非唯一**的布局：多个下标指向同一个元素。

对称矩阵是非唯一布局的典型例子，`A[i, j]` 和 `A[j, i]` 是同一个元素，只存一半就够了。下面是一个完整的自定义布局，满足 [[mdspan.layout.reqmts]] 的全部要求：

```cpp title="symmetric.cpp" run ok
#include <cstdio>
#include <mdspan>
#include <utility>

// 对称矩阵：只存上三角，(i, j) 与 (j, i) 指向同一个元素
struct layout_symmetric {
  template<class Extents>
  struct mapping {
    static_assert(Extents::rank() == 2);
    using extents_type = Extents;
    using index_type   = typename Extents::index_type;
    using rank_type    = typename Extents::rank_type;
    using layout_type  = layout_symmetric;

    extents_type ext_;
    mapping() = default;
    constexpr mapping(const extents_type& e) : ext_(e) {}

    constexpr const extents_type& extents() const noexcept { return ext_; }
    constexpr index_type operator()(index_type i, index_type j) const noexcept {
      if (i > j) std::swap(i, j);
      index_type n = ext_.extent(0);
      return i * n - i * (i - 1) / 2 + (j - i);   // 按行压缩存放的上三角
    }
    constexpr index_type required_span_size() const noexcept {
      index_type n = ext_.extent(0);
      return n * (n + 1) / 2;
    }
    static constexpr bool is_always_unique()     noexcept { return false; }
    static constexpr bool is_always_exhaustive() noexcept { return true; }
    static constexpr bool is_always_strided()    noexcept { return false; }
    constexpr bool is_unique()     const noexcept { return ext_.extent(0) <= 1; }
    constexpr bool is_exhaustive() const noexcept { return true; }
    constexpr bool is_strided()    const noexcept { return false; }
    constexpr index_type stride(rank_type) const noexcept { return 0; }  // 前置条件 is_strided() 不成立，不会被合法调用
    friend constexpr bool operator==(const mapping&, const mapping&) = default;
  };
};

int main() {
  double packed[6] = {1, 2, 3, 4, 5, 6};          // 3×3 对称矩阵只需 6 个元素
  using E = std::extents<int, 3, 3>;
  std::mdspan<double, E, layout_symmetric> s(packed, E{});
  std::printf("%g %g %d\n", s[0, 2], s[2, 0], s.mapping().required_span_size());  // 3 3 6
  s[2, 1] = 50;                                     // 同时改变了 s[1, 2]
  std::printf("%g\n", s[1, 2]);                     // 50
}
```

`is_unique()` 等三个性质是给泛型算法看的承诺：unique 时并行写不同下标不会冲突，exhaustive 时可以把整块存储当一维数组处理，strided 时可以交给要求步长参数的 BLAS 接口。它们都只在返回 `true` 时有意义，`false` 表示不知道（[[mdspan.layout.reqmts#14]] 的注 1）。

### 访问器能表达什么

[[P0009R18]] §2.7 说明了为什么要定制访问：硬件除了普通的读写，还有原子访问、非临时（绕过缓存）的读写；C 的 `restrict` 表达"不与其他数组别名"，`volatile` 限制优化；异构系统里有 CPU 不能直接访问的 GPU 内存，或者需要特殊操作才能访问的全局共享内存。这些都不改变下标公式，只改变"拿到偏移之后怎样碰那个元素"。

所以访问器的要求故意放得很宽。数据句柄 `data_handle_type` 不必是 `element_type*`，甚至不必可以解引用（[[mdspan.accessor.general#3]] 的注 1）；`reference` 不必是 `element_type&`，只要和它有公共引用类型（[[mdspan.accessor.reqmts#4]]）。这使得代理引用成为可能。下面的访问器每次访问都返回 `atomic_ref`，让多个线程安全地累加同一块普通的 `int` 数组，这正是 [[P0860R1]] 设想的原子访问器：

```cpp title="atomic-accessor.cpp" run ok
#include <atomic>
#include <cstdio>
#include <mdspan>
#include <thread>
#include <vector>

// 每次访问都经过 atomic_ref：元素仍是普通的 int
template<class T>
struct atomic_accessor {
  using element_type     = T;
  using data_handle_type = T*;
  using reference        = std::atomic_ref<T>;
  using offset_policy    = atomic_accessor;

  constexpr reference access(T* p, std::size_t i) const noexcept {
    return reference(p[i]);
  }
  constexpr T* offset(T* p, std::size_t i) const noexcept { return p + i; }
};

int main() {
  std::vector<int> buf(4 * 4, 0);
  using E = std::extents<int, 4, 4>;
  std::mdspan<int, E> plain(buf.data());
  std::mdspan<int, E, std::layout_right, atomic_accessor<int>> hist(buf.data());

  std::vector<std::jthread> ts;
  for (int t = 0; t < 4; ++t)
    ts.emplace_back([=] {
      for (int k = 0; k < 100000; ++k)
        hist[k % 4, (k / 4) % 4].fetch_add(1, std::memory_order_relaxed);
    });
  ts.clear();                                  // 等待全部线程结束

  std::printf("%d %d\n", plain[0, 0], plain[3, 3]);   // 25000 25000
}
```

本机用 `-fsanitize=thread` 运行没有报告数据竞争。把 `hist` 换成 `plain`，同样的代码就有数据竞争，是未定义行为。标准库自己提供的访问器只有 `default_accessor` 和 C++26 的 `aligned_accessor`（[[P2897R7]]），后者告诉编译器指针按多少字节对齐。

### 下标：从 `m(i, j)` 到 `m[i, j]`

`mdspan` 在委员会里走了很多年都用函数调用运算符访问元素：`m(i, j)`。原因很简单，C++20 之前重载的 `operator[]` 只能有一个参数，`m[i, j]` 是对逗号表达式 `(i, j)` 求值后再下标。

[[P2128R6]] 比较了当时库作者用来绕开这个限制的三种写法：

| 写法 | 谁在用 | 提案指出的问题 |
|---|---|---|
| `a(i, j, k)` | Fortran、Matlab、Eigen、Kokkos，以及当时的 `mdspan` | 一维用 `[]`、多维用 `()`，同一种操作两种标点；有 `operator()` 的类型可能被误当成可调用对象，传错参数顺序的泛型代码照样能编译 |
| `a[i][j][k]` | C 数组的数组、`vector<vector<T>>` | `a[i]` 必须是一个代理对象，访问一次元素的调用深度随维数增加，妨碍内联；还暗示了行主序、每行单独分配、各行可以不等长 |
| `a[{i, j, k}]` | C++ AMP | 要先构造一个下标对象再拆开；其他语言没有这种写法 |

提案的结论是让 `operator[]` 和 `operator()` 一样接受任意多个参数（包括零个）。另有几种由编译器改写表达式的方案被讨论过并放弃，比如把 `a[x][y][z]` 改写成 `a.operator[](x, y, z)`。它会改变一种常用写法的含义，`a[x]` 在 `a[x][y]` 里可能不再是一个合法的子表达式；`files["home", user]["section", "key"]` 这样有意连写两次多参数下标的代码会被错误地合并；重载决议还要在"一个多参数重载"和"一串单参数重载"之间比较优劣。

这条路之所以可行，是因为 [[P1161R3]] 已经在 C++20 中弃用了下标里不加括号的逗号表达式，并且调查表明这种写法极少出现。P2128 在 C++23 中把它变成非良构，把语法让给多参数下标。内建数组不受影响，它的下标仍然只接受一个表达式：

```cpp title="comma-subscript.cpp" error
struct Grid {
  int d[12];
  int& operator[](int i, int j) { return d[i * 4 + j]; }   // C++23 起允许
};
int main() {
  int arr[3] = {};
  Grid g{};
  g[1, 2] = 7;        // OK：g.operator[](1, 2)
  arr[1, 2] = 7;      // error: 内建下标只接受一个表达式（C++20 中是弃用的逗号表达式）
  arr[(1, 2)] = 7;    // OK：加括号仍是逗号表达式
}
```

本机 Clang 23 在 `-std=c++2c` 下对 `arr[1, 2]` 报 "built-in subscript operator for type 'int[3]' expects exactly one argument"；在 `-std=c++20` 下 `Grid` 的定义本身就被拒绝，`arr[1, 2]` 只得到弃用警告。

P2128 没有给内建数组同时加上多维含义，理由是 C++20 中合法（虽已弃用）的代码到 C++23 应当变成非良构，而不是悄悄换一种含义；要不要让 `arr[1, 2]` 表示别的东西，留到以后再讨论。P0009 从 R13 起把访问运算符改成了 `operator[]`。

这是一个库的需求推动语言修改的例子：没有 P2128，标准的多维数组只能用 `m(i, j)`。

### 为什么不是 range

`mdspan` 没有 `begin()` 和 `end()`：

```cpp
static_assert(!std::ranges::range<std::mdspan<int, std::dextents<int, 2>>>);
```

早期的 `array_ref` 有成员 `begin()`/`end()`。LEWG 在评审中对它们的支持很弱，也不希望由这个提案提供产生 range 的函数，而是希望另写一篇提案专门研究多维迭代。R3 因此删除了迭代器支持（[[P0009R18]] 的修订历史）。这篇后续提案没有进入标准。

下面是从设计本身能看出的几个困难，属于分析，不是提案原文：

- 遍历什么。按下标遍历和按存储遍历在一般布局下不是一回事。上面的对称矩阵有 9 个下标、6 个元素，按下标遍历会把非对角元素访问两次；`layout_stride` 的存储里可能有不属于视图的空隙。
- 按什么顺序。按下标的字典序遍历，在 `layout_left` 下就是前一节测出的慢速跨步访问；按存储顺序遍历，又要求布局是 exhaustive 的。
- 代价。迭代器要保存一个多维下标，每次 `++` 都要逐维进位，比嵌套循环多出分支，也更难向量化。

当前草案里能整体处理 `mdspan` 的算法，是 C++26 之后加入的多维 `copy` 和 `fill`，它们直接接受 `mdspan` 而不是 range（[[mdspan.syn]]）。遍历元素仍然写嵌套循环。

### 名字、别名和下标类型

最终的接口是几轮简化的结果：

- R6 起，完整的类模板叫 `basic_mdspan<T, Extents, Layout, Accessor>`，另有一个便于使用的别名 `mdspan<T, size_t... Extents>`。[[P2299R3]] 指出，有了类模板实参推导和一个表示全动态形状的别名，这层区分就不需要了：删掉别名，把 `basic_mdspan` 改名为 `mdspan`，加上推导指引和 `dextents<Rank>`。它在 R13 并入 P0009，所以今天可以直接写 `std::mdspan m(p, rows, cols)`。
- 长度和下标的类型从 `ptrdiff_t` 改成 `size_t`（R11，为了和 `span` 一致），再由 [[P2553R1]] 改成 `extents` 的第一个模板参数 `IndexType`（R17 并入）。下标类型的符号和宽度会影响性能，`int` 的溢出是未定义行为，编译器可以据此做更积极的优化。
- 加了下标类型参数之后，`dextents<size_t, 3>` 又变长了。[[P2389R2]] 起初想去掉这个参数，LEWG 不同意做破坏性修改，最后在 C++26 中另加了 `dims<Rank, IndexType = size_t>`（[[mdspan.extents.dims]]）。

下标类型参数带来的一个直接后果是转换规则：从 `extents<size_t, ...>` 到 `extents<int, ...>` 即使形状相同也必须显式转换，因为值域变窄了（[[mdspan.extents.cons#4]]）。`std::mdspan(p, n)` 推导出的是 `size_t` 下标，传给参数类型为 `dextents<int, 1>` 的函数会编译失败，前面的 `layout-swap.cpp` 因此显式写出了 `y` 的类型。

## 措辞

!!! std
    The class template `extents` represents a multidimensional index space of rank equal to `sizeof...(Extents)`. ([[mdspan.extents.overview]])

    `extents` 表示一个多维下标空间，维数等于模板实参的个数。整个 [views] 中，"extents" 和"多维下标空间"是同义词。

P0009R18 新增了头文件 `<mdspan>`，放在第 23 章容器库的 [views] 之下，与 `span` 并列。按当前草案的位置整理如下：

| 条款 | 内容 |
|---|---|
| [[mdspan.overview]] | 多维下标空间、rank、多维下标的定义 |
| [[mdspan.extents]] | `extents`、`dextents`；C++26 的 `dims` |
| [[mdspan.layout]] | 布局映射要求（[[mdspan.layout.reqmts]]）、布局策略要求（[[mdspan.layout.policy.reqmts]]）、`layout_left`/`layout_right`/`layout_stride`；C++26 的两种填充布局 |
| [[mdspan.accessor]] | 访问器策略要求、`default_accessor`；C++26 的 `aligned_accessor` |
| [[mdspan.mdspan]] | `mdspan` 本体、构造函数、推导指引、`operator[]` |
| [[mdspan.sub]] | C++26 的 `submdspan` |
| [[expr.sub#1]]、[[over.sub#1]] | P2128：方括号里可以是逗号分隔的列表，交给 `operator[]`；内建下标仍只接受一个表达式（[[expr.sub#2]]） |
| [[diff.cpp20.expr#2]] | 附录 C：下标中逗号的含义改变 |

特性测试宏：`__cpp_lib_mdspan` 在当前草案中是 `202406L`，本机 libc++ 报告的也是这个值；`__cpp_multidimensional_subscript` 是 `202211L`（[[cpp.predefined]]）。

## 后果

### 破坏了什么

`<mdspan>` 是新头文件，库本身不影响旧代码。唯一的不兼容来自 P2128：C++20 中 `arr[1, 2]` 等价于 `arr[(1, 2)]`（已弃用），C++23 起它要么调用多参数的 `operator[]`，要么非良构（[[diff.cpp20.expr#2]]）。

### C++26 的后续

`submdspan` 原本是 P0009 的一部分，为了让 `mdspan` 赶上 C++23 被拆了出去（[[P0009R18]] §2.8）。它在 C++26 由 [[P2630R4]] 加回，并做了两项扩展：切片可以是编译期值，结果的形状因此能保留静态长度；自定义布局可以参与切片。

第二项的定制方式值得一看。`submdspan` 自己不知道怎样切任意布局，它把原映射和切片交给一个名为 `submdspan_mapping` 的函数，只经实参依赖查找（ADL，[[g:argument-dependent-lookup]]）找到它（[[mdspan.sub.map.sliceable#2]]）。P2630 比较了纯 ADL、定制点对象和 `tag_invoke`，认为这个名字足够独特，实现它的只有少数写自定义布局的人，而且它没有默认实现，找不到时是编译错误，所以选了最简单的纯 ADL。它也没有被加进布局策略的要求里，因为不是所有布局都能高效地支持所有切片。

[[P2642R6]] 加入了 `layout_left_padded` 和 `layout_right_padded`：一维连续，相邻行（或列）之间的距离可以大于行长，相当于 BLAS 的"leading dimension"。它和 `layout_stride` 相比有两个好处：类型就保证了有一维步长为 1，只需存一个步长；从这种矩阵里取连续的子矩阵，结果仍是同一种布局，LAPACK 式的分块算法依赖这一点。提案也考虑过一个所有步长都可以是编译期常量的 `layout_stride`，认为它过于复杂，维数一高，多数步长反正依赖运行期的长度。

切片的具体规则、结果布局的选择，以及之后对切片类型的改写，见 [[views.multidim]] 的 submdspan 一节。

### 编译器支持

本机 Clang 23 自带的 libc++ 实现了 `mdspan`、`extents`、`dextents`、`dims`、三种基本布局、`default_accessor` 和 `aligned_accessor`，以及多参数 `operator[]`。`submdspan`、`full_extent`、两种填充布局都还没有实现，`__cpp_lib_submdspan` 没有定义。上面所有带判定的例子都在本机用 `-std=c++2c -Wall -Wextra -pedantic` 编译通过（`comma-subscript.cpp` 按预期被拒绝），可运行的例子用 ASan/UBSan 运行过，`atomic-accessor.cpp` 用 TSan 运行过。

## 思考题

!!! question "1. 为什么这段代码编译失败？"
    ```cpp
    void f(std::mdspan<double, std::dextents<int, 2>> a);
    std::vector<double> v(12);
    f(std::mdspan(v.data(), 3, 4));
    ```

<details markdown="1">
<summary>答案</summary>

`std::mdspan(v.data(), 3, 4)` 按推导指引得到 `mdspan<double, extents<size_t, dynamic_extent, dynamic_extent>>`（[[mdspan.mdspan.overview]] 中的推导指引）。从 `extents<size_t, ...>` 到 `extents<int, ...>` 的转换，因为 `int` 的最大值小于 `size_t` 的最大值而是 `explicit` 的（[[mdspan.extents.cons#4]]），这个 `explicit` 一路传到 `mdspan` 的转换构造函数上，复制初始化形参时不能用。写成 `f(std::mdspan<double, std::dextents<int, 2>>(v.data(), 3, 4))` 就可以。
</details>

!!! question "2. 对称矩阵的布局可以用 `layout_stride` 表示吗？用自定义布局时，并行写入要注意什么？"

<details markdown="1">
<summary>答案</summary>

不能。`layout_stride` 的映射是 `Σ iᵣ × sᵣ`，并且要求映射是 unique 的（[[mdspan.layout.stride.cons]]），而对称布局让 `(i, j)` 和 `(j, i)` 映射到同一个偏移，按定义不 unique。

自定义布局的 `is_unique()` 返回 `false` 时，泛型代码不能假设不同下标对应不同元素。两个线程分别写 `s[1, 2]` 和 `s[2, 1]` 写的是同一个对象，没有同步就是数据竞争。要么只遍历上三角，要么像前面的 `atomic_accessor` 那样换一个原子访问器。
</details>

!!! question "3. C++23 中 `int arr[3]; arr[1, 2];` 是什么？`std::vector<int> v(3); v[1, 2];` 呢？"

<details markdown="1">
<summary>答案</summary>

两者都非良构。内建下标要求方括号里恰好一个赋值表达式（[[expr.sub#2]]）。`vector` 的 `operator[]` 只有一个参数，`v[1, 2]` 按 [[over.sub#1]] 解释成 `v.operator[](1, 2)`，没有可行的重载。C++20 中两者都等价于下标 `2`，只是被弃用；附录 C 记录了这个变化（[[diff.cpp20.expr#2]]）。要保留旧含义，写 `arr[(1, 2)]`。
</details>
