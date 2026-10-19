---
title: 字符串视图
summary: basic_string_view 是不拥有字符的指针加长度；本页讲它怎样构造、哪些操作有前置条件、为什么 data() 不保证以空字符结尾，以及它最常见的错误：悬垂。
status: done
covers: *
papers: P0254R2, P0403R1, P1391R4, P1989R2, P2499R0, P2166R1, P2251R1, P0457R2, P1679R3, P3471R4, P0919R3, P1690R1
related: strings, char.traits, basic.string, string.classes, views.contiguous, class.temporary, range.range, over.match.oper, unord.hash, lex.string, structure.specifications
tags: 标准库, string_view, 悬垂, 加固, 视图
updated: 2026-10-19
---

!!! tldr
    - `string_view` 只保存一个指针和一个长度，不拥有字符，复制它很便宜；它最适合做函数形参。
    - 它不延长任何对象的生命周期。从临时 `std::string` 构造视图再保存下来，视图立即悬垂。
    - `data()` 不保证以空字符结尾，不要交给只接受 `const char*` 的 C 函数。
    - `sv[i]` 要求 `i < size()`，比 `std::string` 的 `i <= size()` 更严；C++26 起这是加固前置条件。
    - 从 range 构造是 `explicit` 的，字符数组仍按 C 字符串处理，`nullptr` 不能用来构造。

## 为什么需要 string_view [string.view.general]

```cpp run ok
#include <string>
#include <string_view>
#include <cstdio>

std::size_t count_a(std::string_view s) {      // 一个非模板形参，接受各种字符串
  std::size_t n = 0;
  for (char c : s) n += (c == 'a');
  return n;
}

int main() {
  std::string str = "banana";
  char buf[] = "papaya";
  std::printf("%zu %zu %zu\n",
              count_a("alpaca"),               // 字面量：不构造临时 string
              count_a(str),                    // string：经转换函数，不复制字符
              count_a(buf));                   // 字符数组：按 C 字符串处理
}
```

形参写成 `const std::string&` 时，传入字面量要先构造一个临时 `string`，可能分配内存；写成 `const char*` 又丢掉了长度。`std::string_view` 两种实参都能接受，而且不复制字符。[string.view.general] ¶2 的注说明了这个设计目的：库提供从 `const charT*` 和 `basic_string` 到 `basic_string_view` 的隐式转换，让用户代码只需接受 `basic_string_view<charT>` 这一种非模板形参类型。

¶1 `basic_string_view` 的对象引用一段常量、连续的 char-like 对象序列（[[g:char-like-type]]），首元素在位置 0。

!!! std
    The class template `basic_string_view` describes an object that can refer to a constant contiguous sequence of char-like objects with the first element of the sequence at position zero.

这句话里有三个要点。refer to 说明视图不拥有字符；constant 说明字符只读，所以 `iterator` 和 `const_iterator` 是同一个类型；contiguous 说明可以用 `data()` 拿到指向首字符的指针。和 `std::span<const char>`（[[views.contiguous]]）相比，`string_view` 多了 traits 参数和一整套查找、比较成员。

`std::string_view` 是 `basic_string_view<char>` 的别名。另外还有 `u8string_view`、`u16string_view`、`u32string_view`、`wstring_view`。

## 内部只有指针和长度 [string.view.template.general]

类定义末尾的两个说明用成员给出了它的全部状态：

```cpp
const charT* data_;   // exposition only
size_type size_;      // exposition only
```

libc++ 就是这样实现的，本机 `sizeof(std::string_view) == 16`。

¶1 `traits` 必须满足字符 traits 的要求（[[char.traits]]）。¶3 除非另有说明，成员函数的复杂度都是 O(1)。

¶2 视图里的指针、迭代器和引用何时失效，完全由被引用的存储决定：

!!! std
    For a `basic_string_view` `str`, any operation that invalidates a pointer in the range `[str.data(), str.data() + str.size())` invalidates pointers, iterators, and references to elements of `str`.

