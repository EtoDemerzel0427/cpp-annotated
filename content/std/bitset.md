---
title: 位集
summary: std::bitset<N>——编译期定长的位序列；bit 0 是最低位、字符串最右边的字符对应 bit 0；带范围检查的成员抛 out_of_range，字符串构造抛 invalid_argument，to_ulong/to_ullong 溢出抛 overflow_error；C++23 起几乎全部 constexpr，C++26 可从 string_view 构造
status: draft
covers: *
papers: P2417R2, P2697R1
related: bit, vector.bool, unord.hash, structure.specifications, intro.multithread, basic.types, expr.const
tags: 标准库, bitset, 代理引用, constexpr
updated: 2026-10-18
---

`std::bitset<N>` 解决的问题很朴素：**位数在编译期就已知**的一串标志位，想按位置读写、整体做与/或/异或/移位、统计置位个数、和整数或 `"0101"` 这样的字符串互相转换。它和 `std::vector<bool>` 的根本区别是 **N 是模板实参**：没有分配器、没有动态增长、对象大小固定（典型实现是 `ceil(N / 机器字位数)` 个字），因此可以整体 `constexpr`、可以放进共享内存、拷贝就是拷贝几个字。

读本节需要先熟悉库规格的"法律元素"——*Constraints*、*Mandates*、*Preconditions*、*Hardened preconditions*、*Throws* 等各自的后果，见 [[structure.specifications]]。本节的子条款：

| 子条款 | 内容 |
|---|---|
| [bitset.syn] | `<bitset>` 概要：类模板与 `&`、`|`、`^`、`>>`、`<<` 五个非成员运算符 |
| [template.bitset.general] | 类定义、位值映射、代理类 `reference`、三类错误 |
| [bitset.cons] | 构造函数：默认、`unsigned long long`、`basic_string`、`basic_string_view`、`const charT*` |
| [bitset.members] | 位运算、`set`/`reset`/`flip`、`operator[]`、`to_ulong`/`to_ullong`/`to_string`、观察函数 |
| [bitset.hash] | `hash<bitset<N>>` |
| [bitset.operators] | 非成员 `&`、`|`、`^` 与流输入输出 |

## 概要（[bitset.syn]）

¶1 只说一句话：`<bitset>` 定义一个类模板和若干相关函数，用于表示和操作**定长**位序列。概要里值得注意的只有两点：

- 它 `#include <string>` 和 `<iosfwd>`——因为 `to_string` 返回 `basic_string`、流运算符要用到 `basic_istream`/`basic_ostream`。也就是说 `<bitset>` 是个**不算轻**的头文件，并且**不是** freestanding 的（对比 [[bit]] 的 `<bit>` 整个是 freestanding）。
- 三个非成员位运算符 `&`、`|`、`^` 都是 `constexpr` 且 `noexcept`；流运算符则既非 `constexpr` 也非 `noexcept`。

## 位的编号：bit 0 是最低位（[template.bitset.general] ¶1–2）

¶2 是理解整个 `bitset` 的钥匙：每一位有一个非负的位置 `pos`；与整数互相转换时，位置 `pos` 对应**位值**（*bit value*）`1 << pos`，多位对应的整数值是各位位值之和。

!!! std
    When converting between an object of type bitset<N> and a value of some integral type, bit position pos corresponds to the bit value 1 << pos.

    即：bit 0 就是整数的最低有效位（LSB），bit N−1 是最高位。这与 CPU 字节序无关——它是**数值**意义上的映射，不是内存布局意义上的映射。标准从未规定 `bitset` 内部用什么存储。

而在与**字符串**互转时（[bitset.cons] ¶4、[bitset.members] ¶41），规则是"字符串的最后一个字符对应 bit 0，往左依次增大"——也就是人类书写二进制数的习惯：`"0110"` 读作 6，`b[1]` 和 `b[2]` 是 1。

于是同一个 `bitset` 有两种"顺序"：`b[i]` 的下标顺序是从低位到高位，`to_string()` 的字符顺序是从高位到低位。初学者遍历 `to_string()` 的第 `i` 个字符并以为它就是 `b[i]`，是最常见的错误。

