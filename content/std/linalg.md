---
title: 基本线性代数算法
summary: C++26 的 <linalg> 用 mdspan 表示向量和矩阵，提供 BLAS 1/2/3 级算法；转置、共轭、乘标量都通过不复制数据的视图表达；静态尺寸不匹配是编译错误，动态尺寸不匹配是 UB；浮点结果不保证与朴素循环逐位相同。
status: draft
covers: *
papers: P1673R13
related: views.multidim, mdspan.accessor.reqmts, mdspan.layout, algorithms.parallel, numerics.defns, complex.numbers, simd, numarray
tags: 标准库, linalg, BLAS, mdspan, C++26
updated: 2026-10-19
---

!!! tldr
    - `<linalg>` {{c++26}} 是 BLAS 的 C++ 接口：向量和矩阵是 `mdspan`，元素类型是模板参数，算法可以接受执行策略。
    - BLAS 里的 `trans`、`alpha` 参数变成了 `transposed(A)`、`scaled(alpha, x)` 这样的视图，它们只换布局或访问器，不复制数据。
    - 两个静态尺寸不匹配的矩阵相乘是编译错误（*Mandates*）；运行期尺寸不匹配是 UB（*Preconditions*）。
    - 输出参数不得与其他参数重叠，除非该函数明确允许别名（例如 `C = E + A·B` 中 C 可以就是 E）。
    - 对浮点类型，实现可以重排求和、使用 Strassen 之类的算法，结果不保证与朴素循环或其他实现逐位相同。

!!! warning "实现现状"
    本机 Clang 23 + libc++ 没有 `<linalg>` 头文件，`__cpp_lib_linalg` 在 libc++ 的 `<version>` 中是注释掉的。本页的例子按当前草案编写，没有经过编译验证，因此不带判定标记。

## 一个例子

```cpp title="linalg-views.cpp"
#include <linalg>
#include <mdspan>

namespace la = std::linalg;
using Mat = std::mdspan<double, std::dextents<int, 2>>;
using CMat = std::mdspan<const double, std::dextents<int, 2>>;

// C = 2·Aᵀ·B：不复制 A，也不需要 trans、alpha 参数
void f(CMat A, CMat B, Mat C) {
  la::matrix_product(la::scaled(2.0, la::transposed(A)), B, C);
}
```

传统 BLAS 的矩阵乘法是 `xGEMM(transA, transB, alpha, A, B, beta, C)`：转置和缩放都是额外的参数。`<linalg>`（[[P1673R13]]）把这些参数拿掉，改成对输入 `mdspan` 的变换。它的目标不是取代厂商优化过的 BLAS 库，而是提供一个类型安全的泛型前端：实现可以在 `double` 加常见布局时转发给厂商 BLAS，其他情况用通用代码。

`mdspan`（[[views.multidim]]）由三部分组成：extents（每一维的长度，可以是编译期常量，也可以是运行期值），布局映射（[[g:layout-mapping]]，把多维下标映射到一维偏移），访问器策略（[[g:accessor-policy]]，决定怎样由偏移取得元素）。

## 不复制数据的三种视图

### scaled（[linalg.scaled]）

`scaled(alpha, x)` 返回一个只读的 `mdspan`，访问第 i 个元素时得到 `alpha * x[i]`。它的实现是一个新的访问器 `scaled_accessor<ScalingFactor, NestedAccessor>`（[linalg.scaled.scaledaccessor]）：

- ¶6 `access(p, i)` 返回 `scaling_factor() * NestedAccessor::element_type(nested_accessor().access(p, i))`；
- `reference` 是乘积类型去掉 `const`，也就是按值返回，所以结果不可写；
- ¶2 *Mandates*：乘积类型有效、可复制构造且不是引用，`ScalingFactor` 建模 `semiregular`，`NestedAccessor` 满足访问器要求（[[mdspan.accessor.reqmts]]）。

乘法的顺序固定是 `alpha * x`。下文会看到，元素类型的乘法不一定可交换，所以这个顺序是有意义的。

### conjugated（[linalg.conj]）

`conjugated(a)` 返回元素取共轭的只读视图，用的访问器是 `conjugated_accessor`。[linalg.conj.conjugated] ¶1 规定返回值的访问器按下列顺序决定：

- ¶1.1 如果 `a` 的访问器已经是 `conjugated_accessor`，直接剥掉这一层，因为共轭两次等于原值；
- ¶1.2 否则，如果元素类型是算术类型（实数），原样使用 `a` 的访问器；
- ¶1.3 否则，如果对元素能找到可用的非限定 `conj`，包一层 `conjugated_accessor`；
- ¶1.4 否则原样使用。

### transposed（[linalg.transp]）

