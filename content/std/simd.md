---
title: 数据并行类型 std::simd
summary: C++26 <simd>——basic_vec/basic_mask 与别名 vec/mask：可向量化类型、宽度与 ABI 标签、启用/禁用的特化；广播构造的"保值转换"约束（v * 2 为何不能编译）、生成器构造、按值的 operator[]；逐元素运算沿用核心语言的 UB；加载/存储的 unchecked/partial 两套接口与对齐标志；归约、掩码归约、select、permute/compress/expand、gather/scatter、chunk/cat；数学与位运算重载；libc++ 尚未提供
status: draft
covers: *
papers: P1928R15
related: numerics, linalg, c.math, bit, complex.numbers, const.wrap.class, conv.rank, expr.pre, numerics.defns
tags: 标准库, simd, 向量化, C++26
updated: 2026-10-18
---

`std::simd` {{c++26}} 把"一条指令同时处理多个数据"的 SIMD 编程模型做成一个可移植的值类型。它源自并行技术规范第 2 版（Parallelism TS 2）中的 `std::experimental::simd`，由 [[P1928R15]] 并入标准，之后在 C++26 周期内又经历了改名（`simd` → `basic_vec`/`vec`，`simd_mask` → `basic_mask`/`mask`，命名空间 `std::simd`）和扩充（复数元素、permute、gather/scatter 等）。

!!! warning "实现现状"
    本机 Clang 23 + libc++ **没有 `<simd>` 头文件**。本页的例子按当前草案编写，**没有**在本机编译验证；已有的 TS 版本 `<experimental/simd>` 使用不同的名字与接口，不能直接对照。

核心思路：`vec<float>` 是"一组 float"，长度（**宽度**）在编译期确定、通常等于目标机器一个向量寄存器能装下的元素个数。`a + b` 对每个元素做加法，编译器把它翻译成一条向量指令。与依赖自动向量化相比，它把"这里要向量化"写进了类型系统。

## 基本概念（[simd.general]）

- ¶1：本子条款定义数据并行类型及其运算。注释：意图是支持 SIMD 寄存器与指令等数据并行执行资源。
- ¶2 **可向量化类型**（[[g:vectorizable-type]]）：全部标准整数类型、字符类型、`float`、`double`；若定义了的 `std::float16_t`、`float32_t`、`float64_t`；以及 `complex<T>`（`T` 为可向量化浮点类型）。注意 **`bool` 不是**可向量化类型（它是整型但不是"标准整数类型"），`long double` 也不是。
- ¶3 **数据并行类型**（[[g:data-parallel-type]]）：`basic_vec` 与 `basic_mask` 的所有**启用的**特化。
- ¶4–¶5：每个特化要么启用要么禁用；数据并行类型由若干个**元素类型**的元素组成，元素个数称为**宽度**，下标从 0 到宽度 − 1。
- ¶6 **逐元素运算**：对一个或多个数据并行对象的元素逐个施加运算，**各次应用彼此无序**（unsequenced）。
- ¶7：对掩码 `mask`，**被选下标**是 `mask[i]` 为真的那些 i，**被选元素**是对应的 `data[i]`。
- ¶8 **保值转换**（[[g:value-preserving-conversion]]）：从算术类型 U 到可向量化类型 T 的转换，若 U 的所有值都能用 T 表示，称为保值的。
- ¶9：程序对 [simd] 中任何模板声明显式或部分特化，{{ifndr}}。

## ABI 标签与宽度（[simd.expos]）

[simd.expos.abi]：**ABI 标签**（[[g:simd-abi-tag]]）是表示数据并行对象大小与二进制表示的类型；它与元素类型一起决定宽度。注释强调：ABI 标签与所选指令集**正交**——它的作用是让数据并行对象能安全地跨 TU 传递（函数调用、I/O）。

- *deduce-abi-t*<T, N>：当 T 可向量化、0 < N ≤ 实现定义的上限（**至少 64**）时，是一个使宽度为 N 的 ABI 标签；
- *native-abi*<T>：实现定义的、对当前目标最高效的标签。注释：带 ISA 扩展的目标上，编译选项可以改变它——例如 `-mavx2` 下 `vec<float>` 可能有 8 个元素，否则 4 个。

