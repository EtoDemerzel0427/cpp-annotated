---
title: C++ and ISO C++ 2023
summary: "What previously valid code breaks or changes behavior when moving from C++23 to C++26: new tokens and keywords, mixed enumeration arithmetic and array comparison becoming errors, delete of an incomplete type, pack indexing, restrictions on macro names, the output of to_string, and a batch of removed library facilities."
updated: 2026-10-19
---

!!! tldr
    - Two kinds of code deprecated in C++20 become errors in C++26: arithmetic and comparisons between different enumerations or between an enumeration and a floating-point type, and directly comparing two arrays. `delete` of a pointer to an incomplete class type also becomes an error.
    - Static reflection, contracts and pack indexing take over previously valid syntax: the tokens `^^` and `:]`, the keyword `contract_assert`, and unnamed `T...[n]`. `pre`, `post` and all keywords can no longer be defined as macros.
    - The floating-point `std::to_string` now produces the shortest round-trip representation: `to_string(3.14)` changes from `"3.140000"` to `"3.14"`. The code compiles as before and the output changes silently.
    - The library removes `<codecvt>`, `<strstream>`, `wstring_convert`, the atomic free functions for `shared_ptr`, the no-argument `string::reserve()`, and `allocator::is_always_equal`.
    - Compiling with `-std=c++23`, Clang gives deprecation or compatibility warnings for most of the soon-to-break code; clean them up before upgrading.

[diff.cpp23] lists the incompatibilities of C++26 relative to C++23: previously well-formed code that becomes ill-formed in C++26, or whose meaning changes. Every entry in the standard has the same format: the affected subclause, what changed, why, and the effect on old code, usually with an example. For changes after C++26 see [[diff.cpp26]]; for earlier versions see [[diff.cpp20]] and so on.

¶1 This subclause follows the order of the chapters in the main text, and the page below is grouped the same way. All tests on this page use Clang 23.1.3 with libc++, comparing `-std=c++23` with `-std=c++2c`.

## Lexical conventions [diff.cpp23.lex] {#diff.cpp23.lex}

### New token `^^`

```cpp error
struct C { int operator^(int); };
int operator^(int (C::*p)(int), C);
int i = &C::operator^^C{};   // error: well-formed in C++23
```

¶1 C++26 adds the reflection operator `^^` ([[g:reflection-operator]], see [[expr.reflect]]), which is a new token ([[lex.operators]]). Tokenization always takes the longest sequence of characters that can form a token ([[lex.pptoken]]), so two adjacent `^` characters are now read as one `^^`.

C++23 splits the third line into `&C::operator^`, `^`, `C{}`: take a pointer to member function, then call the second `operator^`. In C++26, `operator` is followed by `^^`, which forms no operator function name, and the program is ill-formed. A space between the two `^` restores the original meaning.

Clang 23 does not implement static reflection yet and accepts this code in both modes.

### New keyword `contract_assert`

```cpp error
int contract_assert = 0;   // error: contract_assert is a keyword
```

¶2 The C++26 contract assertion statement is written `contract_assert(condition);` ([[stmt.contract.assert]]), so `contract_assert` becomes a keyword ([[lex.key]]) and can no longer be used as a name. The `pre` and `post` used for function contracts are not keywords but identifiers with special meaning ([[g:identifier-with-special-meaning]]); they can still be variable names but cannot be defined as macros (see the [cpp] section below).

Clang 23 does not implement contracts yet and accepts this code in both modes.

## Expressions [diff.cpp23.expr] {#diff.cpp23.expr}

### Mixing an enumeration with another enumeration or a floating-point type

<div class="compare" markdown="1">

```cpp error
enum E1 { e };
enum E2 { f };
bool b = e <= 3.7;      // error
int  k = f - e;         // error
auto x = true ? e : f;  // error
```

```cpp ok
enum E1 { e };
enum E2 { f };
bool b = +e <= 3.7;     // OK
int  k = +f - e;        // OK
int  y = e + 1;         // OK: same enumeration and an integer
```

</div>

¶1 Before computing, a binary operator converts both operands to a common type; this step is the **usual arithmetic conversions** ([[expr.arith.conv]]). C++26 says that if one operand is of enumeration type and the other is of a different enumeration type or a floating-point type, the program is ill-formed. The same applies when the two operands of a conditional operator are of different enumerations.

