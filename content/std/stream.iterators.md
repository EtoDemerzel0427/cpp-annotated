---
title: 流迭代器
summary: istream_iterator（构造时即读第一个值、经 operator>> 格式化读取、读失败变为流末迭代器、只比较流指针）、ostream_iterator（每写一个值后都写分隔串，包括最后一个）、istreambuf_iterator（直接从 streambuf 逐字符读、不跳空白、后置 ++ 返回 proxy、"相等"只看是否都在流末）、ostreambuf_iterator（逐字符 sputc，failed() 报告写失败）；它们可与 default_sentinel 比较；读文件进 string 的"最令人烦恼的解析"。
status: done
covers: *
since: c++98
related: predef.iterators, default.sentinel, input.iterators, output.iterators, iterator.requirements, iostream.format, stream.buffers, dcl.ambig.res, iterators.counted
tags: 标准库, 迭代器, 流, iostream
updated: 2026-10-18
---

¶1 of [stream.iterators.general]：为了让算法模板能直接作用于输入/输出流，库提供了一组"类迭代器"类模板。例 1：

```cpp
partial_sum(istream_iterator<double, char>(cin),
            istream_iterator<double, char>(),
            ostream_iterator<double, char>(cout, "\n"));
```

从 `cin` 读入浮点数，把部分和逐行打印到 `cout`。

四个类模板分两层：

| | 格式化（经 `>>`/`<<`，作用于 `basic_istream`/`basic_ostream`） | 非格式化（逐字符，作用于 `basic_streambuf`） |
|---|---|---|
| 输入 | `istream_iterator<T>` | `istreambuf_iterator<charT>` |
| 输出 | `ostream_iterator<T>` | `ostreambuf_iterator<charT>` |

与本章其他设施不同，流迭代器**不是** freestanding 的（[[iterator.synopsis]]）。

## `istream_iterator`（[istream.iterator]）

¶1 of [istream.iterator.general]：输入迭代器（[[input.iterators]]），从构造时绑定的输入流读取连续元素。

```cpp
template<class T, class charT = char, class traits = char_traits<charT>,
         class Distance = ptrdiff_t>
class istream_iterator {
public:
  using iterator_category = input_iterator_tag;
  using value_type        = T;
  using difference_type   = Distance;
  using pointer           = const T*;
  using reference         = const T&;
  // ...
  constexpr istream_iterator();
  constexpr istream_iterator(default_sentinel_t);
  istream_iterator(istream_type& s);
  // ...
private:
  basic_istream<charT, traits>* in_stream;  // 说明专用
  T value;                                  // 说明专用
};
```

¶2：`T` 须满足 *Cpp17DefaultConstructible*、*Cpp17CopyConstructible*、*Cpp17CopyAssignable*。

**构造**（[istream.iterator.cons]）：

- 默认构造与 `istream_iterator(default_sentinel_t)`：构造**流末迭代器**（[[g:end-of-stream-iterator]]），值初始化 `value`，后条件 `in_stream == nullptr`（¶1–¶2）。¶3：若 `auto x = T();` 中 `T()` 是常量初始化器，这两个构造函数是 constexpr 的——所以流末迭代器可以是编译期常量。
- `istream_iterator(istream_type& s)`：¶4 以 `addressof(s)` 初始化 `in_stream`，值初始化 `value`，**然后调用 `operator++()`**——也就是说，**构造时就读入第一个值**。
- 复制构造：复制 `in_stream` 与 `value`；`noexcept` 等价于 `is_nothrow_copy_constructible_v<T>`（¶5–¶6）。¶7：若 `T` 可平凡析构，析构函数是平凡的。

**操作**（[istream.iterator.ops]）：

