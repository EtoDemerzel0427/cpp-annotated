---
title: 栈踪迹
summary: C++23 的 <stacktrace> 在运行时捕获当前线程的调用栈：栈踪迹只是调用序列的近似；stacktrace_entry 是轻量的条目句柄，basic_stacktrace 是只读的序列容器，current() 失败时返回空对象而不抛异常。
status: draft
covers: *
since: c++23
papers: P0881R7, P2693R1
related: diagnostics, intro.execution, cpp.predefined, container.rev.reqmts, container.alloc.reqmts, sequence.reqmts, format.string.std, unord.hash
tags: 标准库, stacktrace, 调试, C++23
updated: 2026-10-19
---

!!! tldr
    - `std::stacktrace::current()` 捕获当前线程的调用栈。它是 `noexcept` 的，失败时返回一个空对象。
    - 标准只把栈踪迹定义为调用序列的近似表示：内联、尾调用、缺少调试信息都可能让条目缺失，这些都是符合标准的。
    - `stacktrace_entry` 是一个轻量的句柄，复制和比较都很便宜；查询函数在拿不到信息时返回空字符串或 0，只在内存不足时抛异常。
    - `basic_stacktrace` 是只读的、可指定分配器的序列容器；它的 `<=>` 先比长度，再逐个比较条目。
    - 本机 libc++ 还没有实现 `<stacktrace>`；libstdc++ 和 MSVC STL 已经提供。

{{c++23}} 程序出错时，怎样走到出错位置的往往和错误本身一样有用。C++23 之前，获取调用栈要依赖平台 API（`backtrace()`、`CaptureStackBackTrace`）或第三方库（Boost.Stacktrace、cpptrace）。[[P0881R7]] 把它标准化为 `<stacktrace>`，[[P2693R1]] 又加上了 `std::format` 支持。

## 一个例子

```cpp run title="stacktrace.cpp" cc=gsnapshot flags="-std=c++23 -g -lstdc++exp"
#include <cstdlib>
#include <print>
#include <stacktrace>

[[noreturn]] void fail(const char* msg) {
    auto st = std::stacktrace::current(1);        // 跳过 fail 自身
    std::println(stderr, "fatal: {}\n{}", msg, st);
    for (const auto& e : st)
        if (!e.source_file().empty())
            std::println(stderr, "  at {}:{}", e.source_file(), e.source_line());
    std::abort();
}

void parse(int x) { if (x < 0) fail("negative input"); }

int main() { parse(-1); }
```

`current(1)` 捕获调用栈并跳过最内层的一个条目，也就是 `fail` 自己。整个栈踪迹可以直接交给 `println` 输出，也可以逐个遍历条目，查询源文件和行号。

本机 Clang 23 + libc++ 不提供 `<stacktrace>`（`#include` 报 file not found，`<version>` 里的 `__cpp_lib_stacktrace` 被注释掉），这个例子没有在本机验证。godbolt 按钮用 GCC 打开它；libstdc++ 的实现需要额外链接实验性支持库，当前版本是 `-lstdc++exp`。

## 调用序列与栈踪迹 [stacktrace.general]

¶1 本条款的组件让程序保存当前执行线程的栈踪迹，并在运行时查询其中的信息。

¶2 先在抽象机层面定义要表示的东西：

!!! std
    The *invocation sequence* of the current evaluation x₀ in the current thread of execution is a sequence (x₀, …, xₙ) of evaluations such that, for i ≥ 0, xᵢ is within the function invocation xᵢ₊₁.

当前求值 x₀ 的**调用序列**（invocation sequence，[[g:invocation-sequence]]）是一串求值 (x₀, …, xₙ)，其中每个 xᵢ 都发生在函数调用 xᵢ₊₁ 之内（[[intro.execution]]）。换句话说，从当前正在做的事出发，沿着被谁调用一路回溯，直到线程的初始函数。这个定义只涉及抽象机，与栈帧、寄存器无关。

