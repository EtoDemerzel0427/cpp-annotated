---
title: 字符串流
summary: <sstream> 的 basic_stringbuf 怎样用一个 basic_string 同时充当读缓冲区和写缓冲区，以及 istringstream、ostringstream、stringstream 的构造、取出内容、定位和重用时的常见陷阱。
status: done
covers: *
related: stream.buffers, input.streams, output.streams, span.streams, basic.string, string.view, iostreams.base, format
tags: 标准库, iostream, stringstream, 内存流
updated: 2026-10-19
---

!!! tldr
    - `basic_stringbuf` 用一个 `basic_string` 同时做读缓冲区和写缓冲区，`stringstream` 写进去的字符随即可以读出来。
    - 用初始字符串构造的输出流默认从开头覆盖写；要接在末尾续写，打开模式里加 `ate`。
    - `str()` 每次复制一份；C++20 起 `view()` 不复制但可能悬垂，`std::move(ss).str()` 把缓冲区整个移出。
    - `str(s)` 只换内容，不清除流的错误状态；重用一个流要再调用 `clear()`。
    - 不带 `which` 的 `pubseekoff(off, cur)` 会失败，因为读位置和写位置可能不同。

```cpp run ok
#include <iostream>
#include <sstream>

int main() {
  std::stringstream ss;
  ss << "12 34";                  // 写入
  int a, b;
  ss >> a >> b;                   // 刚写的字符马上能读
  std::cout << a + b << '\n';     // 46
}
```

`<sstream>` 提供四个类模板（[sstream.syn] ¶1）。`basic_stringbuf` 是流缓冲区，`basic_istringstream`、`basic_ostringstream`、`basic_stringstream` 各自持有一个 `basic_stringbuf` 成员，分别负责读、写、读写。常用的 `stringstream`、`istringstream` 等是它们 `char` 特化的别名，`w` 前缀的是 `wchar_t` 特化。

流本身只负责格式化，字符存在哪里由流缓冲区（stream buffer，`basic_streambuf` 的派生类）决定，见 [[stream.buffers]]。流缓冲区用两段区域和六个指针管理字符：**get 区**（读）由 `eback()`、`gptr()`、`egptr()` 界定，`gptr()` 是下一个要读的字符；**put 区**（写）由 `pbase()`、`pptr()`、`epptr()` 界定，`pptr()` 是下一个要写的位置。区域用完时，基类会调用派生类覆写的虚函数 `underflow`（补充可读字符）或 `overflow`（腾出写位置）。

## 一个字符串，两个区域 [stringbuf.general]

¶1 `basic_stringbuf` 把输入序列和输出序列关联到同一个字符序列上。这个序列可以用一个 `basic_string` 初始化，也可以以 `basic_string` 的形式取出。

¶2 为了说明行为，标准给它设了三个说明专用（exposition only）的成员，实现不必真的这样写：

- `mode`：打开模式。含 `in` 表示可读，含 `out` 表示可写；
- `buf`：一个 `basic_string`，保存底层字符序列；
- `init-buf-ptrs()`：在 `buf` 被初始化、移动或赋值之后，按 `mode` 重新设置六个指针。

它覆写了 `underflow`、`pbackfail`、`overflow`、`setbuf`、`seekoff`、`seekpos`，其余虚函数（`uflow`、`xsgetn`、`xsputn`、`sync` 等）都用基类的默认实现。

### 指针的初始布局 [stringbuf.members] ¶2–¶3

¶3 `init-buf-ptrs()` 之后的状态：

- 如果 `mode` 含 `out`：`pbase()` 指向 `buf` 的第一个字符，`epptr() >= pbase() + buf.size()`。如果还含 `ate`，`pptr()` 在 `buf.size()` 处，从末尾续写；否则 `pptr() == pbase()`，从开头覆盖写。
- 如果 `mode` 含 `in`：get 区正好覆盖 `buf` 的全部内容，`gptr()` 在开头。

```text
 std::stringstream ss("hello");          mode = in | out
 buf:      [ h  e  l  l  o  ·  ·  · ]    （· 是 capacity 中尚未使用的部分）
 get 区:    eback=gptr            egptr
 put 区:    pbase=pptr                  epptr（可能超过 size）
```