`transposed(a)`（*Mandates*：`a` 是二维的）交换两个 extent，并按 [linalg.transp.transposed] ¶3 选择返回的布局：

| 原布局 | 转置后的布局 |
|---|---|
| `layout_left` / `layout_right` | `layout_right` / `layout_left` |
| `layout_left_padded<P>` / `layout_right_padded<P>` | `layout_right_padded<P>` / `layout_left_padded<P>` |
| `layout_stride` | `layout_stride`（两个步长互换） |
| `layout_blas_packed<上三角, 列主序>` | `layout_blas_packed<下三角, 行主序>`（反之亦然） |
| `layout_transpose<L>` | `L` |
| 其他布局 `L` | `layout_transpose<L>` |

对常见布局，转置的结果仍然是常见布局，实现可以识别出来并转发给 BLAS。

`conjugate_transposed(a)`（[linalg.conjtransposed] ¶2）等价于 `conjugated(transposed(a))`。

## 阅读算法规范的约定（[linalg.general]）

¶1 *Effects* 写成"计算 R = E"时，E 按通常的数学含义理解，xᵀ 表示转置，xᴴ 表示共轭转置。R 如果是名字里带 `Out` 的形参，结果写进它的元素。

¶2–¶3 矩阵 A 的第 i 行是所有 A[i, k]，第 j 列是所有 A[k, j]。对角线是 A[i, i]；上三角是 i ≤ j 的元素，下三角是 i ≥ j 的元素，两者都包含对角线。

¶4 带三角标签参数 `t` 的函数，只访问 `t` 前一个参数 m 中 `t` 所指定的那个三角。访问三角之外的 m[i, j] 时：

- ¶4.1 名字以 `hermitian` 开头的函数用 *conj-if-needed*(m[j, i])；
- ¶4.2 以 `symmetric` 开头的用 m[j, i]；
- ¶4.3 以 `triangular` 开头的用加法单位元（零）。

`hermitian` 函数对对角元还要取实部。标准的例 1 指出，没被访问的那个三角里即使有非零值，也不算违反前置条件。

¶5 带对角标签参数 `d` 的函数，如果 `d` 指定隐式单位对角线，就不访问 m 的对角线，而是当作对角元都是乘法单位元，即使元素类型本身没有乘法单位元。

¶6 算法内部对 `abs`、`conj`、`imag`、`real` 的调用都是非限定的，所以会经由实参依赖查找找到用户类型的版本。

¶7–¶8 两个 `mdspan` 别名（alias），指它们的 extents 相同，且每个下标处引用同一个元素。两个 `mdspan` 重叠（overlap，[[g:mdspan-overlap]]），指存在某对下标引用同一个元素。别名是重叠的特例。

## 标签类型（[linalg.tags]）

六个空的标签类型，各配一个 `inline constexpr` 实例。它们的默认构造函数都是 `explicit` 的，防止 `{}` 意外地被当成一个标签：

| 标签 | 用途 |
|---|---|
| `column_major_t` / `row_major_t` | `layout_blas_packed` 的存储顺序 |
| `upper_triangle_t` / `lower_triangle_t` | 访问哪个三角 |
| `implicit_unit_diagonal_t` / `explicit_diagonal_t` | 是否访问对角线 |

[linalg.algs.reqs] ¶1 用形参的名字约束模板形参：名为 `ExecutionPolicy` 的必须是执行策略，带它的重载是并行算法（[[algorithms.parallel]]）；`Real` 必须能实例化 `complex<Real>`；`Triangle` 必须是两个三角标签之一；`DiagonalStorage` 必须是两个对角标签之一。

## 压缩存储 layout_blas_packed（[linalg.layout.packed]）

¶1–¶4 `layout_blas_packed<Triangle, StorageOrder>` 是一个 `mdspan` 布局映射策略。它表示一个只存储一个三角的方阵，元素紧密排列，对应 BLAS 的 SP、HP、TP 格式。`StorageOrder` 决定按列还是按行打包。一个 5×5 的压缩矩阵只存 15 个元素。

¶5 *Mandates*：两个模板实参分别是三角标签和顺序标签；`Extents` 是二维的；两个静态 extent 至少有一个是动态的，或者两者相等；全部静态时 N(N+1) 能用 `index_type` 表示。¶6 映射类型平凡可复制，并建模 `regular`。

这个映射不是唯一的：A[i, j] 和 A[j, i] 映射到同一个存储位置。所以 `is_always_unique()` 只在静态 extent 小于 2 时为真。这影响了它能用在哪里：普通输出参数要求 `is_always_unique()`，压缩矩阵只能作为 `symmetric_matrix_rank_1_update` 这类只写一个三角的函数的输出。

## 对元素类型的要求（[linalg.reqs]）

### 线性代数值类型（[linalg.reqs.val]）

