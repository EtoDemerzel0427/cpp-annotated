---
title: C++ and ISO C++ 2020
summary: "What previously valid code breaks or changes behavior when moving from C++20 to C++23: the identifier character set, implicit move, multidimensional subscripts, temporary lifetimes in range-based for, u8 literals initializing char arrays, inherited constructors in CTAD, compile-time checking in std::format, the rvalue overload of substr, the completion step of barrier, and more."
updated: 2026-10-19
---

!!! tldr
    - All temporaries in the initializer of a range-based `for` live until the loop ends. The code compiles as before, but destruction happens later, and a temporary holding a lock can cause a deadlock.
    - In `return x;`, a movable local variable or rvalue reference is now an xvalue directly, so a function returning `int&` can no longer simply `return` an `int&&` parameter.
    - `a[1, 2]` is no longer a comma expression but passes two arguments to `operator[]`, making room for the multidimensional subscripts of `std::mdspan`.
    - `std::format` checks the format string at compile time, bit-fields cannot be passed directly as arguments, and `bool` and characters cannot be used as dynamic widths. The major libraries already apply these under `-std=c++20` too.
    - For `std::move(s).substr(...)`, the source string is no longer guaranteed to be unchanged; when, and on which thread, the completion function of `std::barrier` runs is now more up to the implementation.

[diff.cpp20] lists the incompatibilities of C++23 relative to C++20: previously well-formed code that becomes ill-formed in C++23, or whose meaning changes. Every entry in the standard has the same format: the affected subclause, what changed, why, and the effect on old code.

¶1 This subclause lists differences in addition to those in the subclauses above; in other words, to upgrade from C++20 to the current draft you also need to read [[diff.cpp23]] and [[diff.cpp26]]. Entries follow the order of the chapters in the main text. All tests on this page use Clang 23.1.3 with libc++, comparing `-std=c++20` with `-std=c++23`.

## Lexical conventions [diff.cpp20.lex] {#diff.cpp20.lex}

### Identifiers use Unicode's XID properties

```cpp error
int a¨;   // error: U+00A8 is not XID_Continue
```

¶1 Since C++23, the first character of an identifier must have the Unicode property XID_Start or be `_`, the remaining characters must have XID_Continue, and the whole identifier must be in Unicode Normalization Form C (NFC) ([[lex.name]], [[uaxid]]). C++20 used its own table of code point ranges, which included many characters outside XID, such as the diaeresis ¨ in the example above.

The change keeps easily confused characters out of identifiers. NFC is required because the same accented letter can be encoded in two ways (one precomposed character, or a letter plus a combining mark); normalization guarantees that the same name is the same byte sequence in every translation unit, so the linker sees consistent symbols.

Clang 23 uses the new XID rules in all language modes but does not check NFC: a non-NFC identifier such as `e` followed by the combining accent U+0301 is accepted in every mode.

### Concatenated string literals cannot have conflicting encoding prefixes

```cpp error
auto c = L"a" U"b";   // error: conditionally-supported in C++20
```

¶2 Adjacent string literals are concatenated into one ([[lex.string]]). If both have encoding prefixes and they differ, C++20 made it **conditionally-supported** (an implementation may choose not to support it, and must diagnose it if it does not); C++23 makes it ill-formed. No implementation ever supported it, so this entry has no effect on real code. Concatenating a literal with a prefix and one without (`L"a" "b"`) is still valid.

## Expressions [diff.cpp20.expr] {#diff.cpp20.expr}

### Move-eligible id-expressions change from lvalues to xvalues

```cpp
decltype(auto) f(int&& x) { return (x); }   // C++23 returns int&&; C++20 returns int&
int& g(int&& x) { return x; }               // error: well-formed in C++20
```

¶1 When a function returns a local object, the compiler moves instead of copying where it can; this is **implicit move** ([[class.copy.elision]]). C++20 did this by first performing overload resolution treating the returned name as an rvalue, and if that failed, a second time treating it as an lvalue. C++23 switches to a simpler rule: if the operand of a `return` or `co_return` statement or a throw-expression is a move-eligible id-expression ([[g:move-eligible]]: it names a non-volatile object with automatic storage duration, or an rvalue reference to such an object), it is itself an xvalue ([[expr.prim.id.unqual]]).

