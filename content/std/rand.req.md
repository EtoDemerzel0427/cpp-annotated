---
title: 随机数设施的要求
summary: <random> 的"合同层"——按模板形参名施加的类型要求（cv 限定、RealType/IntType/UIntType 不合要求即非良构）、单参构造函数必须 explicit；种子序列、均匀随机比特生成器（概念与具名要求）、引擎、引擎适配器、分布五张要求表的逐项含义，尤其是引擎与分布的 == 语义、discard、流式往返和 param_type
status: done
covers: *
related: rand, rand.eng, rand.util, rand.dist, rand.device, concepts.callable, utility.arg.requirements, basic.fundamental, temp.inst
tags: 标准库, 随机数, 具名要求, 概念
updated: 2026-10-18
---

[rand.req] 是 `<random>` 的"类型系统"：它不定义任何具体的类，而是规定**一个类型要满足什么才算**种子序列、URBG、引擎、引擎适配器、分布。标准自己的 `mt19937`、`normal_distribution` 等都按这些要求来规定（"Each type instantiated from … meets the requirements of …"），用户也可以写自己的引擎或分布，与标准组件自由组合。

| 子条款 | 内容 |
|---|---|
| [rand.req.genl] | 用模板形参名表达要求；单参构造函数必须 `explicit` |
| [rand.req.seedseq] | 种子序列（表 126） |
| [rand.req.urng] | 概念 `uniform_random_bit_generator` 与同名具名要求 |
| [rand.req.eng] | 随机数引擎（表 127） |
| [rand.req.adapt] | 随机数引擎适配器 |
| [rand.req.dist] | 随机数分布（表 128） |

## 一般要求（[rand.req.genl]）

### 模板形参的名字就是约束（¶1）

¶1：在 [rand] 中，模板形参未受约束时，用形参的**名字**表达对实例化的类型要求：

| 形参名 | 要求 | 违反的后果 |
|---|---|---|
| `Sseq`、`URBG`、`Engine`、`RealType`、`IntType`、`UIntType` | 实参不得 cv 限定（¶1.1） | **非良构** |
| `Sseq` | 满足种子序列要求（¶1.2） | 库的一般规则：UB |
| `URBG` | 满足均匀随机比特生成器要求（¶1.3） | 同上 |
| `Engine` | 满足随机数引擎要求（¶1.4） | 同上 |
| `RealType` | 标准浮点类型，或实现定义的扩展浮点类型子集（¶1.5） | **非良构** |
| `IntType` | 标准有符号/无符号整数类型；或宽度在 `char` 与 `long long` 之间的扩展整数类型；或实现定义的整数类型子集（¶1.6） | **非良构** |
| `UIntType` | 宽度在 `short` 与 `long long` 之间的标准或扩展无符号整数类型；或实现定义的子集（¶1.7） | **非良构** |

几个容易踩的点：

- **`char`、`bool`、`char8_t` 等不是 `IntType`**。标准有符号整数类型是 `signed char`、`short`、`int`、`long`、`long long`（[[basic.fundamental]]），`char` 不在其中；`bool` 和字符类型也不是"整数类型"意义上的标准整数类型。所以 `uniform_int_distribution<char>` 非良构，而 `uniform_int_distribution<signed char>`（即通常的 `int8_t`）合法。
- **`unsigned char`/`uint8_t` 是 `IntType` 但不是 `UIntType`**：引擎的 `UIntType` 宽度至少要和 `short` 一样。
- 这些规定把旧标准中的"未定义"改成了"非良构"，实现必须诊断。

```cpp title="inttype.cpp" error
#include <random>

std::uniform_int_distribution<signed char> ok1(-5, 5);    // OK：标准有符号整数类型
std::uniform_int_distribution<unsigned char> ok2(0, 9);   // OK
std::uniform_int_distribution<char> bad1;                 // error：char 不是 IntType
std::uniform_int_distribution<const int> bad2;            // error：cv 限定
std::linear_congruential_engine<unsigned char, 3, 1, 0> bad3;  // error：UIntType 窄于 short
```