```cpp run title="bitset-order.cpp" ok
#include <bitset>
#include <cstdio>

int main() {
    std::bitset<8> b("00010110");        // 字符串最右边是 bit 0
    std::printf("%d %d %lu\n", (int)b[1], (int)b[0], b.to_ulong()); // 1 0 22
    std::bitset<4> t(0b1111'0101ULL);    // 只取低 4 位
    std::printf("%s\n", t.to_string().c_str());                     // 0101
}
```

¶1 中"切换"（*toggle*）一词也在这里定义：把 0 变 1、1 变 0；`flip` 和 `^=` 都用它表述。

## 代理类 `reference`（¶3–12）

C++ 没有"指向单个位的引用"——最小可寻址单位是字节（[[intro.memory]]）。所以非 const 的 `operator[]` 不能返回 `bool&`，只能返回一个**代理对象**（[[g:proxy-reference]]）：`bitset<N>::reference`，它内部通常保存"哪个字 + 哪个掩码"，¶3 称之为"模拟对单个位的引用的类"。

它的接口逐条对应一个真引用应有的操作：

| 操作 | 段落 | 语义 |
|---|---|---|
| 复制构造 | ¶4 | 新代理指向同一位（复制的是"引用"，不是位的值） |
| 析构 | ¶5 | 什么都不做 |
| `operator=(bool)`、`operator=(const reference&)` | ¶6–7 | 按 `bool(x)` 置位或清位，返回 `*this`；后者支持 `b[i] = b[j]` |
| `operator=(bool) const` | ¶6–7 | const 版本，同样修改所指的位 |
| `operator bool()` | ¶8 | 读出该位 |
| `operator~()` | ¶9 | 返回 `!bool(*this)`——注意返回的是 `bool`，不修改位 |
| `flip()` | ¶11–12 | 等价于 `*this = !*this` |
| 三个友元 `swap` | ¶10 | 交换两个代理所指的位，或代理与 `bool&` |

几个值得咀嚼的细节：

- **const 的赋值运算符**：`const reference& operator=(bool) const` 看似荒唐——给 const 对象赋值？但对代理而言，"代理本身不变、它所指向的位变了"恰恰是引用语义（`int* const p` 也能写 `*p = 1`）。有了它，`const bitset<N>::reference` 也能被赋值，这是让代理类型满足 `std::indirectly_writable` 一类概念所需要的（该概念要求 `const` 限定的结果也能被赋值）。libc++ 中这个 const 赋值运算符定义在 `__bit_reference` 里。
- **没有默认构造函数**：代理必须指向某一位才有意义。
- **swap 是友元**：`std::swap(b[0], b[1])` 不能工作（通用 `std::swap` 要求左值，而 `b[0]` 是 prvalue）；但不加限定的 `swap(b[0], b[1])` 通过 ADL（[[basic.lookup.argdep]]）找到这里的友元，可以工作。

!!! pitfall "auto 推导出的是代理，不是 bool"
    `auto r = b[3];` 中 `r` 的类型是 `bitset<8>::reference`，后续 `r = true` 会**修改 `b`**。如果 `b` 先于 `r` 被销毁，`r` 就是悬垂代理。想要一个独立的布尔值，写 `bool r = b[3];` 或 `auto r = b.test(3);`。`vector<bool>` 有完全相同的陷阱。

```cpp run title="bitset-proxy.cpp" ok
#include <bitset>
#include <type_traits>
#include <vector>

int main() {
    std::bitset<8> b;
    auto r = b[3];                      // r 是 bitset<8>::reference，不是 bool
    static_assert(!std::is_same_v<decltype(r), bool>);
    r = true;                           // 改的是 b 本身
    std::vector<bool> v(8);
    auto vr = v[3];                     // vector<bool>::reference：同一种代理
    vr = true;
    return (b.test(3) && v[3]) ? 0 : 1;
}
```

## 三类错误与对应异常（¶13）

¶13 把本节函数可能报告的错误归为三类，各自对应一种异常：*invalid-argument* → `invalid_argument`，*out-of-range* → `out_of_range`，*overflow* → `overflow_error`。这是标准库里少见的、把"错误类别"先抽象出来再映射到异常类型的写法，来自 C++98 时代。后面各函数的 *Throws* 元素就引用这三类。

