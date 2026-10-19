---
title: 标准 locale 类别与 facet
summary: 六个 locale 类别中的标准 facet：ctype 的字符分类与 ctype<char> 查表特化、codecvt 的编码转换、num_get/num_put 以 strtol/printf 为蓝本的解析与格式化、numpunct、collate、time、monetary 和 messages。
status: done
covers: *
related: localization, text, c.locales, istream.formatted.arithmetic, ostream.inserters.arithmetic, file.streams, depr.locale.category, format.string.std, charconv
tags: 标准库, locale, facet, iostream, 数值解析
updated: 2026-10-19
---

!!! tldr
    - 每个标准 facet 都由公开的非虚成员 `f()` 转发给受保护的虚函数 `do_f()`；定制时覆盖 `do_f()`。
    - `istream >> int` 实际由 `num_get` 完成：按流标志选出一个 `strtol` 风格的转换，逐字符收集，再检查千位分组；溢出时存入最大或最小值并设置 `failbit`。
    - `ostream << int` 由 `num_put` 完成：先得到 `"C"` locale 下 `printf` 的输出，再换上 locale 的小数点和千位分隔符，最后填充到 `width()` 并把 `width` 清零。
    - `ctype<char>` 是一个查表的显式特化，换一张分类表就能改变 `>>` 认为哪些字符是空白。
    - `numpunct::grouping()` 返回的字符串被当作整数数组使用，`"\3"` 是每组 3 位，`"3"` 是每组 51 位。

## 公共约定 [locale.categories.general]

每个标准 facet 都是同一个结构：

```cpp
template<class charT>
class numpunct : public locale::facet {
public:
  charT decimal_point() const;            // 只做 return do_decimal_point();
  static locale::id id;
protected:
  ~numpunct();                            // 受保护：只能经由 locale 销毁
  virtual charT do_decimal_point() const; // 规定语义的地方
};
```

公开成员只负责转发，语义写在受保护的虚函数上，定制时派生并覆盖这些虚函数（见 [[localization]]）。大多数 facet 还有一个 `_byname` 派生类，按 locale 名字实现该地区的规则。下文提到成员时，说的都是对应虚函数的语义。

¶1 负责格式化和解析的 facet 提供 `put()` 和 `get()` 成员，供 iostream 的 `<<`、`>>` 使用。它们接受一个 `ios_base&`，从它的 `flags()`、`precision()`、`width()` 读取格式，需要其他 facet 时调用它的 `getloc()`。格式化 facet 用 `fill` 实参补足宽度。

¶2 `put()` 不报告错误，输出迭代器的失败可以从返回的迭代器上看出（如 `ostreambuf_iterator::failed()`）。`get()` 接受一个 `ios_base::iostate&`，忽略它原来的值，解析出错时设置 `failbit`。

¶3 一个虚函数是否调用另一个虚函数是未指定的（{{unspec}}）。所以覆盖 `num_get::do_get(…, long&)` 时，不能指望别的 `do_get` 重载会转去调用它。

## ctype 类别 [category.ctype]

### `ctype<charT>`：字符分类与转换

[category.ctype.general] ¶1 `ctype_base::mask` 是位掩码类型（[[bitmask.types]]），元素为 `space`、`print`、`cntrl`、`upper`、`lower`、`alpha`、`digit`、`punct`、`xdigit`、`blank`，另有组合 `alnum = alpha | digit` 和 `graph = alnum | punct`。

[locale.ctype.general] ¶1 `ctype<charT>` 封装了 `<cctype>` 的功能，istream 解析输入时必须用它给字符分类。它的成员（[locale.ctype.virtuals]）：

- `is(m, c)` 和批量版本 `is(low, high, vec)` 给字符分类；`scan_is`、`scan_not` 找出第一个符合或不符合 `m` 的字符（¶1–¶6）。
- `toupper`、`tolower` 是一对一的映射，没有对应字符时原样返回（¶7–¶10）。
- `widen(c)` 对 `char` 做"最简单合理的变换"得到 `charT`（¶11）。只有基本字符集（[[lex.charset]]）中的字符要求变换唯一；而且变换不能给字符增加分类，即 `ctc.is(M, c) || !is(M, do_widen(c))` 恒为真。
- `narrow(c, dfault)` 是反向变换，无法变换时返回 `dfault`（¶13–¶14）。对基本字符集中的字符，`widen` 后再 `narrow` 能回到原字符；对任何数字字符 `c`，`do_narrow(c, dfault) - '0'` 就是它的数值，`num_get` 正是靠这一条把宽字符数字还原成值。

