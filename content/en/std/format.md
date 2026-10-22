---
title: The formatting library
summary: "The overall structure of the std::format family: basic_format_string with its compile-time format string check, the semantics of format/vformat/format_to/format_to_n/formatted_size, the type-erased arguments basic_format_arg and basic_format_args, error reporting, and the formatters for pair/tuple."
updated: 2026-10-19
---

!!! tldr
    - The format string of `std::format("{} {}", a, b)` is checked at compile time: if the format string does not match the argument types, the program is ill-formed and the compiler must report an error.
    - When the format string is known only at run time, use C++26's `std::dynamic_format(s)` or `std::vformat`; errors then throw `format_error` instead.
    - `format` is a thin template shell; the real work is done by `vformat`, shared by all argument types. Arguments are first normalized to one of 14 types, and user types are type-erased through `handle`.
    - Without the `L` option, formatting is locale-independent.
    - `format_to_n` writes only the first `n` characters, but the returned `size` is the length of the full output, which tells you whether it was truncated.

## Two layers

`<format>` (C++20, [[P0645R10]]) aims to avoid the drawbacks of both `printf` and iostreams. `printf` is concise and fast but not type-safe (`%d` with a `long` is {{ub}}) and cannot be extended to user types. iostreams are type-safe and extensible but verbose; state like `std::hex` sticks to the stream, and the format is split into pieces across many `<<`s, which makes translation hard.

`std::format` uses Python-style format strings, with each type defining its own output by specializing `formatter<T>`, and is split into two layers:

```text
format(fmt, args...)            ← template shell: checks fmt at compile time, packs args
   └─ vformat(fmt.get(), make_format_args(args...))
         └─ non-template run-time interpreter (one copy per Context):
              processes replacement fields one by one → basic_format_arg::visit → formatter<T>::parse/format
```

The shell provides type safety and compile-time diagnostics; the core shares one copy of the code across all argument types, avoiding instantiating a whole set of formatting logic for every combination of argument types.

The format string syntax is covered in [[format.string]], and writing formatters and range formatting in [[format.formatter]]. `std::print` and `std::println` are in [[print.fun]] in Clause 31; they use the same format strings and formatters, differing in output destination and encoding handling.

## Compile-time format string checking [format.fmt.string]

```cpp run title="compile-time-check.cpp" error
#include <format>

int main() {
    auto a = std::format("{} {}", 1);        // error: not enough arguments
    auto b = std::format("{:d}", "str");     // error: strings do not accept d
    auto c = std::format("{0} {}", 1, 2);    // error: mixing automatic and manual numbering
}
```

All three lines are rejected at compile time. The type of `format`'s first parameter is `format_string<Args...>`, which is:

```cpp
template<class charT, class... Args>
struct basic_format_string {
  template<class T> consteval basic_format_string(const T& s);
  constexpr basic_format_string(dynamic-format-string<charT> s) noexcept;
  constexpr basic_string_view<charT> get() const noexcept;
};
```

¶1 The constructor template requires `const T&` to be convertible to `basic_string_view<charT>`; ¶2 it initializes the internal `str` with `s`. The key is ¶3:

!!! std
    A call to this function is not a core constant expression ([expr.const.core]) unless there exist args of types `Args` such that *str* is a format string for args.

Combine this sentence with the core language rules and you get compile-time checking:

1. The constructor is `consteval`, an [[g:immediate-function|immediate function]] ([[dcl.constexpr]]).
2. Calling an immediate function outside an immediate function context is an [[g:immediate-invocation|immediate invocation]]. Per [[expr.const.imm]], an immediate invocation must be a constant expression, otherwise the program is ill-formed.
3. ¶3 says that if the format string is not valid for `Args`, the call is not a core constant expression.
4. So `std::format("{:d}", "str")` is a compile error the standard requires to be diagnosed, not just an extra check by the compiler.

libc++'s constructor parses the whole format string during constant evaluation and calls each argument's formatter's `parse`; when it finds an error it calls a non-`constexpr` function, so the evaluation is no longer a constant expression. That is why Clang's diagnostic reads `call to consteval function ... is not a constant expression`, followed by a note saying `non-constexpr function '__throw_format_error' cannot be used in a constant expression`.

