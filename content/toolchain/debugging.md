---
title: 调试 C++ 程序
summary: 在 macOS 上用 lldb 调试 C++：调试信息从哪里来，优化级别怎样影响单步和变量，断点、条件断点、异常断点和 watchpoint，查看 STL 容器，读懂崩溃的调用栈和 core 文件，把 ASan 报告当作调试线索，C++26 的 <debugging>，以及在编译期和运行期打印类型与追踪值。
group: 调试与诊断
status: draft
order: 145
since: c++98
papers: P2546R5, P2810R4, P2286R8
related: intro.abstract, basic.indet, temp.inst, dcl.type.decltype, debugging.utility, support.srcloc.cons, cstdio.syn, toolchain/exception-implementation, toolchain/name-mangling, toolchain/cmake, toolchain/testing, toolchain/reading-compiler-errors, toolchain/static-analysis, topics/undefined-behavior, topics/dangling-references
tags: 工具链, 调试, lldb, sanitizer, 崩溃, source_location
updated: 2026-10-19
---

!!! tldr
    - 调试器靠编译器写出的调试信息（DWARF）把机器指令对应回源码行和变量。`-O0 -g` 下这种对应是一一的；开了优化，按 as-if 规则变量可以不存在、语句可以合并或重排，调试器就显示 `<variable not available>`，单步也会跳行。
    - 常用的 lldb 操作只有十来个：按函数或行号设断点、条件断点、`breakpoint set -E c++` 在抛出处停下、`next`/`step`/`finish`、`bt`、`frame variable`、`watchpoint set variable`。条件断点每次命中都要停下进程求值，本机约 5 毫秒一次，热循环里改用代码中的条件。
    - 崩溃时先看停止原因和故障地址，再顺着调用栈往上看变量。macOS 默认不写 core 文件，可以在 lldb 里用 `process save-core` 保存现场。
    - ASan 报告给出三段调用栈：出错的访问、释放、分配。在 lldb 下运行时它会停在出错的那一帧，`memory history` 可以重新调出后两段。
    - 模板代码的类型可以让编译器在报错时说出来（只声明不定义的类模板、故意失败的 `static_assert`），运行期用 `__PRETTY_FUNCTION__` 或 `std::source_location`；打印调试输出到 `stderr`，并带上文件、行号和函数名。

!!! note "实验环境"
    Apple M2 Pro，macOS 26，Homebrew Clang 23.1.3 加它自带的 libc++ 头文件。Homebrew 的 LLVM 不带 lldb，这里用的是 Xcode 命令行工具里的 lldb（`lldb --version` 输出 `lldb-2100.0.16.4`）。会话用批处理模式录制：`lldb -b -o '命令' -o '命令' ./prog`，程序崩溃时改用 `-k '命令'` 指定崩溃后执行的命令，否则 lldb 会停在交互提示符等待输入。输出中省略了源码上下文和反汇编，删节处用 `...` 表示。本机 `PATH` 里的 Anaconda 带有旧版 `ld`（见 [[toolchain/compilation-pipeline]]），它链接时报 `can't parse dwarf compilation unit info`，生成的程序没有调试信息，实验时把它从 `PATH` 中去掉了。

## 调试信息从哪里来

`-g` 让编译器在目标文件里写入**调试信息**（debug information）：每条机器指令对应源码的哪一行哪一列，每个变量在哪个寄存器或栈槽里、在哪段指令范围内有效，每个类型的成员布局。Linux 和 macOS 上的格式都是 DWARF。调试器没有别的信息来源，它显示的一切都来自这里。

macOS 有一个特别之处：链接器不把 DWARF 复制进可执行文件，只记下各个 `.o` 文件的路径。要得到可以独立保存的调试信息，需要运行 `dsymutil` 生成一个 `.dSYM` 目录。`clang++ -g x.cpp -o x` 这样一步完成编译和链接时，驱动程序会自动调用它；分开编译和链接时不会：

```text
$ clang++ -std=c++2c -g -c loop.cpp && clang++ loop.o -o loop
$ lldb -b -o 'breakpoint set -f loop.cpp -l 7' ./loop
Breakpoint 1: where = loop`total(...) + 60 at loop.cpp:7:10, address = 0x0000000100000524
$ rm loop.o
$ lldb -b -o 'breakpoint set -f loop.cpp -l 7' ./loop
Breakpoint 1: no locations (pending).
WARNING:  Unable to resolve breakpoint to any actual locations.
```

删掉 `.o` 之后，同一个程序就没有了行号信息。构建系统清理中间文件、或者把可执行文件拷到别的机器上时都会遇到这种情况；发布或归档时先运行 `dsymutil loop`，再保存 `loop.dSYM`。

## 优化与调试体验

同一段代码分别用 `-O0` 和 `-O2` 编译，在 `main` 上设断点后连续单步：

```cpp run title="step.cpp" ok
#include <cstdio>

static int square(int x) { return x * x; }