脚注说明，`do_widen` 的参数是为接收字符字面量的值设计的：`widen('0')` 把字面量编码中的 `'0'` 转成 locale 编码中的对应字符。这就是 [[text]] 所说的字面量编码与执行环境编码在 C++ 库中的交界处。

### `ctype<char>`：查表实现 [facet.ctype.special]

```cpp run title="comma-whitespace.cpp" ok
#include <cassert>
#include <locale>
#include <sstream>
#include <vector>

// 让 >> 把逗号也当作空白
struct comma_ws : std::ctype<char> {
    static const mask* make_table() {
        static std::vector<mask> t(classic_table(), classic_table() + table_size);
        t[','] |= space;
        return t.data();
    }
    comma_ws() : std::ctype<char>(make_table()) {}
};

int main() {
    std::istringstream in("1,2, 3");
    in.imbue(std::locale(in.getloc(), new comma_ws));
    std::vector<int> v;
    for (int x; in >> x;) v.push_back(x);
    assert((v == std::vector{1, 2, 3}));
}
```

[facet.ctype.special.general] ¶1 标准专门规定了 `ctype<char>` 的显式特化，好让 `char` 版本的成员函数可以内联查表。脚注解释，把它写进标准而不留作实现细节，是因为它影响从 `ctype<char>` 派生的接口。它没有 `do_is`、`do_scan_is` 这些虚函数，分类完全由一张 `mask` 表决定：

- 构造函数 `ctype(const mask* tab = nullptr, bool del = false, size_t refs = 0)`：`tab` 为空时用 `classic_table()`（[facet.ctype.char.members] ¶12）；`del` 为真时析构函数执行 `delete[] table()`（[facet.ctype.char.dtor]）。
- `is(m, c)` 返回 `table()[(unsigned char)c] & m`（[facet.ctype.char.members] ¶5）。字符先转成 `unsigned char`，所以负值的 `char` 不会越界，这一点与 `<cctype>` 的 `isalpha(int)` 不同。
- `table_size` 由实现定义，至少为 256。对 `v >= table_size` 的值，`table()[v]` 视为某个实现特定的值，不真正访问数组（[facet.ctype.char.members] ¶1）。
- `classic_table()` 返回 `"C"` locale 的分类表（[facet.ctype.char.statics]）。

上例就是标准做法：复制 `classic_table()`，修改其中几项，把新表交给基类构造函数。

### `codecvt`：编码转换 [locale.codecvt]

[locale.codecvt.general] ¶1–¶3 `codecvt<internT, externT, stateT>` 在两种编码之间转换，`stateT` 决定是哪一对编码。表 91 只要求两个特化：`codecvt<char, char, mbstate_t>` 是退化的转换，什么也不做；`codecvt<wchar_t, char, mbstate_t>` 在实现的窄字符集与宽字符集之间转换。`char16_t`、`char32_t` 的特化在附录 [[depr.locale.category]] 中，已弃用（{{deprecated}}）；C++26 还删除了 `<codecvt>` 头文件中的 `codecvt_utf8` 等（见 [[text]]）。

核心是 `do_in`（外部编码到内部编码）和 `do_out`（反方向），见 [locale.codecvt.virtuals]：

- ¶1 前置条件：`from <= from_end && to <= to_end` 有定义且为真；`state` 在序列开头时已初始化，否则等于转换此前字符后的结果。
- ¶2–¶3 至多读取 `from_end - from` 个源元素、写入 `to_end - to` 个目标元素，遇到无法转换的字符就停止。`from_next`、`to_next` 总是指向最后一个成功转换的元素的下一位。
- ¶5 和表 93 列出返回值：`ok`（完成）、`partial`（没有全部转换）、`error`（遇到无法转换的字符）、`noconv`（两种类型相同，无需转换）。

¶4 是为 `basic_filebuf`（[[file.streams]]）设的要求：filebuf 使用的 codecvt，如果整段转换能返回 `ok`，那么 `do_out` 只给一个源字符、或 `do_in` 只留一个目标位置时，也必须返回 `ok`。这样 filebuf 就可以一次转换一个内部字符。注 1 补充，由于 `state` 的作用，它可能返回 `ok` 或 `partial`，同时 `from_next == from` 而 `to_next != to`，例如只输出了移位序列。

