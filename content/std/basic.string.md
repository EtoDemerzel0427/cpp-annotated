---
title: 类模板 basic_string
summary: basic_string 逐条精读——"连续容器 + 终止符"不变式与修改终止符的 UB、强异常保证、比 vector 更宽的迭代器失效规则（以及它为什么要这么宽：SSO 未被强制却被允许）、构造函数陷阱（{n, c}、nullptr、0、=65）、reserve 不再缩容、resize_and_overwrite 的契约、加固的 operator[]、以 string_view 为中心的成员函数族、substr && 与 subview，以及 libc++ 的 SSO 布局实测
status: done
covers: *
papers: P0980R1, P0966R1, P1072R10, P2166R1, P2438R2, P0457R2, P1679R3, P0254R2, P3471R4
related: strings, string.classes, string.view, char.traits, container.requirements, sequence.reqmts, container.reqmts, container.alloc.reqmts, basic.indet, structure.specifications, expr.const, class.temporary
tags: 标准库, string, SSO, 迭代器失效, 加固, constexpr
updated: 2026-10-18
---

`std::basic_string` 是标准库里最常用的类模板，也是规范条文最长的之一——成员函数超过一百个重载。但这些重载绝大部分是同一件事的不同入口：标准把几乎所有操作都定义为"先构造一个 `basic_string_view`，再调用核心版本"。读懂这一节，抓住三件事就够了：

1. **不变式**：连续存储、`size() <= capacity()`、`data()[size()]` 永远是 `charT()`（[basic.string.general] ¶3）；
2. **通用要求**：超长抛 `length_error`、抛异常则无副作用、宽松的失效规则（[string.require]）；
3. **以 `string_view` 为中心的重载族**：每个修改/查找函数都有一个接受"可转换为 `string_view` 的任何 `T`"的模板版本。

非成员函数（`operator+`、比较、I/O、`erase`）、`to_string`/`stoi`、`hash`、`""s` 在 [[string.classes]]；`basic_string_view` 本身在 [[string.view]]；字符比较规则在 [[char.traits]]。

## 定义与不变式（[basic.string.general]）

¶1：`basic_string` 存储一个长度可变的 char-like 对象序列（[[g:char-like-type]]），首元素位于位置 0。

¶2：每个特化都是**连续容器**（[[container.reqmts]]）。所以 `&s[0] + i == &s[i]`，`data()` 可以交给 C API。

¶3 是这个类最核心的不变式：

!!! std
    In all cases, `[data(), data() + size()]` is a valid range, `data() + size()` points at an object with value `charT()` (a "null terminator"), and `size() <= capacity()` is true. The program has undefined behavior if the null terminator is modified to any value other than `charT()`.

    在任何情况下，`[data(), data()+size()]`（注意是**闭区间**）都是有效范围；`data()+size()` 指向一个值为 `charT()` 的对象——**空终止符**（[[g:null-terminator]]）；`size() <= capacity()`。把空终止符改成 `charT()` 以外的值是 {{ub}}。

几层意思：

- 终止符是一个**真实存在的对象**，不是"读的时候临时变出来的值"。这让 `c_str()` 可以是 O(1) 且 `noexcept`，也让 `s[s.size()]` 返回一个可以绑定的引用。
- 你**可以**通过 `s[s.size()]` 或 `data()[size()]` 往终止符里写——但只能写 `charT()`。写别的值是 UB，因为下一次 `c_str()` 会返回一个不终止的串。
- "In all cases" 包括空字符串和被移动后的字符串：`std::string{}.c_str()` 指向一个 `'\0'`，而 `std::string_view{}.data()` 是空指针（[[string.view]]）。

```cpp run ok
#include <string>
#include <cassert>

int main() {
  std::string s(3, 'x');
  assert(s[s.size()] == '\0');   // 读终止符：OK
  s[s.size()] = '\0';            // 写入 charT()：OK
  // s[s.size()] = 'y';          // UB：[basic.string.general] ¶3
  assert(s.size() == 3);
}
```

类定义之后：¶4 规定推导指引中的 `size_type` 指被推导出的类型的 `size_type`；¶5 规定 `iterator`/`const_iterator` 满足 constexpr 迭代器要求。

