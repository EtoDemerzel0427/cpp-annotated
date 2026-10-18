---
title: 模块的工程实践
summary: 编译器如何实现 C++20 模块（BMI：Clang 的 .pcm、GCC 的 gcm.cache、MSVC 的 .ifc）；Clang 的两阶段与一阶段编译、完整 BMI 与 reduced BMI；P1689 依赖扫描；CMake 的 FILE_SET CXX_MODULES；import std；头文件单元的现状；模块附属在符号修饰中的体现（Itanium 的 W 修饰）；以及一个在本机实际跑通的完整例子。
status: draft
order: 30
related: module, module.unit, module.import, module.global.frag, module.reach, basic.link, basic.def.odr, lex.phases
tags: 模块, 构建
updated: 2026-10-18
---

标准对模块的描述是纯语义的：一个 TU "导入"另一组 TU，被导入 TU 中的声明变得"可达"或"可见"（[[module.import]]、[[module.reach]]）。标准**完全没有**提到文件、编译顺序、二进制接口文件——[[lex.phases]] 只说"依赖的模块单元和头文件单元的源码是否需要可用，由实现定义"。

但模块的语义是为一种特定实现方式量身定做的：**模块接口单元翻译一次，产出一个序列化的编译器内部表示，导入者直接读取它。**这带来了 `#include` 时代没有的工程问题：编译顺序、依赖发现、BMI 的兼容性。本页讲这些问题在各工具链中是怎么解决的。

本页所有命令、输出与数字都来自本机：Homebrew Clang 23.1（libc++，macOS arm64）、CMake 3.29、Ninja。GCC 与 MSVC 部分只描述机制，没有本机验证。

## BMI：二进制模块接口

编译一个模块接口单元（含接口分区、实现分区）时，编译器除了产生目标文件，还产生一个 **BMI**（Built Module Interface，也叫 CMI，Compiled Module Interface）。它本质上是编译器 AST 的序列化，导入者读取它而不是重新解析源码。

| 编译器 | BMI 形式 | 说明 |
|---|---|---|
| Clang | `.pcm` 文件 | 与 Clang 的预编译头（PCH）、Clang modules 共享序列化格式；需显式告知编译器每个 `.pcm` 在哪里 |
| GCC | `.gcm` 文件，默认放在当前目录下的 `gcm.cache/` 目录 | 用 `-fmodules`（旧版本中为 `-fmodules-ts`）开启；GCC 通过"模块映射器"（module mapper）协议把模块名映射到 `.gcm` 路径，默认映射是 `gcm.cache/<模块名>.gcm` |
| MSVC | `.ifc` 文件 | 格式有公开的规范文档（IFC 格式）；接口单元常用 `.ixx` 扩展名 |

BMI 的关键特性：

- **不可移植**：BMI 绑定于具体的编译器版本，以及影响语义的编译选项（语言标准、异常开关、某些宏……）。它不是可分发的"库接口文件"——库作者分发的仍然是模块接口**源码**，由使用者用自己的编译器和选项构建 BMI。
- **编译顺序约束**：导入者必须在被导入模块的 BMI 生成之后才能编译。这让原本"所有 `.cpp` 完全并行"的构建变成了一个 DAG。

Clang 会严格检查配置一致性。本机实验：用 `-std=c++23` 构建 `geo.pcm`，再用 `-std=c++20` 或 `-fno-exceptions` 编译导入者，分别得到：

```text
error: C++23 was enabled in precompiled file '.../geo.pcm' but is currently disabled
error: exception handling was enabled in precompiled file '.../geo.pcm' but is currently disabled
error: precompiled file '.../geo.pcm' cannot be loaded due to a configuration mismatch with the current compilation [-Wmodule-file-config-mismatch]
```

而只改优化级别（`-O2`）不影响 BMI 的使用。

## Clang 的编译模型

### 两阶段：`--precompile` 然后编译 BMI

```bash
clang++ -std=c++23 --precompile geo.cppm -o geo.pcm      # 第一阶段：源码 → BMI
clang++ -std=c++23 -c geo.pcm -o geo.o                    # 第二阶段：BMI → 目标文件
```

第一阶段只做前端（解析、语义分析），一旦 BMI 产出，依赖它的导入者就可以开始编译，而不必等待第二阶段的代码生成。这对构建并行度有好处：关键路径上只有前端时间。