¶3 **栈踪迹**（stacktrace）是调用序列的近似表示，由若干**栈踪迹条目**（stacktrace entry，[[g:stacktrace-entry]]）组成，每个条目代表其中的一个求值。

只能是近似，因为优化后的机器码与抽象机的调用序列并不一一对应：

- 被内联的函数在机器码里没有自己的栈帧，可能从栈踪迹中消失，有的实现能借助调试信息恢复内联帧；
- `return g();` 经尾调用优化变成跳转后，调用者的栈帧被 `g` 的栈帧取代；
- 省略了帧指针或没有调试信息时，回溯可能不完整，源文件和行号也拿不到；
- 在信号处理函数里或栈已经损坏时，回溯本身可能失败。

用了近似这个词，标准就不必为这些情形作保证，栈踪迹的质量交给实现。

## 头文件概要 [stacktrace.syn]

```cpp
namespace std {
  class stacktrace_entry;
  template<class Allocator> class basic_stacktrace;
  using stacktrace = basic_stacktrace<allocator<stacktrace_entry>>;
  namespace pmr {
    using stacktrace = basic_stacktrace<polymorphic_allocator<stacktrace_entry>>;
  }
  // 以及 swap、to_string、operator<<、formatter、hash
}
```

捕获栈踪迹需要分配内存存放条目，所以 `basic_stacktrace` 可以指定分配器。在需要避开全局堆的场合，例如崩溃处理路径上，可以用 `pmr::stacktrace` 配合预先准备好的缓冲区。

## `stacktrace_entry` [stacktrace.entry]

```cpp
class stacktrace_entry {
public:
  using native_handle_type = implementation-defined;

  constexpr stacktrace_entry() noexcept;
  constexpr stacktrace_entry(const stacktrace_entry& other) noexcept;
  constexpr stacktrace_entry& operator=(const stacktrace_entry& other) noexcept;
  ~stacktrace_entry();

  constexpr native_handle_type native_handle() const noexcept;
  constexpr explicit operator bool() const noexcept;

  string description() const;
  string source_file() const;
  uint_least32_t source_line() const;

  friend constexpr bool operator==(const stacktrace_entry& x, const stacktrace_entry& y) noexcept;
  friend constexpr strong_ordering operator<=>(const stacktrace_entry& x, const stacktrace_entry& y) noexcept;
};
```

¶1（[stacktrace.entry.overview]）`stacktrace_entry` 对象要么为空，要么代表一个栈踪迹条目。它满足 `regular`（[[concepts.object]]）和 `three_way_comparable<strong_ordering>`（[[cmp.concept]]）。

条目被设计成轻量的值，典型实现里就是一个指令地址。复制和比较都很便宜且不抛异常；把地址翻译成函数名、查找调试信息这类昂贵的工作推迟到查询函数里按需进行。

### 构造、观察与比较

- [stacktrace.entry.cons] ¶1：默认构造得到空条目。
- [stacktrace.entry.obs] ¶1–¶2：`native_handle()` 的语义由实现定义；对没有改动过的条目，多次调用返回相同的值。¶3：`operator bool` 在且仅在条目为空时返回 `false`。
- [stacktrace.entry.cmp] ¶1：`x == y` 当且仅当两者代表同一个条目，或者都为空。`<=>` 只规定了返回 `strong_ordering`，顺序由实现决定。

### 查询 [stacktrace.entry.query]

| 函数 | 返回 |
|---|---|
| ¶2 `description()` | 对该求值的描述（通常是函数名），或空字符串 |
| ¶4 `source_file()` | 在词法上包含该求值的源文件的假定名称或实际名称（[[cpp.predefined]]），或空字符串 |
| ¶6 `source_line()` | 0，或一个从 1 开始、与该求值相关的行号 |

¶1 的注 1 说明，查询函数把内存分配错误以外的所有错误都当作没有可用信息，这种情况下不抛异常。¶3、¶5、¶7 规定它们只在内部数据结构或结果字符串无法分配时抛出 `bad_alloc`。

