---
title: C++ and ISO C++ 2003
summary: Where valid C++03 (and C++98) code fails to compile or silently changes behavior when moved to C++11 and later, entry by entry, with before-and-after comparisons and what Clang 23 actually does.
updated: 2026-10-19
---

!!! tldr
    - This subclause lists where valid C++03 code fails to compile or changes behavior in C++11 and later. C++98 and C++03 differ only by some corrections, so it applies equally to C++98 code.
    - The compiler reports most of the changes: new keywords, `>>` closing two template argument lists, narrowing in brace initialization, implicitly deleted special members, streams no longer converting implicitly to `bool`.
    - The changes most in need of manual checking are the ones that produce no error: destructors are implicitly `noexcept`, so throwing calls `std::terminate`; a macro right next to a string literal is no longer expanded; and the introduction of xvalues changes the behavior of `typeid` and `?:`.
    - In the library, `basic_string` no longer allows copy-on-write, and `size()` of every container must be constant time. libstdc++ changed its ABI in GCC 5 because of this.
    - Clang applies several of these language changes in `-std=c++03` mode as well, so compiling in the old mode does not always reproduce the old behavior.

Annex C is an informative annex: it creates no rules and only points out where the main text changed (see [[diff]]). Every entry has the same fixed items: the affected subclause of the main text, what changed, why, and the effect on existing code. Below, these are retold as prose, and the annex's examples are compiled on Clang 23.1.3 with libc++ under both `-std=c++03` and `-std=c++11`.

## Lexical conventions {#diff.cpp03.lex}

### New string literal prefixes swallow macros

```cpp run std=c++17 title="u8macro.cpp" ok
#include <cstdio>
#define u8 "abc"
const char* s = u8"def";
int main() { std::puts(s); }
```

¶1 C++11 adds encoding prefixes and raw strings: `u8"…"`, `u"…"`, `U"…"`, `R"(…)"`, and the combinations `u8R`, `uR`, `UR` and `LR`. A macro whose name is one of these prefixes is no longer expanded when it is right next to a string literal; it becomes part of the literal. The program above prints `abcdef` in C++03 (after macro expansion the two literals are concatenated) and `def` in C++11 through C++17, with no diagnostic at all.

Since C++20, `u8"def"` has type `const char8_t[4]`, and this code fails with a type mismatch (see [[diff.cpp17]]).

### User-defined literals swallow macros

¶2 Since C++11, a string literal immediately followed by an identifier forms a single token: a user-defined literal ([[g:user-defined-literal]]). Previously these were two tokens, and the identifier was expanded if it was a macro.

```cpp run error
#include <cstdio>
#define _x "there"
int main() { std::puts("hello"_x); }   // error: needs operator""_x
```

In C++03 this prints `hellothere`. The most common case in real code is a format string written as `"%"PRId64` with no space in between. Clang reports `invalid suffix on literal; C++11 requires a space between literal and identifier` for it under C++11. The fix is to add a space between the literal and the macro.

### New keywords

¶3 The keywords new in C++11 are `alignas`, `alignof`, `char16_t`, `char32_t`, `constexpr`, `decltype`, `noexcept`, `nullptr`, `static_assert` and `thread_local`. C++03 code that uses them as identifiers is no longer valid. Clang's `-Wc++11-compat` finds them in advance under `-std=c++03`.

### Types of integer literals

¶4 C++11 adopts the C99 rule: an unsuffixed decimal integer literal tries `int`, `long` and `long long` in turn and never becomes an unsigned type. The C++03 rule listed only `int` and `long`, and the behavior was undefined if the value did not fit; implementations commonly followed C90 and used `unsigned long`. That change from an unsigned type to `long long` is what the annex is about.

```cpp
// platforms where long is 32 bits (ILP32, 64-bit Windows)
2147483648    // C++03 implementations: unsigned long; C++11: long long
-2147483648   // C++03 implementations: 2147483648 as unsigned long
              // C++11: -2147483648 as long long
```