## 构造函数（[bitset.cons]）

### 默认与整数构造（¶1–2）

- `bitset() noexcept`：全部清零。
- `bitset(unsigned long long val) noexcept`（**非 explicit**）：把 `val` 的低 M 位拷进来，M 是 `N` 与 `unsigned long long` 值表示（[[g:value-representation]]，[[basic.types]]）位数之较小者；N 更大时其余位清零。N 更小时**高位被静默截断**，没有任何异常。

因为它不是 `explicit`、参数又是 `unsigned long long`，任何整数都能隐式变成 `bitset`：`std::bitset<8> b = -1;` 合法——`-1` 先转换为 `ULLONG_MAX`，再截取低 8 位，结果 8 位全 1。

### 字符串构造（¶3–9）

三个字符串构造函数都是 `explicit` 的：

1. `const basic_string<charT, traits, Allocator>& str, pos = 0, n = npos, zero = '0', one = '1'`
2. {{c++26}} `basic_string_view<charT, traits> str, pos, n, zero, one`（[[P2697R1]]）
3. `const charT* str, n = npos, zero, one`

前两者共享 ¶3–7 的规格：

- ¶3：有效长度 `rlen = min(n, str.size() - pos)`；初始化前 `M = min(N, rlen)` 个位。
- ¶4：从 `pos` 开始的字符，等于 `zero` 则该位为 0，**否则**为 1；字符位置 `pos + M - 1` 对应 bit 0，往前依次对应更高位。
- ¶5：`M < N` 时其余位清零。
- ¶6：用 `traits::eq` 比较字符。
- ¶7 *Throws*：`pos > str.size()` 抛 `out_of_range`；**`rlen` 个字符**中任何一个既不是 `zero` 也不是 `one` 抛 `invalid_argument`。

这里有两个容易误读的地方：

- ¶4 说"不等于 `zero` 就是 1"，看起来像是任意字符都算 1；但 ¶7 先一步保证了被检查的 `rlen` 个字符只能是 `zero` 或 `one`，否则根本构造不出来。
- 检查的是 `rlen` 个字符，但只**使用**前 `M` 个。当字符串比 `N` 长时，用的是**左边**的 N 个字符（高位端），右边多余字符被丢弃但仍要合法。于是 `bitset<8>("1111000011")` 的结果是 `11110000`，而不是你可能以为的"保留最低 8 位" `11000011`——这与整数构造的截断方向正好相反。

`const charT*` 版本（¶8–9）在当前草案中带有 *Constraints*：`charT` 不是数组类型、是平凡可复制的、标准布局的、平凡默认可构造的——即"像字符的类型"（与 `basic_string` 对字符类型的要求一致）。由于这是 *Constraints*，不满足时该构造函数**不参与重载决议**，而不是硬错误。它的效果被规定为"如同"先构造 `basic_string_view` 再委托给 ②——这正是 C++26 引入 ② 后顺带对 ③ 的重新表述。

```cpp run title="bitset-ctor.cpp" ok
#include <bitset>
#include <cstdio>
#include <stdexcept>
#include <string>
#include <string_view>

int main() {
    std::bitset<8> s(std::string_view("xx101"), 2);       // C++26：从 pos=2 开始
    std::printf("%s\n", s.to_string().c_str());           // 00000101
    std::bitset<8> trunc("1111000011");                   // M = 8：取左边 8 个字符
    std::printf("%s\n", trunc.to_string().c_str());       // 11110000
    try { std::bitset<8> bad("10201"); }
    catch (const std::invalid_argument&) { std::puts("invalid_argument"); }
    try { std::bitset<8> bad(std::string("101"), 4); }
    catch (const std::out_of_range&) { std::puts("out_of_range"); }
}
```

```cpp run title="bitset-explicit.cpp" error
#include <bitset>
std::bitset<8> a = 5;        // OK：unsigned long long 构造函数不是 explicit
std::bitset<8> b = "101";    // error: const charT* 构造函数是 explicit
```

## 成员函数（[bitset.members]）