!!! impl "libc++"
    libc++ 用 `__libcpp_random_is_valid_inttype` 白名单加 `static_assert` 检查 `IntType`，`char` 和 `const int` 都得到"IntType must be a supported integer type"。源码里把 `int8_t`/`uint8_t` 注释为"extension"——那是旧标准下的说法，按当前草案它们已经是标准允许的。`__int128` 也被接受，属于 ¶1.6 的"实现定义的子集"。`UIntType = unsigned char` 则没有被正面检查：只声明 `linear_congruential_engine<unsigned char, 3, 1, 0>` 对象时 libc++ 照常编译；直到调用 `operator()`，才在内部模板 `__lce_ta` 的实例化上出错。按 ¶1.7 这本应在实例化时就被诊断，所以例子最后一行在 libc++ 上实际不报错。

### 单参构造函数必须 explicit（¶3）

¶3：[rand] 中任何能以单个实参调用、且满足本子条款某个要求的构造函数，都必须声明为 `explicit`。所以 `std::mt19937 g = 42;`、`std::normal_distribution<> d = p;` 都是非良构的——只能直接初始化。这避免了 `void f(std::mt19937)` 被 `f(42)` 悄悄调用、每次产生一个新引擎。

¶2 只是措辞约定："x 是某种迭代器"读作"x 是满足相应迭代器要求的类型的值"。

## 种子序列（[rand.req.seedseq]）

¶1：**种子序列**（seed sequence，[[g:seed-sequence]]）是一个对象，它消耗一串整数数据，按请求产生任意个 [0, 2³²) 内的无符号整数。注释说明用途：避免多个引擎的随机流相互重复，对需要大量引擎的应用尤其有用。

表 126 的要求（`S` 为类型、`q` 为值、`r` 为可能 const 的值）：

| 表达式 | 要求 |
|---|---|
| `S::result_type` | 至少 32 位的无符号整数类型 |
| `S()` | 与所有默认构造的 `S` 有相同初始状态；常数复杂度 |
| `S(ib, ie)` | 内部状态依赖于 `[ib, ie)` 的部分或全部比特；O(ie−ib) |
| `S(il)` | 同 `S(il.begin(), il.end())` |
| `q.generate(rb, re)` | 空范围什么都不做；否则用 32 位量填满 `[rb, re)`，这些量依赖构造时提供的序列，**也可以**依赖以前的 `generate` 调用历史；O(re−rb) |
| `r.size()` | `param` 会复制多少个 32 位单元；常数 |
| `r.param(ob)` | 写出一串 32 位单元，用它构造另一个 `S` 能得到与 `r`"不可区分"的状态 |

注意 `generate` 是**非 const** 的，并允许依赖调用历史：同一个种子序列对象喂给两个引擎，两个引擎得到的可以不同。标准的 `seed_seq` 实际上不依赖历史（见 [[rand.util]]），但通用代码不能这样假设。`size`/`param` 的存在是为了能保存和重建种子序列。

## 均匀随机比特生成器（[rand.req.urng]）

¶1：**均匀随机比特生成器**（[[g:uniform-random-bit-generator]]）`g` 是一个返回无符号整数的函数对象，其可能结果范围内的每个值（理想情况下）等概率。"理想情况"由统计检验来衡量（注释）。

C++20 起它是一个概念：

```cpp
template<class G>
  concept uniform_random_bit_generator =
    invocable<G&> && unsigned_integral<invoke_result_t<G&>> &&
    requires {
      { G::min() } -> same_as<invoke_result_t<G&>>;
      { G::max() } -> same_as<invoke_result_t<G&>>;
      requires bool_constant<(G::min() < G::max())>::value;
    };
```

逐项读：

- `invocable<G&>`：以**非 const 左值**调用，所以 `operator()` 可以（通常也必须）修改状态；
- `unsigned_integral`：结果是无符号的整型。注意 `bool` 满足 `unsigned_integral`（它是整型且不是有符号的），所以概念本身不排除返回 `bool` 的生成器；¶3 的具名要求更严，要求结果是[[basic.fundamental|无符号整数类型]]，`bool` 不是；
- `G::min()`、`G::max()` 是**静态**成员，返回类型与 `g()` 完全相同；
- `bool_constant<(G::min() < G::max())>` 迫使 `min()`、`max()` 是**常量表达式**，并且 `min < max`。

¶2 是语义要求（只有满足才算"建模"）：`G::min() <= g()`、`g() <= G::max()`，`g()` 的复杂度是摊还常数。

¶3：类 `G` 满足**具名要求** *uniform random bit generator*，当且仅当它建模上述概念、`invoke_result_t<G&>` 是无符号整数类型（[[basic.fundamental]]），并且提供嵌套的 `result_type` 与之相同。概念不要求 `result_type`，具名要求要求——旧式代码（以及 [rand.req.genl] 中名为 `URBG` 的模板形参）依赖它。

