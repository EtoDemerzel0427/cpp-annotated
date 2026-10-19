---
title: formatter 与范围格式化
summary: std::formatter 定制点：parse 与 format 两个成员的约定、formattable 概念、标准提供与禁用的特化、? 转义格式、解析上下文和格式化上下文；怎样写一个正确的自定义 formatter；C++26 的免锁优化开关；C++23 的范围格式化。
status: draft
covers: *, formatter.requirements, format.formatter.locking, format.formattable, format.formatter.spec, format.string.escaped, format.parse.ctx, format.context, format.range, format.range.fmtkind, format.range.formatter, format.range.fmtdef, format.range.fmtmap, format.range.fmtset, format.range.fmtstr
papers: P0645R10, P2286R8, P2585R1, P2418R2, P3107R5
related: format, format.string, print.fun, namespace.std, container.adaptors.format, temp.expl.spec, temp.spec.partial
tags: 标准库, format, formatter, 范围, 定制点
updated: 2026-10-19
---

!!! tldr
    - 库对每个实参使用 `formatter<T, charT>`：`parse` 读取格式说明，可以在编译期运行；`format` 按读到的选项输出值，在运行期运行。
    - 自定义 formatter 要满足三条：`parse` 是 `constexpr`，`format` 是 `const` 成员，`format` 对上下文类型写成模板。最省事的做法是继承一个现有的 formatter。
    - 没有特化的 `formatter<T>` 是禁用的，它不能构造也不能复制，所以 `formattable<T, char>` 给出 `false`，而不是硬错误。
    - `?` 选择转义形式：字符串加引号，控制字符写成 `\u{...}`，非法码元写成 `\x{...}`。范围和 tuple 的元素默认用这种形式。
    - 元素可格式化的范围默认都可以格式化：序列输出 `[1, 2]`，map 输出 `{1: "x"}`，set 输出 `{1, 3}`；`{:n}`、`{:s}`、`{::spec}` 等选项可以调整。

## 一个完整的例子

```cpp run title="custom-formatter.cpp" ok
#include <cassert>
#include <format>
#include <string_view>
#include <vector>

struct Point { int x, y; };

// 自定义语法：可选的 'p'（紧凑）或 'c'（带括号，默认）
template <>
struct std::formatter<Point> {
  char style = 'c';
  constexpr auto parse(std::format_parse_context& ctx) {
    auto it = ctx.begin();
    if (it != ctx.end() && (*it == 'p' || *it == 'c'))
      style = *it++;
    if (it != ctx.end() && *it != '}')
      throw std::format_error("invalid spec for Point");
    return it;
  }
  template <class FormatContext>
  auto format(const Point& p, FormatContext& ctx) const {
    if (style == 'p')
      return std::format_to(ctx.out(), "{} {}", p.x, p.y);
    return std::format_to(ctx.out(), "({}, {})", p.x, p.y);
  }
};

// format 只读取值，不会重入 print，可以声明为免锁
template <>
constexpr bool std::enable_nonlocking_formatter_optimization<Point> = true;

enum class Color { red, green };

// 继承：复用 string_view 的全部格式说明（填充、对齐、宽度、精度）
template <>
struct std::formatter<Color> : std::formatter<std::string_view> {
  template <class FormatContext>
  auto format(Color c, FormatContext& ctx) const {
    std::string_view name = c == Color::red ? "red" : "green";
    return std::formatter<std::string_view>::format(name, ctx);
  }
};

static_assert(std::formattable<Point, char>);
static_assert(std::formattable<Color, char>);

int main() {
  assert(std::format("{}", Point{1, 2}) == "(1, 2)");
  assert(std::format("{:p}", Point{1, 2}) == "1 2");
  assert(std::format("{:*^7}", Color::red) == "**red**");
  assert(std::format("{}", std::vector{Point{1, 2}, Point{3, 4}})
         == "[(1, 2), (3, 4)]");
  assert(std::format("{::p}", std::vector{Point{1, 2}}) == "[1 2]");  // 元素说明交给 Point
}
```

