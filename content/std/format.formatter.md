---
title: formatter 与范围格式化
summary: formatter<T, charT> 机制——BasicFormatter/Formatter 要求、formattable 概念、启用/禁用的标准特化、? 转义格式、parse 与 format 两个上下文；如何正确编写自定义 formatter（constexpr parse、const 且对上下文泛型的 format、继承现有 formatter）；C++26 的 enable_nonlocking_formatter_optimization；C++23 的范围格式化（format_kind、range_formatter、map/set/string 默认格式）
status: draft
covers: *, formatter.requirements, format.formatter.locking, format.formattable, format.formatter.spec, format.string.escaped, format.parse.ctx, format.context, format.range, format.range.fmtkind, format.range.formatter, format.range.fmtdef, format.range.fmtmap, format.range.fmtset, format.range.fmtstr
papers: P0645R10, P2286R8, P2585R1, P2418R2, P3107R5
related: format, format.string, print.fun, namespace.std, container.adaptors.format, temp.expl.spec, temp.spec.partial
tags: 标准库, format, formatter, 范围, 定制点
updated: 2026-10-18
---

`std::formatter<T, charT>` 是格式化库的**定制点**：库对每个实参调用 `formatter<remove_cvref_t<T>, charT>` 的两个成员——

- `parse(pc)`：读取替换字段中冒号后的 *format-spec*，把解析结果存进 `*this`；
- `format(t, fc)`：按存下的选项把 `t` 写到 `fc.out()`。

这一拆分是整套设计的关键：`parse` 只依赖格式串和类型，因而可以在**编译期**运行（[[format.fmt.string]]）；`format` 依赖值，在运行期运行。用户通过显式特化或偏特化 `std::formatter`（[[namespace.std]] 允许对程序定义类型这样做）来让自己的类型可格式化。

本页覆盖 [format.formatter] 的全部子条款和 [format.range]。

## formatter 要求（[formatter.requirements]）

### 两级要求（¶1–¶2）

- ***BasicFormatter***：可默认构造、可复制构造/赋值、可交换、可析构，且满足表 112——`g.parse(pc)` 与 `f.format(u, fc)`（`u` 是 `T` 的**左值**，`f` 可能是 `const` 的）。
- ***Formatter***：在此基础上还满足表 113——`f.format(t, fc)` 对“可转换为（可能 const 的）`T`”的值也能工作，并且 `f.format(u, fc)` **不修改** `u`。

两级之分来自 [[P2418R2]]：有些类型只能以非 `const` 方式格式化（例如 `ranges::filter_view` 的 `begin()` 不是 `const` 的），它们的 formatter 只满足 *BasicFormatter*。

### `parse` 的约定（表 112）

- ¶3.8：`pc.begin()` 指向 *format-spec* 的开头；没有或为空时，要么 `pc.begin() == pc.end()`，要么 `*pc.begin() == '}'`。
- 解析到第一个**不匹配**的字符为止；除非整个范围都解析完或者不匹配的字符是 `}`，否则抛 `format_error`。
- 返回解析范围的尾后迭代器（即指向 `}` 的迭代器）。

### `format` 的约定

输出**只能**依赖于：被格式化的值、`fc.locale()`、`fc.arg(n)`（用于动态宽度等）、以及上一次 `parse` 看到的格式说明。也就是说 formatter 不应读取全局状态——这让格式化结果可预测，也是“编译期检查 + 运行期格式化”能分开进行的前提。

## `formattable` 概念（[format.formattable]）{{c++23}}

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

从这个定义能读出三条**写自定义 formatter 必须遵守**的规则：

1. **`format` 必须是 `const` 成员函数**——概念里调用的是 `cf.format(...)`，`cf` 是 `const Formatter&`。
2. **formatter 必须 `semiregular`**——可默认构造、可复制。
3. **`format` 必须能接受 `basic_format_context<fmt-iter-for<charT>, charT>`**，而 *fmt-iter-for* 是一个**未指明**的输出迭代器类型（¶1）。只写 `auto format(const T&, std::format_context&) const` 的 formatter 能用于 `std::format("{}", t)`，但**不保证**满足 `formattable`——于是 `vector<T>`、`optional<T>` 等组合类型的 formatter 不能用它。libc++ 的 *fmt-iter-for* 是 `charT*`（`__format/concepts.h`），`format_context&` 绑不上，`std::format("{}", std::vector<T>{})` 直接编译失败。

