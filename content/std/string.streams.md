---
title: 字符串流
summary: basic_stringbuf 如何用一个 basic_string 同时充当 get 区和 put 区——high mark、init-buf-ptrs 的指针布局、ate 与覆盖写、overflow 的扩容、seekoff 的两张表（in|out 同时以 cur 定位会失败）；str() 复制、str()&& 移出、view() 不复制但可能悬垂（C++20），从 string_view 构造（C++26）；istringstream/ostringstream/stringstream 的构造与移动，以及重用 stringstream 时必须 clear() 等陷阱
status: done
covers: *
related: stream.buffers, input.streams, output.streams, span.streams, basic.string, string.view, iostreams.base, format
tags: 标准库, iostream, stringstream, 内存流
updated: 2026-10-18
---

`<sstream>` 中的四个类模板把流接到一个 `basic_string` 上：`basic_stringbuf` 是 streambuf，`basic_istringstream`/`basic_ostringstream`/`basic_stringstream` 是持有一个 `basic_stringbuf` 成员的流。它们常用来做"字符串 ↔ 值"的转换和在内存里拼装输出。理解它们只需要搞清一件事：**`basic_stringbuf` 如何把同一个字符串缓冲区同时作为 get 区和 put 区**。

## `<sstream>` 概要（[sstream.syn]）

声明四个类模板（模板参数都是 `charT`、`traits`、`Allocator`）、它们的非成员 `swap`，以及 `stringbuf`、`istringstream`、`ostringstream`、`stringstream` 和对应的 `w` 前缀别名。¶1：定义四个类模板和八个类型，把流缓冲区与 `basic_string` 对象关联起来（[[string.classes]]）。

## `basic_stringbuf`（[stringbuf]）

### 数据模型（[stringbuf.general]）

```cpp
template<class charT, class traits = char_traits<charT>, class Allocator = allocator<charT>>
class basic_stringbuf : public basic_streambuf<charT, traits> {
  // ……构造函数、str()/view()/get_allocator()……
protected:
  int_type underflow() override;
  int_type pbackfail(int_type c = traits::eof()) override;
  int_type overflow (int_type c = traits::eof()) override;
  basic_streambuf<charT, traits>* setbuf(charT*, streamsize) override;
  pos_type seekoff(off_type off, ios_base::seekdir way, ios_base::openmode which = in | out) override;
  pos_type seekpos(pos_type sp, ios_base::openmode which = in | out) override;
private:
  ios_base::openmode mode;                       // 说明专用
  basic_string<charT, traits, Allocator> buf;    // 说明专用
  void init-buf-ptrs();                          // 说明专用
};
```

¶1：`basic_stringbuf` 把输入序列和（或）输出序列与一个任意字符序列关联，该序列可以从 `basic_string` 初始化，也可以以 `basic_string` 的形式取出。¶2 的说明专用成员：

- `mode`：可读则含 `in`，可写则含 `out`；
- `buf`：底层字符序列；
- `init-buf-ptrs()`：在初始化、移动或赋值 `buf` 之后设置基类的 get 区和 put 区指针。

注意它**没有**覆写 `uflow`、`xsgetn`、`xsputn`、`sync`、`showmanyc`、`imbue`——全靠基类的默认实现加上 get/put 区就够了。

### high mark 与指针布局（[stringbuf.members] ¶1–¶4）

¶1 引入一个概念：**high mark**——缓冲区中"最高的已初始化字符"之后的位置。字符可以通过写入流、通过以 `basic_string` 构造、或通过调用 `str(s)` 而被初始化；后一种情形下，调用之前初始化的字符都被视为未初始化（除非被新字符串重新初始化）。所有"取出底层序列"的成员都以 high mark 为界。

`init-buf-ptrs()` 的后条件（¶3）：

