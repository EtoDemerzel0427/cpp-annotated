---
title: 栈踪迹
summary: C++23 的 <stacktrace>：调用序列（invocation sequence）与"近似表示"的定义；stacktrace_entry（可空、regular、只读查询描述/文件/行号）、basic_stacktrace（只读的、分配器感知的序列容器，current() 带 skip/max_depth 且 noexcept）、比较、to_string 与格式化、哈希；为什么栈踪迹只能是"近似"的，以及实现支持现状（libc++ 尚未提供）。
status: draft
covers: *
since: c++23
papers: P0881R7, P2693R1
related: diagnostics, intro.execution, cpp.predefined, container.rev.reqmts, container.alloc.reqmts, sequence.reqmts, format.string.std, unord.hash
tags: 标准库, stacktrace, 调试, C++23
updated: 2026-10-18
---

{{c++23}} 程序崩溃或出错时，"错误发生在哪里、是怎么走到这里的"往往比错误本身更有价值。在 C++23 之前，获取调用栈只能依赖平台 API（`backtrace()`、`CaptureStackBackTrace`）或第三方库（Boost.Stacktrace、libunwind、cpptrace）。[[P0881R7]] 把这项能力标准化为 `<stacktrace>`，[[P2693R1]] 又为它加上了 `std::format` 支持。

## 调用序列与"近似"（[stacktrace.general]）

¶1：[stacktrace] 描述程序可用来**保存当前执行线程的栈踪迹**、并在运行时查询其信息的组件。

¶2 给出了一个精确的语言层面定义：

!!! std
    The *invocation sequence* of the current evaluation x₀ in the current thread of execution is a sequence (x₀, …, xₙ) of evaluations such that, for i ≥ 0, xᵢ is within the function invocation xᵢ₊₁.

    当前线程中当前求值 x₀ 的**调用序列**（[[g:invocation-sequence]]）是一个求值序列 (x₀, …, xₙ)，其中每个 xᵢ 都位于函数调用 xᵢ₊₁ 之内。

"within the function invocation"指的是 [[intro.execution]] 中的概念：一个求值发生在某次函数调用"之内"，即它是该函数体执行的一部分。所以调用序列就是从"当前正在做的事"沿着"我是被谁调用的"一路回溯到线程的初始函数——这是一个**抽象机**层面的概念，与栈帧、寄存器无关。

¶3 随即承认现实：

!!! std
    A *stacktrace* is an approximate representation of an invocation sequence and consists of stacktrace entries.

    **栈踪迹**是调用序列的一个**近似表示**，由若干**栈踪迹条目**（[[g:stacktrace-entry]]，*stacktrace entry*）组成。一个条目代表栈踪迹中的一个求值。

为什么只能是近似？因为编译器优化会让抽象机的调用序列与机器上真实存在的栈帧不一一对应：

- **内联**：被内联的函数在机器码中没有自己的栈帧，可能从栈踪迹中消失（某些实现能借助调试信息恢复内联帧）；
- **尾调用优化**：`return g();` 被编译成跳转后，调用者的帧被 `g` 的帧取代；
- **省略帧指针**、**没有调试信息**：栈回溯可能不完整，源文件与行号可能拿不到；
- 在信号处理函数、栈已损坏等场合，回溯本身可能失败。

"近似"一词让标准不必对这些情形作任何保证，把质量问题交给实现。

## 头文件概要（[stacktrace.syn]）

```cpp
namespace std {
  class stacktrace_entry;
  template<class Allocator> class basic_stacktrace;
  using stacktrace = basic_stacktrace<allocator<stacktrace_entry>>;
  namespace pmr {
    using stacktrace = basic_stacktrace<polymorphic_allocator<stacktrace_entry>>;
  }
  // swap、to_string、operator<<、formatter、hash 的声明……
}
```

`basic_stacktrace` 是分配器感知的：捕获栈踪迹需要分配内存来存放条目，在内存受限或需要避免全局堆的场合（例如在崩溃处理路径上），可以用 `pmr::stacktrace` 配合预先准备好的单调缓冲区。

## `stacktrace_entry`（[stacktrace.entry]）

