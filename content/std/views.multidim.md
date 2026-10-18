---
title: 多维访问：mdspan
summary: std::mdspan 的完整拆解——多维下标空间与 extents（静态/动态混合、index_type、dextents/dims）、layout mapping 的要求（unique/exhaustive/strided、required_span_size）与五种标准布局（left/right/stride/left_padded/right_padded）、accessor policy（default_accessor、aligned_accessor）、mdspan 的构造与多参数 operator[]、submdspan 的切片规范化与布局保持规则，以及 C++26 之后的多维 copy/fill；附 libc++ 实现现状
status: done
covers: *
papers: P0009R18, P2128R6, P2630R4, P2642R6, P2897R7
related: views, views.contiguous, expr.sub, over.sub, basic.lookup.argdep, array, ptr.align
tags: 标准库, mdspan, 视图, 多维数组, 布局, 加固
updated: 2026-10-18
---

`std::mdspan` 解决的是科学计算、图像处理、线性代数里最常见的一件事：**一块扁平内存，按多维形状来索引**。C 风格的 `a[i * ncols + j]` 把形状和步长散落在每一处下标计算里；`int a[3][4]` 要求编译期尺寸；`vector<vector<int>>` 不连续。`mdspan` 把这件事拆成三个可以独立替换的零件：

```text
m[i, j, k]
   │
   ├─ extents    ：形状。每一维多长？哪些维编译期已知？         → [mdspan.extents]
   ├─ mapping    ：(i, j, k) → 一维偏移 off。行主序？列主序？带步长？ → [mdspan.layout]
   └─ accessor   ：(data_handle, off) → reference。普通解引用？对齐假设？原子？ → [mdspan.accessor]
```

于是 `mdspan<T, Extents, Layout, Accessor>` 的 `operator[]` 就是一行：

```cpp
return acc_.access(ptr_, map_(static_cast<index_type>(std::move(indices))...));
```

这是 [mdspan.mdspan.members] ¶4 的原文。理解了这三个零件各自的要求，`mdspan` 就没有秘密了。本页覆盖 [views.multidim] 的全部子条款；与 `span` 的共性（不拥有存储、浅 const、平凡可复制）见 [[views]] 导读。

!!! impl "libc++ 实现现状（Homebrew LLVM 23 自带的 libc++，本页所有示例据此验证）"
    | 设施 | 状态 |
    |---|---|
    | `extents`、`dextents`、`dims`、`layout_left`/`right`/`stride`、`default_accessor`、`mdspan`（含多参数 `operator[]`、CTAD） | 已实现 |
    | `aligned_accessor` {{c++26}}、`mdspan::at` {{c++26}}、经由 `std::cw<N>` 的静态 extent 推导 | 已实现 |
    | `layout_left_padded` / `layout_right_padded` {{c++26}} | **未实现** |
    | `submdspan`、`full_extent`、`extent_slice`/`range_slice`、`canonical_slices`、`subextents` | **未实现** |
    | 多维 `copy` / `fill`（[mdspan.copy]） | **未实现** |
    本页涉及未实现设施的代码块不带判定标记，只作为标准语义的说明。

## 多维下标空间（[mdspan.overview]）

¶1 给出三个定义：

- **多维下标空间**（*multidimensional index space*，[[g:multidimensional-index-space]]）：若干个整数半开区间 `[Lᵢ, Uᵢ)` 的笛卡尔积；
- 它的 **rank**：区间个数；
- 它的 **size**：`∏(Uᵢ − Lᵢ)`；**rank 为 0 时 size 为 1**。

最后一条容易被忽视：rank-0 的 `mdspan` 不是"空"的，它恰好有一个元素，用 `m[]` 访问。这和"零个数的乘积是 1"的数学约定一致，也让 rank-0 `mdspan` 成为"指向单个对象的视图"。

```cpp run title="rank0.cpp" ok
#include <cstdio>
#include <mdspan>

int main() {
  int x = 7;
  std::mdspan<int, std::extents<int>> d(&x);   // rank 0：恰好一个元素
  d[] = 3;                                       // 空的下标列表，C++23 起合法
  std::printf("%d %u\n", x, unsigned(d.size())); // 3 1
}
```

¶2 定义 **rank index**：`[0, rank)` 中的整数。¶3 定义**多维下标**：一个整数包 `idx`，个数等于 rank，且第 i 个值落在第 i 个区间里。之后所有"越界"都用"不是多维下标"来表述。

在 `mdspan` 里，下界永远是 0（[mdspan.extents.overview] ¶4：第 r 个区间是 `[0, Dᵣ)`），所以"多维下标"就是"每一维都满足 `0 <= iᵣ < extent(r)`"。

## 概要（[mdspan.syn]）

`<mdspan>` 声明的东西按用途分组：

| 组 | 名字 |
|---|---|
| 形状 | `extents`、`dextents`、`dims` |
| 布局策略 | `layout_left`、`layout_right`、`layout_stride`、`layout_left_padded<P>`、`layout_right_padded<P>` |
| 访问器 | `default_accessor`、`aligned_accessor` |
| 视图本体 | `mdspan`（默认 `LayoutPolicy = layout_right`、`AccessorPolicy = default_accessor<ElementType>`） |
| 切片 | `extent_slice`、`range_slice`、`full_extent_t`/`full_extent`、`submdspan_mapping_result`、`canonical_slices`、`subextents`、`submdspan` |
| 多维算法 | `copy`、`fill`（各带执行策略重载）{{c++29}} |

注释 `// mostly freestanding`：只有会抛异常的 `mdspan::at` 被标为 *freestanding-deleted*，带执行策略的算法也不在独立实现中。

## `extents`：形状（[mdspan.extents]）

### 概览（[mdspan.extents.overview]）

`extents<IndexType, Extents...>` 表示一个 rank 为 `sizeof...(Extents)` 的多维下标空间。模板实参中的每个值要么是一个具体长度（**静态 extent**，[[g:static-extent]]），要么是 `dynamic_extent`（**动态 extent**，[[g:dynamic-extent]]），后者的值在运行期存进对象里。

!!! std
    `Eᵣ` is a *dynamic extent* if it is equal to `dynamic_extent`, otherwise `Eᵣ` is a *static extent*.
    第 r 个模板实参等于 `dynamic_extent` 时是动态 extent，否则是静态 extent。

¶1 *Mandates*：`IndexType` 是有符号或无符号整数类型；每个静态 extent 都能用 `IndexType` 表示。

¶2：每个 `extents` 特化建模 `regular` 且平凡可复制。

¶3：记 `Dᵣ` 为第 r 维的实际长度——动态 extent 取存储的值，静态 extent 就是 `Eᵣ` 本身。

说明性成员 `array<index_type, rank_dynamic()> dynamic-extents` 揭示了布局：**只有动态 extent 占存储**。全静态的 `extents` 是空类。

成员类型里有三个"整数类型"，用途各不相同：

| 成员 | 定义 | 用于 |
|---|---|---|
| `index_type` | `IndexType` | 下标、`extent(r)`、映射的结果 |
| `size_type` | `make_unsigned_t<index_type>` | `mdspan::size()` |
| `rank_type` | `size_t` | 维数编号 `r` |