`string_view` 没有自己的失效规则。源 `string` 被销毁或者重新分配（[[basic.string]]），源缓冲区被释放，视图中的元素就都不能再访问了。失效的只是指向元素的指针、迭代器和引用，视图对象本身仍然是一个正常的对象：可以给它赋新值，`size()` 也照样能读。

¶4 `basic_string_view` 是平凡可复制类型（[[g:trivially-copyable-type]]）。这条保证是 C++23 由 [[P2251R1]] 补上的，各实现原本就是这样。在 x86-64 和 AArch64 的常见调用约定下，按值传递 `string_view` 用两个寄存器，比 `const std::string&` 少一次间接访问，所以惯用法是按值传递 `string_view`。

## 构造 [string.view.cons]

类定义中的构造函数如下：

```cpp
constexpr basic_string_view() noexcept;
constexpr basic_string_view(const basic_string_view&) noexcept = default;
constexpr basic_string_view(const charT* str);
basic_string_view(nullptr_t) = delete;
constexpr basic_string_view(const charT* str, size_type len);
template<class It, class End> constexpr basic_string_view(It begin, End end);
template<class R> constexpr explicit basic_string_view(R&& r);
```

### 默认构造与指针加长度

¶1 默认构造的视图满足 `size_ == 0` 且 `data_ == nullptr`。所以 `std::string_view{}.data()` 是空指针，`printf("%s", sv.data())` 在这里是 {{ub}}。`std::string{}.data()` 则总是指向一个空字符。

¶5 `(str, len)` 形式的前置条件是 `[str, str + len)` 是有效范围。它不要求结尾有空字符，中间有空字符也不管。`len == 0` 时 `str` 可以是空指针。

### 从 const charT*

¶2–¶4 前置条件是 `str` 指向一个以 `charT()` 结尾的序列；构造时用 `traits::length(str)` 求长度，复杂度与长度成正比。所以中间的空字符会截断视图：`std::string_view sv = "abc\0def";` 的 `size()` 是 3。

```cpp run ok
#include <string_view>
#include <array>
#include <cassert>

int main() {
  char buf[8] = "ab";
  std::array<char, 4> arr{'x', 'y', 'z', 'w'};
  assert(std::string_view{buf}.size() == 2);   // 数组退化为指针：strlen 语义
  assert(std::string_view{arr}.size() == 4);   // range 构造：整个 array
}
```

字符数组走的也是这个构造函数，而不是下面的 range 构造函数。这是有意的：字符数组几乎总是当作 C 字符串用，把结尾的空字符和没用到的空间都算进视图，会让所有人意外。

### nullptr 被删除

C++23 起 `basic_string_view(nullptr_t)` 被删除（[[P2166R1]]）。以前 `std::string_view sv = nullptr;` 能编译，然后在 `traits::length(nullptr)` 里崩溃。现在它在编译期被拒绝：

```cpp error
#include <string_view>
std::string_view sv = nullptr;   // error: 调用了被删除的函数
```

这只拦得住字面上的 `nullptr`。值为空的 `const char*` 变量仍然能通过编译，运行时违反前置条件。

### 从迭代器对 {{c++20}}

¶7 C++20 加入的 `(begin, end)` 构造函数（[[P1391R4]]）有四个约束：`It` 满足 `contiguous_iterator`；`End` 满足 `sized_sentinel_for<It>`；`It` 的值类型是 `charT`；`End` 不能转换为 `size_type`。

最后一个约束是为了不和 `(const charT*, size_type)` 抢重载：`string_view(p, 5)` 中的 `5` 不能被当成哨兵。¶9 构造的结果是 `data_ = to_address(begin)`、`size_ = end - begin`。

### 从 range：explicit {{c++23}}

¶12 C++23 加入的 range 构造函数（[[P1989R2]]）在 C++23 定稿前改成了 `explicit`（[[P2499R0]]）。它的约束如下，其中 `d` 是 `remove_cvref_t<R>` 类型的左值：