### 概述（[stacktrace.entry.overview]）

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

¶1：`stacktrace_entry` 对象要么为**空**，要么代表一个栈踪迹条目并提供查询其信息的操作。它建模 `regular`（[[concepts.object]]）和 `three_way_comparable<strong_ordering>`（[[cmp.concept]]）。

设计意图：条目本身应当是**轻量的值**——典型实现就是一个指令地址（`native_handle_type` 通常是 `uintptr_t` 一类的整数）。复制、比较都廉价且 `noexcept`；昂贵的工作（符号化、查找调试信息）被推迟到查询函数中，按需进行。

### 构造与观察者（[stacktrace.entry.cons]、[stacktrace.entry.obs]）

- cons ¶1：默认构造函数的后置条件是 `*this` 为空；
- obs ¶1：`native_handle()` 的语义**由实现定义**；¶2：对未改变的条目，连续调用返回相同值；
- obs ¶3：`operator bool` 当且仅当 `*this` 为空时返回 `false`。

### 查询（[stacktrace.entry.query]）

¶1 注 1：所有查询函数都把**内存分配错误以外**的错误视为"没有可用信息"，在那种情况下不抛异常。

| 函数 | 返回 | 段落 |
|---|---|---|
| `description()` | 对该求值的描述（通常是函数名，可能带偏移），或空字符串 | ¶2–¶3 |
| `source_file()` | 词法上包含该求值的源文件的**假定名或实际名**（[[cpp.predefined]]），或空字符串 | ¶4–¶5 |
| `source_line()` | 0，或一个从 1 开始的、与该求值词法相关的行号 | ¶6–¶7 |

三个函数都可能抛 `bad_alloc`（内部数据结构或结果字符串无法分配）。

¶6 的一个细节：如果 `source_file()` 返回的是**假定**名称（受 `#line` 指令影响，[[cpp.line]]），那么 `source_line()` 返回假定行号；如果返回的是实际名称，就返回实际行号——二者必须一致。

"没有信息"的典型原因：程序没有用调试信息编译、符号被剥离、条目落在没有符号的系统库里。所以 `source_file()` 返回空字符串是完全正常的结果，不是错误。

### 比较（[stacktrace.entry.cmp]）

¶1：`x == y` 当且仅当 `x` 与 `y` 代表**同一个**栈踪迹条目，或二者都为空。`<=>` 只规定了返回 `strong_ordering`，具体顺序由实现决定（通常按地址）。

## `basic_stacktrace`（[stacktrace.basic]）

### 概述（[stacktrace.basic.overview]）

`basic_stacktrace` 是一个**只读的序列**：说明专用成员是 `vector<value_type, allocator_type> frames_;`，迭代器都是 const 的（`iterator` 就是 `const_iterator`）。

¶1：它满足可逆容器（[[container.rev.reqmts]]）、分配器感知容器（[[container.alloc.reqmts]]）和序列容器（[[sequence.reqmts]]）的要求，除了

- ¶1.1：只支持移动、赋值、交换，以及为 **const 限定的**序列容器定义的操作（不能 `push_back`、`erase`……）；
- ¶1.2：比较函数的语义与容器要求的不同（见下文）。

### 捕获：`current()`（[stacktrace.basic.cons]）

```cpp
static basic_stacktrace current(const allocator_type& alloc = allocator_type()) noexcept;
static basic_stacktrace current(size_type skip, const allocator_type& alloc = allocator_type()) noexcept;
static basic_stacktrace current(size_type skip, size_type max_depth,
                                const allocator_type& alloc = allocator_type()) noexcept;
```

- ¶1：返回一个 `frames_` 存有当前线程中当前求值的栈踪迹的对象；**若 `frames_` 的初始化失败，返回空对象**。注 1：若成功，`frames_.front()` 近似代表当前求值，`frames_.back()` 近似代表当前线程的初始函数。
- ¶2–¶3：`current(skip)`：如同先取得完整的 `t = current(alloc)`，然后从 `t.begin() + min(n, skip)` 到 `t.end()` 初始化 `frames_`——跳过最内层的 `skip` 个条目（通常用来去掉日志/错误处理包装函数自身）。
- ¶4–¶6：`current(skip, max_depth)`：再截取至多 `max_depth` 个条目。¶5 是一个**强化的前置条件**（*Hardened preconditions*）：`skip <= skip + max_depth` 为真——即二者相加不溢出。在强化实现（[[g:hardened-implementation]]）中违反它是契约违反。