### 覆盖写与 `ate`

ate 的作用最容易在输出流上看出来：

<div class="compare" markdown="1">

```cpp run ok
#include <iostream>
#include <sstream>
int main() {
  std::ostringstream a("XXXXXX");
  a << "ab";
  std::cout << a.str();  // abXXXX
}
```

```cpp run ok
#include <iostream>
#include <sstream>
int main() {
  using std::ios_base;
  std::ostringstream b("XXXXXX",
                       ios_base::ate);
  b << "ab";
  std::cout << b.str();  // XXXXXXab
}
```

</div>

标准没有为字符串流规定 `app` 的含义，`init-buf-ptrs` 只看 `ate`。本机 libc++ 在构造时把 `app` 当作 `ate`（`ostringstream("XXXX", app) << "ab"` 得到 `XXXXab`），但之后 `seekp(0)` 仍能覆盖开头，并不像文件那样每次写之前都回到末尾。

### high mark [stringbuf.members] ¶1、¶4

¶1 标准用 **high mark** 表示缓冲区中最后一个已初始化字符之后的位置。字符通过三种途径成为已初始化：写入流、用 `basic_string` 构造、调用 `str(s)`。调用 `str(s)` 时，之前的字符都算回未初始化，新字符串覆盖到的除外。

¶4 是一条注：为了效率，`basic_stringbuf` 可以直接写 `buf` 在 `size()` 和 `capacity()` 之间的空间，暂时破坏 `basic_string` 的不变式。所以 `buf.size()` 不一定反映写到了哪里，需要 high mark 来记录。所有取出字符串的操作都以 high mark 为终点，并保证返回的字符串满足不变式。

high mark 只增不减。往回定位再写，不会让内容变短：

```cpp run ok
#include <iostream>
#include <sstream>

int main() {
  std::ostringstream os;
  os << "hello";
  os.seekp(0);
  os << "J";
  std::cout << os.str() << '\n';             // Jello：长度仍是 5
  os.seekp(0, std::ios_base::end);
  std::cout << os.tellp() << '\n';           // 5：end 指 high mark
}
```

## 取出和替换内容 [stringbuf.members] ¶5–¶19

| 成员 | 效果 |
|---|---|
| `str() const &` | ¶6 返回 `view()` 的一份副本 |
| `str(const SAlloc& sa) const` {{c++20}} | ¶7–¶8 同上，但副本使用分配器 `sa` |
| `str() &&` {{c++20}} | ¶9–¶10 把底层字符串移出；之后 `buf` 为空，指针按空字符串重新设置 |
| `view() const noexcept` {{c++20}} | ¶11–¶12 返回指向底层字符的 `string_view`，不复制 |
| `str(s)` | ¶14–¶17 `buf = s`（或移动 `s`），再调用 `init-buf-ptrs()` |
| `str(const T& t)` {{c++26}} | ¶18–¶19 `t` 能转换为 `basic_string_view` 时可用，经 `string_view` 赋值 |
| `get_allocator()` | ¶5 返回 `buf` 的分配器 |

¶12 `view()` 返回的范围取决于模式：含 `out` 时是 `[pbase(), high mark)`；否则含 `in` 时是 `[eback(), egptr())`；两者都不含时为空。

¶13 是一条注：底层字符序列被销毁或失效之后，再使用 `view()` 返回的 `string_view` 是未定义行为（结果为空时除外）。继续写入可能导致重新分配，这也算失效：

```cpp title="view-dangling.cpp" ub
#include <iostream>
#include <sstream>
#include <string>
#include <string_view>

int main() {
  std::ostringstream os;
  os << std::string(40, 'a');
  std::string_view v = os.view();
  os << std::string(1000, 'x');      // 重新分配，底层数组被释放
  std::cout << v[0] << '\n';         // UB：v 指向已释放的内存
}
```

本机 ASan 在最后一行报告 heap-use-after-free。如果初始内容很短，字符可能存在字符串对象内部的小缓冲区里（SSO），ASan 看不到释放，但程序同样是 UB。

