---
title: C++ and ISO C++ 2014
summary: "What previously valid code breaks or changes behavior when moving from C++14 to C++17: trigraphs, pp-numbers absorbing p±, removal of bool increment and register, deduction for auto x{1}, noexcept becoming part of the function type, aggregates with base classes, the new semantics of inheriting constructors, removal of dynamic exception specifications, and removal of library facilities such as auto_ptr, bind1st and random_shuffle."
updated: 2026-10-19
---

!!! tldr
    - C++17 removes a batch of obsolete language features: trigraphs, `register`, `++` on `bool`, and dynamic exception specifications such as `throw(int)`.
    - `noexcept` becomes part of the function type: `void() noexcept` and `void()` are two types. Template deduction, specializations of type traits and name mangling are all affected.
    - `auto x{1};` deduces `int` rather than `std::initializer_list<int>`; a class with a public base can be an aggregate, so `T{}` may change from calling the default constructor to aggregate initialization.
    - `new` of an over-aligned type now calls the allocation function taking `std::align_val_t`, so memory-accounting code that replaced only `operator new(size_t)` misses these allocations.
    - The library removes `auto_ptr`, `random_shuffle`, `bind1st`, `bind2nd`, `ptr_fun`, `mem_fun` and others, each with a direct replacement.

[diff.cpp14] lists the incompatibilities of C++17 relative to C++14: previously well-formed code that becomes ill-formed in C++17, or whose meaning changes. Every entry in the standard has the same format: the affected subclause, what changed, why, and the effect on old code.

¶1 This subclause lists differences in addition to those in the subclauses above: to upgrade from C++14 to the current draft you also need to read [[diff.cpp17]] and the subclauses after it. Entries follow the order of the chapters in the main text. All tests on this page use Clang 23.1.3 with libc++, comparing `-std=c++14` with `-std=c++17`. Several entries are treated by compilers as defect fixes and already have the new behavior under `-std=c++14`; this is noted entry by entry below.

## Lexical conventions [diff.cpp14.lex] {#diff.cpp14.lex}

### Support for trigraphs is no longer required

```cpp
const char* s = "??=";   // C++17: "??="; C++14: "#"
```

¶1 A **trigraph** ([[g:trigraph]]) is three characters starting with `??` that are replaced by one character in the earliest phase of translation, for example `??=` by `#` and `??/` by `\`. They were designed for writing C programs on old keyboards and character sets that lacked some characters. C++17 no longer requires support for them ([[lex.phases]]).

The reason for removal is that they often took effect by accident in strings and comments. The classic example is the comment `// what is this??/`: `??/` becomes `\`, which splices the next line of code into the comment. Implementations may still replace trigraphs outside raw string literals when mapping source file characters to the translation character set (an implementation-defined step), so platforms that really need trigraphs (such as EBCDIC) can enable them with a compiler option; Clang and GCC use `-trigraphs`.

Clang 23 replaces the example above with `#` under `-std=c++14` and warns; under `-std=c++17` it keeps `??=` and notes trigraph ignored.

### Preprocessing numbers can contain `p+` and `p-`

```cpp error
#define F(a) b ## a
int b0p = F(0p+0);   // error: in C++14 equivalent to int b0p = b0p + 0;
```

¶2 A numeric token in the preprocessing phase is a **preprocessing number** ([[g:pp-number]]); its grammar is loose and swallows more characters than real numeric literals. To support hexadecimal floating-point literals such as `0x1p+3`, C++17 lets a preprocessing number contain `p+`, `p-`, `P+` and `P-` ([[lex.ppnumber]]). So a character sequence like `0p+0` or `0e1_p+0` is three tokens in C++14 and one in C++17.

In the example above, C++14 splits the argument into `0p`, `+` and `0`, `b ## 0p` pastes into `b0p`, giving `int b0p = b0p + 0;`. In C++17 the argument is the single token `0p+0`, the pasted `b0p+0` is not a valid token, and the program is ill-formed. You will almost never meet this in real code.

Clang 23 does not fully implement this: under `-std=c++17` it still absorbs `p+` only for numbers starting with `0x`, and expands the example to `int b0p = b0p+0;`.

## Expressions [diff.cpp14.expr] {#diff.cpp14.expr}

### Increment of `bool` removed

```cpp error
bool b = false;
void f() { ++b; b++; }   // error: well-formed in C++14
```

¶1 C++17 no longer allows `++` on `bool` ([[expr.post.incr]], [[expr.pre.incr]]); `--` was never allowed. The effect of `b++` is always to set `b` to `true`, a surprising and long-obsolete semantics. Change `++b` to `b = true`, and a `b++` whose value is used to `std::exchange(b, true)`.

