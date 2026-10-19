---
title: 正则匹配：结果、算法与迭代器
summary: 匹配结果 sub_match 和 match_results 只保存指向原序列的迭代器；regex_match 与 regex_search 的区别和失败后的状态；regex_replace 的格式规则；regex_iterator 怎样处理零长度匹配；为防止悬垂而删除的右值重载，以及它们拦不住的情形。
status: draft
covers: re.submatch, re.submatch.general, re.submatch.members, re.submatch.op, re.results, re.results.general, re.results.const, re.results.state, re.results.size, re.results.acc, re.results.form, re.results.all, re.results.swap, re.results.nonmember, re.alg, re.except, re.alg.match, re.alg.search, re.alg.replace, re.iter, re.regiter, re.regiter.general, re.regiter.cnstr, re.regiter.comp, re.regiter.deref, re.regiter.incr, re.tokiter, re.tokiter.general, re.tokiter.cnstr, re.tokiter.comp, re.tokiter.deref, re.tokiter.incr
since: c++11
related: re, basic.life, class.temporary, iterator.requirements, container.alloc.reqmts, dcl.fct.def.delete
tags: 标准库, 正则表达式, regex, 悬垂引用, 迭代器
updated: 2026-10-19
---

!!! tldr
    - 匹配结果不拥有字符，只保存指向被搜索序列的迭代器。被搜索的字符串销毁或修改后，结果就失效了。
    - 默认构造的 `match_results` 还不是 ready 的，在它上面调用 `operator[]`、`str()` 等成员是 UB；匹配过一次（无论成功与否）之后才可以调用。
    - `regex_match` 要求整个序列都匹配；`regex_search` 找最左边的一个匹配。
    - `regex_iterator` 遇到零长度匹配时会保证前进；`regex_token_iterator` 的下标 -1 取匹配之间的部分，可以用来分割字符串。
    - 标准删除了以右值 `std::string` 为目标的重载，但经由 `c_str()` 的悬垂拦不住。

本页是 [[re]] 的下半部分：用正则表达式匹配之后得到什么。

## 一个例子

```cpp run title="match-results.cpp" ok
#include <cassert>
#include <regex>
#include <string>

int main() {
  std::regex date(R"((\d{4})-(\d{2})(?:-(\d{2}))?)");
  std::smatch sm;
  std::string s = "on 2024-07 ok";
  assert(std::regex_search(s, sm, date));
  assert(sm.size() == 4);              // 1 + mark_count()，(?:...) 不计入
  assert(sm[1] == "2024" && sm[2] == "07");
  assert(!sm[3].matched && sm[3].first == s.end());  // 未参与匹配
  assert(sm[99].matched == false);     // 越界下标：返回未匹配的 sub_match
  assert(sm.prefix() == "on " && sm.suffix() == " ok");
  assert(sm.position(1) == 3);
  assert(sm.format("$2/$1") == "07/2024");
  assert(std::regex_replace(s, date, "[$&]") == "on [2024-07] ok");
}
```

`sm` 里的每一项都是一对指向 `s` 的迭代器。`sm[1] == "2024"` 能成立，是因为比较时才把这段字符拷贝出来。下面逐个说明这些成员的规则。

## sub_match：一对迭代器（[re.submatch]）

[re.submatch.general] ¶1 `sub_match` 表示一个标记子表达式匹配到的字符序列。它公开派生自 `pair<BidirectionalIterator, BidirectionalIterator>`，多一个 `bool matched` 成员：

- `first`、`second`：匹配到的区间 `[first, second)`；
- `matched`：这个子表达式是否参与了匹配；
- `length()`（[re.submatch.members] ¶2）：`matched` 时是 `distance(first, second)`，否则是 0；
- `str()` 和 `operator string_type()`（¶3–¶4）：`matched` 时拷贝出一个 `basic_string`，否则返回空串；
- `compare(...)`（¶5–¶7）：都定义为 `str().compare(...)`。

[re.submatch.op] 为 `sub_match` 与 `sub_match`、`basic_string`、字符指针、单个字符之间提供 `==` 和 `<=>`，比较的是内容。所以可以直接写 `sm[1] == "2024"`。

## match_results（[re.results]）

### ready 状态（[re.results.general] ¶3）

¶1–¶2 `match_results` 是 `sub_match` 的集合，满足分配器感知容器（[[container.alloc.reqmts]]）和序列容器的要求，但只支持复制、移动赋值和 const 操作。

¶3 默认构造的 `match_results` 还没有完整的结果状态。一次匹配完成并修改了它之后，它才成为 [[g:ready-match-results|ready]] 的：

