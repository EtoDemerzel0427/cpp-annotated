---
title: The new expression
summary: How a new-expression allocates storage and initializes an object; the allocated type and the result type, array bounds and bad_array_new_length, lookup of and arguments to the allocation function, array allocation overhead, which deallocation function is called when initialization throws, and when the compiler may skip the allocation.
updated: 2026-10-19
---

!!! tldr
    - `new T(args)` has two steps: first the allocation function `operator new` is called to obtain storage, then the object is initialized in it. Allocation happens before the arguments are evaluated; if construction throws, the *new-expression* calls the corresponding deallocation function to return the memory.
    - `new T` performs default-initialization, so the value of an `int` or a simple struct is indeterminate; for zero, write `new T()` or `new T{}`.
    - In an array new only the first dimension may be a run-time value. A negative or too-large length at run time should throw `std::bad_array_new_length`; Clang actually throws `std::bad_alloc`.
    - For class types, `operator new` is first looked up in class scope, and finding any declaration hides the global version; `::new` looks only at global scope.
    - The compiler may omit or merge calls to the replaceable global `operator new`, and during constant evaluation it always omits them; this is what makes `new` usable in `constexpr`.

`new T(args)` looks like a single call, but actually does two things: it calls an **allocation function** (named `operator new` or `operator new[]`, [[g:allocation-function]]) to obtain raw storage, and then initializes an object in that storage. The matching **deallocation function** is named `operator delete` or `operator delete[]`.

The standard library provides global versions ([[new.delete]]), which a program may replace; classes can also have their own versions ([[class.free]]). The requirements on allocation and deallocation functions themselves are in [[basic.stc.dynamic]]; the `delete` expression used to release objects is covered in [[expr.delete]].

## Two steps: allocation and initialization

```cpp run ok
#include <cstdio>
#include <new>

struct W {
  explicit W(int) { std::puts("  W ctor"); }
  static void* operator new(std::size_t n) {
    std::puts("  allocate");
    return ::operator new(n);
  }
  static void operator delete(void* p) {
    std::puts("  deallocate");
    ::operator delete(p);
  }
};
int arg() { std::puts("  evaluate initializer"); return 1; }

int main() {
  delete new W(arg());
}
```

The output order is always allocate, evaluate initializer, W ctor, deallocate. ¶12 specifies that a *new-expression* obtains storage by calling an allocation function: `operator new` when the allocated type isn't an array, `operator new[]` when it is.

¶25 specifies two sequencing relations: the call to the allocation function is sequenced before the evaluation of the expressions in the *new-initializer*; the initialization of the object is sequenced before the value computation of the whole expression. The first was added in C++17 ([[P0145R3]]); before that, whether `new T(f())` allocated first or called `f()` first was unspecified. It also means that even if evaluating the initializer throws, the storage has already been allocated, and ¶27 is responsible for returning it (see below).

### new T, new T() and new T{} (¶24)

¶24 If the *new-initializer* is omitted, the object is **default-initialized** ([[g:default-initialization]]); otherwise the initializer is interpreted according to the rules for direct-initialization ([[dcl.init]]). This produces a common difference:

| Form | Kind of initialization | `struct Pt { int x, y; }` | `int` | Class with a user-provided default constructor |
|---|---|---|---|---|
| `new T` | default-initialization | members indeterminate | indeterminate | calls the default constructor |
| `new T()` | value-initialization | zero-initialized | 0 | calls the default constructor, without zeroing first |
| `new T{}` | list-initialization | members are 0 | 0 | calls the default constructor |

```cpp run ok
#include <cstdio>
struct Pt { int x, y; };
int main() {
  Pt* p1 = new Pt;         // x and y are indeterminate; reading them is UB
  Pt* p2 = new Pt();       // value-initialization: x = y = 0
  Pt* p3 = new Pt{};       // aggregate initialization: x = y = 0
  int* i1 = new int[4];    // 4 indeterminate values
  int* i2 = new int[4]();  // 4 zeros
  std::printf("%d %d %d %d %d\n", p2->x, p2->y, p3->x, p3->y, i2[3]);
  delete p1; delete p2; delete p3; delete[] i1; delete[] i2;
}
```

