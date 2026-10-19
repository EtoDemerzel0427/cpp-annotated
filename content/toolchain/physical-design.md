---
title: 物理设计：头文件与依赖
summary: 头文件和源文件怎样组织才能让项目既能编译又编译得快：#include 的文本替换和它的代价，include guard 与 #pragma once，自包含的头文件，前置声明能做什么、不能做什么，头文件里的 inline、static 与无名命名空间，模板的显式实例化，依赖图、循环依赖与层次化，以及模块这条出路。
group: 工程实践
status: draft
order: 100
since: c++98
related: cpp.include, lex.separate, using.headers, res.on.headers, basic.def.odr, dcl.inline, basic.link, namespace.std, iosfwd.syn, temp.pre, temp.explicit, temp.inst, toolchain/compilation-pipeline, toolchain/linking-and-symbols, toolchain/modules-in-practice, toolchain/build-speed, toolchain/library-boundaries, patterns/pimpl
tags: 工具链, 头文件, 前置声明, ODR, 编译时间, 依赖
updated: 2026-10-19
---

!!! tldr
    - `#include` 把整个文件原样复制进来，每个翻译单元都要从头处理一遍。本机一个 `#include <vector>` 展开成约 2.4 万行，`<iostream>` 约 3.5 万行，这部分开销乘以包含它的翻译单元个数。
    - 每个头文件都应当自包含：单独作为翻译单元的第一行也能编译。靠别的头文件顺带引入的声明属于不要求诊断的违规，换一个标准版本或库版本就可能编译失败。
    - 前置声明让使用者只依赖一个名字，适用于指针、引用和函数声明；需要大小、成员或基类时必须看到定义。不要前置声明 `std` 里的东西，用 `<iosfwd>` 这类库自带的前置声明头文件。
    - 头文件里的函数和变量定义要用 `inline`（或者是模板、constexpr），否则多个翻译单元链接时重复定义。`static` 和无名命名空间让每个翻译单元各得一份副本，数据会重复，可变状态也不再共享。
    - 模板可以在头文件里只留声明，用 `extern template` 加一个 `.cpp` 中的显式实例化把实例化集中到一处。本机实验中，8 个使用者翻译单元的编译时间合计降到原来的约四分之一。

!!! note "实验环境"
    输出与数字来自本机：Apple M2 Pro，macOS，Homebrew Clang 23.1.3 + libc++，CMake 3.29，Ninja 1.12。编译时间是进程的用户态加内核态 CPU 时间，取多次运行的最小值；机器上同时有其他负载，数字只用于比较量级。本机没有安装 include-what-you-use，用的是 LLVM 自带的 `clang-include-cleaner`。

## `#include` 是文本替换

```cpp run title="ndebug.cpp" ok
#include <cassert>
void checked(int x) { assert(x > 0); }

#define NDEBUG
#include <cassert>
void unchecked([[maybe_unused]] int x) { assert(x > 0); }

int main() { unchecked(-1); checked(1); }
```

同一个头文件包含两次，得到两种 `assert`。第一次包含时 `NDEBUG` 没有定义，`assert` 展开成检查；第二次包含时定义了 `NDEBUG`，`assert` 展开成空。程序运行后正常退出，`unchecked(-1)` 没有触发断言。

