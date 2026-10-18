---
title: 基本线性代数算法
summary: C++26 <linalg>——以 mdspan 为参数的 BLAS 1/2/3 算法：标签类型、layout_blas_packed、scaled/conjugated/transposed 这三个"不复制数据"的视图变换（新的访问器与布局）、按形参名与仅用于说明的概念施加的约束、静态 extent 用 Mandates 动态 extent 用 Preconditions 的分工、输出不得重叠、"半环/域上的运算序列"对元素类型的要求与对浮点实现的放宽；各算法族一览；libc++ 尚未实现
status: draft
covers: *
papers: P1673R13
related: views.multidim, mdspan.accessor.reqmts, mdspan.layout, algorithms.parallel, numerics.defns, complex.numbers, simd, numarray
tags: 标准库, linalg, BLAS, mdspan, C++26
updated: 2026-10-18
---

`<linalg>` {{c++26}} 由 [[P1673R13]] 引入，它把数值计算中使用了四十多年的 BLAS（Basic Linear Algebra Subprograms）接口翻译成 C++：向量与矩阵用 `mdspan`（[[views.multidim]]）表示，元素类型是模板参数，可以接受执行策略。它的目标不是取代优化过的 BLAS 库，而是给它们一个类型安全、泛型的前端——实现可以在 `double` + `layout_left` 时转发给厂商 BLAS，在其他情况下用通用代码。

!!! warning "实现现状"
    本机 Clang 23 + libc++ **没有 `<linalg>` 头文件**（libc++ 的 `<version>` 中 `__cpp_lib_linalg` 是注释掉的）。本页的例子按标准编写，**没有**在本机编译验证。

读本页需要先了解 `mdspan` 的三件套：extents、layout mapping（[[g:layout-mapping]]）、accessor policy（[[g:accessor-policy]]）。`<linalg>` 的一大设计特点就是用**新的布局和访问器**表达"转置""共轭""乘以标量"，而不是给每个算法加 `trans`、`alpha` 参数。

## 总述与约定（[linalg.overview]、[linalg.general]）

[linalg.overview] ¶1：本子条款定义基本线性代数算法；访问数组元素的算法通过 `mdspan` 查看元素。

[linalg.general] 建立阅读后面所有 *Effects* 的约定：

- ¶1："计算 R = E" 中 E 取通常的数学含义；xᵀ 是转置，xᴴ 是共轭转置；R 若是名字含 `Out` 的形参，结果写入它的元素。
- ¶2：矩阵 A 的第 i **行**是所有 A[i, k₁]，第 j **列**是所有 A[k₀, j]。
- ¶3：**对角线**是 A[i, i]（0 ≤ i < min(extent(0), extent(1))）；**上三角**是 i ≤ j 的元素，**下三角**是 i ≥ j 的元素，都包含对角线。
- ¶4：对接受参数 `t`（三角标签）的函数，`t` 作用于它前一个参数 m：函数**只访问** m 中 `t` 指定的那个三角。对三角之外的 m[i, j]，名字以 `hermitian` 开头的函数用 *conj-if-needed*(m[j, i])，以 `symmetric` 开头的用 m[j, i]，以 `triangular` 开头的用加法单位元（零）；`hermitian` 函数对对角元用 *real-if-needed*(m[i, i])。标准例子说明：未被访问的那个三角里即使有非零值，也不算违反前置条件。
- ¶5：对接受参数 `d`（对角标签）的函数，若 `d` 指定"隐式单位对角线"，函数不访问 m 的对角线，按对角线全为（双边）乘法单位元解释——即使元素类型本身没有乘法单位元。
- ¶6：所有对 `abs`、`conj`、`imag`、`real` 的调用都是**非限定**的（因此会经过 ADL 找到用户类型的版本）。
- ¶7–¶8：两个 `mdspan` **别名**（alias），指它们 extents 相同且每个下标处引用同一元素；**重叠**（overlap，[[g:mdspan-overlap]]），指存在某对下标引用同一元素。别名是重叠的特例。

