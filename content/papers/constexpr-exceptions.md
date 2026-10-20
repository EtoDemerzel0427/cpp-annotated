---
title: 编译期异常（P3068）
summary: C++26 允许在常量求值中抛出并捕获异常，只要异常对象在同一次求值内销毁：此前编译期代码为什么要写两套错误路径，有哪些替代方案，措辞怎样只改 [expr.const] 的两项，标准库异常类型如何跟进，以及 uncaught_exceptions 和 current_exception 为什么又被撤回了 constexpr。
status: draft
order: 40
group: C++26
since: c++26
papers: P3068R6, P1002R1, P0784R7, P3378R2, P3295R3, P3560R2, P2996R13, CWG3059, P3820R1, P3842R2
related: expr.const.core, expr.const.imm, expr.const.init, expr.throw, except.throw, exception, propagation, std.exceptions, meta.reflection.exception, history/constexpr, topics/compile-time-programming, topics/exception-safety, papers/reflection
tags: constexpr, 异常, 常量求值, consteval, C++26, 提案
updated: 2026-10-19
---

!!! tldr
    - C++20 起 constexpr 函数里可以写 `try` 块，但常量求值一走到 `throw` 就失败，`catch` 永远执行不到。编译期代码要么把 `throw` 当作报错手段，要么另写一套返回 `optional` 的错误路径。
    - [[P3068R6]] 允许常量求值中抛出异常，条件是异常对象（连同它的隐式副本）在同一次求值内销毁。这和 C++20 对动态分配的要求是同一条边界：效果不能带出求值。
    - 没有被捕获的异常让整个表达式不是常量表达式，所以原来靠 `throw` 报编译错误的代码不受影响；未定义行为等其他错误也没有变成异常。
    - 措辞只改了 [[expr.const.core]] 的几项；标准库随后把 `std::exception`、`<stdexcept>` 等异常类型标成 `constexpr`（[[P3378R2]]），反射用 `std::meta::exception` 报告错误（[[P3560R2]]）。
    - `uncaught_exceptions` 和 `current_exception` 的 constexpr 会改变试算常量初始化的结果，[[P3842R2]] 又把它们撤回了。本机 Clang 23 尚未实现 P3068，GCC 的状态页把它列在 GCC 16。

## 编译期代码里的错误路径

C++20 的 [[P1002R1]] 允许 constexpr 函数里出现 `try` 块，但没有改变求值的规则：常量求值只要求值到一个 *throw-expression*，整个表达式就不是**核心常量表达式**（[[g:core-constant-expression|core constant expression]]，可以在编译期求值的表达式）。所以 `catch` 子句在编译期永远执行不到。

这条规则有一个有用的副作用：`throw` 可以用作编译期的报错手段。成功的路径照常求值，失败的路径一碰到 `throw` 就让编译失败，诊断指向 `throw` 所在的行。P3068 提到，fmt、CTHASH 等库就用它来改进编译期的错误信息。

```cpp title="throw-as-error.cpp" error
#include <string_view>
consteval int parse_digit(std::string_view s) {
  if (s.size() != 1 || s[0] < '0' || s[0] > '9')
    throw "parse_digit: not a single digit";
  return s[0] - '0';
}
static_assert(parse_digit("7") == 7);   // OK
constexpr int bad = parse_digit("x7");  // error: 求值到 throw
```

本机 Clang 23 报告 constexpr variable 'bad' must be initialized by a constant expression，附注 subexpression not valid in a constant expression，并指向 `throw` 那一行。诊断显示的是 `throw` 所在的源码行，所以操作数里的字符串字面量能起到错误说明的作用。

### 不能恢复，于是写两遍

麻烦出在调用方想处理错误的时候。编译期的 `catch` 不起作用，调用方只能改用另一个不抛异常的函数。于是同一个解析逻辑往往要写成两个版本：

