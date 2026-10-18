---
title: 库范围的要求：内容、头文件、模块与使用
summary: 库的实体都在 namespace std（可能藏在未指明的内联命名空间里）；库规范中的名字按声明处的非限定查找解释、不做 ADL（swap 等例外）；94 个 C++ 头文件与 21 个 C 设施头文件、<cname> 与 <name.h> 的区别；模块 std 与 std.compat；独立实现的库子集；include 的位置、顺序与 NDEBUG；库实体的链接。
status: done
covers: requirements.general, organization, organization.general, contents, headers, std.modules, compliance, using, using.overview, using.headers, using.linkage
papers: P2465R3, P1642R11
related: library, description, conventions, constraints, namespace.constraints, reserved.names, conforming, intro.compliance, module.import, cpp.include, dcl.link, basic.link, toolchain/modules-in-practice
tags: 库, 头文件, 模块, freestanding, 链接
updated: 2026-10-18
---

[[requirements]]（16.4）是第 16 章的主体："库范围的要求"——适用于**整个**标准库的规则。它分五块：

| 子条款 | 内容 | 本站页面 |
|---|---|---|
| [organization] | 库的内容与组织：命名空间、头文件、模块、独立实现 | 本页 |
| [using] | 程序如何使用库：include / import、链接 | 本页 |
| [utility.requirements] | 对类型和表达式的要求（命名要求表） | [[utility.requirements]] |
| [constraints] | 对程序的约束 | [[constraints]]、[[namespace.constraints]]、[[reserved.names]] |
| [conforming] | 对实现的约束 | [[conforming]] |

## 总则（[requirements.general]）

¶1 [requirements] 规定适用于整个 C++ 标准库的要求；第 17–33 章与附录 D 规定库中各个实体的要求。

¶2 **以线程间交互表述的要求，不适用于只有单个执行线程的程序。** 例如 [[res.on.data.races]] 对实现施加的"不得访问其他线程可访问的对象"等要求，在单线程程序中没有意义；这句话也为单线程环境下的实现（例如某些嵌入式独立实现）省去了同步开销的义务。

¶3 是本节的导航（即上表）。

## 库的内容（[organization.general]、[contents]）

[organization.general] ¶1 是导航：[contents] 描述库定义的实体和宏，[headers] 列出头文件，[compliance] 列出独立实现的要求。

### 库提供 synopsis 中的一切（[contents] ¶1）

¶1 除非另有说明，C++ 标准库为 C++ 标准库头文件（[headers]）的 synopsis 中描述的实体和宏提供定义。

### 一切都在 std 中——也许在一个看不见的内联命名空间里（¶2）

¶2 除 `operator new` 和 `operator delete` 外，所有库实体都定义在命名空间 `std` 或嵌套于 `std` 的命名空间中（脚注：C 标准库头文件 [support.c.headers] 也在全局命名空间定义名字，而 C 库设施的 C++ 头文件也**可以**在全局命名空间定义名字）。某个命名空间中声明的名字，是直接声明在该命名空间中，还是声明在其中的一个**内联命名空间**里，是**未指明**的（脚注：这让实现者可以用内联命名空间来支持库的多种配置）。

这一自由度在实践中被大量使用：

| 实现 | 内联命名空间 | 用途 |
|---|---|---|
| libc++ | `std::__1`（`_LIBCPP_ABI_NAMESPACE`，本机 `__config_site` 中定义） | ABI 版本化：将来的 ABI 破坏性改动可以换成 `__2`，新旧二进制可以链接在同一程序中而不冲突 |
| libstdc++ | `std::__cxx11`（仅 `basic_string`、`list` 等少数组件） | C++11 起的"双 ABI"：新的 `std::string`（不再写时复制）的符号名带 `__cxx11`，与旧 ABI 区分 |
| MSVC STL | 不使用 | — |

