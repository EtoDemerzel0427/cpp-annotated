---
title: Resource inclusion
summary: "C++26's #embed directive expands the bytes of an arbitrary binary file into a comma-separated list of integers; this page covers what it expands to, how resources are found, and the five parameters limit, offset, prefix, suffix and if_empty."
updated: 2026-10-19
---

!!! tldr
    - `#embed "file"` expands the file's contents at preprocessing time into comma-separated integer literals of type `int`, each value as if one byte read with `fgetc`, ranging from 0 to `UCHAR_MAX`.
    - The expansion has no braces and is interpreted by the grammar wherever it appears: array initialization, function arguments, a `std::vector` initializer list all work.
    - Receive the data in `unsigned char`; with `char`, a signed `char` meeting a byte above 127 is a narrowing conversion and ill-formed.
    - `limit` and `offset` select a range of bytes; `prefix` and `suffix` insert tokens only when the resource is nonempty; `if_empty` replaces the whole directive only when the resource is empty.
    - Resource lookup parallels `#include` but is independent of it; `__has_embed` can probe resources and parameters in `#if`.

{{c++26}} Before `#embed`, there were two main ways to put a binary file into a program. One was to convert the file with a tool such as `xxd -i` into a source file of the form `{0x12, 0x34, ...}`, which needs an extra build step and makes the compiler parse millions of integer literals. The other was the assembler's `.incbin` or linker options, which aren't portable, and the data isn't visible at compile time, so it can't be used in `constexpr` computations.

`#embed` hands the job to the preprocessor. Semantically it expands to a sequence of integer literals, so it can be used anywhere a list of integers is needed, including constant evaluation; in implementation terms, the compiler can skip generating text and parsing it again and use the file's bytes directly. It shares its origin with C23's `#embed` and was brought into C++26 by [[P1967R14]].

## What it expands to (¶11–¶13)

```cpp run title="embed-self.cpp" ok flags="-std=c++2c -Wno-c23-extensions"
// this file begins with "// "; below it embeds itself
constexpr unsigned char head[] = {
#embed __FILE__ limit(3)
};
static_assert(sizeof head == 3);
static_assert(head[0] == '/' && head[1] == '/' && head[2] == ' ');
int main() {}
```

`__FILE__` expands to a string literal of the current source file's name, so this example compiles anywhere. `limit(3)` takes only the first three bytes. The other runnable examples on this page use the same trick. Clang 23 treats `#embed` as an extension in C++ mode and gives a `-Wc23-extensions` warning for each use, so the examples turn that warning off.

¶11 Unless changed by a parameter, the `#embed` directive is replaced by a comma-separated list of integer literals of type `int`.

¶12 The value of each element is defined in terms of `fgetc`: first read from the resource in binary mode *resource-offset* times and discard the results (the offset is given by the `offset` parameter, see below), then read *resource-count* times, giving the elements of the list in order. If any of these reads returns `EOF`, the program is ill-formed. `fgetc` returns an `int` converted from `unsigned char`, so every element's value is between 0 and `UCHAR_MAX`; there are no negative values.

¶13 Recommended practice: the value of each integer literal should faithfully reflect the bit stream of the resource, with the implementation accounting for differences between the translation and execution environments if necessary. The standard's Example 2 expresses this expectation: data embedded at compile time and data read from the same file at run time in binary mode with `std::ifstream` should compare equal with `memcmp`.

### Just a comma-separated list of values

Syntactically the expansion is just `v1, v2, ..., vn`, with no braces. The standard's Example 3 shows this:

```cpp
int i = {
#embed "i.dat"
};            // well-formed if i.dat produces just one value
int i2 =
#embed "i.dat"
;             // likewise
struct s { double a, b, c; struct { double e, f, g; } x; double h, i, j; };
s x = {
#embed "s.dat"  // well-formed if it produces no more than 9 values: distributed to members by the brace elision rules
};
```

So it can also appear in a function call's argument list or a `std::vector` initializer list:

```cpp run title="embed-anywhere.cpp" ok flags="-std=c++2c -Wno-c23-extensions"
#include <vector>
int sum3(int a, int b, int c) { return a + b + c; }
int main() {
  std::vector<int> v = {
#embed __FILE__ limit(8)
  };
  int s = sum3(
#embed __FILE__ limit(3)
  );
  return (v.size() == 8 && s == '#' + 'i' + 'n') ? 0 : 1;   // the file begins with "#in"
}
```

