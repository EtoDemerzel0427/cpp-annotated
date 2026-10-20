---
title: 编译警告与静态分析
summary: 在运行之前找出缺陷：标准要求编译器诊断什么、不要求什么，-Wall、-Wextra、-pedantic 实际打开了哪些警告，一组推荐的警告选项与各自抓住的错误，-Werror 与第三方头文件，生命周期和线程安全注解，clang-tidy、Clang 静态分析器和 clang-format 的用法，以及静态分析做不到的事。
group: 工程实践
status: draft
order: 140
since: c++98
related: intro.compliance.general, defns.undefined, conv.integral, conv.double, dcl.init.list, expr.cast, expr.delete, dcl.attr.fallthrough, dcl.attr.nodiscard, intro.races, basic.def.odr, topics/undefined-behavior, topics/dangling-references, topics/arithmetic, topics/casts, toolchain/cmake, toolchain/testing, toolchain/debugging, toolchain/reading-compiler-errors
tags: 工具链, 警告, clang-tidy, 静态分析, UB, IFNDR
updated: 2026-10-19
---

!!! tldr
    - 标准只要求编译器对违反可诊断规则的程序给出至少一条诊断；不要求诊断的规则（IFNDR）和未定义行为（UB）都不在此列。警告是实现自己加的，开多少由命令行决定。
    - `-Wall` 并不是全部警告：本机 Clang 23 上它在默认基础上只多开 59 条，`-Wextra` 再多 19 条。隐式转换、遮蔽、非虚析构、旧式转型、`switch` 贯穿等常见错误都要单独打开。
    - `-Weverything` 包含大量与正确性无关的警告（C++98 兼容性、结构体填充），适合用来发现有哪些警告，不适合直接用于构建。
    - 注解（`[[clang::lifetimebound]]`、线程安全属性）把编译器看不到的约定写进代码，让局部分析能跨越函数边界。clang-tidy 检查写法和惯用法，静态分析器沿着执行路径找空指针和泄漏。
    - 静态分析按翻译单元工作、在不知道运行时数据的情况下推理，跨翻译单元的 ODR 违规和依赖输入的 UB 要靠链接期检查、测试和 sanitizer。

!!! note "实验环境"
    本机 Homebrew Clang 23.1.3（libc++）、clang-tidy 23.1.3、scan-build（随 Homebrew LLVM 安装），CMake 3.29、Ninja，Apple M2 Pro。没有安装 GCC，涉及 GCC 的内容只作描述，没有在本机验证。输出中的长路径做了缩短。

## 一段 `-Wall -Wextra` 不报警的代码

```cpp title="misc.cpp"
#include <string>

struct Shape {
  virtual double area() const = 0;
  ~Shape() = default;               // 非虚析构
};

class Account {
  int balance;
public:
  explicit Account(int balance) : balance(balance) {}
  void deposit(int amount) {
    int balance = this->balance + amount;  // 遮蔽成员
    (void)balance;
  }
};

int parse_level(const char* s) {
  int level = 0;
  switch (s[0]) {
  case 'e': level = 3;              // 忘了 break
  case 'w': level = 2; break;
  default:  level = 1;
  }
  return level;
}

void write(const std::string& s) {
  char* p = (char*)s.data();        // 去掉了 const
  p[0] = 'X';
}
```

