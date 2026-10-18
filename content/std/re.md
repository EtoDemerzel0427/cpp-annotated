---
title: 正则表达式库
summary: <regex> 的总体设计——basic_regex 把模式编译为内部有限状态机、六种文法（默认是修改过的 ECMAScript）、syntax_option_type 与 match_flag_type 两组位掩码、regex_error 的错误码、regex_traits 如何把 locale 接入匹配过程；按 code unit 而非 Unicode 字符匹配；以及这个库为什么在实践中以“慢”闻名
status: draft
covers: re.general, re.req, re.syn, re.const, re.const.general, re.synopt, re.matchflag, re.err, re.badexp, re.traits, re.regex, re.regex.general, re.regex.construct, re.regex.assign, re.regex.operations, re.regex.locale, re.regex.swap, re.regex.nonmemb, re.grammar
since: c++11
related: re.alg, localization, locale.categories, text, bitmask.types, enumerated.types
tags: 标准库, 正则表达式, regex, locale
updated: 2026-10-18
---

`<regex>` 是 C++11 从 Boost.Regex 演化来的正则表达式库。它的接口设计相当完整：可插拔的字符特征（`regex_traits`）、六种文法、可定制的分配器、迭代器式的全局搜索。但它也是标准库里口碑最差的组件之一——主流实现的匹配速度通常比专门的正则引擎慢一到两个数量级，构造 `std::regex` 本身也很昂贵，而 ABI 稳定性要求使实现几乎无法重写。

本页讲“模式”一侧：库的组成、常量、错误、traits、`basic_regex` 和文法；“匹配”一侧——`sub_match`、`match_results`、`regex_match`/`regex_search`/`regex_replace` 和两个迭代器——见 [[re.alg]]。

## 组成（[re.general]、[re.syn]）

¶2 与表 117 列出组成部分：traits 要求（[re.req]）、常量（[re.const]）、异常类型（[re.badexp]）、traits 类模板（[re.traits]）、`basic_regex`（[re.regex]）、子匹配与匹配结果（[re.submatch]、[re.results]）、算法（[re.alg]）、迭代器（[re.iter]）、文法（[re.grammar]）。¶3：ECMAScript 语言规范 Standard Ecma-262 在本节简称 *ECMA-262*。

`basic_regex` 可以用任何 char-like 类型实例化，但标准只提供 `regex`（`char`）和 `wregex`（`wchar_t`）两个别名，以及对应的 `cmatch`/`smatch`/`wcmatch`/`wsmatch`、迭代器别名和 `pmr::` 版本的 `match_results`。**没有** `char8_t`/`char16_t`/`char32_t` 的支持——`regex_traits` 只要求对 `char` 和 `wchar_t` 可用。

[re.syn] 的概要中有一组值得注意的**被删除的重载**：`regex_match`/`regex_search` 接受 `const basic_string&&` 加 `match_results&` 的版本、`regex_iterator`/`regex_token_iterator` 接受 `const regex_type&&` 的构造函数都是 `= delete`。它们用于在编译期拦截“结果引用了临时对象”的悬垂，详见 [[re.alg]]。

## traits 要求与 `regex_traits`（[re.req]、[re.traits]）

`basic_regex<charT, traits>` 不直接调用任何依赖 locale 的 API，而是通过 traits 完成所有与字符相关的判断。[re.req] 规定 traits 类 `X` 必须提供：

| 表达式 | 作用 |
|---|---|
| `X::length(p)` | 空终止串长度（¶10–¶12） |
| `v.translate(c)` / `v.translate_nocase(c)` | 把“等价”的字符映射到同一个代表元（¶13–¶16） |
| `v.transform(F1, F2)` / `v.transform_primary(F1, F2)` | 生成排序键，用于 `collate` 模式下的区间 `[a-z]` 和等价类 `[[=a=]]`（¶17–¶20） |
| `v.lookup_collatename(F1, F2)` | 处理 `[[.ch.]]` 排序元素（¶21–¶22） |
| `v.lookup_classname(F1, F2, icase)` / `v.isctype(c, cl)` | 字符类 `[[:alpha:]]`、`\d`、`\w`（¶23–¶26） |
| `v.value(c, I)` | 数字字符在 8/10/16 进制下的值（¶27–¶28） |
| `u.imbue(loc)` / `v.getloc()` | 设置/获取 locale（¶29–¶32） |

标准的 `regex_traits<charT>`（[re.traits]）用 locale 的 facet 实现这些操作：`translate` 原样返回（¶4）；`translate_nocase` 用 `ctype::tolower`（¶5）；`transform` 用 `collate::transform`（¶6）；`isctype` 把类名映射为 `ctype_base::mask` 查询 `ctype`（¶11–¶12，表 121 列出至少要识别的类名：`alnum`、`alpha`、`blank`、`cntrl`、`digit`/`d`、`graph`、`lower`、`print`、`punct`、`space`/`s`、`upper`、`w`、`xdigit`）。

