---
title: 同步输出流 osyncstream
summary: C++20 的 <syncstream>：basic_syncbuf 把写入的字符攒在自己的缓冲区（关联输出），emit() 或析构时作为一个整体原子地转交给被包装的 streambuf，于是多线程各自用 osyncstream 写同一个流时整段输出不交错；emit 的全序与 synchronizes-with 保证、flush 只是"记下"要刷新（emit_on_flush 改变这一点）、移动会解除包装、emit 持锁期间回调被包装 streambuf 可能死锁；libc++ 需要 -fexperimental-library
status: done
covers: *
since: c++20
related: iostreams.requirements, iostream.objects, output.streams, stream.buffers, intro.races
tags: 标准库, iostream, 多线程, syncstream
updated: 2026-10-18
---

[[iostreams.requirements]] 规定：多个线程并发使用同一个流对象或 streambuf 是数据竞争；同步状态下的 `cout` 虽然不算数据竞争，但输出会以"每次 `<<`"为粒度交错。`<syncstream>`（C++20）解决的正是这个问题：**每个线程用自己的 `osyncstream` 对象**，字符先写进私有缓冲区，最后一次性、原子地交给共享的目标 streambuf。

```cpp title="osyncstream-threads.cpp" ok
#include <iostream>
#include <syncstream>
#include <thread>
#include <vector>

int main() {
  std::vector<std::jthread> ts;
  for (int id = 0; id < 4; ++id)
    ts.emplace_back([id] {
      for (int i = 0; i < 3; ++i)
        std::osyncstream(std::cout) << "thread " << id << " step " << i << '\n';   // 整行原子输出
    });
}
```

行与行的先后顺序取决于调度，但**每一行都是完整的**。

!!! impl "libc++ 需要 `-fexperimental-library`"
    本机 libc++（Clang 23）把 `<syncstream>` 标为实验性：不加 `-fexperimental-library` 时 `std::osyncstream` 不存在、`__cpp_lib_syncbuf` 未定义；加上之后上例正常编译运行，`-fsanitize=thread` 下也没有报告数据竞争。实现用一个全局的、以被包装 streambuf 地址为键的互斥量表来保证"对同一个被包装 streambuf 的 emit 互斥"。

## 概要（[syncstream.syn]）

`<syncstream>` 包含 `<ostream>`，声明 `basic_syncbuf<charT, traits, Allocator>`、其 `swap`、`basic_osyncstream<charT, traits, Allocator>`，以及别名 `syncbuf`、`wsyncbuf`、`osyncstream`、`wosyncstream`。¶1：该头文件提供一种机制，同步多个执行代理（execution agent）对同一个流的写入。

相关的三个操纵符 `emit_on_flush`、`noemit_on_flush`、`flush_emit` 声明在 `<ostream>`（[[output.streams]]）。

## `basic_syncbuf`（[syncstream.syncbuf]）

### 概述（[syncstream.syncbuf.overview]）

```cpp
template<class charT, class traits = char_traits<charT>, class Allocator = allocator<charT>>
class basic_syncbuf : public basic_streambuf<charT, traits> {
public:
  using streambuf_type = basic_streambuf<charT, traits>;
  basic_syncbuf() : basic_syncbuf(nullptr) {}
  explicit basic_syncbuf(streambuf_type* obuf) : basic_syncbuf(obuf, Allocator()) {}
  basic_syncbuf(streambuf_type*, const Allocator&);
  basic_syncbuf(basic_syncbuf&&);
  ~basic_syncbuf();
  basic_syncbuf& operator=(basic_syncbuf&&);
  void swap(basic_syncbuf&);

  bool emit();
  streambuf_type* get_wrapped() const noexcept;
  allocator_type get_allocator() const noexcept;
  void set_emit_on_sync(bool) noexcept;
protected:
  int sync() override;
private:
  streambuf_type* wrapped;      // 说明专用
  bool emit-on-sync{};          // 说明专用
};
```