### 类型成员

`size_type`、`difference_type`、`pointer`、`const_pointer` 都来自 `allocator_traits<Allocator>`，所以使用花式指针（fancy pointer）的分配器时 `pointer` 不是 `charT*`——但 `data()` 仍然返回 `charT*`（[string.accessors] ¶1 用 `to_address(begin())` 定义）。`npos` 是 `size_type(-1)`，既作"找不到"的返回值，也作"直到末尾"的长度实参。

## 通用要求（[string.require]）

### 长度上限（¶1）

任何操作如果会使 `size()` 超过 `max_size()`，就抛 `length_error`。本机 libc++ 的 `max_size()` 为 9223372036854775790（约 2^63）。

### 强异常保证（¶2）

!!! std
    If any member function or operator of `basic_string` throws an exception, that function or operator has no other effect on the `basic_string` object.

这是**整类**的强异常保证：任何成员函数或运算符抛异常时，对字符串对象没有其他影响。它能成立，靠的是 char-like type 的平凡可复制性（[[strings]]）以及 traits 操作不抛（[[char.traits]]）——除分配外，字符串操作内部没有可能失败的步骤，实现可以"先分配新缓冲区，成功后再提交"。对比 `vector::insert`，那里元素的拷贝构造可能抛，标准只给基本保证。

### 分配器与 traits（¶3）

每个对象用 `Allocator` 分配和释放存储；`traits` 必须满足字符 traits 要求。两条注：

- `basic_string` 是分配器感知容器（[[container.alloc.reqmts]]），但**不使用**分配器的 `construct`/`destroy`。这对 `scoped_allocator_adaptor`、`polymorphic_allocator` 的用户有意义：字符不经过 uses-allocator 构造。
- `Allocator::value_type` 与 `charT` 不同、`traits::char_type` 与 `charT` 不同，都非良构。

### 失效规则（¶4）：比 vector 宽得多

!!! std
    References, pointers, and iterators referring to the elements of a `basic_string` sequence may be invalidated by the following uses of that `basic_string` object: (4.1) Passing as an argument to any standard library function taking a reference to non-const `basic_string` as an argument. (4.2) Calling non-const member functions, except `operator[]`, `at`, `data`, `front`, `back`, `begin`, `rbegin`, `end`, and `rend`.

也就是说：

- ¶4.1：把字符串以非 const 引用传给**任何**标准库函数（脚注举例：`swap`、`operator>>`、`getline`）都可能使其失效；
- ¶4.2：调用除那九个之外的**任何非 const 成员函数**都可能使其失效。

这比 `vector` 的规则宽得多。`vector::push_back` 只在重新分配时失效（[[sequence.reqmts]]），而 `string::push_back` 被列为"可能失效"，**无论容量够不够**。标准没有细分，你也不应该依赖"容量够就没事"。`c_str()`、`size()`、`capacity()` 等 const 成员不在名单里——它们不会使任何东西失效。

```cpp run ub
#include <string>
#include <cstdio>

int main() {
  std::string s(40, 'x');
  const char* p = s.c_str();
  s += " grows past capacity and reallocates";
  std::printf("%c\n", *p);    // UB：p 已失效；AddressSanitizer 报 heap-use-after-free
}
```

!!! note "为什么要这么宽？——SSO 与 C++11 之前的 COW"
    C++98/03 的规则更宽，是为了允许**写时复制**（COW）：引用计数共享缓冲区的实现里，连 `operator[]` 这样的非 const 访问都可能触发"分离"而使迭代器失效。C++11 收紧了规则（`operator[]`、`begin` 等不再使失效），配合并发要求，实际上把 COW 排除在外。

    但标准**没有**要求失效仅在重新分配时发生，这为**短字符串优化**（SSO，[[g:short-string-optimization]]）留出了空间：字符存放在 `string` 对象内部的缓冲区里时，"移动"字符串就意味着字符换了地址。[string.cons] ¶30 因此特别规定移动赋值"except that iterators, pointers and references may be invalidated"——而 `vector` 的移动只是转移缓冲区指针，元素本身不动。`swap` 同理：[[container.reqmts]] ¶65 对容器 `swap` 的一般规定是"交换前指向一个容器中某元素的迭代器，交换后指向另一个容器中的同一元素"，但 [string.require] ¶4.1 的脚注专门点名 `swap()` 可能使 `basic_string` 的迭代器失效；¶66.6 的"swap 不使失效"也只适用于容器章中定义的容器，`basic_string` 不在其列。

    SSO 不是标准**要求**的，是标准**允许**的。三大实现（libc++、libstdc++、MSVC STL）都用了它。

