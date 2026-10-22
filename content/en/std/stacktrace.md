---
title: Stacktrace
summary: "C++23's <stacktrace> captures the current thread's call stack at runtime: a stacktrace is only an approximation of the invocation sequence; stacktrace_entry is a lightweight entry handle, basic_stacktrace is a read-only sequence container, and current() returns an empty object on failure instead of throwing."
updated: 2026-10-19
---

!!! tldr
    - `std::stacktrace::current()` captures the current thread's call stack. It is `noexcept` and returns an empty object on failure.
    - The standard defines a stacktrace only as an approximate representation of the invocation sequence: inlining, tail calls, and missing debug information can all make entries disappear, and all of that is conforming.
    - `stacktrace_entry` is a lightweight handle, cheap to copy and compare; the query functions return an empty string or 0 when no information is available, and throw only when out of memory.
    - `basic_stacktrace` is a read-only, allocator-aware sequence container; its `<=>` compares the lengths first, then the entries one by one.
    - libc++ (as tested with Clang 23) does not implement `<stacktrace>` yet; libstdc++ and the MSVC STL provide it.

{{c++23}} When a program fails, how it got to the failure point is often as useful as the error itself. Before C++23, getting the call stack meant relying on platform APIs (`backtrace()`, `CaptureStackBackTrace`) or third-party libraries (Boost.Stacktrace, cpptrace). [[P0881R7]] standardized it as `<stacktrace>`, and [[P2693R1]] added `std::format` support.

## An example

```cpp run title="stacktrace.cpp" cc=gsnapshot flags="-std=c++23 -g -lstdc++exp"
#include <cstdlib>
#include <print>
#include <stacktrace>

[[noreturn]] void fail(const char* msg) {
    auto st = std::stacktrace::current(1);        // skip fail itself
    std::println(stderr, "fatal: {}\n{}", msg, st);
    for (const auto& e : st)
        if (!e.source_file().empty())
            std::println(stderr, "  at {}:{}", e.source_file(), e.source_line());
    std::abort();
}

void parse(int x) { if (x < 0) fail("negative input"); }

int main() { parse(-1); }
```

`current(1)` captures the call stack and skips the innermost entry, which is `fail` itself. The whole stacktrace can be passed straight to `println`, or you can iterate over the entries and query each one's source file and line number.

Clang 23 with libc++ does not provide `<stacktrace>` (the `#include` fails with file not found, and `__cpp_lib_stacktrace` is commented out in `<version>`), so this example was not verified in our tests. The godbolt button opens it with GCC; libstdc++'s implementation needs an extra experimental support library at link time, currently `-lstdc++exp`.

## Invocation sequences and stacktraces [stacktrace.general]

¶1 The components in this subclause let a program store the stacktrace of the current thread of execution and query information about it at runtime.

¶2 First, the thing to be represented is defined at the level of the abstract machine:

!!! std
    The *invocation sequence* of the current evaluation x₀ in the current thread of execution is a sequence (x₀, …, xₙ) of evaluations such that, for i ≥ 0, xᵢ is within the function invocation xᵢ₊₁.

The **invocation sequence** ([[g:invocation-sequence]]) of the current evaluation x₀ is a sequence of evaluations (x₀, …, xₙ) in which each xᵢ happens within the function invocation xᵢ₊₁ ([[intro.execution]]). In other words, start from what is being done right now and trace back through who called it, all the way to the thread's initial function. The definition only involves the abstract machine; it has nothing to do with stack frames or registers.

¶3 A **stacktrace** is an approximate representation of an invocation sequence, consisting of **stacktrace entries** ([[g:stacktrace-entry]]), each representing one evaluation in it.

It can only be approximate, because optimized machine code does not correspond one-to-one with the abstract machine's invocation sequence:

- An inlined function has no stack frame of its own in the machine code and may vanish from the stacktrace; some implementations can recover inline frames from debug information.
- After tail-call optimization turns `return g();` into a jump, the caller's stack frame is replaced by `g`'s.
- With frame pointers omitted or no debug information, unwinding may be incomplete, and source files and line numbers may be unavailable.
- In a signal handler, or when the stack is already corrupted, unwinding itself may fail.

By using the word "approximate", the standard avoids having to guarantee anything in these cases and leaves the quality of the stacktrace to the implementation.

## Header synopsis [stacktrace.syn]

```cpp
namespace std {
  class stacktrace_entry;
  template<class Allocator> class basic_stacktrace;
  using stacktrace = basic_stacktrace<allocator<stacktrace_entry>>;
  namespace pmr {
    using stacktrace = basic_stacktrace<polymorphic_allocator<stacktrace_entry>>;
  }
  // plus swap, to_string, operator<<, formatter, hash
}
```

Capturing a stacktrace needs memory to store the entries, so `basic_stacktrace` takes an allocator. Where the global heap must be avoided, for example on a crash-handling path, `pmr::stacktrace` can be used with a buffer prepared in advance.

## `stacktrace_entry` [stacktrace.entry]