- 若 `mode` 含 `out`：`pbase()` 指向 `buf.front()`，`epptr() >= pbase() + buf.size()`；此外若含 `ate`，`pptr() == pbase() + buf.size()`（从末尾续写），**否则 `pptr() == pbase()`（从开头覆盖写）**。
- 若 `mode` 含 `in`：`eback()` 指向 `buf.front()`，`gptr() == eback()`，`egptr() == eback() + buf.size()`。

```text
 stringstream ss("hello");                 mode = in | out
 buf:      [ h  e  l  l  o  ·  ·  · ]      （· = capacity 中尚未初始化的部分）
 get 区:    eback=gptr            egptr
 put 区:    pbase=pptr                  epptr（可能 ≥ size）
 high mark:                ↑ （size 处）
```

¶4（注）：出于效率，stringbuf 的操作在 `buf` 被封装期间可以**违反 `buf` 的不变式**——例如直接写入 `[buf.data() + buf.size(), buf.data() + buf.capacity())`。所有取出 `basic_string` 的操作都保证返回值满足 `basic_string` 的不变式。这就是 high mark 存在的原因：`buf.size()` 不一定反映写到了哪里。

### 构造函数（[stringbuf.cons]）

| 构造函数 | 效果 |
|---|---|
| `basic_stringbuf()` | 委托给 `basic_stringbuf(in | out)` |
| `explicit basic_stringbuf(which)` | ¶1–¶2 `mode = which`；指针是否初始化为空由实现定义；后条件 `str().empty()` |
| `explicit basic_stringbuf(const string& s, which = in | out)` | ¶3 `buf` 以 `s` 初始化，再 `init-buf-ptrs()` |
| `basic_stringbuf(which, const Allocator& a)` | ¶4–¶5 `buf` 以 `a` 初始化 |
| `explicit basic_stringbuf(string&& s, which = in | out)` | ¶6 `buf` 以 `std::move(s)` 初始化——**不复制** {{c++20}} |
| `basic_stringbuf(const basic_string<…, SAlloc>& s, which, const Allocator& a)` 等 | ¶7–¶9 不同分配器的字符串；`SAlloc` 与 `Allocator` 相同时由上面的重载处理（¶8 *Constraints*） |
| `template<class T> basic_stringbuf(const T& t, which = in | out [, const Allocator& a])` | ¶10–¶12 {{c++26}} *Constraints*：`const T&` 可转换为 `basic_string_view`；先 `basic_string_view sv = t`，再以 `sv, a` 直接非列表初始化 `buf` |
| 移动构造（可带分配器） | ¶13–¶14 见下 |

移动构造（¶13–¶14）：复制构造基类，`mode` 取 `rhs.mode`，`buf` 从 `std::move(rhs).str()` 初始化；**新对象中的指针是否就是 `rhs` 原来的值由实现定义**，但后条件保证读写**位置的偏移**（`gptr() - eback()` 等）与 `rhs` 移动前相同、指针本身与 `rhs` 移动后的不同（不共享缓冲区），locale 相同，`rhs` 变为空但可用。

### 赋值与交换（[stringbuf.assign]）

- 移动赋值：¶1 之后 `*this` 的可观察状态与"从 `rhs` 移动构造"相同。
- `swap`：¶3 前置条件 `propagate_on_container_swap` 为真或两者分配器相等；¶5 `noexcept` 当且仅当 `propagate_on_container_swap || is_always_equal`——与容器的规则相同（[[container.reqmts]]）。

### 取出与设置内容（[stringbuf.members] ¶5–¶19）

