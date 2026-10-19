---
title: 正则表达式库
summary: <regex> 的模式一侧：basic_regex 在运行期把模式编译成状态机，六种文法（默认是修改过的 ECMAScript），两组位掩码选项，regex_error 的错误码，regex_traits 如何接入 locale；匹配按 code unit 进行，没有 Unicode 语义。
status: draft
covers: re.general, re.req, re.syn, re.const, re.const.general, re.synopt, re.matchflag, re.err, re.badexp, re.traits, re.regex, re.regex.general, re.regex.construct, re.regex.assign, re.regex.operations, re.regex.locale, re.regex.swap, re.regex.nonmemb, re.grammar
since: c++11
related: re.alg, localization, locale.categories, text, bitmask.types, enumerated.types
tags: 标准库, 正则表达式, regex, locale
updated: 2026-10-19
---

!!! tldr
    - 构造 `std::regex` 就是在运行期编译模式，开销很大；应构造一次、反复使用。非法模式抛出 `regex_error`。
    - 默认文法是 ECMAScript，取第一个成功的分支；POSIX 文法取最左最长的匹配。同一个模式在两种文法下可以匹配到不同的文本。
    - 所有与 locale 有关的判断都经过 traits 对象，它在 regex 构造时记下当时的全局 locale。
    - 匹配按 code unit 进行：对 UTF-8 字符串，`.` 匹配一个字节，没有任何 Unicode 语义。
    - 主流实现都用回溯算法，速度慢，嵌套量词可能导致指数级回溯。

`<regex>` 是 C++11 在 Boost.Regex 基础上标准化的正则表达式库。本页讲模式一侧：库的组成、选项常量、错误、traits、`basic_regex` 和文法。匹配一侧，即 `sub_match`、`match_results`、`regex_match`、`regex_search`、`regex_replace` 和两种迭代器，见 [[re.alg]]。

## 一个例子

```cpp run title="regex-basics.cpp" ok
#include <cassert>
#include <regex>

int main() {
  std::cmatch m;
  std::regex ecma("Get|GetValue");                         // 默认 ECMAScript
  std::regex posix("Get|GetValue", std::regex::extended);  // POSIX ERE
  assert(std::regex_search("GetValue", m, ecma) && m[0] == "Get");
  assert(std::regex_search("GetValue", m, posix) && m[0] == "GetValue");

  // 只认 code unit：UTF-8 的 "中" 是 3 个 char
  assert(!std::regex_match("中", std::regex(".")));
  assert( std::regex_match("中", std::regex("...")));

  std::regex r("a+", std::regex::icase | std::regex::nosubs);
  assert(r.mark_count() == 0 && std::regex_match("AaA", r));

  std::regex ml("^b", std::regex::ECMAScript | std::regex::multiline);
  assert(std::regex_search("a\nb", ml));                  // ^ 匹配行首
  assert(!std::regex_search("a\nb", std::regex("^b")));   // ^ 只匹配开头

  try { std::regex bad("(ab"); assert(false); }
  catch (const std::regex_error& e) {
    assert(e.code() == std::regex_constants::error_paren);
  }
}
```

这段代码依次展示了本页的几个要点：两种文法对选择分支的不同语义、按 code unit 匹配、选项位掩码，以及非法模式抛出的异常。

## 组成（[re.general]、[re.syn]）

¶2 本节描述一个正则表达式类模板 `basic_regex` 及其 traits、保存匹配结果的 `match_results`、一组算法和两种迭代器。¶3 规定，ECMAScript 语言规范 Ecma-262 在本节中简称 ECMA-262。

`basic_regex` 可以用任何类字符类型实例化，但标准只要求 `regex_traits` 对 `char` 和 `wchar_t` 可用，所以只提供 `regex`、`wregex` 两个别名，以及对应的 `cmatch`、`smatch`、`wcmatch`、`wsmatch` 等。`char8_t`、`char16_t`、`char32_t` 都没有支持。

[re.syn] 的概要里有一组删除的重载：`regex_match`、`regex_search` 接受右值 `basic_string` 加 `match_results&` 的版本，以及 `regex_iterator`、`regex_token_iterator` 接受右值 regex 的构造函数，都是 `= delete`。它们在编译期拦截结果引用临时对象的情况，详见 [[re.alg]]。

## 选项常量（[re.const]）

`std::regex_constants` 命名空间提供三种类型：构造时用的 `syntax_option_type`，匹配时用的 `match_flag_type`，以及错误码 `error_type`。

### syntax_option_type（[re.synopt]）

这是一个由实现定义的位掩码类型（[[bitmask.types]]），`basic_regex` 也把这些值作为静态成员提供，如 `std::regex::icase`。