`std::formatter` 是格式化库的定制点。对 `std::format("{:p}", pt)`，库先用 `formatter<Point>` 的 `parse` 读取冒号后面的 `p`，把结果存进 formatter 对象，再调用 `format` 把值写到输出。

这样拆分的原因是：`parse` 只依赖格式串和类型，所以可以在编译期运行，用来检查格式串（[[format.fmt.string]]）；`format` 依赖值，只能在运行期运行。程序可以为自己定义的类型显式特化或偏特化 `std::formatter`（[[namespace.std]]）。

写 `std::format("{:z}", Point{1, 2})` 会在编译期报错：`parse` 在常量求值中执行了 `throw`，格式串的 consteval 构造因此失败。下面几节解释这段代码里每个细节背后的规则。

## formatter 要求（[formatter.requirements]）

¶1 类型 `F` 满足 ***BasicFormatter*** 要求，是指它可默认构造、可复制构造、可复制赋值、可交换、可析构，并且表 112 的表达式有效：`g.parse(pc)`，以及 `f.format(u, fc)`，其中 `u` 是 `T` 的左值，`f` 可以是 `const` 的。

¶2 ***Formatter*** 要求在此基础上加上表 113：`f.format(t, fc)` 对可转换为（可能带 `const` 的）`T` 的值也有效，并且 `f.format(u, fc)` 不修改 `u`。只满足 *BasicFormatter* 的 formatter 用于只能以非 `const` 方式格式化的类型，例如 `begin()` 不是 `const` 的 `ranges::filter_view`。C++20 的缺陷修正 [[P2418R2]] 让这类类型可以格式化。

表 112 对 `parse` 的约定：

- ¶3.8 `pc.begin()` 指向 *format-spec* 的开头。没有 *format-spec* 或它为空时，`pc.begin() == pc.end()` 或者 `*pc.begin() == '}'`。
- `parse` 解析到第一个不匹配的字符为止。除非整个范围都解析完了，或者不匹配的字符是 `}`，否则抛出 `format_error`。
- 把解析结果存进 `*this`，返回解析范围的尾后迭代器，也就是指向 `}` 的迭代器。

`format` 的输出只能依赖于：被格式化的值、`fc.locale()`、`fc.arg(n)`（用于动态宽度等），以及上一次 `parse` 看到的格式说明。formatter 不应该读取全局状态，否则编译期检查和运行期格式化就不能分开进行。

## formattable 概念（[format.formattable]）{{c++23}}

```cpp
template<class T, class Context,
         class Formatter = typename Context::template formatter_type<remove_const_t<T>>>
  concept formattable-with =
    semiregular<Formatter> &&
    requires(Formatter& f, const Formatter& cf, T&& t, Context fc,
             basic_format_parse_context<typename Context::char_type> pc) {
      { f.parse(pc) } -> same_as<typename decltype(pc)::iterator>;
      { cf.format(t, fc) } -> same_as<typename Context::iterator>;
    };

template<class T, class charT>
  concept formattable =
    formattable-with<remove_reference_t<T>, basic_format_context<fmt-iter-for<charT>, charT>>;
```

从这个定义可以读出写 formatter 必须遵守的三条规则：

1. `format` 必须是 `const` 成员函数，因为概念通过 `const Formatter& cf` 调用它。
2. formatter 必须是 `semiregular` 的：可默认构造，可复制。
3. `format` 必须能接受 `basic_format_context<fmt-iter-for<charT>, charT>`。¶1 规定 *fmt-iter-for* 是一个未指明的输出迭代器类型。

第 3 条最容易出问题。只接受 `std::format_context&` 的 `format` 能用于 `std::format("{}", t)`，但不保证满足 `formattable`。`vector<T>`、`optional<T>` 这类组合类型的 formatter 要求元素满足 `formattable`，于是用不了它：

