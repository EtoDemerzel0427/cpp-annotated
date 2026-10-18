---
title: 正则匹配：结果、算法与迭代器
summary: sub_match 是一对指向原序列的迭代器；match_results 的“ready”状态、未参与匹配的子表达式、prefix/suffix/position；regex_match 与 regex_search 的区别和失败时的后置条件；regex_replace 的格式规则；regex_iterator 对零长度匹配的处理与 regex_token_iterator；为防悬垂而删除的右值重载，以及它们拦不住的情形
status: draft
covers: re.submatch, re.submatch.general, re.submatch.members, re.submatch.op, re.results, re.results.general, re.results.const, re.results.state, re.results.size, re.results.acc, re.results.form, re.results.all, re.results.swap, re.results.nonmember, re.alg, re.except, re.alg.match, re.alg.search, re.alg.replace, re.iter, re.regiter, re.regiter.general, re.regiter.cnstr, re.regiter.comp, re.regiter.deref, re.regiter.incr, re.tokiter, re.tokiter.general, re.tokiter.cnstr, re.tokiter.comp, re.tokiter.deref, re.tokiter.incr
since: c++11
related: re, basic.life, class.temporary, iterator.requirements, container.alloc.reqmts, dcl.fct.def.delete
tags: 标准库, 正则表达式, regex, 悬垂引用, 迭代器
updated: 2026-10-18
---

本页是 [[re]] 的下半部分：正则表达式**用起来**之后得到什么。核心只有一句话——**匹配结果不拥有任何字符，它只是一组指向被搜索序列的迭代器**。几乎所有关于 `<regex>` 结果的坑都由此而来。

## `sub_match`：一对迭代器（[re.submatch]）

[re.submatch.general]/1：`sub_match` 表示某个标记子表达式匹配到的字符序列。它**公开派生自** `pair<BidirectionalIterator, BidirectionalIterator>`，额外有一个 `bool matched` 成员：

- `first`/`second`：匹配到的区间 `[first, second)`；
- `matched`：该子表达式是否参与了匹配；
- `length()`（[re.submatch.members]/2）：`matched ? distance(first, second) : 0`；
- `str()` 与 `operator string_type()`（¶3–¶4）：`matched` 时**拷贝**出一个 `basic_string`，否则空串；
- `compare(...)`（¶5–¶7）：都定义为 `str().compare(...)`。

[re.submatch.op] 为 `sub_match` 与 `sub_match`、`basic_string`、`const value_type*`、单个字符之间提供 `==` 和 `<=>`；比较类别 *SM-CAT*`(I)` 是对应 `basic_string` 的三路比较结果类型（¶1）。因此可以直接写 `m[1] == "2024"`。

## `match_results`（[re.results]）

### 它是一个（受限的）容器（[re.results.general]）

¶1–¶2：`match_results` 是 `sub_match` 的集合，满足分配器感知容器（[[container.alloc.reqmts]]）和序列容器的要求，但**只支持拷贝/移动赋值和 const 容器操作**，且比较运算符语义不同。

!!! std
    The effects of calling most member functions from a match_results object that is not ready are undefined.

¶3 定义 [[g:ready-match-results|ready]]：默认构造的 `match_results` 没有完全建立的结果状态；一次**已完成的**正则匹配修改它之后，它才是 *ready* 的。对非 ready 的对象调用大多数成员函数是 {{ub}}。具体来说，`length`、`position`、`str`、`operator[]`、`prefix`、`suffix`、`format` 都以 `ready() == true` 为前置条件（[re.results.acc]、[re.results.form]）。`size()`/`empty()`/`ready()` 不受此限：默认构造的对象 `size() == 0`（[re.results.const]/3）。

### 下标 0 与未参与的子表达式（¶4）

- `m[0]` 表示整个匹配，`m[0].matched` 总为真。
- `m[n]` 表示第 `n` 个标记子表达式。若它参与了匹配，`matched` 为真，`[first, second)` 是匹配到的区间；**否则 `matched` 为假，`first` 和 `second` 都指向被搜索序列的末尾**。
- 注 1：未参与匹配的多个 `sub_match` 不必是不同的对象。

[re.results.acc]/8：`n >= size()` 时 `operator[]` 返回一个表示未匹配子表达式的 `sub_match`——**越界下标不是 UB**，这与普通容器不同。

### 大小与访问（[re.results.size]、[re.results.acc]）

