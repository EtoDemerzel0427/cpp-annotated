---
title: 流迭代器
summary: istream_iterator、ostream_iterator 经 >> 和 << 做格式化读写，istreambuf_iterator、ostreambuf_iterator 直接逐字符读写流缓冲；它们让算法可以直接作用于输入输出流。
status: done
covers: *
since: c++98
related: predef.iterators, default.sentinel, input.iterators, output.iterators, iterator.requirements, iostream.format, stream.buffers, dcl.ambig.res, iterators.counted
tags: 标准库, 迭代器, 流, iostream
updated: 2026-10-19
---

!!! tldr
    - `istream_iterator<T>` 用 `>>` 读取，构造时就读入第一个值，读失败后变成流末迭代器；`==` 只比较绑定的流指针。
    - `ostream_iterator<T>` 用 `<<` 写出，分隔串写在每个元素之后，所以末尾总会多一个分隔符。
    - `istreambuf_iterator<charT>` 直接从流缓冲逐字符读取，不跳过空白；`*` 不消费字符，`++` 才消费。
    - `ostreambuf_iterator<charT>` 逐字符写入，写失败后静默丢弃后续字符，只能通过 `failed()` 得知。
    - `std::string s(std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>());` 声明的是一个函数，要改用花括号。

## 四个类模板 [stream.iterators.general]

¶1 为了让算法模板能直接作用于输入输出流，标准库提供了几个类似迭代器的类模板。例 1 从 `cin` 读入浮点数，把部分和逐行打印到 `cout`：

```cpp
partial_sum(istream_iterator<double, char>(cin),
            istream_iterator<double, char>(),
            ostream_iterator<double, char>(cout, "\n"));
```

四个类模板按两个维度划分：

| | 格式化：经 `>>`、`<<`，作用于 `basic_istream`、`basic_ostream` | 非格式化：逐字符，作用于 `basic_streambuf` |
|---|---|---|
| 输入 | `istream_iterator<T>` | `istreambuf_iterator<charT>` |
| 输出 | `ostream_iterator<T>` | `ostreambuf_iterator<charT>` |

本章其他适配器多数在独立实现中也要提供，流迭代器不是（[[iterator.synopsis]]），因为它们依赖 iostream。

```cpp run title="stream_iters.cpp" ok
#include <algorithm>
#include <cassert>
#include <iterator>
#include <sstream>
#include <string>
#include <vector>

int main() {
  // istreambuf_iterator：原样读入全部字符，包括空白
  std::istringstream in1("a b  c\n");
  std::string s{std::istreambuf_iterator<char>(in1),
                std::istreambuf_iterator<char>()};
  assert(s == "a b  c\n");

  // istream_iterator<char>：经 operator>> 读入，跳过空白
  std::istringstream in2("a b  c\n");
  std::string t{std::istream_iterator<char>(in2),
                std::istream_iterator<char>()};
  assert(t == "abc");

  // ostream_iterator：分隔串写在每个元素之后
  std::ostringstream os;
  std::vector<int> v{1, 2, 3};
  std::ranges::copy(v, std::ostream_iterator<int>(os, ", "));
  assert(os.str() == "1, 2, 3, ");

  // 构造时就读取；可以与 default_sentinel 比较
  std::istringstream in3("10 20");
  std::istream_iterator<int> it(in3);
  assert(*it == 10);
  ++it;
  ++it;                        // 读失败，变为流末迭代器
  assert(it == std::default_sentinel);
  assert(it == std::istream_iterator<int>());

  // ostreambuf_iterator
  std::ostringstream os2;
  auto r = std::ranges::copy(std::string("hi"),
                             std::ostreambuf_iterator<char>(os2));
  assert(os2.str() == "hi" && !r.out.failed());
}
```

## istream_iterator [istream.iterator]

[istream.iterator.general] ¶1 `istream_iterator` 是一个输入迭代器（[[input.iterators]]），从构造时绑定的输入流读取连续的元素。

```cpp
template<class T, class charT = char,
         class traits = char_traits<charT>,
         class Distance = ptrdiff_t>
class istream_iterator {
public:
  using iterator_category = input_iterator_tag;
  using value_type        = T;
  using difference_type   = Distance;
  using pointer           = const T*;
  using reference         = const T&;
  // ...
private:
  basic_istream<charT, traits>* in_stream;  // 说明专用
  T value;                                  // 说明专用
};
```

它内部只有两样东西：指向流的指针，和最近读到的值。¶2 要求 `T` 可默认构造、可复制构造、可复制赋值。

### 构造时就读取 [istream.iterator.cons]

¶1–¶2 默认构造函数和 `istream_iterator(default_sentinel_t)` 构造**流末迭代器**（end-of-stream iterator）：`in_stream` 为空指针。¶3 如果 `T()` 是常量初始化器，这两个构造函数是 constexpr 的，流末迭代器因此可以是编译期常量。

¶4 `istream_iterator(istream_type& s)` 保存 `addressof(s)`，值初始化 `value`，然后调用 `operator++()`。所以构造的时候就已经读入了第一个值。