¶1：`basic_syncbuf` 把写入它的字符数据——称为**关联输出**（associated output，[[g:associated-output]]）——存入用自己的分配器分配的内部缓冲区。关联输出在调用 `emit()` 或对象析构时转交给被包装的流缓冲区 `*wrapped`。**这种转交相对于其他以同一个对象为被包装 streambuf 的 `basic_syncbuf` 的转交是原子的。**

注意原子性的范围：它只针对**其他 `basic_syncbuf`** 的转交。如果另一个线程绕过 `osyncstream`、直接写 `std::cout`，它不受这把锁的约束——同步状态下的 `cout` 不会因此产生数据竞争，但它的字符可能插进某次 emit 输出的中间。

### 构造与析构（[syncstream.syncbuf.cons]）

- `basic_syncbuf(obuf, allocator)`：¶1 `wrapped = obuf`；¶2 后条件 `get_wrapped() == obuf`、`get_allocator() == allocator`；¶3 除了构造互斥量或分配内存时可能抛出，不抛异常；¶4 内部缓冲区用 `allocator` 的副本分配。
- 移动构造：¶5 `get_wrapped()` 取 `other` 原来的值；`other` 中尚未转交的输出转移到 `*this`；之后 `other.pbase() == other.pptr()` 且 `other.get_wrapped() == nullptr`。¶6：这解除了 `other` 与被包装 streambuf 的关联，保证 `other` 析构时不产生输出。
- 析构函数：¶7 调用 `emit()`；¶8 不抛异常——`emit()` 抛出的异常被捕获并忽略。

### 赋值与交换（[syncstream.syncbuf.assign]）

- 移动赋值：¶1 **先调用 `emit()`**（把自己已有的输出交出去），再从 `rhs` 移动赋值，之后的可观察状态如同从 `rhs` 移动构造；¶2 后条件 `rhs.get_wrapped() == nullptr`，分配器在 `propagate_on_container_move_assignment` 为真时被传播，否则不变；¶4 同样解除 `rhs` 的关联。
- `swap`：¶5 前置条件 `propagate_on_container_swap` 为真或两者分配器相等；¶6 交换状态。
- 非成员 `swap`（[syncstream.syncbuf.special]）：等价于 `a.swap(b)`。

### `emit`（[syncstream.syncbuf.members] ¶1–¶5）

- ¶1 *Effects*：把 `*this` 的关联输出**原子地**转交给 `*wrapped`，使之在输出流中成为一段连续的字符序列。**当且仅当**自上次 `emit()` 以来调用过 `sync()`，才调用 `wrapped->pubsync()`。
- ¶2 *Synchronization*：所有向同一个流缓冲区对象转交字符的 `emit()` 调用，表现为按某个与 happens-before 关系一致的**全序**执行，每个 `emit()` **同步于**（synchronizes with，[[intro.races]]）在该全序中位于其后的 `emit()`。
- ¶3 后条件：成功时关联输出为空。
- ¶4 返回 `true` 当且仅当：`wrapped` 非空；所有字符都成功转交；对 `pubsync()` 的调用（如果有）成功。
- ¶5 *Remarks*：可能在持有一把与 `*wrapped` **唯一关联**的锁的情况下调用 `*wrapped` 的成员函数。

¶2 的同步保证意味着：线程 A 的 `emit()` 输出出现在线程 B 的 `emit()` 输出之前，那么 A 在 emit 之前做的所有内存写入对 B 在 emit 之后都可见——与互斥量的 unlock/lock 配对相同。

其他成员：`get_wrapped()` 返回 `wrapped`；`get_allocator()` 返回分配器副本；`set_emit_on_sync(b)` 设置 *emit-on-sync* 标志。

### `sync` 只是"记下"（[syncstream.syncbuf.virtuals]）

```cpp
int sync() override;
```

¶1：**记录**被包装的流缓冲区需要刷新；然后若 *emit-on-sync* 为真，调用 `emit()`。注：*emit-on-sync* 为假（默认）时，真正的刷新被推迟到 `emit()`。¶2：若调用了 `emit()` 且它返回 `false`，返回 −1，否则返回 0。