`index_type` 选 `int` 而不是 `size_t` 并非偷懒：映射计算 `i * stride + j` 在 32 位有符号整数上，编译器可以假设不溢出（有符号溢出是 UB），从而做更激进的向量化和强度削减。GPU 代码里这一点尤其重要。

### 仅用于说明的辅助函数（[mdspan.extents.expo]）

- *dynamic-index*`(i)`（¶1–¶2）：前 i 维中有几个动态 extent——用来把"第 r 维"翻译成 *dynamic-extents* 数组里的位置；
- *dynamic-index-inv*`(i)`（¶3–¶4）：反过来，第 i 个动态 extent 是第几维；
- *fwd-prod-of-extents*`(i)`（¶5–¶6）：前 i 维长度之积，即 `layout_left` 的 stride；
- *rev-prod-of-extents*`(i)`（¶7–¶8）：第 i 维之后各维长度之积，即 `layout_right` 的 stride；
- *index-cast*`(i)`（¶9）：整数原样返回，其他类型（如整数类类型、`constant_wrapper`）`static_cast` 成 `index_type`。

### 构造函数（[mdspan.extents.cons]）

四种构造方式，规则高度一致：

| 构造 | 段落 | 关键约束 | 前置条件（{{ub}}） | `explicit` |
|---|---|---|---|---|
| 从另一个 `extents` | ¶1–¶4 | rank 相同；对应维静态值相同或有一方动态 | 目标静态维与源实际值相等；值可用 `index_type` 表示 | 静态 ← 动态，或 `index_type` 范围变窄 |
| 从整数包 `exts...` | ¶5–¶8 | 个数为 `rank_dynamic()` **或** `rank()` | 给全部 extent 时静态位置的值必须匹配；值非负且可表示 | 总是 |
| 从 `span<T, N>` / `array<T, N>` | ¶9–¶11 | `N` 为 `rank_dynamic()` 或 `rank()` | 同上 | `N != rank_dynamic()` 时 |

¶6.3 的注 1 点出了一个方便的设计：**可以只给动态 extent**（只给需要存储的那几个值），**也可以给全部 extent**（此时静态维必须与模板实参一致，这是前置条件，不是编译期检查）。

¶4 的 `explicit` 条件值得一读：

```cpp
(((Extents != dynamic_extent) && (OtherExtents == dynamic_extent)) || ... ) ||
(numeric_limits<index_type>::max() < numeric_limits<OtherIndexType>::max())
```

前半是"动态 → 静态需要担保"，与 `span` 一致；后半是"`index_type` 的值域变窄需要担保"——从 `extents<size_t, ...>` 到 `extents<int, ...>` 即使形状完全兼容也是 `explicit` 的。这个细节会一路传递到 mapping 和 `mdspan` 的转换上（见下文 `mdspan` 构造一节）。

¶12–¶13 是推导指引：`extents(Integrals...)` 推导为 `extents<size_t, maybe-static-ext<Integrals>...>`。普通整数推导为动态，`std::cw<4uz>` 这类整型常量包装推导为静态（*maybe-static-ext* 的定义见 [[views.contiguous]] 概要一节）。

### 观察器、比较与别名（[mdspan.extents.obs] 至 [mdspan.extents.dims]）

- `static_extent(i)`：返回 `Eᵢ`（可能是 `dynamic_extent`）；`extent(i)`：返回 `Dᵢ`。二者的前置条件都是 `i < rank()`。
- `operator==`（[mdspan.extents.cmp] ¶1）：rank 相同且每一维长度相等即相等，**不管静态还是动态、不管 `index_type`**。`extents<int, 3>` 与 `extents<size_t, dynamic_extent>{3}` 相等。
- `dextents<IndexType, Rank>`：全动态、rank 为 `Rank`。
- `dims<Rank, IndexType = size_t>` {{c++26}}：同上，只是参数顺序反过来、`IndexType` 有默认值——`dims<2>` 是 `dextents<size_t, 2>` 的简写。

```cpp run title="extents.cpp" ok
#include <cstdio>
#include <mdspan>
#include <type_traits>

using E = std::extents<int, 3, std::dynamic_extent, 4>;   // 中间一维动态

int main() {
  static_assert(E::rank() == 3 && E::rank_dynamic() == 1);
  static_assert(E::static_extent(1) == std::dynamic_extent);

  E e1(5);            // 只给动态 extent：N == rank_dynamic()
  E e2(3, 5, 4);      // 给全部 extent：N == rank()；静态位置的值必须匹配（前置条件）
  std::printf("%d %d\n", e1.extent(1), int(e1 == e2));   // 5 1

  // 只有动态 extent 占存储；libc++ 上输出 1 4
  std::printf("%zu %zu\n", sizeof(std::extents<int, 3, 4>), sizeof(E));

  static_assert(std::is_same_v<std::dextents<int, 2>,
                               std::extents<int, std::dynamic_extent, std::dynamic_extent>>);
  static_assert(std::is_same_v<std::dims<2>, std::dextents<std::size_t, 2>>);
}
```

## Layout mapping：从多维下标到偏移（[mdspan.layout]）

### 记号（[mdspan.layout.general]）

¶1 引入后面要求里用到的记号：`M` 是映射类型，`m` 是它的值，`i`/`j` 是多维下标包，`r` 是 rank index，`dr` 是"第 r 位为 1、其余为 0"的整数包（用来表达"沿第 r 维走一步"）。¶2 定义了几个说明性工具：*is-mapping-of*、*is-layout-left-padded-mapping-of*、*is-layout-right-padded-mapping-of*，以及 *LEAST-MULTIPLE-AT-LEAST*`(x, y)`——不小于 `y` 的 `x` 的最小倍数（`x` 为 0 时就是 `y`），这是 padded 布局计算行距的核心。

### 映射的要求（[mdspan.layout.reqmts]）

一个类型 `M` 满足 **layout mapping 要求**（[[g:layout-mapping]]），需要（¶1）建模 `copyable` 与 `equality_comparable`，移动与交换不抛异常，并提供：

| 表达式 | 段落 | 含义 |
|---|---|---|
| `M::extents_type` / `index_type` / `rank_type` / `layout_type` | ¶2–¶5 | 形状类型及其派生类型；`layout_type` 是能"生出"`M` 的策略类型 |
| `m.extents()` | ¶6 | 返回形状 |
| `m(i...)` | ¶7–¶10 | 偏移：非负，小于 `index_type` 最大值；对下标做 `static_cast<index_type>` 不改变结果 |
| `m.required_span_size()` | ¶11–¶12 | size 为 0 时为 0，否则是 `1 + max m(i...)` |
| `m.is_unique()` | ¶13–¶14 | 不同下标映射到不同偏移 |
| `m.is_exhaustive()` | ¶15–¶16 | `[0, required_span_size())` 中每个偏移都有下标映射到它 |
| `m.is_strided()` | ¶17–¶18 | 每一维都有固定步长 `sᵣ`：`m(i + dr) − m(i) == sᵣ` |
| `m.stride(r)` | ¶19–¶22 | 前置条件 `is_strided()`；返回 `sᵣ` |
| `M::is_always_unique()` 等三个 | ¶23–¶28 | 常量表达式；对该类型的**所有**对象都成立时才可以为 `true` |

