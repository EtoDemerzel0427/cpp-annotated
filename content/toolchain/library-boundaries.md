---
title: 库边界：静态库、动态库与 ABI
summary: 一个 C++ 库的边界由什么组成：静态库和动态库里各有什么，用可见性控制导出哪些符号，哪些改动会在不改符号名的情况下破坏二进制兼容，C 接口为什么是最稳定的边界，异常和 RTTI 怎样跨越动态库，谁分配谁释放，以及 install name、soname 和内联命名空间怎样管理版本。
group: 工程实践
status: draft
order: 110
since: c++98
related: basic.def.odr, basic.link, dcl.link, dcl.fct.default, namespace.def, dcl.meaning.general, except.handle, type.info, expr.delete, dcl.fct.def.replace, lex.phases, toolchain/linking-and-symbols, toolchain/name-mangling, toolchain/object-layout-and-vtables, toolchain/exception-implementation, toolchain/dependencies, patterns/pimpl
tags: 工具链, 库, 动态库, 静态库, ABI, 可见性, 符号, 版本
updated: 2026-10-19
---

!!! tldr
    - 库的边界不只是头文件里的声明。调用方的二进制里还固化了类的大小、虚函数的槽位、inline 函数体、默认实参和异常类型的身份，这些都属于 ABI。
    - 动态库默认导出所有外部链接的符号。用 `-fvisibility=hidden` 加一个导出宏，只导出公开接口；本机例子从 15 个导出符号降到 4 个。
    - 很多破坏 ABI 的改动不改变任何符号名，链接和加载都成功，运行结果却是错的。本机交换两个虚函数的声明顺序后，旧程序调用 `width()` 得到的是 `height()` 的值。
    - 最稳定的边界是 C 接口：`extern "C"` 函数、不透明句柄、错误码，库自己负责分配和释放。异常、`std::` 类型和类布局都不跨过这条线。
    - 版本靠三样东西管理：动态库的 install name 或 soname 区分不兼容的大版本，内联命名空间让不兼容的改动变成链接或加载错误，导出符号表只增不改。

一个库的**边界**是调用方编译好的代码依赖它的全部内容。头文件里的声明只是其中能看见的部分。调用方编译时，编译器还把类的大小、成员偏移、虚函数在 vtable 中的位置、inline 函数的函数体和默认实参的值直接编进了调用方的机器码。这些二进制层面的约定统称 **ABI**（application binary interface）。库换了一个版本而调用方没有重新编译，两边对这些约定的理解就必须一致。

