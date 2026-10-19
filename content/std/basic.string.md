---
title: 类模板 basic_string
summary: basic_string 的成员：结尾空字符的不变式、强异常保证、比 vector 更宽的失效规则与短字符串优化，以及构造、容量、元素访问、修改和查找各组成员的规定与陷阱。
status: done
covers: *
papers: P0980R1, P0966R1, P1072R10, P2166R1, P2438R2, P0457R2, P1679R3, P0254R2, P3471R4
related: strings, string.classes, string.view, char.traits, container.requirements, sequence.reqmts, container.reqmts, container.alloc.reqmts, basic.indet, structure.specifications, expr.const, class.temporary
tags: 标准库, string, SSO, 迭代器失效, 加固, constexpr
updated: 2026-10-19
---

!!! tldr
    - `basic_string` 是连续容器，并且 `data()[size()]` 总是一个真实存在的空字符；把它改成别的值是未定义行为。
    - 任何成员函数抛异常时，字符串保持原样（强异常保证）。
    - 除 `operator[]`、`at`、`data`、`front`、`back`、`begin`、`end`、`rbegin`、`rend` 外，调用任何非 const 成员都可能使指向字符的指针和迭代器失效，即使容量足够。这给短字符串优化留出了空间。
    - 从 `string_view` 构造是 `explicit` 的；`std::string s{3, 'x'}` 得到两个字符；`s = 65` 能编译，结果是 `"A"`。
    - 大多数成员都有一个接受任何可转换为 `string_view` 的类型的模板重载，语义由 [[string.view]] 决定。

`std::string` 是 `basic_string<char>` 的别名。`basic_string` 的成员函数有一百多个重载，但大部分是同一件事的不同入口：标准把几乎所有操作都定义为先构造一个 `basic_string_view`，再调用一个核心版本。非成员函数（`operator+`、比较、I/O、`erase`）、`stoi` 和 `to_string`、`hash`、`""s` 字面量见 [[string.classes]]。

## 结尾的空字符 [basic.string.general]

```cpp run ok
#include <string>
#include <cassert>

int main() {
  std::string s(3, 'x');
  assert(s[s.size()] == '\0');   // 读结尾的空字符：OK
  s[s.size()] = '\0';            // 写入 charT()：OK
  // s[s.size()] = 'y';          // UB
  assert(s.size() == 3);
}
```

¶1 `basic_string` 保存一个长度可变的 char-like 对象序列（[[g:char-like-type]]），首元素在位置 0。¶2 它是连续容器（[[container.reqmts]]），所以 `&s[0] + i == &s[i]`，`data()` 可以直接交给 C 接口。

¶3 是这个类最核心的不变式：

!!! std
    In all cases, `[data(), data() + size()]` is a valid range, `data() + size()` points at an object with value `charT()` (a "null terminator"), and `size() <= capacity()` is true.

注意 `[data(), data() + size()]` 是闭区间。结尾的**空终止符**（null terminator，[[g:null-terminator]]）是一个真实存在的对象，不是读取时临时产生的值。所以 `c_str()` 可以是常数时间、`noexcept` 的，`s[s.size()]` 也能返回一个引用。

¶3 的最后一句规定，把空终止符改成 `charT()` 以外的值是 {{ub}}：之后的 `c_str()` 会返回一个没有正确结尾的序列。写入 `charT()` 本身是允许的。

in all cases 包括空字符串和被移走内容的字符串。`std::string{}.c_str()` 指向一个空字符，而 `std::string_view{}.data()` 是空指针（[[string.view]]）。

