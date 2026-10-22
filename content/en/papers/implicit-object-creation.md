---
title: Implicit object creation (P0593)
summary: C++20, as a defect fix, specifies that operations like malloc, operator new and memcpy create objects on demand, giving C-style low-level code defined behavior. This page covers the problem it solves, the rejected alternatives, the final wording, and why std::start_lifetime_as was still needed afterwards.
tags: proposal, object model, lifetime, malloc, memcpy, DR, UB
group: Core language
updated: 2026-10-19
---

!!! tldr
    - By the C++17 wording, the memory returned by `malloc` contains no objects at all, so `p->a = 1` is strictly UB; pointer arithmetic on allocated storage, as `std::vector` does, is undefined too. Compilers never exploited this; the problem was in the rules themselves.
    - [[P0593R6]] specifies a set of operations that implicitly create objects: only objects of implicit-lifetime types are created, and which objects are created is determined by how later code uses the storage, provided that gives the program defined behavior.
    - The committee rejected the approach of storage simply being objects, because it would defeat type-based alias analysis; it also did not make type punning legal: the old object's value is not passed on to the new object.
    - The language part went into C++20 as a defect fix; the library function `std::start_lifetime_as` was deferred to C++23 ([[P2590R2]]). It is still needed, because implicit creation only happens in a few operations and does not change what existing pointers point to.
    - No tool reliably checks for this kind of UB: UBSan and ASan can't see it, and Clang's TypeSanitizer checks by access type, which does not match the C++ object model.

## The problem: memory, but no objects

A perfectly ordinary C function, compiled as C++:

```cpp run title="make-x.cpp" ok
#include <cstdio>
#include <cstdlib>

struct X { int a, b; };

X* make_x() {
  X* p = (X*)std::malloc(sizeof(struct X));
  p->a = 1;   // C++17 wording: there is no X object, UB
  p->b = 2;   // since C++20: OK
  return p;
}

int main() {
  X* x = make_x();
  std::printf("%d\n", x->a + x->b);
  std::free(x);
}
```

A C++ **object** is an entity with a type and a lifetime, not just a chunk of bytes (see [[topics/object-model]]). C++17 listed every way to create an object: a definition, a *new-expression*, switching the active member of a union, and creating a temporary. `malloc` is not among them, so `p` does not point to any `X`, and `p->a` accesses an `int` subobject that does not exist.

This is not an isolated case. The motivation section of [[P0593R6]] gives three kinds of code:

1. C idioms like the one above;
2. reading a byte buffer from disk or the network, knowing it contains the representation of some struct, and reading it via `reinterpret_cast<Foo*>(buf)`;
3. implementing a `std::vector`-like container yourself: allocating raw storage with `::operator new`, constructing elements in it one by one, and doing pointer arithmetic with `T*`.

The third is the most surprising. Pointer arithmetic is only defined within an array object ([[expr.add]]), and the storage returned by `::operator new` contains no array object, so `begin() + i` and `end() - begin()` are all undefined. By the letter of the C++17 rules, `std::vector` could not be implemented in standard C++. This gap was first raised as the core language issue [[CWG2325]], and [[P0593R6]] is its resolution.

### Where compilers stand

All of these kinds of code work fine on every implementation. Compiling `make_x` above with Clang 23 at `-O2` under `-std=c++17` and under `-std=c++20` gives byte-for-byte identical assembly: a call to `malloc`, then a single 8-byte store writing both 1 and 2.

The paper's explanation: the compiler cannot see inside `malloc`, so it cannot assume `malloc` created no objects; and creating an object corresponds to no action on the machine. So the code a compiler generates must also be correct in the case where `malloc` happened to create the right objects. The status quo is already like this; the standard just needs to write it down. The difficulty is how to write it without also permitting things that should not be permitted.

## The design space

### Option one: storage is objects

The simplest rule is: wherever something depends on an object existing, that object automatically exists. Bytes are objects, and writing with a different type gives a different object. This roughly matches C's **effective type** rules: memory from `malloc` has no declared type, and it takes on the type of the first write (the two models are compared in [[topics/object-model]]).

The paper rejected this approach because it would weaken **type-based alias analysis** (TBAA): the compiler assumes lvalues of different scalar types do not refer to the same object, which lets it skip reloads.