It follows that a custom formatter's `parse` must be `constexpr`; otherwise no `std::format` call that formats that type can be a constant expression, and it simply fails to compile (see [[format.formatter]]).

`format_string<Args...>` is defined as `basic_format_string<char, type_identity_t<Args>...>`. `type_identity_t` makes this parameter a non-deduced context ([[temp.deduct.type]]), so `Args` is deduced only from the later arguments; the string literal is then implicitly converted through the consteval constructor.

### Format strings known only at run time: `dynamic_format` {{c++26}}

```cpp run title="dynamic-format.cpp" ok
#include <cassert>
#include <format>
#include <string>

int main() {
    std::string fmt = "{} + {} = {}";            // a format string known only at run time
    assert(std::format(std::dynamic_format(fmt), 1, 2, 3) == "1 + 2 = 3");

    try {
        (void)std::format(std::dynamic_format("{:d}"), "str");
        assert(false);
    } catch (const std::format_error&) {
        // the check is deferred to run time: an exception is thrown
    }
}
```

When the format string comes from run-time data such as a translation file, `std::format(s, args...)` cannot compile, because `s` is not a constant expression. The C++20 and C++23 approach is to use `std::vformat(s, std::make_format_args(args...))` instead.

C++26's [[P2918R2]] provides a more direct way. It was originally called `std::runtime_format` and is named `std::dynamic_format` in the current draft. It returns an exposition-only *dynamic-format-string* object, and `basic_format_string` has a non-`consteval` constructor accepting it, so the check is deferred to run time and failure throws `format_error`.

The copy constructor and copy assignment of *dynamic-format-string* are both deleted. It holds only a `string_view`; with copying forbidden, the result of `dynamic_format(...)` can only be passed directly to a formatting function, not stored in a variable for later use, which reduces the chance of dangling. libc++ in our tests provides `std::dynamic_format` and not `std::runtime_format`.

## Formatting functions [format.functions]

```cpp run title="format-to-n.cpp" ok
#include <cassert>
#include <format>
#include <iterator>
#include <string>
#include <string_view>

int main() {
    char buf[4];
    auto [out, size] = std::format_to_n(buf, sizeof buf, "{}", 123456);
    assert(size == 6);                                   // the full length
    assert(out == buf + 4);                              // only 4 written
    assert(std::string_view(buf, out) == "1234");

    assert(std::formatted_size("{:>10}", 1) == 10);      // only computes the length, outputs nothing

    std::string s;
    std::format_to(std::back_inserter(s), "{}+{}", 1, 2);
    assert(s == "1+2");
}
```

Each formatting function comes in `char` and `wchar_t` sets, plus versions taking a `const locale&` parameter.

### `format` and `vformat` (¶3–¶8)