¶1 一个合法的值至多设置 `ECMAScript`、`basic`、`extended`、`awk`、`grep`、`egrep` 中的一个文法；都不设置时，文法是 ECMAScript。表 118 列出全部元素：

| 元素 | 效果 |
|---|---|
| `icase` | 忽略大小写 |
| `nosubs` | 不把任何子表达式视为标记的（marked），`match_results` 不保存子匹配 |
| `optimize` | 让引擎更重视匹配速度而不是构造速度，此外没有可观察的效果 |
| `collate` | `[a-b]` 形式的区间按 locale 的排序规则解释 |
| `ECMAScript` | ECMA-262 文法，按 [re.grammar] 修改 |
| `basic`、`extended` | POSIX 基本、扩展正则表达式 |
| `awk`、`grep`、`egrep` | POSIX awk、grep、grep -E 的文法 |
| `multiline` | 只对 ECMAScript：`^`、`$` 也匹配行首、行尾（C++17 起） |

`optimize` 只是提示。在本机 libc++ 的 `<regex>` 中，这个标志除了被定义之外没有在任何地方使用。

ECMAScript 采用回溯语义，选择第一个成功的分支（leftmost-first）；POSIX 文法要求最左最长（leftmost-longest）。所以开头的例子里，`Get|GetValue` 在 `"GetValue"` 上，ECMAScript 匹配到 `"Get"`，`extended` 匹配到 `"GetValue"`。

### match_flag_type（[re.matchflag]）

同样是由实现定义的位掩码类型，传给匹配算法。¶1 规定 `match_default` 和 `format_default` 是空位掩码。表 119 中较常用的有：

- `match_not_bol`、`match_not_eol`：把 `[first, last)` 的开头、结尾视为不在行首、行尾，在子串里搜索时需要；
- `match_not_null` 不接受空匹配；`match_continuous` 只接受从 `first` 开始的匹配；
- `match_prev_avail`：`--first` 是有效位置，于是 `^`、`\b` 能看到前一个字符。`regex_iterator` 在后续搜索中会自动加上它；
- `format_sed`、`format_no_copy`、`format_first_only`：控制 `regex_replace` 和 `match_results::format`。默认的替换规则来自 ECMAScript 的 `String.prototype.replace`：`$&`、`$1`、`` $` ``、`$'`、`$$`。

### error_type 与 regex_error（[re.err]、[re.badexp]）

`error_type` 是由实现定义的枚举类型（[[enumerated.types]]），表 120 列出 13 个值：`error_collate`、`error_ctype`、`error_escape`、`error_backref`、`error_brack`、`error_paren`、`error_brace`、`error_badbrace`、`error_range`、`error_space`、`error_badrepeat`、`error_complexity`、`error_stack`。

`regex_error` 派生自 `runtime_error`，`code()` 返回构造时传入的错误码（[re.badexp]）。

## basic_regex（[re.regex]）

### 构造就是编译（[re.regex.general]）

¶1–¶2 `basic_regex` 对象负责把字符序列转换成某种内部表示。这个表示是什么、匹配算法怎样访问它，标准都不规定；注 1 提到实现通常把算法声明为友元。¶3 本节的函数通过抛出 `regex_error` 报告错误。

所以 `std::regex re(pattern);` 是一次运行期编译：解析模式，构造有限状态机。在每次调用时都构造 regex 的代码里，这是主要的开销来源。应当构造一次、反复使用，例如写成 `static const std::regex`。

### 构造与赋值（[re.regex.construct]、[re.regex.assign]）

- 默认构造的对象不匹配任何字符序列。
- 可以从 `const charT*`、指针加长度、`basic_string`、迭代器区间或 `initializer_list` 构造。构造之后 `flags()` 返回传入的选项，`mark_count()` 返回标记子表达式的个数；模式不合法时抛出 `regex_error`。选项的默认值都是 `ECMAScript`。
- [re.regex.assign] ¶10–¶13：`assign` 编译新模式。¶11 的后置条件只在没有抛出异常时成立，异常时 `*this` 保持不变，即强异常保证。

`mark_count()`、`flags()` 见 [re.regex.operations]；`swap` 是常数时间操作。

## traits：locale 的唯一入口（[re.req]、[re.traits]）

[re.grammar] ¶2 规定，`basic_regex` 在内部保存一个默认构造的 traits 对象，标准称它为 `traits_inst`。`basic_regex` 的成员不得调用任何依赖 locale 的 C 或 C++ API，所有这类判断都要通过 `traits_inst` 的成员完成。[re.req] 规定了 traits 类 `X` 必须提供的操作：