这意味着 **`vec<float>` 的大小和布局可能随编译选项变化**。用不同 `-m` 选项编译的两个 TU 交换 `vec<float>` 是 ODR 问题的温床；跨边界时应使用显式宽度 `vec<float, 8>`。

[simd.expos.defn] 定义了 *simd-size-type*（有符号整数类型，宽度、下标都用它）、*integer-from*<Bytes>（大小为 Bytes 的有符号整数）、*deduced-vec-t*<T>（`decltype(x + x)`，用于数学函数的返回类型推导）等说明用的实体。

## 头文件（[simd.syn]）

主要名字都在 `std::simd` 中：

```cpp
template<class T, class Abi = native-abi<T>> class basic_vec;
template<class T, simd-size-type N = simd-size-v<T, native-abi<T>>>
  using vec = basic_vec<T, deduce-abi-t<T, N>>;
template<size_t Bytes, class Abi> class basic_mask;
template<class T, simd-size-type N = simd-size-v<T, native-abi<T>>>
  using mask = vec<T, N>::mask_type;
```

注意 `basic_mask` 按**元素字节数**而不是元素类型参数化：`vec<float>` 与 `vec<int>`（宽度相同时）共享同一个掩码类型，这样比较 `float` 得到的掩码可以直接用来选择 `int` 元素。

此外，`std` 命名空间通过 using 声明引入了 `min`、`max`、`clamp` 以及数学函数（`std::sin(vec)` 也能工作）。

[simd.traits]：`alignment<T, U>::value` 给出用 `flag_aligned` 加载/存储时所需的对齐；`rebind_t<T, V>` 换元素类型保持宽度；`resize_t<N, V>` 换宽度保持元素类型。

## basic_vec（[simd.class]）

### 启用与禁用（[simd.overview] ¶1）

`basic_vec<T, Abi>` 在 T 可向量化、且 Abi 是某个 N ∈ [1, 64] 的 *deduce-abi-t*<T, N> 时**启用**；T 不可向量化时**禁用**；其余情况由实现定义。禁用的特化：默认构造、析构、复制构造、复制赋值都被删除，只有 `value_type`、`abi_type`、`mask_type` 成员——用它声明变量就是编译错误。

启用的特化：¶1.4 **平凡可复制**；¶1.5 默认初始化即默认初始化所有元素（对 `int` 等就是不确定值）；¶1.6 值初始化即值初始化所有元素；`size()` 等于掩码的 `size()`。

`size` 是一个 `static constexpr integral_constant` **数据成员**，而不是函数——但 `integral_constant` 有 `operator()`，所以 `v.size()` 照样能写，且结果是常量表达式。

### 构造（[simd.ctor]）

**广播构造** `template<class U> constexpr basic_vec(U&& value) noexcept`（¶1–¶3）把一个标量复制到所有元素。它**不是** `explicit` 的，但约束很严（¶2）——满足其一即可：

- ¶2.1 U 可转换为 `value_type`，且 From（`remove_cvref_t<U>`）**不是**算术类型、也不满足 *constexpr-wrapper-like*；
- ¶2.2 From 是算术类型，且 From → `value_type` 是**保值转换**；
- ¶2.3 From 满足 *constexpr-wrapper-like*（如 `std::cw<2>`，见 [[const.wrap.class]]），其值是算术类型，且**这个值**能被 `value_type` 表示。

后果是：

```cpp title="simd-broadcast.cpp" error
#include <simd>
namespace ss = std::simd;

void f(ss::vec<float> v) {
  auto a = v * 2.0f;        // OK：float → float 保值
  auto b = v * std::cw<2>;  // OK：编译期常量 2 可由 float 表示（¶2.3）
  auto c = v * 2;           // error：int → float 不是保值转换（并非所有 int 都能用 float 表示）
  auto d = v * 2.0;         // error：double → float 不保值
}
// 注：本机 libc++ 无 <simd>，未编译验证
```

