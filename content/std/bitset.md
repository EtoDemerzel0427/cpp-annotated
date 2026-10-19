---
title: 位集
summary: std::bitset<N> 是长度在编译期确定的位序列：位的编号与整数、字符串的对应关系，代理类 reference，构造和访问函数各自在什么情况下抛出哪种异常，以及 C++23 起的 constexpr 支持。
status: draft
covers: *
papers: P2417R2, P2697R1
related: bit, vector.bool, unord.hash, structure.specifications, intro.multithread, basic.types, expr.const
tags: 标准库, bitset, 代理引用, constexpr
updated: 2026-10-19
---

!!! tldr
    - bit `pos` 对应整数中的 `1 << pos`，所以 bit 0 是最低位；与字符串互转时，最右边的字符是 bit 0。
    - 从整数构造时保留低位，从过长的字符串构造时保留左边的字符，两者截断方向相反。
    - `test`、`set(pos)`、`reset(pos)`、`flip(pos)` 越界时抛出 `out_of_range`；`operator[]` 越界从不抛出，加固实现中终止，其他实现中是 UB。
    - 非 const 的 `operator[]` 返回代理对象 `reference`；经由它写任意一位，在数据竞争意义上都算写整个 bitset。
    - C++23 起几乎所有成员都能在常量求值中使用，只有流运算符和 `hash` 除外；移位量不小于 N 时结果为零，不是 UB。

```cpp run ok
#include <bitset>
#include <cstdio>

int main() {
  std::bitset<8> b("00010110");      // 最右边的字符是 bit 0
  std::printf("%d %d %lu\n", (int)b[1], (int)b[0], b.to_ulong());
  // 1 0 22
  std::bitset<4> t(0b1111'0101ULL);  // 只保留低 4 位
  std::printf("%s\n", t.to_string().c_str());   // 0101
}
```

`std::bitset<N>` 是一串 N 个标志位，N 是模板实参。它可以按位置读写、整体做与或非和移位、统计置位个数，还能与整数和 `"0101"` 这样的字符串互相转换。

位数在编译期固定，所以它没有分配器，不会增长，对象大小固定，通常是 N 位向上取整到若干个机器字。这是它与 `std::vector<bool>`（[[vector.bool]]）的根本区别。

本页用到库条款的几个小标题（[[structure.specifications]]）：*Throws* 列出函数会抛出的异常；*Constraints* 不满足时函数不参与重载决议；*Hardened preconditions*（加固前置条件）被违反时，加固实现必须终止程序，其他实现中是 UB。

## 头文件 [bitset.syn]

¶1 `<bitset>` 定义类模板 `bitset` 和几个相关函数。概要中包含了 `<string>` 和 `<iosfwd>`，因为 `to_string` 返回 `basic_string`，流运算符要用到 `basic_istream` 和 `basic_ostream`。所以 `<bitset>` 不是一个轻量的头文件，也不属于 freestanding 实现必须提供的部分（对比 [[bit]]）。

非成员的 `&`、`|`、`^` 都是 `constexpr` 且 `noexcept` 的；流运算符两者都不是。

## 位的编号 [template.bitset.general]

¶1 `bitset<N>` 存放一个由 N 个位组成的序列。

¶2 每一位的值是 0（清零，reset）或 1（置位，set）。把 0 变成 1、1 变成 0 叫做**切换**（toggle），`flip` 和 `^=` 都用这个词描述。每一位有一个非负的位置 `pos`：

!!! std
    When converting between an object of type `bitset<N>` and a value of some integral type, bit position `pos` corresponds to the *bit value* `1 << pos`.

与整数互相转换时，位置 `pos` 对应位值 `1 << pos`，多个位对应的整数是各位位值之和。所以 bit 0 是最低有效位，bit N−1 是最高位。这是数值上的对应，与字节序和内存布局无关，标准没有规定 `bitset` 内部怎样存储。

与字符串互相转换时（[bitset.cons] ¶4、[bitset.members] ¶41），最后一个字符对应 bit 0，越往左位置越高，这与书写二进制数的习惯一致：`"0110"` 表示 6，其中 `b[1]` 和 `b[2]` 是 1。

