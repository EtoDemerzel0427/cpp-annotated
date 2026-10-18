---
title: iostream 要求
summary: 本章所有流组件共用的前提——谁可以调用 imbue（在回调里调用是 UB）、streamoff/streamsize 是什么、pos_type/off_type 不是 streampos/streamoff 时行为由实现定义、charT 的取值范围，以及"并发访问同一个流对象或 streambuf 是数据竞争"这条线程安全总规则与它的 happens-before 保证
status: done
covers: *
related: input.output, iostreams.base, stream.buffers, iostream.objects, syncstream, intro.races, intro.multithread, char.traits, fpos
tags: 标准库, iostream, 线程安全, 数据竞争
updated: 2026-10-18
---

[iostreams.requirements] 很短，但它规定的是本章所有类模板共享的"游戏规则"：模板参数能取什么、两个整数类型的含义、以及多线程下什么情况算数据竞争。后面各节的条文都默认这些前提成立。

## imbue 的限制（[iostream.limits.imbue] ¶1）

¶1 包含两条规定：

1. **库自己不会偷偷换 locale。** 除了 `ios_base::imbue` 和 `basic_filebuf::pubimbue`，本章描述的任何函数都不会去调用 `basic_ios::imbue` 或 `basic_streambuf::imbue`。换句话说，locale 只会在你显式要求时改变，一次 `>>` 或 `<<` 不会中途换掉它。
2. **用户代码不许在"回调位置"调用 imbue。** 如果某个由本章函数调用的用户函数（比如被 `ios_base::register_callback` 注册的回调、被 `num_put` 调用的用户 facet），或者用户覆写的某个本章类的虚函数（比如自定义 streambuf 的 `overflow`），在里面调用了 `imbue`，行为未定义 {{ub}}。

