---
title: 标准 locale 类别与 facet
summary: 六大类别的标准 facet 一览——ctype（字符分类、widen/narrow、ctype<char> 的查表特化）、codecvt（编码转换与 basic_filebuf 的逐字符要求）、num_get/num_put（以 printf/strtol 为蓝本的“三阶段”算法、分组检查、溢出时的饱和值）、numpunct、collate、time_get/time_put、money_get/money_put/moneypunct、messages；公共的 NVI 设计与 put/get 的错误报告约定
status: draft
covers: *
related: localization, text, c.locales, istream.formatted.arithmetic, ostream.inserters.arithmetic, file.streams, depr.locale.category, format.string.std, charconv
tags: 标准库, locale, facet, iostream, 数值解析
updated: 2026-10-18
---

[locale.categories] 是第 28 章篇幅最大的部分（三千行原文的大半），但它的结构高度重复：每个 facet 都是“公开非虚成员 `f()` 只做转发 → 受保护的虚函数 `do_f()` 规定语义”，然后再配一个 `_byname` 派生类按 locale 名字实现。理解了这个骨架，再挑出几处真正有分量的规则即可。本页按类别分组讲解，覆盖 [locale.categories] 下的全部子条款。前置知识见 [[localization]]。

## 公共约定（[locale.categories.general]）

¶1：负责格式化/解析的 facet 提供 `put()`/`get()` 成员，供 iostream 的 `<<`/`>>` 使用。它们都接受一个 `ios_base&`，从中读取 `flags()`、`precision()`、`width()`；需要其他 facet 时，调用它的 `getloc()`。格式化 facet 用 `fill` 实参补足宽度。

¶2：`put()` **不报告错误**（输出迭代器的失败可以从返回的迭代器上看出，如 `ostreambuf_iterator::failed()`）；`get()` 接受一个 `ios_base::iostate&`，**忽略它的原值**，解析出错时设置 `failbit`。

¶3：本节中一个虚函数是否调用另一个虚函数是未指明的（{{unspec}}）。这对定制者意义重大：覆盖 `do_get(…, long&)` 不能指望 `do_get(…, int&)` 会转去调用它。

### NVI 骨架

```cpp
template<class charT>
class numpunct : public locale::facet {
public:
  charT decimal_point() const;            // 只做 return do_decimal_point();
  static locale::id id;
protected:
  ~numpunct();                            // 受保护：只能经由 locale 销毁
  virtual charT do_decimal_point() const; // 真正的语义
};
```

所有标准 facet 的析构函数都是 `protected` 的，因此不能在栈上直接创建 `std::numpunct<char> np;`——只能 `new` 出来交给 locale（或派生一个公开析构的类）。

## ctype 类别（[category.ctype]）

### `ctype_base` 与 `ctype<charT>`（[category.ctype.general]、[locale.ctype]）

`ctype_base::mask` 是位掩码类型（[[bitmask.types]]），元素为 `space`、`print`、`cntrl`、`upper`、`lower`、`alpha`、`digit`、`punct`、`xdigit`、`blank`，以及组合 `alnum = alpha | digit`、`graph = alnum | punct`（数值仅供说明）。

`ctype<charT>` 封装 `<cctype>` 的功能（[locale.ctype.general]/1），**istream 在解析输入时必须用它来分类字符**。成员：

- `is(m, c)` / `is(low, high, vec)`：分类；`scan_is`/`scan_not`：找第一个符合/不符合 `m` 的字符（[locale.ctype.virtuals]/1–6）。
- `toupper`/`tolower`：一对一映射，不存在对应字符时原样返回（¶7–¶10）。
- `widen(c)`：把 `char` 做“最简单合理的变换”变成 `charT`（¶11）。只有基本字符集（[[lex.charset]]）中的字符要求有唯一变换；且 widen 不得给字符**增加**分类：`ctc.is(M, c) || !is(M, do_widen(c))`。
- `narrow(c, dfault)`：反向变换，无法变换时返回 `dfault`（¶13–¶14）。对基本字符集中的字符 `c`，`do_widen(do_narrow(c, 0)) == c`；对任意数字字符，`do_narrow(c, dfault) - '0'` 就是它的数值——这一条保证 `num_get` 能把宽字符数字还原。