因此 `b[i]` 的下标从低位数起，`to_string()` 的字符从高位数起。把 `to_string()` 的第 `i` 个字符当成 `b[i]` 是最常见的错误。

## 构造 [bitset.cons]

### 从整数构造（¶1–2）

¶1 默认构造函数把所有位清零。

¶2 `bitset(unsigned long long val)` 把 `val` 的低 M 位复制进来，M 是 N 与 `unsigned long long` 值表示（[[g:value-representation]]，[[basic.types]]）位数中较小的一个。N 更大时，其余位清零；N 更小时，高位被直接丢弃，不报告任何错误。

这个构造函数不是 explicit 的，所以任何整数都能隐式转换为 `bitset`。`std::bitset<8> b = -1;` 是合法的：`-1` 先转换为 `ULLONG_MAX`，再取低 8 位，结果 8 位全为 1。

### 从字符串构造（¶3–9）

三个字符串构造函数都是 explicit 的：

1. `bitset(const basic_string<charT, traits, Allocator>& str, pos = 0, n = npos, zero = '0', one = '1')`
2. `bitset(basic_string_view<charT, traits> str, pos = 0, n = npos, zero = '0', one = '1')` {{c++26}}（[[P2697R1]]）
3. `bitset(const charT* str, n = npos, zero = '0', one = '1')`

<div class="compare" markdown="1">

```cpp run ok
#include <bitset>
std::bitset<8> a = 5;
// OK：整数构造函数不是 explicit
int main() {}
```

```cpp run error
#include <bitset>
std::bitset<8> b = "101";
// error: 字符串构造函数是 explicit
```

</div>

前两个共用一套规则：

- ¶3 有效长度 `rlen` 是 `n` 和 `str.size() - pos` 中较小的一个；只初始化前 M 位，M 是 N 和 `rlen` 中较小的一个。
- ¶4 从 `pos` 开始的字符，等于 `zero` 的对应 0，否则对应 1。位置 `pos + M - 1` 的字符对应 bit 0，往左依次对应更高的位。
- ¶5 M 小于 N 时，其余位清零。
- ¶6 字符用 `traits::eq` 比较。
- ¶7 `pos > str.size()` 时抛出 `out_of_range`；`rlen` 个字符中有任何一个既不是 `zero` 也不是 `one` 时，抛出 `invalid_argument`。

¶4 说不等于 `zero` 就是 1，但 ¶7 已经保证这 `rlen` 个字符只能是 `zero` 或 `one`，所以不会把其他字符当成 1。

¶7 检查全部 `rlen` 个字符，¶3 却只使用前 M 个。字符串比 N 长时，用的是左边的 N 个字符，右边多出的字符被丢弃，但仍然必须合法。所以 `bitset<8>("1111000011")` 的结果是 `11110000`，而不是保留低 8 位的 `11000011`，这与整数构造的截断方向相反。

¶8–¶9 `const charT*` 版本的 *Constraints* 要求 `charT` 不是数组类型，并且是平凡可复制、标准布局、可平凡默认构造的类型，也就是像字符的类型。它的效果规定为先构造一个 `basic_string_view`，再委托给第 2 个构造函数。

```cpp run ok
#include <bitset>
#include <cstdio>
#include <stdexcept>
#include <string>
#include <string_view>

int main() {
  std::bitset<8> s(std::string_view("xx101"), 2);  // 从 pos = 2 开始
  std::printf("%s\n", s.to_string().c_str());      // 00000101
  std::bitset<8> trunc("1111000011");              // 取左边 8 个字符
  std::printf("%s\n", trunc.to_string().c_str());  // 11110000
  try { std::bitset<8> bad("10201"); }
  catch (const std::invalid_argument&) { std::puts("invalid_argument"); }
  try { std::bitset<8> bad(std::string("101"), 4); }
  catch (const std::out_of_range&) { std::puts("out_of_range"); }
}
```

### 三类错误（[template.bitset.general] ¶13）

¶13 本节的函数可能报告三类错误，各对应一种异常：*invalid-argument* 对应 `invalid_argument`，*out-of-range* 对应 `out_of_range`，*overflow* 对应 `overflow_error`。各函数的 *Throws* 用的就是这三种异常。