所以对 `osyncstream` 调用 `flush()`/`<< std::endl` 默认**不会**立即输出任何东西——它只是让下一次 `emit()` 在转交完字符后顺便 `pubsync()` 被包装的 streambuf。这样设计是为了保住原子性：如果 `flush` 立即把半行字符交出去，整段输出就被拆开了。

## `basic_osyncstream`（[syncstream.osyncstream]）

### 概述（[syncstream.osyncstream.overview]）

```cpp
template<class charT, class traits = char_traits<charT>, class Allocator = allocator<charT>>
class basic_osyncstream : public basic_ostream<charT, traits> {
public:
  using syncbuf_type = basic_syncbuf<charT, traits, Allocator>;
  basic_osyncstream(streambuf_type*, const Allocator&);
  explicit basic_osyncstream(streambuf_type* obuf);
  basic_osyncstream(basic_ostream<charT, traits>& os, const Allocator& allocator)
    : basic_osyncstream(os.rdbuf(), allocator) {}
  explicit basic_osyncstream(basic_ostream<charT, traits>& os);
  basic_osyncstream(basic_osyncstream&&) noexcept;
  ~basic_osyncstream();
  basic_osyncstream& operator=(basic_osyncstream&&);
  void emit();
  streambuf_type* get_wrapped() const noexcept;
  syncbuf_type* rdbuf() const noexcept { return const_cast<syncbuf_type*>(addressof(sb)); }
private:
  syncbuf_type sb;     // 说明专用
};
```

¶1：`Allocator` 必须满足 *Cpp17Allocator*。从 `basic_ostream&` 构造时包装的是 `os.rdbuf()`——**包装的是 streambuf，不是流对象**，所以 `os` 的格式状态（`hex`、`width`……）不会被继承，`osyncstream` 有自己的一套。

标准给出的两种用法：

```cpp title="osyncstream-usage.cpp" ok
#include <iostream>
#include <syncstream>

int main() {
  {
    std::osyncstream bout(std::cout);       // 具名对象：用于一个块
    bout << "Hello, ";
    bout << "World!";
    bout << std::endl;                      // 只记下要刷新
    bout << "and more!\n";
  }                                         // 析构：转交全部字符，并刷新 cout

  std::osyncstream(std::cout) << "Hello, " << "World!" << '\n';   // 临时对象：用于一条语句，cout 不被刷新
}
```

### 构造与析构（[syncstream.osyncstream.cons]）

- `basic_osyncstream(buf, allocator)`：¶1 以 `buf` 和 `allocator` 初始化 `sb`，以 `basic_ostream(addressof(sb))` 初始化基类；¶3 后条件 `get_wrapped() == buf`。
- ¶2（注）：`emit()` 可能在持锁期间调用所提供 streambuf 的成员函数，使用不当可能导致**死锁**——例如被包装的 streambuf 的 `overflow` 内部又通过一个包装同一目标的 `osyncstream` 写日志，就会试图再次获取同一把锁。
- 移动构造：¶4 移动基类和 `sb`，然后 `set_rdbuf(addressof(sb))`；¶5 `get_wrapped()` 取 `other` 原来的值，`other.get_wrapped() == nullptr`。

### 成员（[syncstream.osyncstream.members]）

- `emit()`：¶1 表现为非格式化输出函数：构造 sentry 后调用 `sb.emit()`，返回 `false` 时 `setstate(badbit)`。
- `get_wrapped()`：¶4 返回 `sb.get_wrapped()`。

标准用例子说明 `emit` 与刷新的关系（¶2）：

```cpp title="emit-and-flush.cpp" ok
#include <iostream>
#include <syncstream>

int main() {
  std::osyncstream bout(std::cout);
  bout << "Hello," << '\n';      // 不刷新
  bout.emit();                   // 字符转交；cout 未被刷新
  bout << "World!" << std::endl; // 记下刷新；cout 未被刷新
  bout.emit();                   // 字符转交；cout 被刷新
  bout << "Greetings." << '\n';  // 不刷新
}                                // 析构：字符转交；cout 未被刷新
```