¶1 输入输出 `mdspan` 的 `value_type`，以及模板形参 `Scalar`，称为线性代数值类型（[[g:linear-algebra-value-type]]）。¶2 它们必须建模说明用的概念 *scalar*：满足 `semiregular`，既不是 `mdspan` 也不是执行策略。¶3 值初始化的对象必须充当加法单位元。

### 算法可以怎样计算（[linalg.reqs.alg]）

¶2 用抽象代数的语言规定了实现能做什么：

- ¶2.1 函数可以创建任意多个线性代数值类型的对象，用值初始化或者从已有对象直接初始化。
- ¶2.2 三角求解算法（`trsv`、`trmm`、`trsm` 和原地 `trsm`）有一个 `divide` 参数，或者效果等价于有。`divide(a, b)` 解释为 a 乘以 b 的乘法逆元。它们只用 `*`、`*=`、`divide`、一元和二元 `+ -`、`+=`、`-=`、`=`，并且这个运算序列在乘法不可交换的域上也能得到规定的结果。
- ¶2.3 其余 BLAS 1/2/3 函数只用 `*`、`*=`、`+`、`+=`、`=`，运算序列在乘法不可交换的半环上也能得到规定的结果。
- ¶2.4 有输出 `mdspan` 时，所有加数等都必须能赋值给、并能转换为输出的 `value_type`。
- ¶2.5 函数可以任意重排加数和部分和。注 1 强调因子的顺序不会被重排，因为乘法不一定可交换。

¶2.2 和 ¶2.3 还把一些要求列为前置条件：所有加数、部分和、因子、保持因子顺序的部分积以及赋值都必须是良构表达式。

只要求半环意味着元素类型可以是矩阵块、四元数、区间数、自动微分用的对偶数，只要它们有满足结合律和分配律的 `+` 和 `*`。

¶3 注 3 对浮点类型大幅放宽：当所有 `value_type` 和 `Scalar` 都是浮点类型时，实现可以用任何能提高精度的方式求和，可以执行额外的运算来提高性能或精度，也可以使用近似算法，只要满足复杂度要求，并且是对数稳定的（引自 Demmel 2007）。注里明确把 Strassen 矩阵乘法列为允许的例子。

所以 `<linalg>` 的浮点结果不保证与朴素循环逐位相同，在不同实现、不同执行策略之间也不保证逐位相同。

## 辅助规则（[linalg.helpers]）

### 用户类型怎样接入 abs、conj

四个说明用的函数对象决定算法怎样对元素求绝对值、共轭、实部和虚部：

- *abs-if-needed*(E)：无符号整数直接返回 E；其他算术类型用 `std::abs(E)`；否则用非限定的 `abs(E)`，查找时屏蔽了 `std` 里的通用版本，实际上只靠实参依赖查找找到用户的函数。
- *conj-if-needed*、*real-if-needed*：非算术类型且能找到非限定版本时调用它，否则返回 E 本身。
- *imag-if-needed*：同上，找不到时返回 `T{}`，即实数的虚部为零。

每一条都附带一句：如果重载决议选中的函数返回的不是绝对值（或共轭、实部、虚部），程序非良构，不要求诊断（{{ifndr}}），编译器不必报错，程序也没有任何保证。这是用户类型接入 `<linalg>` 的约定：你提供的 `abs` 必须真的是绝对值。

### 参数概念（[linalg.helpers.concepts]）

¶1 算法签名使用一组说明用的概念：*in-vector*、*in-matrix*、*in-object* 分别是一维、二维、一或二维的 `mdspan`。对应的 *out-* 和 *inout-* 版本还要求能通过 `reference` 赋值，并且 `is_always_unique()` 为真。*possibly-packed-out-matrix* 放宽了唯一性，允许 `layout_blas_packed`。

¶2 通过 *in-* 参数的访问不会修改元素。

¶3 除非明确允许，任何 *out-* 或 *inout-* 参数都不得与函数的其他 `mdspan` 参数重叠。这是前置条件，违反就是 UB。允许的例外写在各函数的 *Remarks* 里，例如 `add` 的 z may alias x or y，`matrix_product(A, B, E, C)` 的 C may alias E。注意允许的是别名（完全相同的视图），不是任意重叠。

### 尺寸检查：静态用 Mandates，动态用 Preconditions

```cpp title="linalg-extents.cpp"
#include <linalg>
#include <mdspan>
using std::extents;

void f(std::mdspan<double, extents<int, 3, 4>> A,
       std::mdspan<double, extents<int, 5>> x,  // 应为 4
       std::mdspan<double, extents<int, 3>> y) {
  // error: possibly-multipliable 为 false
  std::linalg::matrix_vector_product(A, x, y);
}
```

