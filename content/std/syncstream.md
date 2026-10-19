---
title: 同步输出流 osyncstream
summary: C++20 的 <syncstream> 让多个线程写同一个流时整段输出不交错：osyncstream 先把字符攒在自己的缓冲区里，在 emit() 或析构时作为一个整体原子地交给目标流缓冲区。
status: done
covers: *
since: c++20
related: iostreams.requirements, iostream.objects, output.streams, stream.buffers, intro.races
tags: 标准库, iostream, 多线程, syncstream
updated: 2026-10-19
---

!!! tldr
    - 每个线程用自己的 `std::osyncstream` 包装共享的流，字符先进私有缓冲区，在 `emit()` 或析构时一次性交给目标，整段输出不会与其他 `osyncstream` 的输出交错。
    - 写向同一个目标的所有 `emit()` 构成一个全序，前一个同步于后一个，效果类似互斥量的解锁和加锁。
    - 默认情况下 `flush()` 和 `std::endl` 只是记下需要刷新，等到下一次 `emit()` 才真正刷新目标；`std::emit_on_flush` 和 `std::flush_emit` 可以改变这一点。
    - `osyncstream` 包装的是流缓冲区，不是流对象，不继承目标流的格式状态。
    - 本机 libc++ 需要 `-fexperimental-library` 才提供 `<syncstream>`。

```cpp title="osyncstream-threads.cpp" run ok
#include <iostream>
#include <syncstream>
#include <thread>
#include <vector>

int main() {
  std::vector<std::jthread> ts;
  for (int id = 0; id < 4; ++id)
    ts.emplace_back([id] {
      for (int i = 0; i < 3; ++i)
        std::osyncstream(std::cout) << "thread " << id << " step " << i << '\n';
    });
}
```

各行的先后取决于线程调度，但每一行都是完整的。如果把 `std::osyncstream(std::cout)` 换成 `std::cout`，程序没有数据竞争（同步状态下的标准流对象允许并发使用，见 [[iostream.objects]]），但不同线程的 `<<` 可以交错，一行里可能混进别的线程的片段。

`<syncstream>` 提供 `basic_syncbuf` 和 `basic_osyncstream` 两个类模板，以及 `syncbuf`、`osyncstream` 和 `w` 前缀的别名。[syncstream.syn] ¶1 说明它的用途：同步多个执行代理（线程等）对同一个流的写入。`basic_syncbuf` 是一个流缓冲区（见 [[stream.buffers]]），`basic_osyncstream` 是持有一个 `basic_syncbuf` 的输出流。

!!! impl "libc++ 需要 `-fexperimental-library`"
    本机 libc++（Clang 23）把 `<syncstream>` 标为实验性。不加 `-fexperimental-library` 时 `std::osyncstream` 不存在，`__cpp_lib_syncbuf` 也没有定义；加上之后本页例子都能编译运行，上面的例子在 `-fsanitize=thread` 下没有报告数据竞争。libc++ 用一张以目标流缓冲区地址为键的全局互斥量表，保证写向同一目标的 `emit` 互斥。

## 攒起来，一次交出 [syncstream.syncbuf.overview]

¶1 写进 `basic_syncbuf` 的字符称为它的**关联输出**（[[g:associated-output|associated output]]），存放在用对象自己的分配器分配的内部缓冲区里。调用 `emit()` 或对象析构时，关联输出被转交给被包装的流缓冲区 `*wrapped`。相对于其他包装同一个流缓冲区的 `basic_syncbuf` 的转交，每次转交都是原子的。

原子性只针对其他 `basic_syncbuf` 的转交。另一个线程如果绕过 `osyncstream` 直接写 `std::cout`，它不受这把锁约束，它的字符可能出现在某次转交的输出中间。