几点值得咀嚼：

- **`required_span_size` 不是元素个数**，而是"底层存储至少要有多长"。对带间隔的 `layout_stride`，它大于 `size()`；对允许重叠的布局（非 unique），它可能小于 `size()`。
- 三个性质都是**单向保证**：¶14、¶16、¶18 都写"returns `true` *only if*…"，注 1、注 2、注 4 明确说"条件成立也可以返回 `false`"——有些布局要精确判断代价太高。泛型代码只能把 `true` 当作可以依赖的承诺，`false` 只意味着"不知道"。
- 这三个性质决定了能做哪些优化：**unique** 才能并行写入不冲突（多维 `copy` 的前置条件就要求目标 `is_unique()`）；**exhaustive** 才能把整块存储当作一维数组来 `memcpy`；**strided** 才能交给需要步长参数的 BLAS 接口。

!!! std
    `m.is_unique()`: `true` only if for every `i` and `j` where `(i != j || ...)` is `true`, `m(i...) != m(j...)` is `true`.
    只有当任意两个不同的多维下标都映射到不同偏移时，`is_unique()` 才可以返回 `true`。

### 映射策略的要求与五种标准策略（[mdspan.layout.policy.reqmts]、[mdspan.layout.policy.overview]）

**布局策略**（layout mapping policy）是一个"映射工厂"：`MP::mapping<E>` 对任意 `extents` 特化 `E` 都是满足上述要求的映射，且其 `layout_type` 指回 `MP`、`extents_type` 就是 `E`（[mdspan.layout.policy.reqmts] ¶1）。`mdspan` 的模板参数是**策略**而不是**映射**，正是为了让同一个布局能套在任何形状上。

[mdspan.layout.policy.overview] ¶1：五种标准策略本身以及两个 padded 模板的每个特化都是平凡可复制、平凡默认构造的空结构体。

| 策略 | 偏移公式（rank 2，下标 `(i, j)`，形状 `R × C`） | unique / exhaustive / strided | 存储 |
|---|---|---|---|
| `layout_right` | `i * C + j`（行主序，C 语言习惯） | 总是 / 总是 / 总是 | 仅 extents |
| `layout_left` | `i + j * R`（列主序，Fortran 习惯） | 总是 / 总是 / 总是 | 仅 extents |
| `layout_stride` | `i * s₀ + j * s₁` | 总是 / 视步长 / 总是 | extents + rank 个步长 |
| `layout_right_padded<P>` | `i * S + j`，`S >= C` 为行距 | 总是 / `S == C` 时 / 总是 | extents + 行距（静态时可不存） |
| `layout_left_padded<P>` | `i + j * S`，`S >= R` 为列距 | 总是 / `S == R` 时 / 总是 | extents + 列距（静态时可不存） |

### `layout_left` 与 `layout_right`（[mdspan.layout.left]、[mdspan.layout.right]）

两者完全对称，以 `layout_left` 为例：

- 概览 ¶1：最左一维步长为 1，向右逐维乘上 extent。¶2：`Extents` 不是 `extents` 的特化则程序 {{ill-formed}}。¶4 *Mandates*：全静态时，整个下标空间的 size 必须能用 `index_type` 表示——`extents<int8_t, 100, 100>` 的 `layout_left::mapping` 在编译期被拒。
- 构造函数（[mdspan.layout.left.cons]）：
    - ¶1–¶2：从 `extents` 构造，前置条件是 size 可表示；
    - ¶3–¶5：从另一个 `layout_left::mapping` 转换，`explicit` 与否跟随 `extents` 的转换；
    - ¶6–¶8：从 `layout_right::mapping` 转换，**仅当 rank ≤ 1**（¶6.1）——一维时行主序和列主序是同一个映射；
    - ¶9–¶12：从 `layout_left_padded` 转换，前置条件是那个 padded 映射恰好没有填充（`stride(1) == extent(0)`）；
    - ¶13–¶16：从 `layout_stride::mapping` 转换，前置条件是步长恰好等于列主序的步长；¶16 规定除 rank 0 外都是 `explicit`。
- 观察器（[mdspan.layout.left.obs]）：¶1 `required_span_size()` 是所有 extent 之积；¶4 偏移是 `Σ iᵣ * stride(r)`；¶7 `stride(i)` 是 *fwd-prod-of-extents*`(i)`；¶9 两个映射相等当且仅当 extents 相等。

```cpp run title="layout-mappings.cpp" ok
#include <array>
#include <cstdio>
#include <mdspan>

int main() {
  using E = std::extents<int, 2, 3>;
  std::layout_right::mapping<E> r(E{});
  std::layout_left::mapping<E>  l(E{});
  std::printf("right: m(1,1)=%d strides=%d,%d\n", r(1, 1), r.stride(0), r.stride(1));  // 4  3,1
  std::printf("left : m(1,1)=%d strides=%d,%d\n", l(1, 1), l.stride(0), l.stride(1));  // 3  1,2

  // 隔一个取一个：unique、strided，但不是 exhaustive
  std::layout_stride::mapping<std::extents<int, 3>> every_other(
      std::extents<int, 3>{}, std::array{2});
  std::printf("every_other: exhaustive=%d required_span_size=%d\n",
              int(every_other.is_exhaustive()), every_other.required_span_size());   // 0 5
}
```

```cpp run title="layout-conversions.cpp" ok
#include <mdspan>
#include <type_traits>

using E1 = std::extents<int, 4>;
using E2 = std::extents<int, 2, 3>;
// rank ≤ 1 时 left 与 right 是同一个映射，可以互转
static_assert(std::is_convertible_v<std::layout_right::mapping<E1>, std::layout_left::mapping<E1>>);
// rank 2 时不可互转（Constraints 不满足）
static_assert(!std::is_constructible_v<std::layout_left::mapping<E2>, std::layout_right::mapping<E2>>);
// left → stride：隐式；stride → left：可以构造但必须显式（需担保步长恰好是列主序）
static_assert(std::is_convertible_v<std::layout_left::mapping<E2>, std::layout_stride::mapping<E2>>);
static_assert(std::is_constructible_v<std::layout_left::mapping<E2>, std::layout_stride::mapping<E2>>);
static_assert(!std::is_convertible_v<std::layout_stride::mapping<E2>, std::layout_left::mapping<E2>>);

int main() {}
```

### `layout_stride`（[mdspan.layout.stride]）

步长由用户给定。几处规范细节：