¶5–¶7 复制构造函数复制两个成员，异常规格等价于 `is_nothrow_copy_constructible_v<T>`；`T` 可平凡析构时，析构函数也是平凡的。

### 操作 [istream.iterator.ops]

¶1–¶4 `*it` 返回 `value`，`it->` 返回 `addressof(value)`，前置条件都是 `in_stream` 非空。返回的是迭代器内部成员的引用，迭代器递增或销毁后这个引用就变了或失效了。[[iterator.requirements.general#15]] 允许前向以下的迭代器这样做。

¶5–¶7 `++it` 等价于：

```cpp
if (!(*in_stream >> value)) in_stream = nullptr;
```

读失败，包括到达文件尾和格式不符，都会把迭代器变成流末迭代器。后置 `++` 声明为 `= default`，效果是复制、前置递增、返回副本（[[over.inc.default]]）。

¶8 `x == y` 返回 `x.in_stream == y.in_stream`，只比较流指针，不比较读到的值。¶9 `i == default_sentinel` 返回 `!i.in_stream`。

所以两个流末迭代器相等；两个绑定同一个流、都没到末尾的迭代器也相等，即使它们的 `value` 不同；绑定不同流的迭代器不相等。算法拿流迭代器唯一需要做的比较是判断有没有到末尾，这些语义已经够用。

## ostream_iterator [ostream.iterator]

[ostream.iterator.general] ¶1 `ostream_iterator` 用 `<<` 把连续的元素写到构造时绑定的输出流。如果构造时给了一个 `charT*`，这个**分隔串**（delimiter string）会在每个 `T` 写出之后写出。

```cpp
template<class T, class charT = char,
         class traits = char_traits<charT>>
class ostream_iterator {
public:
  using iterator_category = output_iterator_tag;
  using value_type        = void;
  using difference_type   = ptrdiff_t;
  using pointer           = void;
  using reference         = void;
  ostream_iterator(ostream_type& s);
  ostream_iterator(ostream_type& s, const charT* delimiter);
  ostream_iterator& operator=(const T& value);
  ostream_iterator& operator*();
  ostream_iterator& operator++();
  ostream_iterator& operator++(int);
private:
  basic_ostream<charT, traits>* out_stream;  // 说明专用
  const charT* delim;                        // 说明专用
};
```

[ostream.iterator.cons.des] ¶1–¶2 构造函数只保存流的地址和分隔串的指针，所以分隔串必须在迭代器使用期间一直存活。

[ostream.iterator.ops] ¶1 赋值做的事情如同：

```cpp
*out_stream << value;
if (delim) *out_stream << delim;
return *this;
```

¶2–¶3 `operator*` 和 `operator++` 都返回 `*this`，于是 `*it++ = x` 最终就是调用赋值。插入迭代器也是这样设计的（[[insert.iterators]]）。

赋值运算符的参数是 `const T&`，所以向 `ostream_iterator<int>` 写 `double` 会先转换成 `int`。`difference_type` 是 `ptrdiff_t`，它因此建模 `output_iterator`，可以交给 `ranges::copy`。

分隔串在每个元素之后写出，`1, 2, 3, ` 的末尾总有一个多余的分隔符。只是想打印一个容器时，C++23 的 `std::print("{}", v)` 或 `views::join_with` 更合适。

## istreambuf_iterator [istreambuf.iterator]

[istreambuf.iterator.general] ¶1 `istreambuf_iterator` 从构造时绑定的流缓冲读取连续的字符。`operator*` 访问当前字符，`operator++` 前进到下一个字符。到达流尾时，也就是 `sgetc()` 返回 `traits::eof()` 时，迭代器变得等于流末迭代器。默认构造函数和 `istreambuf_iterator(nullptr)` 都构造流末迭代器。

¶1 最后还要求所有特化都有平凡的复制构造函数、constexpr 默认构造函数和平凡的析构函数。它实际上就是一个包装起来的 `streambuf*`，可以像指针一样随意复制。

```cpp
template<class charT, class traits = char_traits<charT>>
class istreambuf_iterator {
public:
  using iterator_category = input_iterator_tag;
  using value_type        = charT;
  using difference_type   = traits::off_type;
  using pointer           = unspecified;
  using reference         = charT;   // 不是引用
  // ...
  charT operator*() const;
  istreambuf_iterator& operator++();
  proxy operator++(int);
  bool equal(const istreambuf_iterator& b) const;
private:
  streambuf_type* sbuf_;             // 说明专用
};
```

它不经过格式化：直接调用流缓冲的 `sgetc()`、`sbumpc()`，不跳过空白，不做与 locale 相关的数字解析，也不设置流的状态位。所以它比 `istream_iterator<char>` 快得多，而且保留空白。`reference` 是按值的 `charT`，因此它不满足前向迭代器的要求。

¶2 对流末迭代器调用 `operator*` 是 {{ub}}。

### 构造与操作

[istreambuf.iterator.cons] ¶1 `sbuf_` 是空指针，当且仅当迭代器是流末迭代器。¶2–¶5 可以从 `default_sentinel_t`、`istream&`（取 `s.rdbuf()`）、`streambuf*` 和 *`proxy`* 构造。

[istreambuf.iterator.ops] ¶1 `*it` 返回 `sbuf_->sgetc()`，不消费字符。¶2–¶3 `++it` 如同 `sbuf_->sbumpc()`，这一步才消费字符。

¶4 后置 `++` 返回 *`proxy`*`(sbuf_->sbumpc(), sbuf_)`。[istreambuf.iterator.proxy] ¶1 *`proxy`* 是说明专用的类，成员 `keep_` 保存递增前的字符，`operator*` 返回它，所以 `*it++` 拿到的是递增前的字符。实现不必提供叫 `proxy` 的类，功能等价即可。

¶5 `a.equal(b)` 当且仅当两个迭代器都在流末，或者都不在流末时返回 `true`，不管它们用的是哪个流缓冲。¶6 `a == b` 就是 `a.equal(b)`。¶7 与 `default_sentinel` 比较就是与流末迭代器 `equal`。

这比 `istream_iterator` 的 `==` 更粗：两个读不同文件、都没读完的 `istreambuf_iterator` 也相等。判断是否到了流末要调用 `sgetc()`，所以比较本身就可能触发底层的读取。

## ostreambuf_iterator [ostreambuf.iterator]

[ostreambuf.iterator.general] ¶1 `ostreambuf_iterator` 把连续的字符写到构造时绑定的输出流。

- [ostreambuf.iter.cons] ¶1–¶4 从 `ostream&` 构造时，前置条件是 `s.rdbuf()` 非空；从 `streambuf*` 构造时，前置条件是指针非空。
- [ostreambuf.iter.ops] ¶1–¶2 `it = c`：如果 `failed()` 为 `false`，调用 `sbuf_->sputc(c)`；否则什么也不做。
- ¶3–¶4 `operator*` 和 `operator++` 返回 `*this`。
- ¶5 之前任何一次赋值中 `sputc()` 返回了 `traits::eof()`，`failed()` 就为 `true`。

写失败一次之后，后续的字符都被静默丢弃。写完检查 `failed()` 是得知写入失败的唯一途径。

## 陷阱：声明了一个函数

```cpp run title="vexing.cpp"
#include <iterator>
#include <sstream>
#include <string>

int main() {
  std::istringstream in("hello");
  std::string s(std::istreambuf_iterator<char>(in),
                std::istreambuf_iterator<char>());
  (void)s;   // s 是函数名，什么也没读
}
```

这段代码良构，但 `s` 不是字符串，而是一个函数的声明。第一个形参名叫 `in`，类型是 `istreambuf_iterator<char>`，外面多了一层括号；第二个形参没有名字，类型是返回 `istreambuf_iterator<char>` 的无参函数（调整为函数指针）。本机 Clang 23 给出警告 `parentheses were disambiguated as a function declaration [-Wvexing-parse]`。

依据 [[dcl.ambig.res]]，一条语句既能解释成声明、又能解释成表达式时，按声明处理。修正方法任选一种：

- 用花括号：`std::string s{std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>()};`，就是前面完整例子的写法；
- 给第一个实参再加一层括号：`std::string s((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());`；
- 先给迭代器起名：`std::istreambuf_iterator<char> b(in), e; std::string s(b, e);`。

## 常见误解

!!! pitfall "构造 `istream_iterator` 不会读取"
    构造时就读入第一个值。创建一个 `istream_iterator` 而不使用，也会消费输入；在交互程序里会阻塞等待输入。与 `counted_iterator`、`views::take` 组合时还会多读一个（[[iterators.counted]]）。

!!! pitfall "用 `istream_iterator<char>` 读文本"
    它经 `>>` 读取，会跳过所有空白。要原样读字符，用 `istreambuf_iterator<char>`，或者先对流设置 `std::noskipws`。

## 思考题

!!! question "思考题 1"
    输入是 `"12 abc 34"`，`std::istream_iterator<int> b(in); std::vector<int> v(b, {});` 得到什么？流处于什么状态？

<details markdown="1">
<summary>答案</summary>

`v` 是 `{12}`。读 `12` 成功；读 `abc` 时 `>>` 失败，设置 `failbit`，迭代器变成流末迭代器，构造到此结束。`34` 没有被读取，流处于失败状态，要继续读必须先 `clear()` 并跳过坏数据。`{}` 能用，是因为构造函数的两个参数是同一个模板参数，类型由第一个实参推导，`{}` 就值初始化出一个流末迭代器。
</details>

!!! question "思考题 2"
    `std::istringstream in("abc");` 之后，`auto a = std::istreambuf_iterator<char>(in); auto b = a; ++a;`，`*b` 是什么？

<details markdown="1">
<summary>答案</summary>

`'b'`。`a` 和 `b` 只是同一个 `streambuf*` 的两份副本，没有各自的位置。`++a` 让流缓冲消费了 `'a'`，之后 `*b` 调用 `sgetc()`，看到的是流缓冲当前的字符 `'b'`。这就是单遍输入迭代器的含义：递增一个副本会让其他副本也跟着变。
</details>
