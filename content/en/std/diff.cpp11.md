---
title: C++ and ISO C++ 2011
summary: "What previously valid code breaks or changes behavior when moving from C++11 to C++14: digit separators changing how macro arguments are split, sized operator delete becoming a usual deallocation function, throw branches of the conditional operator, constexpr member functions no longer implicitly const, aggregates with default member initializers, and the removal of gets."
updated: 2026-10-19
---

!!! tldr
    - C++14 has only 7 incompatibilities, and most of them appear only in deliberately contrived code.
    - The one you are most likely to actually hit: `constexpr` non-static member functions are no longer implicitly `const`, so overloads that relied on the implicit `const` become duplicate declarations.
    - The digit separator `'` changes tokenization, so the same macro invocation can expand differently under the two standards.
    - A class with default member initializers can be an aggregate, so `S b{a};` may use a different conversion function, and the result changes silently.
    - `gets` is removed; `operator delete(void*, std::size_t)` becomes a usual deallocation function, which causes trouble for user-defined placement deallocation functions with the same signature.

[diff.cpp11] lists the incompatibilities of C++14 relative to C++11: previously well-formed code that becomes ill-formed in C++14, or whose meaning changes. Every entry in the standard has the same format: the affected subclause, what changed, why, and the effect on old code.

¶1 This subclause lists differences in addition to those in the subclauses above: to upgrade from C++11 to the current draft you also need to read [[diff.cpp14]] and the subclauses after it. Entries follow the order of the chapters in the main text. All tests on this page use Clang 23.1.3, comparing `-std=c++11` with `-std=c++14`.

## Lexical conventions [diff.cpp11.lex] {#diff.cpp11.lex}

### Digit separators change how macro arguments are split

```cpp run title="digit_sep.cpp" ok
#include <cstdio>
#define M(x, ...) __VA_ARGS__
int x[2] = { M(1'2,3'4, 5) };
// C++11: int x[2] = { 5 };
// C++14: int x[2] = { 3'4, 5 };
int main() { std::printf("%d %d\n", x[0], x[1]); }
```

¶1 C++14 allows single quotes between digits as separators, as in `1'000'000` ([[lex.icon]]). To support this, the numeric token of the preprocessing phase, the **preprocessing number** ([[g:pp-number]]), can contain single quotes ([[lex.ppnumber]]).

In C++11, the `'2,3'` in `1'2,3'4` is a character literal, so the arguments of `M` are `1'2,3'4` and `5`, and it expands to `{ 5 }`. In C++14, `1'2` and `3'4` are two numbers, there are three arguments, and it expands to `{ 3'4, 5 }`. Both results are well-formed, just with different meanings, and the compiler says nothing.

Run on Clang 23, `-std=c++11` prints `5 0` and `-std=c++14` prints `34 5`. Real code almost never looks like this.

## Basics [diff.cpp11.basic] {#diff.cpp11.basic}

### Sized `operator delete` becomes a usual deallocation function

```cpp
void* operator new(std::size_t, std::size_t);         // placement allocation function
void operator delete(void*, std::size_t) noexcept;    // C++11: the matching placement deallocation function
                                                       // C++14: same signature as a usual deallocation function

struct T { T(); };
T* f() { return new (8) T; }   // error: well-formed in C++11
```

¶1 C++14 introduces sized deallocation: on `delete p` the compiler passes the object's size to `operator delete(void*, std::size_t)`, so the allocator does not have to record the size of every block itself ([[basic.stc.dynamic.deallocation]]). This function therefore becomes a **usual deallocation function**, the kind a `delete` expression calls, rather than a placement deallocation function that is called only when construction in a placement `new` fails.

In C++11, the second declaration above is the placement deallocation function matching the placement allocation function in the first. In C++14 it has the same signature as the predefined usual deallocation function. When a constructor throws, a placement `new` expression has to call the matching deallocation function, and if the one found happens to be a usual deallocation function, the program is ill-formed; the class-member version has always had this rule ([[expr.new]]).

Clang 23 reports an error for `new (8) T` under `-std=c++14`, saying that `new` with placement arguments refers to a non-placement `operator delete`. The fix is to give the pair of placement functions a second parameter type that cannot collide, such as a custom tag type.

## Expressions [diff.cpp11.expr] {#diff.cpp11.expr}

### `throw` branches in conditional expressions

