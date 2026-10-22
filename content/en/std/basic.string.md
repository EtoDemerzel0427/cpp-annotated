---
title: Class template basic_string
summary: "The members of basic_string: the null-terminator invariant, the strong exception guarantee, invalidation rules broader than vector's and the small string optimization, and the rules and pitfalls of each group of members: construction, capacity, element access, modifiers and searching."
updated: 2026-10-19
---

!!! tldr
    - `basic_string` is a contiguous container, and `data()[size()]` is always a real null character; changing it to any other value is undefined behavior.
    - When any member function throws, the string is left unchanged (strong exception guarantee).
    - Apart from `operator[]`, `at`, `data`, `front`, `back`, `begin`, `end`, `rbegin` and `rend`, calling any non-const member may invalidate pointers and iterators to characters, even when capacity suffices. This leaves room for the small string optimization.
    - Construction from `string_view` is `explicit`; `std::string s{3, 'x'}` gives two characters; `s = 65` compiles and yields `"A"`.
    - Most members have a template overload accepting any type convertible to `string_view`, with semantics determined by [[string.view]].

`std::string` is an alias for `basic_string<char>`. The member functions of `basic_string` have over a hundred overloads, but most are different entry points to the same thing: the standard defines almost every operation as constructing a `basic_string_view` first and then calling one core version. The non-member functions (`operator+`, comparison, I/O, `erase`), `stoi` and `to_string`, `hash`, and the `""s` literal are covered in [[string.classes]].

## The terminating null character [basic.string.general]

```cpp run ok
#include <string>
#include <cassert>

int main() {
  std::string s(3, 'x');
  assert(s[s.size()] == '\0');   // reading the terminating null: OK
  s[s.size()] = '\0';            // writing charT(): OK
  // s[s.size()] = 'y';          // UB
  assert(s.size() == 3);
}
```

¶1 `basic_string` stores a variable-length sequence of char-like objects ([[g:char-like-type]]) with the first element at position 0. ¶2 It is a contiguous container ([[container.reqmts]]), so `&s[0] + i == &s[i]`, and `data()` can be handed directly to C interfaces.

¶3 is the central invariant of this class:

!!! std
    In all cases, `[data(), data() + size()]` is a valid range, `data() + size()` points at an object with value `charT()` (a "null terminator"), and `size() <= capacity()` is true.

Note that `[data(), data() + size()]` is a closed range. The trailing **null terminator** ([[g:null-terminator]]) is a real object, not a value produced on the fly when read. That is why `c_str()` can be constant-time and `noexcept`, and why `s[s.size()]` can return a reference.

The last sentence of ¶3 says that changing the null terminator to any value other than `charT()` is {{ub}}: a later `c_str()` would return a sequence without a proper terminator. Writing `charT()` itself is allowed.

"In all cases" includes empty strings and moved-from strings. `std::string{}.c_str()` points to a null character, whereas `std::string_view{}.data()` is a null pointer ([[string.view]]).

