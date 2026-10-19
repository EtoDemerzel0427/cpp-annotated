---
title: 多维访问：mdspan
summary: std::mdspan 把一块连续内存按多维形状来索引：extents 描述形状，layout mapping 把多维下标换算成偏移，accessor 把偏移变成元素引用；另有 C++26 的切片函数 submdspan 和 C++26 之后的多维 copy/fill。
status: done
covers: *
papers: P0009R18, P2128R6, P2630R4, P2642R6, P2897R7
related: views, views.contiguous, expr.sub, over.sub, basic.lookup.argdep, array, ptr.align
tags: 标准库, mdspan, 视图, 多维数组, 布局, 加固
updated: 2026-10-19
---

!!! tldr
    - `mdspan` 不拥有内存，它由三部分组成：形状 `extents`、把多维下标换算成一维偏移的布局映射、把偏移变成元素引用的访问器。`m[i, j]` 依次经过这三步。
    - `extents` 的每一维可以是编译期常量（静态）或运行期的值（动态），只有动态维占存储。rank 为 0 的 `mdspan` 恰好有一个元素。
    - 默认布局 `layout_right` 是行主序，`layout_left` 是列主序，`layout_stride` 允许任意正步长；C++26 增加了带填充的两种布局。
    - 加固实现会逐维检查 `m[i, j]` 的下标，但没有任何实现能检查你传进来的缓冲区够不够大。
    - C++26 的 `submdspan` 取子视图，并尽量保留连续布局。本机 libc++ 还没有实现 `submdspan`、填充布局和多维 `copy`/`fill`。

## 一块内存，按多维形状索引

```cpp run title="mdspan-basics.cpp" ok
#include <cstdio>
#include <mdspan>
#include <stdexcept>
#include <type_traits>
#include <vector>

int main() {
  std::vector<double> buf(12);
  std::mdspan m(buf.data(), 3, 4);   // 3 行 4 列
  static_assert(std::is_same_v<decltype(m),
                std::mdspan<double, std::dextents<std::size_t, 2>>>);

  for (std::size_t i = 0; i < m.extent(0); ++i)
    for (std::size_t j = 0; j < m.extent(1); ++j)
      m[i, j] = 10.0 * i + j;        // C++23 多参数 operator[]

  std::printf("%g %g\n", m[2, 3], buf[2 * 4 + 3]);   // 23 23

  try {
    (void)m.at(3, 0);                // C++26：越界抛 out_of_range
  } catch (const std::out_of_range&) {
    std::puts("at(3, 0) threw");
  }

  std::mdspan<double, std::extents<int, 3, 4>> fixed(buf.data());
  std::printf("%zu %zu\n", sizeof(m), sizeof(fixed));   // libc++：24 8
}
```

科学计算、图像处理和线性代数里常有这样的需求：数据在一块扁平的内存里，却要按二维、三维的形状访问。手写 `a[i * ncols + j]` 把形状和步长散落在每一处下标计算里；`int a[3][4]` 要求编译期尺寸；`vector<vector<int>>` 的数据不连续。

`std::mdspan`（C++23）是这块内存上的一个多维视图。和 `span` 一样，它不拥有存储，复制它只复制指针和形状（[[views]]）。`m[i, j]` 分三步算出元素：

```text
m[i, j, k]
  ├─ extents  ：形状。每一维多长？哪些维编译期已知？
  ├─ mapping  ：(i, j, k) → 一维偏移。行主序？列主序？带步长？
  └─ accessor ：(数据句柄, 偏移) → 元素引用
```