Clang 23 gives a `-Wdeprecated-increment-bool` warning under `-std=c++14` and an error under `-std=c++17`.

### Dynamic allocation of over-aligned types

```cpp run title="overaligned.cpp" ok
#include <cstdio>
#include <cstdlib>
#include <new>
void* operator new(std::size_t n) {
  std::puts("operator new(size_t)");
  return std::malloc(n);
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

struct alignas(64) V { char c; };
int main() {
  V* v = new V;
  std::printf("%lu\n", reinterpret_cast<unsigned long>(v) % 64);
  delete v;
}
```

¶2 A type whose alignment requirement exceeds `__STDCPP_DEFAULT_NEW_ALIGNMENT__` (16 on common platforms) is an **over-aligned** type. In C++14, `new` of such an object called the ordinary `::operator new(std::size_t)`, which does not guarantee suitably aligned memory. C++17 calls `::operator new(std::size_t, std::align_val_t)` instead ([[expr.new]], [[expr.delete]]), provided the class has no allocation function of its own.

Running the example on Clang 23, under `-std=c++14` the custom `operator new` is called and the address modulo 64 is 32, not aligned; under `-std=c++17` the custom function is not called and the address modulo 64 is 0.

So a program that replaced only `operator new(size_t)` misses allocations of over-aligned types under C++17, affecting code such as memory accounting and memory pools. When replacing the global allocation functions, replace the `std::align_val_t` versions too (single-object and array, `nothrow`, sized `delete`); see [[new.delete]].

## Declarations [diff.cpp14.dcl.dcl] {#diff.cpp14.dcl.dcl}

### `register` removed

```cpp error
void f() { register int x = 0; }   // error: well-formed in C++14
```

¶1 `register` is no longer a storage class specifier ([[dcl.stc]]), but it remains a reserved keyword so it can be repurposed later. Simply delete it; the meaning does not change. Watch out for C headers included by C++ code, where `register` is an error too. Clang 23 gives a `-Wdeprecated-register` warning under `-std=c++14` and an error under `-std=c++17`.

### Deducing `auto` from braces

```cpp
auto x1{1};      // C++17: int; C++14: std::initializer_list<int>
auto x2{1, 2};   // error: std::initializer_list<int> in C++14
auto x3 = {1};   // std::initializer_list<int> in both
```

¶2 For direct-list-initialization `auto x{...}`, C++17 requires a single element in the braces and deduces `auto` as that element's type; C++14 deduced `std::initializer_list` ([[dcl.spec.auto]]). Copy-list-initialization `auto x = {...}` is unchanged and still deduces `initializer_list`. The new rule is more intuitive: `auto x{1};` and `int x{1};` give the same type.

Clang 23 treats this as a defect fix: under `-std=c++14`, `x1` is also `int` and `x2` is also an error.

### Exception specifications become part of the function type

```cpp error
void g1() noexcept;
void g2();
template<class T> int f(T*, T*);
int x = f(g1, g2);   // error: conflicting deductions for T; well-formed in C++14
```

¶3 In C++17, `noexcept` is part of the function type: `void() noexcept` and `void()` are different types ([[dcl.fct]]). A pointer to a `noexcept` function converts implicitly to a pointer to an ordinary function, but not the other way round, so the type system can prevent a potentially-throwing function from being passed where only non-throwing ones are accepted.

In the example above, the two arguments deduce `T = void() noexcept` and `T = void()` respectively, and the deductions conflict. Specifying the template argument explicitly (`f<void()>(g1, g2)`) fixes it.

Two other things are affected. Specializations keyed on function types, such as your own function type traits or traits classes for member function pointers, need an extra specialization for `R(Args...) noexcept`. Name mangling changes too: a function whose parameter types include a pointer to a `noexcept` function has different symbol names under C++14 and C++17.

### Aggregates can have base classes

```cpp
struct derived;
struct base {
  friend struct derived;
private:
  base();
};
struct derived : base {};

derived d1{};   // error: well-formed in C++14
derived d2;     // OK
```

¶4 Since C++17, a class with public non-virtual base classes can also be an **aggregate** ([[dcl.init.aggr]]); in brace initialization the base class subobjects come before the members, as in `struct D : B { int x; }; D d{{}, 1};`.

For such a class, empty braces `derived{}` change from calling the default constructor to aggregate initialization. Aggregate initialization initializes the bases one by one at the point of initialization, and access checking also happens there: `base()` is private and `derived` is its friend, but the initialization of `d1` happens at global scope, where it is inaccessible. `d2` still calls `derived`'s implicitly defined default constructor, which as a friend can access `base()`.