- [mdspan.layout.stride.expo] ¶1 定义 *REQUIRED-SPAN-SIZE*`(e, strides)`：rank 0 时为 1，size 为 0 时为 0，否则为 `1 + Σ (extent(r) − 1) * stride(r)`。
- ¶4 定义仅用于说明的概念 *layout-mapping-alike*：检查一个类型有 `extents_type` 和三个返回 `bool` 的常量表达式 `is_always_*`。`layout_stride` 能从任何 *always unique* 且 *always strided* 的映射构造（[mdspan.layout.stride.cons] ¶6），包括用户自定义映射。
- [mdspan.layout.stride.cons] ¶4 的前置条件很强：每个步长 **> 0**（¶4.1），并且存在一个维度排列 `P`，使得 `s[pᵢ] >= s[pᵢ₋₁] * extent(pᵢ₋₁)`（¶4.3）。注 1 说这个条件对 `layout_stride` 而言**等价于 unique**。换言之：**`layout_stride` 不能表达重叠布局**，也不能表达步长为 0 的广播或负步长的反转——那些需要自定义映射。
- ¶7.4：从其他映射构造时还要求 *OFFSET*`(other) == 0`，即源映射把全零下标映射到偏移 0。
- [mdspan.layout.stride.obs] ¶5：`is_always_exhaustive()` 只在 rank 0 或某维静态 extent 为 0 时为 `true`；¶6：`is_exhaustive()` 在运行期检查步长是否恰好构成某个维度排列下的紧密排列。
- ¶7–¶9：`operator==` 可以与任意 *always strided* 映射比较：extents 相等、*OFFSET* 为 0、每维步长相等。

### `layout_left_padded` 与 `layout_right_padded` {{c++26}}（[mdspan.layout.leftpad]、[mdspan.layout.rightpad]）

带填充的布局（[[P2642R6]]）解决的是一个极其常见的需求：矩阵每行（或每列）末尾有对齐填充，比如为了让每行起点 64 字节对齐，或者矩阵本身是一个更大矩阵的子块。以 `layout_left_padded<PaddingValue>` 为例：

- 概览 ¶1：行为与 `layout_left` 相同，只是"填充步长" `stride(1)` 可以 **大于或等于** `extent(0)`。
- [mdspan.layout.leftpad.expo] ¶1：*static-padding-stride* 在 rank ≤ 1 时为 0；`PaddingValue` 或第 0 维是动态时为 `dynamic_extent`；否则为 *LEAST-MULTIPLE-AT-LEAST*`(padding_value, first-static-extent)`。¶2 的推荐实践：静态可知时**不要**存储这个值。
- 例：`layout_left_padded<4>::mapping<extents<int, 5, 3>>` 的列距是"不小于 5 的 4 的倍数"= 8；`stride` 依次为 1、8，`required_span_size()` 为 `(5−1)·1 + (3−1)·8 + 1 = 21`。
- [mdspan.layout.leftpad.cons]：从 `extents` 构造时按 `PaddingValue` 向上取整（¶1–¶2）；也可以运行期给出 `padding`（¶3–¶6），但若 `PaddingValue` 是静态的，运行期值必须与之相等（¶5.5）。
- [mdspan.layout.leftpad.obs] ¶6–¶7：只有填充步长恰好等于 `extent(0)` 时才 exhaustive。

`layout_right_padded` 镜像对称：填充的是 `stride(rank() − 2)`，即行距。

这两种布局还是 `submdspan` 的"布局保持"关键：从行主序矩阵切出一个子矩阵，结果最自然的表达就是 `layout_right_padded`（见下文）。

**libc++ 尚未实现这两种布局**，本节没有可运行示例。

## Accessor policy：从偏移到引用（[mdspan.accessor]）

### 概念（[mdspan.accessor.general]）

¶1：**访问器策略**（*accessor policy*，[[g:accessor-policy]]）定义了"由一个抽象的数据句柄和下标得到单个对象引用"的类型与操作。¶2 定义**可访问范围**（*accessible range*）：对每个 `i ∈ [0, N)`，访问函数都产生有效引用，则 `[0, N)` 是该句柄与访问器的可访问范围。`mdspan` 所有构造函数的前置条件都用这个概念表述。

¶3 的注 1 一句话打开了想象空间：**`data_handle_type` 不必可解引用**。它可以是 GPU 设备指针、远程内存句柄、压缩块的编号……

### 要求（[mdspan.accessor.reqmts]）

| 成员 | 段落 | 要求 |
|---|---|---|
| `element_type` | ¶2 | 完整对象类型，非抽象类 |
| `data_handle_type` | ¶3 | `copyable`，移动/交换不抛异常；注 1：不必是 `element_type*` |
| `reference` | ¶4 | 与 `element_type&` 有公共引用；注 2：不必是 `element_type&`（可以是代理，如 `atomic_ref<T>`） |
| `offset_policy` | ¶5 | 另一个访问器，可从 `A` 构造，元素类型相同 |
| `a.access(p, i)` | ¶6–¶8 | 返回 `reference`；保持相等性 |
| `a.offset(p, i)` | ¶9–¶11 | 返回 `offset_policy::data_handle_type` 的 `q`，使得 `b.access(q, j)` 与 `a.access(p, i + j)` 访问同一元素 |

`offset_policy` 是 `submdspan` 的关键：切片之后数据句柄要"往前挪"，而挪动之后原来的某些性质（比如对齐）可能不再成立，于是允许换一个访问器类型。¶8 的注 3 举了一个例子：一个"环形"访问器 `access(p, i)` 返回 `p[i % p.size()]`，就不需要任何下标前置条件。

### `default_accessor`（[mdspan.accessor.default]）

最朴素的实现：`data_handle_type` 是 `ElementType*`，`access(p, i)` 就是 `p[i]`（[mdspan.accessor.default.members] ¶2），`offset(p, i)` 就是 `p + i`（¶3）。

- 概览 ¶2：`ElementType` 不能是数组类型（`span<int[3]>` 可以，`mdspan<int[3], …>` 不行——多维的事交给 extents）。
- ¶4：`[0, n)` 是可访问范围当且仅当 `[p, p + n)` 是有效范围。
- [mdspan.accessor.default.members] ¶1：元素类型的转换构造同样只允许**限定转换**（`OtherElementType(*)[]` → `element_type(*)[]`），这就是 `mdspan<int>` → `mdspan<const int>` 能隐式转换、而 `mdspan<Derived>` → `mdspan<Base>` 不能的原因。

### `aligned_accessor` {{c++26}}（[mdspan.accessor.aligned]）

[[P2897R7]] 加入的访问器，向编译器**承诺**数据句柄按 `ByteAlignment` 字节对齐：

- 概览 ¶1 *Mandates*：`ByteAlignment` 是 2 的幂，且不小于 `alignof(ElementType)`。
- ¶5：可访问范围除了要求 `[p, p + n)` 有效，还要求 `n > 0` 时 `is_sufficiently_aligned<byte_alignment>(p)` 为真（[[ptr.align]]）。
- [mdspan.accessor.aligned.members] ¶6：`access(p, i)` 等价于 `assume_aligned<byte_alignment>(p)[i]`——对齐假设被直接喂给优化器，便于生成对齐的 SIMD 加载指令。
- `offset_policy` 是 **`default_accessor`**：`p + i` 之后一般不再对齐，所以切片结果自动退化为普通访问器。
- 转换方向（¶1–¶4、¶7–¶8）：`aligned_accessor` → `default_accessor` 是隐式的（丢掉承诺总是安全的）；`default_accessor` → `aligned_accessor` 是 **`explicit`** 的（凭空做出承诺必须显式）；对齐值大的可以隐式转成对齐值小的。