The old two-phase rule was complicated and had holes: `int&& h(int&& x) { return x; }` did not compile in C++20, because when the return type is a reference that rvalue overload resolution is not performed, and `x` is still treated as an lvalue. Once it is an xvalue, code that relied on the name being an lvalue changes: in `f`, `decltype((x))` depends on the value category, and an xvalue gives `int&&`; in `g`, an xvalue cannot bind to `int&`.

When you really mean to return an lvalue reference, write `return static_cast<int&>(x);`. Clang 23 implements this, and the results in both modes match the comments above.

### Commas in subscripts

```cpp
int a[3];
int x = a[1, 2];     // error: in C++20 equivalent to a[(1, 2)]
int y = a[(1, 2)];   // OK: comma expression, gives a[2]
```

¶2 Since C++23, the comma in `a[x, y]` is no longer the comma operator but separates multiple arguments of the subscript operator ([[expr.sub]]). For a class type, `m[1, 2]` calls `m.operator[](1, 2)`, the syntax used for the multidimensional subscripts of `std::mdspan`. The built-in subscript operator takes only one argument, so writing this on an array is ill-formed.

C++20 had already deprecated unparenthesized comma expressions inside subscripts, and C++23 repurposes the syntax. If you really need the comma operator, add parentheses. Clang 23 gives a `-Wdeprecated-comma-subscript` warning under `-std=c++20` and an error under `-std=c++23`.

## Statements [diff.cpp20.stmt] {#diff.cpp20.stmt}

### Temporaries in a range-based `for` initializer live until the loop ends

```cpp run title="for_temp.cpp" ok
#include <cstdio>
#include <vector>
struct G { const char* n; ~G() { std::printf("~G %s\n", n); } };
std::vector<int> make(const G&) { return {1, 2}; }
int main() {
  for (int x : make(G{"temp"})) std::printf("x=%d\n", x);
}
```

The output on Clang 23 is below. Under `-std=c++20`, `~G temp` is printed before the loop starts; under `-std=c++23`, after the loop ends:

```text
-std=c++20      -std=c++23
~G temp         x=1
x=1             x=2
x=2             ~G temp
```

¶1 A range-based `for` is equivalent to first initializing a reference `auto&& __range` from the initializer and then iterating over it ([[stmt.ranged]]). In C++20, only the temporary bound directly to `__range` had its lifetime extended; the other temporaries in the initializer were destroyed when initialization finished. C++23 says that all temporaries created in the initializer live until the end of the whole loop ([[class.temporary]]).

This fixes a classic trap: in `for (auto x : make().items())`, the temporary returned by `make()` used to be destroyed before the loop started, leaving the reference returned by `items()` dangling, with undefined behavior. Under the new rule this is safe.

The cost is that some temporaries are destroyed later. If the destructor has side effects, such as unlocking, behavior changes. The standard's example:

```cpp
void f() {
  std::vector<int> v = { 42, 17, 13 };
  std::mutex m;

  for (int x : static_cast<void>(std::lock_guard<std::mutex>(m)), v) {
    // C++20: the temporary lock_guard above has already unlocked before the loop starts
    std::lock_guard<std::mutex> guard(m);   // C++23: m is still locked, deadlock
  }
}
```

Running this example on Clang 23, `-std=c++20` finishes normally and `-std=c++23` hangs. The compiler gives no diagnostic at all. When upgrading, check range-based `for` loops whose initializers contain temporaries such as locks or scope guards, and move them into named variables outside the loop.

## Declarations [diff.cpp20.dcl] {#diff.cpp20.dcl}

### UTF-8 string literals can initialize `char` arrays

```cpp error
struct A { char8_t s[10]; };
struct B { char s[10]; };

void f(A);
void f(B);

int main() {
  f({u8""});   // error: ambiguous; in C++20 only A matches
}
```