## 对元素类型的要求（[linalg.reqs]）

### 线性代数值类型（[linalg.reqs.val]）

¶1–¶3：输入输出 `mdspan` 的 `value_type` 与 `Scalar` 模板形参称为**线性代数值类型**（[[g:linear-algebra-value-type]]）；它们必须建模仅用于说明的概念 *scalar*（`semiregular`、不是 `mdspan`、不是执行策略）；**值初始化的对象必须充当加法单位元**。

### 算法可以怎样计算（[linalg.reqs.alg]）

¶2 是理解 `<linalg>` 语义的关键，它用抽象代数的语言规定实现**允许**做什么：

- ¶2.1：函数可以创建任意多个线性代数值类型的对象，值初始化或用已有对象直接初始化。
- ¶2.2：**三角求解算法**（`trsv`、`trmm`、`trsm`、原地 `trsm`）有一个 `BinaryDivideOp divide` 参数（或等价于有），`divide(a, b)` 解释为 a 乘以 b 的乘法逆元。它们使用 `*`、`*=`、`divide`、一元/二元 `+ -`、`+=`、`-=`、`=` 的一个求值序列，这个序列**在乘法不交换的域上**能产生 *Effects* 规定的结果。前置条件：所有加数、减数、部分和、因子、部分积（保持因子顺序）、分子、分母、赋值都是良构表达式。
- ¶2.3：其余 BLAS 1/2/3 函数使用 `*`、`*=`、`+`、`+=`、`=` 的求值序列，这个序列**在乘法不交换的半环上**能产生规定的结果。
- ¶2.4：有输出 `mdspan` 时，所有加数等必须可赋值、可转换为输出的 `value_type`。
- ¶2.5：函数可以任意重排加数与部分和；注释：**因子不会被重排**——乘法不一定可交换。

"半环、乘法不交换"意味着元素类型可以是矩阵块、四元数、区间、自动微分的对偶数……只要它们有 `+`、`*` 且满足结合律、分配律。

¶3 的注释对浮点类型做了大幅放宽：当所有 `value_type` 与 `Scalar` 都是浮点类型时，实现可以以提高精度的任意方式计算浮点和，可以执行额外的算术运算来提高性能或精度，可以使用近似（即使用实数计算也不精确的方法），只要满足复杂度要求且是"对数稳定"的（引用 Demmel 2007）——注释明确把 Strassen 矩阵乘法列为允许的例子。

这意味着：**`<linalg>` 的浮点结果不保证与朴素循环逐位相同**，也不保证在不同实现、不同执行策略之间逐位相同。

## 标签类（[linalg.tags]）

六个空的标签类型，各有一个 `inline constexpr` 实例，默认构造函数都是 `explicit` 的（防止用 `{}` 意外构造出一个标签）：

| 标签 | 用途 |
|---|---|
| `column_major_t` / `row_major_t` | `layout_blas_packed` 的存储顺序 |
| `upper_triangle_t` / `lower_triangle_t` | 指定访问哪个三角 |
| `implicit_unit_diagonal_t` / `explicit_diagonal_t` | 是否访问对角线 |

[linalg.algs.reqs] ¶1 用**形参名**约束未受约束的模板形参：`ExecutionPolicy` 必须是执行策略（这样的函数是并行算法，见 [[algorithms.parallel]]）；`Real` 必须是能实例化 `complex<Real>` 的类型；`Triangle` 必须是两个三角标签之一；`DiagonalStorage` 必须是两个对角标签之一。

## 压缩存储布局 layout_blas_packed（[linalg.layout.packed]）

¶1–¶4：`layout_blas_packed<Triangle, StorageOrder>` 是一个 `mdspan` 布局映射策略，表示**只存一个三角**的方阵，以连续压缩格式存放（对应 BLAS 的 SP、HP、TP 格式）。`StorageOrder` 决定按列还是按行打包。