```cpp title="two-paths.cpp" run ok
#include <optional>
#include <string_view>

constexpr std::optional<int> try_parse(std::string_view s) {
  if (s.empty()) return std::nullopt;
  int v = 0;
  for (char c : s) {
    if (c < '0' || c > '9') return std::nullopt;
    v = v * 10 + (c - '0');
  }
  return v;
}

struct parse_error {};
constexpr int parse(std::string_view s) {
  auto r = try_parse(s);
  if (!r) throw parse_error{};
  return *r;
}

constexpr int port_or(std::string_view s, int dflt) {
  auto r = try_parse(s);      // 不能调用 parse 再 catch
  return r ? *r : dflt;
}

static_assert(parse("8080") == 8080);
static_assert(port_or("http", 80) == 80);
int main() { return parse("42") == 42 ? 0 : 1; }
```

本机 Clang 23 在 `-std=c++20` 到 `-std=c++2c` 下都接受并正常运行。`parse` 给运行期的调用者用，`try_parse` 给编译期需要恢复的调用者用，两者的错误条件必须保持一致。P3068 的引言把这概括为：缺少编译期异常，迫使库作者改用 `std::expected`、`std::optional` 这类侵入性更强的报错方式，或者干脆不处理错误。

标准库自己也有同样的问题。C++20 起 `std::vector` 可以在常量求值中使用（[[P0784R7]]），但 `at()` 越界时抛出 `std::out_of_range`，编译期调用者没法捕获它，只能事先检查下标。

### 反射需要报告错误

第三个动机来自静态反射（[[P2996R13]]）。反射的查询函数都是 `consteval` 的，其中很多会失败，比如对 `int` 调用 `members_of`。P3068 写道，在反射提案里，抛出异常是首选的报错方式。反射一方的权衡见下文和 [[papers/reflection|静态反射]]。

## 设计空间

编译期函数报告错误，有四种可能的做法。[[P3560R2]] 在为反射选择报错方式时把它们并列比较过，结论同样适用于一般的 constexpr 代码：

| 做法 | 问题 |
|---|---|
| 返回一个表示无效的值，类似浮点数的 NaN | 只适用于部分返回类型；返回 `vector`、`string_view` 的函数没有自然的无效值 |
| 返回 `std::expected<T, E>` | 每个调用者都要手动解包，语言不提供帮助 |
| 让表达式不是常量表达式 | 即 C++23 的现状，调用者无法恢复 |
| 抛出异常，可以在同一次求值内捕获 | 需要 P3068 |

P3560 指出，在 P3068 之前第四种做法等价于第三种，因为 `throw` 本身就让求值失败。P3068 让两者分开：没被捕获的异常仍然让求值失败，被捕获的异常照常走 `catch`。

运行期反对异常的常见理由，比如二进制体积和运行时开销，在编译期都不存在。P3560 据此认为，编译器即使在关闭异常的模式下，也没有理由拒绝编译期异常。

### 没有提出的东西

P3068 只让 `throw` 产生的异常可以捕获，没有把其他导致求值失败的情形变成异常。读空指针、有符号溢出等核心语言的未定义行为仍然直接让表达式不是常量：

```cpp title="ub-not-exception.cpp" error
constexpr int read(const int* p) { return *p; }
constexpr int try_to_ignore_ub() {
  try { return read(nullptr); }
  catch (...) { return 0; }
}
constexpr int v = try_to_ignore_ub();   // error: 读空指针
```