```cpp run title="non-generic-format.cpp" error
#include <format>
#include <vector>

struct P { int x; };
template <> struct std::formatter<P> {
  constexpr auto parse(std::format_parse_context& ctx) { return ctx.begin(); }
  auto format(P p, std::format_context& ctx) const {   // 只接受 format_context
    return std::format_to(ctx.out(), "{}", p.x);
  }
};

int main() {
  (void)std::format("{}", P{1});                 // OK
  (void)std::format("{}", std::vector<P>{{1}});  // error: P 不满足 formattable
}
```

libc++ 的 *fmt-iter-for* 是 `charT*`，`format_context&` 绑定不上，所以第二行编译失败。把 `format` 写成对上下文类型的模板，就没有这个问题。

¶2 `T` 和 `charT` 要建模 `formattable`，还要求 `formatter<remove_cvref_t<T>, charT>` 满足 *BasicFormatter* 的语义要求；`remove_reference_t<T>` 带 `const` 时，还要满足 *Formatter* 要求。

## 标准特化（[format.formatter.spec]）

### 启用与禁用（¶2、¶4–¶8）

每个 `formatter` 特化要么是**启用的**（enabled），要么是**禁用的**（disabled）。¶5 库和用户都没有提供特化的 `formatter<T, charT>` 是禁用的。¶7 禁用的特化不能默认构造，不能复制或移动构造，也不能复制或移动赋值。

这样一来，能否格式化就成了一个可以安全查询的类型性质：`formattable` 要求 `semiregular<Formatter>`，禁用的特化不满足，概念给出 `false`，不会产生硬错误。libc++ 的做法是让主模板继承一个所有特殊成员都 `= delete` 的类。

¶2 列出各头文件提供的启用特化（`charT` 是 `char` 或 `wchar_t`）：

| 特化 | debug-enabled | constexpr-enabled |
|---|---|---|
| `formatter<char, char>`、`<char, wchar_t>`、`<wchar_t, wchar_t>` | 是 | 是 |
| 字符串：`charT*`、`const charT*`、`charT[N]`、`basic_string`、`basic_string_view` | 是 | 是 |
| 所有有符号、无符号整数类型和 `bool` | | 是 |
| 所有 cv 非限定浮点类型 | | |
| `nullptr_t` | | 是 |
| `void*`、`const void*` | | |

- **debug-enabled**（[[g:debug-enabled-specialization]]）的特化另外提供 public、constexpr 的成员 `set_debug_format()`，效果相当于格式说明的 type 是 `?`。范围和 tuple 的 formatter 靠它让元素默认以转义形式输出。
- **constexpr-enabled**（[[g:constexpr-enabled-specialization]]）的特化，`format` 成员声明为 `constexpr`。浮点类型和 `void*` 不在其中，所以标准不要求能在编译期格式化浮点数。这是 C++23 之后的新措辞。

¶4 `<format>` 还提供一组禁用的特化：`char` 字符串配 `wchar_t` 输出，例如 `formatter<const char*, wchar_t>`。¶3 的注 1 说明，需要隐式的多字节与宽字符转换的特化都是禁用的。

¶6 库提供的特化都是启用的，并且满足 *Formatter* 要求，除非另有说明。¶8 的例子演示了继承现有 formatter 的惯用法，也说明 `std::format("{}", L"foo")`（宽字符串配窄输出）和未特化的用户类型都是错误。

### 免锁优化（[format.formatter.locking]）{{c++26}}

```cpp
template<class T>
  constexpr bool enable_nonlocking_formatter_optimization = false;
```

这个变量模板服务于 `std::print`（[[print.fun]]）。`print` 有两种实现策略：

- 锁住 `FILE*`，一边格式化一边写入流。不需要中间缓冲区，速度快。
- 先把结果格式化到一个临时字符串，再锁住流一次写入。