Subtracting two unrelated enumerations, or comparing an enumeration with a `double`, is almost always a mistake, so C++20 first deprecated these uses and C++26 makes them errors. Arithmetic between an enumeration and an integer is unaffected. When you really need mixed arithmetic, convert the enumeration to an integer first with unary `+` or `static_cast<int>`. This entry also comes up often when porting C code to C++; see [[diff.iso]].

Clang 23 implements it: with `-std=c++23` it gives deprecation warnings such as `-Wdeprecated-enum-float-conversion` and `-Wdeprecated-enum-enum-conversion`; with `-std=c++2c` all three lines are errors.

### Comparing two arrays directly

<div class="compare" markdown="1">

```cpp error
int arr1[5];
int arr2[5];
bool same = arr1 == arr2;  // error
```

```cpp ok
int arr1[5];
int arr2[5];
bool idem = arr1 == +arr2; // compares addresses
bool less = arr1 < +arr2;  // result unspecified
```

</div>

¶2 If both operands of an equality or relational operator are arrays, the program is ill-formed ([[expr.rel]], [[expr.eq]]). `arr1 == arr2` looks like it compares contents, but both sides first undergo the array-to-pointer conversion and the addresses are compared, so it is almost always a mistake. C++20 deprecated it and C++26 makes it an error.

As long as one side is not of array type, for example `+arr2`, `&arr2[0]` or a pointer variable, nothing changes. The second line on the right compares the addresses of two unrelated objects, and the result of `<` is unspecified. If you meant to compare contents, use `std::ranges::equal` or `std::array`.

Clang 23 implements it: a `-Wdeprecated-array-compare` warning with `-std=c++23`, an error with `-std=c++2c`, with a hint to use unary `+` to make the operand decay to a pointer.

### `delete` of a pointer to an incomplete class type

```cpp error
struct S;

void f(S* p) {
  delete p;   // error: well-formed in C++23
}

struct S {};
```

¶3 A class that has been declared but not yet defined is an **incomplete type**. C++26 says the program is ill-formed if the operand of a *delete-expression* points to an incomplete class type ([[expr.delete]]).

At `delete p` the compiler cannot see `S`'s destructor or a class-specific `operator delete`, so all it can do is skip destruction and free the memory. C++23 allowed this, but if `S` ends up with a non-trivial destructor or its own deallocation function, the behavior is undefined. The new rule moves this error to compile time, and it only looks at whether `S` is complete where the `delete` appears: in the example above, `S` is later defined as a trivial class, and the code is rejected anyway.