这段代码是良构的，`clang++ -std=c++2c -Wall -Wextra -pedantic` 不给任何警告。但它有四个缺陷：通过 `Shape*` 删除派生类对象是 UB（[[expr.delete#3]]）；`deposit` 改的是局部变量而不是成员；`'e'` 落进了 `'w'` 的分支；`write` 去掉了 `const`，如果实参引用的是 `const` 对象，写入就是 UB。

加上四个不在 `-Wall`、`-Wextra` 里的选项，编译器把它们全部指了出来：

```text
$ clang++ -std=c++2c -Wall -Wextra -pedantic -Wshadow-all -Wnon-virtual-dtor \
    -Wold-style-cast -Wimplicit-fallthrough -fsyntax-only misc.cpp
misc.cpp:5:3: warning: 'Shape' has virtual functions but non-virtual destructor [-Wnon-virtual-dtor]
misc.cpp:11:24: warning: constructor parameter 'balance' shadows the field 'balance' of 'Account' [-Wshadow-field-in-constructor]
misc.cpp:13:9: warning: declaration shadows a field of 'Account' [-Wshadow]
misc.cpp:22:3: warning: unannotated fall-through between switch labels [-Wimplicit-fallthrough]
misc.cpp:22:3: note: insert '[[fallthrough]];' to silence this warning
misc.cpp:22:3: note: insert 'break;' to avoid fall-through
misc.cpp:29:13: warning: use of old-style cast [-Wold-style-cast]
5 warnings generated.
```

为什么这些警告不在 `-Wall` 里？因为它们在正确的代码里也会出现：构造函数形参和成员同名是常见写法，有意的贯穿也很常见。编译器默认只开误报很少的警告，其余的由项目根据自己的代码风格选择。

## 标准要求诊断什么

¶1 标准把规则分成两类。**可诊断规则**（diagnosable rule）是除了明确写着 no diagnostic is required 的规则和导致 UB 的规则之外的全部语法和语义规则（[[intro.compliance.general#1]]）。¶2.3 规定，程序违反了任何一条可诊断规则，符合标准的实现就必须发出至少一条**诊断信息**（diagnostic message）。

!!! std
    If a program contains a violation of a rule for which no diagnostic is required, this document places no requirement on implementations with respect to that program.

这是 ¶2.2：违反了不要求诊断的规则，标准对实现就没有任何要求，可以静默编译出任意结果。由此得到三种程序错误：

| 类别 | 例子 | 标准对实现的要求 | 实际效果 |
|---|---|---|---|
| 非良构，要求诊断 | 数组大小为 0（[[dcl.array#1]]），窄化的列表初始化（[[dcl.init.list#3]]） | 至少一条诊断（[[intro.compliance.general#2]]） | 通常是错误；作为扩展接受时是警告 |
| 非良构，不要求诊断（[[g:ifndr]]） | 两个翻译单元里同名类的定义不同（[[basic.def.odr#16]]），odr-use 的函数没有定义（[[basic.def.odr#12]]） | 无 | 可能编译、链接成功，行为不可预测 |
| 未定义行为（[[g:undefined-behavior]]） | 有符号溢出、空指针解引用、数据竞争（[[intro.races#17]]） | 无 | 依赖运行时的值，优化器假设它不发生 |

IFNDR 存在的原因通常是诊断代价太高或者不可能：检查 ODR 需要同时看到所有翻译单元，而编译器一次只处理一个。UB 则大多取决于运行时的数据，编译器在编译 `a + b` 时不知道它会不会溢出。所以编译器原则上无法诊断所有错误，警告和静态分析是在这两类里尽力而为。UB 的完整讨论见 [[topics/undefined-behavior]]。

诊断信息是什么由实现定义（[[defns.diagnostic]]），标准不区分警告和错误。一条警告就满足了要求诊断的义务，之后实现仍可以编译这个程序。这正是编译器扩展的工作方式（[[intro.compliance.general#11]]）：

```cpp title="ext.cpp" error
struct Packet {
  int len;
  char data[0];                        // 零长度数组
};

int pick(int* p, int fallback) {
  int* q = p ?: &fallback;             // 省略中间操作数的 ?:
  return ({ int t = *q; t + 1; });     // 语句表达式
}
```

三处都不是 C++：数组大小必须大于零（[[dcl.array#1]]），后两个是 GNU 扩展的语法。本机 Clang 默认和加 `-Wall -Wextra` 都不报告任何问题，加 `-pedantic` 才给出三条警告，`-pedantic-errors` 把它们变成错误：

```text
$ clang++ -std=c++2c -Wall -Wextra -pedantic -fsyntax-only ext.cpp
ext.cpp:3:13: warning: zero size arrays are an extension [-Wzero-length-array]
ext.cpp:7:15: warning: use of GNU ?: conditional expression extension, omitting middle operand [-Wgnu-conditional-omitted-operand]
ext.cpp:8:11: warning: use of GNU statement expression extension [-Wgnu-statement-expression]
3 warnings generated.
```

换句话说，不加 `-pedantic` 的 Clang 在这个例子上不是符合标准的实现。需要代码能在别的编译器上编译时，应当打开 `-pedantic`（与 `-Wpedantic` 相同）。变长数组 `int buf[n];` 是个例外：本机 Clang 23 默认就对它给出 `-Wvla-cxx-extension` 警告。

标准也直接鼓励一些警告。`[[fallthrough]]` 的推荐做法是让它抑制对贯穿的警告（[[dcl.attr.fallthrough#2]]），`[[nodiscard]]` 的推荐做法是在丢弃返回值时发出警告（[[dcl.attr.nodiscard#4]]）。这些都是 Recommended practice，不是要求。

## `-Wall`、`-Wextra`、`-pedantic` 打开了什么

Homebrew LLVM 带有 `diagtool`，可以列出一组选项下实际启用的警告。本机对一个空文件的统计如下（每行是一条警告，以 Clang 内部的诊断 ID 计）：

| 选项 | 启用的警告数 | 比默认多 |
|---|---|---|
| 默认 | 1450 | 0 |
| `-Wall` | 1509 | 59 |
| `-Wextra` | 1469 | 19 |
| `-pedantic` | 1623 | 173 |
| `-Weverything` | 2265 | 815 |

```text
$ diagtool show-enabled --no-levels -Wall e.cpp | wc -l
    1509
$ diagtool tree -Wextra
-Wextra
  -Wdeprecated-copy
  -Wmissing-field-initializers
  -Wignored-qualifiers
  -Wsign-compare
  -Wunused-parameter
  ...
```

默认就开着的 1450 条包括许多和正确性直接相关的警告：返回局部变量的地址（`-Wreturn-stack-address`）、悬垂引用（`-Wdangling`）、忽略 `[[nodiscard]]` 的返回值（`-Wunused-result`）、`switch` 漏掉枚举值（`-Wswitch`）。`-Wall` 增加的是未使用的变量、未初始化的读取、`printf` 格式、成员初始化顺序、多余的 `std::move` 这一类。`-Wextra` 增加有符号与无符号比较、未使用的形参等。`-pedantic` 增加的 173 条几乎都是 `ext_` 开头的扩展诊断。

三组合起来，比默认多 246 条，而 `-Weverything` 多 815 条，剩下的 569 条从不被这三个选项打开，下一节推荐的警告都在其中。

### `-Weverything` 的噪声

下面的程序没有缺陷，`-Wall -Wextra -pedantic` 也没有警告：

```cpp title="clean.cpp" run ok
#include <cstdio>
#include <span>
#include <string>
#include <vector>

struct Point {
  double x;
  char tag;
};

double total(std::span<const double> xs) {
  double s = 0;
  for (std::size_t i = 0; i < xs.size(); ++i) s += xs[i];
  return s;
}

int main(int argc, char** argv) {
  std::vector<double> v{1.0, 2.0, 3.0};
  auto label = std::string("sum");
  Point p{total(v), 'a'};
  std::printf("%s: %s = %g %c\n", argv[0], label.c_str(), p.x, p.tag);
  return argc > 1;
}
```

`-Weverything` 给出 7 条警告：

```text
clean.cpp:11:8: warning: no previous prototype for function 'total' [-Wmissing-prototypes]
clean.cpp:18:24: warning: generalized initializer lists are incompatible with C++98 [-Wc++98-compat]
clean.cpp:18:24: warning: initialization of initializer_list object is incompatible with C++98 [-Wc++98-compat]
clean.cpp:19:3: warning: 'auto' type specifier is incompatible with C++98 [-Wc++98-compat]
clean.cpp:20:10: warning: generalized initializer lists are incompatible with C++98 [-Wc++98-compat]
clean.cpp:6:8: warning: padding size of 'Point' with 7 bytes to alignment boundary [-Wpadded]
clean.cpp:21:3: warning: function 'printf' is unsafe [-Wunsafe-buffer-usage-in-libc-call]
```

四条在说这段代码不能按 C++98 编译，一条在报告结构体有填充（布局见 [[toolchain/object-layout-and-vtables]]），一条要求非 `static` 函数先有声明，一条属于 `-Wunsafe-buffer-usage` 这组为改写整个代码库而设计的检查。这些警告各有用途，但都不是缺陷。

建议用 `-Weverything` 浏览：在自己的代码上跑一次，看看有哪些警告值得加入项目的列表，然后用显式的 `-W...` 列表构建。也有项目反过来用 `-Weverything` 再加一串 `-Wno-...`，代价是每次升级编译器都会出现新的警告组，构建可能因此失败。

## 推荐的警告集合

建议的起点（Clang；GCC 的选项名大多相同，但分组不完全一致）：

```text
-Wall -Wextra -Wpedantic
-Wconversion            # 含 -Wsign-conversion、-Wshorten-64-to-32 等
-Wshadow                # 或者更严格的 -Wshadow-all
-Wnon-virtual-dtor
-Wold-style-cast
-Wimplicit-fallthrough
-Wthread-safety         # 只有写了注解的代码才会触发
```

`-Wdangling` 系列和 `-Wnull-dereference` 在 Clang 中默认已经打开，不需要再写。下面逐个说明它们抓住的错误和规则依据。在 CMake 里把它们设为目标的 PRIVATE 选项，见 [[toolchain/cmake]]。

### `-Wconversion`：值被悄悄改变的隐式转换

```cpp title="conv.cpp"
#include <cstdint>
#include <vector>

int sum(const std::vector<int>& v) {
  int n = v.size();                 // size_t -> int
  int s = 0;
  for (int i = 0; i < n; ++i)
    s += v[i];                      // int -> size_t
  return s;
}

std::uint8_t clamp_byte(int x) {
  return x;                         // int -> uint8_t
}

float half(double d) { return d / 2; }  // double -> float
```

整数之间的转换总是有定义的：结果是目标类型中与原值模 2^N 同余的那个值（[[conv.integral#3]]）。所以 `clamp_byte(300)` 返回 44，没有 UB，也没有任何提示。浮点转换则不同：`double` 的值超出 `float` 的范围时行为未定义（[[conv.double#2]]）。

这些转换都是良构的。只有在列表初始化里，窄化转换（[[g:narrowing-conversion]]，定义见 [[dcl.init.list#7]]）才是非良构的。`-Wconversion` 把其他场合的窄化也报告出来：

```text
conv.cpp:8:12: warning: implicit conversion changes signedness: 'int' to 'size_type' (aka 'unsigned long') [-Wsign-conversion]
conv.cpp:5:13: warning: implicit conversion loses integer precision: 'size_type' (aka 'unsigned long') to 'int' [-Wshorten-64-to-32]
conv.cpp:13:10: warning: implicit conversion loses integer precision: 'int' to 'std::uint8_t' (aka 'unsigned char') [-Wimplicit-int-conversion]
conv.cpp:16:33: warning: implicit conversion loses floating-point precision: 'double' to 'float' [-Wimplicit-float-conversion]
```

在 Clang 中 `-Wconversion` 已经包含 `-Wsign-conversion`。`-Wsign-conversion` 在使用 `size_t` 下标的代码里会很多，修正方式通常是改变量类型（用 `std::size_t`、`std::ssize`）或者写出 `static_cast`，让转换出现在代码里。整数运算的规则见 [[topics/arithmetic]]。

### `-Wshadow`：内层名字遮住外层

`misc.cpp` 的 `deposit` 声明了与成员同名的局部变量，之后函数体里的 `balance` 都查找到局部变量（[[basic.lookup]]）。`-Wshadow` 报告局部变量遮蔽成员、外层局部变量和全局变量的情况。`-Wshadow-all` 还会报告构造函数形参与成员同名，在 `: balance(balance)` 这种惯用写法上也会触发，是否打开取决于项目风格。

### `-Wnon-virtual-dtor`：在声明处报告

`-Wall` 已经包含 `-Wdelete-non-virtual-dtor`，但它在 `delete` 表达式处报告。用 `std::unique_ptr<Shape>` 时，`delete` 在 libc++ 的 `default_delete` 里，本机的警告指向 `unique_ptr.h:74` 再附上一长串实例化路径。`-Wnon-virtual-dtor` 在类定义处报告：有虚函数而析构函数不是虚的，就给出警告。规则依据是 [[expr.delete#3]]：静态类型与动态类型不同时，静态类型必须有虚析构函数，否则是 UB。

### `-Wold-style-cast`：`(T)x` 到底做了什么

C 风格转型依次尝试 `const_cast`、`static_cast`、`static_cast` 加 `const_cast`、`reinterpret_cast`、`reinterpret_cast` 加 `const_cast`，取第一个可行的（[[expr.cast#4]]）。所以 `(char*)s.data()` 静默地去掉了 `const`，写成 `static_cast<char*>(s.data())` 则编译不过，必须明确写出 `const_cast`。这条警告的价值在于让读者能看到转换的种类，详见 [[topics/casts]]。

### `-Wimplicit-fallthrough`

`switch` 的 `case` 标签本身不改变控制流，执行会从一个分支落进下一个（[[stmt.switch#6]]）。打开警告后，有意的贯穿要写 `[[fallthrough]];`，这正是标准推荐的协议（[[dcl.attr.fallthrough#2]]）。Clang 的提示同时给出了两种修正：加 `[[fallthrough]];` 或加 `break;`。

### `-Wnull-dereference`：Clang 里的范围很窄

Clang 的 `-Wnull-dereference` 默认打开，但它只看字面上的空指针：

```cpp title="nd.cpp"
struct Node { int value; Node* next; };
int f() { return *(int*)nullptr; }              // 警告
int g() { Node* n = nullptr; return n->value; } // 不警告
int h() { int* p = 0; return *p; }              // 不警告
```

```text
nd.cpp:2:18: warning: indirection of non-volatile null pointer will be deleted, not trap [-Wnull-dereference]
```

经过一个变量的空指针，编译器的警告就看不到了。下文的静态分析器对三个函数都报告了 `core.NullDereference`。据 GCC 文档，GCC 的同名选项依赖优化期间的数据流分析，范围不同，本机没有验证。

### `-Wdangling` 与 `[[clang::lifetimebound]]`

编译器只在一个函数内分析。如果一个函数返回的引用可能指向它的实参，调用者那一侧看不出来。`[[clang::lifetimebound]]` 把这个约定写在形参上：

```cpp title="lb.cpp" run ub
#include <map>
#include <string>
#include <string_view>

using Config = std::map<std::string, std::string>;

const std::string& get_or(const Config& c, const std::string& key,
                          const std::string& fallback) {
  auto it = c.find(key);
  return it != c.end() ? it->second : fallback;
}

const std::string& get_or_lb(const Config& c [[clang::lifetimebound]],
                             const std::string& key,
                             const std::string& fallback [[clang::lifetimebound]]) {
  auto it = c.find(key);
  return it != c.end() ? it->second : fallback;
}

std::size_t demo(const Config& c) {
  const std::string& a = get_or(c, "port", "8080");     // 悬垂，无警告
  const std::string& b = get_or_lb(c, "port", "8080");  // 悬垂，有警告
  return a.size() + b.size();
}

int main() { Config c; return demo(c) == 8 ? 0 : 1; }
```

`"8080"` 构造出的临时 `std::string` 在完整表达式结束时销毁，`a` 和 `b` 都悬垂。只有加了注解的版本得到警告：

```text
lb.cpp:22:47: warning: temporary bound to local reference 'b' will be destroyed at the end of the full-expression [-Wdangling]
```

ASan 在运行时对 `a.size()` 报告 `stack-use-after-scope`。libc++ 给 `std::min`、`std::max`、`std::move` 等函数的形参加了这个注解，所以 `const int& m = std::max(1, 2);` 也能得到警告。哪些悬垂情形能被警告抓住，见 [[topics/dangling-references]]。

Clang 没有名为 `-Wlifetimebound` 的选项；注解为 `-Wdangling` 系列提供信息。Clang 23 另有一组默认关闭的生命周期分析 `-Wlifetime-safety`，其中 `-Wlifetime-safety-suggestions` 会建议在哪里加注解。本机在上例上加 `-Wlifetime-safety-all` 的结果：

```text
lb.cpp:7:42: warning: parameter in intra-TU function should be marked [[clang::lifetimebound]] [-Wlifetime-safety-intra-tu-suggestions]
lb.cpp:10:10: note: param returned here
lb.cpp:8:54: warning: parameter in intra-TU function should be marked [[clang::lifetimebound]] [-Wlifetime-safety-intra-tu-suggestions]
lb.cpp:10:10: note: param returned here
lb.cpp:22:47: warning: temporary object does not live long enough [-Wlifetime-safety-use-after-scope]
```

### `-Wthread-safety`：把加锁约定写成注解

数据竞争是 UB（[[intro.races#17]]）。哪个成员由哪个互斥量保护，原本只写在注释里。Clang 的线程安全分析让它成为可检查的注解：

```cpp title="ts.cpp"
#include <mutex>

#define GUARDED_BY(m) __attribute__((guarded_by(m)))
#define REQUIRES(m)   __attribute__((requires_capability(m)))

class Counter {
  std::mutex mu_;
  long hits_ GUARDED_BY(mu_) = 0;
  void bump() REQUIRES(mu_) { ++hits_; }
public:
  void hit() {
    std::lock_guard g(mu_);
    bump();
  }
  long peek() { return hits_; }   // 没加锁
  void hit_capped() {
    mu_.lock();
    if (hits_ >= 100) return;     // 提前返回，锁没释放
    bump();
    mu_.unlock();
  }
  void reset() { bump(); }        // 调用者没持有锁
};
```

```text
$ clang++ -std=c++2c -Wall -Wextra -pedantic -Wthread-safety -fsyntax-only ts.cpp
ts.cpp:15:24: warning: reading variable 'hits_' requires holding mutex 'mu_' [-Wthread-safety-analysis]
ts.cpp:21:3: warning: mutex 'mu_' is not held on every path through here [-Wthread-safety-analysis]
ts.cpp:17:9: note: mutex acquired here
ts.cpp:22:18: warning: calling function 'bump' requires holding mutex 'mu_' exclusively [-Wthread-safety-analysis]
```

本机的 libc++ 已经给 `std::mutex`、`std::lock_guard` 加上了能力（capability）注解，所以只需要标注被保护的数据和函数的前置条件。分析是静态的、按函数进行的：它检查每条路径上是否持有正确的锁，不检查实际的线程交错，也不理解原子操作。运行时的竞争检测用 TSan，见 [[topics/memory-model]]。

## `-Werror` 与第三方代码

`-Werror` 把警告变成错误。建议在 CI 中打开，在开发者本地和发布给用户的构建脚本中关闭：新版本编译器会增加警告，写死的 `-Werror` 会让下游用户在新编译器上无法构建。CMake 3.24 起的 `CMAKE_COMPILE_WARNING_AS_ERROR` 就是为此设计的（见 [[toolchain/cmake]]）。

第三方头文件不该让你的构建失败。`-isystem` 引入的目录被视为系统头文件，其中产生的警告不显示。下面的头文件里有一个旧式转型和一个弃用的函数：

```cpp title="third_party/legacy/legacy.h"
#pragma once
inline int legacy_scale(double x) { return (int)(x * 100); }
[[deprecated("use parse_v2")]] inline int parse_v1(const char*) { return 0; }
```

```cpp title="app.cpp"
#include <legacy/legacy.h>
int run(double x) { return legacy_scale(x) + parse_v1("1"); }
```

```text
$ W="-Wall -Wextra -pedantic -Wconversion -Wold-style-cast -Werror"
$ clang++ -std=c++2c $W -Ithird_party -fsyntax-only app.cpp
third_party/legacy/legacy.h:2:44: error: use of old-style cast [-Werror,-Wold-style-cast]
app.cpp:2:46: error: 'parse_v1' is deprecated: use parse_v2 [-Werror,-Wdeprecated-declarations]
$ clang++ -std=c++2c $W -isystem third_party -fsyntax-only app.cpp
app.cpp:2:46: error: 'parse_v1' is deprecated: use parse_v2 [-Werror,-Wdeprecated-declarations]
$ clang++ -std=c++2c $W -Wno-error=deprecated-declarations -isystem third_party -fsyntax-only app.cpp
app.cpp:2:46: warning: 'parse_v1' is deprecated: use parse_v2 [-Wdeprecated-declarations]
```

第一条来自头文件内部，`-isystem` 消除了它。第二条在你自己的代码里调用了弃用函数，这是你的问题，不会被消除。`-Wno-error=<名字>` 让这一类警告保持为警告，适合迁移期间。CMake 中导入的目标（`find_package` 得到的）默认以 `-isystem` 引入，自己的子目录可以用 `target_include_directories(... SYSTEM ...)`。

模板是个例外：系统头文件中的模板在你的代码里实例化时，有些警告仍会显示，`-Wdelete-non-virtual-dtor` 指向 `unique_ptr.h` 就是一例。

无法改动包含方式时，可以在包含处局部关闭：

```cpp
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wold-style-cast"
#include <legacy/legacy.h>
#pragma clang diagnostic pop
```

!!! pitfall "未知的警告选项"
    给编译器传入它不认识的 `-W...` 选项时，Clang 给出 `-Wunknown-warning-option` 警告。打开 `-Werror` 后它也变成错误，所以用新版编译器的警告名写成的构建脚本，在旧版编译器上会直接失败。跨编译器版本的项目可以用 CMake 的 `check_cxx_compiler_flag` 检测后再添加。

## clang-tidy

clang-tidy 用 Clang 的前端解析源文件，然后对 AST 运行一组检查（check）。它能发现编译器警告不覆盖的问题：惯用法、性能、可以现代化的写法、已知的 bug 模式。Homebrew 的 LLVM 自带它：

```text
$ clang-tidy --version
Homebrew LLVM version 23.1.3
$ clang-tidy --list-checks --checks='*' | wc -l       # 约 600 个检查
```

检查按前缀分组。本机的数量：`bugprone-*` 109 个，`performance-*` 22 个，`modernize-*` 49 个，`cppcoreguidelines-*` 43 个，`readability-*` 62 个，`clang-analyzer-*` 131 个（即下文的静态分析器）。

### 在一个小文件上运行

```cpp title="inventory.cpp"
#include <algorithm>
#include <map>
#include <string>
#include <utility>
#include <vector>

struct Item {
  std::string name;
  int count;
};

class Inventory {
public:
  virtual ~Inventory() = default;
  virtual void add(std::string name, int n) {
    items_.push_back(Item{name, n});
  }
  std::vector<std::string> names() const {
    std::vector<std::string> out;
    for (int i = 0; i < items_.size(); ++i)
      out.push_back(items_[i].name);
    return out;
  }
  double average() const {
    int total = 0;
    for (auto it : items_) total += it.count;
    return total / items_.size();
  }
  void prune() {
    std::remove_if(items_.begin(), items_.end(),
                   [](const Item& it) { return it.count == 0; });
  }
private:
  std::vector<Item> items_;
};

class Logged : public Inventory {
public:
  void add(std::string name, int n) {
    log_.push_back(std::move(name));
    Inventory::add(name, n);
  }
private:
  std::vector<std::string> log_;
};
```

编译器加 `-Wall -Wextra` 只给出两条：第 20 行的有符号与无符号比较，以及第 30 行丢弃了 `remove_if` 的返回值（libc++ 给它标了 `[[nodiscard]]`）。clang-tidy 打开四组检查：

```text
$ clang-tidy --checks='-*,bugprone-*,performance-*,modernize-*,cppcoreguidelines-*' \
    inventory.cpp -- -std=c++20
inventory.cpp:12:7: warning: class 'Inventory' defines a default destructor but does not define a copy constructor, a copy assignment operator, a move constructor or a move assignment operator [cppcoreguidelines-special-member-functions]
inventory.cpp:16:26: warning: use designated initializer list to initialize 'Item' [modernize-use-designated-initializers]
inventory.cpp:16:27: warning: parameter 'name' of type 'std::string' (aka 'basic_string<char>') is passed by value and only copied once; consider moving it to avoid unnecessary copies [performance-unnecessary-value-param]
inventory.cpp:18:3: warning: function 'names' should be marked [[nodiscard]] [modernize-use-nodiscard]
inventory.cpp:18:28: warning: use a trailing return type for this function [modernize-use-trailing-return-type]
inventory.cpp:20:5: warning: use range-based for loop instead [modernize-loop-convert]
inventory.cpp:21:7: warning: 'push_back' is called inside a loop; consider pre-allocating the container capacity before the loop [performance-inefficient-vector-operation]
inventory.cpp:21:27: warning: possibly unsafe 'operator[]', consider bounds-safe alternatives [cppcoreguidelines-pro-bounds-avoid-unchecked-container-access]
inventory.cpp:24:3: warning: function 'average' should be marked [[nodiscard]] [modernize-use-nodiscard]
inventory.cpp:24:10: warning: use a trailing return type for this function [modernize-use-trailing-return-type]
inventory.cpp:26:15: warning: loop variable is copied but only used as const reference; consider making it a const reference [performance-for-range-copy]
inventory.cpp:27:12: warning: narrowing conversion from 'size_type' (aka 'unsigned long') to 'double' [bugprone-narrowing-conversions,cppcoreguidelines-narrowing-conversions]
inventory.cpp:27:12: warning: result of integer division used in a floating point context; possible loss of precision [bugprone-integer-division]
inventory.cpp:30:5: warning: the value returned by this function should not be disregarded; neglecting it may lead to errors [bugprone-unused-return-value]
inventory.cpp:30:5: warning: use a ranges version of this algorithm [modernize-use-ranges]
inventory.cpp:31:20: warning: use a trailing return type for this lambda [modernize-use-trailing-return-type]
inventory.cpp:39:8: warning: annotate this function with 'override' or (rarely) 'final' [cppcoreguidelines-explicit-virtual-functions,modernize-use-override]
inventory.cpp:41:20: warning: 'name' used after it was moved [bugprone-use-after-move]
Suppressed 2471 warnings (2470 in non-user code, 1 with check filters).
```

这 18 条的价值相差很大：

- 真正的缺陷：`bugprone-use-after-move`（第 41 行把已被移走的 `name` 传给基类，基类收到的通常是空字符串）；`bugprone-integer-division`（`average` 先做整数除法再转成 `double`，小数部分丢了）；`bugprone-unused-return-value`（`remove_if` 不删除元素，只返回新的末尾，必须再调用 `erase`，或者改用 `std::erase_if`）。
- 性能问题：按值传参后复制、循环中逐个 `push_back`、范围 `for` 复制元素。
- 现代化写法：`override`、范围 `for`、`ranges` 算法。其中 `override` 值得强制，它让签名不匹配变成编译错误。
- 风格偏好：尾置返回类型、到处加 `[[nodiscard]]`、指定初始化器、禁止 `operator[]`。这些是否采用取决于项目，建议关掉。

`Suppressed 2471 warnings` 说明 clang-tidy 也检查了标准库头文件，但默认只显示用户代码中的结果。

clang-tidy 被移动后的对象使用的判断是保守的：标准库类型被移动后处于有效但未指定的状态，读取它不是 UB，但几乎总是逻辑错误。

### 配置文件 `.clang-tidy`

把选择写进项目根目录的 `.clang-tidy`，clang-tidy 从源文件所在目录向上查找它：

```yaml title=".clang-tidy"
Checks: >
  -*,
  bugprone-*,
  performance-*,
  modernize-*,
  cppcoreguidelines-*,
  -modernize-use-trailing-return-type,
  -modernize-use-nodiscard,
  -modernize-use-designated-initializers,
  -cppcoreguidelines-pro-bounds-avoid-unchecked-container-access,
  -cppcoreguidelines-avoid-magic-numbers
WarningsAsErrors: 'bugprone-use-after-move,bugprone-unused-return-value'
HeaderFilterRegex: '^.*/(src|include)/.*'
CheckOptions:
  cppcoreguidelines-special-member-functions.AllowSoleDefaultDtor: true
```

`Checks` 先用 `-*` 关闭全部，再按组打开、逐个排除。`WarningsAsErrors` 只把确定是缺陷的检查升级为错误，此时 clang-tidy 的退出码为 1，可以让 CI 失败。`HeaderFilterRegex` 决定显示哪些头文件中的结果。`CheckOptions` 调整单个检查，这里允许只声明一个 `= default` 的虚析构函数而不写其他特殊成员。用这个配置运行，剩下 10 条，其中两条变成了错误：

```text
inventory.cpp:30:5: error: the value returned by this function should not be disregarded; neglecting it may lead to errors [bugprone-unused-return-value,-warnings-as-errors]
inventory.cpp:41:20: error: 'name' used after it was moved [bugprone-use-after-move,-warnings-as-errors]
```

### 编译数据库 `compile_commands.json`

上面在 `--` 之后手写了编译选项。真实项目里每个文件的包含路径、宏和标准版本都不同，clang-tidy 需要知道它们才能像编译器一样解析。CMake 加 `CMAKE_EXPORT_COMPILE_COMMANDS ON` 后在构建目录写出编译数据库：

```text
$ cmake -S . -B build -G Ninja -DCMAKE_CXX_COMPILER=clang++
$ cat build/compile_commands.json
[
{
  "directory": "<proj>/build",
  "command": "clang++ -std=gnu++20 -isysroot <sdk> -Wall -Wextra -Wpedantic -o CMakeFiles/inv.dir/src/inventory.cpp.o -c <proj>/src/inventory.cpp",
  "file": "<proj>/src/inventory.cpp",
  "output": "CMakeFiles/inv.dir/src/inventory.cpp.o"
}
]
$ clang-tidy -p build src/inventory.cpp
...
Suppressed 2453 warnings (2451 in non-user code, 2 with check filters).
```

`-p` 指向包含 `compile_commands.json` 的目录。编译数据库里的 `-Wall` 等选项产生的编译器警告在 clang-tidy 中以 `clang-diagnostic-*` 检查的形式出现，上面的配置没有打开它们，所以被过滤（`2 with check filters`）。对整个项目并行运行用 `run-clang-tidy -p build`。CMake 也可以在每次编译时顺带运行 clang-tidy，见 [[toolchain/cmake]]。

`--fix` 让 clang-tidy 直接应用检查提供的修改。本机只打开 `modernize-use-override`、`performance-for-range-copy`、`modernize-loop-convert` 三项运行后的差异：

```diff
-    for (int i = 0; i < items_.size(); ++i)
-      out.push_back(items_[i].name);
+    for (const auto & item : items_)
+      out.push_back(item.name);
...
-    for (auto it : items_) total += it.count;
+    for (const auto& it : items_) total += it.count;
...
-  void add(std::string name, int n) {
+  void add(std::string name, int n) override {
```

自动修改应当按检查分批进行并逐个审阅。修改后的格式不一定符合项目风格（注意 `const auto & item` 的空格），之后可以再跑一次 clang-format。

## Clang 静态分析器

编译器警告和大多数 clang-tidy 检查都是在语法树上匹配模式。**静态分析器**（Clang Static Analyzer）不同，它对每个函数做符号执行：沿着每条可能的路径前进，记录每个变量可能的取值，在某条可行路径上出现空指针解引用、内存泄漏、使用已释放内存时报告。所以它的报告附带一条路径。

```cpp title="cache.cpp"
#include <cstdio>

struct Entry { int key; char* value; };

int key_of(const Entry* e, bool verbose) {
  if (verbose && !e)
    std::puts("no entry");
  return e->key;
}

char* load(const char* path) {
  char* buf = new char[256];
  std::FILE* f = std::fopen(path, "r");
  if (!f) return nullptr;
  std::size_t got = std::fread(buf, 1, 255, f);
  std::fclose(f);
  buf[got] = '\0';
  return buf;
}
```

编译器加 `-Wall -Wextra -pedantic -Wconversion` 没有警告。`clang++ --analyze` 运行分析器，`--analyzer-output text` 把路径打印在终端上：

```text
$ clang++ -std=c++2c --analyze --analyzer-output text cache.cpp
cache.cpp:8:10: warning: Access to field 'key' results in a dereference of a null pointer (loaded from variable 'e') [core.NullDereference]
cache.cpp:6:7: note: Assuming 'verbose' is true
cache.cpp:6:7: note: Left side of '&&' is true
cache.cpp:6:18: note: Assuming 'e' is null
cache.cpp:6:3: note: Taking true branch
cache.cpp:8:10: note: Access to field 'key' results in a dereference of a null pointer (loaded from variable 'e')
cache.cpp:14:18: warning: Potential leak of memory pointed to by 'buf' [cplusplus.NewDeleteLeaks]
cache.cpp:12:15: note: Memory is allocated
cache.cpp:14:8: note: 'f' is null
cache.cpp:14:3: note: Taking true branch
cache.cpp:14:18: note: Potential leak of memory pointed to by 'buf'
```

第一个报告的推理是：代码检查了 `!e`，说明作者认为 `e` 可能为空；在这条分支上继续执行，就会解引用空指针。如果 `e` 从不为空，那个检查就是多余的。第二个报告找到了 `fopen` 失败的路径上没有释放 `buf`，修正方式是用 `std::unique_ptr<char[]>` 或 `std::vector<char>`，见 [[topics/ownership-and-smart-pointers]]。

对整个构建运行时，用 `scan-build` 包住构建命令。它把编译器替换为一个同时运行分析器的包装，最后生成 HTML 报告：

```text
$ scan-build -o report clang++ -std=c++2c -c cache.cpp -o cache.o
scan-build: Using '/opt/homebrew/Cellar/llvm/23.1.3_2/bin/clang-23' for static analysis
cache.cpp:8:10: warning: Access to field 'key' results in a dereference of a null pointer (loaded from variable 'e') [core.NullDereference]
cache.cpp:14:18: warning: Potential leak of memory pointed to by 'buf' [cplusplus.NewDeleteLeaks]
2 warnings generated.
scan-build: Analysis run complete.
scan-build: 2 bugs found.
scan-build: Run 'scan-view report/2026-10-19-190212-55347-1' to examine bug reports.
```

scan-build 通过替换 `CC`、`CXX` 起作用，而 CMake 在配置时就记下了编译器路径，所以 CMake 项目要在 scan-build 之下重新配置一个构建目录：`scan-build cmake -S . -B build-scan -G Ninja`，然后 `scan-build -o report cmake --build build-scan`。本机把 `cache.cpp` 加进上一节的 CMake 项目后这样运行，结果同样是 `2 bugs found`。clang-tidy 的 `clang-analyzer-*` 检查运行的是同一个分析器。

!!! impl "分析器为了减少误报而放弃的报告"
    分析器会内联被调用的函数。如果空指针来自被内联函数的某个 `return nullptr`，默认不报告：这类路径往往在实际中不会出现，报告出来大多是误报。例如 `Entry* e = find(table, n, key); return e->key;`，在 `find` 找不到时返回空指针，本机默认不报告，加 `-Xclang -analyzer-config -Xclang suppress-null-return-paths=false` 后才报告。分析器在每个函数上的探索步数也有上限，路径太多时会提前停止。所以没有报告不代表没有缺陷。

## clang-format

clang-format 只处理格式，不改变语义。它的价值是让格式不再出现在代码评审里：

```text
$ cat .clang-format
BasedOnStyle: LLVM
IndentWidth: 2
ColumnLimit: 80
$ cat fmt.cpp
int  f(int a,int b){if(a>b) return a; else return b;}
$ clang-format fmt.cpp
int f(int a, int b) {
  if (a > b)
    return a;
  else
    return b;
}
$ clang-format --dry-run -Werror fmt.cpp; echo $?
fmt.cpp:1:4: error: code should be clang-formatted [-Wclang-format-violations]
...
1
```

`-i` 原地修改，`--dry-run -Werror` 只检查，适合放进 CI。`git clang-format` 只格式化暂存区中改动过的行，适合逐步接入已有的代码库。

## 静态分析做不到的事

静态分析在不运行程序的情况下推理，它的局限有两个来源。

第一，它一次只看一个翻译单元。两个 `.cpp` 文件各自定义了成员不同的 `struct Config`，每个文件单独看都正确，编译器、clang-tidy、分析器都不会报告；这是 IFNDR（[[basic.def.odr#16]]），链接器通常也静默接受，见 [[toolchain/linking-and-symbols]] 和 [[toolchain/dependencies]]。

第二，它不知道运行时的数据。下标是否越界、乘法是否溢出、两个线程是否真的同时访问，都取决于输入。分析器只能在代码本身暗示了某种可能（比如检查过 `!e`）时报告，否则为了避免误报保持沉默。

这些问题要靠运行时工具：ASan 检测越界和使用已释放内存，UBSan 检测有符号溢出、非法移位等核心语言 UB，TSan 检测数据竞争（概览见 [[topics/undefined-behavior]]）。sanitizer 只能发现被执行到的路径上的问题，所以要和测试配合，见 [[toolchain/testing|测试]]；问题出现之后怎样定位，见 [[toolchain/debugging|调试]]。

| 手段 | 什么时候运行 | 典型发现 | 漏报来源 |
|---|---|---|---|
| 编译器警告 | 每次编译 | 隐式转换、遮蔽、贯穿、悬垂的临时量 | 只看函数内，只认已知模式 |
| 注解 + 警告 | 每次编译 | 违反加锁约定、通过注解形参的悬垂 | 没加注解的代码 |
| clang-tidy | CI、编辑器 | 使用被移动的对象、整数除法、性能问题 | 按模式匹配 |
| 静态分析器 | CI（较慢） | 路径上的空指针、泄漏、double free | 为抑制误报主动放弃，探索有上限 |
| sanitizer | 测试运行时 | 越界、UB、数据竞争 | 只覆盖执行到的路径 |

## 思考题

!!! question "1"
    Clang 默认接受 `char data[0];` 而不给出任何诊断。这违反标准吗？加上 `-Wall -Wextra` 呢？

<details markdown="1">
<summary>答案</summary>

违反。数组大小必须大于零（[[dcl.array#1]]），这是可诊断规则，[[intro.compliance.general#2]] 要求至少一条诊断；实现可以把它作为扩展接受，但 ¶11 要求仍然诊断。本机 Clang 默认和加 `-Wall -Wextra` 都不诊断，加 `-pedantic` 才给出 `-Wzero-length-array` 警告。警告就满足了诊断的要求，编译继续进行也不违反标准。
</details>

!!! question "2"
    `std::uint8_t b = 300;` 能编译，`std::uint8_t b{300};` 不能。为什么？`-Wconversion` 对前者说了什么？

<details markdown="1">
<summary>答案</summary>

两者都要把 `int` 转换为 `unsigned char`。转换本身有定义，结果是模 256 后的 44（[[conv.integral#3]]）。但在列表初始化中，值不能被目标类型表示的常量转换是窄化转换，非良构（[[dcl.init.list#3]]、[[dcl.init.list#7]]），编译器必须诊断。复制初始化没有这条限制。对前者，Clang 默认就给出常量溢出的警告（`-Wconstant-conversion`），`-Wconversion` 则对非常量的同类转换也给出 `-Wimplicit-int-conversion`。
</details>

!!! question "3"
    给 `ts.cpp` 的 `peek` 加上 `std::lock_guard g(mu_);` 后，`-Wthread-safety` 不再报告。这能说明 `Counter` 没有数据竞争吗？

<details markdown="1">
<summary>答案</summary>

不能。分析只检查被注解为 `GUARDED_BY` 的成员在访问时是否持有对应的锁。没有注解的成员、通过指针或引用逃出类的数据、在锁外读到的旧值引出的逻辑错误，都不在它的范围内。数据竞争是运行时的性质（[[intro.races#17]]），需要 TSan 在真实的线程交错下检测。
</details>

## 小结

| 问题 | 建议 |
|---|---|
| 基本警告 | `-Wall -Wextra -Wpedantic`，加上 `-Wconversion -Wshadow -Wnon-virtual-dtor -Wold-style-cast -Wimplicit-fallthrough` |
| `-Weverything` | 用来浏览有哪些警告，不用于构建 |
| `-Werror` | CI 中打开；第三方头文件用 `-isystem`；迁移期用 `-Wno-error=…` |
| 编译器看不到的约定 | `[[clang::lifetimebound]]`、线程安全注解、`[[nodiscard]]` |
| clang-tidy | `.clang-tidy` 中启用 `bugprone`、`performance`，挑选 `modernize`、`cppcoreguidelines`；`-p` 指向编译数据库 |
| 路径相关的缺陷 | `clang++ --analyze`、`scan-build`、`clang-analyzer-*` |
| 格式 | `.clang-format` + CI 中的 `--dry-run -Werror` |
| 静态分析之外 | 跨 TU 的 ODR、依赖输入的 UB：sanitizer 加测试 |