结论：把 `format` 写成**对上下文类型泛型的模板**。

```cpp run title="non-generic-format.cpp" error
#include <format>
#include <vector>

struct P { int x; };
template <> struct std::formatter<P> {
    constexpr auto parse(std::format_parse_context& ctx) { return ctx.begin(); }
    auto format(P p, std::format_context& ctx) const {     // 只接受 format_context
        return std::format_to(ctx.out(), "{}", p.x);
    }
};

int main() {
    (void)std::format("{}", P{1});                 // OK
    (void)std::format("{}", std::vector<P>{{1}});  // error: P 不满足 formattable
}
```

¶2：`T` 与 `charT` **建模** `formattable` 还要求 `formatter<remove_cvref_t<T>, charT>` 满足 *BasicFormatter* 的语义要求，且当 `remove_reference_t<T>` 是 `const` 限定的时满足 *Formatter* 要求。

## 标准特化（[format.formatter.spec]）

### 启用与禁用（¶2、¶5–¶7）

每个 `formatter` 特化要么**启用**（enabled），要么**禁用**（disabled）。¶5：库和用户都没有提供特化的 `formatter<T, charT>` 是禁用的。¶7：禁用的特化**不可默认构造、不可复制/移动构造、不可复制/移动赋值**。

这一条的作用是让“能不能格式化”成为 SFINAE 友好的类型性质：`formattable` 要求 `semiregular<Formatter>`，禁用的特化不满足，于是概念求值为 `false` 而不是硬错误。libc++ 的实现方式很直接（`__format/formatter.h`）：主模板继承一个所有特殊成员都 `= delete` 的 `__disabled_formatter`。

¶2 列出的启用特化：

| 特化 | debug-enabled | constexpr-enabled |
|---|---|---|
| `formatter<char, char>`、`<char, wchar_t>`、`<wchar_t, wchar_t>` | ✓ | ✓ |
| 字符串：`charT*`、`const charT*`、`charT[N]`、`basic_string`、`basic_string_view` | ✓ | ✓ |
| 所有有符号/无符号整数类型和 `bool` | | ✓ |
| 所有 cv 非限定浮点类型 | | |
| `nullptr_t` | | ✓ |
| `void*`、`const void*` | | |

- ***debug-enabled***（[[g:debug-enabled-specialization]]）：额外提供 public、constexpr 的 `set_debug_format()`，效果等同于 type 为 `?`。范围和 tuple 的 formatter 靠它让元素默认以转义形式输出。
- ***constexpr-enabled***（[[g:constexpr-enabled-specialization]]）：`format` 成员是 `constexpr` 的。浮点与 `void*` 不在其列，所以编译期格式化浮点数不被要求支持。

¶4：`<format>` 还提供一组**显式禁用**的特化：`char` 字符串配 `wchar_t` 输出（`formatter<const char*, wchar_t>` 等）。注 1 说明理由：它们需要隐式的多字节/宽字符转换，库不替你做。

¶8 的标准例子展示了“继承现有 formatter”的惯用法，并指出 `std::format("{}", L"foo")`（宽字符串配窄输出）与未特化的用户类型都是错误。

### 锁定优化（[format.formatter.locking]、spec ¶3）{{c++26}}

```cpp
template<class T>
  constexpr bool enable_nonlocking_formatter_optimization = false;
```

这个变量模板服务于 `std::print`（[[print.fun]]）。`print` 有两种实现策略：

- **加锁直写**：锁住 `FILE*`，边格式化边写入流——不用中间缓冲区，快；
- **先缓冲再写**：先把结果格式化到一个临时字符串，再锁住流一次性写入。

直写的风险在于：在持锁期间会调用用户的 `formatter::format`，如果它自己又去打印到同一个流（死锁），或者执行时间很长（阻塞其他线程的输出），后果严重。[[P3107R5]] 的方案是：只有当所有实参类型的 `enable_nonlocking_formatter_optimization` 都为 `true` 时，`print` 才走 `vprint_unicode`/`vprint_nonunicode` 的直写路径，否则走 `*_buffered` 路径。