¶1 After C++20 changed the type of `u8"..."` to array of `const char8_t`, `char s[] = u8"x";` became ill-formed (see the [lex] section of [[diff.cpp17]]). For compatibility with old code, C++23 again allows UTF-8 string literals to initialize `char` and `unsigned char` arrays ([[dcl.init.string]]).

The side effect is that a `u8` literal can now initialize both a `char8_t` array and a `char` array. In the example above, `{u8""}` is viable for both aggregates, and what used to be the only choice becomes ambiguous. Naming the argument's type, for example `f(A{u8""})`, resolves it.

Clang 23 treats this as a defect fix: it reports the ambiguity under `-std=c++20` as well, and accepts `char a[] = u8"abc";` in both modes.

## Overloading [diff.cpp20.over] {#diff.cpp20.over}

### Class template argument deduction considers inherited constructors

```cpp error
template<typename T>
struct B { B(T); };

template<typename T>
struct D : B<T*> {
  D(T);
  using B<T*>::B;
  T m = "a";   // #1
};

D d("");   // error: T deduced as const char, #1 is ill-formed
           // C++20: T deduced as const char*, well-formed
```

¶1 When you write `D d("");` without template arguments, the compiler deduces `T` from the constructors; this is **class template argument deduction** (CTAD, [[over.match.class.deduct]]). Since C++23, base class constructors that a derived class template inherits with a using-declaration also take part in deduction. Since `D("")` can call the inherited `B(T*)`, deduction should consider it too.

In C++20 only `D(T)` takes part, and `T` is deduced as `const char*`. In C++23 the inherited `B(T*)` is a better match, `T` is deduced as `const char`, and the member `T m = "a";` is ill-formed. Writing the template argument or adding a deduction guide restores the original meaning.

Clang 23 does not implement this yet; both modes deduce `D<const char*>`.

## Templates [diff.cpp20.temp] {#diff.cpp20.temp}

### Deducing template arguments from exception specifications

```cpp error
template<bool> struct A { };
template<bool B> void f(void (*)(A<B>) noexcept(B));
void g(A<false>) noexcept;
void h() {
  f(g);   // error: well-formed in C++20
}
```

¶1 Since C++23, the `B` in `noexcept(B)` can be deduced ([[temp.deduct.type]]), so generic code can handle both throwing and non-throwing functions with a single template.

In C++20, `B = false` could only be deduced from `A<B>`; the parameter type is then an ordinary function pointer, a pointer to a `noexcept` function converts to it implicitly, and the call succeeds. In C++23, `B = true` is also deduced from `noexcept(B)`; the two deductions conflict and deduction fails. Writing `f<false>(g)` explicitly makes it compile.

Clang 23 deduces by the new rule under `-std=c++20` as well; both modes report an error.

## Library introduction [diff.cpp20.library] {#diff.cpp20.library}

¶1 C++23 adds the headers `<expected>`, `<flat_map>`, `<flat_set>`, `<generator>`, `<mdspan>`, `<print>`, `<spanstream>`, `<stacktrace>`, `<stdatomic.h>` and `<stdfloat>` ([[headers]]). If a project has a header with the same name and includes it with `#include <...>`, it may get the standard library's version; `<print>` and `<expected>` are the most common clashes.

## Concepts library [diff.cpp20.concepts] {#diff.cpp20.concepts}

### `equality_comparable_with` no longer subsumes `common_reference_with`

```cpp error
template<class T, class U>
  requires equality_comparable_with<T, U>
bool attempted_equals(const T&, const U& u);   // C++20 selects this one

template<class T, class U>
  requires common_reference_with<const remove_reference_t<T>&,
                                 const remove_reference_t<U>&>
bool attempted_equals(const T& t, const U& u);

bool test(shared_ptr<int> p) {
  return attempted_equals(p, nullptr);   // error: ambiguous; well-formed in C++20
}
```

¶1 When two overloads both satisfy their constraints, the more constrained one wins. Which is stronger is decided by whether one constraint **subsumes** the other, that is, whether after expansion it contains all of the other's atomic constraints ([[temp.constr.order]]). C++20's `equality_comparable_with<T, U>` contained `common_reference_with<...>` directly, so the first overload was more constrained and was selected.