| 成员 | 效果 |
|---|---|
| `get_allocator()` | `buf.get_allocator()` |
| `str() const &` | ¶6 `return basic_string(view(), get_allocator());`——**复制** |
| `str(const SAlloc& sa) const` | ¶7–¶8 用另一个分配器复制 {{c++20}} |
| `str() &&` | ¶9–¶10 把底层序列**移出**（先把 `buf` 调整为与 `view()` 相同的内容），之后 `buf` 为空、指针按空 `buf` 重新初始化 {{c++20}} |
| `view() const noexcept` | ¶11–¶12 返回指向底层序列的 `basic_string_view`：含 `out` 时为 `[pbase(), high_mark)`，否则含 `in` 时为 `[eback(), egptr())`，否则为空 {{c++20}} |
| `str(const string& s)`、`str(string&&)`、`str(const basic_string<…, SAlloc>&)` | ¶14–¶17 `buf = s`（或移动），然后 `init-buf-ptrs()` |
| `template<class T> str(const T& t)` | ¶18–¶19 {{c++26}} 经 `basic_string_view` 赋值 |

¶13（注）：在 `*this` 的底层序列被销毁或失效之后使用 `view()` 返回的对象是未定义行为（除非它为空）。"失效"包括继续写入导致扩容：

```cpp title="view-dangling.cpp" ub
#include <iostream>
#include <sstream>
#include <string_view>

int main() {
  std::ostringstream os;
  os << "short";
  std::string_view v = os.view();
  os << std::string(1000, 'x');      // 扩容：底层数组被重新分配
  std::cout << v << '\n';            // UB：v 指向已释放的内存
}
```

### 覆写的虚函数（[stringbuf.virtuals]）

- **`underflow()`**：¶1 有读位置可用时返回 `*gptr()`，否则返回 `eof()`。**底层缓冲区中任何已初始化的字符都被视为输入序列的一部分**——这句话的意思是：在 `in | out` 模式下，写进去的字符随后就能读出来（`overflow` 扩容时会同时推进 `egptr()`，见下）。
- **`pbackfail(c)`**：¶2 三种方式之一：
    1. `c` 不是 `eof()`、有回退位置、且 `c` 等于 `gptr()[-1]`：`gptr()` 减一，返回 `c`；
    2. `c` 不是 `eof()`、有回退位置、且 `mode` 含 `out`：把 `c` 存到 `*--gptr()`，返回 `c`——**只有可写的 stringbuf 才允许回退一个不同的字符**；
    3. `c` 是 `eof()` 且有回退位置：`gptr()` 减一，返回 `not_eof(c)`。
  
  ¶3 否则返回 `eof()`。¶4 多种方式都可行时选哪一种是未指定的。
- **`overflow(c)`**：¶5 `c` 不是 `eof()` 时，若有写位置或能**创造**写位置，调用 `sputc(c)` 并返回 `c`；`c` 是 `eof()` 时没有字符要追加，返回非 `eof()` 值表示成功。¶7：函数可以在任何调用中改变可用写位置的数量。¶8：只有 `mode` 含 `out` 时才能创造写位置——重新分配（或首次分配）一个数组对象，大小足以容纳当前数组**外加至少一个**写位置；若 `mode` 含 `in`，同时把 `egptr()` 改为指向新写位置之后。
- **`seekoff(off, way, which)`**：¶9 按表 144 决定定位哪个序列：

| 条件 | 结果 |
|---|---|
| `which` 含 `in` | 定位输入序列 |
| `which` 含 `out` | 定位输出序列 |
| `which` 同时含 `in` 和 `out`，**且 `way` 是 `beg` 或 `end`** | 同时定位两个序列 |
| 其他 | 定位失败 |

  也就是说：`which` 为 `in | out`（默认实参）且 `way == cur` 时**失败**——因为两个序列的"当前位置"可能不同，无法确定相对于谁。¶10：按表 145 计算 `newoff`：`beg` 为 0，`cur` 为 `xnext - xbeg`，`end` 为 **`high_mark - xbeg`**；下一指针为空而 `newoff` 非零时失败。¶11：`newoff + off` 小于 0 或指向未初始化字符时失败，否则 `xnext = xbeg + newoff + off`。¶12：返回由"结果偏移"构造的 `pos_type`——条文在这里沿用了 `newoff` 这个名字，指的是定位之后的位置（本机 libc++ 上 `pubseekoff(1, cur, in)` 从偏移 2 出发返回 3）；定位失败或无法表示时返回 `pos_type(off_type(-1))`。
