---
title: "From Boost and TR1 to C++26: how the standard library grew"
summary: How the standard library grew after C++98: where its components came from, which designs patch older ones, why ABI compatibility makes existing components so hard to change, and the debate over whether the standard library should keep getting bigger.
tags: history, standard library, Boost, TR1, ABI, Ranges, format
updated: 2026-10-19
---

!!! tldr
    - Nearly every component added to the standard library after C++98 was first used for years in Boost, in a company code base or in the author's own open-source library, and then entered the standard through TR1, a TS or a direct proposal.
    - Many of today's components patch older designs: `unique_ptr` replaces `auto_ptr`, `move_only_function`/`function_ref` make up for `std::function`, `expected` avoids `variant`'s valueless state.
    - Once a component has been compiled into a large number of binaries, its memory layout and function signatures are very hard to change (the ABI constraint), so improvements tend to arrive as new types.
    - There is no consensus on how much the standard library should cover: networking and 2D graphics did not get in, while `hive`, `simd` and `linalg` went into C++26.
    - C++26 standard library hardening turns some precondition violations from undefined behavior into contract violations.

## Practice first, standard later

The C++98 standard library had only containers, iterators and algorithms (from the STL), iostreams, string, locale and the parts inherited from C. Hash tables, regular expressions, smart pointers, threads and filesystems were not in it.

Stroustrup recalls that as the 1998 standard was being wrapped up, the committee generally felt the library was not enough, and that the parts already approved lacked experimentation and performance measurement (HOPL III §4.2). Hash tables are one example: a hash table proposal was submitted in 1995, but the committee no longer had time for careful design. Implementations then each provided their own mutually incompatible `hash_map`, so standardization had to use a different name, which is where the name `unordered_map` comes from.

To avoid repeating this, committee members started **Boost** in 1998: a peer-reviewed collection of open-source libraries, with the explicit goal of building up existing practice for future standardization (HOPL IV §2.3). A library is first publicly reviewed in Boost and tested in real projects; a few years later its authors write a standard proposal backed by implementation experience. regex, thread, `shared_ptr`, variant and filesystem all followed this path.

Boost was not the only source, but later proposers widely adopted this pattern of practice first, standardization later: the precedents for string_view were in the code bases of Google, LLVM and Bloomberg, PMR came from Bloomberg, and {fmt}, range-v3 and date are all open-source libraries maintained by individual authors.

### TR1 and TSes: way stations outside the standard

A **technical report** is not a standard and has no normative force; its role is to write down a set of designs first so that implementers can implement them and users can try them. The first library technical report, TR1, was published in 2007, containing `shared_ptr`/`weak_ptr`, `function`/`bind`, `tuple`, `<type_traits>`, `<random>`, `array`, unordered containers and `<regex>`.

TR1 components were declared in the `std::tr1` namespace, and code at the time wrote `std::tr1::shared_ptr`. C++11 moved almost all of them into `std` and rewrote their interfaces using rvalue references and variadic templates: `tuple` no longer had to simulate variadic parameters, and `function` and `bind` supported perfect forwarding.

After C++11, extensions switched to topic-based **Technical Specifications** (TSes), such as the Filesystem TS, Library Fundamentals TS, Ranges TS and Networking TS. Implementers provided them under `std::experimental`, and the committee decided whether to merge them after gathering experience. Recent proposals more often target the International Standard directly; `format` and `expected` both abandoned the TS route partway.

## auto_ptr → unique_ptr: moving without move semantics

C++98's only smart pointer, `auto_ptr`, represented exclusive ownership. The language had no move semantics then, so it had to borrow the syntax of copying to transfer ownership:

<div class="compare" markdown="1">

```cpp title="C++98: copying transfers"
std::auto_ptr<int> a(new int(1));
std::auto_ptr<int> b = a;
// a has silently become a null pointer
```