### 整体位运算与移位（¶1–12）

`&=`、`|=`、`^=` 逐位操作（¶1–6）；`<<=`/`>>=`（¶7–10）按"位置 I 的新值取自 I−pos / I+pos，越界补零"定义，`<<`/`>>` 是先复制再复合赋值（¶11–12）。全部 `noexcept`。

与内建整数的移位（[[expr.shift]]）对比，有一个重要差别：**`pos >= N` 不是 UB**。¶7.1 / ¶9.1 直接规定越界位补零，所以 `b << 1000` 合法，结果全零。而 `1u << 32` 对 32 位 `unsigned` 是未定义行为。

### `set`/`reset`/`flip`（¶13–29）

无参版本作用于全部位，`noexcept`；带 `pos` 的版本在 `pos` 不是有效位置时 **抛 `out_of_range`**（¶17、¶22、¶29）。注意这些带参版本没有标 `noexcept`——检查是规格的一部分，不是可选的调试辅助。`operator~()`（¶23–24）返回翻转后的副本。

### `operator[]`：硬化前置条件，而非异常（¶30–36）

与 `test(pos)` 抛异常不同，两个 `operator[]` 用的是 **硬化前置条件**（*Hardened preconditions*）：`pos < size()`。按 [[structure.specifications]]：

- 在**硬化实现**（[[g:hardened-implementation]]）中，违反它是一次契约违规，以终止语义检查，在任何可观察副作用之前就终止；
- 在非硬化实现中，违反它是 {{ub}}。

¶32、¶35 还明说 *Throws: Nothing*——所以 `operator[]` 越界**永远不会**抛异常。libc++ 用 `_LIBCPP_ASSERT_VALID_ELEMENT_ACCESS(__p < _Size, ...)` 实现这一检查（`<bitset>`），在启用硬化模式时生效。

| 访问方式 | 越界时 |
|---|---|
| `b.test(pos)` | 抛 `out_of_range`（¶47） |
| `b.set(pos)` / `reset(pos)` / `flip(pos)` | 抛 `out_of_range` |
| `b[pos]` | 硬化实现：契约违规终止；否则 UB |

¶34 规定非 const `operator[]` 返回的代理满足 `(*this)[pos] == this->test(pos)`，且 `(*this)[pos] = val` 等价于 `this->set(pos, val)`。

!!! lawyer "¶36：写一个位就是写整个 bitset"
    *Remarks*：判断数据竞争（[[intro.multithread]]）时，经由返回的代理进行的任何访问或更新，都**潜在地**访问或修改**整个** `bitset`。所以两个线程分别写 `b[0]` 和 `b[1]` 构成数据竞争（{{ub}}），哪怕它们是"不同的位"。这与 `std::vector<T>` 的不同元素可以并发修改不同（`vector<bool>` 则同样例外，见 [[container.requirements.dataraces]]）。物理原因显而易见：改一位要对整个字做读-改-写。

const 版本的 `operator[]` 返回 `bool`。libc++ 历史上让它返回一个 `__bit_const_reference` 代理（不符合标准），现已改为返回 `bool`，并保留宏 `_LIBCPP_DEPRECATED_ABI_BITSET_CONST_SUBSCRIPT_RETURN_REF` 作为过渡期的退出开关（见 `<bitset>` 中的 `TODO(LLVM 24)` 注释）。

### 转换为整数与字符串（¶37–42）

`to_ulong()`/`to_ullong()` 返回 ¶2 定义的整数值 x；当 x **无法用目标类型表示**时抛 `overflow_error`（¶38、¶40）。关键在于判据是**值**而不是 N：`bitset<100>` 只要高于 64 的位全为零，`to_ullong()` 就完全合法。

`to_string(zero, one)` 构造一个长度恰为 N 的字符串，字符位置 N−1 对应 bit 0（¶41）——与字符串构造函数的方向一致，所以 `bitset<N>(b.to_string()) == b` 总成立。

```cpp run title="bitset-overflow.cpp" ok
#include <bitset>
#include <cstdio>
#include <stdexcept>

int main() {
    std::bitset<100> small(42);
    std::printf("%llu\n", small.to_ullong());   // 42：值放得下就行
    std::bitset<100> big;
    big.set(70);
    try { (void)big.to_ullong(); }
    catch (const std::overflow_error&) { std::puts("overflow_error"); }
}
```