这是论文自带的例子，本机 Clang 23 报告 dereferencing a null pointer is not allowed in a constant expression。如果未定义行为能被 `catch (...)` 吞掉，编译期检查 UB 的作用就没有了（[[expr.const.core#2]] 的 ¶2.8）。

### 异常为什么不能带出求值

C++20 允许常量求值中分配内存，但要求在同一次求值内释放，称为**瞬时分配**（[[g:transient-allocation|transient allocation]]）。原因是编译期分配的内存不存在于运行期的堆里，程序运行时无法拿着一个指向它的指针继续使用。

异常对象也是这样。抛出异常会初始化一个具有动态存储期的**异常对象**（[[g:exception-object|exception object]]，[[except.throw#3]]），它的存储以未指定的方式分配（[[except.throw#4]]）。P3068 说，它的措辞基本上把异常当作一次分配来对待：异常对象必须在构造它的那次常量求值内销毁，不能保存下来留给运行期。

## 最终设计

### 在求值内抛出并捕获

```cpp title="catch-at-compile-time.cpp" run std=c++2c
#include <string_view>

struct parse_error { std::string_view input; };

constexpr int parse(std::string_view s) {
  if (s.empty()) throw parse_error{s};
  int v = 0;
  for (char c : s) {
    if (c < '0' || c > '9') throw parse_error{s};
    v = v * 10 + (c - '0');
  }
  return v;
}

constexpr int port_or(std::string_view s, int dflt) {
  try { return parse(s); }
  catch (const parse_error&) { return dflt; }
}

static_assert(parse("8080") == 8080);
static_assert(port_or("http", 80) == 80);  // C++26 起成立
int main() { return port_or("x", 0); }
```

按 C++26 的规则，`port_or("http", 80)` 的求值中构造了一个 `parse_error` 异常对象，`catch` 处理完毕后它被销毁，整个表达式是常量表达式。一套代码同时服务于运行期和编译期，`try_parse` 不再需要。

本机 Clang 23 尚未实现 P3068，对第二个 `static_assert` 报告 subexpression not valid in a constant expression，指向 `parse` 里的 `throw`，所以这里不标判定。去掉这一行后程序能编译，运行期的 `port_or("x", 0)` 正常捕获异常并返回 0。

### 没被捕获的异常

如果异常一直传播到求值的最外层，异常对象没有在求值内销毁，表达式就不是核心常量表达式。结果和 C++23 一样是编译错误，只是原因从求值到 `throw` 变成了异常未被捕获。P3068 因此说它不破坏现有代码：原来能编译的程序，求值时不会遇到 `throw`；遇到 `throw` 的程序，原来就不能编译。

求值的边界由常量表达式本身决定，而不是由外围的 `try` 块决定。下面的 `v` 是 constexpr 变量，它的初始化器是一次独立的常量求值：

```cpp title="separate-evaluation.cpp" error
struct my_exception {};
constexpr int just_error() { throw my_exception{}; }

constexpr int foo() {
  try {
    constexpr int v = just_error();  // error: 异常逃出 v 的初始化
    return v;
  } catch (my_exception) { return 0; }
}
```

外面的 `catch` 无论在编译期还是运行期都帮不上忙，`v` 的初始化本身必须是常量表达式。如果把 `constexpr` 去掉，`auto v = just_error();` 就是 `foo` 求值的一部分，异常可以被同一个 `catch` 捕获。这个例子改编自论文。本机 Clang 23 同样报错，不过原因是它不允许 `throw`。

!!! pitfall "立即调用也是一次独立的求值"
    调用 `consteval` 函数构成**立即调用**（[[g:immediate-invocation|immediate invocation]]），如果它不是常量表达式，它就是立即升级表达式，只能出现在可以升级为 `consteval` 的函数里（[[expr.const.imm#2]] 的 ¶2.2、¶3），出现在普通函数里程序就非良构。所以 `consteval` 函数抛出的异常只能在这次立即调用内部捕获。在运行期代码里写 `try { auto x = f_consteval(bad); } catch (...) {}` 不能让程序通过编译：异常逃出了立即调用，这次调用就不是常量表达式。

### exception_ptr 和隐式副本

`std::exception_ptr` 可以延长异常对象的生命期：只要还有 `exception_ptr` 指向它，它就不会被销毁（[[except.throw#4]] 的 ¶4.2）。`std::rethrow_exception` 还可能先复制一份再抛出（[[propagation#11]]）。因此措辞要求，异常对象和这些隐式副本都在求值内销毁：

<div class="compare" markdown="1">

```cpp title="求值内用完：允许"
#include <exception>
constexpr int f() {
  auto p = std::make_exception_ptr(42);
  try {
    std::rethrow_exception(p);
  } catch (int i) {
    return i;
  }
}
static_assert(f() == 42);
```

```cpp title="带出求值：不允许" error
#include <exception>
constexpr std::exception_ptr p =
  std::make_exception_ptr(42);
// error: 异常对象在求值后
// 仍被 p 引用
```

</div>

`make_exception_ptr` 的效果相当于 `throw e;` 后在 `catch (...)` 里取得当前异常（[[propagation#12]]），所以它也构造了一个异常对象。左边按 C++26 的规则是常量表达式；本机 libc++ 的 `make_exception_ptr` 不是 constexpr，左边不能编译，所以不标判定。右边本机 Clang 23 也拒绝，原因是 libc++ 的 `exception_ptr` 不是字面类型，而不是 ¶2.24。

### throw; 和标准库会抛出的表达式

不带操作数的 `throw;` 重新抛出当前正在处理的异常（[[expr.throw#3]]）。P3068 之后出现了一个漏洞：常量求值可以发生在一个运行期的 `catch` 子句里，这时当前正在处理的是运行期的异常。[[CWG3059]] 给出了这个例子：

```cpp title="cwg3059.cpp" error
int main() {
  try {
    throw 0;
  } catch (...) {
    constexpr int x = [] {
      try { throw; }          // error: 当前异常不是在这次求值中构造的
      catch (...) { return 1; }
    }();
    return x;
  }
}
```

CWG3059 作为缺陷报告加了一项限制：`throw;` 只能重新抛出在本次求值中构造的异常。本机 Clang 23 拒绝这段代码，但原因仍是它不允许任何 `throw`。

语言本身也会抛出异常：`dynamic_cast` 到引用失败时抛出 `std::bad_cast`，`typeid` 作用于空指针解引用时抛出 `std::bad_typeid`，数组 *new-expression* 的长度非法时抛出 `std::bad_array_new_length`。P3068 之前，会抛异常的 `dynamic_cast` 和 `typeid` 直接被列为非常量；之后它们可以在编译期抛出并被捕获，前提是异常类型的定义可达，比如包含了 `<typeinfo>` 或 `<new>`。

## 措辞的变化

核心语言的修改全部在 [[expr.const.core#2]] 的禁止清单里，[except] 一章没有改动：抛出、传播、捕获的规则在常量求值中原样适用。

删除了原来的一项：a *throw-expression*（[expr.throw]）。新增了 ¶2.24：

!!! std
    a construction of an exception object, unless the exception object and all of its implicit copies created by invocations of std::current_exception or std::rethrow_exception ([propagation]) are destroyed within the evaluation of E;
    
    构造异常对象不允许，除非异常对象和经 `current_exception`、`rethrow_exception` 产生的所有隐式副本都在 E 的求值之内销毁。

¶2.20 到 ¶2.23 对 *new-expression*、`delete`、`std::allocator` 的要求用的是同一个句式：在 E 的求值之内分配，也在 E 的求值之内释放。

另外两项：

- ¶2.25 来自 [[CWG3059]]：不带操作数的 *throw-expression* 不允许，除非当前处理的异常的异常对象是在 E 的求值中构造的。
- ¶2.30 从原来的 `dynamic_cast`、`typeid` 一项里删掉了 or that would throw an exception；新的 ¶2.31 只禁止异常类型的定义不可达时会抛异常的 `dynamic_cast`、`typeid` 和 *new-expression*。

这几项在 [[expr.const.core]] 的“异常”一节有逐条解释。从 C++11 到 C++26 常量求值逐步放宽的完整过程见 [[history/constexpr]]。

### 标准库的异常类型

异常对象的类型也必须能在常量求值中构造和析构。P3068 自己的库措辞把 `<exception>`、`<new>`、`<typeinfo>` 里的类型标成了 constexpr：`std::exception` 的构造函数、析构函数和 `what()`（[[exception]]），以及 `bad_alloc`、`bad_array_new_length`、`bad_cast`、`bad_typeid`、`bad_exception` 的 `what()`。[[exception#5]] 还规定，常量求值中 `what()` 返回的字符串使用普通字面量编码，这样编译器才能把它显示在诊断里。

`<stdexcept>` 的部分由 [[P3378R2]] 补上：`logic_error`、`runtime_error` 和它们的七个派生类，以及 `bad_optional_access`、`bad_variant_access`、`bad_expected_access`、`format_error`，全部成员都成为 constexpr（[[std.exceptions]]）。论文的理由很直接：`vector::at` 已经可以在编译期调用，它抛出的 `out_of_range` 也应该能在编译期构造和捕获。论文同时建议，以后每篇把某个库组件 constexpr 化的提案，都要把相关的异常类型一起 constexpr 化。

```cpp title="vector-at.cpp" run std=c++2c
#include <stdexcept>
#include <vector>

constexpr int third_or(const std::vector<int>& v, int dflt) {
  try { return v.at(2); }
  catch (const std::out_of_range&) { return dflt; }
}
static_assert(third_or({1, 2, 3}, 0) == 3);
static_assert(third_or({1, 2}, 0) == 0);   // C++26 起成立
int main() {}
```

本机 libc++ 中 `vector::at` 越界时调用的 `__throw_out_of_range` 不是 constexpr，Clang 23 对第二个 `static_assert` 报告 non-constexpr function '__throw_out_of_range' cannot be used in a constant expression。libc++ 的 `std::exception`、`std::out_of_range` 构造函数本机也都不是 constexpr。

P3378 记录了实现上的障碍。以 libc++ 为例：多数异常类型的 `what()` 和析构函数定义在 `.cpp` 文件里，要搬进头文件，同时还要保留共享库里已有的符号以维持 ABI；`logic_error` 内部用引用计数的字符串，靠 `reinterpret_cast` 和原子操作实现，常量求值中只能改为每次复制字符串。

[[P3295R3]] 原本也包含 constexpr `<stdexcept>` 的内容，它的主题是让 `vector`、`string` 和这些异常类型在独立实现（freestanding）中可以在编译期使用。R3 以这些内容已经进入标准为由删掉了这一部分。

## 后续：被撤回的 uncaught_exceptions 和 current_exception

P3068 把 `<exception>` 里几乎所有函数都标成了 constexpr，包括 `std::uncaught_exceptions()` 和 `std::current_exception()`。这两个函数在运行期读取的是当前线程的全局状态，在常量求值中只能看到本次求值内部的异常。[[P3820R1]] 指出，这种差异会悄悄改变已有程序的行为：

```cpp title="trial-evaluation.cpp" run ok
#include <exception>
int i = 1;

int main() {
  try {
    struct S {
      ~S() {
        const int x = std::uncaught_exceptions();
        i = x;
      }
    };
    S s;
    throw 0;
  } catch (...) {
    const bool b = (std::current_exception() != nullptr);
    return i + b;
  }
}
```

`x` 和 `b` 都是 const 整型变量，属于**潜在常量**（[[g:potentially-constant|potentially-constant]]）的变量。编译器要先试着把它们的初始化器当作常量表达式求值，成功就把它们常量初始化（[[expr.const.init#5]]），这时初始化器是显然常量求值的（[[expr.const.defns#1]] 的 ¶1.6）。如果这两个函数是 constexpr 的，试算会成功：常量求值内部没有未捕获的异常，也没有正在处理的异常，于是 `x` 为 0、`b` 为 `false`，程序返回 0。C++23 中试算失败，变量在运行期初始化，程序返回 2。

两篇论文给出了不同的修法：

- P3820 建议去掉 `uncaught_exceptions` 的 constexpr，另加只统计本次常量求值的 `consteval` 版本；`current_exception` 只在当前异常是本次求值中抛出的时候才是常量。
- [[P3842R2]] 采取保守做法：直接去掉这两个函数的 constexpr，以及 `nested_exception`、`throw_with_nested`、`rethrow_if_nested` 的 constexpr，把编译期的支持留到 C++29 再设计。

当前草案采用的是 P3842。[[exception.syn]] 中 `uncaught_exceptions` 和 `current_exception` 不再是 constexpr；`make_exception_ptr` 仍是 constexpr，它的规格改用一个仅供说明的 constexpr 函数 *current-exception*（[[propagation#12]]）。本机 Clang 23 运行上面的程序返回 2，与当前草案一致。

## 反射中的 std::meta::exception

P3068 进入标准后，[[P3560R2]] 把反射查询的失败从不是常量表达式改为抛出 `std::meta::exception`（[[meta.reflection.exception#1]]）。它是单一的异常类型而不是一个层次结构，记录错误说明、出错的函数（以反射值 `from()` 表示）和调用位置 `where()`。它从 `std::exception` 派生，P3560 的理由是与其他标准异常保持一致，其中一些也会在编译期使用。

```cpp title="meta-exception.cpp" std=c++2c
#include <meta>

consteval bool has_members(std::meta::info r) {
  try {
    (void)members_of(r, std::meta::access_context::current());
    return true;
  } catch (const std::meta::exception&) {
    return false;
  }
}
static_assert(!has_members(^^int));
```

`int` 不是类类型也不是命名空间，按 [[meta.reflection.member.queries#5]]，`members_of` 抛出 `meta::exception`，被 `has_members` 捕获。本机 Clang 23 没有 `<meta>` 头文件，也没有实现反射，这个例子未经编译验证。错误说明为什么同时提供 UTF-8 和普通编码两个版本、为什么 `define_aggregate` 的失败仍然不可恢复，见 [[papers/reflection|静态反射]]。

## 编译器支持

| 项目 | 本机 Clang 23.1.3 / libc++ | 其他 |
|---|---|---|
| 常量求值中抛出并捕获（P3068） | 未实现，求值到 `throw` 即报 subexpression not valid in a constant expression | Clang 状态页标为 No；GCC 状态页把 P3068 列在 GCC 16（本机未验证） |
| `__cpp_constexpr_exceptions` | 未定义 | 当前草案为 `202411L` |
| constexpr 异常类型（P3068 库部分、P3378） | `std::exception`、`bad_alloc`、`out_of_range` 的构造函数都不是 constexpr | `__cpp_lib_constexpr_exceptions` 当前草案为 `202502L`，本机未定义 |
| 反射与 `std::meta::exception` | 没有 `<meta>` | GCC 状态页把 P2996、P3560 列在 GCC 16，需要 `-freflection`（本机未验证） |

!!! impl "关闭异常时"
    标准没有关闭异常的模式，但 `-fno-exceptions` 被广泛使用。本机 Clang 23 在 `-fno-exceptions` 下对任何 `throw` 都报告 cannot use 'throw' with exceptions disabled，constexpr 函数也不例外。P3560 认为编译期异常不影响生成的代码，没有理由在这种模式下禁止；实现是否会这样区分，要等实现 P3068 之后才能观察。

## 思考题

!!! question "1. 同一个函数，两个版本"
    下面两个 `static_assert` 在 C++23 和 C++26 中各怎样？
    
    ```cpp
    constexpr int f(bool b) {
      try {
        if (b) throw 1;
        return 0;
      } catch (int) {
        return 1;
      }
    }
    static_assert(f(false) == 0);
    static_assert(f(true) == 1);
    ```

<details markdown="1">
<summary>答案</summary>

C++23 中第一个成立：`try` 块从 C++20 起可以出现在 constexpr 函数里（[[P1002R1]]），只要求值时不经过 `throw` 就没有问题。第二个不是常量表达式，因为求值到了 *throw-expression*。C++26 中两个都成立：异常对象在 `catch` 结束时销毁，满足 [[expr.const.core#2]] 的 ¶2.24。本机 Clang 23 在 `-std=c++20` 和 `-std=c++2c` 下都只拒绝第二个，即 C++23 的行为。

</details>

!!! question "2. 重新抛出之后"
    ```cpp
    constexpr int g() {
      try { throw 1; }
      catch (...) { throw; }
    }
    static_assert(g() == 1);
    ```
    `throw;` 在常量求值中允许吗？这个 `static_assert` 成立吗？

<details markdown="1">
<summary>答案</summary>

`throw;` 本身允许：当前处理的异常是在本次求值中构造的，满足 ¶2.25。但重新抛出的异常没有被任何 `catch` 捕获，传播到了求值之外，异常对象没有在求值内销毁，违反 ¶2.24。所以 `g()` 不是常量表达式，`static_assert` 非良构。`throw;` 不产生新的异常对象，它只是让同一个对象继续传播（[[expr.throw#3]]）。

</details>