The typical affected case is the pimpl idiom. The fix is to define the function that performs the `delete` (usually the outer class's destructor) in the `.cpp` file, after the definition of `S`. The default deleter of `std::unique_ptr<S>` has always rejected incomplete types with a `static_assert`, so code using it is unaffected.

Clang 23 implements it: a `-Wdelete-incomplete` warning with `-std=c++23`, an error with `-std=c++2c`.

## Declarations [diff.cpp23.dcl.dcl] {#diff.cpp23.dcl.dcl}

### Backing arrays of `initializer_list` can share storage

```cpp unspecified
#include <initializer_list>

bool ne(std::initializer_list<int> a,
        std::initializer_list<int> b) {
  return a.begin() != b.begin() + 1;
}
bool b = ne({2, 3}, {1, 2, 3});   // result unspecified
```

¶1 A `std::initializer_list` does not store its elements itself; they live in an array the compiler generates, called the **backing array** ([[g:backing-array]]). In C++23 every backing array is a distinct temporary array, so in the example above `a.begin()` and `b.begin() + 1` point to different objects and `ne` always returns `true`.

C++26 allows an implementation to put backing arrays with constant contents in static read-only storage, and to let lists with the same contents, or where one is a suffix of the other, share storage ([[dcl.init.list]]). So `{2, 3}` may be the last two elements of `{1, 2, 3}`, and the result of `ne` becomes unspecified. This way the array does not have to be rebuilt on the stack for every call. The comment in the standard's example says previously false, but by the C++23 rules it should be true; the substance here is that a definite result becomes unspecified.

Only code that relies on backing arrays having distinct addresses is affected, which is extremely rare in practice. Clang 23 prints `1` at both `-O0` and `-O2` in our tests; no sharing was observed.

### `T...[n]` is now pack indexing

```cpp
template <typename... T> void f(T... [1]);
template <typename... T> void g(T... ptr[1]);

int main() {
  f<int, double>(nullptr, nullptr);   // error: well-formed in C++23
  g<int, double>(nullptr, nullptr);   // OK
}
```

¶2 In C++23, `T... [1]` in a template declares an unnamed function parameter pack, each parameter of which has type array of `T`, immediately adjusted to a pointer, so the parameters of `f<int, double>` are `int*` and `double*`. C++26 introduces **pack indexing** ([[g:pack-index]]): `T...[n]` denotes the n-th element of pack `T`, so `f` now has a single parameter of type `double` and the original call is ill-formed ([[dcl.array]]).

What tells the two apart is whether the parameter has a name. `T... ptr[1]` has a name, so `...` can only be a pack expansion, and the meaning is unchanged; an unnamed `T... [1]` is now parsed as pack indexing. Naming the parameter keeps the original meaning.

Clang 23 parses it by the new rule under `-std=c++23` as well, with a `-Wpre-c++26-compat` warning that `T...[1]` is no longer a pack expansion.

### New token `:]`

```cpp
struct [[using CC:]] C;    // error: well-formed in C++23
struct [[using DD: ]] D;   // OK
```

¶3 The reflection splice syntax `[: r :]` ([[basic.splice]]) needs the new token `:]`. An attribute specifier can use a `using namespace:` prefix to avoid repeating the attribute namespace ([[dcl.attr.grammar]]). If no attribute follows the prefix and the colon is right next to `]`, `:]` is read as one token and the attribute syntax breaks. A space after the colon fixes it. Empty attribute specifiers like this practically never occur in real code.

Clang 23 does not implement this yet and accepts the first line in both modes.

## Templates [diff.cpp23.temp] {#diff.cpp23.temp}

### Fold-expression constraints require every element to be `bool`

```cpp error
template <typename... V> struct A;
struct S {
  static constexpr int compare(const S&) { return 1; }
};

template <typename... T, typename... U>
void f(A<T...>*, A<U...>*)
  requires (T::compare(U{}) && ...);   // each element is an int

void g(A<S, S>* ap) {
  f(ap, ap);   // error: well-formed in C++23
}
```

¶1 Before constraints (the condition in a *requires-clause*) are compared, they are decomposed into **atomic constraints**: subexpressions that cannot be decomposed further, each of which must have type exactly `bool` ([[temp.constr]]). C++23 treated a fold expression like `(E && ...)` as a single atomic constraint whose type is `bool`, so it did not matter that each `E` was an `int`.

C++26 normalizes such folds into **fold expanded constraints** ([[g:fold-expanded-constraint]]), in which each `E` becomes its own atomic constraint, so `E` itself must be `bool`. The change lets two constraints containing the same fold be compared for strength and take part in subsumption ([[temp.constr.order]]). The fix is an explicit conversion: `requires (bool(T::compare(U{})) && ...)`.

Clang 23 applies the new rule under `-std=c++23` as well; both modes report atomic constraint must be of type 'bool'.

### Deducing template arguments from an overload set

```cpp error
template <typename T>
void f(T&&, void (*)(T&&));

void g(int&);                             // #1
inline namespace A { void g(short&&); }   // #2
inline namespace B { void g(short&&); }   // #3

void q() {
  int x;
  f(x, g);   // error: well-formed in C++23, T deduced as int&
}
```

¶2 When an argument is a function name that denotes several overloads, template argument deduction tries each of the candidates ([[temp.deduct.call]]). The rule for a single candidate is unchanged: the type of #1, `void(int&)`, cannot match `void(T&&)`, so deduction fails; #2 and #3 both deduce `T = short`.

In C++23, as soon as more than one candidate deduced successfully, the second parameter did not participate in deduction; `T` was determined by the first argument alone as `int&`, and `g` then resolved to #1. To allow constraints to eliminate candidates from an overload set, C++26 rewrote this rule ([[temp.deduct.call#6]]): only candidates whose constraints are satisfied are tried, and if all successful deductions give the same result, that result is used. #2 and #3 both deduce `short`, so `T = short` is adopted, which conflicts with `int&` deduced from the first argument, and deduction fails.

The fix is to specify the template argument explicitly: `f<int&>(x, g)`. The second parameter's type is then `void(*)(int&)`, and `g` resolves to #1. Clang 23 reports the error by the new rule under `-std=c++23` as well.

## Preprocessing directives [diff.cpp23.cpp] {#diff.cpp23.cpp}

### Restrictions on macro names

```cpp
#define pre  1      // error: pre has a special meaning
#define post 2      // error
#define override    // error
#define int long    // error: int is a keyword
```

¶1 C++26 says that keywords, identifiers with special meaning (`final`, `override`, `import`, `module`, `pre`, `post` and so on, see [[lex.name]]) and the attribute names in [[dcl.attr]] cannot be defined or undefined as macros; `likely` and `unlikely` may be defined as function-like macros ([[cpp.replace.general]]). Previously, similar restrictions were written only in the library clauses and constrained only programs that use the standard library.

Macros like these silently change the meaning of the code that follows, with different effects on different implementations. The most common conflicts in old code are `#define pre ...` and `#define post ...`; renaming is enough.

Clang 23 implements little of this: there is no diagnostic for `pre` and `post`, and only a `-Wkeyword-macro` warning for keywords and `override`. Alternative tokens such as `and` and `or` are not identifiers and have never been allowed as macro names.

## Library introduction [diff.cpp23.library] {#diff.cpp23.library}

¶1 C++26 adds the headers `<contracts>`, `<debugging>`, `<hazard_pointer>`, `<hive>`, `<inplace_vector>`, `<linalg>`, `<meta>`, `<rcu>`, `<simd>`, `<stdbit.h>`, `<stdckdint.h>` and `<text_encoding>` ([[headers]]). If a project has a header with the same name and includes it with `#include <...>`, it may get the standard library's version.

## Memory management library [diff.cpp23.mem] {#diff.cpp23.mem}

¶1 Calling `realloc` with a non-null pointer and size 0 is now **erroneous behavior** ([[g:erroneous-behavior]]): the standard considers it an error, but the behavior is still defined, the effect is implementation-defined, and the implementation may diagnose it ([[c.malloc#6]]).

The cause is that C23 no longer defines such a call. Implementations already disagreed: glibc frees the memory and returns a null pointer, while macOS returned a new non-null pointer in our tests. Code that uses `realloc(p, 0)` to free memory was never portable; to free, call `free(p)`. The compiler will not report this; it needs to be checked by hand.

## Strings library [diff.cpp23.strings] {#diff.cpp23.strings}

```cpp
auto s = std::to_string(1e-7);   // C++26: "1e-07"   C++23: "0.000000"
auto t = std::to_string(3.14);   // C++26: "3.14"    C++23: "3.140000"
```

¶1 The floating-point overloads of `to_string` and `to_wstring` used to be equivalent to `sprintf("%f")`; they are now equivalent to `std::format("{}", val)`, which outputs the shortest representation that round-trips exactly ([[string.conversions]]). `%f` always keeps 6 decimal places, so `1e-7` becomes `"0.000000"`, and the decimal point character depends on the global C locale.

The code compiles as before; only the output string changes. Code that compares the result, writes it to a file or serializes it is affected; use `std::format("{:f}", x)` when you need the old format. libc++ in our tests does not implement this yet and prints the old format in both modes.

## Input/output library [diff.cpp23.io] {#diff.cpp23.io}

```cpp
std::istringstream in("\xF0\x9F\xA4\xA1 Clown Face");
in.ignore(100, '\xA1');   // C++26: stops at '\xA1'
in.ignore(100, -1L);      // C++26: ambiguous overload
```

¶1 `istream::ignore(n, delim)` used to have a single version, with `delim` of type `int_type`. On platforms where `char` is signed, `'\xA1'` converted to `int` is −95, while the stream internally compares against `traits::to_int_type(c)`, which is the non-negative 161; the two are never equal, so everything is ignored up to the end of file.

C++26 adds an `ignore(streamsize, char)` overload to `basic_istream<char>` ([[istream.unformatted]]), so a `char` argument no longer goes through the problematic conversion. The side effect is that when the second argument is neither an `int` nor a `char` (for example `-1L`), the two overloads are equally good and the call becomes ambiguous; an explicit conversion is needed.

libc++ in our tests has not added this overload, but its implementation stops correctly at `'\xA1'` in both modes (`tellg()` is 4), and the second line compiles in both as well.

## Removed deprecated features [diff.cpp23.depr] {#diff.cpp23.depr}

The facilities in this subclause were all listed in the deprecated-features annex [[depr]], and C++26 removes them. Per [[zombie.names]], the removed names become **zombie names** ([[g:zombie-name]]): programs may no longer use them, and implementations may continue to provide them.

### `allocator<T>::is_always_equal`

```cpp
#include <memory>
template <class T>
struct MyAlloc : std::allocator<T> {
  int tag;   // stateful
};
static_assert(!std::allocator_traits<MyAlloc<int>>
                  ::is_always_equal::value);
// C++23: fails   C++26: passes
```

¶1 The `is_always_equal` of `std::allocator` is `true_type`. A stateful allocator derived from it inherits this member, so `allocator_traits` wrongly assumes all its instances are equal, and the derived class has to remember to redefine it. With the member removed, `allocator_traits` falls back to its default inference, `is_empty<Alloc>`, and the example above becomes correct. libc++ implements this.

### Atomic access functions for `shared_ptr`

¶2 The free functions `std::atomic_load(const shared_ptr<T>*)`, `atomic_store`, `atomic_exchange` and `atomic_compare_exchange_*` are removed. The `shared_ptr` they protect is, by type, no different from an ordinary `shared_ptr`, so as soon as one piece of code bypasses these functions and accesses it directly, there is a silent data race. The replacement is `std::atomic<std::shared_ptr<T>>` ([[util.smartptr.atomic]]); when rewriting, change the variable's type and every access point together. libc++ in our tests still provides these functions in C++26 mode, without even a deprecation warning.

### The no-argument `basic_string::reserve()`

¶3 The no-argument `reserve()` is a non-binding shrink request that duplicates `shrink_to_fit()`, so it is removed. Change it to `shrink_to_fit()` or just delete the call. libc++ gives a deprecation warning in C++23 and reports too few arguments in C++26.

### `<codecvt>`, `<strstream>`, `wstring_convert`

¶4 The `<codecvt>` header and its `codecvt_utf8`, `codecvt_utf16`, `codecvt_utf8_utf16`, `codecvt_mode` and so on are removed. It had been deprecated since C++17 and supports only the obsolete UCS-2 encoding.

¶5 The `<strstream>` header and `istrstream`, `ostrstream`, `strstream` and `strstreambuf` are removed; they had been deprecated since the first C++ standard. For fixed buffers use C++23's `std::ispanstream` and `std::ospanstream`; for dynamic buffers use `std::stringstream`.

¶6 `wstring_convert` and `wbuffer_convert` are removed because they were underspecified and had no clear error-reporting mechanism. The standard library currently has no direct replacement; common options are third-party libraries such as ICU, or writing UTF conversion yourself.

libc++ implements all three: a `-Wdeprecated-declarations` warning in C++23, and the names do not exist in C++26.

## Summary

| Entry | Fate of old code | Clang 23 / libc++ |
|---|---|---|
| `^^` and `:]` tokens | ill-formed | not implemented |
| `contract_assert` keyword | ill-formed | not implemented |
| enumeration mixed with enumeration or floating-point | ill-formed | implemented, warning in C++23 |
| comparing two arrays | ill-formed | implemented, warning in C++23 |
| `delete` of an incomplete type | ill-formed | implemented, warning in C++23 |
| addresses of `initializer_list` backing arrays | result unspecified | no sharing observed |
| unnamed `T...[n]` | ill-formed or changed meaning | implemented, same in C++23 mode |
| fold expanded constraints | ill-formed | implemented, same in C++23 mode |
| deduction from an overload set | ill-formed | implemented, same in C++23 mode |
| macro name restrictions | ill-formed | mostly not implemented |
| `realloc(p, 0)` | erroneous behavior | no diagnostic |
| floating-point `to_string` | output changes | not implemented |
| `istream::ignore(n, char)` | behavior change or ambiguity | overload not added |
| removed deprecated features | ill-formed | all removed except the `shared_ptr` atomic functions |