**为什么 `current()` 是 `noexcept`？** 栈踪迹最常用于错误处理路径：在抛异常前、在断言失败时、在终止处理函数里。如果获取栈踪迹本身可能抛异常，在这些场合使用它就很危险。所以标准规定失败时返回空对象而不是抛出——调用者用 `empty()` 检查即可。

"如同先取得完整的栈踪迹"（as-if）只描述结果；实现可以（也应当）在回溯时直接跳过前 `skip` 帧、在 `max_depth` 帧后停止，而不是先回溯整个栈。

其余构造与赋值（¶7–¶10）：默认构造与分配器构造得到空对象；复制、带分配器的移动、赋值的规格见概述，¶10 允许实现通过"分配失败时保证 `empty()` 为真"来**加强**这些函数的异常规格（[[res.on.exception.handling]]）。

### 观察者（[stacktrace.basic.obs]）

- ¶1：`const_iterator` 建模 `random_access_iterator` 并满足 *Cpp17RandomAccessIterator*；
- ¶2–¶9：`get_allocator`、`begin`/`end`/`rbegin`/`rend` 及其 `c` 版本、`empty`、`size`、`max_size` 都转发给 `frames_`；
- ¶10–¶12：`operator[](frame_no)`：**强化的前置条件** `frame_no < size()`；返回 `frames_[frame_no]`；不抛异常；
- ¶13–¶14：`at(frame_no)`：越界时抛 `out_of_range`。

### 比较（[stacktrace.basic.cmp]）

- ¶1：`x == y` 返回 `equal(x.begin(), x.end(), y.begin(), y.end())`；
- ¶2：`x <=> y`：若 `x.size() != y.size()`，返回 `x.size() <=> y.size()`；否则返回逐元素的字典序三路比较。

这就是 ¶1.2 所说的"语义不同"：容器的 `<=>` 是纯字典序，而这里**先比长度**——更短的栈踪迹总是排在前面。这样的序对于"把栈踪迹作为 `map` 的键，按调用深度分组统计"之类的用途更自然，而且比较长度是 O(1) 的，能更早得出结果。

注意比较模板对**不同分配器**的 `basic_stacktrace` 也有效（`basic_stacktrace<Allocator2>`），`stacktrace` 与 `pmr::stacktrace` 可以直接比较。

### 修改与非成员函数（[stacktrace.basic.mod]、[stacktrace.basic.nonmem]）

- mod ¶1：`swap` 交换内容；`noexcept` 取决于分配器的传播特征；
- nonmem ¶1：非成员 `swap` 等价于 `a.swap(b)`；
- nonmem ¶2–¶3：`to_string(const stacktrace_entry&)` 返回描述该条目的字符串；*Recommended practice*：应当包含 `source_file()` 与 `source_line()` 的信息；
- nonmem ¶4：`to_string(const basic_stacktrace&)` 返回描述整个栈踪迹的字符串。注 1：行数**不保证**等于 `size()`（实现可能为内联帧输出额外的行，或省略某些行）；
- nonmem ¶5–¶6：两个 `operator<<` 分别等价于 `os << to_string(...)`。

## 格式化与哈希（[stacktrace.format]、[stacktrace.basic.hash]）

- format ¶1–¶2：`formatter<stacktrace_entry>` 的格式说明是 *stacktrace-entry-format-spec*：*fill-and-align*ₒₚₜ *width*ₒₚₜ（[[format.string.std]]）；输出如同把 `to_string(se)` 按填充和宽度要求写入；
- format ¶3–¶4：`formatter<basic_stacktrace<Allocator>>` 的格式说明必须为**空**；输出如同 `to_string(s)`；
- hash ¶1：`hash<stacktrace_entry>` 与 `hash<basic_stacktrace<Allocator>>` 是启用的（[[unord.hash]]）。

