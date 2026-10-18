---
title: 预定义宏名
summary: 实现必须预定义的宏（__cplusplus 及其历代取值、__FILE__/__LINE__/__DATE__/__TIME__、__STDC_HOSTED__、__STDCPP_DEFAULT_NEW_ALIGNMENT__、__STDC_EMBED_*__ 与全部语言特性测试宏 __cpp_xxx），有条件预定义的宏（扩展浮点类型、__STDCPP_THREADS__、__STDC__ 系列），以及"不得重定义"的规则。
status: draft
related: cpp.cond, cpp.line, cpp.embed, basic.extended.fp, expr.new, intro.compliance, support.limits
tags: 预处理, 特性检测, 预定义宏
updated: 2026-10-18
---

预定义宏是实现在翻译开始时就"已经 `#define` 好"的宏。它们是程序在**预处理期**了解编译环境的唯一标准渠道：用的是哪版标准、是否托管实现、支持哪些语言特性、`new` 保证多大的对齐……

本节的规范内容不多，但有两个实际意义很大的部分：`__cplusplus` 的取值，以及**表 22**——全部语言特性测试宏（feature-test macros）的权威值表。标准库的 `__cpp_lib_xxx` 宏不在这里，它们定义在 `<version>` 等头文件中（[[version.syn]]）。

前置知识：`#if` 如何求值（[[cpp.cond]]）；`#line` 如何影响"假定的"行号与文件名（[[cpp.line]]）。

## 必须定义的宏（¶1）

### __cplusplus（¶1.1）

当前草案规定其值为整数字面量 `202603L`。注 1：本文档的未来修订会把它替换为更大的值。

历代取值：

| 标准 | `__cplusplus` |
|---|---|
| C++98 / C++03 | `199711L` |
| C++11 | `201103L` |
| C++14 | `201402L` |
| C++17 | `201703L` |
| C++20 | `202002L` |
| C++23 | `202302L` |
| 当前工作草案（C++26 之后） | `202603L` |

值的形式是 `yyyymmL`，即标准（或草案）定稿的年月。在标准正式发布之前，实现对"下一版"使用临时值：Clang 23 的 `-std=c++2c` 下 `__cplusplus` 为 `202400L`。

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

!!! pitfall "用 >= 比较，不要用 =="
    `#if __cplusplus == 201703L` 在 C++20 编译器上就失效了。永远用 `>=`。更好的做法是用**特性测试宏**检测具体特性，而不是从版本号推断——实现可能只支持某个版本的部分特性。

!!! impl "MSVC 的 __cplusplus"
    MSVC 出于兼容性原因，默认把 `__cplusplus` 定义为 `199711L`，无论 `/std:` 选的是什么，除非使用 `/Zc:__cplusplus`。它另提供 `_MSVC_LANG` 报告真实的语言版本。这是一个明确的不符合标准的默认行为。

### 特性测试宏（¶1.2，表 22）

表 22 中的宏必须被定义为对应的整数字面量。注 2：未来修订**可能**把这些值替换为更大的值。

每个宏的值是**引入或最后一次修改该特性的提案被采纳的年月**。所以同一个宏可以有多个历史值，例如 `__cpp_constexpr` 从 C++11 的 `200704L` 一路增长到当前的 `202406L`——每放宽一次 `constexpr` 的限制，就更新一次。用法总是"`>=` 某个值"：

```cpp run title="feature-test.cpp" ok
#if defined(__cpp_if_consteval) && __cpp_if_consteval >= 202106L
constexpr int f(int x) {
  if consteval { return x; } else { return -x; }
}
#else
constexpr int f(int x) { return x; }
#endif
static_assert(f(1) == 1);
int main() {}
```

