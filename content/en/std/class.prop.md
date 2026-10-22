---
title: Properties of classes
summary: "Three class properties that decide whether objects can be manipulated at the byte level: trivially copyable (can it be memcpy'd), standard-layout (is the layout as predictable as a C struct), and implicit-lifetime (can the object be used directly in memory from malloc)."
updated: 2026-10-19
---

!!! tldr
    - A trivially copyable class can be copied byte by byte with `memcpy` or `std::bit_cast`. The conditions involve only copying, moving and destruction, not the default constructor.
    - A standard-layout class has a layout as predictable as a C struct: the first member has the same address as the object, and `offsetof` is guaranteed. The data members must all be in the same class of the inheritance hierarchy and have the same access control.
    - Objects of an implicit-lifetime class can come into existence without running any code, so they can be used directly in storage obtained from `malloc` or `memcpy`.
    - The three properties are independent; trivially copyable is not the same as standard-layout. C++26 moved the notion of a trivial class into Annex D and deprecated it.

## What each property is about

```cpp run title="combinations.cpp" ok
#include <type_traits>

struct N {          // neither
    int i;
    int j;
    virtual ~N() = default;
};

struct T {          // trivially copyable but not standard-layout
    int i;
private:
    int j;
};

struct SL {         // standard-layout but not trivially copyable
    int i;
    int j;
    ~SL() { }
};

struct POD {        // both
    int i;
    int j;
};

static_assert(!std::is_trivially_copyable_v<N>   && !std::is_standard_layout_v<N>);
static_assert( std::is_trivially_copyable_v<T>   && !std::is_standard_layout_v<T>);
static_assert(!std::is_trivially_copyable_v<SL>  &&  std::is_standard_layout_v<SL>);
static_assert( std::is_trivially_copyable_v<POD> &&  std::is_standard_layout_v<POD>);
int main() { }
```

This is adapted from Example 2 in the standard (¶6). `N` has a virtual destructor, so it can't be copied byte by byte and also has a hidden vtable pointer; the two members of `T` have different access control; `SL` has a user-written destructor. The three properties answer three questions:

| Property | Question it answers | Type trait |
|---|---|---|
| Trivially copyable | Is a byte-wise copy the same as a copy by value | `std::is_trivially_copyable` |
| Standard-layout | Can the layout be inferred like a C struct's | `std::is_standard_layout` |
| Implicit-lifetime | Can an object come into existence without running any code | `std::is_implicit_lifetime` |

[[basic.types.general]] builds on these, adding scalar types, to define trivially copyable types, standard-layout types and implicit-lifetime types. This subclause only deals with classes.

C++98's **POD** (plain old data) carried both guarantees at once: can be `memcpy`'d and has a C-like layout. C++11 split it into two independent notions, because the former is about copy semantics and the latter about memory layout, and many types need only one of them.

## Trivially copyable classes (¶1)