程序没有带调试信息编译、符号被剥离、条目落在没有符号的系统库里，都会导致没有信息。所以 `source_file()` 返回空字符串是正常结果，不是错误。

¶6 还要求文件名和行号一致：如果 `source_file()` 返回的是受 `#line` 指令（[[cpp.line]]）影响的假定名称，`source_line()` 也返回假定行号；返回实际名称时就返回实际行号。

## `basic_stacktrace` [stacktrace.basic]

`basic_stacktrace` 内部只有一个说明专用的成员 `vector<value_type, allocator_type> frames_;`。它的 `iterator` 就是 `const_iterator`，内容不能修改。

¶1（[stacktrace.basic.overview]）它满足可逆容器（[[container.rev.reqmts]]）、分配器感知容器（[[container.alloc.reqmts]]）和序列容器（[[sequence.reqmts]]）的要求，只有两处例外：¶1.1 只支持移动、赋值、交换，以及 const 序列容器上可用的操作，所以没有 `push_back`、`erase`；¶1.2 比较函数的语义与容器要求的不同，见下文。

### 捕获：`current()` [stacktrace.basic.cons]

```cpp
static basic_stacktrace current(const allocator_type& alloc = allocator_type()) noexcept;
static basic_stacktrace current(size_type skip, const allocator_type& alloc = allocator_type()) noexcept;
static basic_stacktrace current(size_type skip, size_type max_depth,
                                const allocator_type& alloc = allocator_type()) noexcept;
```

¶1 `current()` 返回保存了当前线程当前求值的栈踪迹的对象；如果 `frames_` 初始化失败，返回空对象。注 1 说，成功时 `frames_.front()` 大致代表当前求值，`frames_.back()` 大致代表线程的初始函数。

¶2–¶3 `current(skip)` 如同先取得完整的栈踪迹 `t`，再用 `t.begin() + min(n, skip)` 到 `t.end()` 初始化 `frames_`，即跳过最内层的 `skip` 个条目。常用来去掉日志或错误处理函数自身。

¶4–¶6 `current(skip, max_depth)` 再在其后至多保留 `max_depth` 个条目。¶5 是一条加固前置条件（*Hardened preconditions*）：`skip <= skip + max_depth`，即两者相加不能回绕。在加固实现（[[g:hardened-implementation]]）中违反它是契约违反，否则是未定义行为。

如同先取得完整栈踪迹只描述结果。实现可以在回溯时直接跳过前 `skip` 个帧，取够 `max_depth` 个就停下。

`current()` 是 `noexcept` 的，因为栈踪迹最常用在错误处理路径上：抛异常之前、断言失败时、终止处理函数里。在这些地方，获取栈踪迹本身再抛异常会很危险，所以标准规定失败时返回空对象，调用者用 `empty()` 检查即可。

¶7–¶9 默认构造和只传分配器的构造得到空对象。¶10 允许实现加强复制、移动、赋值的异常规格，做法是分配失败时让结果为空（[[res.on.exception.handling]]）。

### 访问元素 [stacktrace.basic.obs]

¶1 迭代器是随机访问迭代器。¶2–¶9 的 `get_allocator`、`begin`/`end` 系列、`empty`、`size`、`max_size` 都转发给 `frames_`。

¶10–¶12 `operator[](frame_no)` 有加固前置条件 `frame_no < size()`，返回 `frames_[frame_no]`，不抛异常。¶13–¶14 `at(frame_no)` 越界时抛出 `out_of_range`。

### 比较 [stacktrace.basic.cmp]

¶1 `x == y` 返回 `equal(x.begin(), x.end(), y.begin(), y.end())`。

¶2 `x <=> y`：长度不同时返回 `x.size() <=> y.size()`，长度相同时逐个条目按字典序比较。