所以 `std::vector<int>` 在 libc++ 中的真名是 `std::__1::vector<int, std::__1::allocator<int>>`——这会出现在链接器错误和 mangled name 中。它也解释了为什么"自己前向声明 `std` 里的类型"不仅是 UB（[[namespace.std#1]]），在实践中还真的会坏：

```cpp error
namespace std { template<class T, class A> class vector; }  // UB：向 std 添加声明
#include <vector>
std::vector<int> v;   // libc++：error: reference to 'vector' is ambiguous
                      // ——std::vector（你声明的）与 std::__1::vector（真正的）是两个模板
int main() { }
```

想前向声明 iostream 类型，请用标准提供的 `<iosfwd>`；其他类型只能包含相应的头文件。

### 库规范中的名字如何解释（¶3）

¶3 第 17–33 章或附录 D 中，**声明 D 的规范**里使用非限定名（`swap`、`make_error_code`、`make_error_condition`、`from_stream`、`submdspan_mapping` 除外）时，其含义如同在 D 的上下文中进行**非限定名字查找**（[[basic.lookup.unqual]]）而确定。Note 1：**不进行实参依赖查找**。类似地，*qualified-id* 的含义如同在 D 的上下文中做限定名字查找而确定。

- Example 1：`std::to_array` 规范中的 `is_array_v` 指的是 `::std::is_array_v`。
- Note 2：表达式中的**运算符**（[[over.match.oper]]）不受此限制，见 [[global.functions]]。
- `swap` 的含义在可交换值的重载决议上下文（[[swappable.requirements]]）中确定——即"两步式" `using std::swap; swap(a, b);`。
- `make_error_code`、`make_error_condition`、`from_stream`、`submdspan_mapping` 的含义如同进行 **ADL** 而确定——这些是标准库的**定制点**：用户为自己的错误枚举定义 `make_error_code`，让 `std::error_code` 的构造函数通过 ADL 找到它；为自己的 `mdspan` 布局定义 `submdspan_mapping`；为自己的时间类型定义 `from_stream`。

这条规则的意义在于：当规范写"*Effects*: Equivalent to: `return move(x);`"时，这个 `move` 就是 `std::move`，不会因为 `x` 的类型来自某个也定义了 `move` 的命名空间而被 ADL 劫持。实现必须做到这一点——这就是为什么 libc++/libstdc++ 的源码里到处是 `std::move(...)`、`std::forward<...>(...)`、`std::__addressof(...)` 这样的限定调用（[[global.functions#4]] 从实现的角度重申了这一点）。

## 头文件（[headers]）

### 头文件是什么（¶1）

¶1 C++ 标准库的每个元素都在某个**头文件**（header）中声明或定义（按适用情况）。脚注：头文件不一定是源文件，`<` 和 `>` 之间的序列也不一定是合法的源文件名（[[cpp.include]]）。也就是说，`#include <vector>` 可以由编译器"凭空"提供，不需要磁盘上有一个叫 `vector` 的文件——尽管实践中所有实现都用文件。

### C++ 库头文件（¶2）

¶2 C++ 标准库提供**C++ 库头文件**，见表 24。当前草案中共 94 个：

`<algorithm>` `<any>` `<array>` `<atomic>` `<barrier>` `<bit>` `<bitset>` `<charconv>` `<chrono>` `<compare>` `<complex>` `<concepts>` `<condition_variable>` `<contracts>` `<coroutine>` `<debugging>` `<deque>` `<exception>` `<execution>` `<expected>` `<filesystem>` `<flat_map>` `<flat_set>` `<format>` `<forward_list>` `<fstream>` `<functional>` `<future>` `<generator>` `<hazard_pointer>` `<hive>` `<initializer_list>` `<inplace_vector>` `<iomanip>` `<ios>` `<iosfwd>` `<iostream>` `<istream>` `<iterator>` `<latch>` `<limits>` `<linalg>` `<list>` `<locale>` `<map>` `<mdspan>` `<memory>` `<memory_resource>` `<meta>` `<mutex>` `<new>` `<numbers>` `<numeric>` `<optional>` `<ostream>` `<print>` `<queue>` `<random>` `<ranges>` `<ratio>` `<rcu>` `<regex>` `<scoped_allocator>` `<semaphore>` `<set>` `<shared_mutex>` `<simd>` `<source_location>` `<span>` `<spanstream>` `<sstream>` `<stack>` `<stacktrace>` `<stdexcept>` `<stdfloat>` `<stop_token>` `<streambuf>` `<string>` `<string_view>` `<syncstream>` `<system_error>` `<text_encoding>` `<thread>` `<tuple>` `<type_traits>` `<typeindex>` `<typeinfo>` `<unordered_map>` `<unordered_set>` `<utility>` `<valarray>` `<variant>` `<vector>` `<version>`

### C 库设施的 C++ 头文件（¶3）

¶3 C 标准库的设施由表 25 中的 21 个额外头文件提供：

`<cassert>` `<cctype>` `<cerrno>` `<cfenv>` `<cfloat>` `<cinttypes>` `<climits>` `<clocale>` `<cmath>` `<csetjmp>` `<csignal>` `<cstdarg>` `<cstddef>` `<cstdint>` `<cstdio>` `<cstdlib>` `<cstring>` `<ctime>` `<cuchar>` `<cwchar>` `<cwctype>`

脚注：**有意**不为 `<stdnoreturn.h>` 和 `<threads.h>` 提供 C++ 头文件——前者对应 C 的 `_Noreturn`（C++ 有 `[[noreturn]]`），后者对应 C11 线程（C++ 有 `<thread>`）。曾经存在的 `<ccomplex>`、`<cstdalign>`、`<cstdbool>`、`<ctgmath>`、`<ciso646>` 已被移除，其名字成为"僵尸名字"（[[zombie.names]]）。

### 可导入的 C++ 库头文件（¶4）

¶4 表 24 中的头文件（对独立实现来说是其提供的子集）统称为[[g:importable-library-header|**可导入的 C++ 库头文件**]]（importable C++ library headers）。Note 1：它们可以被导入（[[module.import]]）：

```cpp
import <vector>;                // 导入 <vector> 头文件单元
std::vector<int> vi;            // OK
```

注意表 25 的 C 设施头文件**不在**其中——`import <cstdio>;` 不保证可行（实现可以支持，但那是实现定义的可导入头文件）。原因是 C 头文件高度依赖宏（`assert` 依赖 `NDEBUG`、`errno` 本身是宏……），不适合做成头文件单元。

### `<cname>` 与 `<name.h>`（¶5、¶9）

¶5 除第 16–33 章及附录 D 另有说明外，每个头文件 `<cname>` 的内容与 C 标准库中对应的头文件 `<name.h>` 相同。但在 C++ 标准库中，声明（C 中定义为宏的名字除外）位于命名空间 `std` 的命名空间作用域中。这些名字（包括第 17–33 章与附录 D 添加的重载）是否先在全局命名空间作用域中声明、再通过显式 *using-declaration*（[[namespace.udecl]]）注入 `std`，是**未指明**的。

¶9 [support.c.headers] 描述了在 C++ 程序中使用 `<name.h>`（C 头文件）形式的效果。脚注：`.h` 头文件把所有名字倒进全局命名空间，而新形式把名字放在 `std` 中，因此**新形式是首选**，除非程序意图与 C 严格兼容。

合在一起，可移植的规则是：

| 你包含的 | 保证可用 | 可能可用（未指明） |
|---|---|---|
| `<cstdio>` | `std::printf` | `::printf` |
| `<stdio.h>` | `::printf` | `std::printf` |

```cpp run ok
#include <cstdio>
int main() {
  std::printf("std\n");     // 保证可用
  ::printf("global\n");     // 实践中三大实现都可用，但标准不保证
}
```

libc++ 正是 ¶5 允许的做法：`<cstring>` 先包含 C 的 `<string.h>`（名字在全局），再写 `using ::strlen _LIBCPP_USING_IF_EXISTS;` 注入 `std`。所以在 libc++ 中 `::strlen` 和 `std::strlen` 是**同一个函数**——这也正是 [[extern.types]] 要求 `::T` 与 `std::T` 必须是同一类型的背景。

### 宏必须是宏，函数必须是函数（¶6–¶8）

- ¶6 在 C 中定义为宏的名字，在 C++ 标准库中也必须定义为宏，即使 C 允许以函数实现。Note 2 列出：`assert`、`offsetof`、`setjmp`、`va_arg`、`va_end`、`va_start`。
- ¶7 在 C 中定义为函数的名字，在 C++ 标准库中必须定义为函数。脚注：这禁止了 C 中允许的"在函数原型之外再提供一个**屏蔽宏**（masking macro）"的做法；在 C++ 中要获得同样的内联效果，唯一办法是提供 `extern inline` 函数定义。
- ¶8 在 C++ 中是关键字或运算符的标识符，不得在 C++ 标准库头文件中被定义为宏。脚注：特别地，包含标准头文件 `<iso646.h>` 没有效果。

¶7 的意义：在 C 中，`<ctype.h>` 可以把 `isdigit` 同时声明为函数和宏 `#define isdigit(c) (...)`；在 C++ 中这会破坏 `std::isdigit`（宏不认识命名空间）、破坏取地址、破坏重载。所以 C++ 的 `isdigit` 一定是真正的函数——尽管能不能取它的地址又是另一回事（[[namespace.std#6]]）。

¶8 说的是 `and`、`or`、`not`、`bitand`、`xor` 等**替代记号**（[[lex.digraph]]）以及 `bool`、`true`、`false` 这样的关键字：C 用 `<iso646.h>` 和 `<stdbool.h>` 把它们定义成宏，而在 C++ 里它们本就是记号或关键字，标准库头文件不得把它们定义成宏。

### C 附录 K 的 `_s` 函数（¶10–¶11）

¶10 ISO/IEC 9899:2024 附录 K 描述了大量函数及相关的类型和宏，它们"促进更安全的编程"。函数名有 `_s` 后缀，大多数提供与无后缀版本相同的服务，但通常多一个表示结果数组大小的实参。若包含了任何 C++ 头文件，这些名字中的任何一个是否在全局命名空间声明，是**实现定义**的。（**没有一个**声明在 `std` 中。）

¶11 表 26 列出可能在某个头文件中声明的附录 K 名字（`memcpy_s`、`strcpy_s`、`fopen_s`、`errno_t`、`rsize_t`、`RSIZE_MAX`、`set_constraint_handler_s`……）。这些名字也受 [[macro.names]] 的限制——程序不能把它们定义为宏。

实践中，MSVC 的 UCRT 提供这些函数（含义与附录 K 不尽相同），glibc 不提供。所以 `std::memcpy_s` 永远是错的，`::memcpy_s` 不可移植。

## 标准库模块（[std.modules]）

¶1 C++ 标准库提供以下 **C++ 库模块**。

¶2 具名模块 **`std`** 导出由可导入 C++ 库头文件（表 24，或独立实现提供的子集）和 C 库设施的 C++ 头文件（表 25）提供的、位于命名空间 `std` 中的声明。此外它还导出 `<new>` 提供的**全局命名空间**中的存储分配与释放函数（`::operator new` / `::operator delete`）。

¶3 具名模块 **`std.compat`** 导出与 `std` 相同的声明，另外还导出：

- **¶3.1** 与表 25 的 C 设施头文件在 `std` 中提供的声明相对应的**全局命名空间**声明（[support.c.headers.other] 显式排除的除外）；
- **¶3.2** `<stdbit.h>` 和 `<stdckdint.h>` 提供的声明。

¶4 标准库中的声明附属于哪个模块是**未指明**的。Note 1：符合标准的实现会确保混用 `#include` 和 `import` 不会导致冲突的附属关系（[[basic.link]]）。*推荐做法*：实现应确保这些附属关系不妨碍标准库模块将来的演进或拆分。

¶5 无论是通过包含头文件、导入头文件单元还是导入 C++ 库模块使其可达，标准库中的声明都**指称同一实体**。

¶6 *推荐做法*：实现应避免从 C++ 库模块导出任何其他声明。Note 2：与所有具名模块一样，C++ 库模块**不使宏可见**（[[module.import]]），例如 `assert`、`errno`、`offsetof`、`va_arg`。

```cpp
import std;
int main() {
  std::vector<int> v{1, 2, 3};
  std::println("{}", v);                 // OK
  ::operator delete(::operator new(1));  // OK：std 也导出全局的 operator new/delete（¶2）
  // ::printf("x");                      // error：全局 C 名字只有 std.compat 导出（¶3.1）
  // assert(v.size() == 3);              // error：模块不导出宏（¶6）
}
```

在本机用 libc++ 自带的 `std.cppm` 预编译模块后验证：上面未注释的部分编译运行正常、输出 `[1, 2, 3]`；取消注释 `::printf` 一行，Clang 报 "missing '#include <_printf.h>'; 'printf' must be declared before it is used"；取消注释 `assert` 一行，报 "use of undeclared identifier 'assert'"。需要 `assert` 时，在 `import std;` 之后再 `#include <cassert>`——这正是 ¶4 Note 1 和 ¶5 保证可行的混用。

¶5 是让这种混用安全的关键：`#include <vector>` 得到的 `std::vector` 与 `import std;` 得到的是同一个实体，不会违反 ODR，也不会产生两个不同的类型。模块的工程实践见 [[toolchain/modules-in-practice]]。

!!! history "模块的历史"
    C++20 引入模块时，标准库只承诺"可导入的头文件"（`import <vector>;`），没有具名模块。C++23 通过 [[P2465R3]] 加入了 `std` 与 `std.compat`。一个 `import std;` 往往比包含少数几个头文件还快——因为模块的 BMI 只需构建一次。

## 独立实现（[compliance]）

¶1 定义了两种实现：**宿主实现**（hosted）与**独立实现**（freestanding，[[intro.compliance]]）；实现属于哪一种是**实现定义**的。对宿主实现，本文档描述了可用头文件的集合。

¶2 独立实现有一个实现定义的头文件集合，至少必须包含表 27 中的头文件。当前草案中的表 27 已经相当长：

| 类别 | 头文件 |
|---|---|
| 语言支持 | `<cstddef>` `<cstdlib>` `<cfloat>` `<climits>` `<limits>` `<version>` `<cstdint>` `<new>` `<typeinfo>` `<source_location>` `<exception>` `<contracts>` `<initializer_list>` `<compare>` `<coroutine>` `<cstdarg>` |
| 概念、诊断 | `<concepts>` `<cerrno>` `<system_error>` `<debugging>` |
| 内存、元编程、工具 | `<memory>` `<type_traits>` `<ratio>` `<utility>` `<tuple>` `<optional>` `<variant>` `<expected>` `<functional>` `<bit>` `<stdbit.h>` |
| 容器与视图 | `<array>` `<inplace_vector>` `<span>` `<mdspan>` |
| 迭代器、范围、算法 | `<iterator>` `<ranges>` `<algorithm>` `<numeric>` `<execution>` |
| 字符串与文本 | `<string_view>` `<string>` `<cstring>` `<cwchar>` `<charconv>` |
| 数值、并发 | `<random>` `<cmath>` `<atomic>` |

¶3 对表 27 中的每个头文件，独立实现至少提供该头文件中声明的**独立项**（[[freestanding.item]]）。

注意"头文件在表中"不等于"头文件里的所有东西都要提供"：`<string>` 在表中，但 `std::basic_string` 本身（需要动态内存分配）并不是独立项——独立的部分是 `char_traits` 等。`<memory>` 中的 `unique_ptr` 是独立项，但 `shared_ptr`、`std::allocator`……需要逐条查看 synopsis 的标注。

¶4 [[g:hosted-library-facilities|**宿主库设施**]]（hosted library facilities）是本文档描述的、宿主实现必须提供而独立实现不必提供的设施集合。独立实现提供宿主库设施的一个（可能为空的）实现定义的子集。除非另有说明，以这种方式提供的每个声明、实体和宏的要求，与宿主实现的相应要求相同，只是命名空间的成员不必全部存在。

¶5 独立实现为宿主库设施中命名空间作用域的函数和函数模板的一个（可能为空的）实现定义的子集提供**删除定义**（[[dcl.fct.def.delete]]）。Note 1：实现可以提供删除定义，使得把程序从独立实现迁移到宿主实现时，重载决议的结果不会静默改变。（与 [[freestanding.item#3]] 的 *freestanding-deleted* 机制同理。）

本机 Clang 下可以用 `-ffreestanding` 让 `__STDC_HOSTED__` 为 0（见 [[intro.compliance]]），但这只改变编译器的假设；libc++ 本身并不提供一个裁剪到表 27 的"独立模式"。真正的独立实现通常出现在嵌入式工具链和内核开发中。

## 使用库（[using]）

### 概述（[using.overview]）

¶1 [using] 描述 C++ 程序如何访问标准库设施。[using.headers] 描述翻译**阶段 4**（预处理）的效果，[using.linkage] 描述**阶段 8**（链接）的效果（翻译阶段见 [[lex.phases]]）。

### include 与 import（[using.headers]）

¶1 标准库中的实体定义在头文件中，当翻译单元包含适当的 `#include` 预处理指令（[[cpp.include]]）或适当的 import 声明（[[module.import]]）时，其内容对该翻译单元可用。

¶2 翻译单元可以**以任何顺序**包含库头文件（[[lex.separate]]）。每个头文件可以被包含多次，效果与只包含一次相同——**例外**是 `<cassert>` 或 `<assert.h>`：每次包含的效果取决于当时 `NDEBUG` 的定义（脚注：这与 C 标准库相同）。

```cpp run ok
#define NDEBUG
#include <cassert>
void f() { assert(false); }      // 断言被禁用：assert 展开为 ((void)0)
#undef NDEBUG
#include <cassert>               // 再次包含：按当前的 NDEBUG 重新定义 assert
void g(int x) { assert(x > 0); } // 断言启用
int main() { f(); g(1); }
```

"以任何顺序"是对实现的要求：标准头文件不能依赖被包含的先后顺序（[[res.on.headers#2]] 从实现的角度重申：定义在多个头文件中的类型和宏，必须能以任意顺序包含）。

¶3 翻译单元只能在**任何声明或定义之外**包含头文件，在模块单元中只能在其**全局模块片段**中包含；并且必须在该翻译单元中第一次引用头文件中声明的实体**之前**（按词法顺序）包含该头文件或导入相应的头文件单元。**不要求诊断**（{{ifndr}}）。

```cpp error
namespace N {
#include <vector>    // IFNDR：在声明内部包含标准头文件
}                    // 本机 libc++：error: 'operator new' cannot be declared inside a namespace
int main() { }
```

虽然标准说"不要求诊断"，这类代码在实践中通常都会编译失败——头文件里的声明被放进了错误的命名空间。比较隐蔽的是"先用后包含"：

```cpp
#include <string>               // 碰巧间接提供了 std::size_t 和某些 <cstring> 的声明
std::size_t n = std::strlen("abc");   // IFNDR：在包含 <cstring> 之前引用了其中声明的实体
#include <cstring>
```

这段代码在大多数实现上能编译，但违反了 ¶3；换一个标准库实现（或同一实现的新版本减少了传递包含），它就可能编译失败。

### 链接（[using.linkage]）

¶1 C++ 标准库中的实体具有**外部链接**。除非另有说明，对象和函数具有默认的 `extern "C++"` 链接（[[dcl.link]]）。

¶2 C 标准库中声明为外部链接的名字，是 `extern "C"` 还是 `extern "C++"` 链接，是**实现定义**的。建议实现使用 `extern "C++"` 链接。脚注：声明 C 标准库中的对象或函数签名，唯一可靠的方式是**包含声明它的头文件**——尽管 C 标准 7.1.4 给了"自己声明库函数"的余地。

¶3 程序所需的、库中定义的对象和函数，在程序启动之前被包含进程序。

¶4 另见替换函数（[[replacement.functions]]）、运行期变化（[[handler.functions]]）。

¶2 的脚注说的是 C 程序员熟悉的做法：

```cpp
extern "C" int printf(const char*, ...);   // 不可移植：printf 可能是 extern "C++"，
int main() { printf("hi\n"); }             // 也可能根本不是这个签名
```

在 C 中，"自己声明标准库函数"是合法的（只要签名对）。在 C++ 中，`printf` 的语言链接是实现定义的，自己写的声明可能与真实声明的链接不一致——这既可能是非良构（同一函数的两个声明链接不同，[[dcl.link]]），也违反了 [[extern.names]] 对这些名字的保留。实践中三大实现都用 `extern "C"`，但标准不保证。

## 思考题

!!! question "思考题 1"
    下面的代码在 libc++ 和 libstdc++ 上都能编译通过。它可移植吗？为什么？

    ```cpp
    #include <iostream>
    int main() { std::string s = "hello"; std::cout << s.size(); }
    ```

<details markdown="1">
<summary>展开查看答案与解析</summary>

不可移植。`std::string` 声明在 `<string>` 中，代码没有包含它。[[res.on.headers#1]] 允许 C++ 头文件包含其他 C++ 头文件，`<iostream>` 在两个实现上都碰巧（间接）提供了 `std::string` 的完整定义，但标准只要求 `<iostream>` 提供其 synopsis 中的内容——而 `<iostream>` 的 synopsis 只包含 `<ios>`、`<streambuf>`、`<istream>`、`<ostream>`，`std::string` 不在其中。按 [using.headers] ¶3，程序必须在引用 `std::string` 之前包含 `<string>`，否则 IFNDR。实现可以随时减少传递包含（libc++ 近年来就在持续清理），届时代码就会编译失败。
</details>

!!! question "思考题 2"
    `import std;` 之后能否使用 `std::size_t`？能否使用 `::size_t`？能否使用 `offsetof`？

<details markdown="1">
<summary>展开查看答案与解析</summary>

- `std::size_t`：能。它是 `<cstddef>`（表 25）在 `std` 中提供的声明，¶2 规定 `std` 模块导出它。
- `::size_t`：不保证。全局命名空间的 C 名字由 `std.compat` 导出（¶3.1），`std` 模块只额外导出全局的 `operator new`/`operator delete`。不过，实现也可能因为 `std` 模块的其他声明碰巧使其可见，但标准不保证。
- `offsetof`：不能。它是宏（[headers] ¶6 要求其为宏），而模块不导出宏（¶6 Note 2）。需要时 `#include <cstddef>`。
</details>

## 小结

!!! summary "核心要点"
    - 库实体都在 `std`（`operator new`/`delete` 例外），是否藏在内联命名空间中未指明——libc++ 是 `std::__1`。永远不要自己前向声明 std 中的东西。
    - 库规范中的非限定名按声明处的非限定查找解释、不做 ADL；`swap` 用两步式，`make_error_code` 等四个定制点用 ADL。
    - 94 个 C++ 头文件 + 21 个 C 设施头文件；`<cname>` 保证 `std::` 名字，`<name.h>` 保证全局名字，反向都未指明。
    - C 中的宏必须是宏，函数必须是函数（无屏蔽宏）；C++ 关键字和替代记号不得被定义为宏；附录 K 的 `_s` 函数从不在 `std` 中。
    - `import std;` 导出 `std` 中的一切 + 全局 `operator new`/`delete`；`std.compat` 再加全局 C 名字；模块不导出宏；include 与 import 混用指称同一实体。
    - 独立实现：表 27 中的头文件只需提供标为 freestanding 的项；宿主设施可以被删除定义以防止静默改变语义。
    - include 只能在声明之外、在首次引用之前（IFNDR）；同一头文件可重复包含（`<cassert>` 随 `NDEBUG` 变化）。
    - 库实体外部链接、默认 `extern "C++"`；C 名字的语言链接实现定义——不要自己声明 C 库函数。
