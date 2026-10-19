---
title: 数据并行类型 std::simd
summary: C++26 的 <simd> 提供 vec 和 mask 两种值类型，用一个对象表示一组同时运算的元素；标量到向量的隐式广播只接受保值转换；下标按值返回；逐元素运算沿用核心语言的 UB；加载和存储分 unchecked 与 partial 两套；浮点归约的结合顺序未指定。
status: draft
covers: *
papers: P1928R15
related: numerics, linalg, c.math, bit, complex.numbers, const.wrap.class, conv.rank, expr.pre, numerics.defns
tags: 标准库, simd, 向量化, C++26
updated: 2026-10-19
---

!!! tldr
    - `std::simd::vec<float>` 是一组 `float`，元素个数（宽度）在编译期确定，通常等于一个向量寄存器能装下的个数；`a + b` 对每个元素做加法。
    - 标量只有在转换保值时才能隐式广播：`vec<float>` 乘 `2.0f` 可以，乘 `2` 或 `2.0` 都编译不过。
    - `v[i]` 按值返回，不能对单个元素赋值；`a < b` 返回 `mask`，不能直接放进 `if`，要写 `all_of` 或 `any_of`。
    - 逐元素运算对每个元素求值对应的标量表达式，所以整数除以零、有符号溢出仍然是 UB。
    - 默认宽度随编译选项变化；跨翻译单元传递时应该写明宽度，如 `vec<float, 8>`。

!!! warning "实现现状"
    本机 Clang 23 + libc++ 没有 `<simd>` 头文件。本页的例子按当前草案编写，没有经过编译验证，因此不带判定标记。已有的 TS 版本 `<experimental/simd>` 名字和接口都不同，不能直接对照。

## 一个例子

```cpp title="simd-saxpy.cpp"
#include <cstddef>
#include <simd>
#include <span>
namespace ss = std::simd;

// y = a·x + y
void saxpy(float a, std::span<const float> x,
           std::span<float> y) {
  using V = ss::vec<float>;
  std::size_t i = 0;
  for (; i + V::size() <= x.size(); i += V::size()) {
    V vx = ss::unchecked_load<V>(x.subspan(i, V::size()));
    V vy = ss::unchecked_load<V>(y.subspan(i, V::size()));
    ss::unchecked_store(a * vx + vy, y.subspan(i, V::size()));
  }
  // 尾部不足一个向量：缺的元素读成 0，只写回剩下的元素
  V vx = ss::partial_load<V>(x.subspan(i));
  V vy = ss::partial_load<V>(y.subspan(i));
  ss::partial_store(a * vx + vy, y.subspan(i));
}
```

SIMD（单指令多数据）指一条指令同时处理多个数据。依靠编译器自动向量化时，循环能否向量化取决于优化器能否证明这样做安全；`std::simd` 把"这里按向量处理"写进了类型。`a * vx + vy` 中每个运算都是逐元素的，编译器把它翻译成向量指令。

这个库源自并行技术规范第 2 版中的 `std::experimental::simd`，由 [[P1928R15]] 并入 C++26 {{c++26}}。之后在 C++26 周期内，类型改名为 `basic_vec`、`vec`、`basic_mask`、`mask`，放进命名空间 `std::simd`，并加入了复数元素、permute、gather/scatter 等功能。

## 基本概念（[simd.general]）

¶2 可向量化类型（[[g:vectorizable-type]]）包括：全部标准整数类型、字符类型、`float` 和 `double`；实现定义了的 `std::float16_t`、`float32_t`、`float64_t`；以及元素为可向量化浮点类型的 `complex<T>`。`bool` 和 `long double` 都不是可向量化类型（`bool` 不属于标准整数类型）。

¶3–¶5 `basic_vec` 和 `basic_mask` 的特化分为启用的和禁用的，启用的特化统称数据并行类型（[[g:data-parallel-type]]）。数据并行类型由若干个元素组成，元素的类型称为元素类型，个数称为宽度，下标从 0 到宽度 − 1。