- spec ¶3：标准库为它提供 formatter 的每个类型 `T`，该变量都特化为 `true`（除非另有规定）。
- 范围类型的特化是 `false`（[format.syn]），因为元素的 formatter 可能是用户的；`pair`/`tuple` 是各元素该值的合取（[[format]]）。
- [format.formatter.locking] ¶1：用户**可以**为 cv 非限定的程序定义类型特化它，特化必须可用于常量表达式且类型为 `const bool`。只有在你的 `format` 不会重入 `print`、不会长时间阻塞时才应置为 `true`。

!!! impl
    libc++ 23 声明了该变量模板并为内建 formatter 特化为 `true`（`__format/formatter.h` 及各 `formatter_*.h`），但截至本文编写时 `<print>` 的实现并不引用它——两条路径的区分尚未落地。

## 转义格式化（[format.string.escaped]）{{c++23}}

`?` 类型（或 `set_debug_format()`）产生“适合调试和日志”的**转义字符串**（[[g:escaped-string]]）。¶2 的算法，以字符类型对应的编码 *CE* 解释输入：

1. 输出 `"`；
2. 对每个“编码一个字符 / 移位序列 / 非法码元序列”的片段 *X*：
    - 若是制表、换行、回车、`"`、`\`：输出 `\t`、`\n`、`\r`、`\"`、`\\`（表 114）；
    - 否则，若 *CE* 是 UTF 编码且字符的 General_Category 属于 Separator（Z）或 Other（C）——不可打印字符、控制字符、零宽连接符等——且不是空格：输出 `\u{十六进制}`；
    - 若字符具有 Grapheme_Extend=Yes（组合附加符号）且**前面没有一个原样输出的字符可以依附**：也输出 `\u{…}`；
    - 非 UTF 编码下，实现定义的一组分隔/不可打印字符同样转义；
    - 否则原样输出；
    - 移位序列的处理未指明；**非法码元**逐个输出为 `\x{十六进制}`；
3. 输出 `"`。

¶3：单个字符用 `'` 包围；字符 `'` 输出为 `\'`，而 `"` 原样输出。

Grapheme_Extend 那一条的意图：`"e\u0301"`（e + 组合锐音符）原样输出为 é，而一个**孤立**的组合符号（开头的 `\u0301`、或前面是被转义了的字符）会被转义，避免它“粘”到引号或反斜杠上造成误读。

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

## 解析上下文（[format.parse.ctx]）

`basic_format_parse_context<charT>` 持有：当前未解析的格式串范围 `[begin_, end_)`、编号模式（unknown/manual/automatic）、下一个自动编号、实参个数 `num_args_`。¶2：用户显式或偏特化它是 {{ifndr}}。

| 成员 | 作用 |
|---|---|
| `begin()`/`end()` | 当前 *format-spec* 起点与整个格式串终点 |
| `advance_to(it)` | ¶6 前置条件：`end()` 从 `it` 可达 |
| `next_arg_id()` | 自动编号取下一个下标；已处于手动模式则抛 `format_error`（¶9）；¶10：下标 ≥ `num_args_` 时调用不是核心常量表达式 |
| `check_arg_id(id)` | 进入手动模式；已处于自动模式则抛（¶12）；¶13：`id >= num_args_` 时不是核心常量表达式 |
| `check_dynamic_spec<Ts...>(id)` | {{c++26}} 要求第 `id` 个实参（归一化后）的类型属于 `Ts...`，否则不是核心常量表达式 |
| `check_dynamic_spec_integral` / `_string` | 上者的便捷形式 |

`next_arg_id`/`check_arg_id` 是自定义 formatter 支持**动态宽度**等“引用另一个实参”的语法时必须调用的：它们同时维护“不得混用编号”的不变量，并在编译期检查下标越界。`check_dynamic_spec` 则让用户 formatter 也能在编译期检查被引用实参的**类型**（标准 formatter 对动态宽度做的就是这件事）。