| 约束 | 作用 |
|---|---|
| ¶12.1 `remove_cvref_t<R>` 不是 `basic_string_view` | 不抢复制构造 |
| ¶12.2 `R` 是 `contiguous_range` 和 `sized_range` | 能取得 `data()` 和 `size()` |
| ¶12.3 `range_value_t<R>` 是 `charT` | 不转换元素类型 |
| ¶12.4 `R` 不能转换为 `const charT*` | 字符数组仍按 C 字符串处理 |
| ¶12.5 `d.operator ::std::basic_string_view<charT, traits>()` 不是有效表达式 | 自带转换函数的类型（如 `std::string`）用自己的转换函数 |

¶12.5 使 `std::string` 到 `string_view` 的转换总是走 `string` 的隐式转换函数，而不是这个构造函数。traits 不同时，例如 `basic_string<char, ci_traits>` 要转成 `std::string_view`，转换函数的目标类型对不上，¶12.5 不再排除它，于是可以用这个构造函数显式转换。

改成 `explicit` 的理由是：连续的字符 range 不一定是字符串。`std::vector<char>` 可能是以空字符结尾的缓冲区，也可能是二进制数据；`std::array<char, 16>` 可能只用了前几个字节。如果允许隐式转换，`f(std::string_view)` 就会悄悄接受这些对象，并把结尾的空字符也算进长度：

<div class="compare" markdown="1">

```cpp error
#include <string_view>
#include <vector>
void f(std::string_view);
void g(std::vector<char>& v) {
  f(v);   // error: 构造函数是 explicit
}
```

```cpp run ok
#include <string_view>
#include <vector>
#include <cassert>
int main() {
  std::vector<char> v{'a', 'b', '\0'};
  std::string_view s{v};   // 直接初始化
  assert(s.size() == 3);   // 含结尾的 '\0'
}
```

</div>

约束里没有要求 `R` 是 borrowed range，所以临时的 `vector` 也能用来构造视图，并且立即悬垂：

```cpp
#include <string_view>
#include <vector>
std::string_view x{std::vector<char>{'a', 'b'}};
// x 悬垂：临时 vector 在完整表达式结束时销毁，之后访问 x 的元素是 UB
```

### 推导指引 [string.view.deduct]

¶1 `basic_string_view(It, End)` 推导为 `basic_string_view<iter_value_t<It>>`。¶2 `basic_string_view(R&&)` 推导为 `basic_string_view<range_value_t<R>>`，只要求 `R` 是 `contiguous_range`。

## 悬垂

`string_view` 的问题几乎都可以归结为一点：它不延长任何对象的生命周期。引用绑定到临时对象时的生命周期延长（[[class.temporary]]）只对引用有效。`string_view` 是类类型，从临时 `string` 构造它，只是调用了 `string` 的转换函数，临时对象照常在完整表达式结束时销毁。

```cpp
std::string make();
void f(std::string_view);

f(make());                                   // OK：临时对象活到 f 返回之后
std::string_view a = make();                 // 悬垂
std::string_view b = std::string("x") + "y"; // 悬垂
std::string_view c = "abc"s;                 // 悬垂：""s 产生临时 string
std::string_view d = "abc";                  // OK：字面量具有静态存储期

std::string_view g() {
  std::string s = "local";
  return s;                                  // 悬垂：返回局部 string 的视图
}
```

本机 Clang 23 对 `a`、`b`、`c` 给出 `-Wdangling-gsl` 警告，对 `g` 给出 `-Wreturn-stack-address` 警告，两者都默认开启。Clang 内置了一份标准库类型清单，知道 `std::string_view` 是指针类类型、`std::string` 是拥有者类型。只要中间隔一层函数，编译器就看不出来了：

```cpp run ub
#include <string>
#include <string_view>
#include <iostream>

std::string_view trim(std::string_view s) {          // 返回实参的子视图
  while (!s.empty() && s.front() == ' ') s.remove_prefix(1);
  return s;
}
std::string read_line() { return "   a line long enough to avoid SSO, really"; }

int main() {
  std::cout << trim(read_line()) << '\n';            // OK：临时对象活到完整表达式结束
  std::string_view v = trim(read_line());            // 悬垂，没有警告
  std::cout << v << '\n';                            // UB：ASan 报 heap-use-after-free
}
```