- `size()`（[re.results.size]/1）：成功匹配后为 `1 + mark_count()`，否则 0。注 1：`match_results` 的状态只能通过把它传给 `regex_match`/`regex_search` 来改变。
- `position(n)`（[re.results.acc]/4）：从**目标序列开头**到 `(*this)[n].first` 的距离。“目标序列开头”的含义在 `regex_iterator` 中会被重新定义（见下文）。
- `prefix()`/`suffix()`（¶10、¶12）：匹配之前/之后的部分。

### 格式化（[re.results.form]）

`format(out, fmt_first, fmt_last, flags)`（¶1–¶3）：把格式串拷贝到输出，并将其中的格式说明符替换为对应的子匹配。默认（`format_default`）使用 ECMAScript `replace` 规则：`$&` 整个匹配、`$n`/`$nn` 第 n 个子匹配、`` $` `` 前缀、`$'` 后缀、`$$` 字面 `$`；`format_sed` 改用 sed 规则（`&`、`\n`）。另有返回 `basic_string` 的重载（¶5–¶10）。

### 拷贝、比较、swap

- 表 122（[re.results.const]）：拷贝/移动后 `ready()`、`size()`、`str(n)`、`prefix()`、`suffix()`、`(*this)[n]`、`length(n)`、`position(n)` 都与源相同。注意：拷贝出来的 `sub_match` **仍然指向原来的字符序列**。
- `operator==`（[re.results.nonmember]/1）：两者都非 ready 时为真；一个 ready 一个不 ready 时为假；都 ready 时，都为空则相等，都非空则要求 `prefix`、所有子匹配、`suffix` 分别相等（按**内容**比较，不按迭代器）。
- `swap` 常数时间（[re.results.swap]）。

## 算法（[re.alg]）

### 只可能抛两种异常（[re.except]）

¶1：本节的算法可能抛 `regex_error`，且其 `code()` 只能是 `error_complexity` 或 `error_stack`。也就是说，匹配期间“太复杂”或“栈不够”是**以异常而非崩溃**报告的——前提是实现确实检测了。

```cpp run title="regex-complexity.cpp" ok
#include <cassert>
#include <regex>
#include <string>

int main() {
    std::regex re("(a*)*c");                         // 嵌套量词：经典的灾难性回溯
    std::string s(26, 'a');
    try {
        std::regex_match(s + "b", re);
    } catch (const std::regex_error& e) {
        // [re.except]：算法只可能抛这两种错误码
        assert(e.code() == std::regex_constants::error_complexity ||
               e.code() == std::regex_constants::error_stack);
    }
}
```

本机 libc++ 23 在这里抛出 `error_complexity`；标准并不要求一定抛出——另一个实现可能只是运行很久。

### `regex_match`：必须匹配整个序列（[re.alg.match]）

¶1：迭代器必须满足 `bidirectional_iterator`。¶2：判断正则 `e` 是否匹配**整个** `[first, last)`——只考虑覆盖整个序列的潜在匹配。

¶3 的后置条件：无论成功与否，`m.ready() == true`；失败时 `m` 的状态除 `size() == 0`、`empty() == true` 外**未指明**。成功时按表 123：`m.size() == 1 + e.mark_count()`，`prefix()` 是空区间 `[first, first)` 且 `matched == false`，`suffix()` 是 `[last, last)`，`m[0]` 是 `[first, last)`。

其余重载（¶4–¶8）都转发到迭代器版本；不带 `match_results` 的版本内部构造一个临时的 `match_results`。

### `regex_search`：找任意一个子序列（[re.alg.search]）

¶2：判断 `[first, last)` 中是否存在**某个**与 `e` 匹配的子序列。按 ECMAScript 语义，找到的是**最左**的那个；在最左位置上，选的是**第一个**成功的分支（POSIX 文法则选最长的）。¶3 的后置条件同样要求 `m.ready()`，成功时 `prefix()` 是 `[first, m[0].first)`，`suffix()` 是 `[m[0].second, last)`（表 124）。

标准在 [re.alg.match] 例 1 中给出对照：

| 调用（`re` 为 `"Get|GetValue"`） | 结果 | `m[0]` |
|---|---|---|
| `regex_search("GetValue", m, re)` | true | `"Get"` |
| `regex_match("GetValue", m, re)` | true | `"GetValue"` |
| `regex_search("GetValues", m, re)` | true | `"Get"` |
| `regex_match("GetValues", m, re)` | false | — |