```cpp title="emit-observe.cpp" run ok
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

## `emit` 的保证 [syncstream.syncbuf.members]

¶1 `emit()` 把关联输出原子地转交给 `*wrapped`，使它在输出中成为一段连续的字符。如果自上次 `emit()` 以来调用过 `sync()`，就在转交之后调用 `wrapped->pubsync()`，否则不调用。

¶2 所有向同一个流缓冲区转交字符的 `emit()` 调用，表现为按某个与 happens-before 关系一致的全序执行，每个 `emit()` 同步于（synchronizes with，[[intro.races]]）全序中在它之后的 `emit()`。

这意味着：如果线程 A 的输出出现在线程 B 的输出之前，A 在 `emit()` 之前做的所有内存写入，B 在 `emit()` 之后都能看到。这与同一把互斥量的解锁和加锁配对相同。

¶3 成功之后关联输出为空。¶4 下面三条都成立时返回 `true`，否则返回 `false`：`wrapped` 不为空；所有字符都转交成功；对 `pubsync()` 的调用（如果有）成功。

¶5 `emit()` 可能在持有一把与 `*wrapped` 唯一关联的锁时调用 `*wrapped` 的成员函数。[syncstream.osyncstream.cons] ¶2 的注据此提醒：使用不当可能死锁。例如被包装的流缓冲区在 `overflow` 里又通过一个包装同一目标的 `osyncstream` 写日志，就会试图再次获取同一把锁。

¶6–¶8 其余成员：`get_wrapped()` 返回 `wrapped`，`get_allocator()` 返回分配器的副本，`set_emit_on_sync(b)` 设置下面要讲的 *emit-on-sync* 标志。

## 刷新只是记下 [syncstream.syncbuf.virtuals]

¶1 `sync()` 记录被包装的流缓冲区需要刷新；如果 *emit-on-sync* 标志为真，再调用 `emit()`。注里说明，标志为假（默认）时，真正的刷新推迟到下一次 `emit()`。¶2 调用了 `emit()` 并且它返回 `false` 时，`sync()` 返回 −1，否则返回 0。

所以对 `osyncstream` 调用 `flush()` 或写 `std::endl`，默认不会立即输出任何东西。这是为了保住原子性：如果 `flush` 立即把半段输出交出去，一段输出就被拆开了。标准用一个例子说明 `emit` 与刷新的关系（[syncstream.osyncstream.members] ¶2）：

```cpp title="emit-and-flush.cpp" run ok
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

`<ostream>` 中的三个操纵符（[[output.streams]]）改变这一行为：

| 操纵符 | 流缓冲区是 `basic_syncbuf` 时的效果 |
|---|---|
| `emit_on_flush` | `set_emit_on_sync(true)`：之后每次刷新都立即 `emit` |
| `noemit_on_flush` | `set_emit_on_sync(false)`：恢复默认 |
| `flush_emit` | 先 `flush()`，再立即 `emit()`；失败时置 `badbit` |

对流缓冲区不是 `basic_syncbuf` 的流，前两个没有效果，`flush_emit` 就是 `flush()`。所以泛型代码可以无条件地写 `os << std::flush_emit`。

## 构造、移动和析构 [syncstream.syncbuf.cons]、[syncstream.syncbuf.assign]

¶1–¶2 `basic_syncbuf(obuf, allocator)` 把 `wrapped` 设为 `obuf`，记下分配器。¶3 除了构造互斥量或分配内存时可能抛出，构造函数不抛异常。¶4 内部缓冲区用 `allocator` 的副本分配。

¶5 移动构造之后，`*this` 包装 `other` 原来的目标，`other` 中还没交出的输出转移到 `*this`；`other` 的缓冲区为空，`other.get_wrapped() == nullptr`。¶6 这解除了 `other` 与目标的关联，保证 `other` 析构时不产生输出。

¶7–¶8 析构函数调用 `emit()`，不抛异常：`emit()` 抛出的异常被捕获并忽略。需要处理目标流抛出的异常时，在 `try` 块里显式调用 `emit()`（[syncstream.osyncstream.members] ¶3）。

[syncstream.syncbuf.assign] ¶1 移动赋值先调用 `emit()` 交出自己已有的输出，再从 `rhs` 移动赋值，结果如同从 `rhs` 移动构造。¶2 之后 `rhs.get_wrapped() == nullptr`；分配器在 `propagate_on_container_move_assignment` 为真时随之传播，否则不变。¶4 同样解除 `rhs` 的关联。

## `basic_osyncstream` [syncstream.osyncstream]