标准里没有库的概念。翻译阶段 8（[[lex.phases#1]]）只说各个翻译单元（TU）和库组件合在一起构成程序。静态库、动态库、可见性、版本号都是实现提供的机制。所以本页的规则大多不是标准规则，但每一条背后都有标准规则在起作用：ODR（[[basic.def.odr]]）、语言链接（[[dcl.link]]）、异常匹配（[[except.handle]]）。

目标文件、符号表和链接器的基本行为见 [[toolchain/linking-and-symbols]]，符号名的编码见 [[toolchain/name-mangling]]。

!!! note "实验环境"
    本机为 Apple M2 Pro、macOS 26.5，Homebrew Clang 23.1.3，头文件来自 Homebrew 的 libc++，运行时链接系统的 `/usr/lib/libc++.1.dylib`。链接器是系统的 `ld-1266.8`，命令中用 `--ld-path=/usr/bin/ld` 指定；`nm`、`otool` 也是 `/usr/bin` 下的 Apple 版本。本机没有 GCC、libstdc++ 和能链接 ELF 共享库的链接器，涉及 Linux 的部分都注明据文档。

## 静态库和动态库里有什么

下面是一个小的几何库。头文件声明公开接口，两个 `.cpp` 实现它，其中 `detail::cross` 是内部函数：

```cpp title="geo.h"
#pragma once
#include <string>
#include <vector>

#if defined(GEO_BUILD)
#  define GEO_API __attribute__((visibility("default")))
#else
#  define GEO_API
#endif

namespace geo {
struct GEO_API Point { double x, y; };

class GEO_API Polygon {
public:
  void add(Point p);
  double area() const;
  std::string describe() const;
  std::size_t size() const { return pts_.size(); }   // inline
private:
  std::vector<Point> pts_;
};

template <class T> T sq(T v) { return v * v; }        // 模板
GEO_API double distance(Point a, Point b);
}
```

```cpp title="polygon.cpp"
#include "geo.h"
#include <cmath>
#include <cstdio>
namespace geo {
namespace detail {
double cross(Point a, Point b) { return a.x * b.y - a.y * b.x; }   // 内部函数
}
void Polygon::add(Point p) { pts_.push_back(p); }
double Polygon::area() const {
  double s = 0;
  for (std::size_t i = 0; i < pts_.size(); ++i)
    s += detail::cross(pts_[i], pts_[(i + 1) % pts_.size()]);
  return std::fabs(s) / 2;
}
std::string Polygon::describe() const {
  char buf[64];
  std::snprintf(buf, sizeof buf, "polygon(%zu), area %.1f", size(), area());
  return buf;
}
}
```

```cpp title="distance.cpp"
#include "geo.h"
#include <cmath>
namespace geo {
double distance(Point a, Point b) { return std::sqrt(sq(a.x - b.x) + sq(a.y - b.y)); }
}
```

```cpp title="app.cpp" ok
#include "geo.h"
#include <cstdio>
int main() {
  geo::Polygon p;
  p.add({0, 0}); p.add({4, 0}); p.add({4, 3});
  std::printf("%s, d=%.1f\n", p.describe().c_str(), geo::distance({0, 0}, {4, 3}));
}
```

### 静态库

**静态库**（`.a`）是目标文件的归档。链接时，链接器从中提取需要的成员，把它们的代码复制进可执行文件（提取规则见 [[toolchain/linking-and-symbols]]）：

```text
$ clang++ -std=c++2c -O2 -c polygon.cpp distance.cpp
$ llvm-ar rcs libgeo.a polygon.o distance.o && llvm-ar t libgeo.a
polygon.o
distance.o
$ clang++ -O2 app.cpp -L. -lgeo -o app_static && ./app_static
polygon(3), area 6.0, d=5.0
$ otool -L app_static
app_static:
	/usr/lib/libc++.1.dylib (compatibility version 1.0.0, current version 2100.43.0)
	/usr/lib/libSystem.B.dylib (compatibility version 1.0.0, current version 1356.0.0)
```

可执行文件不再依赖 `libgeo`，库的代码已经在里面了。库升级时，调用方必须重新链接才能用上新代码；反过来说，旧的可执行文件永远不会遇到新版本的库，ABI 问题只在同一次链接的各个目标文件之间出现。

### 动态库

**动态库**（macOS 上是 `.dylib`，Linux 上是 `.so`）是一个已经链接好的映像。可执行文件只记录要用哪个库、要从中取哪些符号，加载时由动态加载器（macOS 是 `dyld`，Linux 是 `ld.so`）把它们接上：

```text
$ clang++ -std=c++2c -O2 -DGEO_BUILD -fvisibility=hidden -shared polygon.cpp distance.cpp \
    -install_name @rpath/libgeo.dylib -o libgeo.dylib
$ clang++ -O2 app.cpp -L. -lgeo -Wl,-rpath,@loader_path -o app_dyn && ./app_dyn
polygon(3), area 6.0, d=5.0
$ otool -L app_dyn
app_dyn:
	@rpath/libgeo.dylib (compatibility version 0.0.0, current version 0.0.0)
	/usr/lib/libc++.1.dylib (compatibility version 1.0.0, current version 2100.43.0)
	/usr/lib/libSystem.B.dylib (compatibility version 1.0.0, current version 1356.0.0)
$ nm -u app_dyn | c++filt | grep geo
geo::Polygon::add(geo::Point)
geo::distance(geo::Point, geo::Point)
geo::Polygon::describe() const
```

`otool -L` 列出可执行文件依赖的动态库，第一行的 `@rpath/libgeo.dylib` 来自库的 install name，后文讲版本时再说。`nm -u` 列出未定义的符号，也就是 `app_dyn` 运行时要向 `libgeo` 要的三个函数。

库可以单独替换，调用方不必重新链接。这是动态库的主要用途，也是 ABI 问题的来源：替换上来的库必须符合调用方编译时的全部假设。

| | 静态库 `.a` | 动态库 `.dylib` / `.so` |
|---|---|---|
| 库的代码在哪里 | 复制进每个使用它的映像 | 只有一份，加载时共享 |
| 升级 | 调用方重新链接 | 替换文件即可，前提是 ABI 兼容 |
| 符号可见性 | 只影响打包成动态库之后的导出 | 决定哪些符号能被其他映像使用 |
| 全局状态 | 每个链接了它的映像各有一份 | 一份 |
| ABI 错误在哪里出现 | 同一次链接的目标文件之间 | 调用方和任何一个版本的库之间 |

### 一个静态库，两份状态

表中"每个链接了它的映像各有一份"常被忽略。下面的 `registry.cpp` 打成静态库，再被两个动态库分别链接：

```cpp title="registry.cpp"
int& instance_count() { static int n = 0; return n; }
```

```cpp title="a.cpp（b.cpp 只把 a_register 换成 b_register）"
int& instance_count();
__attribute__((visibility("default"))) int a_register() { return ++instance_count(); }
```

```cpp title="app.cpp" ifndr
#include <cstdio>
int a_register();
int b_register();
int main() {
  a_register(); a_register();
  std::printf("a sees %d, b sees %d\n", a_register(), b_register());
}
```

```text
$ clang++ -std=c++2c -O2 -c registry.cpp && llvm-ar rcs libregistry.a registry.o
$ clang++ -O2 -shared a.cpp libregistry.a -install_name @rpath/liba.dylib -o liba.dylib
$ clang++ -O2 -shared b.cpp libregistry.a -install_name @rpath/libb.dylib -o libb.dylib
$ clang++ -O2 app.cpp -L. -la -lb -Wl,-rpath,@executable_path -o app && ./app
a sees 3, b sees 1
```

两个动态库各自带了一份 `instance_count()` 和其中的静态局部变量 `n`。本机无论 `registry.cpp` 用默认可见性还是 `-fvisibility=hidden` 编译，结果都一样：macOS 的两级命名空间让每个动态库在构建时就绑定到自己的那一份（见 [[toolchain/linking-and-symbols]]）。在 ELF 平台上，默认可见性的符号可以被插入，两个库的调用通常会解析到同一份（据文档，本机未验证）。

按标准，`instance_count` 是非 inline 函数，程序里有两个定义，违反 [[basic.def.odr#16]]，属于 {{ifndr}}（程序不合法，但实现不必诊断）。实践中的规则是：有全局状态的静态库只能链接进一个最终映像；需要被多个动态库共用时，它自己就应该是动态库。

## 导出什么：符号可见性

### 默认全部导出

不加任何选项构建动态库，所有外部链接的符号都会导出，包括内部函数、inline 函数和模板实例化。`nm -gU` 列出已定义的全局符号：

```text
$ clang++ -std=c++2c -O0 -shared polygon.cpp distance.cpp -o libgeo_def.dylib
$ nm -gU libgeo_def.dylib | c++filt | cut -c 20-
double geo::sq<double>(double)
geo::detail::cross(geo::Point, geo::Point)
geo::Polygon::add(geo::Point)
geo::distance(geo::Point, geo::Point)
geo::Polygon::area() const
geo::Polygon::size() const
geo::Polygon::describe() const
std::__1::allocation_result<...> std::__1::allocator_traits<...>::allocate_at_least[abi:nqe230103]<...>(...)
geo::Point& std::__1::vector<geo::Point, ...>::emplace_back[abi:nqe230103]<geo::Point const&>(geo::Point const&)
...（共 15 个）
```

（输出中的 `std::` 部分为排版做了省略。）

`detail::cross` 被导出了，调用方可以声明并调用它，它从此成了 ABI 的一部分，库作者再也不能随意改它的签名。`Polygon::size()` 和 `sq<double>` 是头文件里的 inline 函数和模板，`-O0` 下没有被内联，各自生成了一份弱定义，也被导出。还有 8 个 `std::vector<geo::Point>` 的成员模板实例化，它们来自 libc++ 的头文件，库作者从未打算提供它们。

这些多余的导出有三个代价：调用方可能依赖本该是内部实现的东西；动态加载器要处理更大的符号表；不同库之间同名的弱定义会被合并（后文有一个例子）。

### `-fvisibility=hidden` 加导出宏

`-fvisibility=hidden` 把默认可见性改为隐藏，再用 `__attribute__((visibility("default")))` 显式标出要导出的实体。通常把它包装成一个宏，构建库时展开为导出属性，使用库时展开为空，即 `geo.h` 开头的 `GEO_API`：

```text
$ clang++ -std=c++2c -O0 -DGEO_BUILD -fvisibility=hidden -shared polygon.cpp distance.cpp -o h0.dylib
$ nm -gU h0.dylib | c++filt | cut -c 20-
geo::Polygon::add(geo::Point)
geo::distance(geo::Point, geo::Point)
geo::Polygon::area() const
geo::Polygon::size() const
geo::Polygon::describe() const
```

`GEO_API` 写在类上时，类的所有成员函数、vtable 和 typeinfo 都导出，所以 inline 的 `size()` 仍在其中。再加上 `-fvisibility-inlines-hidden`，inline 成员函数也隐藏：

| 本机构建方式 | `-O0` 导出数 | `-O2` 导出数 |
|---|---|---|
| 默认 | 15 | 5（`size`、`sq`、`std::vector` 的实例化都被内联掉了，`detail::cross` 仍在） |
| `-fvisibility-inlines-hidden` | 6（`detail::cross` 和 `sq<double>` 仍在） | |
| `-fvisibility=hidden` + `GEO_API` | 5 | 4 |
| 上一行再加 `-fvisibility-inlines-hidden` | 4 | 4 |

两点值得注意。第一，`-O2` 下导出数变少只是因为函数被内联了，换一个优化级别或编译器版本就会变；只有可见性设置能稳定地决定导出什么。第二，`-fvisibility-inlines-hidden` 不影响非 inline 的函数模板实例化，`sq<double>` 仍然导出。

!!! tip "推荐的做法"
    库的所有 TU 都用 `-fvisibility=hidden -fvisibility-inlines-hidden` 编译，公开接口用导出宏逐个标出。这样导出表就是一份显式的清单，加一个导出符号需要改代码，评审时看得见。CMake 的 `CXX_VISIBILITY_PRESET` 和 `GenerateExportHeader` 正是为此提供的，见 [[toolchain/cmake|CMake]]。

导出宏在 Windows 上更加必要。MSVC 的 DLL 默认什么都不导出，导出要写 `__declspec(dllexport)`，使用方还应写 `__declspec(dllimport)`，所以宏必须在构建库和使用库时展开成不同的东西（据 MSVC 文档）。

也可以不改源码，在链接时用一张清单限定导出。macOS 的 `ld` 接受 `-exported_symbols_list`，清单里是修饰后的名字，可以用通配符：

```text
$ cat exports.txt
__ZN3geo7Polygon*
__ZNK3geo7Polygon*
__ZN3geo8distance*
$ clang++ -std=c++2c -O0 -shared polygon.cpp distance.cpp -Wl,-exported_symbols_list,exports.txt -o le.dylib
$ nm -gU le.dylib | c++filt | cut -c 20-
geo::Polygon::add(geo::Point)
geo::distance(geo::Point, geo::Point)
geo::Polygon::area() const
geo::Polygon::size() const
geo::Polygon::describe() const
```

GNU ld 和 lld 的对应机制是版本脚本（`--version-script`），它还能给符号加版本标签，glibc 就用它让同一个函数的新旧实现并存（据文档）。清单的缺点是编译器不知道哪些符号最终会隐藏，不能据此优化；可见性属性在编译时就生效。

### 可见性只管动态库的边界

隐藏可见性的符号在一次链接之内照常使用。把同一个库用 `-fvisibility=hidden` 编译、不定义 `GEO_BUILD`（所以什么都不导出），打成静态库，`app.cpp` 照样能链接：

```text
$ nm -m libh.a | c++filt | grep 'geo::distance'
0000000000000000 (__TEXT,__text) private external geo::distance(geo::Point, geo::Point)
$ clang++ -O2 app.cpp libh.a -o a2 && ./a2
polygon(3), area 6.0, d=5.0
$ nm -m a2 | c++filt | grep 'geo::distance'
0000000100000bbc (__TEXT,__text) non-external (was a private external) geo::distance(geo::Point, geo::Point)
```

`private external` 是 Mach-O 对隐藏可见性的叫法，链接成映像之后变成 `non-external`。隐藏可见性相当于标准中不存在的第三种链接：在一个映像之内是外部链接，出了映像就不可见（见 [[toolchain/linking-and-symbols]]）。

## 什么改动会破坏 ABI

### 一次真实的二进制破坏

数据成员变化导致对象大小不一致的例子见 [[patterns/pimpl]]。下面看另一种更隐蔽的情况：库的 v2 只是调整了两个虚函数的声明顺序。

<div class="compare" markdown="1">

```cpp title="v1/shape.h"
#pragma once
struct Shape {
  virtual ~Shape();
  virtual int width() const;
  virtual int height() const;
};
Shape* make_shape();
```

```cpp title="v2/shape.h"
#pragma once
struct Shape {
  virtual ~Shape();
  virtual int height() const;  // 换了顺序
  virtual int width() const;
};
Shape* make_shape();
```

</div>

```cpp title="shape.cpp（两个版本相同）"
#include "shape.h"
Shape::~Shape() = default;
int Shape::width() const { return 20; }
int Shape::height() const { return 10; }
Shape* make_shape() { return new Shape; }
```

```cpp title="app.cpp" ifndr
#include <cstdio>
#include "shape.h"
int main() {
  Shape* s = make_shape();
  std::printf("width=%d height=%d\n", s->width(), s->height());
  delete s;
}
```

`app.cpp` 按 v1 的头文件编译并链接 v1 的库，然后只把 `lib/libshape.dylib` 换成 v2：

```text
$ ./app
width=20 height=10
$ rm lib/libshape.dylib && cp v2/libshape.dylib lib/
$ ./app
width=10 height=20
```

没有任何错误。两个版本的库导出完全相同的 9 个符号（`make_shape`、三个析构函数变体、`width`、`height`、vtable、typeinfo 和 typeinfo 名字），动态加载器找到了它要的每一个符号。问题在调用方的机器码里：

```text
$ llvm-objdump -d --no-show-raw-insn app      # main 中的两次虚调用，节选
ldr  x8, [x0]           ; 读 vptr
ldr  x8, [x8, #0x10]    ; vtable 第 2 个槽：v1 中是 width
blr  x8
...
ldr  x8, [x19]
ldr  x8, [x8, #0x18]    ; vtable 第 3 个槽：v1 中是 height
blr  x8
```

虚调用编译成按固定偏移读 vtable 槽位（槽位怎样排列见 [[toolchain/object-layout-and-vtables]]）。v2 的 vtable 中，偏移 `0x10` 处放的是 `height`，所以旧程序调用 `width()` 拿到 10。换了位置的如果是参数类型不同的两个虚函数，结果就不是值错了，而是按错误的约定传参，通常直接崩溃。

在标准看来，这个程序里 `Shape` 有两个不同的定义，违反 [[basic.def.odr#16]] 第 4 项（每个定义由相同的记号序列组成），属于 {{ifndr}}。链接器和加载器只比较符号名，所以看不出来。

### 改了 inline 函数体和默认实参

另一类改动不破坏布局，却让调用方继续使用旧的行为：

<div class="compare" markdown="1">

```cpp title="v1/net.h"
#pragma once
inline int max_retries() { return 3; }
int connect(int timeout_ms = 1000);
int lib_max_retries();
```

```cpp title="v2/net.h"
#pragma once
inline int max_retries() { return 5; }
int connect(int timeout_ms = 5000);
int lib_max_retries();
```

</div>

```cpp title="net.cpp"
#include "net.h"
int connect(int timeout_ms) { return timeout_ms; }
int lib_max_retries() { return max_retries(); }
```

```cpp title="app.cpp"
#include <cstdio>
#include "net.h"
int main() {
  std::printf("timeout=%d retries app=%d lib=%d\n",
              connect(), max_retries(), lib_max_retries());
}
```

`app` 按 v1 编译，运行时换上 v2 的库。本机几种优化级别组合的结果：

| `app` | 库 | 输出 |
|---|---|---|
| `-O2`，v1 库 | `-O2` | `timeout=1000 retries app=3 lib=3` |
| `-O2` | 换成 v2，`-O2` | `timeout=1000 retries app=3 lib=5` |
| `-O0` | 换成 v2，`-O2` | `timeout=1000 retries app=3 lib=5` |
| `-O0` | 换成 v2，`-O0` | `timeout=1000 retries app=3 lib=3` |

默认实参是在调用处求值的（[[dcl.fct.default#1]]、[[dcl.fct.default#9]]）：`connect()` 被编译成 `connect(1000)`，值写在调用方的机器码里。库换成 v2 也改变不了它。这不违反任何规则，[[dcl.fct.default#4]] 只要求 inline 函数在各个 TU 中的默认实参相同，非 inline 函数的默认实参本来就可以在各个 TU 中不同。所以改默认值是一个源码兼容、二进制上不生效的改动，旧程序要重新编译才能得到新值。

`max_retries()` 的两个定义不同，违反 [[basic.def.odr#16]]，是 {{ifndr}}。最后一行最能说明问题：两边都是 `-O0` 时，`app` 和库都导出了弱定义 `max_retries()`，`dyld` 在加载时把它们合并成一个，库里的调用也用了 `app` 中的 v1 版本。一个程序同时链接同一个库的两个版本时的同类问题见 [[toolchain/dependencies|依赖管理]]。

### 改动分类

下表按调用方是否需要重新编译来分类。"兼容"指旧的调用方不重新编译、换上新库后行为正确。

| 改动 | 结果 | 原因 |
|---|---|---|
| 新增非虚、非 inline 的自由函数或成员函数 | 兼容 | 只增加导出符号 |
| 新增重载 | 兼容 | 修饰名不同，旧符号仍在 |
| 修改非 inline 函数的实现 | 兼容 | 只有库里的代码变了 |
| 删除或重命名导出函数，修改形参类型 | 加载时失败 | 修饰名变了，旧符号找不到 |
| 修改非模板函数的返回类型 | 静默破坏 | 修饰名不含返回类型（[[toolchain/name-mangling]]） |
| 增删、重排数据成员，修改成员类型 | 静默破坏 | 调用方按旧的大小和偏移分配、访问对象，见 [[patterns/pimpl]] |
| 增删、重排虚函数，新增基类 | 静默破坏 | vtable 槽位和基类偏移变了 |
| 在最后追加一个虚函数 | 调用方派生了这个类时破坏 | 派生类自己的 vtable 里没有新槽位 |
| 修改 inline 函数、模板、`constexpr` 函数的函数体 | 静默的语义破坏 | 函数体已编进调用方，见上节 |
| 修改默认实参 | 旧调用方保留旧值 | 在调用处求值 |
| 修改枚举的底层类型（`enum E : std::uint8_t` 改为 `: int`） | 静默破坏 | 含有它的结构体布局变了；修饰名只含枚举名，不含底层类型 |
| 把函数改成 inline，或反过来 | 改成 inline 时旧调用方可能找不到符号 | inline 函数不保证生成导出符号 |
| 修改导出类型中的 `std::` 成员类型，或换一个标准库 | 视情况 | 见下文 |

后几类之所以危险，是因为它们满足动态链接要求的一切：符号都在。要发现它们，只能靠工具比较两个版本的 ABI。Linux 上常用 libabigail 的 `abidiff` 和 abi-compliance-checker，它们读调试信息，报告类型布局和 vtable 的变化（据文档，本机未安装）。

### 标准库类型也是 ABI

公开接口里出现 `std::string`、`std::vector` 时，这些类型的布局也成了库的 ABI，而它们由标准库实现决定，不由库作者决定。

libstdc++ 是一个典型例子（据 libstdc++ 文档对 dual ABI 的说明）。C++11 禁止写时复制的 `std::string`，并要求 `std::list::size()` 为常数时间，这两项都要改变布局。GCC 5 起，新实现放在内联命名空间 `std::__cxx11` 中，旧实现保留，由宏 `_GLIBCXX_USE_CXX11_ABI` 选择。两种设置编译的代码混用时，涉及 `std::string` 的函数修饰名不同（`std::__cxx11::basic_string` 与 `std::basic_string`），表现为链接时的未定义引用，而不是运行时的内存错误。

libc++ 把所有实体放在 `std::__1` 中，名字里的 `1` 就是它的 ABI 版本号（修饰名的细节见 [[toolchain/name-mangling]]）。本机的输出中，libc++ 的内部函数还带着 `[abi:nqe230103]` 这样的标签。按 libc++ 头文件 `__configuration/attributes.h` 中的说明，这个标签编码了库的版本、是否启用异常和加固模式，打在 `_LIBCPP_HIDE_FROM_ABI` 标记的、本来就不导出的函数上，防止不同配置编译的同名内部函数被链接器合并。

`std::` 类型的布局还受编译选项影响，例如调试版迭代器、libc++ 的有界迭代器，这张选项表见 [[toolchain/dependencies]]。

!!! warning "结论"
    只有在库和所有调用方都用同一个编译器、同一个标准库、同一组选项构建时，才可以在动态库的公开接口里使用 `std::` 类型。做不到这一点，就需要下一节的 C 接口。

## 最稳定的边界：C 接口

C 语言的 ABI 由各个平台的调用约定文档规定，多年不变：函数名不修饰，结构体按字段顺序排列，没有异常、虚函数和模板。C++ 用**语言链接**（language linkage）接入它。[[dcl.link#3]] 要求每个实现都支持 `extern "C"`，[[dcl.link#1]] 的注释说明，语言链接可以对应一种名字表示法和调用约定，这正是实现用来生成 C 风格符号的依据。

### 不透明句柄

```c title="geo_c.h"
#ifndef GEO_C_H
#define GEO_C_H
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif
#define GEO_EXPORT __attribute__((visibility("default")))

typedef struct geo_polygon geo_polygon;     /* 不透明句柄 */
typedef enum { GEO_OK = 0, GEO_EINVAL = 1, GEO_ENOMEM = 2 } geo_status;

GEO_EXPORT geo_polygon* geo_polygon_create(void);
GEO_EXPORT void         geo_polygon_destroy(geo_polygon* p);
GEO_EXPORT geo_status   geo_polygon_add(geo_polygon* p, double x, double y);
GEO_EXPORT geo_status   geo_polygon_area(const geo_polygon* p, double* out);
GEO_EXPORT const char*  geo_last_error(void);

#ifdef __cplusplus
}
#endif
#endif
```

`geo_polygon` 在头文件里只声明不定义，调用方只能持有指向它的指针，不知道它的大小和成员。这是 C 版的 pimpl：库可以任意改变 `geo_polygon` 的内容，调用方的二进制不受影响。

实现用 C++ 写，所有异常在边界上转换成错误码：

```cpp title="geo_c.cpp"
#include "geo_c.h"
#include <cmath>
#include <new>
#include <stdexcept>
#include <string>
#include <vector>

struct geo_polygon {                          // 只有库知道它的定义
  std::vector<std::pair<double, double>> pts;
};

namespace {
thread_local std::string last_error;

template <class F> geo_status guard(F f) noexcept {   // 异常不越过 C 边界
  try { f(); return GEO_OK; }
  catch (const std::bad_alloc&)          { last_error = "out of memory"; return GEO_ENOMEM; }
  catch (const std::invalid_argument& e) { last_error = e.what(); return GEO_EINVAL; }
  catch (...)                            { last_error = "unknown"; return GEO_EINVAL; }
}
}

geo_polygon* geo_polygon_create(void) { return new (std::nothrow) geo_polygon; }
void geo_polygon_destroy(geo_polygon* p) { delete p; }

geo_status geo_polygon_add(geo_polygon* p, double x, double y) {
  return guard([&] {
    if (!p || !std::isfinite(x) || !std::isfinite(y))
      throw std::invalid_argument("bad point");
    p->pts.emplace_back(x, y);
  });
}

geo_status geo_polygon_area(const geo_polygon* p, double* out) {
  return guard([&] {
    if (!p || !out) throw std::invalid_argument("null argument");
    double s = 0;
    auto& v = p->pts;
    for (std::size_t i = 0; i < v.size(); ++i) {
      auto [x0, y0] = v[i];
      auto [x1, y1] = v[(i + 1) % v.size()];
      s += x0 * y1 - x1 * y0;
    }
    *out = std::fabs(s) / 2;
  });
}

const char* geo_last_error(void) { return last_error.c_str(); }
```

```c title="client.c"
#include <math.h>
#include <stdio.h>
#include "geo_c.h"
int main(void) {
  geo_polygon* p = geo_polygon_create();
  geo_polygon_add(p, 0, 0);
  geo_polygon_add(p, 4, 0);
  geo_polygon_add(p, 4, 3);
  double a;
  if (geo_polygon_area(p, &a) == GEO_OK) printf("area=%.1f\n", a);
  if (geo_polygon_add(p, NAN, 0) != GEO_OK) printf("error: %s\n", geo_last_error());
  geo_polygon_destroy(p);
}
```

```text
$ clang++ -std=c++2c -O2 -fvisibility=hidden -shared geo_c.cpp -install_name @rpath/libgeo_c.dylib -o libgeo_c.dylib
$ clang -std=c17 client.c -L. -lgeo_c -Wl,-rpath,@executable_path -o client && ./client
area=6.0
error: bad point
$ nm -gU libgeo_c.dylib
0000000000000ce0 T _geo_last_error
00000000000005f4 T _geo_polygon_add
0000000000000900 T _geo_polygon_area
0000000000000580 T _geo_polygon_create
00000000000005ac T _geo_polygon_destroy
$ otool -L client
client:
	@rpath/libgeo_c.dylib (compatibility version 0.0.0, current version 0.0.0)
	/usr/lib/libSystem.B.dylib (compatibility version 1.0.0, current version 1356.0.0)
```

导出表正好是头文件里的 5 个函数，名字只多了 Mach-O 的前导下划线。`client` 不依赖 libc++，`std::vector` 和 `std::string` 只存在于库的内部，库甚至可以换一个标准库实现重新构建。

### 设计规则

- 句柄加成对的创建和销毁函数。 调用方从不 `sizeof`、从不 `free` 库的对象。
- 异常不越过边界。 标准允许 `extern "C"` 函数抛出异常，但 C 调用方无法处理它，异常穿过 C 代码编译出的、没有回溯信息的帧时，程序通常直接终止（机制见 [[toolchain/exception-implementation]]）。每个导出函数用 `noexcept` 的 `catch (...)` 包住，转换成错误码。
- 只用固定宽度的标量、指针和 C 结构体。 枚举的大小在 C 中由实现决定，要固定大小时，参数类型写成 `int32_t`，枚举值只用作常量。
- 需要传结构体时预留扩展余地。 常见做法是第一个字段写结构体的大小，库按调用方传来的大小读取字段；或者完全不公开结构体，只提供 getter 和 setter。
- 回调带一个 `void*` 用户数据，让调用方能传回自己的状态，回调本身也不能抛出异常。

### 在 C 接口之上恢复 C++ 的用法

C 接口难用，可以在它上面加一层只有头文件的 C++ 包装。这一层随调用方编译，和调用方用的是同一个编译器和同一个标准库，所以在这里使用 `std::unique_ptr` 和异常是安全的：

```cpp title="geo.hpp"
#pragma once
#include <memory>
#include <stdexcept>
#include "geo_c.h"

namespace geo {
class Polygon {            // 只在头文件里，随调用方一起编译
public:
  Polygon() : p_(geo_polygon_create()) {
    if (!p_) throw std::bad_alloc();
  }
  void add(double x, double y) { check(geo_polygon_add(p_.get(), x, y)); }
  double area() const {
    double a;
    check(geo_polygon_area(p_.get(), &a));
    return a;
  }
private:
  static void check(geo_status s) {
    if (s != GEO_OK) throw std::runtime_error(geo_last_error());
  }
  struct Deleter { void operator()(geo_polygon* p) const { geo_polygon_destroy(p); } };
  std::unique_ptr<geo_polygon, Deleter> p_;
};
}
```

本机用这个包装重写 `client.c` 的逻辑，输出相同，`NAN` 那一步变成了在调用方抛出的 `std::runtime_error`。这种两头宽、中间窄的结构常被称为沙漏（hourglass）接口：C++ 实现，C 边界，C++ 包装。代价是每次调用多一层间接，以及要手工维护两层接口。

## 异常和 RTTI 跨越动态库

如果接口里确实要传递 C++ 异常或多态对象，就要关心一件标准里理所当然、实现上并不简单的事：类型的身份。`catch (const ParseError&)` 能接住异常，前提是异常对象的类型和处理器的类型相同（[[except.handle#3]]）；`typeid(a) == typeid(b)` 在两者描述同一个类型时为真（[[type.info#3]]）。实现用 typeinfo 对象表示类型，所以问题变成：库里的 `ParseError` 的 typeinfo 和调用方的是不是被认为同一个。

```cpp title="err.h"
#pragma once
#include <stdexcept>
#define FN_API __attribute__((visibility("default")))
#ifndef ERR_API
#  define ERR_API
#endif
struct ERR_API ParseError : std::runtime_error {   // 没有 key function
  using std::runtime_error::runtime_error;
};
struct ERR_API Node { virtual ~Node() = default; };
struct ERR_API Leaf : Node { int v = 42; };
FN_API void parse(const char* s);
FN_API Node* make_node();
```

```cpp title="lib.cpp"
#include "err.h"
void parse(const char* s) { throw ParseError(s); }
Node* make_node() { return new Leaf; }
```

```cpp title="app.cpp"
#include <cstdio>
#include <typeinfo>
#include "err.h"
int main() {
  Node* n = make_node();
  std::printf("dynamic_cast: %s\n", dynamic_cast<Leaf*>(n) ? "ok" : "null");
  std::printf("typeid equal: %d\n", typeid(*n) == typeid(Leaf));
  try { parse("bad"); }
  catch (const ParseError& e) { std::printf("caught ParseError: %s\n", e.what()); }
  catch (const std::exception& e) { std::printf("caught std::exception: %s\n", e.what()); }
}
```

`app.cpp` 始终用默认选项编译，库用三种方式构建：

| 库的构建方式 | `dynamic_cast` | `typeid` 相等 | `catch` |
|---|---|---|---|
| 默认可见性 | ok | 1 | `ParseError` |
| `-fvisibility=hidden`，类型不加导出宏 | ok | 0 | 落到 `std::exception` |
| `-fvisibility=hidden`，`-DERR_API=__attribute__((visibility("default")))` | ok | 1 | `ParseError` |

第二行就是问题所在：库里抛出的 `ParseError` 没有被 `catch (const ParseError&)` 接住，`typeid` 也认为 `*n` 不是 `Leaf`。

原因在 libc++ 的 `typeinfo` 头文件里有详细说明。三个类型都没有 key function，typeinfo 在每个用到它们的映像中各生成一份。本机是 Apple arm64，libc++ 在这个平台上的做法是：本应以默认可见性的弱定义生成的 typeinfo，改为在每个映像中隐藏，并把 typeinfo 中名字指针的最高位置 1，表示可能有多份，比较时退回到按名字字符串比较，所以第一行和第三行成功（本机 `nm -m` 显示三种构建中库里的 typeinfo 都是 `was a private external`）；隐藏可见性的类型被认为在映像内唯一，只比较地址，跨映像的两份就是两个不同的类型。

`dynamic_cast` 在三种情况下都成功了。它不走头文件里的比较，而是调用运行时库 libc++abi 的 `__dynamic_cast`（本机 `nm -u app` 可见），后者在系统运行时里的比较策略与 `typeid` 不同。本机 `typeid` 和 `catch` 失败而 `dynamic_cast` 成功，只是一次观察，不能依赖。

在其他平台上，规则又不一样（据各库的头文件和文档）：Linux 上的 libc++ 默认只按地址比较，依靠动态加载器把各个映像中默认可见的 typeinfo 合并成一份；libstdc++ 默认按名字字符串比较。在所有这些实现中，隐藏可见性的类型跨映像都可能被当作不同的类型。

类型有 key function 时，问题会提前到链接阶段。把 `ParseError` 的析构函数声明为 `~ParseError() override;` 并在 `lib.cpp` 中定义，typeinfo 只在库中生成；库以 `-fvisibility=hidden` 构建、类型没有导出时，调用方链接失败：

```text
Undefined symbols for architecture arm64:
  "typeinfo for ParseError", referenced from:
      GCC_except_table0 in app-7e2265.o
ld: symbol(s) not found for architecture arm64
```

`GCC_except_table0` 是 `main` 的 LSDA，`catch` 子句在其中记录了要匹配的类型（见 [[toolchain/exception-implementation]]）。

!!! tip "推荐的做法"
    会被调用方 `catch`、`dynamic_cast` 或 `typeid` 的类型，在类上加导出宏，并给它们一个在库的 `.cpp` 中定义的 key function（通常是析构函数），让 vtable 和 typeinfo 只有库里的一份强定义。这些类型和 C++ 标准库类型一样，是 ABI 的一部分。

标准不知道映像的存在。对它来说，程序里只有一个 `ParseError` 类型，上面第二行的结果不符合 [[except.handle#3]]。这是实现为了支持可见性而偏离标准模型的地方。

## 谁分配，谁释放

库返回一块内存时，调用方怎样释放它，也是 ABI 的一部分。下面的库 v1 用 `new[]` 分配，调用方用 `delete[]` 释放，看上去没有问题：

```cpp title="buf.h"
#pragma once
#define API __attribute__((visibility("default")))
API char* make_buffer(int n);
API void free_buffer(char* p);
```

<div class="compare" markdown="1">

```cpp title="buf_v1.cpp"
#include "buf.h"
char* make_buffer(int n) {
  return new char[n];
}
void free_buffer(char* p) {
  delete[] p;
}
```

```cpp title="buf_v2.cpp"
#include "buf.h"
#include <cstddef>
namespace {
alignas(16) char arena[1 << 16];
std::size_t used = 0;
}
char* make_buffer(int n) {  // 改用 arena
  char* p = arena + used;
  used += (n + 15) & ~15;
  return p;
}
void free_buffer(char*) {}
```

</div>

```cpp title="app.cpp"
#include <cstdio>
#include "buf.h"
int main(int argc, char**) {
  char* p = make_buffer(64);
  if (argc > 1) { delete[] p; std::puts("app delete[] done"); }
  else          { free_buffer(p); std::puts("free_buffer done"); }
}
```

```text
$ ./app; ./app x                     # v1
free_buffer done
app delete[] done
$ ./app; ./app x                     # 换成 v2，app 不重新编译
free_buffer done
Abort trap: 6
```

v2 只改了库的内部实现，导出的函数一个没变，自己调用 `delete[]` 的调用方却崩溃了。按标准，`delete[]` 的操作数必须来自之前的数组 new 表达式，否则行为未定义（[[expr.delete#2]]）。v1 时调用方恰好满足这个条件，但这是库的实现细节，不是它的接口。

内存分配方式会因为库的版本、编译选项或平台而变化。Windows 上每个 DLL 可能链接不同的 C 运行时，各有各的堆，在一个 DLL 里 `malloc` 的内存交给另一个 DLL `free` 是常见的崩溃原因（据 MSVC 文档）。macOS 和 Linux 上整个进程通常共用一个 `malloc`，所以这类错误往往藏到库换了分配器才暴露。

规则很简单：**谁分配，谁释放**。库提供成对的创建和销毁函数；C++ 接口里可以返回 `std::unique_ptr<T, D>`，删除器 `D` 调用库导出的销毁函数，就像上一节 `geo.hpp` 的 `Deleter`。

!!! pitfall "在库里替换 operator new 会影响整个进程"
    想让库用自己的分配器，最直接的念头是在库里定义 `operator new[]` 和 `operator delete[]`。本机试验的结果是：即使库以 `-fvisibility=hidden` 构建，这两个函数仍被导出，因为 libc++ 的头文件把它们声明为默认可见；把它们显式标为 hidden，Clang 报错 `visibility does not match previous declaration`。链接这个库的可执行文件里，`delete[]` 就绑定到了库的版本（`nm -m` 显示 `(from libbuf)`）。这与标准一致：替换函数是整个程序的替换（[[dcl.fct.def.replace#1]]），不存在只对一个库生效的 `operator new`。库要用私有分配器，应该给它起自己的名字。

## 版本：install name、compatibility version 与 soname

### macOS：install name

动态库在构建时记录一个 **install name**，链接它的程序把这个名字原样抄进自己的依赖列表，运行时 `dyld` 按它查找库。同时记录两个版本号：current version 是这个文件的版本，compatibility version 是它兼容的最早版本。

```text
$ clang++ -std=c++2c -O2 -fvisibility=hidden -shared geo_c.cpp -o lib/libgeo.1.2.0.dylib \
    -install_name @rpath/libgeo.1.dylib -compatibility_version 1.0.0 -current_version 1.2.0
$ ln -s libgeo.1.2.0.dylib lib/libgeo.1.dylib && ln -s libgeo.1.dylib lib/libgeo.dylib
$ otool -l lib/libgeo.1.2.0.dylib | grep -A5 LC_ID_DYLIB
          cmd LC_ID_DYLIB
      cmdsize 48
         name @rpath/libgeo.1.dylib (offset 24)
   time stamp 1 Wed Dec 31 18:00:01 1969
      current version 1.2.0
compatibility version 1.0.0
$ clang client.c -Llib -lgeo -Wl,-rpath,@executable_path/lib -o client
$ otool -L client | sed -n 2p
	@rpath/libgeo.1.dylib (compatibility version 1.0.0, current version 1.2.0)
```

三个名字各有用途：

- `libgeo.dylib` 只在链接时使用，`-lgeo` 找的就是它，指向当前要链接的版本；
- `libgeo.1.dylib` 是 install name，程序运行时按它加载。`1` 是 ABI 的大版本，只有不兼容的改动才增加它；
- `libgeo.1.2.0.dylib` 是实际的文件。

`@rpath` 表示到程序记录的搜索路径列表（`LC_RPATH`，由 `-Wl,-rpath,...` 写入）中去找，`@executable_path` 和 `@loader_path` 分别是可执行文件和发起加载的映像所在的目录。这样库和程序可以一起移动，不必写死绝对路径。

compatibility version 原本用于检查：程序记录了链接时库的 compatibility version，`dyld` 加载到的库的 current version 低于它时拒绝加载（据 Apple 的文档）。本机试验中，`client` 链接 compatibility version 为 1.3.0 的库，运行时换上 current version 1.2.0 的库，`dyld` 照常加载、运行，没有报错。所以不应依赖这个检查。

### Linux：soname

ELF 的对应物是 **soname**（据文档，本机未验证）。构建时用 `-Wl,-soname,libgeo.so.1` 写入库的 `DT_SONAME`，程序链接时把它记入自己的 `DT_NEEDED`，运行时 `ld.so` 按 soname 查找。文件布局与 macOS 相同：`libgeo.so`（开发用的符号链接）→ `libgeo.so.1`（soname）→ `libgeo.so.1.2.0`（实际文件）。`readelf -d` 可以查看这两个字段，`ldconfig` 负责维护 soname 链接。

两个平台的约定一样：**ABI 不兼容时增加大版本号**，新旧两个大版本的库可以同时安装，旧程序继续加载旧库。兼容的改动只增加次版本号，install name 或 soname 不变。

## 用内联命名空间给 ABI 编号

install name 和 soname 管的是整个库。内联命名空间（[[g:inline-namespace]]）让版本号进入每一个符号名：内联命名空间的成员可以像外层命名空间的成员一样使用（[[namespace.def#6]]），但修饰名里带着内联命名空间的名字。

<div class="compare" markdown="1">

```cpp title="v1/cfg.h"
#pragma once
namespace cfg {
inline namespace v1 {
struct Options { int threads; };
int run(const Options& o);
}
}
```

```cpp title="v2/cfg.h"
#pragma once
namespace cfg {
inline namespace v2 {   // 布局变了
struct Options {
  long budget;
  int threads;
};
int run(const Options& o);
}
}
```

</div>

```cpp title="cfg.cpp"
#include "cfg.h"
int cfg::run(const Options& o) { return o.threads; }
```

```cpp title="app.cpp"
#include <cstdio>
#include "cfg.h"
int main() {
  cfg::Options o{};          // 使用方照常写 cfg::Options
  o.threads = 8;
  std::printf("run -> %d\n", cfg::run(o));
}
```

`app` 按 v1 编译，然后换上 v2 的库：

```text
$ nm -gU v1/libcfg.dylib v2/libcfg.dylib
0000000000000310 T __ZN3cfg2v13runERKNS0_7OptionsE
0000000000000310 T __ZN3cfg2v23runERKNS0_7OptionsE
$ ./app
run -> 8
$ rm lib/libcfg.dylib && cp v2/libcfg.dylib lib/ && ./app
dyld[97296]: Symbol not found: __ZN3cfg2v13runERKNS0_7OptionsE
  Referenced from: <D4C64185-...> .../app
  Expected in:     <3E3C62B2-...> .../lib/libcfg.dylib
Abort trap: 6
```

没有内联命名空间时，这次升级会让库按 v2 的布局读 `threads`，读到错误的值；有了它，同样的错误在加载时就被拦下了。

库还可以同时提供两个版本：`cfg.cpp` 分别包含 v1 和 v2 的头文件编译两次，两个目标文件链接进同一个动态库。本机这样构建的库同时导出 `cfg::v1::run` 和 `cfg::v2::run`，旧的 `app` 不重新编译也能正常运行，新编译的程序用 v2。一个程序同时链接同一个库的两个版本时，内联命名空间怎样把 ODR 违规变成两个不同的实体，见 [[toolchain/dependencies]]。

!!! pitfall "实现文件里要用限定名定义"
    `cfg.cpp` 最初写成 `namespace cfg { int run(const Options& o) { ... } }`，库构建成功，`app` 链接时却报 `cfg::v1::run(cfg::v1::Options const&)` 未定义；库导出的是 `cfg::run(cfg::v1::Options const&)`。非限定的声明在它所在的命名空间 `cfg` 中声明了一个新函数，它与 `v1::run` 的目标作用域不同，是一个重载（[[dcl.meaning.general#3]]）。用限定名 `int cfg::run(...)` 定义时，查找会考虑内联命名空间中的声明（[[basic.scope.scope#7]]），才会对应到 `v1::run`。

libc++ 的 `std::__1` 就是这个机制。本机 libc++ 的 `__config_site` 中定义了 `_LIBCPP_ABI_VERSION 1` 和 `_LIBCPP_ABI_NAMESPACE __1`；`__configuration/abi.h` 在 ABI 版本不低于 2 时打开一批会改变布局的改动。构建 libc++ 时选定更高的版本，内联命名空间的名字也随配置改变，新旧两种二进制就不会被误接在一起。

## 检查清单

设计一个以动态库形式发布的 C++ 库时，可以逐项检查：

| 问题 | 推荐做法 |
|---|---|
| 导出哪些符号 | `-fvisibility=hidden -fvisibility-inlines-hidden`，导出宏逐个标出；发布前用 `nm -gU` 核对导出表 |
| 调用方需不需要知道类的大小 | 不需要时用 pimpl 或不透明句柄 |
| 有没有虚函数要在以后扩展 | 公开的多态接口一旦发布就冻结；扩展时加新接口类 |
| 头文件里有没有会变的 inline 函数、模板和默认实参 | 会变的逻辑放进 `.cpp`；默认实参改用重载 |
| 公开接口里有没有 `std::` 类型 | 只有调用方确定使用同一标准库和选项时才这样做，否则用 C 接口 |
| 异常和多态类型 | 导出这些类型，给它们 key function |
| 内存由谁释放 | 库提供销毁函数，或返回带库删除器的 `unique_ptr` |
| 不兼容的改动 | 换内联命名空间，增加 install name 或 soname 的大版本号 |

## 思考题

!!! question "1"
    一个库的公开类 `Logger` 有虚函数，它的析构函数在头文件中写成 `virtual ~Logger() = default;`。库以 `-fvisibility=hidden` 构建，`Logger` 上加了导出宏。调用方写了 `struct MyLogger : Logger { ... };`。v2 在 `Logger` 的最后追加了一个虚函数 `flush()`，库内部会对传进来的 `Logger&` 调用它。旧的调用方会怎样？

<details markdown="1">
<summary>答案</summary>

`MyLogger` 的 vtable 是调用方按 v1 的定义生成的，只有 v1 的那些槽位，后面紧接着 `MyLogger` 自己新增的虚函数（如果有）。库按 v2 的布局读取 `flush` 所在的槽位，读到的是 `MyLogger` 的某个虚函数或者 vtable 之后的内存，调用的不是 `flush`。追加虚函数只在没有人派生这个类、库也不对外来对象调用新虚函数时才兼容。按标准，程序中 `Logger` 有两个不同的定义，违反 [[basic.def.odr#16]]，属于 {{ifndr}}。
</details>

!!! question "2"
    把 `int connect(int timeout_ms = 1000);` 的默认值改成 5000，算不算破坏 ABI？如果 `connect` 是 inline 函数呢？

<details markdown="1">
<summary>答案</summary>

不破坏符号和布局，但旧的调用方不重新编译就不会得到新值，因为默认实参在调用处求值（[[dcl.fct.default#1]]）。非 inline 函数在不同 TU 中有不同的默认实参是合法的；inline 函数则要求各 TU 累积的默认实参相同，否则是 {{ifndr}}（[[dcl.fct.default#4]]）。想让默认值由库决定，可以改用重载：`int connect();` 在库里调用 `connect(5000)`。
</details>

!!! question "3"
    库以 `-fvisibility=hidden` 构建，只导出 C 接口。它内部用到的 `std::vector<int>` 的成员函数，和调用方程序里的 `std::vector<int>` 的成员函数是不是同一份代码？这违反 ODR 吗？

<details markdown="1">
<summary>答案</summary>

不是同一份。隐藏可见性让每个映像各有一份实例化，它们不会在映像之间合并。只要两边用同一个版本的标准库头文件和相同的选项编译，各份定义由相同的记号组成，满足 [[basic.def.odr#16]] 的要求，多份副本本身不违反 ODR，行为也等价。两边的头文件不同（例如库用旧版 libc++ 构建）时，在标准的模型里就是两个不同的定义；实践中，因为没有任何 `std::` 对象跨过 C 边界，两份代码互不接触，不会出问题。这正是 C 接口能隔离标准库版本的原因。
</details>
