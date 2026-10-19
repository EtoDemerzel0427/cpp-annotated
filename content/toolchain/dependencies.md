---
title: 依赖管理
summary: 怎样把第三方库引入 C++ 项目：为什么没有统一的包格式、为什么编译选项必须一致，同一个库的两个版本怎样在一个程序里造成 ODR 违规，系统包、FetchContent、vcpkg、Conan、子模块和 vendoring 各自的做法，以及锁定版本、校验哈希和按项目类型的选择。
group: 工程实践
status: draft
order: 120
since: c++98
related: basic.def.odr, basic.link, lex.phases, cpp.include, namespace.def, toolchain/linking-and-symbols, toolchain/library-boundaries, toolchain/cmake, toolchain/compilation-pipeline, topics/two-phase-lookup
tags: 工具链, 依赖, 包管理, ODR, ABI, CMake, 构建
updated: 2026-10-19
---

!!! tldr
    - 标准只规定程序由翻译单元和库组件链接而成，不规定库怎样打包、怎样查找。各个包管理器都是在这片空白上各自约定的。
    - 预编译的库只能和用相同标准库、相同 ABI 相关选项编译的代码一起用。所以 C++ 的依赖管理不只是下载正确的版本，还要用正确的方式构建它。
    - 同一个库的两个版本进入一个程序，就是同一个 inline 函数或类有两份不同的定义，属于不要求诊断的 ODR 违规。本机实验中，结果取决于链接顺序和优化级别：值错误、崩溃，或者恰好正常。
    - 从源码一起构建（FetchContent、子模块、vendoring）最容易保证选项一致；vcpkg 和 Conan 在此基础上加了版本求解和二进制缓存；系统包最省事，但版本和选项由发行版决定。
    - 无论用哪种方式，都要锁定确切版本，并校验下载内容的哈希。

## 标准不认识包