C++26 made reading an uninitialized automatic variable erroneous behavior ([[basic.indet]]), but this applies only to automatic storage duration. An object with dynamic storage duration obtained by `new int` still has an indeterminate value, and reading it is still UB.

## The allocated type and the result (¶1–¶2, ¶10–¶11)

¶1 The type of the object a *new-expression* creates is called the **allocated type** ([[g:allocated-type]]). It must be a complete object type, and cannot be an abstract class or an array of an abstract class. References aren't objects, so you can't `new` a reference (Note 1). The type may be cv-qualified: `new const int(5)` creates a `const int` object (Note 2).

```cpp error
struct Abs { virtual void f() = 0; };
struct Inc;
void g(int n) {
  auto a = new int&(n);   // error: a reference isn't an object
  auto b = new Abs;       // error: abstract class
  auto c = new Abs[2];    // error: array of abstract class
  auto d = new Inc;       // error: incomplete type
  auto e = new void;      // error: void is an incomplete type
}
```

¶10 The objects created have dynamic storage duration ([[basic.stc.dynamic]]); their lifetime isn't restricted to the scope in which they are created.

¶11 The result is a prvalue. If the allocated type is an array of `T`, the result type is `T*`, pointing to the first element; otherwise the result is a pointer to the allocated type. So `new int` and `new int[10]` both have type `int*`, and `new int[i][10]` has type `int (*)[10]` (Note 7).

```cpp ok
#include <type_traits>
auto p1 = new const int(5);
static_assert(std::is_same_v<decltype(p1), const int*>);   // cv-qualification is kept
auto p2 = new int*[3];                                     // 3 int*, the result is int**
static_assert(std::is_same_v<decltype(p2), int**>);
```