!!! std
    The effects of calling most member functions from a match_results object that is not ready are undefined.

具体来说，`length`、`position`、`str`、`operator[]`、`prefix`、`suffix`、`format` 都以 `ready() == true` 为前置条件（[re.results.acc]、[re.results.form]）。`size()`、`empty()`、`ready()` 没有这个限制，默认构造的对象 `size()` 为 0（[re.results.const] ¶3）。

### 下标 0 与未参与匹配的子表达式（¶4）

- `m[0]` 表示整个匹配，`m[0].matched` 总是 true。
- `m[n]` 表示第 `n` 个标记子表达式。它参与了匹配时，`matched` 为 true，`[first, second)` 是匹配到的区间；否则 `matched` 为 false，`first` 和 `second` 都指向被搜索序列的末尾。开头例子中可选的第三组就是这样。
- 注 1：几个未参与匹配的子表达式，对应的 `sub_match` 不必是不同的对象。

[re.results.acc] ¶8 规定，`n >= size()` 时，`operator[]` 返回一个表示未匹配子表达式的 `sub_match`。所以越界下标不是 UB，这一点与普通容器不同。

### 大小与访问（[re.results.size]、[re.results.acc]）

- `size()`（[re.results.size] ¶1）：匹配成功后是 `1 + mark_count()`，否则是 0。注 1 说明，`match_results` 的状态只能通过把它传给 `regex_match` 或 `regex_search` 来改变。
- `position(n)`（[re.results.acc] ¶4）：从目标序列开头到 `(*this)[n].first` 的距离。`regex_iterator` 会重新规定目标序列开头指什么，见下文。
- `prefix()`、`suffix()`（¶10、¶12）：匹配之前、之后的部分。

### 格式化（[re.results.form]）

¶1–¶3 `format(out, fmt_first, fmt_last, flags)` 把格式串复制到输出，并把其中的格式说明符替换成对应的子匹配。默认（`format_default`）使用 ECMAScript `replace` 的规则：`$&` 是整个匹配，`$n`、`$nn` 是第 n 个子匹配，`` $` `` 是前缀，`$'` 是后缀，`$$` 是字面的 `$`。设置 `format_sed` 后改用 sed 的规则（`&`、`\n`）。¶5–¶10 是返回 `basic_string` 的重载。

### 复制、比较、swap

- 表 122（[re.results.const]）：复制或移动之后，`ready()`、`size()`、`str(n)`、`prefix()`、`suffix()`、`(*this)[n]`、`length(n)`、`position(n)` 都与源对象相同。复制出的 `sub_match` 仍然指向原来的字符序列。
- [re.results.nonmember] ¶1 `operator==`：两者都不是 ready 时相等；一个 ready 一个不是时不等；都 ready 时，都为空则相等，都非空则逐个比较 `prefix`、所有子匹配和 `suffix` 的内容。
- `swap` 是常数时间操作（[re.results.swap]）。

## 算法（[re.alg]）

### regex_match 与 regex_search

| 调用（`re` 是 `"Get|GetValue"`） | 结果 | `m[0]` |
|---|---|---|
| `regex_search("GetValue", m, re)` | true | `"Get"` |
| `regex_match("GetValue", m, re)` | true | `"GetValue"` |
| `regex_search("GetValues", m, re)` | true | `"Get"` |
| `regex_match("GetValues", m, re)` | false | — |

这张表来自 [re.alg.match] 的例 1。

[re.alg.match] ¶1 迭代器必须满足 `bidirectional_iterator`。¶2 `regex_match` 判断正则表达式是否匹配整个 `[first, last)`，只考虑覆盖整个序列的匹配。所以第二行在 `Get` 失败后继续尝试 `GetValue`。

[re.alg.search] ¶2 `regex_search` 判断 `[first, last)` 中是否有某个子序列匹配。按 ECMAScript 语义，找到的是最左边的匹配；在这个位置上取第一个成功的分支，POSIX 文法则取最长的。

两个函数的 ¶3 都规定，无论成功与否，调用后 `m.ready()` 都为 true。失败时，`m` 除了 `size() == 0`、`empty() == true` 之外的状态都是未指明的。成功时：

- `regex_match`（表 123）：`m.size()` 是 `1 + e.mark_count()`，`m[0]` 是 `[first, last)`，`prefix()` 是空区间 `[first, first)`，`suffix()` 是 `[last, last)`；
- `regex_search`（表 124）：`prefix()` 是 `[first, m[0].first)`，`suffix()` 是 `[m[0].second, last)`。

