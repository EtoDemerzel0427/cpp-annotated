---
title: 兼容性特性（Annex D）
summary: 规范性附录 Annex D 收录"仍然有效、但已被列为删除候选"的特性。本页讲清"弃用"在标准里的确切含义、它与 Annex C 的关系、实现可以做什么，并给出全部 25 项弃用特性的总表：弃用版本、Clang 23 / libc++ 实测的警告标志、替代写法。逐项解析分布在四个子页面。
status: draft
covers: depr.general
related: diff, dcl.attr, intro.compliance, zombie.names
tags: 附录, 弃用, 兼容性, 迁移
updated: 2026-10-18
---

Annex D（Compatibility features，兼容性特性）是标准里的"待拆除区"。这里的每一项都还是合法的 C++，编译器必须按规定支持；但委员会已经表态：它们将来可能被删除，新代码不该再用。

和 [[diff]]（Annex C）、[[ub]]（Annex F）不同，Annex D 是**规范性**（normative）的。它不是对正文的摘要，而是正文的一部分：很多弃用特性的规则**只写在这里**。例如 `std::rel_ops` 的四个运算符模板、`std::iterator` 类模板、`is_pod` 的定义，正文里已经找不到了，Annex D 就是它们唯一的规范来源。

## "弃用"是什么意思（D.1 [depr.general]）

¶1 本附录描述的是为了与现有实现兼容而规定的特性。

¶2 这些特性是**已弃用**的（[[g:deprecated]]）。标准给 *deprecated* 下的定义是：

!!! std
    Normative for the current revision of C++, but having been identified as a candidate for removal from future revisions.

    在当前版本中具有规范效力，但已被认定为将来版本中删除的候选。

拆开来看：

- **"规范效力"**：弃用的特性与其他特性一样受标准约束。符合标准的实现必须接受使用它们的程序，并按规定的语义执行。`-std=c++20` 下 `[=]` 隐式捕获 `this` 仍然有效，编译器不能拒绝。
- **"删除候选"**：只是候选。委员会可能删除它（`auto_ptr`、`register`、`throw()` 都是这样走完全程的），也可能长期保留（`std::iterator` 从 C++17 弃用至今仍在），甚至部分撤销弃用（C++20 弃用了 `volatile` 左值上的复合赋值，C++23 撤销了其中按位复合赋值 `|=`、`&=`、`^=` 的弃用；当前草案中，只要赋值的结果不被使用，对 `volatile` 的任何赋值都不再弃用，见 [[depr.local|核心语言弃用特性]]中 D.4 一节）。
- **实现可以做什么**：¶2 的第二句允许实现给本附录描述的**库名字和实体**加上 `[[deprecated]]` 属性（[[dcl.attr]]）。这就是 libc++ 和 libstdc++ 在使用弃用库设施时发出 `-Wdeprecated-declarations` 警告的依据。对于核心语言的弃用特性，标准没有专门授权；但标准从不禁止实现对良构程序发出额外的诊断（[[intro.compliance]] 只规定什么时候**必须**诊断），所以编译器也会为它们加警告。

!!! note "弃用不改变程序的合法性"
    "被警告"不等于"非良构"。一个使用弃用特性的程序仍然是良构的，`-Werror` 让它编译失败是用户自己的选择，与标准无关。反过来，一个特性从 Annex D 被删除的那一刻，用它的程序才变成非良构，这一变化会作为一条不兼容登记在 Annex C 里（例如 [[diff.cpp23]] 的最后一节）。

## 删除之后：僵尸名

库设施从 Annex D 删除后，它的名字并不是简单地"消失"。[[zombie.names]] 列出了历史上曾经在标准库中出现、后来被删除的名字（`auto_ptr`、`bind1st`、`random_shuffle`、`strstream`、`codecvt_utf8` 等），称为**僵尸名**（[[g:zombie-name]]）：程序不得以任何方式使用它们（例如不能自己在 `std` 里定义一个 `auto_ptr`），而实现**可以继续提供**它们。这就是为什么有些标准库在新模式下仍然提供已删除的设施，而这并不违反标准。

## 总表

下表列出当前草案 Annex D 的全部条目。

- **弃用自**：该特性首次进入 Annex D 的版本。只填我们确定的；拿不准的写"—"。
- **Clang 23 警告**：在 Clang 23.1.3 + libc++ 上实测得到的警告标志及其开启条件。"无"表示在 `-Wall -Wextra -Wdeprecated` 下都没有任何诊断。
- 库特性的实测使用 `-std=c++2c`；libc++ 对部分特性只在较新的语言模式下加 `[[deprecated]]`，详见各子页面。

### 核心语言 · [[depr.local]] 页

