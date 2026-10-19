---
title: 模块的工程实践
summary: 编译器怎样实现 C++20 模块：各编译器的 BMI，Clang 的两种编译方式和 reduced BMI，依赖扫描，CMake 的 CXX_MODULES 文件集，import std 和头文件单元的现状，以及模块附属怎样体现在符号名里。
group: 工具链
status: draft
order: 30
related: module, module.unit, module.import, module.global.frag, module.reach, basic.link, basic.def.odr, lex.phases, toolchain/compilation-pipeline
tags: 模块, 构建
updated: 2026-10-19
---

!!! tldr
    - 编译模块接口单元除了目标文件，还产出一个 BMI（编译器内部表示的序列化）。导入方读取 BMI，不再重新解析源码。
    - BMI 与编译器版本和关键编译选项绑定，不能当作库接口分发。库发布的是模块接口的源码。
    - 导入方必须在 BMI 生成之后才能编译，所以构建系统要先做依赖扫描，弄清每个文件提供和需要哪些模块。CMake 3.28 起用 `FILE_SET CXX_MODULES` 配合 Ninja 完成这件事。
    - 模块附属体现在 Itanium 修饰名的 `W<模块名>` 里。两个模块中的同名实体符号不同，不会冲突；导出与否不影响符号名。
    - 具名模块加 `import std;` 是目前最成熟的组合；头文件单元在 Clang 里仍是实验性的，CMake 不支持。

标准对模块的描述完全是语义上的：一个 TU 导入另一组 TU，被导入的声明变得可达或可见（[[module.import]]、[[module.reach]]）。标准没有提到文件、编译顺序或二进制接口文件，[[lex.phases]] 只说被依赖的模块单元的源码是否必须可用由实现定义。

这套语义是按一种特定的实现方式设计的：模块接口单元翻译一次，产出一份序列化的编译器内部表示，导入方直接读取。这带来了 `#include` 时代没有的工程问题：编译顺序、依赖发现和 BMI 的兼容性。

!!! note "实验环境"
    命令、输出和数字来自本机：Homebrew Clang 23.1（libc++，macOS arm64）、CMake 3.29、Ninja。GCC 和 MSVC 的部分只描述机制，没有在本机验证。

## BMI

编译一个模块接口单元（包括接口分区）或实现分区时，编译器除了产生目标文件，还产生一个 **BMI**（Built Module Interface，也叫 CMI，Compiled Module Interface）。它本质上是编译器 AST 的序列化，导入方读取它而不是重新解析源码。

| 编译器 | BMI | 说明 |
|---|---|---|
| Clang | `.pcm` 文件 | 与 Clang 的预编译头共用序列化格式；要显式告诉编译器每个 `.pcm` 在哪里 |
| GCC | `.gcm` 文件，默认在当前目录的 `gcm.cache/` 下 | 用 `-fmodules`（旧版本为 `-fmodules-ts`）开启；通过模块映射器（module mapper）把模块名映射到文件路径 |
| MSVC | `.ifc` 文件 | IFC 格式有公开的规范；接口单元常用 `.ixx` 扩展名 |

BMI 不可移植。它绑定于具体的编译器版本，也绑定于影响语义的编译选项，如语言标准版本和是否开启异常。库作者分发的仍然是模块接口的源码，由使用者用自己的编译器和选项构建 BMI。

Clang 会严格检查配置是否一致。本机用 `-std=c++23` 构建 `geo.pcm`，再分别用 `-std=c++20` 和 `-fno-exceptions` 编译导入方，得到：

```text
error: C++23 was enabled in precompiled file '.../geo.pcm' but is currently disabled
error: exception handling was enabled in precompiled file '.../geo.pcm' but is currently disabled
error: precompiled file '.../geo.pcm' cannot be loaded due to a configuration mismatch with the current compilation [-Wmodule-file-config-mismatch]
```

只改优化级别（如 `-O2`）不影响 BMI 的使用。

BMI 还带来编译顺序的约束：导入方必须在被导入模块的 BMI 生成之后才能编译。原本所有 `.cpp` 可以完全并行编译，现在变成了一张有向无环图。