其余重载（[re.alg.match] ¶4–¶8、[re.alg.search] ¶4–¶8）都转发到迭代器版本。不带 `match_results` 的版本在内部构造一个临时的 `match_results`，只返回 `bool`。

### regex_replace（[re.alg.replace]）

¶1 `regex_replace` 构造一个 `regex_iterator` 遍历所有匹配。对每个匹配，先输出它的前缀（设置了 `format_no_copy` 时不输出），再输出 `m.format(fmt, flags)`。最后输出最后一个匹配之后的剩余部分（同样受 `format_no_copy` 控制）。设置 `format_first_only` 时只替换第一个匹配。没有任何匹配时，整个输入原样复制到输出。¶3–¶6 是返回 `basic_string` 的重载。

### 只可能抛两种异常（[re.except]）

```cpp run title="regex-complexity.cpp" ok
#include <cassert>
#include <regex>
#include <string>

int main() {
  std::regex re("(a*)*c");          // 嵌套量词：灾难性回溯
  std::string s(26, 'a');
  try {
    std::regex_match(s + "b", re);
  } catch (const std::regex_error& e) {
    assert(e.code() == std::regex_constants::error_complexity ||
           e.code() == std::regex_constants::error_stack);
  }
}
```

¶1 本节的算法可以抛出 `regex_error`，但它的 `code()` 只能是 `error_complexity` 或 `error_stack`。也就是说，匹配过于复杂或栈空间不足，应以异常报告，而不是崩溃，前提是实现检测了这些情况。本机 libc++ 在上例中抛出 `error_complexity`；标准并不要求一定抛出，另一个实现可能只是运行很久。

## 迭代器（[re.iter]）

```cpp run title="regex-iterators.cpp" ok
#include <cassert>
#include <regex>
#include <string>
#include <vector>

int main() {
  std::string s = "a,b,,c";
  std::regex sep(",");
  std::vector<std::string> v(
      std::sregex_token_iterator(s.begin(), s.end(), sep, -1), {});
  assert((v == std::vector<std::string>{"a", "b", "", "c"}));  // -1：匹配之间的部分

  std::string t = "ab";
  std::regex empty("x*");
  int n = 0;
  for (std::sregex_iterator it(t.begin(), t.end(), empty), end; it != end; ++it)
    ++n;
  assert(n == 3);   // 位置 0、1、2 各有一个零长度匹配
}
```

### regex_iterator（[re.regiter]）

[re.regiter.general] ¶1 `regex_iterator` 是一个迭代器适配器，用 `regex_search` 依次找出序列中的所有匹配。每次 `++` 找下一个匹配并存入内部的 `match_results`，解引用得到 `const match_results&`。默认构造的是序列尾迭代器。两个非序列尾的迭代器由相同的实参构造时相等。

迭代器保存的是指向 regex 的指针（[re.regiter.cnstr] ¶2 把 `pregex` 设为 `addressof(re)`），所以 regex 必须比迭代器活得久。

¶2 如果 `match[0].matched` 为 true 且 `match[0].first == match[0].second`，迭代器持有的就是一个[[g:zero-length-match|零长度匹配]]。模式只由 `^`、`$`、`\b` 这类断言构成，或者 `x*` 在不含 `x` 的位置上匹配时，都会出现这种情况。

[re.regiter.incr] 规定的 `operator++` 保证每一步都有进展：

1. ¶1 从 `start = match[0].second` 继续。
2. ¶2 如果当前是零长度匹配，且 `start == end`，迭代器变为序列尾。
3. ¶3 如果当前是零长度匹配，先加上 `match_not_null | match_continuous` 在 `start` 处再试一次，即找一个从同一位置开始的非空匹配。失败时把 `start` 前进一位，再按下一步处理。
4. ¶4 普通情况下加上 `match_prev_avail` 再搜索。这样 `^` 不会误匹配上次匹配结束的位置，`\b` 也能看到前一个字符。

¶5–¶6 每次成功后，`match.prefix().first` 等于上一次的 `match[0].second`，`match.position(i)` 是相对于最初的 `begin` 的偏移，而不是相对于本次搜索的起点。¶7 实现怎样做到这一点是未指明的；注 2 说明实现可以调用自己的内部搜索函数，因此程序为 `regex_search` 提供的特化不一定会被调用。

### regex_token_iterator（[re.tokiter]）