Compiling with `--target=i386-linux-gnu -std=c++03`, Clang warns that this literal is undefined behavior in C++98, interprets it as `unsigned long`, and gives it type `long long` from C++11 on. What is mainly affected is hand-written constants like `INT_MIN`.

## Expressions {#diff.cpp03.expr}

### Only literals are integer null pointer constants

```cpp run ok
#include <cstdio>
void f(void*) { std::puts("#1"); }
void f(...)   { std::puts("#2"); }
template<int N> void g() {
  f(0*N);   // now calls #2; C++03 calls #1
}
int main() { g<0>(); }
```

¶1 In C++03, any integral constant expression with value 0 is a null pointer constant, so `0*N` in `g<0>` converts to `void*` and #1 is called. The function's behavior therefore depended on the value of the template argument. C++11 says an integer null pointer constant ([[g:null-pointer-constant]]) can only be an integer literal with value 0; `0*N` no longer counts, so #2 is called.

Clang prints `#2` under `-std=c++03` as well; it applies this change in all language modes. When you need a null pointer, write `nullptr`.

### xvalues change `typeid` and the conditional operator

C++11 introduces a new value category, the xvalue ([[g:xvalue]]). A member of a class rvalue, such as `C().b`, is now an xvalue, which is a glvalue. The annex records two behavior changes this brings.

```cpp run ok
#include <cstdio>
#include <typeinfo>
void f() {
  struct B {
    B() { std::puts("B()"); }
    virtual ~B() {}
  };
  struct C { B b; };
  (void)typeid(C().b);   // the operand is evaluated since C++11
}
int main() { f(); }
```

¶2 When the operand of `typeid` is a glvalue of polymorphic class type, it is evaluated to obtain the dynamic type ([[expr.typeid]]). `C().b` is an rvalue in C++03 and is not evaluated; in C++11 it is an xvalue and is evaluated, so a `C` is constructed and destroyed. The program above prints nothing in C++03 and prints `B()` in C++11, and Clang also gives a `-Wpotentially-evaluated-expression` warning.

¶5 When the second and third operands of the conditional operator are xvalues, the result can also be an xvalue, and a temporary is no longer forced to be copied ([[expr.cond]]). The annex's example `true ? BB().b : DD().d` calls `B`'s copy constructor one extra time in C++03 and neither copies nor moves in C++11. With a print added to the copy constructor, Clang's C++03 mode prints once and its C++11 mode does not print. Only code that depends on side effects of the copy constructor is affected.

### Integer division rounds toward zero

¶3 C++11 says the quotient of integer `/` rounds toward zero, which fixes the result of `%` as well; this is also the C99 rule. In C++03, whether rounding was toward zero or toward negative infinity when an operand was negative was implementation-defined. On an implementation that chose negative infinity, `-7 / 2` changes from −4 to −3 and `-7 % 2` from 1 to −1. Mainstream implementations have always rounded toward zero, so the practical effect is small.

### `&&` can appear in type names

```cpp error
bool b1 = new int && false;           // error: new (int&&)
struct S { operator int(); };
bool b2 = &S::operator int && false;  // error: operator int&&
```

¶4 In a type name, `&&` denotes an rvalue reference. C++03 parsed `new int && false` as `(new int) && false`, with result `false`; now `int &&` is taken as part of the *new-type-id*, allocating a reference type, which is ill-formed. Clang reports `cannot allocate reference type 'int &&' with new`. Parentheses fix it.

## Declarations {#diff.cpp03.dcl.dcl}

### `auto` is no longer a storage class specifier

¶1 `auto` becomes a placeholder type specifier that deduces a variable's type from its initializer ([[dcl.spec.auto]]). C++03's `auto int x;` is no longer valid. In C++11 and later modes Clang only gives a `-Wauto-storage-class` warning; it is an error only with `-pedantic-errors`. Just delete the `auto`.

### Narrowing in aggregate initialization

```cpp error
int x[] = { 2.0 };   // error: double → int is a narrowing conversion
```