- `operator*`、`operator->`：前条件 `in_stream != nullptr`；返回 `value` / `addressof(value)`——**对迭代器内部成员的引用**，这正是 [[iterator.requirements.general#15]] 允许非前向迭代器做的事。
- `operator++()`：前条件 `in_stream != nullptr`；效果 `if (!(*in_stream >> value)) in_stream = nullptr;`——**读失败（包括到达文件尾、格式错误）即变为流末迭代器**。
- 后置 `operator++(int)` 是预置的（[[over.inc.default]]）：复制、前置递增、返回副本。
- `x == y`：`x.in_stream == y.in_stream`（¶8）——**只比较流指针**，不比较读到的值，也不比较"位置"。
- `i == default_sentinel`：`!i.in_stream`（¶9）。

!!! note "“流末”与“同一流”的比较语义"
    两个流末迭代器相等；两个绑定同一流、都未到末尾的迭代器也相等（即便它们的 `value` 不同）；绑定不同流的迭代器不相等。这对算法唯一有意义的用途——"与流末比较"——是足够的。

## `ostream_iterator`（[ostream.iterator]）

¶1 of [ostream.iterator.general]：用 `operator<<` 向构造时绑定的输出流写入连续元素；若构造时给了 `charT*`，这个**分隔串**（*delimiter string*）会在**每个** `T` 写出**之后**写出。

```cpp
template<class T, class charT = char, class traits = char_traits<charT>>
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

- 构造：存 `addressof(s)` 与 `delimiter`（或 `nullptr`）——**只存指针**，分隔串必须在迭代器使用期间保持存活。
- `operator=(const T& value)`：`*out_stream << value; if (delim) *out_stream << delim; return *this;`
- `operator*`、`operator++` 都返回 `*this`（与插入迭代器同样的设计，见 [[insert.iterators]]）。
- `difference_type` 是 `ptrdiff_t`（C++20 起，此前为 `void`），所以它建模 `output_iterator<..., T>`，可用于 `ranges::copy`。

注意赋值运算符的参数是 `const T&`：`ostream_iterator<int>` 写 `double` 会先转换为 `int`。分隔串在**每个**元素之后写出，所以 `1, 2, 3, ` 末尾总有一个多余的分隔符——C++23 的 `std::format("{}", vec)`/`std::print` 或 `views::join_with` 是更好的选择。

## `istreambuf_iterator`（[istreambuf.iterator]）

¶1 of [istreambuf.iterator.general]：从构造时绑定的流缓冲中读取连续**字符**。`operator*` 访问当前字符；每次 `operator++` 前进到下一字符；到达流尾（`sgetc()` 返回 `traits::eof()`）时，迭代器变得等于**流末**值。默认构造与 `istreambuf_iterator(nullptr)` 都构造流末迭代器。所有特化都必须有**平凡**复制构造函数、constexpr 默认构造函数和**平凡**析构函数——它本质上就是一个 `streambuf*`。

¶2：对流末迭代器调用 `operator*` 是 {{ub}}；对其他值返回一个 `char_type`。不能通过输入迭代器赋值字符。

```cpp
template<class charT, class traits = char_traits<charT>>
class istreambuf_iterator {
public:
  using iterator_category = input_iterator_tag;
  using value_type        = charT;
  using difference_type   = traits::off_type;
  using pointer           = unspecified;
  using reference         = charT;          // 不是引用！
  // ...
  charT operator*() const;
  istreambuf_iterator& operator++();
  proxy operator++(int);
  bool equal(const istreambuf_iterator& b) const;
private:
  streambuf_type* sbuf_;                    // 说明专用
};
```

要点：

- **不经格式化**：直接调用 `sbuf_->sgetc()`/`sbumpc()`，不跳过空白、不考虑 `locale` 的数字解析、不设置流的状态位，因而远比 `istream_iterator<char>` 快，而且**保留空白**。
- `reference` 是 `charT`（按值）：它不满足 *Cpp17ForwardIterator*，也不建模 `forward_iterator`。
- 构造（[istreambuf.iterator.cons]）：¶1 `sbuf_` 为空指针时即流末迭代器；可从 `istream&`（取 `s.rdbuf()`）、`streambuf*`、*`proxy`* 构造。
- `operator*`：返回 `sbuf_->sgetc()`；`operator++()`：如同 `sbuf_->sbumpc()`（[istreambuf.iterator.ops] ¶1–¶2）。注意：`operator*` **不消费**字符，`++` 才消费。
- 后置 `++`：返回 *`proxy`*`(sbuf_->sbumpc(), sbuf_)`（¶4）。[istreambuf.iterator.proxy] ¶1：*`proxy`* 是说明专用类，保存"上一个字符"`keep_`，其 `operator*` 返回它——这让 `*it++` 拿到的是递增前的字符。实现可以不提供名叫 `proxy` 的类，只要功能等价。
- `equal(b)`：¶5 当且仅当**两者都在流末或都不在流末**时返回 `true`，**不论用的是哪个 streambuf**。`==` 即 `a.equal(b)`（¶6），与 `default_sentinel` 比较即 `i.equal(s)`（¶7，`default_sentinel` 隐式构造为流末迭代器）。

`equal` 的语义比 `istream_iterator` 的 `==` 还"粗"：两个读不同文件、都没读完的 `istreambuf_iterator` 也相等。判断"是否到末尾"会调用 `sgetc()`，因此比较本身可能触发底层读取。

## `ostreambuf_iterator`（[ostreambuf.iterator]）

¶1：向构造时绑定的输出流写入连续字符。

- 构造（[ostreambuf.iter.cons]）：从 `ostream&`（前条件 `s.rdbuf()` 非空）或 `streambuf*`（前条件非空）。
- `operator=(charT c)`：若 `failed()` 为 `false`，调用 `sbuf_->sputc(c)`；否则无效果（[ostreambuf.iter.ops] ¶1）。
- `operator*`、`operator++` 返回 `*this`。
- `failed()`：若之前任何一次 `operator=` 中 `sputc()` 返回了 `traits::eof()`，则为 `true`（¶5）。一旦失败，后续写入都被静默丢弃——用完后检查 `failed()` 是唯一得知写入失败的途径。

## 例子：读写整个流

```cpp run title="stream_iters.cpp" ok
#include <algorithm>
#include <cassert>
#include <iterator>
#include <sstream>
#include <string>
#include <vector>

int main() {
    // istreambuf_iterator：原样读入全部字符（含空白）
    std::istringstream in1("a b  c\n");
    std::string s{std::istreambuf_iterator<char>(in1), std::istreambuf_iterator<char>()};
    assert(s == "a b  c\n");

    // istream_iterator<char>：经 operator>> 读入，跳过空白
    std::istringstream in2("a b  c\n");
    std::string t{std::istream_iterator<char>(in2), std::istream_iterator<char>()};
    assert(t == "abc");

    // ostream_iterator：分隔串写在每个元素之后
    std::ostringstream os;
    std::vector<int> v{1, 2, 3};
    std::ranges::copy(v, std::ostream_iterator<int>(os, ", "));
    assert(os.str() == "1, 2, 3, ");

    // 构造即读取；与 default_sentinel 比较
    std::istringstream in3("10 20");
    std::istream_iterator<int> it(in3);
    assert(*it == 10);
    ++it; ++it;                                  // 第二次 ++ 读失败 → 流末
    assert(it == std::default_sentinel);
    assert(it == std::istream_iterator<int>());

    // ostreambuf_iterator
    std::ostringstream os2;
    auto out = std::ranges::copy(std::string("hi"), std::ostreambuf_iterator<char>(os2)).out;
    assert(os2.str() == "hi" && !out.failed());
}
```

## 陷阱：最令人烦恼的解析

```cpp run title="vexing.cpp"
#include <iterator>
#include <sstream>
#include <string>

int main() {
    std::istringstream in("hello");
    std::string s(std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>());
    // 上一行声明了一个名为 s 的函数！
    // 第一个"参数"是名为 in、类型为 istreambuf_iterator<char> 的形参，
    // 第二个是类型为"返回 istreambuf_iterator<char> 的无参函数（的指针）"的无名形参。
    // clang：warning: parentheses were disambiguated as a function declaration [-Wvexing-parse]
    (void)s;   // 只是取了函数名，并没有读任何东西
}
```

依据 [[dcl.ambig.res]]，"能被解释为声明的就是声明"。修正方法任选其一：

- 用花括号：`std::string s{std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>()};`（上一节的写法）；
- 给第一个实参多加一层括号：`std::string s((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());`；
- 先给迭代器命名：`std::istreambuf_iterator<char> b(in), e; std::string s(b, e);`。

## 常见误区

!!! pitfall "以为构造 `istream_iterator` 不会读取"
    构造即读第一个值。只是创建一个 `istream_iterator` 而不使用，也会消费输入；在交互程序里这会阻塞等待。配合 `counted_iterator`/`views::take` 时还会多读一个（[[iterators.counted]]）。

!!! pitfall "用 `istream_iterator<char>` 读文本"
    它经 `>>` 读取，会跳过所有空白。要原样读字符，用 `istreambuf_iterator<char>`（或对流设置 `std::noskipws`）。

!!! pitfall "解引用后保存引用"
    `istream_iterator::operator*` 返回对迭代器内部成员的引用；迭代器递增或销毁后，引用指向的值会变化或失效。

## 思考题

!!! question "思考题"
    1. `std::istream_iterator<int>` 遇到输入 `"12 abc 34"` 时，`std::vector<int> v(it, {})` 得到什么？流处于什么状态？
    2. 为什么 `istreambuf_iterator` 必须有平凡的复制构造函数和析构函数？

<details markdown="1">
<summary>展开查看答案与解析</summary>

1. `{12}`。读 `12` 成功；读 `abc` 时 `>>` 失败，设置 `failbit`，迭代器变为流末，循环结束。流此后处于失败状态，`34` 未被读取；要继续读需先 `clear()` 并跳过坏数据。（`v(it, {})` 中 `{}` 推导为 `istream_iterator<int>`，因为两个参数是同一个模板参数 `InputIterator`，第二个由第一个推导。）
2. 它在语义上就是一个 `streambuf*` 包装，平凡性保证它可以像指针一样廉价地复制、按值传递（通过寄存器）、存放在需要平凡类型的地方，且复制不会产生任何副作用——这对标准库内部大量按值传递迭代器的算法很重要。
</details>

## 小结

!!! summary
    - `istream_iterator`：经 `>>` 读取；构造即读；读失败变流末；`==` 只比流指针；`*` 返回内部成员的引用。
    - `ostream_iterator`：经 `<<` 写；分隔串在每个元素后（含最后一个）；只存指针。
    - `istreambuf_iterator`：逐字符、不跳空白、`reference` 为 `charT`；`*` 不消费、`++` 消费；后置 `++` 返回 proxy；`equal` 只看是否都在流末。
    - `ostreambuf_iterator`：逐字符 `sputc`；`failed()` 报告写失败，失败后写入被丢弃。
    - 输入流迭代器都可与 `default_sentinel` 比较；注意 `string s(istreambuf_iterator<char>(in), ...)` 的声明歧义。