¶6 逐元素运算对一个或多个数据并行对象的元素逐个施加某个运算，各次施加彼此无序（unsequenced）。

¶7 对一个掩码 `mask`，使 `mask[i]` 为真的那些 i 称为被选下标，对应的元素称为被选元素。

¶8 从算术类型 U 到可向量化类型 T 的转换，如果 U 的所有值都能用 T 表示，就称为保值转换（[[g:value-preserving-conversion]]）。

¶9 程序显式特化或部分特化 [simd] 中的任何模板，非良构，不要求诊断（{{ifndr}}）。

## 宽度与 ABI 标签（[simd.expos.abi]）

¶1 ABI 标签（[[g:simd-abi-tag]]）是一个类型，表示数据并行对象的大小和二进制表示。它和元素类型一起决定宽度。¶2 注 2 指出，ABI 标签与所选的指令集是两回事，它的作用是让数据并行对象能安全地跨翻译单元传递（函数调用、I/O）。

两个说明用的别名决定了常用的 ABI 标签：

- ¶4–¶5 *deduce-abi-t*<T, N>：T 可向量化，且 0 < N ≤ 某个实现定义的上限（不小于 64）时，它是使宽度恰好为 N 的 ABI 标签。
- ¶6 *native-abi*<T>：实现定义的、对当前目标最高效的标签。注 3 说明，在有指令集扩展的目标上，编译选项可以改变它。

所以 `vec<float>`（默认用 *native-abi*）的大小和布局可能随编译选项变化。例如在 x86-64 上，开启 AVX 时它可能有 8 个元素，否则可能是 4 个。用不同 `-m` 选项编译的两个翻译单元交换 `vec<float>`，容易造成两边对类型布局的理解不一致；跨边界时应使用显式宽度，如 `vec<float, 8>`。

## 主要的名字（[simd.syn]）

```cpp
template<class T, class Abi = native-abi<T>> class basic_vec;
template<class T, simd-size-type N = simd-size-v<T, native-abi<T>>>
  using vec = basic_vec<T, deduce-abi-t<T, N>>;
template<size_t Bytes, class Abi> class basic_mask;
template<class T, simd-size-type N = simd-size-v<T, native-abi<T>>>
  using mask = vec<T, N>::mask_type;
```

*simd-size-type* 是一个有符号整数类型，宽度和下标都用它表示（[simd.expos.defn]）。

`basic_mask` 按元素的字节数而不是元素类型参数化：宽度相同的 `vec<float>` 和 `vec<int>` 共用同一个掩码类型，所以比较 `float` 得到的掩码可以直接用来选择 `int` 元素。

命名空间 `std` 用 using 声明引入了 `std::simd` 中的 `min`、`max`、`minmax`、`clamp` 和数学函数，所以 `std::sin(v)` 也能用。

[simd.traits] 提供 `alignment<T, U>::value`（用 `flag_aligned` 加载存储时需要的对齐）、`rebind_t<T, V>`（换元素类型、保持宽度）和 `resize_t<N, V>`（换宽度、保持元素类型）。

## basic_vec（[simd.class]）

### 启用与禁用（[simd.overview]）

¶1 `basic_vec<T, Abi>` 在 T 可向量化、且 Abi 是某个 N ∈ [1, 64] 的 *deduce-abi-t*<T, N> 时启用；T 不可向量化时禁用；其余情况是否启用由实现定义。

禁用的特化删除了默认构造函数、析构函数、复制构造函数和复制赋值，只有 `value_type`、`abi_type`、`mask_type` 三个成员，所以用它声明变量是编译错误。

启用的特化（¶1.4–¶1.8）是平凡可复制的；默认初始化会默认初始化每个元素（对 `int` 就是不确定值），值初始化会值初始化每个元素。

`size` 是一个 `static constexpr integral_constant` 数据成员，不是成员函数。`integral_constant` 有 `operator()`，所以 `V::size()` 照样能写，结果是常量表达式。

### 广播构造：只接受保值转换（[simd.ctor] ¶1–¶3）