Changing `d1{}` to `d1` makes it compile. Declaring a constructor for `derived` also works, but then it is no longer an aggregate; see the [dcl] section of [[diff.cpp17]].

## Classes [diff.cpp14.class] {#diff.cpp14.class}

### Inheriting constructors no longer inject constructors into the derived class

```cpp
struct A {
  template<typename T> A(T, typename T::type = 0);
  A(int);
};
struct B : A {
  using A::A;
  B(int);
};
B b(42L);   // C++17: calls B(int)
            // C++14: calls the injected B<long>(long), which then calls A(int)
```

¶1 In C++14, `using A::A;` declared a set of new constructors in `B`, one for each constructor of `A`. C++17 changes this: the declaration only makes `A`'s constructors visible when initializing a `B`, and they take part in overload resolution directly ([[class.inhctor.init]]). Under the old model, default arguments, templates, access control and `explicit` all behaved strangely in various ways; the new model fits better with the rest of the language.

In the example above, C++14 injects `template<class T> B(T)` for `A`'s constructor template, without the default argument, so `B<long>(long)` is an exact match for `42L` and beats `B(int)`, which needs a conversion. It then calls `A<long>(long)`, which is eliminated by the substitution failure for `long::type`, and falls through to `A(int)`. In C++17 the inherited template takes part in resolution as it is, is likewise eliminated by substitution failure, and the remaining `B(int)` wins.

Clang 23 applies the new semantics in all modes: with prints added to the constructors, both `-std=c++14` and `-std=c++17` print `A(int)` then `B(int)`. Very little real code is affected.

## Templates [diff.cpp14.temp] {#diff.cpp14.temp}

### Deduction from the type of a constant template argument

```cpp error
template <int N> struct A;
template <typename T, T N> int foo(A<N>*) = delete;
void foo(void*);
void bar(A<0>* p) {
  foo(p);   // error: calls the deleted template; in C++14 calls foo(void*)
}
```

¶1 C++17 allows `auto` as the type of a constant template parameter (`template<auto N>`), and partial specializations need to be able to extract the type of `N` from it. So C++17 says that in a declaration like `template<typename T, T N>`, when deducing from `A<N>`, `T` can also be deduced from the type of `N` ([[temp.deduct.type]]).

In C++14, `T` cannot be deduced, the template is eliminated, and `foo(void*)` is called. In C++17, `T = int` is deduced, the template is an exact match for `A<0>*` and beats `foo(void*)`, which needs a conversion, and the deleted function is selected. Clang 23 reports call to deleted function under `-std=c++17`.

## Exception handling [diff.cpp14.except] {#diff.cpp14.except}

### Dynamic exception specifications removed

```cpp error
void g() throw(int);   // error: well-formed in C++14
```

¶1 A `throw(T1, T2, ...)` after a function declaration is a **dynamic exception specification** ([[g:dynamic-exception-specification]]); C++17 removes its potentially-throwing forms ([[except.spec]]). They were complicated and brittle to use and did not fit the type system well; with `noexcept` becoming part of the function type, the problem got worse. Just delete the `throw(...)`.

`throw()` was kept for now as a synonym for `noexcept`, and C++20 removed it as well; see [[diff.cpp17]]. When `throw()` is violated, C++17 calls `std::terminate` rather than `std::unexpected`, and whether the stack is unwound before the call is unspecified.

Clang 23 accepts it under `-std=c++14` (warning only with `-Wdeprecated`) and reports an error under `-std=c++17`.

## Library introduction [diff.cpp14.library] {#diff.cpp14.library}

¶1 C++17 adds the headers `<any>`, `<charconv>`, `<execution>`, `<filesystem>`, `<memory_resource>`, `<optional>`, `<string_view>` and `<variant>` ([[headers]]). If a project has a header with the same name and includes it with `#include <...>`, it may get the standard library's version.

¶2 Names in the global namespace consisting of `std` followed by digits (`std1`, `std2` and so on) are reserved for future use by the standard library ([[namespace.future]]); code using such top-level namespaces needs to rename them.

## General utilities library [diff.cpp14.utilities] {#diff.cpp14.utilities}

¶1 The constructors of `std::function` that accept an allocator are removed ([[func.wrap]]), because implementations supported them very inconsistently. Code that constructs a `std::function` with an allocator is ill-formed, and uses-allocator construction no longer passes an allocator to `std::function`.

### Converting from `unique_ptr` to `shared_ptr`

```cpp error
#include <memory>
std::unique_ptr<int[]> arr(new int[1]);
std::shared_ptr<int> ptr(std::move(arr));   // error: int(*)[] is not compatible with int*
```