!!! note "regex 捕获的是**构造时**的全局 locale"
    [re.traits]/17–18：若从未 imbue，`getloc()` 返回的是 `*this` **构造时**生效的全局 locale 的副本。`basic_regex` 内部存放一个默认构造的 traits 对象（[re.grammar]/2 称之为 `traits_inst`），因此一个 `std::regex` 的字符分类、大小写折叠规则在构造时就定下了；之后调用 `std::locale::global` 不会影响已构造的 regex。要换 locale，需调用 `basic_regex::imbue`（[re.regex.locale]），而这会让正则表达式变为“不匹配任何内容”的状态，必须重新 `assign`。

## 常量（[re.const]）

`std::regex_constants` 命名空间提供三种类型：

### `syntax_option_type`（[re.synopt]）

由实现定义的位掩码类型（[[bitmask.types]]）。¶1：一个合法值**至多**设置 `ECMAScript`、`basic`、`extended`、`awk`、`grep`、`egrep` 中的一个文法元素；都不设置时默认 ECMAScript。表 118：

| 元素 | 效果 |
|---|---|
| `icase` | 忽略大小写 |
| `nosubs` | 不把任何子表达式视为“标记的”（*marked*），`match_results` 中不存储子匹配 |
| `optimize` | 让引擎更重视匹配速度而非构造速度；除此之外**没有可观察效果** |
| `collate` | `[a-b]` 形式的区间按 locale 排序规则解释 |
| `ECMAScript` | ECMA-262 文法，按 [re.grammar] 修改 |
| `basic` / `extended` | POSIX 基本/扩展正则表达式 |
| `awk` / `grep` / `egrep` | POSIX awk、grep、grep -E 的文法 |
| `multiline` | 仅对 ECMAScript：`^`/`$` 匹配行首/行尾（C++17 起） |

`optimize` 只是提示——在 libc++ 的 `<regex>` 中，这个标志除了被定义之外没有任何地方使用。

!!! pitfall "ECMAScript 与 POSIX 的“哪个匹配”不同"
    ECMAScript 是回溯式语义：选择**第一个**成功的分支（leftmost-first）；POSIX 文法要求**最左最长**（leftmost-longest）。同样的模式 `Get|GetValue` 在 `"GetValue"` 上搜索，ECMAScript 得到 `"Get"`，`extended` 得到 `"GetValue"`（见下文示例）。

### `match_flag_type`（[re.matchflag]）

同样是由实现定义的位掩码类型。¶1：`match_default` 和 `format_default` 是空位掩码。表 119 中较常用的：

- `match_not_bol`/`match_not_eol`：把 `[first, last)` 的首/尾视为不在行首/行尾——对子串搜索很重要；
- `match_not_null`：不接受空匹配；`match_continuous`：只接受从 `first` 开始的匹配；
- `match_prev_avail`：`--first` 是有效位置（于是 `^`、`\b` 可以看到前一个字符）；`regex_iterator` 在后续搜索中自动加上它；
- `format_sed`、`format_no_copy`、`format_first_only`：控制 `regex_replace` 和 `match_results::format`。默认的替换规则是 ECMAScript `String.prototype.replace` 的规则（`$&`、`$1`、`` $` ``、`$'`、`$$`）。

### `error_type` 与 `regex_error`（[re.err]、[re.badexp]）

`error_type` 是由实现定义的枚举类型（[[enumerated.types]]），表 120 列出 13 个错误：`error_collate`、`error_ctype`、`error_escape`、`error_backref`、`error_brack`、`error_paren`、`error_brace`、`error_badbrace`、`error_range`、`error_space`、`error_badrepeat`、`error_complexity`、`error_stack`。

`regex_error` 派生自 `runtime_error`，`code()` 返回构造时传入的错误码（[re.badexp]/2–3）。

## `basic_regex`（[re.regex]）

### 编译模型（[re.regex.general]）

¶1：`basic_regex` 表示由 `charT` 序列构造的正则表达式，存储按需分配与释放。¶2：对象负责把字符序列转换为**内部表示**；这个表示是什么、算法如何访问它，都不作规定（注 1：实现通常把算法声明为友元）。¶3：本节函数通过抛出 `regex_error` 报告错误。

也就是说，`std::regex re(pattern);` 是一次**运行期编译**：解析模式、构造有限状态机。这在每次调用都构造 regex 的代码里是主要开销来源——应当把 regex 构造一次、反复使用（例如 `static const std::regex`）。

### 构造与赋值（[re.regex.construct]、[re.regex.assign]）

- 默认构造（¶1）：不匹配任何字符序列。
- 从 `const charT*`、`(p, len)`、`basic_string`、迭代器区间或 `initializer_list` 构造（¶2–¶18）：编译模式；*Postconditions*：`flags()` 返回 `f`，`mark_count()` 返回标记子表达式的个数；模式不合法时抛 `regex_error`。所有构造函数的默认 `f` 都是 `ECMAScript`。
- `assign` 系列（[re.regex.assign]/10–13）：赋值新模式；¶10 明确规定**若抛出异常，`*this` 不变**（强异常保证），¶11 的后置条件只在无异常时成立。