Clang 的扩展属性 `[[clang::lifetimebound]]` 可以把这层关系告诉编译器。把形参声明为 `std::string_view s [[clang::lifetimebound]]` 之后，`v` 的那一行也会触发 `-Wdangling-gsl`。

!!! pitfall "短字符串让悬垂看起来没事"
    如果 `read_line()` 返回的字符串很短（libc++ 中不超过 22 个 `char`），字符就存放在 `string` 对象内部（短字符串优化，见 [[basic.string]]）。临时对象在栈上，销毁后那块内存往往原封不动，AddressSanitizer 也不一定能发现。测试通过不能说明没有悬垂。

`string_view` 什么时候可以安全地保存：

- 作为形参总是安全的，实参会活到调用结束。
- 作为返回值，只有返回实参的一部分（由调用者负责实参的生命周期）或者静态存储（字面量、静态对象）时才安全。
- 作为成员或者放进容器，必须保证被引用的对象活得比视图久。这是悬垂最常见的来源。
- 注意 `auto`：`auto x = s.subview(1);` 推导出 `string_view`，而 `auto x = s.substr(1);` 推导出 `string`，两者的生命周期完全不同。

## 访问元素 [string.view.access]

| 成员 | 前置条件 | 违反时 |
|---|---|---|
| `operator[](pos)` | 加固：`pos < size()`（¶1） | 加固实现中是契约违反，否则 {{ub}} |
| `at(pos)` | 无 | `pos >= size()` 时抛 `out_of_range`（¶5） |
| `front()`、`back()` | 加固：`!empty()`（¶6、¶9） | 同 `operator[]` |

¶1 的注特意指出，这个前置条件比 `basic_string::operator[]` 的更强。`string` 保证 `data()[size()]` 是一个空字符（[[basic.string]]），所以允许 `s[s.size()]`；视图后面不一定还有字符，所以不允许 `sv[sv.size()]`。

C++26 把这些前置条件标为加固前置条件（hardened preconditions，[[P3471R4]]，见 [[structure.specifications]]）：在加固实现中，违反它们一定会被检查并按契约违反处理。libc++ 用宏 `_LIBCPP_HARDENING_MODE` 选择加固模式，本机默认不开启。对 `sv == "abc"` 访问 `sv[3]`，默认模式下读出字面量结尾的空字符 0 并正常结束；用 fast 模式编译时，程序在越界处陷入，退出码 133（SIGTRAP）。

### data() 不保证以空字符结尾

```cpp run ok
#include <string_view>
#include <cstdio>
#include <cstdlib>

int main() {
  std::string_view whole = "1234567";
  std::string_view part = whole.substr(0, 3);    // "123"
  std::printf("%d\n", std::atoi(part.data()));   // 打印 1234567，不是 123
  std::printf("%.*s\n", static_cast<int>(part.size()), part.data());  // 正确：显式给出长度
}
```

这段代码没有 UB，因为 `whole` 来自字面量，后面确实有空字符，但结果错了。如果 `part` 引用的缓冲区后面没有空字符，`atoi` 就会越界读，成为 {{ub}}。¶13 的注总结了这一点：

!!! std
    Unlike `basic_string::data()` and *string-literal*s, `data()` can return a pointer to a buffer that is not null-terminated. Therefore it is typically a mistake to pass `data()` to a function that takes just a `const charT*` and expects a null-terminated string.

需要以空字符结尾的字符串时，要么用带长度的接口（`printf("%.*s")`、`fwrite`、`std::from_chars`），要么先构造一个 `std::string`。

### 迭代器与容量

[string.view.iterators] ¶1 `const_iterator` 是实现定义的类型，满足常量随机访问迭代器的要求，并建模 `contiguous_iterator`。libc++ 中它就是 `const char*`。¶3 非空时 `begin()` 指向 `data_`；空视图的 `begin()` 是未指定的值，只保证 `[begin(), end())` 是有效范围。