其余成员：`do_unshift` 输出结束移位状态所需的字符（¶7–¶9）；`do_encoding()` 返回每个内部字符对应的外部字符数，-1 表示编码依赖状态，0 表示长度不固定（¶10）；`do_always_noconv()`、`do_length()`、`do_max_length()`（¶11–¶15）。

## 数值类别 [category.numeric]

[category.numeric.general] ¶2 `num_get`、`num_put` 从 `ios_base&` 实参读取格式标志，从它 imbue 的 locale 取得 `numpunct`（标点）和 `ctype`（字符分类）。¶3 iostream 的数值提取和插入运算符都通过这两个 facet 完成。

### `num_get`：三个阶段的解析 [facet.num.get.virtuals]

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
    assert(big == 2147483647 && e.fail());         // 溢出：存入最大值并设置 failbit
}
```

¶2–¶3 `num_get::do_get` 分三个阶段：

1. **确定转换说明符**。整数按表 95，`basefield == oct` 用 `%o`，`== hex` 用 `%X`，`basefield == 0` 用 `%i`（根据 `0x`、`0` 前缀自动识别进制），否则有符号类型用 `%d`、无符号类型用 `%u`。浮点一律用 `%g`，`void*` 用 `%p`。
2. **逐字符收集**。每读一个 `charT`，在 `"0123456789abcdefpxABCDEFPX+-"` 经 `ctype::widen` 得到的表里查找，映射回对应的 `char`；等于 `decimal_point()` 的字符视为 `'.'`。等于 `thousands_sep()` 且 `grouping()` 非空的字符，如果还没收集到 `'.'`，就记下位置后丢弃，否则阶段 2 结束。其他字符如果能作为第 1 步说明符所接受的输入的下一个字符，就收集起来，否则停止。例 1：对输入 `"0x1a.bp+07p"`，`%d` 只收集 `"0"`，`%i` 收集 `"0x1a"`，`%g` 收集 `"0x1a.bp+07"`。
3. **转换并存储**。用 `strtoll`、`strtoull`、`strtof`、`strtod` 或 `strtold` 转换收集到的字符：

| 情形 | 存入 `val` | `err` |
|---|---|---|
| 转换函数没有转换整个字段 | 0 | `failbit` |
| 有符号整数，值太大（太小） | 最大（最小）可表示值 | `failbit` |
| 无符号整数，值无法表示 | 最大可表示值 | `failbit` |
| 其他 | 转换结果 | 不变 |

¶4 接着检查分组：丢弃的分隔符位置与 `grouping()` 不一致时设置 `failbit`，但值已经存进去了。¶5 如果阶段 2 是因为读到输入末尾而结束的，再设置 `eofbit`。

¶6–¶8 `bool` 版本：没有设置 `boolalpha` 时按 `long` 解析，0 存 `false`，1 存 `true`，其他值存 `true` 并设置 `failbit`。设置了 `boolalpha` 时，用 `truename()` 和 `falsename()` 做匹配，只读到能唯一确定是哪一个为止。

`num_get` 的接口里没有 `int` 和 `short` 的重载。`istream::operator>>(int&)` 先调用 `long` 版本，再检查范围（[[istream.formatted.arithmetic]]）。[category.numeric.general] ¶1 也允许实现把较小类型的提取委托给较大的类型。

!!! note "与 `from_chars` 对比"
    溢出时 `num_get` 写入最大或最小值，[[charconv]] 的 `from_chars` 则不修改目标变量；`num_get` 受 locale 的小数点和分组影响，`from_chars` 永远按 `"C"` locale。两套规则不要混用。

### `num_put`：四个阶段的格式化 [facet.num.put.virtuals]

```cpp run title="num-put.cpp" ok
#include <cassert>
#include <iomanip>
#include <sstream>