¶5 *Mandates*：`Triangle`、`StorageOrder` 是相应标签；`Extents` 是 rank 2 的 `extents`；两个静态 extent 要么有一个是动态的，要么相等（方阵）；全静态时 N(N+1) 必须能用 `index_type` 表示。¶6：映射类型平凡可复制并建模 `regular`。

这个映射的一个特点是**不唯一**（not unique）：A[i, j] 与 A[j, i] 映射到同一个存储位置（只存了一半）。所以 `is_always_unique()` 只在 extent 小于 2 时为真。这直接影响算法的可用性：输出参数的概念 *out-matrix* 要求 `is_always_unique()`，于是压缩矩阵只能用作 `symmetric_matrix_rank_1_update` 等接受 *possibly-packed-out-matrix* 的函数的输出——这些函数只写一个三角。

## 三个原地视图变换

这是 `<linalg>` 最有特色的设计：BLAS 的 `xGEMM(transA, transB, alpha, A, B, beta, C)` 中的 `trans`、`alpha` 参数，在这里变成了**对输入 `mdspan` 的视图变换**，它们不复制数据，只换布局或访问器：

### scaled（[linalg.scaled]）

`scaled(alpha, x)` 返回一个只读 `mdspan`，访问元素时返回 `alpha * x[i...]`。实现方式是新的访问器 `scaled_accessor<ScalingFactor, NestedAccessor>`（[linalg.scaled.scaledaccessor]）：

- `element_type` 是 `const decltype(declval<ScalingFactor>() * declval<NestedAccessor::element_type>())`，`reference` 是去掉 const 的同一类型——**按值返回**，所以结果不可写；
- `access(p, i)` 返回 `scaling_factor() * NestedAccessor::element_type(nested_accessor().access(p, i))`；
- ¶2 *Mandates*：`element_type` 有效、`reference` 可复制构造、不是引用类型、`ScalingFactor` 建模 `semiregular`、`NestedAccessor` 满足访问器要求（[[mdspan.accessor.reqmts]]）。

注意乘法的顺序是 `alpha * x`——对乘法不交换的类型这很重要。

### conjugated（[linalg.conj]）

`conjugated(a)` 返回元素为共轭的只读视图，访问器 `conjugated_accessor`。[linalg.conj.conjugated] ¶1–¶2 有三个优化：

- 若 `a` 的访问器已经是 `conjugated_accessor`，直接剥掉一层（共轭两次等于原值）；
- 若元素类型是算术类型（实数），**原样返回 `a`**；
- 若元素类型有可用的非限定 `conj`（在包含 `template<class U> U conj(const U&) = delete;` 的语境中查找），才包一层 `conjugated_accessor`；否则也原样返回。

### transposed（[linalg.transp]）

`transposed(a)`（*Mandates*：rank 为 2）返回转置视图：extents 互换，布局按 [linalg.transp.transposed] ¶3 映射——`layout_left` ↔ `layout_right`、`layout_left_padded` ↔ `layout_right_padded`、`layout_stride` 保持（步长互换）、`layout_blas_packed<上, 列主>` ↔ `<下, 行主>`、`layout_transpose<L>` 剥回 `L`，其余情况包一层新的布局 `layout_transpose<Layout>`。也就是说，对常见布局，转置的结果仍是常见布局，后端可以识别并转发给 BLAS。

`conjugate_transposed(a)`（[linalg.conjtransposed]）等价于 `conjugated(transposed(a))`。

```cpp title="linalg-views.cpp" ok
#include <linalg>
#include <mdspan>
#include <vector>

namespace la = std::linalg;

void gemm_like(std::mdspan<const double, std::dextents<int, 2>> A,
               std::mdspan<const double, std::dextents<int, 2>> B,
               std::mdspan<double, std::dextents<int, 2>> C) {
  // C = 2·Aᵀ·B：既不复制 A，也不需要 trans/alpha 参数
  la::matrix_product(la::scaled(2.0, la::transposed(A)), B, C);
}

// 注：本机 libc++ 无 <linalg>，未编译验证
```

## 辅助规则（[linalg.helpers]）

