---
title: 库范围的要求：内容、头文件、模块与使用
summary: 适用于整个标准库的基本规则：库实体都在 std 中（可能在内联命名空间里），库规范中的名字怎样查找，C++ 头文件与 C 头文件的区别，import std 与 std.compat，独立实现的库子集，以及包含头文件的位置、顺序和链接。
status: done
covers: requirements.general, organization, organization.general, contents, headers, std.modules, compliance, using, using.overview, using.headers, using.linkage
papers: P2465R3, P1642R11
related: library, description, conventions, constraints, namespace.constraints, reserved.names, conforming, intro.compliance, module.import, cpp.include, dcl.link, basic.link, toolchain/modules-in-practice
tags: 库, 头文件, 模块, freestanding, 链接
updated: 2026-10-19
---

!!! tldr
    - 库实体都在 `std` 里，但可能藏在一个未指明的内联命名空间中（libc++ 是 `std::__1`），所以自己前向声明 `std` 里的类型行不通。
    - 包含 `<cstdio>` 只保证有 `std::printf`，包含 `<stdio.h>` 只保证有 `::printf`，另一半是否存在未指明。
    - `import std;` 导出 `std` 中的一切，但不导出宏，也不导出全局的 C 名字；后者要用 `import std.compat;`。
    - 头文件只能在所有声明之外、并且在第一次使用其中的实体之前包含；靠别的头文件间接带进来的名字不可移植。
    - C 库函数的语言链接由实现定义，声明它们唯一可靠的方式是包含对应的头文件。

[[requirements]] 是适用于整个标准库的规则，本页讲其中的库的组织（[organization]）和程序怎样使用库（[using]）。对类型的要求、对程序的约束和对实现的约束分别见 [[utility.requirements]]、[[constraints]] 和 [[conforming]]。

## 库实体在哪个命名空间 [contents]

### 前向声明 std 里的类型为什么会出错（¶2）

```cpp ub
namespace std { template<class T, class A> class vector; }  // UB：向 std 添加声明
#include <vector>
std::vector<int> v;   // libc++：error: reference to 'vector' is ambiguous
int main() {}
```

