---
title: 随机数设施的要求
summary: 一个类型要满足什么才算种子序列、URBG、引擎、引擎适配器或分布；引擎和分布的 == 比较什么；以及 IntType、RealType、UIntType 这些模板形参接受哪些类型。
status: done
covers: *
related: rand, rand.eng, rand.util, rand.dist, rand.device, concepts.callable, utility.arg.requirements, basic.fundamental, temp.inst
tags: 标准库, 随机数, 具名要求, 概念
updated: 2026-10-19
---

!!! tldr
    - 概念 `uniform_random_bit_generator` 只检查语法：能以非 const 左值调用、返回无符号整型、有 `constexpr` 的静态 `min() < max()`。均匀与否只能靠统计检验。
    - 引擎由状态、转移算法和生成算法规定。两个引擎 `==` 的含义是它们将来产生的无限序列相同，而不是内部字节相同。
    - 分布可以有内部状态（例如缓存的第二个正态值），`reset()` 清除它；`d(g, p)` 用临时参数生成而不改变 `d`。
    - 引擎的文本表示跨实现通用，分布的文本表示格式由实现定义。
    - `uniform_int_distribution<char>`、`<bool>`、`<const int>` 都是非良构的；`signed char` 和 `unsigned char` 可以。

[rand.req] 不定义具体的类，只规定一个类型要满足什么才算种子序列、URBG、引擎、适配器或分布。标准自己的 `mt19937`、`normal_distribution` 都按这些要求来规定，用户写的类型只要满足要求，也能和标准组件自由组合。各类实体的概览见 [[rand]]。

## 均匀随机比特生成器（[rand.req.urng]）

先看一个自己写的生成器：

```cpp run title="urbg-concept.cpp" ok
#include <cstdint>
#include <random>

struct Counter {
  using result_type = std::uint32_t;
  static constexpr result_type min() { return 0; }
  static constexpr result_type max() { return 0xFFFF'FFFF; }
  result_type n = 0;
  result_type operator()() { return n++; }
};
static_assert(std::uniform_random_bit_generator<Counter>);

// 没有静态的 min()/max()
using Lambda = decltype([s = 0u]() mutable { return s++; });
static_assert(!std::uniform_random_bit_generator<Lambda>);

struct Degenerate {                     // min < max 不成立
  using result_type = unsigned;
  static constexpr unsigned min() { return 5; }
  static constexpr unsigned max() { return 5; }
  unsigned operator()() { return 5; }
};
static_assert(!std::uniform_random_bit_generator<Degenerate>);

struct Signed {                         // 结果必须是无符号的
  static constexpr int min() { return 0; }
  static constexpr int max() { return 9; }
  int operator()() { return 3; }
};
static_assert(!std::uniform_random_bit_generator<Signed>);

int main() {}
```

`Counter` 显然不随机，却满足概念。概念只能检查语法；每个值等概率这一点只能由文档和统计检验保证。把 `Counter` 传给分布是良构的，得到一个确定的序列，测试分布实现时正好用得上。

¶1 **均匀随机比特生成器**（[[g:uniform-random-bit-generator]]）`g` 是一个返回无符号整数的函数对象，取值范围内每个值（理想情况下）等概率。C++20 起它对应一个概念：

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

逐项来看：

- `invocable<G&>`：以非 const 左值调用，所以 `operator()` 可以修改状态，通常也必须修改；
- `unsigned_integral`：结果是无符号整型。`bool` 也满足 `unsigned_integral`，概念本身不排除它；
- `G::min()`、`G::max()` 是静态成员，返回类型与 `g()` 完全相同；
- `bool_constant<(G::min() < G::max())>` 迫使两者是常量表达式，并且 `min < max`。

¶2 要建模（model）这个概念，还要满足语义要求：`G::min() <= g()`、`g() <= G::max()`，`g()` 的复杂度是摊还常数。

¶3 **具名要求** *uniform random bit generator* 比概念多两条：`invoke_result_t<G&>` 必须是无符号整数类型（[[basic.fundamental]]，`bool` 不算），并且要有嵌套的 `result_type` 与之相同。旧式代码和名为 `URBG` 的模板形参依赖这个 `result_type`。

## 种子序列（[rand.req.seedseq]）

¶1 **种子序列**（[[g:seed-sequence]]）消耗一串整数，再按请求产生任意多个 [0, 2³²) 内的无符号整数。注释说明了用途：避免多个引擎产生重复的随机流，需要大量引擎的程序尤其用得上。标准提供的种子序列是 `seed_seq`（[[rand.util]]）。

表 126 的要求（`S` 是类型，`q` 是值，`r` 是可能 const 的值）：