### *abs-if-needed* 等（¶1 of each）

四个仅用于说明的函数对象决定了算法如何对元素调用 `abs`、`conj`、`real`、`imag`：

- *abs-if-needed*(E)：无符号整数直接返回 E；算术类型用 `std::abs(E)`；否则用非限定 `abs(E)`（在有 `template<class U> U abs(U) = delete;` 的语境中查找，即只经 ADL）；
- *conj-if-needed*、*real-if-needed*：非算术类型且有可用的非限定版本时调用，否则返回 E 本身；
- *imag-if-needed*：同上，否则返回 `T{}`（实数的虚部为零）。

每个都附带一句：若重载决议选中的函数**不返回**绝对值/共轭/实部/虚部，程序非良构，**不要求诊断**（{{ifndr}}）。这是用户类型接入 `<linalg>` 的合同：你的 `abs` 必须真的是绝对值。

### 参数概念（[linalg.helpers.concepts]）

算法签名使用仅用于说明的概念：*in-vector*/*in-matrix*/*in-object*（rank 为 1/2/1或2 的 `mdspan`）；*out-*/*inout-* 版本还要求 `reference` 可从 `element_type` 赋值且 `is_always_unique()`；*possibly-packed-out-matrix* 放宽唯一性以允许 `layout_blas_packed`。

¶2：通过 *in-* 参数的访问不修改元素。¶3：除非明确允许，任何 *out-*/*inout-* 参数**不得与其他 `mdspan` 参数重叠**——这是前置条件，违反是 UB。允许的例外在各函数的 *Remarks* 里，例如 `add` 的 "z may alias x or y"、`matrix_product(A, B, E, C)` 的 "C may alias E"。注意是**别名**（完全相同的视图）而不是任意重叠。

### 静态检查与动态检查的分工（[linalg.helpers.mandates]、[linalg.helpers.precond]）

*possibly-addable*、*possibly-multipliable* 检查**静态** extent：只要有一方是 `dynamic_extent` 就放过，两方都是静态值时必须相等。算法用它们写 *Mandates*，于是两个静态尺寸不匹配的矩阵相乘是**编译错误**。

*addable*、*multipliable* 检查**运行期** extent，算法用它们写 *Preconditions*。所以动态尺寸不匹配是 UB。

```cpp title="linalg-extents.cpp" error
#include <linalg>
#include <mdspan>

void f(std::mdspan<double, std::extents<int, 3, 4>> A,
       std::mdspan<double, std::extents<int, 5>> x,       // 应为 4
       std::mdspan<double, std::extents<int, 3>> y) {
  std::linalg::matrix_vector_product(A, x, y);   // error：possibly-multipliable 为 false（Mandates）
}
```

## 算法族一览

[linalg.algs.blas1] 的复杂度统一为：mdspan 访问次数与算术运算次数与"所有 mdspan 参数中 extent 之积的最大值"成线性关系。