C++23 replaces the `common_reference_with` in `three_way_comparable_with`, `equality_comparable_with` and `totally_ordered_with` with an exposition-only concept ([[cmp.concept]], [[concept.equalitycomparable]], [[concept.totallyordered]]), so that non-copyable, move-only types (such as `unique_ptr` compared with `nullptr`) can satisfy these concepts. The subsumption relation disappears with it, neither overload is more constrained, and the call becomes ambiguous.

libc++ treats this as a defect fix and reports the ambiguity under `-std=c++20` as well.

## Memory management library [diff.cpp20.memory] {#diff.cpp20.memory}

¶1 C++23 forbids programs from partially or explicitly specializing `allocator_traits` ([[allocator.traits.general]]), so that `allocate_at_least` and other future members can be added: a user's own specialization would lack these new members.

A program that violates this rule is **ill-formed, no diagnostic required** (IFNDR): the compiler need not report it, the code may compile as usual, but the standard no longer guarantees any result. Clang 23 gives no diagnostic at all for such a specialization. Customizations belong in the allocator type itself; `allocator_traits` reads the members of the same name from the allocator.

## General utilities library [diff.cpp20.utilities] {#diff.cpp20.utilities}

All four entries in this subclause are fixes to `std::format`. libc++ already has the new behavior under `-std=c++20`; the compile-time format string checking and the switch to forwarding references were applied retroactively to C++20 as defect reports.

### Format strings are checked at compile time

```cpp error
auto s = std::format("{:d}", "I am not a number");
// error: in C++20, throws format_error at run time
```

¶1 The format string parameter of `format`, `format_to`, `vformat_to`, `format_to_n` and `formatted_size` changes to type `format_string<Args...>` ([[format]]). Its constructor is `consteval`; it parses the format string at compile time and checks that it matches the argument types, so a wrong format string fails to compile. `format_args_t` is removed at the same time.

For format strings known only at run time, use `std::vformat(fmt, std::make_format_args(args...))`, or C++26's `std::runtime_format`.

### Bit-fields cannot be passed directly as format arguments

```cpp
struct tiny { int bit: 1; };
auto t = tiny();
std::format("{}", t.bit);    // error: in C++20 returns "0"
std::format("{}", +t.bit);   // OK: copied to an int first
```

¶2 The argument type of `format` and related functions changes from `const Args&...` to the forwarding reference `Args&&...` ([[format]]), which is needed to format views that cannot be iterated or copied when const, such as `filter_view`. A non-const reference cannot bind to a bit-field, so passing a bit-field becomes ill-formed; make a copy first.

### Dynamic width and precision accept only integer types

```cpp
std::format("{:*^{}}", "", true);   // error: in C++20 returns "*"
std::format("{:*^{}}", "", '1');    // error: in C++20 the number of characters output is implementation-defined
```

¶3 In the format string `{:*^{}}`, the inner `{}` means the width is taken from the next argument. C++23 requires that argument to be a standard signed or unsigned integer type; neither `bool` nor character types are allowed ([[format.string.std]]), because as a width or precision they have no useful, portable meaning. libc++ rejects both lines at compile time in both modes.

### `formatter<const charT[N], charT>` removed

¶4 C++23 removes the specialization `formatter<const charT[N], charT>` ([[format.formatter.spec]]). `formatter` is designed to be instantiated only with cv-unqualified object types, and this specialization did not fit. Ordinary `std::format("{}", "abc")` is unaffected; only code that uses this specialization directly breaks.

## Strings library [diff.cpp20.strings] {#diff.cpp20.strings}

### The rvalue overload of `substr`

```cpp
std::string s1 = "some long string that forces allocation", s2 = s1;
std::move(s1).substr(10, 5);
assert(s1 == s2);   // C++23: unspecified; C++20: always holds
std::string s3(std::move(s2), 10, 5);
assert(s1 == s2);   // likewise
```

¶1 C++23 adds a `substr(...) &&` overload to `basic_string`, and a matching constructor `basic_string(basic_string&&, size_type pos, size_type n, ...)` ([[string.classes]]). When taking a substring of a string that is about to be destroyed, its buffer can be reused directly, saving an allocation.