| 表达式 | 要求 |
|---|---|
| `S::result_type` | 至少 32 位的无符号整数类型 |
| `S()` | 与所有默认构造的 `S` 初始状态相同 |
| `S(ib, ie)`、`S(il)` | 内部状态依赖于输入序列的部分或全部比特 |
| `q.generate(rb, re)` | 用 32 位量填满 `[rb, re)`；结果依赖构造时的输入，也可以依赖之前 `generate` 的调用历史 |
| `r.size()` | `param` 会写出多少个 32 位单元 |
| `r.param(ob)` | 写出一串 32 位单元，用它构造另一个 `S` 能得到与 `r` 不可区分的状态 |

`generate` 不是 const 成员，而且允许依赖调用历史。所以同一个种子序列对象依次喂给两个引擎，两个引擎得到的种子可以不同。标准的 `seed_seq` 恰好不依赖历史，但通用代码不能这样假设。`size` 和 `param` 用来保存并重建种子序列。

## 随机数引擎（[rand.req.eng]）

¶1 **随机数引擎**（[[g:random-number-engine]]）是另外满足播种、输入输出等要求的 URBG。

### 状态、转移与生成（¶2–¶3）

¶2 引擎 `e` 在任意时刻处于某个状态 eᵢ（i ≥ 0），构造后为初始状态 e₀。状态可以由构造函数、`seed`、赋值或 `operator>>` 建立。

¶3 每种引擎的规范必须定义三样东西：

1. 状态的大小，以 `result_type` 大小的倍数表示；
2. **转移算法**（transition algorithm）TA：把 eᵢ 推进到后继状态 eᵢ₊₁；
3. **生成算法**（generation algorithm）GA：把状态映射为一个 `result_type` 值。

`e()` 把状态推进到 eᵢ₊₁ = TA(eᵢ)，并返回 GA(eᵢ)。GA 作用在转移前的状态上，但它的定义可以引用转移的结果。例如线性同余引擎定义 GA(xᵢ) = xᵢ₊₁，返回的正是新状态（[[rand.eng]]）。

### 表 127 的要点（¶4）

| 表达式 | 语义 |
|---|---|
| `E()` | 与所有默认构造的 `E` 初始状态相同 |
| `E(s)` | 由一个 `result_type` 值 `s` 决定初始状态 |
| `E(q)` | 初始状态依赖于对种子序列 `q` 的一次 `generate` 调用 |
| `e.seed()`、`e.seed(s)`、`e.seed(q)` | 后置条件分别是 `e == E()`、`e == E(s)`、`e == E(q)` |
| `e()` | 推进到 TA(eᵢ)，返回 GA(eᵢ)；摊还常数复杂度 |
| `e.discard(z)` | 推进到 eᵢ₊z，效果等价于连续调用 z 次 `e()` |
| `x == y` | 当且仅当 `x`、`y` 将来无限次调用产生的无限序列相同 |

`==` 比较的是将来的行为，不是内部表示。两个内部字节不同、将来输出完全相同的引擎必须比较相等，例如 `philox_engine` 里缓存的输出可以由密钥和计数器重建。反过来，相等的引擎可以互相替换而不改变程序的可观察行为。

脚注 220 指出，`discard` 往往可以用引擎特有的方式实现得比循环快得多：线性同余引擎可以用快速幂跳跃，`philox_engine` 只需修改计数器。标准只要求不比循环慢；libc++ 的 `mersenne_twister_engine::discard` 就是循环调用 `operator()`。

¶5 引擎必须可复制构造、可复制赋值，复杂度不超过 O(状态大小)。复制一个 `mt19937` 要复制约 2.5 KB 的状态。按值传递引擎既慢又容易出错：被推进的是副本，原引擎不变，下次调用又得到同样的数。

### 文本表示（¶6–¶17）

在宿主实现上，`os << x` 以十进制、左对齐、空格填充写出 `x` 当前状态的文本表示，之后恢复流的格式标志（¶7–¶11）。`is >> v` 读回状态，读入失败时 `v` 保持不变并设置 `failbit`（¶12–¶17）。写出再读回之后 `x == v`，前提是两者之间都没有被调用。

文本表示的内容由各引擎规定（[[rand.eng]]），所以一个实现写出的 `mt19937` 状态可以被另一个实现读入。

```cpp run title="engine-roundtrip.cpp" ok
#include <cassert>
#include <random>
#include <sstream>

int main() {
  std::mt19937 a(42);
  a.discard(100);
  std::stringstream ss;
  ss << a;              // 保存完整状态（624 个数）
  std::mt19937 b;
  ss >> b;              // 恢复
  assert(a == b);       // 比较将来的序列
  assert(a() == b());
}
```