```cpp title="C++11: transfer has to be spelled out"
std::unique_ptr<int> a(new int(1));
std::unique_ptr<int> b = std::move(a);
// std::unique_ptr<int> c = b;  // error
```

</div>

In [[N1856]] (2005), Howard Hinnant explained why the left side is unacceptable: generic code assumes that after a copy, source and target are equivalent. Put `auto_ptr`s in a container and sort it, and some `sort` implementation may copy an element into a local variable as the pivot, nulling out the element in the container; the result depends on the implementation and may even crash.

N1856's solution was to add `unique_ptr`, movable but not copyable, and leave ownership transfer to C++11's rvalue references. Code that would have silently transferred ownership now fails to compile:

```cpp run error
#include <memory>
#include <vector>
int main() {
    std::vector<std::unique_ptr<int>> v;
    v.push_back(std::make_unique<int>(1));
    auto q = v[0];   // error: unique_ptr's copy constructor is deleted
}
```

Because `unique_ptr` could directly replace `auto_ptr`, the committee had a rare opportunity to actually remove a flawed facility (HOPL IV §4.2.4). `auto_ptr` was deprecated in C++11 and removed in C++17 ([[N4190]], see [[diff.cpp14.depr]]). `make_unique` only arrived in C++14.

```cpp run error
#include <memory>
int main() {
    std::auto_ptr<int> p(new int(1));   // error: std::auto_ptr has been removed since C++17
}
```

!!! impl "The calling-convention cost of unique_ptr"
    At the source level `unique_ptr` is a zero-overhead abstraction, but under the mainstream Itanium C++ ABI, a class type with a non-trivial destructor passed by value must be passed through memory, not in registers. [[P1863R1]] lists this as a performance problem that cannot be removed because of ABI constraints; the ABI section below returns to this topic. See also [[toolchain/object-layout-and-vtables]].

## std::function and three new wrappers

`std::function` came from Boost.Function and entered C++11 through TR1. It is a [[g:type-erasure|type-erasing]] wrapper: any callable object with a matching signature can be stored in the same type `function<R(Args...)>`, at the cost of a possible heap allocation and an indirect call. It has two problems that were later discussed again and again.

First, `function` itself is copyable, so it requires the wrapped object to be copyable. A lambda that captured a `unique_ptr` won't fit:

```cpp run error
#include <functional>
#include <memory>
int main() {
    auto p = std::make_unique<int>(10);
    std::function<int(int)> g = [p = std::move(p)](int x) { return x + *p; };
    // error: std::function requires copyability, and this lambda is move-only
}
```

Second, its `operator()` is a `const` member function, yet it calls the wrapped object's non-`const` call operator, which is a hole in const-correctness.

Changing `std::function` would change the behavior of existing code and also break ABI, so the committee added new types:

| Type | Owns the object | Copyable | Version |
|---|---|---|---|
| `function` | Yes | Yes | C++11 |
| `move_only_function` | Yes | No | C++23 |
| `copyable_function` | Yes | Yes | C++26 |
| `function_ref` | No | Yes (shallow copy) | C++26 |

The last three allow `const`, `noexcept` and ref-qualifiers in the signature, for example `copyable_function<int(int) const>`, which fixes the const-correctness problem.

```cpp run
#include <functional>
#include <memory>
#include <print>
int call_twice(std::function_ref<int(int)> f, int x) { return f(f(x)); }   // doesn't own, doesn't allocate
int main() {
    auto p = std::make_unique<int>(10);
    std::move_only_function<int(int)> add = [p = std::move(p)](int x) { return x + *p; };
    std::println("{}", call_twice(add, 1));   // 21
}
```

This example is well-formed according to the standard, but the libc++ shipped with Clang 23 does not provide `move_only_function` and `function_ref` yet, so it has no verdict; you can use the godbolt button to verify it with GCC trunk.

Turning one type into four also drew criticism: in [[P3023R1]], David Sankel argued that this does nothing to reduce complexity. Supporters' reasoning is that their semantics really are different, and no single type can satisfy them all. The clause is [[func.wrap]].