### `regex_replace`（[re.alg.replace]）

¶1：构造一个 `regex_iterator` 遍历所有匹配；对每个匹配，若未设置 `format_no_copy`，先输出其前缀，再输出 `m.format(fmt, flags)`；最后（若未设置 `format_no_copy`）输出最后一个匹配之后的剩余部分；若设置了 `format_first_only`，只替换第一个匹配。没有匹配时整个输入被原样拷贝（除非 `format_no_copy`）。¶3–¶6 是返回 `basic_string` 的便利重载。

## 迭代器（[re.iter]）

### `regex_iterator`（[re.regiter]）

[re.regiter.general]/1：`regex_iterator` 是一个迭代器适配器，用 `regex_search` 逐个找出序列中**所有**的匹配；每次 `++` 都找下一个并存进内部的 `match_results`。默认构造的是序列尾迭代器；解引用得到 `const match_results&`。两个非尾迭代器“由相同实参构造”时相等。

它持有的是指向 regex 的**指针**（构造函数把 `pregex` 设为 `addressof(re)`，[re.regiter.cnstr]/2）——因此 regex 必须比迭代器活得久。

¶2 定义 [[g:zero-length-match]]：`match[0].matched` 为真且 `match[0].first == match[0].second`，例如模式只由 `^`、`$`、`\b` 之类断言构成，或 `x*` 在不含 `x` 的位置上。

`operator++`（[re.regiter.incr]）的规则是为了**保证进展**：

- ¶1：从 `start = match[0].second` 继续。
- ¶2：若当前是零长度匹配且 `start == end`，变为尾迭代器。
- ¶3：若当前是零长度匹配，先用 `match_not_null | match_continuous` 在 `start` 处再试一次（找一个从同一位置开始的**非空**匹配）；失败则把 `start` 前进一位，再按普通情况继续。
- ¶4：普通情况下加上 `match_prev_avail` 再搜索——这样 `^` 不会误匹配上次匹配结束的位置，`\b` 能看到前一个字符。
- ¶5–¶6：每次成功后，`match.prefix().first` 等于上一次的 `match[0].second`，且 `match.position(i)` 是相对于**最初** `begin` 的偏移，而不是相对于本次搜索起点。¶7–¶8：实现如何做到这一点未指明——注 2 说明实现可能调用内部搜索函数，所以用户提供的 `regex_search` 特化不会被调用。

### `regex_token_iterator`（[re.tokiter]）

`regex_token_iterator` 在 `regex_iterator` 之上，按给定的子匹配下标列表依次产出 `sub_match`：下标 `n >= 0` 取每个匹配的第 `n` 个子匹配；下标 **-1** 表示取**匹配之间**的部分——这就是用正则做 `split` 的标准写法。最后一个匹配之后若还有剩余字符，-1 也会把它作为最后一个 token 产出。

```cpp run title="regex-iterators.cpp" ok
#include <cassert>
#include <regex>
#include <string>
#include <vector>

int main() {
    std::string s = "a,b,,c";
    std::regex sep(",");
    std::vector<std::string> v(std::sregex_token_iterator(s.begin(), s.end(), sep, -1), {});
    assert((v == std::vector<std::string>{"a", "b", "", "c"}));   // -1：取匹配之间的部分

    std::string t = "ab";
    std::regex empty("x*");
    int n = 0;
    for (std::sregex_iterator it(t.begin(), t.end(), empty), end; it != end; ++it) ++n;
    assert(n == 3);   // 位置 0、1、2 各一个零长度匹配，迭代器保证前进
}
```

## 综合示例

```cpp run title="match-results.cpp" ok
#include <cassert>
#include <regex>
#include <string>

int main() {
    std::regex date(R"((\d{4})-(\d{2})(?:-(\d{2}))?)");
    std::smatch sm;
    std::string s = "on 2024-07 ok";
    assert(std::regex_search(s, sm, date));
    assert(sm.size() == 4);                           // 1 + mark_count()：(?:...) 不计入
    assert(sm[1] == "2024" && sm[2] == "07");
    assert(!sm[3].matched && sm[3].first == s.end()); // 未参与匹配：指向被搜索序列末尾
    assert(sm[99].matched == false);                  // 越界下标：返回未匹配的 sub_match
    assert(sm.prefix() == "on " && sm.suffix() == " ok");
    assert(sm.position(1) == 3);
    assert(sm.format("$2/$1") == "07/2024");
    assert(std::regex_replace(s, date, "[$&]") == "on [2024-07] ok");
}
```