## libc++ 的 SSO 布局（实现视角）

本机（Apple arm64，Homebrew Clang 23 + libc++）实测：

| 量 | 值 |
|---|---|
| `sizeof(std::string)` | 24（三个指针宽） |
| `sizeof(std::u16string)`、`sizeof(std::u32string)` | 24 |
| 空 `string` 的 `capacity()` | 22 |
| 空 `u16string` / `u32string` 的 `capacity()` | 10 / 4 |
| 22 个字符 | 仍在对象内部 |
| 23 个字符 | 堆分配，`capacity() == 24` |
| 逐个 `push_back` 的容量序列 | 22 → 47 → 95 → 191 → 383 |
| 移动构造后源对象 | `size() == 0`，`capacity() == 22`（回到短模式） |
| `string(100, 'x')` 再 `resize(5)` + `shrink_to_fit()` | `capacity() == 22`（缩回对象内部） |

libc++ 的 `basic_string` 内部是一个 `union`，"长模式"存 `{指针, 大小, 容量}` 三个字，"短模式"把同样的 24 字节当作 `charT` 数组加一个字节的长度。区分两种模式的标志位有两种摆法，由 `_LIBCPP_ABI_ALTERNATE_STRING_LAYOUT` 选择：

| | 默认布局（Linux x86-64 等） | 替代布局（Apple arm64 等，本机） |
|---|---|---|
| 长模式 | `{is_long:1 + cap:63, size, data}` | `{data, size, cap:63 + is_long:1}` |
| 短模式 | 首字节 `{is_long:1, size:7}`，字符从偏移 1 开始 | 字符从偏移 0 开始，**末字节** `{size:7, is_long:1}` |
| 短模式容量 | 23 − 1 = 22 | 23 − 1 = 22 |

两种布局都利用了"容量的某一位永远用不到"：默认布局把容量存为偶数（分配大小对齐），最低位用作标志；替代布局让标志占据第三个字的最高位，所以 `max_size()` 约为 2^63。"22"这个数字来自 `sizeof(__long) - 1 = 23` 个 `char` 的空间，再减去终止符。

其他实现不在本机，仅供参考：libstdc++ 的 `std::string` 是 32 字节（指针 + 大小 + 16 字节的联合，短模式容量 15），MSVC STL 同样是 32 字节、短模式容量 15。

!!! impl "SSO 对代码的可见影响"
    - 短字符串的 `data()` 指向 `string` 对象自身。被销毁/移动的短字符串留下的悬垂指针指向**栈**或另一个对象内部，AddressSanitizer 往往检测不到（[[string.view]] 的悬垂示例）。
    - 本机实测：`c_str()` 指向 `&s` 的短字符串，在增长到堆上之后，原指针所指的字节变成了长模式的数据指针——没有崩溃，只有垃圾。
    - `std::swap` 两个短字符串要复制 24 字节，而不是交换三个指针——仍是 O(1)，[string.swap] ¶4 只要求常数时间。
    - 返回短字符串的函数完全没有堆分配。

## 构造与赋值（[string.cons]）

### 基本构造（¶1–8）

- ¶1：`basic_string(const Allocator&)` 后置条件 `size() == 0`；`noexcept`。
- ¶2–3：拷贝和移动构造；移动构造是 `noexcept` 的，源对象处于"有效但未指明的状态"（[[g:valid-but-unspecified-state]]）。libc++ 实测为空。
- ¶4–8：从 `str` 的 `[pos, pos + rlen)` 构造（`rlen` 的计算在 ¶4.2 中，`n` 超过剩余长度时截断）；`pos > s.size()` 抛 `out_of_range`。**C++23 新增了 `basic_string&&` 版本**（[[P2438R2]] 的一部分），¶8 的推荐做法：分配器相等时应避免分配，即直接"偷"源对象的缓冲区再截取。