## chrono: distinguishing units with types

C++11's thread library needed to express sleep durations and wait deadlines, and [[N2661]] (2008) proposed `duration`, `time_point` and clocks for this. Several of its design choices determine how `<chrono>` is used today.

**Precision neutrality.** `duration<Rep, Period>` represents units with the compile-time rational `ratio`; `hours` and `nanoseconds` are just different instances of the same class template.

**Only lossless implicit conversions.** Coarser units convert implicitly to finer ones; the other way requires `duration_cast`:

<div class="compare" markdown="1">

```cpp ok
#include <chrono>
using namespace std::chrono;
seconds s = hours(1);    // lossless
minutes m = duration_cast<minutes>(
    seconds(90));        // explicit truncation
int main() {}
```

```cpp error
#include <chrono>
using namespace std::chrono;
hours h = seconds(3600);
// error: a lossy conversion
// requires duration_cast
int main() {}
```

</div>

**No calendar.** N2661 has a section titled *Sold Separately*: it provides no calendar, specifies no epoch and does not handle leap seconds, promising only to be the foundation of a future date library. That calendar library was later completed by Hinnant himself as the open-source date/tz library, and entered C++20 through [[P0355R7]].

The calendar part continues the idea of preventing errors with types: `year`, `month`, `day` and `weekday` are each separate types, so something like `ymd + 10`, where it is unclear whether days, months or years are being added, is rejected; date conversions are `constexpr` (HOPL IV §9.3.6).

```cpp run ok
#include <chrono>
#include <print>
using namespace std::chrono;
static_assert(year_month_day{2016y / May / 29d}.ok());
static_assert(weekday{sys_days{2016y / May / 29}} == Sunday);   // day of the week computed at compile time
int main() {
    constexpr auto d = 2026y / October / 18d;
    std::println("{} is a {}", d, weekday{sys_days{d}});   // 2026-10-18 is a Sun
}
```

The clauses are [[time]], [[time.cal]] and [[time.zone]].

## Filesystem: two ways of reporting errors

`std::filesystem` came from Boost.Filesystem and was merged into C++17 through the Filesystem TS, an example of the TS mechanism working as designed.

One of its features is that most operations come in two versions: one throws `filesystem_error` on failure, the other takes an `error_code&` parameter and does not throw. Stroustrup's explanation is that errors in file operations are sometimes rare exceptional situations and sometimes expected outcomes (such as a file not existing), and both cases need to be served (HOPL IV §8.6). The clause is [[filesystems]].

## Vocabulary types: optional, variant, any, string_view

C++17 added a set of **vocabulary types** for passing data between interfaces. Most of them entered the standard through the Library Fundamentals TS.

The precedents for `string_view` were string reference types such as Google's `StringPiece` and LLVM's `StringRef`, used to avoid constructing a `std::string` just to pass an argument ([[N3921]]). It does not own the characters it refers to, so it is also a common source of dangling references (see [[topics/dangling-references]], [[string.view]]).

### variant's empty state

The longest debate in `variant`'s design was about exception safety during assignment. Suppose `v` holds an `S` and is to hold a `T` instead: `v` must first destroy the `S`, then construct the `T` in the same storage. If constructing the `T` throws, `v` holds neither an `S` nor a `T`. [[N4542]] discusses several ways out one by one:

- Require that constructing any alternative type never throws. This restriction is too strong, and which types satisfy it depends on the implementation.
- Double buffering: Boost.Variant constructs the new value in separate storage first, then destroys the old value once that succeeds. The cost is extra memory, and the address of the internal storage changes.
- Introduce a visible empty state, like a moved-from object: valid, but with unspecified contents.

The third was chosen in the end. In this state, `get` and `visit` throw `bad_variant_access` ([[P0088R3]]), and the query function is named `valueless_by_exception()`, a name that itself reminds you this state only comes from exceptions.