## 悬垂：被删除的重载与它们拦不住的情形

因为 `match_results` 只存迭代器，用临时 `std::string` 做搜索目标、事后再读结果，是典型的悬垂（[[class.temporary]]）。标准为此删除了两组重载（[re.syn]）：

- `regex_match`/`regex_search(const basic_string&&, match_results&, ...)` —— `= delete`；
- `regex_iterator`/`regex_token_iterator` 接受 `const regex_type&&` 的构造函数 —— `= delete`（迭代器存的是 regex 的地址）。

```cpp title="deleted-overloads.cpp" error
#include <regex>
#include <string>
std::string get() { return "key=value"; }
int main() {
    std::regex re("(\\w+)=(\\w+)");
    std::smatch m;
    std::regex_search(get(), m, re);                                      // error: 调用被删除的函数
    std::sregex_iterator it(get().begin(), get().end(), std::regex("x")); // error: 调用被删除的构造函数
}
```

不带 `match_results` 的 `regex_search(get(), re)` 仍然合法——它只返回 `bool`，不会悬垂。但删除重载只认得 `basic_string` 右值，**拦不住**经由指针的情形：

```cpp run title="dangling-cmatch.cpp" ub
#include <iostream>
#include <regex>
#include <string>

std::string load() { return "user=alice; a long enough line to defeat SSO"; }

int main() {
    std::regex re(R"((\w+)=(\w+))");
    std::cmatch m;
    if (std::regex_search(load().c_str(), m, re))   // 编译通过：const char* 重载没有被删除
        ;                                           // 完整表达式结束，临时 string 已销毁
    std::cout << m[2] << '\n';                      // UB: m 中的指针悬空
}
```

本机用 `-fsanitize=address` 运行，报告 heap-use-after-free。同理，`std::string_view` 指向的串被销毁、或者 `std::string` 在匹配之后被修改（可能重新分配），都会让已有的 `match_results` 失效。

## 思考题

<details markdown="1">
<summary>1. 对一个刚默认构造的 `std::smatch m;`，`m[0]`、`m.size()`、`m.empty()` 分别是否合法？</summary>

`m.size()`（返回 0）和 `m.empty()`（返回 true）合法，它们没有 `ready()` 前置条件（[re.results.size]、[re.results.const]/3）。`m[0]` 是 {{ub}}：[re.results.acc]/7 要求 `ready() == true`，而默认构造的对象不是 ready 的（[re.results.general]/3）。注意这和“匹配失败后的 `m[0]`”不同：匹配失败后 `m` 是 ready 的（[re.alg.match]/3），此时 `m[0]` 因 `0 >= size()` 而返回一个未匹配的 `sub_match`（[re.results.acc]/8），是合法的。
</details>

<details markdown="1">
<summary>2. 用 `sregex_iterator` 遍历时，`(*it).position(0)` 是相对于什么的偏移？</summary>

相对于构造迭代器时传入的 `begin`，而不是本次 `regex_search` 的起点（[re.regiter.incr]/5–6）。实现必须调整 `match_results` 使 `position` 反映整个目标序列中的位置，`prefix().first` 也必须等于上一次匹配的 `match[0].second`。
</details>

## 小结

| 要点 | 出处 |
|---|---|
| `sub_match` 是 `pair<It, It>` + `matched`；不拥有字符 | [re.submatch.general] |
| 非 ready 的 `match_results` 上调用多数成员是 UB | [re.results.general]/3 |
| 未参与的子表达式：`matched == false`，迭代器指向序列末尾 | [re.results.general]/4 |
| 越界 `operator[]` 返回未匹配的 `sub_match` | [re.results.acc]/8 |
| 算法只抛 `error_complexity`/`error_stack` | [re.except]/1 |
| `regex_match` 要求覆盖整串；`regex_search` 找最左匹配 | [re.alg.match]/2、[re.alg.search]/2 |
| `regex_iterator` 对零长度匹配先尝试非空匹配，再前进一位 | [re.regiter.incr]/3 |
| `basic_string&&` 与 `regex&&` 的重载被删除，但 `c_str()` 悬垂拦不住 | [re.syn] |