### 从 `string_view` 类对象（¶9–12）

```cpp
template<class T> basic_string(const T& t, size_type pos, size_type n, const Allocator& a = Allocator());
template<class T> explicit basic_string(const T& t, const Allocator& a = Allocator());
```

约束都是"`const T&` 可转换为 `basic_string_view<charT, traits>`"，第二个还要求"**不能**转换为 `const charT*`"（¶11.2）。后者是 **`explicit`** 的：

```cpp
std::string_view sv = "abc";
std::string s1(sv);        // OK
std::string s2 = sv;       // error：explicit
void f(const std::string&);
f(sv);                     // error：不会悄悄分配
```

这是 [[P0254R2]] 的刻意设计：`string → string_view` 便宜，所以隐式；`string_view → string` 要分配内存，所以显式。¶11.2 排除了 `const char*`，让字面量继续走下面那个**隐式**的 `const charT*` 构造函数。

### 从字符指针（¶13–17）

- `basic_string(const charT* s, size_type n, ...)`：前置条件 `[s, s+n)` 有效，可包含内嵌 `'\0'`；
- `basic_string(const charT* s, ...)`：等价于 `basic_string(s, traits::length(s), a)`；¶16 的约束"`Allocator` 是分配器"只为影响 CTAD。

`basic_string(nullptr_t) = delete;`（C++23，[[P2166R1]]）把 `std::string s = nullptr;` 变成编译错误。本机上连 `std::string s = 0;` 也被拒绝，诊断指向这个被删除的构造函数：`0` 是空指针常量，转换为 `nullptr_t` 与转换为 `const char*` 同为空指针转换。无论重载决议最终判为二义还是选中被删除函数，程序都非良构。

### `(n, c)` 与 `{n, c}`：初始化列表陷阱（¶19、¶23）

```cpp run ok
#include <string>
#include <cassert>

int main() {
  std::string a(3, 'x');      // "xxx"：¶19，n 个 c
  std::string b{3, 'x'};      // "\3x"：initializer_list<char>，两个字符
  std::string c{65, 'x'};     // "Ax"
  assert(a == "xxx" && b.size() == 2 && c == "Ax");
}
```

列表初始化优先选择 `initializer_list` 构造函数（[[over.match.list]]），`3` 和 `65` 都是能无窄化地转换为 `char` 的常量表达式，于是 `{65, 'x'}` 是两个字符的列表。这与 `std::vector<int>{3, 1}` 是同一个坑。

### 迭代器、range、初始化列表（¶20–23）

- ¶20–21：`InputIterator` 版本按 [[sequence.reqmts]] 的规则构造；约束"qualifies as an input iterator"保证 `string(5, 'x')` 不会误选它。
- ¶22：`from_range_t` 版本（C++23）。
- ¶23：`initializer_list<charT>`。

### 带分配器的拷贝/移动（¶24–25）与推导指引（¶26–27）

¶25：`basic_string(basic_string&&, const Allocator&)` 在 `alloc == str.get_allocator()` 时不抛。

推导指引：`basic_string(InputIt, InputIt)`、`basic_string(from_range, R&&)`，以及两个从 `basic_string_view` 推导的指引——其中单参数那个是 `explicit` 的：

```cpp
std::string_view sv = "x";
std::basic_string a(sv);    // OK：推导为 std::string
std::basic_string b = sv;   // error：explicit 推导指引不参与拷贝初始化
```

### 赋值（¶28–36）

- ¶28：拷贝赋值；自赋值无效果。
- ¶30：移动赋值"按序列容器的方式"进行，**但迭代器、指针和引用可能失效**（见上文 SSO）。`noexcept` 条件是 POCMA 或 `is_always_equal`。
- ¶32–33：从 `string_view` 类对象赋值，同样排除 `const charT*`。
- ¶34：`operator=(const charT*)`；`operator=(nullptr_t) = delete`。
- ¶35：`operator=(charT c)` 等价于赋值一个长度为 1 的视图。