```cpp run ok
#include <variant>
#include <stdexcept>
#include <cstdio>
struct Bomb {
    Bomb() = default;
    Bomb(Bomb&&) { throw std::runtime_error("boom"); }
};
int main() {
    std::variant<int, Bomb> v = 42;
    try {
        v.emplace<Bomb>(Bomb{});   // destroys the int first, then initializes Bomb with a throwing move constructor
    } catch (const std::runtime_error&) {}
    std::printf("%d %d\n", v.valueless_by_exception(), v.index() == std::variant_npos);   // 1 1
}
```

### Three types, three interfaces

`optional`, `variant` and `any` were designed separately, and their interfaces differ a lot: getting the value is written `*opt`, `get<int>(var)` and `any_cast<int>(a)` respectively. Stroustrup calls this a classic example of design by committee and considers pattern matching the more fundamental solution (HOPL IV §8.3); the Direction Group's [[P2000R4]] also cites it as evidence of the standard library's lack of consistency. The clauses are [[optional]], [[variant]] and [[any]].

## PMR: allocators no longer change the container's type

C++98 allocators are a template parameter of the container, so changing the allocator changes the type: `vector<int, A1>` and `vector<int, A2>` cannot be assigned to each other, and a function taking `vector<int>` accepts neither.

[[N3916]] (Halpern) put the allocation strategy in a virtual base class, `memory_resource`, and used a fixed allocator type, `polymorphic_allocator`, to point at some resource at run time. That way all containers using PMR are the same type, for example `std::pmr::vector<int>`. The facility comes from Bloomberg's BSL library, used internally for more than ten years, and the proposal says it significantly improved testability (test resources can be injected).

```cpp run ok
#include <memory_resource>
#include <vector>
#include <cstddef>
#include <print>
int main() {
    std::byte buffer[1024];
    std::pmr::monotonic_buffer_resource arena(buffer, sizeof buffer);
    std::pmr::vector<int> v(&arena);   // takes memory from the buffer on the stack first, then asks the upstream resource
    for (int i = 0; i < 10; ++i) v.push_back(i);
    std::println("{}", v.size());      // 10
}
```

This trades a virtual function call for a single type, the same idea as `std::function` trading type erasure for a single type above. The clause is [[mem.res]].

## expected: errors as return values

`expected<T, E>` makes a value or an error into a return type. It took about eight years, from [[N4015]] in 2014 to being merged into C++23 in 2022. What was reviewed again and again was mainly its place among error-handling approaches: how it relates to exceptions, `error_code`, Boost.Outcome and the deterministic exceptions proposed at the time ([[P0709R4]]), and whether `E` should default to `std::error_code` (the final decision was no default).

Its design explicitly avoids `variant`'s empty state: [[P0323R12]] guarantees that an `expected` always holds either a `T` or an `E`, so users never have to deal with a valueless state. C++23 also gave `optional` and `expected` monadic operations such as `and_then`, `transform` and `or_else` ([[P0798R8]], [[P2505R5]]).

```cpp run ok
#include <expected>
#include <charconv>
#include <string_view>
#include <print>
enum class parse_error { not_a_number, out_of_range };
std::expected<int, parse_error> parse_int(std::string_view s) {
    int value{};
    auto [ptr, ec] = std::from_chars(s.data(), s.data() + s.size(), value);
    if (ec == std::errc::invalid_argument) return std::unexpected(parse_error::not_a_number);
    if (ec == std::errc::result_out_of_range) return std::unexpected(parse_error::out_of_range);
    return value;
}
int main() {
    auto doubled = parse_int("21").transform([](int x) { return x * 2; });
    std::println("{}", doubled.value_or(-1));          // 42
    std::println("{}", parse_int("abc").has_value());  // false
}
```

The clause is [[expected]].

## Ranges: sentinels and a second set of algorithms

