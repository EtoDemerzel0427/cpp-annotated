---
title: System error support
summary: "<system_error> pairs an integer error code with its origin (an error category): error_code holds the precise platform error, error_condition represents a portable error condition, and the two are compared through the categories' virtual functions; plus how to define your own error categories and the system_error exception."
updated: 2026-10-19
---

!!! tldr
    - An error consists of an integer value and an error category. Categories are non-copyable singleton objects, and two categories are the same if and only if they are the same object.
    - `error_code` holds the error an operation actually got, precise but platform-dependent; `error_condition` represents a kind of error the caller cares about, a portable abstraction.
    - Two `error_code`s are equal only if both category and value are the same; when an `error_code` is compared with an `error_condition`, the `equivalent` virtual functions of both categories decide, and they are equal if either side accepts.
    - Store and pass errors with `error_code`, and determine which kind of error it is with a condition such as `errc`.
    - Custom error codes: specialize `is_error_code_enum`, provide `make_error_code` in the enumeration's namespace, and derive a category from `error_category`.

Operating systems and low-level libraries all report errors as integers: POSIX uses `errno`, Windows uses `GetLastError()`, `getaddrinfo` has its own `EAI_*`, and various third-party libraries each have their own set. A bare `int` is ambiguous: `2` is `ENOENT` on POSIX, `ERROR_FILE_NOT_FOUND` on Windows, and possibly something else in some HTTP library.

`<system_error>`'s approach is to pair the integer with its origin, the error category. ¶1 says these components are used by the standard library and C++ programs to report error conditions originating from the operating system or other low-level application program interfaces ([syserr.general]).

## An example first

```cpp run title="code-vs-condition.cpp" ok
#include <cerrno>
#include <cstdio>
#include <iostream>
#include <system_error>

int main() {
    std::error_code ec(ENOENT, std::system_category());   // an error reported by the operating system
    std::error_code gc = std::make_error_code(std::errc::no_such_file_or_directory);

    std::printf("%d\n", ec == std::errc::no_such_file_or_directory);   // 1: code vs. condition
    std::printf("%d\n", std::errc::no_such_file_or_directory == ec);   // 1: C++20 reversed rewrite
    std::printf("%d\n", ec == gc);                                     // 0: code vs. code
    std::cout << ec << " | " << ec.message() << " | " << gc << '\n';
    // system:2 | No such file or directory | generic:2

    auto cond = ec.default_error_condition();
    std::printf("%s:%d\n", cond.category().name(), cond.value());      // generic:2
    std::error_code big(100000, std::system_category());               // doesn't correspond to any errno value
    auto c2 = big.default_error_condition();
    std::printf("%s:%d\n", c2.category().name(), c2.value());          // system:100000
}
```

`ec` and `gc` both have the value 2, yet they aren't equal, because they belong to different categories. `ec` equals `errc::no_such_file_or_directory` because `system_category` considers its own 2 to correspond to POSIX's `ENOENT`. The rest of this page explains where these results come from.

The whole design consists of four classes:

| Class | Role |
|---|---|
| `error_category` ([[g:error-category]]) | The origin of errors: distinguishes origins by object identity, and uses virtual functions to interpret values and map them to portable conditions |
| `error_code` ([[g:error-code]]) | The error an operation actually got, precise and platform-dependent |
| `error_condition` ([[g:error-condition]]) | The error condition the caller cares about, abstract and portable |
| `system_error` | An exception carrying an `error_code` |

## Error categories [syserr.errcat]

### Categories are singletons, and identity is the address

```cpp
class error_category {
public:
  constexpr error_category() noexcept;
  virtual ~error_category();
  error_category(const error_category&) = delete;
  error_category& operator=(const error_category&) = delete;
  virtual const char* name() const noexcept = 0;
  virtual error_condition default_error_condition(int ev) const noexcept;
  virtual bool equivalent(int code, const error_condition& condition) const noexcept;
  virtual bool equivalent(const error_code& code, int condition) const noexcept;
  virtual string message(int ev) const = 0;

  bool operator==(const error_category& rhs) const noexcept;
  strong_ordering operator<=>(const error_category& rhs) const noexcept;
};
```

¶1 ([syserr.errcat.overview]) `error_category` serves as a base class for types used to identify the source and encoding of a particular category of error code. Programs may derive their own categories, and derived classes shall behave as specified in this subclause.

Categories can't be copied and are always passed by reference; an `error_code` stores a pointer to one. Note 1 points out that two category objects are equal if and only if their addresses are the same; if a custom category type has several objects, comparisons between them may be false.