- **`seekpos(sp, which)`**：¶13 等价于 `seekoff(off_type(sp), beg, which)`。
- **`setbuf(s, n)`**：¶15 效果由实现定义，但 `setbuf(0, 0)` 无效果。

```cpp title="stringbuf-seek.cpp" ok
#include <iostream>
#include <sstream>

int main() {
  std::stringstream ss;
  int a, b;
  ss << "12 34";
  ss >> a >> b;                              // 写进去的字符随即可读
  std::cout << a << ' ' << b << '\n';        // 12 34

  std::stringstream s2("abc");
  std::cout << s2.rdbuf()->pubseekoff(0, std::ios_base::cur) << ' ';  // -1：in|out 同时以 cur 定位
  std::cout << s2.tellg() << ' ' << s2.tellp() << '\n';               // 0 0：各自只定位一个序列
}
```

`tellg()` 传的是 `in`、`tellp()` 传的是 `out`（[[input.streams]]、[[output.streams]]），所以它们都能工作；直接调用 `pubseekoff` 而不给 `which` 时才会碰到这条规则。

## 三个流类（[istringstream]、[ostringstream]、[stringstream]）

三者结构相同：派生自 `basic_istream` / `basic_ostream` / `basic_iostream`，持有一个说明专用的 `basic_stringbuf sb` 成员。

| 类 | 默认 `which` | 构造 `sb` 时实际使用的模式 |
|---|---|---|
| `basic_istringstream` | `in` | `which | in` |
| `basic_ostringstream` | `out` | `which | out` |
| `basic_stringstream` | `out | in` | `which` |

也就是说，`istringstream` 总能读、`ostringstream` 总能写，你传入的 `which` 只能**增加**模式（如 `ate`）。构造函数（[istringstream.cons] ¶1–¶10 等）都是"以 `addressof(sb)` 初始化基类、以相应实参初始化 `sb`"，与 `basic_stringbuf` 的构造函数一一对应，包括 C++26 的 `string_view` 版本。

- 移动构造（[istringstream.cons] ¶11 等）：移动构造基类和 `sb`，然后调用 `set_rdbuf(addressof(sb))` 安装**自己的** `sb`。
- `swap`（[istringstream.swap] ¶1 等）：`basic_istream::swap(rhs); sb.swap(rhs.sb);`。
- 成员（[istringstream.members] 等）：`rdbuf()` 返回 `const_cast<basic_stringbuf*>(addressof(sb))`——**`const` 成员函数返回非 `const` 指针**；`str()`、`view()`、`str(s)` 全部转发给 `rdbuf()`。

`rdbuf()` 返回的是派生类型 `basic_stringbuf*`（隐藏了 `basic_ios::rdbuf()`），而且**没有** `rdbuf(sb)` 重载：通过派生类调用 `ss.rdbuf(other)` 会编译失败，要换 streambuf 只能经由基类引用，而那样做之后 `ss.str()` 访问的仍是成员 `sb`，与流实际使用的 streambuf 不一致。

## 常见陷阱

```cpp title="stringstream-pitfalls.cpp" ok
#include <iostream>
#include <sstream>
#include <string>

int main() {
  std::ostringstream a("XXXXXX");                        // 没有 ate：从开头覆盖写
  a << "ab";
  std::cout << a.str() << '\n';                          // abXXXX

  std::ostringstream b("XXXXXX", std::ios_base::ate);    // ate：从末尾续写
  b << "ab";
  std::cout << b.str() << '\n';                          // XXXXXXab

  std::stringstream c;
  c << "first";
  int dummy; c >> dummy;                                 // 读失败：failbit
  c.str("");                                             // 换内容不会清除状态位
  c << "second";
  std::cout << '[' << c.str() << "] fail=" << c.fail() << '\n';   // [] fail=1
  c.clear();                                             // 必须显式 clear()
  c << "second";
  std::cout << '[' << c.str() << "]\n";                  // [second]

  std::ostringstream d;
  d << std::string(100, 'z');
  std::string s = std::move(d).str();                    // 移出缓冲区，不复制
  std::cout << s.size() << ' ' << d.view().size() << '\n';   // 100 0
}
```