The STL represents a sequence with a pair of iterators. [[N4128]] (Niebler, Parent, Sutton, 2014) proposed ranges as algorithm arguments while deliberately keeping iterators as the foundation, on the grounds that iterators have a solid track record as the basis for algorithms. The key change it introduced was the **sentinel**: the end of a range can have a different type from the iterator. That way, a sequence that runs until some predicate holds, or n elements from some point, does not need a fake end iterator.

Ranges depend on concepts, which only entered the language in C++20, so they were first published as the Ranges TS and then merged into C++20 by [[P0896R4]]. To avoid changing the behavior of old code, the existing algorithms such as `std::sort` were left alone, and a new set of constrained algorithms was provided in `std::ranges`. That is why the standard library has two sets of algorithms side by side today.

```cpp run ok
#include <ranges>
#include <vector>
#include <print>
int main() {
    std::vector<int> v{1, 2, 3, 4, 5, 6, 7, 8, 9, 10};
    auto r = v | std::views::filter([](int i) { return i % 2 == 0; })
               | std::views::transform([](int i) { return i * i; })
               | std::views::take(3);
    std::println("{}", r);                          // [4, 16, 36]
    auto w = std::views::zip(v, v | std::views::drop(1))
           | std::ranges::to<std::vector>();        // C++23
    std::println("{}", w.size());                   // 9
}
```

C++20 Ranges lacked many components already in range-v3. C++23 added `views::zip`, `ranges::to`, `views::chunk_by`, `ranges::fold_left` and others following the priorities in [[P2214R2]], and C++26 added `views::concat` and more. The clause is [[ranges]].

## format: type-safe format strings

iostreams are type-safe and extensible but weak at formatting; `printf` is convenient to write but does no type checking. `std::format` aims for both: format strings, while staying type-safe and extensible (HOPL IV §9.3.7). Its prototype is Victor Zverovich's open-source library {fmt}, merged into C++20 by [[P0645R10]].

Several design decisions made during review are visible in today's wording: Python-style `{}` rather than `%`; users extend formatting by specializing `std::formatter<T>`; no locale dependence by default; floating-point numbers are output by default in the shortest representation that round-trips exactly (Zverovich, *std::format in C++20*, 2019).

```cpp run ok
#include <format>
#include <string>
#include <print>
struct Point { int x, y; };
template <>
struct std::formatter<Point> : std::formatter<std::string> {
    auto format(Point p, auto& ctx) const {   // generic context: also formattable inside containers
        return std::formatter<std::string>::format(std::format("({}, {})", p.x, p.y), ctx);
    }
};
int main() {
    std::println("{}", std::format("{:>8}|{:<6.2f}|{:#x}", "abc", 3.14159, 255));   //      abc|3.14  |0xff
    std::println("{}", Point{1, 2});                                                // (1, 2)
}
```

When C++20 was first published, errors in format strings were only reported at run time, with exceptions. [[P2216R3]] changed the format string parameter to a `basic_format_string` constructed by a `consteval` constructor, checked at compile time, and applied retroactively to C++20 as a defect report:

```cpp run error
#include <format>
int main() {
    auto s = std::format("{:d}", "text");   // error: a string can't be formatted with d; rejected at compile time
}
```

C++23 added `std::print`/`std::println` and formatting of ranges. The clauses are [[format]] and [[print.fun]].

## After C++23: numerics and containers

After C++23, the growth of the standard library turned to high-performance computing and low-level containers. All of these components have long proposal histories.

| Component | Version | Notes |
|---|---|---|
| `mdspan` | C++23 | Multidimensional array view, does not own memory ([[views.multidim]]) |
| `linalg` | C++26 | Linear algebra based on BLAS, built on `mdspan` ([[linalg]]) |
| `simd` | C++26 | Data-parallel types, first tried out in Parallelism TS 2 ([[simd]]) |
| `inplace_vector` | C++26 | A variable-length array with capacity fixed at compile time and elements stored in place ([[inplace.vector]]) |
| `hive` | C++26 | A container where insertion and erasure don't invalidate iterators to other elements ([[hive]]) |