第一种策略在持锁期间调用用户的 `formatter::format`。如果它又打印到同一个流，会死锁；如果它执行很久，会阻塞其他线程的输出。[[P3107R5]] 的规定是：只有所有实参类型的 `enable_nonlocking_formatter_optimization` 都为 `true` 时，`print` 才走直接写入的路径，否则先缓冲。

- [format.formatter.spec] ¶3：标准库为之提供 formatter 的每个类型，这个变量都特化为 `true`，除非另有规定。
- 范围类型的特化是 `false`（[[format]]），因为元素的 formatter 可能是用户写的；`pair`、`tuple` 取各元素该值的合取。
- [format.formatter.locking] ¶1：用户可以为 cv 非限定的程序定义类型特化它，特化必须可用于常量表达式，类型为 `const bool`。只有 `format` 不会重入 `print`、不会长时间阻塞时，才应设为 `true`。

!!! impl
    本机 libc++ 声明了这个变量模板，并为内建 formatter 特化为 `true`，但 `<print>` 的实现还没有用到它，两条路径的区分尚未落地。

## 转义格式（[format.string.escaped]）{{c++23}}

```cpp run title="escaped.cpp" ok
#include <cassert>
#include <format>
#include <string>

int main() {
  assert(std::format("[{:?}]", "h\tllo") == "[\"h\\tllo\"]");
  assert(std::format("[{:?}, {:?}]", '\'', '"') == "['\\'', '\"']");
  assert(std::format("{:?}", std::string("\0\x1b", 2)) == "\"\\u{0}\\u{1b}\"");
  assert(std::format("{:?}", "\xc3\x28") == "\"\\x{c3}(\"");   // 非法 UTF-8
  assert(std::format("{:?}", "\u0301") == "\"\\u{301}\"");      // 孤立的组合符号
}
```

¶1 字符或字符串可以格式化为转义形式，便于调试和写日志，结果叫做**转义字符串**（[[g:escaped-string]]）。¶2 用字符类型对应的编码 *CE* 解释输入并构造输出：

1. 输出 `"`。
2. 把输入分成片段，每段是一个字符、一个移位序列，或者一串非法码元，依次处理：
    - 制表、换行、回车、`"`、`\` 输出为 `\t`、`\n`、`\r`、`\"`、`\\`（表 114）。
    - *CE* 是 UTF 编码，字符的 General_Category 属于 Separator（Z）或 Other（C），并且不是空格时，输出 `\u{十六进制}`。这一类包括控制字符、不可打印字符、零宽连接符等。
    - 字符具有 Grapheme_Extend=Yes 属性（组合附加符号），而它前面没有一个原样输出的字符可以依附时，也输出 `\u{...}`。
    - 非 UTF 编码下，实现定义的一组分隔字符和不可打印字符同样转义。
    - 其他字符原样输出。
    - 移位序列怎样处理未指明；非法码元逐个输出为 `\x{十六进制}`。
3. 输出 `"`。

¶3 单个字符的转义形式用 `'` 包围；字符 `'` 输出为 `\'`，`"` 原样输出。

组合符号那一条的用意是：`"e\u0301"`（e 加组合锐音符）原样输出为 é；孤立的组合符号，比如出现在开头，或者前一个字符已经被转义，就会被转义，避免它粘在引号或反斜杠上造成误读。

## 解析上下文（[format.parse.ctx]）

`basic_format_parse_context<charT>` 保存当前未解析的格式串范围、编号模式（未定、手动、自动）、下一个自动编号和实参个数 `num_args_`。¶2 程序显式特化或偏特化它是 IFNDR，即程序非良构，但不要求编译器诊断。