所以三种取法各有用途：只读一下用 `view()`，并且在下一次写之前用完；要拿走结果用 `std::move(os).str()`，不复制；`str()` 每次都复制，在循环里反复调用代价是 O(n²)。

## 写进去就能读 [stringbuf.virtuals] ¶1、¶5–¶8

¶5 put 区写满时，`sputc` 调用 `overflow(c)`。如果能腾出一个写位置，`overflow` 就写入 `c` 并返回 `c`；`c` 是 `eof()` 时没有字符要写，返回一个非 `eof()` 的值表示成功。¶6 失败返回 `eof()`。¶7 每次调用都可以改变可用写位置的数量。

¶8 只有 `mode` 含 `out` 时才能腾出写位置。办法是重新分配（或第一次分配）一个数组，容纳当前内容外加至少一个写位置。如果 `mode` 还含 `in`，`overflow` 同时把 `egptr()` 推到新写入的字符之后。

¶1 `underflow()` 有可读字符时返回 `*gptr()`，否则返回 `eof()`。缓冲区里任何已初始化的字符都算输入序列的一部分。

这两条合起来解释了开头的例子：`stringstream` 写入时 `overflow` 推进了 `egptr()`，刚写的字符就进入了 get 区。

## 回退字符 [stringbuf.virtuals] ¶2–¶4

`putback(c)` 在当前读位置前面放回一个字符。如果 `c` 正好等于上一个读出的字符，基类直接把 `gptr()` 减一；否则调用 `pbackfail(c)`。

¶2 `pbackfail(c)` 有三种成功的方式：

1. `c` 不是 `eof()`，前面还有位置，并且 `c` 等于 `gptr()[-1]`：`gptr()` 减一，返回 `c`；
2. `c` 不是 `eof()`，前面还有位置，并且 `mode` 含 `out`：把 `c` 写到 `*--gptr()`，返回 `c`；
3. `c` 是 `eof()`，前面还有位置：`gptr()` 减一，返回 `not_eof(c)`。

¶3 都不满足时返回 `eof()`，表示失败。¶4 有多种方式可行时，选哪一种未指定。第 2 种方式会修改缓冲区，所以只有可写的 stringbuf 才能放回一个不同的字符：

<div class="compare" markdown="1">

```cpp run ok
#include <iostream>
#include <sstream>
int main() {
  std::istringstream in("abc");
  in.get();
  in.putback('z');        // 失败
  std::cout << in.bad();  // 1
}
```

```cpp run ok
#include <iostream>
#include <sstream>
#include <string>
int main() {
  std::stringstream s("abc");
  s.get();
  s.putback('z');         // 成功
  std::string r;
  s >> r;
  std::cout << r;         // zbc
}
```

</div>

左边 `istringstream` 的模式只有 `in`，前两种方式都不适用，`pbackfail` 返回 `eof()`，`putback` 置 `badbit`。右边 `stringstream` 的模式含 `out`，第 2 种方式把 `'z'` 写进了缓冲区。

## 定位 [stringbuf.virtuals] ¶9–¶14

`seekoff(off, way, which)` 是 `seekg`、`seekp`、`tellg`、`tellp` 背后的虚函数。`which` 说明要定位哪个序列，`way` 是起点：`beg`（开头）、`cur`（当前位置）或 `end`（末尾）。

¶9 按下表决定定位哪个序列：

| 条件 | 结果 |
|---|---|
| `which` 只含 `in` | 定位输入序列 |
| `which` 只含 `out` | 定位输出序列 |
| `which` 含 `in` 和 `out`，`way` 是 `beg` 或 `end` | 两个序列都定位 |
| 其他情况 | 失败 |

最后一行包括 `which` 为 `in | out`、`way` 为 `cur` 的情形。读位置和写位置可能不同，相对于谁的当前位置无法确定，所以直接失败。

¶10 对每个要定位的序列，先算出起点偏移 `newoff`：`beg` 为 0，`cur` 为下一指针减去起始指针（`gptr() - eback()` 或 `pptr() - pbase()`），`end` 为 high mark 减去起始指针。下一指针为空而 `newoff` 不为 0 时失败。