[[mdspan.mdspan.members#4]] 把 `operator[]` 写成一行：

```cpp
return acc_.access(ptr_, map_(static_cast<index_type>(std::move(indices))...));
```

`mdspan<T, Extents, LayoutPolicy, AccessorPolicy>` 的后两个模板参数默认是 `layout_right` 和 `default_accessor<T>`。上例里两个运行期的长度让 `m` 存了指针加两个 `size_t`，共 24 字节；`fixed` 的形状在类型里，只存一个指针。

!!! impl "libc++ 的实现状况（本机 Clang 23 自带的 libc++，下文示例据此验证）"
    | 设施 | 状态 |
    |---|---|
    | `extents`、`dextents`、`dims`、`layout_left`/`right`/`stride`、`default_accessor`、`mdspan`（含多参数 `operator[]`、CTAD） | 已实现 |
    | `aligned_accessor`、`mdspan::at`、经由 `std::cw<N>` 推导静态长度 | 已实现 |
    | `layout_left_padded`、`layout_right_padded` | 未实现 |
    | `submdspan`、`full_extent`、`extent_slice`、`range_slice`、`canonical_slices`、`subextents` | 未实现 |
    | 多维 `copy`、`fill` | 未实现 |

    用到未实现设施的代码块不带判定，只用来说明标准的规定。

## 形状：`extents` [mdspan.extents]

### 多维下标空间 [mdspan.overview]

[[mdspan.overview#1]] 定义了几个基本词。**多维下标空间**（multidimensional index space，[[g:multidimensional-index-space]]）是若干个整数半开区间 `[Lᵢ, Uᵢ)` 的笛卡尔积。区间的个数叫 **rank**。它的 **size** 是各维 `Uᵢ − Lᵢ` 的乘积；rank 为 0 时 size 为 1，这与零个数的乘积为 1 的约定一致。

[[mdspan.overview#3]] 把一个整数包叫做空间中的**多维下标**，条件是个数等于 rank，并且第 i 个值落在第 i 个区间内。后面所有关于越界的规定，都说成某某不是多维下标。`extents` 表示的空间下界总是 0，第 r 维的区间是 `[0, Dᵣ)`（[[mdspan.extents.overview#4]]）。

所以 rank 为 0 的 `mdspan` 不是空的，它恰好有一个元素，用空的下标列表 `m[]` 访问，相当于指向单个对象的视图：

```cpp run title="rank0.cpp" ok
#include <cstdio>
#include <mdspan>

int main() {
  int x = 7;
  std::mdspan<int, std::extents<int>> d(&x);   // rank 0：恰好一个元素
  d[] = 3;                                       // 空下标列表
  std::printf("%d %u\n", x, unsigned(d.size())); // 3 1
}
```

### 静态维与动态维

`extents<IndexType, Extents...>` 的每个模板实参要么是一个具体长度，叫**静态长度**（static extent，[[g:static-extent]]）；要么是 `dynamic_extent`，叫**动态长度**（dynamic extent，[[g:dynamic-extent]]），它的值在运行期存在对象里。只有动态长度占存储，全静态的 `extents` 是空类。

```cpp run title="extents.cpp" ok
#include <cstdio>
#include <mdspan>
#include <type_traits>

using E = std::extents<int, 3, std::dynamic_extent, 4>;   // 中间一维动态

int main() {
  static_assert(E::rank() == 3 && E::rank_dynamic() == 1);
  static_assert(E::static_extent(1) == std::dynamic_extent);

  E e1(5);         // 只给动态长度
  E e2(3, 5, 4);   // 给全部长度：静态位置的值必须一致（前置条件）
  std::printf("%d %d\n", e1.extent(1), int(e1 == e2));   // 5 1

  // 只有动态长度占存储；libc++ 上输出 1 4
  std::printf("%zu %zu\n", sizeof(std::extents<int, 3, 4>), sizeof(E));

  static_assert(std::is_same_v<std::dextents<int, 2>,
      std::extents<int, std::dynamic_extent, std::dynamic_extent>>);
  static_assert(std::is_same_v<std::dims<2>, std::dextents<std::size_t, 2>>);
}
```

[[mdspan.extents.overview#1]] 要求 `IndexType` 是有符号或无符号整数类型，并且每个静态长度都能用它表示。每个 `extents` 特化都建模 `regular`，并且可平凡复制（¶2）。

`extents` 有三个整数成员类型：`index_type`（即 `IndexType`，用于下标、`extent(r)` 和映射的结果）、`size_type`（`make_unsigned_t<index_type>`，用于 `mdspan::size()`）、`rank_type`（`size_t`，用于维数编号）。

`index_type` 常选 `int` 而不是 `size_t`。有符号溢出是 UB，编译器可以假设 `i * stride + j` 不溢出，从而做更积极的向量化和强度削减，这在 GPU 代码里尤其重要。

### 构造与转换 [mdspan.extents.cons]

`extents` 可以从整数包、`span`/`array` 或另一个 `extents` 构造。[[mdspan.extents.cons#6]] 的注 1 说明了整数包的两种给法：只给动态长度（正好是要存的那几个值），或者给全部长度。后一种情况下静态位置的值必须与模板实参一致，这是前置条件，编译器不检查。所有给出的值都必须非负并且能用 `index_type` 表示。

从另一个 `extents` 转换时，rank 必须相同，对应维要么静态值相同，要么至少一方是动态的（¶1）。[[mdspan.extents.cons#4]] 规定转换在下面两种情况下是 `explicit` 的：

```cpp
(((Extents != dynamic_extent) && (OtherExtents == dynamic_extent)) || ... ) ||
(numeric_limits<index_type>::max() < numeric_limits<OtherIndexType>::max())
```

前半是从动态到静态需要程序员担保长度，与 `span` 一致；后半是 `index_type` 的值域变窄也需要担保。所以从 `extents<size_t, ...>` 到 `extents<int, ...>` 即使形状完全一样也必须显式转换。这个规则会一路传到 mapping 和 `mdspan` 的转换上。

推导指引 `extents(Integrals...)` 推导为 `extents<size_t, ...>`（¶12–¶13）。普通整数推导为动态长度，`std::cw<4uz>` 这样的整型常量包装推导为静态长度。

### 观察函数与别名

- `static_extent(i)` 返回第 i 个模板实参（可能是 `dynamic_extent`），`extent(i)` 返回第 i 维的实际长度（[[mdspan.extents.obs]]）。
- 两个 `extents` 相等，当且仅当 rank 相同并且每一维长度相等，不管静态还是动态、不管 `index_type`（[[mdspan.extents.cmp]]）。
- `dextents<IndexType, Rank>` 是全动态的 `extents`；C++26 的 `dims<Rank, IndexType = size_t>` 是同一个东西，参数顺序相反，并且 `IndexType` 有默认值。

## 布局映射：从多维下标到偏移 [mdspan.layout]

### 映射要满足什么 [mdspan.layout.reqmts]

**布局映射**（layout mapping，[[g:layout-mapping]]）是一个对象 `m`，`m(i, j, ...)` 把多维下标换算成一维偏移。[[mdspan.layout.reqmts#1]] 要求它可复制、可比较相等，移动和交换不抛异常，并提供：

| 表达式 | 含义 |
|---|---|
| `m.extents()` | 形状 |
| `m(i...)` | 偏移，非负；先把下标转换成 `index_type` 不改变结果 |
| `m.required_span_size()` | size 为 0 时是 0，否则是最大偏移加 1 |
| `m.is_unique()` | 不同的下标映射到不同的偏移 |
| `m.is_exhaustive()` | `[0, required_span_size())` 中每个偏移都有下标映射到它 |
| `m.is_strided()` | 每一维都有固定步长 `sᵣ`：沿第 r 维走一步，偏移增加 `sᵣ` |
| `m.stride(r)` | 前置条件是 `is_strided()`，返回 `sᵣ` |
| `M::is_always_unique()` 等三个 | 常量表达式；对该类型所有对象都成立时才可以为 `true` |

`required_span_size()` 不是元素个数，而是底层存储至少要多长。带间隔的布局中它大于 `size()`；允许多个下标指向同一元素的布局中它可能小于 `size()`。

三个性质都是单向的保证。[[mdspan.layout.reqmts#14]]、¶16、¶18 都写成 "returns `true` only if…"，注 1、注 2、注 4 明确说条件成立时也可以返回 `false`，因为有些布局精确判断的代价太高。泛型代码只能依赖 `true`，`false` 只表示不知道。

这三个性质决定了能做哪些优化：unique 时并行写入不会冲突，多维 `copy` 就要求目标 `is_unique()`；exhaustive 时可以把整块存储当一维数组处理；strided 时可以交给需要步长参数的 BLAS 接口。

### 策略与映射 [mdspan.layout.policy.reqmts]

`mdspan` 的模板参数是**布局策略**（layout mapping policy），不是映射本身。策略 `MP` 是一个映射工厂：对任何 `extents` 特化 `E`，`MP::mapping<E>` 都是满足上述要求的映射，它的 `layout_type` 是 `MP`，`extents_type` 是 `E`。这样同一种布局可以套在任何形状上。标准的五种策略都是可平凡复制、可平凡默认构造的空结构体（[[mdspan.layout.policy.overview]]）。

以 rank 2、形状 `R × C`、下标 `(i, j)` 为例：

| 策略 | 偏移 | unique / exhaustive / strided |
|---|---|---|
| `layout_right` | `i * C + j`（行主序，C 的习惯） | 总是 / 总是 / 总是 |
| `layout_left` | `i + j * R`（列主序，Fortran 的习惯） | 总是 / 总是 / 总是 |
| `layout_stride` | `i * s₀ + j * s₁` | 总是 / 视步长而定 / 总是 |
| `layout_right_padded<P>` {{c++26}} | `i * S + j`，行距 `S >= C` | 总是 / `S == C` 时 / 总是 |
| `layout_left_padded<P>` {{c++26}} | `i + j * S`，列距 `S >= R` | 总是 / `S == R` 时 / 总是 |

```cpp run title="layout-mappings.cpp" ok
#include <array>
#include <cstdio>
#include <mdspan>

int main() {
  using E = std::extents<int, 2, 3>;
  std::layout_right::mapping<E> r(E{});
  std::layout_left::mapping<E>  l(E{});
  std::printf("right: %d %d,%d\n", r(1, 1), r.stride(0), r.stride(1));  // 4 3,1
  std::printf("left : %d %d,%d\n", l(1, 1), l.stride(0), l.stride(1));  // 3 1,2

  // 隔一个取一个：unique、strided，但不是 exhaustive
  std::layout_stride::mapping<std::extents<int, 3>> every_other(
      std::extents<int, 3>{}, std::array{2});
  std::printf("%d %d\n", int(every_other.is_exhaustive()),
              every_other.required_span_size());   // 0 5
}
```

### `layout_left` 与 `layout_right`

两者完全对称。以 `layout_left` 为例（[[mdspan.layout.left]]）：最左一维步长为 1，往右每一维的步长是左边各维长度之积。全静态时，整个空间的 size 必须能用 `index_type` 表示，否则编译期就被拒绝（[[mdspan.layout.left.overview#4]]）。

映射之间的转换必须保证同一个下标得到同一个偏移：

- 从另一个 `layout_left::mapping` 转换，`explicit` 与否跟随 `extents` 的转换；
- 从 `layout_right::mapping` 转换，只在 rank ≤ 1 时允许（[[mdspan.layout.left.cons#6]]），因为一维时行主序和列主序是同一个映射；
- 从 `layout_stride::mapping` 转换，前置条件是步长恰好是列主序的步长，除 rank 0 外都是 `explicit` 的（¶16）。

```cpp run title="layout-conversions.cpp" ok
#include <mdspan>
#include <type_traits>

using E1 = std::extents<int, 4>;
using E2 = std::extents<int, 2, 3>;
using L1 = std::layout_left::mapping<E1>;
using R1 = std::layout_right::mapping<E1>;
using L2 = std::layout_left::mapping<E2>;
using R2 = std::layout_right::mapping<E2>;
using S2 = std::layout_stride::mapping<E2>;

static_assert(std::is_convertible_v<R1, L1>);       // rank 1：可以互转
static_assert(!std::is_constructible_v<L2, R2>);    // rank 2：不行
static_assert(std::is_convertible_v<L2, S2>);       // left → stride：隐式
static_assert(std::is_constructible_v<L2, S2>);     // stride → left：
static_assert(!std::is_convertible_v<S2, L2>);      //   只能显式

int main() {}
```

### `layout_stride` [mdspan.layout.stride]

`layout_stride` 的步长由用户给出。[[mdspan.layout.stride.cons#4]] 的前置条件很强：每个步长都必须大于 0；并且存在一个维度的排列，使得按这个顺序每一维的步长不小于前一维的步长乘以前一维的长度。注 1 说明，这个条件保证了 `is_unique()` 为真。

所以 `layout_stride` 不能表达多个下标指向同一元素的布局，也不能表达步长为 0 的广播或负步长的反转，那些需要自定义映射。它能从任何总是 unique、总是 strided 的映射构造，包括用户自定义的映射（¶6），前提是源映射把全零下标映射到偏移 0（¶7.4）。`is_exhaustive()` 在运行期检查步长是否恰好构成某种维度顺序下的紧密排列（[[mdspan.layout.stride.obs#6]]）。

### 带填充的布局 {{c++26}}

矩阵的每一行末尾常有填充，例如为了让每行起点按 64 字节对齐，或者矩阵本身是一个更大矩阵的子块。`layout_right_padded<PaddingValue>` 与 `layout_right` 相同，只是行距 `stride(rank() − 2)` 可以大于最后一维的长度；`layout_left_padded` 对称地放宽列距 `stride(1)`（[[P2642R6]]）。

行距按 `PaddingValue` 向上取整。例如 `layout_left_padded<4>::mapping<extents<int, 5, 3>>` 的列距是不小于 5 的 4 的倍数，即 8；两维的步长是 1、8，`required_span_size()` 是 `(5−1)·1 + (3−1)·8 + 1 = 21`。行距在编译期可知时，[[mdspan.layout.leftpad.expo#2]] 建议实现不要存储它。只有行距恰好等于该维长度时，这种映射才是 exhaustive 的。

后面会看到，从行主序矩阵切出子矩阵时，结果最自然的布局就是 `layout_right_padded`。libc++ 还没有实现这两种布局，本节没有可运行的例子。

## 访问器：从偏移到元素 [mdspan.accessor]

**访问器策略**（accessor policy，[[g:accessor-policy]]）规定怎样从一个数据句柄和一个偏移得到元素的引用（[[mdspan.accessor.general#1]]）。如果对 `[0, N)` 中的每个 `i`，访问函数都能得到有效引用，就说 `[0, N)` 是这个句柄和访问器的**可访问范围**（accessible range，¶2）。`mdspan` 所有构造函数的前置条件都用这个词表述。

数据句柄 `data_handle_type` 不一定是指针，也不必能解引用（¶3 注 1），它可以是 GPU 设备指针、远程内存的句柄，或者压缩块的编号。[[mdspan.accessor.reqmts]] 要求访问器提供：

| 成员 | 要求 |
|---|---|
| `element_type` | 完整对象类型，不是抽象类 |
| `data_handle_type` | 可复制，移动和交换不抛异常 |
| `reference` | 与 `element_type&` 有公共引用；可以是代理，比如 `atomic_ref<T>` |
| `offset_policy` | 另一个访问器类型，能从本访问器构造，元素类型相同 |
| `a.access(p, i)` | 返回 `reference` |
| `a.offset(p, i)` | 返回句柄 `q`，用 `offset_policy` 访问 `q` 的第 `j` 个元素，等于访问 `p` 的第 `i + j` 个元素 |

`offset_policy` 是为切片准备的：取子视图时数据句柄要往前移，移动之后原来的某些性质（比如对齐）可能不再成立，所以允许换一个访问器类型。

### `default_accessor`

最简单的访问器：句柄是 `ElementType*`，`access(p, i)` 就是 `p[i]`，`offset(p, i)` 就是 `p + i`（[[mdspan.accessor.default.members]]）。`[0, n)` 是可访问范围，当且仅当 `[p, p + n)` 是有效范围。

它的转换构造函数只允许限定转换，即 `OtherElementType(*)[]` 能转换为 `element_type(*)[]` 时才可用（[[mdspan.accessor.default.members#1]]）。所以 `mdspan<int>` 能隐式转换为 `mdspan<const int>`，`mdspan<Derived>` 却不能转换为 `mdspan<Base>`。`ElementType` 不能是数组类型，多维的事交给 `extents`。

### `aligned_accessor` {{c++26}}

`aligned_accessor<ElementType, ByteAlignment>`（[[P2897R7]]）向编译器承诺数据句柄按 `ByteAlignment` 字节对齐：

- `ByteAlignment` 必须是 2 的幂，并且不小于 `alignof(ElementType)`；
- 可访问范围除了要求 `[p, p + n)` 有效，还要求 `n > 0` 时 `is_sufficiently_aligned<ByteAlignment>(p)` 为真（[[mdspan.accessor.aligned.overview#5]]、[[ptr.align]]）；
- `access(p, i)` 等价于 `assume_aligned<ByteAlignment>(p)[i]`，对齐假设直接交给优化器，便于生成对齐的 SIMD 加载指令；
- `offset_policy` 是 `default_accessor`，因为 `p + i` 一般不再对齐。

转换方向体现了谁承担担保：从 `aligned_accessor` 到 `default_accessor` 是隐式的，丢掉承诺总是安全的；从 `default_accessor` 到 `aligned_accessor` 是 `explicit` 的，凭空做出承诺必须显式写出；对齐值大的可以隐式转换为对齐值小的。

```cpp run title="aligned-accessor.cpp" ok
#include <cstdio>
#include <mdspan>
#include <memory>
#include <type_traits>

using Aligned = std::aligned_accessor<float, 16>;
using V4 = std::mdspan<float, std::extents<int, 4>,
                       std::layout_right, Aligned>;

float sum4(V4 x) { return x[0] + x[1] + x[2] + x[3]; }

int main() {
  alignas(16) float buf[8] = {1, 2, 3, 4, 5, 6, 7, 8};
  std::mdspan<float, std::extents<int, 4>> plain(buf);

  if (std::is_sufficiently_aligned<16>(plain.data_handle())) {
    // default_accessor → aligned_accessor 必须显式
    V4 a(plain.data_handle(), plain.mapping(), Aligned{});
    std::printf("%g\n", sum4(a));   // 10
  }
  static_assert(std::is_same_v<Aligned::offset_policy,
                               std::default_accessor<float>>);
  static_assert(!std::is_convertible_v<std::default_accessor<float>, Aligned>);
  static_assert(std::is_convertible_v<Aligned, std::default_accessor<float>>);
}
```

如果 `buf` 实际没有对齐，却构造了用 `aligned_accessor` 的 `mdspan`，就违反了构造函数关于可访问范围的前置条件，行为未定义。`assume_aligned` 的假设不成立时，优化器生成的对齐加载指令可能直接让程序崩溃。

## `mdspan` 本体 [mdspan.mdspan]

### 类型要求（[[mdspan.mdspan.overview]]）

`mdspan` 只有三个说明用成员：访问器 `acc_`、映射 `map_` 和数据句柄 `ptr_`。`ElementType` 必须是完整的对象类型，不能是抽象类或数组，并且与访问器的 `element_type` 相同（¶2）。每个特化都可复制；访问器、映射和句柄都可平凡复制时，`mdspan` 也可平凡复制（¶5）。

### 构造与类型推导

所有构造函数都有同一条前置条件：`[0, map_.required_span_size())` 是 `ptr_` 和 `acc_` 的可访问范围。`mdspan` 无法检查这一点，传入的缓冲区太小就是 {{ub}}（见常见误解一节）。

- 默认构造要求 `rank_dynamic() > 0`（[[mdspan.mdspan.cons#1]]）。默认构造的指针为空，空指针上唯一的可访问范围是 `[0, 0)`，所以 `required_span_size()` 必须为 0；只有存在动态长度（值初始化为 0）时才能保证这一点。全静态的 `mdspan` 因此没有默认构造函数。
- `(p, exts...)` 接受 `rank()` 个或 `rank_dynamic()` 个长度，总是 `explicit` 的；`(p, span 或 array)` 在个数不等于 `rank_dynamic()` 时是 `explicit` 的。
- `(p, extents)`、`(p, mapping)` 和 `(p, mapping, accessor)`。只有最后一个能传入非默认构造的访问器。
- 从另一个 `mdspan` 转换：映射或访问器的转换是 `explicit` 的，这个转换就是 `explicit` 的（¶24）。加固实现会检查每个静态维与源的实际长度一致（¶22）。

常用的几条推导指引：

| 实参 | 推导结果 |
|---|---|
| 一维 C 数组 | `mdspan<T, extents<size_t, N>>`，静态长度 |
| 裸指针 | `mdspan<T, extents<size_t>>`，rank 0 |
| `(T*, 整数...)` | 普通整数推导为动态长度，`std::cw<N>` 推导为静态长度 |
| `(T*, span<I, N>)` 或 `(T*, array<I, N>)` | `mdspan<T, dextents<size_t, N>>` |
| `(T*, extents)` 或 `(T*, mapping)` | 保留 `extents`，或取映射的 `extents_type` 和 `layout_type` |

```cpp run title="mdspan-ctad-conversions.cpp" ok
#include <array>
#include <mdspan>
#include <type_traits>
#include <utility>

int buf[12];
std::mdspan a(buf, std::cw<3uz>, std::cw<4uz>);   // 静态长度
static_assert(std::is_same_v<decltype(a),
              std::mdspan<int, std::extents<std::size_t, 3, 4>>>);
std::mdspan b(buf, std::array{3, 4});              // 动态长度
static_assert(std::is_same_v<decltype(b), std::mdspan<int, std::dims<2>>>);
std::mdspan c(buf);                                // C 数组：rank 1
static_assert(std::is_same_v<decltype(c),
              std::mdspan<int, std::extents<std::size_t, 12>>>);
int* p = buf;
std::mdspan d(p);                                  // 裸指针：rank 0
static_assert(decltype(d)::rank() == 0);

// int → const int、静态 → 动态：隐式
std::mdspan<const int, std::dims<2>> ro1 = a;
// index_type 从 size_t 变窄到 int：必须显式
std::mdspan<const int, std::dextents<int, 2>> ro2{a};

static_assert(!std::is_default_constructible_v<
              std::mdspan<int, std::extents<int, 3>>>);
static_assert(std::is_default_constructible_v<std::mdspan<int, std::dims<1>>>);
static_assert(std::is_trivially_copyable_v<std::mdspan<int, std::dims<2>>>);

int main() {}
```

`ro2` 那一行最容易让人意外：形状完全兼容，元素只是加了 const，却必须显式转换。原因是 `extents<size_t, …>` 到 `extents<int, …>` 的值域变窄（[[mdspan.extents.cons#4]]），经 `layout_right::mapping` 的 `explicit(!is_convertible_v<OtherExtents, extents_type>)` 传到了 `mdspan`。用 CTAD 从整数推导出的下标类型是 `size_t`，手写的函数参数却常用 `int`，这是 `mdspan` 用户最常遇到的不能隐式转换的情况。

注意数组和指针的区别：`std::mdspan m(buf)` 中，`buf` 是 `int[12]` 时推导出 rank 1、长度 12；是 `int*` 时推导出 rank 0。

### 下标运算 [mdspan.mdspan.members]

`operator[]` 接受恰好 `rank()` 个下标（¶1）。¶3 规定了一条加固前置条件：下标必须是 `extents()` 中的多维下标，也就是每一维各自在范围内。注 1 指出这蕴含最终偏移小于 `required_span_size()`，反之不成立。

多参数的 `operator[]` 依赖 C++23 的语法变化：方括号里可以是逗号分隔的列表，交给重载的 `operator[]`（[[expr.sub]]、[[over.sub]]、[[P2128R6]]）。内建下标仍然只接受一个表达式。C++20 先弃用了下标里的逗号表达式 `a[i, j]`，C++23 再把这个语法让给多参数下标。

也可以传一个 `span` 或 `array` 作下标，效果等于把它展开后调用（¶5–¶6）。C++26 的 `at()` 在下标不是多维下标时抛 `out_of_range`（¶7–¶12）。`size()` 返回无符号的 `size_type`（¶13–¶14），`empty()` 在 size 为 0 时为真。

```cpp run title="mdspan-subscript-errors.cpp" error
#include <mdspan>

int buf[12];
std::mdspan<int, std::dims<2>> m(buf, 3, 4);
int x = m[1][2];                                   // error: 没有单参数 operator[]
int y = m[1, 2];                                   // OK
std::mdspan<int, std::extents<int, 3, 4>> s1 = m;  // error: 动态 → 静态必须显式
std::mdspan<int, std::extents<int, 3, 4>> s2{m};   // OK：加固实现检查长度
```

### 同一块内存，不同的视图

换一个布局就是换一种解读方式，数据一个字节都不用动：

```cpp run title="mdspan-views.cpp" ok
#include <array>
#include <cstdio>
#include <mdspan>

int main() {
  int buf[6] = {0, 1, 2, 3, 4, 5};
  std::mdspan<int, std::extents<int, 2, 3>> a(buf);   // 2×3 行主序
  // 同一块内存看成 3×2 列主序：恰好是 a 的转置
  std::mdspan<int, std::extents<int, 3, 2>, std::layout_left> t(buf);
  for (int i = 0; i < 2; ++i)
    for (int j = 0; j < 3; ++j)
      if (a[i, j] != t[j, i]) return 1;

  // 只看第 1 列：长度 2、步长 3，起点偏移 1
  using L = std::layout_stride::mapping<std::extents<int, 2>>;
  std::mdspan col(buf + 1, L(std::extents<int, 2>{}, std::array{3}));
  std::printf("%d %d %d\n", col[0], col[1],
              int(col.is_exhaustive()));   // 1 4 0
}
```

## 取子视图：`submdspan` {{c++26}} [mdspan.sub]

`submdspan(m, slices...)` 为每一维给一个**切片说明符**（slice specifier），返回一个只看原 `mdspan` 一部分元素的新 `mdspan`。它由 [[P2630R4]] 加入 C++26，切片类型和辅助函数后来又经过改写（特性测试宏 `__cpp_lib_submdspan` 现为 202603L）。下面按当前草案叙述，libc++ 尚未实现本节的任何设施。

按当前草案，下面几行的结果如注释所示：

```cpp
double buf[24];
std::mdspan m(buf, 4, 6);          // 4×6，layout_right

auto row = std::submdspan(m, 2, std::full_extent);
// rank 1，长度 6，layout_right
auto col = std::submdspan(m, std::full_extent, 3);
// rank 1，长度 4，layout_stride，步长 6
auto blk = std::submdspan(m, std::pair{1, 3}, std::pair{2, 5});
// 2×3，layout_right_padded<dynamic_extent>，行距 6
auto odd = std::submdspan(m, std::full_extent,
                          std::extent_slice{1, 3, 2});
// 4×3，取第 1、3、5 列，layout_stride
```

### 切片的种类 [mdspan.sub.overview]

[[mdspan.sub.overview#2]] 列出可以用作切片的类型：

| 切片 | 含义 | 这一维在结果中 |
|---|---|---|
| 可转换为 `full_extent_t`，即 `std::full_extent` | 整维 | 保留，长度不变 |
| 可转换为 `IndexType` 的整数 | 固定这一维的下标 | 消失，rank 减 1 |
| `extent_slice{offset, extent, stride}` | 从 `offset` 起取 `extent` 个，步长 `stride` | 保留，长度为 `extent` |
| `range_slice{first, last, stride}` | 在 `[first, last)` 中按步长取 | 保留 |
| 能用结构化绑定拆成两个整数的类型，如 `pair{a, b}` | `[a, b)` | 保留，长度 `b − a` |

使维度消失的切片叫**折叠切片**（collapsing slice，¶5）。整维和步长为编译期常量 1 的 `extent_slice` 叫**单位步长切片**（unit-stride slice，¶6），它们决定了结果能否保留连续布局。

!!! warning "`extent_slice` 的 `extent` 是选出的元素个数"
    `extent_slice{.offset = 1, .extent = 4, .stride = 3}` 与 `range_slice{.first = 1, .last = 11, .stride = 3}` 都选出下标 1、4、7、10（[[mdspan.sub.range.slices#3]] 注 1）。`extent_slice` 的 `extent` 是结果的长度 4，不是原区间的长度。P2630 里字段相同的 `strided_slice`，`extent` 指的是原区间的长度，从旧资料迁移时要特别注意。

### 规范化

`submdspan` 先把所有切片转换成三种**规范形式**之一：`full_extent_t`、下标（`IndexType` 或 `constant_wrapper<v>`）、各字段都是规范下标的 `extent_slice`（[[mdspan.sub.overview#4]]）。`pair` 和 `range_slice` 都被转换成 `extent_slice`，元素个数为 `1 + (跨度 − 1) / 步长`（[[mdspan.sub.helpers#7]]）。

编译期常量在这一步被保留下来：`std::cw<N>` 规范化为 `cw<IndexType(N)>`，而不是普通整数。规范化后，`extent_slice` 的 `extent` 是 `constant_wrapper` 时，结果的这一维是静态长度；整维保留原来的静态长度；其他情况都是动态长度（[[mdspan.sub.extents#5]]）。公开的 `canonical_slices` 和 `subextents` 分别返回规范化后的切片和结果形状。

每个切片都必须落在对应维的范围内，选取多于一个元素时步长必须为正。违反这一点是普通的前置条件违反（[[mdspan.sub.sub#6]]），行为未定义，不是加固前置条件。

### 结果用什么布局

`submdspan` 自己不知道怎样切任意布局。它把规范化的切片交给 `submdspan_mapping(src.mapping(), slices...)`，这个名字只经 ADL 查找（[[mdspan.sub.map.sliceable#2]]、[[basic.lookup.argdep]]）。标准布局都以隐藏友元的形式提供它，自定义布局也可以提供。返回值 `submdspan_mapping_result{mapping, offset}` 给出新映射和起点偏移，[[mdspan.sub.sub#7]] 用它构造结果：

```cpp
auto sub_map_result = submdspan_mapping(src.mapping(), slices...);
return mdspan(src.accessor().offset(src.data_handle(), sub_map_result.offset),
              sub_map_result.mapping,
              typename AccessorPolicy::offset_policy(src.accessor()));
```

注意最后一个实参：结果的访问器是原访问器的 `offset_policy`。对 `aligned_accessor`，切片之后就变回 `default_accessor`。

以 `layout_right` 为例，结果布局按下面的顺序选择（[[mdspan.sub.map.right#1]]）：

1. 原 rank 为 0 时原样返回；结果 rank 为 0 时用 `layout_right`。
2. 结果的各维中，最后几维都是整维，再往前一维是单位步长切片，更前面都是被折叠的下标：仍然是 `layout_right`。上例的 `row` 就是这样。
3. 最后一维是单位步长切片，并满足（1.4）的其余条件：`layout_right_padded`，行距取自原映射。上例的 `blk` 两维都是单位步长切片，但第二维不是整维，于是得到行距为 6 的 padded 布局。
4. 否则用 `layout_stride`。上例的 `col` 和 `odd` 最后一维不是单位步长切片，都落到这里。

`layout_left` 与此镜像对称，`layout_stride` 切出来总是 `layout_stride`，两种填充布局有各自的规则。这些规则的用意是能证明连续的就保留连续布局，从而保留 `is_always_exhaustive()` 这类编译期性质，下游代码可以继续走快速路径。如果没有 `layout_right_padded`，`blk` 只能退化成 `layout_stride`，丢掉行内连续这一信息。

## 多维 `copy` 与 `fill` {{c++29}} [mdspan.copy]

C++26 之后的草案在 `<mdspan>` 中加入了 `mdspan` 版本的 `std::copy(src, dst)` 和 `std::fill(dst, value)`，各有带执行策略的重载（`__cpp_lib_mdspan_copy` 为 202606L）：

- `copy` 要求两边都是 `mdspan`，`Dst::reference` 能由 `Src::reference` 赋值，两边的 `extents` 兼容（[[mdspan.copy#1]]）；
- 前置条件是 `dst.is_unique()`，并且源和目标的元素不重叠（¶2）；加固前置条件是两边的 `extents()` 相等（¶3）；
- 效果是逐元素赋值，没有规定遍历顺序。正因为如此才要求目标 unique、源和目标不重叠，实现可以按两边的布局选择最快的遍历顺序，甚至向量化。

它们和 `<algorithm>` 中的 `std::copy(first, last, out)`、`std::fill(first, last, value)` 参数个数不同，又都有约束，不会互相干扰。libc++ 尚未实现。

## 常见误解

!!! pitfall "加固模式能发现缓冲区太小"
    构造 `mdspan` 时要求 `[0, required_span_size())` 是可访问范围，但没有任何实现能知道一个裸指针背后有多大的存储。

```cpp run title="mdspan-too-small.cpp" ub
#include <mdspan>

int main() {
  int buf[6]{};
  std::mdspan m(buf, 3, 4);   // UB：要求 [0, 12) 可访问，buf 只有 6 个元素
  return m[2, 3];             // 访问 buf[11]
}
```

本机用 ASan 运行报告 stack-buffer-overflow；而 libc++ 的 debug 加固模式不报错，因为 `(2, 3)` 确实是 3×4 形状中合法的多维下标。

!!! pitfall "偏移在缓冲区内就没问题"
    反过来，在 3×4 行主序的 `mdspan` 上，`m[0, 4]` 算出的偏移是 4，落在缓冲区之内，ASan 看不出问题。但 `(0, 4)` 不是多维下标，违反了 `operator[]` 的加固前置条件。下标逐维检查而不只检查最终偏移，正是为了抓这类错误。

```cpp run title="mdspan-hardening.cpp" flags="-std=c++2c -D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_DEBUG"
#include <cstdio>
#include <mdspan>

int main() {
  int buf[12]{};
  std::mdspan<int, std::dims<2>> m(buf, 3, 4);
  std::printf("%d\n", m[0, 4]);   // 偏移 4 在 buf 之内，但 (0, 4) 越界
}
```

本机 libc++ 的 debug 模式报告 `mdspan: operator[] out of bounds access` 并终止，fast 模式以陷阱指令终止；不开加固时程序打印 0，这是没有任何提示的 {{ub}}。

!!! pitfall "`m[i][j]` 与 `m[i, j]` 一样"
    `mdspan` 没有返回子视图的单参数 `operator[]`（rank 1 时 `m[i]` 直接返回元素），所以不能链式下标。给自己写的多维容器加 `operator[]` 时也要注意：C++20 把 `a[i, j]` 解析为逗号表达式 `a[(i, j)]`（已弃用），C++23 起才是两个实参的 `operator[]`，同一行代码在不同语言模式下意思不同。

!!! pitfall "`layout_stride` 能表达广播或反转"
    [[mdspan.layout.stride.cons#4]] 要求每个步长大于 0，并且映射是 unique 的。步长为 0 的广播和负步长的反转都需要自定义布局映射。

## 历史

| 版本 | 变化 |
|---|---|
| C++23 | `mdspan`、`extents`、`dextents`、`layout_left`/`right`/`stride`、`default_accessor`（[[P0009R18]]）；配套的多参数下标运算符（[[P2128R6]]） |
| C++26 | `submdspan`（[[P2630R4]]）；`layout_left_padded`/`layout_right_padded`（[[P2642R6]]）；`aligned_accessor`（[[P2897R7]]）；`dims`；`mdspan::at`；经由整型常量包装推导静态长度；`operator[]` 的下标检查和转换构造函数的长度检查成为加固前置条件 |
| 之后的修订 | 切片类型改为 `extent_slice`/`range_slice`，规范化拆成 `canonical_slices`/`subextents`；C++26 之后加入多维 `copy`/`fill` |

## 思考题

!!! question "思考题 1"
    `layout_left::mapping<extents<int, 3, 4>>` 与 `layout_right::mapping<extents<int, 3, 4>>` 为什么不能互相转换，而 `extents<int, 4>` 的可以？如果确实要把行主序矩阵当列主序用，应该怎么做？

<details markdown="1">
<summary>答案</summary>

映射之间的转换必须保证同一个下标得到同一个偏移。rank ≤ 1 时两种布局都是 `m(i) = i`，所以 [[mdspan.layout.left.cons#6]] 只在 `rank() <= 1` 时允许转换。rank 2 时 `(i, j)` 在两种布局下的偏移不同，转换后会看到不同的元素，所以不提供。

要把行主序的 `R × C` 矩阵当列主序用，应交换长度构造新视图：`mdspan<T, extents<int, C, R>, layout_left>(ptr)`，它恰好是原矩阵的转置（见上文 `mdspan-views.cpp`）。
</details>

!!! question "思考题 2"
    为什么 `mdspan<int, extents<int, 3>>` 不能默认构造，`mdspan<int, extents<int, 0>>` 也不能？

<details markdown="1">
<summary>答案</summary>

[[mdspan.mdspan.cons#1]] 的约束是 `rank_dynamic() > 0`，两者都是 0。对 `extents<int, 3>`，理由是 ¶2 的前置条件：空指针上 `[0, 3)` 不可能是可访问范围。对 `extents<int, 0>`，`required_span_size()` 是 0，前置条件其实能满足，但约束没有去区分某一维是否恰好为 0，而是把全静态的情况统一排除。约束在编译期检查，规则越简单，各实现越不容易产生分歧。
</details>

!!! question "思考题 3"
    对一个使用 `aligned_accessor<float, 64>` 的 `mdspan` 做 `submdspan(m, std::full_extent)`，结果的访问器是什么类型？为什么标准不让它保持 `aligned_accessor`？

<details markdown="1">
<summary>答案</summary>

结果的访问器是 `AccessorPolicy::offset_policy`（[[mdspan.sub.sub#7]]），`aligned_accessor` 的 `offset_policy` 是 `default_accessor<float>`。即使这次切片的偏移恰好是 0，类型也无法在编译期知道这一点；一般的偏移是运行期的值，`p + offset` 不再保证 64 字节对齐。调用者能确认对齐时，可以先用 `is_sufficiently_aligned<64>` 检查，再显式构造回 `aligned_accessor`，做法与上文 `aligned-accessor.cpp` 相同。
</details>

<details class="fine" markdown="1"><summary>其余条文</summary>

[[mdspan.syn]]：`<mdspan>` 标为 mostly freestanding，独立实现也要提供其中的大部分内容。`mdspan` 是 partially freestanding：会抛异常的 `at` 标为 freestanding-deleted。

[[mdspan.extents.expo]] 定义了几个说明用的辅助函数：*dynamic-index*`(i)` 是前 i 维中动态长度的个数，用来找到第 r 维的值存在哪里；*dynamic-index-inv* 是它的反函数；*fwd-prod-of-extents*`(i)` 是前 i 维长度之积，即 `layout_left` 的步长；*rev-prod-of-extents*`(i)` 是第 i 维之后各维长度之积，即 `layout_right` 的步长；*index-cast* 把整数原样返回，其他类型 `static_cast` 成 `index_type`。

[[mdspan.layout.general]] 引入要求中用到的记号（`M`、`m`、`i`、`j`、`r`，以及第 r 位为 1、其余为 0 的整数包 `dr`），并定义 *LEAST-MULTIPLE-AT-LEAST*`(x, y)`：`x` 为 0 时是 `y`，否则是不小于 `y` 的 `x` 的最小倍数。填充布局用它计算行距。

[[mdspan.layout.stride.expo]] 定义 *REQUIRED-SPAN-SIZE*（rank 0 时为 1，size 为 0 时为 0，否则为 `1 + Σ (extent(r) − 1) * stride(r)`）、*OFFSET*（全零下标的偏移）和仅用于说明的概念 *layout-mapping-alike*。`layout_stride` 的 `operator==` 可以与任何总是 strided 的映射比较：形状相等、*OFFSET* 为 0、每维步长相等（[[mdspan.layout.stride.obs#9]]）。

[[mdspan.sub.map.sliceable]] 规定可切片映射的要求：对有效切片，结果映射的形状等于 `subextents(...)`，结果中每个下标的偏移加上 `offset` 等于原映射在对应原下标处的值；对非规范的切片类型调用必须非良构。[[mdspan.sub.map.common#8]] 规定起点偏移取所有切片下界处的映射值；某一维下界等于该维长度（空切片）时改取 `required_span_size()`，以免在越界的下标上求值。

[[mdspan.sub.helpers]] 中 ¶7–¶10 定义的辅助函数叫 *canonical-range-slice*，¶12 调用时却写成 *canonical-slice-range*。两者显然是同一个函数，这是编辑性的不一致，不影响语义。

</details>
