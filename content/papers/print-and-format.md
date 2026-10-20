---
title: std::format 与 std::print（P0645、P2093、P2286）
summary: C++20 的 std::format 和 C++23 的 std::print 怎样同时避开 printf 和 iostream 的缺点：Python 风格的格式串、默认与 locale 无关、靠特化 formatter 扩展、用类型擦除控制代码体积；格式串的编译期检查为什么靠一个 consteval 构造函数实现、为什么算破坏性修改；print 怎样处理 Windows 控制台的 Unicode；范围默认怎样输出；以及运行期格式串从 vformat 到 dynamic_format 的演变。
status: draft
order: 52
group: 标准库
since: c++20
papers: P0645R10, P1892R1, P2216R3, P2905R2, P2918R2, P3391R2, P3953R3, P2093R14, P3107R5, P2286R8, P0424R1
related: format, namespace.std, format.string, format.formatter, format.fmt.string, format.string.std, format.args, format.range.fmtkind, print.fun, ostream.formatted.print, diff.cpp20.utilities, expr.const.imm, locale.statics, patterns/type-erasure, topics/ranges-design, topics/compile-time-programming, history/modern-library
tags: 提案, 标准库, format, print, 格式串, consteval, 类型擦除, Unicode, C++20, C++23
updated: 2026-10-19
---

!!! tldr
    - `printf` 不检查类型、不能扩展到用户类型；iostream 类型安全，但格式状态会留在流上，一句话被拆进多个 `<<`，也不能调换实参顺序。[[P0645R10]] 用 Python 风格的 `{}` 格式串和可特化的 `formatter<T>` 兼得两者，成为 C++20 的 `<format>`。
    - 格式串的错误本来在运行期抛出 `format_error`。[[P2216R3]] 把格式串形参的类型改成带 `consteval` 构造函数的 `basic_format_string`，把检查变成一次必须是常量表达式的调用，于是错误必须在编译期诊断。它作为缺陷报告适用于 C++20，代价是用变量作格式串的旧代码不再能编译。
    - 每个 `format` 调用只是一层把实参打包成类型擦除的 `format_args` 的薄外壳，真正的格式化代码只有一份。本机 libc++ 中这份代码约 46 KB，之后每多一处调用只增加几百字节。
    - C++23 的 `std::print`（[[P2093R14]]）直接写到 `stdout`；在字面量编码是 UTF-8 时，遇到只能用原生 Unicode API 显示的终端（Windows 控制台），改用该 API 输出，避免乱码。
    - [[P2286R8]] 让范围默认可以格式化：序列输出 `[1, 2]`，map 输出 `{"k": 1}`，元素中的字符串加引号并转义。

## C++20 之前：两种都不够好的选择

在 C++20 之前，输出一行带数值的文本，要么用 C 的 `printf`，要么用 iostream。两者各有一类问题。

`printf` 的格式说明同时承担两件事：怎样显示，以及实参是什么类型。`%d`、`%ld`、`%lld` 的区别只在于告诉函数去读一个 `int`、`long` 还是 `long long`，按 C 标准，类型写错就是 {{ub}}：

```cpp title="printf-types.cpp" run ub
#include <cstdint>
#include <cstdio>

int main() {
  long n = 1L << 40;
  std::int64_t id = 42;
  std::printf("%d\n", n);    // UB: %d 要求 int
  std::printf("%ld\n", id);  // 在 macOS 上 int64_t 是 long long
}
```

本机 Clang 23 对两行都给出 `-Wformat` 警告。第二行在 Linux 上没有问题，因为那里的 `int64_t` 是 `long`；可移植的写法要用 `<cinttypes>` 里的 `PRId64` 宏。`printf` 也无法扩展：用户类型只能先转成字符串，`std::string` 要写 `.c_str()`。

iostream 用重载解决了类型问题，也能为用户类型重载 `<<`。但它把格式选项做成了流的状态：