¶2 C++17 makes `shared_ptr` support arrays, so you can write `shared_ptr<T[]>` and `shared_ptr<T[N]>`. To that end, the constraint on constructing a `shared_ptr<T>` from a `unique_ptr<Y, D>` now requires `Y*` to be compatible with `T*` and the `unique_ptr`'s pointer type to be convertible to the `shared_ptr`'s element pointer type ([[util.smartptr.shared]]). In the example above `Y` is `int[]`, `int(*)[]` is not compatible with `int*`, and the program is ill-formed. Use `std::shared_ptr<int[]>` instead.

In our tests libc++ rejects the example under `-std=c++14` as well.

## Strings library [diff.cpp14.string] {#diff.cpp14.string}

### Non-const `data()`

```cpp error
int f(char*) = delete;
int f(const char*);
std::string s;
int x = f(s.data());   // error: selects the deleted f(char*); well-formed in C++14
```

¶1 C++17 adds a non-const `data()` to `basic_string` that returns `charT*` ([[basic.string]]), consistent with `std::vector::data()`. Calling `data()` on a non-const string now yields `char*` instead of `const char*`, and functions overloaded separately for `char*` and `const char*` take the other branch. When you need a `const char*`, use `s.c_str()` or `std::as_const(s).data()`.

## Containers library [diff.cpp14.containers] {#diff.cpp14.containers}

### The comparator's call operator must be const

```cpp error
#include <set>
struct compare {
  bool operator()(int a, int b) { return a < b; }   // missing const
};
int main() {
  const std::set<int, compare> s;
  s.find(0);   // may fail to compile in C++17
}
```

¶1 C++17 clarifies the requirements on associative containers: the function call operator of the comparison object must be callable on a const comparison object ([[associative.reqmts]]). Adding `const` to `operator()` fixes it. In our tests libc++ rejects the example in both modes, with a library-specific warning that the comparator has no usable const call operator.

## Removed deprecated features [diff.cpp14.depr] {#diff.cpp14.depr}

¶1 C++17 removes `auto_ptr`, `unary_function`, `binary_function`, `random_shuffle`, `ptr_fun`, `mem_fun`, `mem_fun_ref`, `bind1st` and `bind2nd`, all of which have been superseded by newer features:

| Removed | Replacement |
|---|---|
| `auto_ptr` | `unique_ptr` |
| `unary_function`, `binary_function` | no base class needed; use `invoke_result_t` when you need the result type |
| `random_shuffle` | `std::shuffle(first, last, urbg)` |
| `ptr_fun` | pass the function pointer or a lambda directly |
| `mem_fun`, `mem_fun_ref` | `std::mem_fn` |
| `bind1st`, `bind2nd` | a lambda or `std::bind` |

Replacing `auto_ptr` with `unique_ptr` is usually mechanical, but mind `auto_ptr`'s transfer-of-ownership-on-copy semantics: where `a = b` used to transfer ownership silently, it must become `a = std::move(b)`. `unique_ptr` cannot be copied, so the compiler points out all of these places. libc++ gives deprecation warnings for these names under `-std=c++14` and reports them as nonexistent under `-std=c++17`.

¶2 The iostream members kept in [depr.ios.members] for compatibility with pre-standard code are removed, for example the types `ios_base::io_state`, `open_mode` and `seek_dir`. Use `iostate`, `openmode` and `seekdir` instead.

## Summary

| Entry | Fate of old code | Clang 23 / libc++ |
|---|---|---|
| trigraphs | changed meaning | implemented |
| preprocessing numbers absorbing `p±` | ill-formed or changed meaning | not fully implemented |
| `bool` increment | ill-formed | implemented, warning in C++14 |
| `new` of over-aligned types | a different allocation function called | implemented |
| `register` | ill-formed | implemented, warning in C++14 |
| `auto x{1}` | type changes | implemented, same in C++14 mode |
| `noexcept` in the function type | ill-formed, mangled names change | implemented |
| aggregates with base classes | ill-formed or changed meaning | implemented |
| inheriting constructors | a different constructor called | implemented, same in C++14 mode |
| deduction from the type of a constant argument | ill-formed | implemented |
| dynamic exception specifications | ill-formed | implemented |
| allocator for `std::function` | ill-formed | removed |
| `unique_ptr<T[]>` to `shared_ptr<T>` | ill-formed | rejected in both modes |
| non-const `data()` | a different overload called | implemented |
| non-const comparator | ill-formed | rejected in both modes |
| removed deprecated features | ill-formed | removed |