## 例子

```cpp run title="stacktrace.cpp" cc=gsnapshot flags="-std=c++23 -g -lstdc++exp"
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

!!! warning "实现状况"
    截至本文编写时，**本机 Clang 23 + libc++ 不提供 `<stacktrace>`**（`#include <stacktrace>` 报"file not found"；`<version>` 中 `__cpp_lib_stacktrace` 处于注释状态），所以上例未能在本机验证。libstdc++ 与 MSVC STL 提供了实现；libstdc++ 的实现需要额外链接其实验性支持库（当前版本为 `-lstdc++exp`，早期版本库名不同）。上面的 godbolt 按钮按此配置用 GCC 打开。

## 陷阱

!!! pitfall "在信号处理函数中使用"
    `current()` 需要分配内存，`description()` 等需要读取调试信息——这些都不是异步信号安全的。在 `SIGSEGV` 处理函数中捕获栈踪迹是常见需求，但用 `std::stacktrace` 做这件事并没有标准保证；可以考虑用 `pmr::stacktrace` 配合预分配缓冲区来减少风险，但符号化仍应推迟到安全的上下文中。

!!! pitfall "发布构建中的空信息"
    `-O2` 加上剥离符号的发布构建中，栈踪迹可能残缺、`source_file()` 可能全为空。这符合标准（"近似"、"没有可用信息"）。需要可用的生产环境栈踪迹，就要保留调试信息（或分离的调试符号文件）。

!!! pitfall "依赖 `to_string` 的格式"
    `to_string`/`operator<<`/`format` 的输出格式完全由实现决定，只有"推荐包含源文件和行号"。不要解析它；需要结构化信息时遍历条目，分别调用 `description()`、`source_file()`、`source_line()`。

## 思考题

!!! question "思考题"
    1. 为什么 `stacktrace_entry` 的复制、比较、`native_handle()` 都是 `constexpr` 的，而 `description()` 不是？
    2. `std::stacktrace::current(0, 0)` 返回什么？`current(1, numeric_limits<std::stacktrace::size_type>::max())` 呢？
    3. 两次在同一位置调用 `std::stacktrace::current()` 得到的对象一定相等吗？

<details markdown="1">
<summary>展开查看答案与解析</summary>

1. 条目本质上是一个不透明的句柄（通常是地址）。复制、比较只操作这个句柄，可以在常量求值中进行（例如对默认构造的空条目）；而 `description()` 等需要在运行时读取符号表或调试信息，并返回动态分配的 `string`，本质上是运行期操作。
2. `current(0, 0)`：跳过 0 个、至多取 0 个，结果为空（`frames_` 从 `t.begin()` 到 `t.begin() + min(n, 0)`）。第二个调用中，`skip + max_depth` 在（无符号的）`size_type` 上回绕为 0，`skip <= skip + max_depth` 为假，违反强化的前置条件（¶5）——在强化实现中是契约违反，否则是 UB。想要"不限深度"应当调用 `current(skip)`。
3. 不一定。首先，捕获可能失败而返回空对象（`current()` 是 `noexcept` 的，失败不抛异常），一次成功、一次失败就不相等。其次，源代码中两处不同的调用本身就是不同的求值，最内层条目不同。即使是同一调用点（例如循环体中）经同一调用路径执行两次，实践中通常相等，但标准只把栈踪迹定义为"近似表示"，并不保证这一点。
</details>

## 小结

!!! summary
    - 调用序列是抽象机概念；栈踪迹是它的**近似**表示，内联、尾调用、缺少调试信息都会造成偏差。
    - `stacktrace_entry`：可为空的轻量句柄，`regular`，查询函数在无信息时返回空串/0，只在分配失败时抛 `bad_alloc`。
    - `basic_stacktrace`：只读的、分配器感知的序列；`current(skip, max_depth)` 为 `noexcept`，失败返回空对象；`operator[]` 与 `current` 的参数有强化的前置条件。
    - 比较先比长度、再按字典序；`to_string`/`format` 的格式由实现决定。
    - libc++ 尚未实现；libstdc++、MSVC STL 已提供。