```cpp title="sticky.cpp" run ok
#include <iostream>

int main() {
  std::cout << std::hex << 255 << '\n';  // ff
  std::cout << 255 << '\n';              // 仍然是 ff
}
```

`std::hex` 一直生效，直到有人把它改回来。一句话被拆成多个 `<<` 之后，翻译人员拿不到一个完整的句子；不同语言的语序不同，而 `<<` 链的顺序写死在代码里，无法调换（[[P0645R10]] 的位置实参一节专门提到了这一点）。

两者还有一个共同点：输出受全局 locale 影响。下面的程序把全局 locale 设成德语，`printf` 和 `cout` 输出的小数点都变成了逗号：

```cpp title="locale.cpp" ok
#include <cstdio>
#include <format>
#include <iostream>
#include <locale>

int main() {
  std::locale de("de_DE.UTF-8");
  std::locale::global(de);   // 有名字的 locale 也会调用 setlocale
  std::cout.imbue(de);
  std::printf("%.1f\n", 1234.5);                     // 1234,5
  std::cout << 1234.5 << '\n';                       // 1.234,5
  std::cout << std::format("{}", 1234.5) << '\n';    // 1234.5
  std::cout << std::format("{:L}", 1234.5) << '\n';  // 1.234,5
}
```

`printf` 也变了，是因为 [[locale.statics#1]] 规定，`locale::global` 的实参有名字时，还要调用 `setlocale(LC_ALL, ...)` 改变 C 的 locale。写 JSON、日志这类给机器读的文本时，这正是不想要的。程序需要系统里有 `de_DE.UTF-8` locale，否则构造 `std::locale` 时抛出 `runtime_error`；本机 macOS 上的输出如注释所示。

## P0645 的设计空间

[[P0645R10]] 以 Victor Zverovich 的开源库 {fmt} 为基础。它要回答的问题可以分成五个。

### 格式串用什么语法

论文考虑过两条保守的路线。一条是沿用 `printf` 的 `%` 语法并修补它的问题，论文认为这样做会破坏兼容，又和 `printf` 相像到让人误用。另一条是 Boost.Format 的 `format("%1%") % x`，它用 `operator%` 串起实参，C++11 有了变参模板之后已经没有必要，而且它的语法同样背着 `printf` 的包袱。

最终采用 Python、.NET 和 Rust 一系的语法：替换字段写在 `{}` 里，冒号后面是格式说明。类型信息由实参本身提供，格式说明只管显示方式，于是长度修饰符 `h`、`l`、`ll` 都不需要了：

```cpp title="basics.cpp" run ok
#include <cassert>
#include <cstdint>
#include <format>

int main() {
  long n = 1L << 40;
  std::int64_t id = 42;
  assert(std::format("{} {}", n, id) == "1099511627776 42");
  assert(std::format("{:x} {}", 255, 255) == "ff 255");  // 不留状态
  assert(std::format("{0} of {1}", 3, 10) == "3 of 10");
  assert(std::format("{1} 中的第 {0} 个", 3, 10) == "10 中的第 3 个");
}
```

最后两行是**位置实参**（positional argument）：`{1}` 指第二个实参。译文可以调换顺序而不改代码。自动编号 `{}` 和手动编号 `{0}` 不能在同一个格式串里混用（[[format.string.general#4]]）。格式串的完整语法见 [[format.string]]。

### locale：默认不用

P0645 仿照 Python，默认的格式化与 locale 无关，只有专门的类型说明 `n` 才按 locale 输出数字。理由是高吞吐的文本（JSON、XML）不需要也不应该依赖 locale，而且不查询 locale 也更快。

`n` 在 C++20 发布前被换掉了。[[P1892R1]] 指出，`n` 只能得到一种按 locale 的表示，用不了 `f`、`e` 这些浮点格式；它改为一个修饰选项，可以和任何类型说明组合，例如 `{:.2Lf}`。选用大写的 `L`，理由包括它与 locale 有字面上的联系、不会像小写字母那样在等宽字体里与数字混淆，以及它醒目，使用了 locale 这件事不容易被忽略。今天的规则在 [[format.string.std#17]]：写了 `L` 才使用上下文的 locale，而且 `L` 只对算术类型有效。

### 怎样扩展到用户类型

用户为自己的类型特化 `std::formatter<T>`，提供两个成员：`parse` 读取冒号后面的格式说明，`format` 按读到的选项输出值。P0645 明确选择了特化，而不是像 `swap` 那样通过实参依赖查找（[[g:argument-dependent-lookup|ADL]]）找一个自由函数。论文的理由有两个：`parse` 的实参里没有被格式化的对象，要靠 ADL 找到它就得加一个虚设的形参；ADL 方案的编译速度也更差。

`parse` 和 `format` 分开，是整个设计后来能做编译期检查的前提：`parse` 只依赖格式串和类型，`format` 才依赖值。写一个 formatter 的细节见 [[format.formatter]]，本页后面有一个完整的例子。

### 代码体积：类型擦除

模板接受任意实参类型，代价是每组实参类型都可能实例化出一整套格式化代码。P0645 的做法是让变参的 `format` 只做一件事：把实参打包成**类型擦除**（[[g:type-erasure|type erasure]]，见 [[patterns/type-erasure]]）的 `format_args`，再调用一个非模板的 `vformat`：

```cpp
template<class... Args>
string format(format_string<Args...> fmt, Args&&... args) {
  return vformat(fmt.get(), make_format_args(args...));
}
```

`format_args` 中的每个实参都被归一化为十几种基本类型之一，用户类型通过一个函数指针间接调用它的 formatter（[[format.arguments]]）。论文特意把 `vformat` 和 `format_args` 作为公开接口，让用户写自己的日志函数时也能用同样的手法，而不是只当作实现细节。

本机 Clang 23 + libc++，`-O2`，统计可执行文件 `__text` 节的大小：

| 程序 | 1 次调用 | 21 次调用 | 每次调用约增加 |
|---|---|---|---|
| `printf("line %s %d\n", ...)` | 48 B | 544 B | 25 B |
| `cout << ... << ...` | 1.1 KB | 2.9 KB | 93 B |
| `std::print("line {} {}\n", ...)` | 46.2 KB | 52.5 KB | 320 B |

`printf` 和 iostream 的实现代码都在系统的动态库里，所以起点很小。libc++ 的格式化代码在头文件里，第一次使用时整份进入程序，约 46 KB；之后每多一处调用只增加打包实参的几百字节，而不是再实例化一套格式化逻辑。这 21 次调用的格式串各不相同，实参类型相同，格式串的内容不进入类型，所以不引起新的实例化。

### 性能

P0645 报告的基准中，{fmt} 把整数转成字符串比 `sprintf` 快约 30%，比 `ostringstream` 快得多。本机（负载较高，取 5 轮中的最小值）的测量方向一致：

| 每次调用（`"{} {}"` 配一个字符串和一个 `int`） | 耗时 |
|---|---|
| `snprintf` 写入缓冲区 | 57 ns |
| `ostringstream` | 112 ns |
| `std::format` 返回 `string` | 48 ns |
| `std::format_to_n` 写入缓冲区 | 43 ns |

加上一个 `{:.3f}` 浮点数之后，四者依次约为 180、340、115、92 ns。这些数字只说明本机 libc++ 的情况，不同的标准库实现差别很大。

## 编译期检查格式串（P2216）

C++20 最初的规则是：格式串不合法时，`format` 在运行期抛出 `format_error`。`std::format("{:d}", "I am not a number")` 能编译，运行时才失败。可是绝大多数格式串是字面量，编译时就已经知道。[[P2216R3]] 统计了一个代码库里的 100 个 `printf` 调用，其中 98 个的格式串是字面量，另外 2 个是包在 gettext 宏里的字面量。

### consteval 构造函数

P2216 没有给格式串引入新的语言特性，只改了 `format` 第一个形参的类型。下面是同一个技巧的最小版本，它只检查 `{}` 的个数是否等于实参个数：

```cpp title="consteval-trick.cpp" run error
#include <cstddef>
#include <stdexcept>
#include <string_view>
#include <type_traits>

template <class... Args> struct fmt_string {
  std::string_view s;
  template <class T>
  consteval fmt_string(const T& t) : s(t) {
    std::size_t n = 0;
    for (std::size_t i = 0; i + 1 < s.size(); ++i)
      if (s[i] == '{' && s[i + 1] == '}') ++n;
    if (n != sizeof...(Args))
      throw std::logic_error("count mismatch");
  }
};

template <class... Args>
void log(fmt_string<std::type_identity_t<Args>...>,
         const Args&...) {}

int main() {
  log("{} {}", 1, 2);  // OK
  log("{}", 1, 2);     // error: 不是常量表达式
}
```

起作用的是三条规则的组合：

1. 构造函数是 `consteval` 的，即[[g:immediate-function|立即函数]]。在立即函数语境之外调用它，是一次[[g:immediate-invocation|立即调用]]，立即调用必须是常量表达式，否则程序非良构（[[expr.const.imm]]）。
2. 字符串字面量隐式转换为 `fmt_string` 时调用了这个构造函数，所以这次转换必须在编译期完成。
3. 常量求值中执行到 `throw`，求值就不是常量表达式。格式串错了，构造函数走到 `throw`，程序非良构，编译器必须诊断。

`std::type_identity_t` 让第一个形参不参与模板实参推导，`Args` 只从后面的实参推出（[[format]] 的思考题 2 解释了为什么必须这样）。如果把 `consteval` 换成 `constexpr`，这个程序能编译，错误的那一行在运行时抛出异常：形参的初始化不要求常量求值。

标准库的版本是 [[format.fmt.string]] 的 `basic_format_string`。它的构造函数不写 `throw`，而是在 ¶3 直接规定结果：

!!! std
    A call to this function is not a core constant expression ([expr.const.core]) unless there exist args of types `Args` such that *str* is a format string for args.

    只要格式串对这些实参类型不合法，这次调用就不是核心常量表达式，于是立即调用失败，程序非良构。

libc++ 的实现在常量求值中把格式串完整解析一遍，对每个替换字段调用对应 formatter 的 `parse`。所以用户类型的格式说明也在编译期检查，前提是 `parse` 是 `constexpr` 的：

```cpp title="celsius.cpp" run ok
#include <format>
#include <print>

struct Celsius { double v; };

template <>
struct std::formatter<Celsius> {
  bool fahrenheit = false;
  constexpr auto parse(std::format_parse_context& ctx) {
    auto it = ctx.begin();
    if (it != ctx.end() && *it == 'F') { fahrenheit = true; ++it; }
    if (it != ctx.end() && *it != '}')
      throw std::format_error("Celsius: 只接受 F");
    return it;
  }
  auto format(Celsius c, auto& ctx) const {
    return fahrenheit
      ? std::format_to(ctx.out(), "{}°F", c.v * 9 / 5 + 32)
      : std::format_to(ctx.out(), "{}°C", c.v);
  }
};

int main() {
  std::println("{} = {:F}", Celsius{100}, Celsius{100});  // 100°C = 212°F
  // std::println("{:K}", Celsius{0});  // error: parse 在常量求值中抛出
}
```

去掉最后一行的注释，本机 Clang 23 报告 `call to consteval function ... is not a constant expression`，note 指向 `parse` 里的 `throw`。

### 考虑过的方案

P2216 比较了两个范围：只检查字符串字面量，或者检查所有在编译期已知的格式串（包括 `constexpr` 变量）。最终的措辞采用后者，构造函数接受任何能转换为 `string_view` 的常量。

论文还记录了委员会的一个选择：格式串不合法时，不采用非良构但不要求诊断（IFNDR）的说法，而是要求编译器必须报错。¶3 的写法做到了这一点：常量求值失败是普通的非良构。

更早的 P0645 已经讨论过编译期检查。它承认可以用 `constexpr` 函数在编译期解析格式串，但 C++17 给不出满意的接口：要把格式串带进编译期，就得让每个格式串成为一个类型，而要求用户为每个格式串手写或用宏生成一个类型是不可接受的。论文把希望寄托在编译期字符串的提案上（例如基于用户定义字面量的 [[P0424R1]]）。C++20 的 `consteval` 提供了另一条路：构造函数在编译期读取格式串的内容，却不需要把它编进类型，用户照样写普通的字符串字面量。

### 为什么是破坏性修改

C++20 原来的 `format` 接受 `string_view`，所以用一个运行期字符串作格式串是合法的。P2216 之后，这样的代码非良构：

```cpp title="runtime-string.cpp" run error
#include <format>
#include <string>

std::string f(const std::string& fmt) {
  return std::format(fmt, 1);  // error: fmt 不是常量
}
```

原来在运行期抛异常的错误格式串，现在也变成编译错误。附录 C 的 [[diff.cpp20.utilities#1]] 记录了这两类变化，以及 P2216 的另一半改动：去掉 `format_args_t`，让 `vformat_to` 不再为每种输出迭代器类型实例化一套代码。

委员会仍然把 P2216 作为对 C++20 的缺陷报告。论文的理由是当时还没有标准库实现 C++20 的格式化，受影响的现有代码很少。本机 libc++ 在 `-std=c++20` 下同样执行编译期检查。

## 运行期才知道的格式串

翻译文件里的格式串只在运行期才知道。P2216 之后，C++20 和 C++23 的办法是直接调用类型擦除的那一层：

```cpp title="runtime-format.cpp" run ok
#include <cstdio>
#include <format>
#include <string>

std::string translate(const char* key) {  // 假想的翻译表
  return std::string(key) == "found" ? "找到 {} 个文件，共 {} 字节" : key;
}

int main() {
  std::string fmt = translate("found");
  int files = 3, bytes = 1024;

  auto a = std::vformat(fmt, std::make_format_args(files, bytes));
  auto b = std::format(std::dynamic_format(fmt), files, bytes);  // C++26
  std::puts(a == b ? a.c_str() : "mismatch");

  try {
    (void)std::format(std::dynamic_format(translate("{:d}")), "x");
  } catch (const std::format_error& e) {
    std::puts(e.what());  // 错误推迟到运行期
  }
}
```

`vformat` 本来是给写格式化函数的人用的底层接口，直接用它有一个陷阱。`make_format_args` 只保存实参的引用，[[P2905R2]] 举的例子是：

```cpp
auto args = std::make_format_args(path.string());  // 引用了临时 string
std::string msg = std::vformat(str, args);         // 临时量已经销毁
```

P2905 把 `make_format_args` 的形参从转发引用改成左值引用，传右值直接非良构；它作为缺陷报告适用于 C++23。本机 libc++ 拒绝 `std::make_format_args(42)`，note 说明 `expects an lvalue`。于是上例只能先把实参存进变量。

[[P2918R2]] 另外提供了一个面向使用者的写法：`std::format(std::runtime_format(s), args...)`。`runtime_format` 返回一个仅用于说明的类型，`basic_format_string` 为它准备了一个非 `consteval` 的构造函数，检查推迟到运行期，失败时抛出 `format_error`。这个类型不能复制，只能直接传给格式化函数。

C++23 之后，[[P3391R2]] 让 `std::format` 可以在常量求值中使用，`runtime` 这个名字就不准确了：用了它的格式串也可能在编译期被处理。[[P3953R3]] 把它改名为 `std::dynamic_format`，论文的说法是，真正的区别不在于何时格式化，而在于格式串怎样提供、何时检查。因为 `runtime_format` 本身是 C++26 的新特性，改名不影响已发布的标准。本机 libc++ 只提供 `std::dynamic_format`。

## std::print（P2093）

C++20 有了 `std::format`，输出到终端仍然要写 `std::cout << std::format(...)`：先构造一个临时 `string`，再把它交给 iostream 做一次格式化输出。[[P2093R14]] 提出 `std::print` 和 `std::println`，一次调用完成格式化和输出。

### 输出到哪里

论文调查了其他语言后，让 `print` 默认写到 C 的 `stdout`，另有接受 `FILE*` 的重载；接受 `ostream&` 的重载放在 `<ostream>` 里，其余放在新头文件 `<print>` 中，以免使用 `print` 就要包含庞大的 `<ostream>`。作为 `ostream` 成员函数的写法 `std::cout.print(...)` 被认为更别扭而没有采用。`print` 不自动换行，与 `printf` 一致；`println` 另行提供。

[[print.fun]] 中 `println(FILE*, ...)` 的措辞（¶5）很直接：把 `fmt.get()` 加上 `'\n'` 拼成一个新字符串，再用 `dynamic_format` 交给 `print`。拼出来的格式串不再是常量，但原来的格式串已经在编译期检查过了。

本机测量（输出重定向到 `/dev/null`，关闭 iostream 与 stdio 的同步，取 5 轮最小值）：

| 每次调用 | `"{} {}\n"` | 再加 `{:.3f}` |
|---|---|---|
| `printf` | 78 ns | 200 ns |
| `cout <<` | 140 ns | 368 ns |
| `std::print` | 76 ns | 151 ns |

### Windows 控制台的乱码

P2093 的另一半是编码。Windows 控制台默认按一个传统代码页（如 437）解释字节，程序即使用 `/utf-8` 编译、字面量都是 UTF-8，用 `cout` 输出中文仍然是乱码。论文的设计是：

1. 如果普通字面量编码（[[g:literal-encoding|literal encoding]]，即字符串字面量在程序里的编码）是 UTF-8，`print` 就调用 `vprint_unicode`，否则调用 `vprint_nonunicode`（[[print.fun#2]]）。字面量编码是 UTF-8，就说明程序的作者在用 UTF-8 写文本。
2. `vprint_unicode` 发现目标是一个只能通过原生 Unicode API 显示 Unicode 的终端时，先刷新流，再用该 API 写出（[[print.fun#10]]）。注释说明在 Windows 上就是 `WriteConsoleW`。输出被重定向到文件或管道时，字节原样写出，不做转换。
3. 输出中有非法的码元时行为未定义，¶12 建议需要转码的实现用 U+FFFD 替换它们。

论文考虑过 Java 的做法：把输出转换成当前代码页。它认为这会丢失无法表示的字符，还要付出转换的开销，因此选择了 C、Go、Rust 那样保持原编码，只在终端这一处转换。本机是 macOS，终端本来就按 UTF-8 显示，¶10.1 的分支不会走到，这部分无法在本机验证。

### 后续：直接写进流的缓冲区

C++23 的措辞规定 `print` 先格式化到一个临时 `string`，再写出。[[P3107R5]] 指出这排除了 `printf` 那样在持有流的锁时直接格式化进缓冲区的实现，后者省掉一次分配，论文的基准中快 42% 到 72%。

直接写入的难点是用户的 formatter 在流被锁住时运行：如果它自己去拿一把别的线程持有的锁，而那个线程正在等同一个流，就会死锁。所以 P3107 让这种优化需要声明：变量模板 `enable_nonlocking_formatter_optimization<T>` 默认为 `false`（[[format.formatter.locking#1]]），标准类型的 formatter 设为 `true`。今天的 [[print.fun#2]] 据此选择：全部实参类型都声明了，就调用直接写入的 `vprint_unicode`，否则调用先格式化到 `string` 的 `vprint_unicode_buffered`。论文选择变量模板而不是 formatter 的成员，是因为一个 formatter 继承另一个时，变量模板的值不会被一起继承。

## 范围的格式化（P2286）

C++20 的 `std::format` 不能直接输出 `vector`。{fmt} 早就支持，而标准类型的 formatter 只能由标准库提供：按 [[namespace.std#2]]，程序添加的特化必须依赖至少一个程序定义的类型，`formatter<std::vector<int>>` 不符合。[[P2286R8]] 补上了这一块：

```cpp title="ranges.cpp" run ok
#include <map>
#include <print>
#include <ranges>
#include <set>
#include <string>
#include <vector>

int main() {
  std::vector<int> v{1, 2, 3};
  std::vector<std::string> w{"a", "b c", "\t"};
  std::map<std::string, int> m{{"x", 1}, {"y", 2}};

  std::println("{}", v);               // [1, 2, 3]
  std::println("{::#x}", v);           // [0x1, 0x2, 0x3]
  std::println("{:n}", v);             // 1, 2, 3
  std::println("{}", w);               // ["a", "b c", "\t"]
  std::println("{}", m);               // {"x": 1, "y": 2}
  std::println("{}", std::set{3, 1});  // {1, 3}
  std::println("{}", v | std::views::transform(
                         [](int i) { return i * i; }));  // [1, 4, 9]
  std::println("{:?s}", std::vector{'h', 'i', '\n'});    // "hi\n"
}
```

注释是本机 libc++ 的实际输出。论文中的主要决定：

- 括号：序列用 `[]`，`pair` 和 `tuple` 用 `()`，map 用 `{k: v}`，set 用 `{}`，与 Python 和 {fmt} 一致。论文比较过序列用 `{}` 还是 `[]`、tuple 用 `{}` 还是 `()`。
- 字符串默认加引号并转义。`["a", "b c", "\t"]` 能看出每个元素的边界和不可见字符；不加引号的话，含一个元素 `"a, b"` 的 vector 和含 `"a"`、`"b"` 两个元素的 vector 都输出 `[a, b]`。为此新增了 `?` 类型说明（调试格式，见 [[format.string.escaped]]），容器的 formatter 在元素没有格式说明时调用元素 formatter 的 `set_debug_format()`。
- 元素的格式说明放在第二个冒号后面。`{::#x}` 的第一部分是给整个范围的（填充、对齐、宽度、`n` 去掉括号），第二部分 `#x` 原样交给元素的 formatter。显式写一个空的元素说明 `{::}` 就取消了字符串的引号。
- `pair` 和 `tuple` 不支持逐元素的格式说明。早期修订版尝试过，但格式串里可以出现任何字符，没有可靠的分隔符，就撤回了。
- 论文最后没有加入一个独立的 `format_join`，而是公开 `range_formatter` 类模板，提供 `set_separator`、`set_brackets` 和 `underlying()`，map 和 set 的 formatter 也是用它搭出来的。

一个范围按序列、map、set 还是字符串输出，由变量模板 `format_kind<R>` 决定（[[format.range.fmtkind#2]]）。其中 ¶2.1 处理一个边界情况：`std::filesystem::path` 的元素类型还是 `path`，如果把它当作范围格式化，`formattable` 的检查会无限递归，所以这类范围被禁用。细节见 [[format.formatter]]；ranges 本身的设计见 [[topics/ranges-design]]。

## 措辞去了哪里

| 内容 | 条款 | 来源 |
|---|---|---|
| 格式串语法、标准格式说明、`L` | [[format.string]]、[[format.string.std#17]] | P0645、P1892 |
| `basic_format_string` 的 consteval 构造函数 | [[format.fmt.string#3]] | P2216 |
| `dynamic_format` | [[format.fmt.string]]、[[format.syn]] | P2918、P3953 |
| `make_format_args` 只接受左值 | [[format.arg.store]] | P2905 |
| `formatter` 的 `parse`/`format` 约定 | [[format.formatter]] | P0645 |
| 范围的格式化 | [[format.range]] | P2286 |
| `print`、`println`、`vprint_unicode` | [[print.fun]]、[[ostream.formatted.print]] | P2093、P3107 |
| 兼容性 | [[diff.cpp20.utilities#1]] | P2216 |

格式化库各部分的逐段释义见 [[format]]、[[format.string]] 和 [[format.formatter]]。`<format>` 在整个标准库演进中的位置见 [[history/modern-library]]。

## 编译器支持

本机 Clang 23.1.3 + libc++ 的情况：

| 特性 | 结果 |
|---|---|
| `std::format`、自定义 formatter | 支持，`__cpp_lib_format` 为 `202110L` |
| 格式串编译期检查 | 支持，`-std=c++20` 下同样生效 |
| `std::print`、`std::println` | 支持，`__cpp_lib_print` 为 `202207L` |
| 范围、`pair`/`tuple` 的格式化 | 支持，`__cpp_lib_format_ranges` 为 `202207L` |
| `make_format_args` 拒绝右值 | 支持，`-std=c++23` 下同样生效 |
| `std::dynamic_format` | 支持；没有 `std::runtime_format` |
| 在常量表达式中调用 `std::format` | 不支持（见 [[format]]） |

`__cpp_lib_format` 停在 `202110L`，比实际实现的功能旧，所以在 libc++ 上不能只靠这个宏判断 `dynamic_format` 是否可用。GCC 和 MSVC 本机未验证。

## 思考题

!!! question "1. 把 consteval 换成 constexpr"
    如果 `basic_format_string` 的构造函数只是 `constexpr` 而不是 `consteval`，`std::format("{:d}", "x")` 会怎样？

<details markdown="1">
<summary>答案</summary>

程序能编译，运行时抛出 `format_error`。`constexpr` 函数只是允许在常量求值中调用；用字符串字面量初始化一个函数形参不是需要常量求值的语境，编译器会在运行期执行构造函数。`consteval` 让这次调用成为立即调用，[[expr.const.imm]] 要求它必须是常量表达式，检查才被强制提前到编译期。把本页 `consteval-trick.cpp` 中的 `consteval` 改成 `constexpr`，本机 Clang 23 编译通过，错误的那一行在运行时抛出 `logic_error`。

</details>

!!! question "2. 字符串的引号"
    `std::println("{}", std::vector<std::string>{"a"})` 输出 `["a"]`。怎样得到 `[a]`？为什么默认要加引号？

<details markdown="1">
<summary>答案</summary>

写 `std::println("{::}", v)`。第二个冒号后面是给元素的格式说明，显式写出一个空说明，容器的 formatter 就不再对元素调用 `set_debug_format()`。默认加引号是为了让输出没有歧义：元素里可能有逗号、空格、换行，不加引号就看不出元素的边界（[[P2286R8]]）。

</details>

!!! question "3. 为什么 print 先看字面量编码"
    `std::print` 根据普通字面量编码是否为 UTF-8 选择 `vprint_unicode`，为什么不看运行时的 locale？

<details markdown="1">
<summary>答案</summary>

格式串几乎都是字面量，字面量编码描述的就是程序作者写下的文本的编码，而且在编译期就确定。`std::format` 本身的设计也不依赖 locale（不写 `L` 时），宽度估算同样按与 locale 无关的编码进行（[[format.string.std#12]]）。用运行时 locale 决定会让同一个程序在不同环境下对同一段字节做不同的解释。这是 [[P2093R14]] 给出的理由。

</details>