```cpp run title="urbg-concept.cpp" ok
#include <cstdint>
#include <random>

struct Counter {                                   // 满足概念，也满足具名要求
  using result_type = std::uint32_t;
  static constexpr result_type min() { return 0; }
  static constexpr result_type max() { return 0xFFFF'FFFF; }
  result_type n = 0;
  result_type operator()() { return n++; }
};
static_assert(std::uniform_random_bit_generator<Counter>);

using Lambda = decltype([s = 0u]() mutable { return s++; });
static_assert(!std::uniform_random_bit_generator<Lambda>);   // 没有静态 min()/max()

struct Degenerate {
  using result_type = unsigned;
  static constexpr unsigned min() { return 5; }
  static constexpr unsigned max() { return 5; }  // min < max 不成立
  unsigned operator()() { return 5; }
};
static_assert(!std::uniform_random_bit_generator<Degenerate>);

struct Signed {
  static constexpr int min() { return 0; }
  static constexpr int max() { return 9; }
  int operator()() { return 3; }
};
static_assert(!std::uniform_random_bit_generator<Signed>);   // 结果必须是无符号整数
```

`Counter` 完全满足语法要求，但它显然不"均匀随机"——概念只能检查语法，"每个值等概率"永远只能靠文档和统计检验保证。把 `Counter` 传给分布是良构的，结果是确定的、可预测的序列；这在测试分布实现时很有用。

## 随机数引擎（[rand.req.eng]）

¶1：**随机数引擎**（[[g:random-number-engine]]）是额外满足播种、输入输出等要求的 URBG。

### 状态模型（¶2–¶3）

¶2：引擎 `e` 在任意时刻有状态 eᵢ（i ≥ 0），构造后为初始状态 e₀；状态可以由构造函数、`seed`、赋值或 `operator>>` 建立。

¶3：引擎类型的规范必须定义三样东西：

1. 状态的大小，以 `result_type` 大小的倍数表示，是整数常量表达式；
2. **转移算法** TA：把 eᵢ 推进到后继状态 eᵢ₊₁；
3. **生成算法** GA：把状态映射为一个 `result_type` 值。

`e()` 的语义（表 127）是：把状态推进到 eᵢ₊₁ = TA(eᵢ)，并返回 GA(eᵢ)。GA 作用在**转移前**的状态上，但它的定义可以引用转移的结果——例如线性同余引擎把 GA 定义为 GA(xᵢ) = xᵢ₊₁，于是返回的正是新状态（见 [[rand.eng]]）。

### 表 127 的要点

| 表达式 | 语义 | 复杂度 |
|---|---|---|
| `E()` | 与所有默认构造的 `E` 初始状态相同 | O(状态大小) |
| `E(x)` | 与 `x` 比较相等 | O(状态大小) |
| `E(s)` | 由 `result_type` 值 `s` 决定初始状态 | O(状态大小) |
| `E(q)` | 初始状态依赖于对种子序列 `q` 的**一次** `generate` 调用的结果 | 同 `q.generate` 填充一个"状态大小"长的序列 |
| `e.seed()`、`e.seed(s)`、`e.seed(q)` | 后置条件分别是 `e == E()`、`e == E(s)`、`e == E(q)` | 同相应构造 |
| `e()` | 推进到 TA(eᵢ)，返回 GA(eᵢ) | 摊还常数（按 URBG） |
| `e.discard(z)` | 把状态推进到 eᵢ₊z，效果等价于连续调用 z 次 `e()` | 不劣于 z 次调用 |
| `x == y` | 等价关系；当且仅当 `x`、`y` 将来无限次调用产生的**无限序列相同**时为真 | O(状态大小) |

`==` 的定义值得细读：它比较的是**未来行为**，而不是内部表示。两个内部字节不同、但未来输出序列完全一致的引擎状态也必须比较相等（例如 `philox_engine` 中缓存的输出 Y 可以从 K、X 重建）。反过来，相等的引擎可以互相替换而不改变程序的可观察行为。

脚注 220 说明 `discard` 常常可以用引擎特有的方式实现得远比循环快——线性同余引擎可以用快速幂跳跃，`philox_engine` 只需改计数器。但标准只要求"不劣于"朴素循环；libc++ 的 `mersenne_twister_engine::discard` 和 `linear_congruential_engine::discard` 都是循环调用 `operator()`。