```cpp run title="aligned-accessor.cpp" ok
#include <cstdio>
#include <mdspan>
#include <memory>
#include <type_traits>

using Aligned = std::aligned_accessor<float, 16>;

float sum4(std::mdspan<float, std::extents<int, 4>, std::layout_right, Aligned> x) {
  return x[0] + x[1] + x[2] + x[3];       // access 内部是 assume_aligned<16>(p)[i]
}

int main() {
  alignas(16) float buf[8] = {1, 2, 3, 4, 5, 6, 7, 8};
  std::mdspan<float, std::extents<int, 4>> plain(buf);

  if (std::is_sufficiently_aligned<16>(plain.data_handle())) {
    // default_accessor → aligned_accessor 是 explicit 的：程序员必须亲自担保对齐
    std::mdspan<float, std::extents<int, 4>, std::layout_right, Aligned> a(
        plain.data_handle(), plain.mapping(), Aligned{});
    std::printf("%g\n", sum4(a));          // 10
  }
  static_assert(std::is_same_v<Aligned::offset_policy, std::default_accessor<float>>);
  static_assert(!std::is_convertible_v<std::default_accessor<float>, Aligned>);
  static_assert(std::is_convertible_v<Aligned, std::default_accessor<float>>);
}
```

如果 `buf` 实际上没有对齐却构造了 `aligned_accessor` 的 `mdspan`，违反的是构造函数"可访问范围"的前置条件，行为未定义——`assume_aligned` 的假设一旦为假，优化器生成的对齐加载指令可能直接崩溃。

## `mdspan` 本体（[mdspan.mdspan]）

### 概览（[mdspan.mdspan.overview]）

¶1："`mdspan` is a view of a multidimensional array of elements." 说明性成员只有三个：`acc_`、`map_`、`ptr_`。

¶2 *Mandates*：`ElementType` 是完整对象类型、非抽象、**非数组**；`Extents` 是 `extents` 的特化；`ElementType` 与 `AccessorPolicy::element_type` 相同。¶3：`LayoutPolicy` 和 `AccessorPolicy` 必须满足各自的要求（违反不要求诊断）。

¶4：每个特化建模 `copyable`，移动与交换不抛异常。¶5：当 accessor、mapping、数据句柄都平凡可复制时，`mdspan` 也平凡可复制。

推导指引（概要末尾）值得记住几条：

| 实参 | 推导结果 |
|---|---|
| `(CArray&)`，一维 C 数组 | `mdspan<T, extents<size_t, N>>`（静态） |
| `(Pointer&&)`，裸指针 | `mdspan<T, extents<size_t>>`（rank 0） |
| `(T*, Integrals...)` | `mdspan<T, extents<size_t, maybe-static-ext<Integrals>...>>` |
| `(T*, span<I, N>)` / `(T*, const array<I, N>&)` | `mdspan<T, dextents<size_t, N>>` |
| `(T*, const extents<I, E...>&)` | 原样保留 `extents` |
| `(T*, const Mapping&)` | 取 mapping 的 `extents_type` 和 `layout_type` |
| `(handle, const Mapping&, const Accessor&)` | 全部从参数推导 |

注意数组与指针的区别：`std::mdspan m(buf)` 中 `buf` 若是 `int[12]`，推导出 rank 1、extent 12；若是 `int*`，推导出 rank 0。

### 构造函数（[mdspan.mdspan.cons]）

所有构造函数共享一条前置条件："`[0, map_.required_span_size())` 是 `ptr_` 与 `acc_` 的可访问范围"——**`mdspan` 无从检查这一点**，传入的缓冲区太小就是 {{ub}}，加固模式也帮不上忙（见陷阱一节）。

- ¶1–¶3 默认构造：*Constraints* 要求 `rank_dynamic() > 0`。这条约束看似奇怪，其实是前置条件逼出来的：默认构造的 `ptr_` 是空指针，空指针上唯一的可访问范围是 `[0, 0)`，所以 `required_span_size()` 必须为 0；只有存在动态 extent（值初始化为 0）才能保证这一点。全静态 `extents<int, 3>` 的 `mdspan` 因此**没有默认构造函数**。
- ¶4–¶7：`(p, exts...)`，个数为 `rank()` 或 `rank_dynamic()`，总是 `explicit`。
- ¶8–¶10：`(p, span/array of extents)`，`N != rank_dynamic()` 时 `explicit`。
- ¶11–¶13：`(p, extents)`；¶14–¶16：`(p, mapping)`；¶17–¶18：`(p, mapping, accessor)`——最后一个是唯一能传入非默认访问器的途径。
- ¶19–¶24：从另一个 `mdspan` 转换。*Constraints* 看 mapping 和 accessor 能否构造；*Mandates* 看数据句柄和 extents 能否构造；¶22 的 *Hardened precondition* 检查每个静态维与源的实际长度一致；¶24 的 `explicit` 条件是"mapping 或 accessor 的转换是 explicit 的"。

```cpp run title="mdspan-ctad-conversions.cpp" ok
#include <array>
#include <mdspan>
#include <type_traits>
#include <utility>

int buf[12];
std::mdspan a(buf, std::cw<3uz>, std::cw<4uz>);       // 静态 extents
static_assert(std::is_same_v<decltype(a), std::mdspan<int, std::extents<std::size_t, 3, 4>>>);
std::mdspan b(buf, std::array{3, 4});                  // 运行期 extents
static_assert(std::is_same_v<decltype(b), std::mdspan<int, std::dims<2>>>);
std::mdspan c(buf);                                    // C 数组：rank 1，静态 extent 12
static_assert(std::is_same_v<decltype(c), std::mdspan<int, std::extents<std::size_t, 12>>>);
int* p = buf;
std::mdspan d(p);                                      // 裸指针：rank 0
static_assert(decltype(d)::rank() == 0);

std::mdspan<const int, std::dims<2>>          ro1 = a;  // OK：int → const int、静态 → 动态，隐式
std::mdspan<const int, std::dextents<int, 2>> ro2{a};   // OK：index_type 从 size_t 变窄到 int，必须显式

static_assert(!std::is_default_constructible_v<std::mdspan<int, std::extents<int, 3>>>);
static_assert(std::is_default_constructible_v<std::mdspan<int, std::dims<1>>>);
static_assert(std::is_trivially_copyable_v<std::mdspan<int, std::dims<2>>>);

int main() {}
```

`ro2` 那一行值得多看一眼：形状完全兼容、元素只是加 const，却因为 `extents<size_t, …>` → `extents<int, …>` 的值域变窄（[mdspan.extents.cons] ¶4 的后半），经由 `layout_right::mapping` 的 `explicit(!is_convertible_v<OtherExtents, extents_type>)` 一路传导到 `mdspan` 的 `explicit`。用 CTAD 从整数推导出来的是 `size_t` 下标，而手写的函数参数常常是 `int` 下标——这是 `mdspan` 用户最常遇到的"为什么不能隐式转换"。