| 表达式 | 作用 | 段落 |
|---|---|---|
| `X::length(p)` | 空终止串的长度 | ¶10–¶12 |
| `v.translate(c)`、`v.translate_nocase(c)` | 把等价的字符映射到同一个代表字符 | ¶13–¶16 |
| `v.transform(F1, F2)`、`v.transform_primary(F1, F2)` | 生成排序键，用于 `collate` 模式的区间和等价类 `[[=a=]]` | ¶17–¶20 |
| `v.lookup_collatename(F1, F2)` | 解析排序元素 `[[.ch.]]` | ¶21–¶22 |
| `v.lookup_classname(F1, F2, icase)`、`v.isctype(c, cl)` | 字符类 `[[:alpha:]]`、`\d`、`\w` | ¶23–¶26 |
| `v.value(c, I)` | 数字字符在 8、10、16 进制下的值 | ¶27–¶28 |
| `u.imbue(loc)`、`v.getloc()` | 设置、获取 locale | ¶29–¶32 |

标准提供的 `regex_traits<charT>` 用 locale 的 facet 实现这些操作：`translate` 原样返回（[re.traits] ¶4），`translate_nocase` 用 `ctype::tolower`（¶5），`transform` 用 `collate::transform`（¶6），`isctype` 把类名映射到 `ctype_base::mask` 再查询 `ctype`（¶11–¶12）。¶10 和表 121 列出至少要识别的类名：`alnum`、`alpha`、`blank`、`cntrl`、`digit`、`d`、`graph`、`lower`、`print`、`punct`、`space`、`s`、`upper`、`w`、`xdigit`。

[re.traits] ¶17–¶18 规定，如果从未调用 `imbue`，`getloc()` 返回 traits 对象构造时生效的全局 locale 的副本。因此一个 `std::regex` 的字符分类和大小写规则在构造时就定下了，之后调用 `std::locale::global` 不影响已经构造的 regex。

要更换 locale，需要调用 `basic_regex::imbue`。按 [re.regex.locale] ¶1，调用之后这个 regex 不匹配任何字符序列，必须重新 `assign` 模式。

## 文法（[re.grammar]）

¶1 用 `ECMAScript` 构造的 regex，文法就是 ECMA-262 的文法，但有以下修改：

- ¶3–¶5：字符类中增加 POSIX 风格的 `[[:class:]]`、`[[.collating.]]`、`[[=equiv=]]`。
- ¶7–¶11：类名通过 `lookup_classname` 解析，至少要识别上面列出的 15 个；`\d`、`\s`、`\w` 分别等价于 `[[:digit:]]`、`[[:space:]]`、`[_[:alnum:]]`。无效的类名使编译抛出 `regex_error`。
- ¶12：`\uXXXX` 的值超出 `charT` 能表示的范围时抛出 `regex_error`。对 `char` 来说，模式 `中` 不合法。本机 libc++ 用这个模式构造 `std::regex` 并不抛出，与条文不符。
- ¶14：匹配语义按 ECMA-262，再由匹配标志和 traits 修饰。比较两个字符时，`icase` 下比较 `translate_nocase` 的结果，`collate` 下比较 `translate` 的结果，否则直接用 `==`（¶14.1）。`collate` 模式下，区间 `c1-c2` 用 `transform` 得到的排序键比较（¶14.2）。

¶14 也说明了本页开头的 code unit 问题。整个库没有 Unicode 的概念：比较的是一个个 `charT`。对 UTF-8 编码的 `std::string`，`.` 匹配一个字节，`\w` 对每个字节调用 `ctype<char>` 分类，`[à-ü]` 是字节区间。处理非 ASCII 文本时，要么接受按字节的语义，要么改用支持 Unicode 的正则引擎。

## 性能

!!! impl "为什么 std::regex 慢"
    标准没有规定复杂度，但它的规格让高性能实现很难做：ECMAScript 语义（包括反向引用）需要回溯；字符判断要经过 traits 和 locale；`basic_regex` 是模板，内部表示随类型进入 ABI，实现很难在不破坏 ABI 的前提下重写。libc++ 和 libstdc++ 都采用回溯实现，嵌套量词如 `(a*)*c` 会出现指数级回溯。本机 libc++ 在超过内部阈值后抛出 `error_complexity`，这是 [re.except] 允许匹配算法抛出的两种错误之一（见 [[re.alg]]）。

    需要处理不可信输入或追求性能时，可以考虑 RE2、PCRE2、Hyperscan 或编译期正则库。

## 小结

| 要点 | 出处 |
|---|---|
| 默认文法是 ECMAScript；六种文法互斥 | [re.synopt] ¶1 |
| `optimize` 只是提示 | 表 118 |
| 构造就是编译；非法模式抛 `regex_error` | [re.regex.general] ¶3 |
| traits 是 locale 的唯一入口，记下构造时的全局 locale | [re.grammar] ¶2、[re.traits] ¶17 |
| 按 `charT`（code unit）匹配，没有 Unicode 语义 | [re.grammar] ¶12、¶14 |
