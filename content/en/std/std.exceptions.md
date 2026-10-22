---
title: Exception classes
summary: "The nine exception classes of <stdexcept>: what errors the logic_error and runtime_error branches each report, the uniform constructor and what() requirements, why copying must not throw, and where the standard library throws which one."
updated: 2026-10-19
---

!!! tldr
    - The nine classes of `<stdexcept>` form two branches: `logic_error` (errors in program logic, preventable in theory) and `runtime_error` (events beyond the program's control). The classification is partly historical and isn't always strict.
    - All nine classes have the same interface: two `explicit` constructors taking `const string&` and `const char*`; no default constructor; `what()` returns a string with the same contents as the argument.
    - Standard library exception classes must not throw when copied, so implementations store the message in a reference-counted immutable string rather than a `std::string` member.
    - `bad_alloc`, `bad_cast` and others derive directly from `exception`, so `catch (const std::runtime_error&)` doesn't catch them.

## Who throws which

```cpp run title="who-throws-what.cpp" ok
#include <bitset>
#include <cstdio>
#include <future>
#include <stdexcept>
#include <string>
#include <vector>

template<class F> void probe(const char* name, F f) {
  try { f(); }
  catch (const std::logic_error& e) {
    std::printf("%-16s logic_error:   %s\n", name, e.what());
  }
  catch (const std::runtime_error& e) {
    std::printf("%-16s runtime_error: %s\n", name, e.what());
  }
}

int main() {
  probe("vector::at", [] {        // out_of_range
    std::vector<int> v; (void)v.at(1); });
  probe("stoi(\"x\")", [] {        // invalid_argument
    (void)std::stoi("x"); });
  probe("stoi(huge)", [] {        // out_of_range
    (void)std::stoi("99999999999"); });
  probe("vector::reserve", [] {   // length_error
    std::vector<int> v; v.reserve(v.max_size() + 1); });
  probe("bitset::to_ulong", [] {  // overflow_error
    std::bitset<128> b; b.set(100); (void)b.to_ulong(); });
  probe("get_future x2", [] {     // future_error
    std::promise<int> p;
    (void)p.get_future(); (void)p.get_future(); });
}
```

The text of `what()` is up to the implementation, so all that is guaranteed above is which `catch` each case lands in. The table lists typical throw sites in the standard library:

| Exception | Typical throw sites in the standard library |
|---|---|
| `out_of_range` | `at()` of the containers and `string`; out-of-range positions in `string::substr` and `insert`; `stoi` and friends when the result is out of range; `bitset::set(pos)` and others |
| `invalid_argument` | `stoi` and friends when no conversion can be performed; constructing a `bitset` from a string with invalid characters |
| `length_error` | A container's `reserve` or constructor requesting more than `max_size()`; a `string` growing beyond `max_size()` |
| `overflow_error` | `bitset::to_ulong` and `to_ullong` when the result doesn't fit |
| `domain_error`, `range_error`, `underflow_error` | The standard library itself hardly ever throws them; they are left for user code (`range_error` used to be thrown by `wstring_convert`, which was removed in C++26) |

Keep `length_error` and `bad_alloc` apart: a request exceeding `max_size()` is logically impossible and throws `length_error`; a request within it for which there isn't enough memory is run-time resource exhaustion and throws `bad_alloc`.

## Two kinds of error ([std.exceptions.general])

¶1 The standard library provides these classes for reporting certain errors in C++ programs ([[res.on.exception.handling]]). The error model they reflect divides errors into two broad categories: **logic errors** and **runtime errors**.

!!! std
    The distinguishing characteristic of logic errors is that they are due to errors in the internal logic of the program. In theory, they are preventable.

¶2 Logic errors are due to errors in the internal logic of the program and are preventable in theory. ¶3 Runtime errors, by contrast, are due to events beyond the scope of the program and can't be easily predicted in advance.

The practical test is whether the caller could have detected the problem before the call. `v.at(i)` throws `out_of_range`, and the caller could have checked `i < v.size()` first, so it is a logic error. Failing to open a file throws `filesystem_error` (derived from `runtime_error` via `system_error`), and whether the file exists isn't under the program's control, so it is a runtime error. The overflow in `bitset::to_ulong` could in fact also be checked in advance by the caller, yet it is classified as a runtime error, because arithmetic overflow is traditionally seen as an event occurring during computation.

!!! note "Why logic errors still throw"
    Logic errors are preventable in theory; that is, they are bugs. A caller usually doesn't know how to recover from its own bug, so the current view is that bugs should be reported with assertions or contracts ([[assertions]], [[basic.contract]]) and terminate early. The `logic_error` branch reflects C++98's design of reporting every error with exceptions. Newer standard library interfaces prefer to write such cases as preconditions, keeping `logic_error` only for interfaces such as `at()` that explicitly provide a checked version.

## Class hierarchy ([stdexcept.syn])

```text
exception                    <exception>, see [support.exception]
├── logic_error              errors presumably detectable before the program executes
│   ├── domain_error         domain errors
│   ├── invalid_argument     invalid arguments
│   ├── length_error         length exceeding the maximum allowable size
│   ├── out_of_range         argument not in its expected range
│   └── future_error         <future>
└── runtime_error            errors presumably detectable only when the program executes
    ├── range_error          range errors in internal computations
    ├── overflow_error       arithmetic overflow
    ├── underflow_error      arithmetic underflow
    ├── system_error         <system_error>, see [syserr]
    │   ├── ios_base::failure     <ios>
    │   └── filesystem_error      <filesystem>
    ├── format_error         <format>
    └── regex_error          <regex>
```

The synopsis of `<stdexcept>` declares only the first nine classes, with indentation hinting at the inheritance. The descriptions in the comments come from paragraph 1 of each class definition; for example, [[logic.error]] says it reports errors such as violations of logical preconditions or class invariants. Other standard library exceptions, such as `bad_alloc`, `bad_cast`, `bad_optional_access` and `bad_expected_access`, derive directly from `exception` and belong to neither branch.

## A uniform interface ([logic.error] through [underflow.error])

The specifications of the nine classes are nearly identical. Taking `logic_error` as an example:

```cpp
namespace std {
  class logic_error : public exception {
  public:
    constexpr explicit logic_error(const string& what_arg);
    constexpr explicit logic_error(const char* what_arg);
  };
}
```

¶2 and ¶3 of each class give the same postconditions: after construction from `const string&`, `strcmp(what(), what_arg.c_str()) == 0`, and after construction from `const char*`, `strcmp(what(), what_arg) == 0`. A few things follow:

1. There is no default constructor; a message must be given. [[exception#2]] says standard library classes derived from `exception` have a default constructor, except when the class synopsis lists other constructors, which is the case here.
2. The constructors are `explicit`. `throw std::runtime_error("x")` works; `std::runtime_error e = "x";` doesn't.
3. `what()` returns a copy of the message, whose lifetime is managed by the exception object. Modifying or destroying the original `string` after construction doesn't affect `what()`.

### Copying must not throw

Exception objects may be copied while being thrown and caught ([[except.throw]], [[except.handle]]). If copying needed to allocate memory, it could throw `bad_alloc` in the middle of handling an exception. So [[exception#2]] requires that every standard library class derived from `exception` have a copy constructor and copy assignment operator with non-throwing exception specifications, and that after copying `what()` have the same contents on both sides.

This means an implementation can't simply store the message in a `std::string` member.

!!! impl "libc++'s reference-counted string"
    libc++'s `logic_error` and `runtime_error` each have a `__libcpp_refstring` member, which is just a pointer to a heap block holding a reference count plus the string. Construction allocates once, which may throw `bad_alloc`, but that happens before the `throw`. Later copies just increment the reference count atomically and don't throw. The other seven classes inherit the storage of these two base classes. libstdc++ uses a similar copy-on-write string.

## C++26: `constexpr` constructors

In the current draft the constructors of all nine classes are `constexpr`, and so are the members of `exception` ([[exception]]). This goes with C++26 allowing exceptions to be thrown and caught during constant evaluation ([[P3068R6]]): a `std::out_of_range` thrown by a `constexpr` function no longer makes the evaluation fail if it is caught during constant evaluation.

```cpp
#include <stdexcept>
constexpr bool f() {
  try { throw std::logic_error("x"); }
  catch (const std::exception&) { return true; }
}
static_assert(f());   // per the current draft: OK
```

At the time of writing, Clang 23 doesn't support throwing exceptions during constant evaluation, not even `throw 1`, and reports that the `static_assert` expression isn't a constant expression. So the code above carries no verdict.

## Common misconceptions

!!! pitfall "Catching by value"
    `catch (std::exception e)` slices an `out_of_range` into an `exception` object, and `what()` becomes the base class version, returning an implementation-defined string. Catch by `const&`.

!!! pitfall "`catch (const std::runtime_error&)` catches all runtime errors"
    `bad_alloc`, `bad_cast` and `bad_optional_access` aren't in the `runtime_error` branch, and `future_error` is even in the `logic_error` branch. When you need a catch-all, catch `const std::exception&`.

!!! pitfall "Building the message can throw too"
    `throw std::runtime_error("open " + path + " failed")` constructs two temporary `string`s before throwing, and the exception object stores another copy. When memory is exhausted, building the message may throw `bad_alloc`, masking the original error.

## Questions

!!! question "Questions"
    1. Why does `std::system_error` derive from `runtime_error` rather than directly from `exception`?
    2. Does a custom exception class `struct my_error : std::runtime_error { std::string detail; };` violate the standard's requirements?
    3. After `std::logic_error e("x"); std::logic_error f = e;`, is `e.what() == f.what()` (comparing pointers) guaranteed to hold?

<details markdown="1">
<summary>Answer</summary>

1. A failed system call is a typical event beyond the scope of the program ([[std.exceptions.general]] ¶3), so putting it in the `runtime_error` branch fits the classification model. It also lets existing `catch (const std::runtime_error&)` handlers catch it, including `ios_base::failure`, which derives from `system_error` since C++11.
2. No. [[exception#2]] constrains standard library classes, not user classes. But it goes against the reasoning behind that constraint: copying a `std::string` member may throw `bad_alloc`. When catching by value, the handler's parameter is initialized from the exception object ([[except.handle]]), and `std::current_exception` may also copy it; if a function called by the exception handling mechanism after the exception object is initialized but before a handler is activated exits via an exception, `std::terminate` is called ([[except.terminate]]). User exception classes should preferably also hold only data that doesn't throw when copied, such as a `shared_ptr<const string>`, or put the information in the base class's `what_arg`.
3. Not necessarily. The standard requires only `strcmp(e.what(), f.what()) == 0`. On libc++ the two pointers happen to be equal because they share the same storage, but that is an implementation detail.
</details>