```cpp title="simd-broadcast.cpp"
#include <simd>
namespace ss = std::simd;

void f(ss::vec<float> v) {
  auto a = v * 2.0f;        // OK: float → float 保值
  auto b = v * std::cw<2>;  // OK: 编译期常量 2 能用 float 表示
  auto c = v * 2;           // error: int → float 不保值
  auto d = v * 2.0;         // error: double → float 不保值
}
```

广播构造函数 `template<class U> constexpr basic_vec(U&& value) noexcept` 把一个标量复制到每个元素。它不是 `explicit` 的，所以 `v * 2.0f` 中的 `2.0f` 能隐式转换为 `vec<float>`。但 ¶2 的约束很严，下面三条满足其一才行，其中 From 是 `remove_cvref_t<U>`：

- ¶2.1 U 能转换为 `value_type`，且 From 既不是算术类型，也不满足 *constexpr-wrapper-like*；
- ¶2.2 From 是算术类型，且 From 到 `value_type` 是保值转换；
- ¶2.3 From 满足 *constexpr-wrapper-like*（例如 `std::cw<2>`，见 [[const.wrap.class]]），它的值是算术类型，并且这个值能用 `value_type` 表示。

`int` 到 `float` 不是保值转换，因为不是每个 `int` 都能用 `float` 精确表示，所以 `v * 2` 不能编译。在标量代码里，`x * 2` 悄悄把 `int` 转成 `float` 通常无伤大雅；在 SIMD 代码里，隐式的整数转浮点或者宽转窄常常意味着精度损失或额外的转换指令，`std::simd` 要求把它们写出来。

### 其他构造函数

- 转换构造（¶4–¶6）：从宽度相同的另一个 `basic_vec` 逐元素 `static_cast`。如果转换不保值，或者是整数降秩、浮点降秩（[[conv.rank]]），这个构造函数是 `explicit` 的。
- 生成器构造（¶7–¶10）：第 i 个元素初始化为 `gen(integral_constant<simd-size-type, i>())`。下标作为编译期常量传入，生成器里可以用 `if constexpr`。¶10 规定 `gen` 对每个 i 恰好调用一次，按 i 递增的顺序。
- 范围构造（¶11–¶15）：要求 `r` 是连续且有大小的范围，`ranges::size(r)` 是常量表达式且等于 `size()`。所以只能用 `std::array`、`span<T, N>` 这类大小静态已知的范围。¶16–¶17 的推导指引让 `basic_vec(std::array<float, 8>{…})` 推导为 `vec<float, 8>`。
- 复数构造（¶20–¶21）：元素是 `complex` 时，可以由实部向量和虚部向量构造。

### 下标按值返回（[simd.subscr]）

¶1–¶3 `value_type operator[](simd-size-type i) const` 的前置条件是 0 ≤ i < `size()`，返回第 i 个元素的值。它返回值而不是引用，也没有非 const 版本，所以 `v[0] = 1.0f;` 不能编译。

寄存器里的单个元素没有地址，按引用返回会迫使实现把整个向量放在内存里。要修改单个元素，可以用 `select`、生成器构造或者掩码操作。

¶4 `operator[](const I& indices)`（`I` 是整数 `vec`）等价于 `permute(*this, indices)`。

### 迭代器（[simd.iterator]）

`begin()` 返回说明用的 *simd-iterator*，`end()` 返回 `default_sentinel`。迭代器的 `operator*` 按值返回。它的 `iterator_concept` 是 `random_access_iterator_tag`，`iterator_category` 却是 `input_iterator_tag`，因为 C++17 风格的前向迭代器要求 `*it` 返回引用。它可以用于范围 `for` 和只读算法。

## 逐元素运算（[simd.unary]、[simd.nonmembers]）

一元运算（`++`、`--`、`!`、`~`、`+`、`-`）、二元运算（`+ - * / % & | ^ << >>`）、复合赋值和比较运算都遵循同一个模式：

- *Constraints*：对应的标量表达式合法，例如二元运算要求 `requires (value_type a, value_type b) { a op b; }`；
- 结果是对每个元素施加这个运算；比较运算返回 `mask_type`，`!` 也返回 `mask_type`。