int main() {
    std::ostringstream os;
    os << std::setw(6) << std::internal << -42 << '|' << 7;
    assert(os.str() == "-   42|7");      // 填充在符号之后；width 用完即被清零

    std::ostringstream h;
    h << std::showbase << std::hex << std::setw(8) << std::internal << std::setfill('0') << 255;
    assert(h.str() == "0x0000ff");       // internal：填充在 0x 之后
}
```

¶2 规定了四个阶段，¶5 给出细节：

1. **确定 `printf` 转换说明符**，得到 `"C"` locale 下 `printf(spec, val)` 会输出的字符。整数按表 97：`oct` 用 `%o`，`hex` 用 `%x` 或 `%X`。浮点按表 98：`fixed` 用 `%f`，`scientific` 用 `%e`，两者都设置时用 `%a`，否则用 `%g`。表 100 加上修饰：`showpos` 对应 `+`，整数的 `showbase` 和浮点的 `showpoint` 对应 `#`。浮点在 `floatfield` 不是 `fixed | scientific` 时以 `precision()` 作为精度。
2. **换上 locale 的标点**。小数点之外的字符经 `ctype::widen` 转换；按 `numpunct::grouping()` 插入 `thousands_sep()`；小数点换成 `decimal_point()`。
3. **填充**。按表 101 决定填充位置：`left` 填在后面，`right` 填在前面，`internal` 填在符号或 `0x` 之后。长度不足 `width()` 时用 `fill` 补足，然后调用 `str.width(0)`。所以 `setw` 只对下一次输出有效。
4. **输出**，逐个执行 `*out++ = c`。

¶6 `bool` 版本：没有 `boolalpha` 时当作 `int` 输出，否则输出 `truename()` 或 `falsename()`。

### `numpunct`：数字标点 [facet.numpunct]

[locale.numpunct.general] ¶1 表 91 要求的 `numpunct<char>` 和 `numpunct<wchar_t>` 提供 `"C"` locale 的格式。¶2 用文法给出整数和浮点数的格式，并规定：解析时如果数字部分没有千位分隔符，就不施加分组约束。

[facet.numpunct.virtuals] ¶1–¶2 `do_decimal_point` 默认返回 `'.'`，`do_thousands_sep` 默认返回 `','`。

¶3–¶4 `do_grouping` 返回一个 `string`，但它被当作整数数组使用：`vec[i]` 是从右往左第 `i` 组的位数；超出末尾时重复最后一组；`vec[i] <= 0` 或等于 `CHAR_MAX` 表示这一组位数不限。默认返回空串，即不分组。脚注专门提醒，`"\003"` 是每组 3 位，而 `"3"` 的值是字符 `'3'` 的编码 51，大概会被理解为每组 51 位。

¶5–¶6 `do_truename`、`do_falsename` 默认返回 `"true"` 和 `"false"`。

## collate 类别 [category.collate]

[locale.collate.general] ¶1 `collate<charT>` 提供字符串的排序比较和散列，`locale::operator()` 就用它实现。

[locale.collate.virtuals]：

- ¶1 `do_compare` 返回 1、-1 或 0。表 91 要求的特化做字典序比较（[[alg.lex.comparison]]），`"C"` locale 下就是按 code unit 比较。
- ¶2 `do_transform` 返回一个排序键：两个排序键按字典序比较的结果，与对原字符串调用 `do_compare` 的结果相同。脚注说明它适合一个字符串要与很多字符串比较的场景，相当于 C 的 `strxfrm`。
- ¶3–¶4 `do_compare` 认为相等的字符串必须散列相同；建议不相等的字符串碰撞概率接近 `1.0/numeric_limits<unsigned long>::max()`。

`collate_byname` 按 locale 名字实现该语言的排序规则。实际效果取决于平台 C 库的 `strcoll`、`wcscoll`，同一个 locale 名字在不同平台上的排序结果可能不同。

## time 类别 [category.time]

`time_get` 把字符序列解析成 `tm`，`time_put` 把 `tm` 格式化为字符序列，两者都按 `strftime`、`strptime` 风格的转换说明工作。iostream 层面的封装是操纵符 `std::get_time` 和 `std::put_time`。

- `time_get` 提供 `date_order()`（`no_order`、`dmy`、`mdy`、`ymd`、`ydm`）、`get_time`、`get_date`、`get_weekday`、`get_monthname`、`get_year`，以及按格式串解析的 `get(s, end, f, err, t, fmt, fmtend)`。[locale.time.get.general] ¶2 解析中途到达末尾时设置 `eofbit`。[locale.time.get.virtuals] ¶9 两位数年份是否接受、属于哪个世纪由实现定义；¶15 多次调用 `do_get` 时是否保留中间状态以组合各字段，是未指定的。
- `time_put::put` 逐个处理格式串中的转换说明（[locale.time.put.members] ¶1），`do_put` 按 `strftime` 的规则输出（[locale.time.put.virtuals] ¶1），并建议修饰符 `E`、`O` 的解释遵循 POSIX（¶3）。

C++20 `<chrono>` 的格式化（[[time.format]]）走 `std::format` 的路线，只在 `L` 选项下才使用 locale。

## monetary 类别 [category.monetary]