这是刻意的设计：在标量代码里 `x * 2` 悄悄把 `int` 转成 `float` 无伤大雅；在 SIMD 代码里，隐式的宽转窄或整数转浮点经常意味着精度损失或意料之外的指令。`std::simd` 让它们一律需要显式写出。

**转换构造** `basic_vec(const basic_vec<U, UAbi>&)`（¶4–¶6）：宽度必须相同；逐元素 `static_cast`；在不保值、或整数降秩、或浮点降秩（[[conv.rank]]）时是 `explicit` 的。

**生成器构造** `explicit basic_vec(G&& gen)`（¶7–¶10）：第 i 个元素初始化为 `gen(integral_constant<simd-size-type, i>())`——下标作为**编译期常量**传入，所以生成器里可以用 `if constexpr`。¶10：`gen` 对每个 i 恰好调用一次，按 i 递增的顺序。

**范围构造** `basic_vec(R&& r, flags<…> = {})`（¶11–¶15）：要求 `r` 是连续、有大小的范围，且 `ranges::size(r)` 是常量表达式并**等于** `size()`——所以只能用 `std::array`、`span<T, N>` 这类静态大小的范围。还有带掩码的版本和类模板实参推导指引（¶16–¶17）：`basic_vec(std::array<float, 8>{…})` 推导为 `vec<float, 8>`。

**复数构造**（¶20–¶21）：元素是 `complex` 时，可以从实部向量和虚部向量构造。

### 下标：按值返回（[simd.subscr]）

¶1–¶3：`value_type operator[](simd-size-type i) const`，*Preconditions*：0 ≤ i < `size()`。**返回值而不是引用**，也没有非 const 版本——`v[0] = 1.0f;` 不能编译。SIMD 寄存器中的单个元素没有地址，按引用返回会迫使实现把整个向量放在内存里。修改单个元素要用 `select`、生成器构造或掩码操作。注意这里是普通的 *Preconditions*，不是加固前置条件。

¶4：`operator[](const I& indices)`（`I` 是整数 `vec`）等价于 `permute(*this, indices)`。

### 迭代器（[simd.iterator]）

`begin()` 返回仅用于说明的 *simd-iterator*，`end()` 返回 `default_sentinel`。迭代器的 `operator*` 按值返回，`iterator_concept` 是 `random_access_iterator_tag`，`iterator_category` 却是 `input_iterator_tag`——因为它不满足 C++17 前向迭代器"`*it` 返回引用"的要求。可以用于 range-for 和只读算法。

## 逐元素运算（[simd.unary]、[simd.nonmembers]）

一元运算（`++`、`--`、`!`、`~`、`+`、`-`）、二元运算（`+ - * / % & | ^ << >>`）、复合赋值、比较运算都有相同的模式：

- *Constraints*：对应的标量表达式（如 `requires (value_type a, value_type b) { a op b; }`）合法；
- 结果是对每个元素施加 op 的逐元素运算；比较运算返回 `mask_type`。

二元运算都是 `noexcept` 的 `friend` 函数（隐藏友元，只经 ADL 找到），参数是 `const basic_vec&`——由于广播构造不是 `explicit`，`v * 2.0f` 中的 `2.0f` 可以隐式转换为 `basic_vec`。