¶5：引擎必须满足 *Cpp17CopyConstructible* 与 *Cpp17CopyAssignable*，复杂度不劣于 O(状态大小)。复制一个 `mt19937` 要复制约 2.5 KB 状态，按值传递引擎是常见的性能陷阱，也是逻辑陷阱：副本被推进，原引擎不变，下一次又产生同样的数。

### 流式输入输出（¶6–¶17）

在宿主实现上：

- `os << x`（¶7–¶11）：以 `dec | left`、填充字符为空格写出 `x` 当前状态的文本表示，相邻数字之间至少一个空格；之后恢复 `os` 的格式标志与填充字符。
- `is >> v`（¶12–¶17）：前置条件是输入由 locale、`charT`、`traits` 都相同的流写出；读入失败时**保证 `v` 不变**并设置 `failbit`。往返保证：`os << x` 写出、`is >> v` 读入后 `x == v`，只要期间两者都没有被调用。

文本表示的内容由各引擎规定（[[rand.eng]]），所以一个实现写出的 `mt19937` 状态可以被另一个实现读入——这是引擎"可移植"的另一面。

```cpp run title="engine-roundtrip.cpp" ok
#include <cassert>
#include <random>
#include <sstream>

int main() {
  std::mt19937 a(42);
  a.discard(100);
  std::stringstream ss;
  ss << a;                // 保存完整状态（624 个数）
  std::mt19937 b;
  ss >> b;                // 恢复
  assert(a == b);         // == 比较未来序列
  assert(a() == b());
}
```

## 随机数引擎适配器（[rand.req.adapt]）

¶1：**引擎适配器** `a` 是一个引擎，它取另一个引擎（**基引擎** `b`）产生的值，施加某种算法，得到随机性质不同的序列。`a.base()` 必须有效并返回基引擎的 const 引用。

¶2–¶9 规定如何把引擎要求"翻译"到适配器上：默认构造、`A(s)`、`A(q)`、`seed(…)` 都转发给基引擎；`a1 == a2` 当且仅当两者的基引擎相等。

¶10 的附加要求：

- ¶10.1 每个函数的复杂度不超过基引擎上对应函数的复杂度；
- ¶10.2 适配器的状态**包含**基引擎的状态，大小不小于基引擎；
- ¶10.3 复制适配器要复制基引擎状态；
- ¶10.4 文本表示要包含基引擎的文本表示。

!!! lawyer "== 只看基引擎？"
    ¶4 说两个适配器"基引擎相等则返回 true，否则 false"。但表 127 对引擎的 `==` 要求"未来序列相同"。对 `discard_block_engine`，额外状态 n（块内计数）不同、基引擎相同的两个对象，未来序列显然不同。这两条放在一起读，¶4 只能理解为对**以同样方式构造并经历同样操作**的适配器的简化描述；实践中 libc++ 的 `discard_block_engine::operator==` 同时比较基引擎和 n，`shuffle_order_engine` 同时比较表 V 与 Y。

## 随机数分布（[rand.req.dist]）

¶1：**随机数分布**（[[g:random-number-distribution]]）`d` 是一个函数对象，返回值服从某个概率密度函数 p(z)（连续）或离散概率函数 P(zᵢ)。¶2：概率函数通常含有外部给定的量，称为**分布的参数**，写作 p(z | a, b) 或 p(z | {p})。

### 表 128 的要点

| 表达式 | 语义 |
|---|---|
| `D::result_type` | 算术类型 |
| `D::param_type` | 参数包类型 `P` |
| `D()` | 与任何新默认构造的 `D` 行为不可区分 |
| `D(p)` | 与直接用 `p` 的那组值构造的分布行为不可区分 |
| `d.reset()` | 之后对 `d` 的使用**不依赖** reset 之前任何引擎产生的值；常数复杂度 |
| `x.param()` / `d.param(p)` | 读 / 设参数；`D(p).param() == p` |
| `d(g)` | 对同一个 `g` 连续调用，结果按 p(z \| {d.param()}) 分布；摊还常数次调用 `g` |
| `d(g, p)` | 用参数 `p` 生成，**不改变** `d` 的参数 |
| `x.min()` / `x.max()` | 可能返回值的最大下界 / 最小上界 |
| `x == y` | 参数相等，且在 `g1 == g2` 时两者未来产生的无限序列相同 |