| 成员 | 作用 |
|---|---|
| `begin()`、`end()` | 当前 *format-spec* 的起点、整个格式串的终点 |
| `advance_to(it)` | ¶6 前置条件：从 `it` 可以到达 `end()` |
| `next_arg_id()` | 自动编号，取下一个下标；已处于手动模式时抛出 `format_error`（¶9）；下标不小于 `num_args_` 时不是核心常量表达式（¶10） |
| `check_arg_id(id)` | 进入手动模式；已处于自动模式时抛出（¶12）；`id >= num_args_` 时不是核心常量表达式（¶13） |
| `check_dynamic_spec<Ts...>(id)` {{c++26}} | 第 `id` 个实参的类型不属于 `Ts...` 时，调用不是核心常量表达式（¶14–¶15） |
| `check_dynamic_spec_integral`、`check_dynamic_spec_string` | 上一行的简便形式（¶16–¶17） |

自定义 formatter 想支持动态宽度这类引用另一个实参的语法时，必须调用 `next_arg_id` 或 `check_arg_id`。它们既维护不能混用编号的规则（[[format.string]]），又在编译期检查下标是否越界。`check_dynamic_spec` 进一步在编译期检查被引用实参的类型，标准 formatter 对动态宽度做的就是这件事。

¶3 的注 1 指出：公开构造函数把 `num_args_` 初始化为 0，所以在程序自己构造的解析上下文上调用 `next_arg_id` 等成员，永远不是核心常量表达式。库内部使用能传入实参个数的构造方式。

!!! impl
    本机 libc++ 的 `basic_format_parse_context` 还没有提供 `check_dynamic_spec` 系列成员。

## 格式化上下文（[format.context]）

`basic_format_context<Out, charT>` 保存实参和输出迭代器：

- `arg(id)`（¶6）取第 `id` 个实参，越界时得到一个空的实参；
- `locale()`（¶7）在格式化函数接受了 locale 时返回它，否则返回 `std::locale()`，即全局 locale；
- `out()`（¶8）等价于 `return std::move(out_);`，迭代器被移出，写完之后要把新位置作为返回值交回，或者调用 `advance_to`；
- `advance_to(it)`（¶9）等价于 `out_ = std::move(it);`。

¶3 `Out` 必须建模 `output_iterator<const charT&>`。¶4 `format_context` 是向 `string` 追加内容的那个特化。¶5 建议实现对每种 `charT` 只提供一个这样的特化，用统一接口的临时缓冲区包装 `string`、`vector` 等目标，避免为每种输出迭代器重复实例化。libc++ 的 `format_context` 就是 `basic_format_context<back_insert_iterator<__format::__output_buffer<char>>, char>`，这个类型会出现在 formatter 相关的诊断信息里。

## 范围格式化（[format.range]）{{c++23}}

```cpp run title="ranges.cpp" ok
#include <cassert>
#include <format>
#include <map>
#include <set>
#include <string>
#include <vector>

int main() {
  assert(std::format("{}", std::vector{1, 2, 3}) == "[1, 2, 3]");
  assert(std::format("{::#x}", std::vector{10, 11}) == "[0xa, 0xb]");   // 元素说明
  assert(std::format("{:n}", std::vector{1, 2}) == "1, 2");            // 去掉括号
  assert(std::format("{:*^11}", std::vector{1, 2}) == "**[1, 2]***");  // 宽度作用于整体
  assert(std::format("{}", std::vector<std::string>{"a", "b"}) == "[\"a\", \"b\"]");
  assert(std::format("{}", std::map<int, std::string>{{1, "x"}}) == "{1: \"x\"}");
  assert(std::format("{}", std::set{3, 1}) == "{1, 3}");
  assert(std::format("{}", std::vector{'h', 'i'}) == "['h', 'i']");
  assert(std::format("{:s}", std::vector{'h', 'i'}) == "hi");
  assert(std::format("{:?s}", std::vector{'h', '\n'}) == "\"h\\n\"");
  assert(std::format("{}", std::vector<std::vector<int>>{{1}, {2, 3}}) == "[[1], [2, 3]]");
}
```