1. **用初始字符串构造 `ostringstream` 会覆盖而不是追加**，除非给 `ate`（init-buf-ptrs 的 ¶3.1.2）。标准没有为 stringbuf 单独规定 `app`（`init-buf-ptrs` 只看 `ate`）；本机 libc++ 在构造时把 `app` 当作 `ate` 处理（`ostringstream("XXXX", app) << "ab"` 得到 `XXXXab`），但随后 `seekp(0)` 仍能覆盖开头——并不是文件那种"每次写之前都定位到末尾"的语义。
2. **重用流要 `str("")` 加 `clear()`**：`str(s)` 只重置缓冲区和指针，不碰 `basic_ios` 的状态位；之前的 `failbit`/`eofbit` 会让后续所有操作直接失败。另外格式标志（`hex` 等）也会保留。
3. **`str()` 每次都复制**：循环里反复调用 `os.str()` 是 O(n²)。只读用 `view()`，取走用 `std::move(os).str()`。
4. **`view()` 可能悬垂**：继续写入会扩容（上文 `view-dangling.cpp`）。
5. **`istringstream` 与 `std::stoi` 等的取舍**：转换单个数值时，`std::from_chars`（[[charconv]]）不依赖 locale、不分配、可以精确报告错误位置，比构造一个 `istringstream` 快得多；`std::format` 同理之于 `ostringstream`（[[format]]）。字符串流的优势在于可以复用已有的 `operator<<`/`>>`。

## 思考题

<details markdown="1">
<summary>1. <code>std::istringstream in("abc"); in.get(); in.putback('z');</code> 成功吗？换成 <code>std::stringstream</code> 呢？</summary>

`istringstream` 的 `sb` 模式是 `in`（不含 `out`）。`putback('z')` → `sputbackc('z')`，`'z'` 与 `gptr()[-1]`（`'a'`）不同，于是调用 `pbackfail('z')`；方式 1 不适用（字符不同），方式 2 要求 `mode` 含 `out`，也不适用，于是返回 `eof()`，`putback` 置 `badbit`（[[stringbuf.virtuals#2]]）。`stringstream` 的模式含 `out`，方式 2 适用：把 `'z'` 写到缓冲区第一个字符处，成功，之后读出 `"zbc"`。
</details>

<details markdown="1">
<summary>2. <code>std::ostringstream os; os &lt;&lt; "hello"; os.seekp(0); os &lt;&lt; "J"; os.str()</code> 是什么？<code>os.seekp(0, std::ios_base::end)</code> 定位到哪里？</summary>

`"Jello"`：`seekp(0)` 把 `pptr()` 移回开头，写入 `J` 覆盖了 `h`，但 high mark 仍在 5，所以 `str()` 返回 5 个字符（[[stringbuf.members#1]]、¶12.1）。`seekp(0, end)` 定位到 high mark，即偏移 5——表 145 中 `end` 的 `newoff` 是 `high_mark - xbeg`，而不是 `pptr()`。
</details>

## 小结

- `basic_stringbuf` = 一个 `basic_string` + `mode`；`init-buf-ptrs` 让 get 区覆盖已有内容、put 区从开头（或 `ate` 时从末尾）开始。
- high mark 记录写到过的最远位置，`str()`/`view()`/`seekoff(end)` 都以它为界。
- 可写时 `overflow` 扩容并同步推进 `egptr()`，所以 `stringstream` 写入的内容立即可读。
- `seekoff` 同时定位两个序列时不允许 `cur`。
- C++20 起 `str()&&` 和 `view()` 避免复制，`string&&` 构造避免复制；C++26 起可直接从 `string_view` 构造和赋值。