| 条款 | 特性 | 弃用自 | Clang 23 警告 | 替代 |
|---|---|---|---|---|
| D.2 [depr.local] | 非 TU 局部的声明构成暴露（例如外部链接的函数返回无名命名空间里的类型） | C++20 | 无 | 把被暴露的实体移出无名命名空间，或把声明改为内部链接 |
| D.3 [depr.capture.this] | `[=]` 隐式按引用捕获 `*this` | C++20 | `-Wdeprecated-this-capture`（默认开启） | `[=, this]` 或 `[=, *this]` |
| D.4 [depr.volatile.type] | `volatile` 的 `++`/`--`、使用 `volatile` 赋值的结果、`volatile` 形参/返回类型、`volatile` 结构化绑定 | C++20 | `-Wdeprecated-volatile`（默认开启） | 显式读、改、写；去掉形参和返回类型上的 `volatile` |
| D.5 [depr.ellipsis.comma] | 省略号前没有逗号：`void f(int...)` | C++26 | `-Wdeprecated-missing-comma-variadic-parameter`（C++26 模式默认开启） | `void f(int, ...)` |
| D.6 [depr.impldec] | 有用户声明的析构函数或复制操作时，隐式定义复制构造/复制赋值 | C++11 | `-Wdeprecated-copy`（`-Wextra`）；`-Wdeprecated-copy-with-dtor` 等（`-Wdeprecated`） | 显式 `= default` 或遵循"三/五法则" |
| D.7 [depr.static.constexpr] | 类外冗余地重声明 `static constexpr` 数据成员 | C++17 | `-Wdeprecated-redundant-constexpr-static-def`（`-Wdeprecated`） | 删掉类外的声明 |
| D.8 [depr.lit] | `operator "" _x`（引号与标识符之间有空格） | C++23 | `-Wdeprecated-literal-operator`（默认开启） | `operator""_x` |
| D.9 [depr.template.template] | `N::template V` 这种无模板实参列表的 `template` 前缀（依赖名也算） | — | 无 | 非依赖名去掉 `template`；依赖名目前没有可用的替代写法 |

### 库 · 数值、C 兼容、类型特征与工具 · [[depr.numeric.limits.has.denorm]] 页

| 条款 | 特性 | 弃用自 | Clang 23 / libc++ 警告 | 替代 |
|---|---|---|---|---|
| D.10 [depr.numeric.limits.has.denorm] | `numeric_limits::has_denorm`、`has_denorm_loss`、`float_denorm_style` | C++23 | `-Wdeprecated-declarations`（C++23 起） | `std::numeric_limits<T>::denorm_min()` 等，或直接查 `<cfloat>` 中的 `*_TRUE_MIN` |
| D.11 [depr.c.macros] | `FLT_HAS_SUBNORM` 等、`DECIMAL_DIG`、经 `<cmath>` 获得的 `INFINITY`/`NAN`、`__bool_true_false_are_defined` | — | 无 | `*_DECIMAL_DIG`；包含 `<cfloat>` 取 `INFINITY`/`NAN`；不需要 `__bool_true_false_are_defined` |
| D.12 [depr.cerrno] | `ENODATA`、`ENOSR`、`ENOSTR`、`ETIME` 及对应的 `errc` 枚举项 | — | 宏无；`errc` 枚举项有 `-Wdeprecated-declarations`（libc++ 在所有模式下） | 这些是 POSIX STREAMS 的错误码，POSIX 已删除 |
| D.13 [depr.meta.types] | `is_trivial`、`is_pod`、`aligned_storage`、`aligned_union` | `is_pod` C++20；`aligned_*` C++23；`is_trivial` C++26 | `-Wdeprecated-declarations`（libc++ 分别在对应模式起） | `is_trivially_copyable` + `is_trivially_default_constructible`；`is_standard_layout`；`alignas(A) std::byte buf[N]` |
| D.14 [depr.relops] | `std::rel_ops` | C++20 | `-Wdeprecated-declarations`（C++20 起） | `operator<=>` 与 `operator==`（改写候选） |
| D.15 [depr.tuple] | `tuple_size<volatile T>`、`tuple_element<I, volatile T>` 等 | C++20 | 无 | 先 `remove_volatile_t` |
| D.16 [depr.variant] | `variant_size<volatile T>`、`variant_alternative<I, volatile T>` 等 | C++20 | 无 | 同上 |
| D.17 [depr.vector.bool.swap] | 静态成员 `vector<bool>::swap(reference, reference)` | — | 无 | `swap(v[i], v[j])`（经 ADL 找到 `reference` 的友元 `swap`） |
| D.18 [depr.iterator] | `std::iterator` 基类模板 | C++17 | `-Wdeprecated-declarations`（C++17 起） | 直接写五个成员类型别名 |
| D.19 [depr.move.iter.elem] | `move_iterator::operator->` | C++20 | `-Wdeprecated-declarations`（C++20 起） | `(*it).member` 或 `it.base()->member` |

### 库 · 本地化、格式化、时间、文件系统、iostream · [[depr.locale.category]] 页