## 代理类 `reference` [template.bitset.general]

```cpp run ok
#include <bitset>
#include <cassert>
#include <type_traits>

int main() {
  std::bitset<8> b;
  auto r = b[3];   // bitset<8>::reference，不是 bool
  static_assert(!std::is_same_v<decltype(r), bool>);
  r = true;        // 改的是 b
  assert(b.test(3));

  b[0] = true;
  swap(b[0], b[1]);   // ADL 找到 reference 的友元 swap
  assert(!b[0] && b[1]);
}
```

C++ 中最小的可寻址单位是字节（[[intro.memory]]），没有指向单个位的引用，所以非 const 的 `operator[]` 不能返回 `bool&`。它返回一个**代理对象**（[[g:proxy-reference]]），类型是 `bitset<N>::reference`，内部通常记录位在哪个字里以及对应的掩码。¶3 说它是一个模拟单个位的引用的类。

它的成员对应一个引用应有的操作：

| 操作 | 段落 | 效果 |
|---|---|---|
| 复制构造 | ¶4 | 新代理指向同一位 |
| 析构 | ¶5 | 什么也不做 |
| `operator=(bool)`、`operator=(const reference&)`、`operator=(bool) const` | ¶6–7 | 按 `bool(x)` 置位或清零，返回 `*this`；第二个支持 `b[i] = b[j]` |
| `operator bool()` | ¶8 | 读出该位 |
| `operator~()` | ¶9 | 返回 `!bool(*this)`，类型是 `bool`，不修改位 |
| 三个友元 `swap` | ¶10 | 交换两个代理所指的位，或者代理与一个 `bool&` |
| `flip()` | ¶11–12 | 等价于 `*this = !*this` |

const 限定的赋值运算符改的是代理所指的位，代理本身不变，就像 `int* const p` 也能写 `*p = 1`。有了它，`const reference` 也可以被赋值，`vector<bool>::reference` 有同样的成员。

`reference` 没有默认构造函数，代理必须指向某一位才有意义。`swap` 是友元，只能通过实参依赖查找（[[basic.lookup.argdep]]）找到，所以要写不加限定的 `swap(b[0], b[1])`。标准中通用的 `std::swap` 要求左值，不接受 `b[0]` 这样的纯右值；libc++ 在 `std` 命名空间中额外提供了代理的 `swap`，所以 `std::swap(b[0], b[1])` 在 libc++ 上也能编译，但这不是标准保证的。

!!! pitfall "`auto` 推导出的是代理，不是 `bool`"
    `auto r = b[3];` 中 `r` 的类型是 `bitset<8>::reference`，之后 `r = true` 会修改 `b`。如果 `b` 先于 `r` 被销毁，`r` 就悬垂了。需要一个独立的布尔值时，写 `bool r = b[3];` 或 `auto r = b.test(3);`。`vector<bool>` 有同样的问题。

## 成员函数 [bitset.members]

### 整体位运算和移位（¶1–12）

¶1–¶6 `&=`、`|=`、`^=` 逐位运算。¶7–¶10 `<<=` 把位置 I 的新值取自原来的 I − pos，`>>=` 取自 I + pos，超出范围的补 0。¶11–¶12 `<<`、`>>` 先复制再做复合赋值。这些函数都是 `noexcept` 的。

与内建整数的移位（[[expr.shift]]）不同，移位量不小于 N 并不是 UB。¶7.1 和 ¶9.1 直接规定这时新值为 0，所以 `b << 1000` 是合法的，结果全为 0；而对 32 位的 `unsigned`，`1u << 32` 是未定义行为。

### `set`、`reset`、`flip`（¶13–29）

不带参数的版本作用于所有位，是 `noexcept` 的。带 `pos` 的版本在 `pos` 不是有效位置时抛出 `out_of_range`（¶17、¶22、¶29），因此没有标 `noexcept`。¶23–¶24 `operator~()` 返回所有位切换后的副本。

### `operator[]` 与 `test`（¶30–36、¶46–47）

| 访问方式 | 越界时 |
|---|---|
| `b.test(pos)` | 抛出 `out_of_range`（¶47） |
| `b.set(pos)`、`b.reset(pos)`、`b.flip(pos)` | 抛出 `out_of_range` |
| `b[pos]` | 加固实现中终止程序，其他实现中是 {{ub}} |