## 引擎适配器（[rand.req.adapt]）

¶1 **引擎适配器**（[[g:random-number-engine-adaptor]]）`a` 是一个引擎，它取另一个引擎（**基引擎**，base engine）`b` 产生的值，施加某种算法，得到随机性质不同的序列。`a.base()` 返回基引擎的 const 引用。

¶2–¶9 把引擎的要求转到适配器上：默认构造、`A(s)`、`A(q)`、各个 `seed` 都转发给基引擎；`a1 == a2` 当且仅当两者的基引擎相等。

¶10 还要求：每个函数的复杂度不超过基引擎上对应函数的复杂度；适配器的状态包含基引擎的状态；复制适配器要复制基引擎的状态；文本表示包含基引擎的文本表示。

!!! lawyer "== 只看基引擎？"
    ¶4 说两个适配器的基引擎相等就返回 true。但表 127 要求引擎的 `==` 表示将来的序列相同。两个 `discard_block_engine` 基引擎相同、块内计数不同时，将来的序列显然不同。两条放在一起读，¶4 只能理解为对以同样方式构造、经历同样操作的适配器的简化描述。libc++ 的 `discard_block_engine::operator==` 同时比较基引擎和计数，`shuffle_order_engine` 同时比较内部表和缓存值。

## 随机数分布（[rand.req.dist]）

¶1 **随机数分布**（[[g:random-number-distribution]]）`d` 是一个函数对象，返回值服从某个概率密度函数 p(z) 或离散概率函数 P(zᵢ)。¶2 概率函数里通常含有外部给定的量，称为分布的**参数**，写作 p(z | a, b) 或 p(z | {p})。

### 表 128 的要点（¶3）

| 表达式 | 语义 |
|---|---|
| `D::param_type` | 参数包类型，下面记作 `P` |
| `D()`、`D(p)` | 默认参数，或用 `p` 中的参数构造 |
| `d.reset()` | 之后对 `d` 的使用不依赖 reset 之前任何引擎产生的值 |
| `x.param()`、`d.param(p)` | 读、写参数；`D(p).param() == p` |
| `d(g)` | 对同一个 `g` 连续调用，结果服从 p(z \| {d.param()})；平均调用 `g` 常数次 |
| `d(g, p)` | 用参数 `p` 生成，不改变 `d` 自己的参数 |
| `x.min()`、`x.max()` | 可能返回值的最大下界、最小上界 |
| `x == y` | 参数相等，并且在 `g1 == g2` 时两者将来产生的序列相同 |

`reset` 的存在说明分布可以有内部状态。典型例子是正态分布的 Box–Muller 或极坐标法，一次算出两个值、缓存一个，`reset` 清除这类缓存（[[rand]] 的思考题演示了它的影响）。

`d(g, p)` 让同一个分布对象可以用不同参数生成。下面的洗牌每一步上界都不同：

```cpp run title="dist-param.cpp" ok
#include <random>
#include <utility>
#include <vector>

template<class T, class G>
void shuffle_vec(std::vector<T>& v, G& g) {
  std::uniform_int_distribution<std::size_t> d;
  using P = decltype(d)::param_type;
  for (std::size_t i = v.size(); i > 1; --i)
    std::swap(v[i - 1], v[d(g, P(0, i - 1))]);
}

int main() {
  std::vector<int> v{1, 2, 3, 4, 5};
  std::mt19937 g(1);
  shuffle_vec(v, g);
}
```

### 其他要求（¶4–¶20）

- ¶4 分布可复制构造、可复制赋值。
- ¶5 在两次 `d(g)` 之间调用 `os << d` 或任何 const 成员函数，不会改变产生的序列。查询参数、打印状态不会扰动随机流。
- ¶6 把 `x` 写出、再读回同类型的 `y`，此后 `y(g)` 与 `x(g)` 产生相同的序列。文本表示包括参数和内部数据，例如正态分布缓存的值。文本格式由实现定义，跨实现读入没有保证，这一点与引擎不同。
- ¶7 `D::param_type` 是嵌套类还是 typedef，未指明。所以不能前向声明 `std::normal_distribution<double>::param_type`。
- ¶8–¶10 `P` 可复制、可比较相等；`D` 每个接受参数的构造函数，`P` 都有参数相同的构造函数；`D` 每个返回参数的成员函数，`P` 都有同名的成员函数；`P` 声明 `using distribution_type = D;`。
- ¶11–¶20 流插入和提取，读入失败时 `d` 不变。

## 模板实参的限制（[rand.req.genl]）

