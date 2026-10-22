---
title: String views
summary: "basic_string_view is a pointer plus a length that does not own its characters; this page covers how it is constructed, which operations have preconditions, why data() is not guaranteed to be null-terminated, and its most common mistake: dangling."
updated: 2026-10-19
---

!!! tldr
    - A `string_view` stores only a pointer and a length, owns no characters, and is cheap to copy; it is best used as a function parameter.
    - It does not extend the lifetime of anything. Construct a view from a temporary `std::string` and keep it, and the view dangles immediately.
    - `data()` is not guaranteed to be null-terminated; do not pass it to C functions that take only a `const char*`.
    - `sv[i]` requires `i < size()`, stricter than `std::string`'s `i <= size()`; since C++26 this is a hardened precondition.
    - Construction from a range is `explicit`, character arrays are still treated as C strings, and `nullptr` cannot be used to construct one.

## Why string_view [string.view.general]

```cpp run ok
#include <string>
#include <string_view>
#include <cstdio>

std::size_t count_a(std::string_view s) {      // one non-template parameter accepts all kinds of strings
  std::size_t n = 0;
  for (char c : s) n += (c == 'a');
  return n;
}

int main() {
  std::string str = "banana";
  char buf[] = "papaya";
  std::printf("%zu %zu %zu\n",
              count_a("alpaca"),               // literal: no temporary string constructed
              count_a(str),                    // string: via a conversion function, no characters copied
              count_a(buf));                   // character array: treated as a C string
}
```

With a parameter of type `const std::string&`, passing a literal first constructs a temporary `string`, which may allocate; with `const char*`, the length is lost. `std::string_view` accepts both kinds of argument without copying characters. The note in [string.view.general] ¶2 states this design goal: the library provides implicit conversions from `const charT*` and `basic_string` to `basic_string_view`, so that user code can accept just `basic_string_view<charT>` as a single non-templated parameter type.

¶1 An object of `basic_string_view` refers to a constant, contiguous sequence of char-like objects ([[g:char-like-type]]) with the first element at position 0.

!!! std
    The class template `basic_string_view` describes an object that can refer to a constant contiguous sequence of char-like objects with the first element of the sequence at position zero.

There are three points in this sentence. "Refer to" says the view does not own the characters; "constant" says the characters are read-only, so `iterator` and `const_iterator` are the same type; "contiguous" says `data()` yields a pointer to the first character. Compared with `std::span<const char>` ([[views.contiguous]]), `string_view` adds a traits parameter and a full set of search and comparison members.

`std::string_view` is an alias for `basic_string_view<char>`. There are also `u8string_view`, `u16string_view`, `u32string_view` and `wstring_view`.

## Just a pointer and a length inside [string.view.template.general]

The two exposition-only members at the end of the class definition give all of its state:

```cpp
const charT* data_;   // exposition only
size_type size_;      // exposition only
```

libc++ implements it exactly this way; `sizeof(std::string_view) == 16` in our tests.

¶1 `traits` must meet the character traits requirements ([[char.traits]]). ¶3 Unless otherwise specified, member functions have O(1) complexity.

¶2 When pointers, iterators and references into a view are invalidated is decided entirely by the referenced storage:

!!! std
    For a `basic_string_view` `str`, any operation that invalidates a pointer in the range `[str.data(), str.data() + str.size())` invalidates pointers, iterators, and references to elements of `str`.

`string_view` has no invalidation rules of its own. When the source `string` is destroyed or reallocates ([[basic.string]]), or the source buffer is freed, none of the view's elements may be accessed any more. Only the pointers, iterators and references to elements are invalidated; the view object itself is still a normal object: you can assign it a new value, and `size()` can still be read.

¶4 `basic_string_view` is a trivially copyable type ([[g:trivially-copyable-type]]). This guarantee was added in C++23 by [[P2251R1]]; implementations already behaved this way. Under the usual x86-64 and AArch64 calling conventions, passing a `string_view` by value uses two registers, one indirection fewer than `const std::string&`, so the idiom is to pass `string_view` by value.

## Construction [string.view.cons]

The constructors in the class definition:

```cpp
constexpr basic_string_view() noexcept;
constexpr basic_string_view(const basic_string_view&) noexcept = default;
constexpr basic_string_view(const charT* str);
basic_string_view(nullptr_t) = delete;
constexpr basic_string_view(const charT* str, size_type len);
template<class It, class End> constexpr basic_string_view(It begin, End end);
template<class R> constexpr explicit basic_string_view(R&& r);
```

