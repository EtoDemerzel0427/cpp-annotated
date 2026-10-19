---
title: span 流
summary: C++23 的 <spanstream> 把流接到调用者提供的一段固定大小的缓冲区上：不分配、不拥有、不增长，写满即失败；它取代了已被移除的 <strstream>。
status: done
covers: *
since: c++23
related: string.streams, stream.buffers, views.span, input.streams, output.streams, iostreams.requirements
tags: 标准库, iostream, spanstream, 内存流, 无分配
updated: 2026-10-19
---

!!! tldr
    - `ospanstream`、`ispanstream`、`spanstream` 借用一段 `std::span<char>` 做缓冲区，从不分配内存；缓冲区的生命周期由调用者保证。
    - 写满缓冲区后插入失败，流进入错误状态，不会扩容；读到末尾时置 `eofbit`。
    - 输出模式下 `span()` 返回已经写入的部分 `[pbase(), pptr())`。
    - `ispanstream` 可以直接从 `string_view` 这类只读范围构造；从字符串字面量构造时，结尾的 `'\0'` 也算在内。
    - 截至写作时，本机 libc++ 还没有提供 `<spanstream>`。本页例子的按钮使用 GCC trunk。

```cpp title="ospanstream-fixed.cpp" cc=gsnapshot run
#include <iostream>
#include <span>
#include <spanstream>
#include <string_view>

int main() {
  char buf[16];
  std::ospanstream os(buf);                 // 不分配，最多写 16 个字符
  os << "id=" << 42 << " ok";
  std::span<char> written = os.span();      // 已写入的部分
  std::cout << std::string_view(written.data(), written.size())
            << " good=" << bool(os) << '\n';                    // id=42 ok good=1

  os << " and some more text";              // 超出 16 个字符
  std::cout << os.span().size() << " good=" << bool(os) << '\n';  // 16 good=0
}
```

`<spanstream>` 与 [[string.streams]] 对称，提供 `basic_spanbuf` 和三个流类 `basic_ispanstream`、`basic_ospanstream`、`basic_spanstream`，以及 `spanbuf`、`ispanstream` 等 `char` 别名和 `w` 前缀的 `wchar_t` 别名。区别在于底层存储：字符串流拥有一个可以增长的 `basic_string`，span 流只借用调用者给的一段 `span<charT>`（[[views.span]]），大小固定。

典型用途有两种。一是在不能分配内存的场合（嵌入式、实时代码、信号处理函数）把输出格式化到栈上的数组里；二是把一段已有的内存（网络包、内存映射的文件）当作输入流解析，不必先复制成 `std::string`。

!!! impl "本页例子没有在本机运行"
    本机 libc++（Clang 23）没有 `<spanstream>` 头文件，`<version>` 里 `__cpp_lib_spanstream` 的定义被注释掉了。libstdc++ 已经提供了这个头文件。本页例子按标准写成，没有标判定；点 godbolt 按钮会用 GCC trunk 编译运行。

## 借用的缓冲区 [span.streams.overview]

¶1 这些类把流缓冲区与一个 `span` 关联起来。¶1 的注提醒了借用带来的两条责任：

- span 所指的字符序列必须比流对它的使用活得更久，这由使用者保证；
- 多个 `basic_spanbuf` 对象引用重叠的字符序列，在不同线程中使用，并且至少有一个在写，就构成数据竞争。

第二条与字符串流不同。每个字符串流有自己的缓冲区，不同的流对象之间不会竞争；span 流的流对象虽然各不相同，底层内存却可能是同一块。

## `basic_spanbuf` [spanbuf]

### 数据成员 [spanbuf.general]

¶1–¶2 `basic_spanbuf` 派生自 `basic_streambuf`，有两个说明专用的成员：打开模式 `mode`（含 `in` 表示可读，含 `out` 表示可写），以及指向底层字符序列的 `std::span<charT> buf`。它没有分配器模板参数，因为从不分配。

### 设置缓冲区 [spanbuf.members] ¶2–¶3、[spanbuf.cons] ¶1

¶2 `span(s)` 把 `buf` 设为 `s`，再按 `mode` 设置六个指针（get 区与 put 区的指针，见 [[stream.buffers]]）。[spanbuf.cons] ¶1 构造函数 `basic_spanbuf(s, which)` 也是先记下 `which`，再如同调用 `span(s)`。

¶3 指针的布局与 `basic_stringbuf` 的 `init-buf-ptrs` 相同：