类型成员 `size_type`、`difference_type`、`pointer` 等都来自 `allocator_traits<Allocator>`。使用花式指针（fancy pointer）的分配器时，`pointer` 不是 `charT*`，但 `data()` 仍然返回 `charT*`（[[string.accessors#1]] 用 `to_address(begin())` 定义它）。`npos` 是 `size_type(-1)`，既表示找不到，也表示直到末尾。

## 通用要求 [string.require]

¶1 任何操作如果会使 `size()` 超过 `max_size()`，就抛 `length_error`。本机 libc++ 的 `max_size()` 是 9223372036854775790，约为 2^63。

¶2 整个类提供强异常保证：

!!! std
    If any member function or operator of `basic_string` throws an exception, that function or operator has no other effect on the `basic_string` object.

这能做到，是因为 char-like 类型是平凡的，traits 操作又不会抛（[[char.traits]]）。除了分配内存，字符串操作里没有会失败的步骤，实现可以先分配新缓冲区，成功之后再替换旧的。`vector::insert` 则只有基本保证，因为元素的复制构造可能抛异常。

¶3 每个对象用 `Allocator` 分配和释放存储，`traits` 必须满足字符 traits 的要求。两条注补充说明：

- `basic_string` 是分配器感知容器（[[container.alloc.reqmts]]），但不使用分配器的 `construct` 和 `destroy`，字符不经过 uses-allocator 构造。
- `Allocator::value_type` 或 `traits::char_type` 与 `charT` 不同时，程序非良构。

### 失效规则比 vector 宽 [string.require]

```cpp run ub
#include <string>
#include <cstdio>

int main() {
  std::string s(40, 'x');
  const char* p = s.c_str();
  s += " grows past capacity and reallocates";
  std::printf("%c\n", *p);    // UB：p 已失效，ASan 报 heap-use-after-free
}
```

¶4 指向 `basic_string` 中字符的引用、指针和迭代器，可能因为下面两类使用而失效：

- ¶4.1 把这个字符串作为非 const 引用实参传给任何标准库函数。脚注举了 `swap`、`operator>>`、`getline` 的例子。
- ¶4.2 调用任何非 const 成员函数，但 `operator[]`、`at`、`data`、`front`、`back`、`begin`、`rbegin`、`end`、`rend` 除外。

这比 `vector` 宽得多。`vector::push_back` 只在重新分配时使迭代器失效（[[sequence.reqmts]]），`string::push_back` 则无论容量够不够都可能使它们失效，标准没有细分，程序不能依赖容量足够时的行为。`c_str()`、`size()` 等 const 成员不在这一规则内，不会使任何东西失效。

!!! note "为什么这样规定：COW 与 SSO"
    C++98 的规则更宽，是为了允许写时复制（copy-on-write，COW）：多个字符串共享一块带引用计数的缓冲区，连 `operator[]` 这样的非 const 访问都可能触发复制，从而使迭代器失效。C++11 把 `operator[]`、`begin` 等移出了失效名单，加上并发方面的要求，实际上排除了 COW。

    但标准没有把失效限定在重新分配时，这为**短字符串优化**（short string optimization，SSO，[[g:short-string-optimization]]）留出了空间：短字符串的字符存放在 `string` 对象内部，移动或交换字符串时，字符必须换地址。所以 [[string.cons#30]] 规定移动赋值可能使迭代器失效；`swap` 虽然一般容器保证不使迭代器失效（[[container.reqmts#66.6]]），¶4 的脚注却专门点名了 `basic_string::swap()`。

    标准允许 SSO，但不要求。libc++、libstdc++、MSVC STL 都实现了它。

## 短字符串优化：libc++ 的实测

本机（Apple arm64，Homebrew Clang 23 + libc++）的测量结果：

| 项目 | 结果 |
|---|---|
| `sizeof(std::string)`、`sizeof(std::u16string)`、`sizeof(std::u32string)` | 都是 24 |
| 空 `string`、`u16string`、`u32string` 的 `capacity()` | 22、10、4 |
| 22 个字符的 `string` | 字符在对象内部，从偏移 0 开始 |
| 23 个字符的 `string` | 堆分配，`capacity() == 24` |
| 逐个 `push_back` 时的容量变化 | 22 → 47 → 95 → 191 → 383 → 767 |
| 被移动构造后的源对象 | `size() == 0`，`capacity() == 22` |
| `string(100, 'x')` 后 `resize(5)` 再 `shrink_to_fit()` | `capacity() == 22`，回到对象内部 |

libc++ 的 `basic_string` 内部是一个 union。长模式存放数据指针、大小、容量三个字；短模式把同样的 24 字节当作字符数组，外加一个字节存放长度和区分两种模式的标志位。24 字节去掉一个长度字节是 23 个 `char`，再去掉结尾的空字符，就是短模式的容量 22。

标志位的位置有两种布局，由 `_LIBCPP_ABI_ALTERNATE_STRING_LAYOUT` 选择。默认布局（Linux x86-64 等）把标志放在第一个字节，短模式的字符从偏移 1 开始；替代布局（Apple arm64 等，即本机）把标志放在最后一个字节，字符从偏移 0 开始。两种布局都利用了容量中永远用不到的一位来存放标志。

其他实现不在本机，仅供参考：libstdc++ 和 MSVC STL 的 `std::string` 都是 32 字节，短模式容量 15。

!!! impl "SSO 对代码的影响"
    - 短字符串的 `data()` 指向 `string` 对象自身。短字符串被销毁或移走后留下的悬垂指针指向栈上或另一个对象内部，AddressSanitizer 往往检测不到（见 [[string.view]] 的悬垂例子）。
    - 交换两个短字符串要复制 24 字节，而不是交换三个指针。这仍然是常数时间，满足 [[string.swap#4]] 的要求。
    - 返回短字符串的函数完全没有堆分配。

## 构造与赋值 [string.cons]

### 几个容易出错的构造

```cpp run ok
#include <string>
#include <cassert>

int main() {
  std::string a(3, 'x');      // "xxx"：n 个 c
  std::string b{3, 'x'};      // "\3x"：initializer_list<char>，两个字符
  std::string c{65, 'x'};     // "Ax"
  assert(a == "xxx" && b.size() == 2 && c == "Ax");
}
```

¶19 `(n, c)` 构造 `n` 个 `c`。花括号初始化则优先选择 `initializer_list` 构造函数（¶23，[[over.match.list]]），`3` 和 `65` 都是能无窄化地转换为 `char` 的常量表达式，于是 `{65, 'x'}` 是两个字符的列表。`std::vector<int>{3, 1}` 是同一个问题。

<div class="compare" markdown="1">

```cpp run ok
#include <string>
#include <string_view>
int main() {
  std::string_view sv = "abc";
  std::string s1(sv);   // OK：直接初始化
  (void)s1;
}
```

```cpp error
#include <string>
#include <string_view>
void f(const std::string&);
void g(std::string_view sv) {
  std::string s2 = sv;  // error: explicit
  f(sv);                // error: 不会悄悄分配
}
```

</div>

¶11 从 `string_view` 类对象构造的模板有两个约束：`const T&` 能转换为 `basic_string_view<charT, traits>`，并且不能转换为 `const charT*`。它是 `explicit` 的。这是 [[P0254R2]] 的设计：`string` 到 `string_view` 很便宜，所以是隐式的；`string_view` 到 `string` 要分配内存，所以必须显式写出。第二个约束把 `const char*` 排除在外，字面量就继续走隐式的 `const charT*` 构造函数。

C++23 起 `basic_string(nullptr_t)` 被删除（[[P2166R1]]），`std::string s = nullptr;` 不能编译。本机上 `std::string s = 0;` 也被拒绝，诊断指向这个被删除的构造函数：`0` 是空指针常量，转换为 `nullptr_t` 和转换为 `const char*` 都是空指针转换。不论重载决议的结果是二义还是选中被删除的函数，程序都非良构。

!!! pitfall "s = 65 得到字符 A"
    `operator=(charT c)`（¶35）接受任何能隐式转换为 `char` 的值。`std::string s; s = 65;` 能编译，本机 Clang 23 开着 `-Wall -Wextra -pedantic` 也没有警告，结果是 `"A"`。常见的来源是想写 `s = std::to_string(n)`，却写成了 `s = n`。

### 其余构造函数

- ¶1 `basic_string(const Allocator&)` 构造空字符串，`noexcept`。
- ¶2–¶3 复制和移动构造。移动构造是 `noexcept` 的，源对象处于有效但未指定的状态（[[g:valid-but-unspecified-state]]）；libc++ 中它变为空串。
- ¶4–¶8 从另一个字符串的 `[pos, pos + rlen)` 构造，`n` 超过剩余长度时截断，`pos > size()` 时抛 `out_of_range`。C++23 加入了接受 `basic_string&&` 的版本（[[P2438R2]]），¶8 建议分配器相等时直接接管源对象的缓冲区，不再分配。
- ¶13–¶15 `(const charT* s, size_type n)` 的前置条件是 `[s, s+n)` 有效，中间可以有空字符。¶17 `(const charT* s)` 等价于 `basic_string(s, traits::length(s), a)`。
- ¶20–¶21 迭代器对构造函数要求实参能当作输入迭代器，所以 `string(5, 'x')` 不会误选它。¶22 C++23 加入 `from_range_t` 版本。
- ¶24–¶25 带分配器的复制和移动构造。分配器相等时，带分配器的移动构造不抛异常。

推导指引 ¶26–¶27 中，从 `basic_string_view` 推导的单参数版本是 `explicit` 的：`std::basic_string a(sv);` 推导为 `std::string`，`std::basic_string b = sv;` 不能编译。

### 赋值

- ¶28 复制赋值。自赋值没有效果。
- ¶30 移动赋值按序列容器的方式进行，但迭代器、指针和引用可能失效，原因是上文的 SSO。它在分配器满足 `propagate_on_container_move_assignment` 或 `is_always_equal` 时是 `noexcept` 的。
- ¶32–¶33 从 `string_view` 类对象赋值，约束与构造时相同。
- ¶34 `operator=(const charT*)`；`operator=(nullptr_t)` 被删除。
- ¶35 `operator=(charT c)` 等价于赋值一个长度为 1 的视图。

## 容量 [string.capacity]

### reserve 不再缩小容量

!!! std
    Following a call to `reserve`, `capacity()` is greater or equal to the argument of `reserve` if reallocation happens; and equal to the previous value of `capacity()` otherwise.

¶14 C++20 起，`reserve` 只在当前容量小于实参时重新分配，实参较小时什么也不做（[[P0966R1]]）。在那之前，`s.reserve()`（实参默认为 0）是一个不保证执行的缩容请求；无参版本在 C++20 被弃用，后来被移除。现在缩容只能用 `shrink_to_fit()`。¶15 实参大于 `max_size()` 时抛 `length_error`。本机 libc++ 中 `reserve(100)` 之后 `capacity()` 是 103。

¶16–¶18 `shrink_to_fit()` 是一个不保证执行的缩容请求，不会增加容量；如果重新分配，所有引用、指针和迭代器（包括尾后迭代器）都失效。libc++ 在内容放得下时会缩回对象内部的 SSO 缓冲区。

¶19 `clear()` 等价于 `erase(begin(), end())`，不释放内存，`capacity()` 不变。

¶1–¶6 `size()` 和 `length()` 是常数时间；`resize(n, c)` 截断或者追加 `c`，`resize(n)` 用 `charT()` 填充。

### resize_and_overwrite {{c++23}}

```cpp run ok
#include <string>
#include <cstdio>
#include <cassert>

int main() {
  std::string s;
  s.resize_and_overwrite(32, [](char* p, std::size_t n) {
    return std::snprintf(p, n + 1, "%d-%d", 12, 34);   // 可以写 n+1 个字符，包括结尾的空字符
  });
  assert(s == "12-34" && s.size() == 5);
}
```

先分配一块缓冲区、交给 C 接口填写、再确定实际长度，是很常见的写法。用 `resize(n)` 做这件事，会先把缓冲区无用地清零一遍。C++23 的 `resize_and_overwrite(n, op)`（[[P1072R10]]）省掉了这一步。¶7–¶10 规定了它的契约：

- `op` 收到指针 `p` 和长度 `m == n`。`[p, p+n]` 是有效的闭区间，所以 `op` 可以写 `p[n]`，`snprintf` 正需要这一点。前 `min(size(), n)` 个字符是原来的内容，其余位置的值可能不确定（[[basic.indet]]）。
- ¶8 `op` 的返回值必须是整数类类型。
- ¶9 `op` 不能抛异常，不能修改 `p` 和 `m`；返回值 `r` 满足 `0 <= r <= m`；`[p, p+r)` 中不能留下不确定的值。
- ¶10 结果是字符串的内容变为 `[p, p+r)`，`[p, p+n]` 中的所有指针和引用失效，所以 `op` 不能把 `p` 存起来以后再用。

违反任何一条前置条件都是 {{ub}}，没有加固检查。`op` 抛异常也是 UB，这是强异常保证的一个例外：`op` 写了一半时，实现没有办法回滚。

## 元素访问与迭代器 [string.access]

| 成员 | 前置条件 | 违反时 |
|---|---|---|
| `operator[](pos)` | 加固：`pos <= size()`（¶1） | 加固实现中是契约违反，否则 {{ub}} |
| `at(pos)` | 无 | `pos >= size()` 时抛 `out_of_range`（¶6） |
| `front()`、`back()` | 加固：`!empty()`（¶7、¶9） | 同 `operator[]` |

`operator[]` 允许 `pos == size()`，返回结尾空字符的引用；`at(size())` 却抛异常，两者的边界差一。C++26 把这些前置条件标为加固前置条件（[[P3471R4]]，见 [[structure.specifications]]）：加固实现必须检查它们，违反时按契约违反处理。libc++ 用宏 `_LIBCPP_HARDENING_MODE` 选择加固模式，本机默认不开启。

[string.iterators] 中 `end()` 指向结尾空字符的位置，但解引用 `end()` 仍然是越界；要读空字符，用 `s[s.size()]`。libc++ 的 `string::iterator` 是包装类型 `__wrap_iter<char*>`。

## 修改器 [string.modifiers]

### 接受 string_view 类对象的模板重载

`operator+=`、`append`、`assign`、`insert`、`replace`、`find` 一族和 `compare` 都有这样一个模板重载：

```cpp
template<class T> constexpr basic_string& append(const T& t);
// Constraints: is_convertible_v<const T&, basic_string_view<charT, traits>> 为 true，
//              且 is_convertible_v<const T&, const charT*> 为 false
```

为什么不直接写成接受 `basic_string_view` 的非模板函数？那样 `s.append("abc")` 会在 `append(const charT*)` 和 `append(basic_string_view)` 之间二义，两者都只需一次转换。写成模板并排除能转换为 `const charT*` 的类型后，字面量和 `char*` 只匹配 `const charT*` 重载，`std::string_view` 和其他能转换为视图的类型匹配模板。

### 追加、赋值、插入、替换

这几组函数的核心版本都接受 `(const charT* s, size_type n)`，前置条件是 `[s, s+n)` 有效；带位置参数的版本在 `pos > size()` 时抛 `out_of_range`，结果超长时抛 `length_error`。

- [[string.append#15]] 迭代器版本的 `append` 等价于先构造一个临时字符串再追加，所以 `s.append(s.begin(), s.end())` 是正确的。¶16 C++23 加入 `append_range`；¶18 `push_back(c)` 等价于 `append(1, c)`。
- 源和目标是同一个字符串时，例如 `s += s` 或 `s.append(s.data() + 1, 3)`，结果也必须正确。规范只说追加区间的一份副本，没有给出源不得与 `*this` 重叠的前置条件，实现要在重新分配之前先保存源内容。
- [[string.assign#14]] `assign(n, c)` 定义为 `clear(); resize(n, c);`。
- [string.insert] 的迭代器版本要求 `p` 是 `*this` 上的有效迭代器，返回指向第一个插入字符的迭代器，`n == 0` 时返回 `p`。
- [string.replace] 的迭代器版本要求 `[begin(), i1)` 和 `[i1, i2)` 都是有效范围。

### erase 与 pop_back [string.erase]

¶1–¶3 `erase(pos = 0, n = npos)` 删除 `[pos, pos + min(n, size() - pos))`，`pos > size()` 时抛 `out_of_range`。所以 `s.erase(3)` 删除从位置 3 开始的所有字符，而不是位置 3 上的一个字符；后者要写 `s.erase(s.begin() + 3)`（¶4–¶7）。¶12 `pop_back()` 的加固前置条件是 `!empty()`。

### copy 与 swap

[string.copy] `copy(s, n, pos)` 等价于 `basic_string_view(*this).copy(s, n, pos)`，不写结尾的空字符。

[string.swap] ¶1 `swap` 的前置条件是分配器的 `propagate_on_container_swap` 为真，或者两者的分配器相等，否则是 {{ub}}。¶3–¶4 它不抛异常，复杂度是常数。

## 字符串操作 [string.ops]

### c_str、data 与转换为视图 [string.accessors]

¶1 `c_str()`、`data() const` 和 `data()` 都返回 `to_address(begin())`，常数时间。所以 `c_str() == data()` 总是成立，区别只在于非 const 的 `data()`（C++17 起）返回可写的 `charT*`。

¶3 `operator basic_string_view<charT, traits>() const noexcept` 等价于 `basic_string_view(data(), size())`。这是 `string` 到 `string_view` 的隐式转换，[[string.view]] 中的悬垂问题都从这里开始。

### 查找与比较

[string.find] 的所有重载都归结为 `basic_string_view` 的同名函数，语义见 [[string.view]]：找不到返回 `npos`，从不抛 `out_of_range`。¶4 模板版本的 `noexcept` 与 `is_nothrow_convertible_v<const T&, basic_string_view<charT, traits>>` 一致。

[string.compare] 的所有版本都等价于 `basic_string_view(*this)` 的对应 `compare`，带 `pos1`、`n1` 的版本在 `pos1 > size()` 时抛 `out_of_range`。

[string.starts.with]、[string.ends.with]（C++20，[[P0457R2]]）和 [string.contains]（C++23，[[P1679R3]]）都等价于 `basic_string_view(data(), size())` 的同名成员，各有接受视图、字符、`const charT*` 的三个重载：

```cpp run ok
#include <string>
#include <cassert>

int main() {
  std::string s = "hello";
  assert(s.starts_with("he") && s.starts_with('h') && !s.ends_with("lo!"));
  assert(s.contains("ell") && s.contains('o') && !s.contains("xyz"));
  assert(!std::string{}.starts_with('a'));   // 空串返回 false，不违反 front() 的前置条件
}
```

### substr 与 subview [string.substr]

```cpp
constexpr basic_string substr(size_type pos = 0, size_type n = npos) const &;
constexpr basic_string substr(size_type pos = 0, size_type n = npos) &&;
constexpr basic_string_view<charT, traits> subview(size_type pos = 0, size_type n = npos) const;
```

C++23 把 `substr` 分成 `const &` 和 `&&` 两个重载（[[P2438R2]]）。¶2 对右值调用时等价于 `basic_string(std::move(*this), pos, n)`，可以接管源对象的缓冲区，所以 `make().substr(1)` 可能完全不分配。

¶3 `subview` 是较新的工作草案加入的，返回一个视图，不复制字符。两者在 `pos > size()` 时都抛 `out_of_range`。`auto t = s.subview(1);` 中 `t` 是 `string_view`，`s` 修改或销毁后 `t` 就悬垂；对右值字符串调用 `subview`，得到的视图立即悬垂。

## constexpr 与瞬态分配

C++20 起 `basic_string` 的所有成员都是 `constexpr`（[[P0980R1]]）。但常量求值中分配的内存必须在同一次求值中释放（瞬态分配，[[g:transient-allocation]]、[[expr.const]]）：

```cpp
constexpr std::size_t f() { std::string s = "a fairly long string that leaves SSO"; return s.size(); }
static_assert(f() == 36);                                           // OK：分配在 f 内部释放
constexpr std::string s1 = "short";                                 // 本机 libc++ 接受：SSO，没有分配
constexpr std::string s2 = "a fairly long string that leaves SSO";  // error: 不是常量表达式
```

`s1` 能编译完全取决于实现：libc++ 中短字符串不分配内存。换一个短模式容量不同的实现，或者把字符串加长到超过 22 个字符，同样的写法就会失败。可移植的代码不应依赖这一点，编译期的字符串常量用 `std::string_view` 或字符数组。

## 历史

!!! history
    - C++11 收紧了失效规则并加入并发要求，实际上排除了写时复制的实现。
    - C++17 起非 const 的 `data()` 返回 `charT*`；从 `string_view` 构造和赋值的成员随 [[P0254R2]] 加入。
    - C++20：所有成员成为 `constexpr`（[[P0980R1]]）；`reserve` 不再缩容（[[P0966R1]]）；加入 `starts_with`、`ends_with`（[[P0457R2]]）。
    - C++23：`resize_and_overwrite`（[[P1072R10]]）；删除 `nullptr` 构造（[[P2166R1]]）；右值 `substr` 和接受 `basic_string&&` 的子串构造（[[P2438R2]]）；`contains`（[[P1679R3]]）。
    - C++26：元素访问的前置条件改为加固前置条件（[[P3471R4]]）。

## 思考题

!!! question "思考题 1"
    `const char* p = s.c_str(); s.push_back('x'); std::puts(p);`，已知 `s.capacity() > s.size() + 1`。这段代码合法吗？

<details markdown="1">
<summary>答案</summary>

标准不保证合法。[string.require] ¶4.2 规定，除九个例外之外的非 const 成员都可能使指针失效，`push_back` 不在例外中，标准也没有像 `vector` 那样把失效限定在重新分配时。`p` 可能已经失效，使用它是 {{ub}}。

实践中三个主流实现在容量足够时都不会搬动缓冲区。即便如此，`push_back` 把原来空字符的位置改成了 `'x'`，并在后面写了新的空字符，所以 `puts(p)` 打印出的内容也包含这个 `x`。
</details>

!!! question "思考题 2"
    为什么 `std::string s = sv;`（`sv` 是 `std::string_view`）非良构，而 `std::string s = "abc";` 合法？

<details markdown="1">
<summary>答案</summary>

复制初始化只考虑非 `explicit` 的构造函数。从 `string_view` 类对象构造的模板是 `explicit` 的（[[string.cons#11]]），`string_view` 也没有到 `string` 的转换函数。`"abc"` 用的是 `basic_string(const charT*, const Allocator& = Allocator())`，它不是 `explicit` 的。设计意图是需要分配内存的转换必须显式写出（[[P0254R2]]）。
</details>

!!! question "思考题 3"
    `a.swap(b)` 之后，原来指向 `b` 中字符的迭代器指向哪里？换成 `std::vector<char>` 呢？

<details markdown="1">
<summary>答案</summary>

对 `vector`，[[container.reqmts#65]] 保证交换后迭代器指向另一个容器中的同一个元素，因为交换的只是缓冲区指针，元素没动；¶66.6 还保证 `swap` 不使引用、指针、迭代器失效。

对 `string`，[string.require] ¶4 的脚注点名 `swap()` 可能使它们失效。原因是 SSO：两个短字符串的字符都存放在各自的对象内部，交换只能复制字符，旧迭代器仍然指向原来那个对象内部的缓冲区，那里现在存的是另一个字符串的内容。
</details>