!!! pitfall "`s = 65;` 静默得到 “A”"
    `operator=(charT)` 接受任何能隐式转换为 `char` 的值。`std::string s; s = 65;` 编译通过，`-Wall -Wextra -pedantic` 下也没有任何警告（本机 Clang 23），结果是 `"A"`。常见来源是想写 `s = std::to_string(n)` 却写成了 `s = n`。

## 迭代器（[string.iterators]）

¶1–4：`begin`/`end`/`rbegin`/`rend` 及其 `c` 版本，语义同容器。`end()` 指向终止符的位置，但**不能**解引用 `end()` 来读终止符——那是迭代器的越界解引用；要读用 `s[s.size()]`。libc++ 的 `string::iterator` 是一个包装类型（`__wrap_iter<char*>`），而 `string_view::const_iterator` 就是 `const char*`。

## 容量（[string.capacity]）

**`size()`/`length()`**（¶1–2）：常数时间。

**`resize(n, c)` / `resize(n)`**（¶5–6）：截断或追加 `n - size()` 个 `c`；`resize(n)` 用 `charT()` 填充。

**`resize_and_overwrite(n, op)`** {{c++23}}（¶7–11，[[P1072R10]]）：为"先分配一块缓冲区、交给 C API 填充、再确定实际长度"这一模式设计，避免 `resize(n)` 的无用清零：

```cpp run ok
#include <string>
#include <cstdio>
#include <cassert>

int main() {
  std::string s;
  s.resize_and_overwrite(32, [](char* p, std::size_t n) {
    return std::snprintf(p, n + 1, "%d-%d", 12, 34);   // 可以写 n+1 个字符（含终止符位置）
  });
  assert(s == "12-34" && s.size() == 5);
}
```

契约（¶7–10）：

- `p` 指向的 `[p, p+n]`（**闭区间**，所以 `op` 可以往 `p[n]` 写终止符，`snprintf` 正需要这个）有效；前 `k = min(size(), n)` 个字符是原内容，`[p+k, p+n]` 可能是不确定值（[[basic.indet]]）；
- ¶8 *Mandates*：`std::move(op)(p, m)` 返回整数类类型；
- ¶9 前置条件：`op` **不得抛出**、不得修改 `p` 和 `m`；返回值 `r` 满足 `0 <= r <= m`；`[p, p+r)` 中不能留下不确定值；
- ¶10 效果：内容变为 `[p, p+r)`，并使 `[p, p+n]` 的所有指针和引用失效——即 `op` 不能把 `p` 存起来以后再用。

违反任何一条前置条件都是 {{ub}}，没有加固检查。`op` 抛异常同样是 UB，这一点与整个类的强异常保证（[string.require] ¶2）形成例外：实现无法在 `op` 写了一半时回滚。

**`capacity()`**（¶12–13）：已分配存储的大小。

**`reserve(res_arg)`**（¶14–15）：

!!! std
    Following a call to `reserve`, `capacity()` is greater or equal to the argument of `reserve` if reallocation happens; and equal to the previous value of `capacity()` otherwise. Reallocation happens at this point if and only if the current capacity is less than the argument of `reserve`.

C++20 起 `reserve` **不再缩容**（[[P0966R1]]）：参数小于当前容量时什么也不做。在那之前，`s.reserve()`（无参数，默认 0）是一个非绑定的缩容请求，无参版本在 C++20 被弃用、后来被移除。现在要缩容只能用 `shrink_to_fit()`。`res_arg > max_size()` 抛 `length_error`。本机 libc++：`reserve(100)` 后 `capacity() == 103`。

**`shrink_to_fit()`**（¶16–18）：非绑定的缩容请求；不增加容量；重新分配时使所有引用、指针、迭代器（包括尾后迭代器）失效。libc++ 会在内容放得下时缩回对象内部的 SSO 缓冲区。

**`clear()`**（¶19）：等价于 `erase(begin(), end())`——**不释放内存**，`capacity()` 不变。**`empty()`**（¶20）。

## 元素访问（[string.access]）