¶2 Since C++11, brace initialization does not allow narrowing conversions ([[g:narrowing-conversion]]), and that includes the aggregate initialization C++03 already had. The rule is there to catch mistakes. Clang reports `type 'double' cannot be narrowed to 'int' in initializer list`; it is an error, but it can be turned off with `-Wno-c++11-narrowing`. Code with lots of C-style table initialization may have many of these; the fix is to write explicit conversions.

### Names in unnamed namespaces get internal linkage

```cpp ifndr
namespace { extern "C" { extern int x; } }  // #1
namespace A { extern "C" int x = 42; }      // #2
int main(void) { return x; }
```

¶3 C++11 changes names declared in unnamed namespaces from external to internal linkage, and says that language linkage (`extern "C"`) applies only to names with external linkage. This matches users' expectations: the whole point of an unnamed namespace is to make names visible only in the current file.

In C++03, #1 and #2 both have external linkage and C language linkage and are the same variable. Now #1 has internal linkage and C++ language linkage, #2 is not its definition, and the `x` used by `main` is #1, which is never defined; the program violates the ODR, no diagnostic required ([[basic.def.odr]]). Clang compiles and links it in all three modes, and the program returns 42, i.e. it still treats the two as the same variable. That is allowed for an IFNDR program, but it shows the compiler will not find this problem for you. Code like this is extremely rare in practice.

## Classes {#diff.cpp03.class}

### Implicit special member functions can be defined as deleted

```cpp error
struct S { int& r; };   // reference member: cannot be copy-assigned
S* p;
int n = sizeof(*p = *p);  // error: copy assignment is deleted
```

¶1 Since C++11, an implicitly declared default constructor, destructor, copy constructor or copy assignment operator whose implicit definition would be ill-formed is defined as deleted ([[class.default.ctor]], [[class.dtor]], [[class.copy.ctor]], [[class.copy.assign]]). A deleted function is detected already during overload resolution, so template argument deduction can fail cleanly.

The cost: C++03 allowed using such a function where no definition was needed, such as the unevaluated operand of `sizeof` above. Now the function called is deleted and the program is ill-formed. Clang's C++03 mode accepts this code; its C++11 mode reports `copy assignment operator is implicitly deleted`.

### Destructors are implicitly `noexcept`

```cpp run ok title="dtor_throw.cpp"
#include <cstdio>
struct D { ~D() { throw 1; } };
int main() {
  try { D d; } catch (...) { std::puts("caught"); }
}
```

¶2 Since C++11, a user-declared destructor without an exception specification has the same exception specification as an implicitly declared destructor would, which is usually non-throwing ([[except.spec]]). Throwing from such a destructor calls `std::terminate` directly, before `catch` can handle it.

The program above prints `caught` in C++03; in C++11 it prints `libc++abi: terminating due to uncaught exception of type int` with exit code 134. Clang warns `'~D' has a non-throwing exception specification but can still throw`. This is the entry most worth checking when upgrading: if the destructor really must throw, write `~D() noexcept(false)`; otherwise make it non-throwing.

## Templates {#diff.cpp03.temp}

### `export` repurposed for modules

¶1 C++03's exported templates (`export template<…>`) are removed, and the `export` keyword is reused for modules in C++20 ([[module]], [[cpp.module]], [[cpp.import]]). The original `export` had no implementation consensus; only the EDG front end ever implemented it. For `export template<class T> void f(T);` Clang gives only an `exported templates are unsupported` warning under `-std=c++03` and `-std=c++11`, and an error under `-std=c++20`. Just delete the `export`.

### `>>` can close two template argument lists

<div class="compare" markdown="1">

```cpp error
template <class T> struct X { };
template <int N> struct Y { };
X< Y< 1 >> 2 > > x;
// error: >> closes both Y and X
```

```cpp ok
template <class T> struct X { };
template <int N> struct Y { };
X< Y< (1 >> 2) > > x;
// OK: the >> in parentheses is a right shift
```

</div>

