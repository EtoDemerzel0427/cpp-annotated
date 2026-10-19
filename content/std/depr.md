---
title: 兼容性特性（Annex D）
summary: 弃用在标准里的确切含义，以及当前草案 Annex D 中全部弃用特性的总表：弃用版本、Clang 23 / libc++ 的警告、替代写法。
status: done
covers: depr.general
related: diff, dcl.attr, intro.compliance, zombie.names
tags: 附录, 弃用, 兼容性, 迁移
updated: 2026-10-19
---

!!! tldr
    - 弃用（deprecated）的特性仍然是合法的 C++，实现必须支持；它只表示委员会把它列为将来删除的候选。
    - Annex D 是规范性附录。`std::rel_ops`、`std::iterator`、`is_pod` 等设施的规则只写在这里，正文里已经没有了。
    - 标准允许实现给弃用的库名字加 `[[deprecated]]`，这就是 `-Wdeprecated-declarations` 警告的来源；核心语言部分的警告是编译器自己加的。
    - 一个特性从 Annex D 删除时，会作为一条不兼容登记在 Annex C；删除后的库名字成为僵尸名，程序不得使用。
    - 下面的总表列出全部弃用特性，其中几项 Clang 不发出任何警告，只能靠搜索代码找出来。

## 弃用是什么意思 [depr.general]

`-std=c++20` 下写 `[=]` 并在 lambda 里使用成员，Clang 会警告隐式捕获 `this` 已弃用，但程序照样编译运行。弃用是标准里的一种正式状态，它的含义在 Annex D 开头定义。

¶1 Annex D 描述的是为了与现有实现兼容而规定的特性。

¶2 这些特性都是弃用的（[[g:deprecated]]），标准这样定义弃用：

!!! std
    Normative for the current revision of C++, but having been identified as a candidate for removal from future revisions.

前半句说弃用的特性与其他特性一样有规范效力。符合标准的实现必须接受使用它们的程序，并按规定的语义执行。后半句说它只是删除的候选：委员会可能删除它（`auto_ptr`、`register`、`throw()` 都是这样被删除的），也可能长期保留（`std::iterator` 从 C++17 弃用至今），还可能撤销一部分弃用（对 `volatile` 的复合赋值，见 [[depr.volatile.type]]）。

Annex D 与 Annex C [[diff]] 不同，它是规范性的，是正文的一部分。很多弃用特性的规则只写在这里，例如 `std::rel_ops` 的四个运算符模板、`std::iterator` 类模板、`is_pod` 的定义。

¶2 的最后一句允许实现给 Annex D 中描述的库名字和实体加上 `[[deprecated]]` 属性（[[dcl.attr]]）。libc++ 和 libstdc++ 正是这样做的，使用弃用的库设施会得到 `-Wdeprecated-declarations` 警告。核心语言的弃用特性没有对应的授权，但标准只规定什么时候必须诊断，从不禁止实现对良构程序发出额外的诊断（[[intro.compliance]]），所以编译器也会为它们加上警告。

!!! note "弃用不改变程序的合法性"
    使用弃用特性的程序仍然是良构的，加了 `-Werror` 而编译失败是用户自己的选择。特性被从 Annex D 删除时，使用它的程序才变成非良构，这一改动会作为一条不兼容登记在 Annex C，例如 [[diff.cpp23]] 的最后一节。

## 删除之后：僵尸名

库设施从 Annex D 删除后，它的名字不会就此可以随意使用。[[zombie.names]] 列出了曾经在标准库中出现、后来被删除的名字，如 `auto_ptr`、`bind1st`、`random_shuffle`、`strstream`、`codecvt_utf8`，称为僵尸名（[[g:zombie-name]]）。它们保留给以前的标准化使用：程序不能自己在 `std` 中声明 `auto_ptr`，而实现可以继续提供这些设施。所以有些标准库在新的语言模式下仍然提供已删除的设施，这并不违反标准。

## 总表

下表列出当前草案 Annex D 的全部条目。弃用自一栏只填确定的版本，拿不准的写"—"。警告一栏是 Clang 23.1.3 + libc++ 在 `-std=c++2c` 下的实测结果；"无"表示在 `-Wall -Wextra -Wdeprecated` 下都没有诊断。libc++ 对一些库特性只在较新的语言模式下加 `[[deprecated]]`，详见各子页面。

### 核心语言（[[depr.local]] 页）