¶3 注 1 一个细节：公开构造函数把 `num_args_` 初始化为 0，所以**用户自己构造**的解析上下文上调用 `next_arg_id` 等永远不是核心常量表达式。库内部用的是能传入实参个数的构造方式（libc++ 在 `basic_format_string` 的构造函数里传入 `sizeof...(_Args)`）。

!!! impl
    截至本文编写时，libc++ 23 的 `basic_format_parse_context`（`__format/format_parse_context.h`）尚未提供 `check_dynamic_spec` 系列成员。

## 格式化上下文（[format.context]）

`basic_format_context<Out, charT>` 持有实参（`basic_format_args`）和输出迭代器：

- `arg(id)`：取第 `id` 个实参（越界得空 arg）；
- `locale()`：¶7，格式化函数给了 locale 就返回它，否则返回 `std::locale()`（全局 locale）；
- `out()`：¶8，**`return std::move(out_);`**——迭代器被移出，所以写完必须用返回值或 `advance_to` 放回；
- `advance_to(it)`：¶9，`out_ = std::move(it)`。

¶3：`Out` 必须建模 `output_iterator<const charT&>`。¶4：`format_context` 是某个“向 `string` 追加”的迭代器对应的特化，¶5 建议实现只提供**一个**这样的特化，用类型擦除的缓冲区统一处理 `string`、`vector` 等目标，从而避免为每种输出迭代器重复实例化。libc++ 的 `format_context` 就是 `basic_format_context<back_insert_iterator<__format::__output_buffer<char>>, char>`（`__format/buffer.h`），这也是上面 `formattable` 例子里诊断信息中出现的那个类型。

## 编写自定义 formatter

把前面各节的要求合起来：

1. `parse` 写成 `constexpr`——否则编译期检查无法执行，用到该类型的所有 `std::format("...")` 调用都会编译失败；
2. `parse` 遇到不认识的说明时 `throw std::format_error(...)`——在常量求值中这会使立即调用失败，从而把错误变成编译错误；
3. `format` 写成 `const` 成员函数**模板**，对上下文类型泛型；
4. 能复用就复用：继承一个现有 formatter，它的 `parse` 自动给你完整的 *std-format-spec* 支持。

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

// format 只读值、不重入 print，可以声明为免锁
template <>
constexpr bool std::enable_nonlocking_formatter_optimization<Point> = true;

enum class Color { red, green };

// 继承：复用 string_view 的全部格式说明（fill、align、width、precision……）
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
    assert(std::format("{}", std::vector{Point{1, 2}, Point{3, 4}}) == "[(1, 2), (3, 4)]");
    assert(std::format("{::p}", std::vector{Point{1, 2}}) == "[1 2]");   // 元素格式说明交给 Point
}
```

`std::format("{:z}", Point{1, 2})` 会在**编译期**报错：`parse` 在常量求值中执行了 `throw`。

## 范围格式化（[format.range]）{{c++23}}

[[P2286R8]] 让所有 `input_range` 默认可格式化（只要元素可格式化），[[P2585R1]] 改进了默认格式：map 输出 `{k: v}`，set 输出 `{a, b}`，字符序列可以按字符串输出。

```cpp
template<ranges::input_range R, class charT>
  requires (format_kind<R> != range_format::disabled) &&
           formattable<ranges::range_reference_t<R>, charT>