[[P2286R8]] 让元素可格式化的 `input_range` 默认都可以格式化，[[P2585R1]] 改进了默认格式：map 输出 `{k: v}`，set 输出 `{a, b}`，字符序列可以按字符串输出。范围的 formatter 是一个受约束的偏特化：

```cpp
template<ranges::input_range R, class charT>
  requires (format_kind<R> != range_format::disabled) &&
           formattable<ranges::range_reference_t<R>, charT>
struct formatter<R, charT> : range-default-formatter<format_kind<R>, R, charT> { };
```

它按 `format_kind<R>` 的值分派到四种仅用于说明的 *range-default-formatter*。

### format_kind：自动分类（[format.range.fmtkind]）

¶1 对非范围类型实例化 `format_kind` 的主模板，程序非良构。¶2 对 `input_range` 的分类规则是：

1. ¶2.1 元素类型（去掉引用和 cv 之后）就是 `R` 本身时，为 `disabled`。注 1 说明这是为了避免约束递归：`filesystem::path` 是元素为 `path` 的范围，不排除的话，`formattable<path>` 会要求 `formattable<path>`。
2. ¶2.2 否则，如果 `R::key_type` 是一个类型：`R::mapped_type` 也是类型，并且元素是 `pair` 或二元 `tuple` 时为 `map`，否则为 `set`。
3. ¶2.3 其余为 `sequence`。

`string` 和 `debug_string` 不会被自动选中。`std::string` 有自己的 formatter，比范围偏特化更特殊；`vector<char>` 默认按序列输出为 `['h', 'i']`。¶3 用户可以为自己的范围类型特化 `format_kind`，例如把自定义字符串类声明为 `range_format::string`。

### range_formatter（[format.range.formatter]）

¶2 范围的格式说明语法是：

```text
range-format-spec:  range-fill-and-align(opt) width(opt) n(opt) range-type(opt) range-underlying-spec(opt)
range-type:         m | s | ?s
range-underlying-spec:  : format-spec        ← 交给元素的 formatter
```

- 填充字符不能是 `{`、`}`，也不能是 `:`，因为 `:` 引出元素的格式说明。
- ¶5 `n` 去掉外层括号。
- ¶6 和表 115 规定 *range-type*：`m` 要求元素是二元 `pair` 或 `tuple`，括号变为 `{}`，每个元素输出为 `k: v`；`s`、`?s` 要求元素类型是 `charT`，按字符串或转义字符串输出，这时不能再有 `n` 或元素说明。
- ¶9 没有元素说明、*range-type* 不是 `s` 或 `?s`，并且元素的 formatter 有 `set_debug_format()` 时，调用它。所以 `vector<string>` 默认输出带引号：`["a", "b"]`。
- ¶11 输出依次是开括号、以分隔符隔开的各元素、闭括号，默认分别是 `[`、`, `、`]`，可以用 `set_brackets`、`set_separator` 修改。宽度和对齐作用于整个范围的输出。

### 四种默认格式（[format.range.fmtdef] 至 [format.range.fmtstr]）

| `format_kind` | 行为 | 例子 |
|---|---|---|
| `sequence` | 直接交给 `range_formatter` | `[1, 2, 3]` |
| `map` | [format.range.fmtmap] ¶1 要求元素是二元 `pair` 或 `tuple`；括号为 `{}`，元素去掉括号，元素内部的分隔符改为 `: ` | `{1: "x"}` |
| `set` | 括号改为 `{}` | `{1, 3}` |
| `string`、`debug_string` | [format.range.fmtstr] ¶1 要求元素类型就是 `charT`；先复制成 `basic_string<charT>` 再按字符串格式化；`debug_string` 另外调用 `set_debug_format()` | `hi`、`"hi"` |