### 多参数 `operator[]` 与 `at`（[mdspan.mdspan.members]）

¶1–¶4：`operator[](OtherIndexTypes... indices)`，个数必须等于 `rank()`。¶3 的 *Hardened precondition*：`I`（经 *index-cast* 后的下标）是 `extents()` 中的多维下标——即**每一维单独**在范围内。注 1 指出这蕴含 `map_(I) < required_span_size()`，反过来则不成立。

这个接口依赖 C++23 起 [[expr.sub]] 的语法变化：下标运算符的方括号里可以是逗号分隔的 *initializer-clause* 列表，交给重载的 `operator[]`（[[over.sub]]，[[P2128R6]]）。内建下标仍然只接受单个表达式（[[expr.sub]] ¶2）。C++20 先把下标里的逗号表达式 `a[i, j]` 标为弃用，C++23 再把这个语法让给多参数下标。

¶5–¶6：也可以传一个 `span` 或 `array` 作为下标，等价于展开后调用。

¶7–¶12：`at()` {{c++26}}：越界（不是多维下标）时抛 `out_of_range`。

¶13–¶14：`size()` 返回 `size_type`（无符号），前置条件是 size 能用 `size_type` 表示；¶15 `empty()`；¶16 `swap` 逐成员交换。

```cpp run title="mdspan-basics.cpp" ok
#include <cstdio>
#include <mdspan>
#include <stdexcept>
#include <type_traits>
#include <vector>

int main() {
  std::vector<double> buf(12);
  std::mdspan m(buf.data(), 3, 4);                 // CTAD：mdspan<double, dextents<size_t, 2>>
  static_assert(std::is_same_v<decltype(m),
                std::mdspan<double, std::dextents<std::size_t, 2>>>);

  for (std::size_t i = 0; i < m.extent(0); ++i)
    for (std::size_t j = 0; j < m.extent(1); ++j)
      m[i, j] = 10.0 * i + j;                       // C++23 多参数 operator[]

  std::printf("%g %g\n", m[2, 3], buf[2 * 4 + 3]);  // 23 23：layout_right 即行主序

  try {
    (void)m.at(3, 0);                               // C++26：越界抛 out_of_range
  } catch (const std::out_of_range&) {
    std::puts("at(3, 0) threw");
  }

  std::mdspan<double, std::extents<int, 3, 4>> fixed(buf.data());
  std::printf("sizeof: dyn=%zu static=%zu\n", sizeof(m), sizeof(fixed));  // libc++：24 8
}
```

```cpp run title="mdspan-subscript-errors.cpp" error
#include <mdspan>

int buf[12];
std::mdspan<int, std::dims<2>> m(buf, 3, 4);
int x = m[1][2];                                    // error: 没有单参数 operator[]，不能链式下标
int y = m[1, 2];                                    // OK
std::mdspan<int, std::extents<int, 3, 4>> s1 = m;   // error: 动态 → 静态必须显式
std::mdspan<int, std::extents<int, 3, 4>> s2{m};    // OK：¶22 的 Hardened precondition 检查 extent
```

### 同一块内存，不同的视图

`mdspan` 的威力在于：换一个 layout 就是换一种解读，数据一个字节都不动。

```cpp run title="mdspan-views.cpp" ok
#include <array>
#include <cstdio>
#include <mdspan>

int main() {
  int buf[6] = {0, 1, 2, 3, 4, 5};
  std::mdspan<int, std::extents<int, 2, 3>> a(buf);                     // 2×3，layout_right
  std::mdspan<int, std::extents<int, 3, 2>, std::layout_left> at(buf);  // 同一块内存看成 3×2 列主序
  for (int i = 0; i < 2; ++i)
    for (int j = 0; j < 3; ++j)
      if (a[i, j] != at[j, i]) return 1;                                // at 恰好是 a 的转置

  // 只看第 1 列：extent 2、stride 3，起点偏移 1
  using L = std::layout_stride::mapping<std::extents<int, 2>>;
  std::mdspan col(buf + 1, L(std::extents<int, 2>{}, std::array{3}));
  std::printf("%d %d exhaustive=%d\n", col[0], col[1], int(col.is_exhaustive()));  // 1 4 0
}
```

## `submdspan`：切片 {{c++26}}（[mdspan.sub]）

`submdspan(m, slices...)` 为每一维给一个**切片说明符**（slice specifier），返回一个看着原 `mdspan` 一部分元素的新 `mdspan`。它在 C++26 由 [[P2630R4]] 加入；当前草案的切片类型和辅助函数在那之后又经过了改写，下面按当前草案叙述。**libc++ 尚未实现本节任何设施。**

### 切片类型（[mdspan.sub.overview]）

¶2：对给定的 `IndexType`，一个类型 `S` 是**切片类型**，如果它是以下之一：

| 切片 | 含义 | 结果中这一维 |
|---|---|---|
| 可转换为 `full_extent_t`（即 `std::full_extent`） | 整维 | 保留，长度不变 |
| 可转换为 `IndexType` 的整数 | 固定这一维的下标 | **消失**（rank 减 1） |
| `extent_slice{offset, extent, stride}` | 从 `offset` 起取 `extent` 个，步长 `stride` | 保留，长度为 `extent` |
| `range_slice{first, last, stride}` | `[first, last)` 中按步长取 | 保留 |
| 可用结构化绑定拆成两个整数的类型（如 `pair{a, b}`、`tuple`） | `[a, b)` | 保留，长度 `b − a` |

¶5：**collapsing slice**（使维度消失的切片）是除 `full_extent_t` 与 `extent_slice` 以外的规范切片类型，即单个下标。¶6：**unit-stride slice** 是 `full_extent_t`，或步长为编译期常量 1 的 `extent_slice`。

¶3–¶4 定义了**规范**（canonical）形式：所有切片最终都被规范化为三种之一——`full_extent_t`、规范下标类型（`IndexType` 或 `constant_wrapper<v>`）、各字段都是规范下标类型的 `extent_slice`。¶7 定义每种规范切片在原维上覆盖的半开区间；¶8–¶9 定义"有效切片"：区间必须落在原维之内，步长在选取多于一个元素时必须为正。

!!! warning "`extent_slice` 的 `extent` 是选出的元素个数"
    [mdspan.sub.range.slices] ¶3 注 1：`extent_slice{.offset = 1, .extent = 4, .stride = 3}` 与 `range_slice{.first = 1, .last = 11, .stride = 3}` 都选出下标 1、4、7、10。注意 `extent_slice` 的 `extent` 是**结果的长度**（4），而不是原区间的长度；它的覆盖区间按 [mdspan.sub.overview] ¶7.3 计算为 `[offset, offset + 1 + (extent − 1) * stride)`。早期草案中字段相同的 `strided_slice` 里，`extent` 指的是原区间长度——从旧资料迁移时要特别小心。

### 规范化（[mdspan.sub.helpers]、[mdspan.sub.canonical]、[mdspan.sub.extents]）