¶3 `format(fmt, args...)` is equivalent to `vformat(fmt.str, make_format_args(args...))`. ¶7 `vformat` returns the formatted result; if `loc` is given, it is used for locale-specific formatting, that is, the `L` option ([[format.string.std#17]]).

Without `loc`, the global locale `std::locale()` is used only when `L` appears in a format spec ([[format.context#7]]). So `std::format("{}", 1234.5)` prints `1234.5` even under a German locale.

### `format_to` and `vformat_to` (¶9–¶18)

¶13–¶17 Output is written to `[out, out + N)` starting at the iterator `out`, and `out + N` is returned, where `N` is the number of characters output. ¶14 is a constraint: `Out` satisfies the syntactic requirements of `output_iterator<const charT&>`; ¶15 is a precondition: `Out` also meets the semantic requirements of that concept.

`format_to` does not know how big the destination is. Using it to write into a fixed-size array is {{ub}} if the output is too long.

### `format_to_n` and `formatted_size` (¶19–¶28)

¶19 Let `N` be the length of the full output (that is, `formatted_size(fmt, args...)`) and `M = clamp(n, 0, N)`. ¶22 Only the first `M` characters are written; ¶23 `{out + M, N}` is returned. So the returned `size` is the full length, and comparing it with `n` tells you whether the output was truncated; a negative `n` is treated as 0.

¶27 `formatted_size` returns only the length and outputs no characters. ¶21 and ¶26 require each argument's formatter to meet the *BasicFormatter* requirements ([[format.formatter]]).

### Compile-time formatting (¶1)

¶1 A call to these functions can be a constant subexpression only if every formatter specialization used is [[g:constexpr-enabled-specialization|constexpr-enabled]]. The versions without a `locale` parameter are all declared `constexpr` in the synopsis; those with `locale` are not, because `std::locale` cannot be used in constant evaluation. This wording was added to the draft after C++23.

!!! impl
    At the time of writing, libc++'s `std::format` is not yet `constexpr`; `static_assert(std::format("{}", 42) == "42")` does not compile, and `__cpp_lib_format` is still `202110L`.

## Error reporting [format.err.report]

¶1 specifies three things:

1. If the `fmt` passed is not a valid format string for `args`, the formatting function throws `format_error`. For the `format_string` versions most such errors are already caught at compile time, so this sentence mainly applies to the `vformat` family and to `dynamic_format`. But some errors can only be found at run time, such as a negative argument for the dynamic width `{:{}}` ([[format.string.std#10]]).
2. Exceptions thrown by formatter specializations and iterator operations are propagated.
3. Allocation failure is reported as in [[res.on.exception.handling]], that is, by throwing `bad_alloc`.

[format.error] `format_error` derives from `runtime_error`; both constructors are `constexpr`, and ¶2–¶3 specify that `what()` has the same contents as the string passed in.

## Type erasure of arguments [format.arguments]

```cpp run title="format-args.cpp" ok
#include <cassert>
#include <format>
#include <type_traits>

int main() {
    short sh = 3;
    const char* s = "hi";
    auto store = std::make_format_args(sh, s);
    std::format_args args = store;                          // a view that does not own the arguments
    assert(args.get(0) && args.get(1) && !args.get(2));    // out of range gives an empty arg
    bool is_int = args.get(0).visit([](auto v) { return std::is_same_v<decltype(v), int>; });
    assert(is_int);                                         // short is normalized to int
    assert(std::vformat("{}-{}", args) == "3-hi");
}
```

### `basic_format_arg`: one of 14 types [format.arg]

In the exposition, `basic_format_arg<Context>` is just a

```cpp
variant<monostate, bool, char-type,
        int, unsigned int, long long int, unsigned long long int,
        float, double, long double,
        const char-type*, basic_string_view<char-type>,
        const void*, handle>
```

Every argument is first normalized to one of these 14, so the run-time core needs only one copy. ¶6 gives the mapping (`TD` is the argument type with `const` removed):

| Argument type `TD` | Stored as |
|---|---|
| `bool`, `char-type` | as is (¶6.1) |
| `char`, with `char-type` being `wchar_t` | `static_cast<wchar_t>(static_cast<unsigned char>(v))`, converted to unsigned first to avoid sign-extending negative values (¶6.2) |
| signed integers no wider than `int` (`short`, `signed char`, ...) | `int` (¶6.3) |
| unsigned integers no wider than `unsigned int` | `unsigned int` (¶6.4) |
| wider integers | `long long` or `unsigned long long` (¶6.5–¶6.6) |
| standard floating-point types | as is (¶6.7) |
| `basic_string`, `basic_string_view` with matching character type | `basic_string_view` (¶6.8) |
| decays to `char-type*` or `const char-type*` | `const char-type*` (¶6.9) |
| `void*`, `nullptr_t` and the like | `const void*` (¶6.10) |
| everything else (user types, extended floating-point types, integers wider than `long long`, ...) | `handle` (¶6.11) |

The signed and unsigned integer types in ¶6.3–¶6.6 include extended integer types ([[basic.fundamental]]). Extended integers wider than `long long` match none of those rules and fall into `handle`. ¶4 requires the argument type to be formattable with `Context`, that is, to have a usable formatter; Note 1 points out that pointers to members have no standard formatter, so formatting one directly is ill-formed.

¶5 Precondition: if the argument decays to `char-type*` or `const char-type*`, it must point to a null-terminated string. Passing a `char` array without a terminating null is {{ub}}.

¶10–¶14 `handle` erases user types: it stores the object's address and a function pointer, and the function constructs a `formatter<TD>` at run time, calling `parse` and then `format`. ¶11–¶13 say that if `const TD` is formattable, the object is passed to `format` as `const`, otherwise as non-`const`. This was added by [[P2418R2]] to support views that can only be iterated as non-`const` (such as `filter_view`).

¶8–¶9 The stored value is accessed with the member function `arg.visit(vis)`, added by C++26's [[P2637R3]] and declared with an explicit object parameter `this basic_format_arg arg` ([[dcl.fct]]). The old free function `visit_format_arg` has moved to Annex [[depr.format]]. ¶3, ¶7 A default-constructed `basic_format_arg` holds `monostate`, and its `explicit operator bool` is false.

### `make_format_args` accepts only lvalues [format.arg.store]

¶3 `make_format_args(Args&... fmt_args)` returns an exposition-only *format-arg-store*, internally an `array<basic_format_arg<Context>, sizeof...(Args)>`.

The parameters are lvalue references `Args&`, a change made by [[P2905R2]], which as a defect report also applies to C++23. Previously they were forwarding references, and `std::make_format_args(42)` compiled, but the returned store referred to a temporary destroyed at the end of the full-expression, so storing it in a variable and using it later dangled. Now passing an rvalue is simply ill-formed:

```cpp run title="make-format-args.cpp" error
#include <format>

int main() {
    auto s = std::vformat("{}", std::make_format_args(42));   // error: cannot bind an rvalue
}
```

### `basic_format_args`: a view that does not own the arguments [format.args]

¶3 `basic_format_args<Context>` stores only the number of arguments and a pointer to the store's array; it does not own the arguments. ¶4 An out-of-range `get(i)` returns a default-constructed `basic_format_arg` rather than being {{ub}}, which can be detected with `explicit operator bool`.

¶2 recommends that implementations optimize the representation for a small number of arguments, for example by packing the type tags of the arguments separately. libc++ does exactly that: with few arguments, it packs each argument's type tag into a few bits of a 64-bit integer and stores the values in a separate array; only past a limit does it store a full array of `basic_format_arg`.

## Formatters for `pair` and `tuple` [format.tuple]

```cpp run title="tuple-format.cpp" ok
#include <cassert>
#include <format>
#include <string>
#include <tuple>
#include <utility>

int main() {
    assert(std::format("{}", std::tuple{1, "s", 2.5}) == "(1, \"s\", 2.5)");
    assert(std::format("{:m}", std::pair{1, 2}) == "1: 2");
    assert(std::format("{:n}", std::pair{1, 2}) == "1, 2");
    assert(std::format("{:*^10}", std::pair{1, 2}) == "**(1, 2)**");
}
```

¶1 Since C++23 the standard library provides formatters for `pair` and `tuple` whenever every element type is formattable ([[P2286R8]]). The default output is `(a, b, c)`. ¶7 Each element's formatter parses an empty format spec and, where possible, `set_debug_format()` is called, so string elements are quoted and escaped, as in `(1, "s", 2.5)`.

¶2–¶4 The *tuple-format-spec* has only three parts, `[fill-and-align][width][type]`, and `type` has two values (Table 116):

- `m`: valid only with exactly two elements; equivalent to `set_separator(": ")` plus `set_brackets({}, {})`, giving `1: 2`, which is exactly the format of map elements;
- `n`: removes the brackets, giving `1, 2`.

There is no way to give a format spec for individual elements, unlike `{::spec}` for ranges. If you need it, you have to write your own formatter or unpack the elements first.

The value of `enable_nonlocking_formatter_optimization` for `pair` and `tuple` is the conjunction of the corresponding values for the elements (see [[format.formatter]]).

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[format.syn] is the synopsis of `<format>`. ¶1 specifies that `format_to_n_result<Out>` has only the two members `out` and `size` and no base classes, so it can be unpacked with a structured binding.

[format.functions] ¶2 says that the `+` operation used in the descriptions for some iterator categories is to be understood per the conventions of [algorithms.requirements]. ¶4–¶6 and ¶10–¶12 are the `wchar_t` and `locale` overloads, with the same equivalences as the `char` versions.

[format.arg] ¶1–¶2 `basic_format_arg` lets user-defined formatters access arguments; a program adding a specialization of it is {{ub}}.

[format.arg.store] ¶2 requires each argument's formatter to meet *BasicFormatter*; ¶4 `make_wformat_args` is equivalent to `make_format_args<wformat_context>`.

[format.tuple] ¶5–¶6 and ¶8–¶11 specify the effects of `set_separator` and `set_brackets`, and that `format` outputs the opening bracket, the elements separated by the separator, and the closing bracket, in that order.

</details>

## History

!!! history
    - C++20: [[P0645R10]] introduced `<format>`, based on the {fmt} library.
    - [[P2216R3]] (a defect report against C++20): added consteval compile-time checking via `basic_format_string`, and reduced code bloat of `format_to` across different iterator types.
    - [[P2418R2]] (a defect report against C++20): support for types that can only be formatted as non-`const`.
    - C++23: [[P2508R1]] exposed `basic_format_string` (previously exposition-only) and added `get()`; [[P2286R8]] added formatting of ranges and `pair`/`tuple`, and the `?` debug format.
    - C++26: [[P2637R3]] member function `visit`; [[P2905R2]] `make_format_args` accepts only lvalues; [[P2918R2]] run-time format strings, later renamed `dynamic_format`.
    - The draft after C++23 made the formatting functions `constexpr` and introduced the notion of constexpr-enabled specializations.

## Common misconceptions

!!! pitfall "Storing a `basic_format_args` or the result of `make_format_args`"
    `basic_format_args` is just a view, and the `string_view`s and `handle`s inside a *format-arg-store* are only references. Do not store them anywhere that outlives the arguments.

!!! pitfall "Writing to a fixed-size buffer with `format_to`"
    `format_to` has no length parameter. To write into a fixed-size buffer use `format_to_n`, and check the returned `size` for truncation.

!!! pitfall "Assuming `std::format` uses the global locale by default"
    The opposite: without `L` it is locale-independent; only `{:L}` uses a locale.

## Questions

!!! question "Question 1"
    In `std::format(fmt_sv, 1)`, `fmt_sv` is a `constexpr std::string_view` local variable. Does it compile? What if `constexpr` is removed?

<details markdown="1">
<summary>Answer</summary>

With `constexpr`, yes. Constructing the `format_string` is an immediate invocation; `fmt_sv` is a `constexpr` variable whose value can be read during constant evaluation ([[expr.const]]), and the check passes.

Without `constexpr`, the value of `fmt_sv` cannot be read during constant evaluation, the immediate invocation is not a constant expression, and the program is ill-formed. Clang reports `call to consteval function ... is not a constant expression`. Use `std::dynamic_format(fmt_sv)` or `vformat` instead.
</details>

!!! question "Question 2"
    Why is `format_string<Args...>` written as `basic_format_string<char, type_identity_t<Args>...>`? What would happen with plain `basic_format_string<char, Args...>`?

<details markdown="1">
<summary>Answer</summary>

In `format(format_string<Args...> fmt, Args&&... args)`, if the first parameter also took part in deducing `Args`, deduction would have to match the string literal's type `const char[N]` against `basic_format_string<char, Args...>`. That necessarily fails, and deduction does not consider implicit conversions ([[temp.deduct.call]]), so the whole deduction fails.

`type_identity_t` makes this parameter a non-deduced context, so `Args` is deduced only from `args`; once deduction is done, the string literal is implicitly converted to `basic_format_string` through the consteval constructor.
</details>

## Summary

| Facility | Key points |
|---|---|
| `basic_format_string` | consteval construction; with an invalid format string the immediate invocation is not a constant expression, so compilation fails |
| `dynamic_format` | C++26; defers checking to run time, throwing `format_error` on failure; formerly named `runtime_format` |
| `format` / `vformat` | template shell plus a type-erased core; no locale without `L` |
| `format_to_n` | writes `min(n, N)` characters and returns `{out + M, N}`, where `N` is the full length |
| `basic_format_arg` | one of 14 types; short integers normalized to `int`; user types stored as `handle` |
| `make_format_args` | accepts only lvalues ([[P2905R2]]) |
| `basic_format_args` | a view that does not own the arguments; an out-of-range `get` returns an empty arg |
| tuple formatter | outputs `(a, b)`; `m` gives `a: b`, `n` removes the brackets; string elements use the debug format automatically |
| `format_error` | derives from `runtime_error`; constructors are `constexpr` |
