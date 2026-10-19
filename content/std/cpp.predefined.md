---
title: 预定义宏名
summary: 实现必须预先定义的宏：__cplusplus、全部语言特性测试宏、__FILE__ 与 __LINE__、__DATE__ 与 __TIME__、__STDC_HOSTED__ 等；有条件定义的宏；以及程序不得重定义它们的规则。
status: done
related: cpp.cond, cpp.line, cpp.embed, basic.extended.fp, expr.new, intro.compliance, support.limits
tags: 预处理, 特性检测, 预定义宏
updated: 2026-10-19
---

!!! tldr
    - `__cplusplus` 表示语言版本，取值形如 `202302L`。比较时用 `>=`，不要用 `==`。
    - 表 22 的 `__cpp_xxx` 宏逐项报告语言特性，值是该特性最后一次修订的年月；检测具体特性比从版本号推断更可靠。库特性宏 `__cpp_lib_xxx` 在 `<version>` 里。
    - `__FILE__`、`__LINE__` 报告假定的位置，受 `#line` 影响，是仅有的两个在翻译单元中会变化的预定义宏。
    - 程序 `#define` 或 `#undef` 本节列出的任何宏，或者 `defined`，都是非良构的；实现自己的预定义宏必须使用保留名。

**预定义宏**是实现在翻译开始前就已经定义好的宏。它们是程序在预处理期了解编译环境的标准渠道：用的是哪一版标准，是不是宿主实现，支持哪些语言特性，`new` 保证多大的对齐。

## __cplusplus：语言版本（¶1.1）

```cpp run title="cplusplus.cpp" ok
#if __cplusplus >= 202302L
#  define CXX_VER 23
#elif __cplusplus >= 202002L
#  define CXX_VER 20
#else
#  define CXX_VER 17
#endif
static_assert(CXX_VER >= 17);
int main() {}
```

¶1.1 当前草案规定 `__cplusplus` 是整数字面量 `202603L`。注 1 说明，以后的修订会把它换成更大的值。历代取值如下：

| 标准 | `__cplusplus` |
|---|---|
| C++98 / C++03 | `199711L` |
| C++11 | `201103L` |
| C++14 | `201402L` |
| C++17 | `201703L` |
| C++20 | `202002L` |
| C++23 | `202302L` |
| 当前工作草案 | `202603L` |

值的形式是 `yyyymmL`，取自标准或草案定稿的年月。下一版标准正式发布之前，编译器使用一个临时值：本机 Clang 23 在 `-std=c++2c` 下定义为 `202400L`。

!!! pitfall "用 >= 比较，不要用 =="
    `#if __cplusplus == 201703L` 换到 C++20 编译器上就不成立了，应当写 `>=`。更好的做法是用下面的特性测试宏检测具体特性，因为实现可能只支持某一版标准的一部分特性。

!!! impl "MSVC 的 __cplusplus"
    为了兼容旧代码，MSVC 默认把 `__cplusplus` 定义为 `199711L`，不管 `/std:` 选的是哪一版，加上 `/Zc:__cplusplus` 才报告真实的值。它另外提供 `_MSVC_LANG` 表示实际的语言版本。这个默认行为不符合标准。

## 特性测试宏（¶1.2，表 22）

```cpp run title="feature-test.cpp" ok
#if __cpp_if_consteval >= 202106L
constexpr int f(int x) {
  if consteval { return x; } else { return -x; }
}
#else
constexpr int f(int x) { return x; }
#endif
static_assert(f(1) == 1);
int main() {}
```

¶1.2 表 22 列出的宏必须定义为表中对应的整数字面量。注 2 说明，以后的修订可能把这些值换成更大的值。

这些宏叫做**特性测试宏**（feature-test macro）。每个宏的值是引入或最近一次修改该特性的提案被采纳的年月，所以同一个宏会随着特性的扩充而增大。例如 `__cpp_constexpr` 从 C++11 的 `200704L` 一路增长到当前的 `202406L`，每放宽一次 `constexpr` 的限制就更新一次。用法总是与某个值比较 `>=`。