- *canonical-index*（¶3–¶6）：整型常量包装变成 `cw<IndexType(v)>`，普通整数 `static_cast` 成 `IndexType`。**编译期常量信息被保留下来**，后面会决定结果 extent 是否静态。
- *canonical-range-slice*（¶7–¶10）：把"起点 + 跨度 + 步长"变成 `extent_slice`，元素个数为 `1 + (span − 1) / stride`；若跨度和步长都是编译期常量，元素个数也是编译期常量。
- *canonical-slice*（¶11–¶12）：按上面的表格把每种输入切片分派到对应的规范形式。`pair` 与 `range_slice` 都走 *canonical-range-slice*。
- `canonical_slices(src, slices...)`（[mdspan.sub.canonical] ¶1–¶4）：公开接口，返回规范化后的 `tuple`。
- `subextents(src, slices...)`（[mdspan.sub.extents]）：计算结果形状。¶5 规定结果的静态 extent：`full_extent` 保留原静态值；`extent_slice` 的 `extent` 是 `constant_wrapper` 时取其值；其余为动态。

!!! lawyer "草案里的一个名字不一致"
    [mdspan.sub.helpers] ¶7–¶10 定义的辅助函数叫 *canonical-range-slice*，而 ¶12 的 *canonical-slice* 在 `range_slice` 和 pair-like 分支里调用的是 *canonical-slice-range*。两者显然指同一个函数，这属于编辑性问题，不影响语义。

### 定制点：`submdspan_mapping`（[mdspan.sub.map]）

`submdspan` 本身不知道如何切任意布局——它把规范化后的切片交给 `submdspan_mapping(src.mapping(), slices...)`，**仅通过实参依赖查找（ADL）**找到这个函数（[mdspan.sub.map.sliceable] ¶2，[[basic.lookup.argdep]]）。标准布局都以隐藏友元（hidden friend）的形式提供它。返回值是 `submdspan_mapping_result{mapping, offset}`（[mdspan.sub.map.result]）。

[mdspan.sub.map.sliceable] ¶3–¶5 规定了**可切片映射**（sliceable layout mapping）的要求：对有效切片，结果映射的 extents 等于 `subextents(...)`，并且对结果中每个多维下标 `i`，`smr.mapping(i...) + smr.offset` 等于原映射在对应原下标处的值。¶3.2 还要求对非规范切片类型调用必须是 {{ill-formed}}——自定义布局不能偷偷接受未规范化的切片。

### 标准布局切片后得到什么布局（[mdspan.sub.map.left] 至 [mdspan.sub.map.rightpad]）

[mdspan.sub.map.common] ¶6 定义结果步长：原步长乘上 `extent_slice` 的步长；¶8 定义偏移：所有切片下界处的映射值（若某维下界等于该维 extent，即空切片，则取 `required_span_size()` 以避免越界求值）。

结果布局的选择规则（以 `layout_right` 为例，[mdspan.sub.map.right] ¶1）：

1. rank 0 原样返回；结果 rank 为 0 时返回 `layout_right`；
2. 若结果中**最后若干维都是 `full_extent`、再往前一维是 unit-stride**——仍然是 `layout_right`（行主序的"连续尾部"被保留）；
3. 否则，若最后一维是 unit-stride，并满足 ¶1.4 的条件——**`layout_right_padded`**，行距取自原映射；
4. 否则退化为 `layout_stride`。

`layout_left` 镜像对称；`layout_stride` 总是得到 `layout_stride`；padded 布局有自己的保持规则。这套规则的意义：**能证明连续的就保留连续布局**，从而保留 `is_always_exhaustive()` 等编译期性质，下游代码可以继续走快速路径。

### `submdspan` 函数（[mdspan.sub.sub]）

¶2：先 `canonical_slices` 规范化；¶3：再经 ADL 调用 `submdspan_mapping`；¶7 的效果：

```cpp
auto sub_map_result = submdspan_mapping(src.mapping(), slices...);
return mdspan(src.accessor().offset(src.data_handle(), sub_map_result.offset),
              sub_map_result.mapping,
              typename AccessorPolicy::offset_policy(src.accessor()));
```

注意最后一个实参：结果的访问器是原访问器的 `offset_policy`——对 `aligned_accessor`，切片之后就变回 `default_accessor`。¶6 的前置条件：每个切片都是对应维的有效切片（违反为 {{ub}}，不是加固前置条件）。

按当前草案，下面这段代码的结果类型如注释所示（libc++ 不支持，未在本地验证）：

```cpp
double buf[24];
std::mdspan m(buf, 4, 6);                                         // 4×6，layout_right，dims<2>

auto row = std::submdspan(m, 2, std::full_extent);                // rank 1，长度 6，layout_right
auto col = std::submdspan(m, std::full_extent, 3);                // rank 1，长度 4，layout_stride，步长 6
auto blk = std::submdspan(m, std::pair{1, 3}, std::pair{2, 5});   // 2×3，layout_right_padded<dynamic_extent>，行距 6
auto odd = std::submdspan(m, std::full_extent,
                          std::extent_slice{1, 3, 2});            // 4×3，列 1、3、5，layout_stride
```

`blk` 一行是 padded 布局存在的理由：子矩阵的每一行仍然连续，只是行与行之间隔着原矩阵的行宽。没有 `layout_right_padded`，它只能退化成 `layout_stride`，丢掉"行内连续"这一可供优化的编译期信息。

## 多维 `copy` 与 `fill` {{c++29}}（[mdspan.copy]）

当前草案在 `<mdspan>` 中加入了 `std::copy(src, dst)` 与 `std::fill(dst, value)` 的 `mdspan` 版本（特性测试宏 `__cpp_lib_mdspan_copy` 为 202606L，属于 C++26 之后的批次）：

- ¶1 *Constraints*：`Src` 与 `Dst` 都是 `mdspan` 特化；`Dst::reference` 可由 `Src::reference` 赋值；`Src::extents_type` 可由 `Dst::extents_type` 构造（注 1：即 rank 相同、每维静态值相同或有一方动态）。
- ¶2 *Preconditions*：`dst.is_unique()`；且 `src` 与 `dst` 的元素**不重叠**。
- ¶3 *Hardened preconditions*：`src.extents() == dst.extents()`。
- ¶4：逐元素赋值。没有规定遍历顺序——这正是要求目标唯一、源目标不重叠的原因，实现可以按两侧布局选择最优的遍历顺序甚至向量化。
- ¶5–¶6：`fill` 把 `value` 赋给每个元素。

它们与 `<algorithm>` 中的 `std::copy(first, last, out)`、`std::fill(first, last, value)` 参数个数不同，又都受 *Constraints* 限制，不会互相干扰。**libc++ 尚未实现。**

## 常见误区与陷阱

!!! pitfall "缓冲区太小：加固模式也救不了"
    构造 `mdspan` 时"`[0, required_span_size())` 是可访问范围"只是前置条件，没有任何实现能检查一个裸指针背后有多大。

```cpp run title="mdspan-too-small.cpp" ub
#include <mdspan>

int main() {
  int buf[6]{};
  std::mdspan m(buf, 3, 4);   // UB: 前置条件要求 [0, 12) 是 buf 的可访问范围
  return m[2, 3];             // 访问 buf[11]
}
```