`mdspan`'s subscript syntax `m[i, j]` relies on a C++23 language change: `operator[]` can take multiple arguments ([[P2128R6]]). This is an example of library needs driving a language change.

```cpp run ok
#include <mdspan>
#include <vector>
#include <print>
int main() {
    std::vector<double> buf(6);
    std::mdspan m(buf.data(), 2, 3);           // 2 rows, 3 columns, row-major by default; doesn't own memory
    for (std::size_t i = 0; i < m.extent(0); ++i)
        for (std::size_t j = 0; j < m.extent(1); ++j)
            m[i, j] = 10.0 * i + j;
    std::println("{}", buf);                   // [0, 1, 2, 10, 11, 12]
}
```

At the time of writing, the libc++ we test with provides `mdspan`, but not yet `<linalg>`, `<simd>`, `<inplace_vector>` or `<hive>`.

## ABI: why existing components are so hard to change

**ABI** (application binary interface) refers to the conventions between compiled binaries: class memory layout, calling conventions, name mangling. The word ABI does not appear in the standard's text, but in practice it constrains the standard library: change a class's data members or a function's signature, and old and new code disagree at link time or run time (see [[toolchain/name-mangling]]).

### The C++11 break

C++11 prohibited reference-counted implementations of `basic_string` ([[diff.cpp03.strings]]) and required `list::size()` to be constant time ([[diff.cpp03.containers]]). For this, libstdc++ introduced a new `std::string` and `std::list` in GCC 5.1, and to keep old binaries working, it has provided both the old and the new ABI ever since (libstdc++ manual, *Dual ABI*). Implementers widely regard that break as expensive and painful, and later standards have tried to avoid breaking ABI ([[P1863R1]]).

### Improvements blocked by ABI

[[P1863R1]] (Winters, *ABI - Now or Never*, 2020) lists some performance that cannot be recovered because of this:

- The layout and hash functions of `unordered_map` and `std::hash`, where improvements would require recompiling all code;
- The cost of passing `unique_ptr` by value, determined by the calling convention;
- Tuning of `std::string`'s short string optimization.

`std::regex` is another example: improving its implementation usually requires changing class layouts or the signatures of internal templates, and these are already compiled into users' binaries. [[P3001R0]] lists `vector<bool>`, `unordered_map` and `regex` together as facilities that are not good enough, yet not broken enough to remove, and so must stay forever.

P1863R1 argued that the committee should pick one of two: schedule a version for an ABI break, or explicitly commit to ABI stability and tell users who need maximum performance to use external libraries. In 2020 the committee took a set of straw polls on this, and the result was to choose neither: no promise of permanent stability, and no large-scale break in C++23 (meeting minutes [[P2130R0]]). The later Direction Group documents [[P2000R4]] and [[P3466R1]] both take a case-by-case position: link compatibility with older C++ versions is the default requirement, and an individual proposal may break ABI, but the reasons must be explicitly discussed and recorded.

The practical effect is that the layout of existing components is very hard to change, and improvements tend to arrive as new types. The three wrappers after `function` are an example.

## Proposals that did not make it

**The Networking TS.** It is based on Asio, with more than a decade of production use, and was published as a TS in 2018. But it depended on executors, whose design kept changing; after the committee moved to the sender/receiver model in 2021, networking needed to be redesigned on the new model, and in the end it did not make it into C++26. The story is in [[history/executors-to-execution]].

**2D graphics.** The 2D graphics proposal based on Cairo ([[P0267R10]] and others) lost consensus to continue in 2018. According to the authors' retrospective ([[P0988R0]]), the objections included: the wording exceeded 140 pages, and reviewing it would take up a lot of committee time; some held that a graphics API does not belong in an International Standard, and others that this API was already outdated. The committee decided not to continue graphics work in any form at that time, and the reference implementation io2d continued as an independent project (Sutter, Rapperswil trip report, June 2018).