### 观察函数（¶43–50）

`count()`（置位个数）、`size()`（返回 N）、`operator==`、`test(pos)`（越界抛异常）、`all()`/`any()`/`none()`（分别是 `count() == size()`、`count() != 0`、`count() == 0`）。`operator!=` 不在概要中：C++20 起由 `==` 的重写候选（[[over.match.oper]]）提供。注意 `bitset` **没有** `operator<`，也没有迭代器——不能直接用于 `std::set` 或 range-for。

!!! note "N == 0"
    `bitset<0>` 是合法的：`size()` 为 0，`all()` 为 true（空集上的全称命题），`none()` 为 true，`to_ullong()` 返回 0。libc++ 为它提供了专门的 `__bitset<0, 0>` 特化。

## 哈希（[bitset.hash]）

¶1 只说一句："该特化是启用的（enabled）"——即 `hash<bitset<N>>` 满足 [[unord.hash]] 对启用特化的全部要求，可以直接做 `unordered_set` / `unordered_map` 的键。哈希值本身是未指明的。

## 非成员运算符（[bitset.operators]）

- ¶1–3：`&`、`|`、`^` 定义为复制 `lhs` 再做复合赋值。它们是**函数模板**、两个参数都是 `bitset<N>`，所以 `b & 1` 这样的混合运算**不会**通过隐式转换匹配——模板实参推导（[[temp.deduct.call]]）不考虑用户定义转换。
- ¶4–6 `operator>>`：一个格式化输入函数，最多提取 N 个字符；遇到 EOF 或下一个字符不是 `widen('0')`/`widen('1')` 时停止（不提取该字符）；然后 `x = bitset<N>(str)`。若 `N > 0` 却一个字符都没存下，置 `failbit`。
- ¶7–8 `operator<<`：输出 `to_string`，其中 `'0'`/`'1'` 用流的 locale 的 `ctype` 扩宽。

## constexpr 化

C++11 时只有默认构造、整数构造、const `operator[]` 和 `size()` 是 `constexpr`。[[P2417R2]]（C++23，特性测试宏 `__cpp_lib_constexpr_bitset` = `202207L`）把几乎所有成员——包括字符串构造、`to_string`、`to_ulong`、代理 `reference` 的操作——变成 `constexpr`。仍然不是 `constexpr` 的只有流运算符和 `hash`。

抛异常的路径在常量求值中会使表达式不是常量表达式（在常量求值内未被捕获的异常不能"逃出"）：

```cpp run title="bitset-constexpr.cpp" ok
#include <bitset>

constexpr std::bitset<16> make() {
    std::bitset<16> b("1010");          // C++23 起 constexpr
    b[15] = true;                       // 代理赋值也是 constexpr
    b <<= 1;                            // bit 15 被移出
    return b.flip(0);
}
static_assert(make().to_ulong() == 0b10101);
static_assert(std::bitset<8>(-1).count() == 8);   // -1 → ULLONG_MAX → 低 8 位全 1

int main() {}
```

```cpp run title="bitset-constexpr-throw.cpp" error
#include <bitset>
constexpr std::bitset<8> bad("1012");   // error: 构造函数会抛 invalid_argument，不是常量表达式
```

## 实现视角（libc++）

libc++ 的 `<bitset>` 把存储放在私有基类 `__bitset<字数, N>` 中，按 `size_t` 为字分块，并对"0 个字"和"1 个字"做了特化——`bitset<64>` 在 64 位平台上就是一个 `size_t`，所有操作都是单条整数指令。代理 `reference` 是 `__bit_reference<__bitset>`，与 `vector<bool>` **复用同一个模板**（`<__bit_reference>`），这也解释了二者行为的高度一致。`count()` 在 Clang 下对单字情形直接用 `__builtin_popcountg`（先截成 `unsigned _BitInt(N)` 以忽略未用的高位）；`hash` 对单字特化直接返回存储的字，多字时把各字异或起来——哈希质量很一般，但标准只要求"启用"。