¶2 Since C++11, `>>` in a template argument list is treated as two `>`, closing two levels of templates in a row, so `vector<vector<int>>` no longer needs a space. The space requirement had long been seen as a minor nuisance, and with alias templates, nesting of non-class types becomes more common.

The cost is that right-shift expressions valid in C++03 may be misread. On the left, C++03 sees `Y<(1 >> 2)>`; now `Y< 1 >>` closes two levels first, and the remaining `2 > > x` cannot be parsed. Clang's C++03 mode uses `-Wc++11-compat` to warn that parentheses will be needed here.

### Dependent calls can find functions with internal linkage

```cpp run ok
#include <cstdio>
template<class T> void call(T t) { g(t, 0); }
namespace N {
  struct S {};
  void g(S, long) { std::puts("long"); }
  static void g(S, int) { std::puts("int"); }
}
int main() { call(N::S()); }   // prints int
```

¶3 In C++03, a dependent call at the template's point of instantiation could find only functions with external linkage through argument-dependent lookup, so the example could only call `g(S, long)`. C++11 removes this restriction; `g(S, int)` with internal linkage also takes part in overload resolution and is the better match ([[temp.dep.candidate]]). Clang prints `int` under `-std=c++03` as well.

## Standard library

Most library entries are adjustments to signatures and requirements; old code either fails to compile or, in rare cases, behaves differently.

### Names, headers and macros {#diff.cpp03.library}

¶1 Every identifier later added to the standard library may conflict with C++03 code. The typical case is defining your own `bind`, `function`, `array`, `move` or `begin` after `using namespace std;`, which becomes ambiguous with the new facility of the same name in `std`, or gets selected by argument-dependent lookup. Removing `using namespace std;` is the most thorough fix.

¶2 The new C++ headers are `<array>`, `<atomic>`, `<chrono>`, `<condition_variable>`, `<forward_list>`, `<future>`, `<initializer_list>`, `<mutex>`, `<random>`, `<ratio>`, `<regex>`, `<scoped_allocator>`, `<system_error>`, `<thread>`, `<tuple>`, `<typeindex>`, `<type_traits>`, `<unordered_map>` and `<unordered_set>`; the new C compatibility headers are `<cfenv>`, `<cinttypes>`, `<cstdint>` and `<cuchar>`. Code that wrote its own headers with the same names may break ([[headers]]).

¶3 `std::swap` moves from `<algorithm>` to `<utility>` ([[swappable.requirements]]). Code that uses `swap` having included only `<algorithm>` needs to include `<utility>` on some implementations.

¶4 The global namespace `posix` is reserved for future standardization ([[namespace.posix]]).

