---
title: Pointer and pointer-to-member declarators
summary: "What the declarators `* cv D1` and `C::* cv D1` mean: cv qualifies the pointer itself, why `T**` can't convert to `const T**`, what can't have pointers, and how pointers to members are declared, restricted and represented in the ABI."
updated: 2026-10-19
---

!!! tldr
    - The cv after `*` qualifies the pointer itself. To make the pointed-to object const, `const` goes in the specifiers: `const int *p` or `int const *p`.
    - `int*` converts implicitly to `const int*`, but `int**` can't convert to `const int**`, since that would allow modifying a const object through it. Write `const int* const*` when you need this.
    - There are no pointers to references, no pointers to bit-fields, and no ordinary pointers to function types with cv- or ref-qualifiers.
    - A pointer to member `T C::*` is a different type from a pointer. Declaring one doesn't require `C` to be complete or to actually have a member of that type; it can't point to a static member, a member of reference type, or `void`.

This page covers the two prefix declarator operators of [[dcl.decl]]: ordinary pointers `*` and pointers to members `C::*`. References `&` and `&&` are in [[dcl.ref]].

## Pointer declarators [dcl.ptr]

### cv qualifies the pointer itself (¶1)

```cpp run ok
#include <type_traits>

const int ci = 10, *pc = &ci, *const cpc = pc, **ppc;
int i, *p, *const cp = &i;

static_assert(std::is_same_v<decltype(pc),  const int *>);       // points to const int
static_assert(std::is_same_v<decltype(cpc), const int *const>);  // const pointer to const int
static_assert(std::is_same_v<decltype(ppc), const int **>);      // pointer to const int*
static_assert(std::is_same_v<decltype(cp),  int *const>);        // const pointer to int

int main() { }
```

¶1 If `D` in a declaration `T D` has the form `* cv D1`, the type of the name is "cv pointer to `T`", preceded by the modifiers accumulated by the inner declarator `D1` (the recursive procedure for computing the type is in [[dcl.decl]]).

!!! std
    The *cv-qualifier*s apply to the pointer and not to the object pointed to.

The cv after `*` qualifies the pointer itself, not the object pointed to. The pointed-to type is the `T` given by the specifiers, so to make the object const, `const` must go into the specifiers. Likewise, attributes after `*` appertain to the pointer type.

Reading `*const cpc` above by this rule: the outermost operator is `* const`, which sits right next to the `const int` given by the specifiers, so `cpc` is a const pointer to `const int`.

### const correctness (¶2)

¶2 is an example that uses one set of variables to show which operations are allowed:

<div class="compare" markdown="1">

```cpp
// valid operations
i = ci;     // read a const object
*cp = ci;   // cp is const, *cp isn't
pc++;       // pc itself isn't const
pc = cpc;   // copy a pointer value
pc = p;     // int* → const int*
ppc = &pc;  // same type
```

```cpp
// ill-formed operations
ci = 1;     // error: modifies a const object
ci++;       // error
*pc = 2;    // error: through a pointer to const
cp = &ci;   // error: cp is const
cpc++;      // error: cpc is const
p = pc;     // error: discards const
ppc = &p;   // error: int** → const int**
```

</div>

The last line is worth thinking about. If converting `int*` to `const int*` is safe, why isn't converting `int**` to `const int**`? Suppose `ppc = &p` were allowed; then you could write:

```cpp
*ppc = &ci;   // OK: *ppc has type const int*, and so does &ci
*p = 5;       // but *ppc is p, and p now points to ci: a const object is modified
```

`ppc` uses a location that holds an `int*` as if it held a `const int*`, and the `const` is silently lost. So [[conv.qual]] requires that if `const` is added at some level of a multi-level pointer, every level outside it must also get `const`. `int**` can convert to `const int* const*`, because the outer level is const too, and `*ppc = &ci` can no longer be written.

```cpp run ok
int *p;
const int *const *ok = &p;   // OK: const added at the outer level too
int main() { (void)ok; }
```

!!! pitfall "Passing `char**` to `const char**`"
    Passing a `char**` like `argv` to a function whose parameter is `const char**` is an error. The compiler isn't being overly strict; it's plugging the hole above. Change the parameter to `const char* const*`.

### Pointers that can't be formed (¶3)

¶3 is a note; the normative rules are elsewhere:

- There are no pointers to references, because references are not objects ([[dcl.ref#5]]). `int&* p;` is ill-formed.
- Function types with cv- or ref-qualifiers, such as `void() const`, are only used to describe the types of non-static member functions and can't form ordinary function pointers ([[dcl.fct#11]]); they can form pointers to members such as `void (S::*)() const`.
- The address of a bit-field can't be taken ([[class.bit]]), so a pointer never points to a bit-field.

Apart from these, a pointer can point to any object type, function type, `void`, and arrays, including arrays of unknown bound, `int (*)[]`.

## Pointers to members [dcl.mptr]

### Declaring pointers to members (¶2–3)

```cpp run ok
struct X {
  void f(int) { }
  int a;
};
struct Y;               // incomplete type

int X::* pmi = &X::a;
void (X::* pmf)(int) = &X::f;
double X::* pmd;        // OK even though X has no double member
char Y::* pmc;          // OK even though Y is incomplete

int main() {
  X obj;
  obj.*pmi = 7;         // assigns to obj.a
  (obj.*pmf)(7);        // calls obj.f(7)
  return obj.a == 7 ? 0 : 1;
}
```

¶2 If `D` has the form `C::* cv D1` and `C::` designates a class, the type of the name is "cv pointer to member of class `C` of type `T`". The example in paragraph 3 is the code above.

`pmd` and `pmc` are both valid, which shows that a pointer-to-member type is just a combination of a class and a member type. Declaring one requires neither that the class be complete nor that it actually have such a member. The requirements apply when a value is formed: `&X::a` must find a non-static member ([[expr.unary.op]]).

In the call `(obj.*pmf)(7)`, the parentheses can't be omitted: `.*` has lower precedence than function call, so `obj.*pmf(7)` parses as `obj.*(pmf(7))`. You can also write `std::invoke(pmf, obj, 7)`. The rules for `.*` and `->*` are in [[expr.mptr.oper]].

The last sentence of ¶2 says that `C::` can't designate an anonymous union. Normally you can't write a name designating an anonymous union, but a C++26 [[g:splice-specifier|splice-specifier]] can produce such a qualifier, and this sentence is there for it.

¶1 The component names of a *ptr-operator* ([[expr.prim.id.unqual#2]]) are those of its `C::` part. Name lookup uses this definition; for example, [[basic.lookup.unqual#5]] specifies how these names are looked up in a conversion function name `operator T C::*`.

### What it can't point to (¶4)

¶4 A pointer to member can't point to a static member or a member of reference type, and can't be a "pointer to member of cv `void`".

```cpp run error
struct X { static int s; int& r; };
int X::* p1 = &X::s;   // error: &X::s has the ordinary pointer type int*
int& X::* p2;          // error: points to a reference member
void X::* p3;          // error: points to void
```

A static member doesn't belong to any object, and `&X::s` yields an ordinary pointer. A reference is not an object and has no location to record.

### A pointer to member is not a pointer (¶5)

¶5 is a note: pointers to members and pointers are different types. A pointer to member can only be declared with the `C::*` syntax, and an ordinary pointer declarator never produces a pointer to member. C++ also has no "reference to member" type.

So a pointer to member can't be converted to `void*` or compared with an ordinary pointer; `std::is_pointer_v<int X::*>` is `false`, and `std::is_member_pointer_v<int X::*>` is `true` ([[basic.compound]]). Conversions between pointers to members are in [[conv.mem]]: a pointer to member of a base class can convert to a pointer to member of a derived class, the opposite direction from ordinary pointers.

## Implementation notes

!!! impl
    - On mainstream platforms an ordinary pointer is just an address. `T* const` and `T*` have the same representation; cv only matters at compile time.
    - In the Itanium C++ ABI (used by GCC and Clang on Linux and macOS), a pointer to data member is a `ptrdiff_t` holding the member's byte offset from the start of the object. Offset 0 is a valid value, so the null member pointer is represented as -1. In our tests (arm64, Clang 23), for a class with virtual functions and members `int a, b`, `&X::a` and `&X::b` are 8 and 12 (the first 8 bytes are the vtable pointer), and `nullptr` is -1.
    - A pointer to member function consists of two words `{ptr, adj}`, where `adj` is the adjustment applied to `this` before the call. For a non-virtual function, `ptr` is the function address; for a virtual function, `ptr` encodes the position in the vtable. x86-64 uses the lowest bit of `ptr` to mark virtual functions; the ARM variant uses the lowest bit of `adj` instead, because the lowest bit of a code address is used for Thumb. In our tests, the first virtual function gave `{0, 1}`.
    - In MSVC, the size of a pointer to member depends on the class's inheritance model (single, multiple, virtual). A pointer to member formed while the class is still incomplete can only use the most general, and largest, representation. That is the ABI cost of allowing pointers to members of incomplete classes.

## History

!!! history
    - The rules for ordinary pointers are inherited from C; pointers to members have been in C++ since its early days.
    - C++11 allowed attributes after `*` and `C::*`; `nullptr` converts to any pointer-to-member type.
    - C++20 unified and relaxed qualification conversions ([[conv.qual]]), for example allowing a pointer to an array of known bound to convert to a pointer to an array of unknown bound.

## Questions

!!! question "Question 1"
    What is the type of `p` in `int *const *volatile *p;`? Which of `p`, `*p`, `**p` and `***p` can be assigned to?

<details markdown="1">
<summary>Answer</summary>

The specifier is `int` and the declarator is `*const *volatile *p`. Of the three prefix operators, the leftmost `*const` is outermost; it sits right next to `int`, giving "const pointer to `int`"; the next level `*volatile` gives "volatile pointer to [the former]"; the innermost `*` gives "pointer to [the former]".

`p` has no cv and can be assigned to; `*p` is a volatile pointer and can be assigned to, since volatile doesn't prevent writes; `**p` is a const pointer and can't be assigned to; `***p` is an `int` and can be assigned to.
</details>

!!! question "Question 2"
    Why can you declare a pointer to member of an incomplete class, `char Y::* pmc;`, but not write `sizeof(Y)`?

<details markdown="1">
<summary>Answer</summary>

Declaring `char Y::*` just composes a type and doesn't need to know `Y`'s layout, just as declaring `Y*` doesn't need `Y` to be complete. A complete class is only needed when a value is formed (`&Y::m` has to look up the member) or used (`obj.*pmc` needs an object). `sizeof(Y)`, by contrast, must know the layout. The cost shows up in the ABI: the Itanium ABI's pointer-to-member representation is independent of the class; MSVC's depends on the inheritance model, and for an incomplete class it can only conservatively use the most general representation.
</details>
