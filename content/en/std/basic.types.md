---
title: Types
summary: "How types are classified; which bytes an object occupies in memory and which bits carry its value; what an incomplete type is; and what the categories trivially copyable, standard-layout, implicit-lifetime, literal and layout-compatible each guarantee."
updated: 2026-10-19
---

!!! tldr
    - An object occupies `sizeof(T)` bytes, called its object representation; the bits that actually carry the value are the value representation, and the rest are padding bits. So two equal objects can have different bytes.
    - An incomplete type (a class declared but not defined, an array of unknown bound, `void`, etc.) has unknown size and cannot be used to define objects, take `sizeof`, or do pointer arithmetic.
    - Trivially copyable types can be copied with `memcpy`; standard-layout types have C-compatible layout; objects of implicit-lifetime types can be created out of thin air by operations like `malloc`. The three are independent properties.
    - Literal type only means an object might be created during constant evaluation; since C++23 the concept has little use left.
    - Distinct scalar types are never layout-compatible, even if `int` and `long` have exactly the same size and representation.

[[basic.types]] (6.9) does not cover how to declare types; that is the business of [[dcl]] and [[class]]. It answers lower-level questions: what kinds of types there are, which bytes an object occupies in memory, and which types can be copied byte by byte or appear out of nowhere in memory from `malloc`. The aliasing rules in [[basic.lval]], lifetime in [[basic.life]], constant evaluation in [[expr.const]], and `<type_traits>` are all built on these terms.

This page covers 6.9.1 [[basic.types.general]]. The other subclauses each have their own page: [[basic.types.trivial]] (the `memcpy` guarantee), [[basic.fundamental]] (integers, characters, floating-point and so on, including 6.9.4 extended floating-point types), [[basic.compound]] (pointers, arrays, references and so on), [[basic.type.qualifier]] (const and volatile), and [[conv.rank]] (conversion ranks).

## Classification of types

¶1 is a note: types are divided into **fundamental types** (built-in integers, floating-point, `void` and so on, see [[basic.fundamental]]) and **compound types** (arrays, pointers, classes and so on, constructed from other types, see [[basic.compound]]). Types describe objects, references or functions.

References and functions are not objects ([[intro.object]]), but they have types. That is why the standard later defines object types separately (¶6): rules like `sizeof`, `new` and array elements only make sense for object types.

The primary type category traits in `<type_traits>` place every type in exactly one leaf of the tree below ([[meta.unary.cat]]):

```text
types
├── fundamental types                       is_fundamental
│   ├── arithmetic types                    is_arithmetic
│   │   ├── integral: bool, character types, signed/unsigned integers  is_integral
│   │   └── floating-point types            is_floating_point
│   ├── cv void                             is_void
│   ├── std::nullptr_t                      is_null_pointer
│   └── std::meta::info  (C++26)            is_reflection
└── compound types                          is_compound
    ├── arrays                              is_array
    ├── functions                           is_function
    ├── pointers                            is_pointer
    ├── lvalue / rvalue references          is_lvalue_reference / is_rvalue_reference
    ├── classes (non-union) / unions        is_class / is_union
    ├── enumerations                        is_enum
    └── pointers to data members / member functions  is_member_object_pointer / is_member_function_pointer
```