The cost is that after calling `substr` on an xvalue the source string is in a valid but unspecified state, whereas C++20 guaranteed it was unchanged. In our tests libc++ does empty `s1` under `-std=c++23` (`s1.size()` is 0), while under `-std=c++20` it is still 39. Only code that keeps using `s` after calling `substr` on `std::move(s)` is affected, and such code already violates the convention of not using an object after moving from it.

## Containers library [diff.cpp20.containers] {#diff.cpp20.containers}

### Heterogeneous `erase` and `extract` for associative containers

```cpp error
struct B {
  auto operator<=>(const B&) const = default;
};

struct D : private B {
  void f(std::set<B, std::less<>>& s) {
    s.erase(*this);   // error: well-formed in C++20
  }
};
```

¶1 When the comparator is transparent (has an `is_transparent` member, as `std::less<>` does), C++23 adds template overloads `erase(K&&)` and `extract(K&&)` accepting any key type to associative and unordered containers ([[associative.reqmts]], [[unord.req]]), so erasing does not require constructing a `key_type` object first.

A template overload is an exact match for the argument and beats the original `erase(const key_type&)`, which needs a conversion. In the example above, `D` inherits privately from `B`, and the conversion from `D` to `B` is accessible only inside `D`. In C++20 the conversion happened at the call site, which was fine; now it happens inside the library, where it is inaccessible, and the program is ill-formed. Converting at the call site (`s.erase(static_cast<const B&>(*this))`) fixes it.

libc++ in our tests does not implement heterogeneous `erase` yet and accepts this code in both modes.

## Concurrency support library [diff.cpp20.thread] {#diff.cpp20.thread}

### The phase completion step of `barrier`

```cpp
auto b0 = std::barrier(1);
b0.arrive();
b0.arrive();         // C++23: implementation-defined; C++20: well-defined

int data = 0;
auto b1 = std::barrier(1, [&]() noexcept { data++; });
b1.arrive();
assert(data == 1);   // C++23: implementation-defined; C++20: well-defined
b1.arrive();         // likewise
```

¶1 `std::barrier` lets a group of threads synchronize in phases: in each phase, once all participants have arrived, a **phase completion step** runs, which calls the completion function given at construction, and then the next phase begins ([[thread.barrier]]).

C++20 said the completion step always runs, and runs on the last thread that calls `arrive` or `arrive_and_drop` in that phase. C++23 changes this: if no thread calls `wait` in a phase, whether the completion step runs is implementation-defined; when it runs, it may run on any thread that arrived or waited in that phase. This both fixes the original self-contradictory wording and leaves room for implementation optimizations.

Code that relies on the completion function running exactly once, running on a particular thread, or running even without a call to `wait` may change behavior. The portable approach is for participating threads to use `arrive_and_wait`, or to call `wait` after arriving. In our tests libc++ runs the completion function at `arrive` in both modes, and `data` is 1.

## Summary

| Entry | Fate of old code | Clang 23 / libc++ |
|---|---|---|
| identifiers: XID, NFC | ill-formed | XID implemented and used in all modes; NFC not checked |
| `L"a" U"b"` | ill-formed | always rejected |
| implicit move yields an xvalue | changed meaning or ill-formed | implemented |
| `a[1, 2]` | ill-formed or changed meaning | implemented |
| range-based `for` temporaries | destroyed later, no diagnostic | implemented |
| `u8` literal initializing a `char` array | ambiguity | implemented, same in C++20 mode |
| inherited constructors in CTAD | ill-formed or changed meaning | not implemented |
| deduction from `noexcept(B)` | ill-formed | implemented, same in C++20 mode |
| subsumption of comparison concepts | ambiguity | implemented, same in C++20 mode |
| specializing `allocator_traits` | IFNDR | no diagnostic |
| the four `std::format` entries | ill-formed | implemented, same in C++20 mode |
| `substr() &&` | source string state unspecified | implemented |
| heterogeneous `erase` | ill-formed | not implemented |
| `barrier` completion step | implementation-defined | behavior unchanged |