为什么？`basic_streambuf` 的规定允许派生类在两次 `imbue` 之间**缓存** locale 相关的结果（[[streambuf.cons#2]]、[[streambuf.virt.locales#2]]），`basic_filebuf` 还会缓存 `codecvt` facet 用于编码转换。如果在一次读写的中途换掉 locale，这些缓存就和真实状态不一致了。

!!! pitfall "`imbue` 不是线程安全的配置开关"
    `imbue` 应该在流开始使用之前调用一次。对文件流尤其如此：`basic_filebuf::imbue` 在文件不处于开头、且旧 locale 的编码是状态相关时，要求新旧 `codecvt` 相同（[[filebuf.virtuals]] ¶20），否则违反前置条件。

## 两个整数类型：`streamoff` 与 `streamsize`（[stream.types]）

```cpp
using streamoff  = implementation-defined;
using streamsize = implementation-defined;
```

- ¶1 `streamoff`：某个**有符号**基本整数类型，大到能表示操作系统允许的最大文件大小。它是 `seekoff` 的偏移量类型，也是 `fpos` 可以与之互相转换的"距离"类型。
- ¶2 `streamsize`：某个有符号基本整数类型，表示一次 I/O 操作传输的字符数或缓冲区大小——`read`、`write`、`gcount()`、`width()`、`precision()` 用的都是它。脚注说，C 里会用 `size_t`、POSIX 里会用 `ssize_t` 的地方，这里用 `streamsize`。

两者都是有符号的，因为 `-1` 在流接口里普遍用作错误标志（如 `showmanyc()` 返回 −1、`pos_type(off_type(-1))` 表示定位失败）。

```cpp title="stream-types.cpp" ok
#include <ios>
#include <type_traits>

static_assert(std::is_signed_v<std::streamoff>);
static_assert(std::is_signed_v<std::streamsize>);
static_assert(std::is_same_v<std::char_traits<char>::off_type, std::streamoff>);

int main() {}
```

## 定位类型的限制（[iostreams.limits.pos]）

¶1：本章所有以 `charT`、`traits` 为参数的类，只有在 `traits::pos_type` 是 `streampos`、`traits::off_type` 是 `streamoff` 时，才保证按描述工作；用其他类型时行为由实现定义 {{impl}}（除非下文另有说明）。

¶2（注）：标准提供的各个 `char_traits` 特化（[[char.traits]]）都满足这一点：`state_type` 是 `mbstate_t`，`pos_type` 是 `fpos<mbstate_t>`，`off_type` 是 `streamoff`。所以只有自己写 `traits` 时才需要关心这条。`basic_filebuf` 对此要求更严：`pos_type` 不是 `fpos<traits::state_type>` 时行为未定义（[[filebuf.general#4]]）。

¶3：`charT` 是 `char`、`wchar_t` 以及实现定义的其他"字符容器类型"（[[defns.character.container]]）之一。注意这里**没有** `char8_t`、`char16_t`、`char32_t`：标准并不保证 `basic_ostream<char8_t>` 可用——`<iosfwd>` 只给出了 `u8streampos` 之类的 `fpos` 别名，没有 `u8ostream`。在本机 libc++ 上，`std::basic_ostringstream<char16_t> os; os << u"abc";` 连编译都通不过——`basic_ios` 的成员（如 `widen`）要用到 `ctype<char16_t>`，而 [[locale.categories]] 并不要求提供这个特化，libc++ 也没有提供。

## 线程安全（[iostreams.threadsafety]）

### 总规则：同一个对象的并发访问是数据竞争（¶1）

!!! std
    Concurrent access to a stream object, stream buffer object, or C Library stream by multiple threads may result in a data race unless otherwise specified.

    多个线程并发访问同一个流对象、streambuf 或 C 库流（`FILE*`），除非另有规定，可能构成数据竞争——而数据竞争是未定义行为（[[intro.races]]）。

这条规则与容器的规则（[[res.on.data.races]]）同一个思路：库只保证**不同对象**可以被不同线程并发使用，同一个对象需要使用者自己加锁。原因很直接：哪怕是"只读"的 `in >> x`，也会修改 get 区指针、状态位和 `gcount`；而 `os << x` 会修改 put 区指针和 `width`。

"除非另有规定"的例外有两处：

- **同步状态下的标准流对象**（[[iostream.objects.overview#7]]）：只要没调用 `sync_with_stdio(false)`，多个线程并发调用 `cout` 的格式化和非格式化 I/O 函数不构成数据竞争——但字符**可能交错**。
- **`osyncstream`**（[[syncstream]]）：每个线程有自己的 `osyncstream` 对象，它们对同一个被包装 streambuf 的 `emit()` 是原子的。

```cpp title="cout-threads.cpp" ok
#include <iostream>
#include <thread>

int main() {
  // 标准规定：同步状态下的 cout 并发使用不是数据竞争，但两行文字可能交错
  std::thread t1([] { for (int i = 0; i < 3; ++i) std::cout << "aaaa" << i << '\n'; });
  std::thread t2([] { for (int i = 0; i < 3; ++i) std::cout << "bbbb" << i << '\n'; });
  t1.join();
  t2.join();
}
```

!!! impl "libc++ 与 ThreadSanitizer"
    在本机（Clang 23 + libc++）用 `-fsanitize=thread` 运行上例，TSan 会报告 `cout` 内部成员上的数据竞争，位置在格式化输出的 `__pad_and_output` / `__put_character_sequence` 中——它们读写的是 `ios_base` 里的字段宽度等成员（每次格式化输出后的 `width(0)`）。按标准 [[iostream.objects.overview#7]] 这不应构成数据竞争；TSan 的报告反映的是 libc++ 对这些成员的读写没有加同步。写入的值实际上都是 0，通常被视为良性，但如果项目在 CI 里跑 TSan，需要为 `cout` 加锁、改用 `osyncstream`，或者添加抑制规则。

至于用户自己创建的流对象（`ofstream`、`ostringstream`、自定义 streambuf），并发访问同一个对象就是 UB，没有任何例外：

```cpp title="shared-ostringstream.cpp" ub
#include <sstream>
#include <thread>

int main() {
  std::ostringstream log;
  std::thread t1([&] { log << "from t1\n"; });   // UB: 与 t2 并发修改同一个 stringbuf
  std::thread t2([&] { log << "from t2\n"; });
  t1.join();
  t2.join();
}
```

### 通过流传递的值建立同步（¶2）

!!! std
    If one thread makes a library call a that writes a value to a stream and, as a result, another thread reads this value from the stream through a library call b such that this does not result in a data race, then a's write synchronizes with b's read.

¶2 是一条容易被忽略的**正面**保证：如果线程 A 往流里写了一个值，线程 B 通过（不构成数据竞争的）库调用读到了这个值，那么 A 的写**同步于**（synchronizes with，[[intro.races]]）B 的读。于是 A 在写之前做的所有内存修改，对 B 在读之后都可见——流在这里扮演了和互斥量、原子变量类似的角色。

典型场景是两个线程通过管道或同一个文件通信：只要每一端各自用自己的流对象（因而没有数据竞争），读到对方写的数据就意味着建立了 happens-before 关系。这条规定也是 [[syncstream]] 中 `emit()` "全序 + synchronizes with" 保证的背景。

## 思考题

<details markdown="1">
<summary>1. 在自定义 streambuf 的 `overflow` 里调用 <code>this->pubimbue(loc)</code> 会怎样？在 <code>main</code> 里、流还没有用之前调用呢？</summary>

在 `overflow` 里调用是 {{ub}}：`overflow` 是"本章某个类的覆写虚函数"，[[iostream.limits.imbue]] ¶1 明确规定从这类函数里调用 `imbue` 行为未定义。在 `main` 里、使用流之前调用则完全没问题——这正是 `pubimbue` 存在的目的。
</details>

<details markdown="1">
<summary>2. 两个线程分别持有指向<b>同一个</b> <code>filebuf</code> 的两个不同 <code>ostream</code> 对象，各自写入。这是数据竞争吗？</summary>

是。[[iostreams.threadsafety]] ¶1 说的是"流对象**或** streambuf 对象"的并发访问；两个 `ostream` 对象虽然不同，但它们的 `<<` 都会修改同一个 `filebuf` 的 put 区指针。这正是 `osyncstream` 要解决的问题：每个线程用自己的 `syncbuf` 缓冲，最后原子地交给共享的 streambuf。
</details>

## 小结

| 规则 | 出处 | 后果 |
|---|---|---|
| 库函数不会自行调用 `imbue`；回调/覆写的虚函数里调用 `imbue` | [iostream.limits.imbue] ¶1 | 后者 {{ub}} |
| `streamoff`、`streamsize` 是有符号整数类型 | [stream.types] | `-1` 可作错误值 |
| `pos_type`/`off_type` 不是 `streampos`/`streamoff` | [iostreams.limits.pos] ¶1 | {{impl}}（`filebuf` 下 {{ub}}） |
| 并发访问同一个流对象 / streambuf / `FILE*` | [iostreams.threadsafety] ¶1 | 数据竞争 {{ub}}，同步状态的标准流除外 |
| 通过流写入并被另一线程读到 | [iostreams.threadsafety] ¶2 | 写同步于读 |