```cpp
class stacktrace_entry {
public:
  using native_handle_type = implementation-defined;

  constexpr stacktrace_entry() noexcept;
  constexpr stacktrace_entry(const stacktrace_entry& other) noexcept;
  constexpr stacktrace_entry& operator=(const stacktrace_entry& other) noexcept;
  ~stacktrace_entry();

  constexpr native_handle_type native_handle() const noexcept;
  constexpr explicit operator bool() const noexcept;

  string description() const;
  string source_file() const;
  uint_least32_t source_line() const;

  friend constexpr bool operator==(const stacktrace_entry& x, const stacktrace_entry& y) noexcept;
  friend constexpr strong_ordering operator<=>(const stacktrace_entry& x, const stacktrace_entry& y) noexcept;
};
```

¶1 ([stacktrace.entry.overview]) A `stacktrace_entry` object is either empty or represents a stacktrace entry. It models `regular` ([[concepts.object]]) and `three_way_comparable<strong_ordering>` ([[cmp.concept]]).

Entries are designed as lightweight values; in a typical implementation an entry is just an instruction address. Copying and comparing are cheap and never throw; expensive work such as translating the address into a function name or looking up debug information is deferred to the query functions and done on demand.

### Construction, observers, and comparison

- [stacktrace.entry.cons] ¶1: default construction yields an empty entry.
- [stacktrace.entry.obs] ¶1–¶2: the semantics of `native_handle()` are implementation-defined; for an entry that has not been modified, successive calls return the same value. ¶3: `operator bool` returns `false` if and only if the entry is empty.
- [stacktrace.entry.cmp] ¶1: `x == y` if and only if both represent the same entry, or both are empty. For `<=>`, only the return type `strong_ordering` is specified; the order is up to the implementation.

### Query [stacktrace.entry.query]

| Function | Returns |
|---|---|
| ¶2 `description()` | a description of the evaluation (usually the function name), or an empty string |
| ¶4 `source_file()` | the presumed or actual name of the source file that lexically contains the evaluation ([[cpp.predefined]]), or an empty string |
| ¶6 `source_line()` | 0, or a 1-based line number related to the evaluation |

Note 1 in ¶1 says the query functions treat all errors other than memory allocation errors as "no information available" and do not throw in that case. ¶3, ¶5, and ¶7 specify that they throw `bad_alloc` only when the internal data structures or the resulting string cannot be allocated.

A program compiled without debug information, stripped symbols, or an entry that falls in a system library without symbols all lead to "no information". So `source_file()` returning an empty string is a normal result, not an error.

¶6 also requires the file name and line number to agree: if `source_file()` returns a presumed name affected by a `#line` directive ([[cpp.line]]), `source_line()` returns the presumed line number too; if it returns the actual name, it returns the actual line number.

## `basic_stacktrace` [stacktrace.basic]

Internally, `basic_stacktrace` has a single exposition-only member `vector<value_type, allocator_type> frames_;`. Its `iterator` is the same as `const_iterator`, so the contents cannot be modified.

¶1 ([stacktrace.basic.overview]) It meets the requirements of a reversible container ([[container.rev.reqmts]]), an allocator-aware container ([[container.alloc.reqmts]]), and a sequence container ([[sequence.reqmts]]), with two exceptions: ¶1.1 only move, assignment, swap, and the operations supported for const-qualified sequence containers are supported, so there is no `push_back` or `erase`; ¶1.2 the semantics of the comparison functions differ from those required for containers, as described below.

### Capture: `current()` [stacktrace.basic.cons]

```cpp
static basic_stacktrace current(const allocator_type& alloc = allocator_type()) noexcept;
static basic_stacktrace current(size_type skip, const allocator_type& alloc = allocator_type()) noexcept;
static basic_stacktrace current(size_type skip, size_type max_depth,
                                const allocator_type& alloc = allocator_type()) noexcept;
```

¶1 `current()` returns an object holding a stacktrace of the current evaluation in the current thread; if initializing `frames_` fails, it returns an empty object. Note 1 says that on success, `frames_.front()` approximately represents the current evaluation and `frames_.back()` approximately represents the thread's initial function.

¶2–¶3 `current(skip)` behaves as if it first obtained the full stacktrace `t` and then initialized `frames_` from `t.begin() + min(n, skip)` to `t.end()`, that is, it skips the innermost `skip` entries. This is commonly used to leave out the logging or error-handling function itself.

¶4–¶6 `current(skip, max_depth)` additionally keeps at most `max_depth` entries after that. ¶5 is a hardened precondition (*Hardened preconditions*): `skip <= skip + max_depth`, i.e. the sum must not wrap around. In a hardened implementation ([[g:hardened-implementation]]) violating it is a contract violation; otherwise it is undefined behavior.

"As if it first obtained the full stacktrace" only describes the result. An implementation can skip the first `skip` frames directly while unwinding and stop once it has `max_depth` of them.

