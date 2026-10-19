---
title: iostream 要求
summary: 第 31 章所有流组件共用的前提：多个线程访问同一个流是数据竞争（同步状态的标准流除外）；回调里调用 imbue 是未定义行为；streamoff、streamsize 是有符号整数；charT 只保证 char 和 wchar_t。
status: done
covers: *
related: input.output, iostreams.base, stream.buffers, iostream.objects, syncstream, intro.races, intro.multithread, char.traits, fpos
tags: 标准库, iostream, 线程安全, 数据竞争
updated: 2026-10-19
---

!!! tldr
    - 多个线程同时使用同一个流对象、流缓冲区或 `FILE*`，除非另有规定，就是数据竞争。标准流 `cout` 等在与 stdio 同步时是例外，但输出的字符仍可能交错。
    - 一个线程通过流写入、另一个线程读到了这个值，写同步于读，此前的内存修改对读的一方可见。
    - 库函数不会自己改变流的 locale；在库调用的回调或重写的虚函数里调用 `imbue` 是未定义行为。
    - `streamoff`（文件偏移）和 `streamsize`（传输的字符数）都是有符号整数类型，`-1` 在流接口里常作错误值。
    - 流模板只保证对 `char` 和 `wchar_t` 可用；`basic_ostringstream<char16_t>` 在 libc++ 上无法使用。

## 线程安全 [iostreams.threadsafety]

### 同一个流不能被多个线程同时使用（¶1）

```cpp run ub
#include <sstream>
#include <thread>

int main() {
  std::ostringstream log;
  std::thread t1([&] { log << "from t1\n"; });   // UB: 与 t2 同时修改同一个 stringbuf
  std::thread t2([&] { log << "from t2\n"; });
  t1.join();
  t2.join();
}
```

`log << "..."` 看似只是追加几个字符，实际上要修改流缓冲区的 put 区指针、可能重新分配内部的字符串，还要读写流的 `width`。两个线程同时这样做，就是**数据竞争**（data race，[[intro.races]]）：两个线程冲突地访问同一内存位置，彼此之间没有先后关系。数据竞争是未定义行为。本机用 `-fsanitize=thread` 运行，ThreadSanitizer 报告了数据竞争。

!!! std
    Concurrent access to a stream object, stream buffer object, or C Library stream by multiple threads may result in a data race unless otherwise specified.

¶1 多个线程并发访问同一个流对象、流缓冲区对象或 C 库流（`FILE*`），除非另有规定，可能构成数据竞争。这与容器的规则（[[res.on.data.races]]）是同一个思路：库保证不同的对象可以由不同线程同时使用，同一个对象要由使用者自己加锁。

即使是只读的 `in >> x` 也不例外，它要移动 get 区指针、修改状态位和 `gcount()` 的值。两个线程分别持有两个不同的 `ostream`、但指向同一个 `filebuf`，同样是数据竞争，因为两边的 `<<` 都在修改那个 `filebuf`。

另有规定的例外有两处：