### 一阶段：`-fmodule-output`

```bash
clang++ -std=c++23 -c geo.cppm -fmodule-output=geo.pcm -o geo.o
```

一次调用同时产出目标文件和 BMI。CMake 驱动 Clang 时用的就是这种方式（见下文）。

### 完整 BMI 与 reduced BMI

`--precompile` 产出的是**完整 BMI**，它保留了生成目标代码所需的一切（例如非 inline 函数体）。导入者其实不需要这些。**reduced BMI** 只保留导入者需要的部分，并实施 [[module.global.frag#3]] 的**丢弃**规则。

本机观察（Clang 23）：

- `-c x.cppm -fmodule-output=x.pcm` 默认就产出 reduced BMI——与显式加 `-fmodules-reduced-bmi` 的产物大小完全相同；加 `-fno-modules-reduced-bmi` 则产出与 `--precompile` 相同的完整 BMI。
- 下面例子中的 `geo.pcm`（全局模块片段中 `#include <cmath>`）：完整 BMI 922,948 字节，reduced BMI 365,412 字节。
- **语义差异**：[[module.global.frag#5]] 的标准例子中，`use_g<int>()` 应因 `N::g` 被丢弃而失败。用完整 BMI 时 Clang 接受它；用 reduced BMI 时 Clang 正确地报错。也就是说，**构建方式会改变 Clang 对同一程序是否良构的判断**——依赖未被丢弃的全局模块片段声明的代码，换一种构建方式可能就编译不过。

### 告诉编译器 BMI 在哪里

Clang 不会自动寻找 BMI，需要显式指定：

| 选项 | 含义 |
|---|---|
| `-fmodule-file=<模块名>=<路径>` | 指定某个模块（或分区，如 `geo:shapes`）的 BMI 路径 |
| `-fprebuilt-module-path=<目录>` | 在目录中按 `<模块名>.pcm` 查找；分区 `M:P` 对应 `M-P.pcm` |
| `-fmodule-file=<路径>` | 不带名字的形式，用于头文件单元的 BMI |

`.cppm`（或 `.ccm`、`.cxxm`、`.c++m`）扩展名告诉 Clang 这是模块接口单元；其他扩展名需要 `-x c++-module`。

## 完整的本地例子

一个带接口分区、实现单元，并使用 `import std;` 的小模块。

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

两阶段构建（本机实际执行的命令，按依赖顺序）：

```bash
LIBCXX=/opt/homebrew/opt/llvm/share/libc++/v1
# 标准库模块（每个工具链配置构建一次）
clang++ -std=c++23 -Wno-reserved-module-identifier --precompile $LIBCXX/std.cppm -o std.pcm
# 先分区，后主接口
clang++ -std=c++23 --precompile shapes.cppm -o geo-shapes.pcm
clang++ -std=c++23 --precompile geo.cppm -fmodule-file=geo:shapes=geo-shapes.pcm -o geo.pcm
# BMI → 目标文件
clang++ -std=c++23 -c geo-shapes.pcm -o geo-shapes.o
clang++ -std=c++23 -c geo.pcm -fmodule-file=geo:shapes=geo-shapes.pcm -o geo.o
clang++ -std=c++23 -c std.pcm -o std.o
# 实现单元与导入者
clang++ -std=c++23 -c geo.cpp -fmodule-file=geo=geo.pcm -fmodule-file=geo:shapes=geo-shapes.pcm -o geo-impl.o
clang++ -std=c++23 -c main.cpp -fprebuilt-module-path=. -o main.o
# 链接
clang++ main.o geo.o geo-shapes.o geo-impl.o std.o -o app
./app          # 输出：area = 12.566
```

几点说明：

- `-Wno-reserved-module-identifier`：`std` 是保留模块名（[[module.unit#1]]），Clang 对 `export module std;` 给出警告。
- 第二阶段编译 `geo.pcm` 时仍需指明 `geo:shapes` 的位置——BMI 记录了依赖，但不记录依赖的路径。
- `main.cpp` 用 `-fprebuilt-module-path=.`，Clang 自动找 `std.pcm` 和 `geo.pcm`，再由 `geo.pcm` 中记录的模块名找 `geo-shapes.pcm`。
- 本机测得构建 `std.pcm` 约 1 秒，产物约 37 MB。

一阶段构建：

```bash
clang++ -std=c++23 -c shapes.cppm -fmodule-output=geo-shapes.pcm -o geo-shapes.o
clang++ -std=c++23 -c geo.cppm -fmodule-file=geo:shapes=geo-shapes.pcm -fmodule-output=geo.pcm -o geo.o
clang++ -std=c++23 -c geo.cpp -fprebuilt-module-path=. -o geo-impl.o
clang++ -std=c++23 -c main.cpp -fprebuilt-module-path=. -fmodule-file=std=std.pcm -o main.o
clang++ main.o geo.o geo-shapes.o geo-impl.o std.o -o app
```

### 编译时间：一个小测量

用 `import std;` 的程序（vector + ranges::sort + println）与用 `#include <vector>`、`<algorithm>`、`<print>` 的等价程序，各编译三次（`-c`，`-O0`）：前者约 0.30 s，后者约 0.53 s。这还没有计入"`std.pcm` 只需构建一次"的摊销效果——项目越大、每个 TU 包含的标准头越多，差距越明显。这只是一个本机数据点，不是基准测试。

## 符号修饰：模块附属在 ABI 中的体现

[[basic.link#8]] 规定附属于不同模块的同名实体是**不同实体**；[[module.unit#7]] 规定了附属规则。Itanium C++ ABI（Clang、GCC 在非 Windows 平台使用）用 `W` 前缀把模块名编码进修饰名。上例的 `nm` 输出（Mach-O 符号带一个额外的前导 `_`）：

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

解读：

- `_ZN3geoW3geo2piEv`：`N 3geo` 是命名空间 `geo`，`W3geo` 是**模块** `geo`，然后是 `2pi`。`llvm-cxxfilt` 解码为 `geo::pi@geo()`。命名空间与模块同名纯属巧合，二者在修饰中位于不同位置。
- `geo::pi` 未导出（模块链接），`geo::area` 导出（外部链接），但**两者都带 `W3geo`**：修饰名反映的是**附属**，不是链接。模块链接的实体在目标文件里仍然是全局符号（`T`），链接器并不知道"模块链接"的存在——是修饰名中的模块名保证了别的模块无法意外地链接到它。
- `geo::area` 在**分区** `:shapes` 中声明，但修饰名里没有分区名——与 [[module.unit#3]] Note 1"模块划分为哪些单元对外不可见"一致。分区名只出现在模块初始化函数的符号中：`_ZGIW3geoWP6shapes`（`GI` = 模块初始化器，`WP` = 分区）。
- `_ZGIW3geo` 是模块 `geo` 的**初始化函数**。导入者的初始化代码会调用它，以保证被导入模块中的动态初始化先于导入者执行。
- 带点的模块名逐段编码：`export module a.b;` 中的 `f()` 修饰为 `_ZW1aW1b1fv`。
- `extern "C++"` 块中的声明附属于全局模块（[[module.unit#7]] ¶7.2.4），修饰名中**没有** `W`：在模块 M 中 `extern "C++" int f3();` 修饰为 `_Z2f3v`，与在普通头文件中声明完全相同。这是渐进迁移时保持 ABI 不变的手段。

### 两个模块的同名实体互不冲突

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

本机链接成功，返回 33。两个 `helper` 修饰为 `_ZW1A6helperv` 和 `_ZW1B6helperv`，两个导出的 `f` 也分属 `_ZW1A1fv` 和 `_ZW1B1fv`。在头文件世界里，这是一次 ODR 违规（IFNDR，链接器可能报重复符号，也可能静默选一个）。但若在**同一个 TU** 中同时 `import A; import B;` 并调用 `f()`，两个 `f` 都可见，调用有歧义——Clang 23 报 "declaration 'f' attached to named module 'A' cannot be attached to other modules"。

### 类内定义的成员函数不再是 inline

[[class.mfct#1]]：只有附属于全局模块的类的类内定义成员函数才隐式 inline。用 `nm -m` 观察：

```text
W.o（export module W; export struct S { int get() {...} inline int iget() {...} };）:
  (__TEXT,__text) external      __ZNW1W1S3getEv     ← 强定义
  (__TEXT,__text) weak external __ZNW1W1S4igetEv    ← 显式 inline，弱定义
g.o（普通 TU 中的 struct G { int get() {...} };）:
  (__TEXT,__text) weak external __ZN1G3getEv        ← 隐式 inline，弱定义
```

导入 W 的 TU 调用 `s.get()` 时生成对 `__ZNW1W1S3getEv` 的外部引用（`U`），而不是内联展开。修改 `get` 的函数体不改变 W 的 ABI。

### GCC 与 MSVC

- GCC 在 Itanium 平台上同样使用 `W` 前缀的模块修饰（本机未验证）。
- MSVC 使用自己的修饰与链接方案，模块附属信息的记录方式不同（本页不展开）。

## 依赖扫描：P1689

`#include` 时代，构建系统不需要知道文件之间的依赖就能开始编译——依赖（头文件）是编译**之后**由 `-MD` 报告的，只用于增量构建。模块改变了这一点：编译 `main.cpp` **之前**就必须知道它导入了 `geo`，并且 `geo.pcm` 已经生成。

解决办法是在编译之前做一次**依赖扫描**：轻量地预处理每个源文件，找出它**提供**哪个模块、**需要**哪些模块。[[P1857R3]] 把 `module`/`import` 行变成预处理指令，正是为了让这种扫描可以只做预处理而不做 C++ 解析。扫描结果的格式由 WG21 文档 P1689（"Format for describing dependencies of source files"）规定，是一个 JSON 格式；Clang（`clang-scan-deps -format=p1689`）、GCC 与 MSVC 也提供输出这种格式的选项（本机未验证其细节）。

本机对上例的扫描结果：

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

`main.cpp` 的扫描结果没有 `provides`，`requires` 为 `std` 和 `geo`。构建系统汇总所有扫描结果，建立"模块名 → 提供它的源文件 → BMI 路径"的映射，生成编译顺序，并为每个 TU 生成对应的 `-fmodule-file=` 参数。

扫描也是发现 [[module.unit#2]]（两个主接口单元，IFNDR）和 [[module.import#10]]（循环依赖）的地方——编译器单独编译一个 TU 时看不到这些。

## CMake

CMake 3.28 起正式支持 C++20 具名模块（需要 Ninja 或 Visual Studio 生成器；Makefile 生成器不支持）。模块接口源文件放进 `CXX_MODULES` 类型的 **file set**：

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

本机 `cmake -G Ninja -DCMAKE_CXX_COMPILER=/opt/homebrew/opt/llvm/bin/clang++` 后构建，`ninja -v` 显示的步骤：

1. 对每个源文件（包括 `main.cpp` 和实现单元 `greet.cpp`）运行 `clang-scan-deps -format=p1689`，输出 `.ddi` 文件；
2. `cmake -E cmake_ninja_dyndep` 汇总 `.ddi`，生成 Ninja 的**动态依赖**（dyndep）文件和每个 TU 的 `.modmap` 响应文件；
3. 按依赖顺序编译，每条命令通过 `@xxx.o.modmap` 引用参数。`greet.cppm` 的 modmap 内容是：

    ```text
    -x c++-module
    -fmodule-output=CMakeFiles/greet.dir/greet.pcm
    -fmodule-file=greet:fmt=CMakeFiles/greet.dir/greet-fmt.pcm
    ```

   即 CMake 用的是 Clang 的**一阶段**编译（于是默认产出 reduced BMI）。

要点：

- 实现单元（`module greet;`）不放进 `CXX_MODULES` file set，它只是普通源文件——但它仍然会被扫描。
- `PUBLIC` 的 `CXX_MODULES` file set 让依赖 `greet` 的目标能导入它。由于 BMI 不能跨编译配置复用，库对外提供的应当是模块接口源码，而不是 BMI。
- 两个源文件都写 `export module M;` 时，本机 Ninja 报 `multiple rules generate CMakeFiles/dup.dir/M.pcm` 并停止。

### `import std;` 与 CMake

本机的 CMake 3.29 不支持自动构建标准库模块。较新的 CMake 版本以**实验特性**的形式提供 `import std;` 支持（目标属性 `CXX_MODULE_STD`，并需要设置一个随 CMake 版本变化的实验开关 UUID）。具体用法以所用 CMake 版本的文档为准，本页未在本机验证。手动做法就是上面的命令：自己从 `std.cppm` 构建 `std.pcm` 并加入编译。

## 头文件单元的现状

[[module.import#5]] 的头文件单元（`import <vector>;`、`import "config.h";`）是标准中实现最弱的部分：

- **Clang**：支持，`-fmodule-header=user|system` 配合 `-xc++-header`/`-xc++-system-header` 构建头文件单元的 BMI，再用不带名字的 `-fmodule-file=<路径>` 导入。本机可用（导入宏也正常工作），但每次导入都有警告 "the implementation of header units is in an experimental phase"。
- **CMake**：不支持头文件单元（本机 3.29 的 `CXX_MODULES` file set 只处理具名模块）。
- 难点在于构建系统：头文件单元有独立的宏环境（[[module.import#5]] Note 2），同一个头文件在不同编译选项下可能需要不同的 BMI；[[module.import#5]] ¶5.3 对"两个 TU 中的 `import "x.h"` 是否同一个头文件单元"未指明，正是为这种不确定性留余地。
- MSVC 支持把可导入头文件的 `#include` 自动翻译为 `import`（[[cpp.include#10]] 允许的实现定义行为）。

实践建议：具名模块 + `import std;` 是当前最成熟的组合；对第三方头文件，放进全局模块片段 `#include`。

## ODR 与模块：实践中的变化

- **模块链接实体**：附属于不同模块的同名实体是不同实体，修饰名不同——"两个库都有 `detail::helper`"不再是问题（前提是它们都在具名模块中）。
- **全局模块实体仍然共享**：全局模块片段中 `#include` 进来的东西附属于全局模块，跨 TU 的 ODR 一致性要求与头文件时代相同。不同模块用不同的宏配置包含同一头文件，仍是 IFNDR。区别在于：同时导入这些模块时，编译器会在合并 BMI 时比对定义，有机会报错。本机实验（同一个 `struct Cfg` 在一个模块中是 `{ long v; }`，另一个中是 `{ int v; }`）：Clang 23 在访问成员 `v` 时报 "reference to 'v' is ambiguous"，并列出两个版本——没有静默选一个。
- **inline 与模板**：附属于具名模块的 inline 函数必须在同一定义域中定义（[[dcl.inline#5]]），类内成员函数不再隐式 inline——这让"inline 函数在多个 TU 中的定义必须逐记号相同"的问题大多消失：它们只有一个定义，存在 BMI 中。

## 常见问题

!!! pitfall "BMI 当作库接口分发"
    不行。BMI 与编译器版本、编译选项绑定。分发模块接口的**源码**（`.cppm`），让使用者构建。

!!! pitfall "Makefile 生成器"
    CMake 的 Unix Makefiles 生成器不支持 C++ 模块，需要 Ninja（或 Visual Studio）。

!!! pitfall "Clang 的实现分区警告"
    在接口单元中 `import` 实现分区时，Clang 给出 `-Wimport-implementation-partition-unit-in-interface-unit`：实现分区对外不是必然可达的（[[module.reach#1]]），Clang 选择不把它视为可达。若导入者需要其中的定义，改为接口分区。

## 小结

| 主题 | 要点 |
|---|---|
| BMI | `.pcm`（Clang）/ `gcm.cache/*.gcm`（GCC）/ `.ifc`（MSVC）；绑定编译器版本与选项，不可分发 |
| Clang 编译 | 两阶段 `--precompile` + `-c x.pcm`（完整 BMI）；一阶段 `-fmodule-output`（Clang 23 默认 reduced BMI，实施丢弃） |
| 查找 BMI | `-fmodule-file=名字=路径`、`-fprebuilt-module-path=目录` |
| 依赖扫描 | P1689 JSON；`clang-scan-deps -format=p1689` |
| CMake | ≥3.28，`FILE_SET CXX_MODULES`，Ninja；`import std` 在更新的版本中为实验特性 |
| 头文件单元 | Clang 实验性支持；CMake 不支持 |
| 修饰 | Itanium `W<模块名>` 标记附属，`WP` 标记分区（仅初始化器）；`extern "C++"` 无 `W`；导出与否不影响修饰 |