| 条款 | 特性 | 弃用自 | Clang 23 / libc++ 警告 | 替代 |
|---|---|---|---|---|
| D.20 [depr.locale.category] | `codecvt<char16_t, char>`、`codecvt<char32_t, char>` 及其 `char8_t` 版本、`codecvt_byname` 同类 | `char` 版本 C++20 | `-Wdeprecated-declarations`（C++20 起） | 第三方 Unicode 库；C++26 起 `<text_encoding>` 只解决识别编码 |
| D.21 [depr.format] | `visit_format_arg` | C++26 | `-Wdeprecated-declarations`（C++26 模式） | `basic_format_arg::visit` 成员 |
| D.22 [depr.ctime] | `asctime`、`ctime` | — | 无 | `std::format("{:%c}", tp)`、`strftime` |
| D.23.1 [depr.fs.path.factory] | `filesystem::u8path` | C++20 | `-Wdeprecated-declarations`（C++20 起） | `path(std::u8string_view)` 或 `path(u8"…")` |
| D.23.2 [depr.fs.path.obs] | 返回 `std::string` 的 `path::string()` / `generic_string()` | — | 无 | `native_encoded_string()`、`display_string()` 及其 `generic_` 版本（见正文 [[fs.class.path]]） |
| D.25 [depr.istream.extractors] | 向 `signed char` / `unsigned char`（及其数组）提取 | — | 无 | 读入 `char` 后转换 |
| D.26 [depr.ostream.inserters] | 插入 `signed char` / `unsigned char`（及其指针） | — | 无 | `static_cast<char>(c)`；数值用 `+c` 或 `int(c)` |

### 库 · 原子操作 · [[depr.atomics]] 页

| 条款 | 特性 | 弃用自 | Clang 23 / libc++ 警告 | 替代 |
|---|---|---|---|---|
| D.24.2 [depr.atomics.volatile] | 非免锁 `atomic<T>` 上的 `volatile` 成员函数 | C++20 | 无 | 去掉 `volatile`，或确认 `is_always_lock_free` |
| D.24.3 [depr.atomics.nonmembers] | `atomic_init` | C++20 | `-Wdeprecated-declarations`（C++20 起） | 构造时初始化，或 `store(v, memory_order::relaxed)` |
| D.24.4 [depr.atomics.types.operations] | `ATOMIC_VAR_INIT` | C++20 | `-Wdeprecated-pragma`（C++20 起，宏弃用） | `std::atomic<int> v{5};` |
| D.24.5 [depr.atomics.order] | `memory_order::consume`、`memory_order_consume`、`kill_dependency` | C++26 | 无 | `memory_order::acquire`；删掉 `kill_dependency` |

## 怎么用这张表

1. **找出自己代码里的弃用用法**：Clang 下 `-Wdeprecated` 打开核心语言部分的大多数检查；库部分默认就会报 `-Wdeprecated-declarations`。上表中标"无"的几项编译器查不出来，只能靠搜索。
2. **判断紧迫性**：弃用时间越早，通常越接近删除。C++17 及以前弃用而至今未删的只有三项：隐式复制操作（C++11）、类外重声明 `static constexpr` 成员（C++17）和 `std::iterator`（C++17）；前两项牵涉的代码太多，短期内不太可能删除。
3. **改写**：替代写法基本都是在弃用的同一版本里就已经可用的，改了之后对旧标准也兼容。例外是 `[=, this]`：它在 C++17 中是非良构的（Clang 作为扩展接受并警告），需要同时支持 C++17 和 C++20 时，写显式捕获列表 `[this, &x]` 或 `[this, x]`。

## 历史上从 Annex D 删除的特性

这些特性现在已经不在 Annex D 里了，而是以"删除"的形式登记在 Annex C：

| 删除于 | 特性 | 记录位置 |
|---|---|---|
| C++17 | `register`、`bool` 的 `++`、动态异常说明、三字符组、`auto_ptr`、`bind1st`/`bind2nd`、`ptr_fun`、`mem_fun`、`random_shuffle`、`unary_function`/`binary_function`、旧 iostreams 成员 | [[diff.cpp14]] |
| C++20 | `throw()`、`uncaught_exception`、可适配函数 API（`not1` 等）、`allocator` 的冗余成员、`raw_storage_iterator`、临时缓冲区、`shared_ptr::unique`、`is_literal_type`、`result_of`、`<ccomplex>` 等空 C 头文件 | [[diff.cpp17]] |
| C++23 | 下标中的逗号表达式（改作多维下标） | [[diff.cpp20]] |
| C++26 | 枚举与浮点/其他枚举的混合运算、数组比较、`allocator::is_always_equal`、`shared_ptr` 的原子自由函数、`string::reserve()`、`<codecvt>`、`<strstream>`、`wstring_convert`/`wbuffer_convert` | [[diff.cpp23]] |
