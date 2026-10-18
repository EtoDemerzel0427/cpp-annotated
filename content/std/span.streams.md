---
title: span 流
summary: C++23 的 <spanstream>：把流接到调用者提供的固定大小缓冲区 span<charT> 上，不分配、不拥有、不增长——写满即失败（badbit）；basic_spanbuf 的 span() 返回已写部分、seekoff 的 baseoff 规则、ispanstream 从只读范围构造时的 const_cast 与字符串字面量的结尾 '\0'；它为何是被移除的 strstream 的替代品，以及截至写作时 libc++ 尚未提供该头文件
status: done
covers: *
since: c++23
related: string.streams, stream.buffers, views.span, input.streams, output.streams, iostreams.requirements
tags: 标准库, iostream, spanstream, 内存流, 无分配
updated: 2026-10-18
---

`<spanstream>`（C++23）提供与 [[string.streams]] 对称的一组类：`basic_spanbuf`、`basic_ispanstream`、`basic_ospanstream`、`basic_spanstream`。区别在于底层存储：字符串流**拥有**一个可增长的 `basic_string`，span 流只是**借用**调用者提供的一段 `span<charT>`（[[views.span]]），大小固定、从不分配。

典型用途：在栈上的固定缓冲区里格式化（嵌入式、实时、信号处理等不能分配内存的场合），或者把一段已有的内存（网络包、内存映射文件）当作输入流解析，而不先复制成 `std::string`。

!!! history "替代 `strstream`"
    C++98 的 `<strstream>`（`istrstream`、`ostrstream`、`strstream`、`strstreambuf`）同样操作 `char*` 缓冲区，但它的接口混杂了"借用"与"动态分配"两种模式，`str()` 会"冻结"缓冲区、要求调用者记得 `freeze(false)`，从标准化之初就被弃用。`<spanstream>` 是它的现代替代品。当前草案已删除 `<strstream>`（[[diff.cpp23]] 中列出，属于 C++26 相对 C++23 的变化）{{removed:C++26}}，实现可以按 [[zombie.names]] 继续提供。

!!! impl "libc++ 尚未提供 `<spanstream>`"
    截至写作时，本机 libc++（Clang 23）的头文件目录里没有 `<spanstream>`，`<version>` 中 `__cpp_lib_spanstream` 的定义被注释掉。本页的例子按标准写成，**没有在本机运行**；可以在 Compiler Explorer 上用 GCC（libstdc++ 已提供该头文件）验证，例子的按钮已经指定了 GCC trunk。

## 概述（[span.streams.overview]）

¶1：`<spanstream>` 定义的类模板与类型把流缓冲区与 `span` 特化类型的对象关联起来。注（¶1 中的 Note 1）有两条重要提醒：

- **生命周期由用户负责**：给定 span 所表示的字符序列必须比这些类的对象对它的使用活得更久。
- **数据竞争**：从不同线程使用多个引用**重叠**底层序列的 `basic_spanbuf` 对象，且至少一个在写，构成数据竞争。——即使流对象各不相同，共享底层内存也会竞争，这一点与字符串流不同。

## `<spanstream>` 概要（[spanstream.syn]）

四个类模板（参数只有 `charT`、`traits`，没有分配器）、各自的非成员 `swap`，以及 `spanbuf`/`ispanstream`/`ospanstream`/`spanstream` 和 `w` 前缀的别名。

## `basic_spanbuf`（[spanbuf]）

### 数据模型（[spanbuf.general]）

```cpp
template<class charT, class traits = char_traits<charT>>
class basic_spanbuf : public basic_streambuf<charT, traits> {
public:
  basic_spanbuf() : basic_spanbuf(ios_base::in | ios_base::out) {}
  explicit basic_spanbuf(ios_base::openmode which)
    : basic_spanbuf(std::span<charT>(), which) {}
  explicit basic_spanbuf(std::span<charT> s, ios_base::openmode which = ios_base::in | ios_base::out);
  basic_spanbuf(basic_spanbuf&& rhs);
  basic_spanbuf& operator=(basic_spanbuf&& rhs);
  void swap(basic_spanbuf& rhs);

  std::span<charT> span() const noexcept;
  void span(std::span<charT> s) noexcept;
protected:
  basic_streambuf<charT, traits>* setbuf(charT*, streamsize) override;
  pos_type seekoff(off_type off, ios_base::seekdir way, ios_base::openmode which = in | out) override;
  pos_type seekpos(pos_type sp, ios_base::openmode which = in | out) override;
private:
  ios_base::openmode mode;     // 说明专用
  std::span<charT> buf;        // 说明专用
};
```

¶1–¶2：与 `basic_stringbuf` 一样，`mode` 记录可读/可写，`buf` 是底层字符序列的**视图**。注意它只覆写了 `setbuf`、`seekoff`、`seekpos`——**没有覆写 `underflow`、`overflow`、`pbackfail`**。[spanbuf.virtuals] ¶1 的注解释了原因：底层缓冲区大小固定，这三个函数都无法提供有用的行为。于是它们使用基类的默认实现，一律返回 `eof()`：