[[format]] 中仅用于说明的 *fmt-maybe-const* 的作用是：如果 `const R` 也是元素可格式化的范围，就以 `const R&` 格式化，否则以 `R&` 格式化。这样只能非 `const` 迭代的视图也能格式化。

容器适配器 `stack`、`queue`、`priority_queue` 的格式化见 [[container.adaptors.format]]。

## 常见误解

!!! pitfall "format 忘了 const"
    `formattable` 通过 `const Formatter&` 调用 `format`。在本机 libc++ 中，`format` 不是 `const` 成员时，连最简单的 `std::format("{}", t)` 也编译失败。需要可变状态时可以用 `mutable` 成员，但这通常说明设计有问题。

!!! pitfall "parse 不是 constexpr"
    编译期检查要在常量求值中调用 `parse`。`parse` 不是 `constexpr` 时，每个 `std::format("...", t)` 都编译失败，只能改用 `vformat` 或 `dynamic_format`。

!!! pitfall "手写输出后没有返回新的迭代器"
    `out()` 把迭代器移出。手写输出时要写成 `auto it = ctx.out(); *it++ = 'x'; return it;`，返回的迭代器就是新的位置。

!!! pitfall "随意开启免锁优化"
    如果 `format` 内部调用了 `std::print` 输出到同一个流，或者做了耗时的 I/O，把 `enable_nonlocking_formatter_optimization` 设为 `true`，在实现了直接写入路径的库上会导致死锁或长时间持锁。

## 思考题

!!! question "思考题 1"
    `vector<bool>` 的 `range_reference_t` 是 `vector<bool>::reference`，不是 `bool`。为什么 `std::format("{}", std::vector<bool>{true, false})` 仍然可以编译？

<details markdown="1">
<summary>答案</summary>

范围偏特化要求 `formattable<range_reference_t<R>, charT>`，而 `vector<bool>::reference` 是一个代理类。[[vector.bool]] 专门为这个代理类型提供了一个 formatter 偏特化，内部委托给 `formatter<bool>`。没有它，`format_kind` 虽然给出 `sequence`，`formattable` 约束却不满足，范围偏特化不会被选中。本机输出 `[true, false]`。
</details>

!!! question "思考题 2"
    `std::format("{}", std::filesystem::path("a/b"))` 会输出 `[a, b]` 吗？

<details markdown="1">
<summary>答案</summary>

不会走范围格式化。`path` 的元素类型就是 `path`，按 [format.range.fmtkind] ¶2.1，`format_kind<path>` 是 `disabled`。C++26 为 `path` 提供了专门的 formatter（[fs.path.fmtr]），按路径字符串输出。没有提供这个 formatter 的实现上，`path` 不可格式化；本机 libc++ 中 `std::formattable<std::filesystem::path, char>` 为 `false`。
</details>

## 小结

| 主题 | 规则 |
|---|---|
| 两个成员 | `parse` 读取并保存选项，可在编译期运行；`format` 在运行期输出 |
| `formattable` | 要求 formatter 是 `semiregular` 的、`format` 是 `const` 的、能接受未指明迭代器类型的上下文 |
| 禁用的特化 | 特殊成员都不可用，`formattable` 给出 `false` |
| debug-enabled | 有 `set_debug_format()`；范围和 tuple 对元素自动调用 |
| constexpr-enabled | 整数、`bool`、字符、字符串、`nullptr_t`；不包括浮点和 `void*` |
| 转义 `?` | 加引号；控制和不可打印字符写成 `\u{..}`，非法码元写成 `\x{..}` |
| 解析上下文 | `next_arg_id`、`check_arg_id` 维护编号规则；`check_dynamic_spec` 在编译期检查类型 |
| 免锁优化 | 默认 `false`；标准类型为 `true`；范围为 `false`；用户可以特化 |
| 范围 | `format_kind` 分为 map、set、sequence；`{:n}`、`{:m}`、`{:s}`、`{:?s}`、`{::元素说明}` |