```cpp title="inttype.cpp" error
#include <random>

std::uniform_int_distribution<signed char> a(-5, 5);    // OK
std::uniform_int_distribution<unsigned char> b(0, 9);   // OK
std::uniform_int_distribution<char> c;      // error: char 不是 IntType
std::uniform_int_distribution<const int> d; // error: cv 限定
std::linear_congruential_engine<unsigned char, 3, 1, 0>
    e;                          // error: UIntType 比 short 窄
```

¶1 [rand] 的模板形参没有用概念约束时，形参的名字本身就表示对实参的要求：

| 形参名 | 实参必须是 | 违反的后果 |
|---|---|---|
| `Sseq`、`URBG`、`Engine`、`RealType`、`IntType`、`UIntType` | 没有 cv 限定的类型（¶1.1） | 非良构 |
| `Sseq` / `URBG` / `Engine` | 满足种子序列 / URBG / 引擎要求（¶1.2–¶1.4） | 违反库的要求，UB |
| `RealType` | 标准浮点类型，或实现选定的扩展浮点类型（¶1.5） | 非良构 |
| `IntType` | 标准有符号或无符号整数类型；宽度在 `char` 与 `long long` 之间的扩展整数类型；或实现选定的其他整数类型（¶1.6） | 非良构 |
| `UIntType` | 宽度在 `short` 与 `long long` 之间的标准或扩展无符号整数类型；或实现选定的其他无符号整数类型（¶1.7） | 非良构 |

标准有符号整数类型只有 `signed char`、`short`、`int`、`long`、`long long` 五个（[[basic.fundamental]]），`char`、`bool` 和各种字符类型都不在其中。所以 `uniform_int_distribution<char>` 非良构，而 `uniform_int_distribution<signed char>`（通常就是 `int8_t`）合法。`unsigned char` 可以做 `IntType`，但不能做 `UIntType`，因为引擎的 `UIntType` 至少要和 `short` 一样宽。要随机的布尔值，用 `bernoulli_distribution`。

!!! impl "libc++"
    libc++ 用一个白名单加 `static_assert` 检查 `IntType`，`char`、`bool`、`const int` 都会得到 "IntType must be a supported integer type"。`__int128` 被接受，属于实现选定的其他整数类型。`UIntType = unsigned char` 则没有被直接检查：只声明 `linear_congruential_engine<unsigned char, 3, 1, 0>` 的对象时照常编译，直到调用 `operator()` 才在内部模板的实例化上出错。按 ¶1.7 这本应在实例化时就诊断，所以上面例子的最后一个声明在 libc++ 上实际不报错。

¶3 [rand] 中任何能以单个实参调用、并且满足本节某项要求的构造函数都必须是 `explicit` 的。所以 `std::mt19937 g = 42;` 非良构，只能写 `std::mt19937 g(42);`。这样 `void f(std::mt19937)` 不会因为 `f(42)` 悄悄构造出一个新引擎。

<details class="fine" markdown="1"><summary>其余条文</summary>

[rand.req.genl] ¶2：[rand] 中"x 是某种迭代器"读作"x 是满足相应迭代器要求的类型的值"。

[rand.req.eng] ¶4 还列出了 `E(x)`（与 `x` 比较相等）以及各操作的复杂度：构造、`seed`、`==` 都是 O(状态大小)，`E(q)` 与 `q.generate` 填充一个状态大小的序列同阶，`discard(z)` 不劣于 z 次 `e()`。

</details>

## 思考题

!!! question "1"
    `std::uniform_int_distribution<bool>` 和 `std::uniform_int_distribution<std::int8_t>` 良构吗？如果某个平台上 `std::int8_t` 是扩展整数类型而不是 `signed char` 呢？

<details markdown="1">
<summary>答案</summary>

`bool` 既不是标准整数类型也不是扩展整数类型，除非实现把它放进自己选定的集合，否则按 [rand.req.genl] ¶1.6 非良构。libc++ 拒绝它。

`int8_t` 通常是 `signed char` 的别名，属于标准有符号整数类型，良构。如果它是扩展整数类型，¶1.6 要求宽度不小于 `char`、不大于 `long long`；8 位等于 `char` 的宽度，同样良构。
</details>

!!! question "2"
    `std::mt19937 a, b; b.discard(1); a();` 之后 `a == b` 吗？两者的内部字节一定相同吗？

<details markdown="1">
<summary>答案</summary>

相等。`discard(1)` 等价于调用一次 `b()`（表 127），之后两者将来的无限序列相同，所以比较相等。

内部字节标准并不关心，`==` 是按将来的行为定义的。`mt19937` 的两条路径执行完全相同的操作，字节实际上也相同；但一般的引擎可以让 `discard` 走跳跃式的捷径，得到表示不同而将来序列相同的状态，它们也必须比较相等。
</details>