!!! pitfall "Receive in unsigned char"
    The elements are integer literals of type `int`, with values 0 to 255 for 8-bit bytes. When they initialize a `char` array, if `char` is signed and some byte is 128 or more, that's a narrowing conversion in list-initialization ([[dcl.init.list]]), and the program is ill-formed. So receive them in `unsigned char`. `std::byte` can't be implicitly converted from `int` and can't receive them directly either.

    Clang 23 disagrees with the standard here: when `#embed` directly initializes a `char` array, it doesn't report narrowing even with a `0xFF` byte, and the value becomes `-1`; but compiling the `-E` output `{255, 1}` does report a narrowing error. The reason is that Clang takes a fast path for `#embed` that doesn't generate integer literals.

## How resources are found (¶1–¶7)

The lookup rules of `#embed` copy those of `#include` ([[cpp.include]]) almost word for word, replacing headers with resources: arbitrary sources of data accessible in the translation environment.

- ¶1 **[[g:bracket-resource-search|Bracket resource search]]**: search a sequence of places for a resource uniquely identified by a sequence of characters; places and identification are implementation-defined.
- ¶2 **[[g:quote-resource-search|Quote resource search]]**: search for a resource named by the sequence of characters in an implementation-defined manner; if unsupported or not found, fall back to a bracket resource search.

¶3–¶5 `# embed header-name parameters...` replaces the directive with preprocessing tokens derived from the resource's data. The `<...>` form does a bracket resource search and the `"..."` form a quote resource search.

¶6 If the bracket resource search fails, or the resource found can't be processed by the implementation, the program is ill-formed. Note 1 adds that a resource found but unprocessable makes the program ill-formed even with `limit(0)`, or when only probed in `__has_embed`.

¶7 Recommended practice: the search paths for resources should be similar to but independent of those for `#include`. GCC and Clang provide the `--embed-dir=<dir>` option for this. Tested with Clang 23, `#embed <x.bin>` looks only in directories given by `--embed-dir`, and `-I` directories have no effect on it; `#embed "x.bin"` looks in the includer's directory first. The benefit of keeping them separate is that `#embed <logo.png>` doesn't go looking in system header directories, and `#include` doesn't find files in resource directories.

## How big a resource is (¶9–¶10)

¶9 The size of a resource is described by several quantities:

| Quantity | Meaning |
|---|---|
| *implementation-resource-width* | the size of the resource in bits, implementation-defined |
| *implementation-resource-count* | the previous divided by `CHAR_BIT`, i.e. the number of bytes |
| *resource-offset* | the value of the `offset` parameter if present, otherwise 0 |
| *resource-count* ([[g:resource-count]]) | with `limit`, max(min(limit, bytes − offset), 0); otherwise max(bytes − offset, 0) |

A resource whose *resource-count* is 0 is an **empty resource**.

If the number of bits in the resource isn't a multiple of `CHAR_BIT`, the program is ill-formed; Example 1 in ¶10 is a 6-bit resource. Size is measured in bits to accommodate platforms whose bytes aren't 8 bits, and resources that don't come from ordinary files.

The `max(..., 0)` in the formulas means an `offset` beyond the size of the resource isn't an error; the resource just becomes empty. The `if_empty` parameter exists for exactly this situation.

## Parameters (¶8, [[cpp.embed.param]])

¶8 In either form, the parameters after `#embed` are first macro-expanded like ordinary text, and after expansion must have the form of a parameter sequence. So macros can be used in parameters:

```cpp
#define MAX_HEADER 64
#embed "file.bin" limit(MAX_HEADER)
```