!!! lawyer "逐元素运算继承核心语言的 UB"
    规范说结果"用对 lhs 与 rhs 逐元素施加 op 的结果初始化"，也就是对每个元素求值标量表达式 `a op b`。于是核心语言的规则逐个元素适用：`vec<int>` 某个元素除以零、有符号溢出、移位量超过宽度，都是 UB（[[expr.pre#4]]、[[expr.mul]]、[[expr.shift]]）——即使硬件的向量指令对这些情况有确定的行为。反过来，`vec<std::int8_t>` 的 `a + b`：标量表达式先经整型提升算成 `int`，再用来初始化 `int8_t` 元素，这是按模 2⁸ 的良定义转换，没有 UB。

移位还有 `v << n`（n 是 *simd-size-type* 标量）的重载，所有元素移同样的位数。

`select(mask, a, b)`（[simd.alg] ¶10）是 SIMD 版的条件运算符：`mask[i] ? a[i] : b[i]`，通过 ADL 找到仅用于说明的 *simd-select-impl*（"与 [contents] 相反"——标准库通常禁止依赖 ADL 找到未指名的函数，这里特意允许）。对 `bool` 条件，`select(c, a, b)` 就是 `c ? a : b`。

## 加载与存储（[simd.loadstore]、[simd.flags]）

从内存到向量、从向量到内存，有两套接口：

| | 范围不足 `size()` 时 |
|---|---|
| `unchecked_load` / `unchecked_store` | *Preconditions*：`ranges::size(r) ≥ V::size()`——不足即 UB；若大小是常量表达式则为 *Mandates* |
| `partial_load` / `partial_store` | 只读/写前 `ranges::size(r)` 个，其余元素为 `T()` / 不写 |

两者都有带掩码的重载（只处理被选元素）和"迭代器 + 个数""迭代器 + 哨兵""范围"三种形式。`partial_*` 可以安全处理数组末尾不足一个向量的"尾巴"，代价是额外的比较；`unchecked_*` 在已知长度足够时更快。

**标志**（[simd.flags]）：`flags<…>` 像一个类型级的位掩码，`operator|` 合并（`consteval`）。

- `flag_default`：无特殊假设；
- `flag_convert`：允许不保值的元素类型转换（例如从 `double` 数组加载到 `vec<float>`）。没有它时，不保值转换是 *Mandates* 错误；
- `flag_aligned`：断言指针按 `alignment_v<V, U>` 对齐——*Preconditions*，不对齐是 UB；
- `flag_overaligned<N>`：断言按 N 对齐（N 必须是 2 的幂）。

```cpp title="simd-saxpy.cpp" ok
#include <cstddef>
#include <simd>
#include <span>
namespace ss = std::simd;

// y = a·x + y，用 partial_load/store 处理尾部
void saxpy(float a, std::span<const float> x, std::span<float> y) {
  using V = ss::vec<float>;
  std::size_t i = 0;
  for (; i + V::size() <= x.size(); i += V::size()) {
    V vx = ss::unchecked_load<V>(x.subspan(i, V::size()));
    V vy = ss::unchecked_load<V>(y.subspan(i, V::size()));
    ss::unchecked_store(a * vx + vy, y.subspan(i, V::size()));
  }
  V vx = ss::partial_load<V>(x.subspan(i));          // 不足的元素读成 0
  V vy = ss::partial_load<V>(y.subspan(i));
  ss::partial_store(a * vx + vy, y.subspan(i));      // 只写剩余的元素
}
// 注：本机 libc++ 无 <simd>，未编译验证
```

**gather/scatter**（[simd.permute.memory]）：`unchecked_gather_from(r, indices)`、`partial_gather_from` 按下标向量从范围中收集元素；`unchecked_scatter_to`、`partial_scatter_to` 按下标分散写回。`partial_*` 版本对越界下标的元素不读不写。

## 归约（[simd.reductions]）

- `reduce(x, op = plus<>{})`：*Constraints*：`op` 建模 *reduction-binary-operation*（可对 `vec<T, 1>` 调用、逐元素且**可交换**）；结果是 *GENERALIZED_SUM*（[[numerics.defns]]，[[g:generalized-sum]]）——**以未指明的方式结合**。浮点归约的结果因此不保证与顺序累加相同，也不保证跨实现、跨宽度相同。
- 带掩码的 `reduce(x, mask, op, identity)`：只归约被选元素；`identity` 对 `plus`、`multiplies`、位运算有默认值，其他运算必须显式给出。
- `reduce_min`、`reduce_max`：`T` 必须全序。

掩码归约（[simd.mask.reductions]）：`all_of`、`any_of`、`none_of`、`reduce_count`；`reduce_min_index`/`reduce_max_index` 返回第一个/最后一个为真的下标，*Preconditions*：`any_of(k)`——全假时调用是 UB。每个都有接受 `bool` 的重载，使同一段泛型代码对标量和向量都能工作。

## 重排与组合（[simd.permute.*]、[simd.creation]）

- **静态 permute**（[simd.permute.static]）：`permute(v, idxmap)`，`idxmap(i)` 或 `idxmap(i, size)` 必须是**常量表达式**（*Mandates*），给出第 i 个结果元素取自哪个源元素；可以返回 `zero_element`（置零）或 `uninit_element`（值未指明）。结果宽度可以与源不同（模板实参 N）。
- **动态 permute**：`permute(v, indices)`，下标是运行期的整数向量。
- **compress / expand**（[simd.permute.mask]）：把被选元素紧凑地移到前面 / 反之展开，对应 AVX-512 的同名指令。
- **chunk / cat**：把宽向量切成若干窄向量（不整除时返回 `tuple`，最后一块较窄），或把若干向量拼接起来。
- `iota<V>`：元素为 0, 1, 2, … 的常量。

## 数学与位运算（[simd.math]、[simd.bit]、[simd.complex.math]）

几乎所有 `<cmath>` 函数（[[c.math]]）都有对浮点 `vec` 的重载，约束为 *math-floating-point*，返回类型用 *deduced-vec-t* 推导——所以可以混合 `vec` 与可隐式转换为它的类型。整数结果的函数（`ilogb`、`frexp` 的指数）返回 `rebind_t<int, …>`。`<bit>` 的函数（[[bit]]：`popcount`、`countl_zero`、`rotl`、`byteswap`、`bit_ceil`…）有对无符号整数 `vec` 的重载。复数元素有 `real`、`imag`、`abs`、`arg`、`norm`、`conj`、`proj`、`polar` 以及超越函数。

## basic_mask（[simd.mask.class]）

- 启用规则与 `basic_vec` 类似，按字节数：存在某个可向量化类型的 `sizeof` 等于 Bytes 时才可能启用；启用的特化平凡可复制。
- 构造：广播 `bool`（`explicit`，且实参必须**恰好**是 `bool`，`same_as<value_type> auto`）；从另一个宽度相同的掩码显式转换；生成器构造（生成器必须返回 `bool`）；从 `bitset<size()>` 隐式构造；从无符号整数显式构造（按位取前 M 个元素，其余为假）。
- 下标同样按值返回 `bool`。
- 一元 `!` 返回掩码；`+`、`-`、`~` 对每个 `bool` 元素施加运算、返回元素类型为 *integer-from*<Bytes> 的整数向量（如 `-m` 的真元素为 −1）——前提是存在大小为 Bytes 的可向量化有符号整数类型，否则这三个运算符被删除。
- 转换（[simd.mask.conv]）：到 `basic_vec<U, A>`（宽度相同；`sizeof(U) != Bytes` 时为 `explicit`），`to_bitset()`，`to_ullong()`（*Preconditions*：超过 `unsigned long long` 位数的那些元素都为假）。
- 二元 `&&`、`||`、`&`、`|`、`^` 和复合赋值都是逐元素的，**不短路**（两个操作数都已经求值好了）；六个比较运算符也是逐元素的，返回掩码。

!!! pitfall "if (a < b) 不能编译"
    `a < b` 返回 `mask`，而掩码没有到 `bool` 的转换——"一组比较结果"转成一个 `bool` 有 all/any 两种合理语义，标准拒绝替你选。要写成 `if (all_of(a < b))` 或 `if (any_of(a < b))`。

## 小结

| 方面 | 规则 |
|---|---|
| 类型 | `basic_vec<T, Abi>`/`vec<T, N>`、`basic_mask<Bytes, Abi>`/`mask<T, N>`，命名空间 `std::simd` |
| 元素 | 可向量化类型：标准整数、字符、`float`、`double`、`floatN_t`、`complex`；不含 `bool`、`long double` |
| 宽度 | 由 ABI 标签决定；`native-abi` 随编译选项变化 |
| 广播 | 只接受保值转换或编译期常量包装；`v * 2` 对 `vec<float>` 非良构 |
| 下标 | 按值返回，只读 |
| 运算 | 逐元素、无序；核心语言的 UB 逐元素适用 |
| 加载/存储 | `unchecked_*`（长度不足 UB）与 `partial_*`（安全处理尾部）；对齐标志是前置条件 |
| 归约 | *GENERALIZED_SUM*，结合方式未指明 |
| 实现 | libc++ 尚无 `<simd>` |