| 条款 | 特性 | 弃用自 | Clang 23 警告 | 替代 |
|---|---|---|---|---|
| D.2 [depr.local] | 非 TU 局部实体的声明构成暴露，例如外部链接的函数返回无名命名空间中的类型 | C++20 | 无 | 把被暴露的实体移出无名命名空间，或让声明有内部链接 |
| D.3 [depr.capture.this] | `[=]` 隐式按引用捕获 `*this` | C++20 | `-Wdeprecated-this-capture`（默认开启） | `[=, this]` 或 `[=, *this]` |
| D.4 [depr.volatile.type] | `volatile` 对象的 `++`/`--`、使用对 `volatile` 赋值的结果、`volatile` 形参和返回类型、`volatile` 结构化绑定 | C++20 | `-Wdeprecated-volatile`（默认开启） | 显式读、改、写；去掉形参和返回类型上的 `volatile` |
| D.5 [depr.ellipsis.comma] | 省略号前没有逗号：`void f(int...)` | C++26 | `-Wdeprecated-missing-comma-variadic-parameter`（C++26 模式默认开启） | `void f(int, ...)` |
| D.6 [depr.impldec] | 有用户声明的析构函数或复制操作时，隐式定义复制构造函数或复制赋值运算符 | C++11 | `-Wdeprecated-copy`（`-Wextra`）；析构函数的情形要 `-Wdeprecated` | 显式 `= default`，或遵循三/五/零法则 |
| D.7 [depr.static.constexpr] | 在类外冗余地重新声明 `static constexpr` 数据成员 | C++17 | `-Wdeprecated-redundant-constexpr-static-def`（`-Wdeprecated`） | 删掉类外的声明 |
| D.8 [depr.lit] | `operator "" _x`：引号与后缀之间有空白 | C++23 | `-Wdeprecated-literal-operator`（默认开启） | `operator""_x` |
| D.9 [depr.template.template] | 类模板或别名模板的限定名前写 `template`，后面却没有模板实参列表 | — | 无 | 非依赖名去掉 `template`；依赖名在 Clang 上暂无替代写法 |

### 库：数值、C 兼容、类型特征与工具（[[depr.numeric.limits.has.denorm]] 页）

| 条款 | 特性 | 弃用自 | Clang 23 / libc++ 警告 | 替代 |
|---|---|---|---|---|
| D.10 [depr.numeric.limits.has.denorm] | `numeric_limits::has_denorm`、`has_denorm_loss`、`float_denorm_style` | C++23 | `-Wdeprecated-declarations`（C++23 起） | `numeric_limits<T>::denorm_min()`，或 `<cfloat>` 中的 `*_TRUE_MIN` |
| D.11 [depr.c.macros] | `FLT_HAS_SUBNORM` 等、`DECIMAL_DIG`、经 `<cmath>` 获得的 `INFINITY`/`NAN`、`__bool_true_false_are_defined` | — | 无 | `*_DECIMAL_DIG`；从 `<cfloat>` 取 `INFINITY`/`NAN` |
| D.12 [depr.cerrno] | `ENODATA`、`ENOSR`、`ENOSTR`、`ETIME` 及对应的 `errc` 枚举项 | — | 宏无；`errc` 枚举项有 `-Wdeprecated-declarations` | 这些是 POSIX 已删除的 STREAMS 错误码 |
| D.13 [depr.meta.types] | `is_trivial`、`is_pod`、`aligned_storage`、`aligned_union` | `is_pod` C++20；`aligned_*` C++23；`is_trivial` C++26 | `-Wdeprecated-declarations`（各自从对应模式起） | `is_trivially_copyable` 加 `is_trivially_default_constructible`；`is_standard_layout`；`alignas(A) std::byte buf[N]` |
| D.14 [depr.relops] | `std::rel_ops` | C++20 | `-Wdeprecated-declarations`（C++20 起） | `operator<=>` 与 `operator==` |
| D.15 [depr.tuple] | `tuple_size<volatile T>`、`tuple_element<I, volatile T>` 等 | C++20 | 无 | 先 `remove_volatile_t` |
| D.16 [depr.variant] | `variant_size<volatile T>`、`variant_alternative<I, volatile T>` 等 | C++20 | 无 | 同上 |
| D.17 [depr.vector.bool.swap] | 静态成员 `vector<bool>::swap(reference, reference)` | — | 无 | `swap(v[i], v[j])` |
| D.18 [depr.iterator] | `std::iterator` 基类模板 | C++17 | `-Wdeprecated-declarations`（C++17 起） | 直接写出五个成员类型别名 |
| D.19 [depr.move.iter.elem] | `move_iterator::operator->` | C++20 | `-Wdeprecated-declarations`（C++20 起） | `(*it).member` 或 `it.base()->member` |

### 库：本地化、格式化、时间、文件系统、iostream（[[depr.locale.category]] 页）