struct formatter<R, charT> : range-default-formatter<format_kind<R>, R, charT> { };
```

即：范围的 formatter 是一个**受约束的偏特化**，按 `format_kind<R>` 分派到四种仅用于说明的 *range-default-formatter*。

### `format_kind`：自动分类（[format.range.fmtkind]）

¶1：实例化 `format_kind` 的主模板（非范围类型）是非良构的。¶2 对 `input_range` 的分类规则：

1. 若 `remove_cvref_t<range_reference_t<R>>` 就是 `R` 本身 → `disabled`。注 1：防止约束递归——`filesystem::path` 是“元素为 `path` 的范围”，不排除的话 `formattable<path>` 要求 `formattable<path>`。
2. 否则若 `R::key_type` 有效：再若 `R::mapped_type` 有效且元素是 `pair` 或二元 `tuple` → `map`；否则 → `set`。
3. 否则 → `sequence`。

注意 `string` 与 `debug_string` 永远不会被自动选中——`std::string` 自己有专门的 formatter（[format.formatter.spec]），比范围偏特化更特化；而 `vector<char>` 默认按 `sequence` 输出为 `['h', 'i']`。¶3：用户可以为自己的范围类型特化 `format_kind`（必须是 `const range_format` 且可用于常量表达式），例如把自定义字符串类声明为 `range_format::string`。

### `range_formatter`（[format.range.formatter]）

¶2 的 *range-format-spec*：

```text
range-format-spec:  range-fill-and-align(opt) width(opt) n(opt) range-type(opt) range-underlying-spec(opt)
range-type:         m | s | ?s
range-underlying-spec:  : format-spec        ← 交给元素的 formatter
```

- *range-fill* 不能是 `{`、`}`、**`:`**（`:` 是元素说明的引导符）。
- `n`（¶5）：去掉外层括号。
- `m`（表 115）：元素须为二元 `pair`/`tuple`；括号变 `{}`，每个元素按 `m` 输出为 `k: v`。
- `s`/`?s`：元素须为 `charT`；按字符串 / 转义字符串输出；此时不能再有 `n` 或元素说明。
- ¶9：若没有元素说明且元素 formatter 是 debug-enabled 的，就调用其 `set_debug_format()`——所以 `vector<string>` 默认输出带引号：`["a", "b"]`。
- ¶11：输出为 开括号、元素（以分隔符隔开）、闭括号；默认分别是 `[`、`, `、`]`，可用 `set_brackets`/`set_separator` 修改。宽度和对齐作用于**整个**范围的输出。

### 四种默认格式（[format.range.fmtdef] 至 [format.range.fmtstr]）

| `format_kind` | 行为 | 例 |
|---|---|---|
| `sequence`（fmtdef） | 直接委托 `range_formatter` | `[1, 2, 3]` |
| `map`（fmtmap） | ¶1 *Mandates* 元素为二元 pair/tuple；括号 `{}`，元素的括号去掉、分隔符改为 `: ` | `{1: "x"}` |
| `set`（fmtset） | 括号改为 `{}` | `{1, 3}` |
| `string`/`debug_string`（fmtstr） | *Mandates* 元素就是 `charT`；先拷贝成 `basic_string<charT>` 再按字符串格式化；`debug_string` 额外调用 `set_debug_format()` | `hi` / `"hi"` |

*fmt-maybe-const*（[format.syn]）的作用：若 `const R` 也是元素可格式化的范围，就以 `const R&` 格式化，否则以 `R&`——与 [[P2418R2]] 对非 const 可迭代视图的支持一脉相承。

容器适配器（`stack`、`queue`、`priority_queue`）的格式化另见 [[container.adaptors.format]]。

```cpp run title="ranges.cpp" ok
#include <cassert>
#include <format>
#include <map>
#include <set>
#include <string>
#include <vector>