这就是 ¶1.2 所说的语义不同。容器的 `<=>` 是纯字典序，这里先比长度，较短的栈踪迹总排在前面。比较长度是常数时间，多数情况下能更早得出结果。

两个比较运算符都是模板，可以比较分配器不同的栈踪迹，`stacktrace` 和 `pmr::stacktrace` 可以直接比较。

### 输出 [stacktrace.basic.nonmem]

¶2 `to_string(const stacktrace_entry&)` 返回描述该条目的字符串；¶3 建议其中包含 `source_file()` 和 `source_line()` 的信息。¶4 `to_string(const basic_stacktrace&)` 返回描述整个栈踪迹的字符串，注 1 说行数不保证等于 `size()`，实现可能为内联帧多输出几行，也可能省略某些行。¶5–¶6 的两个 `operator<<` 都等价于输出 `to_string(...)`。

[stacktrace.format] ¶1–¶2 `formatter<stacktrace_entry>` 只接受填充、对齐和宽度（[[format.string.std]]），输出 `to_string(se)`；¶3–¶4 `formatter<basic_stacktrace<Allocator>>` 的格式说明必须为空，输出 `to_string(s)`。

[stacktrace.basic.hash] ¶1 `hash<stacktrace_entry>` 和 `hash<basic_stacktrace<Allocator>>` 都是启用的（[[unord.hash]]）。

## 常见误解

!!! pitfall "在信号处理函数里捕获栈踪迹"
    `current()` 要分配内存，`description()` 等要读取调试信息，这些都不是异步信号安全的。在 `SIGSEGV` 处理函数里用 `std::stacktrace` 没有标准保证。用 `pmr::stacktrace` 配合预分配的缓冲区可以减少风险，但符号化仍应推迟到安全的上下文里做。

!!! pitfall "发布构建里的栈踪迹是空的"
    开了优化又剥离了符号的构建里，栈踪迹可能残缺，`source_file()` 可能全为空。这符合标准。需要在生产环境得到有用的栈踪迹，就要保留调试信息，或者保留分离的调试符号文件。

!!! pitfall "解析 `to_string` 的输出"
    `to_string`、`operator<<` 和 `format` 的输出格式完全由实现决定。需要结构化的信息时，遍历条目，分别调用 `description()`、`source_file()`、`source_line()`。

## 思考题

!!! question "思考题 1"
    为什么 `stacktrace_entry` 的复制、比较、`native_handle()` 都是 `constexpr` 的，而 `description()` 不是？

<details markdown="1">
<summary>答案</summary>

条目本质上是一个不透明的句柄，通常是一个地址。复制和比较只操作这个句柄，可以在常量求值中进行，例如对默认构造的空条目。`description()` 等需要在运行时读取符号表或调试信息，并返回动态分配的 `string`，只能在运行期执行。
</details>

!!! question "思考题 2"
    `std::stacktrace::current(0, 0)` 返回什么？`current(1, std::numeric_limits<std::stacktrace::size_type>::max())` 呢？

<details markdown="1">
<summary>答案</summary>

`current(0, 0)` 跳过 0 个、至多保留 0 个，结果为空。

第二个调用中，`size_type` 是无符号类型，`skip + max_depth` 回绕为 0，`skip <= skip + max_depth` 为假，违反了 [[stacktrace.basic.cons#5]] 的加固前置条件：在加固实现中是契约违反，否则是未定义行为。想要不限深度，应当调用 `current(skip)`。
</details>

!!! question "思考题 3"
    在同一个位置先后两次调用 `std::stacktrace::current()`，得到的对象一定相等吗？

<details markdown="1">
<summary>答案</summary>

不一定。捕获可能失败而返回空对象，一次成功一次失败就不相等。源代码里两处不同的调用本身就是不同的求值，最内层条目不同。即使是同一个调用点（例如循环体里）沿同一条调用路径执行两次，实践中通常相等，但标准只把栈踪迹定义为近似表示，没有保证这一点。
</details>