- 读到 span 末尾：`underflow()` 返回 `eof()`，流置 `eofbit`；
- 写满 span：`sputc` 发现没有写位置，调用 `overflow()`，返回 `eof()`，插入器据此报告失败（算术插入器、`put`、`write` 规定置 `badbit`，见 [[output.streams]]）——**不扩容**；
- 回退一个不同的字符：`pbackfail()` 返回 `eof()`，`putback` 置 `badbit`。

### 构造、赋值（[spanbuf.cons]、[spanbuf.assign]）

- `basic_spanbuf(s, which)`：¶1 以 `basic_streambuf()` 初始化基类，`mode` 为 `which`，然后如同调用 `span(s)` 设置指针。
- 移动构造：¶2–¶3 移动基类、`mode` 与 `buf`；`*this` 的六个指针**等于** `rhs` 原来的值（因为缓冲区不属于任何一方，直接共享同一块外部内存是正确的）；`rhs.buf.empty()` 在移动后是否为真由实现定义。
- 移动赋值：¶1 等价于"移动构造一个临时对象再 `swap`"。`swap`：¶2 交换基类、`mode`、`buf`。

### `span()` 与 `span(s)`（[spanbuf.members]）

- `span()`：¶1 若 `mode` 含 `out`，返回 `span<charT>(pbase(), pptr())`——**已写入的部分**；否则返回整个 `buf`。注：与 `basic_stringbuf` 不同，底层序列从不增长、也不被拥有；需要拥有的副本时把结果转换为 `basic_string`。
- `span(s)`：¶2 `buf = s`，按 `mode` 初始化输入和输出序列。¶3 后条件（与 stringbuf 的 `init-buf-ptrs` 相同的布局）：
    - 含 `out`：`pbase() == s.data()`、`epptr() == pbase() + s.size()`；含 `ate` 时 `pptr() == pbase() + s.size()`，否则 `pptr() == pbase()`；
    - 含 `in`：`eback() == s.data()`、`gptr() == eback()`、`egptr() == eback() + s.size()`。

注意 `span()` 在输出模式下用的是 `pptr()`，而 `basic_stringbuf::view()` 用的是 high mark：`seekp` 回退之后，span 流的 `span()` 会**变短**，字符串流的 `view()` 不会。

### 定位（[spanbuf.virtuals] ¶2–¶8）

`seekoff(off, way, which)`：

- ¶2：`which` 含 `in` 时定位输入序列（`xnext` 为 `gptr()`、`xbeg` 为 `eback()`）；含 `out` 时定位输出序列（`pptr()`、`pbase()`）。
- ¶3：`which` 同时含 `in` 和 `out` 且 `way` 为 `cur` 时失败（同 stringbuf）。
- ¶4：下一指针为空且新偏移非零时失败。否则计算 `baseoff`：`beg` 为 0；`cur` 为当前偏移；`end` 时——**若 `mode` 只含 `out` 不含 `in`，为 `pptr() - pbase()`（已写入的末尾）；否则为 `buf.size()`（整个 span 的末尾）**。
- ¶5：`baseoff + off` 溢出、小于 0、或大于 `buf.size()` 时失败；否则 `newoff = baseoff + off`，`xnext = xbeg + newoff`。
- ¶6：失败返回 `pos_type(off_type(-1))`，否则 `pos_type(newoff)`。

`seekpos(sp, which)`：¶7 `return seekoff(off_type(sp), beg, which);`。`setbuf(s, n)`：¶8 `this->span(std::span<charT>(s, n)); return this;`——这是 span 流唯一能"换缓冲区"的虚接口。

## 三个流类（[ispanstream]、[ospanstream]、[spanstream]）

| 类 | 基类 | 构造 `sb` 的模式 | `span()` 返回 |
|---|---|---|---|
| `basic_ispanstream` | `basic_istream` | `which | in` | `span<const charT>` |
| `basic_ospanstream` | `basic_ostream` | `which | out` | `span<charT>` |
| `basic_spanstream` | `basic_iostream` | `which`（默认 `out | in`） | `span<charT>` |

（[spanstream.cons] 的声明中草案把默认实参写成了 `ios_base::out | ios_bas::in`，`ios_bas` 是编辑性笔误，以概要中的 `ios_base::out | ios_base::in` 为准。）

共同点：持有说明专用的 `basic_spanbuf sb`；移动构造先移动基类和 `sb`，再 `set_rdbuf(addressof(sb))`；`swap` 交换基类和 `sb`；`rdbuf()` 是 `const noexcept` 的，返回 `const_cast` 去掉 `const` 的 `addressof(sb)`。

### `basic_ispanstream` 的只读范围构造函数（[ispanstream.cons] ¶3–¶4）

```cpp
template<class ROS> explicit basic_ispanstream(ROS&& s);
```