标准规定，`#include` 指令被所指文件的全部内容替换（[[cpp.include#3]]），被包含的文件再递归地经过预处理。源文件加上它直接和间接包含的所有内容，叫做**预处理翻译单元**（[[g:preprocessing-translation-unit|preprocessing translation unit]]，[[lex.separate#1]]）。头文件没有自己的作用域，也不会被单独编译，它的意义完全取决于被粘贴到哪里、粘贴之前定义了哪些宏。`<cassert>` 是标准特意设计成每次包含都重新生效的头文件（[[using.headers#2]]），其他标准头文件包含多次和包含一次效果相同。

预处理的输出、行标记和头文件搜索路径见 [[toolchain/compilation-pipeline]]。这里关心的是这种模型对项目组织的影响。

### 每个翻译单元重新处理一遍

编译器每次只看一个翻译单元（TU），TU 之间不共享任何解析结果。10 个 `.cpp` 都包含 `<format>`，`<format>` 就要被预处理、解析、做语义分析 10 次。下表是本机对只含一行 `#include <h>` 加一个空 `main` 的文件的测量：行数是 `clang++ -std=c++2c -E -P` 输出的非空行数，文件数是 `-H` 列出的包含记录，时间是 `-fsyntax-only` 的 CPU 时间（不做代码生成）。

| 头文件 | 预处理后行数 | 包含记录（不同文件） | CPU 时间 |
|---|---:|---:|---:|
| （无） | 1 | 0 | 33 ms |
| `<cstddef>` | 137 | 43（36） | 34 ms |
| `<iosfwd>` | 254 | 45（45） | 34 ms |
| `<utility>` | 4 026 | 195（185） | 55 ms |
| `<string_view>` | 9 575 | 391（337） | 85 ms |
| `<memory>` | 11 272 | 360（317） | 92 ms |
| `<string>` | 13 958 | 457（387） | 143 ms |
| `<map>` | 15 863 | 443（376） | 117 ms |
| `<vector>` | 23 565 | 550（449） | 156 ms |
| `<algorithm>` | 24 028 | 827（600） | 166 ms |
| `<ranges>` | 23 710 | 601（474） | 166 ms |
| `<format>` | 29 990 | 718（565） | 256 ms |
| `<print>` | 30 120 | 720（567） | 295 ms |
| `<iostream>` | 35 487 | 759（597） | 342 ms |
| `<chrono>` | 40 958 | 809（637） | 338 ms |

空文件的 33 ms 是启动编译器本身的开销。一个包含 `<iostream>` 的 TU，在写下第一行自己的代码之前已经花掉了约 0.3 秒 CPU 时间。项目里有几百个 TU 时，这就是全量构建时间的主要部分。

包含记录比不同文件多，是因为有些文件进入了不止一次。例如 Clang 自带的 `<stddef.h>` 设计成可以多次包含，按调用方事先定义的 `__need_*` 宏每次提供不同的子集。

### `<vector>` 为什么比 `<string>` 还大

把预处理输出按行标记归到来源文件，再按 libc++ 的子目录汇总，可以看出这些行从哪里来：

```text
$ printf '#include <vector>\n' > v.cpp
$ python3 attr.py v.cpp          # 按 "# 行号 文件" 行标记统计每个文件贡献的非空行
total 23564
  3604  15.3% __format/
  2488  10.6% __algorithm/
  2341   9.9% string
  2084   8.8% __vector/
  1809   7.7% __iterator/
  1377   5.8% __type_traits/
  1050   4.5% __memory/
   935   4.0% (C/SDK headers)
   ...
```

`<vector>` 自己的实现（`__vector/`）只占 9%。最大的一块是 `__format/`，它来自 C++23 的 `vector<bool>::reference` 格式化器：libc++ 的 `<vector>` 在 `_LIBCPP_STD_VER >= 23` 时包含 `__vector/vector_bool_formatter.h`，后者包含 `__format/formatter.h`，进而拉进了 `<string>`。按标准版本测同一个文件：

```text
$ for s in 17 20 23 2c; do echo "c++$s $(clang++ -std=c++$s -E -P v.cpp | grep -c .)"; done
c++17 12588
c++20 15719
c++23 23426
c++2c 23564
```

`<algorithm>` 是另一种结构。libc++ 把每个算法放在 `__algorithm/` 下的单独文件里，本机这个目录有 209 个文件，`<algorithm>` 全部包含，它们贡献了 46% 的行。而 `<vector>` 只用到其中 39 个。

```text
$ printf '#include <algorithm>\n' > al.cpp && python3 attr.py al.cpp
total 24027
 11081  46.1% __algorithm/
  1748   7.3% __iterator/
  1400   5.8% __type_traits/
  ...
```

这些数字是 libc++ 23 的实现细节，libstdc++ 和 MSVC STL 的拆分方式不同。可以确定的一点是，标准只规定每个头文件至少提供哪些声明，允许它包含其他标准头文件（[[res.on.headers#1]]），所以标准库头文件的实际开销只能测，不能从标准推出来。

## 防止重复包含

```text
point.h            shapes.h               main.cpp
struct Point {…};  #include "point.h"     #include "point.h"
                   struct Rect {…};       #include "shapes.h"
```

```text
$ clang++ -std=c++2c -fsyntax-only main.cpp
In file included from main.cpp:2:
In file included from ./shapes.h:1:
./point.h:1:8: error: redefinition of 'Point'
main.cpp:1:10: note: './point.h' included multiple times, additional include site here
```

`main.cpp` 通过两条路径包含了 `point.h`，文本替换后同一个类定义出现两次。一个 TU 中任何可定义的实体只能有一个定义（[[basic.def.odr#2]]），这条违规必须诊断。头文件之间互相包含是常态，所以每个头文件都要能承受重复包含。

<div class="compare" markdown="1">

```cpp title="point.h（include guard）"
#ifndef GEO_POINT_H
#define GEO_POINT_H

struct Point { int x, y; };

#endif
```

```cpp title="point.h（#pragma once）"
#pragma once


struct Point { int x, y; };

```

</div>

左边是 **include guard**：第一次包含时定义宏，之后再包含，`#ifndef` 让整个文件内容被跳过。它只用标准的条件编译，到处都能用。宏名要在整个项目及其依赖里唯一，复制粘贴一个头文件忘了改宏名，第二个文件就会被悄悄跳过。

右边的 `#pragma once` 不是标准的一部分。[[cpp.pragma#1]] 只说 `#pragma` 的行为由实现定义、不认识的 pragma 被忽略。GCC、Clang、MSVC 都支持它，语义是同一个文件在一个 TU 中只处理一次。

两者的分歧在于怎样判断同一个文件。include guard 看宏名，`#pragma once` 看文件本身。本机实验：

```text
$ cp a/point.h b/point.h       # 两份内容相同的 #pragma once 头文件
$ printf '#include "a/point.h"\n#include "b/point.h"\n' > two.cpp
$ clang++ -std=c++2c -fsyntax-only two.cpp
./b/point.h:2:8: error: redefinition of 'Point'

$ ln -s a/point.h c_point.h    # 符号链接指向同一个文件
$ printf '#include "a/point.h"\n#include "c_point.h"\n' > sym.cpp
$ clang++ -std=c++2c -fsyntax-only sym.cpp && echo ok
ok
```

同一个文件经过符号链接或不同的搜索路径到达，Clang 能认出来。内容相同的两个副本则被当作两个文件。如果用 include guard 且宏名相同，第二个副本会被跳过。这种情况通常出现在同一个第三方库被引入了两次，而那本身就是需要修正的问题，见 [[toolchain/dependencies|依赖管理]]。

性能上两者没有差别。Clang 和 GCC 都会识别整个文件被 `#ifndef`/`#endif` 包住的模式，记住守卫宏，之后再遇到这个文件时直接跳过，不再打开读取。上面加了 include guard 的 `main.cpp` 用 `-H` 编译，`point.h` 只列出一次，`shapes.h` 里那次包含根本没有进入文件。

!!! tip "建议"
    新项目用 `#pragma once`：少一个需要全局唯一的名字，不会因为复制文件出错。要支持不认识它的编译器，或者同一个头文件确实会以副本形式出现在多个位置时，用 include guard，宏名带上项目和路径前缀。

## 自包含的头文件

### 碰巧能编译

```cpp run title="leak.cpp" ifndr
#include <vector>

std::string greet() { return "hi"; }    // 没有 #include <string>

int main() {
  std::vector<int> v{1, 2};
  return greet().size() == v.size() ? 0 : 1;
}
```

本机 Clang 23 + libc++ 用 `-std=c++23` 或 `-std=c++2c` 编译这段代码，没有任何诊断；用 `-std=c++20` 报错：

```text
leak.cpp:3:13: error: implicit instantiation of undefined template 'std::basic_string<char>'
```

原因就是前面看到的：C++23 模式下 `<vector>` 经由格式化器间接包含了 `<string>`，C++20 模式下只间接得到 `basic_string` 的前置声明。标准允许标准头文件包含别的头文件（[[res.on.headers#1]]），但不要求它们这样做；另一方面，TU 在第一次使用某个头文件中声明的实体之前，必须自己包含这个头文件，违反时不要求诊断（[[using.headers#3]]）。依赖间接包含的程序今天能编译，升级编译器、换标准库或换 `-std` 后就可能失败。

`clang-include-cleaner` 按使用情况给出应当增删的头文件：

```text
$ clang-include-cleaner --print=changes leak.cpp -- -std=c++2c
+ <string>
```

### 自己的头文件也一样

```cpp title="include/geo/label.h"
#pragma once
#include "geo/point.h"

struct Label {
  Point at;
  std::string text;   // 依赖调用方先包含 <string>
};
```

```cpp title="src/label.cpp"
#include <string>
#include "geo/label.h"
Label make() { return {{1, 2}, "origin"}; }
```

`label.cpp` 编译通过，因为它恰好先包含了 `<string>`。另一个先包含 `label.h` 的文件就会报 `use of undeclared identifier 'std'`。这种错误往往在头文件写好很久之后，由别人在别处触发。

一个头文件如果作为 TU 的第一行也能编译，就称它是**自包含的**（self-contained）。检查方法是为每个头文件生成一个只有一行 `#include` 的 TU，单独编译。CMake 3.24 起可以自动完成这件事：

```cmake title="CMakeLists.txt"
add_library(geo src/label.cpp)
target_sources(geo PUBLIC FILE_SET HEADERS BASE_DIRS include
               FILES include/geo/point.h include/geo/label.h)
set_target_properties(geo PROPERTIES VERIFY_INTERFACE_HEADER_SETS ON)
```

```text
$ cmake --build build --target all_verify_interface_header_sets
FAILED: .../geo_verify_interface_header_sets/geo/label.h.cxx.o
In file included from .../geo_verify_interface_header_sets/geo/label.h.cxx:1:
.../include/geo/label.h:5:3: error: use of undeclared identifier 'std'
    5 |   std::string text;   // 依赖调用方先包含 <string>
      |   ^
```

CMake 为头文件集中的每个头文件生成一个 `.cxx` 文件，内容只有一行 `#include <geo/label.h>`，编译但不链接。CMake 本身的用法见 [[toolchain/cmake|CMake]]。

!!! tip "建议"
    在 `foo.cpp` 里把 `#include "foo.h"` 放在第一行。这样每次编译 `foo.cpp` 就顺带检查了 `foo.h` 是否自包含，不需要额外的构建目标。头文件和源文件都只包含自己直接用到的东西（include what you use），不依赖别人顺带引入。

## 前置声明

头文件 `car.h` 只要提到 `Engine`，最直接的做法是 `#include "engine.h"`。代价是所有包含 `car.h` 的 TU 都依赖 `engine.h` 及它包含的一切，`engine.h` 一改，它们全部重新编译。如果 `car.h` 只需要知道 `Engine` 是一个类，一行 `class Engine;` 就够了。

### 前置声明能做什么

<div class="compare" markdown="1">

```cpp title="可以" ok
class Engine;

class Car {
  Engine* engine_;
  Engine& spare_;
public:
  Car(Engine& e);
  Engine make_engine() const;
  void swap_engine(Engine e);
};
```

```cpp title="不可以" error
class Engine;

class Car {
  Engine engine_;  // error: 成员
};
struct Turbo : Engine {};  // error: 基类
auto n = sizeof(Engine);   // error
int rpm(Engine& e) {
  return e.rpm();  // error: 成员访问
}
```

</div>

`class Engine;` 声明了一个类，但没有给出定义，此时 `Engine` 是**不完整类型**（[[g:incomplete-type|incomplete type]]）。编译器知道它是一个类，不知道它的大小和成员。凡是需要大小、布局或成员的地方都要求类型完整：定义该类型的对象或非静态成员、作为基类、`sizeof`、成员访问、按值传参的函数定义或调用等，[[basic.def.odr#14]] 的注列出了完整的清单。

指针和引用的大小与所指类型无关，所以可以使用不完整类型。函数声明的形参和返回类型也可以不完整，只有函数定义和调用时才要求完整（[[dcl.fct.def.general#2]]）。左边的 `make_engine` 和 `swap_engine` 因此合法，调用它们的 TU 需要看到 `Engine` 的定义。

`unique_ptr<Impl>` 成员也能用不完整类型，但析构要求完整，特殊成员函数必须定义在 `.cpp` 里。完整的做法见 [[patterns/pimpl|pimpl]]。

### 默认实参只能写在一处

前置声明头文件里的函数声明和类模板声明，常常和正式头文件里的声明一起出现在同一个 TU 中：

```cpp title="defarg.cpp" error
// net_fwd.h
template <class T, class Alloc = void> class Buffer;
void send(const Buffer<char>& b, int flags = 0);

// net.h：又写了一遍默认实参
template <class T, class Alloc = void> class Buffer { };
void send(const Buffer<char>& b, int flags = 0);
```

```text
defarg.cpp:6:34: error: template parameter redefines default argument
defarg.cpp:7:38: error: redefinition of default argument
```

默认实参和默认模板实参本身也是可定义的项（[[basic.def.odr#1]]），一个 TU 里只能定义一次，哪怕两次的值相同（[[dcl.fct.default#4]] 的注）。所以默认实参只能放在一个头文件里，通常放在前置声明头文件里，正式头文件包含它，不再重复。

### 不要前置声明标准库

```cpp title="fwd-string.cpp" ub
namespace std { class string; }        // 自己声明 std::string
void greet(const std::string& name);

#include <string>
int main() { greet("hi"); }
```

向 `namespace std` 添加声明，除非标准另有许可，行为未定义（[[namespace.std#1]]）。这不只是形式上的规定。`std::string` 根本不是类，而是 `basic_string<char>` 的别名；libc++ 还把所有实体放在内联命名空间 `std::__1` 里。本机编译报错：

```text
.../c++/v1/stdexcept:86:30: error: reference to 'string' is ambiguous
fwd-string.cpp:1:23: note: candidate found by name lookup is 'std::string'
.../c++/v1/__fwd/string.h:45:7: note: candidate found by name lookup is 'std::__1::string'
```

就算改写成 `basic_string` 的模板声明，名字也落在 `std` 而不是 `std::__1` 里，默认模板实参也不能再写一遍。需要前置声明时，用标准库自己提供的头文件。最常用的是 `<iosfwd>`（[[iosfwd.syn]]），它声明了 `basic_ostream`、`ostream` 等流类型和 `char_traits`、`allocator`：

```cpp title="point.h"
#pragma once
#include <iosfwd>

struct Point { int x, y; };
std::ostream& operator<<(std::ostream& os, Point p);
```

```cpp title="point.cpp"
#include "point.h"
#include <ostream>

std::ostream& operator<<(std::ostream& os, Point p) {
  return os << '(' << p.x << ", " << p.y << ')';
}
```

本机 `<iosfwd>` 预处理后 253 行，`-fsyntax-only` 约 36 ms；`<ostream>` 34 488 行，约 320 ms。所有包含 `point.h` 的 TU 都省下了这个差值，只有真正输出 `Point` 的 TU 才需要包含 `<ostream>` 或 `<iostream>`。

!!! tip "建议"
    自己的库如果有很多类型会被别人前置声明，就提供一个 `foo_fwd.h`，把前置声明和默认模板实参集中在那里。使用者包含它，而不是自己手写 `class Foo;`。这样库作者以后把某个类改成模板的别名，使用者的代码不受影响。

## 头文件里的定义与 ODR

```cpp title="util.h"
#pragma once
int clamp_pct(int v) {             // 非 inline 的定义
  return v < 0 ? 0 : v > 100 ? 100 : v;
}
```

```text
$ clang++ -std=c++2c a.cpp main.cpp -o app      # 两个 TU 都包含 util.h
duplicate symbol 'clamp_pct(int)' in:
    /var/folders/.../a-c88075.o
    /var/folders/.../main-2e8c2c.o
ld: 1 duplicate symbol for architecture arm64
```

`#pragma once` 只防止一个 TU 内的重复，管不了 TU 之间。两个 TU 各自得到一份 `clamp_pct` 的定义。非 inline 的非模板函数或变量在整个程序里只能有一个定义（[[basic.def.odr#16.1]]），违反时不要求诊断，这里是链接器碰巧发现了。

加上 `inline` 就合法了。**inline 函数**（[[g:inline-function|inline function]]）可以在多个 TU 中定义，只要每处定义由相同的记号序列组成、其中的名字指向相同的实体（[[basic.def.odr#16.4]]、[[basic.def.odr#16.5]]）。它仍然是一个实体、一个地址（[[dcl.inline#2]]）。编译器把它放进弱定义，链接器从多份中保留一份：

```text
$ nm -m a.o
0000000000000000 (__TEXT,__text) external __Z1av
0000000000000018 (__TEXT,__text) weak external __Z9clamp_pcti
```

弱定义和 COMDAT 的机制见 [[toolchain/linking-and-symbols]]。头文件里可以安全地放这些定义：

| 写在头文件里 | 为什么多个 TU 不冲突 |
|---|---|
| 类、枚举的定义 | 每个 TU 最多一个定义，各 TU 的定义相同（[[basic.def.odr#16]]） |
| `inline` 函数，类内定义的成员函数 | inline（类内定义的成员函数在全局模块中隐式 inline，[[dcl.inline#5]] 的注） |
| `constexpr` 函数、`consteval` 函数 | 隐式 inline |
| `inline` 变量（C++17），`constexpr` 静态数据成员 | inline |
| 模板 | 模板及其实例化可以在多个 TU 中定义 |
| 命名空间作用域的 `const`/`constexpr` 变量 | 内部链接（[[basic.link#3.2]]），每个 TU 一份独立的对象 |

最后一行与前面几行性质不同：它不是多个定义合并成一个，而是根本就是多个实体。这正是下一节的主题。

### `static` 和无名命名空间：每个 TU 一份

```cpp title="table.h"
#pragma once
static int hits = 0;
static int table[4096] = {1, 2, 3};
static int lookup(int i) { ++hits; return table[i & 4095]; }
```

`static` 或无名命名空间（[[g:unnamed-namespace|unnamed namespace]]）给名字**内部链接**（[[g:internal-linkage|internal linkage]]，[[basic.link#3]]、[[basic.link#4]]）：这个名字只在本 TU 内指代这个实体。头文件被三个 TU 包含，就有三个互不相干的 `hits`、三张 `table`、三个 `lookup`。本机用 `-O2` 编译三个各调用一次 `lookup` 的 TU，链接后：

```text
$ ./app      # 依次调用 hits_1 三次、hits_2 和 hits_3 各一次，再打印三个 TU 中 table 的地址
3 1 1
0x104210010 0x104214010 0x104218010
$ size -m app | grep __data
	Section __data: 49160
```

第一个 TU 调用了三次，后两个各一次，计数互不影响；`table` 有三个地址，`__data` 节是 3 × 16 KiB 再加 8 字节。把三个 `static` 换成 `inline`：

```text
$ ./app2
3 4 5
0x104214014 0x104214014 0x104214014
$ size -m app2 | grep __data
	Section __data: 16396
```

现在全程序只有一个 `hits` 和一张 `table`。只读的小常量放在内部链接里问题不大，优化器通常把它们直接折进代码，用不到的副本也会被删掉。可变状态和大块数据就不行：放在 `static` 里，每个 TU 改的是自己的副本，数据也按 TU 个数重复。

!!! pitfall "inline 函数里引用无名命名空间的实体"
    ```cpp title="table.h" ifndr
    #pragma once
    namespace {
    int hits = 0;                    // 每个 TU 各有一个 hits
    }
    inline int lookup() { return ++hits; }   // 每个 TU 的定义指向不同的 hits
    ```

    `lookup` 是 inline 函数，各 TU 的定义记号相同，但其中的 `hits` 在每个 TU 里指向不同的变量，违反了 [[basic.def.odr#16.5]]，程序非良构，不要求诊断。两个 TU 各调用一次 `lookup()` 后返回自己的 `hits`，本机的结果取决于优化级别和链接顺序：

    | 编译 | 输出 |
    |---|---|
    | `-O0`，`t1.cpp t2.cpp` 的顺序 | `1 0` |
    | `-O0`，`t2.cpp t1.cpp` 的顺序 | `0 2` |
    | `-O2`，两种顺序 | `1 1` |

    `-O0` 下没有内联，链接器保留了第一个目标文件里的 `lookup`，两个 TU 都去加那个 TU 的 `hits`。`-O2` 下各 TU 内联了自己的版本。链接器和编译器都没有报告任何问题。clang-tidy 的 `misc-anonymous-namespace-in-header` 检查会对头文件中的无名命名空间给出警告。

标准把这种声明叫做**暴露**（exposure，[[basic.link#14]]）：inline 函数的函数体提到了内部链接的实体。它出现在模块接口单元里是非良构的，出现在头文件这类其他场合则已被弃用（[[basic.link#17]]）。

## 模板：定义放在哪里

函数模板、类模板的成员函数在某个 TU 中隐式实例化时，它们的定义必须在那里可达，除非这个特化在别处被显式实例化（[[temp.pre#10]]）。所以模板的定义通常整个写在头文件里，每个使用它的 TU 都会实例化一遍、生成一遍代码，最后由链接器合并。

如果一个模板只会用到少数几组模板实参，可以把实例化集中到一个 `.cpp`：

```cpp title="stats.h"
#pragma once
#include <string>
#include <vector>

template <class T>
class Stats {
  std::vector<T> xs_;
public:
  void add(T x) { xs_.push_back(x); }
  std::string report() const;     // 定义在 stats.cpp
};
extern template class Stats<double>;
```

```cpp title="stats.cpp"
#include "stats.h"
#include <algorithm>
#include <format>

template <class T>
std::string Stats<T>::report() const {
  auto v = xs_;
  std::ranges::sort(v);
  return std::format("n={} min={} median={} max={}",
                     v.size(), v.front(), v[v.size() / 2], v.back());
}
template class Stats<double>;      // 显式实例化定义
```

`template class Stats<double>;` 是**显式实例化定义**，在 `stats.cpp` 里生成 `Stats<double>` 所有已定义成员的代码（[[temp.explicit#10]]）。头文件里的 `extern template class Stats<double>;` 是**显式实例化声明**（[[g:explicit-instantiation-declaration|explicit instantiation declaration]]，[[temp.explicit#2]]），它让 `Stats<double>` 的成员成为声明过的特化（[[temp.inst#1]]），其他 TU 不再隐式实例化它们，只留下对符号的引用：

```text
$ llvm-nm -C u1.o | grep Stats
                 U Stats<double>::report() const
```

inline 成员（如类内定义的 `add`）是例外，它们仍会在使用处实例化以便内联，只是不必生成独立的函数体（[[temp.inst#5]] 的注）。

本机测量：8 个 TU 各自使用 `Stats<double>` 并调用 `report()`，比较三种组织方式。A 是全部定义放在头文件里；B1 头文件不变，只加上 `extern template`；B2 是上面的写法，头文件只有声明。

| | `-O0` 8 个 TU 合计 | `-O2` 8 个 TU 合计 | 8 个目标文件合计（`-O0`） | `stats.cpp`（`-O2`） |
|---|---:|---:|---:|---:|
| A 隐式实例化 | 4.88 s | 7.80 s | 2934 KiB | — |
| B1 `extern template`，定义仍在头文件 | 2.84 s | 3.51 s | 63 KiB | 0.96 s |
| B2 `extern template`，定义移到 `.cpp` | 1.33 s | 1.67 s | 63 KiB | 0.90 s |

B1 省掉的是实例化和代码生成：`std::format` 的整套机制不再在每个 TU 里实例化一遍。它省不掉解析，头文件仍然包含 `<format>` 和 `<algorithm>`，每个 TU 仍要处理约 3 万行。B2 把这两个头文件也移出去，每个 TU 只剩 `<string>` 和 `<vector>`。加上 `stats.cpp` 自己的编译时间，`-O2` 下 B2 合计约 2.6 s，A 是 7.8 s。

代价有两个。第一，`report()` 不再能内联到调用方，`-O2` 下每次调用都是一次真正的函数调用。第二，模板只对列出的模板实参可用：有人用 `Stats<int>` 时，B2 的写法在链接时报未定义符号，需要在 `stats.cpp` 里再加一行显式实例化。如果某个 TU 隐式实例化需要用到一个只有显式实例化声明、而程序里没有对应显式实例化定义的特化，程序非良构，不要求诊断（[[temp.explicit#12]]）。

!!! tip "建议"
    先测再改。用 `-ftime-trace` 找出实例化最耗时的模板（见 [[toolchain/build-speed|编译速度]]），只对实参集合固定、实例化成本高的模板这样做。通用的库模板保持在头文件里。

## 依赖图

### 看见依赖

`-H` 把每次进入的头文件按嵌套深度打印到标准错误，一个点表示一层。下面是一个小项目，只保留项目自己的头文件：

```text
$ clang++ -std=c++2c -Isrc -fsyntax-only -H src/main.cpp 2>&1 | grep -v '/v1/\|^\.* /'
. src/feed/decoder.h
.. src/book/order_book.h
... src/core/ids.h
... src/core/price.h
```

这几个文件加上 `main.cpp` 一共 22 行，预处理后是 29 395 行。用几行 Python 把 `-H` 的缩进还原成边，就能交给 Graphviz 画图：

```python title="hdeps.py"
# 用法：clang++ -fsyntax-only -H ... 2>&1 | python3 hdeps.py main.cpp
import sys
stack = [sys.argv[1]]
edges = set()
for line in sys.stdin:
    if not line.startswith('.'): continue
    dots, path = line.rstrip('\n').split(' ', 1)
    del stack[len(dots):]
    edges.add((stack[-1], path))
    stack.append(path)
print('digraph deps {')
for a, b in sorted(edges):
    if '/v1/' not in b and not b.startswith('/'):   # 只画项目内的头文件
        print(f'  "{a}" -> "{b}";')
print('}')
```

```text
$ clang++ -std=c++2c -Isrc -fsyntax-only -H src/main.cpp 2>&1 | python3 hdeps.py src/main.cpp
digraph deps {
  "src/book/order_book.h" -> "src/core/ids.h";
  "src/book/order_book.h" -> "src/core/price.h";
  "src/feed/decoder.h" -> "src/book/order_book.h";
  "src/main.cpp" -> "src/feed/decoder.h";
}
```

`-H` 只列出真正进入的文件。被 include guard 或 `#pragma once` 跳过的重复包含不出现，所以每个 TU 的图里不会有重复的边。

### 构建系统怎样知道要重新编译什么

构建系统用的是另一组选项。`-MD` 在编译的同时写出一个 Makefile 格式的 `.d` 文件，列出目标文件依赖的所有文件；`-MMD` 只列用户头文件，略去系统头文件：

```text
$ clang++ -std=c++2c -MMD -c a.cpp -o a.o && cat a.d
a.o: \
  /Library/Developer/CommandLineTools/SDKs/MacOSX26.sdk/SDKSettings.json \
  a.cpp customer.h order.h
```

CMake 生成的 Ninja 构建默认加 `-MD`，Ninja 读入 `.d` 文件后存进自己的数据库。前面 `geo` 项目里的 `label.cpp`：

```text
$ ninja -C build -t deps CMakeFiles/geo.dir/src/label.cpp.o | head -1
CMakeFiles/geo.dir/src/label.cpp.o: #deps 395, deps mtime ... (VALID)
$ touch include/geo/point.h && ninja -C build -n geo
[1/2] Building CXX object CMakeFiles/geo.dir/src/label.cpp.o
[2/2] Linking CXX static library libgeo.a
```

一个三行的 `.cpp` 依赖 395 个文件，其中任何一个变了它都要重新编译。头文件的依赖越宽，改一行引起的重编译就越多。

### 循环依赖

```cpp title="order.h"
#pragma once
#include "customer.h"
struct Order {
  Customer* owner;
  double total;
};
```

```cpp title="customer.h"
#pragma once
#include "order.h"
#include <vector>
struct Customer {
  std::vector<Order> orders;
  double spent() const;
};
```

两个头文件互相包含。`#pragma once` 让循环在第二次进入时停下，结果是先被包含的那个头文件看不到另一个的定义：

```text
$ clang++ -std=c++2c -fsyntax-only a.cpp      # a.cpp 先包含 customer.h
./order.h:4:3: error: unknown type name 'Customer'
$ clang++ -std=c++2c -fsyntax-only b.cpp      # b.cpp 先包含 order.h
./customer.h:5:15: error: use of undeclared identifier 'Order'
```

报错的位置随包含顺序变化，这是循环依赖的典型症状。clang-tidy 的 `misc-header-include-cycle` 能直接找出循环：

```text
$ clang-tidy --checks='-*,misc-header-include-cycle' --header-filter='.*' b.cpp -- -std=c++2c
.../customer.h:2:10: warning: circular header file dependency detected while including 'order.h', please check the include path [misc-header-include-cycle]
```

`Order` 只用到 `Customer*`，把 `order.h` 里的 `#include "customer.h"` 换成 `struct Customer;`，依赖就变成单向的 `customer.h → order.h`，两个 TU 都能编译。

### 层次化

把一对 `.h`/`.cpp` 看作一个**组件**，组件之间按包含关系连边。没有环的依赖图可以分层：不依赖项目内任何组件的在第 1 层，只依赖第 1 层的在第 2 层，以此类推。这个做法叫**层次化**（levelization），出自 John Lakos 的 *Large-Scale C++ Software Design*（1996）。

层次化的好处很具体。每一层可以只链接下层组件就单独测试；改动一个组件只影响它上面的层；构建可以按层并行。出现环时，环上的组件只能作为一个整体编译、测试和理解。

打破环的常用手段：

- 只用到指针或引用时，改用前置声明，像上面的 `Order`。
- 把两边都需要的部分提取成一个更低层的新组件。
- 把高层依赖低层的方向反过来，例如让低层通过回调或接口通知高层，而不是直接调用它。

库与库之间的依赖方向、哪些头文件算公开接口，见 [[toolchain/library-boundaries|库的边界]]。

## 模块

前面所有的问题，根源都是头文件按文本重复处理：每个 TU 重新解析、宏会泄漏进来、包含顺序可能影响含义、间接包含暴露了不该暴露的名字。C++20 的具名模块从语言层面换了一种模型：模块接口只编译一次，导入方读取编译好的结果；宏不跨越 `import`；没有导出的名字导入方看不见；模块中的 ODR 违规在定义可达时必须诊断（[[basic.def.odr#16]]）。

`import std;` 一次导入整个标准库，本机比较的结果见 [[toolchain/compilation-pipeline]]。BMI、依赖扫描、CMake 集成和目前的限制见 [[toolchain/modules-in-practice]]。模块也不隐藏类的布局，pimpl 想解决的重编译问题它只解决了一半，见 [[patterns/pimpl]]。

## 思考题

!!! question "1"
    头文件里有 `const int kLimit = 100;` 和 `inline int limit() { return kLimit; }`，被多个 TU 包含。每个 TU 的 `kLimit` 是不同的对象，`limit` 的定义里的名字指向不同的实体，这算不算 ODR 违规？把函数体改成 `return *&kLimit;` 呢？

<details markdown="1">
<summary>答案</summary>

第一种写法不算。命名空间作用域的 const 变量有内部链接（[[basic.link#3.2]]），每个 TU 各有一个 `kLimit`。但 [[basic.def.odr#16.5.1]] 专门允许 inline 定义中的名字指向内部链接的非 volatile const 对象，条件是各处类型相同、用常量表达式初始化、值相同，并且在定义中没有被 odr-use。`return kLimit;` 立即对它做左值到右值转换，不构成 odr-use。

第二种写法取了 `kLimit` 的地址，构成 odr-use，例外不再适用，程序非良构，不要求诊断。把它写成 `inline constexpr int kLimit = 100;` 就只有一个对象，两种写法都没有问题。
</details>

!!! question "2"
    下面的头文件能编译吗？包含它的 TU 写 `void f() { Tree t; }` 呢？

    ```cpp
    #include <vector>
    struct Node;
    struct Tree { std::vector<Node> kids; };
    ```

<details markdown="1">
<summary>答案</summary>

头文件本身可以。[[vector.overview#4]] 允许用不完整类型实例化 `vector`，只要分配器满足完整性要求（`std::allocator` 满足），但在引用这个 `vector` 特化的任何成员之前，元素类型必须已经完整。

`Tree t;` 需要 `Tree` 的隐式默认构造函数和析构函数，它们在这个 TU 里被隐式定义，引用了 `vector<Node>` 的构造函数和析构函数。此时 `Node` 仍不完整，违反了库的要求，行为未定义（[[res.on.functions#2]]）。本机 libc++ 在实例化 `~vector` 用到的 `size()` 时报 `arithmetic on a pointer to an incomplete type 'Node'`。解决办法是在 `.cpp` 里、`Node` 完整之后定义 `Tree` 的构造函数和析构函数，和 pimpl 的处理方式相同。
</details>

!!! question "3"
    `#pragma once` 和 include guard 都能防止同一个 TU 里的重复定义。为什么它们都不能防止 `int clamp_pct(int)` 这样的头文件定义在链接时重复？

<details markdown="1">
<summary>答案</summary>

两者的作用范围都只是一个 TU 的预处理。每个 TU 从头开始预处理，宏和 pragma 的状态不会从一个 TU 带到另一个，所以每个包含该头文件的 TU 都得到一份定义。跨 TU 的规则是 [[basic.def.odr#16.1]]：非 inline 的非模板函数在整个程序中只能定义一次。解决办法是把它声明为 `inline`，或者把定义移到一个 `.cpp` 里，头文件只留声明。
</details>

## 小结

| 问题 | 做法 | 依据 |
|---|---|---|
| 同一 TU 内重复包含 | `#pragma once` 或 include guard | [[basic.def.odr#2]]、[[cpp.pragma#1]] |
| 依赖间接包含 | 每个头文件自包含，include what you use；每个头文件单独编译一次检查 | [[using.headers#3]]、[[res.on.headers#1]] |
| 头文件依赖太宽 | 只需指针、引用、函数声明时用前置声明；流类型用 `<iosfwd>` | [[basic.def.odr#14]]、[[iosfwd.syn]] |
| 前置声明标准库 | 不要这样做 | [[namespace.std#1]] |
| 头文件里的函数、变量定义 | `inline`、`constexpr` 或模板 | [[basic.def.odr#16]]、[[dcl.inline#2]] |
| 头文件里的 `static`、无名命名空间 | 每个 TU 一份；不要用于可变状态，不要被 inline 函数引用 | [[basic.link#3]]、[[basic.def.odr#16.5]] |
| 昂贵模板的重复实例化 | `extern template` + 一个 `.cpp` 中的显式实例化，先测量 | [[temp.explicit#2]]、[[temp.pre#10]] |
| 循环依赖 | 前置声明、提取低层组件，保持依赖图无环 | — |
| 文本包含的根本代价 | 具名模块 | [[toolchain/modules-in-practice]] |
