---
title: Character arrays
summary: "Initializing character arrays from string literals: which arrays go with which literals, the terminating null character must fit (unlike in C), and extra elements are zeroed."
updated: 2026-10-19
---

!!! tldr
    - An array generally can't be initialized from another array; a string literal initializing a character array is the only exception.
    - The element type must match the literal's encoding prefix: `char` with `"…"`, `char8_t` with `u8"…"`, `wchar_t` with `L"…"`, and so on; `char` and `unsigned char` arrays can also use `u8"…"`.
    - The implicit `'\0'` at the end of the literal counts as an initializer too, and if it doesn't fit, the declaration is ill-formed. C allows dropping it; C++ doesn't.
    - If the array is longer than the literal, the extra elements are zeroed; an array of unknown bound takes its length from the literal, counting the `'\0'`.

## Which arrays go with which literals (¶1)

```cpp run ok
char msg[] = "Syntax error on line %s\n";
static_assert(sizeof msg == 25);   // '\n' is 1 character, plus the terminating '\0'

unsigned char bytes[] = "\xff\x01"; // '\xff' becomes 255 by integral conversion
char a[] = "a\0b";                  // an embedded \0 is copied as usual
static_assert(sizeof a == 4);
char32_t cat[] = U"ab" U"cd";       // concatenation happens in translation phases; there is only one literal here
static_assert(sizeof cat / sizeof cat[0] == 5);
char s[] = {"abc"};                 // an extra pair of braces is fine too
int main() { return bytes[0] == 255 ? 0 : 1; }
```

A string literal has an array type such as `const char[N]` ([[lex.string]]), and initializing an array from an array, as in `int a[3] = b;`, is ill-formed. Character arrays are the only exception, and this subclause specifies it.

¶1 The following pairings are allowed, optionally with the literal enclosed in braces:

| Array element type | Usable literals |
|---|---|
| Ordinary character types `char`, `signed char`, `unsigned char` | Ordinary string literals `"…"` |
| `char8_t` | UTF-8 literals `u8"…"` |
| `char16_t` | UTF-16 literals `u"…"` |
| `char32_t` | UTF-32 literals `U"…"` |
| `wchar_t` | Wide literals `L"…"` |
| Additionally: `char`, `unsigned char` | UTF-8 literals `u8"…"` |

The characters of the literal, including the implicit `'\0'` at the end, initialize the array elements in order; if the types differ, an integral conversion ([[conv.integral]]) is applied, e.g. a `char` value from an ordinary literal converted to `unsigned char`.

Any other pairing is ill-formed. Nothing other than a literal, including a pointer to a literal, can initialize an array:

```cpp error
char8_t     e1[] = "abc";   // error: a char8_t array needs a u8 literal
wchar_t     e2[] = "abc";   // error
char16_t    e3[] = U"abc";  // error: a UTF-32 literal doesn't go with char16_t
signed char e4[] = u8"abc"; // error: the extra allowance for u8 doesn't cover signed char
const char* p = "x";
char        e5[] = p;       // error: not a string literal
```

### `u8` literals and `char` arrays

When C++20 introduced `char8_t`, the type of `u8"…"` changed from `const char[N]` to `const char8_t[N]`, and lots of old code of the form `char s[] = u8"…";` stopped compiling. [[P2513R4]], as a defect fix against C++20, restored initializing `char` and `unsigned char` arrays from `u8` literals, i.e. the last row of the table.

This allowance only covers array initialization. `const char* p = u8"abc";` is still ill-formed, because it would need a conversion from `const char8_t*` to `const char*`, which doesn't exist.

`signed char` is not included. UTF-8 code units take values 0–255, which `unsigned char` represents exactly, and `char` is the type traditionally used to hold UTF-8; `signed char` is neither.

## The terminating null character must fit (¶2)

<div class="compare" markdown="1">

```cpp error
char cv[4] = "asdf";
// error: 5 initializers,
// only 4 elements
```

```cpp ok
char cv[4] = {'a', 's', 'd', 'f'};
// OK: a list of characters,
// no '\0' appended
```

</div>

¶2 There can't be more initializers than array elements. The initializers include the implicit `'\0'` at the end, so `"asdf"` needs 5 elements. Clang 23's diagnostic spells it out: array size is 4 but initializer has size 5 (including the null terminating character).

