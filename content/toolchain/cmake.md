---
title: 用 CMake 组织项目
summary: 以目标为中心的 CMake：一个库、一个可执行文件和测试，使用要求的 PRIVATE/PUBLIC/INTERFACE，语言标准与构建类型最终变成哪些编译选项，警告、sanitizer 预设、compile_commands.json，库的安装与导出，模块的构建，以及常见的反模式。
group: 工程实践
status: draft
order: 115
since: c++98
related: basic.def.odr, lex.separate, intro.compliance.general, assertions.assert, cpp.predefined, cpp.include, toolchain/compilation-pipeline, toolchain/modules-in-practice, toolchain/linking-and-symbols, toolchain/dependencies
tags: 工具链, CMake, 构建, ODR, sanitizer, 模块
updated: 2026-10-19
---

!!! tldr
    - CMake 不编译代码，它生成构建文件（如 Ninja 的 `build.ninja`），里面是一条条编译器命令。判断一段 CMake 写得对不对，最终要看它生成的命令行。
    - 设置挂在目标上，用 PRIVATE / PUBLIC / INTERFACE 说明它只影响自己、同时影响使用者，还是只影响使用者。头文件里用到的宏、包含路径和标准版本必须是 PUBLIC，否则库和使用者看到的是两个不同的类，属于不要求诊断的 ODR 违规。
    - `target_compile_features(... cxx_std_NN)` 声明最低标准并向使用者传递，`CMAKE_CXX_STANDARD` 设置项目的默认值；`CMAKE_CXX_EXTENSIONS OFF` 让 CMake 生成 `-std=c++NN` 而不是 `-std=gnu++NN`。
    - 警告选项是目标的 PRIVATE 设置；sanitizer、`-Werror`、编译器路径这类构建环境的选择放进 `CMakePresets.json`，不写进 `CMakeLists.txt`。
    - 全局的 `include_directories`、`add_definitions`、在 `CMakeLists.txt` 里改写 `CMAKE_CXX_FLAGS`、用 `file(GLOB)` 收集源文件，都会让构建依赖于目录结构或调用者，而不是目标之间的关系。