在 `#if` 中，没有定义的标识符会被替换为 0（[[cpp.cond#10]]）。所以在不支持 `if consteval` 的实现上，上面的 `#if` 也能正确地得到假，不必先写 `defined(...)`。

标准库的特性测试宏 `__cpp_lib_xxx` 不在本节，它们由库头文件定义，C++20 起汇集在 `<version>` 里（[[version.syn]]）。检测库特性之前要先包含 `<version>` 或相应的头文件，否则宏没有定义，在 `#if` 里被当作 0。

表 22 共有 78 个宏。下表是其中本机 Clang 23（`-std=c++2c`）的值与草案不同的项：

| 宏 | 草案值 | Clang 23 |
|---|---|---|
| `__cpp_concepts` | `202606L` | `202002` |
| `__cpp_consteval` | `202606L` | `202211L` |
| `__cpp_constexpr_exceptions` | `202411L` | 未定义 |
| `__cpp_constexpr_virtual_inheritance` | `202506L` | 未定义 |
| `__cpp_contracts` | `202606L` | 未定义 |
| `__cpp_deduction_guides` | `202207L` | `201703L` |
| `__cpp_designated_initializers` | `202606L` | `201707L` |
| `__cpp_expansion_statements` | `202506L` | 未定义 |
| `__cpp_impl_coroutine` | `202606L` | `201902L` |
| `__cpp_impl_reflection` | `202603L` | 未定义 |
| `__cpp_modules` | `201907L` | `1` |
| `__cpp_nontype_template_args` | `201911L` | `201411L` |
| `__cpp_pack_indexing` | `202606L` | `202311L` |
| `__cpp_pp_embed` | `202606L` | 未定义 |
| `__cpp_template_parameters` | `202502L` | 未定义 |
| `__cpp_trivial_union` | `202603L` | 未定义 |

没有定义的宏对应尚未实现的特性，例如反射、契约和展开语句。`__cpp_pp_embed` 是个例外：Clang 已经支持 `#embed`，但在 C++ 中把它当作扩展，也不支持标准的 `offset` 参数（[[cpp.embed]]）。值较小的宏表示只实现了特性的早期版本，例如 `__cpp_deduction_guides` 停在 C++17 的值，说明 C++20 对别名模板的类模板实参推导等扩展还没有完整实现。`__cpp_concepts` 的值缺少 `L` 后缀，`__cpp_modules` 的值 `1` 根本不是年月，表明 Clang 认为自己的模块支持还不完整。

草案里出现 `202603L`、`202606L` 这样的值，说明这些特性在 C++26 定稿之后又被修订过。

<details markdown="1"><summary>表 22 全部 78 个宏</summary>

| 宏 | 草案值 | Clang 23 |
|---|---|---|
| `__cpp_aggregate_bases` | `201603L` | `201603L` |
| `__cpp_aggregate_nsdmi` | `201304L` | `201304L` |
| `__cpp_aggregate_paren_init` | `201902L` | `201902L` |
| `__cpp_alias_templates` | `200704L` | `200704L` |
| `__cpp_aligned_new` | `201606L` | `201606L` |
| `__cpp_attributes` | `200809L` | `200809L` |
| `__cpp_auto_cast` | `202110L` | `202110L` |
| `__cpp_binary_literals` | `201304L` | `201304L` |
| `__cpp_capture_star_this` | `201603L` | `201603L` |
| `__cpp_char8_t` | `202207L` | `202207L` |
| `__cpp_concepts` | `202606L` | `202002` |
| `__cpp_conditional_explicit` | `201806L` | `201806L` |
| `__cpp_consteval` | `202606L` | `202211L` |
| `__cpp_constexpr` | `202406L` | `202406L` |
| `__cpp_constexpr_dynamic_alloc` | `201907L` | `201907L` |
| `__cpp_constexpr_exceptions` | `202411L` | 未定义 |
| `__cpp_constexpr_in_decltype` | `201711L` | `201711L` |
| `__cpp_constexpr_virtual_inheritance` | `202506L` | 未定义 |
| `__cpp_constinit` | `201907L` | `201907L` |
| `__cpp_contracts` | `202606L` | 未定义 |
| `__cpp_decltype` | `200707L` | `200707L` |
| `__cpp_decltype_auto` | `201304L` | `201304L` |
| `__cpp_deduction_guides` | `202207L` | `201703L` |
| `__cpp_delegating_constructors` | `200604L` | `200604L` |
| `__cpp_deleted_function` | `202403L` | `202403L` |
| `__cpp_designated_initializers` | `202606L` | `201707L` |
| `__cpp_enumerator_attributes` | `201411L` | `201411L` |
| `__cpp_expansion_statements` | `202506L` | 未定义 |
| `__cpp_explicit_this_parameter` | `202110L` | `202110L` |
| `__cpp_fold_expressions` | `201603L` | `201603L` |
| `__cpp_generic_lambdas` | `201707L` | `201707L` |
| `__cpp_guaranteed_copy_elision` | `201606L` | `201606L` |
| `__cpp_hex_float` | `201603L` | `201603L` |
| `__cpp_if_consteval` | `202106L` | `202106L` |
| `__cpp_if_constexpr` | `201606L` | `201606L` |
| `__cpp_impl_coroutine` | `202606L` | `201902L` |
| `__cpp_impl_destroying_delete` | `201806L` | `201806L` |
| `__cpp_impl_reflection` | `202603L` | 未定义 |
| `__cpp_impl_three_way_comparison` | `201907L` | `201907L` |
| `__cpp_implicit_move` | `202207L` | `202207L` |
| `__cpp_inheriting_constructors` | `201511L` | `201511L` |
| `__cpp_init_captures` | `201803L` | `201803L` |
| `__cpp_initializer_lists` | `200806L` | `200806L` |
| `__cpp_inline_variables` | `201606L` | `201606L` |
| `__cpp_lambdas` | `200907L` | `200907L` |
| `__cpp_modules` | `201907L` | `1` |
| `__cpp_multidimensional_subscript` | `202211L` | `202211L` |
| `__cpp_named_character_escapes` | `202606L` | `202606L` |
| `__cpp_namespace_attributes` | `201411L` | `201411L` |
| `__cpp_noexcept_function_type` | `201510L` | `201510L` |
| `__cpp_nontype_template_args` | `201911L` | `201411L` |
| `__cpp_nontype_template_parameter_auto` | `201606L` | `201606L` |
| `__cpp_nsdmi` | `200809L` | `200809L` |
| `__cpp_pack_indexing` | `202606L` | `202311L` |
| `__cpp_placeholder_variables` | `202306L` | `202306L` |
| `__cpp_pp_embed` | `202606L` | 未定义 |
| `__cpp_range_based_for` | `202211L` | `202211L` |
| `__cpp_raw_strings` | `200710L` | `200710L` |
| `__cpp_ref_qualifiers` | `200710L` | `200710L` |
| `__cpp_return_type_deduction` | `201304L` | `201304L` |
| `__cpp_rvalue_references` | `200610L` | `200610L` |
| `__cpp_size_t_suffix` | `202011L` | `202011L` |
| `__cpp_sized_deallocation` | `201309L` | `201309L` |
| `__cpp_static_assert` | `202306L` | `202306L` |
| `__cpp_static_call_operator` | `202207L` | `202207L` |
| `__cpp_structured_bindings` | `202411L` | `202411L` |
| `__cpp_template_parameters` | `202502L` | 未定义 |
| `__cpp_template_template_args` | `201611L` | `201611L` |
| `__cpp_threadsafe_static_init` | `200806L` | `200806L` |
| `__cpp_trivial_union` | `202603L` | 未定义 |
| `__cpp_unicode_characters` | `200704L` | `200704L` |
| `__cpp_unicode_literals` | `200710L` | `200710L` |
| `__cpp_user_defined_literals` | `200809L` | `200809L` |
| `__cpp_using_enum` | `201907L` | `201907L` |
| `__cpp_variable_templates` | `201304L` | `201304L` |
| `__cpp_variadic_friend` | `202403L` | `202403L` |
| `__cpp_variadic_templates` | `200704L` | `200704L` |
| `__cpp_variadic_using` | `201611L` | `201611L` |
</details>

## __FILE__ 与 __LINE__：当前位置（¶1.4、¶1.5）

```cpp run title="unique-name.cpp" ok
#define CAT_(a, b) a##b
#define CAT(a, b) CAT_(a, b)
#define UNIQUE(name) CAT(name, __LINE__)
int UNIQUE(tmp) = 1;   // int tmp4 = 1;
int UNIQUE(tmp) = 2;   // int tmp5 = 2;
int main() { return tmp4 + tmp5 - 3; }
```

¶1.4 `__FILE__` 是表示当前源文件**假定名字**的字符串字面量。¶1.5 `__LINE__` 是整数字面量 `0` 或一个十进制整数字面量，表示当前源行在当前源文件中的**假定行号**。两者都可以由 `#line` 改变（注 3、注 4，[[cpp.line]]）。

`__LINE__` 不含数字分隔符，也不含整数后缀。所以它可以安全地用 `##` 拼进标识符，如上面的 `tmp4`，也可以字符串化。`CAT` 必须写两层：`##` 的操作数不会先展开（[[cpp.concat#2]]），只写一层会拼出 `tmp__LINE__`。

¶3 除了 `__FILE__` 和 `__LINE__`，预定义宏的值在整个翻译单元中保持不变。所以即使翻译跨过了午夜，`__DATE__` 也不会变。

在函数里需要调用者的位置时，C++20 起更推荐 `std::source_location::current()`（[[support.srcloc]]）。它作为默认实参时在调用点求值，而 `__LINE__` 只能取宏展开处的行号。

## __DATE__ 与 __TIME__：翻译时间（¶1.3、¶1.9）

¶1.3 `__DATE__` 是源文件的翻译日期，形如 `"Mmm dd yyyy"` 的字符串字面量。月份名与 `asctime` 生成的相同；日期小于 10 时，`dd` 的第一个字符是空格，如 `"Jan  1 1970"`。

¶1.9 `__TIME__` 是翻译时间，形如 `"hh:mm:ss"`。日期或时间拿不到时，实现必须给出一个实现定义的有效值。

!!! impl "可复现构建"
    这两个宏让每次编译的产物都不一样，破坏可复现构建（reproducible builds）。GCC 和 Clang 都支持环境变量 `SOURCE_DATE_EPOCH`，设置后这两个宏取该时间戳对应的值。本机 Clang 23 在 `SOURCE_DATE_EPOCH=0` 下得到 `"Jan  1 1970"` 和 `"00:00:00"`。`-Wdate-time` 会对使用它们的地方给出警告。

## 描述实现的宏（¶1.6–¶1.8）

¶1.7 `__STDC_HOSTED__` 在宿主实现中是 `1`，在独立实现中是 `0`。独立实现可以在没有操作系统的环境下运行，标准库只要求提供一个子集（[[intro.compliance]]）。本机 Clang 23 默认是 1，加 `-ffreestanding` 后是 0。

```cpp
#if __STDC_HOSTED__
#  include <iostream>   // 独立实现不保证提供 <iostream>
#endif
```

¶1.8 `__STDCPP_DEFAULT_NEW_ALIGNMENT__` 是 `std::size_t` 类型的整数字面量，值为 `operator new(std::size_t)` 和 `operator new[](std::size_t)` 保证的对齐。注 6 补充，对齐要求更大的类型，`new` 表达式会调用 `operator new(std::size_t, std::align_val_t)` 等重载（[[expr.new]]）。

这个宏随 C++17 的对齐 `new`（[[P0035R4]]）一起引入，它给出了超对齐的分界线：对齐要求超过这个值的类型，`new` 会走 `align_val_t` 重载。本机 Clang 23（arm64 macOS）定义为 `16UL`，`UL` 后缀使它的类型是 `unsigned long`，在这个平台上就是 `std::size_t`。

```cpp run title="new-align.cpp" ok
#include <cstddef>
#include <new>
struct alignas(64) CacheLine { char data[64]; };
int main() {
  // 64 大于 __STDCPP_DEFAULT_NEW_ALIGNMENT__（通常是 16），
  // 所以 new 调用 operator new(size_t, align_val_t)
  CacheLine* p = new CacheLine;
  bool ok = reinterpret_cast<std::size_t>(p) % 64 == 0;
  delete p;
  return ok ? 0 : 1;
}
```

¶1.6 {{c++26}} `__STDC_EMBED_NOT_FOUND__`、`__STDC_EMBED_FOUND__`、`__STDC_EMBED_EMPTY__` 分别是 `0`、`1`、`2`。注 5 说明，它们是 `__has_embed` 表达式可能得到的值（[[cpp.cond]]）。

## 有条件定义的宏（¶2）

¶2 下面这些宏由实现视情况定义：

| 宏 | 条件与取值 |
|---|---|
| `__STDCPP_FLOAT16_T__` | 当且仅当支持 ISO/IEC 60559 binary16 作为扩展浮点类型时定义为 1，对应 `std::float16_t` |
| `__STDCPP_FLOAT32_T__` | 同上，binary32，对应 `std::float32_t` |
| `__STDCPP_FLOAT64_T__` | 同上，binary64，对应 `std::float64_t` |
| `__STDCPP_FLOAT128_T__` | 同上，binary128，对应 `std::float128_t` |
| `__STDCPP_BFLOAT16_T__` | 当且仅当支持具有 `std::bfloat16_t` 性质的扩展浮点类型时定义为 1 |
| `__STDC__` | 是否定义、值是多少，都由实现定义 |
| `__STDC_MB_MIGHT_NEQ_WC__` | 定义为 1 时表示：基本字符集的成员在 `wchar_t` 编码中的码值，不一定等于它作为普通字符字面量时的值 |
| `__STDC_VERSION__` | 是否定义、值是多少，都由实现定义 |
| `__STDC_ISO_10646__` | 形如 `yyyymmL`；是否定义、值是多少，都由实现定义 |
| `__STDCPP_THREADS__` | 当且仅当程序可以有多个执行线程时定义为 1 |

扩展浮点类型的五个宏来自 C++23 的 [[P1467R9]]（见 [[basic.extended.fp]]）。条件是当且仅当，所以宏有定义就保证编译器支持对应的类型。

```cpp run title="float16.cpp" ok
#if defined(__STDCPP_FLOAT16_T__) && __has_include(<stdfloat>)
#  include <stdfloat>
using half = std::float16_t;
#else
using half = float;   // 回退
#endif
int main() { half h = 1; return static_cast<int>(h) - 1; }
```

宏由编译器预定义，而别名 `std::float16_t` 由库头文件 `<stdfloat>` 提供，两者可能不同步，所以这里同时检查。本机 Clang 23 没有定义这五个宏，搭配的 libc++ 也没有 `<stdfloat>`。

`__STDC__` 在 C 中表示实现符合 C 标准；在 C++ 中，它是否存在、值是多少都由实现定义。GCC 和 Clang 定义为 1，MSVC 默认不定义。要区分 C 和 C++，应当检查 `__cplusplus`。

本机 Clang 23（arm64 macOS）上，`__STDCPP_THREADS__` 和 `__STDC__` 都是 1，`__STDC_VERSION__` 和 `__STDC_ISO_10646__` 没有定义。在 Linux 上，`__STDC_ISO_10646__` 通常由 glibc 自动预包含的 `<stdc-predef.h>` 定义。

## 不得重定义（¶4）

```cpp title="redefine-predefined.cpp" error
#define __cplusplus 201103L    // error: 本节的预定义宏
#undef __FILE__                // error
#define __cpp_concepts 1       // error: 特性测试宏也属于本节
#define defined                // error: defined
```

¶4 如果本节列出的任何预定义宏名，或者标识符 `defined`，出现在 `#define` 或 `#undef` 中，程序非良构。C++23 及以前，这种情况是未定义行为。本机 Clang 23 对前三行只给出 `-Wbuiltin-macro-redefined` 警告，对 `#define defined` 报错。

¶4 第二句要求，实现自己的其他预定义宏必须以下划线加大写字母或两个下划线开头，也就是落在保留标识符的范围内（[[lex.name]]），不会与用户的名字冲突。GCC 在 GNU 模式下预定义的 `linux`、`unix` 不符合这一条，所以在 `-std=c++20` 这类严格模式下，GCC 不定义它们。

## 历史与演进

!!! history
    - C++98 有 `__cplusplus`（`199711L`）、`__DATE__`、`__FILE__`、`__LINE__`、`__TIME__`，`__STDC__` 由实现定义。早期 GCC 曾长期把 `__cplusplus` 定义为 1，所以老代码里的版本检测并不可靠。
    - C++11 加入 `__STDC_HOSTED__`、`__STDCPP_THREADS__`，以及与 C99 同步的 `__STDC_MB_MIGHT_NEQ_WC__`、`__STDC_VERSION__`、`__STDC_ISO_10646__`。
    - C++17 加入 `__STDCPP_DEFAULT_NEW_ALIGNMENT__`（[[P0035R4]]）。
    - C++20 把特性测试宏从委员会的非规范性文档 SD-6 搬进标准正文（[[P0941R2]]）。
    - C++23 加入扩展浮点类型的五个宏（[[P1467R9]]）。
    - C++26 加入 `__STDC_EMBED_*__` 和 `__cpp_pp_embed`（[[P1967R14]]）。
    - C++23 之后的新措辞把重定义预定义宏从未定义行为改为非良构。

## 思考题

!!! question "思考题 1"
    为什么特性测试宏的值是年月，而不是简单的 0 和 1？举一个只检查 `defined(__cpp_xxx)` 会出错的例子。

<details markdown="1">
<summary>答案</summary>

因为同一个特性会被多次扩充，年月值让代码能区分具体是哪一版。以 `__cpp_constexpr` 为例：C++11 是 `200704L`，那时 `constexpr` 函数只能有一条 `return` 语句；C++14 放宽为 `201304L`；C++20 允许 `constexpr` 虚函数，值至少是 `201907L`。

如果代码依赖 `constexpr` 虚函数，只检查 `defined(__cpp_constexpr)`，在只支持 C++11 的编译器上也为真，编译就会失败。应当写 `#if __cpp_constexpr >= 201907L`。
</details>

!!! question "思考题 2"
    `__LINE__` 规定为不含数字分隔符、不含整数后缀的十进制整数字面量。如果它可以展开为 `1'234` 或 `1234u`，哪些常见写法会出问题？

<details markdown="1">
<summary>答案</summary>

最直接的是 `##` 拼接。`CAT(var_, __LINE__)` 应当得到标识符 `var_1234`，而 `var_1'234` 根本拼不成一个合法的预处理记号。

另一个是 `#line __LINE__` 这样的写法：宏替换之后必须是数字序列（[[cpp.line#3]]），`1'234` 和 `1234u` 都不符合。把形式固定下来，这些惯用法才能移植。
</details>