¶30、¶33 两个 `operator[]` 的加固前置条件都是 `pos < size()`，¶32、¶35 又规定它们不抛出任何异常。所以 `operator[]` 越界永远不会抛异常，它与 `test` 的关系类似于 `vector` 的 `operator[]` 与 `at`。libc++ 在启用加固模式时检查这个条件。

¶31 const 版本返回 `bool`。¶34 非 const 版本返回的代理满足 `(*this)[pos] == this->test(pos)`，并且 `(*this)[pos] = val` 等价于 `this->set(pos, val)`。

!!! lawyer "写一个位就是写整个 bitset（¶36）"
    判断数据竞争时（[[intro.multithread]]），经由 `operator[]` 返回的代理进行的读或写，都可能访问或修改整个 `bitset`。所以两个线程分别写同一个 bitset 的 `b[0]` 和 `b[1]`，即使位置不同，也构成数据竞争，行为未定义。原因在于修改一位需要对整个字做读、改、写。`vector<T>` 的不同元素可以并发修改，`vector<bool>` 则同样例外（[[container.requirements.dataraces]]）。

### 转换为整数和字符串（¶37–42）

¶37–¶40 `to_ulong()` 和 `to_ullong()` 返回 ¶2 定义的整数值。这个值不能用目标类型表示时，抛出 `overflow_error`。判断依据是值而不是 N：`bitset<100>` 只要高于 bit 63 的位全为 0，`to_ullong()` 就能正常返回。

```cpp run ok
#include <bitset>
#include <cstdio>
#include <stdexcept>

int main() {
  std::bitset<100> small(42);
  std::printf("%llu\n", small.to_ullong());   // 42
  std::bitset<100> big;
  big.set(70);
  try { (void)big.to_ullong(); }
  catch (const std::overflow_error&) { std::puts("overflow_error"); }
}
```

¶41–¶42 `to_string(zero, one)` 构造一个长度恰为 N 的字符串，位置 N−1 的字符对应 bit 0。方向与字符串构造函数一致，所以 `bitset<N>(b.to_string()) == b` 总是成立。

### 查询（¶43–50）

¶43 `count()` 返回置位的个数，¶44 `size()` 返回 N，¶45 `operator==` 逐位比较，¶46 `test(pos)` 读一位。¶48–¶50 `all()`、`any()`、`none()` 分别是 `count() == size()`、`count() != 0`、`count() == 0`。

`operator!=` 不在概要中，C++20 起由 `==` 的重写候选提供（[[over.match.oper]]）。`bitset` 没有 `operator<`，也没有迭代器，不能直接作为 `std::set` 的键，也不能用于范围 `for`。

`bitset<0>` 是合法的：`size()` 为 0，`all()` 和 `none()` 都为真，`to_ullong()` 返回 0。

## 哈希与非成员运算符

[bitset.hash] ¶1 `hash<bitset<N>>` 是启用的特化（[[unord.hash]]），所以 `bitset` 可以直接作为 `unordered_set` 和 `unordered_map` 的键。哈希值是什么，标准没有规定。

[bitset.operators] ¶1–¶3 `&`、`|`、`^` 复制 `lhs` 后做复合赋值。它们是函数模板，两个参数都是 `bitset<N>`。模板实参推导不考虑用户定义的转换（[[temp.deduct.call]]），所以 `b & 1` 无法推导出 N，不能编译，要写成 `b & std::bitset<8>(1)`。

¶4–¶7 `operator>>` 是一个格式化输入函数，最多提取 N 个字符。遇到文件结束，或者下一个字符既不是 `widen('0')` 也不是 `widen('1')` 时停止，那个字符不被提取。然后执行 `x = bitset<N>(str)`。如果 N 大于 0 却一个字符也没有读到，设置 `failbit`。

¶8 `operator<<` 输出 `to_string` 的结果，其中 `'0'` 和 `'1'` 用流的 locale 的 `ctype` 加宽。

## 在常量求值中使用