`reset` 的存在说明分布可以有**内部状态**：最典型的是正态分布的 Box–Muller/极坐标法一次生成两个值、缓存一个。`reset` 清掉这类缓存。`d(g, p)` 让同一个分布对象可以用不同参数生成，而不必为每组参数构造对象——例如在一个循环里按不同上界抽样：

```cpp title="dist-param.cpp" ok
#include <random>
#include <vector>

// Fisher–Yates：每一步上界不同，复用同一个分布对象
template<class T, class G>
void shuffle_vec(std::vector<T>& v, G& g) {
  std::uniform_int_distribution<std::size_t> d;
  using P = decltype(d)::param_type;
  for (std::size_t i = v.size(); i > 1; --i)
    std::swap(v[i - 1], v[d(g, P(0, i - 1))]);
}
```

### 其他段落

- ¶4：`D` 满足 *Cpp17CopyConstructible*、*Cpp17CopyAssignable*。
- ¶5：`d(g)` 产生的序列**不受**其间调用 `os << d` 或任何 `const` 成员函数的影响——查询参数、打印状态不会扰动随机流。
- ¶6：把 `x` 的文本表示用 `os << x` 写出、再用 `is >> y` 读回同类型的 `y`，此后 `y(g)` 与 `x(g)` 产生相同的序列。文本表示包括参数**和附加内部数据**（¶12），比如正态分布缓存的那个值。注意文本表示的格式是实现定义的，跨实现读入没有保证——这与引擎不同。
- ¶7：`D::param_type` 是嵌套类还是 typedef，**未指明**。所以不能前向声明 `struct std::normal_distribution<double>::param_type;`，也不能依赖它的名字做 ADL。
- ¶8–¶10：`P` 满足可复制构造、可复制赋值、*Cpp17EqualityComparable*；对 `D` 每个接受分布参数的构造函数，`P` 有参数个数、类型、默认值都相同的构造函数；对 `D` 每个返回参数的成员函数，`P` 有同名、同类型、同语义的成员函数；`P` 声明 `using distribution_type = D;`。
- ¶11–¶20：流插入/提取，失败时保证 `d` 不变。

## 思考题

!!! question "1"
    `std::uniform_int_distribution<bool>` 和 `std::uniform_int_distribution<std::int8_t>` 是否良构？若 `std::int8_t` 在某平台上是一个扩展整数类型而不是 `signed char` 呢？

<details markdown="1">
<summary>答案</summary>

`bool` 不是标准有符号或无符号整数类型，也不是扩展整数类型，除非实现把它放进"实现定义的子集"，否则按 [rand.req.genl] ¶1.6 非良构。（要随机布尔值，用 `bernoulli_distribution`。）

`int8_t` 通常是 `signed char` 的别名，属于标准有符号整数类型，良构。若它是扩展整数类型，¶1.6 要求其宽度"大于等于 `char` 的宽度、小于等于 `long long` 的宽度"——8 位等于 `char` 的宽度，也良构。
</details>

!!! question "2"
    `std::mt19937 a, b; b.discard(1); a();` 之后 `a == b` 吗？`a` 和 `b` 的内部字节一定相同吗？

<details markdown="1">
<summary>答案</summary>

相等：`discard(1)` 的效果等价于调用一次 `b()`（表 127），之后两者的未来无限序列相同，按表 127 的 `==` 语义比较相等。至于内部字节，标准不关心——`==` 是按未来行为定义的。对 `mt19937` 而言两条路径执行的操作完全相同，实际字节通常也相同；但对一般的引擎，`discard` 可以走跳跃式捷径，得到表示不同而未来序列相同的状态，它们也必须比较相等。
</details>

## 小结

| 实体 | 关键要求 |
|---|---|
| 一般 | 形参名即约束；`RealType`/`IntType`/`UIntType`/cv 限定违规为非良构；单参构造函数 `explicit` |
| 种子序列 | 输出 32 位量；`generate` 可依赖历史；`param` 可重建 |
| URBG | 概念：可调用、无符号结果、`constexpr` 的 `min < max`；具名要求另需 `result_type` |
| 引擎 | 状态 + TA + GA；`==` 比较未来序列；`discard`；可移植的文本表示 |
| 适配器 | 状态包含基引擎；`base()` |
| 分布 | 可有内部状态（`reset` 清除）；`d(g, p)` 不改参数；`param_type` 形式未指明；文本格式不跨实现 |