脚注说明 `do_widen` 的参数是为接收**字符字面量**的值而设计的：`widen('0')` 把字面量编码中的 `'0'` 转为 locale 编码中的对应字符。这正是 [[text]] 所说“字面量编码 vs 执行编码”在 C++ 层面的接缝。

### `ctype<char>` 特化（[facet.ctype.special]）

¶1：标准专门规定了 `ctype<char>` 的显式特化，以便对 `char` 的成员函数可以**内联查表**实现；脚注解释，之所以写进标准而非留作实现细节，是因为它影响派生接口。它没有 `do_is`/`do_scan_is` 虚函数——分类完全由一张 `mask` 表决定：

- 构造函数 `ctype(const mask* tab = nullptr, bool del = false, size_t refs = 0)`：`tab` 为空则用 `classic_table()`；`del` 为真时析构函数 `delete[] table()`（[facet.ctype.char.dtor]）。
- `is(m, c)` 返回 `table()[(unsigned char)c] & m`（[facet.ctype.char.members]/5）。注意转换为 `unsigned char`——与 `<cctype>` 的 `isalpha(int)` 不同，这里负值 `char` 不是 UB。
- `table_size` 由实现定义，至少 256；对 `v >= table_size` 的值，`table()[v]` 视为某个实现特定的值而不真正访问数组（¶1）。
- `classic_table()` 返回 `"C"` locale 的分类表（[facet.ctype.char.statics]）。

想自定义“哪些字符算空白”（例如让 `>>` 以逗号分隔），标准做法就是派生 `ctype<char>`，复制 `classic_table()` 并修改，再把新表传给基类构造函数。

### `codecvt`（[locale.codecvt]）

`codecvt<internT, externT, stateT>` 在两种编码之间转换（[locale.codecvt.general]/1），`stateT` 选择是哪一对编码（¶2）。表 91 只要求两个特化（¶3）：

- `codecvt<char, char, mbstate_t>`：**退化**的转换，什么也不做；
- `codecvt<wchar_t, char, mbstate_t>`：在实现的本地窄字符集与宽字符集之间转换。

`char16_t`/`char32_t` 与 `char`/`char8_t` 之间的特化已移入附录 [[depr.locale.category]]（{{deprecated}}）；C++26 更彻底删除了 `<codecvt>` 头文件中的 `codecvt_utf8` 等（见 [[text]]）。

核心是 `do_in`/`do_out`（[locale.codecvt.virtuals]）：

- ¶1 *Preconditions*：`from <= from_end && to <= to_end` 良定义且为真；`state` 在序列开头已初始化，否则等于转换此前字符的结果。
- ¶2–¶3：至多转换 `from_end - from` 个源元素、写入 `to_end - to` 个目标元素；遇到无法转换的字符即停止；`from_next`/`to_next` 总是指向最后一个**成功转换**元素的下一位。
- 表 93 列出返回值：`ok`（完成）、`partial`（未全部转换）、`error`（遇到无法转换的字符）、`noconv`（类型相同且无需转换）。

¶4 是一条为 `basic_filebuf`（[[file.streams]]）设的要求：被 filebuf 使用的 codecvt，如果整段转换能返回 `ok`，那么**只给一个源字符**（`do_out`）或**只留一个目标位置**（`do_in`）时也必须返回 `ok`。这保证 filebuf 可以逐字符地转换。注 1 补充：由于 `state` 的作用，它可能返回 `ok`/`partial` 而 `from_next == from`、`to_next != to`（例如只输出了移位序列）。