int main(int argc, char**) {
  int a = argc + 1;
  int b = square(a);
  int c = a + b;
  std::printf("%d\n", c);
  int d = c * 2;
  std::printf("%d\n", d);
  return 0;
}
```

`-O0 -g` 下，断点停在第 6 行，每个 `next` 前进一行，所有变量随时可查：

```text
(lldb) breakpoint set -n main
(lldb) run
-> 6   	  int a = argc + 1;
(lldb) frame variable
(int) argc = 1
(int) a = 1
(int) b = 1876944424
(int) c = -1
(int) d = -16
(lldb) next
-> 7   	  int b = square(a);
...
(lldb) next
-> 11  	  std::printf("%d\n", d);
(lldb) frame variable
(int) argc = 1
(int) a = 2
(int) b = 4
(int) c = 6
(int) d = 12
```

第一次 `frame variable` 时 `b`、`c`、`d` 还没有初始化，调试器显示的是这些栈槽里原有的字节。按 [[basic.indet#1]]，这样的自动变量在 C++26 中具有**错误值**（[[g:erroneous-value|erroneous value]]），程序读取它属于错误行为；调试器读内存不受这条规则约束，看到的就是一个碰巧在那里的数。

`-O2 -g` 下，同样的命令得到：

```text
(lldb) run
-> 8   	  int c = a + b;
(lldb) frame variable
(int) argc = 1
(int) c = <variable not available>
(int) d = <variable not available>
(int) a = <no location, value may have been optimized out>
(int) b = <no location, value may have been optimized out>
(lldb) next
-> 9   	  std::printf("%d\n", c);
(lldb) next
-> 10  	  int d = c * 2;
```

断点直接落在第 8 行，第 6、7 行没有对应的指令；`a` 和 `b` 从来没有存在过，`square` 被内联后整个计算只剩下 `argc` 的几条算术指令。标准允许这样做：实现只需要产生与抽象机相同的**可观察行为**（[[g:observable-behavior|observable behavior]]），也就是 volatile 访问、写入文件的数据和交互设备上的输入输出（[[intro.abstract#1]]、[[intro.abstract#8]]）。局部变量的值和语句的执行顺序都不在其中，这就是 [[g:as-if-rule|as-if 规则]]。调试器看到的是真实的机器，不是抽象机。

| 选项 | 本机 `step.cpp` 的表现 | 适合 |
|---|---|---|
| `-O0 -g` | 每行都能停，变量随时可查 | 日常开发、单步排查逻辑 |
| `-Og -g` | 每行都能停；变量在赋值后才可查，之前是 `<variable not available>` | 需要一点优化又要能调试 |
| `-O1 -g`、`-O2 -g` | 从第 8 行开始，`a`、`b` 没有位置 | 发布版本、性能问题、只在优化下出现的问题 |

Clang 23 的 `-Og` 不只是优化级别：`clang++ -g -Og -c step.cpp -###` 显示驱动程序额外传了 `-fextend-variable-liveness=all`，让变量在整个作用域内保持可查。`-O1` 没有这个选项。

!!! tip "建议"
    开发时用 `-O0 -g`，或在项目太慢时用 `-Og -g`；发布版本也带上 `-g`（CMake 的 RelWithDebInfo，见 [[toolchain/cmake]]）。调试信息不进入加载的代码段，不影响运行速度，却决定了线上崩溃时能不能看懂调用栈。只在 `-O2` 下出现、`-O0` 下消失的问题，多数是 UB 或数据竞争，先用 sanitizer 而不是调试器去找（见 [[topics/undefined-behavior]]）。

## 断点、单步与查看变量

| 目的 | lldb 命令 | 简写 |
|---|---|---|
| 在函数上设断点 | `breakpoint set -n total` | `b total` |
| 在某行设断点 | `breakpoint set -f loop.cpp -l 7` | `b loop.cpp:7` |
| 条件断点 | `breakpoint set -f loop.cpp -l 7 -c "i == 500"` | |
| 在抛出异常时停下 | `breakpoint set -E c++` | |
| 运行、继续 | `run`、`continue` | `r`、`c` |
| 单步，不进入调用 | `next` | `n` |
| 单步，进入调用 | `step` | `s` |
| 运行到当前函数返回 | `finish` | |
| 调用栈 | `bt`、`bt 5` | |
| 切换栈帧 | `frame select 2`、`up`、`down` | `f 2` |
| 查看变量 | `frame variable`、`frame variable x s` | `v x` |
| 求值表达式 | `expression -- v.size()` | `p v.size()` |
| 监视内存写入 | `watchpoint set variable p.checksum` | |

`frame variable` 只读调试信息和内存，不执行目标程序的代码；`expression` 会把表达式编译后在目标进程里运行。两者的差别在查看容器时会显现出来。

条件断点适合在大循环里停在某一次迭代：

```cpp run title="loop.cpp" ok
#include <cstdio>
#include <vector>

long total(const std::vector<int>& v) {
  long s = 0;
  for (std::size_t i = 0; i < v.size(); ++i) {
    s += v[i];
  }
  return s;
}

int main() {
  std::vector<int> v(1000);
  for (int i = 0; i < 1000; ++i) v[i] = i % 7;
  std::printf("%ld\n", total(v));
}
```

```text
(lldb) breakpoint set -f loop.cpp -l 7 -c "i == 500"
Breakpoint 1: where = loop`total(...) + 60 at loop.cpp:7:10, address = 0x0000000100000524
(lldb) run
* thread #1, queue = 'com.apple.main-thread', stop reason = breakpoint 1.1
    frame #0: 0x0000000100000524 loop`total(v=size=error: ...) at loop.cpp:7:10
-> 7   	    s += v[i];
(lldb) frame variable i s
(std::size_t) i = 500
(long) s = 1494
```

条件不是在程序里求值的。每次执行到这一行，进程都停下来，lldb 读出 `i`、算出条件，不满足再让进程继续。把循环改成 20000 次、条件改成 `i == 19999`，本机整个会话用了约 104 秒，同一程序断点禁用时约 1 秒，折合每次命中约 5 毫秒。热循环里更快的做法是临时在代码里写 `if (i == 19999) __builtin_debugtrap();`，见下文的 `<debugging>` 一节。

断点行要选在变量已经存在的地方。把条件断点设在 `for (int x : v) s += x;` 这样的单行范围 for 上，本机得到两个断点位置，第一个位于循环变量 `x` 声明之前，条件求值失败，报 `use of undeclared identifier 'x'`。

## 查看 STL 容器

lldb 内置了 libc++ 的**数据格式化器**（data formatter）：它知道 `std::vector`、`std::map`、`std::string` 的内部结构，把它们显示成元素列表，而不是一堆指针。

```cpp run title="stl.cpp" ok
#include <map>
#include <print>
#include <string>
#include <vector>