[string.view.capacity] 中，`size()` 和 `length()` 返回 `size_`，`empty()` 返回 `size_ == 0`。

## 修改视图 [string.view.modifiers]

这些成员改的是视图本身，不是字符：

- ¶1–¶2 `remove_prefix(n)`：加固前置条件 `n <= size()`，效果是 `data_ += n; size_ -= n;`；
- ¶3–¶4 `remove_suffix(n)`：加固前置条件 `n <= size()`，效果是 `size_ -= n;`；
- ¶5 `swap(s)`：交换两个视图。

## 子串、比较与前缀 [string.view.ops]

¶1–¶6 `copy(s, n, pos)` 把 `min(n, size() - pos)` 个字符复制到 `s`，返回复制的个数。它不写结尾的空字符。`pos > size()` 时抛 `out_of_range`。

¶7–¶10 `substr(pos, n)` 和 `subview(pos, n)` 返回 `basic_string_view(data() + pos, rlen)`，其中 `rlen = min(n, size() - pos)`：

- `pos == size()` 是合法的，结果是空视图；`pos > size()` 抛 `out_of_range`；
- `n` 超过剩余长度时自动截断；
- 结果与原视图引用同一块存储，不复制字符。

`subview` 是较新的工作草案加入的，对视图来说与 `substr` 完全相同。它是为 `basic_string` 准备的：`string::substr` 返回复制出来的 `string`，`string::subview` 返回不复制的视图。视图也有同名成员，泛型代码就可以对两者用同一个名字。

¶11–¶14 `compare(str)` 先用 `traits::compare(data(), str.data(), rlen)` 比较前 `rlen = min(size(), str.size())` 个字符，结果非零就返回它；为零时由长度决定，短的较小（Table 88）。¶15–¶19 其余的 `compare` 重载都等价于先调用 `substr`，所以带位置参数的版本可能抛 `out_of_range`。

¶20–¶28 `starts_with`、`ends_with`（C++20，[[P0457R2]]）和 `contains`（C++23，[[P1679R3]]）：

- `starts_with(x)` 等价于 `basic_string_view(data(), min(size(), x.size())) == x`；
- `starts_with(charT c)` 等价于 `!empty() && traits::eq(front(), c)`，空视图返回 `false`，不会违反 `front()` 的前置条件；
- `contains(x)` 等价于 `find(x) != npos`。

接受 `basic_string_view` 和 `charT` 的版本是 `noexcept` 的；接受 `const charT*` 的版本不是，因为它要先用指针构造视图，有前置条件。

## 查找 [string.view.find]

¶1 查找函数的最坏复杂度是 O(`size() * str.size()`)，标准建议实现做得更好。¶2 所有 `const charT*`、`(const charT*, n)`、`charT` 重载都归结为 `basic_string_view` 版本。六个函数的定义形式相同：找满足条件的最低或最高位置 `xpos`，找不到就返回 `npos`。

| 函数 | 方向 | `xpos` 的条件 |
|---|---|---|
| `find`（¶3–¶5） | 最低，`xpos >= pos` | 从 `xpos` 开始与 `str` 匹配 |
| `rfind`（¶6–¶8） | 最高，`xpos <= pos` | 同上 |
| `find_first_of`（¶9–¶11） | 最低 | `data_[xpos]` 等于 `str` 中某个字符 |
| `find_last_of`（¶12–¶14） | 最高 | 同上 |
| `find_first_not_of`（¶15–¶17） | 最低 | `data_[xpos]` 不等于 `str` 中任何字符 |
| `find_last_not_of`（¶18–¶20） | 最高 | 同上 |

几个边界情况：

- 查找函数从不抛异常。`pos` 越界只是找不到。
- `find("", pos)` 在 `pos <= size()` 时返回 `pos`，因为空串在任何位置都匹配。
- `rfind(x, pos)` 的 `pos` 是匹配起点的上界，所以能找到跨过 `pos` 的匹配。

