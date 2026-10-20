---
title: 测试、sanitizer 与模糊测试
summary: 怎样测试 C++ 代码才能抓到 UB 和数据竞争：最小的测试框架，编译期测试与编译失败测试，ASan、LSan、UBSan、TSan 各抓什么、开销多大、哪些不能组合，测试中的标准库加固，CI 里的构建矩阵，libFuzzer 模糊测试，基于性质的测试，llvm-cov 覆盖率，以及同一组测试在 -O0 与 -O2 下的不同结果。
group: 工程实践
status: draft
order: 135
since: c++98
papers: P3471, P0543R3
related: defns.undefined, expr.pre, intro.races, basic.indet, expr.const.core, dcl.pre, expr.prim.req, temp.deduct, dcl.spec.auto, string.view, structure.specifications, intro.compliance, numeric.sat, topics/undefined-behavior, topics/dangling-references, topics/memory-model, topics/arithmetic, topics/concepts, topics/compile-time-programming, toolchain/cmake, toolchain/debugging, toolchain/static-analysis
tags: 工具链, 测试, sanitizer, ASan, UBSan, TSan, 模糊测试, 覆盖率, 加固
updated: 2026-10-19
---

!!! tldr
    - 普通的单元测试只检查结果对不对。UB 和数据竞争常常让错误的程序在测试里给出正确的结果，所以测试要在 sanitizer 构建里再跑一遍，sanitizer 才是判断 UB 的那一方。
    - UBSan 默认报告后继续运行，退出码仍是 0。测试里要加 `-fno-sanitize-recover=undefined`，否则 UB 报告只是一行没人看的日志。
    - ASan 与 TSan 不能放进同一个构建，macOS 上没有 MSan。CI 至少需要 ASan+UBSan、TSan、普通 `-O2` 三个配置。
    - 手写的用例通常想不到恶意或畸形的输入。libFuzzer 在本机不到一秒就找到了一个所有单元测试和 100% 行覆盖率都没发现的越界读。
    - 编译期测试（`static_assert` 加 `constexpr`）和编译失败测试（概念加 `requires` 表达式）在编译时就能拦住一部分错误，但它们也有盲区。

!!! note "实验环境"
    Apple M2 Pro，macOS，Homebrew Clang 23.1.3（libc++），CMake 3.29.3，Ninja 1.12.1。`/opt/homebrew/opt/llvm/bin` 放在 `PATH` 最前面，这样 sanitizer 运行时能找到 `llvm-symbolizer`；Anaconda 的旧版 `ld` 从 `PATH` 中去掉了（见 [[toolchain/compilation-pipeline]]）。调试信息用 `-gdwarf-4`，原因见 [[topics/dangling-references]]。本机没有安装 GoogleTest、Catch2、doctest，下文的测试用自己写的几行代码完成。报告中的长调用栈有删节。

## 一个解析器和它的测试

下文所有实验都围绕一个小函数：把 `a=1;b=2` 这样的文本解析成键值对，反斜杠转义下一个字符。

```cpp title="kv.hpp"
#pragma once
#include <optional>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

using KV = std::vector<std::pair<std::string, std::string>>;

// "a=1;b=x\;y" -> {"a","1"}, {"b","x;y"}
std::optional<KV> parse_kv(std::string_view s);
```

```cpp title="kv.cpp"
#include "kv.hpp"

std::optional<KV> parse_kv(std::string_view s) {
  KV out;
  std::string key, val;
  std::string* cur = &key;
  for (std::size_t i = 0; i < s.size(); ++i) {
    char c = s[i];
    if (c == '\\') {              // 转义：下一个字符原样保留
      cur->push_back(s[++i]);
      continue;
    }
    if (c == '=' && cur == &key) { cur = &val; continue; }
    if (c == ';') {
      if (cur != &val) return std::nullopt;
      out.emplace_back(std::move(key), std::move(val));
      key.clear(); val.clear(); cur = &key;
      continue;
    }
    cur->push_back(c);
  }
  if (cur == &val) out.emplace_back(std::move(key), std::move(val));
  else if (!key.empty()) return std::nullopt;
  return out;
}
```

这段代码有一个错误：输入以单个反斜杠结尾时，`s[++i]` 的下标等于 `s.size()`。后文会看到，哪些手段能发现它，哪些不能。

### 不依赖框架的测试

测试框架做的事情，核心只有三件：检查一个条件，失败时报告位置，最后用退出码告诉构建系统成败。C++20 的 `std::source_location` 让这件事不再需要宏来取行号，宏只用来把表达式变成字符串：

```cpp title="check.hpp"
#pragma once
#include <cstdio>
#include <source_location>

inline int g_failures = 0;

inline void check(bool ok, const char* expr,
                  std::source_location loc =
                      std::source_location::current()) {
  if (!ok) {
    ++g_failures;
    std::printf("%s:%u: CHECK failed: %s\n",
                loc.file_name(), loc.line(), expr);
  }
}
#define CHECK(...) check(static_cast<bool>(__VA_ARGS__), #__VA_ARGS__)
```

默认实参 `std::source_location::current()` 在调用处求值，所以报告的是 `CHECK` 所在的行。宏写成可变参数，是为了让 `CHECK(f<a, b>())` 这种含逗号的表达式不被拆成两个宏实参。

```cpp title="kv_test.cpp"
#include "check.hpp"
#include "kv.hpp"

int main() {
  auto r = parse_kv("a=1;b=2");
  CHECK(r && r->size() == 2);
  CHECK((*r)[1] == KV::value_type{"b", "2"});

  auto e = parse_kv(R"(b=x\;y)");
  CHECK(e && (*e)[0].second == "x;y");

  CHECK(!parse_kv("novalue;"));
  CHECK(parse_kv("") && parse_kv("")->empty());
  CHECK(parse_kv("a=1")->size() == 2);       // 故意写错的用例

  std::printf("%s\n", g_failures ? "FAILED" : "OK");
  return g_failures != 0;
}
```