二元运算是 `noexcept` 的隐藏友元，参数是 `const basic_vec&`，只能经由实参依赖查找找到。正因为参数是 `basic_vec` 本身，标量操作数要经过上面的广播构造函数转换。移位另有 `v << n` 形式的重载（n 是 *simd-size-type* 标量），所有元素移相同的位数。

!!! lawyer "逐元素运算继承核心语言的 UB"
    [simd.binary] ¶3 说结果"用对 lhs 和 rhs 逐元素施加 op 的结果初始化"，也就是对每个元素求值标量表达式 `a op b`。于是核心语言的规则逐个元素适用：`vec<int>` 的某个元素除以零、有符号溢出、移位量不小于位宽，都是 UB（[[expr.pre#4]]、[[expr.mul]]、[[expr.shift]]），即使硬件的向量指令对这些情况有确定的行为。

    反过来，`vec<std::int8_t>` 的 `a + b` 没有 UB：标量表达式先经整型提升按 `int` 计算，再用结果初始化 `int8_t` 元素，这个转换按模 2⁸ 定义（[[conv.integral]]）。

### select

[simd.alg] ¶9–¶10 的 `select(c, a, b)` 是 SIMD 版的条件运算符：

- `c` 是 `bool` 时，等价于 `c ? a : b`；
- `c` 是掩码时，结果的第 i 个元素是 `c[i] ? a[i] : b[i]`，实现方式是调用说明用的 *simd-select-impl*（[simd.cond]）。¶10 特意规定它通过实参依赖查找找到，并注明这与 [[contents]] 的一般规则相反。

## 加载与存储（[simd.loadstore]、[simd.flags]）

在内存和向量之间搬运数据有两套函数：

| | 范围比 `V::size()` 短时 |
|---|---|
| `unchecked_load` / `unchecked_store` | ¶3 前置条件要求 `ranges::size(r) ≥ V::size()`，不足就是 UB；如果长度是常量表达式，¶2 改为 *Mandates*，不足是编译错误 |
| `partial_load` / `partial_store` | 只读写前 `ranges::size(r)` 个元素；加载时其余元素为 `T()`，存储时其余位置不写 |

两者都有带掩码的重载（只处理被选元素），也都接受范围、迭代器加个数、迭代器加哨兵三种形式。开头例子的主循环用 `unchecked_*`，因为长度已知足够；尾部不足一个向量的部分用 `partial_*`，代价是多一些比较。

[simd.flags] 的 `flags<…>` 是一组类型级的选项，用 `|` 组合：

- `flag_default`：没有额外假设；
- `flag_convert`：允许不保值的元素类型转换，例如从 `double` 数组加载到 `vec<float>`。没有它时，不保值的转换违反 *Mandates*；
- `flag_aligned`：断言指针按 `alignment_v<V, U>` 对齐，这是前置条件，不对齐是 UB；
- `flag_overaligned<N>`：断言按 N 对齐，N 必须是 2 的幂。

[simd.permute.memory] 的 gather/scatter 按一个下标向量访问内存：`unchecked_gather_from(r, indices)` 和 `partial_gather_from` 从范围中收集元素，`unchecked_scatter_to` 和 `partial_scatter_to` 分散写回。`partial_*` 版本对越界下标对应的元素既不读也不写。

## 归约（[simd.reductions]、[simd.mask.reductions]）

`reduce(x, op = plus<>{})` 把所有元素归约成一个值：

- ¶1 `op` 必须建模 *reduction-binary-operation*：能对 `vec<T, 1>` 调用，并且（[simd.expos.defn] ¶8）是可交换的逐元素运算；
- ¶3 结果是 *GENERALIZED_SUM*（[[numerics.defns]]，[[g:generalized-sum]]），元素以未指定的方式结合。所以浮点归约的结果不保证与顺序累加相同，在不同实现、不同宽度之间也不保证相同。

带掩码的 `reduce(x, mask, op, identity)` 只归约被选元素，没有被选元素时返回 `identity`。¶5 `op` 是 `plus<>`、`multiplies<>` 或位运算时 `identity` 有默认值，其他运算必须显式给出。`reduce_min`、`reduce_max` 要求 `T` 建模 `totally_ordered`。

掩码的归约有 `all_of`、`any_of`、`none_of`、`reduce_count`，以及 `reduce_min_index`、`reduce_max_index`（返回最小、最大的为真下标）。后两者的前置条件是 `any_of(k)`，全为假时调用是 UB。

这些函数都有接受 `bool` 或标量的重载，同一段泛型代码对标量和向量都能工作。

## 重排、组合与数学函数

- 静态 permute（[simd.permute.static]）：`permute(v, idxmap)`，`idxmap(i)` 必须是常量表达式，给出第 i 个结果元素取自哪个源元素，也可以返回 `zero_element`（置零）或 `uninit_element`（值未指定）。结果宽度可以与源不同。
- 动态 permute（[simd.permute.dynamic]）：`permute(v, indices)`，下标是运行期的整数向量。
- compress / expand（[simd.permute.mask]）：把被选元素紧凑地移到前面，或者反过来展开，对应 AVX-512 中的同名指令。
- chunk / cat（[simd.creation]）：把宽向量切成几段较窄的向量，或者把几个向量拼起来。
- `iota<V>`：元素依次为 0, 1, 2, … 的常量。

[simd.math] 为浮点 `vec` 提供了几乎所有 `<cmath>` 函数（[[c.math]]）的重载，返回类型用 *deduced-vec-t* 推导，所以可以混用 `vec` 和能隐式转换为它的类型。[simd.bit] 为无符号整数 `vec` 提供 `<bit>`（[[bit]]）中的 `popcount`、`countl_zero`、`rotl`、`byteswap` 等。[simd.complex.math] 为复数元素提供 `real`、`imag`、`abs`、`arg`、`norm`、`conj`、`proj`、`polar` 和超越函数。

## basic_mask（[simd.mask.class]）

```cpp title="simd-mask.cpp"
#include <simd>
namespace ss = std::simd;

bool all_less(ss::vec<float> a, ss::vec<float> b) {
  // if (a < b) ...           // error: mask 不能转换为 bool
  return ss::all_of(a < b);   // 或者 any_of(a < b)
}
```

`a < b` 返回一组比较结果。把它转换成一个 `bool` 有全部为真和任一为真两种合理含义，标准不替你选，所以 `basic_mask` 没有到 `bool` 的转换。

- 启用规则（[simd.mask.overview] ¶1）与 `basic_vec` 类似，但按字节数：只有存在某个可向量化类型的 `sizeof` 等于 Bytes 时才可能启用。启用的特化平凡可复制。
- 构造（[simd.mask.ctor]）：从 `bool` 广播（`explicit`，实参必须恰好是 `bool`）；从宽度相同的另一个掩码显式转换；生成器构造（生成器必须返回 `bool`）；从 `bitset<size()>` 构造；从无符号整数显式构造（按位取前 M 个元素，其余为假）。
- 下标同样按值返回 `bool`。
- 一元运算（[simd.mask.unary]）：`!` 返回掩码。`+`、`-`、`~` 对每个元素的 `bool` 值施加运算，返回元素类型为 *integer-from*<Bytes>（大小为 Bytes 的有符号整数）的 `vec`，例如 `-m` 中为真的元素是 −1。如果没有这样大小的可向量化有符号整数类型，这三个运算符被删除。
- 转换（[simd.mask.conv]）：可以转换为宽度相同的 `basic_vec<U, A>`（`sizeof(U)` 不等于 Bytes 时是 `explicit` 的），也有 `to_bitset()` 和 `to_ullong()`。`to_ullong()` 的前置条件是超出 `unsigned long long` 位数的那些元素都为假。
- 二元 `&&`、`||`、`&`、`|`、`^` 及其复合赋值都是逐元素的。`&&` 和 `||` 也不短路，因为两个操作数在调用前都已经求值。六个比较运算符同样逐元素进行，返回掩码。