| 条款 | 特性 | 弃用自 | Clang 23 / libc++ 警告 | 替代 |
|---|---|---|---|---|
| D.20 [depr.locale.category] | `codecvt<char16_t, char>`、`codecvt<char32_t, char>` 及其 `char8_t` 版本，`codecvt_byname` 同类 | `char` 版本 C++20 | `-Wdeprecated-declarations`（C++20 起） | 第三方 Unicode 库 |
| D.21 [depr.format] | `visit_format_arg` | C++26 | `-Wdeprecated-declarations`（C++26 模式） | 成员函数 `basic_format_arg::visit` |
| D.22 [depr.ctime] | `asctime`、`ctime` | — | 无 | `std::format("{:%c}", tp)`、`strftime` |
| D.23.1 [depr.fs.path.factory] | `filesystem::u8path` | C++20 | `-Wdeprecated-declarations`（C++20 起） | `path(std::u8string_view)` 或 `path(u8"…")` |
| D.23.2 [depr.fs.path.obs] | 返回 `std::string` 的 `path::string()`、`generic_string()` | — | 无 | `native_encoded_string()`、`display_string()` 及其 `generic_` 版本（[[fs.class.path]]） |
| D.25 [depr.istream.extractors] | 向 `signed char`、`unsigned char` 及其数组提取 | — | 无 | 读入 `char` 后转换 |
| D.26 [depr.ostream.inserters] | 插入 `signed char`、`unsigned char` 及其指针 | — | 无 | `static_cast<char>(c)`；当数值输出时用 `+c` |

### 库：原子操作（[[depr.atomics]] 页）

| 条款 | 特性 | 弃用自 | Clang 23 / libc++ 警告 | 替代 |
|---|---|---|---|---|
| D.24.2 [depr.atomics.volatile] | 非免锁的 `volatile atomic<T>` 上的成员函数 | C++20 | 无 | 去掉 `volatile`，或确认 `is_always_lock_free` |
| D.24.3 [depr.atomics.nonmembers] | `atomic_init` | C++20 | `-Wdeprecated-declarations`（C++20 起） | 构造时初始化，或 `store(v, memory_order::relaxed)` |
| D.24.4 [depr.atomics.types.operations] | `ATOMIC_VAR_INIT` | C++20 | `-Wdeprecated-pragma`（C++20 起） | `std::atomic<int> v{5};` |
| D.24.5 [depr.atomics.order] | `memory_order::consume`、`memory_order_consume`、`kill_dependency` | C++26 | 无 | `memory_order::acquire`；删掉 `kill_dependency` |

## 清理弃用用法

在 Clang 下，`-Wdeprecated` 打开核心语言部分的大多数检查，库部分的 `-Wdeprecated-declarations` 默认就开着。表中标"无"的几项编译器查不出来，只能靠搜索代码。

弃用得越早，通常越接近删除。C++17 及以前弃用而至今未删的只有三项：隐式复制操作（C++11）、类外重新声明 `static constexpr` 成员（C++17）和 `std::iterator`（C++17）。前两项牵涉的代码太多，短期内不太可能删除。

替代写法大多在弃用的同一版本里就已经可用，改了之后对旧标准也兼容。例外是 `[=, this]`：它在 C++17 中非良构（Clang 作为扩展接受并警告）。需要同时支持 C++17 和 C++20 时，写不带默认捕获的显式列表，如 `[this, &x]`。

## 已经删除的弃用特性

下列特性曾在 Annex D 中，删除时登记在 Annex C 的对应小节：

| 删除于 | 特性 | 记录位置 |
|---|---|---|
| C++17 | `register`、`bool` 的 `++`、动态异常说明、三字符组、`auto_ptr`、`bind1st`/`bind2nd`、`ptr_fun`、`mem_fun`、`random_shuffle`、`unary_function`/`binary_function`、旧 iostreams 成员 | [[diff.cpp14]] |
| C++20 | `throw()`、`uncaught_exception`、`not1` 等可适配函数接口、`allocator` 的冗余成员、`raw_storage_iterator`、临时缓冲区、`shared_ptr::unique`、`is_literal_type`、`result_of`、`<ccomplex>` 等空的 C 头文件 | [[diff.cpp17]] |
| C++23 | 下标中的逗号表达式（改作多维下标） | [[diff.cpp20]] |
| C++26 | 枚举与浮点或其他枚举的混合运算、数组比较、`allocator::is_always_equal`、`shared_ptr` 的原子自由函数、`string::reserve()`、`<codecvt>`、`<strstream>`、`wstring_convert`/`wbuffer_convert` | [[diff.cpp23]] |