[category.monetary.general] ¶1 货币类别有 `money_get`、`money_put` 和 `moneypunct<charT, Intl>`，`Intl` 选择本地格式还是国际格式（如 `$` 与 `USD `）。

[locale.moneypunct.general] ¶1–¶2 `moneypunct` 提供 `curr_symbol`、`positive_sign`、`negative_sign`、`frac_digits` 以及 `pos_format`、`neg_format`。格式是一个由四个成分组成的 `pattern`：`symbol`、`sign`、`value` 各出现一次，第四个是 `space` 或 `none`。

[locale.money.get.virtuals]：

- ¶1 `money_get::do_get` 总是用 `neg_format()` 的模式解析。结果是以最小货币单位计的整数，例 1：美国 locale 下 `$1,056.23` 得到 `105623`，或数字串 `"105623"`。
- ¶2 没有设置 `showbase` 时，货币符号是可选的。
- ¶3 正负号字符串的第一个字符在 `sign` 位置匹配，其余字符要求出现在所有其他成分之后。例 2 用 `"()"` 表示负数，`"(100 L)"` 中的右括号要在最后出现。

[locale.money.put.virtuals] ¶1 `money_put` 根据值的正负选用 `neg_format` 或 `pos_format` 输出，输出后调用 `str.width(0)`；¶3 只有设置了 `showbase` 才输出货币符号。

## messages 类别 [category.messages]

`messages<charT>` 是对消息目录（如 POSIX 的 `catgets`）的抽象：`open(name, loc)` 得到一个 `catalog`，失败时返回负值；`get(cat, set, msgid, dfault)` 取出消息，找不到时返回 `dfault`；`close(cat)` 释放资源。

名字如何对应到目录、`(set, msgid)` 如何对应到消息，都由实现定义（[locale.messages.virtuals] ¶1、¶5）。对没有打开或已经关闭的 `catalog` 调用 `get`、`close` 违反前置条件（¶4、¶6）。实践中很少有人用它，gettext 一类的方案更常见。

<details class="fine" markdown="1"><summary>其余条文</summary>

各 facet 的 `Members` 子条款（[locale.ctype.members]、[facet.num.get.members]、[facet.numpunct.members]、[locale.collate.members]、[locale.time.get.members]、[locale.money.get.members]、[locale.messages.members] 等）只规定公开成员返回对应 `do_` 虚函数的结果。

各 `_byname` 子条款（[locale.ctype.byname]、[locale.codecvt.byname]、[locale.numpunct.byname]、[locale.collate.byname]、[locale.time.get.byname]、[locale.time.put.byname]、[locale.moneypunct.byname]、[locale.messages.byname]）只给出类定义，语义由 [locale.facet] ¶5 统一规定。

[facet.ctype.char.virtuals] ¶1 `ctype<char>` 的 `do_toupper` 等虚函数与通用模板中的同名函数描述相同。

[locale.ctype.general] ¶2 `ctype<char>` 和 `ctype<wchar_t>` 实现适合本机字符集的分类。

</details>

## 常见误解

!!! pitfall "覆盖了一个 `do_get` 重载，却没有生效"
    `num_get` 没有 `int`、`short` 的重载，`istream::operator>>(int&)` 调用的是 `long` 版本。[locale.categories.general] ¶3 又说一个虚函数是否调用另一个是未指定的。定制 `num_get` 时要覆盖所有相关的重载。

!!! pitfall "以为 `ctype<wchar_t>::toupper` 能做完整的 Unicode 大小写转换"
    `ctype` 的大小写转换是逐字符一对一的。`ß` 变成 `SS`、土耳其语的 `i` 变成 `İ` 这类一对多或依赖语言的映射无法表达。

## 小结

| 类别 | 主要 facet | 记住一条 |
|---|---|---|
| ctype | `ctype`、`codecvt` | `ctype<char>` 是查表的显式特化；filebuf 要求 codecvt 能逐字符转换 |
| numeric | `num_get`、`num_put`、`numpunct` | 解析是 `strtol` 加分组检查，溢出存入极值；`grouping` 是整数数组 |
| collate | `collate` | 默认按字典序；`transform` 生成排序键 |
| time | `time_get`、`time_put` | `strftime`/`strptime` 风格；多次 `do_get` 是否组合未指定 |
| monetary | `money_get`、`money_put`、`moneypunct` | 解析总用 `neg_format`；结果以最小货币单位计 |
| messages | `messages` | 映射全部由实现定义 |