The default constructor is `constexpr`, so category objects of derived classes can be constant-initialized and are unaffected by static initialization order.

### Default behavior of the virtual functions [syserr.errcat.virtuals]

`name()` and `message(int)` are pure virtual, and derived classes must provide them: the former returns the category name, the latter translates a value into descriptive text. The other three virtual functions have default implementations:

| Function | Default return |
|---|---|
| ¶2 `default_error_condition(ev)` | `error_condition(ev, *this)`, same value, same category |
| ¶3 `equivalent(int code, const error_condition& cond)` | `default_error_condition(code) == cond` |
| ¶4 `equivalent(const error_code& code, int cond)` | `*this == code.category() && code.value() == cond` |

The two `equivalent`s go in different directions:

- `equivalent(int code, const error_condition&)` is called on the category the code belongs to, and asks: does this `code` of my category belong to that condition?
- `equivalent(const error_code&, int condition)` is called on the category the condition belongs to, and asks: does that `error_code` belong to the condition `condition` of my category?

Whether a code and a condition are equivalent can be established by either side's category. The comparison operators below ask both.

¶1–¶4 of [syserr.errcat.derived] are looser for derived classes overriding these functions than the default implementations: `default_error_condition(ev)` returns the condition corresponding to `ev`, and the two `equivalent`s return `true` if the category considers the two equivalent. What "corresponding" and "equivalent" mean exactly is up to the derived class.

### Comparing categories [syserr.errcat.nonvirtuals]

¶1 `operator==` returns `this == &rhs`. ¶2 `operator<=>` returns `compare_three_way()(this, &rhs)`; `compare_three_way` gives a total order over any pointers ([[comparisons.three.way]]), so categories can be sorted, but the order depends on the objects' addresses and may differ from run to run.

### The two standard categories [syserr.errcat.objects]

¶1–¶2 `generic_category()` returns the same object on every call; `name()` returns `"generic"`, and the other virtual functions behave as the base class defaults. It interprets POSIX `errno` values, and `errc` values are interpreted in this category.

¶3–¶4 `system_category()` is also a singleton; `name()` returns `"system"`, and it represents the operating system's native error codes. Its `default_error_condition(ev)` has a special specification:

- if `ev` is 0, it returns `error_condition(0, generic_category())`;
- if `ev` corresponds to a POSIX `errno` value `pxv`, it returns `error_condition(pxv, generic_category())`;
- otherwise it returns `error_condition(ev, system_category())`.

What constitutes correspondence for a given operating system is unspecified. Note 1 explains that the number of system error codes is huge and some don't correspond to any POSIX value, so it is left to the implementation.

This is what `system_category` is for. On POSIX systems, system error codes are `errno` values and the mapping is the identity; on Windows, its values are Win32 error codes returned by `GetLastError()`, and `default_error_condition` maps things like `ERROR_FILE_NOT_FOUND` to `errc::no_such_file_or_directory`. So `ec == std::errc::no_such_file_or_directory` holds on both platforms. The 100000 in the example above doesn't correspond to any POSIX value, so it stays in `system_category`.

## `error_code` [syserr.errcode]

¶1 ([syserr.errcode.overview]) An `error_code` holds an error code value, such as one originating from the operating system. Note 1 says it complements reporting errors with exceptions, giving interfaces that don't want to or can't throw a channel for reporting.

Its data is just two exposition-only members `int val_;` and `const error_category* cat_;`, an integer plus a pointer, so it can be passed and stored by value cheaply.

### Construction and modification

| Operation | Effect |
|---|---|
| `error_code()` | Value 0, category `system_category()` (constructors ¶1) |
| `error_code(int val, const error_category& cat)` | Stores them directly (constructors ¶2) |
| `template<class E> error_code(E e)` | Constraints: `is_error_code_enum_v<E>`; effects: `error_code ec = make_error_code(e); assign(ec.value(), ec.category());` (constructors ¶3–¶4) |
| `assign(val, cat)`, `operator=(E e)` | As above (modifiers ¶1–¶4) |
| `clear()` | Value 0, category `system_category()` (modifiers ¶5) |

The `make_error_code(e)` in the enumeration constructor is an unqualified call, found through argument-dependent lookup ([[basic.lookup.argdep]]) in the namespace of the enumeration `E`, where users provide it. This is the extension point: specialize `is_error_code_enum` for your enumeration, provide `make_error_code` in the same namespace, and `error_code ec = my_errc::timeout;` compiles.

When the *Constraints* aren't met, this constructor doesn't participate in overload resolution ([[structure.specifications]]), so `error_code ec = 42;` doesn't match the template constructor.