其余成员：`do_unshift` 输出终止移位序列；`do_encoding()` 返回每个内部字符对应的外部字符数（-1 表示状态相关，0 表示变长）；`do_always_noconv()`；`do_length()`；`do_max_length()`。

## 数值类别（[category.numeric]）

### `num_get`：三阶段解析（[facet.num.get.virtuals]）

`num_get` 是 `istream >> 数值` 的真正执行者。¶2–¶3 把它规定为三个阶段：

**阶段 1——确定转换说明符**。按表 95：`basefield == oct` → `%o`；`== hex` → `%X`；`basefield == 0` → `%i`（自动识别 `0x`/`0` 前缀）；否则有符号 `%d`、无符号 `%u`。浮点一律 `%g`，`void*` 用 `%p`。

**阶段 2——逐字符累积**。每读一个 `charT`，在 `"0123456789abcdefpxABCDEFPX+-"` 经 `ctype::widen` 得到的表中查找，映射回 `char`；等于 `numpunct::decimal_point()` 的视为 `'.'`；等于 `thousands_sep()` 且 `grouping()` 非空的**丢弃但记住位置**。然后检查该字符能否作为阶段 1 说明符的输入字段的下一个字符，能就累积，否则停止。例 1：对输入 `"0x1a.bp+07p"`，`%d` 只累积 `"0"`，`%i` 累积 `"0x1a"`，`%g` 累积 `"0x1a.bp+07"`。

**阶段 3——转换并存储**。用 `strtoll`/`strtoull`/`strtof`/`strtod`/`strtold` 转换累积的字段：

| 情形 | 存入 `val` | `err` |
|---|---|---|
| 转换函数没有转换整个字段 | 0 | `failbit` |
| 有符号整数溢出 | 最大（或最小）可表示值 | `failbit` |
| 无符号整数无法表示 | 最大可表示值 | `failbit` |
| 其他 | 转换结果 | 不变 |

¶4：然后检查分组——丢弃的分隔符位置与 `grouping()` 不一致时设置 `failbit`（**值仍然被存入**）。¶5：若阶段 2 因 `in == end` 结束，设置 `eofbit`。

`bool` 版本（¶6–¶8）：未设置 `boolalpha` 时按 `long` 解析，0 → `false`，1 → `true`，其他值存 `true` 并设 `failbit`；设置了 `boolalpha` 时按 `truename()`/`falsename()` 做前缀唯一匹配。

```cpp run title="num-get.cpp" ok
#include <cassert>
#include <locale>
#include <sstream>
#include <string>

struct grouped : std::numpunct<char> {
protected:
    char do_thousands_sep() const override { return '\''; }
    std::string do_grouping() const override { return "\3"; }
};

int main() {
    int v = -1;
    std::istringstream a("1,234");                 // classic locale：',' 不是数字的一部分
    a >> v;
    assert(v == 1 && a.peek() == ',');

    std::locale loc(std::locale::classic(), new grouped);
    std::istringstream b("1'234'567");
    b.imbue(loc);
    b >> v;
    assert(v == 1234567 && b.eof() && !b.fail());

    std::istringstream c("12'34");                 // 分隔符位置与 grouping 不一致
    c.imbue(loc);
    c >> v;
    assert(v == 1234 && c.fail());                 // 值照样存入，但设置 failbit

    bool f = false;
    std::istringstream d("2");                     // 非 boolalpha：只有 0/1 合法
    d >> f;
    assert(f == true && d.fail());

    int big = 7;
    std::istringstream e("99999999999");
    e >> big;
    assert(big == 2147483647 && e.fail());         // 溢出：饱和到最大值 + failbit
}
```

!!! note "与 `from_chars` 对比"
    `num_get` 在溢出时**写入**饱和值，而 [[charconv]] 的 `from_chars` 在溢出时**不修改** `value`；`num_get` 受 locale 的小数点、分组影响，`from_chars` 永远是 `"C"` 语义。这两套规则不要混用。

### `num_put`：四阶段格式化（[facet.num.put.virtuals]）

