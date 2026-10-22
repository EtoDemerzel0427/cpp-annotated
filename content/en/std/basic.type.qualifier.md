---
title: CV-qualifiers
summary: "How const and volatile apply to types: every object type has four cv versions; what a const object is; the cv-qualification of an array belongs to its elements; the partial order of more cv-qualified; and where top-level cv-qualifiers are dropped."
updated: 2026-10-19
---

!!! tldr
    - Every type other than function and reference types has four versions: `T`, `const T`, `volatile T` and `const volatile T`, with the same representation and alignment. Function types and reference types never carry cv.
    - Whether an object is a [[g:const-object|const object]] is determined by its type when it is created. Modifying a const object is UB; a non-const object seen through a const pointer may be modified after casting away const.
    - `const int*` is not itself a const type: cv does not propagate from components to compound types. The only exception is arrays: an array's cv is its elements' cv.
    - [[g:top-level-cv-qualifiers|Top-level cv]] is the cv applied directly to the whole type. Parameter types, by-value template deduction, `auto` and the types of prvalues all drop it.
    - volatile accesses are observable behavior, but they are not atomic and do not synchronize threads. C++20 deprecated several easily misunderstood uses of volatile.

## Four cv versions (¶1)

`const` and `volatile` are collectively the **cv-qualifiers**. Where they are written and how they combine is governed by the grammar in [[dcl.type.cv]]; this subclause covers what they mean once applied to a type.

¶1 Each type other than a function or reference type is a member of a group of four types:

| Version | With `int` as an example |
|---|---|
| cv-unqualified | `int` |
| const-qualified | `const int` |
| volatile-qualified | `volatile int` |
| const-volatile-qualified | `const volatile int` |

These four types are distinct, but must have the same representation and alignment requirements ([[basic.align]]). Footnote 28 explains the purpose: to make them interchangeable as arguments to functions, return values from functions, and non-static data members of unions. For example, passing the value of a `const int` to an `int` parameter requires no change to how it looks in memory.

Function types and reference types are always cv-unqualified. When cv is added to them through a typedef or template parameter, the cv is ignored ([[dcl.ref]], [[dcl.fct]]):

```cpp run ok
#include <type_traits>

using Ref = int&;
using Fn  = void(int);

static_assert(std::is_same_v<const Ref, int&>);   // the const is ignored
static_assert(std::is_same_v<const Fn, Fn>);      // the const is ignored
int main() {}
```

The program is well-formed; Clang 23 only notes that the qualifiers have no effect (`-Wignored-reference-qualifiers`, `-Wignored-qualifiers`).

## const objects (¶1.1–¶1.3)

```cpp run ub
int main() {
  int i = 2;
  const int* cip = &i;               // i seen through a const pointer, but i is not a const object
  *const_cast<int*>(cip) = 4;        // OK

  const int* ciq = new const int(3); // the new object has type const int
  *const_cast<int*>(ciq) = 4;        // UB: modifies a const object

  struct X { mutable int m; int n; };
  const X x{1, 2};
  x.m = 10;                          // OK: a mutable member is not a const object
  const_cast<X&>(x).n = 20;          // UB: x.n is a const object
  delete ciq;
  return i;
}
```

The two `const_cast`s are written the same way but have different outcomes. The difference is whether the object being modified is itself a const object. ¶1 defines three kinds of objects:

- ¶1.1 a **const object** is an object of type `const T` or a non-mutable subobject of a const object.
- ¶1.2 a **volatile object** is an object of type `volatile T` or a subobject of a volatile object.
- ¶1.3 a **const volatile object** is an object of type `const volatile T`, a non-mutable subobject of a const volatile object, a const subobject of a volatile object, or a non-mutable volatile subobject of a const object.

Note 1 adds that the type of an object includes the cv-qualifiers specified in the declaration or *new-type-id* when the object is created. So const is a property an object carries from birth, independent of what kind of pointer or reference is later used to access it.