## Clang 的编译方式

### 两阶段

```bash
clang++ -std=c++23 --precompile geo.cppm -o geo.pcm      # 第一阶段：源码 → BMI
clang++ -std=c++23 -c geo.pcm -o geo.o                    # 第二阶段：BMI → 目标文件
```

第一阶段只运行前端，做解析和语义分析。BMI 一产出，依赖它的导入方就可以开始编译，不必等第二阶段的代码生成。构建的关键路径上因此只有前端的时间。

### 一阶段

```bash
clang++ -std=c++23 -c geo.cppm -fmodule-output=geo.pcm -o geo.o
```

一次调用同时产出目标文件和 BMI。CMake 驱动 Clang 时用的就是这种方式。

### 完整 BMI 与 reduced BMI

`--precompile` 产出**完整 BMI**，它保留了生成目标代码所需的一切，例如非 inline 函数的函数体。导入方其实不需要这些。**reduced BMI** 只保留导入方需要的部分，并且执行 [[module.global.frag#3]] 的丢弃规则：全局模块片段中没有被模块本身用到的声明（不是 [[g:decl-reachable]] 的声明）被丢弃，导入方看不到它们。

本机 Clang 23 的行为：

- `-c x.cppm -fmodule-output=x.pcm` 默认产出 reduced BMI，与显式加 `-fmodules-reduced-bmi` 的结果大小相同；加 `-fno-modules-reduced-bmi` 则产出与 `--precompile` 相同的完整 BMI。
- 下面例子中的 `geo.pcm`（全局模块片段里 `#include <cmath>`）：完整 BMI 约 920 KB，reduced BMI 约 365 KB。

两者在语义上也有差别。[[module.global.frag#5]] 的标准例子中，`use_g<int>()` 应当因为 `N::g` 被丢弃而失败。用完整 BMI 时 Clang 接受它，用 reduced BMI 时 Clang 正确地报错：

<div class="compare" markdown="1">

```text
# --precompile（完整 BMI）
$ clang++ -fsyntax-only \
    -fmodule-file=M=M.pcm Mi.cpp
（通过）
```

```text
# -fmodule-output（reduced BMI）
$ clang++ -fsyntax-only \
    -fmodule-file=M=M.pcm Mi.cpp
error: use of undeclared identifier 'g'
```

</div>

也就是说，构建方式会改变 Clang 对同一个程序是否良构的判断。依赖了本应丢弃的全局模块片段声明的代码，换一种构建方式就可能编译不过。

### 告诉编译器 BMI 在哪里

Clang 不会自动寻找 BMI，要显式指定：

| 选项 | 含义 |
|---|---|
| `-fmodule-file=<模块名>=<路径>` | 指定某个模块或分区（如 `geo:shapes`）的 BMI 路径 |
| `-fprebuilt-module-path=<目录>` | 在目录中按 `<模块名>.pcm` 查找；分区 `M:P` 对应 `M-P.pcm` |
| `-fmodule-file=<路径>` | 不带名字的形式，用于头文件单元的 BMI |

扩展名 `.cppm`（或 `.ccm`、`.cxxm`、`.c++m`）告诉 Clang 这是模块接口单元；其他扩展名要加 `-x c++-module`。

## 一个完整的例子

一个带接口分区和实现单元、并使用 `import std;` 的小模块：

```cpp title="shapes.cppm"
export module geo:shapes;
export namespace geo {
  struct Circle { double r; };
  double area(const Circle& c);
}
```

```cpp title="geo.cppm"
module;
#include <cmath>
export module geo;
export import :shapes;
namespace geo {
  double pi() { return std::acos(-1.0); }   // 模块链接：只在模块 geo 内可用
}
```

```cpp title="geo.cpp"
module geo;
namespace geo {
  double area(const Circle& c) { return pi() * c.r * c.r; }
}
```

```cpp title="main.cpp" ok
import std;
import geo;
int main() {
  geo::Circle c{2.0};
  std::println("area = {:.3f}", geo::area(c));
}
```

两阶段构建，按依赖顺序执行：

```bash
LIBCXX=/opt/homebrew/opt/llvm/share/libc++/v1
# 标准库模块（每种工具链配置构建一次）
clang++ -std=c++23 -Wno-reserved-module-identifier --precompile $LIBCXX/std.cppm -o std.pcm
# 先分区，后主接口
clang++ -std=c++23 --precompile shapes.cppm -o geo-shapes.pcm
clang++ -std=c++23 --precompile geo.cppm -fmodule-file=geo:shapes=geo-shapes.pcm -o geo.pcm
# BMI → 目标文件
clang++ -std=c++23 -c geo-shapes.pcm -o geo-shapes.o
clang++ -std=c++23 -c geo.pcm -fmodule-file=geo:shapes=geo-shapes.pcm -o geo.o
clang++ -std=c++23 -c std.pcm -o std.o
# 实现单元与导入方
clang++ -std=c++23 -c geo.cpp -fmodule-file=geo=geo.pcm -fmodule-file=geo:shapes=geo-shapes.pcm -o geo-impl.o
clang++ -std=c++23 -c main.cpp -fprebuilt-module-path=. -o main.o
# 链接
clang++ main.o geo.o geo-shapes.o geo-impl.o std.o -o app
./app          # 输出：area = 12.566
```

`std` 是保留的模块名（[[module.unit#1]]），Clang 对 `export module std;` 给出警告，所以构建 `std.pcm` 时要加 `-Wno-reserved-module-identifier`。本机构建 `std.pcm` 约需 1 秒，产物约 37 MB。

第二阶段编译 `geo.pcm` 时仍要指明 `geo:shapes` 的位置。BMI 记录了依赖哪些模块，但不记录它们的路径。`main.cpp` 用 `-fprebuilt-module-path=.`，Clang 自己找到 `std.pcm` 和 `geo.pcm`，再按 `geo.pcm` 中记录的模块名找到 `geo-shapes.pcm`。

一阶段构建的写法：

```bash
clang++ -std=c++23 -c shapes.cppm -fmodule-output=geo-shapes.pcm -o geo-shapes.o
clang++ -std=c++23 -c geo.cppm -fmodule-file=geo:shapes=geo-shapes.pcm -fmodule-output=geo.pcm -o geo.o
clang++ -std=c++23 -c geo.cpp -fprebuilt-module-path=. -o geo-impl.o
clang++ -std=c++23 -c main.cpp -fprebuilt-module-path=. -fmodule-file=std=std.pcm -o main.o
clang++ main.o geo.o geo-shapes.o geo-impl.o std.o -o app
```

编译时间方面有一个本机数据点。用 `import std;` 的程序（vector、`ranges::sort`、`println`）和用 `#include <vector>`、`<algorithm>`、`<print>` 的等价程序，各编译三次（`-c -O0`），前者约 0.30 s，后者约 0.53 s。这还没有计入 `std.pcm` 只需构建一次的摊销效果。这不是严格的基准测试。

## 模块附属在符号名里

[[basic.link#8]] 规定，附属于不同模块的同名实体是不同的实体；[[module.unit#7]] 规定声明附属于哪个模块。Itanium C++ ABI（Clang 和 GCC 在非 Windows 平台上使用）用 `W` 前缀把模块名编码进修饰名。上例的 `nm` 输出（Mach-O 符号多一个前导 `_`）：

```text
geo-impl.o:
                 U __ZN3geoW3geo2piEv
0000000000000000 T __ZN3geoW3geo4areaERKNS_S0_6CircleE
geo.o:
0000000000000018 S __ZGIW3geo
0000000000000000 T __ZN3geoW3geo2piEv
                 U _acos
geo-shapes.o:
0000000000000000 S __ZGIW3geoWP6shapes
```

`_ZN3geoW3geo2piEv` 中，`N 3geo` 是命名空间 `geo`，`W3geo` 是模块 `geo`，然后是 `2pi`。`llvm-cxxfilt` 把它解码为 `geo::pi@geo()`。命名空间和模块同名只是巧合，两者在修饰名中的位置不同。

`geo::pi` 没有导出，是模块链接；`geo::area` 导出了，是外部链接。但两者都带 `W3geo`，修饰名反映的是附属，不是链接。模块链接的实体在目标文件里仍是全局符号 `T`，链接器不知道模块链接的存在。别的模块之所以不会意外地链接到它，是因为修饰名里有模块名。

`geo::area` 声明在分区 `:shapes` 中，修饰名里却没有分区名。这与 [[module.unit#3]] 的注 1 一致：模块划分成哪些单元，对模块外部不可见。分区名只出现在模块初始化函数的符号里：`_ZGIW3geoWP6shapes`，其中 `GI` 表示模块初始化函数，`WP` 表示分区。`_ZGIW3geo` 是模块 `geo` 的初始化函数，导入方的初始化代码会先调用它，以保证被导入模块的动态初始化先执行。

另外两条规则：

- 带点的模块名逐段编码。`export module a.b;` 中的 `f()` 修饰为 `_ZW1aW1b1fv`。
- 出现在 `extern "C++"` 块中的声明附属于全局模块（[[module.unit#7]] ¶7.2.4），修饰名里没有 `W`。在模块 M 中声明的 `extern "C++" int f3();` 修饰为 `_Z2f3v`，与在普通头文件中声明完全相同。渐进迁移时用它保持 ABI 不变。

### 两个模块中的同名实体

```cpp title="A.cppm"
export module A;
export int f() { return 1; }
int helper() { return 10; }
export int a() { return helper(); }
```

```cpp title="B.cppm"
export module B;
export int f() { return 2; }
int helper() { return 20; }
export int b() { return helper(); }
```

```cpp title="ua.cpp"
import A;
int ua() { return f() + a(); }
```

```cpp title="ub.cpp"
import B;
int ub() { return f() + b(); }
```

```cpp title="main.cpp" ok
int ua(); int ub();
int main() { return ua() + ub(); }   // 1+10 + 2+20 = 33
```

本机链接成功，返回 33。两个 `helper` 修饰为 `_ZW1A6helperv` 和 `_ZW1B6helperv`，两个 `f` 分别是 `_ZW1A1fv` 和 `_ZW1B1fv`。如果它们都写在头文件里，这就是一次 ODR 违规（IFNDR），链接器可能报重复符号，也可能静默选一个。

但是一个 TU 不能同时 `import A;` 和 `import B;`。两个 `f` 的声明对应（[[basic.scope.scope]]），却附属于不同的模块，所以是两个互相冲突的实体（[[basic.link#10]] 注 5）。本机 Clang 23 在导入处就报错，即使没有调用 `f()`：

```text
error: declaration 'f' attached to named module 'A' cannot be attached to other modules
```

### 类内定义的成员函数不再隐式 inline

[[class.mfct#1]] 规定，只有附属于全局模块的类，其类内定义的成员函数才隐式 inline。用 `nm -m` 观察：

```text
W.o（export module W; export struct S { int get() {...} inline int iget() {...} };）:
  (__TEXT,__text) external      __ZNW1W1S3getEv     ← 强定义
  (__TEXT,__text) weak external __ZNW1W1S4igetEv    ← 显式 inline，弱定义
g.o（普通 TU 中的 struct G { int get() {...} };）:
  (__TEXT,__text) weak external __ZN1G3getEv        ← 隐式 inline，弱定义
```

导入 W 的 TU 调用 `s.get()` 时，生成对 `__ZNW1W1S3getEv` 的外部引用，而不是内联展开。所以修改 `get` 的函数体不会改变 W 的 ABI。

GCC 在 Itanium 平台上同样使用 `W` 前缀的模块修饰（本机未验证）。MSVC 使用自己的修饰和链接方案，模块附属信息的记录方式不同。

## 依赖扫描

使用 `#include` 时，构建系统不需要事先知道文件之间的依赖就能开始编译。头文件依赖是编译之后由 `-MD` 报告的，只用于增量构建。模块改变了这一点：编译 `main.cpp` 之前，就必须知道它导入了 `geo`，并且 `geo.pcm` 已经生成。

办法是在编译之前做一次**依赖扫描**：只预处理每个源文件，找出它提供哪个模块、需要哪些模块。[[P1857R3]] 把 `module` 和 `import` 行变成了预处理指令，目的之一就是让扫描只需预处理、不需完整解析 C++。扫描结果的格式由 WG21 文档 P1689 规定，是一种 JSON。Clang 用 `clang-scan-deps -format=p1689` 输出这种格式，GCC 和 MSVC 也有对应的选项（本机未验证细节）。

```bash
clang-scan-deps -format=p1689 -- clang++ -std=c++23 -c geo.cppm -o geo.o
```

```json
{
  "revision": 0,
  "rules": [
    {
      "primary-output": "geo.o",
      "provides": [
        { "is-interface": true, "logical-name": "geo", "source-path": "geo.cppm" }
      ],
      "requires": [
        { "logical-name": "geo:shapes" }
      ]
    }
  ],
  "version": 1
}
```

`main.cpp` 的扫描结果没有 `provides`，`requires` 是 `std` 和 `geo`。构建系统汇总所有扫描结果，建立"模块名 → 提供它的源文件 → BMI 路径"的映射，排出编译顺序，并为每个 TU 生成对应的 `-fmodule-file=` 参数。

单独编译一个 TU 时看不到的错误，也在这里暴露出来，例如一个模块有两个主接口单元（[[module.unit#2]]，IFNDR），或者模块之间循环依赖（[[module.import#10]]）。

## CMake

CMake 3.28 起正式支持 C++20 具名模块，要求使用 Ninja 或 Visual Studio 生成器，Makefile 生成器不支持。模块接口源文件放进类型为 `CXX_MODULES` 的文件集（file set）：

```cmake title="CMakeLists.txt"
cmake_minimum_required(VERSION 3.28)
project(greet LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_library(greet)
target_sources(greet
  PUBLIC
    FILE_SET CXX_MODULES FILES
      src/greet.cppm          # 主接口单元
      src/greet-fmt.cppm      # 接口分区 greet:fmt
  PRIVATE
    src/greet.cpp)            # 实现单元：普通源文件

add_executable(app src/main.cpp)
target_link_libraries(app PRIVATE greet)
```

本机用 `cmake -G Ninja -DCMAKE_CXX_COMPILER=/opt/homebrew/opt/llvm/bin/clang++` 配置后构建，`ninja -v` 显示三步：

1. 对每个源文件（包括 `main.cpp` 和实现单元 `greet.cpp`）运行 `clang-scan-deps -format=p1689`，输出 `.ddi` 文件；
2. `cmake -E cmake_ninja_dyndep` 汇总 `.ddi`，生成 Ninja 的动态依赖（dyndep）文件和每个 TU 的 `.modmap` 响应文件；
3. 按依赖顺序编译，每条命令通过 `@xxx.o.modmap` 引用这些参数。`greet.cppm` 的 modmap 是：

    ```text
    -x c++-module
    -fmodule-output=CMakeFiles/greet.dir/greet.pcm
    -fmodule-file=greet:fmt=CMakeFiles/greet.dir/greet-fmt.pcm
    ```

    可见 CMake 用的是 Clang 的一阶段编译，因此默认产出 reduced BMI。

实现单元（`module greet;`）不放进 `CXX_MODULES` 文件集，它只是普通的源文件，但仍然会被扫描。`PUBLIC` 的 `CXX_MODULES` 文件集让依赖 `greet` 的目标可以导入它；由于 BMI 不能跨编译配置复用，库对外提供的是模块接口的源码。两个源文件都写 `export module M;` 时，本机 Ninja 报 `multiple rules generate CMakeFiles/dup.dir/M.pcm` 并停止。

本机的 CMake 3.29 不能自动构建标准库模块。较新的 CMake 以实验特性的形式支持 `import std;`（目标属性 `CXX_MODULE_STD`，还要设置一个随版本变化的实验开关），具体用法以所用版本的文档为准，本机未验证。手动的做法就是前面的命令：自己从 `std.cppm` 构建 `std.pcm` 并加入编译。

## 头文件单元的现状

[[module.import#5]] 的头文件单元（`import <vector>;`、`import "config.h";`）是实现最不成熟的部分。

Clang 支持它：用 `-fmodule-header=user|system` 配合 `-xc++-header` 或 `-xc++-system-header` 构建头文件单元的 BMI，再用不带名字的 `-fmodule-file=<路径>` 导入。本机可用，宏的导入也正常，但每次导入都有警告 "the implementation of header units is in an experimental phase"。CMake 3.29 的 `CXX_MODULES` 文件集只处理具名模块，不支持头文件单元。

难点在构建系统。头文件单元有自己独立的宏环境（[[module.import#5]] 注 2），同一个头文件在不同编译选项下可能需要不同的 BMI。标准在 ¶5.3 中规定，两个 TU 中的 `import "x.h"` 是否导入同一个头文件单元是未指定的，就是为这种情况留余地。

MSVC 支持把可导入头文件的 `#include` 自动转换为 `import`，这是 [[cpp.include#10]] 允许的实现定义行为。

目前比较稳妥的做法是：自己的代码用具名模块加 `import std;`，第三方头文件放在全局模块片段里 `#include`。

## 模块对 ODR 的影响

附属于具名模块的同名实体是不同的实体，修饰名也不同。两个库都有 `detail::helper` 不再是问题，前提是它们都写在具名模块中。

全局模块的实体仍然共享。全局模块片段中 `#include` 进来的声明附属于全局模块，跨 TU 的 ODR 要求与头文件时代相同；不同模块用不同的宏配置包含同一个头文件，仍然是 IFNDR。区别在于同时导入这些模块时，编译器合并 BMI 时会比较定义，有机会报错。本机实验中，同一个 `struct Cfg` 在一个模块里是 `{ long v; }`，在另一个模块里是 `{ int v; }`，Clang 23 在访问成员 `v` 时报 "reference to 'v' is ambiguous" 并列出两个版本，没有静默地选一个。

附属于具名模块的 inline 函数，如果在某个定义域中声明，就必须在同一定义域中定义（[[dcl.inline#5]]）；类内定义的成员函数也不再隐式 inline。多数情况下这些函数只有一个定义，存放在 BMI 中，"各 TU 中的定义必须逐记号相同"的问题也就基本消失了。

## 常见问题

!!! pitfall "把 BMI 当作库接口分发"
    不可行。BMI 与编译器版本和编译选项绑定。分发模块接口的源码（`.cppm`），让使用者自己构建。

!!! pitfall "用 Makefile 生成器"
    CMake 的 Unix Makefiles 生成器不支持 C++ 模块，要用 Ninja 或 Visual Studio。

!!! pitfall "在接口单元中导入实现分区"
    Clang 对此给出 `-Wimport-implementation-partition-unit-in-interface-unit` 警告。实现分区对模块外的导入方不一定可达（[[module.reach#1]]），Clang 选择不把它视为可达。如果导入方需要其中的定义，把它改成接口分区。

## 小结

| 主题 | 要点 |
|---|---|
| BMI | Clang 的 `.pcm`，GCC 的 `gcm.cache/*.gcm`，MSVC 的 `.ifc`；绑定编译器版本与选项，不可分发 |
| Clang 的编译方式 | 两阶段：`--precompile` 后 `-c x.pcm`，得到完整 BMI；一阶段：`-fmodule-output`，Clang 23 默认得到 reduced BMI 并执行丢弃规则 |
| 查找 BMI | `-fmodule-file=名字=路径`、`-fprebuilt-module-path=目录` |
| 依赖扫描 | P1689 格式的 JSON；`clang-scan-deps -format=p1689` |
| CMake | 3.28 起，`FILE_SET CXX_MODULES` 加 Ninja；`import std;` 在较新版本中是实验特性 |
| 头文件单元 | Clang 实验性支持；CMake 不支持 |
| 符号修饰 | `W<模块名>` 标记附属，`WP` 标记分区（只出现在初始化函数中）；`extern "C++"` 中的声明没有 `W`；导出与否不影响符号名 |