## 比较运算符 [string.view.comparison]

```cpp run ok
#include <string>
#include <string_view>
#include <cassert>
using namespace std::literals;

int main() {
  std::string s = "abc";
  assert("abc"sv == "abc");     // const char* 隐式转换为 string_view
  assert("abc" == "abc"sv);     // 重写候选：交换操作数
  assert("abc"sv == s);         // string 的转换函数
  assert(("abc"sv <=> "abd"sv) < 0);
}
```

标准只声明了两个运算符模板：

```cpp
template<class charT, class traits>
  constexpr bool operator==(basic_string_view<charT, traits> lhs,
                            type_identity_t<basic_string_view<charT, traits>> rhs) noexcept;
template<class charT, class traits>
  constexpr /* see below */ operator<=>(basic_string_view<charT, traits> lhs,
                                        type_identity_t<basic_string_view<charT, traits>> rhs) noexcept;
```

¶1 `==` 返回 `lhs.compare(rhs) == 0`。¶2–¶4 `<=>` 的结果类型 `R` 是 `traits::comparison_category`，没有这个成员时是 `weak_ordering`；`R` 必须是比较类别类型；结果是 `static_cast<R>(lhs.compare(rhs) <=> 0)`。

第二个形参包了一层 `type_identity_t`，原因在 ¶5 的注里。模板实参推导不考虑隐式转换（[[temp.deduct.call]]），如果两个形参都是 `basic_string_view<charT, traits>`，`sv == "abc"` 就会推导失败，因为从 `const char*` 推不出 `basic_string_view<charT, traits>`。`type_identity_t<...>` 使第二个形参成为不推导的语境（[[g:non-deduced-context]]），`charT` 和 `traits` 只从 `lhs` 推导，`rhs` 就能经隐式转换匹配。

`"abc" == sv` 则由 C++20 的重写候选处理：编译器会把它当作 `sv == "abc"` 再试一次（[[over.match.oper]]）。所以一个模板就能覆盖两个方向，`!=`、`<` 等也都由重写得到。

## 输出、哈希与 sv 字面量

[string.view.io] ¶1 `operator<<` 是格式化输出函数（[[ostream.formatted.reqmts]]）：按 `os.width()` 填充，然后调用 `os.width(0)`。它按长度输出，中间的空字符也会写出去。

[string.view.hash] ¶1 五个标准别名都有启用的 `hash` 特化（[[unord.hash]]）。注 1 指出，视图的哈希值等于对应字符串的哈希值，这由 [[basic.string.hash]] 保证。所以 `unordered_map<std::string, V>` 可以用 `string_view` 查找而不构造临时 `string`（C++20 的异构查找，[[P0919R3]]、[[P1690R1]]），透明的哈希器直接用 `hash<string_view>` 即可：

```cpp run ok
#include <string>
#include <string_view>
#include <unordered_map>
#include <functional>
#include <cassert>
using namespace std::literals;

struct string_hash {
  using is_transparent = void;
  std::size_t operator()(std::string_view s) const noexcept {
    return std::hash<std::string_view>{}(s);
  }
};

int main() {
  std::unordered_map<std::string, int, string_hash, std::equal_to<>> m{{"key", 1}};
  assert(m.find("key"sv)->second == 1);   // 不构造临时 std::string
}
```

只有使用默认 traits 的视图有 `hash` 特化，`basic_string_view<char, ci_traits>` 没有。

[string.view.literals] ¶1–¶5 `operator""sv(str, len)` 返回 `basic_string_view{str, len}`，在 `std::literals::string_view_literals` 中（[[P0403R1]]）。`len` 来自字面量本身，所以中间的空字符会保留：`"abc\0def"sv` 的 `size()` 是 7。字符串字面量具有静态存储期（[[lex.string]]），所以 `"..."sv` 不会悬垂，是返回 `string_view` 最安全的写法。

<details class="fine" markdown="1"><summary>其余条文</summary>