A special member function that does nothing extra is **trivial**: a trivial copy constructor or copy assignment is a byte-wise copy, a trivial destructor does nothing. The exact conditions are in the respective subclauses ([[class.copy.ctor#12]], [[class.copy.assign#9]], [[class.dtor#8]]) and follow the same pattern:

1. It is not user-provided ([[g:user-provided]]), that is, it is implicitly declared or defaulted with `= default` on its first declaration;
2. The class has no virtual functions and no virtual base classes (the destructor version: the destructor is not virtual);
3. For every base class and member of class type, the function selected to perform the same operation is also trivial.

Virtual functions and virtual base classes break triviality because, when copying, the vtable pointer and virtual base offsets must be set to the values for the target object's type. The source object might be a base class subobject inside some more-derived object, and its bytes can't simply be copied over.

¶1 A class is a **trivially copyable class** ([[g:trivially-copyable-class|trivially copyable class]]) if and only if:

- ¶1.1 it has at least one eligible copy constructor, move constructor, copy assignment operator or move assignment operator;
- ¶1.2 each eligible function of these four kinds is trivial;
- ¶1.3 it has a trivial, non-deleted destructor.

The default constructor is not among the conditions. The default constructor of `struct S { int x = 0; };` is non-trivial because of the default member initializer, but `S` is still trivially copyable.

### Eligible: only the functions that can actually be used count

A special member function is **eligible** ([[g:eligible-special-member-function|eligible]]) if it is not deleted, its constraints (if any) are satisfied, and there is no other function of the same kind that is also satisfied and more constrained ([[special#6]]). C++20 introduced this notion ([[P0848R3]]) so that wrappers like `std::optional<T>` can be trivially copyable themselves when `T` is:

```cpp run title="conditionally-trivial.cpp" ok
#include <string>
#include <type_traits>

template<class T>
struct Opt {
    Opt(const Opt&) requires std::is_trivially_copy_constructible_v<T> = default;  // #1
    Opt(const Opt&) { /* manual copy */ }                                            // #2
    T t;
};

// Opt<int>: #1 satisfies its constraint and is more constrained than the unconstrained #2; only #1 is eligible, and it is trivial
static_assert(std::is_trivially_copyable_v<Opt<int>>);
// Opt<std::string>: #1 does not satisfy its constraint; only #2 is eligible, and it is user-provided
static_assert(!std::is_trivially_copyable_v<Opt<std::string>>);

int main() { }
```

¶1.2 only requires the eligible functions to be trivial. In `Opt<int>`, #2 is non-trivial but not eligible, so it doesn't affect the result. Before C++20 the same effect required layers of base class template specializations.

### A class whose copy and move operations are all deleted

¶1.1 requires at least one eligible copy or move operation, and a deleted function is not eligible. So a class with all copy and move operations `= delete`d is not trivially copyable: a type whose author deliberately forbade copying should not be copyable with `memcpy`.

```cpp run title="all-deleted.cpp" ok
#include <type_traits>
#include <cstdio>

struct NoCopy {
    NoCopy() = default;
    NoCopy(const NoCopy&) = delete;
    NoCopy& operator=(const NoCopy&) = delete;
};   // move operations are not implicitly declared

struct MoveOnly {
    MoveOnly() = default;
    MoveOnly(MoveOnly&&) = default;             // trivial and eligible
    MoveOnly& operator=(MoveOnly&&) = default;  // trivial and eligible
};   // copy operations are defined as deleted, not eligible, no effect on the result

static_assert(std::is_trivially_copyable_v<MoveOnly>);

int main() {
    // should be 0 per the standard (¶1.1); Clang 23 prints 1
    std::printf("%d\n", std::is_trivially_copyable_v<NoCopy>);
}
```

!!! warning "Clang disagrees with the standard"
    Clang 23 reports `is_trivially_copyable` as `true` for a class whose copy and move operations are all deleted. The requirement of at least one non-deleted operation comes from [[CWG1734]], which Clang has not implemented. Don't rely on this edge case in portable code.

### What trivially copyable buys you

- Copying an object's bytes into another object of the same type with `memcpy` or `memmove`, or copying them out and back in, yields the same value ([[basic.types.trivial]]).
- `std::bit_cast` requires both source and destination to be trivially copyable types ([[bit.cast]]), and `std::atomic<T>` requires `T` to be trivially copyable.
- A trivially copyable class is usually also an implicit-lifetime class (it has a trivial copy constructor and a trivial destructor), so `memcpy` into new storage implicitly creates objects ([[intro.object]]).

In the Itanium ABI, whether an object can be passed in registers depends on whether it is trivial for the purposes of calls (copy constructor, move constructor, destructor), which is close to but not the same as trivially copyable; see the implementation notes in [[basic.types]].

## Standard-layout classes (¶2)

```cpp run title="first-member.cpp" ok
#include <cstddef>

struct Header { int tag; };
struct Packet {            // standard-layout: all data members are in Packet
    Header h;
    char payload[16];
};

static_assert(offsetof(Packet, h) == 0);
static_assert(offsetof(Packet, payload) == sizeof(Header));

int main() {
    Packet p{{7}, {}};
    Header* hp = reinterpret_cast<Header*>(&p);   // OK: hp points to p.h
    return hp->tag - 7;
}
```

Intuitively, a **standard-layout class** ([[g:standard-layout-class|standard-layout class]]) is one whose layout can be inferred like a C struct's: data members are laid out in declaration order, the first member is at offset 0, there is no hidden vtable pointer, and nothing gets shifted because subobjects of the same type must have distinct addresses.

¶2 A class `S` is a standard-layout class if it satisfies all of the following:

| Item | Condition | Rationale |
|---|---|---|
| ¶2.1 | No non-static data members of non-standard-layout class type (or array of such types) or of reference type | Standard layout must hold recursively; C has no reference members |
| ¶2.2 | No virtual functions and no virtual base classes | The position of the vtable pointer and virtual base pointer is implementation-defined (Itanium puts it at offset 0) |
| ¶2.3 | All non-static data members have the same access control | Historical; see below |
| ¶2.4 | No non-standard-layout base classes | Recursion |
| ¶2.5 | At most one base class subobject of any given type | Two subobjects of the same type must have distinct addresses and can't both be at offset 0 |
| ¶2.6 | All non-static data members and bit-fields in the class and its base classes are first declared in the same class | The first member is uniquely determined and is at offset 0 |
| ¶2.7 | No element of the set *M*(S) of types as a base class | Prevents an empty base and the first member of the same type from being forced apart |

### Data members can only be in one level (¶2.6)

```cpp run title="sl-hierarchy.cpp" ok
#include <type_traits>

struct B { int i; };              // standard-layout
struct C : B { };                 // standard-layout: data members are all in B
struct D : C { };                 // standard-layout
struct E : D { char : 4; };       // not: E has a bit-field, while i is declared in B

struct Base { int a; };
struct Derived : Base { int b; }; // not: a is in Base, b in Derived

static_assert(std::is_standard_layout_v<D>);
static_assert(!std::is_standard_layout_v<E>);
static_assert(!std::is_standard_layout_v<Derived>);
int main() { }
```

At most one class in the inheritance hierarchy can have data members; the rest must be empty. When both a base and a derived class have data members, which member comes first depends on how the implementation arranges base class subobjects; the Itanium ABI may even pack derived class members into the base's tail padding. `E` shows that unnamed bit-fields count too: an unnamed bit-field is not a member ([[class.bit#2]]), which is why the wording explicitly says "and bit-fields". The first four lines are Example 1 in the standard (¶3).

### At most one base of a given type (¶2.5)

```cpp run title="sl-dup-base.cpp" ok
#include <type_traits>

struct Q { };
struct S : Q { };
struct T : Q { };
struct U : S, T { };          // U contains two Q subobjects

static_assert(!std::is_standard_layout_v<U>);
int main() { }
```

The two `Q` subobjects are distinct objects of the same type and must have distinct addresses ([[intro.object]]), so they can't both be at offset 0. But a standard-layout class requires the object's address to equal that of each base class subobject ([[class.mem.general#31]]), which is impossible here.

### An empty base of the same type as the first member (¶2.7)

```cpp run title="sl-mx.cpp" ok
#include <type_traits>
#include <cstdio>

struct E { };
struct S1 : E { E e; int x; };   // base E has the same type as the first member e
struct S2 : E { int x; E e; };   // the first member is an int

static_assert(!std::is_standard_layout_v<S1>);
static_assert(std::is_standard_layout_v<S2>);

int main() {
    S1 s;
    std::printf("%td\n", reinterpret_cast<char*>(&s.e) - reinterpret_cast<char*>(&s));
}
```

The empty base optimization wants to put the empty base `E` at offset 0, and the first member `e` also wants to be at offset 0. They are distinct objects of the same type and must have distinct addresses (which is what footnote 81 says), so the implementation has to move `e` to offset 1; in our tests the output is `1`. The guarantee that the first member has the same address as the object is lost, so the standard says `S1` is not standard-layout.

Note 1 explains that *M*(X) is the set of the types of all non-base-class subobjects of X that may be at offset 0. It is defined recursively:

- ¶2.7.1 If X is a non-union class with no non-static data members: *M*(X) is empty;
- ¶2.7.2 If X is a non-union class with a non-static data member of type X₀ that either is the first non-static data member (possibly an anonymous union) or has zero size: *M*(X) consists of X₀ and the elements of *M*(X₀);
- ¶2.7.3 If X is a union: *M*(X) is the union of all member types Uᵢ and all *M*(Uᵢ), because every member of a union is at offset 0;
- ¶2.7.4 If X is an array with element type Xₑ: *M*(X) consists of Xₑ and the elements of *M*(Xₑ);
- ¶2.7.5 If X is neither a class nor an array: *M*(X) is empty.

Because the definition is recursive, it also catches cases one level removed: in `struct S : E { struct { E inner; } w; };`, the type of `w` is in *M*(S), and `E` is in the *M* of `w`'s type, so `S` is not standard-layout. ¶2.7.2 also counts zero-size members because an empty `[[no_unique_address]]` member may be placed at offset 0 even if it isn't the first member.

### Same access control (¶2.3)

```cpp run title="sl-access.cpp" ok
#include <type_traits>

struct OK {         // all data members private: standard-layout
private:
    int i;
    int j;
public:
    int get() const { return i + j; }   // access of member functions doesn't matter
};
static_assert(std::is_standard_layout_v<OK>);
int main() { }
```

¶2.3 only looks at non-static data members. Before C++23 the relative order of members in different access sections (between `public:` and `private:`) was unspecified, and implementations could in theory reorder them; this item exists to rule out reordering. C++23 removed the permission to reorder ([[P1847R4]]), and now non-variant members of nonzero size are always allocated in declaration order ([[class.mem.general#24]]). But ¶2.3 was kept, because changing it would change the result of `is_standard_layout` for existing code.

### What standard layout guarantees

Standard layout by itself is just a classification; the guarantees are stated elsewhere:

1. The object is **pointer-interconvertible** ([[g:pointer-interconvertible]], [[class.mem.general#31]], [[basic.compound#7]]) with its first non-static data member (if not a bit-field) and with all its base class subobjects: converting a pointer between them with `reinterpret_cast` yields a pointer to the other directly. C-style header inheritance (`struct Derived { Base base; ... }`, using a `Derived*` as a `Base*`) relies on this.
2. `offsetof` is guaranteed to work for standard-layout classes and is conditionally-supported for other classes ([[support.types.layout#1]]). GCC and Clang give a `-Winvalid-offsetof` warning for `offsetof` on non-standard-layout types.
3. Two standard-layout structs have a common initial sequence ([[class.mem.general#27]]). When they are in the same union, the common prefix can be read through the inactive member ([[class.mem.general#30]]).
4. Layout compatibility ([[class.mem.general#28]]).
5. The note in ¶5 points out that standard-layout classes are useful for communicating with code written in other languages, for example passing structs across an `extern "C"` interface.

¶4 A standard-layout class defined with `struct` or `class` is a **standard-layout struct**; one defined with `union` is a **standard-layout union**. The common initial sequence is only defined for structs, and layout compatibility of unions has its own rule ([[class.mem.general#29]]), hence the distinction.

## Implicit-lifetime classes (¶8)

```cpp run title="implicit-lifetime.cpp" ok
#include <cstdlib>

struct Point { int x, y; };          // implicit-lifetime class

int main() {
    auto* p = static_cast<Point*>(std::malloc(sizeof(Point)));
    p->x = 1;                         // OK since C++20: malloc implicitly created a Point object
    p->y = 2;
    int r = p->x + p->y;
    std::free(p);
    return r - 3;
}
```

In C++17, this code is strictly speaking UB: `malloc` only allocates storage, and no `Point` object exists. C++20 introduced **implicit object creation** ([[P0593R6]], [[intro.object]]): operations such as `malloc`, `operator new`, `memcpy`, and starting the lifetime of an array of `unsigned char` or `std::byte` implicitly create objects of implicit-lifetime types in the storage, if doing so gives the program defined behavior.

¶8 A class `S` is an **implicit-lifetime class** ([[g:implicit-lifetime-class|implicit-lifetime class]]) if

- ¶8.1 it is an aggregate whose destructor is not user-provided, or
- ¶8.2 it has at least one trivial eligible constructor and a trivial, non-deleted destructor.

Both routes mean the same thing: an object can come into existence without running any user code. In ¶8.2, a trivial constructor (default, copy or move, any will do) shows there is a way to produce an object without executing code; a trivial destructor shows the object can also end without executing code. An aggregate in ¶8.1 can be initialized via aggregate initialization, with each member initialized on its own and no constructor called, so even if its members are non-trivial, the aggregate itself can appear implicitly as long as its destructor isn't user-written. The destructor restriction in ¶8.1 was added after C++20 by a core language issue.

```cpp run title="il-classes.cpp" ok
#include <type_traits>

struct Agg   { int x; ~Agg() { } };                   // aggregate, but user-provided destructor: no
struct P     { P() : x(1) { } int x; };               // trivial copy constructor, trivial destructor: yes (¶8.2)
struct NotIL { NotIL() { } NotIL(const NotIL&) { } int x; };   // no trivial constructor: no

static_assert(!std::is_implicit_lifetime_v<Agg>);
static_assert( std::is_implicit_lifetime_v<P>);
static_assert(!std::is_implicit_lifetime_v<NotIL>);
int main() { }
```

`P` has a user-provided default constructor, but its copy constructor is trivial: moving the bytes of another `P` over gives you a `P`, which is exactly what happens when `memcpy` implicitly creates an object.

!!! lawyer "An aggregate containing a `std::string` is also an implicit-lifetime class"
    `struct A { std::string s; };` is an aggregate with an implicitly declared destructor, so by ¶8.1 it is an implicit-lifetime class. That doesn't mean storage from `malloc` will automatically contain a usable `std::string`. `std::string` is not an implicit-lifetime type; when an `A` is created implicitly, the lifetime of the member `s` does not begin, and using it is still UB. Implicit lifetime only guarantees that the outer object can appear implicitly.

C++23 also provides `std::start_lifetime_as<T>` ([[obj.lifetime]]), which explicitly starts the lifetime of an object of implicit-lifetime type over existing bytes while preserving their contents. Use it when interpreting a network buffer as a struct.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

¶7 is a note: aggregates of class type are described in [[dcl.init.aggr]]. Being an aggregate is about initialization syntax and differs from all three properties in this subclause.

</details>

## Implementation notes

!!! impl "Type traits are compiler built-ins"
    `std::is_trivially_copyable`, `std::is_standard_layout` and `std::is_implicit_lifetime` are implemented as compiler built-ins on GCC, Clang and MSVC (for example Clang's `__is_trivially_copyable`, `__is_standard_layout`, `__builtin_is_implicit_lifetime`). They depend on information only the front end knows, such as whether a function is eligible or user-provided, and can't be written in pure library code.

!!! impl "The Itanium ABI's POD for the purpose of layout"
    The Itanium ABI has its own notion of POD for the purpose of layout, used to decide whether a derived class can reuse a base's tail padding. For example, with `struct A { int i; char c; }; struct B : A { char d; };`: if `A` is a POD for the purpose of layout, `d` can't go into `A`'s tail padding, because a C programmer might overwrite the padding with `memcpy(&a, ..., sizeof(A))`. This definition is based on C++03's POD and is frozen for ABI stability; it doesn't match standard-layout. Whether a type is standard-layout and whether a derived class will reuse its tail padding are not the same question.

## History

!!! history
    - C++98/03 had only the notion of POD, carrying both guarantees: can be `memcpy`'d and has a C-like layout.
    - C++11 split it into trivial, trivially copyable and standard-layout; POD meant trivial plus standard-layout. A class with user constructors could now be standard-layout.
    - [[CWG1734]] changed the definition of trivially copyable to require at least one non-deleted copy or move operation.
    - C++20 introduced eligible special member functions ([[P0848R3]]) and implicit-lifetime classes ([[P0593R6]]), and deprecated POD and `std::is_pod`.
    - C++23 no longer allows reordering members by access section ([[P1847R4]]); ¶2.3 is still there.
    - C++26 moved trivial classes, trivial types and `std::is_trivial` into Annex D and deprecated them ([[P3247R2]], [[depr.meta.types#3]]). A trivial class required trivially copyable plus a trivial default constructor, tying together two unrelated things; if you need them, query `is_trivially_copyable` and `is_trivially_default_constructible` separately.

## Common misconceptions

!!! pitfall "A default member initializer rules out `memcpy`"
    `struct S { int x = 0; };` is trivially copyable. A default member initializer only makes the default constructor non-trivial and has nothing to do with copying.

!!! pitfall "Standard-layout means it can be `memcpy`'d"
    Standard-layout is not the same as trivially copyable. `SL` has a user-provided destructor; it is standard-layout but can't be copied byte by byte.

!!! pitfall "Using `offsetof` on a derived class"
    `struct Derived : Base { int b; };` (where `Base` has data members) is not standard-layout, so `offsetof(Derived, b)` is conditionally-supported and GCC and Clang warn. A struct that needs `offsetof` should have all its data members in one class.

## Questions

!!! question "Question 1"
    Which of these are standard-layout classes?

    ```cpp
    struct E { };
    struct A : E { int x; };
    struct B : E { A a; };
    struct C : E { [[no_unique_address]] E e2; int y; };
    union  U { E e; int i; };
    struct D : E { U u; };
    ```

<details markdown="1">
<summary>Answer</summary>

- `A`: *M*(A) = {int}, the base `E` is not in it, and all data members are in `A`; standard-layout.
- `B`: *M*(B) = {A} ∪ *M*(A) = {A, int}, the base `E` is not in it, and the only data member is `B`'s own `a`. By the letter of the rules `B` is standard-layout, and Clang reports `true` too. But `a` contains an `E` base class subobject; if `a` were at offset 0 it would share an address with `B`'s `E` base class subobject, and distinct objects of the same type can't share an address. *M*(X) only collects non-base-class subobjects, so it doesn't catch this case. In our tests Clang puts `a` at offset 4, so the promise in [[class.mem.general#31]] that the first member has the same address as the object fails here. This is a hole in the definition.
- `C`: `e2` has zero size, so by ¶2.7.2 `E` ∈ *M*(C), and `E` is a base of `C`; not standard-layout.
- `U`: a union with no bases whose members are all standard-layout; yes.
- `D`: *M*(D) = {U} ∪ *M*(U) = {U, E, int}, and `E` is a base of `D`; no.
</details>

!!! question "Question 2"
    Is `struct X { X(const X&) = default; X(X&&) = delete; int i; };` trivially copyable? What if `X(X&&) = delete;` is changed to `X(X&&) { }`?

<details markdown="1">
<summary>Answer</summary>

The first one is. The copy constructor is eligible and trivial; the move constructor is deleted and not eligible. Because the user declared a move constructor, the copy assignment is implicitly declared as deleted ([[class.copy.assign#2]]) and the move assignment is not implicitly declared ([[class.copy.assign#4]]). The destructor is trivial. The only eligible function is the copy constructor, and it is trivial.

The second one isn't. The move constructor is user-provided, eligible but not trivial, violating ¶1.2.
</details>

!!! question "Question 3"
    Why does ¶8.2 only require at least one trivial eligible constructor, rather than a trivial default constructor?

<details markdown="1">
<summary>Answer</summary>

Implicit object creation only requires that some way of creating the object gives the program defined behavior; it doesn't specify which constructor. As long as there is one trivial constructor, objects of the type can come into existence without executing code; `memcpy`, for instance, corresponds to the semantics of a trivial copy constructor. Requiring a trivial default constructor would exclude types like `struct P { P() : x(1) {} int x; };`, whose default constructor does something but whose copy is just a bitwise copy, and such types are common in `memcpy` and network-buffer scenarios.
</details>