The type members `size_type`, `difference_type`, `pointer` and the rest all come from `allocator_traits<Allocator>`. With an allocator using fancy pointers, `pointer` is not `charT*`, but `data()` still returns `charT*` ([[string.accessors#1]] defines it via `to_address(begin())`). `npos` is `size_type(-1)`, meaning both "not found" and "until the end".

## General requirements [string.require]

¶1 Any operation that would make `size()` exceed `max_size()` throws `length_error`. With libc++ in our tests, `max_size()` is 9223372036854775790, about 2^63.

¶2 The whole class provides the strong exception guarantee:

!!! std
    If any member function or operator of `basic_string` throws an exception, that function or operator has no other effect on the `basic_string` object.

This is achievable because char-like types are trivial and traits operations do not throw ([[char.traits]]). Apart from allocating memory, no step of a string operation can fail, so an implementation can allocate the new buffer first and replace the old one only after that succeeds. `vector::insert`, by contrast, has only the basic guarantee, because copy-constructing an element may throw.

¶3 Each object allocates and deallocates storage with `Allocator`, and `traits` must meet the character traits requirements. Two notes add:

- `basic_string` is an allocator-aware container ([[container.alloc.reqmts]]), but does not use the allocator's `construct` and `destroy`; characters do not go through uses-allocator construction.
- If `Allocator::value_type` or `traits::char_type` differs from `charT`, the program is ill-formed.

### Invalidation rules broader than vector's [string.require]

```cpp run ub
#include <string>
#include <cstdio>

int main() {
  std::string s(40, 'x');
  const char* p = s.c_str();
  s += " grows past capacity and reallocates";
  std::printf("%c\n", *p);    // UB: p is invalid; ASan reports heap-use-after-free
}
```

¶4 References, pointers and iterators referring to the characters of a `basic_string` may be invalidated by two kinds of use:

- ¶4.1 passing the string as a non-const reference argument to any standard library function. A footnote gives `swap`, `operator>>` and `getline` as examples.
- ¶4.2 calling any non-const member function except `operator[]`, `at`, `data`, `front`, `back`, `begin`, `rbegin`, `end` and `rend`.

This is much broader than for `vector`. `vector::push_back` invalidates iterators only on reallocation ([[sequence.reqmts]]), while `string::push_back` may invalidate them whether or not capacity suffices; the standard makes no finer distinction, and programs cannot rely on the behavior when capacity is sufficient. Const members such as `c_str()` and `size()` are outside this rule and invalidate nothing.

!!! note "Why the rule is like this: COW and SSO"
    C++98's rule was even broader, to allow copy-on-write (COW): several strings share a reference-counted buffer, and even non-const access like `operator[]` could trigger a copy and thus invalidate iterators. C++11 took `operator[]`, `begin` and the like off the invalidation list, which, together with the concurrency requirements, effectively ruled out COW.

    But the standard did not restrict invalidation to reallocation, and that leaves room for the **small string optimization** (SSO, [[g:short-string-optimization]]): the characters of a short string are stored inside the `string` object, so when the string is moved or swapped, the characters must change address. That is why [[string.cons#30]] says move assignment may invalidate iterators, and why, although containers in general guarantee that `swap` does not invalidate iterators ([[container.reqmts#66.6]]), the footnote to ¶4 names `basic_string::swap()` specifically.

    The standard permits SSO but does not require it. libc++, libstdc++ and the MSVC STL all implement it.

## Small string optimization: measuring libc++

Measured on Apple arm64 with Homebrew Clang 23 + libc++:

| Item | Result |
|---|---|
| `sizeof(std::string)`, `sizeof(std::u16string)`, `sizeof(std::u32string)` | all 24 |
| `capacity()` of an empty `string`, `u16string`, `u32string` | 22, 10, 4 |
| A `string` of 22 characters | characters inside the object, starting at offset 0 |
| A `string` of 23 characters | heap-allocated, `capacity() == 24` |
| Capacity growth under repeated `push_back` | 22 → 47 → 95 → 191 → 383 → 767 |
| Source object after move construction | `size() == 0`, `capacity() == 22` |
| `string(100, 'x')`, then `resize(5)`, then `shrink_to_fit()` | `capacity() == 22`, back inside the object |

Internally, libc++'s `basic_string` is a union. Long mode stores three words: data pointer, size and capacity; short mode treats the same 24 bytes as a character array plus one byte holding the length and the flag that distinguishes the two modes. 24 bytes minus one length byte is 23 `char`s, minus the terminating null, which gives the short-mode capacity of 22.

There are two layouts for where the flag lives, selected by `_LIBCPP_ABI_ALTERNATE_STRING_LAYOUT`. The default layout (Linux x86-64 and others) puts the flag in the first byte, so short-mode characters start at offset 1; the alternate layout (Apple arm64 and others, as in our tests) puts the flag in the last byte, so characters start at offset 0. Both layouts use a bit of the capacity that can never be used otherwise to store the flag.

Other implementations, not tested here and for reference only: libstdc++'s and the MSVC STL's `std::string` are both 32 bytes, with a short-mode capacity of 15.

!!! impl "How SSO affects code"
    - The `data()` of a short string points into the `string` object itself. A dangling pointer left after a short string is destroyed or moved from points onto the stack or into another object, and AddressSanitizer often cannot detect it (see the dangling example in [[string.view]]).
    - Swapping two short strings copies 24 bytes rather than swapping three pointers. That is still constant time and meets the requirement in [[string.swap#4]].
    - A function returning a short string does no heap allocation at all.

## Construction and assignment [string.cons]

### Some error-prone constructions

```cpp run ok
#include <string>
#include <cassert>

int main() {
  std::string a(3, 'x');      // "xxx": n copies of c
  std::string b{3, 'x'};      // "\3x": initializer_list<char>, two characters
  std::string c{65, 'x'};     // "Ax"
  assert(a == "xxx" && b.size() == 2 && c == "Ax");
}
```

¶19 `(n, c)` constructs `n` copies of `c`. Brace initialization, however, prefers the `initializer_list` constructor (¶23, [[over.match.list]]); `3` and `65` are both constant expressions convertible to `char` without narrowing, so `{65, 'x'}` is a list of two characters. `std::vector<int>{3, 1}` has the same problem.

<div class="compare" markdown="1">

```cpp run ok
#include <string>
#include <string_view>
int main() {
  std::string_view sv = "abc";
  std::string s1(sv);   // OK: direct-initialization
  (void)s1;
}
```

```cpp error
#include <string>
#include <string_view>
void f(const std::string&);
void g(std::string_view sv) {
  std::string s2 = sv;  // error: explicit
  f(sv);                // error: no silent allocation
}
```

</div>

¶11 The template constructing from a `string_view`-like object has two constraints: `const T&` is convertible to `basic_string_view<charT, traits>`, and is not convertible to `const charT*`. It is `explicit`. This is the design of [[P0254R2]]: `string` to `string_view` is cheap, so it is implicit; `string_view` to `string` allocates, so it must be written explicitly. The second constraint excludes `const char*`, so literals keep using the implicit `const charT*` constructor.

Since C++23, `basic_string(nullptr_t)` is deleted ([[P2166R1]]), and `std::string s = nullptr;` does not compile. In our tests `std::string s = 0;` is rejected too, with a diagnostic pointing at this deleted constructor: `0` is a null pointer constant, and converting it to `nullptr_t` and to `const char*` are both null pointer conversions. Whether overload resolution ends up ambiguous or selects the deleted function, the program is ill-formed.

!!! pitfall "s = 65 gives the character A"
    `operator=(charT c)` (¶35) accepts any value implicitly convertible to `char`. `std::string s; s = 65;` compiles, without a warning even under Clang 23 with `-Wall -Wextra -pedantic`, and yields `"A"`. A common source is meaning to write `s = std::to_string(n)` and writing `s = n` instead.

### The other constructors

- ¶1 `basic_string(const Allocator&)` constructs an empty string, `noexcept`.
- ¶2–¶3 Copy and move construction. Move construction is `noexcept`, and the source is left in a valid but unspecified state ([[g:valid-but-unspecified-state]]); in libc++ it becomes empty.
- ¶4–¶8 Construction from `[pos, pos + rlen)` of another string; `n` beyond the remaining length is truncated, and `pos > size()` throws `out_of_range`. C++23 added versions taking `basic_string&&` ([[P2438R2]]), and ¶8 recommends that, when the allocators are equal, the source's buffer be taken over directly with no new allocation.
- ¶13–¶15 The precondition of `(const charT* s, size_type n)` is that `[s, s+n)` is valid; it may contain null characters. ¶17 `(const charT* s)` is equivalent to `basic_string(s, traits::length(s), a)`.
- ¶20–¶21 The iterator-pair constructor requires arguments that qualify as input iterators, so `string(5, 'x')` does not pick it by mistake. ¶22 C++23 added a `from_range_t` version.
- ¶24–¶25 Copy and move construction with an allocator. When the allocators are equal, move construction with an allocator does not throw.

Among the deduction guides in ¶26–¶27, the single-argument version deducing from `basic_string_view` is `explicit`: `std::basic_string a(sv);` deduces `std::string`, and `std::basic_string b = sv;` does not compile.

### Assignment

- ¶28 Copy assignment. Self-assignment has no effect.
- ¶30 Move assignment works as for sequence containers, except that iterators, pointers and references may be invalidated, because of SSO as above. It is `noexcept` when the allocator has `propagate_on_container_move_assignment` or `is_always_equal`.
- ¶32–¶33 Assignment from a `string_view`-like object, with the same constraints as construction.
- ¶34 `operator=(const charT*)`; `operator=(nullptr_t)` is deleted.
- ¶35 `operator=(charT c)` is equivalent to assigning a view of length 1.

## Capacity [string.capacity]

### reserve no longer shrinks

!!! std
    Following a call to `reserve`, `capacity()` is greater or equal to the argument of `reserve` if reallocation happens; and equal to the previous value of `capacity()` otherwise.

¶14 Since C++20, `reserve` reallocates only when the current capacity is less than the argument, and does nothing when the argument is smaller ([[P0966R1]]). Before that, `s.reserve()` (with the argument defaulting to 0) was a non-binding shrink request; the no-argument version was deprecated in C++20 and later removed. Now shrinking is done only with `shrink_to_fit()`. ¶15 An argument greater than `max_size()` throws `length_error`. With libc++ in our tests, `capacity()` is 103 after `reserve(100)`.

¶16–¶18 `shrink_to_fit()` is a non-binding request to reduce capacity and never increases it; if it reallocates, all references, pointers and iterators (including the past-the-end iterator) are invalidated. libc++ moves the contents back into the in-object SSO buffer when they fit.

¶19 `clear()` is equivalent to `erase(begin(), end())`; it does not free memory, and `capacity()` is unchanged.

¶1–¶6 `size()` and `length()` are constant time; `resize(n, c)` truncates or appends `c`, and `resize(n)` fills with `charT()`.

### resize_and_overwrite {{c++23}}

```cpp run ok
#include <string>
#include <cstdio>
#include <cassert>

int main() {
  std::string s;
  s.resize_and_overwrite(32, [](char* p, std::size_t n) {
    return std::snprintf(p, n + 1, "%d-%d", 12, 34);   // may write n+1 characters, including the terminating null
  });
  assert(s == "12-34" && s.size() == 5);
}
```

Allocating a buffer, handing it to a C interface to fill in, and then setting the actual length is a very common pattern. Doing it with `resize(n)` first zeroes the buffer for no purpose. C++23's `resize_and_overwrite(n, op)` ([[P1072R10]]) skips that step. ¶7–¶10 lay out its contract:

- `op` receives a pointer `p` and a length `m == n`. `[p, p+n]` is a valid closed range, so `op` may write `p[n]`, which is exactly what `snprintf` needs. The first `min(size(), n)` characters are the original contents; the other positions may have indeterminate values ([[basic.indet]]).
- ¶8 The return value of `op` must be of integer-like type.
- ¶9 `op` must not throw and must not modify `p` or `m`; its return value `r` satisfies `0 <= r <= m`; no indeterminate values may remain in `[p, p+r)`.
- ¶10 The string's contents become `[p, p+r)`, and all pointers and references into `[p, p+n]` are invalidated, so `op` must not store `p` for later use.

Violating any of these preconditions is {{ub}}, with no hardening check. `op` throwing is also UB, an exception to the strong exception guarantee: if `op` has written halfway, the implementation has no way to roll back.

## Element access and iterators [string.access]

| Member | Precondition | On violation |
|---|---|---|
| `operator[](pos)` | hardened: `pos <= size()` (¶1) | contract violation in a hardened implementation, otherwise {{ub}} |
| `at(pos)` | none | throws `out_of_range` if `pos >= size()` (¶6) |
| `front()`, `back()` | hardened: `!empty()` (¶7, ¶9) | same as `operator[]` |

`operator[]` allows `pos == size()` and returns a reference to the terminating null, while `at(size())` throws: the two boundaries differ by one. C++26 marks these as hardened preconditions ([[P3471R4]], see [[structure.specifications]]): a hardened implementation must check them and treat violations as contract violations. libc++ selects the hardening mode with the macro `_LIBCPP_HARDENING_MODE`, off by default in our tests.

In [string.iterators], `end()` points at the position of the terminating null, but dereferencing `end()` is still out of bounds; to read the null, use `s[s.size()]`. libc++'s `string::iterator` is the wrapper type `__wrap_iter<char*>`.

## Modifiers [string.modifiers]

### Template overloads accepting string_view-like objects

`operator+=`, `append`, `assign`, `insert`, `replace`, the `find` family and `compare` all have a template overload like this:

```cpp
template<class T> constexpr basic_string& append(const T& t);
// Constraints: is_convertible_v<const T&, basic_string_view<charT, traits>> is true
//              and is_convertible_v<const T&, const charT*> is false
```

Why not simply a non-template function taking `basic_string_view`? Then `s.append("abc")` would be ambiguous between `append(const charT*)` and `append(basic_string_view)`, both needing one conversion. Making it a template and excluding types convertible to `const charT*` means literals and `char*` match only the `const charT*` overload, while `std::string_view` and other types convertible to a view match the template.

### Append, assign, insert, replace

The core version of each of these groups takes `(const charT* s, size_type n)`, with the precondition that `[s, s+n)` is valid; versions with position arguments throw `out_of_range` when `pos > size()`, and `length_error` when the result would be too long.

- [[string.append#15]] The iterator version of `append` is equivalent to constructing a temporary string first and then appending, so `s.append(s.begin(), s.end())` is correct. ¶16 C++23 added `append_range`; ¶18 `push_back(c)` is equivalent to `append(1, c)`.
- When source and target are the same string, as in `s += s` or `s.append(s.data() + 1, 3)`, the result must still be correct. The specification only says a copy of the range is appended and gives no precondition that the source not overlap `*this`, so implementations must save the source contents before reallocating.
- [[string.assign#14]] `assign(n, c)` is defined as `clear(); resize(n, c);`.
- The iterator versions in [string.insert] require `p` to be a valid iterator on `*this` and return an iterator to the first inserted character, or `p` if `n == 0`.
- The iterator versions in [string.replace] require `[begin(), i1)` and `[i1, i2)` to be valid ranges.

### erase and pop_back [string.erase]

¶1–¶3 `erase(pos = 0, n = npos)` removes `[pos, pos + min(n, size() - pos))` and throws `out_of_range` if `pos > size()`. So `s.erase(3)` removes all characters from position 3 on, not the single character at position 3; for the latter, write `s.erase(s.begin() + 3)` (¶4–¶7). ¶12 `pop_back()` has the hardened precondition `!empty()`.

### copy and swap

[string.copy] `copy(s, n, pos)` is equivalent to `basic_string_view(*this).copy(s, n, pos)` and does not write a terminating null.

[string.swap] ¶1 The precondition of `swap` is that the allocator's `propagate_on_container_swap` is true or the two allocators are equal; otherwise it is {{ub}}. ¶3–¶4 It does not throw and has constant complexity.

## String operations [string.ops]

### c_str, data and conversion to a view [string.accessors]

¶1 `c_str()`, `data() const` and `data()` all return `to_address(begin())` in constant time. So `c_str() == data()` always holds; the only difference is that non-const `data()` (since C++17) returns a writable `charT*`.

¶3 `operator basic_string_view<charT, traits>() const noexcept` is equivalent to `basic_string_view(data(), size())`. This is the implicit conversion from `string` to `string_view`, where all the dangling problems in [[string.view]] start.

### Searching and comparison

All overloads in [string.find] reduce to the same-named functions of `basic_string_view`, with semantics described in [[string.view]]: they return `npos` when nothing is found and never throw `out_of_range`. ¶4 The `noexcept` of the template versions matches `is_nothrow_convertible_v<const T&, basic_string_view<charT, traits>>`.

All versions in [string.compare] are equivalent to the corresponding `compare` of `basic_string_view(*this)`; the versions with `pos1` and `n1` throw `out_of_range` when `pos1 > size()`.

[string.starts.with], [string.ends.with] (C++20, [[P0457R2]]) and [string.contains] (C++23, [[P1679R3]]) are all equivalent to the same-named members of `basic_string_view(data(), size())`, each with three overloads taking a view, a character and a `const charT*`:

```cpp run ok
#include <string>
#include <cassert>

int main() {
  std::string s = "hello";
  assert(s.starts_with("he") && s.starts_with('h') && !s.ends_with("lo!"));
  assert(s.contains("ell") && s.contains('o') && !s.contains("xyz"));
  assert(!std::string{}.starts_with('a'));   // an empty string returns false without violating front()'s precondition
}
```

### substr and subview [string.substr]

```cpp
constexpr basic_string substr(size_type pos = 0, size_type n = npos) const &;
constexpr basic_string substr(size_type pos = 0, size_type n = npos) &&;
constexpr basic_string_view<charT, traits> subview(size_type pos = 0, size_type n = npos) const;
```

C++23 split `substr` into `const &` and `&&` overloads ([[P2438R2]]). ¶2 Called on an rvalue, it is equivalent to `basic_string(std::move(*this), pos, n)` and can take over the source's buffer, so `make().substr(1)` may not allocate at all.

¶3 `subview` was added in a more recent working draft; it returns a view and copies no characters. Both throw `out_of_range` when `pos > size()`. In `auto t = s.subview(1);`, `t` is a `string_view`, which dangles once `s` is modified or destroyed; calling `subview` on an rvalue string gives a view that dangles immediately.

## constexpr and transient allocation

Since C++20 all members of `basic_string` are `constexpr` ([[P0980R1]]). But memory allocated during constant evaluation must be freed within the same evaluation (transient allocation, [[g:transient-allocation]], [[expr.const]]):

```cpp
constexpr std::size_t f() { std::string s = "a fairly long string that leaves SSO"; return s.size(); }
static_assert(f() == 36);                                           // OK: the allocation is freed inside f
constexpr std::string s1 = "short";                                 // accepted by libc++ in our tests: SSO, no allocation
constexpr std::string s2 = "a fairly long string that leaves SSO";  // error: not a constant expression
```

Whether `s1` compiles depends entirely on the implementation: in libc++ short strings do not allocate. With an implementation that has a different short-mode capacity, or with the string lengthened past 22 characters, the same code fails. Portable code should not depend on this; use `std::string_view` or character arrays for compile-time string constants.

## History

!!! history
    - C++11 tightened the invalidation rules and added concurrency requirements, effectively ruling out copy-on-write implementations.
    - Since C++17, non-const `data()` returns `charT*`; the members constructing from and assigning from `string_view` came with [[P0254R2]].
    - C++20: all members became `constexpr` ([[P0980R1]]); `reserve` no longer shrinks ([[P0966R1]]); `starts_with` and `ends_with` added ([[P0457R2]]).
    - C++23: `resize_and_overwrite` ([[P1072R10]]); construction from `nullptr` deleted ([[P2166R1]]); rvalue `substr` and substring construction from `basic_string&&` ([[P2438R2]]); `contains` ([[P1679R3]]).
    - C++26: the preconditions of element access became hardened preconditions ([[P3471R4]]).

## Questions

!!! question "Question 1"
    `const char* p = s.c_str(); s.push_back('x'); std::puts(p);`, given that `s.capacity() > s.size() + 1`. Is this code valid?

<details markdown="1">
<summary>Answer</summary>

The standard does not guarantee it. [string.require] ¶4.2 says that every non-const member except the nine exceptions may invalidate pointers; `push_back` is not among the exceptions, and the standard does not restrict invalidation to reallocation as it does for `vector`. `p` may be invalid, and using it is {{ub}}.

In practice, none of the three major implementations moves the buffer when capacity suffices. Even so, `push_back` changes the old null position to `'x'` and writes a new null after it, so what `puts(p)` prints includes that `x` as well.
</details>

!!! question "Question 2"
    Why is `std::string s = sv;` (with `sv` a `std::string_view`) ill-formed while `std::string s = "abc";` is valid?

<details markdown="1">
<summary>Answer</summary>

Copy-initialization considers only non-`explicit` constructors. The template constructing from a `string_view`-like object is `explicit` ([[string.cons#11]]), and `string_view` has no conversion function to `string`. `"abc"` uses `basic_string(const charT*, const Allocator& = Allocator())`, which is not `explicit`. The design intent is that conversions that allocate must be written explicitly ([[P0254R2]]).
</details>

!!! question "Question 3"
    After `a.swap(b)`, where do iterators that pointed to characters in `b` point? What about with `std::vector<char>`?

<details markdown="1">
<summary>Answer</summary>

For `vector`, [[container.reqmts#65]] guarantees that after the swap the iterators point to the same elements, now in the other container, because only the buffer pointers are exchanged and the elements do not move; ¶66.6 also guarantees that `swap` does not invalidate references, pointers or iterators.

For `string`, the footnote to [string.require] ¶4 names `swap()` as possibly invalidating them. The reason is SSO: the characters of two short strings live inside their respective objects, so swapping can only copy characters, and an old iterator still points into the buffer inside the original object, which now holds the other string's contents.
</details>