`regex_token_iterator` 建立在 `regex_iterator` 之上，按给定的子匹配下标列表依次产出 `sub_match`。下标 `n >= 0` 取每个匹配的第 `n` 个子匹配；下标 -1 取匹配之间的部分，这就是用正则表达式分割字符串的标准写法。最后一个匹配之后如果还有剩余字符，-1 也会把它作为最后一个 token 产出。

## 悬垂：删除的重载与它们拦不住的情形

`match_results` 只保存迭代器，所以用临时 `std::string` 作为搜索目标、事后再读结果，就会悬垂（[[class.temporary]]）。[re.syn] 为此删除了两组重载：

- `regex_match`、`regex_search` 中以 `const basic_string&&` 为目标、带 `match_results&` 的版本；
- `regex_iterator`、`regex_token_iterator` 以 `const regex_type&&` 为参数的构造函数，因为迭代器保存的是 regex 的地址。

```cpp title="deleted-overloads.cpp" error
#include <regex>
#include <string>
std::string get() { return "key=value"; }
int main() {
  std::regex re("(\\w+)=(\\w+)");
  std::smatch m;
  std::regex_search(get(), m, re);   // error: 调用被删除的函数
  std::string s = get();
  std::sregex_iterator it(s.begin(), s.end(),
                          std::regex("x"));   // error: 调用被删除的构造函数
}
```

不带 `match_results` 的 `regex_search(get(), re)` 仍然合法，它只返回 `bool`，不会悬垂。但删除的重载只认 `basic_string` 右值，拦不住经由指针的情形：

```cpp run title="dangling-cmatch.cpp" ub
#include <iostream>
#include <regex>
#include <string>

std::string load() {
  return "user=alice; a long enough line to defeat SSO";
}

int main() {
  std::regex re(R"((\w+)=(\w+))");
  std::cmatch m;
  std::regex_search(load().c_str(), m, re);  // const char* 重载没有被删除
  // 完整表达式结束，临时 string 已销毁
  std::cout << m[2] << '\n';                 // UB: m 中的指针悬空
}
```

本机用 `-fsanitize=address` 运行，报告 heap-use-after-free。同样，`std::string_view` 指向的字符串被销毁，或者 `std::string` 在匹配之后被修改（可能重新分配内存），都会让已有的 `match_results` 失效。

## 思考题

!!! question "思考题 1"
    对刚默认构造的 `std::smatch m;`，`m.size()`、`m.empty()`、`m[0]` 分别是否合法？匹配失败之后呢？

<details markdown="1">
<summary>答案</summary>

`m.size()`（返回 0）和 `m.empty()`（返回 true）合法，它们没有 `ready()` 前置条件（[re.results.size]、[re.results.const] ¶3）。`m[0]` 是 UB：[re.results.acc] ¶7 要求 `ready() == true`，而默认构造的对象不是 ready 的（[re.results.general] ¶3）。

匹配失败之后，`m` 是 ready 的（[re.alg.match] ¶3），`size()` 为 0。这时 `m[0]` 满足 `0 >= size()`，按 [re.results.acc] ¶8 返回一个未匹配的 `sub_match`，是合法的。
</details>

!!! question "思考题 2"
    用 `sregex_iterator` 遍历时，`it->position(0)` 是相对于什么的偏移？

<details markdown="1">
<summary>答案</summary>

相对于构造迭代器时传入的 `begin`，而不是本次 `regex_search` 的起点（[re.regiter.incr] ¶5–¶6）。实现必须调整 `match_results`，使 `position` 反映在整个目标序列中的位置，`prefix().first` 也必须等于上一次匹配的 `match[0].second`。
</details>

## 小结

| 要点 | 出处 |
|---|---|
| `sub_match` 是一对迭代器加 `matched`，不拥有字符 | [re.submatch.general] |
| 在非 ready 的 `match_results` 上调用多数成员是 UB | [re.results.general] ¶3 |
| 未参与匹配的子表达式：`matched` 为 false，迭代器指向序列末尾 | [re.results.general] ¶4 |
| 越界的 `operator[]` 返回未匹配的 `sub_match` | [re.results.acc] ¶8 |
| 算法只抛 `error_complexity` 或 `error_stack` | [re.except] ¶1 |
| `regex_match` 要求覆盖整个序列；`regex_search` 找最左的匹配 | [re.alg.match] ¶2、[re.alg.search] ¶2 |
| 零长度匹配时先尝试同一位置的非空匹配，再前进一位 | [re.regiter.incr] ¶3 |
| 删除了右值 `basic_string` 和右值 regex 的重载，但拦不住 `c_str()` 悬垂 | [re.syn] |