| BLAS 级别 | 函数 | 对应 BLAS | 要点 |
|---|---|---|---|
| 1 | `setup_givens_rotation`、`apply_givens_rotation` | xLARTG、xROT | 返回 c、s、r；c 是实数，c² + \|s\|² = 1 |
| 1 | `swap_elements` | xSWAP | |
| 1 | `scale(alpha, x)` | xSCAL | 原地 x = αx |
| 1 | `copy(x, y)` | xCOPY | rank 必须相同（*Constraints*） |
| 1 | `add(x, y, z)` | xAXPY | z = x + y；αx + y 写作 `add(scaled(alpha, x), y, z)`；z 可与 x 或 y 别名 |
| 1 | `dot`、`dotc` | xDOT、xDOTU、xDOTC | 可给初值 `init` 决定结果类型；`dotc` = `dot(conjugated(v1), v2)` |
| 1 | `vector_two_norm` | xNRM2 | 返回 √(\|init\|² + Σ\|vᵢ\|²) |
| 1 | `vector_abs_sum` | xASUM | |
| 1 | `vector_idx_abs_max` | IxAMAX | 空向量返回 `size_type` 最大值；复数按 \|re\| + \|im\| 比较 |
| 1 | `matrix_frob_norm`、`matrix_one_norm`、`matrix_inf_norm` | — | BLAS 标准中有、参考实现中无 |
| 2 | `matrix_vector_product` | xGEMV | y = Ax，或 z = y + Ax（z 可与 y 别名） |
| 2 | `symmetric_/hermitian_/triangular_matrix_vector_product` | xSYMV、xHEMV、xTRMV 等 | 只读指定三角 |
| 2 | `triangular_matrix_vector_solve` | xTRSV、xTPSV | 解 Ax = b；无解时 x 的元素有效但未指明 |
| 2 | `matrix_rank_1_update[_c]` | xGER、xGERU、xGERC | A = xyᵀ 或 A = E + xyᵀ |
| 2 | `symmetric_/hermitian_matrix_rank_1_update`、`…_rank_2_update` | xSYR、xHER、xSYR2、xHER2 | 输出可以是压缩布局 |
| 3 | `matrix_product` | xGEMM | C = AB，或 C = E + AB（C 可与 E 别名） |
| 3 | `symmetric_/hermitian_/triangular_matrix_product` 等 | xSYMM、xHEMM、xTRMM | |
| 3 | `triangular_matrix_left_product`、`…_right_product` | xTRMM | 原地 |
| 3 | `symmetric_/hermitian_matrix_rank_k_update`、`…_rank_2k_update` | xSYRK、xHERK、xSYR2K、xHER2K | |
| 3 | `triangular_matrix_matrix_left_solve`、`…_right_solve` | xTRSM | 有非原地与原地版本 |

`dot` 的结果类型规则值得一提（[linalg.algs.blas1.dot] ¶5–¶9）：不给 `init` 时结果类型是 `decltype(v1[i] * v2[i])`，从 `T{}` 开始累加；给了 `init` 时结果类型就是 `init` 的类型，而 ¶7 的 *Remarks* 规定：若 `Scalar` 精度高于元素类型（都是浮点或 `complex`），中间项按 `Scalar` 的精度或更高计算。于是 `dot(v1, v2, 0.0L)` 是"用 `long double` 累加 `float` 向量的点积"的标准写法。`vector_two_norm` 的 `init` 有同样的作用。

注意 `<linalg>` 的"更新"函数在当前草案中都分为**覆盖**与**更新**两种重载：例如 `matrix_rank_1_update(x, y, A)` 计算 A = xyᵀ（覆盖），`matrix_rank_1_update(x, y, E, A)` 计算 A = E + xyᵀ（A 可与 E 别名）。旧资料中"rank-1 update 总是 A += xyᵀ"的说法与当前措辞不符。

## 与 valarray、simd 的关系

- [[numarray]] 的 `valarray` 也以 BLAS 为灵感（`slice` 就是 BLAS 风格的跨步），但它把"数组"和"运算"绑在一个类型里；`<linalg>` 只是算法，数据由 `mdspan` 借来，与存储解耦。
- [[simd]] 是更底层的工具：`<linalg>` 的实现可以在内部用 `std::simd` 向量化，用户代码也可以把 `simd` 当作元素类型——只要它满足 *scalar* 概念和半环运算。

## 小结

| 方面 | 规则 |
|---|---|
| 数据表示 | `mdspan`；转置、共轭、缩放通过新布局/访问器表达，不复制 |
| 元素类型 | *scalar* 概念；值初始化即零；运算在（不交换的）半环/域上有意义 |
| 浮点 | 允许重排、额外运算、近似（对数稳定即可）——结果不逐位可复现 |
| 尺寸检查 | 静态 extent：*Mandates*；动态 extent：*Preconditions* |
| 输出 | 不得与其他参数重叠，*Remarks* 明确允许的别名除外 |
| `abs`/`conj` 等 | 非限定调用；用户版本语义不对则 IFNDR |
| 实现 | libc++ 尚无 `<linalg>` |