### Default construction and pointer plus length

¶1 A default-constructed view has `size_ == 0` and `data_ == nullptr`. So `std::string_view{}.data()` is a null pointer, and `printf("%s", sv.data())` is {{ub}} here. `std::string{}.data()`, by contrast, always points to a null character.

¶5 The precondition of the `(str, len)` form is that `[str, str + len)` is a valid range. It does not require a null character at the end and does not care about null characters in the middle. When `len == 0`, `str` may be a null pointer.

### From const charT*

¶2–¶4 The precondition is that `str` points to a sequence terminated by `charT()`; the length is computed at construction with `traits::length(str)`, in time proportional to the length. So an embedded null character truncates the view: `std::string_view sv = "abc\0def";` has `size()` 3.

```cpp run ok
#include <string_view>
#include <array>
#include <cassert>

int main() {
  char buf[8] = "ab";
  std::array<char, 4> arr{'x', 'y', 'z', 'w'};
  assert(std::string_view{buf}.size() == 2);   // array decays to pointer: strlen semantics
  assert(std::string_view{arr}.size() == 4);   // range construction: the whole array
}
```

Character arrays also go through this constructor, not the range constructor below. That is deliberate: character arrays are almost always used as C strings, and counting the terminating null and the unused space into the view would surprise everyone.

### nullptr is deleted

Since C++23, `basic_string_view(nullptr_t)` is deleted ([[P2166R1]]). Before that, `std::string_view sv = nullptr;` compiled and then crashed in `traits::length(nullptr)`. Now it is rejected at compile time:

```cpp error
#include <string_view>
std::string_view sv = nullptr;   // error: call to deleted function
```

This only catches a literal `nullptr`. A `const char*` variable whose value is null still compiles and violates the precondition at run time.

### From an iterator pair {{c++20}}

¶7 The `(begin, end)` constructor added in C++20 ([[P1391R4]]) has four constraints: `It` satisfies `contiguous_iterator`; `End` satisfies `sized_sentinel_for<It>`; the value type of `It` is `charT`; `End` is not convertible to `size_type`.

The last constraint keeps it from competing with `(const charT*, size_type)` in overload resolution: the `5` in `string_view(p, 5)` must not be taken as a sentinel. ¶9 The result is `data_ = to_address(begin)` and `size_ = end - begin`.

### From a range: explicit {{c++23}}

¶12 The range constructor added in C++23 ([[P1989R2]]) was made `explicit` before C++23 was finalized ([[P2499R0]]). Its constraints, where `d` is an lvalue of type `remove_cvref_t<R>`:

| Constraint | Purpose |
|---|---|
| ¶12.1 `remove_cvref_t<R>` is not `basic_string_view` | does not compete with the copy constructor |
| ¶12.2 `R` models `contiguous_range` and `sized_range` | `data()` and `size()` are available |
| ¶12.3 `range_value_t<R>` is `charT` | no element type conversion |
| ¶12.4 `R` is not convertible to `const charT*` | character arrays are still treated as C strings |
| ¶12.5 `d.operator ::std::basic_string_view<charT, traits>()` is not a valid expression | types with their own conversion function (such as `std::string`) use it |

¶12.5 makes the conversion from `std::string` to `string_view` always go through `string`'s implicit conversion function, not this constructor. When the traits differ, for example converting `basic_string<char, ci_traits>` to `std::string_view`, the conversion function's target type does not match, ¶12.5 no longer excludes it, and this constructor can be used for an explicit conversion.

The reason for `explicit` is that a contiguous range of characters is not necessarily a string. A `std::vector<char>` might be a null-terminated buffer or binary data; a `std::array<char, 16>` might use only its first few bytes. If implicit conversion were allowed, `f(std::string_view)` would silently accept these objects and count the terminating null into the length:

<div class="compare" markdown="1">

```cpp error
#include <string_view>
#include <vector>
void f(std::string_view);
void g(std::vector<char>& v) {
  f(v);   // error: the constructor is explicit
}
```

```cpp run ok
#include <string_view>
#include <vector>
#include <cassert>
int main() {
  std::vector<char> v{'a', 'b', '\0'};
  std::string_view s{v};   // direct-initialization
  assert(s.size() == 3);   // includes the trailing '\0'
}
```