```cpp run title="tbaa.cpp" ok
int f(int* i, float* x) {
  *i = 1;
  *x = 2.0f;   // cannot modify the int object *i refers to
  return *i;   // the compiler returns 1 directly
}
```

Clang 23 at `-O2` compiles `return *i` to the constant 1; only with `-fno-strict-aliasing` does it reload from memory. The basis for this optimization is [[basic.lval#11]]: an `int` object cannot be accessed through a `float` lvalue. If `*x = 2.0f` could conjure up a `float` object in place, that basis would no longer hold. The paper also points out that, for the conflict between effective types and TBAA (C defect report 236), the C committee adopted at least four mutually incompatible interpretations over the years, without a good solution in nearly twenty years, so this path was not taken.

This choice leaves a visible difference: a memory pool idiom that C allows is still UB in C++.

```cpp run title="reuse.cpp" ub
#include <cstdio>
#include <cstdlib>

int main() {
  void* m = std::malloc(8);
  *static_cast<int*>(m) = 1;      // malloc implicitly creates an int
  *static_cast<float*>(m) = 2.0f; // UB: there is no float object here
  std::printf("%g\n", *static_cast<float*>(m));
  std::free(m);
}
```

`malloc` can only create a set of objects at the moment it is called, and an `int` and a `float` cannot occupy the same storage at the same time, so no set of objects makes both writes defined. In C, the second write merely changes the effective type. To reuse storage in C++, a new object must be created explicitly before the second write, for example with `::new (m) float(2.0f)`. Whether C's effective type rules can be fully expressed with implicit creation is still an open core issue ([[CWG3042]]).

### Option two: only allocation functions foresee the future

The second idea gives only `malloc` and `operator new` a privilege: they know how the storage will be used in the future and create exactly the objects needed. The paper considered this insufficient. Memory pools reuse the same allocation for different objects over and over; that reuse happens in C++ code the compiler can see, and needs the same capability.

So the paper calls for an explicit marker saying that objects are created from this point. `malloc` is a ready-made marker; reused storage needs another. Earlier revisions proposed a library function `std::bless(void* p, size_t n)`. R5 removed it following review by the library design group, on the grounds that `new (p) std::byte[n]` already serves the same purpose: when the lifetime of a byte array begins, objects are implicitly created in it. This relies on [[CWG2382]], which specifies that a non-allocating placement new creating an array may have no overhead, so `new (p) std::byte[n]` occupies exactly `[p, p + n)`. The typed version was renamed `start_lifetime_as`, covered later.

### Option three: member access creates

R2 of the paper once proposed that a member access on a union is itself enough to implicitly create an object. After an implementer objected, R3 dropped it. `reinterpret_cast` was never under consideration: pointer conversions do not create objects.

### Which types can be created implicitly

Creating an object implicitly presupposes that it requires running no code. On that basis the paper sets two conditions: creating an object of the type runs no code, and destroying it runs no code either. A type that maintains an invariant should not appear out of thin air.

These two conditions concern only the object itself, not its subobjects. Creating and destroying an array object itself runs no code (its elements are another matter), and aggregate classes can be viewed the same way. The final **implicit-lifetime types** ([[g:implicit-lifetime-type|implicit-lifetime type]], [[basic.types.general#7]]) are scalar types, implicit-lifetime classes, array types, and cv-qualified versions of these. An **implicit-lifetime class** ([[g:implicit-lifetime-class|implicit-lifetime class]], [[class.prop#8]]) is:

- an aggregate whose destructor is not user-provided; or
- a class with at least one trivial eligible constructor (default, copy and move all count) and a trivial, non-deleted destructor.

Requiring just one trivial constructor, rather than requiring both default construction and copy construction to be trivial, was a relaxation made in R2 at a study group's suggestion: types with only a trivial default constructor are suitable for constructing by member-wise assignment, and types with only a trivial copy constructor are suitable for copying in from an on-disk representation. Aggregates were added in R4 at the evolution group's suggestion. The destructor restriction in the first condition was added later by [[CWG2605]]. C++23's `std::is_implicit_lifetime` ([[P2674R1]]) lets you query it directly:

```cpp run title="implicit-lifetime.cpp" ok
#include <memory>
#include <string>
#include <type_traits>

struct Pod { int a; double b; };
struct Agg { int n; std::unique_ptr<int> p; };
struct AggDtor { int n; ~AggDtor() {} };
struct Ctor { int x; Ctor() = default; Ctor(int); };
struct Rule0 { std::string s; Rule0(); };

static_assert(std::is_implicit_lifetime_v<Pod>);
static_assert(std::is_implicit_lifetime_v<Agg>);
static_assert(!std::is_implicit_lifetime_v<AggDtor>);
static_assert(std::is_implicit_lifetime_v<Ctor>);
static_assert(!std::is_implicit_lifetime_v<Rule0>);
static_assert(std::is_implicit_lifetime_v<std::string[4]>);
static_assert(!std::is_implicit_lifetime_v<std::string>);

int main() {}
```

`Agg` contains a `unique_ptr` and is still an implicit-lifetime type, because it is an aggregate whose own destructor is not user-provided. But implicitly creating an `Agg` does not begin the lifetime of `p` ([[intro.object#13]] Note 4); `p` still has to be constructed with placement new. `std::string[4]` is similar: the array object can appear implicitly, but the four `string` elements do not. `AggDtor` is the case excluded by [[CWG2605]], which Clang 23 already implements.

## The final rules

### Creation on demand

[[intro.object#13]] is the core of the whole proposal:

!!! std
    For each operation that is specified as implicitly creating objects, that operation implicitly creates and starts the lifetime of zero or more objects of implicit-lifetime types ([basic.types.general]) in its specified region of storage if doing so would result in the program having defined behavior.

An operation specified as **implicitly creating objects** ([[g:implicitly-create-objects|implicitly create objects]]) creates zero or more objects of implicit-lifetime types in its region of storage, chosen so that the program has defined behavior. If no such set of objects exists, the program has UB; if there are several, which set is created is unspecified.

Which objects to create can depend on code executed later:

```cpp run title="choose.cpp" ok
#include <cstdio>
#include <cstdlib>

int main(int argc, char**) {
  void* m = std::malloc(2 * sizeof(double));
  if (argc > 1) {                 // malloc created a double
    double* d = static_cast<double*>(m);
    *d = 1.5;
    std::printf("%g\n", *d);
  } else {                        // malloc created an int[2]
    int* p = static_cast<int*>(m);
    p[0] = 1;
    p[1] = 2;                     // pointer arithmetic needs an array object
    std::printf("%d\n", p[0] + p[1]);
  }
  std::free(m);
}
```

Which branch runs depends on run-time arguments, while `malloc` is called before the branch. The rule means: for the execution that actually happens, if some set of objects makes it defined, then `malloc` created that set. The paper sums this up with an observation: changing the set of implicitly created objects can only change whether an execution is defined, never how it behaves. That is why this rule, which seems to require foreseeing the future, needs no action from the compiler.

The paper uses `std::vector<int>` to illustrate several sets coexisting. After `reserve(4)` followed by only three `push_back`s, creating either `int[3]` or `int[4]` in the allocated storage makes the program defined, and both interpretations give the same behavior; one more `push_back` and only `int[4]` remains.

### Which pointer is returned

Creating objects is not enough; the pointer `malloc` returns also has to point to the right object. In the `else` branch of the example above, what is needed is a pointer to the first element of `int[2]`, not a pointer to the array itself, or else `static_cast<int*>(m)` would not give an `int*` that can be subscripted (an array and its first element are not **pointer-interconvertible**, [[basic.compound#7]]).

For this R6 added [[intro.object#14]]: some operations also produce a pointer to a **suitable created object** ([[g:suitable-created-object|suitable created object]]), i.e. one chosen from the created objects whose address is the start of the region, again chosen so that the program is defined. `malloc`, `calloc`, `realloc`, `aligned_alloc` ([[c.malloc#4]], [[c.malloc#7]]) and all functions named `operator new` or `operator new[]` ([[intro.object#16]]) behave this way.

When the lifetime of a byte array begins, objects are also implicitly created, but that operation has no return value, and a pointer decayed from the array still points to the array's element. That is why objects in a byte buffer need `std::launder` to reach; see the section on `launder` in [[topics/object-model]].

### Where the wording changed

| Subclause | Change |
|---|---|
| [[intro.object#1]] | Operations that implicitly create objects added to the ways objects are created |
| [[intro.object#13]]–[[intro.object#16]] | The rules for implicit creation, suitable created objects, byte arrays and `operator new` |
| [[basic.types.general#7]], [[class.prop#8]] | Define implicit-lifetime types and implicit-lifetime classes |
| [[c.malloc#4]], [[c.malloc#7]] | The `malloc` family implicitly creates objects; `calloc` before zeroing, `realloc` before copying |
| [[cstring.syn#3]] | `memcpy` and `memmove` implicitly create objects in the destination before copying |
| [[allocator.members]] ¶5 | `allocator<T>::allocate(n)` only creates the `T[n]` array object and does not begin the lifetime of the elements |
| [[bit.cast]] ¶3 | Nested objects in the result are implicitly created (for types containing unions) |
| [[class.copy.ctor#16]] etc. | A trivial union copy also copies the object structure |
| [[basic.life#2]], [[expr.call#4]] | A pseudo-destructor call ends the object's lifetime |

The `allocate` row was changed in R6 to fit with C++20's constexpr containers: if `allocate` could create any set of objects, a compile-time evaluator could not track it; specifying that it only creates a `T[n]` gives pointer arithmetic an array to rely on and lets compile time model it precisely. A user's own allocator that reuses storage can meet the same requirement with `new (p) std::byte[n * sizeof(T)]`.

### Type punning was not made legal

Implicit creation is easily misread as meaning bytes can be read as any type at will. The paper devotes a section to explaining that it does not:

```cpp run title="no-pun.cpp" ub
#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <new>

int main() {
  void* m = std::malloc(4);
  *static_cast<int*>(m) = 0x3f800000;  // OK: malloc created an int
  ::new (m) std::byte[4];              // OK: implicitly creates objects in it
  float* f = std::launder(static_cast<float*>(m));
  std::printf("%g\n", *f);             // UB: the float's value is indeterminate
  std::free(m);
}
```

After `new (m) std::byte[4]`, a `float` can indeed appear implicitly, and `*f` does point to it. But an object's value only has meaning within its own lifetime ([[basic.life#5]]): the `int`'s lifetime ended when its storage was reused, and its value went with it; the newly created `float` has an indeterminate value, and reading an indeterminate value is UB ([[basic.indet]]). This preserves the premise of TBAA: reading some scalar type never reads a value previously written as an unrelated scalar type. To interpret bytes as another type, use `std::memcpy` or `std::bit_cast` (see [[topics/type-punning]]).

The same consideration determined how unions are copied:

```cpp run title="union-copy.cpp" ub
union U { int n; float f; };

float pun(int n) {
  U u = {.n = n};
  U u2 = u;      // the active member of u2 is n too
  return u2.f;   // UB: f is not within its lifetime
}

int main() { return pun(1) > 0; }
```

A trivial union copy constructor only copies bytes. By the letter of C++17, `u2` has no active member at all. The paper considered two fixes: have the copy also copy the object structure, so `u2`'s active member is `n`; or have the copy implicitly create objects, so `u2.f` becomes a bit conversion. It chose the former, to preserve equational reasoning (`u2` should be the same as `u`) and to make bit conversions explicit with `std::bit_cast`. The result is written in [[class.copy.ctor#16]] and [[class.copy.assign]].

### No creation during constant evaluation

The *Except during constant evaluation* at the start of [[intro.object#16]] excludes constant evaluation. The paper's reason is that constant evaluation is already conservative about object creation, and supporting it would be very costly for some implementations; since `reinterpret_cast` is forbidden in constant expressions, the difference is unobservable in most cases anyway.

<div class="compare" markdown="1">

```cpp error
#include <memory>
constexpr int g() {
  std::allocator<int> al;
  int* p = al.allocate(2);
  p[0] = 1;   // the element is not within its lifetime
  int r = p[0];
  al.deallocate(p, 2);
  return r;
}
static_assert(g() == 1);
```

```cpp ok
#include <memory>
constexpr int h() {
  std::allocator<int> al;
  int* p = al.allocate(2);
  std::construct_at(p, 1);
  int r = p[0];
  std::destroy_at(p);
  al.deallocate(p, 2);
  return r;
}
static_assert(h() == 1);
```

</div>

`allocate` only begins the lifetime of the array object, not of its elements ([[allocator.members]] ¶5), and during constant evaluation there is no implicit creation to fill the gap, so `p[0]` is an `int` not within its lifetime. Clang 23 rejects the left side, pointing out that `p[0] = 1` is an assignment to an object outside its lifetime. At compile time, elements must be created one by one with `std::construct_at`.

### Pseudo-destructor calls

The paper also fixed an inconsistency along the way. When generic code writes `p->~T()` and `T` is `int`, it is called a **pseudo-destructor call** ([[g:pseudo-destructor|pseudo-destructor]]), which C++17 specified as having no effect. The paper considered this a mistake: if objects can appear implicitly, they should also be able to end explicitly. Since C++20, a pseudo-destructor call ends the lifetime of a scalar object ([[expr.call#4]]). The paper added an Annex C entry for this: reading the object afterwards is UB, which is observable in constant evaluation; see [[diff.cpp17.basic#1]] and the explanation on the [[diff.cpp17]] page.

### Into C++20 as a defect fix

The paper could not complete library review before the C++20 deadline, so the author split it in two: the language rules, which give existing practice defined behavior, were merged into C++20 as a defect fix (DR), also responding to a national body comment asking C++20 to adopt implicit object creation; being a DR, it also applies to earlier standard modes. The new library function `start_lifetime_as` was deferred to C++23. What a DR means is explained in [[papers/how-to-read-a-paper]]. This is also why `make_x` should be considered defined under `-std=c++17` as well.

## Later fixes

[[CWG2489]] removed `char` arrays. [[P0593R6]] originally specified that arrays of `char`, `unsigned char` and `std::byte` all implicitly create objects when their lifetime begins, but only the latter two can **provide storage** ([[g:provides-storage|provides storage]], [[intro.object#3]]) for objects within them. The two pieces of wording were inconsistent, and the fix is that `char` arrays no longer implicitly create objects. Buffers should always be declared as `unsigned char` or `std::byte` (see the pitfall on the [[intro.object]] page).

[[CWG2605]] tightened the rule for aggregates: an aggregate with a user-provided destructor is no longer an implicit-lifetime class, because destroying it runs code, violating the paper's own second condition.

[[LWG4064]] clarified the return value of `memcpy`. The original wording only said `memcpy` implicitly creates objects in the destination region, not what its return value points to, so whether `*static_cast<int*>(std::memcpy(buf, &x, 4))` still needs `std::launder` was disputed. After the fix, [[cstring.syn#3]] specifies that `memcpy` and `memmove` return a pointer to a suitable created object.

## Why start_lifetime_as is still needed

The library half was added to C++23 by [[P2590R2]]: `std::start_lifetime_as<T>(p)` and `start_lifetime_as_array<T>(p, n)` ([[obj.lifetime#5]]). They create a `T` object at `p` whose object representation is the existing bytes, and return a pointer to it. P2590R2 gives two kinds of situations that implicit creation does not cover.

The first is storage that does not come from the few functions the standard names. An implementation can specify that `mmap` or `VirtualAlloc` implicitly create objects, but in practice there is usually no such documentation; users' own memory pools even less so, since the reuse happens in C++ code the compiler can see.

The second is bytes that are already in a buffer. Then the question is not whether there is an object, but what the pointer in hand points to. Section 3.7 of [[P0593R6]] holds that `new char[N]` implicitly creates a suitable `Foo`, so `reinterpret_cast<Foo*>(buffer.get())` is defined; section 1.2 of [[P2590R2]] judges the same code to be UB. Under the current wording the latter is right: `char` arrays no longer implicitly create objects ([[CWG2489]]), and the pointer from `reinterpret_cast` still points to the array element, not to that `Foo` ([[expr.static.cast#12]]).

<div class="compare" markdown="1">

```cpp ub
#include <cstring>
struct Header { int len, kind; };

int len(unsigned char* buf) {
  auto* h =
    reinterpret_cast<Header*>(buf);
  return h->len;  // doesn't point to a Header
}
```

```cpp ok
#include <cstring>
#include <new>
struct Header { int len, kind; };

int len(unsigned char* buf) {
  void* v = std::memmove(
    buf, buf, sizeof(Header));
  auto* h = std::launder(
    static_cast<Header*>(v));
  return h->len;
}
```

</div>

Both assume that `buf` is aligned and that its first 8 bytes are a valid `Header` representation. The right side is the substitute that can be written in C++20: `memmove` copies the bytes to a temporary area, implicitly creates objects at the destination, and copies them back, so the bytes are unchanged and the object now exists. After [[LWG4064]] its return value itself points to the `Header`, so `launder` is no longer necessary, though keeping it is harmless. Clang 23 at `-O2` eliminates the `memmove` and the `launder` on the right entirely, leaving the function with a single load instruction, the same as the left.

`start_lifetime_as` gives this idiom a name, and does not access the storage, so it works on read-only mapped memory too:

```cpp
struct Header { int len, kind; };

int len(const unsigned char* buf) {
  return std::start_lifetime_as<Header>(buf)->len;
}
```

At the time of writing, the libc++ shipped with Clang 23 does not yet provide `std::start_lifetime_as` (there is no `__cpp_lib_start_lifetime_as`), so this code has not been compiled. `std::is_implicit_lifetime` is already provided. How it divides the work with `launder`, and the details of the array version, are in [[obj.lifetime]] and [[topics/type-punning]].

## Can it be checked

Implicit creation only decides whether an execution is defined and corresponds to no action on the machine, so dynamic tools have a hard time checking it. Observations with Clang 23:

- `-fsanitize=address,undefined` reports nothing for `reuse.cpp`, `no-pun.cpp` or `union-copy.cpp`; the first two print `2` and `1` respectively.
- `-fsanitize=type` (TypeSanitizer) reports the second write and the following read in `reuse.cpp`, and also reports `no-pun.cpp` reading as `float` storage last written as `int`. But what it checks is whether the access type matches the type of the last write, which approximates the aliasing rules the optimizer uses rather than the C++ object model: change the second write in `reuse.cpp` to the valid `::new (m) float(2.0f)` and it still reports; the read on the left above that lacks `launder` is not reported.

!!! impl
    The real risk comes from the optimizer, not from checking tools. TBAA relies on objects of different types not overlapping; as long as a program reusing storage creates the new object explicitly with placement new, `memcpy` or `start_lifetime_as`, the compiler will not treat a write of the old type and a read of the new type as unrelated.

## Questions

!!! question "Is this code defined?"
    ```cpp
    struct P { int x, y; };
    int f() {
      alignas(P) char buf[sizeof(P)];
      P* p = reinterpret_cast<P*>(buf);
      p->x = 1;
      return p->x;
    }
    ```

<details markdown="1">
<summary>Answer</summary>

It is not. A `char` array does not implicitly create objects when its lifetime begins ([[intro.object#16]]; after [[CWG2489]] only `unsigned char` and `std::byte` do), so there is no `P` in `buf`. Even with `unsigned char`, the pointer from `reinterpret_cast` still points to `buf[0]`, and `std::launder` is needed to point to the implicitly created `P`. The simplest way is `P* p = ::new (buf) P;`, with an `unsigned char` or `std::byte` buffer.

</details>

!!! question "Can `malloc` make both uses below defined?"
    ```cpp
    void* m = std::malloc(sizeof(int));
    *static_cast<int*>(m) = 1;
    unsigned u = *static_cast<unsigned*>(m);
    ```

<details markdown="1">
<summary>Answer</summary>

It is defined. `malloc` creates an `int`, and the second line writes to it. The third line reads the `int` object through an `unsigned` lvalue, which [[basic.lval#11]] allows (access through the corresponding unsigned type), and the value read is 1. No second object is needed here, which is what makes it different from `reuse.cpp`.

</details>

## Summary

| Question | Conclusion | Source |
|---|---|---|
| Which operations implicitly create objects | The `malloc` family, `operator new`, the start of lifetime of `unsigned char`/`std::byte` arrays, `memcpy`/`memmove`, `bit_cast`, `start_lifetime_as` | [[intro.object#16]], [[c.malloc#4]], [[cstring.syn#3]], [[obj.lifetime#5]] |
| Which objects are created | The set that makes the program defined; if none, UB | [[intro.object#13]] |
| Which types can be created implicitly | Scalars, arrays, classes with a trivial constructor and trivial destructor, aggregates whose destructor is not user-provided | [[basic.types.general#7]], [[class.prop#8]] |
| Is type punning now legal | No, the new object's value is indeterminate | [[basic.life#5]] |
| During constant evaluation | Does not happen | [[intro.object#16]] |
| How it entered the standard | The language part as a DR for C++20, the library part as C++23's [[P2590R2]] | |