- 含 `out`：put 区覆盖整个 `s`。含 `ate` 时 `pptr()` 在末尾，否则在开头；
- 含 `in`：get 区覆盖整个 `s`，`gptr()` 在开头。

### 取出已写内容 [spanbuf.members] ¶1

¶1 `span()` 在 `mode` 含 `out` 时返回 `span<charT>(pbase(), pptr())`，也就是已经写入的部分；否则返回整个 `buf`。注里说明，需要一份拥有所有权的副本时，把结果转换成 `basic_string`。

这里有一处与字符串流不同。`basic_stringbuf::view()` 以 high mark（写到过的最远位置）为终点，`basic_spanbuf::span()` 以当前的 `pptr()` 为终点。用 `seekp` 往回定位之后，`span()` 会变短，`view()` 不会。

### 写满和读完 [spanbuf.virtuals] ¶1

`basic_spanbuf` 只覆写了 `setbuf`、`seekoff`、`seekpos`。¶1 的注解释了原因：缓冲区大小固定，`overflow`、`underflow`、`pbackfail` 都给不出有用的行为。于是这三个函数使用基类的默认实现，一律返回 `eof()`：

- 写满时 `sputc` 找不到写位置，调用 `overflow()`，得到 `eof()`，插入器据此报告失败。算术插入器、`put`、`write` 规定此时置 `badbit`（[[output.streams]]），字符串插入器在主流实现中也置 `badbit`。缓冲区不会扩容。
- 读到 span 末尾时 `underflow()` 返回 `eof()`，提取操作置 `eofbit`。
- 放回一个与上次读出的字符不同的字符时，`pbackfail()` 返回 `eof()`，`putback` 置 `badbit`。

写满之后，前面写入的字符仍在缓冲区里，但流已经处于失败状态，之后的插入都不再生效。如果需要截断而不失败，`std::format_to_n`（[[format]]）更合适。

### 定位 [spanbuf.virtuals] ¶2–¶8

规则与 [[string.streams]] 的 `seekoff` 大体相同：

¶2 `which` 含 `in` 时定位输入序列，含 `out` 时定位输出序列。¶3 `which` 同时含 `in` 和 `out`、`way` 为 `cur` 时失败，因为两个序列的当前位置可能不同。

¶4 下一指针为空而新偏移不为 0 时失败。否则算出起点 `baseoff`：`beg` 为 0；`cur` 为当前偏移；`end` 分两种情况：

- ¶4.3.1 `mode` 含 `out` 而不含 `in`：`pptr() - pbase()`，即已写内容的末尾；
- ¶4.3.2 其他情况：`buf.size()`，即整个 span 的末尾。

¶5 `baseoff + off` 溢出、小于 0、或大于 `buf.size()` 时失败；否则把下一指针设到 `baseoff + off` 处。¶6 失败返回 `pos_type(off_type(-1))`，成功返回新位置。

¶7 `seekpos(sp, which)` 等价于 `seekoff(off_type(sp), beg, which)`。¶8 `setbuf(s, n)` 等价于 `span(std::span<charT>(s, n))`，然后返回 `this`。

### 移动 [spanbuf.cons] ¶2–¶3、[spanbuf.assign]

¶2–¶3 移动构造之后，新对象的六个指针与 `rhs` 原来的值完全相同。缓冲区不属于任何一方，两个对象指向同一块外部内存是正确的。`rhs.buf` 移动后是否为空由实现定义。

[spanbuf.assign] ¶1 移动赋值等价于先从 `rhs` 移动构造一个临时对象，再与它 `swap`。¶2 `swap` 交换基类、`mode` 和 `buf`。

## 三个流类 [ispanstream]、[ospanstream]、[spanstream]

| 类 | 基类 | 传给 `sb` 的模式 | `span()` 的返回类型 |
|---|---|---|---|
| `basic_ispanstream` | `basic_istream` | `which \| in` | `span<const charT>` |
| `basic_ospanstream` | `basic_ostream` | `which \| out` | `span<charT>` |
| `basic_spanstream` | `basic_iostream` | `which`（默认 `out \| in`） | `span<charT>` |

三者都持有一个说明专用的 `basic_spanbuf sb`。移动构造先移动基类和 `sb`，再调用 `set_rdbuf(addressof(sb))`；`swap` 交换基类和 `sb`；`rdbuf()` 是 `const noexcept` 的，返回 `const_cast` 之后的 `basic_spanbuf*`。