¶3：可以把 `emit()` 放进 `try` 块，处理被包装流抛出的异常——析构函数会吞掉异常，显式 `emit()` 则不会。

¶5：`get_wrapped()` 可以用来再包装一次。下面的代码输出**不交错**的两行，而且 `Goodbye, Planet!` 在前，因为内层临时对象先析构、先 emit：

```cpp title="nested-wrap.cpp" ok
#include <iostream>
#include <syncstream>

int main() {
  std::osyncstream bout1(std::cout);
  bout1 << "Hello, ";
  {
    std::osyncstream(bout1.get_wrapped()) << "Goodbye, " << "Planet!" << '\n';
  }
  bout1 << "World!" << '\n';
}
// 输出：
// Goodbye, Planet!
// Hello, World!
```

## 与 `<ostream>` 中三个操纵符的配合

| 操纵符 | 效果（若 `rdbuf()` 是 `basic_syncbuf`） |
|---|---|
| `emit_on_flush` | `set_emit_on_sync(true)`：之后每次 `flush` 都立即 `emit` |
| `noemit_on_flush` | `set_emit_on_sync(false)`：恢复默认 |
| `flush_emit` | 先 `flush()`（记下刷新），再立即 `emit()`；失败置 `badbit` |

对不是 `basic_syncbuf` 的流，前两个无效果，`flush_emit` 只是 `flush()`。所以在泛型代码里可以无条件地写 `os << std::flush_emit`：对 `osyncstream` 它立即交出并刷新，对普通流它就是 `flush`。

```cpp title="emit-observe.cpp" ok
#include <iostream>
#include <sstream>
#include <syncstream>

int main() {
  std::ostringstream sink;
  {
    std::osyncstream out(sink);
    out << "buffered";
    std::cout << "before emit: [" << sink.str() << "]\n";   // []
    out.emit();
    std::cout << "after emit:  [" << sink.str() << "]\n";   // [buffered]
    out << " tail";
  }                                                          // 析构时再 emit 一次
  std::cout << "after scope: [" << sink.str() << "]\n";     // [buffered tail]
}
```

## 思考题

<details markdown="1">
<summary>1. 两个线程各自 <code>std::osyncstream o(std::cout); o &lt;&lt; std::hex &lt;&lt; x;</code>，会影响 <code>std::cout</code> 的格式标志吗？</summary>

不会。`osyncstream` 是一个独立的 `basic_ostream` 对象，有自己的 `basic_ios` 状态；它包装的是 `cout.rdbuf()`，而不是 `cout` 本身（[[syncstream.osyncstream.overview]]）。反过来，`cout` 上已经设置的 `hex` 也不会被 `osyncstream` 继承。
</details>

<details markdown="1">
<summary>2. 把 <code>osyncstream</code> 作为某个对象的长期成员，所有日志都写进它，会有什么问题？</summary>

所有输出都留在它的缓冲区里，直到析构或显式 `emit()` 才出现——程序崩溃时会全部丢失，长时间运行时内存持续增长；`flush`/`endl` 默认也不会让输出出现（[[syncstream.syncbuf.virtuals#1]]）。`osyncstream` 的设计用法是"一段逻辑输出一个对象"（一条语句的临时对象或一个块内的具名对象）；若确实要长期持有，至少设置 `emit_on_flush` 或在合适的边界调用 `emit()`。
</details>

## 小结

- 每个线程用自己的 `osyncstream`，字符先进私有缓冲区（关联输出），`emit()` 或析构时原子地转交给被包装的 streambuf。
- 同一被包装对象上的所有 `emit()` 构成全序，并依次 synchronizes-with。
- `flush`/`endl` 默认只记下"需要刷新"，在下一次 `emit()` 时一并执行；`emit_on_flush`、`flush_emit` 改变这一行为。
- 移动构造/赋值解除源对象的包装；析构吞掉 `emit()` 的异常，需要处理异常时显式调用 `emit()`。
- 绕过 `osyncstream` 直接写同一目标的代码不受其锁保护。