</div>

The constraints do not require `R` to be a borrowed range, so a temporary `vector` can also be used to construct a view, which then dangles immediately:

```cpp
#include <string_view>
#include <vector>
std::string_view x{std::vector<char>{'a', 'b'}};
// x dangles: the temporary vector is destroyed at the end of the full-expression; accessing x's elements afterwards is UB
```

### Deduction guides [string.view.deduct]

¶1 `basic_string_view(It, End)` deduces `basic_string_view<iter_value_t<It>>`. ¶2 `basic_string_view(R&&)` deduces `basic_string_view<range_value_t<R>>`, requiring only that `R` be a `contiguous_range`.

## Dangling

Almost every `string_view` problem comes down to one point: it does not extend the lifetime of anything. Lifetime extension when a reference binds to a temporary ([[class.temporary]]) applies only to references. `string_view` is a class type; constructing it from a temporary `string` merely calls `string`'s conversion function, and the temporary is destroyed at the end of the full-expression as usual.

```cpp
std::string make();
void f(std::string_view);

f(make());                                   // OK: the temporary lives until after f returns
std::string_view a = make();                 // dangles
std::string_view b = std::string("x") + "y"; // dangles
std::string_view c = "abc"s;                 // dangles: ""s produces a temporary string
std::string_view d = "abc";                  // OK: the literal has static storage duration

std::string_view g() {
  std::string s = "local";
  return s;                                  // dangles: returns a view of a local string
}
```

Clang 23 warns about `a`, `b` and `c` with `-Wdangling-gsl` and about `g` with `-Wreturn-stack-address`, both on by default. Clang has a built-in list of standard library types and knows that `std::string_view` is a pointer-like type and `std::string` an owner type. Put one function in between, and the compiler can no longer see it:

```cpp run ub
#include <string>
#include <string_view>
#include <iostream>

std::string_view trim(std::string_view s) {          // returns a subview of the argument
  while (!s.empty() && s.front() == ' ') s.remove_prefix(1);
  return s;
}
std::string read_line() { return "   a line long enough to avoid SSO, really"; }

int main() {
  std::cout << trim(read_line()) << '\n';            // OK: the temporary lives until the end of the full-expression
  std::string_view v = trim(read_line());            // dangles, no warning
  std::cout << v << '\n';                            // UB: ASan reports heap-use-after-free
}
```

Clang's extension attribute `[[clang::lifetimebound]]` can tell the compiler about this relationship. Declare the parameter as `std::string_view s [[clang::lifetimebound]]`, and the line with `v` also triggers `-Wdangling-gsl`.

!!! pitfall "Short strings make dangling look harmless"
    If `read_line()` returns a short string (at most 22 `char`s in libc++), the characters are stored inside the `string` object (the small string optimization, see [[basic.string]]). The temporary is on the stack, that memory is often left untouched after destruction, and AddressSanitizer may not catch it. Passing tests do not show there is no dangling.

When a `string_view` can be kept safely:

- As a parameter it is always safe; the argument lives until the call ends.
- As a return value it is safe only when returning part of an argument (the caller is responsible for the argument's lifetime) or static storage (literals, static objects).
- As a member or in a container, the referenced object must outlive the view. This is the most common source of dangling.
- Watch `auto`: `auto x = s.subview(1);` deduces `string_view`, while `auto x = s.substr(1);` deduces `string`, with entirely different lifetimes.

## Element access [string.view.access]

| Member | Precondition | On violation |
|---|---|---|
| `operator[](pos)` | hardened: `pos < size()` (¶1) | contract violation in a hardened implementation, otherwise {{ub}} |
| `at(pos)` | none | throws `out_of_range` if `pos >= size()` (¶5) |
| `front()`, `back()` | hardened: `!empty()` (¶6, ¶9) | same as `operator[]` |

The note in ¶1 points out that this precondition is stronger than that of `basic_string::operator[]`. `string` guarantees that `data()[size()]` is a null character ([[basic.string]]), so `s[s.size()]` is allowed; a view may have no character after it, so `sv[sv.size()]` is not.

C++26 marks these as hardened preconditions ([[P3471R4]], see [[structure.specifications]]): in a hardened implementation, violating them is always checked and handled as a contract violation. libc++ selects the hardening mode with the macro `_LIBCPP_HARDENING_MODE`, off by default in our tests. Accessing `sv[3]` with `sv == "abc"` reads the literal's terminating null, 0, in the default mode and ends normally; compiled in fast mode, the program traps at the out-of-bounds access with exit code 133 (SIGTRAP).

### data() is not guaranteed to be null-terminated

```cpp run ok
#include <string_view>
#include <cstdio>
#include <cstdlib>

int main() {
  std::string_view whole = "1234567";
  std::string_view part = whole.substr(0, 3);    // "123"
  std::printf("%d\n", std::atoi(part.data()));   // prints 1234567, not 123
  std::printf("%.*s\n", static_cast<int>(part.size()), part.data());  // right: give the length explicitly
}
```

This code has no UB, because `whole` comes from a literal that really does have a null after it, but the result is wrong. If the buffer `part` refers to had no null after it, `atoi` would read out of bounds, which is {{ub}}. The note in ¶13 sums this up:

!!! std
    Unlike `basic_string::data()` and *string-literal*s, `data()` can return a pointer to a buffer that is not null-terminated. Therefore it is typically a mistake to pass `data()` to a function that takes just a `const charT*` and expects a null-terminated string.

When you need a null-terminated string, either use an interface that takes a length (`printf("%.*s")`, `fwrite`, `std::from_chars`) or construct a `std::string` first.

### Iterators and capacity

[string.view.iterators] ¶1 `const_iterator` is an implementation-defined type that meets the constant random access iterator requirements and models `contiguous_iterator`. In libc++ it is just `const char*`. ¶3 When the view is non-empty, `begin()` points to `data_`; for an empty view `begin()` is an unspecified value, only guaranteed to make `[begin(), end())` a valid range.

In [string.view.capacity], `size()` and `length()` return `size_`, and `empty()` returns `size_ == 0`.

## Modifying the view [string.view.modifiers]

These members change the view itself, not the characters:

- ¶1–¶2 `remove_prefix(n)`: hardened precondition `n <= size()`; effect `data_ += n; size_ -= n;`;
- ¶3–¶4 `remove_suffix(n)`: hardened precondition `n <= size()`; effect `size_ -= n;`;
- ¶5 `swap(s)`: exchanges the two views.

## Substrings, comparison and prefixes [string.view.ops]

¶1–¶6 `copy(s, n, pos)` copies `min(n, size() - pos)` characters to `s` and returns the number copied. It does not write a terminating null. It throws `out_of_range` if `pos > size()`.

¶7–¶10 `substr(pos, n)` and `subview(pos, n)` return `basic_string_view(data() + pos, rlen)`, where `rlen = min(n, size() - pos)`:

- `pos == size()` is valid and gives an empty view; `pos > size()` throws `out_of_range`;
- `n` larger than the remaining length is truncated automatically;
- the result refers to the same storage as the original view; no characters are copied.

`subview` was added in a more recent working draft and, for views, is identical to `substr`. It exists for `basic_string`: `string::substr` returns a copied `string`, while `string::subview` returns a non-copying view. With a member of the same name on the view, generic code can use one name for both.

¶11–¶14 `compare(str)` first compares the first `rlen = min(size(), str.size())` characters with `traits::compare(data(), str.data(), rlen)` and returns that if nonzero; if zero, the lengths decide, and the shorter is smaller (Table 88). ¶15–¶19 The other `compare` overloads are all equivalent to calling `substr` first, so the versions with position arguments can throw `out_of_range`.

¶20–¶28 `starts_with`, `ends_with` (C++20, [[P0457R2]]) and `contains` (C++23, [[P1679R3]]):

- `starts_with(x)` is equivalent to `basic_string_view(data(), min(size(), x.size())) == x`;
- `starts_with(charT c)` is equivalent to `!empty() && traits::eq(front(), c)`; an empty view returns `false` without violating `front()`'s precondition;
- `contains(x)` is equivalent to `find(x) != npos`.

The versions taking `basic_string_view` and `charT` are `noexcept`; the versions taking `const charT*` are not, because they first construct a view from the pointer, which has a precondition.

## Searching [string.view.find]

¶1 The worst-case complexity of the search functions is O(`size() * str.size()`); the standard recommends that implementations do better. ¶2 All the `const charT*`, `(const charT*, n)` and `charT` overloads reduce to the `basic_string_view` version. The six functions are defined in the same form: find the lowest or highest position `xpos` meeting a condition, or return `npos` if there is none.

| Function | Direction | Condition on `xpos` |
|---|---|---|
| `find` (¶3–¶5) | lowest, `xpos >= pos` | `str` matches starting at `xpos` |
| `rfind` (¶6–¶8) | highest, `xpos <= pos` | same |
| `find_first_of` (¶9–¶11) | lowest | `data_[xpos]` equals some character of `str` |
| `find_last_of` (¶12–¶14) | highest | same |
| `find_first_not_of` (¶15–¶17) | lowest | `data_[xpos]` equals no character of `str` |
| `find_last_not_of` (¶18–¶20) | highest | same |

Some edge cases:

- The search functions never throw. An out-of-range `pos` just means nothing is found.
- `find("", pos)` returns `pos` when `pos <= size()`, because the empty string matches at every position.
- In `rfind(x, pos)`, `pos` is an upper bound on the start of the match, so a match extending past `pos` can be found.

## Comparison operators [string.view.comparison]

```cpp run ok
#include <string>
#include <string_view>
#include <cassert>
using namespace std::literals;

int main() {
  std::string s = "abc";
  assert("abc"sv == "abc");     // const char* implicitly converts to string_view
  assert("abc" == "abc"sv);     // rewritten candidate: operands swapped
  assert("abc"sv == s);         // string's conversion function
  assert(("abc"sv <=> "abd"sv) < 0);
}
```

The standard declares only two operator templates:

```cpp
template<class charT, class traits>
  constexpr bool operator==(basic_string_view<charT, traits> lhs,
                            type_identity_t<basic_string_view<charT, traits>> rhs) noexcept;
template<class charT, class traits>
  constexpr /* see below */ operator<=>(basic_string_view<charT, traits> lhs,
                                        type_identity_t<basic_string_view<charT, traits>> rhs) noexcept;
```

¶1 `==` returns `lhs.compare(rhs) == 0`. ¶2–¶4 The result type `R` of `<=>` is `traits::comparison_category`, or `weak_ordering` if there is no such member; `R` must be a comparison category type; the result is `static_cast<R>(lhs.compare(rhs) <=> 0)`.

The second parameter is wrapped in `type_identity_t`, and the note in ¶5 explains why. Template argument deduction does not consider implicit conversions ([[temp.deduct.call]]); if both parameters were `basic_string_view<charT, traits>`, `sv == "abc"` would fail deduction, since `basic_string_view<charT, traits>` cannot be deduced from `const char*`. `type_identity_t<...>` makes the second parameter a non-deduced context ([[g:non-deduced-context]]), so `charT` and `traits` are deduced from `lhs` only, and `rhs` can match through implicit conversion.

`"abc" == sv` is handled by C++20 rewritten candidates: the compiler tries it again as `sv == "abc"` ([[over.match.oper]]). So one template covers both directions, and `!=`, `<` and the rest are all obtained by rewriting.

## Output, hashing and the sv literal

[string.view.io] ¶1 `operator<<` is a formatted output function ([[ostream.formatted.reqmts]]): it pads according to `os.width()` and then calls `os.width(0)`. It outputs by length, so embedded null characters are written too.

[string.view.hash] ¶1 All five standard aliases have enabled `hash` specializations ([[unord.hash]]). Note 1 says that a view's hash value equals the hash value of the corresponding string, which [[basic.string.hash]] guarantees. So an `unordered_map<std::string, V>` can be looked up with a `string_view` without constructing a temporary `string` (C++20 heterogeneous lookup, [[P0919R3]], [[P1690R1]]), and a transparent hasher can simply use `hash<string_view>`:

```cpp run ok
#include <string>
#include <string_view>
#include <unordered_map>
#include <functional>
#include <cassert>
using namespace std::literals;

struct string_hash {
  using is_transparent = void;
  std::size_t operator()(std::string_view s) const noexcept {
    return std::hash<std::string_view>{}(s);
  }
};

int main() {
  std::unordered_map<std::string, int, string_hash, std::equal_to<>> m{{"key", 1}};
  assert(m.find("key"sv)->second == 1);   // no temporary std::string constructed
}
```

Only views with the default traits have `hash` specializations; `basic_string_view<char, ci_traits>` does not.

[string.view.literals] ¶1–¶5 `operator""sv(str, len)` returns `basic_string_view{str, len}` and lives in `std::literals::string_view_literals` ([[P0403R1]]). `len` comes from the literal itself, so embedded nulls are kept: `"abc\0def"sv` has `size()` 7. String literals have static storage duration ([[lex.string]]), so `"..."sv` never dangles and is the safest way to return a `string_view`.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

The header comment of [string.view.synop] says mostly freestanding: freestanding implementations also provide `string_view`, but the throwing `at`, `copy`, `substr`, `subview` and the `compare` overloads with position arguments are deleted in freestanding implementations, and `operator<<` is provided only in hosted implementations.

The synopsis also specializes both `ranges::enable_view` and `ranges::enable_borrowed_range` as `true`. The latter means that calling a ranges algorithm on an rvalue `string_view` yields a real iterator, not `ranges::dangling` ([[g:borrowed-range]], [[range.range]]): the view is gone, but the characters remain.

[string.view.synop] ¶1 Once `<string_view>` is included, `swap` from [utility.swap] and the function templates `begin`, `size`, `data` and others from [iterator.range] are available.

[string.view.cons] ¶8 requires the concepts of the iterator-pair constructor to be not just syntactically satisfied but modeled; ¶10 it throws whatever `end - begin` throws. ¶13–¶14 The range constructor initializes with `ranges::data(r)` and `ranges::size(r)` and propagates their exceptions.

[string.view.capacity] ¶2 `max_size()` returns the largest number of characters a view can refer to.

</details>

## History

!!! history
    - C++17 introduced `string_view` ([[P0254R2]] also gave `std::string` an implicit conversion to `string_view`) and the `sv` literal ([[P0403R1]]).
    - C++20 added the iterator-pair constructor ([[P1391R4]]) and `starts_with`/`ends_with` ([[P0457R2]]), and the comparison operators became `==` and `<=>`. In C++17 the standard merely required implementations to provide enough additional overloads to support comparison with convertible types.
    - C++23 added `contains` ([[P1679R3]]), deleted construction from `nullptr` ([[P2166R1]]), added the `explicit` range constructor ([[P1989R2]], [[P2499R0]]), and guaranteed trivial copyability ([[P2251R1]]).
    - C++26 made the preconditions of element access and `remove_prefix`/`remove_suffix` hardened preconditions ([[P3471R4]]).

## Questions

!!! question "Question 1"
    Does `std::string_view sv = std::string("hi"); std::cout << sv.size();` have undefined behavior?

<details markdown="1">
<summary>Answer</summary>

No. `size_` is an integer copied from the temporary `string` at construction; reading it does not access the destroyed storage. [string.view.template.general] ¶2 invalidates only pointers, iterators and references to elements.

But at this point `sv.data()` is an invalid pointer value ([[g:invalid-pointer-value]]), and `sv[0]`, `sv.front()` and outputting `sv` all access elements and are all {{ub}}. That it compiles and `size()` works fine is exactly why dangling is hard to spot.
</details>

!!! question "Question 2"
    Given `void f(std::string_view); std::vector<char> v;`, does `f(v)` compile? What about `f(std::string_view(v))`?

<details markdown="1">
<summary>Answer</summary>

`f(v)` is ill-formed. The parameter is copy-initialized, which needs an implicit conversion; the range constructor is `explicit`, and `vector` has no conversion function to `string_view`.

`f(std::string_view(v))` is valid. A functional cast is direct-initialization and can call an `explicit` constructor; `vector<char>` meets all the constraints in ¶12: contiguous, sized, value type `char`, not convertible to `const char*`, no `operator string_view`.
</details>

!!! question "Question 3"
    Why does `string_view::operator[]` require `pos < size()`, while `string::operator[]` requires only `pos <= size()`?

<details markdown="1">
<summary>Answer</summary>

`basic_string` guarantees that `data() + size()` points to an object with value `charT()` ([[basic.string]]), so `s[s.size()]` has something to read. A view has no such guarantee. It might refer to the first three characters of `"hello"`, in which case `sv[3]` is `'l'`, not a null character; or it might refer to the last few characters of a buffer, in which case `sv[sv.size()]` is out of bounds. The note in [string.view.access] ¶1 points out exactly this difference.
</details>