## `bitset` vs `vector<bool>`

| | `bitset<N>` | `vector<bool>`（[[vector.bool]]） |
|---|---|---|
| 位数 | 编译期常量 | 运行期，可增长 |
| 存储 | 对象内部，无堆分配 | 经分配器在堆上 |
| `constexpr` | C++23 起几乎全部 | C++20 起（瞬态分配） |
| 迭代器 | 无 | 有（代理迭代器） |
| 整体位运算 | `& | ^ ~ << >>` | 只有 `flip()` |
| 与整数/字符串互转 | 有 | 无 |
| 越界访问 | `test` 抛异常；`[]` 硬化前置条件 | `at` 抛异常；`[]` 硬化前置条件 |
| 是否"容器" | 不是 | 名义上是，但不满足容器要求（`operator[]` 不返回 `bool&`） |

经验法则：位数固定、需要整体运算或整数转换时用 `bitset`；位数运行时才知道时用 `vector<bool>`（或第三方动态位集）。

## 思考题

!!! question "1"
    `std::bitset<4>("101100")` 和 `std::bitset<4>(0b101100)` 的值分别是什么？为什么不一样？

<details markdown="1">
<summary>展开查看答案与解析</summary>

字符串版本：`rlen = 6`，`M = min(4, 6) = 4`，使用从 `pos` 开始的前 4 个字符 `"1011"`，字符位置 `pos + M − 1`（即 `"1011"` 的最后一个字符）对应 bit 0，结果是 `1011`（[bitset.cons] ¶3–4）。

整数版本：取 `val` 的低 4 位（¶2），`0b101100` 的低 4 位是 `1100`。

字符串截断保留的是左端（高位端）字符，整数截断保留的是低位——方向相反。
</details>

!!! question "2"
    两个线程分别执行 `b[0] = true;` 和 `b.set(1);`，其中 `b` 是同一个 `std::bitset<64>`。这段代码有数据竞争吗？如果把 `b[0] = true` 换成对另一个 `bitset` 的写入呢？

<details markdown="1">
<summary>展开查看答案与解析</summary>

有。[bitset.members] ¶36 规定经由代理的更新"潜在地修改整个底层 bitset"，而 `set(1)` 显然修改 `b`；两者都没有同步，按 [[intro.multithread]] 构成数据竞争，行为未定义。换成两个不同的 `bitset` 对象则没有冲突。
</details>

!!! question "3"
    为什么 `std::bitset<8> b; b[0] & true;` 能编译，而 `b & std::bitset<8>(1)` 可以、`b & 1` 却不行？

<details markdown="1">
<summary>展开查看答案与解析</summary>

`b[0]` 是 `reference`，经其 `operator bool()` 转换后可参与内建 `&`。而非成员 `operator&` 是 `template<size_t N> bitset<N> operator&(const bitset<N>&, const bitset<N>&)`，`b & 1` 时第二个参数 `int` 无法推导出 `N`，模板实参推导失败（推导不考虑隐式转换，[[temp.deduct.call]]），也没有其他可行候选，于是非良构。写成 `b & std::bitset<8>(1)` 或 `b & decltype(b)(1)` 即可。
</details>

## 小结

| 主题 | 要点 |
|---|---|
| 位编号 | bit `pos` ↔ 位值 `1 << pos`；字符串最右字符是 bit 0 |
| 整数构造 | 非 explicit、`noexcept`，静默截断到低 N 位 |
| 字符串构造 | explicit；`pos > size()` → `out_of_range`；非法字符 → `invalid_argument`；过长时保留左端；C++26 新增 `string_view` 版本 |
| `test`/`set(pos)`/... | 越界抛 `out_of_range` |
| `operator[]` | 硬化前置条件，*Throws: Nothing*；非 const 版返回代理 `reference` |
| `to_ulong`/`to_ullong` | 值放不下时抛 `overflow_error`，与 N 无关 |
| 移位 | `pos >= N` 合法，补零（与内建移位不同） |
| 并发 | 经代理写任一位 = 写整个 bitset |
| constexpr | C++23（P2417R2）起几乎全部，流运算符与 hash 除外 |