`current()` is `noexcept` because stacktraces are most often used on error-handling paths: just before throwing an exception, when an assertion fails, in a terminate handler. In those places, having the stacktrace capture itself throw would be dangerous, so the standard specifies that failure returns an empty object, and the caller just checks `empty()`.

¶7–¶9 Default construction and construction from just an allocator yield an empty object. ¶10 allows implementations to strengthen the exception specifications of copy, move, and assignment by making the result empty when allocation fails ([[res.on.exception.handling]]).

### Element access [stacktrace.basic.obs]

¶1 The iterators are random access iterators. ¶2–¶9: `get_allocator`, the `begin`/`end` family, `empty`, `size`, and `max_size` all forward to `frames_`.

¶10–¶12 `operator[](frame_no)` has the hardened precondition `frame_no < size()`, returns `frames_[frame_no]`, and does not throw. ¶13–¶14 `at(frame_no)` throws `out_of_range` when out of bounds.

### Comparison [stacktrace.basic.cmp]

¶1 `x == y` returns `equal(x.begin(), x.end(), y.begin(), y.end())`.

¶2 `x <=> y`: if the lengths differ, it returns `x.size() <=> y.size()`; if they are the same, it compares the entries lexicographically.

This is the "different semantics" ¶1.2 refers to. A container's `<=>` is purely lexicographic; here the lengths are compared first, so a shorter stacktrace always sorts first. Comparing lengths takes constant time and in most cases settles the result earlier.

Both comparison operators are templates and can compare stacktraces with different allocators, so `stacktrace` and `pmr::stacktrace` can be compared directly.

### Output [stacktrace.basic.nonmem]

¶2 `to_string(const stacktrace_entry&)` returns a string describing the entry; ¶3 recommends that it include the information from `source_file()` and `source_line()`. ¶4 `to_string(const basic_stacktrace&)` returns a string describing the whole stacktrace; Note 1 says the number of lines is not guaranteed to equal `size()`, as an implementation may print extra lines for inline frames or omit some lines. ¶5–¶6: both `operator<<` overloads are equivalent to outputting `to_string(...)`.

[stacktrace.format] ¶1–¶2: `formatter<stacktrace_entry>` accepts only fill, alignment, and width ([[format.string.std]]) and outputs `to_string(se)`; ¶3–¶4: the format specification for `formatter<basic_stacktrace<Allocator>>` must be empty, and it outputs `to_string(s)`.

[stacktrace.basic.hash] ¶1: `hash<stacktrace_entry>` and `hash<basic_stacktrace<Allocator>>` are both enabled ([[unord.hash]]).

## Common misconceptions

!!! pitfall "Capturing a stacktrace in a signal handler"
    `current()` allocates memory, and `description()` and friends read debug information; none of this is async-signal-safe. Using `std::stacktrace` in a `SIGSEGV` handler has no guarantee from the standard. `pmr::stacktrace` with a preallocated buffer reduces the risk, but symbolization should still be deferred to a safe context.

!!! pitfall "The stacktrace is empty in release builds"
    In an optimized build with stripped symbols, the stacktrace may be incomplete and `source_file()` may be empty for every entry. This is conforming. To get useful stacktraces in production, keep the debug information, or keep separate debug symbol files.

!!! pitfall "Parsing the output of `to_string`"
    The output format of `to_string`, `operator<<`, and `format` is entirely up to the implementation. When you need structured information, iterate over the entries and call `description()`, `source_file()`, and `source_line()` separately.

## Questions

!!! question "Question 1"
    Why are copying, comparison, and `native_handle()` of `stacktrace_entry` all `constexpr`, while `description()` is not?

<details markdown="1">
<summary>Answer</summary>

An entry is essentially an opaque handle, usually an address. Copying and comparing only operate on that handle and can happen during constant evaluation, for example on a default-constructed empty entry. `description()` and the like need to read the symbol table or debug information at runtime and return a dynamically allocated `string`, so they can only run at runtime.
</details>

!!! question "Question 2"
    What does `std::stacktrace::current(0, 0)` return? What about `current(1, std::numeric_limits<std::stacktrace::size_type>::max())`?

<details markdown="1">
<summary>Answer</summary>

`current(0, 0)` skips 0 entries and keeps at most 0, so the result is empty.

In the second call, `size_type` is an unsigned type, so `skip + max_depth` wraps around to 0, `skip <= skip + max_depth` is false, and the hardened precondition of [[stacktrace.basic.cons#5]] is violated: a contract violation in a hardened implementation, undefined behavior otherwise. If you want no depth limit, call `current(skip)`.
</details>

!!! question "Question 3"
    If `std::stacktrace::current()` is called twice in a row at the same place, are the resulting objects necessarily equal?

<details markdown="1">
<summary>Answer</summary>

Not necessarily. Capture can fail and return an empty object, so if one succeeds and the other fails, they are not equal. Two different calls in the source code are different evaluations to begin with, and their innermost entries differ. Even when the same call site (for example, in a loop body) is executed twice along the same call path, the results are usually equal in practice, but the standard defines a stacktrace only as an approximate representation and does not guarantee it.
</details>