!!! note "未定义 = 0"
    在 `#if` 中，未定义的宏名被替换为 0（[[cpp.cond#10]]），所以 `#if __cpp_concepts >= 201907L` 在不支持概念的实现上也能正确地得到假，不必先写 `defined(...)`。上例中的 `defined` 只是为了让意图更明确。

下表列出当前草案表 22 的**全部** 78 个宏及其值，并附 Clang 23 在 `-std=c++2c` 下的实测值（加粗者与草案不同）：

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
| `__cpp_concepts` | `202606L` | **`202002`** |
| `__cpp_conditional_explicit` | `201806L` | `201806L` |
| `__cpp_consteval` | `202606L` | **`202211L`** |
| `__cpp_constexpr` | `202406L` | `202406L` |
| `__cpp_constexpr_dynamic_alloc` | `201907L` | `201907L` |
| `__cpp_constexpr_exceptions` | `202411L` | **未定义** |
| `__cpp_constexpr_in_decltype` | `201711L` | `201711L` |
| `__cpp_constexpr_virtual_inheritance` | `202506L` | **未定义** |
| `__cpp_constinit` | `201907L` | `201907L` |
| `__cpp_contracts` | `202606L` | **未定义** |
| `__cpp_decltype` | `200707L` | `200707L` |
| `__cpp_decltype_auto` | `201304L` | `201304L` |
| `__cpp_deduction_guides` | `202207L` | **`201703L`** |
| `__cpp_delegating_constructors` | `200604L` | `200604L` |
| `__cpp_deleted_function` | `202403L` | `202403L` |
| `__cpp_designated_initializers` | `202606L` | **`201707L`** |
| `__cpp_enumerator_attributes` | `201411L` | `201411L` |
| `__cpp_expansion_statements` | `202506L` | **未定义** |
| `__cpp_explicit_this_parameter` | `202110L` | `202110L` |
| `__cpp_fold_expressions` | `201603L` | `201603L` |
| `__cpp_generic_lambdas` | `201707L` | `201707L` |
| `__cpp_guaranteed_copy_elision` | `201606L` | `201606L` |
| `__cpp_hex_float` | `201603L` | `201603L` |
| `__cpp_if_consteval` | `202106L` | `202106L` |
| `__cpp_if_constexpr` | `201606L` | `201606L` |
| `__cpp_impl_coroutine` | `202606L` | **`201902L`** |
| `__cpp_impl_destroying_delete` | `201806L` | `201806L` |
| `__cpp_impl_reflection` | `202603L` | **未定义** |
| `__cpp_impl_three_way_comparison` | `201907L` | `201907L` |
| `__cpp_implicit_move` | `202207L` | `202207L` |
| `__cpp_inheriting_constructors` | `201511L` | `201511L` |
| `__cpp_init_captures` | `201803L` | `201803L` |
| `__cpp_initializer_lists` | `200806L` | `200806L` |
| `__cpp_inline_variables` | `201606L` | `201606L` |
| `__cpp_lambdas` | `200907L` | `200907L` |
| `__cpp_modules` | `201907L` | **`1`** |
| `__cpp_multidimensional_subscript` | `202211L` | `202211L` |
| `__cpp_named_character_escapes` | `202606L` | `202606L` |
| `__cpp_namespace_attributes` | `201411L` | `201411L` |
| `__cpp_noexcept_function_type` | `201510L` | `201510L` |
| `__cpp_nontype_template_args` | `201911L` | **`201411L`** |
| `__cpp_nontype_template_parameter_auto` | `201606L` | `201606L` |
| `__cpp_nsdmi` | `200809L` | `200809L` |
| `__cpp_pack_indexing` | `202606L` | **`202311L`** |
| `__cpp_placeholder_variables` | `202306L` | `202306L` |
| `__cpp_pp_embed` | `202606L` | **未定义** |
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
| `__cpp_template_parameters` | `202502L` | **未定义** |
| `__cpp_template_template_args` | `201611L` | `201611L` |
| `__cpp_threadsafe_static_init` | `200806L` | `200806L` |
| `__cpp_trivial_union` | `202603L` | **未定义** |
| `__cpp_unicode_characters` | `200704L` | `200704L` |
| `__cpp_unicode_literals` | `200710L` | `200710L` |
| `__cpp_user_defined_literals` | `200809L` | `200809L` |
| `__cpp_using_enum` | `201907L` | `201907L` |
| `__cpp_variable_templates` | `201304L` | `201304L` |
| `__cpp_variadic_friend` | `202403L` | `202403L` |
| `__cpp_variadic_templates` | `200704L` | `200704L` |
| `__cpp_variadic_using` | `201611L` | `201611L` |

读这张表的几点提示：

- **Clang 未定义**：特性尚未实现，例如反射（`__cpp_impl_reflection`）、契约（`__cpp_contracts`）、展开语句（`__cpp_expansion_statements`）、`#embed`（`__cpp_pp_embed`——Clang 虽已支持 `#embed`，但在 C++ 中视为扩展，且不支持标准的 `offset` 参数，见 [[cpp.embed]]）。
- **Clang 值较小**：实现了特性的早期版本，未实现后来的修订，例如 `__cpp_deduction_guides`（`201703L` 对 `202207L`：未完整实现 C++20 的别名模板 CTAD 等扩展）、`__cpp_nontype_template_args`（`201411L` 对 `201911L`：C++20 的类类型 NTTP 被认为未完整实现）。
- **形式异常**：Clang 的 `__cpp_concepts` 为 `202002`（没有 `L` 后缀），`__cpp_modules` 为 `1`——后者明显不是"年月"值，表明实现自认为模块支持尚不完整。
- 草案中出现 `202603L`、`202606L` 等值，说明这些宏在 C++26 定稿之后的工作草案中又被修订过。

!!! tip "库特性宏"
    `__cpp_lib_xxx` 由标准库头文件定义，C++20 起统一汇集在 `<version>` 中（[[version.syn]]）。检测库特性前要先 `#include <version>`（或相应的头文件），否则宏未定义、被当作 0。

### __DATE__ 与 __TIME__（¶1.3、¶1.9）

- `__DATE__`：源文件的翻译日期，形如 `"Mmm dd yyyy"` 的字符串字面量；月份名与 `asctime` 生成的相同；日期小于 10 时 `dd` 的第一个字符是**空格**（`"Jan  1 1970"`）。若日期不可得，实现必须提供一个实现定义的有效日期。
- `__TIME__`：翻译时间，形如 `"hh:mm:ss"`，同 `asctime`。

!!! impl "可复现构建"
    `__DATE__`/`__TIME__` 让每次编译的产物都不同，破坏可复现构建（reproducible builds）。GCC 和 Clang 都支持环境变量 `SOURCE_DATE_EPOCH`：设置后这两个宏取该时间戳对应的值（Clang 23 实测 `SOURCE_DATE_EPOCH=0` 得到 `"Jan  1 1970"` 和 `"00:00:00"`）；`-Wdate-time` 会对使用它们的地方告警。

### __FILE__ 与 __LINE__（¶1.4、¶1.5）

- `__FILE__`：表示当前源文件**假定名字**的字符串字面量。注 3：可以由 `#line` 改变（[[cpp.line]]）。
- `__LINE__`：整数字面量 `0` 或一个十进制整数字面量，**不含数字分隔符和整数后缀**，表示当前源文件中当前源行的**假定行号**。注 4：同样可以由 `#line` 改变。

"不含数字分隔符和整数后缀"的规定让 `__LINE__` 可以安全地用于 `##` 拼接（如生成唯一标识符 `var_123`）和字符串化。

```cpp run title="unique-name.cpp" ok
#define CAT_(a, b) a##b
#define CAT(a, b) CAT_(a, b)
#define UNIQUE(name) CAT(name, __LINE__)
int UNIQUE(tmp) = 1;   // int tmp4 = 1;
int UNIQUE(tmp) = 2;   // int tmp5 = 2;
int main() { return tmp4 + tmp5 - 3; }
```

`CAT` 必须两层：`##` 的操作数不展开（[[cpp.concat#2]]），一层的话会拼出 `tmp__LINE__`。

`__FILE__` 与 `__LINE__` 是唯二在一个翻译单元中**值会变**的预定义宏（¶3）。C++20 起，函数内部更推荐用 `std::source_location::current()`（[[support.srcloc]]），它能作为默认实参在**调用点**求值，而 `__LINE__` 只能在宏展开处求值。

### __STDC_EMBED_*__（¶1.6）{{c++26}}

`__STDC_EMBED_NOT_FOUND__`、`__STDC_EMBED_FOUND__`、`__STDC_EMBED_EMPTY__` 分别是整数字面量 `0`、`1`、`2`。注 5：它们是 `__has_embed` 表达式的可能取值（[[cpp.cond#4]]）。

### __STDC_HOSTED__（¶1.7）

托管实现（hosted）为 `1`，独立实现（freestanding）为 `0`（[[intro.compliance]]）。

```cpp
#if __STDC_HOSTED__
#  include <iostream>   // 独立实现不保证提供 <iostream>
#endif
```

GCC/Clang 的 `-ffreestanding` 会把它定义为 0（Clang 23 实测）。

### __STDCPP_DEFAULT_NEW_ALIGNMENT__（¶1.8）

`std::size_t` 类型的整数字面量，值为调用 `operator new(std::size_t)` 或 `operator new[](std::size_t)` **保证**的对齐。注 6：更大的对齐要求会传给 `operator new(std::size_t, std::align_val_t)` 等（[[expr.new]]）。

这个宏是 C++17 对齐 `new`（[[P0035R4]]）的配套：它告诉你"超过多少字节对齐就算**超对齐**、需要走 `align_val_t` 重载"。在 64 位 Linux 和 macOS 上通常是 16。

```cpp run title="new-align.cpp" ok
#include <cstddef>
#include <new>
struct alignas(64) CacheLine { char data[64]; };
int main() {
  // 64 > __STDCPP_DEFAULT_NEW_ALIGNMENT__（通常为 16）：new 调用 operator new(size_t, align_val_t)
  CacheLine* p = new CacheLine;
  bool ok = reinterpret_cast<std::size_t>(p) % 64 == 0;
  delete p;
  return ok ? 0 : 1;
}
```

Clang 23 在 arm64 macOS 上将其定义为 `16UL`——`UL` 后缀使字面量的类型为 `unsigned long`，在该平台上就是 `std::size_t`。

## 有条件定义的宏（¶2）

¶2 中的宏由实现**有条件地**定义：

| 宏 | 条件 / 值 |
|---|---|
| `__STDCPP_FLOAT16_T__` | 当且仅当支持 ISO/IEC 60559 binary16 作为扩展浮点类型时定义为 1（`std::float16_t`） |
| `__STDCPP_FLOAT32_T__` | binary32（`std::float32_t`） |
| `__STDCPP_FLOAT64_T__` | binary64（`std::float64_t`） |
| `__STDCPP_FLOAT128_T__` | binary128（`std::float128_t`） |
| `__STDCPP_BFLOAT16_T__` | 支持具有 `std::bfloat16_t` 性质的扩展浮点类型时为 1 |
| `__STDC__` | 是否定义、值为何，实现定义 |
| `__STDC_MB_MIGHT_NEQ_WC__` | 整数字面量 1：表示在 `wchar_t` 的编码中，基本字符集成员的码值不一定等于它作为普通字符字面量时的值 |
| `__STDC_VERSION__` | 是否定义、值为何，实现定义 |
| `__STDC_ISO_10646__` | 形如 `yyyymmL`；是否定义、值为何，实现定义 |
| `__STDCPP_THREADS__` | 当且仅当程序可以有多个执行线程时定义为 1 |

扩展浮点类型的五个宏来自 C++23 的 [[P1467R9]]（见 [[basic.extended.fp]]）。它们是"当且仅当"：定义了就**保证**对应的 `std::floatN_t` 可用。

```cpp run title="float16.cpp" ok
#if defined(__STDCPP_FLOAT16_T__) && __has_include(<stdfloat>)
#  include <stdfloat>
using half = std::float16_t;
#else
using half = float;   // 回退
#endif
int main() { half h = 1; return static_cast<int>(h) - 1; }
```

（类型 `std::float16_t` 由库头文件 `<stdfloat>` 提供，而宏是编译器预定义的；两者分属编译器与标准库，所以稳妥起见同时检查。Clang 23 搭配的 libc++ 尚无 `<stdfloat>`。）

!!! impl "实测"
    Clang 23（arm64 macOS）：`__STDCPP_FLOAT16_T__`、`__STDCPP_BFLOAT16_T__` 等均**未定义**（Clang 尚未提供 `std::floatN_t`）；`__STDCPP_THREADS__` 为 1；`__STDC__` 为 1；`__STDC_VERSION__` 未定义；`__STDC_ISO_10646__` 未定义。GCC 自 13 起在支持的目标上定义扩展浮点类型的宏。在 Linux/glibc 上，`__STDC_ISO_10646__` 通常由 glibc 自动预包含的 `<stdc-predef.h>` 定义。

`__STDC__` 在 C 中表示"符合标准的实现"；在 C++ 中它的存在与值都由实现定义——GCC/Clang 定义为 1，MSVC 默认不定义。不要用它来区分 C 与 C++，用 `__cplusplus`。

## 值不变（¶3）

¶3：除 `__FILE__` 与 `__LINE__` 外，预定义宏的值在整个翻译单元中**保持不变**。所以 `__DATE__` 不会在翻译跨越午夜时改变，`__TIME__` 在整个 TU 中是同一个值。

## 不得重定义（¶4）

¶4：如果本节中的任何预定义宏名，或标识符 `defined`，成为 `#define` 或 `#undef` 的对象，程序**非良构**。任何**其他**预定义宏名（即实现自己的扩展宏）必须以下划线加大写字母或双下划线开头。

后一句保证实现的预定义宏都在保留标识符的空间里（[[lex.name]]），不会与用户的名字冲突。所以 `linux`、`unix` 这类 GCC 在 GNU 模式下预定义的宏，严格来说不符合标准——这正是 `-std=c++20`（而不是 `-std=gnu++20`）下 GCC 不定义它们的原因。

```cpp title="redefine-predefined.cpp" error
#define __cplusplus 201103L    // error: 预定义宏
#undef __FILE__                // error
#define __cpp_concepts 1       // error: 特性测试宏也是本节的预定义宏
#define defined                // error: defined
```

Clang 23 对前三行只给 `-Wbuiltin-macro-redefined` 警告，对 `#define defined` 报错。

## 历史与演进

!!! history
    - **C++98**：`__cplusplus`（`199711L`）、`__DATE__`、`__FILE__`、`__LINE__`、`__TIME__`；`__STDC__` 实现定义。（早期 GCC 曾长期把 `__cplusplus` 定义为 1。）
    - **C++11**：`__STDC_HOSTED__`、`__STDCPP_THREADS__`，以及与 C99 同步的 `__STDC_MB_MIGHT_NEQ_WC__`、`__STDC_VERSION__`、`__STDC_ISO_10646__`。
    - **C++17**：`__STDCPP_DEFAULT_NEW_ALIGNMENT__`（[[P0035R4]]）。
    - **C++20**：特性测试宏从 SD-6（委员会的常设文档，非规范性建议）进入标准正文（[[P0941R2]]）。
    - **C++23**：扩展浮点类型的 `__STDCPP_FLOATn_T__`/`__STDCPP_BFLOAT16_T__`（[[P1467R9]]）。
    - **C++26**：`__STDC_EMBED_*__`、`__cpp_pp_embed`（[[P1967R14]]）{{c++26}}。
    - **当前草案**：对预定义宏的 `#define`/`#undef` 由 UB（C++23 及以前）改为非良构。

## 思考题

!!! question "思考题 1"
    为什么特性测试宏的值是年月，而不是简单的 0/1？举例说明一个只检查 `defined(__cpp_xxx)` 会出错的情形。

<details markdown="1">
<summary>展开查看答案与解析</summary>

因为同一个特性会被多次扩充。以 `__cpp_constexpr` 为例：C++11 的 `constexpr` 函数只能有一条 `return` 语句，C++14 放宽（`201304L`），C++20 允许 `try`、`virtual`、平凡默认初始化等（`201907L`、`202002L`），C++23 允许非字面量变量和 `goto`（`202110L`、`202207L`），C++26 允许从 `void*` 的转换（`202306L`）和 placement new（`202406L`）。若代码依赖 C++20 的 `constexpr` 虚函数，只检查 `defined(__cpp_constexpr)` 在 C++11 编译器上也为真，必然出错；应写 `__cpp_constexpr >= 201907L`。

（上面列出的中间值来自各版本的特性测试宏表；具体以 SD-6 文档为准。）
</details>

!!! question "思考题 2"
    `__LINE__` 被规定为"不含数字分隔符、不含整数后缀"的十进制整数字面量。如果允许 `__LINE__` 展开为 `1'234` 或 `1234u`，会破坏哪些常见用法？

<details markdown="1">
<summary>展开查看答案与解析</summary>

最直接的是 `##` 拼接：`CAT(var_, __LINE__)` 应当得到合法标识符 `var_1234`，而 `var_1'234` 不是一个合法的预处理记号（`'` 开始一个字符字面量），`var_1234u` 虽然是合法标识符，但如果同一宏在别处被期望为纯数字（如与 `#line` 配合、或用于数组大小再字符串化比较）就会出问题。另外 `#line __LINE__` 这种自引用写法要求 *digit-sequence*，带分隔符或后缀都不匹配 [[cpp.line#3]] 的形式。标准把形式钉死，就保证了这些惯用法的可移植性。
</details>

## 小结

!!! summary
    - `__cplusplus`：`199711L`、`201103L`、`201402L`、`201703L`、`202002L`、`202302L`；当前草案 `202603L`。用 `>=` 比较。MSVC 需 `/Zc:__cplusplus`。
    - 表 22 列出全部语言特性测试宏；值是年月，多次修订会递增；未定义在 `#if` 中为 0。库特性宏在 `<version>` 中。
    - `__FILE__`/`__LINE__` 报告**假定**的位置（受 `#line` 影响），是唯二值会变化的预定义宏；`__LINE__` 无分隔符无后缀，可安全拼接。
    - `__DATE__`/`__TIME__` 破坏可复现构建，可用 `SOURCE_DATE_EPOCH` 固定。
    - `__STDC_HOSTED__`、`__STDCPP_DEFAULT_NEW_ALIGNMENT__`、`__STDC_EMBED_*__` 必须定义；扩展浮点、线程、`__STDC__` 系列有条件定义。
    - `#define`/`#undef` 本节的预定义宏或 `defined`：非良构。实现自己的预定义宏必须使用保留名。