¶11 如果 `newoff + off` 小于 0，或者指向未初始化的字符，定位失败；否则把下一指针设到 `newoff + off` 处。¶12 成功时返回新位置，失败时返回 `pos_type(off_type(-1))`。条文在这里沿用了 `newoff` 这个名字，实际指定位之后的偏移：本机 libc++ 上从偏移 2 出发调用 `pubseekoff(1, cur, in)` 返回 3。

¶13–¶14 `seekpos(sp, which)` 等价于 `seekoff(off_type(sp), beg, which)`。

```cpp title="stringbuf-seek.cpp" run ok
#include <iostream>
#include <sstream>

int main() {
  std::stringstream s("abc");
  auto* sb = s.rdbuf();
  std::cout << sb->pubseekoff(0, std::ios_base::cur) << '\n';  // -1：in|out 加 cur
  std::cout << s.tellg() << ' ' << s.tellp() << '\n';         // 0 0
}
```

`tellg()` 传的 `which` 是 `in`，`tellp()` 传的是 `out`（[[input.streams]]、[[output.streams]]），各自只定位一个序列，所以都能工作。只有直接调用 `pubseekoff` 并使用默认的 `which` 时才会碰到这条规则。

## 构造 [stringbuf.cons]

| 构造函数 | 效果 |
|---|---|
| `basic_stringbuf()` | 委托给 `basic_stringbuf(in \| out)` |
| `explicit basic_stringbuf(which)` | ¶1–¶2 内容为空；六个指针是否初始化为空由实现定义 |
| `basic_stringbuf(const string& s, which = in \| out)` | ¶3 复制 `s` 到 `buf`，再调用 `init-buf-ptrs()` |
| `basic_stringbuf(string&& s, which = in \| out)` {{c++20}} | ¶6 把 `s` 移进 `buf`，不复制 |
| 带分配器、或字符串分配器类型不同的重载 | ¶4–¶5、¶7–¶9 |
| `basic_stringbuf(const T& t, which, a)` 等 {{c++26}} | ¶10–¶12 `t` 能转换为 `basic_string_view` 时可用，先转成 `string_view` 再初始化 `buf` |

C++26 的 `string_view` 重载让 `std::istringstream in(sv);` 不必先写 `std::string(sv)`。不过 `buf` 仍然会复制一份字符；不想复制，见 [[span.streams]]。

¶13–¶14 移动构造把 `rhs` 的内容移过来。新对象里的指针是不是 `rhs` 原来的值由实现定义，但读写位置的偏移与移动前相同，指针也不会与 `rhs` 共享缓冲区；`rhs` 变为空但仍可使用。移动赋值（[stringbuf.assign] ¶1）的结果与移动构造相同。

## 三个流类 [istringstream]、[ostringstream]、[stringstream]

三个类的结构相同：分别派生自 `basic_istream`、`basic_ostream`、`basic_iostream`，持有一个说明专用的成员 `basic_stringbuf sb`，构造函数与 `basic_stringbuf` 的一一对应。构造时实际传给 `sb` 的模式如下：

| 类 | 默认 `which` | 传给 `sb` 的模式 |
|---|---|---|
| `basic_istringstream` | `in` | `which \| in` |
| `basic_ostringstream` | `out` | `which \| out` |
| `basic_stringstream` | `out \| in` | `which` |

所以 `istringstream` 总能读，`ostringstream` 总能写，传入的 `which` 只能增加模式，例如 `ate`。

其余成员都转发给 `sb`：

- `rdbuf()` 是 `const` 成员函数，返回 `const_cast` 之后的 `basic_stringbuf*`（[istringstream.members] ¶1 等）。它隐藏了 `basic_ios::rdbuf()`，而且没有 `rdbuf(sb)` 这个设置用的重载，所以通过派生类调用 `ss.rdbuf(other)` 编译不过。
- `str()`、`view()`、`str(s)` 等价于对 `rdbuf()` 调用同名函数。
- 移动构造先移动基类和 `sb`，再调用 `set_rdbuf(addressof(sb))`，让基类指向自己的 `sb`（[istringstream.cons] ¶11 等）。`swap` 交换基类和 `sb`。