`basic_osyncstream` 派生自 `basic_ostream`，持有一个说明专用的 `basic_syncbuf sb`。从 `basic_ostream& os` 构造时，它包装的是 `os.rdbuf()`。所以 `os` 的格式状态（`hex`、`width` 等）不会被继承，`osyncstream` 有自己的一套；反过来，对 `osyncstream` 设置格式也不影响 `os`。

[syncstream.osyncstream.cons] ¶1 构造函数用目标流缓冲区和分配器初始化 `sb`，再用 `addressof(sb)` 初始化基类。¶3 之后 `get_wrapped()` 返回这个目标。¶4–¶5 移动构造先移动基类和 `sb`，再调用 `set_rdbuf(addressof(sb))`；之后 `other.get_wrapped()` 为空。

[syncstream.osyncstream.members] ¶1 成员 `emit()` 表现为非格式化输出函数：构造 sentry 对象之后调用 `sb.emit()`，返回 `false` 时 `setstate(badbit)`。¶4 `get_wrapped()` 返回 `sb.get_wrapped()`。

[syncstream.osyncstream.overview] ¶2–¶3 用两个例子给出了两种典型用法：具名对象用于一个块，临时对象用于一条语句。

```cpp title="osyncstream-usage.cpp" run ok
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

  std::osyncstream(std::cout) << "Hello, " << "World!" << '\n';   // 临时对象：cout 不被刷新
}
```

¶5 的例子说明，可以用 `get_wrapped()` 拿到目标再包装一次。下面输出两行不交错的文字，`Goodbye, Planet!` 在前，因为内层的临时对象先析构、先 emit：

```cpp title="nested-wrap.cpp" run ok
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

## 常见误解

!!! pitfall "把 `osyncstream` 当作长期持有的日志流"
    所有输出都留在它的缓冲区里，直到析构或显式 `emit()` 才出现，`flush` 和 `endl` 默认也不会让输出出现。程序崩溃时这些输出全部丢失，长时间运行时内存持续增长。设计上的用法是一段逻辑输出用一个对象：一条语句用临时对象，或一个块用具名对象。确实需要长期持有时，至少设置 `emit_on_flush`，或在合适的边界调用 `emit()`。

## 思考题

!!! question "思考题 1"
    两个线程各自执行 `std::osyncstream o(std::cout); o << std::hex << x;`，会改变 `std::cout` 的格式标志吗？

<details markdown="1">
<summary>答案</summary>

不会。`osyncstream` 是一个独立的 `basic_ostream` 对象，有自己的 `basic_ios` 状态；它包装的是 `cout.rdbuf()`，不是 `cout` 本身。反过来，`cout` 上已经设置的 `hex` 也不会被 `osyncstream` 继承。
</details>

!!! question "思考题 2"
    线程 A 先给全局变量 `int n = 42;` 赋值，再执行 `std::osyncstream(std::cout) << "ready\n";`。线程 B 随后用 `osyncstream` 向 `std::cout` 写了一行，并且这行出现在 `ready` 之后。B 在这之后读 `n` 是否有数据竞争？

<details markdown="1">
<summary>答案</summary>

没有。两次 `emit()` 都转交到 `cout.rdbuf()`，按 [[syncstream.syncbuf.members#2]]，它们处于一个全序中，A 的 `emit()` 在前，同步于 B 的 `emit()`。于是 A 对 `n` 的写入先发生于 B 的 `emit()` 之后的读取，B 读到 42。不过这种依赖输出顺序的同步很难推理，实际代码里应使用显式的同步手段。
</details>

<details class="fine" markdown="1"><summary>其余条文</summary>

[syncstream.syn]：头文件包含 `<ostream>`，声明 `basic_syncbuf`、它的非成员 `swap`、`basic_osyncstream`，以及别名 `syncbuf`、`wsyncbuf`、`osyncstream`、`wosyncstream`。

[syncstream.syncbuf.assign] ¶3：移动赋值返回 `*this`。¶5–¶6：`swap` 要求 `propagate_on_container_swap` 为真或两者分配器相等，交换两者的状态。[syncstream.syncbuf.special] ¶1：非成员 `swap` 等价于 `a.swap(b)`。

[syncstream.osyncstream.overview] ¶1：`Allocator` 必须满足 *Cpp17Allocator* 要求。

</details>