*Constraints*：`ROS` 满足 `ranges::borrowed_range`，且 `!convertible_to<ROS, span<charT>> && convertible_to<ROS, span<const charT>>`。*Effects*：令 `sp` 为 `span<const charT>(std::forward<ROS>(s))`，等价于 `basic_ispanstream(span<charT>(const_cast<charT*>(sp.data()), sp.size()))`。

也就是说，输入 span 流可以接受**只读**的连续范围（如 `std::string_view`、`const char[]`），内部用 `const_cast` 去掉 `const` 后交给 `basic_spanbuf`。这是安全的，因为 `ispanstream` 的模式不含 `out`：没有写位置，`pbackfail` 也不修改缓冲区。成员 `span(ROS&&)`（[ispanstream.members] ¶4–¶5）同理。要求 `borrowed_range` 是为了防止传入一个临时 `std::string`——它的数据在构造函数返回后就销毁了。

[ispanstream.general] ¶1 的注提醒：**从字符串字面量构造时，结尾的 `'\0'` 也包含在内**——字面量是 `const char[N]`，`N` 包括终止符。

```cpp title="ispanstream-literal.cpp" ok cc=gsnapshot run
#include <iostream>
#include <spanstream>
#include <string>
#include <string_view>

int main() {
  std::ispanstream a("42");                    // 底层 span 是 {'4','2','\0'}，3 个字符
  int x; a >> x;
  std::cout << x << " eof=" << a.eof() << '\n';     // 42 eof=0：遇到 '\0' 停下，没有撞到末尾

  std::ispanstream b(std::string_view("42"));  // string_view 不含终止符
  b >> x;
  std::cout << x << " eof=" << b.eof() << '\n';     // 42 eof=1

  // std::ispanstream c(std::string("42"));    // error：std::string 不是 borrowed_range
}
```

## 例子：在栈缓冲区里格式化

```cpp title="ospanstream-fixed.cpp" ok cc=gsnapshot run
#include <iostream>
#include <span>
#include <spanstream>
#include <string_view>

int main() {
  char buf[16];
  std::ospanstream os(buf);                         // 不分配；最多 16 个字符
  os << "id=" << 42 << " ok";
  std::span<char> written = os.span();              // 已写入的部分
  std::cout << std::string_view(written.data(), written.size())
            << " ok=" << bool(os) << '\n';          // id=42 ok ok=1

  os << " and some more text";                      // 超出 16 个字符
  std::cout << os.span().size() << " ok=" << bool(os) << '\n';   // 16 ok=0：写满后流进入失败状态
}
```

写满之后已写入的前 16 个字符仍在缓冲区里，但流已处于失败状态（`overflow()` 返回 `eof()`，插入器据此置错误位；主流实现置的是 `badbit`），之后的插入全部无效。需要"截断而不失败"的语义时，`std::format_to_n`（[[format]]）通常更合适。

## 思考题

<details markdown="1">
<summary>1. <code>std::spanstream ss(buf); ss &lt;&lt; "abc"; ss.seekp(0, std::ios_base::end);</code> 之后 <code>tellp()</code> 是多少？换成 <code>std::ospanstream</code> 呢？</summary>

`spanstream` 的模式是 `out | in`，[[spanbuf.virtuals#4]] ¶4.3.2 规定此时 `end` 的 `baseoff` 是 `buf.size()`，所以 `tellp()` 是整个缓冲区的大小。`ospanstream` 的模式只有 `out`，¶4.3.1 规定 `baseoff` 是 `pptr() - pbase()`，即 3。前者把"末尾"理解为缓冲区末尾（可能包含未写入的垃圾），后者理解为已写内容的末尾。
</details>

<details markdown="1">
<summary>2. 两个线程分别用各自的 <code>ospanstream</code> 写同一个 <code>char buf[64]</code> 的前半和后半，有数据竞争吗？</summary>

只要两段内存不重叠，就没有：数据竞争是按内存位置判断的（[[intro.races]]），两个 `basic_spanbuf` 各自写不同的字符。[[span.streams.overview]] 的注针对的是**重叠**的底层序列。但如果其中一个流写满后越界——不会发生，spanbuf 在 `epptr()` 处就停止了，这正是固定大小的好处。
</details>

## 小结

- span 流借用调用者的固定缓冲区：不分配、不拥有、不增长，生命周期由调用者保证。
- 只覆写 `setbuf`/`seekoff`/`seekpos`；写满即失败（通常是 `badbit`），读完即 `eofbit`。
- `span()` 在输出模式下返回 `[pbase(), pptr())`；`seekoff(end)` 对纯输出流指已写末尾，否则指缓冲区末尾。
- `ispanstream` 可以从 `string_view` 等只读借用范围构造；从字符串字面量构造会包含结尾的 `'\0'`。
- `<strstream>` 已从当前草案移除，`<spanstream>` 是替代品；本机 libc++ 尚未提供它。