int main() {
    assert(std::format("{}", std::vector{1, 2, 3}) == "[1, 2, 3]");
    assert(std::format("{::#x}", std::vector{10, 11}) == "[0xa, 0xb]");    // 元素说明
    assert(std::format("{:n}", std::vector{1, 2}) == "1, 2");             // 去括号
    assert(std::format("{:*^11}", std::vector{1, 2}) == "**[1, 2]***");   // 宽度作用于整体
    assert(std::format("{}", std::vector<std::string>{"a", "b"}) == "[\"a\", \"b\"]");
    assert(std::format("{}", std::map<int, std::string>{{1, "x"}}) == "{1: \"x\"}");
    assert(std::format("{}", std::set{3, 1}) == "{1, 3}");
    assert(std::format("{}", std::vector{'h', 'i'}) == "['h', 'i']");
    assert(std::format("{:s}", std::vector{'h', 'i'}) == "hi");
    assert(std::format("{:?s}", std::vector{'h', '\n'}) == "\"h\\n\"");
    assert(std::format("{}", std::vector<std::vector<int>>{{1}, {2, 3}}) == "[[1], [2, 3]]");
}
```

## 常见误区

!!! pitfall "`format` 忘了 `const`"
    `formattable` 用 `const Formatter&` 调用 `format`。在 libc++ 中，`format` 不是 `const` 成员时连最简单的 `std::format("{}", t)` 都编译失败。永远把 `format` 声明为 `const`，需要可变状态就放进 `mutable` 成员（但通常意味着设计有问题）。

!!! pitfall "`parse` 不是 `constexpr`"
    编译期检查要在常量求值中调用 `parse`。非 `constexpr` 的 `parse` 会让每一个 `std::format("...", t)` 编译失败，只剩 `vformat`/`dynamic_format` 可用。

!!! pitfall "直接写 `ctx.out()` 却忘了返回"
    `out()` 把迭代器**移出**。手写输出时要 `auto it = ctx.out(); *it++ = 'x'; return it;`，返回的迭代器就是新的位置。

!!! pitfall "盲目开启免锁优化"
    若你的 `format` 内部调用了 `std::print` 到同一个流，或做了耗时 I/O，把 `enable_nonlocking_formatter_optimization` 置为 `true` 会在实现了直写路径的库上导致死锁或长时间持锁。

## 历史

- C++20：[[P0645R10]] 引入 formatter 机制；[[P2418R2]]（C++20 DR）区分 *BasicFormatter*/*Formatter*。
- C++23：[[P2286R8]] 范围、tuple 格式化，`?` 转义，`formattable` 概念，`range_formatter`；[[P2585R1]] 改进默认格式（map、set、字符串）。
- C++26：[[P3107R5]] 引入 `enable_nonlocking_formatter_optimization`，允许 `print` 高效实现；`check_dynamic_spec` 系列加入解析上下文。
- C++23 之后：constexpr-enabled 特化、各成员函数的 `constexpr` 化。

## 思考题

!!! question "1"
    为什么 `vector<bool>` 能被 `std::format` 格式化？它的 `range_reference_t` 是 `vector<bool>::reference`，不是 `bool`。

<details markdown="1">
<summary>展开查看答案与解析</summary>

范围偏特化要求 `formattable<range_reference_t<R>, charT>`，而 `vector<bool>::reference` 本身不是 `bool`。标准为此在 [[vector.bool.fmt]] 中专门提供了一个受约束的 formatter 偏特化（约束为“是 `vector<bool>` 的 reference 类型”），内部委托给 `formatter<bool>`。没有它，`format_kind` 虽然给出 `sequence`，`formattable` 约束却不满足，范围偏特化就不会被选中。
</details>

!!! question "2"
    `std::format("{}", std::filesystem::path("a/b"))` 会输出 `[a, b]` 吗？

<details markdown="1">
<summary>展开查看答案与解析</summary>

不会走范围格式化：`path` 的元素类型就是 `path`，[format.range.fmtkind] ¶2.1 使 `format_kind<path>` 为 `disabled`。C++26 为 `path` 提供了专门的 formatter（见 [[fs.path.fmtr]]），按路径字符串输出（可选 `?` 转义与 `g` 通用格式）；没有这个 formatter 的实现上，它就是不可格式化的。
</details>

## 小结

| 主题 | 规则 |
|---|---|
| 两个成员 | `parse`（编译期可运行）存选项；`format`（运行期）输出 |
| `formattable` | 要求 `semiregular` formatter、`const` 的 `format`、能接受未指明迭代器的上下文 |
| 禁用特化 | 特殊成员全部不可用 → `formattable` 为假（SFINAE 友好） |
| debug-enabled | 有 `set_debug_format()`；范围/tuple 对元素自动调用 |
| constexpr-enabled | 整数、`bool`、字符、字符串、`nullptr_t`；**不含**浮点与 `void*` |
| 转义 `?` | 引号包围；控制/不可打印字符 `\u{..}`，非法码元 `\x{..}` |
| 解析上下文 | `next_arg_id`/`check_arg_id` 维护编号不变量；`check_dynamic_spec` 编译期类型检查 |
| 免锁优化 | 默认 `false`；标准类型 `true`；范围 `false`；用户可特化 |
| 范围 | `format_kind` 分 map/set/sequence；`{:n}`、`{:m}`、`{:s}`、`{:?s}`、`{::元素说明}` |