ASan 报 stack-buffer-overflow；而 libc++ 的 debug 加固模式**不报错**——`(2, 3)` 确实是 `3×4` 形状中的合法多维下标。

!!! pitfall "物理不越界的逻辑越界"
    反过来，`m[0, 4]` 在 `3×4` 行主序的 `mdspan` 上算出的偏移是 4，落在缓冲区之内，ASan 看不出问题；但 `(0, 4)` 不是多维下标，违反 ¶3 的加固前置条件。libc++ 的 debug 模式会报 `mdspan: operator[] out of bounds access`，fast 模式以陷阱指令终止；非加固模式下它是静默的 {{ub}}。下标逐维检查而不是只检查最终偏移，正是这类 bug 的克星。

```cpp run title="mdspan-hardening.cpp" flags="-std=c++2c -D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_DEBUG"
#include <cstdio>
#include <mdspan>

int main() {
  int buf[12]{};
  std::mdspan<int, std::dims<2>> m(buf, 3, 4);
  std::printf("%d\n", m[0, 4]);   // 偏移 4 在 buf 之内，但 (0, 4) 不是多维下标：加固实现中终止
}
```

!!! pitfall "`m[i][j]` 与 `m[i, j]`"
    `mdspan` 没有返回"子视图"的单参数 `operator[]`（rank 1 时的 `m[i]` 直接返回元素引用），所以不能链式下标。另一方面，`a[i, j]` 这种写法对**自己写的**多维容器类要格外当心：C++20 中它被解析为逗号表达式 `a[(i, j)]`（已弃用），C++23 起才是两个实参的重载 `operator[]`——同一行代码在不同语言模式下意思完全不同。

!!! pitfall "以为 `layout_stride` 能表达广播或反转"
    [mdspan.layout.stride.cons] ¶4.1 要求每个步长 > 0，¶4.3 要求结果 unique。步长为 0 的广播（多个下标指向同一元素）和负步长的反转都需要自定义 layout mapping。

## 历史

| 版本 | 变化 |
|---|---|
| C++23 | `mdspan`、`extents`、`dextents`、`layout_left`/`right`/`stride`、`default_accessor`（[[P0009R18]]）；配套的多维下标运算符（[[P2128R6]]） |
| C++26 | `submdspan`（[[P2630R4]]）；`layout_left_padded`/`layout_right_padded`（[[P2642R6]]）；`aligned_accessor`（[[P2897R7]]）；`dims`；`mdspan::at`；经由整型常量包装推导静态 extent；`operator[]` 的下标检查与转换构造函数的 extent 检查成为 *Hardened preconditions* |
| C++26 之后的草案 | 切片类型改为 `extent_slice`/`range_slice`，规范化逻辑拆成 `canonical_slices`/`subextents`；多维 `copy`/`fill` |

## 思考题

!!! question "1. `layout_left::mapping<extents<int, 3, 4>>` 与 `layout_right::mapping<extents<int, 3, 4>>` 为什么不能互相转换，而 `extents<int, 4>` 的可以？若确实需要把行主序矩阵当作列主序来用，应该怎么做？"

<details markdown="1">
<summary>展开查看答案与解析</summary>

映射之间的转换必须保持"同一下标得到同一偏移"。rank ≤ 1 时两种布局的映射都是 `m(i) = i`，所以 [mdspan.layout.left.cons] ¶6.1 只在 `rank() <= 1` 时允许转换。rank 2 时 `(i, j)` 在两者下的偏移不同，转换后的 `mdspan` 会看到不同的元素，这不是"同一视图的另一种类型"，所以不提供。

若要把行主序的 `R × C` 矩阵当作列主序使用，正确的做法是**交换 extents** 构造一个新视图：`mdspan<T, extents<int, C, R>, layout_left>(ptr)`，它恰好是原矩阵的转置（见上文 `mdspan-views.cpp`）。

</details>

!!! question "2. 为什么 `mdspan<int, extents<int, 3>>` 不能默认构造，而 `mdspan<int, extents<int, 0>>` 也不能？"

<details markdown="1">
<summary>展开查看答案与解析</summary>

[mdspan.mdspan.cons] ¶1.1 的约束是 `rank_dynamic() > 0`，两者都是 0，所以都不能默认构造。对 `extents<int, 3>`，理由是 ¶2 的前置条件：空指针上 `[0, 3)` 不可能是可访问范围。对 `extents<int, 0>`，`required_span_size()` 是 0，前置条件其实能满足——约束写成 `rank_dynamic() > 0` 是一个保守而简单的近似，把"全静态"统一排除在外，而不是去区分某维是否恰好为 0。这是规范选择简单规则的一个例子：约束是编译期的，越简单越不容易在不同实现间产生分歧。

</details>

!!! question "3. 对一个 `aligned_accessor<float, 64>` 的 `mdspan` 做 `submdspan(m, std::full_extent)`，结果的访问器类型是什么？为什么标准不让它保持 `aligned_accessor`？"

<details markdown="1">
<summary>展开查看答案与解析</summary>

结果访问器是 `AccessorPolicy::offset_policy`（[mdspan.sub.sub] ¶7），而 `aligned_accessor` 的 `offset_policy` 是 `default_accessor<float>`（[mdspan.accessor.aligned.overview] 概要）。即使这个切片的偏移恰好是 0、结果仍然对齐，类型也无法在编译期知道这一点——一般的切片偏移是运行期值，`p + offset` 不再保证 64 字节对齐。若调用者能确认对齐，可以先用 `is_sufficiently_aligned<64>` 检查，再显式构造回 `aligned_accessor`，与上文 `aligned-accessor.cpp` 的做法相同。

</details>

## 小结

| 零件 | 职责 | 关键规则 |
|---|---|---|
| `extents` | 形状 | 只存动态 extent；`index_type` 变窄或动态 → 静态时转换为 `explicit`；rank 0 的 size 为 1 |
| layout mapping | 下标 → 偏移 | unique / exhaustive / strided 是单向保证；`required_span_size` ≠ `size` |
| `layout_left`/`right` | 列主序 / 行主序 | 只在 rank ≤ 1 时互转；从 `layout_stride` 构造是 `explicit` |
| `layout_stride` | 任意正步长 | 必须 unique；不能广播、不能反转 |
| padded 布局 | 带行距/列距的连续块 | `submdspan` 切子矩阵的自然结果；libc++ 未实现 |
| accessor | 偏移 → 引用 | `data_handle_type` 不必是指针；`offset_policy` 用于切片后换类型 |
| `aligned_accessor` | 对齐承诺 | 从 `default_accessor` 构造是 `explicit`；切片后退化为 `default_accessor` |
| `mdspan` | 组合三者 | 多参数 `operator[]` 逐维加固检查；缓冲区大小无法检查；全静态不可默认构造 |
| `submdspan` | 切片 | 先规范化，再经 ADL 调 `submdspan_mapping`；尽量保留连续布局；libc++ 未实现 |