¶2 规定四个阶段：

1. **阶段 1**：根据 `flags()` 选出 `printf` 转换说明符（表 97–100：`oct` → `%o`，`hex` → `%x`/`%X`，`fixed` → `%f`，`scientific` → `%e`，`fixed|scientific` → `%a`，否则 `%g`；`showpos` → `+`，`showbase`/`showpoint` → `#`），对浮点（`floatfield` 不是 `fixed|scientific` 时）以 `precision()` 作精度，然后得到 **在 `"C"` locale 下** `printf(spec, val)` 会打印的字符。
2. **阶段 2**：除小数点外的每个字符经 `ctype::widen` 转换；按 `numpunct::grouping()` 插入 `thousands_sep()`；小数点替换为 `decimal_point()`。
3. **阶段 3**：按 `adjustfield` 决定填充位置（表 101：`left` 填在后，`right` 填在前，`internal` 填在符号或 `0x` 之后）；不足 `width()` 时用 `fill` 补足；**然后调用 `str.width(0)`**——这就是 `setw` 只对下一次输出有效的原因。
4. **阶段 4**：逐字符 `*out++ = c` 输出。

`bool`（¶6）：无 `boolalpha` 时当作 `int` 输出；否则输出 `truename()`/`falsename()`。

### `numpunct`（[facet.numpunct]）

[locale.numpunct.general]/1：表 91 要求的 `numpunct<char>`/`numpunct<wchar_t>` 提供 `"C"` locale 的格式；¶2 用文法给出数字格式（*intval*、*floatval*），并规定**解析时若数字部分没有千位分隔符，则不施加分组约束**。

[facet.numpunct.virtuals]：`do_decimal_point` 默认 `'.'`，`do_thousands_sep` 默认 `','`（¶1–¶2）；`do_grouping`（¶3–¶4）返回一个被当作整数向量使用的 `string`：`vec[i]` 是从右往左第 `i` 组的位数，超出末尾则重复最后一组，`vec[i] <= 0` 或 `== CHAR_MAX` 表示该组不限位数；默认返回空串（不分组）。脚注用“(!)”警告：`"\003"` 是每组 3 位，而 `"3"` 大概是每组 51 位。`do_truename`/`do_falsename` 默认 `"true"`/`"false"`（¶5–¶6）。

## collate 类别（[category.collate]）

`collate<charT>` 提供字符串的排序比较与散列（[locale.collate.general]/1），`locale::operator()` 就是用它实现的。[locale.collate.virtuals]：

- `do_compare`（¶1）：返回 1/-1/0；表 91 要求的特化做**字典序**比较（[[alg.lex.comparison]]）——`"C"` locale 下就是按 code unit 比较。
- `do_transform`（¶2）：返回一个“排序键”字符串，对两个排序键做字典序比较，结果与 `do_compare` 相同。脚注说明它适用于“一个字符串要与很多字符串比较”的场景（相当于 C 的 `strxfrm`）。
- `do_hash`（¶3–¶4）：`do_compare` 判等的字符串必须散列相同；建议不等字符串碰撞概率接近 `1.0/numeric_limits<unsigned long>::max()`。

`collate_byname` 按 locale 名字实现该语言的排序规则；实际质量取决于平台 C 库的 `strcoll`/`wcscoll`，不同平台对同一 locale 名字的排序结果可能不同。

## time 类别（[category.time]）

`time_get`（[locale.time.get]）把字符序列解析为 `tm`，`time_put`（[locale.time.put]）把 `tm` 格式化为字符序列；二者都按 `strftime`/`strptime` 风格的转换说明工作。