[string.view.synop] 的头注释是 mostly freestanding：独立实现也提供 `string_view`，但会抛异常的 `at`、`copy`、`substr`、`subview` 和带位置参数的 `compare` 在独立实现中被删除，`operator<<` 只在宿主实现中提供。

概要还把 `ranges::enable_view` 和 `ranges::enable_borrowed_range` 都特化为 `true`。后者意味着对右值 `string_view` 调用 ranges 算法会得到真正的迭代器，而不是 `ranges::dangling`（[[g:borrowed-range]]、[[range.range]]）：视图销毁了，字符还在。

[string.view.synop] ¶1 包含 `<string_view>` 后，[utility.swap] 中的 `swap` 和 [iterator.range] 中的 `begin`、`size`、`data` 等函数模板都可以使用。

[string.view.cons] ¶8 要求迭代器对构造函数的概念不仅在语法上满足，而且被建模；¶10 它抛出 `end - begin` 抛出的异常。¶13–¶14 range 构造函数用 `ranges::data(r)` 和 `ranges::size(r)` 初始化，并传播它们的异常。

[string.view.capacity] ¶2 `max_size()` 返回视图能引用的最大字符数。

</details>

## 历史

!!! history
    - C++17 引入 `string_view`（[[P0254R2]] 同时给 `std::string` 加上到 `string_view` 的隐式转换），以及 `sv` 字面量（[[P0403R1]]）。
    - C++20 加入迭代器对构造函数（[[P1391R4]]）、`starts_with`/`ends_with`（[[P0457R2]]），比较运算符改为 `==` 和 `<=>`。C++17 时标准只是要求实现提供足够多的额外重载来支持与可转换类型的比较。
    - C++23 加入 `contains`（[[P1679R3]]）、删除 `nullptr` 构造（[[P2166R1]]）、加入 `explicit` 的 range 构造函数（[[P1989R2]]、[[P2499R0]]），并保证平凡可复制（[[P2251R1]]）。
    - C++26 把元素访问和 `remove_prefix`/`remove_suffix` 的前置条件改为加固前置条件（[[P3471R4]]）。

## 思考题

!!! question "思考题 1"
    `std::string_view sv = std::string("hi"); std::cout << sv.size();` 有未定义行为吗？

<details markdown="1">
<summary>答案</summary>

没有。`size_` 是构造时从临时 `string` 复制来的整数，读取它不会访问已销毁的存储。[string.view.template.general] ¶2 只让指向元素的指针、迭代器和引用失效。

但此时 `sv.data()` 是无效的指针值（[[g:invalid-pointer-value]]），`sv[0]`、`sv.front()`、输出 `sv` 都要访问元素，都是 {{ub}}。能编译、`size()` 也正常，正是悬垂难以发现的原因。
</details>

!!! question "思考题 2"
    `void f(std::string_view); std::vector<char> v;` 之后，`f(v)` 能编译吗？`f(std::string_view(v))` 呢？

<details markdown="1">
<summary>答案</summary>

`f(v)` 非良构。形参用复制初始化，需要隐式转换，而 range 构造函数是 `explicit` 的，`vector` 也没有到 `string_view` 的转换函数。

`f(std::string_view(v))` 合法。函数式转换是直接初始化，可以调用 `explicit` 构造函数；`vector<char>` 满足 ¶12 的所有约束：连续、有大小、值类型是 `char`、不能转换为 `const char*`、没有 `operator string_view`。
</details>

!!! question "思考题 3"
    为什么 `string_view::operator[]` 要求 `pos < size()`，而 `string::operator[]` 只要求 `pos <= size()`？

<details markdown="1">
<summary>答案</summary>

`basic_string` 保证 `data() + size()` 指向一个值为 `charT()` 的对象（[[basic.string]]），所以 `s[s.size()]` 有东西可读。视图没有这个保证。它可能引用 `"hello"` 的前三个字符，这时 `sv[3]` 是 `'l'` 而不是空字符；也可能引用缓冲区的最后几个字符，这时 `sv[sv.size()]` 越界。[string.view.access] ¶1 的注专门指出了这个差别。
</details>