标准不规定怎样构建程序。它只说一个源文件连同它包含的头文件，去掉条件编译跳过的行，构成一个预处理翻译单元（[[lex.separate#1]]）；翻译单元可以分别翻译，再链接成程序。头文件在哪里找、用哪个语言模式、定义哪些宏，都由实现定义或由命令行决定（[[cpp.include#1]]）。

这些命令行选项改变的正是标准意义上的程序：`-D` 决定哪些行留在翻译单元里，`-std=` 决定 `__cplusplus` 的值（[[cpp.predefined#1]]）和整套语言规则。所以构建脚本的错误常常表现为语言层面的错误，最典型的是 ODR 违规。编译器驱动程序怎样把一条命令拆成预处理、编译、链接，见 [[toolchain/compilation-pipeline]]。

!!! note "实验环境"
    本机 CMake 3.29.3、Ninja 1.12.1、Homebrew Clang 23.1.3（libc++）、clang-tidy 23.1.3，Apple M2 Pro。命令行输出中源码目录记为 `<src>`，SDK 路径记为 `<sdk>`，编译器路径简写为 `clang++`，并略去了生成依赖文件的 `-MD -MT … -MF …` 参数，长命令按需折行，其余省略处用 `...` 表示。本机 `PATH` 里的 Anaconda 带有旧版 `ld` 和 `ar`（见 [[toolchain/compilation-pipeline]]），实验时把它从 `PATH` 中去掉了。MSVC 相关的选项只描述，没有在本机验证。

## 一个小项目

一个统计词频的库 `tally`，一个命令行程序，一个测试：

```text
tally/
├── CMakeLists.txt
├── CMakePresets.json
├── cmake/tallyConfig.cmake.in
├── include/tally/tally.hpp      公开头文件
├── src/tally.cpp                库的实现
├── src/split.hpp                库的私有头文件
├── app/main.cpp                 命令行程序
└── tests/tally_test.cpp         测试
```

公开头文件只用到 C++17 的 `string_view`：

```cpp title="include/tally/tally.hpp"
#pragma once
#include <cstddef>
#include <string>
#include <string_view>
#include <unordered_map>
#include <utility>
#include <vector>

namespace tally {

class Counter {
public:
  void add_text(std::string_view text);
  std::size_t count(std::string_view word) const;
  std::vector<std::pair<std::string, std::size_t>> top(std::size_t n) const;

private:
  std::unordered_map<std::string, std::size_t> counts_;
};

} // namespace tally
```

实现用到 C++20 的 `std::ranges::sort`，命令行程序用到 C++23 的 `std::println`。三个文件对标准版本的要求各不相同，这一点下面会用到。

```cpp title="app/main.cpp"
#include <tally/tally.hpp>

#include <iostream>
#include <iterator>
#include <print>
#include <string>

int main() {
  std::string text(std::istreambuf_iterator<char>(std::cin), {});
  tally::Counter c;
  c.add_text(text);
  for (auto& [word, n] : c.top(3))
    std::println("{:>4} {}", n, word);
}
```

`CMakeLists.txt` 的前半部分（安装部分见后文）：

```cmake title="CMakeLists.txt"
cmake_minimum_required(VERSION 3.28)
project(tally VERSION 0.1.0 LANGUAGES CXX)

include(GNUInstallDirs)

set(CMAKE_CXX_EXTENSIONS OFF)        # -std=c++NN，而不是 -std=gnu++NN
set(CMAKE_CXX_SCAN_FOR_MODULES OFF)  # 没有模块源文件，不做依赖扫描

# ---- 库 ----
add_library(tally src/tally.cpp)
add_library(tally::tally ALIAS tally)

target_compile_features(tally
  PUBLIC  cxx_std_17      # 头文件用到 string_view：使用者至少要 C++17
  PRIVATE cxx_std_20)     # 实现用到 std::ranges::sort

target_include_directories(tally
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>
  PRIVATE
    src)

# 警告是这个目标自己的设置，不传给使用者
set(gcc_like "$<COMPILE_LANG_AND_ID:CXX,GNU,Clang,AppleClang>")
set(msvc     "$<COMPILE_LANG_AND_ID:CXX,MSVC>")
target_compile_options(tally PRIVATE
  "$<${gcc_like}:-Wall;-Wextra;-Wpedantic;-Wconversion>"
  "$<${msvc}:/W4;/permissive->")

# ---- 可执行文件 ----
add_executable(tally-cli app/main.cpp)
target_compile_features(tally-cli PRIVATE cxx_std_23)   # std::println
target_link_libraries(tally-cli PRIVATE tally::tally)

# ---- 测试 ----
include(CTest)
if(BUILD_TESTING)
  add_executable(tally_test tests/tally_test.cpp)
  target_link_libraries(tally_test PRIVATE tally::tally)
  add_test(NAME tally_test COMMAND tally_test)
endif()
```

CMake 的工作分两步。**配置**（configure）阶段执行 `CMakeLists.txt`，在构建目录里生成构建文件；构建阶段由 Ninja 执行这些文件里的命令。`-v` 让 Ninja 打印每条命令：

```text
$ cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Debug \
        -DCMAKE_CXX_COMPILER=/opt/homebrew/opt/llvm/bin/clang++
$ cmake --build build -v
[1/6] clang++ -I<src>/include -g -std=c++17 -arch arm64 -isysroot <sdk>
        -o CMakeFiles/tally_test.dir/tests/tally_test.cpp.o -c <src>/tests/tally_test.cpp
[2/6] clang++ -I<src>/include -I<src>/src -g -std=c++20 -arch arm64 -isysroot <sdk>
        -Wall -Wextra -Wpedantic -Wconversion
        -o CMakeFiles/tally.dir/src/tally.cpp.o -c <src>/src/tally.cpp
[3/6] ar qc libtally.a CMakeFiles/tally.dir/src/tally.cpp.o && llvm-ranlib libtally.a
[4/6] clang++ -g ... CMakeFiles/tally_test.dir/tests/tally_test.cpp.o -o tally_test libtally.a
[5/6] clang++ -I<src>/include -g -std=c++23 -arch arm64 -isysroot <sdk>
        -o CMakeFiles/tally-cli.dir/app/main.cpp.o -c <src>/app/main.cpp
[6/6] clang++ -g ... CMakeFiles/tally-cli.dir/app/main.cpp.o -o tally-cli libtally.a
$ ctest --test-dir build
1/1 Test #1: tally_test .......................   Passed    0.38 sec
$ printf 'the cat and the hat\nthe end, the cat\n' | ./build/tally-cli
   4 the
   2 cat
   1 and
```

整页都可以对照这段输出来读。同一个项目里三个 TU 得到了三个不同的 `-std=`；只有 `tally.cpp` 能看到 `src/` 目录，只有它带警告选项。下面逐项解释这些差别从哪里来。

!!! pitfall "编译器在第一次配置时就定下来"
    不指定 `CMAKE_CXX_COMPILER` 时，本机 CMake 选的是 `/usr/bin/c++`，即 Xcode 的 AppleClang 21，而不是 `PATH` 里的 Homebrew Clang。编译器在第一次配置时写入缓存，之后再改要用 `cmake --fresh` 或删掉构建目录重新配置。

## 目标与使用要求

**目标**（target）是 CMake 的基本单位：`add_library` 和 `add_executable` 各创建一个。编译选项、包含路径、宏定义、语言标准都设置在目标上，而不是设置在目录或全局变量上。

每条设置都带一个关键字，说明它对谁生效。挂在目标自己身上的叫构建要求；需要传给使用者（通过 `target_link_libraries` 依赖它的目标）的叫**使用要求**（usage requirements）：

| 关键字 | 编译本目标时 | 编译使用者时 | 典型内容 |
|---|---|---|---|
| `PRIVATE` | 生效 | 不生效 | 实现用的私有头文件目录、警告选项、只在 `.cpp` 中用到的依赖 |
| `PUBLIC` | 生效 | 生效 | 公开头文件目录、头文件里检查的宏、头文件要求的最低标准 |
| `INTERFACE` | 不生效 | 生效 | 只有头文件的库（`add_library(x INTERFACE)`）的全部设置 |

在上面的输出里可以逐条对上：

- `include/` 是 PUBLIC，所以 `tally_test.cpp` 和 `main.cpp` 的命令行里也有 `-I<src>/include`；`src/` 是 PRIVATE，只出现在 `tally.cpp` 的命令行里。使用者因此不可能 `#include "split.hpp"`。
- `cxx_std_17` 是 PUBLIC，`tally_test` 没有自己的标准要求，于是得到 `-std=c++17`；`tally-cli` 自己要求 C++23，取较高者。`cxx_std_20` 是 PRIVATE，只作用于库本身。
- 警告选项是 PRIVATE，使用者的命令行里没有。

依赖关系本身也分三种。`target_link_libraries(a PUBLIC b)` 表示 a 的头文件里用到了 b，链接 a 的目标也会得到 b 的使用要求；`PRIVATE` 表示只有 a 的 `.cpp` 用到 b。使用要求沿着 PUBLIC 和 INTERFACE 依赖逐层传递，这就是目标之间的依赖图。

`add_library(tally::tally ALIAS tally)` 定义一个带命名空间的别名，与安装后 `find_package` 得到的名字相同。使用者写 `tally::tally` 时，名字写错会在配置时报错；写 `tally` 时，一个不存在的目标名会被当作链接器参数 `-ltally`，要到链接时才失败。

### 使用要求写错的后果

假设库提供一个可选的统计功能，用宏开关控制，开关影响类的成员：

```cpp title="include/tally/tally.hpp（节选）"
class Counter {
  // ...
private:
  std::unordered_map<std::string, std::size_t> counts_;
#ifdef TALLY_STATS
  std::size_t words_seen_ = 0;
#endif
};
```

```cmake
target_compile_definitions(tally PRIVATE TALLY_STATS)   # 错误：应为 PUBLIC
```

`tally.cpp` 编译时定义了 `TALLY_STATS`，`tally_test.cpp` 编译时没有。两个翻译单元里的 `Counter` 由不同的记号序列构成：本机测得库这边 `sizeof(Counter)` 是 48，测试这边是 40。

[[basic.def.odr#16]] 要求一个类在多个翻译单元中的定义由相同的记号序列构成（¶16.4），违反时程序非良构，不要求诊断{{ifndr}}。实际后果是测试在栈上只分配了 40 字节，库的 `add_text` 却去读写偏移 40 处的 `words_seen_`，那里已经不属于这个对象。用 ASan 构建时立刻报错：

```text
==91378==ERROR: AddressSanitizer: stack-buffer-overflow on address 0x00016f85a528
READ of size 8 at 0x00016f85a528 thread T0
    #0 in tally::Counter::add_text(...) tally.cpp:13
    #1 in main tally_test.cpp:17
  This frame has 5 object(s):
    [32, 72) 'c' (line 16) <== Memory access at offset 72 overflows this variable
```

同一个程序用 RelWithDebInfo 构建、不加 sanitizer 时，本机测试通过，命令行程序输出也正确。这种错误可能长期潜伏。改成 `PUBLIC` 后，测试的命令行里出现 `-DTALLY_STATS`，问题消失。

判断标准很简单：头文件里 `#if` 检查的宏，头文件 `#include` 的路径，头文件用到的语言特性，都是 PUBLIC。同一个库被不同选项构建两次的情形见 [[toolchain/dependencies|依赖管理]]。

## 设置语言标准

CMake 有两种设置标准的方式，含义不同：

- `target_compile_features(t PUBLIC cxx_std_20)` 声明目标至少需要 C++20。它是使用要求，可以传递给使用者，也会写进导出的包配置。
- `CMAKE_CXX_STANDARD` 变量（或目标属性 `CXX_STANDARD`）为之后创建的目标设定一个默认标准。它不传递给使用者。

两者同时存在时，CMake 取能满足所有要求的最高版本。本机对一个空目标逐项试验，生成的选项如下（编译器为 Homebrew Clang 23）：

| 设置 | 生成的选项 |
|---|---|
| 什么都不设 | 无，使用编译器默认（Clang 23 为 `gnu++17`，`__cplusplus` 为 `201703L`；AppleClang 21 为 `201402L`） |
| `CMAKE_CXX_STANDARD 23` | `-std=gnu++23` |
| `CMAKE_CXX_STANDARD 23` 加 `CMAKE_CXX_EXTENSIONS OFF` | `-std=c++23` |
| `cxx_std_20` | `-std=gnu++20` |
| `CMAKE_CXX_STANDARD 17`、`EXTENSIONS OFF` 加 `cxx_std_20` | `-std=c++20` |
| `CMAKE_CXX_STANDARD 26`、`EXTENSIONS OFF` 加 `cxx_std_20` | `-std=c++26` |
| `cxx_std_17`（编译器默认已满足） | 无 |

最后一行说明，最低要求已经被编译器的默认模式满足时，CMake 不加任何选项。这时编译器用的是它自己的默认模式，包括 GNU 扩展。如果设置了 `CMAKE_CXX_EXTENSIONS OFF`，CMake 会补上 `-std=c++17` 来关闭扩展，前面 `tally_test` 的命令行就是这样来的（这是 CMake 3.22 起策略 CMP0128 的行为）。

`CMAKE_CXX_STANDARD_REQUIRED ON` 让 CMake 在编译器不支持该版本时报错，而不是悄悄退回较低的版本。只用 `target_compile_features` 时不需要它，编译特性本身就是硬性要求。

### C++26

本机 CMake 3.29 的 Clang 模块已经知道 C++26 的选项，`CMAKE_CXX_STANDARD 26` 生成 `-std=c++26`。但 `cxx_std_26` 不能用，配置时报错：

```text
CMake Error at CMakeLists.txt:14 (target_compile_features):
  target_compile_features The compiler feature "cxx_std_26" is not known to
  CXX compiler

  "Clang"

  version 23.1.3.
```

所以在这个版本组合下，要用 C++26 只能通过 `CMAKE_CXX_STANDARD`，并且无法把 C++26 声明为传给使用者的要求。较新的 CMake 是否已经支持，以所用版本的文档为准。另外，Clang 23 在 `-std=c++26` 下把 `__cplusplus` 定义为 `202400L`，与当前草案 [[cpp.predefined#1]] 中的 `202603L` 不同，因为 C++26 的支持还没有最终完成。

### 为什么关掉扩展

`gnu++NN` 模式开启编译器扩展。[[intro.compliance.general#11]] 允许实现有扩展，前提是扩展不改变任何良构程序的行为。GNU 模式并不满足这一点：

```cpp title="typeof.cpp" run ok
int typeof = 1;   // typeof 不是 C++ 关键字
int main() { return typeof - 1; }
```

这个程序是良构的，`-std=c++23` 下正常编译。`-std=gnu++23` 下 Clang 把 `typeof` 当作 GNU 关键字，报 `expected expression`。两种模式下预定义宏也不同：本机 `-std=c++23` 定义 `__STRICT_ANSI__`，`gnu++23` 不定义，另外多出两个描述 `__int128` 的宏。有些库头文件按 `__STRICT_ANSI__` 选择不同的代码路径。

推荐设置 `CMAKE_CXX_EXTENSIONS OFF`，用标准模式编写可移植的代码。确实需要某个扩展时，在用到它的目标上单独开启。

!!! note "一个程序里的多个标准版本"
    上面的项目把库编译成 C++20，测试编译成 C++17，再链接在一起。标准没有这种概念，在它看来每个 `-std=` 都是一个不同的实现。libc++ 和 libstdc++ 都尽量让不同版本模式编译的代码可以混合链接，日常这样做没有问题；但头文件若按 `__cplusplus` 改变类的成员，就会出现上一节那样的 ODR 违规。最省心的做法是在顶层项目里用 `CMAKE_CXX_STANDARD` 统一版本，库本身只用 `target_compile_features` 声明最低要求。

## 构建类型

**构建类型**（build type）是一组预设的优化和调试选项。单配置的生成器（Ninja、Makefile）在配置时用 `CMAKE_BUILD_TYPE` 选定一种。本机 Clang 下的默认值：

| `CMAKE_BUILD_TYPE` | 追加的选项 |
|---|---|
| `Debug` | `-g` |
| `Release` | `-O3 -DNDEBUG` |
| `RelWithDebInfo` | `-O2 -g -DNDEBUG` |
| `MinSizeRel` | `-Os -DNDEBUG` |
| 空（默认） | 无，即 `-O0` 且没有调试信息 |

空的构建类型很少是想要的结果，在预设里总是明确给出。

`-DNDEBUG` 的作用由标准规定：包含 `<cassert>` 时如果定义了 `NDEBUG`，`assert` 展开为 `((void)0)`（[[assertions.assert#1]]），条件表达式根本不求值。所以 Release 构建里不能把有副作用的代码写进 `assert`。

`NDEBUG` 也会影响 ODR。头文件里的 inline 函数如果用了 `assert`，在定义了 `NDEBUG` 和没定义的两个 TU 中，宏展开后的记号序列不同，同样违反 [[basic.def.odr#16]]。在同一个 CMake 构建里，所有目标共用同一个构建类型，不会出现这种混合；把 Release 构建、安装好的库和 Debug 构建的程序链接在一起时就可能出现。

### 多配置生成器

`Ninja Multi-Config`（以及 Visual Studio、Xcode）在一个构建目录里同时生成多种配置，构建时再选择：

```text
$ cmake -S . -B bmc -G "Ninja Multi-Config"
$ cmake --build bmc --config Release -v
[2/6] clang++ -DCMAKE_INTDIR=\"Release\" -I<src>/include -I<src>/src -O3 -DNDEBUG
        -std=c++20 ... -o CMakeFiles/tally.dir/Release/src/tally.cpp.o -c <src>/src/tally.cpp
$ cmake --build bmc --config Debug
$ ls bmc/Debug bmc/Release
bmc/Debug:   libtally.a  tally-cli  tally_test
bmc/Release: libtally.a  tally-cli  tally_test
$ ctest --test-dir bmc -C Release
```

在多配置生成器下，配置阶段还不知道最终构建哪种配置，`CMAKE_BUILD_TYPE` 是空的。因此 `if(CMAKE_BUILD_TYPE STREQUAL "Debug")` 这样的判断在多配置下永远不成立。要按配置改变设置，用生成器表达式 `$<CONFIG:Debug>`，它在两种生成器下都正确。

## 生成器表达式

**生成器表达式**（generator expression）是形如 `$<...>` 的表达式，不在执行 `CMakeLists.txt` 时求值，而在生成构建文件时针对每个目标、每种配置分别求值。这时编译器、配置和目标的最终属性都已确定。

上面的警告设置就是例子：

```cmake
set(gcc_like "$<COMPILE_LANG_AND_ID:CXX,GNU,Clang,AppleClang>")
target_compile_options(tally PRIVATE
  "$<${gcc_like}:-Wall;-Wextra;-Wpedantic;-Wconversion>"
  "$<${msvc}:/W4;/permissive->")
```

`$<条件:值>` 在条件为 1 时得到值，否则得到空串。值中的多个选项用分号分隔，整个表达式加引号，避免空格把它拆成几个参数。常用的几种：

| 表达式 | 含义 |
|---|---|
| `$<CXX_COMPILER_ID:Clang,AppleClang>` | 编译器是否为其中之一 |
| `$<COMPILE_LANG_AND_ID:CXX,MSVC>` | 编译的是 C++ 源文件且编译器是 MSVC；目标里混有 C 源文件时比上一种准确 |
| `$<CONFIG:Debug>` | 当前配置是否为 Debug |
| `$<BUILD_INTERFACE:...>` / `$<INSTALL_INTERFACE:...>` | 在构建树中使用 / 安装后使用，见后文 |
| `$<IF:条件,真值,假值>` | 二选一 |

例如只在 Debug 下打开 libc++ 的加固模式：

```cmake
target_compile_definitions(tally PRIVATE
  $<$<CONFIG:Debug>:_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_DEBUG>)
```

## 警告属于目标

警告选项写在目标上，用 PRIVATE。理由有三：

1. 警告是项目自己的代码质量要求，不应强加给使用者。库的使用者可能用不同的编译器版本，新版本多出来的警告不该让他们的构建失败。
2. 第三方代码（`add_subdirectory` 引入的依赖）不该被你的警告级别覆盖。全局设置做不到这一点。
3. 不同的目标可以有不同的级别，例如对遗留代码暂时放宽。

使用者包含 `tally.hpp` 时，头文件中的代码用的是使用者的警告选项。对安装后的库，CMake 把导入目标的包含目录用 `-isystem` 传给编译器（后文的输出中可以看到），编译器不报系统头文件中的警告。

`-Werror` 更不该写死在 `CMakeLists.txt` 里。CMake 3.24 起有 `CMAKE_COMPILE_WARNING_AS_ERROR` 变量（初始化目标属性 `COMPILE_WARNING_AS_ERROR`），由构建者决定是否开启，例如只在 CI 中打开。本机打开后每条编译命令都多了 `-Werror`；配置时加 `--compile-no-warning-as-error` 则忽略它。

## 预设：CMakePresets.json

一个 sanitizer 构建需要指定生成器、构建目录、构建类型和一串选项。把这些写进文档让每个人手敲，迟早有人敲错。**预设**（preset）把它们存在仓库里的 `CMakePresets.json` 中：

```json title="CMakePresets.json"
{
  "version": 6,
  "configurePresets": [
    {
      "name": "base",
      "hidden": true,
      "generator": "Ninja",
      "binaryDir": "${sourceDir}/build/${presetName}",
      "cacheVariables": { "CMAKE_EXPORT_COMPILE_COMMANDS": "ON" }
    },
    {
      "name": "debug",
      "inherits": "base",
      "cacheVariables": { "CMAKE_BUILD_TYPE": "Debug" }
    },
    {
      "name": "release",
      "inherits": "base",
      "cacheVariables": { "CMAKE_BUILD_TYPE": "RelWithDebInfo" }
    },
    {
      "name": "asan",
      "inherits": "base",
      "cacheVariables": {
        "CMAKE_BUILD_TYPE": "Debug",
        "CMAKE_CXX_FLAGS": "-fsanitize=address,undefined -fno-omit-frame-pointer"
      }
    },
    {
      "name": "tsan",
      "inherits": "base",
      "cacheVariables": {
        "CMAKE_BUILD_TYPE": "Debug",
        "CMAKE_CXX_FLAGS": "-fsanitize=thread"
      }
    },
    {
      "name": "ci",
      "inherits": "base",
      "cacheVariables": {
        "CMAKE_BUILD_TYPE": "RelWithDebInfo",
        "CMAKE_COMPILE_WARNING_AS_ERROR": "ON"
      }
    }
  ],
  "buildPresets": [
    { "name": "debug", "configurePreset": "debug" },
    { "name": "asan",  "configurePreset": "asan" },
    { "name": "tsan",  "configurePreset": "tsan" },
    { "name": "ci",    "configurePreset": "ci" }
  ],
  "testPresets": [
    {
      "name": "asan",
      "configurePreset": "asan",
      "output": { "outputOnFailure": true },
      "environment": { "UBSAN_OPTIONS": "print_stacktrace=1:halt_on_error=1" }
    }
  ]
}
```

```text
$ cmake --preset asan
$ cmake --build --preset asan
$ ctest --preset asan
```

几点说明：

- sanitizer 通过缓存变量 `CMAKE_CXX_FLAGS` 传入。这个变量是留给构建者的，CMake 把它同时放进编译命令和链接命令；本机 `asan` 预设的链接命令是 `c++ -fsanitize=address,undefined -fno-omit-frame-pointer -g ... -o tally_test libtally.a`。sanitizer 必须在链接时也出现，才会链接进对应的运行时库。
- ASan 和 TSan 不能同时使用（Clang 报 `'-fsanitize=address' not allowed with '-fsanitize=thread'`），所以是两个预设、两个构建目录。
- UBSan 默认报告后继续运行，`halt_on_error=1` 让测试在第一个错误处失败。
- 公共的 `CMakePresets.json` 提交到仓库；个人的设置（如编译器路径）放在 `CMakeUserPresets.json` 里，它可以继承公共预设，通常加进 `.gitignore`。

```json title="CMakeUserPresets.json"
{
  "version": 6,
  "configurePresets": [
    {
      "name": "my-asan",
      "inherits": "asan",
      "cacheVariables": { "CMAKE_CXX_COMPILER": "/opt/homebrew/opt/llvm/bin/clang++" }
    }
  ],
  "buildPresets": [ { "name": "my-asan", "configurePreset": "my-asan" } ],
  "testPresets": [ { "name": "my-asan", "inherits": "asan", "configurePreset": "my-asan" } ]
}
```

!!! impl "本机：同一个预设，两个编译器"
    公共的 `asan` 预设没有指定编译器，本机选中 AppleClang。最初在测试预设里设置了 `ASAN_OPTIONS=detect_leaks=1`，结果测试直接失败，输出 `AddressSanitizer: detect_leaks is not supported on this platform.`。换成 Homebrew Clang 23 构建（上面的 `my-asan`），同一个选项可用，一个故意泄漏的程序被报告为 `LeakSanitizer: detected memory leaks`。在 macOS 上，泄漏检测是否可用取决于用的是哪个工具链的 sanitizer 运行时。

## compile_commands.json

clangd、clang-tidy 这类工具要像编译器一样解析源文件，就必须知道每个文件的编译选项：包含路径、宏、标准版本。`CMAKE_EXPORT_COMPILE_COMMANDS ON`（上面的 `base` 预设已经打开）让 CMake 在构建目录里写出 `compile_commands.json`，每个 TU 一项。它只对 Makefile 和 Ninja 生成器有效。

```json
{
  "directory": "<src>/build/debug",
  "command": "/opt/homebrew/opt/llvm/bin/clang++ -I<src>/include -I<src>/src -g -std=c++20 -arch arm64 -isysroot <sdk> -Wall -Wextra -Wpedantic -Wconversion -o CMakeFiles/tally.dir/src/tally.cpp.o -c <src>/src/tally.cpp",
  "file": "<src>/src/tally.cpp",
  "output": "CMakeFiles/tally.dir/src/tally.cpp.o"
}
```

没有它，工具只能猜：

```text
$ clang-tidy --checks='-*,bugprone-*,performance-*' tally/src/tally.cpp
Error while trying to load a compilation database:
Could not auto-detect compilation database for file "tally/src/tally.cpp"
...
Running without flags.
<src>/src/tally.cpp:1:10: error: 'tally/tally.hpp' file not found [clang-diagnostic-error]
$ clang-tidy -p build/debug --checks='-*,bugprone-*,performance-*' src/tally.cpp
（没有诊断）
```

`-p` 指向包含 `compile_commands.json` 的目录。clangd 在源文件所在目录及其上级目录中查找这个文件，也查找这些目录下的 `build/` 子目录。用了 `build/<预设名>` 这样的布局时，可以在源码根目录建一个指向它的符号链接，或者在 clangd 的配置文件 `.clangd` 里用 `CompileFlags: CompilationDatabase: build/debug` 指定。

也可以让 CMake 在编译每个文件时顺便运行 clang-tidy：设置 `CMAKE_CXX_CLANG_TIDY`（例如 `-DCMAKE_CXX_CLANG_TIDY="clang-tidy;--checks=-*,bugprone-*"`）后，生成的每条编译命令都包在 `cmake -E __run_co_compile --tidy=...` 里。检查项的选择见 [[toolchain/static-analysis|静态分析]]。

## 安装与导出

库要给别的项目用，需要安装头文件和库文件，并导出一份描述目标的 CMake 文件，让使用者用 `find_package` 找回 `tally::tally` 这个目标和它的全部使用要求：

```cmake title="CMakeLists.txt（续）"
include(CMakePackageConfigHelpers)

install(TARGETS tally EXPORT tallyTargets)
install(DIRECTORY include/ DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})
install(EXPORT tallyTargets
  NAMESPACE tally::
  DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/tally)

configure_package_config_file(cmake/tallyConfig.cmake.in
  ${CMAKE_CURRENT_BINARY_DIR}/tallyConfig.cmake
  INSTALL_DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/tally)
write_basic_package_version_file(
  ${CMAKE_CURRENT_BINARY_DIR}/tallyConfigVersion.cmake
  COMPATIBILITY SameMajorVersion)
install(FILES
  ${CMAKE_CURRENT_BINARY_DIR}/tallyConfig.cmake
  ${CMAKE_CURRENT_BINARY_DIR}/tallyConfigVersion.cmake
  DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/tally)
```

```cmake title="cmake/tallyConfig.cmake.in"
@PACKAGE_INIT@
include("${CMAKE_CURRENT_LIST_DIR}/tallyTargets.cmake")
check_required_components(tally)
```

安装后，生成的 `tallyTargets.cmake` 里记录的正是 PUBLIC 的那部分设置；PRIVATE 的 `src/`、`cxx_std_20` 和警告选项都没有出现：

```cmake
add_library(tally::tally STATIC IMPORTED)

set_target_properties(tally::tally PROPERTIES
  INTERFACE_COMPILE_FEATURES "cxx_std_17"
  INTERFACE_INCLUDE_DIRECTORIES "${_IMPORT_PREFIX}/include"
)
```

包含目录在构建树里和安装后不同，所以前面用 `$<BUILD_INTERFACE:...>` 和 `$<INSTALL_INTERFACE:...>` 分别给出。导出时只保留后者，路径相对于安装前缀。

使用者的 `CMakeLists.txt`：

```cmake title="consumer/CMakeLists.txt"
cmake_minimum_required(VERSION 3.28)
project(consumer LANGUAGES CXX)
set(CMAKE_CXX_SCAN_FOR_MODULES OFF)

find_package(tally 0.1 CONFIG REQUIRED)

add_executable(wordfreq main.cpp)
target_compile_options(wordfreq PRIVATE -Wall -Wextra -Wconversion)
target_link_libraries(wordfreq PRIVATE tally::tally)
```

```text
$ cmake --install build/release --prefix ../prefix
$ cmake -S . -B b -G Ninja -DCMAKE_PREFIX_PATH=<dir>/prefix
$ cmake --build b -v
[1/2] clang++ -isystem <dir>/prefix/include -arch arm64 -isysroot <sdk>
        -Wall -Wextra -Wconversion -o CMakeFiles/wordfreq.dir/main.cpp.o -c <dir>/consumer/main.cpp
[2/2] clang++ ... CMakeFiles/wordfreq.dir/main.cpp.o -o wordfreq <dir>/prefix/lib/libtally.a
```

包含目录以 `-isystem` 出现；这个使用者没有关闭扩展，`cxx_std_17` 又被 Clang 的默认模式满足，所以命令行里没有 `-std=`。依赖从哪里来、怎样锁定版本，见 [[toolchain/dependencies|依赖管理]]；动态库的符号可见性和 ABI 稳定性，见 [[toolchain/library-boundaries|库的边界]]。

## 模块

模块的构建机制（BMI、依赖扫描、`FILE_SET CXX_MODULES`、CMake 生成的 `.modmap`）已经在 [[toolchain/modules-in-practice]] 中讲过。这里补充三件与项目组织有关的事。

### 没有模块时也会扫描

`cmake_minimum_required(VERSION 3.28)` 启用了策略 CMP0155：标准设为 C++20 或更高的目标，即使没有任何模块源文件，CMake 也默认对每个源文件运行 `clang-scan-deps`，以防它们 `import` 了什么。本项目去掉 `set(CMAKE_CXX_SCAN_FOR_MODULES OFF)` 后，Debug 构建从 6 步变成 12 步：每个 TU 多一次扫描，每个目标多一次 `cmake_ninja_dyndep`。项目不用模块时，关掉扫描。

### 安装模块接口

给 `tally` 加一个模块接口，把头文件中的类导出：

```cpp title="src/tally.cppm"
module;
#include <tally/tally.hpp>
export module tally;
export namespace tally {
  using tally::Counter;
}
```

```cmake
target_sources(tally PUBLIC
  FILE_SET CXX_MODULES BASE_DIRS src FILES src/tally.cppm)

install(TARGETS tally EXPORT tallyTargets
  FILE_SET CXX_MODULES DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/tally/modules)
install(EXPORT tallyTargets
  NAMESPACE tally::
  CXX_MODULES_DIRECTORY cxx-modules
  DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/tally)
```

安装的是接口的源码 `tally.cppm`，不是 BMI。导出文件中多了一个属性，把模块名映射到源文件：

```cmake
set_property(TARGET "tally::tally"
  PROPERTY IMPORTED_CXX_MODULES_RELEASE
    "tally=${_IMPORT_PREFIX}/include/tally/modules/tally.cppm"
)
```

使用者 `import tally;` 时，CMake 在使用者的构建目录里另建一个内部目标（本机名为 `tally__tally@synth_…`），用使用者的编译器重新编译这个接口，得到 BMI。这与 BMI 不能分发的原因一致。

### BMI 的选项必须一致

这个内部目标用什么选项编译，决定了 BMI 能否被导入。本机的情形：库导出的要求是 `cxx_std_20`，使用者把自己的目标设为 C++23（无论用 `CMAKE_CXX_STANDARD 23` 还是 `cxx_std_23`），内部目标仍以 `-std=c++20` 编译接口，于是导入失败：

```text
error: C++23 was disabled in precompiled file 'CMakeFiles/tally__tally@synth_15c5226b978c.dir/d239af2f2b1f.bmi' but is currently enabled
error: precompiled file '...' cannot be loaded due to a configuration mismatch with the current compilation [-Wmodule-file-config-mismatch]
```

使用者改为 C++20 后构建成功并正确运行。这是 CMake 3.29 加 Clang 23 上观察到的行为；结论是，导出模块的库与使用者目前最好约定同一个标准版本。

## 常见的反模式

| 写法 | 问题 | 改为 |
|---|---|---|
| `include_directories(...)`、`add_definitions(...)`、`add_compile_options(...)` | 作用于当前目录及子目录中的所有目标，包括 `add_subdirectory` 引入的第三方代码；不是使用要求，不会传给使用者，也不会导出 | `target_include_directories`、`target_compile_definitions`、`target_compile_options`，并写明关键字 |
| 在 `CMakeLists.txt` 里 `set(CMAKE_CXX_FLAGS ...)` | 覆盖构建者传入的选项；作用于所有目标；不会导出 | 项目需要的写在目标上；构建者的选择放进预设 |
| `file(GLOB SRCS src/*.cpp)` | 新增文件不会触发重新配置，构建悄悄漏掉文件 | 显式列出源文件 |
| `target_link_libraries(app tally)`，不写关键字 | 旧式签名，传递规则与关键字形式不同，两种形式不能对同一目标混用 | 总是写 `PRIVATE` / `PUBLIC` / `INTERFACE` |
| `if(CMAKE_BUILD_TYPE STREQUAL "Debug")` | 多配置生成器下 `CMAKE_BUILD_TYPE` 为空 | `$<CONFIG:Debug>` |
| 选项里直接写 `-std=c++20` | 与 CMake 生成的 `-std=` 冲突，最后一个生效 | `target_compile_features` 或 `CMAKE_CXX_STANDARD` |

后两类问题在本机都能直接看到。下面的 `CMakeLists.txt` 在项目里设置了 `CMAKE_CXX_FLAGS`，构建者又在命令行传入 `-DCMAKE_CXX_FLAGS=-fsanitize=address`：

```cmake
set(CMAKE_CXX_FLAGS "-Wall -std=c++17")
add_executable(g src/main.cpp src/helper.cpp)
target_compile_features(g PRIVATE cxx_std_20)
```

```text
[2/3] c++ -Wall -std=c++17 -std=gnu++20 -arch arm64 -isysroot <sdk> ... -c <src>/src/main.cpp
```

`set` 定义的普通变量遮住了同名的缓存变量，构建者要的 `-fsanitize=address` 消失了，而且没有任何提示。命令行里有两个 `-std=`，后面的 `gnu++20` 生效。

`file(GLOB)` 的问题：

```text
$ echo 'int helper() { return 1; }' > src/helper.cpp
$ cmake --build b
ninja: no work to do.
```

`file(GLOB)` 只在配置时求值一次，新文件要等到下次重新配置才会加入。加上 `CONFIGURE_DEPENDS` 后，本机每次构建都先执行一步 `Re-checking globbed directories...`，发现变化时输出 `-- GLOB mismatch!` 并重新配置。CMake 的文档指出这一选项并非对所有生成器都可靠，而且每次构建都要付出检查的代价。显式列出源文件还有一个好处：代码评审时能看到新增了哪个翻译单元。

## 思考题

!!! question "1"
    `tally` 的头文件不变，只在 `tally.cpp` 里加了 `#include <fmt/format.h>` 并调用 fmt。`target_link_libraries(tally ??? fmt::fmt)` 该用哪个关键字？如果后来头文件里也加了 `#include <fmt/format.h>` 呢？

<details markdown="1">
<summary>答案</summary>

只有 `.cpp` 用到时用 `PRIVATE`：使用者编译时不需要 fmt 的包含路径，也就不应该看到它。不过 `tally` 是静态库，链接使用者时仍需要 fmt 的库文件，CMake 会自动把 PRIVATE 的链接依赖以 `$<LINK_ONLY:...>` 的形式记入导出文件，只传链接、不传编译设置。

头文件也包含它之后要改成 `PUBLIC`。否则使用者的 TU 找不到 `<fmt/format.h>`；更隐蔽的情况是使用者恰好从别处找到了另一个版本的 fmt 头文件，与库编译时用的版本不同，这就是 [[basic.def.odr#16]] 的违规。
</details>

!!! question "2"
    某个库在头文件里写了 `#if __cplusplus >= 202002L` 来决定是否给一个类加一个 `std::span` 成员。库用 `target_compile_features(lib PUBLIC cxx_std_17)` 构建，项目的 `CMAKE_CXX_STANDARD` 是 20。会出问题吗？

<details markdown="1">
<summary>答案</summary>

在同一个 CMake 构建里不会：`CMAKE_CXX_STANDARD 20` 是所有目标的默认值，库和使用者都以 C++20 编译，`cxx_std_17` 只是下限。

问题出在库被单独构建并安装之后。库用 C++17 编译，使用者用 C++20 编译，两边 `__cplusplus` 不同，类的定义不同，属于不要求诊断的 ODR 违规（[[basic.def.odr#16]]）。CMake 只传递最低要求，无法要求使用者与库使用同一个版本。头文件不应该让类的布局依赖于 `__cplusplus`；如果必须这样做，只能在文档中写明库和使用者要用相同的标准版本构建。
</details>

!!! question "3"
    为什么 sanitizer 选项放在预设的 `CMAKE_CXX_FLAGS` 里是合理的，而在 `CMakeLists.txt` 里 `set(CMAKE_CXX_FLAGS ...)` 是反模式？

<details markdown="1">
<summary>答案</summary>

`CMAKE_CXX_FLAGS` 是缓存变量，本来就是留给构建者的接口：同一份源码，有人要 ASan 构建，有人要 TSan 构建，有人要普通构建，这是构建环境的选择，不是项目的属性。预设只是把构建者的选择记录下来。

在 `CMakeLists.txt` 里 `set` 同名的普通变量，等于项目替构建者做了决定，并且遮住了构建者传入的值，上文的实验中 `-fsanitize=address` 就这样消失了。项目自身确实需要的选项应当写在目标上。
</details>

## 小结

| 主题 | 要点 |
|---|---|
| 目标与使用要求 | PRIVATE 只给自己，INTERFACE 只给使用者，PUBLIC 两者都给；头文件依赖的一切都是 PUBLIC |
| 写错的代价 | 头文件中的宏是 PRIVATE 时，库和使用者看到不同的类定义，IFNDR；本机 ASan 报 `stack-buffer-overflow`，不加 sanitizer 时测试照常通过 |
| 语言标准 | `cxx_std_NN` 是可传递的下限，`CMAKE_CXX_STANDARD` 是默认值；`CMAKE_CXX_EXTENSIONS OFF` 得到 `-std=c++NN`；本机 CMake 3.29 不认识 `cxx_std_26`，`CMAKE_CXX_STANDARD 26` 可用 |
| 构建类型 | Debug `-g`，Release `-O3 -DNDEBUG`，RelWithDebInfo `-O2 -g -DNDEBUG`；空类型没有优化也没有调试信息；多配置下用 `$<CONFIG:...>` |
| 警告 | 目标的 PRIVATE 选项；`-Werror` 交给 `CMAKE_COMPILE_WARNING_AS_ERROR` |
| 预设 | 生成器、构建目录、构建类型、sanitizer 写进 `CMakePresets.json`；个人设置放 `CMakeUserPresets.json` |
| 工具 | `CMAKE_EXPORT_COMPILE_COMMANDS ON`，clang-tidy 用 `-p` 指向构建目录 |
| 安装 | `install(TARGETS … EXPORT)` 加 `install(EXPORT … NAMESPACE)`，使用者 `find_package(… CONFIG)`；导出的只有使用要求 |
| 模块 | C++20 目标默认扫描，不用模块时关掉；安装的是接口源码，使用者重建 BMI，标准版本要一致 |