| 成员 | 前置条件 | 越界时 |
|---|---|---|
| `operator[](pos)` | 加固：`pos <= size()`（¶1） | 加固实现中为契约违反，否则 {{ub}} |
| `at(pos)` | — | `pos >= size()` 抛 `out_of_range`（¶6） |
| `front()` / `back()` | 加固：`!empty()`（¶7、¶9） | 同 `operator[]` |

`operator[]` 允许 `pos == size()`，返回终止符；`at(size())` 却抛异常——两者的边界差一。C++26 把这些前置条件标为 *Hardened preconditions*（[[P3471R4]]，含义见 [[structure.specifications]]）：在加固实现中违反它们必定被检查并作为契约违反处理，而不是放任 UB。libc++ 用 `_LIBCPP_ASSERT_VALID_ELEMENT_ACCESS` 实现这些检查，由 `_LIBCPP_HARDENING_MODE` 宏控制（本机默认关闭）。

## 修改器（[string.modifiers]）

所有修改器都遵循同一模式：核心版本接受 `(const charT* s, size_type n)`，其余重载"等价于"构造一个视图后调用它。

### 共同的"`string_view` 类对象"重载

`operator+=`、`append`、`assign`、`insert`、`replace`、`find` 族、`compare` 都有这样一个模板重载：

```cpp
template<class T> constexpr basic_string& append(const T& t);
// Constraints: is_convertible_v<const T&, basic_string_view<charT, traits>> 为 true，
//              且 is_convertible_v<const T&, const charT*> 为 false
```

为什么是模板而不是直接接受 `basic_string_view`？如果直接写 `append(basic_string_view)`，那么 `s.append("abc")` 会在 `append(const charT*)` 和 `append(basic_string_view)` 之间产生二义（两者都是一次转换）。写成模板并排除 `const charT*`，字面量和 `char*` 就只匹配 `const charT*` 重载，而 `std::string_view`、自定义的可转换类型匹配模板。

### `+=`、`append`、`push_back`（[string.op.append]、[string.append]）

- `append(const charT* s, size_type n)`（¶7–9）：前置条件 `[s, s+n)` 有效；
- `append(const basic_string& str, pos, n)`（¶2）：带位置的版本都通过 `substr` 定义，所以 `pos > str.size()` 抛 `out_of_range`；
- `append(InputIterator, InputIterator)`（¶15）：等价于先构造临时 `basic_string` 再追加——这保证了**自引用安全**（`s.append(s.begin(), s.end())` 正确）；
- `append_range`（¶16）：C++23；
- `push_back(c)`（¶18）：等价于 `append(1, c)`。

自引用：`s += s`、`s.append(s.data() + 1, 3)` 这类"源与目标是同一个字符串"的调用都必须正确，因为规范是按值语义写的（"Appends a copy of the range"），没有给出"源不得与 `*this` 重叠"的前置条件。实现需要在重新分配前先复制源内容。

### `assign`（[string.assign]）

`assign(size_type n, charT c)`（¶14）定义为 `clear(); resize(n, c);`。其余同 `append` 模式。`assign(basic_string&&)` 等价于移动赋值。

### `insert`（[string.insert]）

位置版本：`pos > size()` 抛 `out_of_range`，结果超长抛 `length_error`（¶10、¶14）。迭代器版本：前置条件 `p` 是 `*this` 上的有效迭代器，返回指向第一个插入字符的迭代器（`n == 0` 时返回 `p`）。

### `erase`、`pop_back`（[string.erase]）

- `erase(pos = 0, n = npos)`（¶1–3）：删除 `[pos, pos + min(n, size()-pos))`；`pos > size()` 抛 `out_of_range`。所以 `s.erase(3)` 是"删除从 3 开始的所有字符"——**不是**删除下标 3 的一个字符；后者要写 `s.erase(s.begin() + 3)`。
- `erase(const_iterator p)`（¶4–7）：前置条件 `p` 可解引用；不抛。
- `pop_back()`（¶12–14）：加固前置条件 `!empty()`。

### `replace`（[string.replace]）