This is a deliberate incompatibility between C++ and C. C allows `char cv[4] = "asdf";`, giving an array not terminated by `'\0'` (C11 6.7.9/14: the terminator is written only if there is room or the array size is unknown). C uses this for fixed-length unterminated fields, but more often it's a bug: reading the array later with `strlen` or `printf("%s")` runs off the end. C++ makes it a compile error.

When you really need a fixed-length character array without a terminator, write a braced list of characters as on the right, or use `std::array<char, 4>`; the intent is clearer.

## Extra elements are zeroed (¶3)

```cpp run ok
#include <cassert>
int main() {
  char buf[8] = "ab";    // 'a', 'b', '\0', then 5 more '\0'
  for (int i = 2; i < 8; ++i) assert(buf[i] == 0);
}
```

¶3 If there are fewer initializers than array elements, the elements not explicitly initialized are zero-initialized ([[dcl.init#5]]). This has the same effect as initializing the remaining elements from `{}` in aggregate initialization ([[dcl.init.aggr#6]]).

This holds for arrays with automatic storage duration too, so `char buf[4096] = "";` zeroes the whole buffer, and compilers usually generate a `memset` for it. When you only want an empty string and don't care about the other bytes, that's an unnecessary cost.

## Unknown bound and multidimensional arrays

A character array of unknown bound takes its length from the literal, counting the `'\0'`: `char s[] = "hi";` has type `char[3]`. The basis is [[dcl.init.aggr#11]]: the array's length equals the number of explicitly initialized elements, and a string literal provides one more initializer than its number of characters.

A multidimensional character array can be initialized with a list of literals, one per row:

```cpp run ok
char grid[][4] = { "abc", "def", "ghi" };   // char[3][4]
static_assert(sizeof grid == 12);
char names[2][4] = { "abc", "de" };         // names[1] is 'd','e','\0','\0'
int main() {}
```

Each `"abc"` is a clause of the outer aggregate initialization. It doesn't start with `{`, but it can initialize a whole `char[4]` row directly, so it appertains to that row ([[dcl.init.aggr#15]]), and the row is then initialized from the literal by the rules of this subclause.

## Edge cases

!!! lawyer "String literals in parentheses"
    The condition in item 3 of [[dcl.init#15]] is that the initializer is a *string-literal*. Whether `char a[]("abc");`, whose initializer is a parenthesized expression list, or `char a[] = ("abc");`, a parenthesized literal, satisfies this condition is not clear from the wording. If not, the former would fall to item 5 (parenthesized initialization of arrays), initializing the first `char` element with `"abc"`, and be ill-formed. Clang 23 accepts both and treats them as string initialization, with `sizeof a == 4`. The portable form is `char a[] = "abc";`.

!!! lawyer "std::array and string literals"
    Mainstream implementations all accept `std::array<char, 4> s = {"abc"};`: the clause `"abc"` appertains to the `char[4]` member inside `std::array`, which is then initialized from the literal by this subclause. By the literal wording of item 3 of [[dcl.init.aggr#15]], a clause appertains directly to an element only if it can be implicitly converted to the element type, and an array type has no implicit conversion sequence to speak of, so this result isn't obvious from the wording; but it is the consensus in practice.

!!! impl
    A local `char s[] = "hello";` is an array on the stack, not a pointer to read-only data. The compiler generates code that copies from `.rodata` or writes immediates, so `s[0] = 'H';` is valid. By contrast, `const char* p = "hello";` points to read-only storage, and writing through it after a `const_cast` is UB ([[lex.string]]).

## History

!!! history
    - Since C++98, failing to fit the terminating null character has been ill-formed, unlike in C.
    - C++11 added `char16_t`, `char32_t` and the literals `u""`, `U""` and `u8""`; at the time, `u8""` had type `const char[N]`.
    - C++20 added `char8_t`, and `u8""` became `const char8_t[N]`; [[P2513R4]], as a defect fix, restored initializing `char` and `unsigned char` arrays from `u8` literals.

## Questions

!!! question "Question"
    Which is valid: `char s[3] = {'a', 'b', 'c'};` or `char s[3] = "abc";`? How large is `char t[] = {'a', 'b', 'c'};`?

<details markdown="1">
<summary>Answer</summary>

The former is valid: the braced list has exactly 3 clauses and goes through ordinary aggregate initialization, with no `'\0'` appended. The latter is ill-formed: the literal carries an implicit `'\0'`, making 4 initializers (¶2).

`t` has size 3, likewise with no null character, and calling `strlen` on it is UB.
</details>