int sum(const std::vector<int>& v) {
  int s = 0;
  for (int x : v) s += x;
  return s;
}

int main() {
  std::vector<int> v{3, 1, 4, 1, 5};
  std::map<std::string, int> m{{"apple", 3}, {"pear", 5}};
  std::string s = "a string long enough to live on the heap";
  std::println("{}", sum(v) + m.size() + s.size());
}
```

用 Homebrew Clang 23 编译，停在第 16 行：

```text
(lldb) frame variable v m s
(std::vector<int>) v = size=error: Failed to determine start/end of vector data. {}
(std::map<std::string, int>) m = size=2 {
  [0] = (first = "apple", second = 3)
  [1] = (first = "pear", second = 5)
}
(std::string) s = "a string long enough to live on the heap"
```

`map` 和 `string` 正常，`vector` 失败了。`frame variable --raw v` 显示原始的成员：

```text
(std::__1::vector<int, std::__1::allocator<int> >) v = {
  __layout_ = {
    __begin_ = 0x0000000100601bf0
    __end_ = 0x0000000100601c04
     = {
      __capacity_ = 0x0000000100601c04
      ...
```

原因是版本不匹配。格式化器按成员名读取容器内部，libc++ 23 把 `vector` 的三个指针移进了一个 `__layout_` 成员，而 Xcode 的 lldb 是按 Apple 自带的 libc++ 写的。用 Apple Clang（`/usr/bin/clang++`，配套 Apple 的 libc++）编译同一个文件，同一个 lldb 显示：

```text
(lldb) frame variable v
(std::vector<int>) v = size=5 {
  [0] = 3
  [1] = 1
  [2] = 4
  [3] = 1
  [4] = 5
}
(lldb) frame variable v[2]
(int) v[2] = 4
```

格式化器失效时，可以绕过它直接读内存：`parray 5 v.__layout_.__begin_` 打印从这个指针开始的 5 个元素。长远的办法是让调试器和标准库来自同一个工具链，例如用 LLVM 自己的 lldb 配合 Homebrew 的 libc++（本机没有安装，未验证）。

另一个常见的失败是用 `expression` 调用容器的成员函数：

```text
(lldb) p v[2]
error: Couldn't look up symbols:
  $__lldb_func::0x1:0x85c8:_ZNSt3__16vectorIiNS_9allocatorIiEEEixB9nqe210106Em
Hint: The expression tried to call a function that is not present in the target, perhaps because it was optimized out by the compiler.
```

这次是用 Apple Clang 编译的程序，格式化器正常，`frame variable v[2]` 能用，`p v[2]` 却失败。`vector<int>::operator[]` 是类模板的成员函数，按 [[temp.inst#3]]，隐式实例化类模板特化时只实例化成员函数的声明；按 [[temp.inst#4]]，定义要等到在需要定义的上下文中被引用时才实例化。程序里从没调用过 `operator[]`，可执行文件里就没有这个函数，表达式求值器无处可调。同一个程序里 `p v.size()` 成功：`nm` 显示可执行文件里有 `vector<int>::size()` 的函数体（libc++ 内部用到了它），却没有 `operator[]`。`frame variable v[2]` 走的是格式化器提供的合成子元素，不需要调用任何函数。

## 在异常抛出处停下

```cpp run title="exc.cpp" ok
#include <cstdio>
#include <map>
#include <stdexcept>
#include <string>

int parse_port(const std::string& s) {
  return std::stoi(s);                 // 非数字时抛出 invalid_argument
}

int main() {
  std::map<std::string, std::string> cfg{
      {"host", "localhost"}, {"port", "80a"}, {"backup", "x"}};
  for (const auto& [k, v] : cfg) {
    try {
      if (k != "host") std::printf("%s=%d\n", k.c_str(), parse_port(v));
    } catch (const std::exception& e) {
      std::printf("%s: %s\n", k.c_str(), e.what());
    }
  }
}
```

程序输出 `backup: stoi: no conversion` 和 `port=80`。异常已经被接住，等到 `catch` 里才看，抛出点的栈早已回溯掉了。`breakpoint set -E c++` 让 lldb 在异常抛出的那一刻停下：

```text
(lldb) breakpoint set -E c++
Breakpoint 1: no locations (pending).
(lldb) run
2 locations added to breakpoint 1
* thread #1, queue = 'com.apple.main-thread', stop reason = breakpoint 1.1
    frame #0: 0x0000000180810040 libc++abi.dylib`__cxa_throw
(lldb) bt 6
  * frame #0: 0x0000000180810040 libc++abi.dylib`__cxa_throw
    frame #1: 0x00000001807a2618 libc++.1.dylib`std::__1::__throw_invalid_argument[abi:nqe210106](char const*) + 72
    frame #2: 0x00000001807a25a8 libc++.1.dylib`std::__1::(anonymous namespace)::throw_from_string_invalid_arg(...) + 60
    frame #3: 0x0000000180784a98 libc++.1.dylib`std::__1::stoi(...) + 224
    frame #4: 0x0000000100000508 exc`parse_port(s="x") at exc.cpp:7:10
    frame #5: 0x00000001000006ac exc`main at exc.cpp:15:58
```

这个断点设在运行时库的 `__cxa_throw` 和 `__cxa_rethrow` 上（`breakpoint list` 显示 `catch: off throw: on`），每个 `throw` 都编译成对 `__cxa_throw` 的调用，所以无论异常在哪里抛出都会停下。这一机制见 [[toolchain/exception-implementation]]。`frame select 4` 切到自己的代码，就能看到出错的输入是 `"x"`。

lldb 的帮助说明可以用 `-O 类型名` 只在抛出某种类型时停下。本机用 `breakpoint set -E c++ -O std::out_of_range` 试验，程序仍然停在抛出 `invalid_argument` 的地方，这个过滤没有起作用。异常很多的程序里，可以先在 `catch` 子句里设断点确认是哪一种异常，再回到抛出点。

未被接住的异常不需要这个断点。主流实现在找不到 handler 时不回溯栈就调用 `std::terminate`（[[except.handle#8]] 允许这样做），崩溃现场里抛出点的调用栈是完整的。

## 用 watchpoint 找出谁改了内存

一个值莫名其妙地变了，而改它的代码不在你怀疑的地方，这是 watchpoint 的典型用途。**watchpoint** 让处理器在某个地址被写入时触发陷阱，调试器停在写入它的那条指令之后。

```cpp run title="watch.cpp" ub
#include <cstdio>

struct Packet {
  char name[8];
  int  checksum;
};

void set_name(Packet& p, const char* s) {
  int i = 0;
  while (s[i] != '\0') {        // 没有检查 i < 8
    p.name[i] = s[i];
    ++i;
  }
  p.name[i] = '\0';
}

int main() {
  Packet p{};
  p.checksum = 42;
  set_name(p, "sensor-12");
  std::printf("checksum = %d\n", p.checksum);
}
```

程序打印 `checksum = 50`。`"sensor-12"` 有 9 个字符，`p.name[8]` 越过了数组的末尾，这是 UB；在本机的布局下，它恰好写到了紧随其后的 `checksum` 的最低字节（字符 `'2'` 的值是 50）。在赋值之后的第 20 行停下，监视 `checksum`：

```text
(lldb) breakpoint set -f watch.cpp -l 20
(lldb) run
(lldb) watchpoint set variable p.checksum
Watchpoint created: Watchpoint 1: addr = 0x16fdfe580 size = 4 state = enabled type = m
...
(lldb) continue

Watchpoint 1 hit:
old value: 42
new value: 50
* thread #1, queue = 'com.apple.main-thread', stop reason = watchpoint 1
    frame #0: 0x00000001000004d8 watch`set_name(p=0x000000016fdfe578, s="sensor-12") at watch.cpp:12:5
-> 12  	    ++i;
(lldb) frame variable i
(int) i = 8
```

停下时 PC 已经在写入之后的 `++i`，`i == 8` 指出了越界的那一次。watchpoint 用的是处理器的调试寄存器，数量很少，只能监视几个小的地址范围；局部变量所在的栈帧返回后要删掉它，否则会在不相干的写入上触发（本机继续运行时，它在进程退出阶段又命中了一次）。

sanitizer 对这个例子的表现不一。`-fsanitize=address` 没有报告：越界的写入仍然落在 `Packet` 对象之内，ASan 只在对象之间放置红区。`-fsanitize=undefined` 报告了 `runtime error: index 8 out of bounds for type 'char[8]'`，因为编译器知道 `p.name` 的数组类型。如果写入是经过一个 `char*` 指针完成的，UBSan 也看不到，这时 watchpoint 是最直接的工具。

## 读懂崩溃

```cpp run title="crash.cpp" ub
#include <cstdio>

namespace app {
struct Node { int value; Node* next; };

template <class F>
int walk(const Node* n, F f) {
  int s = 0;
  for (; n; n = n->next->next) s += f(n->value);  // 跳两步
  return s;
}
}  // namespace app

int main() {
  app::Node c{3, nullptr}, b{2, &c}, a{1, &b};
  std::printf("%d\n", app::walk(&a, [](int x) { return x * 10; }));
}
```

直接运行，shell 只给出退出码 139（128 + `SIGSEGV` 的 11）。在 lldb 下运行，崩溃时自动执行 `-k` 指定的命令：

```text
$ lldb -b -o run -k bt -k 'frame variable' -k 'frame select 1' -k 'frame variable' -k 'quit 1' ./crash
(lldb) run
* thread #1, queue = 'com.apple.main-thread', stop reason = EXC_BAD_ACCESS (code=1, address=0x8)
    frame #0: 0x00000001000005a0 crash`int app::walk<main::$_0>(n=0x000000016fdfe590, f=(unnamed class) @ 0x000000016fdfe54f) at crash.cpp:9:26
-> 9   	  for (; n; n = n->next->next) s += f(n->value);  // 跳两步
    	                         ^
(lldb) bt
  * frame #0: 0x00000001000005a0 crash`int app::walk<main::$_0>(...) at crash.cpp:9:26
    frame #1: 0x000000010000052c crash`main at crash.cpp:16:23
    frame #2: 0x00000001804afe00 dyld`start + 6992
(lldb) frame variable
(const app::Node *) n = 0x000000016fdfe590
((unnamed class)) f = {}
(int) s = 40
(lldb) frame select 1
(lldb) frame variable
(app::Node) c = {
  value = 3
  next = nullptr
}
...
```

按下面的顺序读：

1. 停止原因。`EXC_BAD_ACCESS` 是 macOS 对非法内存访问的叫法，`address=0x8` 是故障地址。地址很小，几乎总是通过空指针访问成员：`Node` 里 `int value` 占 4 字节，再对齐 4 字节，`next` 的偏移正是 8。
2. 列号。`9:26` 指向第二个 `->next`。第一个 `->` 读到的 `n->next` 是空指针，第二个在它上面再取成员。
3. 变量。`n` 指向 `c`（`frame select 1` 里 `b.next` 的值），`c.next` 是 `nullptr`；`s = 40` 说明前一次迭代处理了 `a`。到这里原因已经清楚：从 `a` 跳两步到了 `c`，再跳两步时中间那个节点不存在。

调用栈里的函数名已经**还原**（demangle）成 C++ 的写法。符号表里存的是修饰过的名字，`nm` 可以看到原样，`c++filt` 把它还原：

```text
$ nm crash | grep walk
0000000100000554 t __ZN3app4walkIZ4mainE3$_0EEiPKNS_4NodeET_
$ nm crash | grep walk | awk '{print $3}' | c++filt
int app::walk<main::$_0>(app::Node const*, main::$_0)
```

`main::$_0` 是 Clang 给 `main` 里那个 lambda 的闭包类型起的内部名字。名字修饰的规则见 [[toolchain/name-mangling]]。

### core 文件

**core 文件**是进程崩溃时内存和寄存器的快照，可以事后用调试器打开。本机的内核设置是 `kern.coredump: 1`、`kern.corefile: /cores/core.%P`，但 shell 默认 `ulimit -c` 为 0。实验结果如下：

- `ulimit -c unlimited` 后运行 `./crash`，退出码 139，`/cores` 里没有文件。
- 用 `codesign` 给程序加上 `com.apple.security.get-task-allow` 权限后重试，仍然没有。
- `/cores` 的属主是 root、权限 755，`touch /cores/x` 报 `Permission denied`。普通用户的进程无法在那里写文件，这很可能是没有 core 的直接原因。修改这个目录的权限需要管理员操作，本机没有做，所以无法确认改了以后能否生成。

在调试器里则可以直接保存现场，事后再打开：

```text
$ lldb -b -o run -k 'process save-core --style stack crash.core' -k 'quit 1' ./crash
$ ls -l crash.core
-rw-------@ 1 weiran  wheel  20480 Oct 19 19:12 crash.core
$ lldb -c crash.core ./crash -o bt -o 'frame variable'
* thread #1, stop reason = ESR_EC_DABORT_EL0 (fault address: 0x8)
  * frame #0: 0x00000001000005a0 crash`int app::walk<main::$_0>(n=0x000000016fdfe570, ...) at crash.cpp:9:26
    frame #1: 0x000000010000052c crash`main at crash.cpp:16:23
    frame #2: 0x00000001804afe00 libsystem_kernel.dylib`host_request_notification + 72
(lldb) frame variable
(const app::Node *) n = 0x000000016fdfe570
((unnamed class)) f = {}
(int) s = 40
```

`--style stack` 只保存栈和寄存器，所以只有 20 KB。代价是系统库的代码不在文件里，lldb 用本机当前的库去对应地址，第 2 帧被错标成了 `host_request_notification`（实际是 `dyld` 的 `start`）。自己代码的帧和变量完整，排查这类问题已经够用；要完整内存用 `--style full`。

## 把 sanitizer 报告当作调试线索

sanitizer 的种类和开销见 [[topics/undefined-behavior]]，各类内存错误的例子见 [[topics/dangling-references]]。这里关注怎样读一份 ASan 报告。

```cpp run title="uaf.cpp" ub
#include <cstdio>
#include <vector>

int main() {
  std::vector<int> v{1, 2, 3};
  int& first = v[0];
  v.push_back(4);              // 容量不够，重新分配
  std::printf("%d\n", first);  // first 指向已释放的旧数组
}
```

用 `-g -O0 -fsanitize=address` 编译后运行，本机第一次得到的报告里每一帧都是 `atos failed to symbolize address`，只有地址没有函数名。macOS 上 ASan 默认调用系统的 `atos` 做符号化，在本机的环境里它失败了。指定 LLVM 自己的符号化工具后正常：

```text
$ ASAN_SYMBOLIZER_PATH=/opt/homebrew/opt/llvm/bin/llvm-symbolizer ./uaf
==56439==ERROR: AddressSanitizer: heap-use-after-free on address 0x6020000000d0 at pc ...
READ of size 4 at 0x6020000000d0 thread T0
    #0 0x000102988aac in main <dir>/uaf.cpp:8:23
    #1 0x0001804afdfc in start (/usr/lib/dyld:arm64e+0x1fdfc)

0x6020000000d0 is located 0 bytes inside of 12-byte region [0x6020000000d0,0x6020000000dc)
freed by thread T0 here:
    #0 0x000102f39854 in _ZdlPv (.../libclang_rt.asan_osx_dynamic.dylib:arm64+0x65854)
    #1 ... in void std::__1::__libcpp_deallocate[abi:nqe230103]<int>(...) .../__new/allocate.h:62:10
    ...
    #6 ... in int* std::__1::vector<int, ...>::__emplace_back_slow_path[abi:nqe230103]<int>(int&&) .../__vector/vector.h:1055:1
    ...
    #10 ... in std::__1::vector<int, ...>::push_back[abi:nqe230103](int&&) .../__vector/vector.h:466:90
    #11 ... in main <dir>/uaf.cpp:7:5

previously allocated by thread T0 here:
    #0 ... in _Znwm (.../libclang_rt.asan_osx_dynamic.dylib:arm64+0x6545c)
    ...
    #6 ... in std::__1::vector<int, ...>::__vallocate[abi:nqe230103](unsigned long) .../__vector/vector.h:607:25
    ...
SUMMARY: AddressSanitizer: heap-use-after-free ...
Shadow bytes around the buggy address:
  0x602000000000: fa fa fd fa fa fa fd fd fa fa fd fd fa fa 00 06
=>0x602000000080: fa fa 00 06 fa fa 00 00 fa fa[fd]fd fa fa fa fa
  0x602000000100: fa fa fa fa fa fa fa fa fa fa fa fa fa fa fa fa
Shadow byte legend (one shadow byte represents 8 application bytes):
  Addressable:           00
  Partially addressable: 01 02 03 04 05 06 07
  Heap left redzone:       fa
  Freed heap region:       fd
  ...
```

报告分四块，按顺序读：

1. 错误类型和访问。`heap-use-after-free`，第 8 行读了 4 字节。这一段告诉你在哪里出错，但原因通常不在这里。
2. 地址在哪块内存里。读的位置在一块 12 字节区域的第 0 字节。12 字节正是 3 个 `int`，也就是 `v` 最初的数组。
3. 释放和分配的调用栈。中间几十帧是 libc++ 的内部函数，从下往上找第一帧自己的代码：释放发生在第 7 行的 `push_back`，分配发生在第 5 行构造 `v` 时（截断的部分里）。三个位置连起来就是完整的故事：第 5 行分配，第 6 行取得引用，第 7 行扩容释放，第 8 行使用。
4. **影子字节**（shadow bytes）。ASan 为每 8 字节应用内存保留 1 字节记录状态：`00` 表示 8 字节都可访问，`01`–`07` 表示只有前几个字节可访问，`fa` 是堆块之间的红区，`fd` 是已释放的内存。方括号标出被访问的那一格：`[fd]fd` 是这块 12 字节区域对应的两格，都已释放。越界访问时，方括号会落在 `fa` 上，旁边的 `00` 和 `0x` 告诉你越过了多少。

在 lldb 下运行带 ASan 的程序，它会在报告时停下，并自动选中出错的那一帧：

```text
(lldb) run
* thread #1, queue = 'com.apple.main-thread', stop reason = Use of deallocated memory
    frame #5: 0x0000000100000ab0 uaf0`main at uaf.cpp:8:23
(lldb) memory history &first
  thread #4294967295: tid = 0x0001, ... name = 'Memory deallocated by Thread 1'
    ...
    frame #11: 0x0000000100000a48 uaf0`main at uaf.cpp:7:5
  thread #4294967295: tid = 0x0001, ... name = 'Memory allocated by Thread 1'
    ...
    frame #10: 0x00000001000009fc uaf0`main at uaf.cpp:5:20
```

`memory history` 把 ASan 记录的释放和分配栈作为两个伪线程显示出来，可以像普通的栈一样逐帧查看。

## 在代码里请求调试器：`<debugging>` {{c++26}}

C++26 新增头文件 `<debugging>`，提供三个函数：`std::breakpoint()`、`std::breakpoint_if_debugging()` 和 `std::is_debugger_present()`（[[P2546R5]]）。

!!! std
    `void breakpoint() noexcept;` The semantics of this function are implementation-defined.

`breakpoint()` 的语义整体由实现定义（[[debugging.utility#1]]），注释说明它的意图是有调试器时暂停程序、交给调试器，没有调试器时程序可能异常终止。`breakpoint_if_debugging()` 等价于先问 `is_debugger_present()` 再调用 `breakpoint()`（¶2）。`is_debugger_present()` 的默认行为由实现定义（¶4），并且是可替换函数（¶5，[[P2810R4]]）：程序可以提供自己的定义，例如从环境变量判断是否在受控的调试环境里。

截至写作时，本机 Clang 23 的 libc++ 还没有实现这个头文件：`#include <debugging>` 报 `'debugging' file not found`；`<version>` 的实现状态注释里 `__cpp_lib_debugging` 被注释掉了，当前草案中这个宏的值是 `202403L`。在它可用之前，macOS 上可以用平台接口写出同样的效果：

```cpp run title="trap.cpp"
#include <cstdio>
#include <sys/sysctl.h>
#include <unistd.h>

// 进程被跟踪时，内核在 p_flag 中设置 P_TRACED
bool debugger_attached() {
  kinfo_proc info{};
  std::size_t size = sizeof info;
  int mib[] = {CTL_KERN, KERN_PROC, KERN_PROC_PID, getpid()};
  if (sysctl(mib, 4, &info, &size, nullptr, 0) != 0) return false;
  return (info.kp_proc.p_flag & P_TRACED) != 0;
}

int main() {
  std::printf("debugger: %d\n", debugger_attached());
  if (debugger_attached()) __builtin_debugtrap();
  std::puts("after trap");
}
```

这段代码只能在 macOS 上编译，所以没有标判定。直接运行时打印 `debugger: 0` 和 `after trap`；在 lldb 下运行时打印 `debugger: 1`，然后停下：

```text
* thread #1, queue = 'com.apple.main-thread', stop reason = EXC_BREAKPOINT (code=1, subcode=0x1000005d0)
    frame #0: 0x00000001000005d4 trap`main at trap.cpp:16:28
(lldb) continue
after trap
Process 58751 exited with status = 0 (0x00000000)
```

`__builtin_debugtrap()` 是 Clang 的内建函数，本机编译成 `brk #0xf000`，lldb 能从它之后继续执行。不要和 `__builtin_trap()` 混淆：它编译成 `brk #0x1`，用于表示不可恢复的错误，编译器把它当作不返回的调用，之后的代码视为不可达，不能指望从那里继续。

## 调试模板：让编译器说出类型

模板代码出问题时，第一步常常是弄清某个 `T`、某个 `decltype` 到底是什么类型。最直接的办法是让编译器在错误信息里把它写出来：

```cpp title="show-type.cpp" error
#include <map>
#include <string>
#include <vector>

template <class T> struct show_type;   // 只声明，不定义

int main() {
  std::map<std::string, std::vector<int>> m;
  auto it = m.begin();
  auto&& [k, v] = *it;
  show_type<decltype(it)>{};           // error: 不完整类型
  show_type<decltype(k)>{};            // error: 不完整类型
}
```

```text
show-type.cpp:11:3: error: implicit instantiation of undefined template 'show_type<std::__map_iterator<std::__tree_iterator<std::__value_type<std::string, std::vector<int>>, std::__tree_node<std::__value_type<std::string, std::vector<int>>, void *> *, long>>>'
show-type.cpp:12:3: error: implicit instantiation of undefined template 'show_type<const std::string>'
```

第二行值得注意：`k` 是结构化绑定，`decltype(k)` 不是 `const std::string&`，而是它的**被引用类型**（referenced type），也就是 `const std::string`（[[dcl.type.decltype#1]]）。这类问题靠读代码很难判断，让编译器打印一次就清楚了。

要看函数模板推导出的 `T`，在函数体里放一个必然失败、又依赖 `T` 的 `static_assert`：

```cpp title="inspect-t.cpp" error
#include <type_traits>

template <class T> void f(T&&) {
  static_assert(std::is_void_v<T>, "inspect T");
}

int main() {
  const int x = 0;
  f(x);
  f(42);
}
```

```text
inspect-t.cpp:4:17: error: static assertion failed due to requirement 'std::is_void_v<const int &>': inspect T
inspect-t.cpp:9:3: note: in instantiation of function template specialization 'f<const int &>' requested here
inspect-t.cpp:4:17: error: static assertion failed due to requirement 'std::is_void_v<int>': inspect T
inspect-t.cpp:10:3: note: in instantiation of function template specialization 'f<int>' requested here
```

条件必须依赖 `T`。写成 `static_assert(false)` 时，每次实例化也会失败，但错误信息里看不到 `T`。读长篇模板错误的一般方法见 [[toolchain/reading-compiler-errors|读懂编译器报错]]。

运行期也可以打印类型。GCC 和 Clang 的 `__PRETTY_FUNCTION__` 包含模板实参，`std::source_location::function_name()` 在 Clang 上给出同样的字符串：

```cpp run title="pretty.cpp" ok
#include <print>
#include <source_location>
#include <string_view>
#include <utility>
#include <vector>

template <class T>
void g(T&&) {
  std::println("{}", __PRETTY_FUNCTION__);
  std::println("{}", std::source_location::current().function_name());
}

template <class T>
constexpr std::string_view type_name() {
  std::string_view s = __PRETTY_FUNCTION__;   // "... [T = ...]"
  auto b = s.find("T = ") + 4;
  return s.substr(b, s.rfind(']') - b);
}

int main() {
  std::vector<int> v;
  g(v);
  g(std::move(v));
  std::println("{}", type_name<decltype(v.begin())>());
}
```

```text
void g(T &&) [T = std::vector<int> &]
void g(T &&) [T = std::vector<int> &]
void g(T &&) [T = std::vector<int>]
void g(T &&) [T = std::vector<int>]
std::__wrap_iter<int *>
```

这两种写法的内容都不受标准约束：`__PRETTY_FUNCTION__` 是编译器扩展，`function_name()` 的值由实现定义（[[support.srcloc.cons#1]]）。`type_name` 这样按 `"T = "` 截取的写法在本机能用，换一个编译器格式就不同，只适合临时调试。

## 打印调试的正确做法

在关键位置打印变量的值，常常比单步更快，尤其是在多线程、时序相关或者只在某台机器上出现的问题里。有三点要做对：输出到哪里，带什么信息，打印本身会不会改变程序。

```cpp run title="trace.cpp" ok
#include <map>
#include <print>
#include <source_location>
#include <string>
#include <vector>

template <class T>
const T& trace(const T& value, const char* expr,
               std::source_location loc =
                   std::source_location::current()) {
  std::println(stderr, "{}:{} [{}] {} = {}", loc.file_name(),
               loc.line(), loc.function_name(), expr, value);
  return value;
}
#define TRACE(e) trace((e), #e)

int parse(const std::string& s) {
  TRACE(s);
  return static_cast<int>(TRACE(s.size()));
}

int main() {
  std::vector<std::string> args{"x", "tab\there", ""};
  std::map<std::string, int> m{{"a", 1}};
  TRACE(args);
  TRACE(m);
  return parse("abc") - 3;
}
```

```text
trace.cpp:25 [int main()] args = ["x", "tab\there", ""]
trace.cpp:26 [int main()] m = {"a": 1}
trace.cpp:18 [int parse(const std::string &)] s = abc
trace.cpp:19 [int parse(const std::string &)] s.size() = 3
```

- 位置信息。`std::source_location::current()` 写在默认实参里，取到的是调用处的位置，而不是 `trace` 自己的位置（[[support.srcloc.cons#2]]）。宏只剩下一个用途：用 `#e` 把表达式的源码变成字符串。
- 容器直接打印。C++23 的 `std::format` 和 `std::print` 能格式化 range（[[P2286R8]]）：`vector` 显示成 `[...]`，`map` 显示成 `{k: v}`，作为元素的字符串带引号并转义，空字符串和制表符一目了然。
- 返回原值。`trace` 返回它的参数，可以包在任何表达式外面而不改变表达式的值，像第 19 行那样。注意它返回引用：`TRACE(s.size())` 的临时对象活到完整表达式结束，在同一个表达式里使用没有问题；写成 `const auto& n = TRACE(s.size());` 就会悬垂（见 [[topics/dangling-references]]）。

输出到 `stderr` 有一个实际的理由：它不带缓冲。程序在打印之后崩溃时，缓冲区里还没写出的内容就丢了：

```cpp run title="lost.cpp" ub
#include <cstdio>
#include <print>

int main(int argc, char**) {
  std::printf("printf: before crash\n");
  std::println(stderr, "stderr: before crash");
  int* volatile p = nullptr;
  if (argc > 0) *p = 1;                  // UB：解引用空指针
}
```

本机把输出接到管道（`./lost 2>&1 | cat`）时，只看到 `stderr: before crash`，`stdout` 那一行留在缓冲区里，随进程一起消失。这时 `stdout` 是全缓冲的，`\n` 不会触发写出。

标准对此也有一个说法。C++26 规定，向宿主环境交付待写入文件的数据的函数返回时，构成一个**可观察检查点**（[[g:observable-checkpoint|observable checkpoint]]，[[cstdio.syn#2]]）；检查点之前的可观察行为，即使之后发生 UB，也必须如实产生（[[intro.abstract#6]]）。写进缓冲区还不算交付，所以只有 `stderr` 的那次输出或 `fflush` 之后的输出受这条保证。详细讨论见 [[topics/undefined-behavior]]。

!!! pitfall "打印改变了程序"
    加一行打印就让问题消失，是 UB 和数据竞争的典型症状。打印是一次不透明的外部调用，它会改变寄存器分配、内联决定和线程之间的时序，原来被优化利用的 UB 可能不再触发。遇到这种情况，不要把打印留下当作修复，改用 sanitizer 去找真正的原因。

## 思考题

!!! question
    `-O2 -g` 下，lldb 在 `step.cpp` 第 8 行停下，`frame variable a` 显示 `<no location, value may have been optimized out>`。这是编译器的缺陷吗？`-O2` 的程序是否仍然符合标准？

<details markdown="1">
<summary>答案</summary>

不是缺陷。[[intro.abstract#1]] 只要求实现模拟抽象机的可观察行为，¶8 列出的可观察行为不包括局部变量的值。`a` 只是计算 `c` 的中间结果，编译器把整个计算折叠成几条指令后，`a` 不再占据任何寄存器或内存，调试信息如实地说它没有位置。程序的输出与 `-O0` 相同，所以符合标准。调试信息本身不是标准的一部分，它能描述到什么程度是实现质量问题；Clang 的 `-Og` 加上 `-fextend-variable-liveness=all` 正是为了改善这一点。
</details>

!!! question
    `p v[2]` 报 `The expression tried to call a function that is not present in the target`，而 `p v.size()` 正常。在程序里加一行什么代码，`p v[2]` 就能用了？为什么？

<details markdown="1">
<summary>答案</summary>

在程序某处实际调用一次 `v[0]`（或任何下标），例如 `std::printf("%d\n", v[0]);`。`vector<int>` 被隐式实例化时，成员函数只实例化声明（[[temp.inst#3]]）；只有在需要定义的上下文中被引用时才实例化定义（[[temp.inst#4]]），可执行文件里才有它的代码。即便如此，`-O2` 下它也可能被全部内联而没有独立的函数体，所以更可靠的是用 `frame variable v[2]`，它通过格式化器读取内存，不调用函数。
</details>

!!! question
    `watch.cpp` 用 ASan 构建没有报告，用 UBSan 构建报告了越界。把 `set_name` 的参数改成 `char* dst`，在函数里写 `dst[i] = s[i]`，调用处传 `p.name`，UBSan 还能报告吗？

<details markdown="1">
<summary>答案</summary>

不能。UBSan 的数组越界检查只在编译器知道数组类型和长度时插入，`-fsanitize=bounds` 处理的是 `p.name[i]` 这种下标表达式。参数变成 `char*` 后，函数内只知道一个指针，`dst[8]` 对编译器来说只是一次指针运算。ASan 也看不到，因为写入仍在 `Packet` 对象之内。行为仍然是 UB（越过了 `char[8]` 的末尾）。这时 watchpoint 是找到写入者的直接办法，另一个办法是用静态分析（见 [[toolchain/static-analysis]]）。
</details>

## 小结

| 问题 | 工具 | 要点 |
|---|---|---|
| 逻辑错误，想看每一步 | `-O0 -g` + `next`/`step`/`frame variable` | 优化后变量和行号会丢失，这是 as-if 规则允许的 |
| 某一次迭代才出错 | 条件断点 | 每次命中约 5 毫秒；热循环里改用代码中的 `if` 加 `__builtin_debugtrap()` |
| 异常从哪里抛出 | `breakpoint set -E c++` | 停在 `__cxa_throw`，往上找自己的帧 |
| 值被意外改写 | `watchpoint set variable` | 停在写入之后；ASan 看不到对象内部的越界 |
| 崩溃 | `bt`、`frame variable`、故障地址 | 小地址多半是空指针访问成员；macOS 默认不写 core，可用 `process save-core` |
| 内存错误 | ASan 报告、`memory history` | 读三段调用栈；本机需设置 `ASAN_SYMBOLIZER_PATH` |
| 容器显示不出来 | `frame variable --raw`、`parray` | lldb 与 libc++ 版本要匹配 |
| 模板里的类型 | 不定义的 `show_type<T>`、依赖 `T` 的 `static_assert` | 运行期用 `__PRETTY_FUNCTION__`、`source_location` |
| 打印调试 | `std::println(stderr, ...)` + `source_location` | `stdout` 的缓冲内容在崩溃时丢失 |

调试器只能告诉你程序做了什么。确认修复之后，把触发问题的输入写成测试，防止它再次出现（见 [[toolchain/testing|测试]]）。