!!! pitfall "`errc` is a condition enumeration, not a code enumeration"
    The standard specializes only `is_error_condition_enum<errc>` ([[system.error.syn#2]] allows programs to specialize these two templates for their own types). So `std::error_condition c = std::errc::invalid_argument;` compiles, but `std::error_code ec = std::errc::invalid_argument;` doesn't; Clang reports "no viable conversion from 'std::errc' to 'std::error_code'". To get an `error_code`, write `std::make_error_code(std::errc::invalid_argument)`. `errc` represents portable conditions for comparisons (`ec == std::errc::invalid_argument`), not concrete error values.

### Observers and non-member functions

- Observers ¶1–¶2 `value()` and `category()` return the two members; ¶3 `default_error_condition()` equals `category().default_error_condition(value())`.
- ¶4 `message()` equals `category().message(value())`. It isn't `noexcept` and may allocate memory and throw `bad_alloc`.
- ¶5 `explicit operator bool()` returns `value() != 0`.
- Non-member ¶1 `make_error_code(errc e)` returns `error_code(static_cast<int>(e), generic_category())`.
- Non-member ¶2 `operator<<` writes `category-name:value`, such as `system:2`, not the descriptive text.

`if (ec)` looks only at whether the value is 0, regardless of category. All of `<system_error>` follows the convention that the value 0 means no error in any category. When defining a category for a low-level library that uses 0 to mean some error, the mapping must avoid 0.

## `error_condition` [syserr.errcondition]

!!! std
    error_condition values are portable abstractions, while error_code values are implementation specific.

Note 1 in ¶1 says `error_condition` values are portable abstractions, while `error_code` values are implementation-specific.

Its interface is almost the same as `error_code`'s, likewise a value plus a category pointer. The differences:

- default construction and `clear()` use `generic_category()` (constructors ¶1, modifiers ¶5), not `system_category()`;
- the enumeration constructor is constrained by `is_error_condition_enum_v` and calls `make_error_condition` through argument-dependent lookup (constructors ¶3–¶4);
- there is no `default_error_condition()`; it is itself a condition;
- non-member ¶1 `make_error_condition(errc e)` returns `error_condition(static_cast<int>(e), generic_category())`;
- there is no `operator<<`, and no formatter.

## Comparison [syserr.compare]

| Comparison | Returns |
|---|---|
| ¶1 `error_code == error_code` | `lhs.category() == rhs.category() && lhs.value() == rhs.value()` |
| ¶2 `error_code == error_condition` | `lhs.category().equivalent(lhs.value(), rhs) \|\| rhs.category().equivalent(lhs, rhs.value())` |
| ¶3 `error_condition == error_condition` | Same category and same value |
| ¶4, ¶5 the two `<=>` | Compare categories first (by address), then values |

Same-type comparison is exact. `error_code(ENOENT, system_category())` and `error_code(ENOENT, generic_category())` aren't equal, even though on POSIX they say the same thing.

Comparison between `error_code` and `error_condition` is semantic: first ask whether the code's category considers the value to belong to that condition, then ask whether the condition's category claims the code; if either answers yes, they are equal. With the default implementation, the first question is just `default_error_condition(code) == condition`, and `system_category` maps values that have a correspondence to `generic_category`, which is why the first line of the opening example prints 1.

!!! note "Only three `==` remain in the synopsis since C++20"
    In C++17 and earlier, the synopsis also had `error_condition == error_code` and all the `!=` and `<`. Since C++20, `!=` and the reversed `==` are provided automatically by rewritten candidates ([[over.match.oper]]), and `<` and the rest by `<=>`. There is no `<=>` between `error_code` and `error_condition`: the relation between them is membership, not ordering within one domain of values.

This leads to how `<system_error>` should be used:

- Pass and store errors as `error_code`. It keeps the original value and origin, so logs can print something like `system:10054` that helps investigation.
- To determine which kind of error it is, compare with an `error_condition`, usually an `errc` enumerator: `if (ec == std::errc::timed_out)`. This works on both POSIX and Windows.
- Don't compare with `make_error_code(errc::...)`. That is an exact comparison of two `error_code`s, equal only if the other one happens to be in `generic_category` too.

## Defining your own error category

An HTTP client library has its own error codes, and the application layer cares about whether a request can be retried:

```cpp run title="custom-category.cpp" ok
#include <cstdio>
#include <string>
#include <system_error>

// the library's own error codes: concrete, implementation-specific
enum class http_errc { ok = 0, not_found = 404, timeout = 408, server_down = 503 };
// the error conditions the application cares about: abstract, portable
enum class app_cond { ok = 0, retryable = 1, permanent = 2 };

template<> struct std::is_error_code_enum<http_errc> : std::true_type {};
template<> struct std::is_error_condition_enum<app_cond> : std::true_type {};

struct app_category_t final : std::error_category {
  const char* name() const noexcept override { return "app"; }
  std::string message(int c) const override {
    return c == 1 ? "retryable" : c == 2 ? "permanent" : "unknown";
  }
};
const std::error_category& app_category() { static const app_category_t c; return c; }
std::error_condition make_error_condition(app_cond c) { return {static_cast<int>(c), app_category()}; }

struct http_category_t final : std::error_category {
  const char* name() const noexcept override { return "http"; }
  std::string message(int c) const override { return "HTTP " + std::to_string(c); }
  // the code-to-condition mapping lives on the code side
  bool equivalent(int code, const std::error_condition& cond) const noexcept override {
    if (cond == app_cond::retryable)  return code == 408 || code == 503;
    if (cond == app_cond::permanent)  return code == 404;
    if (cond == std::errc::timed_out) return code == 408;   // also matches a generic condition
    return default_error_condition(code) == cond;
  }
};
const std::error_category& http_category() { static const http_category_t c; return c; }
std::error_code make_error_code(http_errc e) { return {static_cast<int>(e), http_category()}; }

int main() {
  std::error_code ec = http_errc::timeout;          // make_error_code found via argument-dependent lookup
  std::printf("%s\n", ec.message().c_str());                      // HTTP 408
  std::printf("retryable? %d\n", ec == app_cond::retryable);      // 1
  std::printf("permanent? %d\n", ec == app_cond::permanent);      // 0
  std::printf("timed_out? %d\n", ec == std::errc::timed_out);     // 1
  std::printf("same code? %d\n", ec == std::error_code(408, std::generic_category()));  // 0
}
```

A few notes:

- The category objects are singletons implemented with function-local statics, whose initialization is thread-safe since C++11. Constant-initialized global objects work too.
- `make_error_code` and `make_error_condition` must be in the enumeration's namespace for argument-dependent lookup to find them.
- The mapping can be written in the code's category (overriding `equivalent(int, const error_condition&)` or `default_error_condition`), or in the condition's category (overriding `equivalent(const error_code&, int)`). The former suits a library that knows which general conditions its errors belong to; the latter suits an application that defines a condition and claims error codes from several libraries without modifying them.

## `system_error` [syserr.syserr]

¶1 `system_error` is an exception carrying an error code, typically used to report errors originating from the operating system. Note 1 in ¶2 recommends that errors representing out-of-memory conditions throw `bad_alloc` rather than `system_error`.

```cpp
class system_error : public runtime_error {
public:
  system_error(error_code ec, const string& what_arg);
  system_error(error_code ec, const char* what_arg);
  system_error(error_code ec);
  system_error(int ev, const error_category& ecat, const string& what_arg);
  system_error(int ev, const error_category& ecat, const char* what_arg);
  system_error(int ev, const error_category& ecat);
  const error_code& code() const noexcept;
  const char* what() const noexcept override;
};
```

[syserr.syserr.members] ¶1–¶6 give the postconditions of the six constructors: `code()` equals the given error code; the versions taking `what_arg` additionally require `what()` to contain `what_arg`, but not necessarily equal it. ¶8 says `what()` returns a string incorporating the constructor arguments, and Note 1 gives `what_arg + ": " + code.message()` as an example.

Classes such as `runtime_error` in [[std.exceptions]] require `what()` to equal `what_arg`; `system_error` requires only containment, so that implementations can append the error code's descriptive text.

```cpp run title="system-error.cpp" ok
#include <cerrno>
#include <cstdio>
#include <stdexcept>
#include <system_error>

int main() {
    try {
        throw std::system_error(ENOENT, std::system_category(), "open config");
    } catch (const std::runtime_error& e) {      // system_error derives from runtime_error
        std::printf("what(): %s\n", e.what());   // libc++: open config: No such file or directory
        if (auto* se = dynamic_cast<const std::system_error*>(&e))
            std::printf("is ENOENT: %d\n", se->code() == std::errc::no_such_file_or_directory);
    }
}
```

`ios_base::failure` and `filesystem::filesystem_error` both derive from `system_error`; `std::thread`, `std::mutex` and others also throw `system_error` when system resources are unavailable.

## Formatting and hashing

### formatter [syserr.fmt]

Drafts after C++23 add `formatter<error_code, charT>` for `error_code`. The format spec is *fill-and-align*ₒₚₜ *width*ₒₚₜ `?`ₒₚₜ `s`ₒₚₜ (¶3). Per ¶5:

- without `s`, it writes `category-name:value`, consistent with `operator<<`, so `std::format("{}", ec)` gives `system:2`;
- with `s`, it writes `ec.message()`, so `std::format("{:s}", ec)` gives `No such file or directory`. If `charT` is `char` and the ordinary literal encoding is UTF-8, the message is transcoded to UTF-8, with invalid byte sequences replaced by U+FFFD; otherwise it is transcoded to an implementation-defined encoding;
- with `?`, it is written as an escaped string ([[format.string.escaped]]). `set_debug_format()` in ¶2 has the same effect, and is used when an `error_code` is formatted as a container element.

At the time of writing, Clang 23 + libc++ doesn't have this specialization yet: `std::format("{}", std::error_code())` is an error saying the default constructor of `formatter<std::error_code, char>` is implicitly deleted.

### Hashing [syserr.hash]

¶1 `hash<error_code>` and `hash<error_condition>` are enabled ([[unord.hash]]), so they can be keys of unordered containers.

!!! impl "libc++'s hash looks only at the value"
    In libc++, both specializations just return `static_cast<size_t>(value())`, without mixing in the category. So `error_code(2, system_category())` and `error_code(2, generic_category())` have the same hash but aren't equal. This is allowed, since hashing only requires equal objects to have equal hashes, but large numbers of error codes with the same value and different categories end up in the same bucket.

## Common misconceptions

!!! pitfall "Each shared library with its own copy of a category object"
    A category's identity is its address. If a category object is defined in an inline function in a header, Windows DLLs, or shared libraries compiled with `-fvisibility=hidden`, may each have their own copy. `error_code`s from two modules with the same category and value then compare unequal, and the `equivalent` mappings stop working. Category singletons should be defined and exported in one shared library.

!!! pitfall "Putting errno values in system_category"
    `errno` values belong to `generic_category`, while native error codes returned directly by operating system APIs belong to `system_category`. On POSIX the two have the same numbers, so mixing them usually happens to work; on Windows, `errno` values and Win32 error codes are two different numbering schemes.

!!! pitfall "Thinking `message()` can't throw"
    `message()` returns a `std::string` and may throw `bad_alloc`. Be careful calling it in `noexcept` destructors or error recovery paths.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[syserr.general] ¶2: the components of this subclause don't change the value of `errno`; *Recommended practice* suggests that implementations also leave other libraries' error state unchanged (for example, Windows' `GetLastError()`). The typical use is to read `errno` after a failed system call and then construct an `error_code`; if construction overwrote `errno`, it would break the caller's subsequent checks.

[system.error.syn] ¶1: the value of each `errc` enumerator is the same as the corresponding `<cerrno>` macro; whether `<system_error>` also provides these macros is unspecified, so to use `ENOENT`, include `<cerrno>` yourself. `errc` itself is freestanding.

[syserr.errcat.virtuals] ¶1 requires `name()` to return a string in the ordinary literal encoding; ¶5 requires `message(ev)` to return a multibyte string in the execution character set.

</details>

## Questions

!!! question "Question 1"
    `std::errc::timed_out` and `app_cond::retryable` from the example are two different `error_condition`s. Can one `error_code` equal both? Does this contradict `==` being an equivalence relation?

<details markdown="1">
<summary>Answer</summary>

Yes; `http_errc::timeout` in the example equals both. It isn't a contradiction: `error_code == error_condition` is a membership relation between two different types, like element and set, not an equivalence relation on a single type. `error_code` and `error_condition` have no common type and don't satisfy `equality_comparable_with` ([[concepts.compare]]), and the standard doesn't claim they do.
</details>

!!! question "Question 2"
    Why is the default category of `error_code` `system_category()`, while that of `error_condition` is `generic_category()`?

<details markdown="1">
<summary>Answer</summary>

A default-constructed object has the value 0, meaning no error. `error_code` holds errors that actually occurred, whose most common source is the operating system, so it defaults to `system_category`. `error_condition` represents portable conditions, and the standard vocabulary for portable conditions is `errc`, which is interpreted in `generic_category`, so it defaults to `generic_category`. With the value 0 neither is an error, and the difference in category is basically visible only when printing.
</details>

!!! question "Question 3"
    If the code's category considers `ec` to belong to `cond`, but `cond`'s category doesn't, what is the result of `ec == cond`?

<details markdown="1">
<summary>Answer</summary>

`true`. The comparison in [[syserr.compare#2]] is the logical OR of the two questions, so it is equal if either side accepts.
</details>