向 `std` 添加声明本身就是未定义行为（[[namespace.std#1]]），而在 libc++ 上它还会直接导致编译失败。原因在 ¶2。

¶2 除 `operator new` 和 `operator delete` 外，所有库实体都定义在命名空间 `std` 或嵌套在 `std` 里的命名空间中。一个名字是直接声明在某个命名空间里，还是声明在其中的一个内联命名空间里，是未指明的。脚注说明，这样做是为了让实现可以用内联命名空间支持库的多种配置。

实践中各实现这样使用它：

| 实现 | 内联命名空间 | 用途 |
|---|---|---|
| libc++ | `std::__1`（`_LIBCPP_ABI_NAMESPACE`，本机 `__config_site` 中定义） | ABI 版本化：将来不兼容的 ABI 可以换成 `__2`，新旧二进制可以链接进同一个程序 |
| libstdc++ | `std::__cxx11`（只用于 `basic_string`、`list` 等少数组件） | C++11 起的双 ABI：新的 `std::string`（不再写时复制）符号名带 `__cxx11`，与旧 ABI 区分 |

所以 `std::vector<int>` 在 libc++ 中的真名是 `std::__1::vector<int, std::__1::allocator<int>>`，链接错误和符号名里看到的就是它。上面的程序里，自己声明的 `std::vector` 和真正的 `std::__1::vector` 是两个不同的模板，名字查找时两者都可见，于是歧义。想前向声明 iostream 类型可以用 `<iosfwd>`，其他类型只能包含对应的头文件。

### 库规范中的名字怎样查找（¶3）

¶3 第 17–33 章和附录 D 里，声明 D 的规范中出现的非限定名，含义如同在 D 的上下文中做非限定名字查找（[[basic.lookup.unqual]]）而确定。注 1 强调，不做实参依赖查找（ADL）。限定名同样按 D 处的限定查找确定。例 1：`std::to_array` 的规范里提到的 `is_array_v` 就是 `::std::is_array_v`。

所以规范写 *Effects*: Equivalent to: `return move(x);` 时，这个 `move` 就是 `std::move`，不会因为 `x` 的类型所在的命名空间也有一个 `move` 而被 ADL 换掉。实现必须做到这一点，这也是标准库源码里到处写 `std::move(...)`、`std::forward<...>(...)` 的原因（[[global.functions#4]] 从实现的角度重申了这一点）。

有几处例外：

- 注 2：表达式中的运算符不受这条限制（[[over.match.oper]]），见 [[global.functions]]。
- `swap` 的含义按可交换值的重载决议语境确定（[[swappable.requirements]]），也就是先 `using std::swap;` 再非限定调用 `swap(a, b)` 的两步式。
- `make_error_code`、`make_error_condition`、`from_stream`、`submdspan_mapping` 按 ADL 确定。它们是库的定制点：用户为自己的错误枚举定义 `make_error_code`，`std::error_code` 的构造函数经 ADL 找到它；为自己的 `mdspan` 布局定义 `submdspan_mapping`；为自己的时间类型定义 `from_stream`。

## 头文件 [headers]

### 两类头文件（¶1–¶3）

¶1 库的每个元素都在某个**头文件**（header）中声明或定义。脚注指出，头文件不一定是源文件，`<` 和 `>` 之间的名字也不一定是合法的文件名（[[cpp.include]]）；只是实践中所有实现都用文件。

¶2 C++ 库头文件见表 24，当前草案中有 94 个，从 `<algorithm>` 到 `<version>`，包括较新的 `<contracts>`、`<meta>`、`<simd>`、`<hive>`、`<inplace_vector>`。

¶3 C 标准库的设施由表 25 中另外 21 个头文件提供：`<cassert>`、`<cctype>`、`<cerrno>`、`<cfenv>`、`<cfloat>`、`<cinttypes>`、`<climits>`、`<clocale>`、`<cmath>`、`<csetjmp>`、`<csignal>`、`<cstdarg>`、`<cstddef>`、`<cstdint>`、`<cstdio>`、`<cstdlib>`、`<cstring>`、`<ctime>`、`<cuchar>`、`<cwchar>`、`<cwctype>`。脚注说明，`<stdnoreturn.h>` 和 `<threads.h>` 有意没有对应的 C++ 头文件，C++ 有 `[[noreturn]]` 和 `<thread>`。以前的 `<ccomplex>`、`<cstdbool>` 等已被移除，名字保留为 [[zombie.names]]。

### `<cname>` 与 `<name.h>`（¶5、¶9）

```cpp run ok
#include <cstdio>
int main() {
  std::printf("std\n");     // 保证可用
  ::printf("global\n");     // 三大实现都可用，但标准不保证
}
```

¶5 `<cname>` 的内容与 C 标准库对应的 `<name.h>` 相同，但声明（C 中定义为宏的名字除外）位于命名空间 `std` 中。这些名字是否先在全局命名空间声明、再用 *using-declaration*（[[namespace.udecl]]）引入 `std`，是未指明的。

¶9 包含 `<name.h>` 形式的效果见 [support.c.headers]：名字都在全局命名空间。脚注建议，除非程序要与 C 严格兼容，否则用 `<cname>` 形式。合起来，可移植的规则是：

| 包含的头文件 | 保证可用 | 是否可用未指明 |
|---|---|---|
| `<cstdio>` | `std::printf` | `::printf` |
| `<stdio.h>` | `::printf` | `std::printf` |

libc++ 采用的就是 ¶5 允许的做法：`<cstring>` 先包含 C 的 `<string.h>`，名字落在全局，再写 `using ::strlen _LIBCPP_USING_IF_EXISTS;` 引入 `std`。所以在 libc++ 中 `::strlen` 和 `std::strlen` 是同一个函数。[[extern.types]] 要求 `::T` 和 `std::T` 是同一类型，也是这个背景。

### 宏必须是宏，函数必须是函数（¶6–¶8）

¶6 在 C 中定义为宏的名字，在 C++ 中也必须是宏，即使 C 允许用函数实现。注 2 列出了 `assert`、`offsetof`、`setjmp`、`va_arg`、`va_end`、`va_start`。

¶7 在 C 中定义为函数的名字，在 C++ 中必须是函数。C 允许 `<ctype.h>` 在函数原型之外再提供一个同名的屏蔽宏（masking macro），如 `#define isdigit(c) (...)`；在 C++ 中这会破坏 `std::isdigit`（宏不认识命名空间）、取地址和重载，所以被禁止。脚注说，想得到同样的内联效果，只能提供 inline 函数定义。至于能不能取 `isdigit` 的地址，那是另一个问题（[[namespace.std#6]]）。

¶8 在 C++ 中是关键字或运算符的标识符，不能在标准库头文件里定义成宏。C 用 `<iso646.h>` 把 `and`、`or`、`not` 等定义成宏，而在 C++ 中它们本来就是替代记号（[[lex.digraph]]）。脚注说，包含 `<iso646.h>` 没有任何效果。

### 可导入的头文件（¶4）

¶4 表 24 中的头文件（对独立实现是它提供的那部分）统称[[g:importable-library-header|可导入的 C++ 库头文件]]（importable C++ library headers），可以用 import 声明导入为头文件单元（[[module.import]]）：

```cpp
import <vector>;                // 导入 <vector> 头文件单元
std::vector<int> vi;            // OK
```

表 25 的 C 设施头文件不在其中，`import <cstdio>;` 不保证可行。这些头文件高度依赖宏（`assert` 随 `NDEBUG` 变化，`errno` 本身是宏），不适合作头文件单元。

### 附录 K 的 `_s` 函数（¶10–¶11）

¶10 C 标准附录 K 定义了一批带 `_s` 后缀的边界检查函数，如 `memcpy_s`、`strcpy_s`、`fopen_s`，大多比无后缀的版本多一个表示结果数组大小的参数。包含任何 C++ 头文件后，这些名字是否在全局命名空间声明由实现定义，而且它们都不在 `std` 中。¶11 的表 26 列出了这些名字，它们也受 [[macro.names]] 的限制，程序不能把它们定义成宏。

实践中 MSVC 的 UCRT 提供这些函数（含义与附录 K 不完全相同），glibc 不提供。所以 `std::memcpy_s` 总是错的，`::memcpy_s` 不可移植。

## 包含头文件的规则 [using.headers]

¶1 程序通过 `#include` 指令（[[cpp.include]]）或 import 声明（[[module.import]]）使用库中的实体。

### 顺序与重复包含（¶2）

¶2 翻译单元可以按任意顺序包含库头文件（[[lex.separate]]），每个头文件可以包含多次，效果与包含一次相同。例外是 `<cassert>` 和 `<assert.h>`：每次包含的效果取决于当时 `NDEBUG` 的定义，这与 C 相同。

```cpp run ok
#define NDEBUG
#include <cassert>
void f() { assert(false); }      // 断言被禁用
#undef NDEBUG
#include <cassert>               // 按当前的 NDEBUG 重新定义 assert
void g(int x) { assert(x > 0); } // 断言启用
int main() { f(); g(1); }
```

任意顺序是对实现的要求：标准头文件不能依赖包含的先后（[[res.on.headers#2]] 从实现的角度重申了这一点）。

### 位置和时机（¶3）

¶3 头文件只能在任何声明或定义之外包含；在模块单元中，只能在全局模块片段里包含。并且要在翻译单元第一次引用头文件里声明的实体之前，包含它或导入相应的头文件单元。违反这些规则的程序非良构，不要求诊断（{{ifndr}}）。

```cpp ifndr
namespace N {
#include <vector>    // IFNDR：在声明内部包含标准头文件
}
int main() {}
```

虽然不要求诊断，这类代码实际上几乎总会编译失败，因为头文件里的声明被放进了错误的命名空间。本机 libc++ 报 'operator new' cannot be declared inside a namespace。

更隐蔽的是先用后包含：

```cpp ifndr
#include <string>
std::size_t n = std::strlen("abc");  // IFNDR：在包含 <cstring> 之前使用
#include <cstring>
int main() {}
```

本机 libc++ 上 `<string>` 间接带进了 `strlen` 的声明，这段代码能编译。换一个标准库，或者同一个库的新版本减少了间接包含，它就可能编译失败。

## 标准库模块 [std.modules]

¶1–¶2 标准库提供两个具名模块。模块 **`std`** 导出可导入 C++ 库头文件（表 24）和 C 设施头文件（表 25）提供的、位于命名空间 `std` 中的声明，另外还导出 `<new>` 提供的全局 `operator new` 和 `operator delete`。

¶3 模块 **`std.compat`** 导出 `std` 的全部内容，再加上表 25 各头文件中 `std` 里的声明所对应的全局命名空间声明（[support.c.headers.other] 明确排除的除外），以及 `<stdbit.h>` 和 `<stdckdint.h>` 提供的声明。

¶6 *推荐做法*：实现不应从这两个模块导出其他声明。注 2 提醒，和所有具名模块一样，它们不导出宏（[[module.import]]），例如 `assert`、`errno`、`offsetof`、`va_arg`。

```cpp
import std;
int main() {
  std::vector<int> v{1, 2, 3};
  std::println("{}", v);                 // OK
  ::operator delete(::operator new(1));  // OK：std 也导出全局的 operator new/delete
  // ::printf("x");                      // error：全局 C 名字只由 std.compat 导出
  // assert(v.size() == 3);              // error：模块不导出宏
}
```

本机用 libc++ 自带的 `std.cppm` 预编译模块后验证：这段代码输出 `[1, 2, 3]`。取消注释 `::printf` 一行，Clang 报 missing '#include <_printf.h>'; 'printf' must be declared before it is used；取消注释 `assert` 一行，报 use of undeclared identifier 'assert'。需要 `assert` 时，在 `import std;` 之后再 `#include <cassert>` 即可。

这种混用是安全的，因为 ¶5 规定，库中的一个声明不论是通过包含头文件、导入头文件单元还是导入模块变得可达，都指称同一个实体。`#include <vector>` 和 `import std;` 得到的 `std::vector` 是同一个模板，不违反 ODR。¶4 说明，库中的声明附属于哪个模块是未指明的；注 1 补充，符合标准的实现会保证混用 `#include` 和 `import` 不会造成冲突的附属关系（[[basic.link]]）。工程实践见 [[toolchain/modules-in-practice]]。

!!! history
    C++20 引入模块时，标准库只承诺可导入的头文件（`import <vector>;`），没有具名模块。C++23 通过 [[P2465R3]] 加入了 `std` 和 `std.compat`。

## 独立实现的库 [compliance]

¶1 实现分为宿主实现（hosted）和独立实现（freestanding，[[intro.compliance]]），属于哪一种由实现定义。独立实现可以在没有操作系统的环境中运行，常见于内核和嵌入式开发。

¶2 独立实现提供一组实现定义的头文件，其中至少包括表 27 中的头文件。当前草案的表 27 已经相当长：语言支持类的 `<cstddef>`、`<limits>`、`<new>`、`<exception>`、`<contracts>`、`<coroutine>` 等，工具类的 `<memory>`、`<utility>`、`<tuple>`、`<optional>`、`<variant>`、`<expected>`、`<functional>`，容器和视图 `<array>`、`<inplace_vector>`、`<span>`、`<mdspan>`，以及 `<iterator>`、`<ranges>`、`<algorithm>`、`<string_view>`、`<string>`、`<charconv>`、`<random>`、`<cmath>`、`<atomic>` 等。

¶3 对表 27 中的每个头文件，独立实现至少提供其中声明的独立项（[[freestanding.item]]）。头文件在表中，不等于头文件里的一切都要提供：`<string>` 在表中，但需要动态内存分配的 `std::basic_string` 不是独立项，独立的是 `char_traits` 等部分。哪些是独立项要逐条看 synopsis 的标注。

¶4 [[g:hosted-library-facilities|宿主库设施]]（hosted library facilities）是宿主实现必须提供、独立实现不必提供的那部分库。独立实现可以提供其中实现定义的一个子集（可以为空），提供了的部分，要求与宿主实现相同。

¶5 独立实现还可以为宿主库设施中命名空间作用域的一些函数提供删除定义（[[dcl.fct.def.delete]]）。注 1 说明，这样做能防止程序从独立实现迁移到宿主实现时，重载决议的结果悄悄改变，原理与 [[conventions]] 里的 *freestanding-deleted* 相同。

本机 Clang 可以用 `-ffreestanding` 让 `__STDC_HOSTED__` 为 0，但这只改变编译器的假设，libc++ 并不会因此裁剪成表 27 的子集。

## 链接 [using.linkage]

¶1 标准库实体具有外部链接。除非另有说明，对象和函数具有默认的 `extern "C++"` 语言链接（[[dcl.link]]）。

¶2 C 标准库中具有外部链接的名字是 `extern "C"` 还是 `extern "C++"` 链接，由实现定义；标准建议用 `extern "C++"`。脚注说，声明 C 标准库中的对象或函数，唯一可靠的方式是包含声明它的头文件，尽管 C 标准 7.1.4 允许 C 程序自己声明库函数。

```cpp
extern "C" int printf(const char*, ...);   // 不可移植：语言链接和签名
int main() { printf("hi\n"); }             // 都不保证与库中的声明一致
```

在 C 中，只要签名正确，自己声明标准库函数是合法的。在 C++ 中，`printf` 的语言链接由实现定义，自己写的声明可能与真实的声明不一致，这些名字和签名也保留给实现（[[extern.names]]）。实践中三大实现都用 `extern "C"`，但标准不保证。

¶3 程序需要的、库中定义的对象和函数，在程序启动之前就已包含进程序。

## 思考题

!!! question "思考题 1"
    下面的代码在 libc++ 和 libstdc++ 上都能编译。它可移植吗？

    ```cpp
    #include <iostream>
    int main() { std::string s = "hello"; std::cout << s.size(); }
    ```

<details markdown="1">
<summary>答案</summary>

不可移植。`std::string` 声明在 `<string>` 中，代码没有包含它。[[res.on.headers#1]] 允许 C++ 头文件包含其他 C++ 头文件，两个实现的 `<iostream>` 都碰巧间接提供了 `std::string`，但标准只要求 `<iostream>` 提供它的 synopsis 中的内容，以及它包含的 `<ios>`、`<streambuf>`、`<istream>`、`<ostream>` 的内容，其中都没有 `std::string`。按 [using.headers] ¶3，程序必须在使用 `std::string` 之前包含 `<string>`，否则 IFNDR。实现随时可能减少间接包含，届时这段代码就会编译失败。
</details>

!!! question "思考题 2"
    `import std;` 之后能否使用 `std::size_t`？`::size_t` 呢？`offsetof` 呢？

<details markdown="1">
<summary>答案</summary>

`std::size_t` 可以用：它是 `<cstddef>`（表 25）在 `std` 中提供的声明，¶2 规定模块 `std` 导出它。

`::size_t` 不保证：全局的 C 名字由 `std.compat` 导出（¶3.1），`std` 只额外导出全局的 `operator new` 和 `operator delete`。

`offsetof` 不能用：它是宏（[headers] ¶6），模块不导出宏（¶6 注 2）。需要时 `#include <cstddef>`。
</details>

<details class="fine" markdown="1"><summary>其余条文</summary>

[requirements.general] ¶1：[requirements] 规定适用于整个标准库的要求，第 17–33 章和附录 D 规定各个实体的要求。¶2：以线程之间的交互表述的要求，不适用于只有一个执行线程的程序。¶3：[requirements] 的五个部分分别是 [organization]（库的内容和组织）、[using]（程序怎样使用库）、[[utility.requirements]]（对类型和函数的要求）、[[constraints]]（对程序的约束）、[[conforming]]（对实现的约束）。

[organization.general] ¶1：[contents] 描述库提供的实体和宏，[headers] 列出头文件，[compliance] 规定独立实现的要求。

[contents] ¶1：除非另有说明，库为头文件 synopsis 中描述的实体和宏提供定义。¶2 的脚注还说明，C 标准库头文件（[support.c.headers]）也在全局命名空间定义名字，而 C 设施的 C++ 头文件也可以这样做。

[headers] ¶2 表 24 的完整列表：`<algorithm>` `<any>` `<array>` `<atomic>` `<barrier>` `<bit>` `<bitset>` `<charconv>` `<chrono>` `<compare>` `<complex>` `<concepts>` `<condition_variable>` `<contracts>` `<coroutine>` `<debugging>` `<deque>` `<exception>` `<execution>` `<expected>` `<filesystem>` `<flat_map>` `<flat_set>` `<format>` `<forward_list>` `<fstream>` `<functional>` `<future>` `<generator>` `<hazard_pointer>` `<hive>` `<initializer_list>` `<inplace_vector>` `<iomanip>` `<ios>` `<iosfwd>` `<iostream>` `<istream>` `<iterator>` `<latch>` `<limits>` `<linalg>` `<list>` `<locale>` `<map>` `<mdspan>` `<memory>` `<memory_resource>` `<meta>` `<mutex>` `<new>` `<numbers>` `<numeric>` `<optional>` `<ostream>` `<print>` `<queue>` `<random>` `<ranges>` `<ratio>` `<rcu>` `<regex>` `<scoped_allocator>` `<semaphore>` `<set>` `<shared_mutex>` `<simd>` `<source_location>` `<span>` `<spanstream>` `<sstream>` `<stack>` `<stacktrace>` `<stdexcept>` `<stdfloat>` `<stop_token>` `<streambuf>` `<string>` `<string_view>` `<syncstream>` `<system_error>` `<text_encoding>` `<thread>` `<tuple>` `<type_traits>` `<typeindex>` `<typeinfo>` `<unordered_map>` `<unordered_set>` `<utility>` `<valarray>` `<variant>` `<vector>` `<version>`

[std.modules] ¶4 *推荐做法*：实现应保证声明的模块附属关系不妨碍标准库模块将来的演进或拆分。

[using.overview] ¶1：[using.headers] 描述翻译阶段 4（预处理）的效果，[using.linkage] 描述阶段 8（链接）的效果，见 [[lex.phases]]。

[using.linkage] ¶4：另见替换函数（[[replacement.functions]]）和运行期可更换的处理函数（[[handler.functions]]）。

</details>