C++11 起，默认构造、整数构造、const `operator[]` 和 `size()` 就是 `constexpr` 的。C++23 的 [[P2417R2]] 把其余成员，包括字符串构造、`to_string`、`to_ulong` 和代理 `reference` 的操作，都改成了 `constexpr`，特性测试宏 `__cpp_lib_constexpr_bitset` 为 `202207L`。仍然不是 `constexpr` 的只有流运算符和 `hash`。

```cpp run ok
#include <bitset>

constexpr std::bitset<16> make() {
  std::bitset<16> b("1010");   // C++23 起可在常量求值中使用
  b[15] = true;                // 代理赋值
  b <<= 1;                     // bit 15 被移出
  return b.flip(0);
}
static_assert(make().to_ulong() == 0b10101);
static_assert(std::bitset<8>(-1).count() == 8);

int main() {}
```

会抛出异常的路径不能出现在常量表达式中（[[expr.const]]），所以非法输入会在编译期被发现：

```cpp run error
#include <bitset>
constexpr std::bitset<8> bad("1012");
// error: 构造函数要抛出 invalid_argument，不是常量表达式
```

!!! impl "libc++ 的实现"
    libc++ 把存储放在私有基类 `__bitset<字数, N>` 中，以 `size_t` 为一个字，并对 0 个字和 1 个字的情况做了特化。在 64 位平台上，`bitset<64>` 就是一个 `size_t`，各种操作都是单条整数指令。代理 `reference` 与 `vector<bool>` 共用模板 `__bit_reference`，所以两者的行为几乎一致。`hash` 在单字时直接返回存储的字，多字时把各字异或起来。

## `bitset` 与 `vector<bool>`

| | `bitset<N>` | `vector<bool>`（[[vector.bool]]） |
|---|---|---|
| 位数 | 编译期常量 | 运行期确定，可增长 |
| 存储 | 在对象内部，不分配内存 | 经分配器在堆上 |
| 常量求值 | C++23 起几乎全部 | C++20 起（分配必须在求值结束前释放） |
| 迭代器 | 无 | 有（代理迭代器） |
| 整体位运算 | `&`、`|`、`^`、`~`、`<<`、`>>` | 只有 `flip()` |
| 与整数、字符串互转 | 有 | 无 |
| 越界访问 | `test` 抛异常，`[]` 是加固前置条件 | `at` 抛异常，`[]` 是加固前置条件 |

位数固定、需要整体运算或与整数互转时用 `bitset`；位数到运行时才知道时用 `vector<bool>`。

## 思考题

!!! question "思考题 1"
    `std::bitset<4>("101100")` 和 `std::bitset<4>(0b101100)` 的值分别是什么？为什么不一样？

<details markdown="1">
<summary>答案</summary>

字符串版本：`rlen = 6`，M = min(4, 6) = 4，使用前 4 个字符 `"1011"`，其中最后一个字符对应 bit 0，结果是 `1011`（[bitset.cons] ¶3–4）。

整数版本：取 `val` 的低 4 位（¶2），`0b101100` 的低 4 位是 `1100`。

字符串截断保留左端，也就是高位一端的字符；整数截断保留低位。方向相反。
</details>

!!! question "思考题 2"
    两个线程分别执行 `b[0] = true;` 和 `b.set(1);`，`b` 是同一个 `std::bitset<64>`。有数据竞争吗？

<details markdown="1">
<summary>答案</summary>

有。[bitset.members] ¶36 规定经由代理的写可能修改整个 bitset，`set(1)` 也修改 `b`，两者之间没有同步，按 [[intro.multithread]] 构成数据竞争，行为未定义。如果两个线程写的是两个不同的 `bitset` 对象，就没有冲突。
</details>

!!! question "思考题 3"
    为什么 `b & std::bitset<8>(1)` 能编译，`b & 1` 却不能？

<details markdown="1">
<summary>答案</summary>

非成员 `operator&` 的声明是 `template<size_t N> bitset<N> operator&(const bitset<N>&, const bitset<N>&)`。对 `b & 1`，第二个实参 `int` 无法推导出 N，推导时也不考虑经由整数构造函数的隐式转换（[[temp.deduct.call]]），于是这个模板不可行，也没有别的候选，程序非良构。两边都是 `bitset<8>` 时推导成功。
</details>