- `time_get` 提供 `date_order()`（`no_order`/`dmy`/`mdy`/`ymd`/`ydm`）、`get_time`/`get_date`/`get_weekday`/`get_monthname`/`get_year`，以及 C++11 增加的按格式串解析的 `get(s, end, f, err, t, fmt, fmtend)`。[locale.time.get.general]/2：解析中途到达 `end` 时设置 `eofbit`。[locale.time.get.virtuals]/15：多次调用 `do_get` 时是否保留中间状态以组合字段是未指明的。
- `time_put::put` 逐个处理格式串中的转换说明（[locale.time.put.members]/1），`do_put` 按 `strftime` 的规则输出（[locale.time.put.virtuals]/1），并建议修饰符（`E`、`O`）的解释遵循 POSIX（¶3）。

iostream 层面的封装是 `std::get_time`/`std::put_time` 操纵符；而 C++20 的 `<chrono>` 格式化（[[time.format]]）走的是 `std::format` 路线，仅在 `L` 选项下才使用 locale。

## monetary 类别（[category.monetary]）

`money_get`、`money_put`、`moneypunct<charT, Intl>`（`Intl` 选择本地或国际格式，如 `$` 与 `USD `）。[category.monetary.general]/2：成员规范只适用于表 91/92 要求的特化。

- `moneypunct` 提供 `curr_symbol`、`positive_sign`/`negative_sign`、`frac_digits`、`pos_format`/`neg_format`（由 `money_base::part` 的四元组 `{symbol, sign, space, none, value}` 组成的 `pattern`）。
- `money_get::do_get`（[locale.money.get.virtuals]）：**总是用 `neg_format()` 的模式解析**（¶1）；结果是以“最小货币单位”计的整数（例 1：美国 locale 下 `$1,056.23` 得到 `105623`，或数字串 `"105623"`）；未设置 `showbase` 时货币符号是可选的（¶2）；正负号字符串的第一个字符在 `sign` 位置匹配，其余字符要求出现在所有其他成分之后（¶3，例 2 用 `"()"` 括号表示负数）。
- `money_put` 按 `pos_format`/`neg_format` 输出。

## messages 类别（[category.messages]）

`messages<charT>` 是对消息目录（如 POSIX `catgets`）的抽象：`open(name, loc)` 得到 `catalog`（失败返回负值），`get(cat, set, msgid, dfault)` 取消息（找不到返回 `dfault`），`close(cat)` 释放资源。名字到目录、`(set, msgid)` 到消息的映射都是由实现定义的（[locale.messages.virtuals]/1、/5）；对未打开或已关闭的 `catalog` 调用 `get`/`close` 违反前置条件（¶4、¶6）。实践中几乎没人用它——gettext 之类的方案更常见。

## 常见误区

!!! pitfall "覆盖了一个 `do_get` 重载，却发现没生效"
    `num_get` 的 `int`、`short` 版本并不在 `num_get` 的接口里——`istream::operator>>(int&)` 是先调用 `long` 版本再做范围检查的（[[istream.formatted.arithmetic]]）。而 ¶3 说一个虚函数是否调用另一个是未指明的。定制 `num_get` 时要覆盖所有相关重载。

!!! pitfall "以为 `ctype<wchar_t>::toupper` 能做完整的 Unicode 大小写转换"
    `ctype` 的大小写转换是逐字符一对一的；`ß` → `SS`、土耳其语 `i` → `İ` 这类与上下文或语言相关的映射无法表达。

## 小结

| 类别 | 主要 facet | 最该记住的一条 |
|---|---|---|
| ctype | `ctype`、`codecvt` | `ctype<char>` 是查表的显式特化；filebuf 要求 codecvt 能逐字符转换 |
| numeric | `num_get`、`num_put`、`numpunct` | 解析=“`strtol` + 分组检查”；溢出存饱和值；`grouping` 是整数向量 |
| collate | `collate` | 默认字典序；`transform` 生成排序键 |
| time | `time_get`、`time_put` | `strftime`/`strptime` 风格；多次 `do_get` 是否组合未指明 |
| monetary | `money_get`、`money_put`、`moneypunct` | 解析总用 `neg_format`；结果以最小货币单位计 |
| messages | `messages` | 映射全部由实现定义 |