核心版本 ¶7–10：替换 `[pos1, pos1 + min(n1, size()-pos1))` 为 `[s, s+n2)`；`pos1 > size()` 抛 `out_of_range`；结果超长抛 `length_error`。迭代器版本（¶17、¶21）前置条件：`[begin(), i1)` 和 `[i1, i2)` 是有效范围。

### `copy`、`swap`（[string.copy]、[string.swap]）

`copy(s, n, pos)` 等价于 `basic_string_view(*this).copy(s, n, pos)`，注：**不写终止符**。

`swap`（¶1–4）：前置条件——`propagate_on_container_swap` 为真，**或**两者分配器相等；否则 {{ub}}。不抛，常数时间。

## 字符串操作（[string.ops]）

### `c_str()`、`data()`、转换为 `string_view`（[string.accessors]）

¶1：`c_str()`、`data() const`、`data()` 都返回 `to_address(begin())`，常数时间。所以 `c_str() == data()` 永远成立，两者唯一的区别是非 const 的 `data()`（C++17 起）返回可写的 `charT*`。

¶3：`operator basic_string_view<charT, traits>() const noexcept`，等价于 `basic_string_view(data(), size())`。这是 `string → string_view` 的隐式转换，也是 [[string.view]] 中所有悬垂问题的入口。

¶4：`get_allocator()`。

### 查找（[string.find]）

¶1 把所有 `basic_string`、`const charT*`、`(const charT*, n)`、`charT` 重载归结为 `string_view` 版本；¶2–4 是模板版本（约束同上），其 `noexcept` 等价于 `is_nothrow_convertible_v<const T&, basic_string_view>`。语义完全由 [string.view.find] 规定（见 [[string.view]]）：找不到返回 `npos`，**从不抛 `out_of_range`**。

### `substr` 与 `subview`（[string.substr]）

```cpp
constexpr basic_string substr(size_type pos = 0, size_type n = npos) const &;
constexpr basic_string substr(size_type pos = 0, size_type n = npos) &&;
constexpr basic_string_view<charT, traits> subview(size_type pos = 0, size_type n = npos) const;
```

- C++23 把 `substr` 拆成 `const &` 和 `&&` 两个重载（[[P2438R2]]）：对右值调用时等价于 `basic_string(std::move(*this), pos, n)`，可以复用源的缓冲区。`make().substr(1)` 因此可能零分配。
- `subview` 是工作草案在 C++26 之后新增的：返回视图、不复制。`pos > size()` 都抛 `out_of_range`。
- 坑：`auto t = s.subview(1);` 的 `t` 是 `string_view`，`s` 一旦修改或销毁，`t` 就悬垂；对**右值** `string` 调用 `subview` 会立即产生悬垂视图。

### `compare`（[string.compare]）

全部"等价于"`basic_string_view(*this)` 的对应 `compare`（[[string.view]]）。带 `pos1`、`n1` 的版本 `pos1 > size()` 抛 `out_of_range`。

### `starts_with`、`ends_with`、`contains`

[string.starts.with]、[string.ends.with]（C++20，[[P0457R2]]）与 [string.contains]（C++23，[[P1679R3]]）：都等价于 `basic_string_view(data(), size())` 的同名成员，各有接受 `basic_string_view`、`charT`、`const charT*` 三个重载。

```cpp run ok
#include <string>
#include <cassert>

int main() {
  std::string s = "hello";
  assert(s.starts_with("he") && s.starts_with('h') && !s.ends_with("lo!"));
  assert(s.contains("ell") && s.contains('o') && !s.contains("xyz"));
  assert(!std::string{}.starts_with('a'));   // 空串：false，不违反 front() 的前置条件
}
```

## `constexpr basic_string` 与瞬态分配

C++20 起 `basic_string` 的所有成员都是 `constexpr`（[[P0980R1]]）。但常量求值中分配的内存必须在同一次求值内释放（瞬态分配，[[g:transient-allocation]]，[[expr.const]]），所以：

```cpp
constexpr std::size_t f() { std::string s = "a fairly long string that leaves SSO"; return s.size(); }
static_assert(f() == 36);                                     // OK：分配在 f 内部释放
constexpr std::string s2 = "a fairly long string that leaves SSO";  // error：指向堆分配对象的指针不是常量表达式
constexpr std::string s1 = "short";                           // 本机 libc++ 接受：SSO，无分配
```