[[dcl.type.cv#4]] specifies that modifying a const object during its lifetime is UB. This is for the sake of optimization: compilers can put const objects in read-only sections, constant-fold them, and cache their values across function calls. A modification through `const_cast` generally cannot be detected at compile time, so the standard does not make it a compile error.

!!! note "mutable exempts only from const"
    ¶1.2 has no "non-mutable" qualification: every subobject of a volatile object is volatile. volatile says this storage may be changed by factors outside the program, which holds for the whole object; `mutable` is for logical constness (caches, for example) and is unrelated.

!!! lawyer "Not const during construction and destruction"
    A const object is not treated as const while its constructor and destructor run ([[class.ctor]], [[class.dtor]]), so the constructor of `const Widget w;` can assign to members. [[dcl.type.cv#4]] speaks of "during its lifetime", and the lifetime begins only after construction completes ([[basic.life]]).

## Compound types don't inherit cv, except arrays (¶2–¶4)

¶2 Except for array types, a compound type ([[basic.compound]]) is not cv-qualified by the cv-qualifiers (if any) of the types from which it is compounded.

| Type | Itself const-qualified? | Notes |
|---|---|---|
| `const int*` | no | an ordinary pointer to const int |
| `int* const` | yes | a const pointer |
| `const int&` | no | references never carry cv |
| `S` in `struct S { const int x; }` | no | a class doesn't become const because a member is const |
| `const int[3]` | yes | an array, see ¶3 |

So `std::is_const_v<const int*>` is `false`.

¶3 An array type whose elements are cv-qualified is also considered to have the same cv-qualifications as its elements. Note 2 says the same from the other direction: cv-qualifiers applied to an array type attach to the element type, so cv `T`, where `T` is an array type, refers to an array whose elements are so qualified ([[dcl.array]]). Adapted from Example 1:

```cpp run ok
#include <type_traits>

typedef char CA[5];
typedef const char CC;
CC       arr1[5] = { 0 };     // an array of 5 const char
const CA arr2    = { 0 };     // const applied to the array typedef attaches to the elements

static_assert(std::is_same_v<decltype(arr1), decltype(arr2)>);
static_assert(std::is_same_v<decltype(arr1), const char[5]>);
static_assert(std::is_const_v<const char[5]>);   // the array type counts as const-qualified
int main() {}
```

An array cannot be assigned as a whole and has no value independent of its elements, so there is no case where the array itself is const but its elements are not. Attaching cv uniformly to the elements avoids two indistinguishable types. It also makes templates work naturally: instantiating `template<class T> void f(const T&)` with `int[3]` gives the parameter type `const int(&)[3]`.

The sentence that the array itself also counts as cv-qualified was added by the resolution of [[CWG1059]]. Through C17, C considered array types themselves never qualified; C23 adopted the same rule as C++.

¶4 is a note pointing to cv-qualified function types. The type of a member function `void f() const` is written `void() const`; this `const` qualifies the implicit object parameter ([[dcl.fct]], [[over.match.funcs]]), and the function type itself is still cv-unqualified.

## More cv-qualified (¶5)

```cpp run ok
#include <cstdio>

void f(const int&)          { std::puts("const int&"); }
void f(const volatile int&) { std::puts("const volatile int&"); }

int main() {
  int i = 0;
  f(i);          // both are viable; const int& has less cv, so it is better
  volatile int v = 0;
  f(v);          // const int& is not viable (cannot drop volatile)
}
```

The program prints `const int&` and then `const volatile int&`. Overload resolution needs to compare which of two types has more cv, and uses the partial order defined in ¶5.

¶5 There is a partial ordering on cv-qualifiers, according to which a type can be said to be **more cv-qualified** than another. Table 16 lists all the relations:

| Less | | More |
|---|---|---|
| no cv | < | `const` |
| no cv | < | `volatile` |
| no cv | < | `const volatile` |
| `const` | < | `const volatile` |
| `volatile` | < | `const volatile` |

You can think of it as inclusion between subsets of {const, volatile}. `const` and `volatile` do not include each other and cannot be compared, which is why it is a partial order.

The main rules that use the [[g:more-cv-qualified|more cv-qualified]] order are three:

- Qualification conversions can only add cv ([[conv.qual]]): `int*` can convert to `const int*`, not the other way around.
- Reference binding: for a reference to `cv1 T` to bind to an object of type `cv2 T`, cv1 must not be less than cv2 ([[dcl.init.ref]]).
- Overload resolution: when two reference bindings differ only in cv, the one with less cv is better ([[over.ics.rank]]), as in the example above.

## Top-level cv (¶6)

¶6 In describing types, the standard uses the notation cv (or cv1, cv2) for an arbitrary set of cv-qualifiers: {const}, {volatile}, {const, volatile} or the empty set. For a type cv `T`, the qualifiers that cv denotes are its **top-level cv-qualifiers**. Intuitively, top-level cv is the layer applied directly to the whole type. Example 2 gives three examples:

| *type-id* | Top-level cv | Why |
|---|---|---|
| `const int&` | none | references carry no cv; the `const` belongs to the referenced type |
| `volatile int * const` | `const` | the pointer itself is const; the `volatile` belongs to the pointed-to type |
| `void (C::* volatile)(int) const` | `volatile` | the pointer to member itself is volatile; the trailing `const` belongs to the member function type |

Many rules drop only top-level cv:

```cpp run ok
#include <type_traits>

void f(int);
void f(const int);           // a redeclaration of the same function
void f(int) {}

void g(int*);
void g(const int*);          // two different overloads: the const is not top-level

const int k();
static_assert(std::is_same_v<decltype(k()), int>);   // the cv of a prvalue is removed

int main() {
  const int ci = 0;
  auto a = ci;                                     // auto drops top-level const
  static_assert(std::is_same_v<decltype(a), int>);
  int* const p = nullptr;
  auto q = p;                                      // q is int*
  static_assert(std::is_same_v<decltype(q), int*>);
}
```

1. Parameter type adjustment ([[dcl.fct]]) deletes top-level cv from parameters, so `void f(int)` and `void f(const int)` are the same function. A `const` on a parameter only affects whether this local variable can be modified in the function body.
2. Template argument deduction for by-value parameters ([[temp.deduct.call]]) ignores top-level cv: calling `template<class T> void h(T);` with a `const int` argument deduces `T = int`. `auto` deduces by the same rule.
3. A prvalue of non-class, non-array type cv `T` has its type adjusted to `T` ([[expr.type#2]]). So for a function returning `const int`, the call expression has type `int`, and Clang notes that the const on the return type has no effect.

In the Itanium C++ ABI (used by GCC and Clang on Linux and macOS), top-level cv on function parameters does not enter the mangled name either; `f(int)` and `f(const int)` have the same symbol.

## Semantics and deprecations of volatile

This subclause only defines what a volatile object is. The semantics of volatile are elsewhere:

- [[dcl.type.cv#5]]: the semantics of an access through a volatile glvalue are implementation-defined; accessing an object defined with a volatile type through a non-volatile glvalue is UB.
- [[intro.abstract]]: accesses through volatile glvalues are observable behavior; compilers cannot omit or merge them, or change their order relative to one another.
- volatile provides no atomicity and establishes no happens-before relation between threads. Multithreaded synchronization needs `std::atomic` ([[atomics]]).

C++20's [[P1152R4]] deprecated several uses of volatile that suggest an atomicity or single access that volatile does not provide. Those still deprecated in the current draft ([[depr.volatile.type]]):

| Use | Status |
|---|---|
| `++` and `--` on volatile arithmetic or pointer types | deprecated: `++v` is one read plus one write, often mistaken for atomic |
| assignment whose left operand is of volatile non-class type, with the result used (as in `x = v = 1`) | deprecated ([[expr.assign#5]]) |
| assignment and compound assignment as standalone statements, like `v = 1`, `v += 1`, <code>v &#124;= mask</code> | not deprecated |
| function types with volatile parameters or a volatile return type | deprecated: volatile on a by-value parameter is meaningless |
| volatile-qualified structured bindings | deprecated |

Compound assignment went back and forth. C++20 deprecated all of them, but register operations like `REG |= BIT` are everywhere in embedded code. [[P2327R1]] first undeprecated the bitwise compound assignments, and [[CWG2654]] then undeprecated the rest.

```cpp run ok
volatile int reg;
int x;

void f() {
  reg |= 0x4;      // OK
  reg += 1;        // OK
  reg = 3;         // OK: the assignment is a discarded-value expression
  ++reg;           // deprecated
  x = reg = 2;     // deprecated: uses the result of a volatile assignment
}
void g(volatile int);   // deprecated: volatile parameter

int main() { f(); }
```

Under `-std=c++2c`, Clang 23 gives `-Wdeprecated-volatile` warnings for `++reg`, `x = reg = 2` and the declaration of `g`, and no warning for `reg |= 0x4` or `reg += 1`, consistent with the current draft.

!!! impl
    - const objects with static storage duration and constant initialization usually go into read-only sections (`.rodata` in ELF, `__TEXT,__const` in Mach-O), and writing to one after `const_cast` triggers a segmentation fault. const objects with dynamic initialization or mutable members can only go into writable sections.
    - GCC and Clang make each volatile access correspond to one load or store instruction of the same width, not reordered with other volatile accesses, but insert no memory barriers. MSVC's `/volatile:ms` mode gives volatile acquire/release semantics, which is an extension; on ARM targets the default is `/volatile:iso`.

## Common misconceptions

!!! pitfall "const pointers and pointers to const"
    With `const int* p` you can change `p` but not `*p`; `int* const p` is the opposite. Read declarations from right to left: `int* const` is a const pointer to int.

!!! pitfall "`const_cast` itself is UB"
    Casting away const is always valid; UB occurs only if a const object is then modified. Conversely, modifying a const object by other means such as `memcpy`, without `const_cast`, is equally UB.

!!! pitfall "volatile can be used for thread synchronization"
    C++'s volatile, unlike Java's, provides no atomicity and establishes no happens-before. Two threads reading and writing the same `volatile int` without synchronization is still a data race ([[intro.races]]).

## Questions

!!! question "1. In `using A = int[3]; const A* p;`, what is the type of `p`? What is the value of `std::is_const_v<std::remove_pointer_t<decltype(p)>>`?"

<details markdown="1">
<summary>Answer</summary>

The const in `const A` attaches to the elements, so `const A` is `const int[3]`, and `p` has type `const int (*)[3]`. By ¶3, `const int[3]` counts as a const-qualified type, so the result is `true`.
</details>

!!! question "2. In `struct S { mutable int m; const int c; int n; }; const S cs{1,2,3}; S s{1,2,3};`, which are const objects?"

<details markdown="1">
<summary>Answer</summary>

- `cs` has type `const S` and is a const object.
- `cs.m` is a mutable subobject of a const object and is not a const object.
- `cs.c` and `cs.n` are non-mutable subobjects of a const object and are both const objects.
- `s` is not a const object, but `s.c` has type `const int` and is a const object. `s.m` and `s.n` are not.

So `const_cast<int&>(s.c) = 0;` is also UB (¶1.1, [[dcl.type.cv#4]]).
</details>

!!! question "3. Why is `void f(volatile int)` deprecated, but `void g(volatile int*)` not?"

<details markdown="1">
<summary>Answer</summary>

A `volatile int` parameter is a local copy passed by value; this volatile is top-level cv, does not enter the function type, and is invisible to callers. It only keeps accesses to the copy in the function body from being optimized, which is almost never what the author intended. The volatile in `volatile int*` is not top-level; it says the pointed-to object (usually a hardware register) needs volatile access, and is part of the interface. Example 3 in [[depr.volatile.type]] contrasts exactly these two forms.
</details>