### 其余成员

- `mark_count()`（[re.regex.operations]/1）：标记子表达式数；`flags()`（¶2）。
- `imbue(loc)`（[re.regex.locale]/1）：调用 `traits_inst.imbue(loc)`，之后正则不匹配任何内容；`getloc()`（¶2）。
- `swap`（[re.regex.swap]）常数时间；非成员 `swap`（[re.regex.nonmemb]）。

## 文法（[re.grammar]）

¶1：以 `ECMAScript` 构造时，文法就是 ECMA-262 规定的文法，但有以下修改：

- ¶3–¶5：字符类中增加 POSIX 风格的 `[[:class:]]`、`[[.collating.]]`、`[[=equiv=]]`。
- ¶2：**`basic_regex` 的成员不得调用任何依赖 locale 的 C 或 C++ API**，而是调用 `traits_inst` 的相应成员——这保证了 traits 是唯一的 locale 接入点。
- ¶7–¶11：`ClassName` 通过 `lookup_classname` 解析，无效类名抛 `regex_error`。
- ¶12：`\uXXXX` 的值超出 `charT` 能表示的范围时抛 `regex_error`——对 `char` 而言，模式 `\u4E2D` 就是非法的。不过本机实测 libc++ 23 用这个模式构造 `std::regex` 并不抛出，与该条款不符。
- ¶14：匹配语义按 ECMA-262，并受 `match_flag_type` 和 traits 修饰：两个字符比较时，`icase` 下比较 `translate_nocase`，`collate` 下比较 `translate`，否则直接 `==`（¶14.1）；`collate` 模式的区间 `c1-c2` 用 `transform` 后的排序键比较（¶14.2）；字符类成员关系用 `isctype(c, lookup_classname(...))` 判断（¶14.4）。

!!! warning "regex 匹配的是 code unit，不是字符"
    整个库没有任何 Unicode 概念。对 UTF-8 编码的 `std::string`，`.` 匹配一个**字节**，`\w` 对每个字节调用 `ctype<char>` 分类，`[à-ü]` 是字节区间。处理非 ASCII 文本时，要么接受“按字节”的语义，要么改用专门的 Unicode 正则引擎。

## 示例

```cpp run title="regex-basics.cpp" ok
#include <cassert>
#include <regex>
#include <string>

int main() {
    std::cmatch m;
    std::regex ecma("Get|GetValue");                                   // 默认 ECMAScript
    std::regex posix("Get|GetValue", std::regex::extended);            // POSIX ERE
    assert(std::regex_search("GetValue", m, ecma)  && m[0] == "Get");      // 第一个成功的分支
    assert(std::regex_search("GetValue", m, posix) && m[0] == "GetValue"); // 最左最长

    // 只认 code unit：UTF-8 的 "中" 是 3 个 char
    assert(!std::regex_match("中", std::regex(".")));
    assert( std::regex_match("中", std::regex("...")));

    std::regex r("a+", std::regex::icase | std::regex::nosubs);
    assert(r.mark_count() == 0 && std::regex_match("AaA", r));

    std::regex ml("^b", std::regex::ECMAScript | std::regex::multiline);
    assert(std::regex_search("a\nb", ml));                    // multiline：^ 匹配行首
    assert(!std::regex_search("a\nb", std::regex("^b")));     // 默认：^ 只匹配目标序列开头

    try { std::regex bad("(ab"); assert(false); }
    catch (const std::regex_error& e) { assert(e.code() == std::regex_constants::error_paren); }
}
```

## 性能与实现现状

!!! impl "为什么 std::regex 慢"
    标准并不规定算法复杂度，但它的规范选择使高性能实现很困难：ECMAScript 语义（含反向引用）天然需要回溯；traits 接口要求逐字符经过虚函数式的 locale 调用；`basic_regex` 是模板，内部表示随类型一起进入 ABI。libc++ 和 libstdc++ 都采用回溯式实现，对嵌套量词（如 `(a*)*c`）会出现指数级回溯——libc++ 在超过内部阈值后抛出 `error_complexity`（这是 [re.except] 允许的两种错误之一，见 [[re.alg]]）。需要处理不可信输入或追求性能时，应考虑 RE2、PCRE2、Hyperscan 或编译期正则库。

## 小结

| 要点 | 出处 |
|---|---|
| 默认文法 ECMAScript；六种文法互斥 | [re.synopt]/1 |
| `optimize` 只是提示 | 表 118 |
| 构造即编译；非法模式抛 `regex_error` | [re.regex.general]/3、[re.regex.construct] |
| traits 是 locale 的唯一接入点；捕获构造时的全局 locale | [re.grammar]/2、[re.traits]/17 |
| 按 `charT`（code unit）匹配，无 Unicode 语义 | [re.grammar]/12、/14 |