[linalg.helpers.mandates] 定义了 *possibly-addable* 和 *possibly-multipliable*，它们只看静态 extent：任何一方是 `dynamic_extent` 就放过，两方都是静态值时必须相等。算法用它们写 *Mandates*，所以上例中 3×4 的矩阵乘长度为 5 的向量是编译错误。

[linalg.helpers.precond] 定义的 *addable* 和 *multipliable* 检查运行期的 extent，算法用它们写 *Preconditions*。所以动态尺寸不匹配是 UB。

## 算法一览

[linalg.algs.blas1.complexity] 规定 BLAS 1 函数的复杂度：`mdspan` 访问次数和算术运算次数，与所有 `mdspan` 参数中 extent 之积的最大值成线性关系。

| 级别 | 函数 | 对应 BLAS | 要点 |
|---|---|---|---|
| 1 | `setup_givens_rotation`、`apply_givens_rotation` | xLARTG、xROT | |
| 1 | `swap_elements` | xSWAP | |
| 1 | `scale(alpha, x)` | xSCAL | 原地 x = αx |
| 1 | `copy(x, y)` | xCOPY | |
| 1 | `add(x, y, z)` | xAXPY | z = x + y；αx + y 写作 `add(scaled(alpha, x), y, z)`；z 可以是 x 或 y 的别名 |
| 1 | `dot`、`dotc` | xDOT、xDOTU、xDOTC | `dotc(v1, v2)` 即 `dot(conjugated(v1), v2)` |
| 1 | `vector_two_norm` | xNRM2 | |
| 1 | `vector_abs_sum` | xASUM | |
| 1 | `vector_idx_abs_max` | IxAMAX | 空向量返回 `size_type` 的最大值 |
| 1 | `matrix_frob_norm`、`matrix_one_norm`、`matrix_inf_norm` | | 矩阵范数 |
| 2 | `matrix_vector_product` | xGEMV | y = Ax，或 z = y + Ax（z 可以是 y 的别名） |
| 2 | `symmetric_`、`hermitian_`、`triangular_matrix_vector_product` | xSYMV、xHEMV、xTRMV 等 | 只读指定的三角 |
| 2 | `triangular_matrix_vector_solve` | xTRSV、xTPSV | 解 Ax = b；无解时 x 的元素有效但值未指定 |
| 2 | `matrix_rank_1_update`、`matrix_rank_1_update_c` | xGER、xGERU、xGERC | A = xyᵀ，或 A = E + xyᵀ；`_c` 版本用 xyᴴ |
| 2 | `symmetric_`、`hermitian_matrix_rank_1_update`，`…_rank_2_update` | xSYR、xHER、xSYR2、xHER2 | 输出可以是压缩布局 |
| 3 | `matrix_product` | xGEMM | C = AB，或 C = E + AB（C 可以是 E 的别名） |
| 3 | `symmetric_`、`hermitian_`、`triangular_matrix_product` | xSYMM、xHEMM、xTRMM | |
| 3 | `triangular_matrix_left_product`、`…_right_product` | xTRMM | 原地 |
| 3 | `symmetric_`、`hermitian_matrix_rank_k_update`，`…_rank_2k_update` | xSYRK、xHERK、xSYR2K、xHER2K | |
| 3 | `triangular_matrix_matrix_left_solve`、`…_right_solve` | xTRSM | 有非原地和原地两种版本 |

更新类函数在当前草案中都分覆盖和更新两种重载。例如 `matrix_rank_1_update(x, y, A)` 计算 A = xyᵀ，`matrix_rank_1_update(x, y, E, A)` 计算 A = E + xyᵀ，A 可以是 E 的别名。BLAS 中 rank-1 update 总是 A += xyᵀ，`<linalg>` 的措辞与此不同。

### dot 的结果类型（[linalg.algs.blas1.dot]）

不给初值时（¶9），结果类型是两个元素类型乘积的类型，从 `T{}` 开始累加。给了初值 `init` 时（¶5–¶6），结果类型就是 `init` 的类型。¶7 *Remarks* 还规定：如果元素类型和 `Scalar` 都是浮点类型或 `complex`，并且 `Scalar` 的精度更高，那么求和的中间项至少按 `Scalar` 的精度计算。

所以 `dot(v1, v2, 0.0L)` 是用 `long double` 累加 `float` 向量点积的标准写法。`vector_two_norm` 的 `init` 有同样的作用。

## 与 valarray、simd 的关系

[[numarray]] 的 `valarray` 也受 BLAS 启发，`slice` 就是 BLAS 式的跨步访问。但它把数据和运算绑在同一个类型里；`<linalg>` 只提供算法，数据由 `mdspan` 借来，存储方式与算法无关。

[[simd]] 是更底层的工具，`<linalg>` 的实现可以在内部用它做向量化。