### 从只读范围构造 `ispanstream` [ispanstream.cons] ¶3–¶4

```cpp
template<class ROS> explicit basic_ispanstream(ROS&& s);
```

¶3 这个构造函数要求 `ROS` 是 `borrowed_range`，能转换为 `span<const charT>`，但不能转换为 `span<charT>`。¶4 它先构造 `span<const charT> sp`，再用 `const_cast` 去掉 `const`，交给 `basic_spanbuf`。

去掉 `const` 是安全的：`ispanstream` 的模式不含 `out`，没有写位置，`pbackfail` 也不修改缓冲区。要求 `borrowed_range` 是为了拒绝临时的 `std::string`，它的字符在构造函数返回后就销毁了。成员函数 `span(ROS&&)`（[ispanstream.members] ¶4–¶5）有同样的约束和效果。

[ispanstream.general] ¶1 的注提醒：从字符串字面量构造时，结尾的 `'\0'` 也在底层序列里。字面量的类型是 `const char[N]`，`N` 包括终止符。

```cpp title="ispanstream-literal.cpp" cc=gsnapshot run
#include <iostream>
#include <spanstream>
#include <string>
#include <string_view>

int main() {
  int x;
  std::ispanstream a("42");                  // 底层是 {'4','2','\0'}
  a >> x;
  std::cout << x << " eof=" << a.eof() << '\n';   // 42 eof=0：停在 '\0' 前

  std::ispanstream b(std::string_view("42")); // 不含终止符
  b >> x;
  std::cout << x << " eof=" << b.eof() << '\n';   // 42 eof=1

  // std::ispanstream c(std::string("42"));   // error：临时 string 不是 borrowed_range
}
```

## 历史

!!! history "取代 `<strstream>`"
    C++98 的 `<strstream>`（`istrstream`、`ostrstream`、`strstream`、`strstreambuf`）同样操作 `char*` 缓冲区，但同一个类既能借用调用者的缓冲区，也能自己动态分配。动态分配时 `str()` 会冻结缓冲区，调用者必须记得 `freeze(false)`，否则内存泄漏。它从第一版标准起就被弃用。

    C++23 加入 `<spanstream>` 作为替代，只做借用这一件事。当前草案已经删除了 `<strstream>`（[[diff.cpp23]]）{{removed:C++26}}，实现可以按 [[zombie.names]] 继续提供。

## 思考题

!!! question "思考题 1"
    `char buf[64]; std::spanstream ss(buf); ss << "abc"; ss.seekp(0, std::ios_base::end);` 之后 `ss.tellp()` 是多少？换成 `std::ospanstream` 呢？

<details markdown="1">
<summary>答案</summary>

`spanstream` 的模式是 `out | in`，按 [[spanbuf.virtuals#4]] 的 ¶4.3.2，`end` 的起点是 `buf.size()`，所以 `tellp()` 是 64。`ospanstream` 的模式只有 `out`，按 ¶4.3.1，起点是 `pptr() - pbase()`，结果是 3。前者把末尾理解为缓冲区末尾，那里可能是从未写过的字符；后者理解为已写内容的末尾。
</details>

!!! question "思考题 2"
    两个线程分别用各自的 `ospanstream` 写同一个 `char buf[64]` 的前 32 个和后 32 个字符，有数据竞争吗？

<details markdown="1">
<summary>答案</summary>

没有。数据竞争是按内存位置判断的（[[intro.races]]），两个流写的字符互不重叠；[[span.streams.overview]] 的注针对的是重叠的序列。每个流的 put 区在构造时就限定在自己那一半，写满后在 `epptr()` 处停下，不会越界写到另一半。
</details>

<details class="fine" markdown="1"><summary>其余条文</summary>

[spanstream.syn] 声明四个类模板（模板参数只有 `charT` 和 `traits`）、各自的非成员 `swap`，以及 `spanbuf`、`ispanstream`、`ospanstream`、`spanstream` 和 `w` 前缀的别名。

[spanbuf.assign] ¶3 和各流类的 [*.swap] ¶2：非成员 `swap` 等价于 `x.swap(y)`。

[spanstream.cons] 中构造函数声明的默认实参写成了 `ios_base::out | ios_bas::in`，`ios_bas` 是编辑上的笔误，以类概要中的 `ios_base::out | ios_base::in` 为准。

</details>