`s1` 能编译完全是实现细节：短字符串在 libc++ 中不分配内存。换一个 SSO 容量不同的实现，或者把字符串加长一个字符，同样的代码就会失败。可移植代码不应依赖它；需要编译期字符串常量时用 `std::string_view` 或字符数组。

## 思考题

!!! question "1. `const char* p = s.c_str(); s.push_back('x'); std::puts(p);`——如果 `s.capacity() > s.size() + 1`，这段代码合法吗？"

<details markdown="1">
<summary>展开查看答案与解析</summary>

按标准**不保证**。[string.require] ¶4.2 规定调用除九个例外以外的非 const 成员函数"may invalidate"指针，`push_back` 不在例外名单里，标准也没有像 `vector` 那样把失效限定在"重新分配时"。所以 `p` 可能已失效，使用它是 {{ub}}。实践中三大实现在容量足够时都不会搬动缓冲区，但 `p` 所指的序列已经不再以 `'\0'` 正确终止于原位置——`push_back` 把原终止符位置改写为 `'x'`，并在后面写了新终止符，所以 `puts(p)` 即便"能用"也会打印出带 `x` 的内容。

</details>

!!! question "2. 为什么 `std::string s = sv;`（`sv` 是 `std::string_view`）非良构，而 `std::string s = “abc”;` 合法？"

<details markdown="1">
<summary>展开查看答案与解析</summary>

拷贝初始化只考虑转换构造函数（非 `explicit` 的）。从 `string_view` 的构造函数 `template<class T> explicit basic_string(const T&, const Allocator& = Allocator())` 是 `explicit` 的（[string.cons] ¶11），`string_view` 也没有到 `string` 的转换函数。`"abc"` 走的是 `basic_string(const charT*, const Allocator& = Allocator())`，非 `explicit`。设计意图：涉及分配的转换必须显式写出（[[P0254R2]]）。

</details>

!!! question "3. `a.swap(b)` 之后，原来指向 `b` 中字符的迭代器指向哪里？换成 `std::vector<char>` 呢？"

<details markdown="1">
<summary>展开查看答案与解析</summary>

对 `vector`，[[container.reqmts]] ¶65 保证交换后迭代器指向**另一个容器中的同一元素**（缓冲区指针被交换，元素不动），¶66.6 还保证 `swap` 不使引用、指针、迭代器失效。对 `string`，[string.require] ¶4.1（脚注点名 `swap()`）说它们可能失效。原因是 SSO：两个短字符串的字符都存放在各自对象内部，交换只能**复制**字符，旧迭代器仍指向原来那个对象内部的缓冲区——现在那里存的是另一个字符串的内容。

</details>

## 小结

| 主题 | 规则 |
|---|---|
| 不变式 | 连续；`[data(), data()+size()]` 有效；`data()[size()] == charT()`；改终止符为非零是 UB |
| 异常 | 超长抛 `length_error`；任何成员抛异常则无副作用（强保证），`resize_and_overwrite` 的 `op` 抛出则是 UB |
| 失效 | 除 `[]`/`at`/`data`/`front`/`back`/`begin`/`end`/`rbegin`/`rend` 外的非 const 成员都可能使失效；移动赋值也会 |
| SSO | 未强制但被允许；libc++ 24 字节，`char` 容量 22 |
| 构造 | 从 `string_view` 为 `explicit`；`nullptr` 删除；`{n, c}` 是初始化列表 |
| `reserve` | C++20 起只增不减；缩容用 `shrink_to_fit`（非绑定） |
| 访问 | `operator[]` 加固 `pos <= size()`；`at` 抛 `out_of_range`（`pos >= size()`） |
| 重载族 | 模板 `T` 可转 `string_view` 且不可转 `const charT*` |
| `substr` | `&&` 重载复用缓冲区；`subview` 返回视图 |
| constexpr | 分配必须是瞬态的；短字符串 constexpr 变量能否编译取决于实现 |