```text
$ clang++ -std=c++2c -Wall -Wextra -pedantic -g kv.cpp kv_test.cpp -o kv_test && ./kv_test
kv_test.cpp:14: CHECK failed: parse_kv("a=1")->size() == 2
FAILED
$ echo $?
1
```

CTest 只看退出码，非零就算失败（接入方式见 [[toolchain/cmake]]）。去掉故意写错的那一行，测试通过，而那个越界读仍然在代码里。

!!! note "测试框架"
    GoogleTest、Catch2、doctest 在这套机制上增加了测试注册（不必在 `main` 里手动调用）、按名字筛选、夹具、参数化、失败时打印两边的值、输出 JUnit XML 供 CI 展示。它们可以用 Homebrew 安装，或在 CMake 里用 `FetchContent` 拉取（见 [[toolchain/dependencies]]）。本机没有安装，这里不给出它们的输出。选哪一个对下文没有影响：sanitizer、模糊测试、覆盖率都作用在编译选项和运行时上，与断言写法无关。

## 编译期测试

### `static_assert` 与 `constexpr`

把 `parse_kv` 改成定义在头文件里的 `constexpr` 函数（`kvc.hpp`，函数体不变，只在前面加 `constexpr`），测试就可以在编译时运行。C++20 起 `std::string`、`std::vector` 可以在常量求值中分配内存，只要分配在求值结束前释放。

```cpp title="kvc_test.cpp"
#include "kvc.hpp"
static_assert(parse_kv("a=1;b=2")->size() == 2);
static_assert(parse_kv(R"(b=x\;y)")->at(0).second == "x;y");
static_assert(!parse_kv("novalue;"));
int main() {}
```