```cpp
struct S {
  int x = 1;
  void mf() { x = 2; }
};
int f(bool cond) {
  S s;
  (cond ? s : throw 0).mf();   // C++14: called on s itself; C++11: on a copy of s
  return s.x;
}
// f(true): C++14 returns 2, C++11 returns 1
// sizeof(true ? "" : throw 0): C++14 is sizeof(const char[1]), C++11 is sizeof(const char*)
```

¶1 When one branch of a conditional expression `c ? a : b` is a throw-expression, C++14 says the type and value category of the result are those of the other branch ([[expr.cond]]). C++11 first applied the lvalue-to-rvalue, array-to-pointer and function-to-pointer conversions to the other branch, so the lvalue `s` became a temporary copy and `""` decayed to a pointer. These conversions, especially the temporary produced by the lvalue-to-rvalue conversion, were considered both unnecessary and surprising.

Clang 23 treats this as a defect fix and has the new behavior under `-std=c++11` too: `f(true)` returns 2 and the `sizeof` is 1. Only code that relies on that unnecessary copy is affected, and there is practically none.

## Declarations [diff.cpp11.dcl.dcl] {#diff.cpp11.dcl.dcl}

### `constexpr` member functions are no longer implicitly `const`

<div class="compare" markdown="1">

```cpp error
struct S {
  constexpr const int& f();
  int& f();   // error
};
```

```cpp ok
struct S {
  constexpr const int& f() const;
  int& f();   // OK
};
```

</div>

¶1 In C++11, a `constexpr` non-static member function is implicitly a `const` member function; C++14 drops this implicit rule ([[dcl.constexpr]]). C++14 allows `constexpr` functions to modify objects, so `constexpr` member functions need to be able to modify `*this` and can no longer all be `const`.

The left side declares two different overloads in C++11: one `const` and one non-`const`. In C++14 both are non-`const` member functions differing only in return type, and the program is ill-formed. Writing `const` explicitly on functions that relied on the implicit `const`, as on the right, gives the same meaning under both standards.

Clang 23 already gives a `-Wconstexpr-not-const` warning under `-std=c++11` suggesting adding `const`, and an error under `-std=c++14`.

### A class with default member initializers can be an aggregate

```cpp run title="aggr14.cpp" ok
#include <cstdio>
struct S { int m = 1; };   // an aggregate since C++14
struct X {
  operator int() { std::puts("operator int"); return 5; }
  operator S()   { std::puts("operator S");   return S{}; }
};
int main() {
  X a{};
  S b{a};   // C++14: aggregate initialization, b.m initialized from int(a)
            // C++11: via operator S, then copied
  std::printf("b.m=%d\n", b.m);
}
```

¶2 In C++11, a class with a default member initializer (such as `int m = 1;`) is not an **aggregate**; C++14 removes this restriction ([[dcl.init.aggr]]) so that aggregate initialization can use default member initializers too.

So `S b{a}` changes from copy-initialization (first converting `a` to `S` with `operator S`) to aggregate initialization (initializing the first member `m` from `a`, via `operator int`). Run on Clang 23, `-std=c++11` prints `operator S` and `b.m=1`, and `-std=c++14` prints `operator int` and `b.m=5`. The result changes silently, but providing conversion functions both to a class type and to the type of its first member is rare.

## Library introduction [diff.cpp11.library] {#diff.cpp11.library}

¶1 C++14 adds the header `<shared_mutex>` ([[headers]]). If a project has a header with the same name and includes it with `#include <...>`, it may get the standard library's version.

## Input/output library [diff.cpp11.input.output] {#diff.cpp11.input.output}

¶1 C++14 no longer defines `gets` ([[c.files]]); C11 removed it too. `gets` cannot limit the length of what it reads, so long input overflows the buffer. Use `fgets(buf, sizeof buf, stdin)` (note that it keeps the newline) or `std::getline`. In our tests there is a deprecation warning from the macOS SDK headers under `-std=c++11`, and `std::gets` does not exist under `-std=c++14`.

## Summary

| Entry | Fate of old code | Clang 23 |
|---|---|---|
| digit separators | macro expansion changes | implemented |
| sized `operator delete` | ill-formed | implemented |
| `throw` branches | result changes | implemented, same in C++11 mode |
| `constexpr` member functions no longer implicitly `const` | ill-formed | implemented, warning in C++11 |
| aggregates with default member initializers | result changes | implemented |
| `gets` | ill-formed | removed |