- 标准流对象在与 stdio 同步时（默认就是同步的），多个线程并发调用它们的格式化和非格式化输入输出函数不是数据竞争（[[iostream.objects.overview#7]]）。字符仍然可能交错。
- `osyncstream`（[[syncstream]]）：每个线程用自己的 `osyncstream` 对象，最后把整段内容原子地交给共享的流缓冲区。

```cpp run ok
#include <iostream>
#include <thread>

int main() {
  // 同步状态下并发使用 cout 不是数据竞争，但两行文字可能交错
  std::thread t1([] { for (int i = 0; i < 3; ++i) std::cout << "aaaa" << i << '\n'; });
  std::thread t2([] { for (int i = 0; i < 3; ++i) std::cout << "bbbb" << i << '\n'; });
  t1.join();
  t2.join();
}
```

!!! impl "libc++ 与 ThreadSanitizer"
    本机（Clang 23 + libc++）用 `-fsanitize=thread` 运行上例，TSan 报告了 `cout` 内部的数据竞争：一处是 `fill()` 第一次调用时惰性设置填充字符，一处是每次输出后执行的 `width(0)`。按标准这个程序没有数据竞争，报告反映的是 libc++ 读写这些成员时没有加同步。在 CI 里跑 TSan 的项目，可以给 `cout` 加锁、改用 `osyncstream`，或者添加抑制规则。

### 通过流传递的值建立同步（¶2）

¶2 如果线程 A 的一次库调用向流写入了一个值，线程 B 通过另一次不构成数据竞争的库调用读到了这个值，那么 A 的写**同步于**（synchronizes with）B 的读。按 [[intro.races]]，A 在写之前做的所有内存修改，B 在读之后都能看到。流在这里起的作用和互斥量、原子变量一样。

典型场景是两个线程经由管道或同一个文件通信，每一端用自己的流对象，所以没有数据竞争。读到对方写的数据，就说明两者之间建立了先后关系。`osyncstream` 的 `emit()` 提供的同步保证也以此为背景。

## imbue 的限制 [iostream.limits.imbue]

¶1 这一段有两条规定。

第一，除了 `ios_base::imbue` 和 `basic_filebuf::pubimbue`，本章的函数都不会调用 `basic_ios::imbue` 或 `basic_streambuf::imbue`。也就是说，流的 locale 只在程序显式要求时才改变，一次 `>>` 或 `<<` 不会中途换掉它。

第二，如果本章某个函数调用的用户函数，或者用户在本章某个类的派生类里重写的虚函数，调用了 `imbue`，行为未定义。前者如用 `register_callback` 注册的回调、`num_put` 调用的用户 facet，后者如自定义 streambuf 的 `overflow`。

原因是缓存。[[streambuf.virt.locales#2]] 允许流缓冲区在两次 `imbue` 之间缓存 locale 相关的结果，`basic_filebuf` 还会缓存 `codecvt` facet 用于编码转换。在一次读写的中途换掉 locale，这些缓存就与实际状态不一致了。

`imbue` 应当在开始使用流之前调用。对文件流尤其如此：如果文件不在开头、旧 locale 的编码又是状态相关的，`basic_filebuf::imbue` 要求新旧 `codecvt` facet 相同，否则违反前置条件（[[filebuf.virtuals#20]]）。

## `streamoff` 与 `streamsize` [stream.types]

```cpp run ok
#include <ios>
#include <type_traits>

static_assert(std::is_signed_v<std::streamoff>);
static_assert(std::is_signed_v<std::streamsize>);
static_assert(std::is_same_v<std::char_traits<char>::off_type, std::streamoff>);

int main() {}
```

¶1 `streamoff` 是某个有符号基本整数类型，大到能表示操作系统允许的最大文件大小。它是 `seekoff` 的偏移量类型，也是 `fpos` 可以与之互相转换的距离类型。脚注说它通常是 `long long`，本机 libc++ 正是如此。

¶2 `streamsize` 也是某个有符号基本整数类型，表示一次输入输出传输的字符数或缓冲区大小。`read`、`write`、`gcount()`、`width()`、`precision()` 都用它。C 里用 `size_t`、POSIX 里用 `ssize_t` 的地方，这里用 `streamsize`。

两者都有符号，因为流接口普遍用 `-1` 表示错误，例如 `showmanyc()` 返回 `-1`，`pos_type(off_type(-1))` 表示定位失败。

## 字符类型与定位类型 [iostreams.limits.pos]

¶3 本章的模板参数 `charT` 取 `char`、`wchar_t`，或者实现定义的其他字符容器类型（[[defns.character.container]]）。`char8_t`、`char16_t`、`char32_t` 不在保证之列：`<iosfwd>` 只给了 `u8streampos` 之类的位置类型别名，没有 `u8ostream`。

本机 libc++ 上，`std::basic_ostringstream<char16_t> os;` 能编译，但 `os << u"abc";` 不能。插入字符串要用 `widen` 等成员，它们依赖 `ctype<char16_t>`，而 [[locale.categories]] 不要求提供这个特化，libc++ 也没有提供。

¶1 本章以 `charT`、`traits` 为参数的类，只有在 `traits::pos_type` 是 `streampos`、`traits::off_type` 是 `streamoff` 时，才保证按描述工作。用其他类型时，除非另有说明，行为由实现定义。

¶2 这只影响自己写 `traits` 的人。注 1 指出，标准的各个 `char_traits` 特化（[[char.traits]]）的 `state_type` 都是 `mbstate_t`，`pos_type` 都是 `fpos<mbstate_t>`，`off_type` 都是 `streamoff`。`basic_filebuf` 的要求更严：`pos_type` 不是 `fpos<traits::state_type>` 时行为未定义（[[filebuf.general#4]]）。

## 思考题

!!! question "思考题 1"
    在自定义 streambuf 的 `overflow` 里调用 `this->pubimbue(loc)` 会怎样？在 `main` 里、流还没有用过时调用呢？

<details markdown="1">
<summary>答案</summary>

`overflow` 是本章某个类的虚函数的重写，[[iostream.limits.imbue#1]] 规定从这样的函数里调用 `imbue` 行为未定义。在 `main` 里、使用流之前调用则没有问题，`pubimbue` 本来就是为此提供的。
</details>

!!! question "思考题 2"
    两个线程各有一个 `std::ofstream`，打开的是同一个文件路径，各自写入。这是数据竞争吗？

<details markdown="1">
<summary>答案</summary>

不是 [[iostreams.threadsafety#1]] 意义上的数据竞争：两个流对象和它们各自的 `filebuf` 都是不同的对象。但两者的数据写进文件的顺序和交错方式由操作系统决定，文件内容可能互相覆盖，这是文件系统层面的问题，标准不作保证。
</details>

## 小结

| 规则 | 出处 | 后果 |
|---|---|---|
| 并发访问同一个流对象、流缓冲区或 `FILE*` | [iostreams.threadsafety] ¶1 | 数据竞争 {{ub}}；同步状态的标准流除外 |
| 通过流写入并被另一线程读到 | [iostreams.threadsafety] ¶2 | 写同步于读 |
| 库函数不自行调用 `imbue`；回调或重写的虚函数里调用 `imbue` | [iostream.limits.imbue] ¶1 | 后者 {{ub}} |
| `streamoff`、`streamsize` 是有符号整数类型 | [stream.types] | `-1` 可作错误值 |
| `pos_type`/`off_type` 不是 `streampos`/`streamoff` | [iostreams.limits.pos] ¶1 | {{impl}}；用于 `basic_filebuf` 时 {{ub}} |