## Standard library hardening (C++26)

C++26 introduced the [[g:hardened-implementation|hardened implementation]]: whether an implementation is hardened is implementation-defined ([[intro.compliance#8]]). In a hardened implementation, violating a [[g:hardened-precondition|hardened precondition]] (such as the index range of `vector::operator[]`, or `optional::operator*` requiring a value) triggers a contract violation with a terminating semantic; in a non-hardened implementation it is still undefined behavior ([[structure.specifications#3.5]]).

```cpp ub
#include <vector>
#include <cstdio>
int main() {
    std::vector<int> v{1, 2, 3};
    std::printf("%d\n", v[3]);   // UB: out-of-bounds access in a non-hardened implementation; a contract violation in a hardened one, and the program terminates
}
```

With libc++, its hardening mode can be turned on with `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_FAST`. Compiled with Clang 23 at `-O2` with that macro, the example above terminates with a trap at the out-of-bounds access (exit code 133, i.e. SIGTRAP) and does not read out-of-bounds memory.

The design comes from libc++'s hardening modes ([[P3471R4]]). It only checks existing preconditions and adds no new ones; its overhead must be low enough to enable in production, and the paper cites a Google report that after deployment over hundreds of millions of lines of code, the performance impact was as low as 0.3%; and it is designed not to require ABI changes, so hardened and non-hardened code can be mixed in one program.

## How big should the standard library be?

The sections above keep returning to the same question: what belongs in the standard library? Each side's position is documented.

- **Restraint.** [[P3001R0]] argues that the standard library is good at facilities that need compiler support, vocabulary types, cross-platform operating system abstractions, and basic algorithms and data structures. The value of high-performance containers lies in keeping up with hardware, and standardization freezes both interface and ABI, so containers like `hive` are not a good fit for the standard library.
- **Expansion.** [[P2000R4]] recommends providing networking, simple graphics and support for modern hardware, partly for teaching: students should be able to start learning with only what every implementation provides.
- **Consistency.** P2000R4 also points out that components are polished in isolation and differ in style, the interfaces of optional/variant/any above being an example; it recommends that someone explicitly consider the interaction of each new feature with the others.

The disagreement is mainly about which category a particular component falls into, and where the committee's time should go first. Judging by the outcome, C++26 accepted `hive`, `simd` and `linalg`, and did not accept networking.

## Timeline

| Year | Event |
|---|---|
| 1998 | C++98; Boost founded |
| 2007 | TR1 published: smart pointers, `function`, `tuple`, `regex`, unordered containers |
| 2011 | C++11: TR1 merged into `std`; `unique_ptr`, `chrono`; `auto_ptr` deprecated |
| 2017 | C++17: filesystem, `optional`/`variant`/`any`, `string_view`, PMR; `auto_ptr` removed |
| 2020 | C++20: Ranges, `format`, calendars and time zones; ABI policy vote |
| 2023 | C++23: `expected`, `mdspan`, `print`, `move_only_function` |
| 2026 | C++26: `std::execution`, `linalg`, `simd`, `inplace_vector`, `hive`, `function_ref`, standard library hardening |

<details class="fine" markdown="1"><summary>Sources</summary>

- HOPL III: Bjarne Stroustrup, *Evolving a language in and for the real world: C++ 1991–2006* (2007), §4.2, §6.2.
- HOPL IV: Bjarne Stroustrup, *Thriving in a Crowded and Changing World: C++ 2006–2020* (2020), §2.3, §4.2.4, §8.3, §8.6, §9.3.6, §9.3.7.
- Victor Zverovich, *std::format in C++20* (2019).
- Herb Sutter's trip reports (herbsutter.com), for when each component was merged.
- The libstdc++ manual, section *Dual ABI*.
- Other WG21 papers are linked in the text.

</details>