标准里与依赖有关的只有两处。翻译阶段 8（[[lex.phases#1]]）说，翻译好的翻译单元（TU）合并在一起，用库组件满足本 TU 中没有定义的外部引用。`#include <x.h>` 去哪里找头文件，[[cpp.include#1]] 规定由实现定义。

除此之外，什么是一个库、它的头文件和二进制放在哪里、它依赖哪些别的库、它是用什么选项编译的，标准一概不管。Python 有 wheel，Rust 有 crate，它们都是语言官方规定的包格式。C++ 没有这样的格式，于是出现了几种互不兼容的约定：

| 约定 | 描述一个库的方式 | 谁在用 |
|---|---|---|
| pkg-config 的 `.pc` 文件 | 一组编译和链接参数 | Linux 发行版、Homebrew、许多 C 库 |
| CMake 包配置文件（`<名字>Config.cmake`） | CMake 导入目标，带头文件路径、库文件、依赖和编译要求 | 用 CMake 构建的库 |
| vcpkg 的 port、Conan 的 recipe | 一段如何从源码构建的脚本，加上版本元数据 | 对应的包管理器 |

本机装着 Homebrew 的 zstd，它同时提供两种描述。`.pc` 文件只是几行参数：

```text
$ cat /opt/homebrew/lib/pkgconfig/libzstd.pc
prefix=/opt/homebrew/opt/zstd
exec_prefix=${prefix}
includedir=${prefix}/include
libdir=${exec_prefix}/lib

Name: zstd
Description: fast lossless compression algorithm library
URL: https://facebook.github.io/zstd/
Version: 1.5.7
Libs: -L${libdir} -lzstd
Libs.private:
Cflags: -I${includedir}
```

`/opt/homebrew/lib/cmake/zstd/` 下是 CMake 的包配置文件，定义了 `zstd::libzstd_shared`、`zstd::libzstd_static` 等导入目标。两种描述都没有记录这个库是用哪个编译器、哪个标准库、什么选项编译的，而这恰恰是 C++ 最需要的信息。

## 编译选项也是接口

一个预编译的 C++ 库，其二进制与编译时的许多选项绑定。这类二进制层面的约定统称 **ABI**（application binary interface）：类的布局、函数怎样传参、符号名怎样修饰、异常怎样传播。修饰名见 [[toolchain/name-mangling]]，类的布局见 [[toolchain/object-layout-and-vtables]]。

C 库的 ABI 相对稳定，换个编译选项一般没有影响。C++ 库的头文件里有大量 inline 函数和模板，它们在使用方的 TU 中实例化，和库的二进制混在一起。只要两边对同一个类型的理解不同，就会出错。

| 选项或配置 | 不一致时会怎样 |
|---|---|
| 标准库实现（libc++ / libstdc++ / MSVC STL） | `std::string` 等类型的布局和修饰名都不同。libc++ 把实体放在 `std::__1` 里，混用时通常表现为链接错误 |
| `-std=` | 库的头文件可能用 `__cplusplus` 选择不同的成员或类型别名，两边看到的类定义不同 |
| 异常和 RTTI（`-fno-exceptions`、`-fno-rtti`） | 异常穿过没有回溯信息的帧时直接终止；`dynamic_cast` 和 `typeid` 找不到类型信息 |
| 调试版迭代器 | libstdc++ 的 `_GLIBCXX_DEBUG`、MSVC 的 `_ITERATOR_DEBUG_LEVEL`、libc++ 的有界迭代器 ABI 都会改变容器或迭代器的布局 |
| sanitizer | 部分只要求整个程序一起启用（如 TSan、MSan），否则漏报或误报 |
| 库自己的配置宏 | 头文件里 `#ifdef` 决定的成员，两边定义不同就是两个不同的类 |

本机有两个直接观察。第一，libc++ 的有界迭代器是一个 ABI 配置（`_LIBCPP_ABI_BOUNDED_ITERATORS_IN_VECTOR` 等宏；按 libc++ 的文档，这类 ABI 宏应在构建 libc++ 时统一选定，这里手工定义只为观察布局）。打开后 `sizeof(std::vector<int>::iterator)` 从 8 字节变成 24 字节；而 `_LIBCPP_HARDENING_MODE_DEBUG` 这种加固模式不改变布局，仍是 8 字节。

第二，一个以默认选项编译的库抛出异常，异常穿过中间一个以 `-fno-exceptions` 编译的 TU，再由 `main` 中的 `catch (...)` 接住。全部以默认选项编译时输出 `cleanup`、`caught`；中间那个 TU 改用 `-fno-exceptions` 后，程序以 `libc++abi: terminating due to uncaught exception` 终止，局部对象没有析构。机制见 [[toolchain/exception-implementation]]。

这些选项各自的含义和怎样在库的接口上避开它们，见 [[toolchain/library-boundaries|库的边界]]。对依赖管理而言，结论只有一条：**同一个程序里的所有 C++ 代码，包括所有依赖，应当用同一个编译器、同一个标准库和同一组 ABI 相关选项构建。**

!!! impl "本机的一个例子"
    用 Homebrew LLVM 的 clang++ 直接构建时，头文件来自 Homebrew 的 libc++，`otool -L` 却显示可执行文件在运行时链接 `/usr/lib/libc++.1.dylib`，即系统自带的 libc++。这里的例子都能正常运行，但头文件和运行时库来自两个不同版本的 libc++。新头文件一旦引用了系统库中没有的符号，就会在链接或加载时失败。

## 一个程序里的两个版本

一个库被多个依赖间接引入时，最容易出现这种情况：`liba` 自带了 `mini` 的 1.0 版，`libb` 自带了 2.0 版，应用程序同时链接 `liba` 和 `libb`。下面把它缩到最小，`mini` 是一个只有头文件的库，2.0 版给 `Options` 加了一个成员：

<div class="compare" markdown="1">

```cpp title="v1/mini/mini.hpp"
#pragma once
namespace mini {
struct Options {
  int level;
};
inline Options defaults() {
  return {1};
}
inline const char* version() {
  return "1.0";
}
}
```

```cpp title="v2/mini/mini.hpp"
#pragma once
namespace mini {
struct Options {
  int level;
  long cache[4];
};
inline Options defaults() {
  return {2, {64, 64, 64, 64}};
}
inline const char* version() {
  return "2.0";
}
}
```

</div>

`a.cpp` 代表 `liba`，用 `-Iv1` 编译；`b.cpp` 代表 `libb`，用 `-Iv2` 编译。两者的源码只有名字不同：

```cpp title="a.cpp"
#include <mini/mini.hpp>
#include <cstdio>
void use_a() {
  mini::Options o = mini::defaults();
  std::printf("a: built with 1.0, sees %s, level=%d\n",
              mini::version(), o.level);
}
```

```cpp title="b.cpp"
#include <mini/mini.hpp>
#include <cstdio>
void use_b() {
  mini::Options o = mini::defaults();
  std::printf("b: built with 2.0, sees %s, level=%d\n",
              mini::version(), o.level);
}
```

```cpp title="main.cpp" ifndr
void use_a();
void use_b();
int main() { use_a(); use_b(); }   // 与 a.cpp、b.cpp 一起：IFNDR
```

每个 TU 单独看都没有问题，`-Wall -Wextra -pedantic` 也没有任何警告。下面是本机的结果：

```text
$ clang++ -std=c++2c -O0 -Iv1 -c a.cpp
$ clang++ -std=c++2c -O0 -Iv2 -c b.cpp
$ clang++ -std=c++2c -O0 -c main.cpp
$ clang++ main.o a.o b.o -o app_ab && ./app_ab
a: built with 1.0, sees 1.0, level=1
b: built with 2.0, sees 1.0, level=73039476
$ clang++ main.o b.o a.o -o app_ba && ./app_ba
Bus error: 10
```

`-O0` 时 inline 函数没有内联，每个目标文件里都有一份 `mini::defaults()` 和 `mini::version()`，在 Mach-O 上是弱定义。链接器只按名字去重，保留其中一份（见 [[toolchain/linking-and-symbols]]），而两份的内容不同：

- `a.o` 在前时，`b` 调用的是 1.0 版的 `defaults()`。1.0 版只在寄存器里返回一个 `int`；`b` 以为返回的是 40 字节的结构体，从自己的栈上读到一个从未写过的值。
- `b.o` 在前时，`a` 调用的是 2.0 版。2.0 版要把 40 字节写到调用方提供的地址，`a` 按 1.0 版的约定根本没有提供这个地址，于是写到了一个随机地址上，进程收到 SIGBUS。

改用 `-O2` 编译 `a.cpp` 和 `b.cpp`，两次调用都内联进了各自的 TU，目标文件里不再有 `mini::` 符号，输出变得正常：

```text
a: built with 1.0, sees 1.0, level=1
b: built with 2.0, sees 2.0, level=2
```

把两个 TU 打成静态库再链接，本机系统链接器无论写 `-la -lb` 还是 `-lb -la`，都选了 `a.o` 中的版本。同一份源码，结果取决于链接顺序、链接方式和优化级别。在 AddressSanitizer 下，崩溃报告指向 `mini::defaults()+0x70`，栈是 `use_a → mini::defaults`，看不出问题出在两个版本的头文件上。

### 标准怎么看

`mini::Options`、`mini::defaults` 和 `mini::version` 都是**可定义项**（definable item），允许在多个 TU 中各有一个定义，条件是这些定义满足 [[basic.def.odr#16]] 的一系列要求，其中第一条（¶16.4）就是由相同的记号序列组成。两个版本的头文件显然不满足。

!!! std
    if the definitions in different translation units do not satisfy the following requirements, the program is ill-formed; a diagnostic is required only if the definable item is attached to a named module …

也就是说，这样的程序是 {{ifndr}}：不合法，但编译器和链接器都没有义务发现。上面那些看似随机的结果，都是这条规则允许的。如果 `mini` 是模块并且后一个定义处能看到前一个，实现就必须诊断；普通头文件不在此列。

### 怎样避免

第一条也是最根本的一条：**一个程序里每个库只能有一个版本**。这正是包管理器做版本求解的原因：它在整个依赖图上为每个库选出一个版本，所有依赖它的库都用这个版本构建。自带一份第三方库源码的库（下文的 vendoring）会绕过这种求解，所以库作者不应该把依赖的源码原样塞进自己公开的头文件里。

第二条是库作者可以做的：把版本号编进符号名。常用的手段是**内联命名空间**（[[g:inline-namespace]]）。内联命名空间的成员可以像外层命名空间的成员一样使用（[[namespace.def#6]]），但它们属于不同的命名空间，修饰名也不同。libc++ 的 `std::__1` 就是这样做的。

```cpp title="v2/mini/mini.hpp（带版本命名空间）" ok
#pragma once
namespace mini {
inline namespace v2 {
struct Options { int level; long cache[4]; };
inline Options defaults() { return {2, {64, 64, 64, 64}}; }
inline const char* version() { return "2.0"; }
}
}
```

1.0 版同样包在 `inline namespace v1` 里之后，使用方的源码一字不改，两个版本就成了不同的实体，程序不再违反 ODR：

```text
$ llvm-nm a.o b.o | grep mini
0000000000000058 T __ZN4mini2v17versionEv
0000000000000040 T __ZN4mini2v18defaultsEv
0000000000000064 T __ZN4mini2v27versionEv
0000000000000040 T __ZN4mini2v28defaultsEv
$ ./app_ba
a: built with 1.0, sees 1.0, level=1
b: built with 2.0, sees 2.0, level=2
```

当两个版本的类型真的要跨库传递时，错误也从运行时提前到了链接时。`liba` 用 1.0 定义 `int level_of(const mini::Options&)`，用 2.0 编译的调用方链接时报：

```text
Undefined symbols for architecture arm64:
  "level_of(mini::v2::Options const&)", referenced from:
      _main in nb2.o
```

这不能让两个版本互通，只是把静默的错误变成可见的错误。

## 只有头文件的库与需要编译的库

| | 只有头文件（header-only） | 需要编译 |
|---|---|---|
| 引入方式 | 加一个头文件搜索路径 | 还要链接 `.a`、`.so`/`.dylib`/`.dll` |
| 用什么选项编译 | 使用方的选项，每个 TU 各编译一遍 | 库构建时的选项，必须与使用方一致 |
| 编译时间 | 每个包含它的 TU 都要付出 | 只付一次 |
| ODR 风险 | 有：全是 inline 函数和模板，上一节的例子就是 header-only | 有：库内部的 inline 函数与使用方看到的可能不同 |
| 典型例子 | 大部分 Boost 库、nlohmann/json、Eigen | zstd、OpenSSL、Boost.Filesystem |

header-only 的库免去了选项一致的问题，因为它总是用使用方的选项编译。但它并没有免去版本冲突：只要两份头文件进入同一个程序，就是上一节的情形。

有些库两种方式都提供。fmt 默认编译成库，定义 `FMT_HEADER_ONLY` 后变成 header-only；spdlog 既可以只包含头文件使用，也可以编译成库（此时定义 `SPDLOG_COMPILED_LIB`）。选择时注意同一个程序里只能用一种方式，否则又是同一实体的两份不同定义。

## 把依赖拿进来的几种方式

下面的命令在本机执行：CMake 3.29.3、Ninja、Homebrew 7.0.9、git。vcpkg、Conan 和 pkg-config 本机没有安装，相关内容只描述用法，不给运行结果。CMake 本身的用法见 [[toolchain/cmake|CMake]]。

### 系统包管理器：brew、apt

用 `brew install zstd` 或 `apt install libzstd-dev` 安装，再在 CMake 中查找：

```cmake
find_package(zstd 1.5 REQUIRED CONFIG)
target_link_libraries(app PRIVATE zstd::libzstd_shared)
```

不用 CMake 的项目可以用 `pkg-config --cflags --libs libzstd` 取得上面 `.pc` 文件里的参数。

优点是什么都不用构建。缺点是版本由发行版决定，选项也由发行版决定。Linux 发行版里的 C++ 库一般用发行版默认的 GCC 和 libstdc++ 构建，你的项目换成 Clang + libc++ 就不能直接用它们。Homebrew 的库用 Apple 的工具链构建，与本机 Homebrew LLVM 的 libc++ 并不是同一个标准库（见上面的 impl 提示）；zstd 是 C 库，所以不受影响。

`find_package` 找到的也不一定是你以为的那一份。本机第一次配置时，CMake 选中的是 Anaconda 自带的 zstd：

```text
$ grep zstd_DIR build/CMakeCache.txt
zstd_DIR:PATH=/opt/homebrew/anaconda3/lib/cmake/zstd
$ ./build/app
fmt 120100; zstd header 1.5.5, runtime 1.5.5
```

原因是 `PATH` 中 `/opt/homebrew/anaconda3/bin` 排在 `/opt/homebrew/bin` 前面，而 CMake 会从 `PATH` 中的每个 `bin` 目录推出一个前缀去搜索包配置文件。显式指定前缀后得到的才是 Homebrew 的版本：

```text
$ cmake -S . -B build2 -G Ninja -DCMAKE_PREFIX_PATH=/opt/homebrew
$ grep zstd_DIR build2/CMakeCache.txt
zstd_DIR:PATH=/opt/homebrew/lib/cmake/zstd
$ ./build2/app
fmt 120100; zstd header 1.5.7, runtime 1.5.7
```

依赖系统包时，构建日志里要能看到每个依赖解析到了哪个路径和版本，CI 上要固定基础镜像。

### 从源码一起构建：add_subdirectory 与 FetchContent

把依赖的源码放在项目旁边，用 `add_subdirectory(third_party/fmt)` 加入构建，依赖就成了项目里的普通目标。`FetchContent` 做的是同一件事，只是源码在配置时下载：

```cmake title="CMakeLists.txt"
cmake_minimum_required(VERSION 3.24)
project(deps_demo LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

include(FetchContent)
FetchContent_Declare(fmt
  URL      https://github.com/fmtlib/fmt/releases/download/12.1.0/fmt-12.1.0.zip
  URL_HASH SHA256=695fd197fa5aff8fc67b5f2bbc110490a875cdf7a41686ac8512fb480fa8ada7
  FIND_PACKAGE_ARGS 12)
FetchContent_MakeAvailable(fmt)

find_package(zstd 1.5 REQUIRED CONFIG)

add_executable(app main.cpp)
target_link_libraries(app PRIVATE fmt::fmt zstd::libzstd_shared)
```

```cpp title="main.cpp" ok
#include <fmt/format.h>
#include <zstd.h>
int main() {
  fmt::print("fmt {}; zstd header {}, runtime {}\n",
             FMT_VERSION, ZSTD_VERSION_STRING, ZSTD_versionString());
}
```

`FIND_PACKAGE_ARGS`（CMake 3.24 起）的意思是先 `find_package(fmt 12)`，找不到再下载。本机没有安装 fmt，所以走了下载：

```text
$ cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH=/opt/homebrew
-- {fmt} version: 12.1.0
-- Configuring done (2.1s)
$ cmake --build build
[4/5] Linking CXX static library _deps/fmt-build/libfmt.a
[5/5] Linking CXX executable app
```

从源码构建的好处在 Ninja 的命令里看得最清楚。fmt 的源文件和项目自己的源文件用的是同一个编译器、同一组选项：

```text
$ ninja -C build -t commands | grep -E 'format.cc|main.cpp'
clang++ ... -O3 -DNDEBUG -std=gnu++23 ... -c _deps/fmt-src/src/format.cc
clang++ ... -O3 -DNDEBUG -std=gnu++23 ... -c main.cpp
```

上一节表格里的问题自动消失了：项目加上 `-fsanitize=address` 或换一个标准库，fmt 也跟着重新构建。代价是每个开发者、每次全新的 CI 构建都要编译所有依赖，大的依赖（LLVM、Boost 全家、gRPC）这样做很慢。

固定版本是使用方的责任。上面的 `URL_HASH` 把下载内容固定到一个确切的压缩包；用 `GIT_REPOSITORY` 时，`GIT_TAG` 应该写提交哈希而不是分支名，因为分支会移动，标签也可以被重新指向。

固定了版本，换工具链时依赖仍可能出问题。本机最初用的是 fmt 11.1.4，它的 `format.h` 调用了 `malloc` 和 `free`，却没有包含 `<cstdlib>`，过去靠其他标准头文件间接包含。Clang 23 的 libc++ 不再间接包含它，于是在模板定义处报错：

```text
fmt/format.h:752:35: error: call to function 'free' that is neither visible in the
template definition nor found by argument-dependent lookup
```

这是两阶段查找的规则（[[topics/two-phase-lookup]]）：模板定义中的非依赖名字在定义处查找。升级编译器和标准库时，依赖也要一起验证；fmt 12.1.0 在本机可以正常编译。

### git submodule

子模块把另一个仓库的某个提交记录在本仓库里：

```bash
git submodule add https://github.com/fmtlib/fmt.git third_party/fmt
git -C third_party/fmt checkout 12.1.0
git add third_party/fmt .gitmodules
```

本仓库记录的是 fmt 的提交哈希，不是标签名，所以版本是确定的。CMake 中用 `add_subdirectory(third_party/fmt)` 引入，效果与 FetchContent 相同。

子模块的问题主要在使用上：克隆时要加 `--recurse-submodules`，切换分支后要 `git submodule update`，否则子模块停在旧提交上；依赖之间没有版本求解，两个子模块各自又带了同一个库时，就会出现上一节的情形。

### vendoring

**vendoring** 是把依赖的源码直接复制进自己的仓库（常放在 `third_party/` 或 `vendor/` 下），作为普通文件提交。不需要网络，构建最可靠，代码审查也能看到依赖的每一行变化。

代价是升级要手工完成，而且很容易在复制的源码里顺手改几行，之后就再也合不回上游。建议在目录里保留一个说明文件，写明上游地址、版本或提交哈希、许可证和本地修改。

### vcpkg

vcpkg 是微软维护的源码包管理器：每个库对应一个 port，即一段从源码构建的脚本，在本机按选定的配置构建后安装。本机没有安装 vcpkg。

**清单模式**（manifest mode）下，项目根目录放一个 `vcpkg.json`：

```json title="vcpkg.json"
{
  "dependencies": [
    "fmt",
    { "name": "zstd", "version>=": "1.5.6" }
  ],
  "builtin-baseline": "<vcpkg 仓库的某个提交哈希>",
  "overrides": [
    { "name": "fmt", "version": "11.0.2" }
  ]
}
```

`builtin-baseline` 指向 vcpkg 端口仓库的一个提交，它决定了每个库默认用哪个版本。`version>=` 给出下限，`overrides` 强制指定版本。vcpkg 对每个库只选一个版本：满足所有下限（基线本身也是一个下限）的最低版本，因此一个程序里不会出现两个版本。

配置 CMake 时指定 vcpkg 的工具链文件，`find_package` 就能找到 vcpkg 构建的库：

```bash
cmake -S . -B build -DCMAKE_TOOLCHAIN_FILE="$VCPKG_ROOT/scripts/buildsystems/vcpkg.cmake"
```

**triplet** 描述目标平台和构建方式，如 `arm64-osx`、`x64-linux`、`x64-windows-static`。自定义 triplet 是一个 CMake 文件，设置 `VCPKG_TARGET_ARCHITECTURE`、`VCPKG_LIBRARY_LINKAGE`（静态或动态）、`VCPKG_CRT_LINKAGE`、`VCPKG_CXX_FLAGS` 等，相当于把上一节表格中的选项写成一份配置，所有依赖都按它构建。

**二进制缓存**默认开启。vcpkg 为每个包计算一个哈希，包括 port 文件、triplet、编译器版本和所有依赖的哈希，任何一项变化都重新构建。缓存位置用环境变量 `VCPKG_BINARY_SOURCES` 配置，可以指向本地目录或团队共享的存储，CI 机器之间由此共享构建结果。

### Conan

Conan 是另一个跨平台的 C/C++ 包管理器，用 Python 写 recipe，同样可以从源码构建或下载预编译的二进制。本机没有安装 Conan，下面按 Conan 2 的用法描述。

```ini title="conanfile.txt"
[requires]
fmt/11.0.2
zstd/1.5.6

[generators]
CMakeDeps
CMakeToolchain

[layout]
cmake_layout
```

Conan 用 **profile** 描述编译配置，`conan profile detect` 根据本机编译器生成默认 profile：

```ini title="profile"
[settings]
os=Macos
arch=armv8
build_type=Release
compiler=apple-clang
compiler.version=17
compiler.libcxx=libc++
compiler.cppstd=20
```

profile 中的 `settings` 参与计算每个二进制包的 package ID。换了 `compiler.libcxx` 或 `compiler.cppstd`，就会找不到匹配的预编译包，需要用 `--build=missing` 从源码构建。这是 Conan 处理选项一致性的方式：选项不同就是不同的二进制。

```bash
conan install . --output-folder=build --build=missing
conan lock create .                          # 生成 conan.lock
conan install . --lockfile=conan.lock ...    # 之后按锁文件安装
```

**锁文件**（lockfile）记录依赖图中每个包解析到的确切版本和 recipe 修订号。版本范围（如 `fmt/[>=11 <12]`）让依赖可以自动更新，锁文件让同一次提交在任何机器上解析出同样的结果。

## 可复现：锁定版本

可复现的构建要求同一个提交在任何时间、任何机器上得到同样的依赖。各方式对应的做法：

| 方式 | 锁定什么 | 写在哪里 |
|---|---|---|
| 系统包 | 发行版或镜像版本 | CI 基础镜像、Dockerfile；Homebrew 基本无法锁定 |
| FetchContent | `URL` + `URL_HASH`，或 `GIT_TAG` 写提交哈希 | `CMakeLists.txt` |
| git submodule | 提交哈希 | 父仓库的树对象，自动记录 |
| vendoring | 源码本身 | 仓库里的文件 |
| vcpkg | `builtin-baseline`、`overrides` | `vcpkg.json`、`vcpkg-configuration.json` |
| Conan | 锁文件 | `conan.lock` |

依赖的版本只是一半。编译器版本、标准库版本和 CMake 版本同样影响结果，上面 fmt 11.1.4 的例子就是换了标准库之后才出错的。CI 中应当固定工具链版本，并在构建日志里打印出来。

FetchContent 还有两个与可复现有关的开关：`FETCHCONTENT_FULLY_DISCONNECTED=ON` 禁止配置时访问网络，只用已有的源码；`FETCHCONTENT_SOURCE_DIR_<名字>` 让某个依赖改用本地目录，便于在不改 `CMakeLists.txt` 的情况下调试依赖。

## 供应链：校验下载的内容

从网络获取的代码会在你的机器上编译和执行，构建脚本本身也会执行。基本的防线是校验哈希：记录一个确切的哈希，下载内容不符就拒绝。把上面 `URL_HASH` 的一个十六进制数字改掉，CMake 下载后拒绝使用：

```text
-- SHA256 hash of
    .../fmt-subbuild/fmt-populate-prefix/src/fmt-12.1.0.zip
  does not match expected value
    expected: '695ed197fa5aff8fc67b5f2bbc110490a875cdf7a41686ac8512fb480fa8ada7'
      actual: '695fd197fa5aff8fc67b5f2bbc110490a875cdf7a41686ac8512fb480fa8ada7'
-- Hash mismatch, removing...
CMake Error at .../FetchContent.cmake:1714 (message):
  Build step for fmt failed: 1
```

其他方式的对应机制：git 的提交哈希本身就是内容的哈希；vcpkg 的每个 port 在 `portfile.cmake` 中记录源码包的 SHA512；Conan 的 recipe 修订号是 recipe 内容的哈希，锁文件把它也固定下来。

其余几条建议：

- 哈希要在第一次引入时根据可信来源确认（例如对照发布页公布的哈希，或者自己审查过源码），之后它只能保证内容没有变。
- 依赖升级像普通代码改动一样经过审查，看一眼变更记录和差异。
- 团队较大时，用内部镜像或私有仓库（vcpkg 的自定义 registry、Conan 的私有 remote）托管依赖，避免构建依赖外部网站的可用性。
- 需要软件物料清单（SBOM）时，vcpkg 会为每个安装的包生成 SPDX 格式的文件；其他方式需要自己整理依赖清单。

## 许可证

引入依赖也引入了它的许可证义务。MIT、BSD、Apache-2.0、Boost Software License 等宽松许可证一般只要求保留版权和许可声明；LGPL 对静态链接有额外要求（使用者要能替换库），GPL 要求整个程序以兼容的许可证发布。依赖的依赖也要算在内。分发二进制前列出所有依赖的许可证，有疑问时咨询法务。

## 怎么选

下面是建议，理由写在各列里，不是唯一的答案：

| 项目类型 | 建议 | 理由 |
|---|---|---|
| 小工具、示例、课程作业 | FetchContent，固定 `URL_HASH` 或提交哈希 | 无需额外工具；依赖少，从源码构建的时间可以接受 |
| 开源库 | 只用 `find_package` 声明依赖，让使用方决定怎样提供；测试依赖可用 FetchContent | 库不应替使用方选择版本，更不能把依赖的源码带进公开头文件 |
| 中大型应用、依赖多 | vcpkg 清单模式或 Conan，加锁定和二进制缓存 | 需要版本求解和缓存，自己维护几十个 FetchContent 不现实 |
| 公司内部的大型代码库 | vendoring 或单仓库，配合统一的构建系统 | 完全掌控工具链和选项，所有代码一起审查、一起构建 |
| 只面向某个 Linux 发行版的软件 | 系统包 | 与发行版一起维护，由发行版负责安全更新 |
| 嵌入式、交叉编译 | vendoring 或 vcpkg/Conan 的自定义 triplet/profile | 选项特殊，预编译包通常不适用 |

几种方式也可以组合。常见的做法是用 `find_package` 写构建脚本，由 vcpkg、Conan 或 `FetchContent` 的 `FIND_PACKAGE_ARGS` 在背后提供这些包。这样换一种依赖来源时，`CMakeLists.txt` 不用改。

## 常见误解

!!! pitfall "header-only 就不会有版本冲突"
    header-only 只是避免了预编译二进制与选项不一致的问题。两个版本的头文件进入同一个程序，正是上文 `mini` 例子的情形：ODR 违规，不要求诊断。

!!! pitfall "链接通过了，版本就没问题"
    链接器只比较符号名（[[toolchain/linking-and-symbols]]）。类的布局、inline 函数的内容、宏决定的成员，都不在符号名里。

!!! pitfall "Release 能跑，Debug 崩溃，是编译器的 bug"
    ODR 违规的表现依赖内联决策。`mini` 的例子在 `-O2` 下输出正确，在 `-O0` 下崩溃。遇到这类现象时，先检查是否有同一个库的两个版本、或用不同选项构建的同一个库。

## 思考题

!!! question "1"
    `liba` 和 `libb` 都把 `mini` 1.0 的头文件复制进了自己的源码树，内容完全相同，只是一个放在 `liba/third_party/`，一个放在 `libb/third_party/`。程序违反 ODR 吗？

<details markdown="1">
<summary>答案</summary>

不违反。[[basic.def.odr#16]] 要求的是每个定义由相同的记号序列组成、名字查找到相同的实体等，与头文件在磁盘上的位置无关。只要两份文件的内容和被包含时的环境（宏、之前的声明）相同，就满足要求。风险在于以后有一方升级了，另一方没有。
</details>

!!! question "2"
    把 `mini` 编译成动态库 `libmini.dylib` 并只导出非 inline 的函数，能解决两个版本共存的问题吗？

<details markdown="1">
<summary>答案</summary>

只能解决一部分。两个版本中同名的非 inline 函数怎样解析，取决于平台规则：ELF 默认按全局搜索顺序解析，引用会绑定到先找到的那一份；Mach-O 的两级命名空间记录每个引用来自哪个动态库（据文档）。见 [[toolchain/linking-and-symbols]] 的动态库一节。标准对此没有任何保证。头文件里的 inline 函数和类定义仍在使用方的 TU 中编译，布局不同的问题依旧存在。可靠的做法仍是一个程序只用一个版本，或者用内联命名空间等手段让两个版本成为不同的实体。
</details>

!!! question "3"
    用 `FetchContent` 引入一个库，并在顶层设置了 `CMAKE_CXX_STANDARD 23`。这个库自己的 `CMakeLists.txt` 里写了 `set(CMAKE_CXX_STANDARD 17)`。两边的代码会用不同的 `-std` 编译吗？这为什么可能有问题？

<details markdown="1">
<summary>答案</summary>

会。`add_subdirectory` 和 `FetchContent_MakeAvailable` 把依赖作为子目录加入，子目录里的 `set` 只影响它自己的作用域，所以依赖的源文件按 C++17 编译，项目自己的按 C++23 编译。本机 CMake 3.29 生成的命令里，依赖的源文件干脆没有 `-std=`，因为 C++17 就是 Clang 23 的默认值（`gnu++17`）。如果依赖的公开头文件里有按 `__cplusplus` 选择的成员或类型别名，两边看到的定义就不同，就是上文讨论的 ODR 违规。检查 `ninja -t commands` 或 `compile_commands.json` 可以确认每个文件实际用的选项。
</details>