And for that very reason, [[cpp.pre#4]] forbids defining `limit`, `prefix`, `suffix` or `if_empty` as macros, since otherwise the parameter names themselves would be expanded away.

There are five standard parameters, each appearing at most once in a directive. Prefixed parameters of the form `vendor::name` are conditionally-supported with implementation-defined semantics ([[cpp.pre#4]]).

| Parameter | Effect | When the resource is empty |
|---|---|---|
| `limit(n)` | take at most n elements | |
| `offset(n)` | skip n elements first | |
| `prefix(...)` | insert these tokens before the list | ignored |
| `suffix(...)` | insert these tokens after the list | ignored |
| `if_empty(...)` | | the whole directive is replaced by these tokens |

### limit and offset

`limit(...)` specifies the maximum number of elements in the list ([[cpp.embed.param.limit]]). The contents of the parentheses are evaluated as a constant expression by the rules of `#if` ([[cpp.cond]]), but without another round of macro expansion, since ¶8 already expanded them. The result must be an integral constant expression not less than 0, and `defined` can't appear in the parentheses.

Evaluating by the rules of `#if` means undefined identifiers become 0. Example 1 of [[cpp.embed.param.limit]]:

```cpp
#undef DATA_LIMIT
#if __has_embed(<data.dat> limit(DATA_LIMIT))   // equivalent to limit(0)
#endif
```

Example 2 of the same subclause has a subtlety: `#embed <data.dat> limit(__has_include("a.h"))` is valid, because `__has_include` can be used under the `#if` rules; the same contents inside `__has_embed(...)` are ill-formed, because `__has_include` can't appear inside the parentheses of `__has_embed`.

`limit` is commonly used to take just the head of a file, such as a magic number or signature, or to take a finite number of bytes from an unbounded resource (such as `/dev/urandom`):

```cpp
constexpr unsigned char sound_signature[] = {
#embed <sdk/jump.wav> limit(2+2)     // only the first 4 bytes, i.e. "RIFF"
};
static_assert(sizeof(sound_signature) == 4);
```

`offset(...)` specifies how many elements to skip first ([[cpp.embed.param.offset]]), with the same evaluation rules and restrictions as `limit`. When combined, skip first, then limit:

```cpp
#embed <sdk/jump.wav>                    // arr
#embed <sdk/jump.wav> offset(2)          // offset_arr[0] == arr[2]
#embed <sdk/jump.wav> offset(1) limit(1) // offset_limit_arr[0] == arr[1]
```

Clang 23 doesn't support the standard `offset` yet, reporting unknown embed preprocessor parameter 'offset', but provides the extension parameter `clang::offset` with the same semantics:

```cpp run title="embed-offset.cpp" impl flags="-std=c++2c -Wno-c23-extensions" cc=clang_trunk
// ABCDEFG
constexpr unsigned char mid[] = {
#embed __FILE__ clang::offset(3) limit(3)   // skip "// ", take "ABC"
};
static_assert(mid[0] == 'A' && mid[1] == 'B' && mid[2] == 'C');
int main() {}
```

### prefix, suffix and if_empty

`prefix(...)` and `suffix(...)` put the tokens in their parentheses immediately before or after the list when the resource is nonempty, and are ignored when it's empty ([[cpp.embed.param.prefix]], [[cpp.embed.param.suffix]]). They solve the separator problem. Here's the example from [[cpp.embed.param.suffix]]:

```cpp
constexpr unsigned char whl[] = {
#embed "ches.glsl" \
  prefix(0xEF, 0xBB, 0xBF, ) /* a UTF-8 BOM and a comma when nonempty */ \
  suffix(,)                  /* a trailing comma when nonempty */
  0                          /* always ends with 0 */
};
// an empty file gives { 0 }; a nonempty one gives { 0xEF, 0xBB, 0xBF, data..., 0 }
```

Without these two parameters, writing `{ 0xEF, 0xBB, 0xBF, #embed ..., 0 }` directly would produce consecutive commas like `0xBF, , 0` when the resource is empty, which is a syntax error.

A common use is producing a null-terminated string:

```cpp run title="embed-cstr.cpp" ok flags="-std=c++2c -Wno-c23-extensions"
// this file begins with "//"
constexpr unsigned char text[] = {
#embed __FILE__ limit(2) suffix(, 0)
};
static_assert(sizeof text == 3 && text[0] == '/' && text[2] == 0);
int main() {}
```

`if_empty(...)` is the opposite: ignored when the resource is nonempty; when it's empty, the whole `#embed` directive is replaced by the tokens in its parentheses, and naturally `prefix` and `suffix` don't appear ([[cpp.embed.param.if.empty]]).

```cpp run title="embed-if-empty.cpp" ok flags="-std=c++2c -Wno-c23-extensions"
constexpr int v[] = {
#embed __FILE__ limit(0) prefix(1, ) suffix(, 2) if_empty(-1)
};
static_assert(sizeof v == sizeof(int) && v[0] == -1);   // the resource is empty; only if_empty remains
int main() {}
```

The three examples in [[cpp.embed.param.if.empty]] show what counts as empty: `limit(0)` makes any resource empty, in `__has_embed` too; a 1-byte resource with `offset(1)` is also empty.

## Writing the resource name with macros (¶14)

¶14 If `embed` isn't followed by a header-name token, the rest of the directive is first macro-expanded, and then a header name is formed from the spellings of, and whitespace between, the tokens immediately following `embed`, with whitespace handled in an implementation-defined way. If that succeeds, it's processed as in the direct form; if not, the program is ill-formed. The same situation for `#include` is IFNDR; this is stricter. Note 2 likewise reminds that adjacent string literals aren't concatenated.

Note 3 stresses that the whole directive is macro-expanded only once. Example 4:

```cpp
#define EMPTY
#define X myfile
#define Y rsc
#define Z 42
#embed <myfile.rsc> prefix(Z)    // direct form: only the part after the header name is expanded
#embed EMPTY <X.Y>  prefix(Z)    // macro form: the whole thing is expanded; X, Y and Z are all replaced
// both lines are equivalent to #embed <myfile.rsc> prefix(42)
```

For the second line, Clang 23 doesn't expand the `X` and `Y` in `<X.Y>` and reports 'X.Y' file not found, which disagrees with the draft. The same goes for the analogous `#include` case (see [[cpp.include]]).

## Probing with __has_embed

`__has_embed` is defined in [[cpp.cond#4]]. It processes the tokens in its parentheses as `#embed` would, giving `__STDC_EMBED_NOT_FOUND__` (0), `__STDC_EMBED_FOUND__` (1) or `__STDC_EMBED_EMPTY__` (2); these three macros are in [[cpp.predefined]]. An unknown parameter makes the result 0 rather than making the program ill-formed, so you can try a vendor parameter first and fall back to the standard form:

```cpp
#if __has_embed("logo.png" vendor::compress(zstd)) == __STDC_EMBED_FOUND__
  // the implementation supports this vendor parameter, and the resource is nonempty
#elif __has_embed("logo.png") == __STDC_EMBED_FOUND__
  // without the vendor parameter
#endif
```

## Implementation view

!!! impl "Why #embed is fast"
    The standard semantics are expansion into a list of integer literals, but under the as-if rule an implementation only needs to produce the same result. Clang generates, in the preprocessor, a special token carrying the resource data for the parser, which eventually becomes the AST node `EmbedExpr`. In common cases such as initializing an `unsigned char` array, the data is copied as a block, without creating an integer literal node per byte. So embedding resources of tens of MB is acceptable in memory and time. Only when the preprocessed output is printed with `-E` is it really printed as `65, 66, 67, ...`.

!!! impl "Dependency tracking"
    Embedded resources, like included headers, appear in dependency files generated by `-MD` and `-MMD`, so the build system recompiles when a resource changes. Tested with Clang 23, this is indeed the case.

!!! impl "Clang 23 support"
    `#embed` is available in C++ mode but warned about as an extension; `clang::offset` is supported but the standard `offset` isn't; the feature-test macro `__cpp_pp_embed` isn't defined.

## History

!!! history
    - Before `#embed`, the community embedded data with `xxd -i`, `.incbin`, binary inputs to the linker and the like; there was also a `std::embed` proposal for reading files at compile time as a library function, which wasn't adopted.
    - C23 standardized `#embed` first.
    - C++26 brought in the same mechanism through [[P1967R14]], adding `__has_embed`, the `__STDC_EMBED_*__` macros and the feature-test macro `__cpp_pp_embed` at the same time. The `offset` parameter was added later.

## Questions

!!! question "Question 1"
    The resource `r.bin` has 5 bytes. What does each directive below expand to?
    ```cpp
    #embed "r.bin" offset(3) limit(10)
    #embed "r.bin" offset(7) prefix(1,) if_empty(0)
    #embed "r.bin" limit(0) suffix(,9)
    ```

<details markdown="1">
<summary>Answer</summary>

By ¶9, the byte count is 5.

1. The offset is 3, resource-count = max(min(10, 5 − 3), 0) = 2, expanding to the values of the 4th and 5th bytes.
2. The offset is 7, resource-count = max(5 − 7, 0) = 0, the resource is empty: `prefix` is ignored, and the whole directive is replaced by the contents of `if_empty`, `0`.
3. resource-count = max(min(0, 5), 0) = 0, the resource is empty: `suffix` is ignored; there's no `if_empty`, so it expands to nothing, no tokens at all.
</details>

!!! question "Question 2"
    Why are the elements of `#embed` specified to be of type `int` with values from `fgetc`, rather than directly as values of type `unsigned char`?

<details markdown="1">
<summary>Answer</summary>

The preprocessor can only produce preprocessing tokens, and there's no way to write an integer literal of type `unsigned char`; the smallest integer literal type is `int` ([[lex.icon]]). Specifying integer literals of type `int` means `#embed` can be understood as plain text (the `-E` output can be compiled again) and can be used anywhere a list of integers can be written. Taking the values from `fgetc` pins byte values down precisely as nonnegative `unsigned char` values, avoiding the implementation-defined difference of whether `char` is signed. The cost is the narrowing problem mentioned earlier: the receiver must use `unsigned char` or a wider type.
</details>

## Summary

!!! summary
    - `#embed` expands a resource into comma-separated integer literals of type `int`, with values as if from byte-by-byte `fgetc`, ranging from 0 to `UCHAR_MAX`.
    - The search parallels `#include`: bracket resource search, quote resource search (falling back to bracket search); separate search paths are recommended.
    - The parameter part is always macro-expanded first; failing to form a resource name in the macro form is ill-formed, stricter than `#include`.
    - `limit` and `offset` are evaluated by the `#if` rules and must not be less than 0; the number of elements is max(min(limit, bytes − offset), 0).
    - `prefix` and `suffix` take effect only when the resource is nonempty; `if_empty` takes effect only when it's empty, and replaces the whole directive.
    - Receive in `unsigned char` to avoid narrowing.