## 重用一个流

```cpp title="reuse.cpp" run ok
#include <iostream>
#include <sstream>

int main() {
  std::stringstream c;
  c << "first";
  int n;
  c >> n;                        // 读失败：failbit
  c.str("");                     // 只换内容
  c << "second";                 // 流仍处于失败状态，什么也没写
  std::cout << '[' << c.str() << "] fail=" << c.fail() << '\n';  // [] fail=1
  c.clear();
  c << "second";
  std::cout << '[' << c.str() << "]\n";                          // [second]
}
```

`str(s)` 只重置 `basic_stringbuf` 的缓冲区和指针，流对象上的状态位（`failbit`、`eofbit`）属于 `basic_ios`，不受影响。状态位不为零时，格式化输入输出一开始就失败。格式标志（`hex`、`precision` 等）同样会保留。重用一个流要 `str("")` 再 `clear()`，或者干脆构造一个新的。

## 常见误解

!!! pitfall "`ostringstream os(\"prefix\");` 之后写入的内容会接在后面"
    不会，写入从开头覆盖。要续写，构造时加 `std::ios_base::ate`。

!!! pitfall "`flush()` 或 `std::endl` 会让字符串流做点什么"
    `basic_stringbuf` 没有覆写 `sync`，基类版本什么也不做。字符写进去就已经在缓冲区里了，`endl` 只是多写了一个 `'\n'`。

!!! pitfall "转换单个数值时字符串流是最简单的选择"
    写起来简单，但每次都要构造流、查询 locale。`std::from_chars`、`std::to_chars`（[[charconv]]）不依赖 locale、不分配内存，还能报告出错位置；格式化输出可以用 `std::format`（[[format]]）。字符串流的长处在于能复用类型已有的 `operator<<` 和 `operator>>`。

## 思考题

!!! question "思考题 1"
    下面的程序输出什么？
    ```cpp
    std::ostringstream os;
    os << "abcdef";
    os.seekp(2);
    std::cout << os.view() << ' ' << os.str().size();
    ```

<details markdown="1">
<summary>答案</summary>

输出 `abcdef 6`。`seekp(2)` 只移动了 `pptr()`，high mark 仍在 6。`view()` 在含 `out` 的模式下返回 `[pbase(), high mark)`（[[stringbuf.members#12]]），`str()` 是它的副本。对比 [[span.streams]]：`ospanstream::span()` 返回的是 `[pbase(), pptr())`，同样的操作之后长度是 2。
</details>

!!! question "思考题 2"
    `std::stringstream ss("abc"); ss.seekg(0, std::ios_base::end);` 之后 `ss.tellp()` 是多少？

<details markdown="1">
<summary>答案</summary>

是 0。`seekg` 传的 `which` 是 `in`，只定位输入序列（[[stringbuf.virtuals#9]]），`pptr()` 仍在开头。`stringbuf` 的读位置和写位置相互独立，这一点与 [[file.streams]] 不同：文件流的两个序列共享同一个文件位置。
</details>

<details class="fine" markdown="1"><summary>其余条文</summary>

[sstream.syn] 声明四个类模板、它们的非成员 `swap`，以及 `stringbuf`、`istringstream`、`ostringstream`、`stringstream` 和对应的 `w` 前缀别名。¶1 说明这些类把流缓冲区与 `basic_string` 对象关联起来。

[stringbuf.assign] ¶3–¶5：`swap` 要求两个对象的分配器相等，或者 `propagate_on_container_swap` 为真；它是 `noexcept` 的，当且仅当 `propagate_on_container_swap` 或 `is_always_equal` 为真。这与容器的规则相同（[[container.reqmts]]）。¶6 非成员 `swap` 等价于 `x.swap(y)`。

[stringbuf.virtuals] ¶15–¶16：`setbuf(s, n)` 的效果由实现定义，只规定 `setbuf(0, 0)` 没有效果；返回 `this`。

[istringstream.swap]、[ostringstream.swap]、[stringstream.swap]：成员 `swap` 先交换基类，再交换 `sb`；非成员 `swap` 等价于 `x.swap(y)`。

</details>