`static_assert` 的条件必须是常量表达式，值为假时声明失败，程序非良构（[[dcl.pre#13]]），实现必须拒绝它（[[intro.compliance.general#2]] ¶2.5）。更有用的是另一条规则：常量求值中出现核心语言 UB 时，表达式不是常量表达式（[[expr.const.core#2]]），所以编译期测试顺带检查了执行路径上的有符号溢出、越界、使用生命周期外的对象等。这一点的例子见 [[topics/undefined-behavior]]。

把结尾反斜杠的用例加进来，结果取决于标准库是否开启加固：

```cpp
static_assert(parse_kv(R"(a=1\)")->at(0).second == "1");
```

```text
$ clang++ -std=c++2c kvc_test.cpp
error: static assertion failed due to requirement 'parse_kv("a=1\\")->at(0).second == "1"'

$ clang++ -std=c++2c -D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_FAST kvc_test.cpp
error: static assertion expression is not an integral constant expression
.../c++/v1/string_view:417:12: note: subexpression not valid in a constant expression
  417 |     return _LIBCPP_ASSERT_VALID_ELEMENT_ACCESS(__pos < size(), "string_view[] index out of bounds"), __data_[__pos];
./kvc.hpp:19:22: note: in call to 's.operator[](4)'
```

第一次编译中，Clang 执行了越界的 `s[4]`，读到字面量末尾的 `'\0'`，于是 `second` 是两个字符的 `"1\0"`，断言只是因为值不对而失败。核心语言层面这次读取没有越界，`"a=1\\"` 这个数组确实有 5 个元素；违反的是 `string_view::operator[]` 的前置条件 `pos < size()`（[[string.view.access#1]]）。库 UB 在常量求值中是否被诊断是未指定的（[[expr.const.core#4]]），Clang 在这里没有诊断。开启加固后，前置条件变成了库里的一个检查，常量求值碰到它就失败，诊断直接指向 `s[++i]`。

!!! pitfall "编译期测试只覆盖它运行的那些实参"
    `static_assert` 证明的是：对这几个输入、在这条执行路径上没有核心语言 UB。它不检查别的输入，`if consteval` 分支在运行期可能走完全不同的代码，`reinterpret_cast` 和 `memcpy` 这类操作根本不能出现在常量求值里。它是一组跑得很早的单元测试，不是证明。

### 编译失败测试

有些接口的正确性在于拒绝错误的用法：不同单位的长度不能相加，`double` 不能隐式变成 `Meters`。这类性质要用**编译失败测试**来检查：断言某个表达式不能通过编译。用概念加 `requires` 表达式可以做到：

```cpp run title="units.cpp" ok
#include <type_traits>

struct Meters  { double v; };
struct Seconds { double v; };

constexpr Meters operator+(Meters a, Meters b) { return {a.v + b.v}; }

template <class T, class U>
concept addable = requires(T a, U b) { a + b; };

static_assert(addable<Meters, Meters>);
static_assert(!addable<Meters, Seconds>);       // 单位不同不能相加
static_assert(!addable<Meters, double>);        // 裸 double 也不行
static_assert(!std::is_convertible_v<double, Meters>);
static_assert((Meters{1} + Meters{2}).v == 3);

int main() {}
```

把模板实参代入 `requires` 表达式时，如果在[[g:immediate-context|直接语境]]里产生了无效的表达式，`requires` 表达式的值是 `false`，程序不会因此非良构（[[expr.prim.req#5]]）。所以 `!addable<Meters, Seconds>` 是一个本身能通过编译的编译失败测试。

两种写法看起来等价，结果不同：

<div class="compare" markdown="1">

```cpp ok
template <class T, class U>
concept addable =
  requires(T a, U b) { a + b; };

static_assert(!addable<Meters, Seconds>);
```

```cpp error
// 不在模板里：直接报错
static_assert(!requires(Meters m,
                        Seconds s) {
  m + s;
});
```

</div>

[[expr.prim.req#5]] 的注 1 说明了右边的情况：`requires` 表达式不出现在模板化实体的声明里时，其中的无效表达式让程序非良构。Clang 对右边报 `invalid operands to binary expression ('Meters' and 'Seconds')`。只有通过模板参数代入，失败才会被吸收成 `false`。

第二个陷阱是直接语境的边界。被测函数的返回类型是 `auto` 时，判断调用是否有效需要先实例化函数体来推导返回类型，函数体里的错误不在直接语境中（[[dcl.spec.auto.general#15]]，[[temp.deduct.general#8]]）：

<div class="compare" markdown="1">

```cpp error
template <class T>
auto scale(Meters m, T k) {
  return Meters{m.v * k};
}
template <class T>
concept scalable = requires(
    Meters m, T k) { scale(m, k); };

static_assert(!scalable<const char*>);
// 硬错误：函数体里 double * const char*
```

```cpp ok
template <class T>
  requires requires(double d, T k) {
    d * k;
  }
Meters scale(Meters m, T k) {
  return Meters{m.v * k};
}
template <class T>
concept scalable = requires(
    Meters m, T k) { scale(m, k); };

static_assert(!scalable<const char*>);
```

</div>

左边 Clang 报 `invalid operands to binary expression ('double' and 'const char *')`，注释链指向 `in instantiation of function template specialization 'scale<const char *>'`。编译失败测试能测到的，只是接口在声明中写明的约束。这正好也是它的价值：如果这个测试写不出来，说明接口没有把要求写在签名上，调用者也只能从函数体深处的错误信息里知道它（见 [[topics/concepts]]、[[toolchain/reading-compiler-errors|读懂编译错误]]）。

需要检查一段代码在约束之外的地方确实编译失败时（例如某个 `static_assert` 会触发），概念帮不上忙，只能在测试脚本里调用编译器，期待它以非零退出码结束。

## sanitizer：让 UB 在测试里现形

**sanitizer** 是编译器插桩加运行时库的组合：编译器在每次内存访问、算术运算或同步操作周围插入检查代码，链接时带上对应的运行时库，运行到违规操作时打印报告。它们是动态工具，只看实际执行到的路径。各工具检测范围的总表见 [[topics/undefined-behavior]]，这里关注测试时怎么用、各自的盲区在哪里。

### ASan：越界与释放后使用

**AddressSanitizer**（ASan，`-fsanitize=address`）在每个堆块、栈变量、全局变量周围放置不可访问的红区，并在释放后把内存标记为不可访问，每次读写前查一张影子表。

用它跑解析器，三种输入各给出一个以反斜杠结尾的字符串：

```cpp title="trail.cpp" ub
#include "kv.hpp"
#include <cstdio>
#include <string>
int main() {
  auto a = parse_kv(R"(a=1\)");                  // 字面量后面还有 '\0'
  std::printf("literal: %zu\n", a->at(0).second.size());
  std::string s = R"(a=1\)";
  auto b = parse_kv(s);                          // std::string 后面也有 '\0'
  std::printf("string:  %zu\n", b->at(0).second.size());
  auto* p = new char[4]{'a', '=', '1', '\\'};    // 恰好 4 字节
  auto c = parse_kv({p, 4});
  std::printf("heap:    %zu\n", c->at(0).second.size());
  delete[] p;
}
```

```text
$ clang++ -std=c++2c -g -gdwarf-4 -fsanitize=address,undefined kv.cpp trail.cpp && ./a.out
literal: 2
string:  2
==47934==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x6020000000d4 ...
SUMMARY: AddressSanitizer: heap-buffer-overflow kv.cpp:10 in parse_kv(...)
```

前两个调用都执行了 UB，ASan 却没有报告：字符串字面量和 `std::string` 的缓冲区末尾都有一个 `'\0'`，`s[4]` 读到的是合法内存，只是不属于这个 `string_view`。ASan 只知道哪些字节可以访问，不知道 `string_view` 的边界。只有缓冲区恰好在 4 字节处结束时，读取才落进红区。

单元测试里的输入几乎都是字面量和 `std::string`，所以就算整个测试套件都在 ASan 下运行，这个错误也不会出现。后文的标准库加固和模糊测试从两个方向解决这个问题。怎样逐段读 ASan 报告见 [[toolchain/debugging]]。

!!! impl "macOS 上 ASan 默认关闭的检查"
    本机 ASan 默认不做泄漏检测，不检测 stack-use-after-return，不检测 `new[]` 与 `delete` 的不匹配。测试时可以统一设置 `ASAN_OPTIONS=detect_leaks=1:detect_stack_use_after_return=1:alloc_dealloc_mismatch=1`。三者的例子分别见 [[topics/ownership-and-smart-pointers]] 和 [[topics/dangling-references]]。

### LSan：泄漏

LeakSanitizer 随 ASan 一起链接，进程退出时扫描所有仍可达的内存，报告不可达的堆块。泄漏不是 UB，但在长期运行的服务里同样致命。在 macOS 上它需要显式开启：

```text
$ clang++ -std=c++2c -g -gdwarf-4 -fsanitize=address leak.cpp -o leak
$ ./leak; echo $?
0
$ ASAN_OPTIONS=detect_leaks=1 ./leak; echo $?
==51030==ERROR: LeakSanitizer: detected memory leaks

Indirect leak of 40 byte(s) in 1 object(s) allocated from:
    #0 0x000104e1145c in _Znwm+0x6c (libclang_rt.asan_osx_dynamic.dylib:arm64+0x6545c)
    ...
SUMMARY: AddressSanitizer: 80 byte(s) leaked in 2 allocation(s).
1
```

`leak.cpp` 是两个互相持有 `shared_ptr` 的节点，完整分析见 [[topics/ownership-and-smart-pointers]]。默认设置下退出码是 0，CI 不会发现任何问题。

### UBSan：核心语言 UB

**UndefinedBehaviorSanitizer**（UBSan，`-fsanitize=undefined`）在可能产生 UB 的运算前插入检查。`-fsanitize=undefined` 是一组检查的总称，用 `-###` 可以看到本机 Clang 23 展开后的列表：

```text
$ clang++ -fsanitize=undefined -### -c x.cpp 2>&1 | tr ' ' '\n' | grep -- -fsanitize=
"-fsanitize=alignment,array-bounds,bool,builtin,enum,float-cast-overflow,function,
  integer-divide-by-zero,nonnull-attribute,null,pointer-overflow,return,
  returns-nonnull-attribute,shift-base,shift-exponent,signed-integer-overflow,
  unreachable,vla-bound"
```

它们对应的都是标准规定为 UB 的操作，例如 `signed-integer-overflow` 对应算术表达式的结果不可表示（[[expr.pre#4]]）。本机这份列表里没有 `vptr`（按错误动态类型访问成员），需要单独写 `-fsanitize=vptr`，例子见 [[topics/casts]]。`unsigned-integer-overflow`、`implicit-conversion` 这类检查不在其中，因为无符号回绕和隐式截断都有定义；它们在 `-fsanitize=integer` 里，适合用来查逻辑错误，但会在合法的哈希和随机数代码里报告大量结果。

UBSan 的默认行为对测试很不友好：

```cpp run title="hash.cpp" ub
#include <cstdio>
#include <string_view>

int hash(std::string_view s) {
  int h = 0;
  for (char c : s) h = h * 31 + c;   // 有符号溢出
  return h;
}

int main() {
  std::printf("%d\n", hash("ab"));
  std::printf("%d\n", hash("hello, world"));
}
```

```text
$ clang++ -std=c++2c -g -gdwarf-4 -fsanitize=undefined hash.cpp -o h && ./h; echo $?
3105
hash.cpp:6:26: runtime error: signed integer overflow: 99162322 * 31 cannot be represented in type 'int'
SUMMARY: UndefinedBehaviorSanitizer: undefined-behavior hash.cpp:6:26
-640608884
0
```

报告之后程序继续运行，退出码 0，测试显示通过。大多数 UBSan 检查默认是可恢复的（`-###` 输出中的 `-fsanitize-recover=` 列出了它们，只有 `return` 和 `unreachable` 不在其中）。测试构建应当加 `-fno-sanitize-recover=undefined`：

```text
$ clang++ -std=c++2c -g -gdwarf-4 -fsanitize=undefined -fno-sanitize-recover=undefined hash.cpp -o h && ./h; echo $?
3105
hash.cpp:6:26: runtime error: signed integer overflow: 99162322 * 31 cannot be represented in type 'int'
SUMMARY: UndefinedBehaviorSanitizer: undefined-behavior hash.cpp:6:26
134
```

运行时选项 `UBSAN_OPTIONS=halt_on_error=1` 在本机得到同样的结果（退出码 134），不需要重新编译，但它依赖环境变量是否被正确传进测试进程。把行为写进编译选项更可靠。另外，同一个源码位置的 UBSan 报告只打印一次，修好一处之后可能会冒出下一处。

### TSan：数据竞争

两个线程对同一个内存位置的访问，如果至少一个是写、至少一个不是原子操作，而且两者之间没有 happens-before 关系，就构成[[g:data-race|数据竞争]]，行为未定义（[[intro.races#17]]）。**ThreadSanitizer**（TSan，`-fsanitize=thread`）为每次访问记录线程和向量时钟，发现两个访问之间缺少同步时报告。

```cpp run title="race.cpp" ub
#include <cstdio>
#include <thread>

struct Stats {
  long parsed = 0;               // 应该是 std::atomic<long>
  void on_parse() { ++parsed; }
};

int main() {
  Stats st;
  auto work = [&] { for (int i = 0; i < 1000; ++i) st.on_parse(); };
  std::thread t1(work), t2(work);
  t1.join(); t2.join();
  std::printf("%ld\n", st.parsed);
}
```

```text
$ clang++ -std=c++2c -O2 race.cpp && for i in 1 2 3 4 5; do ./a.out; done
2000
2000
2000
2000
2000
$ clang++ -std=c++2c -g -gdwarf-4 -O1 -fsanitize=thread race.cpp && ./a.out
==================
WARNING: ThreadSanitizer: data race (pid=50051)
  Write of size 8 at 0x00016bae2ac8 by thread T2:
    #0 Stats::on_parse() race.cpp:6 (race_tsan:arm64+0x1000008cc)
    #1 main::$_0::operator()() const race.cpp:11 (race_tsan:arm64+0x1000008cc)
    ...
  Previous write of size 8 at 0x00016bae2ac8 by thread T1:
    #0 Stats::on_parse() race.cpp:6 (race_tsan:arm64+0x1000008cc)
    ...
  Location is stack of main thread.
  ...
SUMMARY: ThreadSanitizer: data race race.cpp:6 in Stats::on_parse()
==================
2000
ThreadSanitizer: reported 1 warnings
```

不开 TSan 时，五次运行都打印出正确的 2000，测试会通过。TSan 不依赖竞争真的造成错误结果，只要两次访问之间没有同步就报告，所以一次运行就够了。它报告进程退出码非零（本机为 134）。TSan 只能检查执行到的交错，对从未并发执行过的代码路径无能为力；内存模型本身见 [[topics/memory-model]]。

### MSan：本机不可用

MemorySanitizer（`-fsanitize=memory`）追踪每一位是否已初始化，报告依赖未初始化值的分支和输出。它只支持 Linux 等少数平台，本机 Clang 23 报 `unsupported option '-fsanitize=memory' for target 'arm64-apple-darwin25.5.0'`。它还要求所有代码（包括标准库）都用 MSan 插桩编译，否则会误报，所以通常只在 Linux CI 上用专门构建的 libc++ 运行。

在 macOS 上可以用两种办法部分替代：

- `-Wall` 中的 `-Wsometimes-uninitialized` 等警告能发现一部分路径上的未初始化读取。
- `-ftrivial-auto-var-init=pattern` 让未初始化的局部变量以固定的字节模式开始。本机一个漏写 `else` 分支的函数，默认构建返回 `0xeca77660` 这样每次不同的垃圾值，加这个选项后稳定返回 `0xaaaaaaaa`。它不报告错误，但让依赖未初始化值的测试稳定地失败，而不是偶尔失败。

C++26 把读取未初始化的自动变量从 UB 改成了错误行为（erroneous behavior，[[basic.indet#2]]，[[P2795R5]]），变量的初始字节是实现决定的**错误值**（[[basic.indet#1]]）。`pattern` 选项正是一种这样的实现选择。截至写作时 Clang 默认仍按 UB 处理这类读取，见 [[topics/undefined-behavior]]。

### 开销

下面是同一个基准程序（对一个 20000 对键值、约 50 万字节的输入调用 `parse_kv` 400 次）在不同构建下的本机结果，都用 `-O2 -g`。机器同时在运行其他任务，每种配置跑 3 次，时间波动较大，只适合看数量级：

| 构建 | 用时（ms，3 次） | 相对普通 `-O2` | 最大常驻内存 |
|---|---|---|---|
| 普通 `-O2` | 355–516 | 1× | 10 MB |
| `-O0`（不加 sanitizer） | 3111–3193 | 约 7× | 10 MB |
| libc++ 加固 EXTENSIVE | 288–574 | 约 1× | 10 MB |
| 覆盖率插桩 | 427–604 | 约 1.1× | 10 MB |
| UBSan | 743–1046 | 约 2× | 12 MB |
| ASan | 1036–1448 | 约 2.5× | 275 MB |
| ASan + UBSan | 1474–1854 | 约 3.5× | 275 MB |
| TSan（单线程） | 7983–12173 | 约 20–30× | 44 MB |

几点观察：

- ASan 的内存开销远大于时间开销。影子内存、红区，以及把释放的内存放进隔离区延迟复用，让常驻内存涨了二十多倍。
- 这个基准不断分配小字符串，TSan 在单线程程序里也要记录每次访问，开销最大。
- `-O0` 比任何一种 `-O2` 下的 sanitizer 构建都慢。sanitizer 构建用 `-O1` 或 `-O2` 编译是常见做法，既更快，又让测试在接近发布的优化下运行（见后文）。

### 哪些能组合

本机 Clang 23 的结果：

| 组合 | 结果 |
|---|---|
| ASan + UBSan | 可以 |
| TSan + UBSan | 可以 |
| ASan + TSan | `'-fsanitize=address' not allowed with '-fsanitize=thread'` |
| ASan + TySan | `'-fsanitize=type' not allowed with '-fsanitize=address'` |
| fuzzer + ASan / UBSan / TSan | 可以 |
| MSan | 本机不支持 |

ASan、TSan、MSan 各自都要接管内存分配和地址空间布局，影子内存的映射方式互相冲突，所以只能各占一个构建。UBSan 的检查是局部的，不需要影子内存，可以和任何一个放在一起。实际的结论是：一个 ASan+UBSan 构建，一个 TSan 构建，各跑一遍全部测试。

## 标准库加固：把库 UB 变成测试失败

前面的 `parse_kv(R"(a=1\)")` 违反的是 `string_view::operator[]` 的前置条件。C++26 把这类前置条件标为**加固前置条件**（hardened precondition），在加固实现中，调用函数前会以终止语义检查它，违反时是契约违反而不是 UB（[[structure.specifications#3]] ¶3.5，[[intro.compliance.general#8]]，[[P3471]]）。libc++ 用 `_LIBCPP_HARDENING_MODE` 选择检查级别，各级别的含义见 [[topics/undefined-behavior]]。

同一个 `trail.cpp`，不加 sanitizer，只换加固级别：

```text
$ clang++ -std=c++2c -g -D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_FAST kv.cpp trail.cpp && ./a.out; echo $?
133
$ clang++ -std=c++2c -g -D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_DEBUG kv.cpp trail.cpp && ./a.out; echo $?
string_view:417: libc++ Hardening assertion __pos < size() failed: string_view[] index out of bounds
134
```

ASan 漏掉的字面量用例，加固模式在第一次调用时就终止了程序。原因是加固检查的是 `string_view` 自己的边界，ASan 检查的是底层内存的边界。两者互补：加固只覆盖标准库的接口，对裸指针和自己写的容器无能为力；ASan 覆盖所有内存访问，但看不到逻辑上的边界。

`std::string::operator[]` 的加固前置条件是 `pos <= size()`（[[string.access#1]]），允许读末尾的 `'\0'`；`string_view` 的是 `pos < size()`。标准在 `string_view` 处专门加了一条注说明后者更严格。把参数从 `const std::string&` 改成 `std::string_view` 的重构，可能让原本合法的 `s[s.size()]` 变成 UB，加固模式能在测试里抓到它。

加固模式的开销在上面的基准中测不出来，所以推荐在所有测试构建中开启 DEBUG 级别，在发布构建中考虑 FAST 级别。加固和 sanitizer 可以同时开启。

## 在 CI 里组织构建

预设的写法和 `CMAKE_CXX_FLAGS` 为什么要放在预设里，见 [[toolchain/cmake]]。下面只列测试相关的配置：

```json title="CMakePresets.json（节选）"
{ "name": "asan-ubsan", "inherits": "base",
  "cacheVariables": { "CMAKE_CXX_FLAGS":
    "-fsanitize=address,undefined -fno-sanitize-recover=undefined -fno-omit-frame-pointer -gdwarf-4" } },
{ "name": "tsan", "inherits": "base",
  "cacheVariables": { "CMAKE_CXX_FLAGS": "-fsanitize=thread -gdwarf-4" } },
{ "name": "hardened-o2", "inherits": "base",
  "cacheVariables": { "CMAKE_BUILD_TYPE": "RelWithDebInfo", "CMAKE_CXX_FLAGS":
    "-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_DEBUG" } },
{ "name": "coverage", "inherits": "base",
  "cacheVariables": { "CMAKE_CXX_FLAGS":
    "-fprofile-instr-generate -fcoverage-mapping" } },
{ "name": "fuzz", "inherits": "base",
  "cacheVariables": { "KV_FUZZ": "ON", "CMAKE_CXX_FLAGS":
    "-fsanitize=fuzzer-no-link,address,undefined -gdwarf-4" } }
```

测试预设里给 ASan 构建设置 `"environment": { "ASAN_OPTIONS": "detect_leaks=1" }`。本机在 `base` 预设里指定了 Homebrew Clang 23，配置、构建了这五个预设，`ctest --preset asan-ubsan` 通过。

| 配置 | 抓什么 | 建议频率 |
|---|---|---|
| Debug + ASan + UBSan，不可恢复 | 内存错误、核心语言 UB、泄漏 | 每次提交 |
| TSan | 数据竞争 | 每次提交（有多线程代码时） |
| `-O2` + libc++ 加固 DEBUG | 库前置条件；只在优化后暴露的 UB | 每次提交 |
| 覆盖率 | 哪些代码没被测到 | 每次提交，或每天 |
| 模糊测试短跑（固定次数） | 畸形输入 | 每次提交 |
| 模糊测试长跑 | 更深的路径 | 每天或持续运行 |
| Linux + MSan（如果有条件） | 未初始化读取 | 每天 |

sanitizer 不能链接到未插桩的代码里就算完事。ASan 的报告只针对插桩过的代码；预编译的第三方库里的越界读不会被发现，TSan 则可能把它看不到的同步当作缺失，报告假阳性。依赖最好和项目用同一组选项从源码构建（见 [[toolchain/dependencies]]）。

## 模糊测试

**模糊测试**（fuzzing）让程序自动生成大量输入去执行被测代码。libFuzzer 是 LLVM 自带的覆盖率引导型模糊测试引擎：编译器用 `-fsanitize=fuzzer` 插入覆盖率计数，引擎每生成一个输入就观察它是否走到了新的分支，走到了就把它留进语料库，作为之后变异的起点。配合 ASan 和 UBSan，任何一个输入触发的 UB 都会变成崩溃。

本机 Homebrew Clang 23 带有 libFuzzer 的运行时（`libclang_rt.fuzzer_osx.a`），`-fsanitize=fuzzer` 可以直接使用。Xcode 自带的 Apple Clang 21 接受这个选项，但链接时报告找不到 `libclang_rt.fuzzer_osx.a`。

### 目标函数

**模糊测试目标**（fuzz target）是一个固定签名的 C 函数，引擎反复调用它：

```cpp title="kv_fuzz.cpp"
#include "kv.hpp"
#include <cstddef>
#include <cstdint>

extern "C" int LLVMFuzzerTestOneInput(const std::uint8_t* data,
                                      std::size_t size) {
  std::string_view s(reinterpret_cast<const char*>(data), size);
  (void)parse_kv(s);
  return 0;
}
```

`-fsanitize=fuzzer` 同时提供 `main`。引擎把每个输入放在一个恰好 `size` 字节的堆块里，这正是 ASan 需要的条件：越过末尾一个字节就进入红区。

```text
$ clang++ -std=c++2c -g -gdwarf-4 -O1 -fsanitize=fuzzer,address,undefined kv.cpp kv_fuzz.cpp -o kv_fuzz
$ mkdir corpus && ./kv_fuzz corpus
INFO: Seed: 2604735966
#2      INITED cov: 34 ft: 34 corp: 1/1b exec/s: 0 rss: 34Mb
#3      NEW    cov: 35 ft: 41 corp: 2/3b lim: 4 exec/s: 0 rss: 34Mb L: 2/2 MS: 1 CrossOver-
...
#124    NEW    cov: 86 ft: 124 corp: 5/13b lim: 4 exec/s: 0 rss: 38Mb L: 3/4 MS: 2 ChangeBinInt-InsertByte-
...
#1143   NEW    cov: 94 ft: 137 corp: 12/42b lim: 6 exec/s: 0 rss: 38Mb L: 6/6 MS: 1 CopyPart-
==38537==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x60200000a512 ...
READ of size 1 at 0x60200000a512 thread T0
    #0 ... in parse_kv(std::__1::basic_string_view<char, std::__1::char_traits<char>>) kv.cpp:10
    #1 ... in LLVMFuzzerTestOneInput kv_fuzz.cpp:8
    ...
0x60200000a512 is located 0 bytes after 2-byte region [0x60200000a510,0x60200000a512)
...
SUMMARY: AddressSanitizer: heap-buffer-overflow kv.cpp:10 in parse_kv(...)
0x87,0x5c,
artifact_prefix='./'; Test unit written to ./crash-e580f7707522eeeb678ce70c71887f8915079557
```

每行开头的 `#N` 是已执行的输入数，`cov` 是覆盖到的边数。引擎从空语料库开始，执行一千多个输入后找到了崩溃：两个字节 `0x87 0x5c`，第二个字节是反斜杠。崩溃输入写进了 `crash-` 文件。本机换 5 个随机种子再跑，分别在 288 到 2853 次执行后找到同一个错误，每次都不到一秒；其中 4 次的崩溃输入就是单个反斜杠 `0x5c`。

### 复现、修复、回归

把崩溃文件作为参数传给目标程序，只执行这一个输入：

```text
$ ./kv_fuzz crash-08534f33c201a45017b502e90a800f1b708ebcb3
Running: crash-08534f33c201a45017b502e90a800f1b708ebcb3
==47330==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x602000000191 ...
    #0 0x000100bc155c in parse_kv(...) kv.cpp:10
```

修复是在转义时检查后面还有没有字符：

```cpp
if (c == '\\') {
  if (++i == s.size()) return std::nullopt;   // 结尾的孤立反斜杠
  cur->push_back(s[i]);
  continue;
}
```

修复后本机让引擎跑 30 秒，执行了约 268 万个输入（平均每秒约 8.7 万个），没有再崩溃，覆盖的边数稳定在 133。

崩溃输入应当留下来。一种做法是在单元测试里加一个用例（`CHECK(!parse_kv("\\"))`）；另一种是把崩溃文件放进仓库里的语料库目录，CI 中用 `./kv_fuzz corpus_dir -runs=0` 只回放语料库而不生成新输入。本机对只含一个崩溃文件的目录这样运行，修复前立即报告 heap-buffer-overflow。

### 放进 CTest

模糊测试的长跑不适合每次提交，但跑固定次数的冒烟测试很便宜：

```cmake
option(KV_FUZZ "Build libFuzzer targets" OFF)
if(KV_FUZZ)
  add_executable(kv_fuzz tests/kv_fuzz.cpp)
  target_link_libraries(kv_fuzz PRIVATE kv)
  target_link_options(kv_fuzz PRIVATE -fsanitize=fuzzer)
  add_test(NAME kv_fuzz_smoke
           COMMAND kv_fuzz -runs=20000 -seed=1)
endif()
```

上面 `fuzz` 预设里，编译选项用 `-fsanitize=fuzzer-no-link`：所有目标都插入覆盖率计数，但只有模糊测试目标链接 libFuzzer 的 `main`，普通的单元测试仍然用自己的 `main`。本机在修复前运行 `ctest --preset fuzz`，单元测试通过，`kv_fuzz_smoke` 在 0.81 秒时报告同一个 heap-buffer-overflow 并失败。固定 `-seed` 让 CI 结果可重现。

!!! tip "写模糊测试目标的几条建议"
    - 目标要快，不要有全局状态，不要依赖时间或随机数，否则崩溃无法重现。
    - 除了检查不崩溃，还可以在目标里检查性质，例如解析成功后把结果再序列化、再解析，用 `__builtin_trap()` 断言两次结果相同。
    - 输入格式有结构时，给一些合法样本作为初始语料库，或用 `-dict=` 提供关键字字典，引擎能更快走到深处。

## 基于性质的测试

**基于性质的测试**（property-based testing）不写具体的输入和期望输出，而是写一个对所有输入都应成立的性质，由程序生成大量随机输入去检验。它和模糊测试相近，区别在于输入是按类型结构生成的（这里是一组键值对，而不是字节串），检查的是语义性质而不只是不崩溃。C++ 有 RapidCheck 这类库提供生成器和失败用例的自动缩小，本机没有安装；用标准库的 `<random>` 可以写一个最小版本。

解析器最自然的性质是：序列化之后再解析，得到原来的值。

```cpp title="prop.cpp" ok
#include "kv.hpp"
#include <cstdio>
#include <random>

std::string to_kv(const KV& kv) {
  std::string out;
  auto put = [&](const std::string& s) {
    for (char c : s) {
      if (c == ';' || c == '\\') out += '\\';
      out += c;
    }
  };
  for (std::size_t i = 0; i < kv.size(); ++i) {
    if (i) out += ';';
    put(kv[i].first); out += '='; put(kv[i].second);
  }
  return out;
}

std::string random_string(std::mt19937& g) {
  static constexpr char alphabet[] = "ab=;\\";   // 偏向特殊字符
  std::uniform_int_distribution<int> len(0, 4), ch(0, 4);
  std::string s(len(g), ' ');
  for (char& c : s) c = alphabet[ch(g)];
  return s;
}

int main() {
  std::string shortest;
  int failures = 0;
  std::mt19937 g(12345);                        // 固定种子：失败可重现
  for (int iter = 0; iter < 10000; ++iter) {
    KV kv(std::uniform_int_distribution<int>(0, 3)(g));
    for (auto& [k, v] : kv) { k = random_string(g); v = random_string(g); }
    std::string text = to_kv(kv);
    if (parse_kv(text) != kv) {                 // 性质：解析是序列化的逆
      if (shortest.empty() || text.size() < shortest.size()) shortest = text;
      ++failures;
    }
  }
  if (failures) {
    std::printf("%d of 10000 failed; shortest: %s\n", failures, shortest.c_str());
    return 1;
  }
  std::puts("10000 cases OK");
}
```

```text
$ clang++ -std=c++2c -g -gdwarf-4 -fsanitize=address,undefined kv.cpp prop.cpp && ./a.out
3847 of 10000 failed; shortest: ==
```

最短的失败用例是 `==`：键为 `=`、值为空的一对，序列化时 `=` 没有转义，解析器把第一个 `=` 当作分隔符，得到键为空、值为 `=`。这个错误在 `to_kv` 里，不是 UB，sanitizer 和模糊测试都不会报告它。在 `put` 中把 `=` 也转义后，10000 个用例全部通过。

记录最短的失败用例是最简单的缩小办法。字母表故意只包含特殊字符，否则随机字符串很少碰到边界。生成器的设计决定了这类测试能找到什么。

## 覆盖率

Clang 的源码级覆盖率分两步：`-fprofile-instr-generate -fcoverage-mapping` 编译，程序运行时把计数写进 `.profraw` 文件；再用 `llvm-profdata` 合并、`llvm-cov` 生成报告。

```text
$ clang++ -std=c++2c -O0 -fprofile-instr-generate -fcoverage-mapping kv.cpp kv_test.cpp -o kv_cov
$ LLVM_PROFILE_FILE=kv.profraw ./kv_cov
$ llvm-profdata merge -sparse kv.profraw -o kv.profdata
$ llvm-cov report ./kv_cov -instr-profile=kv.profdata kv.cpp
Filename  Regions  Missed Regions   Cover  Functions ...  Lines  Missed Lines    Cover  Branches  Missed Branches   Cover
kv.cpp         25               1  96.00%          1 ...     23             0  100.00%        16                2  87.50%
```

`llvm-cov show` 逐行给出执行次数，`-show-branches=count` 再给出每个条件的真假次数（节选）：

```text
    9|     23|    if (c == '\\') {              // 转义：下一个字符原样保留
  ------------------
  |  Branch (9:9): [True: 1, False: 22]
  ------------------
   10|      1|      cur->push_back(s[++i]);
   11|      1|      continue;
   12|      1|    }
   13|     22|    if (c == '=' && cur == &key) { cur = &val; continue; }
  ------------------
  |  Branch (13:9): [True: 4, False: 18]
  |  Branch (13:21): [True: 4, False: 0]
  ------------------
   ...
   23|      2|  else if (!key.empty()) return std::nullopt;
  ------------------
  |  Branch (23:12): [True: 0, False: 2]
  ------------------
```

行覆盖率 100%，越界读的那一行执行过一次，错误依然没被发现。覆盖率回答的是哪些代码执行过，不回答在什么值下执行过：第 10 行只在反斜杠后面还有字符时执行过。两个未覆盖的分支倒是有用的提示：没有测试过值里含 `=` 的情况（`13:21` 为假），也没有测试过只有键没有 `=` 的结尾（`23:12` 为真）。

所以覆盖率适合找没测到的代码，不适合证明测试充分。100% 的覆盖率加上 sanitizer，仍然要靠边界值、模糊测试和性质测试去覆盖输入空间。覆盖率插桩的运行开销很低（上表约 1.1×），可以与 sanitizer 分开，单独作为一个 CI 配置。

## 同一组测试，-O0 与 -O2

只在 `-O0` 下跑测试，会漏掉一类错误：依赖 UB 的代码在不优化时恰好按硬件行为工作，优化之后编译器利用 UB 改写了它。

```cpp run title="sat.cpp" ub
#include <climits>
#include <cstdio>

int sat_add(int a, int b) {
  int r = a + b;                 // 先算，再看有没有回绕
  if (b > 0 && r < a) return INT_MAX;
  if (b < 0 && r > a) return INT_MIN;
  return r;
}

int main() {
  bool ok = sat_add(INT_MAX, 1) == INT_MAX
         && sat_add(INT_MIN, -1) == INT_MIN;
  std::puts(ok ? "PASS" : "FAIL");
}
```

| 构建 | 输出 |
|---|---|
| `-O0` | PASS |
| `-O1`、`-O2` | FAIL |
| `-O0 -fsanitize=undefined` | 报告 `signed integer overflow: 2147483647 + 1`，然后 PASS |
| `-O2 -fsanitize=undefined` | 报告同一处溢出，然后 PASS |

`a + b` 溢出是 UB（[[expr.pre#4]]），编译器可以假设它不发生；在这个假设下 `b > 0 && a + b < a` 永远为假。本机 `-O2` 把整个函数编译成一条 `add w0, w1, w0`，两个检查都消失了。

最后两行说明了另一件事：UBSan 插桩后，`-O2` 下的测试又通过了，因为检查代码阻止了这次优化。sanitizer 构建与发布构建是两个不同的程序。所以 CI 里需要一个不加 sanitizer、只开优化和加固的配置，它最接近实际发布的程序。

正确的写法是不让溢出发生：C++26 的 `std::saturating_add`（[[numeric.sat]]，[[P0543R3]]）本机 libc++ 已提供；也可以用编译器内建的 `__builtin_add_overflow`，本机 `-O2` 把它编译成带溢出标志的 `adds` 加一条 `csel`。更多的算术陷阱见 [[topics/arithmetic]]。

## 思考题

!!! question "思考题 1"
    一个项目的全部单元测试都在 ASan+UBSan 构建下通过，覆盖率 100%。这能说明程序里没有越界读吗？

<details markdown="1">
<summary>答案</summary>

不能。本页的 `parse_kv` 就是反例：越界读所在的行被执行过，但测试的输入都是字面量或 `std::string`，越界读到的是缓冲区末尾的 `'\0'`，ASan 认为这块内存可以访问。违反的是 `string_view::operator[]` 的前置条件 `pos < size()`（[[string.view.access#1]]），这是库 UB，只有标准库加固能检查。覆盖率只说明代码执行过，不说明在什么值下执行过。
</details>

!!! question "思考题 2"
    下面这个编译失败测试为什么本身就不能编译？怎样改？

    ```cpp
    struct Celsius { double v; };
    static_assert(!requires(Celsius c) { c * 2.0; });
    ```

<details markdown="1">
<summary>答案</summary>

`requires` 表达式不在模板化实体的声明中，其中的无效表达式直接让程序非良构（[[expr.prim.req#5]] 的注 1）。只有通过模板参数代入，替换失败才会被吸收成 `false`。改法是先定义一个概念，例如 `template <class T> concept scalable_by_double = requires(T t) { t * 2.0; };`，再写 `static_assert(!scalable_by_double<Celsius>);`。
</details>

!!! question "思考题 3"
    CI 里已经有 ASan+UBSan 构建，为什么还要单独跑一个 TSan 构建，以及一个不加 sanitizer 的 `-O2` 构建？

<details markdown="1">
<summary>答案</summary>

ASan 与 TSan 不能链接进同一个程序，数据竞争（[[intro.races#17]]）只有 TSan 能检测，所以 TSan 必须单独构建。不加 sanitizer 的 `-O2` 构建是因为插桩会改变优化：本页的 `sat_add` 在 `-O2` 下测试失败，加了 UBSan 的 `-O2` 构建反而通过。发布的是不带 sanitizer 的程序，测试也需要覆盖它。
</details>

## 小结

| 手段 | 能发现 | 盲区 |
|---|---|---|
| 单元测试 | 给定输入下的错误结果 | UB 让错误程序给出正确结果时 |
| `static_assert` + `constexpr` | 测试路径上的核心语言 UB（编译期） | 其他输入；库 UB 不保证诊断 |
| 概念 + `requires` | 接口应当拒绝的用法 | 函数体内、直接语境之外的错误 |
| ASan（+LSan） | 越界、释放后使用、泄漏（macOS 需 `detect_leaks=1`） | 仍在合法内存内的逻辑越界 |
| UBSan | 溢出、移位、空指针、未对齐等 | 默认可恢复，要加 `-fno-sanitize-recover` |
| TSan | 数据竞争 | 不能与 ASan 同用；只看执行到的交错 |
| MSan | 未初始化读取 | macOS 不支持 |
| libc++ 加固 | 标准库前置条件 | 裸指针和自定义容器 |
| libFuzzer | 畸形输入导致的崩溃和 UB | 需要能快速重复调用的目标 |
| 性质测试 | 语义错误（如序列化不可逆） | 生成器碰不到的输入 |
| 覆盖率 | 没有执行过的代码 | 执行过但值没覆盖到 |
| `-O2` 无 sanitizer | 只在优化后暴露的 UB | 不报告原因，只表现为结果错误 |