!!! pitfall "An array new hidden by a typedef"
    ```cpp
    using Buf = char[64];
    char* p = new Buf;    // this is an array new
    delete p;             // UB: must use delete[]
    ```
    ¶11 makes clear that a type name denoting an array type also counts as an array. If the allocated type is an array, `operator new[]` is called, and it must be paired with `delete[]`, regardless of how it was written ([[expr.delete#2]]).

### auto and class template argument deduction (¶2)

¶2 When the type contains `auto`, `decltype(auto)` or a class template name with its arguments omitted, the allocated type is deduced as for the invented declaration `T x init;`, where `init` is the *new-initializer*.

<div class="compare" markdown="1">

```cpp ok
template<class T>
struct A { A(T, T) {} };
auto x = new auto('a');  // char*
auto y = new A{1, 2};    // A<int>*
auto w = new auto{42};   // int*
```

```cpp error
auto a = new auto;
// error: no initializer
auto b = new auto(1, 2);
// error: auto x(1, 2); can't be deduced
auto c = new auto{1, 2};
// error: auto x{1, 2}; is ill-formed
```

</div>

### Two grammar traps (¶3–¶5)

¶3 The type part (*new-type-id*) takes the longest possible sequence of declarators, so `new int * i` is parsed as `(new int*) i`, a syntax error, and not as `(new int) * i`.

¶4 is a note: `new int(*[10])()` is parsed as `(new int)(*[10])()`, treating `(*[10])` as the initializer of the `int`, which is ill-formed. To allocate a compound type such as an array of function pointers, put the whole type in parentheses: `new (int (*[10])())`.

¶5 An attribute after an array declarator appertains to the corresponding array type.

## Array new (¶6–¶9, ¶26)

### Only the first dimension may be a variable (¶6)

¶6 The first dimension is an ordinary expression and may be a run-time value, or zero; every subsequent dimension must be a constant expression of type `std::size_t` with a value greater than zero.

| `int n = 42;` | Result |
|---|---|
| `new float[n][5]` | OK, result type `float(*)[5]` |
| `new float[5][n]` | ill-formed: the second dimension isn't a constant |
| `new float[0]` | OK: an array of zero elements |
| `new float[n][0]` | ill-formed: the second dimension must be greater than zero |

The result is a pointer to the first element, and the type of the first element (here `float[5]`) must be completely known at compile time for pointer arithmetic to make sense. C++ has no variable-length array types like C99.

Clang 23 gives the warning `zero size arrays are an extension` for `new float[n][0]` only under `-pedantic`. A warning counts as a diagnostic, so this conforms, but in the default configuration the code compiles as an extension.

### Unknown bound (¶7) {{c++20}}

¶7 When the type is an array of unknown bound, an initializer is required, and the number of elements is determined by the initializer. This rule comes from C++20's [[P1009R2]] and applies to earlier standards as a defect report.

<div class="compare" markdown="1">

```cpp ok
auto a = new int[]{1, 2, 3};   // 3 elements
auto b = new char[]("hello");  // 6 elements
auto c = new int[](1, 2);      // 2 elements
```

```cpp error
auto a = new int[];
// error: an initializer is required
```

</div>

### Invalid lengths (¶8)

¶8 The first dimension expression is implicitly converted to `std::size_t`. Its value is **erroneous** in these cases:

- ¶8.1 it is negative before the conversion;
- ¶8.2 the expression is of class type and the value obtained from the conversion function is negative before conversion to `size_t` (footnote 53: after conversion to `size_t` a negative value can no longer be seen);
- ¶8.3 the total size of the object would exceed the implementation-defined limit, for example when `n * sizeof(T)` overflows;
- ¶8.4 the initializer provides more elements than the array has (a string literal counts its terminating `'\0'`).

If the value is erroneous and the expression is a constant expression, the program is ill-formed (¶8.5). Otherwise the allocation function isn't called (¶8.6): if the allocation function that would have been called is non-throwing (like the `std::nothrow` version), the result is a null pointer; otherwise an exception is thrown that would match a handler of type `std::bad_array_new_length`.

```cpp error
auto a = new int[-1];          // error: constant and negative
auto b = new int[2]{1, 2, 3};  // error: more initializers than elements
```

```cpp run ok
#include <new>
#include <cstdio>
int main(int argc, char**) {
  int n = -argc;                          // -1 at run time
  try {
    int* p = new int[n];
    delete[] p;
  } catch (const std::bad_array_new_length&) {
    std::puts("bad_array_new_length");    // the standard requires this path
  } catch (const std::bad_alloc&) {
    std::puts("bad_alloc");               // Clang 23 actually takes this path
  }
  int* q = new (std::nothrow) int[n];     // non-throwing version: the result is null
  std::puts(q ? "non-null" : "null");
}
```

!!! warning "Clang's deviation"
    In our tests Clang 23 replaces an erroneous size with `SIZE_MAX` and calls `operator new[]` as usual, so it throws an ordinary `std::bad_alloc`, and code that only catches `bad_array_new_length` misses it. This also violates the requirement not to call the allocation function: a user-replaced `operator new[]` receives a request for `SIZE_MAX`. The case of too many initializers (¶8.4) behaves the same way. With `-fsanitize=address`, ASan reports `requested allocation size ... exceeds maximum supported size` directly and terminates the program. GCC implements ¶8.6 by calling the Itanium ABI runtime function `__cxa_throw_bad_array_new_length`.

When the length is 0, the allocation function is called as usual and allocates an array with no elements.

### Elements not covered by the initializer (¶9)

¶9 When the length isn't a constant but an initializer list is given, the compiler doesn't know whether the list fills the array, so it checks whether initializing a hypothetical element would be valid: for a braced list, the hypothetical element is copy-initialized from `{}`; for a parenthesized list, it is value-initialized.

```cpp error
struct E { explicit E(); E(int); };
struct NoDef { NoDef(int); };
void f(int n) {
  auto a = new E[n]{1, 2};       // error: remaining elements are copy-initialized from {}, can't use the explicit constructor
  auto b = new NoDef[n](1, 2);   // error: remaining elements are value-initialized, NoDef has no default constructor
  auto c = new NoDef[2]{1, 2};   // OK: the length is a constant and is exactly filled
}
```

### Array new needs the destructor (¶26)

¶26 When an array of objects of class type is created, the destructor is **potentially invoked** ([[g:potentially-invoked]]). If constructing the k-th element throws, the elements already constructed must be destroyed in reverse order, so even if you never `delete[]`, `new T[n]` requires the destructor to be accessible and not deleted.

```cpp error
struct P { private: ~P() = default; public: P() = default; };
P* a = new P;      // OK: a single object doesn't need the destructor
P* b = new P[2];   // error: the destructor is private
```

## Which allocation function is called (¶13, ¶17, ¶19–¶21)

### Class scope first (¶13)

¶13 If the allocated type is a class type `T` (or an array of one) and the expression doesn't begin with `::`, the allocation function's name is looked up in the scope of `T` first (including base classes). If nothing is found, or if `::new` was written, it is looked up in the global scope.

This is name lookup, not a fallback after overload resolution fails: as soon as there is any `operator new` in class scope, the global version is hidden.

<div class="compare" markdown="1">

```cpp ok
#include <cstddef>
struct A {
  static void* operator new(
      std::size_t, int);
};
A* p = new (1) A;   // OK
A* q = ::new A;     // OK: global lookup only
```

```cpp error
#include <cstddef>
struct A {
  static void* operator new(
      std::size_t, int);
};
A* p = new A;
// error: the global version is hidden
```

</div>

So a class that declares only a placement version usually also needs to declare the ordinary version, or bring in the global version with `using` ([[class.free]]).

### How the arguments are assembled (¶19–¶21)

¶19 A *new-expression* can pass extra arguments to the allocation function with the form `new (args...) T`; such an expression is called a **placement new-expression** ([[g:placement-new-expression]]). In the standard, placement refers to any such extra arguments, not only `new (ptr) T`; `new (std::nothrow) T` is also a placement new.

¶20 Overload resolution is performed on the assembled call:

1. The first argument is the number of bytes requested, of type `std::size_t`;
2. if the type's alignment requirement exceeds `__STDCPP_DEFAULT_NEW_ALIGNMENT__` (called new-extended alignment, [[basic.align]]), the next argument is the alignment, of type `std::align_val_t`;
3. the placement arguments follow in order.

If no matching function is found, there is a second attempt: if the original call had the alignment argument, it is removed (¶20.1); if it didn't, it is added (¶20.2). That way a class that provides only `operator new(size_t)` can still `new` an over-aligned type (just without the alignment guarantee), and a class that provides only the aligned version can also `new` ordinary types.

The example in ¶21 writes out the four cases as calls:

| Expression | Call for an ordinary type | Call with new-extended alignment |
|---|---|---|
| `new T` | `operator new(sizeof(T))` | `operator new(sizeof(T), std::align_val_t(alignof(T)))` |
| `new(2,f) T` | `operator new(sizeof(T), 2, f)` | `operator new(sizeof(T), std::align_val_t(alignof(T)), 2, f)` |
| `new T[5]` | `operator new[](sizeof(T) * 5 + x)` | `operator new[](sizeof(T) * 5 + x, std::align_val_t(alignof(T)))` |
| `new(2,f) T[5]` | `operator new[](sizeof(T) * 5 + x, 2, f)` | `operator new[](sizeof(T) * 5 + x, std::align_val_t(alignof(T)), 2, f)` |

(If no match is found, the other column is tried.)

```cpp run ok
#include <cstdio>
#include <cstdlib>
#include <new>

struct alignas(64) Line { char c[64]; };   // 64 exceeds the default new alignment

void* operator new(std::size_t n, std::align_val_t a) {
  std::printf("operator new(%zu, align_val_t{%zu})\n", n, static_cast<std::size_t>(a));
  if (void* p = std::aligned_alloc(static_cast<std::size_t>(a), n)) return p;
  throw std::bad_alloc{};
}
void operator delete(void* p, std::align_val_t) noexcept { std::free(p); }

int main() {
  std::printf("default new alignment = %zu\n", __STDCPP_DEFAULT_NEW_ALIGNMENT__);
  Line* l = new Line;     // the second argument is std::align_val_t(64)
  delete l;               // delete also prefers the version taking align_val_t
}
```

In our tests (macOS arm64) the output is `default new alignment = 16` and `operator new(64, align_val_t{64})`. Before C++17's [[P0035R4]], `new` ignored `alignas` entirely and just called `operator new(64)`, whose storage was only guaranteed fundamental alignment, so over-aligned SIMD types often went wrong.

### Array allocation overhead (¶17, ¶21)

The *x* in the table above is the **array allocation overhead**: a non-negative unspecified value by which the result of an array new is offset from the value returned by `operator new[]`. It may appear in every array new, including those that call a user placement allocation function; the only exception is the standard library's `operator new[](std::size_t, void*)`. The overhead may differ from one call to the next.

¶17 The first argument must be no less than the size of the object; it may be larger only if the object is an array and the allocation function isn't a non-allocating form like `operator new[](size_t, void*)`, and the excess is *x*. For arrays of `char`, `unsigned char` and `std::byte`, *x* must also be an integral multiple of an alignment: the strictest fundamental alignment of any object type whose size is no greater than the size of the array. Note 9 explains why: allocating `new char[sizeof(T)]` and then placing a `T` in it is a common idiom, and the overhead must not break the alignment of that storage.

!!! impl "Array cookies"
    In practice *x* has almost only one use: recording the number of elements in front of the array, called a **cookie**, so that `delete[] p` knows how many elements to destroy.

    - Itanium C++ ABI (x86-64 Linux/macOS, AArch64 Linux): a cookie is added only if the element type has a non-trivial destructor, or if the selected `operator delete[]` needs a `size_t` parameter. The cookie size is `max(sizeof(size_t), alignof(T))`, and the element count is stored immediately before the first element. For `struct NT { int x; ~NT(); }` on x86-64, `new NT[5]` requests 5 × 4 + 8 = 28 bytes and the result pointer is offset by 8.
    - ARM C++ ABI (32-bit ARM, and Apple arm64): the cookie is two `size_t`s, storing the element size and the element count in that order.
    - Element types with trivial destructors usually have no cookie; `new int[4]` requests exactly 16 bytes.
    - MSVC likewise records the element count for element types with non-trivial destructors.
    - `operator new[](size_t, void*)` adds no cookie; a user-defined placement `operator new[]` might, in which case `new (buf) T[n]` uses more bytes than `n * sizeof(T)`.

    This is the practical reason `new[]` must be paired with `delete[]`: `delete` doesn't read the cookie, so the pointer passed to `operator delete` is 8 or 16 bytes off the real allocation address; conversely, `delete[]` on a single object reads a cookie that doesn't exist.

```cpp run impl
#include <cstdio>
#include <cstdlib>
#include <new>

struct Trivial { int x; };
struct NonTrivial { int x; ~NonTrivial() {} };

void* last;
void* operator new[](std::size_t n) {
  std::printf("operator new[](%zu)\n", n);
  return last = std::malloc(n);
}
void operator delete[](void* p) noexcept { std::free(p); }
void operator delete[](void* p, std::size_t n) noexcept {
  std::printf("operator delete[](p, %zu)\n", n);
  std::free(p);
}

int main() {
  auto* a = new Trivial[4];
  std::printf("  offset = %td\n", (char*)a - (char*)last);
  delete[] a;
  auto* b = new NonTrivial[5];
  std::printf("  offset = %td\n", (char*)b - (char*)last);
  delete[] b;
}
```

In our tests (macOS arm64) the output is `operator new[](16)`, `offset = 0`, `operator new[](36)`, `offset = 16`, `operator delete[](p, 36)`. On x86-64 Linux the second allocation is 28 bytes with an offset of 8. The first `delete[]` calls the unsized version and the second calls the sized version; the selection rules are in [[expr.delete#9]].

## Allocation failure (¶22–¶23)

¶22 Note 10: an allocation function without `noexcept` indicates failure by throwing `std::bad_alloc`; a `noexcept` allocation function indicates failure by returning a null pointer.

If the allocation function returns a null pointer, no initialization is performed and no deallocation function is called; the value of the *new-expression* is a null pointer. So when `new (std::nothrow) T(args)` fails, `T`'s constructor is never called.

The exception is the non-allocating form `operator new(size_t, void*)` ([[new.delete.placement]]): if it returns a null pointer, that is, if you write `new (nullptr) T`, the behavior is undefined. Making this case UB on its own means the compiler doesn't have to check whether `p` is null before every `new (p) T`.

```cpp ub
#include <new>
int main() {
  void* p = nullptr;
  int* q = ::new (p) int(1);   // UB: non-allocating placement new yields a null pointer
  (void)q;
}
```

¶23 Note 11: when a non-null pointer is returned, it points to storage of sufficient size and suitable alignment. For arrays, the address of the object isn't necessarily the address of that storage, since a cookie may come first.

## Returning memory when initialization fails (¶27–¶32)

```cpp run ok
#include <cstdio>
#include <new>

struct Arena { alignas(16) char buf[256]; std::size_t used = 0; };

struct Widget {
  int v;
  explicit Widget(int v) : v(v) { if (v < 0) throw v; }

  static void* operator new(std::size_t n) {
    std::printf("  Widget::operator new(%zu)\n", n);
    return ::operator new(n);
  }
  static void operator delete(void* p) noexcept {
    std::puts("  Widget::operator delete(void*)");
    ::operator delete(p);
  }
  static void* operator new(std::size_t n, Arena& a) {
    std::printf("  Widget::operator new(%zu, Arena&)\n", n);
    void* p = a.buf + a.used; a.used += n; return p;
  }
  static void operator delete(void*, Arena&) noexcept {   // pairs with the placement version above
    std::puts("  Widget::operator delete(void*, Arena&)");
  }
};

int main() {
  std::puts("new Widget(-1):");
  try { new Widget(-1); } catch (int) { std::puts("  caught"); }

  Arena a;
  std::puts("new (a) Widget(-2):");
  try { new (a) Widget(-2); } catch (int) { std::puts("  caught"); }
}
```

Both constructions throw. The first calls the ordinary `operator delete(void*)`, the second calls `operator delete(void*, Arena&)`, which pairs with the placement version, and only then is the exception caught by `catch`.

¶27 If any part of the initialization (including evaluating the initializer and calling the constructor) terminates by throwing an exception and a matching deallocation function can be found, it is used to return the storage, and then the exception continues to propagate. If no unambiguous matching function is found, the exception still propagates, but the storage isn't returned. Note 13 points out that this is appropriate for forms like `new (buf) T` that don't really allocate memory, and for other forms it most likely means a memory leak.

¶28 The deallocation function is looked up the same way as the allocation function: for class types, class scope first; `::new` looks only at global scope.

¶29 For an ordinary (non-placement) allocation function, the deallocation function is selected by the rules for `delete` expressions ([[expr.delete]]); for a placement allocation function, it is selected by ¶30. Either way, the selected deallocation function must not be deleted and must be accessible at the point of the *new-expression*.

### Which deallocation function pairs with a placement allocation function (¶30–¶31)

¶30 Among the candidate deallocation functions, after removing the first parameter (the `size_t` of the allocation function, the `void*` of the deallocation function), the parameter-type-list must be identical to that of the allocation function. Function templates are first replaced by specializations through template argument deduction, and candidates whose constraints aren't satisfied are removed. If exactly one remains, it is selected; otherwise no function is selected. A deallocation function with one more parameter than the allocation function never matches, even if that parameter has a default argument (Note 14).

If the selected function is a **usual deallocation function** ([[g:usual-deallocation-function]]), the program is ill-formed. Example 7 shows why:

```cpp error
#include <cstddef>
struct S {
  static void* operator new(std::size_t, std::size_t);   // placement allocation function
  static void operator delete(void*, std::size_t);       // usual sized deallocation function
};
S* p = new (0) S;   // error
```

After removing the first parameter both are `(size_t)`, so they match formally. But the second parameter of the deallocation function means the size of the object, while the placement new would pass it the argument `0`, which means something completely different. The standard chooses to make this an error rather than silently pass the wrong argument.

Examples 8–10 deal with templates and constraints; this part is new wording after C++23. In Example 8 the only candidate is the template `template<int = 0> void operator delete(void*, A&)`, which after deduction matches the allocation function and is selected. In Example 9 both the template and the non-template match, leaving two candidates, so no function is selected; the program is still well-formed, but the storage isn't returned if the constructor throws. In Example 10 `requires (I > 0)` excludes the template, and the remaining non-template is selected.

¶32 The first argument to the deallocation function is the pointer returned by the allocation function; a placement deallocation function also receives the same placement arguments as the allocation.

## Omitting and merging allocations (¶14–¶16, ¶18)

¶14 An implementation may omit a call to a replaceable global allocation function, providing the storage itself instead or by extending the allocation of another *new-expression*.

```cpp ok
int f() {
  int* p = new int(42);   // at Clang -O2 the whole function becomes return 42
  int r = *p;
  delete p;
  return r;
}
```

A replaced `operator new` may have side effects such as printing or counting, so before C++14 the as-if rule didn't allow the compiler to remove a redundant `new`/`delete` pair. [[N3664]] explicitly allows these calls to be omitted: even if the user replaces the allocation function, it may never be called. This applies only to replaceable global allocation functions called by a *new-expression*; class-specific `operator new`, explicit `::operator new(n)` calls and placement forms are not covered.

¶16 An implementation may also merge two allocations into one: extend the allocation of `e1` to also provide storage for `e2`. This requires that merging be unobservable; the conditions include that `e1` is sequenced before `e2`, that `e2` is evaluated whenever `e1` obtains storage, that both call the same replaceable global allocation function, that exceptions they throw would first be caught by the same handler, that both pointers are passed to `delete`, and that `e2` is evaluated before `e1` is deleted. In the standard's Example 5, the second allocation can't be merged when it is inside a `try` block, because merging would change which handler catches a failed allocation. ¶18 specifies that the merged size is no greater than the sum of the individual allocations plus any necessary alignment padding.

## new in constant evaluation (¶15) {{c++20}}

¶15 During constant evaluation, calls to replaceable allocation functions are always omitted, and the compiler provides the storage. Since C++20 ([[P0784R7]]), `new` can be used in constant evaluation, but the allocated storage must be released with `delete` within the same constant evaluation; this is called a **transient allocation** ([[g:transient-allocation]]).

<div class="compare" markdown="1">

```cpp ok
constexpr int sum(int n) {
  int* p = new int[n];
  int s = 0;
  for (int i = 0; i < n; ++i)
    s += (p[i] = i);
  delete[] p;   // released within the same evaluation
  return s;
}
static_assert(sum(10) == 45);
```

```cpp error
constexpr int* leak() {
  return new int(1);
}
constexpr int* q = leak();
// error: the allocation escapes the constant evaluation
```

</div>

{{c++26}} Since C++26 ([[P2747R2]]), `operator new(size_t, void*)` is also `constexpr`, and placement new can be used in constant evaluation, provided the pointer points to an object of a suitable type ([[expr.const.core]]). `std::construct_at` no longer needs special handling by the compiler.

```cpp ok
#include <memory>
#include <new>
constexpr int g() {
  std::allocator<int> al;
  int* p = al.allocate(1);
  ::new (static_cast<void*>(p)) int(7);   // C++26: usable in constant evaluation
  int r = *p;
  std::destroy_at(p);
  al.deallocate(p, 1);
  return r;
}
static_assert(g() == 7);
```

## Placement new and const objects

The allocated type can be any complete object type, and the *new-expression* itself doesn't care what was in the target storage before. But [[basic.life#12]] makes it UB to create a new object in the storage of a const complete object with static, thread or automatic storage duration, because the compiler may assume the values of such objects never change, and may even put them in a read-only segment.

<div class="compare" markdown="1">

```cpp ub
#include <new>
struct S { int m; };
const S cs{1};
int main() {
  ::new (const_cast<S*>(&cs)) S{2};
  // UB: const object with static storage duration
}
```

```cpp run ok
#include <new>
struct S { int m; };
int main() {
  const S* p = new const S{1};
  ::new (const_cast<S*>(p)) S{2};
  p = std::launder(p);
  int r = p->m;
  delete p;
  return r == 2 ? 0 : 1;
}
```

</div>

const objects with dynamic storage duration aren't subject to this restriction. But the old object is a const complete object and can't be transparently replaced ([[basic.life#9]]), so `std::launder` is needed before the new object can be accessed through the old pointer.

## History

!!! history
    - C++98 already had the placement syntax, `std::nothrow` and the array overhead *x*; a negative array length was UB.
    - C++11 added braced initializers and `new auto(x)`, and made negative or too-large array lengths throw the new `std::bad_array_new_length`.
    - C++14's [[N3664]] allowed calls to replaceable global allocation functions to be omitted and merged.
    - C++17's [[P0035R4]] added aligned new; [[P0145R3]] sequenced the allocation before the evaluation of the initializer; `new A{1, 2}` can also use class template argument deduction.
    - C++20's [[P0784R7]] allowed `new` in constant evaluation; [[P1009R2]] allowed new of arrays of unknown bound; parenthesized aggregate initialization made `new int[](1, 2)` valid.
    - C++26's [[P2747R2]] allowed placement new in constant evaluation.

## Common misconceptions

!!! pitfall "Thinking `new T` zeroes the memory"
    `new int`, `new Pt` (an aggregate) and `new int[n]` all only default-initialize, so the values are indeterminate. When you need zeros, write `new T()`, `new T{}` or `new int[n]()`.

!!! pitfall "Thinking a replaced `operator new` is always called"
    ¶14 allows calls to replaceable global allocation functions to be omitted. A test that counts allocations by replacing `operator new` may get a smaller count with optimizations enabled.

!!! pitfall "Thinking `new (buf) T[n]` uses exactly `n * sizeof(T)` bytes"
    The standard library's `operator new[](size_t, void*)` adds no overhead, but a user-defined placement `operator new[]` may. Don't assume the result of an array placement new equals `buf`.

## Questions

!!! question "Question 1"
    With `int n = 0;`, what does `new int[n]` return? Can you dereference the result? Does it need `delete[]`?

<details markdown="1">
<summary>Answer</summary>

The end of ¶8 specifies that a length of 0 calls the allocation function as usual. [[basic.stc.dynamic.allocation]] requires that a successful allocation return a non-null pointer distinct from every other live allocation, even when 0 bytes are requested. A zero-element array has no first element, so the result doesn't point to any object, and dereferencing it is UB; but the allocation is real and must be `delete[]`d, or it leaks.
</details>

!!! question "Question 2"
    In `new (std::nothrow) T(f())`, if the allocation fails and returns null, is `f()` called? If the allocation succeeds and `f()` throws, what happens?

<details markdown="1">
<summary>Answer</summary>

By ¶25, the allocation is sequenced before the evaluation of the initializer. When the allocation fails and returns null, ¶22 says no initialization is performed; `f()` is part of the initialization, so it isn't called.

If the allocation succeeds and `f()` throws, that is the case in ¶27 of initialization terminating by an exception. The `std::nothrow` version is a placement allocation function, so ¶30 finds the standard library's `operator delete(void*, const std::nothrow_t&)`, which is used to return the storage, and then the exception continues to propagate.
</details>

## Summary

| Stage | Paragraphs | Rule |
|---|---|---|
| Type | ¶1–¶2 | complete object type, not abstract, may be cv-qualified; `auto` and class templates are deduced as for `T x init;` |
| Array length | ¶6–¶9 | only the first dimension may be a variable; erroneous length: ill-formed if constant, otherwise throws `bad_array_new_length` or yields a null pointer |
| Result | ¶11 | an array gives a pointer to the first element, otherwise a pointer to the object |
| Lookup | ¶13, ¶28 | class types look in class scope first, hiding the global ones; `::new` looks only at global scope |
| Arguments | ¶17, ¶20–¶21 | size (may include array overhead), possibly `align_val_t`, placement arguments; if nothing matches, retry the other way |
| Omitting and merging | ¶14–¶18 | only replaceable global allocation functions; always omitted in constant evaluation |
| Failure | ¶22 | a null return means no initialization; a null return from the non-allocating form is UB |
| Initialization | ¶24–¶25 | no initializer means default-initialization; allocation is sequenced before evaluating the initializer |
| Cleanup | ¶26–¶32 | when initialization throws, the matching deallocation function is called; placement requires identical parameter lists, and matching a usual deallocation function is ill-formed |