¶5 Attribute names can no longer be used as macro names, so C++03 code that defines `override`, `final` or `noreturn` macros is no longer valid ([[macro.names]]). The current draft has moved this rule to the preprocessing chapter ([[cpp.replace.general#9]]) and added `pre` and `post` along with contracts ([[diff.cpp23]]). Clang 23 gives only a warning for `#define override` and no diagnostic for `#define noreturn`.

### Exception specification of `operator new` {#diff.cpp03.language.support}

¶1 The declarations of the global `operator new` drop `throw(std::bad_alloc)`, to use `noexcept` uniformly ([[new.delete.single]]). A replacement `operator new` may throw other exceptions, and code that assumes it throws only `std::bad_alloc` may behave differently. Code that declares a replacement with `throw(std::bad_alloc)` is, according to the annex, now ill-formed. Since C++17 any dynamic exception specification with types is ill-formed; Clang accepts such declarations under C++03 and C++11 and reports an error from C++17 on.

### Thread-local `errno` {#diff.cpp03.diagnostics}

¶1 `errno` is thread-local, to support the new thread facilities ([[errno]]). Code that relied on all threads sharing one `errno` was already implementation-specific, and may now behave differently.

### Base classes of function objects {#diff.cpp03.utilities}

¶1 Standard function objects such as `std::plus`, `std::less` and `std::reference_wrapper` no longer derive from `std::unary_function` or `std::binary_function` ([[refwrap]], [[arithmetic.operations]], [[comparisons]], [[logical.operations]], [[bitwise.operations]]). These two base classes have been superseded by newer features and are no longer defined since C++17 ([[diff.cpp14]]). Code that relies on this derivation fails to compile.

### `basic_string` no longer allows copy-on-write {#diff.cpp03.strings}

¶1 The requirements on `basic_string` no longer allow reference-counted (copy-on-write, COW) implementations ([[string.classes]]). The iterator invalidation rules of reference-counted strings differ subtly from other implementations, and this change makes behavior uniform. C++11's data race rules also conflict with COW: a non-`const` `operator[]` must unshare first, which is a hidden write.

GCC's libstdc++ was originally a COW implementation. To comply with this entry, GCC 5 introduced a new `std::__cxx11::basic_string`, incompatible with the old ABI and selected by the `_GLIBCXX_USE_CXX11_ABI` macro.

¶2 Some `const` member functions, such as `data` and `c_str`, no longer invalidate iterators ([[string.require]]). This relaxation allows the small string optimization (SSO).

### Containers {#diff.cpp03.containers}

¶1 For every container that provides `size()`, `size()` must be constant time ([[container.requirements]]). C++03 did not specify its complexity, and implementations had inconsistent performance characteristics. `std::list` therefore has to maintain a counter, which changes its layout, and `splice` of a range goes from constant to linear time. libstdc++'s `std::list` changed with the C++11 ABI for this reason too.

¶2 Several container requirements are relaxed, so C++03 code meant to work generically across containers may need adjusting: `forward_list` has no `size()`, so use `empty()` to test for emptiness; an `array` is not empty after construction; `swap()` on an `array` is not constant time.

¶3 The requirements each container member function places on the element type are spelled out individually; for example, only functions like `resize(n)` require the element to be default-constructible. An explicit instantiation `template class std::vector<NoDefault>;` instantiates all members and may fail to compile if the element type has no default constructor.

¶4 The following member functions used to return `void` and now return an iterator ([[sequence.reqmts]], [[associative.reqmts]]): `erase(iter)` and `erase(begin, end)` of `set`, `multiset`, `map` and `multimap`; `insert(pos, num, val)` and `insert(pos, beg, end)` of `vector`, `deque`, `list` and `forward_list`. Code that depends on the return type, such as taking a member function pointer to these functions, fails to compile.

¶5 The iterator parameters of the following member functions change from `iterator` to `const_iterator`: `insert(iter, val)` of the sequence and associative containers, `insert(pos, beg, end)` of the sequence containers, `erase(begin, end)` of the associative containers, and all forms of `list::splice` and `list::merge`. The insertion position is only used for locating, so a mutable iterator is not needed. Direct calls are unaffected; code that takes member function pointers may fail to compile.

¶6 The fill value of `resize` in `vector`, `deque` and `list` changes from pass-by-value to pass-by-reference, and a single-argument overload `resize(n)` is added, to work with move semantics. Code that takes a member function pointer to `resize` may fail to compile.

### Algorithms use moves {#diff.cpp03.algorithms}

```cpp run ok
#include <algorithm>
#include <cstdio>
#include <string>
#include <vector>
int main() {
  std::vector<std::string> v;
  v.push_back("a string too long for SSO, #1");
  v.push_back("x");
  v.push_back("a string too long for SSO, #2");
  (void)std::remove(v.begin(), v.end(),
                    std::string("x"));
  for (std::size_t i = 0; i != v.size(); ++i)
    std::printf("[%s]\n", v[i].c_str());
}
```

¶1 Algorithms move instead of copying ([[algorithms.general]]). Objects that were moved from or left at the tail were already in a valid but unspecified state; now they may be in a different valid but unspecified state. In the example above, with libc++ the tail element is a copy of `#2` in C++03 mode and an empty moved-from string in C++11 mode. Code that reads the tail elements after `remove` was already relying on unspecified values.

### Representation of complex numbers {#diff.cpp03.numerics}

¶1 The representation of `complex<float>`, `complex<double>` and `complex<long double>` is specified as a two-element array holding the real part and then the imaginary part, compatible with C99's `_Complex` ([[complex.numbers]]). Code that relies on an implementation-specific binary representation may no longer be compatible. Mainstream implementations already used this layout.

### `num_get` recognizes hexadecimal floating-point {#diff.cpp03.locale}

¶1 The `num_get` facet recognizes the hexadecimal format when parsing floating-point numbers ([[facet.num.get.virtuals]]). In C++03, reading a `double` from `"0x1p3"` stopped at the `x` and gave 0; now it may give 8. libc++ gives 8 in both modes.

### iostreams {#diff.cpp03.input.output}

```cpp error
#include <iostream>
bool ok() { return std::cin; }  // error
bool e = std::cin == false;     // error
```

¶1 The boolean conversion of streams and sentries changes from C++03's `operator void*()` to `explicit operator bool()` ([[istream.sentry]], [[ostream.sentry]], [[iostate.flags]]). Code that relies on the implicit conversion fails to compile; the annex lists five cases: passing a stream to a function taking `bool`; comparing with `true` or `false` using `==`; returning a stream from a function returning `bool`; assigning a stream to a `bool` member via aggregate initialization; and initializing a `const bool&` that would bind to a temporary with a stream.

`if (std::cin)`, `while (in >> x)` and `!std::cin` are contextual conversions to `bool` and are unaffected. The code above passes in Clang's C++03 mode, and both lines are errors in C++11. Rewrite as `return !std::cin.fail();` or `static_cast<bool>(std::cin)`.

¶2 `std::ios_base::failure` no longer derives directly from `std::exception` but from `std::system_error`, which derives from `std::runtime_error` ([[ios.failure]]). This lets it carry a more detailed error code. Now `catch (std::runtime_error&)` also catches it, and code relying on the original inheritance may behave differently.

```cpp
#include <iostream>
int main() {
  int flag = std::ios_base::hex;
  std::cout.setf(flag);   // may be ill-formed
}
```

¶3 The flag types of `ios_base`, `fmtflags`, `iostate`, `openmode` and `seekdir`, are bitmask types, with each value defined as a `constexpr static` member ([[ios.base]]). Code that assumes they are integers or `std::bitset` may fail to compile. The example above compiles with libc++, because libc++'s `fmtflags` is `unsigned int`; with a library that implements `fmtflags` as an enumeration (such as libstdc++) it is an error. Give the variable type `std::ios_base::fmtflags` instead.

## Summary

| Entry | Result | Clang 23 behavior |
|---|---|---|
| macros named `u8` and other prefixes | behavior changes silently | new rule |
| `"hello"_x` | ill-formed | new rule |
| types of integer literals | type changes | new rule |
| `0*N` no longer a null pointer constant | a different overload called | new rule in the old mode too |
| `typeid`, `?:` and xvalues | behavior changes silently | new rule |
| `new int && false` | ill-formed | new rule |
| `auto int x;` | ill-formed | warning only |
| narrowing | ill-formed | new rule |
| linkage in unnamed namespaces | IFNDR | same behavior as the old rule |
| implicitly deleted special members | ill-formed | new rule |
| destructors implicitly `noexcept` | terminate on throw | new rule, with a warning |
| `export template` | ill-formed | warning only before C++20 |
| `>>` | ill-formed | new rule |
| dependent calls finding internal-linkage functions | a different overload called | new rule in the old mode too |
| `explicit operator bool` for streams | ill-formed | new rule |
| type of `fmtflags` | possibly ill-formed | libc++ unaffected |

<details class="fine" markdown="1"><summary>Remaining wording</summary>

¶1 [diff.cpp03.general] says that this subclause lists the differences between C++ and ISO C++ 2003 by the chapters of this document, in addition to the differences listed in the preceding subclauses (C.1 to C.6).

</details>