The categories defined in ¶6–¶9 of this page cut across this tree; for example, scalar types include both the arithmetic types among fundamental types and the pointers and enumerations among compound types. The primary category traits give the same result for `T` and `const T` ([[meta.unary.cat#2]]), so `is_integral_v<const int>` is true.

## Object and value representations (¶2)

```cpp run ok
#include <type_traits>

struct P { char c; int i; };   // usually 3 bytes of padding after c
struct Q { int a; int b; };    // no padding on common ABIs

static_assert(!std::has_unique_object_representations_v<P>);
static_assert( std::has_unique_object_representations_v<Q>);  // depends on the ABI
static_assert( std::has_unique_object_representations_v<int>);
static_assert(!std::has_unique_object_representations_v<float>);

int main() {}
```

On common ABIs `sizeof(P) == 8`, yet the value of a `P` is determined by only 5 bytes. Two equal `P` objects can differ in the other 3 bytes. The standard uses two terms to describe this.

¶2 The [[g:object-representation|object representation]] of a type `T` is the sequence of `sizeof(T)` `unsigned char` objects taken up by a complete object of type `T`. The [[g:value-representation|value representation]] is the set of bits in the object representation that participate in representing a value. Bits that are not part of the value representation are [[g:padding-bits|padding bits]].

Bit-fields are defined separately: the object representation is the bits the bit-field occupies (as many as its width, [[class.bit]]), and the value representation is the bits among them that participate in representing the value.

One value can have several object representations, for three reasons:

1. Padding bytes in classes, as in `P` above.
2. Padding bits inside scalar types. The 80-bit `long double` on x86-64 Linux occupies 16 bytes, of which 48 bits are padding; `bool` usually occupies 8 bits but has only two values ([[basic.fundamental#10]]).
3. One value with several bit patterns, or a bit pattern not corresponding to a unique value. IEEE floating-point `+0.0` and `-0.0` compare equal but differ in bits, and NaN has many bit patterns.

So `memcmp` and byte-wise hashing are reliable only for types where each value has exactly one object representation. `std::has_unique_object_representations` ([[meta.unary.prop]]) answers exactly this question; the example above passes on Clang 23.

`std::bit_cast` also looks at the value representation in constant evaluation: if a byte of the result comes from padding bits of the source, its value is indeterminate, and the whole expression is not a constant expression ([[bit.cast]]).

```cpp run error
#include <bit>

struct P  { char c; int i; };
struct B8 { unsigned char b[8]; };

constexpr P  p{1, 2};
constexpr B8 bytes = std::bit_cast<B8>(p);   // error: b[1..3] come from padding
```

!!! impl "Padding bytes may contain old data"
    When copying a struct, the compiler may skip the padding or leave arbitrary contents in it. Writing a struct byte by byte to a file or network packet can leak old data from memory. Security-sensitive code usually `memset`s the whole object first and then fills in the members one by one.

## Incomplete types (¶3–¶5)

```cpp run error
class X;                 // X is an incomplete type
extern X* xp;            // OK: a pointer to an incomplete type is fine
extern int arr[];        // the type of arr is incomplete
typedef int UNKA[];      // UNKA is an incomplete type
UNKA* arrp;
UNKA** arrpp;

void foo() {
  xp++;                  // error: X is incomplete, so the step size is unknown
  arrp++;                // error: incomplete type
  arrpp++;               // OK: sizeof(UNKA*) is known
}

struct X { int i; };     // now X is complete
int arr[10];             // now the type of arr is complete

X x;
void bar() {
  xp = &x;               // OK
  arrp = &arr;           // OK: int(*)[10] → int(*)[], a qualification conversion
  xp++;                  // OK: X is complete
  arrp++;                // error: UNKA can never be completed
}
```

This is Example 1 from ¶4 of the standard. `xp++` needs the size of `X` to compute the step, so it becomes valid only after `X` is defined. `arrp++`, however, is never valid, for the reason below.

¶3 The following are **incompletely-defined object types**: a class that has been declared but not defined; an enumeration type in certain contexts; and an array of unknown bound or of incomplete element type. Together with cv `void` they are [[g:incomplete-type|incomplete types]]. A footnote gives the substance: the size and layout of these types are unknown. So objects of incomplete type cannot be defined (note 2), and you cannot take `sizeof`, `new`, do pointer arithmetic or access members. Exactly which contexts forbid incomplete types is specified by the individual declaration and expression rules (note 4 in ¶5).

!!! note "When an enumeration is incomplete"
    An enumeration with a fixed underlying type is complete after its *enum-base*, so `sizeof(E)` can be used right after `enum class E : int;`. An enumeration without a fixed underlying type is complete only at its closing brace, because the compiler must see all enumerators to choose the underlying type ([[dcl.enum#6]]).

### A class becomes complete and keeps its type; an array becomes complete and changes type (¶4)

¶4 distinguishes two ways of becoming complete later:

- After `class X;`, `X` is incomplete; after `class X { ... };` it is complete, and it is the same type before and after. An array of `X`, `X[3]`, also becomes complete along with it, and is likewise the same type.
- In `extern int arr[];`, the type of `arr` is `int[]`. After the redeclaration `int arr[10];`, the type of `arr` becomes `int[10]`. These are two different types: what became complete is the declared type of the variable `arr`; the type `int[]` itself did not change.

So note 3 says that a pointer or reference to an array of unknown bound, and an array of unknown bound named by a typedef, are permanently incomplete types. In the example above, `arrp` has type `int(*)[]`; `int[]` cannot be completed, so `arrp++` is forever ill-formed. `arrp = &arr` converts `int(*)[10]` to `int(*)[]`, a qualification conversion allowed since C++20 ([[conv.qual]]).

### Where a class counts as complete

A class is complete after its definition. In addition, a class counts as complete within its **complete-class contexts**, even before the class definition ends. Complete-class contexts include member function bodies, default arguments, *noexcept-specifiers*, default member initializers and so on ([[class.mem.general#10]], [[class.mem.general#11]]). So a member function body can use members declared later and can write `sizeof(S)`:

```cpp run ok
struct S {
  int f() { return sizeof(S) + g(); }   // OK: a function body is a complete-class context
  int g() { return n; }
  int n = sizeof(S);                     // OK: so is a default member initializer
  // S member;                           // error: S is incomplete here
  S* next;                               // OK: a pointer to an incomplete type
};

int main() { return S{}.f() > 0 ? 0 : 1; }
```

### `delete` of an incomplete type {{c++26}}

```cpp run error
struct Impl;                          // incomplete
void destroy(Impl* p) { delete p; }   // error (C++26)
```

In C++23 and earlier, if `Impl` had a non-trivial destructor or a class-specific deallocation function, such a `delete` was UB, and compilers could only warn. Since C++26, [[expr.delete#4]] makes the program ill-formed if the object being deleted has incomplete type at the point of deletion. Clang 23 reports an error under `-std=c++2c` and a `-Wdelete-incomplete` warning under `-std=c++23`.

This is why, in the pimpl idiom, a class holding a `std::unique_ptr<Impl>` must define its destructor in the source file where `Impl` is complete.

## Object types (¶6)

¶6 An [[g:object-type|object type]] is any type other than a function type, a reference type or cv `void`, including cv-qualified ones.

The definition does not exclude incomplete types. An undefined class and `int[]` are object types, just incomplete. This way, pointers to object types ([[basic.compound#3]]) can cover cases like `X*` where `X` is not yet defined.

```cpp run ok
#include <type_traits>
struct Incomplete;
static_assert( std::is_object_v<int>);
static_assert( std::is_object_v<int[]>);          // incomplete, but still an object type
static_assert( std::is_object_v<Incomplete>);
static_assert(!std::is_object_v<int&>);
static_assert(!std::is_object_v<void>);
static_assert(!std::is_object_v<int(int)>);
int main() {}
```

## Scalars and the three categories built on them (¶7)

¶7 first defines [[g:scalar-type|scalar types]]: arithmetic types, enumeration types, pointer types, pointer-to-member types, `std::meta::info`, `std::nullptr_t`, and cv-qualified versions of these. Intuitively, a scalar is an indivisible value with no subobjects. `std::meta::info` is the type of reflection values in C++26 static reflection ([[P2996R13]]); it is a scalar, so it can be the type of a non-type template parameter.

The next three categories are all defined by the same pattern: scalar types, plus classes satisfying some condition, plus arrays, plus cv-qualified versions of these. They differ in the condition on classes.

| Category | Condition on classes | Arrays | Trait | Guarantee |
|---|---|---|---|---|
| trivially copyable | trivially copyable classes | elements must be in this category too | `is_trivially_copyable` | `memcpy` is a copy |
| standard-layout | standard-layout classes | elements must be in this category too | `is_standard_layout` | layout compatible with C |
| implicit-lifetime | implicit-lifetime classes | any array | `is_implicit_lifetime` | can be implicitly created |

These three properties are independent of each other. Their requirements on classes are all in [[class.prop]].

### Trivially copyable types

The significance of [[g:trivially-copyable-type|trivially copyable types]] is in [[basic.types.trivial]]: copying an object's bytes elsewhere and back, or copying bytes between two objects of the same type, carries the value along. For other types, `memcpy` guarantees nothing. `std::bit_cast` also requires both source and destination to be trivially copyable.

The conditions for a trivially copyable class ([[class.prop#1]]) use the word **eligible**: a special member function is eligible if it is not deleted, its constraints (if any) are satisfied, and it is not superseded by a more constrained function of the same kind ([[special]]). The conditions are: at least one eligible copy constructor, move constructor, copy assignment operator or move assignment operator; each such eligible function is trivial; and the destructor is trivial and not deleted.

```cpp run ok
#include <type_traits>
#include <string>

struct A { int x; double y; };        // yes
struct B { int x; B(const B&) {} };   // no: user-provided copy constructor
struct C { int x; ~C() {} };          // no: non-trivial destructor
struct D { std::string s; };          // no: a member is not
struct E { const int x; };            // yes: trivial copy constructor, assignment deleted

static_assert( std::is_trivially_copyable_v<A>);
static_assert(!std::is_trivially_copyable_v<B>);
static_assert(!std::is_trivially_copyable_v<C>);
static_assert(!std::is_trivially_copyable_v<D>);
static_assert( std::is_trivially_copyable_v<E>);
static_assert( std::is_trivially_copyable_v<const volatile int[4]>);
int main() {}
```

`E` cannot be assigned, yet it is trivially copyable. This property only says whether copying bytes preserves the value, not whether the type can be copied.

### Standard-layout types

The class part of [[g:standard-layout-type|standard-layout types]] ([[class.prop#2]]) roughly requires: no virtual functions or virtual base classes; the same access control for all non-static data members; all non-static data members first declared in the same class; members and base classes that are also standard-layout; plus a few restrictions preventing two subobjects of the same type from landing at the same address.

```cpp run ok
#include <type_traits>

struct B { int i; };
struct C : B { };                     // yes: all data members are in B
struct D : B { int j; };              // no: data members spread over B and D
struct E { int a; private: int b; };  // no: different access control
struct V { virtual void f(); };       // no: has a virtual function

static_assert( std::is_standard_layout_v<C>);
static_assert(!std::is_standard_layout_v<D>);
static_assert(!std::is_standard_layout_v<E>);
static_assert(!std::is_standard_layout_v<V>);
int main() {}
```

When these requirements are met, the layout is as predictable as a C struct: the object's address is the same as that of its first non-static data member (not a bit-field) and of each base class subobject ([[class.mem.general#31]]), so they are [[g:pointer-interconvertible|pointer-interconvertible]] and can be converted to each other with `reinterpret_cast` ([[basic.compound#7]]). `offsetof` is guaranteed only for standard-layout classes ([[support.types.layout]]), and the rule for reading the common initial sequence through an inactive union member also applies only to standard-layout structs ([[class.mem.general#30]]).

`E` in the example above is trivially copyable but not standard-layout; `struct SL { int i; ~SL(); };`, with a user destructor, is standard-layout but not trivially copyable. Types that are both are roughly the POD of older standards.

### Implicit-lifetime types

```cpp run ok
#include <cstdlib>

struct X { int a, b; };

int main() {
  X* p = static_cast<X*>(std::malloc(sizeof(X)));
  p->a = 1; p->b = 2;     // strictly UB in C++17: no X object was created
  int r = p->a + p->b;    // OK since C++20: malloc implicitly created an X
  std::free(p);
  return r == 3 ? 0 : 1;
}
```

This is a common pattern in C-style code. In the C++17 object model, objects could only be created by definitions, `new` expressions and the like; the memory returned by `malloc` contained no `X` object, and accessing `p->a` was strictly UB. C++20 fixed this with [[P0593R6]].

[[intro.object#13]] specifies that operations such as `malloc`, `operator new`, `memcpy`, `std::bit_cast`, and starting the lifetime of an `unsigned char` or `std::byte` array **implicitly create objects** in the corresponding storage: as long as creating some objects would give the program defined behavior, those objects are considered created. Only objects of [[g:implicit-lifetime-type|implicit-lifetime types]] can be created this way. Creating and destroying objects of these types requires running no code, so assuming they already exist does not change the program's behavior.

An implicit-lifetime class satisfies one of two conditions ([[class.prop#8]]): it is an **aggregate** (a class with no user-declared constructors, no virtual functions, no private or protected direct non-static data members and so on, which can be initialized member by member with braces, see [[dcl.init.aggr]]) whose destructor is not user-provided; or it has at least one trivial eligible constructor and a trivial, non-deleted destructor.

```cpp run ok
#include <type_traits>

struct NI  { NI() {} ~NI() {} };    // construction and destruction both non-trivial
struct Agg { int a; NI n; };        // an aggregate whose destructor is not user-provided

static_assert(!std::is_implicit_lifetime_v<NI>);
static_assert( std::is_implicit_lifetime_v<NI[3]>);  // arrays always are
static_assert( std::is_implicit_lifetime_v<Agg>);    // even with a non-trivial member
int main() {}
```

Two results are often surprising:

- Every array type is an implicit-lifetime type, even if its element type is not. Implicitly creating an array does not create its elements; they still have to be constructed separately, for example with placement new. This is what containers rely on when they allocate a block of memory, treat it as `T[N]`, and construct elements one by one.
- An aggregate counts even if it has non-trivial members. Implicitly creating an `Agg` starts only the lifetime of `Agg` itself; the member `n` is not constructed by it.

C++23 added the corresponding trait `std::is_implicit_lifetime` ([[P2674R1]]) and `std::start_lifetime_as` ([[obj.lifetime]]), which explicitly starts an object's lifetime over existing bytes.

## Literal types (¶8)

A [[g:literal-type|literal type]] is the type a `constexpr` variable must have ([[dcl.constexpr]]). ¶8 lists: cv `void`, scalar types, reference types, arrays of literal type, and class types satisfying all of the following:

- ¶8.5.1 it has a `constexpr` destructor;
- ¶8.5.2 all of its non-variant non-static data members and base classes are of non-volatile literal types;
- ¶8.5.3 and there is a way to create an object from scratch in constant evaluation: it is a closure type (the type of a lambda); or it is an aggregate (for a union, with no variant members or at least one variant member of non-volatile literal type, and the anonymous union members of a non-union aggregate must satisfy the same); or it has at least one `constexpr` constructor or constructor template that is not a copy or move constructor, inherited ones included.

Copy and move constructors don't count because they need an existing object.

```cpp run error
struct L   { constexpr L(int) {} };   // a literal type
struct NL  { NL(int) {} };            // not: no constexpr constructor
struct NL2 {                          // not: its only constexpr constructor
  constexpr NL2(const NL2&) = default; //      is the copy constructor
  int x;
};
struct VM  { volatile int x; };       // not: a member is volatile

constexpr L  a(1);    // OK
constexpr NL b(1);    // error: NL is not a literal type
constexpr VM c{1};    // error: VM is not a literal type
```

!!! std
    A literal type is one for which it might be possible to create an object within a constant expression.

Note 5 stresses the word "might": being a literal type guarantees neither that an object of it can actually be created in a constant expression, nor that its objects can be used in constant expressions.

The weight of this concept has been declining. C++20 allowed `constexpr` destructors, making `std::string` and `std::vector` literal types. C++23's [[P2448R2]] removed the requirement that parameter and return types of `constexpr` functions be literal types. Today it is mainly still used for the types of `constexpr` variables and for which objects can be created in constant evaluation. `std::is_literal_type` was deprecated in C++17 and removed in C++20 precisely because the question it answers has almost no practical use.

## Layout-compatible types (¶9)

¶9 Two types *cv1* `T1` and *cv2* `T2` are [[g:layout-compatible-types|layout-compatible types]] if:

- they are the same type, possibly with different cv-qualification, so `int` and `const int` are layout-compatible;
- they are layout-compatible enumerations, i.e. with the same underlying type ([[dcl.enum]]);
- they are layout-compatible standard-layout classes: the common initial sequence of the two classes (the longest sequence of members, starting from the first, whose types are pairwise layout-compatible) covers all members ([[class.mem.general#28]]; for unions see [[class.mem.general#29]]).

Distinct scalar types are never layout-compatible, even with exactly the same size and representation: `int` and `unsigned int`, `char` and `signed char`, and `int` and `long` (both 32-bit on Windows) are not.

```cpp run ok
struct A { int a; char b; };
struct B { int x; char y; };            // layout-compatible with A
struct C { int x; unsigned char y; };   // not layout-compatible with A
enum E1 : int {};
enum class E2 : int {};

// libc++ does not yet provide std::is_layout_compatible; use the Clang and GCC builtin here
static_assert( __is_layout_compatible(int, const int));
static_assert(!__is_layout_compatible(int, unsigned));
static_assert( __is_layout_compatible(A, B));
static_assert(!__is_layout_compatible(A, C));
static_assert( __is_layout_compatible(E1, E2));
int main() {}
```

Layout compatibility has two uses. First, the common initial sequence of two struct members of a union requires corresponding members to be layout-compatible, so that the common prefix can be read through an inactive member ([[class.mem.general#27]], [[class.mem.general#30]]). Second, pointers to layout-compatible types have the same value representation and alignment requirements ([[basic.compound#3]]).

`std::is_layout_compatible` is a trait added in C++20, but the libc++ shipped with Clang 23 does not provide it yet.

## Implementation view

!!! impl "The ABI's triviality is not the standard's trivially copyable"
    When the Itanium C++ ABI (GCC and Clang on Linux and macOS) decides whether a class-type argument can be passed in registers, it checks whether the class is non-trivial for the purposes of calls: it has a non-trivial copy constructor, move constructor or destructor, or all of its copy and move constructors are deleted. Whether copy assignment is trivial does not affect argument passing, but it does affect `is_trivially_copyable`. Clang's `[[clang::trivial_abi]]` lets types with non-trivial destructors be passed in registers too. MSVC's x64 ABI has its own rules.

!!! impl "Clang's verdict when all copy and move operations are deleted"
    `struct F { int x; F& operator=(F&&) = delete; };` declares a move assignment operator, so the implicit copy constructor and copy assignment operator are defined as deleted ([[class.copy.ctor]], [[class.copy.assign]]), and the move constructor is no longer implicitly declared. Deleted functions are not eligible, so `F` has no eligible copy or move operation and, per [[class.prop#1.1]], is not trivially copyable. But on Clang 23 `std::is_trivially_copyable_v<F>` is `true`, which disagrees with the standard. Portable code should not rely on such edge cases.

## History

!!! history
    - C++98 had only the single concept of POD (plain old data), which carried three duties at once: can be `memcpy`ed, layout-compatible with C, and statically initializable. Its conditions were strict: any user-declared constructor destroyed POD-ness.
    - C++11 split POD into two independent concepts, trivial (and thus trivially copyable) and standard-layout, with POD as their conjunction. It also introduced `constexpr` and literal types.
    - C++20 introduced eligible special member functions and rewrote trivially copyable into today's definition; introduced implicit-lifetime types and implicit object creation ([[P0593R6]]); and deprecated `std::is_pod`.
    - C++23 removed the literal-type requirement for `constexpr` functions ([[P2448R2]]) and added `std::is_implicit_lifetime` ([[P2674R1]]) and `std::start_lifetime_as`.
    - In C++26, `std::meta::info` became a scalar type; trivial classes and `std::is_trivial` were moved to Annex D and deprecated ([[P3247R2]], see [[depr.meta.types]]), because "trivial" bundles "can be `memcpy`ed" with "default construction does nothing", a combination almost no code needs; and `delete` of an incomplete class type went from UB to ill-formed.

## Common misconceptions

!!! pitfall "Mixing up the various kinds of trivial"
    - `is_trivially_copyable<T>`: can be `memcpy`ed. This is the one most code actually needs.
    - `is_trivial<T>` (deprecated in C++26): trivially copyable, and with a trivial default constructor. `struct S { int x = 0; };` has a default member initializer, so its default construction is non-trivial and it is not a trivial type, yet it can be `memcpy`ed just fine.
    - `is_standard_layout<T>`: C-compatible layout, `offsetof` usable; unrelated to whether it can be `memcpy`ed.
    - `is_pod<T>` (deprecated in C++20): the conjunction of the first two; don't use it to decide anything anymore.

!!! pitfall "Trivially copyable means you can `memcpy` into any object of that type"
    The guarantee of [[basic.types.trivial#3]] does not cover **potentially-overlapping subobjects**, i.e. base class subobjects and members with `[[no_unique_address]]` ([[intro.object#7]]). They may share tail padding with other objects, and copying a whole block of `sizeof` bytes can overwrite adjacent data; see [[basic.types.trivial]] for an example.

!!! pitfall "Using traits on incomplete types"
    Most type traits require their argument to be a complete type, cv `void`, or an array of unknown bound (see the preconditions in [[meta.unary.prop]]); otherwise the behavior is undefined. Instantiating the same trait specialization before and after a type is completed can give different results, which violates the ODR ([[basic.def.odr]]).

## Questions

!!! question "1. Which of these are implicit-lifetime types?"
    ```cpp
    struct A { int x; A() = default; };
    struct B { int x; B() {} };
    struct C { std::string s; };     // an aggregate
    struct D { D() = default; ~D() {} };
    using E = std::string[2];
    ```

<details markdown="1">
<summary>Answer</summary>

- `A` is. Since C++20, a user-declared constructor (even `= default`) makes a class no longer an aggregate ([[dcl.init.aggr]]), so `A` does not satisfy [[class.prop#8.1]]. But its default constructor is trivial and so is its destructor, satisfying [[class.prop#8.2]].
- `B` is. It has a user-provided constructor, so it is not an aggregate, and its default construction is not trivial. But the implicitly declared copy constructor is trivial and eligible, and ¶8.2 only requires at least one trivial eligible constructor; a copy constructor counts.
- `C` is. It is an aggregate whose destructor is not user-provided, regardless of whether `std::string` is an implicit-lifetime type.
- `D` is not. `~D() {}` is a user-provided destructor, which is not trivial, so neither condition holds.
- `E` is. All array types are.

`std::is_implicit_lifetime_v` on Clang 23 gives the same verdicts for these five types.
</details>

!!! question "2. After `extern int a[]; int a[10];`, what is `decltype(a)`? After `int (*p)[] = &a;`, can you write `p + 1`?"

<details markdown="1">
<summary>Answer</summary>

After the redeclaration, `a` has type `int[10]`, and `decltype(a)` is `int[10]` (¶4: the array types in the two declarations are different types). `int (*p)[] = &a;` is valid; it is a qualification conversion allowed since C++20. But the type `p` points to, `int[]`, is permanently incomplete, and `p + 1` needs its size, so it is ill-formed.
</details>

!!! question "3. Why does ¶7 explicitly list the cv-qualified versions in every category?"

<details markdown="1">
<summary>Answer</summary>

The definitions of categories like integral and floating-point types already include cv versions, but in the standard's terminology, enumeration types, pointer types, pointer-to-member types, `std::nullptr_t` and class types all refer to cv-unqualified types. Without listing them explicitly, `const MyEnum`, `int* const` and `const std::nullptr_t` would be excluded from categories like scalar and trivially copyable. Including cv versions uniformly in the category definitions makes traits give consistent results for `T` and `const T`.
</details>
